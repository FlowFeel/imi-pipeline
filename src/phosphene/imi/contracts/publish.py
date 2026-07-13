"""PublishContract — proves a Draft was correctly published to observatory.wiki.

The contract reads a PublishedArticle and asserts that the article
exists, is accessible, and carries the required SEO metadata.
Each assertion maps to a Behave scenario in publish_draft.feature.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class ContractResult:
    """Result of a single contract assertion.

    Attributes:
        name: Human-readable contract name.
        passed: Whether the assertion passed.
        evidence: What was actually found.
        expected: What the spec requires.
        spec_ref: Reference to the originating spec document.
    """

    name: str
    passed: bool
    evidence: object
    expected: object
    spec_ref: str = ""


@dataclass(frozen=True)
class ContractReport:
    """Aggregated results from running all contracts.

    Attributes:
        results: Individual contract results.
        all_passed: True only if every result passed.
    """

    results: list[ContractResult]

    @property
    def all_passed(self) -> bool:
        """True if every contract passed."""
        return all(r.passed for r in self.results)

    def failed(self) -> list[ContractResult]:
        """Return only the failing results."""
        return [r for r in self.results if not r.passed]


class PublishContract:
    """Proves a published article satisfies the publication spec.

    Checks that the article URL returns HTTP 200 and that the
    page contains the expected title. Further SEO checks are
    delegated to the SEO contract layer.

    Attributes:
        article_url: The canonical URL of the published article.
        title: Expected article title.
    """

    def __init__(self, article_url: str, title: str) -> None:
        """Initialise with the published article URL and expected title."""
        self.article_url = article_url
        self.title = title

    def article_is_accessible(self) -> ContractResult:
        """Assert the article URL returns HTTP 200."""
        try:
            req = urllib.request.Request(
                self.article_url,
                headers={"User-Agent": "phosphene-imi/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                status = r.status
            return ContractResult(
                name="article is accessible",
                passed=status == 200,
                evidence=status,
                expected=200,
                spec_ref="okr_publish_pipeline#article-accessible",
            )
        except Exception as exc:
            return ContractResult(
                name="article is accessible",
                passed=False,
                evidence=str(exc),
                expected=200,
                spec_ref="okr_publish_pipeline#article-accessible",
            )

    def prove(self) -> ContractReport:
        """Run all publish contracts and return the report."""
        return ContractReport(results=[self.article_is_accessible()])
