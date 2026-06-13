# Contributing to Tendril

Thanks for your interest. Tendril reconstructs the cross-repo dependency graph of a multi-repo estate and serves it to coding agents. The most valuable contributions are **new provider plugins** (more VCS, CI/CD, telemetry, language extractors) and improvements to resolution accuracy — both of which the plugin contract is designed to make possible without touching core.

## Before you start

Read these, in order — they are the source of truth:

- **[`PRD.md`](PRD.md)** — what Tendril is and why.
- **[`SPEC.md`](SPEC.md)** — how it works; the plugin contract is §4.
- **[`CLAUDE.md`](CLAUDE.md)** — the non-negotiable invariants (these apply to humans too).
- **[`docs/architecture.md`](docs/architecture.md)** — the picture.

## Ways to contribute

- **Provider plugins** — a new VCS, CI/CD, telemetry, graph-store, or language extractor. The golden path is below.
- **Resolution quality** — better identity normalization/aliasing, deploy-step detection signatures, scoping emulation, confidence calibration.
- **Core** — the index, traversal, resolver, query layer, MCP server. Higher bar; discuss in an issue first.
- **Docs, examples, fixtures** — always welcome, especially recorded provider fixtures for the conformance suite.

Open an issue before a large change so we can agree on the approach.

## The invariants (do not break these)

These are the design, summarized from `CLAUDE.md`:

1. **Plugin-first** — adding/changing a provider must not require core changes. If you're editing core to add a platform, extend the contract instead (and bump its semver).
2. **The projection join** — edges match a *consumer projection* to a *provider projection*; never reduce to repo-name matching.
3. **Index globally, traverse from the anchor.**
4. **CI/CD is per-repo** — attribution runs before resolution; handle build-vs-deploy handoffs.
5. **Capability detection + graceful degradation** — never assume a feature is enabled; a missing capability must not fail the run.
6. **Provenance + confidence on every edge** (`declared`/`injected`/`observed`, `high`/`medium`/`low`).
7. **Never fabricate** — secrets are masked everywhere; emit `unresolved-secret`/`unresolved-no-source`, and emit candidates (not a silent pick) for ambiguous matches.
8. **Read-only and secret-redacting** — no write paths to any provider; redact secret-typed values before persistence.

A PR that violates an invariant will be asked to change regardless of how useful the feature is.

## Adding a provider (the golden path)

1. Implement the relevant interface from [`SPEC.md §4`](SPEC.md): `VCSProvider`, `CICDProvider`, `ExtractorPlugin`, `TelemetryProvider`, or `GraphStore`.
2. Declare static capabilities; for telemetry, implement `probe()` so the engine can detect what's actually populated.
3. Add a `tendril-plugin.toml` manifest (`id`, `family`, `contract_version`, capabilities).
4. **Pass the conformance suite** against recorded fixtures. The suite is the executable definition of the contract; passing it is what makes a provider "supported." Add fixtures for your provider where coverage is missing.
5. Keep it read-only. If you genuinely cannot express something within the contract, the contract is incomplete — propose a contract change (with a semver bump and a deprecation note for any break), don't work around it in core.

## Development setup

> Placeholders until scaffolding lands — keep this section current as the build matures.

```
# install:   TBD
# build:     TBD
# lint:      TBD
# test:      TBD   (must include the plugin conformance suite)
# run e2e:   TBD   (the Phase-1 slice: github repo → actions → env var → resolved edge)
```

The first milestone runs against **public/sample fixtures** with no private credentials, so anyone can reproduce it.

## Testing

- New code ships with tests. New providers ship with fixtures and **must pass the conformance suite**.
- Prefer **recorded fixtures over live API calls** in tests — deterministic, no credentials, reproducible in CI.
- Output must be **deterministic**: same inputs → same graph; sort nodes/edges deterministically.
- Every edge must carry concrete `evidence[]` (`file:line`, `store:scope:key`, `run-id`). An edge with no evidence is a bug, not a stylistic nit.

## Commit & PR conventions

- Keep PRs focused. For a new provider, the first PR should be the smallest unit that passes conformance for one capability.
- Write clear messages; reference the issue. Conventional Commits (`feat:`, `fix:`, `docs:`) are encouraged.
- **Sign off your commits** under the [Developer Certificate of Origin](https://developercertificate.org/) — add `Signed-off-by: Your Name <you@example.com>` (`git commit -s`). By contributing, you agree your contribution is licensed under Apache-2.0 (see `LICENSE`).
- CI must be green, including the conformance suite, before review.

## The honesty norm

Tendril's entire value is that it **never fabricates an edge or a value** and is honest about how much to trust what it produces. When in doubt, label lower confidence, flag the unresolved case, and surface the ambiguity — don't paper over it to make the graph look more complete. Reviews will push on this specifically.

## Security

Tendril holds read credentials to source and CI/CD systems and maps an organization's topology, so security issues are taken seriously. **Do not open a public issue for a vulnerability.** Report it privately per `SECURITY.md` (planned) or to the maintainers. Never commit credentials or real secret values, including in fixtures — scrub fixtures of anything sensitive.

## License

By contributing, you agree that your contributions are licensed under the **Apache License 2.0** (`LICENSE`). The copyright notice for source files follows the appendix template in `LICENSE` (`Copyright [yyyy] [name of copyright owner]`).
