from __future__ import annotations

from typing import Any


def format_message_history(
    messages: list[dict[str, object]],
    *,
    include_code_blocks: bool = True,
    max_messages: int | None = None,
    per_message_limit: int | None = None,
    empty_text: str = "暂无会话上下文。",
    user_label: str = "用户",
    assistant_label: str = "助教",
    separator: str = "\n\n",
) -> str:
    """Format a conversation into a readable context block.

    This is used by both the chat flow and the PPT learning flow so they
    can share the same history rendering behavior while still tuning the
    amount of context they expose.
    """

    if max_messages is not None:
        items = messages[-max_messages:]
    else:
        items = messages

    lines: list[str] = []
    for message in items:
        role = str(message.get("role", "user"))
        label = user_label if role == "user" else assistant_label
        content = str(message.get("content", "")).strip()
        if include_code_blocks:
            content = _append_code_blocks(content, message.get("code_blocks"))
        if per_message_limit is not None and len(content) > per_message_limit:
            content = content[:per_message_limit].rstrip() + "..."
        if content:
            lines.append(f"{label}：{content}")

    return separator.join(lines) if lines else empty_text


def build_chat_history_messages(
    messages: list[dict[str, object]],
    *,
    include_code_blocks: bool = True,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content", "")).strip()
        if include_code_blocks:
            content = _append_code_blocks(content, message.get("code_blocks"))
        if content:
            history.append({"role": role, "content": content})
    return history


def _append_code_blocks(content: str, code_blocks: Any) -> str:
    if not code_blocks:
        return content
    return content + "\n" + "\n".join(str(block) for block in code_blocks)
