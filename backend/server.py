"""Stage-one offline IDS API. Suricata executes without shell or Docker socket."""
import datetime as dt
import re
from queries import alerts, overview, detail, aggregate_alerts
import base64
import concurrent.futures
import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import shutil
import subprocess
import threading
import uuid
from contextlib import contextmanager
from security import FailureLimiter
from rule_editor import publish, lifecycle, validate_rule
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from collector import connect, import_eve

STATE = pathlib.Path(os.environ.get('STATE_DIR', '/state'))
STATE.mkdir(parents=True, exist_ok=True)
DB = STATE / 'events.sqlite'
PASSWORD = os.environ.get('APP_PASSWORD', '')
VIEWER_PASSWORD = os.environ.get('VIEWER_PASSWORD', '')
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
SLOTS = threading.BoundedSemaphore(4)
RULES = pathlib.Path(os.environ.get('RULES_PATH', '/app/rules/local.rules'))
RULE_LOCK = threading.Lock()
AUTH_FAILURES = FailureLimiter()

def rule_list(include_archived=False):
    with database() as db:
        states = dict(db.execute('SELECT sid,enabled FROM rule_state'))
        overrides = {r['sid']: (r['raw'], r['revision']) for r in db.execute('SELECT * FROM rule_overrides')}
        catalog = {r['sid']: dict(r) for r in db.execute('SELECT * FROM rule_catalog')}
    baselines = {int(re.search(r'\bsid\s*:\s*(\d+)\s*;', line)[1]): line
                 for line in RULES.read_text().splitlines() if line.startswith('alert ')}
    for sid, row in catalog.items():
        baselines.setdefault(sid, row['baseline'])
    return [{'sid': sid, 'raw': overrides.get(sid, (raw, 0))[0],
             'revision': overrides.get(sid, (raw, 0))[1], 'baseline': raw,
             'archived': bool(catalog.get(sid, {}).get('archived', 0)),
             'enabled': bool(states.get(sid, 1)) and not catalog.get(sid, {}).get('archived', 0)}
            for sid, raw in sorted(baselines.items())
            if include_archived or not catalog.get(sid, {}).get('archived', 0)]


@contextmanager
def database():
    connection = connect(DB)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


with database() as db:
    db.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,status TEXT, error TEXT, sha256 TEXT)')
    db.execute("UPDATE tasks SET status='failed',error='Service restarted during processing; please resubmit' WHERE status IN ('queued','running')")


