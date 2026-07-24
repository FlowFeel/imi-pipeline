"""Tests for KellyContractValidators — TDD first.

Five deterministic JSON-LD shape validators, each tested against known-good
and known-bad payloads.

No LLM output assertions. All tests cover deterministic structural shapes.

TDD note: these tests were written before the implementation (E-09 discipline).

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest
from validators import KellyContractValidators


# ---------------------------------------------------------------------------
# Shared good payload (golden output A shape)
# ---------------------------------------------------------------------------

GOLDEN_PAYLOAD: dict = {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Why Capitalism Relies on Nature and Care Work It Does Not Pay For",
    "description": "Modern economies depend on unpriced ecosystem functions.",
    "url": "https://observatory.wiki/Why_Capitalism",
    "author": {
        "@type": "Person",
        "name": "Gunnar Rundgren",
        "url": "https://observatory.wiki/Gunnar_Rundgren",
    },
    "publisher": {
        "@type": "Organization",
        "name": "Observatory.wiki",
        "url": "https://observatory.wiki",
    },
    "datePublished": "2026-03-25T00:00:00Z",
    "dateModified": "2026-03-25T00:00:00Z",
    "keywords": ["capitalism", "economics", "economy"],
    "articleSection": "Economy",
    "sameAs": ["https://doi.org/10.59888/cave-art-2026"],
}


# ---------------------------------------------------------------------------
# no_hollow_fields
# ---------------------------------------------------------------------------


class TestNoHollowFields:
    """no_hollow_fields returns empty list for clean payloads, paths for hollow ones."""

    def test_no_hollow_fields_clean(self) -> None:
        """Golden payload — all real values — returns empty list."""
        violations = KellyContractValidators.no_hollow_fields(GOLDEN_PAYLOAD)
        assert violations == [], f"Expected no violations, got: {violations}"

    def test_no_hollow_fields_catches_empty_string(self) -> None:
        """Payload with an empty-string value returns the offending path."""
        payload = {
            "@type": "Article",
            "headline": "Test",
            "description": "",  # hollow
        }
        violations = KellyContractValidators.no_hollow_fields(payload)
        assert any("description" in v for v in violations), (
            f"Expected 'description' in violations, got: {violations}"
        )

    def test_no_hollow_fields_catches_empty_dict(self) -> None:
        """Payload with an empty-dict value returns the offending path."""
        payload = {
            "@type": "Article",
            "headline": "Test",
            "author": {},  # hollow dict
        }
        violations = KellyContractValidators.no_hollow_fields(payload)
        assert any("author" in v for v in violations), (
            f"Expected 'author' in violations, got: {violations}"
        )

    def test_no_hollow_fields_catches_empty_list(self) -> None:
        """Payload with an empty-list value returns the offending path."""
        payload = {
            "@type": "Article",
            "headline": "Test",
            "keywords": [],  # hollow list
        }
        violations = KellyContractValidators.no_hollow_fields(payload)
        assert any("keywords" in v for v in violations), (
            f"Expected 'keywords' in violations, got: {violations}"
        )

    def test_no_hollow_fields_nested_empty_string(self) -> None:
        """Nested empty string is caught with correct path."""
        payload = {"author": {"@type": "Person", "name": ""}}
        violations = KellyContractValidators.no_hollow_fields(payload)
        assert any("author" in v and "name" in v for v in violations), (
            f"Expected author.name path in violations, got: {violations}"
        )


# ---------------------------------------------------------------------------
# same_as_is_array
# ---------------------------------------------------------------------------


class TestSameAsIsArray:
    """same_as_is_array returns bool — True iff sameAs is a list (or absent)."""

    def test_same_as_is_array_passes(self) -> None:
        """sameAs as a list passes."""
        result = KellyContractValidators.same_as_is_array({"sameAs": ["url"]})
        assert result is True

    def test_same_as_is_array_fails_on_string(self) -> None:
        """sameAs as a bare string fails."""
        result = KellyContractValidators.same_as_is_array({"sameAs": "url"})
        assert result is False

    def test_same_as_absent_passes(self) -> None:
        """No sameAs — optional field, passes by default."""
        result = KellyContractValidators.same_as_is_array({"headline": "Test"})
        assert result is True


# ---------------------------------------------------------------------------
# author_is_person
# ---------------------------------------------------------------------------


class TestAuthorIsPerson:
    """author_is_person returns bool — True iff author.@type == 'Person' (or absent)."""

    def test_author_is_person_passes(self) -> None:
        """Author with @type Person passes."""
        result = KellyContractValidators.author_is_person(
            {"author": {"@type": "Person", "name": "Test"}}
        )
        assert result is True

    def test_author_is_person_fails_on_org(self) -> None:
        """Author with @type Organization fails."""
        result = KellyContractValidators.author_is_person(
            {"author": {"@type": "Organization"}}
        )
        assert result is False

    def test_author_absent_passes(self) -> None:
        """No author — optional, passes."""
        result = KellyContractValidators.author_is_person({"headline": "Test"})
        assert result is True


# ---------------------------------------------------------------------------
# dates_are_z_form
# ---------------------------------------------------------------------------


class TestDatesAreZForm:
    """dates_are_z_form returns bool — True iff all date fields end in Z."""

    def test_dates_are_z_form_passes(self) -> None:
        """Dates in Z form pass."""
        result = KellyContractValidators.dates_are_z_form(
            {
                "datePublished": "2026-06-28T12:00:00Z",
                "dateModified": "2026-06-28T12:00:00Z",
                "dateCreated": "2026-06-28T12:00:00Z",
            }
        )
        assert result is True

    def test_dates_are_z_form_fails(self) -> None:
        """Dates without Z designator fail."""
        result = KellyContractValidators.dates_are_z_form(
            {"datePublished": "2026-06-28"}  # no Z
        )
        assert result is False

    def test_dates_absent_passes(self) -> None:
        """No date fields — passes."""
        result = KellyContractValidators.dates_are_z_form({"headline": "Test"})
        assert result is True

    def test_offset_form_fails(self) -> None:
        """Dates with +00:00 offset instead of Z fail."""
        result = KellyContractValidators.dates_are_z_form(
            {"datePublished": "2026-03-25T00:00:00+00:00"}
        )
        assert result is False


# ---------------------------------------------------------------------------
# schema_type_is_valid
# ---------------------------------------------------------------------------


class TestSchemaTypeIsValid:
    """schema_type_is_valid returns bool — True iff @type is in valid set."""

    def test_schema_type_valid(self) -> None:
        """ScholarlyArticle is a valid primary type."""
        result = KellyContractValidators.schema_type_is_valid(
            {"@type": "ScholarlyArticle"}
        )
        assert result is True

    def test_schema_type_article_valid(self) -> None:
        """Article is valid."""
        result = KellyContractValidators.schema_type_is_valid({"@type": "Article"})
        assert result is True

    def test_schema_type_report_valid(self) -> None:
        """Report is valid."""
        result = KellyContractValidators.schema_type_is_valid({"@type": "Report"})
        assert result is True

    def test_schema_type_invalid(self) -> None:
        """Recipe is not a valid Observatory type."""
        result = KellyContractValidators.schema_type_is_valid({"@type": "Recipe"})
        assert result is False

    def test_schema_type_blog_posting_invalid(self) -> None:
        """BlogPosting is explicitly out of scope."""
        result = KellyContractValidators.schema_type_is_valid({"@type": "BlogPosting"})
        assert result is False

    def test_schema_type_news_article_invalid(self) -> None:
        """NewsArticle is explicitly out of scope."""
        result = KellyContractValidators.schema_type_is_valid({"@type": "NewsArticle"})
        assert result is False

    def test_schema_type_absent_passes(self) -> None:
        """No @type — optional, passes."""
        result = KellyContractValidators.schema_type_is_valid({"headline": "Test"})
        assert result is True

    def test_type_as_list_containing_valid_passes(self) -> None:
        """@type as list containing a valid type passes."""
        result = KellyContractValidators.schema_type_is_valid(
            {"@type": ["Article", "LearningResource"]}
        )
        assert result is True
