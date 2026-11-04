"""Crossref 5.3.1 deposit builder and client package."""

from phosphene.imi.crossref.client import (
    CrossrefClientProtocol,
    CrossrefHttpClient,
    parse_deposit_receipt,
)
from phosphene.imi.crossref.generator import render_crossref_xml
from phosphene.imi.crossref.models import (
    CrossrefContributor,
    CrossrefDepositBatch,
    CrossrefDepositRecord,
    DepositReceipt,
    DepositStatus,
    normalize_orcid,
)

__all__ = [
    "CrossrefClientProtocol",
    "CrossrefContributor",
    "CrossrefDepositBatch",
    "CrossrefDepositRecord",
    "CrossrefHttpClient",
    "DepositReceipt",
    "DepositStatus",
    "normalize_orcid",
    "parse_deposit_receipt",
    "render_crossref_xml",
]
