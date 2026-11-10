"""LD-340 — three consumer-facing download flags, one bundle, three independent groups.

* **Group (a)** — ``--deep-read-bases`` gives the embedded-Base deep read a command-line
  route (it was a ``Parser`` argument only). OFF by default is byte-identical and makes zero
  Base API calls; the flag wires a ``BaseReadClient`` the way ``--deep-read-sheets`` wires its
  own; every failure degrades to the placeholder.
* **Group (b)** — ``--local-time`` is an OPT-IN filename-stamp basis. The default does not
  move (UTC), the flag switches the stamp to the machine's local clock, and the caveat (a
  TZ-dependent filename breaks cross-machine byte-identity) is printed in the help.
* **Group (c)** — ``--route area/section/topic`` is the consumer-supplied routing override.
  The caller supplies the subpath; the library infers nothing. ``..``, an absolute path and an
  empty segment are refused with the reason named.
"""

import logging
import os
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from cli_invoke import invoke_cli
from larkdocio.cli import cli
from larkdocio.read import download
from larkdocio.read.config import Config

DOCX_URL = "https://example.larksuite.com/docx/AbCdEfG123"


def _patch_env(monkeypatch, *, app_id="id", app_secret="secret"):
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: (app_id, app_secret))


def _normalize(text: str) -> str:
    return " ".join(text.split())


# =========================================================================== #
# Group (a) — AC1: the flag exists, OFF is byte-identical, ON wires the client #
# =========================================================================== #

def test_ac1_deep_read_bases_flag_is_registered_on_download():
    out = CliRunner().invoke(cli, ["download", "--help"]).output
    assert "--deep-read-bases" in out


def test_ac1_parse_default_constructs_no_base_client_and_no_deep_read():
    """No base_client handed to _parse → the Parser is byte-identical to today: deep read
    off, no client, zero Base surface reachable."""
    from test_download_pipeline import _StubClient  # reuse the offline stub

    client = _StubClient(blocks=[], docx=SimpleNamespace(title="T", document_id="D"))
    _d, _b, parser, _t, _m = download._parse(client, Config(), "DOC")
    assert parser.deep_read_bases is False
    assert parser.base_client is None


def test_ac1_parse_threads_base_client_and_turns_deep_read_on():
    from test_download_pipeline import _StubClient

    client = _StubClient(blocks=[], docx=SimpleNamespace(title="T", document_id="D"))
    base_client = object()
    _d, _b, parser, _t, _m = download._parse(client, Config(), "DOC", base_client=base_client)
    assert parser.deep_read_bases is True
    assert parser.base_client is base_client


def test_ac1_cli_threads_deep_read_bases_and_builds_client_only_when_on(monkeypatch):
    """The flag reaches handle_download_command; absent, it is False and NO BaseReadClient is
    ever constructed (zero Base API surface on the default path)."""
    import larkdocio.cli as cli_mod

    calls = []
    monkeypatch.setattr(cli_mod, "handle_download_command", lambda *a, **k: calls.append(k))
    invoke_cli(cli_mod.cli, ["download", DOCX_URL, "--deep-read-bases"])
    invoke_cli(cli_mod.cli, ["download", DOCX_URL])
    assert calls[0]["deep_read_bases"] is True
    assert calls[1]["deep_read_bases"] is False


def test_ac1_handler_constructs_base_client_only_when_flag_on(monkeypatch, tmp_path):
    """Integration wiring: with the flag ON a BaseReadClient is constructed and threaded into
    the parser; with it OFF the constructor is never touched."""
    from test_download_pipeline import _StubClient, _StubParser

    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())

    built = []

    class _SpyBaseClient:
        def __init__(self, *a, **k):
            built.append((a, k))

    monkeypatch.setattr(download, "BaseReadClient", _SpyBaseClient)

    captured = {}
    real_parse = download._parse

    def _spy_parse(client, config, doc_token, **kw):
        captured.update(kw)
        return (
            SimpleNamespace(__dict__={}), [],
            _StubParser(markdown="# ok\n"), "T", "# ok\n",
        )

    monkeypatch.setattr(download, "_parse", _spy_parse)

    # OFF — no client built, no base_client threaded.
    invoke_cli(cli, ["download", DOCX_URL, "-o", str(tmp_path)])
    assert built == []
    assert captured.get("base_client") is None

    built.clear()
    captured.clear()
    # ON — exactly one client built and threaded through.
    invoke_cli(cli, ["download", DOCX_URL, "-o", str(tmp_path), "--deep-read-bases"])
    assert len(built) == 1
    assert isinstance(captured.get("base_client"), _SpyBaseClient)


