# 依赖审计记录

日期：2026-10-29。工具 pip-audit 2.9.0，隔离安装于被 Git 忽略的本地 .audit-tools，不加入应用镜像。

实际命令：

```sh
python -m pip_audit --disable-pip --no-deps -r backend/requirements.txt -f json -o validation/pip-audit.json
```

实际退出码 0，输出 No known vulnerabilities found，原始报告见 pip-audit.json。backend/requirements.txt 仅注释，因为 API/采集器/生成器使用标准库；因此审计对象为零个 pip 第三方应用包。前端为原生 JS/CSS，不安装 npm 应用包。

不能据此认定整个容器无漏洞：Suricata、Nginx、Debian 原生库和 Python 解释器不在 pip-audit 范围，系统包审计仍需完成。工具首次执行缺少 --no-deps 被拒绝，修正参数后才得到本报告；未把失败输出作为成功。

可用 scripts/audit-python.ps1 在安装了 Python 的 Windows 环境中复现，需网络下载审计工具。首次启动脚本已通过 Git Bash 的 `bash -n` 语法检查，但不是干净 Ubuntu 实际启动验证。
