# Nacos oauth2-proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `nacos.localhost` 从 Nacos 原生 OIDC 切换到独立 `oauth2-proxy-nacos` 入口，并保持 Keycloak SSO。

**Architecture:** 采用现有 `gateway -> oauth2-proxy -> app` 模式。`gateway` 只做域名转发，`oauth2-proxy-nacos` 负责浏览器侧认证跳转，Nacos 自身关闭原生 OIDC 登录面，只保留 Console upstream。

**Tech Stack:** Docker Compose, Nginx, oauth2-proxy, Keycloak, Nacos, Python `unittest`

---

## Internal Grade

- `L`
- 单代理串行执行
- 先测试收敛合同，再调整配置，最后做静态验证

## File Map

- Modify: `business_panel/catalog.py`
- Modify: `business_panel/probes.py`
- Modify: `compose.yml`
- Modify: `gateway/nginx.conf`
- Modify: `nacos/application.properties`
- Modify: `scripts/bootstrap-keycloak.sh`
- Modify: `tests/test_config_catalog.py`
- Modify: `tests/test_probes.py`
- Modify: `tests/test_nacos_nightingale_compose.py`
- Optional: `README.md`

## Phase 1: Red Tests

- [ ] 把 `tests/test_config_catalog.py` 中 `nacos` 单元合同改为：
  - `start_services=("nacos", "nacos-mysql", "oauth2-proxy-nacos")`
  - `stop_services=("nacos", "oauth2-proxy-nacos")`
  - `auth_mode="oauth2_proxy_redirect"`
  - `auth_path="/oauth2/"`
- [ ] 把 `tests/test_probes.py` 中 Nacos 认证合同改为检查 `302 -> /oauth2/` 或 Keycloak redirect，不再检查 `/v1/auth/oidc/login`
- [ ] 把 `tests/test_probes.py` 中 Nacos 配置合同改为：
  - `nacos.core.auth.enabled=false`
  - 不再要求 `oidc` 相关 key 存在
  - `bootstrap_clients` 中 `oauth2-proxy` 包含 `http://nacos.localhost/oauth2/callback`
- [ ] 把 `tests/test_nacos_nightingale_compose.py` 中 compose / gateway 合同改为：
  - 存在 `oauth2-proxy-nacos`
  - `nacos.localhost` upstream 指向 `http://oauth2-proxy-nacos:4183`
- [ ] 运行聚焦测试，确认至少一项按新合同失败

## Phase 2: Green Implementation

- [ ] 在 `business_panel/catalog.py` 把 Nacos 切到 `oauth2_proxy_redirect`
- [ ] 在 `business_panel/probes.py` 删除 Nacos 原生 OIDC 特判，复用 `oauth2_proxy_redirect` 探测
- [ ] 在 `compose.yml` 新增 `oauth2-proxy-nacos`
  - `--http-address=0.0.0.0:4183`
  - `--redirect-url=${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}/oauth2/callback`
  - `--upstream=http://nacos:8080/`
  - `--cookie-name=_oauth2_proxy_nacos`
- [ ] 在 `gateway/nginx.conf` 把 `nacos.localhost` 改到 `oauth2-proxy-nacos`
- [ ] 在 `nacos/application.properties` 关闭原生 auth / oidc，只保留 Console 基础配置
- [ ] 在 `scripts/bootstrap-keycloak.sh` 给 `oauth2-proxy` client 增加 Nacos callback/origin，并移除 `nacos` 原生浏览器侧 OIDC client 合同

## Phase 3: Verification And Cleanup

- [ ] 运行目标单测
- [ ] 运行 `docker compose --env-file .env config`
- [ ] 如 README 已明显与实现不一致，则补最小说明
- [ ] 写入 runtime verification receipt 与 cleanup receipt

## Verification Commands

- `python3 -m unittest tests.test_config_catalog tests.test_probes tests.test_nacos_nightingale_compose -v`
- `docker compose --env-file .env config >/tmp/nacos-oauth2-proxy.compose.yml`

## Rollback

- 如认证代理链路失效，回滚本次对 `compose.yml`、`gateway/nginx.conf`、`nacos/application.properties`、`scripts/bootstrap-keycloak.sh` 的改动
- 不回滚与 Nightingale 或其他服务无关的既有脏改动

## Cleanup Expectations

- 输出 `verification-receipt.md`
- 输出 `cleanup-receipt.md`
- 更新 `stage-lineage.json` 到 `phase_cleanup`