def process(task):
    folder = STATE / task
    try:
        with database() as db:
            db.execute("UPDATE tasks SET status='running' WHERE id=?", (task,))
        with RULE_LOCK:
            snapshot = [r['raw'] for r in rule_list() if r['enabled']]
            (folder / 'active.rules').write_text('\n'.join(snapshot) + '\n')
        command = ['suricata', '-c', '/etc/suricata/suricata.yaml', '-S', str(folder / 'active.rules'),
                   '--set', 'stream.checksum-validation=no']
        with (folder / 'engine.log').open('w') as log:
            subprocess.run(command + ['-T', '-l', str(folder)], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
            subprocess.run(command + ['--runmode', 'single', '-r', str(folder / 'input.pcap'), '-l', str(folder)],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        with database() as db:
            import_eve(db, task, folder / 'eve.json')
            db.execute("UPDATE tasks SET status='complete' WHERE id=?", (task,))
    except Exception as exc:
        with database() as db:
            db.execute("UPDATE tasks SET status='failed',error=? WHERE id=?", (str(exc), task))
    finally:
        SLOTS.release()


class API(BaseHTTPRequestHandler):
    def send_json(self, code, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        if code == 401:
            self.send_header('WWW-Authenticate', 'Basic realm="IDS"')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        key = self.headers.get('X-Real-IP') or self.client_address[0]
        self.auth_limited = AUTH_FAILURES.blocked(key)
        if self.auth_limited:
            return False
        try:
            scheme, encoded = self.headers.get('Authorization', '').split(' ', 1)
            value = base64.b64decode(encoded, validate=True).decode()
            if scheme.lower() != 'basic':
                raise ValueError('unsupported authentication scheme')
            for actor, password in [('analyst', PASSWORD), ('viewer', VIEWER_PASSWORD)]:
                if password and hmac.compare_digest(value.encode(), (actor + ':' + password).encode()):
                    self.actor = actor
                    AUTH_FAILURES.reset(key)
                    return True
        except (ValueError, UnicodeError):
            pass
        AUTH_FAILURES.record_failure(key)
        return False

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/api/healthz':
            return self.send_json(200, {'status': 'ok', 'service': 'offline-ids'})
        if not self.authorized():
            return self.send_json(429 if self.auth_limited else 401, {'error': '登录失败过多，请一分钟后重试' if self.auth_limited else '需要登录，用户名 analyst'})
        with database() as db:
            if url.path == '/api/me':
                return self.send_json(200, {'username': self.actor, 'readonly': self.actor == 'viewer'})
            if url.path == '/api/groups':
                query = parse_qs(url.query)
                try:
                    window = int(query.get('window', ['10'])[0])
                    task = query.get('task_id', [''])[0]
                    rows = db.execute("SELECT * FROM events WHERE event_type='alert' AND task_id=? ORDER BY timestamp,id LIMIT 50001", (task,)).fetchall()
                    if len(rows) > 50000:
                        return self.send_json(413, {'error': '单任务聚合上限为 50000 条'})
                    groups = aggregate_alerts(rows, window)
                    return self.send_json(200, {'raw_count': len(rows), 'group_count': len(groups), 'reduction_rate': 1-len(groups)/len(rows) if rows else 0, 'items': groups[:200], 'window_seconds': window})
                except ValueError:
                    return self.send_json(400, {'error': '聚合窗口应为 1 到 3600 秒整数'})
            if url.path == '/api/tasks':
                return self.send_json(200, [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY rowid DESC LIMIT 100')])
            if url.path == '/api/overview':
                return self.send_json(200, overview(db))
            if re.fullmatch(r'/api/rules/\d+/history', url.path):
                sid = int(url.path.split('/')[3])
                baseline = next((r['baseline'] for r in rule_list(True) if r['sid'] == sid), None)
                if baseline is None:
                    return self.send_json(404, {'error': 'not_found'})
                rows = [dict(r) for r in db.execute('SELECT sid,revision,raw,actor,created_at FROM rule_revisions WHERE sid=? ORDER BY revision DESC', (sid,))]
                rows.append({'sid': sid, 'revision': 0, 'raw': baseline, 'actor': 'repository', 'created_at': None})
                for row in rows:
                    action = db.execute('SELECT action FROM rule_actions WHERE sid=? AND revision=?', (sid, row['revision'])).fetchone()
                    row['action'] = action[0] if action else 'edit' if row['revision'] else 'baseline'
                return self.send_json(200, rows)
            if url.path == '/api/rules':
                return self.send_json(200, rule_list(parse_qs(url.query).get('include_archived') == ['1']))
            if url.path == '/api/alerts':
                try:
                    return self.send_json(200, alerts(db, parse_qs(url.query)))
                except ValueError:
                    return self.send_json(400, {'error': '分页参数必须是整数'})
            if re.fullmatch(r'/api/alerts/\d+', url.path):
                result = detail(db, int(url.path.rsplit('/', 1)[1]))
                if result:
                    snapshot = STATE / result['task_id'] / 'active.rules'
                    source = snapshot if snapshot.exists() else RULES
                    result['rule'] = next((line for line in source.read_text().splitlines() if re.search(r'\bsid\s*:\s*'+str(result['sid'])+r'\s*;', line)), '历史规则快照不可用')
                return self.send_json(200 if result else 404, result or {'error': 'not_found'})
        return self.send_json(404, {'error': 'not_found'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send_json(403, {'error': 'cross_origin_request_rejected'})
        if not self.authorized():
            return self.send_json(429 if self.auth_limited else 401, {'error': '登录失败过多，请一分钟后重试' if self.auth_limited else 'unauthorized'})
        if self.actor != 'analyst':
            return self.send_json(403, {'error': '只读角色不能执行修改操作'})
        if self.path == '/api/rules/create' or re.fullmatch(r'/api/rules/\d+(/rollback|/archive|/restore)?', self.path):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 32768 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('规则请求大小无效')
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('请求必须是 JSON 对象')
                sid = body.get('sid') if self.path == '/api/rules/create' else int(self.path.split('/')[3])
                with RULE_LOCK:
                    all_rules = rule_list(True)
                    candidates = [r for r in all_rules if not r['archived']]
                    now = dt.datetime.now(dt.timezone.utc).isoformat()
                    if self.path == '/api/rules/create':
                        raw = validate_rule(body.get('raw'), sid)
                        if sid in [r['sid'] for r in all_rules]:
                            raise RuntimeError('SID 已存在（含已归档规则），请改用其他编号或恢复原规则')
                        with database() as db:
                            revision = publish(db, sid, raw, 0, self.actor, candidates + [{'sid': sid, 'raw': raw}], STATE, now)
                            db.execute('INSERT INTO rule_catalog(sid,baseline) VALUES (?,?)', (sid, raw))
                            db.execute('INSERT INTO rule_actions(sid,action,revision,actor,created_at) VALUES (?,?,?,?,?)', (sid, 'create', revision, self.actor, now))
                        return self.send_json(201, {'ok': True, 'revision': revision})
                    current = next((r for r in all_rules if r['sid'] == sid), None)
                    if current and self.path.endswith(('/archive', '/restore')):
                        with database() as db:
                            revision = lifecycle(db, current, self.path.rsplit('/', 1)[1], body.get('base_revision'), self.actor, STATE, all_rules, now)
                        return self.send_json(200, {'ok': True, 'revision': revision})
                    if sid not in [r['sid'] for r in candidates]:
                        return self.send_json(404, {'error': '规则不存在'})
                    with database() as db:
                        raw = body.get('raw')
                        if self.path.endswith('/rollback'):
                            target = body.get('revision')
                            if type(target) is not int:
                                raise ValueError('回滚版本必须是整数')
                            if target == 0:
                                raw = current['baseline']
                            else:
                                row = db.execute('SELECT raw FROM rule_revisions WHERE sid=? AND revision=?', (sid, target)).fetchone()
                                if not row:
                                    raise ValueError('历史版本不存在')
                                raw = row[0]
                        revision = publish(db, sid, raw, body.get('base_revision'), self.actor, candidates, STATE, dt.datetime.now(dt.timezone.utc).isoformat())
                        db.execute('INSERT INTO rule_actions(sid,action,revision,actor,created_at) VALUES (?,?,?,?,?)', (sid, 'rollback' if self.path.endswith('/rollback') else 'edit', revision, self.actor, now))
                return self.send_json(200, {'ok': True, 'revision': revision, 'note': '已通过真实引擎校验，对后续任务生效'})
            except RuntimeError as exc:
                return self.send_json(409, {'error': str(exc)})
            except (ValueError, KeyError, TypeError) as exc:
                return self.send_json(422, {'error': str(exc)})
            except (subprocess.TimeoutExpired, OSError):
                return self.send_json(503, {'error': '引擎校验未完成，旧规则保持不变，请稍后重试'})
        if self.path == '/api/rules' or re.fullmatch(r'/api/alerts/\d+/(status|notes)', self.path):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                limit = 16384 if self.path.endswith('/notes') else 4096
                if not 0 < size <= limit or self.headers.get('Transfer-Encoding'):
                    raise ValueError('invalid_body')
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('请求必须是 JSON 对象')
                with database() as db:
                    if self.path == '/api/rules':
                        sid = int(body['sid'])
                        if sid not in [r['sid'] for r in rule_list()] or type(body['enabled']) is not bool:
                            raise ValueError('invalid_rule')
                        with RULE_LOCK:
                            db.execute('INSERT OR REPLACE INTO rule_state VALUES (?,?)', (sid, int(body['enabled'])))
                    else:
                        event_id = int(self.path.split('/')[3])
                        if self.path.endswith('/notes'):
                            conclusion, recommendation = body.get('conclusion'), body.get('recommendation', '')
                            if not isinstance(conclusion, str) or not conclusion.strip() or len(conclusion) > 1500 or not isinstance(recommendation, str) or len(recommendation) > 1500:
                                raise ValueError('invalid_notes')
                            if not db.execute("SELECT 1 FROM events WHERE id=? AND event_type='alert'", (event_id,)).fetchone():
                                return self.send_json(404, {'error': 'not_found'})
                            db.execute('INSERT INTO analyst_notes(event_id,conclusion,recommendation,actor,created_at) VALUES (?,?,?,?,?)', (event_id, conclusion.strip(), recommendation.strip(), self.actor, dt.datetime.now(dt.timezone.utc).isoformat()))
                            db.commit()
                            return self.send_json(200, {'ok': True})
                        if body['status'] not in ('new', 'confirmed', 'false_positive', 'ignored'):
                            raise ValueError('invalid_status')
                        if not db.execute("SELECT 1 FROM events WHERE id=? AND event_type='alert'", (event_id,)).fetchone():
                            return self.send_json(404, {'error': 'not_found'})
                        db.execute('INSERT OR REPLACE INTO dispositions VALUES (?,?)', (event_id, body['status']))
                        db.execute('INSERT INTO audit(event_id,status,actor,changed_at) VALUES (?,?,?,?)', (event_id, body['status'], 'analyst', dt.datetime.now(dt.timezone.utc).isoformat()))
                return self.send_json(200, {'ok': True, 'note': '规则状态作用于后续开始执行的任务'})
            except (ValueError, KeyError, TypeError):
                return self.send_json(400, {'error': 'invalid_request'})
        if self.path != '/api/tasks':
            return self.send_json(404, {'error': 'not_found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.send_json(400, {'error': 'invalid_length'})
        if self.headers.get('Transfer-Encoding') or not 24 <= size <= 20 * 1024 * 1024:
            return self.send_json(413, {'error': '请上传 24 字节至 20 MB 的 PCAP 文件'})
        # Reserve room for EVE output and SQLite, rather than accepting into a full disk.
        if shutil.disk_usage(STATE).free < max(512 * 1024 * 1024, size * 20):
            return self.send_json(507, {'error': '证据存储可用空间不足，请先备份并由管理员处理容量'})
        if not SLOTS.acquire(blocking=False):
            return self.send_json(429, {'error': '队列已满，请稍后重试'})
        try:
            self.connection.settimeout(30)
            data = self.rfile.read(size)
            if len(data) != size or data[:4] not in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'):
                SLOTS.release()
                return self.send_json(400, {'error': '当前仅接受经典 PCAP 二进制格式'})
            task = uuid.uuid4().hex
            folder = STATE / task
            folder.mkdir()
            (folder / 'input.pcap').write_bytes(data)
            with database() as db:
                db.execute('INSERT INTO tasks VALUES (?,?,?,?)', (task, 'queued', None, hashlib.sha256(data).hexdigest()))
            POOL.submit(process, task)
        except Exception:
            SLOTS.release()
            return self.send_json(500, {'error': '上传失败'})
        return self.send_json(202, {'id': task})


if __name__ == '__main__':
    if not PASSWORD:
        raise SystemExit('APP_PASSWORD is required')
    ThreadingHTTPServer(('0.0.0.0', 8000), API).serve_forever()
