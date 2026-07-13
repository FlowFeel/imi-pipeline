"""T-360 — Salesforce outlet Tier 2 integration test.

Fires SalesforceOutlet against a Flask mock server and validates
the captured payload against KellyContractValidators.

No real Salesforce credentials needed. The mock captures the exact
payload sent by the outlet for contract assertion.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Generator
from typing import Any

import pytest
from fixtures import IMI_INTEGRATION_DRAFT, make_pydantic_draft
from mock_servers.salesforce_mock import create_salesforce_mock_app
from validators import KellyContractValidators


@pytest.fixture(scope="module")
def sf_mock_server() -> Generator[tuple[Any, int], None, None]:
    """Start the Salesforce Flask mock in a thread, yield (app, port)."""
    import socket
    import threading

    app = create_salesforce_mock_app()

    # Find ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False),
        daemon=True,
    )
    thread.start()

    # Wait for server to be ready
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/last-request")
            urllib.request.urlopen(req, timeout=1)
            break
        except Exception:
            time.sleep(0.05)

    yield app, port


class _MockSFClient:
    """Minimal SFClientProtocol implementation that talks to the Flask mock.

    Satisfies SFClientProtocol structurally (duck typing).
    Routes create_record to the mock server's HTTP endpoint.
    """

    def __init__(self, base_url: str) -> None:
        """Initialise with mock server base URL."""
        self._base_url = base_url

    def create_record(
        self,
        object_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """POST to the mock server's create endpoint."""
        url = f"{self._base_url}/services/data/v59.0/sobjects/{object_type}/"
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def record_exists(
        self,
        object_type: str,
        field: str,
        value: str,
    ) -> bool:
        """Always False — mock does not track existing records."""
        return False


class TestSalesforcePayload:
    """Salesforce outlet sends a Kelly-compliant payload to the mock server."""

    def test_outlet_fires_and_succeeds(self, sf_mock_server: tuple[Any, int]) -> None:
        """SalesforceOutlet publishes to the mock and returns success."""
        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.salesforce import SalesforceOutlet

        app, port = sf_mock_server
        client = _MockSFClient(f"http://127.0.0.1:{port}")
        outlet = SalesforceOutlet(client=client)
        draft = make_pydantic_draft()
        event = PublicationEvent(draft=draft, publisher_id="flow")
        result = outlet.publish(event)

        assert result.succeeded is True
        assert result.artifact is not None

    def test_captured_payload_has_no_hollow_fields(
        self, sf_mock_server: tuple[Any, int]
    ) -> None:
        """The payload captured by the mock has no empty strings or Nones."""
        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.salesforce import SalesforceOutlet

        app, port = sf_mock_server
        client = _MockSFClient(f"http://127.0.0.1:{port}")
        outlet = SalesforceOutlet(client=client)
        draft = make_pydantic_draft()
        event = PublicationEvent(draft=draft, publisher_id="flow")
        outlet.publish(event)

        # Fetch the captured payload
        payload = _get_last_request(port)
        KellyContractValidators.no_hollow_fields(payload)

    def test_captured_payload_has_required_fields(
        self, sf_mock_server: tuple[Any, int]
    ) -> None:
        """The payload has the V2 Salesforce field names (discovered 2026-06-22)."""
        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.salesforce import SalesforceOutlet

        app, port = sf_mock_server
        client = _MockSFClient(f"http://127.0.0.1:{port}")
        outlet = SalesforceOutlet(client=client)
        draft = make_pydantic_draft()
        event = PublicationEvent(draft=draft, publisher_id="flow")
        outlet.publish(event)

        payload = _get_last_request(port)
        # V2 field names
        assert "Headline__c" in payload
        assert "Observatory_Area__c" in payload
        assert "Observatory_wiki_Status__c" in payload
        assert "Date_Received__c" in payload
        _draft = IMI_INTEGRATION_DRAFT()
        assert payload["Headline__c"] == _draft.title
        assert payload["Observatory_Area__c"] == _draft.category
        assert payload["Observatory_wiki_Status__c"] == "Published"
        # Required boolean fields
        assert payload["Pay__c"] is False
        assert payload["GTM_Site_Uploaded__c"] is False
        # V1 field names must NOT be present
        assert "Name" not in payload
        assert "Author__c" not in payload
        assert "Category__c" not in payload
        assert "Status__c" not in payload

    def test_payload_with_observatory_url(
        self, sf_mock_server: tuple[Any, int]
    ) -> None:
        """When observatory_url is in metadata, it appears in the payload."""
        from phosphene.imi.draft import Draft
        from phosphene.imi.event import PublicationEvent
        from phosphene.imi.outlets.salesforce import SalesforceOutlet

        app, port = sf_mock_server
        client = _MockSFClient(f"http://127.0.0.1:{port}")
        outlet = SalesforceOutlet(client=client)

        draft = Draft(
            title="Test With Observatory URL",
            body="Test body content.",
            author="Flow",
            category="Economy",
            metadata={"observatory_url": "https://observatory.wiki/Test"},
        )
        event = PublicationEvent(draft=draft, publisher_id="flow")
        outlet.publish(event)

        payload = _get_last_request(port)
        assert (
            payload.get("Observatory_wiki_Site_Link__c")
            == "https://observatory.wiki/Test"
        )
        assert "Observatory_URL__c" not in payload  # V1 field must be absent
        KellyContractValidators.no_hollow_fields(payload)


def _get_last_request(port: int) -> dict[str, Any]:
    """Fetch the last request body from the mock server."""
    url = f"http://127.0.0.1:{port}/last-request"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())
