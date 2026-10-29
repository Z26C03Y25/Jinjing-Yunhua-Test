#!/bin/sh
# First start on Ubuntu after configuring a working Docker registry mirror.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
command -v python3 >/dev/null
docker compose version
if [ ! -e .env ]; then
    umask 077
    python3 - <<'PY'
import secrets
from pathlib import Path
analyst, viewer = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
Path('.env').write_text('WEB_BIND=0.0.0.0\nWEB_PORT=80\nAPP_PASSWORD='+analyst+'\nVIEWER_PASSWORD='+viewer+'\n')
print('首次生成的登录信息（保存在服务器 .env，请妥善保存）：')
print('analyst:', analyst)
print('viewer:', viewer)
PY
fi
docker compose config --quiet
docker image inspect debian:12.9-slim >/dev/null 2>&1 || docker pull debian:12.9-slim
docker image inspect nginx:1.28.0-alpine >/dev/null 2>&1 || docker pull nginx:1.28.0-alpine
revision=$(git rev-parse HEAD)
image=$(docker compose config --format json | python3 -c 'import sys,json; print(json.load(sys.stdin)["services"]["backend"]["image"])')
docker build --pull=false --label "org.opencontainers.image.revision=$revision" -f backend/Dockerfile -t "$image" .
docker compose up -d --no-build --pull never --wait --wait-timeout 120
docker compose ps
echo '启动完成：浏览器访问服务器 HTTP 80 端口。已有 .env 时不会重置密码。'
