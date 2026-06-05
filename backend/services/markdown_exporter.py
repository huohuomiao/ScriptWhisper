from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.schemas.script_yaml import ScriptYAML
from backend.services.script_yaml_validator import repair_scene_source_refs

HIGHLIGHT_LABELS = {
    "#fff3a3": "黄色标记",
    "#cfe8ff": "蓝色标记",
    "#d8f5d2": "绿色标记",
    "#ffd8d2": "红色标记",
    "yellow": "黄色标记",
    "blue": "蓝色标记",
    "green": "绿色标记",
    "red": "红色标记",
}

TYPE_LABELS = {
    "action": "动作",
    "camera": "镜头",
    "dialogue": "对白",
    "narration": "旁白",
    "note": "备注",
    "transition": "转场",
}


def to_markdown(script_yaml: ScriptYAML | Mapping[str, Any], *, chapters: Any = None) -> str:
    data = _validated_data(script_yaml, chapters=chapters)
    chapter_refs = _chapter_refs(chapters, data)
    character_by_id = {character["id"]: character for character in data.get("characters", [])}
    location_by_id = {location["id"]: location for location in data.get("locations", [])}
    scene_by_chapter = _group_scenes(data.get("scenes", []), chapter_refs)

    lines = [f"# {data.get('project', {}).get('title') or '未指定'}", ""]
    logline = data.get("project", {}).get("logline")
    if logline:
        lines.extend([f"> {logline}", ""])

    all_scenes = data.get("scenes", [])
    for chapter in chapter_refs:
        chapter_scenes = scene_by_chapter.get(chapter["chapter_id"], [])
        lines.extend([f"## {chapter['chapter_title']}", ""])
        if not chapter_scenes:
            lines.extend(["当前章节还没有生成场景。", ""])
            continue

        for scene in chapter_scenes:
            scene_number = all_scenes.index(scene) + 1 if scene in all_scenes else 1
            location = location_by_id.get(scene.get("location_id"), {})
            characters = [
                character_by_id.get(character_id, {}).get("name", character_id)
                for character_id in scene.get("characters", [])
            ]
            lines.extend([f"### S{scene_number} {scene.get('title') or '未命名场景'}", ""])
            if scene.get("summary"):
                lines.extend([scene["summary"], ""])
            lines.append(f"- 来源章节：{scene.get('source_ref', {}).get('chapter_title') or chapter['chapter_title']}")
            if scene.get("source_ref", {}).get("excerpt"):
                lines.append(f"- 原文依据：{scene['source_ref']['excerpt']}")
            if location:
                lines.append(f"- 地点：{location.get('name') or scene.get('location_id')}")
            if characters:
                lines.append(f"- 人物：{' / '.join(characters)}")
            lines.append("")

            for script_line in data.get("script", []):
                if script_line.get("scene_id") == scene.get("id"):
                    lines.extend(_script_line_markdown(script_line, character_by_id))
                    lines.append("")

    return "\n".join(lines).strip() + "\n"


def _validated_data(value: ScriptYAML | Mapping[str, Any], *, chapters: Any = None) -> dict[str, Any]:
    model = value if isinstance(value, ScriptYAML) else ScriptYAML.model_validate(value)
    if chapters:
        repaired_data, _issues = repair_scene_source_refs(model, chapters)
        model = ScriptYAML.model_validate(repaired_data)
    return model.model_dump(mode="json", exclude_none=True)


def _chapter_refs(chapters: Any, data: dict[str, Any]) -> list[dict[str, Any]]:
    if chapters:
        refs = []
        for index, chapter in enumerate(chapters, start=1):
            raw = chapter.model_dump(mode="json") if hasattr(chapter, "model_dump") else dict(chapter)
            chapter_index = raw.get("chapter_index") or index
            refs.append(
                {
                    "chapter_id": raw.get("chapter_id") or raw.get("id") or f"chapter_{chapter_index}",
                    "chapter_index": chapter_index,
                    "chapter_title": raw.get("chapter_title") or raw.get("title") or f"第 {chapter_index} 章",
                }
            )
        return refs

    refs_by_id = {}
    for scene in data.get("scenes", []):
        source = scene.get("source_ref") or {}
        chapter_id = source.get("chapter_id")
        if chapter_id and chapter_id not in refs_by_id:
            refs_by_id[chapter_id] = {
                "chapter_id": chapter_id,
                "chapter_index": source.get("chapter_index") or len(refs_by_id) + 1,
                "chapter_title": source.get("chapter_title") or f"第 {len(refs_by_id) + 1} 章",
            }
    return sorted(refs_by_id.values(), key=lambda item: item["chapter_index"]) or [
        {"chapter_id": "chapter_1", "chapter_index": 1, "chapter_title": "第 1 章"}
    ]


def _group_scenes(scenes: list[dict[str, Any]], chapters: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {chapter["chapter_id"]: [] for chapter in chapters}
    fallback = chapters[0]["chapter_id"]
    for scene in scenes:
        chapter_id = scene.get("source_ref", {}).get("chapter_id") or fallback
        groups.setdefault(chapter_id, []).append(scene)
    return groups


def _script_line_markdown(line: dict[str, Any], character_by_id: dict[str, dict[str, Any]]) -> list[str]:
    content = line.get("text") or line.get("content") or ""
    if not content:
        return []

    marker = _highlight_label(line.get("highlight_color"))
    prefix = f"【{marker}】" if marker else ""
    if line.get("type") == "dialogue":
        speaker_id = line.get("character_id") or line.get("speaker_id")
        speaker = line.get("speaker_name") or character_by_id.get(speaker_id, {}).get("name") or speaker_id or "未指定"
        emotion = f"（{line['emotion']}）" if line.get("emotion") else ""
        output = [f"**{speaker}**{emotion}：{prefix}{content}"]
    else:
        label = TYPE_LABELS.get(line.get("type"), line.get("type") or "动作")
        output = [f"_{label}_：{prefix}{content}"]

    if line.get("note"):
        output.append(f"> 备注：{line['note']}")
    return output


def _highlight_label(value: Any) -> str | None:
    if not value:
        return None
    return HIGHLIGHT_LABELS.get(str(value).strip().lower(), f"{value}标记")
