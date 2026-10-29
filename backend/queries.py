import json
import datetime as dt
import re
from collector import normalize


def aggregate_alerts(rows, seconds=10):
    if not 1 <= seconds <= 3600:
        raise ValueError('window must be between 1 and 3600 seconds')
    groups = {}
    for row in rows:
        row = dict(row)
        value = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', row['timestamp'].replace('Z', '+00:00'))
        timestamp = dt.datetime.fromisoformat(value).timestamp()
        key = (row['task_id'], row['sid'], row['src_ip'], row['src_port'], row['dest_ip'], row['dest_port'], row['proto'], int(timestamp // seconds))
        if key not in groups:
            groups[key] = {**row, 'count': 0, 'first_seen': row['timestamp'], 'last_seen': row['timestamp']}
        group = groups[key]
        group['count'] += 1
        group['first_seen'] = min(group['first_seen'], row['timestamp'])
        group['last_seen'] = max(group['last_seen'], row['timestamp'])
    return list(groups.values())


def alerts(db, query):
    clauses, args = ["e.event_type='alert'"], []
    for field in ('task_id', 'src_ip', 'proto', 'severity', 'sid'):
        value = query.get(field, [''])[0]
        if value:
            clauses.append('e.' + field + '=?')
            args.append(value)
    if query.get('status', [''])[0]:
        clauses.append("COALESCE(d.status,'new')=?")
        args.append(query['status'][0])
    where = ' WHERE ' + ' AND '.join(clauses)
    join = ' FROM events e LEFT JOIN dispositions d ON d.event_id=e.id'
    page = max(1, int(query.get('page', ['1'])[0]))
    size = min(100, max(1, int(query.get('size', ['25'])[0])))
    sort = {'time': 'e.timestamp', 'severity': 'e.severity', 'signature': 'e.signature'}.get(query.get('sort', ['time'])[0], 'e.timestamp')
    direction = 'ASC' if query.get('direction', ['desc'])[0] == 'asc' else 'DESC'
    total = db.execute('SELECT count(*)' + join + where, args).fetchone()[0]
    rows = db.execute("SELECT e.*,COALESCE(d.status,'new') AS status" + join + where + f' ORDER BY {sort} {direction},e.id DESC LIMIT ? OFFSET ?', args + [size, (page - 1) * size])
    return {'total': total, 'page': page, 'size': size, 'items': [dict(r) for r in rows]}


def overview(db):
    def grouped(field):
        return [dict(r) for r in db.execute(f"SELECT {field} AS label,count(*) AS count FROM events WHERE event_type='alert' GROUP BY {field} ORDER BY count DESC LIMIT 10")]
    return {'alerts': db.execute("SELECT count(*) FROM events WHERE event_type='alert'").fetchone()[0],
            'tasks': db.execute('SELECT count(*) FROM tasks').fetchone()[0],
            'sources': grouped('src_ip'), 'signatures': grouped('signature'), 'ports': grouped('dest_port'),
            'trend': grouped("substr(timestamp,1,13)")}


def detail(db, event_id):
    row = db.execute("SELECT * FROM events WHERE id=? AND event_type='alert'", (event_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    metadata = db.execute('SELECT * FROM protocol_metadata WHERE event_id=?', (event_id,)).fetchone()
    raw = json.loads(row['raw_json'])
    if metadata:
        result['protocol_metadata'] = dict(metadata)
    else:
        names = [r[1] for r in db.execute('PRAGMA table_info(protocol_metadata)')][1:]
        result['protocol_metadata'] = dict(zip(names, normalize(raw)))
    result['payload'] = result['protocol_metadata']['payload_excerpt']
    result['related'] = [json.loads(r[0]) for r in db.execute("SELECT raw_json FROM events WHERE task_id=? AND flow_id=? AND event_type IN ('flow','http','dns','tls') ORDER BY id LIMIT 50", (row['task_id'], row['flow_id']))]
    result['audit'] = [dict(r) for r in db.execute('SELECT status,actor,changed_at FROM audit WHERE event_id=? ORDER BY id', (event_id,))]
    result['analyst_notes'] = [dict(r) for r in db.execute('SELECT conclusion,recommendation,actor,created_at FROM analyst_notes WHERE event_id=? ORDER BY id', (event_id,))]
    return result
