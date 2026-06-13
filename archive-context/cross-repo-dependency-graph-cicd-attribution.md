# Cross-Repo Dependency Graph — CI/CD Attribution & Multi-Provider Spec

*Third companion. The earlier docs assumed we knew which CI/CD system owned a repo. In reality the CI/CD is **per-repo and heterogeneous** — GitHub Actions, TeamCity, CircleCI, Octopus, Bitbucket Pipelines, or combinations, with config and secrets in different stores. This document specifies the **CI/CD Attribution Engine** that discovers a repo's own CI/CD before resolution can happen, and routes each token to the correct variable store.*

---

## 1. Why this is a first-class subsystem, not an assumption

The resolver's job is to turn a token like `{landing-page-url}` into a concrete per-environment value. To do that it must know **which store holds that value** — and that store is determined by **which system deploys this specific repo to this specific environment.** That answer changes from repo to repo:

- `webpage-solution` might deploy via Octopus.
- `landing-page-ui` might build *and* deploy entirely in GitHub Actions, with the URL in a GitHub **Environment variable**.
- `landing-page-api` might build in GitHub Actions but hand off to Octopus for the deploy.

So before resolution, a per-repo discovery step has to answer: *what builds this repo, what deploys it, to which environments, and where do its environment-scoped variables live?* That is the **CI/CD Attribution Engine**. It was buried as open-question F.1; it is actually a core phase that sits **between extraction and variable resolution**.

```
 connectors → extraction → [ CI/CD ATTRIBUTION ] → variable resolution → resolver/join → graph
                                    │
                                    └── produces a per-repo CI/CD Profile that tells the
                                        resolver WHICH store to query, per environment
```

## 2. The provider set (now open-ended, GitHub Actions added)

CI/CD is no longer three named systems; it's a detectable, open set. First-class targets and the detection signal for each:

| Provider | Intrinsic signal (in-repo) | Variable/secret store | Native env-scoping construct |
|---|---|---|---|
| **GitHub Actions** | `.github/workflows/*.yml` | Actions variables (readable) + Actions secrets (names only) | **GitHub Environments** |
| **CircleCI** | `.circleci/config.yml` | Contexts + project env vars (secret values masked) | Context binding / project |
| **Octopus Deploy** | `.octopus/*.ocl` (Config-as-Code) or none (server-side) | Variable sets / project vars (sensitive masked) | **Octopus Environments** (+ role/tenant/channel) |
| **TeamCity** | `.teamcity/` Kotlin DSL or pipelines yaml, or none | Build/deploy parameters | Parameters per build config |
| **Bitbucket Pipelines** | `bitbucket-pipelines.yml` | Repo/workspace/deployment variables (secured = masked) | **Bitbucket Deployments** |
| Azure DevOps / Jenkins / others | `azure-pipelines.yml`, `Jenkinsfile`, … | varies | varies |

GitHub Actions is special because it is **intrinsic** — it lives in the repo, so detection is definitive and the store (variables/environments) is reachable through the same GitHub credential. The same is true of CircleCI's and Bitbucket Pipelines' in-repo config. TeamCity and Octopus are often **server-side** (config not in the repo), so those lean on extrinsic mapping (§4).

## 3. Two directions of evidence

Attribution joins **intrinsic** (what the repo declares) and **extrinsic** (what the CI/CD platforms claim about the repo) evidence.

**Intrinsic — detectors run on the repo tree:**

- Presence of a detector file → provider with role *build* and/or *deploy*.
- **Deploy-step detection inside a build workflow** is the key heuristic for chaining: scan a GitHub Actions / CircleCI / Bitbucket Pipelines config for steps that *perform a deploy* — an `octo`/OctopusDeploy action, an `aws deploy`/`aws s3 sync`/CloudFormation step, `helm upgrade`/`kubectl apply`, a TeamCity/CircleCI trigger, a Terraform apply. The presence of such a step tells you **who actually owns the environment-specific deploy**, which is what determines where injected runtime config (the tokens) comes from.
- `environment:` keyword (GitHub Actions) → which GitHub Environment a job targets → which environment-scoped vars/secrets apply.

**Extrinsic — mappings built during global indexing:**

- **TeamCity:** VCS roots → repo URL. A build config's VCS root is the authoritative link from TeamCity back to the repo it builds.
- **CircleCI:** project ⇄ repo (effectively 1:1).
- **Octopus:** Config-as-Code Git connection → repo (when used); otherwise the link is indirect, via the package/artifact a deployment process consumes back to the build that produced it (weaker, lower confidence).
- **GitHub Actions / Bitbucket Pipelines:** intrinsic by nature — they *are* the repo's CI, no external mapping needed.

