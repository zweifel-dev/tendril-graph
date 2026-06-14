"""Bitbucket Data Center VCS provider (REST API v1.0, read-only)."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from tendril.models.ir import Capabilities, FileEntry, RepoRef
from tendril.plugins.base import VCSProvider


class BitbucketDCProvider(VCSProvider):

    def __init__(
        self,
        base_url: str,
        token: str,
        fixture_dir: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._fixture_dir = fixture_dir

    def id(self) -> str:
        return "bitbucket-dc"

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

        repos: list[RepoRef] = []
        start = 0
        while True:
            data = self._get(f"/rest/api/1.0/repos?start={start}&limit=100")
            for raw in data.get("values", []):
                project_key = raw.get("project", {}).get("key", "")
                slug = raw.get("slug", "")
                clone_url = ""
                for link in raw.get("links", {}).get("clone", []):
                    if link.get("name") == "http":
                        clone_url = link["href"]
                        break
                repos.append(RepoRef(
                    provider=self.id(),
                    org=project_key,
                    name=slug,
                    url=clone_url,
                ))
            if data.get("isLastPage", True):
                break
            start = data.get("nextPageStart", start + 100)
        return repos

    def read_tree(self, repo: RepoRef, ref: str) -> list[FileEntry]:
        if self._fixture_dir is not None:
            return self._fixture_read_tree(repo, ref)

        files: list[FileEntry] = []
        start = 0
        while True:
            data = self._get(
                f"/rest/api/1.0/projects/{repo.org}/repos/{repo.name}"
                f"/files/{ref}?start={start}&limit=1000",
            )
            for path in data.get("values", []):
                files.append(FileEntry(path=path))
            if data.get("isLastPage", True):
                break
            start = data.get("nextPageStart", start + 1000)
        return files

    def read_file(self, repo: RepoRef, ref: str, path: str) -> bytes:
        if self._fixture_dir is not None:
            return self._fixture_read_file(repo, ref, path)

        url = (
            f"{self._base_url}/rest/api/1.0/projects/{repo.org}"
            f"/repos/{repo.name}/raw/{path}?at={ref}"
        )
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req) as resp:
            return resp.read()

    def default_branch(self, repo: RepoRef) -> str:
        if self._fixture_dir is not None:
            return self._fixture_default_branch(repo)

        data = self._get(
            f"/rest/api/1.0/projects/{repo.org}/repos/{repo.name}/default-branch",
        )
        display_id = data.get("displayId", "")
        return display_id or data.get("id", "refs/heads/main").split("/")[-1]

    # -- HTTP helpers ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

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
        return data.get("displayId", "main")
