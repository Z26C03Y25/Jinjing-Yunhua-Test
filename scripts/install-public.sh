#!/bin/bash
set -euo pipefail
umask 077
export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8
if [ "$(id -u)" -ne 0 ]; then
    echo '请使用 root 账户安装；脚本需要安装基础依赖及访问 Docker。' >&2
    exit 1
fi
command -v docker >/dev/null || { echo '请先安装 Docker Engine，再运行本脚本。' >&2; exit 1; }
if ! docker info >/dev/null 2>&1; then
    systemctl start docker
    docker info >/dev/null
fi
missing=0
for command in git python3 make curl; do command -v "$command" >/dev/null || missing=1; done
if [ "$missing" = 1 ] || ! docker compose version >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::Retries=2 update < /dev/null
    apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends git python3 make curl ca-certificates < /dev/null
    if ! docker compose version >/dev/null 2>&1; then
        apt-get -o DPkg::Lock::Timeout=120 install -y docker-compose-plugin < /dev/null || apt-get -o DPkg::Lock::Timeout=120 install -y docker-compose-v2 < /dev/null
    fi
fi
docker compose up --help | grep -- '--wait-timeout' > /dev/null || { echo 'Docker Compose版本过旧，请更新Docker Compose插件。' >&2; exit 1; }
temporary=$(mktemp -d /tmp/jinjing-public-install.XXXXXXXX)
trap 'rm -f -- "$temporary/install.py"; rmdir -- "$temporary"' EXIT
printf '%s' '__PYTHON64__' | base64 -d > "$temporary/install.py"
python3 "$temporary/install.py" --directory '__DIRECTORY__' --web-port '__WEBPORT__' --bind '__BIND__' --project '__PROJECT__' --backend-image '__IMAGE__' __EXTRA__ < /dev/tty
