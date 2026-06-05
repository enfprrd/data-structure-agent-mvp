from __future__ import annotations

from app import build_effective_question


class FakeClient:
    def chat(self, messages: list[dict[str, str]], temperature: float = 0, max_tokens: int = 120) -> str:
        return "演示归并排序的二路归并过程"


class GraphFollowupClient:
    def chat(self, messages: list[dict[str, str]], temperature: float = 0, max_tokens: int = 120) -> str:
        assert "图" in messages[-1]["content"]
        assert "更多的结点" in messages[-1]["content"]
        return "图的 DFS 如果有更多顶点时如何遍历和扩展"


def test_ambiguous_demo_followup_uses_llm_rewrite() -> None:
    messages = [
        {"role": "user", "content": "归并算法的时间空间复杂度是多少"},
        {"role": "assistant", "content": "归并排序时间复杂度 O(n log n)，空间复杂度 O(n)。"},
    ]
    effective = build_effective_question("演示一下呗", messages, FakeClient())  # type: ignore[arg-type]
    assert effective == "演示归并排序的二路归并过程"


def test_short_graph_node_followup_uses_llm_rewrite() -> None:
    messages = [
        {"role": "user", "content": "演示一下图的dfs"},
        {"role": "assistant", "content": "图 DFS 从顶点 0 出发，访问顺序是 0 -> 1 -> 3 -> 4 -> 2。"},
    ]
    effective = build_effective_question("如果是更多的结点呢", messages, GraphFollowupClient())  # type: ignore[arg-type]
    assert effective == "图的 DFS 如果有更多顶点时如何遍历和扩展"


def test_ambiguous_followup_without_llm_does_not_guess_locally() -> None:
    messages = [
        {"role": "user", "content": "演示一下图的dfs"},
        {"role": "assistant", "content": "图 DFS 从顶点 0 出发。"},
    ]
    effective = build_effective_question("如果是更多的结点呢", messages, None)
    assert effective == "如果是更多的结点呢"
