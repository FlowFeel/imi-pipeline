"""Publication event and result types — the provenance chain of the publish pipeline.

An article that reaches observatory.wiki carries no inherent record of who
published it, when, or what else was published alongside it. That provenance
is not a property of the article — it is a property of the act of publishing.
This module captures the act: a PublicationEvent records the decision to
publish, an OutletResult records what one outlet did with that decision, and
a PublicationReport aggregates the full consequence.

The separation matters because provenance and content have different lifecycles.
The Draft is frozen at creation and never changes. The event that triggered
publication may be retried, audited, compensated. Conflating them loses the
ability to reason about "what happened" independently of "what was published."

OutletResult.succeeded is a bool, not an exception. The never-raise pattern:
outlets return results, not exceptions. A failure is a data point to be
aggregated, not a control-flow interruption. If outlets raised, the pipeline
would need try/except per outlet, and the Report could never be complete —
the first exception would prevent subsequent outlets from reporting.

PublicationReport.all_succeeded aggregates rather than short-circuiting.
A partial publish (WordPress succeeded, Salesforce failed) is not a success
with a footnote — it is a distinct pipeline state that the saga compensator
needs to reason about. The Report makes that state inspectable.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime
from typing import Any

from phosphene.utils.text import slugify
from pydantic import Field, model_validator

from phosphene.imi.work import ArticleDraft, Draft, InvariantStatic, PublicationWork


class PublicationEvent(InvariantStatic):
    """The canonical trigger for the publish pipeline.

    Created once per publish request. Passed to every outlet unchanged.
    Outlets read the event; they do not modify it.

    Attributes:
        work: The publication work (ArticleDraft or PreprintWork) to be published.
        publisher_id: Identifier of the agent initiating publish (e.g. 'jan', 'flow').
        timestamp: When the event was created. Defaults to now (UTC).
        idempotency_key: Stable key for deduplication. Defaults to work title slug.
    """

    work: PublicationWork
    publisher_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    idempotency_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: Any) -> Any:
        """Allow legacy callers to pass  instead of ."""
        if isinstance(data, dict):
            if "draft" in data and "work" not in data:
                data = dict(data)
                data["work"] = data.pop("draft")
        return data

    @property
    def draft(self) -> ArticleDraft:
        """Backward-compatible accessor returning an ArticleDraft view.

        If the underlying work is an ArticleDraft, returns it directly.
        If it is a PreprintWork, returns its unidirectional article view projection.
        """
        if isinstance(self.work, ArticleDraft):
            return self.work
        return self.work.to_article_view()

    def model_copy(
        self, *, update: dict[str, Any] | None = None, deep: bool = False
    ) -> PublicationEvent:
        """Support legacy model_copy(update={"draft": ...})."""
        if update and "draft" in update and "work" not in update:
            update = dict(update)
            update["work"] = update.pop("draft")
        return super().model_copy(update=update, deep=deep)

    def model_post_init(self, __context: object) -> None:
        """Set idempotency key from work title if not provided."""
        if self.idempotency_key is None:
            object.__setattr__(
                self,
                "idempotency_key",
                slugify(self.work.title, max_length=80),
            )


class OutletResult(InvariantStatic):
    """Result produced by a single outlet.

    ``succeeded`` is a bool, not an exception, because an outlet failure is
    a data point to be collected — not a control-flow interruption. If outlets
    raised on failure, the caller would need per-outlet try/except and could
    never produce a complete Report: the first exception would mask all
    subsequent outlets. The never-raise pattern ensures every outlet gets
    its turn and every result is captured.

    Attributes:
        outlet: Name of the outlet (e.g. 'observatory', 'salesforce').
        succeeded: Whether the outlet completed successfully.
        artifact: The primary artifact produced (URL, record ID, etc.).
        error: Error message if the outlet failed.
        metadata: Additional outlet-specific data.
    """

    outlet: str
    succeeded: bool
    artifact: str | None = None
    error: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class PublicationReport(InvariantStatic):
    """Aggregated results from all outlets for a single PublicationEvent.

    The report is the final output of the pipeline. It tells Jan what
    succeeded, what failed, and where the published content lives.

    Attributes:
        event: The triggering publication event.
        results: One OutletResult per outlet that ran.
    """

    event: PublicationEvent
    results: list[OutletResult] = Field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        """True only if every outlet succeeded.

        Aggregates the full result set rather than short-circuiting on
        first failure. A partial publish (WordPress up, Salesforce down)
        is not a success — it is an inconsistent state that the saga
        compensator must resolve. This property makes that distinction
        visible at the Report level.
        """
        return bool(self.results) and all(r.succeeded for r in self.results)

    @property
    def observatory_url(self) -> str | None:
        """The live URL on observatory.wiki, if published."""
        for r in self.results:
            if r.outlet == "observatory" and r.succeeded:
                return r.artifact
        return None

    def failed_outlets(self) -> list[OutletResult]:
        """Return results for outlets that did not succeed."""
        return [r for r in self.results if not r.succeeded]

    def summary(self) -> str:
        """One-line human-readable summary of the report."""
        passed = [r.outlet for r in self.results if r.succeeded]
        failed = [r.outlet for r in self.results if not r.succeeded]
        status = "✅" if self.all_succeeded else "⚠️"
        return (
            f"{status} {self.event.draft.title!r} — passed: {passed} | failed: {failed}"
        )


@dataclass
class SyndicationResult:
    """Temporal Workflow return type for SyndicationSagaWorkflow.

    Dataclass (not Pydantic) — Temporal's default data converter
    handles dataclasses directly without custom codec configuration.

    Maps 1:1 to PublicationReport but serialisable by Temporal.
    """

    succeeded: bool
    wordpress_url: str = ""
    mediawiki_page: str = ""
    salesforce_id: str = ""
    observatory_url: str = ""
    error_message: str = ""
    compensations_executed: list[str] = dc_field(default_factory=list)
