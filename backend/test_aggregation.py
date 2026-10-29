import unittest
from queries import aggregate_alerts


class AggregationTest(unittest.TestCase):
    def test_preserves_rule_flow_task_and_window_boundaries(self):
        base = {'task_id': 'a', 'sid': 1, 'src_ip': 'a', 'src_port': 10, 'dest_ip': 'b', 'dest_port': 80, 'proto': 'TCP', 'timestamp': '2026-01-01T00:00:01Z'}
        rows = [base, dict(base, timestamp='2026-01-01T00:00:02Z'), dict(base, sid=2), dict(base, task_id='b'), dict(base, dest_port=81), dict(base, timestamp='2026-01-01T00:00:11Z')]
        groups = aggregate_alerts(rows)
        self.assertEqual(len(groups), 5)
        self.assertEqual(groups[0]['count'], 2)
        self.assertEqual(sum(r['count'] for r in groups), 6)
        with self.assertRaises(ValueError):
            aggregate_alerts(rows, 0)


if __name__ == '__main__':
    unittest.main()
