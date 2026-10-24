# -*- coding: utf-8 -*-
"""One HTTP wave: shared connection pool sized to the call list."""
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter

from synergy_inbounder.communicator import _cache_hits, _wave_local


def run_wave(calls):
    """Run callables together. The pool size equals the number of calls.

    Worker threads share one Session so urllib3 does not cap the wave at 10.
    """
    jobs = list(calls or [])
    if not jobs:
        return []
    size = len(jobs)
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=size, pool_maxsize=size)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    box = _cache_hits.get()

    def _invoke(call):
        _wave_local.session = session
        _wave_local.cache_hits = box
        try:
            return call()
        finally:
            _wave_local.session = None
            _wave_local.cache_hits = None

    try:
        if size == 1:
            return [_invoke(jobs[0])]
        with ThreadPoolExecutor(max_workers=size) as pool:
            futures = [pool.submit(_invoke, call) for call in jobs]
            return [future.result() for future in futures]
    finally:
        session.close()
