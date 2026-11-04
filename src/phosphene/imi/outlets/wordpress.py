"""WordPressOutlet — creates an imi_registry entry on the IMI WordPress site.

The outlet is decomposed into three separable concerns:

1. **Payload construction** — pure logic. ``WordPressPostFormatter``
   transforms a Draft into a WordPress post payload. No I/O.
2. **Idempotency decision** — pure logic. Given whether a post exists,
   decide whether to create or return the existing URL. No I/O.
3. **I/O execution** — the client protocol handles all HTTP.

Slug-based dedup, not title-based: WordPress URLs are slug-stable,
titles are display-mutable. The slug is the identity key for the
Scholar Registry.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi_wordpress.adapters import PreprintPayloadAdapter

from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.formatters import WordPressPostFormatter
from phosphene.imi.outlets.base import PublicationOutlet
from phosphene.imi.protocols import WPClientProtocol
from phosphene.imi.work import ArticleDraft, PreprintWork


class WordPressOutlet(PublicationOutlet):
    """Creates an IMI Scholar Registry entry on independentmediainstitute.org.

    Attributes:
        _client: A WPClientProtocol implementation.
        _post_type: The WordPress CPT slug (default: imi_registry).
        _formatter: Maps a Draft to a WordPress post payload.
    """

    def __init__(
        self,
        client: WPClientProtocol,
        post_type: str = "imi_registry",
        formatter: WordPressPostFormatter | None = None,
    ) -> None:
        """Initialise with an injectable WP client and optional formatter.

        Args:
            client: Any object satisfying WPClientProtocol.
            post_type: WordPress CPT slug.
            formatter: Post payload formatter. Defaults to
                WordPressPostFormatter. Inject a custom one for testing.
        """
        self._client = client
        self._post_type = post_type
        self._formatter = formatter or WordPressPostFormatter()

    @property
    def name(self) -> str:
        """Outlet slug."""
        return "wordpress"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Create an imi_registry entry for this publication event.

        Wires: format → idempotency check → I/O.
        Never raises — all errors captured in OutletResult.error.

        Uses ``draft.slug`` — the canonical slug computed by the Draft
        model — matching WordPress's ``sanitize_title_with_dashes()``.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=entry_url.
        """
        work = event.work
        slug = work.slug
        try:
            # Concern 1: I/O — check existence
            if self._client.post_exists(self._post_type, slug):
                # Concern 2: Idempotency decision — pure
                return self._idempotent_result(self._post_type, slug)

            # Concern 3: Payload construction — pure pattern matching
            match work:
                case PreprintWork():
                    payload = dict(
                        PreprintPayloadAdapter.to_wordpress(work.to_preprint_entry())
                    )
                case ArticleDraft():
                    payload = self._formatter.format_payload(work)
                case _:
                    payload = self._formatter.format_payload(event.draft)

            # Concern 4: I/O — create post
            post = self._client.create_post(
                post_type=self._post_type,
                data=payload,
            )
            url = post.get("url", self._client.post_url(self._post_type, slug))
            post_id = str(post.get("id", ""))
            return OutletResult(
                outlet=self.name,
                succeeded=True,
                artifact=url,
                metadata={"post_id": post_id} if post_id else {},
            )
        except Exception as exc:
            return OutletResult(
                outlet=self.name,
                succeeded=False,
                error=str(exc),
            )

    def _idempotent_result(self, post_type: str, slug: str) -> OutletResult:
        """Construct an idempotent-skip result.

        Pure: given that a post exists, build the result.

        Args:
            post_type: The WordPress CPT slug.
            slug: The post slug that already exists.

        Returns:
            OutletResult marking the publish as idempotent.
        """
        url = self._client.post_url(post_type, slug)
        return OutletResult(
            outlet=self.name,
            succeeded=True,
            artifact=url,
            metadata={"idempotent": "true"},
        )
