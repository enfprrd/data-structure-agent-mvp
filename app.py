from __future__ import annotations

import json
import os
import re
from pathlib import Path

import streamlit as st

from code_checker import check_c_code_in_answer
from llm import DeepSeekClient, DeepSeekError, load_dotenv
from operation_visualizer import (
    UNSUPPORTED_HINT,
    SUPPORTED_OPERATIONS,
    build_visualization,
    build_visualization_from_features,
    explain_visualization_source,
    render_visualization,
)
from rag import MarkdownKeywordRetriever


BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
SYSTEM_PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"
CODE_BLOCK_PATTERN = r"```(?:c|C)\s*.*?```"


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def build_user_prompt(
    question: str,
    contexts: list[dict[str, str]],
    learning_summary: str,
) -> str:
    context_text = "\n\n".join(
        f"【资料 {index} | {item['source']}】\n{item['content']}"
        for index, item in enumerate(contexts, start=1)
    )
    if not context_text:
        context_text = "未检索到高相关资料。"

    return f"""下面是从本地 Markdown 知识库检索到的资料：

{context_text}

这是此前对话压缩后的学习上下文，不是用户的新问题：
{learning_summary or "暂无。"}

用户问题：
{question}

请严格依据上面的本地教材知识库片段回答。若资料不足，只说明“知识库资料不足，需要补充教材内容”，不要自由扩展未检索到的知识。
回答要自然、紧凑，像助教直接讲题，不要写成报告。
无论用户是否明确要求代码，都要在回答末尾给出一个简短的 C 语言代码块，供网页演示板和自动检查使用。"""


def build_feature_prompt(
    question: str,
    contexts: list[dict[str, str]],
    learning_summary: str,
) -> str:
    context_titles = "\n".join(f"- {item['source']}" for item in contexts[:3])
    return f"""请把用户的数据结构问题特征化，用于网页交互演示板判断。

用户问题：
{question}

此前学习上下文：
{learning_summary or "暂无。"}

检索片段：
{context_titles}

只返回 JSON，不要解释。字段：
- supported: true 或 false。只有当前 MVP 能演示时才为 true
- operation: 从下面枚举中选一个：
  head_insert, tail_insert, linked_insert, linked_delete, linked_search, linked_length,
  linked_reverse, circular_traverse, seq_insert, seq_delete, none
- structure: linked_list, circular_list, sequential_list, unknown
- values: 用户明确给出的数据序列，例如 [10,12,15,39,49]；没有则 []
- target: 查找或删除目标值；没有则 null
- position: 插入或删除位置；没有则 null
- confidence: 0 到 1
- reason: 20 字以内中文理由

规则：
- 排序、栈、队列、树、图都暂不支持演示，supported=false, operation=none
- 用户给出的数字序列必须放入 values
- 用户追问“它、这个、刚才那个”时，结合此前学习上下文判断

示例：
{{"supported":true,"operation":"linked_reverse","structure":"linked_list","values":[10,12,15,39,49],"target":null,"position":null,"confidence":0.95,"reason":"用户要链表逆序"}}"""


def classify_question_with_deepseek(
    client: DeepSeekClient,
    question: str,
    contexts: list[dict[str, str]],
    learning_summary: str,
) -> dict[str, object]:
    try:
        raw = client.chat(
            [
                {
                    "role": "system",
                    "content": "你只输出严格 JSON，不输出 Markdown，不输出解释。",
                },
                {
                    "role": "user",
                    "content": build_feature_prompt(question, contexts, learning_summary),
                },
            ],
            temperature=0,
            max_tokens=300,
        )
    except DeepSeekError:
        return {}

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}

    return data if isinstance(data, dict) else {}


def feature_supported(features: dict[str, object]) -> bool:
    if not features:
        return True
    if features.get("supported") is False:
        return False
    operation = str(features.get("operation", "")).strip().lower()
    return operation in SUPPORTED_OPERATIONS


def feature_reason(features: dict[str, object]) -> str:
    reason = str(features.get("reason", "")).strip()
    if reason:
        return reason
    return UNSUPPORTED_HINT


def clearly_unsupported_question(question: str) -> str:
    compact = question.lower().replace(" ", "")
    unsupported_terms = {
        "排序": "排序通常属于后续章节，当前 MVP 暂不支持排序演示。",
        "升序": "排序通常属于后续章节，当前 MVP 暂不支持排序演示。",
        "降序": "排序通常属于后续章节，当前 MVP 暂不支持排序演示。",
        "冒泡": "冒泡排序不在当前第 2 章线性表 MVP 演示范围内。",
        "选择排序": "选择排序不在当前第 2 章线性表 MVP 演示范围内。",
        "插入排序": "插入排序不在当前第 2 章线性表 MVP 演示范围内。",
        "sort": "排序不在当前第 2 章线性表 MVP 演示范围内。",
    }
    for term, reason in unsupported_terms.items():
        if term in compact:
            return reason
    return ""


