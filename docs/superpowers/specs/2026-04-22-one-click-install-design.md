# 真正一键安装设计稿

状态：draft-approved-in-chat  
日期：2026-04-22  
适用项目：`/home/zazaki/Projects/Integration_of_third-party_tools`

## 1. 目标

把当前项目的安装入口补到“单命令完成本机可用”的程度。

目标命令形态：

```bash
sudo ./install.sh --base-domain example.internal
```

执行完成后，目标 Linux 主机应尽量自动完成：

- 预检安装条件
- 生成或补齐 `.env`
- 自动派生各服务域名
- 自动维护本机 `/etc/hosts`
- 启动主栈
- 修复 phpMyAdmin 自动登录账号
- 刷新 Keycloak realm / groups / clients / 测试用户
- 自动初始化 Portainer 并写入 OAuth 配置
- 启动业务面板
- 执行安装后验收并输出结果摘要

本轮目标是“任意 Linux 主机上本机浏览器可完成统一登录闭环”，不是“任何网络环境下无条件自动对外提供服务”。

## 2. 交付物

本次设计对应实现后应至少包含：

- 增强后的根目录安装入口 `install.sh`
- 增强后的 `scripts/install-lib.sh`
- 一个新的安装辅助脚本，用于 hosts、IP 探测或 Portainer API 自动化
- README 中的一键安装说明更新
- 对应自动化测试
- 安装后的统一验收输出

## 3. 前提与边界

### 3.1 已知前提

一键安装依赖以下条件成立：

- 目标系统是 Linux
- 当前用户具备 `sudo` 权限
- Docker 与 Docker Compose 已安装
- 当前用户有权限访问 Docker
- 安装命令会显式传入 `--base-domain`
- Harbor 默认不安装；只有显式 `--with-harbor` 才进入 Harbor 路径

### 3.2 非目标

本轮不包含以下内容：

- 自动安装 Docker / Docker Compose
- 自动申请 TLS 证书
- 自动配置外部 DNS
- 自动让局域网其他机器获得域名解析
- 自动处理 Windows 宿主机 `hosts`
- 自动修复所有 Harbor 内部运行异常
- 自动做多机部署或高可用

## 4. 设计结论

采用 `单命令总控脚本 + 复用现有脚本 + 少量新增自动化` 方案。

保留并继续复用：

- `scripts/init-network.sh`
- `scripts/up-main.sh`
- `scripts/repair-mariadb-phpmyadmin-user.sh`
- `scripts/bootstrap-keycloak.sh`
- `scripts/panel.sh`
- `scripts/check-main.sh`

新增自动化能力只补当前链路中真正缺失的部分：

- `--base-domain` / `--public-ip` 参数
- 自动派生域名并写入 `.env`
- 自动写入本机 `/etc/hosts`
- 自动初始化并配置 Portainer OAuth
- 自动执行安装后验收

不采用“重写整套安装流程”的原因：

- 当前脚本链路已经被仓库测试覆盖
- 现有 Keycloak / oauth2-proxy / Nacos / Nightingale 路径已经稳定
- 需要补的是环境输入与 Portainer 集成，而不是替换整套安装架构

## 5. 输入与参数接口

### 5.1 必填参数

安装脚本新增必填参数：

- `--base-domain`

例如：

```bash
sudo ./install.sh --base-domain example.internal
```

脚本不再把“用户先手工修改 `.env.example` 占位值”作为一键安装前提。

### 5.2 可选参数

保留或新增以下参数：

- `--public-ip 192.168.1.10`
- `--skip-panel`
- `--with-harbor`
- `--skip-harbor`
- `--repair`

参数含义：

- `--public-ip`
  - 明确指定对外地址
- `--skip-panel`
  - 跳过业务面板启动
- `--with-harbor`
  - 显式启用 Harbor prepare / install
- `--skip-harbor`
  - 保留兼容；在当前默认行为下等价于显式确认跳过 Harbor
- `--repair`
  - 在已有安装上重跑自动修复与验收逻辑

