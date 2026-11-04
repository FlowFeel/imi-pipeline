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
Gate 1: Lint & Syntax (Ruff check/format & PHP -l) [< 10s]
  ├── Gate 2: BDD Contracts (Behave --tags ~@integration) [< 15s]
  └── Gate 3: Pure Unit Tests (Pytest tests/unit) [T0 in-memory]
        ├── Gate 4: Wire-Level Integration (Pytest tests/integration) [T2 wire mocks]
        └── Gate 5: DOI Harness (WP 6.4 + MariaDB + Crossref Stub) [E2E Docker]
              └── Summary Gate: ci-pass (Strict: all 5 gates required, 0 continue-on-error)
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

8. **Pull Request Discipline & CI Gate Invariants:**
   - Every change must be submitted via a Pull Request using `.github/pull_request_template.md`.
   - Direct pushes to `main` without a passing CI run are prohibited.
   - All commits must follow the Conventional Commits format (`feat`, `fix`, `refactor`, `docs`, `test`, `style`).
   - Every PR must verify the 5 formal CI gates:
     1. **Lint & Syntax:** `ruff check`, `ruff format --check`, and PHP syntax (`php -l`).
     2. **Behavioral Proof:** `behave features/ --tags ~@integration`.
     3. **Pure Unit:** `pytest tests/unit` and pure PHP tests with zero Docker/network.
     4. **Docker Integration / DOI Harness:** Full stack E2E validation with clean teardown.
     5. **Summary Gate:** `ci-pass` status check required for branch merge.
   - In-repo dependencies (`lib/imi_wordpress`, `lib/temporal`) must remain hermetic and workspace-resolved to ensure identical local and CI execution.
   - See [docs/PR_DISCIPLINE_AND_CI.md](PR_DISCIPLINE_AND_CI.md) for full branch protection and review guidelines.
