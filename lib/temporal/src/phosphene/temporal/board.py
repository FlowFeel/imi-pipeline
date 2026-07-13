"""Live polling board for Temporal-backed TaskFlow jobs.

Replaces the manifest-file polling pattern with a Temporal Query.
The old pattern: read a JSON manifest from disk, parse step states,
re-render. The failure mode: stale reads when the file is being
written, race conditions between the writer (step executor) and the
reader (board renderer), and no way to query state for a workflow
running on a different host.

``TaskFlowWorkflow.get_status()`` is a ``@workflow.query`` handler.
Queries are synchronous reads of workflow state that do not mutate
history and do not require the workflow to be actively executing.
The Temporal server serves the query from the latest replay state,
so the board always reflects the true step states — not a cached
file that may lag behind.

The board can be rendered to Telegram as an in-place edited message —
one pinned message that updates as steps complete, rather than a stream
of new messages.

Two usage patterns:

1. **On-demand** (``/board`` command in Telegram):
   Call ``fetch_board(client, workflow_id)`` and send the result.

2. **Heartbeat** (auto-update while job is active):
   Call ``start_board_updater(client, workflow_id, chat_id, message_id)``
   which runs a background task that edits the board message every
   ``poll_interval_seconds``.

The board format is compatible with the existing ``board_lines()`` renderer
from ``phosphene.taskflow.oc_board`` — same structure, different data source.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_STATUS_ICON = {
    "pending": "⏳",
    "active": "🔄",
    "complete": "✅",
    "failed": "❌",
    "blocked": "🚫",
    "skipped": "⏭️",
}

_STATUS_LABEL = {
    "pending": "PENDING ",
    "active": "ACTIVE  ",
    "complete": "COMPLETE",
    "failed": "FAILED  ",
    "blocked": "BLOCKED ",
    "skipped": "SKIPPED ",
}


@dataclass
class BoardStatus:
    """Live status fetched from a running TaskFlowWorkflow via Query.

    Attributes:
        workflow_id: The Temporal workflow ID.
        title: Job title from the TaskBrief.
        step_states: Dict of step index → status string.
        completed: Count of completed steps.
        total: Total step count.
        failed: List of failed step indices.
        is_done: True when workflow has reached a terminal state.
    """

    workflow_id: str
    title: str
    step_states: dict[int, str]
    completed: int
    total: int
    failed: list[int]
    is_done: bool = False


async def fetch_board(client: Any, workflow_id: str) -> BoardStatus:
    """Fetch live board status from a running TaskFlowWorkflow.

    Calls the ``get_status`` Query on the workflow and returns a
    ``BoardStatus`` suitable for rendering.

    Args:
        client: Connected Temporal Client.
        workflow_id: ID of the running TaskFlowWorkflow.

    Returns:
        ``BoardStatus`` with current step states.

    Raises:
        temporalio.client.WorkflowNotFoundError: If the workflow does not exist.
        temporalio.client.WorkflowQueryFailedError: If the query fails.
    """
    from temporalio.client import RPCError
    from temporalio.service import RPCStatusCode

    raw = None
    try:
        handle = client.get_workflow_handle(workflow_id)
        raw = await handle.query("get_status")
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            logger.warning("Workflow %r not found — may have completed", workflow_id)
        else:
            raise

    if raw is None:
        return BoardStatus(
            workflow_id=workflow_id,
            title=workflow_id,
            step_states={},
            completed=0,
            total=0,
            failed=[],
            is_done=True,
        )

    step_states: dict[int, str] = {
        int(k): v for k, v in (raw.get("step_states") or {}).items()
    }
    return BoardStatus(
        workflow_id=workflow_id,
        title=raw.get("title", workflow_id),
        step_states=step_states,
        completed=int(raw.get("completed", 0)),
        total=int(raw.get("total", 0)),
        failed=[int(i) for i in (raw.get("failed") or [])],
        is_done=raw.get("is_done", False),
    )

    step_states: dict[int, str] = {
        int(k): v for k, v in (raw.get("step_states") or {}).items()
    }
    return BoardStatus(
        workflow_id=workflow_id,
        title=raw.get("title", workflow_id),
        step_states=step_states,
        completed=int(raw.get("completed", 0)),
        total=int(raw.get("total", 0)),
        failed=[int(i) for i in (raw.get("failed") or [])],
        is_done=raw.get("is_done", False),
    )


def render_board(status: BoardStatus) -> str:
    """Render a BoardStatus as a plain-text polling board.

    Compatible with the existing ``board_lines()`` format from
    ``phosphene.taskflow.oc_board``.

    Args:
        status: Live board status from ``fetch_board()``.

    Returns:
        Formatted board string for Telegram or stdout.
    """
    lines: list[str] = [
        f"📋 {status.title}",
        f"{'─' * 44}",
    ]

    for idx in sorted(status.step_states):
        raw_status = status.step_states[idx]
        icon = _STATUS_ICON.get(raw_status, "❓")
        label = _STATUS_LABEL.get(raw_status, raw_status.upper().ljust(8))
        lines.append(f"  {icon} [{label}] Step {idx:02d}")

    lines.append(f"{'─' * 44}")
    pct = int(status.completed / status.total * 100) if status.total else 0
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    lines.append(f"  Progress: {status.completed}/{status.total}  |{bar}|  {pct}%")

    if status.failed:
        lines.append(f"  ⚠️  Failed steps: {status.failed}")

    return "\n".join(lines)


async def poll_and_render(
    client: Any,
    workflow_id: str,
    poll_interval_seconds: float = 30.0,
    on_update: Any = None,
) -> None:
    """Poll a running workflow and call ``on_update`` with the rendered board.

    Runs until the workflow reaches a terminal state or is cancelled.
    Used by the heartbeat task and the Telegram board updater.

    Args:
        client: Connected Temporal Client.
        workflow_id: ID of the running TaskFlowWorkflow.
        poll_interval_seconds: How often to query the workflow status.
        on_update: Async callable that receives the rendered board string.
            Called after each poll. If None, logs the board to INFO.
    """
    while True:
        try:
            status = await fetch_board(client, workflow_id)
            board = render_board(status)

            if on_update is not None:
                await on_update(board)
            else:
                logger.info("Board update for %r:\n%s", workflow_id, board)

            if status.is_done or (
                status.total > 0 and status.completed == status.total
            ):
                logger.info("Workflow %r complete — stopping board poll", workflow_id)
                break

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Board poll error for %r: %s", workflow_id, exc)

        await asyncio.sleep(poll_interval_seconds)