def summarize_learning_context(
    client: DeepSeekClient,
    old_summary: str,
    question: str,
    answer: str,
    features: dict[str, object],
) -> str:
    feature_text = json.dumps(features, ensure_ascii=False)
    prompt = f"""请维护一个极短的本科数据结构学习上下文摘要，用于下一轮理解指代和节约 token。

旧摘要：
{old_summary or "暂无。"}

本轮用户问题：
{question}

本轮问题特征：
{feature_text}

本轮助教回答：
{answer[:1800]}

只输出 120 字以内中文摘要。必须包含：
- 当前主题/操作
- 用户可能正在困惑的点
- 用户偏好或页面交互偏好

不要输出列表符号以外的多余解释。"""
    try:
        summary = client.chat(
            [
                {"role": "system", "content": "你负责压缩学习上下文，只输出短摘要。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=220,
        )
    except DeepSeekError:
        return old_summary

    return summary.strip()[:300]


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

    if "demo_steps" not in st.session_state:
        st.session_state.demo_steps = []

    if "demo_title" not in st.session_state:
        st.session_state.demo_title = "等待提问"

    if "demo_hint" not in st.session_state:
        st.session_state.demo_hint = ""

    if "demo_version" not in st.session_state:
        st.session_state.demo_version = 0

    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False

    if "learning_summary" not in st.session_state:
        st.session_state.learning_summary = ""

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
        if st.session_state.learning_summary:
            st.caption(st.session_state.learning_summary)
        else:
            st.caption("暂无。")
        if st.button("清空"):
            st.session_state.messages = []
            st.session_state.last_contexts = []
            st.session_state.learning_summary = ""
            st.session_state.pending_question = ""
            st.session_state.pending_contexts = []
            st.session_state.is_generating = False
            st.session_state.demo_steps = []
            st.session_state.demo_title = "等待提问"
            st.session_state.demo_hint = ""
            st.session_state.demo_version += 1
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
            st.markdown("### 当前演示")
            st.caption(st.session_state.demo_title)
            if st.session_state.demo_hint:
                st.caption(st.session_state.demo_hint)
            render_visualization(
                st.session_state.demo_steps,
                key=f"main_demo_{st.session_state.demo_version}",
                empty_message=st.session_state.demo_hint,
            )

    with chat_col:
        st.markdown("### 对话")
        with st.container(height=560, border=True):
            render_chat_messages(st.session_state.messages)
            if st.session_state.pending_question:
                with st.chat_message("assistant"):
                    st.markdown("翻教材中...")

        question = st.chat_input("问一个线性表问题")
    if question and not st.session_state.is_generating and not st.session_state.pending_question:
        retriever = MarkdownKeywordRetriever(KNOWLEDGE_DIR)
        retrieval_query = (
            f"{question}\n当前学习上下文：{st.session_state.learning_summary}"
            if st.session_state.learning_summary
            else question
        )
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

    if not contexts:
        answer = "这块教材笔记还没补到，我先不乱讲。"
        st.session_state.demo_steps = []
        st.session_state.demo_title = question
        st.session_state.demo_hint = "这块笔记还没补到。"
        st.session_state.demo_version += 1
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.pending_question = ""
        st.session_state.pending_contexts = []
        st.session_state.is_generating = False
        st.rerun()
        return

    features = classify_question_with_deepseek(
        client,
        question,
        contexts,
        st.session_state.learning_summary,
    )
    unsupported_reason = clearly_unsupported_question(question)
    if unsupported_reason:
        features = {
            "supported": False,
            "operation": "none",
            "reason": unsupported_reason,
            "values": [],
        }

    if features and not feature_supported(features):
        st.session_state.demo_steps = []
        st.session_state.demo_title = question
        st.session_state.demo_hint = feature_reason(features)
        st.session_state.demo_version += 1

    preliminary_steps = build_visualization_from_features(
        features,
        question,
        st.session_state.learning_summary,
    )
    if preliminary_steps:
        st.session_state.demo_steps = preliminary_steps
        st.session_state.demo_title = question
        reason = str(features.get("reason", "")).strip()
        operation = str(features.get("operation", "")).strip()
        st.session_state.demo_hint = reason or operation or "已识别操作"
        st.session_state.demo_version += 1

    messages = [
        {"role": "system", "content": load_system_prompt()},
        {
            "role": "user",
            "content": build_user_prompt(
                question,
                contexts,
                st.session_state.learning_summary,
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

    visual_steps = (
        []
        if features and not feature_supported(features)
        else build_visualization_from_features(
            features,
            question,
            f"{st.session_state.learning_summary}\n{answer}",
        )
    )
    if visual_steps:
        st.session_state.demo_steps = visual_steps
        st.session_state.demo_title = question
        st.session_state.demo_hint = explain_visualization_source(visual_steps)
        st.session_state.demo_version += 1

    visible_answer, code_blocks = make_teaching_view(answer, user_wants_code(question))
    st.session_state.learning_summary = summarize_learning_context(
        client,
        st.session_state.learning_summary,
        question,
        visible_answer,
        features,
    )
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
