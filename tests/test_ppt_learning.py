from __future__ import annotations

from io import BytesIO

import pytest

from ppt_learning import SlideCard, build_context_pack, parse_pptx_to_slide_cards


pptx = pytest.importorskip("pptx")


def test_parse_pptx_extracts_text_tables_and_notes() -> None:
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "栈的基本概念"
    slide.placeholders[1].text = "栈是只允许在一端进行插入和删除的线性表。\n后进先出。"

    table_shape = slide.shapes.add_table(2, 2, 0, 0, 3000000, 1000000)
    table = table_shape.table
    table.cell(0, 0).text = "操作"
    table.cell(0, 1).text = "含义"
    table.cell(1, 0).text = "push"
    table.cell(1, 1).text = "入栈"

    slide.notes_slide.notes_text_frame.text = "课堂备注：注意栈顶指针变化。"

    output = BytesIO()
    presentation.save(output)

    cards = parse_pptx_to_slide_cards("deck-a", output.getvalue(), client=None)

    assert len(cards) == 1
    assert cards[0].deck_id == "deck-a"
    assert cards[0].slide_id == 1
    assert cards[0].title == "栈的基本概念"
    assert "后进先出" in cards[0].raw_text
    assert cards[0].tables == [[["操作", "含义"], ["push", "入栈"]]]
    assert "栈顶指针" in cards[0].notes
    assert cards[0].concept_type == "text"
    assert cards[0].summary


def test_parse_pptx_marks_blank_slide_as_text_missing() -> None:
    presentation = pptx.Presentation()
    presentation.slides.add_slide(presentation.slide_layouts[6])
    output = BytesIO()
    presentation.save(output)

    cards = parse_pptx_to_slide_cards("deck-b", output.getvalue(), client=None)

    assert cards[0].concept_type == "text_missing"
    assert cards[0].keywords == ["text_missing"]
    assert "不猜测图片信息" in cards[0].summary


def test_context_pack_is_page_aware_and_retrieves_related_slides() -> None:
    cards = [
        SlideCard("deck", 1, "线性表", "线性表定义", "", summary="介绍线性结构", keywords=["线性表"]),
        SlideCard("deck", 2, "栈", "栈是后进先出的线性表", "", summary="栈的定义", keywords=["栈", "后进先出"]),
        SlideCard("deck", 3, "队列", "队列是先进先出的线性表", "", summary="队列的定义", keywords=["队列", "先进先出"]),
    ]

    pack = build_context_pack(cards, current_slide_id=2, question="队列和栈有什么区别？")

    assert pack.current_slide.slide_id == 2
    assert pack.prev_slide == {
        "slide_id": 1,
        "title": "线性表",
        "summary": "介绍线性结构",
        "keywords": ["线性表"],
        "concept_type": "unknown",
    }
    assert pack.next_slide and pack.next_slide["slide_id"] == 3
    assert [item["slide_id"] for item in pack.deck_outline] == [1, 2, 3]
    assert [slide.slide_id for slide in pack.retrieved_slides] == [3]
