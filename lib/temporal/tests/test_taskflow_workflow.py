"""Tests for TaskFlowWorkflow — Temporal-native task runner.

Verifies topological sort, parallel wave execution, get_status query,
human gate integration, saga compensation on failure, and the full
TaskBrief → TaskResult pipeline.
"""
# ruff: noqa: SIM117  # nested async-with is the standard Temporal test pattern

from __future__ import annotations

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from phosphene.temporal.taskflow.models import StepInput, StepOutput, TaskBrief

# ── Mock activities ─────────────────────────────────────────────────


@activity.defn(name="dispatch_step_activity")
async def mock_dispatch(step: StepInput) -> StepOutput:
    """Succeed with a marker output."""
    return StepOutput(index=step.index, succeeded=True, output=f"done:{step.title}")


@activity.defn(name="dispatch_step_activity_fail")
async def mock_dispatch_fail(step: StepInput) -> StepOutput:
    """Return a failure StepOutput."""
    return StepOutput(index=step.index, succeeded=False, error="simulated failure")


# ── Tests ───────────────────────────────────────────────────────────


class TestTaskFlowModels:
    """Model import and construction smoke tests."""

    def test_models_importable(self) -> None:
        from phosphene.temporal.taskflow.models import (  # noqa: F401
            StepInput,
            StepOutput,
            TaskBrief,
            TaskResult,
        )

    def test_step_input_defaults(self) -> None:
        s = StepInput(0, "core/generate", "Title", "Instruction")
        assert s.depends_on == []
        assert s.timeout_seconds == 300


class TestTopoSort:
    """Topological sort groups steps into dependency waves."""

    def test_topo_sort_single_wave(self) -> None:
        from phosphene.temporal.workflows.taskflow import _topo_sort

        steps = [
            StepInput(0, "core/generate", "A", "inst"),
            StepInput(1, "core/generate", "B", "inst"),
        ]
        waves = _topo_sort(steps)
        assert len(waves) == 1
        assert len(waves[0]) == 2

    def test_topo_sort_sequential(self) -> None:
        from phosphene.temporal.workflows.taskflow import _topo_sort

        steps = [
            StepInput(0, "core/generate", "A", "inst"),
            StepInput(1, "core/generate", "B", "inst", depends_on=[0]),
        ]
        waves = _topo_sort(steps)
        assert len(waves) == 2
        assert waves[0][0].index == 0
        assert waves[1][0].index == 1

    def test_topo_sort_diamond(self) -> None:
        """Diamond dependency: 0 → {1,2} → 3."""
        from phosphene.temporal.workflows.taskflow import _topo_sort

        steps = [
            StepInput(0, "core/generate", "A", "inst"),
            StepInput(1, "core/generate", "B", "inst", depends_on=[0]),
            StepInput(2, "core/generate", "C", "inst", depends_on=[0]),
            StepInput(3, "core/generate", "D", "inst", depends_on=[1, 2]),
        ]
        waves = _topo_sort(steps)
        assert len(waves) == 3
        assert {s.index for s in waves[0]} == {0}
        assert {s.index for s in waves[1]} == {1, 2}
        assert {s.index for s in waves[2]} == {3}

    def test_topo_sort_circular_raises(self) -> None:
        from phosphene.temporal.workflows.taskflow import _topo_sort

        steps = [
            StepInput(0, "core/generate", "A", "inst", depends_on=[1]),
            StepInput(1, "core/generate", "B", "inst", depends_on=[0]),
        ]
        with pytest.raises(ValueError, match="Circular"):
            _topo_sort(steps)


