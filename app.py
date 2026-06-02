from __future__ import annotations

import json
import os
import re
from pathlib import Path

import streamlit as st

from code_checker import check_c_code_in_answer
from llm import DeepSeekClient, DeepSeekError, load_dotenv
from rag import MarkdownKeywordRetriever
from visualizer.dispatcher import dispatch
from visualizer.intent_parser import parse_operation_request
from visualizer.protocol import Clarification, OperationRequest
from visualizer.renderers.html_renderer import render_step_html, render_styles


BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
SYSTEM_PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"
CODE_BLOCK_PATTERN = r"```(?:c|C)\s*.*?```"


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def build_user_prompt(
    question: str,
    contexts: list[dict[str, str]],
) -> str:
    context_text = "\n\n".join(
        f"【资料 {index} | {item['source']}】\n{item['content']}"
        for index, item in enumerate(contexts, start=1)
    )
    if not context_text:
        context_text = "未检索到高相关资料。"

    return f"""下面是从本地 Markdown 知识库检索到的资料：

{context_text}

用户问题：
{question}

请严格依据上面的本地教材知识库片段回答。若资料不足，只说明“知识库资料不足，需要补充教材内容”，不要自由扩展未检索到的知识。
回答要自然、紧凑，像助教直接讲题，不要写成报告。
无论用户是否明确要求代码，都要在回答末尾给出一个简短的 C 语言代码块，供网页演示板和自动检查使用。"""


def build_conversation_context(messages: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "user"))
        label = "用户" if role == "user" else "助教"
        content = str(message.get("content", "")).strip()
        code_blocks = message.get("code_blocks")
        if code_blocks:
            content = content + "\n" + "\n".join(str(block) for block in code_blocks)
        if content:
            lines.append(f"{label}：{content}")
    return "\n\n".join(lines)


