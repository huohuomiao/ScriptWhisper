from collections.abc import Mapping
from pathlib import Path
import json
import re
from typing import Any

from pydantic import BaseModel

from backend.schemas.script_yaml import ScriptYAML
from backend.services.script_yaml_validator import repair_scene_source_refs

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "examples" / "sample_output.yaml"


def export_script_yaml(
    script_yaml: ScriptYAML | Mapping[str, Any],
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    *,
    chapters: Any = None,
) -> Path:
    data = _validated_data(script_yaml, chapters=chapters)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(to_yaml(data) + "\n", encoding="utf-8")
    return destination


def to_yaml(value: ScriptYAML | Mapping[str, Any], *, chapters: Any = None) -> str:
    data = _validated_data(value, chapters=chapters)
    return "\n".join(_dump_value(data, indent=0))


def _validated_data(value: ScriptYAML | Mapping[str, Any], *, chapters: Any = None) -> dict[str, Any]:
    if isinstance(value, ScriptYAML):
        model = value
    else:
        model = ScriptYAML.model_validate(value)
    if chapters:
        repaired_data, _issues = repair_scene_source_refs(model, chapters)
        model = ScriptYAML.model_validate(repaired_data)
    return model.model_dump(mode="json", exclude_none=True)


def _dump_value(value: Any, indent: int) -> list[str]:
    if isinstance(value, Mapping):
        return _dump_mapping(value, indent)
    if isinstance(value, list):
        return _dump_list(value, indent)
    return [" " * indent + _format_scalar(value)]


def _dump_mapping(value: Mapping[str, Any], indent: int) -> list[str]:
    if not value:
        return [" " * indent + "{}"]

    lines: list[str] = []
    prefix = " " * indent
    for key, item in value.items():
        lines.extend(_dump_key_value(prefix, key, item, child_indent=indent + 2))
    return lines


def _dump_list(value: list[Any], indent: int) -> list[str]:
    prefix = " " * indent
    if not value:
        return [prefix + "[]"]

    lines: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            item_lines = _dump_mapping_item(item, indent)
            lines.extend(item_lines)
        elif isinstance(item, list):
            lines.append(prefix + "-")
            lines.extend(_dump_list(item, indent + 2))
        elif _is_multiline_string(item):
            lines.append(prefix + "- |")
            lines.extend(_dump_block_string(item, indent + 2))
        else:
            lines.append(prefix + f"- {_format_scalar(item)}")
    return lines


def _dump_mapping_item(value: Mapping[str, Any], indent: int) -> list[str]:
    prefix = " " * indent
    if not value:
        return [prefix + "- {}"]

    lines: list[str] = []
    items = list(value.items())
    first_key, first_value = items[0]

    if _is_complex(first_value):
        lines.append(prefix + f"- {first_key}:")
        lines.extend(_dump_value(first_value, indent + 4))
    elif _is_multiline_string(first_value):
        lines.append(prefix + f"- {first_key}: |")
        lines.extend(_dump_block_string(first_value, indent + 4))
    else:
        lines.append(prefix + f"- {first_key}: {_format_scalar(first_value)}")

    child_prefix = " " * (indent + 2)
    for key, item in items[1:]:
        lines.extend(_dump_key_value(child_prefix, key, item, child_indent=indent + 4))

    return lines


def _dump_key_value(prefix: str, key: str, value: Any, child_indent: int) -> list[str]:
    if _is_complex(value):
        return [prefix + f"{key}:"] + _dump_value(value, child_indent)
    if _is_multiline_string(value):
        return [prefix + f"{key}: |"] + _dump_block_string(value, child_indent)
    return [prefix + f"{key}: {_format_scalar(value)}"]


def _dump_block_string(value: str, indent: int) -> list[str]:
    prefix = " " * indent
    return [prefix + line for line in value.splitlines()]


def _is_complex(value: Any) -> bool:
    return isinstance(value, (Mapping, list))


def _is_multiline_string(value: Any) -> bool:
    return isinstance(value, str) and "\n" in value


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if value == "":
            return '""'
        if _can_use_plain_string(value):
            return value
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, BaseModel):
        return _format_scalar(value.model_dump(mode="json", exclude_none=True))
    return json.dumps(value, ensure_ascii=False)


def _can_use_plain_string(value: str) -> bool:
    if value.strip() != value:
        return False
    if value[0] in "-?:,[]{}#&*!|>'\"%@`":
        return False
    if value.lower() in {"null", "true", "false", "yes", "no", "on", "off"}:
        return False
    if re.fullmatch(r"[+-]?(?:\d+|\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", value):
        return False
    if ": " in value or " #" in value:
        return False
    return not any(char in value for char in "\r\n\t")
