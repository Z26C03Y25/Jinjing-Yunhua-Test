"""Submit actual PCAPs to deployed API and evaluate; never synthesize alerts."""
import argparse
import base64
import datetime as dt
import getpass
import json
import os
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def match(alert, expected):
    lo, hi = expected['dst_port_range']
    return (alert['sid'] == expected['sid'] and alert['src_ip'] == expected['src_ip']
            and alert['dest_ip'] == expected['dst_ip']
            and alert['proto'].upper() == expected['proto'].upper()
            and ('src_port' not in expected or alert['src_port'] == expected['src_port'])
            and lo <= alert['dest_port'] <= hi
            and timestamp(expected['window']['start']) <= timestamp(alert['timestamp']) <= timestamp(expected['window']['end']))


def evaluate(truth, alerts):
    expected = truth['expected_alerts']
    tp = sum(sum(match(a, e) for a in alerts) >= e.get('min_count', 1) for e in expected)
    fp = [a for a in alerts if truth['benign'] or not any(match(a, e) for e in expected)]
    matched_alerts = len(alerts) - len(fp)
    precision = matched_alerts / len(alerts) if alerts else None
    recall = tp / len(expected) if expected else None
    # One unexpected alert group is one false finding; repeated packets are not separate findings.
    fp_groups = {(a['sid'], a['src_ip'], a.get('src_port'), a['dest_ip'], a['dest_port'], a['proto'], int(timestamp(a['timestamp']).timestamp()) // 10) for a in fp}
    finding_precision = tp / (tp + len(fp_groups)) if tp + len(fp_groups) else None
    f1 = 2 * finding_precision * recall / (finding_precision + recall) if finding_precision is not None and recall is not None and finding_precision + recall else (0 if expected else None)
    return {'scenario': truth['scenario'], 'tp_expectations': tp, 'fn_expectations': len(expected)-tp,
            'matched_alerts': matched_alerts, 'fp_alerts': len(fp), 'precision_alert_level': precision,
            'recall_expectation_level': recall, 'precision_finding_level': finding_precision, 'fp_findings': len(fp_groups), 'f1_finding_level': f1, 'false_positives': fp}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1')
    args = parser.parse_args()
    password = os.environ.get('APP_PASSWORD') or getpass.getpass('分析员密码: ')
    auth = 'Basic ' + base64.b64encode(('analyst:' + password).encode()).decode()

    def api(path, data=None):
        request = urllib.request.Request(args.url.rstrip('/') + '/api' + path, data=data,
            headers={'Authorization': auth, 'Content-Type': 'application/octet-stream'})
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response)

    results = []
    for path in sorted((ROOT / 'validation/ground_truth').glob('*.json')):
        truth = json.loads(path.read_text(encoding='utf-8'))
        started = time.monotonic()
        task = api('/tasks', (ROOT / 'data' / truth['pcap']).read_bytes())['id']
        deadline = time.monotonic() + 300
        while True:
            row = next(r for r in api('/tasks') if r['id'] == task)
            if row['status'] == 'failed':
                raise RuntimeError(row['error'])
            if row['status'] == 'complete':
                break
            if time.monotonic() > deadline:
                raise TimeoutError(task)
            time.sleep(1)
        found, page = [], 1
        while True:
            batch = api(f'/alerts?task_id={task}&size=100&page={page}')
            found.extend(batch['items'])
            if len(found) >= batch['total']:
                break
            page += 1
        result = evaluate(truth, found)
        result['task_id'] = task
        result['client_observed_completion_ms'] = round((time.monotonic() - started) * 1000, 2)
        results.append(result)
    summary = {'matched_alerts': sum(r['matched_alerts'] for r in results), 'fp_alerts': sum(r['fp_alerts'] for r in results), 'tp_expectations': sum(r['tp_expectations'] for r in results), 'fn_expectations': sum(r['fn_expectations'] for r in results)}
    summary['precision_alert_level'] = summary['matched_alerts'] / (summary['matched_alerts'] + summary['fp_alerts']) if summary['matched_alerts'] + summary['fp_alerts'] else None
    summary['recall_expectation_level'] = summary['tp_expectations'] / (summary['tp_expectations'] + summary['fn_expectations']) if summary['tp_expectations'] + summary['fn_expectations'] else None
    report = {'summary': summary, 'metric_definition': '原始告警精确率单列；finding 精确率/召回率/F1 使用期望命中项与同 SID 五元组十秒窗的误报组计数。完成耗时为客户端提交到收齐结果，含排队、网络和轮询，不是首攻击包到入库时延。', 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'results': results,
              'limitations': ['已覆盖 Web、扫描、异常 DNS、HTTP 认证失败四类线索；正常基线的 DNS 仅查询、TLS 仅 ClientHello，不含完整握手', 'finding 聚合只用于评测误报计数，尚非业务告警抑制功能', '未实现业务去重率；离线抓包历史时间与处理时间分开，不用历史包到当前日期的差值冒充检测耗时']}
    (ROOT / 'validation/report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 真实 API 自验结果', '', '| 场景 | 期望 TP | 期望 FN | 告警 FP |', '| --- | --- | --- | --- |']
    lines += [f"| {r['scenario']} | {r['tp_expectations']} | {r['fn_expectations']} | {r['fp_alerts']} |" for r in results]
    lines += ['', '统计口径与未完成项见 report.json。正常样本无告警时 precision/recall 为 null，不将其伪称为 100%。']
    (ROOT / 'validation/report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
