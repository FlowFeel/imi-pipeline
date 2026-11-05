"""Protocol interfaces for WordPress I/O — the A1 (pure-io-separation) seam.

These Protocols define the I/O boundary. Pure logic modules depend on
these interfaces, not on concrete clients. Production uses
:class:`~phosphene.imi_wordpress.client.UrllibWPClient` and
:class:`~phosphene.imi_wordpress.db_client.WPEngineDBClient`; tests use
:class:`~phosphene.imi_wordpress.fakes.FakeWPClient` and
:class:`~phosphene.imi_wordpress.fakes.FakeDBClient`.

@dft
- A1 (pure-io-separation): these Protocols ARE the seam. Logic imports
  Protocols, never concrete clients.
- A5 (mock-doubles): the fakes satisfy these Protocols with real behavior.
"""

from __future__ import annotations

from typing import Any, Protocol


class WPClientProtocol(Protocol):
    """Protocol for the WordPress REST API client (application layer).

    The REST API goes through WordPress's metadata layer which applies
    ``wp_slash()`` on write. Reads with ``context=edit`` return
    unslashed values.
    """

    config: Any

    def get_page(self, page_id: int, context: str = "edit") -> dict[str, Any]:
        """Fetch a page via the REST API."""
        ...

    def get_page_by_slug(self, slug: str, context: str = "edit") -> dict[str, Any]:
        """Fetch a page by slug via the REST API."""
        ...

    def get_meta(self, page_id: int, context: str = "edit") -> dict[str, Any]:
        """Fetch all meta fields for a page."""
        ...

    def update_page(self, page_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a page via the REST API."""
        ...

    def list_revisions(self, page_id: int, context: str = "edit") -> list[dict[str, Any]]:
        """List revisions for a page."""
        ...

    def create_post(self, post_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a WordPress post."""
        ...

    def update_post(self, post_type: str, post_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a WordPress post via the REST API."""
        ...

    def delete_post(
        self, post_url_or_id: str | int, post_type: str = "imi_registry"
    ) -> dict[str, Any]:
        """Delete a WordPress post permanently (used by saga compensation)."""
        ...

    def post_exists(self, post_type: str, slug: str) -> bool:
        """Check if a post with the given slug exists."""
        ...


class DBClientProtocol(Protocol):
    """Protocol for the direct database client (persistence layer).

    The DB client bypasses WordPress's ``wp_slash()`` by using raw SQL
    through a mu-plugin gateway. This is the persistence-layer
    counterpart to :class:`WPClientProtocol`.
    """

    def get_raw_meta(self, post_id: int, meta_key: str = "_elementor_data") -> str:
        """Read a raw meta value directly from the database."""
        ...

    def set_elementor_data(self, post_id: int, value: str) -> dict[str, Any]:
        """Write ``_elementor_data`` via raw SQL UPDATE."""
        ...

    def restore_from_meta(self, post_id: int, source_meta_id: int) -> dict[str, Any]:
        """Copy a meta value from one postmeta row to another."""
        ...

    def list_revisions(self, post_id: int) -> dict[str, Any]:
        """List all database revisions for a post."""
        ...

    def backup_page(self, post_id: int) -> dict[str, Any]:
        """Export a full backup of a page (post + all meta)."""
        ...

    def sql_query(self, query: str) -> dict[str, Any]:
        """Execute a read-only SELECT query."""
        ...
