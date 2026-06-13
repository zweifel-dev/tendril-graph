# Cross-Repo Dependency Graph — Deep Dive & Integration Spec

*Companion to the PRD & Technical Specification. This document traces one real dependency chain end-to-end through the architecture, specifies the micro-frontend composition extractor that chain requires, and defines the concrete connection/integration requirements for all five source platforms.*

---

## Part A — The canonical worked example, traced end to end

> **This example is illustrative of the *mechanism*, not an assumed stack.** It uses a .NET WebForms host with JS/TS micro-UIs because that combination exercises every hard case at once — deploy-time token injection, browser-side iframe composition, and a repo-name ≠ URL-path ≠ deploy-host mismatch. The same machinery applies unchanged to a React/SPA shell, a Java/Spring gateway, a Python service, or any equivalent composition; swap the extractor plugin, keep the resolution logic.

This is the chain that motivates the whole design, traced through every component so the abstract machinery has a concrete referent.

### A.1 The chain in plain terms

```
[ webpage-solution ]   ← anchor. Classic WebForms. /login.aspx → /home.aspx
        │
        │  /home.aspx hosts an <iframe src="{landing-page-url}/dashboard-ui">
        │  web.config defines the token {landing-page-url}, injected at deploy time
        ▼
   resolves (per environment) to a concrete AWS URL, e.g.
   https://d-ui.prod.example.com   (serving the /dashboard-ui path)
        │
        │  that URL is a PROVIDER IDENTITY claimed by...
        ▼
[ landing-page-ui ]   ← GitHub repo. Name ≠ path ≠ deploy URL. Deployed separately to AWS.
        │
        │  its own config references the BFF base URL (injected per env)
        ▼
[ landing-page-api ]  ← deployed separately. The backend-for-frontend.
```

Three things in this chain break naive approaches and exercise the spec's hard parts:

1. **Name ≠ path ≠ URL.** The repo is `landing-page-ui`; the URL path is `/dashboard-ui`; the deployed host is some AWS URL. Nothing string-matches across the three. Resolution must go through canonical identity, not literal names.
2. **The edge is a token, not a literal.** The iframe doesn't contain a URL; it contains `{landing-page-url}`, replaced at deploy time, differently per environment. The edge only becomes concrete after variable resolution against the CI/CD store.
3. **The composition point is markup, not code.** The dependency is declared by an `<iframe src>` in server-rendered `.aspx`, not by an `HttpClient` call. A code-only extractor misses it entirely.

### A.2 What each component produces for this chain

**Step 1 — Extractors run on `webpage-solution` (consumer projection).**

The micro-frontend extractor (Part B) scans `.aspx`/`.master` markup and finds the iframe:

```
reference:   iframe-src
raw_value:   "{landing-page-url}/dashboard-ui"
token_refs:  ["landing-page-url"]
env_hint:    none-in-markup        # value is injected, not literal
evidence:    home.aspx:118  +  web.config:<appSettings>/landing-page-url
kind:        ui-composition (iframe)
```

It also records that `web.config` declares `landing-page-url` as an injectable token (a placeholder with no literal value in the repo), which tells the resolver "go ask the CI/CD store for this, per environment."

**Step 2 — Variable resolution engine evaluates the token, per environment.**

For each environment, resolve `landing-page-url` against the relevant CI/CD variable store (Octopus variable set scoped to that environment, or a TeamCity parameter, or a CircleCI context — whichever deploys this app). Result:

```
env=dev   → https://d-ui.dev.example.com    (confidence: resolved)
env=stage → https://d-ui.stage.example.com  (confidence: resolved)
env=prod  → https://d-ui.prod.example.com   (confidence: resolved)
```

Concatenate the path: the consumer reference for prod becomes `https://d-ui.prod.example.com/dashboard-ui`. URLs are typically *not* secret-typed, so they resolve cleanly even though secret values would be masked (see Part C caveat).

**Step 3 — The reverse index already holds `landing-page-ui`'s provider projection.**

