"""Summarize timestamps only; never export private prompts or credentials."""
import argparse
import collections
import datetime as dt
import json
import pathlib
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--sessions-root', type=pathlib.Path, default=pathlib.Path.home()/'.codex/sessions')
parser.add_argument('--cutoff-revision', default='c87c82c')
args = parser.parse_args()
zone = dt.timezone(dt.timedelta(hours=8))
cutoff = dt.datetime.fromisoformat(subprocess.check_output(['git','show','-s','--format=%cI',args.cutoff_revision],text=True).strip())
stamps = set()
source_files = 0
for path in args.sessions_root.rglob('*.jsonl'):
    with path.open(encoding='utf-8') as stream:
        try:
            meta = json.loads(next(stream))['payload']
        except (ValueError, KeyError, StopIteration):
            continue
        if meta.get('id') != '01a182c6-a9ad-78b2-a87e-ca50289c1c42' or isinstance(meta.get('source'), dict):
            continue
        source_files += 1
        for line in stream:
            try:
                row = json.loads(line)
                payload = row.get('payload', {})
                stamp = dt.datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
            except (ValueError, KeyError):
                continue
            meaningful = row.get('type') == 'response_item' and (payload.get('type') in ('custom_tool_call','custom_tool_call_output') or payload.get('type') == 'message' and payload.get('role') in ('user','assistant'))
            meaningful |= row.get('type') == 'event_msg' and payload.get('type') in ('agent_message','task_started','task_complete','item_completed')
            if meaningful and stamp <= cutoff:
                stamps.add(stamp)
commits = collections.Counter()
for line in subprocess.check_output(['git','log',args.cutoff_revision,'--format=%cI'],text=True).splitlines():
    stamp = dt.datetime.fromisoformat(line)
    if stamp <= cutoff:
        stamps.add(stamp)
        commits[str(stamp.astimezone(zone).date())] += 1


def summarize(gap):
    intervals = []
    for stamp in sorted(stamps):
        if not intervals or (stamp-intervals[-1][1]).total_seconds() > gap*60:
            intervals.append([stamp, stamp])
        else:
            intervals[-1][1] = stamp
    daily = collections.defaultdict(float)
    for start, end in intervals:
        cursor = start.astimezone(zone)
        end = end.astimezone(zone)
        while cursor < end:
            boundary = dt.datetime.combine(cursor.date()+dt.timedelta(days=1),dt.time(),zone)
            stop = min(boundary,end)
            daily[str(cursor.date())] += (stop-cursor).total_seconds()/3600
            cursor = stop
    return {'hours':round(sum(daily.values()),3),'daily_hours':{k:round(v,3) for k,v in daily.items()},'intervals':[[a.astimezone(zone).isoformat(),b.astimezone(zone).isoformat()] for a,b in intervals]}


report = {'cutoff_revision':args.cutoff_revision,'cutoff_time':cutoff.isoformat(),'timezone':'Asia/Shanghai','session_files':source_files,'git_commits_by_day':dict(commits),'method':'Union of project main-thread activity and Git timestamps; deduplicate; split at gaps over 15 minutes and at midnight. Guardian threads and unrelated projects excluded. No fixed minutes added per commit.','activity_proxy':summarize(15),'sensitivity_30min':summarize(30),'stated_estimate_hours':round(summarize(15)['hours']),'limitation':'Retrospective activity-session estimate including AI execution and waits; not precise human labor measurement. Includes recorded installation and video work up to cutoff; does not reconstruct unlogged offline effort.'}
pathlib.Path('validation/effort-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
