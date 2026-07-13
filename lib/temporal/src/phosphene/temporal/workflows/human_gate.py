"""HumanGateWorkflow — a gate is a decision, not a notification.

A gate pauses a workflow and waits for a typed response. The caller
submits a decision and receives the outcome in the same round-trip.
This is the semantic contract: a gate is a synchronous decision point,
not an asynchronous message. Choosing Temporal Update over Signal is
choosing the primitive whose semantics match this contract.

Signal means "a thing happened." It confirms delivery to the Temporal
server but says nothing about whether the workflow accepted the payload
or what the outcome was. The sender would need to poll a separate query
to learn whether the decision was valid. Update means "a decision was
made and acknowledged." The sender blocks until the workflow processes
the Update and returns ``HumanGateResult``. The gate *is* this
synchronous exchange.

The concrete consequence: with Update, the Telegram reply to Kelly says
"✅ Approved" only after the workflow has accepted the decision. With
Signal, the reply could only say "✅ Sent" — the decision might be
rejected by the validator, and Kelly would not know.

The validator runs before the handler. Malformed decisions — invalid
strings, empty reviewer — are rejected before they mutate state. The
workflow remains in its waiting state; the gate stays open for a valid
retry. Validation is a pure predicate. Mutation is in the handler. The
result is returned from the handler. Three phases, cleanly separated.

Time-skipping in tests exercises the real timeout path.
``WorkflowEnvironment.start_time_skipping()`` intercepts Temporal's
timer machinery at the SDK level, advancing the virtual clock past
``timedelta(hours=48)`` instantly. The workflow uses real ``timedelta``
objects and real ``wait_condition`` calls. The test proves the timeout
behaviour, not a mock of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow


@dataclass
class HumanGateInput:
    """Input to HumanGateWorkflow.

    Attributes:
        prompt: The question or instruction shown to the reviewer.
        requester: Who initiated this gate (e.g. ``"flow"``).
        channel: Delivery channel for the prompt (e.g. ``"telegram"``).
        timeout_hours: Business hours before the gate times out.
    """

    prompt: str
    requester: str
    channel: str = "telegram"
    timeout_hours: int = 48


@dataclass
class ApprovalRequest:
    """Update payload from the reviewer.

    Attributes:
        reviewer: Name or ID of the reviewer submitting the decision.
        decision: Either ``"approve"`` or ``"reject"``.
        notes: Optional reviewer notes or rationale.
    """

    reviewer: str
    decision: str
    notes: str = ""


@dataclass
class HumanGateResult:
    """Result returned by HumanGateWorkflow.

    Attributes:
        approved: True if the reviewer approved, False otherwise.
        reviewer: Name of the reviewer who decided.
        notes: Optional reviewer notes.
        timed_out: True if the gate expired without a decision.
    """

    approved: bool
    reviewer: str | None = None
    notes: str | None = None
    timed_out: bool = False


@workflow.defn
class HumanGateWorkflow:
    """Durable decision point — pauses a workflow until a human responds.

    The pause is durable: Temporal holds the workflow state across process
    restarts, deploys, and outages. A gate opened on Monday can be
    approved on Wednesday with no process staying alive in between.

    The interaction primitive is Update, not Signal. A gate requires a
    synchronous exchange: the caller submits a decision and receives
    ``HumanGateResult`` in the same round-trip. Signal would express
    the wrong contract — delivery confirmation without decision
    acknowledgement.

    The validator gates mutation: malformed inputs are rejected before
    the handler runs. The workflow state stays unchanged; the gate
    remains open for a valid retry.

    Integration with TaskFlow::

        # Human-gate steps become child workflows:
        result = await workflow.execute_child_workflow(
            HumanGateWorkflow.run,
            HumanGateInput(prompt=step.instruction, requester="flow"),
            id=f"gate-{workflow.info().workflow_id}-step-{step.index}",
        )
        if not result.approved:
            # Handle rejection ...

    Integration with Telegram::

        # Flow receives /approve from Kelly, calls:
        handle = client.get_workflow_handle(gate_workflow_id)
        result = await handle.execute_update(
            HumanGateWorkflow.submit_decision,
            ApprovalRequest(reviewer="Kelly", decision="approve", notes="LGTM"),
        )
        # result.approved is True; Flow confirms to Kelly.
    """

    def __init__(self) -> None:
        """Initialise with no decision pending."""
        self._decision: HumanGateResult | None = None
        self._gate: HumanGateInput | None = None

    @workflow.update
    async def submit_decision(self, request: ApprovalRequest) -> HumanGateResult:
        """Update handler: reviewer submits approve or reject.

        Mutates workflow state so ``wait_condition`` unblocks.
        Returns ``HumanGateResult`` to the caller synchronously.

        Args:
            request: The reviewer's decision.

        Returns:
            ``HumanGateResult`` with the decision outcome.
        """
        self._decision = HumanGateResult(
            approved=(request.decision == "approve"),
            reviewer=request.reviewer,
            notes=request.notes,
        )
        return self._decision

    @submit_decision.validator
    def validate_decision(self, request: ApprovalRequest) -> None:
        """Reject malformed decisions before mutating state.

        Args:
            request: The incoming approval request.

        Raises:
            ValueError: If ``decision`` is not ``"approve"`` or ``"reject"``,
                or if ``reviewer`` is empty.
        """
        if request.decision not in ("approve", "reject"):
            raise ValueError(
                f"Invalid decision: {request.decision!r}. "
                "Must be 'approve' or 'reject'."
            )
        if not request.reviewer.strip():
            raise ValueError("reviewer must not be empty.")

    @workflow.query
    def get_prompt(self) -> str:
        """Return the prompt text for display to reviewers.

        Returns:
            The prompt string from the input, or empty string before run() starts.
        """
        return self._gate.prompt if self._gate is not None else ""

    @workflow.run
    async def run(self, gate: HumanGateInput) -> HumanGateResult:
        """Wait for a reviewer decision or time out.

        Args:
            gate: Input containing prompt, requester, and timeout.

        Returns:
            ``HumanGateResult`` — approved, rejected, or timed_out.
        """
        self._gate = gate
        timeout_seconds = gate.timeout_hours * 3600

        try:
            await workflow.wait_condition(
                lambda: self._decision is not None,
                timeout=timedelta(seconds=timeout_seconds),
            )
        except TimeoutError:
            return HumanGateResult(approved=False, timed_out=True)

        assert self._decision is not None  # type narrowing
        return self._decision
