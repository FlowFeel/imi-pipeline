"""Tests for PublicationEvent, OutletResult, PublicationReport.

Pure tests. No network. No filesystem. All types are InvariantStatic.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest

from phosphene.imi.draft import Draft
from phosphene.imi.event import OutletResult, PublicationEvent, PublicationReport


def make_draft(**kwargs: object) -> Draft:
    """Build a minimal valid Draft for testing."""
    defaults = {
        "title": "Test Article",
        "body": "Article body content.",
        "author": "Test Author",
        "category": "Economy",
    }
    defaults.update(kwargs)  # type: ignore[arg-type]
    return Draft(**defaults)  # type: ignore[arg-type]


class TestPublicationEvent:
    """Tests for PublicationEvent construction."""

    def test_event_constructs_with_draft(self) -> None:
        """A valid event constructs from a Draft."""
        event = PublicationEvent(draft=make_draft(), publisher_id="jan")
        assert event.draft.title == "Test Article"
        assert event.publisher_id == "jan"

    def test_timestamp_defaults_to_now(self) -> None:
        """Timestamp is set automatically if not provided."""
        event = PublicationEvent(draft=make_draft(), publisher_id="jan")
        assert event.timestamp is not None

    def test_idempotency_key_derived_from_title(self) -> None:
        """Idempotency key is slugified title by default."""
        event = PublicationEvent(draft=make_draft(), publisher_id="jan")
        assert event.idempotency_key == "test-article"

    def test_event_is_immutable(self) -> None:
        """PublicationEvent is frozen — mutation raises."""
        event = PublicationEvent(draft=make_draft(), publisher_id="jan")
        with pytest.raises(Exception):
            event.publisher_id = "other"  # type: ignore[misc]


class TestOutletResult:
    """Tests for OutletResult."""

    def test_successful_result(self) -> None:
        """A successful result carries the artifact."""
        r = OutletResult(
            outlet="observatory",
            succeeded=True,
            artifact="https://observatory.wiki/Test_Article",
        )
        assert r.succeeded is True
        assert r.artifact == "https://observatory.wiki/Test_Article"

    def test_failed_result_carries_error(self) -> None:
        """A failed result carries the error message."""
        r = OutletResult(
            outlet="salesforce",
            succeeded=False,
            error="HTTP 401: Unauthorized",
        )
        assert r.succeeded is False
        assert r.error == "HTTP 401: Unauthorized"
        assert r.artifact is None


class TestPublicationReport:
    """Tests for PublicationReport aggregation."""

    def make_event(self) -> PublicationEvent:
        """Build a minimal event for testing."""
        return PublicationEvent(draft=make_draft(), publisher_id="jan")

    def test_all_succeeded_when_all_pass(self) -> None:
        """all_succeeded is True only when all outlets succeeded."""
        report = PublicationReport(
            event=self.make_event(),
            results=[
                OutletResult(
                    outlet="observatory", succeeded=True, artifact="https://obs.wiki/A"
                ),
                OutletResult(outlet="salesforce", succeeded=True, artifact="SF-001"),
            ],
        )
        assert report.all_succeeded is True

    def test_not_all_succeeded_when_any_fails(self) -> None:
        """all_succeeded is False when any outlet fails."""
        report = PublicationReport(
            event=self.make_event(),
            results=[
                OutletResult(
                    outlet="observatory", succeeded=True, artifact="https://obs.wiki/A"
                ),
                OutletResult(outlet="salesforce", succeeded=False, error="timeout"),
            ],
        )
        assert report.all_succeeded is False

    def test_observatory_url_extracted(self) -> None:
        """observatory_url returns the artifact from the observatory outlet."""
        report = PublicationReport(
            event=self.make_event(),
            results=[
                OutletResult(
                    outlet="observatory", succeeded=True, artifact="https://obs.wiki/A"
                ),
            ],
        )
        assert report.observatory_url == "https://obs.wiki/A"

    def test_observatory_url_none_when_not_published(self) -> None:
        """observatory_url is None when observatory has not succeeded."""
        report = PublicationReport(
            event=self.make_event(),
            results=[
                OutletResult(outlet="observatory", succeeded=False, error="MW error"),
            ],
        )
        assert report.observatory_url is None

    def test_failed_outlets_filter(self) -> None:
        """failed_outlets() returns only failed results."""
        report = PublicationReport(
            event=self.make_event(),
            results=[
                OutletResult(
                    outlet="observatory", succeeded=True, artifact="https://obs.wiki/A"
                ),
                OutletResult(outlet="salesforce", succeeded=False, error="timeout"),
                OutletResult(
                    outlet="pardot", succeeded=False, error="invalid template"
                ),
            ],
        )
        failed = report.failed_outlets()
        assert len(failed) == 2
        assert {r.outlet for r in failed} == {"salesforce", "pardot"}

    def test_summary_all_passed(self) -> None:
        """Summary includes success icon when all outlets pass."""
        report = PublicationReport(
            event=self.make_event(),
            results=[
                OutletResult(
                    outlet="observatory", succeeded=True, artifact="https://obs.wiki/A"
                )
            ],
        )
        assert "✅" in report.summary()

    def test_summary_partial_failure(self) -> None:
        """Summary includes warning icon when any outlet fails."""
        report = PublicationReport(
            event=self.make_event(),
            results=[
                OutletResult(
                    outlet="observatory", succeeded=True, artifact="https://obs.wiki/A"
                ),
                OutletResult(outlet="salesforce", succeeded=False, error="timeout"),
            ],
        )
        assert "⚠️" in report.summary()
