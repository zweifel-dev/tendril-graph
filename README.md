<div align="center">

# 🌱 Tendril-Graph

**Trace the tendrils between your repos.**

Tendril reconstructs the cross-repo dependency graph of a multi-repo estate — the wiring that connects micro-UIs, backends-for-frontends, and services through configuration injected at build and deploy time — and serves it to coding agents and humans.

<!-- badges: build · coverage · license · npm/pypi — add on first release -->

[Requirements](PRD.md) · [Spec](SPEC.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md)

</div>

---

## What it is

Modern product lines span many repositories wired together not in code but in **configuration** — base URLs, service names, queue names — **injected at deploy time**, differently per environment. No single artifact says "repo A depends on repo B in production." Tendril reconstructs that graph **statically**, by reading source, build/deploy descriptors, and CI/CD variable stores, and optionally **cross-validates** it against runtime telemetry.

The mechanism in three sentences: every service has a **consumer projection** (the URLs and names it references — "I call X") and a **provider projection** (the identities it claims when it deploys — "I am reachable as Y"). Tendril builds a global index of every provider projection, then walks outward from an **anchor repo**, and an edge exists wherever a consumer reference matches a provider identity — scoped to an environment, carried with a confidence score and the evidence that produced it. Intra-repo structure is left to other tools; Tendril owns the **inter-repo, per-environment** layer and exposes it to coding agents (e.g. as the backbone for `find_relevant_repos()`).

> Everything platform-, language-, and vendor-specific is a **plugin behind a stable contract** — Tendril is general-purpose and community-extensible by design.

## Architecture

See **[docs/architecture.md](docs/architecture.md)** for the rendered diagram. Three data planes (source / build-deploy / runtime) feed a resolution pipeline behind a provider-plugin boundary, producing a confidence- and evidence-tagged graph served over an MCP query layer.

## Quickstart

> ⚠️ Interface below is illustrative of the Phase 1 target (see [PRD §10](PRD.md)); commands land as the scaffolding does.

```bash
# install (reference distribution)
tendril init

# register read-only providers (credentials via your secret broker / env)
tendril providers add github --app-id $GH_APP_ID --installation $GH_INSTALL
tendril providers add github-actions          # rides the github credential
tendril providers add octopus --url $OCTO_URL --api-key $OCTO_KEY
tendril providers add datadog --site $DD_SITE # optional telemetry

# build the graph from an anchor, for an environment
tendril graph build --anchor github:acme/webpage-solution --env prod

# ask it things
tendril query find-relevant-repos "checkout flow" --env prod --min-confidence medium
tendril query impact github:acme/landing-page-api --env prod
tendril query explain-edge <edge-id>      # full evidence + provenance chain

# serve to coding agents
tendril serve --mcp
```

## Provider support matrix

Reference implementations shipped in-tree. Add your own behind the [plugin contract](SPEC.md#4-the-provider-plugin-contract-fr-17).

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

Telemetry is **never required** — Tendril probes which capabilities are populated and degrades gracefully.

## Security posture

- **Read-only, least-privilege** credentials per provider, from a central broker, short-TTL and rotated.
- **Secret redaction before persistence** — secret-typed values are stored as "sensitive, present," never as values. Tendril does not read or exfiltrate secrets; where a dependency hides inside one, the edge is flagged `unresolved-secret` (and may be recovered, at the edge level, from telemetry without reading the secret).
- The graph itself maps your estate's topology and is sensitive — access-control the query layer and MCP server accordingly.

## Extending Tendril

Add a provider without touching core. Implement the relevant interface from [`SPEC.md §4`](SPEC.md#4-the-provider-plugin-contract-fr-17) — `VCSProvider`, `CICDProvider`, `ExtractorPlugin`, `TelemetryProvider`, or `GraphStore` — declare a `tendril-plugin.toml` manifest, and pass the **conformance suite** (the executable definition of the contract). See the plugin developer guide (`docs/plugins.md`, planned).

## Status

Pre-release / in design. The requirements (`PRD.md`) and spec (`SPEC.md`) are stable enough to build from; `prompt.md` is the Claude Code handoff that turns them into an implementation plan. Track progress against the phased roadmap in [PRD §10](PRD.md).

## Contributing

Issues and provider plugins welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the spec first; new providers must pass the conformance suite. Be honest about confidence — Tendril's value is that it never fabricates an edge or a value.

## License

Apache-2.0 (intended). See [LICENSE](LICENSE).
