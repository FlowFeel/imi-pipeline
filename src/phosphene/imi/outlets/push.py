"""PushOutlet — pushes an existing editorial article to the magazine wiki.

The MW Push extension replicates pages from editorial to magazine.
This outlet fires AFTER the article exists on editorial.

Decomposed into three concerns:

1. **Idempotency decision** — pure: given whether the page exists on
   the target, decide whether to push or return the existing URL.
2. **I/O execution** — delegated to protocols. ``PushClientProtocol``
   handles the push write. ``MagazineClientProtocol`` handles the
   read (existence check + URL).
3. **Verification** — pure: given that the page now exists, construct
   the success result.

The magazine site is behind a protocol (``MagazineClientProtocol``)
so the outlet is testable without ``mwclient`` or a real wiki.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from phosphene.imi.clients.push_client import PushClient
from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.outlets.base import PublicationOutlet


@runtime_checkable
class MagazineClientProtocol(Protocol):
    """Minimal interface for checking page state on the magazine (target) wiki.

    This is the READ side of the push operation. The WRITE side is
    ``PushClient`` on the editorial (source) wiki.
    """

    def page_exists(self, title: str) -> bool:
        """True if a page with this title exists on the magazine wiki."""
        ...

    def page_url(self, title: str) -> str:
        """Canonical URL for a page title on the magazine wiki."""
        ...


class PushOutlet(PublicationOutlet):
    """Outlet that uses the MW Push extension to replicate pages.

    Args:
        push_client: PushClient connected to the editorial (source) wiki.
        magazine_client: Any object satisfying MagazineClientProtocol
            for the magazine (target) wiki.
    """

    def __init__(
        self,
        push_client: PushClient,
        magazine_client: MagazineClientProtocol,
    ) -> None:
        self._push_client = push_client
        self._magazine = magazine_client

    @property
    def name(self) -> str:
        """Short slug identifying this outlet."""
        return "push"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Push the article to the magazine wiki.

        Idempotent: if the page already exists on the magazine, returns
        success with metadata indicating no push was needed.

        Verifies arrival after push by re-checking existence on target.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=URL on success.
        """
        title = event.draft.title
        try:
            # Concern 1: Idempotency — check existence on target
            if self._magazine.page_exists(title):
                return self._idempotent_result(title)

            # Concern 2: I/O — push to source wiki
            result = self._push_client.push_page(title)
            if not result.succeeded:
                return OutletResult(
                    outlet=self.name,
                    succeeded=False,
                    error=result.error,
                )

            # Concern 3: Verification — re-check existence on target
            if not self._magazine.page_exists(title):
                return OutletResult(
                    outlet=self.name,
                    succeeded=False,
                    error="Push reported success but page not found on magazine",
                )

            return OutletResult(
                outlet=self.name,
                succeeded=True,
                artifact=self._magazine.page_url(title),
            )
        except Exception as exc:
            return OutletResult(
                outlet=self.name,
                succeeded=False,
                error=str(exc),
            )

    def _idempotent_result(self, title: str) -> OutletResult:
        """Construct an idempotent-skip result.

        Args:
            title: The page title that already exists on the target.

        Returns:
            OutletResult marking the push as idempotent.
        """
        return OutletResult(
            outlet=self.name,
            succeeded=True,
            artifact=self._magazine.page_url(title),
            metadata={"idempotent": "true"},
        )
