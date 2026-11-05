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
    CrossrefClientProtocol,
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
        crossref_client: CrossrefClientProtocol | None = None,
    ) -> None:
        """Initialise with injectable clients satisfying protocol interfaces."""
        self._wp = wp_client
        self._mw = mw_client
        self._sf = sf_client
        if pardot_client is None:
            from phosphene.imi.fakes import FakePardotClient

            pardot_client = FakePardotClient()
        self._pardot_client = pardot_client
        if crossref_client is None:
            from phosphene.imi.fakes import FakeCrossrefClient

            crossref_client = FakeCrossrefClient()
        self._crossref = crossref_client

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
    # Scholarly Preprint & Crossref DOI Activities
    # ------------------------------------------------------------------

    @activity.defn
    async def publish_wordpress_preprint(self, request: Any) -> dict[str, Any]:
        """Publish scholarly preprint to WordPress with DOI status pending."""
        from phosphene.imi_wordpress.domain import (
            DOI,
            Author,
            DOIRecord,
            DOIStatus,
            EditorialState,
            License,
            VersionInfo,
        )

        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.wordpress import WordPressOutlet
        from phosphene.imi.request import PreprintDepositRequest
        from phosphene.imi.work import PreprintWork

        req = (
            PreprintDepositRequest.from_dict(request)
            if isinstance(request, dict)
            else request
        )
        suffix = req.doi_suffix.replace("imi.2026.", "")
        doi = DOI(suffix=f"imi.2026.{suffix}")
        primary = Author(
            name=req.primary_author_name,
            orcid=req.primary_author_orcid or None,
        )
        coauthors = [Author(name=name) for name in req.coauthor_names]
        doi_rec = DOIRecord(
            doi=doi,
            status=DOIStatus.PENDING,
            deposit_id="",
            minted_date="",
        )
        work = PreprintWork(
            title=req.title,
            primary_author=primary,
            coauthors=coauthors,
            abstract=req.abstract,
            doi_record=doi_rec,
            version=VersionInfo(number=1),
            editorial_state=EditorialState.LIVE_PREPRINT,
            license=License.CC_BY_NC_SA_4_0,
        )

        outlet = WordPressOutlet(client=self._wp)
        result = outlet.publish(
            PublicationEvent(work=work, publisher_id=req.publisher_id)
        )
        if not result.succeeded:
            raise RuntimeError(result.error or "WordPress preprint publish failed")

        post_url = result.artifact or ""
        post_id_raw = result.metadata.get("post_id", "0")
        try:
            post_id = int(post_id_raw)
        except (ValueError, TypeError):
            post_id = 0

        return {
            "post_id": post_id,
            "post_url": post_url,
            "doi": doi.value,
            "title": req.title,
        }

    @activity.defn
    async def deposit_crossref(self, request: Any) -> dict[str, Any]:
        """Generate schema 5.3.1 XML and deposit metadata to Crossref."""
        from phosphene.imi_wordpress.domain import (
            DOI,
            Author,
            DOIRecord,
            DOIStatus,
            EditorialState,
            License,
            VersionInfo,
        )

        from phosphene.imi.crossref import CrossrefXmlBuilder
        from phosphene.imi.work import PreprintWork

        title = request.get("title", "")
        author_name = request.get("primary_author_name", "Author")
        author_orcid = request.get("primary_author_orcid", "")
        coauthors = [Author(name=n) for n in request.get("coauthor_names", [])]
        target_url = request.get("target_url") or request.get("post_url", "")
        doi_val = request.get("doi", "")
        suffix = doi_val.replace("10.67767/imi.2026.", "").replace("10.67767/", "")

        work = PreprintWork(
            title=title,
            primary_author=Author(name=author_name, orcid=author_orcid or None),
            coauthors=coauthors,
            abstract=request.get("abstract", ""),
            doi_record=DOIRecord(
                doi=DOI(suffix=f"imi.2026.{suffix}"),
                status=DOIStatus.PENDING,
            ),
            version=VersionInfo(number=1),
            editorial_state=EditorialState.LIVE_PREPRINT,
            license=License.CC_BY_NC_SA_4_0,
        )

        xml = CrossrefXmlBuilder.build_xml(work, target_url=target_url)
        receipt = self._crossref.deposit(xml)

        if not receipt.is_valid:
            raise RuntimeError(receipt.error or "Crossref deposit was rejected")

        return {
            "deposit_id": receipt.deposit_id,
            "doi": receipt.doi,
            "status": receipt.status,
        }

    @activity.defn
    async def poll_crossref_status(self, request: Any) -> dict[str, Any]:
        """Poll Crossref receipt to confirm registration."""
        deposit_id = request.get("deposit_id", "")
        receipt = self._crossref.get_deposit_status(deposit_id)
        if not receipt.is_valid:
            raise RuntimeError(receipt.error or f"Failed to poll deposit {deposit_id}")

        return {
            "deposit_id": receipt.deposit_id,
            "doi": receipt.doi,
            "status": receipt.status,
        }

    @activity.defn
    async def activate_wordpress_doi(self, request: Any) -> dict[str, Any]:
        """Activate DOI on WordPress after confirmed Crossref deposit."""
        import time

        post_id = int(request.get("post_id", 0))
        deposit_id = request.get("deposit_id", "")
        doi = request.get("doi", "")
        minted_date = time.strftime("%Y-%m-%d")

        meta_update = {
            "reg_doi_status": "active",
            "reg_crossref_deposit_id": deposit_id,
            "reg_doi": doi,
            "reg_doi_url": f"https://doi.org/{doi}",
            "reg_doi_minted_date": minted_date,
        }

        self._wp.update_post(
            post_type="imi_registry",
            post_id=post_id,
            data={"meta": meta_update},
        )

        return {
            "activated": True,
            "post_id": post_id,
            "doi": doi,
            "status": "active",
        }

    @activity.defn
    async def rollback_wordpress_preprint(self, post_info: Any) -> None:
        """Rollback compensation: delete post if DOI registration aborted."""
        if isinstance(post_info, dict):
            post_id = post_info.get("post_id", 0)
            post_url = post_info.get("post_url", "")
            if hasattr(self._wp, "delete_post"):
                if post_id:
                    self._wp.delete_post(post_id)
                elif post_url:
                    self._wp.delete_post(post_url)

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
