# Phase 1 Doc Quality And Index Terms Design

## Goal

在不改动请求/响应 schema 展示结构、不引入异常抽取和 service 级静态分析的前提下，先提升接口文档的可读性与 `capabilityTerms` 的信噪比。

本阶段只处理以下问题：

- `P1.1` Doc 摘要与描述文案质量
- `P1.9` fallback 摘要 / 响应描述 / 索引词生成过于依赖粗粒度 token
- `P1.15` 注释提取对编号型标题与辅助信息的去噪不足

## Scope

本阶段允许修改：

- [scripts/api_contract/provider.py](/Users/luohao/.codex/skills/api-contract-client-workflow/scripts/api_contract/provider.py)
- 相关测试文件
- 计划 / 待优化清单等文档

本阶段明确不处理：

- `PageDTO` / `Tree<T>` / 上传接口 / query object 的展示结构
- `Object` / `Response<?>` 的深层语义推断
- `BusinessException` / 错误码抽取
- 校验分组、`required=false`、动态 body 的结构化建模

## Problem Statement

当前文档质量的主要问题不在 schema 抽取本身，而在“标题词源”和“说明文案词源”。

具体表现：

- 注释首行如果带历史编号，会直接成为摘要，例如 `0000发送登录/注册短信`
- fallback 文案会退化成 `处理X并返回结果`
- token 翻译表太小，很多英文驼峰拆词或路径 token 会原样进入文档
- `capabilityTerms` 会继承摘要、方法名、路径 token 中的低价值词，例如编号词、模板词、异常切词结果

这些问题共享同一条词源链路，因此适合在一个阶段内集中治理。

## Chosen Approach

采用“单链路收口”的做法，只改 `provider.py` 里的注释清洗、摘要生成、描述生成、别名与标签生成规则。

理由：

- 改动面集中，容易验证
- 能同时改善 doc 与 index，不需要拆两轮
- 不会提前进入高风险的类型系统与异常抽取改造

## Design

### 1. 注释首行归一化

对 `_comment_lines()` / `_extract_summary()` 增加轻量去噪规则：

- 去除纯编号前缀，如 `0001`、`0501`、`9902`
- 保留编号后的真实标题正文
- 排除 YApi 链接行、平台外链行、纯辅助说明行
- 避免把 `@param`、`@return`、作者/时间类元信息当作摘要正文

预期效果：

- `0000发送登录/注册短信` -> `发送登录/注册短信`
- `0501 查询当前用户的角色下拉列表` -> `查询当前用户的角色下拉列表`
- `9901法大大人脸异步回调` -> `法大大人脸异步回调`

### 2. fallback 摘要与 description 改写

对 `_extract_summary()`、`_description_for()`、`_response_description()` 做统一收口：

- 禁止继续输出 `处理X并返回结果`
- 当注释质量不足时，优先基于“动作 + 目标”生成自然中文短语
- 当目标无法稳定推断时，宁可回退为简洁中性文案，也不要输出低质量英文拼接

预期效果：

- `处理CallBack并返回结果` -> `处理回调请求`
- `处理DynamicsqlSelect并返回结果` -> `执行动态查询`
- `处理Gettmppositionlist并返回结果` -> `查询临时岗位列表`

### 3. token 归一化与低价值词去噪

对 `_translate_token()`、`_intent_aliases_for()`、`_tags_for()` 的输入做清洗：

- 过滤纯数字 token
- 过滤模板性低价值词，例如 `处理`
- 对英文 token 做更稳的映射或降噪，减少 `capitalize` 生硬直出
- 将文档 fallback 词源和索引词源做轻度隔离，避免低质量摘要直接污染 `capabilityTerms`

预期效果：

- `capabilityTerms` 中不再出现 `0602`、`0603`、`处理`
- 减少异常切词和低质量英文片段

## Testing Strategy

先补测试，再实现：

- 为编号注释清洗新增测试
- 为 fallback 摘要 / description 新规则新增测试
- 为 `capabilityTerms` 去噪新增测试
- 跑全量 `unittest`

测试优先覆盖：

- `UserLoginOpenApiBaseController`
- `RoleController`
- `FddCallBackController`
- `UserJobController`
- 已有 `gitlab_api` / parser 回归测试不应被破坏

## Documentation Rule

本阶段新增一条持续规则：

- 每解决一个待优化项，必须同步更新 [docs/API_CONTRACT_SKILL_待优化清单.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/API_CONTRACT_SKILL_待优化清单.md)
- 若阶段范围、验收标准或结论发生变化，也必须同步更新本设计文档与实施计划

## Implementation Status

更新时间：2026-03-18

- 已完成编号型注释摘要清洗，编号前缀和 `YApi`/URL 元信息不会再直接进入摘要首行
- 已完成 fallback summary / description / response description 的模板文案替换
- 已完成 aliases / tags / path tokens 的纯数字与低价值词过滤
- 已新增 `RoleController`、`FddCallBackController`、`UserLoginOpenApiBaseController` 三组 Phase 1 回归测试
- 已完成 `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
- 已完成 `python3 -m unittest discover -s tests -v`，当前结果为 `Ran 33 tests` / `OK`

## Acceptance Criteria

满足以下条件即可视为第一阶段完成：

- 目标 controller 的方法摘要不再保留编号前缀
- 文档中不再出现 `处理X并返回结果` 这类模板 description
- `capabilityTerms` 不再包含纯编号词和明显模板词
- 全量测试通过
- 待优化清单中的相关条目状态已同步更新
