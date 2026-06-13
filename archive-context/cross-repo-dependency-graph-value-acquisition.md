# Cross-Repo Dependency Graph — Value Acquisition Ladder & Browser-Fallback Assessment

*Fourth companion. Addresses the proposal to use a browser tool (Playwright) to read variable values from the CI/CD UI when they aren't easily available via API. Conclusion: the underlying instinct — let the platform resolve, then read the answer — is right, but UI scraping is the wrong mechanism for it, and it cannot defeat secret masking. This specifies a tiered acquisition ladder with browser automation as a constrained last resort.*

---

## 1. The proposal and the kernel of truth

The proposal: when a variable value is hard to get via API (masked, server-side, scoping too complex to emulate), drive the CI/CD web UI with a browser tool to read the value off the screen.

The kernel that's correct: **reimplementing each platform's scoping/substitution engine is the brittle part of the resolver.** Octopus scope matching (environment/role/tenant/channel), GitHub Environment overrides, TeamCity parameter inheritance, CircleCI context layering — emulating all of that faithfully is error-prone. Capturing the platform's *own* resolved effective value sidesteps the whole problem. That goal is sound and worth designing for.

## 2. The hard floor: the UI masks secrets exactly like the API

The single most important correction. The values most likely to be "not easily available" are **secret-typed** — and secrets are masked at the **presentation layer**, so the web UI reveals nothing the API doesn't:

- GitHub never renders a secret value in the UI (it shows "Updated N days ago," with no reveal action); the API returns names only.
- Octopus sensitive variables display as `••••••` in the UI and are non-retrievable via API once saved.
- CircleCI, TeamCity (password-typed parameters), and Bitbucket (secured variables) all mask in the UI as well as the API.
- Secrets are also masked in **deploy/build logs** (GitHub replaces secret values with `***`; the others redact equivalently).

Therefore: **for a true secret, Playwright recovers nothing the API didn't.** Any acquisition strategy bottoms out at the same floor — if a dependency genuinely hides inside a secret-typed value, it stays `unresolved-secret` regardless of fetch mechanism. (The exceptions are misconfigurations — a URL stored as a *non-secret* variable, or a value committed into a repo config file — and those are already reachable by the cheaper rungs below.)

This reframes browser automation: it is not a tool for getting *hidden* values. It is, at most, a tool for getting *non-secret* values that are awkward to compute via API.

## 3. The acquisition ladder

The resolver acquires each value by trying rungs in order, cheapest and safest first, stopping at the first that yields a concrete value. Each rung records which rung produced the value (provenance) and its confidence.

| # | Rung | Mechanism | Gets | Risk/cost | Notes |
|---|---|---|---|---|---|
| 1 | **Static config in repo** | read file | literal values in `appsettings.*`, `values.{env}.yaml`, `.env` committed | lowest | already in the extractor path |
| 2 | **CI/CD variable store API** | typed connector + scope emulation | non-secret store values; we apply scoping | low | the default for injected config; secrets masked |
| 3 | **Effective-value API / preview** | platform preview endpoint | non-secret value **as the platform resolved it** | low | where it exists (e.g. Octopus variable preview); the cleanest "platform resolves, we read" |
| 4 | **Deploy-log harvesting** | read deploy/build logs via API | non-secret values **actually injected** in a real deploy, per env | low–medium | ground truth of what shipped; secrets masked; tied to a specific run (freshness) |
| 5 | **Browser automation (Playwright)** | drive the UI | non-secret rendered/effective values the above can't reach | **high** | last resort; non-secret only; prefer self-hosted; §5 |
| 6 | **Runtime introspection** | query deployed service config/health | effective config from the running service | medium | future / validation source; non-secret only |
| — | **Floor** | — | secret-typed values | — | `unresolved-secret` + evidence at every rung |

Rungs 3 and 4 are the **better-shaped version of the proposal's instinct**: they let the platform do the resolution and read the answer, but through structured API surfaces rather than a browser.

## 4. Deploy-log harvesting — the recommended way to "read the resolved answer"

This deserves emphasis because it captures most of what the browser idea was reaching for, at far lower risk:

