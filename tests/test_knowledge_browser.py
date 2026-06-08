from __future__ import annotations

from app import _search_knowledge, _split_knowledge_sections


def test_split_knowledge_sections() -> None:
    text = "# 图\n\n简介\n\n## DFS\n\n深度优先遍历\n\n## BFS\n\n广度优先遍历"
    sections = _split_knowledge_sections(text)
    assert len(sections) == 3
    assert "DFS" in sections[1]


def test_search_knowledge_sections(tmp_path) -> None:
    graph = tmp_path / "graph.md"
    graph.write_text("# 图\n\n## DFS\n\n深度优先遍历使用 visited 数组。", encoding="utf-8")
    stack = tmp_path / "stack.md"
    stack.write_text("# 栈\n\n## 入栈\n\n元素进入栈顶。", encoding="utf-8")

    matches = _search_knowledge("visited", [graph, stack])
    assert len(matches) == 1
    assert matches[0]["source"] == "graph.md"
