"""Phosphene Utilities — domain-agnostic text rendering and parsing helpers.

Enforces absolute separation of data manipulation from text rendering.
Zero domain dependencies.
"""

from __future__ import annotations

from phosphene.utils.html import (
    MetaTag,
    extract_jsonld,
    extract_meta_tags,
    render_meta_tags,
)
from phosphene.utils.text import (
    extract_url_slug,
    extract_url_title,
    humanize_slug,
    join_delimited,
    parse_command_line,
    slugify,
)
from phosphene.utils.wikitext import render_wikitext_template

__all__ = [
    "MetaTag",
    "extract_jsonld",
    "extract_meta_tags",
    "extract_url_slug",
    "extract_url_title",
    "humanize_slug",
    "join_delimited",
    "parse_command_line",
    "render_meta_tags",
    "render_wikitext_template",
    "slugify",
]
