# Cross-Repo Dependency Graph — Runtime Telemetry Integration

*Fifth companion. Brings observability in as a third data plane alongside repos and CI/CD config. Telemetry is modeled as a **pluggable provider with detectable capabilities**, not a single hardcoded product — Datadog is the reference implementation, but the same interface fits Grafana (Tempo/Loki), Honeycomb, New Relic, or a raw OpenTelemetry collector. The system probes which capabilities are actually populated and degrades gracefully, because enterprises wire these up unevenly. Telemetry is layered on the static graph for cross-validation and enrichment — it is never required.*

---

## 1. The kernel: three data planes, not two

The graph is reconstructed from declarative sources (repos + CI/CD config). Observability is a legitimate **third plane** recording what the estate *actually did at runtime*. Because the goal is dependency/deploy *relationships* — not secrets — telemetry is a natural fit, and it reaches dependencies that static analysis structurally cannot: things wired by service discovery, computed at runtime, or hidden behind secrets.

```
Plane 1: Source repos          → declared wiring (what the code/config says)
Plane 2: CI/CD config          → injected per-env wiring (what deploy resolves)
Plane 3: Runtime telemetry     → observed behavior (what actually called what)
                                  ── cross-validates and enriches 1 + 2 ──
```

Telemetry is **additive**: the system must produce a useful graph with zero telemetry, because coverage is partial and uneven (see §5). When present, it raises confidence and catches what static missed; it is never a hard dependency.

## 2. Telemetry as a pluggable provider with detectable capabilities

Do not bind to one product or assume any feature is enabled. Define a **TelemetryProvider** interface whose implementations declare which **capabilities** they can actually serve for a given org:

| Capability | What it yields | Typical enterprise availability |
|---|---|---|
| `logs` | request/access logs → infer caller→callee edges from URLs, host headers, correlation IDs | **near-universal** — almost always flowing |
| `apm_traces` | distributed traces → service dependency map (upstream/downstream), per `env` | **common** — but not on every service |
| `apm_service_dependencies` | a precomputed service dependency graph | common where APM is mature |
| `rum` | browser/real-user monitoring → frontend resource loads, route/iframe composition | **present on user-facing apps**; the one that can see browser-side edges |
| `deploy_events` / `software_delivery` | deployment markers, versions, CI/CD pipeline visibility | **frequently absent** — many orgs never wire CI Visibility / deployment tracking to pipelines |

