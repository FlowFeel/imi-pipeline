"""ObservatoryPublisher — creates/edits wiki pages on observatory.wiki.

The publisher is the adapter between the Draft model and the
MediaWiki action API. It authenticates via bot password, obtains
a CSRF token, and uses action=edit to create or update articles.

Dry-run mode is available for BDD testing without a live API.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from phosphene.imi.draft import Draft

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """Raised when the MW API returns an error during publish."""


class ObservatoryPublisher:
    """Publishes Draft articles to observatory.wiki via the MW action API.

    The publish flow:
      1. Login with bot credentials (action=login)
      2. Obtain CSRF edit token (action=query&meta=tokens)
      3. Create or edit the wiki page (action=edit)
      4. Return the canonical URL

    Attributes:
        api_url: The MediaWiki API endpoint (e.g. https://observatory.wiki/w/api.php).
        username: Bot username for MW login.
        password: Bot password for MW login.
        dry_run: If True, skip all API calls and return the expected URL.
    """

    def __init__(
        self,
        api_url: str,
        username: str,
        password: str,
        *,
        dry_run: bool = False,
    ) -> None:
        """Initialise with MW API URL and bot credentials.

        Args:
            api_url: Full URL to the MW api.php endpoint.
            username: Bot login username.
            password: Bot login password.
            dry_run: If True, construct the URL without hitting the API.
        """
        self.api_url = api_url.rstrip("/")
        self.username = username
        self.password = password
        self.dry_run = dry_run
        self._wiki_base_url = self._derive_wiki_base(self.api_url)
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )

    @staticmethod
    def _derive_wiki_base(api_url: str) -> str:
        """Derive the wiki page base URL from the API URL.

        Strips the ``/w/api.php`` (or ``/api.php``) suffix and appends
        ``/wiki/``. For example:
            ``https://observatory.wiki/w/api.php`` → ``https://observatory.wiki/wiki/``

        Args:
            api_url: Full URL to the MW api.php endpoint.

        Returns:
            Base URL for wiki page links, with trailing slash.
        """
        base = api_url
        for suffix in ("/w/api.php", "/api.php"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return f"{base}/wiki/"

    def publish(self, draft: Draft) -> str:
        """Create or edit a wiki page for the given draft.

        If the page already exists, it is updated (idempotent).
        In dry_run mode, no API call is made — the URL is constructed
        from the title and returned directly.

        Args:
            draft: The finished article draft to publish.

        Returns:
            The canonical URL of the published article on observatory.wiki.

        Raises:
            PublishError: If the MW API returns an error.
        """
        title_with_underscores = draft.title.replace(" ", "_")
        canonical_url = f"{self._wiki_base_url}{title_with_underscores}"

        if self.dry_run:
            logger.info("DRY RUN: would publish '%s' → %s", draft.title, canonical_url)
            return canonical_url

        self._login()
        csrf_token = self._get_csrf_token()
        self._edit_page(
            title=draft.title,
            text=draft.body,
            token=csrf_token,
            summary=f"Published by Flow: {draft.title}",
        )

        logger.info("Published '%s' → %s", draft.title, canonical_url)
        return canonical_url

    def _api_post(self, params: dict[str, str]) -> dict:
        """POST to the MW API and return parsed JSON.

        Args:
            params: Form-encoded parameters for the API call.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            PublishError: If the request fails or returns non-JSON.
        """
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(
            self.api_url,
            data=data,
            headers={"User-Agent": "phosphene-imi/1.0"},
        )
        try:
            with self._opener.open(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            return json.loads(body)
        except Exception as exc:
            raise PublishError(f"MW API request failed: {exc}") from exc

    def _api_get(self, params: dict[str, str]) -> dict:
        """GET from the MW API and return parsed JSON.

        Args:
            params: Query-string parameters for the API call.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            PublishError: If the request fails or returns non-JSON.
        """
        qs = urllib.parse.urlencode({**params, "format": "json"})
        url = f"{self.api_url}?{qs}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "phosphene-imi/1.0"},
        )
        try:
            with self._opener.open(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            return json.loads(body)
        except Exception as exc:
            raise PublishError(f"MW API request failed: {exc}") from exc

    def _login(self) -> None:
        """Authenticate with the MW API using bot credentials.

        Two-step login: first GET a login token, then POST with credentials.

        Raises:
            PublishError: If login fails.
        """
        # Step 1: Get login token
        token_resp = self._api_get({
            "action": "query",
            "meta": "tokens",
            "type": "login",
        })
        login_token = token_resp.get("query", {}).get("tokens", {}).get("logintoken")
        if not login_token:
            raise PublishError(f"No login token in response: {token_resp}")

        # Step 2: POST login
        login_resp = self._api_post({
            "action": "login",
            "lgname": self.username,
            "lgpassword": self.password,
            "lgtoken": login_token,
            "format": "json",
        })
        result = login_resp.get("login", {}).get("result")
        if result != "Success":
            raise PublishError(
                f"MW login failed: {login_resp.get('login', {}).get('reason', result)}"
            )
        logger.debug("Logged in as %s", self.username)

    def _get_csrf_token(self) -> str:
        """Obtain a CSRF edit token from the MW API.

        Must be called after _login() — the session cookies carry auth.

        Returns:
            The CSRF token string.

        Raises:
            PublishError: If the token cannot be obtained.
        """
        resp = self._api_get({
            "action": "query",
            "meta": "tokens",
            "type": "csrf",
        })
        token = resp.get("query", {}).get("tokens", {}).get("csrftoken")
        if not token:
            raise PublishError(f"No CSRF token in response: {resp}")
        return token

    def _edit_page(
        self,
        title: str,
        text: str,
        token: str,
        summary: str,
    ) -> None:
        """Create or edit a wiki page.

        Uses action=edit which is idempotent: if the page exists it is
        updated; if it does not exist it is created.

        Args:
            title: Page title.
            text: Full page content (wikitext).
            token: CSRF edit token.
            summary: Edit summary.

        Raises:
            PublishError: If the edit API returns an error.
        """
        resp = self._api_post({
            "action": "edit",
            "title": title,
            "text": text,
            "token": token,
            "summary": summary,
            "bot": "1",
            "format": "json",
        })
        edit_result = resp.get("edit", {})
        if edit_result.get("result") != "Success":
            error = resp.get("error", {})
            raise PublishError(
                f"MW edit failed for '{title}': "
                f"{error.get('info', edit_result)}"
            )
        logger.debug(
            "Page '%s' %s",
            title,
            "created" if edit_result.get("new") else "updated",
        )
