from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.app.config import get_settings
from backend.schemas.conversion import ConvertRequest, ConvertResponse
from backend.schemas.upload import UploadResponse
from backend.services.ai_client import AIClient, AIClientError
from backend.services.upload_storage import UploadStorageError, save_txt_upload

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/convert", response_model=ConvertResponse)
async def convert_novel(payload: ConvertRequest) -> ConvertResponse:
    client = AIClient(get_settings())

    try:
        return await client.convert_to_script(payload)
    except AIClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/upload", response_model=UploadResponse)
async def upload_novel(file: UploadFile = File(...)) -> UploadResponse:
    try:
        return await save_txt_upload(file)
    except UploadStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
