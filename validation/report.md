# 真实 API 自验结果

| 场景 | 期望 TP | 期望 FN | 告警 FP |
| --- | --- | --- | --- |
| benign_http | 0 | 0 | 0 |
| benign_mix | 0 | 0 | 0 |
| brute_http | 1 | 0 | 0 |
| dns_long | 1 | 0 | 0 |
| scan_slow | 0 | 1 | 0 |
| scan_syn | 1 | 0 | 0 |
| web_sqli | 1 | 0 | 0 |
| web_sqli_case | 1 | 0 | 0 |
| web_xss | 1 | 0 | 0 |

统计口径与未完成项见 report.json。正常样本无告警时 precision/recall 为 null，不将其伪称为 100%。

## 汇总与耗时

原始告警 2353 条，按任务/SID/五元组/十秒桶聚合为 1156 组，减少 50.87%。原始证据保留。

客户端完成耗时均值 2119.89 ms，最大 4047.0 ms；包含网络/排队/轮询，不等于引擎首包检测时延。历史样本首攻击包到入库墙钟差见 JSON，不能用来评价处理速度。
