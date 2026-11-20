# -*- coding: utf-8 -*-
"""One HTTP wave: shared connection pool sized to the call list."""
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter

from synergy_inbounder.communicator import _cache_hits, _force_expire, _force_refresh, _wave_local


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
    force_exp = _force_expire.get()
    force_ref = _force_refresh.get()

    def _invoke(call):
        _wave_local.session = session
        _wave_local.cache_hits = box
        tok_exp = _force_expire.set(force_exp)
        tok_ref = _force_refresh.set(force_ref)
        try:
            return call()
        finally:
            _force_expire.reset(tok_exp)
            _force_refresh.reset(tok_ref)
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


def run_tracked_wave(calls):
    """Execute ``run_wave(calls)`` and return ``(results, used_network_bool)``."""
    box = []
    token = _cache_hits.set(box)
    try:
        results = run_wave(calls)
    finally:
        _cache_hits.reset(token)
    used_network = any(not hit for hit in box)
    return results, used_network
