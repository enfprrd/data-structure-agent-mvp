from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest


def test_merge_sort() -> None:
    request = OperationRequest.model_validate(
        {
            "structure": "sort",
            "operation": "merge_sort",
            "params": {"values": [5, 2, 4, 1]},
            "initial_state": {"data": [5, 2, 4, 1]},
        }
    )
    trace = dispatch(request)
    assert trace.summary.result == "[1, 2, 4, 5]"
    assert trace.summary.time_complexity == "O(n log n)"
