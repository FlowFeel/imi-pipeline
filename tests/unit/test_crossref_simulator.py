"""T0 Pure Unit Tests for the Hermetic Crossref Schema 5.3.1 Simulator Engine.

Verifies that the simulator behaves as an axiomatic court for Crossref deposits:
- Enforces Schema 5.3.1 structure (namespaces, head, depositor, contributors, titles, doi_data).
- Rejects malformed or incomplete XML with authentic Crossref batch diagnostics.
- Registers DOIs and simulates HTTP 302 resolution to the registered target resource.
- Emulates error injection (timeout, malformed receipt, reject) for saga testing.

OKR: @okr_doi_preprint
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

from phosphene.imi.crossref import CrossrefXmlBuilder
from phosphene.imi.crossref_simulator import CrossrefSimulatorEngine
from phosphene.imi.work import PreprintWork


def _make_preprint(
    title: str = "Subsurface Lithic Morphologies",
    primary_name: str = "Deborah Barsky",
    primary_orcid: str = "0000-0002-1825-0097",
    coauthor_names: list[str] | None = None,
    suffix: str = "042",
    prefix: str = "10.67767",
) -> PreprintWork:
    primary = Author(name=primary_name, orcid=primary_orcid, affiliation="IPHES")
    coauthors = [
        Author(name=name, affiliation="University") for name in (coauthor_names or [])
    ]
    doi_rec = DOIRecord(
        doi=DOI(suffix=f"imi.2026.{suffix}", prefix=prefix),
        status=DOIStatus.PENDING,
    )
    return PreprintWork(
        title=title,
        primary_author=primary,
        coauthors=coauthors,
        abstract="Archaeological analysis of lithic cutting edges.",
        doi_record=doi_rec,
        version=VersionInfo(number=1),
        editorial_state=EditorialState.LIVE_PREPRINT,
        license=License.CC_BY_NC_SA_4_0,
    )


class TestCrossrefSimulatorEngine:
    """T0 Pure Unit Tests for CrossrefSimulatorEngine."""

    def test_valid_deposit_accepted_and_registered(self) -> None:
        engine = CrossrefSimulatorEngine()
        work = _make_preprint(suffix="101")
        target_url = "https://ind.media/registry/subsurface-lithic-morphologies"
        xml = CrossrefXmlBuilder.build_xml(work, target_url=target_url)

        res = engine.deposit(xml)
        assert res.status_code == 201
        assert res.is_valid is True
        assert res.deposit_id.startswith("cr-dep-")
        assert res.doi == "10.67767/imi.2026.101"
        assert res.target_url == target_url

        # Check receipt XML
        root = ET.fromstring(res.response_body)
        assert root.find("doi").text == "10.67767/imi.2026.101"
        assert root.find("status").text == "pending"

        # Check resolution mapping
        assert engine.resolve_doi("10.67767/imi.2026.101") == target_url

    def test_resolution_unregistered_doi_returns_none(self) -> None:
        engine = CrossrefSimulatorEngine()
        assert engine.resolve_doi("10.67767/imi.2026.999") is None

    def test_reject_missing_namespace(self) -> None:
        engine = CrossrefSimulatorEngine()
        bad_xml = '<doi_batch version="5.3.1"><head><doi_batch_id>1</doi_batch_id></head></doi_batch>'
        res = engine.deposit(bad_xml)
        assert res.status_code == 400
        assert res.is_valid is False
        assert "namespace" in (res.error or "").lower()

    def test_reject_wrong_version(self) -> None:
        engine = CrossrefSimulatorEngine()
        bad_xml = '<doi_batch xmlns="http://www.crossref.org/schema/5.3.1" version="4.4.2"></doi_batch>'
        res = engine.deposit(bad_xml)
        assert res.status_code == 400
        assert res.is_valid is False
        assert "version must be 5.3.1" in (res.error or "").lower()

    def test_reject_missing_depositor(self) -> None:
        engine = CrossrefSimulatorEngine()
        bad_xml = """<doi_batch xmlns="http://www.crossref.org/schema/5.3.1" version="5.3.1">
          <head>
            <doi_batch_id>batch-1</doi_batch_id>
            <timestamp>1700000000</timestamp>
            <registrant>IMI</registrant>
          </head>
          <body></body>
        </doi_batch>"""
        res = engine.deposit(bad_xml)
        assert res.status_code == 400
        assert "depositor" in (res.error or "").lower()

    def test_reject_missing_first_author_sequence(self) -> None:
        engine = CrossrefSimulatorEngine()
        # Person with sequence="additional" instead of "first"
        bad_xml = """<doi_batch xmlns="http://www.crossref.org/schema/5.3.1" version="5.3.1">
          <head>
            <doi_batch_id>batch-1</doi_batch_id>
            <timestamp>1700000000</timestamp>
            <depositor><depositor_name>IMI</depositor_name><email_address>flow@ind.media</email_address></depositor>
            <registrant>IMI</registrant>
          </head>
          <body>
            <posted_content type="preprint">
              <contributors>
                <person_name sequence="additional" contributor_role="author">
                  <surname>Barsky</surname>
                </person_name>
              </contributors>
              <titles><title>Title</title></titles>
              <posted_date><month>11</month><day>5</day><year>2026</year></posted_date>
              <doi_data><doi>10.67767/imi.2026.111</doi><resource>https://ind.media</resource></doi_data>
            </posted_content>
          </body>
        </doi_batch>"""
        res = engine.deposit(bad_xml)
        assert res.status_code == 400
        assert "first" in (res.error or "").lower()

    def test_reject_unauthorized_doi_prefix(self) -> None:
        engine = CrossrefSimulatorEngine(allowed_prefix="10.67767")
        work = _make_preprint(prefix="10.59888")
        xml = CrossrefXmlBuilder.build_xml(work, target_url="https://ind.media/test")
        res = engine.deposit(xml)
        assert res.status_code == 400
        assert "unauthorized prefix" in (res.error or "").lower()

    def test_reject_dummy_orcid(self) -> None:
        engine = CrossrefSimulatorEngine()
        # Direct XML containing the dummy ORCID
        bad_xml = """<doi_batch xmlns="http://www.crossref.org/schema/5.3.1" version="5.3.1">
          <head>
            <doi_batch_id>batch-1</doi_batch_id>
            <timestamp>1700000000</timestamp>
            <depositor><depositor_name>IMI</depositor_name><email_address>flow@ind.media</email_address></depositor>
            <registrant>IMI</registrant>
          </head>
          <body>
            <posted_content type="preprint">
              <contributors>
                <person_name sequence="first" contributor_role="author">
                  <surname>Barsky</surname>
                  <ORCID>https://orcid.org/0000-0002-1234-5678</ORCID>
                </person_name>
              </contributors>
              <titles><title>Title</title></titles>
              <posted_date><month>11</month><day>5</day><year>2026</year></posted_date>
              <doi_data><doi>10.67767/imi.2026.111</doi><resource>https://ind.media</resource></doi_data>
            </posted_content>
          </body>
        </doi_batch>"""
        res = engine.deposit(bad_xml)
        assert res.status_code == 400
        assert "dummy orcid" in (res.error or "").lower()

    def test_scripted_modes_timeout_and_malformed(self) -> None:
        engine = CrossrefSimulatorEngine()
        engine.script_mode("201", "timeout")
        engine.script_mode("202", "malformed")

        work1 = _make_preprint(suffix="201")
        xml1 = CrossrefXmlBuilder.build_xml(work1, "https://ind.media/test")
        res1 = engine.deposit(xml1)
        assert res1.status_code == 500
        assert "timeout" in (res1.error or "").lower()

        work2 = _make_preprint(suffix="202")
        xml2 = CrossrefXmlBuilder.build_xml(work2, "https://ind.media/test")
        res2 = engine.deposit(xml2)
        assert res2.status_code == 201
        assert "<doi>" not in res2.response_body  # malformed receipt
