# Integration of Third-party Tools

本项目用于在 Linux / WSL2 环境中部署一套带统一认证入口的本地第三方工具栈。当前主路径是：

- 根目录 `compose.yml` 负责主栈
- 根目录 `install.sh` 负责推荐的一键安装
- `scripts/` 负责环境准备、启动、初始化与验收
- `business_panel/` 提供独立的本地业务面板
- `harbor/` 保留 Harbor 官方安装路径，不并入主 `compose.yml`

## 当前项目体系

### 统一入口

项目当前默认使用 `80` 端口作为统一 Web 入口，通过不同主机名分流到各业务：

- Keycloak
- Portainer
- Kafka UI
- RedisInsight
- phpMyAdmin
- mongo-express
- Nacos
- Nightingale
- Harbor（可选）

非 Web 入口仍保留：

- Kafka bootstrap：`PUBLIC_HOST:9092`
- 业务面板：默认 `127.0.0.1:8090`

### 认证与组件关系

- Keycloak 是统一认证中心
- `oauth2-proxy` 负责多个 Web 工具的前置登录保护
- `gateway/nginx.conf` 负责按主机名转发到各服务
- Harbor 继续使用官方 `install.sh` 生成自己的 compose，再通过 override 接入统一网络

### phpMyAdmin 当前约束

- 只有 `platform-admins` 组成员可以进入 phpMyAdmin
- 非 `platform-admins` 成员会收到 `403`
- 进入后会自动使用固定 MariaDB 账号登录
- 该账号只授权 `appdb`
- 如需重建该账号，可执行 `./install.sh --repair` 或 `./scripts/repair-mariadb-phpmyadmin-user.sh`

### 当前包含内容

- 主栈服务：Keycloak、PostgreSQL、Portainer、Kafka、Kafka UI、Redis、RedisInsight、MariaDB、phpMyAdmin、MongoDB、mongo-express、Nacos、Nightingale、gateway、oauth2-proxy
- 可选模块：Harbor
- 本地运维面板：`business_panel`
- 自动化测试：`tests/`
- 需求/计划留档：`docs/requirements/`、`docs/plans/`
- 运行输出：`outputs/runtime/`

## 目录结构

```text
.
├── .env.example                 # 环境变量模板
├── compose.yml                  # 主栈 compose
├── install.sh                   # 推荐安装入口
├── business_panel/              # 本地业务面板
├── gateway/                     # 统一 HTTP 入口配置
├── harbor/                      # Harbor 模块与官方安装适配
├── kafka-ui/                    # Kafka UI 配置
├── nacos/                       # Nacos 配置与初始化 SQL
├── nightingale/                 # Nightingale 配置与桥接脚本
├── oauth2-proxy/                # oauth2-proxy 配置
├── phpmyadmin/                  # phpMyAdmin 自定义配置
├── scripts/                     # 安装、启动、修复、验收脚本
├── tests/                       # 自动化测试
├── docs/requirements/           # 冻结需求文档
├── docs/plans/                  # 执行计划文档
└── outputs/runtime/             # 运行日志与临时输出
```

## 环境前提

推荐在 Linux 或 WSL2 的 Linux 文件系统中运行，并提前准备：

- Docker
- Docker Compose v2（`docker compose`）
- Python 3
- `sudo` 权限（推荐安装路径会写当前 Linux 主机的 `hosts`）

补充约束：

- 数据目录建议放 Linux 文件系统，不要放 `/mnt/c/...`
- OIDC 相关主机名不要混用 `localhost` 和 IP
- 如果你在 WSL2 中使用浏览器，Windows 宿主机的 `hosts` 仍需手动补齐
- 仅有旧版 `docker-compose` v1 命令时，不算满足当前脚本依赖；安装链路检查的是 `docker compose version`

## 发行版支持矩阵

这里区分“脚本已适配”与“整套环境已完整验证”，不再统一写成一句“都支持”。

