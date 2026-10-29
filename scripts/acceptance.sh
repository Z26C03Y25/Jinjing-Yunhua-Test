#!/bin/sh
set -eu
source_dir=$(pwd)
test_dir=$(mktemp -d /tmp/jinjing-acceptance.XXXXXXXX)
project="jinjing-acceptance-$(date +%s)"
export COMPOSE_PROJECT_NAME="$project" WEB_BIND=127.0.0.1 WEB_PORT=18080
export GIT_DIR="$source_dir/.git" GIT_WORK_TREE="$test_dir"
cleanup() {
    cd "$test_dir"
    docker compose -p "$project" down -v --remove-orphans >/dev/null 2>&1 || true
    # Only remove the literal mktemp-created acceptance directory.
    case "$test_dir" in /tmp/jinjing-acceptance.*) rm -rf -- "$test_dir";; esac
}
trap cleanup EXIT INT TERM
git --git-dir="$source_dir/.git" archive HEAD | tar -x -C "$test_dir"
cd "$test_dir"
started=$(date +%s)
if ! sh scripts/bootstrap.sh >bootstrap.log 2>&1; then
    # Do not print first-start passwords from bootstrap.log.
    echo '独立初始化失败（日志包含临时凭据，不直接打印）。'
    docker compose -p "$project" logs --tail 60
    exit 1
fi
export ACCEPTANCE_STARTED="$started"
python3 scripts/acceptance_api.py
mkdir -p "$source_dir/.runtime-reports"
cp validation/acceptance-report.json "$source_dir/.runtime-reports/acceptance-report.json"
echo '独立启动与 API 自验完成，临时容器和数据卷即将清理。'
