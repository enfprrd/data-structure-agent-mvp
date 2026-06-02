from __future__ import annotations

import re
from dataclasses import dataclass

import streamlit as st


@dataclass
class VisualStep:
    title: str
    note: str
    values: list[int]
    structure: str
    highlight_index: int | None = None
    extra_value: int | None = None
    pointer_note: str = ""
    code_focus: str = ""


SUPPORTED_OPERATIONS = {
    "head_insert",
    "head_insertion",
    "linked_head_insert",
    "tail_insert",
    "tail_insertion",
    "linked_tail_insert",
    "linked_insert",
    "list_insert",
    "singly_insert",
    "linked_delete",
    "list_delete",
    "linked_search",
    "list_search",
    "linked_length",
    "list_length",
    "linked_reverse",
    "list_reverse",
    "reverse_list",
    "circular_traverse",
    "circular_list",
    "seq_insert",
    "sequential_insert",
    "seq_delete",
    "sequential_delete",
}

UNSUPPORTED_HINT = "这块暂时还不能演示。现在支持：插入、删除、查找、长度、头插、尾插、链表逆置。"


def build_visualization(question: str, model_output: str = "") -> list[VisualStep]:
    source = f"{question}\n{model_output}"
    source_lower = source.lower()
    compact = _compact(source)
    if _has_any(compact, ["排序", "升序", "降序", "sort", "冒泡", "选择排序", "插入排序"]):
        return []

    is_sequential = "顺序表" in source
    is_linked = (
        "链表" in source
        or "单链表" in source
        or "尾插法" in source
        or "头插法" in source
        or "头插" in source
        or "尾插" in source
        or "逆序建表" in source
        or "尾指针" in source
        or "linklist" in source_lower
        or "lnode" in source_lower
        or "tail->next" in source_lower
        or "r->next" in source_lower
        or "rear->next" in source_lower
    )
    wants_tail_insert = _has_any(
        compact,
        [
            "尾插法",
            "尾插",
            "尾部插入",
            "表尾插入",
            "后插建表",
            "尾插建表",
            "尾指针建表",
            "r->next=s",
            "tail->next=s",
            "rear->next=s",
        ],
    )
    wants_head_insert = _has_any(
        compact,
        [
            "头插法",
            "头插",
            "头部插入",
            "表头插入",
            "前插建表",
            "头插建表",
            "逆序建表",
            "s->next=head->next",
            "head->next=s",
        ],
    )
    wants_insert = (
        "插入" in source
        or "加入" in source
        or "尾插" in source
        or "头插" in source
        or "建表" in source
        or "insert" in source_lower
    )
    wants_delete = "删除" in source or "删去" in source or "delete" in source_lower or "free(" in source_lower
    wants_reverse = _has_any(compact, ["链表逆序", "链表逆置", "链表反转", "反转链表", "逆序", "逆置", "reverse"])
    values = _extract_values(question) or _extract_values(model_output)

    if is_linked and wants_reverse and "逆序建表" not in source:
        return _linked_reverse_steps(values)
    if is_sequential and wants_insert:
        return _sequential_insert_steps(values)
    if is_sequential and wants_delete:
        return _sequential_delete_steps(values)
    if is_linked and wants_tail_insert:
        return _linked_tail_insert_steps(values)
    if is_linked and wants_head_insert:
        return _linked_head_insert_steps(values)
    if is_linked and wants_insert:
        return _linked_insert_steps(values)
    if is_linked and wants_delete:
        return _linked_delete_steps(values)
    if "循环链表" in question:
        return _circular_list_steps(values)
    if "长度" in question and is_linked:
        return _linked_length_steps(values)
    if "查找" in question and is_linked:
        return _linked_search_steps(values)

    return []


