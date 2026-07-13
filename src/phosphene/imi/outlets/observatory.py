"""ObservatoryOutlet — publishes a Draft to observatory.wiki.

Observatory is the canonical scholarly home. WordPress hosts the IMI
Scholar Registry (metadata, author profiles); Salesforce tracks the
content management record for fundraising and reporting. But the
article itself — the full text, the wikitext markup, the editorial
structure — lives on observatory.wiki. This outlet is the one that
places the intellectual content where readers find it.

Accepts a MWClientProtocol at construction. Creates a MediaWiki page
from the Draft content and returns an OutletResult with the live URL.

Idempotent: if a page with this title already exists, the existing
URL is returned without creating a duplicate.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.outlets.base import PublicationOutlet
from phosphene.imi.protocols import MWClientProtocol


class ObservatoryOutlet(PublicationOutlet):
    """Publishes a draft article to observatory.wiki via the MW API.

    Observatory is the canonical scholarly home for published content.
    The client handles all HTTP. This class handles all business logic:
    wikitext formatting, idempotency, result construction.

    Attributes:
        _client: A MWClientProtocol implementation.
    """

    def __init__(self, client: MWClientProtocol) -> None:
        """Initialise with an injectable MW client."""
        self._client = client

    @property
    def name(self) -> str:
        """Outlet slug."""
        return "observatory"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Publish the draft to observatory.wiki.

        If the page already exists, returns the existing URL (idempotent).
        Never raises — all errors are captured in OutletResult.error.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=URL on success.
        """
        draft = event.draft
        try:
            if self._client.page_exists(draft.title):
                url = self._client.page_url(draft.title)
                return OutletResult(
                    outlet=self.name,
                    succeeded=True,
                    artifact=url,
                    metadata={"idempotent": "true"},
                )

            content = self._build_wikitext(draft)
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

    def _build_wikitext(self, draft: object) -> str:
        """Build wikitext from the Draft using the ``{{Article|...}}`` template.

        The ``{{Article}}`` template is the structural contract between the
        publish pipeline and the Observatory skin. It carries structured
        metadata (headline, author, section) in a machine-parseable format
        that the skin renders into the article chrome. Without the template,
        the article is raw wikitext with no author attribution, no section
        navigation, and no structured data for the Almanac scraper.

        Minimal implementation for the tracer bullet.
        Full template injection to follow.

        Args:
            draft: The Draft to convert.

        Returns:
            Wikitext string suitable for MW page creation.
        """
        from phosphene.imi.draft import Draft

        assert isinstance(draft, Draft)
        return (
            f"{{{{Article|Headline={draft.title}"
            f"|Author={draft.author}"
            f"|Section={draft.category}}}}}\n\n"
            f"{draft.body}"
        )
