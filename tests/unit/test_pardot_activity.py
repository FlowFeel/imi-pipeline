"""Tests for send_pardot_email activity — DI only, no @patch.

All tests use FakePardotClient injected at construction time.
No mocking libraries, no monkeypatching, no network, milliseconds.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from phosphene.imi.activities import SyndicationActivities
from phosphene.imi.fakes import FakeMWClient, FakePardotClient, FakeSFClient, FakeWPClient


def _make_activities(pardot_client: Any | None = None) -> SyndicationActivities:
    """Build SyndicationActivities with injected fake clients."""
    return SyndicationActivities(
        wp_client=FakeWPClient(),
        mw_client=FakeMWClient(),
        sf_client=FakeSFClient(),
        pardot_client=pardot_client or FakePardotClient(),
    )


def run(coro: Any) -> Any:
    """Run a coroutine synchronously for testing (no pytest-asyncio needed)."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestSendPardotEmailWithOutletResults:
    """send_pardot_email builds result from outlet_results when available."""

    def test_returns_sent_count_on_success(self) -> None:
        """Activity returns 'pardot-sent:N/M' when client succeeds."""
        fake = FakePardotClient()
        acts = _make_activities(fake)

        request = {
            "title": "Test Article",
            "outlet_results": {
                "observatory": {"succeeded": True, "artifact": "https://observatory.wiki/Draft:Test"},
                "wordpress": {"succeeded": True, "artifact": "https://imi.org/wp/test/"},
                "salesforce": {"succeeded": True, "artifact": "a1e00000000001"},
            },
        }
        result = run(acts.send_pardot_email(request))
        assert result == "pardot-sent:1/1"

    def test_calls_client_with_outlet_results(self) -> None:
        """Activity passes outlet artifact URLs to send_pipeline_notification."""
        fake = FakePardotClient()
        acts = _make_activities(fake)

        request = {
            "title": "Test Article",
            "outlet_results": {
                "observatory": {"succeeded": True, "artifact": "https://observatory.wiki/Draft:Test"},
                "wordpress": {"succeeded": True, "artifact": "https://imi.org/wp/test/"},
            },
        }
        run(acts.send_pardot_email(request))

        assert len(fake.calls) == 1
        call_result = fake.calls[0]["result"]
        assert call_result["observatory"] == "https://observatory.wiki/Draft:Test"
        assert call_result["wordpress"] == "https://imi.org/wp/test/"

    def test_only_succeeded_outlets_included(self) -> None:
        """Failed outlet results are not included in the Pardot result dict."""
        fake = FakePardotClient()
        acts = _make_activities(fake)

        request = {
            "title": "Test Article",
            "outlet_results": {
                "observatory": {"succeeded": True, "artifact": "https://observatory.wiki/Draft:Test"},
                "wordpress": {"succeeded": False, "error": "Network error"},
            },
        }
        run(acts.send_pardot_email(request))

        call_result = fake.calls[0]["result"]
        assert "observatory" in call_result
        assert "wordpress" not in call_result


class TestSendPardotEmailFallbackToMetadata:
    """send_pardot_email falls back to request metadata when no outlet_results."""

    def test_empty_outlet_results_uses_metadata(self) -> None:
        """Empty outlet_results dict triggers fallback to title/source_url."""
        fake = FakePardotClient()
        acts = _make_activities(fake)

        request = {
            "title": "Care Work Matters",
            "source_url": "https://example.com/article",
            "outlet_results": {},
        }
        result = run(acts.send_pardot_email(request))
        assert result.startswith("pardot-sent:")
        assert fake.calls[0]["result"]["title"] == "Care Work Matters"
        assert fake.calls[0]["result"]["source_url"] == "https://example.com/article"

    def test_missing_outlet_results_key_uses_metadata(self) -> None:
        """Request with no outlet_results key falls back to metadata."""
        fake = FakePardotClient()
        acts = _make_activities(fake)

        request = {
            "title": "No Outlets Yet",
            "source_url": "https://example.com/no-outlets",
        }
        result = run(acts.send_pardot_email(request))
        assert result.startswith("pardot-sent:")
        assert fake.calls[0]["result"]["title"] == "No Outlets Yet"

    def test_only_failed_outlets_uses_metadata(self) -> None:
        """If all outlet results have succeeded=False, falls back to metadata."""
        fake = FakePardotClient()
        acts = _make_activities(fake)

        request = {
            "title": "All Failed",
            "source_url": "https://example.com/all-failed",
            "outlet_results": {
                "observatory": {"succeeded": False, "error": "timeout"},
            },
        }
        result = run(acts.send_pardot_email(request))
        assert result.startswith("pardot-sent:")
        call_result = fake.calls[0]["result"]
        assert call_result.get("title") == "All Failed"

    def test_empty_request_uses_empty_strings(self) -> None:
        """Minimal empty request does not raise, returns pardot-sent."""
        fake = FakePardotClient()
        acts = _make_activities(fake)

        result = run(acts.send_pardot_email({}))
        assert result.startswith("pardot-sent:")
        call_result = fake.calls[0]["result"]
        assert call_result["title"] == ""
        assert call_result["source_url"] == ""


