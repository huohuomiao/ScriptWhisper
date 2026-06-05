from __future__ import annotations

from typing import Any

from backend.schemas.script_yaml import ScriptYAML, ScriptLineType
from backend.services.ai_client import LLMClient
from backend.services.entity_extractor import ProjectData

VALID_LINE_TYPES: set[str] = {"action", "dialogue", "transition", "note"}


async def generate_script_yaml(project_data: ProjectData, *, client: LLMClient | None = None) -> ScriptYAML:
    data = _ensure_script_yaml_base(project_data)
    llm = client or LLMClient()
    generated = await llm.json(
        _script_messages(data),
        mock_response={"script": _mock_script_lines(data)},
    )
    if not isinstance(generated, dict):
        generated = {}

    data["script"] = _normalize_script_lines(generated.get("script", []), data)
    return ScriptYAML.model_validate(data)


def _script_messages(project_data: ProjectData) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是专业影视编剧。请根据场景大纲生成剧本正文，只输出 JSON："
                "{\"script\":[{\"scene_id\":\"\",\"type\":\"action|dialogue|transition|note\","
                "\"character_id\":\"可选\",\"content\":\"\"}]}。"
                "对白必须提供 character_id；镜头提示使用 type=note。"
            ),
        },
        {"role": "user", "content": f"ScriptYAML 项目数据：{project_data}"},
    ]


def _ensure_script_yaml_base(project_data: ProjectData) -> ProjectData:
    data = dict(project_data)
    data.setdefault("project", {"title": "Untitled"})
    data["project"].setdefault("title", "Untitled")
    data.setdefault("characters", [])
    data.setdefault("locations", [])
    data.setdefault("scenes", [])

    if not data["characters"]:
        data["characters"].append({"id": "narrator", "name": "旁白", "role": "narrator"})
    if not data["locations"]:
        data["locations"].append({"id": "loc_1", "name": "未知地点"})
    if not data["scenes"]:
        data["scenes"].append(
            {
                "id": "scene_1",
                "title": "默认场景",
                "location_id": data["locations"][0]["id"],
                "characters": [data["characters"][0]["id"]],
                "summary": "自动补充的默认场景。",
            }
        )

    return data


def _normalize_script_lines(lines: Any, data: ProjectData) -> list[dict[str, Any]]:
    if not isinstance(lines, list):
        lines = []

    scene_ids = {scene["id"] for scene in data["scenes"]}
    character_ids = {character["id"] for character in data["characters"]}
    scene_characters = {scene["id"]: set(scene.get("characters", [])) for scene in data["scenes"]}
    normalized: list[dict[str, Any]] = []

    for line in lines:
        if not isinstance(line, dict):
            continue

        scene_id = str(line.get("scene_id") or "").strip()
        if scene_id not in scene_ids:
            continue

        line_type = _normalize_line_type(line.get("type"))
        content = str(line.get("content") or "").strip()
        if not content:
            continue

        entry: dict[str, Any] = {
            "scene_id": scene_id,
            "type": line_type,
            "content": content,
        }

        character_id = line.get("character_id")
        if line_type == "dialogue":
            character_id = _valid_dialogue_character(character_id, scene_id, character_ids, scene_characters)
            if not character_id:
                entry["type"] = "action"
            else:
                entry["character_id"] = character_id
        elif character_id and character_id in character_ids:
            entry["character_id"] = character_id

        normalized.append(entry)

    _ensure_each_scene_has_script(normalized, data)
    return normalized


def _normalize_line_type(value: Any) -> ScriptLineType:
    line_type = str(value or "action").strip().lower()
    if line_type in {"camera", "shot", "镜头", "镜头提示"}:
        return "note"
    if line_type not in VALID_LINE_TYPES:
        return "action"
    return line_type  # type: ignore[return-value]


def _valid_dialogue_character(
    value: Any,
    scene_id: str,
    character_ids: set[str],
    scene_characters: dict[str, set[str]],
) -> str | None:
    character_id = str(value or "").strip()
    if character_id in character_ids and character_id in scene_characters.get(scene_id, set()):
        return character_id
    return None


def _ensure_each_scene_has_script(lines: list[dict[str, Any]], data: ProjectData) -> None:
    scenes_with_lines = {line["scene_id"] for line in lines}
    for scene in data["scenes"]:
        if scene["id"] not in scenes_with_lines:
            lines.append(
                {
                    "scene_id": scene["id"],
                    "type": "action",
                    "content": scene.get("summary") or f"{scene['title']}展开。",
                }
            )


def _mock_script_lines(data: ProjectData) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for scene in data["scenes"]:
        scene_id = scene["id"]
        title = scene["title"]
        summary = scene.get("summary") or f"{title}展开。"
        lines.append({"scene_id": scene_id, "type": "action", "content": summary})

        first_character = next(iter(scene.get("characters", [])), None)
        if first_character:
            lines.append(
                {
                    "scene_id": scene_id,
                    "type": "dialogue",
                    "character_id": first_character,
                    "content": "这一刻，我们必须把故事继续讲下去。",
                }
            )

        lines.append({"scene_id": scene_id, "type": "note", "content": f"镜头提示：镜头缓慢推进，突出{title}的情绪。"})
        lines.append({"scene_id": scene_id, "type": "transition", "content": "切至下一场。"})

    return lines
