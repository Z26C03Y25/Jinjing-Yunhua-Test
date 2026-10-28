"""Transactional, repeatable EVE import. No generated or simulated alerts."""
import datetime as dt
import json
import sqlite3

SCHEMA = '''
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, line_no INTEGER NOT NULL,
 event_type TEXT NOT NULL, timestamp TEXT, flow_id TEXT, src_ip TEXT,
 src_port INTEGER, dest_ip TEXT, dest_port INTEGER, proto TEXT,
 sid INTEGER, signature TEXT, severity INTEGER, raw_json TEXT NOT NULL,
 ingested_at TEXT NOT NULL, UNIQUE(task_id,line_no));
CREATE INDEX IF NOT EXISTS event_task ON events(task_id,event_type);
CREATE INDEX IF NOT EXISTS event_flow ON events(task_id,flow_id);
'''


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
    return count
