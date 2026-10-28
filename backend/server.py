"""Stage-one offline IDS API. Suricata executes without shell or Docker socket."""
import datetime as dt
import re
from queries import alerts, overview, detail
import base64
import concurrent.futures
import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from collector import connect, import_eve

STATE = pathlib.Path(os.environ.get('STATE_DIR', '/state'))
STATE.mkdir(parents=True, exist_ok=True)
DB = STATE / 'events.sqlite'
PASSWORD = os.environ.get('APP_PASSWORD', '')
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
SLOTS = threading.BoundedSemaphore(4)
RULES = pathlib.Path(os.environ.get('RULES_PATH', '/app/rules/local.rules'))
RULE_LOCK = threading.Lock()

def rule_list():
    with database() as db:
        states = dict(db.execute('SELECT sid,enabled FROM rule_state'))
    return [{'sid': int(re.search(r'sid:(\d+);', line)[1]), 'raw': line, 'enabled': bool(states.get(int(re.search(r'sid:(\d+);', line)[1]), 1))} for line in RULES.read_text().splitlines() if line.startswith('alert ')]


def database():
    return connect(DB)


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
        try:
            scheme, encoded = self.headers.get('Authorization', '').split(' ', 1)
            value = base64.b64decode(encoded, validate=True).decode()
            return scheme.lower() == 'basic' and hmac.compare_digest(value.encode(), ('analyst:' + PASSWORD).encode())
        except (ValueError, UnicodeError):
            return False

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/api/healthz':
            return self.send_json(200, {'status': 'ok', 'service': 'offline-ids'})
        if not self.authorized():
            return self.send_json(401, {'error': '需要登录，用户名 analyst'})
        with database() as db:
            if url.path == '/api/tasks':
                return self.send_json(200, [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY rowid DESC LIMIT 100')])
            if url.path == '/api/overview':
                return self.send_json(200, overview(db))
            if url.path == '/api/rules':
                return self.send_json(200, rule_list())
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
                    result['rule'] = next((line for line in source.read_text().splitlines() if 'sid:'+str(result['sid'])+';' in line), '历史规则快照不可用')
                return self.send_json(200 if result else 404, result or {'error': 'not_found'})
        return self.send_json(404, {'error': 'not_found'})

    def do_POST(self):
        if not self.authorized():
            return self.send_json(401, {'error': 'unauthorized'})
        if self.path == '/api/rules' or re.fullmatch(r'/api/alerts/\d+/status', self.path):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('invalid_body')
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(size))
                with database() as db:
                    if self.path == '/api/rules':
                        sid = int(body['sid'])
                        if sid not in [r['sid'] for r in rule_list()] or type(body['enabled']) is not bool:
                            raise ValueError('invalid_rule')
                        with RULE_LOCK:
                            db.execute('INSERT OR REPLACE INTO rule_state VALUES (?,?)', (sid, int(body['enabled'])))
                    else:
                        event_id = int(self.path.split('/')[3])
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
