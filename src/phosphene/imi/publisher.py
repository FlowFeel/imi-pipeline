"""ObservatoryPublisher — DEPRECATED.

This module is deprecated. It duplicates ``UrllibMWClient`` — same
login flow, same CSRF acquisition, same edit API. The only unique
feature is dry-run mode, which is better handled by injecting a
``FakeMWClient`` into ``ObservatoryOutlet``.

Migration path:
    - BDD steps: use ``ObservatoryOutlet`` with ``FakeMWClient``
    - URL derivation: use ``UrllibMWClient.page_url()``
    - Dry-run: use ``FakeMWClient`` (returns deterministic URLs)

This module will be removed once BDD steps are migrated.
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
    """DEPRECATED — use ObservatoryOutlet + UrllibMWClient instead.

    Kept only for BDD step compatibility during migration.
    """

    def __init__(
        self,
        api_url: str,
        username: str,
        password: str,
        *,
        dry_run: bool = False,
    ) -> None:
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
        """Derive the wiki page base URL from the API URL."""
        base = api_url
        for suffix in ("/w/api.php", "/api.php"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return f"{base}/wiki/"

    def publish(self, draft: Draft) -> str:
        """Create or edit a wiki page for the given draft."""
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
        token_resp = self._api_get(
            {
                "action": "query",
                "meta": "tokens",
                "type": "login",
            }
        )
        login_token = token_resp.get("query", {}).get("tokens", {}).get("logintoken")
        if not login_token:
            raise PublishError(f"No login token in response: {token_resp}")
        login_resp = self._api_post(
            {
                "action": "login",
                "lgname": self.username,
                "lgpassword": self.password,
                "lgtoken": login_token,
                "format": "json",
            }
        )
        result = login_resp.get("login", {}).get("result")
        if result != "Success":
            raise PublishError(
                f"MW login failed: {login_resp.get('login', {}).get('reason', result)}"
            )

    def _get_csrf_token(self) -> str:
        resp = self._api_get(
            {
                "action": "query",
                "meta": "tokens",
                "type": "csrf",
            }
        )
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
        resp = self._api_post(
            {
                "action": "edit",
                "title": title,
                "text": text,
                "token": token,
                "summary": summary,
                "bot": "1",
                "format": "json",
            }
        )
        edit_result = resp.get("edit", {})
        if edit_result.get("result") != "Success":
            error = resp.get("error", {})
            raise PublishError(
                f"MW edit failed for '{title}': {error.get('info', edit_result)}"
            )
