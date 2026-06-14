# Feature Specification: M0–M4 Core Implementation — Verify and Complete

**Feature Branch**: `001-m0-m4-verify`

**Created**: 2026-06-14

**Status**: Draft (v2 — updated per milestone-verification.md checklist)

**Input**: Building out milestones M0 through M4 from PRD.md and critique-plan.md,
verified against review.md's high-level completion analysis (whose accuracy is not assumed).

**Self-contained note**: All facts cited from review.md are inlined below so this spec
can be used as the sole reference for PR evaluation without consulting external documents.

**References**:
- `spec/initial-plan/PRD.md` — product requirements and phased roadmap
- `spec/initial-plan/critique-plan.md` — implementation plan with M0–M10 milestone
  definitions and gap analysis
- `review.md` — active milestone status table (to be verified, not assumed accurate;
  relevant facts inlined in SC-004 and Assumptions)

---

## Defined Terms

The following terms are used precisely throughout this spec. Any field or output that
references these values MUST use exactly these definitions.

### Confidence Scale

`confidence ∈ {very_high, high, medium, low, very_low}` (ordered, highest first).

- `very_high` — multiple independent confirming sources (static + runtime observed)
- `high` — single strong source (exact host/URL match after env resolution, or artifact id)
- `medium` — normalized logical name match (service/app name after canonicalization)
- `low` — fuzzy or candidate-only match (ambiguous, llm-judged, or partial attribution)
- `very_low` — speculative; requires human review

Confidence is inherited as the **weakest link** in any resolution chain.

### Provenance Values

`provenance ∈ {declared, injected, observed, llm-judged}`

- `declared` — value found verbatim in committed source config (e.g., `appsettings.json`,
  `web.config`) with no variable substitution.
- `injected` — value resolved via the CI/CD variable store or acquisition ladder at
  deploy time; the source config contained a placeholder token, not the literal value.
- `observed` — value derived from runtime telemetry (M10 scope; not M0–M4).
- `llm-judged` — value produced by an LLM judgment call (M9 scope; not M0–M4).

In M0–M4 scope, only `declared` and `injected` are produced.

### Evidence Locator Formats

Every `evidence[]` entry MUST use one of these formats:

| Source type | Format | Example |
|---|---|---|
| Source file | `{filename}:{line}` | `home.aspx:42` |
| CI/CD variable store | `{provider}:{project}:{env}:{key}` | `octopus:Projects-1:prod:LandingPageUrl` |
| Deployment run | `{provider}:run-{id}` | `octopus:run-Deployments-3217` |
| Build run | `{provider}:build-{id}` | `teamcity:build-4891` |

An evidence entry that does not conform to one of these formats is a bug.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Clean-Checkout Test Pass (Priority: P1)

A new contributor clones the repository, installs dependencies from the declared package
manifest, runs the full test suite, and every test passes. No external credentials, no live
API calls, no manual setup beyond `pip install`.

**Why this priority**: This is the fundamental OSS contributor contract. If a clean
checkout doesn't pass tests, no other milestone claim can be trusted.

**Prerequisite**: Golden fixtures MUST be committed to `tests/fixtures/golden/` before
this story is evaluable. The contributor MUST confirm fixture presence with
`ls tests/fixtures/golden/` before running the test suite. If absent, fixture creation
is the first task (see Assumptions).

**Independent Test**: `pip install -e ".[dev]"` followed by `pytest tests/` completes
with zero failures, zero errors, and zero live network calls. "Zero live network calls"
means no HTTP, HTTPS, or DNS resolution to any host outside localhost during the entire
test run.

**Acceptance Scenarios**:

1. **Given** a clean checkout on a machine with no provider credentials configured,
   AND golden fixtures are present in `tests/fixtures/golden/`,
   **When** the contributor runs `pip install -e ".[dev]" && pytest tests/`,
   **Then** all tests pass, no test makes any HTTP/HTTPS/DNS call to an external host,
   and the pytest output reports the number of tests collected and passed (≥ 38).

