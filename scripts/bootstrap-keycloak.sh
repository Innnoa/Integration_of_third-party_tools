#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}"
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

KCADM=(docker exec keycloak /opt/keycloak/bin/kcadm.sh)
KEYCLOAK_PUBLIC_ISSUER="${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}"

wait_for_keycloak() {
  local retries=60
  while (( retries > 0 )); do
    if "${KCADM[@]}" config credentials \
      --server "http://localhost:8080" \
      --realm master \
      --user "${KEYCLOAK_ADMIN_USER}" \
      --password "${KEYCLOAK_ADMIN_PASSWORD}" >/dev/null 2>&1; then
      return 0
    fi
    retries=$((retries - 1))
    sleep 2
  done

  echo "Keycloak 管理接口在预期时间内未就绪。"
  exit 1
}

get_realm_id() {
  "${KCADM[@]}" get "realms/${KEYCLOAK_REALM}" >/dev/null 2>&1
}

ensure_realm() {
  if get_realm_id; then
    echo "Realm 已存在: ${KEYCLOAK_REALM}"
    return
  fi

  "${KCADM[@]}" create realms \
    -s realm="${KEYCLOAK_REALM}" \
    -s enabled=true
  echo "已创建 realm: ${KEYCLOAK_REALM}"
}

get_group_id() {
  local group_name="$1"
  "${KCADM[@]}" get groups -r "${KEYCLOAK_REALM}" \
    | python3 -c 'import json,sys; data=json.load(sys.stdin); target=sys.argv[1];
for item in data:
    if item.get("path","").endswith("/"+target):
        print(item["id"])
        break' "${group_name}"
}

ensure_group() {
  local group_name="$1"
  local group_id=""
  if group_id="$(get_group_id "${group_name}")" && [[ -n "${group_id}" ]]; then
    echo "Group 已存在: ${group_name}"
    return
  fi

  "${KCADM[@]}" create groups -r "${KEYCLOAK_REALM}" -s name="${group_name}"
  echo "已创建 group: ${group_name}"
}

get_client_uuid() {
  local client_id="$1"
  "${KCADM[@]}" get clients -r "${KEYCLOAK_REALM}" \
    | python3 -c 'import json,sys; data=json.load(sys.stdin); target=sys.argv[1];
for item in data:
    if item.get("clientId")==target:
        print(item["id"])
        break' "${client_id}"
}

create_or_update_client() {
  local client_id="$1"
  local secret="$2"
  local redirect_uris="$3"
  local web_origins="$4"

  local client_uuid
  client_uuid="$(get_client_uuid "${client_id}")"

  if [[ -z "${client_uuid}" ]]; then
    "${KCADM[@]}" create clients -r "${KEYCLOAK_REALM}" \
      -s clientId="${client_id}" \
      -s name="${client_id}" \
      -s enabled=true \
      -s protocol=openid-connect \
      -s publicClient=false \
      -s standardFlowEnabled=true \
      -s directAccessGrantsEnabled=false \
      -s serviceAccountsEnabled=false \
      -s "redirectUris=${redirect_uris}" \
      -s "webOrigins=${web_origins}"
    client_uuid="$(get_client_uuid "${client_id}")"
    echo "已创建 client: ${client_id}"
  else
    "${KCADM[@]}" update "clients/${client_uuid}" -r "${KEYCLOAK_REALM}" \
      -s enabled=true \
      -s publicClient=false \
      -s standardFlowEnabled=true \
      -s directAccessGrantsEnabled=false \
      -s serviceAccountsEnabled=false \
      -s "redirectUris=${redirect_uris}" \
      -s "webOrigins=${web_origins}"
    echo "已更新 client: ${client_id}"
  fi

  "${KCADM[@]}" update "clients/${client_uuid}" -r "${KEYCLOAK_REALM}" \
    -s 'attributes."post.logout.redirect.uris"="+"' \
    -s secret="${secret}" >/dev/null
}

create_groups_mapper() {
  local client_id="$1"
  local client_uuid
  client_uuid="$(get_client_uuid "${client_id}")"

  if "${KCADM[@]}" get "clients/${client_uuid}/protocol-mappers/models" -r "${KEYCLOAK_REALM}" \
      | python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(0 if any(x.get("name")=="groups" for x in data) else 1)'
  then
    return
  fi

  "${KCADM[@]}" create "clients/${client_uuid}/protocol-mappers/models" -r "${KEYCLOAK_REALM}" \
    -s name=groups \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-group-membership-mapper \
    -s 'config."full.path"="true"' \
    -s 'config."id.token.claim"="true"' \
    -s 'config."access.token.claim"="true"' \
    -s 'config."userinfo.token.claim"="true"' \
    -s 'config."claim.name"="groups"'
}

create_oauth2_proxy_audience_mapper() {
  local client_uuid
  client_uuid="$(get_client_uuid "${OAUTH2_PROXY_CLIENT_ID}")"

  if "${KCADM[@]}" get "clients/${client_uuid}/protocol-mappers/models" -r "${KEYCLOAK_REALM}" \
      | python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(0 if any(x.get("name")=="audience-oauth2-proxy" for x in data) else 1)'
  then
    return
  fi

  "${KCADM[@]}" create "clients/${client_uuid}/protocol-mappers/models" -r "${KEYCLOAK_REALM}" \
    -s name=audience-oauth2-proxy \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-audience-mapper \
    -s 'config."included.client.audience"="oauth2-proxy"' \
    -s 'config."id.token.claim"="true"' \
    -s 'config."access.token.claim"="true"'
}

