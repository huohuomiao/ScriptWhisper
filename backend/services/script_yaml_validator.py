from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any

from pydantic import ValidationError

from backend.schemas.script_yaml import ScriptYAML

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
LINE_TYPES = {"action", "dialogue", "transition", "note", "camera", "narration"}


@dataclass(frozen=True)
class ValidationResult:
    data: ScriptYAML
    repaired: bool
    issues: list[str]


def validate_script_yaml(data: ScriptYAML | dict[str, Any]) -> ScriptYAML:
    return data if isinstance(data, ScriptYAML) else ScriptYAML.model_validate(data)


def validate_or_repair_script_yaml(
    data: ScriptYAML | dict[str, Any],
    *,
    auto_repair: bool = True,
    chapters: Any = None,
) -> ValidationResult:
    try:
        validated = validate_script_yaml(data)
        if chapters:
            repaired_data, source_issues = repair_scene_source_refs(validated, chapters)
            if source_issues:
                return ValidationResult(
                    data=ScriptYAML.model_validate(repaired_data),
                    repaired=True,
                    issues=source_issues,
                )
        return ValidationResult(data=validated, repaired=False, issues=[])
    except ValidationError as exc:
        if not auto_repair:
            raise
        repaired_data, issues = repair_script_yaml_data(data, chapters=chapters)
        repaired_model = ScriptYAML.model_validate(repaired_data)
        return ValidationResult(data=repaired_model, repaired=True, issues=issues or _validation_issues(exc))


def repair_script_yaml(data: ScriptYAML | dict[str, Any], *, chapters: Any = None) -> ScriptYAML:
    repaired_data, _issues = repair_script_yaml_data(data, chapters=chapters)
    return ScriptYAML.model_validate(repaired_data)


def repair_script_yaml_data(
    data: ScriptYAML | dict[str, Any],
    *,
    chapters: Any = None,
) -> tuple[dict[str, Any], list[str]]:
    raw = data.model_dump(mode="json") if isinstance(data, ScriptYAML) else deepcopy(data)
    if not isinstance(raw, dict):
        raw = {}

    issues: list[str] = []
    chapter_refs = _chapter_refs(chapters)
    repaired: dict[str, Any] = {
        "project": _repair_project(raw.get("project"), issues),
        "characters": [],
        "locations": [],
        "scenes": [],
        "script": [],
    }

    character_id_map, repaired["characters"] = _repair_named_items(
        raw.get("characters"), "char", {"id", "name", "role", "description"}, issues
    )
    location_id_map, repaired["locations"] = _repair_named_items(
        raw.get("locations"), "loc", {"id", "name", "description"}, issues
    )
    scene_id_map, repaired["scenes"] = _repair_scenes(
        raw.get("scenes"),
        repaired["locations"],
        character_id_map,
        issues,
        chapter_refs,
    )
    repaired["script"] = _repair_script_lines(
        raw.get("script"),
        repaired["scenes"],
        repaired["characters"],
        scene_id_map,
        character_id_map,
        issues,
    )

    _ensure_scene_script_lines(repaired, issues)
    return repaired, issues


def repair_scene_source_refs(data: ScriptYAML | dict[str, Any], chapters: Any) -> tuple[dict[str, Any], list[str]]:
    raw = data.model_dump(mode="json") if isinstance(data, ScriptYAML) else deepcopy(data)
    if not isinstance(raw, dict):
        raw = {}

    chapter_refs = _chapter_refs(chapters)
    issues: list[str] = []
    scenes = raw.get("scenes") if isinstance(raw.get("scenes"), list) else []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        repaired_source = _repair_source_ref(scene.get("source_ref"), index, chapter_refs, issues)
        if scene.get("source_ref") != repaired_source:
            scene["source_ref"] = repaired_source
    return raw, issues


def _repair_project(value: Any, issues: list[str]) -> dict[str, Any]:
    project = value if isinstance(value, dict) else {}
    if not project:
        issues.append("missing project object; created default project")

    title = str(project.get("title") or "Untitled").strip() or "Untitled"
    repaired = {"title": title, "version": str(project.get("version") or "1.0")}
    for key in ("genre", "logline", "source"):
        if project.get(key):
            repaired[key] = str(project[key])
    repaired["source_language"] = str(project.get("source_language") or "zh")
    repaired["target_language"] = _normalize_target_language(project.get("target_language"))
    return repaired


