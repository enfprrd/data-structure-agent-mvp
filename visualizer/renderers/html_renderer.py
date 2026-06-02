from __future__ import annotations

import html
from typing import Any

from visualizer.protocol import Step


def render_step_html(step: Step) -> str:
    state = step.state
    kind = state.get("kind")
    if kind == "sequence":
        return _render_sequence(state)
    if kind == "linked":
        return _render_linked(state)
    if kind == "stack":
        return _render_stack(state)
    if kind == "queue":
        return _render_queue(state)
    return "<div class='dsvp-empty'>暂无可视化状态</div>"


def render_styles() -> str:
    return """
    <style>
    .dsvp-wrap{font-family:Arial,'Microsoft YaHei',sans-serif;margin:12px 0;padding:14px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;overflow:auto}
    .dsvp-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
    .dsvp-cell,.dsvp-node,.dsvp-head,.dsvp-stack-item,.dsvp-queue-item{min-width:54px;min-height:42px;padding:8px 10px;border:2px solid #d1d5db;border-radius:8px;background:white;color:#111827;text-align:center;font-weight:700}
    .dsvp-cell small{display:block;color:#6b7280;font-weight:500;margin-top:3px}
    .dsvp-node{border-color:#60a5fa}
    .dsvp-head{background:#eef2ff;border-color:#6366f1;color:#312e81}
    .dsvp-arrow{color:#64748b;font-weight:800}
    .dsvp-stack{display:flex;flex-direction:column-reverse;align-items:flex-start;gap:6px}
    .dsvp-stack-item{width:120px;border-color:#22c55e}
    .dsvp-stack-top,.dsvp-queue-mark{font-size:12px;color:#475569;font-weight:700}
    .dsvp-queue-item{border-color:#f59e0b}
    .dsvp-meta{margin-top:10px;color:#475569;font-size:13px}
    .dsvp-empty{padding:18px;color:#64748b}
    </style>
    """


def _render_sequence(state: dict[str, Any]) -> str:
    cells = []
    for cell in state.get("cells", []):
        cells.append(
            "<div class='dsvp-cell'>"
            f"{html.escape(str(cell.get('value')))}"
            f"<small>{html.escape(str(cell.get('label')))}</small>"
            "</div>"
        )
    meta = state.get("metadata", {})
    return f"<div class='dsvp-wrap'><div class='dsvp-row'>{''.join(cells)}</div><div class='dsvp-meta'>length={meta.get('length')} / capacity={meta.get('capacity')}</div></div>"


def _render_linked(state: dict[str, Any]) -> str:
    value_by_id = {node.get("id"): node for node in state.get("nodes", [])}
    parts = ["<div class='dsvp-head'>head</div>"]
    for node in state.get("nodes", []):
        if node.get("id") == "head":
            continue
        parts.append("<span class='dsvp-arrow'>-></span>")
        parts.append(f"<div class='dsvp-node'>{html.escape(str(node.get('label')))}</div>")
    parts.append("<span class='dsvp-arrow'>-> NULL</span>")
    pointers = ", ".join(f"{item.get('name')}={item.get('target')}" for item in state.get("pointers", []))
    return f"<div class='dsvp-wrap'><div class='dsvp-row'>{''.join(parts)}</div><div class='dsvp-meta'>{html.escape(pointers)}</div></div>"


def _render_stack(state: dict[str, Any]) -> str:
    items = "".join(f"<div class='dsvp-stack-item'>{html.escape(str(item.get('value')))}</div>" for item in state.get("items", []))
    return f"<div class='dsvp-wrap'><div class='dsvp-stack'>{items}</div><div class='dsvp-stack-top'>top={state.get('top')}</div></div>"


def _render_queue(state: dict[str, Any]) -> str:
    items = "".join(f"<div class='dsvp-queue-item'>{html.escape(str(item.get('value')))}</div>" for item in state.get("items", []))
    return f"<div class='dsvp-wrap'><div class='dsvp-row'><span class='dsvp-queue-mark'>front</span>{items}<span class='dsvp-queue-mark'>rear</span></div><div class='dsvp-meta'>front={state.get('front')} / rear={state.get('rear')}</div></div>"
