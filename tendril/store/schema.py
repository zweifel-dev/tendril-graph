"""Kùzu schema DDL — node and edge table definitions.

Separated from the adapter so the schema can be inspected, tested,
and evolved independently of the persistence layer.
"""

SCHEMA_DDL = [
    # Node tables
    "CREATE NODE TABLE IF NOT EXISTS Repo("
    "id STRING, provider STRING, org STRING, name STRING, "
    "url STRING, default_branch STRING, last_indexed_ref STRING, last_seen STRING, "
    "PRIMARY KEY(id))",

    "CREATE NODE TABLE IF NOT EXISTS Deployable("
    "id STRING, repo_id STRING, kind STRING, name STRING, "
    "PRIMARY KEY(id))",

    "CREATE NODE TABLE IF NOT EXISTS Environment("
    "id STRING, name STRING, canonical_name STRING, provenance STRING, "
    "PRIMARY KEY(id))",

    "CREATE NODE TABLE IF NOT EXISTS Endpoint("
    "id STRING, scheme STRING, host STRING, port INT64, path_base STRING, env STRING, "
    "PRIMARY KEY(id))",

    "CREATE NODE TABLE IF NOT EXISTS ServiceIdentity("
    "id STRING, canonical_value STRING, identity_class STRING, env STRING, "
    "PRIMARY KEY(id))",

    "CREATE NODE TABLE IF NOT EXISTS ConfigVar("
    "id STRING, name STRING, declared_in STRING, injected BOOLEAN, "
    "PRIMARY KEY(id))",

    "CREATE NODE TABLE IF NOT EXISTS DeployedRef("
    "id STRING, sha STRING, branch STRING, env STRING, deployable_id STRING, "
    "deploy_timestamp STRING, source STRING, "
    "PRIMARY KEY(id))",

    "CREATE NODE TABLE IF NOT EXISTS Pipeline("
    "id STRING, provider STRING, pipeline_id STRING, name STRING, "
    "PRIMARY KEY(id))",

    # Edge tables
    "CREATE REL TABLE IF NOT EXISTS PRODUCES("
    "FROM Repo TO Deployable, "
    "env STRING, provenance STRING, confidence STRING, evidence STRING, discovered_at STRING)",

    "CREATE REL TABLE IF NOT EXISTS DEPENDS_ON("
    "FROM Deployable TO Deployable, "
    "env STRING, provenance STRING, confidence STRING, evidence STRING, "
    "discovered_at STRING, deployed_ref STRING, ambiguous BOOLEAN, stale BOOLEAN)",

    "CREATE REL TABLE IF NOT EXISTS EXPOSES("
    "FROM Deployable TO Endpoint, "
    "env STRING, provenance STRING, confidence STRING, evidence STRING, discovered_at STRING)",

    "CREATE REL TABLE IF NOT EXISTS CONSUMES("
    "FROM Deployable TO Endpoint, "
    "env STRING, provenance STRING, confidence STRING, evidence STRING, discovered_at STRING)",

    "CREATE REL TABLE IF NOT EXISTS RESOLVES_TO("
    "FROM Endpoint TO Deployable, "
    "env STRING, provenance STRING, confidence STRING, evidence STRING, discovered_at STRING)",

    "CREATE REL TABLE IF NOT EXISTS DEPLOYED_AS("
    "FROM Deployable TO DeployedRef, "
    "env STRING, provenance STRING, confidence STRING, evidence STRING, discovered_at STRING)",
]
