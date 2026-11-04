"""Crossref Schema 5.3.1 deposit builder, receipt parser, and HTTP client.

Decomposes the scholarly Crossref deposit process into pure DFT layers:
1. Pure POPO / XML assembly (CrossrefXmlBuilder) — transforms a PreprintWork
   into schema 5.3.1 compliant XML. Zero network I/O.
2. Pure receipt parser (CrossrefReceiptParser) — extracts deposit ID, DOI,
   and status while validating receipt invariants (e.g. malformed detection).
3. Client protocol & HTTP transport (CrossrefClientProtocol, HttpCrossrefClient)
   — communicates with doi.crossref.org or test stub over HTTPS.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from phosphene.imi.protocols import CrossrefClientProtocol
from phosphene.imi.work import PreprintWork

# ── Precompiled Invariant Regexes ──────────────────────────────────────────
_ORCID_RE = re.compile(
    r"^https?://orcid\.org/0000-000[1-3]-\d{4}-\d{3}[\dX]$",
    re.IGNORECASE,
)
_DUMMY_ORCIDS = frozenset(
    {
        "0000-0002-1234-5678",
        "https://orcid.org/0000-0002-1234-5678",
        "http://orcid.org/0000-0002-1234-5678",
    }
)
_CR_DEP_PATTERN = re.compile(r"cr-dep-\d+")
_XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'

CROSSREF_SCHEMA_VERSION = "5.3.1"
CROSSREF_XMLNS = "http://www.crossref.org/schema/5.3.1"
DEFAULT_DEPOSITOR_NAME = "Independent Media Institute"
DEFAULT_DEPOSITOR_EMAIL = "flow@ind.media"
DEFAULT_REGISTRANT = "Independent Media Institute"


@dataclass(frozen=True)
class CrossrefReceipt:
    """Immutable representation of a Crossref deposit confirmation receipt.

    Attributes:
        deposit_id: Crossref deposit tracking ID (e.g. 'cr-dep-9001').
        doi: Registered DOI string.
        status: Deposit status (e.g. 'pending', 'registered', 'active', 'failed').
        is_valid: Whether the receipt satisfied well-formed schema constraints.
        error: Diagnostic error message if invalid.
        raw: Raw receipt body text.
    """

    deposit_id: str = ""
    doi: str = ""
    status: str = "pending"
    is_valid: bool = True
    error: str | None = None
    raw: str = ""


class CrossrefXmlBuilder:
    """Pure domain builder creating Crossref Schema 5.3.1 XML for Preprints."""

    @staticmethod
    def normalize_orcid(raw_orcid: str | None) -> str | None:
        """Validate and normalize an ORCID identifier.

        Returns:
            Normalized 'https://orcid.org/...' string, or None if invalid/dummy.
        """
        if not raw_orcid:
            return None
        cleaned = raw_orcid.strip()
        if not cleaned or cleaned in _DUMMY_ORCIDS:
            return None
        if not cleaned.startswith("http"):
            cleaned = f"https://orcid.org/{cleaned}"
        if _ORCID_RE.match(cleaned):
            return cleaned
        return None

    @classmethod
    def _split_name(cls, full_name: str) -> tuple[str, str]:
        """Split a personal name into (given_name, surname)."""
        parts = full_name.strip().split()
        if not parts:
            return "", "Unknown"
        if len(parts) == 1:
            return "", parts[0]
        return " ".join(parts[:-1]), parts[-1]

    @classmethod
    def build_xml(
        cls,
        work: PreprintWork,
        target_url: str,
        *,
        batch_id: str | None = None,
        timestamp: int | None = None,
    ) -> str:
        """Generate Crossref 5.3.1 XML for a preprint.

        Args:
            work: Pure PreprintWork domain POPO.
            target_url: Landing page URL where the DOI must resolve.
            batch_id: Optional unique batch identifier.
            timestamp: Optional epoch timestamp.

        Returns:
            Well-formed Crossref deposit XML string.
        """
        ts = int(timestamp if timestamp is not None else time.time())
        b_id = batch_id or f"imi-{work.slug[:40]}-{ts}"
        doi_val = work.doi_record.doi.value if work.doi_record.doi else ""

        # Build contributors
        contributors_xml: list[str] = []

        # Primary author
        given, surname = cls._split_name(work.primary_author.name)
        orcid = cls.normalize_orcid(work.primary_author.orcid)
        orcid_tag = f"            <ORCID>{xml_escape(orcid)}</ORCID>\n" if orcid else ""
        given_tag = (
            f"            <given_name>{xml_escape(given)}</given_name>\n"
            if given
            else ""
        )
        contributors_xml.append(
            '          <person_name sequence="first" contributor_role="author">\n'
            f"{given_tag}"
            f"            <surname>{xml_escape(surname)}</surname>\n"
            f"{orcid_tag}"
            "          </person_name>"
        )

        # Co-authors
        for coauthor in work.coauthors:
            co_given, co_surname = cls._split_name(coauthor.name)
            co_orcid = cls.normalize_orcid(coauthor.orcid)
            co_orcid_tag = (
                f"            <ORCID>{xml_escape(co_orcid)}</ORCID>\n"
                if co_orcid
                else ""
            )
            co_given_tag = (
                f"            <given_name>{xml_escape(co_given)}</given_name>\n"
                if co_given
                else ""
            )
            contributors_xml.append(
                '          <person_name sequence="additional" contributor_role="author">\n'
                f"{co_given_tag}"
                f"            <surname>{xml_escape(co_surname)}</surname>\n"
                f"{co_orcid_tag}"
                "          </person_name>"
            )

        contributors_block = "\n".join(contributors_xml)

        # Date
        now_dt = time.gmtime(ts)
        year = now_dt.tm_year
        month = f"{now_dt.tm_mon:02d}"
        day = f"{now_dt.tm_mday:02d}"

        # Abstract
        abstract_block = ""
        if work.abstract and work.abstract.strip():
            abstract_block = (
                f'        <abstract xmlns="http://www.ncbi.nlm.nih.gov/JATS1">\n'
                f"          <p>{xml_escape(work.abstract.strip())}</p>\n"
                f"        </abstract>\n"
            )

        # Item number
        item_num = work.registry_id.strip() if work.registry_id else work.slug
        item_number_block = (
            f"        <item_number>{xml_escape(item_num)}</item_number>\n"
            if item_num
            else ""
        )

        xml = (
            f"{_XML_HEADER}"
            f'<doi_batch version="{CROSSREF_SCHEMA_VERSION}" '
            f'xmlns="{CROSSREF_XMLNS}" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            f'xsi:schemaLocation="{CROSSREF_XMLNS} '
            'http://www.crossref.org/schemas/crossref5.3.1.xsd">\n'
            "  <head>\n"
            f"    <doi_batch_id>{xml_escape(b_id)}</doi_batch_id>\n"
            f"    <timestamp>{ts}</timestamp>\n"
            "    <depositor>\n"
            f"      <depositor_name>{DEFAULT_DEPOSITOR_NAME}</depositor_name>\n"
            f"      <email_address>{DEFAULT_DEPOSITOR_EMAIL}</email_address>\n"
            "    </depositor>\n"
            f"    <registrant>{DEFAULT_REGISTRANT}</registrant>\n"
            "  </head>\n"
            "  <body>\n"
            '    <posted_content type="preprint">\n'
            "      <contributors>\n"
            f"{contributors_block}\n"
            "      </contributors>\n"
            "      <titles>\n"
            f"        <title>{xml_escape(work.title)}</title>\n"
            "      </titles>\n"
            "      <posted_date>\n"
            f"        <year>{year}</year>\n"
            f"        <month>{month}</month>\n"
            f"        <day>{day}</day>\n"
            "      </posted_date>\n"
            f"{item_number_block}"
            f"{abstract_block}"
            "      <doi_data>\n"
            f"        <doi>{xml_escape(doi_val)}</doi>\n"
            f"        <resource>{xml_escape(target_url)}</resource>\n"
            "      </doi_data>\n"
            "    </posted_content>\n"
            "  </body>\n"
            "</doi_batch>\n"
        )
        return xml


class CrossrefReceiptParser:
    """Pure parser validating Crossref receipt responses."""

    @classmethod
    def parse(cls, raw: str) -> CrossrefReceipt:
        """Parse XML receipt returned by Crossref or the test stub.

        Guarantees that a receipt is marked invalid if either <cr-dep-id>
        or <doi> is missing or empty.
        """
        if not raw or not raw.strip():
            return CrossrefReceipt(
                is_valid=False,
                error="Empty response from Crossref",
                raw=raw,
            )

        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            return CrossrefReceipt(
                is_valid=False,
                error=f"Malformed receipt XML: {exc}",
                raw=raw,
            )

        # Search for tags regardless of namespace
        dep_id_elem = root.find(".//cr-dep-id")
        if dep_id_elem is None:
            dep_id_elem = root.find(".//batch_id")
        doi_elem = root.find(".//doi")
        status_elem = root.find(".//status")

        dep_id = (dep_id_elem.text or "").strip() if dep_id_elem is not None else ""
        doi = (doi_elem.text or "").strip() if doi_elem is not None else ""
        status = (
            (status_elem.text or "pending").strip()
            if status_elem is not None
            else "pending"
        )

        if not dep_id:
            match = _CR_DEP_PATTERN.search(raw)
            if match:
                dep_id = match.group(0)

        # Invariant: A valid deposit receipt MUST contain both deposit_id and doi
        if not dep_id:
            return CrossrefReceipt(
                is_valid=False,
                error="Malformed receipt: missing <cr-dep-id>",
                raw=raw,
            )

        if not doi:
            return CrossrefReceipt(
                deposit_id=dep_id,
                is_valid=False,
                error="Malformed receipt: missing <doi> element",
                raw=raw,
            )

        return CrossrefReceipt(
            deposit_id=dep_id,
            doi=doi,
            status=status,
            is_valid=True,
            raw=raw,
        )


class HttpCrossrefClient(CrossrefClientProtocol):
    """Concrete HTTP client communicating with Crossref deposit API."""

    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout_seconds

    def deposit(self, xml_payload: str) -> CrossrefReceipt:
        """Submit XML deposit to Crossref. Returns CrossrefReceipt."""
        url = f"{self._base_url}/servlet/deposit"
        data = xml_payload.encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/xml; charset=utf-8")

        if self._username and self._password:
            import base64

            auth = base64.b64encode(
                f"{self._username}:{self._password}".encode()
            ).decode()
            req.add_header("Authorization", f"Basic {auth}")

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                return CrossrefReceiptParser.parse(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return CrossrefReceipt(
                is_valid=False,
                error=f"HTTP {exc.code}: {body}",
                raw=body,
            )
        except Exception as exc:
            return CrossrefReceipt(
                is_valid=False,
                error=f"Connection failure: {exc}",
            )

    def get_deposit_status(self, deposit_id: str) -> CrossrefReceipt:
        """Poll the status of a previously submitted deposit."""
        url = f"{self._base_url}/deposits/{deposit_id}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                if body.strip().startswith("{"):
                    import json

                    data = json.loads(body)
                    return CrossrefReceipt(
                        deposit_id=deposit_id,
                        doi=data.get("doi", ""),
                        status=data.get("status", "pending"),
                        is_valid=True,
                        raw=body,
                    )
                return CrossrefReceiptParser.parse(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return CrossrefReceipt(
                deposit_id=deposit_id,
                is_valid=False,
                error=f"HTTP {exc.code}: {body}",
                raw=body,
            )
        except Exception as exc:
            return CrossrefReceipt(
                deposit_id=deposit_id,
                is_valid=False,
                error=f"Connection failure: {exc}",
            )
