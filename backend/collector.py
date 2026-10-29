"""Transactional, repeatable EVE import. No generated or simulated alerts."""
import datetime as dt
import json
import sqlite3
import base64

SCHEMA = '''
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, line_no INTEGER NOT NULL,
 event_type TEXT NOT NULL, timestamp TEXT, flow_id TEXT, src_ip TEXT,
 src_port INTEGER, dest_ip TEXT, dest_port INTEGER, proto TEXT,
 sid INTEGER, signature TEXT, severity INTEGER, raw_json TEXT NOT NULL,
 ingested_at TEXT NOT NULL, UNIQUE(task_id,line_no));
CREATE INDEX IF NOT EXISTS event_task ON events(task_id,event_type);
CREATE INDEX IF NOT EXISTS event_flow ON events(task_id,flow_id);
CREATE TABLE IF NOT EXISTS dispositions(event_id INTEGER PRIMARY KEY,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event_id INTEGER,status TEXT,actor TEXT,changed_at TEXT);
CREATE TABLE IF NOT EXISTS rule_state(sid INTEGER PRIMARY KEY,enabled INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS protocol_metadata(
 event_id INTEGER PRIMARY KEY REFERENCES events(id), app_proto TEXT,
 http_host TEXT,http_url TEXT,http_method TEXT,http_status INTEGER,
 dns_name TEXT,dns_type TEXT,tls_sni TEXT,tls_version TEXT,
 packets_to_server INTEGER,packets_to_client INTEGER,
 bytes_to_server INTEGER,bytes_to_client INTEGER,payload_excerpt TEXT);
'''


def normalize(event):
    http, dns, tls, flow = (event.get(key) or {} for key in ('http', 'dns', 'tls', 'flow'))
    alert = event.get('alert') or {}
    payload = event.get('payload_printable') or alert.get('payload_printable')
    if not payload:
        encoded = event.get('payload') or alert.get('payload')
        if encoded:
            try:
                payload = base64.b64decode(encoded, validate=True).decode('utf-8', errors='replace')
            except (ValueError, TypeError):
                pass
    if not payload and http.get('url'):
        payload = '[HTTP metadata, not raw payload] ' + str(http.get('http_method', '')) + ' ' + str(http['url'])
    return (event.get('app_proto'), http.get('hostname'), http.get('url'), http.get('http_method'),
            http.get('status'), dns.get('rrname'), dns.get('rrtype'), tls.get('sni'), tls.get('version'),
            flow.get('pkts_toserver'), flow.get('pkts_toclient'), flow.get('bytes_toserver'),
            flow.get('bytes_toclient'), payload[:4096] if payload else None)


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def import_eve(db, task_id, path):
    count = 0
    with db:
        with open(path, encoding='utf-8') as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                event = json.loads(line)
                alert = event.get('alert') or {}
                cursor = db.execute('''INSERT OR IGNORE INTO events
                    (task_id,line_no,event_type,timestamp,flow_id,src_ip,src_port,
                    dest_ip,dest_port,proto,sid,signature,severity,raw_json,ingested_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (task_id, number, event.get('event_type', 'unknown'), event.get('timestamp'),
                     str(event['flow_id']) if 'flow_id' in event else None,
                     event.get('src_ip'), event.get('src_port'), event.get('dest_ip'),
                     event.get('dest_port'), event.get('proto'), alert.get('signature_id'),
                     alert.get('signature'), alert.get('severity'), line.strip(),
                     dt.datetime.now(dt.timezone.utc).isoformat()))
                count += cursor.rowcount
                if cursor.rowcount:
                    db.execute('INSERT INTO protocol_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (cursor.lastrowid,) + normalize(event))
    return count
