"""T0 Pure Unit Verification Suite for PublicationWork Discriminated Union.

Verifies:
1. InvariantStatic rigor: frozen immutability, extra-forbidden schemas, null-omission.
2. State-space partitioning: ArticleDraft vs PreprintWork algebraic sum type.
3. Unidirectional projection: PreprintWork.to_article_view().
4. Formal promotion factory: promote_to_preprint().
5. Wire serialization: deterministic JSON roundtrip via TypeAdapter(PublicationWork).
6. PublicationEvent integration: legacy draft compatibility and polymorphic work handling.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import json

import pytest
from phosphene.imi_wordpress.domain import (
    DOI,
    Author,
    DOIRecord,
    DOIStatus,
    EditorialState,
    License,
    VersionInfo,
)
from pydantic import TypeAdapter, ValidationError

from phosphene.imi.event import PublicationEvent
from phosphene.imi.work import (
    ArticleDraft,
    Draft,
    PreprintWork,
    PublicationWork,
    promote_to_preprint,
)


class TestArticleDraftInvariants:
    """Invariant static constraints on journalistic ArticleDraft."""

    def test_valid_article_draft_creation(self) -> None:
        art = ArticleDraft(
            title="Why Care Work Matters",
            body="Comprehensive analysis of labor economics.",
            author="Gunnar Rundgren",
            category="Economy",
            keywords=["economics", "care-work"],
        )
        assert art.kind == "article"
        assert art.title == "Why Care Work Matters"
        assert art.slug == "why-care-work-matters"
        assert art.keywords == ["economics", "care-work"]

    def test_forbid_empty_strings(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            ArticleDraft(
                title="   ",
                body="Some text",
                author="Author",
                category="Economy",
            )

    def test_forbid_extra_fields(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ArticleDraft(  # type: ignore[call-arg]
                title="Title",
                body="Body",
                author="Author",
                category="Economy",
                extra_leak="malicious_or_accidental",
            )

    def test_frozen_immutability(self) -> None:
        art = ArticleDraft(
            title="Title",
            body="Body",
            author="Author",
            category="Economy",
        )
        with pytest.raises(ValidationError, match="Instance is frozen"):
            art.title = "Mutated"  # type: ignore[misc]

    def test_draft_backward_compatibility_alias(self) -> None:
        d = Draft(
            title="Title",
            body="Body",
            author="Author",
            category="Economy",
        )
        assert isinstance(d, ArticleDraft)
        assert d.kind == "article"


class TestPreprintWorkInvariants:
    """Invariant static constraints on scholarly PreprintWork."""

    def test_valid_preprint_creation(self) -> None:
        prep = PreprintWork(
            title="Lithic Technologies in Pleistocene",
            primary_author=Author(name="Deborah Barsky", orcid="0000-0002-1825-0097"),
            abstract="Study of early tool manufacturing techniques.",
            methodology="Micro-wear and stratigraphy analysis.",
            license=License.CC_BY_4_0,
            keywords=["archaeology", "pleistocene"],
            coauthors=[Author(name="Alain Tuffreau")],
            pdf_url="https://ind.media/pdf/lithic-v1.pdf",
            doi_record=DOIRecord(
                doi=DOI(suffix="imi.2026.042"),
                status=DOIStatus.ACTIVE,
                deposit_id="cr-dep-9912",
                minted_date="2026-11-01",
            ),
            version=VersionInfo(number=1),
            editorial_state=EditorialState.LIVE_PREPRINT,
        )
        assert prep.kind == "preprint"
        assert prep.slug == "lithic-technologies-in-pleistocene"
        assert prep.doi_record.doi is not None
        assert prep.doi_record.doi.value == "10.67767/imi.2026.042"
        assert prep.doi_record.status == DOIStatus.ACTIVE

    def test_forbid_empty_title_or_author(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            PreprintWork(
                title="",
                primary_author=Author(name="Author"),
            )
        with pytest.raises(ValidationError, match="must not be empty"):
            PreprintWork(
                title="Valid Title",
                primary_author=Author(name="  "),
            )

    def test_forbid_extra_fields(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            PreprintWork(  # type: ignore[call-arg]
                title="Title",
                primary_author=Author(name="Author"),
                leaked_attribute="forbidden",
            )

    def test_projection_to_preprint_entry(self) -> None:
        prep = PreprintWork(
            title="Agade Positional Survey",
            primary_author=Author(name="Julian Reade"),
            abstract="Locational analysis based on Tigris canal networks.",
            pdf_url="https://ind.media/pdf/agade-v1.pdf",
            doi_record=DOIRecord(
                doi=DOI(suffix="imi.2026.088"),
                status=DOIStatus.ACTIVE,
                deposit_id="cr-dep-8811",
            ),
            version=VersionInfo(number=1),
            editorial_state=EditorialState.LIVE_PREPRINT,
        )
        entry = prep.to_preprint_entry()
        assert entry.title == prep.title
        assert entry.slug == prep.slug
        assert entry.primary_author.name == "Julian Reade"
        assert entry.doi_record.doi is not None
        assert entry.doi_record.doi.value == "10.67767/imi.2026.088"
        assert entry.editorial_state == EditorialState.LIVE_PREPRINT


class TestUnidirectionalProjection:
    """Read-only projection from PreprintWork to ArticleDraft."""

    def test_live_preprint_projects_article_view_with_banner(self) -> None:
        prep = PreprintWork(
            title="Body-Grammar Typology",
            primary_author=Author(name="Jan Ritch-Frel"),
            abstract="Typological survey of embodied language structures.",
            keywords=["language", "cognitive-science"],
            destination_url="https://observatory.wiki/Body_Grammar",
            editorial_state=EditorialState.LIVE_PREPRINT,
            body="Full narrative wikitext body of the paper.",
        )
        article_view = prep.to_article_view()
        assert isinstance(article_view, ArticleDraft)
        assert article_view.kind == "article"
        assert article_view.title == "Body-Grammar Typology"
        assert article_view.author == "Jan Ritch-Frel"
        assert article_view.category == "Preprints"
        assert article_view.body.startswith(
            "{{Preprint}}\n\nFull narrative wikitext body"
        )
        assert article_view.source_url == "https://observatory.wiki/Body_Grammar"

    def test_draft_preprint_omits_banner_in_article_view(self) -> None:
        prep = PreprintWork(
            title="Early Draft Discovery",
            primary_author=Author(name="Author"),
            abstract="Abstract only.",
            editorial_state=EditorialState.DRAFT,
        )
        article_view = prep.to_article_view()
        assert not article_view.body.startswith("{{Preprint}}")
        assert article_view.body == "Abstract only."


class TestFormalPromotionFactory:
    """Formal promotion from ArticleDraft into PreprintWork."""

    def test_promote_to_preprint_preserves_provenance(self) -> None:
        draft = ArticleDraft(
            title="Degrowth in Global Supply Chains",
            body="Detailed macroeconomic breakdown of logistics networks.",
            author="Maria Santos",
            category="Economy",
            keywords=["degrowth", "supply-chains"],
            source_url="https://ind.media/drafts/degrowth",
        )
        prep = promote_to_preprint(
            draft,
            abstract="Synthesized abstract for scholarly indexing.",
            methodology="Input-output matrix modeling.",
            license=License.CC_BY_4_0,
            pdf_url="https://ind.media/pdf/degrowth-v1.pdf",
            editorial_state=EditorialState.LIVE_PREPRINT,
            doi_record=DOIRecord(
                doi=DOI(suffix="imi.2026.050"),
                status=DOIStatus.PENDING,
            ),
        )
        assert isinstance(prep, PreprintWork)
        assert prep.kind == "preprint"
        assert prep.title == draft.title
        assert prep.slug == draft.slug
        assert prep.primary_author.name == "Maria Santos"
        assert prep.abstract == "Synthesized abstract for scholarly indexing."
        assert prep.body == draft.body
        assert prep.doi_record.doi is not None
        assert prep.doi_record.doi.value == "10.67767/imi.2026.050"
        assert prep.doi_record.status == DOIStatus.PENDING
        assert prep.version.number == 1
        # Confirm originating draft remained completely unchanged
        assert draft.title == "Degrowth in Global Supply Chains"
        assert draft.kind == "article"


class TestWireSerializationRoundtrip:
    """Deterministic wire roundtrips across task execution boundaries."""

    def test_article_draft_json_roundtrip(self) -> None:
        art = ArticleDraft(
            title="Idempotent Publishing",
            body="Article body content.",
            author="Flow",
            category="Technology",
        )
        dump = art.model_dump_json()
        restored = TypeAdapter(PublicationWork).validate_json(dump)
        assert isinstance(restored, ArticleDraft)
        assert restored == art

    def test_preprint_work_json_roundtrip(self) -> None:
        prep = PreprintWork(
            title="Marine Debris Valuation",
            primary_author=Author(name="Elena Rostova", orcid="0000-0001-9876-5432"),
            abstract="Valuation methodology for pelagic plastic pollution.",
            methodology="Remote sensing and coastal survey.",
            keywords=["marine-biology", "ecology"],
            doi_record=DOIRecord(
                doi=DOI(suffix="imi.2026.110"),
                status=DOIStatus.ACTIVE,
                deposit_id="cr-dep-7710",
                minted_date="2026-11-04",
            ),
            version=VersionInfo(number=2),
            editorial_state=EditorialState.LIVE_PREPRINT,
        )
        dump = prep.model_dump_json()
        restored = TypeAdapter(PublicationWork).validate_json(dump)
        assert isinstance(restored, PreprintWork)
        assert restored.kind == "preprint"
        assert restored.title == prep.title
        assert restored.doi_record.status == DOIStatus.ACTIVE
        assert restored.doi_record.doi is not None
        assert restored.doi_record.doi.value == "10.67767/imi.2026.110"

    def test_invalid_discriminator_rejected(self) -> None:
        raw_json = json.dumps({"kind": "unknown_kind", "title": "Invalid"})
        with pytest.raises(ValidationError, match="Input tag 'unknown_kind' found"):
            TypeAdapter(PublicationWork).validate_json(raw_json)


class TestPublicationEventIntegration:
    """PublicationEvent integration with PublicationWork."""

    def test_legacy_draft_initialization(self) -> None:
        art = ArticleDraft(
            title="Legacy Draft",
            body="Text",
            author="Author",
            category="General",
        )
        event = PublicationEvent(draft=art, publisher_id="jan")
        assert event.work.kind == "article"
        assert event.draft == art
        assert event.idempotency_key == "legacy-draft"

    def test_preprint_work_initialization(self) -> None:
        prep = PreprintWork(
            title="Scholarly Work",
            primary_author=Author(name="Dr. Scholar"),
            abstract="Scholarly abstract.",
        )
        event = PublicationEvent(work=prep, publisher_id="flow")
        assert event.work.kind == "preprint"
        # Accessing .draft projects to ArticleDraft
        assert isinstance(event.draft, ArticleDraft)
        assert event.draft.author == "Dr. Scholar"
        assert event.idempotency_key == "scholarly-work"

    def test_event_json_roundtrip(self) -> None:
        prep = PreprintWork(
            title="Event Roundtrip Paper",
            primary_author=Author(name="Author"),
            abstract="Abstract.",
        )
        event = PublicationEvent(work=prep, publisher_id="flow")
        dump = event.model_dump_json()
        restored = TypeAdapter(PublicationEvent).validate_json(dump)
        assert restored.work.kind == "preprint"
        assert restored.publisher_id == "flow"
        assert restored.idempotency_key == "event-roundtrip-paper"
