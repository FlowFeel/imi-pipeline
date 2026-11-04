## Description & Architectural Intent

<!--
Briefly summarize the motivation, business context, and scope of this pull request.
Link to the relevant Issue, OKR (@okr_publish_pipeline, @okr_doi_preprint), or ADR document.
-->

- **Issue / Context:**
- **OKR:**
- **ADR Reference:**

---

## Architectural Seams & Layer Changes

<!-- Check all layers modified by this change -->
- [ ] **Pure Domain Model (`src/phosphene/imi/work.py`, `event.py`, `request.py`):** Closed algebraic types, invariant-static frozen models, total validity.
- [ ] **Domain-Agnostic Utilities (`phosphene.utils`):** Pure text, HTML, or wikitext helpers with zero domain dependencies.
- [ ] **Wire Adapters (`phosphene.imi_wordpress.adapters`):** Intermediate representation (IR) projection separated from serialization.
- [ ] **Triggers & Formatters (`src/phosphene/imi/triggers/`, `formatters.py`):** Pure command parsing, decoupled presentation.
- [ ] **Temporal Sagas & Outlets (`src/phosphene/imi/outlets/`, `workflow.py`):** IO execution, idempotent retry, compensation.
- [ ] **Test Harness & Infrastructure (`features/`, `tests/`, `testdata/`):** Living specifications, Docker test fixtures.

---

## Invariant Verification Checklist

All PRs must satisfy the core engineering invariants before review:

- [ ] **1. Total Invariant Validity:** Every domain entity satisfies all invariants from instantiation. Zero hollow or conditionally initialized fields.
- [ ] **2. Discriminated Union Boundaries:** Editorial drafts (`ArticleDraft`) and scholarly preprints (`PreprintWork`) are partitioned with closed sum types.
- [ ] **3. Text Rendering Separation:** No raw HTML assembly, wikitext template formatting, or manual CSV joining in domain entities or resolvers. Uses `phosphene.utils`.
- [ ] **4. Precompiled Regex Invariant:** All regular expressions are precompiled at module load time (`re.compile`). Zero inline `re.search` / `re.findall`.
- [ ] **5. Scholarly SEO Safety:** Pending DOIs never emit `<meta name="citation_doi">`. Retracted preprints render tombstones without deleting metadata.
- [ ] **6. Hermetic Teardown:** Docker test stacks cleanly terminate on completion or failure (`make doi-down`, `down -v`).

---

## Test Evidence Matrix

| Gate | Scope | Command | Result |
| :--- | :--- | :--- | :--- |
| **Gate 1: Lint & Format** | Ruff check & format check | `uv run ruff check src/ tests/ features/ lib/imi_wordpress/src/ && uv run ruff format --check src/ tests/ features/ lib/imi_wordpress/src/` | |
| **Gate 2: BDD Contract** | Non-integration feature suite | `uv run behave features/ --tags ~@integration --no-capture` | |
| **Gate 3: Pure Unit** | T0 unit tests (no Docker) | `uv run pytest tests/unit -v --tb=short` | |
| **Gate 4: Integration** | Temporal + MediaWiki (Docker) | `uv run pytest tests/integration -v --tb=short` | |
| **Gate 5: DOI Harness** | Scholarly lifecycle E2E stack | `make doi-test` | |

---

## Reviewer Sign-Off Checklist

- [ ] Code strictly observes logic / IO protocol boundaries.
- [ ] No regression in BDD feature living specifications.
- [ ] All CI gates passed green (`ci-pass` status check).
