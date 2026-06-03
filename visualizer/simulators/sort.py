from __future__ import annotations

from typing import Any

from visualizer.protocol import Action, CellHighlight, Highlights, OperationRequest, Step, Summary, VisualizationTrace


def _values(request: OperationRequest) -> list[Any]:
    return list(request.params.values or request.initial_state.data)


def _state(data: list[Any]) -> dict[str, Any]:
    return {
        "kind": "sequence",
        "cells": [{"index": index + 1, "value": value, "label": f"A[{index + 1}]"} for index, value in enumerate(data)],
        "metadata": {"length": len(data), "capacity": len(data)},
    }


def _text(data: list[Any]) -> str:
    return "[" + ", ".join(str(item) for item in data) + "]"


def _step(step_id: int, phase: str, title: str, description: str, data: list[Any], index: int | None = None, role: str = "current", action_type: str = "compare") -> Step:
    highlights = Highlights()
    if index is not None:
        highlights.cells.append(CellHighlight(index=index + 1, role=role))  # type: ignore[arg-type]
    return Step(
        step_id=step_id,
        phase=phase,
        title=title,
        description=description,
        state=_state(data),
        highlights=highlights,
        actions=[Action(type=action_type, description=description, target=f"A[{index + 1}]" if index is not None else "array")] if index is not None else [],
        message=description,
    )


def simulate_sort(request: OperationRequest) -> VisualizationTrace:
    if request.operation == "insertion_sort":
        return _insertion(request)
    if request.operation == "selection_sort":
        return _selection(request)
    if request.operation == "quick_sort":
        return _quick(request)
    return _bubble(request)


def _bubble(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做冒泡排序。", current)]
    for end in range(len(current) - 1, 0, -1):
        swapped = False
        for index in range(end):
            steps.append(_step(len(steps) + 1, "compare", "比较相邻元素", f"比较 A[{index + 1}]={current[index]} 和 A[{index + 2}]={current[index + 1]}。", current, index, "target"))
            if current[index] > current[index + 1]:
                current[index], current[index + 1] = current[index + 1], current[index]
                swapped = True
                steps.append(_step(len(steps) + 1, "shift", "交换相邻元素", f"两者逆序，交换后得到 {_text(current)}。", current, index + 1, "moved", "shift"))
        if not swapped:
            break
    steps.append(_step(len(steps) + 1, "done", "排序完成", f"最终有序序列为 {_text(current)}。", current, None, "success"))
    return _trace(request, "冒泡排序演示", data, current, "O(n^2)", "O(1)", steps)


def _insertion(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做直接插入排序。", current)]
    for i in range(1, len(current)):
        key = current[i]
        j = i - 1
        steps.append(_step(len(steps) + 1, "current", "取出待插入元素", f"取 A[{i + 1}]={key}，准备插入前面的有序区。", current, i, "target"))
        while j >= 0 and current[j] > key:
            current[j + 1] = current[j]
            steps.append(_step(len(steps) + 1, "shift", "后移元素", f"{current[j]} 大于 {key}，向后移动一位。", current, j + 1, "moved", "shift"))
            j -= 1
        current[j + 1] = key
        steps.append(_step(len(steps) + 1, "assign", "插入元素", f"把 {key} 放入 A[{j + 2}]，当前序列 {_text(current)}。", current, j + 1, "new", "assign"))
    return _trace(request, "直接插入排序演示", data, current, "O(n^2)", "O(1)", steps)


def _selection(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做简单选择排序。", current)]
    for i in range(len(current) - 1):
        min_index = i
        steps.append(_step(len(steps) + 1, "current", "确定本趟起点", f"从第 {i + 1} 位开始寻找最小元素。", current, i, "target"))
        for j in range(i + 1, len(current)):
            steps.append(_step(len(steps) + 1, "compare", "比较最小值", f"比较当前最小 {current[min_index]} 与 A[{j + 1}]={current[j]}。", current, j, "visited"))
            if current[j] < current[min_index]:
                min_index = j
                steps.append(_step(len(steps) + 1, "current", "更新最小位置", f"更新最小元素位置为第 {min_index + 1} 位。", current, min_index, "target"))
        if min_index != i:
            current[i], current[min_index] = current[min_index], current[i]
            steps.append(_step(len(steps) + 1, "shift", "交换到有序区末尾", f"交换第 {i + 1} 位和第 {min_index + 1} 位，得到 {_text(current)}。", current, i, "moved", "shift"))
    return _trace(request, "简单选择排序演示", data, current, "O(n^2)", "O(1)", steps)


def _quick(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做快速排序。", current)]

    def partition(low: int, high: int) -> int:
        pivot = current[low]
        steps.append(_step(len(steps) + 1, "current", "选择枢轴", f"选择 A[{low + 1}]={pivot} 作为枢轴。", current, low, "target"))
        i, j = low, high
        while i < j:
            while i < j and current[j] >= pivot:
                steps.append(_step(len(steps) + 1, "compare", "从右向左扫描", f"A[{j + 1}]={current[j]} >= pivot，继续左移。", current, j, "visited"))
                j -= 1
            if i < j:
                current[i] = current[j]
                steps.append(_step(len(steps) + 1, "assign", "填左侧空位", f"把 A[{j + 1}] 放到左侧空位 A[{i + 1}]。", current, i, "moved", "assign"))
                i += 1
            while i < j and current[i] <= pivot:
                steps.append(_step(len(steps) + 1, "compare", "从左向右扫描", f"A[{i + 1}]={current[i]} <= pivot，继续右移。", current, i, "visited"))
                i += 1
            if i < j:
                current[j] = current[i]
                steps.append(_step(len(steps) + 1, "assign", "填右侧空位", f"把 A[{i + 1}] 放到右侧空位 A[{j + 1}]。", current, j, "moved", "assign"))
                j -= 1
        current[i] = pivot
        steps.append(_step(len(steps) + 1, "assign", "枢轴归位", f"枢轴 {pivot} 放到第 {i + 1} 位。", current, i, "success", "assign"))
        return i

    def quick(low: int, high: int) -> None:
        if low < high:
            pivot_index = partition(low, high)
            quick(low, pivot_index - 1)
            quick(pivot_index + 1, high)

    quick(0, len(current) - 1)
    return _trace(request, "快速排序演示", data, current, "平均 O(n log n)，最坏 O(n^2)", "平均 O(log n)", steps)


def _trace(request: OperationRequest, title: str, initial: list[Any], result: list[Any], time_complexity: str, space_complexity: str, steps: list[Step]) -> VisualizationTrace:
    return VisualizationTrace(
        title=title,
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=_text(initial), result=_text(result), time_complexity=time_complexity, space_complexity=space_complexity),
        steps=steps,
    )