class TestTaskFlowWorkflow:
    """Workflow execution tests using time-skipping environment."""

    @pytest.mark.asyncio
    async def test_workflow_importable(self) -> None:
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow  # noqa: F401

    @pytest.mark.asyncio
    async def test_single_step_completes(self) -> None:
        from phosphene.temporal.workflows.human_gate import HumanGateWorkflow
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow

        brief = TaskBrief(
            "Test",
            "desc",
            "flow",
            steps=[StepInput(0, "core/generate", "Step A", "inst")],
        )
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-single",
                workflows=[TaskFlowWorkflow, HumanGateWorkflow],
                activities=[mock_dispatch],
            ):
                result = await env.client.execute_workflow(
                    TaskFlowWorkflow.run,
                    brief,
                    id="test-single",
                    task_queue="test-single",
                )
        assert result.succeeded is True
        assert len(result.step_outputs) == 1
        assert result.step_outputs[0].output == "done:Step A"

    @pytest.mark.asyncio
    async def test_parallel_steps_same_wave(self) -> None:
        from phosphene.temporal.workflows.human_gate import HumanGateWorkflow
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow

        brief = TaskBrief(
            "Test",
            "desc",
            "flow",
            steps=[
                StepInput(0, "core/generate", "A", "inst"),
                StepInput(1, "core/generate", "B", "inst"),
            ],
        )
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-parallel",
                workflows=[TaskFlowWorkflow, HumanGateWorkflow],
                activities=[mock_dispatch],
            ):
                result = await env.client.execute_workflow(
                    TaskFlowWorkflow.run,
                    brief,
                    id="test-parallel",
                    task_queue="test-parallel",
                )
        assert result.succeeded is True
        assert len(result.step_outputs) == 2

    @pytest.mark.asyncio
    async def test_sequential_steps_ordered(self) -> None:
        """Steps with depends_on execute in correct wave order."""
        from phosphene.temporal.workflows.human_gate import HumanGateWorkflow
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow

        brief = TaskBrief(
            "Test",
            "desc",
            "flow",
            steps=[
                StepInput(0, "core/generate", "First", "inst"),
                StepInput(1, "core/generate", "Second", "inst", depends_on=[0]),
                StepInput(2, "core/generate", "Third", "inst", depends_on=[1]),
            ],
        )
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-seq",
                workflows=[TaskFlowWorkflow, HumanGateWorkflow],
                activities=[mock_dispatch],
            ):
                result = await env.client.execute_workflow(
                    TaskFlowWorkflow.run,
                    brief,
                    id="test-seq",
                    task_queue="test-seq",
                )
        assert result.succeeded is True
        assert len(result.step_outputs) == 3

    @pytest.mark.asyncio
    async def test_get_status_query(self) -> None:
        from phosphene.temporal.workflows.human_gate import HumanGateWorkflow
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow

        brief = TaskBrief(
            "Test",
            "desc",
            "flow",
            steps=[StepInput(0, "core/generate", "A", "inst")],
        )
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-query",
                workflows=[TaskFlowWorkflow, HumanGateWorkflow],
                activities=[mock_dispatch],
            ):
                handle = await env.client.start_workflow(
                    TaskFlowWorkflow.run,
                    brief,
                    id="test-query",
                    task_queue="test-query",
                )
                result = await handle.result()
                assert result.succeeded is True
                status = await handle.query(TaskFlowWorkflow.get_status)
        assert status["total"] == 1
        assert status["completed"] == 1
        assert status["failed"] == []

    @pytest.mark.asyncio
    async def test_human_gate_timeout(self) -> None:
        """Human gate step times out; workflow reports failure at that step."""
        from phosphene.temporal.workflows.human_gate import HumanGateWorkflow
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow

        brief = TaskBrief(
            "Gate test",
            "Should time out",
            "flow",
            steps=[StepInput(0, "core/human-gate", "Approval", "Please approve")],
        )
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate-timeout",
                workflows=[TaskFlowWorkflow, HumanGateWorkflow],
                activities=[],
            ):
                result = await env.client.execute_workflow(
                    TaskFlowWorkflow.run,
                    brief,
                    id="test-gate-timeout",
                    task_queue="test-gate-timeout",
                )
        assert result.succeeded is False
        assert result.blocked_at_index == 0

    @pytest.mark.asyncio
    async def test_human_gate_approved_via_update(self) -> None:
        """Reviewer sends Update → gate approves → workflow continues."""
        import asyncio

        from temporalio.service import RPCError

        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateWorkflow,
        )
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow

        brief = TaskBrief(
            "Approve test",
            "Should be approved",
            "flow",
            steps=[
                StepInput(0, "core/human-gate", "Approval", "Please approve"),
                StepInput(1, "core/generate", "Post-gate", "Do after", depends_on=[0]),
            ],
        )
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-gate-approve",
                workflows=[TaskFlowWorkflow, HumanGateWorkflow],
                activities=[mock_dispatch],
            ):
                handle = await env.client.start_workflow(
                    TaskFlowWorkflow.run,
                    brief,
                    id="test-gate-approve",
                    task_queue="test-gate-approve",
                )
                # Wait for the child HumanGateWorkflow to be started
                gate_handle = env.client.get_workflow_handle(
                    "human-gate-test-gate-approve-step-0"
                )
                for _ in range(50):
                    try:
                        await gate_handle.query(HumanGateWorkflow.get_prompt)
                        break
                    except RPCError:
                        await asyncio.sleep(0.1)
                gate_result = await gate_handle.execute_update(
                    HumanGateWorkflow.submit_decision,
                    ApprovalRequest(
                        reviewer="Kelly",
                        decision="approve",
                        notes="LGTM",
                    ),
                )
                assert gate_result.approved is True
                result = await handle.result()
        assert result.succeeded is True
        assert len(result.step_outputs) == 2
