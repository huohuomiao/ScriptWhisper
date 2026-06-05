from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import upload_storage


def test_upload_sample_novel_3chapters(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(upload_storage, "UPLOAD_DIR", tmp_path)
    client = TestClient(app)
    sample_path = Path(__file__).resolve().parents[2] / "examples" / "sample_novel_3chapters.txt"

    with sample_path.open("rb") as sample_file:
        response = client.post(
            "/api/upload",
            files={"file": ("sample_novel_3chapters.txt", sample_file, "text/plain")},
        )

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    saved_file = tmp_path / data["stored_filename"]

    assert payload["success"] is True
    assert payload["message"] == "Upload completed."
    assert payload["error_code"] is None
    assert data["filename"] == "sample_novel_3chapters.txt"
    assert data["size_bytes"] == sample_path.stat().st_size
    assert data["content"] == sample_path.read_text(encoding="utf-8-sig")
    assert saved_file.exists()
    assert saved_file.read_bytes() == sample_path.read_bytes()


def test_upload_rejects_non_txt_file() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/upload",
        files={"file": ("sample.md", b"# title", "text/markdown")},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "Only .txt files are supported."
    assert payload["data"] is None
    assert payload["error_code"] == "HTTP_400"


def test_upload_rejects_whitespace_only_file() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/upload",
        files={"file": ("empty.txt", b"\xef\xbb\xbf  \n", "text/plain")},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "Uploaded file is empty."
    assert payload["data"] is None
    assert payload["error_code"] == "HTTP_400"
