from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.script_yaml import ScriptYAML


class ConvertRequest(BaseModel):
    text: str = Field(..., min_length=1)
    title: str | None = None
    source: str | None = None
    mock: bool | None = None
    target_language: Literal["zh", "en", "fr", "ja", "ru"] = "zh"


class ChapterResponse(BaseModel):
    id: str
    chapter_id: str
    chapter_index: int = Field(..., ge=1)
    title: str
    heading: str
    marker: str
    content: str
    word_count: int
    summary: str
    status: str


class StageLog(BaseModel):
    stage: str
    chapter_index: int | None = None
    chapter_title: str | None = None
    prompt_chars: int = 0
    elapsed_seconds: float
    response_chars: int = 0


class ConvertResponse(BaseModel):
    chapters: list[ChapterResponse]
    script_yaml: ScriptYAML
    repaired: bool
    issues: list[str]
    mock_mode: bool
    stage_logs: list[StageLog] = Field(default_factory=list)


class PolishSceneRequest(BaseModel):
    script_yaml: ScriptYAML
    scene_id: str = Field(..., min_length=1)
    action: Literal["conflict", "dialogue"]


class PolishSceneResponse(BaseModel):
    script_yaml: ScriptYAML
    repaired: bool
    issues: list[str]
