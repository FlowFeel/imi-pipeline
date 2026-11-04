"""Pipeline runner — fan-out draft publication to multiple outlets.

.. note::

   This is the legacy fan-out runner, superseded by ``SyndicationSagaWorkflow``
   in ``phosphene.imi.workflow``. The fan-out produces inconsistent state on
   partial failure (outlet 3 succeeds after outlet 2 fails → mixed publish state
   with no rollback). It remains here for reference and backward compatibility —
   use the Temporal saga for new work.

Wires ``Draft → [Outlet, ...] → PipelineResult``.  Each outlet is called
in order; failures are captured (never raised) so that subsequent outlets
always get their turn.  Dry-run mode skips all outlet calls entirely.

@dft
- A1 (pure-io-separation): I/O wiring module — wires outlets (which do I/O).
  The result dataclasses (``OutletCallResult``, ``PipelineResult``) are pure.
- A2 (determinism): no datetime/random/uuid. Deterministic outlet ordering.
- A6 (check-result): ``run()`` returns a :class:`PipelineResult` (the proof).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class OutletProtocol(Protocol):
    """Structural protocol satisfied by any object with name + publish."""

    name: str

    def publish(self, draft: Any) -> dict[str, Any]:
        """Publish *draft* and return a result dict.

        Args:
            draft: The draft object to publish.

        Returns:
            A dict that MAY contain an ``"artifact"`` key with a URL or id.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutletCallResult:
    """Immutable record of a single outlet invocation.

    Attributes:
        outlet_name: Name of the outlet that was called.
        succeeded: Whether the call completed without error.
        artifact: Optional artifact string (URL, id) on success.
        error: Optional error description on failure.
    """

    outlet_name: str
    succeeded: bool
    artifact: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    """Immutable aggregate result of a full pipeline run.

    Attributes:
        outlet_results: List of per-outlet call results.
        dry_run: True when the pipeline was invoked in dry-run mode.
    """

    outlet_results: list[OutletCallResult] = field(default_factory=list)
    dry_run: bool = False

    @property
    def all_succeeded(self) -> bool:
        """Return True if every outlet call succeeded (or the list is empty).

        Returns:
            True when no outlet failed; vacuously true for empty results.
        """
        return all(r.succeeded for r in self.outlet_results)

    @property
    def wordpress_url(self) -> str | None:
        """Extract the artifact from the wordpress outlet, if it succeeded.

        Looks for an :class:`OutletCallResult` whose ``outlet_name`` is
        ``"wordpress"`` and ``succeeded`` is True, then returns its artifact.

        Returns:
            The wordpress artifact string, or None if not found / failed.
        """
        for r in self.outlet_results:
            if r.outlet_name == "wordpress" and r.succeeded:
                return r.artifact
        return None


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


class IMIPipeline:
    """Fan-out pipeline that publishes a draft to multiple outlets.

    Args:
        outlets: Ordered list of outlets to invoke.
        dry_run: When True, skip all outlet calls and return immediately.
    """

    def __init__(
        self,
        outlets: list[Any] | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialise the pipeline.

        Args:
            outlets: Ordered list of outlet objects satisfying
                :class:`OutletProtocol`.
            dry_run: If True, :meth:`run` will short-circuit without
                calling any outlet.
        """
        self._outlets: list[Any] = outlets or []
        self._dry_run = dry_run

    def run(self, draft: Any) -> PipelineResult:
        """Execute the pipeline against *draft*.

        Calls each outlet's ``publish`` method in order.  If an outlet
        raises, the exception is caught and recorded as a failed
        :class:`OutletCallResult`; the next outlet is still called.

        In dry-run mode, no outlets are called and the result is returned
        with ``dry_run=True`` and an empty ``outlet_results`` list.

        Args:
            draft: The draft object to publish.

        Returns:
            A :class:`PipelineResult` aggregating all outlet outcomes.
        """
        if self._dry_run:
            return PipelineResult(outlet_results=[], dry_run=True)

        results: list[OutletCallResult] = []
        for outlet in self._outlets:
            try:
                resp = outlet.publish(draft)
                artifact = resp.get("artifact") if isinstance(resp, dict) else None
                results.append(
                    OutletCallResult(
                        outlet_name=outlet.name,
                        succeeded=True,
                        artifact=artifact,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    OutletCallResult(
                        outlet_name=outlet.name,
                        succeeded=False,
                        error=str(exc),
                    )
                )

        return PipelineResult(outlet_results=results)


class WordPressOutlet:
    """Outlet that syndicates a PreprintEntry or draft to WordPress via a WPClient.

    Satisfies :class:`OutletProtocol`. Adapts domain entities via
    :class:`~phosphene.imi_wordpress.adapters.PreprintPayloadAdapter`.
    """

    name: str = "wordpress"

    def __init__(self, client: Any) -> None:
        self.client = client
        self._published_slugs: set[str] = set()

    def publish(self, draft: Any) -> dict[str, Any]:
        """Publish a preprint or draft to WordPress idempotently."""
        from phosphene.imi_wordpress.adapters import PreprintPayloadAdapter
        from phosphene.imi_wordpress.domain import PreprintEntry

        if isinstance(draft, PreprintEntry):
            payload = PreprintPayloadAdapter.to_wordpress(draft)
        elif hasattr(draft, "to_wp_payload"):
            payload = draft.to_wp_payload()
        else:
            payload = dict(draft)

        slug = payload.get("slug")
        if slug and (slug in self._published_slugs or self.client.post_exists(slug)):
            return {
                "ok": True,
                "status": "skipped",
                "slug": slug,
                "artifact": self.client.post_url(0),
            }

        res = self.client.create_post(payload)
        if slug:
            self._published_slugs.add(slug)

        post_id = res.get("id", 0)
        artifact = res.get("link") or self.client.post_url(post_id)
        return {"ok": True, "artifact": artifact, "response": res}
