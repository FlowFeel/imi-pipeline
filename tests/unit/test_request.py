"""Tests for SyndicationRequest, OutletOutcome, and SyndicationResult.

Covers:
1. SyndicationRequest defaults
2. Idempotency key auto-generation from title slug
3. Idempotency key preserved when explicitly supplied
4. Outlet selection defaults (wordpress/salesforce/mediawiki=True, pardot=False)
5. from_dict with a full SyndicationRequest dict
6. from_dict with a legacy Draft dict (backward compatibility)
7. from_dict drops unknown keys without raising
8. OutletOutcome defaults
9. SyndicationResult defaults

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest

from phosphene.imi.request import OutletOutcome, SyndicationRequest, SyndicationResult


class TestSyndicationRequestDefaults:
    """SyndicationRequest has sane defaults for all optional fields."""

    def test_required_fields_only(self) -> None:
        """Construct with only required fields; check all defaults apply."""
        req = SyndicationRequest(title="Test Article")
        assert req.title == "Test Article"
        assert req.body == ""  # default when not specified
        assert req.body_format == "wikitext"
        assert req.author == ""
        assert req.category == ""
        assert req.source_url == ""
        assert req.date == ""
        assert req.publisher_id == "flow"
        assert req.trigger_source == ""
        assert req.pipeline_mode == "production"
        assert req.jsonld == {}

    def test_outlet_defaults(self) -> None:
        """Default outlets: WP, SF, MW enabled; Pardot disabled."""
        req = SyndicationRequest(title="T", body="B")
        assert req.outlets["wordpress"] is True
        assert req.outlets["salesforce"] is True
        assert req.outlets["mediawiki"] is True
        assert req.outlets["pardot"] is False

    def test_outlet_defaults_are_independent_instances(self) -> None:
        """Each request gets its own outlets dict — not a shared reference."""
        r1 = SyndicationRequest(title="T1", body="B1")
        r2 = SyndicationRequest(title="T2", body="B2")
        r1.outlets["wordpress"] = False
        assert r2.outlets["wordpress"] is True

    def test_custom_outlets(self) -> None:
        """Explicit outlets override defaults."""
        req = SyndicationRequest(
            title="T",
            body="B",
            outlets={"wordpress": False, "salesforce": False, "pardot": True},
        )
        assert req.outlets["wordpress"] is False
        assert req.outlets["salesforce"] is False
        assert req.outlets.get("mediawiki") is None  # not in custom dict
        assert req.outlets["pardot"] is True


class TestIdempotencyKey:
    """SyndicationRequest.__post_init__ derives idempotency_key from title."""

    def test_auto_generated_from_title(self) -> None:
        """idempotency_key defaults to lowercased hyphenated title."""
        req = SyndicationRequest(title="Why Care Work Matters", body="B")
        assert req.idempotency_key == "why-care-work-matters"

    def test_auto_generated_truncated_at_80_chars(self) -> None:
        """Auto-generated keys are capped at 80 characters."""
        long_title = "A " * 50  # 100 chars when lowercased + hyphenated
        req = SyndicationRequest(title=long_title.strip(), body="B")
        assert len(req.idempotency_key) <= 80

    def test_explicit_key_preserved(self) -> None:
        """An explicit idempotency_key is never overridden."""
        req = SyndicationRequest(
            title="Override Test",
            body="B",
            idempotency_key="my-custom-key-123",
        )
        assert req.idempotency_key == "my-custom-key-123"

    def test_spaces_become_hyphens(self) -> None:
        """Spaces in title become hyphens in the key."""
        req = SyndicationRequest(title="Cave Art and Older Ice", body="B")
        assert req.idempotency_key == "cave-art-and-older-ice"

    def test_title_with_mixed_case(self) -> None:
        """Title is lowercased in the key."""
        req = SyndicationRequest(title="CamelCase Title", body="B")
        assert req.idempotency_key == "camelcase-title"


class TestFromDict:
    """SyndicationRequest.from_dict handles v3 and legacy shapes."""

    def test_from_full_syndication_request_dict(self) -> None:
        """from_dict reconstructs a SyndicationRequest from its own asdict output."""
        from dataclasses import asdict

        original = SyndicationRequest(
            title="Cave Painting Study",
            body="Wikitext body.",
            author="Jan",
            category="Science",
            trigger_source="telegram",
        )
        d = asdict(original)
        reconstructed = SyndicationRequest.from_dict(d)
        assert reconstructed.title == original.title
        assert reconstructed.author == original.author
        assert reconstructed.idempotency_key == original.idempotency_key

    def test_from_legacy_draft_dict(self) -> None:
        """from_dict accepts a legacy Draft dict (no publisher_id, no outlets)."""
        legacy = {
            "title": "Legacy Article",
            "body": "Article body.",
            "author": "Flow",
            "category": "Economy",
            "source_url": "https://observatory.wiki/article",
        }
        req = SyndicationRequest.from_dict(legacy)
        assert req.title == "Legacy Article"
        assert req.author == "Flow"
        # Defaults apply for missing fields
        assert req.publisher_id == "flow"
        assert req.outlets["wordpress"] is True

    def test_from_dict_drops_unknown_keys(self) -> None:
        """from_dict silently drops keys not in SyndicationRequest (e.g. Draft-only fields)."""
        d = {
            "title": "Test",
            "body": "Body",
            "keywords": ["a", "b"],         # Draft-only field
            "metadata": {"extra": "data"},  # Draft-only field
        }
        # Should not raise
        req = SyndicationRequest.from_dict(d)
        assert req.title == "Test"

    def test_from_dict_none_values_dropped(self) -> None:
        """from_dict does not pass None values; dataclass defaults apply."""
        d = {"title": "T", "body": "B", "author": None, "category": None}
        req = SyndicationRequest.from_dict(d)
        assert req.author == ""    # default
        assert req.category == ""  # default


class TestOutletSelection:
    """Outlet selection logic — only True outlets are selected by the saga."""

    def test_selected_returns_only_enabled_outlets(self) -> None:
        """Filtering req.outlets for True gives only the selected outlets."""
        req = SyndicationRequest(
            title="T",
            body="B",
            outlets={"wordpress": True, "salesforce": False, "mediawiki": True, "pardot": False},
        )
        selected = [name for name, enabled in req.outlets.items() if enabled]
        assert selected == ["wordpress", "mediawiki"]

    def test_pardot_opt_in_selected(self) -> None:
        """Pardot is selected when explicitly opted in."""
        req = SyndicationRequest(
            title="T",
            body="B",
            outlets={"wordpress": False, "salesforce": False, "mediawiki": False, "pardot": True},
        )
        selected = [name for name, enabled in req.outlets.items() if enabled]
        assert selected == ["pardot"]


class TestOutletOutcome:
    """OutletOutcome dataclass defaults."""

    def test_defaults(self) -> None:
        """OutletOutcome.artifact and .error default to empty string."""
        o = OutletOutcome(outlet="wordpress", succeeded=True)
        assert o.artifact == ""
        assert o.error == ""

    def test_failure_carries_error(self) -> None:
        """OutletOutcome.error is set for failures."""
        o = OutletOutcome(outlet="salesforce", succeeded=False, error="429 rate limit")
        assert o.succeeded is False
        assert o.error == "429 rate limit"


class TestSyndicationResult:
    """SyndicationResult dataclass defaults."""

    def test_defaults(self) -> None:
        """SyndicationResult defaults: empty dict, empty string, empty list."""
        r = SyndicationResult(succeeded=True)
        assert r.outlet_results == {}
        assert r.error_message == ""
        assert r.compensations_executed == []

    def test_with_outlet_results(self) -> None:
        """SyndicationResult.outlet_results is keyed by outlet name."""
        outcomes = {
            "wordpress": OutletOutcome(outlet="wordpress", succeeded=True, artifact="https://wp.test/"),
            "salesforce": OutletOutcome(outlet="salesforce", succeeded=False, error="timeout"),
        }
        r = SyndicationResult(succeeded=False, outlet_results=outcomes, error_message="salesforce: timeout")
        assert r.outlet_results["wordpress"].succeeded is True
        assert r.outlet_results["salesforce"].succeeded is False
        assert r.error_message == "salesforce: timeout"