def build_visualization_from_features(
    features: dict[str, object] | None,
    question: str = "",
    model_output: str = "",
) -> list[VisualStep]:
    if not features:
        return build_visualization(question, model_output)

    supported = features.get("supported", True)
    if supported is False:
        return []

    operation = str(features.get("operation", "")).strip().lower()
    if operation in {"", "none", "unsupported", "unknown"}:
        return []

    values = _coerce_values(features.get("values")) or _extract_values(question) or _extract_values(model_output)
    aliases = {
        "head_insert": lambda: _linked_head_insert_steps(values),
        "head_insertion": lambda: _linked_head_insert_steps(values),
        "linked_head_insert": lambda: _linked_head_insert_steps(values),
        "tail_insert": lambda: _linked_tail_insert_steps(values),
        "tail_insertion": lambda: _linked_tail_insert_steps(values),
        "linked_tail_insert": lambda: _linked_tail_insert_steps(values),
        "linked_insert": lambda: _linked_insert_steps(values),
        "list_insert": lambda: _linked_insert_steps(values),
        "singly_insert": lambda: _linked_insert_steps(values),
        "linked_delete": lambda: _linked_delete_steps(values),
        "list_delete": lambda: _linked_delete_steps(values),
        "linked_search": lambda: _linked_search_steps(values),
        "list_search": lambda: _linked_search_steps(values),
        "linked_length": lambda: _linked_length_steps(values),
        "list_length": lambda: _linked_length_steps(values),
        "linked_reverse": lambda: _linked_reverse_steps(values),
        "list_reverse": lambda: _linked_reverse_steps(values),
        "reverse_list": lambda: _linked_reverse_steps(values),
        "circular_traverse": lambda: _circular_list_steps(values),
        "circular_list": lambda: _circular_list_steps(values),
        "seq_insert": lambda: _sequential_insert_steps(values),
        "sequential_insert": lambda: _sequential_insert_steps(values),
        "seq_delete": lambda: _sequential_delete_steps(values),
        "sequential_delete": lambda: _sequential_delete_steps(values),
    }

    builder = aliases.get(operation)
    if builder:
        return builder()

    return build_visualization(question, model_output)


def _compact(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "")
        .replace("\n", "")
        .replace("\t", "")
        .replace("；", ";")
    )


def _has_any(text: str, needles: list[str]) -> bool:
    return any(needle.lower().replace(" ", "") in text for needle in needles)


def _extract_values(text: str) -> list[int]:
    numbers = [int(item) for item in re.findall(r"(?<![A-Za-z])-?\d+", text)]
    return numbers[:8]


def _coerce_values(raw: object) -> list[int]:
    if not isinstance(raw, list):
        return []
    values: list[int] = []
    for item in raw:
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return values[:8]


def _use_values(values: list[int], fallback: list[int]) -> list[int]:
    return values if values else fallback


def explain_visualization_source(steps: list[VisualStep]) -> str:
    if not steps:
        return "暂无可演示操作"
    return steps[0].title


