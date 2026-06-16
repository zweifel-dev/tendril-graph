# Tasks: Roslyn IntraRepoProvider (M8)

**Input**: Design documents from `/specs/003-roslyn-intrarepo/`

**Prerequisites**: [plan.md](plan.md) · [spec.md](spec.md) · [research.md](research.md) · [data-model.md](data-model.md) · [contracts/](contracts/)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase (different files, no blocking dependency)
- **[Story]**: Maps to spec.md user story (US1 = P1, US2 = P2, US3 = P3)
- Exact file paths in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create all directories, project files, and config wiring so both the Python and
C# tracks can start in parallel.

- [X] T001 Create Python package structure: `tendril/connectors/intra/__init__.py`, `tests/conformance/intra/__init__.py`, `tests/conformance/__init__.py` (if missing), `tests/integration/` (if missing), `tests/fixtures/conformance/intra/roslyn/` directory
- [X] T002 Create C# project file `tendril/analyzers/roslyn/TendrilRoslyn.csproj` targeting `net8.0` with NuGet dependencies: `Microsoft.CodeAnalysis.CSharp`, `Microsoft.CodeAnalysis.Workspaces.MSBuild`, `Microsoft.Build.Locator`, `System.Text.Json` — plus stub file `tendril/analyzers/roslyn/Models/.gitkeep`
- [X] T003 [P] Add `intra_repo.roslyn_binary` config key to `tendril/config.py` (reads `TENDRIL_ROSLYN_BINARY` env var first, then `[intra_repo] roslyn_binary` from `tendril.toml`, no PATH search); verify `IntraRepoProvider` ABC in `tendril/plugins/base.py` exposes `capabilities()`, `matches()`, `analyze()`, `resolve_value()` — extend if any are missing

**Checkpoint**: `pip install -e ".[dev]"` still succeeds; `pytest tests/` still shows 111 passing

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure shared across all three user stories. Complete ALL tasks in
this phase before starting any user story work.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Implement `SubprocessError` class and `SubprocessBridge.__init__`, `__enter__`, `__exit__`, `_close`, `_kill` in `tendril/connectors/intra/subprocess_bridge.py` — `SubprocessError` has fields `method: str`, `message: str`, `code: int`, `restarted: bool`, `detail: dict | None`; `__exit__` sends stdin EOF, waits up to 5s, then kills
- [X] T005 [P] Implement C# model DTOs in `tendril/analyzers/roslyn/Models/`: `IntraRepoFacts.cs` (def_use dict, value_sets dict, call_graph null, partial_analysis, truncated, skipped_files), `ValueSet.cs` (value, source, condition, layer), `ResolvedValue.cs` (resolved=true, value, source, def_use_chain, layer), `Unresolved.cs` (resolved=false, reason enum, detail), `SkippedFile.cs` (path, reason) — all serialize/deserialize via `System.Text.Json`
- [X] T006 Implement `SubprocessBridge._start`, `_handshake`, `_send_recv`, `_read_response` in `tendril/connectors/intra/subprocess_bridge.py` — `_start` spawns `Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=0)` then calls `_handshake`; `_read_response` uses a `threading.Thread(target=_read, daemon=True)` + `t.join(timeout=)` to timeout `readline()`; on timeout kills proc and raises `TimeoutError`; on empty line raises `EOFError` (depends on T004)
- [X] T007 Implement `SubprocessBridge.call()` and `_call_locked()` in `tendril/connectors/intra/subprocess_bridge.py` — `call()` acquires `threading.Lock` (clock starts here per FR-M8-002), selects `analyze_timeout` (120s) or `default_timeout` (30s) by method name, delegates to `_call_locked`; `_call_locked` handles at-most-one restart: on crash kill → `_start()` → retry once → if second failure raise `SubprocessError(restarted=False)`; log `WARNING event="bridge.restart"` with `method`, `attempt`, `binary_path` fields (depends on T006)
- [X] T008 Implement C# `Program.cs` (call `MSBuildLocator.RegisterDefaults()` before any workspace type is referenced, then `await RunServer(ct)`) and `Server.cs` skeleton (JSON-RPC dispatch loop: `StreamReader(Console.OpenStandardInput(), UTF8)`, `StreamWriter(Console.OpenStandardOutput(), UTF8) { AutoFlush=false }`, `ReadLineAsync` loop, `DispatchAsync` switch, `FlushAsync` after every response, `null` return = EOF = clean exit, all exceptions → JSON error response) in `tendril/analyzers/roslyn/` — handlers are stubs returning `JsonRpcError(-32601,"not implemented")` for now (depends on T005)
- [X] T009 Implement `RoslynIntraRepoProvider` class in `tendril/connectors/intra/roslyn_subprocess.py`: constructor takes `binary_path: str | None` (from config) and `bridge_factory`; implement `capabilities()` returning `{layer1: bool, layer2: bool, def_use: bool}` (all-false when binary is None or handshake fails, logs `WARNING event="roslyn-binary-unavailable"`); implement `matches(repo_ir)` returning True if repo contains `.cs`, `.vb`, `web.config`, or `appsettings*.json` files; `analyze()` and `resolve_value()` are stubs raising `NotImplementedError` (depends on T007)

