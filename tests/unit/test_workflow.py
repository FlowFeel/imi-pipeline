"""Tests for SyndicationSagaWorkflow — updated for v3 dynamic outlet saga.

v3 workflow returns a dict (asdict(SyndicationResult)) with outlet_results
keyed by outlet name, not fixed fields like wordpress_url/salesforce_id.

Verifies:
1. Workflow is importable
2. All activities succeed → result["succeeded"]=True, outlet_results populated
3. Salesforce fails → WordPress compensation fires → succeeded=False
4. Compensation order is LIFO (registry order: WP→SF→MW; SF fail → WP comp)

Uses WorkflowEnvironment.start_time_skipping() with mock activities
registered by name — no real HTTP, no real outlets.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import asdict

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from phosphene.imi.request import SyndicationRequest

# ---------------------------------------------------------------------------
# Test request — minimal SyndicationRequest for workflow tests
# ---------------------------------------------------------------------------

TEST_REQUEST = asdict(SyndicationRequest(
    title="IMI Integration Test — Cave Behaviours v8",
    body="Integration test article. Do not publish.",
))


# ---------------------------------------------------------------------------
# Helpers — per-test activity factories to avoid shared-state pollution
# ---------------------------------------------------------------------------


def _make_activities(comp_log: list[str]):
    """Build fresh mock activities that log compensations into comp_log."""

    @activity.defn(name="publish_wordpress")
    async def mock_publish_wordpress(request: dict) -> str:
        return "https://independentmediainstitute.org/imi_registry/test/"

    @activity.defn(name="publish_mediawiki")
    async def mock_publish_mediawiki(request: dict) -> str:
        return "Draft:IMI Integration Test"

    @activity.defn(name="sync_salesforce")
    async def mock_sync_salesforce(request: dict) -> str:
        return "a1e00000000001"

    @activity.defn(name="send_pardot_email")
    async def mock_send_pardot_email(request: dict) -> str:
        return "pardot-skipped"

    @activity.defn(name="delete_wordpress_post")
    async def mock_delete_wordpress_post(url: str) -> None:
        comp_log.append(f"DELETE_WP:{url}")

    @activity.defn(name="delete_mediawiki_page")
    async def mock_delete_mediawiki_page(page: str) -> None:
        comp_log.append(f"DELETE_MW:{page}")

    @activity.defn(name="delete_salesforce_record")
    async def mock_delete_salesforce_record(sf_id: str) -> None:
        comp_log.append(f"DELETE_SF:{sf_id}")

    @activity.defn(name="noop_compensation")
    async def mock_noop_compensation(artifact: str) -> None:
        comp_log.append(f"NOOP:{artifact}")

    return [
        mock_publish_wordpress,
        mock_publish_mediawiki,
        mock_sync_salesforce,
        mock_send_pardot_email,
        mock_delete_wordpress_post,
        mock_delete_mediawiki_page,
        mock_delete_salesforce_record,
        mock_noop_compensation,
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyndicationSagaWorkflow:
    """SyndicationSagaWorkflow orchestrates IMI outlets with Saga compensation."""

    def test_workflow_is_importable(self) -> None:
        """The workflow module and class are importable."""
        from phosphene.imi.workflow import SyndicationSagaWorkflow

        assert SyndicationSagaWorkflow is not None

    def test_activities_are_importable(self) -> None:
        """The activities module and class are importable."""
        from phosphene.imi.activities import SyndicationActivities

        assert SyndicationActivities is not None

    def test_syndication_result_is_importable(self) -> None:
        """SyndicationResult dataclass is importable from request.py (v3)."""
        from phosphene.imi.request import SyndicationResult

        assert SyndicationResult is not None
        r = SyndicationResult(succeeded=True)
        assert r.succeeded is True
        assert r.compensations_executed == []

    @pytest.mark.asyncio
    async def test_all_activities_succeed(self) -> None:
        """All three outlets succeed → result['succeeded']=True, outlet_results populated."""
        from phosphene.imi.workflow import SyndicationSagaWorkflow

        comp_log: list[str] = []

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-all-succeed",
                workflows=[SyndicationSagaWorkflow],
                activities=_make_activities(comp_log),
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    TEST_REQUEST,
                    id="test-all-succeed",
                    task_queue="test-all-succeed",
                )

        assert result["succeeded"] is True
        assert result["error_message"] == ""
        assert result["compensations_executed"] == []

        outlet_results = result["outlet_results"]
        assert outlet_results["wordpress"]["artifact"] == (
            "https://independentmediainstitute.org/imi_registry/test/"
        )
        assert outlet_results["mediawiki"]["artifact"] == "Draft:IMI Integration Test"
        assert outlet_results["salesforce"]["artifact"] == "a1e00000000001"

    @pytest.mark.asyncio
    async def test_salesforce_failure_triggers_compensation(self) -> None:
        """Salesforce fails → WP compensation fires → succeeded=False.

        Registry order: wordpress → salesforce → mediawiki.
        WP succeeds, SF fails. compensation stack = [(delete_wp, wp_url)].
        LIFO: delete_wp fires. MW never ran.
        """
        from phosphene.imi.workflow import SyndicationSagaWorkflow

        comp_log: list[str] = []

        @activity.defn(name="sync_salesforce")
        async def sf_fail(request: dict) -> str:
            raise RuntimeError("Salesforce rate limit (429)")

        acts = _make_activities(comp_log)
        acts_with_sf_fail = [
            a for a in acts if getattr(a, "__name__", "") != "mock_sync_salesforce"
        ] + [sf_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-sf-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=acts_with_sf_fail,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    TEST_REQUEST,
                    id="test-sf-fail",
                    task_queue="test-sf-fail",
                )

        assert result["succeeded"] is False
        assert result["error_message"]  # non-empty error
        # WP ran (and was compensated); SF failed; MW never ran
        outlet_results = result["outlet_results"]
        assert outlet_results["wordpress"]["succeeded"] is True
        assert outlet_results["salesforce"]["succeeded"] is False
        # Only WP compensation fired (before SF, nothing after)
        assert len(comp_log) == 1
        assert comp_log[0].startswith("DELETE_WP:")
        assert len(result["compensations_executed"]) == 1

    @pytest.mark.asyncio
    async def test_compensation_order_is_reverse(self) -> None:
        """Compensation fires in LIFO: last-succeeded step is first reversed.

        Registry order: wordpress → salesforce → mediawiki.
        WP and SF succeed. MW fails. comp stack = [(delete_wp,..), (delete_sf,..)].
        LIFO: delete_sf first, delete_wp second.
        """
        from phosphene.imi.workflow import SyndicationSagaWorkflow

        comp_log: list[str] = []

        @activity.defn(name="publish_mediawiki")
        async def mw_fail(request: dict) -> str:
            raise RuntimeError("MW unavailable")

        acts = _make_activities(comp_log)
        acts_with_mw_fail = [
            a for a in acts if getattr(a, "__name__", "") != "mock_publish_mediawiki"
        ] + [mw_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-reverse-order",
                workflows=[SyndicationSagaWorkflow],
                activities=acts_with_mw_fail,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    TEST_REQUEST,
                    id="test-reverse-order",
                    task_queue="test-reverse-order",
                )

        # MW compensation came from it failing; WP+SF both succeeded and registered comps
        # LIFO: SF comp first (registered last), then WP comp
        assert comp_log[0].startswith("DELETE_SF:")
        assert comp_log[1].startswith("DELETE_WP:")
        # Result carries the compensations
        assert len(result["compensations_executed"]) == 2
