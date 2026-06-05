from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.script_yaml import ScriptYAML


def test_convert_endpoint_runs_mock_pipeline() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/convert",
        json={
            "title": "雨夜来信",
            "text": "第一章 雨夜来信\n\n林澈在旧影院门口见到沈微。沈微把电影票递给他。",
            "source": "sample.txt",
            "mock": True,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["mock_mode"] is True
    assert data["chapters"][0]["title"] == "第一章 雨夜来信"
    assert data["script_yaml"]["project"]["title"] == "雨夜来信"
    assert data["script_yaml"]["characters"]
    assert data["script_yaml"]["locations"]
    assert data["script_yaml"]["scenes"]
    assert data["script_yaml"]["script"]


def test_polish_scene_endpoint_updates_scriptyaml() -> None:
    client = TestClient(app)
    convert_response = client.post(
        "/api/convert",
        json={
            "title": "雨夜来信",
            "text": "林澈在旧影院门口见到沈微。",
            "mock": True,
        },
    )
    script_yaml = convert_response.json()["script_yaml"]
    scene_id = script_yaml["scenes"][0]["id"]

    response = client.post(
        "/api/scenes/polish",
        json={
            "script_yaml": script_yaml,
            "scene_id": scene_id,
            "action": "conflict",
        },
    )

    assert response.status_code == 200
    data = response.json()
    scene = data["script_yaml"]["scenes"][0]

    assert "压力升级" in scene["summary"]
    assert any(line["scene_id"] == scene_id and line["type"] == "note" for line in data["script_yaml"]["script"])


def test_project_optional_empty_strings_become_none() -> None:
    data = {
        "project": {"title": "Test", "genre": "", "logline": "  ", "source": " source.txt "},
        "characters": [{"id": "char_1", "name": "A"}],
        "locations": [{"id": "loc_1", "name": "Room"}],
        "scenes": [{"id": "scene_1", "title": "Open", "location_id": "loc_1", "characters": ["char_1"]}],
        "script": [{"scene_id": "scene_1", "type": "action", "content": "Start."}],
    }

    result = ScriptYAML.model_validate(data)

    assert result.project.genre is None
    assert result.project.logline is None
    assert result.project.source == "source.txt"
