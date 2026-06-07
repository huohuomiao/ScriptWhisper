from pydantic import BaseModel


class UploadResponse(BaseModel):
    filename: str
    stored_filename: str
    saved_path: str
    size_bytes: int
    content: str
