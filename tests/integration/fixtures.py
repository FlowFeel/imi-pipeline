"""Shared fixtures for IMI integration tests.

Provides:
  - IMI_INTEGRATION_DRAFT: factory function returning an ArticleDraft
    with cave paper metadata and realistic JSON-LD payload.
  - CAVE_PAPER_JSONLD: standalone dict of the cave paper JSON-LD.
  - Draft: lightweight dataclass for tests that do not need Pydantic overhead.
  - make_pydantic_draft: convert a Draft dataclass to the real Pydantic Draft.
  - require_integration: skip unless IMI_INTEGRATION=true in env.

The cave paper draft mirrors the golden output B shape from the Kelly contract
(ScholarlyArticle path) with author affiliation, sameAs array, and all date
fields in Z form.

Keywords include "integration-test" and "do-not-index" so records are easily
found and cleaned up in any real system.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest

from phosphene.imi.draft import Draft as ArticleDraft

# ---------------------------------------------------------------------------
# Lightweight fixture dataclass (no Pydantic validation overhead)
# ---------------------------------------------------------------------------


@dataclass
class Draft:
    """Lightweight draft for integration tests.

    Not the Pydantic Draft — a plain dataclass that can be used as a
    fixture without Pydantic validation overhead.
    For tests that need the real Draft, use make_pydantic_draft().
    """

    title: str = "IMI Integration Test — Cave Behaviours v8"
    body: str = "Integration test article. Do not publish."
    author: str = "Flow (pipeline test)"
    category: str = "Economy"
    source_url: str | None = None
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# JSON-LD payload (cave paper, golden output B shape)
# ---------------------------------------------------------------------------

CAVE_PAPER_JSONLD: dict = {
    "@context": "https://schema.org",
    "@type": "ScholarlyArticle",
    "headline": "Cave Art and Early Human Symbolism: An Integration Test Article",
    "description": (
        "Upper Paleolithic cave art as evidence of early symbolic cognition: "
        "integration test fixture, do not publish or index."
    ),
    "url": "https://observatory.wiki/Cave_Art_And_Early_Human_Symbolism_Integration_Test",
    "mainEntityOfPage": {
        "@type": "WebPage",
        "@id": "https://observatory.wiki/Cave_Art_And_Early_Human_Symbolism_Integration_Test",
    },
    "author": {
        "@type": "Person",
        "name": "Test Author",
        "url": "https://observatory.wiki/Test_Author",
        "affiliation": {
            "@type": "Organization",
            "name": "Independent Media Institute",
        },
    },
    "publisher": {
        "@type": "Organization",
        "name": "Observatory.wiki",
        "url": "https://observatory.wiki",
    },
    "datePublished": "2026-06-28T00:00:00Z",
    "dateModified": "2026-06-28T00:00:00Z",
    "keywords": ["cave-art", "integration-test", "do-not-index"],
    "articleSection": "Anthropology",
    "license": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "sameAs": ["https://doi.org/10.59888/cave-art-integration-test-2026"],
    "identifier": "10.59888/cave-art-integration-test-2026",
    "about": "Prehistoric archaeology",
}


# ---------------------------------------------------------------------------
# Factory: IMI_INTEGRATION_DRAFT — returns ArticleDraft for the cave paper
# ---------------------------------------------------------------------------


def IMI_INTEGRATION_DRAFT() -> ArticleDraft:
    """Return a test ArticleDraft with cave paper metadata.

    The payload mirrors the golden output B shape from the Kelly contract:
    a ScholarlyArticle with author affiliation, sameAs array, and all
    required date fields in Z form.

    Keywords include "integration-test" and "do-not-index" so the
    record is easily found and cleaned up in any real system.

    Returns:
        A frozen ArticleDraft instance ready for pipeline testing.
    """
    return ArticleDraft(
        title="Cave Art and Early Human Symbolism: An Integration Test Article",
        body=(
            "Integration test article. Do not publish or index. "
            "This fixture represents a Woodchipper-evaluated paper on "
            "Upper Paleolithic cave art and early human symbolic cognition."
        ),
        author="Test Author",
        category="Anthropology",
        keywords=["cave-art", "integration-test", "do-not-index"],
        metadata={
            "schema_type": "ScholarlyArticle",
            "do_not_publish": "true",
        },
    )


# ---------------------------------------------------------------------------
# IMI_INTEGRATION gate
# ---------------------------------------------------------------------------


def require_integration() -> None:
    """Skip the test if IMI_INTEGRATION env var is not set.

    Gate for tests that require external infrastructure
    (Flask mock servers, Docker containers, etc.).

    Raises:
        pytest.skip.Exception: If IMI_INTEGRATION is not set to a truthy value.
    """
    if os.environ.get("IMI_INTEGRATION", "").lower() not in {"true", "1", "yes"}:
        pytest.skip("Set IMI_INTEGRATION=true to run")


# ---------------------------------------------------------------------------
# Pydantic Draft converter
# ---------------------------------------------------------------------------


def make_pydantic_draft(fixture_draft: Draft | None = None) -> ArticleDraft:
    """Convert a fixture Draft dataclass to the real Pydantic ArticleDraft.

    When no fixture_draft is supplied, returns IMI_INTEGRATION_DRAFT() — the
    canonical cave paper test draft. Pass a Draft() instance to override.

    Args:
        fixture_draft: Optional fixture Draft dataclass. When None, delegates
            to IMI_INTEGRATION_DRAFT().

    Returns:
        A phosphene.imi.draft.Draft (ArticleDraft) instance.
    """
    if fixture_draft is None:
        return IMI_INTEGRATION_DRAFT()
    return ArticleDraft(
        title=fixture_draft.title,
        body=fixture_draft.body,
        author=fixture_draft.author,
        category=fixture_draft.category,
    )
