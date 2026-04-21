# phpMyAdmin 固定账号自动登录设计稿

状态：draft-approved-in-chat  
日期：2026-04-21  
适用项目：`/home/zazaki/Projects/Integration_of_third-party_tools`

## 1. 目标

在当前 `Keycloak + oauth2-proxy + phpMyAdmin + MariaDB` 链路上，把 phpMyAdmin 从“SSO 后仍需二次输入数据库账号密码”改为：

- 先通过统一登录完成外层身份认证
- 仅允许 `platform-admins` 组成员进入 phpMyAdmin
- 进入后自动使用固定 MariaDB 专用管理账号登录
- 不再展示 phpMyAdmin 原生用户名/密码登录页
- 非授权组成员访问时直接返回 `403`

## 2. 交付物

本次实现应至少包含：

- `.env.example` 中新增 phpMyAdmin 固定账号自动登录所需变量
- `compose.yml` 中 phpMyAdmin 与 `oauth2-proxy-phpmyadmin` 的相关配置更新
- phpMyAdmin 自定义配置文件，用于启用固定账号自动登录
- MariaDB 补偿脚本，用于幂等创建 phpMyAdmin 专用账号并授予 `appdb` 管理权限
- README 中新增 phpMyAdmin 自动登录与组限制说明
- 必要测试，覆盖目录编排、配置暴露或行为约束

## 3. 非目标

本次不包含以下能力：

- Keycloak 用户到 MariaDB 用户的一对一映射
- 按不同 Keycloak 用户下发不同数据库权限
- 为 phpMyAdmin 保留手工数据库登录入口
- 自动登录 MariaDB `root`
- 超出 `appdb` 的跨库管理能力
- 新增第二套认证代理或自定义会话桥接服务

## 4. 当前问题

当前仓库中，phpMyAdmin 只做了外层 SSO 前置保护，没有做内层数据库自动登录：

- `gateway/nginx.conf` 将 `pma.localhost` 转发到 `oauth2-proxy-phpmyadmin`
- `oauth2-proxy-phpmyadmin` 再转发到 `phpmyadmin:80`
- `phpmyadmin` 容器仅配置了 `PMA_HOST`、`PMA_PORT`、`PMA_ABSOLUTE_URI`
- 仓库内没有 `PMA_USER`、`PMA_PASSWORD`、`signon` 或自定义 `config.user.inc.php` 配置

因此，当前用户完成统一登录后，仍会看到 phpMyAdmin 自己的数据库登录页。

## 5. 设计结论

推荐采用“外层组控准入 + 内层固定账号自动登录”的最小闭环方案。

### 5.1 外层准入

`oauth2-proxy-phpmyadmin` 增加基于 Keycloak group claim 的准入限制：

- 增加参数：`--allowed-group=/platform-admins`
- 非该组成员：直接返回 `403`
- 已通过 SSO 但不在该组内的用户，不再进入 phpMyAdmin 页面

原因：

- 当前项目已经为 Keycloak client 配置 `groups` mapper
- `platform-admins` 已是现有脚本中稳定存在的组名
- 在代理层拦截，比进入 phpMyAdmin 后再处理更简单、更清晰

### 5.2 内层登录

phpMyAdmin 改为固定账号自动登录：

- 认证模式改为 `auth_type = config`
- 数据库主机继续使用 `mariadb`
- 使用一个新的 phpMyAdmin 专用 MariaDB 账号
- 不提供手工输入数据库用户名/密码的页面

原因：

- 当前目标明确是“统一入口后直接进入”
- 不需要实现会话桥接，也不需要维护更复杂的 `signon` 方案
- 后续如果真的要做“按人映射”，可以再独立迭代

## 6. 权限设计

### 6.1 Keycloak 侧

访问 phpMyAdmin 的前提：

- 已完成 Keycloak 登录
- 用户属于 `/platform-admins`

不额外新增 `phpmyadmin-admins` 组，首版直接复用现有组。

### 6.2 MariaDB 侧

新增一个固定 phpMyAdmin 专用账号：

- 用户名：`pma_appdb_admin`
- 密码来源：`.env` 中的 `PHPMYADMIN_AUTOLOGIN_PASSWORD`

