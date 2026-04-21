# WSL2 DevOps SSO Stack

本项目用于在 WSL2 的 Arch Linux 环境中，部署一套以 Keycloak 为统一认证中心的本地 DevOps 管理栈。  

## 包含的服务

- Keycloak + PostgreSQL
- Portainer
- Kafka（单节点 KRaft）
- KafkaUI
- RedisInsight
- phpMyAdmin + MariaDB
- mongo-express + MongoDB
- oauth2-proxy
- Harbor
- Nacos
- Nightingale

## 目录结构

```text
.
├── .env.example
├── README.md
├── compose.yml
├── docs
│   ├── plans
│   └── requirements
├── harbor
│   ├── README.md
│   ├── docker-compose.override.yml
│   └── harbor.yml.example
├── kafka-ui
│   └── application.yml
├── oauth2-proxy
│   └── oauth2-proxy.cfg
├── outputs
│   └── runtime
└── scripts
```

## WSL2 注意事项

### 1. 不要把 OIDC 地址写成 localhost

浏览器和容器内服务访问 Keycloak 时，必须看到同一个 issuer。  
因此 `.env` 里的 `PUBLIC_HOST` 应该填写：

- WSL2 当前 IP
- 或你后续准备用的本地域名

不要在 Keycloak client、Harbor hostname、oauth2-proxy redirect URI 里混用 `localhost` 和 IP。

### 2. 数据目录尽量放 Linux 文件系统

数据库与 Harbor 数据目录建议留在 WSL Linux 文件系统，例如：

- `/home/...`
- `/opt/...`
- `/srv/...`

不建议放 `/mnt/c/...`，否则更容易碰到性能和权限问题。

### 3. Windows 访问与局域网访问

- Windows 本机优先使用 `http://localhost:<port>`
- 如果 `PUBLIC_HOST` 对应的 WSL IP 在 Windows 浏览器里返回异常，但 `localhost` 正常，这是 WSL2/宿主机转发路径问题，不是容器本身问题
- 如果要让局域网其他机器访问，需要额外处理 WSL2 网络映射
- 这部分不在本项目脚本自动化范围内

## 快速开始

### 0. 一键安装

如果你希望按当前项目约定直接完成预检、补 `.env`、启动主栈、准备 Harbor、初始化 Keycloak，并启动业务面板，可以直接运行：

```bash
./install.sh
```

常用参数：

```bash
./install.sh --repair
./install.sh --skip-panel
```

说明：

- `--repair` 是对同一安装流程的重跑/修复模式，不是单独的安装路径
- 安装脚本会在 `.env` 缺少常用密码或 secret 占位值时自动生成安全随机值
- 安装脚本不会自动修改 Windows 宿主机的 `hosts` 文件，需要你手工添加
- 安装脚本最终提示里给出的主机名与 `hosts` 指引，会按当前 `.env` 中的 `*_PUBLIC_HOST` 值输出；未配置时才回退到默认示例
- Harbor 为必需组件；默认要求 `harbor/installer/` 目录和其中的安装脚本已经存在

### 1. 复制环境文件

```bash
./scripts/prepare-env.sh
```

然后编辑 `.env`，至少修改：

- `PUBLIC_HOST`
- 所有密码和 secret
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_HOST_BOOTSTRAP_SERVER`
- `KEYCLOAK_TEST_PASSWORD`，如果你准备直接用脚本创建本地测试用户

### 2. 创建外部网络

```bash
./scripts/init-network.sh
```

### 3. 启动主栈

```bash
./scripts/up-main.sh
```

### 4. 检查主栈状态

```bash
./scripts/check-main.sh
```

### 5. 统一启停所有服务

推荐直接使用总控脚本：

```bash
./scripts/services.sh start
./scripts/services.sh stop
./scripts/services.sh restart
./scripts/services.sh status
```

说明：

- `start` 会先启动主栈，再在 Harbor compose 存在时启动 Harbor
- `stop` 只停止容器，不删除卷
- `restart` 适合你重新测试前做一次完整重启
- `status` 会同时显示主栈和 Harbor 的状态

## 默认访问入口

当前默认只保留统一 Web 入口 `80` 端口，按主机名分流：

- Keycloak: `http://auth.localhost`
- Portainer: `http://portainer.localhost`
- KafkaUI: `http://kafka.localhost`
- RedisInsight: `http://redis.localhost`
- phpMyAdmin: `http://pma.localhost`
- mongo-express: `http://mongo.localhost`
- Harbor: `http://harbor.localhost`
- Nacos: `http://nacos.localhost`
- Nightingale: `http://nightingale.localhost`

非 Web 入口仍单独保留：

