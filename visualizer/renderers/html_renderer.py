from __future__ import annotations

import html
import re
from typing import Any

from visualizer.protocol import Action, Step


ROLE_LABELS = {
    "current": "当前",
    "previous": "前驱",
    "target": "目标",
    "new": "新",
    "deleted": "删除",
    "moved": "移动",
    "visited": "已访问",
    "changed": "已改变",
    "success": "成功",
    "error": "错误",
}


def render_step_html(step: Step) -> str:
    state = step.state
    kind = state.get("kind")
    if kind == "sequence":
        body = _render_sequence(step)
    elif kind == "linked":
        body = _render_linked(step)
    elif kind == "stack":
        body = _render_stack(step)
    elif kind == "queue":
        body = _render_queue(step)
    elif kind == "tree":
        body = _render_tree(step)
    elif kind == "graph":
        body = _render_graph(step)
    elif kind == "unsupported":
        body = _render_unsupported(step)
    else:
        body = "<div class='dsvp-empty'>暂无可视化状态</div>"
    return f"<div class='dsvp-stage'>{body}{_render_step_companion(step)}</div>"


def render_styles() -> str:
    return """
    <style>
    .dsvp-stage{font-family:Arial,'Microsoft YaHei',sans-serif;margin:12px 0}
    .dsvp-wrap{position:relative;margin:0;padding:16px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;overflow:auto}
    .dsvp-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
    .dsvp-lane{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap;padding:4px 0 2px}
    .dsvp-link-pair{display:inline-flex;align-items:stretch;gap:8px}
    .dsvp-cell,.dsvp-node,.dsvp-head,.dsvp-stack-item,.dsvp-queue-item{position:relative;box-sizing:border-box;min-width:62px;min-height:62px;padding:7px 10px;border:2px solid #d1d5db;border-radius:8px;background:white;color:#111827;text-align:center;font-weight:700;box-shadow:0 1px 2px rgba(15,23,42,.06);transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease,background .22s ease}
    .dsvp-cell small{display:block;color:#6b7280;font-weight:500;margin-top:3px}
    .dsvp-value{display:block;line-height:1.25;word-break:break-word}
    .dsvp-node{border-color:#60a5fa}
    .dsvp-head{background:#eef2ff;border-color:#6366f1;color:#312e81}
    .dsvp-arrow{align-self:center;color:#64748b;font-weight:900;padding-top:10px;transition:color .22s ease,transform .22s ease}
    .dsvp-arrow.trail{color:#2563eb;animation:dsvp-path .7s ease both}
    .dsvp-null{align-self:center;color:#64748b;font-weight:800;padding-top:10px}
    .dsvp-stack{display:flex;flex-direction:column-reverse;align-items:flex-start;gap:6px;min-height:52px}
    .dsvp-stack-item{width:130px;border-color:#22c55e}
    .dsvp-stack-top,.dsvp-queue-mark{font-size:12px;color:#475569;font-weight:800}
    .dsvp-queue-item{border-color:#f59e0b}
    .dsvp-meta{margin-top:10px;color:#475569;font-size:13px}
    .dsvp-empty{padding:18px;color:#64748b}
    .dsvp-trail{background:#eff6ff;border-color:#93c5fd;color:#1e3a8a}
    .dsvp-role-current,.dsvp-role-target{background:#fff7ed;border-color:#fb923c;box-shadow:0 0 0 4px rgba(251,146,60,.18);animation:dsvp-pulse 1.1s ease-in-out infinite}
    .dsvp-role-previous{background:#eef2ff;border-color:#818cf8;box-shadow:0 0 0 4px rgba(129,140,248,.16)}
    .dsvp-role-new{background:#ecfdf5;border-color:#22c55e;box-shadow:0 0 0 4px rgba(34,197,94,.16);animation:dsvp-pop .34s ease-out both}
    .dsvp-role-moved,.dsvp-role-changed{background:#fefce8;border-color:#eab308;box-shadow:0 0 0 4px rgba(234,179,8,.18);animation:dsvp-slide .38s ease-out both}
    .dsvp-role-visited{background:#eff6ff;border-color:#60a5fa}
    .dsvp-role-success{background:#ecfdf5;border-color:#16a34a;box-shadow:0 0 0 4px rgba(22,163,74,.2);animation:dsvp-success .9s ease-in-out 2}
    .dsvp-role-error,.dsvp-role-deleted{background:#fef2f2;border-color:#ef4444;box-shadow:0 0 0 4px rgba(239,68,68,.16)}
    .dsvp-marker-row{display:flex;justify-content:center;align-items:center;gap:3px;flex-wrap:wrap;min-height:17px;margin:-1px 0 4px}
    .dsvp-badge{position:static;display:inline-flex;align-items:center;max-width:86px;padding:2px 6px;border-radius:999px;background:#0f172a;color:white;font-size:10px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-shadow:0 1px 3px rgba(15,23,42,.16)}
    .dsvp-badge.pointer{background:#2563eb}
    .dsvp-badge.success{background:#16a34a}
    .dsvp-badge.error{background:#dc2626}
    .dsvp-badge.new{background:#059669}
    .dsvp-pointer-row{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
    .dsvp-pointer-chip{display:inline-flex;align-items:center;gap:4px;padding:4px 8px;border:1px solid #cbd5e1;border-radius:999px;background:white;color:#334155;font-size:12px;font-weight:700}
    .dsvp-pointer-chip.active{border-color:#2563eb;background:#eff6ff;color:#1d4ed8}
    .dsvp-tree{display:flex;justify-content:center;min-width:340px;overflow:auto;padding:4px 0 2px}
    .dsvp-tree-subtree{display:flex;flex-direction:column;align-items:center;position:relative}
    .dsvp-tree-children{display:flex;justify-content:center;gap:22px;position:relative;margin-top:24px}
    .dsvp-tree-children::before{content:"";position:absolute;left:28px;right:28px;top:-12px;border-top:2px solid #93c5fd}
    .dsvp-tree-subtree.has-child>.dsvp-tree-node-wrap::after{content:"";position:absolute;left:50%;bottom:-24px;height:24px;border-left:2px solid #93c5fd}
    .dsvp-tree-child{position:relative;min-width:58px}
    .dsvp-tree-child::before{content:"";position:absolute;left:50%;top:-12px;height:12px;border-left:2px solid #93c5fd}
    .dsvp-tree-node-wrap{position:relative;display:flex;justify-content:center}
    .dsvp-tree-node{position:relative;box-sizing:border-box;width:58px;min-width:58px;min-height:58px;padding:7px 8px;border:2px solid #60a5fa;border-radius:999px;background:white;color:#111827;text-align:center;font-weight:800;box-shadow:0 1px 2px rgba(15,23,42,.06);transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease,background .22s ease}
    .dsvp-tree-empty{width:58px;height:58px;visibility:hidden}
    .dsvp-graph-node{position:relative;box-sizing:border-box;min-width:54px;min-height:54px;padding:7px 10px;border:2px solid #60a5fa;border-radius:999px;background:white;color:#111827;text-align:center;font-weight:800;box-shadow:0 1px 2px rgba(15,23,42,.06);transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease,background .22s ease}
    .dsvp-graph{display:flex;flex-direction:column;gap:12px}
    .dsvp-graph-nodes{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .dsvp-graph-edges{display:flex;gap:6px;flex-wrap:wrap}
    .dsvp-edge-chip{padding:4px 8px;border-radius:999px;background:#f1f5f9;color:#334155;border:1px solid #cbd5e1;font-size:12px;font-weight:700}
    .dsvp-companion{margin-top:8px;display:grid;grid-template-columns:1fr;gap:8px}
    .dsvp-panel{border:1px solid #e5e7eb;border-radius:8px;background:white;padding:10px 12px}
    .dsvp-panel-title{margin:0 0 6px;color:#334155;font-size:12px;font-weight:800}
    .dsvp-timeline{display:flex;gap:6px;flex-wrap:wrap}
    .dsvp-pill{padding:4px 8px;border-radius:999px;background:#f1f5f9;color:#334155;font-size:12px;font-weight:700}
    .dsvp-pill.active{background:#dbeafe;color:#1d4ed8}
    .dsvp-actions{margin:0;padding-left:18px;color:#334155;font-size:13px}
    .dsvp-actions li{margin:4px 0}
    .dsvp-code{display:flex;flex-direction:column;gap:4px}
    .dsvp-code-line{font-family:Consolas,'Courier New',monospace;font-size:12px;line-height:1.45;padding:5px 7px;border-radius:6px;background:#0f172a;color:#e2e8f0;overflow:auto}
    .dsvp-unsupported{padding:14px;color:#334155;white-space:pre-wrap}
    @keyframes dsvp-pulse{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-2px) scale(1.03)}}
    @keyframes dsvp-pop{0%{transform:scale(.82);opacity:.3}100%{transform:scale(1);opacity:1}}
    @keyframes dsvp-slide{0%{transform:translateX(-8px)}100%{transform:translateX(0)}}
    @keyframes dsvp-success{0%,100%{filter:none}50%{filter:brightness(1.08)}}
    @keyframes dsvp-path{0%{transform:translateX(-4px);opacity:.45}100%{transform:translateX(0);opacity:1}}
    @media (min-width:900px){.dsvp-companion{grid-template-columns:1fr 1fr}.dsvp-panel.wide{grid-column:1 / -1}}
    </style>
    """


