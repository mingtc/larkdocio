"""Pipeline tests for ``read/download.py`` against a stubbed ``Client`` (no network).

Covers LD-014:

* **B1 exit codes (AC3, TDD red-first):** a *failed* download exits **nonzero**
  (missing creds; IP-block; permission; unknown error), a *successful* one exits 0.
* **Files-on-disk end state (AC1):** markdown written; image/board token
  substitution incl. duplicate tokens (first-occurrence ``replace(..., 1)``) and
  failed-asset warn-and-continue; ``--dump`` payload; where the output lands;
  filename policy under a frozen clock.
* **Mutant kills (AC2):** the image-link-substitution test fails if that behavior
  is hand-disabled.

LD-650 removed the body-sniffing router these files also exercised. The scope line above
lost its "routing on/off" entry rather than keeping a false inventory, and the two end-to-end
routing arms were TRANSFORMED into their successors below — one of them is a no-route
landing assertion, which is one of the two things in the suite that catch the
``AttributeError``/``NameError`` class the naive cut would have shipped.

The ``Client`` is stubbed at the ``larkdocio.read.download.Client`` boundary; the
``Parser`` is stubbed where a controlled markdown/token surface is needed. Env
loading + credential resolution are monkeypatched so the suite never touches the
real repo ``.env`` and stays fully offline/deterministic.
"""

import json
import os
import time
from datetime import datetime as _real_datetime, timezone as _timezone
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from cli_invoke import invoke_cli
from larkdocio.cli import cli
from larkdocio.read import download
from larkdocio.read.config import Config, OutputConfig
from larkdocio.utils.sanitize import sanitize_path_string

DOCX_URL = "https://example.larksuite.com/docx/AbCdEfG123"


class _StubClient:
    """Configurable stand-in for ``read.client.Client`` — no network."""

    def __init__(
        self,
        *,
        docx=None,
        blocks=None,
        get_docx_error=None,
        image_paths=None,
        image_error=None,
        board_paths=None,
        board_error=None,
    ):
        self._docx = docx or SimpleNamespace(title="Doc Title", document_id="DOCID")
        self._blocks = [] if blocks is None else blocks
        self._get_docx_error = get_docx_error
        self._image_paths = image_paths or {}
        self._image_error = image_error
        self._board_paths = board_paths or {}
        self._board_error = board_error

    def get_docx_content(self, doc_token):
        if self._get_docx_error is not None:
            raise self._get_docx_error
        return self._docx, self._blocks

    def download_image(self, img_token, out_dir):
        if self._image_error is not None:
            raise self._image_error
        return self._image_paths[img_token]

    def download_board_image(self, board_token, out_dir):
        if self._board_error is not None:
            raise self._board_error
        return self._board_paths[board_token]


class _StubParser:
    """Stand-in for ``read.parser.Parser`` with a controlled markdown/token surface."""

    def __init__(self, markdown="# ok\n", img_tokens=(), board_tokens=(), file_tokens=()):
        self._markdown = markdown
        self.img_tokens = list(img_tokens)
        self.board_tokens = list(board_tokens)
        self.file_tokens = list(file_tokens)

    def parse_docx_content(self, document_id, blocks):
        return self._markdown


def _patch_env(monkeypatch, *, app_id="id", app_secret="secret"):
    """Neutralize ``.env`` loading and pin credential resolution (offline)."""
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(
        download, "get_read_credentials", lambda: (app_id, app_secret)
    )


# --------------------------------------------------------------------------- #
# AC3 — B1 exit codes (TDD red-first: written before download.py is changed)  #
# --------------------------------------------------------------------------- #

