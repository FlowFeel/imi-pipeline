"""SalesforceOutlet — creates a Content_Management__c record on publish.

The outlet is decomposed into three separable concerns:

1. **Payload construction** — pure logic. ``SalesforceRecordFormatter``
   transforms a Draft into a Salesforce record payload. No I/O.
2. **Idempotency decision** — pure logic. Given whether a record exists,
   decide whether to create or return the existing artifact. No I/O.
3. **I/O execution** — the client protocol handles all HTTP.

Schema (discovered 2026-06-22 against live indmedia.my.salesforce.com):
Name is auto-number (not settable), title → Headline__c, category →
Observatory_Area__c, status → Observatory_wiki_Status__c.

The object type is injected at construction — no env var reads inside
the outlet. The caller (worker.py) decides production vs stage.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.formatters import SalesforceRecordFormatter
from phosphene.imi.outlets.base import PublicationOutlet
from phosphene.imi.protocols import SFClientProtocol


class SalesforceOutlet(PublicationOutlet):
    """Creates a Salesforce Content_Management__c record on article publish.

    Attributes:
        _client: A SFClientProtocol implementation.
        _object_type: Salesforce object API name.
        _formatter: Maps a Draft to a Salesforce record payload.
    """

    DEFAULT_OBJECT_TYPE = "Content_Management__c"
    TEST_OBJECT_TYPE = "IMI_Pipeline_Test__c"

    def __init__(
        self,
        client: SFClientProtocol,
        object_type: str | None = None,
        formatter: SalesforceRecordFormatter | None = None,
    ) -> None:
        """Initialise with an injectable Salesforce client.

        Args:
            client: Any object satisfying SFClientProtocol.
            object_type: Salesforce object API name. Defaults to
                DEFAULT_OBJECT_TYPE. Caller decides production vs stage.
            formatter: Record payload formatter. Defaults to
                SalesforceRecordFormatter.
        """
        self._client = client
        self._object_type = object_type or self.DEFAULT_OBJECT_TYPE
        self._formatter = formatter or SalesforceRecordFormatter()

    @property
    def name(self) -> str:
        """Outlet slug."""
        return "salesforce"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Create a Salesforce Content_Management__c record.

        Wires: format → idempotency check → I/O.
        Never raises — all errors captured in OutletResult.error.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=Salesforce_ID.
        """
        draft = event.draft
        observatory_url: str | None = draft.metadata.get("observatory_url")
        try:
            # Concern 1: I/O — check existence by Headline__c
            if self._client.record_exists(
                self._object_type, "Headline__c", draft.title
            ):
                # Concern 2: Idempotency decision — pure
                return OutletResult(
                    outlet=self.name,
                    succeeded=True,
                    artifact=draft.title,
                    metadata={"idempotent": "true"},
                )

            # Concern 3: Payload construction — pure
            data = self._formatter.format_payload(draft, observatory_url)

            # Concern 4: I/O — create record
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
