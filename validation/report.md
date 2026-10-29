# 真实 API 自验结果

| 场景 | 期望 TP | 期望 FN | 告警 FP |
| --- | --- | --- | --- |
| benign_http | 0 | 0 | 0 |
| dns_long | 1 | 0 | 0 |
| scan_slow | 0 | 1 | 0 |
| scan_syn | 1 | 0 | 0 |
| web_sqli | 1 | 0 | 0 |
| web_sqli_case | 1 | 0 | 0 |
| web_xss | 1 | 0 | 0 |

统计口径与未完成项见 report.json。正常样本无告警时 precision/recall 为 null，不将其伪称为 100%。