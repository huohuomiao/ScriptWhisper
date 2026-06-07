from __future__ import annotations

from typing import Any, Mapping

from backend.services.ai_client import LLMClient
from backend.services.entity_extractor import ProjectData


async def plan_scenes_from_chapter(
    chapter_text: str,
    project_data: ProjectData,
    *,
    chapter_meta: Mapping[str, Any] | None = None,
    client: LLMClient | None = None,
) -> ProjectData:
    data = _ensure_scene_data(project_data)
    llm = client or LLMClient()
    source = _normalize_chapter_meta(chapter_meta, chapter_text)
    planned = await llm.json(
        _scene_messages(chapter_text, data),
        mock_response={"scenes": _mock_scenes(chapter_text, data)},
    )
    if not isinstance(planned, dict):
        planned = {}

    for scene in planned.get("scenes", []):
        normalized = _normalize_scene(scene, data, source, chapter_text)
        if normalized:
            data["scenes"].append(normalized)

    return data


def _scene_messages(chapter_text: str, project_data: ProjectData) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是剧本策划。请把章节拆成场景大纲，只输出 JSON："
                "{\"scenes\":[{\"title\":\"\",\"location_id\":\"\",\"characters\":[],\"summary\":\"\"}]}。"
                "location_id 必须来自项目地点；characters 必须来自项目人物 ID。"
                "Do not output source_ref, chapter_id or chapter_index; the backend will attach chapter source data."
                + _target_language_instruction(project_data)
            ),
        },
        {
            "role": "user",
            "content": f"项目数据：{project_data}\n\n章节文本：\n{chapter_text}",
        },
    ]


def _target_language_instruction(project_data: ProjectData) -> str:
    language = str(project_data.get("project", {}).get("target_language") or "zh")
    return (
        "请使用所选目标语言输出人物描述、地点描述、场景摘要、剧情节拍、动作、对白、镜头和导出文本。"
        f"当前 target_language={language}。"
    )


def _ensure_scene_data(project_data: ProjectData) -> ProjectData:
    data = dict(project_data)
    data.setdefault("characters", [])
    data.setdefault("locations", [])
    data.setdefault("scenes", [])
    if not data["locations"]:
        data["locations"].append({"id": "loc_1", "name": "未知地点", "description": "自动补充的默认地点"})
    return data


def _normalize_scene(
    scene: Any,
    data: ProjectData,
    chapter_meta: dict[str, Any],
    chapter_text: str,
) -> dict[str, Any] | None:
    if not isinstance(scene, dict):
        return None

    title = str(scene.get("title") or f"场景 {len(data['scenes']) + 1}").strip()
    summary = str(scene.get("summary") or "").strip()
    location_id = _resolve_location_id(scene, data)
    characters = _resolve_character_ids(scene.get("characters", []), data)
    scene_id = str(scene.get("id") or _next_scene_id(data)).strip()
    existing_ids = {item.get("id") for item in data.get("scenes", []) if isinstance(item, dict)}
    if scene_id in existing_ids:
        scene_id = _next_scene_id(data)

    return {
        "id": scene_id,
        "title": title,
        "location_id": location_id,
        "characters": characters,
        "summary": summary,
        "source_ref": _build_source_ref(chapter_meta, scene, chapter_text, summary),
    }


def _resolve_location_id(scene: dict[str, Any], data: ProjectData) -> str:
    locations = data.get("locations", [])
    location_ids = {item.get("id") for item in locations if isinstance(item, dict)}
    requested_id = scene.get("location_id")
    if requested_id in location_ids:
        return str(requested_id)

    requested_name = str(scene.get("location_name") or "").strip()
    for item in locations:
        if isinstance(item, dict) and requested_name and item.get("name") == requested_name:
            return str(item["id"])

    return str(locations[0]["id"])


def _resolve_character_ids(characters: Any, data: ProjectData) -> list[str]:
    if not isinstance(characters, list):
        return []

    known_by_id = {item.get("id"): item for item in data.get("characters", []) if isinstance(item, dict)}
    known_by_name = {item.get("name"): item.get("id") for item in data.get("characters", []) if isinstance(item, dict)}
    resolved: list[str] = []
    for value in characters:
        if value in known_by_id and value not in resolved:
            resolved.append(str(value))
            continue
        if value in known_by_name and known_by_name[value] not in resolved:
            resolved.append(str(known_by_name[value]))
    return resolved


