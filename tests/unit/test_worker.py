"""Tests for phosphene.imi.worker — toggleable Temporal worker.

RED first: these tests must fail before worker.py exists.
Covers: mode defaults, env-driven mode, fake/real client injection,
activity registration surface, and entrypoint callability.
"""

from __future__ import annotations

import importlib
import inspect
import os
from unittest.mock import patch


def test_worker_mode_defaults_to_standalone() -> None:
    """IMI_WORKER_MODE defaults to standalone when env var not set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("IMI_WORKER_MODE", None)
        from phosphene.imi import worker

        importlib.reload(worker)
        assert worker.IMI_WORKER_MODE == "standalone"


def test_worker_mode_heartbeat_from_env() -> None:
    """IMI_WORKER_MODE=heartbeat is read correctly."""
    with patch.dict(os.environ, {"IMI_WORKER_MODE": "heartbeat"}):
        from phosphene.imi import worker

        importlib.reload(worker)
        assert worker.IMI_WORKER_MODE == "heartbeat"


def test_build_activities_fake_mode() -> None:
    """IMI_CLIENT_MODE=fake returns SyndicationActivities with fake clients."""
    with patch.dict(os.environ, {"IMI_CLIENT_MODE": "fake"}):
        from phosphene.imi.worker import _build_activities

        acts = _build_activities()
        from phosphene.imi.activities import SyndicationActivities

        assert isinstance(acts, SyndicationActivities)


def test_build_activities_registers_all_six_methods() -> None:
    """SyndicationActivities has all 6 activity methods."""
    with patch.dict(os.environ, {"IMI_CLIENT_MODE": "fake"}):
        from phosphene.imi.worker import _build_activities

        acts = _build_activities()
        for method in [
            "publish_wordpress",
            "publish_mediawiki",
            "sync_salesforce",
            "delete_wordpress_post",
            "delete_mediawiki_page",
            "delete_salesforce_record",
        ]:
            assert hasattr(acts, method), f"Missing activity: {method}"


def test_worker_entrypoint_is_callable() -> None:
    """main() is importable and callable without crashing on import."""
    from phosphene.imi.worker import main, start

    assert callable(main)
    assert inspect.iscoroutinefunction(start)
