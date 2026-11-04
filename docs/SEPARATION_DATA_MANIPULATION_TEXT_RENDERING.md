# ADR: Separation of Data Manipulation from Text Rendering

**Status:** Accepted  
**Date:** 2026-11-04  
**Scope:** `imi-pipeline`, `imi-wordpress`, `observatory-magazine-v2`  
**Directives:** Section 7 of `AGENT_DIRECTIVES.md`

---

## 1. Context & Architectural Problem

Data models, wire adapters, and integration workflows across the publishing pipeline frequently interleaved **data manipulation** (entity validation, business logic, semantic projection, state calculation) with **text rendering** (raw HTML string interpolation, wikitext syntax assembly, CSV formatting) and **text parsing** (uncompiled ad-hoc regex searches, hand-rolled slug derivation).

### Diagnosed Failure Modes

1. **Presentation Syntax Leakage into Pure Domain Contracts**:
   - `PreprintPayloadAdapter.to_citation_meta()` directly formatted raw `<meta ...>` tags via string concatenation instead of projecting typed intermediate structures.
   - `PreprintWork.to_article_view()` injected raw wikitext `{{Preprint}}\n\n` into the article body string inside the domain model.
2. **Duplicated, Inconsistent String Derivations**:
   - Slugification was implemented in three conflicting ways: regex-based in `work.py`, `.replace(" ", "-")` in `event.py`, and dictionary fallback in `fakes.py`.
3. **Regex Compilation & Re-execution Hotpaths**:
   - Regular expressions in triggers (`TelegramTrigger`) and test scrapers (`doi_steps.py`, `metadata_extractor.py`) were evaluated via uncompiled module-level calls (`re.search`, `re.findall`), re-compiling bytecode on every invocation.
4. **Brittle Test Expectations**:
   - Unit tests were forced to assert on rigid HTML/wikitext string serialization rather than verifiable, typed intermediate representations.

---

## 2. Architectural Decision

We enforce the **absolute separation of data manipulation from text rendering and parsing** by establishing domain-agnostic utility submodules:

1. **Pure Domain & Adapter Responsibility (Data Manipulation)**:
   - Domain entities and projection adapters manipulate typed structures only.
   - Projections that emit presentation elements MUST yield typed intermediate representations (e.g. `list[MetaTag]`, `Mapping[str, str]`).
   - Adapters MUST NOT assemble raw HTML strings, wikitext markup, or manual CSV concatenations.
2. **Domain-Agnostic Utility Responsibility (Text Rendering & Parsing)**:
   - All string assembly (HTML escaping, tag construction, wikitext templating) and regex parsing reside in `phosphene.utils` (Python) and `Phosphene\Utils` (PHP).
   - These utilities contain **zero domain dependencies**. They can be unit-tested and fuzz-tested at T0 in total isolation.
   - All regular expressions MUST be precompiled at module load time (`re.compile`).

---

## 3. The Typed Intermediate Representations (IR)

### A. MetaTag (HTML Presentation IR)
```python
class MetaTag(InvariantStatic):
    name: str
    content: str
```
Adapters project domain entities to `list[MetaTag]`. The renderer (`render_meta_tags`) handles attribute escaping, quotes, and newlines.

### B. Standardized Delimited Strings (Wire IR)
Instead of arbitrary `", ".join(...)`, adapters call `join_delimited(items, delimiter=", ")` which guarantees null-omission (dropping empty, null, or whitespace-only elements).

### C. Slug & Command Invariants
- `slugify(text: str, max_length: int | None = None) -> str`: Normalizes Unicode, removes invalid characters, consolidates hyphens, and handles length caps deterministically.
- `parse_command_line(text: str) -> tuple[str, dict[str, str]]`: Precompiled, deterministic extraction of URLs and `--key=value` flags.

---

## 4. Verification & Testing Invariants

1. **T0 Unit Isolation**: Every function in `phosphene.utils` is tested against hostile inputs: empty strings, null bytes, special characters (`<`, `>`, `"`, `'`, `&`, `|`, `{`, `}`), trailing whitespace, and non-ASCII Unicode.
2. **Zero Regressions**: All existing BDD scenarios and unit tests in `imi-wordpress` (271+ tests) and `imi-pipeline` (318+ tests) must pass unconditionally.