def _next_scene_id(data: ProjectData) -> str:
    existing = {scene.get("id") for scene in data.get("scenes", []) if isinstance(scene, dict)}
    index = len(existing) + 1
    while f"scene_{index}" in existing:
        index += 1
    return f"scene_{index}"


def _mock_scenes(chapter_text: str, data: ProjectData) -> list[dict[str, Any]]:
    paragraphs = [part.strip() for part in chapter_text.split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [chapter_text.strip()]

    scenes: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(paragraphs[:8], start=1):
        scenes.append(
            {
                "title": _make_scene_title(paragraph, len(scenes) + 1),
                "location_id": _find_location_id(paragraph, data),
                "characters": _find_character_ids(paragraph, data),
                "summary": paragraph.replace("\n", " ")[:160],
                "_source_excerpt": paragraph.replace("\n", " ")[:240],
                "_paragraph_range": [paragraph_index, paragraph_index],
            }
        )
    return scenes


def _normalize_chapter_meta(chapter_meta: Mapping[str, Any] | None, chapter_text: str) -> dict[str, Any]:
    source = dict(chapter_meta or {})
    chapter_index = _positive_int(source.get("chapter_index") or source.get("index"), 1)
    chapter_id = str(source.get("chapter_id") or source.get("id") or f"chapter_{chapter_index}").strip()
    chapter_title = str(source.get("chapter_title") or source.get("title") or source.get("heading") or chapter_id).strip()
    content = str(source.get("content") or chapter_text or "").strip()
    return {
        "chapter_id": chapter_id or f"chapter_{chapter_index}",
        "chapter_index": chapter_index,
        "chapter_title": chapter_title or f"Chapter {chapter_index}",
        "content": content,
    }


def _build_source_ref(
    chapter_meta: dict[str, Any],
    scene: dict[str, Any],
    chapter_text: str,
    summary: str,
) -> dict[str, Any]:
    excerpt = str(scene.get("_source_excerpt") or "").strip()
    if not excerpt:
        excerpt = _best_excerpt(str(chapter_meta.get("content") or chapter_text), summary)

    source_ref: dict[str, Any] = {
        "chapter_id": chapter_meta["chapter_id"],
        "chapter_index": chapter_meta["chapter_index"],
        "chapter_title": chapter_meta["chapter_title"],
        "excerpt": excerpt,
    }

    paragraph_range = scene.get("_paragraph_range")
    if _valid_paragraph_range(paragraph_range):
        source_ref["paragraph_range"] = paragraph_range
    return source_ref


def _best_excerpt(chapter_text: str, summary: str) -> str:
    paragraphs = [part.strip().replace("\n", " ") for part in chapter_text.split("\n\n") if part.strip()]
    if not paragraphs:
        return chapter_text.strip().replace("\n", " ")[:240]

    summary_tokens = _tokens(summary)
    if not summary_tokens:
        return paragraphs[0][:240]

    best = max(paragraphs, key=lambda paragraph: len(summary_tokens & _tokens(paragraph)))
    return best[:240]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in str(text).replace("。", " ").replace(".", " ").split() if token.strip()}


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _valid_paragraph_range(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    start, end = value
    return isinstance(start, int) and isinstance(end, int) and start >= 1 and end >= start


def _make_scene_title(text: str, index: int) -> str:
    sentence = text.replace("\n", " ").split("。", 1)[0].strip()
    if not sentence:
        return f"场景 {index}"
    return sentence[:24]


def _find_location_id(text: str, data: ProjectData) -> str:
    for location in data.get("locations", []):
        if isinstance(location, dict) and location.get("name") and str(location["name"]) in text:
            return str(location["id"])
    return str(data["locations"][0]["id"])


def _find_character_ids(text: str, data: ProjectData) -> list[str]:
    ids: list[str] = []
    for character in data.get("characters", []):
        if isinstance(character, dict) and character.get("name") and str(character["name"]) in text:
            ids.append(str(character["id"]))
    return ids
