# Nacos Keycloak Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `http://nacos.localhost/` 稳定走 Keycloak OIDC 登录，并在登录成功后回到可用的 Nacos Console。

**Architecture:** 保持 Nacos 3.2.1 的原生 OIDC 架构，不新增 `oauth2-proxy`。实现分三块：先用测试锁定真实登录入口 `/v1/auth/oidc/login` 与回调 `/v1/auth/oidc/callback`，再补齐 OIDC 插件缺失的 `caffeine` 依赖并收敛 Keycloak client redirect URI，最后做运行态验证，确认 `nacos.localhost` 能被引导到 `auth.localhost` 并回到 Console。

**Tech Stack:** Docker Compose, Nginx, Nacos 3.2.1-2026.04.03, Keycloak, Bash, Python `unittest`

---

## File Map

- Modify: `business_panel/catalog.py`
  - 把 `nacos` 业务单元的 `auth_path` 从泛化值改成真实 OIDC 登录入口 `/v1/auth/oidc/login`
- Modify: `business_panel/probes.py`
  - 让 Nacos 认证探测走 `/v1/auth/oidc/login`，不再错误假设首页直接 302 到 Keycloak
- Modify: `scripts/bootstrap-keycloak.sh`
  - 把 `nacos` Keycloak client 的 redirect URI 从宽泛 `/*` 收敛到官方回调路径 `/v1/auth/oidc/callback`
- Modify: `compose.yml`
  - 给 `nacos` 服务补挂载 `caffeine-3.1.8.jar`
- Create: `nacos/plugins/caffeine-3.1.8.jar`
  - OIDC 插件缺失的运行时依赖，下载自 Maven Central
- Modify: `tests/test_config_catalog.py`
  - 让 `nacos` 的 `auth_path` 断言匹配真实登录入口
- Modify: `tests/test_probes.py`
  - 锁定 Nacos 探测 URL、Keycloak client redirect URI、回调路径契约
- Modify: `tests/test_nacos_nightingale_compose.py`
  - 断言 `compose.yml` 已挂载 `caffeine-3.1.8.jar`
- Modify: `README.md`
  - 只在实现后确认需要时补一条 Nacos 登录入口说明

### Task 1: Lock The Nacos OIDC Contract With Failing Tests

**Files:**
- Modify: `tests/test_config_catalog.py`
- Modify: `tests/test_probes.py`
- Modify: `tests/test_nacos_nightingale_compose.py`

- [ ] **Step 1: Write the failing catalog test for the real Nacos auth entry**

```python
        self.assertEqual(units["nacos"].auth_path, "/v1/auth/oidc/login")
        self.assertEqual(units["nightingale"].auth_path, "openid-connect/auth")
```

- [ ] **Step 2: Write the failing probe test that Nacos uses `/v1/auth/oidc/login`**

```python
    def test_probe_auth_nacos_uses_oidc_login_endpoint(self) -> None:
        unit = _unit(
            unit_id="nacos",
            entry_url="http://nacos.localhost",
            auth_mode="oidc_redirect",
            auth_path="/v1/auth/oidc/login",
        )
        client = FakeProbeClient(
            {
                "http://nacos.localhost/v1/auth/oidc/login": HttpResponse(
                    status=302,
                    headers={
                        "Location": (
                            "http://auth.localhost/realms/infra/protocol/openid-connect/auth"
                            "?client_id=nacos"
                            "&redirect_uri=http%3A%2F%2Fnacos.localhost%2Fv1%2Fauth%2Foidc%2Fcallback"
                        )
                    },
                    body="",
                )
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result.level, "ok")
        self.assertEqual(client.calls, [("http://nacos.localhost/v1/auth/oidc/login", False)])
```

- [ ] **Step 3: Replace the failing bootstrap contract for the Nacos callback URI**

```python
        self.assertEqual(
            bootstrap_clients["nacos"],
            {
                "secret": "${NACOS_CLIENT_SECRET:-nacos-client-secret}",
                "redirect_uris": "[\\\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}/v1/auth/oidc/callback\\\"]",
                "web_origins": "[\\\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}\\\"]",
            },
        )
```

- [ ] **Step 4: Add the failing compose assertion for the missing caffeine dependency**

```python
        self.assertIn(
            "./nacos/plugins/caffeine-3.1.8.jar:/home/nacos/plugins/caffeine-3.1.8.jar:ro",
            nacos,
        )
```

