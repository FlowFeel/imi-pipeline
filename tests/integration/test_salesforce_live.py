"""Tier 3 — live Salesforce integration (gated behind IMI_INTEGRATION=true + SF creds).

Tests in this module fire against the real Salesforce org. They are gated
behind two conditions:
  1. IMI_INTEGRATION=true in env — prevents accidental CI runs.
  2. SF_CONSUMER_KEY and SF_CONSUMER_SECRET in env — credentials gate.

These tests require:
  - A Salesforce org accessible from the running environment.
  - An ``IMI_Pipeline_Test__c`` custom object (or equivalent) in that org.
  - Admin action to provision the test object if it does not exist.

Run with:
  IMI_INTEGRATION=true SF_CONSUMER_KEY=... SF_CONSUMER_SECRET=... uv run pytest -m integration_live

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


def test_salesforce_live_create_and_cleanup() -> None:
    """Create an IMI_Pipeline_Test__c record, verify, delete.

    Requires:
    - SF_CONSUMER_KEY, SF_CONSUMER_SECRET in env
    - IMI_Pipeline_Test__c custom object in Salesforce org

    Procedure (once admin has created the test object):
    1. Instantiate RealSFClient with env credentials.
    2. Create a Content_Management__c record with the cave paper fixture.
    3. Assert the record ID is non-empty and the record is queryable.
    4. Delete the record in teardown (cleanup is mandatory).
    """
    pytest.skip(
        "Salesforce test object not yet created — needs admin action. "
        "Provision IMI_Pipeline_Test__c in the org, then remove this skip."
    )


def test_salesforce_live_idempotency() -> None:
    """Publishing the same draft twice creates exactly one record.

    Procedure (once admin has created the test object):
    1. Publish the cave paper draft twice via SalesforceOutlet.
    2. Assert both results succeeded.
    3. Assert the second result carries metadata.idempotent == 'true'.
    4. Query by Headline__c — assert exactly one record exists.
    5. Delete the record in teardown.
    """
    pytest.skip(
        "Salesforce test object not yet created — needs admin action. "
        "See test_salesforce_live_create_and_cleanup for provisioning notes."
    )


def test_salesforce_live_v2_field_names() -> None:
    """Live record carries V2 field names (not V1).

    Verifies that the live Salesforce org rejects payloads with V1 field names
    (Name, Author__c, Category__c, Status__c) and accepts V2 field names.

    Procedure (once admin has created the test object):
    1. POST a payload with V1 field names — assert rejection (4xx response).
    2. POST a payload with V2 field names via SalesforceOutlet — assert success.
    3. Delete the created record in teardown.
    """
    pytest.skip(
        "Salesforce test object not yet created — needs admin action. "
        "V2 field names: Headline__c, Observatory_Area__c, Observatory_wiki_Status__c."
    )
