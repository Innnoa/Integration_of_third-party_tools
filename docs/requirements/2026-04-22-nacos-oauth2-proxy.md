# 2026-04-22 Nacos oauth2-proxy Requirement

## 背景

仓库在 2026-04-21 曾尝试让 Nacos 继续使用原生 OIDC，但当前方案已冻结为放弃 Nacos 原生 OIDC，改走与 RedisInsight、phpMyAdmin 相同的外层认证代理模式。

现有稳定模式：

- `gateway` 负责域名入口分发
- 受保护应用通过 `oauth2-proxy` 实例接入 Keycloak
- 应用本身只处理业务页面，不再承担浏览器侧 OIDC 登录回跳

## 目标

本次只交付一件事：

- 让 `http://nacos.localhost/` 通过独立的 `oauth2-proxy-nacos` 接入 Keycloak，并在认证完成后进入可用的 Nacos Console

## 冻结方案

### 入口链路

- 浏览器访问 `http://nacos.localhost/`
- `gateway` 不再直连 `nacos:8080`
- `gateway` 改为转发到 `oauth2-proxy-nacos`
- `oauth2-proxy-nacos` 的 upstream 固定为 `http://nacos:8080/`

### 认证边界

- Keycloak 继续使用 `auth.localhost` 与现有 realm
- Nacos 不再使用原生 OIDC 登录
- Nacos Console 的原生登录页关闭
- Nacos 应用对外只保留被 `oauth2-proxy-nacos` 代理后的访问面

### Keycloak 合同

- `oauth2-proxy` Keycloak client 必须增加 `http://nacos.localhost/oauth2/callback`
- `oauth2-proxy` Keycloak client 的 web origin 必须增加 `http://nacos.localhost`
- 不再把 `nacos` 作为浏览器侧原生 OIDC client 的事实来源

### 仓库内合同

- `business_panel` 中 `nacos` 单元改为 `oauth2_proxy_redirect`
- `business_panel` 中 `nacos` 的认证探测改为检查 `/oauth2/` 跳转
- `compose.yml` 新增 `oauth2-proxy-nacos`
- `gateway/nginx.conf` 中 `nacos.localhost` 指向 `oauth2-proxy-nacos`
- `nacos/application.properties` 去掉原生 OIDC 依赖，只保留 Console 与基础服务配置

## 验收标准

满足以下条件才算完成：

1. 配置与测试层面不再依赖 `nacos.core.auth.system.type=oidc`
2. `nacos.localhost` 的入口路由与认证模型与 RedisInsight/phpMyAdmin 保持同类模式
3. `scripts/bootstrap-keycloak.sh` 中 `oauth2-proxy` client 已覆盖 Nacos callback / origin
4. 相关单元测试通过，且 `docker compose config` 可解析

## 非目标

- 不做 Nacos 角色、租户、细粒度权限映射
- 不做 Nacos 单点退出联动
- 不保留 “原生 OIDC 与 oauth2-proxy 双轨并存” 的兼容路径
