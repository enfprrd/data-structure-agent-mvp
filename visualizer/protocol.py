from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SUPPORTED_DEMO_PAIRS = {
    "sequential_list": {"insert", "delete", "search"},
    "singly_linked_list": {"insert", "delete", "search", "build"},
    "stack": {
        "push",
        "pop",
        "linked_push",
        "linked_pop",
        "base_conversion",
        "bracket_matching",
        "expression_bracket_check",
        "infix_to_postfix",
        "postfix_evaluation",
        "prefix_evaluation",
        "expression_evaluation",
        "call_stack",
        "recursion_trace",
        "hanoi_recursive",
        "hanoi_iterative",
        "maze_backtracking",
        "dfs_iterative",
        "binary_tree_preorder_iterative",
        "binary_tree_inorder_iterative",
        "binary_tree_postorder_iterative",
        "browser_history",
        "undo_redo",
        "tag_matching",
        "syntax_parse_stack",
        "monotonic_stack",
        "next_greater_element",
        "largest_rectangle",
        "daily_temperatures",
        "stack_sort",
        "two_stacks_queue",
        "reverse_stack",
        "train_rearrangement",
        "pop_sequence_validation",
    },
    "queue": {"enqueue", "dequeue"},
    "binary_tree": {"traverse_preorder", "traverse_inorder", "traverse_postorder", "traverse_level_order"},
    "graph": {"build", "dfs", "bfs", "dijkstra", "prim", "kruskal", "floyd", "topological_sort"},
    "search_table": {"sequential_search", "binary_search"},
    "sort": {"bubble_sort", "insertion_sort", "selection_sort", "quick_sort", "merge_sort"},
}
SUPPORTED_STRUCTURES = set(SUPPORTED_DEMO_PAIRS)
SUPPORTED_OPERATIONS = {operation for operations in SUPPORTED_DEMO_PAIRS.values() for operation in operations}
SUPPORTED_ACTION_TYPES = {
    "check_condition",
    "create_node",
    "delete_node",
    "assign",
    "link",
    "unlink",
    "move",
    "shift",
    "compare",
    "visit",
    "push",
    "pop",
    "enqueue",
    "dequeue",
}
SUPPORTED_ROLES = {
    "current",
    "previous",
    "target",
    "new",
    "deleted",
    "moved",
    "visited",
    "changed",
    "success",
    "error",
}


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class RequestParams(ProtocolModel):
    mode: str | None = None
    position: int | None = None
    value: int | str | None = None
    target: int | str | None = None
    values: list[Any] | None = None
    capacity: int | None = None


