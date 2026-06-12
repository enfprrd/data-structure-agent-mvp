from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from conversation_context import format_message_history
from llm import DeepSeekClient, DeepSeekError
from rag import MarkdownKeywordRetriever


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+")
CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```|(?:^|\n)(?: {4}|\t).+", re.MULTILINE)


@dataclass
class SlideCard:
    deck_id: str
    slide_id: int
    title: str
    raw_text: str
    notes: str
    tables: list[list[list[str]]] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    concept_type: str = "unknown"

    @property
    def has_text(self) -> bool:
        return bool(self.raw_text.strip() or self.notes.strip() or self.tables)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContextPack:
    current_slide: SlideCard
    prev_slide: dict[str, Any] | None
    next_slide: dict[str, Any] | None
    deck_outline: list[dict[str, Any]]
    retrieved_slides: list[SlideCard]
    conversation_summary: str
    textbook_contexts: list[dict[str, str]] = field(default_factory=list)


def parse_pptx_to_slide_cards(
    deck_id: str,
    pptx_bytes: bytes,
    client: DeepSeekClient | None = None,
) -> list[SlideCard]:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise RuntimeError("缺少 python-pptx，请先安装 requirements.txt 中的依赖。") from exc

    presentation = Presentation(BytesIO(pptx_bytes))
    cards: list[SlideCard] = []
    for index, slide in enumerate(presentation.slides, start=1):
        card = _extract_slide(deck_id, index, slide)
        if card.has_text:
            _enrich_slide_card(card, client)
        else:
            card.summary = "该页没有可提取的文本内容，第一阶段不猜测图片信息。"
            card.keywords = ["text_missing"]
            card.concept_type = "text_missing"
        cards.append(card)
    return cards


def render_pptx_slide_images(
    deck_id: str,
    pptx_bytes: bytes,
    output_root: Path | str,
    width: int = 1440,
    height: int = 810,
) -> list[str]:
    output_dir = (Path(output_root) / deck_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in output_dir.glob("slide_*.png"):
        try:
            path.unlink()
        except Exception:
            pass

    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return []

    with tempfile.TemporaryDirectory(prefix="ppt_render_") as temp_dir:
        temp_path = Path(temp_dir) / f"{deck_id}.pptx"
        temp_path.write_bytes(pptx_bytes)

        powerpoint = None
        presentation = None
        pythoncom.CoInitialize()
        try:
            powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
            presentation = powerpoint.Presentations.Open(
                str(temp_path),
                ReadOnly=True,
                Untitled=False,
                WithWindow=False,
            )
            rendered: list[str] = []
            for index in range(1, presentation.Slides.Count + 1):
                image_path = output_dir / f"slide_{index:03d}.png"
                presentation.Slides(index).Export(str(image_path), "PNG", width, height)
                rendered.append(str(image_path))
            return rendered
        except Exception:
            return []
        finally:
            if presentation is not None:
                try:
                    presentation.Close()
                except Exception:
                    pass
            if powerpoint is not None:
                try:
                    powerpoint.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
    return []


def discover_local_pptx_files(directory: Path | str) -> list[Path]:
    base = Path(directory)
    if not base.exists() or not base.is_dir():
        return []
    return sorted(
        [path for path in base.iterdir() if path.is_file() and path.suffix.lower() == ".pptx"],
        key=lambda path: path.name.lower(),
    )


def build_context_pack(
    slide_cards: list[SlideCard],
    current_slide_id: int,
    question: str,
    conversation_messages: list[dict[str, str]] | None = None,
    textbook_retriever: MarkdownKeywordRetriever | None = None,
    top_k: int = 3,
) -> ContextPack:
    if not slide_cards:
        raise ValueError("slide_cards 不能为空")

    index = min(max(current_slide_id - 1, 0), len(slide_cards) - 1)
    current_slide = slide_cards[index]
    retrieved = retrieve_related_slides(slide_cards, question, current_slide.slide_id, top_k=top_k)
    textbook_contexts = (
        textbook_retriever.retrieve(question, top_k=2, boost_terms=current_slide.keywords)
        if textbook_retriever is not None and question.strip()
        else []
    )
    return ContextPack(
        current_slide=current_slide,
        prev_slide=_slide_brief(slide_cards[index - 1]) if index > 0 else None,
        next_slide=_slide_brief(slide_cards[index + 1]) if index < len(slide_cards) - 1 else None,
        deck_outline=[{"slide_id": card.slide_id, "title": card.title or f"第 {card.slide_id} 页"} for card in slide_cards],
        retrieved_slides=retrieved,
        conversation_summary=summarize_conversation(conversation_messages or []),
        textbook_contexts=textbook_contexts,
    )


def answer_with_context_pack(
    client: DeepSeekClient,
    context_pack: ContextPack,
    question: str,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是 PPT-Aware 数据结构学习助教。你只能读取用户提供的 PPT 文本、备注、表格、"
                "检索到的相关页和本地教材片段；不能声称看过 PPT 图片或截图。"
            ),
        },
        {"role": "user", "content": build_ppt_user_prompt(context_pack, question)},
    ]
    return client.chat(messages, temperature=0.2, max_tokens=2200)


def build_ppt_user_prompt(context_pack: ContextPack, question: str) -> str:
    pack = context_pack_to_prompt_dict(context_pack)
    return f"""
用户当前正在阅读 PPT 第 {context_pack.current_slide.slide_id} 页。

用户问题：
{question}

ContextPack（只包含当前页完整文本、相邻页摘要、目录、相关页和少量教材片段）：
{json.dumps(pack, ensure_ascii=False, indent=2)}

回答规则：
1. 优先依据 current_slide。
2. 其次依据 prev_slide、next_slide 和 retrieved_slides。
3. 再参考 textbook_contexts。
4. 如果 PPT 文本没有相关信息，明确说“不在当前 PPT 文本中”，不要猜图片内容。
5. 每个关键结论必须标注来源页码，例如“来源：第 3 页”或“来源：第 3、5 页”。
6. 如果 current_slide.concept_type 是 text_missing，先提示该页可提取文本不足。
7. 不要说你看到了图片、图表截图或视觉布局；第一阶段只做文本版。
"""


def context_pack_to_prompt_dict(context_pack: ContextPack) -> dict[str, Any]:
    return {
        "current_slide": context_pack.current_slide.to_dict(),
        "prev_slide": context_pack.prev_slide,
        "next_slide": context_pack.next_slide,
        "deck_outline": context_pack.deck_outline,
        "retrieved_slides": [
            {
                "slide_id": card.slide_id,
                "title": card.title,
                "summary": card.summary,
                "keywords": card.keywords,
                "raw_text_excerpt": _shorten(card.raw_text, 900),
            }
            for card in context_pack.retrieved_slides
        ],
        "conversation_summary": context_pack.conversation_summary,
        "textbook_contexts": context_pack.textbook_contexts,
    }


def retrieve_related_slides(
    slide_cards: list[SlideCard],
    question: str,
    current_slide_id: int,
    top_k: int = 3,
) -> list[SlideCard]:
    query_tokens = _tokenize(question)
    if not query_tokens:
        query_tokens = _tokenize(" ".join(_find_slide(slide_cards, current_slide_id).keywords))
    scored: list[tuple[int, SlideCard]] = []
    for card in slide_cards:
        if card.slide_id == current_slide_id:
            continue
        haystack = " ".join(
            [
                card.title,
                card.raw_text,
                card.notes,
                card.summary,
                " ".join(card.keywords),
                _tables_to_text(card.tables),
            ]
        ).lower()
        score = sum(haystack.count(token.lower()) for token in query_tokens)
        for keyword in card.keywords:
            if keyword and keyword.lower() in question.lower():
                score += 4
        if score > 0:
            scored.append((score, card))
    scored.sort(key=lambda item: (-item[0], item[1].slide_id))
    return [card for _, card in scored[:top_k]]


def summarize_conversation(messages: list[dict[str, object]], max_items: int = 6) -> str:
    return format_message_history(
        messages,
        include_code_blocks=False,
        max_messages=max_items,
        per_message_limit=180,
        empty_text="暂无会话上下文。",
        separator="\n",
    )


def _extract_slide(deck_id: str, slide_id: int, slide: Any) -> SlideCard:
    title = _extract_title(slide)
    text_parts: list[str] = []
    tables: list[list[list[str]]] = []

    for shape in slide.shapes:
        if getattr(shape, "has_table", False):
            tables.append(_extract_table(shape.table))
            continue
        if getattr(shape, "has_text_frame", False):
            text = shape.text_frame.text.strip()
            if text:
                text_parts.append(text)

    notes = _extract_notes(slide)
    raw_text = _dedupe_join([title, *text_parts])
    code_blocks = [match.group(0).strip() for match in CODE_BLOCK_PATTERN.finditer(raw_text)]
    return SlideCard(
        deck_id=deck_id,
        slide_id=slide_id,
        title=title,
        raw_text=raw_text,
        notes=notes,
        tables=tables,
        code_blocks=code_blocks,
    )


def _extract_title(slide: Any) -> str:
    title_shape = getattr(slide.shapes, "title", None)
    if title_shape is not None and getattr(title_shape, "has_text_frame", False):
        return title_shape.text_frame.text.strip()
    for shape in slide.shapes:
        if getattr(shape, "has_text_frame", False):
            text = shape.text_frame.text.strip()
            if text:
                return text.splitlines()[0].strip()
    return ""


def _extract_table(table: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([cell.text.strip() for cell in row.cells])
    return rows


def _extract_notes(slide: Any) -> str:
    try:
        notes_slide = slide.notes_slide
        text_frame = notes_slide.notes_text_frame
    except Exception:
        return ""
    return text_frame.text.strip() if text_frame is not None else ""


def _enrich_slide_card(card: SlideCard, client: DeepSeekClient | None) -> None:
    fallback_summary = _extractive_summary(card)
    card.summary = fallback_summary
    card.keywords = _extract_keywords(card)
    card.concept_type = "text"

    if client is None:
        return
    try:
        raw = client.chat(
            [
                {
                    "role": "system",
                    "content": "你只输出 JSON，不要解释。字段：summary, keywords, concept_type。",
                },
                {
                    "role": "user",
                    "content": (
                        "请基于这一页 PPT 的可提取文本生成元数据，不要猜测图片内容。\n"
                        f"标题：{card.title}\n"
                        f"正文：{_shorten(card.raw_text, 3500)}\n"
                        f"备注：{_shorten(card.notes, 1200)}\n"
                        f"表格：{_shorten(_tables_to_text(card.tables), 1200)}\n"
                        '输出 JSON 示例：{"summary":"...","keywords":["..."],"concept_type":"definition|algorithm|example|exercise|overview|text"}'
                    ),
                },
            ],
            temperature=0,
            max_tokens=500,
        )
    except DeepSeekError:
        return
    meta = _parse_slide_meta(raw)
    if meta:
        card.summary = meta.get("summary") or fallback_summary
        card.keywords = meta.get("keywords") or card.keywords
        card.concept_type = meta.get("concept_type") or card.concept_type


def _parse_slide_meta(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    keywords = data.get("keywords")
    if not isinstance(keywords, list):
        keywords = []
    return {
        "summary": str(data.get("summary") or "").strip()[:500],
        "keywords": [str(item).strip()[:30] for item in keywords if str(item).strip()][:10],
        "concept_type": str(data.get("concept_type") or "text").strip()[:30],
    }


def _extractive_summary(card: SlideCard) -> str:
    text = " ".join([card.title, card.raw_text, card.notes, _tables_to_text(card.tables)]).strip()
    if not text:
        return "该页没有可提取的文本内容，第一阶段不猜测图片信息。"
    sentences = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    summary = " ".join(sentence.strip() for sentence in sentences if sentence.strip())[:240]
    return summary or _shorten(text, 240)


def _extract_keywords(card: SlideCard, limit: int = 8) -> list[str]:
    text = " ".join([card.title, card.raw_text, card.notes, _tables_to_text(card.tables)])
    tokens = _tokenize(text)
    counts: dict[str, int] = {}
    for token in tokens:
        if len(token) <= 1 and not token.isascii():
            continue
        counts[token] = counts.get(token, 0) + 1
    return [token for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text) if token.strip()]


def _slide_brief(card: SlideCard) -> dict[str, Any]:
    return {
        "slide_id": card.slide_id,
        "title": card.title,
        "summary": card.summary,
        "keywords": card.keywords,
        "concept_type": card.concept_type,
    }


def _find_slide(slide_cards: list[SlideCard], slide_id: int) -> SlideCard:
    for card in slide_cards:
        if card.slide_id == slide_id:
            return card
    return slide_cards[0]


def _tables_to_text(tables: list[list[list[str]]]) -> str:
    lines: list[str] = []
    for table_index, table in enumerate(tables, start=1):
        lines.append(f"表格 {table_index}:")
        for row in table:
            lines.append(" | ".join(row))
    return "\n".join(lines)


def _dedupe_join(parts: list[str]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for line in part.splitlines():
            normalized = line.strip()
            if not normalized or normalized in seen:
                continue
            lines.append(normalized)
            seen.add(normalized)
    return "\n".join(lines)


def _shorten(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."
