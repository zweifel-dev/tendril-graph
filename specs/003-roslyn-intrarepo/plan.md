# Implementation Plan: Roslyn IntraRepoProvider (M8)

**Branch**: `003-roslyn-intrarepo` | **Date**: 2026-06-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-roslyn-intrarepo/spec.md`

---

## Summary

M8 adds intra-repo static analysis for .NET codebases by wiring a Roslyn-based subprocess
analyzer behind the existing `IntraRepoProvider` ABC. The implementation has two parallel
tracks:

1. **Python track**: `SubprocessBridge` (thread-safe, context-manager subprocess client using
   `threading.Lock` + reader-thread timeout) + `RoslynIntraRepoProvider` (wires the bridge
   to the `IntraRepoProvider` ABC and integrates into `TraversalEngine._resolve_token()`).
2. **C# track**: `TendrilRoslyn` — a net8.0 CLI binary implementing:
   - Layer 1: `web.config` + `appsettings*.json` config-file parsing (always runs, BCL-only)
   - Layer 2a: Syntactic Roslyn analysis (`const` declarations, field initializers, property
     defaults — no build required)
   - Layer 2b: Semantic Roslyn analysis (def-use across files, constant folding — compiled
     workspace, MSBuildWorkspace)
   - `tendril-rpc/v1` JSON-RPC server over stdin/stdout

The result: `.NET` dependency edges carry `layer: 1|2` evidence and higher confidence.

---

## Technical Context

**Language/Version**: Python 3.12+ (bridge + provider) / C# net8.0 (minimum net6.0) for the
analyzer binary

**Primary Dependencies**:
- Python: stdlib only (`subprocess`, `threading`, `json`, `uuid`, `logging`)
- C#: `Microsoft.CodeAnalysis.CSharp` (Roslyn), `Microsoft.Build.Locator`, `System.Text.Json`
  (all BCL or well-known NuGet packages; no HTTP layer)

**Storage**: N/A — analyzer is stateless per-call; results flow through `IntraRepoFacts`
into the existing graph store via the traversal engine

**Testing**: pytest (Python conformance suite + integration tests); no live .NET SDK required
in CI (fixture-mode replay via `tests/fixtures/conformance/intra/roslyn/`)

**Target Platform**: Linux/macOS/Windows (Python side); net8.0 cross-platform (C# side)

**Project Type**: library extension (new provider behind existing `IntraRepoProvider` ABC)
+ subprocess binary (`TendrilRoslyn`)

**Performance Goals**: `analyze()` ≤ 120s per repo (90th-percentile large .NET solution);
`resolve_value()` ≤ 30s per call (clock starts at lock acquisition per FR-M8-002)

**Constraints**: no write paths; no external network in analyzer; secret values redacted
before any persistence; binary PATH not searched (explicit path required for reproducibility)

**Scale/Scope**: Single bridge instance per `tendril graph build` run; one in-flight request
at a time (M8 constraint); one subprocess shared across all .NET repos in the run

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Plugin-First (NON-NEGOTIABLE) | ✅ PASS | `RoslynIntraRepoProvider` implements `IntraRepoProvider` ABC; no core changes required; wires in via existing `TraversalEngine._resolve_token()` |
| II. Projection Join | ✅ PASS | Provider contributes `IntraRepoFacts`; resolution uses existing projection join; M8 does not alter join logic |
| III. Global Index, Anchor Traversal | ✅ PASS | Provider is stateless; global index unaffected; intra-repo analysis is anchor-bounded by design |
| IV. CI/CD Attribution | ✅ PASS | M8 does not alter attribution; analysis runs on the deployed ref |
| V. Capability Detection (NON-NEGOTIABLE) | ✅ PASS | `capabilities()` returns all-false when binary missing or version incompatible; missing binary logs WARNING and does NOT fail the run (FR-M8-010) |
| VI. Evidence-Backed Edges | ✅ PASS | Every resolved value carries `def_use_chain` locators; degraded paths record `evidence=["intra-repo-provider:degraded", "<reason>"]` |
| VII. Non-Fabrication (NON-NEGOTIABLE) | ✅ PASS | `Unresolved` emitted (never guessed) for dynamic, missing, or secret values; `Unresolved.reason` is a typed enum |
| VIII. Grounded LLM Judgment | ✅ PASS | M8 is fully deterministic (no LLM path); structured mode is the only mode |
| IX. Read-Only, Secret-Redacting (NON-NEGOTIABLE) | ✅ PASS | Analyzer is read-only; secret keys redacted before any persistence using `tendril.toml [redact_patterns]` as single source of truth |
| X. Deployed-Ref Accuracy | ✅ PASS | Analysis runs on the repo path at the deployed ref; `repo_path` parameter must reflect the checked-out SHA |

**Post-Phase-1 re-check**: All gates re-verified after contract design — no violations found.
The `SubprocessBridge` and `TendrilRoslyn` designs are entirely read-only; the `IntraRepoFacts`
schema carries full evidence chains; degradation paths are defined for all failure modes.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-roslyn-intrarepo/
├── plan.md              # This file
├── research.md          # Phase 0 output (subprocess + Roslyn patterns)
├── data-model.md        # Phase 1 output (entity schemas)
├── quickstart.md        # Phase 1 output (dev setup)
├── contracts/           # Phase 1 output (interface contracts)
│   ├── subprocess_bridge.md    # SubprocessBridge ABC + protocol
│   ├── intra_repo_provider.md  # RoslynIntraRepoProvider wiring
│   └── tendril_roslyn_rpc.md   # C# server method contracts
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
# Python side (new files)
tendril/connectors/intra/
├── __init__.py
├── roslyn_subprocess.py    # RoslynIntraRepoProvider: IntraRepoProvider ABC impl
└── subprocess_bridge.py    # SubprocessBridge: thread-safe tendril-rpc/v1 client

# C# side (new directory)
tendril/analyzers/roslyn/
├── TendrilRoslyn.csproj
├── Program.cs               # Main() — MSBuildLocator.RegisterDefaults() entry point
├── Server.cs                # JSON-RPC stdin/stdout dispatch loop
├── Layer1/
│   ├── WebConfigParser.cs   # XDocument-based web.config <appSettings> parsing
│   └── AppSettingsParser.cs # System.Text.Json appsettings*.json parsing
├── Layer2/
│   ├── SyntacticAnalyzer.cs # CSharpSyntaxTree walking (const/field/property)
│   └── SemanticAnalyzer.cs  # MSBuildWorkspace + compilation def-use
└── Models/
    ├── IntraRepoFacts.cs     # C# DTO matching JSON schema in spec
    ├── ValueSet.cs
    ├── ResolvedValue.cs
    └── Unresolved.cs

# Conformance fixture (new)
tests/fixtures/conformance/intra/roslyn/
└── analyze_result.json      # Golden fixture covering both layer 1 and layer 2 entries

# Test files (new)
tests/conformance/
└── intra/
    └── test_roslyn_conformance.py   # Fixture-mode replay tests (no .NET SDK required)
tests/integration/
└── test_roslyn_bridge.py    # Python bridge + mock subprocess tests

# Modified files
tendril/core/traversal.py    # TraversalEngine._resolve_token(): wire in RoslynIntraRepoProvider
tendril/plugins/base.py      # IntraRepoProvider ABC (verify/extend if needed)
tendril/config.py            # Add intra_repo.roslyn_binary config key
```

**Structure Decision**: Single-project (Option 1) with a nested C# project at
`tendril/analyzers/roslyn/`. The C# code is kept inside the Python package tree (not a
separate repo) because the binary is a bundled implementation detail, not a public plugin.
The Python plugin ABI wraps it — external consumers see only `IntraRepoProvider`.

---

## Complexity Tracking

> No constitution violations that require justification. The C# subprocess is a
> straightforward plugin implementation pattern already documented in SPEC.md §17.8 and the
> constitution's Technology Stack section ("Roslyn via subprocess JSON-RPC bridge").
