# API Contract Skill 待优化清单

更新时间：2026-03-18

## 当前策略

当前这些问题先记录，不在本轮继续摊大。

优先级原则：
- 先分清“代码问题”还是“环境问题”
- 先处理会阻断真实回放的项
- 再处理会显著提升覆盖率的 parser / type-source 问题

## 当前最高优先级

### P0. GitLab API 真实回放被 HTTPS/TLS 握手阻塞

状态（2026-03-18）：
- Phase 6 已完成第一轮环境证据收集
- DNS、ICMP、TCP、HTTP 都可达，但 HTTPS/TLS 仍在 `ClientHello` 后被对端断开
- 当前机器的 SSH 通道可用，因此阻塞集中在 HTTPS/API 通道，不在 GitLab 账号、SSH 密钥或 contracts 仓库可达性
- 在 TLS 问题解除前，`gitlab_api` 真实回放、token 权限和分支策略验证都无法继续推进

当前现状：
- `GitLabApiContractStore` 已经实现
- 本地测试已覆盖并通过
- 但当前机器访问 `https://gitlab.dstcar.com/api/v4/...` 仍会在 TLS 握手早期失败

已确认的证据：
- `urllib`: `[SSL: UNEXPECTED_EOF_WHILE_READING]`
- `nscurl`: `A TLS error caused the secure connection to fail`
- `curl`: `SSL_ERROR_SYSCALL`
- `openssl s_client`: `SSL handshake has read 0 bytes and written 1555 bytes`
- `curl -v http://gitlab.dstcar.com/`: `302 Found` 且跳转到 `http://gitlab.dstcar.com/users/sign_in`

结论：
- 当前不是 token 权限问题
- 不是 contracts 模型问题
- 不是 API store 代码逻辑首先出错
- 是当前机器访问到的 GitLab HTTPS 入口 / 网关链路存在问题
- 当前已确认不是 DNS 不通，也不是 TCP `443` 不通

## 当前高优先级功能优化

### P1. capabilityTerms 质量仍需要继续优化

重点方向：
- 过滤噪声词
- 压制泛动作词
- 提升业务实体词、领域词权重
- 改善大服务第一跳 service 路由质量

说明：
- 当前仓库事实仍是 `indexes/global.index.json`
- 这项优化影响的是 service 路由精度，不改变真源模型

补充样本证据（2026-03-18，`dst-user-core-service` 随机抽样 10 个 controller）：
- 当前 `global.index.json` 的 `capabilityTerms` 中已出现明显噪声词，例如：`0602`、`0603`、`处理`、`建用`
- 数字编号、泛动作词、异常切词结果已经进入索引词表，会直接拉低 service 路由质量
- 后续需要把“编号词 / 模板词 / 错切词”明确纳入去噪规则，而不是只做权重微调

### P1.1 Doc 摘要与描述文案质量需要专项优化

状态（2026-03-18）：
- Phase 1 已完成第一轮收口
- 已消除 `处理X并返回结果` 这一类默认模板文案
- 已为无注释场景补充更自然的中文 fallback 短语
- 后续若还出现新的低质量业务词源，再放到后续 phase 单独补样本

本轮抽样暴露的问题：
- 方法标题和描述大量退化为模板文案，例如：
  - `处理Checkinfo`
  - `处理Addorg并返回结果`
  - `处理Getemployeeinfo并返回结果`
- 当前 fallback 文案可读性差，且会污染 `Doc` 阅读质量与索引信号
- 需要优先改进 summary / description 生成策略，避免在缺少高质量注释时直接输出这类模板句

优化方向：
- 优先使用更稳定的 Javadoc 首行、中文注释、注解语义
- 当只能回退到方法名时，输出规范化动作短语，不再输出“处理X并返回结果”
- 英文驼峰拆词后的大小写、词形和中文化策略需要单独收口

### P1.2 字段说明缺失率高，`无` 占位过多

状态（2026-03-18）：
- Phase 4 已完成第一轮收口
- 字段说明现已支持从 `@Schema(description=...)`、`@ApiModelProperty(...)` 之类注解中提取语义
- 对既无注释、也无注解、也无内置字段兜底的场景，当前会明确标为“未提供说明”
- 后续仍可继续补更多业务注解、枚举说明和通用字段词典

