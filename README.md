# API Contract Client Workflow

面向公司内部 Java/OpenFeign 场景的 API contracts skill。

它解决两件事：
- provider 从 Spring Controller/DTO 源码生成标准 contracts 真源
- consumer 通过检索 contracts 真源生成本地 Feign 调用代码

## 当前结构

```text
api-contract-client-workflow/
├── SKILL.md
├── references/
├── scripts/
├── templates/
└── examples/
```

## 核心模型

- 真源对象：
  - `SERVICE.yaml`
  - `Controller.spec.yaml`
- 派生对象：
  - `Controller.doc.md`
  - `indexes/`

contracts 仓库结构固定为：

```text
repo-root/
  services/
    <service>/
      SERVICE.yaml
      controllers/
        <Controller>/
          <Controller>.spec.yaml
          <Controller>.doc.md
  indexes/
    global.index.json
    services/
      <service>/
        manifest.json
        operations.jsonl
        inverted/
          <bucket>.json
```

## 检索与生成

- 检索链路：
  - `global.index.json -> service shard -> spec`
- 生成链路：
  - `SERVICE.yaml + Spec + consumer 本地规则 -> Java/OpenFeign`
- 不支持 Node/PHP
- 不支持 local fallback

## 规则文件

- [contract-model.md](/Users/luohao/.codex/skills/api-contract-client-workflow/references/contract-model.md)
- [provider-mode.md](/Users/luohao/.codex/skills/api-contract-client-workflow/references/provider-mode.md)
- [consumer-mode.md](/Users/luohao/.codex/skills/api-contract-client-workflow/references/consumer-mode.md)
- [operation-id.md](/Users/luohao/.codex/skills/api-contract-client-workflow/references/operation-id.md)
- [java-feign-defaults.md](/Users/luohao/.codex/skills/api-contract-client-workflow/references/java-feign-defaults.md)
- [doc-model.md](/Users/luohao/.codex/skills/api-contract-client-workflow/references/doc-model.md)

## 主要命令

```bash
python3 scripts/api_contract_cli.py provider sync ...
python3 scripts/api_contract_cli.py provider delete-controller ...
python3 scripts/api_contract_cli.py consumer search ...
python3 scripts/api_contract_cli.py consumer generate ...
python3 scripts/api_contract_cli.py contracts rebuild-index
```

## 运行方式

- 默认仍通过 Git over SSH 访问
- 也支持通过 GitLab API + token 访问远端 contracts 仓库
- consumer 本地规则在 consumer 仓库根目录读取
- 本地规则优先级：
  - 本地 YAML
  - 本地结构推断
  - 公司默认规则

### Source 选择

默认 source 仍是 `github`，对应现有 Git/SSH 路径。

如果需要走 GitLab API：

```bash
export API_CONTRACT_SOURCE=gitlab_api
export API_CONTRACT_GITLAB_TOKEN=<token>
```

可选覆盖项：

```bash
export API_CONTRACT_GITLAB_BASE_URL=https://gitlab.dstcar.com/api/v4
export API_CONTRACT_GITLAB_PROJECT=dmp/ai-coding/dst-api-skills-repo
export API_CONTRACT_GITLAB_BRANCH=main
export API_CONTRACT_GITLAB_START_BRANCH=main
```

说明：

- `API_CONTRACT_GITLAB_TOKEN` 是 API 模式必填项
- `API_CONTRACT_GITLAB_BRANCH` 未设置时，回退到 `API_CONTRACT_GITHUB_BRANCH`
- 当目标分支不存在时，可通过 `API_CONTRACT_GITLAB_START_BRANCH` 基于已有分支创建首次提交
- 默认 contracts 结构仍是 `indexes/global.index.json`，本次没有切到 split global

## 当前状态

### 已完成

- `provider` parser 多轮兼容性修复已落地
- `GitLabApiContractStore` 已实现
- `build_contract_store()` 已支持 `API_CONTRACT_SOURCE=gitlab_api`
- 默认 Git SSH 模式已完成最小真实回放
- 当前测试总数为 `30`，文档记录为全量通过

### 待优化 / 待验证

- `gitlab_api` 模式真实远端回放仍未完成
- 当前机器访问 `https://gitlab.dstcar.com/api/v4/...` 时，TLS 握手在 `ClientHello` 后被对端中断
- `capabilityTerms` 路由质量仍需优化
- 真实 provider 样本回放仍需继续扩大
- 跨模块类型源码回溯仍有收口空间

### 当前已确认的 HTTPS 现象

- DNS 可解析到 `198.18.0.13`
- TCP `443` 可连接
- `curl -vk` 与 `openssl s_client` 都显示客户端发出 `ClientHello` 后未收到任何服务端 TLS 数据
- `http://gitlab.dstcar.com/` 可返回 `302 Found`，但跳转目标仍是 `http://gitlab.dstcar.com/users/sign_in`

结论：

- 当前阻塞更像 GitLab HTTPS 入口、反向代理或网关层问题，不是本仓库 Python 代码、token 或 API 路径问题
- 在 HTTPS 恢复前，真实联调建议继续优先使用 SSH 路径

## 验证

```bash
python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py
python3 -m unittest discover -s tests -v
```
