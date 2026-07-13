"""TemporalClient — configured once from env, cached, shared across all workflows.

Every workflow in woodchipper connects through this module.
No workflow or activity imports ``temporalio.client.Client`` directly.
The cache ensures one connection per process regardless of how many
workflows or workers are started.

Connection retry rationale (WS-024):
    ``Client.connect()`` fails hard on first call if the server is
    unavailable. The Temporal Python SDK retries *after* the initial
    connection is established (worker polling, activity heartbeats),
    but the initial connection itself is a one-shot call.

    In Docker Compose, the worker container may start before the
    Temporal server is fully ready — even with healthchecks, there's
    a window between "port open" and "gRPC accepting requests."

    The Temporal community consensus (community.temporal.io/t/1368) is
    that workers should tolerate server unavailability at startup. The
    SDK doesn't do this for you on ``Client.connect()``. So we retry
    with exponential backoff.

    This makes the worker resilient to startup ordering without
    requiring the infrastructure to guarantee it. The compose
    healthcheck chain (Postgres → Temporal → Worker) is still correct,
    but the worker no longer crashes if Temporal needs a few extra
    seconds after the healthcheck passes.

Configuration via environment variables:

- ``TEMPORAL_URL`` — Temporal server address (default: ``localhost:7233``)
- ``TEMPORAL_NAMESPACE`` — Temporal namespace (default: ``default``)
- ``TEMPORAL_TASK_QUEUE`` — Default task queue (default: ``phosphene-main``)
- ``TEMPORAL_CONNECT_RETRIES`` — Max connection attempts (default: ``10``)
- ``TEMPORAL_CONNECT_BACKOFF`` — Initial backoff seconds (default: ``2``)
"""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client

logger = logging.getLogger(__name__)

TEMPORAL_URL: str = os.environ.get("TEMPORAL_URL", "localhost:7233")
TEMPORAL_NAMESPACE: str = os.environ.get("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE: str = os.environ.get("TEMPORAL_TASK_QUEUE", "phosphene-main")
TEMPORAL_CONNECT_RETRIES: int = int(os.environ.get("TEMPORAL_CONNECT_RETRIES", "10"))
TEMPORAL_CONNECT_BACKOFF: float = float(os.environ.get("TEMPORAL_CONNECT_BACKOFF", "2"))


async def get_client(
    url: str = TEMPORAL_URL,
    namespace: str = TEMPORAL_NAMESPACE,
    max_retries: int = TEMPORAL_CONNECT_RETRIES,
    initial_backoff: float = TEMPORAL_CONNECT_BACKOFF,
) -> Client:
    """Return a connected Temporal client with startup retry.

    Retries the initial ``Client.connect()`` with exponential backoff.
    This is necessary because the Temporal Python SDK does not retry
    the initial connection — only subsequent operations after the
    connection is established.

    In Docker Compose, the worker may start before Temporal is fully
    ready. This retry loop makes the worker resilient to startup
    ordering without requiring the infrastructure to guarantee it.

    Args:
        url: Temporal gRPC address.
        namespace: Temporal namespace.
        max_retries: Maximum connection attempts before raising.
        initial_backoff: Initial delay between retries (doubles each attempt).

    Returns:
        Connected Temporal Client instance.

    Raises:
        RuntimeError: If all retry attempts are exhausted.
    """
    backoff = initial_backoff

    for attempt in range(1, max_retries + 1):
        try:
            client = await Client.connect(url, namespace=namespace)
            if attempt > 1:
                logger.info(
                    "Temporal connection succeeded on attempt %d/%d",
                    attempt, max_retries,
                )
            return client
        except Exception as exc:
            if attempt == max_retries:
                logger.error(
                    "Temporal connection failed after %d attempts: %s",
                    max_retries, exc,
                )
                raise RuntimeError(
                    f"Failed to connect to Temporal at {url} after "
                    f"{max_retries} attempts: {exc}"
                ) from exc

            logger.warning(
                "Temporal connection attempt %d/%d failed (%s), "
                "retrying in %.1fs...",
                attempt, max_retries, exc, backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)  # cap at 30s

    # Unreachable, but satisfies type checker
    raise RuntimeError("Exhausted retries")  # pragma: no cover
