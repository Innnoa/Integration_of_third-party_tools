# WSL2 本地 DevOps 管理栈统一 SSO Requirement

状态：draft-approved-in-chat  
日期：2026-04-16  
模式：`vibe`  
运行策略：本地 HTTP 优先，统一 `PUBLIC_HOST` 占位，后续可平滑切换 HTTPS/域名

## 1. 目标

在 WSL2 的 Arch Linux 环境中，构建一套可本地运行的 DevOps 管理栈，统一接入 Keycloak，实现尽可能一致的单点登录体验。

## 2. 交付物

本次实现阶段需要生成以下交付物：

- 根目录 `compose.yml`
- 根目录 `.env.example`
- 根目录 `README.md`
- `oauth2-proxy/oauth2-proxy.cfg`
- `kafka-ui/application.yml`
- `harbor/harbor.yml.example`
- `harbor/docker-compose.override.yml`
- `harbor/README.md`
- `scripts/` 下的启动、检查、网络初始化、Harbor 预处理脚本
- `docs/plans/` 下的执行计划
- `outputs/runtime/vibe-sessions/` 下的最小运行留痕

## 3. 范围

### 3.1 必须覆盖的服务

- Keycloak
- PostgreSQL（Keycloak 后端）
- Portainer
- KafkaUI
- RedisInsight
- phpMyAdmin
- MongoDB
- mongo-express
- Redis
- MariaDB
- oauth2-proxy
- Harbor

### 3.2 认证方式

- Portainer：使用原生 OAuth/OIDC 对接 Keycloak
- KafkaUI：使用原生 OAuth2/OIDC 对接 Keycloak
- Harbor：使用 Harbor 自带 OIDC 对接 Keycloak
- RedisInsight：通过 oauth2-proxy 前置保护
- phpMyAdmin：通过 oauth2-proxy 前置保护
- mongo-express：通过 oauth2-proxy 前置保护

## 4. 架构约束

### 4.1 网络与编排

- 主栈使用单一 `docker compose` 文件管理
- Harbor 不强行并入主 compose，保持官方 `harbor.yml + install.sh` 路径
- Harbor 通过外部 Docker 网络接入主栈，与其他服务共享一个可发现网络
- 统一外部网络名使用占位变量，例如 `TOOLS_NETWORK=tools_net`

### 4.2 地址策略

- 所有 OIDC 相关地址统一基于 `PUBLIC_HOST`
- 默认不把 `localhost` 写入 OIDC issuer、redirect URI 或 Harbor hostname
- `PUBLIC_HOST` 使用用户后续填写的稳定访问地址，可是 WSL2 当前 IP，也可以是后续域名
- 默认公开协议为 `http`

### 4.3 Harbor 例外处理

- Harbor 维持官方安装方式，不手工拆成自维护的主 compose 服务组
- Harbor 交付物应包含：
  - `harbor.yml.example`
  - 网络 override 文件
  - 安装与 OIDC 配置说明
  - Docker insecure registry 说明

## 5. 端口规划

默认端口规划如下，后续通过 `.env.example` 可调整：

- Keycloak：`8080`
- Portainer：`9000`
- KafkaUI：`8082`
- RedisInsight（oauth2-proxy 暴露）：`4180`
- phpMyAdmin（oauth2-proxy 暴露）：`4181`
- mongo-express（oauth2-proxy 暴露）：`4182`
- Harbor：`8088`

内部依赖服务不强制对宿主机暴露：

- Keycloak PostgreSQL：`5432`
- Redis：`6379`
- MariaDB：`3306`
- MongoDB：`27017`

## 6. 配置策略

### 6.1 Keycloak

- 使用 PostgreSQL 作为后端数据库
- 使用持久化卷保存 PostgreSQL 数据
- 使用容器环境变量初始化管理员账户
- 本地测试使用 `start-dev`
- 文档必须明确：如后续切生产模式，需要切换为 `start --optimized` 并补全 HTTPS/hostname 策略

### 6.2 oauth2-proxy

- 使用 Keycloak OIDC provider
- 使用 Redis 存储 session
- 为 RedisInsight、phpMyAdmin、mongo-express 分别使用独立实例或至少独立监听入口
- 每个实例使用独立 `cookie_name`
- 配置中不预设 cookie domain，避免 IP/localhost 测试阶段冲突

### 6.3 KafkaUI

- 使用配置文件而不是长环境变量串保存 OAuth2 配置
- 配置中使用 `PUBLIC_HOST` 占位
- 留出后续按 group 做 RBAC 的位置

### 6.4 Portainer

- 容器层只负责运行 Portainer 本体
- OIDC 参数通过 README 明确指引在 UI 中配置
- 本地测试优先开启 HTTP 入口

## 7. 目录结构要求

最终项目目录至少包含：

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

## 8. 验收标准

满足以下条件才算本阶段实现完成：

1. `docker compose config` 对主栈配置解析成功
2. `.env.example` 中所有外部地址均使用占位符，不写死具体 IP
3. Harbor 相关文件完整，且说明中明确其安装方式与主栈不同
4. README 包含：
   - WSL2 注意事项
   - 启动顺序
   - Keycloak realm/client 初始化步骤
   - Portainer/KafkaUI/Harbor 的 OIDC 参数
   - oauth2-proxy 的使用方式
   - SSO 验证步骤
   - 常见问题排查
5. `scripts/` 下至少包含：
   - 外部网络创建脚本
   - 主栈启动脚本
   - 主栈检查脚本
   - Harbor 预检查或安装辅助脚本
6. 所有脚本通过 `bash -n` 静态检查

## 9. 非目标

本轮不包含以下内容：

- 自动下载 Harbor 安装包
- 自动调用 Keycloak Admin API 创建 realm/client
- 自动为 Windows 配置 `netsh interface portproxy`
- 自动生成 HTTPS 证书或 Traefik 路由
- 自动替用户执行 `docker login` 到 Harbor

## 10. 风险与注意事项

- WSL2 IP 可能变化；一旦变化，需要同步更新 `.env`
- 混用 `localhost` 与 IP 会导致 OIDC issuer 或 redirect URI 不一致
- Harbor 在 HTTP + IP 模式下只适合本地测试
- RedisInsight 卷在部分环境下可能有权限问题
- 当前目录不是 git 仓库，无法满足“写完 spec 后提交”这一流程要求，本次仅能保存文档文件，不执行提交

## 11. 实施决策

已冻结的实现决策如下：

- 采用“主 compose + Harbor 官方安装器模块”的双层结构
- 所有 OIDC 地址统一基于 `PUBLIC_HOST`
- 本轮优先完成 HTTP 可运行版本
- Harbor 单独保留安装说明和 override 文件，不伪装成普通 compose 服务

