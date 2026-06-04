from __future__ import annotations

from app import build_effective_question


class FakeClient:
    def chat(self, messages: list[dict[str, str]], temperature: float = 0, max_tokens: int = 120) -> str:
        return "演示归并排序的二路归并过程"


def test_ambiguous_demo_followup_uses_llm_rewrite() -> None:
    messages = [
        {"role": "user", "content": "归并算法的时间空间复杂度是多少"},
        {"role": "assistant", "content": "归并排序时间复杂度 O(n log n)，空间复杂度 O(n)。"},
    ]
    effective = build_effective_question("演示一下呗", messages, FakeClient())  # type: ignore[arg-type]
    assert effective == "演示归并排序的二路归并过程"
