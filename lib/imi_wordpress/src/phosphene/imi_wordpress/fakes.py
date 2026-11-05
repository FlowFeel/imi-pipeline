"""Real in-process test doubles for WordPress I/O — the A5 (mock-doubles) seam.

These fakes satisfy :class:`~phosphene.imi_wordpress.protocols.WPClientProtocol`
and :class:`~phosphene.imi_wordpress.protocols.DBClientProtocol` with real,
in-process behavior. They replace ``MagicMock(spec=...)`` in tests.

Why fakes, not mocks:
    A ``MagicMock`` records that a method was called but returns a canned
    response. It does not execute behavior. A fake executes real behavior
    in-process — it stores data, returns it on read, and tracks state.

    A mock test proves the caller *called* the right method. A fake test
    proves the caller *handles* the response correctly. Fakes catch logic
    bugs that mocks cannot: off-by-one errors, wrong key lookups, missing
    error handling, state corruption.

@dft
- A1 (pure-io-separation): fakes are pure in-process — no network, no disk.
- A5 (mock-doubles): real behavior, not ``MagicMock``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from phosphene.imi_wordpress.config import WPConfig


@dataclass
class FakeWPClient:
    """In-process fake of the WordPress REST API client.

    Stores pages, meta, and revisions in memory. All methods return
    real data structures — no canned responses. Callers can inspect
    ``self.calls`` to verify the call sequence (like a mock, but with
    real behavior).

    @dft A5 (mock-doubles): real in-process behavior, not MagicMock.
    """

    config: WPConfig
    pages: dict[int, dict[str, Any]] = field(default_factory=dict)
    meta: dict[int, dict[str, str]] = field(default_factory=dict)
    revisions: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    created_posts: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def get_page(self, page_id: int, context: str = "edit") -> dict[str, Any]:
        self.calls.append({"method": "get_page", "page_id": page_id, "context": context})
        if page_id not in self.pages:
            return {"error": True, "message": f"Page {page_id} not found"}
        return self.pages[page_id]

    def get_page_by_slug(self, slug: str, context: str = "edit") -> dict[str, Any]:
        self.calls.append({"method": "get_page_by_slug", "slug": slug, "context": context})
        for page in self.pages.values():
            if page.get("slug") == slug:
                return page
        return {"error": True, "message": f"No page found with slug: {slug}"}

    def get_meta(self, page_id: int, context: str = "edit") -> dict[str, Any]:
        self.calls.append({"method": "get_meta", "page_id": page_id, "context": context})
        return self.meta.get(page_id, {})

    def update_page(self, page_id: int, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"method": "update_page", "page_id": page_id, "data": data})
        if page_id not in self.pages:
            return {"error": True, "message": f"Page {page_id} not found"}
        self.pages[page_id].update(data)
        return self.pages[page_id]

    def list_revisions(self, page_id: int, context: str = "edit") -> list[dict[str, Any]]:
        self.calls.append({"method": "list_revisions", "page_id": page_id, "context": context})
        return self.revisions.get(page_id, [])

    def create_post(self, post_type: str, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"method": "create_post", "post_type": post_type, "data": data})
        new_id = len(self.created_posts) + 1
        post = {"id": new_id, "type": post_type, **data}
        self.created_posts.append(post)
        return post

    def update_post(self, post_type: str, post_id: int, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(
            {"method": "update_post", "post_type": post_type, "post_id": post_id, "data": data}
        )
        for post in self.created_posts:
            if post.get("id") == post_id:
                if (
                    "meta" in data
                    and isinstance(post.get("meta"), dict)
                    and isinstance(data["meta"], dict)
                ):
                    post["meta"].update(data["meta"])
                post.update({k: v for k, v in data.items() if k != "meta"})
                return post
        return {"error": True, "message": f"Post {post_id} not found"}

    def delete_post(
        self, post_url_or_id: str | int, post_type: str = "imi_registry"
    ) -> dict[str, Any]:
        self.calls.append(
            {"method": "delete_post", "post_url_or_id": post_url_or_id, "post_type": post_type}
        )
        target_id: int | None = None
        if isinstance(post_url_or_id, int):
            target_id = post_url_or_id
        elif isinstance(post_url_or_id, str) and post_url_or_id.isdigit():
            target_id = int(post_url_or_id)

        for i, post in enumerate(self.created_posts):
            match_id = target_id is not None and post.get("id") == target_id
            match_url = isinstance(post_url_or_id, str) and (
                post.get("slug") in post_url_or_id or str(post.get("id")) in post_url_or_id
            )
            if match_id or match_url:
                deleted = self.created_posts.pop(i)
                return {"deleted": True, "previous": deleted}
        return {"error": True, "message": f"Post {post_url_or_id} not found"}

    def post_exists(self, post_type: str, slug: str) -> bool:
        self.calls.append({"method": "post_exists", "post_type": post_type, "slug": slug})
        for post in self.created_posts:
            if post.get("type") == post_type and post.get("slug") == slug:
                return True
        return False

    # Test helper: seed a page + meta for a test scenario
    def seed_page(
        self, page_id: int, page: dict[str, Any], meta: dict[str, str] | None = None
    ) -> None:
        """Seed a page and optional meta for a test scenario."""
        self.pages[page_id] = page
        if meta is not None:
            self.meta[page_id] = meta


@dataclass
class FakeDBClient:
    """In-process fake of the direct database client.

    Stores meta values in memory. Simulates the raw-SQL gateway without
    any network or WordPress instance. Tracks all writes in
    ``self.write_log`` for parity verification.

    @dft A5 (mock-doubles): real in-process behavior, not MagicMock.
    Can simulate ``wp_slash()`` corruption via :meth:`simulate_slashing`.
    """

    meta_store: dict[int, dict[str, str]] = field(default_factory=dict)
    backups: dict[int, dict[str, Any]] = field(default_factory=dict)
    write_log: list[dict[str, Any]] = field(default_factory=list)
    _slash_on_write: bool = False

    def get_raw_meta(self, post_id: int, meta_key: str = "_elementor_data") -> str:
        return self.meta_store.get(post_id, {}).get(meta_key, "")

    def set_elementor_data(self, post_id: int, value: str) -> dict[str, Any]:
        stored = self._apply_slashing(value) if self._slash_on_write else value
        self.meta_store.setdefault(post_id, {})["_elementor_data"] = stored
        self.write_log.append(
            {"post_id": post_id, "key": "_elementor_data", "length": len(stored)}
        )
        import json

        json_valid = True
        try:
            json.loads(stored)
        except (json.JSONDecodeError, TypeError):
            json_valid = False
        return {
            "status": "updated",
            "verify_length": len(stored),
            "verify_json_valid": json_valid,
        }

    def restore_from_meta(self, post_id: int, source_meta_id: int) -> dict[str, Any]:
        # Simplified: in the fake, source_meta_id maps to a backup entry
        backup = self.backups.get(source_meta_id, {})
        value = backup.get("meta", {}).get("_elementor_data", "")
        self.meta_store.setdefault(post_id, {})["_elementor_data"] = value
        return {"status": "restored", "source_length": len(value), "verify_length": len(value)}

    def list_revisions(self, post_id: int) -> dict[str, Any]:
        return {"total_revisions": 0, "revisions": []}

    def backup_page(self, post_id: int) -> dict[str, Any]:
        meta = self.meta_store.get(post_id, {})
        self.backups[post_id] = {"page_id": post_id, "meta": dict(meta)}
        return {"page_id": post_id, "meta": dict(meta)}

    def sql_query(self, query: str) -> dict[str, Any]:
        return {"query": query, "results": 0, "data": []}

    def simulate_slashing(self, enabled: bool = True) -> None:
        """Simulate ``wp_slash()`` corruption on subsequent writes.

        When enabled, ``set_elementor_data`` will escape all double
        quotes in the value before storing it — exactly what WordPress's
        ``update_post_meta()`` does. This lets parity tests verify the
        harness detects the corruption.
        """
        self._slash_on_write = enabled

    def _apply_slashing(self, value: str) -> str:
        """Apply ``wp_slash()``-like escaping to a value."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    # Test helper: seed meta for a test scenario
    def seed_meta(self, post_id: int, meta_key: str, value: str) -> None:
        """Seed a meta value for a test scenario."""
        self.meta_store.setdefault(post_id, {})[meta_key] = value
