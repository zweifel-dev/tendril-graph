# Research: Roslyn IntraRepoProvider (M8)

**Phase 0 output** | **Date**: 2026-06-15 | **Plan**: [plan.md](plan.md)

All NEEDS CLARIFICATION items resolved (40/40 via speckit.clarify + review.md resolution).
This document consolidates implementation-ready patterns for the four key technical areas.

---

## 1. Python Thread-Safe Subprocess Bridge

### Decision
Use `subprocess.Popen` with `bufsize=0` (binary, unbuffered), a single `threading.Lock` for
call serialization, and a reader-thread trick for `readline()` timeout enforcement.

### Rationale
- `communicate()` is unsuitable — it reads until EOF, not per-message.
- `bufsize=0` (unbuffered binary I/O) is mandatory; buffered mode silently holds the newline
  until the buffer fills, causing the C# side to never receive the request.
- The reader-thread trick (`threading.Thread(target=_read, daemon=True)` + `t.join(timeout=)`)
  is the only portable way to get a timeout on a blocking `readline()` from a `Popen` stdout.
- The lock must be held for the **entire** write+read cycle — releasing between write and read
  allows another thread to interleave a second write before the first response arrives.
- `daemon=True` on the reader thread ensures it doesn't prevent process exit; it unblocks
  when `_kill()` closes the subprocess stdout.

### Key patterns

```python
# SubprocessBridge skeleton (see contracts/subprocess_bridge.py for full interface)
class SubprocessBridge:
    def __init__(self, command, default_timeout=30.0, analyze_timeout=120.0):
        self._command = command
        self._default_timeout = default_timeout
        self._analyze_timeout = analyze_timeout
        self._lock = threading.Lock()
        self._proc = None

    def __enter__(self): return self
    def __exit__(self, *_): self._close()

    def _close(self):
        if self._proc:
            self._proc.stdin.close()   # EOF → child ReadLine returns ""
            try: self._proc.wait(timeout=5)
            except: self._proc.kill()
            finally: self._proc = None

    def _start(self):
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,          # CRITICAL: unbuffered binary
        )
        self._handshake()

    def _read_response(self, timeout):
        result, exc = [], []
        def _read():
            try: result.append(self._proc.stdout.readline())
            except Exception as e: exc.append(e)
        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            self._kill()
            t.join(timeout=2)
            raise TimeoutError(f"no response within {timeout}s")
        if exc: raise exc[0]
        raw = result[0]
        if not raw: raise EOFError("subprocess exited")
        return json.loads(raw.decode())

    def call(self, method, params):
        timeout = self._analyze_timeout if method == "analyze" \
                  else self._default_timeout
        with self._lock:   # clock starts here (FR-M8-002 / CHK015)
            return self._call_locked(method, params, timeout, _restarted=False)
```

### Alternatives considered
- **asyncio.create_subprocess_exec** — rejected: Tendril core is sync; adding an event loop
  for one subprocess adds complexity without benefit in M8.
- **multiprocessing.Process** — rejected: overkill; we need IPC, not process isolation.
- **`proc.communicate(timeout=)`** — rejected: reads until EOF; incompatible with a long-lived
  server process that keeps stdin open.

### Gotchas
- `bufsize=0` is the single most common footgun for subprocess JSON-RPC.
- Holding the lock for write+read is mandatory; `id`-based multiplexing (CHK039) is reserved
  for a future protocol version.
- On subprocess crash: at-most-one restart per error event (CHK037). If restart fails, all
  queued callers receive `SubprocessError(restarted=False)`.

---

## 2. C# Roslyn Workspace Initialization

### Decision
Use `Microsoft.Build.Locator.MSBuildLocator.RegisterDefaults()` at the very top of `Main()`
before any workspace types are loaded. Support syntactic-only fallback for the no-build path.

### Rationale
- `MSBuildLocator.RegisterDefaults()` locates the installed .NET SDK / VS Build Tools at
  runtime without requiring `dotnet` on PATH — it uses the .NET host's own install location.
- **Load-order constraint**: this call must happen before any `Microsoft.Build.*` or
  `Microsoft.CodeAnalysis.MSBuild.*` type is JIT-loaded. Violating this causes
  `TypeLoadException` or `MissingMethodException` at runtime, not at compile time.
- Wrap in `if (MSBuildLocator.CanRegister)` to handle re-registration gracefully.