- Debian 13 `trixie`：当前脚本路径最稳，Compose 包名与安装回退逻辑已针对这条路径修复，并有自动化测试覆盖
- Ubuntu 22.04 / 24.04：`apt` 路径已适配 `docker-compose-plugin -> docker-compose-v2 -> docker-compose` 回退，脚本层兼容性明显更稳，但仍建议先跑安装前自检
- Fedora / RHEL / Rocky / AlmaLinux / CentOS：当前有 `dnf` / `yum` 包管理器映射，属于“脚本已覆盖包管理器路径”，不是“整套环境已完整验证”
- Arch Linux：当前有 `pacman` 包管理器映射，适合先跑安装前自检后再安装
- openSUSE / SLES：当前有 `zypper` 包管理器映射，适合先跑安装前自检后再安装
- 其他发行版：不默认承诺稳定兼容，建议先人工确认依赖安装方式

## 安装前自检

在首次安装前，建议先执行：

```bash
./scripts/check-install-prereqs.sh
```

脚本会输出：

- 当前发行版与版本
- 当前识别到的包管理器
- `python3`、`docker`、`docker compose`、`sudo` 状态
- 当前发行版下推导出的 Docker / Compose 候选包名
- 最终结论：`ready`、`installable` 或 `blocked`

结果解释：

- `ready`：当前主机已具备关键依赖，可以继续执行安装
- `installable`：依赖还不完整，但当前脚本能够识别包管理器并尝试安装
- `blocked`：当前主机缺少受支持的包管理器，或缺少基本提权条件，需要先人工处理

如果你只是想看当前 `apt` 系发行版会尝试哪些 Compose 包，这个脚本也会直接打印出来。

## 推荐安装路径

推荐直接走一键安装，当前项目的主入口是根目录 `install.sh`。

### 1. 基本安装

```bash
sudo ./install.sh --base-domain example.internal
```

这个入口会按当前项目约定完成以下动作：

- 预检依赖
- 生成或补齐 `.env`
- 自动派生 `auth.<domain>`、`portainer.<domain>`、`nacos.<domain>` 等主机名
- 自动回写当前 Linux 主机的 `PUBLIC_HOST`、`KAFKA_HOST_BOOTSTRAP_SERVER` 与各个 `*_PUBLIC_HOST`
- 写入当前 Linux 主机的 `hosts`
- 启动主栈
- 初始化 Keycloak
- 配置 Portainer OIDC
- 修复 phpMyAdmin 自动登录账号
- 启动业务面板（默认开启）
- 执行安装后验收并输出摘要

### 2. 常用参数

```bash
sudo ./install.sh --base-domain example.internal --repair
sudo ./install.sh --base-domain example.internal --skip-panel
sudo ./install.sh --base-domain example.internal --public-ip 192.168.50.10
sudo ./install.sh --base-domain example.internal --with-harbor
```

参数说明：

- `--base-domain`：必填，安装脚本会据此派生各服务主机名
- `--repair`：重跑安装链路并修复已有环境
- `--skip-panel`：不启动本地业务面板
- `--public-ip`：覆盖自动探测到的对外地址
- `--with-harbor`：进入 Harbor 准备与安装路径

### 3. 安装后访问

安装完成后，以 `.env` 中当前值为准，典型入口如下：

- `http://auth.<base-domain>`
- `http://portainer.<base-domain>`
- `http://kafka.<base-domain>`
- `http://redis.<base-domain>`
- `http://pma.<base-domain>`
- `http://mongo.<base-domain>`
- `http://nacos.<base-domain>`
- `http://nightingale.<base-domain>`
- `http://harbor.<base-domain>`（仅启用 Harbor 时）
- `http://127.0.0.1:8090`（默认业务面板）

### 4. 安装后建议检查

```bash
./scripts/check-main.sh
./scripts/services.sh status
./scripts/panel.sh status
```

## 手动安装路径

如果你不想直接执行一键安装，可以按当前脚本链路手动完成。

### 1. 生成 `.env`

```bash
./scripts/prepare-env.sh
```

然后至少检查并修改：

- `PUBLIC_HOST`
- `KEYCLOAK_PUBLIC_HOST`
- `PORTAINER_PUBLIC_HOST`
- `KAFKA_UI_PUBLIC_HOST`
- `REDISINSIGHT_PUBLIC_HOST`
- `PHPMYADMIN_PUBLIC_HOST`
- `MONGO_EXPRESS_PUBLIC_HOST`
- `NACOS_PUBLIC_HOST`
- `NIGHTINGALE_PUBLIC_HOST`
- 所有密码与 secret 项

