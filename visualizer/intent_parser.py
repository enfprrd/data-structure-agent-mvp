from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from visualizer.protocol import (
    Clarification,
    OperationRequest,
    supported_demo_summary,
    validation_to_clarification,
)


COURSE_OPERATION_VOCABULARY = """
本地右侧可视化已经实现的 structure/operation 组合如下，只有这些会真的播放动画：
{supported_demo_pairs}

如果用户要演示的内容不在上面，不要硬塞成已支持的 operation。请仍然输出合法 OperationRequest，并使用下面课程词表中最贴切的 structure/operation；前台会告知“JSON 合法，但本地暂不支持该演示”。

课程词表：
- stack: push, pop, linked_push, linked_pop, base_conversion, bracket_matching, expression_bracket_check, infix_to_postfix, postfix_evaluation, prefix_evaluation, expression_evaluation, call_stack, recursion_trace, hanoi_recursive, hanoi_iterative, maze_backtracking, dfs_iterative, binary_tree_preorder_iterative, binary_tree_inorder_iterative, binary_tree_postorder_iterative, browser_history, undo_redo, tag_matching, syntax_parse_stack, monotonic_stack, next_greater_element, largest_rectangle, daily_temperatures, stack_sort, two_stacks_queue, reverse_stack, train_rearrangement, pop_sequence_validation
- string: naive_match, kmp_match
- array: address_mapping, matrix_transpose, sparse_matrix_transpose
- generalized_list: head_tail, depth, length
- binary_tree: traverse_preorder, traverse_inorder, traverse_postorder, traverse_level_order, threaded_binary_tree, huffman_build
- tree: forest_to_binary_tree, binary_tree_to_forest
- graph: build, dfs, bfs, dijkstra, prim, kruskal, floyd, topological_sort, critical_path
- search_table: sequential_search, binary_search, block_search
- binary_search_tree: search, insert, delete
- balanced_binary_tree: search, insert, rotate
- b_tree: search, insert
- hash_table: search, insert, delete
- sort: bubble_sort, insertion_sort, selection_sort, quick_sort, shell_sort, heap_sort, merge_sort, radix_sort
- external_sort: multiway_merge, replacement_selection, loser_tree, optimal_merge_tree

禁止把 operation 写成 value、target、position、data、array、node 这类参数名或对象名。
""".strip()


PARSER_SYSTEM_PROMPT = f"""
你是数据结构演示意图与请求解析器。你的任务不是回答用户问题，而是把“对话 + 助手教学回答 + C 代码”规整成严格 JSON。

总原则：
- 只输出 JSON，不要 Markdown，不要解释。
- 必须优先依据助手回答末尾 C 代码中的 main、初始化数据、函数调用、实参、position/value/target/values。
- 如果文字讲解和 C 代码冲突，以 C 代码为准。
- 如果没有演示意图，输出 {{"needs_demo": false}}。
- 如果有演示意图，输出 needs_demo=true，并给出完整 OperationRequest 字段。
- 如果用户说“继续演示”“展示一下”，结合此前完整对话上下文，使用最近主题和最近可用数据。

严格 JSON schema：
{{
  "needs_demo": true,
  "version": "1.0",
  "structure": "结构名",
  "operation": "操作名",
  "params": {{
    "mode": "可选",
    "position": 1,
    "value": 9,
    "target": 9,
    "values": [3, 5, 7],
    "capacity": 10
  }},
  "initial_state": {{
    "data": [3, 5, 7],
    "metadata": {{"index_base": 1, "use_head_node": true, "capacity": 10}}
  }},
  "options": {{"language": "c", "explain_level": "beginner"}}
}}

字段要求：
- structure 和 operation 必须是字符串，不能留空。
- params 必须存在；没有参数也输出空对象。
- initial_state.data 必须是数组。树、图、排序等也要尽量从 C 代码或文字中抽取初始数据；图可用顶点、边或邻接矩阵的数组表达。
- metadata 默认写入 index_base=1、use_head_node=true、capacity=10，除非题目或代码明确给了别的约定。
- 图演示必须保留用户给出的顶点标签；用户给的是 1,2,3,4,5 就必须输出 metadata.vertices=["1","2","3","4","5"]，不要改成 A,B,C,D,E。
- 图如果使用邻接矩阵表示 initial_state.data，必须同时在 metadata.vertices 中给出矩阵行列对应的顶点标签。
- 图 DFS/BFS 的起点必须放在 metadata.start 或 params.value/target 中，并且标签要和 metadata.vertices 保持一致。
- 图如果没有边权，不要凭空生成 weight；无向图要写 metadata.directed=false。
- 用户给出“邻接表 1: 2,3；2: 1,4,5”时，按邻接表解析，不要把逗号后的数字理解为边权。
- 位置序号默认从 1 开始。
- 单链表默认带头结点。
- 顺序表、栈、队列默认 capacity=10，除非代码或题目明确给出。

本地已支持演示的参数要求：
- sequential_list insert/delete/search：insert/delete 必须有 params.position；insert 必须有 params.value；search 必须有 params.target。
- singly_linked_list insert/delete/search/build：insert/delete 必须有 params.position；insert 必须有 params.value；search 必须有 params.target；build 必须有 params.values，mode 用 head_insert 或 tail_insert。
- stack push/pop：push 必须有 params.value。
- stack 的经典应用：优先使用上面 stack 词表里的 operation；表达式类可把 token 放到 params.values；汉诺塔可把盘子数放到 params.value；括号/标签可把字符串放到 params.value；出栈序列、火车调度目标序列可放到 params.values。
- queue enqueue/dequeue：enqueue 必须有 params.value。

头插/尾插建表示例：
- 头插建表：structure=singly_linked_list，operation=build，params.mode=head_insert，params.values 保持代码/main 中的输入顺序。
- 尾插建表：structure=singly_linked_list，operation=build，params.mode=tail_insert，params.values 保持代码/main 中的输入顺序。
- values 表示输入顺序，不是最终链表顺序。

{COURSE_OPERATION_VOCABULARY.format(supported_demo_pairs=supported_demo_summary())}

如果用户确实要演示，但结合对话、回答和 C 代码仍缺少 initial_state.data、position、value、target、values 等必要信息，输出：
{{
  "needs_demo": true,
  "needs_clarification": true,
  "message": "具体说明缺少什么",
  "missing_fields": ["initial_state.data"]
}}
""".strip()


