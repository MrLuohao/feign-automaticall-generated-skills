# API Contract Client Workflow Handoff

更新时间：2026-03-19

## 当前项目状态

- 这个 skill 仓库已经收缩为最小可运行结构：`SKILL.md`、`references/`、`scripts/`、`templates/`、`tests/`
- 当前检索主链已经从旧 JSON 索引切到：
  - 真源：远端 contracts 仓库
  - 发布级索引：`indexes/releases/`
  - 本地缓存：SQLite
  - 生成锚点：唯一 `operationId`
- 当前默认策略：
  - 真源默认分支：`main`
  - 索引发布默认分支：`test`
  - 索引发布默认前缀：`indexes/releases/`
  - 默认本地缓存目录：当前项目下 `.cache/api-contract/`

## 已完成

### 架构改造

- provider 侧已收回为“只维护真源和 doc”，不再写旧 `global.index.json` / `operations.jsonl` / `inverted/*.json`
- 已实现发布级索引构建：
  - `manifest.json`
  - `router.sqlite.gz`
  - `shards/<service>/operations.sqlite.gz`
  - `delta/<version>.json`
- 已实现本地缓存管理：
  - 无缓存自动同步
  - 查询前轻量 manifest 检查
  - manifest 变更自动刷新
  - manifest 检查失败回退旧缓存
- 已实现 `ContractStoreArtifactPublisher`
  - 可把索引发布到任意 `ContractStore`
  - 当前默认用于 Git/SSH、GitLab API、本地路径
- 已保留可注入的 `LlmContextEnricher` 抽象
  - 当前 CLI 默认使用 `BasicContextEnricher`
  - 没有再强绑独立 HTTP 模型服务

### CLI 能力

- `provider sync`
- `provider delete-controller`
- `contracts index build`
- `contracts cache sync`
- `contracts cache status`
- `consumer search`
- `consumer generate`

### 测试状态

- 当前本仓库测试总数：`24`
- 当前结果：`OK`
- 已验证的重点包括：
  - 索引构建与压缩产物
  - delta manifest
  - 本地缓存同步/增量更新
  - ContractStore 发布索引
  - 真实缓存策略
  - consumer search/generate 主链
  - 默认发布分支/前缀

## 本次真实联调结果

### 真实 provider 联调

- 已成功对真实 provider 项目：
  - `/Users/luohao/Desktop/DST/user-center/dst-oa-server`
- 对真实 controller：
  - `com.dst.oa.modules.business.multi.controller.DstMultiIamUserController`
- 跑通：
  - `provider sync`
  - `contracts index build`

### 真实 consumer 联调

- 已成功在真实 consumer 项目：
  - `/Users/luohao/Desktop/DST/dst-app/dst-app-bff-service`
- 通过真实链路生成“编辑IAM用户”的 Feign 调用
- 生成文件位置：
  - `/Users/luohao/Desktop/DST/dst-app/dst-app-bff-service/src/main/java/com/dst/app/bff/infrastructure/acl/oa/client/DstMultiIamUserApi.java`
  - `/Users/luohao/Desktop/DST/dst-app/dst-app-bff-service/src/main/java/com/dst/app/bff/infrastructure/acl/oa/dto/DstMultiUserCreateDTO.java`

### 远端 test 分支状态

- 曾成功把 `DstMultiIamUserController` 真源和 `indexes/releases/` 索引发布到：
  - `git@gitlab.dstcar.com:dmp/ai-coding/dst-api-skills-repo.git`
  - `test` 分支
- 之后按用户要求，已经把远端 `test` 分支内容清空
- 当前结论：
  - `test` 分支现在是干净的，可重新开始测试

## 当前未完成

- 还没有把“真实 consumer 生成后如何与项目现有 ACL 目录风格对齐”做成规则
- 还没有针对多 service / 20 万接口规模做真实体量性能压测
- 还没有把当前默认策略提交到 git
- 还没有把真实 GitLab `test` 分支重新跑一遍全链路，因为最后一步用户要求先清空远端 `test`

## 当前外部副作用

- 远端 contracts 仓库 `test` 分支已清空
- `dst-app-bff-service` 里仍保留本次真实生成的 ACL 文件：
  - `src/main/java/com/dst/app/bff/infrastructure/acl/oa/client/DstMultiIamUserApi.java`
  - `src/main/java/com/dst/app/bff/infrastructure/acl/oa/dto/DstMultiUserCreateDTO.java`
- 本次联调用到的临时缓存目录已经清理

## 下次新窗口建议起手动作

先读本文件，再按下面顺序继续：

1. 确认远端 `test` 分支当前为空
2. 重新对目标 provider 跑一次：
   - `provider sync`
3. 重新对 `test` 分支跑一次：
   - `contracts index build`
4. 在真实 consumer 项目里跑：
   - `consumer search`
   - `consumer generate`
5. 检查生成的 ACL 落位、命名和 DTO 结构是否符合 `dst-app-bff-service` 当前风格

## 推荐环境变量

```bash
export API_CONTRACT_SOURCE=github
export API_CONTRACT_GITHUB_BRANCH=main

export API_CONTRACT_INDEX_PUBLISH_SOURCE=github
export API_CONTRACT_INDEX_PUBLISH_GITHUB_BRANCH=test
export API_CONTRACT_INDEX_PUBLISH_PREFIX=indexes/releases

export API_CONTRACT_INDEX_SOURCE=github
export API_CONTRACT_INDEX_GITHUB_BRANCH=test
export API_CONTRACT_INDEX_PREFIX=indexes/releases
```

## 备注

- 如果下次继续走真实链路，不要再用本地副本绕过远端
- 如果要重新验证生成链，请优先从已经清空的远端 `test` 分支重新开始
