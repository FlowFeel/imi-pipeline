"""Telegram live board updater for Temporal-backed TaskFlow jobs.

Sends one pinned board message to a Telegram thread, then edits it
in-place as the workflow progresses. This avoids message spam — the
board is always the same message, just updated.

Integration with the OpenClaw message tool:

    # Send initial board message and pin it
    initial_board = await fetch_board(client, workflow_id)
    msg_id = await send_initial_board(chat_id, thread_id, initial_board)

    # Start the updater — edits the message every 30s until done
    asyncio.create_task(
        edit_board_loop(client, workflow_id, chat_id, msg_id, thread_id)
    )

Heartbeat task integration (registered in heartbeat/registry.py):
The ``temporal_board_heartbeat`` task calls this on any active workflow
registered in the active-jobs registry (once T-338 is built).
"""

from __future__ import annotations

import logging
from typing import Any

from phosphene.temporal.board import render_board

logger = logging.getLogger(__name__)


async def edit_board_loop(
    client: Any,
    workflow_id: str,
    chat_id: str | int,
    message_id: str | int,
    thread_id: str | int | None = None,
    poll_interval_seconds: float = 30.0,
    oc_message_tool: Any = None,
) -> None:
    """Edit a Telegram message in-place as the workflow progresses.

    Polls ``TaskFlowWorkflow.get_status()`` every ``poll_interval_seconds``
    and edits the board message via the OpenClaw message tool.

    Stops when the workflow completes or is cancelled.

    Args:
        client: Connected Temporal Client.
        workflow_id: ID of the running TaskFlowWorkflow.
        chat_id: Telegram chat ID to post to.
        message_id: ID of the board message to edit.
        thread_id: Telegram thread/topic ID (forum groups).
        poll_interval_seconds: How often to update the board.
        oc_message_tool: The OC ``message`` tool callable. If None,
            logs the board to INFO only (useful in tests).
    """

    async def _edit(board_text: str) -> None:
        """Edit the board message with updated content."""
        if oc_message_tool is None:
            logger.info("Board (no OC tool):\n%s", board_text)
            return

        try:
            await oc_message_tool(
                action="edit",
                channel="telegram",
                message_id=str(message_id),
                message=f"```\n{board_text}\n```",
                chat_id=str(chat_id),
                **({"thread_id": str(thread_id)} if thread_id else {}),
            )
        except Exception as exc:
            logger.warning("Failed to edit board message: %s", exc)

    from phosphene.temporal.board import poll_and_render

    await poll_and_render(
        client=client,
        workflow_id=workflow_id,
        poll_interval_seconds=poll_interval_seconds,
        on_update=_edit,
    )


async def post_initial_board(
    workflow_id: str,
    title: str,
    total_steps: int,
    oc_message_tool: Any,
    chat_id: str | int,
    thread_id: str | int | None = None,
) -> str | None:
    """Post the initial pending board message to Telegram.

    Sends a board showing all steps as PENDING before the workflow starts.
    Returns the message ID for use with ``edit_board_loop``.

    Args:
        workflow_id: ID of the workflow about to start.
        title: Job title for the board header.
        total_steps: Number of steps (all shown as pending).
        oc_message_tool: The OC ``message`` tool callable.
        chat_id: Telegram chat ID.
        thread_id: Telegram thread/topic ID (forum groups).

    Returns:
        Message ID string, or None if send failed.
    """
    from phosphene.temporal.board import BoardStatus

    initial = BoardStatus(
        workflow_id=workflow_id,
        title=title,
        step_states={i: "pending" for i in range(total_steps)},
        completed=0,
        total=total_steps,
        failed=[],
        is_done=False,
    )
    board_text = render_board(initial)

    try:
        result = await oc_message_tool(
            action="send",
            channel="telegram",
            target=str(chat_id),
            message=f"```\n{board_text}\n```",
            **({"thread_id": str(thread_id)} if thread_id else {}),
        )
        return result.get("messageId") if isinstance(result, dict) else None
    except Exception as exc:
        logger.warning("Failed to post initial board: %s", exc)
        return None
