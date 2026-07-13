"""Flask mock server for WordPress REST API.

Simulates the minimal WordPress REST API surface needed for
integration testing the WordPressOutlet:

- POST /wp-json/wp/v2/imi_registry → creates a mock post, returns it
- GET /last-request → returns last received request body

No real WordPress credentials needed. All responses are deterministic.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify, request


def create_wordpress_mock_app() -> Flask:
    """Create and configure the WordPress mock Flask app.

    Returns:
        Configured Flask app with WordPress REST API endpoints.
    """
    app = Flask(__name__)
    app.config["TESTING"] = True

    # Store last request for inspection
    _last_request: dict[str, Any] = {}

    @app.route("/wp-json/wp/v2/imi_registry", methods=["POST"])
    def create_post() -> tuple[Response, int]:
        """Create an imi_registry post — returns synthetic post data."""
        body = request.get_json(force=True, silent=True) or {}
        _last_request.clear()
        _last_request.update(body)

        slug = body.get("slug", "test-post")
        return jsonify(
            {
                "id": 9999,
                "date": "2026-06-22T00:00:00",
                "date_gmt": "2026-06-22T00:00:00",
                "modified": "2026-06-22T00:00:00",
                "modified_gmt": "2026-06-22T00:00:00",
                "slug": slug,
                "status": body.get("status", "draft"),
                "type": "imi_registry",
                "link": f"http://localhost/imi_registry/{slug}/",
                "title": {"rendered": body.get("title", "Test Post")},
                "url": f"http://localhost/imi_registry/{slug}/",
                "meta": body.get("meta", {}),
            }
        ), 201

    @app.route("/last-request", methods=["GET"])
    def last_request() -> Response:
        """Inspection endpoint — returns the last received request body."""
        return jsonify(_last_request)

    # Store ref to _last_request on the app for direct access in tests
    app._last_request = _last_request  # type: ignore[attr-defined]

    return app