2. **Given** the same clean checkout with fixtures present,
   **When** the contributor runs `python -m tendril --help`,
   **Then** the CLI responds with a usage description listing `providers`, `graph`, `query`,
   and `serve` as subcommands.

---

### User Story 2 — Plugin ABCs Exist as Real Contracts (Priority: P1)

A provider implementer can read the code and discover seven clearly-defined plugin
interfaces (VCS, CI/CD, Extractor, IntraRepo, Telemetry, GraphStore, LLM) with
documented method signatures and return types. Creating a new provider does not require
reading or modifying any core traversal or resolution code.

All seven ABCs MUST exist as versioned contracts even if IntraRepo, Telemetry, and LLM
carry only stub/minimal implementations in M0–M4. Stub bodies are acceptable; absent
interfaces are not.

**Why this priority**: The plugin-first principle is the non-negotiable design invariant.
If ABCs are stubs without real contracts, every provider added later risks core divergence.

**Independent Test**: A `FakePlugin` implementing one ABC can be registered and appear in
`tendril providers list` output without editing any file outside the plugin itself.

**Acceptance Scenarios**:

1. **Given** the seven plugin ABCs are in place,
   **When** a developer implements the `VCSProvider` interface with a minimal in-memory
   fake and registers it via the plugin discovery mechanism,
   **Then** the fake appears in `tendril providers list` and passes the corresponding
   conformance test class without any change to core.

2. **Given** a plugin manifest (`tendril-plugin.toml`) is present in a provider package,
   **When** the package is installed alongside the core,
   **Then** the plugin is auto-discovered, its declared capabilities are readable, and
   incompatible contract versions are rejected with a clear error message.

---

### User Story 3 — VCS and CI/CD Connectors Pass Conformance (Priority: P1)

A quality engineer can run the conformance test suite against the four reference connectors
(GitHub, Bitbucket DC, TeamCity, Octopus) and see all tests green using fixture data only.

**Why this priority**: review.md claims M1 is 90% complete. The specific gap is: the
conformance base classes exist at `tests/conformance/` but no concrete subclasses exist
for the real connectors. This story's acceptance criteria define what "M1 closed" means.

**M1 gap closure criterion** (see also SC-002 and CHK031): The gap is closed when
concrete conformance test subclasses exist in the file system **AND** those tests execute
without error **AND** the tests cover every abstract method declared in the respective ABC.
Criterion (a) or (b) alone is NOT sufficient.

**Independent Test**: `pytest tests/conformance/ -v` passes for all four connectors
without network calls, using pre-recorded fixtures.

**Acceptance Scenarios**:

1. **Given** the GitHub and Bitbucket DC connectors are implemented against fixtures,
   **When** the VCS conformance test classes are run for both connectors,
   **Then** all VCS conformance tests pass, covering: listing repos in a scope, reading a
   file at a specific ref, reading the repo tree, and returning connector capabilities.

2. **Given** the TeamCity and Octopus connectors are implemented against fixtures,
   **When** the CI/CD conformance test classes are run for both connectors,
   **Then** all CI/CD conformance tests pass, covering: listing pipelines, reading variable
   stores with scoping, reading provider identities, and (Octopus only) resolving the
   deployed ref for a project and environment.

3. **Given** the Octopus conformance test includes a deployed-ref test,
   **When** the test calls `resolve_deployed_ref` against the Octopus fixture,
   **Then** it returns a non-null result with a non-empty SHA field.

---

### User Story 4 — First Real DEPENDS_ON Edge End-to-End (Priority: P1)

A developer can run the graph build command against the golden fixture estate and get a
single verified `DEPENDS_ON@prod` edge with complete evidence: the iframe consumer
reference, the token resolution through the variable store, the deployed SHA, the
originating Octopus deployment, and an empty unknowns list.

**Why this priority**: This is the M4 acceptance criterion and the core mechanism proof.
The two M4 gaps from review.md are: (1) rung 4 is a stub with no log parsing, and (2)
the end-to-end test assertions are not tight. This story closes both.

