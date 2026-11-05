"""Real WordPress REST API client using urllib.

HTTP Basic authentication via application passwords (WP 5.6+).
stdlib only — no requests dependency. Never raises — all errors return dicts.

The never-raise pattern exists because the outlet layer handles failure,
not the client. Raising would force callers to catch and re-wrap — that is
redundant error handling with no information gain. The client's job is
transport; the pipeline's job is deciding what a failure means.

@dft
- A1 (pure-io-separation): I/O wiring module — imports urllib (allowed).
  Satisfies :class:`~phosphene.imi_wordpress.protocols.WPClientProtocol`.
- A5 (mock-doubles): :class:`~phosphene.imi_wordpress.fakes.FakeWPClient`
  is the in-process test double.
- A6 (check-result): all methods return dicts (the proof), never None.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from phosphene.imi_wordpress import __version__
from phosphene.imi_wordpress.config import WPConfig

USER_AGENT = f"UrllibWPClient/{__version__}"


class UrllibWPClient:
    """WordPress REST API client using urllib.request.

    Uses HTTP Basic authentication with username and application password.
    All public methods are non-raising: exceptions are caught and returned
    as error dicts or safe defaults.

    Attributes:
        config: WordPress connection configuration.
    """

    def __init__(self, config: WPConfig) -> None:
        """Initialise the client with WordPress connection config.

        Args:
            config: WordPress connection configuration containing URL,
                username, and application password.
        """
        self.config = config
        self._auth_header = self._build_auth_header()

    def _build_auth_header(self) -> str:
        """Build the Basic auth header value.

        Returns:
            Base64-encoded auth string for the Authorization header.
        """
        credentials = f"{self.config.username}:{self.config.app_password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def create_post(self, post_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a WordPress post via the REST API.

        Sends a POST request to the WP REST endpoint for the given post type.
        Never raises — catches all exceptions and returns an error dict on failure.

        Args:
            post_type: WordPress post type slug (e.g. ``"posts"``, ``"imi_registry"``).
            data: Post data dict (title, content, status, meta, etc.).

        Returns:
            The created post response dict from WordPress on success,
            or ``{"error": True, "message": "<description>"}`` on failure.
        """
        url = f"{self.config.url}/wp-json/wp/v2/{post_type}"
        body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            return {"error": True, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": True, "message": str(exc)}

    def update_post(self, post_type: str, post_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a WordPress post via the REST API.

        Sends a POST request to /wp-json/wp/v2/{post_type}/{post_id}.
        Never raises — catches all exceptions and returns an error dict on failure.

        Args:
            post_type: WordPress post type slug (e.g. "posts", "imi_registry").
            post_id: WordPress post ID.
            data: Post data dict to update (meta, status, title, etc.).

        Returns:
            Updated post response dict, or {"error": True, "message": ...} on failure.
        """
        url = f"{self.config.url}/wp-json/wp/v2/{post_type}/{post_id}"
        body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            return {"error": True, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": True, "message": str(exc)}

    def delete_post(
        self, post_url_or_id: str | int, post_type: str = "imi_registry"
    ) -> dict[str, Any]:
        """Permanently delete a WordPress post via the REST API (force=true).

        Used by saga compensation to clean up posts when downstream Crossref
        deposit fails (Axiom of Search Engine Safety: no leaked dead links).
        Accepts either a post ID (int or numeric str) or a URL.
        Never raises — catches all exceptions and returns an error dict on failure.

        Args:
            post_url_or_id: Post ID or URL of the post to delete.
            post_type: WordPress post type slug (default: "imi_registry").

        Returns:
            WordPress deletion response dict (e.g. {"deleted": True, ...})
            or {"error": True, "message": ...} on failure.
        """
        import re

        post_id: int | None = None
        if isinstance(post_url_or_id, int):
            post_id = post_url_or_id
        elif isinstance(post_url_or_id, str):
            clean = post_url_or_id.strip()
            if clean.isdigit():
                post_id = int(clean)
            elif "?p=" in clean:
                match = re.search(r"[?&]p=(\d+)", clean)
                if match:
                    post_id = int(match.group(1))
            else:
                slug = clean.rstrip("/").split("/")[-1]
                url = self.post_url(post_type, slug)
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": self._auth_header,
                        "User-Agent": USER_AGENT,
                    },
                    method="GET",
                )
                try:
                    with urllib.request.urlopen(req) as resp:
                        results = json.loads(resp.read().decode("utf-8"))
                        if isinstance(results, list) and results:
                            post_id = results[0].get("id")
                except Exception:  # noqa: BLE001, S110
                    pass

        if not post_id:
            return {
                "error": True,
                "message": f"Could not resolve post ID from '{post_url_or_id}'",
            }

        del_url = f"{self.config.url}/wp-json/wp/v2/{post_type}/{post_id}?force=true"
        del_req = urllib.request.Request(
            del_url,
            headers={
                "Authorization": self._auth_header,
                "User-Agent": USER_AGENT,
            },
            method="DELETE",
        )

        try:
            with urllib.request.urlopen(del_req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            return {"error": True, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": True, "message": str(exc)}

    def post_exists(self, post_type: str, slug: str) -> bool:
        """Check if a post with the given slug exists.

        Sends a GET request filtering by slug. Never raises — returns False
        on any error.

        Args:
            post_type: WordPress post type slug (e.g. ``"posts"``, ``"imi_registry"``).
            slug: Post slug to search for.

        Returns:
            True if at least one matching post exists, False otherwise
            (including on network/parse errors).
        """
        url = self.post_url(post_type, slug)

        req = urllib.request.Request(
            url,
            headers={"Authorization": self._auth_header},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                results = json.loads(resp.read().decode("utf-8"))
                return isinstance(results, list) and len(results) > 0
        except Exception:  # noqa: BLE001
            return False

    def post_url(self, post_type: str, slug: str) -> str:
        """Build the REST API query URL for a post type filtered by slug.

        This is a pure string builder — no HTTP request is made.

        Args:
            post_type: WordPress post type slug (e.g. ``"posts"``, ``"imi_registry"``).
            slug: Post slug to filter by.

        Returns:
            The fully-qualified REST API URL string.
        """
        return f"{self.config.url}/wp-json/wp/v2/{post_type}?slug={slug}"

    def get_page(self, page_id: int, context: str = "edit") -> dict[str, Any]:
        """Fetch a page via the REST API.

        Uses ``context=edit`` by default to access protected meta fields
        like ``_elementor_data``. Never raises — returns error dict on failure.

        Args:
            page_id: WordPress page ID.
            context: REST API context (``"edit"`` or ``"view"``).

        Returns:
            Page dict from WordPress, including meta with edit context.
        """
        url = f"{self.config.url}/wp-json/wp/v2/pages/{page_id}?context={context}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self._auth_header,
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"error": True, "message": str(exc)}

    def get_page_by_slug(self, slug: str, context: str = "edit") -> dict[str, Any]:
        """Fetch a page by slug via the REST API.

        Args:
            slug: Page slug to search for.
            context: REST API context.

        Returns:
            First matching page dict, or error dict if not found.
        """
        url = f"{self.config.url}/wp-json/wp/v2/pages?slug={slug}&context={context}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self._auth_header,
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                pages = json.loads(resp.read().decode("utf-8"))
                if isinstance(pages, list) and pages:
                    return pages[0]
                return {"error": True, "message": f"No page found with slug: {slug}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": True, "message": str(exc)}

    def update_page(self, page_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update a page via the REST API.

        Sends a POST request to the WP REST endpoint for the page.
        Use this to update ``content``, ``title``, ``status``, etc.
        For meta fields (especially ``_elementor_data``), use
        :class:`WPEngineDBClient` to avoid WordPress slashing corruption.

        Args:
            page_id: WordPress page ID.
            data: Fields to update (title, content, status, etc.).

        Returns:
            Updated page dict on success, error dict on failure.
        """
        url = f"{self.config.url}/wp-json/wp/v2/pages/{page_id}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"error": True, "message": str(exc)}

    def get_meta(self, page_id: int, context: str = "edit") -> dict[str, Any]:
        """Fetch all meta fields for a page via REST API.

        With ``context=edit``, returns protected meta fields including
        ``_elementor_data``, ``_elementor_page_settings``, etc.

        Args:
            page_id: WordPress page ID.
            context: REST API context.

        Returns:
            Dict of meta key → value strings.
        """
        page = self.get_page(page_id, context=context)
        if isinstance(page, dict) and page.get("error"):
            return page
        return page.get("meta", {})

    def list_revisions(self, page_id: int, context: str = "edit") -> list[dict[str, Any]]:
        """List revisions for a page via REST API.

        Args:
            page_id: WordPress page ID.
            context: REST API context.

        Returns:
            List of revision dicts, or empty list on error.
        """
        url = f"{self.config.url}/wp-json/wp/v2/pages/{page_id}/revisions?context={context}&per_page=50"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self._auth_header,
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []
