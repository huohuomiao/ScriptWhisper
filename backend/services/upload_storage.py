from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backend.schemas.upload import UploadResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = PROJECT_ROOT / "backend" / "uploads"
MAX_UPLOAD_SIZE = 2 * 1024 * 1024


class UploadStorageError(RuntimeError):
    pass


def _safe_name(filename: str | None) -> str:
    name = Path(filename or "novel.txt").name.strip()
    return name or "novel.txt"


def _relative_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


async def save_txt_upload(file: UploadFile) -> UploadResponse:
    filename = _safe_name(file.filename)
    if Path(filename).suffix.lower() != ".txt":
        raise UploadStorageError("Only .txt files are supported.")

    content = await file.read()
    if not content:
        raise UploadStorageError("Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_SIZE:
        raise UploadStorageError("Uploaded file is larger than 2 MB.")

    try:
        text = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise UploadStorageError("Uploaded file must be UTF-8 text.") from exc
    if not text.strip():
        raise UploadStorageError("Uploaded file is empty.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}_{filename}"
    destination = UPLOAD_DIR / stored_filename
    destination.write_bytes(content)

    return UploadResponse(
        filename=filename,
        stored_filename=stored_filename,
        saved_path=_relative_path(destination),
        size_bytes=len(content),
        content=text,
    )
