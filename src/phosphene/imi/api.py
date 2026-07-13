"""IMI Syndication API — FastAPI push endpoint for the APITrigger.

Provides:
  POST /api/syndicate — accept a syndication request, start Temporal workflow
  GET  /health        — liveness check

Run as: python -m phosphene.imi.api
or via uvicorn: uvicorn phosphene.imi.api:app --port 8090

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from phosphene.imi.dispatcher import SyndicationDispatcher
from phosphene.imi.request import SyndicationRequest
from phosphene.temporal.client import get_client

app = FastAPI(title="IMI Syndication API")


class SyndicateRequest(BaseModel):
    """HTTP request body — maps to SyndicationRequest.

    All fields except ``title`` are optional with sensible defaults.
    ``outlets`` controls which destinations are targeted in this run.
    """

    title: str
    body: str = ""
    body_format: str = "wikitext"
    author: str = ""
    category: str = ""
    source_url: str = ""
    date: str = ""
    outlets: dict[str, bool] = {
        "wordpress": True,
        "salesforce": True,
        "mediawiki": True,
        "pardot": False,
    }
    publisher_id: str = "api"


@app.post("/api/syndicate")
async def syndicate(req: SyndicateRequest) -> dict:
    """Push endpoint — accepts a syndication request and starts the Temporal workflow.

    Builds a SyndicationRequest from the body, dispatches it to Temporal via
    SyndicationDispatcher, and returns the workflow ID so the caller can poll
    Temporal for status.

    Args:
        req: Validated Pydantic request body.

    Returns:
        dict with ``workflow_id`` and ``status`` keys.
    """
    sr = SyndicationRequest(**req.model_dump(), trigger_source="api")
    client = await get_client()
    dispatcher = SyndicationDispatcher(client)
    workflow_id = await dispatcher.dispatch(sr)
    return {"workflow_id": workflow_id, "status": "dispatched"}


@app.get("/health")
async def health() -> dict:
    """Liveness check endpoint.

    Returns:
        dict with ``status: ok``.
    """
    return {"status": "ok"}


def main() -> None:
    """Entry point for standalone mode: python -m phosphene.imi.api."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8090)


if __name__ == "__main__":
    main()