- [ ] **Step 5: Run the targeted tests to prove they fail for the current implementation**

Run:

```bash
python3 -m unittest \
  tests.test_config_catalog.ConfigCatalogTest.test_build_units_includes_nacos_and_nightingale \
  tests.test_probes.ProbeAuthTest.test_probe_auth_nacos_uses_oidc_login_endpoint \
  tests.test_probes.Task3OidcConfigContractTest.test_keycloak_bootstrap_refreshes_nacos_and_nightingale_clients \
  tests.test_nacos_nightingale_compose.ComposeExtensionTest.test_compose_includes_nacos_and_nightingale_services \
  -v
```

Expected:

- `auth_path` 仍是旧值
- Nacos probe 仍然请求根路径
- Keycloak bootstrap 仍然使用 `/*`
- `compose.yml` 还没有 `caffeine-3.1.8.jar` 挂载

- [ ] **Step 6: Commit the red tests**

```bash
git add tests/test_config_catalog.py tests/test_probes.py tests/test_nacos_nightingale_compose.py
git commit -m "test: lock nacos keycloak login contract"
```

### Task 2: Implement The Native OIDC Login Chain

**Files:**
- Modify: `business_panel/catalog.py`
- Modify: `business_panel/probes.py`
- Modify: `scripts/bootstrap-keycloak.sh`
- Modify: `compose.yml`
- Create: `nacos/plugins/caffeine-3.1.8.jar`

- [ ] **Step 1: Download the missing caffeine runtime dependency**

Run:

```bash
mkdir -p nacos/plugins
curl -sSLo nacos/plugins/caffeine-3.1.8.jar \
  https://repo1.maven.org/maven2/com/github/ben-manes/caffeine/caffeine/3.1.8/caffeine-3.1.8.jar
```

Expected:

- `nacos/plugins/caffeine-3.1.8.jar` exists
- `ls -lh nacos/plugins/caffeine-3.1.8.jar` shows a non-zero file size

- [ ] **Step 2: Point the Nacos business unit metadata at the real OIDC login endpoint**

```python
        UnitDefinition(
            unit_id="nacos",
            display_name="Nacos",
            description="Configuration and service discovery platform.",
            entry_url=f"{settings.public_scheme}://{settings.nacos_public_host}",
            compose_scope="main",
            start_services=("nacos", "nacos-mysql"),
            stop_services=("nacos", "nacos-mysql"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="/v1/auth/oidc/login",
            auth_expectation="required",
        ),
```

- [ ] **Step 3: Update the Nacos auth probe to call `/v1/auth/oidc/login`**

```python
    if unit.auth_mode == "oidc_redirect":
        if unit.unit_id == "nightingale":
            response = client.fetch(f"{unit.entry_url}/api/n9e/auth/redirect?redirect={quote('/', safe='')}")
            if "openid-connect/auth" in response.body and "client_id=nightingale" in response.body:
                return ProbeResult.ok("检测到 OIDC 跳转")
            return ProbeResult.fail("未检测到 OIDC 跳转")
        target = unit.entry_url
        if unit.unit_id == "nacos":
            target = f"{unit.entry_url}{unit.auth_path}"
        response = client.fetch(target)
        location = _header_value(response.headers, "Location")
        if unit.auth_path in location or "openid-connect/auth" in location or "/oauth2/authorization/" in location:
            return ProbeResult.ok("检测到 OIDC 跳转")
        return ProbeResult.fail("未检测到 OIDC 跳转")
```

- [ ] **Step 4: Narrow the Keycloak Nacos client redirect URI to the official callback path**

```bash
create_or_update_client \
  "nacos" \
  "${NACOS_CLIENT_SECRET:-nacos-client-secret}" \
  "[\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}/v1/auth/oidc/callback\"]" \
  "[\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}\"]"
```

- [ ] **Step 5: Mount the caffeine jar into the Nacos plugins directory**

