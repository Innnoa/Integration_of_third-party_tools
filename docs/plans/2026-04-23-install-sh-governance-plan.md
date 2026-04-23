# install.sh Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `install.sh` 收敛成唯一对外安装入口，补齐依赖安装、自愈重试、分阶段结果记录和更严格的最终验收。

**Architecture:** 继续保留 `install.sh + scripts/install-lib.sh + scripts/install_helper.py` 结构，由 `install.sh` 负责摘要输出，`install-lib.sh` 负责阶段调度、依赖检测/安装、自愈和验证汇总。测试继续以 Python `unittest` 驱动，优先锁定阶段顺序、自动安装依赖、失败重试和结果摘要。

**Tech Stack:** Bash, Python `unittest`, Docker Compose, existing helper scripts

---

### Task 1: Lock installer governance behavior with failing tests

**Files:**
- Modify: `tests/test_install_script.py`

- [ ] 补失败测试，锁定 `deps` 阶段会在缺少依赖时自动调用受支持发行版的包管理器
- [ ] 补失败测试，锁定 `main_stack` 或 `verify` 阶段失败时会按有限次数重试
- [ ] 补失败测试，锁定最终摘要会输出 `overall` 和阶段结果

### Task 2: Implement dependency detection, package-manager mapping, and retries

**Files:**
- Modify: `scripts/install-lib.sh`
- Modify: `install.sh`

- [ ] 在 `install-lib.sh` 增加发行版/包管理器检测与缺失命令判断
- [ ] 实现 `deps` 阶段，支持 `apt / dnf / yum / pacman / zypper`
- [ ] 为关键阶段增加统一重试包装，并在失败前尝试已知安全修复
- [ ] 让阶段日志和状态可被最终摘要读取

### Task 3: Tighten verification and summarize outcomes

**Files:**
- Modify: `scripts/install-lib.sh`
- Modify: `install.sh`
- Modify: `README.md`

- [ ] 让 `verify` 成为常规阶段，而不是只在 `--base-domain` 时触发
- [ ] 输出 `success / degraded / failed` 总状态和各阶段结果
- [ ] 更新 README 中 `install.sh` 的能力说明与成功标准

### Task 4: Run focused verification

**Files:**
- Modify: `tests/test_install_script.py`（如需修正合同）

- [ ] 运行安装器相关测试
- [ ] 运行 `docker compose --env-file .env -f compose.yml config`
- [ ] 检查安装器输出与 README 描述一致
