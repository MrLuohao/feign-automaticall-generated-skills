# API Contract Client Workflow Handoff

更新时间：2026-03-18

## 当前阶段

- 已连续完成多轮 `provider` parser 兼容性修复
- 已新增 GitLab API contract store，可通过 token/API 写远端 contracts
- 当前本地测试总数为 `30`，全部通过
- `provider.py` 的方法发现、接口继承链解析、参数注解提取、数组/varargs 类型处理已明显增强
- 已完成：
  - token/API 写远端替代 Git SSH
- 已验证：
  - 默认 Git SSH 模式可真实写回远端 contracts
- 当前外部阻塞：
  - 当前机器到 `gitlab.dstcar.com` HTTPS API 的 TLS 握手在 `ClientHello` 后被对端中断，导致 `gitlab_api` 模式尚未完成真实回放
- 当前远端状态：
  - `dmp/ai-coding/dst-api-skills-repo` 的 `main` 已清空，适合重新做联调测试
- 还未开始做：
  - capabilityTerms 质量优化
  - 真实 provider 仓库回放验证

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

已新增：

- `docs/plans/2026-03-17-gitlab-api-contract-store-design.md`
- `docs/plans/2026-03-17-gitlab-api-contract-store.md`

说明：

- 早先 handoff 中提到的 `controller-parsing-compat` 两份计划文件当前仓库中不存在，不应再继续当作现存文件引用

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

- `Ran 30 tests`
- `OK`

### 真实联调验证

已完成：

- 默认 `github` / Git SSH 模式下，一轮最小 `provider sync + rebuild-index` 真实回放成功

未完成：

- `gitlab_api` 模式真实远端回放

当前已确认的真实外部错误：

- `urllib`: `[SSL: UNEXPECTED_EOF_WHILE_READING]`
- `nscurl`: TLS secure connection failed
- `curl`: `SSL_ERROR_SYSCALL`
- `openssl s_client`: 服务端未返回任何 TLS 数据，`SSL handshake has read 0 bytes and written 1555 bytes`
- `curl -v http://gitlab.dstcar.com/`: `302 Found`，但跳转目标仍是 `http://gitlab.dstcar.com/users/sign_in`

当前链路判断：

- DNS 可解析到 `198.18.0.13`
- TCP `443` 可连接
- 失败点在服务端 TLS 握手早期，不是本仓库 Python 代码、token 或 API 路径问题

## 当前仍未落实的优化点

### P0

- 解决当前机器到 GitLab HTTPS API 的 TLS 握手问题
- 在 HTTPS API 可用后，继续完成 `gitlab_api` 模式真实回放验证
- 明确 token 权限边界、分支策略和失败回滚预期

### P1

- 优化 `capabilityTerms`
  - 增加噪声过滤
  - 提升业务实体词权重
  - 调整 service 路由词聚合策略

### P2

- 做真实 provider 仓库回放
  - `dst-goods-server`
  - `dst-account-server`

### P3

- 继续收口跨模块类型源码回溯
  - `goods / outer / innerapi`
  - 同名类型语义判定
  - source jar / binary jar / 本地源码优先级

## 当前仓库事实与外部文档分叉

仓库当前仍是：

- `indexes/global.index.json`
- 默认 Git SSH 写远端
- 已支持 GitLab API 写远端
- 当前机器直接访问 GitLab HTTPS API 会在 `ClientHello` 后被对端提前断开
- 远端 `main` 当前已清空

外部文档目标已经写成：

- token/API 写远端

所以新会话继续时，不要把“目标状态”误当成“已落地事实”。

## 新窗口建议起手句

可以直接这样说：

```text
继续 API Contract Client Workflow。
先读取 memory/project-context-handoff.md。
当前 parser 兼容修复已完成，GitLab API contract store 也已落地，并且 30 条测试全绿。
SSH 模式真实回放已成功，但当前机器访问 GitLab HTTPS API 仍卡在 TLS 握手。
远端 main 现在是空仓库，下一步先决定排 TLS 问题还是继续用 SSH 做真实样本回放。
```