def test_download_missing_creds_exits_nonzero(monkeypatch, tmp_path):
    """No credentials → the CLI must exit nonzero (today it logs and exits 0)."""
    _patch_env(monkeypatch, app_id="", app_secret="")

    result = CliRunner().invoke(cli, ["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0


def test_download_permission_error_exits_nonzero(monkeypatch, tmp_path):
    """A permission error (``not read permission`` / code 99991672) → nonzero exit."""
    _patch_env(monkeypatch)
    err = Exception("Failed to get docx blocks: Code: 99991672, Msg: not read permission")
    monkeypatch.setattr(
        download, "Client", lambda *a, **k: _StubClient(get_docx_error=err)
    )

    result = CliRunner().invoke(cli, ["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0


def test_download_ip_block_error_exits_nonzero(monkeypatch, tmp_path):
    """An IP-block error (``ip`` + ``denied``) → nonzero exit."""
    _patch_env(monkeypatch)
    err = Exception("Request rejected: your ip address is denied by the allowlist")
    monkeypatch.setattr(
        download, "Client", lambda *a, **k: _StubClient(get_docx_error=err)
    )

    result = CliRunner().invoke(cli, ["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0


def test_download_unknown_error_exits_nonzero(monkeypatch, tmp_path):
    """An unrecognized error stays nonzero (consistent with the known-error paths)."""
    _patch_env(monkeypatch)
    err = Exception("some unexpected serialization failure")
    monkeypatch.setattr(
        download, "Client", lambda *a, **k: _StubClient(get_docx_error=err)
    )

    result = CliRunner().invoke(cli, ["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0


def test_download_happy_path_exits_zero(monkeypatch, tmp_path):
    """A successful download still exits 0 and writes the markdown file."""
    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown="# hi\n"))

    result = CliRunner().invoke(cli, ["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code == 0
    written = list(tmp_path.glob("*.md"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "# hi\n"


# --------------------------------------------------------------------------- #
# LD-117 — the opt-in fidelity-read wiring threads through download._parse      #
# into the Parser (mirroring the deep_read_sheets plumbing). _parse returns the #
# constructed Parser, so we can assert the attributes it received.              #
# --------------------------------------------------------------------------- #

def test_parse_default_no_sheets_surface_byte_identical():
    # No sheets_client → the exact Parser(config) construction: both opt-ins OFF.
    client = _StubClient(blocks=[], docx=SimpleNamespace(title="T", document_id="D"))
    _docx, _blocks, parser, _title, _md = download._parse(client, Config(), "DOC")
    assert parser.deep_read_sheets is False
    assert parser.sheets_client is None
    assert parser.fidelity_read_sheets is False
    assert parser.sheets_export_reader is None


def test_parse_deep_read_without_export_reader_is_values_only():
    # A deep-read client but NO export reader → deep-read on, fidelity OFF.
    client = _StubClient(blocks=[], docx=SimpleNamespace(title="T", document_id="D"))
    sheets_client = object()
    _d, _b, parser, _t, _m = download._parse(
        client, Config(), "DOC", sheets_client=sheets_client
    )
    assert parser.deep_read_sheets is True
    assert parser.sheets_client is sheets_client
    assert parser.fidelity_read_sheets is False
    assert parser.sheets_export_reader is None


def test_parse_threads_export_reader_and_turns_fidelity_on():
    client = _StubClient(blocks=[], docx=SimpleNamespace(title="T", document_id="D"))
    sheets_client = object()
    export_reader = object()
    _d, _b, parser, _t, _m = download._parse(
        client, Config(), "DOC",
        sheets_client=sheets_client, sheets_export_reader=export_reader,
    )
    assert parser.fidelity_read_sheets is True
    assert parser.sheets_export_reader is export_reader


def test_cli_download_registers_fidelity_read_sheets_flag():
    # The opt-in flag is a real, discoverable CLI surface (mirrors deep-read-sheets).
    out = CliRunner().invoke(cli, ["download", "--help"]).output
    assert "--fidelity-read-sheets" in out
    assert "--deep-read-sheets" in out


def test_cli_download_threads_fidelity_flag_to_handler(monkeypatch):
    # The CLI flag reaches handle_download_command as fidelity_read_sheets=True; the
    # default (flag absent) passes False (byte-identical default path). Use the
    # module + cli group from the CURRENT sys.modules so the patch + invoked cli
    # share one module object even if a prior test reloaded larkdocio.cli.
    import larkdocio.cli as cli_mod

    calls = []
    monkeypatch.setattr(
        cli_mod, "handle_download_command",
        lambda *a, **k: calls.append(k),
    )
    invoke_cli(cli_mod.cli, ["download", DOCX_URL, "--deep-read-sheets", "--fidelity-read-sheets"])
    invoke_cli(cli_mod.cli, ["download", DOCX_URL])
    assert calls[0]["fidelity_read_sheets"] is True
    assert calls[0]["deep_read_sheets"] is True
    assert calls[1]["fidelity_read_sheets"] is False


# --------------------------------------------------------------------------- #
# AC1 — helper-level: where the output directory comes from (LD-650)           #
# --------------------------------------------------------------------------- #

def test_an_explicit_route_is_the_only_helper_that_moves_the_output_dir():
    """TRANSFORMED (LD-650): this pair used to be "the derivation routes / does not route".
    The derivation is gone; the helper that remains is the caller's own subpath."""
    assert download._apply_explicit_route("/base", "area/section/topic") == os.path.join(
        "/base", "area", "section", "topic"
    )


def test_a_body_carrying_metadata_rows_moves_nothing_because_nothing_reads_it():
    """The negative half, and the one that would have caught a derivation left behind: the
    module exposes no callable that turns a document body into a directory."""
    assert not [
        name
        for name in dir(download)
        if "route" in name.lower() and name not in (
            "_apply_explicit_route", "RoutedPath", "ROUTE_EXPLICIT", "ROUTE_DISABLED",
        )
    ], "a body-reading routing helper is back in read/download.py"


# --------------------------------------------------------------------------- #
# AC1 — helper-level: filename policy under a frozen clock (_write_markdown)   #
# --------------------------------------------------------------------------- #

def test_write_markdown_timestamped_title_under_frozen_clock(monkeypatch, tmp_path):
    """title_as_filename (default) → ``[YYYY-MM-DD_HHMM]_<sanitized-title>.md``."""
    class _FrozenDatetime:
        @classmethod
        def now(cls, tz=None):  # tz accepted: the call site asks for UTC (LD-227)
            return _real_datetime(2026, 7, 24, 9, 30, tzinfo=tz)

    monkeypatch.setattr(download, "datetime", _FrozenDatetime)

    download._write_markdown(Config(), str(tmp_path), "TOK", "My Doc", "# body\n")

    expected = tmp_path / f"[2026-07-24_0930]_{sanitize_path_string('My Doc')}.md"
    assert expected.name == "[2026-07-24_0930]_My_Doc.md"
    assert expected.read_text(encoding="utf-8") == "# body\n"


def test_write_markdown_untitled_title_falls_back_to_token(monkeypatch, tmp_path):
    """title_as_filename on but an empty/untitled title → ``[timestamp]_<token>.md``."""
    class _FrozenDatetime:
        @classmethod
        def now(cls, tz=None):  # tz accepted: the call site asks for UTC (LD-227)
            return _real_datetime(2026, 7, 24, 9, 30, tzinfo=tz)

    monkeypatch.setattr(download, "datetime", _FrozenDatetime)

    download._write_markdown(Config(), str(tmp_path), "TOK9", "", "# body\n")

    assert (tmp_path / "[2026-07-24_0930]_TOK9.md").read_text(encoding="utf-8") == "# body\n"


def test_write_markdown_stamp_is_UTC_not_the_machines_local_clock(
    monkeypatch, tmp_path, request
):
    """LD-227 AC3 — the stamp's *basis* is UTC, pinned by construction.

    A shape assertion cannot tell UTC from local, so this test freezes one real
    instant (09:30 UTC) behind a clock whose ``now()`` obeys real ``datetime``
    semantics — naive **local** time when called with no argument, the converted
    instant when called with a tzinfo — and forces the process zone to a
    **non-UTC** one (``Etc/GMT-12`` = UTC+12, where that instant is 21:30).

    Why a machine whose own zone is UTC cannot make this green by accident: the
    zone is set here, not inherited, and the ``preconditions`` assert below fails
    the test outright if the local and UTC renderings ever coincide — so the
    assertion can only pass because the call site asked for UTC.
    """
    if not hasattr(time, "tzset"):  # pragma: no cover - POSIX-only knob
        pytest.skip("TZ switching needs time.tzset (POSIX)")

    ambient_tz = os.environ.get("TZ")

    def _restore_zone():
        # Restore TZ *and* re-apply it: monkeypatch's own undo runs after this
        # test's finalizers, so the env must be put back here, by hand.
        if ambient_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = ambient_tz
        time.tzset()

    request.addfinalizer(_restore_zone)
    os.environ["TZ"] = "Etc/GMT-12"  # POSIX sign convention: UTC+12
    time.tzset()

    instant = _real_datetime(2026, 7, 24, 9, 30, tzinfo=_timezone.utc)
    utc_stamp = "2026-07-24_0930"
    local_stamp = instant.astimezone().strftime("%Y-%m-%d_%H%M")
    assert local_stamp != utc_stamp, (
        "precondition: the forced zone must render this instant differently from UTC"
    )

    class _FrozenClock:
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return instant.astimezone().replace(tzinfo=None)
            return instant.astimezone(tz)

    monkeypatch.setattr(download, "datetime", _FrozenClock)

    download._write_markdown(Config(), str(tmp_path), "TOK", "My Doc", "# body\n")

    written = [p.name for p in tmp_path.iterdir()]
    assert written == [f"[{utc_stamp}]_My_Doc.md"], written
    assert local_stamp not in written[0]


def test_write_markdown_uses_token_when_title_as_filename_false(tmp_path):
    """title_as_filename=False → ``<token>.md`` (no timestamp, title ignored)."""
    config = Config(OutputConfig(title_as_filename=False))

    download._write_markdown(config, str(tmp_path), "TOK123", "Ignored Title", "x")

    assert (tmp_path / "TOK123.md").read_text(encoding="utf-8") == "x"
    assert list(tmp_path.glob("[*.md")) == []


# --------------------------------------------------------------------------- #
# AC1 + AC2 — image/board substitution (_download_images_and_boards)          #
# --------------------------------------------------------------------------- #

def test_download_images_substitutes_first_occurrence_of_duplicate_token(tmp_path):
    """A duplicate token is rewritten to its local link **once** (``replace(.., 1)``).

    AC2 mutant kill: if the image-link substitution is disabled, the first token
    is not rewritten and this assertion fails.
    """
    local = str(tmp_path / "static" / "IMG1.png")
    client = _StubClient(image_paths={"IMG1": local})
    parser = _StubParser(img_tokens=["IMG1"])

    out = download._download_images_and_boards(
        client, Config(), parser, str(tmp_path), "before IMG1 middle IMG1 after"
    )

    assert out == "before static/IMG1.png middle IMG1 after"


def test_download_images_warn_and_continue_on_failed_download(tmp_path):
    """A per-asset download failure is swallowed (warn-and-continue): the markdown
    is left unchanged and no exception escapes (this is *not* a whole-doc failure)."""
    client = _StubClient(image_error=Exception("asset boom"))
    parser = _StubParser(img_tokens=["IMG1"])

    out = download._download_images_and_boards(
        client, Config(), parser, str(tmp_path), "x IMG1 y"
    )

    assert out == "x IMG1 y"


def test_download_boards_warn_and_continue_on_failed_download(tmp_path):
    """A failed board-image download is swallowed (warn-and-continue): markdown
    unchanged, no exception escapes (the board-side warn-and-continue except path)."""
    client = _StubClient(board_error=Exception("board asset boom"))
    parser = _StubParser(board_tokens=["BRD1"])

    out = download._download_images_and_boards(
        client, Config(), parser, str(tmp_path), "x BRD1 y"
    )

    assert out == "x BRD1 y"


def test_download_boards_substitutes_token(tmp_path):
    """Board tokens are rewritten to their local link the same way images are."""
    local = str(tmp_path / "static" / "BRD1.png")
    client = _StubClient(board_paths={"BRD1": local})
    parser = _StubParser(board_tokens=["BRD1"])

    out = download._download_images_and_boards(
        client, Config(), parser, str(tmp_path), "see BRD1 here"
    )

    assert out == "see static/BRD1.png here"


def test_download_boards_substitutes_first_occurrence_of_duplicate_token(tmp_path):
    """A duplicate board token is rewritten to its local link **once**
    (``replace(.., 1)``) — the same first-occurrence contract as images. Pins the
    ``1`` argument for the board loop (LD-082 characterization)."""
    local = str(tmp_path / "static" / "BRD1.png")
    client = _StubClient(board_paths={"BRD1": local})
    parser = _StubParser(board_tokens=["BRD1"])

    out = download._download_images_and_boards(
        client, Config(), parser, str(tmp_path), "before BRD1 middle BRD1 after"
    )

    assert out == "before static/BRD1.png middle BRD1 after"


# --------------------------------------------------------------------------- #
# LD-082 characterization — the twin-loop WARN strings are BYTE-IDENTICAL.     #
# The image/board relink warn text was previously exercised only for           #
# warn-and-continue behavior (markdown unchanged), never asserted verbatim.    #
# These pin the exact message strings the _fetch_and_relink extraction must     #
# preserve (B3).                                                               #
# --------------------------------------------------------------------------- #

def test_download_image_warn_message_is_byte_identical(tmp_path, caplog):
    """A failed image download logs the exact ``Could not download image
    {token}: {e}`` string (byte-identical warn contract, B3)."""
    client = _StubClient(image_error=Exception("asset boom"))
    parser = _StubParser(img_tokens=["IMG1"])

    with caplog.at_level("WARNING", logger="larkdocio"):
        download._download_images_and_boards(
            client, Config(), parser, str(tmp_path), "x IMG1 y"
        )

    messages = [r.message for r in caplog.records]
    assert "Could not download image IMG1: asset boom" in messages


def test_download_board_warn_message_is_byte_identical(tmp_path, caplog):
    """A failed board download logs the exact ``Could not download board image
    {token}: {e}`` string (byte-identical warn contract, B3)."""
    client = _StubClient(board_error=Exception("board asset boom"))
    parser = _StubParser(board_tokens=["BRD1"])

    with caplog.at_level("WARNING", logger="larkdocio"):
        download._download_images_and_boards(
            client, Config(), parser, str(tmp_path), "x BRD1 y"
        )

    messages = [r.message for r in caplog.records]
    assert "Could not download board image BRD1: board asset boom" in messages


# --------------------------------------------------------------------------- #
# LD-040 (AC4) — download_attachments knob (opt-in, default False)            #
# --------------------------------------------------------------------------- #


class _RecordingClient:
    """A client that records every ``download_image`` call. ``fail=True`` makes
    the download raise (to exercise the warn-and-continue path)."""

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def download_image(self, token, out_dir):
        self.calls.append((token, out_dir))
        if self.fail:
            raise Exception("attachment asset boom")
        return str(os.path.join(out_dir, f"{token}.bin"))

    def download_board_image(self, *a, **k):  # pragma: no cover - no boards here
        raise AssertionError("no boards expected")


def test_attachments_not_downloaded_by_default(tmp_path):
    """AC4 (default False): a queued file token is NOT fetched — zero attachment
    network. The client's download_image is never called for attachments (maintainer
    directive: attachment binaries are NEVER fetched by default)."""
    client = _RecordingClient()
    parser = _StubParser(img_tokens=[], board_tokens=[], file_tokens=["FTOK"])

    out = download._download_images_and_boards(
        client, Config(), parser, str(tmp_path), "before FTOK after"
    )

    assert client.calls == [], (
        "download_attachments defaults False → NO attachment download call"
    )
    # Marker-only: the markdown is left untouched (no token→link substitution).
    assert out == "before FTOK after"


def test_attachments_downloaded_when_enabled(tmp_path):
    """AC4 (True): the stubbed client IS asked to download the queued file token,
    into the assets (image_dir) directory alongside images."""
    client = _RecordingClient()
    parser = _StubParser(img_tokens=[], board_tokens=[], file_tokens=["FTOK"])
    config = Config(OutputConfig(download_attachments=True))

    download._download_images_and_boards(
        client, config, parser, str(tmp_path), "before FTOK after"
    )

    assert len(client.calls) == 1, client.calls
    token, out_dir = client.calls[0]
    assert token == "FTOK"
    assert out_dir == os.path.join(str(tmp_path), "static"), out_dir


def test_attachment_download_failure_warns_and_continues(tmp_path, caplog):
    """AC4 (True + failure): a per-attachment download failure is swallowed
    (warn-and-continue) — no exception escapes, the markdown is unchanged, and the
    failure is logged."""
    client = _RecordingClient(fail=True)
    parser = _StubParser(img_tokens=[], board_tokens=[], file_tokens=["FTOK"])
    config = Config(OutputConfig(download_attachments=True))

    with caplog.at_level("WARNING", logger="larkdocio"):
        out = download._download_images_and_boards(
            client, config, parser, str(tmp_path), "x FTOK y"
        )

    assert out == "x FTOK y"  # unchanged, no exception escaped
    assert any("FTOK" in r.message for r in caplog.records), (
        "a failed attachment download must warn (warn-and-continue)"
    )


def test_download_images_skipped_when_skip_img_download(tmp_path):
    """skip_img_download short-circuits the whole block: no substitution, and the
    client is never consulted (its download would raise if it were)."""
    client = _StubClient(image_error=Exception("must not be called"))
    parser = _StubParser(img_tokens=["IMG1"], board_tokens=["BRD1"])
    config = Config(OutputConfig(skip_img_download=True))

    out = download._download_images_and_boards(
        client, config, parser, str(tmp_path), "IMG1 and BRD1"
    )

    assert out == "IMG1 and BRD1"


# --------------------------------------------------------------------------- #
# AC1 — helper-level: --dump payload (_dump_json)                             #
# --------------------------------------------------------------------------- #

def test_dump_json_writes_payload(tmp_path):
    """--dump writes ``<token>.json`` with a document + per-block payload."""
    docx = SimpleNamespace(title="T", document_id="DOCID")
    blocks = [SimpleNamespace(block_id="b1"), SimpleNamespace(block_id="b2")]

    download._dump_json(docx, blocks, str(tmp_path), "TOK")

    data = json.loads((tmp_path / "TOK.json").read_text(encoding="utf-8"))
    # ``document`` + ``blocks`` are the pinned keepers; the sidecar also declares the
    # Markdown filename stamp's timezone for a ledger reading it (LD-335) — that field
    # is pinned by ``tests/test_filename_timestamp_utc_disclosure.py``.
    assert {"document", "blocks"} <= set(data)
    assert len(data["blocks"]) == 2


# --------------------------------------------------------------------------- #
# AC1 files-on-disk end state + AC2 mutant kills (full pipeline via handle)    #
# --------------------------------------------------------------------------- #

def test_handle_download_writes_markdown_and_substitutes_image(monkeypatch, tmp_path):
    """End-to-end: the written markdown has the image token rewritten to its local
    link. AC2 mutant kill — a disabled substitution leaves the raw token and fails."""
    _patch_env(monkeypatch)
    local = str(tmp_path / "static" / "IMG1.png")
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient(image_paths={"IMG1": local}))
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown="pic IMG1 end\n", img_tokens=["IMG1"]))

    download.handle_download_command(DOCX_URL, str(tmp_path), "", False, "")

    written = list(tmp_path.glob("*.md"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "pic static/IMG1.png end\n"


def test_handle_download_does_NOT_route_a_body_that_used_to_self_route(monkeypatch, tmp_path):
    """TRANSFORMED (LD-650). It used to assert the derived subpath; it now asserts the
    derivation's ABSENCE on the very body that triggered it, which is the same test doing
    the opposite job — and is what would catch a derivation quietly returning."""
    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    body = "| Area | Sales |\n| Section | Billing |\n| Topic | Invoices |\n"
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown=body))

    result = download.handle_download_command(DOCX_URL, str(tmp_path), "", False, "")

    assert list(tmp_path.glob("*.md")), "the markdown lands flat in -o"
    assert not (tmp_path / "sales").exists(), "no derived subpath may be built"
    assert result.output_dir == str(tmp_path)


def test_handle_download_with_no_route_lands_at_the_output_dir_and_answers_its_record(
    monkeypatch, tmp_path
):
    """The SECOND end-to-end no-route landing assertion, kept deliberately (LD-650): the
    no-route branch reads ``.record`` off its own value, so a branch that returns a bare
    ``str`` raises ``AttributeError`` on every ordinary download — invisible to a smoke
    import, and caught here."""
    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown="# plain\n"))

    result = download.handle_download_command(DOCX_URL, str(tmp_path), "", False, "")

    assert list(tmp_path.glob("*.md"))
    assert result.output_dir == str(tmp_path)
    assert list(result.route) == [
        "routed", "reason", "derivation_ran", "labels_found", "labels_missing"
    ]
    assert result.route["reason"] == download.ROUTE_DISABLED


def test_handle_download_dump_writes_json(monkeypatch, tmp_path):
    """End-to-end with --dump: the raw ``<token>.json`` payload is written."""
    _patch_env(monkeypatch)
    docx = SimpleNamespace(title="Doc Title", document_id="DOCID")
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient(docx=docx, blocks=[]))
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown="# body\n"))

    download.handle_download_command(DOCX_URL, str(tmp_path), "", True, "")

    assert (tmp_path / "AbCdEfG123.json").exists()


# --------------------------------------------------------------------------- #
# LD-021 — remaining edge branches (test-only characterization; no behavior    #
# change). Each targets a specific uncovered branch called out in the AC.      #
# --------------------------------------------------------------------------- #

def test_encoder_returns_dunder_dict_for_object_with_dict():
    """LarkObjectEncoder.default returns ``__dict__`` for a normal SDK-like object
    (the non-fallback arm; kept alongside the fallback test as the contrast case)."""
    obj = SimpleNamespace(a=1, b="x")

    assert download.LarkObjectEncoder().default(obj) == {"a": 1, "b": "x"}


def test_encoder_str_fallback_for_object_without_dict():
    """download.py:22-25 — an object with **no** ``__dict__`` falls through to
    ``return str(obj)``. A ``set`` has no ``__dict__`` and is not JSON-native."""
    value = {1, 2, 3}
    assert not hasattr(value, "__dict__")  # guards the branch precondition

    assert download.LarkObjectEncoder().default(value) == str(value)


def test_resolve_doc_rewrites_wiki_node(monkeypatch):
    """download.py:60-63 — a ``wiki`` doc_type resolves the real obj_type/obj_token
    via ``client.get_wiki_node_info`` and rewrites them."""
    monkeypatch.setattr(
        download, "validate_download_url",
        lambda url, allow_host: ("host.larksuite.com", "wiki", "WIKITOK"),
    )
    monkeypatch.setattr(download, "read_config_from_file", lambda path: Config())
    node = SimpleNamespace(obj_type="docx", obj_token="REALTOK")

    class _WikiClient:
        def __init__(self, *a, **k):
            pass

        def get_wiki_node_info(self, token):
            assert token == "WIKITOK"
            return node

    monkeypatch.setattr(download, "Client", _WikiClient)

    client, config, doc_type, doc_token = download._resolve_doc(
        "https://host.larksuite.com/wiki/WIKITOK", "", "", "id", "sec"
    )

    assert doc_type == "docx"
    assert doc_token == "REALTOK"


def test_resolve_doc_legacy_docs_guard_raises(monkeypatch):
    """download.py:65-66 — a ``docs`` doc_type raises the 'no longer supported' guard."""
    monkeypatch.setattr(
        download, "validate_download_url",
        lambda url, allow_host: ("host.larksuite.com", "docs", "TOK"),
    )
    monkeypatch.setattr(download, "read_config_from_file", lambda path: Config())
    monkeypatch.setattr(download, "Client", lambda *a, **k: object())

    with pytest.raises(Exception, match="no longer supported"):
        download._resolve_doc("https://host.larksuite.com/docs/TOK", "", "", "id", "sec")


def test_dump_json_warns_and_continues_on_serialization_error(monkeypatch, tmp_path, caplog):
    """download.py:156-157 — a ``json.dump`` failure is swallowed (warn-and-continue):
    no exception escapes and the failure is logged."""
    docx = SimpleNamespace(title="T", document_id="D")

    def _boom(*a, **k):
        raise ValueError("cannot serialize")

    monkeypatch.setattr(download.json, "dump", _boom)

    with caplog.at_level("WARNING", logger="larkdocio"):
        download._dump_json(docx, [], str(tmp_path), "TOK")  # must not raise

    assert any("Failed to dump pure JSON" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# LD-033 (R-S0 net, AC3 / P0.3) — download credential-validation.             #
#                                                                             #
# The existing B1 exit-code tests only exercise the BOTH-missing case, which  #
# does NOT distinguish `if not app_id or not app_secret:` from the `and`      #
# mutant. These pin the SINGLE-missing-credential boundary (the `or` -> `and` #
# survivor from dev/mutation-baseline-2026-07-24-extended.md) and the         #
# no-covering-test `_validate_and_init` return-None error branch directly.    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "app_id, app_secret, expected",
    [
        ("id", "secret", ("id", "secret")),  # both present -> the credentials
        ("", "secret", None),                # id missing  -> rejected (kills or->and)
        ("id", "", None),                    # secret missing -> rejected (kills or->and)
        ("", "", None),                      # both missing -> rejected
    ],
)
def test_validate_and_init_rejects_any_missing_credential(
    monkeypatch, app_id, app_secret, expected
):
    """download.py:36 — `if not app_id or not app_secret:` rejects when EITHER
    credential is missing. The two single-missing rows kill the `or` -> `and`
    survivor: under `and`, a single-missing pair would wrongly pass through."""
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(
        download, "get_read_credentials", lambda: (app_id, app_secret)
    )
    assert download._validate_and_init(None) == expected


def test_validate_and_init_logs_guidance_on_missing_credential(monkeypatch, caplog):
    """download.py:37-42 — the missing-credential branch logs the operator
    guidance (the no-covering-test error branch) before returning None."""
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: ("id", ""))

    with caplog.at_level("ERROR", logger="larkdocio"):
        result = download._validate_and_init(None)

    assert result is None
    assert any("Missing Lark App Credentials" in r.message for r in caplog.records)


def test_single_missing_credential_download_exits_nonzero(monkeypatch, tmp_path):
    """End-to-end: a SINGLE missing credential (secret) must still fail the
    download with a nonzero exit — the `or` semantics carried through the CLI."""
    _patch_env(monkeypatch, app_id="id", app_secret="")

    result = CliRunner().invoke(cli, ["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0


# --------------------------------------------------------------------------- #
# LD-105 — opt-in embedded-sheet deep-read plumbing                             #
# --------------------------------------------------------------------------- #

def test_parse_threads_sheets_client_into_parser_deep_read_on():
    """``_parse`` with a ``sheets_client`` builds a Parser with deep-read ON and
    that client attached (so the type-30 handler can bridge)."""
    client = _StubClient(docx=SimpleNamespace(title="T", document_id="DOCID"), blocks=[])
    sentinel = object()
    _docx, _blocks, parser, _title, _md = download._parse(
        client, Config(), "TOK", sheets_client=sentinel
    )
    assert parser.deep_read_sheets is True
    assert parser.sheets_client is sentinel


def test_parse_default_leaves_deep_read_off():
    """``_parse`` with no ``sheets_client`` leaves the Parser byte-identical to
    today: deep-read OFF, no client."""
    client = _StubClient(docx=SimpleNamespace(title="T", document_id="DOCID"), blocks=[])
    _docx, _blocks, parser, _title, _md = download._parse(client, Config(), "TOK")
    assert parser.deep_read_sheets is False
    assert parser.sheets_client is None


def test_handle_download_deep_read_flag_builds_sheets_client(monkeypatch, tmp_path):
    """``handle_download_command(deep_read_sheets=True)`` builds a SheetsReadClient
    from the read creds + the URL's domain and threads it into ``_parse``."""
    _patch_env(monkeypatch, app_id="APPID", app_secret="SECRET")
    monkeypatch.setattr(download, "read_config_from_file", lambda path: Config())
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())

    built = {}

    class _FakeSheetsClient:
        def __init__(self, app_id, app_secret, domain):
            built["args"] = (app_id, app_secret, domain)

    monkeypatch.setattr(download, "SheetsReadClient", _FakeSheetsClient)

    captured = {}
    real_parse = download._parse

    def _spy_parse(client, config, doc_token, *, sheets_client=None, sheets_export_reader=None, base_client=None):
        captured["sheets_client"] = sheets_client
        captured["sheets_export_reader"] = sheets_export_reader
        return real_parse(
            client, config, doc_token,
            sheets_client=sheets_client, sheets_export_reader=sheets_export_reader,
        )

    monkeypatch.setattr(download, "_parse", _spy_parse)

    download.handle_download_command(
        DOCX_URL, str(tmp_path), "", False, "", deep_read_sheets=True
    )

    assert built["args"] == ("APPID", "SECRET", "larksuite.com")
    assert isinstance(captured["sheets_client"], _FakeSheetsClient)


def test_handle_download_default_builds_no_sheets_client(monkeypatch, tmp_path):
    """The default download path never constructs a SheetsReadClient (zero Sheets
    surface) — ``_parse`` gets ``sheets_client=None``."""
    _patch_env(monkeypatch, app_id="APPID", app_secret="SECRET")
    monkeypatch.setattr(download, "read_config_from_file", lambda path: Config())
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())

    def _boom(*a, **k):
        raise AssertionError("SheetsReadClient built on the default path")

    monkeypatch.setattr(download, "SheetsReadClient", _boom)

    captured = {}
    real_parse = download._parse

    def _spy_parse(client, config, doc_token, *, sheets_client=None, sheets_export_reader=None, base_client=None):
        captured["sheets_client"] = sheets_client
        captured["sheets_export_reader"] = sheets_export_reader
        return real_parse(
            client, config, doc_token,
            sheets_client=sheets_client, sheets_export_reader=sheets_export_reader,
        )

    monkeypatch.setattr(download, "_parse", _spy_parse)

    download.handle_download_command(DOCX_URL, str(tmp_path), "", False, "")

    assert captured["sheets_client"] is None


def _fake_handle_factory(seen):
    def _fake_handle(url, output_dir, allow_host, dump, config_file, env_file=None,
                     deep_read_sheets=False, fidelity_read_sheets=False,
                     deep_read_bases=False, local_time=False, route=None):
        seen["deep_read_sheets"] = deep_read_sheets
        seen["fidelity_read_sheets"] = fidelity_read_sheets
        seen["deep_read_bases"] = deep_read_bases
        seen["local_time"] = local_time
        seen["route"] = route
    return _fake_handle


def test_cli_download_deep_read_sheets_flag_threads_through(monkeypatch):
    """The ``--deep-read-sheets`` CLI flag reaches ``handle_download_command``.

    Fetch the module + its ``cli`` group from the CURRENT ``sys.modules`` so the
    patched ``handle_download_command`` and the invoked ``cli`` share one module
    object even if a prior test reloaded ``larkdocio.cli``
    (``test_cli_logging_config`` pops+re-imports it) — the stale module-level
    ``from larkdocio.cli import cli`` would otherwise miss the patch.
    """
    import larkdocio.cli as cli_mod

    seen = {}
    monkeypatch.setattr(cli_mod, "handle_download_command", _fake_handle_factory(seen))

    result = CliRunner().invoke(
        cli_mod.cli, ["download", DOCX_URL, "-o", "./out", "--deep-read-sheets"]
    )
    assert result.exit_code == 0
    assert seen["deep_read_sheets"] is True


def test_cli_download_deep_read_off_by_default(monkeypatch):
    """Without the flag, ``handle_download_command`` receives deep_read_sheets=False."""
    import larkdocio.cli as cli_mod

    seen = {}
    monkeypatch.setattr(cli_mod, "handle_download_command", _fake_handle_factory(seen))

    result = CliRunner().invoke(cli_mod.cli, ["download", DOCX_URL, "-o", "./out"])
    assert result.exit_code == 0
    assert seen["deep_read_sheets"] is False
