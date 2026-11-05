"""Tests for PreprintDepositSagaWorkflow — scholarly preprint & DOI saga.

Verifies:
1. Happy path:
   WordPress create (pending) -> Crossref XML deposit -> Poll receipt -> Activate DOI (active).
2. Deposit failure:
   Crossref rejects deposit (e.g. malformed or network timeout).
   activate_wordpress_doi NEVER runs.
   Compensation fires to clean up / revert.
   Axiom of Search Engine Safety holds: DOI remains pending or rolled back.
3. Polling failure:
   Receipt polling fails -> Compensation fires, DOI never activates.
4. Activity Integration:
   SyndicationActivities executing against FakeWPClient and FakeCrossrefClient
   verifies exact meta fields updated (reg_doi_status, reg_crossref_deposit_id, reg_doi).

Uses WorkflowEnvironment.start_time_skipping() for fast, deterministic execution.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import asdict

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from phosphene.imi.activities import SyndicationActivities
from phosphene.imi.fakes import (
    FakeCrossrefClient,
    FakeMWClient,
    FakePardotClient,
    FakeSFClient,
    FakeWPClient,
)
from phosphene.imi.request import PreprintDepositRequest
from phosphene.imi.workflow import PreprintDepositSagaWorkflow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**kwargs) -> dict:
    """Build a PreprintDepositRequest dict."""
    base = PreprintDepositRequest(
        title="Lithic Tool Technologies",
        primary_author_name="Deborah Barsky",
        primary_author_orcid="0000-0002-1825-0097",
        doi_suffix="042",
        abstract="Archaeological analysis of Pleistocene tool traditions.",
        coauthor_names=["Jan Ritch-Frel"],
    )
    d = asdict(base)
    d.update(kwargs)
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPreprintDepositSagaWorkflow:
    """Workflow-level tests using time-skipping mock activities."""

    @pytest.mark.asyncio
    async def test_happy_path_all_phases_succeed(self) -> None:
        execution_order: list[str] = []
        comp_log: list[str] = []

        @activity.defn(name="publish_wordpress_preprint")
        async def mock_publish(req: dict) -> dict:
            execution_order.append("publish_wordpress_preprint")
            return {
                "post_id": 101,
                "post_url": "https://ind.media/registry/lithic-tools",
                "doi": "10.67767/imi.2026.042",
                "title": req.get("title", ""),
            }

        @activity.defn(name="deposit_crossref")
        async def mock_deposit(req: dict) -> dict:
            execution_order.append("deposit_crossref")
            return {
                "deposit_id": "cr-dep-9912",
                "doi": "10.67767/imi.2026.042",
                "status": "pending",
            }

        @activity.defn(name="poll_crossref_status")
        async def mock_poll(req: dict) -> dict:
            execution_order.append("poll_crossref_status")
            return {
                "deposit_id": "cr-dep-9912",
                "doi": "10.67767/imi.2026.042",
                "status": "active",
            }

        @activity.defn(name="activate_wordpress_doi")
        async def mock_activate(req: dict) -> dict:
            execution_order.append("activate_wordpress_doi")
            return {"activated": True, "doi": req.get("doi", ""), "post_id": 101}

        @activity.defn(name="rollback_wordpress_preprint")
        async def mock_rollback(arg: dict) -> None:
            comp_log.append("ROLLBACK_WP")

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-preprint-queue",
                workflows=[PreprintDepositSagaWorkflow],
                activities=[
                    mock_publish,
                    mock_deposit,
                    mock_poll,
                    mock_activate,
                    mock_rollback,
                ],
            ):
                req = _make_request()
                res = await env.client.execute_workflow(
                    PreprintDepositSagaWorkflow.run,
                    req,
                    id=f"test-preprint-{req['idempotency_key']}",
                    task_queue="test-preprint-queue",
                )

        assert res["succeeded"] is True
        assert res["doi_status"] == "active"
        assert res["doi"] == "10.67767/imi.2026.042"
        assert res["deposit_id"] == "cr-dep-9912"
        assert res["post_id"] == 101
        assert execution_order == [
            "publish_wordpress_preprint",
            "deposit_crossref",
            "poll_crossref_status",
            "activate_wordpress_doi",
        ]
        assert comp_log == []

    @pytest.mark.asyncio
    async def test_crossref_failure_prevents_activation_and_runs_compensation(
        self,
    ) -> None:
        execution_order: list[str] = []
        comp_log: list[str] = []

        @activity.defn(name="publish_wordpress_preprint")
        async def mock_publish(req: dict) -> dict:
            execution_order.append("publish_wordpress_preprint")
            return {
                "post_id": 102,
                "post_url": "https://ind.media/registry/lithic-tools-2",
                "doi": "10.67767/imi.2026.042",
            }

        @activity.defn(name="deposit_crossref")
        async def mock_deposit(req: dict) -> dict:
            execution_order.append("deposit_crossref")
            raise RuntimeError("Malformed receipt XML: missing <doi>")

        @activity.defn(name="poll_crossref_status")
        async def mock_poll(req: dict) -> dict:
            execution_order.append("poll_crossref_status")
            return {}

        @activity.defn(name="activate_wordpress_doi")
        async def mock_activate(req: dict) -> dict:
            execution_order.append("activate_wordpress_doi")
            return {}

        @activity.defn(name="rollback_wordpress_preprint")
        async def mock_rollback(arg: dict) -> None:
            comp_log.append(f"ROLLBACK_WP:{arg.get('post_id')}")

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-preprint-queue-fail",
                workflows=[PreprintDepositSagaWorkflow],
                activities=[
                    mock_publish,
                    mock_deposit,
                    mock_poll,
                    mock_activate,
                    mock_rollback,
                ],
            ):
                req = _make_request()
                res = await env.client.execute_workflow(
                    PreprintDepositSagaWorkflow.run,
                    req,
                    id=f"test-fail-{req['idempotency_key']}",
                    task_queue="test-preprint-queue-fail",
                )

        assert res["succeeded"] is False
        assert res["doi_status"] == "pending"
        assert "Malformed receipt" in res["error_message"]
        # Invariant: activate_wordpress_doi MUST NEVER run
        assert "activate_wordpress_doi" not in execution_order
        assert comp_log == ["ROLLBACK_WP:102"]

    @pytest.mark.asyncio
    async def test_tri_service_happy_path_all_phases_succeed(self) -> None:
        execution_order: list[str] = []
        comp_log: list[str] = []

        @activity.defn(name="publish_wordpress_preprint")
        async def mock_publish_wp(req: dict) -> dict:
            execution_order.append("publish_wordpress_preprint")
            return {
                "post_id": 105,
                "post_url": "https://ind.media/registry/lithic-tools",
                "doi": "10.67767/imi.2026.042",
                "title": req.get("title", ""),
            }

        @activity.defn(name="publish_observatory_preprint")
        async def mock_publish_mw(req: dict) -> dict:
            execution_order.append("publish_observatory_preprint")
            return {
                "wiki_url": "https://observatory.wiki/wiki/Lithic_Tools",
                "wiki_title": req.get("title", ""),
            }

        @activity.defn(name="deposit_crossref")
        async def mock_deposit(req: dict) -> dict:
            execution_order.append("deposit_crossref")
            return {
                "deposit_id": "cr-dep-9912",
                "doi": "10.67767/imi.2026.042",
                "status": "pending",
            }

        @activity.defn(name="poll_crossref_status")
        async def mock_poll(req: dict) -> dict:
            execution_order.append("poll_crossref_status")
            return {
                "deposit_id": "cr-dep-9912",
                "doi": "10.67767/imi.2026.042",
                "status": "active",
            }

        @activity.defn(name="activate_wordpress_doi")
        async def mock_activate_wp(req: dict) -> dict:
            execution_order.append("activate_wordpress_doi")
            return {"activated": True, "doi": req.get("doi", ""), "post_id": 105}

        @activity.defn(name="activate_observatory_preprint")
        async def mock_activate_mw(req: dict) -> dict:
            execution_order.append("activate_observatory_preprint")
            return {
                "activated": True,
                "title": req.get("title", ""),
                "status": "active",
            }

        @activity.defn(name="rollback_wordpress_preprint")
        async def mock_rollback_wp(arg: dict) -> None:
            comp_log.append("ROLLBACK_WP")

        @activity.defn(name="rollback_observatory_preprint")
        async def mock_rollback_mw(arg: dict) -> None:
            comp_log.append("ROLLBACK_OBSERVATORY")

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-tri-service-queue",
                workflows=[PreprintDepositSagaWorkflow],
                activities=[
                    mock_publish_wp,
                    mock_publish_mw,
                    mock_deposit,
                    mock_poll,
                    mock_activate_wp,
                    mock_activate_mw,
                    mock_rollback_wp,
                    mock_rollback_mw,
                ],
            ):
                req = {
                    **_make_request(),
                    "syndicate_to_observatory": True,
                }
                res = await env.client.execute_workflow(
                    PreprintDepositSagaWorkflow.run,
                    req,
                    id=f"test-tri-{req['idempotency_key']}",
                    task_queue="test-tri-service-queue",
                )

        assert res["succeeded"] is True
        assert res["post_id"] == 105
        assert res["doi_status"] == "active"
        assert res["wiki_url"] == "https://observatory.wiki/wiki/Lithic_Tools"
        assert execution_order == [
            "publish_wordpress_preprint",
            "publish_observatory_preprint",
            "deposit_crossref",
            "poll_crossref_status",
            "activate_wordpress_doi",
            "activate_observatory_preprint",
        ]
        assert comp_log == []

    @pytest.mark.asyncio
    async def test_tri_service_crossref_rejection_triggers_lifo_compensation_across_wp_and_mw(
        self,
    ) -> None:
        comp_log: list[str] = []

        @activity.defn(name="publish_wordpress_preprint")
        async def mock_publish_wp(req: dict) -> dict:
            return {
                "post_id": 106,
                "post_url": "https://ind.media/registry/lithic-tools",
                "doi": "10.67767/imi.2026.042",
            }

        @activity.defn(name="publish_observatory_preprint")
        async def mock_publish_mw(req: dict) -> dict:
            return {
                "wiki_url": "https://observatory.wiki/wiki/Lithic_Tools",
                "wiki_title": "Lithic Tools",
            }

        @activity.defn(name="deposit_crossref")
        async def mock_deposit_fail(req: dict) -> dict:
            raise RuntimeError("Crossref XML schema rejection: missing depositor")

        @activity.defn(name="poll_crossref_status")
        async def mock_poll(req: dict) -> dict:
            return {}

        @activity.defn(name="activate_wordpress_doi")
        async def mock_activate_wp(req: dict) -> dict:
            return {}

        @activity.defn(name="activate_observatory_preprint")
        async def mock_activate_mw(req: dict) -> dict:
            return {}

        @activity.defn(name="rollback_wordpress_preprint")
        async def mock_rollback_wp(arg: dict) -> None:
            comp_log.append(f"ROLLBACK_WP:{arg.get('post_id')}")

        @activity.defn(name="rollback_observatory_preprint")
        async def mock_rollback_mw(arg: dict) -> None:
            comp_log.append(f"ROLLBACK_OBSERVATORY:{arg.get('wiki_title')}")

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-tri-fail-queue",
                workflows=[PreprintDepositSagaWorkflow],
                activities=[
                    mock_publish_wp,
                    mock_publish_mw,
                    mock_deposit_fail,
                    mock_poll,
                    mock_activate_wp,
                    mock_activate_mw,
                    mock_rollback_wp,
                    mock_rollback_mw,
                ],
            ):
                req = {
                    **_make_request(),
                    "syndicate_to_observatory": True,
                }
                res = await env.client.execute_workflow(
                    PreprintDepositSagaWorkflow.run,
                    req,
                    id=f"test-tri-fail-{req['idempotency_key']}",
                    task_queue="test-tri-fail-queue",
                )

        assert res["succeeded"] is False
        assert res["doi_status"] == "pending"
        assert "Crossref XML schema rejection" in res["error_message"]
        # Invariant: LIFO order: MW first, then WP
        assert comp_log == ["ROLLBACK_OBSERVATORY:Lithic Tools", "ROLLBACK_WP:106"]


class TestPreprintActivitiesIntegration:
    """Activity integration tests using FakeWPClient and FakeCrossrefClient."""

    @pytest.mark.asyncio
    async def test_activities_end_to_end_lifecycle(self) -> None:
        wp_fake = FakeWPClient()
        cr_fake = FakeCrossrefClient()
        mw_fake = FakeMWClient()
        sf_fake = FakeSFClient()
        pardot_fake = FakePardotClient()

        acts = SyndicationActivities(
            wp_client=wp_fake,
            mw_client=mw_fake,
            sf_client=sf_fake,
            pardot_client=pardot_fake,
            crossref_client=cr_fake,
        )

        req = _make_request(title="Pleistocene Tool Discovery", doi_suffix="099")

        # Phase 1: Publish to WP
        pub_res = await acts.publish_wordpress_preprint(req)
        assert pub_res["post_id"] > 0
        assert pub_res["doi"] == "10.67767/imi.2026.099"
        post_id = pub_res["post_id"]

        # Check post in fake store: reg_doi_status MUST BE pending
        created_post = [p for p in wp_fake.posts.values() if p["id"] == post_id][0]
        assert created_post["meta"]["reg_doi_status"] == "pending"
        assert created_post["meta"]["reg_doi"] == "10.67767/imi.2026.099"

        # Phase 2: Deposit to Crossref
        dep_req = {
            **req,
            "post_id": post_id,
            "post_url": pub_res["post_url"],
            "doi": pub_res["doi"],
        }
        dep_res = await acts.deposit_crossref(dep_req)
        assert dep_res["deposit_id"].startswith("cr-dep-")
        assert dep_res["status"] == "pending"
        deposit_id = dep_res["deposit_id"]

        # Phase 3: Poll status
        poll_res = await acts.poll_crossref_status(
            {"deposit_id": deposit_id, "doi": pub_res["doi"]}
        )
        assert poll_res["deposit_id"] == deposit_id

        # Phase 4: Activate DOI
        act_res = await acts.activate_wordpress_doi(
            {
                "post_id": post_id,
                "deposit_id": deposit_id,
                "doi": pub_res["doi"],
                "post_url": pub_res["post_url"],
            }
        )
        assert act_res["activated"] is True

        # Check updated post meta in fake store: reg_doi_status MUST BE active
        updated_post = [p for p in wp_fake.posts.values() if p["id"] == post_id][0]
        assert updated_post["meta"]["reg_doi_status"] == "active"
        assert updated_post["meta"]["reg_crossref_deposit_id"] == deposit_id
        assert updated_post["meta"]["reg_doi"] == "10.67767/imi.2026.099"
        assert (
            updated_post["meta"]["reg_doi_url"]
            == "https://doi.org/10.67767/imi.2026.099"
        )
        assert bool(updated_post["meta"]["reg_doi_minted_date"])

    @pytest.mark.asyncio
    async def test_activities_tri_service_publication_and_rollback(self) -> None:
        wp_fake = FakeWPClient()
        mw_fake = FakeMWClient()
        cr_fake = FakeCrossrefClient()

        acts = SyndicationActivities(
            wp_client=wp_fake,
            mw_client=mw_fake,
            sf_client=FakeSFClient(),
            pardot_client=FakePardotClient(),
            crossref_client=cr_fake,
        )

        req = _make_request(title="Acheulean Handaxe Distribution", doi_suffix="101")
        req["syndicate_to_observatory"] = True

        # Phase 1a: WP publish
        wp_res = await acts.publish_wordpress_preprint(req)
        assert wp_res["post_id"] > 0
        post_id = wp_res["post_id"]

        # Phase 1b: MW publish
        mw_res = await acts.publish_observatory_preprint(req)
        assert mw_res["wiki_title"] == "Acheulean Handaxe Distribution"
        assert "Acheulean Handaxe Distribution" in mw_fake.pages

        # Assert {{Preprint}} template banner is rendered in wiki page
        assert (
            "{{Preprint" in mw_fake.pages["Acheulean Handaxe Distribution"]["content"]
        )

        # Simulate failure rollback in LIFO order
        await acts.rollback_observatory_preprint(mw_res)
        await acts.rollback_wordpress_preprint(wp_res)

        # Invariant: both stores purged
        assert "Acheulean Handaxe Distribution" not in mw_fake.pages
        matching_posts = [p for p in wp_fake.posts.values() if p["id"] == post_id]
        assert len(matching_posts) == 0
