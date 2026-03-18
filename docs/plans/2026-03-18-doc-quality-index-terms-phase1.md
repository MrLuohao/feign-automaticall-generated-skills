# Doc Quality And Index Terms Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve generated doc readability and `capabilityTerms` quality by cleaning numbered comments, replacing low-quality fallback copy, and filtering low-value index terms.

**Architecture:** Keep all phase-1 changes inside the provider-side text generation path. Add focused tests around summary extraction, description fallback, and index-term cleanup, then implement the minimal normalization helpers in `provider.py` without touching schema extraction or error parsing.

**Tech Stack:** Python 3 stdlib, `unittest`, existing provider/parser/index builder code

## Execution Status

更新时间：2026-03-18

- 状态：已完成
- 已新增三组 focused regression tests，分别锁定 summary、description、capability 目标行为
- 已在 `provider.py` 内完成注释清洗、fallback 文案改写和 search term 过滤
- focused verification:
  - `python3 -m unittest tests.test_github_source_workflow -k summary -v`
  - `python3 -m unittest tests.test_github_source_workflow -k description -v`
  - `python3 -m unittest tests.test_github_source_workflow -k capability -v`
- full verification:
  - `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
  - `python3 -m unittest discover -s tests -v`
- 当前全量结果：`Ran 33 tests` / `OK`

---

### Task 1: Lock numbered-comment cleanup with failing tests

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Write the failing tests**

Add tests that verify generated specs/docs do not keep numeric prefixes in summaries for representative controllers such as:

- `UserLoginOpenApiBaseController`
- `RoleController`
- `FddCallBackController`

Assert examples like:

- `0000发送登录/注册短信` becomes `发送登录/注册短信`
- `0501 查询当前用户的角色下拉列表` becomes `查询当前用户的角色下拉列表`
- `9901法大大人脸异步回调` becomes `法大大人脸异步回调`

**Step 2: Run focused tests to verify failure**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k summary -v`

Expected:

- FAIL because current summaries still keep numbering

**Step 3: Implement minimal comment-title normalization**

Modify [provider.py](/Users/luohao/.codex/skills/api-contract-client-workflow/scripts/api_contract/provider.py):

- add helper(s) to strip numeric prefixes and skip low-value comment lines
- apply normalization in `_extract_summary()`

**Step 4: Run focused tests to verify pass**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k summary -v`

Expected:

- PASS

### Task 2: Replace low-quality fallback description copy

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Write the failing tests**

Add tests for methods that currently fall back to low-quality copy, asserting that generated:

- `summary`
- `description`
- `response.description`

do not contain patterns like:

- `处理X并返回结果`
- raw camel-case concatenations such as `CallBack`, `DynamicsqlSelect`, `Gettmppositionlist`

**Step 2: Run focused tests to verify failure**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k description -v`

Expected:

- FAIL because current fallback copy still uses the old template

**Step 3: Implement minimal fallback rewrite**

Modify [provider.py](/Users/luohao/.codex/skills/api-contract-client-workflow/scripts/api_contract/provider.py):

- tighten `_infer_target_label()`
- improve `_translate_token()`
- rewrite `_description_for()` and `_response_description()` to emit concise natural Chinese phrases

**Step 4: Run focused tests to verify pass**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k description -v`

Expected:

- PASS

### Task 3: Filter low-value index terms and aliases

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Write the failing tests**

Add tests asserting generated search aliases/tags or `global.index.json` capability terms do not include:

- pure numeric tokens like `0602`
- generic template words like `处理`
- obvious bad splits from fallback generation

Also assert useful business tokens remain.

**Step 2: Run focused tests to verify failure**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k capability -v`

Expected:

- FAIL because low-value terms are still emitted

**Step 3: Implement minimal term cleanup**

Modify [provider.py](/Users/luohao/.codex/skills/api-contract-client-workflow/scripts/api_contract/provider.py):

- add low-value token filters
- avoid feeding cleaned-out tokens into aliases/tags
- keep business DTO/type names and meaningful path terms

**Step 4: Run focused tests to verify pass**

Run:

- `python3 -m unittest tests.test_github_source_workflow -k capability -v`

Expected:

- PASS

### Task 4: Update docs and verify full regression

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `docs/plans/2026-03-18-doc-quality-index-terms-phase1-design.md`
- Modify: `docs/plans/2026-03-18-doc-quality-index-terms-phase1.md`
- Test: `tests/test_github_source_workflow.py`

**Step 1: Update status docs**

Update:

- the relevant `P1.1 / P1.9 / P1.15` status in [API_CONTRACT_SKILL_待优化清单.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/API_CONTRACT_SKILL_待优化清单.md)
- the design doc acceptance section if implementation details changed
- this plan with execution status notes

**Step 2: Run syntax verification**

Run:

- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`

Expected:

- PASS

**Step 3: Run full regression**

Run:

- `python3 -m unittest discover -s tests -v`

Expected:

- PASS

**Step 4: Commit**

```bash
git add docs/API_CONTRACT_SKILL_待优化清单.md docs/plans/2026-03-18-doc-quality-index-terms-phase1-design.md docs/plans/2026-03-18-doc-quality-index-terms-phase1.md tests/test_github_source_workflow.py scripts/api_contract/provider.py
git commit -m "feat: improve generated doc copy and index terms"
```
