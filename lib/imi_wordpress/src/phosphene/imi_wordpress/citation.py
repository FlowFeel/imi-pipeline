"""Google Scholar citation meta tag generator.

Google Scholar discovers scholarly content via citation meta tags in ``<head>``.
Without these tags, Observatory articles are invisible to academic search.
CitationMetaGenerator is pure — no WordPress, no HTTP — so it can be tested
without a running WordPress instance.

Produces ``<meta>`` tags conforming to Google Scholar's inclusion guidelines:
https://scholar.google.com/intl/en/scholar/inclusion.html#indexing

Tags generated:
    - ``citation_title`` (required)
    - ``citation_author`` (required)
    - ``citation_publisher`` (required, defaults to Independent Media Institute)
    - ``citation_publication_date`` (optional)
    - ``citation_journal_title`` (optional)
    - ``citation_doi`` (optional)

@dft
- A1 (pure-io-separation): pure logic — no I/O imports, no network.
- A2 (determinism): no datetime/random/uuid. Frozen dataclass.
- A4 (dft-docs): this docstring section.
- A6 (check-result): ``render()`` returns the HTML string (the proof).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape as html_escape


@dataclass(frozen=True)
class CitationMetaGenerator:
    """Frozen dataclass that renders Google Scholar citation meta tags.

    Args:
        title: Article title (required).
        author: Author name (required).
        published_date: Publication date in YYYY/MM/DD format (optional).
        journal: Journal or publication title (optional).
        doi: Digital Object Identifier (optional).
        publisher: Publisher name. Defaults to ``"Independent Media Institute"``.
    """

    title: str
    author: str
    published_date: str | None = None
    journal: str | None = None
    doi: str | None = None
    publisher: str = field(default="Independent Media Institute")

    def render(self) -> str:
        """Render all applicable citation meta tags as an HTML string.

        Returns:
            Newline-joined ``<meta>`` tag string ready for ``<head>`` injection.
        """
        tags: list[str] = [
            self._tag("citation_title", self.title),
            self._tag("citation_author", self.author),
            self._tag("citation_publisher", self.publisher),
        ]
        if self.published_date is not None:
            tags.append(self._tag("citation_publication_date", self.published_date))
        if self.journal is not None:
            tags.append(self._tag("citation_journal_title", self.journal))
        if self.doi is not None:
            tags.append(self._tag("citation_doi", self.doi))
        return "\n".join(tags)

    @staticmethod
    def _tag(name: str, content: str) -> str:
        """Render a single ``<meta>`` tag with HTML-escaped content.

        Args:
            name: Meta tag name attribute value.
            content: Meta tag content attribute value (will be escaped).

        Returns:
            A self-closing ``<meta>`` tag string.
        """
        return f'<meta name="{name}" content="{html_escape(content, quote=True)}" />'


def generate_citation_meta(
    title: str,
    author: str,
    published_date: str | None = None,
    journal: str | None = None,
    doi: str | None = None,
    publisher: str = "Independent Media Institute",
) -> str:
    """Convenience function to generate citation meta tags.

    Creates a :class:`CitationMetaGenerator` and calls :meth:`render`.

    Args:
        title: Article title (required).
        author: Author name (required).
        published_date: Publication date in YYYY/MM/DD format (optional).
        journal: Journal or publication title (optional).
        doi: Digital Object Identifier (optional).
        publisher: Publisher name. Defaults to ``"Independent Media Institute"``.

    Returns:
        Newline-joined ``<meta>`` tag HTML string.
    """
    return CitationMetaGenerator(
        title=title,
        author=author,
        published_date=published_date,
        journal=journal,
        doi=doi,
        publisher=publisher,
    ).render()