During global indexing, `landing-page-ui`'s *own* deploy descriptors were read: its CI/CD deploy step pushes the build to an AWS target, and the deploy config / IaC declares the hostname and served path. So the index contains:

```
provider identity (env=prod):
  host: d-ui.prod.example.com
  path_base: /dashboard-ui
  artifact: landing-page-ui (built from GitHub repo landing-page-ui)
  evidence: <landing-page-ui deploy config / values.prod.yaml / Octopus deploy target>
  identity_class: network (host) + deploy-target  → HIGH confidence
```

**Step 4 — Resolver joins consumer reference to provider identity.**

The prod consumer reference `https://d-ui.prod.example.com/dashboard-ui` exact-matches the indexed provider host+path. Edge emitted:

```
webpage-solution  --DEPENDS_ON @prod-->  landing-page-ui
  via: ui-composition (iframe)
  confidence: HIGH  (exact host match, both sides fully resolved)
  evidence: [home.aspx:118, web.config:landing-page-url,
             octopus:varset/.../prod:landing-page-url,
             landing-page-ui deploy target d-ui.prod.example.com]
```

`landing-page-ui` is enqueued for traversal.

**Step 5 — Recurse: `landing-page-ui` → `landing-page-api`.**

The JS/TS extractor on `landing-page-ui` finds its BFF base-URL config (`.env`/build-time injection). Same resolution cycle per environment; the resolved API URL matches `landing-page-api`'s provider identity in the index. Edge:

```
landing-page-ui  --DEPENDS_ON @prod-->  landing-page-api
  via: http-client (config base URL)
  confidence: HIGH
```

`landing-page-api` is enqueued; its outbound refs (DB, queues, downstream services) continue the walk.

### A.3 The resulting graph fragment

```json
{
  "nodes": [
    {"id": "repo:gh/webpage-solution", "type": "Repo", "vcs": "github"},
    {"id": "repo:gh/landing-page-ui",  "type": "Repo", "vcs": "github"},
    {"id": "repo:gh/landing-page-api", "type": "Repo", "vcs": "github"},
    {"id": "svc:landing-page-ui",  "type": "Deployable", "produced_by": "repo:gh/landing-page-ui"},
    {"id": "svc:landing-page-api", "type": "Deployable", "produced_by": "repo:gh/landing-page-api"},
    {"id": "ep:d-ui.prod/dashboard-ui", "type": "Endpoint",
     "host": "d-ui.prod.example.com", "path_base": "/dashboard-ui", "env": "prod"}
  ],
  "edges": [
    {"from": "svc:landing-page-ui", "rel": "EXPOSES", "to": "ep:d-ui.prod/dashboard-ui",
     "env": "prod", "confidence": "high",
     "evidence": ["landing-page-ui:deploy-target:d-ui.prod.example.com"]},
    {"from": "repo:gh/webpage-solution", "rel": "CONSUMES", "to": "ep:d-ui.prod/dashboard-ui",
     "env": "prod", "confidence": "high",
     "evidence": ["home.aspx:118", "web.config:landing-page-url",
                  "octopus:varset/prod:landing-page-url"]},
    {"from": "repo:gh/webpage-solution", "rel": "DEPENDS_ON", "to": "repo:gh/landing-page-ui",
     "env": "prod", "via": "ui-composition/iframe", "confidence": "high"},
    {"from": "repo:gh/landing-page-ui", "rel": "DEPENDS_ON", "to": "repo:gh/landing-page-api",
     "env": "prod", "via": "http-client/config-base-url", "confidence": "high"}
  ]
}
```

An agent asked "what does the anchor depend on in prod, and through what?" gets `landing-page-ui` (via iframe composition) → `landing-page-api` (via BFF call), each with evidence it can verify and a confidence it can trust.

### A.4 Where this would silently fail without the design

| Shortcut | Failure on this chain |
|---|---|
| Match repo names to URLs | `landing-page-ui` never matches `/dashboard-ui` or `d-ui.prod...` — zero edges |
| Read literal config values | iframe holds `{landing-page-url}`, a token — no literal to match |
| Code-only extraction | the dependency lives in `.aspx` markup, not in C# |
| Single-environment graph | dev/stage/prod resolve to different hosts; a one-env graph is wrong for the others |
| Anchor-only crawl (no global index) | the provider identity of `landing-page-ui` is in *its* repo, unreachable from the anchor alone |

