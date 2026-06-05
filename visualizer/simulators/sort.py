from __future__ import annotations

from typing import Any

from visualizer.protocol import Action, CellHighlight, Highlights, OperationRequest, PointerHighlight, Step, Summary, VisualizationTrace


def _values(request: OperationRequest) -> list[Any]:
    return list(request.params.values or request.initial_state.data)


def _state(data: list[Any], pointers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "kind": "sequence",
        "cells": [{"index": index + 1, "value": value, "label": f"A[{index + 1}]"} for index, value in enumerate(data)],
        "metadata": {"length": len(data), "capacity": len(data)},
        "pointers": pointers or [],
    }


def _text(data: list[Any]) -> str:
    return "[" + ", ".join(str(item) for item in data) + "]"


def _ptr(name: str, index: int | None, value: Any | None = None) -> dict[str, Any]:
    target = "空" if index is None else f"A[{index + 1}]"
    pointer = {"name": name, "target": target}
    if value is not None:
        pointer["value"] = value
    return pointer


def _step(
    step_id: int,
    phase: str,
    title: str,
    description: str,
    data: list[Any],
    index: int | None = None,
    role: str = "current",
    action_type: str = "compare",
    pointers: list[dict[str, Any]] | None = None,
    pointer_roles: dict[str, str] | None = None,
    code_refs: list[str] | None = None,
) -> Step:
    highlights = Highlights()
    if index is not None:
        highlights.cells.append(CellHighlight(index=index + 1, role=role))  # type: ignore[arg-type]
    for name, pointer_role in (pointer_roles or {}).items():
        highlights.pointers.append(PointerHighlight(name=name, role=pointer_role))  # type: ignore[arg-type]
    return Step(
        step_id=step_id,
        phase=phase,
        title=title,
        description=description,
        state=_state(data, pointers),
        highlights=highlights,
        actions=[Action(type=action_type, description=description, target=f"A[{index + 1}]" if index is not None else "array")] if index is not None else [],
        code_refs=code_refs or [],
        message=description,
    )


def simulate_sort(request: OperationRequest) -> VisualizationTrace:
    if request.operation == "insertion_sort":
        return _insertion(request)
    if request.operation == "selection_sort":
        return _selection(request)
    if request.operation == "quick_sort":
        return _quick(request)
    if request.operation == "merge_sort":
        return _merge(request)
    return _bubble(request)