本轮抽样暴露的问题：
- DTO 字段说明中大量出现 `无`
- 当前生成结果在“可读但信息密度不足”和“结构完整但语义缺失”之间偏向后者
- 这会影响人审阅接口文档时对字段业务语义的理解效率

优化方向：
- 优先提取字段注释、Javadoc、注解中的语义信息
- 对常见通用字段建立更稳的说明兜底策略
- 区分“确实无说明”和“解析失败”，不要统一渲染成 `无`

### P1.3 嵌套类型展开深度仍有不足

状态（2026-03-18）：
- Phase 4 已完成第一轮收口
- 类型展开已能顺着字段类型继续递归下钻，不再只停留在第一层 DTO
- 当前已补充循环去重和类型变量跳过，避免简单递归结构把展开链路打爆
- 更复杂的跨模块深层类型与外部源码缺失场景，仍留给后续阶段继续收口

本轮抽样暴露的问题：
- 部分响应类型虽然已识别到泛型外层，但内部引用类型仍未完全展开，例如 `LeaderInfo`
- 当前文档能看到主 DTO，但复杂返回结构仍可能停留在半展开状态

优化方向：
- 提升嵌套对象、集合泛型、分页泛型内部类型的递归展开能力
- 对“已识别到字段但未继续展开”的场景补足递归读取与去重策略

### P1.4 部分响应类型仍退化为 `Object`

状态（2026-03-18）：
- Phase 3 已完成第一轮收口
- raw `Response`、`Response<?>`、`Response<Object>` 已开始区分“未显式声明 / wildcard / 通用对象”语义
- 当前仍未进入方法体级返回值推断，因此 `Object` 只做最小诚实表达，不做过度猜测

本轮抽样暴露的问题：
- 多个样本文档中的响应 `dataType` 仍显示为 `Object`
- 需要区分这是“真实就是通用对象返回”，还是“泛型/源码/类型回溯未解析完全”导致的退化

优化方向：
- 排查返回类型在 provider parser、类型回溯、response schema 构建链路中的丢失点
- 尽量把 `Object` 退化收敛到“确实无法解析”的少数场景

### P1.5 错误信息栏位空值率偏高，需判断是事实为空还是提取不足

状态（2026-03-18）：
- Phase 4 已完成第一轮收口
- 当前已支持从 controller 方法体里提取最小可用的 `BusinessException` 信息
- 对 `throw new BusinessException("...")` 会记录文本语义；对 `throw new BusinessException(RespCode.xxx)` 会记录枚举码
- 当前仍未扩展到 service-hop 异常链、枚举码反查和统一错误模型映射

本轮抽样现象：
- 10 个样本文档的错误信息区域均为 `无`

后续需要确认：
- 是源码本身没有可提取的业务错误定义
- 还是当前 parser / doc 渲染链路没有覆盖异常、错误码、校验失败语义

如果属于提取不足：
- 需要补充异常声明、统一返回码、校验约束失败语义的抽取策略

### P1.6 老式 query object 参数的请求展示不一致

状态（2026-03-18）：
- Phase 2 已完成第一轮收口
- `### 请求` 现已支持单独展示 legacy query object 输入，不再直接退化为“无请求参数”
- `Request Types` 与 `queryObjects` 区块已能同时表达 DTO 结构和“按 query object 参与请求”的请求语义
- 后续仍可继续补更多 callback/兼容接口样本

本轮排查结论：
- 当前 parser 能识别一部分“未标注 `@RequestBody`、但签名参数本身是对象”的老式 query object
- 例如：
  - `RoleController#roleExport(RoleQuery query)`
  - `RoleController#exportRoleTask(RoleQuery query)`
  - `SynPermissionController#push(PermissionDTO permissionDTO)`
  - `SynRoleController#pushRole(RoleDTO roleDTO)`
- 这些方法的 `Request Types` 往往已经能识别出 DTO，但 `### 请求` 区块不会把这类对象参数展开成 query/body 结构，导致展示不一致