def render_visualization(steps: list[VisualStep], key: str, empty_message: str = "") -> None:
    if not steps:
        _render_empty_panel(empty_message)
        return

    state_key = f"{key}_step"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    current = max(0, min(st.session_state[state_key], len(steps) - 1))
    st.session_state[state_key] = current
    step = steps[current]

    _inject_demo_styles()

    with st.container(border=False):
        st.markdown(
            f"""
            <div class="ds-demo-panel">
                <div class="ds-panel-title">
                    <div class="ds-panel-icon">▶</div>
                    <div>演示</div>
                    <span class="ds-step-badge">第 {current + 1} / {len(steps)} 步</span>
                </div>
                <div class="ds-info-box">
                    <div class="ds-info-label">{step.title}</div>
                    <div class="ds-info-content">{step.note}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if step.structure == "array":
            _render_array(step)
        elif step.structure == "linked":
            _render_linked_list(step, circular=False)
        elif step.structure == "circular":
            _render_linked_list(step, circular=True)

        if step.pointer_note:
            st.markdown(
                f"""
                <div class="ds-note-box">
                    <div class="ds-info-label">提示</div>
                    <div class="ds-info-content">{step.pointer_note}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if step.code_focus:
            st.markdown(
                f"""
                <div class="ds-formula">
                    <div class="ds-code-comment">// 这一步</div>
                    <pre>{step.code_focus}</pre>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown('<div class="ds-controls-label">步骤控制</div>', unsafe_allow_html=True)
        col_prev, col_next = st.columns(2)
        with col_prev:
            if st.button("上一步", key=f"{key}_prev", disabled=current == 0):
                st.session_state[state_key] = current - 1
                st.rerun()
        with col_next:
            if st.button("下一步", key=f"{key}_next", disabled=current == len(steps) - 1):
                st.session_state[state_key] = current + 1
                st.rerun()


def _render_empty_panel(message: str = "") -> None:
    _inject_demo_styles()
    with st.container(border=False):
        st.markdown(
            f"""
            <div class="ds-demo-panel">
                <div class="ds-panel-title">
                    <div class="ds-panel-icon">▶</div>
                    <div>演示</div>
                </div>
                <div class="ds-info-box">
                    <div class="ds-info-label">等待问题</div>
                    <div class="ds-info-content">
                        {message or "问一个线性表操作后，这里会出现逐步演示。"}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _inject_demo_styles() -> None:
    st.markdown(
        """
        <style>
        .ds-demo-panel {
            background: #ffffff;
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            margin-bottom: 14px;
        }
        .ds-panel-title {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #1a1a2e;
            font-size: 20px;
            font-weight: 800;
            margin-bottom: 14px;
        }
        .ds-panel-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            background: #dbeafe;
            color: #1e40af;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }
        .ds-step-badge {
            margin-left: auto;
            font-size: 13px;
            color: #6b7280;
            background: #f3f4f6;
            border-radius: 999px;
            padding: 5px 10px;
            font-weight: 700;
        }
        .ds-info-box, .ds-note-box {
            background: #f0f9ff;
            border: 1px solid #bae6fd;
            border-radius: 10px;
            padding: 12px 15px;
            margin-bottom: 12px;
        }
        .ds-note-box {
            background: #fefce8;
            border-color: #fde68a;
        }
        .ds-info-label {
            color: #0369a1;
            font-size: 12px;
            font-weight: 800;
            margin-bottom: 5px;
        }
        .ds-info-content {
            color: #0c4a6e;
            font-size: 14px;
            line-height: 1.75;
        }
        .ds-formula {
            background: #1a1a2e;
            color: #e2e8f0;
            border-radius: 10px;
            padding: 12px 15px;
            margin: 12px 0;
        }
        .ds-formula pre {
            margin: 0;
            white-space: pre-wrap;
            font-family: Consolas, Monaco, monospace;
            font-size: 14px;
            line-height: 1.7;
        }
        .ds-code-comment {
            color: #94a3b8;
            font-family: Consolas, Monaco, monospace;
            font-size: 12px;
            margin-bottom: 6px;
        }
        .ds-controls-label {
            color: #666;
            font-size: 13px;
            margin: 14px 0 8px;
        }
        div.stButton > button {
            border-radius: 8px;
            border: none;
            background: #4f46e5;
            color: white;
            font-size: 14px;
            padding: 8px 18px;
            transition: all 0.2s;
        }
        div.stButton > button:hover {
            background: #4338ca;
            color: white;
        }
        div.stButton > button:disabled {
            background: #e5e7eb;
            color: #9ca3af;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_array(step: VisualStep) -> None:
    cells = []
    for index, value in enumerate(step.values):
        classes = "array-cell"
        if step.highlight_index == index:
            classes += " active"
        cells.append(f"<div class='{classes}'><span>{value}</span><small>{index}</small></div>")

    extra = ""
    if step.extra_value is not None:
        extra = f"<div class='extra-cell'>待处理：{step.extra_value}</div>"

    st.markdown(
        f"""
        <style>
        .array-wrap {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
            margin: 12px 0 14px;
            padding: 14px;
            background: #f8f9fa;
            border-radius: 12px;
        }}
        .array-cell {{
            width: 58px; height: 58px; border: 2px solid #e5e7eb; border-radius: 8px;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: white; color: #1a1a2e; font-weight: 800;
            font-family: Consolas, Monaco, monospace;
            transition: all 0.25s;
        }}
        .array-cell small {{ color: #9ca3af; font-weight: 700; margin-top: 2px; }}
        .array-cell.active {{
            border-color: #f59e0b;
            background: #fef3c7;
            color: #92400e;
            transform: scale(1.05);
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.28);
        }}
        .extra-cell {{
            padding: 10px 12px; border: 2px dashed #10b981; border-radius: 8px;
            background: #d1fae5; color: #065f46; font-weight: 800;
            font-family: Consolas, Monaco, monospace;
        }}
        </style>
        <div class="array-wrap">{''.join(cells)}{extra}</div>
        """,
        unsafe_allow_html=True,
    )


def _render_linked_list(step: VisualStep, circular: bool) -> None:
    nodes = ["<div class='head-node'>head</div>"]
    for index, value in enumerate(step.values):
        classes = "list-node"
        if step.highlight_index == index:
            classes += " active"
        nodes.append("<div class='arrow'>→</div>")
        nodes.append(f"<div class='{classes}'>{value}</div>")

    if circular:
        nodes.append("<div class='arrow'>↺ head</div>")
    else:
        nodes.append("<div class='arrow'>→ NULL</div>")

    extra = ""
    if step.extra_value is not None:
        extra = f"<div class='new-node'>新结点 s：{step.extra_value}</div>"

    st.markdown(
        f"""
        <style>
        .list-wrap {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
            margin: 12px 0 14px;
            padding: 14px;
            background: #f8f9fa;
            border-radius: 12px;
        }}
        .head-node, .list-node, .new-node {{
            min-width: 58px; height: 42px; padding: 0 10px; border-radius: 8px;
            display: flex; align-items: center; justify-content: center; font-weight: 800;
            font-family: Consolas, Monaco, monospace;
            transition: all 0.25s;
        }}
        .head-node {{ background: #dbeafe; border: 2px solid #3b82f6; color: #1e40af; }}
        .list-node {{ background: white; border: 2px solid #e5e7eb; color: #1a1a2e; }}
        .list-node.active {{
            background: #fef3c7;
            border-color: #f59e0b;
            color: #92400e;
            transform: scale(1.05);
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.28);
        }}
        .new-node {{ background: #d1fae5; border: 2px dashed #10b981; color: #065f46; margin-left: 4px; }}
        .arrow {{ color: #9ca3af; font-weight: 800; }}
        </style>
        <div class="list-wrap">{''.join(nodes)}{extra}</div>
        """,
        unsafe_allow_html=True,
    )


def _sequential_insert_steps(values: list[int] | None = None) -> list[VisualStep]:
    base = _use_values(values or [], [10, 20, 30, 40])
    return [
        VisualStep("初始顺序表", "准备在第 3 个位置插入 99。", base, "array", extra_value=99, code_focus="int i = 3, x = 99;"),
        VisualStep("从后往前移动", "先把 40 后移一格，避免覆盖前面的元素。", [10, 20, 30, 40, 40], "array", 4, 99, code_focus="for (j = L->length; j >= i; j--)"),
        VisualStep("继续移动", "再把 30 后移一格，腾出第 3 个位置。", [10, 20, 30, 30, 40], "array", 3, 99, code_focus="L->data[j] = L->data[j - 1];"),
        VisualStep("放入新元素", "把 99 放到下标 2，也就是第 3 个位置。", [10, 20, 99, 30, 40], "array", 2, code_focus="L->data[i - 1] = x;\nL->length++;"),
    ]


def _sequential_delete_steps(values: list[int] | None = None) -> list[VisualStep]:
    base = _use_values(values or [], [10, 20, 30, 40, 50])
    return [
        VisualStep("初始顺序表", "准备删除第 2 个元素。", base, "array", 1 if len(base) > 1 else 0, code_focus="int i = 2;"),
        VisualStep("后继元素前移", "把 30 前移，覆盖被删位置。", [10, 30, 30, 40, 50], "array", 1, code_focus="L->data[i - 1] = L->data[i];"),
        VisualStep("继续前移", "把 40 前移。", [10, 30, 40, 40, 50], "array", 2, code_focus="L->data[j - 1] = L->data[j];"),
        VisualStep("长度减一", "把 50 前移后，逻辑长度减 1。", [10, 30, 40, 50], "array", 3, code_focus="L->length--;"),
    ]


def _linked_insert_steps(values: list[int] | None = None) -> list[VisualStep]:
    return [
        VisualStep("初始单链表", "准备在 20 后面插入新结点 99。", [10, 20, 30], "linked", code_focus="p = head;"),
        VisualStep("找到前驱 p", "先找到插入位置的前驱结点 p，这里 p 指向 20。", [10, 20, 30], "linked", 1, code_focus="while (j < i - 1) p = p->next;"),
        VisualStep("创建新结点 s", "申请新结点 s，并把数据域设为 99。", [10, 20, 30], "linked", 1, 99, code_focus="s = malloc(sizeof(LNode));\ns->data = 99;"),
        VisualStep("连接新结点后继", "执行 s->next = p->next，让 99 先指向 30。", [10, 20, 30], "linked", 2, 99, "关键：先接住原来的后继结点，避免链断掉。", "s->next = p->next;"),
        VisualStep("前驱指向新结点", "执行 p->next = s，插入完成。", [10, 20, 99, 30], "linked", 2, code_focus="p->next = s;"),
    ]


def _linked_tail_insert_steps(values: list[int] | None = None) -> list[VisualStep]:
    base = _use_values(values or [], [10, 20])
    shown = base[:2] if len(base) >= 2 else base
    insert_value = base[2] if len(base) >= 3 else 30
    return [
        VisualStep("尾插法初始状态", "使用尾指针 r 指向当前链表最后一个结点。", shown, "linked", max(0, len(shown) - 1), code_focus="r = head;"),
        VisualStep("创建新结点 s", f"申请新结点 s，并写入新数据 {insert_value}。", shown, "linked", max(0, len(shown) - 1), insert_value, code_focus="s = malloc(sizeof(LNode));\ns->data = x;"),
        VisualStep("尾结点接上 s", "执行 r->next = s，把新结点接到当前尾结点后面。", shown + [insert_value], "linked", len(shown), code_focus="r->next = s;"),
        VisualStep("移动尾指针", "执行 r = s，让 r 重新指向新的尾结点。", shown + [insert_value], "linked", len(shown), code_focus="r = s;"),
        VisualStep("尾指针收尾", "尾插完成后，新尾结点的 next 应指向 NULL。", shown + [insert_value], "linked", len(shown), code_focus="r->next = NULL;"),
    ]


def _linked_head_insert_steps(values: list[int] | None = None) -> list[VisualStep]:
    base = _use_values(values or [], [10, 20, 30])
    existing = list(reversed(base[:2])) if len(base) >= 2 else base[:]
    insert_value = base[2] if len(base) >= 3 else 30
    return [
        VisualStep("头插法初始状态", "每次把新结点插到头结点 head 后面。", existing, "linked", code_focus="p = head;"),
        VisualStep("创建新结点 s", f"申请新结点 s，并写入新数据 {insert_value}。", existing, "linked", 0 if existing else None, insert_value, code_focus="s = malloc(sizeof(LNode));\ns->data = x;"),
        VisualStep("新结点接原首元结点", "先让 s 指向原来的第一个数据结点。", existing, "linked", 0 if existing else None, insert_value, "关键：先接住原首元结点，否则原链表会断。", "s->next = head->next;"),
        VisualStep("头结点指向 s", "再让 head 指向 s，新结点成为首元结点。", [insert_value] + existing, "linked", 0, code_focus="head->next = s;"),
        VisualStep("头插完成", "头插法会让输入顺序反过来。", [insert_value] + existing, "linked", 0, code_focus="head -> s -> 原首元结点"),
    ]


def _linked_delete_steps(values: list[int] | None = None) -> list[VisualStep]:
    return [
        VisualStep("初始单链表", "准备删除结点 20。", [10, 20, 30], "linked", 1, code_focus="int i = 2;"),
        VisualStep("找到前驱 p", "要删除 20，先找到它的前驱 10。", [10, 20, 30], "linked", 0, code_focus="while (j < i - 1) p = p->next;"),
        VisualStep("保存待删结点 q", "令 q = p->next，此时 q 指向 20。", [10, 20, 30], "linked", 1, code_focus="q = p->next;"),
        VisualStep("跨过待删结点", "执行 p->next = q->next，让 10 直接指向 30。", [10, 30], "linked", 0, code_focus="p->next = q->next;"),
        VisualStep("释放 q", "释放 20 所在结点，删除完成。", [10, 30], "linked", code_focus="free(q);"),
    ]


def _circular_list_steps(values: list[int] | None = None) -> list[VisualStep]:
    return [
        VisualStep("循环链表结构", "尾结点不指向 NULL，而是回到 head。", [10, 20, 30], "circular", code_focus="tail->next = head;"),
        VisualStep("从首元结点开始", "p 从 10 出发，沿 next 访问。", [10, 20, 30], "circular", 0, code_focus="p = head->next;"),
        VisualStep("继续访问", "p 移动到 20。", [10, 20, 30], "circular", 1, code_focus="p = p->next;"),
        VisualStep("回到头结点时结束", "访问完 30 后，next 回到 head，遍历结束。", [10, 20, 30], "circular", 2, code_focus="while (p != head)"),
    ]


def _linked_length_steps(values: list[int] | None = None) -> list[VisualStep]:
    return [
        VisualStep("初始化计数", "count = 0，p 指向首元结点。", [10, 20, 30], "linked", 0, code_focus="count = 0;\np = head->next;"),
        VisualStep("访问 10", "count = 1，p 后移。", [10, 20, 30], "linked", 0, code_focus="count++;\np = p->next;"),
        VisualStep("访问 20", "count = 2，p 后移。", [10, 20, 30], "linked", 1, code_focus="count++;\np = p->next;"),
        VisualStep("访问 30", "count = 3，p 后移到 NULL。", [10, 20, 30], "linked", 2, code_focus="while (p != NULL)"),
    ]


def _linked_search_steps(values: list[int] | None = None) -> list[VisualStep]:
    return [
        VisualStep("从头开始查找", "目标值设为 30，p 指向首元结点 10。", [10, 20, 30], "linked", 0, code_focus="p = head->next;"),
        VisualStep("比较 10", "10 不是目标，p 后移。", [10, 20, 30], "linked", 0, code_focus="if (p->data == x)"),
        VisualStep("比较 20", "20 不是目标，p 后移。", [10, 20, 30], "linked", 1, code_focus="p = p->next;"),
        VisualStep("找到 30", "p->data == 30，查找成功。", [10, 20, 30], "linked", 2, code_focus="return p;"),
    ]


def _linked_reverse_steps(values: list[int] | None = None) -> list[VisualStep]:
    base = _use_values(values or [], [10, 12, 15, 39, 49])
    steps = [
        VisualStep(
            "逆置前链表",
            f"你的链表是：{' -> '.join(map(str, base))} -> NULL。准备使用三指针法逆置。",
            base,
            "linked",
            0 if base else None,
            code_focus="prev = NULL;\ncur = head->next;",
        )
    ]

    reversed_prefix: list[int] = []
    for index, value in enumerate(base):
        remaining = base[index + 1 :]
        reversed_prefix = [value] + reversed_prefix
        note = f"处理结点 {value}：先保存 next，再让当前结点指回 prev。"
        if remaining:
            note += f" 未处理部分还有：{' -> '.join(map(str, remaining))}。"
        else:
            note += " 此时所有结点都已处理。"
        steps.append(
            VisualStep(
                f"反转结点 {value}",
                note,
                reversed_prefix,
                "linked",
                0,
                pointer_note=f"已反转部分：{' -> '.join(map(str, reversed_prefix))} -> NULL",
                code_focus="next = cur->next;\ncur->next = prev;\nprev = cur;\ncur = next;",
            )
        )

    steps.append(
        VisualStep(
            "更新头结点",
            "令 head->next = prev，链表逆置完成。",
            list(reversed(base)),
            "linked",
            0 if base else None,
            code_focus="head->next = prev;",
        )
    )
    return steps
