"""BaseSagaWorkflow — distributed state obligations paired with their inversions.

A distributed transaction that succeeds partially is worse than one that
fails entirely. Partial success leaves external systems in inconsistent
states that are invisible to the orchestrator — WordPress published,
Salesforce failed, the WordPress post exists with no Salesforce record,
and nothing in the system knows this is wrong.

The compensation list is the structural answer: every write to an
external system registers its reversal at the moment of success, not at
the moment of failure. Failure then has a complete map of what must be
undone, in the order it must be undone — the last success is the first
reversal. This is not error handling. It is the expression of a
principle: distributed state obligations are paired with their
inversions at the point they are incurred.

LIFO discharge order is the only ordering that preserves referential
consistency. Step 2 may reference artifacts created by step 1. Reversing
step 1 first orphans step 2's references. Reversing step 2 first removes
the dependent artifacts before removing what they depend on. The ordering
is not arbitrary; it follows from the causal structure of the forward
sequence.

The empty compensation list is the base case. Zero forward steps
completed means zero obligations incurred. Iterating an empty reversed
list yields nothing. No guard clause, no special branch.

Compensation failures are isolated from the original error. A failed
compensation is a secondary condition — recorded in the outcomes list,
logged at CRITICAL for manual intervention. The original workflow error
always propagates to the caller. Masking the root cause with a cleanup
failure makes diagnosis harder, not easier.

The coupling between ``BaseSagaWorkflow`` and Temporal is that Temporal's
durable execution guarantees the compensation list survives process death.
Without durable execution, a crash between step 2 and step 3 would
orphan the compensations. With it, the workflow resumes and completes
the compensation sequence.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from temporalio import workflow


class BaseSagaWorkflow:
    """The obligation register for distributed write sequences.

    The compensation list pairs each forward write with its inversion.
    ``_append_compensation()`` registers the inversion at the moment the
    forward step succeeds. ``_execute_compensations()`` discharges the
    register in LIFO order on failure. The subclass decides what to
    write and what the inversions are. The base class holds the register,
    enforces the ordering, and isolates compensation failures from the
    original error.

    The specific failure mode this prevents: partial success across
    causally linked external systems, where each system is individually
    consistent but the cross-system state is not. The compensation list
    makes the cross-system state recoverable by construction.

    Usage::

        @workflow.defn
        class MySagaWorkflow(BaseSagaWorkflow):
            @workflow.run
            async def run(self, input: MyInput) -> MyResult:
                result_a = await workflow.execute_activity(step_a, ...)
                self._append_compensation(
                    lambda: workflow.execute_activity(rollback_a, result_a, ...)
                )
                result_b = await workflow.execute_activity(step_b, ...)
                self._append_compensation(
                    lambda: workflow.execute_activity(rollback_b, result_b, ...)
                )
                # On failure, rollback_b fires first, then rollback_a.
    """

    def __init__(self) -> None:
        """Initialise the empty compensation list."""
        self._compensations: list[Callable[[], Coroutine[Any, Any, None]]] = []

    def _append_compensation(
        self, rollback: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """Register a rollback coroutine for the most recent forward step.

        Args:
            rollback: A zero-argument async callable that reverses the
                most recently completed forward step.
        """
        self._compensations.append(rollback)

    async def _execute_compensations(self) -> list[str]:
        """Execute all registered compensations in reverse order.

        Compensations run in LIFO order — the last forward step that
        succeeded is the first to be rolled back.

        Compensation failures are caught, logged, and recorded in the
        returned outcome list. They never re-raise — the original
        workflow error is always reported to the caller.

        Returns:
            List of outcome strings, one per compensation:
            ``"ok"`` on success, ``"failed:{error}"`` on failure.
        """
        outcomes: list[str] = []
        for rollback in reversed(self._compensations):
            try:
                await rollback()
                outcomes.append("ok")
            except Exception as exc:
                workflow.logger.critical(
                    f"Compensation failed — manual intervention may be required: {exc}"
                )
                outcomes.append(f"failed:{exc}")
        return outcomes
