"""Human gate wiring — approve or reject a HumanGateWorkflow via Temporal Update.

Flow starts a HumanGateWorkflow when a human decision is needed (SEO package
approval, publish confirmation, etc.). The reviewer sends /approve or /reject
via Telegram. This module receives the command and submits it as a Temporal
Update — not a Signal.

Why Update, not Signal: Signal is fire-and-forget. The sender submits a Signal
and gets back an acknowledgement that the Temporal server received the message,
not that the workflow processed it. If the workflow has already completed,
cancelled, or is in a bad state, the Signal is silently dropped. The reviewer
would see "approved" in Telegram but the gate would remain stuck.

Update is a synchronous exchange: the submitter blocks until the workflow
processes the request and returns a result. Kelly (or Jan) needs to know her
approval was received *and valid* — not merely delivered to the Temporal
server. Update provides that guarantee: the returned ``HumanGateResult``
confirms the decision was applied to workflow state before the Telegram
response is sent.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.temporal.client import get_client
from phosphene.temporal.workflows.human_gate import (
    ApprovalRequest,
    HumanGateResult,
    HumanGateWorkflow,
)


async def approve_gate(
    workflow_id: str, reviewer: str, notes: str = ""
) -> HumanGateResult:
    """Approve a pending HumanGateWorkflow.

    Connects to Temporal, fetches the workflow handle, and submits an
    ``approve`` Update. Returns ``HumanGateResult`` synchronously —
    the caller knows the decision was accepted before replying to the
    reviewer.

    Args:
        workflow_id: The Temporal workflow ID of the gate to approve.
        reviewer: Name or ID of the reviewer submitting the decision.
        notes: Optional reviewer notes or rationale.

    Returns:
        ``HumanGateResult`` with ``approved=True``.
    """
    client = await get_client()
    handle = client.get_workflow_handle(workflow_id)
    return await handle.execute_update(
        HumanGateWorkflow.submit_decision,
        ApprovalRequest(reviewer=reviewer, decision="approve", notes=notes),
    )


async def reject_gate(
    workflow_id: str, reviewer: str, notes: str = ""
) -> HumanGateResult:
    """Reject a pending HumanGateWorkflow.

    Same mechanics as :func:`approve_gate` but with ``decision="reject"``.

    Args:
        workflow_id: The Temporal workflow ID of the gate to reject.
        reviewer: Name or ID of the reviewer submitting the decision.
        notes: Optional reviewer notes or rationale.

    Returns:
        ``HumanGateResult`` with ``approved=False``.
    """
    client = await get_client()
    handle = client.get_workflow_handle(workflow_id)
    return await handle.execute_update(
        HumanGateWorkflow.submit_decision,
        ApprovalRequest(reviewer=reviewer, decision="reject", notes=notes),
    )


async def get_gate_status(workflow_id: str) -> str:
    """Query a HumanGateWorkflow for its current prompt.

    Returns the prompt string if the gate is still waiting, or ``"closed"``
    if the workflow has completed or the prompt is empty.

    Args:
        workflow_id: The Temporal workflow ID to query.

    Returns:
        The prompt string, or ``"closed"`` if the gate is no longer active.
    """
    client = await get_client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        prompt = await handle.query(HumanGateWorkflow.get_prompt)
        return prompt if prompt else "closed"
    except Exception:
        return "closed"
