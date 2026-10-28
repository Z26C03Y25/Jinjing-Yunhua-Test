import json
import pathlib
import tempfile
import unittest
from collector import connect, import_eve


class CollectorTest(unittest.TestCase):
    def test_task_isolation_idempotency_and_rollback(self):
        with tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as temp:
            path = pathlib.Path(temp) / 'eve.json'
            event = {'event_type': 'alert', 'flow_id': 18446744073709551615,
                     'alert': {'signature_id': 1000001, 'signature': '<script>'}}
            path.write_text(json.dumps(event) + '\n', encoding='utf-8')
            db = connect(':memory:')
            self.assertEqual(import_eve(db, 'one', path), 1)
            self.assertEqual(import_eve(db, 'one', path), 0)
            self.assertEqual(import_eve(db, 'two', path), 1)
            self.assertEqual(db.execute('select flow_id from events').fetchone()[0], '18446744073709551615')
            path.write_text(json.dumps(event) + '\ninvalid\n', encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                import_eve(db, 'bad', path)
            self.assertEqual(db.execute("select count(*) from events where task_id='bad'").fetchone()[0], 0)
            db.close()


if __name__ == '__main__':
    unittest.main()
