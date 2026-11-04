"""E2E simulation tests for SyndicationSagaWorkflow — updated for v3.

Simulates the full IMI syndication pipeline using Temporal's
time-skipping test environment with mock activities.  No real HTTP,
no real outlets — pure workflow logic verification.

v3 workflow returns a dict (asdict(SyndicationResult)) with outlet_results
keyed by outlet name.  Registry execution order: WP → SF → MW → pardot.

Test 1: Happy path — all three outlets succeed.
Test 2: Salesforce fails — WP compensation fires (only WP ran before SF).
Test 3: MediaWiki fails — LIFO: SF comp first, then WP comp.
Test 3b: Compensation failure is logged but does not halt the workflow.
Test 4: Article watcher draft extraction from MW parse response.

Uses fixtures from tests/fixtures/ for future MediaWiki integration.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

# ---------------------------------------------------------------------------
# Minimal SyndicationRequest for E2E simulation
# ---------------------------------------------------------------------------
from phosphene.imi.request import SyndicationRequest as _SR
from phosphene.imi.workflow import SyndicationSagaWorkflow

DRAFT = asdict(
    _SR(
        title="Why Care Work Matters",
        body="Care work is foundational to society and the economy.",
        author="Gunnar Rundgren",
        category="Economy",
    )
)


# ---------------------------------------------------------------------------
# Per-test activity factory — avoids global state pollution
# ---------------------------------------------------------------------------


def _make_e2e_activities(comp_log: list[str]) -> list:
    """Build fresh mock activities for the E2E sim tests."""

    @activity.defn(name="publish_wordpress")
    async def mock_wp(request: dict) -> str:
        return (
            "https://independentmediainstitute.org/imi_registry/why-care-work-matters/"
        )

    @activity.defn(name="publish_mediawiki")
    async def mock_mw(request: dict) -> str:
        return "Draft:Why Care Work Matters"

    @activity.defn(name="sync_salesforce")
    async def mock_sf(request: dict) -> str:
        return "a1e000000000SF"

    @activity.defn(name="send_pardot_email")
    async def mock_pardot(request: dict) -> str:
        return "pardot-skipped"

    @activity.defn(name="delete_wordpress_post")
    async def mock_delete_wp(url: str) -> None:
        comp_log.append(f"DELETE_WP:{url}")

    @activity.defn(name="delete_mediawiki_page")
    async def mock_delete_mw(page: str) -> None:
        comp_log.append(f"DELETE_MW:{page}")

    @activity.defn(name="delete_salesforce_record")
    async def mock_delete_sf(sf_id: str) -> None:
        comp_log.append(f"DELETE_SF:{sf_id}")

    @activity.defn(name="noop_compensation")
    async def mock_noop(artifact: str) -> None:
        comp_log.append(f"NOOP:{artifact}")

    return [
        mock_wp,
        mock_mw,
        mock_sf,
        mock_pardot,
        mock_delete_wp,
        mock_delete_mw,
        mock_delete_sf,
        mock_noop,
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestE2ESimulation:
    """End-to-end simulation of the IMI syndication saga."""

    @pytest.mark.asyncio
    async def test_happy_path_all_outlets_succeed(self) -> None:
        """All three outlets succeed → result['succeeded']=True, all artifacts populated.

        v3 returns a dict; outlet artifacts live in result['outlet_results'].
        """
        comp_log: list[str] = []

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="e2e-happy",
                workflows=[SyndicationSagaWorkflow],
                activities=_make_e2e_activities(comp_log),
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    DRAFT,
                    id="e2e-happy",
                    task_queue="e2e-happy",
                )

        assert result["succeeded"] is True
        assert result["compensations_executed"] == []
        assert result["error_message"] == ""
        outlet_results = result["outlet_results"]
        assert outlet_results["wordpress"]["artifact"] == (
            "https://independentmediainstitute.org/imi_registry/why-care-work-matters/"
        )
        assert outlet_results["mediawiki"]["artifact"] == "Draft:Why Care Work Matters"
        assert outlet_results["salesforce"]["artifact"] == "a1e000000000SF"

    @pytest.mark.asyncio
    async def test_salesforce_fails_lifo_compensation(self) -> None:
        """Salesforce fails → LIFO: only WP compensation fires (MW not yet run).

        v3 registry order: WP → SF → MW.  WP succeeds.  SF fails.
        MW never ran.  Compensation = [(delete_wp, wp_url)].  LIFO: delete_wp.
        """
        comp_log: list[str] = []

        @activity.defn(name="sync_salesforce")
        async def mock_sf_fail(request: dict) -> str:
            raise RuntimeError("Salesforce rate limit (429)")

        acts = _make_e2e_activities(comp_log)
        acts_with_sf_fail = [
            a for a in acts if getattr(a, "__name__", "") != "mock_sf"
        ] + [mock_sf_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="e2e-sf-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=acts_with_sf_fail,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    DRAFT,
                    id="e2e-sf-fail",
                    task_queue="e2e-sf-fail",
                )

        assert result["succeeded"] is False
        outlet_results = result["outlet_results"]
        assert outlet_results["wordpress"]["artifact"] == (
            "https://independentmediainstitute.org/imi_registry/why-care-work-matters/"
        )
        assert outlet_results["salesforce"]["succeeded"] is False
        # MW never ran — only WP compensation fires
        assert "mediawiki" not in outlet_results
        assert len(comp_log) == 1
        assert comp_log[0].startswith("DELETE_WP:")
        assert len(result["compensations_executed"]) == 1

    @pytest.mark.asyncio
    async def test_mediawiki_fails_only_wp_and_sf_compensated(self) -> None:
        """MediaWiki fails → LIFO: SF compensated first, then WP.

        v3 registry order: WP → SF → MW.
        WP succeeds, SF succeeds, MW fails.
        Compensation stack = [(delete_wp,..), (delete_sf,..)].  LIFO: delete_sf, delete_wp.
        """
        comp_log: list[str] = []

        @activity.defn(name="publish_mediawiki")
        async def mock_mw_fail(request: dict) -> str:
            raise RuntimeError("MediaWiki connection refused")

        acts = _make_e2e_activities(comp_log)
        acts_with_mw_fail = [
            a for a in acts if getattr(a, "__name__", "") != "mock_mw"
        ] + [mock_mw_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="e2e-mw-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=acts_with_mw_fail,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    DRAFT,
                    id="e2e-mw-fail",
                    task_queue="e2e-mw-fail",
                )

        assert result["succeeded"] is False
        outlet_results = result["outlet_results"]
        assert outlet_results["wordpress"]["artifact"] == (
            "https://independentmediainstitute.org/imi_registry/why-care-work-matters/"
        )
        assert outlet_results["salesforce"]["artifact"] == "a1e000000000SF"
        assert outlet_results["mediawiki"]["succeeded"] is False

        # LIFO: SF compensated first (registered last), then WP
        assert len(comp_log) == 2
        assert comp_log[0].startswith("DELETE_SF:")
        assert comp_log[1].startswith("DELETE_WP:")
        assert len(result["compensations_executed"]) == 2

    @pytest.mark.asyncio
    async def test_compensation_failure_does_not_halt(self) -> None:
        """A failing compensation is logged at CRITICAL but does not prevent
        the workflow from completing. The result carries 'failed:...' in
        compensations_executed — the saga is best-effort on rollback.

        v3 registry order: WP → SF → MW.
        SF fails after WP succeeds.  delete_wp compensation fails.
        Result: succeeded=False, compensations_executed has 1 'failed:...' entry.
        """
        comp_log: list[str] = []

        @activity.defn(name="sync_salesforce")
        async def sf_fail_comp(request: dict) -> str:
            raise RuntimeError("SF unavailable")

        @activity.defn(name="delete_wordpress_post")
        async def wp_delete_fail(url: str) -> None:
            comp_log.append(f"DELETE_WP_FAIL:{url}")
            raise RuntimeError("WP delete also failed")

        acts = _make_e2e_activities(comp_log)
        final_acts = [
            a
            for a in acts
            if getattr(a, "__name__", "") not in ("mock_sf", "mock_delete_wp")
        ] + [sf_fail_comp, wp_delete_fail]

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="e2e-comp-fail",
                workflows=[SyndicationSagaWorkflow],
                activities=final_acts,
            ):
                result = await env.client.execute_workflow(
                    SyndicationSagaWorkflow.run,
                    DRAFT,
                    id="e2e-comp-fail",
                    task_queue="e2e-comp-fail",
                )

        assert result["succeeded"] is False
        # WP ran and succeeded; SF failed; WP compensation fires but also fails
        comps = result["compensations_executed"]
        assert len(comps) == 1
        assert comps[0].startswith("failed:")

    @pytest.mark.skip(
        reason=(
            "Cross-repo import: imi_article_watcher lives in woodchipper "
            "(scripts/feelingflowingbot/heartbeat/). The watcher's ArticleDraft "
            "extraction, the mock_parse_response.json fixture, and the fixture "
            "path (tests/unit/fixtures/) all belong to the woodchipper repo. "
            "Test the watcher's Draft extraction in woodchipper."
        )
    )
    @pytest.mark.asyncio
    async def test_article_watcher_draft_extraction(self) -> None:
        """ArticleDraft is correctly built from a MediaWiki parse response.

        Reads the mock_parse_response.json fixture (same format as the
        Observatory API), extracts wikitext, and verifies the ArticleDraft
        dataclass fields match expected content.

        Imports via importlib.util to reach the watcher module in the
        monorepo scripts tree (namespace packages without __init__.py).
        """
        import importlib.util
        import sys

        mod_name = "imi_article_watcher"
        watcher_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "scripts",
                "feelingflowingbot",
                "heartbeat",
                "imi_article_watcher.py",
            )
        )
        spec = importlib.util.spec_from_file_location(mod_name, watcher_path)
        assert spec and spec.loader
        watcher_mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = watcher_mod
        spec.loader.exec_module(watcher_mod)  # type: ignore[union-attr]
        ArticleDraft = watcher_mod.ArticleDraft

        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        with open(os.path.join(fixtures_dir, "mock_parse_response.json")) as f:
            parse_response = json.load(f)

        # Extract fields the same way the watcher does in run()
        title = parse_response["parse"]["title"]
        content = parse_response["parse"]["wikitext"]["*"]

        draft = ArticleDraft(
            title=title,
            body=content,
            source_url=f"https://observatory.wiki/wiki/{title.replace(' ', '_')}",
        )

        assert draft.title == "Why Care Work Matters"
        assert "Care work is foundational" in draft.body
        assert "Gunnar Rundgren" in draft.body  # Author in template
        assert draft.author == "Observatory"  # Default author
        assert draft.category == "General"  # Default category
        assert draft.source_url == (
            "https://observatory.wiki/wiki/Why_Care_Work_Matters"
        )

    @pytest.mark.asyncio
    async def test_5_human_gate_approve_unblocks_workflow(self) -> None:
        """HumanGateWorkflow pauses then approves synchronously via Temporal Update."""
        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateInput,
            HumanGateWorkflow,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="e2e-gate-5",
                workflows=[HumanGateWorkflow],
            ):
                handle = await env.client.start_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt="Approve SEO package for Why Care Work Matters?",
                        requester="flow",
                        timeout_hours=48,
                    ),
                    id="gate-e2e-5",
                    task_queue="e2e-gate-5",
                )
                result = await handle.execute_update(
                    HumanGateWorkflow.submit_decision,
                    ApprovalRequest(reviewer="Kelly", decision="approve", notes="LGTM"),
                )
                assert result.approved is True
                assert result.reviewer == "Kelly"
                assert result.notes == "LGTM"
                final = await handle.result()
                assert final.approved is True

    @pytest.mark.asyncio
    async def test_6_human_gate_times_out_after_48h(self) -> None:
        """HumanGateWorkflow times out if no reviewer responds (time-skipping)."""
        from phosphene.temporal.workflows.human_gate import (
            HumanGateInput,
            HumanGateWorkflow,
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="e2e-timeout-6",
                workflows=[HumanGateWorkflow],
            ):
                result = await env.client.execute_workflow(
                    HumanGateWorkflow.run,
                    HumanGateInput(
                        prompt="Approve? (will time out)",
                        requester="flow",
                        timeout_hours=48,
                    ),
                    id="gate-e2e-6",
                    task_queue="e2e-timeout-6",
                )
                assert result.approved is False
                assert result.timed_out is True

    @pytest.mark.asyncio
    async def test_7_taskflow_full_pipeline_with_human_gate(self) -> None:
        """Full pipeline: ingest → generate SEO → human gate approval → complete.

        TaskFlowWorkflow executes three steps in dependency order:
        step 0 and step 1 are core/generate (dispatched via mock activity),
        step 2 is core/human-gate (child HumanGateWorkflow).

        The child workflow ID is deterministic:
        ``human-gate-{parent_workflow_id}-step-{step_index}``
        (see taskflow.py ``_execute_human_gate``).
        """
        import asyncio as _asyncio

        from phosphene.temporal.taskflow.models import (
            StepInput,
            StepOutput,
            TaskBrief,
        )
        from phosphene.temporal.workflows.human_gate import (
            ApprovalRequest,
            HumanGateWorkflow,
        )
        from phosphene.temporal.workflows.taskflow import TaskFlowWorkflow
        from temporalio import activity as ta
        from temporalio.service import RPCError

        @ta.defn(name="dispatch_step_activity")
        async def mock_dispatch(step) -> object:
            # step arrives as dict (no typed hint) — access via dict keys
            title = step["title"] if isinstance(step, dict) else step.title
            index = step["index"] if isinstance(step, dict) else step.index
            ta.heartbeat(f"executing: {title}")
            return StepOutput(index=index, succeeded=True, output=f"done:{title}")

        brief = TaskBrief(
            title="Publish: Why Care Work Matters",
            description="Ingest → SEO → Kelly review",
            requester="flow",
            steps=[
                StepInput(
                    index=0,
                    kind="core/generate",
                    title="Ingest article",
                    instruction="Fetch and parse article",
                ),
                StepInput(
                    index=1,
                    kind="core/generate",
                    title="Generate SEO package",
                    instruction="Build SEO metadata",
                    depends_on=[0],
                ),
                StepInput(
                    index=2,
                    kind="core/human-gate",
                    title="Kelly review",
                    instruction="Review SEO package",
                    depends_on=[1],
                ),
            ],
        )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="e2e-tf-7",
                workflows=[TaskFlowWorkflow, HumanGateWorkflow],
                activities=[mock_dispatch],
            ):
                handle = await env.client.start_workflow(
                    TaskFlowWorkflow.run,
                    brief,
                    id="e2e-taskflow-7",
                    task_queue="e2e-tf-7",
                )

                # Wait for the human-gate child workflow to start.
                # Steps 0 and 1 must complete first (activity dispatch),
                # then step 2 spawns the child workflow.
                gate_id = "human-gate-e2e-taskflow-7-step-2"
                gate_handle = env.client.get_workflow_handle(gate_id)

                # Retry loop: the child may not exist yet.
                for _attempt in range(50):
                    try:
                        await gate_handle.execute_update(
                            HumanGateWorkflow.submit_decision,
                            ApprovalRequest(
                                reviewer="Kelly",
                                decision="approve",
                                notes="Ship it",
                            ),
                        )
                        break
                    except RPCError:
                        await _asyncio.sleep(0.1)
                else:
                    pytest.fail(
                        "Human gate child workflow never started within timeout"
                    )

                result = await handle.result()

        assert result.succeeded is True
        assert len(result.step_outputs) == 3
        # Verify step outputs are present for all three steps
        indices = {o.index for o in result.step_outputs}
        assert indices == {0, 1, 2}
        # Step 2 (human gate) should show Kelly's approval
        gate_output = next(o for o in result.step_outputs if o.index == 2)
        assert gate_output.succeeded is True
        assert "Kelly" in gate_output.output
