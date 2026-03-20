# Contract Model

## 系统定位

- 这是公司级 Java API contracts 系统
- 同时服务开发者协作和 AI 代理执行
- provider 生产契约，consumer 消费契约
- 围绕统一远端真源协作
- 面向大规模、多服务、多接口场景
- 不负责全量 SDK 工程生成、框架初始化、鉴权或网关搭建

## 核心对象

- `SERVICE`：service 级唯一事实源
- `Contract Spec`：接口级唯一事实源
- `Index`：检索对象
- `Doc`：阅读对象，由 `Spec` 渲染生成

## 事实源规则

- service 级判断只读取 `SERVICE`
- 接口级判断只读取 `Spec`
- `Index` 和 `Doc` 都是派生产物，不是真源
- `Doc` 不能反向成为事实源、索引输入或生成输入
- 真源变更后，`Index` 和 `Doc` 必须同步更新
- `SERVICE` 允许人工维护
- `Spec` 允许有限人工维护，但代码事实以扫描结果为准

## 存储结构

远端 contracts 仓库固定采用以下结构：

```text
repo-root/
  services/
    <service>/
      SERVICE.yaml
      controllers/
        <Controller>/
          <Controller>.spec.yaml
          <Controller>.doc.md
```

- 仓库根就是 contracts 逻辑根
- 不引入 base path 模型层概念
- `Doc` 与 `Spec` 同层，但仍是派生对象
- 发布级检索索引不再与真源同仓存储，而是独立构建并分发到本地缓存
- 当前默认发布策略是写回同一 GitLab contracts 仓库的独立索引路径，默认分支为 `main`

## 索引总原则

- 检索链路固定为：`query -> local router index -> local service shard -> operationId -> spec`
- 本地缓存索引是运行时检索对象，真源仓库不是查询主路径
- 当前默认索引发布前缀为 `indexes/releases/`
- 全局 router index 只做 service 路由，不放完整 operation 明细
- service shard 是主要检索层
- shard 统一使用本地 SQLite 作为嵌入式检索载体
- 中文检索采用归一化、短语切分和有限同义扩展

## 全局不变量

- 不允许 local fallback
- 允许本地缓存索引；本地缓存是正式主路径，不是 fallback
- consumer 本地规则不进入远端真源
- 公司默认规则、service 差异规则、consumer 本地规则必须分层
- `Doc` 不反向驱动系统

## 调试期默认发布策略

- 真源读取默认仍走主真源分支
- 索引发布默认走 `main` 分支
- 索引发布默认前缀为 `indexes/releases/`
- 本地缓存默认目录为当前 skill 项目的 `.cache/api-contract/`

更多规则见：
- `provider-mode.md`
- `consumer-mode.md`
- `operation-id.md`
- `java-feign-defaults.md`
- `doc-model.md`
