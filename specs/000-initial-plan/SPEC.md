# Tendril-Graph — Technical Specification

*Consolidated technical spec. Companion to `PRD.md`. Covers architecture, the provider plugin contract, the resolution pipeline, the graph model, telemetry cross-validation, and the agent surface. Concrete platforms/languages are reference implementations behind the plugin contract (§4).*

**Status:** Draft v1.0

---

## 1. Architecture overview

Tendril-Graph reconstructs the inter-repo dependency graph from three data planes, with everything platform-specific behind a plugin boundary.

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

**Resolve at the deployed ref, not `main`.** For each environment, config is read from the **exact SHA/branch actually deployed there** — obtained from the deploy plane (the Octopus deployment's release → build → VCS ref) — not from the default branch. The default branch is not what's running; a prod graph built from `HEAD` is subtly wrong wherever prod runs an older ref. The deployed ref is recorded on every edge as evidence. This makes the deploy plane (deploy events / deployed SHA) a *required* truth source, distinct from optional runtime telemetry.

> **v0 reference target & build principle.** The first implementation targets a real, harder-than-cheapest slice: an ASP.NET WebForms (VB + C#) + Angular solution, **built in TeamCity, deployed via Octopus, stored in Bitbucket, with associated repos across both Bitbucket and GitHub.** v0 stands up all seven provider interfaces (§4) as real contracts with **minimal implementations**, so dataflow analysis, LLM judgment, and further providers are added *behind existing seams* — additive, never a core rewrite. Thin but correctly seamed.

---

## 2. Domain model (graph schema)

**Nodes:** `Repo`, `Deployable` (produced_by Repo; kind web/api/job/ui/bff), `Environment` (with provenance), `Endpoint` (scheme/host/port/path_base), `Pipeline`, `CICDProvider` (system, role[]), `VariableStore` (kind, scopes, readable), `ServiceIdentity` (canonical + aliases), `ConfigVar`, `MessageChannel` (queue/topic), `DeployedRef` (sha, branch, env, deployable_id, deploy_timestamp, source).

> **v0 note (C3):** In v0, each repo produces a single `Deployable` by default (1:1 Repo:Deployable). Multi-deployable repos (e.g. a solution with a web app + background job) are flagged for manual review; the CI/CD profile is the signal — Octopus projects map naturally to Deployables. A future `deployables(repo_ir) -> Deployable[]` method on `ExtractorPlugin` will generalize this without a core change.

**Edges** (environment-scoped; carry `provenance`, `confidence`, `evidence`, `discovered_at`):

| Edge | Meaning |
|---|---|
| `Repo —PRODUCES→ Deployable` | a repo builds deployables |
| `Deployable —EXPOSES→ Endpoint @env` | provider projection |
| `Deployable —CONSUMES→ Endpoint @env` | consumer projection |
| `Endpoint —RESOLVES_TO→ Deployable @env` | the join result |
| `Deployable —DEPENDS_ON→ Deployable @env` | the materialized edge agents query |
| `Deployable —DEPLOYED_AS→ DeployedRef @env` | deployed SHA per env (queryable) |
| `Repo —BUILT_BY→ CICDProvider` / `—DEPLOYED_BY→ CICDProvider @env` | attribution (§7) |
| `CICDProvider —RESOLVES_VARS_FROM→ VariableStore` | where values come from |
| `Pipeline —BUILDS→ Repo` / `—DEPLOYS→ Deployable @env` | CI/CD wiring |
| `ConfigVar —INJECTED_INTO→ Deployable @env` | injection provenance |
| `Deployable —PUBLISHES/SUBSCRIBES→ MessageChannel @env` | async dependency |
| `Repo —HAS_INTERNAL_GRAPH→ {tool,locator}` | intra-repo handoff (§12) |

**Provenance dimension** on edges: `declared` (static source), `injected` (CI/CD-resolved), `observed` (runtime telemetry). An edge may carry several; cross-plane agreement multiplies confidence. `DEPENDS_ON` derives from a `CONSUMES → RESOLVES_TO → EXPOSES` triangle and inherits the weakest confidence in the chain.

> **v0 note (M3):** In v0, `DEPENDS_ON` is the primary materialized edge that agents query. `EXPOSES`/`CONSUMES`/`RESOLVES_TO` edges are created as intermediate artifacts during resolution but their persistence is optional — they are most useful for `explain_edge`. The `Endpoint` node is created when a consumer ref or provider identity resolves to a concrete URL/host; it is the evidence chain, not the primary query surface.

> **L1 clarification:** `ConfigVar` nodes are persisted `TokenDecl` records. The `INJECTED_INTO` edge is created when a token resolves against a variable store during the acquisition ladder (§9).

---

## 3. Canonical Service Identity & alias resolution

A service is known by many names; matching on any one is brittle. A canonical `ServiceIdentity` carries aliases across identity **classes**: network (host/URL per env), logical (service/app names), deploy (Octopus project, TeamCity build-config id, slot/role), artifact (NuGet/npm/image id), async (queue/topic), data (DB schema/connection). A normalizer canonicalizes raw references (case-fold, strip env suffixes, expand abbreviations, map host↔service via DNS/ingress). Match confidence by class: exact deploy-target/artifact or exact host/URL (post env-resolution) → **high**; normalized logical-name → **medium**; fuzzy logical/data → **low** (candidate, needs review). Colliding aliases emit *both* candidates; ambiguity is surfaced, never auto-resolved.

> **H1 clarification:** `ProviderIdentity` is the raw extraction output (per-repo, per-extractor). During global indexing, `ProviderIdentity` records are canonicalized and merged into `ServiceIdentity` nodes using the alias resolution rules above. Conflicts (two repos claim the same host) produce two linked nodes with `ambiguous: true`. In v0, this canonicalization is performed in-memory by the `ReverseIndex` during traversal; `ServiceIdentity` nodes are persisted to the graph store for querying. The reverse index is keyed by `ServiceIdentity`, not raw `ProviderIdentity`.

---

## 4. The Provider Plugin Contract (FR-17)

The extensibility core. **Seven plugin families** (five structural, plus an `IntraRepoProvider` for dataflow facts (§4.8) and an `LLMProvider` for grounded judgment (§4.7)) behind stable, **semantically versioned** interfaces, a normalized IR, capability declaration, registration/discovery, and a **conformance suite** every plugin must pass. A third party adds a provider without modifying core. Interfaces below are language-neutral pseudocode; the reference implementation language (e.g. Python or TypeScript) defines the concrete ABI.

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

**Deployable node creation (C3).** `Deployable` nodes are not self-describing — they are produced by the attribution engine combining VCS and CI/CD data. The creation rule: for each `PipelineBinding` returned by `discover_for_repo()` that carries `roles=[deploy]` or `roles=[build, deploy]`, the attribution engine creates a `Deployable` node keyed as `{vcs_provider}:{org}/{repo}#{pipeline_id}`. In v0, when a repo has exactly one deploy binding (the common case), the `#pipeline_id` suffix is omitted and the Deployable id matches the Repo id, giving the 1:1 default. When multiple deploy bindings exist (multi-target), each gets its own Deployable and the repo is flagged. `read_provider_identities()` populates the provider projection of each Deployable; the Deployable node must exist before those identities can be indexed.

### 4.4 `ExtractorPlugin` (language/framework)

```
id() -> string                                   # "dotnet"|"jsts"|"iac"|"composition"|...
matches(repo_ir) -> bool                          # does this repo contain my ecosystem?
extract(repo_ir) -> {
    consumer_refs: ConsumerRef[],
    provider_identities: ProviderIdentity[],
    token_decls: TokenDecl[]
}
# v1+: deployables(repo_ir) -> Deployable[]      # multi-deployable repos; default: 1:1 Repo:Deployable
```
Extractors **locate and classify; never resolve.** Multiple extractors may match one repo; results are merged.

> **v0 note (C3):** In v0, `deployables()` is not required — the system defaults to one `Deployable` per `Repo`. When the CI/CD profile indicates multiple deploy targets (e.g. separate Octopus projects from the same repo), the repo is flagged `multi-deployable` for human review. The `deployables()` method is planned for v1 without requiring a core change.

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

### 4.7 `LLMProvider` (judgment, grounded — §15)

```
id() -> string                                   # "openai-compatible" | "bedrock" | "ollama" | ...
capabilities() -> Capabilities                    # { structured_output, tool_calls, max_context }
complete(req: LLMRequest) -> LLMResponse          # base_url, model, api_key all config (BYOK); temp 0 default
```
`LLMRequest` carries a decision-type goal, a required output schema, the **redacted** evidence, and a grounded read-only tool set. The provider is gateway-agnostic; routing/tiering/residency live in core config, not the plugin. Output is always **grounded** (§15.3) before use — the provider never writes to the graph.

### 4.8 `IntraRepoProvider` (dataflow facts — §6, §12)

Supplies the intra-repo static-analysis facts the resolver and LLM ground on: def-use chains, a reference's resolved value or value-set, dataflow paths, and the call graph. **Not a hard dependency** — satisfied three ways: *self-provide* (bundled engine), *reuse/adapt* (consume an existing tool's output), or *absent → degrade* (format-parser extraction + grounded LLM, lower confidence on computed values).

```
id() -> string                                   # "roslyn" | "joern" | "codegraph-adapter" | "repowise-adapter" | ...
capabilities() -> Capabilities                    # { languages[], def_use, dataflow, interprocedural, cross_file }
analyze(repo_ir) -> IntraRepoFacts                # def-use, value-sets, dataflow paths, call graph
resolve_value(reference) -> ResolvedValue | ValueSet | Unresolved   # backtrack a ref to its computed value(s)
```

Reference adapters: **Roslyn** (.NET, MIT, first-class C#/VB) and **Joern** (Apache-2.0 CPG, cross-language) for self-provide; **CodeGraph / RepoWise / CodeQL-DB** adapters for reuse. License/coverage trade-offs and the engine-selection rubric: §17.9 and `prompt.md`.

### 4.9 Registration, capability negotiation, versioning, conformance

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
- **TeamCity (CI/CD).** Access token; REST at `/app/rest`. Read build configs/templates, parameters, **VCS roots** (the link to the repo), snapshot/artifact deps. Native webhooks for build events. Built-in MCP (2026.1) + community server. **CVE version check (L2):** on connector initialization, read server version from `GET /app/rest/server` and compare against a documented minimum (maintained in `data/deploy_step_signatures.yaml`). If below minimum, emit a `cicd-version-warning` on the provider node and log a human-readable advisory — the run continues; this is never a hard failure. Unreadable version → `cicd-version-unknown` flag only.
- **GitHub Actions (CI/CD, intrinsic).** Rides the GitHub credential. Detect via `.github/workflows/*.yml`. **GitHub Environments are a native, readable per-env scoping source** (`vars.*` readable; `secrets.*` names only; env-scoped values override repo-level when a job sets `environment:`).
- **Bitbucket Pipelines (CI/CD, intrinsic).** Rides the Bitbucket credential. Detect via `bitbucket-pipelines.yml`. Repo/workspace/deployment variables (secured masked); Bitbucket Deployments as the env construct.

**Build-vs-buy on MCP.** Use each platform's **official MCP for the agent/diagnostic path**; build **typed REST connectors for the deterministic bulk index** (pagination, backoff, redaction, reproducibility). Both share the brokered credentials.

---

## 6. Extractor reference implementations

Extraction spans a **spectrum of static analysis**, not just config parsing. From cheapest to most capable: format parsers (literal config) → **AST parsing** (Roslyn for .NET, tree-sitter elsewhere) → **def-use / symbol resolution** (backtrack a reference to its definition) → **data-flow / taint analysis with constant propagation** (follow a value through computation; fold constant-derived strings) → **abstract interpretation** (enumerate the *set* of possible values under branching, e.g. `region=="eu" ? euUrl : usUrl` → `{euUrl, usUrl}`, often tying each branch to its environment condition). Reuse a code-property-graph engine (CodeQL / Semgrep dataflow / Joern) rather than building one per language.

**The ceiling (be honest about it):** exact value recovery across arbitrary code is undecidable (Rice's theorem), so this layer is always an approximation. It **cannot** resolve dynamic/external values (DB-sourced, reflection, DI-by-convention, `$(external-command)` output), cross-language/cross-process value flow, or *intent* (is this string a dependency or a log URL?). Those cases escalate to grounded LLM judgment (§15) or are observed via the acquisition ladder (§9). **Per-repo backtracking is intra-repo dataflow and is consumed across the §12 boundary**, not reimplemented here; this layer focuses on what crosses the repo edge.

Per-ecosystem plugins producing consumer/provider/token projections:

- **Composition (view-layer, FR-13).** Scans `.aspx`/`.ascx`/`.master`/`.cshtml`/`.razor`/`.html` and proxy/rewrite config (`web.config <rewrite>`, IIS URL Rewrite, BFF proxies) for `iframe src`, `script/link src/href`, importmaps/Module-Federation remotes, and config attributes carrying base URLs. Runs placeholder detection (`{t}`, `#{t}`, `${t}`, `%(t)%`, `<%$ %>`) and records a pointer to each token's declaration. Locate-and-classify only.
- **.NET.** `appsettings.*`, `web.config` + transforms, `HttpClient` base addresses, connection strings, `csproj`/NuGet refs, WCF endpoints.
- **JS/TS.** `.env*`, `next/vite/webpack` env injection, `package.json` deps, API-client base URLs, dev-proxy configs.
- **IaC/deploy.** Helm `values.{env}.yaml`, k8s Services/Ingress (provider endpoints), Terraform, ARM/Bicep, Dockerfiles (image identity).
- **(Community) Java/Spring, Python, Go, etc.** Same interface; contributable.

---

## 7. CI/CD Attribution engine

CI/CD is **per-repo and heterogeneous**; the resolver can't pick a variable store until it knows which system deploys *this* repo to *this* env. Attribution runs **between extraction and resolution**.

**Evidence, two directions.** *Intrinsic:* detector files (`.github/workflows/`, `.circleci/config.yml`, `bitbucket-pipelines.yml`, `.teamcity/` Kotlin DSL, `.octopus/*.ocl` Config-as-Code, `azure-pipelines.yml`, `Jenkinsfile`) and **deploy-step detection inside a build workflow** — the key heuristic for chaining. *Extrinsic:* platform→repo mappings (TeamCity VCS roots, CircleCI project⇄repo, Octopus Config-as-Code git connection or artifact provenance).

**Deploy-step signature catalog (C4).** Deploy-step detection is driven by a versioned data file `data/deploy_step_signatures.yaml` — not embedded in code. Each entry has the schema:
```yaml
- provider_id: octopus          # which CI/CD provider owns the deploy step
  match_type: action_id         # action_id | task_type | step_name_pattern
  pattern: "OctopusDeploy/*"    # matched against the workflow step
  env_extraction_hint: environment  # field/key that names the target env, if present
```
The catalog covers common deploy mechanisms (`OctopusDeploy/*` actions, `aws deploy`, `helm upgrade`, `kubectl apply`, Terraform `apply`, TeamCity Octopus deploy runner, Bitbucket Pipelines deployment steps). When a workflow step matches an entry, the named provider is attributed as deploy owner; the `env_extraction_hint` is used to extract the target environment from the step config. **Unknown mechanism** (no catalog match): attribute the build owner as the sole owner, set `deploy_owner_confidence=low`, and emit an `unattributed-deploy` flag on the profile — the run continues.

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

1. **Static config in repo** — literal values committed in `appsettings.*`/`values.{env}.yaml`/`.env`. Read at the **deployed ref** (the SHA obtained from the deploy plane), never at `HEAD`/`main` (FR-24).
2. **CI/CD variable store API** — read value + apply the store's scoping (Octopus scope match, GitHub Environment override, TeamCity inheritance, CircleCI context binding, Bitbucket deployment scope).
3. **Effective-value / preview API** — read the value *as the platform resolved it* (e.g. Octopus variable preview). Cleanest; avoids re-emulating scoping.
4. **Deploy-log harvesting** — parse deploy/build logs for the **effective non-secret values actually injected**, per env. Ground truth of what shipped; carries a run-id/freshness qualifier.
5. **Browser fallback (Playwright)** — *(v1+, deferred from v0)* Inverts the read-only/least-priv security posture; gated: non-secret only, self-hosted only, last resort, dedicated low-priv account, isolated context, never on the bulk path, medium-at-best confidence. Requires a security review gate before enabling.
6. **Runtime introspection (optional)** — query a deployed service's effective config; validation-grade.

**Secret floor.** Secret-typed values are masked in the UI, the API, **and logs** — so no rung recovers them. A genuinely secret-hidden value is emitted as `unresolved-secret` + evidence, for human review or runtime cross-fill (§11). Prefer rungs 3–4 ("let the platform resolve, read the answer") over re-emulating scoping or driving a browser.

**Logic-based pipelines.** Build/deploy pipelines that compute parameters via embedded shell/PowerShell/Groovy with conditionals, loops, or `$(external-command)` output are **not statically evaluated** — that is undecidable in the general case. They resolve via rungs 3–4 (preview API / deploy-log harvest = read the value the pipeline actually emitted), or, for the declarative/constant-folded portions, via §6 analysis. Imperative pipeline logic is an *observe-the-result* problem, not a *static-evaluation* problem.

```
# C1 fix: ref parameter threads the deployed SHA through source reads (FR-24)
acquire(T, repo R, env E, ref: str | None):
    for rung in [static, store_api, preview_api, deploy_log, runtime]:
        # Rung 1 (static): read_file(repo, ref, path) — uses deployed ref, not HEAD
        if rung == static: v = rung.try(T, R, ref)
        else:              v = rung.try(T, R, E)
        if v concrete: return (v, rung, evidence)
    # Rung 5 (browser): deferred to v1+ — see note above
    return (UNRESOLVED_SECRET if T.is_secret else UNRESOLVED_NO_SOURCE)
```

---

## 10. Traversal engine

```
# H2 fix: explicit mode dispatch; structured-mode pseudocode below
evaluate_node(repo, env, mode):
    if mode == "structured":  # deterministic fast path
        profile = attribution(repo)
        refs = extractors(repo)
        deployed_ref = deploy_plane.resolve_ref(profile, env)   # FR-24
        for consumer_ref in refs.consumer_refs:
            value = acquire(consumer_ref.token, repo, env, ref=deployed_ref)   # §9
            candidates = reverse_index.lookup(value, env)                       # §8
            # H5 fix: enqueue ALL candidates; ambiguous=True when len > 1
            ambiguous = len(candidates) > 1
            for cand in candidates:
                edge = DEPENDS_ON(repo → cand.repo, env,
                                  provenance = declared|injected,
                                  confidence = min(profile.conf, score(consumer_ref, cand)),
                                  evidence   = [consumer_ref.evidence, cand.evidence, value.rung],
                                  ambiguous  = ambiguous,
                                  candidates = [c.repo for c in candidates] if ambiguous else [])
                persist(edge)
                if not expanded(cand.repo): enqueue(cand.repo)

    if mode in ("hybrid", "agentic"):  # §15 LLM evaluation loop
        # See §15.2 — LLM proposes, grounding validates
        # structured fast-path runs first in hybrid; LLM handles unresolved/ambiguous only

seed queue with anchor repo
while queue not empty:
    repo = dequeue(); if expanded(repo): continue
    for env in environments:
        evaluate_node(repo, env, mode)
    mark expanded(repo)
```

Cycles handled via the `expanded` set (edges still recorded); per-environment inner loop; confidence inherits the weakest link; traversal anchor-bounded while the index is global.

The structured-mode path above is the v0 default. In **hybrid mode** (the eventual default per §15.1), the structured path runs first as a fast path; the LLM evaluation loop (§15.2) handles only the unresolved and ambiguous results. In **agentic mode**, the LLM evaluates each node across all evidence. The deterministic extractors, index, and acquisition ladder become the *tools the loop calls* and the *grounding that verifies it*. See §15.

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

Tendril-Graph owns inter-repo/per-env edges; intra-repo structure is delegated to an **`IntraRepoProvider`** (§4.8). This includes **intra-repo def-use and dataflow** — backtracking a reference to its definition or computed value *within* a repo. The provider is **not a hard prerequisite**: Tendril-Graph can *self-provide* (run a bundled engine — Roslyn for .NET, Joern for cross-language), *reuse* an existing tool's output via an adapter (CodeGraph, RepoWise, CodeQL DB) to avoid double-analysis, or *degrade* when none is available (format-parser extraction + grounded LLM, at lower confidence on computed values). Tendril-Graph **consumes** these facts and does the inter-repo join + cross-boundary stitching, escalating to grounded LLM judgment (§15) where they run out. Each `Repo` carries `HAS_INTERNAL_GRAPH {tool, locator}`. Agent flow: query Tendril-Graph for "anchor `DEPENDS_ON` billing @prod via `/charges`" → follow the handoff into the repo's intra-repo graph to find the handler. The inter-repo edge lands on the repo boundary; the intra-repo provider resolves below it. No duplication.

---

## 13. Graph store & agent surface

**Store:** a property graph (embedded **Kùzu** for low-ops, or **Neo4j**) behind the `GraphStore` plugin; schema §2 maps 1:1.

**Query layer + MCP server.** Tendril-Graph exposes its own MCP server for agents (alongside the platforms' MCPs). Tools:
- `find_relevant_repos(task_or_seeds, env?, max_hops?, min_confidence?) → ranked repos + why`
- `impact_analysis(repo|endpoint, env, min_confidence?) → downstream consumers + evidence`
- `dependency_path(from, to, env) → path with per-edge confidence`
- `env_diff(repo, env_a, env_b) → added/removed/changed edges`
- `explain_edge(edge_id) → full evidence + provenance chain`

Every response carries confidence and provenance (`declared`/`injected`/`observed`/`llm-judged`), **the deployed ref it was computed from**, and an explicit **unknowns** section — unresolved references, ungrounded candidates, and coverage gaps for the queried scope. A consumer must be able to distinguish *"no dependency"* from *"could not determine"*; the contract never implies completeness it doesn't have. Queries accept a `min_confidence` filter, and `impact_analysis` defaults to **recall-favoring** behavior (a missed downstream consumer is more dangerous than a flagged unknown) — it returns the unknowns alongside the resolved set rather than silently omitting them.

---

## 14. Incremental updates, freshness, security

- **Incremental.** VCS `push` → re-extract that repo, re-resolve its outbound edges and any provider identities it changed (may invalidate others' inbound edges). CI/CD change → re-evaluate affected deployables/envs. Scoped invalidation, not global rebuild. Per-node `last_indexed_ref`/`last_seen`.

  **Scoped invalidation via `resolved_via` index (H4).** Each `DEPENDS_ON` edge stores a `resolved_via` list — the ids of the `ServiceIdentity` nodes whose reverse-index entries produced the match. On any provider-identity change (a `ServiceIdentity` is updated or removed), only edges whose `resolved_via` includes that identity are marked `stale: true`; they are not deleted. On the next traversal pass, stale edges are re-resolved: if they still hold they are cleared; if not they are removed. This bounds invalidation to the affected edges — a provider-identity change never triggers a full graph scan. New edges from the re-resolution pass inherit fresh `resolved_via` pointers.
- **Security.** Read-only per-provider credentials from a central broker, short TTL, rotation, read audit across all systems. **Secret redaction before persistence** — store `{is_secret, resolved:bool}`, never values. The graph itself is sensitive (estate topology) — access-control the query layer and MCP.

---

## 15. LLM judgment & the evaluation loop (grounded, BYOK)

The decisions at the heart of construction — *interpret a repo to find everything it reaches outside itself; decide whether a reference matches a provider; decide what to evaluate next* — are judgment, not pattern-matching. Tendril-Graph treats them as **LLM-driven, grounded by deterministic verification**. The split: **the LLM supplies judgment and interpretation; deterministic tools supply grounding, resolution, and bookkeeping.** The LLM proposes; the tools confirm; nothing ungrounded is trusted.

### 15.1 Run modes

- **structured** — deterministic static analysis only (AST + def-use + dataflow + abstract interpretation, §6). Cheap, fully reproducible, and genuinely capable on backtracking, value-flow, and branch enumeration — but **bounded by the §6 ceiling** (no dynamic/external values, no cross-language/cross-process stitching, no intent classification). Good for clean codebases and reproducibility-critical runs; not a full substitute on a messy estate.
- **agentic** — an LLM evaluates each node across all evidence; highest recall on messy/heterogeneous estates.
- **hybrid (default)** — deterministic extractors fast-path the structured majority; the LLM handles interpretation of unstructured config, ambiguous matches, and the traversal-frontier decision. Configurable per run and per repo.

### 15.2 The evaluation loop (per node)

At each repo the agent receives the repo's evidence (source/API calls, configs, build, CI/CD, hosting) and **read-only, grounded tools**, and pursues three prompt goals: (1) **enumerate outward references** — every API, host, queue, service, or artifact the repo reaches outside itself, each with an evidence locator; (2) **resolve/ground each** to a provider repo via tools, or mark unresolved; (3) **propose the frontier** — which discovered repos to evaluate next.

**Evidence budget (M1).** Evidence is gathered within a per-call budget to control cost and context window usage: `max_files=20, max_bytes=50_000` (both configurable). Priority order for evidence selection within the budget: (1) CI/CD profile + attribution facts, (2) extractor output (consumer refs, provider identities, token decls), (3) deploy config and variable store contents (non-secret), (4) the N most-relevant source files ranked by extractor confidence. All selected evidence passes through the §15.5 pre-hook (redaction + residency gate) before any model call. If the budget is exceeded, lower-priority items are truncated; the model receives a `budget_truncated: true` flag in its context so it can abstain rather than guess on missing evidence.

```
evaluate(repo, env):
    evidence = gather(repo)                      # files, build, CI/CD, hosting (via connectors)
    proposal = LLM.judge(goal=EVALUATE_REPO, evidence,
                         tools=[index.lookup, acquire, get_context, list_envs])
    for cand in proposal.references:
        target = ground(cand)                    # verify against reverse index / connectors
        if target.grounded:
            edge(repo → target, env,
                 provenance = (declared|injected) + llm-judged,
                 confidence = match_class(target),         # grounded → real confidence
                 evidence   = [cand.evidence, target.evidence, llm.trace_id])
        else:
            flag(cand, UNRESOLVED, confidence=low)         # ungrounded → low + flagged
    enqueue(proposal.frontier ∩ grounded_targets)
```

### 15.3 Grounding is the trust anchor

A proposed edge is promoted only when it **grounds**: the proposed provider identity actually exists in the reverse index (or a connector confirms the deploy target/host) and the evidence locator resolves. Grounded → confidence by identity class (§3); ungrounded → low confidence, flagged, never silently kept. This is what stops LLM judgment from hallucinating edges — **judgment is the model's; truth is the index's.**

### 15.4 BYOK, models, and locations (`LLMProvider`, §4.7)

LLM access is a plugin, **OpenAI-compatible-gateway-first** — `base_url`, `model`, and `api_key` are all config, so it drives LiteLLM, vLLM, Ollama, Azure/Bedrock-via-gateway, or a frontier API equally. The router supports **per-decision model tiering** (cheap/local for env-name canonicalization; stronger for identity arbitration and whole-repo evaluation), **data-residency routing** (source-reading tasks pin to in-VPC/self-hosted endpoints; nothing forces proprietary source to a third-party API), and **BYOK** brokered like every other credential. **structured mode runs with no LLM at all** for adopters who can't or won't.

### 15.5 Tools, hooks, and prompt contracts

Every LLM call is wrapped: a **pre-hook** (redaction + residency gate — strip secret-typed values, refuse non-approved endpoints for sensitive tasks); **grounded read-only tools** (`reverse_index.lookup`, `get_context`, `acquire`, `list_environments`) so the model retrieves rather than guesses; a **prompt goal** per decision type (a narrow contract: the task, a required JSON output schema, an explicit *abstain-if-unsure* rule); a **post-hook** (grounding/validation before anything is recorded); and **caching + recorded reasoning** (temperature 0; prompt + response + grounding outcome recorded as the edge's evidence).

### 15.6 Reproducibility & auditability under judgment

Pure determinism is not claimed once judgment is in the loop, but reproducibility and auditability are preserved: **temperature 0 + caching** make re-runs reproduce from recorded decisions; **recorded reasoning traces + grounding evidence** make every edge explain itself; **provenance** marks LLM-influenced edges `llm-judged` and caps their confidence unless grounded. An auditor sees what the model proposed, what grounded it, and why it was (or wasn't) trusted. (This is the basis for the revised NFR-5 in `PRD.md`: "reproducible and grounded," not "purely deterministic.")

### 15.7 Evidence retrieval (the model pulls facts, it isn't handed the repo)

The agent does **not** ingest whole repos into context — that doesn't scale and breaks residency/cost. It **pulls** evidence through tools: read this config file, fetch this CI/CD step, and — critically — **request the §6 dataflow facts** for a reference (its def-use chain, its resolved value or value-set, its branch conditions) from the intra-repo graph (§12). So the model reasons over *program-analysis facts*, not raw source: this grounds it (the facts are deterministically derived), shrinks its job (it judges intent and stitches boundaries rather than re-deriving value flow), and bounds what proprietary code ever reaches a model (residency). The division of labor: **dataflow says what a value *is*; the model says what it *means* and what to do next.**

## 16. Worked example (illustrative of the mechanism)

> Stack is illustrative, not assumed — it exercises every hard case at once.

`webpage-solution` (anchor; `/home.aspx` hosts `<iframe src="{landing-page-url}/dashboard-ui">`, token declared in `web.config`) → composition extractor records the iframe ref + token decl → attribution finds the deploy owner for the env → acquisition ladder resolves `landing-page-url` per env (e.g. Octopus var set or a GitHub Environment variable) to `https://d-ui.prod.example.com` → reverse index holds that host as a provider identity of repo **`landing-page-ui`** (from *its* deploy config) → resolver joins → `webpage-solution —DEPENDS_ON@prod→ landing-page-ui` (via iframe, high confidence, full evidence) → recurse: `landing-page-ui` consumes the BFF base URL → resolves to **`landing-page-api`**. Five naive shortcuts each fail here: name-matching (repo ≠ path ≠ host), literal-config (it's a token), code-only extraction (it's in markup), single-env (hosts differ per env), anchor-only crawl (provider identity lives in the *other* repo). If telemetry is present, APM confirms `landing-page-ui → landing-page-api`; RUM (if on) can confirm the iframe edge.

---

## 17. Open questions

1. **Deploy-step detection coverage** — maintain a catalog of deploy-action signatures; unknown mechanisms degrade to "build owner only." Maintenance vs. flag-and-review policy.
2. **Octopus without Config-as-Code** — repo→project link is indirect (artifact provenance); confirm reliability or require a mapping table.
3. ~~**Environment-name canonicalization**~~ **RESOLVED (v0).** Implemented as `EnvironmentCanonicalizer` (case-fold + configurable alias table in `data/environments_default.yaml`). Unmatched names → `raw-name` + low-confidence, never a failure. The canonicalizer is injected into both the traversal engine and the deployed-ref resolver so that provider env names (e.g. Octopus "Production") match canonical forms (e.g. "prod") transparently.
4. **Identity collisions** (blue/green, shared gateway) — one identity, multiple owners, or distinct?
5. **Graph store default** — Kùzu (embedded, low-ops) vs. Neo4j (tooling). Lean embedded unless concurrency demands otherwise.
6. **Async edges** (queue/topic) — phase in v1 or later? Often the *missed* dependencies.
7. **Confidence calibration** — needs a hand-labeled golden estate; telemetry provides a partial golden source.
8. ~~**Plugin ABI language**~~ **RESOLVED (v0).** Reference implementation language: **Python 3.12+** (Kùzu/LiteLLM/pytest first-class; `importlib.metadata` for plugin discovery). Non-Python plugins use subprocess JSON-RPC (`tendril-rpc/v1`) over stdin/stdout — newline-delimited JSON, no external transport. Plugin ABI: Python ABCs (`tendril/plugins/base.py`) + `tendril-plugin.toml` manifest. In-process for Python; subprocess bridge (`tendril/plugins/subprocess_bridge.py`) for other languages.
9. **Dataflow/CPG engine (`IntraRepoProvider`)** — reuse vs. build, with license as the hard gate (must run on adopters' proprietary code). Grounded findings: **CodeQL** has deep dataflow but its engine **cannot run on closed-source code without a paid GitHub Advanced Security license** → excluded as a bundled default. **Joern** is Apache-2.0 and CPG-based but **C#/.NET is not first-class** (core: C/C++/Java/JS/Python/Kotlin). **Roslyn** (MIT) is the natural .NET engine. **Semgrep CE** is LGPL-2.1 but **intraprocedural only** (cross-file dataflow is Pro/paid, or the Opengrep fork). Likely answer: Roslyn (.NET) + Joern (cross-language) behind the provider, with reuse-adapters for existing tools and a degrade path. Full rubric in `prompt.md`.
10. **Cross-language / cross-process stitching** — value flow that crosses a shell→.NET→JS boundary is the hard residue no single dataflow engine covers. Confirm the approach: grounded LLM stitching over per-language facts, runtime observation (telemetry/logs), or both, with explicit confidence penalties for stitched edges.
