"""Fake clients — test doubles for all external system protocols.

Each fake implements its protocol structurally (duck typing).
Fakes record calls and return predictable, deterministic responses.
They are the only test doubles permitted for outlet unit tests.

No mocking libraries. No monkeypatching. Just simple classes that
satisfy the protocols and give tests control over the IO boundary.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from phosphene.imi.crossref import CrossrefReceipt


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

    def delete_page(self, title: str, reason: str = "") -> None:
        """Remove a page from the fake store."""
        self.pages.pop(title, None)


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

    def update_post(
        self,
        post_type: str,
        post_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing post in the fake store."""
        for key, post in self.posts.items():
            if post.get("id") == post_id:
                if "meta" in data and isinstance(post.get("meta"), dict):
                    post["meta"].update(data["meta"])
                post.update({k: v for k, v in data.items() if k != "meta"})
                return post
        raise ValueError(f"Post ID {post_id} not found in fake store")

    def post_exists(self, post_type: str, slug: str) -> bool:
        """True if create_post was called with this type and slug."""
        return (post_type, slug) in self.posts

    def post_url(self, post_type: str, slug: str) -> str:
        """Return the URL that would have been assigned."""
        return f"{self.base_url}/{post_type}/{slug}/"

    def delete_post(self, post_url: str | int) -> None:
        """Remove a post from the fake store by URL or post ID."""
        for key, post in list(self.posts.items()):
            if (
                post.get("url") == post_url
                or post.get("id") == post_url
                or str(post.get("id")) == str(post_url)
            ):
                del self.posts[key]
                return


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

    def delete_record(
        self,
        object_type: str,
        record_id: str,
    ) -> None:
        """Remove a record from the fake store by Id."""
        for key, record in list(self.records.items()):
            if record.get("Id") == record_id:
                del self.records[key]
                return


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
        """Record the call and return one successful send result per recipient."""
        self.calls.append({"result": result, "recipients": recipients})
        rcpts = recipients if recipients is not None else [{"email": "fake@test.com"}]
        return [
            _FakeSendResult(succeeded=True, email=r.get("email", "fake@test.com"))
            for r in rcpts
        ]


class FakeCrossrefClient:
    """Test double for CrossrefClientProtocol.

    Records submitted deposits and returns deterministic CrossrefReceipts.
    Can be scripted to simulate success, timeout, malformed, or rejection.
    """

    def __init__(self) -> None:
        self.deposits: dict[str, dict[str, Any]] = {}
        self.scripted_modes: dict[str, str] = {}
        self._seq = 9000

    def script_mode(self, doi_suffix: str, mode: str) -> None:
        """Script response mode for a given DOI suffix."""
        self.scripted_modes[doi_suffix] = mode

    def deposit(self, xml_payload: str) -> CrossrefReceipt:
        import re

        from phosphene.imi.crossref import CrossrefReceipt, CrossrefReceiptParser

        match = re.search(r"<doi>([^<]+)</doi>", xml_payload)
        if match:
            doi = match.group(1).strip()
        else:
            doi = ""
            if "10.67767/" in xml_payload:
                start = xml_payload.find("10.67767/")
                doi = xml_payload[start : start + 60].split("<")[0].strip()

        suffix = doi.split("imi.2026.")[-1] if "imi.2026." in doi else doi
        mode = self.scripted_modes.get(suffix, "success")

        if mode == "timeout":
            return CrossrefReceipt(
                is_valid=False,
                error="Upstream timeout",
                raw="<error>timeout</error>",
            )

        if mode == "reject":
            return CrossrefReceipt(
                is_valid=False,
                error="Deposit rejected: bad metadata",
                raw='{"error": "malformed deposit batch"}',
            )

        self._seq += 1
        dep_id = f"cr-dep-{self._seq}"

        if mode == "malformed":
            raw = f"<deposit_receipt><cr-dep-id>{dep_id}</cr-dep-id></deposit_receipt>"
            return CrossrefReceiptParser.parse(raw)

        assigned_doi = (
            doi if doi.startswith("10.67767/") else f"10.67767/imi.2026.{suffix}"
        )
        self.deposits[dep_id] = {
            "doi": assigned_doi,
            "status": "pending",
        }
        raw = (
            "<deposit_receipt>"
            f"<cr-dep-id>{dep_id}</cr-dep-id>"
            f"<doi>{assigned_doi}</doi>"
            "<status>pending</status>"
            "</deposit_receipt>"
        )
        return CrossrefReceiptParser.parse(raw)

    def get_deposit_status(self, deposit_id: str) -> CrossrefReceipt:
        from phosphene.imi.crossref import CrossrefReceipt

        rec = self.deposits.get(deposit_id)
        if not rec:
            return CrossrefReceipt(
                deposit_id=deposit_id,
                is_valid=False,
                error="Unknown deposit id",
            )
        return CrossrefReceipt(
            deposit_id=deposit_id,
            doi=rec["doi"],
            status=rec["status"],
            is_valid=True,
        )
