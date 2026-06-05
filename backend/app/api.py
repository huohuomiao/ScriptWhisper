from fastapi import APIRouter, HTTPException

from backend.app.config import get_settings
from backend.schemas.conversion import ConvertRequest, ConvertResponse
from backend.services.ai_client import AIClient, AIClientError

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