权限边界：

- 仅允许管理 `appdb`
- 不授予全局管理权限
- 不授予 `SUPER`、`GRANT OPTION`、全实例级别权限
- 不使用 `root`

授予范围以“能完成 `appdb` 常见管理操作”为准：

- 结构查看
- 数据查询
- 数据增删改
- 索引与表结构调整
- 视图、触发器、存储过程等对象，仅在验证确认确有需要时追加 `appdb.*` 范围内的最小权限

如果测试发现某些管理操作需要额外权限，应只补 `appdb.*` 范围内的最小权限，不扩大到全库或全局。

## 7. 配置落点

### 7.1 compose.yml

需要补两类配置：

- `oauth2-proxy-phpmyadmin`
  - 增加 `allowed-group` 限制
- `phpmyadmin`
  - 挂载自定义配置文件
  - 注入 `PHPMYADMIN_AUTOLOGIN_USER` 与 `PHPMYADMIN_AUTOLOGIN_PASSWORD`

### 7.2 phpMyAdmin 自定义配置文件

新增独立配置文件：

- `phpmyadmin/config.user.inc.php`

作用：

- 覆盖默认认证模式
- 从环境变量读取固定数据库账号信息
- 固定连接到 `mariadb:3306`
- 使用 `config` 模式直接进入，不显示原生登录表单

### 7.3 MariaDB 初始化/补偿

新增 `scripts/repair-mariadb-phpmyadmin-user.sh`，用来保证以下两类场景都可生效：

- 新环境首次启动
- 已存在数据卷的老环境补齐账号权限

该脚本必须幂等，并纳入安装或 repair 流程调用；不依赖“仅首次初始化执行”的单次脚本。

## 8. 行为约束

首版行为固定如下：

- `platform-admins` 成员访问 `http://pma.localhost`
  - 先经过 Keycloak / oauth2-proxy
  - 通过后直接进入 phpMyAdmin 主界面
  - 不出现数据库用户名/密码输入页
- 非 `platform-admins` 成员访问
  - 完成 SSO 后直接得到 `403`
- 未登录用户访问
  - 仍先进入现有 SSO 跳转流程

## 9. 风险与限制

首版接受以下现实约束：

- 进入 phpMyAdmin 的授权用户共享同一个 MariaDB 账号，数据库侧无法直接区分操作者
- 审计主体仍主要依赖 Keycloak / 代理访问日志，而不是 MariaDB 用户级审计
- 如果 `platform-admins` 组成员过多，实际数据库操作权限也会随之扩大

因此首版必须坚持两点：

- 只允许 `/platform-admins`
- 只开放 `appdb` 范围权限

## 10. 文件范围

预计涉及：

- `.env.example`
- `compose.yml`
- `README.md`
- `scripts/repair-mariadb-phpmyadmin-user.sh`
- `tests/` 下与 compose、配置或探测相关测试
- 新增 `phpmyadmin/` 目录及配置文件

## 11. 验收标准

至少满足以下验收：

1. `platform-admins` 成员访问 `pma.localhost` 时，不再出现 phpMyAdmin 原生数据库登录框。
2. 自动登录后实际连接使用固定专用 MariaDB 账号，而不是 `root`。
3. 该账号只能管理 `appdb`，不能跨库获得全实例管理权限。
4. 非 `platform-admins` 成员完成 SSO 后访问 phpMyAdmin，返回 `403`。
5. 现有 RedisInsight、mongo-express、KafkaUI、Portainer、Harbor 等其他入口语义不被改变。
6. 相关测试通过，至少覆盖新的 compose/配置约束与关键行为。

## 12. 实施顺序

推荐顺序：

1. 补 `.env.example` 中 phpMyAdmin 专用账号相关变量
2. 新增 phpMyAdmin 自定义配置文件
3. 更新 `compose.yml` 中 phpMyAdmin 与 `oauth2-proxy-phpmyadmin` 配置
4. 增加 MariaDB 专用账号创建/补偿逻辑
5. 补测试
6. 更新 README
7. 做定向验证
