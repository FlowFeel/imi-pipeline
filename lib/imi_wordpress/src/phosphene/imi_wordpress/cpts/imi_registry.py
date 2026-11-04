"""IMI Registry custom post type definition.

@dft
- A1 (pure-io-separation): pure logic — no I/O imports. Only ``dataclasses``.
- A2 (determinism): no datetime/random/uuid.
- A3 (manifest-conformance): ``to_wp_payload()`` produces the declared
  meta keys (``author_name``, ``category``, ``source_url``).
- A6 (check-result): ``to_wp_payload()`` returns the payload dict (the proof).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IMIRegistryMeta:
    """Meta fields for an IMI Registry post.

    Attributes:
        author_name: Display name of the article author.
        category: Content category (e.g. 'Economy', 'Environment').
        source_url: Original source URL for the article.
    """

    author_name: str = ""
    category: str = ""
    source_url: str = ""


@dataclass
class IMIRegistryPost:
    """An IMI Registry custom post type instance.

    Attributes:
        title: Post title.
        slug: URL slug (auto-generated from title if empty).
        status: WordPress post status (draft, publish, pending).
        meta: IMI Registry meta fields.
    """

    title: str
    slug: str = ""
    status: str = "draft"
    meta: IMIRegistryMeta = field(default_factory=IMIRegistryMeta)

    def to_wp_payload(self) -> dict[str, Any]:
        """Convert to a WordPress REST API payload dict.

        Returns:
            Dict suitable for POST to /wp-json/wp/v2/imi_registry.
        """
        payload: dict[str, Any] = {
            "title": self.title,
            "status": self.status,
            "meta": {
                "author_name": self.meta.author_name,
                "category": self.meta.category,
                "source_url": self.meta.source_url,
            },
        }
        if self.slug:
            payload["slug"] = self.slug
        return payload
