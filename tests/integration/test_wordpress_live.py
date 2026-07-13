"""Tier 3 — live WordPress integration (gated behind IMI_INTEGRATION=true + WP creds).

Tests in this module fire against the real IMI WordPress site. They are gated
behind two conditions:
  1. IMI_INTEGRATION=true in env — prevents accidental CI runs.
  2. WP_USERNAME and WP_APP_PASSWORD in env — credentials gate.

These tests require:
  - The IMI Scholar Registry CPT (imi_registry) deployed on the live site.
  - Valid WordPress Application Password credentials.
  - Network access from the running environment to independentmediainstitute.org.

Run with:
  IMI_INTEGRATION=true WP_USERNAME=... WP_APP_PASSWORD=... uv run pytest -m integration_live

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration_live,
    pytest.mark.skipif(
        not os.environ.get("IMI_INTEGRATION"),
        reason="IMI_INTEGRATION not set",
    ),
]


def test_wordpress_live_create_draft_post() -> None:
    """Create an imi_registry post with status=draft, verify, delete.

    status=draft is safe: draft posts are not publicly visible.

    Requires:
    - WP_USERNAME, WP_APP_PASSWORD in env
    - imi_registry CPT deployed on the target WordPress instance
    - DELETE permission for the test post in teardown

    Procedure (once credentials are confirmed):
    1. Instantiate UrllibWPClient with env credentials.
    2. Create an imi_registry post using the cave paper fixture (status=draft).
    3. Assert the result URL is non-empty and the post is retrievable.
    4. DELETE the draft post via REST API in teardown.
    """
    pytest.skip(
        "WordPress live credentials not yet confirmed in env. "
        "Set WP_USERNAME and WP_APP_PASSWORD for the target instance, "
        "then remove this skip."
    )


def test_wordpress_live_idempotency() -> None:
    """Publishing the same draft twice returns the same URL.

    Procedure (once credentials are confirmed):
    1. Publish the cave paper draft twice via WordPressOutlet.
    2. Assert both results succeeded.
    3. Assert the second result carries metadata.idempotent == 'true'.
    4. Assert both artifact URLs are identical (slug-stable identity).
    5. DELETE the post in teardown.
    """
    pytest.skip(
        "WordPress live credentials not yet confirmed in env. "
        "See test_wordpress_live_create_draft_post for setup notes."
    )


def test_wordpress_live_slug_collision() -> None:
    """Two articles with the same slug do not create duplicate posts.

    Procedure (once credentials are confirmed):
    1. Create a post with slug 'imi-integration-test-cave-art'.
    2. Attempt to create another post with the same slug.
    3. Assert the outlet returns the existing URL (idempotent).
    4. Assert only one post exists with that slug.
    5. DELETE the post in teardown.
    """
    pytest.skip(
        "WordPress live credentials not yet confirmed in env. "
        "Slug collision test requires write + read + delete access."
    )
