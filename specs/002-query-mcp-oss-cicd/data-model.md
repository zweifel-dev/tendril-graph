# Data Model: Query Layer, MCP Server, OSS Hygiene, CI/CD Breadth (M5–M7)

**Date**: 2026-06-15
**Feature**: 002-query-mcp-oss-cicd

---

## New Types (M5)

### `UnknownsEntry` (dataclass)

Represents one item in the `unknowns` list of a `QueryResult`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `kind` | `str` (enum) | Yes | One of: `unresolved-ref`, `unresolved-secret`, `no-source`, `stale-data`, `ambiguous-match`, `no-match` |
| `description` | `str` | Yes | Human-readable explanation |
| `repo_id` | `str \| None` | No | The repository involved, if known |
| `token` | `str \| None` | No | The variable or reference that could not be resolved |
| `candidates` | `list[str] \| None` | No | Repo IDs for `ambiguous-match` kind only |

### `QueryResult` (dataclass)

Top-level response object for all five query operations.

| Field | Type | Required | Notes |
|---|---|---|---|
| `operation` | `str` | Yes | Tool name (e.g., `find_relevant_repos`) |
| `env` | `str` | Yes | Environment queried |
| `results` | `list[dict[str, Any]]` | Yes | May be empty; per-operation shape below |
| `confidence` | `str` | Yes | Weakest link: `high`, `medium`, or `low` |
| `provenance` | `str` | Yes | Most conservative: `declared`, `injected`, `observed`, or `llm-judged` |
| `deployed_refs` | `dict[str, str]` | Yes | `repo_id → sha`; empty `{}` when no deployments, never `None` |
| `unknowns` | `list[UnknownsEntry]` | Yes | Empty `[]` when nothing unresolved, never `None` |
| `metadata` | `dict[str, Any]` | Yes | Always present; empty `{}` by default |

**Per-operation `results` entry minimum fields** (all operations):

| Field | Type | Notes |
|---|---|---|
| `repo_id` | `str` | Deployable ID |
| `confidence` | `str` | Edge or path confidence |
| `provenance` | `str` | Edge or path provenance |
| `deployed_ref` | `str \| None` | SHA for this repo in this env; `null` if unavailable |

Additional per-operation fields are additive (e.g., `hop_depth` for `find_relevant_repos`, `path_length` for `dependency_path`, `diff_type` for `env_diff`).

### `ErrorResponse` (dataclass / dict)

Returned on all `4xx`/`5xx` responses.

| Field | Type | Notes |
|---|---|---|
| `error.code` | `int` | Mirrors the HTTP status code |
| `error.message` | `str` | Human-readable description |

---

## New Pydantic Input Models (M5 — `tendril/mcp/schema.py`)

### `FindRelevantReposInput`
| Field | Type | Default | Notes |
|---|---|---|---|
| `task` | `str` | required | Keyword description of the task |
| `env` | `str` | required | Environment to query |
| `max_hops` | `int` | `3` | BFS depth limit |
| `min_confidence` | `str` | `"low"` | Filter threshold |

### `ImpactAnalysisInput`
| Field | Type | Default |
|---|---|---|
| `repo_id` | `str` | required |
| `env` | `str` | required |
| `min_confidence` | `str` | `"low"` |

### `DependencyPathInput`
| Field | Type | Default |
|---|---|---|
| `from_id` | `str` | required |
| `to_id` | `str` | required |
| `env` | `str` | required |

### `EnvDiffInput`
| Field | Type | Default |
|---|---|---|
| `repo_id` | `str` | required |
| `env_a` | `str` | required |
| `env_b` | `str` | required |

### `ExplainEdgeInput`
| Field | Type | Default |
|---|---|---|
| `from_id` | `str` | required |
| `to_id` | `str` | required |
| `env` | `str` | required |

---

## New CI/CD Provider Types (M7)

### `GitHubActionsProvider` (implements `CICDProvider`)

Reads `.github/workflows/*.yml`. Produces `PipelineBinding[]` from `jobs.<job_id>.environment` fields.

**State transitions for a workflow file**:
1. File exists, has `environment:` blocks → produce bindings with `roles=[deploy]`
2. File exists, no `environment:` blocks → produce bindings with `roles=[build]`, emit `cicd-profile-note`
3. File is invalid YAML → skip file, emit `cicd-profile-note`, continue

**Variable entry schema** (from GitHub Environments API):
- `vars.*` → `VarEntry(key, value=<string>, is_secret=False, readable=True)`
- `secrets.*` → `VarEntry(key, value=None, is_secret=True, readable=False)`

### `BitbucketPipelinesProvider` (implements `CICDProvider` — stub)

Reads `bitbucket-pipelines.yml`. Produces `PipelineBinding[]` from `deployment:` fields.

**YAML paths scanned**: `pipelines.branches.<pattern>.steps[].deployment`, `pipelines.pull-requests.<pattern>.steps[].deployment`, `pipelines.custom.<name>.steps[].deployment`, `pipelines.default.steps[].deployment`

**v0 scope**: `id()`, `capabilities()`, `discover_for_repo()` only. Variable store reads return empty `VariableStore`.

---

## Existing Schema (Kùzu — unchanged)

The query engine reads these existing node/edge tables:

| Table | Key fields read by query engine |
|---|---|
| `Deployable` | `id`, `repo_id`, `kind`, `name` |
| `Repo` | `id`, `name`, `provider`, `org` |
| `Environment` | `id`, `canonical_name` |
| `DeployedRef` | `id`, `sha`, `env`, `deployable_id` |
| `DEPENDS_ON` (edge) | `env`, `provenance`, `confidence`, `evidence`, `deployed_ref`, `ambiguous`, `stale` |

No schema changes required for M5 or M7.

---

## Golden Fixture Output Schema (`expected/depends_on_prod.json`)

```json
{
  "from_id": "bitbucket-dc:acme/webforms-solution",
  "to_id": "github:acme/landing-page-ui",
  "env": "prod",
  "provenance": "injected",
  "confidence": "high",
  "deployed_ref": "abc123def456",
  "evidence_contains": ["home.aspx", "appsettings.prod.json", "octopus"],
  "unknowns": []
}
```
