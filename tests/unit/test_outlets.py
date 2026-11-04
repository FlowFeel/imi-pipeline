"""Tests for all three publication outlets.

Pure tests using fake clients — no network, no docker, milliseconds.
Each outlet is tested independently via its protocol fake.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from phosphene.imi_wordpress.domain import (
    DOI,
    Author,
    DOIRecord,
    DOIStatus,
    EditorialState,
)

from phosphene.imi.draft import Draft
from phosphene.imi.event import PublicationEvent
from phosphene.imi.fakes import FakeMWClient, FakeSFClient, FakeWPClient
from phosphene.imi.outlets.observatory import ObservatoryOutlet
from phosphene.imi.outlets.salesforce import SalesforceOutlet
from phosphene.imi.outlets.wordpress import WordPressOutlet
from phosphene.imi.work import ArticleDraft, PreprintWork


def make_event(**kwargs: object) -> PublicationEvent:
    """Build a minimal valid PublicationEvent for testing."""
    draft = Draft(
        title=str(kwargs.get("title", "Why Care Work Matters")),
        body=str(kwargs.get("body", "Care work is the foundation of all economies.")),
        author=str(kwargs.get("author", "Gunnar Rundgren")),
        category=str(kwargs.get("category", "Economy")),
    )
    return PublicationEvent(draft=draft, publisher_id="jan")


class TestObservatoryOutlet:
    """Tests for ObservatoryOutlet using FakeMWClient."""

    def test_publish_creates_page_and_returns_url(self) -> None:
        """Publishing a draft creates a MW page and returns its URL."""
        client = FakeMWClient()
        outlet = ObservatoryOutlet(client=client)
        result = outlet.publish(make_event())
        assert result.succeeded is True
        assert result.artifact is not None
        assert "Why_Care_Work_Matters" in result.artifact

    def test_publish_records_page_in_client(self) -> None:
        """The fake client records the created page."""
        client = FakeMWClient()
        outlet = ObservatoryOutlet(client=client)
        outlet.publish(make_event())
        assert client.page_exists("Why Care Work Matters")

    def test_publish_is_idempotent(self) -> None:
        """Publishing the same title twice returns the same URL."""
        client = FakeMWClient()
        outlet = ObservatoryOutlet(client=client)
        result1 = outlet.publish(make_event())
        result2 = outlet.publish(make_event())
        assert result1.artifact == result2.artifact
        assert result2.metadata.get("idempotent") == "true"
        assert len(client.pages) == 1

    def test_publish_failure_returns_failed_result(self) -> None:
        """A client error is captured in OutletResult — not raised."""

        class BreakingClient:
            """A client that always fails."""

            def create_page(self, title: str, content: str, **kw: object) -> dict:
                raise RuntimeError("MW API unavailable")

            def page_exists(self, title: str) -> bool:
                return False

            def page_url(self, title: str) -> str:
                return ""

        outlet = ObservatoryOutlet(client=BreakingClient())  # type: ignore[arg-type]
        result = outlet.publish(make_event())
        assert result.succeeded is False
        assert "MW API unavailable" in (result.error or "")

    def test_outlet_name_is_observatory(self) -> None:
        """Outlet name identifies itself correctly."""
        assert ObservatoryOutlet(FakeMWClient()).name == "observatory"


class TestWordPressOutlet:
    """Tests for WordPressOutlet using FakeWPClient."""

    def test_publish_creates_registry_entry(self) -> None:
        """Publishing creates an imi_registry post and returns its URL."""
        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        result = outlet.publish(make_event())
        assert result.succeeded is True
        assert result.artifact is not None
        assert "imi_registry" in result.artifact

    def test_publish_is_idempotent(self) -> None:
        """Publishing the same slug twice returns the same URL."""
        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        result1 = outlet.publish(make_event())
        result2 = outlet.publish(make_event())
        assert result1.artifact == result2.artifact
        assert result2.metadata.get("idempotent") == "true"
        assert len(client.posts) == 1

    def test_slug_derived_from_title(self) -> None:
        """Slug is a lowercased, hyphenated version of the title."""
        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        outlet.publish(make_event(title="Why Care Work Matters"))
        assert client.post_exists("imi_registry", "why-care-work-matters")

    def test_outlet_name_is_wordpress(self) -> None:
        """Outlet name identifies itself correctly."""
        assert WordPressOutlet(FakeWPClient()).name == "wordpress"

    def test_slug_matches_draft_slug(self) -> None:
        """Outlet uses Draft.slug — not a local slugify — for WP identity.

        T-361 contract: the slug sent to WordPress must equal Draft.slug so
        that idempotency checks use the same identity the WP REST API will
        sanitize to. A local _slugify that preserves non-ASCII breaks this.
        """

        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        event = make_event(title="Why Care Work Matters")
        outlet.publish(event)
        stored_slugs = [k[1] for k in client.posts.keys()]
        assert stored_slugs[0] == event.draft.slug

    def test_non_ascii_title_produces_ascii_slug(self) -> None:
        """Em-dashes, curly quotes, accents are stripped — matching WP sanitize_title.

        WordPress sanitize_title_with_dashes() strips non-ASCII entirely.
        If the outlet preserved them, the first publish would create a post
        with slug 'caf\u00e9-culture' but WP stores 'caf-culture'. The second
        publish checks for the non-ASCII slug, finds nothing, and creates a
        duplicate. This test encodes the fix.
        """
        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        event = make_event(title="Land Reform \u2014 A New Paradigm")
        outlet.publish(event)
        stored_slugs = [k[1] for k in client.posts.keys()]
        slug = stored_slugs[0]
        # Must be pure ASCII
        assert slug.isascii(), f"Slug contains non-ASCII: {slug!r}"
        assert "\u2014" not in slug
        assert slug == event.draft.slug

    def test_idempotency_survives_non_ascii_title(self) -> None:
        """Publishing a non-ASCII title twice returns idempotent result."""
        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        event = make_event(title="Women\u2019s Rights in the 21st Century")
        result1 = outlet.publish(event)
        result2 = outlet.publish(event)
        assert result1.artifact == result2.artifact
        assert result2.metadata.get("idempotent") == "true"
        assert len(client.posts) == 1

    def test_publish_error_captured_not_raised(self) -> None:
        """Client exceptions are captured in OutletResult — never raised."""

        class BreakingWPClient:
            """A client that always fails."""

            def create_post(self, post_type: str, data: dict) -> dict:
                raise RuntimeError("WP REST API unavailable")

            def post_exists(self, post_type: str, slug: str) -> bool:
                return False

            def post_url(self, post_type: str, slug: str) -> str:
                return ""

        outlet = WordPressOutlet(client=BreakingWPClient())  # type: ignore[arg-type]
        result = outlet.publish(make_event())
        assert result.succeeded is False
        assert "WP REST API unavailable" in (result.error or "")

    def test_publish_preprint_work_populates_cpt_scholarly_meta(self) -> None:
        """Publishing a PreprintWork dispatches to PreprintPayloadAdapter with 39 CPT fields."""
        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        preprint = PreprintWork(
            title="Global Economic Trends and Preprints",
            primary_author=Author(
                name="Gunnar Rundgren",
                orcid="0000-0002-1825-0097",
                affiliation="Independent Scholar",
                country="Sweden",
            ),
            abstract="An empirical study of economic systems.",
            doi_record=DOIRecord(
                doi=DOI.from_string("10.5555/imi.2026.001"),
                status=DOIStatus.ACTIVE,
                minted_date="2026-11-04",
            ),
            editorial_state=EditorialState.LIVE_PREPRINT,
            keywords=["Economics", "Agriculture"],
        )
        event = PublicationEvent(work=preprint, publisher_id="jan")
        result = outlet.publish(event)

        assert result.succeeded is True
        assert result.artifact is not None
        post = client.posts[("imi_registry", preprint.slug)]
        assert post["title"] == "Global Economic Trends and Preprints"
        assert post["status"] == "publish"
        meta = post["meta"]
        assert meta["reg_author_name"] == "Gunnar Rundgren"
        assert meta["reg_orcid"] == "0000-0002-1825-0097"
        assert meta["reg_doi"] == "10.5555/imi.2026.001"
        assert meta["reg_doi_status"] == "active"
        assert meta["reg_pipeline_status"] == "preprint"
        assert meta["reg_keywords"] == "Economics, Agriculture"

    def test_publish_preprint_work_is_idempotent(self) -> None:
        """Publishing the same PreprintWork twice skips recreation."""
        client = FakeWPClient()
        outlet = WordPressOutlet(client=client)
        preprint = PreprintWork(
            title="Idempotent Preprint Publication",
            primary_author=Author(name="Test Scholar"),
        )
        event = PublicationEvent(work=preprint, publisher_id="flow")
        res1 = outlet.publish(event)
        res2 = outlet.publish(event)
        assert res1.succeeded is True
        assert res2.succeeded is True
        assert res2.metadata.get("idempotent") == "true"
        assert len(client.posts) == 1


class TestSalesforceOutlet:
    """Tests for SalesforceOutlet using FakeSFClient."""

    def test_publish_creates_sf_record(self) -> None:
        """Publishing creates a Salesforce record and returns its ID."""
        client = FakeSFClient()
        outlet = SalesforceOutlet(client=client)
        result = outlet.publish(make_event())
        assert result.succeeded is True
        assert result.artifact is not None

    def test_publish_is_idempotent(self) -> None:
        """Publishing the same title twice returns without creating duplicate."""
        client = FakeSFClient()
        outlet = SalesforceOutlet(client=client)
        outlet.publish(make_event())
        result2 = outlet.publish(make_event())
        assert result2.succeeded is True
        assert result2.metadata.get("idempotent") == "true"
        assert len(client.records) == 1

    def test_publish_uses_headline_field(self) -> None:
        """Headline__c contains the draft title (not Name which is auto-number)."""
        client = FakeSFClient()
        outlet = SalesforceOutlet(client=client)
        outlet.publish(make_event(title="Why Care Work Matters"))
        record = list(client.records.values())[0]
        assert record.get("Headline__c") == "Why Care Work Matters"
        assert "Name" not in record  # Name is auto-number

    def test_publish_includes_required_boolean_fields(self) -> None:
        """Required boolean fields are always included."""
        client = FakeSFClient()
        outlet = SalesforceOutlet(client=client)
        outlet.publish(make_event())
        record = list(client.records.values())[0]
        assert "Date_Received__c" in record
        assert record.get("Pay__c") is False
        assert record.get("GTM_Site_Uploaded__c") is False
        assert record.get("Translated__c") is False
        assert record.get("Observatory_Classics__c") is False

    def test_publish_uses_correct_url_field(self) -> None:
        """Observatory URL uses Observatory_wiki_Site_Link__c field."""
        client = FakeSFClient()
        outlet = SalesforceOutlet(client=client)
        event = make_event()
        # Inject observatory_url into metadata — immutable so use model_copy
        draft_with_url = event.draft.model_copy(
            update={"metadata": {"observatory_url": "https://observatory.wiki/Test"}}
        )
        event_with_url = event.model_copy(update={"draft": draft_with_url})
        outlet.publish(event_with_url)
        record = list(client.records.values())[0]
        assert (
            record.get("Observatory_wiki_Site_Link__c")
            == "https://observatory.wiki/Test"
        )
        assert "Observatory_URL__c" not in record  # old wrong field name

    def test_idempotency_checks_headline_not_name(self) -> None:
        """Idempotency check uses Headline__c since Name is auto-number."""
        client = FakeSFClient()
        outlet = SalesforceOutlet(client=client)
        # First publish creates the record
        outlet.publish(make_event(title="Duplicate Check"))
        # Second publish should detect it via Headline__c
        result2 = outlet.publish(make_event(title="Duplicate Check"))
        assert result2.metadata.get("idempotent") == "true"
        assert len(client.records) == 1

    def test_outlet_name_is_salesforce(self) -> None:
        """Outlet name identifies itself correctly."""
        assert SalesforceOutlet(FakeSFClient()).name == "salesforce"
