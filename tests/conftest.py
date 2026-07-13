"""Shared conftest for all IMI tests.

Registers custom pytest marks so they are recognised at collection time.
This conftest sits one level above integration/ and unit/ so the marks
are available across the full test suite without modifying pyproject.toml.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register IMI custom markers."""
    config.addinivalue_line(
        "markers",
        (
            "integration_live: Tier 3 live integration tests — requires "
            "IMI_INTEGRATION=true and real service credentials in env."
        ),
    )
