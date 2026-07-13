"""Step definitions for integration_guard.feature.

Covers DryRunGuard scenarios: production writes blocked,
test clients pass.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import sys
from pathlib import Path

from behave import given, then, when

# Make the integration package importable from BDD steps
_integration_dir = str(
    Path(__file__).parent.parent.parent / "tests" / "integration"
)
if _integration_dir not in sys.path:
    sys.path.insert(0, _integration_dir)

from guard import DryRunGuard, ProductionWriteBlocked  # noqa: E402


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given("a DryRunGuard instance without test flag")
def step_guard_no_flag(context) -> None:
    """Create a DryRunGuard where _IS_TEST_CLIENT is False (the default)."""
    context.guard = DryRunGuard()
    context.exception_raised = None


@given("a DryRunGuard subclass with _IS_TEST_CLIENT True")
def step_guard_with_flag(context) -> None:
    """Create a DryRunGuard subclass that has _IS_TEST_CLIENT = True."""

    class TestClient(DryRunGuard):
        _IS_TEST_CLIENT = True

    context.guard = TestClient()
    context.exception_raised = None


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when("a guarded write is attempted")
def step_attempt_guarded_write(context) -> None:
    """Call _check_guard() on the guard instance and capture any exception."""
    try:
        context.guard._check_guard()
        context.exception_raised = None
    except ProductionWriteBlocked as exc:
        context.exception_raised = exc


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("ProductionWriteBlocked is raised")
def step_assert_blocked(context) -> None:
    """Assert that ProductionWriteBlocked was raised."""
    assert context.exception_raised is not None, (
        "Expected ProductionWriteBlocked to be raised, but no exception occurred"
    )
    assert isinstance(context.exception_raised, ProductionWriteBlocked), (
        f"Expected ProductionWriteBlocked, got {type(context.exception_raised)}"
    )


@then("no exception is raised")
def step_assert_not_blocked(context) -> None:
    """Assert that no exception was raised."""
    assert context.exception_raised is None, (
        f"Expected no exception, but got: {context.exception_raised}"
    )
