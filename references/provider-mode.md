# Provider Mode

## 输入

- provider 项目源码
- Controller
- DTO/VO
- domain
- service owner
- 旧 contracts（若存在，仅作语义参考）

## 产出

- `services/<service>/SERVICE.yaml`
- `services/<service>/controllers/<Controller>/<Controller>.spec.yaml`
- `services/<service>/controllers/<Controller>/<Controller>.doc.md`
- 对应的 global/shard 索引更新

## 同步规则

- 代码事实以源码扫描结果为准
- method 级错误信息进入真源
- 首次接入 service 时创建 `SERVICE.yaml`
- 首次接入时必须补齐 `owner.name`
- 首次接入时必须补齐 target 与基础路径规则
- 语义字段按当前方案：以源码重推为主
- 默认收录全部接口
- 使用 `@ApiContractIgnore` 显式排除不对外接口
- 支持类级与方法级排除
- 类级排除表示整个 Controller 不进入 contracts
- 方法级排除表示该方法不进入 `Spec / Doc / Index`
- 若一个 Controller 全部方法都被排除，则本次同步按整类排除处理
- 被排除接口重新同步时，应自动清理旧 `spec/doc` 与对应索引条目

## 删除规则

- 已删除接口直接从 `Spec` 中移除，不保留 deleted 标记
- 支持 `provider delete-controller` 删除整个 Controller 对应 spec/doc
- 不扩展到 delete-service

## 失败条件

- 关键代码事实缺失时失败
- 真源无法正确写入远端仓库时失败
- 不允许通过 `Doc` 或旧索引兜底
- 不允许 local fallback

## 附属能力

- 支持 service 级 rebuild
- rebuild 只作为修复与校验能力
- rebuild 不是日常主流程
