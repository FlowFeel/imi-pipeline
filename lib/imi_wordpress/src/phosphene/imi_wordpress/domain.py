"""Pure domain models for the IMI scholarly preprint registry.

This module models the core business reality of a scholarly preprint registration
independent of any wire protocol, transport format, or WordPress schema.

@dft
- A1 (pure-io-separation): Pure domain logic — zero I/O imports.
- A2 (determinism): Immutable frozen dataclasses, no non-deterministic calls.
- A4 (dft-docs): This docstring section.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# IMI's registered Crossref prefix (Member 57537)
IMI_DOI_PREFIX = "10.67767"


class License(StrEnum):
    """Scholarly publication licenses."""

    CC_BY_NC_SA_4_0 = "CC BY-NC-SA 4.0"
    CC_BY_4_0 = "CC BY 4.0"
    CC0_1_0 = "CC0 1.0"


class DOIStatus(StrEnum):
    """Lifecycle status of a Digital Object Identifier."""

    UNASSIGNED = "unassigned"
    PENDING = "pending"
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class EditorialState(StrEnum):
    """Jan's 5-state preprint editorial lifecycle plus withdrawal."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    UNDER_REVIEW = "under_review"
    LIVE_PREPRINT = "live_preprint"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"

    @property
    def is_published(self) -> bool:
        """True if the state requires a publicly indexable landing page."""
        return self in (
            EditorialState.LIVE_PREPRINT,
            EditorialState.PUBLISHED,
            EditorialState.WITHDRAWN,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DOI:
    """Scholarly Digital Object Identifier value object.

    Constructive and immutable. Defaults to IMI's Crossref prefix (10.67767).
    """

    suffix: str
    prefix: str = IMI_DOI_PREFIX

    @property
    def value(self) -> str:
        """The canonical DOI identifier string, e.g. '10.67767/imi.2026.001'."""
        return f"{self.prefix}/{self.suffix}"

    @property
    def url(self) -> str:
        """The permanent resolution URL, e.g. 'https://doi.org/10.67767/imi.2026.001'."""
        return f"https://doi.org/{self.value}"

    @classmethod
    def from_string(cls, raw: str) -> DOI:
        """Parse a DOI string into a structured DOI value object.

        Splits on the first slash if present; otherwise assumes the string is
        a suffix under IMI's prefix.
        """
        clean = raw.strip()
        if "/" in clean:
            pfx, sfx = clean.split("/", 1)
            return cls(suffix=sfx, prefix=pfx)
        return cls(suffix=clean)


@dataclass(frozen=True, slots=True, kw_only=True)
class DOIRecord:
    """Scholarly DOI registration and state record. Pure data."""

    doi: DOI | None = None
    status: DOIStatus = DOIStatus.UNASSIGNED
    minted_date: str = ""
    deposit_id: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class Author:
    """Scholarly contributor value object.

    Shared contract between primary author and co-authors to eliminate
    primitive obsession.
    """

    name: str
    orcid: str = ""
    affiliation: str = ""
    country: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class VersionInfo:
    """Preprint version lineage value object."""

    number: int = 1
    version_type: str = "major"  # major, minor, patch
    history: str = ""  # changelog / revision notes
    prior_versions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PreprintEntry:
    """Pure domain entity representing a scholarly preprint registry record.

    Axioms:
    - Pure business entity with zero knowledge of WordPress or wire serialization.
    - Preserves semantic collection types (tuple of keywords, tuple of authors).
    - Immutable with native slots for compact memory representation.
    """

    title: str
    primary_author: Author
    slug: str = ""
    editorial_state: EditorialState = EditorialState.DRAFT
    abstract: str = ""
    methodology: str = ""
    license: License = License.CC_BY_NC_SA_4_0
    declaration: bool = True
    keywords: tuple[str, ...] = ()
    coauthors: tuple[Author, ...] = ()
    destination_url: str = ""
    published_destination: str = "Observatory"
    pdf_url: str = ""
    schema_type: str = "ScholarlyArticle"
    registry_id: str = ""
    doi_record: DOIRecord = field(default_factory=DOIRecord)
    version: VersionInfo = field(default_factory=VersionInfo)
    withdrawal_notice: str = ""