def _render_sequence(step: Step) -> str:
    state = step.state
    cell_roles = {item.index: item.role for item in step.highlights.cells}
    active_index = _first_int(cell_roles)
    cells = []
    for cell in state.get("cells", []):
        index = int(cell.get("index", 0))
        role = cell_roles.get(index)
        classes = ["dsvp-cell"]
        if active_index is not None and index < active_index and _is_visit_step(step):
            classes.append("dsvp-trail")
        if role:
            classes.append(_role_class(role))
        badge = _badge(role) if role else ""
        cells.append(
            f"<div class='{' '.join(classes)}'>"
            f"{_marker_row(badge)}"
            f"<span class='dsvp-value'>{html.escape(str(cell.get('value')))}</span>"
            f"<small>{html.escape(str(cell.get('label')))}</small>"
            "</div>"
        )
    meta = state.get("metadata", {})
    return (
        "<div class='dsvp-wrap'>"
        f"<div class='dsvp-row'>{''.join(cells)}</div>"
        f"<div class='dsvp-meta'>length={html.escape(str(meta.get('length')))} / capacity={html.escape(str(meta.get('capacity')))}</div>"
        "</div>"
    )


def _render_linked(step: Step) -> str:
    state = step.state
    node_roles = {item.id: item.role for item in step.highlights.nodes}
    pointer_roles = {item.name: item.role for item in step.highlights.pointers}
    pointers_by_target: dict[str, list[dict[str, Any]]] = {}
    for pointer in state.get("pointers", []):
        pointers_by_target.setdefault(str(pointer.get("target")), []).append(pointer)

    active_node = _first_node_index(node_roles)
    nodes = [node for node in state.get("nodes", []) if node.get("id") != "head"]
    parts: list[str] = [_render_node_box("head", "head", node_roles, pointers_by_target, pointer_roles, is_head=True)]
    for index, node in enumerate(nodes):
        node_id = str(node.get("id"))
        arrow_class = "dsvp-arrow"
        if active_node is not None and index <= active_node and _is_visit_step(step):
            arrow_class += " trail"
        node_html = _render_node_box(node_id, str(node.get("label")), node_roles, pointers_by_target, pointer_roles)
        parts.append(f"<span class='dsvp-link-pair'><span class='{arrow_class}'>-></span>{node_html}</span>")
    parts.append("<span class='dsvp-link-pair'><span class='dsvp-null'>-> NULL</span></span>")

    pointer_chips = []
    for pointer in state.get("pointers", []):
        name = str(pointer.get("name"))
        target = str(pointer.get("target"))
        active = " active" if name in pointer_roles else ""
        pointer_chips.append(
            f"<span class='dsvp-pointer-chip{active}'>{html.escape(name)} -> {html.escape(target)}</span>"
        )

    return (
        "<div class='dsvp-wrap'>"
        f"<div class='dsvp-lane'>{''.join(parts)}</div>"
        f"<div class='dsvp-pointer-row'>{''.join(pointer_chips)}</div>"
        "</div>"
    )


