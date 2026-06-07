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
    data = response.json()
    saved_file = tmp_path / data["stored_filename"]

    assert data["filename"] == "sample_novel_3chapters.txt"
    assert data["size_bytes"] == sample_path.stat().st_size
    assert "第一章" in data["content"]
    assert "第三章" in data["content"]
    assert saved_file.exists()
    assert saved_file.read_text(encoding="utf-8").startswith("第一章")
