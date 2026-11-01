"""Submit actual PCAPs to deployed API and evaluate; never synthesize alerts."""
import argparse
import base64
import datetime as dt
import getpass
import json
import os
import pathlib
import re
import time
import statistics
import subprocess
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def timestamp(value):
    value = value.replace('Z', '+00:00')
    value = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', value)
    return dt.datetime.fromisoformat(value)


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
        groups = api('/groups?task_id=' + task)
        result['aggregation'] = {key: groups[key] for key in ('raw_count', 'group_count', 'reduction_rate', 'window_seconds')}
        if found and truth['expected_alerts']:
            first_attack = min(timestamp(e['window']['start']) for e in truth['expected_alerts'])
            delays = [(timestamp(a['ingested_at']) - first_attack).total_seconds() for a in found]
            result['historical_packet_to_ingestion_seconds'] = {'mean': sum(delays)/len(delays), 'max': max(delays), 'interpretation': '历史样本墙钟差，包含样本年代，不可用来评价引擎处理速度'}
        results.append(result)
    summary = {'matched_alerts': sum(r['matched_alerts'] for r in results), 'fp_alerts': sum(r['fp_alerts'] for r in results), 'tp_expectations': sum(r['tp_expectations'] for r in results), 'fn_expectations': sum(r['fn_expectations'] for r in results)}
    summary['precision_alert_level'] = summary['matched_alerts'] / (summary['matched_alerts'] + summary['fp_alerts']) if summary['matched_alerts'] + summary['fp_alerts'] else None
    summary['recall_expectation_level'] = summary['tp_expectations'] / (summary['tp_expectations'] + summary['fn_expectations']) if summary['tp_expectations'] + summary['fn_expectations'] else None
    summary['precision_finding_level'] = summary['tp_expectations'] / (summary['tp_expectations'] + sum(r['fp_findings'] for r in results)) if summary['tp_expectations'] + sum(r['fp_findings'] for r in results) else None
    p, r = summary['precision_finding_level'], summary['recall_expectation_level']
    summary['f1_finding_level'] = 2*p*r/(p+r) if p is not None and r is not None and p+r else 0
    historical = [(x['historical_packet_to_ingestion_seconds'], x['matched_alerts']+x['fp_alerts']) for x in results if 'historical_packet_to_ingestion_seconds' in x]
    if historical:
        summary['historical_packet_to_ingestion_seconds'] = {'mean': sum(h['mean']*n for h,n in historical)/sum(n for h,n in historical), 'max': max(h['max'] for h,n in historical), 'interpretation':'首攻击包至入库的历史墙钟差，包含样本年代，不是性能指标'}
    summary['raw_alerts'] = sum(r['aggregation']['raw_count'] for r in results)
    summary['aggregate_groups'] = sum(r['aggregation']['group_count'] for r in results)
    summary['reduction_rate'] = 1-summary['aggregate_groups']/summary['raw_alerts'] if summary['raw_alerts'] else 0
    summary['client_completion_ms_mean'] = round(statistics.mean(r['client_observed_completion_ms'] for r in results), 2)
    summary['client_completion_ms_max'] = max(r['client_observed_completion_ms'] for r in results)
    revision = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    report = {'source_revision': revision, 'summary': summary, 'metric_definition': '原始告警精确率单列；finding 精确率/召回率/F1 使用期望命中项与同 SID 五元组十秒窗的误报组计数。完成耗时为客户端提交到收齐结果，含排队、网络和轮询，不是首攻击包到入库时延。', 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'results': results,
              'limitations': ['已覆盖 Web、扫描、异常 DNS、HTTP 认证失败四类线索；正常基线的 DNS 仅查询、TLS 仅 ClientHello，不含完整握手', '评测误报分组与业务固定时间桶聚合分开计算；原始告警始终保留', '离线抓包历史时间与处理时间分开，不用历史包到当前日期的差值冒充检测耗时']}
    (ROOT / 'validation/report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    def metric(value):
        return 'N/A' if value is None else f'{value:.2%}'
    lines = ['# 真实 API 自验结果', '', '生成时间：'+report['generated_at'], '代码版本：'+revision, '',
             '| 场景 | TP期望 | FN期望 | FP告警 | P告警级 | R期望级 | F1 finding级 | 完成耗时ms |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    lines += [f"| {x['scenario']} | {x['tp_expectations']} | {x['fn_expectations']} | {x['fp_alerts']} | {metric(x['precision_alert_level'])} | {metric(x['recall_expectation_level'])} | {metric(x['f1_finding_level'])} | {x['client_observed_completion_ms']} |" for x in results]
    lines += ['', f"总体告警级Precision：{metric(summary['precision_alert_level'])}；期望级Recall：{metric(summary['recall_expectation_level'])}；finding级F1：{metric(summary['f1_finding_level'])}。",
              f"原始{summary['raw_alerts']}条 → {summary['aggregate_groups']}组，去重率{metric(summary['reduction_rate'])}。",
              f"客户端完成耗时均值{summary['client_completion_ms_mean']}ms，最大{summary['client_completion_ms_max']}ms（含网络、排队、轮询）。",
              '', '## 统计口径', report['metric_definition'], '无告警且无期望的正常样本指标记为N/A，不冒充100%。总体Recall以期望项为分母，原始告警无法为漏掉的事件构造告警条数，因此不混淆单位。',
              '', '## 时延与误报', '首攻击包到入库的历史墙钟差均值/最大值见JSON summary.historical_packet_to_ingestion_seconds；包含样本年代，不能当作引擎处理性能。',
              '误报逐条保存在各场景false_positives数组；本轮为零则不存在可归因的误报记录。HTTP 401也可能来自正常重试，不能泛化为零误报。',
              '', '## 变异与FN', 'SQLi大小写变异被nocase检出；慢扫两秒一包，低于十秒超过二十次SYN阈值，保留FN，不修改期望追求全绿。']
    (ROOT / 'validation/report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
