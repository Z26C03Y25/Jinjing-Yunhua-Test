# 自建流量

`python data/gen_pcap.py` 仅用 Python 标准库确定性生成 pcap，不发任何网络包。

- web_sqli.pcap：150 个 HTTP 会话、1500 包，首个请求带 SQLi 特征，其他请求为背景流量。
- benign_http.pcap：150 个正常 HTTP 会话、1500 包。

两个文件使用 Ethernet + IPv4 + TCP，包含握手、请求、响应、关闭和校验和。时间固定从 2026-01-01T10:00:00Z 开始，便于比对。ground truth 在生成前定义于 validation/ground_truth。

当前正常样本只有 HTTP，尚不满足题面最终要求的混合 HTTP/DNS/TLS 基线；后续扩充。

## 扩展样本

新增 SYN 扫描、慢扫、异常长 DNS、SQLi 大小写变种、XSS、HTTP 401 高频认证失败和混合正常样本。四类攻击为扫描、Web 攻击、异常 DNS、HTTP 认证爆破线索。混合基线包含 HTTP、DNS 查询及 TLS ClientHello；TLS/DNS 不构成完整会话，不能声称覆盖所有正常业务。慢扫预期仍保留为攻击期望，用于展示阈值检测的漏检边界。
