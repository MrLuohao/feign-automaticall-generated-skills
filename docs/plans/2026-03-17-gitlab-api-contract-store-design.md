# GitLab API Contract Store Design

**Goal:** Replace Git-over-SSH writes to the remote contracts repository with a token/API-backed path, without changing the contracts model, CLI command surface, or index layout.

## Problem

Current remote access is hard-wired to `GitContractStore`, which clones the contracts repo into a temp directory and pushes via SSH. That has three practical issues:

- It depends on local SSH access and git identity being configured.
- It couples remote transport concerns to git CLI behavior.
- It keeps the current P0 goal blocked even though the contracts model itself is already stable.

## Non-Goals

- Do not change `SERVICE.yaml` / `Controller.spec.yaml` / `Controller.doc.md`.
- Do not change `indexes/global.index.json` to split-global in this iteration.
- Do not change CLI commands or provider/consumer workflow semantics.
- Do not add non-stdlib Python dependencies.

## Approaches Considered

### Option 1: Patch `GitContractStore` to shell out to HTTP tooling

Pros:
- Smallest visible diff.

Cons:
- Keeps git-oriented control flow in place.
- Hard to test cleanly.
- Blurs transport concerns with repository state management.

### Option 2: Add a second `ContractStore` implementation backed by GitLab HTTP APIs

Pros:
- Keeps transport concerns isolated behind the existing abstraction.
- Minimizes impact on `provider.py`, `search.py`, and CLI behavior.
- Easy to switch by environment variable.
- Straightforward to test with mocked HTTP responses.

Cons:
- Requires a new API client path for read/list/write semantics.

### Option 3: Change provider/consumer code to talk to APIs directly

Pros:
- None worth keeping for this repo.

Cons:
- Breaks the current abstraction.
- Spreads transport logic across unrelated modules.
- Makes future index migration harder, not easier.

## Decision

Choose Option 2.

Add `GitLabApiContractStore` alongside the existing `GitContractStore`, keep `ContractStore` as the only integration boundary, and switch implementations in `build_contract_store()` based on environment variables.

## Proposed Design

### Store interface

Keep `ContractStore` unchanged:

- `read_text(relative_path)`
- `write_batch(upserts, deletes, commit_message)`
- `list_files(prefix)`

This keeps `provider`, `search`, `generator`, and `rebuild_index` unchanged.

### New implementation

Add `GitLabApiContractStore` in `scripts/api_contract/contract_store.py` with:

- `base_url`
- `project`
- `branch`
- `token`
- optional `start_branch`

Use GitLab repository APIs:

- `GET /projects/:id/repository/files/:file_path/raw?ref=:branch` for `read_text`
- `GET /projects/:id/repository/tree?path=:prefix&ref=:branch&recursive=true&per_page=100&page=:n` for `list_files`
- `POST /projects/:id/repository/commits` with `actions[]` for `write_batch`
- `GET /projects/:id/repository/branches/:branch` to detect branch existence

### Branch behavior

- If target branch exists, commit directly to it.
- If target branch does not exist and `API_CONTRACT_GITLAB_START_BRANCH` is set, create the first commit using `start_branch`.
- If target branch does not exist and no start branch is configured, fail with a clear error.

This is intentionally narrower than the current orphan-branch git fallback, because GitLab HTTP APIs do not provide a simple empty-orphan equivalent.

### Environment variables

Keep current git mode as default for compatibility.

Add API mode variables:

- `API_CONTRACT_SOURCE=gitlab_api`
- `API_CONTRACT_GITLAB_BASE_URL`
- `API_CONTRACT_GITLAB_PROJECT`
- `API_CONTRACT_GITLAB_TOKEN`
- `API_CONTRACT_GITLAB_BRANCH` with fallback to existing `API_CONTRACT_GITHUB_BRANCH`
- `API_CONTRACT_GITLAB_START_BRANCH` optional

### Error handling

- Convert HTTP failures to `ContractStoreError`.
- Treat `404` on file read as missing file and return `None`.
- Treat `404` on tree listing as empty list when the path or branch is absent.
- Preserve "no staged changes => no write" behavior by skipping commit creation when `upserts` and `deletes` are both empty.

## Testing Strategy

Use TDD and add focused tests before implementation:

1. API store `read_text` returns file content from GitLab raw file endpoint.
2. API store `list_files` paginates and returns only file paths under a prefix.
3. API store `write_batch` sends commit actions and uses `start_branch` when needed.
4. `build_contract_store()` returns API store when `API_CONTRACT_SOURCE=gitlab_api`.
5. Missing API configuration fails with a useful error.

Then run full verification to ensure existing 53 tests remain green.

## Expected Outcome

- Current git/SSH path keeps working.
- API mode becomes available behind env configuration.
- `provider sync` and `contracts rebuild-index` can write remote contracts without SSH.

## Execution Update

2026-03-17 实际落地结果：

- `GitLabApiContractStore` 已实现
- `build_contract_store()` 已支持 `API_CONTRACT_SOURCE=gitlab_api`
- 本地测试当前为 `30` 条并全部通过
- 默认 Git SSH 路径已做过一轮真实远端回放，确认仍可正常写回

当前未打通的不是代码逻辑，而是真实环境：

- 当前机器访问 `https://gitlab.dstcar.com/api/v4/...` 会在 HTTPS/TLS 握手阶段失败
- 因此 `gitlab_api` 模式尚未完成真实远端回放验证

这意味着：

- 设计目标里的“API mode 可真实替代 SSH”在代码层已完成
- 但在真实环境层仍有一个外部 TLS 阻塞待排查
