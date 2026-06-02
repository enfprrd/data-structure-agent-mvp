from __future__ import annotations

from typing import Protocol

from visualizer.protocol import OperationRequest, VisualizationTrace


class Simulator(Protocol):
    def __call__(self, request: OperationRequest) -> VisualizationTrace:
        ...


def get_capacity(request: OperationRequest, default: int = 10) -> int:
    metadata = request.initial_state.metadata
    return int(request.params.capacity or metadata.get("capacity") or default)


def get_index_base(request: OperationRequest) -> int:
    return int(request.initial_state.metadata.get("index_base", 1))
