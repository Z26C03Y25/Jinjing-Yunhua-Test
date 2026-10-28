# 第二阶段审核

本次新增：告警按任务/源 IP/严重性/状态筛选、分页与排序；告警详情包含任务规则快照、关联 flow/http/dns/tls 和处置审计；总览 API 提供趋势和 Top 源/签名/目的端口；规则启停持久化并影响后续开始的任务。

当前总览以结构化文字呈现，图表与界面美化待后续完成。列表筛选 API 支持协议和 SID，界面控件待补。规则不支持在线编辑，启停后的规则快照由引擎执行前 `-T` 校验，失败会将任务标为 failed。

## 部署

1. Windows 同步：`scripts\sync-remote.cmd`。
2. Ubuntu 重建：`docker build --pull=false --progress=plain -f backend/Dockerfile -t jinjing-backend:stage1 .`。系统包安装层通常复用缓存。
3. Windows 部署：`scripts\sync-remote.cmd -Deploy`。旧数据库和分析员密码保留。

## 审核操作

- 登录后查看总览和规则；上传攻击样本，确认任务完成，查看告警详情。
- 将告警改为误报，按状态筛选，再展开详情确认审计记录。
- 关闭 SID 1000001 后重新上传 SQLi 样本，应在新任务中不再出现该 SID；历史任务保留原告警。随后恢复规则。
- Ubuntu 执行 `python3 validation/run_validation.py --url http://127.0.0.1`，输入分析员密码，脚本提交两份样本并等待任务真正 complete 后生成报告。不要在规则关闭时评测，除非有意测试 FN。

测试边界：本地已测事务回滚、幂等、筛选、SQL 注入字符串、关联事件任务隔离、重复告警与时间窗匹配；浏览器脚本通过 Node 语法检查。新增规则启停及自动评测的真实引擎行为尚待本次远程验证。未生成或填充虚构评测报告。
