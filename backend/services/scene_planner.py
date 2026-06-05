from __future__ import annotations

from typing import Any

from backend.services.ai_client import LLMClient
from backend.services.entity_extractor import ProjectData


async def plan_scenes_from_chapter(
    chapter_text: str,
    project_data: ProjectData,
    *,
    client: LLMClient | None = None,
) -> ProjectData:
    data = _ensure_scene_data(project_data)
    llm = client or LLMClient()
    planned = await llm.json(
        _scene_messages(chapter_text, data),
        mock_response={"scenes": _mock_scenes(chapter_text, data)},
    )
    if not isinstance(planned, dict):
        planned = {}

    for scene in planned.get("scenes", []):
        normalized = _normalize_scene(scene, data)
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
            ),
        },
        {
            "role": "user",
            "content": f"项目数据：{project_data}\n\n章节文本：\n{chapter_text}",
        },
    ]


def _ensure_scene_data(project_data: ProjectData) -> ProjectData:
    data = dict(project_data)
    data.setdefault("characters", [])
    data.setdefault("locations", [])
    data.setdefault("scenes", [])
    if not data["locations"]:
        data["locations"].append({"id": "loc_1", "name": "未知地点", "description": "自动补充的默认地点"})
    return data


def _normalize_scene(scene: Any, data: ProjectData) -> dict[str, Any] | None:
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
    for paragraph in paragraphs[:8]:
        scenes.append(
            {
                "title": _make_scene_title(paragraph, len(scenes) + 1),
                "location_id": _find_location_id(paragraph, data),
                "characters": _find_character_ids(paragraph, data),
                "summary": paragraph.replace("\n", " ")[:160],
            }
        )
    return scenes


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
