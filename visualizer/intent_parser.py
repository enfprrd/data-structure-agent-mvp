from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from visualizer.protocol import Clarification, OperationRequest, validation_to_clarification


PARSER_SYSTEM_PROMPT = """你是数据结构演示请求解析器。
你只能把用户自然语言解析为 OperationRequest JSON，不能生成演示步骤、动画、指针变化或数组移动过程。
只输出严格 JSON，不要 Markdown，不要解释。

第一阶段 structure 只能是：
- sequential_list
- singly_linked_list
- stack
- queue

第一阶段 operation 只能是：
- insert
- delete
- search
- push
- pop
- enqueue
- dequeue

教材约定：
- 位置序号使用 1 开始。
- 单链表默认带头结点。
- 顺序表、栈、队列默认 capacity 为 10，除非用户明确给出容量。

如果用户缺少 initial_state.data、position、value、target 等必要信息，输出：
{"needs_clarification": true, "message": "说明缺少什么", "missing_fields": ["..."]}

合法 OperationRequest 必须使用 params 包裹操作参数，例如：
{
  "version": "1.0",
  "structure": "singly_linked_list",
  "operation": "insert",
  "params": {"mode": "by_position", "position": 2, "value": 9},
  "initial_state": {"data": [3, 5, 7], "metadata": {"index_base": 1, "use_head_node": true, "capacity": 10}},
  "options": {"language": "c", "explain_level": "beginner"}
}
"""


def parse_operation_request(client: Any, text: str) -> OperationRequest | Clarification:
    local_request = infer_operation_request_locally(text)
    if local_request is not None:
        return local_request

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
        local_request = infer_operation_request_locally(f"{text}\n{raw}")
        if local_request is not None:
            return local_request
        return Clarification(message="DeepSeek 返回的不是合法 JSON，请重新描述演示需求。", raw=raw)

    payload = _normalize_payload(payload)

    if isinstance(payload, dict) and payload.get("needs_clarification"):
        local_request = infer_operation_request_locally(f"{text}\n{raw}")
        if local_request is not None:
            return local_request
        return Clarification(
            message=str(payload.get("message") or "演示参数还不完整，请补充。"),
            missing_fields=[str(item) for item in payload.get("missing_fields", []) if item],
            raw=raw,
        )

    try:
        return OperationRequest.model_validate(payload)
    except ValidationError as exc:
        local_request = infer_operation_request_locally(f"{text}\n{raw}")
        if local_request is not None:
            return local_request
        return validation_to_clarification(exc, raw=raw)


def parse_operation_request_payload(payload: dict[str, Any]) -> OperationRequest | Clarification:
    payload = _normalize_payload(payload)
    try:
        return OperationRequest.model_validate(payload)
    except ValidationError as exc:
        return validation_to_clarification(exc, raw=json.dumps(payload, ensure_ascii=False))


def infer_operation_request_locally(text: str) -> OperationRequest | None:
    compact = text.replace(" ", "")
    if not any(word in compact for word in ("演示", "展示", "可视化", "逐步", "一步步", "插入", "删除", "查找", "头插", "尾插")):
        return None

    linked_data = _extract_linked_initial_data(text)
    sequence_data = _extract_sequence_data(text)
    operation = _infer_operation(text)
    structure = _infer_structure(text, linked_data, sequence_data)
    insert_mode = _infer_insert_mode(text)
    value = _infer_value(text, operation)
    target = _infer_target(text)
    position = _infer_position(text, operation, insert_mode)

    if structure == "singly_linked_list":
        data = linked_data or sequence_data
        if operation == "insert" and insert_mode == "head" and position is None:
            position = 1
        if operation == "insert" and position == 1 and value is not None and data and data[0] == value:
            data = data[1:]
        if operation == "insert" and insert_mode == "tail" and data:
            position = len(data) + 1
        metadata = {"index_base": 1, "use_head_node": True, "capacity": 10}
    elif structure == "sequential_list":
        data = sequence_data or linked_data
        metadata = {"index_base": 1, "capacity": 10}
    else:
        return None

    params: dict[str, Any] = {"mode": "by_position"}
    if operation in {"insert", "delete"}:
        if position is None:
            return None
        params["position"] = position
    if operation == "insert":
        if value is None:
            return None
        params["value"] = value
    if operation == "search":
        if target is None:
            return None
        params["target"] = target

    if not data:
        return None

    payload = {
        "version": "1.0",
        "structure": structure,
        "operation": operation,
        "params": params,
        "initial_state": {"data": data, "metadata": metadata},
        "options": {"language": "c", "explain_level": "beginner"},
    }
    try:
        return OperationRequest.model_validate(payload)
    except ValidationError:
        return None


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


