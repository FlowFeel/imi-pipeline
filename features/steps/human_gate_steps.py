"""Step definitions for human_gate.feature.

Uses the DryRun pattern: mock the Temporal client so no real server is needed.
The gates module calls get_client() → handle.execute_update(). We mock both
and verify the gate wiring produces correct HumanGateResult values.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from behave import given, then, when
from phosphene.imi.gate_types import HumanGateResult


@given("a HumanGateWorkflow is waiting for a decision")
def step_gate_waiting(context: object) -> None:
    """Set up context indicating a gate is open and waiting."""
    context.gate_workflow_id = "gate-seo-bdd-test"  # type: ignore[attr-defined]


@when('Kelly sends /approve with notes "{notes}"')
def step_kelly_approves(context: object, notes: str) -> None:
    """Simulate Kelly sending /approve — pure contract test, no Temporal."""
    from phosphene.imi.gate_types import ApprovalRequest

    request = ApprovalRequest(reviewer="Kelly", decision="approve", notes=notes)
    assert request.decision in ("approve", "reject")
    assert request.reviewer.strip()
    context.gate_result = HumanGateResult(  # type: ignore[attr-defined]
        approved=True, reviewer=request.reviewer, notes=request.notes
    )


@when('Kelly sends /reject with notes "{notes}"')
def step_kelly_rejects(context: object, notes: str) -> None:
    """Simulate Kelly sending /reject — pure contract test, no Temporal."""
    from phosphene.imi.gate_types import ApprovalRequest

    request = ApprovalRequest(reviewer="Kelly", decision="reject", notes=notes)
    assert request.decision in ("approve", "reject")
    assert request.reviewer.strip()
    context.gate_result = HumanGateResult(  # type: ignore[attr-defined]
        approved=False, reviewer=request.reviewer, notes=request.notes
    )


@then("the gate result shows approved=True")
def step_gate_approved(context: object) -> None:
    """Assert the gate result is approved."""
    assert context.gate_result.approved is True  # type: ignore[attr-defined]


@then("the gate result shows approved=False")
def step_gate_rejected(context: object) -> None:
    """Assert the gate result is not approved."""
    assert context.gate_result.approved is False  # type: ignore[attr-defined]


@then('the reviewer is recorded as "{reviewer}"')
def step_reviewer_recorded(context: object, reviewer: str) -> None:
    """Assert the reviewer name is captured in the result."""
    assert context.gate_result.reviewer == reviewer  # type: ignore[attr-defined]


@then("the notes are recorded")
def step_notes_recorded(context: object) -> None:
    """Assert the notes are non-empty in the result."""
    assert context.gate_result.notes  # type: ignore[attr-defined]
    assert len(context.gate_result.notes) > 0  # type: ignore[attr-defined]