- Kafka bootstrap: `PUBLIC_HOST:9092`

## 统一业务面板（v1）

业务面板用于统一查看业务单元状态并执行受控启停。

### 启动方式

```bash
./scripts/panel.sh start
```

### 访问地址

```text
http://BUSINESS_PANEL_HOST:BUSINESS_PANEL_PORT
```

上面的地址表示面板服务的监听/绑定地址。默认值来自 `.env` 中的 `BUSINESS_PANEL_HOST` 与 `BUSINESS_PANEL_PORT`（默认 `127.0.0.1:8090`）。
如果 `BUSINESS_PANEL_HOST=0.0.0.0`，浏览器访问时应使用实际可达的主机名或 IP（例如 WSL2 IP 或 `localhost` 的可达映射），不要直接输入 `0.0.0.0`。

### v1 能力范围

- 业务卡片提供直达链接：Keycloak、Portainer、KafkaUI、RedisInsight、phpMyAdmin、mongo-express、Harbor、Nacos、Nightingale
- 每个业务单元提供三层状态：`container / endpoint / auth`
- 支持栈级控制：`all` 的 `start / stop / restart`
- 支持业务单元级控制：每张业务卡片的 `start / stop / restart`

补充说明：业务卡片的直达链接和面板内状态探测默认按 `BROWSER_HOST` 生成，适合本机浏览器直接走 `localhost`。这不会改动主栈自身仍使用的 `PUBLIC_HOST` / OIDC 配置；如果你的浏览器访问主机不是 `localhost`，请把 `.env` 里的 `BROWSER_HOST` 改成实际访问主机。

## 统一主机名入口（HTTP）

当前项目支持通过统一反向代理入口把多个业务收敛到 `80` 端口，并按主机名分流。

### Windows `hosts` 必填项

需要在 Windows 宿主机的 `hosts` 文件中加入当前 `.env` 里各个 `*_PUBLIC_HOST` 对应的主机名。安装脚本最终摘要会按当前值给出提示；下面这组只是默认示例：

```text
127.0.0.1 auth.localhost
127.0.0.1 portainer.localhost
127.0.0.1 kafka.localhost
127.0.0.1 redis.localhost
127.0.0.1 pma.localhost
127.0.0.1 mongo.localhost
127.0.0.1 harbor.localhost
127.0.0.1 nacos.localhost
127.0.0.1 nightingale.localhost
```

Windows `hosts` 示例：

```text
127.0.0.1 auth.localhost
127.0.0.1 portainer.localhost
127.0.0.1 kafka.localhost
127.0.0.1 redis.localhost
127.0.0.1 pma.localhost
127.0.0.1 mongo.localhost
127.0.0.1 harbor.localhost
127.0.0.1 nacos.localhost
127.0.0.1 nightingale.localhost
```

如果你把 `.env` 中的 `KEYCLOAK_PUBLIC_HOST`、`PORTAINER_PUBLIC_HOST`、`KAFKA_UI_PUBLIC_HOST`、`REDISINSIGHT_PUBLIC_HOST`、`PHPMYADMIN_PUBLIC_HOST`、`MONGO_EXPRESS_PUBLIC_HOST`、`HARBOR_PUBLIC_HOST`、`NACOS_PUBLIC_HOST`、`NIGHTINGALE_PUBLIC_HOST` 改成了其他值，`hosts` 也要同步改成这些当前值。

统一入口主机名：

- Keycloak: `http://auth.localhost`
- Portainer: `http://portainer.localhost`
- KafkaUI: `http://kafka.localhost`
- RedisInsight: `http://redis.localhost`
- phpMyAdmin: `http://pma.localhost`
- mongo-express: `http://mongo.localhost`
- Harbor: `http://harbor.localhost`
- Nacos: `http://nacos.localhost`
- Nightingale: `http://nightingale.localhost`

说明：

- 当前方案默认关闭旧的 Web 宿主机端口入口，仅保留统一入口 `80`
- 新的浏览器公开地址、OAuth redirect URI 和业务面板直达链接都以各服务自己的 `*_PUBLIC_HOST` 为准
- 包括 Nacos 与 Nightingale 在内，统一入口下都使用同一个 `auth.localhost`（Keycloak）登录会话
- `PUBLIC_HOST` 仍保留给当前主栈里尚未拆分的地址用途，例如 Kafka 宿主机 broker 广播地址

### v1 限制

- Portainer 在 v1 中不做稳定的端到端认证检查（仅保留 `not_checked` 级别）
- Harbor OIDC 在 v1 仅做页面级证据检查，不读取 Harbor 后台配置
- Nacos 与 Nightingale 在 v1 只保证接通 Keycloak 登录；角色、团队和管理员映射暂未自动化

