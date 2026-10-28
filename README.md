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

运行 `scripts\sync-remote.cmd -Deploy`，需要服务器支持 `docker compose up --wait`，且登录用户有 Docker 权限。首次拉取镜像需要访问镜像仓库。默认访问地址为服务器本机 `http://127.0.0.1:8080`，健康检查为 `/healthz`。

在本地另开终端建立隧道（保持窗口开启）：

```bat
C:\Windows\System32\OpenSSH\ssh.exe -N -L 8080:127.0.0.1:8080 root@123.57.158.71
```

随后浏览器打开 `http://localhost:8080`。如需调整监听地址和端口，在服务器仓库目录复制 `.env.example` 为 `.env` 后修改；`.env` 不提交。

镜像由用户在服务器手动准备，例如 `docker pull nginx:1.28.0-alpine`。部署脚本只使用已有镜像，不下载、不构建；缺少镜像时立即退出并提示镜像名。也可在服务器 `.env` 设置 `WEB_IMAGE` 为已准备的 Nginx 兼容镜像标签。
