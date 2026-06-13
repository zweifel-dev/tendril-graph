# Cross-Repo Dependency Graph — PRD & Technical Specification

*A static, evidence-backed dependency graph reconstructed from repositories, builds, and CI/CD configuration — built to feed context to coding agents.*

**Status:** Draft v0.1 · **Audience:** Engineering leadership, platform team, AI tooling team · **Owner:** TBD

---

## The one-paragraph version

Given a single **anchor repo** that a product line starts and ends with, the system reconstructs the full repo-to-repo dependency graph across a multi-repo estate of micro-UIs and backends-for-frontends. It does this *statically* — by reading source, build files, and CI/CD configuration (TeamCity, Octopus, CircleCI) across GitHub and Bitbucket — rather than from runtime telemetry. The central trick: every service has two projections. A **consumer projection** (the URLs, service names, queues, and connection strings it references) and a **provider projection** (the identities it claims when it deploys — its hostnames, deploy targets, artifact names, per environment). An edge exists when one service's consumer reference matches another's provider identity, scoped to an environment, carried with a confidence score and the evidence that produced it. Intra-repo structure is delegated to RepoWise/CodeGraph; this system owns the *inter-repo, per-environment* layer and exposes it to coding agents (e.g. as the data backbone for `find_relevant_repos()`).

---

# Part I — Product Requirements

## 0. Design stance: general-purpose & open-source

This is specified as a **general-purpose, open-source tool** for any organization, not for one estate. Everything platform-, language-, or vendor-specific is a **reference implementation behind a plugin interface**, never a baked-in assumption:

- **VCS, CI/CD, and telemetry are providers behind interfaces.** GitHub/Bitbucket, TeamCity/Octopus/CircleCI/GitHub Actions/Bitbucket Pipelines, and Datadog/Grafana/etc. are reference connectors. Adding a provider is a plugin, not a core change.
- **Language/framework extractors are plugins.** The worked examples use a .NET WebForms host with JS/TS micro-UIs because they exercise the hard cases (token injection, iframe composition, name/URL/repo mismatch), but the extractor interface is ecosystem-agnostic — .NET, JS/TS, Java, Python, Go, and others are equal citizens, each a contributable plugin.
- **No assumption about any one feature being enabled.** Capability detection and graceful degradation are first-class (e.g. telemetry probes what's populated; resolution degrades when a store is unreadable). The tool adapts to whatever a given org actually runs.
- **Configurable scope and neutral defaults.** Orgs/workspaces to index, providers to enable, and environments to track are configuration. Nothing is hardcoded to a particular company, scale, or stack.

Read every concrete example below as illustrative of the *mechanism*, generalizable to any equivalent stack.

## 0.1 Assumptions & dependencies

- **A1 — Full org/workspace read access is granted.** The operator provides read access across *all* relevant GitHub orgs and Bitbucket workspaces, not just the anchor's. This is required, not optional: provider-identity indexing must be global (see Spec §1), and you cannot know in advance which org owns the repo that serves a given URL. This closes what was previously the top open question.
- **A2 — A dedicated read-only credential is provisioned per platform.** The system requires a key/token for each of: **GitHub, Bitbucket, CircleCI, Octopus Deploy, and TeamCity.** Each is least-privilege, read-only, brokered centrally, and rotated. Connection-level details (auth model, scopes, hooks, MCP availability, caveats) are specified in the companion *Deep Dive & Integration Spec*.
- **A3 — Source of truth is declarative.** The estate's wiring is discoverable from source + build/deploy descriptors + CI/CD variable stores. Dependencies that exist *only* at runtime (e.g. endpoints computed from data, service-mesh discovery with no declarative anchor) are out of reach of static reconstruction and are flagged, not invented.

## 1. Problem & context

A product line spans many repositories: micro front-ends, BFF APIs, shared services, and supporting jobs. They are wired together not in code but in **configuration** — base URLs, service names, queue names, connection strings — and those configuration values are **injected at build/deploy time** by the CI/CD platform (TeamCity, Octopus, CircleCI), differently per environment. The result is that no single artifact tells you "repo A depends on repo B in production." The dependency is smeared across:

- the **source** (a config key like `BILLING_BASE_URL`, an `HttpClient` base address, a queue name),
- the **repo's build/deploy descriptors** (what artifact it produces, where it deploys),
- the **CI/CD system's variable store** (the actual value of `BILLING_BASE_URL` in `prod`, possibly itself a placeholder that resolves to another variable), and
- the **provider's own deploy config** (the fact that the billing repo deploys to `billing.prod.internal`).

Today this knowledge lives in senior engineers' heads. That is expensive for incident response and onboarding, and it is a hard blocker for coding agents: an agent asked to change a contract in the anchor repo cannot reason about blast radius, and an agent asked to "fix the checkout flow" cannot assemble the right set of repos as context. The graph is the missing substrate.

This is explicitly **not** a runtime-tracing problem (no APM/OTel dependency). It is a *reconstruction from declarative artifacts* problem. That choice has consequences — covered honestly in §NFR and §Risks — but it means the graph can be built with read access to source and CI/CD alone, with no production instrumentation.

## 2. Goals

- **G1 — Closed-loop graph from an anchor.** Given one anchor repo, produce a complete, traversable graph of the repos/services reachable from it through CI/CD- and config-mediated dependencies.
- **G2 — Per-environment edges.** Every dependency edge is scoped to an environment (dev/test/stage/prod/…), because config injection makes the same code path resolve to different targets per environment.
- **G3 — Evidence and confidence on every edge.** No edge is a bare assertion; each carries provenance (which file/variable/pipeline produced it) and a calibrated confidence score, so downstream consumers (especially agents) know how far to trust it.
- **G4 — Heterogeneous sources.** First-class support for GitHub **and** Bitbucket as VCS, and TeamCity, Octopus, **and** CircleCI as CI/CD.
- **G5 — Agent-consumable.** Expose the graph through a query interface designed for coding agents (impact analysis, relevant-repo retrieval, dependency paths, environment diffs), aligned with the existing `find_relevant_repos()` MCP direction.
- **G6 — Composable with intra-repo tooling.** Treat the repo as a node and hand off to RepoWise/CodeGraph for what happens *inside* a repo, via a clean boundary contract.

## 3. Non-goals

- **NG1 — Static reconstruction is primary; runtime telemetry is optional enrichment.** The graph is built from declarative sources and must function with no telemetry at all. Runtime observability (Datadog) is layered on as an **optional cross-validation and enrichment plane** — it raises confidence where it agrees with the static graph and surfaces dynamic/hidden dependencies static analysis cannot reach, but the system never *depends* on it (the legacy anchor is often the least-instrumented node). Specified in the companion *Runtime Telemetry Integration (Datadog)*.
- **NG2 — Not intra-repo code structure.** Symbol graphs, call graphs, and file-level structure are delegated to RepoWise/CodeGraph.
- **NG3 — Not a CMDB.** It overlaps with a service catalog but is not a system of record for ownership, on-call, or SLAs.
- **NG4 — Not auto-remediation.** It informs change; it does not make changes.
- **NG5 — Not a perfect resolver.** It will not fully emulate every templating/scoping engine or resolve every dynamically computed endpoint. Unresolved and ambiguous references are *flagged*, not hidden.

## 4. Users & primary use cases

**Primary consumer: coding agents.**

1. **Blast-radius / impact analysis.** "I'm changing the response contract of endpoint `X` exposed by the anchor repo — which repos consume it, in which environments?"
2. **Context assembly / relevant-repo retrieval.** "Task: fix the checkout flow." → return the minimal connected subgraph of repos/services involved, so the agent loads the right context instead of the whole estate. This is the data feed for `find_relevant_repos()`.
3. **Dependency path.** "How does the anchor reach the payments ledger — directly, or through a BFF and a queue?"
4. **Environment diff.** "Why does this work in stage but not prod?" → compare the resolved edge set across environments.

**Secondary consumers: humans.**

5. **Incident response.** Trace upstream/downstream of a failing service, per environment.
6. **Onboarding & architecture review.** A navigable map of the estate.

## 5. Functional requirements

- **FR-1** Accept an anchor repo (VCS + org + repo + ref) and produce a dependency graph reachable from it.
- **FR-2** Discover **outbound references** from a repo: config keys/values, in-code base URLs, connection strings, queue/topic names, and artifact/package dependencies.
- **FR-3** Discover **provider identities** for a repo: the hostnames/URLs, deploy targets, deploy slots, artifact names, and queue/topic names it owns, per environment, from its build/deploy and CI/CD config.
- **FR-4** Build a **global reverse index** (provider identity → owning repo/deployable), because resolving a reference requires knowing who provides it, which is not knowable from the anchor alone.
- **FR-5** **Resolve** each outbound reference against the index to a provider repo/deployable, per environment, producing a confidence-scored edge with evidence.
- **FR-6** **Evaluate config injection**: resolve placeholder/variable references (`#{...}`, `${...}`, `%(...)%`, transforms) against the CI/CD variable stores, honoring environment scoping, to obtain concrete values where possible; flag what cannot be resolved.
- **FR-7** **Traverse** from the anchor breadth-first, expanding newly discovered providers, handling cycles (microservice graphs are cyclic) and revisits.
- **FR-8** Support **GitHub and Bitbucket** as source connectors and **TeamCity, Octopus, CircleCI** as CI/CD connectors behind a common interface.
- **FR-9** Persist the graph in a queryable store and expose **agent-facing query operations** (FR use cases §4) plus an **MCP server** wrapping them.
- **FR-10** Support **incremental refresh** on repo push and pipeline/variable change (webhook-driven), with per-node staleness tracking.
- **FR-11** Expose **unresolved / low-confidence / ambiguous** references as first-class output for human review, not silent drops.
- **FR-12** Provide a **boundary handoff** to RepoWise/CodeGraph: each repo node links to its intra-repo graph so an agent can drill from "anchor→billing edge" down to the file that exposes the endpoint.

## 6. Non-functional requirements

- **NFR-1 — Security / least privilege.** Read-only access to VCS and CI/CD. The system holds **five distinct credentials** — GitHub, Bitbucket, CircleCI, Octopus, TeamCity — each least-privilege and read-only, issued from a central secret broker with short TTL and rotation. Configs and variable stores contain secrets; the system must **redact secret-typed values** and never persist or emit them. Note that CircleCI and Octopus already mask secret variable values at the API boundary, which helps; the burden is on us to redact secrets that surface in plain config files. The five-platform credential set is itself a primary risk surface (§Risks).
- **NFR-2 — Accuracy is probabilistic, and labeled as such.** Every edge has confidence ∈ {high, medium, low}. The system optimizes for *high precision on high-confidence edges* and *high recall overall with honest labeling* — not for a single "correct" graph it cannot guarantee.
- **NFR-3 — Freshness.** Full rebuild and incremental update SLAs (targets in §metrics). Staleness is visible per node.
- **NFR-4 — Scale.** Typical target is a small-to-mid estate (tens to low-hundreds of repos; thousands of nodes; tens of thousands of edges), which does **not** require a distributed graph platform — an embedded or single-node property graph suffices. The model scales to larger estates without architectural change; only the store choice and crawl parallelism move.
- **NFR-5 — Determinism & auditability.** Given the same inputs, the same graph. Every edge is traceable to its evidence.
- **NFR-6 — Extensibility.** New CI/CD platform, VCS, or language ecosystem is a new connector/extractor, not a core rewrite.

## 7. Success metrics

- **Coverage:** ≥ 95% of repos reachable from the anchor are discovered and indexed (validated against a hand-built golden estate).
- **Resolution rate:** ≥ 85% of extracted outbound references resolve to a provider at ≥ medium confidence; the remainder are explicitly flagged.
- **Edge precision (high-confidence):** ≥ 0.95 against the golden set.
- **Edge recall (all confidence):** ≥ 0.85 against the golden set.
- **Freshness:** incremental update reflected in the graph within X minutes of a push/pipeline change (target TBD, e.g. 10 min); full rebuild within Y hours.
- **Downstream (the real metric):** measurable uplift in agent task success / reduction in irrelevant repos loaded as context when retrieval is graph-backed vs. baseline.

## 8. Risks & mitigations

| Risk | Why it bites | Mitigation |
|---|---|---|
| **Credential sprawl** across 2 VCS + 3 CI/CD systems | Large secret surface; broad read access | Centralized secret broker, scoped read-only tokens, short TTL, no secret persistence, audit log of reads |
| **Secret leakage** from configs into the graph | Variable stores hold passwords/keys | Type-aware redaction; store only the *shape* of secret values (e.g. "sensitive, present"), never the value |
| **Resolution ambiguity** → wrong edges → agents misled | Two services may claim overlapping identities; fuzzy name matches | Confidence scoring; ambiguous matches emitted as candidates for review, never auto-promoted to high confidence |
| **Config-templating complexity** | Each CI/CD platform has its own scoping & substitution semantics | Per-platform resolver with explicit "best-effort + flag unresolved" contract; never silently guess |
| **Drift** between repo config and what's actually deployed | Static view can lag reality | Per-node staleness; optional later cross-check against runtime as validation (NG1 future) |
| **Heterogeneity tax** | 3 CI/CD models differ structurally | Normalize each into a common IR early; keep platform quirks at the connector edge |
| **Over-trust by agents** | Agents may treat a low-confidence edge as fact | Confidence is part of the query contract; agent tools surface it and can filter on it |

## 9. Phased roadmap

- **Phase 0 — Extraction spike.** Anchor + GitHub + CircleCI + .NET extractor. One environment. Outbound references only (no resolution). Goal: prove we can reliably pull references and provider identities from real repos.
- **Phase 1 — Closed loop.** Reverse index + resolver + BFS traversal with cycle handling. One VCS + one CI/CD. Single environment. First real graph.
- **Phase 2 — Environments.** Octopus connector (its variable scoping is the canonical per-environment model) + per-environment edges + the variable-resolution engine.
- **Phase 3 — Full source matrix.** Add Bitbucket + TeamCity connectors. Complete the VCS × CI/CD matrix.
- **Phase 4 — Agent surface.** Graph store + query layer + MCP server (`find_relevant_repos`, `impact_analysis`, `dependency_path`, `env_diff`) + webhook-driven incremental refresh.
- **Phase 5 — Hardening.** Confidence calibration against a golden set, async/queue edges, secret-redaction audit, RepoWise/CodeGraph handoff polish.

---

# Part II — Technical Specification

## 1. Architecture overview

```
                          ┌──────────────────────────────────────────┐
                          │              Orchestrator                  │
                          │  (anchor-driven traversal + scheduling)    │
                          └───────────────┬────────────────────────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                 │
┌───────▼────────┐              ┌─────────▼─────────┐             ┌─────────▼─────────┐
│ Source         │              │ CI/CD             │             │ Variable          │
│ Connectors     │              │ Connectors        │             │ Resolution Engine │
│ GitHub, BitB.  │              │ TeamCity, Octopus,│             │ (per-env eval of  │
│                │              │ CircleCI          │             │  injected config) │
└───────┬────────┘              └─────────┬─────────┘             └─────────┬─────────┘
        │   normalized repo IR            │  normalized pipeline IR         │
        └─────────────────┬───────────────┴────────────────┬────────────────┘
                          │                                 │
                  ┌───────▼────────┐                ┌───────▼────────┐
                  │  Extractors    │                │  Provider-      │
                  │ (.NET, JS/TS,  │                │  identity       │
                  │  IaC, CI vars) │                │  collector      │
                  └───────┬────────┘                └───────┬────────┘
              consumer projections              provider projections
                          │                                 │
                          │                         ┌───────▼────────┐
                          │                         │ Reverse Index  │
                          │                         │ identity→owner │
                          └──────────────┬──────────┴───────┬────────┘
                                         │ resolve (join)    │
                                  ┌──────▼───────────────────▼──────┐
                                  │      Confidence + Evidence       │
                                  └──────────────┬───────────────────┘
                                                 │ edges
                                        ┌────────▼─────────┐
                                        │   Graph Store    │
                                        │ (property graph) │
                                        └────────┬─────────┘
                                                 │
                                        ┌────────▼─────────┐
                                        │ Query Layer +    │
                                        │ MCP Server       │──▶ coding agents
                                        └──────────────────┘
                                                 │  link out
                                        ┌────────▼─────────┐
                                        │ RepoWise/CodeGraph│ (intra-repo)
                                        └──────────────────┘
```

Data flow in one sentence: connectors emit a normalized IR → extractors derive **consumer projections** and the provider-identity collector derives **provider projections** → provider projections are materialized into a **reverse index** → the resolver **joins** consumer references to provider identities per environment → confidence/evidence are attached → edges land in the **graph store** → the **query layer / MCP server** serves agents.

### The pivotal nuance: indexing is global, traversal is anchored

A naive reading of "start at the anchor and follow" fails: to resolve "I call `billing.prod`" you must already know *which repo provides `billing.prod`*, and that is not derivable from the anchor. Therefore:

- **Provider-identity indexing is global** (or at least covers the whole accessible estate). It is cheap — it reads deploy/build descriptors and CI/CD targets, mostly metadata — and it builds the reverse index.
- **Consumer traversal is anchor-bounded.** From the anchor we expand only the repos reachable through resolved edges, controlling the *scope of the graph* without limiting the *scope of the index*.

In short: index everyone's "I am," then walk the anchor's "I call."

## 2. Domain model (graph schema)

**Node types**

| Node | Key properties |
|---|---|
| `Repo` | vcs, org, name, default_branch, url, last_indexed_ref, staleness |
| `Deployable` | name, kind (web/api/job/ui/bff), produced_by → Repo, artifact_id |
| `Environment` | name (dev/test/stage/prod), aliases |
| `Endpoint` | scheme, host, port, path_base — the addressable identity |
| `Pipeline` | platform (teamcity/octopus/circleci), id, kind (build/deploy) |
| `ServiceIdentity` | canonical id + alias set (see §3) |
| `ConfigVar` | key, scope (env), value_or_redacted, is_secret |
| `MessageChannel` | kind (queue/topic), name — for async edges |

**Edge types** (edges are environment-scoped and carry `confidence`, `evidence`, `discovered_at`)

| Edge | Meaning |
|---|---|
| `Repo —PRODUCES→ Deployable` | a repo builds one or more deployables |
| `Deployable —EXPOSES→ Endpoint @env` | provider projection: "I am reachable here" |
| `Deployable —CONSUMES→ Endpoint @env` | consumer projection: "I call this" |
| `Endpoint —RESOLVES_TO→ Deployable @env` | the resolution edge — the join result |
| `Deployable —DEPENDS_ON→ Deployable @env` | the materialized repo-to-repo edge agents query |
| `Pipeline —BUILDS→ Repo` / `Pipeline —DEPLOYS→ Deployable @env` | CI/CD wiring |
| `ConfigVar —INJECTED_INTO→ Deployable @env` | config injection provenance |
| `Deployable —PUBLISHES/SUBSCRIBES→ MessageChannel @env` | async dependency |
| `Repo —HAS_INTERNAL_GRAPH→ (RepoWise/CodeGraph ref)` | boundary handoff |

`DEPENDS_ON` is the convenience edge most queries hit; it is derived from a `CONSUMES → RESOLVES_TO → EXPOSES` triangle and inherits the weakest confidence in that chain.

## 3. Canonical Service Identity & alias resolution

A service is known by many names; matching on any single one is brittle. Define a **canonical `ServiceIdentity`** carrying an alias set across identity *classes*:

- **Network:** hostnames/URLs per environment (`billing.prod.internal`, `billing.dev.internal`)
- **Logical:** service/app names (`billing-api`, `BillingApi`, `Billing.Service`)
- **Deploy:** Octopus project name, TeamCity build config id, deploy slot/role
- **Artifact:** NuGet package id, npm package, Docker image/repo
- **Async:** queue/topic names it owns
- **Data:** DB schema / connection identity (weaker signal, lower confidence)

A **normalizer** canonicalizes raw references (case-fold, strip env suffixes, expand known abbreviations, map host↔service via DNS/ingress config when available). Matching produces a confidence by identity class:

- exact deploy-target / artifact match → **high**
- exact host/URL match (post env-resolution) → **high**
- normalized logical-name match → **medium**
- fuzzy logical-name / data-identity match → **low** (candidate, needs review)

When two identities claim the same alias, the resolver emits **both** candidates rather than picking one; ambiguity is surfaced (FR-11).

## 4. Connector layer

Each connector translates a platform into a common **IR** so the rest of the system is platform-agnostic. Connectors are read-only.

**Source connectors — capabilities they must expose:** list repos in org/workspace; read file/tree at a ref; read default branch; enumerate webhooks (for later incremental). GitHub and Bitbucket differ in API shape (REST/GraphQL vs. Bitbucket REST + workspaces) but both satisfy this interface.

**CI/CD connectors — capabilities they must expose** (normalized to: *what builds, what deploys where, with what variables, scoped how*):

- **TeamCity:** build configurations & templates, parameters (config/system/env), VCS roots (→ which repo a build belongs to), artifact dependencies and snapshot dependencies (→ build-time inter-build edges). Parameter precedence/templating must be captured.
- **Octopus Deploy:** projects, deployment processes, **variable sets with scoping** (environment, role, target, channel — this is the richest per-environment model and the reason Octopus comes in Phase 2), environments, deployment targets, releases. Variable substitution syntax `#{...}` and its scoping rules are first-class.
- **CircleCI:** `config.yml` (jobs/workflows/orbs), **contexts** and project/context environment variables, deploy jobs. `${VAR}` substitution and context scoping captured.

The connector's job is not to interpret — it is to faithfully extract the platform's build/deploy topology and variable store into IR. Interpretation (resolution, scoping evaluation) happens in the variable-resolution engine and resolver.

## 5. Extractor layer (consumer & provider projections from source)

Extractors run over a repo's normalized IR to produce projections. Per-ecosystem, because reference patterns differ:

- **.NET:** `appsettings.json` / `appsettings.{Environment}.json`, `web.config` + config transforms, `HttpClient`/`HttpClientFactory` base addresses, connection strings, `csproj`/NuGet references (artifact edges), WCF/service endpoints.
- **JS/TS micro-UIs:** `.env*`, `next.config`/`vite`/`webpack` env injection, `package.json` deps, API client base-URL config, dev-proxy configs (a common place BFF wiring hides).
- **IaC / deploy descriptors:** Helm `values.{env}.yaml`, k8s manifests (Services/Ingress → provider endpoints), Terraform, ARM/Bicep, Dockerfiles (image → artifact identity).
- **CI/CD-injected:** the variable stores from §4, treated as a config source whose values may override or supply what the repo leaves as a placeholder.

Each extracted item is `(reference | identity, class, raw_value, env_scope_hint, evidence{file, line, source})`. Extractors are deliberately dumb about *meaning*; they locate and classify, they do not resolve.

## 6. Variable-resolution engine (config injection)

The hard core. Raw values are frequently placeholders, and the concrete value depends on environment-scoped variable stores: `BILLING_URL = #{Billing.BaseUrl}` where `Billing.BaseUrl` is defined in an Octopus variable set scoped to `prod`, possibly referencing yet another variable.

Responsibilities:

1. **Per-environment evaluation.** For each environment, resolve placeholders against the merged variable store for that environment, honoring platform scoping/precedence (Octopus scoping, TeamCity parameter precedence, CircleCI context layering).
2. **Transitive resolution.** Variables referencing variables → resolve the internal variable dependency graph; detect cycles.
3. **Best-effort + flag.** When a value cannot be resolved (computed at runtime, sourced from a system outside scope, conditional logic the engine doesn't model), emit it as **unresolved** with the partial value and the reason. Never fabricate.
4. **Secret awareness.** Sensitive-typed variables are evaluated for *structure* (does it resolve to a host?) but their values are redacted in storage (NFR-1).

Explicit non-goal: this engine does **not** perfectly emulate every templating language or arbitrary build-script logic. It targets the common, declarative cases that cover the large majority of real wiring, and it is honest about the tail.

## 7. The reverse index (who-owns-what)

Materialization of all **provider projections**: for every deployable, every identity it claims (host/URL per env, deploy target, artifact id, queue/topic), keyed for lookup. Built during global indexing (§1). Structure: a multi-map `normalized_identity @env → {Deployable, identity_class, evidence}`, supporting exact and normalized lookups, with the alias machinery of §3 layered on top. This index is what makes the loop closeable — it is the difference between "the anchor mentions `billing.prod`" and "the anchor depends on the *billing repo* in prod."

## 8. Traversal engine

```
seed queue with anchor repo
while queue not empty:
    repo = dequeue()
    if repo already expanded: continue
    consumer_refs = extractors(repo)              # what it calls
    for env in environments:
        for ref in consumer_refs:
            value = variable_resolution(ref, env) # concrete-ish value
            for candidate in reverse_index.lookup(value, env):
                edge = DEPENDS_ON(repo → candidate.repo, env,
                                  confidence=score(ref, candidate),
                                  evidence=[ref.evidence, candidate.evidence])
                persist(edge)
                if candidate.repo not expanded: enqueue(candidate.repo)
    mark repo expanded
```

- **Cycle handling:** microservice graphs are cyclic; the `expanded` set prevents infinite loops while still recording all edges (cycles are real dependencies and must appear in the graph, just not re-walked).
- **Per-environment:** the inner loop is environment-parameterized; an edge present in prod but absent in dev is a normal, queryable outcome.
- **Confidence propagation:** a `DEPENDS_ON` edge inherits the minimum confidence along its `CONSUMES → RESOLVES_TO → EXPOSES` chain.
- **Bounded scope:** traversal expands only reachable repos; the global index already exists, so resolution never requires walking the whole estate.

## 9. Confidence & evidence model

Every edge stores:

- `confidence`: high / medium / low, derived from identity class (§3) and resolution completeness (fully-resolved value > partially-resolved > name-only).
- `evidence`: ordered list of `{source_type, locator}` — e.g. `appsettings.prod.json:42`, `octopus:varset:Billing/prod:Billing.BaseUrl`, `circleci:context:payments:BILLING_URL`. This is what makes the graph auditable (NFR-5) and what lets an agent or human verify rather than trust.

Confidence is part of the **public query contract**: consumers can filter (`min_confidence=high` for blast-radius safety, lower for exploratory context assembly).

## 10. Graph store & query layer

**Store:** a property graph fits the model directly. At this scale (NFR-4) an **embedded graph DB (e.g. Kùzu)** or a single-node **Neo4j** is appropriate; no distributed platform needed. The schema of §2 maps 1:1 to labeled nodes and typed, property-bearing edges. An alternative is graph-over-relational (SQLite + adjacency), acceptable but weaker for path queries.

**Representative queries** (expressed conceptually; final dialect follows the store):

- *Blast radius:* from `Endpoint X exposed by anchor`, all `CONSUMES` in `prod` at `min_confidence=high`.
- *Relevant repos for a task:* given seed repos/keywords, the connected `DEPENDS_ON` subgraph within N hops, ranked by edge confidence and proximity.
- *Dependency path:* shortest `DEPENDS_ON` path anchor → target service in `prod`.
- *Environment diff:* symmetric difference of the anchor's `DEPENDS_ON` edge set between `stage` and `prod`.

## 11. Agent consumption interface (MCP)

The graph is exposed as an **MCP server** so coding agents consume it natively — this is the data backbone for the existing `find_relevant_repos()` direction. Proposed tools:

- `find_relevant_repos(task_or_seeds, env?, max_hops?, min_confidence?) → ranked repos + why`
- `impact_analysis(repo|endpoint, env, min_confidence?) → downstream consumers + evidence`
- `dependency_path(from, to, env) → path with per-edge confidence`
- `env_diff(repo, env_a, env_b) → added/removed/changed edges`
- `explain_edge(edge_id) → full evidence chain` (for agent/human verification)

Each response includes confidence and evidence so the agent can decide how much to rely on it (NFR-2). For deeper file-level context, the agent follows the §12 handoff.

## 12. Integration with RepoWise / CodeGraph (boundary contract)

Clean separation of concerns: this system owns **inter-repo, per-environment** dependencies; RepoWise/CodeGraph own **intra-repo** structure. The contract:

- Each `Repo` node carries a `HAS_INTERNAL_GRAPH` reference (tool + locator) into its intra-repo graph.
- A typical agent flow: query this graph for "anchor `DEPENDS_ON` billing @prod via endpoint `/charges`" → follow the handoff into billing's CodeGraph to find the controller/handler that serves `/charges`. The inter-repo edge lands on the repo boundary; the intra-repo tool resolves below it.
- This system never duplicates intra-repo analysis; it consumes a stable reference, so the two layers evolve independently.

## 13. Incremental updates & freshness

Full crawls are the cold-start; steady state is webhook-driven:

- **VCS push** on a repo → re-extract that repo's projections, re-resolve its outbound edges and any provider identities it changed (which may invalidate inbound edges from others).
- **CI/CD change** (pipeline or variable-set edit) → re-evaluate affected deployables/environments.
- **Staleness** is tracked per node (`last_indexed_ref`, `last_seen`); queries can expose or filter on it. Invalidation is scoped to the changed subgraph, not a global rebuild.

## 14. Security & secret handling

- Read-only, least-privilege tokens per platform, brokered centrally, short TTL (NFR-1).
- **Secret redaction is mandatory and happens before persistence.** Sensitive-typed config values are stored as `{is_secret: true, resolved: <bool>}` — structure only, never value.
- Read audit log across all 5 systems.
- The graph itself is sensitive (it maps the estate's topology); access-control the query layer and MCP server accordingly.

## 15. Open questions / decisions to make

1. **~~Anchor scope vs. global index cost.~~ Resolved by A1** — full org/workspace read access is granted, so global provider indexing is viable. Remaining sub-decision: define whether the index boundary is "all accessible orgs" or an explicit allowlist, to bound crawl cost.
2. **Environment canonicalization.** Environments are named inconsistently across TeamCity/Octopus/CircleCI; need a canonical environment dictionary with aliases.
3. **Async edges in v1?** Queue/topic dependencies are real and often the *missed* ones, but add extractor surface. Phase 5 vs. earlier?
4. **Graph store choice.** Kùzu (embedded, low-ops) vs. Neo4j (richer tooling). Lean embedded unless multi-consumer concurrency is needed soon.
5. **Confidence calibration.** Requires a hand-labeled golden estate; who builds it and how big?
6. **Identity collisions.** Policy when two deployables legitimately share an identity (blue/green, shared gateway) — model as one identity with multiple owners, or distinct?
7. **Runtime validation (future).** Worth a thin OTel/gateway-log cross-check later to score the static graph's precision? Listed as NG1-future; decide if it earns a roadmap slot.

---

*This is a design draft. The honest framing: static reconstruction of config-injected, per-environment dependencies is inherently incomplete — the value is a confidence-scored, evidence-backed approximation that is continuously refreshed and self-labeling about its own uncertainty, not a guaranteed-complete graph. The architecture is built around that reality rather than against it.*
