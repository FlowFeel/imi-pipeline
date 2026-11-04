"""Dry-run WordPress client — records intent without making HTTP requests.

Records all calls to ``self.calls`` without making HTTP requests.

The dry-run client exists because proving pipeline logic (routing,
idempotency, field mapping) and proving connectivity (real HTTP,
live credentials) are distinct concerns. DryRunWPClient proves the former.
Tests that use it verify that the pipeline assembles correct payloads and
respects outlet ordering — without requiring a running WordPress instance
or valid credentials.

@dft
- A1 (pure-io-separation): pure in-process — no I/O imports.
- A5 (mock-doubles): a real in-process double (records calls, returns
  synthetic responses). For full-behavior fakes, use
  :class:`~phosphene.imi_wordpress.fakes.FakeWPClient`.
- A6 (check-result): all methods return dicts (the proof).
"""

from __future__ import annotations

from typing import Any


class DryRunWPClient:
    """WordPress client that records all calls without performing HTTP requests.

    Satisfies WPClientProtocol structurally. All method calls are appended
    to ``self.calls`` for inspection in tests.

    Attributes:
        calls: List of recorded call dicts with keys 'method' and 'args'.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Record a create_post call.

        Args:
            payload: WordPress post payload dict.

        Returns:
            A synthetic response dict with id=0 and the original payload.
        """
        self.calls.append({"method": "create_post", "args": {"payload": payload}})
        return {"id": 0, "status": payload.get("status", "draft"), **payload}

    def post_exists(self, slug: str) -> bool:
        """Check if a post exists by slug (always returns False in dry-run).

        Args:
            slug: Post slug to check.

        Returns:
            Always False.
        """
        self.calls.append({"method": "post_exists", "args": {"slug": slug}})
        return False

    def post_url(self, post_id: int) -> str:
        """Get the URL for a post by ID.

        Args:
            post_id: WordPress post ID.

        Returns:
            A synthetic URL string.
        """
        self.calls.append({"method": "post_url", "args": {"post_id": post_id}})
        return f"https://example.com/?p={post_id}"
