from __future__ import annotations

from typing import Any

from visualizer.protocol import (
    Action,
    CellHighlight,
    DSVPWarning,
    Highlights,
    OperationRequest,
    Step,
    Summary,
    VisualizationTrace,
    make_error_trace,
)
from visualizer.simulators.base import get_capacity, get_index_base


def _state(data: list[Any], capacity: int, index_base: int) -> dict[str, Any]:
    return {
        "kind": "sequence",
        "cells": [
            {"index": index + index_base, "value": value, "label": f"L[{index + index_base}]"}
            for index, value in enumerate(data)
        ],
        "metadata": {"length": len(data), "capacity": capacity, "index_base": index_base},
    }


def _text(data: list[Any]) -> str:
    return "[" + ", ".join(str(item) for item in data) + "]"


def _step(
    step_id: int,
    phase: str,
    title: str,
    description: str,
    data: list[Any],
    capacity: int,
    index_base: int,
    actions: list[Action],
    highlight_index: int | None = None,
    role: str = "current",
    message: str = "",
) -> Step:
    highlights = Highlights()
    if highlight_index is not None:
        highlights.cells.append(CellHighlight(index=highlight_index, role=role))  # type: ignore[arg-type]
    return Step(
        step_id=step_id,
        phase=phase,
        title=title,
        description=description,
        state=_state(data, capacity, index_base),
        highlights=highlights,
        actions=actions,
        code_refs=[],
        message=message or description,
    )


def simulate_sequential_list(request: OperationRequest) -> VisualizationTrace:
    if request.operation == "insert":
        return simulate_insert(request)
    if request.operation == "delete":
        return simulate_delete(request)
    return simulate_search(request)


