from __future__ import annotations

from typing import Literal

from backend.schemas.conversion import PolishSceneResponse
from backend.schemas.script_yaml import ScriptYAML
from backend.services.script_yaml_validator import validate_or_repair_script_yaml

PolishAction = Literal["conflict", "dialogue"]


def polish_scene(script_yaml: ScriptYAML, scene_id: str, action: PolishAction) -> PolishSceneResponse:
    data = script_yaml.model_dump(mode="json", exclude_none=True)
    scene = next((item for item in data["scenes"] if item["id"] == scene_id), None)
    if scene is None:
        result = validate_or_repair_script_yaml(data)
        return PolishSceneResponse(script_yaml=result.data, repaired=True, issues=[f"scene '{scene_id}' not found"])

    if action == "conflict":
        _boost_conflict(data, scene)
    else:
        _rewrite_dialogue(data, scene)

    result = validate_or_repair_script_yaml(data)
    return PolishSceneResponse(script_yaml=result.data, repaired=result.repaired, issues=result.issues)


def _boost_conflict(data: dict, scene: dict) -> None:
    scene["summary"] = f"{scene.get('summary') or scene['title']} 双方目标更明确，场面压力升级。"
    data["script"].append(
        {
            "scene_id": scene["id"],
            "type": "note",
            "content": "镜头提示：压低环境声，保留人物呼吸和停顿，强化对峙感。",
        }
    )
    data["script"].append(
        {
            "scene_id": scene["id"],
            "type": "action",
            "content": "两人之间的距离没有变化，但每一句话都像在逼近对方的底线。",
        }
    )


def _rewrite_dialogue(data: dict, scene: dict) -> None:
    dialogue = next(
        (line for line in data["script"] if line["scene_id"] == scene["id"] and line["type"] == "dialogue"),
        None,
    )
    if dialogue:
        dialogue["content"] = f"{dialogue['content']} 但这次，我不会再替你沉默。"
        return

    character_id = next(iter(scene.get("characters", [])), data["characters"][0]["id"])
    data["script"].append(
        {
            "scene_id": scene["id"],
            "type": "dialogue",
            "character_id": character_id,
            "content": "你以为我只是在等你，其实我是在等一个答案。",
        }
    )