---

## Part B — Micro-frontend composition extractor (new)

The PRD's extractor layer named .NET, JS/TS, IaC, and CI-injected sources. This chain requires an explicit **composition extractor** for server-rendered markup, because micro-UIs are stitched in at the view layer.

**Where it looks.** `.aspx`, `.ascx`, `.master`, `.cshtml`/`.razor`, and plain `.html` templates, plus any server-side string-building that emits these tags.

**What it extracts as consumer references:**

- `<iframe src=...>` — micro-UI hosted in a frame (the example).
- `<script src=...>` / `<link href=...>` — micro-frontend bundles, Module Federation remotes, importmaps.
- `data-*` / config attributes carrying a base URL for a client that hydrates the frame.
- Reverse-proxy / rewrite rules in `web.config` (`<rewrite>`, `<location path>`), IIS URL Rewrite, and BFF proxy config — a very common place the `/dashboard-ui` → upstream mapping actually lives.

**Token awareness.** Every extracted `src`/`href` is run through placeholder detection (`{token}`, `#{token}`, `${token}`, `%(token)%`, ASP.NET `<%$ %>` expressions). A detected token is *not* resolved by the extractor; it is recorded with a pointer to where the token is declared (`web.config` appSettings, transform, or external injection) and handed to the variable-resolution engine (Part C). The extractor's contract stays "locate and classify, never resolve."

**Output shape:** `(reference, kind=ui-composition|asset|proxy-rule, raw_value, token_refs[], evidence{file,line})`.

This extractor is what turns "there's an iframe on the home page" into a first-class, resolvable consumer reference.

---

## Part C — Token resolution trace for `{landing-page-url}`

The single hardest mechanic, shown concretely. The token's concrete value depends on which platform deploys `webpage-solution` and how that platform scopes by environment:

- **Octopus Deploy** (the richest case): `landing-page-url` is a variable in a library variable set or project variables, **scoped by environment** (and possibly role/tenant/channel). The resolver reads the variable set via the REST API, selects the value whose scope matches the target environment, and—if that value itself contains `#{...}`—resolves transitively until concrete or provably stuck. Octopus's REST API exposes variable sets and deployment processes directly. The variable set is fetched from `/api/{spaceId}/variables/{variableSetId}` using an API key in the auth header, and scoping is part of the returned model.
- **TeamCity**: the value is a build/deploy **parameter** (config, system, or env), possibly inherited from a template or parent project. The resolver reads parameters via the REST API and applies precedence/inheritance.
- **CircleCI**: the value is a **context** or project environment variable, layered by which context the deploy job references. The resolver reads context variable *names* and project config; non-secret values resolve, secret values do not (caveat below).

**The masking caveat — and why URLs survive it.** Secret-typed variables are masked at the API boundary on CircleCI and Octopus: the API returns the name and "is-sensitive," not the value. That is correct for our threat model (we never want secret values), and it is mostly harmless for *this* problem, because endpoint URLs, hostnames, and service names — the things that form dependency edges — are rarely marked secret. When a dependency genuinely hides behind a secret-typed value (e.g. a full connection string with an embedded host), the resolver records the edge as **unresolved-secret** with the evidence pointer, surfacing it for a human rather than guessing. Honest degradation, not silent loss.

---

## Part D — Connection & integration requirements (per platform)

For each platform: the credential ("key"), least-privilege read scope, what we pull and how it maps to projections, the incremental hook, MCP availability, and the caveats that change the design.

### D.0 The build-vs-buy call on MCP servers (read this first)

All five platforms now have an MCP server (official or strong community). **They do not replace the indexer's connectors — they complement them.** Two distinct read paths:

