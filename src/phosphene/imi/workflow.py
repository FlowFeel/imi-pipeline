"""SyndicationSagaWorkflow — dynamic outlet-composable syndication saga.

v3 replaces the hardcoded three-step saga with an outlet registry.
The workflow reads which outlets are selected from the SyndicationRequest
and dispatches only those.  Compensation is still LIFO: the last outlet
to succeed is the first to be reversed.

Design properties preserved from v2:
- Forward-compensation: each successful write registers its rollback.
- LIFO compensation: last-written is first-reversed.
- Best-effort compensation: a failing compensation is logged at CRITICAL
  but does not halt the workflow.  The result carries "failed:{err}" so
  the caller can inspect partial rollback state.

``OUTLET_REGISTRY`` is a ClassVar so it is accessible without
instantiation and is inspectable in tests without running a workflow.

``workflow.unsafe.imports_passed_through()`` scopes non-deterministic
imports (datetime, pydantic) to the import phase.  The workflow body
remains deterministic: no IO, no random, no system clock.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from phosphene.imi.request import (
        OutletOutcome,
        PreprintDepositRequest,
        PreprintDepositResult,
        SyndicationRequest,
        SyndicationResult,
    )


@workflow.defn
class SyndicationSagaWorkflow:
    """Outlet-composable syndication saga.

    The OUTLET_REGISTRY maps outlet name → (forward_activity, compensation_activity).
    ``run()`` iterates only selected outlets (req.outlets[name] == True),
    registers a compensation at the moment each forward activity succeeds,
    and executes compensations in LIFO order on any failure.

    Usage::

        result = await client.execute_workflow(
            SyndicationSagaWorkflow.run,
            asdict(request),          # serialise before dispatch
            id=f"syndication-{request.idempotency_key}",
            task_queue="imi-syndication",
        )
    """

    # Registry: outlet name → (forward_activity_name, compensation_activity_name)
    OUTLET_REGISTRY: ClassVar[dict[str, tuple[str, str]]] = {
        "wordpress": ("publish_wordpress", "delete_wordpress_post"),
        "salesforce": ("sync_salesforce", "delete_salesforce_record"),
        "mediawiki": ("publish_mediawiki", "delete_mediawiki_page"),
        "pardot": ("send_pardot_email", "noop_compensation"),
    }

    @workflow.run
    async def run(self, request: dict) -> dict:
        """Execute the dynamic outlet saga.

        Temporal deserialises workflow inputs as plain dicts by default.
        This method reconstructs the typed SyndicationRequest via
        ``SyndicationRequest.from_dict`` so downstream code stays typed.

        Args:
            request: SyndicationRequest as a plain dict (Temporal-serialised).

        Returns:
            SyndicationResult as a plain dict (Temporal-serialised).
        """
        req = (
            SyndicationRequest.from_dict(request)
            if isinstance(request, dict)
            else request
        )

        retry = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
        )

        compensations: list[tuple[str, str]] = []
        results: dict[str, OutletOutcome] = {}

        # Iterate outlets in REGISTRY order first (deterministic regardless of
        # how Temporal deserialises the outlets dict — protobuf/JSON may reorder
        # keys).  Unknown outlets (in req.outlets but not in REGISTRY) are
        # appended at the end so they still surface as OutletOutcome errors.
        enabled_outlets = {name for name, flag in req.outlets.items() if flag}
        selected = [
            name for name in self.OUTLET_REGISTRY if name in enabled_outlets
        ] + [name for name in enabled_outlets if name not in self.OUTLET_REGISTRY]

        for outlet_name in selected:
            if outlet_name not in self.OUTLET_REGISTRY:
                results[outlet_name] = OutletOutcome(
                    outlet=outlet_name,
                    succeeded=False,
                    error=f"Unknown outlet: {outlet_name}",
                )
                continue

            forward_activity, compensation_activity = self.OUTLET_REGISTRY[outlet_name]

            try:
                artifact = await workflow.execute_activity(
                    forward_activity,
                    request,  # pass full request dict — activity extracts what it needs
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=retry,
                )
                compensations.append((compensation_activity, artifact))
                results[outlet_name] = OutletOutcome(
                    outlet=outlet_name,
                    succeeded=True,
                    artifact=artifact,
                )

            except Exception as exc:
                workflow.logger.error(f"{outlet_name} failed: {exc}")
                results[outlet_name] = OutletOutcome(
                    outlet=outlet_name,
                    succeeded=False,
                    error=str(exc),
                )
                executed = await self._compensate(compensations, retry)
                return asdict(
                    SyndicationResult(
                        succeeded=False,
                        outlet_results=results,
                        error_message=f"{outlet_name}: {exc}",
                        compensations_executed=executed,
                    )
                )

        return asdict(
            SyndicationResult(
                succeeded=True,
                outlet_results=results,
            )
        )

    async def _compensate(
        self,
        compensations: list[tuple[str, str]],
        retry: RetryPolicy,
    ) -> list[str]:
        """Execute compensations in reverse (LIFO) order.

        Best-effort: a failing compensation is logged at CRITICAL but
        does not raise.  The outcome list carries "ok" or "failed:{err}".

        Args:
            compensations: List of (activity_name, artifact) tuples,
                in the order the forward activities succeeded.
            retry: Retry policy for compensation activities.

        Returns:
            Outcome strings, one per compensation attempted.
        """
        outcomes: list[str] = []
        for activity_name, artifact in reversed(compensations):
            try:
                await workflow.execute_activity(
                    activity_name,
                    artifact,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry,
                )
                outcomes.append("ok")
            except Exception as rb_err:
                workflow.logger.critical(
                    f"Compensation {activity_name} failed: {rb_err}"
                )
                outcomes.append(f"failed:{rb_err}")
        return outcomes


@workflow.defn
class PreprintDepositSagaWorkflow:
    """Scholarly preprint publication & Crossref DOI registration saga.

    Executes the 4-phase scholarly publication saga:
    1. publish_wordpress_preprint: Creates or ensures imi_registry post with
       DOI status pending (Axiom of Search Engine Safety: no 404 leaks).
    2. deposit_crossref: Generates Crossref Schema 5.3.1 XML and deposits
       metadata to Crossref.
    3. poll_crossref_status: Verifies deposit receipt and registration status.
    4. activate_wordpress_doi: Transitions DOI status to active, recording
       reg_crossref_deposit_id, reg_doi_minted_date, and enabling citation_doi.

    On failure at steps 2-4:
    Executes LIFO compensation: deletes or demotes the preprint post to pending,
    guaranteeing that unminted DOIs NEVER leak to Google Scholar citation tags.
    """

    @workflow.run
    async def run(self, request: dict) -> dict:
        req = (
            PreprintDepositRequest.from_dict(request)
            if isinstance(request, dict)
            else request
        )
        retry = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
        )

        compensations: list[tuple[str, Any]] = []
        executed_compensations: list[str] = []

        try:
            # Phase 1: Publish to WordPress (pending DOI)
            wp_result = await workflow.execute_activity(
                "publish_wordpress_preprint",
                request,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=retry,
            )
            post_id = wp_result.get("post_id", 0)
            post_url = wp_result.get("post_url", "")
            doi_val = wp_result.get("doi", "")
            compensations.append(("rollback_wordpress_preprint", wp_result))

            # Phase 2: Deposit metadata to Crossref
            deposit_req = {
                **request,
                "target_url": req.target_url or post_url,
                "post_id": post_id,
                "doi": doi_val,
            }
            cr_result = await workflow.execute_activity(
                "deposit_crossref",
                deposit_req,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=retry,
            )
            deposit_id = cr_result.get("deposit_id", "")

            # Phase 3: Poll / Confirm receipt status
            poll_req = {"deposit_id": deposit_id, "doi": doi_val}
            await workflow.execute_activity(
                "poll_crossref_status",
                poll_req,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=retry,
            )

            # Phase 4: Activate DOI on WordPress
            activate_req = {
                "post_id": post_id,
                "post_url": post_url,
                "deposit_id": deposit_id,
                "doi": doi_val,
            }
            await workflow.execute_activity(
                "activate_wordpress_doi",
                activate_req,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=retry,
            )

            return asdict(
                PreprintDepositResult(
                    succeeded=True,
                    post_id=post_id,
                    post_url=post_url,
                    doi=doi_val,
                    deposit_id=deposit_id,
                    doi_status="active",
                )
            )

        except Exception as exc:
            workflow.logger.error(f"PreprintDepositSagaWorkflow failed: {exc}")
            for act_name, arg in reversed(compensations):
                try:
                    await workflow.execute_activity(
                        act_name,
                        arg,
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=retry,
                    )
                    executed_compensations.append("ok")
                except Exception as rb_err:
                    executed_compensations.append(f"failed:{rb_err}")

            cause = getattr(exc, "cause", None)
            detail = getattr(cause, "message", str(cause)) if cause else str(exc)
            return asdict(
                PreprintDepositResult(
                    succeeded=False,
                    doi_status="pending",
                    error_message=str(detail),
                    compensations_executed=executed_compensations,
                )
            )
