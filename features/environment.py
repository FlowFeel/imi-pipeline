"""Behave environment for phosphene-imi features.

Initialises shared context for all IMI pipeline scenarios.
Clears state before each scenario for isolation.

OKR: @okr_publish_pipeline
"""
from __future__ import annotations

import sys
from pathlib import Path


def before_all(context: object) -> None:
    """Bootstrap PYTHONPATH and shared configuration."""
    src = Path(__file__).resolve().parent.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    context.repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent  # type: ignore[attr-defined]


def before_scenario(context: object, scenario: object) -> None:  # noqa: ARG001
    """Isolate state between scenarios."""
    context.draft = None  # type: ignore[attr-defined]
    context.published_article = None  # type: ignore[attr-defined]
    context.publish_error = None  # type: ignore[attr-defined]
    context.contract_report = None  # type: ignore[attr-defined]
