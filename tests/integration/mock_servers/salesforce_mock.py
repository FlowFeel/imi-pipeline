"""Flask mock server for Salesforce API.

Simulates the minimal Salesforce REST API surface needed for
integration testing the SalesforceOutlet:

- POST /services/oauth2/token → synthetic access_token
- POST /services/data/v59.0/sobjects/Content_Management__c/ → synthetic record
- GET /last-request → returns last received request body

No real Salesforce credentials needed. All responses are deterministic.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import threading
from typing import Any

from flask import Flask, Response, jsonify, request


def create_salesforce_mock_app() -> Flask:
    """Create and configure the Salesforce mock Flask app.

    Returns:
        Configured Flask app with Salesforce API endpoints.
    """
    app = Flask(__name__)
    app.config["TESTING"] = True

    # Store last request for inspection
    _last_request: dict[str, Any] = {}

    @app.route("/services/oauth2/token", methods=["POST"])
    def token() -> Response:
        """OAuth2 token endpoint — returns synthetic access token."""
        return jsonify(
            {
                "access_token": "MOCK_ACCESS_TOKEN_00D000000000001",
                "instance_url": "http://localhost",
                "id": "https://login.salesforce.com/id/00D000000000001/005000000000001",
                "token_type": "Bearer",
                "issued_at": "1000000000000",
                "signature": "mock_signature",
            }
        )

    @app.route(
        "/services/data/v59.0/sobjects/Content_Management__c/",
        methods=["POST"],
    )
    def create_record() -> tuple[Response, int]:
        """Create a Content_Management__c record — returns synthetic ID."""
        body = request.get_json(force=True, silent=True) or {}
        _last_request.clear()
        _last_request.update(body)
        return jsonify(
            {
                "Id": "a1e0000000000001AAA",
                "id": "a1e0000000000001AAA",
                "success": True,
                "errors": [],
            }
        ), 201

    @app.route("/last-request", methods=["GET"])
    def last_request() -> Response:
        """Inspection endpoint — returns the last received request body."""
        return jsonify(_last_request)

    # Store ref to _last_request on the app for direct access in tests
    app._last_request = _last_request  # type: ignore[attr-defined]

    return app


def run_salesforce_mock(port: int = 0) -> tuple[threading.Thread, int]:
    """Start the Salesforce mock server in a background thread.

    Args:
        port: Port to bind to. 0 = ephemeral (OS-assigned).

    Returns:
        Tuple of (thread, actual_port).
    """
    app = create_salesforce_mock_app()
    import socket

    # Find an ephemeral port
    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False),
        daemon=True,
    )
    thread.start()
    return thread, port
