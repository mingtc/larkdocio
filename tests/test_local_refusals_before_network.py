"""LD-397 — a refusal the library can make for free never costs a credential or a packet.

The measured slip (spike gap G15): ``larkdocio folder <a docx URL>`` resolved credentials and
issued a live ``tenant_access_token`` request **before** any URL-shape objection. A refusal that
reaches the network can leak, hang or bill — and when the credentials are also wrong the user is
handed an **auth** error for a command that was never going to run, and debugs the wrong problem.

The proof here is a **negative**, which is why it is spied rather than observed:

* ``_no_network`` makes any DNS/socket attempt raise :class:`_NetworkAttempted`, a
  ``BaseException`` — so no ``except Exception`` anywhere on the path can swallow the evidence
  and let a network touch read as a clean refusal;
* ``get_read_credentials`` is spied **in the namespace each verb resolves it from**, so
  "credentials were never resolved" is asserted rather than inferred.

The ordering moved for the **refusal** path only: the valid-input cases at the bottom pin that a
URL a verb can actually read still resolves credentials exactly as before.
"""
import logging
import socket

import pytest
from click.testing import CliRunner

from larkdocio.cli import cli
from larkdocio.drive import client as drive_client
from larkdocio.read import download

DOCX_URL = "https://example.larksuite.com/docx/AbCdEfG123"
WIKI_URL = "https://example.larksuite.com/wiki/AbCdEfG123"
SHEETS_URL = "https://example.larksuite.com/sheets/AbCdEfG123"
FOLDER_URL = "https://example.larksuite.com/drive/folder/AbCdEfG123"


class _NetworkAttempted(BaseException):
    """Deliberately NOT an ``Exception``: a network touch must not be catchable by the
    broad handlers on the download/folder paths, or the spy would prove nothing."""


@pytest.fixture
def _no_network(monkeypatch):
    def _boom(*args, **kwargs):
        raise _NetworkAttempted("the refusal path touched the network")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket.socket, "connect", _boom)
    return _boom


@pytest.fixture
def _credential_spy(monkeypatch):
    """Record every credential resolution on either verb's path (and neutralise ``.env``)."""
    calls = []

    def _resolve():
        calls.append("get_read_credentials")
        return ("spy-id", "spy-secret")

    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", _resolve)
    monkeypatch.setattr(drive_client, "get_read_credentials", _resolve)
    return calls


def _invoke(args):
    # Fresh handler per invocation — CliRunner swaps sys.stderr, and a handler left bound to a
    # closed stream prints logging's own traceback into this run's output.
    logging.getLogger("larkdocio").handlers.clear()
    return CliRunner().invoke(cli, args)


# --------------------------------------------------------------------------- #
# AC1/AC2 — `folder` refuses a document URL locally: no credentials, no packets.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("url, word", [(DOCX_URL, "DOCX"), (WIKI_URL, "WIKI"), (SHEETS_URL, "SHEETS")])
def test_folder_refuses_a_non_folder_url_before_any_credential_or_network(
        url, word, tmp_path, monkeypatch, _no_network, _credential_spy):
    # LD-700: the verb's env resolution creates ./.env when none exists; keep it in tmp_path.
    monkeypatch.chdir(tmp_path)
    result = _invoke(["folder", url, "-o", str(tmp_path)])

    assert result.exit_code != 0, result.output
    assert word in result.output and "FOLDER" in result.output, result.output
    assert _credential_spy == [], f"credentials were resolved for a refusal: {_credential_spy}"


# --------------------------------------------------------------------------- #
# AC3/AC4 — the sibling verb: `download` refuses a folder URL the same way.     #
# --------------------------------------------------------------------------- #

def test_download_refuses_a_folder_url_before_any_credential_or_network(
        tmp_path, monkeypatch, _no_network, _credential_spy):
    monkeypatch.chdir(tmp_path)  # LD-700: no ./.env written into the checkout
    result = _invoke(["download", FOLDER_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0, result.output
    # The message is the one shipped today, verbatim in its routing half (AC6).
    assert "DRIVE FOLDER url" in result.output, result.output
    assert "larkdocio folder" in result.output, result.output
    assert _credential_spy == [], f"credentials were resolved for a refusal: {_credential_spy}"


def test_download_refuses_a_spreadsheet_url_before_any_credential_or_network(
        tmp_path, _no_network, _credential_spy):
    result = _invoke(["download", SHEETS_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0, result.output
    assert "SPREADSHEET url" in result.output, result.output
    assert _credential_spy == [], f"credentials were resolved for a refusal: {_credential_spy}"


# --------------------------------------------------------------------------- #
# AC5 — NOT a behavior change for valid inputs: a readable URL still resolves   #
# credentials, in the same place, before the read.                              #
# --------------------------------------------------------------------------- #

def test_download_still_resolves_credentials_for_a_document_url(tmp_path, _credential_spy, monkeypatch):
    reached = []

    def _fake_resolve_doc(url, allow_host, config_file, app_id, app_secret):
        reached.append((url, app_id, app_secret))
        raise SystemExit(0)  # stop before any network; ordering is what is under test

    monkeypatch.setattr(download, "_resolve_doc", _fake_resolve_doc)
    _invoke(["download", DOCX_URL, "-o", str(tmp_path)])

    assert _credential_spy == ["get_read_credentials"], _credential_spy
    assert reached == [(DOCX_URL, "spy-id", "spy-secret")], reached


def test_folder_still_builds_its_read_client_for_a_folder_url(tmp_path, _credential_spy, monkeypatch):
    built = []

    def _fake_walk(*args, **kwargs):
        built.append(args[1])
        raise SystemExit(0)

    monkeypatch.setattr("larkdocio.drive.read.walk_folder", _fake_walk)
    _invoke(["folder", FOLDER_URL, "-o", str(tmp_path)])

    assert _credential_spy == ["get_read_credentials"], _credential_spy
    assert built == ["AbCdEfG123"], built