def parse_operation_request(client: Any, text: str, max_attempts: int = 2) -> OperationRequest | Clarification | None:
    feedback = ""
    last_raw = ""
    last_clarification: Clarification | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            raw = _call_parser(client, text, feedback)
        except RuntimeError as exc:
            return Clarification(message=str(exc), raw=str(exc))
        last_raw = raw
        payload = _load_json(raw)
        if payload is None:
            last_clarification = Clarification(
                message="DeepSeek 返回的不是合法 JSON，正在尝试重新生成。",
                raw=raw,
            )
            feedback = _build_retry_feedback(last_clarification, raw)
            continue

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
            last_clarification = validation_to_clarification(exc, raw=raw)
            feedback = _build_retry_feedback(last_clarification, raw)

    if last_clarification is not None:
        last_clarification.message = "DeepSeek 重新生成后，演示 JSON 仍不完整或格式不合法。"
        last_clarification.raw = last_clarification.raw or last_raw
        return last_clarification

    return Clarification(message="解析演示请求失败。", raw=last_raw)


def parse_operation_request_payload(payload: dict[str, Any]) -> OperationRequest | Clarification:
    payload = _normalize_payload(payload)
    try:
        return OperationRequest.model_validate(payload)
    except ValidationError as exc:
        return validation_to_clarification(exc, raw=json.dumps(payload, ensure_ascii=False))


def _call_parser(client: Any, text: str, feedback: str = "") -> str:
    user_content = text
    if feedback:
        user_content = (
            f"{text}\n\n"
            "上一次 JSON 没有通过本地自检。请只重新输出一个完整、严格、合法的 JSON；"
            "不要解释，不要 Markdown。\n"
            f"本地自检反馈：\n{feedback}"
        )
    try:
        return client.chat(
            [
                {"role": "system", "content": PARSER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=800,
        )
    except Exception as exc:
        raise RuntimeError(f"解析请求时调用 DeepSeek 失败：{exc}") from exc


def _build_retry_feedback(clarification: Clarification, raw: str) -> str:
    missing = ", ".join(clarification.missing_fields) if clarification.missing_fields else "未能定位到字段"
    return (
        f"问题：{clarification.message}\n"
        f"缺失或错误字段：{missing}\n"
        f"本地错误详情：{clarification.raw}\n"
        f"上一次原始输出：{raw}"
    )


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

    normalized["params"] = params
    if "version" not in normalized and not normalized.get("needs_clarification"):
        normalized["version"] = "1.0"
    if "options" not in normalized and not normalized.get("needs_clarification"):
        normalized["options"] = {"language": "c", "explain_level": "beginner"}

    initial_state = normalized.get("initial_state")
    if isinstance(initial_state, dict):
        initial_state.setdefault("metadata", {"index_base": 1, "use_head_node": True, "capacity": 10})

    return normalized