def _bubble(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做冒泡排序。", current)]
    for end in range(len(current) - 1, 0, -1):
        swapped = False
        for index in range(end):
            pointers = [_ptr("i", index, current[index]), _ptr("i+1", index + 1, current[index + 1]), _ptr("end", end)]
            steps.append(_step(len(steps) + 1, "compare", "比较相邻元素", f"比较 A[{index + 1}]={current[index]} 和 A[{index + 2}]={current[index + 1]}。", current, index, "target", pointers=pointers, pointer_roles={"i": "target", "i+1": "visited"}, code_refs=["if (A[i] > A[i + 1]) swap(A[i], A[i + 1]);"]))
            if current[index] > current[index + 1]:
                current[index], current[index + 1] = current[index + 1], current[index]
                swapped = True
                steps.append(_step(len(steps) + 1, "shift", "交换相邻元素", f"两者逆序，交换后得到 {_text(current)}。", current, index + 1, "moved", "shift", pointers=pointers, pointer_roles={"i": "moved", "i+1": "moved"}, code_refs=["temp = A[i]; A[i] = A[i + 1]; A[i + 1] = temp;"]))
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
        steps.append(_step(len(steps) + 1, "current", "取出待插入元素", f"取 A[{i + 1}]={key}，准备插入前面的有序区。", current, i, "target", pointers=[_ptr("i", i, key), _ptr("j", j, current[j])], pointer_roles={"i": "target"}, code_refs=["key = A[i]; j = i - 1;"]))
        while j >= 0 and current[j] > key:
            current[j + 1] = current[j]
            steps.append(_step(len(steps) + 1, "shift", "后移元素", f"{current[j]} 大于 {key}，向后移动一位。", current, j + 1, "moved", "shift", pointers=[_ptr("i", i, key), _ptr("j", j, current[j]), _ptr("j+1", j + 1)], pointer_roles={"j": "target", "j+1": "moved"}, code_refs=["A[j + 1] = A[j]; j--;"]))
            j -= 1
        current[j + 1] = key
        steps.append(_step(len(steps) + 1, "assign", "插入元素", f"把 {key} 放入 A[{j + 2}]，当前序列 {_text(current)}。", current, j + 1, "new", "assign", pointers=[_ptr("insert", j + 1, key), _ptr("j", j)], pointer_roles={"insert": "new"}, code_refs=["A[j + 1] = key;"]))
    return _trace(request, "直接插入排序演示", data, current, "O(n^2)", "O(1)", steps)


def _selection(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做简单选择排序。", current)]
    for i in range(len(current) - 1):
        min_index = i
        steps.append(_step(len(steps) + 1, "current", "确定本趟起点", f"从第 {i + 1} 位开始寻找最小元素。", current, i, "target", pointers=[_ptr("i", i), _ptr("min", min_index, current[min_index])], pointer_roles={"i": "target", "min": "target"}, code_refs=["min = i;"]))
        for j in range(i + 1, len(current)):
            steps.append(_step(len(steps) + 1, "compare", "比较最小值", f"比较当前最小 {current[min_index]} 与 A[{j + 1}]={current[j]}。", current, j, "visited", pointers=[_ptr("i", i), _ptr("min", min_index, current[min_index]), _ptr("j", j, current[j])], pointer_roles={"min": "target", "j": "visited"}, code_refs=["if (A[j] < A[min]) min = j;"]))
            if current[j] < current[min_index]:
                min_index = j
                steps.append(_step(len(steps) + 1, "current", "更新最小位置", f"更新最小元素位置为第 {min_index + 1} 位。", current, min_index, "target", pointers=[_ptr("i", i), _ptr("min", min_index, current[min_index]), _ptr("j", j, current[j])], pointer_roles={"min": "target"}, code_refs=["min = j;"]))
        if min_index != i:
            current[i], current[min_index] = current[min_index], current[i]
            steps.append(_step(len(steps) + 1, "shift", "交换到有序区末尾", f"交换第 {i + 1} 位和第 {min_index + 1} 位，得到 {_text(current)}。", current, i, "moved", "shift", pointers=[_ptr("i", i, current[i]), _ptr("min", min_index, current[min_index])], pointer_roles={"i": "moved", "min": "moved"}, code_refs=["swap(A[i], A[min]);"]))
    return _trace(request, "简单选择排序演示", data, current, "O(n^2)", "O(1)", steps)


def _quick(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做快速排序。", current)]

    def partition(low: int, high: int) -> int:
        pivot = current[low]
        steps.append(_step(len(steps) + 1, "current", "选择枢轴", f"选择 A[{low + 1}]={pivot} 作为枢轴。", current, low, "target", pointers=[_ptr("low", low), _ptr("high", high), _ptr("pivot", low, pivot)], pointer_roles={"pivot": "target"}, code_refs=["pivot = A[low]; i = low; j = high;"]))
        i, j = low, high
        while i < j:
            while i < j and current[j] >= pivot:
                steps.append(_step(len(steps) + 1, "compare", "从右向左扫描", f"A[{j + 1}]={current[j]} >= pivot，j 继续左移。", current, j, "visited", pointers=[_ptr("low", low), _ptr("high", high), _ptr("i", i, current[i]), _ptr("j", j, current[j]), _ptr("pivot", low, pivot)], pointer_roles={"j": "visited", "pivot": "target"}, code_refs=["while (i < j && A[j] >= pivot) j--;"]))
                j -= 1
            if i < j:
                current[i] = current[j]
                steps.append(_step(len(steps) + 1, "assign", "填左侧空位", f"把 A[{j + 1}] 放到左侧空位 A[{i + 1}]，然后 i 右移。", current, i, "moved", "assign", pointers=[_ptr("i", i, current[i]), _ptr("j", j, current[j]), _ptr("pivot", low, pivot)], pointer_roles={"i": "moved", "j": "target"}, code_refs=["A[i] = A[j]; i++;"]))
                i += 1
            while i < j and current[i] <= pivot:
                steps.append(_step(len(steps) + 1, "compare", "从左向右扫描", f"A[{i + 1}]={current[i]} <= pivot，i 继续右移。", current, i, "visited", pointers=[_ptr("low", low), _ptr("high", high), _ptr("i", i, current[i]), _ptr("j", j, current[j]), _ptr("pivot", low, pivot)], pointer_roles={"i": "visited", "pivot": "target"}, code_refs=["while (i < j && A[i] <= pivot) i++;"]))
                i += 1
            if i < j:
                current[j] = current[i]
                steps.append(_step(len(steps) + 1, "assign", "填右侧空位", f"把 A[{i + 1}] 放到右侧空位 A[{j + 1}]，然后 j 左移。", current, j, "moved", "assign", pointers=[_ptr("i", i, current[i]), _ptr("j", j, current[j]), _ptr("pivot", low, pivot)], pointer_roles={"j": "moved", "i": "target"}, code_refs=["A[j] = A[i]; j--;"]))
                j -= 1
        current[i] = pivot
        steps.append(_step(len(steps) + 1, "assign", "枢轴归位", f"i 和 j 相遇，枢轴 {pivot} 放到第 {i + 1} 位。", current, i, "success", "assign", pointers=[_ptr("i/j", i, pivot), _ptr("pivot", i, pivot)], pointer_roles={"i/j": "success", "pivot": "success"}, code_refs=["A[i] = pivot;"]))
        return i

    def quick(low: int, high: int) -> None:
        if low < high:
            pivot_index = partition(low, high)
            quick(low, pivot_index - 1)
            quick(pivot_index + 1, high)

    quick(0, len(current) - 1)
    return _trace(request, "快速排序演示", data, current, "平均 O(n log n)，最坏 O(n^2)", "平均 O(log n)", steps)


def _merge(request: OperationRequest) -> VisualizationTrace:
    data = _values(request)
    current = list(data)
    aux = list(current)
    steps = [_step(1, "init", "初始序列", f"准备对 {_text(current)} 做二路归并排序。", current)]

    def merge_sort(left: int, right: int) -> None:
        if left >= right:
            steps.append(_step(len(steps) + 1, "check", "子序列已有序", f"A[{left + 1}..{right + 1}] 只有一个元素，天然有序。", current, left, "success", "check_condition"))
            return

        mid = (left + right) // 2
        steps.append(_step(len(steps) + 1, "current", "二分子序列", f"把 A[{left + 1}..{right + 1}] 分成 A[{left + 1}..{mid + 1}] 和 A[{mid + 2}..{right + 1}]。", current, mid, "target", pointers=[_ptr("left", left), _ptr("mid", mid), _ptr("right", right)], pointer_roles={"mid": "target"}, code_refs=["mid = (left + right) / 2;"]))
        merge_sort(left, mid)
        merge_sort(mid + 1, right)
        merge(left, mid, right)

    def merge(left: int, mid: int, right: int) -> None:
        steps.append(_step(len(steps) + 1, "compare", "开始归并", f"归并两个有序段 A[{left + 1}..{mid + 1}] 和 A[{mid + 2}..{right + 1}]。", current, left, "current", pointers=[_ptr("left", left), _ptr("mid", mid), _ptr("right", right)], pointer_roles={"left": "current"}, code_refs=["i = left; j = mid + 1; k = left;"]))
        i, j, k = left, mid + 1, left
        while i <= mid and j <= right:
            steps.append(_step(len(steps) + 1, "compare", "比较两段首元素", f"比较左段 A[{i + 1}]={current[i]} 与右段 A[{j + 1}]={current[j]}，较小者写入辅助数组 B[{k + 1}]。", current, i, "target", pointers=[_ptr("i", i, current[i]), _ptr("j", j, current[j]), _ptr("k", k)], pointer_roles={"i": "target", "j": "visited", "k": "new"}, code_refs=["if (A[i] <= A[j]) B[k++] = A[i++]; else B[k++] = A[j++];"]))
            if current[i] <= current[j]:
                aux[k] = current[i]
                i += 1
            else:
                aux[k] = current[j]
                j += 1
            steps.append(_step(len(steps) + 1, "assign", "写入辅助数组", f"辅助数组 B[{k + 1}] 得到 {aux[k]}。", current, k, "new", "assign", pointers=[_ptr("i", i if i <= mid else None), _ptr("j", j if j <= right else None), _ptr("k", k, aux[k])], pointer_roles={"k": "new"}, code_refs=["B[k] = 较小元素;"]))
            k += 1
        while i <= mid:
            aux[k] = current[i]
            steps.append(_step(len(steps) + 1, "assign", "复制左段剩余元素", f"左段剩余 A[{i + 1}]={current[i]}，复制到 B[{k + 1}]。", current, i, "moved", "assign", pointers=[_ptr("i", i, current[i]), _ptr("k", k)], pointer_roles={"i": "moved", "k": "new"}, code_refs=["B[k++] = A[i++];"]))
            i += 1
            k += 1
        while j <= right:
            aux[k] = current[j]
            steps.append(_step(len(steps) + 1, "assign", "复制右段剩余元素", f"右段剩余 A[{j + 1}]={current[j]}，复制到 B[{k + 1}]。", current, j, "moved", "assign", pointers=[_ptr("j", j, current[j]), _ptr("k", k)], pointer_roles={"j": "moved", "k": "new"}, code_refs=["B[k++] = A[j++];"]))
            j += 1
            k += 1
        for index in range(left, right + 1):
            current[index] = aux[index]
            steps.append(_step(len(steps) + 1, "assign", "写回原数组", f"把辅助数组 B[{index + 1}]={aux[index]} 写回 A[{index + 1}]，当前序列 {_text(current)}。", current, index, "changed", "assign", pointers=[_ptr("index", index, aux[index])], pointer_roles={"index": "changed"}, code_refs=["A[index] = B[index];"]))

    if current:
        merge_sort(0, len(current) - 1)
    steps.append(_step(len(steps) + 1, "done", "排序完成", f"最终有序序列为 {_text(current)}。", current, None, "success"))
    return _trace(request, "归并排序演示", data, current, "O(n log n)", "O(n)", steps)


def _trace(request: OperationRequest, title: str, initial: list[Any], result: list[Any], time_complexity: str, space_complexity: str, steps: list[Step]) -> VisualizationTrace:
    return VisualizationTrace(
        title=title,
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=_text(initial), result=_text(result), time_complexity=time_complexity, space_complexity=space_complexity),
        steps=steps,
    )
