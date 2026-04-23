# 2026-04-23 install.sh 治理 Requirement

## 背景

当前项目已经具备基础一键安装能力，但安装逻辑仍偏“脚本串联”：

- 对依赖、环境、启动顺序、初始化、修复、验收的治理不够统一
- 失败后的自动修复、自愈重试、降级判定还不完整
- 成功标准需要从“服务起来”收敛到“关键登录链可用”

本次需求目标是把 `install.sh` 收敛为唯一对外安装入口，统一承载安装、修复、配置、验收与结果汇总。

## 目标

- 保持 `install.sh` 为唯一对外入口
- 默认采用“先自愈、后失败”的执行策略
- 尽量兼容更泛化的 Linux 发行版，不只针对 `WSL2 + Arch Linux`
- 在需要时允许自动使用 `sudo` 安装依赖
- 默认只改当前用户本机环境，不改 `systemd`、防火墙、开机自启等系统级持久配置
- 安装成功标准升级为：
  - 关键服务启动
  - 主入口可访问
  - 关键登录跳转正确

## 非目标

- 不重构为新的独立安装器产品
- 不把安装主流程迁移为新的 systemd 服务管理体系
- 不自动删除业务数据、卷或数据库
- 不自动覆盖用户已经明确设置的密码、域名、client secret 等关键配置
- 不默认操作项目之外的 Docker 资源

## 总体架构

`install.sh` 仍是唯一入口，内部按阶段调度现有脚本与辅助程序，例如：

- `scripts/init-network.sh`
- `scripts/up-main.sh`
- `scripts/bootstrap-keycloak.sh`
- `scripts/install_helper.py`

整体改造方向不是推翻现有资产，而是在 `install.sh` 中建立统一阶段模型，使每个阶段都具备：

- 前置条件
- 执行动作
- 自愈动作
- 重试次数
- 成功判据

安装最终输出必须归一到 3 种状态：

- `success`
- `degraded`
- `failed`

## 阶段模型

建议把安装流程固定为以下 10 个阶段：

1. `preflight`
2. `deps`
3. `env`
4. `network`
5. `start`
6. `bootstrap`
7. `configure`
8. `repair`
9. `verify`
10. `summary`

### 1. preflight

负责检测：

- 发行版类型
- Shell、`docker`、`docker compose`、`python3`、`sudo`
- 基本网络可达性
- 关键端口占用
- 当前目录与文件权限

策略：

- 缺依赖时自动进入 `deps`
- 对已存在的容器、网络、卷仅做记录，不立即判错

### 2. deps

负责自动安装项目所需依赖。

支持优先识别：

- `apt`
- `dnf`
- `yum`
- `pacman`
- `zypper`

策略：

- 允许自动使用 `sudo`
- 只安装当前项目必需依赖
- 不修改 `systemd`、防火墙或开机启动项
- 安装失败时输出已尝试命令与失败点

### 3. env

负责生成或修复 `.env`：

- 补默认值
- 替换占位 secret
- 自动生成随机密码
- 派生 `*_PUBLIC_HOST`
- 计算当前主机 IP

策略：

- 只补缺或替换占位值
- 不覆盖用户已有明确配置
- 校验关键变量之间的一致性

### 4. network

负责创建或修复项目 Docker 网络。

策略：

- 网络已存在时直接复用
- 网络异常时只处理当前项目网络
- 不清理项目外网络

### 5. start

负责启动主栈服务。

策略：

- 对镜像拉取失败、服务未 ready、短暂端口冲突做有限次重试
- 不做破坏性清理
- 只调用已知安全修复路径

### 6. bootstrap

负责初始化统一认证与基础对象：

- Keycloak realm
- groups
- clients
- test user

策略：

- 已存在对象做更新，不重复创建
- 区分未 ready、凭据不匹配、对象冲突等失败类型

### 7. configure

负责安装后配置写入：

- Portainer 原生 OIDC
- Nightingale 配置渲染
- 后续如 Harbor 等需要安装后写配置的服务

策略：

- 重复执行时按目标配置对齐
- 不依赖“首次安装”状态

### 8. repair

负责执行内建的已知问题修复，例如：

- 首次启动顺序问题
- 账号或配置漂移问题
- 已有 repair 脚本能覆盖的问题

策略：

- 只修已知、可回放、无破坏的故障
- 不做不透明的 destructive 操作

### 9. verify

负责最终验收。

成功标准必须覆盖：

- 关键容器状态
- 关键入口可访问
- 关键登录跳转正确

首批关键对象固定为：

- `Keycloak`
- `Portainer`
- `Nightingale`
- `Nacos`

建议验收口径：

- `Keycloak`：OIDC metadata 可读
- `Portainer`：入口可进入正确 OIDC/Keycloak 登录链
- `Nightingale`：入口可进入正确 OIDC/Keycloak 登录链
- `Nacos`：入口可进入 `oauth2-proxy -> Keycloak` 登录链

### 10. summary

负责输出统一结果摘要：

- 总状态：`success / degraded / failed`
- 各阶段状态
- 各关键服务验证结果
- 已执行修复动作
- 失败阶段与建议排查点

## 幂等与自愈边界

### 必须幂等

- `.env` 生成与补全
- Keycloak realm / group / client / user 初始化
- Portainer OIDC 写入
- Nightingale 配置渲染
- Docker 网络创建
- 验证阶段

### 允许自动修复

- 缺依赖时自动安装
- 占位 secret 自动替换
- 启动顺序导致的临时失败自动重试
- 已知可恢复问题自动修复
- 入口未 ready 但容器已启动时等待并重试

### 明确禁止自动乱动

- 不自动删卷、清库、重置业务数据
- 不自动改 `systemd`、防火墙、开机自启
- 不自动执行 `docker compose down -v`
- 不自动覆盖用户自定义域名、密码、client secret
- 不自动处理项目外 Docker 资源

统一边界原则：

> 只允许自动执行可重复、可回放、不会破坏已有数据的修复动作。

## 完成定义

### Success

同时满足以下条件：

- 关键容器已运行并通过基本健康检查
- 关键入口可访问
- 关键登录跳转正确

### Degraded

主目标可用，但存在非关键问题，例如：

- 可选组件失败
- 面板未启动但主服务正常
- 非关键入口验证失败

### Failed

以下任一情况成立：

- 关键容器无法启动
- 关键入口不可访问
- 关键登录跳转不正确
- 关键初始化失败且自动修复后仍失败

## 验收结论

本次安装器治理的最低成功标准定义为：

> `install.sh` 成功 = 核心服务启动 + 主入口可访问 + Portainer / Nightingale / Nacos 登录链正确。
