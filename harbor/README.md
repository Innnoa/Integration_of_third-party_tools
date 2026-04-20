# Harbor 模块说明

这个目录只放 Harbor 的模板与辅助文件，不直接提供 Harbor 完整安装包。

## 为什么 Harbor 不放进主 compose

Harbor 官方推荐通过 `harbor.yml + install.sh` 生成并维护自己的 `docker-compose.yml`。  
本项目保留这条官方路径，只通过 `docker-compose.override.yml` 把 Harbor 接入主栈使用的外部网络 `TOOLS_NETWORK`。

## 目录约定

- `harbor.yml.example`：本地 HTTP 测试模板
- `docker-compose.override.yml`：为官方生成的 Harbor compose 增加 `tools_net`

## 使用步骤

1. 从 Harbor Releases 下载并解压 `online installer`
2. 把解压后的内容放到 `harbor/installer/`
3. 把 `harbor.yml.example` 复制为 `harbor/installer/harbor.yml`
4. 用你的 `HARBOR_PUBLIC_HOST` 和管理员密码修改 `harbor.yml`
5. 把 `docker-compose.override.yml` 复制到 `harbor/installer/`
6. 先执行根目录 `scripts/init-network.sh`
7. 再执行根目录 `scripts/prepare-harbor.sh`
8. 最后在 `harbor/installer/` 里运行 `./install.sh --with-trivy`

如果 Harbor 官方生成的服务名与你当前版本不完全一致，请按生成后的 `docker-compose.yml` 调整 override 里的服务名。

## OIDC 配置建议

Harbor 启动后，在 Web UI 里进入：

- `Administration -> Configuration -> Authentication`

推荐配置：

- Auth Mode: `OIDC`
- OIDC Provider Name: `keycloak`
- OIDC Provider Endpoint: `http://auth.localhost/realms/infra`
- OIDC Client ID: `harbor`
- OIDC Client Secret: 你的 Keycloak client secret
- OIDC Scope: `openid,profile,email,groups,offline_access`
- Group Claim Name: `groups`
- OIDC Admin Group: `/harbor-admins`
- Username Claim: `preferred_username`
- Automatic Onboarding: `ON`

## Docker CLI 注意事项

如果 Harbor 继续用 HTTP，本机 Docker 需要把 Harbor 配成 insecure registry，例如：

```json
{
  "insecure-registries": ["harbor.localhost"]
}
```

然后重启 Docker。

## 说明

- `hostname` 不要写 `localhost`
- `data_volume` 建议放在 WSL Linux 文件系统，不要放 `/mnt/c/...`
- Harbor OIDC 登录成功后，`docker login` 使用 Harbor `CLI Secret`，不是 Keycloak 密码
