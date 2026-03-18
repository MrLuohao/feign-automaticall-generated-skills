---
name: api-contract-client-workflow
description: 用于 Java Spring 接口契约同步、Controller 契约清理，以及在当前 Java 项目生成 OpenFeign 调用代码。凡是涉及同步/更新/删除接口契约，或根据 `Controller.java`、`com.xxx.Controller`、自然语言需求生成 Feign 调用的请求，都应触发。
---

# API Contract Client Workflow

## Overview

这个 skill 负责两类工作：

- provider 侧：把 Java Spring Controller 同步为标准 contracts
- consumer 侧：基于 contracts 检索接口并生成 Java/OpenFeign 调用代码

远端 contracts 仓库是真源。`SERVICE.yaml` 和 `Controller.spec.yaml` 是真源对象，`Doc` 和 `Index` 是派生产物。

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

优先阅读：

- `references/contract-model.md`
- `references/provider-mode.md`
- `references/consumer-mode.md`
- `references/operation-id.md`
- `references/java-feign-defaults.md`
- `references/doc-model.md`

查看触发样例：

- `examples/trigger-examples.md`