- **Bulk indexer connectors (direct REST):** the system's own typed connectors hit each platform's REST API directly. This is required for the indexer because it needs deterministic pagination over the *whole* estate, controlled rate-limit/backoff, field-level redaction, and reproducible output. An MCP tool surface is built for conversational, bounded queries, not for crawling thousands of objects deterministically.
- **Agent-facing / ad-hoc path (MCP):** the official MCP servers are excellent for the coding-agent and human-diagnostic experience — "what's the deploy process for project X," "show me this context's vars." Wire these in alongside this system's own MCP server (PRD §II.11) so agents can drill from a graph edge into the live platform.

Net: **buy (use) MCP for agent/diagnostic reads; build typed REST connectors for the bulk index.** The connectors and the MCP servers can share the same brokered credentials.

### D.1 GitHub (source)

- **Credential.** For a multi-org estate, prefer a **GitHub App** with an installation token (`ghs_`) over a personal token: fine-grained PATs are scoped to a single resource owner, so one PAT cannot span multiple orgs cleanly. A GitHub App installed per org gives org-scoped, app-controlled, auditable read access; a classic PAT can span orgs but is coarse and tied to a user. Given A1 (all orgs), GitHub App is the right primitive.
- **Least-privilege read.** Repository **Contents: Read-only** (read files/tree at a ref), **Metadata: Read** (list repos), and org read for enumeration. No write anywhere.
- **What we pull → projections.** Repo list (nodes), file/tree at default branch (source for extractors: `web.config`, `appsettings.*`, `.aspx`, `.env`, IaC), build descriptors. (If GitHub Actions is also in play, its workflows; but the CI/CD of record here is TeamCity/Octopus/CircleCI.)
- **Incremental hook.** GitHub App webhooks on `push` → re-index the changed repo's projections.
- **MCP.** GitHub ships an official MCP server with a read-only mode and toolset filtering; it auto-filters tools by a classic PAT's scopes, while fine-grained PATs and App tokens show all tools and rely on API-level permission enforcement. Use it for the agent path; use the REST/GraphQL API for the bulk index.
- **Caveat.** Token-type choice drives the whole access model; decide App-vs-PAT before building the connector.

### D.2 Bitbucket (source)

- **The fork that matters: Cloud vs Data Center.** These are different products with different APIs and auth, and the connector must branch on it.
  - **Cloud:** OAuth 2.0 / API-token auth against `api.bitbucket.org`, with the access token as a Bearer token; OAuth access tokens expire in one hour and are refreshed via the refresh token. Plan for token refresh in the connector.
  - **Data Center (self-hosted):** HTTP access tokens used as Bearer credentials against the self-hosted REST API; project- and repo-level tokens are supported and a Data Center license is required to create them.
- **Least-privilege read.** Repository read (list workspaces/projects/repos, read file contents, branches). A separate webhook scope governs webhook access independently of the repository scope — request it only if we manage webhooks for incremental.
- **Incremental hook.** Repo `push` webhooks (Cloud and DC both support repository webhooks).
- **MCP.** Atlassian's Rovo MCP Server now supports Bitbucket Cloud — managed at the org level, authenticating via a scoped API token, able to list workspaces/repos, browse branches, and read file contents; it requires an org-linked workspace and (for now) API-token rather than OAuth auth. Useful for the agent path on Cloud; Data Center will lean on direct REST.
- **Caveat.** Determine Cloud vs DC (or both) up front — it bifurcates auth, base URLs, token lifetime, and MCP availability.

### D.3 CircleCI (CI/CD)

- **Credential.** A personal API token passed in the `Circle-Token` header (or as the basic-auth username); project tokens are not supported on API v2, so a personal token on a dedicated service account is the path.
- **What we pull → projections.** `config.yml` (jobs/workflows/orbs → build & deploy topology), and contexts and their environment-variable names via the `/api/v2/context/.../environment-variable` endpoints (variable store for resolution). Deploy jobs reveal where artifacts go (provider identities).
- **Incremental hook.** CircleCI outbound webhooks on workflow/job completion; config changes arrive via the repo push (config lives in the repo).
- **MCP.** CircleCI publishes an official MCP server (`@circleci/mcp-server-circleci`) with local stdio and self-managed remote deployment options, taking a CircleCI token. Agent path.
- **Caveats.** Expect HTTP 429 on rate limits with stricter per-org limits on some endpoints (e.g. ~10/hour on usage endpoints); list endpoints paginate via `next_page_token` — the bulk connector needs backoff + pagination. Secret env-var **values are masked**; we read names, not secrets (Part C).