The join: intrinsic detection says "this repo uses X"; extrinsic mapping confirms "X's pipeline Y is bound to this repo." Agreement → high confidence. Intrinsic-only (common for GHA) → high if the signal is definitive. Extrinsic-only (server-side TeamCity/Octopus with nothing in the repo) → medium, flagged for confirmation.

## 4. Handling multiplicity and chaining

A repo's CI/CD is a **set of (provider, role)**, not a single value, and the build owner and deploy owner are frequently different systems.

**The canonical chained case:**

```
GitHub Actions builds landing-page-api  →  workflow step invokes Octopus to deploy
                                            (OctopusDeploy/* action / octo CLI)

  build owner  = github-actions   (build-time vars resolve from Actions vars)
  deploy owner = octopus          (RUNTIME tokens like {landing-page-url} resolve
                                   from the Octopus variable set, env-scoped)
```

The rule the resolver needs:

> **Injected runtime/deploy-time tokens resolve against the *deploy owner's* store for the target environment. Build-time-only tokens resolve against the *build owner's* store.** The deploy owner is whichever system performs the environment-specific deploy step — detected intrinsically (deploy step in the build workflow) or extrinsically (Octopus/TeamCity bound to the repo).

If a repo deploys *itself* in GitHub Actions (no handoff), build owner = deploy owner = GitHub Actions, and tokens resolve from GitHub **Environment** variables for the target environment.

## 5. The CI/CD Profile (the engine's output)

One per repo, consumed by the resolver:

```yaml
repo: gh/landing-page-ui
environments_detected: [dev, stage, prod]
providers:
  - system: github-actions
    role: [build, deploy]            # deploys itself, no handoff
    confidence: high
    evidence: [.github/workflows/deploy.yml]
    env_scoping_source: github-environments
    variable_stores:
      - kind: actions-variables      # ${{ vars.* }}
        readable: true               # values returned by API
        scopes: [repository, environment, organization]
      - kind: actions-secrets        # ${{ secrets.* }}
        readable: false              # names only, values never returned
        scopes: [repository, environment, organization]

# contrast — the chained case for a different repo:
# repo: gh/landing-page-api
# providers:
#   - system: github-actions   role: [build]    variable_stores: [actions-variables, actions-secrets]
#   - system: octopus          role: [deploy]   env_scoping_source: octopus-environments
#     variable_stores: [{kind: octopus-varset, readable: partial, scopes:[env,role,tenant,channel]}]
#     deploy_handoff_evidence: [.github/workflows/deploy.yml: "uses: OctopusDeploy/..."]
```

The profile carries its own **confidence**, and any edge whose resolution depended on the profile inherits that ceiling — a shaky attribution can never yield a high-confidence edge.

## 6. Resolver store-selection algorithm

This is the concrete answer to "the CI/CD changes per repo." Given token `T` referenced in repo `R` for environment `E`:

```
1. profile = attribution[R]
2. if profile has no provider that deploys to E:
       emit T as UNRESOLVED-NO-ATTRIBUTION (orphan repo) + evidence; stop
3. owner = deploy_owner(profile, E)         # the env-specific deployer
   if T is build-time-only: owner = build_owner(profile)
4. store = owner.variable_store
5. value = store.lookup(T, scope=E)         # honor that store's scoping rules:
       #  github-environments: env-scoped vars override repo-level
       #  octopus:  match scope (environment [+role/tenant/channel])
       #  circleci: value from the context bound to the deploy job
       #  teamcity: parameter on the deploy build config (with inheritance)
       #  bitbucket: deployment-scoped variable for E
       #  NOTE: the *how* of this lookup is a tiered ladder (static → store API →
       #  preview API → deploy-log harvest → browser fallback) — see the
       #  Value Acquisition Ladder companion. Prefer reading the platform's
       #  already-resolved effective value over re-emulating its scoping engine.
6. if value is secret-typed / write-only (GH secret, masked Octopus/CircleCI/BB var):
       emit T as UNRESOLVED-SECRET + evidence pointer; stop
7. if value contains nested tokens: recurse (3–6) until concrete or stuck
8. return concrete value  →  resolver joins it against the reverse index
```

Steps 2 and 6 are the honest-degradation paths: a repo with no attributable deployer, or a value that legitimately lives in a secret store, produces a *flagged* result, never a fabricated edge.

## 7. GitHub Environments as a first-class scoping source

