"""PublicationWork — closed algebraic sum type for editorial and scholarly works.

Partitions the publication domain into mutually exclusive, invariant-static variants:
1. ArticleDraft — journalistic editorial draft for magazine circulation (Observatory, Salesforce, Pardot).
2. PreprintWork — scholarly research record registered with persistent DOI (Crossref, IMI Scholar Registry).

Deduction runs downward from pure domain models. Egress outlets pattern-match
on PublicationWork and dispatch to specialized adapters without complecting.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal, Union

from phosphene.imi_wordpress.domain import (
    DOI,
    Author,
    DOIRecord,
    DOIStatus,
    EditorialState,
    License,
    PreprintEntry,
    VersionInfo,
)
from phosphene.utils.text import slugify
from phosphene.utils.wikitext import render_wikitext_template
from pydantic import BaseModel, Field, model_validator


class InvariantStatic(BaseModel):
    """Base class for frozen, strict Pydantic models.

    Enforces immutability and forbids undeclared attributes.
    """

    model_config = {
        "frozen": True,
        "extra": "forbid",
        "arbitrary_types_allowed": True,
    }


class ArticleDraft(InvariantStatic):
    """A journalistic article draft ready for magazine publication.

    Every field present must carry real data (null-omission). No hollow fields.
    """

    kind: Literal["article"] = "article"
    title: str
    body: str
    author: str
    category: str
    source_url: str | None = None
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def slug(self) -> str:
        """URL-safe slug derived deterministically from the title."""
        return slugify(self.title)

    @model_validator(mode="after")
    def no_empty_strings(self) -> ArticleDraft:
        """Enforce null-omission — no empty string values in core fields."""
        for field in ("title", "body", "author", "category"):
            if not getattr(self, field).strip():
                raise ValueError(f"Field '{field}' must not be empty.")
        return self


# Backward-compatible alias for existing callers
Draft = ArticleDraft


class PreprintWork(InvariantStatic):
    """A scholarly research work governed by the IMI Scholar Registry.

    Models the full scholarly apparatus: author affiliations, ORCIDs,
    Crossref DOI record, version increments, and immutable PDF artifact.
    """

    kind: Literal["preprint"] = "preprint"
    title: str
    primary_author: Author
    abstract: str = ""
    methodology: str = ""
    license: License = License.CC_BY_NC_SA_4_0
    declaration: bool = True
    keywords: list[str] = Field(default_factory=list)
    coauthors: list[Author] = Field(default_factory=list)
    destination_url: str = ""
    published_destination: str = "Observatory"
    pdf_url: str = ""
    schema_type: str = "ScholarlyArticle"
    registry_id: str = ""
    doi_record: DOIRecord = Field(default_factory=DOIRecord)
    version: VersionInfo = Field(default_factory=VersionInfo)
    editorial_state: EditorialState = EditorialState.DRAFT
    withdrawal_notice: str | None = None
    body: str | None = None

    @property
    def slug(self) -> str:
        """URL-safe slug derived deterministically from the title."""
        return slugify(self.title)

    @model_validator(mode="after")
    def no_empty_strings(self) -> PreprintWork:
        """Enforce non-empty title and primary author name."""
        if not self.title.strip():
            raise ValueError("Field 'title' must not be empty.")
        if not self.primary_author.name.strip():
            raise ValueError("Primary author 'name' must not be empty.")
        return self

    def to_preprint_entry(self) -> PreprintEntry:
        """Project to pure imi-wordpress PreprintEntry domain entity."""
        return PreprintEntry(
            title=self.title,
            primary_author=self.primary_author,
            slug=self.slug,
            editorial_state=self.editorial_state,
            abstract=self.abstract,
            methodology=self.methodology,
            license=self.license,
            declaration=self.declaration,
            keywords=tuple(self.keywords),
            coauthors=tuple(self.coauthors),
            destination_url=self.destination_url,
            published_destination=self.published_destination,
            pdf_url=self.pdf_url,
            schema_type=self.schema_type,
            registry_id=self.registry_id,
            doi_record=self.doi_record,
            version=self.version,
            withdrawal_notice=self.withdrawal_notice or "",
        )

    def to_article_view(self) -> ArticleDraft:
        """Unidirectional projection of a scholarly work into an article presentation view.

        Extracts the narrative text, formats the author, and prepends
        the {{Preprint}} banner if in live preprint state.
        MediaWiki consumes this without dependency on Crossref/DOI infrastructure.
        """
        content = self.body or self.abstract
        body = (
            render_wikitext_template("Preprint", {}, body=content)
            if self.editorial_state == EditorialState.LIVE_PREPRINT
            else content
        )
        return ArticleDraft(
            title=self.title,
            body=body,
            author=self.primary_author.name,
            category="Preprints",
            keywords=list(self.keywords),
            source_url=self.destination_url or None,
        )


def promote_to_preprint(
    draft: ArticleDraft,
    primary_author: Author | None = None,
    abstract: str = "",
    methodology: str = "",
    license: License = License.CC_BY_NC_SA_4_0,
    declaration: bool = True,
    coauthors: Sequence[Author] = (),
    pdf_url: str = "",
    doi_record: DOIRecord | None = None,
    version: VersionInfo | None = None,
    editorial_state: EditorialState = EditorialState.DRAFT,
) -> PreprintWork:
    """Formal promotion factory: transitions an ArticleDraft into an immutable PreprintWork.

    Preserves audit trails: the originating draft remains complete within its
    own editorial history, while the newly minted preprint begins its immutable
    lifecycle under its own DOI allocation.
    """
    author = primary_author or Author(name=draft.author)
    return PreprintWork(
        title=draft.title,
        primary_author=author,
        abstract=abstract or draft.body[:500],
        methodology=methodology,
        license=license,
        declaration=declaration,
        keywords=list(draft.keywords),
        coauthors=list(coauthors),
        destination_url=draft.source_url or "",
        pdf_url=pdf_url,
        doi_record=doi_record or DOIRecord(),
        version=version or VersionInfo(number=1),
        editorial_state=editorial_state,
        body=draft.body,
    )


# Closed Algebraic Sum Type
PublicationWork = Annotated[
    ArticleDraft | PreprintWork,
    Field(discriminator="kind"),
]