影响：
- 文档阅读者会看到“DTO 已存在”，但请求参数区域仍像“没有这组对象参数”
- 对老项目、兼容性接口、补偿类接口的请求理解不够直观

优化方向：
- 为未标注 `@RequestBody` 的对象参数补一类明确的请求展示模型
- 至少要在文档中说明“该对象按 query object 参与请求”
- 进一步可按字段拆为 query 参数表，或增加单独的 `queryObject` 展示区块

### P1.7 动态 body 与基础设施参数的识别/展示仍需收口

状态（2026-03-18）：
- Phase 2 已完成第一轮收口
- `Map<String,Object>` / `JSONObject` 一类动态 body 已增加“动态对象，非固定 schema”语义说明
- `HttpServletRequest`、`HttpServletResponse` 已从 query object 候选中排除
- 当前仍未扩展到更复杂的动态 schema 推断，只完成最小可读性表达

本轮排查现象：
- `@RequestBody Map<String, Object>` 这类动态请求体当前会显示 `Request Types = 无`
- 例如：`BackendController#updateUserAuth(@RequestBody Map<String, Object> param)`
- `HttpServletRequest` 这类基础设施参数当前仍可能被 parser 暂时识别为 query object 候选，虽然暂未造成文档错误，但内部识别不够干净

影响：
- 动态 JSON body 的可读性不足，读文档时无法快速判断“这是自由结构对象”还是“漏解析”
- 基础设施参数若不尽早排除，后续扩展请求参数抽取时容易污染结果

优化方向：
- 对 `Map<String,Object>`、`JSONObject`、原始动态 JSON 请求体增加专门的展示语义
- 不强行伪造字段，但需要明确标记“动态对象 / 非固定 schema”
- 在参数识别阶段排除 `HttpServletRequest`、`HttpServletResponse` 等基础设施类型，避免进入 query object 候选集

### P1.8 原始 `Response` / `Response<?>` 过多，导致响应语义被压扁

状态（2026-03-18）：
- Phase 3 已完成第一轮收口
- `response.description` 已不再把 raw/wildcard/object-like 返回统一压成普通 `Object`
- 当前实现会明确表达“响应体未显式声明，按通用对象处理”或“通用对象返回结果”
- 若后续要继续提升语义准确度，需要额外引入方法体 / 调用链层面的推断

本轮全量扫描现象（`dst-user-core-service`）：
- 原始 `Response` 返回方法约 `109` 个
- `Response<?>` 返回方法约 `45` 个
- `Response<Object>` 返回方法约 `4` 个

代表性样本：
- `PositionRoleConfController#add`
- `PositionRoleController#addPositionRole`
- `FoundationAdminController#modifyAdminInformation`
- `RoleController#roleExport`
- `UserJobController#importOrgType`

当前影响：
- 当前解析规则会把原始 `Response` 统一压成 `envelopeType=Response` + `dataType=Object`
- `Response<?>` 也会被统一归一成 `Object`
- 对“无返回体但成功/失败有语义”“真实返回是导出结果/回调结果/包装对象”的接口，文档会显得过于粗糙
- 这会放大 `dataType=Object` 的占比，削弱文档与检索的可判读性

优化方向：
- 区分原始 `Response`、`Response<?>`、`Response<Object>`、`Response<Void>`、`Response.succeed()` 等不同语义
- 尽量结合方法体返回表达式、service 调用返回值或约定模式做更细粒度推断
- 对确实无法推断的场景，至少要在文档上明确标记“泛型未显式声明”，避免误导成真实 `Object`

### P1.9 fallback 摘要/响应描述/索引词生成过于依赖粗粒度 token

状态（2026-03-18）：
- Phase 1 已完成第一轮收口
- 已补充 token 翻译与常见复合词归一化，减少 `capitalize` 直出
- 已对 aliases/tags/path tokens 增加低价值词过滤，纯数字 token 不再直接进入 `capabilityTerms`
- 现阶段仍未解决所有异常切词，只完成了编号词、模板词和典型低质量 token 的第一轮压制

本轮排查结论：
- 当前 `_extract_summary`、`_description_for`、`_response_description`、`_infer_target_label` 主要依赖方法名、路径 token、类型名来拼 fallback 文案
- `_translate_token()` 的映射表很小，未命中的 token 会直接 `capitalize`
- 数字编号、英文驼峰拆词、路径 token、缩写词容易直接进入摘要和索引

