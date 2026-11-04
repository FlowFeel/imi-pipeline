"""Crossref 5.3.1 deposit models and schema validation.

Pure domain representation of Crossref deposit batches for scholarly preprints
under IMI prefix 10.67767 (Member 57537).

Axioms:
- A1 (pure-io-separation): Pure data structures, zero network/IO.
- A2 (determinism): Pure functions, immutable records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

CROSSREF_SCHEMA_VERSION = "5.3.1"
CROSSREF_XMLNS = "http://www.crossref.org/schema/5.3.1"
JATS_XMLNS = "http://www.ncbi.nlm.nih.gov/JATS1"

IMI_DOI_PREFIX = "10.67767"
IMI_MEMBER_ID = "57537"
IMI_DEPOSITOR_NAME = "Independent Media Institute"
IMI_DEPOSITOR_EMAIL = "deposits@independentmediainstitute.org"
IMI_REGISTRANT = "Independent Media Institute"


class DepositStatus(StrEnum):
    """Lifecycle status of a Crossref deposit batch."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"


_ORCID_RE = re.compile(
    r"^(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])$",
    re.IGNORECASE,
)


def normalize_orcid(raw: str) -> str:
    """Normalize and validate an ORCID string to canonical URI format.

    Returns 'https://orcid.org/0000-0002-1825-0097' on match.
    Raises ValueError on invalid format.
    """
    clean = raw.strip()
    if not clean:
        return ""
    m = _ORCID_RE.match(clean)
    if not m:
        raise ValueError(f"Invalid ORCID identifier format: {raw!r}")
    orcid_digits = m.group(1).upper()
    return f"https://orcid.org/{orcid_digits}"


@dataclass(frozen=True, slots=True, kw_only=True)
class CrossrefContributor:
    """A person contributor to a Crossref deposit."""

    name: str
    sequence: str = "first"  # 'first' | 'additional'
    contributor_role: str = "author"
    orcid: str = ""
    affiliation: str = ""

    def __post_init__(self) -> None:
        if self.sequence not in ("first", "additional"):
            raise ValueError(
                f"sequence must be 'first' or 'additional', got {self.sequence!r}"
            )
        if self.orcid:
            # Validate format
            normalize_orcid(self.orcid)

    @property
    def given_name(self) -> str:
        parts = self.name.strip().split()
        return " ".join(parts[:-1]) if len(parts) > 1 else ""

    @property
    def surname(self) -> str:
        parts = self.name.strip().split()
        return parts[-1] if parts else ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CrossrefDepositRecord:
    """Deposit metadata for a single preprint item."""

    title: str
    doi: str
    resource_url: str
    primary_author: CrossrefContributor
    coauthors: tuple[CrossrefContributor, ...] = ()
    abstract: str = ""
    posted_date: str = ""  # YYYY-MM-DD
    license_url: str = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
    group_title: str = "Observatory Preprints"

    def __post_init__(self) -> None:
        if not self.doi.startswith(f"{IMI_DOI_PREFIX}/"):
            raise ValueError(
                f"Invalid DOI prefix for IMI deposit: {self.doi!r}, expected {IMI_DOI_PREFIX}/*"
            )
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.resource_url.strip():
            raise ValueError("resource_url cannot be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class CrossrefDepositBatch:
    """Top-level batch envelope for Crossref 5.3.1 deposit."""

    batch_id: str
    depositor_name: str = IMI_DEPOSITOR_NAME
    depositor_email: str = IMI_DEPOSITOR_EMAIL
    registrant: str = IMI_REGISTRANT
    timestamp: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))
    records: tuple[CrossrefDepositRecord, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class DepositReceipt:
    """Parsed deposit receipt from Crossref submission."""

    deposit_id: str
    doi: str
    status: DepositStatus
    raw_response: str
    message: str = ""
