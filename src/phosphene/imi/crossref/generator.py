"""Pure XML generator for Crossref Schema 5.3.1 deposit batches.

Outputs valid Crossref XML for posted content (preprints) conforming to
http://www.crossref.org/schema/5.3.1.

@dft
- A1 (pure-io-separation): Pure string/XML builder, zero network/IO.
- A2 (determinism): Pure functional generation.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

from phosphene.imi.crossref.models import (
    CROSSREF_SCHEMA_VERSION,
    CROSSREF_XMLNS,
    JATS_XMLNS,
    CrossrefContributor,
    CrossrefDepositBatch,
    CrossrefDepositRecord,
    normalize_orcid,
)


def _escape(val: str) -> str:
    return html.escape(val, quote=True)


def _render_contributor(contributor: CrossrefContributor) -> str:
    lines = [
        f'        <person_name sequence="{contributor.sequence}" contributor_role="{contributor.contributor_role}">'
    ]
    if contributor.given_name:
        lines.append(
            f"          <given_name>{_escape(contributor.given_name)}</given_name>"
        )
    lines.append(f"          <surname>{_escape(contributor.surname)}</surname>")

    if contributor.orcid:
        canon_orcid = normalize_orcid(contributor.orcid)
        lines.append(f"          <ORCID>{_escape(canon_orcid)}</ORCID>")

    if contributor.affiliation:
        lines.append("          <affiliations>")
        lines.append(
            f"            <institution><institution_name>{_escape(contributor.affiliation)}</institution_name></institution>"
        )
        lines.append("          </affiliations>")

    lines.append("        </person_name>")
    return "\n".join(lines)


def _render_record(record: CrossrefDepositRecord) -> str:
    # Date parsing
    posted = record.posted_date or datetime.now(UTC).strftime("%Y-%m-%d")
    parts = posted.split("-")
    year = parts[0]
    month = parts[1] if len(parts) > 1 else "01"
    day = parts[2] if len(parts) > 2 else "01"

    lines = [
        '    <posted_content type="preprint">',
        f"      <group_title>{_escape(record.group_title)}</group_title>",
        "      <contributors>",
        _render_contributor(record.primary_author),
    ]

    for coauthor in record.coauthors:
        lines.append(_render_contributor(coauthor))

    lines.append("      </contributors>")
    lines.append("      <titles>")
    lines.append(f"        <title>{_escape(record.title)}</title>")
    lines.append("      </titles>")
    lines.append("      <posted_date>")
    lines.append(f"        <month>{month}</month>")
    lines.append(f"        <day>{day}</day>")
    lines.append(f"        <year>{year}</year>")
    lines.append("      </posted_date>")

    if record.abstract:
        lines.append(f'      <jats:abstract xmlns:jats="{JATS_XMLNS}">')
        lines.append(f"        <jats:p>{_escape(record.abstract)}</jats:p>")
        lines.append("      </jats:abstract>")

    if record.license_url:
        lines.append(
            '      <program xmlns="http://www.crossref.org/AccessIndicators.xsd">'
        )
        lines.append(f'        <free_to_read start_date="{year}-{month}-{day}" />')
        lines.append(
            f'        <license_ref applies_to="vor" start_date="{year}-{month}-{day}">{_escape(record.license_url)}</license_ref>'
        )
        lines.append("      </program>")

    lines.append("      <doi_data>")
    lines.append(f"        <doi>{_escape(record.doi)}</doi>")
    lines.append(f"        <resource>{_escape(record.resource_url)}</resource>")
    lines.append("      </doi_data>")
    lines.append("    </posted_content>")

    return "\n".join(lines)


def render_crossref_xml(batch: CrossrefDepositBatch) -> str:
    """Render a CrossrefDepositBatch into Crossref Schema 5.3.1 XML string."""
    header = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<doi_batch version="{CROSSREF_SCHEMA_VERSION}" xmlns="{CROSSREF_XMLNS}" '
        f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="{CROSSREF_XMLNS} http://www.crossref.org/schemas/crossref5.3.1.xsd">',
        "  <head>",
        f"    <doi_batch_id>{_escape(batch.batch_id)}</doi_batch_id>",
        f"    <timestamp>{batch.timestamp}</timestamp>",
        "    <depositor>",
        f"      <depositor_name>{_escape(batch.depositor_name)}</depositor_name>",
        f"      <email_address>{_escape(batch.depositor_email)}</email_address>",
        "    </depositor>",
        f"    <registrant>{_escape(batch.registrant)}</registrant>",
        "  </head>",
        "  <body>",
    ]

    records_xml = [_render_record(rec) for rec in batch.records]

    footer = [
        "  </body>",
        "</doi_batch>",
    ]

    return "\n".join(header + records_xml + footer)