**Fixture SHA**: The golden fixture Octopus deployment record for `webforms-solution` in
the `prod` environment specifies `sha=abc123def456`. This is the known constant that
`deployed_ref` MUST equal. It lives at
`tests/fixtures/golden/cicd/octopus/deployments_Projects-1_prod.json`.

**Independent Test**: Running `tendril graph build --anchor bitbucket-dc:acme/webforms-solution
--env prod --fixture-dir tests/fixtures/golden/` and querying the result produces the edge
with all required fields populated.

**Acceptance Scenarios**:

1. **Given** the golden fixture for a 3-repo estate (webforms-solution → landing-page-ui
   → landing-page-api) is in place,
   **When** the graph build runs for the anchor repo and `prod` environment,
   **Then** the resulting graph contains a `DEPENDS_ON@prod` edge with ALL of the following
   asserted (asserting only edge existence does NOT satisfy this criterion):
   - `from_id` = `"bitbucket-dc:acme/webforms-solution"` (exact string)
   - `to_id` = `"github:acme/landing-page-ui"` (exact string)
   - `env` = `"prod"` (exact string)
   - `provenance` = `"injected"` (from the Defined Terms provenance scale)
   - `confidence` = `"high"` (from the Defined Terms confidence scale)
   - `deployed_ref` = `"abc123def456"` (SHA from `deployments_Projects-1_prod.json`)
   - `evidence[]` containing at minimum 3 entries: one with `home.aspx` as filename,
     one with `appsettings.prod.json` as filename, and one referencing an Octopus
     variable store or deployment run (per the Evidence Locator Formats in Defined Terms)
   - `unknowns[]` = empty list

2. **Given** the same fixture run,
   **When** the test queries the `deployed_ref` field on the resulting edge,
   **Then** it equals `"abc123def456"` — the SHA from the Octopus deployment fixture, not
   the default branch HEAD. `deployed_ref` is the `sha` field of the `DeployedRef` entity
   associated with `webforms-solution` in the `prod` environment.

3. **Given** a reference token that is secret-typed in the variable store,
   **When** the acquisition ladder reaches the secret floor,
   **Then** the token is recorded as `unresolved-secret` with evidence pointing to the
   variable store entry (using the `{provider}:{project}:{env}:{key}` format), and the
   reference appears in the build's `unknowns[]` output — not fabricated, not omitted.

---

### User Story 5 — Attribution Identifies Build and Deploy Owners (Priority: P2)

Given a repo's file tree and CI/CD fixture data, the attribution engine produces a
structured per-repo profile that correctly identifies TeamCity as the build owner and
Octopus as the deploy owner, with separate variable stores for each role.

**Why this priority**: Attribution is M2 and is marked complete in review.md. This story
verifies that claim and ensures chaining (build-owner ≠ deploy-owner) is handled.

**Independent Test**: Calling the attribution function against the fixture
`webforms-solution` repo produces a `CICDProfile` with the expected build and deploy
assignments.

**Acceptance Scenarios**:

1. **Given** the webforms-solution fixture contains TeamCity VCS root data and Octopus
   project fixtures,
   **When** attribution runs on the fixture repo,
   **Then** the resulting profile identifies `teamcity` as the build owner with role
   `build` and `octopus` as the deploy owner with role `deploy`, each with evidence
   locating the detection signal.

2. **Given** a repo whose build pipeline contains a deploy-step action targeting Octopus,
   **When** attribution resolves the deploy owner,
   **Then** the profile flags the chained ownership (TC builds → Octopus deploys) and
   assigns deploy-time variable resolution to the Octopus store.

3. **Given** a repo where no CI/CD deploy-step signatures match any known deploy-action,
   **When** attribution runs on that repo,
   **Then** the `CICDProfile` sets `deploy_owner=null` and `deploy_confidence=low` and
   records an `unattributed-deploy` flag in evidence. The run continues at reduced
   confidence — it does not fail.

---

### User Story 6 — Extractors Locate and Classify Without Resolving (Priority: P2)

The composition extractor and .NET extractor, when run against the webforms-solution
fixture, produce consumer references and token declarations that correctly identify the
iframe and the config-token dependency — without resolving any variable values.

