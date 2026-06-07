from __future__ import annotations

import json
import logging
import re
from time import perf_counter
from typing import Any, Mapping

from backend.services.ai_client import LLMClient, LLMClientError
from backend.services.entity_extractor import ProjectData, _mock_extract_entities
from backend.services.scene_planner import _ensure_scene_data, _mock_scenes, _normalize_chapter_meta, _normalize_scene
from backend.services.script_generator import _mock_script_lines, _normalize_script_lines

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
MAX_GENERATION_ATTEMPTS = 2
MIN_GENERATED_SCENES = 3
MIN_GENERATED_SCRIPT_LINES_PER_SCENE = 10

logger = logging.getLogger(__name__)


async def generate_chapter_script_data(
    chapter_text: str,
    project_data: ProjectData,
    *,
    chapter_meta: Mapping[str, Any] | None = None,
    client: LLMClient | None = None,
) -> tuple[ProjectData, dict[str, Any]]:
    data = _ensure_project_data(project_data)
    llm = client or LLMClient()
    source = _normalize_chapter_meta(chapter_meta, chapter_text)
    messages = _chapter_messages(chapter_text, data, source)
    prompt_chars = 0

    started_at = perf_counter()
    response_chars = 0
    quality_issues: list[str] = []
    generated: dict[str, Any] | list[Any] = {}
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        attempt_messages = messages if attempt == 1 else _retry_messages(messages, quality_issues)
        prompt_chars += _message_chars(attempt_messages)
        generated = await llm.json(
            attempt_messages,
            temperature=0.35,
            mock_response=_mock_chapter_result(chapter_text, data),
        )
        if not isinstance(generated, dict):
            generated = {}
        response_chars = len(json.dumps(generated, ensure_ascii=False))
        quality_issues = [] if llm.mock_mode else _generation_quality_issues(generated)
        if not quality_issues:
            break
        logger.warning(
            "chapter generation quality check failed chapter=%s attempt=%s issues=%s",
            source["chapter_index"],
            attempt,
            "; ".join(quality_issues),
        )
    if quality_issues:
        raise LLMClientError(
            "AI API output did not meet the quality floor: "
            + "; ".join(quality_issues)
            + "."
        )
    elapsed = perf_counter() - started_at

    character_aliases = _merge_named_items(data, "characters", generated.get("characters"), "char")
    location_aliases = _merge_named_items(data, "locations", generated.get("locations"), "loc")
    location_aliases.update(_merge_scene_locations(data, generated.get("scenes")))
    data = _ensure_scene_data(data)
    _drop_default_location_if_possible(data)
    location_aliases.update(_item_aliases(data.get("locations", [])))

    new_scenes, scene_aliases, nested_script = _merge_scenes(
        generated.get("scenes"),
        data,
        source,
        chapter_text,
        character_aliases,
        location_aliases,
    )

    script_lines = _script_lines_from_generated(generated.get("script"), nested_script)
    if not script_lines and llm.mock_mode:
        scoped_data = {**data, "scenes": new_scenes}
        script_lines = _mock_script_lines(scoped_data)

    prepared_lines = [
        _prepare_script_line(line, scene_aliases, character_aliases, len(new_scenes) == 1)
        for line in script_lines
        if isinstance(line, dict)
    ]
    scoped_data = {**data, "scenes": new_scenes}
    data.setdefault("script", []).extend(_normalize_script_lines(prepared_lines, scoped_data))

    stage_log = {
        "stage": "chapter_generate",
        "chapter_index": source["chapter_index"],
        "chapter_title": source["chapter_title"],
        "prompt_chars": prompt_chars,
        "elapsed_seconds": round(elapsed, 3),
        "response_chars": response_chars,
    }
    logger.info(
        "ai_stage stage=%s chapter=%s prompt_chars=%s elapsed=%.3f response_chars=%s",
        stage_log["stage"],
        stage_log["chapter_index"],
        stage_log["prompt_chars"],
        elapsed,
        stage_log["response_chars"],
    )
    return data, stage_log