**Checkpoint**: `pytest tests/` still passes 111 tests; `python -c "from tendril.connectors.intra.subprocess_bridge import SubprocessBridge"` imports cleanly; `SubprocessBridge` context-manager lifecycle tested manually against a `cat` subprocess

---

## Phase 3: User Story 1 — .NET Config Value Resolved Without Acquisition Ladder (Priority: P1) 🎯 MVP

**Goal**: `RoslynIntraRepoProvider.resolve_value("LandingPageUrl")` returns `ResolvedValue(value="https://d-ui.prod.example.com", layer=1)` from a `.web.config` fixture using the subprocess bridge end-to-end. This is the M8 primary acceptance criterion.

**Independent Test**: `pytest tests/conformance/intra/ -k "test_resolve_webconfig_layer1"` passes against the golden fixture with no live .NET subprocess.

- [X] T01 [P] [US1] Implement C# `WebConfigParser.cs` in `tendril/analyzers/roslyn/Layer1/WebConfigParser.cs`: use `XDocument.Load(filePath)` to parse `web.config`, locate `<appSettings><add key=... value=...>` elements, yield `(key, value, sourceLocator, condition=null, layer=1)` where `sourceLocator = "web.config:{key}"` relative to `repo_path`; on `XException` add to `skipped_files` with `reason="parse-error"` and continue
- [X] T01 [P] [US1] Implement C# `AppSettingsParser.cs` in `tendril/analyzers/roslyn/Layer1/AppSettingsParser.cs`: enumerate `appsettings.json`, `appsettings.*.json` (sorted by specificity: base < env-specific); use `JsonDocument.Parse(stream)` with flatten-with-`:` (matching ASP.NET Core `IConfiguration` key paths); coerce non-string values (`number → GetRawText()`, `true→"true"`, `false→"false"`, `null→""`); set `condition` = basename of file for env-specific files (e.g., `"appsettings.prod.json"`), `null` for base file; `sourceLocator = "{relative_path}:{flattened_key}"`; on `JsonException` add to `skipped_files` and continue
- [X] T01 [US1] Implement C# `"analyze"` handler in `tendril/analyzers/roslyn/Server.cs`: validate `repo_path` exists; run `WebConfigParser` + `AppSettingsParser` (layer 1); build `IntraRepoFacts` with `layer=1` entries in `value_sets` and `def_use`; set `call_graph=null`, `partial_analysis=false`, `truncated=false`; if serialized JSON > 10 MB set `truncated=true` and keep only top-N symbols ranked by reference count (FR-M8-014); return as JSON-RPC success result (depends on T010, T011, T008)
- [X] T01 [US1] Implement C# `"resolve_value"` handler in `tendril/analyzers/roslyn/Server.cs`: call `analyze` internally for the repo; apply disambiguation tiebreak — (1) layer 2 over layer 1, (2) most-specific config file (by depth/specificity of filename), (3) alphabetical on source locator; return `ResolvedValue` if found, else `Unresolved(reason="not-found")` or `Unresolved(reason="dynamic-value")` for computed values (depends on T012)
- [X] T01 [US1] Implement secret redaction in `RoslynIntraRepoProvider` in `tendril/connectors/intra/roslyn_subprocess.py`: load `[redact_patterns]` from `tendril.toml` (defaults: `*password*`, `*secret*`, `*token*`, `*apikey*`, `*api_key*`, `*connectionstring*`, case-insensitive glob); before returning any `IntraRepoFacts`, filter `value_sets` and `def_use` — for matched key names, substitute with `Unresolved(reason="is-secret")`; do NOT log the matched key name at DEBUG (depends on T009)
- [X] T01 [US1] Implement `RoslynIntraRepoProvider.analyze(repo_path)` in `tendril/connectors/intra/roslyn_subprocess.py`: call `self._bridge.call("analyze", {"repo_path": repo_path})`; deserialize response into `IntraRepoFacts` dataclass; apply secret redaction from T014; on `SubprocessError` return empty `IntraRepoFacts(partial_analysis=True)` with degraded evidence (depends on T014)
- [X] T01 [US1] Implement `RoslynIntraRepoProvider.resolve_value(repo_path, key)` in `tendril/connectors/intra/roslyn_subprocess.py`: call `self._bridge.call("resolve_value", {"repo_path": repo_path, "key": key})`; check if key matches redact patterns first → return `Unresolved(reason="is-secret")`; else deserialize result as `ResolvedValue` or `Unresolved`; on `SubprocessError` return `Unresolved(reason="build-failed")` (depends on T014, T015)
- [X] T01 [US1] Create golden conformance fixture `tests/fixtures/conformance/intra/roslyn/analyze_result.json` covering both layer-1 entries (at minimum: `LandingPageUrl` from `web.config:LandingPageUrl`, `Logging:LogLevel:Default` from `appsettings.json`, `ConnectionStrings:DefaultConnection` from `appsettings.prod.json`) and one layer-2 stub entry (`ServiceUrl` from `src/AppConfig.cs:42`, `layer=2`) — fixture must have `partial_analysis=false`, `truncated=false`, `call_graph=null`
- [X] T01 [US1] Wire `RoslynIntraRepoProvider` into `tendril/core/traversal.py → TraversalEngine._resolve_token()`: if an `IntraRepoProvider` is registered AND `capabilities().get("def_use")` AND `provider.matches(repo_ir)`, call `provider.resolve_value(repo_path, token)` BEFORE descending to the acquisition ladder (rung 0); on `ResolvedValue` record `provenance="declared"`, `confidence="high"`, `evidence=[def_use_chain entries]`, `layer`; on `Unresolved` or `SubprocessError` record `evidence=["intra-repo-provider:degraded", f"reason:{reason}"]` and continue to ladder (depends on T015, T016)
- [X] T01 [US1] Write fixture-mode conformance tests in `tests/conformance/intra/test_roslyn_conformance.py` covering US1 acceptance scenarios: (1) `resolve_value("LandingPageUrl")` returns `ResolvedValue(value="https://d-ui.prod.example.com", def_use_chain=["web.config:LandingPageUrl"], layer=1)`; (2) `analyze()` returns `IntraRepoFacts` with `value_sets["LandingPageUrl"][0].layer == 1`; (3) `resolve_value("NonExistentKey")` returns `Unresolved(reason="not-found")` — all in fixture-mode (no live subprocess, monkeypatch bridge with recorded response from T017)

