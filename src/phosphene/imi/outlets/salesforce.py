"""SalesforceOutlet — creates a Content_Management__c record on publish.

``Content_Management__c`` exists because fundraising and editorial are
causally linked but operationally separate. When Jan reports to funders,
she needs to say "we published 47 articles this quarter across these
categories" — that query runs against Salesforce, not against MediaWiki.
The custom object bridges the gap: every published article gets a
Salesforce record that fundraising dashboards, Pardot campaigns, and
board reports can reference without querying the wiki.

Schema (discovered 2026-06-22 against live indmedia.my.salesforce.com)::

    Name              — auto-number (NOT settable, omit from payload)
    Headline__c       — article title
    Date_Received__c  — date, REQUIRED
    Pay__c            — boolean, REQUIRED (default False)
    GTM_Site_Uploaded__c — boolean, REQUIRED (default False)
    Translated__c     — boolean, REQUIRED (default False)
    Observatory_Classics__c — boolean, REQUIRED (default False)
    Observatory_wiki_Site_Link__c — URL (was Observatory_URL__c)
    Observatory_wiki_Status__c    — picklist (was Status__c)
    Observatory_Area__c           — picklist (was Category__c)
    Contact__c        — reference (author lookup, optional)

Accepts a SFClientProtocol at construction. Creates a Salesforce record
capturing the publication event and returns an OutletResult with the
Salesforce record ID.

Idempotent: checks by Headline__c (not Name, which is auto-number and
not searchable by title).

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from datetime import date

from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.outlets.base import PublicationOutlet
from phosphene.imi.protocols import SFClientProtocol


class SalesforceOutlet(PublicationOutlet):
    """Creates a Salesforce Content_Management__c record on article publish.

    The record enables downstream reporting, Pardot campaign attribution,
    and board-level content analytics — none of which should require
    querying the wiki directly.

    The client handles all HTTP and OAuth. This class handles field mapping,
    idempotency, and result construction.

    Attributes:
        _client: A SFClientProtocol implementation.
        _object_type: Salesforce object API name.
    """

    DEFAULT_OBJECT_TYPE = "Content_Management__c"
    TEST_OBJECT_TYPE = "IMI_Pipeline_Test__c"

    def __init__(
        self,
        client: SFClientProtocol,
        object_type: str | None = None,
    ) -> None:
        """Initialise with an injectable Salesforce client."""
        self._client = client
        import os

        if object_type is None:
            mode = os.environ.get("IMI_PIPELINE_MODE", "production")
            object_type = (
                self.TEST_OBJECT_TYPE if mode == "stage" else self.DEFAULT_OBJECT_TYPE
            )
        self._object_type = object_type

    @property
    def name(self) -> str:
        """Outlet slug."""
        return "salesforce"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Create a Salesforce Content_Management__c record.

        Field mapping reflects the live schema discovered 2026-06-22:
        Name is auto-number (omitted), title goes to Headline__c,
        category to Observatory_Area__c, status to Observatory_wiki_Status__c,
        and the wiki link to Observatory_wiki_Site_Link__c.

        Idempotency checks Headline__c — not Name (which is auto-number
        and cannot be queried by title).

        Never raises — all errors captured in OutletResult.error.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=Salesforce_ID.
        """
        draft = event.draft
        observatory_url: str | None = draft.metadata.get("observatory_url")
        try:
            # Idempotency: check by Headline__c (Name is auto-number)
            if self._client.record_exists(
                self._object_type, "Headline__c", draft.title
            ):
                return OutletResult(
                    outlet=self.name,
                    succeeded=True,
                    artifact=draft.title,
                    metadata={"idempotent": "true"},
                )

            data: dict[str, str | bool] = {
                # Title → Headline__c (Name is auto-number, never set)
                "Headline__c": draft.title,
                # Required date field
                "Date_Received__c": date.today().isoformat(),
                # Category → Observatory_Area__c (was Category__c)
                "Observatory_Area__c": draft.category,
                # Status → Observatory_wiki_Status__c (was Status__c)
                "Observatory_wiki_Status__c": "Published",
                # Required boolean fields — all default False
                "Pay__c": False,
                "GTM_Site_Uploaded__c": False,
                "Translated__c": False,
                "Observatory_Classics__c": False,
            }
            if observatory_url:
                data["Observatory_wiki_Site_Link__c"] = observatory_url

            record = self._client.create_record(self._object_type, data)
            sf_id = record.get("Id", "")
            return OutletResult(
                outlet=self.name,
                succeeded=bool(sf_id),
                artifact=sf_id or None,
                error=None if sf_id else "No Id returned from Salesforce",
            )
        except Exception as exc:
            return OutletResult(
                outlet=self.name,
                succeeded=False,
                error=str(exc),
            )
