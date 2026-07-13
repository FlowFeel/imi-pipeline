"""WordPressOutlet — creates an imi_registry entry on the IMI WordPress site.

Accepts a WPClientProtocol at construction. Creates an imi_registry
post from the PublicationEvent and returns an OutletResult with the
entry URL.

Idempotency is enforced at the outlet level, not the caller's. The
caller should never need to check whether a post already exists before
calling ``publish()`` — that check is the outlet's responsibility.
Pushing idempotency up to the caller creates a TOCTOU race (check,
then create) and distributes dedup logic across every callsite.
Keeping it inside the outlet makes the guarantee structural.

Slug-based dedup, not title-based: WordPress URLs are slug-stable,
titles are display-mutable. Two posts can share a title; no two
posts share a slug within a CPT. The slug is the identity key for
the Scholar Registry — it determines the canonical URL that other
systems (Salesforce, Observatory) link to.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.outlets.base import PublicationOutlet
from phosphene.imi.protocols import WPClientProtocol


class WordPressOutlet(PublicationOutlet):
    """Creates an IMI Scholar Registry entry on independentmediainstitute.org.

    Idempotency lives here because the outlet owns the write. The caller
    says "publish this" and gets back a result — never "check first, then
    publish." If the entry already exists, the outlet returns the existing
    URL with ``metadata={"idempotent": "true"}`` so the saga knows no
    compensation is needed for this step.

    Attributes:
        _client: A WPClientProtocol implementation.
        _post_type: The WordPress CPT slug (default: imi_registry).
    """

    def __init__(
        self,
        client: WPClientProtocol,
        post_type: str = "imi_registry",
    ) -> None:
        """Initialise with an injectable WP client."""
        self._client = client
        self._post_type = post_type

    @property
    def name(self) -> str:
        """Outlet slug."""
        return "wordpress"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Create an imi_registry entry for this publication event.

        If an entry with this slug already exists, returns existing URL.
        Never raises — all errors captured in OutletResult.error.

        Uses ``draft.slug`` — the canonical slug computed by the Draft
        model — instead of a local slugify. Draft.slug strips non-ASCII
        characters (em-dashes, curly quotes, accents) via regex, matching
        WordPress's ``sanitize_title_with_dashes()`` behavior. A local
        slugify that preserves non-ASCII would create TOCTOU mismatches:
        the outlet sends ``café-culture`` but WP stores ``caf-culture``,
        breaking idempotency on second publish.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=entry_url.
        """
        draft = event.draft
        slug = draft.slug
        try:
            if self._client.post_exists(self._post_type, slug):
                url = self._client.post_url(self._post_type, slug)
                return OutletResult(
                    outlet=self.name,
                    succeeded=True,
                    artifact=url,
                    metadata={"idempotent": "true"},
                )

            post = self._client.create_post(
                post_type=self._post_type,
                data={
                    "title": draft.title,
                    "slug": slug,
                    "status": "publish",
                    "meta": {
                        "author_name": draft.author,
                        "category": draft.category,
                        "source_url": draft.source_url or "",
                    },
                },
            )
            url = post.get("url", self._client.post_url(self._post_type, slug))
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

    @staticmethod
    def _slugify(title: str) -> str:
        """Convert a title to a URL-safe slug.

        .. deprecated::
            Retained for backward compatibility. New code should use
            ``Draft.slug`` which handles non-ASCII correctly via regex.
        """
        return title.lower().replace(" ", "-")[:80]