**Checkpoint**: `pytest tests/conformance/intra/test_roslyn_conformance.py -k "test_resolve_webconfig_layer1 or test_analyze_layer1 or test_not_found"` passes; `pytest tests/` still ≥ 111 passing

---

## Phase 4: User Story 2 — Subprocess Bridge Runs and Recovers (Priority: P2)

**Goal**: Bridge crash-restart, timeout enforcement, and graceful degradation (missing binary) all work correctly. Layer 2 C# AST analysis (`const` declarations, semantic def-use) is implemented and integrated.

**Independent Test**: Integration tests in `tests/integration/test_roslyn_bridge.py` pass using a mock subprocess (no live .NET binary).

- [X] T02 [P] [US2] Implement C# `SyntacticAnalyzer.cs` in `tendril/analyzers/roslyn/Layer2/SyntacticAnalyzer.cs`: for each `.cs`/`.vb` file in `repo_path` call `CSharpSyntaxTree.ParseText(text, path: file)`; walk `FieldDeclarationSyntax` with `const` modifier and `LocalDeclarationStatementSyntax` with `const`; extract `LiteralExpressionSyntax` string values; record `source = "{relative_path}:{line_number}"` (1-indexed); also walk property default values; yield `(key=identifier, value, source, layer=2, condition=null)`; on `IOException` or `CSharpParseException` add to `skipped_files("parse-error")` and continue
- [X] T02 [P] [US2] Implement C# `SemanticAnalyzer.cs` in `tendril/analyzers/roslyn/Layer2/SemanticAnalyzer.cs`: check `MSBuildLocator.CanRegister`; `MSBuildWorkspace.Create()`; `OpenSolutionAsync(solutionPath, ct)`; after load check `workspace.Diagnostics` for `WorkspaceDiagnosticKind.Failure` — classify: message containing "NuGet" or "restore" → `reason="nuget-restore-failed"`, message containing "build" → `reason="build-failed"`, otherwise → `reason="workspace-load-failed"`; for each project skip `Language` ≠ CSharp/VB; walk `INamedTypeSymbol` constants via `GetCompilationAsync`; yield cross-file def-use chains; on any exception set `partial_analysis=true` (depends on T008 — MSBuildLocator.RegisterDefaults() must have run in Main())
- [X] T02 [US2] Integrate layer 2 into C# `"analyze"` handler in `tendril/analyzers/roslyn/Server.cs`: after layer 1 runs, call `SyntacticAnalyzer` (always); attempt `SemanticAnalyzer` (catch exceptions → `partial_analysis=true`); merge results: layer 2 entries augment layer 1 in `value_sets` with `layer=2`; apply layer precedence (layer 2 overrides layer 1 for `resolve_value()`, both preserved in `value_sets`); populate `skipped_files`; set `partial_analysis=true` if semantic fails; enforce 10 MB truncation (depends on T020, T021, T012)
- [X] T02 [US2] Write integration test for `SubprocessBridge` in `tests/integration/test_roslyn_bridge.py`: use a mock Python subprocess (`subprocess.Popen` against a `python -c` echo server); test handshake success, 3 sequential `call()` invocations return correct results, kill subprocess mid-run then next `call()` triggers exactly one restart and returns result or `SubprocessError(restarted=False)`, second failure after restart raises `SubprocessError` with `restarted=False` (depends on T007)
- [X] T02 [P] [US2] Write integration test for capabilities degradation in `tests/integration/test_roslyn_bridge.py`: construct `RoslynIntraRepoProvider(binary_path=None)`; assert `capabilities() == {"layer1": False, "layer2": False, "def_use": False}`; assert `WARNING` with `event="roslyn-binary-unavailable"` is logged (use `pytest caplog`); assert `analyze()` returns empty `IntraRepoFacts` without raising (depends on T009)
- [X] T02 [P] [US2] Write integration test for timeout behavior in `tests/integration/test_roslyn_bridge.py`: mock a subprocess that never responds; assert `call()` raises `SubprocessError` (from `TimeoutError` path) within `default_timeout` seconds; assert bridge can still be used after timeout via restart (depends on T007)

