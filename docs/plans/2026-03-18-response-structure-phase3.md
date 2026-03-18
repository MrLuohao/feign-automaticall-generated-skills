# Response Structure Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve response-side docs for raw `Response`, wildcard/object returns, pagination wrappers, tree structures, and inherited response types.

**Architecture:** Extend response schema collection and doc rendering so wrapper types and inherited response models retain useful outer-layer information. Do not attempt service-body semantic inference beyond what is needed to reduce obvious `Object` flattening.

**Tech Stack:** Python 3 stdlib, `unittest`, existing provider/parser/doc renderer code

## Execution Status

更新时间：2026-03-18

- 状态：已完成
- 已新增 raw/wildcard/object-like response、page wrapper、tree/inheritance 三组 focused regression tests
- 已补充 raw `Response` / `Response<?>` / `Response<Object>` 的最小差异化响应描述
- 已让 `PageDTO` / `Page` / `IPage` / `Tree` 参与外层 schema 收集
- 已为继承型空壳响应类型增加“继承自 X”的最小标注
- focused verification:
  - `python3 -m unittest tests.test_github_source_workflow -k response -v`
  - `python3 -m unittest tests.test_github_source_workflow -k page -v`
  - `python3 -m unittest tests.test_github_source_workflow -k tree -v`
- full verification:
  - `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
  - `python3 -m unittest discover -s tests -v`
- 当前全量结果：`Ran 39 tests` / `OK`

---

### Task 1: Add failing tests for raw `Response` / `Response<?>` handling

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Modify: `scripts/api_contract/doc_renderer.py`

**Step 1: Write the failing tests**

Cover:

- raw `Response`
- `Response<?>`
- `Response<Object>`

using representative controllers such as:

- `FoundationEnterpriseController`
- `UserJobController`
- `RoleController`

Assert:

- docs distinguish explicit unknown/wildcard/object-like returns from truly parsed object schemas
- response descriptions become more truthful than generic `Object`

**Step 2: Run focused tests to verify failure**

- `python3 -m unittest tests.test_github_source_workflow -k response -v`

**Step 3: Implement minimal response-wrapper semantics**

**Step 4: Re-run focused tests**

### Task 2: Add failing tests for `PageDTO` / `Page<T>` outer-layer expansion

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Modify: `scripts/api_contract/doc_renderer.py`

**Step 1: Write the failing tests**

Cover:

- `SynPermissionController#page`
- `PositionRoleConfController#page`
- `DstEmployeeController#getEmployeeInfoPage`

Assert:

- `Response Types` shows the outer pagination model
- item element types are still expanded

**Step 2: Run focused tests to verify failure**

- `python3 -m unittest tests.test_github_source_workflow -k page -v`

**Step 3: Implement pagination wrapper expansion**

**Step 4: Re-run focused tests**

### Task 3: Add failing tests for `Tree<T>` and inherited response shell types

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Modify: `scripts/api_contract/doc_renderer.py`

**Step 1: Write the failing tests**

Cover:

- `PermissionController#parentRolePermissionSelect`
- `OrgController#orgServerTree`
- inherited VO/DTO wrappers like `SignRouterConfigVo extends SignRouterConfig`
- inherited response entities like `UnifyLogEnterprise extends UnifyLog`

Assert:

- tree responses are no longer rendered as pure scalar strings
- inherited shell types are either merged, annotated, or presented as “inherits from X”

**Step 2: Run focused tests to verify failure**

- `python3 -m unittest tests.test_github_source_workflow -k tree -v`

**Step 3: Implement tree/inheritance response rendering improvements**

**Step 4: Re-run focused tests**

### Task 4: Update docs and run full regression

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `docs/plans/2026-03-18-response-structure-phase3.md`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Update backlog/doc status**

Mark progress for:

- `P1.4`
- `P1.8`
- `P1.11`
- `P1.12`
- `P1.13`

**Step 2: Run syntax verification**

- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`

**Step 3: Run full regression**

- `python3 -m unittest discover -s tests -v`

**Step 4: Commit**

```bash
git add docs/API_CONTRACT_SKILL_待优化清单.md docs/plans/2026-03-18-response-structure-phase3.md tests/test_github_source_workflow.py scripts/api_contract/provider.py scripts/api_contract/doc_renderer.py
git commit -m "feat: improve response structure rendering"
```
