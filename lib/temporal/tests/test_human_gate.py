"""Tests for HumanGateWorkflow.

Verifies Update handler, validator, approval/rejection flow,
timeout with time-skipping, and Query for prompt text.
"""

from __future__ import annotations

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


class TestHumanGateWorkflow:
    """HumanGateWorkflow pauses on Update, resumes on approve/reject."""

    @pytest.mark.asyncio
    async def test_human_gate_is_importable(self) -> None:
        """HumanGateWorkflow can be imported."""
        from phosphene.temporal.workflows.human_gate import (  # noqa: F401
            ApprovalRequest,
            HumanGateInput,
            HumanGateResult,
            HumanGateWorkflow,
        )

    @pytest.mark.asyncio
    async def test_approve_update_resolves_gate(self) -> None:
        """submit_decision Update with approve=True resolves and returns approved result."""
        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateInput,
            HumanGateWorkflow,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate",
                workflows=[HumanGateWorkflow],
                activities=[],
            ):
                handle = await env.client.start_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt="Please approve the SEO package",
                        requester="flow",
                        timeout_hours=48,
                    ),
                    id="test-gate-approve",
                    task_queue="test-gate",
                )

                gate_result = await handle.execute_update(
                    HumanGateWorkflow.submit_decision,
                    ApprovalRequest(
                        reviewer="Kelly",
                        decision="approve",
                        notes="Looks good",
                    ),
                )

                result = await handle.result()

        assert gate_result.approved is True
        assert gate_result.reviewer == "Kelly"
        assert gate_result.notes == "Looks good"
        assert result.approved is True
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_reject_update_resolves_gate_as_not_approved(self) -> None:
        """submit_decision with decision=reject resolves as not approved."""
        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateInput,
            HumanGateWorkflow,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate-reject",
                workflows=[HumanGateWorkflow],
                activities=[],
            ):
                handle = await env.client.start_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt="Approve?",
                        requester="flow",
                        timeout_hours=48,
                    ),
                    id="test-gate-reject",
                    task_queue="test-gate-reject",
                )

                await handle.execute_update(
                    HumanGateWorkflow.submit_decision,
                    ApprovalRequest(reviewer="Kelly", decision="reject"),
                )

                result = await handle.result()

        assert result.approved is False
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_timeout_resolves_as_timed_out(self) -> None:
        """Gate times out when no Update arrives; start_time_skipping advances instantly."""
        from phosphene.temporal.workflows.human_gate import (
            HumanGateInput,
            HumanGateWorkflow,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate-timeout",
                workflows=[HumanGateWorkflow],
                activities=[],
            ):
                # timeout_hours=0 would be invalid; use 1 second via timeout_seconds override
                # We use timeout_hours=1 — time-skipping advances past it instantly
                result = await env.client.execute_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt="This will time out",
                        requester="flow",
                        timeout_hours=1,
                    ),
                    id="test-gate-timeout",
                    task_queue="test-gate-timeout",
                )

        assert result.timed_out is True
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_validator_rejects_invalid_decision(self) -> None:
        """Validator raises before mutating state when decision is not approve/reject."""
        from temporalio.client import WorkflowUpdateFailedError

        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateInput,
            HumanGateWorkflow,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate-validator",
                workflows=[HumanGateWorkflow],
                activities=[],
            ):
                handle = await env.client.start_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt="Approve?",
                        requester="flow",
                        timeout_hours=1,
                    ),
                    id="test-gate-validator",
                    task_queue="test-gate-validator",
                )

                with pytest.raises(WorkflowUpdateFailedError):
                    await handle.execute_update(
                        HumanGateWorkflow.submit_decision,
                        ApprovalRequest(reviewer="Kelly", decision="maybe"),
                    )

    @pytest.mark.asyncio
    async def test_validator_rejects_empty_reviewer(self) -> None:
        """Validator rejects empty reviewer string."""
        from temporalio.client import WorkflowUpdateFailedError

        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateInput,
            HumanGateWorkflow,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate-empty-reviewer",
                workflows=[HumanGateWorkflow],
                activities=[],
            ):
                handle = await env.client.start_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt="Approve?", requester="flow", timeout_hours=1
                    ),
                    id="test-gate-empty-reviewer",
                    task_queue="test-gate-empty-reviewer",
                )

                with pytest.raises(WorkflowUpdateFailedError):
                    await handle.execute_update(
                        HumanGateWorkflow.submit_decision,
                        ApprovalRequest(reviewer="  ", decision="approve"),
                    )

    @pytest.mark.asyncio
    async def test_get_prompt_query_returns_prompt_text(self) -> None:
        """get_prompt Query returns the prompt text before gate resolves."""
        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateInput,
            HumanGateWorkflow,
        )

        prompt_text = "Please review the SEO package for this article"

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate-query",
                workflows=[HumanGateWorkflow],
                activities=[],
            ):
                handle = await env.client.start_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt=prompt_text,
                        requester="flow",
                        timeout_hours=1,
                    ),
                    id="test-gate-query",
                    task_queue="test-gate-query",
                )

                queried_prompt = await handle.query(HumanGateWorkflow.get_prompt)

                # Resolve the gate so the worker can shut down cleanly
                await handle.execute_update(
                    HumanGateWorkflow.submit_decision,
                    ApprovalRequest(reviewer="Kelly", decision="approve"),
                )
                await handle.result()

        assert queried_prompt == prompt_text