**Checkpoint**: `pytest tests/integration/test_roslyn_bridge.py` passes; `pytest tests/` still ≥ 111 passing; `pytest tests/conformance/intra/` still passes

---

## Phase 5: User Story 3 — Conformance Suite Validates the Provider (Priority: P3)

**Goal**: Full `IntraRepoProvider` conformance suite passes with zero network calls, zero live subprocess, and covers both layer 1 and layer 2 output (CHK021).

**Independent Test**: `pytest tests/conformance/intra/roslyn/` passes on a host with no .NET SDK.

- [X] T02 [US3] Extend `tests/fixtures/conformance/intra/roslyn/analyze_result.json` to include SC-M8-007 layer-2 entry: `value_sets["ServiceUrl"] = [{"value": "https://svc.prod.example.com", "source": "src/AppConfig.cs:42", "condition": null, "layer": 2}]` and matching `def_use["ServiceUrl"] = ["src/AppConfig.cs:42"]`; also add a `partial_analysis: true` variant fixture at `tests/fixtures/conformance/intra/roslyn/analyze_result_partial.json` with only layer-1 data
- [X] T02 [P] [US3] Write conformance test for layer-2 AST resolution in `tests/conformance/intra/test_roslyn_conformance.py` (SC-M8-007): `resolve_value("ServiceUrl")` returns `ResolvedValue(value="https://svc.prod.example.com", source="src/AppConfig.cs:42", layer=2)` from the T026 fixture
- [X] T02 [P] [US3] Write conformance tests for `Unresolved` paths in `tests/conformance/intra/test_roslyn_conformance.py`: (a) `resolve_value("NonExistentKey") == Unresolved(reason="not-found")`; (b) key matching a redact pattern returns `Unresolved(reason="is-secret")`; (c) fixture with `dynamic-value` reason is returned as `Unresolved(reason="dynamic-value")` without fabrication
- [X] T02 [P] [US3] Write conformance test for `partial_analysis=true` in `tests/conformance/intra/test_roslyn_conformance.py`: using the `analyze_result_partial.json` fixture from T026, assert `IntraRepoFacts.partial_analysis == True`; assert no layer-2 entries appear in `value_sets`; assert traversal engine records `source_analysis: partial` in edge evidence (monkeypatch traversal engine call)
- [X] T03 [P] [US3] Write conformance test for `capabilities()` contract in `tests/conformance/intra/test_roslyn_conformance.py`: (a) when fixture is healthy: `capabilities() == {"layer1": True, "layer2": True, "def_use": True}`; (b) when fixture marks binary unavailable: all-false with no exception raised; (c) `matches()` returns True for a fixture with `.cs` files, False for a fixture with only `.py` files
- [X] T03 [US3] Run `pytest tests/` and confirm: (a) all M8 conformance tests pass; (b) baseline of 111 pre-M8 tests continue to pass (SC-M8-003); (c) SC-M8-001 (100% of literal keys in golden fixture resolved), SC-M8-007 (layer-2 ServiceUrl), SC-M8-004 (WARNING log on missing binary) all covered by test assertions

