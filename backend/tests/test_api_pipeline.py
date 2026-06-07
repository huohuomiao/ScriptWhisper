from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.conversion import ConvertRequest
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
    assert data["script_yaml"]["project"]["target_language"] == "zh"
    assert data["script_yaml"]["characters"]
    assert data["script_yaml"]["locations"]
    assert data["script_yaml"]["scenes"]
    assert data["script_yaml"]["script"]


def test_convert_request_target_language_defaults_to_zh() -> None:
    payload = ConvertRequest(text="Lin meets Shen.")

    assert payload.target_language == "zh"


def test_convert_endpoint_accepts_target_language() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/convert",
        json={
            "title": "Rain Letter",
            "text": "Chapter 1 Rain Letter\n\nLin meets Shen outside the old cinema.",
            "source": "sample.txt",
            "mock": True,
            "target_language": "en",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["script_yaml"]["project"]["source_language"] == "zh"
    assert data["script_yaml"]["project"]["target_language"] == "en"


def test_single_chapter_multiple_scenes_bind_to_first_chapter() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/convert",
        json={
            "title": "One Chapter",
            "text": "Chapter 1 Opening\n\nAlice waits in the station.\n\nBob arrives with a locked case.",
            "mock": True,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    scenes = data["script_yaml"]["scenes"]

    assert len(data["chapters"]) == 1
    assert data["chapters"][0]["chapter_id"] == "chapter_1"
    assert data["chapters"][0]["chapter_index"] == 1
    assert len(scenes) >= 2
    assert {scene["source_ref"]["chapter_id"] for scene in scenes} == {"chapter_1"}
    assert {scene["source_ref"]["chapter_index"] for scene in scenes} == {1}


def test_two_chapters_bind_scenes_to_real_source_chapters() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/convert",
        json={
            "title": "Two Chapters",
            "text": (
                "Chapter 1 Opening\n\nAlice waits in the station.\n\n"
                "Chapter 2 Return\n\nBob returns with a locked case."
            ),
            "mock": True,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    scenes = data["script_yaml"]["scenes"]
    first_chapter_scenes = [scene for scene in scenes if scene["source_ref"]["chapter_id"] == "chapter_1"]
    second_chapter_scenes = [scene for scene in scenes if scene["source_ref"]["chapter_id"] == "chapter_2"]

    assert [chapter["chapter_id"] for chapter in data["chapters"]] == ["chapter_1", "chapter_2"]
    assert first_chapter_scenes
    assert second_chapter_scenes
    assert all(scene["source_ref"]["chapter_index"] == 1 for scene in first_chapter_scenes)
    assert all(scene["source_ref"]["chapter_index"] == 2 for scene in second_chapter_scenes)


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
    assert result.project.source_language == "zh"
    assert result.project.target_language == "zh"


def test_scriptyaml_accepts_editable_script_line_fields() -> None:
    data = {
        "project": {"title": "Editable Lines"},
        "characters": [{"id": "char_1", "name": "A"}],
        "locations": [{"id": "loc_1", "name": "Room"}],
        "scenes": [{"id": "scene_1", "title": "Open", "location_id": "loc_1", "characters": ["char_1"]}],
        "script": [
            {
                "id": "line_1",
                "scene_id": "scene_1",
                "type": "camera",
                "content": "Push in.",
                "text": "Push in.",
                "highlight_color": "#fff3a3",
                "note": "Keep the frame tight.",
            },
            {
                "id": "line_2",
                "scene_id": "scene_1",
                "type": "dialogue",
                "content": "I am ready.",
                "speaker_name": "Guest",
                "emotion": "calm",
            },
        ],
    }

    result = ScriptYAML.model_validate(data)

    assert result.script[0].type == "camera"
    assert result.script[0].highlight_color == "#fff3a3"
    assert result.script[1].speaker_name == "Guest"


def test_scriptyaml_accepts_camel_case_highlight_color() -> None:
    data = {
        "project": {"title": "Editable Lines"},
        "characters": [{"id": "char_1", "name": "A"}],
        "locations": [{"id": "loc_1", "name": "Room"}],
        "scenes": [{"id": "scene_1", "title": "Open", "location_id": "loc_1", "characters": ["char_1"]}],
        "script": [{"scene_id": "scene_1", "type": "action", "content": "Start.", "highlightColor": "purple"}],
    }

    result = ScriptYAML.model_validate(data)

    assert result.script[0].highlight_color == "purple"
