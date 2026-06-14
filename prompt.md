# prompt.md — Claude Code handoff for Tendril-Graph

You are helping build **Tendril-Graph**, an open-source tool that reconstructs the cross-repo dependency graph of a multi-repo estate from repositories, CI/CD configuration, and (optionally) runtime telemetry, and serves it to coding agents.

Two documents in this repo are your source of truth: **`PRD.md`** (product requirements) and **`SPEC.md`** (technical spec). Read both fully before doing anything.

## Your task

Do **both**, in order, in a single pass:

1. **Critique and improve the spec.** Find gaps, ambiguities, weak assumptions, over-engineering, and missing failure modes. Propose concrete edits (as a diff or a clearly-marked revision section). Be a skeptical senior engineer, not a cheerleader — if something won't work, say so and say why.
2. **Produce an implementation plan.** A phased, buildable plan that an engineer (or you, in Claude Code) can execute, mapped to the roadmap in `PRD.md §10` and the components in `SPEC.md`.

If a requirement in the PRD and a detail in the SPEC conflict, flag it explicitly rather than silently picking one.

## Invariants you must preserve (these are the design, not suggestions)

- **Plugin-first.** VCS, CI/CD, Extractor, Telemetry, and GraphStore are providers behind the versioned contract in `SPEC.md §4`. Core never hardcodes a platform. Adding a provider must not touch core. The conformance suite is the executable definition of the contract.
- **The projection join.** Edges come from matching a service's consumer projection ("I call X") to another's provider projection ("I am reachable as Y"), per environment, with confidence + evidence. Don't reduce this to name-matching.
- **Index globally, traverse from the anchor.** Provider-identity indexing is global across the configured scope; consumer traversal is anchor-bounded. Don't "just follow from the anchor" — that can't close the loop.
- **CI/CD is per-repo.** Attribution (`SPEC.md §7`) runs before resolution and routes each token to the correct store; build owner and deploy owner can differ and chain.
- **Capability detection + graceful degradation.** Never assume a feature is enabled (especially telemetry deploy-tracking and readable variable stores). Probe, then degrade visibly to flagged/lower-confidence output. A missing capability must not fail the run.
- **Honesty over completeness.** Every edge carries provenance (`declared`/`injected`/`observed`/`llm-judged`) and confidence. Secrets are masked everywhere (UI, API, logs) — never fabricate a value or an edge; emit `unresolved-secret`/`unresolved-no-source` and let telemetry or a human fill it.
- **LLM judgment is grounded, not authoritative.** The hard decisions (what a repo reaches, whether a reference matches, what to evaluate next) may be LLM-driven (hybrid mode is the default), but every proposal must be grounded against the reverse index/connectors before it's trusted; ungrounded → flagged low-confidence. A deterministic **structured mode (no LLM)** must remain available. Model access is **BYOK and gateway-agnostic** (LiteLLM/vLLM/Ollama/Bedrock/frontier), with residency routing; redact before any model call.
- **Resolve at the deployed ref, not `main` (FR-24).** For each environment, read config from the exact SHA/branch actually deployed (from the Octopus deployment), and record that ref on every edge. A graph built from the default branch is wrong wherever an environment runs an older ref.
- **Communicate accuracy and uncertainty (FR-25).** Every answer surfaces confidence, provenance, the deployed ref, and an explicit unknowns section. A consumer must distinguish "no dependency" from "could not determine." Favor recall; never imply completeness.
- **Documentation must be runnable (FR-19).** The README must state exact requirements and, **per provider (GitHub, Bitbucket, TeamCity, Octopus, telemetry)**, the credential/token type, scopes, how to create it, where to put it, required access breadth, and any prerequisite that must run prior. Don't leave dangling "TBD" where a real adopter needs a step.
- **Read-only, least-privilege, secret-redacting.** No write paths to any provider. Redact secret-typed values before persistence.

## What a good implementation plan looks like

