"""IMI Temporal worker — toggleable standalone/heartbeat mode.

IMI_WORKER_MODE controls execution:
  "standalone" (default) — asyncio.run(start()) — run as a process
  "heartbeat"            — expose start() coroutine for heartbeat dispatcher

IMI_CLIENT_MODE controls client injection:
  "real" (default) — inject UrllibWPClient, UrllibMWClient, UrllibSFClient from env
  "fake"           — inject FakeWPClient, FakeMWClient, FakeSFClient (testing)

IMI_CLIENT_MODE exists because proving pipeline logic and proving
connectivity are distinct concerns requiring different proof strategies.
With ``fake``, all calls are recorded but no HTTP leaves the process —
this is safe for proving saga sequencing, compensation ordering, and
result aggregation without touching production systems. With ``real``,
live credentials produce production consequences. The toggle is an
environment variable (not a constructor flag) because the decision is
operational, not architectural: the same code runs in both modes, and
the mode is determined by the deployment context, not by the caller.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import asyncio
import os

from phosphene.temporal.client import TEMPORAL_TASK_QUEUE, get_client
from temporalio.worker import Worker

from phosphene.imi.activities import SyndicationActivities
from phosphene.imi.workflow import SyndicationSagaWorkflow

IMI_WORKER_MODE: str = os.environ.get("IMI_WORKER_MODE", "standalone")
IMI_TASK_QUEUE: str = os.environ.get("IMI_TASK_QUEUE", TEMPORAL_TASK_QUEUE)


class _PardotClientAdapter:
    """Wraps the pardot.notification module function as a protocol object.

    Allows the worker to inject a real Pardot client that satisfies
    PardotClientProtocol without coupling the activity layer to the
    cross-repo import.
    """

    def send_pipeline_notification(
        self,
        result: dict[str, str],
        recipients: list[dict] | None = None,
    ) -> list:
        """Delegate to the real send_pipeline_notification function.

        Reads consumer key/secret from env at call time so the adapter
        can be constructed without credentials being available yet.

        Args:
            result: Pipeline result dict.
            recipients: Optional recipient override.

        Returns:
            List of SendResult from the real Pardot client.
        """
        import os as _os

        from pardot.notification import send_pipeline_notification as _send

        consumer_key = _os.environ.get("PARDOT_CONSUMER_KEY", "")
        consumer_secret = _os.environ.get("PARDOT_CONSUMER_SECRET", "")
        return _send(
            result=result,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
        )


def _build_activities() -> SyndicationActivities:
    """Build SyndicationActivities with injected clients.

    IMI_CLIENT_MODE=fake uses fakes (testing/dry-run): all calls are
    recorded, no HTTP, safe for proving pipeline logic without
    production consequences. IMI_CLIENT_MODE=real (default) uses real
    clients from env config: live credentials, production writes.

    Returns:
        A fully wired :class:`SyndicationActivities` instance.
    """
    mode = os.environ.get("IMI_CLIENT_MODE", "real")
    if mode == "fake":
        from phosphene.imi.fakes import (
            FakeMWClient,
            FakePardotClient,
            FakeSFClient,
            FakeWPClient,
        )

        return SyndicationActivities(
            FakeWPClient(), FakeMWClient(), FakeSFClient(), FakePardotClient()
        )

    # Real clients — read config from env
    from phosphene.imi.clients.mediawiki import MWConfig, UrllibMWClient

    # Cross-repo imports — these packages are installed as editable deps
    try:
        from phosphene.imi_wordpress.client import UrllibWPClient
        from phosphene.imi_wordpress.config import WPConfig

        wp_client = UrllibWPClient(config=WPConfig.from_env())
    except ImportError:
        from phosphene.imi.fakes import FakeWPClient

        wp_client = FakeWPClient()  # type: ignore[assignment]

    try:
        from phosphene.imi_salesforce.client import UrllibSFClient
        from phosphene.imi_salesforce.config import SFConfig

        sf_client = UrllibSFClient(config=SFConfig.from_env())
    except ImportError:
        from phosphene.imi.fakes import FakeSFClient

        sf_client = FakeSFClient()  # type: ignore[assignment]

    # Pardot — cross-repo import with graceful fallback
    try:
        pardot_client: object = _PardotClientAdapter()
        # Validate the import is available (adapter delegates lazily, so probe now)
        import pardot.notification
    except ImportError:
        from phosphene.imi.fakes import FakePardotClient

        pardot_client = FakePardotClient()  # type: ignore[assignment]

    mw_client = UrllibMWClient(config=MWConfig.from_env())
    return SyndicationActivities(
        wp_client=wp_client,
        mw_client=mw_client,
        sf_client=sf_client,
        pardot_client=pardot_client,  # type: ignore[arg-type]
    )


async def start() -> None:
    """Start the IMI Temporal worker. Runs indefinitely."""
    activities = _build_activities()
    client = await get_client()
    worker = Worker(
        client,
        task_queue=IMI_TASK_QUEUE,
        workflows=[SyndicationSagaWorkflow],
        activities=[
            activities.publish_wordpress,
            activities.publish_mediawiki,
            activities.sync_salesforce,
            activities.send_pardot_email,
            activities.delete_wordpress_post,
            activities.delete_mediawiki_page,
            activities.delete_salesforce_record,
            activities.noop_compensation,
        ],
    )
    async with worker:
        await asyncio.Event().wait()  # run forever


def main() -> None:
    """Entry point for standalone mode."""
    asyncio.run(start())


if __name__ == "__main__":
    main()
