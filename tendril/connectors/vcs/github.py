"""GitHub VCS provider (REST API, read-only)."""

from __future__ import annotations

import base64
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from tendril.config import HTTPConfig
from tendril.connectors._http import resilient_get
from tendril.models.ir import Capabilities, FileEntry, RepoRef
from tendril.plugins.base import VCSProvider

_BASE_URL = "https://api.github.com"


class GitHubProvider(VCSProvider):

    def __init__(
        self,
        token: str,
        fixture_dir: Path | None = None,
        http_config: HTTPConfig | None = None,
    ) -> None:
        self._token = token
        self._fixture_dir = fixture_dir
        self._http_config = http_config or HTTPConfig()

    def id(self) -> str:
        return "github"

    def capabilities(self) -> Capabilities:
        return {
            "list_repos": True,
            "read_tree": True,
            "read_file": True,
            "default_branch": True,
            "webhooks": False,
        }

    # -- VCSProvider interface ------------------------------------------------

    def list_repos(self, scope: dict[str, Any]) -> list[RepoRef]:
        if self._fixture_dir is not None:
            return self._fixture_list_repos(scope)

        org = scope.get("org", "")
        repos: list[RepoRef] = []
        page = 1
        while True:
            data = self._get(f"/orgs/{org}/repos?per_page=100&page={page}")
            if not data:
                break
            for raw in data:
                repos.append(RepoRef(
                    provider=self.id(),
                    org=raw.get("owner", {}).get("login", org),
                    name=raw["name"],
                    default_branch=raw.get("default_branch", "main"),
                    url=raw.get("clone_url", ""),
                ))
            if len(data) < 100:
                break
            page += 1
        return repos

    def read_tree(self, repo: RepoRef, ref: str) -> list[FileEntry]:
        if self._fixture_dir is not None:
            return self._fixture_read_tree(repo, ref)

        data = self._get(
            f"/repos/{repo.org}/{repo.name}/git/trees/{ref}?recursive=1",
        )
        files: list[FileEntry] = []
        for item in data.get("tree", []):
            files.append(FileEntry(
                path=item["path"],
                type="tree" if item["type"] == "tree" else "file",
                size=item.get("size", 0),
            ))
        return files

    def read_file(self, repo: RepoRef, ref: str, path: str) -> bytes:
        if self._fixture_dir is not None:
            return self._fixture_read_file(repo, ref, path)

        data = self._get(
            f"/repos/{repo.org}/{repo.name}/contents/{path}?ref={ref}",
        )
        encoding = data.get("encoding", "")
        content = data.get("content", "")
        if encoding == "base64":
            return base64.b64decode(content)
        return content.encode("utf-8")

    def default_branch(self, repo: RepoRef) -> str:
        if self._fixture_dir is not None:
            return self._fixture_default_branch(repo)

        data = self._get(f"/repos/{repo.org}/{repo.name}")
        return data.get("default_branch", "main")

    # -- HTTP helpers ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "tendril-graph/0.1",
        }

    def _get(self, path: str) -> Any:
        url = f"{_BASE_URL}{path}"
        result = resilient_get(url, headers=self._headers(), config=self._http_config)
        if not result.ok:
            raise urllib.error.URLError(result.error or f"HTTP {result.status}")
        return json.loads(result.body)

    # -- Fixture helpers ------------------------------------------------------

    def _fixture_path(self, *parts: str) -> Path:
        assert self._fixture_dir is not None
        return self._fixture_dir / self.id() / "/".join(parts)

    def _load_fixture(self, *parts: str) -> Any:
        p = self._fixture_path(*parts).with_suffix(".json")
        return json.loads(p.read_text(encoding="utf-8"))

    def _fixture_list_repos(self, scope: dict[str, Any]) -> list[RepoRef]:
        data = self._load_fixture("list_repos")
        repos: list[RepoRef] = []
        for raw in data:
            repos.append(RepoRef(
                provider=self.id(),
                org=raw["org"],
                name=raw["name"],
                default_branch=raw.get("default_branch", "main"),
                url=raw.get("url", ""),
            ))
        return repos

    def _fixture_read_tree(self, repo: RepoRef, ref: str) -> list[FileEntry]:
        data = self._load_fixture(repo.org, repo.name, "tree")
        return [FileEntry(path=p) for p in data]

    def _fixture_read_file(self, repo: RepoRef, ref: str, path: str) -> bytes:
        file_path = (
            self._fixture_dir / self.id() / repo.org / repo.name / "files" / path  # type: ignore[operator]
        )
        return file_path.read_bytes()

    def _fixture_default_branch(self, repo: RepoRef) -> str:
        data = self._load_fixture(repo.org, repo.name, "default_branch")
        return data.get("default_branch", "main")
