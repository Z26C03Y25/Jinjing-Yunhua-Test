import pathlib
import tempfile
import unittest
from collector import connect
from maintenance import backup, restore


class MaintenanceTest(unittest.TestCase):
    def test_roundtrip_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            state = root / 'state'
            state.mkdir()
            db = connect(state / 'events.sqlite')
            db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,status TEXT,error TEXT,sha256 TEXT)')
            db.execute("INSERT INTO tasks VALUES ('sample','complete',NULL,'hash')")
            db.commit()
            db.close()
            (state / 'sample').mkdir()
            (state / 'sample/input.pcap').write_bytes(b'original evidence')
            archive = root / 'backup.tar.gz'
            backup(state, archive)
            result = restore(root / 'restored', archive)
            self.assertEqual(result['database_counts']['tasks'], 1)
            self.assertEqual((root / 'restored/sample/input.pcap').read_bytes(), b'original evidence')
            with self.assertRaises(ValueError):
                restore(root / 'restored', archive)
