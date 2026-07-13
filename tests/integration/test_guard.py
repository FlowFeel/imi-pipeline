"""Tests for DryRunGuard — hard lock enforcement.

TDD: these tests define the expected interface before implementation.
Zero @patch. DI only.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest
from guard import DryRunGuard, ProductionWriteBlocked


class TestDryRunGuard:
    """DryRunGuard blocks production writes via _check_guard()."""

    def test_production_write_blocked(self) -> None:
        """Base DryRunGuard (not test client) raises ProductionWriteBlocked."""
        guard = DryRunGuard()
        # _IS_TEST_CLIENT defaults to False on the base class
        with pytest.raises(ProductionWriteBlocked):
            guard._check_guard()

    def test_test_client_passes(self) -> None:
        """Subclass with _IS_TEST_CLIENT = True passes the guard."""

        class TestClient(DryRunGuard):
            _IS_TEST_CLIENT = True

        client = TestClient()
        # Should not raise
        client._check_guard()

    def test_production_write_blocked_is_runtime_error(self) -> None:
        """ProductionWriteBlocked is a RuntimeError subclass."""
        assert issubclass(ProductionWriteBlocked, RuntimeError)

    def test_error_message_contains_class_name(self) -> None:
        """ProductionWriteBlocked message includes the class name."""

        class MyUnsafeClient(DryRunGuard):
            _IS_TEST_CLIENT = False

        client = MyUnsafeClient()
        with pytest.raises(ProductionWriteBlocked, match="MyUnsafeClient"):
            client._check_guard()

    def test_false_flag_blocked(self) -> None:
        """Explicitly setting _IS_TEST_CLIENT = False blocks the write."""

        class ExplicitFalseClient(DryRunGuard):
            _IS_TEST_CLIENT = False

        client = ExplicitFalseClient()
        with pytest.raises(ProductionWriteBlocked):
            client._check_guard()
