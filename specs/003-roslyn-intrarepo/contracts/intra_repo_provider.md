# Contract: RoslynIntraRepoProvider

**Phase 1 output** | **Date**: 2026-06-15

`RoslynIntraRepoProvider` implements the `IntraRepoProvider` ABC from
`tendril/plugins/base.py`. It wraps `SubprocessBridge` to provide static .NET analysis
behind the standard provider interface.

---

## Interface

```python
# tendril/connectors/intra/roslyn_subprocess.py

from tendril.plugins.base import IntraRepoProvider
from tendril.connectors.intra.subprocess_bridge import SubprocessBridge

class RoslynIntraRepoProvider(IntraRepoProvider):
    """
    IntraRepoProvider implementation backed by the TendrilRoslyn subprocess.
    Thread-safe; one SubprocessBridge instance per provider instance (= per run).
    """

    def capabilities(self) -> dict[str, bool]:
        """
        Returns capability flags.
        All-false when: binary not found, handshake fails, or version incompatible.
        Never raises.

        Keys: {
          "layer1": bool,   # config-file parsing available
          "layer2": bool,   # C# AST analysis available
          "def_use": bool,  # def-use chain resolution available
        }
        """
        ...

    def matches(self, repo_ir: RepoIR) -> bool:
        """
        Returns True if the repo contains .NET files (.cs, .vb, web.config,
        appsettings*.json, *.csproj, *.vbproj, *.sln).
        Must be called before analyze() — if False, analyze() must NOT be called.
        (FR-M8-013 / CHK027)
        """
        ...

    def analyze(self, repo_path: str) -> IntraRepoFacts:
        """
        Run full analysis (layer 1 + layer 2) on the .NET repo at repo_path.
        Clock starts when SubprocessBridge lock is acquired.
        Timeout: 120s (analyze_timeout).

        On partial failure (layer 2 unavailable):
          Returns IntraRepoFacts with partial_analysis=True, layer-1 data only.
          Does NOT raise.

        On complete failure (binary missing / layer 1 fails):
          Returns empty IntraRepoFacts with partial_analysis=True, skipped_files populated.
          Does NOT raise (Principle V — NON-NEGOTIABLE).
        """
        ...

    def resolve_value(self, repo_path: str, key: str) -> ResolvedValue | Unresolved:
        """
        Resolve a single key using the disambiguation tiebreak:
          1. Layer 2 over layer 1
          2. Most-specific config file (appsettings.prod > appsettings)
          3. Alphabetical tiebreak on source locator

        Returns ResolvedValue or Unresolved (never raises SubprocessError to caller).
        Secret keys return Unresolved(reason="is-secret") (CHK006, FR-M8-012).
        """
        ...
```

---

## TraversalEngine Integration

Entry point: `tendril/core/traversal.py → TraversalEngine._resolve_token()`

The traversal engine calls `.matches(repo_ir)` before calling `.analyze()`. If `matches()`
returns False, `analyze()` is not called and the acquisition ladder continues unchanged
(FR-M8-013 / CHK027).

Degradation evidence format (CHK020):
```python
# When binary is missing or analyze times out:
edge.evidence.append("intra-repo-provider:degraded")
edge.evidence.append(f"reason:{reason}")  # e.g., "reason:binary-not-found"
```

`partial_analysis: True` in `IntraRepoFacts`:
- Traversal engine records `source_analysis: partial` in edge evidence (CHK005)
- Callers MUST treat layer-2 def-use chains as absent

---

## Secret Redaction

Secret keys are identified using the patterns from `tendril.toml [redact_patterns]`
(case-insensitive glob). Default patterns (FR-M8-012):
- `*password*`, `*secret*`, `*token*`, `*apikey*`, `*api_key*`, `*connectionstring*`

Redaction happens in the Python layer (not in the C# binary):
- Key matched by redact pattern → `resolve_value()` returns `Unresolved(reason="is-secret")`
- Key names are NOT logged at DEBUG if they match a redact pattern (CHK036)
- Values of secret keys NEVER appear in `IntraRepoFacts.value_sets` (MUST be filtered)

Note: The C# binary sends all values it finds; the Python bridge filters secrets before
returning data to the traversal engine. This keeps the C# side simple and stateless.