def _render_stack(step: Step) -> str:
    state = step.state
    items = state.get("items", [])
    active_top = int(state.get("top", -1))
    rendered = []
    for item in items:
        index = int(item.get("index", -1))
        role = _stack_role(step, index, active_top)
        classes = ["dsvp-stack-item"]
        if role:
            classes.append(_role_class(role))
        badge = _badge(role) if role else ""
        rendered.append(
            f"<div class='{' '.join(classes)}'>{_marker_row(badge)}<span class='dsvp-value'>{html.escape(str(item.get('value')))}</span></div>"
        )
    return (
        "<div class='dsvp-wrap'>"
        f"<div class='dsvp-stack'>{''.join(rendered)}</div>"
        f"<div class='dsvp-stack-top'>top={html.escape(str(state.get('top')))}</div>"
        "</div>"
    )


def _render_queue(step: Step) -> str:
    state = step.state
    items = state.get("items", [])
    rendered = []
    for index, item in enumerate(items):
        role = _queue_role(step, index, len(items))
        classes = ["dsvp-queue-item"]
        if role:
            classes.append(_role_class(role))
        badge = _badge(role) if role else ""
        rendered.append(
            f"<div class='{' '.join(classes)}'>{_marker_row(badge)}<span class='dsvp-value'>{html.escape(str(item.get('value')))}</span></div>"
        )
    return (
        "<div class='dsvp-wrap'>"
        f"<div class='dsvp-row'><span class='dsvp-queue-mark'>front</span>{''.join(rendered)}<span class='dsvp-queue-mark'>rear</span></div>"
        f"<div class='dsvp-meta'>front={html.escape(str(state.get('front')))} / rear={html.escape(str(state.get('rear')))}</div>"
        "</div>"
    )


