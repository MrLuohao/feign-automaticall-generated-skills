# Parser Compat And Type Source Phase 5 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Continue closing parser compatibility gaps and type-source lookup gaps that still cause unsupported signatures, missing controllers, or incomplete schemas.

**Architecture:** Keep parser and type-source work isolated from doc copy/rendering phases. Expand signature parsing and source lookup only through test-driven coverage of real provider samples.

**Tech Stack:** Python 3 stdlib, `unittest`, Java source scanning, optional source-jar retrieval

## Execution Status

更新时间：2026-03-18

- 状态：已完成
- 已新增 package-private signature、fully-qualified mapping controller discovery、本地 `record` type-source 三组 focused regression tests
- 已支持 package-private controller 方法签名
- 已支持 fully-qualified Spring mapping 注解的 controller 方法发现
- 已补充本地 `record` 类型的源码定位与 schema 解析
- focused verification:
  - `python3 -m unittest tests.test_github_source_workflow -k signature -v`
  - `python3 -m unittest tests.test_github_source_workflow -k supported_controller -v`
  - `python3 -m unittest tests.test_github_source_workflow -k missing_source -v`
- full verification:
  - `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
  - `python3 -m unittest discover -s tests -v`
- 当前全量结果：`Ran 45 tests` / `OK`

---

### Task 1: Expand unsupported-signature coverage

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`

**Step 1: Add failing tests for representative unsupported signatures**

**Step 2: Run focused tests**

- `python3 -m unittest tests.test_github_source_workflow -k signature -v`

**Step 3: Implement minimal parser support**

**Step 4: Re-run focused tests**

### Task 2: Expand “no supported controller methods found” coverage

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`

**Step 1: Add failing tests for older annotation/layout styles**

**Step 2: Run focused tests**

- `python3 -m unittest tests.test_github_source_workflow -k supported_controller -v`

**Step 3: Implement minimal controller method discovery improvements**

**Step 4: Re-run focused tests**

### Task 3: Improve type-source lookup across modules and jars

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`

**Step 1: Add failing tests for cross-module and missing-source cases**

**Step 2: Run focused tests**

- `python3 -m unittest tests.test_github_source_workflow -k missing_source -v`

**Step 3: Improve local-source / source-jar / binary-jar resolution order**

**Step 4: Re-run focused tests**

### Task 4: Update docs and run full regression

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `docs/plans/2026-03-18-parser-compat-and-type-source-phase5.md`

**Step 1: Update backlog/doc status**

Mark progress for:

- `P2`
- `P3`
- `P4`

**Step 2: Run syntax verification**

- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`

**Step 3: Run full regression**

- `python3 -m unittest discover -s tests -v`

**Step 4: Commit**

```bash
git add docs/API_CONTRACT_SKILL_待优化清单.md docs/plans/2026-03-18-parser-compat-and-type-source-phase5.md tests/test_github_source_workflow.py scripts/api_contract/provider.py
git commit -m "feat: extend parser compatibility and type source lookup"
```