def _infer_structure(text: str, linked_data: list[int], sequence_data: list[int]) -> str | None:
    if any(word in text for word in ("单链表", "链表", "head->next", "head ->", "头插", "尾插")) or linked_data:
        return "singly_linked_list"
    if any(word in text for word in ("顺序表", "线性表", "数组")) or sequence_data:
        return "sequential_list"
    return None


def _infer_operation(text: str) -> str:
    if any(word in text for word in ("删除", "删去")):
        return "delete"
    if "查找" in text:
        return "search"
    return "insert"


def _infer_insert_mode(text: str) -> str | None:
    head_index = max(text.rfind("头插"), text.rfind("表头插入"), text.rfind("head->next"))
    tail_index = max(text.rfind("尾插"), text.rfind("表尾插入"), text.rfind("尾部插入"), text.rfind("r->next"))
    if head_index < 0 and tail_index < 0:
        return None
    return "tail" if tail_index > head_index else "head"


def _extract_linked_initial_data(text: str) -> list[int]:
    direct_matches = re.findall(r"用\s*([0-9,\s，、-]+)\s*演示\s*(?:带头结点)?单?链表", text)
    if direct_matches:
        values = [int(item) for item in re.findall(r"-?\d+", direct_matches[-1])]
        if values:
            return values

    candidates = re.findall(
        r"(?:初始(?:链表)?|当前(?:带头结点)?单链表)[：:\s]*head\s*(?:->|→)\s*([^\n\r]*?)\s*(?:->|→)\s*NULL",
        text,
        flags=re.IGNORECASE,
    )
    if candidates:
        candidates = [candidates[-1]]
    if not candidates:
        candidates = re.findall(
            r"(?<!结果[：:])head\s*(?:->|→)\s*([^\n\r]*?)\s*(?:->|→)\s*NULL",
            text,
            flags=re.IGNORECASE,
        )
    if not candidates:
        return []

    for candidate in candidates:
        values = [int(item) for item in re.findall(r"-?\d+", candidate)]
        if values:
            return values
    return []


def _extract_sequence_data(text: str) -> list[int]:
    patterns = [
        r"用\s*顺序表\s*([0-9,\s，、-]+)\s*演示",
        r"顺序表\s*\[([0-9,\s，、-]+)\]",
        r"\[([0-9,\s，、-]+)\]",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            values = [int(item) for item in re.findall(r"-?\d+", matches[-1])]
            if values:
                return values
    return []


def _infer_position(text: str, operation: str, insert_mode: str | None = None) -> int | None:
    if insert_mode == "head":
        return 1
    if insert_mode == "tail":
        return None
    match = re.search(r"第\s*(\d+)\s*(?:位|个|位置)", text)
    if match:
        return int(match.group(1))
    match = re.search(r'"position"\s*:\s*(\d+)', text)
    if match:
        return int(match.group(1))
    if operation == "insert" and "表头" in text:
        return 1
    return None


def _infer_value(text: str, operation: str) -> int | None:
    if operation != "insert":
        return None
    patterns = [
        r"插入\s*(?:元素|新结点)?\s*(-?\d+)",
        r"(?:s->data|data)\s*=\s*(-?\d+)",
        r"新结点\s*s?[：:\s]*(-?\d+)",
        r"用头插法插入\s*(-?\d+)",
        r"插入\s*`?(-?\d+)`?",
        r'"value"\s*:\s*(-?\d+)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return int(matches[-1])
    return None


def _infer_target(text: str) -> int | None:
    patterns = [
        r"查找\s*(-?\d+)",
        r"目标(?:值)?\s*[：:=]\s*(-?\d+)",
        r'"target"\s*:\s*(-?\d+)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return int(matches[-1])
    return None


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
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
