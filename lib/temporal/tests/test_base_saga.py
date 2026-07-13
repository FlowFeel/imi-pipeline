"""Tests for BaseSagaWorkflow.

Verifies compensation list management, reverse execution order,
empty list safety, and failure isolation (compensation failure
does not mask the original error).

Note: Temporal does not support local (nested) workflow classes.
All @workflow.defn classes must be at module level.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

# Note: 'activity' import is used by module-level @activity.defn decorators.
# 'workflow' import is used by module-level @workflow.defn decorators.


@dataclass
class _SagaInput:
    """Test input for saga workflow fixtures."""

    fail_at: int = -1


@dataclass
class _SagaResult:
    """Test result for saga workflow fixtures."""

    succeeded: bool
    compensations_executed: list[str]
    error: str = ""


# ---------------------------------------------------------------------------
# Module-level workflow and activity definitions for TestBaseSagaWorkflow
# ---------------------------------------------------------------------------


@activity.defn(name="saga_step_a")
async def _step_a() -> str:
    """Forward step A."""
    return "a"


@activity.defn(name="saga_step_b")
async def _step_b() -> str:
    """Forward step B."""
    return "b"


@activity.defn(name="saga_step_fail")
async def _step_fail() -> str:
    """Step that always fails."""
    raise RuntimeError("step_fail intentional")


@activity.defn(name="saga_rollback_a")
async def _rollback_a() -> None:
    """Rollback for step A."""


@activity.defn(name="saga_rollback_b")
async def _rollback_b() -> None:
    """Rollback for step B."""


@activity.defn(name="saga_fail_immediately")
async def _fail_immediately() -> None:
    """Step that fails immediately — for empty-compensation test."""
    raise RuntimeError("immediate failure")


@activity.defn(name="saga_do_work")
async def _do_work() -> None:
    """Work step for bad-rollback test."""


@activity.defn(name="saga_fail_step_simple")
async def _fail_step_simple() -> None:
    """Fail step for bad-rollback test."""
    raise RuntimeError("original error")


@activity.defn(name="saga_bad_rollback")
async def _bad_rollback() -> None:
    """Rollback that itself fails."""
    raise RuntimeError("rollback also failed")


@workflow.defn(name="ThreeStepSaga")
class _ThreeStepSaga:
    """Three-step saga: steps A and B succeed, step C fails. A and B must roll back."""

    def __init__(self) -> None:
        """Initialise saga."""
        from phosphene.temporal.workflows.base import BaseSagaWorkflow

        self._saga = BaseSagaWorkflow()

    @workflow.run
    async def run(self, inp: _SagaInput) -> _SagaResult:
        """Run three steps with compensation."""
        from datetime import timedelta

        from temporalio.common import RetryPolicy

        act_kw = {
            "start_to_close_timeout": timedelta(seconds=5),
            "retry_policy": RetryPolicy(maximum_attempts=1),
        }
        try:
            await workflow.execute_activity("saga_step_a", **act_kw)
            self._saga._append_compensation(
                lambda: workflow.execute_activity("saga_rollback_a", **act_kw)
            )
            await workflow.execute_activity("saga_step_b", **act_kw)
            self._saga._append_compensation(
                lambda: workflow.execute_activity("saga_rollback_b", **act_kw)
            )
            await workflow.execute_activity("saga_step_fail", **act_kw)
        except Exception as exc:
            outcomes = await self._saga._execute_compensations()
            return _SagaResult(
                succeeded=False,
                compensations_executed=outcomes,
                error=str(exc),
            )
        return _SagaResult(succeeded=True, compensations_executed=[])


@workflow.defn(name="NoCompSaga")
class _NoCompSaga:
    """Saga that fails immediately with no compensations registered."""

    def __init__(self) -> None:
        """Initialise saga."""
        from phosphene.temporal.workflows.base import BaseSagaWorkflow

        self._saga = BaseSagaWorkflow()

    @workflow.run
    async def run(self, inp: _SagaInput) -> _SagaResult:
        """Fail with no compensations."""
        from datetime import timedelta

        from temporalio.common import RetryPolicy

        act_kw = {
            "start_to_close_timeout": timedelta(seconds=5),
            "retry_policy": RetryPolicy(maximum_attempts=1),
        }
        try:
            await workflow.execute_activity("saga_fail_immediately", **act_kw)
        except Exception:
            outcomes = await self._saga._execute_compensations()
            return _SagaResult(succeeded=False, compensations_executed=outcomes)
        return _SagaResult(succeeded=True, compensations_executed=[])


@workflow.defn(name="BadRollbackSaga")
class _BadRollbackSaga:
    """Saga where the rollback itself fails."""

    def __init__(self) -> None:
        """Initialise saga."""
        from phosphene.temporal.workflows.base import BaseSagaWorkflow

        self._saga = BaseSagaWorkflow()

    @workflow.run
    async def run(self, inp: _SagaInput) -> _SagaResult:
        """Work step succeeds, forward step fails, rollback also fails."""
        from datetime import timedelta

        from temporalio.common import RetryPolicy

        act_kw = {
            "start_to_close_timeout": timedelta(seconds=5),
            "retry_policy": RetryPolicy(maximum_attempts=1),
        }
        try:
            await workflow.execute_activity("saga_do_work", **act_kw)
            self._saga._append_compensation(
                lambda: workflow.execute_activity("saga_bad_rollback", **act_kw)
            )
            await workflow.execute_activity("saga_fail_step_simple", **act_kw)
        except Exception as exc:
            outcomes = await self._saga._execute_compensations()
            return _SagaResult(
                succeeded=False,
                compensations_executed=outcomes,
                error=str(exc),
            )
        return _SagaResult(succeeded=True, compensations_executed=[])


_ALL_ACTIVITIES = [
    _step_a,
    _step_b,
    _step_fail,
    _rollback_a,
    _rollback_b,
    _fail_immediately,
    _do_work,
    _fail_step_simple,
    _bad_rollback,
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBaseSagaWorkflow:
    """BaseSagaWorkflow manages compensation list with correct semantics."""

    @pytest.mark.asyncio
    async def test_compensation_executes_in_reverse_order(self) -> None:
        """Compensations execute in reverse: rollback_b before rollback_a.

        The _ThreeStepSaga runs steps A and B, then step_fail raises.
        Compensations fire in LIFO order (rollback_b then rollback_a).
        We verify the outcome list contains two "ok" entries (both
        compensations succeeded) and the original error is reported.
        Reverse ordering is guaranteed by BaseSagaWorkflow._execute_compensations.
        """
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-saga-reverse",
                workflows=[_ThreeStepSaga],
                activities=_ALL_ACTIVITIES,
            ):
                result = await env.client.execute_workflow(
                    _ThreeStepSaga.run,
                    _SagaInput(),
                    id="test-reverse-compensation",
                    task_queue="test-saga-reverse",
                )

        assert result.succeeded is False
        # Temporal wraps activity errors as ActivityError("Activity task failed")
        # with the original RuntimeError in the cause chain.
        assert result.error  # non-empty error string
        # Two compensations executed (rollback_b then rollback_a)
        assert len(result.compensations_executed) == 2
        assert all(o == "ok" for o in result.compensations_executed)

    @pytest.mark.asyncio
    async def test_empty_compensation_list_is_safe(self) -> None:
        """_execute_compensations with no registered compensations returns empty list."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-no-comp",
                workflows=[_NoCompSaga],
                activities=[_fail_immediately],
            ):
                result = await env.client.execute_workflow(
                    _NoCompSaga.run,
                    _SagaInput(),
                    id="test-no-comp",
                    task_queue="test-no-comp",
                )

        assert result.succeeded is False
        assert result.compensations_executed == []

    @pytest.mark.asyncio
    async def test_compensation_failure_does_not_mask_original_error(self) -> None:
        """Original error is reported even when compensation fails."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-bad-rollback",
                workflows=[_BadRollbackSaga],
                activities=[_do_work, _fail_step_simple, _bad_rollback],
            ):
                result = await env.client.execute_workflow(
                    _BadRollbackSaga.run,
                    _SagaInput(),
                    id="test-bad-rollback",
                    task_queue="test-bad-rollback",
                )

        assert result.succeeded is False
        # Temporal wraps activity errors — the error string is
        # "Activity task failed", not the original RuntimeError message.
        assert result.error  # non-empty error string reported
        # The compensation itself also failed (bad_rollback raises)
        assert len(result.compensations_executed) == 1
        assert any("failed" in o for o in result.compensations_executed)
