from __future__ import annotations

from visualizer.dispatcher import dispatch
from visualizer.protocol import OperationRequest
from visualizer.renderers.html_renderer import render_step_html


def graph_req(operation: str, data: list[object], metadata: dict[str, object] | None = None) -> OperationRequest:
    return OperationRequest.model_validate(
        {
            "structure": "graph",
            "operation": operation,
            "initial_state": {"data": data, "metadata": metadata or {}},
        }
    )


def test_prim_minimum_spanning_tree() -> None:
    request = graph_req(
        "prim",
        [
            [0, 2, 3],
            [2, 0, 1],
            [3, 1, 0],
        ],
        {"vertices": ["A", "B", "C"], "directed": False, "start": "A"},
    )
    trace = dispatch(request)
    assert "总权值:3" in trace.summary.result
    assert trace.steps[-1].state["directed"] is False


def test_kruskal_minimum_spanning_tree() -> None:
    request = graph_req(
        "kruskal",
        [
            {"from": "A", "to": "B", "weight": 2},
            {"from": "A", "to": "C", "weight": 3},
            {"from": "B", "to": "C", "weight": 1},
        ],
        {"directed": False},
    )
    trace = dispatch(request)
    assert "总权值:3" in trace.summary.result


def test_floyd_all_pairs_shortest_paths() -> None:
    request = graph_req(
        "floyd",
        [
            [0, 3, 10],
            [0, 0, 2],
            [0, 0, 0],
        ],
        {"vertices": ["A", "B", "C"]},
    )
    trace = dispatch(request)
    assert "A: 0, 3, 5" in trace.summary.result


def test_topological_sort() -> None:
    request = graph_req(
        "topological_sort",
        [
            {"from": "A", "to": "B"},
            {"from": "A", "to": "C"},
            {"from": "B", "to": "D"},
            {"from": "C", "to": "D"},
        ],
    )
    trace = dispatch(request)
    assert trace.summary.result == "A -> B -> C -> D"


def test_undirected_graph_svg_has_edges_without_arrows() -> None:
    request = graph_req(
        "prim",
        [
            [0, 2, 3],
            [2, 0, 1],
            [3, 1, 0],
        ],
        {"vertices": ["A", "B", "C"], "directed": False},
    )
    trace = dispatch(request)
    html = render_step_html(trace.steps[-1])
    assert "<line" in html
    assert "marker-end" not in html


def test_graph_matrix_preserves_numeric_vertex_labels() -> None:
    request = graph_req(
        "dfs",
        [
            [0, 1, 1],
            [1, 0, 0],
            [1, 0, 0],
        ],
        {"vertices": ["1", "2", "3"], "directed": False, "start": "1"},
    )
    trace = dispatch(request)
    assert trace.steps[-1].state["nodes"] == ["1", "2", "3"]
    assert trace.summary.result == "1 -> 2 -> 3"
