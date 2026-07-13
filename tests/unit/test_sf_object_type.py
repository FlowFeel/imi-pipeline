"""Test Salesforce outlet object type selection.

Verifies the outlet picks the right SF object based on
IMI_PIPELINE_MODE env var, without touching Salesforce.
"""

from __future__ import annotations

from phosphene.imi.fakes import FakeSFClient
from phosphene.imi.outlets.salesforce import SalesforceOutlet


class TestSFObjectTypeSelection:
    """Object type is determined by mode, injectable, and testable."""

    def test_default_is_production_object(self, monkeypatch):
        monkeypatch.delenv("IMI_PIPELINE_MODE", raising=False)
        outlet = SalesforceOutlet(client=FakeSFClient())
        assert outlet._object_type == "Content_Management__c"

    def test_explicit_production_mode(self, monkeypatch):
        monkeypatch.setenv("IMI_PIPELINE_MODE", "production")
        outlet = SalesforceOutlet(client=FakeSFClient())
        assert outlet._object_type == "Content_Management__c"

    def test_stage_mode_uses_test_object(self, monkeypatch):
        monkeypatch.setenv("IMI_PIPELINE_MODE", "stage")
        outlet = SalesforceOutlet(client=FakeSFClient())
        assert outlet._object_type == "IMI_Pipeline_Test__c"

    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("IMI_PIPELINE_MODE", "production")
        outlet = SalesforceOutlet(
            client=FakeSFClient(),
            object_type="Custom_Test__c",
        )
        assert outlet._object_type == "Custom_Test__c"

    def test_class_constants_are_correct(self):
        assert SalesforceOutlet.DEFAULT_OBJECT_TYPE == "Content_Management__c"
        assert SalesforceOutlet.TEST_OBJECT_TYPE == "IMI_Pipeline_Test__c"
