# Tendril-Graph — Product Requirements Document

*An open-source tool that reconstructs the cross-repo dependency graph of a multi-repo estate — the wiring that connects micro-UIs, BFFs, and services through configuration and CI/CD — and serves it to coding agents and humans.*

**Status:** Draft v1.0 (consolidated) · **Companion:** `SPEC.md` (technical), `prompt.md` (Claude Code handoff) · **License intent:** OSS (Apache-2.0 recommended)

> **Project name — `Tendril`.** A Tendril-Graph is the slender thread a plant uses to attach itself to whatever it grows against; the tool traces the tendrils that attach one repo to another. Working name — verify npm / PyPI / crates / GitHub-org / domain availability before public launch. Shortlist alternatives if it collides: *Skein, Ariadne, Throughline*.

---

## The one-paragraph version

Given a single **anchor repo**, Tendril-Graph reconstructs the full repo-to-repo dependency graph across an estate of micro-UIs and backends-for-frontends that are wired together through configuration injected at build/deploy time. It works **statically** — reading source, build/deploy descriptors, and CI/CD variable stores across pluggable VCS and CI/CD providers — and optionally **cross-validates** against runtime telemetry. The core mechanism: every service has a **consumer projection** (the URLs, service names, queues it references) and a **provider projection** (the identities it claims when it deploys, per environment); an edge exists when one service's consumer reference matches another's provider identity, scoped to an environment, carried with confidence and evidence. Everything platform-, language-, and vendor-specific is a **plugin behind a stable contract**, so the tool is general-purpose and community-extensible. Intra-repo structure is delegated to existing tools; Tendril-Graph owns the inter-repo, per-environment layer and exposes it to coding agents (e.g. as the backbone for `find_relevant_repos()`).

---

# Part I — Product Requirements

## 0. Design stance: general-purpose & open-source

Tendril-Graph is built for **any organization**, not one estate. Everything platform-, language-, or vendor-specific is a **reference implementation behind a plugin interface**, never a baked-in assumption:

- **VCS, CI/CD, telemetry, and graph-store are providers behind versioned interfaces.** Reference connectors ship in-tree; adding a provider is a plugin, not a core change.
- **Language/framework extractors are plugins.** .NET, JS/TS, Java, Python, Go, IaC, and view-layer composition are equal citizens, each contributable.
- **Capability detection and graceful degradation are first-class.** The tool probes what a given org actually runs (which stores are readable, which telemetry is populated) and adapts; it never assumes a feature is enabled.
- **Scope and defaults are configuration.** Orgs/workspaces to index, providers to enable, environments to track — all config. Nothing is hardcoded to a company, scale, or stack.

Every concrete example in this document and in `SPEC.md` is illustrative of the *mechanism*, generalizable to any equivalent stack.

## 1. Assumptions & dependencies

- **A1 — Scoped read access is granted to the orgs/workspaces to be indexed.** Provider-identity indexing must be global across the configured scope (you cannot know in advance which org owns the repo serving a given URL), so the operator grants read access to every org/workspace they want covered, not just the anchor's.
- **A2 — One read-only credential per enabled provider.** Each enabled VCS, CI/CD, and telemetry provider needs a least-privilege, read-only credential, brokered centrally and rotated. (Reference providers: GitHub, Bitbucket, CircleCI, Octopus, TeamCity, GitHub Actions, Bitbucket Pipelines, Datadog — see `SPEC.md` for per-provider detail.)
- **A3 — Source of truth is declarative.** Wiring is discoverable from source + build/deploy descriptors + CI/CD variable stores. Dependencies that exist only at runtime are out of static reach and are flagged, not invented; optional telemetry can recover them.
- **A4 — Intra-repo analysis is a pluggable capability, not a hard dependency.** Tendril-Graph needs intra-repo dataflow facts (def-use, value-sets, call graph) to resolve computed values and ground LLM judgment, but does **not** require any specific external tool to be run first. The `IntraRepoProvider` is satisfied by *self-provide* (bundled engine — Roslyn for .NET, Joern for cross-language), *reuse* (adapter consuming CodeGraph / RepoWise / CodeQL output if the org already runs them), or *degrade* (format-parser extraction + grounded LLM at lower confidence). CodeQL is excluded as a bundled default because its engine is not licensed for proprietary code without GitHub Advanced Security.