def test_ac2_deep_read_bases_descriptor_is_now_a_cli_flag():
    """The machine-readable half of the amended decision: mode flips config→cli, cli names the
    real switch, and the summary no longer claims it is 'not a command-line flag'."""
    import larkdocio

    flag = larkdocio.capabilities(full=True)["flags"]["deep_read_bases"]
    assert flag["mode"] == "cli"
    assert flag["cli"] == "--deep-read-bases"
    assert flag["default"] is False
    lowered = flag["summary"].lower()
    assert "not a command-line flag" not in lowered
    assert "not a command line flag" not in lowered


def test_ac2_download_help_documents_deep_read_bases_degrade():
    out = _normalize(CliRunner().invoke(cli, ["download", "--help"]).output)
    assert "--deep-read-bases" in out
    # the true half of the old reason survives: it degrades to the placeholder
    assert "placeholder" in out.lower()


# =========================================================================== #
# Group (b) — AC3/AC4: --local-time is opt-in, default unmoved, caveat printed  #
# =========================================================================== #

def test_ac3_local_time_flag_is_registered_and_help_states_the_tradeoff():
    out = _normalize(CliRunner().invoke(cli, ["download", "--help"]).output)
    assert "--local-time" in out
    # the caveat: same instant, two machines, different names → machine-dependent
    assert "different" in out.lower()
    assert "machine" in out.lower()


def test_ac3_default_stamp_is_UTC_byte_identical(monkeypatch, tmp_path):
    """Flag absent → the stamp is computed exactly as today (UTC), the filename byte-identical."""
    from datetime import datetime as _dt, timezone as _tz

    class _FrozenUTC(_dt):
        @classmethod
        def now(cls, tz=None):
            assert tz is _tz.utc, "default path must take the stamp in UTC"
            return _dt(2026, 8, 8, 4, 5, tzinfo=_tz.utc)

    monkeypatch.setattr(download, "datetime", _FrozenUTC)
    download._write_markdown(Config(), str(tmp_path), "TOK", "My Doc", "# b\n")
    assert [p.name for p in tmp_path.iterdir()] == ["[2026-08-08_0405]_My_Doc.md"]


def test_ac3_local_time_uses_the_local_clock_and_same_shape(monkeypatch, tmp_path):
    """Flag on → the stamp is the local wall clock (datetime.now() with no tz); the rendered
    SHAPE is unchanged, only the digits move — no offset, no Z, no zone suffix."""
    import re
    from datetime import datetime as _dt

    class _FrozenLocal(_dt):
        @classmethod
        def now(cls, tz=None):
            assert tz is None, "local-time path must read the local wall clock (no tz)"
            return _dt(2026, 8, 8, 12, 5)

    monkeypatch.setattr(download, "datetime", _FrozenLocal)
    download._write_markdown(Config(), str(tmp_path), "TOK", "My Doc", "# b\n", local_time=True)
    names = [p.name for p in tmp_path.iterdir()]
    assert names == ["[2026-08-08_1205]_My_Doc.md"], names
    assert not re.search(r"(?i)utc|[+-]\d{4}|Z\.md$", names[0]), names[0]


def test_ac4_sidecar_reports_the_actual_basis(tmp_path):
    """The --dump sidecar's filename_timestamp.timezone reports the RUN's basis, so it stops
    lying when the filename is local. Keys are unchanged (pinned keeper)."""
    docx = SimpleNamespace(title="T", document_id="D")

    default_dir = tmp_path / "utc"
    default_dir.mkdir()
    download._dump_json(docx, [], str(default_dir), "TOK")
    import json
    utc = json.loads((default_dir / "TOK.json").read_text(encoding="utf-8"))["filename_timestamp"]
    assert utc == {"timezone": "UTC", "format": "[%Y-%m-%d_%H%M]"}

    local_dir = tmp_path / "local"
    local_dir.mkdir()
    download._dump_json(docx, [], str(local_dir), "TOK", local_time=True)
    loc = json.loads((local_dir / "TOK.json").read_text(encoding="utf-8"))["filename_timestamp"]
    assert loc["timezone"] == "local"
    assert loc["format"] == "[%Y-%m-%d_%H%M]"


def test_ac4_epilog_still_names_UTC_as_default_and_local_time_as_the_way_out():
    epilog = _normalize(cli.commands["download"].epilog)
    assert "UTC" in epilog
    assert "--local-time" in epilog


def test_ac3_cli_threads_local_time_to_handler(monkeypatch):
    import larkdocio.cli as cli_mod

    calls = []
    monkeypatch.setattr(cli_mod, "handle_download_command", lambda *a, **k: calls.append(k))
    invoke_cli(cli_mod.cli, ["download", DOCX_URL, "--local-time"])
    invoke_cli(cli_mod.cli, ["download", DOCX_URL])
    assert calls[0]["local_time"] is True
    assert calls[1]["local_time"] is False


