"""Step definitions for preprint_saga_compensation.feature.

Verifies PreprintDepositSagaWorkflow forward execution and LIFO compensation.
"""

from __future__ import annotations

import asyncio
from typing import Any

from behave import given, then, when
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from phosphene.imi.workflow import PreprintDepositSagaWorkflow


@given('a valid preprint deposit request for "{title}" with DOI "{doi}"')
def step_valid_request(context: Any, title: str, doi: str) -> None:
    context.saga_title = title
    context.saga_doi = doi
    context.crossref_error = None
    context.execution_order = []
    context.comp_log = []
    clean_slug = title.lower().replace(" ", "-")
    doi_suffix = doi.split("/")[-1] if "/" in doi else doi
    context.saga_request = {
        "title": title,
        "primary_author_name": "Deborah Barsky",
        "doi_suffix": doi_suffix,
        "abstract": f"Abstract for {title}",
        "target_url": f"https://ind.media/registry/{clean_slug}",
        "idempotency_key": f"test-{abs(hash(title))}",
    }


@given('Crossref will reject the metadata deposit with "{error_msg}"')
def step_crossref_will_reject(context: Any, error_msg: str) -> None:
    context.crossref_error = error_msg


@when("the preprint publication saga executes")
def step_saga_executes(context: Any) -> None:
    async def _run() -> dict:
        @activity.defn(name="publish_wordpress_preprint")
        async def mock_publish(req: dict) -> dict:
            context.execution_order.append("publish_wordpress_preprint")
            return {
                "post_id": 102,
                "post_url": context.saga_request["target_url"],
                "doi": context.saga_doi,
            }

        @activity.defn(name="deposit_crossref")
        async def mock_deposit(req: dict) -> dict:
            context.execution_order.append("deposit_crossref")
            if context.crossref_error:
                raise RuntimeError(context.crossref_error)
            return {"deposit_id": "cr-dep-9912"}

        @activity.defn(name="poll_crossref_status")
        async def mock_poll(req: dict) -> dict:
            context.execution_order.append("poll_crossref_status")
            return {"status": "success"}

        @activity.defn(name="activate_wordpress_doi")
        async def mock_activate(req: dict) -> dict:
            context.execution_order.append("activate_wordpress_doi")
            return {"status": "active"}

        @activity.defn(name="rollback_wordpress_preprint")
        async def mock_rollback(arg: dict) -> None:
            context.comp_log.append(f"ROLLBACK_WP:{arg.get('post_id')}")

        async with await WorkflowEnvironment.start_time_skipping() as env:
            q = f"queue-{context.saga_request['idempotency_key']}"
            async with Worker(
                env.client,
                task_queue=q,
                workflows=[PreprintDepositSagaWorkflow],
                activities=[
                    mock_publish,
                    mock_deposit,
                    mock_poll,
                    mock_activate,
                    mock_rollback,
                ],
            ):
                return await env.client.execute_workflow(
                    PreprintDepositSagaWorkflow.run,
                    context.saga_request,
                    id=f"wf-{context.saga_request['idempotency_key']}",
                    task_queue=q,
                )

    context.saga_result = asyncio.run(_run())


@then("the saga completes successfully")
def step_saga_succeeds(context: Any) -> None:
    assert context.saga_result.get("succeeded") is True, (
        f"Saga failed: {context.saga_result}"
    )


@then("the preprint post is published to WordPress")
def step_post_published(context: Any) -> None:
    assert "publish_wordpress_preprint" in context.execution_order


@then("the Crossref metadata deposit succeeds")
def step_crossref_succeeds(context: Any) -> None:
    assert "deposit_crossref" in context.execution_order
    assert "poll_crossref_status" in context.execution_order


@then("the DOI status is active")
def step_doi_active(context: Any) -> None:
    assert context.saga_result.get("doi_status") == "active"
    assert "activate_wordpress_doi" in context.execution_order


@then('the saga fails with error containing "{error_fragment}"')
def step_saga_fails(context: Any, error_fragment: str) -> None:
    assert context.saga_result.get("succeeded") is False
    err = context.saga_result.get("error_message", "")
    assert error_fragment in err, f"expected {error_fragment!r} in {err!r}"


@then("the DOI is never activated")
def step_doi_never_activated(context: Any) -> None:
    assert "activate_wordpress_doi" not in context.execution_order


@then("the WordPress preprint post is compensated and rolled back")
def step_post_compensated(context: Any) -> None:
    assert "ROLLBACK_WP:102" in context.comp_log


@then("the DOI status remains pending")
def step_doi_remains_pending(context: Any) -> None:
    assert context.saga_result.get("doi_status") == "pending"