- **Start with the real v0 vertical slice**: an **ASP.NET WebForms (VB + C#) + Angular** solution, **built in TeamCity, deployed via Octopus, stored in Bitbucket, with associated repos across both Bitbucket and GitHub.** This is deliberately the real slice, not the cheapest one — it puts server-side CI/CD, dual-VCS, deployed-ref resolution, and a mixed VB/C#/Angular codebase in v0. Prove one real `DEPENDS_ON` edge end-to-end: Octopus deployment → **deployed SHA** → read config at that ref → TeamCity VCS-root attribution → convention-based resolution (observe the effective value before re-emulating scoping) → one grounded edge with evidence, confidence, and explicit uncertainty.
- **Seam everything in v0; implement thinly.** Stand up all seven provider interfaces (VCS, CI/CD, Extractor, IntraRepo, Telemetry, GraphStore, LLM) as real contracts in v0, with minimal implementations behind them, so dataflow analysis and LLM judgment are added *behind existing seams* later — additive, never a rewrite. Tech debt that would force a later core rebuild is a defect, not a v0 shortcut (FR-27).
- **Then widen along the contract, not the core:** add the reverse index + resolver (close the loop), per-env Octopus scoping + the acquisition ladder (observe-first ordering), then the remaining connectors and extractors, then `IntraRepoProvider` (Roslyn for VB+C#, Joern cross-language) and grounded LLM judgment — each earning its place against a *measured* resolution gap.
- **Each phase states:** components touched, the plugin interfaces exercised, the test fixtures needed (recorded VCS trees / CI-CD configs / telemetry payloads), the acceptance check, and what's explicitly deferred.
- **Call out the load-bearing hard parts early:** the variable-resolution/acquisition ladder, attribution's deploy-step detection, identity normalization/aliasing, and confidence calibration. Propose how each is tested against a small golden estate.
- **Decide the open questions in `SPEC.md §17`** where you can (graph-store default, plugin ABI language, async edges in/out of v1), with a one-line rationale each; leave the rest as explicit decisions for the owner.

## Constraints & preferences

- Pick the **plugin ABI / reference language** (Python or TypeScript) and justify it in one paragraph; keep the choice consistent across the conformance suite and the first reference providers.
- Favor an **embedded graph store** (Kùzu) unless you can argue concurrency needs Neo4j.
- Keep the first milestone runnable against **public/sample fixtures** (no private credentials) so contributors can reproduce it — this is an OSS project.
- Respect the OSS deliverables in `PRD.md` FR-17 through FR-21 (plugin contract, name, README, architecture diagram, license/contributing/dev-guide/example). The architecture diagram must be committed as source (Mermaid/ASCII/SVG), not a screenshot.

## Decide early: the intra-repo dataflow engine (`IntraRepoProvider`, `SPEC.md §4.8 / §17.9`)

Tendril-Graph needs intra-repo dataflow facts (def-use chains, a reference's value or value-set, call graph) to resolve computed values and to **ground** the LLM. This is a pluggable `IntraRepoProvider`; without it the LLM is back to reasoning over raw source (expensive, ungrounded, residency-leaking), so the engine choice is on the critical path. Recommend an engine (or set) using this rubric — **license is the hard gate**, since adopters run this on their own proprietary code.

Grounded findings (verify if stale):
- **CodeQL** — deepest interprocedural dataflow, covers C#. ❌ Engine licensing forbids use on non-open-source code without a paid GitHub Advanced Security license → **excluded as a bundled default** for a tool run on private code.
- **Joern** — Apache-2.0, code-property-graph + dataflow, imports code without a build env. ✅ License fit. ⚠️ Core languages are C/C++/Java/JS/Python/Kotlin → **C#/.NET not first-class**.
- **Roslyn** — MIT, first-class C#/VB semantic model + dataflow APIs. ✅ The natural **.NET** engine; fills Joern's gap.
- **Semgrep CE / Opengrep** — LGPL-2.1 engine; CE is **intraprocedural only**, cross-file/interprocedural dataflow is Pro (paid) or the Opengrep fork. Useful for breadth/patterns; shallow on cross-file dataflow free.

Rubric, weighted in this order: (1) **license** — legally runnable on proprietary code and redistributable alongside an Apache-2.0 tool (note LGPL linking implications); (2) **language coverage** for the first targets (.NET first → Roslyn; then JS/TS, Java, Python); (3) **dataflow depth** — interprocedural + cross-file, not single-file; (4) **fact extractability** — can def-use / value-sets / call graph be pulled out as queryable data to feed grounding; (5) **ops** — embeddable, runs without a full build, acceptable speed; (6) **maintenance** — active, contributor-friendly.

Starting point to validate (not adopt blindly): **Roslyn for .NET + Joern for cross-language**, behind one `IntraRepoProvider` contract, with reuse-adapters for an org's existing CodeGraph/RepoWise/CodeQL output, and a degrade path (format-parser + grounded LLM) when no engine is available. Justify or override in your plan.

## Output format

1. **Spec critique** — a bulleted list of issues ranked by severity, each with a proposed fix; then a marked-up revision (diff or revised sections) for the changes you're confident about.
2. **Implementation plan** — phased as above, with a short dependency graph of milestones and a "first PR" definition (smallest mergeable unit that produces a real edge).
3. **Decisions & open questions** — what you decided and why; what you're escalating to the owner.

Push back where the spec is wrong or thin. The goal is a plan that survives contact with a real, messy, multi-provider estate — not one that only works when everything is perfectly configured.
