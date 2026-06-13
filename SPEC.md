# Tendril — Technical Specification

*Consolidated technical spec. Companion to `PRD.md`. Covers architecture, the provider plugin contract, the resolution pipeline, the graph model, telemetry cross-validation, and the agent surface. Concrete platforms/languages are reference implementations behind the plugin contract (§4).*

**Status:** Draft v1.0 (consolidated)

---

## 1. Architecture overview

Tendril reconstructs the inter-repo dependency graph from three data planes, with everything platform-specific behind a plugin boundary.

```
        ┌──────────────────────────── PROVIDERS (plugins, §4) ────────────────────────────┐
        │                                                                                  │
  Source plane              Build/Deploy plane                Runtime plane                │
 ┌──────────────┐   ┌──────────────────────────┐   ┌──────────────────────────┐           │
 │ VCSProvider  │   │ CICDProvider             │   │ TelemetryProvider        │           │
 │ github,      │   │ github-actions, octopus, │   │ datadog, grafana,        │           │
 │ bitbucket-*  │   │ teamcity, circleci,      │   │ honeycomb, otel          │           │
 │              │   │ bitbucket-pipelines      │   │ (capability-probed)      │           │
 └──────┬───────┘   └───────────┬──────────────┘   └────────────┬─────────────┘           │
        │ RepoIR                │ PipelineIR / VariableStore     │ ObservedEdges           │
        └──────────┬────────────┴───────────────┬────────────────┘                         │
                   ▼                             ▼                                          │
          ┌──────────────────┐        ┌────────────────────────┐                           │
          │ ExtractorPlugins │        │ CI/CD Attribution (§7) │                           │
          │ dotnet, jsts,    │        │ per-repo provider      │                           │
          │ iac, composition │        │ discovery + profile    │                           │
          └────────┬─────────┘        └───────────┬────────────┘                           │
                   │ consumer refs + provider IDs  │ which store per env                   │
                   └──────────────┬────────────────┘                                        │
                                  ▼                                                         │
                    ┌──────────────────────────┐    ◄── Value Acquisition Ladder (§9)      │
                    │ Variable Resolution +     │        static→store→preview→log→browser   │
                    │ Reverse Index (§8) +      │                                           │
                    │ Resolver / Join (§10)     │                                           │
                    └────────────┬──────────────┘                                           │
                                 │ declared/injected edges (confidence + evidence)          │
                                 ▼                                                          │
                    ┌──────────────────────────┐    observed edges (cross-validate, §11)   │
                    │   GraphStore (plugin)     │ ◄────────────────────────────────────────┘
                    │   kuzu / neo4j            │
                    └────────────┬──────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │ Query Layer + MCP (§13)   │──▶ coding agents
                    └──────────────────────────┘
```

### 1.1 The two load-bearing ideas

**The projection join.** Every service has a **consumer projection** (references it emits — "I call X") and a **provider projection** (identities it claims — "I am reachable as Y"). An edge exists when a consumer reference matches a provider identity, scoped to an environment, with confidence from the match strength. The reverse index materializes all provider projections so the join can be computed.

**Index globally, traverse from the anchor.** Resolving "I call `billing.prod`" requires already knowing who *provides* `billing.prod`, which is not derivable from the anchor. So provider-identity indexing is **global** across the configured scope (cheap, mostly metadata), while consumer **traversal is anchor-bounded**. Index everyone's "I am," walk the anchor's "I call."

---

## 2. Domain model (graph schema)

**Nodes:** `Repo`, `Deployable` (produced_by Repo; kind web/api/job/ui/bff), `Environment` (with provenance), `Endpoint` (scheme/host/port/path_base), `Pipeline`, `CICDProvider` (system, role[]), `VariableStore` (kind, scopes, readable), `ServiceIdentity` (canonical + aliases), `ConfigVar`, `MessageChannel` (queue/topic).

**Edges** (environment-scoped; carry `provenance`, `confidence`, `evidence`, `discovered_at`):