- **What it gets:** the *effective, injected, non-secret* values that the last (or a chosen) deployment actually used, per environment — read from logs that every platform exposes via API (GitHub Actions job logs, Octopus task logs, TeamCity build logs, CircleCI step output, Bitbucket pipeline logs).
- **Why it's strong:** it is the ground truth of what shipped, more trustworthy than statically-resolved config because it reflects the real evaluated result after all scoping and substitution. No scoping engine to reimplement.
- **Limits, stated honestly:** only values that actually appear in logs are recoverable; secrets are masked (`***`); the value is tied to a specific run, so it carries a freshness/provenance caveat (label it with the run id and timestamp); log parsing is semi-structured and needs per-platform patterns.
- **Even more robust (opt-in, more invasive):** add a deploy step that writes the resolved non-secret config to a manifest artifact the indexer reads. This makes "the deploy emits its own resolved config" a contract rather than a scrape — best fidelity, but only covers repos you instrument and requires touching pipelines.

## 5. Browser automation — where it's justified, where it isn't

Browser automation is the bottom functional rung (above only the secret floor). It is justified **only** when all of the following hold:

- the value is **non-secret** (otherwise it's masked in the UI too — §2),
- rungs 1–4 cannot reach it (genuinely server-side, no preview API, never logged), and
- the target is **self-hosted** (TeamCity / Octopus / Bitbucket Data Center), where a dedicated low-privilege UI account can be created and there is no SaaS bot-detection or terms-of-service friction.

Against SaaS (GitHub, Bitbucket Cloud, CircleCI Cloud, Octopus Cloud) it should be avoided.

### Why it's the last rung — the security analysis

| Dimension | API connector (rungs 2–4) | Browser automation (rung 5) |
|---|---|---|
| Credential | scoped, **read-only** service token | interactive **login**; usually human-equivalent rights, not constrainable to read-only at the UI |
| Mutation risk | cannot write | the session *can* change things; a bug or injection mutates config |
| MFA/SSO | n/a | forces an MFA-exempt service account (a hole) or stored session cookies (theft/expiry churn) |
| Auditability | clean API audit, distinct identity | looks like a human session; harder to attribute |
| Stability | API contract; versioned | DOM selectors rot on every layout change/A-B test |
| Throughput | fast, paginated, bulk-safe | orders of magnitude slower; not viable for bulk crawl |
| ToS / detection | sanctioned | discouraged on many SaaS; can lock the account |

The system's entire security posture (NFR-1) is built on least-privilege, read-only, brokered, short-TTL, non-mutating API credentials. Browser automation inverts every one of those properties. That cost is acceptable only at the bottom rung, for a non-secret value with no structured path, on infrastructure you own.

### If it is used, constrain it hard

Dedicated low-privilege UI account; isolated/ephemeral browser context; never on the bulk-crawl path (targeted per-variable only); strict allowlist of pages it may visit; capture timestamp + source URL as evidence; lower confidence than any API-sourced rung; and a kill switch.

## 6. Confidence & provenance per rung

Acquisition rung is part of an edge's evidence, and it caps confidence:

- Rungs 1–3 (static / store API / preview API): **high** — deterministic, reproducible.
- Rung 4 (deploy log): **high on value fidelity** (it's what actually ran) but carries a **freshness** qualifier (bound to a run id); treat as high if the run is recent, medium if stale.
- Rung 5 (browser): **medium at best** — brittle capture; always carries capture timestamp and a "verify" flag.
- Rung 6 (runtime): **validation-grade** — best used to *confirm or contradict* a statically-derived edge rather than to originate one.
- Floor (secret): no value; edge marked `unresolved-secret` with the evidence pointer for human review.

## 7. How it plugs into the resolver

This refines the store-selection algorithm in the *CI/CD Attribution & Multi-Provider Spec* (§6). Where that algorithm said `value = store.lookup(T, scope=E)`, substitute the ladder:

```
value, rung = acquire(T, repo=R, env=E):
    for rung in [static, store_api, preview_api, deploy_log, browser, runtime]:
        if rung is browser and (T is secret-typed or target is SaaS): continue
        v = rung.try(T, R, E)
        if v is concrete: return (v, rung)
    if T is secret-typed: return (UNRESOLVED_SECRET, floor)
    return (UNRESOLVED_NO_SOURCE, floor)
```

Attribution (which store) still comes first; the ladder governs *how* the value is pulled from that store, with structured rungs strongly preferred and the browser gated behind the secret/SaaS checks.

## 8. Recommendation

Adopt the instinct, not the mechanism. Build rungs 3 and 4 — **preview APIs and deploy-log harvesting** — as the primary way to capture platform-resolved effective values; they deliver most of what the browser idea was after, with API-grade safety and fidelity. Keep **Playwright as a gated, non-secret, self-hosted-only, last-resort rung**, constrained as in §5. And keep the floor explicit: secrets are masked everywhere, so no acquisition strategy turns a secret-hidden dependency into a resolved edge — it stays flagged for a human, which is the correct and safe outcome.
