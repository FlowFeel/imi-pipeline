"""Tests for WikitextParser — extract_article_params, extract_author, extract_category.

All tests are pure.  No network calls, no fixtures beyond inline data.

Tests cover:
- Basic single-line template extraction
- Multiline template (params on separate lines)
- Nested templates inside parameter values
- No {{Article}} template present → empty dict
- Multiple templates on the page — only extracts from {{Article}}
- Author with wiki markup ([[link|display]])
- Empty value (|Author=)
- Duplicate keys (last wins)
- Mixed-case key normalisation (|AUTHOR= → author)
- extract_author / extract_category shortcuts

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi.parser import WikitextParser


class TestExtractArticleParams:
    """Tests for WikitextParser.extract_article_params."""

    # ------------------------------------------------------------------
    # Basic extraction
    # ------------------------------------------------------------------

    def test_basic_single_line(self) -> None:
        """Basic single-line template returns all named parameters."""
        wikitext = "{{Article|Headline=Test Article|Author=Jane Doe|Category=Science}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert params["headline"] == "Test Article"
        assert params["author"] == "Jane Doe"
        assert params["category"] == "Science"

    def test_all_standard_fields(self) -> None:
        """Standard Observatory article template parses all fields."""
        wikitext = (
            "{{Article\n"
            "|Headline=Cave Art and Early Human Symbolism\n"
            "|Author=Jane Doe\n"
            "|Category=Human Origins\n"
            "|Date=2026-06-15\n"
            "|Img=File:cave-art.jpg\n"
            "|Img_cap=A Paleolithic cave painting\n"
            "}}"
        )
        params = WikitextParser.extract_article_params(wikitext)
        assert params["headline"] == "Cave Art and Early Human Symbolism"
        assert params["author"] == "Jane Doe"
        assert params["category"] == "Human Origins"
        assert params["date"] == "2026-06-15"
        assert params["img"] == "File:cave-art.jpg"
        assert params["img_cap"] == "A Paleolithic cave painting"

    # ------------------------------------------------------------------
    # Multiline template
    # ------------------------------------------------------------------

    def test_multiline_template(self) -> None:
        """Multiline template (params on separate lines) parses correctly."""
        wikitext = (
            "Some intro text.\n"
            "{{Article\n"
            "|Headline=Multiline Test\n"
            "|Author=Alice\n"
            "|Category=Testing\n"
            "}}\n"
            "Trailing text."
        )
        params = WikitextParser.extract_article_params(wikitext)
        assert params["headline"] == "Multiline Test"
        assert params["author"] == "Alice"
        assert params["category"] == "Testing"

    def test_multiline_values_trimmed(self) -> None:
        """Leading/trailing whitespace in values is stripped."""
        wikitext = (
            "{{Article\n"
            "| Headline = Spaced Value \n"
            "| Author   = Bob Smith  \n"
            "|Category=Biology\n"
            "}}"
        )
        params = WikitextParser.extract_article_params(wikitext)
        assert params["headline"] == "Spaced Value"
        assert params["author"] == "Bob Smith"

    # ------------------------------------------------------------------
    # Nested templates inside values
    # ------------------------------------------------------------------

    def test_nested_template_in_img_cap(self) -> None:
        """Nested template inside Img_cap is preserved and not mis-split."""
        wikitext = (
            "{{Article\n"
            "|Headline=Fossil Record\n"
            "|Author=Dr. Jones\n"
            "|Category=Paleontology\n"
            "|Img_cap={{cite|source=Museum|year=1999}}\n"
            "}}"
        )
        params = WikitextParser.extract_article_params(wikitext)
        # The img_cap value must contain the inner template intact
        assert "{{cite|source=Museum|year=1999}}" in params["img_cap"]
        # Other params must still parse correctly
        assert params["author"] == "Dr. Jones"
        assert params["category"] == "Paleontology"

    def test_nested_template_does_not_split_outer(self) -> None:
        """A pipe inside a nested template does not split outer template params."""
        wikitext = "{{Article|Headline=Test|Author={{if|a|b}}|Category=Weird}}"
        params = WikitextParser.extract_article_params(wikitext)
        # Author should be the nested template string, not split
        assert "author" in params
        assert "{{if|a|b}}" in params["author"]
        assert params["category"] == "Weird"

    # ------------------------------------------------------------------
    # No {{Article}} template
    # ------------------------------------------------------------------

    def test_no_article_template_returns_empty(self) -> None:
        """Missing {{Article}} template returns empty dict."""
        wikitext = "This page has no article template at all."
        params = WikitextParser.extract_article_params(wikitext)
        assert params == {}

    def test_empty_string_returns_empty(self) -> None:
        """Empty input returns empty dict."""
        params = WikitextParser.extract_article_params("")
        assert params == {}

    def test_other_template_only_returns_empty(self) -> None:
        """Page with only non-Article template returns empty dict."""
        wikitext = "{{InfoBox|Name=Foo|Type=Bar}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert params == {}

    # ------------------------------------------------------------------
    # Multiple templates on the page
    # ------------------------------------------------------------------

    def test_multiple_templates_extracts_article(self) -> None:
        """When multiple templates are present, only {{Article}} is parsed."""
        wikitext = (
            "{{InfoBox|Name=Foo|Category=NotThis}}\n"
            "{{Article|Headline=The Real One|Author=Correct Author|Category=Environment}}\n"
            "{{Footer|Year=2026}}"
        )
        params = WikitextParser.extract_article_params(wikitext)
        assert params["author"] == "Correct Author"
        assert params["category"] == "Environment"
        assert params["headline"] == "The Real One"

    def test_article_template_with_preceding_template(self) -> None:
        """{{Article}} after another template is located and parsed."""
        wikitext = (
            "{{Stub}}\n{{Article|Author=First Found|Category=Science|Headline=H}}"
        )
        params = WikitextParser.extract_article_params(wikitext)
        assert params["author"] == "First Found"

    # ------------------------------------------------------------------
    # Wiki markup in values
    # ------------------------------------------------------------------

    def test_author_with_wiki_link_markup(self) -> None:
        """Author specified as [[Jane Doe|J. Doe]] is returned as-is."""
        wikitext = "{{Article|Headline=H|Author=[[Jane Doe|J. Doe]]|Category=History}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert params["author"] == "[[Jane Doe|J. Doe]]"

    def test_value_with_equals_sign(self) -> None:
        """Values containing = are not truncated (split on FIRST = only)."""
        wikitext = "{{Article|Headline=A=B+C|Author=Author|Category=Math}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert params["headline"] == "A=B+C"

    # ------------------------------------------------------------------
    # Empty values
    # ------------------------------------------------------------------

    def test_empty_value_included(self) -> None:
        """Param with empty value (|Author=) is included as empty string."""
        wikitext = "{{Article|Headline=Test|Author=|Category=Science}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert "author" in params
        assert params["author"] == ""

    def test_empty_value_does_not_shadow_other_params(self) -> None:
        """Empty Author does not affect Category extraction."""
        wikitext = "{{Article|Headline=Test|Author=|Category=Ecology}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert params["category"] == "Ecology"

    # ------------------------------------------------------------------
    # Duplicate keys
    # ------------------------------------------------------------------

    def test_duplicate_keys_last_wins(self) -> None:
        """When the same key appears twice, the last value wins."""
        wikitext = (
            "{{Article"
            "|Headline=First"
            "|Author=First Author"
            "|Category=Science"
            "|Author=Second Author"
            "}}"
        )
        params = WikitextParser.extract_article_params(wikitext)
        assert params["author"] == "Second Author"

    # ------------------------------------------------------------------
    # Mixed case key normalisation
    # ------------------------------------------------------------------

    def test_uppercase_key_lowercased(self) -> None:
        """Keys are normalised to lowercase regardless of input case."""
        wikitext = "{{Article|HEADLINE=Upper|AUTHOR=Cap|CATEGORY=Cat}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert params["headline"] == "Upper"
        assert params["author"] == "Cap"
        assert params["category"] == "Cat"

    def test_mixed_case_key_lowercased(self) -> None:
        """Mixed-case key (|Author=) maps to 'author'."""
        wikitext = "{{Article|Headline=H|Author=Jane|Category=Science}}"
        params = WikitextParser.extract_article_params(wikitext)
        assert "author" in params
        assert "Author" not in params

    # ------------------------------------------------------------------
    # Return type
    # ------------------------------------------------------------------

    def test_returns_dict(self) -> None:
        """return type is dict[str, str] for a valid template."""
        wikitext = "{{Article|Headline=H|Author=A|Category=C}}"
        result = WikitextParser.extract_article_params(wikitext)
        assert isinstance(result, dict)
        for k, v in result.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


class TestExtractAuthor:
    """Tests for WikitextParser.extract_author shortcut."""

    def test_extract_author_returns_author_value(self) -> None:
        """extract_author returns the Author param value."""
        wikitext = "{{Article|Headline=H|Author=John Smith|Category=C}}"
        assert WikitextParser.extract_author(wikitext) == "John Smith"

    def test_extract_author_missing_returns_empty_string(self) -> None:
        """extract_author returns '' when no {{Article}} template found."""
        assert WikitextParser.extract_author("No template here.") == ""

    def test_extract_author_empty_value_returns_empty_string(self) -> None:
        """extract_author returns '' when |Author= has empty value."""
        wikitext = "{{Article|Headline=H|Author=|Category=C}}"
        assert WikitextParser.extract_author(wikitext) == ""

    def test_extract_author_with_wiki_markup(self) -> None:
        """extract_author preserves [[link|display]] markup in value."""
        wikitext = "{{Article|Headline=H|Author=[[Jane|J. Doe]]|Category=C}}"
        assert WikitextParser.extract_author(wikitext) == "[[Jane|J. Doe]]"


class TestExtractCategory:
    """Tests for WikitextParser.extract_category shortcut."""

    def test_extract_category_returns_category_value(self) -> None:
        """extract_category returns the Category param value."""
        wikitext = "{{Article|Headline=H|Author=A|Category=Environment}}"
        assert WikitextParser.extract_category(wikitext) == "Environment"

    def test_extract_category_missing_returns_empty_string(self) -> None:
        """extract_category returns '' when no {{Article}} template found."""
        assert WikitextParser.extract_category("No template.") == ""

    def test_extract_category_empty_value_returns_empty_string(self) -> None:
        """extract_category returns '' when |Category= has empty value."""
        wikitext = "{{Article|Headline=H|Author=A|Category=}}"
        assert WikitextParser.extract_category(wikitext) == ""
