import threading
import time


class FailureLimiter:
    def __init__(self, limit=10, window=60):
        self.limit, self.window = limit, window
        self.entries, self.lock = {}, threading.Lock()

    def blocked(self, key, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self.entries = {k: v for k, v in self.entries.items() if now-v[0] < self.window}
            return self.entries.get(key, (now, 0))[1] >= self.limit

    def record_failure(self, key, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            start, count = self.entries.get(key, (now, 0))
            self.entries[key] = (now, 1) if now-start >= self.window else (start, count+1)

    def reset(self, key):
        with self.lock:
            self.entries.pop(key, None)
