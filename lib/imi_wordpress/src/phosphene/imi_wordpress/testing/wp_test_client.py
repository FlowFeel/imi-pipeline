"""WordPress REST API test client using urllib.

Non-raising HTTP client that returns structured WPResponse objects.
Uses Basic auth (application passwords) for REST endpoints.

@dft
- A1 (pure-io-separation): I/O wiring module — imports urllib (allowed).
- A5 (mock-doubles): :class:`~phosphene.imi_wordpress.fakes.FakeWPClient`
  is the in-process test double (no HTTP).
- A6 (check-result): all methods return :class:`WPResponse` (the proof).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class WPResponse:
    """Structured response from a WordPress REST API call."""

    status: int
    data: dict[str, Any] | list[Any] | None
    ok: bool
    error_code: str | None
    error_message: str | None
    raw_body: str


class WPTestClient:
    """Non-raising WordPress REST API test client.

    Uses urllib with Basic auth (application password).
    Returns WPResponse for all outcomes including network errors.
    """

    def __init__(
        self,
        url: str,
        username: str,
        app_password: str,
        timeout: int = 15,
    ) -> None:
        """Initialize with WordPress site credentials.

        Args:
            url: Base URL of the WordPress site (e.g. https://example.com).
            username: WordPress username.
            app_password: WordPress application password.
            timeout: Request timeout in seconds.
        """
        self._base_url = url.rstrip("/")
        self._timeout = timeout
        creds = f"{username}:{app_password}"
        self._auth = "Basic " + base64.b64encode(creds.encode()).decode()

    def get(self, path: str) -> WPResponse:
        """Send an authenticated GET request."""
        return self._request("GET", path, auth=True)

    def post(self, path: str, data: dict[str, Any] | None = None) -> WPResponse:
        """Send an authenticated POST request with JSON body."""
        return self._request("POST", path, data=data, auth=True)

    def delete(self, path: str) -> WPResponse:
        """Send an authenticated DELETE request."""
        return self._request("DELETE", path, auth=True)

    def options(self, path: str) -> WPResponse:
        """Send an authenticated OPTIONS request."""
        return self._request("OPTIONS", path, auth=True)

    def fetch_html(self, url: str) -> str:
        """Fetch a page as HTML (no auth, browser User-Agent).

        Args:
            url: Full URL to fetch.

        Returns:
            HTML body as string, or empty string on error.
        """
        req = Request(url)
        req.add_header("User-Agent", _BROWSER_UA)
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, OSError):
            return ""

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        auth: bool = False,
    ) -> WPResponse:
        """Execute an HTTP request and return WPResponse.

        Args:
            method: HTTP method.
            path: API path (appended to base URL).
            data: JSON body for POST requests.
            auth: Whether to include auth header.
        """
        url = f"{self._base_url}{path}"
        body_bytes: bytes | None = None
        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")

        req = Request(url, data=body_bytes, method=method)
        req.add_header("User-Agent", _BROWSER_UA)
        req.add_header("Content-Type", "application/json")
        if auth:
            req.add_header("Authorization", self._auth)

        try:
            with urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                status = resp.status
        except HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            status = e.code
        except (URLError, OSError) as e:
            return WPResponse(
                status=0,
                data=None,
                ok=False,
                error_code="network_error",
                error_message=str(e),
                raw_body="",
            )

        # Parse JSON response
        parsed: dict[str, Any] | list[Any] | None = None
        error_code: str | None = None
        error_message: str | None = None
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

        if isinstance(parsed, dict):
            error_code = parsed.get("code")
            error_message = parsed.get("message")

        ok = 200 <= status < 300

        return WPResponse(
            status=status,
            data=parsed,
            ok=ok,
            error_code=error_code,
            error_message=error_message,
            raw_body=raw,
        )
