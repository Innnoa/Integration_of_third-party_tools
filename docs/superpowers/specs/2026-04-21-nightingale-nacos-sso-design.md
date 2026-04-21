# 夜莺与 Nacos 一体化登录设计稿

状态：draft-approved-in-chat  
日期：2026-04-21  
适用项目：`/home/zazaki/Projects/Integration_of_third-party_tools`

## 1. 目标

在当前统一入口与 Keycloak 体系下，新增两个服务：

- 夜莺（Nightingale）
- Nacos

并满足以下要求：

- 并入当前主 `compose.yml`
- 通过现有统一入口网关暴露
- 使用现有 Keycloak 作为统一登录中心
- 首版只打通登录，不做自动角色映射
- 同步接入当前业务面板

## 2. 交付物

本次实现应至少包含：

- 主 `compose.yml` 中新增 Nacos 与夜莺相关服务
- `.env.example` 中新增对应公开主机名与服务配置项
- `gateway/nginx.conf` 增加两条主机名转发规则
- `scripts/bootstrap-keycloak.sh` 增加 `nacos` 与 `nightingale` client 的刷新逻辑
- 对应服务配置文件或环境变量模板
- `business_panel` 中新增两个业务单元、入口与状态探测
- README 中新增这两个服务的统一入口与登录说明

## 3. 非目标

首版不包含以下内容：

- 从 Keycloak 自动映射夜莺或 Nacos 的角色/团队/管理员权限
- 细粒度 RBAC 打通
- 复杂组织架构同步
- 多实例高可用部署
- HTTPS 和证书发放

## 4. 设计结论

两者都采用 **原生 OIDC**，不通过 `oauth2-proxy` 前置。

原因：

- Nacos 已有官方 OIDC 方案
- 夜莺已支持原生 OIDC 单点登录
- 当前目标仅为“登录打通”，不需要额外引入代理层
- 对控制台类产品而言，原生接入更直接，也更容易后续继续扩展

## 5. 接入后的统一入口

在现有统一入口基础上增加：

- `http://nacos.localhost`
- `http://nightingale.localhost`

当前统一主机名集合将扩展为：

- `auth.localhost`
- `portainer.localhost`
- `kafka.localhost`
- `redis.localhost`
- `pma.localhost`
- `mongo.localhost`
- `harbor.localhost`
- `nacos.localhost`
- `nightingale.localhost`

## 6. 服务编排结构

### 6.1 Nacos 组

首版建议包含：

- `nacos`
- `nacos-mysql`

原因：

- 首版希望以稳定可用为先
- 直接采用 MySQL 模式更接近长期可保留结构
- 比内嵌存储更稳，后续迁移成本更低

公开入口：

- `nacos.localhost -> nacos`

### 6.2 夜莺组

首版建议包含：

- `nightingale`
- `nightingale-mysql`
- `nightingale-redis`

原因：

- 夜莺不是简单静态 Web 服务
- 为避免与现有业务 Redis 混用带来状态污染，首版先给夜莺独立依赖
- 后续如需收敛依赖，再单独评估

公开入口：

- `nightingale.localhost -> nightingale-web`

## 7. Keycloak 集成策略

### 7.1 Nacos

需要新增 Keycloak client：

- `client_id = nacos`

首版要求：

- 公开入口：`http://nacos.localhost`
- issuer：`http://auth.localhost/realms/infra`
- redirect URI：按 Nacos OIDC 插件所需路径配置为 `nacos.localhost`
- 登录必须通过 Keycloak 完成

首版验收标准：

- 能从 `nacos.localhost` 跳转到 Keycloak
- 登录成功后回到 Nacos

### 7.2 夜莺

需要新增 Keycloak client：

- `client_id = nightingale`

首版要求：

- 公开入口：`http://nightingale.localhost`
- SSO / issuer 地址指向 `http://auth.localhost/realms/infra`
- redirect URL：`http://nightingale.localhost/callback`
- 登录必须通过 Keycloak 完成

首版验收标准：

- 能从 `nightingale.localhost` 跳转到 Keycloak
- 登录成功后回到夜莺

## 8. 权限策略

首版明确只做 **登录打通**。

不做：

- Keycloak group 到 Nacos 角色映射
- Keycloak role 到夜莺团队/角色映射
- 自动提升管理员权限

当前建议：

- 各系统内部管理员和权限先手工配置
- 先确保 SSO 成功
- 角色映射作为后续独立迭代

## 9. 网关改动

`gateway/nginx.conf` 需要新增两段：

- `nacos.localhost`
- `nightingale.localhost`

要求：

- 与现有主机名路由保持同一风格
- 不修改现有旧路由语义
- 继续通过 Host 分流，不走路径前缀

## 10. 面板接入

业务面板要新增两个业务单元：

- `nacos`
- `nightingale`

首版接入规则：

- 提供直达链接
- 提供容器状态
- 提供入口状态
- 认证状态只验证“是否出现预期 OIDC 跳转”，不做更深业务验证

推荐和现有 `KafkaUI` 接入方式保持一致。

## 11. 配置策略

建议新增这些环境变量：

- `NACOS_PUBLIC_HOST=nacos.localhost`
- `NIGHTINGALE_PUBLIC_HOST=nightingale.localhost`

根据实际镜像与配置需求，进一步补充：

- Nacos 数据库连接参数
- 夜莺数据库连接参数
- 夜莺 Redis 连接参数
- 各自的 OIDC client id / secret

## 12. 实施顺序

推荐顺序：

1. 新增 `.env.example` 配置项
2. 在主 `compose.yml` 中加入 Nacos 与夜莺服务
3. 更新 `gateway/nginx.conf`
4. 配好服务自身的 OIDC 配置
5. 扩展 `scripts/bootstrap-keycloak.sh`
6. 接入 `business_panel`
7. 更新 README
8. 做端到端验证

## 13. 验收标准

满足以下条件时可认为首版完成：

1. `nacos.localhost` 能打开
2. `nightingale.localhost` 能打开
3. 两者都能正常跳转到 `auth.localhost`
4. 两者登录成功后能回到各自系统
5. 业务面板能显示这两个服务
6. 面板内能看到这两个服务的入口与基础状态
7. 全量配置校验与自动化测试通过

## 14. 风险与注意事项

- 不同版本的 Nacos / 夜莺镜像，其 OIDC 配置项可能存在差异，实施前需按当前版本文档核对
- 首版不做角色映射，因此“能登录”不等于“权限已合理配置”
- 夜莺独立 Redis 会增加一组运行依赖，但可降低与现有栈互相影响的风险
- 当前目录不是 git 仓库外的临时实验环境，本次设计仅保存文档，不执行提交流程以外的额外变更

## 15. 冻结决策

本设计确认后的冻结结论如下：

- 夜莺与 Nacos 都并入当前主 `compose.yml`
- 两者都通过现有 `gateway` 暴露统一入口
- 两者都接现有 Keycloak
- 首版只打通登录，不做角色映射
- 两者都接入当前业务面板
