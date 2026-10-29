"""Versioned rule edits: optimistic concurrency and actual engine validation."""
import pathlib
import re
import subprocess
import tempfile


def validate_rule(raw, sid):
    if not isinstance(raw, str) or not raw.strip() or len(raw.encode('utf-8')) > 8192:
        raise ValueError('规则不能为空，最大 8 KB')
    raw = raw.strip()
    if '\n' in raw or '\r' in raw or not raw.startswith('alert '):
        raise ValueError('仅支持单行 alert IDS 规则')
    identifiers = re.findall(r'\bsid\s*:\s*(\d+)\s*;', raw)
    if identifiers != [str(sid)]:
        raise ValueError('必须保留当前唯一 SID，不允许改变规则编号')
    if re.search(r'\b(lua|luajit|filestore)\s*[:;]', raw, re.I):
        raise ValueError('网页编辑不支持脚本执行或文件落盘关键字')
    return raw


def check_rules(lines, state, runner=subprocess.run):
    with tempfile.TemporaryDirectory(prefix='rule-check-', dir=state) as folder:
        path = pathlib.Path(folder) / 'candidate.rules'
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        log = pathlib.Path(folder) / 'validation.log'
        with log.open('w', encoding='utf-8') as stream:
            result = runner(['suricata', '-T', '-c', '/etc/suricata/suricata.yaml', '-S', str(path), '-l', folder],
                            stdout=stream, stderr=subprocess.STDOUT, timeout=30, check=False)
        if result.returncode:
            raise ValueError('Suricata 校验失败，旧规则未修改：\n' + log.read_text(encoding='utf-8', errors='replace')[-6000:])


def publish(db, sid, raw, base_revision, actor, candidates, state, now, checker=check_rules):
    raw = validate_rule(raw, sid)
    row = db.execute('SELECT revision FROM rule_overrides WHERE sid=?', (sid,)).fetchone()
    revision = row[0] if row else 0
    if type(base_revision) is not int or base_revision != revision:
        raise RuntimeError('规则已被其他操作更新，请刷新后再修改')
    checker([raw if r['sid'] == sid else r['raw'] for r in candidates], state)
    revision += 1
    db.execute('INSERT OR REPLACE INTO rule_overrides VALUES (?,?,?)', (sid, raw, revision))
    db.execute('INSERT INTO rule_revisions(sid,revision,raw,actor,created_at) VALUES (?,?,?,?,?)', (sid, revision, raw, actor, now))
    return revision
