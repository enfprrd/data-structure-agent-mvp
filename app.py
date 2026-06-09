from __future__ import annotations

import json
import hashlib
import html
import os
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

import auth_store
from code_checker import check_c_code_in_answer
from llm import DeepSeekClient, DeepSeekError, load_dotenv
from ppt_learning import (
    answer_with_context_pack,
    build_context_pack,
    parse_pptx_to_slide_cards,
)
from rag import MarkdownKeywordRetriever
from visualizer.dispatcher import dispatch
from visualizer.intent_parser import parse_operation_request
from visualizer.protocol import Clarification, OperationRequest
from visualizer.renderers.html_renderer import render_step_html, render_styles


BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
LESSONS_DIR = BASE_DIR / "lessons"
SYSTEM_PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"
CODE_BLOCK_PATTERN = r"```(?:c|C)\s*.*?```"
DEMO_WORD_PATTERN = re.compile(r"演示|展示|继续|播放|可视化|跑一个|看一个|讲一个|试一个")
COURSE_TOPIC_PATTERN = re.compile(
    r"线性表|顺序表|链表|栈|队列|串|KMP|数组|广义表|矩阵|树|二叉树|图|DFS|BFS|查找|排序|归并|快速|冒泡|插入排序|选择排序|堆排序|希尔|基数|哈夫曼|Dijkstra|Floyd|Prim|Kruskal|散列|哈希"
)
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


def bootstrap_device_token() -> str:
    token = str(st.query_params.get("device_id", "")).strip()
    if token:
        components.html(
            f"""
            <script>
            document.cookie = "ds_agent_device_id={token}; path=/; max-age=31536000; SameSite=Lax";
            </script>
            """,
            height=0,
        )
        return token

    fallback = st.session_state.get("device_token") or secrets.token_urlsafe(24)
    st.session_state.device_token = fallback
    components.html(
        f"""
        <script>
        const name = "ds_agent_device_id=";
        const hit = document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith(name));
        let token = hit ? hit.substring(name.length) : "{fallback}";
        if (!hit) {{
            document.cookie = "ds_agent_device_id=" + token + "; path=/; max-age=31536000; SameSite=Lax";
        }}
        const url = new URL(window.parent.location.href);
        if (!url.searchParams.get("device_id")) {{
            url.searchParams.set("device_id", token);
            window.parent.history.replaceState(null, "", url.toString());
            window.parent.location.reload();
        }}
        </script>
        """,
        height=0,
    )
    return fallback


def append_chat_message(message: dict[str, object]) -> None:
    message.setdefault("created_at", datetime.now().strftime("%H:%M"))
    st.session_state.messages.append(message)
    conversation_id = st.session_state.get("conversation_id")
    if conversation_id:
        auth_store.append_message(int(conversation_id), message)


def load_persisted_messages() -> None:
    conversation_id = st.session_state.get("conversation_id")
    loaded_key = (
        int(conversation_id or 0),
        st.session_state.get("user_id"),
        st.session_state.get("device_token"),
    )
    if st.session_state.get("loaded_history_key") == loaded_key:
        return
    st.session_state.messages = auth_store.load_messages(int(conversation_id)) if conversation_id else []
    st.session_state.loaded_history_key = loaded_key


def finish_generation() -> None:
    st.session_state.pending_question = ""
    st.session_state.pending_effective_question = ""
    st.session_state.pending_contexts = []
    st.session_state.pending_rag_keywords = []
    st.session_state.pending_rag_plan = {}
    st.session_state.is_generating = False
    st.session_state.generation_started_at = 0.0


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

请严格依据上面的本地教材片段回答。若资料不足，只说明“知识库资料不足，需要补充教材内容”，不要自由扩展未检索到的知识。
回答要像课堂助教讲题：先解释核心概念，再讲操作过程，最后点出易错点；不要只给一两句结论。
如果用户问的是演示、插入、删除、查找、建表、代码运行过程，回答至少包含：
- 本次例子的初始状态和目标
- 操作过程的分步解释
- 每个关键指针或数组移动为什么这样做
- 最终结果
- 1 到 3 个易错点
如果用户是在要求演示、展示、逐步操作、继续演示，或问题具有演示意图，回答末尾必须给出一个完整可运行的 C 程序：
- 必须包含 #include、结构体定义、核心操作函数、打印函数和 main。
- main 中的数据、操作和值必须和文字讲解完全一致。
- 文字讲解中必须明确写出初始数据、数据结构、操作类型，以及 position/value/target 等操作参数。
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


def build_effective_question(
    question: str,
    messages: list[dict[str, object]],
    client: DeepSeekClient | None = None,
) -> str:
    current = question.strip()
    if not _is_ambiguous_follow_up(current):
        return current

    if not messages:
        return current

    rewritten = _rewrite_follow_up_with_deepseek(current, messages, client)
    if rewritten:
        return rewritten

    return current


def get_recent_rag_keywords(messages: list[dict[str, object]], limit: int = 12) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()
    for message in reversed(messages):
        for raw_keyword in message.get("rag_keywords") or []:
            keyword = str(raw_keyword).strip()
            keyword_key = keyword.lower()
            if not keyword or keyword_key in seen:
                continue
            keywords.append(keyword)
            seen.add(keyword_key)
            if len(keywords) >= limit:
                return keywords
    return keywords


def retrieve_with_rag_memory(
    retriever: MarkdownKeywordRetriever,
    question: str,
    rag_keywords: list[str],
    rag_plan: dict[str, Any] | None = None,
    top_k: int = 3,
) -> list[dict[str, str]]:
    boost_weights = build_weighted_rag_terms(rag_plan, rag_keywords)
    current_terms = _clean_keyword_list((rag_plan or {}).get("query_keywords"))
    all_terms = list(boost_weights)

    user_contexts = retriever.retrieve(
        question,
        top_k=top_k,
        boost_terms=current_terms,
        boost_weights=boost_weights,
    )
    if not all_terms:
        return user_contexts

    keyword_query = " ".join(all_terms)
    combined_query = f"{question}\nRAG keywords: {keyword_query}"
    keyword_contexts = retriever.retrieve(
        keyword_query,
        top_k=top_k,
        boost_terms=all_terms,
        boost_weights=boost_weights,
    )
    combined_contexts = retriever.retrieve(
        combined_query,
        top_k=top_k,
        boost_terms=all_terms,
        boost_weights=boost_weights,
    )
    return _merge_contexts(user_contexts, combined_contexts, keyword_contexts, top_k=top_k)


