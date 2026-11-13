# -*- coding: utf-8 -*-
"""Thread-safe Singleflight coalescing primitive.

Coalesces concurrent calls for the same key so only the first caller executes
``builder()``, while concurrent callers wait on the shared ``Future``.
"""
from concurrent.futures import Future
import threading


class SingleflightGroup:
    """Coalesce in-flight work by key using a shared lock and ``Future``."""

    def __init__(self, lock=None):
        self._lock = lock or threading.Lock()
        self._inflight = {}

    @property
    def lock(self):
        return self._lock

    @property
    def inflight(self):
        return self._inflight

    def clear(self):
        with self._lock:
            self._inflight.clear()

    def do(self, key, builder):
        """Run ``builder()`` once per concurrent ``key``."""
        with self._lock:
            future = self._inflight.get(key)
            if future is None:
                future = Future()
                self._inflight[key] = future
                owner = True
            else:
                owner = False
        if not owner:
            return future.result()
        try:
            value = builder()
        except Exception as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(value)
            return value
        finally:
            with self._lock:
                if self._inflight.get(key) is future:
                    self._inflight.pop(key, None)
