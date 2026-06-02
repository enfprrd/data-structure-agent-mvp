from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest


def req(operation: str, params: dict[str, object], data: list[int]) -> OperationRequest:
    return OperationRequest.model_validate(
        {"structure": "queue", "operation": operation, "params": params, "initial_state": {"data": data, "metadata": {"capacity": 10}}}
    )


def test_enqueue() -> None:
    trace = dispatch(req("enqueue", {"value": 3}, [1, 2]))
    assert trace.steps[-1].state["rear"] == 3


def test_dequeue() -> None:
    trace = dispatch(req("dequeue", {}, [1, 2]))
    assert trace.summary.result == "队头 [2] 队尾"


def test_empty_dequeue() -> None:
    trace = dispatch(req("dequeue", {}, []))
    assert trace.errors[0].code == "EMPTY_QUEUE_DEQUEUE"
