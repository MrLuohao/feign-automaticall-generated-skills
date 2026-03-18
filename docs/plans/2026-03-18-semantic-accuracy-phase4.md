# Semantic Accuracy Phase 4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve semantic completeness of generated docs by enriching field descriptions, deepening nested type expansion, and extracting basic error information.

**Architecture:** Build on the stabilized request/response rendering from earlier phases. Extend field-description inference, nested type recursion, and method error extraction in small, test-first increments.

**Tech Stack:** Python 3 stdlib, `unittest`, existing provider/parser/doc renderer code

## Execution Status

更新时间：2026-03-18

- 状态：已完成
- 已新增字段注解说明、嵌套引用类型、`BusinessException` 错误提取三组 focused regression tests
- 已补充字段注解说明抽取，并对缺失说明场景统一标记为“未提供说明”
- 已让类型收集顺着字段继续递归下钻，并增加去重与类型变量保护
- 已支持从 controller 方法体中提取最小可用的 `BusinessException` 错误信息
- focused verification:
  - `python3 -m unittest tests.test_github_source_workflow -k field_description -v`
  - `python3 -m unittest tests.test_github_source_workflow -k nested -v`
  - `python3 -m unittest tests.test_github_source_workflow -k errors -v`
- full verification:
  - `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
  - `python3 -m unittest discover -s tests -v`
- 当前全量结果：`Ran 42 tests` / `OK`

---

### Task 1: Improve field-description quality

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`

**Step 1: Write failing tests**

Cover DTOs where fields currently render as `无` despite meaningful comments or annotations.

**Step 2: Run focused tests**

- `python3 -m unittest tests.test_github_source_workflow -k field_description -v`

**Step 3: Implement better field-description extraction**

Include:

- Javadoc/comment text
- better fallback maps
- clearer distinction between “missing” and “unknown”

**Step 4: Re-run focused tests**

### Task 2: Deepen nested type expansion

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`

**Step 1: Write failing tests**

Cover:

- nested DTOs
- recursive referenced child objects
- callback payloads
- pagination element structures

**Step 2: Run focused tests**

- `python3 -m unittest tests.test_github_source_workflow -k nested -v`

**Step 3: Implement deeper recursive expansion with dedupe/guardrails**

**Step 4: Re-run focused tests**

### Task 3: Add basic error extraction

**Files:**
- Modify: `tests/test_github_source_workflow.py`
- Modify: `scripts/api_contract/provider.py`
- Modify: `scripts/api_contract/models.py`
- Modify: `scripts/api_contract/spec_io.py`
- Modify: `scripts/api_contract/doc_renderer.py`

**Step 1: Write failing tests**

Cover:

- direct `throw new BusinessException("...")` in controller methods
- direct `throw new BusinessException(RespCode.xxx)` in controller methods
- service-hop extraction for a bounded initial subset only if feasible

**Step 2: Run focused tests**

- `python3 -m unittest tests.test_github_source_workflow -k errors -v`

**Step 3: Implement minimal viable error extraction**

**Step 4: Re-run focused tests**

### Task 4: Update docs and run full regression

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `docs/plans/2026-03-18-semantic-accuracy-phase4.md`

**Step 1: Update backlog/doc status**

Mark progress for:

- `P1.2`
- `P1.3`
- `P1.5`

**Step 2: Run syntax verification**

- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`

**Step 3: Run full regression**

- `python3 -m unittest discover -s tests -v`

**Step 4: Commit**

```bash
git add docs/API_CONTRACT_SKILL_待优化清单.md docs/plans/2026-03-18-semantic-accuracy-phase4.md tests/test_github_source_workflow.py scripts/api_contract/provider.py scripts/api_contract/models.py scripts/api_contract/spec_io.py scripts/api_contract/doc_renderer.py
git commit -m "feat: improve semantic accuracy in generated docs"
```
