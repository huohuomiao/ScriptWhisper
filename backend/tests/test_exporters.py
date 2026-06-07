from backend.services.markdown_exporter import to_markdown
from backend.services.yaml_exporter import to_yaml


def test_yaml_export_repairs_invalid_source_ref_chapter() -> None:
    yaml_text = to_yaml(_editable_script_yaml(), chapters=[_chapter("chapter_1", 1, "第一章 雨夜来信")])

    assert "chapter_99" not in yaml_text
    assert "chapter_id: chapter_1" in yaml_text
    assert "chapter_index: 1" in yaml_text
    assert "null" not in yaml_text


def test_markdown_export_groups_by_chapter_and_omits_empty_fields() -> None:
    markdown = to_markdown(
        _editable_script_yaml(),
        chapters=[
            _chapter("chapter_1", 1, "第一章 雨夜来信"),
            _chapter("chapter_2", 2, "第二章 旧影院"),
        ],
    )

    assert "## 第一章 雨夜来信" in markdown
    assert "### S1 雨夜重逢" in markdown
    assert "## 第二章 旧影院" in markdown
    assert "### S2 银幕亮起" in markdown
    assert "【黄色标记】这句对白需要加强冲突" in markdown
    assert "> 备注：这里需要停顿。" in markdown
    assert "null" not in markdown
    assert "None" not in markdown
    assert "undefined" not in markdown
    assert "\n> \n" not in markdown


def _chapter(chapter_id: str, chapter_index: int, title: str) -> dict:
    return {
        "chapter_id": chapter_id,
        "chapter_index": chapter_index,
        "title": title,
        "content": f"{title} 原文。",
    }


def _editable_script_yaml() -> dict:
    return {
        "project": {"title": "雨夜来信"},
        "characters": [{"id": "lin_che", "name": "林澈"}],
        "locations": [{"id": "old_cinema", "name": "旧影院"}],
        "scenes": [
            {
                "id": "scene_1",
                "title": "雨夜重逢",
                "location_id": "old_cinema",
                "characters": ["lin_che"],
                "summary": "林澈在旧影院门口停下。",
                "source_ref": {
                    "chapter_id": "chapter_99",
                    "chapter_index": 99,
                    "chapter_title": "不存在章节",
                    "excerpt": "错误来源。",
                },
            },
            {
                "id": "scene_2",
                "title": "银幕亮起",
                "location_id": "old_cinema",
                "characters": ["lin_che"],
                "summary": "银幕亮起。",
                "source_ref": {
                    "chapter_id": "chapter_2",
                    "chapter_index": 2,
                    "chapter_title": "第二章 旧影院",
                    "excerpt": "银幕亮起。",
                },
            },
        ],
        "script": [
            {
                "id": "line_1",
                "scene_id": "scene_1",
                "type": "dialogue",
                "character_id": "lin_che",
                "content": "这句对白需要加强冲突",
                "highlight_color": "#fff3a3",
                "note": "这里需要停顿。",
            },
            {
                "id": "line_2",
                "scene_id": "scene_2",
                "type": "camera",
                "content": "镜头推近银幕。",
                "note": "",
            },
        ],
    }
