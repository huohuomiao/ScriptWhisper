from __future__ import annotations

import re
from typing import Any

from backend.services.ai_client import LLMClient

ProjectData = dict[str, Any]


async def extract_entities_from_chapter(
    chapter_text: str,
    project_data: ProjectData | None = None,
    *,
    client: LLMClient | None = None,
) -> ProjectData:
    data = _ensure_project_data(project_data)
    llm = client or LLMClient()
    extracted = await llm.json(
        _entity_messages(chapter_text, data),
        mock_response=_mock_extract_entities(chapter_text),
    )
    if not isinstance(extracted, dict):
        extracted = {}

    _merge_named_items(data, "characters", extracted.get("characters", []), "char")
    _merge_named_items(data, "locations", extracted.get("locations", []), "loc")
    return data


def _entity_messages(chapter_text: str, project_data: ProjectData) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是剧本开发助理。请从章节文本中抽取角色表和地点表，"
                "只输出 JSON，格式为 {\"characters\": [], \"locations\": []}。"
                "角色字段包含 name, role, description；地点字段包含 name, description。"
                + _target_language_instruction(project_data)
            ),
        },
        {"role": "user", "content": chapter_text},
    ]


def _target_language_instruction(project_data: ProjectData) -> str:
    language = str(project_data.get("project", {}).get("target_language") or "zh")
    return (
        "请使用所选目标语言输出人物描述、地点描述、场景摘要、剧情节拍、动作、对白、镜头和导出文本。"
        f"当前 target_language={language}。"
    )


def _ensure_project_data(project_data: ProjectData | None) -> ProjectData:
    data = dict(project_data or {})
    data.setdefault("project", {"title": "Untitled"})
    data.setdefault("characters", [])
    data.setdefault("locations", [])
    return data


def _merge_named_items(data: ProjectData, key: str, items: Any, id_prefix: str) -> None:
    if not isinstance(items, list):
        return

    existing = data.setdefault(key, [])
    names = {item.get("name") for item in existing if isinstance(item, dict)}
    ids = {item.get("id") for item in existing if isinstance(item, dict)}

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name or name in names:
            continue

        entry = {k: v for k, v in item.items() if k in {"id", "name", "role", "description"} and v}
        entry["name"] = name
        entry["id"] = _next_id(id_prefix, ids) if not entry.get("id") else str(entry["id"])
        existing.append(entry)
        names.add(name)
        ids.add(entry["id"])


def _next_id(prefix: str, existing_ids: set[str]) -> str:
    index = 1
    while f"{prefix}_{index}" in existing_ids:
        index += 1
    return f"{prefix}_{index}"


def _mock_extract_entities(chapter_text: str) -> dict[str, list[dict[str, str]]]:
    return {
        "characters": _mock_characters(chapter_text),
        "locations": _mock_locations(chapter_text),
    }


def _mock_characters(text: str) -> list[dict[str, str]]:
    names: list[str] = []
    for match in re.finditer(r"([\u4e00-\u9fa5]{2,4})(?:说|问|道|望|握|走|站|递)", text):
        name = match.group(1)
        if name not in names and not _looks_like_common_phrase(name):
            names.append(name)

    if not names:
        for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text):
            name = match.group(1)
            if name.lower() not in {"chapter", "the"} and name not in names:
                names.append(name)

    return [
        {
            "name": name,
            "role": "待定",
            "description": f"从章节文本中识别到的人物：{name}",
        }
        for name in names[:8]
    ]


def _mock_locations(text: str) -> list[dict[str, str]]:
    patterns = [
        r"(?:在|到|向|从|来到|走向)([\u4e00-\u9fa5]{0,8}?(?:影院门口|影院|门口|长街尽头|长街|巷子|房间|放映室|街道|车站|大厅|屋内|屋外))",
        r"\b([A-Z][A-Za-z\s]{1,30}(?:Station|Cinema|Room|Street|Hall))\b",
    ]
    locations: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1).strip()
            if name and name not in locations:
                locations.append(name)

    return [
        {
            "name": name,
            "description": f"从章节文本中识别到的地点：{name}",
        }
        for name in locations[:8]
    ]


def _looks_like_common_phrase(value: str) -> bool:
    blocked = {"终于", "没有", "如果", "今晚", "镜头", "雨停后", "旧影院"}
    location_terms = ("影院", "门口", "长街", "巷子", "房间", "放映室", "车站", "大厅")
    return value in blocked or value.endswith(("后的", "里的", "上的")) or any(term in value for term in location_terms)