def _render_tree(step: Step) -> str:
    state = step.state
    node_roles = {item.id: item.role for item in step.highlights.nodes}
    nodes = state.get("nodes", [])
    by_index = {int(node.get("index", 0)): node for node in nodes}
    order = " -> ".join(str(item) for item in state.get("visit_order", []))
    tree_html = _render_tree_subtree(0, by_index, node_roles)
    return (
        "<div class='dsvp-wrap'>"
        f"<div class='dsvp-tree'>{tree_html}</div>"
        f"<div class='dsvp-meta'>访问序列：{html.escape(order or '暂无')}</div>"
        "</div>"
    )


def _render_graph(step: Step) -> str:
    state = step.state
    node_roles = {item.id: item.role for item in step.highlights.nodes}
    node_html = []
    for node in state.get("nodes", []):
        node_id = str(node)
        role = node_roles.get(node_id)
        classes = ["dsvp-graph-node"]
        if role:
            classes.append(_role_class(role))
        node_html.append(
            f"<div class='{' '.join(classes)}'>{_marker_row(_badge(role) if role else '')}<span class='dsvp-value'>{html.escape(node_id)}</span></div>"
        )
    edge_html = []
    for edge in state.get("edges", []):
        src = html.escape(str(edge.get("from")))
        dst = html.escape(str(edge.get("to")))
        weight = edge.get("weight")
        label = f"{src} -> {dst}" + (f" ({html.escape(str(weight))})" if weight not in (None, 1) else "")
        edge_html.append(f"<span class='dsvp-edge-chip'>{label}</span>")
    order = " -> ".join(str(item) for item in state.get("visit_order", []))
    return (
        "<div class='dsvp-wrap'>"
        "<div class='dsvp-graph'>"
        f"<div class='dsvp-graph-nodes'>{''.join(node_html)}</div>"
        f"<div class='dsvp-graph-edges'>{''.join(edge_html)}</div>"
        "</div>"
        f"<div class='dsvp-meta'>轨迹：{html.escape(order or '暂无')}</div>"
        "</div>"
    )


