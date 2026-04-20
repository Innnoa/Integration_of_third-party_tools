# 一键安装脚本设计稿

状态：draft-approved-in-chat  
日期：2026-04-20  
适用项目：`/home/zazaki/Projects/Integration_of_third-party_tools`

## 1. 目标

为当前项目补一个统一安装入口，让别人拿到完整项目目录后，可以通过一个脚本尽量完成：

- 环境检查
- 生成或补齐 `.env`
- 启动主栈
- 安装并接入 Harbor
- 刷新 Keycloak clients
- 启动业务面板
- 输出统一入口地址与后续检查提示

脚本目标是“尽量一键可用”，不是承诺在任何主机上零前置条件百分之百成功。

## 2. 交付物

本次设计对应的实现交付物应包含：

- 根目录统一入口脚本 `install.sh`
- 对现有 `scripts/*.sh` 的最小必要增强
- 对 `.env.example` 的最小必要增强
- README 中新增安装脚本说明
- 对应测试或至少静态验证与人工验收记录

## 3. 前提与边界

### 3.1 已知前提

安装脚本依赖以下事实成立：

- 项目完整目录会一起交付，不是只发 `compose.yml`
- Harbor installer 包会一起带上
- Docker 与 Docker Compose 已安装
- 当前用户有权限访问 Docker
- Windows `hosts` 需要由用户手动补，不由脚本代写

### 3.2 非目标

本轮不包含以下内容：

- 自动写入 Windows `hosts`
- 自动安装 Docker / Docker Compose
- 自动申请管理员权限
- 自动生成 HTTPS 证书
- 自动修复所有 Harbor 内部异常状态
- 自动把业务面板改成 Docker 容器

## 4. 设计结论

采用 `总控脚本 + 复用现有脚本` 方案。

具体做法：

- 新增根目录 `install.sh` 作为唯一安装入口
- 底层尽量复用现有：
  - `scripts/prepare-env.sh`
  - `scripts/init-network.sh`
  - `scripts/up-main.sh`
  - `scripts/prepare-harbor.sh`
  - `scripts/bootstrap-keycloak.sh`
  - `scripts/services.sh`
  - `scripts/panel.sh`

不采用“全新重写一套安装逻辑”的原因：

- 当前项目已有真实跑通过的脚本链路
- 复用现有逻辑风险更低
- 更便于后续维护和排障

## 5. 阶段结构

`install.sh` 采用固定阶段执行：

1. `preflight`
2. `env`
3. `network`
4. `main_stack`
5. `harbor_prepare`
6. `harbor_install`
7. `bootstrap`
8. `panel`

### 5.1 `preflight`

职责：

- 检查 `docker`
- 检查 `docker compose`
- 检查当前用户是否可访问 Docker
- 检查 `harbor/installer/` 是否存在
- 检查必要模板与配置文件是否存在
- 提示用户手动补 Windows `hosts`

### 5.2 `env`

职责：

- 若无 `.env`，基于 `.env.example` 生成
- 自动生成密码和 secret
- 写入统一入口相关主机名：
  - `KEYCLOAK_PUBLIC_HOST`
  - `PORTAINER_PUBLIC_HOST`
  - `KAFKA_UI_PUBLIC_HOST`
  - `REDISINSIGHT_PUBLIC_HOST`
  - `PHPMYADMIN_PUBLIC_HOST`
  - `MONGO_EXPRESS_PUBLIC_HOST`
  - `HARBOR_PUBLIC_HOST`
- 保留用户已存在的自定义值

### 5.3 `network`

职责：

- 调用 `scripts/init-network.sh`

### 5.4 `main_stack`

职责：

- 启动主栈
- 确保至少以下服务可用：
  - `gateway`
  - `keycloak-postgres`
  - `keycloak`
  - `portainer`
  - `kafka-ui`
  - 三个 `oauth2-proxy`

### 5.5 `harbor_prepare`

职责：

- 调用 `scripts/prepare-harbor.sh`
- 让 Harbor 模板与当前 `.env` 对齐

