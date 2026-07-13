"""SyndicationDispatcher — the single bridge between triggers and Temporal.

Every trigger (API, Telegram, Asana, MW hook) calls dispatch() with a
SyndicationRequest. The dispatcher starts one SyndicationSagaWorkflow per
request, using the idempotency_key as the workflow ID to deduplicate
repeated syndication attempts for the same content.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import asdict

from phosphene.imi.request import SyndicationRequest


class SyndicationDispatcher:
    """Receives a SyndicationRequest from any trigger and starts the Temporal workflow.

    This is the single integration point: every trigger calls dispatch().
    Every dispatch starts one SyndicationSagaWorkflow.

    Idempotent: uses ``request.idempotency_key`` as the Temporal workflow ID.
    If the same article is syndicated twice, Temporal deduplicates.
    """

    def __init__(
        self,
        temporal_client: object,
        task_queue: str = "imi-syndication",
    ) -> None:
        """Initialise the dispatcher with a Temporal client.

        Args:
            temporal_client: Connected Temporal Client instance.
                             Typed as ``object`` to avoid hard Temporal dependency
                             in this module — the caller provides the real client.
            task_queue: Temporal task queue name. Defaults to ``imi-syndication``.
        """
        self._client = temporal_client
        self._task_queue = task_queue

    async def dispatch(self, request: SyndicationRequest) -> str:
        """Start a syndication workflow. Returns the workflow run ID.

        Uses ``request.idempotency_key`` as the Temporal workflow ID for
        deduplication. If a workflow with the same key is already running,
        Temporal returns a handle to the existing run.

        Args:
            request: Fully populated SyndicationRequest from any trigger.

        Returns:
            The Temporal workflow ID (``handle.id``).
        """
        handle = await self._client.start_workflow(
            "SyndicationSagaWorkflow",
            asdict(request),
            id=f"syndication-{request.idempotency_key}",
            task_queue=self._task_queue,
        )
        return handle.id
