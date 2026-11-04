"""Domain-agnostic HTML presentation and parsing utilities.

Pure functions with zero domain dependencies.
All regular expressions are precompiled at module load time.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Precompiled regex patterns
_META_TAG_PATTERN = re.compile(
    r'<meta\s+name="([^"]+)"\s+content="([^"]*)"\s*/?>',
    re.IGNORECASE,
)
_JSONLD_PATTERN = re.compile(
    r'<script\s+type="application/ld\+json">(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MetaTag:
    """Immutable representation of an HTML <meta> tag.

    Attributes:
        name: The name attribute (e.g. 'citation_title').
        content: The text content of the tag.
    """

    name: str
    content: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("MetaTag 'name' must not be empty.")


def render_meta_tags(tags: Sequence[MetaTag]) -> str:
    """Render a sequence of MetaTag objects to valid HTML markup.

    Escapes attribute values using HTML entity encoding to prevent injection.

    Args:
        tags: Sequence of MetaTag instances.

    Returns:
        Newline-delimited HTML meta tags.
    """
    rendered = [
        f'<meta name="{html.escape(t.name, quote=True)}" content="{html.escape(t.content, quote=True)}" />'
        for t in tags
    ]
    return "\n".join(rendered)


def extract_meta_tags(html_text: str, prefix: str | None = None) -> dict[str, str]:
    """Extract <meta name="..." content="..."> tags from HTML text.

    Args:
        html_text: HTML document string.
        prefix: Optional prefix filter (e.g. 'citation_').

    Returns:
        Dictionary of {name: content}.
    """
    tags: dict[str, str] = {}
    for match in _META_TAG_PATTERN.finditer(html_text):
        name, content = match.group(1), match.group(2)
        if prefix is None or name.startswith(prefix):
            tags[name] = content
    return tags


def extract_jsonld(html_text: str) -> dict[str, Any]:
    """Extract and parse Schema.org JSON-LD from an HTML document.

    Args:
        html_text: HTML document containing <script type="application/ld+json">.

    Returns:
        Parsed JSON dictionary, or empty dict if not found or malformed.
    """
    match = _JSONLD_PATTERN.search(html_text)
    if not match:
        return {}
    raw_json = match.group(1).strip()
    try:
        return json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        return {}