**The ordering matters.** Reliance should track availability: lean on `logs` and `apm_traces` as the typical baseline, use `rum` where it exists (it's the only plane that sees browser composition), and treat `deploy_events`/`software_delivery` as a **bonus if populated, never a prerequisite** — deploy/version facts already come from the CI/CD plane, so telemetry deploy-tracking is corroboration, not a primary source.

**Reference implementation — Datadog.** The official Datadog MCP/API exposes a service-dependencies tool (APM), a service catalog read, APM span search, a logs/events surface, RUM, and a software-delivery toolset. Map these onto the capabilities above. Other providers slot into the same interface: Grafana Tempo (traces) + Loki (logs), Honeycomb (traces), New Relic (APM/logs), or an OTel collector feeding any backend. Auth is provider-specific (Datadog uses an API key + application key, read-only); the indexer pulls via the provider's API and wires the provider's MCP, where one exists, to the agent path.

## 3. What each capability contributes to the graph

- **Service dependency edges** (from `apm_service_dependencies` or derived from `apm_traces`): the observed analog of `DEPENDS_ON` — service A actually called service B — already `env`-scoped via tags. Where APM is absent, **logs can be mined for the same edges** (a request to host X carrying a known service's correlation id), at lower fidelity.
- **Browser/composition edges** (from `rum`): the frontend relationships backend tracing never sees — a page that loads a micro-UI bundle or hosts another app in an iframe. This is the plane that can capture a server-rendered host → micro-UI edge.
- **Service → repo resolution** (from the provider's service catalog / git metadata tags, e.g. a `git.repository_url` tag): a direct service-name → repo link, the exact mapping the static reverse index works to reconstruct.
- **Deploy/version facts** (from `deploy_events`, *if populated*): what shipped, which version, when, to which env — corroborating the CI/CD plane.

## 4. Capability detection & graceful degradation

The integration runs a **probe pass** per org before relying on anything, and adapts:

```
probe(provider, env):
    caps = {}
    caps.logs        = provider.has_logs(env)                 # almost always true
    caps.apm         = provider.has_traces(env)               # check sample volume > 0
    caps.svc_deps    = provider.has_service_dependencies(env)
    caps.rum         = provider.has_rum(env)                  # user-facing apps
    caps.deploys     = provider.has_deploy_events(env)        # often false
    return caps

select_edge_source(caps):
    if caps.svc_deps: return service_dependency_graph         # best
    if caps.apm:      return derive_edges_from_traces         # good
    if caps.logs:     return derive_edges_from_logs           # baseline, lower fidelity
    return none                                               # telemetry contributes nothing; static stands alone

use_rum_if(caps.rum)            # additive: browser/composition edges
use_deploys_if(caps.deploys)   # additive corroboration only; never required
```

Two rules make this safe:

1. **Probe, never assume.** A capability that exists in the product but isn't populated for this org/env is treated as absent. (Empty ≠ available.)
2. **Degrade, don't fail.** Missing `deploy_events` is a non-event (CI/CD plane covers deploys). Missing APM falls back to logs. Missing everything means telemetry simply adds nothing this run, and the static graph is unaffected.

## 5. The honest limits — enrichment, not replacement

1. **Coverage equals instrumentation.** Telemetry sees only instrumented services and traffic that actually flowed. **Entry-point and edge services are often the least instrumented** — legacy or perimeter components frequently predate the observability rollout — which is awkward because the traversal starts there. Coverage is often thinnest exactly where the anchor sits.
2. **Only exercised paths appear → false negatives for cold dependencies.** A declared dependency not called during the observation window (seasonal job, failover path, rarely-hit feature) is invisible to runtime but real. Static analysis sees declared-but-unexercised edges; telemetry does not.
3. **Browser composition needs RUM, and RUM is not guaranteed.** A host page that embeds a micro-UI in an iframe is a browser-side relationship. Backend tracing won't see it; **RUM can, if configured** — and RUM is more commonly present than software-delivery, so where it exists it's a real asset for catching exactly these composition edges. Where RUM is absent, these edges rest on the static plane alone.
4. **Behavior, not wiring.** Telemetry says A calls B. It does **not** say *where that dependency is configured* — which config token, which CI/CD variable, which repo to edit. For the primary use case (an agent safely changing a contract or endpoint), the agent needs the **wiring**, which lives in the static graph. Telemetry confirms the edge exists; static says how to change it.
5. **Another identity space.** Provider `service` names are one more alias class to reconcile with repo names, deploy targets, and URLs — except where a `git.repository_url`-style tag or catalog entity short-circuits it. Encouraging that tagging is the highest-leverage resolution win on both planes.

Net: telemetry is a **validator and dynamic-dependency catcher**, not a source of truth for how the estate is wired.

## 6. The cross-validation model (the real payoff)

Overlay the runtime edge set on the static edge set per environment and reconcile:

| Case | Meaning | Action |
|---|---|---|
| **Static ∩ Runtime** | declared *and* observed | promote to **highest confidence** — a verified edge |
| **Static − Runtime** | declared, not observed | likely a **cold path** (keep, tag `not-observed-in-window`); *or* a **stale/dead dependency** if the service is active but the call never appears → flag for cleanup |
| **Runtime − Static** | observed, not declared | a **dynamic/hidden dependency static missed** — service discovery, runtime-computed endpoint, or secret-hidden wiring. **Add it, provenance = observed, and flag** |

The third row is the highest-value output: it surfaces dependencies that appear in no readable config — including the secret-hidden edges the acquisition ladder left as `unresolved-secret`. Runtime fills those in **at the edge level without ever reading a secret value**.

This static-vs-runtime divergence report is a **first-class operational deliverable** on its own: stale dependencies to remove, undocumented dependencies to formalize — independent of the coding-agent use case.

## 7. Service catalog as a reverse-index seed

Where a provider's service catalog holds entity definitions (ownership, repo links, declared dependencies), that catalog is a **high-quality seed for the reverse index** — much of the service→repo→dependency mapping may already be curated. Two synergies:

- Pull it to bootstrap resolution (service identity → repo) before the static crawl runs.
- Catalog entity-definition files often live **in the repos**, so the static extractor can read them directly as a config source — the same artifact serves both planes.

Well-maintained catalog → the resolution problem shrinks; absent → the static reverse index remains the fallback.

## 8. Data-model & architecture placement

- Edges gain a **provenance dimension**: `declared` (static), `injected` (CI/CD-resolved), `observed` (runtime). An edge may carry several; cross-plane agreement is the confidence multiplier.
- New edge attribute `observation`: `{env, last_seen, sample_count, capability, provider}` on runtime-confirmed edges, so freshness, traffic volume, and which capability produced it are queryable.
- Telemetry is an **enrichment/validation plane**, run after the static graph is built; it is **not** a rung in the value-acquisition ladder (it observes the resulting call, it does not resolve a token to a value). It contributes *edges and resolution hints*, not *token values*.
- The agent query layer exposes provenance so an agent can request `declared`, `observed`, or `both` and weight accordingly.

## 9. PRD deltas

- **NG1 (already revised):** static reconstruction is primary and self-sufficient; runtime telemetry is an optional cross-validation/enrichment layer; the system functions with telemetry absent.
- **Provider-agnostic requirement:** telemetry support is defined against a `TelemetryProvider` capability interface; no specific product or feature (notably deployment tracking) may be assumed present. Implementations probe and degrade.
- **New success metrics:** cross-plane agreement rate (high-confidence static edges confirmed by runtime) and dynamic-catch count (runtime-only edges surfaced); runtime gives a partial golden source for measuring static precision/recall.
- **Recommendation to adopters:** enable unified service tagging + git metadata and maintain catalog entity definitions — the highest-leverage, lowest-cost change that makes both planes far more resolvable.

## 10. Recommendation

Treat telemetry as the **third plane and validation layer, behind a provider interface**. Probe capabilities and degrade: rely on **logs and APM as the typical baseline**, use **RUM where present** (it's what catches browser/composition edges), and treat **deploy/software-delivery tracking as a bonus, not a dependency** — many estates never wire it, and the CI/CD plane already supplies deploys. Use it to (a) confirm static edges and lift confidence, (b) catch dynamic and secret-hidden dependencies static can't see, and (c) seed resolution from the service catalog where maintained. Keep the static graph primary, because it alone provides the **wiring** an agent needs to make changes, and because entry-point/edge services are often the least instrumented.