当前已见表现：
- 文档里出现 `处理Push并返回结果`、`处理DynamicsqlSelect并返回结果` 之类的模板描述
- 索引 `capabilityTerms` 中出现 `0602`、`0603`、`处理`、`建用` 等噪声词
- 老接口上带编号注释时，数字编号会直接影响文档标题和 service 路由词表

优化方向：
- 对数字编号、模板动词、异常切词结果做统一去噪
- 扩大 token 翻译/归一化能力，降低 `capitalize` 直出英文片段的比例
- 把“文档 fallback 文案生成”和“索引词生成”拆开治理，避免两者共享低质量词源

### P1.10 文件上传接口的请求语义展示不准确

状态（2026-03-18）：
- Phase 2 已完成第一轮收口
- `MultipartFile`、`MultipartFile[]`、`MultipartFile...` 已不再按普通 `queryParams` 展示
- 文档中已改为单独 `fileParts` 区块表达上传字段，普通标量伴随参数会继续保留在 `queryParams`
- 若后续需要补 `contentType` / `multipart/form-data` 级别提示，可在后续阶段继续增强

本轮排查样本：
- `AliOcrOpenApiController#businessLicense(@RequestParam(\"file\") MultipartFile file)`
- `UserJobController#importOrgType(@RequestParam(\"file\") MultipartFile file, @RequestParam(\"departmentId\") String departmentId)`
- `UserJobController#importInit(@RequestParam(\"file\") MultipartFile file)`
- `UserJobController#importHuaZhong(@RequestParam(\"file\") MultipartFile file)`

当前现象：
- 文档里会把 `MultipartFile file` 渲染到 `queryParams`
- 例如上传接口当前展示为：
  - `file | MultipartFile | 是 | 无`
  - 但区块标题仍是 `queryParams`

影响：
- 上传接口的真实请求语义更接近 `multipart/form-data`
- 当前展示方式容易让读者误以为 `file` 是普通查询参数，而不是文件 part/form-data 字段

优化方向：
- 为 `MultipartFile`、`MultipartFile[]`、`MultipartFile...` 增加专门的上传参数展示语义
- 即使源码使用的是 `@RequestParam(\"file\") MultipartFile`，文档层也应优先表达为文件上传字段，而不是普通 query 参数
- 有需要时补充 `contentType` / `multipart` 提示

### P1.11 `PageDTO` 等包装型响应的外层结构信息丢失

状态（2026-03-18）：
- Phase 3 已完成第一轮收口
- `PageDTO`、`Page`、`IPage` 一类包装型响应已开始保留外层 schema
- 内部元素类型仍会继续展开，不再只剩元素 DTO 而丢失分页包装层
- 当前仍以本地源码可解析的包装类型为主，外部 jar 中更复杂的分页包装仍可继续补样本

本轮排查样本：
- `SynPermissionController#page` -> `Response<PageDTO<PositionRoleNew>>`
- `PositionRoleConfController#page` -> `Response<PageDTO<PositionRoleConf>>`
- `SignRouterController#page` -> `Response<PageDTO<SignRouterConfigVo>>`
- `SynUserController#querySynUserList` -> `Response<PageDTO<SynUser>>`

当前现象：
- `dataType` 会正确显示 `PageDTO<...>`
- 但 `Response Types` 里只展开了内部实体类型，例如 `PositionRoleNew`
- `PageDTO` 本身的分页字段，如页码、页大小、总数、列表容器等，没有进入文档结构

影响：
- 调用方无法从 `Response Types` 直接看出分页响应的完整结构
- 文档对“列表项对象”是清楚的，但对“分页包装协议”表达不完整

优化方向：
- 为 `PageDTO<T>`、`Page<T>` 等包装类型保留外层 schema
- 同时继续展开内部元素类型，避免只保留包装层或只保留内部层
- 明确展示分页元信息字段与数据列表字段

### P1.12 `Tree<T>` 等结构化泛型响应仍被当作标量展示

