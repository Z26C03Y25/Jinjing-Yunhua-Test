# 第一阶段试运行（尚未远程实测）

1. Windows 执行 `scripts\sync-remote.cmd` 同步代码，暂不加 Deploy。
2. Ubuntu 仓库内执行 `docker build -f backend/Dockerfile -t jinjing-backend:stage1 .`，需要访问 Debian 镜像及软件源。脚本依旧不会自行构建下载。
3. 服务器仓库 `.env` 添加 `APP_PASSWORD=你设置的分析员密码`；不要复用服务器密码。用户名固定 analyst。
4. Windows 执行 `scripts\sync-remote.cmd -Deploy`。
5. 网页登录后上传 data/web_sqli.pcap，刷新任务至 complete，查看告警；再上传 benign_http.pcap 对照。

任务失败时服务器执行 `docker compose exec backend cat /state/任务ID/engine.log` 查看日志。

限制：尚未在 Ubuntu 验证规则与回放，不能声明检出率。仅经典 PCAP、单 worker、最多四项排队、手动刷新。规则管理及完整界面待做。apt 包尚未锁定，最终需要锁定实际验证版本并审计。密码经 HTTP 传输，当前演示应限制访问来源，最终需完善认证。数据保存在 ids-state 卷，重启保留；不挂载 Docker socket。
