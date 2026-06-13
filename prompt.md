# prompt.md — Claude Code handoff for Tendril

You are helping build **Tendril**, an open-source tool that reconstructs the cross-repo dependency graph of a multi-repo estate from repositories, CI/CD configuration, and (optionally) runtime telemetry, and serves it to coding agents.

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
- **Honesty over completeness.** Every edge carries provenance (`declared`/`injected`/`observed`) and confidence. Secrets are masked everywhere (UI, API, logs) — never fabricate a value or an edge; emit `unresolved-secret`/`unresolved-no-source` and let telemetry or a human fill it.
- **Read-only, least-privilege, secret-redacting.** No write paths to any provider. Redact secret-typed values before persistence.

## What a good implementation plan looks like

- **Start with the cheapest end-to-end vertical slice** that proves the whole pipeline: **GitHub repo → GitHub Actions workflow → GitHub Environment variable → resolved per-env edge → graph → one MCP query.** GitHub Actions is intrinsic and GitHub Environments give readable per-env variables, so this slice needs no external CI/CD server. Get one real `DEPENDS_ON` edge with evidence end-to-end before breadth.
- **Then widen along the contract, not the core:** add the reverse index + resolver (close the loop), then attribution, then the acquisition ladder + Octopus (per-env scoping), then the remaining VCS/CI-CD connectors, then telemetry cross-validation, then the published plugin contract + conformance suite.
- **Each phase states:** components touched, the plugin interfaces exercised, the test fixtures needed (recorded VCS trees / CI-CD configs / telemetry payloads), the acceptance check, and what's explicitly deferred.
- **Call out the load-bearing hard parts early:** the variable-resolution/acquisition ladder, attribution's deploy-step detection, identity normalization/aliasing, and confidence calibration. Propose how each is tested against a small golden estate.
- **Decide the open questions in `SPEC.md §16`** where you can (graph-store default, plugin ABI language, async edges in/out of v1), with a one-line rationale each; leave the rest as explicit decisions for the owner.

## Constraints & preferences

- Pick the **plugin ABI / reference language** (Python or TypeScript) and justify it in one paragraph; keep the choice consistent across the conformance suite and the first reference providers.
- Favor an **embedded graph store** (Kùzu) unless you can argue concurrency needs Neo4j.
- Keep the first milestone runnable against **public/sample fixtures** (no private credentials) so contributors can reproduce it — this is an OSS project.
- Respect the OSS deliverables in `PRD.md` FR-17 through FR-21 (plugin contract, name, README, architecture diagram, license/contributing/dev-guide/example). The architecture diagram must be committed as source (Mermaid/ASCII/SVG), not a screenshot.

## Output format

1. **Spec critique** — a bulleted list of issues ranked by severity, each with a proposed fix; then a marked-up revision (diff or revised sections) for the changes you're confident about.
2. **Implementation plan** — phased as above, with a short dependency graph of milestones and a "first PR" definition (smallest mergeable unit that produces a real edge).
3. **Decisions & open questions** — what you decided and why; what you're escalating to the owner.

Push back where the spec is wrong or thin. The goal is a plan that survives contact with a real, messy, multi-provider estate — not one that only works when everything is perfectly configured.