状态（2026-03-18）：
- Phase 3 已完成第一轮收口
- `Tree<T>` 已不再只作为纯字符串 `dataType` 留在文档里
- `Response Types` 现在可以展示树节点结构及 `children` 字段
- 递归树的更深层裁剪策略后续仍可继续优化

本轮排查样本：
- `PermissionController#parentRolePermissionSelect` -> `Response<List<Tree<Integer>>>`
- `OrgController#orgServerTree` -> `Response<List<Tree<String>>>`
- `PartnerEnterpriseController#queryEnterprisePermissionSelect` -> `Response<List<Tree<Integer>>>`
- `UserJobController#rolePermission` -> `Response<List<Tree<Integer>>>`

当前现象：
- `dataType` 会显示 `List<Tree<Integer>>`
- 但 `Response Types` 区块通常直接显示为“标量类型”，不会进一步展开 `Tree` 的结构

影响：
- 树形响应的节点字段、children 结构、value/label 等层级信息缺失
- 对前端或调用方理解返回结构帮助有限

优化方向：
- 对 `Tree<T>`、通用树节点、递归节点类型做结构化展开
- 对递归 children 字段增加去重与递归截断策略，避免无限展开
- 在文档中保留“树节点结构 + 泛型值类型”的双重表达

### P1.13 继承型 DTO / VO 的空壳类型展示过多

状态（2026-03-18）：
- Phase 3 已完成第一轮收口
- 对“无自有字段、仅继承父类”的响应类型，当前会增加最小继承说明，不再只显示“无字段”
- 当前策略是显式标注“继承自 X”，后续若需要再评估是否改成更强的父子合并展示

本轮排查结论：
- 当前类型解析会把“子类本身没有字段、字段都在父类里”的类型也单独保留下来
- 典型样本：
  - `PermissionNewQuery extends PageQuery`，子类本身无字段
  - `SignRouterConfigQuery extends PageQuery`，子类本身无字段
  - `UnifyLogEnterprise extends UnifyLog`，子类本身无字段
  - `SignRouterConfigVo extends SignRouterConfig`，子类本身无字段
- 文档中会出现：
  - `PageQuery - 无字段`
  - `PermissionNewQuery - 无字段`
  - 或父类字段已展开，但子类空壳仍继续展示

影响：
- 读者会误以为该 DTO/VO 本身就是一个“没有任何字段的请求/响应对象”
- 对继承层级较多的分页对象、VO 包装对象，会产生重复且低价值的展示噪声
- 真正的结构信息在父类里，但文档重点却被“空壳类”分散了

优化方向：
- 对仅继承父类、无自有字段的类型做特殊处理
- 可选方案：
  - 合并展示为“子类名（继承父类字段）”
  - 或直接隐藏空壳子类，只展示父类字段来源
  - 或在空壳类下明确标记“无自有字段，继承自 X”
- 对 `PageQuery` 这类通用父类尤其要避免重复出现多个“无字段”条目

### P1.14 必填与校验约束语义仍有明显缺口

状态（2026-03-18）：
- Phase 2 已完成第一轮收口
- `@RequestBody(required=false)` 与 `@RequestParam(defaultValue=...)` 的必填语义已保留
- 方法参数级 `@NotBlank`、`@NotNull`、`@Size`、`@Length`、`@Pattern`、`@Min`、`@Max`、`@Valid`、`@Validated` 已开始进入请求参数说明
- 当前仍未建立完整的结构化“约束列”和分组校验模型，这部分仍有后续收口空间

本轮排查结论：
- 当前字段级 `required` 只认 `@NotNull`、`@NotBlank`、`@NotEmpty`
- 其他常见校验注解如 `@Size`、`@Length`、`@Pattern`、`@Min`、`@Max` 虽可能进入原始约束字符串，但不会被结构化表达
- 方法参数级校验语义丢失更明显：
  - `@RequestParam("corpName") @NotBlank String corpName`
  - `@RequestParam MultipartFile file`
  - `@Valid @RequestBody XxxParam`
  - `@Validated(AddGroup.class) @RequestBody XxxParam`
  这些校验不会完整反映到请求参数“必填/约束”展示

