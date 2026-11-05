"""UrllibMWClient — MediaWiki bot auth client using stdlib only.

Uses ``urllib.request`` exclusively. No ``requests`` library. This is a
deliberate constraint: the client must work in any Python environment
without dependency management. ``stdlib`` is always available; ``requests``
requires a venv that may not exist in the target execution context —
particularly inside the Temporal worker container, where adding a
pip dependency means rebuilding the image and re-qualifying the test suite.

The stdlib constraint also eliminates version-conflict risk. ``requests``
pulls in ``urllib3``, ``certifi``, ``charset-normalizer``, and ``idna`` —
four transitive deps that can collide with other packages in the monorepo.
``urllib.request`` has zero transitive deps because it ships with Python.

Design principles:
    - stdlib only — no ``requests``, no external HTTP deps.
    - Never raises — all public methods return dicts; errors
      are captured in an ``{"error": ...}`` envelope.
    - Two-step login flow: ``action=login`` with ``lgtoken``.
    - CSRF token acquired via ``action=query&meta=tokens&type=csrf``.

Example::

    from phosphene.imi.clients.mediawiki import MWConfig, UrllibMWClient

    cfg = MWConfig.from_env()
    client = UrllibMWClient(cfg)
    client.login()
    csrf = client.get_csrf_token()
    result = client.create_page("My Page", "== Hello ==", summary="init")
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MWConfig:
    """Frozen configuration for connecting to a MediaWiki instance.

    Attributes:
        base_url: MediaWiki base URL (e.g. ``https://observatory.wiki``).
            Must NOT include a trailing slash or ``/w/api.php``.
        username: Bot username for ``action=login``.
        password: Bot password for ``action=login``.
    """

    base_url: str
    username: str
    password: str

    @classmethod
    def from_env(cls) -> MWConfig:
        """Construct from environment variables.

        Reads ``MW_BASE_URL``, ``MW_USERNAME``, ``MW_PASSWORD``.

        Returns:
            A populated :class:`MWConfig`.

        Raises:
            EnvironmentError: If any required variable is missing.
        """
        required = ("MW_BASE_URL", "MW_USERNAME", "MW_PASSWORD")
        missing = [v for v in required if v not in os.environ]
        if missing:
            raise OSError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls(
            base_url=os.environ["MW_BASE_URL"],
            username=os.environ["MW_USERNAME"],
            password=os.environ["MW_PASSWORD"],
        )


class UrllibMWClient:
    """MediaWiki Action API client using ``urllib.request``.

    Uses ``http.cookiejar.CookieJar`` for automatic session cookie
    management across the two-step login flow and subsequent API calls.

    Args:
        config: A :class:`MWConfig` instance with connection details.
    """

    def __init__(self, config: MWConfig) -> None:
        self._config = config
        self._api_url = f"{config.base_url}/w/api.php"
        self._csrf_token: str | None = None
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )

    def _post(self, params: dict[str, str]) -> dict[str, Any]:
        """Send a POST request to the MW API.

        Args:
            params: Form-encoded parameters for the API call.

        Returns:
            Parsed JSON response as a dict.
        """
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(self._api_url, data=data, method="POST")
        req.add_header("User-Agent", "PhospheneMWClient/1.0 (flow@ind.media)")
        with self._opener.open(req) as resp:
            return json.loads(resp.read())

    def login(self) -> dict[str, Any]:
        """Perform two-step MW bot login.

        Step 1: Fetch a login token via ``action=query&meta=tokens&type=login``.
        Step 2: Submit ``action=login`` with the token, username, and password.

        Returns:
            The API response dict. On success, contains
            ``{"login": {"result": "Success", ...}}``.
            On failure, returns an ``{"error": ...}`` dict.
        """
        try:
            # Step 1: get login token
            token_resp = self._post(
                {
                    "action": "query",
                    "meta": "tokens",
                    "type": "login",
                    "format": "json",
                }
            )
            login_token = token_resp["query"]["tokens"]["logintoken"]

            # Step 2: login with token
            return self._post(
                {
                    "action": "login",
                    "lgname": self._config.username,
                    "lgpassword": self._config.password,
                    "lgtoken": login_token,
                    "format": "json",
                }
            )
        except Exception as exc:
            return {"error": str(exc)}

    def get_csrf_token(self) -> str:
        """Fetch a CSRF (edit) token from the API.

        Must be called after :meth:`login`. The token is cached on the
        client for subsequent :meth:`create_page` calls.

        Returns:
            The CSRF token string (typically ends with ``+\\``).

        Raises:
            RuntimeError: If the token fetch fails.
        """
        try:
            resp = self._post(
                {
                    "action": "query",
                    "meta": "tokens",
                    "type": "csrf",
                    "format": "json",
                }
            )
            token = resp["query"]["tokens"]["csrftoken"]
            self._csrf_token = token
            return token
        except Exception as exc:
            raise RuntimeError(f"Failed to get CSRF token: {exc}") from exc

    def page_exists(self, title: str) -> bool:
        """Check whether a page exists on the wiki.

        Queries ``action=query&titles=<title>`` and checks whether any
        returned page has the ``missing`` key.

        Args:
            title: The page title to check.

        Returns:
            ``True`` if the page exists, ``False`` if missing or on error.
        """
        try:
            resp = self._post(
                {
                    "action": "query",
                    "titles": title,
                    "format": "json",
                }
            )
            pages = resp.get("query", {}).get("pages", {})
            return all("missing" not in page for page in pages.values())
        except Exception:
            return False

    def page_url(self, title: str) -> str:
        """Return the canonical URL for a page title.

        Replaces spaces with underscores per MediaWiki convention.

        Args:
            title: The page title.

        Returns:
            Full URL string, e.g. ``https://observatory.wiki/wiki/My_Page``.
        """
        return f"{self._config.base_url}/wiki/{title.replace(' ', '_')}"

    def create_page(
        self,
        title: str,
        content: str,
        summary: str = "",
        **kwargs: str,
    ) -> dict[str, Any]:
        """Create a new wiki page via ``action=edit`` with ``createonly``.

        Uses the cached CSRF token from :meth:`get_csrf_token`.
        If no token is cached, attempts to auto-acquire one.

        This method uses ``createonly=true`` — it will fail if the page
        already exists. Use :meth:`edit_page` to update existing pages.

        Never raises — returns an ``{"error": ...}`` dict on failure.

        Args:
            title: Page title to create.
            content: Wikitext content for the page body.
            summary: Edit summary for the revision log.
            **kwargs: Additional parameters passed to the API.

        Returns:
            The API response dict. On success contains
            ``{"edit": {"result": "Success", ...}}``.
        """
        try:
            token = self._csrf_token
            if token is None:
                token = self.get_csrf_token()

            params: dict[str, str] = {
                "action": "edit",
                "title": title,
                "text": content,
                "summary": summary,
                "token": token,
                "format": "json",
                "createonly": "true",
                **kwargs,
            }
            return self._post(params)
        except Exception as exc:
            return {"error": str(exc)}

    def edit_page(
        self,
        title: str,
        content: str,
        summary: str = "",
        **kwargs: str,
    ) -> dict[str, Any]:
        """Create or update a wiki page via ``action=edit``.

        Unlike :meth:`create_page`, this does NOT use ``createonly`` —
        it will create the page if it doesn't exist or update it if it does.
        This matches the behaviour expected by the ``ObservatoryPublisher``.

        Uses the cached CSRF token from :meth:`get_csrf_token`.
        If no token is cached, attempts to auto-acquire one.

        Never raises — returns an ``{"error": ...}`` dict on failure.

        Args:
            title: Page title to create or update.
            content: Wikitext content for the page body.
            summary: Edit summary for the revision log.
            **kwargs: Additional parameters passed to the API.

        Returns:
            The API response dict. On success contains
            ``{"edit": {"result": "Success", ...}}``.
        """
        try:
            token = self._csrf_token
            if token is None:
                token = self.get_csrf_token()

            params: dict[str, str] = {
                "action": "edit",
                "title": title,
                "text": content,
                "summary": summary,
                "token": token,
                "format": "json",
                **kwargs,
            }
            return self._post(params)
        except Exception as exc:
            return {"error": str(exc)}

    def delete_page(
        self,
        title: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Delete a wiki page via ``action=delete``.

        Used for saga compensation rollback.
        Uses the cached CSRF token from :meth:`get_csrf_token`.
        If no token is cached, attempts to auto-acquire one.

        Never raises — returns an ``{"error": ...}`` dict on failure.

        Args:
            title: Title of the page to delete.
            reason: Deletion summary for the logging table.

        Returns:
            The API response dict. On success contains
            ``{"delete": {"title": ..., ...}}``.
        """
        try:
            token = self._csrf_token
            if token is None:
                token = self.get_csrf_token()

            params: dict[str, str] = {
                "action": "delete",
                "title": title,
                "reason": reason,
                "token": token,
                "format": "json",
            }
            return self._post(params)
        except Exception as exc:
            return {"error": str(exc)}
