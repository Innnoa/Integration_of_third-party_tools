# 2026-04-21 Nacos Keycloak Login Design

## 1. 背景

当前仓库已经接入了 Nacos 3.2.1 与 Keycloak 的基础 OIDC 配置，但登录闭环还没有被验证为稳定可用。

现有证据：

- `nacos/application.properties` 已启用 `nacos.core.auth.system.type=oidc`
- `nacos/application.properties` 已配置 `issuer-uri=http://auth.localhost/realms/infra`
- `nacos/application.properties` 已配置 `client-id=nacos`
- `scripts/bootstrap-keycloak.sh` 已创建 `client_id=nacos`
- 运行态验证显示 `http://nacos.localhost/` 会先跳到 `/next/`
- 运行态验证显示 `nacos` 的 API 服务运行在 `8848`，Console 运行在 `8080`
- 运行态验证显示 `http://nacos.localhost/next/` 能返回 Nacos Console HTML

这说明当前问题不是“完全没有 Keycloak 配置”，而是“需要把 Nacos 3.2.1 Console 的真实登录入口、Keycloak client 配置、统一公开入口三者对齐”，让用户稳定从 `http://nacos.localhost/` 发起登录并回到 Nacos。

## 2. 目标

本次只交付一件事：

- 打通 `http://nacos.localhost/ -> Keycloak -> 回到 Nacos Console` 的登录链路

明确不做：

- 单点退出联动
- 角色/组映射
- 细粒度权限模型
- 新增 `oauth2-proxy`

## 3. 约束

- 对外固定入口必须是 `http://nacos.localhost/`
- 认证架构继续使用 Nacos 原生 OIDC，不新增第二套认证代理
- Keycloak 继续使用当前 `auth.localhost` 与 `infra` realm
- 修改范围尽量收敛到 Nacos 配置、Keycloak bootstrap、必要的 gateway 兼容规则、以及对应测试
- 不能覆盖其他 AI 正在改的无关文件内容

## 4. 方案比较

### 方案 A：继续使用 Nacos 原生 OIDC，修正登录回跳链路

做法：

- 保留 Nacos 现有 OIDC 配置
- 以运行态实际入口 `/next/` 为准校准 Nacos 登录入口行为
- 校准 Keycloak `nacos` client 的 redirect URI 与 public origin
- 补回归测试验证 `nacos.localhost` 的登录跳转

优点：

- 与仓库当前实现最一致
- 修改面最小
- 不引入新的认证组件

缺点：

- 需要基于当前 Nacos 3.2.1 Console 的真实行为做一次精确校准

### 方案 B：在 Nacos 前叠加 `oauth2-proxy`

做法：

- 让 gateway 不直接进 Nacos，而是先进 `oauth2-proxy`
- Keycloak 登录由 `oauth2-proxy` 负责

优点：

- 和 RedisInsight/phpMyAdmin 一类服务模式统一

缺点：

- 与现有 Nacos 原生 OIDC 重叠
- 复杂度更高
- 会引入新的回调与 cookie 问题

### 方案 C：只做网关跳转兼容，不调整 Keycloak client

做法：

- 通过 Nginx 把多个旧入口重写到当前 Console 路径
- 不校准 Keycloak client

优点：

- 改动很快

缺点：

- 只能修页面入口，不保证登录回跳正确
- 后续版本漂移时容易再次失效

## 5. 选型

采用方案 A。

理由：

- 当前仓库已经具备 Nacos 原生 OIDC 的基础配置
- 用户这次只要求打通登录闭环，不需要新增认证层
- 目标入口明确为 `http://nacos.localhost/`，适合通过最小配置修复完成

## 6. 设计

### 6.1 公开入口

- 浏览器公开入口固定为 `http://nacos.localhost/`
- `gateway/nginx.conf` 保持 `nacos.localhost -> nacos:8080`
- 若当前 Console 的稳定入口不是根路径，则 gateway 只做最小兼容跳转，把旧入口收敛到当前 Console 入口

### 6.2 Nacos 认证

- 继续使用 `nacos/application.properties` 的 OIDC 配置
- `issuer-uri` 继续指向 `http://auth.localhost/realms/infra`
- `client-id` 保持 `nacos`
- `client-secret` 保持由本地开发环境默认值驱动
- 以 Nacos 3.2.1 当前 Console 行为为准，确保未登录访问时会进入 Keycloak 授权流程

### 6.3 Keycloak Client

- `scripts/bootstrap-keycloak.sh` 中的 `nacos` client 继续作为唯一认证客户端
- redirect URI 配置需要与运行态实际登录回跳路径一致
- web origin 继续以 `http://nacos.localhost` 为准
- 若当前宽泛 `/*` 无法稳定闭环，则收敛到运行态真实回跳地址

### 6.4 测试与验收

代码级验证需要覆盖：

- `nacos/application.properties` 的 OIDC 关键配置仍存在
- `scripts/bootstrap-keycloak.sh` 中 `nacos` client 的 redirect URI / origin 与设计一致
- `gateway` 对 `nacos.localhost` 的入口行为与当前 Console 入口一致

运行态验收需要覆盖：

1. 打开 `http://nacos.localhost/`
2. 未登录时进入 Keycloak 登录页
3. 登录成功后回到 Nacos Console

## 7. 影响文件

- `nacos/application.properties`
- `scripts/bootstrap-keycloak.sh`
- `gateway/nginx.conf`
- `tests/test_probes.py`
- `tests/test_nacos_nightingale_compose.py`
- `README.md`（仅在访问说明需要更新时）

## 8. 风险

- Nacos 3.2.1 Console 使用 `/next/` 作为前端入口，真实登录发起点可能不是简单的服务端 302，而是前端脚本驱动
- Keycloak 当前 `nacos` client 已经使用宽泛 redirect URI，单靠静态配置检查不足以证明登录闭环真实可用
- 如果当前镜像后续再漂移，入口路径可能变化，因此需要让测试同时覆盖“公开入口”和“Keycloak client 配置”

## 9. 最终交付标准

满足以下三条才算完成：

- `http://nacos.localhost/` 可作为唯一公开入口
- 访问该入口时，未登录用户能被正确引导到 `auth.localhost`
- 登录完成后，浏览器能回到可用的 Nacos Console 页面
