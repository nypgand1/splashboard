import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

REPO = __file__.rsplit('/tests/', 1)[0]


def _free_port():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_http(url, timeout=40):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            time.sleep(0.25)
    raise RuntimeError(f'e2e server did not start: {last}')


@pytest.fixture(scope='session')
def e2e_server():
    port = _free_port()
    harness = os.path.join(REPO, 'tests', 'e2e', 'harness.py')
    proc = subprocess.Popen(
        [sys.executable, harness, str(port)],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    url = f'http://127.0.0.1:{port}'
    try:
        _wait_http(url)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
