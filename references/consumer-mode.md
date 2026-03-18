# Consumer Mode

## 行为链

consumer 行为链固定为：

`global.index -> service shard -> spec -> 本地结构识别 -> 生成`

## 检索规则

- 先读 `global.index.json`
- 再进入少量 service shard 做主检索
- 候选收敛后再回源 `Spec`
- 最终必须落到唯一 `operationId`
- 未形成唯一高置信候选时，不允许直接生成

## 终止策略

- 路由上限：Top3 services
- 候选召回上限：Top50
- Spec 回源确认上限：Top5
- 仍未收敛则终止
- 返回未命中或歧义结论
- 提示补线索、补契约或联系 owner
- 不自动扩散搜索
- 不生成近似代码

## 生成规则优先级

1. 公司默认 Java/OpenFeign 规则
2. `SERVICE.yaml` 的 provider 服务级差异
3. consumer 本地规则决定落位与命名

## consumer 本地规则

- consumer 本地规则不进入远端 contracts 真源
- 在本地生成前识别当前 consumer 项目结构
- 不是云端推断

优先级固定为：

1. consumer 仓库根目录本地 YAML 规则
2. 本地项目结构自动推断
3. 公司默认落位规则

### 推断歧义

- 自动推断出现多个候选时，交互模式下必须确认
- 非交互模式下应直接失败
- 不允许自动选择首个候选并继续写文件

## 适用语言

- 只生成 Java/OpenFeign
- 不再提供 Node/PHP 生成分支
