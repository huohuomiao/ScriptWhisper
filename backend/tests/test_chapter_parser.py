from backend.services.chapter_parser import is_chapter_heading, parse_chapters


def test_parse_chinese_chapter_headings() -> None:
    text = "\n".join(
        [
            "楔子",
            "这不是章节标题。",
            "",
            "第一章 雨夜来信",
            "雨停后的长街泛着冷光。",
            "",
            "第十二回：旧影院",
            "影院大门被风推开。",
            "",
            "第3章 归来",
            "林澈终于明白答案。",
        ]
    )

    chapters = parse_chapters(text)

    assert len(chapters) == 3
    assert [chapter.marker for chapter in chapters] == ["第一章", "第十二回", "第3章"]
    assert [chapter.title for chapter in chapters] == ["雨夜来信", "旧影院", "归来"]
    assert chapters[0].content == "雨停后的长街泛着冷光。"
    assert chapters[0].start_line == 4
    assert chapters[0].end_line == 6


def test_parse_english_chapter_headings() -> None:
    text = "\n".join(
        [
            "Chapter 1: Arrival",
            "The station clock stopped at midnight.",
            "",
            "CHAPTER IV Return",
            "She opened the old cinema door.",
            "",
            "Chapter Ten - Last Letter",
            "The final line remained unfinished.",
        ]
    )

    chapters = parse_chapters(text)

    assert len(chapters) == 3
    assert [chapter.marker for chapter in chapters] == ["Chapter 1", "CHAPTER IV", "Chapter Ten"]
    assert [chapter.title for chapter in chapters] == ["Arrival", "Return", "Last Letter"]
    assert chapters[2].content == "The final line remained unfinished."


def test_is_chapter_heading_rejects_regular_lines() -> None:
    assert is_chapter_heading("这一章只是普通叙述，不是标题。") is None
    assert is_chapter_heading("Chapterhouse is a word, not a chapter title.") is None
    assert is_chapter_heading("Chapter 1 " + "x" * 130) is None


def test_parse_chapters_returns_empty_list_without_headings() -> None:
    text = "雨停后的长街泛着冷光。\n她没有开口，只把电影票递给他。"

    assert parse_chapters(text) == []