| Edge | Meaning |
|---|---|
| `Repo —PRODUCES→ Deployable` | a repo builds deployables |
| `Deployable —EXPOSES→ Endpoint @env` | provider projection |
| `Deployable —CONSUMES→ Endpoint @env` | consumer projection |
| `Endpoint —RESOLVES_TO→ Deployable @env` | the join result |
| `Deployable —DEPENDS_ON→ Deployable @env` | the materialized edge agents query |
| `Repo —BUILT_BY→ CICDProvider` / `—DEPLOYED_BY→ CICDProvider @env` | attribution (§7) |
| `CICDProvider —RESOLVES_VARS_FROM→ VariableStore` | where values come from |
| `Pipeline —BUILDS→ Repo` / `—DEPLOYS→ Deployable @env` | CI/CD wiring |
| `ConfigVar —INJECTED_INTO→ Deployable @env` | injection provenance |
| `Deployable —PUBLISHES/SUBSCRIBES→ MessageChannel @env` | async dependency |
| `Repo —HAS_INTERNAL_GRAPH→ {tool,locator}` | intra-repo handoff (§12) |

**Provenance dimension** on edges: `declared` (static source), `injected` (CI/CD-resolved), `observed` (runtime telemetry). An edge may carry several; cross-plane agreement multiplies confidence. `DEPENDS_ON` derives from a `CONSUMES → RESOLVES_TO → EXPOSES` triangle and inherits the weakest confidence in the chain.

---

## 3. Canonical Service Identity & alias resolution

A service is known by many names; matching on any one is brittle. A canonical `ServiceIdentity` carries aliases across identity **classes**: network (host/URL per env), logical (service/app names), deploy (Octopus project, TeamCity build-config id, slot/role), artifact (NuGet/npm/image id), async (queue/topic), data (DB schema/connection). A normalizer canonicalizes raw references (case-fold, strip env suffixes, expand abbreviations, map host↔service via DNS/ingress). Match confidence by class: exact deploy-target/artifact or exact host/URL (post env-resolution) → **high**; normalized logical-name → **medium**; fuzzy logical/data → **low** (candidate, needs review). Colliding aliases emit *both* candidates; ambiguity is surfaced, never auto-resolved.

---

## 4. The Provider Plugin Contract (FR-17)

The extensibility core. **Six plugin families** (five structural, plus an optional advisory `LLMProvider`, §4.7) behind stable, **semantically versioned** interfaces, a normalized IR, capability declaration, registration/discovery, and a **conformance suite** every plugin must pass. A third party adds a provider without modifying core. Interfaces below are language-neutral pseudocode; the reference implementation language (e.g. Python or TypeScript) defines the concrete ABI.

### 4.1 Shared IR types

```
RepoRef         { provider, org, name, default_branch, url }
FileEntry       { path, type(file|dir), size }
Evidence        { source_type, locator }            # e.g. "appsettings.prod.json:42"
ConsumerRef     { kind, raw_value, token_refs[], env_hint?, evidence[] }
ProviderIdentity{ identity_class, value, env?, evidence[] }
TokenDecl       { name, declared_in: Evidence, injected: bool }
VarEntry        { key, value? , is_secret, readable, scope: {env?, role?, tenant?, channel?} }
VariableStore   { kind, entries: VarEntry[], scoping_model }
PipelineBinding { provider, pipeline_id, repo: RepoRef, roles:[build|deploy|test], env? }
ObservedEdge    { from_service, to_service, env, capability, last_seen, sample_count }
ServiceEntity   { service, repo?, deps[]?, team? }
Capabilities    { <name>: bool }                    # declared per provider, probed where dynamic
```

### 4.2 `VCSProvider` (source plane)

```
id() -> string                                   # "github" | "bitbucket-cloud" | "bitbucket-dc"
capabilities() -> Capabilities                   # { graphql, webhooks, ... }
list_repos(scope) -> RepoRef[]
read_tree(repo, ref) -> FileEntry[]
read_file(repo, ref, path) -> bytes
default_branch(repo) -> string
list_webhooks(repo) -> Webhook[]                 # optional, for incremental
```

### 4.3 `CICDProvider` (build/deploy plane)

