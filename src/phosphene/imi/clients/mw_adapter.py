"""MWClientAdapter — mwclient-based MediaWiki adapter.

mwclient handles the messy parts of MediaWiki interaction: login token
negotiation, CSRF token management, cookie persistence, retry on transient
HTTP errors, and multipart file uploads. It presents pages as Python objects
with ``.exists``, ``.edit()``, and URL properties.

This adapter translates between the mwclient object model and the
:class:`~phosphene.imi.protocols.MWClientProtocol` structural interface.
The adapter adds no HTTP logic — it delegates entirely to mwclient and
transforms return values into the dict/bool/str shapes the protocol demands.

Why mwclient over raw urllib?
    The existing :class:`~phosphene.imi.clients.mediawiki.UrllibMWClient`
    exists for zero-dependency contexts (Temporal worker containers).
    For the push pipeline running in the main workspace, mwclient provides
    automatic session management, proper redirect handling, and tested
    edge-case coverage (e.g., maxlag retry, token refresh on expiry).

Connection factory:
    :func:`connect_mwclient` parses a base URL into the host/path/scheme
    triple that mwclient expects, creates a Site, and logs in. Returns
    a live Site instance ready for adapter wrapping.

Example::

    from phosphene.imi.clients.mw_adapter import connect_mwclient, MWClientAdapter

    site = connect_mwclient("http://localhost:8085/w", "Bot", "secret")
    adapter = MWClientAdapter(site, base_url="http://localhost:8085/w")
    if not adapter.page_exists("My Page"):
        adapter.create_page("My Page", "== Hello ==", summary="init")
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import mwclient


def connect_mwclient(
    base_url: str,
    username: str,
    password: str,
) -> mwclient.Site:
    """Create and authenticate an mwclient.Site from a base URL.

    Parses the base URL into components mwclient expects:
    - **host**: ``hostname:port`` (port omitted if default for scheme)
    - **path**: URL path with trailing slash (e.g. ``/w/``)
    - **scheme**: ``http`` or ``https``

    Args:
        base_url: MediaWiki script path URL (e.g. ``http://localhost:8085/w``).
        username: Bot username for login.
        password: Bot password for login.

    Returns:
        An authenticated :class:`mwclient.Site` instance.
    """
    parsed = urlparse(base_url)
    scheme = parsed.scheme or "http"

    # mwclient wants host as "hostname:port" (no scheme)
    host = parsed.hostname or "localhost"
    if parsed.port and parsed.port not in (80, 443):
        host = f"{host}:{parsed.port}"

    # Path must end with /
    path = parsed.path
    if not path.endswith("/"):
        path = f"{path}/"

    site = mwclient.Site(host, path=path, scheme=scheme)
    site.login(username, password)
    return site


class MWClientAdapter:
    """Adapter from mwclient.Site to MWClientProtocol.

    Wraps a live mwclient Site and translates its object-oriented page
    model into the dict/bool/str protocol the pipeline outlets expect.

    Args:
        site: An authenticated :class:`mwclient.Site`.
        base_url: The base URL used to construct canonical page URLs
            as a fallback when mwclient's URL methods are unavailable.
    """

    def __init__(self, site: mwclient.Site, base_url: str) -> None:
        self._site = site
        self._base_url = base_url.rstrip("/")

    def page_exists(self, title: str) -> bool:
        """Check whether a page exists on the wiki.

        Delegates to the mwclient Page ``.exists`` property which queries
        the API internally.

        Args:
            title: The page title to check.

        Returns:
            ``True`` if the page exists, ``False`` otherwise.
        """
        return bool(self._site.pages[title].exists)

    def page_url(self, title: str) -> str:
        """Return the canonical URL for a page.

        Uses the mwclient Page object's ``page_url`` attribute if available.

        Args:
            title: The page title.

        Returns:
            Full URL string for the page.
        """
        page = self._site.pages[title]
        return page.page_url

    def create_page(
        self,
        title: str,
        content: str,
        summary: str = "",
        **kwargs: str,
    ) -> dict[str, Any]:
        """Create or overwrite a wiki page.

        Calls ``page.edit(content, summary)`` on the mwclient Page object.
        mwclient handles CSRF token acquisition and retry internally.

        Args:
            title: Page title to create.
            content: Wikitext content for the page body.
            summary: Edit summary for the revision log.
            **kwargs: Reserved for future use.

        Returns:
            Dict with at minimum a ``url`` key pointing to the created page.
        """
        page = self._site.pages[title]
        page.edit(content, summary)
        return {"url": self.page_url(title), "title": title}

    def delete_page(self, title: str, reason: str = "") -> None:
        """Delete a wiki page via mwclient.

        Used for saga compensation rollback.

        Args:
            title: Page title to delete.
            reason: Reason for deletion.
        """
        page = self._site.pages[title]
        page.delete(reason=reason)
