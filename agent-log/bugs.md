# 已实际发生的 Agent 实现问题

## B6：事务上下文没有关闭 SQLite 连接

- 现象：新增真实 HTTP 安全测试的接口断言通过，但 Windows 清理临时 SQLite 文件时失败，文件仍被打开。
- 原因：sqlite3 的 `with connection` 仅提交/回滚事务，不自动 close；原 server.database 直接返回连接。
- 修复：用 contextmanager 包装事务并在 finally 中显式关闭连接，保留采集器事务逻辑。
- 验证：七项本地回归含真实回环 HTTP 测试全部通过，临时目录正常清理。新增测试使用固定虚构测试凭据，不是实际服务器密码。

## B5：未核实 Debian 12 的 Suricata 包来源

- 现象：软件源索引成功下载，但普通 bookworm 源没有 suricata 安装候选版本。
- 原因：Dockerfile 直接假设主仓库提供包，未先核对当前包索引。
- 修复：根据 Debian 官方包索引增加 bookworm-backports，指定 Suricata 1:7.0.10-1~bpo12+1；构建打印 build-info。
- 验证：官方包索引已核对，真实容器构建仍待服务器重试，尚未宣称成功。

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
# 2026-10-30：恢复演练的 Compose 参数兼容错误

AI首次使用docker compose run --tmpfs；实际服务器返回unknown flag，备份归档已生成且后端已恢复运行，恢复检查尚未执行。修复为使用服务配置已有的私有/tmp tmpfs并恢复到/tmp/restore，不挂载或覆盖业务目录。验收必须以修复后真正执行结果为准，不能把归档成功当作恢复成功。

# 2026-10-30：SQLite检查连接未关闭

备份恢复测试在Windows临时目录清理时出现WinError32。原因是sqlite3连接的with只管理事务，不关闭连接。改用contextlib.closing，完整11项测试通过。若忽略，会留下数据库句柄并影响文件操作。

# 2026-10-30：备份命令读走远程脚本输入

首次修复tmpfs参数后恢复成功，但命令正常结束却没有后续独立验收输出。排查发现远程脚本通过管道送给bash，docker compose run默认附带stdin，可能读走后续命令。两处维护容器调用均显式从/dev/null读取，再重跑串联路径验证。只检查退出码无法发现这种漏执行。

# 2026-10-30：独立登录页被浏览器原生认证框干扰

真实Chrome错误密码测试等待页面错误提示超时。原API的401总带WWW-Authenticate，触发浏览器原生Basic认证交互，使自建登录流程无法正常结束。前端请求标识XMLHttpRequest，后端仅对这类请求省略challenge，仍返回401且继续校验角色和密码；非XHR客户端行为保留。服务器实测错误密码、回车登录、深链接保护、退出清理通过，检测与CRUD回归通过。

