# Quickstart: Roslyn IntraRepoProvider (M8)

**Phase 1 output** | **Date**: 2026-06-15

---

## Prerequisites

**Python side:**
```bash
# From repo root — already satisfied if M0-M7 setup is complete
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

**C# side (for binary development only):**
```bash
# .NET SDK 8.0+ required for TendrilRoslyn development
dotnet --version   # 8.0.x or higher

# Build the binary (from repo root)
cd tendril/analyzers/roslyn
dotnet build -c Release
```

**CI / conformance tests (no .NET SDK needed):**
```bash
# Conformance tests replay the fixture — no binary required
.venv/bin/python -m pytest tests/conformance/intra/ -v
```

---

## Configuration

In `tendril.toml`:
```toml
[intra_repo]
roslyn_binary = "/path/to/TendrilRoslyn"   # or use TENDRIL_ROSLYN_BINARY env var

[redact_patterns]
# Optional: override default secret patterns (case-insensitive glob)
# Defaults: *password*, *secret*, *token*, *apikey*, *api_key*, *connectionstring*
extra = ["*apitoken*"]
```

Or via environment variable (highest priority):
```bash
export TENDRIL_ROSLYN_BINARY=/path/to/TendrilRoslyn
```

---

## Running the Bridge Manually

```python
from tendril.connectors.intra.subprocess_bridge import SubprocessBridge

binary = "/path/to/TendrilRoslyn"
with SubprocessBridge([binary]) as bridge:
    result = bridge.call("analyze", {"repo_path": "/path/to/dotnet-repo"})
    print(result["value_sets"])
```

---

## Running Tests

```bash
# All tests (M0-M8) — must all pass before merge
.venv/bin/python -m pytest tests/ -v

# Conformance suite only (no .NET SDK required)
.venv/bin/python -m pytest tests/conformance/intra/roslyn/ -v

# Bridge unit tests (mock subprocess)
.venv/bin/python -m pytest tests/integration/test_roslyn_bridge.py -v
```

---

## Fixture-Mode Conformance

The conformance tests replay `tests/fixtures/conformance/intra/roslyn/analyze_result.json`.
The fixture MUST cover both layer-1 and layer-2 entries (CHK021/FR-M8-008).

To update the fixture (when the binary output schema changes):
```bash
# Run the binary against the reference fixture repo and capture output
export TENDRIL_ROSLYN_BINARY=/path/to/TendrilRoslyn
.venv/bin/python -c "
from tendril.connectors.intra.subprocess_bridge import SubprocessBridge
import json
with SubprocessBridge(['/path/to/TendrilRoslyn']) as b:
    result = b.call('analyze', {'repo_path': 'tests/fixtures/conformance/intra/roslyn/fixture-repo'})
    print(json.dumps(result, indent=2))
" > tests/fixtures/conformance/intra/roslyn/analyze_result.json
```

---

## Debugging the C# Binary

```bash
# Run the binary directly to inspect RPC exchange
echo '{"id":"test1","method":"handshake","params":{"client_version":"1.0"}}' \
  | /path/to/TendrilRoslyn

# Diagnostics go to stderr
/path/to/TendrilRoslyn 2>roslyn_debug.log
```

---

## Key Files

| File | Purpose |
|------|---------|
| `tendril/connectors/intra/subprocess_bridge.py` | SubprocessBridge (Python) |
| `tendril/connectors/intra/roslyn_subprocess.py` | RoslynIntraRepoProvider |
| `tendril/analyzers/roslyn/Program.cs` | TendrilRoslyn entry point |
| `tendril/analyzers/roslyn/Server.cs` | JSON-RPC dispatch loop |
| `tendril/analyzers/roslyn/Layer1/` | Config-file parsers |
| `tendril/analyzers/roslyn/Layer2/` | Syntactic + semantic analyzers |
| `tests/fixtures/conformance/intra/roslyn/` | Golden fixture (JSON) |
| `tests/conformance/intra/test_roslyn_conformance.py` | Fixture-mode tests |
| `specs/003-roslyn-intrarepo/contracts/` | Interface contracts (this feature) |
