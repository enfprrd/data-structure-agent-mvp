from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest


def req(operation: str, params: dict[str, object], data: list[int]) -> OperationRequest:
    return OperationRequest.model_validate(
        {
            "structure": "singly_linked_list",
            "operation": operation,
            "params": params,
            "initial_state": {"data": data, "metadata": {"use_head_node": True, "index_base": 1}},
        }
    )


def test_insert_middle() -> None:
    trace = dispatch(req("insert", {"position": 2, "value": 9}, [3, 5, 7]))
    assert trace.summary.result == "head -> 3 -> 9 -> 5 -> 7 -> NULL"
    assert any("s->next" in action.description for step in trace.steps for action in step.actions)


def test_delete_middle() -> None:
    trace = dispatch(req("delete", {"position": 2}, [3, 5, 7]))
    assert trace.summary.result == "head -> 3 -> 7 -> NULL"


def test_search_found() -> None:
    trace = dispatch(req("search", {"target": 5}, [3, 5, 7]))
    assert trace.summary.result == "找到，位置为 2"


def test_search_not_found() -> None:
    trace = dispatch(req("search", {"target": 9}, [3, 5, 7]))
    assert trace.warnings[0].code == "NOT_FOUND"


def test_insert_empty() -> None:
    trace = dispatch(req("insert", {"position": 1, "value": 9}, []))
    assert trace.summary.result == "head -> 9 -> NULL"