## 1.1 Key design bets & confidence

The design rests on a set of bets of varying strength. Stated honestly so the build can de-risk the weak ones first. (This is confidence in the *approach*; per-edge confidence is a separate runtime property, NFR-2.)

| Design bet | Confidence | Why |
|---|---|---|
| Static reconstruction from declarative sources covers most config-injected wiring | Medium-High | True for the target problem; misses purely-runtime/dynamic deps (telemetry mitigates) |
| Reverse-index + projection join closes the loop | High | Mechanically sound; the core idea is robust |
| Per-repo CI/CD attribution is discoverable | Medium | Intrinsic signals strong; server-side Octopus without Config-as-Code is weak (may need a mapping table) |
| Per-env token resolution via stores + acquisition ladder | Medium | Scoping emulation is hard; preview/deploy-log rungs mitigate; the secret floor is a real, permanent gap |
| Deterministic dataflow handles backtracking & value-flow within a language | Medium-High | Mature tech (Roslyn/Joern); an approximation with known limits |
| Cross-language / cross-process value stitching | **Low** | No single engine does it; relies on grounded LLM + telemetry; expect lower-confidence edges here |
| Grounded LLM judgment avoids hallucinated edges | Medium | Grounding against the index is a strong guard; residual risk on ungrounded stitching; needs calibration |
| Intra-repo analysis as a pluggable provider (self / reuse / degrade) | Medium-High | Roslyn (.NET, MIT) + Joern (Apache-2.0) cover much; the .NET-on-Joern gap and engine integration are the risks |
| Telemetry as optional enrichment | High | Clearly additive; coverage varies but never required |
| Plugin contract enables community extension | Medium | Depends on getting the interfaces right; conformance suite mitigates; unproven until real third-party providers exist |
| Single-node property graph scales to target estates | High (small-mid) / Medium (large) | Fine for tens-to-low-hundreds of repos; large estates need parallelism and store choice |

**De-risk order:** the two lowest-confidence bets — cross-language/cross-process stitching and per-env resolution's hard cases — should be probed against a real estate early (a spike), because they bound how complete the graph can ever be.

## 2. Problem & context

A product line spans many repositories — micro front-ends, BFF APIs, shared services, jobs — wired together not in code but in **configuration**: base URLs, service names, queue names, connection strings, **injected at build/deploy time** by the CI/CD platform, differently per environment. No single artifact states "repo A depends on repo B in production"; the dependency is smeared across source, repo build/deploy descriptors, the CI/CD variable store, and the provider's own deploy config. Today that knowledge lives in senior engineers' heads — expensive for incident response and onboarding, and a hard blocker for coding agents that cannot reason about blast radius or assemble the right repos as context. Tendril-Graph is the missing substrate.

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
- **FR-17 — Provider Plugin Contract.** Tendril-Graph MUST define **stable, versioned plugin interfaces** for VCS, CI/CD, Extractor, Telemetry, and GraphStore providers, with a normalized IR, capability declaration, registration/discovery, semantic versioning, and a **conformance test suite** every plugin must pass. A third party MUST be able to add a provider without modifying core. (Interfaces specified in `SPEC.md`.)
- **FR-18 — Project identity & branding.** Ship under the project name **Tendril** (pending availability check), with consistent CLI name, package names, and a one-line positioning statement.
- **FR-19 — README.** Ship a root `README.md` covering: what it is and the consumer/provider-projection model in three sentences; the **v0 reference stack** and quickstart (install → point at an anchor → get a graph); the **provider support matrix** (VCS × CI/CD × telemetry, with capability notes); the architecture diagram (FR-20); the plugin-developer pointer; contribution + license. It MUST also document, explicitly and per provider: **(a) exact requirements** to run (runtime, dependencies, supported provider versions); **(b) how to obtain access and keys** — for each of GitHub, Bitbucket, TeamCity, Octopus, and any telemetry provider: what credential/token type, what scopes, the steps to create it, and **where to put it** (config/env/broker); **(c) prerequisites and run-order** — anything that must run prior (e.g. an `IntraRepoProvider`/intra-repo analysis, or enabling Octopus deploy events) and the required access breadth (which orgs/workspaces); and **(d) prior work / provenance** — the design docs and any upstream tools it builds on.
- **FR-20 — Architecture diagram.** Ship a canonical architecture diagram (committed as source — Mermaid/ASCII/SVG — not a screenshot) showing the three planes (source / build-deploy / runtime), the provider-plugin boundary, the resolution pipeline, and the graph/query/MCP output. Referenced by README and SPEC.
- **FR-21 — OSS project hygiene.** Ship `LICENSE` (Apache-2.0 recommended), `CONTRIBUTING.md`, a **plugin developer guide**, and at least one runnable end-to-end example using only public/sample providers.

