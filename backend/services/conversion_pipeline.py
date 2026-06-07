from __future__ import annotations

from dataclasses import asdict

from backend.schemas.conversion import ChapterResponse, ConvertResponse
from backend.services.ai_client import LLMClient, LLMSettings
from backend.services.chapter_parser import Chapter, parse_chapters
from backend.services.entity_extractor import extract_entities_from_chapter
from backend.services.scene_planner import plan_scenes_from_chapter
from backend.services.script_generator import generate_script_yaml_data
from backend.services.script_yaml_validator import validate_or_repair_script_yaml


async def convert_novel_text(
    text: str,
    *,
    title: str | None = None,
    source: str | None = None,
    mock: bool | None = None,
    target_language: str = "zh",
) -> ConvertResponse:
    stripped_text = text.strip()
    chapters = parse_chapters(stripped_text)
    if not chapters:
        chapters = [_single_chapter(stripped_text, title)]
    chapter_responses = [_chapter_response(chapter, index) for index, chapter in enumerate(chapters, start=1)]

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
    client = LLMClient(settings)

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
    }

    for chapter, chapter_response in zip(chapters, chapter_responses, strict=True):
        chapter_text = chapter.content.strip() or chapter.heading
        project_data = await extract_entities_from_chapter(chapter_text, project_data, client=client)
        project_data = await plan_scenes_from_chapter(
            chapter_text,
            project_data,
            chapter_meta=chapter_response.model_dump(mode="json"),
            client=client,
        )

    script_yaml_data = await generate_script_yaml_data(project_data, client=client)
    result = validate_or_repair_script_yaml(script_yaml_data, chapters=chapter_responses)

    return ConvertResponse(
        chapters=chapter_responses,
        script_yaml=result.data,
        repaired=result.repaired,
        issues=result.issues,
        mock_mode=client.mock_mode,
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