## Keycloak 初始化

### 1. 登录管理台

打开：

```text
http://PUBLIC_HOST:8080/admin
```

使用 `.env` 里的：

- `KEYCLOAK_ADMIN_USER`
- `KEYCLOAK_ADMIN_PASSWORD`

### 2. 创建 Realm

推荐：

- Realm name: `infra`

如果你修改过 `.env` 里的 `KEYCLOAK_REALM`，就以你自己的值为准。

### 3. 创建组

建议至少创建：

- `/platform-admins`
- `/harbor-admins`
- `/kafka-admins`
- `/tools-users`

### 4. 创建测试用户

例如：

- Username: `opsadmin`
- Email: `opsadmin@example.local`

并把用户加入适当的组。

### 5. 创建 groups Client Scope

在 `Client scopes` 里创建一个 `groups` scope，增加 `Group Membership` mapper：

- Token Claim Name: `groups`
- Full group path: `ON`
- Add to ID token: `ON`
- Add to access token: `ON`
- Add to userinfo: `ON`

## Keycloak Clients 建议

### 1. Portainer

- Client ID: `portainer`
- Client Type: `OpenID Connect`
- Client authentication: `ON`
- Standard flow: `ON`
- Valid redirect URIs:
  - `http://portainer.localhost/`
- Valid post logout redirect URIs:
  - `+`
- Web origins:
  - `http://portainer.localhost`
- Default client scopes:
  - `profile`
  - `email`
  - `groups`

### 2. KafkaUI

- Client ID: `kafka-ui`
- Client authentication: `ON`
- Standard flow: `ON`
- Valid redirect URIs:
  - `http://kafka.localhost/login/oauth2/code/keycloak`
- Valid post logout redirect URIs:
  - `http://kafka.localhost/`
- Web origins:
  - `http://kafka.localhost`
- Default client scopes:
  - `profile`
  - `email`
  - `groups`

### 2.1 Kafka Broker

- 部署方式：单节点 Kafka，KRaft 模式，无 ZooKeeper
- 容器内地址：`kafka:29092`
- 宿主机地址：`PUBLIC_HOST:9092`
- 当前定位：给 KafkaUI 和本机调试提供一个最小可用的 broker

### 3. oauth2-proxy

- Client ID: `oauth2-proxy`
- Client authentication: `ON`
- Standard flow: `ON`
- Valid redirect URIs:
  - `http://redis.localhost/oauth2/callback`
  - `http://pma.localhost/oauth2/callback`
  - `http://mongo.localhost/oauth2/callback`
- Valid post logout redirect URIs:
  - `http://redis.localhost/*`
  - `http://pma.localhost/*`
  - `http://mongo.localhost/*`
- Web origins:
  - `+`
- Default client scopes:
  - `profile`
  - `email`
  - `groups`

#### Audience mapper

`oauth2-proxy` client 建议额外增加一个 Audience mapper，把 `oauth2-proxy` 自己加入 token audience。

### 4. Harbor

- Client ID: `harbor`
- Client authentication: `ON`
- Standard flow: `ON`
- Valid redirect URIs:
  - `http://harbor.localhost/*`
- Valid post logout redirect URIs:
  - `http://harbor.localhost/*`
- Web origins:
  - `http://harbor.localhost`
- Default client scopes:
  - `profile`
  - `email`
  - `groups`

## 各服务接入说明

### Portainer

先用本地管理员账号登录 Portainer，然后在：

- `Settings -> Authentication -> OAuth`

填写：

- Client ID: `portainer`
- Client Secret: `PORTAINER_CLIENT_SECRET`
- Authorization URL: `http://auth.localhost/realms/infra/protocol/openid-connect/auth`
- Access Token URL: `http://auth.localhost/realms/infra/protocol/openid-connect/token`
- Resource URL: `http://auth.localhost/realms/infra/protocol/openid-connect/userinfo`
- Redirect URL: `http://portainer.localhost/`
- Logout URL: `http://auth.localhost/realms/infra/protocol/openid-connect/logout`
- User Identifier: `preferred_username`
- Scopes: `openid profile email groups`
- Auto create users: `ON`

建议第一次不要隐藏本地登录，等 OIDC 跑通后再收口。

### KafkaUI

KafkaUI 已经通过 `kafka-ui/application.yml` 预设 OIDC。  
只要 Keycloak client 配对，访问：

```text
http://PUBLIC_HOST:8082
```

就会跳到 Keycloak 登录。

### Kafka

Kafka 本体采用单节点 KRaft 模式：

- 容器内 broker：`kafka:29092`
- 宿主机 broker：`PUBLIC_HOST:9092`

