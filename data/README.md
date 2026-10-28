# 自建流量

`python data/gen_pcap.py` 仅用 Python 标准库确定性生成 pcap，不发任何网络包。

- web_sqli.pcap：150 个 HTTP 会话、1500 包，首个请求带 SQLi 特征，其他请求为背景流量。
- benign_http.pcap：150 个正常 HTTP 会话、1500 包。

两个文件使用 Ethernet + IPv4 + TCP，包含握手、请求、响应、关闭和校验和。时间固定从 2026-01-01T10:00:00Z 开始，便于比对。ground truth 在生成前定义于 validation/ground_truth。

当前正常样本只有 HTTP，尚不满足题面最终要求的混合 HTTP/DNS/TLS 基线；后续扩充。
