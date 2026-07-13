"""Parse {{Article}} template parameters from Observatory wikitext.

Extracts structured metadata (author, category, headline, date, image)
from the {{Article|...}} template invocation. Returns a dict of the
parsed parameters, lowercased keys.

This is a deterministic parser — no LLM, no heuristics. It reads the
template syntax and extracts the named parameters.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations


class WikitextParser:
    """Parse Observatory {{Article}} template parameters.

    Handles the ``{{Article|Key=Value|...}}`` template syntax used by
    Observatory articles.  The parser is deliberately simple and
    deterministic: it walks characters to track ``{{``/``}}`` nesting
    depth, splits on ``|`` at depth zero, and splits each segment on
    the first ``=`` character.

    This is not a general wikitext parser.  It only targets the
    ``{{Article}}`` template invocation.
    """

    TEMPLATE_NAME = "Article"

    @staticmethod
    def extract_article_params(wikitext: str) -> dict[str, str]:
        """Extract parameters from ``{{Article|Key=Value|...}}`` template.

        Locates the ``{{Article`` invocation in *wikitext*, finds its
        matching ``}}``, then parses the pipe-delimited named parameters
        inside it.

        The parser tracks ``{{``/``}}`` depth to correctly handle nested
        templates inside parameter values (e.g. ``|Img_cap={{cite|...}}``).

        Keys are lowercased and stripped of surrounding whitespace.
        Values are stripped of surrounding whitespace.  When the same
        key appears more than once the last occurrence wins.

        Args:
            wikitext: Raw wikitext string that may contain an
                ``{{Article|...}}`` template invocation.

        Returns:
            Dict mapping lowercased parameter names to their string
            values.  Returns an empty dict if no ``{{Article}}``
            template is found.
        """
        # Locate ''{{Article'' (case-sensitive — observatory convention)
        marker = "{{" + WikitextParser.TEMPLATE_NAME
        start = wikitext.find(marker)
        if start == -1:
            return {}

        # Walk from the opening {{ to find the matching }}
        # We start counting at depth=1 because we are inside the outer {{
        pos = start + 2  # skip past {{
        depth = 1
        length = len(wikitext)

        while pos < length and depth > 0:
            if wikitext[pos] == "{" and pos + 1 < length and wikitext[pos + 1] == "{":
                depth += 1
                pos += 2
            elif wikitext[pos] == "}" and pos + 1 < length and wikitext[pos + 1] == "}":
                depth -= 1
                if depth == 0:
                    break
                pos += 2
            else:
                pos += 1

        if depth != 0:
            # Unbalanced template — return empty
            return {}

        # The inner content is between the first | after ''{{Article'' and pos
        # (pos now points at the first } of the closing }})
        inner = wikitext[start + 2 : pos]  # includes "Article..." through content

        # Split the inner content into segments on | at depth 0
        segments = WikitextParser._split_on_pipe(inner)

        # The first segment is the template name itself — skip it
        params: dict[str, str] = {}
        for segment in segments[1:]:
            # Split on first = only
            eq_pos = segment.find("=")
            if eq_pos == -1:
                # Positional parameter or bare name — skip (not used in Article)
                continue
            key = segment[:eq_pos].strip().lower()
            value = segment[eq_pos + 1 :].strip()
            if key:
                params[key] = value

        return params

    @staticmethod
    def extract_author(wikitext: str) -> str:
        """Extract the ``|Author=`` parameter from ``{{Article}}``.

        Shortcut that calls :meth:`extract_article_params` and returns
        the ``author`` value.

        Args:
            wikitext: Raw wikitext string.

        Returns:
            Author string, or empty string if not found.
        """
        return WikitextParser.extract_article_params(wikitext).get("author", "")

    @staticmethod
    def extract_category(wikitext: str) -> str:
        """Extract the ``|Category=`` parameter from ``{{Article}}``.

        Shortcut that calls :meth:`extract_article_params` and returns
        the ``category`` value.

        Args:
            wikitext: Raw wikitext string.

        Returns:
            Category string, or empty string if not found.
        """
        return WikitextParser.extract_article_params(wikitext).get("category", "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_on_pipe(text: str) -> list[str]:
        """Split *text* on ``|`` characters at nesting depth 0.

        Nested ``{{...}}`` are treated as a single unit — ``|`` inside
        them does not split the outer template arguments.

        Args:
            text: Inner template content (excluding outer ``{{``/``}}``).

        Returns:
            List of string segments split on top-level ``|``.
        """
        segments: list[str] = []
        brace_depth = 0    # tracks {{ / }}
        bracket_depth = 0  # tracks [[ / ]]
        current: list[str] = []
        i = 0
        length = len(text)

        while i < length:
            ch = text[i]
            if ch == "{" and i + 1 < length and text[i + 1] == "{":
                brace_depth += 1
                current.append("{{")
                i += 2
            elif ch == "}" and i + 1 < length and text[i + 1] == "}":
                brace_depth -= 1
                current.append("}}")
                i += 2
            elif ch == "[" and i + 1 < length and text[i + 1] == "[":
                bracket_depth += 1
                current.append("[[")
                i += 2
            elif ch == "]" and i + 1 < length and text[i + 1] == "]":
                bracket_depth -= 1
                current.append("]]")
                i += 2
            elif ch == "|" and brace_depth == 0 and bracket_depth == 0:
                segments.append("".join(current))
                current = []
                i += 1
            else:
                current.append(ch)
                i += 1

        # Append the final segment (may be empty)
        segments.append("".join(current))
        return segments