def simulate_insert(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    capacity = get_capacity(request)
    index_base = get_index_base(request)
    position = int(request.params.position or 0)
    value = request.params.value
    initial = _text(data)

    if len(data) >= capacity:
        return make_error_trace(request, "OVERFLOW", "顺序表已满。", f"capacity = {capacity}，当前 length = {len(data)}。", initial)
    if position < 1 or position > len(data) + 1:
        return make_error_trace(
            request,
            "INVALID_POSITION",
            "插入位置不合法。",
            f"当前线性表长度为 {len(data)}，合法插入位置为 1 到 {len(data) + 1}，但收到 position = {position}。",
            initial,
        )

    steps: list[Step] = []
    current = list(data)
    steps.append(
        _step(
            1,
            "init",
            "初始状态",
            f"当前顺序表为 {_text(current)}，准备在第 {position} 位插入 {value}。",
            current,
            capacity,
            index_base,
            [],
        )
    )
    steps.append(
        _step(
            2,
            "check",
            "检查插入位置",
            f"顺序表长度为 {len(data)}，第 {position} 位在合法范围内。",
            current,
            capacity,
            index_base,
            [Action(type="check_condition", description="检查 1 <= position <= length + 1 且表未满。", target="position")],
            position,
            "target",
        )
    )

    current.append(current[-1] if current else value)
    step_id = 3
    for source in range(len(data) - 1, position - 2, -1):
        current[source + 1] = current[source]
        shown_position = source + 1
        steps.append(
            _step(
                step_id,
                "shift",
                f"后移第 {shown_position} 位元素",
                f"将第 {shown_position} 位元素 {current[source]} 向后移动一位，给插入位置腾空间。",
                current,
                capacity,
                index_base,
                [Action(type="shift", description="从后向前移动，避免覆盖尚未移动的元素。", target=f"L[{shown_position + 1}]", value=current[source])],
                shown_position + 1,
                "moved",
            )
        )
        step_id += 1

    current[position - 1] = value
    steps.append(
        _step(
            step_id,
            "assign",
            "写入新元素",
            f"将 {value} 写入第 {position} 位。",
            current,
            capacity,
            index_base,
            [Action(type="assign", description="L.data[position - 1] = value。", target=f"L[{position}]", value=value)],
            position,
            "new",
        )
    )
    step_id += 1
    steps.append(
        _step(
            step_id,
            "done",
            "插入完成",
            f"length 加 1，顺序表变为 {_text(current)}。",
            current,
            capacity,
            index_base,
            [Action(type="assign", description="length = length + 1。", target="length", value=len(current))],
            position,
            "success",
        )
    )

    return VisualizationTrace(
        title="顺序表按位插入演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(current), time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
    )


def simulate_delete(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    capacity = get_capacity(request)
    index_base = get_index_base(request)
    position = int(request.params.position or 0)
    initial = _text(data)

    if not data:
        return make_error_trace(request, "EMPTY_LIST_DELETE", "空表不能删除。", "当前顺序表 length = 0，没有可删除元素。", initial)
    if position < 1 or position > len(data):
        return make_error_trace(
            request,
            "INVALID_POSITION",
            "删除位置不合法。",
            f"当前线性表长度为 {len(data)}，合法删除位置为 1 到 {len(data)}，但收到 position = {position}。",
            initial,
        )

    current = list(data)
    deleted = current[position - 1]
    steps: list[Step] = [
        _step(1, "init", "初始状态", f"当前顺序表为 {_text(current)}，准备删除第 {position} 位元素 {deleted}。", current, capacity, index_base, []),
        _step(2, "check", "检查删除位置", f"第 {position} 位在合法范围内。", current, capacity, index_base, [Action(type="check_condition", description="检查 1 <= position <= length。", target="position")], position, "target"),
    ]
    step_id = 3
    for source in range(position, len(data)):
        current[source - 1] = current[source]
        steps.append(
            _step(
                step_id,
                "shift",
                f"前移第 {source + 1} 位元素",
                f"将第 {source + 1} 位元素 {current[source]} 向前移动一位，覆盖被删位置后的空缺。",
                current,
                capacity,
                index_base,
                [Action(type="shift", description="后继元素依次前移。", target=f"L[{source}]", value=current[source])],
                source,
                "moved",
            )
        )
        step_id += 1
    current = current[:-1]
    steps.append(
        _step(
            step_id,
            "done",
            "删除完成",
            f"length 减 1，删除值为 {deleted}，顺序表变为 {_text(current)}。",
            current,
            capacity,
            index_base,
            [Action(type="assign", description="length = length - 1。", target="length", value=len(current))],
            None,
            "success",
        )
    )
    return VisualizationTrace(
        title="顺序表按位删除演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(current), time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
    )


def simulate_search(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    capacity = get_capacity(request)
    index_base = get_index_base(request)
    target = request.params.target
    initial = _text(data)
    steps: list[Step] = [
        _step(1, "init", "初始状态", f"从第一个元素开始顺序查找 {target}。", data, capacity, index_base, [])
    ]
    found_index: int | None = None
    for index, value in enumerate(data, start=1):
        success = value == target
        if success:
            found_index = index
        steps.append(
            _step(
                len(steps) + 1,
                "compare",
                f"比较第 {index} 位",
                f"比较 L[{index}] = {value} 与目标 {target}。",
                data,
                capacity,
                index_base,
                [Action(type="compare", description="按值查找逐个比较元素。", target=f"L[{index}]", value=value)],
                index,
                "success" if success else "visited",
                "查找成功。" if success else "继续向后查找。",
            )
        )
        if success:
            break

    warnings: list[DSVPWarning] = []
    result = f"找到，位置为 {found_index}" if found_index is not None else "未找到"
    if found_index is None:
        warnings.append(DSVPWarning(code="NOT_FOUND", message="查找值不存在。", detail=f"顺序表中没有值 {target}。"))
        steps.append(
            _step(
                len(steps) + 1,
                "done",
                "查找结束",
                f"扫描结束，未找到 {target}。",
                data,
                capacity,
                index_base,
                [],
                None,
                "error",
            )
        )

    return VisualizationTrace(
        title="顺序表按值查找演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=result, time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
        warnings=warnings,
    )
