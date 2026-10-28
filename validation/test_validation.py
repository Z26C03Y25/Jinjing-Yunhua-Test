import unittest
from run_validation import evaluate


class EvaluationTest(unittest.TestCase):
    def test_duplicate_matches_are_not_false_positives(self):
        expected = {'sid': 1, 'src_ip': 'a', 'dst_ip': 'b', 'dst_port_range': [80, 80], 'proto': 'TCP', 'window': {'start': '2026-01-01T00:00:00Z', 'end': '2026-01-01T00:00:01Z'}}
        alert = {'sid': 1, 'src_ip': 'a', 'dest_ip': 'b', 'dest_port': 80, 'proto': 'TCP', 'timestamp': '2026-01-01T00:00:00.5+0000'}
        result = evaluate({'scenario': 'test', 'benign': False, 'expected_alerts': [expected]}, [alert, alert])
        self.assertEqual(result['tp_expectations'], 1)
        self.assertEqual(result['fp_alerts'], 0)
        alert = dict(alert, timestamp='2026-01-01T00:00:02Z')
        result = evaluate({'scenario': 'test', 'benign': False, 'expected_alerts': [expected]}, [alert])
        self.assertEqual(result['fn_expectations'], 1)
        self.assertEqual(result['fp_alerts'], 1)


if __name__ == '__main__':
    unittest.main()
