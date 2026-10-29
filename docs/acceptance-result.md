# 独立初始化验收结果

2026-10-29，通过 Windows SSH 自动执行 scripts/acceptance.sh。第一次运行发现宿主机 Python 无法解析 +0000 时区，已修复后重新验收。

实际第二次结果：empty_database、viewer_login、viewer_write_denied、cross_origin_denied、invalid_capture_rejected、nine_scenarios_completed、known_slow_scan_fn、benign_clean 均为 true，耗时 24 秒。

后续安全加固版 a13f86f 再次独立验收：上述项目及 authentication_failure_throttled 均为 true，同为24秒（已有镜像缓存）。演示环境健康检查和版本核验通过，公网 CSP 头已检查。

测试在独立 mktemp 目录、Compose 项目、127.0.0.1:18080 和全新数据卷中运行；bootstrap 自动生成两角色随机密码，日志未对外打印临时凭据。退出清理仅删除独立测试容器、网络、数据卷及临时目录。没有删除演示系统数据。完整机器报告保存在服务器原仓库 .runtime-reports/acceptance-report.json，不纳入 Git。

边界：使用已有 Debian/Nginx 镜像与系统包构建缓存，非全新操作系统/无缓存下载环境；不能将 24 秒当作干净机器首次安装耗时。浏览器视觉、系统包漏洞扫描和公网 HTTP 传输保护未由此验证。
