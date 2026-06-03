from __future__ import annotations

from visualizer.protocol import OperationRequest, VisualizationTrace, is_supported_demo_pair, make_unsupported_trace
from visualizer.simulators.binary_tree import simulate_binary_tree
from visualizer.simulators.graph import simulate_graph
from visualizer.simulators.queue import simulate_queue
from visualizer.simulators.search_table import simulate_search_table
from visualizer.simulators.sequential_list import simulate_sequential_list
from visualizer.simulators.singly_linked_list import simulate_singly_linked_list
from visualizer.simulators.sort import simulate_sort
from visualizer.simulators.stack import simulate_stack


def dispatch(request: OperationRequest) -> VisualizationTrace:
    if not is_supported_demo_pair(request.structure, request.operation):
        return make_unsupported_trace(request)

    simulators = {
        "sequential_list": simulate_sequential_list,
        "singly_linked_list": simulate_singly_linked_list,
        "stack": simulate_stack,
        "queue": simulate_queue,
        "binary_tree": simulate_binary_tree,
        "graph": simulate_graph,
        "search_table": simulate_search_table,
        "sort": simulate_sort,
    }
    return simulators[request.structure](request)
