from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest
from visualizer.renderers.html_renderer import render_step_html


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


def test_quick_sort_shows_partition_pointers() -> None:
    request = OperationRequest.model_validate(
        {
            "structure": "sort",
            "operation": "quick_sort",
            "params": {"values": [4, 1, 3, 2]},
            "initial_state": {"data": [4, 1, 3, 2]},
        }
    )
    trace = dispatch(request)
    pointer_names = {
        pointer["name"]
        for step in trace.steps
        for pointer in step.state.get("pointers", [])
    }
    assert {"i", "j", "pivot"} <= pointer_names
    assert trace.summary.result == "[1, 2, 3, 4]"


def test_merge_sort_shows_merge_pointers_in_html() -> None:
    request = OperationRequest.model_validate(
        {
            "structure": "sort",
            "operation": "merge_sort",
            "params": {"values": [5, 2, 4, 1]},
            "initial_state": {"data": [5, 2, 4, 1]},
        }
    )
    trace = dispatch(request)
    pointer_step = next(
        step
        for step in trace.steps
        if {"i", "j", "k"} <= {pointer["name"] for pointer in step.state.get("pointers", [])}
    )
    html = render_step_html(pointer_step)
    assert "i" in html
    assert "j" in html
    assert "k" in html