def _chapter_messages(
    chapter_text: str,
    project_data: ProjectData,
    chapter_meta: dict[str, Any],
) -> list[dict[str, str]]:
    target_language = str(project_data.get("project", {}).get("target_language") or "zh")
    context = {
        "project": project_data.get("project", {}),
        "existing_characters": project_data.get("characters", []),
        "existing_locations": project_data.get("locations", []),
        "existing_scene_count": len(project_data.get("scenes", [])),
    }
    schema = {
        "characters": [{"name": "", "role": "", "description": "60字以内"}],
        "locations": [{"name": "", "description": "60字以内"}],
        "scenes": [
            {
                "title": "",
                "location_name": "",
                "characters": ["角色名或已有角色ID"],
                "summary": "120字以内，说明目标/冲突/转折/承接",
                "source_excerpt": "原文摘录，120字以内",
                "paragraph_range": [1, 1],
                "script": [{"type": "camera|action|dialogue|transition|note", "speaker_name": "", "content": "40-90字"}],
            }
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是影视剧本改编助手。只输出一个合法 JSON 对象，不要 Markdown，不要解释。\n"
                f"目标输出语言 target_language={target_language}。\n"
                "质量硬性要求：每章至少 3 个场景，原文信息量足够时输出 4-5 个场景；"
                "每个场景的 script 至少 10 行，且必须覆盖镜头、动作、对白、反应、信息揭示和转场。"
                "场景之间必须有连续因果：铺垫 -> 目标受阻 -> 发现/冲突升级 -> 转折/悬念，后一场要承接前一场的信息。"
                "不要只写摘要，不要用空泛句子填充；每行正文都要包含可拍摄动作、可听见对白或明确镜头调度。"
                "对白密度要足够：每个有角色互动的场景至少 3 行 dialogue，对白要符合人物处境，不能像旁白总结。"
                "镜头语言要具体：写清景别、运动、视线、物件、声响或节奏变化，避免只写‘镜头推进’。"
                "必须保留原文关键细节、人物动机、物件、地点变化和悬念信息；不要凭空改写主线。"
                "characters/locations 只写本章明确出现的关键新增项，避免把动作短语、代词、情绪、物件或地点描述误当人物。"
                "content 中不要使用英文双引号；引用编号或台词时使用中文书名号或单引号。"
                "source_excerpt 必须直接摘自原文。paragraph_range 必须是 [start,end] 数组。"
                "characters 可用已有 ID 或角色名；script 必须放在每个 scene 内，不要使用顶层 script 数组。\n"
                f"JSON 格式：{json.dumps(schema, ensure_ascii=False)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"项目上下文：{json.dumps(context, ensure_ascii=False)}\n\n"
                f"章节信息：{json.dumps(chapter_meta, ensure_ascii=False)}\n\n"
                f"本章完整原文：\n{chapter_text}"
            ),
        },
    ]


def _retry_messages(base_messages: list[dict[str, str]], issues: list[str]) -> list[dict[str, str]]:
    return [
        *base_messages,
        {
            "role": "user",
            "content": (
                "上一版输出未达到硬性质量要求："
                + "；".join(issues)
                + "。请重新输出完整 JSON：至少 3 个场景，每个 scene.script 至少 10 行，"
                "保留原文关键细节，保持场景之间因果承接。不要解释，不要 Markdown。"
            ),
        },
    ]


def _generation_quality_issues(generated: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    scenes = generated.get("scenes")
    if not isinstance(scenes, list):
        return ["scenes must be a list"]
    if len(scenes) < MIN_GENERATED_SCENES:
        issues.append(f"expected at least {MIN_GENERATED_SCENES} scenes, got {len(scenes)}")

    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            issues.append(f"scene {index} is not an object")
            continue
        script = scene.get("script") or scene.get("script_lines")
        if not isinstance(script, list):
            issues.append(f"scene {index} has no nested script list")
            continue
        usable_lines = [line for line in script if isinstance(line, dict) and str(line.get("content") or line.get("text") or "").strip()]
        if len(usable_lines) < MIN_GENERATED_SCRIPT_LINES_PER_SCENE:
            issues.append(
                f"scene {index} expected at least {MIN_GENERATED_SCRIPT_LINES_PER_SCENE} script lines, got {len(usable_lines)}"
            )
    return issues[:8]


def _ensure_project_data(project_data: ProjectData) -> ProjectData:
    data = dict(project_data)
    data.setdefault("project", {"title": "Untitled"})
    data.setdefault("characters", [])
    data.setdefault("locations", [])
    data.setdefault("scenes", [])
    data.setdefault("script", [])
    return data


def _merge_named_items(data: ProjectData, key: str, items: Any, prefix: str) -> dict[str, str]:
    existing = data.setdefault(key, [])
    aliases = _item_aliases(existing)
    if not isinstance(items, list):
        return aliases

    names = {str(item.get("name")): item for item in existing if isinstance(item, dict) and item.get("name")}
    ids = {str(item.get("id")) for item in existing if isinstance(item, dict) and item.get("id")}
    allowed_keys = {"id", "name", "role", "description"} if key == "characters" else {"id", "name", "description"}

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("speaker_name") or "").strip()
        if not name or not _valid_named_item(key, name, item):
            continue
        raw_id = str(item.get("id") or "").strip()
        if name in names:
            assigned_id = str(names[name]["id"])
        else:
            if key == "locations":
                duplicate_id = _matching_location_id(name, existing)
                if duplicate_id:
                    aliases[name] = duplicate_id
                    aliases[duplicate_id] = duplicate_id
                    if raw_id:
                        aliases[raw_id] = duplicate_id
                    continue
            assigned_id = _next_id(prefix, ids)
            entry = {field: item[field] for field in allowed_keys if field in item and item[field]}
            entry["id"] = assigned_id
            entry["name"] = name
            existing.append(entry)
            names[name] = entry
            ids.add(assigned_id)

        aliases[name] = assigned_id
        aliases[assigned_id] = assigned_id
        if raw_id:
            aliases[raw_id] = assigned_id

    return aliases


