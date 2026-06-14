# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Tendril-Graph has M0–M4 scaffolding committed (all 7 plugin ABCs, Kùzu store, VCS/CI/CD connectors, attribution engine, extractors, reverse index, resolver, BFS traversal). All 38 tests pass. Read this file every session before touching anything.

## What Tendril-Graph is

Tendril-Graph reconstructs the **cross-repo dependency graph** of a multi-repo estate from source, CI/CD configuration, and (optionally) runtime telemetry, and serves it to coding agents. Canonical docs, in priority order:

- **`PRD.md`** — product requirements (the what/why).
- **`SPEC.md`** — technical spec (the how). The provider plugin contract is `SPEC.md §4`.
- **`docs/architecture.md`** — the canonical Mermaid architecture diagram (committed as source, FR-20).
- **`prompt.md`** — the one-shot handoff for producing/improving the implementation plan. If you're being asked to plan or critique the spec, follow that.
- **`archive-context/`** — five detailed prior planning sessions (CI/CD attribution, value acquisition, runtime telemetry, deep integration analysis, full PRD/spec review). Consult these for design rationale that is not repeated in the docs above.

When `PRD.md`/`SPEC.md` and code disagree, the docs are the source of truth — update code to match, or flag the doc as wrong; never silently diverge.

## Invariants — do not violate these (they are the design)

1. **Plugin-first.** VCS, CI/CD, Extractor, Telemetry, and GraphStore are providers behind the versioned contract (`SPEC.md §4`). **Adding or changing a provider must not require core changes.** If you find yourself editing core to add a platform, stop — extend the contract instead, and bump its semver.
2. **The projection join.** Edges come from matching a *consumer projection* ("I call X") to a *provider projection* ("I am reachable as Y"), per environment, with confidence + evidence. Never reduce this to repo-name matching — repo name, URL path, and deploy host routinely differ.
3. **Index globally, traverse from the anchor.** Provider-identity indexing spans the whole configured scope; consumer traversal is anchor-bounded. "Just follow from the anchor" cannot close the loop and is a bug.
4. **CI/CD is per-repo.** Attribution (`SPEC.md §7`) runs *before* resolution and routes each token to the correct store. Build owner and deploy owner can differ and chain (build in Actions, deploy via Octopus) — handle the handoff.
5. **Capability detection + graceful degradation.** Never assume a feature is enabled — not telemetry deploy-tracking, not readable variable stores, not anything. Probe, then degrade to flagged/lower-confidence output. **A missing capability must never fail the run.**
6. **Provenance + confidence on every edge.** Tag each edge `declared` / `injected` / `observed` and `high` / `medium` / `low`. These are part of the query contract.
7. **Never fabricate.** Secrets are masked in UI, API, and logs alike — you cannot recover them, so don't pretend to. Emit `unresolved-secret` / `unresolved-no-source` and let telemetry or a human fill the gap. Same for ambiguous identity matches: emit candidates, never auto-pick.
8. **Read-only and secret-redacting.** No write paths to any provider, ever. Redact secret-typed values **before persistence** — store "sensitive, present," never the value.
9. **LLM judgment is grounded, never authoritative.** The hard decisions (what a repo reaches, whether a reference matches, what to evaluate next) may be LLM-driven — but every proposal must be **grounded** against the reverse index/connectors before it's trusted; ungrounded → flagged low-confidence. The LLM proposes; grounding validates; it never writes an unverified edge or value. Redact before any model call; cache calls (temp 0) for reproducibility; model/endpoint is **BYOK and configurable, incl. self-hosted**; a deterministic **structured mode (no LLM) must stay available**.
10. **Resolve at the deployed ref, not `main`.** For each environment, read config from the exact SHA/branch actually deployed (from the deploy plane — Octopus), and record that ref on every edge. A graph built from the default branch is wrong wherever an environment runs an older ref.
11. **Communicate accuracy and uncertainty.** Every answer surfaces confidence, provenance, the deployed ref, and an explicit unknowns set. A consumer must distinguish "no dependency" from "could not determine." Favor recall; never imply completeness.
12. **v0 is seamed for expansion.** Implement all seven provider interfaces as real contracts in v0 with minimal bodies, so dataflow analysis and LLM judgment slot in behind existing seams later. Tech debt that would force a later core rebuild is a defect, not a v0 shortcut.

