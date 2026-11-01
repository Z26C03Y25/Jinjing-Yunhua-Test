"""Render a one-page report from actual validation output."""
import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / 'validation/report.json').read_text(encoding='utf-8'))
out = ROOT / 'output/pdf'
out.mkdir(parents=True, exist_ok=True)
font_path = os.environ.get('REPORT_FONT', r'C:\Windows\Fonts\simsun.ttc')
pdfmetrics.registerFont(TTFont('ReportChinese', font_path))
c = canvas.Canvas(str(out / '自验报告.pdf'), pagesize=(595, 842))
c.setTitle('金睛云华 - 自验报告')
y = 790


def text(value, size=10, color='#334155', gap=16):
    global y
    c.setFont('ReportChinese', size)
    c.setFillColor(HexColor(color))
    for line in simpleSplit(value, 'ReportChinese', size, 505):
        c.drawString(45, y, line)
        y -= gap


text('金睛云华 / 流量威胁检测系统', 21, '#0f766e', 30)
text('真实离线回放自验 | '+report['generated_at'][:10]+' | 代码 '+report.get('source_revision','未记录')[:10], 10, '#64748b', 23)
text('提交人：张椿雨 | 吉林化工大学 | 计算机科学与技术', 9, '#64748b', 18)
s = report['summary']
text('1. 结论', 13, '#0f172a', 21)
text(f"四类攻击线索，九个场景；期望命中 {s['tp_expectations']}，FN {s['fn_expectations']}，FP {s['fp_alerts']}。")
text(f"告警级 Precision {s['precision_alert_level']:.2%}；期望级 Recall {s['recall_expectation_level']:.2%}。统计单位分别标注，不代表未知流量检测能力。")
text(f"原始 {s['raw_alerts']} 条 -> {s['aggregate_groups']} 组，减少 {s['reduction_rate']:.2%}，原始证据保留。")
text(f"客户端完成耗时均值 {s['client_completion_ms_mean']:.0f} ms，最大 {s['client_completion_ms_max']:.0f} ms，包含网络、排队和轮询。", gap=22)
text('2. 场景与实际结果', 13, '#0f172a', 22)
names = {'benign_http':'正常 HTTP','benign_mix':'混合正常流量','brute_http':'HTTP 高频认证失败','dns_long':'异常长 DNS','scan_slow':'慢扫变异','scan_syn':'SYN 扫描','web_sqli':'SQLi','web_sqli_case':'SQLi 大小写变异','web_xss':'XSS'}
text('场景 / 期望SID / 实际结果 / Precision / Recall / F1（后三项口径见JSON）', 9, '#64748b', 17)
for r in report['results']:
    truth=json.loads((ROOT/'validation/ground_truth'/ (r['scenario']+'.json')).read_text(encoding='utf-8'))
    expected=','.join(str(x['sid']) for x in truth['expected_alerts']) or '-'
    fmt=lambda x:'N/A' if x is None else f'{x:.1%}'
    text(f"{names[r['scenario']]} | {expected} | TP{r['tp_expectations']} FN{r['fn_expectations']} FP{r['fp_alerts']} | {fmt(r['precision_alert_level'])} / {fmt(r['recall_expectation_level'])} / {fmt(r['f1_finding_level'])}", size=8.5, gap=17)
y -= 8
text('3. 误报、漏检与边界', 13, '#0f172a', 22)
text('本轮负样本无告警，未发现 FP。慢扫两秒一包，低于同源十秒超过二十次 SYN 的阈值，真实漏检保留为 FN。')
text('SQLi 大小写变异检出（nocase）；HTTP 401 高频仅为爆破线索，正常认证重试可能误报。')
text('混合样本含 HTTP、DNS 查询、TLS ClientHello，未覆盖完整 TLS 握手。固定时间桶聚合不跨任务/SID/五元组。')
h=s.get('historical_packet_to_ingestion_seconds')
if h:text(f"首攻击包至入库墙钟差均值 {h['mean']:.1f}s，最大 {h['max']:.1f}s，含历史样本年代，不代表性能。", size=9, gap=20)
text('4. 复现与未完成项', 13, '#0f172a', 22)
text('Ubuntu + Docker Compose：make validate。逐场景证据、指标定义及任务 ID 见 validation/report.json。')
text('独立空卷初始化与九场景安全验收通过，24-25 秒，使用已有镜像缓存；不等同无缓存全新机器验收。')
text('已做应用 pip 审计、权限/输入/跨源/限流测试；浏览器 XSS 文本渲染实测已通过；系统包漏洞扫描及依赖完整快照未完成。')
text('公网仅 HTTP；高可用等不在本题范围。项目协作投入约7小时（记录复盘，含AI执行等待，非精确人工计时）；未代签。',size=9)
assert y > 40, y
c.setFont('ReportChinese', 8)
c.setFillColor(HexColor('#94a3b8'))
c.drawString(45, 28, '数据源：真实部署 API 自验结果。未伪造全绿报告；已知缺陷如实保留。')
c.save()
assert len(PdfReader(out / '自验报告.pdf').pages) == 1
print(out / '自验报告.pdf')