**Why this priority**: M3 is marked complete. This story verifies the extraction output
shape and confirms extractors are classify-only (no resolution).

**Independent Test**: Running the composition extractor against the webforms-solution
fixture tree produces a `ConsumerRef` for the iframe with the token name as a `token_ref`.

**Acceptance Scenarios**:

1. **Given** a `home.aspx` file containing an iframe with a placeholder token in the src
   attribute,
   **When** the composition extractor runs against the fixture,
   **Then** it returns a `ConsumerRef` with `kind=iframe`, `raw_value` containing the
   placeholder, `token_refs` listing the token name, and an `evidence` locator pointing
   to the file and line number in `{filename}:{line}` format.

2. **Given** an `appsettings.prod.json` file with a config key pointing to an external
   URL,
   **When** the .NET extractor runs against the fixture,
   **Then** it returns a `TokenDecl` for that key with the file path in its evidence, and
   does NOT attempt to contact any external service or resolve the URL.

---

### Edge Cases

- **Deployed ref missing or malformed**: "Malformed" means any of: (a) the `sha` field is
  absent from the deployment fixture, (b) the `sha` field is an empty string, or (c) the
  `sha` field is not a valid hex string of at least 7 characters. In all three cases the
  run MUST degrade to `deployed_ref=null` with a `stale` flag on the edge. The run MUST
  NOT fail.

- **Consumer reference maps to zero provider identities**: The `ConsumerRef` is recorded
  in the graph build's `unknowns[]` output set (at the build level, not on an edge, since
  no edge can exist without a target). The evidence for the unresolved reference is
  preserved. The traversal continues to other references. This behavior preserves recall —
  traversal is not blocked by any individual unresolved reference.

- **Two repos share the same provider identity value**: Both are indexed. The reverse-index
  lookup returns both candidates. Each produces a `DEPENDS_ON` edge with `ambiguous=true`,
  `confidence=low` (regardless of identity class), and a `candidates[]` field listing both
  matched deployables. BFS continues with both. No auto-pick occurs.

- **Variable is secret-typed and no rung recovers it**: The token is emitted as
  `unresolved-secret`; no value is fabricated or logged; the reference appears in the
  build's `unknowns[]`. The graph never stores the secret value.

- **Conformance test subclass omits a required abstract method**: Pytest "collection time"
  is the phase where pytest discovers and instantiates test classes, before any test
  function executes. A missing abstract method raises `TypeError` during this phase. The
  test command exits non-zero with the collection error visible in output. No tests are
  silently skipped.

- **Rung 5 (browser automation) would be the only remaining option**: The acquisition
  ladder returns `unresolved-no-source`. Rung 5 is not attempted in M0–M4 scope and is
  not present in the implementation.

- **BFS encounters a previously-expanded repo (cycle)**: The repo is not re-expanded.
  Any new edges from this traversal path to the already-expanded repo are still recorded
  in the graph. The existing repo node is not duplicated. The traversal frontier does not
  re-enqueue the expanded repo.

- **Graph build runs for a non-prod environment (e.g., staging)**: The build MUST produce
  environment-specific edges using the deployed SHA for `staging` from the staging
  deployment fixture. Provider identities and resolved variable values may differ from
  `prod`; each environment produces an independent edge set with its own `deployed_ref`.

- **Empty extraction (no consumer references found)**: The repo is marked as expanded with
  zero outbound `DEPENDS_ON` edges. No error is raised. The repo node exists in the graph.
  The build output records the repo as traversed with `consumer_refs=[]`.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** *(covered by US2)*: The system MUST expose seven plugin ABCs —
  `VCSProvider`, `CICDProvider`, `ExtractorPlugin`, `IntraRepoProvider`,
  `TelemetryProvider`, `GraphStore`, `LLMProvider` — as independently-versionable
  contracts discoverable without modifying core code. In M0–M4, `IntraRepoProvider`,
  `TelemetryProvider`, and `LLMProvider` MAY carry stub/minimal implementations but
  MUST exist as real, callable interfaces.

