"""ObservatoryOutlet — publishes a Draft to observatory.wiki.

Observatory is the canonical scholarly home. WordPress hosts the IMI
Scholar Registry (metadata, author profiles); Salesforce tracks the
content management record for fundraising and reporting. But the
article itself — the full text, the wikitext markup, the editorial
structure — lives on observatory.wiki. This outlet is the one that
places the intellectual content where readers find it.

The outlet is decomposed into three separable concerns:

1. **Payload construction** — pure logic. ``ObservatoryWikitextFormatter``
   transforms a Draft into wikitext. No I/O, testable in isolation.
2. **Idempotency decision** — pure logic. Given whether a page exists,
   decide whether to create or return the existing URL. No I/O.
3. **I/O execution** — the client protocol handles all HTTP. The outlet
   wires the decision to the client and constructs the result.

This separation means each concern is independently testable:
- Formatter: ``assert formatter.format_wikitext(draft) == expected_wikitext``
- Idempotency: ``assert decide_idempotent(True, url) == OutletResult(...)``
- I/O: inject a fake client, assert the right methods were called.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.formatters import ObservatoryWikitextFormatter
from phosphene.imi.outlets.base import PublicationOutlet
from phosphene.imi.protocols import MWClientProtocol


class ObservatoryOutlet(PublicationOutlet):
    """Publishes a draft article to observatory.wiki via the MW API.

    The outlet wires three concerns: formatting (pure), idempotency
    (pure), and I/O (protocol). Each concern is independently testable.

    Attributes:
        _client: A MWClientProtocol implementation.
        _formatter: Transforms a Draft into wikitext.
    """

    def __init__(
        self,
        client: MWClientProtocol,
        formatter: ObservatoryWikitextFormatter | None = None,
    ) -> None:
        """Initialise with an injectable MW client and optional formatter.

        Args:
            client: Any object satisfying MWClientProtocol.
            formatter: Wikitext formatter. Defaults to
                ObservatoryWikitextFormatter. Inject a custom one for
                testing or alternative template formats.
        """
        self._client = client
        self._formatter = formatter or ObservatoryWikitextFormatter()

    @property
    def name(self) -> str:
        """Outlet slug."""
        return "observatory"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Publish the draft to observatory.wiki.

        Wires the three concerns: format → idempotency check → I/O.
        Never raises — all errors are captured in OutletResult.error.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=URL on success.
        """
        draft = event.draft
        try:
            # Concern 1: I/O — check existence
            if self._client.page_exists(draft.title):
                # Concern 2: Idempotency decision — pure
                return self._idempotent_result(draft.title)

            # Concern 3: Payload construction — pure
            content = self._formatter.format_wikitext(draft)

            # Concern 4: I/O — create page
            result = self._client.create_page(
                title=draft.title,
                content=content,
                summary=f"Published by Flow — {event.publisher_id}",
            )
            url = result.get("url", self._client.page_url(draft.title))
            return OutletResult(
                outlet=self.name,
                succeeded=True,
                artifact=url,
            )
        except Exception as exc:
            return OutletResult(
                outlet=self.name,
                succeeded=False,
                error=str(exc),
            )

    def _idempotent_result(self, title: str) -> OutletResult:
        """Construct an idempotent-skip result.

        Pure: given that a page exists, build the result without
        making any additional I/O calls beyond the URL lookup.

        Args:
            title: The page title that already exists.

        Returns:
            OutletResult marking the publish as idempotent.
        """
        url = self._client.page_url(title)
        return OutletResult(
            outlet=self.name,
            succeeded=True,
            artifact=url,
            metadata={"idempotent": "true"},
        )