# =========================================================================== #
# Group (c) — AC5: --route is the consumer's path; no convention enters         #
# =========================================================================== #

def test_ac5_route_flag_is_registered():
    out = CliRunner().invoke(cli, ["download", "--help"]).output
    assert "--route" in out


def test_ac5_route_places_document_under_the_supplied_subpath():
    out = download._apply_explicit_route("/base", "area/section/topic")
    assert out == os.path.join("/base", "area", "section", "topic")


def test_ac5_route_segments_go_through_sanitize_but_keep_caller_spelling():
    """Same sanitize_path_string treatment the derived segments get (spaces→_, reserved
    chars stripped) — but no lowercasing: the caller's path is theirs, not inferred."""
    out = download._apply_explicit_route("/base", "My Area/Sub Section")
    assert out == os.path.join("/base", "My_Area", "Sub_Section")


def test_ac5_route_refuses_parent_traversal():
    with pytest.raises(Exception) as exc:
        download._apply_explicit_route("/base", "a/../../etc")
    assert ".." in str(exc.value)


def test_ac5_route_refuses_absolute_path():
    with pytest.raises(Exception) as exc:
        download._apply_explicit_route("/base", "/etc/passwd")
    assert "absolute" in str(exc.value).lower()


def test_ac5_route_refuses_empty():
    with pytest.raises(Exception) as exc:
        download._apply_explicit_route("/base", "   ")
    assert "empty" in str(exc.value).lower()


def test_ac5_route_refuses_empty_interior_segment():
    with pytest.raises(Exception) as exc:
        download._apply_explicit_route("/base", "a//b")
    assert "empty" in str(exc.value).lower()


def test_ac5_route_places_the_output_and_the_document_body_is_never_consulted(
    monkeypatch, tmp_path
):
    """REWRITTEN, NEVER DELETED (LD-650). The old arm spied on the derivation to prove
    ``--route`` took precedence over it; the derivation is gone, so the spy went — and
    **both landing assertions are kept verbatim**, because they are the whole of contract
    item 1 and deleting this test is the easiest way to lose it silently.

    The body is still the one that used to self-route into ``sales/``, which is what makes
    the second assertion meaningful: nothing may exist there, under any switch, ever again."""
    from test_download_pipeline import _StubClient, _StubParser

    _patch_env(monkeypatch)
    body_md = "| Area | Sales |\n| Section | Billing |\n| Topic | Invoices |\n"
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown=body_md))

    invoke_cli(cli, ["download", DOCX_URL, "-o", str(tmp_path), "--route", "x/y"])

    landed = list((tmp_path / "x" / "y").glob("*.md"))
    assert landed, "the document must land under the caller-supplied --route path"
    # and NOT under the path the retired derivation would have built from that body
    assert not (tmp_path / "sales").exists()


def test_ac5_no_route_lands_at_the_output_dir_and_narrates_NOTHING_about_routing(
    monkeypatch, tmp_path, caplog
):
    """TRANSFORMED (LD-650). The old arm asserted the INFO "miss report" still fired; that
    report described a derivation that no longer runs, so what replaces it is the two claims
    that outlived it — the file lands in ``-o`` (an end-to-end no-route landing assertion,
    which is one of the things that catch the naive cut's runtime break), and a download that
    was asked to relocate nothing says nothing about relocation at any level."""
    from test_download_pipeline import _StubClient, _StubParser

    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown="# plain\n"))

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        invoke_cli(cli, ["download", DOCX_URL, "-o", str(tmp_path)])

    assert list(tmp_path.glob("*.md")), "the markdown must land in -o itself"
    assert not [r for r in caplog.records if "routing" in r.message.lower()
                or "--route" in r.message]


def test_ac5_route_logs_its_OWN_line_and_no_retired_routing_report(monkeypatch, tmp_path, caplog):
    """The surviving half of the old pair: ``--route`` logs the caller-supplied-path line the
    downstream consumer parses, and the retired report's sentence never returns."""
    from test_download_pipeline import _StubClient, _StubParser

    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown="# plain\n"))

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        invoke_cli(cli, ["download", DOCX_URL, "-o", str(tmp_path), "--route", "a/b"])
    # Nothing but the ``--route`` line itself speaks of routing (LD-716: the retired report is
    # caught by the general word, so no probe string names what it once reported).
    assert not [r for r in caplog.records if "routing" in r.message.lower()
                and "--route" not in r.message]
    assert any("--route" in r.message for r in caplog.records)
