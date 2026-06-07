from typing import Literal

from pydantic import BaseModel, Field


class ConvertRequest(BaseModel):
    novel_text: str = Field(..., min_length=1, max_length=12000)
    style: str = Field(default="影视剧本", max_length=40)
    model: str | None = Field(default=None, max_length=120)


class ConvertResponse(BaseModel):
    script: str
    provider: Literal["mock", "api"]
