# Contract: Provider Configuration

**Module**: `tendril/config.py` (extended)

## Interface Pattern

All provider config classes follow the established `LLMConfig` / `DatadogConfig` pattern:

```python
@dataclass
class ProviderConfig:
    """Base pattern (not a literal base class — each is independent)."""

    # Required fields specific to each provider
    # ...

    def is_complete(self) -> bool:
        """True if all required fields are non-empty strings."""

    def missing_fields(self) -> list[str]:
        """List of field names that are unset or empty."""

def load_<provider>_config() -> <Provider>Config:
    """
    Factory function. Resolution order:
    1. Environment variables (highest priority)
    2. tendril.toml section
    3. Built-in defaults (lowest priority, usually empty)

    Empty/whitespace-only env var values are treated as unset.
    """
```

## Provider-Specific Configs

### GitHubConfig

```python
@dataclass
class GitHubConfig:
    token: str = ""              # GH_TOKEN (PAT path)
    app_id: str = ""             # GH_APP_ID (App path)
    install_id: str = ""         # GH_INSTALL_ID (App path)
    private_key_path: str = ""   # GH_PRIVATE_KEY_PATH (App path)

    def is_complete(self) -> bool:
        # Complete if token is set OR all three app fields are set
        return bool(self.token.strip()) or all(
            f.strip() for f in [self.app_id, self.install_id, self.private_key_path]
        )
```

TOML section: `[vcs.github]`

### BitbucketDCConfig

```python
@dataclass
class BitbucketDCConfig:
    base_url: str = ""   # BB_BASE_URL
    token: str = ""      # BB_TOKEN

    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.token.strip())
```

TOML section: `[vcs.bitbucket_dc]`

### TeamCityConfig

```python
@dataclass
class TeamCityConfig:
    base_url: str = ""   # TC_BASE_URL
    token: str = ""      # TC_TOKEN

    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.token.strip())
```

TOML section: `[cicd.teamcity]`

### OctopusConfig

```python
@dataclass
class OctopusConfig:
    base_url: str = ""   # OCTO_URL
    api_key: str = ""    # OCTO_API_KEY
    space: str = ""      # OCTO_SPACE

    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.api_key.strip() and self.space.strip())
```

TOML section: `[cicd.octopus]`

## Validation

On provider initialization, a lightweight validation call SHOULD be attempted:

| Provider | Validation Call | Success Criterion |
|---|---|---|
| GitHub | `GET /user` or `GET /app` | HTTP 200 |
| Bitbucket DC | `GET /rest/api/1.0/projects?limit=1` | HTTP 200 |
| TeamCity | `GET /app/rest/server` | HTTP 200 |
| Octopus | `GET /api/{space}/machines?take=0` | HTTP 200 |

Validation failure does NOT raise — it logs a WARNING and the provider is excluded from the build.
