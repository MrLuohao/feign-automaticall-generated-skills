---
name: api-contract-client-workflow
description: 用于 Java Spring 接口契约同步、Controller 契约清理，以及在当前 Java 项目生成 OpenFeign 调用代码。凡是涉及同步/更新/删除接口契约，或根据 `Controller.java`、`com.xxx.Controller`、自然语言需求生成 Feign 调用的请求，都应触发。
---

# API Contract Client Workflow

## Overview

这个 skill 负责两类工作：

- provider 侧：把 Java Spring Controller 同步为标准 contracts
- consumer 侧：基于本地缓存索引检索接口，并按真源生成 Java/OpenFeign 调用代码

远端 contracts 仓库是真源。`SERVICE.yaml` 和 `Controller.spec.yaml` 是真源对象，`Doc` 和 `Index` 是派生产物。
检索默认走本地缓存的 SQLite 索引；生成时再按唯一 `operationId` 回源读取真源。

## When To Use

以下请求必须进入本 skill：

- 同步、更新、补全、重新扫描接口契约
- 删除某个 Controller 对应的 spec/doc
- 在当前 Java 项目生成某个接口的 Feign 调用代码
- 请求里出现 `com.xxx.Controller`、`*Controller.java`、`controller / 接口 / 接口控制器` 等对象词，并伴随同步、生成、更新、删除动作

不要用于：

- 框架初始化
- 网关、鉴权、基础设施搭建
- Node/PHP 客户端生成

## Execution Entry

统一入口：

```bash
python3 scripts/api_contract_cli.py ...
```

当前默认工作流：

- 真源继续从 contracts 真源仓库读取并写回 `test` 分支
- 索引构建产物默认发布到与真源相同的 `test` 分支
- 默认发布前缀为 `indexes/releases/`
- 本地检索默认使用缓存索引，查询前会做轻量版本检查

## Recommended Debug Workflow

调试期推荐固定使用：

```bash
export API_CONTRACT_SOURCE=github
export API_CONTRACT_GITHUB_BRANCH=test

export API_CONTRACT_INDEX_PUBLISH_SOURCE=github
export API_CONTRACT_INDEX_PUBLISH_GITHUB_BRANCH=test
export API_CONTRACT_INDEX_PUBLISH_PREFIX=indexes/releases

export API_CONTRACT_CACHE_DIR="/Users/luohao/.codex/skills/api-contract-client-workflow/.cache/api-contract"
```

最小联调链路：

```bash
# 1. provider 同步真源
python3 scripts/api_contract_cli.py provider sync \
  --provider-repo /path/to/provider-repo \
  --controller com.xxx.Controller \
  --domain your-domain \
  --service-owner your-name

# 2. 构建并发布索引产物到 test 分支
python3 scripts/api_contract_cli.py contracts index build \
  --output-dir /tmp/api-contract-index-release

# 3. 本地同步缓存
python3 scripts/api_contract_cli.py contracts cache sync \
  --index-base-url file:///tmp/api-contract-index-release

# 4. 检索接口
python3 scripts/api_contract_cli.py consumer search \
  --query "查询某个接口" \
  --consumer-repo /path/to/consumer-repo \
  --index-base-url file:///tmp/api-contract-index-release

# 5. 生成 Feign 调用代码
python3 scripts/api_contract_cli.py consumer generate \
  --query "查询某个接口" \
  --consumer-repo /path/to/consumer-repo \
  --index-base-url file:///tmp/api-contract-index-release
```

说明：

- 若不传 `--index-base-url`，则需要提前把索引发布到远端可读取位置，并通过环境变量提供发布源
- 调试期建议先用本地 `output-dir + file://` 路径验证
- 验证通过后，直接发布到远端 `test` 分支索引路径
- 若不显式设置 `API_CONTRACT_CACHE_DIR`，默认缓存目录为当前 skill 项目的 `.cache/api-contract/`

优先阅读：

- `references/contract-model.md`
- `references/provider-mode.md`
- `references/consumer-mode.md`
- `references/operation-id.md`
- `references/java-feign-defaults.md`
- `references/doc-model.md`
