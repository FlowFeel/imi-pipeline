"""Tests for Draft — the canonical pipeline input.

All tests are pure. No network calls. No fixtures beyond inline data.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest

from phosphene.imi.draft import Draft


class TestDraft:
    """Tests for Draft construction and validation."""

    def test_valid_draft_constructs(self) -> None:
        """A fully populated draft constructs without error."""
        d = Draft(
            title="Why Care Work Matters",
            body="Care work is the foundation of all economies...",
            author="Gunnar Rundgren",
            category="Economy",
        )
        assert d.title == "Why Care Work Matters"
        assert d.author == "Gunnar Rundgren"

    def test_empty_title_is_rejected(self) -> None:
        """Empty title violates null-omission — must be rejected."""
        with pytest.raises(Exception):
            Draft(title="", body="body", author="author", category="cat")

    def test_empty_body_is_rejected(self) -> None:
        """Empty body violates null-omission — must be rejected."""
        with pytest.raises(Exception):
            Draft(title="title", body="", author="author", category="cat")

    def test_whitespace_only_title_is_rejected(self) -> None:
        """Whitespace-only title is not a real title."""
        with pytest.raises(Exception):
            Draft(title="   ", body="body", author="author", category="cat")

    def test_optional_fields_have_sensible_defaults(self) -> None:
        """Optional fields default to empty collections, not None."""
        d = Draft(title="title", body="body", author="author", category="cat")
        assert d.keywords == []
        assert d.metadata == {}
        assert d.source_url is None

    def test_draft_is_immutable(self) -> None:
        """Draft is InvariantStatic — mutation raises."""
        d = Draft(title="title", body="body", author="author", category="cat")
        with pytest.raises(Exception):
            d.title = "new title"  # type: ignore[misc]

    def test_extra_fields_are_forbidden(self) -> None:
        """Extra fields are rejected — strict schema."""
        with pytest.raises(Exception):
            Draft(
                title="title",
                body="body",
                author="author",
                category="cat",
                unknown_field="value",
            )