## How to add a provider (the golden path)

1. Implement the relevant interface from `SPEC.md §4` (`VCSProvider` | `CICDProvider` | `ExtractorPlugin` | `TelemetryProvider` | `GraphStore`).
2. Declare static capabilities and (for telemetry) implement `probe()`.
3. Add a `tendril-plugin.toml` manifest (`id`, `family`, `contract_version`, capabilities).
4. **Pass the conformance suite** against recorded fixtures — it is the executable definition of the contract and the gate for being "supported."
5. Do not touch core. If you must, the contract is wrong — fix the contract (with a semver bump and deprecation note), not a one-off.

## Working conventions

- **Reference language / ABI:** *TBD — set this on first scaffolding and keep it consistent across core, the conformance suite, and the first reference providers.* (`SPEC.md §17.8` open question.)
- **Graph store default:** prefer embedded **Kùzu** unless concurrency demands Neo4j; both behind the `GraphStore` plugin.
- **Reproducibility:** where LLM judgment is used, run models at temperature 0 and cache/record decisions so re-runs reproduce; a deterministic **structured mode (no LLM)** must remain available. Regardless of mode, output ordering is deterministic — sort nodes/edges deterministically, and ground every edge.
- **Evidence is mandatory:** every edge carries an `evidence[]` with concrete locators (`file:line`, `store:scope:key`, `run-id`). An edge with no evidence is a bug.
- **Fixtures over live calls in tests:** record provider responses; the first milestone must run against public/sample fixtures with no private credentials.

## Build / test / run

```bash
# install (editable — required for `python -m tendril` to work from source):
python -m venv .venv && .venv/bin/pip install -e ".[dev]"

# run all tests (M0 acceptance + M4 end-to-end, no live API calls):
.venv/bin/python -m pytest tests/

# run a single test file:
.venv/bin/python -m pytest tests/test_end_to_end.py -v

# run the CLI:
.venv/bin/tendril --help
.venv/bin/tendril providers list
```

**Package layout note:** All implementation packages (`cli/`, `core/`, `models/`, etc.) live at the project root as flat top-level packages. `tendril/` is a thin shim that provides `python -m tendril` and the console script. `pip install -e .` installs both. `store/schema.py` holds the Kùzu DDL separately from the adapter.

## First milestone (if you're starting the build)

Build the **real v0 vertical slice** end-to-end before breadth: an **ASP.NET WebForms (VB + C#) + Angular** solution, **built in TeamCity, deployed via Octopus, stored in Bitbucket, with associated repos across both Bitbucket and GitHub.** Prove one real `DEPENDS_ON` edge: Octopus deployment → **deployed SHA** → read config at that ref → TeamCity VCS-root attribution → convention-based resolution (observe the effective value before re-emulating scoping) → one grounded edge with evidence, confidence, and explicit uncertainty. Stand up all seven provider interfaces as real contracts in this phase (thin bodies) so dataflow/LLM are additive later. Then widen along the contract.  (reverse index/resolver → attribution → acquisition ladder + Octopus → remaining connectors → telemetry). See `prompt.md` and `PRD.md §10`.

## Things not to do

- Don't hardcode a platform, language, or environment name into core.
- Don't assume any capability is present; don't fail when one is absent.
- Don't invent edge values or pick among ambiguous matches silently.
- Don't let an LLM proposal become an edge without grounding it against the index/connectors.
- Don't hardcode a model vendor or endpoint; don't remove the deterministic structured mode; don't send unredacted/secret content to a model.
- Don't add write/mutation calls to any provider.
- Don't persist secret values, or echo them into logs or the graph.
- Don't reduce the projection join to name-matching, or the global index to an anchor-only walk.