### Key patterns

```csharp
// Program.cs — MUST be at the very top of Main()
if (MSBuildLocator.CanRegister)
    MSBuildLocator.RegisterDefaults();

// Only reference workspace types AFTER RegisterDefaults()
await RunServer();
```

```csharp
// Syntactic layer (layer 2a) — no build, no workspace
var tree = CSharpSyntaxTree.ParseText(sourceText, path: filePath);
// → walk FieldDeclarationSyntax with const modifier for string literals

// Semantic layer (layer 2b) — requires compiled workspace
using var workspace = MSBuildWorkspace.Create();
var solution = await workspace.OpenSolutionAsync(solutionPath, ct);
var hasBuildFailures = workspace.Diagnostics
    .Any(d => d.Kind == WorkspaceDiagnosticKind.Failure);
```

### Alternatives considered
- **`dotnet script` / `dotnet-exec`** — rejected: requires dotnet on PATH; adds runtime dep.
- **Omnisharp.NET** — rejected: HTTP server overhead; wrong abstraction for batch analysis.
- **Reflection-based MSBuild loading** — rejected: fragile; `MSBuildLocator` is the official
  supported path.

### Gotchas
- `MSBuildWorkspace.OpenSolutionAsync()` does NOT throw on build failure — it returns and
  populates `workspace.Diagnostics`. Always check diagnostics after the call.
- Distinguish failure reasons: NuGet restore failure → "NuGet" / "restore" in diagnostic
  message → `reason: "nuget-restore-failed"`. Compilation failure → `reason: "build-failed"`.
  Project load failure → `reason: "workspace-load-failed"` (CHK033).
- Mixed C#/VB.NET solutions: `MSBuildWorkspace` handles them natively. Skip unsupported
  project languages by checking `project.Language` (CHK029).

---

## 3. Config File Parsing (Layer 1, No Roslyn)

### Decision
Use `System.Xml.Linq.XDocument` for `web.config` and `System.Text.Json.JsonDocument` for
`appsettings*.json`. Both are BCL-only — zero additional NuGet dependencies.

### Rationale
- `XDocument` (LINQ to XML) is cleaner than `XmlDocument` for null-safe attribute access.
- `JsonDocument` on net8.0 is zero-allocation for parsing and does not need `Newtonsoft.Json`.
- Flatten `appsettings.json` with `:` separator to match ASP.NET Core `IConfiguration` key
  paths (e.g., `ConnectionStrings:DefaultConnection`, `Logging:LogLevel:Default`).

### Key patterns

```csharp
// web.config parsing
var doc = XDocument.Load(filePath);
var appSettings = doc.Root?.Descendants("appSettings").FirstOrDefault();
foreach (var add in appSettings?.Elements("add") ?? [])
{
    var key = (string?)add.Attribute("key");
    var value = (string?)add.Attribute("value");
    if (key != null && value != null) yield return (key, value, null);
}

// appsettings*.json parsing (with flattening)
using var doc = JsonDocument.Parse(stream);
foreach (var (k, v) in FlattenJson(doc.RootElement, ""))
    yield return (k, v, conditionFromFilename);

// Non-string coercion (CHK029)
var strValue = el.ValueKind switch {
    JsonValueKind.String => el.GetString()!,
    JsonValueKind.Number => el.GetRawText(),
    JsonValueKind.True   => "true",
    JsonValueKind.False  => "false",
    JsonValueKind.Null   => "",
    _                    => el.GetRawText(),
};
```

### Alternatives considered
- `Newtonsoft.Json` — rejected: unnecessary NuGet dependency; `System.Text.Json` suffices.
- `XmlDocument` — rejected: inferior null-safety vs `XDocument`.
- Pre-parse with `System.Configuration.ConfigurationManager` — rejected: requires app domain;
  not suitable for parsing external repos' config files.

### Gotchas
- `JsonDocument` is `IDisposable`; `JsonElement` values become invalid after the owning
  document is disposed. Extract all values before the `using` block closes.
- `web.config` files commonly have `<?xml version="1.0" encoding="utf-8"?>` declarations;
  `XDocument.Load(filePath)` handles encoding correctly (reading strings first via
  `File.ReadAllText()` can lose encoding information).
- `condition` for a `ValueSet` entry: set to the **basename** of the most specific
  `appsettings.*.json` file (e.g., `"appsettings.prod.json"`); null for `web.config`
  entries and for `appsettings.json` base file (CHK004).

