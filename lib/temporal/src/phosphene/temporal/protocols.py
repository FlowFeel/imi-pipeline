"""Protocols for phosphene.temporal — two execution contracts, one migration path.

The sync ``StepExecutorInterface`` and the async
``AsyncStepExecutorInterface`` represent different models of step
execution. The sync interface expresses file-backed local execution:
state is written to disk, recovery reads the last-written manifest.
The async interface expresses Temporal-backed durable execution: state
lives in event history, recovery is replay. These are not implementation
variants of the same thing. They are distinct contracts for distinct
execution contexts, and both are valid simultaneously.

The migration path is gradual and non-breaking. The sync interface
preserves 459 existing tests and all current callers. The async
interface enables Temporal-native callers. ``SyncAdapter`` bridges the
two during the transition. The three phases:

1. ``TemporalStepExecutor`` implements async. Sync callers use
   ``SyncAdapter``.
2. Async-ready callers adopt the async interface directly.
3. ``SyncAdapter`` and the sync interface are retired when no sync
   callers remain.

``@runtime_checkable`` enables duck-type dispatch via ``isinstance()``.
The limitation: Python's Protocol ``__instancecheck__`` does not
distinguish ``def`` from ``async def``. A sync class with matching
method names passes the runtime check. This is a language-level
boundary — ``inspect.iscoroutinefunction`` is not consulted by
``__instancecheck__``. Static type checkers (pyright, mypy) do
distinguish them. The runtime check is useful for dispatch; static
analysis is the correctness gate.

This module has no dependency on ``phosphene.taskflow``. The protocol
shape uses ``Any`` so callers can pass ``TaskManifest`` objects without
creating a circular import. Type narrowing happens in the concrete
implementor (``TemporalStepExecutor``), which imports ``TaskManifest``
directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AsyncStepExecutorInterface(Protocol):
    """The async execution contract — state lives in Temporal event history.

    Mirrors the sync ``StepExecutorInterface`` exactly except every method
    is ``async def``. The shape is identical; only the calling convention
    differs. Migration is mechanical: swap the executor, add ``await``.
    No business logic changes, no new parameters, no reordering.

    Implementors: ``TemporalStepExecutor`` (``phosphene.taskflow.temporal``).
    Bridge for sync callers: ``SyncAdapter`` (``phosphene.temporal.adapters``).
    """

    async def mark_active(self, manifest: Any, index: int) -> Any:
        """Mark step ``index`` as ACTIVE and persist state.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to activate.

        Returns:
            Updated manifest with step in ACTIVE state.
        """
        ...

    async def complete_step(
        self,
        manifest: Any,
        index: int,
        output_paths: list[str] | None = None,
        output_metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Mark step ``index`` as COMPLETE and persist state.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to complete.
            output_paths: Paths of files produced by this step.
            output_metadata: Arbitrary metadata from step execution.

        Returns:
            Updated manifest with step in COMPLETE state.
        """
        ...

    async def fail_step(self, manifest: Any, index: int, error: str) -> Any:
        """Mark step ``index`` as FAILED and persist state.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to fail.
            error: Human-readable error description.

        Returns:
            Updated manifest with step in FAILED state.
        """
        ...

    async def skip_step(self, manifest: Any, index: int, reason: str) -> Any:
        """Mark step ``index`` as SKIPPED and persist state.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to skip.
            reason: Human-readable reason for skipping.

        Returns:
            Updated manifest with step in SKIPPED state.
        """
        ...

    async def save_manifest(self, manifest: Any) -> None:
        """Persist the manifest to durable storage.

        Args:
            manifest: The ``TaskManifest`` to persist.
        """
        ...

    async def load_manifest(self) -> Any:
        """Load the manifest from durable storage.

        Returns:
            The persisted ``TaskManifest``.
        """
        ...

    async def recover_active_steps(self, manifest: Any) -> Any:
        """Recover stale ACTIVE steps after process restart.

        For Temporal-backed executors this is a no-op — Temporal's
        replay mechanism handles recovery automatically. For local
        executors it resets orphaned ACTIVE steps to PENDING.

        Args:
            manifest: The current ``TaskManifest``.

        Returns:
            Updated manifest with stale ACTIVE steps reset.
        """
        ...
