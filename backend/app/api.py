from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.schemas.upload import UploadResponse
from backend.services.upload_storage import UploadStorageError, save_txt_upload

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/upload", response_model=UploadResponse)
async def upload_novel(file: UploadFile = File(...)) -> UploadResponse:
    try:
        return await save_txt_upload(file)
    except UploadStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
