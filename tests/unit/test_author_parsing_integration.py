"""Integration tests — author/category extraction from {{Article}} wikitext.

Verifies that SyndicationActivities._to_draft_and_publisher extracts
author and category from the wikitext body when those fields are not
explicitly set on the SyndicationRequest.

Uses real SyndicationActivities with injected fake clients (DI).
Zero @patch / monkeypatch — behaviour is proven through interfaces only.

Scenarios:
1. Author and category in wikitext, not in request → extracted into Draft.
2. Author in request, not in wikitext → request value wins, not overwritten.
3. Category in request, not in wikitext → request value wins.
4. Author in both request and wikitext → request value wins.
5. Category in wikitext, not in request → extracted into Draft.
6. Neither author nor category in request or wikitext → defaults apply.
7. non-wikitext body_format → parser is NOT invoked, defaults apply.
8. Author extracted from multiline {{Article}} template.
9. Author with nested template in wikitext correctly extracted.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from phosphene.imi.activities import SyndicationActivities
from phosphene.imi.fakes import FakeMWClient, FakeSFClient, FakeWPClient
from phosphene.imi.request import SyndicationRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_activities() -> SyndicationActivities:
    """Return a SyndicationActivities wired with fake clients."""
    return SyndicationActivities(
        wp_client=FakeWPClient(),
        mw_client=FakeMWClient(),
        sf_client=FakeSFClient(),
    )


ARTICLE_WIKITEXT = """\
{{Article
|Headline=Cave Art and Early Human Symbolism
|Author=Jane Doe
|Category=Human Origins
|Date=2026-06-15
|Img=File:cave-art.jpg
|Img_cap=A Paleolithic cave painting
}}

The earliest known cave art dates back approximately 45,000 years.
"""

ARTICLE_WIKITEXT_NO_AUTHOR = """\
{{Article
|Headline=Climate and Agriculture
|Category=Environment
|Date=2026-06-20
}}

Some content about climate.
"""

ARTICLE_WIKITEXT_NO_CATEGORY = """\
{{Article
|Headline=Economic Shifts
|Author=Bob Wilson
|Date=2026-07-01
}}

Content about economics.
"""

ARTICLE_WIKITEXT_NO_AUTHOR_NO_CATEGORY = """\
{{Article
|Headline=Untitled Study
|Date=2026-07-01
}}

Body text here.
"""

ARTICLE_WIKITEXT_NESTED = """\
{{Article
|Headline=Fossil Study
|Author=Dr. Anna Petrov
|Category=Paleontology
|Img_cap={{cite|source=Natural History Museum|year=2020}}
}}

Fossil content.
"""

MULTILINE_ARTICLE = """\
{{Article
|Headline=Multiline Article
|Author=Multiline Author
|Category=Multiline Category
}}
"""


def _build_request(wikitext: str, **overrides) -> dict:
    """Build a SyndicationRequest dict from wikitext plus optional overrides."""
    base = SyndicationRequest(
        title="Test Article",
        body=wikitext,
        body_format="wikitext",
    )
    d = asdict(base)
    d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWikitextAuthorCategoryExtraction:
    """Integration tests ensuring _to_draft_and_publisher uses WikitextParser."""

    def test_author_and_category_extracted_when_missing_from_request(self) -> None:
        """When request has no author/category, they are parsed from wikitext."""
        acts = make_activities()
        request = _build_request(ARTICLE_WIKITEXT)
        # Ensure request has no author/category overrides
        assert request.get("author", "") == "" or request["author"] == ""
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.author == "Jane Doe"
        assert draft.category == "Human Origins"

    def test_request_author_wins_over_wikitext(self) -> None:
        """Explicit author in request is not overwritten by wikitext author."""
        request = _build_request(ARTICLE_WIKITEXT, author="Explicit Author")
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.author == "Explicit Author"

    def test_request_category_wins_over_wikitext(self) -> None:
        """Explicit category in request is not overwritten by wikitext category."""
        request = _build_request(ARTICLE_WIKITEXT, category="Explicit Category")
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.category == "Explicit Category"

    def test_both_author_and_category_in_request_preserve_both(self) -> None:
        """When both author and category are in request, neither is overwritten."""
        request = _build_request(
            ARTICLE_WIKITEXT,
            author="Override Author",
            category="Override Category",
        )
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.author == "Override Author"
        assert draft.category == "Override Category"

    def test_category_extracted_when_only_author_missing(self) -> None:
        """Category is extracted from wikitext when author not in wikitext either."""
        request = _build_request(ARTICLE_WIKITEXT_NO_AUTHOR)
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        # No author in wikitext or request → falls back to default
        assert draft.author == "Observatory"
        assert draft.category == "Environment"

    def test_author_extracted_when_only_category_missing(self) -> None:
        """Author is extracted from wikitext when category not in wikitext."""
        request = _build_request(ARTICLE_WIKITEXT_NO_CATEGORY)
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.author == "Bob Wilson"
        # No category in wikitext or request → falls back to default
        assert draft.category == "General"

    def test_defaults_when_neither_in_wikitext_nor_request(self) -> None:
        """Default Observatory/General apply when neither field is in wikitext or request."""
        request = _build_request(ARTICLE_WIKITEXT_NO_AUTHOR_NO_CATEGORY)
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.author == "Observatory"
        assert draft.category == "General"

    def test_non_wikitext_format_does_not_parse(self) -> None:
        """Parser is NOT invoked for body_format != 'wikitext'."""
        # Use a body that contains {{Article}} markup,
        # but body_format is 'markdown' — parser must not run.
        request = _build_request(ARTICLE_WIKITEXT, body_format="markdown")
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        # With no wikitext parsing and no explicit overrides, defaults apply
        assert draft.author == "Observatory"
        assert draft.category == "General"

    def test_multiline_template_extracted(self) -> None:
        """Author and category are correctly extracted from a multiline template."""
        request = _build_request(MULTILINE_ARTICLE)
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.author == "Multiline Author"
        assert draft.category == "Multiline Category"

    def test_nested_template_in_wikitext_does_not_corrupt_extraction(self) -> None:
        """Nested template in an unrelated param does not corrupt author/category."""
        request = _build_request(ARTICLE_WIKITEXT_NESTED)
        draft, _ = SyndicationActivities._to_draft_and_publisher(request)
        assert draft.author == "Dr. Anna Petrov"
        assert draft.category == "Paleontology"

    def test_publisher_id_extracted_correctly(self) -> None:
        """publisher_id is correctly derived from the request dict."""
        request = _build_request(ARTICLE_WIKITEXT, publisher_id="jan")
        _, publisher_id = SyndicationActivities._to_draft_and_publisher(request)
        assert publisher_id == "jan"

    def test_draft_is_valid_and_complete(self) -> None:
        """The returned Draft satisfies invariant static constraints."""
        from phosphene.imi.draft import Draft

        request = _build_request(ARTICLE_WIKITEXT)
        draft, publisher_id = SyndicationActivities._to_draft_and_publisher(request)
        assert isinstance(draft, Draft)
        assert draft.title == "Test Article"
        assert draft.body == ARTICLE_WIKITEXT
        assert draft.author == "Jane Doe"
        assert draft.category == "Human Origins"
        assert publisher_id == "flow"
