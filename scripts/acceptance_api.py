import base64
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
env = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines() if '=' in line)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, user='analyst', data=None, origin=None):
    password = env['APP_PASSWORD' if user == 'analyst' else 'VIEWER_PASSWORD']
    headers = {'Authorization': 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()}
    if origin:
        headers['Origin'] = origin
    req = urllib.request.Request('http://127.0.0.1:18080/api' + path, data=data, headers=headers)
    try:
        with opener.open(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


checks = {}
checks['empty_database'] = request('/tasks')[1] == []
checks['viewer_login'] = request('/me', 'viewer')[1].get('readonly') is True
checks['viewer_write_denied'] = request('/tasks', 'viewer', b'x'*24)[0] == 403
checks['cross_origin_denied'] = request('/tasks', data=b'x'*24, origin='http://other.invalid')[0] == 403
checks['invalid_capture_rejected'] = request('/tasks', data=b'x'*24)[0] == 400
assert all(checks.values()), checks
os.environ['APP_PASSWORD'] = env['APP_PASSWORD']
import runpy
import sys
sys.argv = ['run_validation.py', '--url', 'http://127.0.0.1:18080']
runpy.run_path(str(root / 'validation/run_validation.py'), run_name='__main__')
report = json.loads((root / 'validation/report.json').read_text())
checks['nine_scenarios_completed'] = len(report['results']) == 9
checks['known_slow_scan_fn'] = next(r for r in report['results'] if r['scenario'] == 'scan_slow')['fn_expectations'] == 1
checks['benign_clean'] = all(r['fp_alerts'] == 0 for r in report['results'] if r['scenario'].startswith('benign'))
result = {'checks': checks, 'all_passed': all(checks.values()), 'elapsed_seconds': int(time.time())-int(os.environ['ACCEPTANCE_STARTED']), 'scope': '空容器和数据卷、已有基础镜像缓存；不是空操作系统或无缓存镜像环境', 'validation': report}
(root / 'validation/acceptance-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({'checks': checks, 'elapsed_seconds': result['elapsed_seconds']}, ensure_ascii=False))
assert result['all_passed']
