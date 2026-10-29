import json
import pathlib
import tempfile
import unittest
from collector import connect, import_eve, normalize


class CollectorTest(unittest.TestCase):
    def test_protocol_metadata_and_payload_precedence(self):
        value = normalize({'app_proto': 'http', 'http': {'hostname': 'lab.example', 'url': '/x', 'http_method': 'GET', 'status': 401}, 'payload': 'PGltZz4=', 'flow': {'bytes_toserver': 123}})
        self.assertEqual(value[1:5], ('lab.example', '/x', 'GET', 401))
        self.assertEqual(value[-1], '<img>')
        self.assertEqual(value[-3], 123)
        self.assertIn('not raw payload', normalize({'http': {'url': '/x'}})[-1])
        self.assertEqual(normalize({'tls': {'sni': 'lab.example'}})[7], 'lab.example')
        self.assertEqual(normalize({'dns': {'rrname': 'lab.example'}})[5], 'lab.example')

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
