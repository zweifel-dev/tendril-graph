# Tendril — Product Requirements Document

*An open-source tool that reconstructs the cross-repo dependency graph of a multi-repo estate — the wiring that connects micro-UIs, BFFs, and services through configuration and CI/CD — and serves it to coding agents and humans.*

**Status:** Draft v1.0 (consolidated) · **Companion:** `SPEC.md` (technical), `prompt.md` (Claude Code handoff) · **License intent:** OSS (Apache-2.0 recommended)

> **Project name — `Tendril`.** A tendril is the slender thread a plant uses to attach itself to whatever it grows against; the tool traces the tendrils that attach one repo to another. Working name — verify npm / PyPI / crates / GitHub-org / domain availability before public launch. Shortlist alternatives if it collides: *Skein, Ariadne, Throughline*.

---

## The one-paragraph version

Given a single **anchor repo**, Tendril reconstructs the full repo-to-repo dependency graph across an estate of micro-UIs and backends-for-frontends that are wired together through configuration injected at build/deploy time. It works **statically** — reading source, build/deploy descriptors, and CI/CD variable stores across pluggable VCS and CI/CD providers — and optionally **cross-validates** against runtime telemetry. The core mechanism: every service has a **consumer projection** (the URLs, service names, queues it references) and a **provider projection** (the identities it claims when it deploys, per environment); an edge exists when one service's consumer reference matches another's provider identity, scoped to an environment, carried with confidence and evidence. Everything platform-, language-, and vendor-specific is a **plugin behind a stable contract**, so the tool is general-purpose and community-extensible. Intra-repo structure is delegated to existing tools; Tendril owns the inter-repo, per-environment layer and exposes it to coding agents (e.g. as the backbone for `find_relevant_repos()`).

---

# Part I — Product Requirements

## 0. Design stance: general-purpose & open-source

Tendril is built for **any organization**, not one estate. Everything platform-, language-, or vendor-specific is a **reference implementation behind a plugin interface**, never a baked-in assumption:

- **VCS, CI/CD, telemetry, and graph-store are providers behind versioned interfaces.** Reference connectors ship in-tree; adding a provider is a plugin, not a core change.
- **Language/framework extractors are plugins.** .NET, JS/TS, Java, Python, Go, IaC, and view-layer composition are equal citizens, each contributable.
- **Capability detection and graceful degradation are first-class.** The tool probes what a given org actually runs (which stores are readable, which telemetry is populated) and adapts; it never assumes a feature is enabled.
- **Scope and defaults are configuration.** Orgs/workspaces to index, providers to enable, environments to track — all config. Nothing is hardcoded to a company, scale, or stack.

Every concrete example in this document and in `SPEC.md` is illustrative of the *mechanism*, generalizable to any equivalent stack.

## 1. Assumptions & dependencies

- **A1 — Scoped read access is granted to the orgs/workspaces to be indexed.** Provider-identity indexing must be global across the configured scope (you cannot know in advance which org owns the repo serving a given URL), so the operator grants read access to every org/workspace they want covered, not just the anchor's.
- **A2 — One read-only credential per enabled provider.** Each enabled VCS, CI/CD, and telemetry provider needs a least-privilege, read-only credential, brokered centrally and rotated. (Reference providers: GitHub, Bitbucket, CircleCI, Octopus, TeamCity, GitHub Actions, Bitbucket Pipelines, Datadog — see `SPEC.md` for per-provider detail.)
- **A3 — Source of truth is declarative.** Wiring is discoverable from source + build/deploy descriptors + CI/CD variable stores. Dependencies that exist only at runtime are out of static reach and are flagged, not invented; optional telemetry can recover them.

## 2. Problem & context

A product line spans many repositories — micro front-ends, BFF APIs, shared services, jobs — wired together not in code but in **configuration**: base URLs, service names, queue names, connection strings, **injected at build/deploy time** by the CI/CD platform, differently per environment. No single artifact states "repo A depends on repo B in production"; the dependency is smeared across source, repo build/deploy descriptors, the CI/CD variable store, and the provider's own deploy config. Today that knowledge lives in senior engineers' heads — expensive for incident response and onboarding, and a hard blocker for coding agents that cannot reason about blast radius or assemble the right repos as context. Tendril is the missing substrate.

## 3. Goals

