"""Shared pytest fixtures for phosphene.temporal test suites.

Import these fixtures in conftest.py files across any package that uses
Temporal in tests. The session-scoped ``temporal_env`` fixture starts
one time-skipping Temporal test server for the entire test session,
amortising the ~0.3s startup cost across all tests.

Usage in conftest.py::

    from phosphene.temporal.testing.fixtures import temporal_env, worker_factory
    __all__ = ["temporal_env", "worker_factory"]
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


@pytest.fixture(scope="session")
async def temporal_env() -> Generator[WorkflowEnvironment, None, None]:
    """Session-scoped time-skipping Temporal test environment.

    Starts one Temporal test server for the entire pytest session.
    Time advances automatically past sleeps and timers (``start_time_skipping``).
    Use for: human gate timeout tests, retry backoff, any test with
    ``asyncio.sleep`` or ``wait_condition``.

    For integration tests that need real timing, use
    ``WorkflowEnvironment.start_local()`` directly in the test.

    Yields:
        Running ``WorkflowEnvironment`` instance.
    """
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


@pytest.fixture
def worker_factory(temporal_env: WorkflowEnvironment):  # noqa: ANN201
    """Factory for spinning up test workers against the session environment.

    Returns a callable that creates a ``Worker`` context manager.
    Workers are not started automatically — use as an async context manager.

    Args:
        temporal_env: Session-scoped WorkflowEnvironment fixture.

    Returns:
        Callable that accepts ``workflows``, ``activities``, and optional
        ``task_queue`` and returns a ``Worker`` context manager.

    Usage::

        async with worker_factory(
            workflows=[MySagaWorkflow],
            activities=[mock_activity],
            task_queue="test-queue",
        ) as worker:
            result = await temporal_env.client.execute_workflow(...)
    """

    class _Factory:
        """Inner factory class for worker creation."""

        def __call__(
            self,
            workflows: list,
            activities: list,
            task_queue: str = "test",
        ) -> Worker:
            """Create a Worker for the given workflows and activities.

            Args:
                workflows: List of workflow classes to register.
                activities: List of activity functions to register.
                task_queue: Task queue name for this worker.

            Returns:
                Configured ``Worker`` instance (use as async context manager).
            """
            return Worker(
                temporal_env.client,
                task_queue=task_queue,
                workflows=workflows,
                activities=activities,
            )

    return _Factory()
