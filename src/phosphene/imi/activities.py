"""Syndication Activities — hexagonal adapters connecting outlets to Temporal.

Activities receive the full SyndicationRequest dict (v3).  Each forward
activity extracts what it needs, builds a Draft and PublicationEvent
internally, and delegates to the outlet.  Outlets remain unchanged:
they accept a PublicationEvent and return an OutletResult.  Temporal
is still infrastructure; the outlets are still the domain core.

Backward compatibility: if the request dict contains Draft fields but
not SyndicationRequest fields (e.g. ``author`` but not ``publisher_id``),
``_to_draft`` falls back gracefully.  Legacy callers that pass a plain
Draft dict still work.

Compensation activities mirror each forward activity.  The saga
registers a compensation at the moment a forward activity succeeds.
On failure the workflow calls ``_compensate`` in LIFO order.

New in v3:
- ``send_pardot_email`` — Pardot stub.  Returns "pardot-skipped" until
  a real Pardot client protocol is defined.
- ``noop_compensation`` — For outlets where reversal is impossible
  (email can't be unsent).

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from phosphene.imi.protocols import (
    MWClientProtocol,
    PardotClientProtocol,
    SFClientProtocol,
    WPClientProtocol,
)


class SyndicationActivities:
    """All external IO for the Syndication Saga.

    One class, injected with real or fake clients.  The injection is what
    makes activities testable without HTTP: inject fakes, assert outlet
    behaviour, never touch a network.  The same class with real clients
    becomes the production worker.

    Activities are @activity.defn methods — Temporal dispatches them.
    Each forward activity builds a Draft and PublicationEvent from the
    incoming SyndicationRequest dict, then delegates to the outlet.

    Clients injected: WPClientProtocol, MWClientProtocol, SFClientProtocol.
    """

    def __init__(
        self,
        wp_client: WPClientProtocol,
        mw_client: MWClientProtocol,
        sf_client: SFClientProtocol,
        pardot_client: PardotClientProtocol | None = None,
    ) -> None:
        """Initialise with injectable clients satisfying protocol interfaces."""
        self._wp = wp_client
        self._mw = mw_client
        self._sf = sf_client
        if pardot_client is None:
            from phosphene.imi.fakes import FakePardotClient

            pardot_client = FakePardotClient()
        self._pardot_client = pardot_client

    # ------------------------------------------------------------------
    # Forward activities
    # ------------------------------------------------------------------

    @activity.defn
    async def publish_wordpress(self, request: Any) -> str:
        """Create imi_registry post on WordPress. Returns post URL.

        Accepts a SyndicationRequest dict (v3) or a legacy Draft dict.
        Builds a Draft and PublicationEvent internally before delegating.

        Args:
            request: SyndicationRequest dict from Temporal.

        Returns:
            Post URL string.

        Raises:
            RuntimeError: If the outlet reports failure.
        """
        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.wordpress import WordPressOutlet

        d, publisher_id = self._to_draft_and_publisher(request)
        outlet = WordPressOutlet(client=self._wp)
        result = outlet.publish(PublicationEvent(draft=d, publisher_id=publisher_id))
        if not result.succeeded:
            raise RuntimeError(result.error or "WordPress publish failed")
        return result.artifact or ""

    @activity.defn
    async def publish_mediawiki(self, request: Any) -> str:
        """Create Draft: page on Observatory (MediaWiki). Returns page title.

        Args:
            request: SyndicationRequest dict from Temporal.

        Returns:
            Page title string.

        Raises:
            RuntimeError: If the outlet reports failure.
        """
        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.observatory import ObservatoryOutlet

        d, publisher_id = self._to_draft_and_publisher(request)
        outlet = ObservatoryOutlet(client=self._mw)
        result = outlet.publish(PublicationEvent(draft=d, publisher_id=publisher_id))
        if not result.succeeded:
            raise RuntimeError(result.error or "MediaWiki publish failed")
        return result.artifact or ""

    @activity.defn
    async def sync_salesforce(self, request: Any) -> str:
        """Create Content_Management__c record in Salesforce. Returns SF ID.

        Args:
            request: SyndicationRequest dict from Temporal.

        Returns:
            Salesforce record ID string.

        Raises:
            RuntimeError: If the outlet reports failure.
        """
        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.salesforce import SalesforceOutlet

        d, publisher_id = self._to_draft_and_publisher(request)
        outlet = SalesforceOutlet(client=self._sf)
        result = outlet.publish(PublicationEvent(draft=d, publisher_id=publisher_id))
        if not result.succeeded:
            raise RuntimeError(result.error or "Salesforce sync failed")
        return result.artifact or ""

    @activity.defn
    async def send_pardot_email(self, request: Any) -> str:
        """Send Pardot pipeline notification for the syndicated article.

        Extracts outlet artifact URLs from ``outlet_results`` in the request,
        builds a result dict from succeeded outlets, and delegates to the
        injected Pardot client. Falls back to ``title`` / ``source_url``
        metadata when no outlet results are available.

        Never propagates exceptions — they are captured and returned as
        ``pardot-error:<exception>`` strings so the saga can continue.

        Args:
            request: SyndicationRequest dict from Temporal.

        Returns:
            "pardot-sent:<sent>/<total>" on success, or
            "pardot-error:<exception>" on failure.
        """
        try:
            outlet_results = (
                request.get("outlet_results", {}) if isinstance(request, dict) else {}
            )

            # Build result dict from succeeded outlets
            result: dict[str, str] = {}
            for outlet_name, outlet_data in outlet_results.items():
                if isinstance(outlet_data, dict) and outlet_data.get("succeeded"):
                    result[outlet_name] = outlet_data.get("artifact", "")

            # Fall back to metadata when no succeeded outlet results
            if not result:
                meta = request if isinstance(request, dict) else {}
                result["title"] = meta.get("title", "")
                result["source_url"] = meta.get("source_url", "")

            outcomes = self._pardot_client.send_pipeline_notification(result)
            sent = sum(1 for o in outcomes if getattr(o, "succeeded", False))
            return f"pardot-sent:{sent}/{len(outcomes)}"
        except Exception as exc:
            return f"pardot-error:{exc}"

    # ------------------------------------------------------------------
    # Compensation activities (rollback)
    # ------------------------------------------------------------------

    @activity.defn
    async def delete_wordpress_post(self, post_url: str) -> None:
        """Rollback: delete the WordPress post at post_url.

        Args:
            post_url: URL of the post to delete.
        """
        self._wp.delete_post(post_url)

    @activity.defn
    async def delete_mediawiki_page(self, page_title: str) -> None:
        """Rollback: delete the Draft: page on Observatory.

        Args:
            page_title: Title of the page to delete.
        """
        self._mw.delete_page(page_title, reason="Saga compensation rollback")

    @activity.defn
    async def delete_salesforce_record(self, sf_id: str) -> None:
        """Rollback: delete the Salesforce Content_Management__c record.

        Args:
            sf_id: Salesforce record ID to delete.
        """
        self._sf.delete_record("Content_Management__c", sf_id)

    @activity.defn
    async def noop_compensation(self, artifact: str) -> None:
        """No-op compensation for outlets where reversal is not possible.

        Pardot emails cannot be unsent.  This compensation is registered
        by the saga for Pardot forward activities but does nothing on
        execution.  The activity must exist to satisfy the registry
        contract; it is intentionally a no-op.

        Args:
            artifact: Artifact ID from the forward activity (ignored).
        """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_draft_and_publisher(request: Any) -> tuple[Any, str]:
        """Extract a Draft and publisher_id from a request dict or legacy draft dict.

        Handles three input shapes:
        1. SyndicationRequest dict (v3) — has ``title``, ``body``, and
           optionally ``publisher_id``, ``author``, ``category``, etc.
        2. Legacy Draft dict — has ``title``, ``body``, ``author``,
           ``category``.  No ``publisher_id``.
        3. Draft or dataclass instance — passed through to _to_draft.

        Args:
            request: Temporal-deserialised activity input.

        Returns:
            (Draft instance, publisher_id string).
        """
        from phosphene.imi.draft import Draft

        if isinstance(request, dict):
            from phosphene.imi.parser import WikitextParser

            publisher_id = request.get("publisher_id", "flow") or "flow"
            # Extract Draft-compatible fields, dropping SyndicationRequest-only keys
            draft_keys = {
                "title",
                "body",
                "author",
                "category",
                "source_url",
                "keywords",
                "metadata",
            }
            draft_data: dict[str, Any] = {
                k: v for k, v in request.items() if k in draft_keys and v is not None
            }

            # --- Phase 1: Parse wikitext for author/category if needed ---
            body = draft_data.get("body", "")
            body_format = request.get("body_format", "wikitext")
            should_parse = body_format == "wikitext" and bool(body)

            author = draft_data.get("author", "")
            if not author and should_parse:
                parsed_author = WikitextParser.extract_author(body)
                if parsed_author:
                    draft_data["author"] = parsed_author

            category = draft_data.get("category", "")
            if not category and should_parse:
                parsed_category = WikitextParser.extract_category(body)
                if parsed_category:
                    draft_data["category"] = parsed_category

            # --- Phase 2: Strip empty strings so setdefault can apply defaults ---
            if not draft_data.get("author", ""):
                draft_data.pop("author", None)
            if not draft_data.get("category", ""):
                draft_data.pop("category", None)
            draft_data.setdefault("author", "Observatory")
            draft_data.setdefault("category", "General")

            # --- Phase 3: Construct Draft with resolved values ---
            return Draft(**draft_data), publisher_id

        if isinstance(request, Draft):
            return request, "flow"

        if hasattr(request, "__dataclass_fields__"):
            from dataclasses import asdict as _asdict

            return SyndicationActivities._to_draft_and_publisher(_asdict(request))

        # Fallback: treat as dict-like
        return SyndicationActivities._to_draft_and_publisher(dict(request))

    @staticmethod
    def _to_draft(draft: Any) -> Any:
        """Convert Temporal-deserialised draft to a Draft model.

        Backward-compatible helper for any code that still calls _to_draft
        directly.  New code should use _to_draft_and_publisher.

        Args:
            draft: Dict or dataclass from Temporal.

        Returns:
            Draft instance.
        """
        from phosphene.imi.draft import Draft

        if isinstance(draft, Draft):
            return draft
        if isinstance(draft, dict):
            return Draft(**draft)
        if hasattr(draft, "__dataclass_fields__"):
            from dataclasses import asdict

            return Draft(**asdict(draft))
        return Draft(**dict(draft))
