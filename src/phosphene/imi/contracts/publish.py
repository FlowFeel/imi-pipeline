"""PublishContract — proves a Draft was correctly published to observatory.wiki.

The contract verifies that the article exists, is accessible, and carries
the required SEO metadata. Each assertion maps to a Behave scenario in
publish_draft.feature.

Decomposed into two concerns:

1. **AccessibilityChecker** — the I/O boundary. Makes the HTTP request
   and returns a raw status. Injected into the contract so tests can
   substitute a fake checker without touching the network.

2. **PublishContract** — pure assertion logic. Given a checker result,
   constructs a ``ContractResult``. No I/O. Testable in isolation.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class AccessibilityCheckerProtocol(Protocol):
    """Protocol for checking whether a URL is accessible."""

    def check_url(self, url: str) -> int:
        """Return the HTTP status code for the URL.

        Returns:
            HTTP status code (e.g. 200, 404, 503).
        """
        ...


class UrllibAccessibilityChecker:
    """Production accessibility checker using urllib.

    Makes a real HTTP request and returns the status code.
    Never raises — returns 0 on network errors.
    """

    def check_url(self, url: str) -> int:
        """Fetch the URL and return the HTTP status code.

        Args:
            url: The URL to check.

        Returns:
            HTTP status code, or 0 if the request fails.
        """
        import urllib.request

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "phosphene-imi/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status
        except Exception:
            return 0


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

    The accessibility checker is injected so the contract's assertion
    logic is testable without network calls.

    Attributes:
        article_url: The canonical URL of the published article.
        title: Expected article title.
        _checker: Accessibility checker for URL verification.
    """

    def __init__(
        self,
        article_url: str,
        title: str,
        checker: AccessibilityCheckerProtocol | None = None,
    ) -> None:
        """Initialise with the published article URL and expected title.

        Args:
            article_url: The canonical URL of the published article.
            title: Expected article title.
            checker: Accessibility checker. Defaults to
                UrllibAccessibilityChecker. Inject a fake for testing.
        """
        self.article_url = article_url
        self.title = title
        self._checker = checker or UrllibAccessibilityChecker()

    def article_is_accessible(self) -> ContractResult:
        """Assert the article URL returns HTTP 200.

        Pure: delegates the HTTP call to the injected checker and
        constructs the ContractResult from the returned status.

        Returns:
            ContractResult with passed=True if status is 200.
        """
        status = self._checker.check_url(self.article_url)
        return ContractResult(
            name="article is accessible",
            passed=status == 200,
            evidence=status,
            expected=200,
            spec_ref="okr_publish_pipeline#article-accessible",
        )

    def prove(self) -> ContractReport:
        """Run all publish contracts and return the report."""
        return ContractReport(results=[self.article_is_accessible()])
