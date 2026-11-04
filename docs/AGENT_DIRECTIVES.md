# Agent Directives & Developer Guide

## Architecture Overview

`imi-pipeline` orchestrates media syndication across external publishing outlets using Temporal sagas and Behavioral-Driven Development (BDD) contracts.

### Core Outlets
- **Observatory Magazine** (`observatory.wiki` / MediaWiki)
- **IMI WordPress** (`independentmediainstitute.org` / CPT `imi_registry`)
- **Salesforce / Pardot** (Lead distribution & email alerts)
- **Crossref DOI Minting** (Scholarly DOI prefix `10.67767`, Member 57537)

---

## Testing & CI Architecture

The repository enforces outside-in testing across 5 formal gates:

```
Gate 1: Lint (Ruff check & format)
  ├── Gate 2: BDD Contracts (Behave --tags ~@integration) [0.3s, no Docker]
  └── Gate 3: Unit Tests (Pytest -m "not integration") [3s, 233 passing]
        └── Gate 5: DOI Harness (WP 6.4 + MariaDB + Crossref Stub) [E2E Docker]
              └── Summary Gate: ci-pass
```

### Running Tests Locally

#### 1. Quick Quality Check (No Docker Required)
```bash
uv sync --all-extras
uv run ruff check src/ tests/ features/
uv run ruff format --check src/ tests/ features/
uv run behave features/ --tags ~@integration --no-capture
uv run pytest tests/unit -v --tb=short
```

#### 2. DOI Preprint Test Harness (Docker Stack)
The DOI harness is 100% self-contained in `testdata/`. It requires Docker and validates:
- Search engine safety: pending DOIs omit `<meta name="citation_doi">` to prevent 404 indexing leaks.
- DOI activation: successful Crossref minting switches status to `active` and renders citation tags.
- Immutable versions: version increments update metadata without fracturing the base DOI.
- Structured data: Schema.org `ScholarlyArticle` JSON-LD parity.
- Retraction tombstones: retracted papers tombstone DOI and notice without deleting the record.
- Crossref HTTP stub: validates XML deposits, receipt polling, and malformed receipt error recovery.

```bash
make doi-up     # Boot MariaDB 10.11, WP 6.4, and Crossref Stub; install WP via setup_wp.py
make doi-test   # Run all 7 scenarios (68 steps) in features/doi_preprint_lifecycle.feature
make doi-down   # Cleanly stop containers and prune test volumes (-v)
```

---

## Agent Invariants & Hard Rules

When modifying or extending this pipeline, all agents and contributors must observe these invariants:

1. **Protocol Decoupling (Logic/IO Separation):**
   - Outlets interact with external services strictly via protocols defined in `src/phosphene/imi/protocols.py`.
   - Never import direct network clients inside domain activities. Use Fakes in unit tests.
2. **Deterministic BDD Contracts:**
   - Any new business requirement begins with a Gherkin feature file in `features/`.
   - Pure contract features must run without live network dependencies or long timeouts.
   - Any scenario requiring a live container stack must be annotated `@integration`.
3. **No 404 Leaks (DOI Safety):**
   - A preprint in `PENDING` state **must never emit** `<meta name="citation_doi">`.
   - Google Scholar and scrapers must only receive the citation tag once Crossref has returned an active deposit.
4. **Clean Docker Teardown:**
   - When running Docker pipelines, always guarantee teardown using `make doi-down` or `down -v`.
   - Do not leave dangling containers, networks, or host ports bound on developer machines.
5. **Linting & Code Formatting:**
   - Run `uv run ruff check --fix src/ tests/ features/` and `uv run ruff format src/ tests/ features/` prior to every commit.

6. **The PublicationWork Discriminated Union Meta-Model:**
   - All publication works must be modeled as an algebraic sum type (`PublicationWork = ArticleDraft | PreprintWork`).
   - Never pass raw metadata dictionaries or untyped property bags across pipeline boundaries.
   - Never add scholarly registry fields to `ArticleDraft` as hollow optional fields.
   - Use explicit promotion (`promote_to_preprint`) to elevate an editorial draft into an immutable scholarly record.
   - Use unidirectional projections (`PreprintWork.to_article_view()`) to project scholarly works into the editorial wiki interface.
   - See [docs/META_MODEL_PUBLICATION_WORK.md](META_MODEL_PUBLICATION_WORK.md) for full architectural rationale.

7. **Separation of Data Manipulation from Text Rendering:**
   - Pure domain models, resolvers, and wire adapters MUST NOT assemble raw HTML strings, wikitext templates, or manual CSV concatenations.
   - Domain adapters must emit typed intermediate representations (e.g. `list[MetaTag]`, `Mapping[str, str]`).
   - All string formatting, HTML escaping, wikitext templating, delimiter joining, and regex parsing must reside in domain-agnostic `phosphene.utils` (Python) and `Phosphene\Utils` (PHP) submodules.
   - All regular expressions must be precompiled (`re.compile`) at module initialization.
   - See [docs/SEPARATION_DATA_MANIPULATION_TEXT_RENDERING.md](SEPARATION_DATA_MANIPULATION_TEXT_RENDERING.md) for full architectural rationale.
