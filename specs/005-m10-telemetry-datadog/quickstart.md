# Quickstart: M10 — Telemetry Cross-Validation (Datadog)

**Date**: 2026-06-15

## Prerequisites

- Tendril-Graph installed: `pip install -e ".[dev]"` from repo root
- A static graph already built (M0–M9): `tendril graph build --anchor ... --fixture-dir ...`
- For live mode: Datadog API key, App key, and site configured

## 1. Fixture Mode (Zero Credentials)

Run reconciliation against recorded Datadog fixtures:

```bash
# Build the static graph first
tendril graph build \
  --anchor bitbucket-dc:PROJ/web-app \
  --env prod \
  --fixture-dir tests/fixtures/golden/vcs \
  --db /tmp/tendril.db

# Run telemetry reconciliation against fixtures
tendril telemetry reconcile \
  --env prod \
  --db /tmp/tendril.db \
  --fixture-dir tests/fixtures/conformance/telemetry/datadog
```

Output: `DivergenceReport` JSON on stdout showing confirmed, static-only, and
runtime-only edges.

## 2. Live Mode (With Datadog Credentials)

Set credentials via environment variables:

```bash
export DD_API_KEY="your-api-key"
export DD_APP_KEY="your-app-key"
export DD_SITE="datadoghq.com"        # or datadoghq.eu, us3.datadoghq.com, etc.

# Optional tuning
export TENDRIL_DD_TIMEOUT_SECONDS=60   # Per-call timeout (default: 60)
export TENDRIL_DD_LOOKBACK_HOURS=24    # Time window for traces/logs/RUM (default: 24)
export TENDRIL_DD_MAX_RESULTS=1000     # Max results per method per env (default: 1000)
```

Or configure via `tendril.toml`:

```toml
[telemetry.datadog]
api_key = "your-api-key"
app_key = "your-app-key"
site = "datadoghq.com"
timeout_seconds = 60
lookback_hours = 24
max_results = 1000
```

Then run:

```bash
# Standalone reconcile
tendril telemetry reconcile --env prod --db /tmp/tendril.db

# Or automatic: graph build runs telemetry when credentials are present
tendril graph build \
  --anchor bitbucket-dc:PROJ/web-app \
  --env prod \
  --fixture-dir tests/fixtures/golden/vcs \
  --db /tmp/tendril.db
```

## 3. Reading the DivergenceReport

```json
{
  "env": "prod",
  "confirmed": [
    {"from_id": "github:acme/web-app", "to_id": "github:acme/api-gateway", "env": "prod"}
  ],
  "static_only": [
    {"from_id": "github:acme/web-app", "to_id": "github:acme/legacy-svc", "env": "prod"}
  ],
  "runtime_only": [
    {
      "from_id": "github:acme/web-app",
      "to_id": "github:acme/analytics-svc",
      "env": "prod",
      "confidence": "high",
      "evidence": [
        {"source_type": "datadog-apm", "locator": "datadog:apm:prod:/api/v1/service_dependencies@2026-06-15T10:30:00Z"}
      ],
      "deployed_ref": null
    }
  ],
  "unknowns": [
    {"service": "payment-svc", "env": "prod", "capability": "apm", "reason": "no-index-match", "candidates": null}
  ],
  "capabilities_probed": {"apm": true, "logs": true, "traces": false, "rum": false},
  "metadata": [
    {"capability": "traces", "reason": "inactive", "message": "capability traces inactive for env prod"}
  ],
  "elapsed_seconds": 3.2
}
```

Key sections:
- **confirmed**: Static edges validated by runtime traffic (no action needed)
- **static_only**: Declared dependencies with no observed traffic (review: stale?)
- **runtime_only**: Undeclared live dependencies — written to the graph automatically
- **unknowns**: Datadog services that couldn't be matched to a repo (needs service-tag mapping)

## 4. Querying Runtime-Discovered Edges

After reconcile, runtime-only edges are in the graph store and queryable:

```bash
# See details of a runtime-discovered edge
tendril query explain-edge \
  --from-id "github:acme/web-app" \
  --to-id "github:acme/analytics-svc" \
  --env prod \
  --db /tmp/tendril.db

# Find repos reachable via any edge (static + observed)
tendril query find-relevant-repos \
  --task "analytics service" \
  --env prod \
  --db /tmp/tendril.db
```

## 5. Running Tests

```bash
# All tests (M0–M10), no credentials required
pytest tests/

# Just M10 tests
pytest tests/conformance/telemetry/ tests/integration/test_telemetry_reconcile.py -v

# Just the conformance suite
pytest tests/conformance/telemetry/test_datadog_conformance.py -v
```

## 6. Adding service-tag Mappings

To improve resolution of Datadog service names to repos, add `service-tag` identities
to your provider data:

```json
{
  "kind": "service-tag",
  "value": "payment-service"
}
```

This maps the Datadog service name `payment-service` (case-sensitive) to the repo that
declares this identity. Add these to your VCS or CI/CD provider's `ProviderIdentity`
output.