class InitialState(ProtocolModel):
    data: list[Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data", mode="before")
    @classmethod
    def data_must_be_array(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("initial_state.data 必须是数组。")
        return value


class RequestOptions(ProtocolModel):
    language: str = "c"
    explain_level: str = "beginner"


class OperationRequest(ProtocolModel):
    version: str = "1.0"
    structure: str
    operation: str
    params: RequestParams = Field(default_factory=RequestParams)
    initial_state: InitialState
    options: RequestOptions = Field(default_factory=RequestOptions)

    @model_validator(mode="after")
    def validate_request_shape(self) -> "OperationRequest":
        self.structure = self.structure.strip()
        self.operation = self.operation.strip()
        if not self.structure:
            raise ValueError("structure 不能为空。")
        if not self.operation:
            raise ValueError("operation 不能为空。")

        if not is_supported_demo_pair(self.structure, self.operation):
            return self

        missing: list[str] = []
        if self.operation in {"insert", "delete"} and self.params.position is None:
            missing.append("params.position")
        if self.operation in {"insert", "push", "enqueue"} and self.params.value is None:
            missing.append("params.value")
        if self.operation == "search" and self.params.target is None:
            missing.append("params.target")
        if self.structure == "singly_linked_list" and self.operation == "build" and not self.params.values:
            missing.append("params.values")
        if self.structure == "search_table" and self.params.target is None:
            missing.append("params.target")
        if missing:
            raise ValueError("缺少必要字段：" + ", ".join(missing))
        return self


class Summary(ProtocolModel):
    initial: str
    result: str
    time_complexity: str
    space_complexity: str


class DSVPError(ProtocolModel):
    code: str
    message: str
    detail: str = ""
    recoverable: bool = True


class DSVPWarning(ProtocolModel):
    code: str
    message: str
    detail: str = ""
    recoverable: bool = True


class Action(ProtocolModel):
    type: Literal[
        "check_condition",
        "create_node",
        "delete_node",
        "assign",
        "link",
        "unlink",
        "move",
        "shift",
        "compare",
        "visit",
        "push",
        "pop",
        "enqueue",
        "dequeue",
    ]
    description: str
    target: str | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    value: Any | None = None


class HighlightItem(ProtocolModel):
    role: Literal[
        "current",
        "previous",
        "target",
        "new",
        "deleted",
        "moved",
        "visited",
        "changed",
        "success",
        "error",
    ]


class NodeHighlight(HighlightItem):
    id: str


class EdgeHighlight(HighlightItem):
    from_: str = Field(alias="from")
    to: str


class CellHighlight(HighlightItem):
    index: int


class PointerHighlight(HighlightItem):
    name: str


class Highlights(ProtocolModel):
    nodes: list[NodeHighlight] = Field(default_factory=list)
    edges: list[EdgeHighlight] = Field(default_factory=list)
    cells: list[CellHighlight] = Field(default_factory=list)
    pointers: list[PointerHighlight] = Field(default_factory=list)


class Step(ProtocolModel):
    step_id: int
    phase: str
    title: str
    description: str
    state: dict[str, Any]
    highlights: Highlights = Field(default_factory=Highlights)
    actions: list[Action] = Field(default_factory=list)
    code_refs: list[str] = Field(default_factory=list)
    message: str = ""


class VisualizationTrace(ProtocolModel):
    version: str = "1.0"
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    structure: str
    operation: str
    summary: Summary
    steps: list[Step] = Field(default_factory=list)
    errors: list[DSVPError] = Field(default_factory=list)
    warnings: list[DSVPWarning] = Field(default_factory=list)


class Clarification(BaseModel):
    needs_clarification: bool = True
    message: str
    missing_fields: list[str] = Field(default_factory=list)
    raw: str = ""


def validation_to_clarification(exc: ValidationError, raw: str = "") -> Clarification:
    missing: list[str] = []
    messages: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        if loc:
            missing.append(loc)
        messages.append(str(error.get("msg", "")))
    return Clarification(
        message="DeepSeek 生成的演示 JSON 参数不完整或格式不合法，正在尝试重新生成。",
        missing_fields=missing,
        raw=raw or "; ".join(messages),
    )


def is_supported_demo_pair(structure: str, operation: str) -> bool:
    return operation in SUPPORTED_DEMO_PAIRS.get(structure, set())


def supported_demo_summary() -> str:
    return "\n".join(
        f"- {structure}: {', '.join(sorted(operations))}"
        for structure, operations in SUPPORTED_DEMO_PAIRS.items()
    )


def make_error_trace(
    request: OperationRequest,
    code: str,
    message: str,
    detail: str,
    initial: str,
) -> VisualizationTrace:
    return VisualizationTrace(
        title=f"{request.structure} {request.operation} 演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(
            initial=initial,
            result=initial,
            time_complexity="O(1)",
            space_complexity="O(1)",
        ),
        steps=[
            Step(
                step_id=1,
                phase="error",
                title="参数检查失败",
                description=message,
                state={},
                highlights=Highlights(),
                actions=[
                    Action(
                        type="check_condition",
                        description=detail,
                        target="request",
                    )
                ],
                message=detail,
            )
        ],
        errors=[DSVPError(code=code, message=message, detail=detail, recoverable=True)],
    )


def make_unsupported_trace(request: OperationRequest) -> VisualizationTrace:
    supported = supported_demo_summary()
    detail = (
        f"DeepSeek 已生成合法 OperationRequest：structure={request.structure}, "
        f"operation={request.operation}。\n"
        "这说明不是参数格式错误，而是本地右侧演示器暂未实现这一类动画。\n\n"
        f"当前本地可视化支持：\n{supported}"
    )
    initial = str(request.initial_state.data)
    return VisualizationTrace(
        title="当前操作暂不支持可视化演示",
        structure=request.structure,
        operation=request.operation,
        summary=Summary(
            initial=initial,
            result=initial,
            time_complexity="取决于该算法",
            space_complexity="取决于该算法",
        ),
        steps=[
            Step(
                step_id=1,
                phase="unsupported",
                title="本地演示器暂不支持",
                description=detail,
                state={"kind": "unsupported", "request": request.model_dump()},
                highlights=Highlights(),
                actions=[
                    Action(
                        type="check_condition",
                        description="JSON 合法，但没有对应的本地可视化模拟器。",
                        target="dispatcher",
                    )
                ],
                message=detail,
            )
        ],
        warnings=[
            DSVPWarning(
                code="UNSUPPORTED_DEMO",
                message="当前操作暂不支持右侧可视化演示。",
                detail=detail,
                recoverable=False,
            )
        ],
    )
