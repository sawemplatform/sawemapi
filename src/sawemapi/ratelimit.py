"""Client-side throttling, so the API's rate limits are rarely reached."""
import threading
import time
from collections import deque

# The API's documented defaults as (requests, seconds): 30 per minute, 500 per hour.
# Limits are configured per environment and endpoints may override them, so check
# with your platform administrator.
DEFAULT_RATE_LIMITS = ((30, 60), (500, 3600))


class RateLimiter:
    """Sliding-window limiter: blocks in `acquire` until a request is allowed.

    Args:
        limits (iterable): (requests, seconds) pairs. A request is allowed only when
            every limit is satisfied.
        clock (callable): Returns the current time in seconds. For tests.
        sleep (callable): Waits for the given seconds. For tests.
    """

    def __init__(self, limits=DEFAULT_RATE_LIMITS, clock=time.monotonic, sleep=time.sleep):
        self._limits = tuple((int(count), float(seconds)) for count, seconds in limits)
        if not self._limits or any(count < 1 or seconds <= 0 for count, seconds in self._limits):
            raise ValueError("limits must be (requests >= 1, seconds > 0) pairs")
        self._clock = clock
        self._sleep = sleep
        self._stamps = deque()
        self._lock = threading.Lock()

    def acquire(self):
        """Wait until a request is allowed, then record it."""
        with self._lock:
            while True:
                now = self._clock()
                horizon = max(seconds for _, seconds in self._limits)
                while self._stamps and self._stamps[0] <= now - horizon:
                    self._stamps.popleft()
                wait = 0.0
                for count, seconds in self._limits:
                    recent = [t for t in self._stamps if t > now - seconds]
                    if len(recent) >= count:
                        wait = max(wait, recent[-count] + seconds - now)
                if wait <= 0:
                    self._stamps.append(now)
                    return
                self._sleep(wait)
