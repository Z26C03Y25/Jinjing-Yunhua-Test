import unittest
from security import FailureLimiter


class SecurityTest(unittest.TestCase):
    def test_failure_limit_expires_and_isolated_by_address(self):
        limiter = FailureLimiter(limit=2, window=60)
        for _ in range(2):
            limiter.record_failure('one', now=10)
        self.assertTrue(limiter.blocked('one', now=11))
        self.assertFalse(limiter.blocked('two', now=11))
        self.assertFalse(limiter.blocked('one', now=71))
        limiter.record_failure('one', now=72)
        limiter.reset('one')
        self.assertFalse(limiter.blocked('one', now=73))
