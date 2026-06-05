from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.script_yaml import ScriptYAML


class ConvertRequest(BaseModel):
    text: str = Field(..., min_length=1)
    title: str | None = None
    source: str | None = None
    mock: bool | None = None


class ChapterResponse(BaseModel):
    id: str
    title: str
    heading: str
    marker: str
    content: str
    word_count: int
    summary: str
    status: str


class ConvertResponse(BaseModel):
    chapters: list[ChapterResponse]
    script_yaml: ScriptYAML
    repaired: bool
    issues: list[str]
    mock_mode: bool


class PolishSceneRequest(BaseModel):
    script_yaml: ScriptYAML
    scene_id: str = Field(..., min_length=1)
    action: Literal["conflict", "dialogue"]


class PolishSceneResponse(BaseModel):
    script_yaml: ScriptYAML
    repaired: bool
    issues: list[str]
