"""Hermetic Crossref Schema 5.3.1 Simulator Engine.

Provides an axiomatic in-memory simulation of the Crossref deposit and resolution system:
1. Validates Schema 5.3.1 XML constraints (root namespaces, head, depositor, contributors,
   surname requirements, ORCID validity, titles, dates, doi_data).
2. Generates authentic Crossref deposit receipts (or failure batch diagnostics).
3. Maintains DOI registry mapping: DOI -> Target Resource Landing Page URL.
4. Simulates HTTP 302 DOI resolution from registered DOIs to destination pages.
5. Injects controlled failure modes (timeout, malformed receipt, batch rejection).

OKR: @okr_doi_preprint
"""

from __future__ import annotations

import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

NS = "http://www.crossref.org/schema/5.3.1"
NS_MAP = {"cr": NS}

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


@dataclass(frozen=True)
class SimulatorDepositResult:
    """Outcome of a deposit submitted to the simulator engine."""

    status_code: int
    response_body: str
    is_valid: bool
    deposit_id: str = ""
    doi: str = ""
    target_url: str = ""
    error: str | None = None


class CrossrefSimulatorEngine:
    """Pure domain engine simulating the Crossref Schema 5.3.1 service."""

    def __init__(self, allowed_prefix: str = "10.67767") -> None:
        self.allowed_prefix = allowed_prefix.rstrip("/")
        self._lock = threading.Lock()
        self._registry: dict[str, dict[str, Any]] = {}
        self._deposits: dict[str, dict[str, Any]] = {}
        self._scripted: dict[str, str] = {}
        self._seq = 9000

    def reset(self) -> None:
        """Clear all registered DOIs, deposits, and scripted behaviors."""
        with self._lock:
            self._registry.clear()
            self._deposits.clear()
            self._scripted.clear()
            self._seq = 9000

    def script_mode(self, suffix: str, mode: str) -> None:
        """Script a specific response mode for a DOI suffix (e.g. timeout, malformed)."""
        clean_suffix = str(suffix).lstrip("0") or "0"
        with self._lock:
            self._scripted[clean_suffix] = mode

    def resolve_doi(self, doi: str) -> str | None:
        """Resolve a registered DOI to its landing page URL."""
        with self._lock:
            clean_doi = doi.strip()
            if clean_doi.startswith("https://doi.org/"):
                clean_doi = clean_doi.replace("https://doi.org/", "")
            elif clean_doi.startswith("http://doi.org/"):
                clean_doi = clean_doi.replace("http://doi.org/", "")
            rec = self._registry.get(clean_doi)
            return rec.get("resource") if rec else None

    def get_deposit(self, deposit_id: str) -> dict[str, Any] | None:
        """Retrieve deposit record by deposit tracking ID."""
        with self._lock:
            return self._deposits.get(deposit_id)

    def deposit(self, raw_xml: str) -> SimulatorDepositResult:
        """Validate Schema 5.3.1 XML and process deposit registration."""
        with self._lock:
            self._seq += 1
            dep_id = f"cr-dep-{self._seq}"

        # 1. XML Well-formedness
        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError as exc:
            return self._failure(dep_id, f"Malformed XML syntax: {exc}", code=400)

        # 2. Namespace & Version check
        if root.tag != f"{{{NS}}}doi_batch":
            return self._failure(
                dep_id,
                f"Missing or invalid Schema 5.3.1 namespace in root element: {{{NS}}}doi_batch, got '{root.tag}'",
                code=400,
            )
        if root.attrib.get("version") != "5.3.1":
            return self._failure(
                dep_id,
                f"Root version must be 5.3.1, got '{root.attrib.get('version')}'",
                code=400,
            )

        # 3. Head & Depositor validation
        head = root.find("cr:head", NS_MAP)
        if head is None:
            return self._failure(dep_id, "Missing mandatory <head> element", code=400)

        batch_id = head.find("cr:doi_batch_id", NS_MAP)
        if batch_id is None or not (batch_id.text or "").strip():
            return self._failure(dep_id, "Missing mandatory <doi_batch_id>", code=400)

        depositor = head.find("cr:depositor", NS_MAP)
        if depositor is None:
            return self._failure(
                dep_id, "Missing mandatory <depositor> element", code=400
            )
        dep_name = depositor.find("cr:depositor_name", NS_MAP)
        dep_email = depositor.find("cr:email_address", NS_MAP)
        if dep_name is None or not (dep_name.text or "").strip():
            return self._failure(dep_id, "Missing <depositor_name>", code=400)
        if dep_email is None or not (dep_email.text or "").strip():
            return self._failure(dep_id, "Missing <email_address>", code=400)

        # 4. Body & Content validation
        body = root.find("cr:body", NS_MAP)
        if body is None:
            return self._failure(dep_id, "Missing mandatory <body> element", code=400)

        content = body.find("cr:posted_content", NS_MAP)
        if content is None:
            content = body.find("cr:journal_article", NS_MAP)
        if content is None:
            return self._failure(
                dep_id,
                "Missing <posted_content> or <journal_article> in <body>",
                code=400,
            )

        # Contributors
        contributors = content.find("cr:contributors", NS_MAP)
        if contributors is not None:
            persons = contributors.findall("cr:person_name", NS_MAP)
            if not persons:
                return self._failure(
                    dep_id, "Contributors block has no <person_name>", code=400
                )
            if persons[0].attrib.get("sequence") != "first":
                return self._failure(
                    dep_id, "First contributor must have sequence='first'", code=400
                )
            for idx, p in enumerate(persons):
                surname = p.find("cr:surname", NS_MAP)
                if surname is None or not (surname.text or "").strip():
                    return self._failure(
                        dep_id,
                        f"Contributor {idx} missing mandatory <surname>",
                        code=400,
                    )
                orcid = p.find("cr:ORCID", NS_MAP)
                if orcid is not None:
                    orcid_val = (orcid.text or "").strip()
                    if orcid_val in _DUMMY_ORCIDS:
                        return self._failure(
                            dep_id,
                            f"Invalid dummy ORCID submitted: '{orcid_val}'",
                            code=400,
                        )
                    if not _ORCID_RE.match(orcid_val):
                        return self._failure(
                            dep_id, f"Malformed ORCID format: '{orcid_val}'", code=400
                        )

        # Titles
        titles = content.find("cr:titles", NS_MAP)
        if titles is None or titles.find("cr:title", NS_MAP) is None:
            return self._failure(dep_id, "Missing mandatory <titles><title>", code=400)

        # DOI Data
        doi_data = content.find("cr:doi_data", NS_MAP)
        if doi_data is None:
            return self._failure(dep_id, "Missing mandatory <doi_data> block", code=400)
        doi_elem = doi_data.find("cr:doi", NS_MAP)
        resource_elem = doi_data.find("cr:resource", NS_MAP)
        if doi_elem is None or not (doi_elem.text or "").strip():
            return self._failure(dep_id, "Missing mandatory <doi>", code=400)
        if resource_elem is None or not (resource_elem.text or "").strip():
            return self._failure(dep_id, "Missing mandatory <resource> URL", code=400)

        doi_str = doi_elem.text.strip()
        resource_url = resource_elem.text.strip()

        # Prefix authorization check
        if not doi_str.startswith(f"{self.allowed_prefix}/"):
            return self._failure(
                dep_id,
                f"Unauthorized prefix in '{doi_str}'. Allowed prefix: '{self.allowed_prefix}'",
                code=400,
            )

        # Suffix scripted failure check
        suffix = doi_str.split("/")[-1].split(".")[-1]
        clean_suffix = suffix.lstrip("0") or "0"
        with self._lock:
            mode = self._scripted.get(clean_suffix, "success")

        if mode == "timeout":
            return SimulatorDepositResult(
                status_code=500,
                response_body="<error>Upstream Crossref timeout</error>",
                is_valid=False,
                deposit_id=dep_id,
                doi=doi_str,
                error="Simulated timeout",
            )
        if mode == "reject":
            return self._failure(dep_id, "Simulated batch rejection", code=400)

        # Record into registry
        with self._lock:
            self._registry[doi_str] = {
                "deposit_id": dep_id,
                "resource": resource_url,
                "status": "active",
                "registered_at": time.time(),
            }
            self._deposits[dep_id] = {
                "doi": doi_str,
                "resource": resource_url,
                "status": "pending",
                "mode": mode,
                "received_at": time.time(),
            }

        if mode == "malformed":
            # Omit <doi> from receipt to test client receipt validation
            malformed_receipt = (
                f"<deposit_receipt><cr-dep-id>{dep_id}</cr-dep-id></deposit_receipt>"
            )
            return SimulatorDepositResult(
                status_code=201,
                response_body=malformed_receipt,
                is_valid=True,
                deposit_id=dep_id,
                doi=doi_str,
                target_url=resource_url,
            )

        # Standard Success Receipt
        receipt_xml = (
            f"<deposit_receipt>"
            f"<cr-dep-id>{dep_id}</cr-dep-id>"
            f"<doi>{doi_str}</doi>"
            f"<status>pending</status>"
            f"</deposit_receipt>"
        )
        return SimulatorDepositResult(
            status_code=201,
            response_body=receipt_xml,
            is_valid=True,
            deposit_id=dep_id,
            doi=doi_str,
            target_url=resource_url,
        )

    def _failure(
        self, dep_id: str, message: str, code: int = 400
    ) -> SimulatorDepositResult:
        body = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<doi_batch_diagnostic status="completed" xmlns="{NS}">\n'
            f"  <submission_id>{dep_id}</submission_id>\n"
            f"  <batch_data>\n"
            f'    <record_diagnostic status="Failure">\n'
            f"      <msg>{message}</msg>\n"
            f"    </record_diagnostic>\n"
            f"  </batch_data>\n"
            f"</doi_batch_diagnostic>"
        )
        return SimulatorDepositResult(
            status_code=code,
            response_body=body,
            is_valid=False,
            deposit_id=dep_id,
            error=message,
        )
