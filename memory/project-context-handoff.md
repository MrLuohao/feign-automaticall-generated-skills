# API Contract Client Workflow Handoff

更新时间：2026-03-19

## 当前阶段

- 已连续完成多轮 `provider` parser 兼容性修复
- 已新增 GitLab API contract store，可通过 token/API 写远端 contracts
- Phase 1 已完成第一轮文档文案与 `capabilityTerms` 去噪收口
- Phase 2 已完成第一轮请求结构语义收口
- Phase 3 已完成第一轮响应结构语义收口
- Phase 4 已完成第一轮语义准确性收口
- Phase 5 已完成第一轮 parser 兼容性与类型源码回溯收口
- Phase 6 已完成第一轮环境证据收集，但真实 API/SSH 回放仍未完全闭环
- 当前本地测试总数为 `45`，全部通过
- `provider.py` 的方法发现、接口继承链解析、参数注解提取、数组/varargs 类型处理已明显增强
- 已完成：
  - token/API 写远端替代 Git SSH
  - Phase 1：编号型注释清洗、fallback 文案改写、低价值 capability terms 过滤
  - Phase 2：legacy query object、multipart/file input、dynamic body 与最小校验语义展示
  - Phase 3：response wrapper、分页包装、树结构与继承空壳响应展示
  - Phase 4：字段注解说明、嵌套类型递归、`BusinessException` 错误提取
  - Phase 5：package-private 签名、fully-qualified mapping discovery、本地 `record` 类型源码解析
  - Phase 6：TLS 诊断复跑、SSH 通道确认、环境证据归档
- 已验证：
  - 默认 Git SSH 模式可真实写回远端 contracts
- 当前外部阻塞：
  - 当前机器到 `gitlab.dstcar.com` HTTPS API 的 TLS 握手在 `ClientHello` 后被对端中断，导致 `gitlab_api` 模式尚未完成真实回放
- 当前远端状态：
  - `dmp/ai-coding/dst-api-skills-repo` 的 `main` 已清空，适合重新做联调测试
- 当前 provider 样本状态：
  - `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 本地副本均已定位，且工作区干净，可直接进入 SSH bounded replay 准备
  - `dst-app-service` 与 `dst-app-bff-service` 已于 2026-03-19 在远端 contracts 仓库 `test` 分支完成一轮全量 controller sync，结果为 `40` 成功 / `0` 失败
- 当前优化规划状态：
  - 已完成待优化问题排查与分阶段路线拆分
  - 已写完 Phase 1 ~ Phase 6 的设计/实施计划文档
  - 已完成 Phase 1
  - 已完成 Phase 2
  - 已完成 Phase 3
  - 已完成 Phase 4
  - 已完成 Phase 5
  - Phase 6 已部分完成

## 已完成的关键改动

### provider parser 兼容性

已补强并有回归测试覆盖：

- `implements XxxApi` 接口映射继承
- imported interface 优先解析
- 多接口 `implements A, B`
- `implements GenericApi<T>, OtherApi` 泛型接口列表解析
- 接口 `extends` 父接口链上的方法映射继承
- 接口链上的类级 `@RequestMapping` 路径继承
- 多层接口路径顺序修正与重复去重
- package-private 方法支持
- 接口方法 `;` 结尾支持
- `@RequestMapping(value={...}, method={RequestMethod.POST})` 旧式数组写法
- `@PatchMapping`
- fully-qualified Spring 注解支持
- 多注解叠加时仅提取目标 Spring 注解参数
- `@PathVariable/@RequestParam/@RequestHeader/@RequestPart` 的显式名字提取
- `required=false`、`defaultValue=...` 语义支持
- `final` 修饰符不再污染方法返回类型和参数类型
- `MultipartFile[]`、`MultipartFile...` 上传参数支持
- `String...` 等 varargs 参数归一化为数组
- `String[]` 等标量数组 body/response 归为 scalar，不再错误下钻源码

### 设计与计划文档

已做精简：

- 已删除已完成且只保留历史执行快照价值的旧计划文件
- 当前只保留仍有直接续接价值的活文档

### remote store 能力

已新增：

- `GitLabApiContractStore`
- `API_CONTRACT_SOURCE=gitlab_api`
- `API_CONTRACT_GITLAB_TOKEN`
- `API_CONTRACT_GITLAB_BASE_URL`
- `API_CONTRACT_GITLAB_PROJECT`
- `API_CONTRACT_GITLAB_BRANCH`
- `API_CONTRACT_GITLAB_START_BRANCH`

兼容性说明：

- 默认 `github` source 仍走原来的 Git SSH 路径
- API 模式只替换远端传输方式，不改变 contracts 模型和 CLI surface
- 全局索引仍是 `indexes/global.index.json`
- 当前机器的真实 HTTPS API 回放仍被 TLS 问题阻塞

## 当前验证状态

已通过：

- `python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py`
- `python3 -m unittest discover -s tests -v`

当前结果：

- `Ran 45 tests`
- `OK`

### 真实联调验证

已完成：

- 默认 `github` / Git SSH 模式下，一轮最小 `provider sync + rebuild-index` 真实回放成功
- `dst-app-service` 全量 `14` 个 controller 已真实同步到 `test` 分支，生成 `68` 个 operation
- `dst-app-bff-service` 全量 `26` 个 controller 已真实同步到 `test` 分支，生成 `85` 个 operation

未完成：

- `gitlab_api` 模式真实远端回放
- `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 这组代表性 provider 仓库的 SSH bounded replay

