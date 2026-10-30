"""Actual deployed engine acceptance; always restore the original rule content."""
import base64
import datetime
import json
import os
import pathlib
import urllib.error
import urllib.request

base = os.environ.get('TEST_URL', 'http://123.57.158.71').rstrip('/')
auth = 'Basic ' + base64.b64encode(('analyst:' + os.environ['APP_PASSWORD']).encode()).decode()


def api(path, body=None, expected=200):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + '/api' + path, data=data,
        headers={'Authorization': auth, 'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(request, timeout=45)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        result = json.load(response)
        assert response.code == expected, (response.code, result)
        return result


original = next(r for r in api('/rules') if r['sid'] == 1000001)
path = '/rules/1000001'
checks = []
try:
    invalid = original['raw'].rstrip().removesuffix(')') + ' invalid_keyword:yes;)'
    api(path, {'raw': invalid, 'base_revision': original['revision']}, 422)
    current = next(r for r in api('/rules') if r['sid'] == 1000001)
    assert current == original
    checks.append('real_engine_rejects_invalid_rule_without_change')
    # A comment in the signature changes text without changing detection logic.
    edited = original['raw'].replace('msg:"', 'msg:"Acceptance test: ', 1)
    published = api(path, {'raw': edited, 'base_revision': original['revision']})
    checks.append('real_engine_accepts_valid_rule')
    api(path, {'raw': original['raw'], 'base_revision': original['revision']}, 409)
    checks.append('stale_revision_rejected')
    history = api(path + '/history')
    assert any(r['revision'] == published['revision'] and r['raw'] == edited for r in history)
    checks.append('published_content_in_audit_history')
finally:
    current = next(r for r in api('/rules') if r['sid'] == 1000001)
    if current['raw'] != original['raw']:
        restored = api(path + '/rollback', {'revision': original['revision'], 'base_revision': current['revision']})
        assert next(r for r in api('/rules') if r['sid'] == 1000001)['raw'] == original['raw']
        checks.append('rollback_restores_original_content_as_new_revision')

report = {'tested_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'url': base, 'checks': checks, 'passed': len(checks) == 5}
pathlib.Path('validation/rule-editor-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
