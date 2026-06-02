from __future__ import annotations

from typing import Any

from visualizer.protocol import Action, Highlights, OperationRequest, Step, Summary, VisualizationTrace, make_error_trace
from visualizer.simulators.base import get_capacity


def _state(data: list[Any], capacity: int, front: int = 0) -> dict[str, Any]:
    return {
        "kind": "queue",
        "items": [{"index": index, "value": value} for index, value in enumerate(data)],
        "front": front,
        "rear": front + len(data),
        "metadata": {"capacity": capacity, "circular": False},
    }


def _text(data: list[Any]) -> str:
    return "队头 [" + ", ".join(str(item) for item in data) + "] 队尾"


def _step(step_id: int, phase: str, title: str, description: str, data: list[Any], capacity: int, actions: list[Action], front: int = 0) -> Step:
    return Step(
        step_id=step_id,
        phase=phase,
        title=title,
        description=description,
        state=_state(data, capacity, front),
        highlights=Highlights(),
        actions=actions,
        message=description,
    )


def simulate_queue(request: OperationRequest) -> VisualizationTrace:
    if request.operation == "enqueue":
        return simulate_enqueue(request)
    return simulate_dequeue(request)


def simulate_enqueue(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    capacity = get_capacity(request)
    value = request.params.value
    initial = _text(data)
    if len(data) >= capacity:
        return make_error_trace(request, "QUEUE_OVERFLOW", "队列已满。", f"capacity = {capacity}，当前元素个数为 {len(data)}。", initial)

    result = data + [value]
    steps = [
        _step(1, "init", "初始状态", f"当前队列为 {_text(data)}。", data, capacity, []),
        _step(2, "check", "检查是否队满", "当前队列未满，可以入队。", data, capacity, [Action(type="check_condition", description="检查 rear < capacity。", target="rear")]),
        _step(3, "enqueue", "在 rear 位置写入元素", f"在 rear = {len(data)} 的位置写入 {value}。", result, capacity, [Action(type="enqueue", description="data[rear] = value。", target="rear", value=value)]),
        _step(4, "move", "rear 后移", f"rear 从 {len(data)} 后移到 {len(result)}。", result, capacity, [Action(type="move", description="rear = rear + 1。", target="rear", value=len(result))]),
        _step(5, "done", "入队完成", f"结果为 {_text(result)}。", result, capacity, []),
    ]
    return VisualizationTrace(
        title="队列入队演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(result), time_complexity="O(1)", space_complexity="O(1)"),
        steps=steps,
    )


def simulate_dequeue(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    capacity = get_capacity(request)
    initial = _text(data)
    if not data:
        return make_error_trace(request, "EMPTY_QUEUE_DEQUEUE", "空队列不能出队。", "front == rear，没有可读取的队头元素。", initial)

    popped = data[0]
    result = data[1:]
    steps = [
        _step(1, "init", "初始状态", f"当前队列为 {_text(data)}。", data, capacity, []),
        _step(2, "check", "检查是否队空", "当前队列非空，可以出队。", data, capacity, [Action(type="check_condition", description="检查 front != rear。", target="front/rear")]),
        _step(3, "dequeue", "读取 front 元素", f"读取队头元素 {popped}。", data, capacity, [Action(type="dequeue", description="value = data[front]。", target="front", value=popped)]),
        _step(4, "move", "front 后移", "front 后移一位，逻辑队头变为下一个元素。", result, capacity, [Action(type="move", description="front = front + 1。", target="front", value=1)], front=1),
        _step(5, "done", "出队完成", f"结果为 {_text(result)}。", result, capacity, []),
    ]
    return VisualizationTrace(
        title="队列出队演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(result), time_complexity="O(1)", space_complexity="O(1)"),
        steps=steps,
    )
