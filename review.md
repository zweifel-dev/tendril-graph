★ Insight ─────────────────────────────────────
  The scaffold is structurally sound — ABCs, IR types, and the BFS skeleton are all correct. But there are 3 correctness
  bugs that will prevent the M4 acceptance test from passing, plus the pyproject.toml is missing entirely (nothing can be
  installed). The bugs are concentrated in the glue code, not the design.
  ─────────────────────────────────────────────────

  Here is the full review:

  ---
  Milestone flow assessment

  The Mermaid flow in critique-plan.md is correct and matches what was actually generated. M4 is correctly marked as the
  gate. M5 (query/MCP) and M6 (OSS hygiene) being parallel after M4 is right. One concern: M2 (attribution) and M3
  (extractors) are shown as sequential, but they're actually independent — attribution touches CI/CD files; extractors
  touch source/config files. They could be developed in parallel.

  ---
  What's solid

  M0 — ABCs and IR types are clean. plugins/base.py matches every interface in SPEC §4 faithfully. All seven ABCs are
  present. models/ir.py is comprehensive — includes AcquisitionResult (good addition not in the spec pseudocode but
  required for the ladder), Provenance/Confidence/IdentityClass enums, CICDProfile/CICDProviderEntry (correctly implements
  the critique's C3 fix for Deployable discovery). models/graph.py implements every §2 node/edge type including
  DeployedRefNode (H2 fix), DependsOn.ambiguous + candidates (H4/H5 fix), DependsOn.resolved_via (H3 fix for invalidation
  tracking). The graph model is more complete than I expected.

  M3 — Extractors are solid. CompositionExtractor handles all five token syntaxes, all markup extensions,
  locate-and-classify only (never resolves). DotNetExtractor handles appsettings.{env}.json with correct env_hint
  extraction, web.config appSettings + connectionStrings + WCF endpoints, .csproj NuGet refs as ARTIFACT provider
  identities. Both are production-quality.

  M4 — Reverse index and resolver design are correct. ReverseIndex does exact + normalized URL lookup with proper env
  filtering and _class_confidence mapping. The secret floor in Resolver.acquire is correctly implemented — is_secret=True
  returns UNRESOLVED_SECRET and stops. The BFS cycle detection via expanded set is correct. The E2E test covers the right
  acceptance criteria.

  ---
  Bugs — must fix before M4 acceptance test can pass

  BUG 1 (CRITICAL): pyproject.toml is missing — nothing installs

  There is no pyproject.toml. All imports use from models.ir import ... but there's no tendril/ package directory
  and no installation config mapping the root to the tendril namespace. pip install -e . would fail. pytest would fail with
   ModuleNotFoundError: No module named 'tendril'.

  Fix needed: Create pyproject.toml with at minimum:
  [build-system]
  requires = ["setuptools>=68"]
  build-backend = "setuptools.backends.legacy:build"

  [project]
  name = "tendril-graph"
  version = "0.1.0-alpha"
  requires-python = ">=3.12"
  dependencies = ["kuzu", "pyyaml", "typer", "fastapi"]

  [project.optional-dependencies]
  dev = ["pytest", "pytest-cov"]

  [tool.setuptools.packages.find]
  where = ["."]
  include = ["tendril*", "plugins*", "models*", "core*", "connectors*", "extractors*", "store*", "cli*", "mcp*", "query*"]
  Or better, move all source into a src/tendril/ layout. The current flat layout (root = package) can work with the right
  pyproject.toml but is fragile.

  BUG 2 (CRITICAL): FR-24 violated — extractors are called with "HEAD" instead of the deployed ref

  traversal.py:207:
  result = ext.extract(repo, "HEAD", tree, self._read_file)

  The deployed ref is correctly resolved (line 94–97) and correctly stored in result.deployed_refs. But when
  _run_extractors is called, it passes "HEAD" to every extractor. This means all file reads inside CompositionExtractor and
   DotNetExtractor use HEAD, not the deployed SHA. This violates FR-24 and means the graph is wrong whenever prod runs an
  older ref than main.

  Fix needed: Pass ref_str into _run_extractors:
  def _run_extractors(self, repo, tree, ref="HEAD"):
      ...
      result = ext.extract(repo, ref, tree, self._read_file)
  And call it with self._run_extractors(repo, tree, ref=ref_str) inside the env loop.

  BUG 3 (HIGH): attribution._detect_deploy_steps ignores file content — always returns all signatures

  attribution.py:138–151:
  def _detect_deploy_steps(self, repo_tree, build_provider_id):
      evidence = []
      for sig in self._signatures:
          if sig.get("match_type") == "action_id":
              evidence.append(...)
      return evidence

  This returns evidence for every signature in the YAML regardless of whether it appears in the repo's workflow files.
  Every repo gets roles=["build", "deploy"] for every signature pattern, regardless of content. The actual workflow YAML
  files need to be read and scanned for the signature patterns.

  Fix needed: Read the relevant workflow files (.github/workflows/*.yml, .teamcity/ files, etc.) and scan them for the
  pattern. At minimum, return empty evidence if no workflow files were fetched — but ideally integrate with read_file to
  parse them. Since AttributionEngine doesn't currently have access to read_file, either pass it in or accept workflow
  content as a parameter.

  BUG 4 (MEDIUM): kuzu_store.upsert_node mutates the caller's dict

  kuzu_store.py:62: table = node.pop("_table", None) destructively removes _table from the passed dict. If the caller
  reuses the dict (e.g., loops), _table is gone on the second call.

  Fix: node = dict(node); table = node.pop("_table", None)

  BUG 5 (MEDIUM): kuzu_store.upsert_edge always CREATEs — duplicates on re-runs

  upsert_edge always issues CREATE (a)-[r:REL_TYPE]->(b). Running the BFS twice, or re-indexing a repo, doubles all edges.
  Kùzu supports MERGE on relationships with a workaround (it doesn't support MERGE on rel tables directly) — but at minimum
   the traversal should guard against re-persisting edges that already exist.

  Fix (short-term): Check if the edge exists before creating. Or track persisted edges in a set in the traversal result and
   skip duplicates.

  BUG 6 (MEDIUM): kuzu_store.path() query has invalid syntax

  env_filter = " AND rels(p, r, r.env = $env)" if env else ""
  rels(p, r, ...) is not valid Kùzu Cypher. Kùzu's path filtering syntax differs from Neo4j.

  Fix: Remove the env filter from path() for now (query all edges, filter in Python), or use Kùzu's correct syntax once
  verified.

  ---
  Issues that won't block M4 but need fixing before M6 (OSS milestone)

  - _resolve_chaining is a near-no-op: build_only = [p for p in providers if p.roles == ["build"]] then tries
  b.roles.remove("deploy") — but build-only providers don't have "deploy". The chaining logic needs to correctly identify
  the TC-builds + Octopus-deploys case and set roles accordingly.
  - _extract_static_values in traversal is backwards: It reads static values from consumer refs with matching env_hint, but
   consumer refs are the things being referenced (URLs), not the key→value config. Rung 1 should read the
  appsettings.prod.json file at the deployed ref and return its key→value map. The current implementation accidentally
  works for the test because the test's variable store rung 2 finds the value first.
  - _repo_from_full_name produces incomplete RepoRef: Reconstructed RepoRefs are missing url, default_branch — if
  discovered dependent repos get enqueued and then read_tree is called on them, they won't have the metadata the connectors
   need.

  ---
  Summary table

  ┌───────────────────────────────────────────┬────────────────────┬─────────────────────────┐
  │                   Item                    │       Status       │         Blocks          │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ 7 plugin ABCs                             │ Correct            │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ IR types (models/ir.py)                   │ Correct + complete │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ Graph model (models/graph.py)             │ Correct + complete │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ CompositionExtractor                      │ Solid              │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ DotNetExtractor                           │ Solid              │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ ReverseIndex                              │ Correct            │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ Resolver.acquire (secret floor)           │ Correct            │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ BFS structure (cycle detection, env loop) │ Correct            │ —                       │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ pyproject.toml missing                    │ Missing            │ Everything              │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ Extractors called with "HEAD"             │ Bug                │ FR-24 / M4 test         │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ _detect_deploy_steps ignores content      │ Bug                │ Attribution correctness │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ upsert_node dict mutation                 │ Bug                │ M4 (subtle)             │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ upsert_edge no dedup                      │ Bug                │ M6                      │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ path() invalid Kùzu syntax                │ Bug                │ M5 query layer          │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ _resolve_chaining near-no-op              │ Logic error        │ M2 chaining             │
  ├───────────────────────────────────────────┼────────────────────┼─────────────────────────┤
  │ _extract_static_values backwards          │ Logic error        │ Rung 1 correctness      │
  └───────────────────────────────────────────┴────────────────────┴─────────────────────────┘