Worth calling out because it makes GitHub Actions a complete per-environment story on its own — no external deploy system required:

- Variables and secrets exist at **repository, environment, and organization** scope.
- When a job declares `environment: prod`, the **environment-scoped** values **override** repository-level values of the same name. This is the direct GitHub-native analog of Octopus environment scoping.
- **Variables (`vars.*`) are plaintext and readable via the API** — so a URL stored as a GitHub Environment variable resolves cleanly. **Secrets (`secrets.*`) are write-only**: the API lists names without values at every scope. So `${{ vars.LANDING_PAGE_URL }}` under `environment: prod` resolves to the concrete prod URL; `${{ secrets.LANDING_PAGE_URL }}` resolves only to "unresolved-secret."
- Caveats the parser must respect: reusable workflows define the environment at the job level (the called workflow's environment, not the caller's), and `secrets: inherit` changes what's in scope — so environment attribution must follow the reusable-workflow call graph, not just the top-level job.

## 8. Data-model additions

Fold into the spec's schema:

- Node `CICDProvider {system, role[]}` and node `VariableStore {kind, scopes[], readable}`.
- Edge `Repo —BUILT_BY→ CICDProvider` and `Repo —DEPLOYED_BY→ CICDProvider @env` (confidence, evidence).
- Edge `CICDProvider —RESOLVES_VARS_FROM→ VariableStore`.
- `Environment` nodes record their **provenance** (GitHub Environment / Octopus Environment / CircleCI context binding / TeamCity config / Bitbucket Deployment) to feed environment-name canonicalization.

## 9. Connection-requirement additions

**GitHub Actions rides the existing GitHub credential** (the GitHub App from the deep-dive's D.1). Additional fine-grained read permissions:

- **Actions: Read** (list workflows/runs), **Variables: Read** (read `vars` values), **Secrets: Read** (metadata/names only — values are never returned), **Environments: Read** (enumerate environments and their scoped vars/secrets-metadata).
- Repository **Contents: Read** already covers reading the workflow YAML files themselves.

**Bitbucket Pipelines rides the existing Bitbucket credential** — read `bitbucket-pipelines.yml`, repository/workspace/**deployment** variables (secured ones masked), and the Deployments (environments) config.

No new platform credential is introduced by adding GitHub Actions or Bitbucket Pipelines — both are reached through the VCS keys already provisioned in A2.

## 10. Phasing impact

- **Attribution moves to Phase 1.5** — a prerequisite for correct per-environment resolution (Phase 2). You cannot resolve a token without first knowing its store.
- **GitHub Actions moves up to Phase 1** alongside the first VCS, because it is intrinsic, common, and reachable through the GitHub credential with no extra platform onboarding — making it the cheapest end-to-end vertical slice (repo → workflow → GitHub Environment variable → resolved edge) to prove the whole pipeline.
- Server-side TeamCity/Octopus attribution (extrinsic mapping) lands with their connectors in Phases 2–3.

## 11. Updated open questions

1. **Deploy-step detection coverage.** The chaining heuristic (§3) depends on recognizing deploy steps inside build workflows. Build a maintained catalog of deploy-action signatures (Octopus actions, AWS deploy verbs, helm/kubectl, Terraform apply, platform triggers); unknown deploy mechanisms degrade to "build owner only," risking a missed deploy store. How aggressively to maintain this catalog vs. flag-and-review?
2. **Multiple deployers per environment.** If a repo is deployed to the same environment by two systems (migration in progress, blue/green across platforms), which store wins? Propose: emit both candidate resolutions with confidence, don't silently pick.
3. **Octopus without Config-as-Code.** When Octopus config is purely server-side, the repo→project link is indirect (artifact provenance). Confirm whether package/build metadata reliably ties an Octopus deployment process back to its source repo, or whether a manual mapping table is needed for those projects.
4. **Environment-name canonicalization across providers** (carried forward) — GitHub Environments, Octopus Environments, CircleCI context bindings, TeamCity parameters, and Bitbucket Deployments all name environments independently; the canonical environment dictionary is now a hard dependency of the resolver, not a nicety.

---

*The shape of the fix: CI/CD attribution is a discovery phase that runs per repo and answers "where does this repo's config actually come from," producing a profile the resolver uses to pick the right store per environment. Adding GitHub Actions isn't just one more connector — because GitHub Environments are a native, readable (for variables) per-environment scoping source, a repo that builds and deploys entirely in GitHub Actions becomes the simplest possible end-to-end proof of the whole system.*
