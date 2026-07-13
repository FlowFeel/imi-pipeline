"""TaskFlow data models — serialisable inputs and outputs for Temporal workflows.

These dataclasses are the wire format between TaskFlowWorkflow and its
Activities. They must be fully serialisable by Temporal's default data
converter (JSON via ``dataclasses_json``-compatible paths).

``StepInput`` is what the Activity receives.
``StepOutput`` is what the Activity returns.
``TaskBrief`` is the workflow input — replaces
``phosphene.taskflow.models.TaskManifest``.
``TaskResult`` is the workflow output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepInput:
    """Serialisable input to a single TaskFlow step Activity.

    The Activity receives this, executes the instruction, returns ``StepOutput``.

    Attributes:
        index: Zero-based step position in the pipeline.
        kind: Step kind — determines dispatch strategy
            (e.g. ``"core/generate"``, ``"core/human-gate"``).
        title: Human-readable step title for progress display.
        instruction: The instruction text to execute.
        depends_on: Indices of steps that must complete before this one.
        timeout_seconds: Maximum execution time before Temporal kills the Activity.
    """

    index: int
    kind: str
    title: str
    instruction: str
    depends_on: list[int] = field(default_factory=list)
    timeout_seconds: int = 300


@dataclass
class StepOutput:
    """Result of a single TaskFlow step Activity.

    Attributes:
        index: The step index this output corresponds to.
        succeeded: Whether the step completed successfully.
        output: Human-readable output or result summary.
        artifact: Optional path or URI to a produced artifact.
        error: Error message if the step failed.
    """

    index: int
    succeeded: bool
    output: str = ""
    artifact: str | None = None
    error: str | None = None


@dataclass
class TaskBrief:
    """Input to TaskFlowWorkflow.

    Replaces ``phosphene.taskflow.models.TaskManifest`` as the workflow input.
    Must be fully serialisable by Temporal's default data converter.

    Attributes:
        title: Human-readable job title.
        description: Job description for logging and display.
        requester: Who initiated this job (e.g. ``"jan"``, ``"flow"``).
        steps: Ordered list of steps to execute.
        domain: Domain tag for routing and display (e.g. ``"platform"``).
    """

    title: str
    description: str
    requester: str
    steps: list[StepInput] = field(default_factory=list)
    domain: str = "platform"


@dataclass
class TaskResult:
    """Output of TaskFlowWorkflow.

    Attributes:
        succeeded: True if all steps completed successfully.
        step_outputs: Collected outputs from all executed steps.
        blocked_at_index: Index of the step that caused failure, if any.
        error: Error message if the workflow failed.
    """

    succeeded: bool
    step_outputs: list[StepOutput] = field(default_factory=list)
    blocked_at_index: int | None = None
    error: str | None = None
