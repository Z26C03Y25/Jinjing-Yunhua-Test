import tempfile
import pathlib
import unittest
from collector import connect
from rule_editor import publish, validate_rule


class RuleEditorTest(unittest.TestCase):
    def test_validation_failure_keeps_current_and_revision_conflict(self):
        db = connect(':memory:')
        raw = 'alert tcp any any -> any any (msg:"test"; sid:1000001; rev:1;)'
        candidates = [{'sid': 1000001, 'raw': raw}]
        def rejected(*args):
            raise ValueError('engine rejected')
        with self.assertRaises(ValueError):
            publish(db, 1000001, raw, 0, 'analyst', candidates, '.', 'now', checker=rejected)
        self.assertEqual(db.execute('SELECT count(*) FROM rule_overrides').fetchone()[0], 0)
        self.assertEqual(publish(db, 1000001, raw, 0, 'analyst', candidates, '.', 'now', checker=lambda *args: None), 1)
        with self.assertRaises(RuntimeError):
            publish(db, 1000001, raw, 0, 'analyst', candidates, '.', 'now', checker=lambda *args: None)
        for invalid in [raw.replace('1000001', '1000002'), raw+'\n'+raw, raw.replace('alert ', 'drop '), raw.replace('rev:1;', 'lua:test.lua;')]:
            with self.assertRaises(ValueError):
                validate_rule(invalid, 1000001)
        db.close()
