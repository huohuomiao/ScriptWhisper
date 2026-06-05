from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.script_yaml import ScriptYAML


def test_convert_endpoint_runs_mock_pipeline() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/convert",
        json={
            "title": "Rain Letter",
            "text": "Chapter 1 Rain Letter\n\nLin meets Shen outside the old cinema.",
            "source": "sample.txt",
            "mock": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]

    assert payload["success"] is True
    assert payload["message"] == "Novel converted."
    assert payload["error_code"] is None
    assert data["mock_mode"] is True
    assert data["chapters"]
    assert data["script_yaml"]["project"]["title"] == "Rain Letter"
    assert data["script_yaml"]["characters"]
    assert data["script_yaml"]["locations"]
    assert data["script_yaml"]["scenes"]
    assert data["script_yaml"]["script"]


def test_polish_scene_endpoint_updates_scriptyaml() -> None:
    client = TestClient(app)
    convert_response = client.post(
        "/api/convert",
        json={
            "title": "Rain Letter",
            "text": "Lin meets Shen outside the old cinema.",
            "mock": True,
        },
    )
    script_yaml = convert_response.json()["data"]["script_yaml"]
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
    payload = response.json()
    data = payload["data"]
    scene = data["script_yaml"]["scenes"][0]

    assert payload["success"] is True
    assert payload["message"] == "Scene polished."
    assert payload["error_code"] is None
    assert scene["summary"]
    assert any(line["scene_id"] == scene_id and line["type"] == "note" for line in data["script_yaml"]["script"])


def test_convert_endpoint_validation_error_uses_api_envelope() -> None:
    client = TestClient(app)

    response = client.post("/api/convert", json={"text": ""})

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "Request validation failed."
    assert payload["error_code"] == "VALIDATION_ERROR"
    assert payload["data"]["errors"]


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
