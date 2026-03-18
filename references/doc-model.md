# Doc Model

## 对象定位

- `Doc` 是阅读对象
- 由 `Spec` 渲染生成
- 服务于查阅、review 和协作理解
- 不服务于事实判断、索引构建或生成决策

## 展示来源

- 主要来源于 `Spec`
- 仅允许引入少量与阅读直接相关的 `SERVICE` 上下文
- 不允许引入独立真相来源

## 展示内容

- Controller 概览
- 方法详情
- 请求
- 响应
- DTO 摘要
- 错误信息
- 源码定位
- `operationId`

## SERVICE 上下文边界

只允许展示：

- `service`
- `domain`
- `basePath`
- `pathPrefix`（若存在）

不展开：

- target 细节
- owner
- 生成规则
- 其他 service 级配置

## 检索信号展示边界

- `aliases`
- `tags`

不进入 `Doc` 主体展示。

## 禁止事项

- `Doc` 不能反向作为事实源
- `Doc` 不能引入独立规则
- `Doc` 不能承载 consumer 本地规则
- `Doc` 不能成为第二套系统模型