---

## 4. C# JSON-RPC 2.0 Minimal stdin/stdout Server

### Decision
Use `Console.OpenStandardInput()`/`Console.OpenStandardOutput()` (not `Console.In`/`Console.Out`),
`StreamWriter` with `AutoFlush = false`, and explicit `FlushAsync()` after every response.

### Rationale
- `Console.OpenStandardOutput()` bypasses the `TextWriter` layer that may apply platform
  CRLF normalization on Windows. Python's `readline()` splits on `\n`, so a `\r\n` in the
  response line causes a JSON parse failure on the Python side.
- `AutoFlush = false` + explicit `FlushAsync()` is the only guarantee that Python's blocking
  `readline()` unblocks immediately after each response. With `AutoFlush = true` the runtime
  may still buffer internally.
- `stdin.ReadLineAsync()` returning `null` == EOF == Python closed stdin == clean teardown
  signal. No special "quit" message is needed.

### Key patterns

```csharp
using var stdin  = new StreamReader(Console.OpenStandardInput(),
                       Encoding.UTF8, detectEncodingFromByteOrderMarks: false);
using var stdout = new StreamWriter(Console.OpenStandardOutput(), Encoding.UTF8)
                   { AutoFlush = false };

string? line;
while ((line = await stdin.ReadLineAsync(ct)) is not null)
{
    var request  = JsonNode.Parse(line) as JsonObject;
    var requestId = request?["id"]?.GetValue<string>();
    try
    {
        var result   = await DispatchAsync(request!, ct);
        var response = new JsonObject { ["id"] = requestId, ["result"] = result };
        await stdout.WriteLineAsync(response.ToJsonString());
        await stdout.FlushAsync(ct);    // CRITICAL: unblocks Python readline()
    }
    catch (Exception ex)
    {
        var err = new JsonObject {
            ["id"]    = requestId,
            ["error"] = new JsonObject {
                ["code"] = -32603, ["message"] = ex.Message,
            }
        };
        await stdout.WriteLineAsync(err.ToJsonString());
        await stdout.FlushAsync(ct);
    }
}
// null return = stdin EOF = clean shutdown (FR-M8-001/CHK007)
```

### Alternatives considered
- HTTP server (ASP.NET Minimal API) — rejected: subprocess-bridge pattern specifically avoids
  network dependencies; stdin/stdout is simpler for a single-consumer tool.
- Named pipes — rejected: platform-specific setup; stdin/stdout is portable.
- `Console.In`/`Console.Out` — rejected: CRLF risk on Windows; encoding layer interference.

### Gotchas
- Every non-RPC output (startup logs, diagnostics) MUST go to `stderr`, never `stdout`.
  Anything on stdout that is not valid newline-terminated JSON causes a `json.JSONDecodeError`
  in the Python bridge, triggering a crash-and-restart cycle.
- The dispatch loop is intentionally single-threaded. The Python bridge serializes with a
  lock; the C# server processes one message at a time. Async I/O within `HandleAnalyzeAsync`
  is fine, but the `await` chain must not process the next stdin line while the current
  handler is running.
- `JsonDocument` for the inner payload (typed `IntraRepoFacts`) vs `JsonNode` for the outer
  envelope (dynamic dispatch). Use `JsonSerializer` with typed POCOs for known payloads.

---

## Summary: Cross-Cutting Gotchas

| Area | Gotcha | Fix |
|------|--------|-----|
| Python Popen | Buffered I/O holds data | `bufsize=0` + explicit `flush()` |
| Python reader | `readline()` blocks forever | Reader thread + `join(timeout=)` + `kill()` |
| Python lock | Interleaved writes | Hold lock for entire write+read cycle |
| C# MSBuildLocator | Load-order `TypeLoadException` | `RegisterDefaults()` before any workspace type |
| C# stdout | `readline()` never unblocks | `AutoFlush=false` + explicit `FlushAsync()` per response |
| C# stdout | CRLF on Windows | `Console.OpenStandardOutput()` raw stream |
| C# stderr | Diagnostic on stdout → bridge parse failure | All non-RPC output to stderr only |
| C# JsonDocument | `JsonElement` invalid after dispose | Extract before `using` closes |
| C# NuGet vs build | Undifferentiated failure | Check `workspace.Diagnostics` message for "NuGet"/"restore" |
