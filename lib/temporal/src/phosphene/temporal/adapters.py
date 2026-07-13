"""SyncAdapter — Phase 1 bridge between sync callers and async executors.

Sync and async are mutually exclusive execution contexts. A sync caller
cannot ``await``; an async caller cannot block. ``SyncAdapter`` wraps
the async ``AsyncStepExecutorInterface`` behind a synchronous calling
convention, so existing sync callers (``bridge.py``, ``runners.py``,
``session.py``) can use a Temporal-backed executor without rewriting
their call sites.

The bridge works by creating a new event loop per call via
``asyncio.run()``. This is safe exactly when no loop is already running.
Inside a running loop, the outer loop is blocked waiting for the sync
call, and the sync call needs the loop to run its coroutine — deadlock.
The adapter detects this and raises ``RuntimeError`` immediately. The
failure mode is specific: it is not "something might go wrong" but
"the calling thread's event loop cannot make progress while
``asyncio.run()`` holds it." Callers inside an async context use
``AsyncStepExecutorInterface`` directly.

This module is Phase 1 scaffolding. It enables gradual migration from
file-backed to Temporal-backed execution without breaking the 459 sync
tests. Phase 2 callers adopt the async interface directly. Phase 3
retires this module.
"""

from __future__ import annotations

import asyncio
from typing import Any

from phosphene.temporal.protocols import AsyncStepExecutorInterface


class SyncAdapter:
    """Wraps an async executor behind the sync calling convention.

    Each method delegates to the underlying async executor via
    ``asyncio.run()``, creating and destroying a new event loop per call.
    ``_run()`` checks for a running loop before dispatching and raises
    ``RuntimeError`` if one exists — the specific failure mode is
    deadlock: the running loop cannot make progress while
    ``asyncio.run()`` holds the thread.

    Phase 1 scaffolding. New callers should use
    ``AsyncStepExecutorInterface`` directly.

    Args:
        async_executor: An async executor implementing ``AsyncStepExecutorInterface``.
    """

    def __init__(self, async_executor: AsyncStepExecutorInterface) -> None:
        """Initialise the adapter with an async executor.

        Args:
            async_executor: Async executor to delegate to.
        """
        self._exec = async_executor

    def _run(self, coro: Any) -> Any:
        """Run a coroutine synchronously.

        Raises:
            RuntimeError: If called inside a running event loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            raise RuntimeError(
                "SyncAdapter cannot be used inside a running event loop. "
                "Use AsyncStepExecutorInterface directly in async contexts."
            )

        return asyncio.run(coro)

    def mark_active(self, manifest: Any, index: int) -> Any:
        """Mark step active — delegates to async executor.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to activate.

        Returns:
            Updated manifest.
        """
        return self._run(self._exec.mark_active(manifest, index))

    def complete_step(
        self,
        manifest: Any,
        index: int,
        output_paths: list[str] | None = None,
        output_metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Complete a step — delegates to async executor.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to complete.
            output_paths: Output file paths.
            output_metadata: Step execution metadata.

        Returns:
            Updated manifest.
        """
        return self._run(
            self._exec.complete_step(
                manifest,
                index,
                output_paths=output_paths,
                output_metadata=output_metadata,
            )
        )

    def fail_step(self, manifest: Any, index: int, error: str) -> Any:
        """Fail a step — delegates to async executor.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to fail.
            error: Error description.

        Returns:
            Updated manifest.
        """
        return self._run(self._exec.fail_step(manifest, index, error))

    def skip_step(self, manifest: Any, index: int, reason: str) -> Any:
        """Skip a step — delegates to async executor.

        Args:
            manifest: The current ``TaskManifest``.
            index: Step index to skip.
            reason: Skip reason.

        Returns:
            Updated manifest.
        """
        return self._run(self._exec.skip_step(manifest, index, reason))

    def save_manifest(self, manifest: Any) -> None:
        """Persist manifest — delegates to async executor.

        Args:
            manifest: The ``TaskManifest`` to persist.
        """
        self._run(self._exec.save_manifest(manifest))

    def load_manifest(self) -> Any:
        """Load manifest — delegates to async executor.

        Returns:
            The persisted ``TaskManifest``.
        """
        return self._run(self._exec.load_manifest())

    def recover_active_steps(self, manifest: Any) -> Any:
        """Recover stale active steps — delegates to async executor.

        Args:
            manifest: The current ``TaskManifest``.

        Returns:
            Updated manifest.
        """
        return self._run(self._exec.recover_active_steps(manifest))
