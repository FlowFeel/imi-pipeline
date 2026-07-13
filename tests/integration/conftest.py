"""Shared conftest for IMI integration tests.

Provides:
  - imi_integration marker: tests skip unless IMI_INTEGRATION=true in env.
  - Credential fixtures: each reads from env or skips with a clear message.
  - sys.path patch so guard, validators, fixtures can be imported directly.

Usage in tests::

    @pytest.mark.imi_integration
    def test_something(sf_consumer_key, wp_username):
        ...

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# sys.path — allow direct imports from the integration directory
# ---------------------------------------------------------------------------

_integration_dir = str(Path(__file__).parent)
if _integration_dir not in sys.path:
    sys.path.insert(0, _integration_dir)


# ---------------------------------------------------------------------------
# imi_integration marker — skip unless IMI_INTEGRATION=true
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register the imi_integration marker."""
    config.addinivalue_line(
        "markers",
        "imi_integration: mark test as requiring IMI_INTEGRATION=true in env",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip tests marked imi_integration unless IMI_INTEGRATION=true."""
    if os.environ.get("IMI_INTEGRATION", "").lower() not in {"true", "1", "yes"}:
        skip_mark = pytest.mark.skip(
            reason="Set IMI_INTEGRATION=true to run integration tests"
        )
        for item in items:
            if item.get_closest_marker("imi_integration"):
                item.add_marker(skip_mark)


# ---------------------------------------------------------------------------
# Credential fixtures — each returns the value or skips
# ---------------------------------------------------------------------------


def _env_or_skip(var: str) -> str:
    """Read an env var or skip the test with a clear message.

    Args:
        var: Environment variable name.

    Returns:
        The value of the env var.

    Raises:
        pytest.skip.Exception: If the env var is not set.
    """
    value = os.environ.get(var)
    if not value:
        pytest.skip(f"Missing {var}")
    return value


@pytest.fixture
def sf_consumer_key() -> str:
    """Salesforce OAuth consumer key."""
    return _env_or_skip("SF_CONSUMER_KEY")


@pytest.fixture
def sf_consumer_secret() -> str:
    """Salesforce OAuth consumer secret."""
    return _env_or_skip("SF_CONSUMER_SECRET")


@pytest.fixture
def wp_username() -> str:
    """WordPress application username."""
    return _env_or_skip("WP_USERNAME")


@pytest.fixture
def wp_app_password() -> str:
    """WordPress application password."""
    return _env_or_skip("WP_APP_PASSWORD")


@pytest.fixture
def mw_bot_username() -> str:
    """MediaWiki bot username."""
    return _env_or_skip("MW_BOT_USERNAME")


@pytest.fixture
def mw_bot_password() -> str:
    """MediaWiki bot password."""
    return _env_or_skip("MW_BOT_PASSWORD")
