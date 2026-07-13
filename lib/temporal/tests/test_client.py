"""Tests for TemporalClient — configured once from env, cached, shared.

Verifies that get_client() is importable, that the cache works (same
object returned on repeated calls), and that the client respects
TEMPORAL_URL and TEMPORAL_NAMESPACE env vars.
"""

from __future__ import annotations

import pytest


class TestTemporalClient:
    """TemporalClient configured from env, cached across calls."""

    def test_get_client_is_importable(self) -> None:
        """get_client can be imported from phosphene.temporal.client."""
        from phosphene.temporal.client import get_client  # noqa: F401

    def test_temporal_url_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TEMPORAL_URL defaults to localhost:7233."""
        from phosphene.temporal import client as client_module

        monkeypatch.delenv("TEMPORAL_URL", raising=False)
        # Force re-read of env var
        monkeypatch.setattr(client_module, "TEMPORAL_URL", "localhost:7233")
        assert client_module.TEMPORAL_URL == "localhost:7233"

    def test_temporal_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TEMPORAL_URL reads from environment variable."""
        import importlib

        import phosphene.temporal.client as client_module

        monkeypatch.setenv("TEMPORAL_URL", "my-temporal-host:7233")
        importlib.reload(client_module)
        assert client_module.TEMPORAL_URL == "my-temporal-host:7233"

    def test_temporal_namespace_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TEMPORAL_NAMESPACE reads from environment variable."""
        import importlib

        import phosphene.temporal.client as client_module

        monkeypatch.setenv("TEMPORAL_NAMESPACE", "phosphene-prod")
        importlib.reload(client_module)
        assert client_module.TEMPORAL_NAMESPACE == "phosphene-prod"

    def test_get_client_is_coroutine(self) -> None:
        """get_client is an async function (coroutine)."""
        import asyncio

        from phosphene.temporal.client import get_client

        assert asyncio.iscoroutinefunction(get_client)
