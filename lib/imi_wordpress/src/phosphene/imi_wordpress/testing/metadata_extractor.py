"""Metadata extractor for rendered WordPress registry pages.

Extracts citation meta tags, Open Graph, Dublin Core, JSON-LD,
Yoast SEO presence, and canonical URLs from HTML content.

@dft
- A1 (pure-io-separation): pure logic — imports only standard libraries and phosphene.utils.
- A2 (determinism): no datetime/random/uuid. Same HTML in → same metadata out.
- A6 (check-result): from_html() returns a PageMetadata (the proof).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from phosphene.utils.html import extract_meta_tags

# Precompiled regex patterns
_OG_PATTERN = re.compile(r'<meta\s+property="(og:[^"]*)"\s+content="([^"]*)"', re.IGNORECASE)
_JSONLD_BLOCKS = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_CANONICAL_1 = re.compile(r'<link[^>]*rel="canonical"[^>]*href="([^"]*)"', re.IGNORECASE)
_CANONICAL_2 = re.compile(r'<link[^>]*href="([^"]*)"[^>]*rel="canonical"', re.IGNORECASE)


@dataclass(frozen=True)
class PageMetadata:
    """Structured metadata extracted from a rendered WordPress page."""

    citation: dict[str, str] = field(default_factory=dict)
    open_graph: dict[str, str] = field(default_factory=dict)
    dublin_core: dict[str, str] = field(default_factory=dict)
    jsonld: list[dict[str, Any]] = field(default_factory=list)
    yoast_present: bool = False
    canonical_url: str | None = None


class MetadataExtractor:
    """Extract structured metadata from WordPress-rendered HTML."""

    @staticmethod
    def from_html(html: str) -> PageMetadata:
        """Parse HTML and return structured PageMetadata."""
        return PageMetadata(
            citation=MetadataExtractor._extract_citation(html),
            open_graph=MetadataExtractor._extract_open_graph(html),
            dublin_core=MetadataExtractor._extract_dublin_core(html),
            jsonld=MetadataExtractor._extract_jsonld(html),
            yoast_present=MetadataExtractor._detect_yoast(html),
            canonical_url=MetadataExtractor._extract_canonical(html),
        )

    @staticmethod
    def _extract_citation(html: str) -> dict[str, str]:
        """Extract Highwire Press citation_* meta tags."""
        return extract_meta_tags(html, prefix="citation_")

    @staticmethod
    def _extract_open_graph(html: str) -> dict[str, str]:
        """Extract Open Graph og:* meta tags."""
        return dict(_OG_PATTERN.findall(html))

    @staticmethod
    def _extract_dublin_core(html: str) -> dict[str, str]:
        """Extract Dublin Core DC.* meta tags."""
        return extract_meta_tags(html, prefix="DC.")

    @staticmethod
    def _extract_jsonld(html: str) -> list[dict[str, Any]]:
        """Extract and parse JSON-LD script blocks."""
        blocks = _JSONLD_BLOCKS.findall(html)
        results: list[dict[str, Any]] = []
        for block in blocks:
            try:
                parsed = json.loads(block.strip())
                if isinstance(parsed, dict):
                    results.append(parsed)
            except (json.JSONDecodeError, ValueError):
                continue
        return results

    @staticmethod
    def _detect_yoast(html: str) -> bool:
        """Detect Yoast SEO schema graph marker."""
        return "yoast-schema-graph" in html

    @staticmethod
    def _extract_canonical(html: str) -> str | None:
        """Extract canonical URL from link tag (handles attribute order)."""
        match = _CANONICAL_1.search(html)
        if match:
            return match.group(1)
        match = _CANONICAL_2.search(html)
        if match:
            return match.group(1)
        return None
