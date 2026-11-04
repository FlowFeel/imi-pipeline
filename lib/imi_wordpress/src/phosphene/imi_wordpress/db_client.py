"""WP Engine database client — direct DB access via mu-plugin gateway.

The REST API goes through WordPress's metadata layer which applies
``wp_slash()`` on write. This corrupts raw JSON values by escaping
double quotes. The :class:`WPEngineDBClient` bypasses this by using
a mu-plugin gateway deployed via WP Engine git that executes raw SQL
through the WordPress ``$wpdb`` object.

This client is the persistence-layer counterpart to :class:`UrllibWPClient`
(the application-layer REST client). Together they form the dual-layer
parity harness: REST reads are compared against DB reads to detect
abstraction leaks.

The mu-plugin endpoint lives at ``/?imi_diag=1`` and requires a secret
token or administrator login.

@dft
- A1 (pure-io-separation): I/O wiring module — imports urllib (allowed).
  Satisfies :class:`~phosphene.imi_wordpress.protocols.DBClientProtocol`.
- A5 (mock-doubles): :class:`~phosphene.imi_wordpress.fakes.FakeDBClient`
  is the in-process test double.
- A6 (check-result): all methods return dicts/strings (the proof).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from phosphene.imi_wordpress import __version__

USER_AGENT = f"WPEngineDBClient/{__version__}"


class WPEngineDBClient:
    """Direct database client via WP Engine mu-plugin gateway.

    Communicates with a temporary mu-plugin (``imi-diagnostics.php``)
    deployed via WP Engine git. The plugin exposes SQL query, meta read,
    meta write (raw SQL), and backup actions behind a token-authenticated
    endpoint.

    All writes use raw ``$wpdb->query()`` to avoid WordPress's
    ``wp_slash()`` which corrupts JSON values.

    Attributes:
        site_url: WordPress site URL.
        token: Secret authentication token for the mu-plugin.
    """

    def __init__(self, site_url: str, token: str) -> None:
        """Initialize the DB client.

        Args:
            site_url: WordPress site URL (e.g. https://independentmediainstitute.org).
            token: Secret token for the mu-plugin endpoint.
        """
        self.site_url = site_url.rstrip("/")
        self.token = token

    def _request(self, action: str, **params: str | int) -> dict[str, Any]:
        """Send a GET request to the mu-plugin gateway.

        Args:
            action: The diagnostic action name.
            **params: Additional query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            RuntimeError: If the request fails or returns an error.
        """
        query_params = {
            "imi_diag": "1",
            "action": action,
            "token": self.token,
            **{k: str(v) for k, v in params.items()},
        }
        query_string = urllib.parse.urlencode(query_params)
        url = f"{self.site_url}/?{query_string}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"DB gateway HTTP {exc.code}: {body}") from exc
        except Exception as exc:
            raise RuntimeError(f"DB gateway error: {exc}") from exc

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"DB gateway error: {data.get('error')}")
        return data

    def _post(self, action: str, body: dict[str, Any], **params: str | int) -> dict[str, Any]:
        """Send a POST request to the mu-plugin gateway.

        Args:
            action: The diagnostic action name.
            body: JSON body to send.
            **params: Additional query parameters.

        Returns:
            Parsed JSON response dict.
        """
        query_params = {
            "imi_diag": "1",
            "action": action,
            "token": self.token,
            **{k: str(v) for k, v in params.items()},
        }
        query_string = urllib.parse.urlencode(query_params)
        url = f"{self.site_url}/?{query_string}"

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"DB gateway HTTP {exc.code}: {body_text}") from exc

    def get_raw_meta(self, post_id: int, meta_key: str = "_elementor_data") -> str:
        """Read a raw meta value directly from the database.

        Uses raw SQL — no WordPress slashing/unslashing.

        Args:
            post_id: WordPress post ID.
            meta_key: Meta key to read.

        Returns:
            The raw meta value string, or empty string if not found.
        """
        data = self._request("raw_meta", page_id=post_id, key=meta_key)
        return data.get("value", "")

    def set_elementor_data(self, post_id: int, value: str) -> dict[str, Any]:
        """Write ``_elementor_data`` via raw SQL UPDATE.

        Bypasses ``update_post_meta()`` to avoid ``wp_slash()`` corruption.

        Args:
            post_id: WordPress post ID.
            value: The raw JSON string to write.

        Returns:
            Response dict with status, verify_length, verify_json_valid.
        """
        return self._post(
            "set_elementor",
            {"_elementor_data": value},
            page_id=post_id,
        )

    def restore_from_meta(self, post_id: int, source_meta_id: int) -> dict[str, Any]:
        """Copy a meta value from one postmeta row to another via raw SQL.

        Args:
            post_id: Target post ID.
            source_meta_id: Source postmeta row ID (meta_id column).

        Returns:
            Response dict with status, source_length, verify_length,
            verify_matches_source, verify_json_valid.
        """
        return self._request(
            "restore_elementor",
            page_id=post_id,
            source_meta_id=source_meta_id,
        )

    def list_revisions(self, post_id: int) -> dict[str, Any]:
        """List all database revisions for a post.

        Queries the ``wp_posts`` table for revision-type children.
        Returns elementor_data length for each revision.

        Args:
            post_id: WordPress post ID.

        Returns:
            Dict with total_revisions and revisions list.
        """
        return self._request("revisions", page_id=post_id)

    def backup_page(self, post_id: int) -> dict[str, Any]:
        """Export a full backup of a page (post + all meta) as JSON.

        Args:
            post_id: WordPress post ID.

        Returns:
            Dict with page info and all meta keys/values.
        """
        return self._request("backup", page_id=post_id)

    def search_postmeta(
        self, meta_key: str = "_elementor_data", min_length: int = 500
    ) -> dict[str, Any]:
        """Search for postmeta entries with large values.

        Useful for finding orphaned copies of Elementor data.

        Args:
            meta_key: Meta key to search for.
            min_length: Minimum value length to include.

        Returns:
            Dict with results count and entries list.
        """
        return self._request(
            "search_postmeta",
            s=meta_key,
        )

    def sql_query(self, query: str) -> dict[str, Any]:
        """Execute a read-only SELECT query on the WordPress database.

        Args:
            query: SQL SELECT query.

        Returns:
            Dict with query, results count, and data.

        Raises:
            ValueError: If the query is not a SELECT.
        """
        if not query.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        return self._request("sql", q=query)

    def compare(self, page_id: int, source_post_id: int) -> dict[str, Any]:
        """Compare elementor data between two posts.

        Args:
            page_id: Target post ID.
            source_post_id: Source post ID.

        Returns:
            Dict with source/target lengths, JSON validity, length diff.
        """
        return self._request(
            "compare",
            page_id=page_id,
            source_post_id=source_post_id,
        )

    def page_meta(self, post_id: int) -> dict[str, Any]:
        """Dump all postmeta for a page with value lengths and previews.

        Args:
            post_id: WordPress post ID.

        Returns:
            Dict with page info and meta dict.
        """
        return self._request("page_meta", page_id=post_id)
