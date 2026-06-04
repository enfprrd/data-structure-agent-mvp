from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest
from visualizer.renderers.html_renderer import render_step_html


def test_binary_tree_svg_renders_edges_and_empty_slots() -> None:
    request = OperationRequest.model_validate(
        {
            "structure": "binary_tree",
            "operation": "traverse_preorder",
            "initial_state": {"data": ["A", "B", "C", None, "D"], "metadata": {}},
        }
    )
    trace = dispatch(request)
    html = render_step_html(trace.steps[0])
    assert "<svg" in html
    assert "<line" in html
    assert "null" in html


def test_graph_svg_renders_edges_and_weights() -> None:
    request = OperationRequest.model_validate(
        {
            "structure": "graph",
            "operation": "build",
            "initial_state": {
                "data": [[0, 3, 0], [0, 0, 2], [0, 0, 0]],
                "metadata": {"vertices": ["A", "B", "C"]},
            },
        }
    )
    trace = dispatch(request)
    html = render_step_html(trace.steps[-1])
    assert "<svg" in html
    assert "<line" in html
    assert ">3<" in html
