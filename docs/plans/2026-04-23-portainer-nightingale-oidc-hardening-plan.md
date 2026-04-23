# Portainer Nightingale OIDC Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 Portainer 原生 OIDC 自动化字段，并让 Nightingale 配置随 `.env` 与 `--base-domain` 一起稳定生成。

**Architecture:** 保持 Portainer 与 Nightingale 都走各自原生 OIDC，不改成 `oauth2-proxy` 前置模式。Portainer 继续通过安装阶段 API 写入认证设置；Nightingale 改为启动前根据 `.env` 渲染 `config.toml`，避免主机名和 client secret 漂移。

**Tech Stack:** Python `unittest`, Bash, Docker Compose, Keycloak OIDC, Portainer API, Nightingale TOML config

---

### Task 1: Lock Portainer OAuth defaults with failing tests

**Files:**
- Modify: `tests/test_install_helper.py`
- Modify: `scripts/install_helper.py`

- [ ] 为 `configure-portainer` CLI 增加失败测试，锁定 `UserIdentifier`、`Scopes`、`OAuthAutoCreateUsers`
- [ ] 运行单测确认先失败
- [ ] 只补最小实现，让测试转绿

### Task 2: Render Nightingale config from `.env`

**Files:**
- Modify: `scripts/install_helper.py`
- Modify: `scripts/up-main.sh`
- Modify: `.env.example`
- Modify: `scripts/install-lib.sh`
- Modify: `scripts/bootstrap-keycloak.sh`
- Modify: `nightingale/config.toml`
- Modify: `tests/test_nacos_nightingale_compose.py`
- Modify: `tests/test_install_helper.py`

- [ ] 为 Nightingale 配置渲染新增失败测试，锁定 `.env -> config.toml`
- [ ] 运行单测确认先失败
- [ ] 实现 `render-nightingale-config` 子命令，并在 `up-main.sh` 调用
- [ ] 补 `.env.example` 和安装默认值，统一 `NIGHTINGALE_CLIENT_SECRET`
- [ ] 更新默认渲染后的 `nightingale/config.toml`

### Task 3: Verification and docs

**Files:**
- Modify: `README.md`

- [ ] 补 README 中 Portainer 自动化字段和 Nightingale 渲染说明
- [ ] 运行相关测试与最小回归验证
