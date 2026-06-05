from dataclasses import dataclass
import re

MAX_HEADING_LENGTH = 120

_CHINESE_HEADING_RE = re.compile(
    r"^\s*(?P<marker>第\s*[零〇一二两三四五六七八九十百千万\d]+\s*[章节回卷部篇])"
    r"(?:\s*[:：、.\-]?\s*(?P<title>.*?))?\s*$"
)
_ENGLISH_HEADING_RE = re.compile(
    r"^\s*(?P<marker>chapter\s+(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty))"
    r"(?:\s*[:：、.\-]?\s*(?P<title>.*?))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Chapter:
    index: int
    marker: str
    title: str
    heading: str
    content: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class _HeadingMatch:
    line_index: int
    line_number: int
    marker: str
    title: str
    heading: str


def is_chapter_heading(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_LENGTH:
        return None

    for pattern in (_CHINESE_HEADING_RE, _ENGLISH_HEADING_RE):
        match = pattern.match(stripped)
        if match:
            marker = re.sub(r"\s+", " ", match.group("marker")).strip()
            title = (match.group("title") or "").strip()
            return marker, title

    return None


def parse_chapters(text: str) -> list[Chapter]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    headings = _find_headings(lines)
    chapters: list[Chapter] = []

    for index, heading in enumerate(headings, start=1):
        next_heading = headings[index] if index < len(headings) else None
        content_start = heading.line_index + 1
        content_end = next_heading.line_index if next_heading else len(lines)
        end_line = next_heading.line_number - 1 if next_heading else len(lines)

        chapters.append(
            Chapter(
                index=index,
                marker=heading.marker,
                title=heading.title,
                heading=heading.heading,
                content="\n".join(lines[content_start:content_end]).strip("\n"),
                start_line=heading.line_number,
                end_line=end_line,
            )
        )

    return chapters


def _find_headings(lines: list[str]) -> list[_HeadingMatch]:
    headings: list[_HeadingMatch] = []

    for line_index, line in enumerate(lines):
        heading = is_chapter_heading(line)
        if not heading:
            continue

        marker, title = heading
        headings.append(
            _HeadingMatch(
                line_index=line_index,
                line_number=line_index + 1,
                marker=marker,
                title=title,
                heading=line.strip(),
            )
        )

    return headings