当前实现限制：
- `@RequestParam` 是否必填只看 `required=false`，不会结合 `@NotBlank/@NotNull`
- `@RequestBody` 只要存在就直接记为必填，不区分 `required=false`
- 请求参数表当前没有单独的“约束”列，因此方法参数上的校验注解会整体丢失
- `@Validated` / `@Valid` / 分组校验语义没有进入 spec/doc

样本证据：
- `CompensateController#externalUserCompensate(@RequestParam(\"corpName\") @NotBlank String corpName)`
- `UserLoginOpenApiBaseController#smsLogin(@RequestBody @Validated LoginSmsParam loginSmsParam, HttpServletRequest request)`
- `SignRouterController#add(@Validated(AddGroup.class) @RequestBody SignRouterConfigParam param)`
- 多个 DTO 字段上存在 `@Length`、`@Size`、`@Pattern`、`@Min`、`@Max` 等约束，但文档层没有结构化体现

影响：
- 文档中的“必填”并不等于真实校验规则
- 调用方只能看到一部分字段必填语义，很多长度/格式/范围约束看不到或只能看到原始注解碎片
- 校验分组场景会被完全抹平

优化方向：
- 区分“框架参数是否要求存在”和“业务校验是否要求非空/符合约束”
- 为请求参数区块增加结构化约束展示，不只停留在 DTO 字段表
- 支持 `@RequestBody(required=false)`、`@RequestParam(required=false)`、`defaultValue` 等语义
- 对 `@Validated` / `@Valid` / 分组校验增加最小可用表达，至少不要完全丢失

### P1.15 注释提取对编号型标题与辅助信息的去噪不足

状态（2026-03-18）：
- Phase 1 已完成第一轮收口
- `_comment_lines()` 已支持清洗编号前缀，并跳过 `YApi` / URL / 元信息类注释行
- 已新增 `RoleController`、`UserLoginOpenApiBaseController`、`FddCallBackController` 相关回归测试
- 若后续发现新的编号格式或平台辅助注释模式，再继续补充规则

本轮排查结论：
- 当前 `_extract_summary()` 直接取注释清洗后的第一行作为摘要
- `_comment_lines()` 只会过滤空行、HTML、`@param/@return` 等标签行，但不会处理编号前缀、YApi 链接上下文、注释中的辅助编号体系

当前已见表现：
- 大量摘要直接以编号开头：
  - `0000发送登录/注册短信`
  - `0501 查询当前用户的角色下拉列表`
  - `9901法大大人脸异步回调`
  - `1001导入用户权限信息`
- 同一编号会在多个方法里重复出现，导致方法摘要区分度不足
- 当注释首行质量差时，仍会直接进入文档和索引，而不是做进一步清洗

相关样本：
- `UserLoginOpenApiBaseController`
- `RoleController`
- `FddCallBackController`
- `UserJobController`

影响：
- 文档目录和方法摘要会被历史编号体系污染
- 索引词、能力词和 fallback 文案也更容易继承这些低价值编号信息
- 对真正的人类可读摘要提炼帮助有限

优化方向：
- 在注释提取阶段识别并清洗纯编号前缀、章节号、历史接口编号
- 区分“业务标题正文”和“辅助编号/外链/平台说明”
- YApi 链接、平台编号等信息可保留为扩展元数据，但不应默认进入摘要首行
- 对“编号 + 标题”的注释格式增加专门归一化规则

### P2. `Unsupported method signature` 仍需继续收口

状态（2026-03-18）：
- Phase 5 已完成第一轮收口
- 当前已支持 package-private controller 方法签名，不再直接落到 `Unsupported method signature`
- 这轮只补了最小签名兼容面，更多复杂修饰符组合和非常规声明仍可继续补样本

重点方向：
- 更复杂的修饰符组合
- 更多非标准 Spring 方法声明
- 真实批量样本里的边角签名

### P3. `No supported controller methods found` 仍有剩余模式

状态（2026-03-18）：
- Phase 5 已完成第一轮收口
- fully-qualified Spring mapping 注解已进入 controller 方法发现链路
- 当前仍未穷尽所有历史 Controller 布局和更复杂的注解变体，后续可继续补真实样本