- **G1 — Closed-loop graph from an anchor.** From one anchor repo, produce a complete, traversable graph of reachable repos/services.
- **G2 — Per-environment edges.** Every edge is environment-scoped, because config injection makes the same code path resolve differently per environment.
- **G3 — Evidence and confidence on every edge.** No bare assertions; each edge carries provenance and a calibrated confidence, so agents know how far to trust it.
- **G4 — Provider-pluggable across heterogeneous estates.** First-class support for multiple VCS and CI/CD systems, and optional telemetry, all behind stable contracts.
- **G5 — Agent-consumable.** Expose the graph through agent-facing operations (impact analysis, relevant-repo retrieval, dependency paths, env diffs) and an MCP server.
- **G6 — Composable with intra-repo tooling.** Treat the repo as a node and hand off to intra-repo graph tools (e.g. RepoWise/CodeGraph) via a clean boundary.
- **G7 — Community-extensible.** A documented, versioned plugin contract and developer guide so third parties add providers/extractors without touching core.

## 4. Non-goals

- **NG1 — Static reconstruction is primary; telemetry is optional enrichment.** The graph must function with no telemetry; runtime observability is layered on as cross-validation only.
- **NG2 — Not intra-repo code structure.** Symbol/call graphs are delegated to intra-repo tools.
- **NG3 — Not a CMDB.** Overlaps a service catalog but is not the system of record for ownership/on-call/SLAs.
- **NG4 — Not auto-remediation.** Informs change; does not make changes.
- **NG5 — Not a perfect resolver.** Will not fully emulate every templating/scoping engine or resolve every dynamic endpoint. Unresolved/ambiguous references are flagged, not hidden.

## 5. Users & primary use cases

**Primary: coding agents.** (1) Blast-radius/impact analysis on a contract change. (2) Context assembly — return the minimal connected subgraph for a task (the `find_relevant_repos()` feed). (3) Dependency path between two services. (4) Environment diff ("works in stage, not prod").
**Secondary: humans.** (5) Incident response — trace upstream/downstream per env. (6) Onboarding & architecture review.

## 6. Functional requirements

**Core graph**
- **FR-1** Accept an anchor repo and produce the reachable dependency graph.
- **FR-2** Discover outbound **consumer references** (config keys/values, in-code base URLs, connection strings, queue/topic names, artifact deps, view-layer composition).
- **FR-3** Discover **provider identities** per repo per environment (hostnames/URLs, deploy targets, deploy slots, artifact names, queues) from build/deploy + CI/CD config.
- **FR-4** Build a **global reverse index** (provider identity → owning repo/deployable) across the configured scope.
- **FR-5** **Resolve** each reference against the index, per environment, to a confidence-scored edge with evidence.
- **FR-6** **Evaluate config injection** — resolve placeholders against CI/CD variable stores honoring environment scoping; flag the unresolvable.
- **FR-7** **Traverse** breadth-first from the anchor, handling cycles and revisits, per environment.
- **FR-8** **Attribute CI/CD per repo** — discover each repo's own build/deploy providers (which differ per repo and may chain) and route each token to the correct store.
- **FR-9** **Acquire values via a tiered ladder** — static config → store API → preview API → deploy-log harvest → constrained browser fallback → (optional) runtime; prefer reading the platform's already-resolved effective value.
- **FR-10** **Cross-validate against telemetry (optional)** — overlay observed edges, reconcile static∩/−/observed-only, and emit a divergence report.
- **FR-11** Expose **unresolved / low-confidence / ambiguous** references as first-class output for review.
- **FR-12** Provide a **boundary handoff** to intra-repo graph tools.
- **FR-13** **Composition extractor** — extract `iframe`/`script`/`link`/proxy-rewrite references from server-rendered markup and config, with placeholder detection.
- **FR-14** **Multi-identity resolution** — succeed when repo name, URL path, and deploy host all differ, matching on canonical identity classes.

**Consumption**
- **FR-15** Persist the graph in a queryable store and expose agent-facing query operations plus an **MCP server**.
- **FR-16** Support **incremental refresh** on repo push and pipeline/variable change, with per-node staleness.

**Open-source & extensibility (new)**
- **FR-17 — Provider Plugin Contract.** Tendril MUST define **stable, versioned plugin interfaces** for VCS, CI/CD, Extractor, Telemetry, and GraphStore providers, with a normalized IR, capability declaration, registration/discovery, semantic versioning, and a **conformance test suite** every plugin must pass. A third party MUST be able to add a provider without modifying core. (Interfaces specified in `SPEC.md`.)
- **FR-18 — Project identity & branding.** Ship under the project name **Tendril** (pending availability check), with consistent CLI name, package names, and a one-line positioning statement.
- **FR-19 — README.** Ship a root `README.md` covering: what it is and the consumer/provider-projection model in three sentences; quickstart (install → point at an anchor → get a graph); the **provider support matrix** (VCS × CI/CD × telemetry, with capability notes); the architecture diagram (FR-20); the plugin-developer pointer; security/credential posture; and contribution + license.
- **FR-20 — Architecture diagram.** Ship a canonical architecture diagram (committed as source — Mermaid/ASCII/SVG — not a screenshot) showing the three planes (source / build-deploy / runtime), the provider-plugin boundary, the resolution pipeline, and the graph/query/MCP output. Referenced by README and SPEC.
- **FR-21 — OSS project hygiene.** Ship `LICENSE` (Apache-2.0 recommended), `CONTRIBUTING.md`, a **plugin developer guide**, and at least one runnable end-to-end example using only public/sample providers.

