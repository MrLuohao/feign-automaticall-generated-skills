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

### P2. `Unsupported method signature` 仍需继续收口

重点方向：
- 更复杂的修饰符组合
- 更多非标准 Spring 方法声明
- 真实批量样本里的边角签名

### P3. `No supported controller methods found` 仍有剩余模式

当前仍需继续确认：
- 更老的非接口型 Controller 写法
- 更复杂的注解组合
- framework/common 包中的契约来源识别

### P4. `缺少类型源码 / Missing java source` 仍要继续收口

重点方向：
- `goods / outer / innerapi` 分层项目中的跨模块类型回溯
- 多模块仓库里的同名类型语义判定
- 本地源码、source jar、binary jar 三层回溯优先级

## 中优先级事项

### P5. 真实 provider 仓库回放还需要继续做

建议样本：
- `dst-goods-server`
- `dst-account-server`

### P6. token/API 权限边界和分支策略需要真实验证

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

## 建议的下一步顺序

1. 先决定是否排 TLS/HTTPS API 问题
2. 如果暂时不排 API 问题，先继续走 SSH 做业务链路回放
3. 用真实 provider 样本继续收集 parser / type-source 问题
4. 再回头提升 `capabilityTerms` 路由质量
