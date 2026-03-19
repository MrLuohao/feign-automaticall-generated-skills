# Environment And Real Replay Phase 6 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Resolve the remaining real-environment validation gaps around GitLab API TLS access, real provider replay, and token/branch strategy verification.

**Architecture:** Separate environment validation from code refactors. Treat TLS/API reachability, replay verification, and branch/token behavior as operational checks with explicit evidence capture.

**Tech Stack:** Python 3, git over SSH, GitLab API, curl/openssl/nscurl, existing CLI workflow

## Execution Status

更新时间：2026-03-19

- 状态：部分完成
- 已于 2026-03-19 复跑 TLS 诊断，结果与历史判断一致：DNS/ICMP/TCP 通，HTTPS/TLS 在 `ClientHello` 后被对端提前断开
- 本轮证据：
  - `nslookup gitlab.dstcar.com` -> `198.18.0.13`
  - `ping -c 1 gitlab.dstcar.com` -> 0% packet loss
  - `curl -vk https://gitlab.dstcar.com/api/v4/version` -> `SSL_ERROR_SYSCALL`
  - `openssl s_client -connect gitlab.dstcar.com:443 -servername gitlab.dstcar.com` -> `unexpected eof while reading`, `SSL handshake has read 0 bytes and written 1555 bytes`
  - `curl -v http://gitlab.dstcar.com/` -> `302 Found`, `Location: http://gitlab.dstcar.com/users/sign_in`
- 已确认 SSH 通道可用：
  - `ssh -T git@gitlab.dstcar.com` -> `Welcome to GitLab, @luohao!`
  - `git ls-remote git@gitlab.dstcar.com:dmp/ai-coding/dst-api-skills-repo.git` -> 可读取 `main` / `test`
- 已确认远端 contracts 仓库 `main` 仍是空树：
  - `git clone --depth 1 git@gitlab.dstcar.com:dmp/ai-coding/dst-api-skills-repo.git /tmp/dst-api-skills-repo-phase6-check`
  - clone 结果仅包含 `.git/*`，工作树无 contracts 文件
- 已完成一轮真实 SSH bounded replay：
  - 使用 `API_CONTRACT_GITHUB_BRANCH=test`
  - 已同步 `dst-app-service` 全量 `14` 个 controller，生成 `68` 个 operation
  - 已同步 `dst-app-bff-service` 全量 `26` 个 controller，生成 `85` 个 operation
  - 本轮结果：`40` 个 controller 全部同步成功，`0` 个失败
- 未完成项：
  - 代表性 provider 仓库 SSH bounded replay：`dst-app-service` 与 `dst-app-bff-service` 已在 `test` 分支完成一轮全量 controller 回放，但 `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 这组更高代表性的样本仍未执行
  - GitLab API token/branch/rollback 真实验证：仍被 HTTPS/TLS 阻塞
- 当前建议：
  - 优先由网络/网关侧排 TLS 问题
  - 在已有 `dst-app-*` 结果基础上，继续补 `dst-user-core-service`、`dst-goods-server`、`dst-account-server` 的 bounded replay

---

### Task 1: Reproduce and document the TLS/API failure precisely

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `memory/project-context-handoff.md`
- Modify: `docs/plans/2026-03-18-environment-and-real-replay-phase6.md`

**Step 1: Re-run the minimal HTTPS/TLS diagnostics**

Run:

- `curl -vk https://gitlab.dstcar.com/api/v4/version`
- `openssl s_client -connect gitlab.dstcar.com:443 -servername gitlab.dstcar.com`

**Step 2: Capture exact failure evidence**

Record:

- DNS result
- TCP reachability
- TLS handshake behavior
- whether failure still occurs on the same machine/network

**Step 3: Update docs with current evidence**

### Task 2: Validate SSH real replay on representative provider repos

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `memory/project-context-handoff.md`
- Modify: `docs/plans/2026-03-18-environment-and-real-replay-phase6.md`

**Step 1: Select representative providers**

- `dst-user-core-service`
- `dst-goods-server`
- `dst-account-server`

**Step 2: Run bounded real replay over SSH**

Use dedicated branches and capture:

- provider sync success/failure
- rebuild-index success/failure
- produced remote file layout

**Step 3: Document observed gaps**

### Task 3: Validate GitLab API token/branch behavior once HTTPS is available

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `memory/project-context-handoff.md`
- Modify: `docs/plans/2026-03-18-environment-and-real-replay-phase6.md`

**Step 1: Verify minimum token permissions**

**Step 2: Verify target-branch absent + `API_CONTRACT_GITLAB_START_BRANCH` behavior**

**Step 3: Verify failure/rollback messaging**

### Task 4: Close out backlog status

**Files:**
- Modify: `docs/API_CONTRACT_SKILL_待优化清单.md`
- Modify: `memory/project-context-handoff.md`
- Modify: `docs/plans/2026-03-18-environment-and-real-replay-phase6.md`

**Step 1: Update status for**

- `P0`
- `P5`
- `P6`

**Step 2: Record residual risks and next recommended operator action**
