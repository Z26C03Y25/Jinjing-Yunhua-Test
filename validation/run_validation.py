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
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else (0 if expected else None)
    return {'scenario': truth['scenario'], 'tp_expectations': tp, 'fn_expectations': len(expected)-tp,
            'matched_alerts': matched_alerts, 'fp_alerts': len(fp), 'precision_alert_level': precision,
            'recall_expectation_level': recall, 'f1_mixed_units': f1, 'false_positives': fp}


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
        results.append(result)
    report = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'results': results,
              'limitations': ['当前攻击类别为 Web、扫描、异常 DNS，尚缺第四类攻击；正常基线尚缺 DNS/TLS', 'F1 为告警级精确率与期望级召回率的混合值，字段显式标注；最终报告需统一统计口径', '时延、去重率及变异测试尚未纳入']}
    (ROOT / 'validation/report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 真实 API 自验结果', '', '| 场景 | 期望 TP | 期望 FN | 告警 FP |', '| --- | --- | --- | --- |']
    lines += [f"| {r['scenario']} | {r['tp_expectations']} | {r['fn_expectations']} | {r['fp_alerts']} |" for r in results]
    lines += ['', '统计口径与未完成项见 report.json。正常样本无告警时 precision/recall 为 null，不将其伪称为 100%。']
    (ROOT / 'validation/report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