## 6. 域名与地址模型

### 6.1 自动派生规则

当用户传入：

```bash
--base-domain example.internal
```

脚本自动派生：

- `auth.example.internal`
- `portainer.example.internal`
- `kafka.example.internal`
- `redis.example.internal`
- `pma.example.internal`
- `mongo.example.internal`
- `nacos.example.internal`
- `nightingale.example.internal`

Harbor 仅在 `--with-harbor` 时派生：

- `harbor.example.internal`

### 6.2 `PUBLIC_HOST` 与 Kafka 广播地址

脚本写入：

- `PUBLIC_HOST=<public-ip>`
- `KAFKA_HOST_BOOTSTRAP_SERVER=<public-ip>:9092`

原因：

- 浏览器侧统一入口继续使用派生域名
- Kafka 宿主机广播地址仍必须使用真实可达 IP

### 6.3 `public-ip` 决定规则

优先级：

1. 用户显式传入 `--public-ip`
2. 自动探测默认出口 IPv4
3. 若探测失败则直接报错并停止

自动探测应使用稳定且脚本化可实现的方式，例如基于默认路由选择的源地址，而不是随意取第一块网卡。

## 7. `.env` 生成与补齐策略

### 7.1 自动写入内容

脚本在 `.env` 中自动确保以下值存在且正确：

- `PUBLIC_SCHEME`
- `PUBLIC_HOST`
- `BROWSER_HOST`
- `KEYCLOAK_PUBLIC_HOST`
- `PORTAINER_PUBLIC_HOST`
- `KAFKA_UI_PUBLIC_HOST`
- `REDISINSIGHT_PUBLIC_HOST`
- `PHPMYADMIN_PUBLIC_HOST`
- `MONGO_EXPRESS_PUBLIC_HOST`
- `NACOS_PUBLIC_HOST`
- `NIGHTINGALE_PUBLIC_HOST`
- `KAFKA_HOST_BOOTSTRAP_SERVER`
- `BUSINESS_PANEL_HOST`
- `BUSINESS_PANEL_PORT`

在启用 Harbor 时额外确保：

- `HARBOR_PUBLIC_HOST`

其中：

- `BROWSER_HOST` 默认保持 `localhost`
- 若用户已有自定义值，则保留现有值

### 7.2 幂等规则

- `.env` 不存在：基于 `.env.example` 生成
- `.env` 已存在：
  - 不覆盖已有密码和 secret
  - 只覆盖当前安装脚本负责管理的域名与地址字段
  - 只补缺失键
- 占位 secret 若仍是示例值，可继续按现有逻辑自动替换成随机值

## 8. 本机 `/etc/hosts` 自动维护

### 8.1 目标

让目标 Linux 主机的本机浏览器在安装完成后，直接可以访问派生域名。

### 8.2 写入策略

脚本使用带标记块的方式维护 `/etc/hosts`，例如：

- `# BEGIN integration_of_third-party_tools`
- `# END integration_of_third-party_tools`

块内写入当前派生域名到 `<public-ip>` 的映射。

幂等要求：

- 重跑时替换整个标记块
- 不无限追加重复条目
- 不修改标记块以外的用户自定义内容

### 8.3 权限处理

因为 `/etc/hosts` 需要管理员权限，目标使用方式固定为：

```bash
sudo ./install.sh --base-domain example.internal
```

不在脚本内部再二次提权。

## 9. Portainer 自动化

### 9.1 问题定义

当前仓库只会在 Keycloak 侧创建 `portainer` client，但 Portainer 自身 OAuth 配置仍需手工进入 Web UI 写入，因此无法称为真正一键。

### 9.2 设计结论

安装脚本在主栈启动并确认 Portainer 可达后，通过 Portainer 官方 API 自动完成：

- 首次管理员初始化
- 管理员登录获取 token
- 写入 OAuth 配置

### 9.3 自动配置内容

Portainer 最终应被脚本写成：

