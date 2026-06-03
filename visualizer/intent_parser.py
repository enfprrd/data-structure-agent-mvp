from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from visualizer.protocol import Clarification, OperationRequest, validation_to_clarification


PARSER_SYSTEM_PROMPT = """你是数据结构演示意图与请求解析器。
你只能判断是否需要演示，并在需要演示时把自然语言、助手回答和 C 代码规整为 OperationRequest JSON。
你不能生成演示步骤、动画、指针变化或数组移动过程。
只输出严格 JSON，不要 Markdown，不要解释。

先判断用户新问题是否需要右侧演示：
- 如果不需要演示，输出：{"needs_demo": false}
- 如果需要演示，输出 needs_demo=true，并给出完整 OperationRequest。
- 用户说“演示一下”“展示一下”“继续演示”时，要结合此前完整对话上下文，使用最近的主题和最近可用的数据。
- 如果输入中包含“助手刚刚输出的回答（包含用于演示理解的 C 代码）”，必须优先依据这段回答和其中 C 代码判断演示参数。
- C 代码中的 main、初始化数据、调用的操作函数、实参 position/value/target 是最高优先级依据。
- 如果文字讲解和 C 代码冲突，以 C 代码为准。
- 如果最近主题是“头插法建表”或 C 代码是在循环调用头插函数建立链表，operation 必须是 build，params.mode 必须是 head_insert，params.values 必须保持代码/main 中的输入顺序。
- 如果最近主题是“尾插法建表”或 C 代码是在循环调用尾插函数建立链表，operation 必须是 build，params.mode 必须是 tail_insert，params.values 必须保持代码/main 中的输入顺序。
- 注意 values 表示输入顺序，不是最终链表顺序。比如依次头插 30、20、10，应输出 values=[30,20,10]，本地模拟器会得到 10->20->30。
- 只有“在已有链表某个位置插入一个新元素”才使用 operation=insert。

第一阶段 structure 只能是：
- sequential_list
- singly_linked_list
- stack
- queue

第一阶段 operation 只能是：
- insert
- delete
- search
- build
- push
- pop
- enqueue
- dequeue

教材约定：
- 位置序号使用 1 开始。
- 单链表默认带头结点。
- 顺序表、栈、队列默认 capacity 为 10，除非用户明确给出容量。

如果用户需要演示，但结合上下文仍缺少 initial_state.data、position、value、target 等必要信息，输出：
{"needs_demo": true, "needs_clarification": true, "message": "说明缺少什么", "missing_fields": ["..."]}

合法 OperationRequest 必须使用 params 包裹操作参数，例如：
{
  "needs_demo": true,
  "version": "1.0",
  "structure": "singly_linked_list",
  "operation": "insert",
  "params": {"mode": "by_position", "position": 2, "value": 9},
  "initial_state": {"data": [3, 5, 7], "metadata": {"index_base": 1, "use_head_node": true, "capacity": 10}},
  "options": {"language": "c", "explain_level": "beginner"}
}

头插建表示例：
{
  "needs_demo": true,
  "version": "1.0",
  "structure": "singly_linked_list",
  "operation": "build",
  "params": {"mode": "head_insert", "values": [30, 20, 10]},
  "initial_state": {"data": [], "metadata": {"index_base": 1, "use_head_node": true, "capacity": 10}},
  "options": {"language": "c", "explain_level": "beginner"}
}
"""


def parse_operation_request(client: Any, text: str) -> OperationRequest | Clarification | None:
    raw = ""
    try:
        raw = client.chat(
            [
                {"role": "system", "content": PARSER_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=500,
        )
    except Exception as exc:
        return Clarification(message=f"解析请求时调用 DeepSeek 失败：{exc}", raw=str(exc))

    payload = _load_json(raw)
    if payload is None:
        return Clarification(message="DeepSeek 返回的不是合法 JSON，请重新描述演示需求。", raw=raw)

    payload = _normalize_payload(payload)

    if payload.get("needs_demo") is False:
        return None

    if isinstance(payload, dict) and payload.get("needs_clarification"):
        return Clarification(
            message=str(payload.get("message") or "演示参数还不完整，请补充。"),
            missing_fields=[str(item) for item in payload.get("missing_fields", []) if item],
            raw=raw,
        )

    try:
        return OperationRequest.model_validate(payload)
    except ValidationError as exc:
        return validation_to_clarification(exc, raw=raw)


def parse_operation_request_payload(payload: dict[str, Any]) -> OperationRequest | Clarification:
    payload = _normalize_payload(payload)
    try:
        return OperationRequest.model_validate(payload)
    except ValidationError as exc:
        return validation_to_clarification(exc, raw=json.dumps(payload, ensure_ascii=False))


def _load_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("needs_demo") is True and isinstance(payload.get("request"), dict):
        wrapped = dict(payload["request"])
        wrapped["needs_demo"] = True
        payload = wrapped

    normalized = dict(payload)
    params = normalized.get("params")
    if not isinstance(params, dict):
        params = {}

    for key in ("mode", "position", "value", "target", "values", "capacity"):
        if key in normalized and key not in params:
            params[key] = normalized.pop(key)

    if params:
        normalized["params"] = params
    if "version" not in normalized and not normalized.get("needs_clarification"):
        normalized["version"] = "1.0"
    if "options" not in normalized and not normalized.get("needs_clarification"):
        normalized["options"] = {"language": "c", "explain_level": "beginner"}

    initial_state = normalized.get("initial_state")
    if isinstance(initial_state, dict):
        initial_state.setdefault("metadata", {"index_base": 1, "use_head_node": True, "capacity": 10})

    return normalized
