from __future__ import annotations

from typing import Any

from visualizer.protocol import Action, Highlights, OperationRequest, Step, Summary, VisualizationTrace, make_error_trace
from visualizer.simulators.base import get_capacity


def _state(data: list[Any], capacity: int) -> dict[str, Any]:
    return {
        "kind": "stack",
        "items": [{"index": index, "value": value} for index, value in enumerate(data)],
        "top": len(data) - 1,
        "metadata": {"capacity": capacity},
    }


def _text(data: list[Any]) -> str:
    return "栈底 [" + ", ".join(str(item) for item in data) + "] 栈顶"


def _step(step_id: int, phase: str, title: str, description: str, data: list[Any], capacity: int, actions: list[Action]) -> Step:
    return Step(
        step_id=step_id,
        phase=phase,
        title=title,
        description=description,
        state=_state(data, capacity),
        highlights=Highlights(),
        actions=actions,
        message=description,
    )


def simulate_stack(request: OperationRequest) -> VisualizationTrace:
    if request.operation == "push":
        return simulate_push(request)
    return simulate_pop(request)


def simulate_push(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    capacity = get_capacity(request)
    value = request.params.value
    initial = _text(data)
    if len(data) >= capacity:
        return make_error_trace(request, "STACK_OVERFLOW", "栈已满。", f"capacity = {capacity}，当前元素个数为 {len(data)}。", initial)

    result = data + [value]
    steps = [
        _step(1, "init", "初始状态", f"当前栈为 {_text(data)}。", data, capacity, []),
        _step(2, "check", "检查是否栈满", "当前栈未满，可以入栈。", data, capacity, [Action(type="check_condition", description="检查 top < capacity - 1。", target="top")]),
        _step(3, "move", "top 后移", f"top 从 {len(data) - 1} 后移到 {len(data)}。", data, capacity, [Action(type="move", description="top = top + 1。", target="top", value=len(data))]),
        _step(4, "push", "写入栈顶元素", f"将 {value} 写入新的栈顶位置。", result, capacity, [Action(type="push", description="data[top] = value。", target="top", value=value)]),
        _step(5, "done", "入栈完成", f"结果为 {_text(result)}。", result, capacity, []),
    ]
    return VisualizationTrace(
        title="栈入栈演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(result), time_complexity="O(1)", space_complexity="O(1)"),
        steps=steps,
    )


def simulate_pop(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    capacity = get_capacity(request)
    initial = _text(data)
    if not data:
        return make_error_trace(request, "EMPTY_STACK_POP", "空栈不能出栈。", "top = -1，没有可读取的栈顶元素。", initial)

    popped = data[-1]
    result = data[:-1]
    steps = [
        _step(1, "init", "初始状态", f"当前栈为 {_text(data)}。", data, capacity, []),
        _step(2, "check", "检查是否栈空", "当前栈非空，可以出栈。", data, capacity, [Action(type="check_condition", description="检查 top != -1。", target="top")]),
        _step(3, "pop", "读取栈顶元素", f"读取栈顶元素 {popped}。", data, capacity, [Action(type="pop", description="value = data[top]。", target="top", value=popped)]),
        _step(4, "move", "top 前移", f"top 从 {len(data) - 1} 前移到 {len(result) - 1}。", result, capacity, [Action(type="move", description="top = top - 1。", target="top", value=len(result) - 1)]),
        _step(5, "done", "出栈完成", f"结果为 {_text(result)}。", result, capacity, []),
    ]
    return VisualizationTrace(
        title="栈出栈演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(result), time_complexity="O(1)", space_complexity="O(1)"),
        steps=steps,
    )
