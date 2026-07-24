"""Integration test configuration — container lifecycle fixtures.

Session-scoped fixtures that start Docker containers, wait for health,
yield endpoints/clients, and tear down. Each fixture starts only the
services it needs.

Fixtures:
    temporal_endpoint: starts Temporal stack, yields "localhost:7233"
    mw_client: starts MW stack, inits, yields UrllibMWClient
    full_stack: starts everything, yields (temporal_endpoint, mw_client)

These fixtures use subprocess directly — no Makefiles, no wrappers.
Docker must be available on the host.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

COMPOSE = Path(__file__).parent.parent.parent / "testdata" / "docker-compose.test.yml"


def _compose_up(*services: str) -> None:
    """Start named services via docker compose, waiting for health."""
    cmd = ["docker", "compose", "-f", str(COMPOSE), "up", "-d", "--wait", *services]
    subprocess.run(cmd, check=True)


def _compose_down(*services: str) -> None:
    """Stop and remove named services and their volumes."""
    if services:
        cmd = ["docker", "compose", "-f", str(COMPOSE), "rm", "-f", "-v", *services]
    else:
        cmd = ["docker", "compose", "-f", str(COMPOSE), "down", "-v"]
    subprocess.run(cmd, check=True)


def _wait_for_http(url: str, timeout: int = 120) -> None:
    """Wait for an HTTP endpoint to return 200."""
    import requests

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"{url} did not become healthy within {timeout}s")


@pytest.fixture(scope="session")
def temporal_endpoint():
    """Start Temporal container, yield endpoint, tear down.

    Yields:
        str: The Temporal server endpoint (host:port).
    """
    _compose_up("temporal-db", "temporal")
    yield "localhost:7233"
    _compose_down("temporal-db", "temporal")


@pytest.fixture(scope="session")
def mw_client():
    """Start MW stack, run init scripts, yield a connected client.

    Returns:
        UrllibMWClient: Authenticated client connected to the test MW.
    """
    from phosphene.imi.clients.mediawiki import MWConfig, UrllibMWClient

    _compose_up("db", "elasticsearch", "web")
    _wait_for_http("http://localhost:8085/")

    # Run init scripts
    subprocess.run(
        [
            "docker",
            "exec",
            "imi-pipeline-web-1",
            "bash",
            "/init/00-create-test-admin.sh",
        ],
        check=True,
    )
    subprocess.run(
        ["docker", "exec", "imi-pipeline-web-1", "bash", "/init/01-seed-test-pages.sh"],
        check=True,
    )

    config = MWConfig(
        base_url="http://localhost:8085",
        username="TestBot",
        password="testpass",
    )
    client = UrllibMWClient(config)
    client.login()
    client.get_csrf_token()
    yield client
    _compose_down("db", "elasticsearch", "web")


@pytest.fixture(scope="session")
def full_stack(temporal_endpoint):
    """Start both Temporal and MW stacks.

    Yields:
        tuple: (temporal_endpoint, mw_client)
    """
    # temporal_endpoint fixture already started Temporal.
    # We need mw_client too — but we can't call it as a fixture
    # because it would create a second session. Instead, start MW here.
    from phosphene.imi.clients.mediawiki import MWConfig, UrllibMWClient

    _compose_up("db", "elasticsearch", "web")
    _wait_for_http("http://localhost:8085/")

    subprocess.run(
        [
            "docker",
            "exec",
            "imi-pipeline-web-1",
            "bash",
            "/init/00-create-test-admin.sh",
        ],
        check=True,
    )
    subprocess.run(
        ["docker", "exec", "imi-pipeline-web-1", "bash", "/init/01-seed-test-pages.sh"],
        check=True,
    )

    config = MWConfig(
        base_url="http://localhost:8085",
        username="TestBot",
        password="testpass",
    )
    client = UrllibMWClient(config)
    client.login()
    client.get_csrf_token()

    yield (temporal_endpoint, client)

    _compose_down("db", "elasticsearch", "web")