**Checkpoint**: `pytest tests/conformance/intra/` passes with `--no-header -q` showing all green; `pytest tests/ -x` passes without any regression

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Observability, documentation, and hardening that touches multiple stories.

- [ ] T032 [P] Update `docs/architecture.md` to add `RoslynIntraRepoProvider` and `SubprocessBridge` to the architecture diagram; add `TendrilRoslyn` binary as a subprocess node connected to `SubprocessBridge` via `tendril-rpc/v1`
- [ ] T033 [P] Run the full quickstart validation from `specs/003-roslyn-intrarepo/quickstart.md`: verify `pip install -e ".[dev]"` succeeds, `pytest tests/` passes all tests, conformance fixture replay works; fix any documentation errors found

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ──────────────────────────────────────────────────── no deps
    │
Phase 2 (Foundational) ───────────────────────────────────────── depends on Phase 1
    │                                                               BLOCKS all stories
    ├── Phase 3 (US1, P1) 🎯 MVP ─────────────────────────── depends on Phase 2
    │       │
    │       ├── Phase 4 (US2, P2) ──────────────────────── depends on Phase 3
    │       │       │
    │       │       └── Phase 5 (US3, P3) ─────────────── depends on Phase 3+4
    │       │               │
    │       │               └── Phase 6 (Polish) ──────── depends on Phase 5