class TestSendPardotEmailErrorHandling:
    """send_pardot_email captures exceptions — does not propagate."""

    def test_raising_client_returns_pardot_error(self) -> None:
        """A client that raises returns 'pardot-error:<exc>' instead of raising."""

        class ExplodingPardotClient:
            """Always raises on send."""

            def send_pipeline_notification(
                self, result: dict, recipients: list | None = None
            ) -> list:
                raise RuntimeError("Pardot API unreachable")

        acts = _make_activities(ExplodingPardotClient())  # type: ignore[arg-type]
        result = run(acts.send_pardot_email({"title": "test"}))

        assert result.startswith("pardot-error:")
        assert "Pardot API unreachable" in result

    def test_connection_error_returns_pardot_error(self) -> None:
        """Connection errors are caught and reported as pardot-error."""

        class NetworkErrorClient:
            def send_pipeline_notification(
                self, result: dict, recipients: list | None = None
            ) -> list:
                raise ConnectionError("connection refused")

        acts = _make_activities(NetworkErrorClient())  # type: ignore[arg-type]
        result = run(acts.send_pardot_email({"title": "test"}))

        assert result.startswith("pardot-error:")
        assert "connection refused" in result

    def test_forward_activity_does_not_raise(self) -> None:
        """send_pardot_email never propagates exceptions to the caller/saga."""

        class AlwaysRaisesClient:
            def send_pipeline_notification(
                self, result: dict, recipients: list | None = None
            ) -> list:
                raise ValueError("unexpected value")

        acts = _make_activities(AlwaysRaisesClient())  # type: ignore[arg-type]
        # Must not raise
        result = run(acts.send_pardot_email({"title": "test"}))
        assert isinstance(result, str)


class TestFakePardotClientProtocol:
    """FakePardotClient satisfies PardotClientProtocol structurally."""

    def test_fake_records_calls(self) -> None:
        """FakePardotClient.calls records each invocation."""
        fake = FakePardotClient()
        fake.send_pipeline_notification({"observatory": "https://obs.test"})
        fake.send_pipeline_notification({"wordpress": "https://wp.test"}, recipients=None)

        assert len(fake.calls) == 2
        assert fake.calls[0]["result"]["observatory"] == "https://obs.test"
        assert fake.calls[1]["result"]["wordpress"] == "https://wp.test"

    def test_fake_returns_succeeded_results(self) -> None:
        """FakePardotClient returns a list of results with succeeded=True."""
        fake = FakePardotClient()
        results = fake.send_pipeline_notification({"observatory": "https://obs.test"})

        assert len(results) == 1
        assert results[0].succeeded is True

    def test_fake_satisfies_protocol(self) -> None:
        """FakePardotClient is an instance of PardotClientProtocol."""
        from phosphene.imi.protocols import PardotClientProtocol

        fake = FakePardotClient()
        assert isinstance(fake, PardotClientProtocol)

    def test_default_pardot_client_is_fake(self) -> None:
        """SyndicationActivities defaults to FakePardotClient when not injected."""
        acts = SyndicationActivities(
            wp_client=FakeWPClient(),
            mw_client=FakeMWClient(),
            sf_client=FakeSFClient(),
        )
        assert isinstance(acts._pardot_client, FakePardotClient)