### D.4 Octopus Deploy (CI/CD — the environment-scoping engine)

- **Credential.** An Octopus **API key** in the auth header, against the instance base URL, scoped by **Space**. Use a read-only service account.
- **What we pull → projections.** This is the richest provider-side source. Read-only: spaces, environments, projects, deployment processes, deployment targets (machines/roles), project variables and library variable sets, and git branches for version-controlled projects. Deployment processes + targets give provider identities (where a deployable lands); variable sets give the **environment-scoped** values that resolve consumer tokens like `{landing-page-url}`.
- **Incremental hook.** Octopus **Subscriptions** emit event payloads (deploy/release/variable changes) to a webhook endpoint → targeted re-index of the affected project/environment.
- **MCP.** Octopus publishes an official MCP server (`@octopusdeploy/mcp-server`) that talks to the REST API via the existing API-key security model; it is read-only and exposes spaces, projects, environments, deployment processes, targets, and variable sets. Strong fit for the agent path.
- **Caveat.** Sensitive variables are masked (Part C). Scoping rules (environment + role + tenant + channel) are non-trivial — the resolver must implement Octopus scope matching faithfully, which is why Octopus is the Phase 2 anchor for per-environment edges.

### D.5 TeamCity (CI/CD)

- **Credential.** A TeamCity access token (Bearer) against the REST API at `/app/rest`, on a read-only service account.
- **What we pull → projections.** Build configurations and templates, typed parameters (config/system/env), and **VCS roots** — which are the link from a build configuration back to its source repo — plus snapshot/artifact dependencies (build-time inter-build edges). VCS roots are essential: they tie a TeamCity build (and thus its parameters and deploy steps) to the GitHub/Bitbucket repo it builds.
- **Incremental hook.** TeamCity has native webhooks for server events (build started/finished, agent events) with documented REST payload schemas; separately, VCS commit hooks notify TeamCity to check for new changes. Use the former for change-driven re-index.
- **MCP.** TeamCity 2026.1 ships a built-in MCP endpoint at `<server-url>/app/mcp` (build-log retrieval, a generic REST GET, and a build trigger), and a community `teamcity-mcp` server offers a much larger typed tool surface with token auth and pre-2026.1 compatibility. The built-in generic REST GET is a convenient agent path.
- **Caveat.** A post-authentication vulnerability (CVE-2026-44413) affects TeamCity On-Premises (Cloud unaffected) — confirm the instance is patched before pointing a service credential at it; this is a self-hosted-security gate, not a blocker.

### D.5a GitHub Actions & Bitbucket Pipelines (intrinsic CI/CD)

CI/CD is not just the three external servers — it is **per-repo and often lives inside the repo**. Two intrinsic providers ride the VCS credentials already provisioned (no new key):

