"""Flask mock server for MediaWiki API.

Simulates the minimal MediaWiki API surface needed for wire-level
integration testing of the ObservatoryOutlet:

- POST /w/api.php?action=login → success
- POST /w/api.php?action=query (tokens) → returns csrf token
- POST /w/api.php?action=edit → returns {"edit": {"result": "Success"}}
- GET /w/api.php?action=query&titles=Draft:... → returns page exists

No real MediaWiki instance needed. All responses are deterministic.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify, request


def create_mediawiki_mock_app() -> Flask:
    """Create and configure the MediaWiki mock Flask app.

    Returns:
        Configured Flask app with MediaWiki API endpoints.
    """
    app = Flask(__name__)
    app.config["TESTING"] = True

    # Track created pages and last edit request
    _pages: dict[str, str] = {}  # title → wikitext
    _last_edit_request: dict[str, Any] = {}

    @app.route("/w/api.php", methods=["POST", "GET"])
    def api() -> Response:
        """Handle all MW API actions via the action parameter."""
        # Get action from either query params or form data
        action = request.args.get("action") or request.form.get("action", "")

        if action == "login":
            return _handle_login()
        elif action == "query":
            return _handle_query()
        elif action == "edit":
            return _handle_edit(_pages, _last_edit_request)
        else:
            return jsonify(
                {
                    "error": {
                        "code": "unknown_action",
                        "info": f"Unknown action: {action}",
                    }
                }
            )

    @app.route("/last-edit-request", methods=["GET"])
    def last_edit() -> Response:
        """Inspection endpoint — returns the last edit request params."""
        return jsonify(_last_edit_request)

    @app.route("/pages", methods=["GET"])
    def list_pages() -> Response:
        """Inspection endpoint — returns all created pages."""
        return jsonify(_pages)

    # Store refs for direct access in tests
    app._pages = _pages  # type: ignore[attr-defined]
    app._last_edit_request = _last_edit_request  # type: ignore[attr-defined]

    return app


def _handle_login() -> Response:
    """Handle login action — always succeeds."""
    return jsonify(
        {
            "login": {
                "result": "Success",
                "lguserid": 1,
                "lgusername": "flow-bot",
            }
        }
    )


def _handle_query() -> Response:
    """Handle query action — tokens or page existence."""
    meta = request.form.get("meta") or request.args.get("meta", "")
    titles = request.form.get("titles") or request.args.get("titles", "")
    token_type = request.form.get("type") or request.args.get("type", "")

    if meta == "tokens":
        if token_type == "login":
            return jsonify({"query": {"tokens": {"logintoken": "MOCK_LOGIN_TOKEN+\\"}}})
        else:
            return jsonify({"query": {"tokens": {"csrftoken": "MOCK_CSRF_TOKEN+\\"}}})

    if titles:
        # Check if page exists in our store
        from flask import current_app

        pages = current_app._pages  # type: ignore[attr-defined]
        if titles in pages:
            return jsonify(
                {
                    "query": {
                        "pages": {
                            "12345": {
                                "pageid": 12345,
                                "ns": 3212,
                                "title": titles,
                            }
                        }
                    }
                }
            )
        else:
            return jsonify(
                {
                    "query": {
                        "pages": {
                            "-1": {
                                "ns": 3212,
                                "title": titles,
                                "missing": "",
                            }
                        }
                    }
                }
            )

    return jsonify({"query": {}})


def _handle_edit(
    pages: dict[str, str],
    last_edit_request: dict[str, Any],
) -> Response:
    """Handle edit action — create/update a page."""
    title = request.form.get("title", "")
    text = request.form.get("text", "")

    # Store the edit params for inspection
    last_edit_request.clear()
    last_edit_request.update(
        {
            "title": title,
            "text": text,
            "token": request.form.get("token", ""),
            "createonly": request.form.get("createonly", ""),
            "format": request.form.get("format", ""),
        }
    )

    # Store the page
    pages[title] = text

    return jsonify(
        {
            "edit": {
                "result": "Success",
                "pageid": 12345,
                "title": title,
                "contentmodel": "wikitext",
                "oldrevid": 0,
                "newrevid": 100,
                "newtimestamp": "2026-06-22T00:00:00Z",
            }
        }
    )
