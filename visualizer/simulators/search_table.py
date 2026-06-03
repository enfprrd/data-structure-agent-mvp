from __future__ import annotations

from typing import Any

from visualizer.protocol import Action, CellHighlight, DSVPWarning, Highlights, OperationRequest, Step, Summary, VisualizationTrace


def _state(data: list[Any]) -> dict[str, Any]:
    return {
        "kind": "sequence",
        "cells": [{"index": index + 1, "value": value, "label": f"A[{index + 1}]"} for index, value in enumerate(data)],
        "metadata": {"length": len(data), "capacity": len(data)},
    }


def _text(data: list[Any]) -> str:
    return "[" + ", ".join(str(item) for item in data) + "]"


def _step(step_id: int, title: str, description: str, data: list[Any], index: int | None = None, role: str = "current") -> Step:
    highlights = Highlights()
    if index is not None:
        highlights.cells.append(CellHighlight(index=index + 1, role=role))  # type: ignore[arg-type]
    return Step(
        step_id=step_id,
        phase="compare" if index is not None else "init",
        title=title,
        description=description,
        state=_state(data),
        highlights=highlights,
        actions=[Action(type="compare", description=description, target=f"A[{index + 1}]" if index is not None else "table")] if index is not None else [],
        code_refs=[],
        message=description,
    )


def simulate_search_table(request: OperationRequest) -> VisualizationTrace:
    if request.operation == "binary_search":
        return simulate_binary_search(request)
    return simulate_sequential_search(request)


def simulate_sequential_search(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    target = request.params.target
    steps = [_step(1, "初始查找表", f"从第一个元素开始顺序查找目标 {target}。", data)]
    found: int | None = None
    for index, value in enumerate(data):
        ok = value == target
        steps.append(_step(len(steps) + 1, f"比较第 {index + 1} 个元素", f"比较 A[{index + 1}] = {value} 与目标 {target}。", data, index, "success" if ok else "visited"))
        if ok:
            found = index + 1
            break
    warnings: list[DSVPWarning] = []
    result = f"找到，位置为 {found}" if found is not None else "未找到"
    if found is None:
        warnings.append(DSVPWarning(code="NOT_FOUND", message="查找失败", detail=f"查找表中没有 {target}。"))
    return VisualizationTrace(
        title="顺序查找演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=_text(data), result=result, time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
        warnings=warnings,
    )


def simulate_binary_search(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    target = request.params.target
    steps = [_step(1, "初始有序表", f"在有序表 {_text(data)} 中折半查找 {target}。", data)]
    low, high = 0, len(data) - 1
    found: int | None = None
    while low <= high:
        mid = (low + high) // 2
        value = data[mid]
        ok = value == target
        steps.append(
            _step(
                len(steps) + 1,
                f"检查 mid = {mid + 1}",
                f"low={low + 1}，high={high + 1}，mid={mid + 1}，比较 A[{mid + 1}] = {value} 与目标 {target}。",
                data,
                mid,
                "success" if ok else "target",
            )
        )
        if ok:
            found = mid + 1
            break
        if value < target:  # type: ignore[operator]
            low = mid + 1
        else:
            high = mid - 1
    warnings: list[DSVPWarning] = []
    result = f"找到，位置为 {found}" if found is not None else "未找到"
    if found is None:
        warnings.append(DSVPWarning(code="NOT_FOUND", message="查找失败", detail=f"有序表中没有 {target}。"))
    return VisualizationTrace(
        title="折半查找演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=_text(data), result=result, time_complexity="O(log n)", space_complexity="O(1)"),
        steps=steps,
        warnings=warnings,
    )
