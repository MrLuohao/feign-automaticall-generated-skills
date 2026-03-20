from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

from .indexer import (
    dump_global_index,
    dump_inverted_bucket,
    dump_manifest,
    dump_operation_docs,
    load_global_index,
    load_inverted_bucket,
    load_manifest,
    load_operation_docs,
)
from .models import (
    ControllerSpecModel,
    GlobalIndexModel,
    OperationSearchDoc,
    ServiceModel,
    ServiceShardManifest,
)
from .service_io import load_service_text, render_service
from .spec_io import load_spec_text, render_spec


DEFAULT_CONTRACTS_REMOTE_URL = "git@gitlab.dstcar.com:dmp/ai-coding/dst-api-skills-repo.git"
DEFAULT_CONTRACTS_GITLAB_BASE_URL = "https://gitlab.dstcar.com/api/v4"
DEFAULT_CONTRACTS_GITLAB_PROJECT = "dmp/ai-coding/dst-api-skills-repo"


class ContractStoreError(RuntimeError):
    pass


class ContractStore(ABC):
    @abstractmethod
    def read_text(self, relative_path: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, relative_path: str) -> bytes | None:
        raise NotImplementedError

    @abstractmethod
    def write_batch(
        self,
        upserts: dict[str, str | bytes],
        deletes: list[str],
        commit_message: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_files(self, prefix: str) -> list[str]:
        raise NotImplementedError

    def get_service_root(self, service: str) -> str:
        return f"services/{service}"

    def get_service_file(self, service: str) -> str:
        return f"{self.get_service_root(service)}/SERVICE.yaml"

    def get_controller_root(self, service: str, controller: str) -> str:
        return f"{self.get_service_root(service)}/controllers/{controller}"

    def get_controller_spec_file(self, service: str, controller: str) -> str:
        return f"{self.get_controller_root(service, controller)}/{controller}.spec.yaml"

    def get_controller_doc_file(self, service: str, controller: str) -> str:
        return f"{self.get_controller_root(service, controller)}/{controller}.doc.md"

    def get_global_index_file(self) -> str:
        return "indexes/global.index.json"

    def get_service_shard_root(self, service: str) -> str:
        return f"indexes/services/{service}"

    def get_service_manifest_file(self, service: str) -> str:
        return f"{self.get_service_shard_root(service)}/manifest.json"

    def get_service_operations_file(self, service: str) -> str:
        return f"{self.get_service_shard_root(service)}/operations.jsonl"

    def get_service_inverted_dir(self, service: str) -> str:
        return f"{self.get_service_shard_root(service)}/inverted"

    def get_service_inverted_bucket_file(self, service: str, bucket: str) -> str:
        return f"{self.get_service_inverted_dir(service)}/{bucket}"

    def load_service(self, service: str) -> ServiceModel | None:
        text = self.read_text(self.get_service_file(service))
        return load_service_text(text) if text is not None else None

    def write_service(self, model: ServiceModel, commit_message: str | None = None) -> None:
        self.write_batch({self.get_service_file(model.service): render_service(model)}, [], commit_message)

    def load_spec(self, service: str, controller: str) -> ControllerSpecModel | None:
        text = self.read_text(self.get_controller_spec_file(service, controller))
        return load_spec_text(text) if text is not None else None

    def write_spec(self, service: str, controller: str, spec: ControllerSpecModel, commit_message: str | None = None) -> None:
        self.write_batch({self.get_controller_spec_file(service, controller): render_spec(spec)}, [], commit_message)

    def read_doc(self, service: str, controller: str) -> str | None:
        return self.read_text(self.get_controller_doc_file(service, controller))

    def write_doc(self, service: str, controller: str, doc_text: str, commit_message: str | None = None) -> None:
        self.write_batch({self.get_controller_doc_file(service, controller): doc_text}, [], commit_message)

    def load_global_index(self) -> GlobalIndexModel | None:
        text = self.read_text(self.get_global_index_file())
        return load_global_index(text) if text is not None else None

    def write_global_index(self, index: GlobalIndexModel, commit_message: str | None = None) -> None:
        self.write_batch({self.get_global_index_file(): dump_global_index(index)}, [], commit_message)

    def load_service_manifest(self, service: str) -> ServiceShardManifest | None:
        text = self.read_text(self.get_service_manifest_file(service))
        return load_manifest(text) if text is not None else None

    def write_service_manifest(
        self, service: str, manifest: ServiceShardManifest, commit_message: str | None = None
    ) -> None:
        self.write_batch({self.get_service_manifest_file(service): dump_manifest(manifest)}, [], commit_message)

    def load_operation_docs(self, service: str) -> list[OperationSearchDoc]:
        text = self.read_text(self.get_service_operations_file(service))
        return [] if text is None else load_operation_docs(text)

    def write_operation_docs(
        self, service: str, docs: list[OperationSearchDoc], commit_message: str | None = None
    ) -> None:
        self.write_batch({self.get_service_operations_file(service): dump_operation_docs(docs)}, [], commit_message)

    def load_inverted_bucket(self, service: str, bucket: str) -> dict[str, list[str]] | None:
        text = self.read_text(self.get_service_inverted_bucket_file(service, bucket))
        return None if text is None else load_inverted_bucket(text)

    def write_inverted_bucket(
        self, service: str, bucket: str, data: dict[str, list[str]], commit_message: str | None = None
    ) -> None:
        self.write_batch({self.get_service_inverted_bucket_file(service, bucket): dump_inverted_bucket(data)}, [], commit_message)

    def list_services(self) -> list[str]:
        services: set[str] = set()
        for file_path in self.list_files("services/"):
            parts = file_path.split("/")
            if len(parts) >= 2:
                services.add(parts[1])
        return sorted(services)

    def list_service_controllers(self, service: str) -> list[str]:
        controllers: set[str] = set()
        prefix = f"{self.get_service_root(service)}/controllers/"
        for file_path in self.list_files(prefix):
            parts = file_path.split("/")
            if len(parts) >= 4:
                controllers.add(parts[3])
        return sorted(controllers)

    def iter_all_services(self) -> list[ServiceModel]:
        results: list[ServiceModel] = []
        for service in self.list_services():
            model = self.load_service(service)
            if model is not None:
                results.append(model)
        return results

    def iter_all_specs(self) -> list[tuple[str, str, ControllerSpecModel]]:
        results: list[tuple[str, str, ControllerSpecModel]] = []
        for service in self.list_services():
            for controller in self.list_service_controllers(service):
                spec = self.load_spec(service, controller)
                if spec is not None:
                    results.append((service, controller, spec))
        return results


class GitContractStore(ContractStore):
    def __init__(self, remote_url: str, branch: str):
        self.remote_url = remote_url
        self.branch = branch
        self._tempdir = tempfile.TemporaryDirectory(prefix="api-contract-store-")
        self.repo_root = Path(self._tempdir.name)
        self._worktree_ready = False
        self._active_branch_exists: bool | None = None
        self._init_repo()

    def read_text(self, relative_path: str) -> str | None:
        if not self._ensure_worktree_loaded():
            return None
        path = self.repo_root / relative_path
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def read_bytes(self, relative_path: str) -> bytes | None:
        if not self._ensure_worktree_loaded():
            return None
        path = self.repo_root / relative_path
        if not path.exists():
            return None
        return path.read_bytes()

    def write_batch(
        self,
        upserts: dict[str, str | bytes],
        deletes: list[str],
        commit_message: str | None = None,
    ) -> None:
        branch_exists = self._ensure_worktree_loaded()
        if not branch_exists:
            self._checkout_orphan_branch()
            self._worktree_ready = True
            self._active_branch_exists = False
        for relative_path, content in upserts.items():
            path = self.repo_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        for relative_path in deletes:
            path = self.repo_root / relative_path
            if path.exists():
                path.unlink()
                _cleanup_empty_dirs(path.parent, self.repo_root)
        self._run_git("add", "-A")
        if not self._has_staged_changes():
            return
        self._ensure_commit_identity()
        self._run_git("commit", "-m", commit_message or "Update API contracts")
        self._run_git("push", "origin", f"HEAD:refs/heads/{self.branch}")
        self._worktree_ready = True
        self._active_branch_exists = True

    def list_files(self, prefix: str) -> list[str]:
        if not self._ensure_worktree_loaded():
            return []
        root = self.repo_root / prefix
        if root.is_file():
            return [prefix.rstrip("/")]
        if not root.exists():
            return []
        return sorted(path.relative_to(self.repo_root).as_posix() for path in root.rglob("*") if path.is_file())

    def _init_repo(self) -> None:
        self._run_git("init")
        self._run_git("remote", "add", "origin", self.remote_url)

    def _checkout_remote_branch(self) -> bool:
        self._run_git("fetch", "--depth", "1", "origin", self.branch)
        self._run_git("checkout", "-B", self.branch, "FETCH_HEAD")
        self._worktree_ready = True
        self._active_branch_exists = True
        return True

    def _checkout_orphan_branch(self) -> None:
        self._run_git("checkout", "--orphan", self.branch)
        for child in self.repo_root.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        self._worktree_ready = True
        self._active_branch_exists = False

    def _ensure_worktree_loaded(self) -> bool:
        if self._worktree_ready:
            return bool(self._active_branch_exists)
        branch_exists = self._remote_branch_exists()
        if branch_exists:
            self._checkout_remote_branch()
        else:
            self._worktree_ready = True
            self._active_branch_exists = False
        return branch_exists

    def _remote_branch_exists(self) -> bool:
        result = self._run_git("ls-remote", "--exit-code", "--heads", "origin", self.branch, check=False)
        if result.returncode == 0:
            return True
        if result.returncode == 2:
            return False
        raise ContractStoreError(result.stderr.strip() or result.stdout.strip() or "Failed to inspect remote branch")

    def _has_staged_changes(self) -> bool:
        result = self._run_git("diff", "--cached", "--quiet", check=False)
        if result.returncode == 0:
            return False
        if result.returncode == 1:
            return True
        raise ContractStoreError(result.stderr.strip() or result.stdout.strip() or "Failed to inspect staged changes")

    def _ensure_commit_identity(self) -> None:
        name = self._git_config_value("user.name") or os.getenv("GIT_AUTHOR_NAME")
        email = self._git_config_value("user.email") or os.getenv("GIT_AUTHOR_EMAIL")
        if not name or not email:
            raise ContractStoreError(
                "Missing git commit identity. Configure `git config --global user.name` and `git config --global user.email`."
            )
        self._run_git("config", "user.name", name)
        self._run_git("config", "user.email", email)

    def _git_config_value(self, key: str) -> str | None:
        result = self._run_git("config", "--get", key, check=False)
        return result.stdout.strip() or None if result.returncode == 0 else None

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise ContractStoreError(result.stderr.strip() or result.stdout.strip() or "git command failed")
        return result


class GitLabApiContractStore(ContractStore):
    def __init__(
        self,
        base_url: str,
        project: str,
        branch: str,
        token: str,
        *,
        start_branch: str | None = None,
        timeout: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self.project = project
        self.branch = branch
        self.token = token
        self.start_branch = start_branch
        self.timeout = timeout

    def read_text(self, relative_path: str) -> str | None:
        body, _ = self._request(
            "GET",
            self._file_raw_url(relative_path, self.branch),
            allow_missing=True,
        )
        return None if body is None else body.decode("utf-8")

    def read_bytes(self, relative_path: str) -> bytes | None:
        body, _ = self._request(
            "GET",
            self._file_raw_url(relative_path, self.branch),
            allow_missing=True,
        )
        return body

    def write_batch(
        self,
        upserts: dict[str, str | bytes],
        deletes: list[str],
        commit_message: str | None = None,
    ) -> None:
        if not upserts and not deletes:
            return
        branch_exists = self._branch_exists(self.branch)
        ref = self.branch if branch_exists else self.start_branch
        if ref is None:
            raise ContractStoreError(
                f"Target branch `{self.branch}` does not exist. Set `API_CONTRACT_GITLAB_START_BRANCH` to create it via API."
            )

        actions: list[dict[str, object]] = []
        for relative_path, content in upserts.items():
            action = "update" if self._file_exists(relative_path, ref) else "create"
            if isinstance(content, bytes):
                encoded_content = base64.b64encode(content).decode("ascii")
                encoding = "base64"
            else:
                encoded_content = content
                encoding = "text"
            actions.append(
                {
                    "action": action,
                    "file_path": relative_path,
                    "content": encoded_content,
                    "encoding": encoding,
                }
            )
        for relative_path in deletes:
            if self._file_exists(relative_path, ref):
                actions.append({"action": "delete", "file_path": relative_path})

        if not actions:
            return

        payload: dict[str, object] = {
            "branch": self.branch,
            "commit_message": commit_message or "Update API contracts",
            "actions": actions,
        }
        if not branch_exists and self.start_branch:
            payload["start_branch"] = self.start_branch
        self._request_json("POST", self._commits_url(), payload)

    def list_files(self, prefix: str) -> list[str]:
        normalized_prefix = prefix.rstrip("/")
        results: list[str] = []
        page = 1
        while True:
            body, headers = self._request(
                "GET",
                self._repository_tree_url(normalized_prefix, page),
                allow_missing=True,
            )
            if body is None:
                return []
            items = json.loads(body.decode("utf-8"))
            for item in items:
                if item.get("type") == "blob" and isinstance(item.get("path"), str):
                    results.append(item["path"])

            next_page = ""
            if headers is not None:
                next_page = headers.get("X-Next-Page", "") or headers.get("x-next-page", "")
            if next_page:
                page = int(next_page)
                continue
            if len(items) >= 100:
                page += 1
                continue
            return sorted(results)

    def _branch_exists(self, branch: str) -> bool:
        body, _ = self._request("GET", self._branch_url(branch), allow_missing=True)
        return body is not None

    def _file_exists(self, relative_path: str, ref: str) -> bool:
        body, _ = self._request("HEAD", self._file_metadata_url(relative_path, ref), allow_missing=True)
        return body is not None

    def _request_json(self, method: str, url: str, payload: dict[str, object] | None = None) -> object:
        body, _ = self._request(method, url, payload=payload)
        return {} if body is None else json.loads(body.decode("utf-8"))

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, object] | None = None,
        *,
        allow_missing: bool = False,
    ) -> tuple[bytes | None, object | None]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("PRIVATE-TOKEN", self.token)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read(), response.headers
        except urllib.error.HTTPError as exc:
            if allow_missing and exc.code == 404:
                return None, getattr(exc, "headers", None)
            raise ContractStoreError(self._http_error_message(exc)) from exc
        except urllib.error.URLError as exc:
            raise ContractStoreError(str(exc.reason) or "GitLab API request failed") from exc

    def _commits_url(self) -> str:
        return f"{self._project_api_root()}/repository/commits"

    def _branch_url(self, branch: str) -> str:
        encoded_branch = urllib.parse.quote(branch, safe="")
        return f"{self._project_api_root()}/repository/branches/{encoded_branch}"

    def _file_raw_url(self, relative_path: str, ref: str) -> str:
        query = urllib.parse.urlencode({"ref": ref})
        return f"{self._project_api_root()}/repository/files/{self._quote_path(relative_path)}/raw?{query}"

    def _file_metadata_url(self, relative_path: str, ref: str) -> str:
        query = urllib.parse.urlencode({"ref": ref})
        return f"{self._project_api_root()}/repository/files/{self._quote_path(relative_path)}?{query}"

    def _repository_tree_url(self, prefix: str, page: int) -> str:
        params = {
            "ref": self.branch,
            "recursive": "true",
            "per_page": "100",
            "page": str(page),
        }
        if prefix:
            params["path"] = prefix
        query = urllib.parse.urlencode(params)
        return f"{self._project_api_root()}/repository/tree?{query}"

    def _project_api_root(self) -> str:
        encoded_project = urllib.parse.quote(self.project, safe="")
        return f"{self.base_url}/projects/{encoded_project}"

    def _quote_path(self, value: str) -> str:
        return urllib.parse.quote(value, safe="")

    def _http_error_message(self, exc: urllib.error.HTTPError) -> str:
        detail = ""
        try:
            body = exc.read()
        except Exception:  # pragma: no cover
            body = b""
        if body:
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = body.decode("utf-8", errors="replace").strip()
            else:
                if isinstance(data, dict):
                    detail = str(data.get("message") or data.get("error") or data).strip()
                else:
                    detail = str(data).strip()
        return detail or f"GitLab API request failed: HTTP {exc.code} for {exc.url}"


