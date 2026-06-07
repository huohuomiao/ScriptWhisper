import asyncio
import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.schemas.api_response import ApiResponse, success_response
from backend.schemas.conversion import ConvertRequest, ConvertResponse, PolishSceneRequest, PolishSceneResponse
from backend.schemas.upload import UploadResponse
from backend.services.ai_client import LLMClientError
from backend.services.conversion_pipeline import convert_novel_text
from backend.services.scene_polisher import polish_scene
from backend.services.upload_storage import UploadStorageError, save_txt_upload

router = APIRouter()


@router.get("/health")
async def health() -> ApiResponse:
    return success_response({"status": "ok"})


@router.post("/api/upload", response_model=ApiResponse)
async def upload_novel(file: UploadFile = File(...)) -> ApiResponse:
    try:
        result: UploadResponse = await save_txt_upload(file)
        return success_response(result, "Upload completed.")
    except UploadStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/convert", response_model=ApiResponse)
async def convert_novel(payload: ConvertRequest) -> ApiResponse:
    try:
        result: ConvertResponse = await convert_novel_text(
            payload.text,
            title=payload.title,
            source=payload.source,
            mock=payload.mock,
            target_language=payload.target_language,
        )
        return success_response(result, "Novel converted.")
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/convert/stream")
async def convert_novel_stream(payload: ConvertRequest) -> StreamingResponse:
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def progress(event: dict) -> None:
        await queue.put(event)

    async def run_conversion() -> None:
        try:
            result: ConvertResponse = await convert_novel_text(
                payload.text,
                title=payload.title,
                source=payload.source,
                mock=payload.mock,
                target_language=payload.target_language,
                progress_callback=progress,
            )
            await queue.put({"type": "complete", "data": result.model_dump(mode="json")})
        except LLMClientError as exc:
            await queue.put({"type": "error", "message": str(exc), "error_code": "AI_API_ERROR"})
        except Exception as exc:  # pragma: no cover - defensive for streamed responses
            await queue.put(
                {
                    "type": "error",
                    "message": str(exc) or "Internal server error.",
                    "error_code": "INTERNAL_ERROR",
                }
            )
        finally:
            await queue.put(None)

    asyncio.create_task(run_conversion())

    async def events():
        while True:
            event = await queue.get()
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@router.post("/api/scenes/polish", response_model=ApiResponse)
async def polish_scene_endpoint(payload: PolishSceneRequest) -> ApiResponse:
    result: PolishSceneResponse = polish_scene(payload.script_yaml, payload.scene_id, payload.action)
    return success_response(result, "Scene polished.")