## 7. Non-functional requirements

- **NFR-1 — Security / least privilege.** Read-only per-provider credentials from a central broker, short TTL, rotation. Redact secret-typed values; never persist or emit them. Note that several platforms already mask secrets at the API boundary. The multi-provider credential set is a primary risk surface.
- **NFR-2 — Probabilistic, honestly labeled accuracy.** Every edge carries confidence ∈ {high, medium, low}. Optimize for high precision on high-confidence edges and high recall overall with honest labeling — not a single guaranteed-correct graph.
- **NFR-3 — Freshness.** Full-rebuild and incremental SLAs; per-node staleness visible.
- **NFR-4 — Scale.** Typical target: small-to-mid estates (tens to low-hundreds of repos; thousands of nodes; tens of thousands of edges) on an embedded or single-node property graph. Scales to larger estates without architectural change.
- **NFR-5 — Determinism & auditability.** Same inputs → same graph; every edge traces to evidence.
- **NFR-6 — Extensibility.** New provider/extractor is a plugin, not a core rewrite (see FR-17).
- **NFR-7 — Graceful degradation.** Missing capabilities (unreadable store, absent telemetry feature, unattributable repo) degrade visibly to flagged/lower-confidence output; the run never fails wholesale.

## 8. Success metrics

- **Coverage:** ≥ 95% of repos reachable from the anchor discovered/indexed (vs. a golden estate).
- **Resolution rate:** ≥ 85% of references resolved at ≥ medium confidence; rest flagged.
- **Edge precision (high-confidence):** ≥ 0.95 · **Edge recall (all):** ≥ 0.85 vs. golden set.
- **Cross-plane agreement** (with telemetry present): share of high-confidence static edges confirmed by runtime; plus dynamic-catch count (runtime-only edges surfaced).
- **Freshness:** incremental change reflected within target minutes; full rebuild within target hours.
- **Ecosystem:** time-to-add a new provider by a third party (proxy for FR-17 quality).
- **Downstream:** uplift in agent task success / reduction in irrelevant repos loaded when retrieval is graph-backed.

## 9. Risks & mitigations

| Risk | Why it bites | Mitigation |
|---|---|---|
| Credential sprawl across many providers | Large secret surface | Central broker, scoped read-only short-TTL tokens, no secret persistence, read audit |
| Secret leakage into the graph | Stores/configs hold secrets | Type-aware redaction; store only "sensitive, present", never values |
| Resolution ambiguity → wrong edges | Overlapping identities, fuzzy matches | Confidence scoring; ambiguous matches emitted as candidates, never auto-promoted |
| Config-templating complexity | Each platform differs | Per-provider resolver, best-effort + flag; prefer reading the platform's resolved value |
| Drift (config vs. deployed) | Static lags reality | Per-node staleness; optional telemetry cross-check |
| Over-trust by agents | Agents treat low-confidence as fact | Confidence in the query contract; agents can filter |
| Plugin-contract churn | Breaking third-party plugins | Semver the contract, conformance suite, deprecation policy |

## 10. Phased roadmap

- **Phase 0 — Extraction spike.** One VCS + one CI/CD + one extractor, single env, outbound refs only. Prove extraction against real repos.
- **Phase 1 — Closed loop + the cheapest vertical slice.** Reverse index + resolver + BFS with cycles. Land **GitHub + GitHub Actions** first (intrinsic; GitHub Environments give readable per-env variables): repo → workflow → environment variable → resolved edge, end to end.
- **Phase 1.5 — CI/CD attribution.** Per-repo provider discovery + store routing (prerequisite for correct per-env resolution).
- **Phase 2 — Environments + acquisition ladder.** Octopus (env scoping) + variable resolution + preview/deploy-log rungs.
- **Phase 3 — Full provider matrix.** Bitbucket, TeamCity, CircleCI, Bitbucket Pipelines connectors; complete VCS × CI/CD.
- **Phase 4 — Agent surface + telemetry.** Query layer + MCP server + incremental webhooks + telemetry cross-validation (capability-probed).
- **Phase 5 — Hardening + ecosystem.** Confidence calibration vs. golden set, async/queue edges, secret-redaction audit, and the **published plugin contract + developer guide + conformance suite** for community providers.

*Design honesty: static reconstruction of config-injected, per-environment dependencies is inherently incomplete. Tendril's value is a confidence-scored, evidence-backed, self-labeling approximation that refreshes continuously and degrades visibly — not a guaranteed-complete graph. The architecture is built around that reality.*
