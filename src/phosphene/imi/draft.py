"""Draft — backward-compatible alias and re-exports for PublicationWork.

Canonical models live in `phosphene.imi.work`.
This module re-exports `Draft`, `ArticleDraft`, `PreprintWork`, and `PublicationWork`
to maintain stability across legacy call sites.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.work import (
    ArticleDraft,
    Draft,
    InvariantStatic,
    PreprintWork,
    PublicationWork,
    promote_to_preprint,
)

__all__ = [
    "ArticleDraft",
    "Draft",
    "InvariantStatic",
    "PreprintWork",
    "PublicationWork",
    "promote_to_preprint",
]
