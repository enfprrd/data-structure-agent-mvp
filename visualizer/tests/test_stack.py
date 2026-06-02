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