**Judgment & LLM (grounded, BYOK)**
- **FR-22 — LLM judgment with deterministic grounding.** The construction decisions that require judgment — interpreting a repo to find its outward dependencies, deciding whether a reference matches a provider, and choosing the traversal frontier — MAY be LLM-driven (**hybrid mode is the default**; a deterministic **structured mode** with no LLM MUST remain available). Every LLM proposal MUST be **grounded** against the reverse index/connectors before it is trusted; ungrounded proposals are flagged low-confidence, never silently kept. The LLM proposes; grounding validates; the LLM never writes an unverified edge or value.
- **FR-23 — BYOK, model- and location-agnostic LLM.** LLM access is an `LLMProvider` plugin, **OpenAI-compatible-gateway-first** (LiteLLM / vLLM / Ollama / Azure / Bedrock / frontier), with **per-decision model tiering** and **data-residency routing** (source-reading tasks pinnable to self-hosted/in-VPC endpoints). Credentials are BYOK and brokered. A **redaction hook** MUST run before any model call; calls MUST be cached and recorded for reproducibility and audit.

**Correctness, truth & uncertainty**
- **FR-24 — Resolve at the deployed ref, not the default branch.** For each environment, the graph MUST be reconstructed from the **exact SHA/branch that is actually deployed** to that environment, obtained from the deploy plane (e.g. the Octopus deployment's release → build → VCS ref). Reading config from `HEAD`/`main` is incorrect for any environment running an older ref. The deployed ref is recorded on every edge as evidence.
- **FR-25 — Communicate accuracy and uncertainty in the output.** The query/consumer contract MUST surface, for every answer: confidence, provenance (`declared`/`injected`/`observed`/`llm-judged`), the deployed ref it was computed from, and **what is unknown** — unresolved references, ungrounded candidates, and coverage gaps are first-class output, never hidden. A consumer must be able to distinguish "no dependency" from "we could not determine." Optimize for recall and honest labeling (NFR-2): a missed edge is more dangerous than a flagged unknown.
- **FR-26 — Truth is established and documented through observation where available.** Observed reality — the deployed SHA, deploy events, and (where present) telemetry — is recorded as a **documented truth source** that grounds and corroborates the declarative graph, with provenance. Where observation and declaration disagree, both are kept and the divergence is reported (FR-10). Observation is mandatory for the deployed ref (FR-24) and optional-but-recorded for runtime behavior.
- **FR-27 — v0 is seamed for expansion (no rebuild).** v0 MUST implement the full set of provider interfaces (VCS, CI/CD, Extractor, IntraRepo, Telemetry, GraphStore, LLM) as real contracts with minimal implementations behind them, so that adding dataflow analysis, LLM judgment, and additional providers is **additive, not a rewrite**. v0 is thin but correctly seamed; tech debt that would force a later rebuild of the core is a defect.

## 7. Non-functional requirements

- **NFR-1 — Security / least privilege.** Read-only per-provider credentials from a central broker, short TTL, rotation. Redact secret-typed values; never persist or emit them. Note that several platforms already mask secrets at the API boundary. The multi-provider credential set is a primary risk surface.
- **NFR-2 — Probabilistic, honestly labeled accuracy.** Every edge carries confidence ∈ {very high, high, medium, low, very low}. Optimize for very high precision on very high-confidence edges and very high recall overall with honest labeling — not a single guaranteed-correct graph.
- **NFR-3 — Freshness.** Full-rebuild and incremental SLAs; per-node staleness visible.
- **NFR-4 — Scale.** Typical target: small-to-mid estates (tens to low-hundreds of repos; thousands of nodes; tens of thousands of edges) on an embedded or single-node property graph. Scales to larger estates without architectural change.
- **NFR-5 — Reproducibility, grounding & auditability.** Where LLM judgment is used (hybrid/agentic modes), runs reproduce via temperature-0 + cached, recorded decisions; **every edge is grounded** (verified against the reverse index/connectors) and traces to evidence, including any LLM reasoning trace. A fully deterministic **structured mode** (no LLM) remains available for adopters who require it. Output ordering is deterministic regardless of mode.
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

**v0 reference target:** an **ASP.NET WebForms (VB + C#) solution with Angular pages**, built in **TeamCity**, deployed via **Octopus**, stored in **Bitbucket**, with associated repos across **both Bitbucket and GitHub**. This is deliberately the *real* slice, not the cheapest one — it puts server-side CI/CD (TeamCity VCS roots, Octopus variable scoping), dual-VCS, deployed-ref resolution, and a mixed VB/C#/Angular codebase in v0 from the start.

**Build principle (no rebuild later):** v0 stands up the **provider interfaces as real contracts** (VCS, CI/CD, Extractor, IntraRepo, Telemetry, GraphStore, LLM) with minimal implementations behind them, so adding dataflow analysis, LLM judgment, and more providers later is **additive, never a rewrite**. The seams exist from day one; the implementations start thin. This is how "narrow v0" and "must expand without tech debt" are reconciled.

- **Phase 0 — Seams + ingestion.** Stand up the seven provider contracts (stub/minimal impls). Wire Bitbucket + GitHub (read), TeamCity (build configs, VCS roots), Octopus (deployments, variable sets). Prove file + CI/CD ingestion and **convention-based extraction** (host/env/naming patterns) against real repos. Single env, outbound refs only.
- **Phase 1 — Closed loop at the deployed ref.** Reverse index + resolver + BFS with cycles. **Octopus deployment → deployed SHA/branch → read config at that exact ref** (never `main`). TeamCity VCS roots → per-repo attribution. Convention-matcher resolves the common case; **observe the effective value** (deploy-log / preview) *before* re-emulating scoping. Produce one real `DEPENDS_ON` edge end-to-end, with evidence, confidence, and explicit uncertainty.
- **Phase 2 — Per-environment + acquisition ladder.** Octopus variable scoping per environment; the acquisition ladder with **observe-first ordering**; GitHub-hosted associated repos folded in.
- **Phase 3 — Breadth, behind the existing contracts.** Additional connectors (GitHub Actions, CircleCI, Bitbucket Pipelines) and extractors — all as plugins against the Phase-0 interfaces, no core change.
- **Phase 4 — Dataflow + LLM (additive, via the v0 seams).** `IntraRepoProvider` (Roslyn for VB + C#, Joern for cross-language) and grounded LLM judgment slot into the interfaces that already exist — earning their place against measured resolution gaps, not by rewrite.
- **Phase 5 — Agent surface, observed-truth, ecosystem.** Query layer + MCP, telemetry cross-validation + divergence report, incremental webhooks, confidence calibration, and the published plugin contract + conformance suite.

*Design honesty: static reconstruction of config-injected, per-environment dependencies is inherently incomplete. Tendril's value is a confidence-scored, evidence-backed, self-labeling approximation that refreshes continuously and degrades visibly — not a guaranteed-complete graph. The architecture is built around that reality.*