def _merge_scene_locations(data: ProjectData, scenes: Any) -> dict[str, str]:
    if not isinstance(scenes, list):
        return {}
    scene_locations: list[dict[str, str]] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        location_name = str(scene.get("location_name") or scene.get("location") or "").strip()
        if location_name:
            scene_locations.append({"name": location_name, "description": "从场景地点识别到的地点"})
    return _merge_named_items(data, "locations", scene_locations, "loc")


def _drop_default_location_if_possible(data: ProjectData) -> None:
    locations = data.get("locations")
    if not isinstance(locations, list) or len(locations) <= 1:
        return
    data["locations"] = [
        location
        for location in locations
        if not (
            isinstance(location, dict)
            and str(location.get("id") or "") == "loc_1"
            and str(location.get("name") or "") in {"未知地点", "未命名"}
        )
    ] or locations


def _merge_scenes(
    scenes: Any,
    data: ProjectData,
    chapter_meta: dict[str, Any],
    chapter_text: str,
    character_aliases: dict[str, str],
    location_aliases: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    if not isinstance(scenes, list):
        scenes = []

    new_scenes: list[dict[str, Any]] = []
    scene_aliases: dict[str, str] = {}
    nested_script: list[dict[str, Any]] = []

    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        raw_id = str(scene.get("id") or "").strip()
        prepared = _prepare_scene(scene, character_aliases, location_aliases)
        if raw_id and not ID_RE.fullmatch(raw_id):
            prepared.pop("id", None)

        normalized = _normalize_scene(prepared, data, chapter_meta, chapter_text)
        if not normalized:
            continue
        data["scenes"].append(normalized)
        new_scenes.append(normalized)

        aliases = {raw_id, str(scene.get("title") or "").strip(), normalized["id"]}
        for alias in aliases:
            if alias:
                scene_aliases[alias] = normalized["id"]

        for line in _scene_script_lines(scene):
            nested = dict(line)
            nested["scene_id"] = normalized["id"]
            nested_script.append(nested)

    return new_scenes, scene_aliases, nested_script


def _prepare_scene(
    scene: dict[str, Any],
    character_aliases: dict[str, str],
    location_aliases: dict[str, str],
) -> dict[str, Any]:
    prepared = dict(scene)
    location_id = str(prepared.get("location_id") or "").strip()
    location_name = str(prepared.get("location_name") or prepared.get("location") or "").strip()
    if location_id in location_aliases:
        prepared["location_id"] = location_aliases[location_id]
    elif location_name in location_aliases:
        prepared["location_id"] = location_aliases[location_name]
    elif location_name:
        prepared["location_name"] = location_name

    characters = prepared.get("characters")
    if isinstance(characters, list):
        prepared["characters"] = [character_aliases.get(str(value), str(value)) for value in characters]

    source_excerpt = prepared.get("source_excerpt") or prepared.get("excerpt")
    if source_excerpt:
        prepared["_source_excerpt"] = str(source_excerpt)
    if prepared.get("paragraph_range"):
        prepared["_paragraph_range"] = prepared["paragraph_range"]
    return prepared


def _scene_script_lines(scene: dict[str, Any]) -> list[dict[str, Any]]:
    script = scene.get("script") or scene.get("script_lines")
    return script if isinstance(script, list) else []


def _script_lines_from_generated(script: Any, nested_script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    if isinstance(script, list):
        lines.extend(line for line in script if isinstance(line, dict))
    lines.extend(nested_script)
    return lines


def _prepare_script_line(
    line: dict[str, Any],
    scene_aliases: dict[str, str],
    character_aliases: dict[str, str],
    single_scene: bool,
) -> dict[str, Any]:
    prepared = dict(line)
    scene_id = str(prepared.get("scene_id") or prepared.get("scene") or "").strip()
    if scene_id in scene_aliases:
        prepared["scene_id"] = scene_aliases[scene_id]
    elif single_scene and scene_aliases:
        prepared["scene_id"] = next(iter(scene_aliases.values()))

    for key in ("character_id", "speaker_id"):
        value = str(prepared.get(key) or "").strip()
        if value in character_aliases:
            prepared[key] = character_aliases[value]

    speaker_name = str(prepared.get("speaker_name") or prepared.get("speaker") or "").strip()
    if speaker_name:
        prepared["speaker_name"] = speaker_name
        if speaker_name in character_aliases and not prepared.get("character_id"):
            prepared["character_id"] = character_aliases[speaker_name]

    if "text" in prepared and not prepared.get("content"):
        prepared["content"] = prepared["text"]
    return prepared


def _item_aliases(items: Any) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if not isinstance(items, list):
        return aliases
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        item_id = str(item["id"])
        aliases[item_id] = item_id
        if item.get("name"):
            aliases[str(item["name"])] = item_id
    return aliases


def _valid_named_item(key: str, name: str, item: dict[str, Any]) -> bool:
    if key == "characters":
        return _valid_character_name(name, item)
    if key == "locations":
        return _valid_location_name(name)
    return True


def _valid_character_name(name: str, item: dict[str, Any]) -> bool:
    blocked_exact = {"待定", "未知", "人物", "关系人物", "功能待细化", "旁白"}
    blocked_terms = (
        "味",
        "气味",
        "味道",
        "纸张",
        "灰尘",
        "小车",
        "推着",
        "混合",
        "这种",
        "清单",
        "铁盒",
        "档案盒",
        "门口",
        "地下室",
        "灯光",
        "镜头",
        "章节",
        "场景",
        "关系",
        "功能",
        "自动",
        "承载",
        "通篇",
        "同一个",
        "重复",
        "从未",
        "听",
        "他们",
        "她们",
        "他想",
        "她想",
        "慢慢",
        "猛地",
        "讨回",
        "他知",
        "她知",
        "交给",
        "转身",
        "穿着",
        "大声",
        "来的",
        "方向",
        "快步",
        "怎么",
    )
    if name in blocked_exact or any(term in name for term in blocked_terms):
        return False
    if name.startswith(("是", "在", "从", "对", "他", "她", "你", "我", "这", "那", "来", "去", "给")):
        return False
    if name.endswith(("的", "了", "着", "想", "知", "要", "喊", "地", "向")):
        return False
    if len(name) > 8 and not any(marker in name for marker in ("女人", "男人", "老人", "孩子", "调查员", "管理员")):
        return False
    role = str(item.get("role") or "").strip()
    description = str(item.get("description") or "").strip()
    return bool(role or description or 1 < len(name) <= 8)


def _valid_location_name(name: str) -> bool:
    blocked_exact = {"未知", "未知地点", "地点", "门口", "屋内", "室内", "外面", "里面", "这里", "那里"}
    blocked_terms = ("人物关系", "情绪", "功能", "自动补充")
    if name in blocked_exact or any(term in name for term in blocked_terms):
        return False
    return len(name) >= 2


def _matching_location_id(name: str, existing: list[Any]) -> str | None:
    for item in existing:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            continue
        existing_name = str(item["name"])
        if name == existing_name or (len(name) <= 2 and name in existing_name):
            return str(item["id"])
    return None


def _next_id(prefix: str, existing_ids: set[str]) -> str:
    index = 1
    while f"{prefix}_{index}" in existing_ids:
        index += 1
    return f"{prefix}_{index}"


def _message_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(str(message.get("content") or "")) for message in messages)


def _mock_chapter_result(chapter_text: str, project_data: ProjectData) -> dict[str, Any]:
    temp = _ensure_project_data(project_data)
    extracted = _mock_extract_entities(chapter_text)
    _merge_named_items(temp, "characters", extracted.get("characters"), "char")
    _merge_named_items(temp, "locations", extracted.get("locations"), "loc")
    temp = _ensure_scene_data(temp)
    return {
        "characters": extracted.get("characters", []),
        "locations": extracted.get("locations", []),
        "scenes": _mock_scenes(chapter_text, temp),
    }
