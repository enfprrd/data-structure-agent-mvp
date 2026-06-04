from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
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
FOLLOW_UP_DEMO_PATTERN = re.compile(r"^(演示|展示|继续|来|讲|看|跑|播放|可视化).{0,12}(一下|下|呗|吧|看看|演示)?[。！!？?~～]*$")
GENERATION_STALE_SECONDS = 45
VERSION_FILE_PATTERNS = [
    "*.py",
    "*.md",
    "*.txt",
    "knowledge/*.md",
    "prompts/*.txt",
    "visualizer/**/*.py",
]


def build_app_version() -> str:
    latest_mtime = Path(__file__).stat().st_mtime
    for pattern in VERSION_FILE_PATTERNS:
        for path in BASE_DIR.glob(pattern):
            if path.is_file():
                latest_mtime = max(latest_mtime, path.stat().st_mtime)

    modified_at = datetime.fromtimestamp(latest_mtime)
    return f"dev-{modified_at:%Y%m%d-%H%M}"


APP_VERSION = build_app_version()


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
回答要像课堂助教讲题：先解释核心概念，再讲操作过程，最后点出易错点；不要只给一两句结论。
如果用户问的是演示、插入、删除、查找、建表、代码运行过程，回答至少包含：
- 本次例子的初始状态和目标
- 操作过程的分步解释
- 每个关键指针或数组移动为什么这么做
- 最终结果
- 1 到 3 个易错点
如果用户是在要求演示、展示、逐步操作、继续演示，或问题具有演示意图，回答末尾必须给出一个完整可运行的 C 程序：
- 必须包含 #include、结构体定义、核心操作函数、打印函数和 main。
- main 中的数据、操作和值必须和你的文字讲解完全一致。
- 文字讲解中必须明确写出：初始数据、数据结构、操作类型，以及 position/value/target 等操作参数。
- 这份 C 代码会作为右侧演示板理解演示意图和参数的依据。
如果用户不是在要求演示，也没有明确要求完整代码，回答末尾保留一个简短 C 语言代码块即可。"""


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


def build_effective_question(question: str, messages: list[dict[str, object]]) -> str:
    current = question.strip()
    if not _is_follow_up_demo_question(current):
        return current

    previous_topic = _last_user_topic(messages)
    if not previous_topic:
        return current
    return f"{_demo_topic_query(previous_topic)}\n追问：{current}"


def _is_follow_up_demo_question(question: str) -> bool:
    compact = re.sub(r"\s+", "", question)
    if FOLLOW_UP_DEMO_PATTERN.fullmatch(compact):
        return True
    return compact in {"演示一下", "演示一下呗", "展示一下", "继续演示", "可视化一下"}


def _last_user_topic(messages: list[dict[str, object]]) -> str:
    for message in reversed(messages):
        if str(message.get("role")) != "user":
            continue
        content = str(message.get("content", "")).strip()
        if content and not _is_follow_up_demo_question(content):
            return content
    return ""


def _demo_topic_query(topic: str) -> str:
    compact = re.sub(r"(的)?(时间|空间)?复杂度(是多少|如何分析|怎么分析)?", "", topic)
    compact = compact.replace("时间空间", "").replace("时间和空间", "")
    if "归并算法" in compact and "归并排序" not in compact:
        compact += " 归并排序"
    return f"{compact} 演示 排序过程 操作步骤"


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
        st.info("问个数据结构课问题试试。")
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


def finish_generation() -> None:
    st.session_state.pending_question = ""
    st.session_state.pending_effective_question = ""
    st.session_state.pending_contexts = []
    st.session_state.is_generating = False
    st.session_state.generation_started_at = 0.0


def render_current_trace_demo() -> None:
    trace = st.session_state.get("dsvp_trace")
    request = st.session_state.get("dsvp_request")
    clarification = st.session_state.get("dsvp_clarification")

    st.markdown("### 当前演示")
    if clarification:
        st.caption("从对话中检测到演示意图，但 DeepSeek 生成的演示 JSON 没有通过本地自检。")
        st.warning(clarification.message)
        if clarification.missing_fields:
            st.caption("缺失或不合法字段：" + ", ".join(clarification.missing_fields))
        if clarification.raw:
            with st.expander("本地自检详情", expanded=False):
                st.code(clarification.raw)
        return

    if trace is None:
        st.caption("在对话中提出“演示/逐步展示”等需求后，这里会自动出现步骤或支持状态。")
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

    prev_col, next_col, reset_col = st.columns(3)
    with prev_col:
        if st.button("上一步", disabled=current == 0, key="chat_demo_prev"):
            st.session_state.dsvp_autoplay = False
            st.session_state.dsvp_step = current - 1
            st.rerun()
    with next_col:
        if st.button("下一步", disabled=current == len(steps) - 1, key="chat_demo_next"):
            st.session_state.dsvp_autoplay = False
            st.session_state.dsvp_step = current + 1
            st.rerun()
    with reset_col:
        if st.button("重置", key="chat_demo_reset"):
            st.session_state.dsvp_autoplay = False
            st.session_state.dsvp_step = 0
            st.rerun()
    autoplay = st.toggle("自动播放", value=bool(st.session_state.get("dsvp_autoplay", False)), key="chat_demo_autoplay")
    st.session_state.dsvp_autoplay = autoplay

    if st.session_state.get("dsvp_autoplay"):
        if current < len(steps) - 1:
            time.sleep(0.8)
            st.session_state.dsvp_step = current + 1
            st.rerun()
        else:
            st.session_state.dsvp_autoplay = False

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
            height: 100dvh;
            overflow: hidden;
        }
        [data-testid="stMainBlockContainer"] {
            max-width: 1680px;
            padding-top: clamp(0.75rem, 1.6vh, 1.5rem);
            padding-bottom: 0.75rem;
            height: 100dvh;
            overflow: hidden;
        }
        .st-key-demo_panel {
            height: calc(100dvh - 9.25rem);
            min-height: 360px;
            overflow-y: auto;
            overflow-x: hidden;
            overscroll-behavior: contain;
            padding-right: 0.35rem;
        }
        .st-key-demo_panel [data-testid="stVerticalBlock"] {
            gap: 0.55rem;
        }
        .st-key-chat_scroll {
            height: min(560px, calc(100dvh - 18rem)) !important;
            min-height: 300px;
            overflow-y: auto;
            overscroll-behavior: contain;
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
        @media (max-height: 820px) and (min-width: 901px) {
            [data-testid="stMainBlockContainer"] {
                padding-top: 0.65rem;
            }
            h1 {
                font-size: 2.15rem !important;
                margin-bottom: 0.35rem !important;
            }
            h3 {
                margin-top: 0.45rem !important;
                margin-bottom: 0.45rem !important;
            }
            .st-key-demo_panel {
                height: calc(100dvh - 7.75rem);
                min-height: 300px;
            }
            .st-key-chat_scroll {
                height: calc(100dvh - 15.75rem) !important;
                min-height: 260px;
            }
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
            .st-key-chat_scroll {
                height: 45dvh !important;
                min-height: 260px;
                max-height: 520px;
                overflow-y: auto;
                overscroll-behavior: contain;
            }
            .st-key-demo_panel {
                height: 58dvh;
                min-height: 320px;
                max-height: 620px;
                overflow-y: auto;
                overflow-x: hidden;
                overscroll-behavior: contain;
                border-bottom: 1px solid #e5e7eb;
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
    st.caption(f"当前范围：整门本科数据结构课程知识库。默认中文回答，默认 C 语言代码。版本：{APP_VERSION}")

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

    if "dsvp_autoplay" not in st.session_state:
        st.session_state.dsvp_autoplay = False

    if "dsvp_clarification" not in st.session_state:
        st.session_state.dsvp_clarification = None

    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False

    if "generation_started_at" not in st.session_state:
        st.session_state.generation_started_at = 0.0

    if "pending_question" not in st.session_state:
        st.session_state.pending_question = ""

    if "pending_effective_question" not in st.session_state:
        st.session_state.pending_effective_question = ""

    if "pending_contexts" not in st.session_state:
        st.session_state.pending_contexts = []

    with st.sidebar:
        st.header("运行状态")
        st.write("知识库目录：`knowledge/`")
        st.write("检索：knowledge / Top 3")
        st.write("模型：DeepSeek Chat")
        st.write(f"版本：`{APP_VERSION}`")

        if os.getenv("DEEPSEEK_API_KEY"):
            st.success("已检测到 DEEPSEEK_API_KEY")
        else:
            st.warning("未检测到 DEEPSEEK_API_KEY。建议在项目根目录创建 `.env` 文件。")

        st.divider()
        st.markdown("上下文：")
        st.caption(f"将发送完整历史对话：{len(st.session_state.messages)} 条")
        if st.session_state.pending_question:
            st.caption(f"待处理问题：{st.session_state.pending_question}")
        if st.button("恢复生成状态"):
            finish_generation()
            st.rerun()
        if st.button("清空"):
            st.session_state.messages = []
            st.session_state.last_contexts = []
            st.session_state.pending_question = ""
            st.session_state.pending_effective_question = ""
            st.session_state.pending_contexts = []
            st.session_state.is_generating = False
            st.session_state.generation_started_at = 0.0
            st.session_state.dsvp_request = None
            st.session_state.dsvp_trace = None
            st.session_state.dsvp_step = 0
            st.session_state.dsvp_autoplay = False
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

        question = st.chat_input("问一个数据结构课问题")
    if question and not st.session_state.pending_question:
        retriever = MarkdownKeywordRetriever(KNOWLEDGE_DIR)
        effective_question = build_effective_question(question, st.session_state.messages)
        contexts = retriever.retrieve(effective_question, top_k=3)
        st.session_state.last_contexts = contexts
        st.session_state.messages.append({"role": "user", "content": question})
        st.session_state.pending_question = question
        st.session_state.pending_effective_question = effective_question
        st.session_state.pending_contexts = contexts
        st.rerun()

    if not st.session_state.pending_question:
        return

    st.session_state.is_generating = True
    st.session_state.generation_started_at = time.time()
    question = st.session_state.pending_question
    effective_question = st.session_state.get("pending_effective_question") or question
    contexts = st.session_state.pending_contexts
    prior_messages = st.session_state.messages[:-1]
    conversation_context = build_conversation_context(prior_messages)

    try:
        client = DeepSeekClient()
    except DeepSeekError as exc:
        answer = f"调用 DeepSeek API 失败：{exc}"
        st.session_state.messages.append({"role": "assistant", "content": answer})
        finish_generation()
        st.rerun()
        return

    if not contexts:
        answer = "知识库资料不足，需要补充教材内容。"
        st.session_state.messages.append({"role": "assistant", "content": answer})
        finish_generation()
        st.rerun()
        return

    messages = [
        {"role": "system", "content": load_system_prompt()},
        *build_chat_history_messages(prior_messages),
        {
            "role": "user",
            "content": build_user_prompt(
                effective_question,
                contexts,
            ),
        },
    ]

    try:
        answer = client.chat(messages)
    except DeepSeekError as exc:
        answer = f"调用 DeepSeek API 失败：{exc}"
        st.session_state.messages.append({"role": "assistant", "content": answer})
        finish_generation()
        st.rerun()
        return

    parse_text = (
        f"此前完整对话上下文：\n{conversation_context or '暂无。'}\n\n"
        f"用户新问题：\n{question}\n\n"
        f"助手刚刚输出的回答（包含用于演示理解的 C 代码）：\n{answer}"
    )
    try:
        parsed_demo = parse_operation_request(client, parse_text)
        needs_demo_code = isinstance(parsed_demo, (OperationRequest, Clarification))
        show_code = user_wants_code(question)
        code_check = (
            check_c_code_in_answer(answer)
            if show_code or needs_demo_code
            else check_c_code_in_answer(None)
        )
        if needs_demo_code and not code_check.has_code:
            code_check.needs_fix = True
            code_check.summary = (
                "这是演示类问题，但回答末尾没有检测到 ```c 代码块。"
                "请补充完整可运行 C 程序，供右侧演示板理解数据和操作参数。"
            )

        if (show_code or needs_demo_code) and code_check.needs_fix:
            fix_messages = messages + [
                {"role": "assistant", "content": answer},
                {
                    "role": "user",
                    "content": (
                        "你刚才生成的 C 代码编译或运行失败。"
                        "请根据下面错误信息修正，并重新输出完整教学回答和完整可运行 C 代码。"
                        "教学回答要保留初始状态、操作过程、结果和易错点，不要只输出代码。"
                        "如果这是演示类问题，修正后的文字、main 中的数据和操作参数必须完全一致。"
                        "不要提到“重新检查”“修正版”等内部过程说明，直接给学生最终答案。\n\n"
                        f"{code_check.summary}"
                    ),
                },
            ]
            try:
                answer = client.chat(fix_messages)
                code_check = check_c_code_in_answer(answer)
            except DeepSeekError as exc:
                code_check.summary += f"\n\n二次修正调用失败：{exc}"

        final_parse_text = (
            f"此前完整对话上下文：\n{conversation_context or '暂无。'}\n\n"
            f"用户新问题：\n{question}\n\n"
            f"助手刚刚输出的回答（包含用于演示理解的 C 代码）：\n{answer}"
        )
        parsed_demo = parse_operation_request(client, final_parse_text)
        if isinstance(parsed_demo, OperationRequest):
            st.session_state.dsvp_request = parsed_demo
            st.session_state.dsvp_trace = dispatch(parsed_demo)
            st.session_state.dsvp_step = 0
            st.session_state.dsvp_autoplay = False
            st.session_state.dsvp_clarification = None
        elif isinstance(parsed_demo, Clarification):
            st.session_state.dsvp_clarification = parsed_demo
            st.session_state.dsvp_request = None
            st.session_state.dsvp_trace = None
            st.session_state.dsvp_step = 0
            st.session_state.dsvp_autoplay = False
        else:
            st.session_state.dsvp_clarification = None

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
    except Exception as exc:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": f"本轮生成时出现异常，已自动恢复输入状态。错误信息：{exc}",
            }
        )
    finish_generation()
    st.rerun()


if __name__ == "__main__":
    main()
