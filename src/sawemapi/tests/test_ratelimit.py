"""Tests for sawemapi.ratelimit."""
import unittest

from sawemapi import RateLimiter


class FakeTime:
    """A clock whose sleep advances it, so limiter tests take no real time."""

    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def clock(self):
        """The current fake time."""
        return self.now

    def sleep(self, seconds):
        """Advance the fake time."""
        self.slept.append(seconds)
        self.now += seconds


class TestRateLimiter(unittest.TestCase):
    """Sliding window behaviour."""

    def setUp(self):
        """Create a fake clock."""
        self.time = FakeTime()

    def limiter(self, *limits):
        """A limiter on the fake clock."""
        return RateLimiter(limits, clock=self.time.clock, sleep=self.time.sleep)

    def test_under_limit_does_not_wait(self):
        """Requests within the limit go straight through."""
        limiter = self.limiter((3, 60))
        for _ in range(3):
            limiter.acquire()
        self.assertEqual(self.time.slept, [])

    def test_waits_for_oldest_to_age_out(self):
        """The request over the limit waits until the oldest in the window expires."""
        limiter = self.limiter((2, 60))
        limiter.acquire()
        self.time.now += 10
        limiter.acquire()
        limiter.acquire()
        self.assertEqual(self.time.slept, [50])

    def test_all_limits_apply(self):
        """The tightest limit decides the wait."""
        limiter = self.limiter((1, 5), (3, 60))
        limiter.acquire()
        limiter.acquire()
        self.assertEqual(self.time.slept, [5])

    def test_window_slides(self):
        """After the window passes, requests are allowed again without waiting."""
        limiter = self.limiter((1, 60))
        limiter.acquire()
        self.time.now += 61
        limiter.acquire()
        self.assertEqual(self.time.slept, [])

    def test_rejects_bad_limits(self):
        """Empty or non-positive limits are an error."""
        with self.assertRaises(ValueError):
            RateLimiter([])
        with self.assertRaises(ValueError):
            RateLimiter([(0, 60)])
