# WSL2 DevOps SSO Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成一套在 WSL2 Arch Linux 上可直接使用的本地 DevOps 管理栈部署骨架，基于 Keycloak 统一 SSO，并保留 Harbor 官方安装路径。

**Architecture:** 主栈通过单一 `compose.yml` 管理 Keycloak、PostgreSQL、Portainer、KafkaUI、RedisInsight、phpMyAdmin、MongoDB、mongo-express、Redis、MariaDB 与 oauth2-proxy；Harbor 不并入主 compose，而是通过 `harbor.yml.example`、override 和辅助脚本接入同一外部网络。OIDC 地址统一使用 `PUBLIC_HOST` 占位，默认本地 HTTP 测试优先。

**Tech Stack:** Docker Compose, Keycloak, PostgreSQL, Portainer, Kafbat UI, oauth2-proxy, Redis, RedisInsight, MariaDB, phpMyAdmin, MongoDB, mongo-express, Harbor

---

### Task 1: 初始化项目骨架与环境模板

**Files:**
- Create: `.env.example`
- Create: `README.md`
- Create: `scripts/init-network.sh`
- Create: `scripts/up-main.sh`
- Create: `scripts/check-main.sh`
- Create: `scripts/prepare-env.sh`

- [ ] **Step 1: 写入环境模板**

```dotenv
PUBLIC_HOST=REPLACE_ME_PUBLIC_HOST
PUBLIC_SCHEME=http
TOOLS_NETWORK=tools_net
KEYCLOAK_REALM=infra
```

- [ ] **Step 2: 写入基础脚本**

```bash
#!/usr/bin/env bash
set -euo pipefail
docker network inspect "${TOOLS_NETWORK}" >/dev/null 2>&1 || docker network create "${TOOLS_NETWORK}"
```

- [ ] **Step 3: 写入 README 顶部说明**

```md
# WSL2 DevOps SSO Stack

本项目用于在 WSL2 本地部署 Keycloak 驱动的统一 SSO 管理栈。
```

- [ ] **Step 4: 验证脚本语法**

Run: `bash -n scripts/init-network.sh scripts/up-main.sh scripts/check-main.sh scripts/prepare-env.sh`  
Expected: exit code 0

### Task 2: 生成主栈 compose

**Files:**
- Create: `compose.yml`

- [ ] **Step 1: 定义公共网络与卷**

```yaml
networks:
  tools_net:
    external: true
    name: ${TOOLS_NETWORK}
```

- [ ] **Step 2: 写入 Keycloak 与 PostgreSQL**

```yaml
keycloak:
  image: ${KEYCLOAK_IMAGE}
  command: start-dev
```

- [ ] **Step 3: 写入管理与代理服务**

```yaml
portainer:
  command: --http-enabled --bind :9000 --bind-https ""
```

- [ ] **Step 4: 运行 compose 解析检查**

Run: `docker compose --env-file .env.example config >/tmp/tools-sso-compose.rendered.yml`  
Expected: exit code 0

### Task 3: 生成 oauth2-proxy 与 KafkaUI 配置

**Files:**
- Create: `oauth2-proxy/oauth2-proxy.cfg`
- Create: `kafka-ui/application.yml`

- [ ] **Step 1: 写入 oauth2-proxy 公共配置**

```toml
provider = "keycloak-oidc"
scope = "openid profile email groups"
session_store_type = "redis"
```

- [ ] **Step 2: 写入 KafkaUI OIDC 配置**

```yaml
auth:
  type: OAUTH2
```

- [ ] **Step 3: 检查占位符是否保留**

Run: `rg -n "PUBLIC_HOST|KEYCLOAK_REALM|KAFKA_UI_CLIENT_ID" kafka-ui oauth2-proxy`  
Expected: 能看到占位符或环境变量引用

### Task 4: 生成 Harbor 模块模板

**Files:**
- Create: `harbor/harbor.yml.example`
- Create: `harbor/docker-compose.override.yml`
- Create: `harbor/README.md`
- Create: `scripts/prepare-harbor.sh`

- [ ] **Step 1: 写入 harbor.yml 模板**

```yaml
hostname: REPLACE_ME_PUBLIC_HOST

http:
  port: 8088
```

- [ ] **Step 2: 写入 Harbor 网络 override**

```yaml
networks:
  tools_net:
    external: true
    name: tools_net
```

- [ ] **Step 3: 写入 Harbor 预检查脚本**

```bash
#!/usr/bin/env bash
set -euo pipefail
test -f harbor/installer/install.sh
```

- [ ] **Step 4: 验证 Harbor 模块文件存在**

Run: `find harbor -maxdepth 2 -type f | sort`  
Expected: 至少包含 3 个 Harbor 文件

### Task 5: 完成总文档与静态验证

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 补齐 README 的部署说明、Keycloak 初始化、OIDC 参数与排障章节**

```md
## Keycloak 初始化
## Harbor OIDC 配置
## 常见问题排查
```

- [ ] **Step 2: 运行静态验证**

Run: `bash -n scripts/*.sh && docker compose --env-file .env.example config >/tmp/tools-sso-compose.rendered.yml && rg -n "REPLACE_ME_PUBLIC_HOST|PUBLIC_HOST" .`  
Expected: 脚本语法正确、compose 可解析、占位符保留合理

- [ ] **Step 3: 记录验证结果并准备交付说明**

Run: `find . -maxdepth 3 -type f | sort`  
Expected: 能看到根目录配置、脚本、文档、Harbor 模块与 runtime 留痕

