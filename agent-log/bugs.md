# 已实际发生的 Agent 实现问题

## B1：Git 自带 SSH 与中文用户目录不兼容

- 现象：SSH 尝试读取乱码的 `/c/Users/.../.ssh`，无法保存 known_hosts，认证失败。
- 修复：Git 显式使用 Windows OpenSSH，并指定密钥与 known_hosts 路径。
- 验证：用户运行日志显示 GitHub 认证及推送成功。

## B2：自动填密程序放在中文 TEMP 路径

- 现象：CreateProcessW error 2、ssh_askpass 无法启动。
- 修复：放到当前英文仓库路径的 `.git` 临时目录，加入启动及解密自检，退出清理。
- 验证：本地测试辅助程序加解密往返成功；用户后续日志确认无口令重复提示且推送成功。

## B3：题目文件哈希读取不兼容

- 现象：用户环境未识别 Get-FileHash；改用 File.OpenRead 后又因 Word 占用失败。
- 修复：使用 .NET SHA256 和允许读写共享的只读文件流，排除 Word 锁文件。
- 验证：本地共享读取成功；用户远程日志确认题目 SHA256 校验成功。

## B4：入口网络配置缺少独立入口网络

- 初版将 web 和 backend 都只放在 internal 网络，用户浏览器访问失败。
- 修复：web 加入 edge 桥接网络，同时保留 app 内部网络；backend 只加入 app。
- 验证：用户后续截图显示页面可通过公网 80 访问；当时未获得网络抓包，不能将该配置认定为唯一根因。
