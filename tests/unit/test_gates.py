"""Tests for human gate wiring — approve/reject via Temporal Update.

Verifies:
1. approve_gate calls execute_update with correct ApprovalRequest payload
2. reject_gate sends a reject decision
3. get_gate_status queries the workflow prompt
4. gate_cli approve exits 0
5. gate_cli reject exits 1

All tests mock the Temporal client — no real Temporal server needed.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from phosphene.temporal.workflows.human_gate import (
    ApprovalRequest,
    HumanGateResult,
    HumanGateWorkflow,
)


class TestApproveGate:
    """approve_gate submits an 'approve' Update to the HumanGateWorkflow."""

    @pytest.mark.asyncio
    async def test_approve_gate_calls_execute_update_with_correct_payload(
        self,
    ) -> None:
        """approve_gate calls handle.execute_update with decision='approve'."""
        from phosphene.imi.gates import approve_gate

        expected_result = HumanGateResult(approved=True, reviewer="Kelly", notes="LGTM")

        mock_handle = AsyncMock()
        mock_handle.execute_update = AsyncMock(return_value=expected_result)

        mock_client = AsyncMock()
        mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)

        with patch("phosphene.imi.gates.get_client", return_value=mock_client):
            result = await approve_gate(
                workflow_id="gate-seo-123", reviewer="Kelly", notes="LGTM"
            )

        assert result.approved is True
        assert result.reviewer == "Kelly"
        assert result.notes == "LGTM"
        mock_client.get_workflow_handle.assert_called_once_with("gate-seo-123")
        mock_handle.execute_update.assert_called_once()
        call_args = mock_handle.execute_update.call_args
        request = call_args[0][1]  # positional arg after the update method
        assert isinstance(request, ApprovalRequest)
        assert request.decision == "approve"
        assert request.reviewer == "Kelly"
        assert request.notes == "LGTM"


class TestRejectGate:
    """reject_gate submits a 'reject' Update to the HumanGateWorkflow."""

    @pytest.mark.asyncio
    async def test_reject_gate_sends_reject_decision(self) -> None:
        """reject_gate calls handle.execute_update with decision='reject'."""
        from phosphene.imi.gates import reject_gate

        expected_result = HumanGateResult(
            approved=False, reviewer="Kelly", notes="Needs more keywords"
        )

        mock_handle = AsyncMock()
        mock_handle.execute_update = AsyncMock(return_value=expected_result)

        mock_client = AsyncMock()
        mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)

        with patch("phosphene.imi.gates.get_client", return_value=mock_client):
            result = await reject_gate(
                workflow_id="gate-seo-456",
                reviewer="Kelly",
                notes="Needs more keywords",
            )

        assert result.approved is False
        assert result.reviewer == "Kelly"
        assert result.notes == "Needs more keywords"
        call_args = mock_handle.execute_update.call_args
        request = call_args[0][1]
        assert request.decision == "reject"


class TestGetGateStatus:
    """get_gate_status queries the workflow's get_prompt to check gate state."""

    @pytest.mark.asyncio
    async def test_get_gate_status_queries_workflow(self) -> None:
        """get_gate_status returns the prompt from a live gate, or 'closed'."""
        from phosphene.imi.gates import get_gate_status

        mock_handle = AsyncMock()
        mock_handle.query = AsyncMock(return_value="Approve SEO package for article X?")

        mock_client = AsyncMock()
        mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)

        with patch("phosphene.imi.gates.get_client", return_value=mock_client):
            status = await get_gate_status("gate-seo-789")

        assert status == "Approve SEO package for article X?"
        mock_handle.query.assert_called_once_with(HumanGateWorkflow.get_prompt)


class TestGateCliApprove:
    """gate_cli approve command exits 0 on successful approval."""

    def test_gate_cli_approve_exits_0(self) -> None:
        """CLI approve prints JSON result and exits 0."""
        from phosphene.imi import gate_cli

        result = HumanGateResult(approved=True, reviewer="Kelly", notes="LGTM")

        with (
            patch.object(
                sys,
                "argv",
                [
                    "gate_cli",
                    "approve",
                    "gate-seo-123",
                    "--reviewer",
                    "Kelly",
                    "--notes",
                    "LGTM",
                ],
            ),
            patch("phosphene.imi.gate_cli.asyncio_run", return_value=result),
            pytest.raises(SystemExit) as exc_info,
        ):
            gate_cli.main()

        assert exc_info.value.code == 0


class TestGateCliReject:
    """gate_cli reject command exits 1 on rejection."""

    def test_gate_cli_reject_exits_1(self) -> None:
        """CLI reject prints JSON result and exits 1."""
        from phosphene.imi import gate_cli

        result = HumanGateResult(approved=False, reviewer="Kelly", notes="Needs work")

        with (
            patch.object(
                sys,
                "argv",
                [
                    "gate_cli",
                    "reject",
                    "gate-seo-456",
                    "--reviewer",
                    "Kelly",
                    "--notes",
                    "Needs work",
                ],
            ),
            patch("phosphene.imi.gate_cli.asyncio_run", return_value=result),
            pytest.raises(SystemExit) as exc_info,
        ):
            gate_cli.main()

        assert exc_info.value.code == 1
