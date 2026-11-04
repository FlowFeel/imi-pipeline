"""Wire adapters transforming domain entities into transport payloads.

This module contains pure projections that isolate wire formats, encoding rules,
and third-party schema requirements from the core domain entities.

@dft
- A1 (pure-io-separation): Pure projection logic — zero I/O imports.
- A2 (determinism): Deterministic encoding transformations.
- A3 (manifest-conformance): WordPressMeta strictly models CPT 39-field contract.
- A4 (dft-docs): This docstring section.
- A6 (check-result): Returns typed payload dictionaries (proof of serialization).
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

from phosphene.imi_wordpress.domain import (
    DOIStatus,
    EditorialState,
    PreprintEntry,
)
from phosphene.utils.html import MetaTag, render_meta_tags
from phosphene.utils.text import join_delimited


class WordPressMeta(TypedDict):
    """Canonical TypedDict representing the 39-field IMI Registry schema."""

    reg_author_name: str
    reg_orcid: str
    reg_affiliation: str
    reg_country: str
    reg_abstract: str
    reg_methodology: str
    reg_license: str
    reg_declaration: bool
    reg_keywords: str
    reg_coauthors: str
    reg_destination_url: str
    reg_published_destination: str
    reg_pdf_url: str
    reg_schema_type: str
    reg_registry_id: str
    reg_pipeline_status: str
    reg_version: int
    reg_version_type: str
    reg_version_history: str
    reg_prior_versions: str
    reg_doi: str
    reg_doi_url: str
    reg_doi_status: str
    reg_doi_minted_date: str
    reg_crossref_deposit_id: str
    reg_withdrawal_notice: NotRequired[str]
    reg_title_original: NotRequired[str]
    reg_image_url: NotRequired[str]
    reg_funding: NotRequired[str]
    reg_conflicts: NotRequired[str]
    reg_data_availability: NotRequired[str]
    reg_registered_date: NotRequired[str]


class WordPressPayload(TypedDict):
    """Payload contract for POST/PATCH to /wp-json/wp/v2/imi_registry."""

    title: str
    status: str
    meta: WordPressMeta
    slug: NotRequired[str]


# Schema.org JSON-LD TypedDict with @-prefixed keys
SchemaJsonLd = TypedDict(
    "SchemaJsonLd",
    {
        "@context": str,
        "@type": str,
        "headline": str,
        "description": str,
        "author": list[dict[str, str]],
        "creativeWorkStatus": NotRequired[str],
        "identifier": NotRequired[str],
        "sameAs": NotRequired[str],
    },
)


class PreprintPayloadAdapter:
    """Pure projections transforming domain instances into wire payloads."""

    @staticmethod
    def to_wordpress(entry: PreprintEntry) -> WordPressPayload:
        """Project a PreprintEntry entity into a WordPress REST API payload.

        Encodes collection semantics (keywords joined by comma, coauthors by newline)
        and maps editorial state to both WP post status and reg_pipeline_status.
        """
        wp_status = "publish" if entry.editorial_state.is_published else "draft"

        pipeline_status = {
            EditorialState.LIVE_PREPRINT: "preprint",
            EditorialState.PUBLISHED: "published",
            EditorialState.WITHDRAWN: "withdrawn",
        }.get(entry.editorial_state, "draft")

        meta: WordPressMeta = {
            "reg_author_name": entry.primary_author.name,
            "reg_orcid": entry.primary_author.orcid,
            "reg_affiliation": entry.primary_author.affiliation,
            "reg_country": entry.primary_author.country,
            "reg_abstract": entry.abstract,
            "reg_methodology": entry.methodology,
            "reg_license": str(entry.license),
            "reg_declaration": entry.declaration,
            "reg_keywords": join_delimited(entry.keywords, delimiter=", "),
            "reg_coauthors": join_delimited(
                (author.name for author in entry.coauthors), delimiter="\n"
            ),
            "reg_destination_url": entry.destination_url,
            "reg_published_destination": entry.published_destination,
            "reg_pdf_url": entry.pdf_url,
            "reg_schema_type": entry.schema_type,
            "reg_registry_id": entry.registry_id,
            "reg_pipeline_status": pipeline_status,
            "reg_version": entry.version.number,
            "reg_version_type": entry.version.version_type,
            "reg_version_history": entry.version.history,
            "reg_prior_versions": join_delimited(entry.version.prior_versions, delimiter="\n"),
            "reg_doi": entry.doi_record.doi.value if entry.doi_record.doi else "",
            "reg_doi_url": entry.doi_record.doi.url if entry.doi_record.doi else "",
            "reg_doi_status": str(entry.doi_record.status),
            "reg_doi_minted_date": entry.doi_record.minted_date,
            "reg_crossref_deposit_id": entry.doi_record.deposit_id,
        }

        if entry.withdrawal_notice:
            meta["reg_withdrawal_notice"] = entry.withdrawal_notice

        payload: WordPressPayload = {
            "title": entry.title,
            "status": wp_status,
            "meta": meta,
        }
        if entry.slug:
            payload["slug"] = entry.slug

        return payload

    @staticmethod
    def to_jsonld(entry: PreprintEntry) -> SchemaJsonLd:
        """Project a PreprintEntry entity into a Schema.org JSON-LD dictionary.

        Emits creativeWorkStatus for preprint compliance (Gap B) and maps
        both primary and co-authors to Person objects.
        """
        authors = [
            {"@type": "Person", "name": author.name}
            for author in (entry.primary_author, *entry.coauthors)
        ]

        data: SchemaJsonLd = {
            "@context": "https://schema.org",
            "@type": entry.schema_type,
            "headline": entry.title,
            "description": entry.abstract,
            "author": authors,
        }

        creative_status = {
            EditorialState.LIVE_PREPRINT: "Preprint",
            EditorialState.PUBLISHED: "Published",
            EditorialState.WITHDRAWN: "Retracted",
        }.get(entry.editorial_state)

        if creative_status:
            data["creativeWorkStatus"] = creative_status

        if entry.doi_record.doi:
            data["identifier"] = entry.doi_record.doi.url
            data["sameAs"] = entry.doi_record.doi.url

        return data

    @staticmethod
    def to_citation_tags(
        entry: PreprintEntry,
        publisher: str = "Independent Media Institute",
    ) -> list[MetaTag]:
        """Project a PreprintEntry into structured MetaTag intermediate representations.

        Pure data manipulation without text rendering or HTML string interpolation.
        Emits separate citation_author tags for primary author and each coauthor,
        and emits citation_doi only when the DOI status is ACTIVE.
        """
        primary_name = (
            entry.primaryAuthor.name
            if hasattr(entry, "primaryAuthor")
            else entry.primary_author.name
        )
        tags: list[MetaTag] = [
            MetaTag(name="citation_title", content=entry.title),
            MetaTag(name="citation_author", content=primary_name),
        ]

        for coauthor in entry.coauthors:
            tags.append(MetaTag(name="citation_author", content=coauthor.name))

        tags.append(MetaTag(name="citation_publisher", content=publisher))

        if entry.abstract:
            tags.append(MetaTag(name="citation_abstract", content=entry.abstract))

        if entry.keywords:
            tags.append(
                MetaTag(
                    name="citation_keywords",
                    content=join_delimited(entry.keywords, delimiter=", "),
                )
            )

        if entry.destination_url:
            tags.append(
                MetaTag(
                    name="citation_fulltext_html_url",
                    content=entry.destination_url,
                )
            )

        if entry.pdf_url:
            tags.append(MetaTag(name="citation_pdf_url", content=entry.pdf_url))

        if entry.doi_record.status == DOIStatus.ACTIVE and entry.doi_record.doi:
            tags.append(MetaTag(name="citation_doi", content=entry.doi_record.doi.value))

        return tags

    @classmethod
    def to_citation_meta(
        cls,
        entry: PreprintEntry,
        publisher: str = "Independent Media Institute",
    ) -> str:
        """Render Google Scholar citation meta tags from a PreprintEntry.

        Delegates to the domain-agnostic render_meta_tags presentation utility.
        """
        return render_meta_tags(cls.to_citation_tags(entry, publisher))
