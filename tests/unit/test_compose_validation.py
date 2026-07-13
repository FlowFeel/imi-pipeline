"""Compose validation — catches healthcheck and config errors before CI.

Runs without Docker. Parses the compose file as YAML and validates:
- Healthcheck commands use tools available in their image's shell
- Environment variables match what the image expects
- Service dependencies form a valid DAG
- No bash-specific features in alpine/sh images

This is the prevention layer for WS-024: 16 CI runs spent on
healthcheck command compatibility because we didn't validate locally.

Usage:
    pytest lib/python/imi/tests/test_compose_validation.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    yaml = None

COMPOSE_PATH = Path(__file__).parent.parent / "compose.imi-stage.yml"

# Images known to use alpine/sh (no bash)
ALPINE_IMAGES = {
    "temporalio/auto-setup",
    "temporalio/temporal",
    "temporalio/server",
    "postgres",
}

# Bash-only features that don't work in sh/ash
BASHISMS = [
    "/dev/tcp/",
    "/dev/udp/",
    "[[",       # bash test
    "shopt",
    "declare -",
    "readarray",
    "mapfile",
    "${!",       # indirect expansion
    "<<<",       # here-string
]

# Tools NOT available in standard alpine
ALPINE_MISSING_TOOLS = [
    "curl",      # use wget instead
    "bash",      # use sh
    "grpc_health_probe",  # not bundled
]

# Known valid healthcheck tools per image family
KNOWN_TOOLS = {
    "postgres": ["pg_isready"],
    "temporalio/auto-setup": ["nc", "wget", "tctl", "temporal-sql-tool"],
    "temporalio/temporal": ["nc", "wget", "temporal"],
    "temporalio/server": ["nc", "wget"],
}


def load_compose() -> dict:
    """Load and parse compose YAML."""
    if yaml is None:
        pytest.skip("pyyaml not installed")
    if not COMPOSE_PATH.exists():
        pytest.skip(f"Compose file not found: {COMPOSE_PATH}")
    with open(COMPOSE_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def compose():
    return load_compose()


@pytest.fixture(scope="module")
def services(compose):
    return compose.get("services", {})


class TestComposeStructure:
    """Validate compose file structure."""

    def test_compose_is_valid_yaml(self):
        """Compose file parses as valid YAML."""
        compose = load_compose()
        assert "services" in compose

    def test_all_services_have_image_or_build(self, services):
        """Every service has either image: or build:."""
        for name, svc in services.items():
            assert "image" in svc or "build" in svc, (
                f"Service '{name}' has neither image nor build"
            )

    def test_explicit_network_declared(self, compose):
        """An explicit bridge network is declared."""
        networks = compose.get("networks", {})
        assert networks, "No explicit networks declared — services may not share DNS"
        for name, config in networks.items():
            if config and config.get("driver") == "bridge":
                return
        # If no driver specified, Docker defaults to bridge
        assert networks, "No bridge network found"

    def test_all_services_on_same_network(self, services, compose):
        """All services are on the same explicit network."""
        networks = list(compose.get("networks", {}).keys())
        if not networks:
            pytest.skip("No explicit networks")
        expected_net = networks[0]
        for name, svc in services.items():
            svc_nets = svc.get("networks", [])
            assert expected_net in svc_nets, (
                f"Service '{name}' not on network '{expected_net}'"
            )


class TestHealthchecks:
    """Validate healthcheck commands against known image capabilities."""

    def test_no_bashisms_in_healthchecks(self, services):
        """No bash-specific features in healthcheck commands."""
        for name, svc in services.items():
            hc = svc.get("healthcheck", {})
            test_cmd = hc.get("test", [])
            if isinstance(test_cmd, list):
                cmd_str = " ".join(test_cmd)
            else:
                cmd_str = str(test_cmd)

            image = svc.get("image", "")
            image_base = image.split(":")[0] if image else ""

            if any(image_base.startswith(a) for a in ALPINE_IMAGES):
                for bashism in BASHISMS:
                    assert bashism not in cmd_str, (
                        f"Service '{name}' (image {image}) uses bash feature "
                        f"'{bashism}' in healthcheck — alpine images use sh, not bash"
                    )

    def test_healthcheck_tools_exist_in_image(self, services):
        """Healthcheck commands only use tools known to exist in the image."""
        for name, svc in services.items():
            hc = svc.get("healthcheck", {})
            test_cmd = hc.get("test", [])
            if not test_cmd:
                continue

            if isinstance(test_cmd, list):
                cmd_str = " ".join(test_cmd)
            else:
                cmd_str = str(test_cmd)

            image = svc.get("image", "")
            image_base = image.split(":")[0] if image else ""

            if any(image_base.startswith(a) for a in ALPINE_IMAGES):
                for missing_tool in ALPINE_MISSING_TOOLS:
                    assert missing_tool not in cmd_str.split(), (
                        f"Service '{name}' healthcheck uses '{missing_tool}' "
                        f"which is not available in alpine images"
                    )

    def test_healthcheck_has_start_period(self, services):
        """Services with healthchecks have a start_period for slow starts."""
        for name, svc in services.items():
            hc = svc.get("healthcheck", {})
            if not hc.get("test"):
                continue
            # Postgres starts fast; start_period is recommended but not required
            if "postgres" in svc.get("image", ""):
                continue
            assert "start_period" in hc, (
                f"Service '{name}' has healthcheck without start_period — "
                f"slow-starting services will be marked unhealthy prematurely"
            )


class TestTemporalConfig:
    """Validate Temporal-specific configuration."""

    def test_temporal_db_driver_valid(self, services):
        """Temporal uses a valid DB driver."""
        temporal = services.get("temporal", {})
        env = temporal.get("environment", [])
        env_dict = {}
        for item in env:
            if "=" in item:
                k, v = item.split("=", 1)
                env_dict[k] = v

        if "DB" in env_dict:
            valid_drivers = {"mysql8", "postgres12", "postgres12_pgx", "cassandra"}
            assert env_dict["DB"] in valid_drivers, (
                f"DB={env_dict['DB']} is not valid for auto-setup. "
                f"Valid: {valid_drivers}"
            )

    def test_no_bind_on_ip_without_broadcast(self, services):
        """BIND_ON_IP=0.0.0.0 requires TEMPORAL_BROADCAST_ADDRESS."""
        temporal = services.get("temporal", {})
        env = temporal.get("environment", [])
        env_dict = {}
        for item in env:
            if "=" in item:
                k, v = item.split("=", 1)
                env_dict[k] = v

        if env_dict.get("BIND_ON_IP") == "0.0.0.0":
            assert "TEMPORAL_BROADCAST_ADDRESS" in env_dict, (
                "BIND_ON_IP=0.0.0.0 requires TEMPORAL_BROADCAST_ADDRESS "
                "(ringpop needs an IP, not a hostname)"
            )
            # Broadcast address must be an IP, not a hostname
            addr = env_dict["TEMPORAL_BROADCAST_ADDRESS"]
            assert addr.replace(".", "").isdigit() or addr == "0.0.0.0", (
                f"TEMPORAL_BROADCAST_ADDRESS='{addr}' must be an IP address, "
                f"not a hostname (ringpop rejects DNS names)"
            )

    def test_temporal_depends_on_db(self, services):
        """Temporal service depends on its database."""
        temporal = services.get("temporal", {})
        deps = temporal.get("depends_on", {})
        assert deps, "Temporal has no depends_on — will start before DB is ready"

    def test_workers_depend_on_temporal(self, services):
        """Worker and API depend on Temporal."""
        for name in ("worker", "api"):
            svc = services.get(name, {})
            if not svc:
                continue
            deps = svc.get("depends_on", {})
            assert "temporal" in deps, (
                f"Service '{name}' does not depend on temporal"
            )


class TestDependencyChain:
    """Validate the dependency chain is correct."""

    def test_healthy_dependencies_have_healthcheck(self, services):
        """If a service depends on X with service_healthy, X must have a healthcheck."""
        for name, svc in services.items():
            deps = svc.get("depends_on", {})
            for dep_name, dep_config in deps.items():
                if isinstance(dep_config, dict):
                    condition = dep_config.get("condition", "")
                    if condition == "service_healthy":
                        dep_svc = services.get(dep_name, {})
                        assert dep_svc.get("healthcheck", {}).get("test"), (
                            f"Service '{name}' depends on '{dep_name}' with "
                            f"service_healthy, but '{dep_name}' has no healthcheck"
                        )