def _render_unsupported(step: Step) -> str:
    return f"<div class='dsvp-wrap'><div class='dsvp-unsupported'>{html.escape(step.description)}</div></div>"


def _render_step_companion(step: Step) -> str:
    timeline = _render_timeline(step)
    actions = _render_actions(step.actions)
    code = _render_code_refs(step)
    return (
        "<div class='dsvp-companion'>"
        f"{timeline}"
        f"{actions}"
        f"{code}"
        "</div>"
    )


def _render_timeline(step: Step) -> str:
    roles = []
    roles.extend(item.role for item in step.highlights.cells)
    roles.extend(item.role for item in step.highlights.nodes)
    roles.extend(item.role for item in step.highlights.pointers)
    if not roles:
        return ""
    pills = "".join(
        f"<span class='dsvp-pill active'>{html.escape(ROLE_LABELS.get(str(role), str(role)))}</span>"
        for role in dict.fromkeys(roles)
    )
    return f"<div class='dsvp-panel'><p class='dsvp-panel-title'>当前焦点</p><div class='dsvp-timeline'>{pills}</div></div>"


def _render_actions(actions: list[Action]) -> str:
    if not actions:
        return ""
    items = "".join(f"<li>{html.escape(action.description)}</li>" for action in actions)
    return f"<div class='dsvp-panel'><p class='dsvp-panel-title'>关键动作</p><ul class='dsvp-actions'>{items}</ul></div>"


def _render_code_refs(step: Step) -> str:
    refs = list(step.code_refs)
    if not refs:
        refs = [_infer_code_ref(action) for action in step.actions]
        refs = [ref for ref in refs if ref]
    if not refs:
        return ""
    lines = "".join(f"<div class='dsvp-code-line'>{html.escape(ref)}</div>" for ref in refs[:4])
    return f"<div class='dsvp-panel wide'><p class='dsvp-panel-title'>代码线索</p><div class='dsvp-code'>{lines}</div></div>"


def _render_node_box(
    node_id: str,
    label: str,
    node_roles: dict[str, str],
    pointers_by_target: dict[str, list[dict[str, Any]]],
    pointer_roles: dict[str, str],
    is_head: bool = False,
) -> str:
    role = node_roles.get(node_id)
    classes = ["dsvp-head" if is_head else "dsvp-node"]
    if role:
        classes.append(_role_class(role))
    badges = []
    if role:
        badges.append(_badge(role))
    for pointer in pointers_by_target.get(node_id, []):
        name = str(pointer.get("name"))
        pointer_role = pointer_roles.get(name)
        badge_class = "pointer"
        if pointer_role in {"success", "error", "new"}:
            badge_class = pointer_role
        badges.append(f"<span class='dsvp-badge {badge_class}'>{html.escape(name)}</span>")
    return (
        f"<div class='{' '.join(classes)}'>"
        f"{_marker_row(''.join(badges))}"
        f"<span class='dsvp-value'>{html.escape(label)}</span>"
        "</div>"
    )


def _role_class(role: str) -> str:
    return f"dsvp-role-{html.escape(str(role))}"


def _badge(role: str | None) -> str:
    if not role:
        return ""
    label = ROLE_LABELS.get(str(role), str(role))
    badge_class = str(role) if role in {"success", "error", "new"} else ""
    return f"<span class='dsvp-badge {badge_class}'>{html.escape(label)}</span>"