```yaml
  nacos:
    image: ${NACOS_IMAGE:-nacos/nacos-server:latest}
    container_name: nacos
    restart: unless-stopped
    environment:
      NACOS_DEPLOYMENT_TYPE: ${NACOS_DEPLOYMENT_TYPE:-merged}
      MODE: standalone
      SPRING_DATASOURCE_PLATFORM: mysql
      NACOS_AUTH_TOKEN: ${NACOS_AUTH_TOKEN:-VGhpc0lzTXlDdXN0b21TZWNyZXRLZXkwMTIzNDU2Nzg=}
      NACOS_AUTH_IDENTITY_KEY: ${NACOS_AUTH_IDENTITY_KEY:-serverIdentity}
      NACOS_AUTH_IDENTITY_VALUE: ${NACOS_AUTH_IDENTITY_VALUE:-security}
    volumes:
      - ./nacos/application.properties:/home/nacos/conf/application.properties:ro
      - ./nacos/plugins/caffeine-3.1.8.jar:/home/nacos/plugins/caffeine-3.1.8.jar:ro
```

- [ ] **Step 6: Run the focused tests to make sure the implementation goes green**

Run:

```bash
python3 -m unittest tests/test_config_catalog.py tests/test_probes.py tests/test_nacos_nightingale_compose.py -v
```

Expected:

- Nacos catalog metadata now points at `/v1/auth/oidc/login`
- Nacos auth probe now checks the OIDC login endpoint
- Keycloak bootstrap contract now uses `/v1/auth/oidc/callback`
- `compose.yml` now mounts `caffeine-3.1.8.jar`

- [ ] **Step 7: Commit the implementation**

```bash
git add \
  business_panel/catalog.py \
  business_panel/probes.py \
  scripts/bootstrap-keycloak.sh \
  compose.yml \
  nacos/plugins/caffeine-3.1.8.jar \
  tests/test_config_catalog.py \
  tests/test_probes.py \
  tests/test_nacos_nightingale_compose.py
git commit -m "feat: wire nacos keycloak oidc login"
```

### Task 3: Verify The Live Login Flow And Update Entry Notes

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Refresh the Keycloak client registration**

Run:

```bash
./scripts/bootstrap-keycloak.sh
```

Expected:

- output contains `已更新 client: nacos` or `已创建 client: nacos`

- [ ] **Step 2: Restart only the affected services**

Run:

```bash
docker compose restart nacos gateway
```

Expected:

- `Container nacos Started`
- `Container gateway Started`

- [ ] **Step 3: Verify the Nacos OIDC login endpoint returns a Keycloak redirect**

Run:

```bash
docker compose exec gateway sh -lc \
  'printf "GET /v1/auth/oidc/login HTTP/1.1\r\nHost: nacos.localhost\r\nConnection: close\r\n\r\n" | nc nacos 8080 | sed -n "1,20p"'
```

Expected:

- response status is `302`
- `Location` contains `http://auth.localhost/realms/infra/protocol/openid-connect/auth`
- `Location` contains `client_id=nacos`
- `Location` contains `redirect_uri=http%3A%2F%2Fnacos.localhost%2Fv1%2Fauth%2Foidc%2Fcallback`

- [ ] **Step 4: Verify the public root entry still resolves to the console**

Run:

```bash
docker compose exec gateway sh -lc \
  'printf "GET / HTTP/1.1\r\nHost: nacos.localhost\r\nConnection: close\r\n\r\n" | nc 127.0.0.1 80 | sed -n "1,20p"'
```

Expected:

- response is `302` to `/next/` or `200` HTML from the console
- it is no longer a `404` or `500`

- [ ] **Step 5: Manually verify the browser login round-trip**

Manual spot check:

1. Open `http://nacos.localhost/`
2. Click the Nacos SSO login entry if the Console presents a login page
3. Confirm the browser is redirected to `http://auth.localhost/realms/infra/...`
4. Sign in with the local test account
5. Confirm the browser returns to Nacos Console instead of staying on Keycloak or erroring on callback

- [ ] **Step 6: Update the Nacos access note in README only if the runtime path changed**

```markdown
- Nacos: `http://nacos.localhost`
  - 未登录时通过 Nacos 原生 OIDC 跳转到 `auth.localhost`
  - Keycloak 回调路径：`/v1/auth/oidc/callback`
```

- [ ] **Step 7: Run the full verification set**

Run:

```bash
python3 -m unittest tests/test_config_catalog.py tests/test_probes.py tests/test_nacos_nightingale_compose.py -v
docker compose exec gateway nginx -t
```

Expected:

- all tests pass
- `nginx: configuration file /etc/nginx/nginx.conf test is successful`

- [ ] **Step 8: Commit the runtime verification and docs update**

```bash
git add docs/plans/2026-04-21-nacos-keycloak-login-plan.md
git diff --quiet -- README.md || git add README.md
git commit -m "docs: document nacos keycloak login flow"
```