get_user_id() {
  local username="$1"
  "${KCADM[@]}" get users -r "${KEYCLOAK_REALM}" \
    | python3 -c 'import json,sys; data=json.load(sys.stdin); target=sys.argv[1];
for item in data:
    if item.get("username")==target:
        print(item["id"])
        break' "${username}"
}

ensure_user() {
  local user_id
  user_id="$(get_user_id "${KEYCLOAK_TEST_USER}")"

  if [[ -z "${user_id}" ]]; then
    "${KCADM[@]}" create users -r "${KEYCLOAK_REALM}" \
      -s username="${KEYCLOAK_TEST_USER}" \
      -s enabled=true \
      -s email="${KEYCLOAK_TEST_USER}@example.local" \
      -s emailVerified=true \
      -s firstName=Ops \
      -s lastName=Admin
    user_id="$(get_user_id "${KEYCLOAK_TEST_USER}")"
    echo "已创建测试用户: ${KEYCLOAK_TEST_USER}"
  else
    echo "测试用户已存在: ${KEYCLOAK_TEST_USER}"
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh set-password \
    -r "${KEYCLOAK_REALM}" \
    --username "${KEYCLOAK_TEST_USER}" \
    --new-password "${KEYCLOAK_TEST_PASSWORD}" >/dev/null

  for group_name in platform-admins harbor-admins kafka-admins tools-users; do
    local group_id
    group_id="$(get_group_id "${group_name}")"
    if [[ -n "${group_id}" ]]; then
      "${KCADM[@]}" update "users/${user_id}/groups/${group_id}" -r "${KEYCLOAK_REALM}" >/dev/null 2>&1 || true
    fi
  done
}

wait_for_keycloak
ensure_realm

for group_name in platform-admins harbor-admins kafka-admins tools-users; do
  ensure_group "${group_name}"
done

create_or_update_client \
  "portainer" \
  "${PORTAINER_CLIENT_SECRET}" \
  "[\"${PUBLIC_SCHEME}://${PORTAINER_PUBLIC_HOST}/\"]" \
  "[\"${PUBLIC_SCHEME}://${PORTAINER_PUBLIC_HOST}\"]"

create_or_update_client \
  "${KAFKA_UI_CLIENT_ID}" \
  "${KAFKA_UI_CLIENT_SECRET}" \
  "[\"${PUBLIC_SCHEME}://${KAFKA_UI_PUBLIC_HOST}/login/oauth2/code/keycloak\"]" \
  "[\"${PUBLIC_SCHEME}://${KAFKA_UI_PUBLIC_HOST}\"]"

create_or_update_client \
  "${OAUTH2_PROXY_CLIENT_ID}" \
  "${OAUTH2_PROXY_CLIENT_SECRET}" \
  "[\"${PUBLIC_SCHEME}://${REDISINSIGHT_PUBLIC_HOST}/oauth2/callback\",\"${PUBLIC_SCHEME}://${PHPMYADMIN_PUBLIC_HOST}/oauth2/callback\",\"${PUBLIC_SCHEME}://${MONGO_EXPRESS_PUBLIC_HOST}/oauth2/callback\",\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}/oauth2/callback\"]" \
  "[\"${PUBLIC_SCHEME}://${REDISINSIGHT_PUBLIC_HOST}\",\"${PUBLIC_SCHEME}://${PHPMYADMIN_PUBLIC_HOST}\",\"${PUBLIC_SCHEME}://${MONGO_EXPRESS_PUBLIC_HOST}\",\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}\"]"

create_or_update_client \
  "${HARBOR_CLIENT_ID}" \
  "${HARBOR_CLIENT_SECRET}" \
  "[\"${PUBLIC_SCHEME}://${HARBOR_PUBLIC_HOST}/*\"]" \
  "[\"${PUBLIC_SCHEME}://${HARBOR_PUBLIC_HOST}\"]"

create_or_update_client \
  "nightingale" \
  "${NIGHTINGALE_CLIENT_SECRET}" \
  "[\"${PUBLIC_SCHEME}://${NIGHTINGALE_PUBLIC_HOST}/callback\"]" \
  "[\"${PUBLIC_SCHEME}://${NIGHTINGALE_PUBLIC_HOST}\"]"

for client_name in portainer "${KAFKA_UI_CLIENT_ID}" "${OAUTH2_PROXY_CLIENT_ID}" "${HARBOR_CLIENT_ID}"; do
  create_groups_mapper "${client_name}"
done

create_oauth2_proxy_audience_mapper
ensure_user

echo
echo "Keycloak bootstrap 完成。"
echo "Realm: ${KEYCLOAK_REALM}"
echo "测试用户: ${KEYCLOAK_TEST_USER}"
echo "测试密码: ${KEYCLOAK_TEST_PASSWORD}"
