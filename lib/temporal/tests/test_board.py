"""Tests for phosphene.temporal.board — live Temporal polling board.

Verifies BoardStatus construction, render_board formatting,
fetch_board query handling, and poll_and_render loop termination.
No real Temporal server needed — uses mocked query responses.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from phosphene.temporal.board import BoardStatus, fetch_board, render_board


class TestBoardStatus:
    """BoardStatus dataclass carries correct fields."""

    def test_construction(self) -> None:
        """BoardStatus can be constructed with all fields."""
        status = BoardStatus(
            workflow_id="wf-001",
            title="My Job",
            step_states={0: "complete", 1: "active", 2: "pending"},
            completed=1,
            total=3,
            failed=[],
        )
        assert status.workflow_id == "wf-001"
        assert status.completed == 1
        assert not status.is_done

    def test_is_done_default_false(self) -> None:
        """is_done defaults to False."""
        status = BoardStatus(
            workflow_id="x",
            title="X",
            step_states={},
            completed=0,
            total=0,
            failed=[],
        )
        assert status.is_done is False


class TestRenderBoard:
    """render_board produces formatted board string."""

    def test_renders_title(self) -> None:
        """Board includes the job title."""
        status = BoardStatus(
            workflow_id="wf-001",
            title="Observatory refactor",
            step_states={0: "complete", 1: "active"},
            completed=1,
            total=2,
            failed=[],
        )
        board = render_board(status)
        assert "Observatory refactor" in board

    def test_renders_step_icons(self) -> None:
        """Board includes status icons for each step."""
        status = BoardStatus(
            workflow_id="wf-001",
            title="T",
            step_states={0: "complete", 1: "active", 2: "pending"},
            completed=1,
            total=3,
            failed=[],
        )
        board = render_board(status)
        assert "✅" in board
        assert "🔄" in board
        assert "⏳" in board

    def test_renders_progress_bar(self) -> None:
        """Board includes progress bar and percentage."""
        status = BoardStatus(
            workflow_id="wf-001",
            title="T",
            step_states={0: "complete", 1: "complete"},
            completed=2,
            total=2,
            failed=[],
        )
        board = render_board(status)
        assert "100%" in board

    def test_renders_failed_steps(self) -> None:
        """Board includes failed step indices when present."""
        status = BoardStatus(
            workflow_id="wf-001",
            title="T",
            step_states={0: "complete", 1: "failed"},
            completed=1,
            total=2,
            failed=[1],
        )
        board = render_board(status)
        assert "Failed" in board or "⚠️" in board

    def test_empty_step_states(self) -> None:
        """Board renders cleanly with no steps."""
        status = BoardStatus(
            workflow_id="wf-001",
            title="Empty job",
            step_states={},
            completed=0,
            total=0,
            failed=[],
        )
        board = render_board(status)
        assert "Empty job" in board
        assert "0/0" in board


class TestFetchBoard:
    """fetch_board queries a running workflow and returns BoardStatus."""

    @pytest.mark.asyncio
    async def test_fetch_board_calls_query(self) -> None:
        """fetch_board calls get_status query on the workflow handle."""
        mock_client = MagicMock()
        mock_handle = AsyncMock()
        mock_handle.query.return_value = {
            "step_states": {"0": "complete", "1": "active"},
            "completed": 1,
            "total": 2,
            "failed": [],
            "title": "Test Job",
        }
        mock_client.get_workflow_handle.return_value = mock_handle

        status = await fetch_board(mock_client, "wf-001")

        mock_client.get_workflow_handle.assert_called_once_with("wf-001")
        mock_handle.query.assert_called_once_with("get_status")
        assert status.completed == 1
        assert status.total == 2
        assert status.title == "Test Job"

    @pytest.mark.asyncio
    async def test_fetch_board_handles_not_found(self) -> None:
        """fetch_board returns is_done=True when workflow not found."""
        from temporalio.client import RPCError
        from temporalio.service import RPCStatusCode

        mock_client = MagicMock()
        mock_handle = AsyncMock()
        err = RPCError("Workflow not found", RPCStatusCode.NOT_FOUND, None)
        mock_handle.query.side_effect = err
        mock_client.get_workflow_handle.return_value = mock_handle

        status = await fetch_board(mock_client, "wf-missing")

        assert status.is_done is True
        assert status.workflow_id == "wf-missing"

    @pytest.mark.asyncio
    async def test_fetch_board_parses_string_keys(self) -> None:
        """fetch_board converts string step_state keys to ints."""
        mock_client = MagicMock()
        mock_handle = AsyncMock()
        mock_handle.query.return_value = {
            "step_states": {"0": "complete", "1": "pending", "2": "pending"},
            "completed": 1,
            "total": 3,
            "failed": [],
            "title": "T",
        }
        mock_client.get_workflow_handle.return_value = mock_handle

        status = await fetch_board(mock_client, "wf-001")
        # Keys are ints, not strings
        assert 0 in status.step_states
        assert status.step_states[0] == "complete"


class TestPollAndRender:
    """poll_and_render loops until workflow is done."""

    @pytest.mark.asyncio
    async def test_stops_when_done(self) -> None:
        """poll_and_render exits when is_done is True."""
        mock_client = MagicMock()
        mock_handle = AsyncMock()
        mock_handle.query.return_value = {
            "step_states": {"0": "complete"},
            "completed": 1,
            "total": 1,
            "failed": [],
            "title": "Done job",
            "is_done": True,
        }
        mock_client.get_workflow_handle.return_value = mock_handle

        updates: list[str] = []

        async def capture(board: str) -> None:
            updates.append(board)

        from phosphene.temporal.board import poll_and_render

        await poll_and_render(
            client=mock_client,
            workflow_id="wf-done",
            poll_interval_seconds=0.01,
            on_update=capture,
        )

        assert len(updates) == 1
        assert "Done job" in updates[0]

    @pytest.mark.asyncio
    async def test_calls_on_update_each_poll(self) -> None:
        """poll_and_render calls on_update after each poll."""
        call_count = 0
        mock_client = MagicMock()
        mock_handle = AsyncMock()

        # First call returns active, second returns done
        mock_handle.query.side_effect = [
            {
                "step_states": {"0": "active"},
                "completed": 0,
                "total": 1,
                "failed": [],
                "title": "T",
                "is_done": False,
            },
            {
                "step_states": {"0": "complete"},
                "completed": 1,
                "total": 1,
                "failed": [],
                "title": "T",
                "is_done": True,
            },
        ]
        mock_client.get_workflow_handle.return_value = mock_handle

        async def capture(board: str) -> None:
            nonlocal call_count
            call_count += 1

        from phosphene.temporal.board import poll_and_render

        await poll_and_render(
            client=mock_client,
            workflow_id="wf-two-polls",
            poll_interval_seconds=0.01,
            on_update=capture,
        )

        assert call_count == 2
