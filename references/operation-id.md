# operationId

## 定义

`operationId` 是每个接口方法的稳定唯一标识，用于：

- provider 更新时匹配旧接口
- consumer 检索最终落点
- 生成代码时的目标定位

## 首次创建

- 首次接入时由 provider sync 自动生成
- 不采用人工手工指定作为常规机制
- 一旦旧 Spec 中已有 `operationId`，后续更新必须优先复用

## 稳定性规则

以下变化发生时，默认保持原 `operationId` 不变：

- Java 方法名变化
- path 变化但接口语义未变
- DTO 字段变化
- Controller 文件位置变化

只有当接口语义真正变成新的能力时，才允许新建 `operationId`

## 推荐格式

推荐统一采用稳定、可读、可唯一定位的命名格式，例如：

```text
<domain>.<layer>.<resource>.<action>
```

重点是稳定和唯一，不强制某个字符串模板。

## 匹配顺序

provider 更新已有接口时，匹配顺序固定为：

1. source method
2. `httpMethod + path`
3. 语义比对
4. 人工确认

## 人工修改边界

- 默认禁止手工修改 `operationId`
- 普通重命名、路径调整、DTO 变化都不应触发手改
- 只有接口语义真正变成新的能力时，才允许新建
