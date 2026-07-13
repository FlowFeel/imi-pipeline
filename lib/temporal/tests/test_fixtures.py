"""Tests for phosphene.temporal.testing.fixtures.

Verifies that temporal_env and worker_factory are importable,
carry correct pytest fixture metadata, and that a worker built
via the pattern runs a real workflow to completion.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

# ---------------------------------------------------------------------------
# Minimal workflow + activity used only in this test module
# ---------------------------------------------------------------------------


@activity.defn(name="fixtures_echo")
async def _echo_activity() -> str:
    """Echo a fixed string — proves activities run through the worker."""
    return "echoed"


@dataclass
class _EchoInput:
    """Input dataclass for FixturesEchoWorkflow."""


@dataclass
class _EchoResult:
    """Result dataclass for FixturesEchoWorkflow."""

    value: str


@workflow.defn(name="FixturesEchoWorkflow")
class _FixturesEchoWorkflow:
    """Minimal workflow: runs one activity and returns its result."""

    @workflow.run
    async def run(self, inp: _EchoInput) -> _EchoResult:
        """Execute the echo activity.

        Args:
            inp: Unused input dataclass (required by environment serialisation).

        Returns:
            _EchoResult with the activity return value.
        """
        from datetime import timedelta

        from temporalio.common import RetryPolicy

        value = await workflow.execute_activity(
            "fixtures_echo",
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return _EchoResult(value=value)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFixturesModule:
    """phosphene.temporal.testing.fixtures exports the expected symbols."""

    def test_temporal_env_is_importable(self) -> None:
        """temporal_env can be imported from fixtures module."""
        from phosphene.temporal.testing.fixtures import temporal_env  # noqa: F401

    def test_worker_factory_is_importable(self) -> None:
        """worker_factory can be imported from fixtures module."""
        from phosphene.temporal.testing.fixtures import worker_factory  # noqa: F401

    def test_fixtures_are_pytest_fixture_definitions(self) -> None:
        """Both fixtures are wrapped as pytest FixtureFunctionDefinition instances."""
        from _pytest.fixtures import FixtureFunctionDefinition

        from phosphene.temporal.testing.fixtures import temporal_env, worker_factory

        # In pytest 9.x, @pytest.fixture produces FixtureFunctionDefinition
        assert isinstance(temporal_env, FixtureFunctionDefinition)
        assert isinstance(worker_factory, FixtureFunctionDefinition)
        # temporal_env must be session-scoped to amortise startup cost
        assert temporal_env._fixture_function_marker.scope == "session"  # type: ignore[attr-defined]


class TestFixturesWorkflow:
    """Worker pattern from fixtures module runs workflows correctly."""

    @pytest.mark.asyncio
    async def test_worker_runs_workflow_to_completion(self) -> None:
        """A Worker with registered activities executes a workflow correctly."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="fixtures-echo-queue",
                workflows=[_FixturesEchoWorkflow],
                activities=[_echo_activity],
            ):
                result = await env.client.execute_workflow(
                    _FixturesEchoWorkflow.run,
                    _EchoInput(),
                    id="fixtures-echo-workflow",
                    task_queue="fixtures-echo-queue",
                )

        assert result.value == "echoed"