def _marker_row(content: str) -> str:
    return f"<div class='dsvp-marker-row'>{content}</div>"


def _is_visit_step(step: Step) -> bool:
    return step.phase in {"visit", "compare", "move", "shift"} or any(
        action.type in {"visit", "compare", "move", "shift"} for action in step.actions
    )


def _first_int(values: dict[int, str]) -> int | None:
    return min(values) if values else None


def _first_node_index(node_roles: dict[str, str]) -> int | None:
    indexes = []
    for node_id in node_roles:
        match = re.fullmatch(r"n(\d+)", node_id)
        if match:
            indexes.append(int(match.group(1)))
    return min(indexes) if indexes else None


def _render_tree_subtree(index: int, by_index: dict[int, dict[str, Any]], node_roles: dict[str, str]) -> str:
    node = by_index.get(index)
    if node is None:
        return "<div class='dsvp-tree-empty'></div>"

    node_id = str(node.get("id"))
    role = node_roles.get(node_id)
    classes = ["dsvp-tree-node"]
    if role:
        classes.append(_role_class(role))
    node_html = (
        f"<div class='dsvp-tree-node-wrap'><div class='{' '.join(classes)}'>"
        f"{_marker_row(_badge(role) if role else '')}"
        f"<span class='dsvp-value'>{html.escape(str(node.get('label')))}</span>"
        "</div></div>"
    )

    left_index = 2 * index + 1
    right_index = 2 * index + 2
    has_left = left_index in by_index
    has_right = right_index in by_index
    if not has_left and not has_right:
        return f"<div class='dsvp-tree-subtree'>{node_html}</div>"

    left = _render_tree_subtree(left_index, by_index, node_roles)
    right = _render_tree_subtree(right_index, by_index, node_roles)
    return (
        "<div class='dsvp-tree-subtree has-child'>"
        f"{node_html}"
        "<div class='dsvp-tree-children'>"
        f"<div class='dsvp-tree-child'>{left}</div>"
        f"<div class='dsvp-tree-child'>{right}</div>"
        "</div>"
        "</div>"
    )


def _stack_role(step: Step, index: int, active_top: int) -> str | None:
    action_types = {action.type for action in step.actions}
    if index == active_top and action_types & {"push", "pop"}:
        return "new" if "push" in action_types else "target"
    if index == active_top and step.phase in {"check", "move"}:
        return "current"
    return None


def _queue_role(step: Step, index: int, item_count: int) -> str | None:
    action_types = {action.type for action in step.actions}
    if "dequeue" in action_types and index == 0:
        return "target"
    if "enqueue" in action_types and index == item_count - 1:
        return "new"
    if step.phase == "move" and index == 0:
        return "visited"
    return None


def _infer_code_ref(action: Action) -> str:
    target = action.target or ""
    value = "" if action.value is None else str(action.value)
    if action.type == "check_condition":
        return f"if (!合法条件) return ERROR;  // {action.description}"
    if action.type == "assign":
        return f"{target} = {value};" if value else f"{target} = ...;"
    if action.type == "move":
        return f"{target} = {target}->next;" if "next" in action.description else f"{target} = ...;"
    if action.type == "shift":
        return "data[j + 1] = data[j];"
    if action.type == "compare":
        return f"if ({target} == target) return position;"
    if action.type == "visit":
        return f"visit({target});"
    if action.type == "link":
        src = action.from_ or "node"
        dst = action.to or "next"
        return f"{target or src + '->next'} = {dst};"
    if action.type == "unlink":
        return f"{target or 'pre->next'} = q->next;"
    if action.type == "create_node":
        return "s = malloc(sizeof(Node));"
    if action.type == "delete_node":
        return "free(q);"
    if action.type == "push":
        return f"stack[++top] = {value};"
    if action.type == "pop":
        return "value = stack[top--];"
    if action.type == "enqueue":
        return f"queue[rear++] = {value};"
    if action.type == "dequeue":
        return "value = queue[front++];"
    return ""