- **GitHub Actions** (on the GitHub App credential). Detected by `.github/workflows/*.yml`. Needs **Actions: Read**, **Variables: Read** (reads `vars.*` values), **Secrets: Read** (names only — values never returned), **Environments: Read**. **GitHub Environments are a native, readable per-environment scoping source** — env-scoped variables override repo-level when a job sets `environment:`, making a repo that builds *and* deploys in Actions fully resolvable on its own.
- **Bitbucket Pipelines** (on the Bitbucket credential). Detected by `bitbucket-pipelines.yml`. Reads repository/workspace/**deployment** variables (secured ones masked) and Bitbucket Deployments as the environment construct.

Because CI/CD ownership changes per repo and can chain across systems (build in Actions, deploy via Octopus), a dedicated **CI/CD Attribution Engine** discovers each repo's providers and routes each token to the correct store. That subsystem is specified in its own companion, *CI/CD Attribution & Multi-Provider Spec*.

### D.6 Connection architecture summary

```
                 ┌─────────────────────────────────────────────┐
                 │            Secret Broker (Vault)             │
                 │  5 read-only service credentials, short TTL  │
                 │  GH-App · BB-token · Circle-token ·          │
                 │  Octopus-key · TeamCity-token                │
                 └───────────────┬─────────────────────────────┘
            ┌──────────────┬─────┴───────┬──────────────┬──────────────┐
            ▼              ▼             ▼              ▼              ▼
       ┌────────┐   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
       │ GitHub │   │Bitbucket │  │ CircleCI │  │ Octopus  │  │ TeamCity │
       │connector│  │connector │  │connector │  │connector │  │connector │
       └────┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
            └────────────┴──── normalized IR ─────────┴────────────┘
                                   │                       (same creds, separate path)
                                   ▼                       ┌───────────────────────┐
                         [ indexer / extractors ]          │ official MCP servers   │
                                                           │ GH · BB(Rovo) · Circle │
                                                           │ Octopus · TeamCity     │──▶ coding agents
                                                           └───────────────────────┘
```

Each platform contributes a typed REST connector for the deterministic bulk index, while its MCP server is wired to the agent path; both draw the same brokered, read-only credentials. Hooks per platform feed the incremental refresh loop.

---

## Part E — PRD deltas folded back in

Already applied to the PRD document:

- **A1** — full org/workspace read access granted (closes the prior top open question; provider indexing is global).
- **A2** — a dedicated read-only credential per platform (GitHub, Bitbucket, CircleCI, Octopus, TeamCity), brokered and rotated.
- **A3** — declarative source-of-truth assumption, with runtime-only dependencies flagged not invented.
- **NFR-1** strengthened to name the five credentials, the broker model, and the CircleCI/Octopus masking behavior.

New requirements this deep dive adds, to merge into the spec's extractor and resolver sections:

- **FR-13 (composition extractor).** Extract `iframe`/`script`/`link`/proxy-rewrite references from server-rendered markup and `web.config`, with placeholder detection and a pointer to the token declaration.
- **FR-14 (multi-identity resolution).** Resolution must succeed when repo name, URL path, and deploy host all differ, by matching on canonical identity classes (host, deploy target, artifact), never on literal name equality.
- **NFR-7 (Bitbucket dual-mode).** The Bitbucket connector supports Cloud and Data Center as distinct auth/base-URL/token-lifetime profiles.

---

## Part F — Open questions specific to integration

1. **~~Which platform deploys which app?~~ Now specified** in the *CI/CD Attribution & Multi-Provider Spec*: a per-repo attribution engine discovers each repo's build/deploy providers (intrinsic detectors + extrinsic VCS-root/project mappings), handles build-vs-deploy handoffs, and routes each token to the correct environment-scoped store. Remaining sub-questions (deploy-step detection coverage, Octopus-without-Config-as-Code mapping) are tracked there.
2. **Bitbucket footprint.** Cloud, Data Center, or both? Determines connector scope and token strategy (D.2).
3. **GitHub App vs classic PAT.** App is cleaner for multi-org read (D.1); confirm org admins will install an App vs. issue a broad classic PAT.
4. **Secret-hidden dependencies.** How often do real edges hide behind secret-typed values (connection strings with embedded hosts)? If common, consider a narrowly-scoped, audited exception path; if rare, "unresolved-secret + human review" suffices.
5. **TeamCity patch state.** Confirm On-Premises instances are patched for CVE-2026-44413 before pointing a service credential at them (D.5).
6. **Environment name canonicalization across three CI/CD systems** (still open from the PRD) — Octopus environments, TeamCity parameter conventions, and CircleCI contexts name environments differently; a canonical environment dictionary is a prerequisite for correct per-env edges.

---

*Design honesty, restated for this layer: the worked example resolves cleanly because its wiring is declarative and its URLs are non-secret — the common case. The system's value is that it handles that common case end-to-end with evidence and confidence, and degrades visibly (unresolved/low-confidence, never fabricated) on the cases that static analysis genuinely cannot close.*
