import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def api_url():
    """Levanta la API real del hospital en un puerto libre y devuelve su URL base."""
    puerto = _puerto_libre()
    proc = subprocess.Popen(
        [sys.executable, str(RAIZ / "api" / "servidor.py"), "--puerto", str(puerto)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://localhost:{puerto}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{url}/espera", timeout=1).read()
            break
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.05)
    else:
        proc.terminate()
        pytest.fail("la API del hospital no arrancó")
    yield url
    proc.terminate()
    proc.wait(timeout=5)