```
id() -> string                                   # "github-actions"|"octopus"|"teamcity"|"circleci"|"bitbucket-pipelines"
capabilities() -> Capabilities                   # { variable_preview, deploy_logs, native_webhooks,
                                                 #   env_scoping_model, intrinsic|extrinsic, config_as_code }
discover_for_repo(repo, repo_ir) -> PipelineBinding[]   # intrinsic detection contribution (§7)
list_pipelines(scope) -> Pipeline[]                     # extrinsic mapping (e.g. TeamCity VCS roots)
read_variable_store(pipeline|project, env) -> VariableStore   # with scoping + readable/masked flags
read_provider_identities(pipeline|project, env) -> ProviderIdentity[]   # deploy targets, hosts, artifacts
read_effective_value(token, project, env) -> Resolved | Unresolved      # preview API, if supported
read_deploy_logs(run) -> LogStream              # acquisition ladder rung 4, if supported
```

### 4.4 `ExtractorPlugin` (language/framework)

```
id() -> string                                   # "dotnet"|"jsts"|"iac"|"composition"|...
matches(repo_ir) -> bool                          # does this repo contain my ecosystem?
extract(repo_ir) -> {
    consumer_refs: ConsumerRef[],
    provider_identities: ProviderIdentity[],
    token_decls: TokenDecl[]
}
```
Extractors **locate and classify; never resolve.** Multiple extractors may match one repo; results are merged.

### 4.5 `TelemetryProvider` (runtime plane, optional)

```
id() -> string                                   # "datadog"|"grafana"|"honeycomb"|"otel"
probe(env) -> Capabilities                        # { logs, apm_traces, apm_service_dependencies, rum, deploy_events }
service_dependencies(env) -> ObservedEdge[]       # if apm_service_dependencies
edges_from_traces(env) -> ObservedEdge[]          # if apm_traces
edges_from_logs(env) -> ObservedEdge[]            # if logs (lower fidelity)
edges_from_rum(env) -> ObservedEdge[]             # if rum (browser/composition edges)
service_catalog() -> ServiceEntity[]              # reverse-index seed
deploy_events(env) -> DeployEvent[]               # optional, often absent
```

### 4.6 `GraphStore` (persistence)

```
id() -> string                                   # "kuzu" | "neo4j"
upsert_node(node); upsert_edge(edge)
query(spec) -> rows
neighbors(node, rel?, env?, min_confidence?) -> node[]
path(from, to, env) -> path
```

### 4.7 Registration, capability negotiation, versioning, conformance

- **Registration/discovery.** Plugins register via the ecosystem's entry-point mechanism (e.g. Python entry points, npm package convention) plus a `tendril-plugin.toml` manifest declaring `id`, `family`, `contract_version`, and static capabilities. Core discovers and loads by manifest.
- **Capability negotiation.** Core calls `capabilities()`/`probe()` and routes work to what's actually supported; missing capabilities degrade (NFR-7), never crash.
- **Versioning.** The contract is **semver'd** independently of core. Plugins declare the contract major they target; core refuses incompatible majors with a clear error and supports a deprecation window.
- **Conformance suite.** A published test harness exercises each interface against recorded fixtures (golden VCS trees, CI/CD configs, telemetry payloads). A plugin is "supported" only if it passes; the suite is the contract's executable definition and the gate for community providers.

---

## 5. Connector reference implementations

Each reference connector implements §4 and normalizes its platform into IR. Read-only throughout. Per-provider connection detail (auth, scopes, hooks, MCP, caveats):

