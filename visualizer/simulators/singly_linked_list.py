from __future__ import annotations

from typing import Any

from visualizer.protocol import (
    Action,
    DSVPWarning,
    Highlights,
    NodeHighlight,
    OperationRequest,
    PointerHighlight,
    Step,
    Summary,
    VisualizationTrace,
    make_error_trace,
)


def _state(data: list[Any], pointers: dict[str, str] | None = None) -> dict[str, Any]:
    nodes = [{"id": "head", "label": "head", "value": None}]
    nodes.extend({"id": f"n{index}", "label": str(value), "value": value} for index, value in enumerate(data))
    edges: list[dict[str, str]] = []
    if data:
        edges.append({"from": "head", "to": "n0", "label": "next"})
        for index in range(len(data) - 1):
            edges.append({"from": f"n{index}", "to": f"n{index + 1}", "label": "next"})
        edges.append({"from": f"n{len(data) - 1}", "to": "NULL", "label": "next"})
    else:
        edges.append({"from": "head", "to": "NULL", "label": "next"})
    pointer_items = [{"name": "head", "target": "n0" if data else "NULL"}]
    for name, target in (pointers or {}).items():
        pointer_items.append({"name": name, "target": target})
    return {"kind": "linked", "nodes": nodes, "edges": edges, "pointers": pointer_items}


def _text(data: list[Any]) -> str:
    return "head -> " + " -> ".join(str(item) for item in data) + (" -> NULL" if data else "NULL")


def _step(
    step_id: int,
    phase: str,
    title: str,
    description: str,
    data: list[Any],
    actions: list[Action],
    node_id: str | None = None,
    node_role: str = "current",
    pointers: dict[str, str] | None = None,
    pointer_role: tuple[str, str] | None = None,
    message: str = "",
) -> Step:
    highlights = Highlights()
    if node_id:
        highlights.nodes.append(NodeHighlight(id=node_id, role=node_role))  # type: ignore[arg-type]
    if pointer_role:
        highlights.pointers.append(PointerHighlight(name=pointer_role[0], role=pointer_role[1]))  # type: ignore[arg-type]
    return Step(
        step_id=step_id,
        phase=phase,
        title=title,
        description=description,
        state=_state(data, pointers),
        highlights=highlights,
        actions=actions,
        code_refs=[],
        message=message or description,
    )


def simulate_singly_linked_list(request: OperationRequest) -> VisualizationTrace:
    if request.operation == "build":
        return simulate_build(request)
    if request.operation == "insert":
        return simulate_insert(request)
    if request.operation == "delete":
        return simulate_delete(request)
    return simulate_search(request)


def simulate_build(request: OperationRequest) -> VisualizationTrace:
    initial_data = list(request.initial_state.data)
    values = list(request.params.values or [])
    mode = request.params.mode or "head_insert"
    initial = _text(initial_data)
    current = list(initial_data)
    steps: list[Step] = [
        _step(
            1,
            "init",
            "初始链表状态",
            f"当前带头结点单链表为 {_text(current)}，准备按输入序列 {values} 建表。",
            current,
            [],
        )
    ]
    step_id = 2
    for value in values:
        steps.append(
            _step(
                step_id,
                "create",
                f"创建新结点 {value}",
                f"申请新结点 s，并将数据域写入 {value}。",
                current,
                [Action(type="create_node", description="创建新结点 s。", target="s", value=value)],
                pointers={"s": "s"},
                pointer_role=("s", "new"),
            )
        )
        step_id += 1

        if mode == "tail_insert":
            tail_target = f"n{len(current) - 1}" if current else "head"
            current = current + [value]
            steps.append(
                _step(
                    step_id,
                    "link",
                    f"尾插 {value}",
                    "执行 r->next = s，再令 r = s，新结点成为尾结点。",
                    current,
                    [
                        Action(type="link", description="r->next = s。", target="r->next", **{"from": tail_target}, to="s"),
                        Action(type="move", description="r = s。", target="r", to="s"),
                    ],
                    f"n{len(current) - 1}",
                    "new",
                    pointers={"r": f"n{len(current) - 1}"},
                    pointer_role=("r", "changed"),
                )
            )
        else:
            old_first = "n0" if current else "NULL"
            current = [value] + current
            steps.append(
                _step(
                    step_id,
                    "link",
                    f"头插 {value}",
                    "先执行 s->next = head->next，再执行 head->next = s，新结点成为首元结点。",
                    current,
                    [
                        Action(type="link", description="s->next = head->next。", target="s->next", **{"from": "s"}, to=old_first),
                        Action(type="link", description="head->next = s。", target="head->next", **{"from": "head"}, to="s"),
                    ],
                    "n0",
                    "new",
                    pointers={"s": "n0"},
                    pointer_role=("s", "new"),
                )
            )
        step_id += 1

    steps.append(
        _step(
            step_id,
            "done",
            "建表完成",
            f"结果为 {_text(current)}。",
            current,
            [],
            "n0" if current else None,
            "success",
        )
    )
    title = "单链表头插法建表演示" if mode != "tail_insert" else "单链表尾插法建表演示"
    return VisualizationTrace(
        title=title,
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(current), time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
    )


