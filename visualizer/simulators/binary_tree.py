from __future__ import annotations

from collections import deque
from typing import Any

from visualizer.protocol import Action, Highlights, NodeHighlight, OperationRequest, Step, Summary, VisualizationTrace


def _nodes(data: list[Any]) -> list[dict[str, Any]]:
    return [{"id": f"t{index}", "label": str(value), "value": value, "index": index} for index, value in enumerate(data) if value is not None]


def _edges(data: list[Any]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for index, value in enumerate(data):
        if value is None:
            continue
        left = 2 * index + 1
        right = 2 * index + 2
        if left < len(data) and data[left] is not None:
            edges.append({"from": f"t{index}", "to": f"t{left}", "label": "L"})
        if right < len(data) and data[right] is not None:
            edges.append({"from": f"t{index}", "to": f"t{right}", "label": "R"})
    return edges


def _state(data: list[Any]) -> dict[str, Any]:
    slots = [
        {
            "id": f"t{index}",
            "label": "null" if value is None else str(value),
            "value": value,
            "index": index,
            "empty": value is None,
        }
        for index, value in enumerate(data)
    ]
    return {"kind": "tree", "nodes": _nodes(data), "slots": slots, "edges": _edges(data)}


def _step(step_id: int, title: str, description: str, data: list[Any], index: int | None, role: str, order: list[Any]) -> Step:
    highlights = Highlights()
    if index is not None:
        highlights.nodes.append(NodeHighlight(id=f"t{index}", role=role))  # type: ignore[arg-type]
    return Step(
        step_id=step_id,
        phase="visit" if index is not None else "init",
        title=title,
        description=description,
        state={**_state(data), "visit_order": list(order)},
        highlights=highlights,
        actions=[Action(type="visit", description=description, target=f"t{index}")] if index is not None else [],
        message=description,
    )


def simulate_binary_tree(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    order_indexes = _traverse_indexes(data, request.operation)
    order_values: list[Any] = []
    steps = [_step(1, "初始二叉树", "按层序数组建立二叉树，空位置可用 null 表示。", data, None, "current", order_values)]
    for index in order_indexes:
        order_values.append(data[index])
        steps.append(
            _step(
                len(steps) + 1,
                f"访问结点 {data[index]}",
                f"访问结点 {data[index]}，当前访问序列为 {' -> '.join(str(item) for item in order_values)}。",
                data,
                index,
                "success" if index == order_indexes[-1] else "current",
                order_values,
            )
        )
    return VisualizationTrace(
        title=_title(request.operation),
        structure=request.structure,
        operation=request.operation,
        summary=Summary(
            initial=str(data),
            result=" -> ".join(str(item) for item in order_values),
            time_complexity="O(n)",
            space_complexity="O(h) 或 O(n)",
        ),
        steps=steps,
    )


def _traverse_indexes(data: list[Any], operation: str) -> list[int]:
    result: list[int] = []

    def exists(index: int) -> bool:
        return index < len(data) and data[index] is not None

    def preorder(index: int) -> None:
        if not exists(index):
            return
        result.append(index)
        preorder(2 * index + 1)
        preorder(2 * index + 2)

    def inorder(index: int) -> None:
        if not exists(index):
            return
        inorder(2 * index + 1)
        result.append(index)
        inorder(2 * index + 2)

    def postorder(index: int) -> None:
        if not exists(index):
            return
        postorder(2 * index + 1)
        postorder(2 * index + 2)
        result.append(index)

    def level_order() -> None:
        q: deque[int] = deque([0] if exists(0) else [])
        while q:
            index = q.popleft()
            result.append(index)
            left = 2 * index + 1
            right = 2 * index + 2
            if exists(left):
                q.append(left)
            if exists(right):
                q.append(right)

    if operation == "traverse_inorder":
        inorder(0)
    elif operation == "traverse_postorder":
        postorder(0)
    elif operation == "traverse_level_order":
        level_order()
    else:
        preorder(0)
    return result


def _title(operation: str) -> str:
    titles = {
        "traverse_preorder": "二叉树先序遍历演示",
        "traverse_inorder": "二叉树中序遍历演示",
        "traverse_postorder": "二叉树后序遍历演示",
        "traverse_level_order": "二叉树层序遍历演示",
    }
    return titles.get(operation, "二叉树遍历演示")
