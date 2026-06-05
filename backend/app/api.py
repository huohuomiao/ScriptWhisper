from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.schemas.conversion import ConvertRequest, ConvertResponse, PolishSceneRequest, PolishSceneResponse
from backend.schemas.upload import UploadResponse
from backend.services.ai_client import LLMClientError
from backend.services.conversion_pipeline import convert_novel_text
from backend.services.scene_polisher import polish_scene
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


@router.post("/api/convert", response_model=ConvertResponse)
async def convert_novel(payload: ConvertRequest) -> ConvertResponse:
    try:
        return await convert_novel_text(
            payload.text,
            title=payload.title,
            source=payload.source,
            mock=payload.mock,
        )
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/scenes/polish", response_model=PolishSceneResponse)
async def polish_scene_endpoint(payload: PolishSceneRequest) -> PolishSceneResponse:
    return polish_scene(payload.script_yaml, payload.scene_id, payload.action)
