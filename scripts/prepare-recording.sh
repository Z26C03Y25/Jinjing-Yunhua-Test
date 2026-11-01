#!/bin/sh
# Prepare, but do not start, a separate empty-data recording environment.
set -eu
umask 077
source_dir=$(pwd)
target="$source_dir/.recording/workspace"
if [ -e "$target" ]; then
    echo '录制目录已存在，保留内容，不覆盖或删除。'
    exit 0
fi
if [ -n "$(docker volume ls -q --filter label=com.docker.compose.project=jinjing-recording)" ]; then
    echo '录制项目已有数据卷；拒绝冒充空环境，请先核查。'
    exit 1
fi
mkdir -p "$source_dir/.recording"
git clone --no-hardlinks --quiet "$source_dir" "$target"
python3 - "$source_dir" "$target" <<'PY'
import pathlib,sys,os
source,target=map(pathlib.Path,sys.argv[1:])
values=dict(line.split('=',1) for line in (source/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
text='COMPOSE_PROJECT_NAME=jinjing-recording\nWEB_BIND=127.0.0.1\nWEB_PORT=18080\n'
for key in ('APP_PASSWORD','VIEWER_PASSWORD'):
    text+=key+'='+values.get(key,'')+'\n'
(target/'.env').write_text(text)
os.chmod(target/'.env',0o600)
PY
cd "$target"
docker compose config --quiet
echo "录制环境已准备，尚未启动：$target"
echo '在Windows录屏前建立SSH转发：ssh -L 18080:127.0.0.1:18080 root@服务器IP'
echo "录屏开始后执行：cd '$target' && make up"
echo '浏览器访问：http://127.0.0.1:18080，使用现有分析员密码。'
echo '项目名jinjing-recording，使用独立空业务卷；基础镜像和构建缓存已存在。'