class LocalPathContractStore(ContractStore):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def read_text(self, relative_path: str) -> str | None:
        path = self.root / relative_path
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def read_bytes(self, relative_path: str) -> bytes | None:
        path = self.root / relative_path
        if not path.exists():
            return None
        return path.read_bytes()

    def write_batch(
        self,
        upserts: dict[str, str | bytes],
        deletes: list[str],
        commit_message: str | None = None,
    ) -> None:
        del commit_message
        for relative_path, content in upserts.items():
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        for relative_path in deletes:
            path = self.root / relative_path
            if path.exists():
                path.unlink()
                _cleanup_empty_dirs(path.parent, self.root)

    def list_files(self, prefix: str) -> list[str]:
        normalized = prefix.rstrip("/")
        root = self.root / normalized
        if root.is_file():
            return [normalized]
        if not root.exists():
            return []
        return sorted(path.relative_to(self.root).as_posix() for path in root.rglob("*") if path.is_file())


def build_contract_store(prefix: str = "API_CONTRACT_") -> ContractStore:
    source = os.getenv(f"{prefix}SOURCE", "github").strip().lower()
    default_branch = "test"
    if source in {"github", "git"}:
        branch = os.getenv(f"{prefix}GITHUB_BRANCH", default_branch).strip() or default_branch
        return GitContractStore(DEFAULT_CONTRACTS_REMOTE_URL, branch)
    if source in {"gitlab_api", "api"}:
        token = os.getenv(f"{prefix}GITLAB_TOKEN", "").strip()
        if not token:
            raise ContractStoreError(f"Missing `{prefix}GITLAB_TOKEN` for `gitlab_api` contract source.")
        base_url = os.getenv(f"{prefix}GITLAB_BASE_URL", DEFAULT_CONTRACTS_GITLAB_BASE_URL).strip()
        project = os.getenv(f"{prefix}GITLAB_PROJECT", DEFAULT_CONTRACTS_GITLAB_PROJECT).strip()
        branch = os.getenv(
            f"{prefix}GITLAB_BRANCH",
            os.getenv(f"{prefix}GITHUB_BRANCH", default_branch),
        ).strip() or default_branch
        start_branch = os.getenv(f"{prefix}GITLAB_START_BRANCH", "").strip() or None
        return GitLabApiContractStore(base_url, project, branch, token, start_branch=start_branch)
    if source in {"local_path", "local"}:
        root = os.getenv(f"{prefix}LOCAL_PATH", "").strip() or os.getenv(f"{prefix}LOCAL_SOURCE_PATH", "").strip()
        if not root:
            raise ContractStoreError(
                f"Missing `{prefix}LOCAL_PATH` or `{prefix}LOCAL_SOURCE_PATH` for `local_path` contract source."
            )
        return LocalPathContractStore(Path(root))
    raise ContractStoreError(
        f"Unsupported contract source: {source}. Supported values: github, git, gitlab_api, api, local_path, local."
    )


def _cleanup_empty_dirs(path: Path, stop_at: Path) -> None:
    current = path
    while current != stop_at and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
