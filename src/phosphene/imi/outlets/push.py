"""PushOutlet -- pushes an existing editorial article to the magazine wiki.

The MW Push extension replicates pages from editorial to magazine.
This outlet fires AFTER the article exists on editorial.

Idempotency and verification both use mwclient.page.exists -- a deterministic
property on the mwclient.Page object. The same property serves both purposes:
check before push (skip if already there) and check after push (verify arrival).

magazine_site is injected separately from push_client because verification
is a READ operation on the TARGET, while push is a WRITE on the SOURCE.
Different wikis, different credentials, different concerns.
"""

from __future__ import annotations

import mwclient

from phosphene.imi.clients.push_client import PushClient
from phosphene.imi.event import OutletResult, PublicationEvent
from phosphene.imi.outlets.base import PublicationOutlet


class PushOutlet(PublicationOutlet):
    """Outlet that uses the MW Push extension to replicate pages.

    Args:
        push_client: PushClient connected to the editorial (source) wiki.
        magazine_site: mwclient.Site connected to the magazine (target) wiki.
    """

    def __init__(self, push_client: PushClient, magazine_site: mwclient.Site) -> None:
        self._push_client = push_client
        self._magazine_site = magazine_site

    @property
    def name(self) -> str:
        """Short slug identifying this outlet."""
        return "push"

    def publish(self, event: PublicationEvent) -> OutletResult:
        """Push the article to the magazine wiki.

        Idempotent: if the page already exists on the magazine, returns
        success with metadata indicating no push was needed.

        Verifies arrival after push by checking page.exists on target.

        Args:
            event: The publication event carrying the draft.

        Returns:
            OutletResult with succeeded=True and artifact=URL on success.
        """
        title = event.draft.title
        page = self._magazine_site.pages[title]

        if page.exists:
            return OutletResult(
                outlet=self.name,
                succeeded=True,
                artifact=page.full_url(),
                metadata={"idempotent": "true"},
            )

        result = self._push_client.push_page(title)
        if not result.succeeded:
            return OutletResult(outlet=self.name, succeeded=False, error=result.error)

        # Re-fetch to verify arrival
        page = self._magazine_site.pages[title]
        if not page.exists:
            return OutletResult(
                outlet=self.name,
                succeeded=False,
                error="Push reported success but page not found on magazine",
            )

        return OutletResult(outlet=self.name, succeeded=True, artifact=page.full_url())
