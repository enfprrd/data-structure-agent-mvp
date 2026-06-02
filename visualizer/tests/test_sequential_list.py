from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest


def req(operation: str, params: dict[str, object], data: list[int]) -> OperationRequest:
    return OperationRequest.model_validate(
        {
            "structure": "sequential_list",
            "operation": operation,
            "params": params,
            "initial_state": {"data": data, "metadata": {"capacity": 10, "index_base": 1}},
        }
    )


def test_insert_middle() -> None:
    trace = dispatch(req("insert", {"position": 2, "value": 9}, [1, 2, 3]))
    assert trace.summary.result == "[1, 9, 2, 3]"
    assert any(step.phase == "shift" for step in trace.steps)


def test_insert_tail() -> None:
    trace = dispatch(req("insert", {"position": 4, "value": 9}, [1, 2, 3]))
    assert trace.summary.result == "[1, 2, 3, 9]"


def test_insert_invalid_position() -> None:
    trace = dispatch(req("insert", {"position": 6, "value": 9}, [1, 2, 3]))
    assert trace.errors[0].code == "INVALID_POSITION"


def test_delete_middle() -> None:
    trace = dispatch(req("delete", {"position": 2}, [1, 2, 3]))
    assert trace.summary.result == "[1, 3]"


def test_delete_empty() -> None:
    trace = dispatch(req("delete", {"position": 1}, []))
    assert trace.errors[0].code == "EMPTY_LIST_DELETE"


def test_search_found() -> None:
    trace = dispatch(req("search", {"target": 2}, [1, 2, 3]))
    assert trace.summary.result == "找到，位置为 2"


def test_search_not_found() -> None:
    trace = dispatch(req("search", {"target": 9}, [1, 2, 3]))
    assert trace.warnings[0].code == "NOT_FOUND"