```

### Within Phase 2

```
T004 (SubprocessError + bridge shell) ──┐
T005 (C# Models) ────────────────────── │ parallel start
T004 → T006 (_start/_handshake/IO) ─────┤
T005 → T008 (C# Server skeleton) ───────┤
T006 → T007 (call() + lock + restart) ──┘
T007 + T003 → T009 (RoslynIntraRepoProvider skeleton)
```

### Within Phase 3 (US1)

```
T010, T011 (C# Layer 1 parsers)  ──────┐ parallel
                                        │
T010+T011 → T012 (analyze handler) ────┤
T012 → T013 (resolve_value handler) ───┤
T009 → T014 (secret redaction) ────────┤
T014 → T015 (analyze() Python) ────────┤ sequential within Python provider
T015 → T016 (resolve_value() Python) ──┘
T017 (fixture) ──────────────────────── can start after T012 design is stable
T015+T016+T017 → T018 (traversal wiring)
T017+T018 → T019 (conformance tests)
```

### Within Phase 4 (US2)

```
T020, T021 (C# Layer 2 analyzers)  ────┐ parallel (different files)
T020+T021 → T022 (integrate layer 2) ──┘
T023, T024, T025 (integration tests) ──┐ parallel with each other
```

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on US2 or US3
- **US2 (P2)**: Can start after Phase 3 complete (needs layer 1 done first to integrate)
- **US3 (P3)**: Can start after Phases 3 and 4 (fixture must cover layer 1 AND layer 2 — CHK021)

---

## Parallel Opportunities

### Phase 2 Parallel Launch

```
# These can start simultaneously (different files):
T004  → subprocess_bridge.py shell
T005  → Models/*.cs (C#)
```

### Phase 3 (US1) Parallel Launch

```
# After Phase 2 complete, start simultaneously:
T010  → Layer1/WebConfigParser.cs
T011  → Layer1/AppSettingsParser.cs
T014  → roslyn_subprocess.py (secret redaction, no C# dep)
```

### Phase 4 (US2) Parallel Launch

```
# After Phase 3 complete, start simultaneously:
T020  → Layer2/SyntacticAnalyzer.cs
T021  → Layer2/SemanticAnalyzer.cs
T023  → tests/integration/test_roslyn_bridge.py (mock bridge)
T024  → tests/integration/test_roslyn_bridge.py (capabilities)
T025  → tests/integration/test_roslyn_bridge.py (timeout)
```

### Phase 5 (US3) Parallel Launch

```
# After T026 fixture extension, start simultaneously:
T027  → conformance test layer-2
T028  → conformance test Unresolved paths
T029  → conformance test partial_analysis
T030  → conformance test capabilities()
```

---

## Implementation Strategy

### MVP First (US1 only — Phases 1–3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (SubprocessBridge + C# server skeleton)
3. Complete Phase 3: US1 (layer 1 parsing + provider + traversal wiring + basic fixture test)
4. **STOP and VALIDATE**: `pytest tests/conformance/intra/ -k "test_resolve_webconfig_layer1"` passes
5. Demo: `tendril graph build` against a .NET WebForms repo resolves `LandingPageUrl` from `web.config`

### Incremental Delivery

1. **Phase 1+2 → Foundation** (Python bridge + C# server shell both working)
2. **Phase 3 → US1 (MVP)**: layer 1 config parsing end-to-end, TraversalEngine wired
3. **Phase 4 → US2**: bridge resilience hardened, layer 2 C# AST added
4. **Phase 5 → US3**: full conformance suite passing, SC-M8-003 baseline verified
5. **Phase 6 → Polish**: architecture diagram updated, quickstart validated

### Parallel Team Strategy (if two developers)

```
Developer A (Python):   T001 → T004 → T006 → T007 → T009 → T014 → T015 → T016 → T018 → T019
Developer B (C#):       T001 → T002 → T005 → T008 → T010 → T011 → T012 → T013 → T020 → T021 → T022
```

Both sync at Phase 2 checkpoint before starting Phase 3.

---

## Notes

- **No live .NET SDK in CI**: All tests in `tests/conformance/` use fixture replay. Tests in `tests/integration/` use a mock Python echo subprocess. The C# binary is only needed for manual validation and building the fixture.
- **bufsize=0 is mandatory**: Never use buffered I/O with `SubprocessBridge` (see research.md §1 gotchas).
- **MSBuildLocator load-order**: `RegisterDefaults()` in `Program.cs` must run before any workspace type is referenced in any called method (research.md §2 gotchas).
- **Secret redaction is Python-side**: The C# binary sends all values; the Python `RoslynIntraRepoProvider` filters before returning to the traversal engine.
- **All [P] tasks**: Different files, no blocking dependency on another in-progress task in the same phase.
- Commit after each completed task or logical group (T010+T011 together, T015+T016 together).
- Stop at each **Checkpoint** to verify the test baseline is maintained.
