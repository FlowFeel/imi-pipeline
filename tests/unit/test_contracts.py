"""Tests for PublishContract — the publish pipeline proof layer.

Pure tests. ContractResult and ContractReport are tested without
network calls. HTTP behaviour is tested via mocking in integration tests.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.contracts.publish import ContractReport, ContractResult


class TestContractResult:
    """Tests for ContractResult data structure."""

    def test_passing_result(self) -> None:
        """A passing result reports passed=True."""
        r = ContractResult(
            name="article is accessible",
            passed=True,
            evidence=200,
            expected=200,
        )
        assert r.passed is True

    def test_failing_result(self) -> None:
        """A failing result reports passed=False."""
        r = ContractResult(
            name="article is accessible",
            passed=False,
            evidence=404,
            expected=200,
        )
        assert r.passed is False


class TestContractReport:
    """Tests for ContractReport aggregation."""

    def test_all_passed_when_all_results_pass(self) -> None:
        """all_passed is True only when every result passes."""
        report = ContractReport(
            results=[
                ContractResult("a", True, 200, 200),
                ContractResult("b", True, 200, 200),
            ]
        )
        assert report.all_passed is True

    def test_not_all_passed_when_any_fails(self) -> None:
        """all_passed is False when any result fails."""
        report = ContractReport(
            results=[
                ContractResult("a", True, 200, 200),
                ContractResult("b", False, 404, 200),
            ]
        )
        assert report.all_passed is False

    def test_failed_returns_only_failing(self) -> None:
        """failed() returns only the results that did not pass."""
        report = ContractReport(
            results=[
                ContractResult("a", True, 200, 200),
                ContractResult("b", False, 404, 200),
            ]
        )
        assert len(report.failed()) == 1
        assert report.failed()[0].name == "b"
