# CLAUDE.md

Guidance for Claude Code (and any AI agent) working in the Tendril repository. Read this first, every session.

## What Tendril is

Tendril reconstructs the **cross-repo dependency graph** of a multi-repo estate from source, CI/CD configuration, and (optionally) runtime telemetry, and serves it to coding agents. Canonical docs, in priority order:

- **`PRD.md`** — product requirements (the what/why).
- **`SPEC.md`** — technical spec (the how). The provider plugin contract is `SPEC.md §4`.
- **`docs/architecture.md`** — the architecture diagram.
- **`prompt.md`** — the one-shot handoff for producing/improving the implementation plan. If you're being asked to plan or critique the spec, follow that.

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

## How to add a provider (the golden path)

1. Implement the relevant interface from `SPEC.md §4` (`VCSProvider` | `CICDProvider` | `ExtractorPlugin` | `TelemetryProvider` | `GraphStore`).
2. Declare static capabilities and (for telemetry) implement `probe()`.
3. Add a `tendril-plugin.toml` manifest (`id`, `family`, `contract_version`, capabilities).
4. **Pass the conformance suite** against recorded fixtures — it is the executable definition of the contract and the gate for being "supported."
5. Do not touch core. If you must, the contract is wrong — fix the contract (with a semver bump and deprecation note), not a one-off.

## Working conventions

- **Reference language / ABI:** *TBD — set this on first scaffolding and keep it consistent across core, the conformance suite, and the first reference providers.* (`SPEC.md §16.8` open question.)
- **Graph store default:** prefer embedded **Kùzu** unless concurrency demands Neo4j; both behind the `GraphStore` plugin.
- **Determinism:** same inputs → same graph. No nondeterministic ordering in output; sort edges/nodes deterministically.
- **Evidence is mandatory:** every edge carries an `evidence[]` with concrete locators (`file:line`, `store:scope:key`, `run-id`). An edge with no evidence is a bug.
- **Fixtures over live calls in tests:** record provider responses; the first milestone must run against public/sample fixtures with no private credentials.

## Build / test / run

> Fill these in as scaffolding lands; keep this section current — it's the first thing an agent looks for.

```
# install:   TBD
# build:     TBD
# test:      TBD  (must include the plugin conformance suite)
# run e2e:   TBD  (the Phase-1 slice: github repo → actions → env var → resolved edge)
```

## First milestone (if you're starting the build)

Build the **cheapest end-to-end vertical slice** before breadth: **GitHub repo → GitHub Actions workflow → GitHub Environment variable → one resolved per-env `DEPENDS_ON` edge → graph → one MCP query.** GitHub Actions is intrinsic and GitHub Environments expose readable per-env variables, so this needs no external CI/CD server. Get one real edge with full evidence working end-to-end, then widen along the contract (reverse index/resolver → attribution → acquisition ladder + Octopus → remaining connectors → telemetry). See `prompt.md` and `PRD.md §10`.

## Things not to do

- Don't hardcode a platform, language, or environment name into core.
- Don't assume any capability is present; don't fail when one is absent.
- Don't invent edge values or pick among ambiguous matches silently.
- Don't add write/mutation calls to any provider.
- Don't persist secret values, or echo them into logs or the graph.
- Don't reduce the projection join to name-matching, or the global index to an anchor-only walk.
