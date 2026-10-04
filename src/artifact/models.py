from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):

    click = "click"
    fill = "fill"
    read = "read"
    extract = "extract"
    wait = "wait"
    navigate = "navigate"
    complete = "complete"
    escalate = "escalate"


class Target(BaseModel):

    strategy: str = "semantic"

    role: str | None = None

    name: str | None = None

    label: str | None = None

    text: str | None = None

    css: str | None = None


class ExpectedState(BaseModel):

    kind: Literal[
        "text_present",
        "url_contains",
        "one_of_texts",
        "none"
    ] = "none"

    value: str | list[str] | None = None


class Step(BaseModel):

    id: str

    action: ActionType

    target: Target | None = None

    value: str | None = None

    output_name: str | None = None

    expected_state: ExpectedState | None = None

    retry_count: int = 0


class FieldSpec(BaseModel):

    type: str

    required: bool = True

    description: str | None = None


class Checkpoint(BaseModel):

    kind: Literal[
        "text_present",
        "url_contains",
        "one_of_texts"
    ]

    value: str | list[str]


class Capability(BaseModel):

    schema_version: str = "1.0"

    name: str

    description: str

    inputs: dict[str, FieldSpec]

    outputs: dict[str, FieldSpec]

    steps: list[Step]

    checkpoint: Checkpoint


class ResultStatus(str, Enum):

    success = "success"

    business_outcome = "business_outcome"

    recoverable_error = "recoverable_error"

    failure = "failure"


class ReplayResult(BaseModel):

    status: ResultStatus

    outputs: dict[str, Any] = Field(
        default_factory=dict
    )

    code: str | None = None

    message: str | None = None

    step_id: str | None = None

    expected: Any | None = None

    observed: Any | None = None