- **FR-002** *(covered by US2)*: Each plugin MUST declare its capabilities explicitly via
  a `capabilities()` method. The system MUST route work only to capabilities declared as
  present and MUST NOT fail or raise an exception when a capability is absent.

- **FR-003** *(covered by US3)*: The VCS connectors for GitHub and Bitbucket Data Center
  MUST pass all VCS conformance tests using pre-recorded fixture responses, including
  reading a file at an explicit ref parameter (not defaulting to HEAD).

- **FR-004** *(covered by US3)*: The CI/CD connectors for TeamCity and Octopus Deploy
  MUST pass all CI/CD conformance tests using pre-recorded fixture responses, including
  resolving the deployed ref for a given project and environment from deployment metadata.

- **FR-005** *(covered by US5)*: The attribution engine MUST produce a per-repo
  `CICDProfile` that correctly identifies build and deploy owners, distinguishes their
  roles, assigns each role to the correct variable store, and handles the chained case
  (build ≠ deploy owner) and the unattributed-deploy case (deploy owner not identifiable).

- **FR-006** *(covered by US6)*: The extractor plugins (composition, .NET) MUST locate
  and classify consumer references and provider identities without resolving token values.
  Every extracted item MUST carry an `evidence[]` entry in `{filename}:{line}` format.

- **FR-007** *(covered by US4)*: The reverse index MUST index all provider identities from
  all repos discoverable via the configured provider credentials at build time (the
  "configured scope"). It MUST support lookup by normalized value per environment and
  MUST return candidate matches with confidence and evidence.

- **FR-008** *(covered by US4)*: The acquisition ladder MUST thread the deployed ref
  through source-file reads (rung 1 calls `read_file(repo, ref=deployed_sha, path)`, not
  HEAD). It MUST attempt rungs 2–4 in order before emitting `unresolved-secret` or
  `unresolved-no-source`. Rung 5 (browser) is excluded from M0–M4 scope.

  **Rung 4 closed criterion**: Rung 4 (deploy-log harvesting) gap is closed when, given
  an Octopus task log line containing `LandingPageUrl=https://d-ui.prod.example.com`,
  the parser successfully extracts the key-value pair and returns an `AcquisitionResult`
  with `rung='deploy-log'` and the matched value. A method body that logs "not
  implemented" does NOT satisfy this requirement.

- **FR-009** *(covered by US4)*: The BFS traversal MUST produce `DEPENDS_ON` edges
  carrying `provenance` (from the Defined Terms scale), `confidence` (from the Defined
  Terms scale), `deployed_ref` (SHA string), `evidence[]` (locators per Defined Terms
  formats), and `unknowns[]` (list of unresolved refs at the build level). Confidence is
  inherited as the weakest link in the resolution chain.

- **FR-010** *(covered by US4)*: Secret-typed variable values MUST never be stored in the
  graph, logged to any output stream, emitted in evidence locators, or returned as resolved
  values. They MUST be recorded as `{is_secret: true, resolved: bool}` and the
  corresponding reference flagged `unresolved-secret` in `unknowns[]`.

- **FR-011** *(covered by US1)*: The full test suite MUST pass from a clean checkout with
  no external credentials. Golden fixtures MUST be sufficient for all M0–M4 tests. The
  test count MUST be at least 38 (the committed baseline). A PR that reduces the passing
  count from baseline is a regression.

- **FR-012** *(covered by US1, US2)*: The CLI MUST accept `tendril graph build --anchor
  <id> --env <name>` and produce a queryable graph. `tendril providers list` MUST output
  for each registered provider: its `id`, `family` (VCS/CI/CD/Extractor/etc.),
  `contract_version`, and declared capabilities as key:bool pairs. Output MUST support
  a human-readable default and `--json` for machine consumption.

- **FR-013** *(covered by US4, US5)*: In M0–M4, the system defaults to a 1:1
  Repo:Deployable mapping unless the CI/CD profile explicitly indicates multiple
  deployables (e.g., multiple Octopus projects mapping to one repo). Multi-deployable
  repos MUST be flagged for review rather than silently collapsed or silently expanded.