def build_query_rag_plan(
    client: DeepSeekClient | None,
    question: str,
    prior_messages: list[dict[str, object]],
    previous_keywords: list[str],
) -> dict[str, Any]:
    if client is None:
        return {}
    history = build_conversation_context(prior_messages[-4:])
    prompt = f"""
你是数据结构课程问答系统的检索规划器。请只输出 JSON，不要解释。

目标：根据用户当前问题给出本轮 RAG 检索关键词分组，并判断哪些历史关键词仍可低权重辅助。

输出格式：
{{
  "query_keywords": ["当前问题最重要的关键词，3-8 个"],
  "groups": [
    {{"name": "主题名", "keywords": ["该组关键词"], "weight": 5}}
  ],
  "history_keywords": ["仍然相关的历史关键词，可为空"]
}}

规则：
- 当前问题关键词必须优先于历史关键词。
- 如果当前问题已经明确是新主题，例如二叉树后序遍历，不要沿用上一轮顺序表、链表等无关关键词。
- weight 取 1 到 6；当前核心概念用 5-6，相关操作用 3-4，历史上下文最多 1-2。
- 关键词要适合检索教材 markdown，例如：二叉树、后序遍历、遍历、树；图、DFS、顶点、visited。

最近对话：
{history or "暂无"}

历史 RAG 关键词：
{json.dumps(previous_keywords, ensure_ascii=False)}

用户当前问题：
{question}
"""
    try:
        raw = client.chat(
            [
                {"role": "system", "content": "你只负责输出 RAG 检索 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=500,
        )
    except DeepSeekError:
        return {}
    return normalize_rag_plan(raw, previous_keywords)


def normalize_rag_plan(raw: str, previous_keywords: list[str]) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
    try:
        plan = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    if not isinstance(plan, dict):
        return {}

    query_keywords = _clean_keyword_list(plan.get("query_keywords"))
    groups: list[dict[str, Any]] = []
    for group in plan.get("groups") or []:
        if not isinstance(group, dict):
            continue
        keywords = _clean_keyword_list(group.get("keywords"))
        if not keywords:
            continue
        try:
            weight = int(group.get("weight", 3))
        except (TypeError, ValueError):
            weight = 3
        groups.append(
            {
                "name": str(group.get("name") or "group")[:40],
                "keywords": keywords,
                "weight": min(6, max(1, weight)),
            }
        )

    allowed_history = set(_clean_keyword_list(plan.get("history_keywords")))
    history_keywords = [keyword for keyword in previous_keywords if keyword in allowed_history]
    return {
        "query_keywords": query_keywords,
        "groups": groups,
        "history_keywords": history_keywords,
    }


def build_weighted_rag_terms(rag_plan: dict[str, Any] | None, previous_keywords: list[str]) -> dict[str, int]:
    weights: dict[str, int] = {}
    plan = rag_plan or {}
    for keyword in _clean_keyword_list(plan.get("query_keywords")):
        weights[keyword] = max(weights.get(keyword, 0), 6)
    for group in plan.get("groups") or []:
        if not isinstance(group, dict):
            continue
        try:
            group_weight = int(group.get("weight", 3))
        except (TypeError, ValueError):
            group_weight = 3
        group_weight = min(6, max(1, group_weight))
        for keyword in _clean_keyword_list(group.get("keywords")):
            weights[keyword] = max(weights.get(keyword, 0), group_weight)
    for keyword in _clean_keyword_list(plan.get("history_keywords")):
        if keyword in previous_keywords:
            weights[keyword] = max(weights.get(keyword, 0), 2)
    return weights


def _clean_keyword_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        keyword = str(item).strip()
        key = keyword.lower()
        if not keyword or key in seen:
            continue
        cleaned.append(keyword)
        seen.add(key)
    return cleaned


def _merge_contexts(*groups: list[dict[str, str]], top_k: int) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for group_index, contexts in enumerate(groups):
        for context in contexts:
            source = context["source"]
            score = int(context.get("score", "0"))
            bonus = max(0, 2 - group_index) * 10
            weighted_score = score + bonus
            existing = merged.get(source)
            if existing is None or weighted_score > int(existing.get("score", "0")):
                merged[source] = {**context, "score": str(weighted_score)}
    return sorted(merged.values(), key=lambda item: int(item["score"]), reverse=True)[:top_k]


def build_rag_keywords(
    client: DeepSeekClient,
    prior_messages: list[dict[str, object]],
    question: str,
    effective_question: str,
    answer: str,
    previous_keywords: list[str],
) -> list[str]:
    history = build_conversation_context(prior_messages[-6:])
    prompt = (
        "你负责为数据结构课程问答维护 RAG 检索关键词记忆。\n"
        "请根据最近对话、用户新问题、实际检索问题、助教回答，总结当前最能代表本轮对话主题的关键词。\n"
        "要求：\n"
        "- 只输出 JSON 字符串数组，不要解释。\n"
        "- 输出 4 到 10 个关键词。\n"
        "- 关键词要适合检索教材知识库，例如：图、DFS、深度优先遍历、邻接矩阵、顶点、visited 数组。\n"
        "- 保留最近主主题，不要被短追问里的单个词带偏。\n"
        "- 如果最近在讨论图，用户说结点或节点时，关键词应优先使用顶点。\n"
        "- 可以继承上一轮关键词，但要去掉无关词。\n\n"
        f"上一轮 RAG 关键词：{json.dumps(previous_keywords, ensure_ascii=False)}\n\n"
        f"最近对话：\n{history or '暂无'}\n\n"
        f"用户新问题：{question}\n\n"
        f"实际检索问题：{effective_question}\n\n"
        f"助教回答：\n{answer[:3000]}"
    )
    try:
        raw = client.chat(
            [
                {"role": "system", "content": "你是数据结构问答系统的 RAG 关键词提取器。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=180,
        )
    except DeepSeekError:
        return previous_keywords
    keywords = _parse_rag_keywords(raw)
    return keywords or previous_keywords


def _parse_rag_keywords(raw: str) -> list[str]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
    try:
        values: Any = json.loads(cleaned)
    except json.JSONDecodeError:
        values = re.split(r"[,锛屻€乗n]", cleaned)
    if not isinstance(values, list):
        return []

    keywords: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = str(value).strip().strip('"').strip("'")
        if not keyword or len(keyword) > 24:
            continue
        key = keyword.lower()
        if key in seen:
            continue
        keywords.append(keyword)
        seen.add(key)
        if len(keywords) >= 10:
            break
    return keywords


def _is_ambiguous_follow_up(question: str) -> bool:
    compact = re.sub(r"\s+", "", question)
    if not compact:
        return False
    if len(compact) <= 24 and DEMO_WORD_PATTERN.search(compact):
        return True
    if compact in {"这个呢", "那这个呢", "继续", "继续讲", "继续说", "详细点", "展开讲"}:
        return True
    if len(compact) <= 24 and re.search(r"这个|那个|它|这类|这种|这样|更多|换成|如果是|那要是|呢|吗", compact):
        return True
    return False


def _rewrite_follow_up_with_deepseek(
    question: str,
    messages: list[dict[str, object]],
    client: DeepSeekClient | None,
) -> str:
    if client is None:
        return ""

    history = build_conversation_context(messages[-6:])
    prompt = (
        "你只负责把用户的省略追问改写成一个独立、明确的数据结构课程问题，用于知识库检索。\n"
        "要求：\n"
        "- 只输出改写后的问题，不要解释。\n"
        "- 如果用户说‘演示一个/继续演示/展示一下’，必须继承最近一轮具体主题。\n"
        "- 如果用户使用‘这个/它/更多的结点/如果是更大...’等省略说法，必须结合最近对话判断所指对象。\n"
        "- 如果最近在讨论图，用户说‘结点/节点’通常应理解为图的顶点。\n"
        "- 保留算法或数据结构名，例如归并排序、二叉树、Dijkstra。\n"
        "- 不要擅自改成链表、顺序表等无关主题。\n"
        "- 如果无法判断，就原样输出用户新问题。\n\n"
        f"最近对话：\n{history or '暂无'}\n\n"
        f"用户新问题：{question}"
    )
    try:
        rewritten = client.chat(
            [
                {"role": "system", "content": "你是数据结构问答的检索问题改写器。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=120,
        ).strip()
    except DeepSeekError:
        return ""

    rewritten = re.sub(r"^```(?:text)?|```$", "", rewritten).strip()
    if not rewritten or len(rewritten) > 120:
        return ""
    return rewritten

def render_contexts(contexts: list[dict[str, str]]) -> None:
    with st.expander("检索片段", expanded=False):
        if not contexts:
            st.info("暂无命中。")
            return

        for index, item in enumerate(contexts, start=1):
            st.markdown(f"**{index}. {item['source']}**")
            st.caption(f"score {item['score']}")
            st.markdown(item["content"])
            st.divider()

def render_knowledge_browser() -> None:
    files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not files:
        st.info("知识库暂时为空。")
        return

    titles = {path.name: _knowledge_title(path) for path in files}
    control_col, search_col = st.columns([0.9, 1.1], gap="medium")
    with control_col:
        selected_name = st.selectbox(
            "章节",
            [path.name for path in files],
            format_func=lambda name: titles.get(name, name),
            key="knowledge_reader_file",
        )
    with search_col:
        query = st.text_input("查找", placeholder="DFS、顺序表、归并排序", key="knowledge_reader_query")

    selected_path = KNOWLEDGE_DIR / selected_name
    text = selected_path.read_text(encoding="utf-8")

    with st.container(key="knowledge_reader_body"):
        if query.strip():
            matches = _search_knowledge(query.strip(), files)
            st.caption(f"{len(matches)} 个结果")
            for match in matches[:8]:
                with st.expander(f"{match['title']} | {match['source']}", expanded=False):
                    st.markdown(match["content"])
            return

        st.caption(f"knowledge/{selected_name}")
        sections = _split_knowledge_sections(text)
        for index, section in enumerate(sections):
            title = _section_title(section) or ("章节简介" if index == 0 else f"小节 {index + 1}")
            with st.expander(title, expanded=index == 0):
                st.markdown(section)


def _knowledge_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else path.stem


def _split_knowledge_sections(text: str) -> list[str]:
    sections = [section.strip() for section in re.split(r"\n(?=##\s+)", text) if section.strip()]
    return sections or [text.strip()]


def _section_title(section: str) -> str:
    match = re.search(r"^#{1,6}\s+(.+)$", section, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _search_knowledge(query: str, files: list[Path]) -> list[dict[str, str]]:
    terms = [term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+", query)]
    matches: list[dict[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        chapter_title = _knowledge_title(path)
        for section in _split_knowledge_sections(text):
            compact = section.lower()
            if all(term in compact for term in terms):
                title = _section_title(section) or chapter_title
                matches.append({"source": path.name, "title": title, "content": section})
    return matches

def load_mainline_lessons() -> list[dict[str, Any]]:
    lesson_path = LESSONS_DIR / "mainline.json"
    if not lesson_path.exists():
        return []
    return json.loads(lesson_path.read_text(encoding="utf-8"))


def render_mainline_learning() -> None:
    lessons = load_mainline_lessons()
    if not lessons:
        st.info("主线课程还没有配置。")
        return

    progress = st.session_state.setdefault("lesson_progress", {})
    current_id = st.session_state.setdefault("current_lesson_id", lessons[0]["id"])
    lesson_by_id = {lesson["id"]: lesson for lesson in lessons}
    if current_id not in lesson_by_id:
        current_id = lessons[0]["id"]
        st.session_state.current_lesson_id = current_id

    nav_col, lesson_col = st.columns([0.82, 1.45], gap="large")
    with nav_col:
        st.markdown("### 主线目录")
        total = len(lessons)
        done = sum(1 for lesson in lessons if progress.get(lesson["id"], {}).get("completed"))
        st.caption(f"进度 {done} / {total}")
        for module, module_lessons in _group_lessons_by_module(lessons):
            st.markdown(f"**{module}**")
            for lesson in module_lessons:
                state = progress.get(lesson["id"], {})
                status = "已完成" if state.get("completed") else "学习中" if lesson["id"] == current_id else "未学"
                label = f"{lesson['title']} · {status}"
                if st.button(label, key=f"lesson_nav_{lesson['id']}", use_container_width=True):
                    st.session_state.current_lesson_id = lesson["id"]
                    st.rerun()

    with lesson_col:
        lesson = lesson_by_id[current_id]
        _render_lesson_detail(lesson, progress)


def render_ppt_learning_mode() -> None:
    st.markdown("### PPT学习模式")
    st.caption("第一阶段只解析 PPTX 中的文字、表格和备注；不会把截图或图片传给模型。")

    uploaded = st.file_uploader("上传 PPTX", type=["pptx"], key="pptx_uploader")
    local_path = st.text_input(
        "或输入本地 PPTX 路径",
        placeholder=r"C:\Users\ROG\Desktop\lecture.pptx",
        key="pptx_local_path",
    )

    pptx_bytes: bytes | None = None
    deck_name = ""
    if uploaded is not None:
        pptx_bytes = uploaded.getvalue()
        deck_name = uploaded.name
    elif local_path.strip():
        path = Path(local_path.strip().strip('"'))
        if path.exists() and path.suffix.lower() == ".pptx":
            pptx_bytes = path.read_bytes()
            deck_name = path.name
        else:
            st.warning("没有找到这个 PPTX 文件，或文件后缀不是 .pptx。")

    if not pptx_bytes:
        st.info("先上传一份 PPTX，或填入本机 PPTX 路径。")
        return

    deck_hash = hashlib.sha1(pptx_bytes).hexdigest()[:12]
    if st.session_state.get("ppt_deck_hash") != deck_hash:
        st.session_state.ppt_deck_hash = deck_hash
        st.session_state.ppt_deck_name = deck_name
        st.session_state.ppt_slide_index = 0
        st.session_state.ppt_messages = []
        try:
            meta_client = DeepSeekClient(timeout=30)
        except DeepSeekError:
            meta_client = None
            st.warning("DeepSeek 暂不可用，已先用本地摘要和关键词生成 SlideCard。")
        with st.spinner("正在本地解析 PPT，并为每页生成 SlideCard..."):
            try:
                st.session_state.ppt_slide_cards = parse_pptx_to_slide_cards(
                    deck_id=deck_hash,
                    pptx_bytes=pptx_bytes,
                    client=meta_client,
                )
            except Exception as exc:
                st.error(f"PPT 解析失败：{exc}")
                st.session_state.ppt_slide_cards = []
                return

    slide_cards = list(st.session_state.get("ppt_slide_cards") or [])
    if not slide_cards:
        st.warning("这份 PPT 没有解析出可用页。")
        return

    current_index = min(max(int(st.session_state.get("ppt_slide_index", 0)), 0), len(slide_cards) - 1)
    st.session_state.ppt_slide_index = current_index
    current_slide = slide_cards[current_index]

    left_col, right_col = st.columns([0.95, 1.05], gap="large")
    with left_col:
        st.markdown(f"#### 第 {current_slide.slide_id} / {len(slide_cards)} 页：{current_slide.title or '未命名页'}")
        prev_col, next_col = st.columns(2)
        with prev_col:
            if st.button("上一页", disabled=current_index == 0, use_container_width=True):
                st.session_state.ppt_slide_index = current_index - 1
                st.rerun()
        with next_col:
            if st.button("下一页", disabled=current_index == len(slide_cards) - 1, use_container_width=True):
                st.session_state.ppt_slide_index = current_index + 1
                st.rerun()

        if current_slide.concept_type == "text_missing":
            st.warning("该页可提取文本不足。第一阶段不会猜测图片内容。")
        st.markdown("**提取文本**")
        st.text_area(
            "当前页提取文本",
            current_slide.raw_text or "该页没有可提取正文。",
            height=230,
            label_visibility="collapsed",
        )
        if current_slide.notes:
            with st.expander("备注 notes", expanded=False):
                st.markdown(current_slide.notes)
        if current_slide.tables:
            with st.expander("表格内容", expanded=False):
                for table_index, table in enumerate(current_slide.tables, start=1):
                    st.markdown(f"表格 {table_index}")
                    st.table(table)
        with st.expander("SlideCard", expanded=False):
            st.json(current_slide.to_dict())

    with right_col:
        st.markdown("#### AI讲解与答疑")
        explain_clicked = st.button("讲解当前页", use_container_width=True)
        with st.container(border=False, key="ppt_chat_scroll"):
            for message in st.session_state.setdefault("ppt_messages", []):
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        with st.form("ppt_question_form", clear_on_submit=True):
            ppt_question = st.text_area(
                "对当前页提问",
                placeholder="例如：这一页的核心概念是什么？和上一页有什么关系？",
                height=72,
            )
            asked = st.form_submit_button("发送")

        question = ""
        if explain_clicked:
            question = "请讲解当前页：先说明本页主题，再讲重点、前后页关系和易错点。"
        elif asked and ppt_question.strip():
            question = ppt_question.strip()

        if question:
            _answer_ppt_question(slide_cards, current_slide.slide_id, question)
            st.rerun()


def _answer_ppt_question(slide_cards: list[Any], current_slide_id: int, question: str) -> None:
    st.session_state.ppt_messages.append({"role": "user", "content": question})
    try:
        client = DeepSeekClient()
    except DeepSeekError as exc:
        st.session_state.ppt_messages.append({"role": "assistant", "content": f"DeepSeek API 调用失败：{exc}"})
        return

    retriever = MarkdownKeywordRetriever(KNOWLEDGE_DIR)
    context_pack = build_context_pack(
        slide_cards=slide_cards,
        current_slide_id=current_slide_id,
        question=question,
        conversation_messages=st.session_state.ppt_messages[:-1],
        textbook_retriever=retriever,
        top_k=3,
    )
    try:
        answer = answer_with_context_pack(client, context_pack, question)
    except DeepSeekError as exc:
        answer = f"DeepSeek API 调用失败：{exc}"

    source_pages = [context_pack.current_slide.slide_id]
    source_pages.extend(card.slide_id for card in context_pack.retrieved_slides)
    source_label = "、".join(str(page) for page in sorted(set(source_pages)))
    if "来源" not in answer:
        answer = f"{answer}\n\n来源页码：第 {source_label} 页"
    st.session_state.ppt_messages.append(
        {
            "role": "assistant",
            "content": answer,
            "source_pages": source_pages,
        }
    )


def _group_lessons_by_module(lessons: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: list[tuple[str, list[dict[str, Any]]]] = []
    index: dict[str, list[dict[str, Any]]] = {}
    for lesson in lessons:
        module = str(lesson.get("module") or "未分组")
        if module not in index:
            index[module] = []
            grouped.append((module, index[module]))
        index[module].append(lesson)
    return grouped


def _render_lesson_detail(lesson: dict[str, Any], progress: dict[str, Any]) -> None:
    lesson_id = str(lesson["id"])
    state = progress.setdefault(lesson_id, {})
    st.markdown(
        f"""
        <div class="lesson-hero">
            <div class="lesson-kicker">{html.escape(str(lesson.get("module", "")))} · {html.escape(str(lesson.get("duration", "")))}</div>
            <div class="lesson-title">{html.escape(str(lesson.get("title", "")))}</div>
            <div class="lesson-summary">{html.escape(str(lesson.get("summary", "")))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    objectives = lesson.get("objectives") or []
    if objectives:
        st.markdown("#### 学习目标")
        for item in objectives:
            st.markdown(f"- {item}")

    st.markdown("#### 本课讲解")
    for section in lesson.get("sections") or []:
        with st.expander(str(section.get("heading", "小节")), expanded=True):
            st.markdown(str(section.get("body", "")))

    demo = lesson.get("demo")
    if demo:
        st.markdown("#### 动画演示")
        st.caption("点击后会把右侧演示板切换到本课对应步骤。")
        if st.button("加载本课演示", key=f"lesson_demo_{lesson_id}"):
            _load_lesson_demo(demo)
            st.toast("已加载到右侧演示板")
            st.rerun()

    _render_lesson_quiz(lesson, state)

    complete_col, reset_col = st.columns([0.18, 0.18])
    with complete_col:
        if st.button("标记完成", key=f"lesson_complete_{lesson_id}"):
            state["completed"] = True
            progress[lesson_id] = state
            st.session_state.lesson_progress = progress
            st.rerun()
    with reset_col:
        if st.button("重学本课", key=f"lesson_reset_{lesson_id}"):
            progress[lesson_id] = {}
            st.session_state.lesson_progress = progress
            st.rerun()


def _load_lesson_demo(demo: dict[str, Any]) -> None:
    request = OperationRequest.model_validate(demo)
    st.session_state.dsvp_request = request
    st.session_state.dsvp_trace = dispatch(request)
    st.session_state.dsvp_step = 0
    st.session_state.dsvp_autoplay = False
    st.session_state.dsvp_clarification = None


def _render_lesson_quiz(lesson: dict[str, Any], state: dict[str, Any]) -> None:
    quiz = lesson.get("quiz") or []
    if not quiz:
        return
    lesson_id = str(lesson["id"])
    st.markdown("#### 小测")
    answers = state.setdefault("answers", {})
    for index, item in enumerate(quiz):
        key = f"lesson_quiz_{lesson_id}_{index}"
        stored = answers.get(str(index))
        choices = list(item.get("choices") or [])
        if not choices:
            continue
        default_index = choices.index(stored) if stored in choices else None
        selected = st.radio(
            str(item.get("question", "")),
            choices,
            index=default_index,
            key=key,
            horizontal=False,
        )
        if selected is not None:
            answers[str(index)] = selected
            correct = selected == item.get("answer")
            if correct:
                st.success("回答正确。")
            else:
                st.warning(f"再想想：正确答案是 {item.get('answer')}")
            st.caption(str(item.get("explanation", "")))

    state["answers"] = answers
    state["quiz_correct"] = sum(
        1 for index, item in enumerate(quiz) if answers.get(str(index)) == item.get("answer")
    )
    st.caption(f"小测得分：{state['quiz_correct']} / {len(quiz)}")

def render_auth_panel() -> None:
    st.markdown("**账号**")
    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username")
    if user_id:
        st.success(f"已登录：{username}")
        if st.button("退出登录"):
            st.session_state.user_id = None
            st.session_state.username = ""
            device_id = auth_store.ensure_device(str(st.session_state.device_token), None)
            st.session_state.device_id = device_id
            st.session_state.conversation_id = auth_store.get_or_create_conversation(None, device_id)
            st.session_state.loaded_history_key = None
            load_persisted_messages()
            st.rerun()
        return

    login_tab, register_tab = st.tabs(["登录", "注册"])
    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            username_input = st.text_input("用户名", key="login_username")
            password_input = st.text_input("密码", type="password", key="login_password")
            submitted = st.form_submit_button("登录")
            if submitted:
                ok, result = auth_store.verify_user(username_input, password_input)
                if ok:
                    st.session_state.user_id = int(result)
                    st.session_state.username = username_input.strip()
                    device_id = auth_store.ensure_device(str(st.session_state.device_token), int(result))
                    st.session_state.device_id = device_id
                    st.session_state.conversation_id = auth_store.get_or_create_conversation(int(result), device_id)
                    st.session_state.loaded_history_key = None
                    load_persisted_messages()
                    st.rerun()
                else:
                    st.error(result)

    with register_tab:
        with st.form("register_form", clear_on_submit=False):
            username_input = st.text_input("用户名", key="register_username")
            password_input = st.text_input("密码", type="password", key="register_password")
            submitted = st.form_submit_button("注册并登录")
            if submitted:
                ok, result, user = auth_store.create_user(username_input, password_input)
                if ok and user:
                    user_id = int(user["id"])
                    st.session_state.user_id = user_id
                    st.session_state.username = username_input.strip()
                    device_id = auth_store.ensure_device(str(st.session_state.device_token), user_id)
                    st.session_state.device_id = device_id
                    st.session_state.conversation_id = auth_store.get_or_create_conversation(user_id, device_id)
                    st.session_state.loaded_history_key = None
                    load_persisted_messages()
                    st.rerun()
                else:
                    st.error(result)

def render_chat_messages(messages: list[dict[str, object]]) -> None:
    if not messages:
        st.markdown(
            """
            <div class="chat-welcome">
                <div class="chat-welcome-title">你好，我是你的数据结构助教。</div>
                <div class="chat-welcome-copy">试试问我：如何向顺序表中插入元素？</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for message_index, message in enumerate(messages):
        role = str(message.get("role", "user"))
        bubble_role = "user" if role == "user" else "assistant"
        with st.container(key=f"msg_{bubble_role}_{message_index}"):
            st.markdown(str(message["content"]))
            timestamp = str(message.get("created_at") or "")
            if timestamp:
                st.caption(timestamp)
            code_blocks = list(message.get("code_blocks") or [])
            if code_blocks:
                with st.expander("C 代码", expanded=False):
                    for code_block in code_blocks:
                        st.markdown(str(code_block))
            code_check = message.get("code_check")
            if code_check:
                with st.expander("代码检查", expanded=False):
                    st.markdown(str(code_check))
            if role == "assistant":
                render_step_links(message, message_index)
                render_message_quiz(message, message_index)


def render_step_links(message: dict[str, object], message_index: int) -> None:
    links = list(message.get("step_links") or [])
    if not links:
        return
    has_demo_request = isinstance(message.get("demo_request"), dict) and bool(message.get("demo_request"))
    if not has_demo_request and st.session_state.get("dsvp_trace") is None:
        return
    with st.expander("同步演示步骤", expanded=False):
        for link in links:
            step_index = int(link.get("step_index", 0))
            title = str(link.get("title", f"步骤 {step_index + 1}"))
            description = str(link.get("description", ""))
            if st.button(title, key=f"step_link_{message_index}_{step_index}", use_container_width=True):
                load_demo_from_message(message)
                st.session_state.dsvp_step = step_index
                st.session_state.dsvp_autoplay = False
                st.rerun()
            if description:
                st.caption(description)


def load_demo_from_message(message: dict[str, object]) -> None:
    demo_request = message.get("demo_request")
    if not isinstance(demo_request, dict) or not demo_request:
        return
    try:
        request = OperationRequest.model_validate(demo_request)
        st.session_state.dsvp_request = request
        st.session_state.dsvp_trace = dispatch(request)
        st.session_state.dsvp_clarification = None
    except Exception:
        return


def render_message_quiz(message: dict[str, object], message_index: int) -> None:
    quiz = list(message.get("quiz") or [])
    if not quiz:
        return
    st.markdown("**随堂小测**")
    for quiz_index, item in enumerate(quiz):
        key_prefix = f"chat_quiz_{message_index}_{quiz_index}"
        result_key = f"{key_prefix}_result"
        selected = st.radio(
            str(item.get("question", "")),
            list(item.get("choices") or []),
            index=None,
            key=f"{key_prefix}_answer",
            horizontal=False,
        )
        submitted = st.button("提交小测", key=f"{key_prefix}_submit")
        saved_result = st.session_state.get(result_key)
        if submitted and selected:
            correct = selected == item.get("answer")
            st.session_state[result_key] = {"selected": selected, "correct": correct}
            event_key = f"{result_key}_saved"
            if not st.session_state.get(event_key):
                auth_store.add_learning_event(
                    user_id=st.session_state.get("user_id"),
                    device_id=st.session_state.get("device_id"),
                    conversation_id=st.session_state.get("conversation_id"),
                    tag=str(item.get("tag") or "概念理解"),
                    source_type="chat_quiz",
                    prompt=str(item.get("question", "")),
                    correct=correct,
                    note=f"选择：{selected}",
                )
                st.session_state[event_key] = True
            saved_result = st.session_state[result_key]

        if saved_result:
            if saved_result.get("correct"):
                st.success("答对了。")
            else:
                st.warning(f"这里再回看一下：正确答案是 {item.get('answer')}")
                review_step = item.get("review_step")
                if review_step is not None and st.button("跳到相关演示步骤", key=f"{key_prefix}_review"):
                    st.session_state.dsvp_step = int(review_step)
                    st.session_state.dsvp_autoplay = False
                    st.rerun()
            st.caption(str(item.get("explanation", "")))

def user_wants_code(question: str) -> bool:
    q = question.lower()
    code_words = ["代码", "程序", "实现", "完整", "可运行", "c语言", "c 语言"]
    return any(word in q for word in code_words)


def make_teaching_view(answer: str, keep_code: bool = False) -> tuple[str, list[str]]:
    code_blocks = re.findall(CODE_BLOCK_PATTERN, answer, flags=re.DOTALL)
    if keep_code:
        return answer, code_blocks
    visible = re.sub(CODE_BLOCK_PATTERN, "", answer, flags=re.DOTALL).strip()
    return visible or answer, code_blocks


WEAKNESS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("指针移动", ("指针", "pre->next", "next", "链表", "结点", "节点")),
    ("图遍历顺序", ("图", "DFS", "BFS", "深度优先", "广度优先", "visited", "顶点")),
    ("排序稳定性", ("稳定", "快排", "快速排序", "归并", "冒泡", "插入排序", "选择排序", "排序")),
    ("边界条件", ("越界", "空表", "空栈", "空队", "下标", "position", "边界", "容量")),
    ("数组元素移动", ("顺序表", "数组", "后移", "前移", "插入", "删除")),
    ("栈队列规则", ("栈", "队列", "入栈", "出栈", "入队", "出队", "先进先出", "后进先出")),
    ("树的遍历", ("树", "二叉树", "前序", "中序", "后序", "层序")),
]


def infer_weakness_tags(*parts: object) -> list[str]:
    text = " ".join(str(part) for part in parts if part).lower()
    tags: list[str] = []
    for tag, keywords in WEAKNESS_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            tags.append(tag)
    return tags or ["概念理解"]


def build_interactive_quiz(
    question: str,
    answer: str,
    keywords: list[str],
    trace: Any | None,
) -> list[dict[str, Any]]:
    tags = infer_weakness_tags(question, answer, " ".join(keywords))
    primary = tags[0]
    templates: dict[str, dict[str, Any]] = {
        "指针移动": {
            "question": "链表插入时，为什么通常先写 new->next = pre->next？",
            "choices": ["先保住原后继链", "让新结点释放内存", "让 pre 变成空指针", "为了让数组后移"],
            "answer": "先保住原后继链",
            "explanation": "先连接新结点到原后继，后面再改 pre->next，链才不会断。",
        },
        "图遍历顺序": {
            "question": "DFS/BFS 中 visited 数组最主要用来避免什么？",
            "choices": ["重复访问顶点", "自动计算边权", "改变顶点编号", "让队列变成栈"],
            "answer": "重复访问顶点",
            "explanation": "图里可能有环或多条路径到同一顶点，visited 可以防止反复进入。",
        },
        "排序稳定性": {
            "question": "判断排序算法是否稳定，重点看什么？",
            "choices": ["相等关键字的相对次序是否保持", "数组长度是否变小", "是否一定 O(1) 空间", "是否只能升序"],
            "answer": "相等关键字的相对次序是否保持",
            "explanation": "稳定性只关心相等元素排序前后的相对先后关系。",
        },
        "边界条件": {
            "question": "做插入、删除或查找前，最应该先检查哪类条件？",
            "choices": ["位置范围和结构是否为空/满", "变量名是否足够短", "输出是否有颜色", "代码行数是否固定"],
            "answer": "位置范围和结构是否为空/满",
            "explanation": "很多 C 语言数据结构错误来自越界、空结构操作或容量不足。",
        },
        "数组元素移动": {
            "question": "顺序表插入时，从后往前移动元素的原因是什么？",
            "choices": ["避免覆盖还没移动的元素", "减少数组容量", "让链表不断开", "自动完成二分查找"],
            "answer": "避免覆盖还没移动的元素",
            "explanation": "如果从前往后移，后面的原值可能先被覆盖。",
        },
        "栈队列规则": {
            "question": "栈和队列最核心的区别是什么？",
            "choices": ["栈后进先出，队列先进先出", "栈只能存数字，队列只能存字符", "栈一定比队列快", "队列不能删除元素"],
            "answer": "栈后进先出，队列先进先出",
            "explanation": "这是判断入栈出栈、入队出队顺序的核心。",
        },
        "树的遍历": {
            "question": "二叉树中序遍历的访问顺序是？",
            "choices": ["左子树 -> 根 -> 右子树", "根 -> 左子树 -> 右子树", "左子树 -> 右子树 -> 根", "按层从左到右"],
            "answer": "左子树 -> 根 -> 右子树",
            "explanation": "前序看根在前，中序看根在中间，后序看根在最后。",
        },
        "概念理解": {
            "question": "学一个数据结构操作时，最关键的是把哪三件事连起来？",
            "choices": ["初始状态、操作步骤、最终结果", "字体、颜色、标题", "文件名、路径、端口", "只背一段代码"],
            "answer": "初始状态、操作步骤、最终结果",
            "explanation": "数据结构学习要看到状态如何一步步变化。",
        },
    }
    quiz = dict(templates.get(primary, templates["概念理解"]))
    quiz["tag"] = primary
    quiz["id"] = re.sub(r"\W+", "_", primary.lower())
    if trace is not None and getattr(trace, "steps", None):
        quiz["review_step"] = min(1, len(trace.steps) - 1)
    return [quiz]


def build_step_links(trace: Any | None, limit: int = 8) -> list[dict[str, Any]]:
    if trace is None or not getattr(trace, "steps", None):
        return []
    links: list[dict[str, Any]] = []
    total = len(trace.steps)
    if total <= limit:
        indexes = list(range(total))
    else:
        indexes = sorted(set([0, total - 1, *[round(i * (total - 1) / (limit - 1)) for i in range(limit)]]))
    for index in indexes:
        step = trace.steps[index]
        links.append(
            {
                "step_index": index,
                "title": f"{index + 1}. {step.title}",
                "description": step.description,
            }
        )
    return links


def render_weak_points_panel() -> None:
    weak_points = auth_store.load_weak_points(
        st.session_state.get("user_id"),
        st.session_state.get("device_id"),
    )
    st.markdown("**薄弱点**")
    if not weak_points:
        st.caption("暂无错题记录。")
        return
    for item in weak_points:
        st.caption(f"{item['tag']}：错 {item['misses']} / 做 {item['attempts']}")

def render_current_trace_demo() -> None:
    trace = st.session_state.get("dsvp_trace")
    request = st.session_state.get("dsvp_request")
    clarification = st.session_state.get("dsvp_clarification")

    trace_steps = list(getattr(trace, "steps", []) or []) if trace is not None else []
    current_for_header = int(st.session_state.get("dsvp_step", 0)) + 1 if trace_steps else 0
    total_for_header = len(trace_steps)
    step_text = f"步骤 {current_for_header}/{total_for_header}" if trace_steps else "等待演示"
    st.markdown(
        f"""
        <div class="demo-topbar">
            <div class="demo-title">演示板</div>
            <div class="demo-step-chip">{html.escape(step_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if clarification:
        st.caption("演示参数需要补齐。")
        st.warning(clarification.message)
        if clarification.missing_fields:
            st.caption("字段：" + ", ".join(clarification.missing_fields))
        if clarification.raw:
            with st.expander("自检详情", expanded=False):
                st.code(clarification.raw)
        return

    if trace is None:
        st.markdown(
            """
            <div class="empty-demo">
                <div class="empty-demo-icon">⌁</div>
                <div class="empty-demo-title">演示板将在此显示数据结构的变化过程</div>
                <div class="empty-demo-copy">提问后，如果内容适合演示，这里会自动加载数组、链表、树或图的步骤。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    steps = trace.steps
    if not steps:
        st.caption("暂无步骤。")
        return

    if "dsvp_step" not in st.session_state:
        st.session_state.dsvp_step = 0
    current = min(max(int(st.session_state.dsvp_step), 0), len(steps) - 1)
    st.session_state.dsvp_step = current
    step = steps[current]

    st.caption(trace.title)
    if request is not None:
        with st.expander("请求 JSON", expanded=False):
            st.json(json.loads(request.model_dump_json(by_alias=True)))

    if trace.errors:
        for error in trace.errors:
            st.error(f"{error.code}：{error.message} {error.detail}")
    if trace.warnings:
        for warning in trace.warnings:
            st.warning(f"{warning.code}：{warning.message} {warning.detail}")

    st.markdown(render_styles(), unsafe_allow_html=True)
    st.markdown(
        (
            '<div class="demo-stage-wrap">'
            f"{render_step_html(step)}"
            f'<div class="demo-step-desc">{html.escape(str(step.description))}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    prev_col, play_col, next_col = st.columns([0.24, 0.24, 0.24], gap="small")
    with prev_col:
        if st.button("‹ 上一步", disabled=current == 0, key="chat_demo_prev", use_container_width=True):
            st.session_state.dsvp_autoplay = False
            st.session_state.dsvp_step = current - 1
            st.rerun()
    with play_col:
        play_label = "暂停" if st.session_state.get("dsvp_autoplay") else "播放"
        if st.button(play_label, key="chat_demo_play", use_container_width=True):
            st.session_state.dsvp_autoplay = not bool(st.session_state.get("dsvp_autoplay"))
            st.rerun()
    with next_col:
        if st.button("下一步 ›", disabled=current == len(steps) - 1, key="chat_demo_next", use_container_width=True):
            st.session_state.dsvp_autoplay = False
            st.session_state.dsvp_step = current + 1
            st.rerun()

    jumped = st.slider(
        "步骤进度",
        min_value=1,
        max_value=len(steps),
        value=current + 1,
        label_visibility="collapsed",
    )
    if jumped - 1 != current:
        st.session_state.dsvp_autoplay = False
        st.session_state.dsvp_step = jumped - 1
        st.rerun()

    if st.session_state.get("dsvp_autoplay"):
        if current < len(steps) - 1:
            time.sleep(0.65)
            st.session_state.dsvp_step = current + 1
            st.rerun()
        else:
            st.session_state.dsvp_autoplay = False

    with st.expander("步骤", expanded=False):
        for index, item in enumerate(steps):
            label = f"{'当前 · ' if index == current else ''}{item.step_id}. {item.title}"
            if st.button(label, key=f"demo_step_jump_{index}", use_container_width=True):
                st.session_state.dsvp_autoplay = False
                st.session_state.dsvp_step = index
                st.rerun()
            if index == current:
                st.caption(item.description)

def main() -> None:
    load_dotenv()
    auth_store.init_db()

    st.set_page_config(
        page_title="数据结构助教",
        page_icon="DS",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            min-height: 100dvh;
            overflow-x: hidden;
            overflow-y: auto;
            scroll-behavior: smooth;
        }
        [data-testid="stMainBlockContainer"] {
            max-width: 1680px;
            padding-top: clamp(0.75rem, 1.6vh, 1.5rem);
            padding-bottom: 0.75rem;
            min-height: 100dvh;
            overflow: visible;
        }
        .st-key-demo_panel {
            max-height: calc(100dvh - 9.25rem);
            min-height: 360px;
            overflow-y: auto;
            overflow-x: hidden;
            overscroll-behavior: contain;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
            padding-right: 0.35rem;
        }
        .st-key-demo_panel [data-testid="stVerticalBlock"] {
            gap: 0.55rem;
        }
        .st-key-knowledge_page {
            max-height: calc(100dvh - 11.5rem);
            min-height: 420px;
            overflow-y: auto;
            overflow-x: hidden;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
            padding-right: 0.35rem;
        }
        .st-key-chat_scroll {
            height: min(560px, calc(100dvh - 18rem)) !important;
            min-height: 300px;
            overflow-y: auto;
            overscroll-behavior: contain;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
        }
        .st-key-ppt_chat_scroll {
            height: min(520px, calc(100dvh - 21rem)) !important;
            min-height: 280px;
            overflow-y: auto;
            overscroll-behavior: contain;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
            padding-right: 0.35rem;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #ffffff;
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
                max-height: calc(100dvh - 7.75rem);
                min-height: 300px;
            }
            .st-key-knowledge_page {
                max-height: calc(100dvh - 9.75rem);
                min-height: 340px;
            }
            .st-key-chat_scroll {
                height: calc(100dvh - 15.75rem) !important;
                min-height: 260px;
            }
            .st-key-ppt_chat_scroll {
                height: calc(100dvh - 19rem) !important;
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
                height: auto !important;
                min-height: 0 !important;
                max-height: none !important;
                overflow: visible !important;
            }
            .st-key-ppt_chat_scroll {
                height: auto !important;
                min-height: 240px !important;
                max-height: 55vh !important;
                overflow-y: auto !important;
            }
            .st-key-demo_panel {
                height: auto;
                min-height: 0;
                max-height: none;
                overflow: visible;
                border-bottom: 1px solid #e5e7eb;
            }
            .st-key-knowledge_page {
                height: auto;
                min-height: 360px;
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

        :root {
            --app-bg: #f3f4f6;
            --panel: #ffffff;
            --panel-muted: #f8f9fa;
            --line: #e5e7eb;
            --line-strong: #d1d5db;
            --text: #1a1a2e;
            --muted: #666666;
            --subtle: #6b7280;
            --blue: #2563eb;
            --green: #10b981;
            --amber: #f59e0b;
            --danger: #ef4444;
            --info-bg: #f0f9ff;
            --info-border: #bae6fd;
            --panel-radius: 16px;
            --control-radius: 8px;
            --panel-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background: var(--app-bg);
            color: var(--text);
            font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
        }
        [data-testid="stMainBlockContainer"] {
            max-width: none;
            padding: 0.55rem 1rem 0.7rem;
        }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--line);
        }
        h1, h2, h3 {
            color: var(--text);
            letter-spacing: 0;
        }
        h3 {
            margin: 0.15rem 0 0.55rem !important;
            font-size: 1.05rem !important;
            font-weight: 750 !important;
        }
        [data-testid="stTabs"] [role="tablist"] {
            gap: 0.25rem;
            padding: 0.25rem;
            border-bottom: 0;
            border-radius: var(--control-radius);
            background: #e5e7eb;
        }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background-color: transparent !important;
        }
        [data-testid="stTabs"] [role="tablist"] > div {
            border-bottom: 0 !important;
        }
        [data-testid="stTabs"] button[role="tab"] {
            padding: 0.5rem 0.85rem;
            color: var(--subtle);
            border-radius: 6px;
            border-bottom: 0 !important;
            transition: background 0.2s, color 0.2s, box-shadow 0.2s;
        }
        [data-testid="stTabs"] button[role="tab"]::before,
        [data-testid="stTabs"] button[role="tab"]::after {
            display: none !important;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--blue);
            background: #ffffff;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        .app-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.45rem;
        }
        .app-title {
            margin: 0;
            font-size: clamp(1.25rem, 1.65vw, 1.65rem);
            line-height: 1.1;
            font-weight: 800;
            color: var(--text);
        }
        .app-subtitle {
            margin-top: 0.2rem;
            color: var(--muted);
            font-size: 0.84rem;
        }
        .app-status-row {
            display: flex;
            justify-content: flex-end;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        .status-chip {
            display: inline-flex;
            align-items: center;
            height: 30px;
            padding: 0 0.58rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #ffffff;
            color: #334155;
            font-size: 0.78rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .status-chip.ok {
            color: #065f46;
            border-color: var(--green);
            background: #d1fae5;
        }
        .status-chip.warn {
            color: #92400e;
            border-color: var(--amber);
            background: #fef3c7;
        }
        .st-key-demo_panel,
        .st-key-knowledge_page,
        .st-key-mainline_page,
        .st-key-chat_shell {
            border: 0;
            border-radius: var(--panel-radius);
            background: var(--panel);
            box-shadow: var(--panel-shadow);
        }
        .st-key-demo_panel {
            height: auto;
            max-height: calc(100dvh - 8.7rem);
            min-height: 520px;
            overflow-y: auto;
            overflow-x: hidden;
            overscroll-behavior: contain;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
            padding: 0.82rem 0.82rem 0.7rem;
        }
        .st-key-chat_shell {
            height: auto;
            max-height: calc(100dvh - 14.4rem);
            min-height: 410px;
            overflow: visible;
            padding: 0.82rem 0.82rem 0.7rem;
        }
        .st-key-chat_scroll {
            height: calc(100dvh - 21.6rem) !important;
            min-height: 250px;
            border: 0 !important;
            background: transparent;
        }
        .st-key-knowledge_page {
            height: auto;
            max-height: calc(100dvh - 9.75rem);
            overflow-y: auto;
            overflow-x: hidden;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
            padding: 1rem;
        }
        .st-key-mainline_page {
            height: auto;
            max-height: calc(100dvh - 9.75rem);
            overflow-y: auto;
            overflow-x: hidden;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
            padding: 1rem;
        }
        .st-key-knowledge_reader_body {
            height: calc(100dvh - 17.4rem);
            min-height: 300px;
            overflow-y: auto;
            overflow-x: hidden;
            padding: 0.1rem 0.35rem 0.1rem 0;
        }
        .stChatMessage {
            border-radius: 8px;
            border-color: var(--line);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
        }
        .stChatMessage [data-testid="stMarkdownContainer"] {
            font-size: 0.95rem;
            line-height: 1.65;
        }
        .empty-demo {
            min-height: 260px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            border: 1px dashed var(--line-strong);
            border-radius: 8px;
            background: var(--panel-muted);
            color: var(--muted);
            padding: 1.25rem;
        }
        .empty-demo-title {
            color: var(--text);
            font-weight: 800;
            font-size: 1rem;
            margin-bottom: 0.35rem;
        }
        .empty-demo-copy {
            max-width: 24rem;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        .lesson-hero {
            border: 1px solid var(--info-border);
            border-radius: var(--panel-radius);
            background: var(--info-bg);
            padding: 1rem 1.1rem;
            margin-bottom: 0.9rem;
        }
        .lesson-kicker {
            color: #0369a1;
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .lesson-title {
            color: var(--text);
            font-size: 1.35rem;
            font-weight: 800;
            line-height: 1.25;
            margin-bottom: 0.35rem;
        }
        .lesson-summary {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.6;
        }
        .st-key-question_form {
            border: 1px solid var(--line);
            border-radius: var(--panel-radius);
            background: #ffffff;
            padding: 0.58rem;
            box-shadow: var(--panel-shadow);
        }
        .st-key-question_form [data-testid="stTextInput"] {
            margin: 0;
        }
        .st-key-question_form [data-testid="stFormSubmitButton"] button {
            min-height: 38px;
            min-width: 54px;
            padding-inline: 1rem;
            white-space: nowrap;
        }
        .stButton > button,
        .stFormSubmitButton > button {
            border-radius: var(--control-radius);
            border: 0;
            background: var(--blue);
            color: #ffffff;
            font-weight: 700;
            transition: background 0.2s, transform 0.2s, box-shadow 0.2s;
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            background: #4338ca;
            color: #ffffff;
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.22);
        }
        .stButton > button:focus-visible,
        .stFormSubmitButton > button:focus-visible {
            outline: 3px solid rgba(79, 70, 229, 0.25);
            outline-offset: 2px;
        }
        @media (max-height: 820px) and (min-width: 901px) {
            .app-topbar {
                margin-bottom: 0.55rem;
            }
            .st-key-demo_panel,
            .st-key-chat_shell {
                max-height: calc(100dvh - 8rem);
                min-height: 390px;
            }
            .st-key-knowledge_page {
                max-height: calc(100dvh - 8.7rem);
            }
            .st-key-knowledge_reader_body {
                height: calc(100dvh - 16.2rem);
            }
            .st-key-chat_scroll {
                height: calc(100dvh - 15.7rem) !important;
                min-height: 220px;
            }
        }
        @media (max-width: 900px) {
            .app-topbar {
                display: block;
            }
            .app-status-row {
                justify-content: flex-start;
                margin-top: 0.65rem;
            }
            .st-key-chat_shell {
                height: auto;
                max-height: none;
                min-height: 0;
                overflow: visible;
            }
            .st-key-demo_panel,
            .st-key-knowledge_page,
            .st-key-mainline_page {
                height: auto;
                max-height: none;
                min-height: 0;
                overflow: visible;
            }
            .st-key-knowledge_reader_body {
                height: auto;
                min-height: 0;
                max-height: none;
                overflow: visible;
            }
            .st-key-chat_scroll {
                height: auto !important;
                min-height: 0 !important;
                max-height: none !important;
                overflow: visible !important;
            }
        }

        /* Modern question workspace */
        :root {
            --qa-blue: #2563eb;
            --qa-line: #e5e7eb;
            --qa-panel: #ffffff;
            --qa-muted: #6b7280;
            --qa-text: #111827;
            --qa-soft: #f3f4f6;
            --qa-green: #22c55e;
            --qa-yellow: #facc15;
            --qa-red: #ef4444;
        }
        html,
        body,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            background: #ffffff !important;
        }
        [data-testid="stMainBlockContainer"] {
            max-width: none !important;
            padding: 0 !important;
        }
        [data-testid="stHeader"] {
            background: transparent;
        }
        #MainMenu,
        footer {
            display: none !important;
        }
        [data-testid="stBaseButton-header"] {
            display: none !important;
        }
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"],
        button[kind="headerNoPadding"],
        [data-testid="stBaseButton-headerNoPadding"] {
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }
        [data-testid="stTabs"] {
            padding: 0;
        }
        [data-testid="stTabs"] [role="tablist"] {
            margin: 0;
            border-radius: 0;
            border-bottom: 1px solid var(--qa-line);
            background: #ffffff;
            padding: 0.35rem 0.75rem;
        }
        [data-testid="stTabs"] button[role="tab"] {
            border-radius: 8px;
        }
        .app-topbar {
            display: none;
        }
        .st-key-chat_shell,
        .st-key-demo_panel {
            height: calc(100dvh - 3.1rem);
            max-height: none;
            min-height: 0;
            border-radius: 0;
            box-shadow: none;
            border: 0;
            background: #ffffff;
            padding: 0;
            overflow: hidden;
        }
        .st-key-chat_shell {
            display: flex !important;
            flex-direction: column;
            position: relative !important;
            height: 100% !important;
            min-height: 0 !important;
            padding-bottom: 108px !important;
        }
        div:has(> .st-key-chat_shell) {
            height: 100% !important;
            min-height: 0 !important;
        }
        .st-key-demo_panel {
            border-left: 1px solid var(--qa-line);
            display: flex;
            flex-direction: column;
            padding: 0.95rem 1rem 0.9rem;
        }
        .st-key-chat_shell [data-testid="stVerticalBlock"] {
            gap: 0;
        }
        .chat-topbar,
        .demo-topbar {
            height: 58px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            border-bottom: 1px solid var(--qa-line);
            background: #ffffff;
        }
        .chat-topbar {
            padding: 0 1.1rem;
        }
        .demo-topbar {
            height: 42px;
            border-bottom: 0;
            margin-bottom: 0.75rem;
        }
        .chat-title,
        .demo-title {
            color: var(--qa-text);
            font-size: 1.08rem;
            font-weight: 800;
            letter-spacing: 0;
        }
        .chat-mode-link,
        .demo-step-chip {
            display: inline-flex;
            align-items: center;
            height: 34px;
            border: 1px solid var(--qa-line);
            border-radius: 8px;
            padding: 0 0.7rem;
            color: #374151;
            background: #ffffff;
            font-size: 0.84rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .demo-step-chip {
            background: #f9fafb;
            color: #4b5563;
        }
        .st-key-chat_scroll {
            flex: 1 1 auto;
            position: absolute !important;
            left: 0 !important;
            right: 0 !important;
            top: 58px !important;
            bottom: 108px !important;
            height: auto !important;
            min-height: 0;
            overflow-y: auto !important;
            overflow-x: hidden;
            padding: 1rem 1.1rem 0.8rem;
            scrollbar-gutter: stable;
            -webkit-overflow-scrolling: touch;
        }
        .chat-welcome {
            max-width: 420px;
            margin: 2rem auto;
            padding: 1.1rem 1.2rem;
            border: 1px dashed #cbd5e1;
            border-radius: 12px;
            background: #f8fafc;
            text-align: center;
        }
        .chat-welcome-title {
            color: var(--qa-text);
            font-weight: 800;
            margin-bottom: 0.35rem;
        }
        .chat-welcome-copy {
            color: var(--qa-muted);
            font-size: 0.92rem;
        }
        div[class*="st-key-msg_user_"],
        div[class*="st-key-msg_assistant_"] {
            width: 100%;
            display: flex;
            flex-direction: column;
            margin: 0.45rem 0 0.75rem;
        }
        div[class*="st-key-msg_user_"] {
            align-items: flex-end;
        }
        div[class*="st-key-msg_assistant_"] {
            align-items: flex-start;
        }
        div[class*="st-key-msg_user_"] > div,
        div[class*="st-key-msg_assistant_"] > div {
            max-width: min(78%, 760px);
        }
        div[class*="st-key-msg_user_"] [data-testid="stMarkdownContainer"],
        div[class*="st-key-msg_assistant_"] [data-testid="stMarkdownContainer"] {
            border-radius: 16px;
            padding: 0.72rem 0.9rem;
            line-height: 1.65;
            font-size: 0.95rem;
            box-shadow: none;
        }
        div[class*="st-key-msg_user_"] [data-testid="stMarkdownContainer"] {
            border-bottom-right-radius: 5px;
            background: var(--qa-blue);
            color: #ffffff;
        }
        div[class*="st-key-msg_assistant_"] [data-testid="stMarkdownContainer"] {
            border-bottom-left-radius: 5px;
            background: var(--qa-soft);
            color: var(--qa-text);
        }
        div[class*="st-key-msg_user_"] [data-testid="stMarkdownContainer"] * {
            color: #ffffff !important;
        }
        div[class*="st-key-msg_user_"] [data-testid="stCaptionContainer"],
        div[class*="st-key-msg_assistant_"] [data-testid="stCaptionContainer"] {
            color: #9ca3af;
            font-size: 0.72rem;
            padding: 0.18rem 0.25rem 0;
        }
        div[class*="st-key-msg_assistant_"] pre,
        div[class*="st-key-msg_user_"] pre {
            border-radius: 10px;
            overflow: auto;
        }
        div[class*="st-key-step_link_"] .stButton > button,
        div[class*="st-key-step_link_"] button {
            min-height: 38px !important;
            justify-content: flex-start !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 8px !important;
            background: #ffffff !important;
            color: #111827 !important;
            box-shadow: none !important;
            transform: none !important;
            font-weight: 700 !important;
        }
        div[class*="st-key-step_link_"] .stButton > button:hover,
        div[class*="st-key-step_link_"] button:hover {
            background: #f8fafc !important;
            border-color: #bfdbfe !important;
            color: #2563eb !important;
            box-shadow: none !important;
            transform: none !important;
        }
        div[class*="st-key-msg_assistant_"] [data-testid="stCaptionContainer"] {
            color: #64748b !important;
            opacity: 1 !important;
        }
        .typing-dots {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 0.78rem 0.95rem;
            border-radius: 16px;
            border-bottom-left-radius: 5px;
            background: var(--qa-soft);
        }
        .typing-dots span {
            width: 7px;
            height: 7px;
            border-radius: 999px;
            background: #9ca3af;
            animation: typing-bounce 1s ease-in-out infinite;
        }
        .typing-dots span:nth-child(2) { animation-delay: 0.15s; }
        .typing-dots span:nth-child(3) { animation-delay: 0.3s; }
        @keyframes typing-bounce {
            0%, 80%, 100% { transform: translateY(0); opacity: 0.45; }
            40% { transform: translateY(-4px); opacity: 1; }
        }
        .st-key-question_form {
            border-radius: 0;
            border: 0;
            box-shadow: none;
            padding: 0.75rem 1.1rem;
            background: #ffffff;
        }
        .st-key-chat_input_bar {
            position: absolute !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            z-index: 5;
            flex: 0 0 auto;
            height: auto !important;
            min-height: 0 !important;
            border-top: 1px solid var(--qa-line);
            background: #ffffff;
        }
        .st-key-chat_input_bar .st-key-question_form {
            padding: 0.75rem 1.1rem;
        }
        .st-key-question_form textarea {
            max-height: 120px;
            min-height: 46px !important;
            resize: vertical;
            border-radius: 10px;
        }
        .st-key-question_form [data-testid="stFormSubmitButton"] button {
            min-height: 46px;
            border-radius: 10px;
            background: var(--qa-blue);
            color: #ffffff;
            font-size: 0;
        }
        .st-key-question_form [data-testid="stFormSubmitButton"] button::after {
            content: ">";
            font-size: 1.05rem;
            line-height: 1;
        }
        .demo-stage-wrap {
            flex: 1;
            min-height: 280px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            border: 1px solid var(--qa-line);
            border-radius: 8px;
            background: #ffffff;
            overflow: auto;
        }
        .demo-step-desc {
            margin: 0.7rem 0 0;
            padding: 0.75rem 0.85rem;
            border-top: 1px solid var(--qa-line);
            color: #4b5563;
            font-size: 0.9rem;
            line-height: 1.6;
            background: #f9fafb;
        }
        .empty-demo {
            min-height: calc(100dvh - 13rem);
            border: 1px dashed #cbd5e1;
            border-radius: 8px;
            background: #f9fafb;
        }
        .empty-demo-icon {
            width: 52px;
            height: 52px;
            display: grid;
            place-items: center;
            margin-bottom: 0.7rem;
            border: 1px solid var(--qa-line);
            border-radius: 12px;
            background: #ffffff;
            color: var(--qa-blue);
            font-size: 1.7rem;
            font-weight: 800;
        }
        .dsvp-wrap {
            border: 0 !important;
            border-radius: 0 !important;
            background: #ffffff !important;
        }
        .dsvp-role-current,
        .dsvp-role-target,
        .dsvp-role-moved,
        .dsvp-role-changed,
        .dsvp-svg-node.current,
        .dsvp-svg-node.target,
        .dsvp-svg-node.changed,
        .dsvp-svg-node.moved {
            background: #fef9c3 !important;
            border-color: var(--qa-yellow) !important;
            color: #713f12 !important;
        }
        .dsvp-role-new,
        .dsvp-role-success,
        .dsvp-svg-node.new,
        .dsvp-svg-node.success {
            background: #dcfce7 !important;
            border-color: var(--qa-green) !important;
            color: #166534 !important;
        }
        .dsvp-role-deleted,
        .dsvp-role-error,
        .dsvp-svg-node.deleted,
        .dsvp-svg-node.error {
            background: #fee2e2 !important;
            border-color: var(--qa-red) !important;
            color: #991b1b !important;
        }
        .st-key-demo_panel .stButton > button {
            background: #f3f4f6;
            color: #111827;
            border-radius: 8px;
            box-shadow: none;
            min-height: 38px;
        }
        .st-key-demo_panel .stButton > button:hover {
            background: #e5e7eb;
            color: #111827;
            transform: none;
            box-shadow: none;
        }
        .st-key-demo_panel [data-testid="stSlider"] {
            padding: 0.15rem 0.1rem 0;
        }
        @media (max-width: 767px) {
            [data-testid="stTabs"] [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
            }
            .st-key-chat_shell {
                height: 60vh;
                border-bottom: 1px solid var(--qa-line);
            }
            .st-key-demo_panel {
                height: 40vh;
                border-left: 0;
                padding: 0.75rem;
            }
            .st-key-chat_scroll {
                top: 52px !important;
                bottom: 108px !important;
                height: auto !important;
                min-height: 0;
            }
            .chat-topbar {
                height: 52px;
                padding: 0 0.85rem;
            }
            div[class*="st-key-msg_user_"] > div,
            div[class*="st-key-msg_assistant_"] > div {
                max-width: 90%;
            }
            .empty-demo {
                min-height: 180px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    device_token = bootstrap_device_token()
    st.session_state.device_token = device_token

    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = ""

    device_id = auth_store.ensure_device(device_token, st.session_state.get("user_id"))
    st.session_state.device_id = device_id
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = auth_store.get_or_create_conversation(st.session_state.get("user_id"), device_id)

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

    if "pending_rag_keywords" not in st.session_state:
        st.session_state.pending_rag_keywords = []

    if "pending_rag_plan" not in st.session_state:
        st.session_state.pending_rag_plan = {}

    load_persisted_messages()

    api_ready = bool(os.getenv("DEEPSEEK_API_KEY"))
    api_label = "模型就绪" if api_ready else "缺少 API Key"
    api_class = "ok" if api_ready else "warn"
    user_label = html.escape(str(st.session_state.get("username") or "本机历史"))
    version_label = html.escape(APP_VERSION)
    st.markdown(
        f"""
        <div class="app-topbar">
            <div>
                <h1 class="app-title">数据结构助教</h1>
                <div class="app-subtitle">问答、C 代码检查、步骤演示、主线学习和知识库阅读</div>
            </div>
            <div class="app-status-row">
                <span class="status-chip {api_class}">{api_label}</span>
                <span class="status-chip">{len(st.session_state.messages)} 条对话</span>
                <span class="status-chip">{user_label}</span>
                <span class="status-chip">{version_label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("状态")
        st.caption(f"版本 `{APP_VERSION}`")

        if api_ready:
            st.success("模型可用")
        else:
            st.warning("缺少 DEEPSEEK_API_KEY")

        st.divider()
        render_auth_panel()

        st.divider()
        st.markdown("**对话**")
        st.caption(f"历史 {len(st.session_state.messages)} 条")
        st.caption(f"设备 `{str(st.session_state.device_token)[:8]}...`")
        if st.session_state.pending_question:
            st.caption(f"处理中：{st.session_state.pending_question}")
        recover_col, clear_col = st.columns(2)
        with recover_col:
            if st.button("恢复"):
                finish_generation()
                st.rerun()
        with clear_col:
            if st.button("清空"):
                st.session_state.messages = []
                if st.session_state.get("conversation_id"):
                    auth_store.clear_messages(int(st.session_state.conversation_id))
                st.session_state.last_contexts = []
                st.session_state.pending_question = ""
                st.session_state.pending_effective_question = ""
                st.session_state.pending_contexts = []
                st.session_state.pending_rag_keywords = []
                st.session_state.pending_rag_plan = {}
                st.session_state.is_generating = False
                st.session_state.generation_started_at = 0.0
                st.session_state.dsvp_request = None
                st.session_state.dsvp_trace = None
                st.session_state.dsvp_step = 0
                st.session_state.dsvp_autoplay = False
                st.session_state.dsvp_clarification = None
                st.rerun()

        st.divider()
        render_weak_points_panel()

    question = ""
    qa_tab, mainline_tab, ppt_tab, knowledge_tab = st.tabs(["问答", "主线学习", "PPT学习模式", "知识库"])

    with qa_tab:
        chat_col, demo_col = st.columns([1.35, 1], gap="large")

        with demo_col:
            demo_placeholder = st.empty()
            with demo_placeholder.container():
                with st.container(key="demo_panel"):
                    render_current_trace_demo()

        with chat_col:
            with st.container(key="chat_shell"):
                st.markdown(
                    """
                    <div class="chat-topbar">
                        <div class="chat-title">自由提问</div>
                        <div class="chat-mode-link">主线学习</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                with st.container(border=False, key="chat_scroll"):
                    render_chat_messages(st.session_state.messages)
                    if st.session_state.pending_question:
                        st.markdown(
                            """
                            <div class="typing-dots" aria-label="AI 正在思考">
                                <span></span><span></span><span></span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    render_contexts(st.session_state.last_contexts)
                with st.container(key="chat_input_bar"):
                    with st.form("question_form", clear_on_submit=True):
                        input_col, send_col = st.columns([1, 0.14], gap="small")
                        with input_col:
                            question = st.text_area(
                                "提问",
                                placeholder="输入你的问题，例如：解释一下冒泡排序",
                                label_visibility="collapsed",
                                height=46,
                            )
                        with send_col:
                            submitted_question = st.form_submit_button("发送")
            if not submitted_question:
                question = ""

    with mainline_tab:
        with st.container(key="mainline_page"):
            render_mainline_learning()

    with ppt_tab:
        with st.container(key="ppt_learning_page"):
            render_ppt_learning_mode()

    with knowledge_tab:
        with st.container(key="knowledge_page"):
            render_knowledge_browser()
    if question and not st.session_state.pending_question:
        retriever = MarkdownKeywordRetriever(KNOWLEDGE_DIR)
        rewrite_client = None
        if _is_ambiguous_follow_up(question):
            try:
                rewrite_client = DeepSeekClient(timeout=20)
            except DeepSeekError:
                rewrite_client = None
        effective_question = build_effective_question(question, st.session_state.messages, rewrite_client)
        rag_keywords = get_recent_rag_keywords(st.session_state.messages)
        rag_client = rewrite_client
        if rag_client is None:
            try:
                rag_client = DeepSeekClient(timeout=20)
            except DeepSeekError:
                rag_client = None
        rag_plan = build_query_rag_plan(rag_client, effective_question, st.session_state.messages, rag_keywords)
        contexts = retrieve_with_rag_memory(retriever, effective_question, rag_keywords, rag_plan=rag_plan, top_k=3)
        st.session_state.last_contexts = contexts
        append_chat_message({"role": "user", "content": question})
        st.session_state.pending_question = question
        st.session_state.pending_effective_question = effective_question
        st.session_state.pending_contexts = contexts
        st.session_state.pending_rag_keywords = rag_keywords
        st.session_state.pending_rag_plan = rag_plan
        st.rerun()

    if not st.session_state.pending_question:
        return

    st.session_state.is_generating = True
    st.session_state.generation_started_at = time.time()
    question = st.session_state.pending_question
    effective_question = st.session_state.get("pending_effective_question") or question
    contexts = st.session_state.pending_contexts
    previous_rag_keywords = list(st.session_state.get("pending_rag_keywords") or [])
    rag_plan = dict(st.session_state.get("pending_rag_plan") or {})
    prior_messages = st.session_state.messages[:-1]
    conversation_context = build_conversation_context(prior_messages)

    try:
        client = DeepSeekClient()
    except DeepSeekError as exc:
        answer = f"调用 DeepSeek API 失败：{exc}"
        append_chat_message({"role": "assistant", "content": answer})
        finish_generation()
        st.rerun()
        return

    if not contexts:
        answer = "知识库资料不足，需要补充教材内容。"
        append_chat_message({"role": "assistant", "content": answer})
        finish_generation()
        st.rerun()
        return

    messages = [
        {"role": "system", "content": load_system_prompt()},
        *build_chat_history_messages(prior_messages),
        {
            "role": "user",
            "content": build_user_prompt(effective_question, contexts),
        },
    ]

    try:
        answer = client.chat(messages)
    except DeepSeekError as exc:
        answer = f"调用 DeepSeek API 失败：{exc}"
        append_chat_message({"role": "assistant", "content": answer})
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
                        "不要提到‘重新检查’‘修正版’等内部过程说明，直接给学生最终答案。\n\n"
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

        current_rag_keywords = build_rag_keywords(
            client,
            prior_messages,
            question,
            effective_question,
            answer,
            previous_rag_keywords,
        )
        visible_answer, code_blocks = make_teaching_view(answer, user_wants_code(question))
        current_trace = st.session_state.get("dsvp_trace")
        quiz = build_interactive_quiz(question, answer, current_rag_keywords, current_trace)
        step_links = build_step_links(current_trace)
        message_id = len(st.session_state.messages)
        append_chat_message(
            {
                "id": message_id,
                "role": "assistant",
                "content": answer if user_wants_code(question) else visible_answer,
                "code_blocks": code_blocks if not user_wants_code(question) else [],
                "show_code": user_wants_code(question),
                "code_check": code_check.summary if code_check.has_code else "",
                "rag_keywords": current_rag_keywords,
                "quiz": quiz,
                "step_links": step_links,
                "demo_request": (
                    json.loads(st.session_state.dsvp_request.model_dump_json(by_alias=True))
                    if st.session_state.get("dsvp_request") is not None
                    else {}
                ),
            }
        )
    except Exception as exc:
        append_chat_message(
            {
                "role": "assistant",
                "content": f"本轮生成时出现异常，已自动恢复输入状态。错误信息：{exc}",
            }
        )
    finish_generation()
    st.rerun()


if __name__ == "__main__":
    main()
