import json


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
    raw = json.loads(row['raw_json'])
    result['payload'] = raw.get('payload_printable') or raw.get('alert', {}).get('payload_printable')
    result['related'] = [json.loads(r[0]) for r in db.execute("SELECT raw_json FROM events WHERE task_id=? AND flow_id=? AND event_type IN ('flow','http','dns','tls') ORDER BY id LIMIT 50", (row['task_id'], row['flow_id']))]
    result['audit'] = [dict(r) for r in db.execute('SELECT status,actor,changed_at FROM audit WHERE event_id=? ORDER BY id', (event_id,))]
    return result
