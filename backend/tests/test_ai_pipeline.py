import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from backend.schemas.script_yaml import ScriptYAML
from backend.services.ai_client import LLMClient, LLMClientError, LLMSettings
from backend.services.entity_extractor import extract_entities_from_chapter
from backend.services.scene_planner import plan_scenes_from_chapter
from backend.services.script_generator import _script_messages, generate_script_yaml
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


def test_llm_client_openai_protocol_request_format() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "openai ok"}}]},
            )

        client = LLMClient(
            LLMSettings(
                api_key="test-key",
                api_base_url="https://example.test/v1",
                model="test-model",
                api_protocol="openai",
                max_tokens=1234,
            ),
            transport=httpx.MockTransport(handler),
        )

        result = await client.chat([{"role": "user", "content": "hello"}], temperature=0.1)

        assert result == "openai ok"
        assert str(requests[0].url) == "https://example.test/v1/chat/completions"
        assert requests[0].headers["authorization"] == "Bearer test-key"
        body = json.loads(requests[0].content)
        assert body["model"] == "test-model"
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert body["temperature"] == 0.1
        assert body["max_tokens"] == 1234

    asyncio.run(run())


def test_llm_client_timeout_error_is_actionable() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("", request=request)

        client = LLMClient(
            LLMSettings(
                api_key="test-key",
                api_base_url="https://example.test/v1",
                model="test-model",
                api_protocol="openai",
                max_tokens=1234,
                request_timeout=1,
            ),
            transport=httpx.MockTransport(handler),
        )

        with pytest.raises(LLMClientError) as exc_info:
            await client.chat([{"role": "user", "content": "hello"}], temperature=0.1)

        message = str(exc_info.value)
        assert "timed out after 1s" in message
        assert "AI_REQUEST_TIMEOUT_SECONDS" in message

    asyncio.run(run())


def test_llm_client_anthropic_protocol_request_format() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "anthropic ok"}]},
            )

        client = LLMClient(
            LLMSettings(
                api_key="test-key",
                api_base_url="https://example.test/anthropic",
                model="claude-test",
                api_protocol="anthropic",
                max_tokens=1234,
            ),
            transport=httpx.MockTransport(handler),
        )

        result = await client.chat(
            [
                {"role": "system", "content": "return concise text"},
                {"role": "user", "content": "hello"},
            ],
            temperature=0.3,
        )

        assert result == "anthropic ok"
        assert str(requests[0].url) == "https://example.test/anthropic/v1/messages"
        assert requests[0].headers["authorization"] == "Bearer test-key"
        assert requests[0].headers["x-api-key"] == "test-key"
        assert requests[0].headers["anthropic-version"] == "2023-06-01"
        body = json.loads(requests[0].content)
        assert body["model"] == "claude-test"
        assert body["max_tokens"] == 1234
        assert body["system"] == "return concise text"
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert body["temperature"] == 0.3

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


def test_validate_or_repair_script_yaml_repairs_invalid_source_ref_chapter_index() -> None:
    data = {
        "project": {"title": "Broken Source"},
        "characters": [{"id": "char_1", "name": "Alice"}],
        "locations": [{"id": "loc_1", "name": "Station"}],
        "scenes": [
            {
                "id": "scene_1",
                "title": "Wrong Source",
                "location_id": "loc_1",
                "characters": ["char_1"],
                "summary": "Alice waits.",
                "source_ref": {
                    "chapter_id": "chapter_99",
                    "chapter_index": 99,
                    "chapter_title": "Ghost Chapter",
                    "excerpt": "Invalid excerpt.",
                },
            }
        ],
        "script": [{"scene_id": "scene_1", "type": "action", "content": "Alice waits."}],
    }

    result = validate_or_repair_script_yaml(
        data,
        chapters=[
            {"chapter_id": "chapter_1", "chapter_index": 1, "title": "Chapter 1", "content": "First."},
            {"chapter_id": "chapter_2", "chapter_index": 2, "title": "Chapter 2", "content": "Second."},
        ],
    )

    assert result.repaired is True
    assert result.issues
    source_ref = result.data.scenes[0].source_ref
    assert source_ref is not None
    assert source_ref.chapter_id == "chapter_2"
    assert source_ref.chapter_index == 2
    assert source_ref.chapter_title == "Chapter 2"


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


def test_yaml_exporter_includes_language_fields() -> None:
    data = {
        "project": {"title": "Language Test", "source_language": "zh", "target_language": "fr"},
        "characters": [{"id": "char_1", "name": "A"}],
        "locations": [{"id": "loc_1", "name": "Room"}],
        "scenes": [{"id": "scene_1", "title": "Open", "location_id": "loc_1", "characters": ["char_1"]}],
        "script": [{"scene_id": "scene_1", "type": "action", "content": "Bonjour."}],
    }

    output = to_yaml(data)

    assert "source_language: zh" in output
    assert "target_language: fr" in output


def test_script_generator_prompt_includes_target_language() -> None:
    messages = _script_messages({"project": {"title": "Language Test", "target_language": "ja"}})

    assert "请使用所选目标语言输出人物描述、地点描述、场景摘要、剧情节拍、动作、对白、镜头和导出文本。" in messages[0]["content"]
    assert "target_language=ja" in messages[0]["content"]


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
