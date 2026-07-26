"""RealMWClient — MediaWiki API client for integration tests.

Implements MWClientProtocol. All page creation is forced to
namespace_prefix — enforced in _safe_title(), not optional.

Designed for Tier 2 (wire-level mock) and Tier 3 (container) tests.
Never used against production observatory.wiki — only against mock
servers or the observatory-magazine-v2 container stack.

Hard lock: namespace_prefix enforcement prevents main-namespace writes.
If _safe_title() is bypassed, the client will still prefix any title
that doesn't already carry the prefix.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import contextlib
import json
import urllib.parse
import urllib.request
from typing import Any


class RealMWClient:
    """MediaWiki API client for integration tests.

    Implements MWClientProtocol. All page creation is forced to
    ``namespace_prefix`` — enforced in ``_safe_title()``.

    Uses urllib — no external HTTP library dependency.

    Args:
        base_url: MW API base URL, e.g. ``http://localhost:8080/w``.
        bot_username: Bot account username.
        bot_password: Bot account password.
        namespace_prefix: Namespace to force all page titles into.
            Default: ``"Draft"``. Cannot be overridden per-call.
    """

    def __init__(
        self,
        base_url: str,
        bot_username: str,
        bot_password: str,
        namespace_prefix: str = "Draft",
    ) -> None:
        """Initialise the client.

        Args:
            base_url: MW API base URL.
            bot_username: Bot account username.
            bot_password: Bot account password.
            namespace_prefix: Namespace prefix enforced on all page titles.
        """
        self.base_url = base_url.rstrip("/")
        self._username = bot_username
        self._password = bot_password
        self.namespace_prefix = namespace_prefix
        self._token: str = ""
        self._session_pages: list[str] = []

    # ------------------------------------------------------------------
    # Namespace enforcement
    # ------------------------------------------------------------------

    def _safe_title(self, title: str) -> str:
        """Ensure title is in namespace_prefix. Enforced, not optional.

        Args:
            title: Raw page title.

        Returns:
            Title prefixed with ``namespace_prefix:`` if not already prefixed.
        """
        prefix = f"{self.namespace_prefix}:"
        if title.startswith(prefix):
            return title
        return f"{prefix}{title}"

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _api_url(self) -> str:
        """Return the full API URL."""
        return f"{self.base_url}/api.php"

    def _post(self, **params: Any) -> dict[str, Any]:
        """Make a POST request to the MW API.

        Args:
            **params: Form parameters for the request.

        Returns:
            Parsed JSON response.
        """
        params["format"] = "json"
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(self._api_url(), data=data, method="POST")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def _get(self, **params: Any) -> dict[str, Any]:
        """Make a GET request to the MW API.

        Args:
            **params: Query parameters.

        Returns:
            Parsed JSON response.
        """
        params["format"] = "json"
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{self._api_url()}?{qs}")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def _login(self) -> None:
        """Authenticate and store the CSRF token."""
        # Step 1: get login token
        r = self._get(action="query", meta="tokens", type="login")
        login_token = r["query"]["tokens"]["logintoken"]
        # Step 2: login
        self._post(
            action="login",
            lgname=self._username,
            lgpassword=self._password,
            lgtoken=login_token,
        )
        # Step 3: get CSRF token
        r2 = self._get(action="query", meta="tokens")
        self._token = r2["query"]["tokens"]["csrftoken"]

    # ------------------------------------------------------------------
    # MWClientProtocol
    # ------------------------------------------------------------------

    def create_page(
        self,
        title: str,
        content: str,
        summary: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a page in the namespace_prefix namespace.

        Args:
            title: Page title (namespace prefix enforced).
            content: Wikitext content.
            summary: Edit summary.
            **kwargs: Additional parameters.

        Returns:
            MW API edit response dict.
        """
        if not self._token:
            self._login()
        safe = self._safe_title(title)
        result = self._post(
            action="edit",
            title=safe,
            text=content,
            token=self._token,
            createonly="1",
            summary=summary or f"Integration test — {safe}",
        )
        if hasattr(self, "_session_pages"):
            self._session_pages.append(safe)
        return result

    def page_exists(self, title: str) -> bool:
        """Check if a page exists in the namespace_prefix namespace.

        Args:
            title: Page title.

        Returns:
            True if the page exists.
        """
        safe = self._safe_title(title)
        r = self._get(action="query", titles=safe)
        pages = r.get("query", {}).get("pages", {})
        return next(iter(pages.keys())) != "-1"

    def page_url(self, title: str) -> str:
        """Return a URL for a page.

        Args:
            title: Page title.

        Returns:
            URL string for the page.
        """
        safe = self._safe_title(title)
        base = self.base_url.rstrip("/w")
        return f"{base}/wiki/{safe.replace(' ', '_')}"

    def delete_page(self, title: str, reason: str = "Integration test cleanup") -> None:
        """Delete a page via the MW API.

        Args:
            title: Page title to delete.
            reason: Edit summary for the deletion.
        """
        if not self._token:
            self._login()
        safe = self._safe_title(title)
        self._post(
            action="delete",
            title=safe,
            token=self._token,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Session tracking (for fixture cleanup)
    # ------------------------------------------------------------------

    def begin_session(self) -> None:
        """Start tracking pages created in this test session."""
        self._session_pages = []

    def purge_session(self) -> None:
        """Delete only pages created during this session."""
        for title in list(self._session_pages):
            with contextlib.suppress(Exception):
                self.delete_page(title)
        self._session_pages = []
