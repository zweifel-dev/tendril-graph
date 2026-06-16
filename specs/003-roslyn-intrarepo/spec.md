# Feature Specification: Roslyn IntraRepoProvider (M8)

**Feature Branch**: `003-roslyn-intrarepo`

**Created**: 2026-06-15

**Status**: Draft

**Input**: User description: "within @specs/000-initial-plan/implementation-plan.md and @review.md complete M8 of plan and review @specs/000-initial-plan/PRD.md and @specs/000-initial-plan/SPEC.md and @CLAUDE.md for other relevant context"

---

## Overview

M8 adds **intra-repo static analysis** for .NET codebases (C# and VB.NET) by wiring a Roslyn-based analyzer as a subprocess behind the existing `IntraRepoProvider` contract. This allows Tendril-Graph to resolve config values without touching the acquisition ladder, and without requiring any external static analysis tool to be pre-run by the user.

The analyzer operates in two layers, implemented in order:

1. **Config-file parsing (baseline, layer 1)** — parses `web.config` `<appSettings>` entries and `appsettings*.json` files as XML/JSON. No MSBuild dependency. Always runs. Satisfies the M8 acceptance criterion from `review.md`.
2. **C# AST analysis (layer 2)** — first performs **syntactic analysis** (parses `.cs`/`.vb` files for literal string values in `const` declarations, field initializers, and property defaults — no build required), then attempts **semantic analysis** (resolves references across files and folds constants through def-use chains — requires a successfully compiled workspace). Layer 2 falls back gracefully if MSBuild/NuGet fails, leaving layer 1 results intact.

**Layer precedence**: when the same key exists in both layers, layer 2 takes precedence (C# source overrides config-file defaults at runtime). Both values are preserved in `value_sets` with their respective `layer` field; `resolve_value()` returns the layer-2 result as primary and includes the layer-1 result in the def-use chain as additional evidence.

**Layer observability**: every entry in `value_sets` carries a `"layer"` field (`1` or `2`) so callers can always determine which layer produced a result without interpreting the source locator.

The result: dependency edges derived from .NET repos carry richer evidence, higher confidence, and can resolve references that were previously unresolvable — whether the value lived in a config file or in source code.

This is the **self-provide** path described in SPEC.md §4.8 and §12: Tendril bundles its own engine (Roslyn) for .NET, runs it as a subprocess, and consumes the facts it produces via the `IntraRepoProvider` interface.

---

## Clarifications

### Session 2026-06-15 (speckit.clarify)

- Q: Does the M8 Roslyn analyzer perform full C# AST walking (variable def-use chains in source files) or config-file parsing only? → A: Both — config-file parsing (`web.config` + `appsettings*.json` as XML/JSON) is implemented first as the baseline layer; full C# AST analysis (syntax tree walking, string literal assignments, variable def-use chains in `.cs`/`.vb` source) is layered on top in the same milestone. The AST layer falls back gracefully if MSBuild/compilation fails, so the config-file baseline always works.
- Q: Should there be a separate, longer timeout for the `analyze()` call distinct from the per-message timeout? → A: Yes — `analyze()` gets its own configurable timeout defaulting to 120 seconds (large .NET solutions legitimately need more than 30s); all other calls (e.g., `resolve_value()`) use the 30-second per-message timeout.
- Q: Should `SubprocessBridge` be thread-safe or single-caller-per-instance? → A: Thread-safe — the bridge MUST internally serialize concurrent calls so multiple threads can safely share one instance. The subprocess itself remains single-threaded (one request at a time); the bridge queues concurrent callers.

### Session 2026-06-15 (gap resolution — review.md CHK001–CHK040)

- CHK001: Wire format defined as JSON-RPC 2.0 subset (no batching): `{"id":"<uuid>","method":"<name>","params":{...}}` → `{"id":"<uuid>","result":{...}}` or `{"id":"<uuid>","error":{"code":<int>,"message":"<str>","data":{...}}}`.
- CHK002: `def_use_chain` format: `"<relative_path>:<key_or_line>"`. Config locators use key name (e.g., `"web.config:LandingPageUrl"`); source locators use line number (e.g., `"src/AppConfig.cs:42"`). Always relative to repo root.
- CHK003: `IntraRepoFacts` fully specified; `call_graph` is always `null` in M8.
- CHK004: `ValueSet` condition field is the basename of the most specific config file that provided the value (e.g., `"appsettings.prod.json"`), or `null` for unconditioned values.
- CHK005: `partial_analysis: true` consumer contract — callers MUST treat layer-2 def-use chains as absent; traversal engine records `source_analysis: partial` in edge evidence and continues.
- CHK006: Secret redaction patterns promoted to FR with default glob list and case-insensitive matching; configurable in `tendril.toml`.
- CHK007: Subprocess lifetime = `SubprocessBridge` instance lifetime; teardown via stdin EOF; context manager protocol required.
- CHK008: Binary path via `TENDRIL_ROSLYN_BINARY` env var (highest priority) or `intra_repo.roslyn_binary` in `tendril.toml`; PATH NOT searched by default.
- CHK009: Targets `net8.0`; minimum `net6.0`; documented in binary README.
- CHK010: Handshake message on first connection; version `"1.0"` in M8; incompatible version → capabilities all-false.
- CHK011: Every `value_sets` entry carries `"layer": 1 | 2`.
- CHK012: Layer 2 takes precedence; both values preserved in `value_sets`.
- CHK013: Syntactic analysis (no build) attempted first; semantic analysis (compiled workspace) upgrades it.
- CHK014: Layer 2 failure → `partial_analysis: true`, layer-1 results only, `skipped_files` populated.
- CHK015: 30s timeout clock starts when lock is acquired (request sent), not from queue enqueue time.
- CHK016: `SubprocessError` attributes: `method`, `message`, `code` (JSON-RPC), `restarted: bool`, `detail: dict | None`.
- CHK017: Session = `SubprocessBridge` instance lifetime; one instance per `tendril graph build` run.
- CHK018: `Unresolved.reason` is a typed field with defined values: `"not-found"`, `"dynamic-value"`, `"is-secret"`, `"build-failed"`, `"parse-error"`.
- CHK019: SC-M8-005 clock-start aligned with FR-M8-002 (lock acquired, not queue entry).
- CHK020: Both degradation paths (missing binary, analyze timeout) record `evidence=["intra-repo-provider:degraded", "<reason>"]`.
- CHK021: Fixture covers both layer 1 and layer 2 output; stored at `tests/fixtures/conformance/intra/roslyn/analyze_result.json`.
- CHK022: Both `SubprocessBridge` and traversal engine use `tendril.toml` `[redact_patterns]` as the single source of truth.
- CHK023: SC-M8-001 bounded to the M8 golden fixture (`tests/fixtures/conformance/intra/roslyn/`).
- CHK024: SC-M8-003 rephrased as "all tests passing at M8 start (baseline 111) continue to pass."
- CHK025: SC-M8-007 added for layer-2 AST acceptance criterion.
- CHK026: SC-M8-004 specifies WARNING log level and structured field `event="roslyn-binary-unavailable"`.
- CHK027: FR-M8-013 added: empty `IntraRepoFacts` returned immediately for non-.NET repos; `.matches()` guards `analyze()`.
- CHK028: Version mismatch detected by handshake (CHK010); bridge sets capabilities to all-false with a clear error.
- CHK029: Non-string JSON values serialized to their string representations (`8080` → `"8080"`, `true` → `"true"`).
- CHK030: Layer 2 contradiction with layer 1 resolved by layer precedence rule (CHK012); both preserved in `value_sets`.
- CHK031: Analyzer returns all candidates with locators; `resolve_value()` performs disambiguation using specificity rules (most-specific config file wins; layer 2 over layer 1; alphabetical tiebreak).
- CHK032: `resolve_value()` selects the most specific `ValueSet` entry using the tiebreak in CHK031; callers needing all values use `analyze()` directly.
- CHK033: NuGet restore failures distinguished from build failures: `reason: "nuget-restore-failed"` vs `reason: "build-failed"` vs `reason: "workspace-load-failed"`.
- CHK034: FR-M8-014 added: responses exceeding 10 MB are truncated to top-N symbols with `truncated: true` flag.
- CHK035: No hard memory limit in M8; OOM kills the subprocess and the bridge treats it as a crash-restart scenario.
- CHK036: Bridge logs at WARNING on restart (`bridge.restart`, `method`, `attempt`, `binary_path`); at DEBUG per request cycle (method name; key names excluded if secret-matching).
- CHK037: Callers queued during restart block on the lock; if restart fails all queued callers receive `SubprocessError(restarted=False)`; at most one restart attempt per error event.
- CHK038: Golden fixture already validates XML parsing; assumption confirmed clear.
- CHK039: `id` field preserved in all protocol messages to enable future multiplexing without a breaking change.
- CHK040: FR-M8-011 entrypoint named as `tendril/core/traversal.py → TraversalEngine._resolve_token()`.

---

## Wire Protocol (`tendril-rpc/v1`)

All communication between `SubprocessBridge` and the `TendrilRoslyn` binary uses **newline-delimited JSON** over stdin/stdout. Each message is exactly one line (no embedded newlines in the JSON). The protocol is a subset of JSON-RPC 2.0 — no batching, no notifications.

**Request** (Python → C#):
```json
{"id": "<uuid-v4>", "method": "<method_name>", "params": { ... }}
```

**Success response** (C# → Python):
```json
{"id": "<uuid-v4>", "result": { ... }}
```

**Error response** (C# → Python):
```json
{"id": "<uuid-v4>", "error": {"code": -32603, "message": "build failed", "data": {"reason": "build-failed"}}}
```

**Handshake** (first exchange on every new subprocess):
```json
// Request:
{"id": "handshake", "method": "handshake", "params": {"client_version": "1.0"}}
// Response:
{"id": "handshake", "result": {"server_version": "1.0", "compatible": true}}
```
If `compatible: false`, the bridge MUST close the subprocess and surface `SubprocessError` with a clear version-mismatch message, then set `capabilities()` to all-false. Protocol version in M8 is `"1.0"`.

**Methods** defined in M8:
- `handshake` — version negotiation (see above)
- `analyze` — params: `{"repo_path": "<absolute_path>"}` → `IntraRepoFacts`
- `resolve_value` — params: `{"repo_path": "<absolute_path>", "key": "<key_name>"}` → `ResolvedValue | ValueSet | Unresolved`

**Error codes** (subset of JSON-RPC 2.0):
- `-32700` Parse error
- `-32600` Invalid request
- `-32601` Method not found
- `-32603` Internal error (build failure, OOM, etc.)

The `id` field is present in every message to enable future multiplexing without a breaking protocol change. In M8, the bridge sends one request at a time and correlates by `id`.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — .NET Config Value Resolved Without Acquisition Ladder (Priority: P1)

A developer runs `tendril graph build` against a .NET WebForms solution where the landing page URL is assigned in `web.config` as a literal string (`<add key="LandingPageUrl" value="https://d-ui.prod.example.com"/>`). With M8 in place, Tendril resolves the value directly from the source file via def-use analysis, without going through the variable store API, preview API, or deploy logs. The edge is emitted with provenance `declared` and confidence `high`, and the evidence chain includes the specific file and key that yielded the value.

**Why this priority**: This is the primary value proposition of M8. The acquisition ladder's rungs 1–4 are all read paths against external systems; Roslyn resolution is a pure static analysis path that is always available for .NET repos and always provides a concrete value where the source contains one.

**Independent Test**: Given a golden fixture with a `web.config` containing a literal URL value, run `resolve_value("LandingPageUrl")` via `RoslynIntraRepoProvider` and assert `resolved=True`, `value="https://d-ui.prod.example.com"`, `def_use_chain=["web.config:LandingPageUrl"]`, `layer=1`.

**Acceptance Scenarios**:

1. **Given** a .NET repo fixture containing `web.config` with `<add key="LandingPageUrl" value="https://d-ui.prod.example.com"/>`, **When** `RoslynIntraRepoProvider.resolve_value("LandingPageUrl")` is called, **Then** the result is `ResolvedValue(value="https://d-ui.prod.example.com", resolved=True, def_use_chain=["web.config:LandingPageUrl"], layer=1)` and no acquisition ladder rung is invoked.

2. **Given** the same fixture, **When** `RoslynIntraRepoProvider.analyze(repo_path)` is called, **Then** `IntraRepoFacts.value_sets["LandingPageUrl"]` contains an entry with `layer=1` and the def-use chain traces to the declaring file and key.

3. **Given** a key that does not exist in the repo, **When** `resolve_value("NonExistentKey")` is called, **Then** the result is `Unresolved(reason="not-found")` and no error is raised.

---

### User Story 2 — Subprocess Bridge Runs and Recovers (Priority: P2)

A developer's estate includes both .NET and non-.NET repos. The Roslyn subprocess is spawned only when a repo is identified as .NET, stays alive across multiple calls in the same traversal run, and recovers gracefully if the subprocess exits unexpectedly. Non-.NET repos are unaffected.

**Why this priority**: The subprocess bridge is the plumbing that all future non-Python plugin engines will use (`tendril-rpc/v1`). Correctness and resilience here matters for M8 and every future engine added via the same mechanism.

**Independent Test**: Start `SubprocessBridge`, issue three sequential `call()` invocations, then kill the subprocess externally; assert the next `call()` restarts the subprocess (at most one restart attempt) and returns a result or a well-typed `SubprocessError`.

**Acceptance Scenarios**:

1. **Given** the Roslyn binary is configured and reachable, **When** `SubprocessBridge.call("analyze", {...})` is issued, **Then** the subprocess is spawned, the handshake succeeds, and the subprocess is reused on subsequent calls within the same session (same bridge instance).

2. **Given** the subprocess crashes mid-run, **When** a subsequent `call()` is issued, **Then** the bridge restarts the subprocess once, logs `bridge.restart` at WARNING level, and either returns a result or raises `SubprocessError(restarted=True)`. No unhandled exception propagates to the traversal engine.

3. **Given** the Roslyn binary is missing or fails to start, **When** `RoslynIntraRepoProvider` is initialized, **Then** `capabilities()` returns `{def_use: false, dataflow: false}` and the traversal engine degrades to the acquisition ladder without aborting.

---

### User Story 3 — Conformance Suite Validates the Provider (Priority: P3)

The `RoslynIntraRepoProvider` passes the `IntraRepoProvider` conformance tests using only the bundled golden fixture covering both layer 1 and layer 2 output. No .NET SDK or live subprocess is required.

**Why this priority**: Conformance suites are the executable definition of each provider contract (SPEC.md §4.9). M8 must ship a passing suite so the `IntraRepoProvider` contract is validated end-to-end.

**Independent Test**: `pytest tests/conformance/intra/roslyn/` passes with no network calls and no .NET SDK on the test host.

**Acceptance Scenarios**:

1. **Given** the fixture-mode `RoslynIntraRepoProvider` (replaying `tests/fixtures/conformance/intra/roslyn/analyze_result.json`), **When** the conformance suite runs, **Then** all tests pass with no live subprocess or .NET SDK required.

2. **Given** the conformance suite's `test_resolve_value` test, **When** `resolve_value("LandingPageUrl")` is called against the fixture, **Then** the result matches the golden expected output exactly.

3. **Given** a request for a capability the provider declares as unsupported (e.g., `interprocedural: false`), **When** the caller requests cross-function dataflow, **Then** the provider returns `Unresolved(reason="not-found")` rather than an incorrect value.

---

### Edge Cases

- **Build failure**: When the .NET solution fails to build (missing NuGet packages, incompatible SDK), the analyzer returns `error.data.reason = "build-failed"` (NuGet restore) or `"workspace-load-failed"` (MSBuild error); the bridge surfaces `partial_analysis: true` with only layer-1 results — traversal continues.
- **NuGet restore failure**: Distinguished from build failure with `reason: "nuget-restore-failed"`. Allows operators to diagnose whether it is a network issue vs a code issue.
- **Malformed JSON-RPC response**: The bridge detects the incomplete/invalid read, raises `SubprocessError(code=-32700)`, and kills and restarts the subprocess.
- **Mixed C#/VB.NET solution**: Files the analyzer cannot parse are skipped and recorded in `skipped_files`; the run continues with partial results.
- **Dynamically computed value**: `resolve_value()` returns `Unresolved(reason="dynamic-value")` — never a fabricated value.
- **Duplicate key name across files**: The analyzer returns all candidates with source locators; `resolve_value()` selects by specificity: most-specific config file first (e.g., `appsettings.prod.json` over `appsettings.json`), layer 2 over layer 1, alphabetical tiebreak.
- **Layer 2 contradicts layer 1**: Both values are preserved in `value_sets` with their respective `layer` field; layer 2 is returned as primary by `resolve_value()`.
- **Non-string values in `appsettings*.json`**: Integers, booleans, and arrays are serialized to their JSON string representation (`8080` → `"8080"`, `true` → `"true"`) and included in `value_sets`.
- **Non-.NET repo**: When `analyze()` is called on a repo with no `.cs`, `.vb`, `web.config`, or `appsettings*.json` files, an empty `IntraRepoFacts` is returned immediately without spawning any analysis. The traversal engine is expected to call `.matches(repo_ir)` first to avoid unnecessary calls.
- **Concurrent callers during subprocess restart**: Callers queued on the bridge's internal lock block until restart completes. If restart fails, all queued callers receive `SubprocessError(restarted=False)`. At most one restart attempt per error event.
- **Very large `IntraRepoFacts`**: Responses exceeding 10 MB when serialized are truncated to the top-N most-referenced symbols, with `truncated: true` in the response.
- **`resolve_value()` on a `ValueSet`**: When multiple values exist, `resolve_value()` applies the specificity tiebreak and returns a single `ResolvedValue`. Callers needing the full set call `analyze()` directly and inspect `value_sets`.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-M8-001**: The system MUST provide a `SubprocessBridge` that spawns a child process on first call, keeps it alive for the lifetime of the bridge instance, sends newline-delimited JSON requests over stdin, and reads newline-delimited JSON responses from stdout (`tendril-rpc/v1`). The bridge MUST be thread-safe: concurrent `call()` invocations from multiple threads MUST be serialized internally (one in-flight request at a time); the subprocess itself remains single-threaded. The bridge MUST expose a context manager interface for deterministic teardown.
- **FR-M8-002**: The `SubprocessBridge` MUST enforce a per-call read timeout (default 30 seconds, configurable) for all calls except `analyze()`; the timeout clock starts when the lock is acquired (request sent to subprocess), not from queue enqueue time. A child process that does not respond within the timeout MUST be killed and restarted at most once, and `SubprocessError` returned to the caller.
- **FR-M8-002b**: The `analyze()` call MUST have its own separately configurable timeout (default 120 seconds). If `analyze()` times out, the subprocess is killed, a `SubprocessError` is raised, and an empty `IntraRepoFacts` is returned (triggering graceful degradation). Both degradation paths (missing binary, analyze timeout) MUST record `evidence=["intra-repo-provider:degraded", "<reason>"]` on any affected edges.
- **FR-M8-003**: The system MUST provide a `RoslynIntraRepoProvider` that implements the `IntraRepoProvider` ABC, uses `SubprocessBridge` internally, and declares its capabilities via `capabilities()`. Session lifetime is one `SubprocessBridge` instance per `tendril graph build` run.
- **FR-M8-004**: `RoslynIntraRepoProvider.analyze(repo_path)` MUST return `IntraRepoFacts` produced by two sequential layers: (1) config-file parsing of `web.config` and `appsettings*.json` as XML/JSON (always runs), then (2) C# AST analysis — first syntactic (no build required: `const` declarations, field initializers, property defaults), then semantic (compiled workspace: cross-file def-use chains, constant folding). If layer 2 fails at any sub-step, layer-1 results are returned with `partial_analysis: true` and `skipped_files` populated. Every `value_sets` entry MUST carry `"layer": 1 | 2`.
- **FR-M8-005**: `RoslynIntraRepoProvider.resolve_value(reference)` MUST return a `ResolvedValue` with the concrete string value, source locator, def-use chain, and `layer` field; a `ValueSet` is not returned directly — `resolve_value()` always applies the specificity tiebreak (most-specific config file, layer 2 over layer 1, alphabetical) and returns a single `ResolvedValue`. Returns `Unresolved` when no concrete value can be determined — never a fabricated value. Callers needing the full value set MUST call `analyze()` directly.
- **FR-M8-006**: The Roslyn C# analyzer MUST parse `web.config` `<appSettings>` `<add key=... value=...>` elements and `appsettings*.json` files as XML/JSON (layer 1). Non-string JSON values (integers, booleans) MUST be serialized to their string representations (`8080` → `"8080"`). Additionally, it MUST attempt syntactic AST analysis of `.cs`/`.vb` files (no build required), then semantic analysis if workspace compiles (layer 2). NuGet restore failures are reported as `reason: "nuget-restore-failed"`, distinct from build failures (`"build-failed"`) and workspace-load failures (`"workspace-load-failed"`).
- **FR-M8-007**: The Roslyn C# analyzer MUST handle mixed C#/VB.NET solutions, recording files it cannot parse in `skipped_files` rather than aborting.
- **FR-M8-008**: The system MUST provide a fixture-mode `RoslynIntraRepoProvider` replaying pre-recorded output from `tests/fixtures/conformance/intra/roslyn/analyze_result.json`. This fixture MUST cover both layer-1 entries (config-file keys) and layer-2 entries (AST-derived keys) to fully exercise the two-layer contract.
- **FR-M8-009**: The `RoslynIntraRepoProvider` conformance suite MUST pass with zero network calls and zero live subprocess invocations in CI.
- **FR-M8-010**: When the Roslyn binary is absent, fails the handshake, or fails to start, `RoslynIntraRepoProvider.capabilities()` MUST return `{def_use: false, dataflow: false}`, the bridge MUST log a WARNING with `event="roslyn-binary-unavailable"`, and the traversal engine MUST fall back to the acquisition ladder without aborting.
- **FR-M8-011**: The traversal engine (`tendril/core/traversal.py → TraversalEngine._resolve_token()`) MUST, when an `IntraRepoProvider` is registered and `capabilities().def_use == true` for a .NET repo, call `resolve_value()` before descending to the acquisition ladder — using the provider's result as a pre-ladder resolution step (rung 0).
- **FR-M8-012**: Secret-typed keys MUST NOT appear in the analyzer's `value_sets`. If a key name matches any pattern in `tendril.toml` `[redact_patterns]` (case-insensitive glob; defaults: `*password*`, `*secret*`, `*token*`, `*apikey*`, `*api_key*`, `*connectionstring*`), the analyzer MUST emit it with `value=null` and `is_secret=true`. Both `SubprocessBridge` and the traversal engine use the same `[redact_patterns]` config as the single source of truth.
- **FR-M8-013**: When `analyze()` is called on a repo with no .NET files (no `.cs`, `.vb`, `web.config`, or `appsettings*.json` files at any depth), the analyzer MUST return an empty `IntraRepoFacts` immediately without spawning Roslyn analysis. The traversal engine MUST call `.matches(repo_ir)` on `RoslynIntraRepoProvider` before invoking `analyze()`.
- **FR-M8-014**: Analyzer responses exceeding 10 MB when serialized to JSON MUST be truncated to the top-N most-referenced symbols (ranked by reference count), with `truncated: true` set in the response. The bridge MUST surface this flag in `IntraRepoFacts`.

### Key Entities

**`IntraRepoFacts`** — structured output of `analyze()`:
```json
{
  "def_use": {
    "LandingPageUrl": ["web.config:LandingPageUrl"]
  },
  "value_sets": {
    "LandingPageUrl": [
      {"value": "https://d-ui.prod.example.com", "source": "web.config:LandingPageUrl", "condition": null, "layer": 1}
    ]
  },
  "call_graph": null,
  "partial_analysis": false,
  "truncated": false,
  "skipped_files": []
}
```
- `call_graph` is always `null` in M8 (deferred).
- `partial_analysis: true` when layer 2 failed; callers MUST treat layer-2 def-use chains as absent and record `source_analysis: partial` in edge evidence.
- `skipped_files`: list of `{"file": "<relative_path>", "reason": "<parse-error|build-failed|...>"}`.

**`ResolvedValue`** — single resolved value returned by `resolve_value()`:
```json
{
  "resolved": true,
  "value": "https://d-ui.prod.example.com",
  "source": "web.config:LandingPageUrl",
  "def_use_chain": ["web.config:LandingPageUrl"],
  "layer": 1
}
```

**`ValueSet`** — multiple possible values (held inside `IntraRepoFacts.value_sets`; not returned directly by `resolve_value()`):
```json
[
  {"value": "https://d-ui.prod.example.com", "source": "appsettings.prod.json:LandingPageUrl", "condition": "appsettings.prod.json", "layer": 1},
  {"value": "https://d-ui.staging.example.com", "source": "appsettings.staging.json:LandingPageUrl", "condition": "appsettings.staging.json", "layer": 1}
]
```
`condition`: basename of the most specific config file, or `null` for unconditioned values.

**`Unresolved`** — returned by `resolve_value()` when no concrete value can be determined:
```json
{"resolved": false, "reason": "not-found", "detail": null}
```
Defined `reason` values in M8: `"not-found"` (key absent), `"dynamic-value"` (computed at runtime), `"is-secret"` (key is secret-typed), `"build-failed"` (layer 2 unavailable), `"parse-error"` (file unparseable), `"nuget-restore-failed"`, `"workspace-load-failed"`.

**`SubprocessError`** — raised by `SubprocessBridge.call()` on failure:
```python
SubprocessError(
    method="analyze",        # method that was called
    message="build failed",  # human-readable description
    code=-32603,             # JSON-RPC error code
    restarted=True,          # whether subprocess was successfully restarted
    detail={"reason": "build-failed"}  # optional structured data from error response
)
```

**`SubprocessBridge`** — Python-side client for `tendril-rpc/v1`. Spawns child process on first call, runs handshake, serializes concurrent callers via an internal lock, enforces per-call (30s) and analyze (120s) timeouts, handles restart (at most one per error), and closes the child process via stdin EOF on teardown. Context manager interface: `with SubprocessBridge(command) as bridge: ...`

**`TendrilRoslyn` (C# project)** — subprocess binary. Reads JSON-RPC from stdin, dispatches to the analyzer, writes JSON-RPC to stdout. Single-threaded, one request per message. Exits cleanly on stdin close (EOF). Target framework: `net8.0` (minimum `net6.0`). Binary path configured via `TENDRIL_ROSLYN_BINARY` env var or `intra_repo.roslyn_binary` in `tendril.toml`; PATH is NOT searched.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-M8-001**: For 100% of literal-value keys in the M8 golden fixture (`tests/fixtures/conformance/intra/roslyn/`), `resolve_value()` returns the correct value with `resolved=True` — and no acquisition ladder rung is invoked for those values.
- **SC-M8-002**: The full conformance suite for `RoslynIntraRepoProvider` passes (0 failures) in CI with no .NET SDK and no live subprocess.
- **SC-M8-003**: All tests passing at the start of M8 development (baseline: 111) continue to pass after M8 is merged (no regression).
- **SC-M8-004**: When the Roslyn binary is missing, `tendril graph build` completes successfully (no crash), degrades to the acquisition ladder, and logs a WARNING with structured field `event="roslyn-binary-unavailable"` (testable via `caplog`).
- **SC-M8-005**: A subprocess unresponsive on a non-analyze call is detected within 30 seconds of the lock being acquired; an unresponsive `analyze()` call is detected within 120 seconds of the lock being acquired. In both cases the traversal run continues without hanging.
- **SC-M8-006**: The M8 acceptance criterion from `review.md` passes end-to-end: given VB.NET `web.config` with `<add key="LandingPageUrl" value="https://d-ui.prod.example.com"/>`, `resolve_value("LandingPageUrl")` returns `ResolvedValue(value="https://d-ui.prod.example.com", resolved=True, def_use_chain=["web.config:LandingPageUrl"], layer=1)`.
- **SC-M8-007**: Given a .NET repo fixture where `AppConfig.cs` contains `private const string ServiceUrl = "https://svc.prod.example.com";`, `resolve_value("ServiceUrl")` returns `ResolvedValue(value="https://svc.prod.example.com", resolved=True, def_use_chain=["AppConfig.cs:3"], layer=2)`. (Layer-2 AST acceptance criterion.)

---

## Assumptions

- M4 is complete (traversal engine and acquisition ladder exist). M8 is additive — it inserts a pre-ladder step (rung 0) via FR-M8-011.
- The Roslyn binary (`TendrilRoslyn`) is built separately via `dotnet publish` and is NOT auto-built during `pip install`. Path is configured via `TENDRIL_ROSLYN_BINARY` env var (highest priority) or `intra_repo.roslyn_binary` in `tendril.toml`. PATH is NOT searched.
- Target framework: `net8.0`; minimum supported: `net6.0`. Documented in binary README.
- For CI and conformance tests, the Roslyn binary is not required — fixture-mode replay is used instead.
- The subprocess protocol (`tendril-rpc/v1`) uses the `id` field in all messages to support future multiplexing without a breaking protocol change. In M8, one request is in-flight at a time; the `id` is used for correlation validation only.
- VB.NET config files (`web.config`, `appsettings.*.json`) are parsed as XML/JSON (layer 1) — no VB.NET compilation required. This is validated by the M8 golden fixture.
- Layer 2 syntactic analysis (parsing `.cs`/`.vb` for literal values) does not require a successful build. Layer 2 semantic analysis (cross-file def-use) requires a compiled workspace. If semantic fails, syntactic results are still returned.
- Cross-language, cross-process value stitching is explicitly out of scope for M8 (deferred to M9).
- `SubprocessBridge` is general-purpose (not .NET-specific) so future non-Python engines (e.g., Joern) can use the same bridge and protocol without modification.
- Both `SubprocessBridge` and the traversal engine use `tendril.toml` `[redact_patterns]` as the single source of truth for secret key detection (case-insensitive glob). Default patterns: `*password*`, `*secret*`, `*token*`, `*apikey*`, `*api_key*`, `*connectionstring*`.
- No hard memory limit on the subprocess in M8. OOM kills the subprocess; the bridge treats this as a crash-restart scenario. Operators on memory-constrained hosts can use `analyze_timeout_secs` to bound indirectly.
- Subprocess lifetime = `SubprocessBridge` instance lifetime = one `tendril graph build` run. Teardown via stdin EOF; context manager protocol is the primary interface.
- M8 is independent of M5–M7 and can be developed in parallel.
