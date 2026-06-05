from __future__ import annotations

from app import get_recent_rag_keywords, retrieve_with_rag_memory
from rag import MarkdownKeywordRetriever


def test_recent_rag_keywords_keep_latest_unique_terms() -> None:
    messages = [
        {"role": "assistant", "content": "旧回答", "rag_keywords": ["链表", "结点"]},
        {"role": "assistant", "content": "新回答", "rag_keywords": ["图", "DFS", "顶点", "结点"]},
    ]
    assert get_recent_rag_keywords(messages, limit=4) == ["图", "DFS", "顶点", "结点"]


def test_rag_memory_boosts_previous_graph_topic_for_short_followup(tmp_path) -> None:
    (tmp_path / "graph.md").write_text(
        "# 图\n\n## 深度优先遍历 DFS\n\n图的 DFS 从顶点出发，使用 visited 数组避免重复访问。\n",
        encoding="utf-8",
    )
    (tmp_path / "linked_list.md").write_text(
        "# 链表\n\n## 单链表结点\n\n单链表结点包含 data 和 next 指针。\n",
        encoding="utf-8",
    )

    retriever = MarkdownKeywordRetriever(tmp_path)
    contexts = retrieve_with_rag_memory(
        retriever,
        "如果是更多的结点呢",
        ["图", "DFS", "深度优先遍历", "顶点"],
        top_k=1,
    )

    assert contexts
    assert contexts[0]["source"].startswith("graph.md")