- 保留本地管理员登录入口
- 启用 OAuth
- `Client ID = portainer`
- `Client Secret = PORTAINER_CLIENT_SECRET`
- `Authorization URL = http://auth.<base-domain>/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth`
- `Access Token URL = http://auth.<base-domain>/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`
- `Resource URL = http://auth.<base-domain>/realms/${KEYCLOAK_REALM}/protocol/openid-connect/userinfo`
- `Logout URL = http://auth.<base-domain>/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout`
- `Redirect URL = http://portainer.<base-domain>/`
- `Scopes = openid profile email groups`
- `Auto create users = on`

### 9.4 幂等规则

- 未初始化实例：先走管理员初始化
- 已初始化实例：直接登录并刷新 OAuth 配置
- `--repair` 模式下允许再次强制对齐 OAuth 设置

## 10. 安装阶段

安装脚本保持固定阶段输出，推荐仍为 9 段：

1. `preflight`
2. `env`
3. `network`
4. `main_stack`
5. `phpmyadmin_user_repair`
6. `harbor_prepare`
7. `harbor_install`
8. `bootstrap`
9. `panel`

在当前默认行为下：

- `harbor_prepare` 默认 `SKIP`
- `harbor_install` 默认 `SKIP`

同时新增一个安装后验收步骤，但它可以作为 `panel` 之后的收尾逻辑，不强制改动已有阶段编号。

## 11. 预检与失败处理

### 11.1 预检内容

脚本应在 `preflight` 阶段检查：

- `docker` 是否存在
- `docker compose` 是否存在
- 当前用户是否可访问 Docker
- 传入的 `--base-domain` 是否非空
- 若启用 Harbor，`harbor/installer/install.sh` 是否存在
- 必要脚本和模板是否存在

### 11.2 失败策略

不做激进的自动回滚，不删除容器、不删卷。

采用：

- 阶段失败即停止
- 输出失败阶段名
- 输出失败命令或失败 API
- 输出建议的 `--repair` 重跑方式

原因：

- 当前项目状态机并不简单
- 自动回滚数据卷与运行态风险高
- 对调试而言，保留失败现场更有价值

## 12. 安装后验收

### 12.1 验收内容

脚本在安装完成前自动执行：

- `docker compose config` 解析检查
- 主栈 `docker compose ps` 检查
- Keycloak realm / groups / clients / 测试用户检查
- Portainer API 可登录与 OAuth 配置存在性检查
- 以下入口的未登录跳转检查：
  - `kafka.<base-domain>`
  - `redis.<base-domain>`
  - `pma.<base-domain>`
  - `mongo.<base-domain>`
  - `nacos.<base-domain>`
  - `nightingale.<base-domain>`

验收预期：

- 这些入口至少应出现 Keycloak 或 OAuth2 Proxy 跳转证据

### 12.2 结束摘要

脚本最终输出应包含：

- 当前派生的全部域名
- 当前 `PUBLIC_HOST` / Kafka broker 地址
- `/etc/hosts` 写入结果
- 各核心阶段是 `OK / SKIP / FAIL`
- 验收结果中哪些服务 `ready`
- 哪些服务 `degraded`

## 13. 非目标中的显式保留项

即使补成真正一键，以下内容仍明确不做：

- 让局域网其他机器自动获得解析能力
- 自动配置防火墙 / 路由 / 端口映射
- 自动签发 HTTPS 证书
- 自动把 Harbor 改成默认安装路径

## 14. 设计后的预期结果

在满足 Linux + sudo + Docker + Compose 前提下，用户只需要：

```bash
sudo ./install.sh --base-domain example.internal
```

即可在本机得到：

- 可访问的统一域名入口
- 已写入本机 `/etc/hosts` 的域名映射
- 已完成 Keycloak bootstrap 的登录链路
- 已完成 Portainer OAuth 配置的管理界面
- 安装后可直接查看的验收摘要

这时项目才可以被称为“面向目标 Linux 主机本机使用场景的真正一键安装”。
