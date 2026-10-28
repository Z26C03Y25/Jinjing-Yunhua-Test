# Jinjing-Yunhua-Test
金睛云华前期测试题：基于 Suricata · B/S 架构 流量威胁检测系统

## Windows → Ubuntu 同步

本地推送使用 GitHub SSH，服务器使用专用 SSH Deploy key 拉取。首次运行前在本机执行 `ssh-keygen -t ed25519`，按提示生成密钥（可以设置密钥口令），把 `%USERPROFILE%\.ssh\id_ed25519.pub` 的内容添加到 GitHub Settings → SSH and GPG keys → New SSH key。只上传 `.pub` 公钥，私钥留在本机。脚本会将当前仓库 origin 切换为 SSH 并先检查访问权限。

在仓库目录打开 CMD，执行（无需安装 PowerShell 7）：

```bat
scripts\sync-remote.cmd
```

按中文提示输入服务器 IP、SSH 用户名（直接回车默认 root），随后按 SSH 的 password 提示输入服务器密码（输入时不显示字符）。首次连接请用云控制台核对服务器主机指纹。不要把密码发到聊天或写进仓库。

如果本地 Git 尚未配置提交姓名或邮箱，脚本会中文提示填写，只保存到当前仓库，不修改全局配置。该信息用于 commit 作者署名，不是 GitHub 登录密码。

远程同步在当前 SSH 进程中隔离 Git 全局和系统配置，避免服务器的 `insteadOf` 把 HTTPS 改为 SSH 而出现 `Permission denied (publickey)`，不修改服务器现有配置。当前默认适用于公开仓库；私有仓库需要另行配置此同步进程可用的凭据，全局 credential helper 不会被读取。

脚本将提交所有未忽略的本地修改、推送当前分支，再在 Ubuntu 的 `~/code/Jinjing-Yunhua-Test` 同步：首次自动创建 `~/code` 并 git clone，后续 git pull --ff-only 更新同一分支，核验 commit 和题目 DOCX 的 SHA256。`~` 指 SSH 登录用户的家目录。运行前请检查 `git status`，确保没有准备外的文件。Ubuntu 需预装 git、python3，并能够访问 GitHub；私有仓库还需提前在服务器配置 GitHub 读取凭据，服务器登录密码不能代替 GitHub 凭据。

可选参数：

```bat
scripts\sync-remote.cmd -Server 203.0.113.10 -User ubuntu -Port 22 -SkipCommit
scripts\sync-remote.cmd -RemoteDirectory projects/Jinjing-Yunhua-Test -Message "feat: update application"
REM 后续项目具备 compose 配置且 Ubuntu 已安装 Docker Compose 后：
scripts\sync-remote.cmd -Deploy
```

`-SkipCommit` 只推送已有提交，不提交工作区修改。`-Deploy` 在同步校验成功后运行 `docker compose config --quiet`、`docker compose up -d --build` 和 `docker compose ps`。现已提供最小 Web Compose 环境，部署会等待 Web 健康检查通过（120 秒超时），失败时输出容器日志。检测引擎和后端尚未接入。

CMD 入口内部调用 Windows 自带的 PowerShell 执行同步逻辑，保留 `.ps1` 为实现文件。参数包含空格时请使用双引号。

远程存在未提交修改、分支分叉、版本或文件校验不符时脚本会停止，不执行强制重置。首次 SSH 失败时本地提交可能已推送，解决连接问题后可加 `-SkipCommit` 重试。

## 最小部署环境

运行 `scripts\sync-remote.cmd -Deploy`。服务器需支持 Docker Compose 的 `--wait`，登录用户有 Docker 权限。

公网唯一业务入口为 TCP 80：`浏览器 → 宿主机 80 → web Nginx :8080 → /api/ → backend :8000`。两个容器在同一内部网络，后端无宿主机端口映射。当前 backend 是复用 Nginx 镜像的 API 连通占位服务，只提供 `/api/healthz`，尚无检测业务。后续替换为真实后端时沿用内部 8000 端口。

部署后访问 `http://123.57.158.71/`、`http://123.57.158.71/api/healthz`。云安全组和服务器防火墙放行 TCP 80，无需放行 8080、8000。SSH 管理通道仍需对管理来源保留访问，否则同步脚本无法连接。如果宿主机已有 Nginx 占用 80，请先协调已有服务配置，当前方案由 Compose Nginx 直接接管 80。

如果服务器已存在 `.env`，请将 `WEB_BIND=0.0.0.0`、`WEB_PORT=80` 更新后再部署；该文件不会被 Git 覆盖。

镜像由用户手动准备：`docker pull nginx:1.28.0-alpine`。两个服务复用此镜像，无需额外下载。脚本只使用已有镜像，不下载、不构建；缺少镜像时立即退出。

部署顺序：检查 Compose 配置及镜像 → `docker compose down --remove-orphans` 下架当前项目旧容器 → 启动新版并等待健康检查。不使用 `-v`，保留数据卷。更新期间存在短暂停机；新版启动失败会输出日志，不会自动回滚。

## 自动构建与版本校验

当前 `scripts\sync-remote.cmd -Deploy` 自动同步、按 Git 提交版本构建后端镜像（优先复用本地缓存），构建成功后才下架旧容器，随后启动并等待健康检查，最后核对运行中镜像的提交标签。失败的构建不会下架旧服务。后续无需手动执行 docker build。

首次环境仍需 Docker、基础镜像和 APP_PASSWORD 配置；后续交付初始化流程将进一步统一。仅健康检查通过不能证明镜像是新版，必须同时看到“后端版本核验通过”。