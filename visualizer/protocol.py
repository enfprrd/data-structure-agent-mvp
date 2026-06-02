from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SUPPORTED_STRUCTURES = {"sequential_list", "singly_linked_list", "stack", "queue"}
SUPPORTED_OPERATIONS = {"insert", "delete", "search", "push", "pop", "enqueue", "dequeue"}
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
    values: list[int | str] | None = None
    capacity: int | None = None


class InitialState(ProtocolModel):
    data: list[int | str]
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
    structure: Literal["sequential_list", "singly_linked_list", "stack", "queue"]
    operation: Literal["insert", "delete", "search", "push", "pop", "enqueue", "dequeue"]
    params: RequestParams = Field(default_factory=RequestParams)
    initial_state: InitialState
    options: RequestOptions = Field(default_factory=RequestOptions)

    @model_validator(mode="after")
    def validate_supported_pair_and_params(self) -> "OperationRequest":
        allowed = {
            "sequential_list": {"insert", "delete", "search"},
            "singly_linked_list": {"insert", "delete", "search"},
            "stack": {"push", "pop"},
            "queue": {"enqueue", "dequeue"},
        }
        if self.operation not in allowed[self.structure]:
            raise ValueError(f"{self.structure} 不支持操作 {self.operation}。")

        missing: list[str] = []
        if self.operation in {"insert", "delete"} and self.params.position is None:
            missing.append("params.position")
        if self.operation in {"insert", "push", "enqueue"} and self.params.value is None:
            missing.append("params.value")
        if self.operation == "search" and self.params.target is None:
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
        message="演示参数还不完整或格式不合法，请补充后再演示。",
        missing_fields=missing,
        raw=raw or "; ".join(messages),
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
