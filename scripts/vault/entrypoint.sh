#!/bin/sh
# Local-dev Vault bootstrap — see docker-compose.yml's `vault:` comment.
# Starts a real (file-storage) server, then inits it on first boot / unseals
# it on every later boot, and recreates what dev mode used to provide for
# free: the fixed `dev-only-root-token` and a `secret/` KV v2 mount.
set -e

export VAULT_ADDR=http://127.0.0.1:8200
INIT_FILE=/vault/file/init.txt

vault server -config=/vault/bootstrap/config.hcl &
SERVER_PID=$!

# `vault status` exits 1 while unreachable, 2 once up-but-sealed.
until vault status >/dev/null 2>&1 || [ $? -eq 2 ]; do
  sleep 1
done

# ponytail: unseal key + generated root token live in the same volume as the
# data they protect, and unseal is automatic — fine only because this is a
# throwaway local-dev Vault holding test-app logins. A real deployment needs
# the deferred Vault-vs-cloud-KMS decision (auto-unseal via KMS, no stored
# root token, scoped policies instead of a fixed root token).
if [ ! -f "$INIT_FILE" ]; then
  echo "[vault-bootstrap] first boot: initializing"
  vault operator init -key-shares=1 -key-threshold=1 > "$INIT_FILE"
  FIRST_BOOT=1
fi

UNSEAL_KEY=$(sed -n 's/^Unseal Key 1: //p' "$INIT_FILE")
vault operator unseal "$UNSEAL_KEY" >/dev/null
echo "[vault-bootstrap] unsealed"

if [ -n "$FIRST_BOOT" ]; then
  VAULT_TOKEN=$(sed -n 's/^Initial Root Token: //p' "$INIT_FILE")
  export VAULT_TOKEN
  vault token create -id=dev-only-root-token -policy=root -orphan >/dev/null
  vault secrets enable -path=secret kv-v2 >/dev/null
  echo "[vault-bootstrap] created dev-only-root-token and secret/ (kv-v2)"
fi

wait "$SERVER_PID"
