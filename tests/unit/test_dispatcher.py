"""Tests for SyndicationDispatcher.

Verifies the dispatcher builds the correct Temporal workflow ID from the
idempotency_key and passes the serialised request to start_workflow.

Uses a fake Temporal client (DI, zero @patch).

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pytest

from phosphene.imi.dispatcher import SyndicationDispatcher
from phosphene.imi.request import SyndicationRequest


# ---------------------------------------------------------------------------
# Fake Temporal client
# ---------------------------------------------------------------------------


@dataclass
class _FakeHandle:
    """Fake workflow handle returned by start_workflow."""

    id: str


class FakeTemporalClient:
    """Records start_workflow calls without connecting to Temporal.

    Attributes:
        calls: List of dicts, one per start_workflow call.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def start_workflow(
        self,
        workflow: str,
        arg: object,
        *,
        id: str,
        task_queue: str,
    ) -> _FakeHandle:
        """Record the call and return a fake handle.

        Args:
            workflow: Workflow name string.
            arg: Payload passed to the workflow.
            id: Temporal workflow ID.
            task_queue: Task queue name.

        Returns:
            Fake handle with the given ID.
        """
        self.calls.append({
            "workflow": workflow,
            "arg": arg,
            "id": id,
            "task_queue": task_queue,
        })
        return _FakeHandle(id=id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyndicationDispatcher:
    """SyndicationDispatcher bridges triggers to Temporal."""

    @pytest.mark.asyncio
    async def test_workflow_id_uses_idempotency_key(self) -> None:
        """dispatch() constructs workflow ID as 'syndication-{idempotency_key}'."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client)
        request = SyndicationRequest(title="Cave Art in France")
        # __post_init__ sets idempotency_key = "cave-art-in-france"

        workflow_id = await dispatcher.dispatch(request)

        assert workflow_id == "syndication-cave-art-in-france"
        assert len(client.calls) == 1
        assert client.calls[0]["id"] == "syndication-cave-art-in-france"

    @pytest.mark.asyncio
    async def test_custom_idempotency_key(self) -> None:
        """Explicit idempotency_key is used verbatim in the workflow ID."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client)
        request = SyndicationRequest(
            title="Test Article",
            idempotency_key="my-custom-key-2026-07-01",
        )

        workflow_id = await dispatcher.dispatch(request)

        assert workflow_id == "syndication-my-custom-key-2026-07-01"

    @pytest.mark.asyncio
    async def test_workflow_name_is_syndication_saga(self) -> None:
        """dispatch() calls start_workflow with 'SyndicationSagaWorkflow'."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client)
        request = SyndicationRequest(title="Workflow Name Test")

        await dispatcher.dispatch(request)

        assert client.calls[0]["workflow"] == "SyndicationSagaWorkflow"

    @pytest.mark.asyncio
    async def test_task_queue_default(self) -> None:
        """Default task queue is 'imi-syndication'."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client)
        request = SyndicationRequest(title="Queue Test")

        await dispatcher.dispatch(request)

        assert client.calls[0]["task_queue"] == "imi-syndication"

    @pytest.mark.asyncio
    async def test_custom_task_queue(self) -> None:
        """Custom task queue overrides the default."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client, task_queue="custom-queue")
        request = SyndicationRequest(title="Custom Queue Test")

        await dispatcher.dispatch(request)

        assert client.calls[0]["task_queue"] == "custom-queue"

    @pytest.mark.asyncio
    async def test_payload_is_serialised_request(self) -> None:
        """dispatch() passes asdict(request) as the workflow argument."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client)
        request = SyndicationRequest(
            title="Payload Test",
            body="Some content",
            author="Flow",
            trigger_source="api",
        )

        await dispatcher.dispatch(request)

        payload = client.calls[0]["arg"]
        expected = asdict(request)
        assert payload == expected
        assert payload["title"] == "Payload Test"
        assert payload["body"] == "Some content"
        assert payload["trigger_source"] == "api"

    @pytest.mark.asyncio
    async def test_idempotent_dispatches_same_key(self) -> None:
        """Two dispatches with the same title produce the same workflow ID."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client)
        request1 = SyndicationRequest(title="Idempotent Article")
        request2 = SyndicationRequest(title="Idempotent Article")

        id1 = await dispatcher.dispatch(request1)
        id2 = await dispatcher.dispatch(request2)

        assert id1 == id2
        assert id1 == "syndication-idempotent-article"

    @pytest.mark.asyncio
    async def test_returns_workflow_id_string(self) -> None:
        """dispatch() returns a string (the workflow ID)."""
        client = FakeTemporalClient()
        dispatcher = SyndicationDispatcher(client)
        request = SyndicationRequest(title="Return Type Test")

        result = await dispatcher.dispatch(request)

        assert isinstance(result, str)
        assert result.startswith("syndication-")
