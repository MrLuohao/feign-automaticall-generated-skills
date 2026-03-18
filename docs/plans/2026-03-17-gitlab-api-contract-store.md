# GitLab API Contract Store Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a GitLab API-backed `ContractStore` so remote contracts can be read and written with token/API auth instead of Git-over-SSH.

**Architecture:** Keep `ContractStore` as the single integration boundary. Add `GitLabApiContractStore` in `scripts/api_contract/contract_store.py`, select it through `build_contract_store()`, and leave provider/search/generator logic unchanged. Lock behavior with focused store tests first, then run the full suite.

**Tech Stack:** Python 3 stdlib (`urllib`, `json`), `unittest`, existing `ContractStore` abstraction

---

### Task 1: Add failing tests for API store reads and source selection

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Write the failing tests**

Add tests that:
- instantiate `GitLabApiContractStore`
- mock HTTP responses for file reads
- assert `build_contract_store()` returns the API-backed store when `API_CONTRACT_SOURCE=gitlab_api`
- assert missing API config raises `ContractStoreError`

**Step 2: Run tests to verify they fail**

Run:
- `python3 -m unittest tests.test_github_source_workflow.GitHubSourceWorkflowTest.test_gitlab_api_contract_store_reads_text -v`
- `python3 -m unittest tests.test_github_source_workflow.GitHubSourceWorkflowTest.test_build_contract_store_returns_gitlab_api_store -v`

Expected:
- FAIL because `GitLabApiContractStore` does not exist yet
- or FAIL because builder does not support `gitlab_api`

**Step 3: Write minimal implementation**

Add the new store class skeleton and builder branch in `scripts/api_contract/contract_store.py`.

**Step 4: Run tests to verify they pass**

Run the same focused test commands and confirm PASS.

### Task 2: Add failing tests for tree listing and commit writes

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Write the failing tests**

Add tests that:
- verify `list_files()` handles paginated repository tree responses
- verify `write_batch()` posts the expected commit actions
- verify `write_batch()` uses `start_branch` when the target branch is absent

**Step 2: Run tests to verify they fail**

Run:
- `python3 -m unittest tests.test_github_source_workflow.GitHubSourceWorkflowTest.test_gitlab_api_contract_store_lists_files_with_pagination -v`
- `python3 -m unittest tests.test_github_source_workflow.GitHubSourceWorkflowTest.test_gitlab_api_contract_store_writes_batch_via_commit_api -v`

Expected:
- FAIL because the behavior is not implemented yet

**Step 3: Write minimal implementation**

Implement:
- repository tree pagination
- branch existence check
- commit API payload generation
- error translation to `ContractStoreError`

**Step 4: Run tests to verify they pass**

Run the same focused tests and confirm PASS.

### Task 3: Update docs and verify full regression

**Files:**
- Modify: `README.md`
- Modify: `memory/project-context-handoff.md`
- Modify: `scripts/api_contract/contract_store.py`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Update operator-facing docs**

Document:
- supported `API_CONTRACT_SOURCE` values
- GitLab API environment variables
- compatibility note that default git/SSH mode still exists

**Step 2: Run focused store tests**

Run:
- `python3 -m unittest tests.test_github_source_workflow.GitHubSourceWorkflowTest.test_gitlab_api_contract_store_reads_text -v`
- `python3 -m unittest tests.test_github_source_workflow.GitHubSourceWorkflowTest.test_gitlab_api_contract_store_lists_files_with_pagination -v`
- `python3 -m unittest tests.test_github_source_workflow.GitHubSourceWorkflowTest.test_gitlab_api_contract_store_writes_batch_via_commit_api -v`

Expected: PASS

**Step 3: Run full verification**

Run:
- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
- `python3 -m unittest discover -s tests -v`

Expected: all commands succeed

---

## Execution Status

### 已完成

- Task 1 已完成
- Task 2 已完成
- Task 3 已完成

实际结果：

- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py` 已通过
- `python3 -m unittest discover -s tests -v` 已通过
- 当前全量结果为 `Ran 30 tests` / `OK`

### 后续补充验证

仍需继续完成一项真实环境验证：

- 用 `API_CONTRACT_SOURCE=gitlab_api` 对真实 GitLab 仓库做一轮 `provider sync + contracts rebuild-index` 回放

当前阻塞不是代码，而是环境：

- 当前机器到 `gitlab.dstcar.com` HTTPS API 的 TLS 握手失败
- 同机 `curl` / `nscurl` / `urllib` 都能稳定复现

因此本计划的代码实施已完成，但真实 API mode 联调仍需额外环境排障。
