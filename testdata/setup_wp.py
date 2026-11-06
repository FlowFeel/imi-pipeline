#!/usr/bin/env python3
"""Programmatic WordPress test setup for the DOI harness.

Adapts the pattern from janfrel/imi-wordpress test_setup.py:
Waits for HTTP, installs WP via wp-cli inside the container,
sets permalinks, and creates an application password saved to
testdata/.wp_app_password.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("WP_PORT", "18091"))
URL = f"http://localhost:{PORT}"
CRED_FILE = pathlib.Path(__file__).resolve().parent / ".wp_app_password"


def _wait_for_http(url: str, timeout: int = 90) -> None:
    elapsed = 0
    print(f"Waiting for WordPress at {url}...")
    while elapsed < timeout:
        try:
            req = urllib.request.Request(url, method="HEAD")
            code = urllib.request.urlopen(req, timeout=5).getcode()
            if code in (200, 302):
                print(f"WordPress responded ({code})")
                return
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError):
            pass
        time.sleep(3)
        elapsed += 3
    raise RuntimeError(f"WordPress not responding after {timeout}s at {url}")


def find_container(port: int) -> str:
    res = subprocess.run(
        ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    names = [n for n in res.stdout.strip().split("\n") if n]
    if not names:
        raise RuntimeError(f"No container found published on port {port}")
    return names[0]


def _docker_exec(container: str, *cmd: str) -> str:
    res = subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.stdout.strip()


def main() -> int:
    _wait_for_http(URL)
    container = find_container(PORT)
    print(f"Found container: {container}")

    # Core install
    print("Running wp core install...")
    _docker_exec(
        container,
        "bash",
        "-c",
        f"wp core is-installed --allow-root 2>/dev/null || "
        f"wp core install --url='{URL}' --title='IMI Registry Harness' "
        f"--admin_user=ci_admin --admin_password=ci_admin_pass_2026 "
        f"--admin_email=ci@test.com --skip-email --allow-root",
    )

    # Permalinks
    print("Setting permalinks...")
    _docker_exec(
        container,
        "bash",
        "-c",
        "wp rewrite structure '/%postname%/' --hard --allow-root",
    )

    # App password
    print("Generating application password...")
    out = _docker_exec(
        container,
        "bash",
        "-c",
        "wp user application-password create ci_admin bdd-gateway "
        "--porcelain --allow-root 2>&1",
    )
    password = out.strip().split("\n")[-1].strip().replace(" ", "")
    CRED_FILE.write_text(f"ci_admin:{password}\n")
    print(
        f"Application password generated ({len(password)} chars), "
        f"stored to {CRED_FILE.name}"
    )

    print("WordPress setup complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