def _normalize_target_language(value: Any) -> str:
    language = str(value or "zh").strip().lower()
    return language if language in {"zh", "en", "fr", "ja", "ru"} else "zh"


def _repair_named_items(
    value: Any,
    prefix: str,
    allowed_keys: set[str],
    issues: list[str],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    items = value if isinstance(value, list) else []
    if not items:
        default = {"id": f"{prefix}_1", "name": "未命名"}
        issues.append(f"missing {prefix} list; created default item")
        return {"": default["id"]}, [default]

    used_ids: set[str] = set()
    id_map: dict[str, str] = {}
    repaired: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            issues.append(f"ignored invalid {prefix} item at index {index}")
            continue

        old_id = str(item.get("id") or "").strip()
        new_id = _safe_unique_id(old_id, prefix, index, used_ids)
        if old_id != new_id:
            issues.append(f"repaired {prefix} id '{old_id or '<missing>'}' to '{new_id}'")
        id_map[old_id] = new_id

        name = str(item.get("name") or old_id or new_id).strip() or new_id
        entry = {key: item[key] for key in allowed_keys if key in item and item[key] is not None}
        entry["id"] = new_id
        entry["name"] = name
        repaired.append(entry)

    if not repaired:
        default = {"id": f"{prefix}_1", "name": "未命名"}
        issues.append(f"all {prefix} items invalid; created default item")
        return {"": default["id"]}, [default]

    return id_map, repaired


def _repair_scenes(
    value: Any,
    locations: list[dict[str, Any]],
    character_id_map: dict[str, str],
    issues: list[str],
    chapter_refs: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    items = value if isinstance(value, list) else []
    if not items:
        issues.append("missing scenes; created default scene")
        return {"": "scene_1"}, [
            {
                "id": "scene_1",
                "title": "默认场景",
                "location_id": locations[0]["id"],
                "characters": list({value for value in character_id_map.values() if value}),
                "summary": "自动补全的默认场景。",
                "source_ref": _repair_source_ref(None, 1, chapter_refs, issues),
            }
        ]

    used_ids: set[str] = set()
    location_ids = {location["id"] for location in locations}
    valid_character_ids = set(character_id_map.values())
    scene_id_map: dict[str, str] = {}
    repaired: list[dict[str, Any]] = []
    for index, scene in enumerate(items, start=1):
        if not isinstance(scene, dict):
            issues.append(f"ignored invalid scene at index {index}")
            continue

        old_id = str(scene.get("id") or "").strip()
        new_id = _safe_unique_id(old_id, "scene", index, used_ids)
        if old_id != new_id:
            issues.append(f"repaired scene id '{old_id or '<missing>'}' to '{new_id}'")
        scene_id_map[old_id] = new_id

        location_id = str(scene.get("location_id") or "").strip()
        location_id = location_id if location_id in location_ids else locations[0]["id"]
        characters = _repair_reference_list(scene.get("characters"), character_id_map, valid_character_ids)
        repaired.append(
            {
                "id": new_id,
                "title": str(scene.get("title") or f"场景 {index}").strip(),
                "location_id": location_id,
                "characters": characters,
                "summary": str(scene.get("summary") or "").strip() or None,
                "source_ref": _repair_source_ref(scene.get("source_ref"), index, chapter_refs, issues),
            }
        )

    return scene_id_map, repaired


def _repair_script_lines(
    value: Any,
    scenes: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    scene_id_map: dict[str, str],
    character_id_map: dict[str, str],
    issues: list[str],
) -> list[dict[str, Any]]:
    lines = value if isinstance(value, list) else []
    scene_ids = {scene["id"] for scene in scenes}
    character_ids = {character["id"] for character in characters}
    scene_characters = {scene["id"]: set(scene.get("characters", [])) for scene in scenes}
    first_scene_id = scenes[0]["id"]
    first_character_id = characters[0]["id"]
    repaired: list[dict[str, Any]] = []

    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            issues.append(f"ignored invalid script line at index {index}")
            continue

        scene_id = scene_id_map.get(str(line.get("scene_id") or "").strip(), str(line.get("scene_id") or "").strip())
        if scene_id not in scene_ids:
            issues.append(f"repaired script line scene_id at index {index} to '{first_scene_id}'")
            scene_id = first_scene_id

        line_type = _repair_line_type(line.get("type"))
        content = str(line.get("content") or line.get("text") or "").strip() or "待补全文本。"
        entry: dict[str, Any] = {"scene_id": scene_id, "type": line_type, "content": content}
        for key in ("id", "text", "emotion", "highlight_color", "note", "speaker_name"):
            if line.get(key):
                entry[key] = str(line[key])

        character_id = character_id_map.get(
            str(line.get("character_id") or "").strip(),
            str(line.get("character_id") or "").strip(),
        )
        speaker_id = character_id_map.get(
            str(line.get("speaker_id") or "").strip(),
            str(line.get("speaker_id") or "").strip(),
        )
        if line_type == "dialogue":
            if character_id not in character_ids and speaker_id in character_ids:
                character_id = speaker_id
            if character_id not in character_ids and not entry.get("speaker_name"):
                character_id = first_character_id
                issues.append(f"repaired dialogue character_id at index {index} to '{character_id}'")
            if character_id in character_ids and character_id not in scene_characters[scene_id]:
                scene_characters[scene_id].add(character_id)
                _add_character_to_scene(scenes, scene_id, character_id)
                issues.append(f"added character '{character_id}' to scene '{scene_id}'")
            if character_id in character_ids:
                entry["character_id"] = character_id
                entry["speaker_id"] = character_id
        elif character_id in character_ids:
            entry["character_id"] = character_id

        repaired.append(entry)

    return repaired


def _repair_reference_list(value: Any, id_map: dict[str, str], valid_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        repaired = id_map.get(str(item), str(item))
        if repaired in valid_ids and repaired not in result:
            result.append(repaired)
    return result


def _chapter_refs(chapters: Any) -> list[dict[str, Any]]:
    if chapters is None:
        return [_default_chapter_ref(1)]

    if isinstance(chapters, dict) and isinstance(chapters.get("chapters"), list):
        items = chapters["chapters"]
    elif isinstance(chapters, list):
        items = chapters
    else:
        items = list(chapters) if hasattr(chapters, "__iter__") and not isinstance(chapters, (str, bytes)) else []

    refs: list[dict[str, Any]] = []
    for fallback_index, item in enumerate(items, start=1):
        raw = _object_to_dict(item)
        chapter_index = _positive_int(raw.get("chapter_index") or raw.get("index"), fallback_index)
        chapter_id = str(raw.get("chapter_id") or raw.get("id") or f"chapter_{chapter_index}").strip()
        chapter_title = str(raw.get("chapter_title") or raw.get("title") or raw.get("heading") or chapter_id).strip()
        content = str(raw.get("content") or "").strip()
        refs.append(
            {
                "chapter_id": chapter_id or f"chapter_{chapter_index}",
                "chapter_index": chapter_index,
                "chapter_title": chapter_title or f"Chapter {chapter_index}",
                "excerpt": _chapter_excerpt(content),
            }
        )

    if not refs:
        return [_default_chapter_ref(1)]
    return sorted(refs, key=lambda ref: ref["chapter_index"])


def _repair_source_ref(
    value: Any,
    scene_position: int,
    chapter_refs: list[dict[str, Any]],
    issues: list[str],
) -> dict[str, Any]:
    refs = chapter_refs or [_default_chapter_ref(1)]
    source = value if isinstance(value, dict) else {}
    if not source:
        issues.append(f"added missing source_ref for scene at index {scene_position}")

    by_id = {ref["chapter_id"]: ref for ref in refs}
    raw_index = _int_or_none(source.get("chapter_index"))
    requested_id = str(source.get("chapter_id") or "").strip()

    if raw_index is not None:
        chapter_index = _clamp(raw_index, 1, len(refs))
        target = refs[chapter_index - 1]
        if raw_index != chapter_index:
            issues.append(
                f"repaired source_ref.chapter_index {raw_index} to {chapter_index} for scene at index {scene_position}"
            )
        if requested_id and requested_id in by_id and by_id[requested_id]["chapter_index"] != chapter_index:
            issues.append(
                f"repaired mismatched source_ref chapter_id '{requested_id}' to '{target['chapter_id']}'"
            )
        elif requested_id and requested_id not in by_id:
            issues.append(f"repaired unknown source_ref chapter_id '{requested_id}' to '{target['chapter_id']}'")
    elif requested_id in by_id:
        target = by_id[requested_id]
    else:
        chapter_index = _clamp(scene_position, 1, len(refs))
        target = refs[chapter_index - 1]
        if requested_id:
            issues.append(f"repaired unknown source_ref chapter_id '{requested_id}' to '{target['chapter_id']}'")
        elif source:
            issues.append(f"repaired missing source_ref.chapter_id to '{target['chapter_id']}'")

    excerpt = _first_text(source.get("excerpt"), source.get("evidence"), source.get("text"), target.get("excerpt"))
    repaired = {
        "chapter_id": target["chapter_id"],
        "chapter_index": target["chapter_index"],
        "chapter_title": target["chapter_title"],
    }
    if excerpt:
        repaired["excerpt"] = excerpt

    paragraph_range = source.get("paragraph_range")
    if _valid_paragraph_range(paragraph_range):
        repaired["paragraph_range"] = paragraph_range
    elif paragraph_range is not None:
        issues.append(f"removed invalid source_ref.paragraph_range for scene at index {scene_position}")

    return repaired


def _object_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {
        "id": getattr(value, "id", None),
        "chapter_id": getattr(value, "chapter_id", None),
        "chapter_index": getattr(value, "chapter_index", None),
        "index": getattr(value, "index", None),
        "title": getattr(value, "title", None),
        "heading": getattr(value, "heading", None),
        "content": getattr(value, "content", None),
    }


def _default_chapter_ref(index: int) -> dict[str, Any]:
    return {
        "chapter_id": f"chapter_{index}",
        "chapter_index": index,
        "chapter_title": f"Chapter {index}",
        "excerpt": None,
    }


def _chapter_excerpt(content: str) -> str | None:
    text = content.replace("\n", " ").strip()
    return text[:240] or None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _positive_int(value: Any, default: int) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed and parsed > 0 else default


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: int, lower: int, upper: int) -> int:
    return min(max(value, lower), upper)


def _valid_paragraph_range(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    start, end = value
    return isinstance(start, int) and isinstance(end, int) and start >= 1 and end >= start


def _repair_line_type(value: Any) -> str:
    line_type = str(value or "action").strip().lower()
    if line_type in {"shot", "镜头", "镜头提示"}:
        return "camera"
    return line_type if line_type in LINE_TYPES else "action"


def _ensure_scene_script_lines(data: dict[str, Any], issues: list[str]) -> None:
    scenes_with_lines = {line["scene_id"] for line in data["script"]}
    for scene in data["scenes"]:
        if scene["id"] not in scenes_with_lines:
            data["script"].append(
                {
                    "scene_id": scene["id"],
                    "type": "action",
                    "content": scene.get("summary") or f"{scene['title']}展开。",
                }
            )
            issues.append(f"added missing script line for scene '{scene['id']}'")


def _add_character_to_scene(scenes: list[dict[str, Any]], scene_id: str, character_id: str) -> None:
    for scene in scenes:
        if scene["id"] == scene_id and character_id not in scene["characters"]:
            scene["characters"].append(character_id)
            return


def _safe_unique_id(raw_id: str, prefix: str, index: int, used_ids: set[str]) -> str:
    candidate = raw_id if ID_RE.fullmatch(raw_id) else f"{prefix}_{index}"
    while candidate in used_ids:
        index += 1
        candidate = f"{prefix}_{index}"
    used_ids.add(candidate)
    return candidate


def _validation_issues(exc: ValidationError) -> list[str]:
    return [error["msg"] for error in exc.errors()]