def simulate_insert(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    position = int(request.params.position or 0)
    value = request.params.value
    initial = _text(data)
    if position < 1 or position > len(data) + 1:
        return make_error_trace(
            request,
            "INVALID_POSITION",
            "插入位置不合法。",
            f"当前单链表长度为 {len(data)}，合法插入位置为 1 到 {len(data) + 1}，但收到 position = {position}。",
            initial,
        )

    steps: list[Step] = [
        _step(1, "init", "初始链表状态", f"当前带头结点单链表为 {_text(data)}。", data, []),
        _step(2, "check", "检查插入位置", f"第 {position} 位在合法插入范围内。", data, [Action(type="check_condition", description="检查 1 <= position <= length + 1。", target="position")]),
        _step(3, "create", "创建新结点 s", f"申请新结点 s，并将数据域写入 {value}。", data, [Action(type="create_node", description="创建新结点 s。", target="s", value=value)], pointers={"s": "s"}, pointer_role=("s", "new")),
    ]
    pre_target = "head"
    steps.append(
        _step(
            4,
            "visit",
            "查找前驱结点 pre",
            "pre 从头结点开始，寻找第 position - 1 个结点。",
            data,
            [Action(type="visit", description="pre = head。", target="pre", to="head")],
            pointers={"pre": pre_target},
            pointer_role=("pre", "previous"),
        )
    )
    step_id = 5
    for move_index in range(1, position):
        pre_target = f"n{move_index - 1}"
        steps.append(
            _step(
                step_id,
                "move",
                f"pre 后移到第 {move_index} 个结点",
                f"执行 pre = pre->next，pre 指向值为 {data[move_index - 1]} 的结点。",
                data,
                [Action(type="move", description="pre = pre->next。", target="pre", to=pre_target)],
                pre_target,
                "previous",
                pointers={"pre": pre_target},
                pointer_role=("pre", "previous"),
            )
        )
        step_id += 1

    old_next = "NULL" if position > len(data) else f"n{position - 1}"
    steps.append(
        _step(
            step_id,
            "link",
            "执行 s->next = pre->next",
            "先让新结点 s 指向原来的后继结点，避免链表断开。",
            data,
            [Action(type="link", description="令 s->next 指向 pre->next。", target="s->next", **{"from": "s"}, to=old_next)],
            old_next if old_next != "NULL" else None,
            "changed",
            pointers={"pre": pre_target, "s": old_next},
            pointer_role=("s", "new"),
        )
    )
    step_id += 1
    result = data[: position - 1] + [value] + data[position - 1 :]
    steps.append(
        _step(
            step_id,
            "link",
            "执行 pre->next = s",
            "再让前驱结点 pre 指向 s，插入完成。",
            result,
            [Action(type="link", description="令 pre->next 指向 s。", target="pre->next", **{"from": pre_target}, to="s")],
            f"n{position - 1}",
            "new",
            pointers={"pre": pre_target, "s": f"n{position - 1}"},
            pointer_role=("pre", "changed"),
        )
    )
    step_id += 1
    steps.append(
        _step(step_id, "done", "插入完成", f"结果为 {_text(result)}。", result, [], f"n{position - 1}", "success")
    )

    return VisualizationTrace(
        title="单链表按位插入演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(result), time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
    )


def simulate_delete(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    position = int(request.params.position or 0)
    initial = _text(data)
    if not data:
        return make_error_trace(request, "EMPTY_LIST_DELETE", "空链表不能删除。", "当前单链表没有数据结点。", initial)
    if position < 1 or position > len(data):
        return make_error_trace(
            request,
            "INVALID_POSITION",
            "删除位置不合法。",
            f"当前单链表长度为 {len(data)}，合法删除位置为 1 到 {len(data)}，但收到 position = {position}。",
            initial,
        )

    steps: list[Step] = [
        _step(1, "init", "初始链表状态", f"当前带头结点单链表为 {_text(data)}。", data, []),
        _step(2, "check", "检查删除位置", f"第 {position} 位在合法删除范围内。", data, [Action(type="check_condition", description="检查 1 <= position <= length。", target="position")]),
        _step(3, "visit", "查找前驱结点 pre", "pre 从头结点开始，寻找第 position - 1 个结点。", data, [Action(type="visit", description="pre = head。", target="pre", to="head")], pointers={"pre": "head"}, pointer_role=("pre", "previous")),
    ]
    pre_target = "head"
    step_id = 4
    for move_index in range(1, position):
        pre_target = f"n{move_index - 1}"
        steps.append(
            _step(step_id, "move", f"pre 后移到第 {move_index} 个结点", "执行 pre = pre->next。", data, [Action(type="move", description="pre = pre->next。", target="pre", to=pre_target)], pre_target, "previous", pointers={"pre": pre_target}, pointer_role=("pre", "previous"))
        )
        step_id += 1

    q_id = f"n{position - 1}"
    next_id = "NULL" if position == len(data) else f"n{position}"
    steps.append(
        _step(step_id, "assign", "执行 q = pre->next", f"q 指向待删除的第 {position} 个结点。", data, [Action(type="assign", description="q = pre->next。", target="q", to=q_id)], q_id, "target", pointers={"pre": pre_target, "q": q_id}, pointer_role=("q", "target"))
    )
    step_id += 1
    result = data[: position - 1] + data[position:]
    steps.append(
        _step(step_id, "unlink", "执行 pre->next = q->next", "让前驱结点跨过待删结点，直接指向 q 的后继。", result, [Action(type="unlink", description="pre->next = q->next。", target="pre->next", **{"from": pre_target}, to=next_id)], None, "changed", pointers={"pre": pre_target}, pointer_role=("pre", "changed"))
    )
    step_id += 1
    steps.append(
        _step(step_id, "delete", "执行 free(q)", "释放 q 指向的结点空间。", result, [Action(type="delete_node", description="free(q)。", target="q")], None, "deleted")
    )
    step_id += 1
    steps.append(_step(step_id, "done", "删除完成", f"结果为 {_text(result)}。", result, []))
    return VisualizationTrace(
        title="单链表按位删除演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=_text(result), time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
    )


def simulate_search(request: OperationRequest) -> VisualizationTrace:
    data = list(request.initial_state.data)
    target = request.params.target
    initial = _text(data)
    steps: list[Step] = [
        _step(1, "init", "初始链表状态", f"p 从首元结点开始查找 {target}。", data, [], pointers={"p": "n0" if data else "NULL"}, pointer_role=("p", "current"))
    ]
    found_index: int | None = None
    for index, value in enumerate(data):
        success = value == target
        if success:
            found_index = index + 1
        steps.append(
            _step(
                len(steps) + 1,
                "visit",
                f"访问第 {index + 1} 个结点",
                f"比较 p->data = {value} 与目标 {target}。",
                data,
                [Action(type="visit", description="访问当前结点并比较数据域。", target=f"n{index}", value=value)],
                f"n{index}",
                "success" if success else "visited",
                pointers={"p": f"n{index}"},
                pointer_role=("p", "success" if success else "current"),
            )
        )
        if success:
            break

    warnings: list[DSVPWarning] = []
    result = f"找到，位置为 {found_index}" if found_index is not None else "未找到"
    if found_index is None:
        warnings.append(DSVPWarning(code="NOT_FOUND", message="查找值不存在。", detail=f"单链表中没有值 {target}。"))
        steps.append(_step(len(steps) + 1, "done", "查找结束", f"p 走到 NULL，未找到 {target}。", data, [], pointers={"p": "NULL"}, pointer_role=("p", "error")))

    return VisualizationTrace(
        title="单链表按值查找演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(initial=initial, result=result, time_complexity="O(n)", space_complexity="O(1)"),
        steps=steps,
        warnings=warnings,
    )
