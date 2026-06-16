<div align="center">

# 🌱 Tendril-Graph

**Trace the tendrils between your repos.**

Tendril-Graph reconstructs the cross-repo dependency graph of a multi-repo estate — the wiring that connects micro-UIs, backends-for-frontends, and services through configuration injected at build and deploy time — and serves it to coding agents and humans.

<!-- badges: build · coverage · license · npm/pypi — add on first release -->

[Requirements](specs/000-initial-plan/PRD.md) · [Spec](specs/000-initial-plan/SPEC.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [Previous Context](archive-context/*.md)

</div>

---

## What it is

Modern product lines span many repositories wired together not in code but in **configuration** — base URLs, service names, queue names — **injected at deploy time**, differently per environment. No single artifact says "repo A depends on repo B in production." Tendril-Graph reconstructs that graph **statically**, by reading source, build/deploy descriptors, and CI/CD variable stores, and optionally **cross-validates** it against runtime telemetry.

The mechanism in three sentences: every service has a **consumer projection** (the URLs and names it references — "I call X") and a **provider projection** (the identities it claims when it deploys — "I am reachable as Y"). Tendril-Graph builds a global index of every provider projection, then walks outward from an **anchor repo**, and an edge exists wherever a consumer reference matches a provider identity — scoped to an environment, carried with a confidence score and the evidence that produced it. Intra-repo structure is left to other tools; Tendril-Graph owns the **inter-repo, per-environment** layer and exposes it to coding agents (e.g. as the backbone for `find_relevant_repos()`).

> Everything platform-, language-, and vendor-specific is a **plugin behind a stable contract** — Tendril-Graph is general-purpose and community-extensible by design.

## Architecture

See **[docs/architecture.md](docs/architecture.md)** for the rendered diagram. Three data planes (source / build-deploy / runtime) feed a resolution pipeline behind a provider-plugin boundary, producing a confidence- and evidence-tagged graph served over an MCP query layer.

## v0 reference target

The first supported configuration is a real, non-trivial stack: an **ASP.NET WebForms (VB + C#) + Angular** solution, **built in TeamCity, deployed via Octopus, stored in Bitbucket, with associated repos across both Bitbucket and GitHub.** The quickstart and access notes below reflect that target. Other providers (GitHub Actions, CircleCI, Bitbucket Pipelines, additional telemetry) land later behind the same plugin contracts.

## Requirements

- **Python 3.12+** (the reference implementation language; see [CLAUDE.md](CLAUDE.md)).
- **Read-only** credentials for each enabled provider (next section).
- A graph store (embedded Kùzu by default; no external service required for v0).
- Network reachability to each provider's API endpoint (self-hosted TeamCity/Octopus/Bitbucket DC included).
- Optional: an OpenAI-compatible LLM endpoint and a telemetry provider — neither is required for v0.

## Getting access & keys

All credentials are **read-only and least-privilege**, supplied via environment variables or your secret broker — never committed. Per provider:

| Provider | Credential | Where to create it | Scopes required (read-only) | Env vars |
|---|---|---|---|---|
| **GitHub** | GitHub App *(preferred)* | Settings → Developer settings → GitHub Apps → New GitHub App. Set permissions, generate private key, install on target org(s). App ID is on the app settings page; Installation ID is in the install URL. | Contents: Read · Metadata: Read (+ Actions/Variables/Environments: Read for M7 GitHub Actions) | `GH_APP_ID`, `GH_INSTALL_ID`, `GH_PRIVATE_KEY_PATH` |
| **GitHub** | Fine-grained PAT *(single-org alternative)* | Settings → Developer settings → Personal access tokens → Fine-grained tokens → set Resource owner to the org | Contents: Read · Metadata: Read | `GH_TOKEN` |
| **Bitbucket Data Center** | HTTP access token | Profile icon → Manage account → Personal access tokens → Create token | Projects: Read · Repositories: Read | `BB_BASE_URL`, `BB_TOKEN` |
| **Bitbucket Cloud** | App password | Avatar (bottom-left) → Personal settings → App passwords → Create app password | Repositories: Read | `BB_CLOUD_USERNAME`, `BB_CLOUD_TOKEN` |
| **TeamCity** | Access token | Profile icon → Access Tokens → Create access token. Use a dedicated read-only service account. | Inherits account permissions — use an account scoped to View on build configs and VCS roots | `TC_BASE_URL`, `TC_TOKEN` |
| **Octopus Deploy** | API key | Profile icon → My API Keys → New API Key. Use a service account in the built-in "Octopus Readers" team. Space ID is in the URL when viewing a Space (e.g. `Spaces-1`). | Read on deployments, releases, projects, variable sets, targets | `OCTO_URL`, `OCTO_API_KEY`, `OCTO_SPACE` |
| **Datadog** *(optional)* | API key + App key | Organization settings → API Keys → New Key; Organization settings → Application Keys → New Key | App key scopes: `apm_service_catalog:read`, `metrics:read`, `logs:read` | `DD_API_KEY`, `DD_APP_KEY`, `DD_SITE` |
| **LLM** *(optional)* | BYOK — any OpenAI-compatible gateway | Your provider: OpenAI, Azure OpenAI, Ollama, LiteLLM, AWS Bedrock via gateway, etc. | n/a | `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` |

> See **[`.env.example`](.env.example)** for step-by-step instructions for each provider, including exact UI paths and recommended service account setup.

**Required access breadth:** read access must span **every org/workspace you want indexed** (Bitbucket workspaces *and* GitHub orgs), not just the anchor's — provider-identity indexing is global (see [SPEC §1.1](SPEC.md)). Confirm this access path early; it is often the longest lead-time item.

## Prerequisites & run order

- **Octopus deploy data must be reachable** so Tendril-Graph can resolve the **deployed SHA/branch per environment** and read config at that exact ref (not `main`). This is required, not optional.
- **Intra-repo analysis** (`IntraRepoProvider`) is **not required to run first** — Tendril-Graph self-provides (Roslyn for VB/C#, Joern for cross-language) or, if you already run CodeGraph/RepoWise/CodeQL, an adapter consumes their output. If you choose the reuse path, that tool runs prior and Tendril-Graph points at its output.
- No other tool must run before Tendril-Graph for v0.

## Quickstart

> ⚠️ Interface below is illustrative of the v0 target (see [PRD §10](specs/000-initial-plan/PRD.md)); commands land as the scaffolding does.

```bash
# install (reference distribution)
Tendril-Graph init

# register read-only providers (credentials via your secret broker / env)
Tendril-Graph providers add bitbucket --base-url $BB_BASE_URL --token $BB_TOKEN
Tendril-Graph providers add github    --app-id $GH_APP_ID --installation $GH_INSTALL
Tendril-Graph providers add teamcity  --base-url $TC_BASE_URL --token $TC_TOKEN
Tendril-Graph providers add octopus   --url $OCTO_URL --api-key $OCTO_API_KEY --space $OCTO_SPACE
# optional:
Tendril-Graph providers add datadog   --site $DD_SITE
Tendril-Graph providers add llm       --base-url $LLM_BASE_URL --model $LLM_MODEL --api-key $LLM_API_KEY  # BYOK, gateway-agnostic

# build the graph from an anchor, for an environment
# (resolves the deployed SHA for that env from Octopus, reads config at that ref)
Tendril-Graph graph build --anchor bitbucket:acme/webforms-solution --env prod

# ask it things — answers carry confidence, provenance, deployed ref, and unknowns
Tendril-Graph query find-relevant-repos "checkout flow" --env prod --min-confidence medium
Tendril-Graph query impact bitbucket:acme/landing-page-api --env prod
Tendril-Graph query explain-edge <edge-id>      # full evidence + provenance + deployed ref

# serve to coding agents
Tendril-Graph serve --mcp
```

## Provider support matrix

Reference implementations shipped in-tree. Add your own behind the [plugin contract](specs/000-initial-plan/SPEC.md#4-the-provider-plugin-contract-fr-17).


### Source (VCS)

| Provider | Auth | Incremental | MCP (agent path) | Notes |
|---|---|---|---|---|
| GitHub | GitHub App (preferred) / PAT | `push` webhook | official, read-only | App spans orgs; fine-grained PAT is single-org |
| Bitbucket **Cloud** | OAuth / API token | repo webhook | Atlassian Rovo (Cloud) | tokens expire hourly; refresh required |
| Bitbucket **Data Center** | HTTP access token | repo webhook | — | self-hosted; different base URL/auth |

### Build / Deploy (CI/CD)

| Provider | Kind | Auth | Per-env scoping | Value masking | Notes |
|---|---|---|---|---|---|
| GitHub Actions | intrinsic | rides GitHub cred | **GitHub Environments** | `vars` readable, `secrets` names-only | cheapest end-to-end slice |
| Bitbucket Pipelines | intrinsic | rides Bitbucket cred | Bitbucket Deployments | secured vars masked | — |
| Octopus Deploy | server-side | API key (per Space) | **richest** (env/role/tenant/channel) | sensitive masked | variable preview API available |
| TeamCity | server-side | access token | build-config params | password params masked | VCS roots map build→repo; check On-Prem CVE patching |
| CircleCI | intrinsic+server | personal API token | contexts / project | secret values masked | project tokens unsupported on v2 |

### Runtime (Telemetry — optional, capability-probed)

| Provider | Capabilities used | Auth | Notes |
|---|---|---|---|
| Datadog | service deps (APM), logs, RUM, catalog, deploy-events | API + app key | reference impl; deploy-tracking often absent → falls back to logs/APM/RUM |
| Grafana (Tempo/Loki) · Honeycomb · New Relic · OTel | traces / logs | provider-specific | via the same `TelemetryProvider` interface |

Telemetry is **never required** — Tendril-Graph probes which capabilities are populated and degrades gracefully.

## Security posture

- **Read-only, least-privilege** credentials per provider, from a central broker, short-TTL and rotated.
- **Secret redaction before persistence** — secret-typed values are stored as "sensitive, present," never as values. Tendril-Graph does not read or exfiltrate secrets; where a dependency hides inside one, the edge is flagged `unresolved-secret` (and may be recovered, at the edge level, from telemetry without reading the secret).
- The graph itself maps your estate's topology and is sensitive — access-control the query layer and MCP server accordingly.

## Extending Tendril

Add a provider without touching core. Implement the relevant interface from [`SPEC.md §4`](specs/000-initial-plan/SPEC.md#4-the-provider-plugin-contract-fr-17) — `VCSProvider`, `CICDProvider`, `ExtractorPlugin`, `TelemetryProvider`, or `GraphStore` — declare a `tendril-plugin.toml` manifest, and pass the **conformance suite** (the executable definition of the contract). See the plugin developer guide (`docs/plugins.md`, planned).

## Status

**M0–M10 complete.** All 210 tests pass with zero external credentials (fixture-mode CI). The full vertical slice is working end-to-end: VCS connectors (GitHub, Bitbucket DC), CI/CD connectors (TeamCity, Octopus, GitHub Actions, Bitbucket Pipelines), extractors (DotNet, composition, IaC), Roslyn intra-repo analysis (M8), LLM hybrid mode (M9), and Datadog telemetry cross-validation (M10). The query layer and MCP server expose five agent-facing tools (`find_relevant_repos`, `impact_analysis`, `dependency_path`, `env_diff`, `explain_edge`). See [review.md](review.md) for milestone details and [docs/architecture.md](docs/architecture.md) for the architecture diagram.

## Contributing

Issues and provider plugins welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the spec first; new providers must pass the conformance suite. Be honest about confidence — Tendril's value is that it never fabricates an edge or a value.

## License

Apache-2.0 (intended). See [LICENSE](LICENSE).