- **FR-014** *(covered by US4)*: The system MUST provide an environment name
  canonicalization facility that normalizes env names from different providers (e.g.,
  GitHub "production", Octopus "Prod", TeamCity "prod") via case-folding plus a
  configurable alias table. An unmatched env name falls back to its raw name and
  contributes `confidence=low` to any edge resolved through it — it MUST NOT cause a
  resolution failure.

- **FR-015** *(covered by US4)*: `DEPENDS_ON` edges returned by the graph build MUST be
  ordered deterministically (sorted by `from_id`, then `to_id`, then `env`) so that
  repeated builds against the same fixtures produce identical output sequences.

### Key Entities *(data involved)*

- **CICDProfile**: Per-repo record of build/deploy ownership. Key attributes:
  `build_owner` (provider id string), `deploy_owner` (provider id string or null),
  `deploy_confidence` (from confidence scale), `envs` (list of env name strings),
  `evidence[]` (locators for detection signals), `variable_stores` (list of store
  references per owner role).

- **DeployedRef**: A resolved SHA/branch for a specific deployable and environment. Key
  attributes: `sha` (hex string, ≥ 7 chars), `branch` (string), `env` (string),
  `deployable_id` (string), `deploy_timestamp` (ISO-8601 string), `source` (deployment
  run locator, e.g., `octopus:run-Deployments-3217`). The `deployed_ref` field on
  a `DEPENDS_ON` edge is the `sha` value of this entity.

- **ConsumerRef**: An outbound reference extracted from a repo. Key attributes:
  `kind` (one of: `iframe`, `url`, `connection-string`, `artifact`), `raw_value`
  (string as it appears in source, may contain token placeholders), `token_refs`
  (list of placeholder token name strings), `env_hint` (optional string), `evidence[]`.

- **ProviderIdentity**: A claimed identity for a deployable. Key attributes:
  `identity_class` (one of: `network`, `logical`, `deploy`, `artifact`), `value`
  (string), `env` (optional string), `evidence[]`.

- **DependsOn edge**: The materialized inter-repo dependency. Key attributes: `from_id`
  (string), `to_id` (string), `env` (string), `provenance` (from Defined Terms scale),
  `confidence` (from Defined Terms scale), `deployed_ref` (SHA string from DeployedRef),
  `evidence[]` (locators per Defined Terms formats), `unknowns[]` (list of unresolved
  ConsumerRef records that could not be matched), `ambiguous` (bool), `candidates[]`
  (list of competing Deployable ids, non-empty when `ambiguous=true`).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A contributor completes a clean-checkout install-and-test cycle in a single
  terminal session with zero interactive prompts and zero external network calls (defined
  as: no HTTP, HTTPS, or DNS resolution to any host outside localhost during the test run),
  ending with all tests passing and a count ≥ 38.

- **SC-002**: The four reference connectors (GitHub, Bitbucket DC, TeamCity, Octopus) each
  have concrete conformance test subclasses that pass against pre-recorded fixtures,
  covering every abstract method in the respective ABC. M1 is "closed" only when all three
  conditions hold: (a) subclasses exist in the file system, (b) tests execute without
  error, AND (c) every abstract method is exercised.

- **SC-003**: The end-to-end graph build against the golden 3-repo fixture produces a
  `DEPENDS_ON@prod` edge for which ALL of the following must be asserted (partial
  assertions do NOT satisfy this criterion):
  - `from_id = "bitbucket-dc:acme/webforms-solution"` (exact string)
  - `to_id = "github:acme/landing-page-ui"` (exact string)
  - `env = "prod"` (exact string)
  - `provenance = "injected"` (exact enum value from Defined Terms)
  - `confidence = "high"` (exact enum value from Defined Terms)
  - `deployed_ref = "abc123def456"` (SHA from `deployments_Projects-1_prod.json`)
  - `evidence[]` non-empty with ≥ 3 entries covering: iframe source file, config token
    declaration file, and Octopus variable store or deployment run
  - `unknowns[]` is empty list

