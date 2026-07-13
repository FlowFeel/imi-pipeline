"""Tests for the IMI Syndication FastAPI endpoint.

Uses FastAPI TestClient to POST to /api/syndicate and verify the response.
The Temporal client is intercepted via a fake dispatcher to avoid needing
a live Temporal connection.

fastapi and httpx are required; skip the whole module if unavailable.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from phosphene.imi.api import app

# ---------------------------------------------------------------------------
# Fake dispatcher injection
# ---------------------------------------------------------------------------


class FakeDispatcher:
    """Records dispatched requests without touching Temporal."""

    def __init__(self) -> None:
        self.dispatched: list = []

    async def dispatch(self, request: object) -> str:
        self.dispatched.append(request)
        from phosphene.imi.request import SyndicationRequest

        assert isinstance(request, SyndicationRequest)
        return f"syndication-{request.idempotency_key}"


class FakeTemporal:
    """Minimal fake Temporal client for app-level wiring tests."""

    async def start_workflow(self, *args, **kwargs):  # noqa: ANN
        from dataclasses import dataclass

        @dataclass
        class _H:
            id: str

        return _H(id=kwargs.get("id", "fake-id"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIMISyndicationAPI:
    """FastAPI /api/syndicate endpoint handles syndication requests."""

    def test_health_endpoint(self) -> None:
        """GET /health returns 200 with status ok."""
        with TestClient(app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_syndicate_requires_title(self) -> None:
        """POST /api/syndicate without title returns 422."""
        with TestClient(app) as client:
            response = client.post("/api/syndicate", json={})
        assert response.status_code == 422

    def test_syndicate_minimal_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /api/syndicate with just title returns dispatched status."""
        fake_client = FakeTemporal()

        async def _fake_get_client():
            return fake_client

        import phosphene.imi.api as api_module

        monkeypatch.setattr(api_module, "get_client", _fake_get_client)

        with TestClient(app) as client:
            response = client.post(
                "/api/syndicate",
                json={"title": "Tracer Bullet Test"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "dispatched"
        assert "workflow_id" in body
        assert body["workflow_id"].startswith("syndication-")

    def test_syndicate_full_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /api/syndicate with all fields returns dispatched status."""
        fake_client = FakeTemporal()

        async def _fake_get_client():
            return fake_client

        import phosphene.imi.api as api_module

        monkeypatch.setattr(api_module, "get_client", _fake_get_client)

        payload = {
            "title": "Cave Art in France",
            "body": "{{Article|Headline=Cave Art}}",
            "body_format": "wikitext",
            "author": "Jan",
            "category": "History",
            "source_url": "https://observatory.wiki/Cave_Art_in_France",
            "date": "2026-06-29",
            "outlets": {
                "wordpress": True,
                "salesforce": True,
                "mediawiki": False,
                "pardot": False,
            },
            "publisher_id": "jan",
        }

        with TestClient(app) as client:
            response = client.post("/api/syndicate", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "dispatched"
        assert "cave-art-in-france" in body["workflow_id"]

    def test_syndicate_workflow_id_is_idempotent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same title produces the same workflow_id on both calls."""
        fake_client = FakeTemporal()

        async def _fake_get_client():
            return fake_client

        import phosphene.imi.api as api_module

        monkeypatch.setattr(api_module, "get_client", _fake_get_client)

        with TestClient(app) as client:
            r1 = client.post("/api/syndicate", json={"title": "Same Article"})
            r2 = client.post("/api/syndicate", json={"title": "Same Article"})

        assert r1.json()["workflow_id"] == r2.json()["workflow_id"]

    def test_syndicate_trigger_source_is_api(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The dispatched SyndicationRequest has trigger_source='api'."""
        received: list = []
        fake_client = FakeTemporal()

        # Capture the workflow arg before it's dispatched
        original_start = fake_client.start_workflow

        async def _capture_start(workflow, arg, *, id, task_queue):
            received.append(arg)
            return await original_start(workflow, arg, id=id, task_queue=task_queue)

        fake_client.start_workflow = _capture_start  # type: ignore[method-assign]

        async def _fake_get_client():
            return fake_client

        import phosphene.imi.api as api_module

        monkeypatch.setattr(api_module, "get_client", _fake_get_client)

        with TestClient(app) as client:
            client.post("/api/syndicate", json={"title": "Trigger Source Check"})

        assert len(received) == 1
        assert received[0]["trigger_source"] == "api"
