# Tendril-Graph: Spec Critique + Implementation Plan

## Context

Tendril-Graph is in pre-scaffolding state (design docs only, no code). This plan:
1. Critiques `SPEC.md` as a skeptical senior engineer — gaps, ambiguities, failure modes
2. Produces a phased, buildable implementation plan mapped to `PRD.md §10`
3. Resolves `SPEC.md §17` open questions where possible

The v0 target stack: ASP.NET WebForms (VB+C#) + Angular, built in TeamCity, deployed via Octopus, stored in Bitbucket + GitHub.

---

## Part 1: Spec Critique

> **Resolution legend:** 🟢 Addressed in both code and spec (or spec-only where no code change was needed)

### CRITICAL — Blocks correctness if unaddressed

**C1. `acquire()` has no `ref` parameter — deployed-ref not threaded through resolution (`§9`)** · 🟢

`VCSProvider.read_file(repo, ref, path)` in §4.2 already accepts `ref` — so the VCS interface is correct. But the `acquire()` pseudocode in §9 passes `(T, R, E)` with no `ref`, and the rung-1 call (`static config in repo`) doesn't say which ref to read. This means the acquisition ladder silently reads from whatever ref the VCS connector defaults to (likely `HEAD`), breaking FR-24.

**Fix:** Change `acquire(T, repo R, env E)` → `acquire(T, repo R, env E, ref: str | None)`. Rung 1 calls `read_file(repo, ref, path)` with the deployed ref from `DeployedRef` resolution. Rungs 2-4 (variable store / preview / deploy logs) reflect current platform state — no `ref` applies — but should carry `effective_at: timestamp` where the platform provides it (Octopus audit logs do). Document the distinction: source reads use the deployed ref; store reads reflect current state with a staleness caveat in evidence.

**Status:** `resolver.py` has `ref: str | None = None` on `acquire()`. Rung 1 uses the deployed ref. SPEC.md §9 pseudocode updated. ✅

**C2. Environment-name canonicalization is listed as "open" but is a Phase 0 blocker (`§17.3`)** · 🟢

The resolver joins consumer references to provider identities *per environment*. Without a canonical environment dictionary, the BFS cannot join `github-env:"production"` to `octopus-env:"Prod"` to `tc-param:"prod"`. This is §17.3's open question, but it blocks Phase 1 (first real edge) entirely.

**Fix:** Close this in v0. Strategy: case-fold + configurable alias table:
```toml
[environments.prod]
aliases = ["production", "prd", "live", "Production", "PROD"]
```
Ship common defaults; adopter extends for their estate. Unmatched env names → `raw-name` + low confidence, never a resolution failure.

**Status:** `EnvironmentCanonicalizer` in `tendril/core/environment.py`; `data/environments_default.yaml` ships defaults. Injected into `TraversalEngine` and `DeployedRefResolver`. SPEC.md §17.3 marked RESOLVED. ✅

**C3. Deployable node creation is unspecified (`§2`, `§4.4`)** · 🟢

The domain model has `Repo —PRODUCES→ Deployable`, and `DEPENDS_ON` runs between Deployables, not Repos. But nothing specifies how Deployable nodes are created. The extractor interface (§4.4) returns `{consumer_refs, provider_identities, token_decls}` — no `Deployable[]`. The CI/CD provider (§4.3) returns `PipelineBinding` which has `repo` but no explicit Deployable. The traversal pseudocode in §10 uses `repo` throughout, conflating it with Deployable.

This matters because a single repo can produce multiple deployables (e.g., a solution with a web app + a background job), each with different provider identities and environments. Collapsing Repo = Deployable silently drops this multiplicity.

**Fix:** Add `Deployable` discovery as a concern of attribution + extraction:
- CICDProvider: deploy targets per project/pipeline → Deployable nodes (Octopus project, TeamCity build config with deploy step)
- ExtractorPlugin: add optional `deployables(repo_ir) -> Deployable[]` method (default: one deployable per repo — the common case)
- For v0, default to 1:1 Repo:Deployable unless the CI/CD profile indicates otherwise (Octopus projects map to deployables naturally). Flag multi-deployable repos for manual review.

**Status:** SPEC.md §4.3 now specifies the Deployable creation rule: `PipelineBinding(roles=[deploy])` → Deployable keyed as `{provider}:{org}/{repo}#{pipeline_id}`; v0 omits suffix for 1:1 case. `read_provider_identities()` populates the provider projection after the Deployable node exists. SPEC.md §2 and §4.4 updated with v0 default and v1+ `deployables()` plan. No code change needed for M1-M4. ✅

**C4. Deploy-step detection is under-specified (`§7`)** · 🟢

The spec says "detect deploy-step detection inside a build workflow" but doesn't specify:
- The actual signature catalog (which action IDs, step names, task types)
- Multi-env multi-step pipelines (a pipeline that deploys to staging *then* prod)
- What happens when detection confidence is low
- The CICDProfile output schema

**Fix:** Ship `deploy_step_signatures.yaml` as a versioned data file in core (not embedded in code). Entries: `{provider_id, match_type(action_id|task_type|step_name_pattern), pattern, env_extraction_hint}`. Unknown mechanism → attribute build owner only, set `deploy_owner_confidence=low`, emit `unattributed-deploy` flag.

**Status:** SPEC.md §7 now specifies the full catalog schema (`provider_id`, `match_type`, `pattern`, `env_extraction_hint`), the covered mechanisms, and the unknown-mechanism fallback (`deploy_owner_confidence=low`, `unattributed-deploy` flag). `data/deploy_step_signatures.yaml` exists. ✅

**C5. Plugin ABI is language-neutral pseudocode only (`§4.9`, `§17.8`)** · 🟢

§4.9 mentions "Python entry points, npm package convention" but doesn't settle the reference language, how a Python core loads a non-Python plugin, or whether the ABI is in-process or subprocess. The conformance suite cannot be implemented without this.

**Fix:** See Part 3 (Decisions). Resolved: **Python 3.12+**, subprocess JSON-RPC for non-Python plugins.

**Status:** Entire codebase is Python 3.12+. `tendril/plugins/subprocess_bridge.py` implements the JSON-RPC bridge. SPEC.md §17.8 marked RESOLVED. CLAUDE.md updated. ✅

---

### HIGH — Correctness/completeness degraded

**H1. `ServiceIdentity` (§3) vs `ProviderIdentity` (§4.1) — two concepts, unclear relationship** · 🟢

§3 defines `ServiceIdentity` as a canonical node carrying aliases across identity classes. §4.1 defines `ProviderIdentity` as an IR type output by extractors. The spec never says how `ProviderIdentity` records become `ServiceIdentity` nodes, whether they're merged, or what resolves conflicts when two repos claim the same identity.

**Fix:** Clarify: `ProviderIdentity` is the raw extraction output (per-repo, per-extractor). During global indexing, ProviderIdentities are canonicalized and merged into `ServiceIdentity` nodes using the §3 alias resolution rules. Conflicts (two repos claim the same host) → both linked with `ambiguous: true`. The reverse index (§8) is keyed by ServiceIdentity, not raw ProviderIdentity.

**Status:** In v0, `ReverseIndex` canonicalizes in-memory using `IndexEntry`; `ServiceIdentity` nodes are persisted in Kùzu schema. No code change needed. SPEC.md §3 updated with ProviderIdentity→ServiceIdentity flow and the v0 in-memory clarification. ✅ (spec-only)

**H2. Traversal pseudocode conflates structured and agentic mode (`§10`)** · 🟢

The pseudocode shows the structured-mode path, then says "By default (hybrid/agentic modes) the per-node step is not a fixed extractor sweep." The default is `hybrid` (§15.1) but the pseudocode represents `structured`. A reader implementing from the pseudocode builds the wrong default.

**Fix:** Add mode dispatch:
```
evaluate_node(repo, env, mode):
    if mode == structured:  [current pseudocode]
    if mode in (hybrid, agentic):  [LLM loop from §15.2, using structured as fallback]
```
`hybrid` runs the structured fast-path first, escalates to LLM only for unresolved/ambiguous refs.

**Status:** SPEC.md §10 pseudocode rewritten with explicit `evaluate_node(repo, env, mode)` dispatch. Structured mode is the v0 implementation; hybrid/agentic dispatches to §15.2 (M9). ✅

**H3. No `DeployedRef` as a first-class graph node (`§2`)** · 🟢

The deployed SHA is recorded "on every edge as evidence," but isn't a queryable node. For multi-env queries ("diff prod vs staging"), the deployed SHA per env per Deployable must be queryable — not buried in edge evidence blobs.

**Fix:** Add node: `DeployedRef { sha, branch, env, deployable_id, deploy_timestamp, source: deploy_run_id }`. Edge: `Deployable —DEPLOYED_AS→ DeployedRef @env`.

**Status:** `DeployedRef` is in `models/ir.py` and `store/schema.py`; `DEPLOYED_AS` edge is in the Kùzu DDL. SPEC.md §2 node list and edge table updated to include both. ✅

**H4. Incremental invalidation cascade is unbounded (`§14`)** · 🟢

"A provider identity change may invalidate others' inbound edges" — but no reverse tracking exists. Without it, every provider-identity change requires a full graph scan.

**Fix:** Maintain a `resolved_via` index on `DEPENDS_ON` edges pointing to the `ServiceIdentity` nodes used in resolution. On identity change, invalidate only edges resolved via the changed identity. Mark invalidated edges `stale` (don't delete).

**Status:** SPEC.md §14 now specifies the `resolved_via` index: each `DEPENDS_ON` edge stores the `ServiceIdentity` ids used in resolution; identity change invalidates only matching edges (`stale: true`); re-resolve on next pass. The `DEPENDS_ON` schema already has `stale BOOLEAN`. Implementation deferred to M5+ (Phase 5), but the spec is now normative. ✅

**H5. Ambiguous-candidate BFS behavior unspecified (`§3`)** · 🟢

§3 says "emit both candidates; ambiguity is surfaced, never auto-resolved." But: does BFS continue with all candidates (can explode), one (biased), or neither (blocks traversal)?

**Fix:** BFS continues with **all** candidates at `confidence=low`, edge carries `ambiguous: true` and `candidates: [list]`. Query layer surfaces with an `ambiguous` flag. Owner resolves via config override (canonical identity map) which promotes confidence.

**Status:** `traversal.py` enqueues all candidates; `ambiguous` flag and `candidates` list are set on each `DependsOn` edge when `len(candidates) > 1`. SPEC.md §10 pseudocode updated with explicit `ambiguous=` assignment. ✅

---

### MEDIUM — Implementation guidance gaps

**M1. Evidence budget for LLM undefined (`§15.2`/`§15.7`)** · 🟢

`evidence = gather(repo)` gives no budget. A 500-file monorepo could produce enormous context. Without a budget: cost explodes, context windows overflow.

**Fix:** Define `evidence_budget` in `LLMRequest`: `max_files`, `max_bytes`. Priority order: CI/CD profile + attribution → extractor output → deploy config → N most-relevant source files (ranked by extractor confidence). Source files pass through the residency gate.

**Status:** SPEC.md §15.2 now specifies the budget (`max_files=20, max_bytes=50_000`, configurable), the priority ordering (attribution → extractor output → deploy config → source files), and the `budget_truncated` flag. `LLMRequest` in `plugins/base.py` already carries the fields. Enforcement implemented in M9 `LLMJudge`. ✅

**M2. Browser fallback (rung 5) should not ship in v0 (`§9`)** · 🟢

Per `archive-context/value-acquisition.md`, browser automation inverts every property of the read-only/least-privilege security posture. The spec gates it but even with gates, it violates the spirit of read-only. Rungs 1-4 cover the target stack well.

**Fix:** Remove rung 5 from v0 scope. Mark `(planned, v1+)` with a security review gate.

**Status:** `resolver.py` comment says "Rungs 1-4, rung 5 (browser) removed from v0." SPEC.md §9 rung 5 updated with `(v1+, deferred from v0)` marker and security rationale. ✅

**M3. `Endpoint` node usage in the pipeline is unclear (`§2`)** · 🟢

§2 defines `Endpoint` nodes and `Deployable —EXPOSES→ Endpoint @env` / `Deployable —CONSUMES→ Endpoint @env`, with `Endpoint —RESOLVES_TO→ Deployable @env` as "the join result." But the traversal in §10 skips this intermediate layer entirely — going straight from consumer ref → reverse index → `DEPENDS_ON`. Are Endpoint nodes actually materialized, or is DEPENDS_ON the only persisted edge?

**Fix:** Clarify: in v0, `DEPENDS_ON` is the materialized edge. `EXPOSES`/`CONSUMES`/`RESOLVES_TO` edges are created as intermediate artifacts during resolution but their persistence is optional (useful for `explain_edge`). The Endpoint node is created when a consumer ref or provider identity resolves to a concrete URL/host — it's the evidence chain, not the primary query surface.

**Status:** SPEC.md §2 updated with v0 note clarifying `DEPENDS_ON` as primary and `EXPOSES`/`CONSUMES`/`RESOLVES_TO` as optional intermediates. No code change needed. ✅ (spec-only)

---

### LOW — Clarity/polish

**L1. `ConfigVar` vs `TokenDecl` relationship unclear (`§2`, `§4.1`)** · 🟢

**Fix:** Add to §2: "ConfigVar nodes are persisted TokenDecl records; the `INJECTED_INTO` edge is created when a token resolves against a variable store."

**Status:** SPEC.md §2 updated with this clarification as a domain-model note. No code change needed for M1-M4. ✅ (spec-only)

**L2. TeamCity CVE warning has no action (`§5`)** · 🟢

**Fix:** Read TeamCity version from `/app/rest/server`; emit `cicd-version-warning` on the provider node if below a documented minimum. The run continues.

**Status:** SPEC.md §5 now specifies the automated check: read `GET /app/rest/server` on init, compare to documented minimum, emit `cicd-version-warning` on the provider node if below, `cicd-version-unknown` if unreadable. Run always continues. Implementation in M7 (TeamCity connector). ✅

---

