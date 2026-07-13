"""Fake clients — test doubles for all external system protocols.

Each fake implements its protocol structurally (duck typing).
Fakes record calls and return predictable, deterministic responses.
They are the only test doubles permitted for outlet unit tests.

No mocking libraries. No monkeypatching. Just simple classes that
satisfy the protocols and give tests control over the IO boundary.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Any


class _FakeSendResult:
    """Minimal send result for FakePardotClient."""

    def __init__(self, succeeded: bool, email: str) -> None:
        self.succeeded = succeeded
        self.email = email
        self.email_id: int | None = None
        self.error: str | None = None


class FakeMWClient:
    """Test double for MWClientProtocol.

    Records created pages. Returns deterministic URLs.
    Simulates idempotency: creating an existing page is a no-op.

    Attributes:
        pages: Dict of title → page data for all created pages.
        base_url: Base URL for constructing page URLs.
    """

    def __init__(self, base_url: str = "https://observatory.wiki") -> None:
        """Initialise with empty page store."""
        self.pages: dict[str, dict[str, Any]] = {}
        self.base_url = base_url

    def create_page(
        self,
        title: str,
        content: str,
        summary: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Record and return page metadata."""
        slug = title.replace(" ", "_")
        self.pages[title] = {
            "title": title,
            "slug": slug,
            "url": f"{self.base_url}/{slug}",
            "content": content,
        }
        return self.pages[title]

    def page_exists(self, title: str) -> bool:
        """True if create_page was called with this title."""
        return title in self.pages

    def page_url(self, title: str) -> str:
        """Return the URL that would have been assigned."""
        return f"{self.base_url}/{title.replace(' ', '_')}"


class FakeWPClient:
    """Test double for WPClientProtocol.

    Records created posts by type and slug.
    Returns predictable post data including a canonical URL.

    Attributes:
        posts: Dict of (post_type, slug) → post data.
        base_url: Base URL for constructing post URLs.
    """

    def __init__(self, base_url: str = "https://independentmediainstitute.org") -> None:
        """Initialise with empty post store."""
        self.posts: dict[tuple[str, str], dict[str, Any]] = {}
        self.base_url = base_url

    def create_post(
        self,
        post_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Record and return post data."""
        slug = data.get("slug", data.get("title", "untitled").lower().replace(" ", "-"))
        post = {
            "id": len(self.posts) + 1,
            "post_type": post_type,
            "slug": slug,
            "url": f"{self.base_url}/{post_type}/{slug}/",
            **data,
        }
        self.posts[(post_type, slug)] = post
        return post

    def post_exists(self, post_type: str, slug: str) -> bool:
        """True if create_post was called with this type and slug."""
        return (post_type, slug) in self.posts

    def post_url(self, post_type: str, slug: str) -> str:
        """Return the URL that would have been assigned."""
        return f"{self.base_url}/{post_type}/{slug}/"


class FakeSFClient:
    """Test double for SFClientProtocol.

    Records created records by object type and a configurable key field.
    Returns predictable record data including a synthetic Salesforce Id.

    Attributes:
        records: Dict of (object_type, field_value) → record data.
    """

    def __init__(self) -> None:
        """Initialise with empty record store."""
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self._counter = 0

    def create_record(
        self,
        object_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Record and return Salesforce record data with synthetic Id."""
        self._counter += 1
        sf_id = f"a1e{self._counter:020d}"
        record = {"Id": sf_id, "success": True, **data}
        # Key by Headline__c (real schema) or fall back to Name/Title__c
        key = data.get(
            "Headline__c", data.get("Name", data.get("Title__c", str(self._counter)))
        )
        self.records[(object_type, str(key))] = record
        return record

    def record_exists(
        self,
        object_type: str,
        field: str,
        value: str,
    ) -> bool:
        """True if a record with this field value was created."""
        return (object_type, value) in self.records


class FakePardotClient:
    """Test double for PardotClientProtocol.

    Records notification calls without sending real emails.
    Returns deterministic send results for each recorded call.

    Attributes:
        calls: List of dicts recording each send_pipeline_notification call.
    """

    def __init__(self) -> None:
        """Initialise with empty call record."""
        self.calls: list[dict[str, Any]] = []

    def send_pipeline_notification(
        self,
        result: dict[str, str],
        recipients: list[dict] | None = None,
    ) -> list[_FakeSendResult]:
        """Record the call and return one successful send result per recipient.

        Args:
            result: Pipeline result dict (keys like 'observatory', 'wordpress').
            recipients: Optional recipient list override.

        Returns:
            List of _FakeSendResult, one per recipient.
        """
        self.calls.append({"result": result, "recipients": recipients})
        rcpts = recipients if recipients is not None else [{"email": "fake@test.com"}]
        return [
            _FakeSendResult(succeeded=True, email=r.get("email", "fake@test.com"))
            for r in rcpts
        ]
