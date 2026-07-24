"""Unit test configuration.

With the Temporal testcontainer (docker-compose.test.yml), workflow
tests run against a real Temporal server instead of downloading a
binary that 404s in CI. The auto-xfail is removed.

Tests that need Temporal use the `temporal_endpoint` fixture which
starts the container. Tests that don't need it run as pure unit tests.
"""

import asyncio

import pytest

COMPOSE_PATH = None  # Set by tests that need it


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add asyncio markers to async tests if missing.

    With asyncio_mode=auto, pytest-asyncio should handle this,
    but some versions need explicit markers.
    """
    for item in items:
        if asyncio.iscoroutinefunction(getattr(item, "function", None)):
            if not any(m.name == "asyncio" for m in item.iter_markers()):
                item.add_marker(pytest.mark.asyncio)