- **SC-004**: The following gaps — identified from review.md and inlined here — are either
  closed (per the gap-specific criteria below) or explicitly documented as deferred with
  a scope boundary:

  **Gap 1 (M1)**: No concrete conformance test subclasses exist for GitHub, Bitbucket DC,
  TeamCity, or Octopus connectors. *Closed when*: `pytest tests/conformance/ -v` passes
  for all four connectors with no network calls (SC-002 criterion).

  **Gap 2 (M4-a)**: Rung 4 of the acquisition ladder is a stub that does not parse log
  output. *Closed when*: Given an Octopus log line `KEY=VALUE`, the parser returns an
  `AcquisitionResult` with `rung='deploy-log'` and the matched value (FR-008 criterion).

  **Gap 3 (M4-b)**: The end-to-end test assertions are not tight (edge existence only).
  *Closed when*: The test asserts all fields enumerated in SC-003.

- **SC-005**: `tendril providers list` outputs, for each registered provider: `id`,
  `family`, `contract_version`, and capabilities, without error from a clean install.

- **SC-006**: A secret-typed variable in the fixture store does not appear as a resolved
  value on any of the following surfaces: graph store node/edge properties, pytest
  stdout/stderr captured output, tendril CLI stdout/stderr, evidence locator strings in
  any edge, or any file written by the build process. Instead it appears as an
  `unresolved-secret` entry in the build's `unknowns[]`.

---

## Assumptions

- The review.md milestone status table is a reasonable starting point but its accuracy
  MUST be verified by running actual tests. Active verification commands per milestone:
  - M0: `pytest tests/test_m0_acceptance.py -v`
  - M1: `pytest tests/conformance/ -v --no-header`
  - M2: `pytest tests/ -k attribution -v`
  - M3: `pytest tests/ -k extractor -v`
  - M4: `pytest tests/test_end_to_end.py -v`
  All must pass with zero failures using `pytest tests/` from a clean install.

- The "38 tests pass" baseline from CLAUDE.md MUST be verified before any changes by
  running `pytest tests/ --collect-only` on the current branch. If the actual count
  differs from 38, that count becomes the new baseline for regression purposes. The spec
  requires that no existing passing test be made to fail by any change in this spec's scope.

- Golden fixtures (`tests/fixtures/golden/`) may need to be created or extended as part
  of M4/M6 work. Before US4 acceptance testing begins, the implementing contributor MUST
  confirm fixture presence by running `ls tests/fixtures/golden/`. If absent, fixture
  creation is the first task. The fixture structure follows the JSON format implied by
  connector implementations (e.g., Octopus fixtures mimic the Octopus REST API response
  format); the plan phase MUST document the expected fixture schemas before implementation.

- The conformance base classes exist at `tests/conformance/` per CLAUDE.md. Before
  building conformance subclasses, the plan phase MUST verify that
  `tests/conformance/test_vcs_provider.py` and `tests/conformance/test_cicd_provider.py`
  exist and identify the abstract methods required by each base class.

- Rung 4 being a "stub" (per review.md) means the method body exists but does not parse
  log output. A stub does not satisfy FR-008. The spec requires at minimum the Octopus
  task log KEY=VALUE pattern to be parsed.

- No wall-clock performance requirement is set for the test suite in M0–M4. A reasonable
  target for `pytest tests/` is under 60 seconds on standard developer hardware against
  fixtures; this will be established empirically during M6.

- `tendril-plugin.toml` manifest format, plugin entry-point convention, and capability
  negotiation are defined by the implementation already committed in M0; this spec does not
  redefine them.

---

## Milestone Completion Criteria

A milestone is **complete** when its verification command (listed in Assumptions) exits
with code 0, zero test failures, zero test errors, using fixture data only — with no
modifications to fixture files or test configuration between the clean install and the
test run.

"Partially complete" (e.g., "90%") is not a valid completion state for the purposes of
this spec. A milestone is either complete or not complete. Gap items outstanding at the
end of an iteration MUST be documented as deferred with a clear scope boundary before
being carried into the next milestone's scope.
