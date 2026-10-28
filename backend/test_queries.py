import json
import unittest
from collector import connect
from queries import alerts, detail


class QueryTest(unittest.TestCase):
    def test_filters_pagination_and_related_task_isolation(self):
        db = connect(':memory:')
        for task, kind, sid in [('a', 'alert', 1), ('a', 'flow', None), ('b', 'flow', None), ('b', 'alert', 2)]:
            db.execute('INSERT INTO events(task_id,line_no,event_type,flow_id,sid,raw_json,ingested_at) VALUES (?,?,?,?,?,?,?)', (task, 1 if kind == 'alert' else 2, kind, '123', sid, json.dumps({'event_type': kind}), 'now'))
        self.assertEqual(alerts(db, {'task_id': ['a']})['total'], 1)
        self.assertEqual(alerts(db, {'task_id': ["a' OR 1=1 --"]})['total'], 0)
        self.assertEqual(len(detail(db, 1)['related']), 1)
        db.execute("INSERT INTO dispositions VALUES (1,'confirmed')")
        self.assertEqual(alerts(db, {'status': ['new']})['total'], 1)
        self.assertEqual(alerts(db, {'size': ['1'], 'page': ['2']})['total'], 2)
        db.close()


if __name__ == '__main__':
    unittest.main()
