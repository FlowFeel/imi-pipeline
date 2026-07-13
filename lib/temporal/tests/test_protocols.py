"""Tests for phosphene.temporal.protocols.

Verifies that AsyncStepExecutorInterface is a runtime-checkable Protocol,
that SyncAdapter correctly delegates sync calls to an async implementation,
and that the adapter is safe to use outside a running event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestAsyncStepExecutorInterface:
    """AsyncStepExecutorInterface is a runtime-checkable Protocol."""

    def test_interface_is_importable(self) -> None:
        """Protocol can be imported from phosphene.temporal.protocols."""
        from phosphene.temporal.protocols import (
            AsyncStepExecutorInterface,  # noqa: F401
        )

    def test_concrete_class_satisfies_protocol(self) -> None:
        """A class implementing all async methods satisfies the protocol."""
        from phosphene.temporal.protocols import AsyncStepExecutorInterface

        class ConcreteExecutor:
            async def mark_active(self, manifest: Any, index: int) -> Any:
                return manifest

            async def complete_step(
                self,
                manifest: Any,
                index: int,
                output_paths: list[str] | None = None,
                output_metadata: dict[str, Any] | None = None,
            ) -> Any:
                return manifest

            async def fail_step(self, manifest: Any, index: int, error: str) -> Any:
                return manifest

            async def skip_step(self, manifest: Any, index: int, reason: str) -> Any:
                return manifest

            async def save_manifest(self, manifest: Any) -> None:
                pass

            async def load_manifest(self) -> Any:
                return MagicMock()

            async def recover_active_steps(self, manifest: Any) -> Any:
                return manifest

        assert isinstance(ConcreteExecutor(), AsyncStepExecutorInterface)

    def test_sync_class_structural_check_note(self) -> None:
        """Python runtime_checkable cannot distinguish sync vs async at isinstance time.

        This is a known Python limitation: ``isinstance()`` with a Protocol checks
        for method *presence*, not whether the method is a coroutine. A sync class
        with all the right method names satisfies the structural check even though
        the methods are not async.

        The distinction matters at call time — awaiting a sync method raises
        ``TypeError: object NoneType can't be used in 'await' expression``.
        Static type checkers (pyright, mypy) DO catch this correctly.

        This test documents the limitation rather than asserting incorrect behaviour.
        """
        from phosphene.temporal.protocols import AsyncStepExecutorInterface

        class SyncExecutor:
            """Sync executor — structurally matches protocol but methods are not async."""

            def mark_active(self, manifest: Any, index: int) -> Any:
                """Sync mark_active."""
                return manifest

            def complete_step(self, manifest: Any, index: int, **kwargs: Any) -> Any:
                """Sync complete_step."""
                return manifest

            def fail_step(self, manifest: Any, index: int, error: str) -> Any:
                """Sync fail_step."""
                return manifest

            def skip_step(self, manifest: Any, index: int, reason: str) -> Any:
                """Sync skip_step."""
                return manifest

            def save_manifest(self, manifest: Any) -> None:
                """Sync save_manifest."""

            def load_manifest(self) -> Any:
                """Sync load_manifest."""
                return MagicMock()

            def recover_active_steps(self, manifest: Any) -> Any:
                """Sync recover_active_steps."""
                return manifest

        # isinstance() passes at runtime — Python structural check cannot see async
        # The distinction is enforced by static type checkers, not isinstance()
        assert isinstance(
            SyncExecutor(), AsyncStepExecutorInterface
        )  # known limitation


class TestSyncAdapter:
    """SyncAdapter delegates sync calls to an async implementation."""

    def test_sync_adapter_is_importable(self) -> None:
        """SyncAdapter can be imported from phosphene.temporal.adapters."""
        from phosphene.temporal.adapters import SyncAdapter  # noqa: F401

    def test_mark_active_delegates_to_async(self) -> None:
        """SyncAdapter.mark_active calls async mark_active and returns result."""
        from phosphene.temporal.adapters import SyncAdapter

        sentinel = object()
        async_exec = AsyncMock()
        async_exec.mark_active.return_value = sentinel

        adapter = SyncAdapter(async_exec)
        result = adapter.mark_active(MagicMock(), 0)

        assert result is sentinel
        async_exec.mark_active.assert_called_once()

    def test_complete_step_delegates_to_async(self) -> None:
        """SyncAdapter.complete_step delegates with output_paths and metadata."""
        from phosphene.temporal.adapters import SyncAdapter

        sentinel = object()
        async_exec = AsyncMock()
        async_exec.complete_step.return_value = sentinel

        adapter = SyncAdapter(async_exec)
        result = adapter.complete_step(
            MagicMock(),
            0,
            output_paths=["out.md"],
            output_metadata={"k": "v"},
        )

        assert result is sentinel
        async_exec.complete_step.assert_called_once()

    def test_fail_step_delegates_to_async(self) -> None:
        """SyncAdapter.fail_step delegates error message."""
        from phosphene.temporal.adapters import SyncAdapter

        sentinel = object()
        async_exec = AsyncMock()
        async_exec.fail_step.return_value = sentinel

        adapter = SyncAdapter(async_exec)
        result = adapter.fail_step(MagicMock(), 0, error="timeout")

        assert result is sentinel
        async_exec.fail_step.assert_called_once()

    def test_save_manifest_delegates_to_async(self) -> None:
        """SyncAdapter.save_manifest delegates and returns None."""
        from phosphene.temporal.adapters import SyncAdapter

        async_exec = AsyncMock()
        async_exec.save_manifest.return_value = None

        adapter = SyncAdapter(async_exec)
        result = adapter.save_manifest(MagicMock())

        assert result is None
        async_exec.save_manifest.assert_called_once()

    def test_adapter_raises_if_event_loop_already_running(self) -> None:
        """SyncAdapter raises RuntimeError if called inside a running event loop."""
        from phosphene.temporal.adapters import SyncAdapter

        async_exec = AsyncMock()
        adapter = SyncAdapter(async_exec)

        async def _inner() -> None:
            """Try to use SyncAdapter inside a running loop."""
            with pytest.raises(RuntimeError, match="event loop"):
                adapter.mark_active(MagicMock(), 0)

        asyncio.run(_inner())
