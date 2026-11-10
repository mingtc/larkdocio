"""LD-017 — the IPv4 pin honors ``LARK_DISABLE_IPV4_PIN``
from a ``.env``.

The pin (``socket.getaddrinfo`` → ``AF_INET``) must be applied **after** the
``.env`` is loaded, not at import time. The chosen hook is ``auth.init_env``:
after ``load_dotenv`` runs, ``init_env`` applies the pin unless the (now-loaded)
``LARK_DISABLE_IPV4_PIN`` disables it. This is the single ``.env``-loaded
chokepoint shared by the CLI command handlers *and* the package-API / live-canary
path, so the knob is honored everywhere the reader loads its env — while merely
importing ``larkdocio.cli`` no longer mutates process-wide DNS.

All offline — no network. Each test restores ``socket.getaddrinfo`` and resets
the module-level applied-guard so the global patch never leaks across tests.
"""
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import larkdocio.auth as auth
import larkdocio.common.auth as core_auth
from larkdocio.cli import cli
from larkdocio.read import download

DOCX_URL = "https://example.larksuite.com/docx/AbCdEfG123"


@pytest.fixture(autouse=True)
def _isolate_pin(monkeypatch):
    """Snapshot ``socket.getaddrinfo`` + reset the applied-guard per test so the
    global DNS patch never leaks between tests, and clear the knob from the
    process env so only what a test/``.env`` sets is observed."""
    baseline = socket.getaddrinfo
    # LD-061: the pin-applied guard now lives in the shared core
    # (``larkdocio.common.auth``); reset it at its canonical home so the global
    # DNS patch never leaks between tests. ``larkdocio.auth`` re-exports the pin
    # functions but not this module-level guard's identity.
    monkeypatch.setattr(core_auth, "_ipv4_pin_applied", False, raising=False)
    monkeypatch.delenv("LARK_DISABLE_IPV4_PIN", raising=False)
    yield baseline
    socket.getaddrinfo = baseline


# --------------------------------------------------------------------------- #
# AC1 — init_env is .env-aware: honors LARK_DISABLE_IPV4_PIN from a .env        #
# --------------------------------------------------------------------------- #

def test_init_env_pins_by_default(tmp_path, _isolate_pin):
    """A default ``.env`` (knob absent) → the pin IS applied after load."""
    baseline = _isolate_pin
    env = tmp_path / ".env"
    env.write_text("LARK_APP_ID=x\nLARK_APP_SECRET=y\n", encoding="utf-8")

    auth.init_env(str(env))

    assert socket.getaddrinfo is not baseline, "pin must be applied by default"


def test_init_env_honors_disable_from_dotenv(tmp_path, _isolate_pin):
    """``LARK_DISABLE_IPV4_PIN=1`` set **in the .env** (and unset in the process
    env) → stock resolution; the pin is NOT applied. This is the core B3 bug."""
    baseline = _isolate_pin
    env = tmp_path / ".env"
    env.write_text("LARK_APP_ID=x\nLARK_APP_SECRET=y\nLARK_DISABLE_IPV4_PIN=1\n", encoding="utf-8")

    auth.init_env(str(env))

    assert socket.getaddrinfo is baseline, (
        "LARK_DISABLE_IPV4_PIN=1 from .env must be honored (pin not applied)"
    )


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "yes"])
def test_disable_values_recognized(tmp_path, _isolate_pin, value):
    baseline = _isolate_pin
    env = tmp_path / ".env"
    env.write_text(f"LARK_DISABLE_IPV4_PIN={value}\n", encoding="utf-8")

    auth.init_env(str(env))

    assert socket.getaddrinfo is baseline


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_non_disable_values_still_pin(tmp_path, _isolate_pin, value):
    baseline = _isolate_pin
    env = tmp_path / ".env"
    env.write_text(f"LARK_DISABLE_IPV4_PIN={value}\n", encoding="utf-8")

    auth.init_env(str(env))

    assert socket.getaddrinfo is not baseline


def test_applied_pin_forces_ipv4_family():
    """The applied patch coerces the requested family to ``AF_INET`` (the
    mechanism is unchanged: ``getaddrinfo`` → ``AF_INET``)."""
    baseline = socket.getaddrinfo
    captured = {}

    def spy(host, port, family=0, type=0, proto=0, flags=0):
        captured["family"] = family
        return []

    try:
        socket.getaddrinfo = spy          # stand in for the "original" resolver
        core_auth._ipv4_pin_applied = False
        auth.pin_socket_to_ipv4()         # wraps the spy (shim re-exports the core fn)
        socket.getaddrinfo("example.com", 443, family=socket.AF_INET6)
        assert captured["family"] == socket.AF_INET
    finally:
        socket.getaddrinfo = baseline
        core_auth._ipv4_pin_applied = False


# --------------------------------------------------------------------------- #
# AC1 (end-to-end) — the CLI download path honors the knob from --env-file      #
# --------------------------------------------------------------------------- #

class _StubClient:
    def get_docx_content(self, doc_token):
        return SimpleNamespace(title="T", document_id="D"), []


class _StubParser:
    img_tokens: list = []
    board_tokens: list = []

    def __init__(self, *a, **k):
        self.img_tokens = []
        self.board_tokens = []

    def parse_docx_content(self, document_id, blocks):
        return "# ok\n"


def test_cli_download_honors_disable_from_env_file(tmp_path, monkeypatch, _isolate_pin):
    baseline = _isolate_pin
    env = tmp_path / ".env"
    env.write_text("LARK_APP_ID=x\nLARK_APP_SECRET=y\nLARK_DISABLE_IPV4_PIN=1\n", encoding="utf-8")
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser())

    result = CliRunner().invoke(
        cli, ["--env-file", str(env), "download", DOCX_URL, "-o", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert socket.getaddrinfo is baseline, "disable knob from .env must reach the CLI path"


def test_cli_download_pins_by_default_from_env_file(tmp_path, monkeypatch, _isolate_pin):
    baseline = _isolate_pin
    env = tmp_path / ".env"
    env.write_text("LARK_APP_ID=x\nLARK_APP_SECRET=y\n", encoding="utf-8")
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser())

    result = CliRunner().invoke(
        cli, ["--env-file", str(env), "download", DOCX_URL, "-o", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert socket.getaddrinfo is not baseline, "default CLI path must apply the pin"


# --------------------------------------------------------------------------- #
# AC3 — merely importing larkdocio.cli must NOT mutate process-wide DNS         #
# --------------------------------------------------------------------------- #

def test_importing_cli_does_not_mutate_dns():
    """A fresh process that only imports ``larkdocio.cli`` must leave
    ``socket.getaddrinfo`` untouched (no import-time global DNS mutation)."""
    import os

    src_dir = os.path.dirname(os.path.dirname(auth.__file__))  # .../src
    code = (
        "import socket\n"
        "orig = socket.getaddrinfo\n"
        "import larkdocio.cli\n"
        "assert socket.getaddrinfo is orig, 'import of larkdocio.cli patched getaddrinfo'\n"
        "print('OK')\n"
    )
    env = {**os.environ, "PYTHONPATH": src_dir}
    env.pop("LARK_DISABLE_IPV4_PIN", None)
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, (result.stdout + result.stderr)
    assert "OK" in result.stdout
