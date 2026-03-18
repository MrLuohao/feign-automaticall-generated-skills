# API Contract Optimization Roadmap

## Goal

把当前 [API_CONTRACT_SKILL_待优化清单.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/API_CONTRACT_SKILL_待优化清单.md) 中已经确认的问题，全部挂接到明确的阶段计划上，避免后续优化出现遗漏、重复或顺序混乱。

## Coverage

当前清单中的问题，按阶段映射如下：

### Phase 1: 文档可读性与索引词质量

对应问题：

- `P1.1` Doc 摘要与描述文案质量
- `P1.9` fallback 摘要 / 响应描述 / 索引词生成
- `P1.15` 注释提取对编号型标题与辅助信息的去噪

计划文件：

- [2026-03-18-doc-quality-index-terms-phase1-design.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/plans/2026-03-18-doc-quality-index-terms-phase1-design.md)
- [2026-03-18-doc-quality-index-terms-phase1.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/plans/2026-03-18-doc-quality-index-terms-phase1.md)

### Phase 2: 请求结构展示与输入语义

对应问题：

- `P1.6` 老式 query object 参数的请求展示不一致
- `P1.7` 动态 body 与基础设施参数的识别 / 展示仍需收口
- `P1.10` 文件上传接口的请求语义展示不准确
- `P1.14` 必填与校验约束语义仍有明显缺口

计划文件：

- [2026-03-18-request-structure-phase2.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/plans/2026-03-18-request-structure-phase2.md)

### Phase 3: 响应结构展示与包装类型

对应问题：

- `P1.4` 部分响应类型仍退化为 `Object`
- `P1.8` 原始 `Response` / `Response<?>` 过多，导致响应语义被压扁
- `P1.11` `PageDTO` 等包装型响应的外层结构信息丢失
- `P1.12` `Tree<T>` 等结构化泛型响应仍被当作标量展示
- `P1.13` 继承型 DTO / VO 的空壳类型展示过多

计划文件：

- [2026-03-18-response-structure-phase3.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/plans/2026-03-18-response-structure-phase3.md)

### Phase 4: 语义准确性与文档事实完整度

对应问题：

- `P1.2` 字段说明缺失率高，`无` 占位过多
- `P1.3` 嵌套类型展开深度仍有不足
- `P1.5` 错误信息栏位空值率偏高

计划文件：

- [2026-03-18-semantic-accuracy-phase4.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/plans/2026-03-18-semantic-accuracy-phase4.md)

### Phase 5: parser 兼容性与类型源码回溯

对应问题：

- `P2` `Unsupported method signature` 仍需继续收口
- `P3` `No supported controller methods found` 仍有剩余模式
- `P4` `缺少类型源码 / Missing java source` 仍要继续收口

计划文件：

- [2026-03-18-parser-compat-and-type-source-phase5.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/plans/2026-03-18-parser-compat-and-type-source-phase5.md)

### Phase 6: 真实环境验证与联调收口

对应问题：

- `P0` GitLab API 真实回放被 HTTPS/TLS 握手阻塞
- `P5` 真实 provider 仓库回放还需要继续做
- `P6` token / API 权限边界和分支策略需要真实验证

计划文件：

- [2026-03-18-environment-and-real-replay-phase6.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/plans/2026-03-18-environment-and-real-replay-phase6.md)

## Execution Order

建议顺序：

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4
5. Phase 5
6. Phase 6

理由：

- 先改善文档和索引词质量，立即提升可读性与可观察性
- 再修请求 / 响应展示，避免低质量文案影响结构判断
- 随后补语义准确性（字段说明、异常、嵌套类型）
- 最后再做 parser 扩容和真实环境联调，风险更可控

## Documentation Rule

后续每完成一个阶段，必须同步更新：

- [API_CONTRACT_SKILL_待优化清单.md](/Users/luohao/.codex/skills/api-contract-client-workflow/docs/API_CONTRACT_SKILL_待优化清单.md)
- 对应阶段计划文件中的执行状态
- 若范围变化，补充更新本路线文档
