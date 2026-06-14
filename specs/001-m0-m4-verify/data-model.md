# Data Model: M0–M4 Verify and Complete

**Phase**: 1 | **Date**: 2026-06-14 | **Plan**: [plan.md](plan.md)

This document describes the entities and fields directly affected by the three
gap closures. No new entities are introduced; this feature verifies and completes
existing ones.

---

## Entities Modified or Verified

### AcquisitionResult (`tendril/models/ir.py`)

Returned by `Resolver.acquire()`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | `str \| None` | yes | Resolved value, or sentinel |
| `rung` | `str` | yes | Ladder rung that resolved: `"static"`, `"store_api"`, `"preview_api"`, **`"deploy-log"`** (new in Gap 2), `"exhausted"` |
| `evidence` | `list[Evidence]` | yes | Locators for the resolution source |
| `resolved` | `bool` | yes | True only if a real value was obtained |
| `is_secret` | `bool` | no | True if secret-typed; value is None/MASKED |

**Rung 4 contract**: When rung 4 produces a result, `rung` MUST equal exactly
`"deploy-log"` and `evidence[0].locator` MUST follow the format
`"deploy-log:{token_name}"`.

---

### DependsOn edge (`tendril/models/graph.py`)

The materialized inter-repo dependency edge. SC-003 requires all fields below.

| Field | Type | Required | SC-003 exact value |
|-------|------|----------|--------------------|
| `from_id` | `str` | yes | `"bitbucket-dc:acme/webforms-solution"` |
| `to_id` | `str` | yes | `"github:acme/landing-page-ui"` |
| `env` | `str` | yes | `"prod"` |
| `provenance` | `Provenance` | yes | `Provenance.INJECTED` |
| `confidence` | `Confidence` | yes | `Confidence.HIGH` |
| `deployed_ref` | `str` | yes | `"abc123def456"` (SHA from deployment) |
| `evidence` | `list[Evidence]` | yes | ≥ 3 entries (see below) |
| `unknowns` | `list` | yes | `[]` (empty for the golden fixture run) |
| `ambiguous` | `bool` | yes | `False` |
| `candidates` | `list` | no | `[]` when `ambiguous=False` |
| `stale` | `bool` | no | `False` when `deployed_ref` is valid |

**Evidence minimum** (per SC-003 and Evidence Locator Formats in spec):
1. Entry with `"home.aspx"` in locator — iframe consumer reference source file
2. Entry with `"appsettings.prod.json"` in locator — config token declaration file
3. Entry with `"octopus"` in locator — Octopus variable store or deployment run

All locators must conform to the Evidence Locator Formats defined in the spec:
- Source file: `{filename}:{line}`
- Variable store: `{provider}:{project}:{env}:{key}`
- Deployment run: `{provider}:run-{id}`
- Build run: `{provider}:build-{id}`

---

### DeployedRef (`tendril/models/ir.py`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `sha` | `str` | yes | Hex string ≥ 7 chars; `"abc123def456"` in golden fixture |
| `branch` | `str` | yes | VCS branch name |
| `env` | `str` | yes | Environment the ref was deployed to |
| `deployable_id` | `str` | yes | Project/service identifier |
| `deploy_timestamp` | `str` | yes | ISO-8601 timestamp |
| `source` | `str` | yes | Deployment run locator: `"octopus:release:Releases-50"` |

**Malformed-ref edge case** (spec §Edge Cases):
- If `sha` is absent, empty, or < 7 hex chars: `deployed_ref=null`, edge gains
  `stale=True`. Run does not fail.

---

### Conformance Subclass Contracts

These are test classes, not production entities, but they form a contract that
all connector implementations must satisfy.

#### VCS Conformance (GitHub, Bitbucket DC)

Subclass must supply:
- `provider()` → a `VCSProvider` instance using fixture data (no network)
- `sample_repo()` → a `RepoRef` whose data exists in the fixture directory
- `sample_ref()` → a valid ref string (e.g., `"main"`)
- `sample_file_path()` → a path that `provider().read_file(sample_repo(), sample_ref(), path)` can return bytes for

#### CI/CD Conformance (TeamCity, Octopus)

Subclass must supply:
- `provider()` → a `CICDProvider` instance using fixture data (no network)
- `sample_repo()` → a `RepoRef` whose tree exists in fixture data
- `sample_repo_tree()` → a `list[FileEntry]` representing the repo tree
- `sample_pipeline_or_project()` → a pipeline id or project id present in fixtures

Octopus subclass additionally must supply:
- `test_resolve_deployed_ref_returns_sha()` — calls `resolve_deployed_ref("Projects-1", "prod")`, asserts result is non-null and `sha` is ≥ 7 chars

---

## Fixture Schema (new files)

### `tests/fixtures/cicd/octopus/deployments_Projects-1_prod.json`

Format mirrors the existing `deployments.json` (Octopus REST API
`/deployments?projects=...&environments=...&take=1` response shape):
```json
{
  "Items": [
    {
      "Id": "Deployments-101",
      "ReleaseId": "Releases-50",
      "ProjectId": "Projects-1",
      "EnvironmentId": "Environments-1",
      "TaskId": "ServerTasks-3217",
      "Created": "2026-06-10T09:30:00.000+00:00"
    }
  ]
}
```

### `tests/fixtures/cicd/octopus/release_Releases-50.json`

Format mirrors the Octopus REST API `/releases/{id}` response:
```json
{
  "Id": "Releases-50",
  "ProjectId": "Projects-1",
  "Version": "1.0.847",
  "BuildInformation": [
    {
      "VcsCommitNumber": "abc123def456",
      "Branch": "main",
      "VcsCommitUrl": "https://github.com/acme-corp/webforms-solution/commit/abc123def456"
    }
  ]
}
```

### `tests/fixtures/cicd/octopus/task_log_ServerTasks-3217.txt`

Plain text deploy log for rung 4 testing:
```
2026-06-10 09:30:01 [INFO] Starting deployment of webforms-solution 1.0.847
2026-06-10 09:30:05 [INFO] LandingPageUrl=https://d-ui.prod.example.com
2026-06-10 09:30:07 [INFO] Deployment completed successfully
```
