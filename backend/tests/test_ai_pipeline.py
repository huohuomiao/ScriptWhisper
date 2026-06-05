import asyncio

import pytest
from pydantic import ValidationError

from backend.schemas.script_yaml import ScriptYAML
from backend.services.ai_client import LLMClient, LLMSettings
from backend.services.entity_extractor import extract_entities_from_chapter
from backend.services.scene_planner import plan_scenes_from_chapter
from backend.services.script_generator import generate_script_yaml
from backend.services.script_yaml_validator import validate_or_repair_script_yaml
from backend.services.yaml_exporter import to_yaml


def test_llm_client_mock_mode_chat_and_json() -> None:
    async def run() -> None:
        client = LLMClient(LLMSettings(api_key=None, api_base_url=None, model=None, mock_mode=True))

        chat_result = await client.chat([{"role": "user", "content": "hello mock"}])
        json_result = await client.json(
            [{"role": "user", "content": "return json"}],
            mock_response={"ok": True},
        )

        assert chat_result == "MOCK_RESPONSE: hello mock"
        assert json_result == {"ok": True}

    asyncio.run(run())


def test_scriptyaml_rejects_unknown_references() -> None:
    invalid_data = {
        "project": {"title": "Broken"},
        "characters": [{"id": "lin_che", "name": "林澈"}],
        "locations": [{"id": "old_cinema", "name": "旧影院"}],
        "scenes": [
            {
                "id": "scene_1",
                "title": "雨夜重逢",
                "location_id": "missing_location",
                "characters": ["lin_che"],
            }
        ],
        "script": [{"scene_id": "scene_1", "type": "action", "content": "雨停后的长街泛着冷光。"}],
    }

    with pytest.raises(ValidationError, match="unknown location_id"):
        ScriptYAML.model_validate(invalid_data)


def test_validate_or_repair_script_yaml_fixes_bad_input() -> None:
    bad_data = {
        "project": {},
        "characters": [{"id": "林澈", "name": "林澈"}],
        "locations": [{"id": "旧影院", "name": "旧影院"}],
        "scenes": [
            {
                "id": "场景一",
                "title": "",
                "location_id": "not_found",
                "characters": ["林澈", "ghost"],
            }
        ],
        "script": [{"scene_id": "missing_scene", "type": "dialogue", "content": ""}],
    }

    result = validate_or_repair_script_yaml(bad_data)

    assert result.repaired is True
    assert result.issues
    assert result.data.project.title == "Untitled"
    assert result.data.characters[0].id == "char_1"
    assert result.data.locations[0].id == "loc_1"
    assert result.data.scenes[0].id == "scene_1"
    assert result.data.script[0].scene_id == "scene_1"


def test_yaml_exporter_rejects_invalid_data() -> None:
    invalid_data = {
        "project": {"title": "Broken"},
        "characters": [{"id": "lin_che", "name": "林澈"}],
        "locations": [{"id": "old_cinema", "name": "旧影院"}],
        "scenes": [
            {
                "id": "scene_1",
                "title": "雨夜重逢",
                "location_id": "old_cinema",
                "characters": ["lin_che"],
            }
        ],
        "script": [{"scene_id": "scene_404", "type": "action", "content": "错误场景引用。"}],
    }

    with pytest.raises(ValidationError, match="unknown scene_id"):
        to_yaml(invalid_data)


def test_mock_ai_pipeline_generates_valid_scriptyaml() -> None:
    async def run() -> ScriptYAML:
        chapter_text = (
            "林澈在旧影院门口见到沈微。\n\n"
            "沈微把电影票递给他，放映室里传来机器启动的声音。"
        )
        client = LLMClient(LLMSettings(api_key=None, api_base_url=None, model=None, mock_mode=True))

        project_data = await extract_entities_from_chapter(
            chapter_text,
            {"project": {"title": "雨夜来信"}},
            client=client,
        )
        project_data = await plan_scenes_from_chapter(chapter_text, project_data, client=client)
        script_yaml = await generate_script_yaml(project_data, client=client)
        result = validate_or_repair_script_yaml(script_yaml)

        assert result.repaired is False
        return result.data

    script_yaml = asyncio.run(run())

    assert script_yaml.project.title == "雨夜来信"
    assert script_yaml.characters
    assert script_yaml.locations
    assert script_yaml.scenes
    assert script_yaml.script
