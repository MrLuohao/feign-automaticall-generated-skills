# API Contract Sync Failure Summary

更新时间：2026-03-20

## 背景

- 远端 contracts 仓库 `main` 与 `test` 分支内容已按要求清空
- 当前默认策略已调整为：真源与发布级索引统一写入 `test` 分支
- 本文件用于归档本轮真实链路同步失败项，作为后续优化修复清单

## 失败总览

- `dst-app`: `5 / 41`
- `ocr-service`: `0 / 5`
- `message-center`: `4 / 39`
- `goods-activity`: `325 / 392`
- `user-center`: `162 / 285`

## 主要失败类型

- 类型源码缺失
  典型报错：`Missing java source for ...`、`缺少类型源码: ...`
- Controller 方法映射不受当前解析器支持
  典型报错：`No supported controller methods found ...`
- 特殊签名 / 特殊映射格式暂未覆盖
  典型报错：`Unsupported mapping format`、`Unsupported method signature`

## 各服务代表性失败

### `dst-app`

- `com.dst.app.bff.modules.business.universal.commonlyUsedFunction.controller.CommonlyUsedFunctionController`
  `Missing java source for com.dst.app.bff.common.domain.acl.universal.commonlyUsedFunction.Child`
- `com.dst.app.bff.modules.openapi.goods.controller.GoodsOpenApiController`
  `Missing java source for com.dst.app.bff.common.domain.acl.app.goods.productList.GoodsListItemVO`
- `com.dst.app.bff.modules.openapi.mini.program.WechatOpenApiController`
  `Missing java source for com.dst.app.bff.common.domain.acl.mini.program.wechat.PhoneInfo`

### `message-center`

- `com.dst.message.core.modules.business.sms.smssignature.controller.MessageSmsSignatureController`
  `缺少类型源码: Void`
- `com.dst.message.core.modules.business.sms.smstemplate.controller.MessageSmsTemplateController`
  `缺少类型源码: DescribeTemplateListStatus`
- `com.dst.message.core.modules.business.sms.smstemplateBindinfo.controller.MessageSmsTemplateBindInfoController`
  `Unsupported mapping format`
- `com.dst.message.core.modules.business.uep.es.controller.EsManageController`
  `Missing java source for com.dst.message.core.infrastructure.es.entity.VinBhAnnualInspectionUser`

### `goods-activity`

- `com.dst.activity.center.modules.business.activity.controller.ActivityDepositController`
  `No supported controller methods found ...`
- `com.dst.activity.center.modules.business.equity.controller.CouponPackageController`
  `No supported controller methods found ...`
- `com.dst.goods.modules.business.activity.controller.ActivityAssociatedGoodsController`
  `缺少类型源码: ActivityAssociatedGoodsQuery`
- `com.dst.goods.modules.business.goodsmanage.controller.GoodsManageController`
  `缺少类型源码: GoodsSimpleMode`
- `com.dst.modules.outer.sku.SparePartsSkuOutController`
  `缺少类型源码: SparePartsSkuNcStatus`

### `user-center`

- `com.dst.modules.admin.controller.AdminController`
  `No supported controller methods found ...`
- `com.dst.modules.ping.controller.PingController`
  `缺少类型源码: Results`
- `com.dst.oa.modules.business.blacklist.controller.BlacklistController`
  `缺少类型源码: publicResponse`
- `com.dst.oa.modules.business.multi.controller.DstMultiIamUserController`
  `Missing java source for com.dst.oa.common.domain.iam.ResourceTreeVO`
- `com.dst.modules.business.messagecenter.acceptor.controller.MessageAcceptorController`
  `Unsupported method signature`

## 原始数据

- 运行期汇总文件：`/tmp/api-contract-sync-error-summary.json`
- 服务级进度文件：
  - `/tmp/api-contract-batch-dst-app-progress.json`
  - `/tmp/api-contract-batch-ocr-service-progress.json`
  - `/tmp/api-contract-batch-message-center-progress.json`
  - `/tmp/api-contract-batch-goods-activity-progress.json`
  - `/tmp/api-contract-batch-user-center-progress.json`

## 后续优化建议

1. 先补齐“类型源码缺失”处理策略：
   本地同仓搜索、外部源码依赖、白名单跳过策略要明确
2. 再补“Controller 方法映射”识别能力：
   当前大量旧式 Controller 没被识别，尤其在 `goods-activity` 和 `user-center`
3. 最后补“特殊签名/特殊返回包装”兼容：
   例如 `Void`、`Results`、`publicResponse`、特殊 message controller 签名
