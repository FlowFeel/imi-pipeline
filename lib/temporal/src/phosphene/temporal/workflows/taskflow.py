"""TaskFlowWorkflow — generic durable step engine replacing file-based TaskFlow.

Accepts a ``TaskBrief`` (title + list of ``StepInput``). Executes steps in
dependency order determined by topological sort. Steps within the same wave
(no mutual dependencies) run in parallel via ``asyncio.gather``. Human gate
steps become child ``HumanGateWorkflow`` instances. Failed steps trigger
saga compensation in reverse order via ``BaseSagaWorkflow``.

The topological sort is a module-level pure function (``_topo_sort``), not
a workflow method, because it must be testable without instantiating a
workflow. Temporal workflow classes run inside a replay sandbox — you
cannot call their methods directly in a unit test without starting the
workflow. A module-level function is importable and callable in any
test without Temporal infrastructure.

State is queryable at any time via ``get_status()`` — a ``@workflow.query``
handler. This replaces ``manifest.live_summary()`` and ``active-jobs.jsonl``
polling. Query reads workflow state without mutating history, so the board
renderer can ask "where are we?" at any moment without side effects.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from phosphene.temporal.taskflow.models import (
    StepInput,
    StepOutput,
    TaskBrief,
    TaskResult,
)
from phosphene.temporal.workflows.base import BaseSagaWorkflow

with workflow.unsafe.imports_passed_through():
    from phosphene.temporal.taskflow.activities import dispatch_step_activity
    from phosphene.temporal.workflows.human_gate import (
        HumanGateInput,
        HumanGateWorkflow,
    )


def _topo_sort(steps: list[StepInput]) -> list[list[StepInput]]:
    """Group steps into waves by dependency order.

    Returns a list of waves — steps in each wave can run in parallel.
    Wave 0 contains steps with no dependencies. Wave N depends only on
    steps in waves 0..N-1.

    Args:
        steps: All steps to sort.

    Returns:
        List of waves, each wave a list of ``StepInput``.

    Raises:
        ValueError: If dependencies are circular or unsatisfiable.
    """
    waves: list[list[StepInput]] = []
    completed: set[int] = set()
    remaining = list(steps)

    while remaining:
        wave = [s for s in remaining if all(d in completed for d in s.depends_on)]
        if not wave:
            raise ValueError(
                "Circular dependency or unsatisfiable depends_on in steps."
            )
        waves.append(wave)
        for s in wave:
            completed.add(s.index)
        remaining = [s for s in remaining if s not in wave]

    return waves


@workflow.defn
class TaskFlowWorkflow(BaseSagaWorkflow):
    """Generic durable step engine replacing phosphene.taskflow.

    Accepts a ``TaskBrief`` (title + list of ``StepInput``).
    Executes steps in dependency order via topological sort.
    Human gate steps become child ``HumanGateWorkflow`` instances.
    Failed steps trigger compensation in reverse order.

    State is queryable at any time via ``get_status()``.
    """

    def __init__(self) -> None:
        """Initialise step state tracking on top of saga compensation list."""
        super().__init__()
        self._step_states: dict[int, str] = {}
        self._step_outputs: dict[int, StepOutput] = {}

    @workflow.query
    def get_status(self) -> dict:
        """Polling board — returns current step states via Temporal Query.

        Why Query, not file polling: the old pattern read a manifest file
        from disk. The failure mode: stale reads during writes, race
        conditions between writer and reader, no cross-host visibility.
        Query reads the workflow's in-memory state directly — no file,
        no parsing, no staleness. It does not mutate history, so calling
        it has zero side effects on the running workflow.

        Returns:
            Dict with ``step_states``, ``completed`` count, ``total`` count,
            and ``failed`` indices list.
        """
        return {
            "step_states": dict(self._step_states),
            "completed": sum(1 for s in self._step_states.values() if s == "done"),
            "total": len(self._step_states),
            "failed": [i for i, s in self._step_states.items() if s == "failed"],
        }

    @workflow.run
    async def run(self, brief: TaskBrief) -> TaskResult:
        """Execute all steps in dependency order.

        Steps within the same topological wave run in parallel.
        On failure, saga compensations execute in reverse order.

        Args:
            brief: The task specification with steps.

        Returns:
            ``TaskResult`` with success/failure and collected outputs.
        """
        # Initialise state
        for step in brief.steps:
            self._step_states[step.index] = "pending"

        waves = _topo_sort(brief.steps)

        for wave in waves:
            tasks = [self._execute_step(step) for step in wave]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(wave, results, strict=True):
                if isinstance(result, BaseException):
                    self._step_states[step.index] = "failed"
                    await self._execute_compensations()
                    return TaskResult(
                        succeeded=False,
                        step_outputs=list(self._step_outputs.values()),
                        blocked_at_index=step.index,
                        error=str(result),
                    )
                if not result.succeeded:
                    self._step_states[step.index] = "failed"
                    self._step_outputs[step.index] = result
                    await self._execute_compensations()
                    return TaskResult(
                        succeeded=False,
                        step_outputs=list(self._step_outputs.values()),
                        blocked_at_index=step.index,
                        error=result.error,
                    )

        return TaskResult(
            succeeded=True,
            step_outputs=list(self._step_outputs.values()),
        )

    async def _execute_step(self, step: StepInput) -> StepOutput:
        """Dispatch a single step based on kind.

        Human gate steps become child ``HumanGateWorkflow`` workflows.
        All other kinds go through ``dispatch_step_activity``.

        Args:
            step: The step to execute.

        Returns:
            ``StepOutput`` with the result.
        """
        self._step_states[step.index] = "running"

        if step.kind == "core/human-gate":
            return await self._execute_human_gate(step)

        output = await workflow.execute_activity(
            dispatch_step_activity,
            step,
            start_to_close_timeout=timedelta(seconds=step.timeout_seconds),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        self._step_states[step.index] = "done" if output.succeeded else "failed"
        self._step_outputs[step.index] = output
        return output

    async def _execute_human_gate(self, step: StepInput) -> StepOutput:
        """Delegate to ``HumanGateWorkflow`` child workflow.

        Creates a child workflow with a deterministic ID based on
        the parent workflow ID and step index.

        Args:
            step: The human-gate step to execute.

        Returns:
            ``StepOutput`` reflecting the gate outcome.
        """
        gate_input = HumanGateInput(
            prompt=step.instruction,
            requester="flow",
            timeout_hours=48,
        )
        result = await workflow.execute_child_workflow(
            HumanGateWorkflow.run,
            gate_input,
            id=f"human-gate-{workflow.info().workflow_id}-step-{step.index}",
        )
        if result.timed_out or not result.approved:
            self._step_states[step.index] = "failed"
            output = StepOutput(
                index=step.index,
                succeeded=False,
                error="Human gate: rejected or timed out",
            )
        else:
            self._step_states[step.index] = "done"
            output = StepOutput(
                index=step.index,
                succeeded=True,
                output=f"Approved by {result.reviewer}: {result.notes}",
            )
        self._step_outputs[step.index] = output
        return output