### 5.6 `harbor_install`

职责：

- 执行 Harbor 官方安装流程
- 确保 Harbor 按当前 `harbor.localhost` 等配置生成运行文件

### 5.7 `bootstrap`

职责：

- 调用 `scripts/bootstrap-keycloak.sh`
- 刷新 Keycloak realm/client/groups/user
- 刷新 redirect URI 与 web origins

### 5.8 `panel`

职责：

- 启动 `business_panel`
- 输出面板访问地址

## 6. 可重复执行策略

安装脚本必须支持 `可重复执行`。

### 6.1 幂等规则

- `.env` 已存在：
  - 不覆盖已有密码和 secret
  - 只补缺失键
- Docker 网络已存在：
  - 直接跳过
- 主栈已运行：
  - 不强制重建
- Harbor 已安装：
  - 默认做校验和必要更新
  - 不自动强制重装
- Keycloak bootstrap：
  - 允许重复执行
- 面板已运行：
  - 默认跳过

### 6.2 模式建议

- 默认模式：`安全幂等`
- 修复模式：`--repair`

`--repair` 用于：

- 对齐配置
- 尝试重跑关键阶段
- 修复运行态偏差

## 7. 输入输出约定

### 7.1 输入

推荐支持：

```bash
./install.sh
./install.sh --repair
./install.sh --skip-panel
./install.sh --skip-harbor
```

说明：

- `--repair`
  - 对齐并修复已有安装
- `--skip-panel`
  - 跳过业务面板启动
- `--skip-harbor`
  - 仅用于开发调试，不作为默认外发路径

### 7.2 输出

脚本输出必须分三层：

#### 阶段日志

例如：

- `[1/8] preflight`
- `[2/8] env`
- `[3/8] network`

#### 阶段结果

只允许：

- `OK`
- `SKIP`
- `FAIL`

#### 结束摘要

安装完成后必须打印：

- 统一入口地址
- 面板地址
- Kafka broker 地址
- 手动补 `hosts` 提示
- 后续检查清单

## 8. 推荐输出内容

脚本完成后推荐输出：

- `http://auth.localhost`
- `http://portainer.localhost`
- `http://kafka.localhost`
- `http://redis.localhost`
- `http://pma.localhost`
- `http://mongo.localhost`
- `http://harbor.localhost`
- `http://127.0.0.1:8090`
- `PUBLIC_HOST:9092`

以及：

```text
Next:
1. 在 Windows hosts 中添加 *.localhost
2. 打开 http://auth.localhost
3. 打开 http://portainer.localhost
4. 打开 http://harbor.localhost
```

## 9. 与现有项目结构的关系

当前项目不是“单 compose 文件即可交付”的结构。

安装脚本必须假设这些内容一起交付：

- `compose.yml`
- `.env.example`
- `gateway/`
- `kafka-ui/`
- `oauth2-proxy/`
- `scripts/`
- `business_panel/`
- `harbor/`
- `README.md`

因此对外推荐的交付方式是：

- 整个项目目录
- 外加一个根目录 `install.sh`

不推荐：

- 只发 `compose.yml`
- 只发脚本

## 10. 风险与注意事项

- Windows `hosts` 仍需人工维护
- Harbor installer 依赖官方生成路径，权限问题可能影响重复执行
- Docker 拉镜像可能受代理或网络影响
- 若旧 `.env` 值与当前统一入口方案冲突，脚本应提示，而不是静默覆盖
- 当前目录不是 git 仓库，无法按“写完设计文档即提交”流程执行，本次仅保存文档

## 11. 冻结决策

本设计确认后的冻结结论如下：

- Harbor 是安装脚本必选项，不再作为可选服务
- Harbor installer 会一起交付
- 密码和 secret 默认自动生成
- Windows `hosts` 只提示用户手动补，不由脚本代写
- 安装脚本必须支持可重复执行
- 实现路径采用“总控脚本 + 复用现有脚本”
