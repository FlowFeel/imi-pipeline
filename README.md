# IMI Pipeline

**Contractual media syndication via Temporal & scholarly preprint DOI registration.**

Observatory article published → article watcher detects it → `SyndicationSagaWorkflow` fans out to outlets (WordPress, Salesforce, MediaWiki, Pardot) → forward-compensation with LIFO rollback on failure → human gate for reviewer approval. In addition, handles the automated scholarly preprint lifecycle with Crossref under prefix `10.67767`.

Lineage: [phosphene/go_bdd_reference](https://github.com/phosphene/go_bdd_reference)

## Architectural Values

**From go_bdd_reference:**
1. **Contract Specification** — Gherkin is the formal requirement. `features/` at root.
2. **Environmental Modeling** — child dependencies inside the test boundary.
3. **Behavioral Proof** — BDD runs before unit tests in CI.
4. **Environmental Determinism** — state isolation, frozen fixtures.

**Native to IMI:**
5. **Enforced Ignorance** — the pipeline must not know service internals by design. Services must expose proper contracted surfaces. Bidirectional obligation.
6. **Null-Omission** — `InvariantStatic`: frozen, strict, no empty strings.
7. **Outlet-Level Idempotency** — the outlet owns dedup, not the caller.
8. **Forward-Compensation, LIFO Rollback** — saga compensates in reverse on failure.
9. **Update, Not Signal** — HumanGate uses Temporal Update for synchronous confirmation.
10. **Acceptance ≠ Smoke** — acceptance tests prove code; smoke tests verify environment.
11. **DOI Tombstoning & 404 Prevention** — preprints with `PENDING` DOIs never emit `<meta name="citation_doi">`; retractions retain their permanent DOI while publishing formal tombstone notices.

---

## Quick Start & Verification

### 1. Developer Quality Suite (Pure Local, No Containers)
Runs linting, contract BDD scenarios, and 233 unit tests in < 5 seconds:

```bash
uv sync --all-extras
make ci          # ruff check → ruff format check → behave (contracts) → pytest
```

Or step-by-step:
```bash
uv run ruff check src/ tests/ features/
uv run behave features/ --tags ~@integration
uv run pytest tests/unit -v --tb=short
```

### 2. End-to-End DOI Preprint Test Harness (Docker Stack)
Validates the complete DOI preprint lifecycle against real WordPress 6.4 (PHP 8.2), MariaDB 10.11, and a dedicated Crossref 5.3.1 mock stub:

```bash
make doi-up      # Stage mu-plugins, boot compose stack, provision WP admin & app password
make doi-test    # Run all 7 scenarios (68 steps) in features/doi_preprint_lifecycle.feature
make doi-down    # Cleanly tear down containers and delete test volumes (-v)
```

The stack operates self-contained under `testdata/`:
- **WordPress:** `http://localhost:18091`
- **Crossref Stub:** `http://localhost:18092` (simulates deposit POSTs, receipt queries, and fault injection)
- **MU-Plugins:** Staged automatically into `testdata/wp-mu-plugins/` for CPT `imi_registry` and citation metadata.

---

## CI/CD Pipeline Gates (GitHub Actions)

Every pull request and push to `main` must pass the formal gates:

```
Gate 1: Lint              ──> ruff check & format check (0 errors across 91 files)
Gate 2: Behavioral Proof  ──> behave features/ --tags ~@integration (24 scenarios, 120 steps, ~0.3s)
Gate 3: Unit Tests        ──> pytest tests/unit (233 passed, ~3.5s)
Gate 5: DOI Harness       ──> Docker Compose (WP + MariaDB + Crossref Stub) (7 scenarios, 68 steps)
CI Summary Gate           ──> ci-pass (asserts all required gates are 100% green)
```

---

## System Topology & Satellite Dependency Graph

```
            ┌───────────────────────────────────────────────┐
            │                  imi-pipeline                 │
            │  SyndicationSagaWorkflow / Outlet Activities   │
            │  Crossref 5.3.1 Generator / Lifecycle Engine   │
            └──────┬────────────┬─────────────┬─────────────┘
                   │            │             │
        Protocol   │   Protocol │    Protocol │
                   ▼            ▼             ▼
          ┌─────────────┐ ┌──────────┐ ┌─────────────┐
          │imi-wordpress│ │salesforce│ │imi-registry │
          │  (Python)   │ │ (Python) │ │ (PHP CPT)   │
          └─────────────┘ └──────────┘ └─────────────┘
                                              ▲
                                              │ Minting / Deposit
                                       ┌──────┴──────┐
                                       │  Crossref   │
                                       │ 10.67767/*  │
                                       └─────────────┘
```

The pipeline depends on satellite packages **strictly through protocols** (`src/phosphene/imi/protocols.py`). In tests, protocol fakes satisfy domain activities without live infrastructure. In integration test suites, self-contained Docker fixtures ensure end-to-end reality.

For full developer invariants and agent working guidelines, see [docs/AGENT_DIRECTIVES.md](docs/AGENT_DIRECTIVES.md).
