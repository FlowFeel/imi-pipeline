"""Tests for integration fixtures — IMI_INTEGRATION_DRAFT factory, Draft, make_pydantic_draft.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fixtures import (
    IMI_INTEGRATION_DRAFT,
    Draft,
    make_pydantic_draft,
    require_integration,
)


class TestIMIIntegrationDraft:
    """IMI_INTEGRATION_DRAFT is a factory returning a real ArticleDraft."""

    def test_factory_returns_article_draft(self) -> None:
        """Factory call returns a phosphene.imi.draft.Draft instance."""
        from phosphene.imi.draft import Draft as ArticleDraft

        draft = IMI_INTEGRATION_DRAFT()
        assert isinstance(draft, ArticleDraft)

    def test_draft_has_title(self) -> None:
        """Returned draft has a non-empty title containing 'Integration Test'."""
        draft = IMI_INTEGRATION_DRAFT()
        assert draft.title
        assert "Integration Test" in draft.title

    def test_draft_has_body(self) -> None:
        """Returned draft has a non-empty body."""
        draft = IMI_INTEGRATION_DRAFT()
        assert draft.body

    def test_draft_has_author(self) -> None:
        """Returned draft has a non-empty author."""
        draft = IMI_INTEGRATION_DRAFT()
        assert draft.author

    def test_draft_has_category(self) -> None:
        """Returned draft has the Anthropology category (cave paper)."""
        draft = IMI_INTEGRATION_DRAFT()
        assert draft.category == "Anthropology"

    def test_draft_has_integration_test_keywords(self) -> None:
        """Returned draft carries integration-test and do-not-index keywords."""
        draft = IMI_INTEGRATION_DRAFT()
        assert "integration-test" in draft.keywords
        assert "do-not-index" in draft.keywords

    def test_each_call_returns_fresh_instance(self) -> None:
        """Factory returns a new instance each call (frozen Pydantic)."""
        d1 = IMI_INTEGRATION_DRAFT()
        d2 = IMI_INTEGRATION_DRAFT()
        assert d1 is not d2
        assert d1 == d2  # equal values


class TestDraft:
    """The lightweight Draft dataclass has sane defaults."""

    def test_default_draft_has_title(self) -> None:
        """Default Draft dataclass has a non-empty title."""
        d = Draft()
        assert d.title
        assert "Integration Test" in d.title

    def test_default_draft_has_body(self) -> None:
        """Default Draft dataclass has a non-empty body."""
        assert Draft().body

    def test_default_draft_has_author(self) -> None:
        """Default Draft dataclass has a non-empty author."""
        assert Draft().author

    def test_default_draft_has_category(self) -> None:
        """Default Draft dataclass has 'Economy' category."""
        assert Draft().category == "Economy"

    def test_draft_is_dataclass(self) -> None:
        """Draft is a proper dataclass, not Pydantic."""
        import dataclasses

        assert dataclasses.is_dataclass(Draft)


class TestRequireIntegration:
    """require_integration skips when IMI_INTEGRATION is not set."""

    def test_skips_without_env_var(self) -> None:
        """Without IMI_INTEGRATION, pytest.skip is raised."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("IMI_INTEGRATION", None)
            with pytest.raises(pytest.skip.Exception):
                require_integration()

    def test_passes_with_env_var(self) -> None:
        """With IMI_INTEGRATION=true, no skip."""
        with patch.dict(os.environ, {"IMI_INTEGRATION": "true"}):
            require_integration()  # Should not raise


class TestMakePydanticDraft:
    """make_pydantic_draft converts fixture Draft to Pydantic ArticleDraft."""

    def test_converts_default_draft(self) -> None:
        """Default (no args) returns the IMI_INTEGRATION_DRAFT cave paper."""
        from phosphene.imi.draft import Draft as ArticleDraft

        result = make_pydantic_draft()
        assert isinstance(result, ArticleDraft)
        # Default with no args == the cave paper factory
        assert result.title == IMI_INTEGRATION_DRAFT().title

    def test_converts_custom_draft(self) -> None:
        """Custom fixture Draft converts correctly."""
        from phosphene.imi.draft import Draft as ArticleDraft

        custom = Draft(
            title="Custom Test",
            body="Custom body.",
            author="Test Author",
            category="Environment",
        )
        result = make_pydantic_draft(custom)
        assert isinstance(result, ArticleDraft)
        assert result.title == "Custom Test"
        assert result.category == "Environment"