def build_chat_history_messages(messages: list[dict[str, object]]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content", "")).strip()
        code_blocks = message.get("code_blocks")
        if code_blocks:
            content = content + "\n" + "\n".join(str(block) for block in code_blocks)
        if content:
            history.append({"role": role, "content": content})
    return history


def render_contexts(contexts: list[dict[str, str]]) -> None:
    with st.expander("本次检索到的知识库片段", expanded=False):
        if not contexts:
            st.info("没有检索到明显相关的片段。")
            return

        for index, item in enumerate(contexts, start=1):
            st.markdown(f"**{index}. {item['source']}**")
            st.caption(f"匹配分数：{item['score']}")
            st.markdown(item["content"])
            st.divider()


def render_chat_messages(messages: list[dict[str, object]]) -> None:
    if not messages:
        st.info("问个线性表问题试试。")
        return

    for message in messages:
        with st.chat_message(str(message["role"])):
            st.markdown(str(message["content"]))
            code_blocks = message.get("code_blocks")
            if code_blocks:
                with st.expander("C 语言代码", expanded=bool(message.get("show_code", False))):
                    for code_block in code_blocks:
                        st.markdown(str(code_block))
            code_check = message.get("code_check")
            if code_check:
                with st.expander("C 代码自动检测结果", expanded=False):
                    st.markdown(str(code_check))


def user_wants_code(question: str) -> bool:
    code_words = ["代码", "程序", "实现", "完整", "可运行", "c语言", "c 语言"]
    return any(word in question.lower() for word in code_words)


def split_code_blocks(answer: str) -> tuple[str, list[str]]:
    import re

    code_blocks = re.findall(CODE_BLOCK_PATTERN, answer, flags=re.DOTALL)
    visible_answer = re.sub(CODE_BLOCK_PATTERN, "", answer, flags=re.DOTALL)
    return visible_answer, code_blocks


def make_teaching_view(answer: str, show_code: bool) -> tuple[str, list[str]]:
    import re

    visible_answer, code_blocks = split_code_blocks(answer)
    if show_code:
        return answer, []

    visible_answer = re.sub(
        r"(?ims)(^#{1,4}\s*C\s*语言代码\s*$|^\*\*C\s*语言代码\*\*\s*$|^C\s*语言代码[:：]?\s*$).*?(?=^#{1,4}\s+|^\*\*[^*\n]+?\*\*\s*$|\Z)",
        "",
        visible_answer,
    )
    visible_answer = re.sub(r"\n{3,}", "\n\n", visible_answer).strip()
    return visible_answer, code_blocks


def question_may_need_demo(question: str) -> bool:
    demo_words = [
        "演示",
        "展示",
        "可视化",
        "动画",
        "一步步",
        "逐步",
        "插入",
        "删除",
        "查找",
        "入栈",
        "出栈",
        "入队",
        "出队",
        "push",
        "pop",
        "enqueue",
        "dequeue",
    ]
    return any(word in question.lower() for word in demo_words)


def render_current_trace_demo() -> None:
    trace = st.session_state.get("dsvp_trace")
    request = st.session_state.get("dsvp_request")
    clarification = st.session_state.get("dsvp_clarification")

    st.markdown("### 当前演示")
    if clarification:
        st.caption("从对话中检测到演示意图，但参数还不完整。")
        st.warning(clarification.message)
        if clarification.missing_fields:
            st.caption("缺少字段：" + ", ".join(clarification.missing_fields))
        return

    if trace is None:
        st.caption("在对话中提出“演示/逐步展示插入删除查找”等需求后，这里会自动出现步骤。")
        return

    steps = trace.steps
    if not steps:
        st.caption("本地模拟器没有生成步骤。")
        return

    if "dsvp_step" not in st.session_state:
        st.session_state.dsvp_step = 0
    current = max(0, min(int(st.session_state.dsvp_step), len(steps) - 1))
    st.session_state.dsvp_step = current
    step = steps[current]

    st.caption(trace.title)
    if request is not None:
        with st.expander("OperationRequest JSON", expanded=False):
            st.json(json.loads(request.model_dump_json(by_alias=True)))

    if trace.errors:
        for error in trace.errors:
            st.error(f"{error.code}：{error.message} {error.detail}")
    if trace.warnings:
        for warning in trace.warnings:
            st.warning(f"{warning.code}：{warning.message} {warning.detail}")

    st.markdown(render_styles(), unsafe_allow_html=True)
    st.caption(f"第 {current + 1} / {len(steps)} 步")
    st.markdown(render_step_html(step), unsafe_allow_html=True)
    st.markdown("**当前步骤解释**")
    st.write(step.description)
    st.markdown("**当前关键操作**")
    if step.actions:
        for action in step.actions:
            st.write(f"- {action.description}")
    else:
        st.write("暂无关键操作。")

    prev_col, next_col, reset_col = st.columns(3)
    with prev_col:
        if st.button("上一步", disabled=current == 0, key="chat_demo_prev"):
            st.session_state.dsvp_step = current - 1
            st.rerun()
    with next_col:
        if st.button("下一步", disabled=current == len(steps) - 1, key="chat_demo_next"):
            st.session_state.dsvp_step = current + 1
            st.rerun()
    with reset_col:
        if st.button("重置", key="chat_demo_reset"):
            st.session_state.dsvp_step = 0
            st.rerun()

    with st.expander("步骤列表", expanded=False):
        for index, item in enumerate(steps):
            prefix = "-> " if index == current else ""
            st.write(f"{prefix}{item.step_id}. {item.title}")


def main() -> None:
    load_dotenv()

    st.set_page_config(page_title="本科数据结构知识 Agent MVP", page_icon="📚")
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            height: 100vh;
            overflow: hidden;
        }
        [data-testid="stMainBlockContainer"] {
            max-width: 1440px;
            padding-top: 1.5rem;
            padding-bottom: 1rem;
            height: 100vh;
            overflow: hidden;
        }
        [data-testid="column"]:nth-of-type(2) > div {
            height: calc(100vh - 8.5rem);
            overflow: auto;
        }
        .stChatMessage {
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            padding: 0.25rem 0.5rem;
            background: #ffffff;
        }
        section[data-testid="stChatInput"] {
            position: static;
        }
        @media (max-width: 900px) {
            html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
                height: auto;
                min-height: 100vh;
                overflow: auto;
            }
            [data-testid="stMainBlockContainer"] {
                height: auto;
                min-height: 100vh;
                overflow: visible;
                padding: 1rem 0.75rem 1rem;
            }
            [data-testid="column"]:nth-of-type(2) > div {
                height: auto;
                max-height: none;
                overflow: visible;
            }
            .st-key-chat_scroll {
                max-height: 52vh;
                overflow-y: auto;
            }
            .st-key-demo_panel {
                max-height: none;
                overflow: visible;
            }
            h1 {
                font-size: 1.6rem !important;
            }
            h3 {
                font-size: 1.15rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("本科数据结构知识 Agent MVP")
    st.caption("当前范围：第 2 章线性表。默认中文回答，默认 C 语言代码。")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "last_contexts" not in st.session_state:
        st.session_state.last_contexts = []

    if "dsvp_request" not in st.session_state:
        st.session_state.dsvp_request = None

    if "dsvp_trace" not in st.session_state:
        st.session_state.dsvp_trace = None

    if "dsvp_step" not in st.session_state:
        st.session_state.dsvp_step = 0

    if "dsvp_clarification" not in st.session_state:
        st.session_state.dsvp_clarification = None

    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False

    if "pending_question" not in st.session_state:
        st.session_state.pending_question = ""

    if "pending_contexts" not in st.session_state:
        st.session_state.pending_contexts = []

    with st.sidebar:
        st.header("运行状态")
        st.write("知识库目录：`knowledge/`")
        st.write("检索：knowledge / Top 3")
        st.write("模型：DeepSeek Chat")

        if os.getenv("DEEPSEEK_API_KEY"):
            st.success("已检测到 DEEPSEEK_API_KEY")
        else:
            st.warning("未检测到 DEEPSEEK_API_KEY。建议在项目根目录创建 `.env` 文件。")

        st.divider()
        st.markdown("上下文：")
        st.caption(f"将发送完整历史对话：{len(st.session_state.messages)} 条")
        if st.button("清空"):
            st.session_state.messages = []
            st.session_state.last_contexts = []
            st.session_state.pending_question = ""
            st.session_state.pending_contexts = []
            st.session_state.is_generating = False
            st.session_state.dsvp_request = None
            st.session_state.dsvp_trace = None
            st.session_state.dsvp_step = 0
            st.session_state.dsvp_clarification = None
            st.rerun()

        st.divider()
        st.markdown("示例：")
        st.markdown("- 单链表插入怎么演示？")
        st.markdown("- 写一个顺序表删除的完整 C 代码")
        st.markdown("- 循环链表和单链表有什么区别？")
        st.divider()
        render_contexts(st.session_state.last_contexts)

    chat_col, demo_col = st.columns([1.35, 1], gap="large")

    with demo_col:
        demo_placeholder = st.empty()
        with demo_placeholder.container():
            with st.container(key="demo_panel"):
                render_current_trace_demo()

    with chat_col:
        st.markdown("### 对话")
        with st.container(height=560, border=True, key="chat_scroll"):
            render_chat_messages(st.session_state.messages)
            if st.session_state.pending_question:
                with st.chat_message("assistant"):
                    st.markdown("翻教材中...")

        question = st.chat_input("问一个线性表问题")
    if question and not st.session_state.is_generating and not st.session_state.pending_question:
        retriever = MarkdownKeywordRetriever(KNOWLEDGE_DIR)
        conversation_context = build_conversation_context(st.session_state.messages)
        retrieval_query = f"{question}\n此前完整对话上下文：{conversation_context}" if conversation_context else question
        contexts = retriever.retrieve(retrieval_query, top_k=3)
        st.session_state.last_contexts = contexts
        st.session_state.messages.append({"role": "user", "content": question})
        st.session_state.pending_question = question
        st.session_state.pending_contexts = contexts
        st.rerun()

    if not st.session_state.pending_question or st.session_state.is_generating:
        return

    st.session_state.is_generating = True
    question = st.session_state.pending_question
    contexts = st.session_state.pending_contexts
    prior_messages = st.session_state.messages[:-1]
    conversation_context = build_conversation_context(prior_messages)

    try:
        client = DeepSeekClient()
    except DeepSeekError as exc:
        answer = f"调用 DeepSeek API 失败：{exc}"
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.pending_question = ""
        st.session_state.pending_contexts = []
        st.session_state.is_generating = False
        st.rerun()
        return

    if question_may_need_demo(question):
        parse_text = (
            f"此前完整对话上下文：\n{conversation_context}\n\n"
            f"用户新问题：\n{question}"
        )
        parsed_demo = parse_operation_request(client, parse_text)
        if isinstance(parsed_demo, OperationRequest):
            st.session_state.dsvp_request = parsed_demo
            st.session_state.dsvp_trace = dispatch(parsed_demo)
            st.session_state.dsvp_step = 0
            st.session_state.dsvp_clarification = None
        elif any(word in question for word in ["演示", "展示", "可视化", "一步步", "逐步"]):
            st.session_state.dsvp_clarification = parsed_demo
            st.session_state.dsvp_request = None
            st.session_state.dsvp_trace = None
            st.session_state.dsvp_step = 0

    if not contexts:
        if st.session_state.dsvp_trace is not None:
            answer = "已根据你的对话在右侧生成本地演示步骤。知识库没有检索到高相关片段，所以文字讲解我先不扩展。"
        else:
            answer = "这块教材笔记还没补到，我先不乱讲。"
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.pending_question = ""
        st.session_state.pending_contexts = []
        st.session_state.is_generating = False
        st.rerun()
        return

    messages = [
        {"role": "system", "content": load_system_prompt()},
        *build_chat_history_messages(prior_messages),
        {
            "role": "user",
            "content": build_user_prompt(
                question,
                contexts,
            ),
        },
    ]

    try:
        answer = client.chat(messages)
    except DeepSeekError as exc:
        answer = f"调用 DeepSeek API 失败：{exc}"
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.pending_question = ""
        st.session_state.pending_contexts = []
        st.session_state.is_generating = False
        st.rerun()
        return

    show_code = user_wants_code(question)
    code_check = (
        check_c_code_in_answer(answer)
        if show_code
        else check_c_code_in_answer(None)
    )

    if show_code and code_check.needs_fix:
        fix_messages = messages + [
            {"role": "assistant", "content": answer},
            {
                "role": "user",
                "content": (
                    "你刚才生成的 C 代码编译或运行失败。"
                    "请根据下面错误信息修正，并重新输出完整回答和完整可运行 C 代码。"
                    "不要提到“重新检查”“修正版”等过程说明，直接给学生最终答案。\n\n"
                    f"{code_check.summary}"
                ),
            },
        ]
        try:
            answer = client.chat(fix_messages)
            code_check = check_c_code_in_answer(answer)
        except DeepSeekError as exc:
            code_check.summary += f"\n\n二次修正调用失败：{exc}"

    visible_answer, code_blocks = make_teaching_view(answer, user_wants_code(question))
    message_id = len(st.session_state.messages)
    st.session_state.messages.append(
        {
            "id": message_id,
            "role": "assistant",
            "content": answer if user_wants_code(question) else visible_answer,
            "code_blocks": code_blocks if not user_wants_code(question) else [],
            "show_code": user_wants_code(question),
            "code_check": code_check.summary if code_check.has_code else "",
        }
    )
    st.session_state.pending_question = ""
    st.session_state.pending_contexts = []
    st.session_state.is_generating = False
    st.rerun()


if __name__ == "__main__":
    main()
