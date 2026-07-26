"""Tests for SyndicationSagaWorkflow v3 — dynamic outlet registry saga.

Verifies:
1. Workflow is importable; OUTLET_REGISTRY has all four outlets.
2. Only selected outlets run (non-selected outlets produce no activity calls).
3. All selected outlets succeed → SyndicationResult.succeeded=True with
   outlet_results keyed by outlet name.
4. One outlet fails → compensations fire in LIFO order; succeeded=False.
5. Custom outlet set (e.g. pardot only) runs only that outlet.
6. Unknown outlet in request yields an OutletOutcome with error, saga continues.
7. Compensation failure does not halt the workflow (best-effort).

Uses WorkflowEnvironment.start_time_skipping() with mock activities
registered by name — no real HTTP, no real outlets, no patching.

Registry execution order (OUTLET_REGISTRY): wordpress → salesforce → mediawiki → pardot.
Temporal's Protobuf JSON codec may reorder dict keys alphabetically;
the saga iterates OUTLET_REGISTRY order, not req.outlets.items() order,
to ensure determinism.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import asdict

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from phosphene.imi.request import SyndicationRequest
from phosphene.imi.workflow import SyndicationSagaWorkflow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**kwargs) -> dict:
    """Build a SyndicationRequest dict, allowing field overrides."""
    base = SyndicationRequest(title="Test Article", body="Body text.")
    d = asdict(base)
    d.update(kwargs)
    return d


def _make_activities(comp_log: list[str]) -> list:
    """Build a fresh set of mock activities that log compensations into comp_log.

    Each call returns new activity function objects — avoids cross-test state
    pollution from module-level shared mocks.

    Args:
        comp_log: A list that compensation activities append to.

    Returns:
        List of activity callables registered by name.
    """

    @activity.defn(name="publish_wordpress")
    async def mock_publish_wordpress(request: dict) -> str:
        return "https://wp.test/post/1"

    @activity.defn(name="publish_mediawiki")
    async def mock_publish_mediawiki(request: dict) -> str:
        return "Draft:Test Article"

    @activity.defn(name="sync_salesforce")
    async def mock_sync_salesforce(request: dict) -> str:
        return "SF001"

    @activity.defn(name="send_pardot_email")
    async def mock_send_pardot_email(request: dict) -> str:
        return "pardot-skipped"

    @activity.defn(name="delete_wordpress_post")
    async def mock_delete_wp(artifact: str) -> None:
        comp_log.append(f"DELETE_WP:{artifact}")

    @activity.defn(name="delete_mediawiki_page")
    async def mock_delete_mw(artifact: str) -> None:
        comp_log.append(f"DELETE_MW:{artifact}")

    @activity.defn(name="delete_salesforce_record")
    async def mock_delete_sf(artifact: str) -> None:
        comp_log.append(f"DELETE_SF:{artifact}")

    @activity.defn(name="noop_compensation")
    async def mock_noop_compensation(artifact: str) -> None:
        comp_log.append(f"NOOP:{artifact}")

    return [
        mock_publish_wordpress,
        mock_publish_mediawiki,
        mock_sync_salesforce,
        mock_send_pardot_email,
        mock_delete_wp,
        mock_delete_mw,
        mock_delete_sf,
        mock_noop_compensation,
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyndicationSagaWorkflowV3:
    """SyndicationSagaWorkflow v3 — dynamic outlet-composable saga."""

    def test_workflow_importable(self) -> None:
        """Workflow and OUTLET_REGISTRY are importable."""
        assert SyndicationSagaWorkflow is not None
        reg = SyndicationSagaWorkflow.OUTLET_REGISTRY
        assert "wordpress" in reg
        assert "salesforce" in reg
        assert "mediawiki" in reg
        assert "pardot" in reg

    def test_outlet_registry_structure(self) -> None:
        """Each registry entry is a (forward, compensation) tuple of strings."""
        for name, (fwd, comp) in SyndicationSagaWorkflow.OUTLET_REGISTRY.items():
            assert isinstance(name, str)
            assert isinstance(fwd, str)
            assert isinstance(comp, str)
            assert fwd  # non-empty
            assert comp

    def test_outlet_registry_order(self) -> None:
        """Registry order is wordpress → salesforce → mediawiki → pardot."""
        keys = list(SyndicationSagaWorkflow.OUTLET_REGISTRY.keys())
        assert keys == ["wordpress", "salesforce", "mediawiki", "pardot"]

    @pytest.mark.asyncio
    async def test_all_three_default_outlets_succeed(self) -> None:
        """WP + SF + MW all succeed → succeeded=True, outlet_results has 3 entries."""
        comp_log: list[str] = []
        req = _make_request()  # default: WP, SF, MW selected; pardot off

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-all-succeed",
                workflows=[SyndicationSagaWorkflow],
                activities=_make_activities(comp_log),
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-all-succeed",
                    task_queue="v3-all-succeed",
                )

        assert result["succeeded"] is True
        assert result["error_message"] == ""
        assert result["compensations_executed"] == []
        assert comp_log == []  # no compensations on success

        # All three outlets have results
        outlet_results = result["outlet_results"]
        assert "wordpress" in outlet_results
        assert "salesforce" in outlet_results
        assert "mediawiki" in outlet_results
        assert "pardot" not in outlet_results  # pardot was disabled

        assert outlet_results["wordpress"]["succeeded"] is True
        assert outlet_results["wordpress"]["artifact"] == "https://wp.test/post/1"
        assert outlet_results["mediawiki"]["artifact"] == "Draft:Test Article"
        assert outlet_results["salesforce"]["artifact"] == "SF001"

    @pytest.mark.asyncio
    async def test_only_selected_outlets_run(self) -> None:
        """Request with only salesforce=True runs only SF; WP and MW results absent."""
        comp_log: list[str] = []
        req = _make_request(
            outlets={
                "wordpress": False,
                "salesforce": True,
                "mediawiki": False,
                "pardot": False,
            }
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-sf-only",
                workflows=[SyndicationSagaWorkflow],
                activities=_make_activities(comp_log),
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-sf-only",
                    task_queue="v3-sf-only",
                )

        assert result["succeeded"] is True
        outlet_results = result["outlet_results"]
        assert "salesforce" in outlet_results
        assert outlet_results["salesforce"]["succeeded"] is True
        assert "wordpress" not in outlet_results
        assert "mediawiki" not in outlet_results

    @pytest.mark.asyncio
    async def test_pardot_only_runs_send_pardot_and_noop_comp(self) -> None:
        """Request with only pardot=True runs send_pardot_email."""
        comp_log: list[str] = []
        req = _make_request(
            outlets={
                "wordpress": False,
                "salesforce": False,
                "mediawiki": False,
                "pardot": True,
            }
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-pardot-only",
                workflows=[SyndicationSagaWorkflow],
                activities=_make_activities(comp_log),
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-pardot-only",
                    task_queue="v3-pardot-only",
                )

        assert result["succeeded"] is True
        outlet_results = result["outlet_results"]
        assert "pardot" in outlet_results
        assert outlet_results["pardot"]["succeeded"] is True
        assert outlet_results["pardot"]["artifact"] == "pardot-skipped"

    @pytest.mark.asyncio
    async def test_salesforce_failure_triggers_lifo_compensation(self) -> None:
        """SF fails after WP succeeds → LIFO: only WP compensated (MW not yet run).

        Registry order: wordpress → salesforce → mediawiki → pardot.
        WP succeeds and registers its compensation.  SF fails.
        MW never runs.  Compensation stack = [(delete_wp, wp_url)].
        Reversed (LIFO): delete_wp fires.
        """
        comp_log: list[str] = []

        req = _make_request()  # WP, SF, MW selected

        @activity.defn(name="sync_salesforce")
        async def sf_fail(request: dict) -> str:
            raise RuntimeError("Salesforce rate limit (429)")

        # Rebuild activities but override sync_salesforce
        acts = _make_activities(comp_log)
        # Replace the sync_salesforce slot with sf_fail
        acts = [
            a
            for a in acts
            if getattr(a, "__name__", str(a)) not in ("mock_sync_salesforce",)
        ]
        acts_with_sf_fail = [*acts, sf_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-sf-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=acts_with_sf_fail,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-sf-fail",
                    task_queue="v3-sf-fail",
                )

        assert result["succeeded"] is False
        assert "salesforce" in result["error_message"]

        # LIFO: WP ran first (succeeded), then SF failed before MW ran.
        # Compensation stack = [(delete_wp, wp_url)]; reversed: delete_wp only.
        assert len(comp_log) == 1
        assert comp_log[0].startswith("DELETE_WP:")

        assert len(result["compensations_executed"]) == 1
        assert result["compensations_executed"][0] == "ok"

    @pytest.mark.asyncio
    async def test_mediawiki_failure_lifo_compensation(self) -> None:
        """MW fails after WP+SF succeed → LIFO: SF compensated first, then WP.

        Registry order: wordpress → salesforce → mediawiki.
        WP succeeds, SF succeeds, MW fails.
        Compensation stack = [(delete_wp, wp_url), (delete_sf, sf_id)].
        Reversed (LIFO): delete_sf first, delete_wp second.
        """
        comp_log: list[str] = []

        req = _make_request()  # WP, SF, MW selected

        @activity.defn(name="publish_mediawiki")
        async def mw_fail(request: dict) -> str:
            raise RuntimeError("MediaWiki connection refused")

        acts = _make_activities(comp_log)
        acts_with_mw_fail = [
            a
            for a in acts
            if getattr(a, "__name__", "") not in ("mock_publish_mediawiki",)
        ] + [mw_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-mw-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=acts_with_mw_fail,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-mw-fail",
                    task_queue="v3-mw-fail",
                )

        assert result["succeeded"] is False
        assert "mediawiki" in result["error_message"]

        # LIFO: WP→SF succeeded, MW failed.
        # Compensation stack = [(delete_wp, ...), (delete_sf, ...)].
        # Reversed: delete_sf first, delete_wp second.
        assert len(comp_log) == 2
        assert comp_log[0].startswith("DELETE_SF:")
        assert comp_log[1].startswith("DELETE_WP:")
        assert len(result["compensations_executed"]) == 2

    @pytest.mark.asyncio
    async def test_wordpress_failure_no_compensation(self) -> None:
        """WP fails on first step → no compensations fired (nothing succeeded yet)."""
        comp_log: list[str] = []

        req = _make_request()

        @activity.defn(name="publish_wordpress")
        async def wp_fail(request: dict) -> str:
            raise RuntimeError("WordPress connection refused")

        acts = _make_activities(comp_log)
        acts_with_wp_fail = [
            a
            for a in acts
            if getattr(a, "__name__", "") not in ("mock_publish_wordpress",)
        ] + [wp_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-wp-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=acts_with_wp_fail,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-wp-fail",
                    task_queue="v3-wp-fail",
                )

        assert result["succeeded"] is False
        # No compensations — WP failed before registering any
        assert result["compensations_executed"] == []
        assert comp_log == []

    @pytest.mark.asyncio
    async def test_compensation_failure_does_not_halt_workflow(self) -> None:
        """A failing compensation is logged but the workflow completes normally.

        Registry order: wordpress → salesforce → mediawiki → pardot.
        We use WP disabled so the order is: salesforce → mediawiki → pardot.
        SF succeeds, MW succeeds, pardot fails.
        LIFO: delete_mw (fails), delete_sf (succeeds).
        Both compensation outcomes are captured; workflow returns succeeded=False.
        """
        comp_log: list[str] = []

        # Enable SF + MW + pardot; disable WP so order = SF, MW, pardot
        req = _make_request(
            outlets={
                "wordpress": False,
                "salesforce": True,
                "mediawiki": True,
                "pardot": True,
            }
        )

        @activity.defn(name="send_pardot_email")
        async def pardot_fail(request: dict) -> str:
            raise RuntimeError("Pardot unavailable")

        @activity.defn(name="delete_mediawiki_page")
        async def mw_delete_fail(artifact: str) -> None:
            comp_log.append(f"DELETE_MW_FAIL:{artifact}")
            raise RuntimeError("MW delete also failed")

        acts = _make_activities(comp_log)
        final_acts = [
            a
            for a in acts
            if getattr(a, "__name__", "")
            not in ("mock_send_pardot_email", "mock_delete_mw")
        ] + [pardot_fail, mw_delete_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-comp-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=final_acts,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-comp-fail",
                    task_queue="v3-comp-fail",
                )

        assert result["succeeded"] is False
        # LIFO compensation: MW first (fails), then SF (succeeds)
        comps = result["compensations_executed"]
        assert len(comps) == 2
        assert comps[0].startswith("failed:")  # MW delete failed
        assert comps[1] == "ok"  # SF delete succeeded

    @pytest.mark.asyncio
    async def test_no_outlets_selected_returns_success_empty(self) -> None:
        """All outlets disabled → saga completes with succeeded=True, empty results."""
        comp_log: list[str] = []
        req = _make_request(
            outlets={
                "wordpress": False,
                "salesforce": False,
                "mediawiki": False,
                "pardot": False,
            }
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-no-outlets",
                workflows=[SyndicationSagaWorkflow],
                activities=_make_activities(comp_log),
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-no-outlets",
                    task_queue="v3-no-outlets",
                )

        assert result["succeeded"] is True
        assert result["outlet_results"] == {}
        assert result["compensations_executed"] == []
        assert comp_log == []

    @pytest.mark.asyncio
    async def test_unknown_outlet_recorded_as_error_saga_continues(self) -> None:
        """An unknown outlet name is recorded with error; remaining outlets continue."""
        comp_log: list[str] = []
        req = _make_request(outlets={"unknown_outlet": True, "salesforce": True})

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="v3-unknown-outlet",
                workflows=[SyndicationSagaWorkflow],
                activities=_make_activities(comp_log),
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    req,
                    id="v3-unknown-outlet",
                    task_queue="v3-unknown-outlet",
                )

        # Unknown outlet recorded as error
        assert "unknown_outlet" in result["outlet_results"]
        assert result["outlet_results"]["unknown_outlet"]["succeeded"] is False
        assert "Unknown outlet" in result["outlet_results"]["unknown_outlet"]["error"]
        # Salesforce still runs and succeeds (it's in OUTLET_REGISTRY)
        assert "salesforce" in result["outlet_results"]
        assert result["outlet_results"]["salesforce"]["succeeded"] is True
        # Overall reported as succeeded (unknown outlet doesn't trigger compensation)
        assert result["succeeded"] is True