当前已确认的真实外部错误：

- `urllib`: `[SSL: UNEXPECTED_EOF_WHILE_READING]`
- `nscurl`: TLS secure connection failed
- `curl`: `SSL_ERROR_SYSCALL`
- `openssl s_client`: 服务端未返回任何 TLS 数据，`SSL handshake has read 0 bytes and written 1555 bytes`
- `curl -v http://gitlab.dstcar.com/`: `302 Found`，但跳转目标仍是 `http://gitlab.dstcar.com/users/sign_in`

当前链路判断：

- DNS 可解析到 `198.18.0.13`
- ICMP 可达，TCP `443` 可连接
- 失败点在服务端 TLS 握手早期，不是本仓库 Python 代码、token 或 API 路径问题
- SSH 通道可用，不属于 GitLab 账号或 SSH 密钥阻塞
- 代表性 provider 仓库本地副本已存在，下一步不再是“找仓库”，而是“选 controller + 专用分支执行 bounded replay”
- `dst-app-service` / `dst-app-bff-service` 已验证当前 parser 与远端写回链路在真实仓库上可跑通，剩余工作集中在继续扩大样本覆盖

## 当前仍未落实的优化点

### P0

- 解决当前机器到 GitLab HTTPS API 的 TLS 握手问题
- 在 HTTPS API 可用后，继续完成 `gitlab_api` 模式真实回放验证
- 明确 token 权限边界、分支策略和失败回滚预期

### P1

- Phase 1 已完成：
  - 注释编号前缀、`YApi`/URL 元信息去噪
  - fallback summary / description / response description 改写
  - aliases / tags / path tokens 的纯数字与模板词过滤
- Phase 2 已完成：
  - legacy query object 独立请求区块展示
  - `MultipartFile` 从普通 `queryParams` 切换到 `fileParts`
  - 动态 body 的非固定 schema 描述
  - `defaultValue` / 常见方法参数校验注解说明保留
- Phase 3 已完成：
  - raw / wildcard / object-like `Response` 的最小差异化描述
  - `PageDTO` / `Page` / `IPage` 外层 schema 保留
  - `Tree<T>` 结构化响应展示
  - 继承空壳响应类型的“继承自 X”标注
- Phase 4 已完成：
  - 字段注解说明提取与“未提供说明”占位区分
  - 嵌套引用类型递归展开
  - controller 方法体里的最小 `BusinessException` 错误提取
- Phase 5 已完成：
  - package-private controller 方法签名支持
  - fully-qualified Spring mapping 注解发现
  - 本地 `record` 类型源码定位与 schema 解析
- 下一步：
  - 先协调 TLS/HTTPS API 问题，再继续补 `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 的 provider SSH bounded replay

### P2

- 做真实 provider 仓库回放
  - `dst-user-core-service`
  - `dst-goods-server`
  - `dst-account-server`
  - 当前阻塞：`dst-app-*` 已完成一轮回放，但 `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 这组代表性样本仍未开始

### P3

- 继续收口跨模块类型源码回溯
  - `goods / outer / innerapi`
  - 同名类型语义判定
  - source jar / binary jar / 本地源码优先级

## 活文档现状

当前建议优先维护的文档：

- `docs/API_CONTRACT_SKILL_待优化清单.md`
- `docs/API_CONTRACT_SKILL_链路说明.md`
- `docs/plans/2026-03-18-environment-and-real-replay-phase6.md`
- `memory/project-context-handoff.md`

说明：

- Phase 1 ~ Phase 5 的详细实施计划与更早的 store 设计/实施计划已删除
- 它们的有效结论已收敛进 README、待优化清单、Phase 6 和 handoff

Phase 6 当前范围：

- `P0` GitLab API TLS/HTTPS 阻塞
- `P5` 真实 provider 仓库回放
- `P6` token/API 权限边界与分支策略

执行规则：

- 每解决一个问题，必须同步更新：
  - `docs/API_CONTRACT_SKILL_待优化清单.md`
  - 当前活跃计划文档
  - 若范围变化，再更新 handoff

## 当前仓库事实与外部文档分叉

仓库当前仍是：

- `indexes/global.index.json`
- 默认 Git SSH 写远端
- 已支持 GitLab API 写远端
- 当前机器直接访问 GitLab HTTPS API 会在 `ClientHello` 后被对端提前断开
- 远端 `main` 当前已清空
- `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 本地副本均已存在且工作区干净
- `dst-app-service` 与 `dst-app-bff-service` 已在远端 `test` 分支完成全量 controller sync

外部文档目标已经写成：

- token/API 写远端

所以新会话继续时，不要把“目标状态”误当成“已落地事实”。

## 新窗口建议起手句

可以直接这样说：

```text
继续 API Contract Client Workflow。
先读取 memory/project-context-handoff.md。
当前 parser 兼容修复已完成，GitLab API contract store 也已落地，并且 45 条测试全绿。
Phase 1 到 Phase 5 已完成，Phase 6 已补充 TLS/SSH 环境证据，但真实 API/SSH 回放还未完全闭环。
下一步优先协调 TLS/HTTPS API 问题，并在 `dst-app-*` 已验证通过的基础上继续推进 `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 的 SSH bounded replay。
每解决一个问题，同步更新待优化清单、对应计划文档和 handoff。
```
