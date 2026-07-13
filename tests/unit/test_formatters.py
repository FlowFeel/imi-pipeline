"""Tests for all payload formatters.

Ensures payload construction is correct and pure.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.draft import Draft
from phosphene.imi.formatters import (
    ObservatoryWikitextFormatter,
    SalesforceRecordFormatter,
    WordPressPostFormatter,
)


def make_draft() -> Draft:
    """Helper to construct a valid Draft."""
    return Draft(
        title="Why Care Work Matters",
        body="Care work is foundational.",
        author="Gunnar Rundgren",
        category="Economy",
        source_url="https://source.com/task/1",
    )


class TestObservatoryWikitextFormatter:
    """Tests for ObservatoryWikitextFormatter."""

    def test_formats_wikitext_correctly(self) -> None:
        """Wikitext contains title, author, category and body."""
        formatter = ObservatoryWikitextFormatter()
        draft = make_draft()
        wikitext = formatter.format_wikitext(draft)
        assert (
            "{{Article|Headline=Why Care Work Matters"
            "|Author=Gunnar Rundgren|Section=Economy}}"
        ) in wikitext
        assert "Care work is foundational." in wikitext


class TestWordPressPostFormatter:
    """Tests for WordPressPostFormatter."""

    def test_formats_wordpress_payload_correctly(self) -> None:
        """WordPress payload maps draft fields to post API schema."""
        formatter = WordPressPostFormatter()
        draft = make_draft()
        payload = formatter.format_payload(draft)
        assert payload["title"] == "Why Care Work Matters"
        assert payload["slug"] == "why-care-work-matters"
        assert payload["status"] == "publish"
        assert payload["meta"]["author_name"] == "Gunnar Rundgren"
        assert payload["meta"]["category"] == "Economy"
        assert payload["meta"]["source_url"] == "https://source.com/task/1"


class TestSalesforceRecordFormatter:
    """Tests for SalesforceRecordFormatter (V2 schema, 2026-06-22)."""

    def test_formats_salesforce_payload_without_url(self) -> None:
        """Salesforce record payload maps core draft fields using V2 field names."""
        formatter = SalesforceRecordFormatter()
        draft = make_draft()
        payload = formatter.format_payload(draft)
        # V2: Headline__c replaces Name (auto-number, never set)
        assert payload["Headline__c"] == "Why Care Work Matters"
        assert "Name" not in payload
        # V2: Observatory_Area__c replaces Category__c
        assert payload["Observatory_Area__c"] == "Economy"
        assert "Category__c" not in payload
        # V2: Observatory_wiki_Status__c replaces Status__c
        assert payload["Observatory_wiki_Status__c"] == "Published"
        assert "Status__c" not in payload
        # Required boolean fields
        assert payload["Pay__c"] is False
        assert payload["GTM_Site_Uploaded__c"] is False
        assert payload["Translated__c"] is False
        assert payload["Observatory_Classics__c"] is False
        # Required date field present
        assert "Date_Received__c" in payload
        # No URL field when none provided
        assert "Observatory_wiki_Site_Link__c" not in payload
        # Old V1 fields must be absent
        assert "Author__c" not in payload
        assert "Source__c" not in payload
        assert "Observatory_URL__c" not in payload

    def test_formats_salesforce_payload_with_url(self) -> None:
        """Salesforce record payload incorporates observatory URL with V2 field name."""
        formatter = SalesforceRecordFormatter()
        draft = make_draft()
        url = "https://observatory.wiki/Why_Care_Work_Matters"
        payload = formatter.format_payload(draft, observatory_url=url)
        # V2: Observatory_wiki_Site_Link__c replaces Observatory_URL__c
        assert payload["Observatory_wiki_Site_Link__c"] == url
        assert "Observatory_URL__c" not in payload
