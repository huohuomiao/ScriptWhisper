from __future__ import annotations

from dataclasses import asdict
from inspect import isawaitable
import logging
from time import perf_counter
from typing import Any, Callable

from backend.schemas.conversion import ChapterResponse, ConvertResponse, StageLog
from backend.services.ai_client import LLMClient, LLMSettings
from backend.services.chapter_generator import generate_chapter_script_data
from backend.services.chapter_parser import Chapter, parse_chapters
from backend.services.script_yaml_validator import validate_script_yaml

ProgressCallback = Callable[[dict[str, Any]], Any]

logger = logging.getLogger(__name__)


async def convert_novel_text(
    text: str,
    *,
    title: str | None = None,
    source: str | None = None,
    mock: bool | None = None,
    target_language: str = "zh",
    progress_callback: ProgressCallback | None = None,
) -> ConvertResponse:
    stage_logs: list[StageLog] = []
    stripped_text = text.strip()

    parse_started_at = perf_counter()
    chapters = parse_chapters(stripped_text)
    if not chapters:
        chapters = [_single_chapter(stripped_text, title)]
    chapter_responses = [_chapter_response(chapter, index) for index, chapter in enumerate(chapters, start=1)]
    parse_log = StageLog(
        stage="chapter_parse",
        prompt_chars=0,
        elapsed_seconds=round(perf_counter() - parse_started_at, 3),
        response_chars=len(stripped_text),
    )
    stage_logs.append(parse_log)
    _log_stage(parse_log)
    await _emit_progress(
        progress_callback,
        {
            "type": "stage_complete",
            "stage": parse_log.stage,
            "current": 0,
            "total": len(chapters),
            "log": parse_log.model_dump(mode="json"),
        },
    )

    settings = LLMSettings.from_env()
    if mock is not None:
        settings = LLMSettings(
            api_key=settings.api_key,
            api_base_url=settings.api_base_url,
            model=settings.model,
            mock_mode=mock,
            api_protocol=settings.api_protocol,
            max_tokens=settings.max_tokens,
            request_timeout=settings.request_timeout,
        )

    project_data = {
        "project": {
            "title": (title or _title_from_chapters(chapters) or "Untitled").strip(),
            "source": source,
            "source_language": "zh",
            "target_language": _normalize_target_language(target_language),
        },
        "characters": [],
        "locations": [],
        "scenes": [],
        "script": [],
    }

    async with LLMClient(settings) as client:
        for index, (chapter, chapter_response) in enumerate(
            zip(chapters, chapter_responses, strict=True),
            start=1,
        ):
            chapter_text = chapter.content.strip() or chapter.heading
            await _emit_progress(
                progress_callback,
                {
                    "type": "stage_start",
                    "stage": "chapter_generate",
                    "chapter_index": index,
                    "chapter_title": chapter_response.title,
                    "current": index,
                    "total": len(chapters),
                },
            )
            project_data, raw_log = await generate_chapter_script_data(
                chapter_text,
                project_data,
                chapter_meta=chapter_response.model_dump(mode="json"),
                client=client,
            )
            stage_log = StageLog.model_validate(raw_log)
            stage_logs.append(stage_log)
            await _emit_progress(
                progress_callback,
                {
                    "type": "stage_complete",
                    "stage": stage_log.stage,
                    "chapter_index": stage_log.chapter_index,
                    "chapter_title": stage_log.chapter_title,
                    "current": index,
                    "total": len(chapters),
                    "log": stage_log.model_dump(mode="json"),
                    "characters": len(project_data.get("characters", [])),
                    "locations": len(project_data.get("locations", [])),
                    "scenes": len(project_data.get("scenes", [])),
                    "script_lines": len(project_data.get("script", [])),
                },
            )

    validate_started_at = perf_counter()
    await _emit_progress(
        progress_callback,
        {
            "type": "stage_start",
            "stage": "schema_validate",
            "current": len(chapters),
            "total": len(chapters),
        },
    )
    script_yaml = validate_script_yaml(project_data)
    validate_log = StageLog(
        stage="schema_validate",
        prompt_chars=0,
        elapsed_seconds=round(perf_counter() - validate_started_at, 3),
        response_chars=len(str(script_yaml.model_dump(mode="json"))),
    )
    stage_logs.append(validate_log)
    _log_stage(validate_log)
    await _emit_progress(
        progress_callback,
        {
            "type": "stage_complete",
            "stage": validate_log.stage,
            "current": len(chapters),
            "total": len(chapters),
            "log": validate_log.model_dump(mode="json"),
            "repaired": False,
            "issues": [],
        },
    )

    return ConvertResponse(
        chapters=chapter_responses,
        script_yaml=script_yaml,
        repaired=False,
        issues=[],
        mock_mode=settings.mock_mode,
        stage_logs=stage_logs,
    )


def _normalize_target_language(value: str | None) -> str:
    language = (value or "zh").strip().lower()
    return language if language in {"zh", "en", "fr", "ja", "ru"} else "zh"


def _single_chapter(text: str, title: str | None) -> Chapter:
    heading = (title or "全文").strip() or "全文"
    return Chapter(
        index=1,
        marker="全文",
        title=heading,
        heading=heading,
        content=text,
        start_line=1,
        end_line=max(1, text.count("\n") + 1),
    )


def _title_from_chapters(chapters: list[Chapter]) -> str | None:
    for chapter in chapters:
        if chapter.title:
            return chapter.title
    return None


def _chapter_response(chapter: Chapter, index: int) -> ChapterResponse:
    payload = asdict(chapter)
    title = chapter.heading if not chapter.title else f"{chapter.marker} {chapter.title}".strip()
    content = chapter.content.strip()
    summary = content.replace("\n", " ")[:120] if content else chapter.heading
    return ChapterResponse(
        id=f"chapter_{index}",
        chapter_id=f"chapter_{index}",
        chapter_index=index,
        title=title,
        heading=payload["heading"],
        marker=payload["marker"],
        content=content,
        word_count=len(content),
        summary=summary,
        status="已分析",
    )


async def _emit_progress(callback: ProgressCallback | None, event: dict[str, Any]) -> None:
    if callback is None:
        return
    result = callback(event)
    if isawaitable(result):
        await result


def _log_stage(stage_log: StageLog) -> None:
    logger.info(
        "ai_stage stage=%s chapter=%s prompt_chars=%s elapsed=%.3f response_chars=%s",
        stage_log.stage,
        stage_log.chapter_index,
        stage_log.prompt_chars,
        stage_log.elapsed_seconds,
        stage_log.response_chars,
    )
