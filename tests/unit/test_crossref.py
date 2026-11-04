"""T0 Pure Unit Tests for Crossref 5.3.1 Builder, Parser, and Protocols.

Verifies:
1. XML Schema 5.3.1 Compliance: valid tags, namespace, posted_content type="preprint".
2. Author and Contributor Mapping: given/surname splitting, coauthors with sequence="additional".
3. ORCID Normalization & Defense: dummy placeholders omitted, valid formats normalized.
4. XML Escaping: titles and abstracts with &, <, > safely encoded.
5. Receipt Invariant Validation: well-formed parsing, malformed detection (missing doi/cr-dep-id).
6. Protocol & Fake Conformance: FakeCrossrefClient fulfills CrossrefClientProtocol.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from phosphene.imi_wordpress.domain import (
    DOI,
    Author,
    DOIRecord,
    DOIStatus,
    EditorialState,
    License,
    VersionInfo,
)

from phosphene.imi.crossref import (
    CrossrefReceiptParser,
    CrossrefXmlBuilder,
)
from phosphene.imi.fakes import FakeCrossrefClient
from phosphene.imi.protocols import CrossrefClientProtocol
from phosphene.imi.work import PreprintWork


def _make_preprint(
    title: str = "Lithic Tool Technologies",
    primary_name: str = "Deborah Barsky",
    primary_orcid: str | None = None,
    coauthor_names: list[str] | None = None,
    suffix: str = "042",
    abstract: str = "A detailed analysis of Pleistocene archaeological tools.",
) -> PreprintWork:
    primary = Author(name=primary_name, orcid=primary_orcid)
    coauthors = [Author(name=name) for name in (coauthor_names or [])]
    doi_rec = DOIRecord(
        doi=DOI(suffix=f"imi.2026.{suffix}"),
        status=DOIStatus.PENDING,
    )
    return PreprintWork(
        title=title,
        primary_author=primary,
        coauthors=coauthors,
        abstract=abstract,
        doi_record=doi_rec,
        version=VersionInfo(number=1),
        editorial_state=EditorialState.LIVE_PREPRINT,
        license=License.CC_BY_NC_SA_4_0,
    )


class TestCrossrefXmlBuilder:
    """T0 Pure Unit Tests for Crossref 5.3.1 XML Generator."""

    def test_basic_xml_generation(self) -> None:
        work = _make_preprint()
        target_url = (
            "https://independentmediainstitute.org/registry/lithic-tool-technologies"
        )
        xml = CrossrefXmlBuilder.build_xml(work, target_url, timestamp=1700000000)

        # Must parse as valid XML
        root = ET.fromstring(xml)
        assert "doi_batch" in root.tag
        assert root.attrib["version"] == "5.3.1"

        # Check posted_content
        posted = root.find(".//{http://www.crossref.org/schema/5.3.1}posted_content")
        assert posted is not None
        assert posted.attrib["type"] == "preprint"

        # Check title
        title_elem = root.find(".//{http://www.crossref.org/schema/5.3.1}title")
        assert title_elem is not None and title_elem.text == "Lithic Tool Technologies"

        # Check DOI data
        doi_elem = root.find(".//{http://www.crossref.org/schema/5.3.1}doi")
        assert doi_elem is not None and doi_elem.text == "10.67767/imi.2026.042"
        res_elem = root.find(".//{http://www.crossref.org/schema/5.3.1}resource")
        assert res_elem is not None and res_elem.text == target_url

    def test_author_name_splitting_and_sequence(self) -> None:
        work = _make_preprint(
            primary_name="Deborah Barsky",
            coauthor_names=["Jan Ritch-Frel", "Santos"],
        )
        xml = CrossrefXmlBuilder.build_xml(
            work, "https://ind.media/reg/test", timestamp=1700000000
        )
        root = ET.fromstring(xml)

        persons = root.findall(".//{http://www.crossref.org/schema/5.3.1}person_name")
        assert len(persons) == 3

        # Primary author
        assert persons[0].attrib["sequence"] == "first"
        assert persons[0].attrib["contributor_role"] == "author"
        given = persons[0].find("{http://www.crossref.org/schema/5.3.1}given_name")
        surname = persons[0].find("{http://www.crossref.org/schema/5.3.1}surname")
        assert given is not None and given.text == "Deborah"
        assert surname is not None and surname.text == "Barsky"

        # Co-author 1: "Jan Ritch-Frel" -> given="Jan", surname="Ritch-Frel"
        assert persons[1].attrib["sequence"] == "additional"
        given1 = persons[1].find("{http://www.crossref.org/schema/5.3.1}given_name")
        surname1 = persons[1].find("{http://www.crossref.org/schema/5.3.1}surname")
        assert given1 is not None and given1.text == "Jan"
        assert surname1 is not None and surname1.text == "Ritch-Frel"

        # Co-author 2: single name "Santos" -> given_name absent, surname="Santos"
        assert persons[2].attrib["sequence"] == "additional"
        given2 = persons[2].find("{http://www.crossref.org/schema/5.3.1}given_name")
        surname2 = persons[2].find("{http://www.crossref.org/schema/5.3.1}surname")
        assert given2 is None
        assert surname2 is not None and surname2.text == "Santos"

    def test_orcid_normalization_and_dummy_rejection(self) -> None:
        # Valid ORCID format
        work_valid = _make_preprint(primary_orcid="0000-0002-1825-0097")
        xml_valid = CrossrefXmlBuilder.build_xml(work_valid, "https://ind.media/test")
        assert "<ORCID>https://orcid.org/0000-0002-1825-0097</ORCID>" in xml_valid

        # Dummy placeholder ORCID MUST be omitted completely
        work_dummy = _make_preprint(primary_orcid="0000-0002-1234-5678")
        xml_dummy = CrossrefXmlBuilder.build_xml(work_dummy, "https://ind.media/test")
        assert "<ORCID>" not in xml_dummy

        # Invalid format string MUST be omitted
        work_invalid = _make_preprint(primary_orcid="not-an-orcid")
        xml_invalid = CrossrefXmlBuilder.build_xml(
            work_invalid, "https://ind.media/test"
        )
        assert "<ORCID>" not in xml_invalid

    def test_xml_escaping(self) -> None:
        work = _make_preprint(
            title="Supply & Demand: <The Economics of \"Care\" & 'Labor'>",
            abstract="Study of R&D across Europe & America.",
        )
        xml = CrossrefXmlBuilder.build_xml(work, "https://ind.media/test")
        # Must parse cleanly without XML syntax errors
        root = ET.fromstring(xml)
        title_elem = root.find(".//{http://www.crossref.org/schema/5.3.1}title")
        assert title_elem is not None
        assert (
            title_elem.text == "Supply & Demand: <The Economics of \"Care\" & 'Labor'>"
        )


class TestCrossrefReceiptParser:
    """T0 Pure Unit Tests for Crossref Receipt Parser."""

    def test_parse_valid_stub_receipt(self) -> None:
        raw = (
            "<deposit_receipt>"
            "<cr-dep-id>cr-dep-9912</cr-dep-id>"
            "<doi>10.67767/imi.2026.042</doi>"
            "<status>pending</status>"
            "</deposit_receipt>"
        )
        receipt = CrossrefReceiptParser.parse(raw)
        assert receipt.is_valid is True
        assert receipt.deposit_id == "cr-dep-9912"
        assert receipt.doi == "10.67767/imi.2026.042"
        assert receipt.status == "pending"
        assert receipt.error is None

    def test_reject_malformed_receipt_missing_doi(self) -> None:
        raw = "<deposit_receipt><cr-dep-id>cr-dep-9912</cr-dep-id></deposit_receipt>"
        receipt = CrossrefReceiptParser.parse(raw)
        assert receipt.is_valid is False
        assert receipt.deposit_id == "cr-dep-9912"
        assert "missing <doi>" in (receipt.error or "")

    def test_reject_malformed_receipt_missing_dep_id(self) -> None:
        raw = "<deposit_receipt><doi>10.67767/imi.2026.042</doi></deposit_receipt>"
        receipt = CrossrefReceiptParser.parse(raw)
        assert receipt.is_valid is False
        assert "missing <cr-dep-id>" in (receipt.error or "")

    def test_reject_invalid_xml(self) -> None:
        receipt = CrossrefReceiptParser.parse("Internal Server Error")
        assert receipt.is_valid is False
        assert "Malformed receipt XML" in (receipt.error or "")


class TestCrossrefProtocolsAndFakes:
    """Verification that FakeCrossrefClient fulfills CrossrefClientProtocol."""

    def test_fake_satisfies_protocol(self) -> None:
        fake = FakeCrossrefClient()
        assert isinstance(fake, CrossrefClientProtocol)

    def test_fake_deposit_and_status_lookup(self) -> None:
        fake = FakeCrossrefClient()
        work = _make_preprint(suffix="088")
        xml = CrossrefXmlBuilder.build_xml(work, "https://ind.media/test")

        receipt = fake.deposit(xml)
        assert receipt.is_valid is True
        assert receipt.deposit_id.startswith("cr-dep-")
        assert receipt.doi == "10.67767/imi.2026.088"
        assert receipt.status == "pending"

        # Query deposit status
        lookup = fake.get_deposit_status(receipt.deposit_id)
        assert lookup.is_valid is True
        assert lookup.deposit_id == receipt.deposit_id
        assert lookup.doi == "10.67767/imi.2026.088"

    def test_fake_scripted_malformed(self) -> None:
        fake = FakeCrossrefClient()
        fake.script_mode("099", "malformed")
        work = _make_preprint(suffix="099")
        xml = CrossrefXmlBuilder.build_xml(work, "https://ind.media/test")

        receipt = fake.deposit(xml)
        assert receipt.is_valid is False
        assert "missing <doi>" in (receipt.error or "")

    def test_fake_scripted_timeout(self) -> None:
        fake = FakeCrossrefClient()
        fake.script_mode("101", "timeout")
        work = _make_preprint(suffix="101")
        xml = CrossrefXmlBuilder.build_xml(work, "https://ind.media/test")

        receipt = fake.deposit(xml)
        assert receipt.is_valid is False
        assert "timeout" in (receipt.error or "").lower()