### 2. 初始化网络并启动主栈

```bash
./scripts/init-network.sh
./scripts/up-main.sh
```

也可以直接使用：

```bash
docker compose --env-file .env -f compose.yml up -d
```

### 3. 初始化认证与业务配置

```bash
./scripts/bootstrap-keycloak.sh
```

这个脚本会按当前项目约定初始化 realm、测试用户、客户端和部分认证配置。

### 4. 启动业务面板

```bash
./scripts/panel.sh start
```

默认访问地址来自 `.env`：

```text
http://BUSINESS_PANEL_HOST:BUSINESS_PANEL_PORT
```

### 5. 验证

```bash
./scripts/check-main.sh
./scripts/services.sh status
```

## Harbor 路径

Harbor 不直接放进主 `compose.yml`，当前仓库保留官方安装路径。

### 1. 准备官方安装包

- 把 Harbor `online installer` 解压到 `harbor/installer/`
- 确保 `harbor/installer/install.sh` 存在

### 2. 准备配置

```bash
./scripts/init-network.sh
./scripts/prepare-harbor.sh
```

这一步会基于当前项目内容准备：

- `harbor/installer/harbor.yml`
- `harbor/installer/docker-compose.override.yml`

### 3. 执行官方安装

```bash
cd harbor/installer
./install.sh --with-trivy
```

安装完成后，`scripts/services.sh start|stop|restart|status` 会同时处理主栈和 Harbor。

## 常用运维命令

### 主栈与 Harbor

```bash
./scripts/services.sh start
./scripts/services.sh stop
./scripts/services.sh restart
./scripts/services.sh status
```

### 业务面板

```bash
./scripts/panel.sh start
./scripts/panel.sh stop
./scripts/panel.sh restart
./scripts/panel.sh status
```

### 其他常用脚本

```bash
./scripts/check-install-prereqs.sh
./scripts/check-main.sh
./scripts/repair-mariadb-phpmyadmin-user.sh
```

## 业务面板说明

`business_panel` 是独立于主 compose 的本地 Python 服务，用于统一查看业务状态并执行受控启停。

当前能力：

- 展示各业务入口链接
- 展示 `container / endpoint / auth` 三层状态
- 支持栈级与业务级 `start / stop / restart`

默认监听值来自 `.env`：

- `BUSINESS_PANEL_HOST=127.0.0.1`
- `BUSINESS_PANEL_PORT=8090`

如果把 `BUSINESS_PANEL_HOST` 改成 `0.0.0.0`，浏览器访问时仍应使用实际可达的主机名或 IP，不要直接访问 `0.0.0.0`。

## 验证与测试

文档外的常规检查方式：

```bash
PYTHONPATH=. pytest -q tests
docker compose --env-file .env -f compose.yml config
./scripts/check-main.sh
```

说明：

- `PYTHONPATH=. pytest -q tests` 用于校验当前脚本与 Python 逻辑
- `docker compose ... config` 用于校验 compose 解析
- `./scripts/check-main.sh` 用于查看当前环境的访问入口与主栈状态

## WSL2 与访问约束

### 1. 不要把 issuer 混成两套地址

浏览器访问地址、Keycloak client 配置、oauth2-proxy issuer、Harbor OIDC endpoint 应尽量使用同一套主机名体系。

### 2. Windows `hosts` 需要单独维护

一键安装默认只维护当前 Linux 主机的 `hosts`。如果浏览器运行在 Windows 宿主机，你还需要把 `.env` 中当前各个 `*_PUBLIC_HOST` 加到 Windows `hosts`。

### 3. `localhost` 与 IP 只选一套对外口径

如果 `.env` 已改成域名或 WSL2 IP，就不要再在 OIDC 相关回调里混用 `localhost`。

## 相关文档

- `harbor/README.md`：Harbor 模块单独说明
- `docs/requirements/`：已冻结的需求文档
- `docs/plans/`：实现计划与执行拆解
