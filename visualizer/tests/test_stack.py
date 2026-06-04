from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest


def req(operation: str, params: dict[str, object], data: list[int]) -> OperationRequest:
    return OperationRequest.model_validate(
        {"structure": "stack", "operation": operation, "params": params, "initial_state": {"data": data, "metadata": {"capacity": 10}}}
    )


def test_push() -> None:
    trace = dispatch(req("push", {"value": 3}, [1, 2]))
    assert trace.steps[-1].state["top"] == 2


def test_pop() -> None:
    trace = dispatch(req("pop", {}, [1, 2]))
    assert trace.steps[-1].state["top"] == 0


def test_empty_pop() -> None:
    trace = dispatch(req("pop", {}, []))
    assert trace.errors[0].code == "EMPTY_STACK_POP"


def test_postfix_evaluation() -> None:
    trace = dispatch(req("postfix_evaluation", {"values": ["3", "5", "2", "*", "+"]}, []))
    assert trace.summary.result == "13"
    assert trace.steps[-1].state["stacks"]["stack"] == [13]


def test_bracket_matching() -> None:
    trace = dispatch(req("bracket_matching", {"value": "([{}])"}, []))
    assert trace.summary.result == "匹配成功"
    assert trace.steps[-1].state["stacks"]["stack"] == []


def test_hanoi_recursive() -> None:
    trace = dispatch(req("hanoi_recursive", {"value": 3}, []))
    assert trace.steps[-1].state["stacks"]["C"] == [3, 2, 1]


def test_next_greater_element() -> None:
    trace = dispatch(req("next_greater_element", {}, [2, 1, 2, 4, 3]))
    assert trace.summary.result == "[4, 2, 4, -1, -1]"