- **GitHub (VCS).** Prefer a **GitHub App** installation token over a PAT (fine-grained PATs are single-resource-owner; an App spans orgs cleanly). Read: Contents, Metadata, plus Actions/Variables/Secrets-metadata/Environments for the GitHub Actions CI/CD provider. Webhooks on `push`. Official read-only MCP for the agent path.
- **Bitbucket (VCS).** **Cloud vs Data Center is a hard fork** — Cloud uses OAuth/API-token against `api.bitbucket.org` (tokens expire hourly, refresh needed); Data Center uses HTTP access tokens against the self-hosted REST API. Repo read + separate webhook scope. Atlassian Rovo MCP covers Cloud (org-linked, API-token).
- **CircleCI (CI/CD).** Personal API token (`Circle-Token`); project tokens unsupported on v2. Read `config.yml`, contexts + env-var **names** (secret values masked). Outbound webhooks. Official MCP. Rate-limit/pagination aware.
- **Octopus Deploy (CI/CD).** API key, scoped by Space. Read spaces/environments/projects/deployment-processes/targets/**variable sets** (sensitive masked) + git branches. Subscriptions for events. Official read-only MCP. Richest env-scoping model → anchors per-env work.
- **TeamCity (CI/CD).** Access token; REST at `/app/rest`. Read build configs/templates, parameters, **VCS roots** (the link to the repo), snapshot/artifact deps. Native webhooks for build events. Built-in MCP (2026.1) + community server. **Confirm On-Prem is patched for known CVEs before pointing a credential at it.**
- **GitHub Actions (CI/CD, intrinsic).** Rides the GitHub credential. Detect via `.github/workflows/*.yml`. **GitHub Environments are a native, readable per-env scoping source** (`vars.*` readable; `secrets.*` names only; env-scoped values override repo-level when a job sets `environment:`).
- **Bitbucket Pipelines (CI/CD, intrinsic).** Rides the Bitbucket credential. Detect via `bitbucket-pipelines.yml`. Repo/workspace/deployment variables (secured masked); Bitbucket Deployments as the env construct.

**Build-vs-buy on MCP.** Use each platform's **official MCP for the agent/diagnostic path**; build **typed REST connectors for the deterministic bulk index** (pagination, backoff, redaction, reproducibility). Both share the brokered credentials.

---

## 6. Extractor reference implementations

Per-ecosystem plugins producing consumer/provider/token projections:

- **Composition (view-layer, FR-13).** Scans `.aspx`/`.ascx`/`.master`/`.cshtml`/`.razor`/`.html` and proxy/rewrite config (`web.config <rewrite>`, IIS URL Rewrite, BFF proxies) for `iframe src`, `script/link src/href`, importmaps/Module-Federation remotes, and config attributes carrying base URLs. Runs placeholder detection (`{t}`, `#{t}`, `${t}`, `%(t)%`, `<%$ %>`) and records a pointer to each token's declaration. Locate-and-classify only.
- **.NET.** `appsettings.*`, `web.config` + transforms, `HttpClient` base addresses, connection strings, `csproj`/NuGet refs, WCF endpoints.
- **JS/TS.** `.env*`, `next/vite/webpack` env injection, `package.json` deps, API-client base URLs, dev-proxy configs.
- **IaC/deploy.** Helm `values.{env}.yaml`, k8s Services/Ingress (provider endpoints), Terraform, ARM/Bicep, Dockerfiles (image identity).
- **(Community) Java/Spring, Python, Go, etc.** Same interface; contributable.

---

## 7. CI/CD Attribution engine

CI/CD is **per-repo and heterogeneous**; the resolver can't pick a variable store until it knows which system deploys *this* repo to *this* env. Attribution runs **between extraction and resolution**.

**Evidence, two directions.** *Intrinsic:* detector files (`.github/workflows/`, `.circleci/config.yml`, `bitbucket-pipelines.yml`, `.teamcity/` Kotlin DSL, `.octopus/*.ocl` Config-as-Code, `azure-pipelines.yml`, `Jenkinsfile`) and **deploy-step detection inside a build workflow** (an `OctopusDeploy/*` action, `aws deploy`, `helm/kubectl`, Terraform apply, a platform trigger) — the key heuristic for chaining. *Extrinsic:* platform→repo mappings (TeamCity VCS roots, CircleCI project⇄repo, Octopus Config-as-Code git connection or artifact provenance).

**Multiplicity & chaining.** A repo's CI/CD is a **set of (provider, role)**. Build owner and deploy owner are often different (build in GitHub Actions, deploy via Octopus). Rule:

> **Injected runtime/deploy-time tokens resolve against the *deploy owner's* store for the target env; build-time-only tokens against the *build owner's* store.** The deploy owner is whichever system performs the env-specific deploy step.

**Output — the CI/CD Profile** (per repo): environments detected; per provider its `role[]`, confidence, evidence, `env_scoping_source`, and `variable_stores` (kind, readable, scopes). Profile confidence caps the confidence of any edge resolved through it.

**GitHub Environments** are a first-class env-scoping source on par with Octopus: env-scoped vars/secrets override repo-level when a job sets `environment:`; `vars.*` readable, `secrets.*` names-only. So a repo that builds *and* deploys in Actions is fully resolvable on its own — the cheapest end-to-end slice.

---

## 8. The reverse index

Materialization of all **provider projections**: for every deployable, every identity it claims (host/URL per env, deploy target, artifact id, queue/topic), keyed for exact and normalized lookup with the alias machinery of §3. Built during global indexing. `normalized_identity @env → { Deployable, identity_class, evidence }`. This is what makes the loop closeable.

---

## 9. Variable resolution + Value Acquisition Ladder

Tokens are evaluated per environment against the store the attribution profile selected. The **how** of obtaining a value is a tiered ladder, tried cheapest/safest first; record which rung produced the value (it caps confidence):

1. **Static config in repo** — literal values committed in `appsettings.*`/`values.{env}.yaml`/`.env`.
2. **CI/CD variable store API** — read value + apply the store's scoping (Octopus scope match, GitHub Environment override, TeamCity inheritance, CircleCI context binding, Bitbucket deployment scope).
3. **Effective-value / preview API** — read the value *as the platform resolved it* (e.g. Octopus variable preview). Cleanest; avoids re-emulating scoping.
4. **Deploy-log harvesting** — parse deploy/build logs for the **effective non-secret values actually injected**, per env. Ground truth of what shipped; carries a run-id/freshness qualifier.
5. **Browser fallback (Playwright)** — gated: **non-secret only, self-hosted only, last resort**, dedicated low-priv account, isolated context, never on the bulk path, medium-at-best confidence. Inverts the read-only/least-priv posture, so bottom rung.
6. **Runtime introspection (optional)** — query a deployed service's effective config; validation-grade.

**Secret floor.** Secret-typed values are masked in the UI, the API, **and logs** — so no rung recovers them. A genuinely secret-hidden value is emitted as `unresolved-secret` + evidence, for human review or runtime cross-fill (§11). Prefer rungs 3–4 ("let the platform resolve, read the answer") over re-emulating scoping or driving a browser.

```
acquire(T, repo R, env E):
    for rung in [static, store_api, preview_api, deploy_log, browser, runtime]:
        if rung == browser and (T.is_secret or target.is_saas): continue
        v = rung.try(T, R, E); if v concrete: return (v, rung)
    return (UNRESOLVED_SECRET if T.is_secret else UNRESOLVED_NO_SOURCE)
```

---

## 10. Traversal engine

```
seed queue with anchor repo
while queue not empty:
    repo = dequeue(); if expanded(repo): continue
    profile = attribution(repo)
    refs = extractors(repo)
    for env in environments:
        for ref in refs.consumer_refs:
            value = acquire(ref, repo, env)                  # §9 ladder
            for cand in reverse_index.lookup(value, env):    # §8
                edge = DEPENDS_ON(repo → cand.repo, env,
                                  provenance=declared|injected,
                                  confidence=min(profile.conf, score(ref, cand)),
                                  evidence=[ref.evidence, cand.evidence, value.rung])
                persist(edge); if not expanded(cand.repo): enqueue(cand.repo)
    mark expanded(repo)
```

Cycles handled via the `expanded` set (edges still recorded); per-environment inner loop; confidence inherits the weakest link; traversal anchor-bounded while the index is global.

---

## 11. Telemetry cross-validation (optional plane)

A `TelemetryProvider` is **probed** for capabilities, then used to overlay observed edges and reconcile, per env:

| Case | Meaning | Action |
|---|---|---|
| Static ∩ Runtime | declared & observed | promote to highest confidence |
| Static − Runtime | declared, not observed | cold path (tag `not-observed`) or stale dependency (flag) |
| Runtime − Static | observed, not declared | dynamic/hidden dependency static missed → add (`provenance=observed`) + flag |

The third row **fills the secret floor at the edge level without reading a secret**. Capability ordering by typical availability: **logs (near-universal) ≥ APM ≥ RUM ≫ deploy-events**. Degrade: service-dependency graph → derive from traces → mine from logs → contribute nothing (static stands alone). RUM, where present, catches browser/composition edges backend tracing misses. The static-vs-runtime **divergence report** is a first-class deliverable. Telemetry contributes *edges and resolution hints*, never *token values* — it is not a ladder rung.

---

## 12. Intra-repo boundary

Tendril owns inter-repo/per-env edges; intra-repo structure is delegated. Each `Repo` carries `HAS_INTERNAL_GRAPH {tool, locator}`. Agent flow: query Tendril for "anchor `DEPENDS_ON` billing @prod via `/charges`" → follow the handoff into the repo's intra-repo graph (RepoWise/CodeGraph) to find the handler. The inter-repo edge lands on the repo boundary; the intra-repo tool resolves below it. No duplication.

---

## 13. Graph store & agent surface

**Store:** a property graph (embedded **Kùzu** for low-ops, or **Neo4j**) behind the `GraphStore` plugin; schema §2 maps 1:1.

**Query layer + MCP server.** Tendril exposes its own MCP server for agents (alongside the platforms' MCPs). Tools:
- `find_relevant_repos(task_or_seeds, env?, max_hops?, min_confidence?) → ranked repos + why`
- `impact_analysis(repo|endpoint, env, min_confidence?) → downstream consumers + evidence`
- `dependency_path(from, to, env) → path with per-edge confidence`
- `env_diff(repo, env_a, env_b) → added/removed/changed edges`
- `explain_edge(edge_id) → full evidence + provenance chain`

Every response carries confidence and provenance (`declared`/`injected`/`observed`) so agents filter and weight accordingly.

---

## 14. Incremental updates, freshness, security

- **Incremental.** VCS `push` → re-extract that repo, re-resolve its outbound edges and any provider identities it changed (may invalidate others' inbound edges). CI/CD change → re-evaluate affected deployables/envs. Scoped invalidation, not global rebuild. Per-node `last_indexed_ref`/`last_seen`.
- **Security.** Read-only per-provider credentials from a central broker, short TTL, rotation, read audit across all systems. **Secret redaction before persistence** — store `{is_secret, resolved:bool}`, never values. The graph itself is sensitive (estate topology) — access-control the query layer and MCP.

---

## 15. Worked example (illustrative of the mechanism)

> Stack is illustrative, not assumed — it exercises every hard case at once.

`webpage-solution` (anchor; `/home.aspx` hosts `<iframe src="{landing-page-url}/dashboard-ui">`, token declared in `web.config`) → composition extractor records the iframe ref + token decl → attribution finds the deploy owner for the env → acquisition ladder resolves `landing-page-url` per env (e.g. Octopus var set or a GitHub Environment variable) to `https://d-ui.prod.example.com` → reverse index holds that host as a provider identity of repo **`landing-page-ui`** (from *its* deploy config) → resolver joins → `webpage-solution —DEPENDS_ON@prod→ landing-page-ui` (via iframe, high confidence, full evidence) → recurse: `landing-page-ui` consumes the BFF base URL → resolves to **`landing-page-api`**. Five naive shortcuts each fail here: name-matching (repo ≠ path ≠ host), literal-config (it's a token), code-only extraction (it's in markup), single-env (hosts differ per env), anchor-only crawl (provider identity lives in the *other* repo). If telemetry is present, APM confirms `landing-page-ui → landing-page-api`; RUM (if on) can confirm the iframe edge.

---

## 16. Open questions

1. **Deploy-step detection coverage** — maintain a catalog of deploy-action signatures; unknown mechanisms degrade to "build owner only." Maintenance vs. flag-and-review policy.
2. **Octopus without Config-as-Code** — repo→project link is indirect (artifact provenance); confirm reliability or require a mapping table.
3. **Environment-name canonicalization** across providers (GitHub Environments / Octopus Environments / CircleCI contexts / TeamCity params / Bitbucket Deployments) — a canonical environment dictionary is a hard dependency of the resolver.
4. **Identity collisions** (blue/green, shared gateway) — one identity, multiple owners, or distinct?
5. **Graph store default** — Kùzu (embedded, low-ops) vs. Neo4j (tooling). Lean embedded unless concurrency demands otherwise.
6. **Async edges** (queue/topic) — phase in v1 or later? Often the *missed* dependencies.
7. **Confidence calibration** — needs a hand-labeled golden estate; telemetry provides a partial golden source.
8. **Plugin ABI language** — settle the reference language (Python vs. TypeScript) for the conformance suite and the first community providers.
