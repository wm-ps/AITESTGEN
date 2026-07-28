#!/usr/bin/env bash
cd "$(dirname "$0")/.."
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/openapi.json 2>/dev/null)
  [ "$code" = "200" ] && break
  sleep 1
done
[ -d apps/web/node_modules ] || exit 0
cd apps/web && npm run generate:api-types