检查 Kafka 运行情况：

```bash
./scripts/check-kafka.sh
```

如果你想从宿主机测试连接，使用：

```text
PUBLIC_HOST:9092
```

### oauth2-proxy 前置保护

以下入口都经过 Keycloak 认证：

- RedisInsight: `http://PUBLIC_HOST:4180`
- phpMyAdmin: `http://PUBLIC_HOST:4181`
- mongo-express: `http://PUBLIC_HOST:4182`

第一次访问会跳转到 Keycloak。  
后续因为已经有 Keycloak 会话，一般不需要重复输密码。

## Harbor 安装与 OIDC

Harbor 保持官方安装方式，不并入主 compose。

### 1. 下载 Harbor online installer

从 Harbor 官方 release 下载并解压到：

```text
harbor/installer/
```

### 2. 准备 Harbor 配置

执行：

```bash
./scripts/prepare-harbor.sh
```

这个脚本会：

- 检查 `harbor/installer/install.sh` 是否存在
- 复制 `harbor/harbor.yml.example` 到 `harbor/installer/harbor.yml`
- 复制 `harbor/docker-compose.override.yml` 到 `harbor/installer/`
- 用 `.env` 里的 `PUBLIC_HOST`、`HARBOR_ADMIN_PASSWORD`、`TOOLS_NETWORK` 替换模板中的关键值

### 3. 安装 Harbor

```bash
cd harbor/installer
./install.sh --with-trivy
```

### 4. 配置 Harbor OIDC

Harbor Web UI 中进入：

- `Administration -> Configuration -> Authentication`

填写：

- Auth Mode: `OIDC`
- OIDC Provider Name: `keycloak`
- OIDC Provider Endpoint: `http://PUBLIC_HOST:8080/realms/infra`
- OIDC Client ID: `harbor`
- OIDC Client Secret: `HARBOR_CLIENT_SECRET`
- OIDC Scope: `openid,profile,email,groups,offline_access`
- Group Claim Name: `groups`
- OIDC Admin Group: `/harbor-admins`
- Username Claim: `preferred_username`
- Automatic Onboarding: `ON`

## Harbor Docker CLI 注意事项

如果 Harbor 仍然走 HTTP，本机 Docker 需要加 insecure registry。  
例如编辑 `/etc/docker/daemon.json`：

```json
{
  "insecure-registries": ["PUBLIC_HOST:8088"]
}
```

然后重启 Docker：

```bash
sudo systemctl restart docker
```

另外要注意：

- `docker login PUBLIC_HOST:8088` 使用的不是 Keycloak 密码
- 需要在 Harbor Web UI 中获取对应用户的 `CLI Secret`

## SSO 验证步骤

按这个顺序验证最直观：

1. 先登录 `http://PUBLIC_HOST:8080`
2. 打开 `http://PUBLIC_HOST:19000`
3. 打开 `http://PUBLIC_HOST:8082`
4. 打开 `http://PUBLIC_HOST:4180`
5. 打开 `http://PUBLIC_HOST:4181`
6. 打开 `http://PUBLIC_HOST:4182`
7. 打开 `http://PUBLIC_HOST:8088`

如果 2 到 7 都能在已有 Keycloak 会话下直接进入或无感回跳，说明统一登录已基本跑通。

## 常见问题排查

### 1. redirect_uri mismatch

检查：

- Keycloak client 的 redirect URI 是否与实际访问地址完全一致
- 端口、路径、结尾 `/` 是否一致
- 有没有把 `localhost` 和 IP 混用

### 2. Harbor OIDC 登录失败

重点看：

- Harbor 的 `hostname` 不是 `localhost`
- Harbor OIDC endpoint 是 `http://PUBLIC_HOST:8080/realms/infra`
- Keycloak client 的 redirect URI 先放宽到 `http://PUBLIC_HOST:8088/*`

### 3. oauth2-proxy 循环跳转

检查：

- `OAUTH2_PROXY_COOKIE_SECRET` 是否正确
- `oauth2-proxy` client 是否加了 audience
- 三个 oauth2-proxy 实例是不是误用了同一个 cookie name

### 4. RedisInsight 卷权限问题

如果 RedisInsight 无法写 `/data`：

- 可以改为 bind mount 到 Linux 文件系统目录
- 或手动调整卷权限给 UID 1000

### 5. WSL2 中能访问，Windows 或局域网不能访问

这通常不是 compose 问题，而是 WSL2 网络映射问题。  
需要你自行处理 Windows 端口转发、防火墙或 mirrored networking。

## 静态校验

建议在每次修改配置后运行：

```bash
bash -n scripts/*.sh
docker compose --env-file .env config >/dev/null
```
