"""Tier 3 — live Observatory integration (gated behind IMI_INTEGRATION=true + MW creds).

Tests in this module fire against a real MediaWiki instance (container or
production). They are gated behind two conditions:
  1. IMI_INTEGRATION=true in env — prevents accidental CI runs.
  2. MW_BOT_USERNAME and MW_BOT_PASSWORD in env — credentials gate.

Note on Observatory/MediaWiki Tier 3 scope:
  The container stack (Tier 2 container) already provides strong proof for
  the MW outlet because we own both the Python client and the PHP server.
  Tier 3 live tests here are therefore limited to scenarios that require a
  long-running MW instance (e.g., SMW property store, real namespace queries).

  Container-level Playwright tests (seo-kelly-spec.spec.ts in
  observatory-magazine-v2) cover the full Kelly contract at the rendered
  HTML level and are the authoritative proof for that tier.

Run with:
  IMI_INTEGRATION=true MW_BOT_USERNAME=... MW_BOT_PASSWORD=... uv run pytest -m integration_live

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


def test_observatory_live_create_draft_page() -> None:
    """Create a Draft: page on the target MW instance, verify, delete.

    Draft: pages are not rendered in the public namespace — safe to create.

    Requires:
    - MW_BOT_USERNAME, MW_BOT_PASSWORD in env
    - Target MW instance with Draft: namespace enabled
    - Bot account with edit + delete permissions in Draft: namespace

    Procedure (once credentials are confirmed):
    1. Instantiate RealMWClient with env credentials, namespace_prefix='Draft'.
    2. Create a Draft: page using the cave paper fixture.
    3. Assert page_exists() returns True after creation.
    4. Assert the result artifact URL contains 'Draft:'.
    5. Delete the page via RealMWClient.delete_page() in teardown.
    """
    pytest.skip(
        "MediaWiki live credentials not yet confirmed in env. "
        "Set MW_BOT_USERNAME and MW_BOT_PASSWORD for the target instance, "
        "then remove this skip."
    )


def test_observatory_live_namespace_enforcement() -> None:
    """A draft title without 'Draft:' prefix is still created in Draft: namespace.

    Verifies RealMWClient._safe_title() enforces the namespace prefix even
    when the caller omits it. Prevents main-namespace writes.

    Procedure (once credentials are confirmed):
    1. Pass a bare title (no 'Draft:' prefix) to ObservatoryOutlet.publish().
    2. Query MW API for the created page.
    3. Assert the page title returned begins with 'Draft:'.
    4. Assert no main-namespace page was created with the bare title.
    5. Delete the Draft: page in teardown.
    """
    pytest.skip(
        "MediaWiki live credentials not yet confirmed in env. "
        "Namespace enforcement test requires write + query + delete access."
    )


def test_observatory_live_smw_modification_date() -> None:
    """Published Draft: page has Modification date in the SMW property store.

    Only meaningful against a full MediaWiki container with Semantic
    MediaWiki installed. The container stack already covers this at Tier 2.
    This stub exists for future live SMW store validation.

    Procedure (once SMW container environment is confirmed):
    1. Create a Draft: page with {{Article template.
    2. Query SMW Ask API for Modification date printout.
    3. Assert the Modification date is non-empty and parseable.
    4. Delete the page in teardown.
    """
    pytest.skip(
        "SMW live store test requires full MW container with SMW installed. "
        "The Tier 2 container stack (observatory-magazine-v2) covers this. "
        "Remove this skip only when testing a persistent live MW instance."
    )
