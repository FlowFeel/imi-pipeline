# IMI Pipeline

**Contractual media syndication via Temporal.**

Observatory article published → article watcher detects it → SyndicationSagaWorkflow fans out to outlets (WordPress, Salesforce, MediaWiki, Pardot) → forward-compensation with LIFO rollback on failure → human gate for reviewer approval.

Lineage: [phosphene/go_bdd_reference](https://github.com/phosphene/go_bdd_reference)

## Values

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

## Quick Start

```bash
uv sync --all-extras
make ci          # lint → bdd → test
```

## Dependency Graph

```
            ┌─────────────────┐
            │  imi-pipeline    │
            │  Saga / Outlets  │
            │  Gates / Triggers│
            └────────┬─────────┘
                     │
          ┌──────────┼──────────┐
          │ Protocol  │ Protocol  │ Protocol
          ▼          ▼          ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ imi-     │ │ imi-     │ │ imi-     │
   │ wordpress│ │salesforce│ │ registry │
   │ (Python) │ │ (Python) │ │  (PHP)   │
   └──────────┘ └──────────┘ └──────────┘
```

The pipeline depends on satellites **only through protocols**.
In tests, fakes satisfy the protocols. In production, satellite packages provide real clients.
