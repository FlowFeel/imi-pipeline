"""WordPress test environment setup — programmatic, no shell scripts.

Replaces ci-stubs/setup-wp.sh with a proper Python module that handles:
1. Waiting for WordPress HTTP
2. Installing WordPress via WP-CLI (docker exec)
3. Enabling application passwords
4. Installing Elementor
5. Generating an application password
6. Verifying the mu-plugin gateway

Used as a pytest session-scoped fixture or as a standalone script.

@dft
- A1 (pure-io-separation): I/O wiring module — manages Docker containers,
  runs subprocesses, and verifies HTTP endpoints for test environments.
- A5 (mock-doubles): provides the real WordPress environment for Docker
  integration tests; pure unit tests use FakeWPClient instead.
- A6 (check-result): returns a WPTestEnvironment dataclass containing
  verified connection details.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class WPTestEnvironment:
    """Result of WordPress test environment setup.

    Attributes:
        url: WordPress URL.
        username: Admin username.
        app_password: Application password for REST API.
        db_token: Token for the mu-plugin DB gateway.
        container: Docker container name.
        elementor_active: Whether Elementor was installed and activated.
    """

    url: str
    username: str
    app_password: str
    db_token: str
    container: str
    elementor_active: bool


def find_container(port: int = 18090) -> str:
    """Find the WordPress Docker container by published port.

    Args:
        port: Published port to search for.

    Returns:
        Container name.

    Raises:
        RuntimeError: If no container found on the port.
    """
    result = subprocess.run(
        ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    containers = result.stdout.strip().split("\n")
    if not containers or not containers[0]:
        raise RuntimeError(f"No container found on port {port}")
    return containers[0]


def _docker_exec(container: str, *cmd: str) -> str:
    """Run a command inside the WordPress container via docker exec.

    Args:
        container: Docker container name.
        cmd: Command to run.

    Returns:
        stdout output.
    """
    result = subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _docker_exec_bash(container: str, script: str) -> str:
    """Run a bash script inside the container.

    Args:
        container: Docker container name.
        script: Bash script string.

    Returns:
        stdout output.
    """
    result = subprocess.run(
        ["docker", "exec", container, "bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _wait_for_http(url: str, timeout: int = 90) -> None:
    """Wait for WordPress to respond to HTTP.

    Args:
        url: WordPress URL.
        timeout: Maximum wait time in seconds.

    Raises:
        RuntimeError: If WordPress doesn't respond within timeout.
    """
    import urllib.error

    elapsed = 0
    while elapsed < timeout:
        try:
            code = urllib.request.urlopen(
                urllib.request.Request(url, method="HEAD"),
            ).getcode()
            if code in (200, 302):
                return
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError):
            pass
        time.sleep(5)
        elapsed += 5
    raise RuntimeError(f"WordPress not responding after {timeout}s at {url}")


def _install_wp_cli(container: str) -> None:
    """Install wp-cli inside the container.

    Args:
        container: Docker container name.
    """
    _docker_exec_bash(
        container,
        "curl -sL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar "
        "-o /usr/local/bin/wp && chmod +x /usr/local/bin/wp",
    )


def _wp_core_install(container: str, url: str) -> None:
    """Run wp core install if not already installed.

    The ``--url`` must match the URL the REST client will use (including the
    published port). A mismatch causes WordPress to reject REST API auth with
    401 Unauthorized because the ``siteurl``/``home`` options don't match the
    request URL.

    Args:
        container: Docker container name.
        url: WordPress URL (including port, as accessed from the host).
    """
    installed = _docker_exec(
        container,
        "bash",
        "-c",
        "wp core is-installed --allow-root 2>/dev/null && echo yes || echo no",
    )
    if installed == "yes":
        # Ensure siteurl/home match the access URL (in case WP was installed
        # with a different URL in a previous run)
        _docker_exec_bash(
            container,
            f"wp option update siteurl '{url}' --allow-root && "
            f"wp option update home '{url}' --allow-root && "
            "wp rewrite structure '/%postname%/' --hard --allow-root",
        )
        return
    _docker_exec_bash(
        container,
        f"wp core install "
        f"--url='{url}' "
        f"--title='IMI Test' "
        f"--admin_user=ci_admin "
        f"--admin_password=ci_admin_pass_2026 "
        f"--admin_email=ci@test.com "
        f"--skip-email --allow-root && "
        "wp rewrite structure '/%postname%/' --hard --allow-root",
    )


def _enable_app_passwords(container: str) -> None:
    """Enable application passwords over HTTP.

    Args:
        container: Docker container name.
    """
    _docker_exec_bash(
        container,
        "mkdir -p /var/www/html/wp-content/mu-plugins && "
        'printf \'<?php\\nadd_filter("wp_is_application_passwords_available", "__return_true");\\n'
        'add_filter("application_password_is_api_request", "__return_true");\\n\' '
        "> /var/www/html/wp-content/mu-plugins/ci-allow-app-passwords.php",
    )


def _install_elementor(container: str) -> bool:
    """Install and activate Elementor.

    Args:
        container: Docker container name.

    Returns:
        True if Elementor is active, False if install failed.
    """
    _docker_exec(
        container,
        "bash",
        "-c",
        "wp plugin install elementor --activate --allow-root 2>&1",
    )
    active = _docker_exec(
        container,
        "bash",
        "-c",
        "wp plugin is-active elementor --allow-root 2>/dev/null && echo yes || echo no",
    )
    return active == "yes"


def _create_app_password(container: str) -> str:
    """Generate an application password for the admin user.

    Args:
        container: Docker container name.

    Returns:
        Application password string.
    """
    output = _docker_exec(
        container,
        "bash",
        "-c",
        "wp user application-password create ci_admin ci_app --allow-root --porcelain 2>&1",
    )
    # porcelain output is just the password on the last line (remove internal spaces)
    password = output.strip().split("\n")[-1].strip().replace(" ", "")
    if not password:
        raise RuntimeError("Failed to generate application password")
    return password


def _verify_gateway(url: str, token: str) -> bool:
    """Verify the mu-plugin gateway responds.

    Args:
        url: WordPress URL.
        token: Gateway token.

    Returns:
        True if gateway responds with status ok.
    """
    try:
        req = urllib.request.Request(
            f"{url}/?imi_diag=1&action=status&token={token}",
            headers={"User-Agent": "WPTestSetup/1.0"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def setup_wordpress(
    port: int = 18090,
    db_token: str = "imi_test_token",
) -> WPTestEnvironment:
    """Set up WordPress test environment programmatically.

    Waits for HTTP, installs WP, enables app passwords, installs
    Elementor, generates app password, verifies mu-plugin gateway.

    Args:
        port: WordPress published port.
        db_token: Token for the mu-plugin DB gateway.

    Returns:
        WPTestEnvironment with connection details.

    Raises:
        RuntimeError: If any setup step fails.
    """
    url = f"http://localhost:{port}"
    container = find_container(port)

    _wait_for_http(url)
    _install_wp_cli(container)
    _wp_core_install(container, url)
    _enable_app_passwords(container)
    elementor_ok = _install_elementor(container)
    app_password = _create_app_password(container)
    gateway_ok = _verify_gateway(url, db_token)

    if not gateway_ok:
        raise RuntimeError("Mu-plugin gateway not responding")

    return WPTestEnvironment(
        url=url,
        username="ci_admin",
        app_password=app_password,
        db_token=db_token,
        container=container,
        elementor_active=elementor_ok,
    )
