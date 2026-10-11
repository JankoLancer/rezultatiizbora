#!/usr/bin/env python3
"""Cross-process Nominatim rate limiter + shared 429 circuit-breaker.

Usage:
    from ratelimit import limiter
    limiter.wait()          # blocks until a request slot is free
    limiter.penalize(120)   # on HTTP 429: pause ALL processes for 120s
"""
import fcntl
import os
import time

_DIR = os.path.dirname(os.path.abspath(__file__))


class RateLimiter:
    def __init__(self, min_interval=1.3, lockfile=None):
        self.min = min_interval
        self.lockfile = lockfile or os.path.join(_DIR, ".nominatim.lock")
        self.lastfile = self.lockfile + ".last"
        self.cooldownfile = self.lockfile + ".cooldown"

    def _read(self, path):
        try:
            return float(open(path).read())
        except Exception:  # noqa: BLE001
            return 0.0

    def penalize(self, seconds):
        with open(self.lockfile, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            until = max(time.time() + seconds, self._read(self.cooldownfile))
            with open(self.cooldownfile, "w") as fh:
                fh.write(str(until))
            fcntl.flock(lf, fcntl.LOCK_UN)

    def wait(self):
        os.makedirs(os.path.dirname(self.lockfile), exist_ok=True)
        with open(self.lockfile, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            now = time.time()
            cd = self._read(self.cooldownfile)
            if cd > now:
                time.sleep(cd - now)
                now = time.time()
            last = self._read(self.lastfile)
            if now - last < self.min:
                time.sleep(self.min - (now - last))
            with open(self.lastfile, "w") as fh:
                fh.write(str(time.time()))
            fcntl.flock(lf, fcntl.LOCK_UN)


limiter = RateLimiter()
