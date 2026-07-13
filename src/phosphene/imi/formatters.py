"""Formatters — pure transformations mapping drafts to target outlet payloads.

This module contains only pure functions and classes. No IO.
Allows testing outlet payload generation in isolation without mocks.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from typing import Any

from phosphene.imi.draft import Draft


class ObservatoryWikitextFormatter:
    """Formats a Draft into wikitext for observatory.wiki."""

    def format_wikitext(self, draft: Draft) -> str:
        """Render a Draft to wikitext using the standard Article template."""
        return (
            f"{{{{Article|Headline={draft.title}"
            f"|Author={draft.author}"
            f"|Section={draft.category}}}}}\n\n"
            f"{draft.body}"
        )


class WordPressPostFormatter:
    """Maps a Draft to WordPress post API payload."""

    def format_payload(self, draft: Draft) -> dict[str, Any]:
        """Convert a Draft to a dictionary matching WordPress post creation API."""
        return {
            "title": draft.title,
            "slug": draft.slug,
            "status": "publish",
            "meta": {
                "author_name": draft.author,
                "category": draft.category,
                "source_url": draft.source_url or "",
            },
        }


class SalesforceRecordFormatter:
    """Maps a Draft to Salesforce Content_Management__c record payload.

    Field mapping reflects the live schema discovered 2026-06-22:
    Name is auto-number (omitted), title goes to Headline__c,
    category to Observatory_Area__c, status to Observatory_wiki_Status__c,
    and the wiki link to Observatory_wiki_Site_Link__c.

    Note: the SalesforceOutlet builds its own payload inline and does
    not use this formatter.  This class exists so that payload
    construction can be tested as a pure function, independently of
    the outlet's IO/idempotency logic.
    """

    def format_payload(
        self,
        draft: Draft,
        observatory_url: str | None = None,
    ) -> dict[str, Any]:
        """Convert a Draft to a dictionary matching Salesforce Content_Management__c.

        Field names match the V2 schema discovered 2026-06-22 against
        live indmedia.my.salesforce.com.  Name is auto-number and
        must not be set.

        Args:
            draft: The draft to convert.
            observatory_url: Optional observatory wiki URL for the article.

        Returns:
            A dict ready to POST to the Salesforce REST API.
        """
        from datetime import date

        data: dict[str, Any] = {
            # Title → Headline__c (Name is auto-number, never set)
            "Headline__c": draft.title,
            # Required date field
            "Date_Received__c": date.today().isoformat(),
            # Category → Observatory_Area__c (was Category__c)
            "Observatory_Area__c": draft.category,
            # Status → Observatory_wiki_Status__c (was Status__c)
            "Observatory_wiki_Status__c": "Published",
            # Required boolean fields — all default False
            "Pay__c": False,
            "GTM_Site_Uploaded__c": False,
            "Translated__c": False,
            "Observatory_Classics__c": False,
        }
        if observatory_url:
            # URL → Observatory_wiki_Site_Link__c (was Observatory_URL__c)
            data["Observatory_wiki_Site_Link__c"] = observatory_url
        return data
