"""Client protocols — structural interfaces for all external system clients.

Protocols define the minimal interface each outlet needs from its client.
Any object that satisfies the structural interface (duck typing) works —
no inheritance required. In tests, fakes satisfy the protocol.
In production, real HTTP clients satisfy the protocol.

This is the boundary between business logic (outlets) and IO (clients).
Outlets depend on protocols. Clients implement protocols. Neither knows
about the other's internals.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MWClientProtocol(Protocol):
    """Minimal MediaWiki API interface required by ObservatoryOutlet.

    Defines the MW operations an outlet needs: create or update a page,
    check existence, retrieve a page URL, and delete a page (for
    saga compensation). Nothing else.
    """

    def create_page(
        self,
        title: str,
        content: str,
        summary: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create or overwrite a wiki page. Returns page metadata."""
        ...

    def page_exists(self, title: str) -> bool:
        """True if a page with this title exists."""
        ...

    def page_url(self, title: str) -> str:
        """Canonical URL for a page title."""
        ...

    def delete_page(self, title: str, reason: str = "") -> None:
        """Delete a wiki page. Used by saga compensation."""
        ...


@runtime_checkable
class WPClientProtocol(Protocol):
    """Minimal WordPress REST API interface required by WordPressOutlet.

    Defines the WP operations needed: create a post of a given type,
    check if a post already exists by slug, get a post URL,
    and delete a post (for saga compensation).
    """

    def create_post(
        self,
        post_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a WordPress post. Returns the created post data."""
        ...

    def post_exists(self, post_type: str, slug: str) -> bool:
        """True if a post of this type with this slug already exists."""
        ...

    def post_url(self, post_type: str, slug: str) -> str:
        """Canonical URL for a post type and slug."""
        ...

    def delete_post(self, post_url: str) -> None:
        """Delete a WordPress post. Used by saga compensation."""
        ...


@runtime_checkable
class SFClientProtocol(Protocol):
    """Minimal Salesforce API interface required by SalesforceOutlet.

    Defines the Salesforce operations needed: create a record of a given
    object type, check if a record already exists by a key field,
    and delete a record (for saga compensation).
    """

    def create_record(
        self,
        object_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a Salesforce record. Returns the created record data including Id."""
        ...

    def record_exists(
        self,
        object_type: str,
        field: str,
        value: str,
    ) -> bool:
        """True if a record of this type has field=value."""
        ...

    def delete_record(
        self,
        object_type: str,
        record_id: str,
    ) -> None:
        """Delete a Salesforce record. Used by saga compensation."""
        ...


@runtime_checkable
class PardotClientProtocol(Protocol):
    """Minimal Pardot interface required by the send_pardot_email activity.

    Wraps pipeline notification sending behind a single method so the
    activity is testable without credentials or network calls.
    """

    def send_pipeline_notification(
        self,
        result: dict[str, str],
        recipients: list[dict] | None = None,
    ) -> list:
        """Send pipeline notification emails. Returns list of send results."""
        ...