当前仍需继续确认：
- 更老的非接口型 Controller 写法
- 更复杂的注解组合
- framework/common 包中的契约来源识别

### P4. `缺少类型源码 / Missing java source` 仍要继续收口

状态（2026-03-18）：
- Phase 5 已完成第一轮收口
- 本地 `record` 类型已能进入类型源码定位与 schema 解析链路
- 当前仍需继续扩展到更复杂的跨模块、本地源码 / source jar / binary jar 混合场景

重点方向：
- `goods / outer / innerapi` 分层项目中的跨模块类型回溯
- 多模块仓库里的同名类型语义判定
- 本地源码、source jar、binary jar 三层回溯优先级

## 中优先级事项

### P5. 真实 provider 仓库回放还需要继续做

状态（2026-03-18）：
- Phase 6 已完成第一轮环境证据收集
- 当前机器到 GitLab 的 SSH 通道可用，`git ls-remote git@gitlab.dstcar.com:dmp/ai-coding/dst-api-skills-repo.git` 可正常返回远端分支
- 代表性 provider 仓库 `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 当前不在本机固定路径内，本轮未继续做 bounded replay
- 下一步需要先准备这些 provider 仓库的本地副本或明确可访问的远端路径，再继续 SSH 回放

建议样本：
- `dst-user-core-service`
- `dst-goods-server`
- `dst-account-server`

### P6. token/API 权限边界和分支策略需要真实验证

状态（2026-03-18）：
- Phase 6 已完成第一轮环境证据收集
- 当前 `gitlab_api` 配置面仍可正常构造 `GitLabApiContractStore`
- 但 HTTPS/TLS 在 `ClientHello` 后即被对端断开，因此 token 权限、`API_CONTRACT_GITLAB_START_BRANCH` 行为、失败回滚提示都还无法在真实 API 通道上验证
- 在 HTTPS 恢复前，相关验证只能停留在本地单测层，不能误记为真实环境已验证

后续需要确认：
- token 至少需要哪些 GitLab 权限
- `API_CONTRACT_GITLAB_BRANCH` 不存在时是否统一依赖 `API_CONTRACT_GITLAB_START_BRANCH`
- API mode 提交失败时的回滚和报错体验

## 已经完成、不要再当成待办的事项

以下内容已经完成，不应再作为“未做”继续记录：

1. `GitLabApiContractStore` 已实现
2. `build_contract_store()` 已支持 `API_CONTRACT_SOURCE=gitlab_api`
3. 当前本地测试总数为 `30` 条
4. 当前本地测试全绿
5. 默认 Git SSH 路径仍可真实写远端
6. 已完成 HTTPS 链路基础排查，问题已收敛到服务端 TLS 握手早期断开

## 需要明确纠正的过期认知

### 1. 当前不是 split global

当前真实结构仍是：
- `indexes/global.index.json`

### 2. API mode 不是“已经真实跑通”

当前真实情况是：
- 代码实现完成
- 本地测试完成
- 真实 HTTPS API 回放未完成

### 3. 当前远端 `main` 已经被清空

为便于后续重新测试，`dmp/ai-coding/dst-api-skills-repo` 的 `main` 当前是空树状态。

### 4. 当前机器的 SSH 通道是通的，但 HTTPS API 仍不通

当前真实情况是：
- `ssh -T git@gitlab.dstcar.com` 返回 `Welcome to GitLab, @luohao!`
- `git ls-remote git@gitlab.dstcar.com:dmp/ai-coding/dst-api-skills-repo.git` 可正常读取 `main` / `test`
- `curl -vk https://gitlab.dstcar.com/api/v4/version` 仍在 `ClientHello` 后以 `SSL_ERROR_SYSCALL` 失败
- `openssl s_client` 仍显示 `SSL handshake has read 0 bytes and written 1555 bytes`

## 建议的下一步顺序

1. 先协调网络/网关侧排 TLS/HTTPS API 问题
2. 并行准备 `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 的本地副本或明确可访问路径
3. 如果 HTTPS 仍未恢复，继续优先走 SSH 做 bounded replay
4. HTTPS 恢复后，再验证 token 权限、目标分支缺失和 rollback 提示
