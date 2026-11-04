"""Unit tests for Crossref 5.3.1 generator, ORCID normalization, and receipt parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from phosphene.imi.crossref import (
    CrossrefContributor,
    CrossrefDepositBatch,
    CrossrefDepositRecord,
    DepositStatus,
    normalize_orcid,
    parse_deposit_receipt,
    render_crossref_xml,
)


class TestOrcidNormalization:
    def test_valid_orcid_formats(self) -> None:
        assert (
            normalize_orcid("0000-0002-1825-0097")
            == "https://orcid.org/0000-0002-1825-0097"
        )
        assert (
            normalize_orcid("http://orcid.org/0000-0002-1825-0097")
            == "https://orcid.org/0000-0002-1825-0097"
        )
        assert (
            normalize_orcid("https://orcid.org/0000-0001-5109-3700")
            == "https://orcid.org/0000-0001-5109-3700"
        )
        assert (
            normalize_orcid("0000-0002-1694-233x")
            == "https://orcid.org/0000-0002-1694-233X"
        )

    def test_empty_orcid_returns_empty(self) -> None:
        assert normalize_orcid("") == ""
        assert normalize_orcid("   ") == ""

    def test_invalid_orcid_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid ORCID"):
            normalize_orcid("invalid-orcid")

        with pytest.raises(ValueError, match="Invalid ORCID"):
            normalize_orcid("0000-0002-1825")


class TestCrossrefXmlGenerator:
    def test_renders_valid_schema_531_xml(self) -> None:
        primary = CrossrefContributor(
            name="Deborah Barsky",
            sequence="first",
            orcid="0000-0002-1825-0097",
            affiliation="IPHES, Tarragona",
        )
        coauthor = CrossrefContributor(
            name="Maria Santos",
            sequence="additional",
        )

        record = CrossrefDepositRecord(
            title="Lithic Tool Technologies & Handaxe Typology",
            doi="10.67767/imi.2026.042",
            resource_url="https://independentmediainstitute.org/registry/imi-2026-042/",
            primary_author=primary,
            coauthors=(coauthor,),
            abstract="A comprehensive analysis of Acheulean bifacial artifacts.",
            posted_date="2026-11-04",
        )

        batch = CrossrefDepositBatch(
            batch_id="batch-test-042",
            timestamp=1793755000,
            records=(record,),
        )

        xml_output = render_crossref_xml(batch)

        # 1. Structural assertions
        assert 'version="5.3.1"' in xml_output
        assert "http://www.crossref.org/schema/5.3.1" in xml_output
        assert "<doi_batch_id>batch-test-042</doi_batch_id>" in xml_output
        assert "<doi>10.67767/imi.2026.042</doi>" in xml_output
        assert (
            "<resource>https://independentmediainstitute.org/registry/imi-2026-042/</resource>"
            in xml_output
        )
        assert "<surname>Barsky</surname>" in xml_output
        assert "<given_name>Deborah</given_name>" in xml_output
        assert "<ORCID>https://orcid.org/0000-0002-1825-0097</ORCID>" in xml_output
        assert "<institution_name>IPHES, Tarragona</institution_name>" in xml_output
        assert "<jats:p>A comprehensive analysis" in xml_output

        # 2. Parse with ElementTree to verify XML well-formedness
        root = ET.fromstring(xml_output)
        assert root.tag.endswith("doi_batch")

    def test_invalid_prefix_rejected_by_record(self) -> None:
        author = CrossrefContributor(name="Jan Ritch-Frel")
        with pytest.raises(ValueError, match="Invalid DOI prefix"):
            CrossrefDepositRecord(
                title="Title",
                doi="10.12345/wrong.prefix",
                resource_url="https://example.org",
                primary_author=author,
            )


class TestReceiptParser:
    def test_parses_success_receipt(self) -> None:
        xml = (
            "<deposit_receipt>"
            "<cr-dep-id>cr-dep-9912</cr-dep-id>"
            "<doi>10.67767/imi.2026.042</doi>"
            "<status>completed</status>"
            "</deposit_receipt>"
        )
        receipt = parse_deposit_receipt(xml)
        assert receipt.deposit_id == "cr-dep-9912"
        assert receipt.doi == "10.67767/imi.2026.042"
        assert receipt.status == DepositStatus.COMPLETED

    def test_parses_pending_receipt(self) -> None:
        xml = (
            "<deposit_receipt>"
            "<cr-dep-id>cr-dep-9913</cr-dep-id>"
            "<doi>10.67767/imi.2026.043</doi>"
            "<status>pending</status>"
            "</deposit_receipt>"
        )
        receipt = parse_deposit_receipt(xml)
        assert receipt.deposit_id == "cr-dep-9913"
        assert receipt.status == DepositStatus.PENDING

    def test_malformed_receipt_missing_doi_flags_failed(self) -> None:
        xml = "<deposit_receipt><cr-dep-id>cr-dep-9914</cr-dep-id></deposit_receipt>"
        receipt = parse_deposit_receipt(xml)
        assert receipt.deposit_id == "cr-dep-9914"
        assert receipt.doi == ""
        assert receipt.status == DepositStatus.FAILED
