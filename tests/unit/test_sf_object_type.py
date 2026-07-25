"""Test Salesforce outlet object type selection.

Verifies the outlet picks the right SF object based on the injected
object_type parameter. The caller (worker.py) decides production vs
stage — the outlet has no env var dependency.
"""

from __future__ import annotations

from phosphene.imi.fakes import FakeSFClient
from phosphene.imi.outlets.salesforce import SalesforceOutlet


class TestSFObjectTypeSelection:
    """Object type is injected, not read from env inside the outlet."""

    def test_default_is_production_object(self) -> None:
        outlet = SalesforceOutlet(client=FakeSFClient())
        assert outlet._object_type == "Content_Management__c"

    def test_explicit_production_object(self) -> None:
        outlet = SalesforceOutlet(
            client=FakeSFClient(),
            object_type="Content_Management__c",
        )
        assert outlet._object_type == "Content_Management__c"

    def test_stage_mode_uses_test_object(self) -> None:
        outlet = SalesforceOutlet(
            client=FakeSFClient(),
            object_type=SalesforceOutlet.TEST_OBJECT_TYPE,
        )
        assert outlet._object_type == "IMI_Pipeline_Test__c"

    def test_explicit_override_wins(self) -> None:
        outlet = SalesforceOutlet(
            client=FakeSFClient(),
            object_type="Custom_Test__c",
        )
        assert outlet._object_type == "Custom_Test__c"

    def test_class_constants_are_correct(self) -> None:
        assert SalesforceOutlet.DEFAULT_OBJECT_TYPE == "Content_Management__c"
        assert SalesforceOutlet.TEST_OBJECT_TYPE == "IMI_Pipeline_Test__c"
