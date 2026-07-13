"""SyndicationRequest — the canonical input for all syndication workflows.

Trigger-agnostic: any trigger produces a SyndicationRequest.
Outlet-composable: the outlets dict controls which outlets fire.

Dataclass (not Pydantic) so Temporal's default data converter handles
serialisation without custom codec configuration.  Temporal serialises
dataclasses to JSON and deserialises them back; a Pydantic model would
require a custom codec, which adds operational complexity for no benefit
at the Temporal boundary.

``SyndicationRequest.from_dict`` exists for backward compatibility: the
old pipeline passed a Draft dict (title, body, author, category) and did
not carry outlet selection.  From-dict filters unknown fields so legacy
callers still work; the saga defaults to all three core outlets.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields


@dataclass
class SyndicationRequest:
    """The single input type for all syndication workflows.

    Trigger-agnostic: any trigger produces this. The workflow reads it.
    Outlet-composable: outlets dict controls which outlets fire.

    Dataclass (not Pydantic) so Temporal's default data converter
    handles it without custom codecs.

    Attributes:
        title: Article headline. Required.
        body: Full article body (wikitext, markdown, or HTML). Required.
        body_format: Format indicator for body. Default: "wikitext".
        author: Author display name.
        category: Primary content category.
        source_url: Origin URL if content came from an external system.
        date: ISO date string.
        outlets: Outlet selection — True means include in this run.
        publisher_id: Identifier of the agent initiating this syndication.
        trigger_source: Origin system identifier (e.g. "asana", "telegram").
        idempotency_key: Dedup key — auto-derived from title slug if empty.
        pipeline_mode: Execution mode (production | stage | dry_run).
        jsonld: JSON-LD / SEO structured data (for Kelly contract compliance).
    """

    # Content
    title: str
    body: str = ""  # wikitext, markdown, or HTML
    body_format: str = "wikitext"
    author: str = ""
    category: str = ""
    source_url: str = ""
    date: str = ""

    # Outlet selection — True means "include in this syndication run"
    outlets: dict[str, bool] = field(
        default_factory=lambda: {
            "wordpress": True,
            "salesforce": True,
            "mediawiki": True,
            "pardot": False,  # email is opt-in, not default
        }
    )

    # Metadata
    publisher_id: str = "flow"
    trigger_source: str = ""
    idempotency_key: str = ""
    pipeline_mode: str = "production"

    # JSON-LD / SEO (optional, for Kelly contract compliance)
    jsonld: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set idempotency key from title slug if not provided."""
        if not self.idempotency_key:
            self.idempotency_key = self.title.lower().replace(" ", "-")[:80]

    @classmethod
    def from_dict(cls, d: dict) -> "SyndicationRequest":
        """Build from a dict, ignoring unknown fields.

        Backward-compatible with legacy Draft dicts: unknown fields
        (e.g. ``keywords``, ``metadata``) are silently dropped.
        ``None`` values are also dropped so dataclass defaults apply.

        Args:
            d: Source dict, which may be a SyndicationRequest, a Draft,
               or any dict with at least ``title`` and ``body``.

        Returns:
            A fully populated SyndicationRequest.
        """
        known = {f.name for f in dc_fields(cls)}
        filtered = {k: v for k, v in d.items() if k in known and v is not None}
        return cls(**filtered)


@dataclass
class OutletOutcome:
    """Result from a single outlet in the saga.

    Attributes:
        outlet: Name of the outlet (e.g. "wordpress", "salesforce").
        succeeded: Whether the outlet completed successfully.
        artifact: Primary artifact produced (URL, record ID, page title).
        error: Error message if the outlet failed.
    """

    outlet: str
    succeeded: bool
    artifact: str = ""
    error: str = ""


@dataclass
class SyndicationResult:
    """Outcome of a syndication run.

    Dynamic: only outlets that were selected appear in outlet_results.
    Returned as a dict (via dataclasses.asdict) from the workflow so
    Temporal's default converter handles nested types correctly.

    Attributes:
        succeeded: True if all selected outlets completed without exception.
        outlet_results: Per-outlet outcome keyed by outlet name.
        error_message: Human-readable error if succeeded=False.
        compensations_executed: Compensation outcomes ("ok" or "failed:{err}").
    """

    succeeded: bool
    outlet_results: dict[str, OutletOutcome] = field(default_factory=dict)
    error_message: str = ""
    compensations_executed: list[str] = field(default_factory=list)
