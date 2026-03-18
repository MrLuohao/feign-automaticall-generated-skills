# Request Structure Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve request-side doc accuracy for legacy query objects, dynamic bodies, file uploads, and validation semantics without changing remote store behavior.

**Architecture:** Extend the provider-side request parameter extraction model and doc rendering so the generated spec/doc can distinguish query-object inputs, multipart/file inputs, dynamic JSON bodies, and richer validation semantics. Keep the changes local to parameter parsing, request schema assembly, and markdown rendering.

**Tech Stack:** Python 3 stdlib, `unittest`, existing provider/parser/doc renderer code

## Execution Status

更新时间：2026-03-18

- 状态：已完成
- 已新增 legacy query object、multipart/file input、dynamic body / validation 三组 focused regression tests
- 已扩展 `RequestModel`，支持 `queryObjects` 展示
- 已完成 `MultipartFile` -> `fileParts` 语义收口
- 已补充动态 body 的非固定 schema 描述，以及 `defaultValue` / 常见校验注解的请求参数说明
- focused verification:
  - `python3 -m unittest tests.test_github_source_workflow -k request -v`
  - `python3 -m unittest tests.test_github_source_workflow -k multipart -v`
  - `python3 -m unittest tests.test_github_source_workflow -k validation -v`
- full verification:
  - `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
  - `python3 -m unittest discover -s tests -v`
- 当前全量结果：`Ran 36 tests` / `OK`

---

### Task 1: Add failing tests for legacy query-object request rendering

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Modify: `scripts/api_contract/doc_renderer.py`

**Step 1: Write the failing tests**

Cover representative controllers:

- `RoleController#roleExport(RoleQuery query)`
- `SynPermissionController#push(PermissionDTO permissionDTO)`
- `FddCallBackController#userAuthEleCallBack(FaceAuthCallBackResponse response)`

Assert:

- `Request Types` still includes the DTO
- `### 请求` no longer shows “无请求参数” for legacy object inputs
- the doc explicitly identifies them as query-object or callback payload input

**Step 2: Run focused tests to verify failure**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k request -v`

Expected:

- FAIL

**Step 3: Implement minimal query-object request model**

Update provider/doc-rendering code to:

- keep legacy object inputs distinct from scalar query params
- render them in a dedicated request section instead of silently dropping them

**Step 4: Re-run focused tests**

Expected:

- PASS

### Task 2: Add failing tests for multipart and file-upload semantics

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Modify: `scripts/api_contract/doc_renderer.py`

**Step 1: Write the failing tests**

Cover:

- `AliOcrOpenApiController`
- `UserJobController#importOrgType`
- `UserJobController#importInit`

Assert:

- `MultipartFile` is not rendered as plain `queryParams`
- upload requests are marked as multipart/file input
- any companion scalar params remain visible

**Step 2: Run focused tests to verify failure**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k multipart -v`

Expected:

- FAIL

**Step 3: Implement multipart-aware rendering**

Adjust request extraction / rendering to:

- identify file inputs explicitly
- distinguish file parts from plain query params
- keep markdown readable for upload endpoints

**Step 4: Re-run focused tests**

Expected:

- PASS

### Task 3: Add failing tests for dynamic body and validation semantics

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Modify: `scripts/api_contract/doc_renderer.py`

**Step 1: Write the failing tests**

Cover:

- `BackendController#updateUserAuth(@RequestBody Map<String, Object> param)`
- controllers using `@Validated`, `@Valid`, `@NotBlank`, `@NotNull`, `@Length`, `@Size`

Assert:

- dynamic JSON body is explicitly labeled as non-fixed schema
- request parameter/field docs retain more validation semantics
- `required=false` and `defaultValue` semantics are handled where present

**Step 2: Run focused tests to verify failure**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k validation -v`

Expected:

- FAIL

**Step 3: Implement minimal validation-aware request semantics**

Update request parsing to:

- preserve dynamic-body labeling
- enrich required/constraints metadata
- avoid polluting query-object candidates with infrastructure params like `HttpServletRequest`

**Step 4: Re-run focused tests**

Expected:

- PASS

### Task 4: Update docs and run full regression

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `docs/plans/2026-03-18-request-structure-phase2.md`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Update backlog/doc status**

Mark progress for:

- `P1.6`
- `P1.7`
- `P1.10`
- `P1.14`

**Step 2: Run syntax verification**

- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`

**Step 3: Run full regression**

- `python3 -m unittest discover -s tests -v`

**Step 4: Commit**

```bash
git add docs/API_CONTRACT_SKILL_待优化清单.md docs/plans/2026-03-18-request-structure-phase2.md tests/test_github_source_workflow.py scripts/api_contract/provider.py scripts/api_contract/doc_renderer.py
git commit -m "feat: improve request structure rendering"
```
