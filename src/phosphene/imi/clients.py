"""Concrete clients implementing external system protocols.

Specifically, the urllib HTTP client implementations used in production.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import urllib.request
from typing import Any

from phosphene.imi.protocols import HTTPResponseProtocol


class UrllibHTTPResponse:
    """Concrete wrapper around urllib's HTTPResponse."""

    def __init__(self, response: Any) -> None:
        """Eagerly record the status from the HTTPResponse object."""
        self._status = int(response.status)

    @property
    def status(self) -> int:
        """Return the HTTP status code."""
        return self._status


class UrllibHTTPClient:
    """Urllib-based implementation of HTTPClientProtocol."""

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> HTTPResponseProtocol:
        """Perform an HTTP GET request using urllib.request."""
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return UrllibHTTPResponse(response)
