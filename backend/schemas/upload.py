from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    filename: str = Field(..., min_length=1)
    stored_filename: str = Field(..., min_length=1)
    saved_path: str = Field(..., min_length=1)
    size_bytes: int = Field(..., ge=1)
    content: str = Field(..., min_length=1)
