from __future__ import annotations

from visualizer.protocol import OperationRequest, VisualizationTrace
from visualizer.simulators.queue import simulate_queue
from visualizer.simulators.sequential_list import simulate_sequential_list
from visualizer.simulators.singly_linked_list import simulate_singly_linked_list
from visualizer.simulators.stack import simulate_stack


def dispatch(request: OperationRequest) -> VisualizationTrace:
    simulators = {
        "sequential_list": simulate_sequential_list,
        "singly_linked_list": simulate_singly_linked_list,
        "stack": simulate_stack,
        "queue": simulate_queue,
    }
    return simulators[request.structure](request)
