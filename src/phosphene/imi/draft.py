"""Draft — the canonical input to the publish pipeline.

A Draft is the normalised representation of a finished article,
regardless of where it arrived from. Asana task, Telegram message,
or structured document — all become a Draft before the pipeline
touches them.

The Draft is Invariant Static: frozen, strict, no empty strings.
This is the null-omission principle applied at the input boundary.
If a field is absent, it is absent — not an empty string, not None
masquerading as data.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator


class InvariantStatic(BaseModel):
    """Base class for frozen, strict Pydantic models."""

    model_config = {"frozen": True, "extra": "forbid"}


class Draft(InvariantStatic):
    """A finished article ready for publication.

    The stable contract between ingestion and publication.
    Every field that is present must carry real data — no empty strings.

    Attributes:
        title: Article headline. Required. Non-empty.
        body: Full article body text or wikitext. Required. Non-empty.
        author: Author display name. Required. Non-empty.
        category: Primary content category (e.g. "Economy", "Environment").
        source_url: Origin URL if draft came from an external system.
        keywords: SEO keywords for the article.
        metadata: Arbitrary additional fields from the source system.
    """

    title: str
    body: str
    author: str
    category: str
    source_url: str | None = None
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def slug(self) -> str:
        """URL-safe slug derived from the title.

        Computed from title so agents can use draft.slug without
        knowing how slugs are constructed.

        Returns:
            Lowercase hyphenated slug, e.g. "why-care-work-matters".
        """
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")

    @model_validator(mode="after")
    def no_empty_strings(self) -> Draft:
        """Enforce null-omission — no empty string values."""
        for field in ("title", "body", "author", "category"):
            if not getattr(self, field).strip():
                raise ValueError(f"Field '{field}' must not be empty.")
        return self
