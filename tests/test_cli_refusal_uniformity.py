"""A deliberate refusal reaches the terminal as ONE ``Error:`` line — on every subcommand.

A ``LarkConfigError`` is the toolkit's *user-input / configuration* refusal: the message is
already written for the person reading it (*"that is a SPREADSHEET url, not a document url…"*).
``download`` used to let it fall through the unknown-error path, which logs
``"Report the following if it is a bug"`` and re-raises — so a well-worded refusal arrived as a
Python traceback labelled a possible bug, while the same class out of ``mermaid`` printed a
clean ``Error:`` line.

The three assertions here are the whole contract:

* the refusal text survives **verbatim**, prefixed with ``Error: `` and no traceback;
* the handling is **uniform across the click group**, walked rather than named, so a future
  subcommand cannot introduce a third convention;
* an **unexpected** exception keeps its traceback and its bug-report banner — the fork is the
  point, not the suppression.
"""
import logging
import pathlib
import re

import click
import pytest
from click.testing import CliRunner

import token_mint_probe as probe
from larkdocio import cli as cli_mod
from larkdocio.cli import cli
from larkdocio.errors import LarkConfigError
from larkdocio.read import download

DOCX_URL = "https://example.larksuite.com/docx/AbCdEfG123"
SHEETS_URL = "https://example.larksuite.com/sheets/AbCdEfG123"
BASE_URL = "https://example.larksuite.com/base/AbCdEfG123"


def _patch_env(monkeypatch):
    """Neutralize ``.env`` loading and pin credential resolution (offline)."""
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: ("id", "secret"))


def _invoke(args, **kwargs):
    """Invoke the command line with a FRESH log handler — harness hygiene, not leniency.

    ``_configure_logging`` binds its ``StreamHandler`` to whatever ``sys.stderr`` is at the
    first invocation in the process (once-per-process, as a real run has), while ``CliRunner``
    swaps that stream per invocation. A handler left over from an earlier invocation therefore
    writes into a closed stream, and ``logging`` prints its own ``--- Logging error ---``
    traceback into THIS run's output — which would make the no-traceback assertions below
    measure the harness instead of the refusal. Clearing the handlers lets each invocation
    configure its own, which is what one real process does.
    """
    logging.getLogger("larkdocio").handlers.clear()
    return CliRunner().invoke(cli, args, **kwargs)


# --------------------------------------------------------------------------- #
# AC-A1 — the refusal prints as one Error: line, per refusal flavour.          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("url, doc_type", [(SHEETS_URL, "sheets"), (BASE_URL, "base")])
def test_a_non_document_url_refusal_prints_one_Error_line_and_no_traceback(
        monkeypatch, tmp_path, url, doc_type):
    _patch_env(monkeypatch)
    expected = download._NON_DOCUMENT_URL_MESSAGES[doc_type]

    result = _invoke(["download", url, "-o", str(tmp_path)])

    assert result.exit_code != 0, "a refused url must exit nonzero"
    assert "Error: " in result.output, f"no Error: line in:\n{result.output}"
    # The refusal's own wording is what makes it actionable — it must survive verbatim.
    assert expected in " ".join(result.output.split())
    assert "Traceback" not in result.output, "a deliberate refusal is not a crash"
    assert "Report the following if it is a bug" not in result.output, (
        "a deliberate refusal must not be labelled a possible bug")
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"the refusal escaped as {result.exception!r} rather than a clean exit")


def test_every_non_document_url_flavour_is_covered_by_this_uniformity(monkeypatch, tmp_path):
    """Every entry in the refusal map, not the two hand-named ones.

    **LD-323 — the url is built from the PATH SHAPE, not from the type.** The two were the same
    word until a Drive folder arrived at the two-segment path ``drive/folder`` while reporting
    the one-word type ``drive``; spelling ``/drive/`` here would test a url the validator refuses
    before this map is ever consulted, which would make the whole walk vacuous for that flavour.
    """
    from larkdocio.common import URL_PATH_SHAPES

    _patch_env(monkeypatch)
    shape_of = {url_type: shape for shape, url_type in URL_PATH_SHAPES.items()}
    for doc_type, message in download._NON_DOCUMENT_URL_MESSAGES.items():
        url = f"https://example.larksuite.com/{shape_of[doc_type]}/AbCdEfG123"
        result = _invoke(["download", url, "-o", str(tmp_path)])
        assert "Traceback" not in result.output, f"{doc_type} url printed a traceback"
        assert "Error: " in result.output, f"{doc_type} url printed no Error: line"
        assert message in " ".join(result.output.split()), f"{doc_type} lost its wording"


# --------------------------------------------------------------------------- #
# AC-A2 — the handling is uniform across the whole click group, walked.        #
# --------------------------------------------------------------------------- #

def test_EVERY_subcommand_turns_a_LarkConfigError_into_a_clean_Error_line():
    """Walk the group rather than naming subcommands: a future one inherits the contract.

    Each command is invoked through click's own machinery with its callback replaced by one
    that raises the refusal, so what is measured is the boundary behaviour, not a promise
    written next to each command.
    """
    commands = cli.commands
    assert commands, "the group has no subcommands to walk"

    for name, command in sorted(commands.items()):
        refusal = f"a deliberate refusal out of {name}"

        def _raise(*args, _refusal=refusal, **kwargs):
            raise LarkConfigError(_refusal)

        ctx = click.Context(command, info_name=name, parent=click.Context(cli))
        ctx.obj = {}
        original = command.callback
        command.callback = _raise
        try:
            with pytest.raises(click.ClickException) as caught:
                command.invoke(ctx)
        finally:
            command.callback = original

        assert not isinstance(caught.value, click.UsageError), (
            f"{name} reported a refusal as a usage error")
        assert str(caught.value) == refusal, (
            f"{name} did not preserve the refusal text verbatim: {str(caught.value)!r}")
        assert caught.value.__cause__ is None, (
            f"{name} kept the original exception chained, so a traceback can reach the "
            "terminal")


def test_the_uniformity_is_STRUCTURAL_not_repeated_per_command():
    """The guarantee lives on the command class the group mints, so it cannot be forgotten.

    A per-command ``try/except`` is the shape that lets the third subcommand ship without
    one; this asserts the group hands every command the same class.
    """
    for name, command in cli.commands.items():
        assert isinstance(command, cli_mod._RefusalUniformCommand), (
            f"{name} is a plain {type(command).__name__} — it can ship its own convention")


# --------------------------------------------------------------------------- #
# AC-A3 — an unexpected exception still surfaces its traceback.               #
# --------------------------------------------------------------------------- #

def test_an_unexpected_exception_KEEPS_its_traceback_and_bug_banner(monkeypatch, tmp_path):
    """The other side of the fork. ``check_err``'s banner exists for genuine bugs."""
    _patch_env(monkeypatch)

    class _Boom:
        def get_docx_content(self, doc_token):
            raise AttributeError("'NoneType' object has no attribute 'block_type'")

    monkeypatch.setattr(download, "Client", lambda *a, **k: _Boom())

    result = _invoke(["download", DOCX_URL, "-o", str(tmp_path)], catch_exceptions=True)

    assert result.exit_code != 0
    assert isinstance(result.exception, AttributeError), (
        f"an unexpected {type(result.exception).__name__} was reduced to a clean refusal — "
        "the bug-report path must survive for the class it was written for")
    assert "Report the following if it is a bug" in result.output


def test_the_fork_is_decided_by_the_EXCEPTION_CLASS_only(monkeypatch, tmp_path):
    """A ``LarkConfigError`` raised from deep in the pipeline is still a refusal, and a
    ``KeyError`` raised from the same place is still a bug — position does not decide."""
    _patch_env(monkeypatch)

    class _Refusing:
        def get_docx_content(self, doc_token):
            raise LarkConfigError("the document is a type this reader cannot read")

    class _Buggy:
        def get_docx_content(self, doc_token):
            raise KeyError("block_type")

    monkeypatch.setattr(download, "Client", lambda *a, **k: _Refusing())
    refused = _invoke(["download", DOCX_URL, "-o", str(tmp_path)])
    assert "Error: the document is a type this reader cannot read" in refused.output
    assert "Traceback" not in refused.output

    monkeypatch.setattr(download, "Client", lambda *a, **k: _Buggy())
    crashed = _invoke(["download", DOCX_URL, "-o", str(tmp_path)], catch_exceptions=True)
    assert isinstance(crashed.exception, KeyError)


# --------------------------------------------------------------------------- #
# LD-658 AC4 — the seam covers the two BUILTIN refusal classes, and a token   #
# mint failure stops being reported as a possible bug in this library.        #
# --------------------------------------------------------------------------- #

BUG_BANNER = "Report the following if it is a bug"


def test_a_MISTYPED_download_url_is_a_refusal_not_a_bug_report(monkeypatch, tmp_path):
    """**LD-658 AC4.** ``common/url.py`` raises a bare builtin ``ValueError`` **by stated
    contract** (its own docstring: *"a ``ValueError`` refusal, never a default"*), and the seam
    converted only ``LarkConfigError``. Executed before the fix: the refusal printed, then
    ``====================``, then the bug-report banner, then a ~45-line traceback — for a
    typo the user made.
    """
    _patch_env(monkeypatch)
    result = _invoke(["download", "https://example.larksuite.com/docx/", "-o", str(tmp_path)])

    assert result.exit_code != 0
    assert "Error: " in result.output
    assert "not a recognised Lark URL" in " ".join(result.output.split())
    assert "Traceback" not in result.output
    assert BUG_BANNER not in result.output, (
        "the user's own typo is still being presented as a possible bug in this library")


def test_the_FOLDER_verb_had_no_handler_at_all_and_now_refuses_like_download(monkeypatch, tmp_path):
    """AC4 names this as the worse half: ``larkdocio folder <bad url>`` printed a **bare
    traceback with no refusal line**, because the conversion it needed was on a class the seam
    did not catch. Fixing the seam fixes every verb at once — which is the reason the seam is on
    the command class (``_RefusalUniformCommand``) rather than written per command."""
    # LD-700: the verb's env resolution creates ./.env when none exists; run it in tmp_path so
    # the suite never writes one into the checkout.
    monkeypatch.chdir(tmp_path)
    result = _invoke(["folder", "https://example.larksuite.com/drive/folder/", "-o",
                      str(tmp_path)])

    assert result.exit_code != 0
    assert "Error: " in result.output, f"still no refusal line:\n{result.output}"
    assert "Traceback" not in result.output
    assert BUG_BANNER not in result.output


def test_an_OSError_refuses_cleanly_AND_still_says_it_may_be_ours(monkeypatch, tmp_path):
    """AC4 widens the seam to ``OSError`` so LD-659's filename overflow surfaces as a refusal.

    The hazard in that widening, named rather than assumed: an ``OSError`` is **not** a refusal
    contract anywhere in this library — it is a fact about the machine, the path, *or a fault of
    ours* — so converting it silently would bury an internal I/O bug in a bland one-liner. The
    conversion therefore **discloses the ambiguity** and says how to get the traceback back.
    ``ValueError`` gets no such tail because ``common/url.py`` documents it as a refusal class.
    """
    _patch_env(monkeypatch)

    class _Overflowing:
        def get_docx_content(self, doc_token):
            raise OSError(36, "File name too long", "/out/" + "漢" * 90 + ".md")

    monkeypatch.setattr(download, "Client", lambda *a, **k: _Overflowing())
    result = _invoke(["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "File name too long" in result.output, "the OS's own words must survive"
    folded = " ".join(result.output.split())
    assert cli_mod.OSERROR_MAY_BE_OURS in folded, (
        "an OSError was reduced to a bland refusal with no hint that it might be a fault in "
        "larkdocio rather than in the caller's environment")
    assert "LOG_LEVEL=DEBUG" in folded, "the traceback route is not named"


def test_a_TOKEN_MINT_failure_names_the_CREDENTIALS_not_a_bug_in_this_library(
        monkeypatch, tmp_path):
    """**LD-658 AC4, second half (the seat's correction).** A wrong App ID/Secret fails the SDK
    token handshake with ``lark_oapi``'s ``ObtainAccessTokenException`` — neither a
    ``LarkAPIError`` nor a ``ValueError`` nor an ``OSError``, so widening the seam does **not**
    catch it, and it landed in ``_report_error``'s default arm with the bug-report banner and a
    traceback. The user was never told it was a credential problem, which variables to fix, or
    which ``.env`` was read. This is the second most likely first-run mistake.
    """
    from lark_oapi.core.exception import ObtainAccessTokenException

    from larkdocio.common.auth import resolved_read_env

    _patch_env(monkeypatch)

    class _BadSecret:
        def get_docx_content(self, doc_token):
            raise ObtainAccessTokenException(
                "obtain tenant access token failed", 10003, "app not exist or app secret error")

    monkeypatch.setattr(download, "Client", lambda *a, **k: _BadSecret())
    result = _invoke(["download", DOCX_URL, "-o", str(tmp_path)])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert BUG_BANNER not in result.output, (
        "a wrong app secret is still being reported as a possible bug in this library")
    folded = " ".join(result.output.split())
    # Lark's own words survive.
    assert "app not exist or app secret error" in folded
    # ...and the two things the user actually needs: which variables, and which .env.
    for var in resolved_read_env():
        assert var in folded, f"{var} — the variable in force is not named"
    assert ".env" in folded


def test_the_token_mint_arm_names_the_env_pair_IN_FORCE_not_a_hard_coded_pair(monkeypatch):
    """The variable names are read off ``resolved_read_env()``, which answers with the pair that
    actually resolved (preferred ``LARK_READ_APP_*`` or the legacy fallback). A hard-coded pair
    would send a legacy-configured caller to edit variables they do not have."""
    import inspect

    source = inspect.getsource(download._report_error)
    assert "resolved_read_env" in source, (
        "the arm hard-codes credential variable names instead of asking which pair is in force")
    assert "LARK_READ_APP_ID" not in source and "LARK_APP_ID" not in source


def test_the_bug_report_banner_now_has_a_DESTINATION(monkeypatch, tmp_path):
    """AC4's *"also"*: the banner demanded a bug report while ``pyproject.toml`` shipped no
    ``[project.urls]``, so there was nowhere to send it. The url is authored once and this
    checks the projection, not a retyped copy."""
    import tomllib
    from pathlib import Path

    from larkdocio.common import reporting

    urls = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["urls"]
    assert reporting.ISSUES_URL == urls["Issues"], (
        "the runtime banner's destination and the wheel's METADATA disagree")

    _patch_env(monkeypatch)

    class _Buggy:
        def get_docx_content(self, doc_token):
            raise KeyError("block_type")

    monkeypatch.setattr(download, "Client", lambda *a, **k: _Buggy())
    result = _invoke(["download", DOCX_URL, "-o", str(tmp_path)], catch_exceptions=True)
    assert BUG_BANNER in result.output
    assert reporting.ISSUES_URL in " ".join(result.output.split()), (
        "the banner still demands a bug report without naming where it goes")


# --------------------------------------------------------------------------- #
# LD-658 — how the token-mint arm's refusal is FORMATTED, on every subcommand.  #
# --------------------------------------------------------------------------- #

def _rejected_token():
    from lark_oapi.core.exception import ObtainAccessTokenException

    return ObtainAccessTokenException(
        "obtain tenant access token failed", 10003, "app not exist or app secret error")


def test_the_seam_FORMATS_an_injected_token_failure_the_same_way_on_every_subcommand(caplog):
    """**FORMATTING, not coverage — renamed in the LD-658 third round, and the rename is the
    point.**

    This test **injects** ``ObtainAccessTokenException`` into each command's callback. That
    proves the seam formats and exits correctly wherever such an exception arrives, and it proves
    **nothing whatsoever** about whether a real run on that verb ever raises that class. Its
    former name — *"EVERY subcommand reports a REJECTED APP SECRET as a credential problem"* —
    claimed the second thing, was cited for it, and let a false consumer-facing claim ship: the
    library has **two** token-mint paths (see
    :func:`test_the_token_mint_COVERAGE_is_per_TOKEN_PATH_and_the_gap_is_pinned` below) and only
    one of them raises this class.

    **An artificial population cannot support a coverage claim.** That is the same blind spot
    caught three times inside this issue's own fix round; this was the fourth, and the cure here
    is honesty about scope rather than a stronger assertion — the coverage question is asked by
    the next test, against the real mint.
    """
    commands = cli.commands
    assert commands, "the group has no subcommands to walk"

    for name, command in sorted(commands.items()):
        def _raise(*args, **kwargs):
            raise _rejected_token()

        ctx = click.Context(command, info_name=name, parent=click.Context(cli))
        ctx.obj = {}
        original = command.callback
        command.callback = _raise
        caplog.clear()
        try:
            with caplog.at_level("ERROR", logger="larkdocio"):
                with pytest.raises(click.ClickException) as caught:
                    command.invoke(ctx)
        finally:
            command.callback = original

        assert not isinstance(caught.value, click.UsageError), name
        assert caught.value.__cause__ is None, (
            f"{name} kept the original exception chained, so a traceback can reach the terminal")
        emitted = " ".join(r.message for r in caplog.records)
        assert "CREDENTIAL problem" in emitted, (
            f"{name} does not tell the user this is a credential problem: {emitted!r}")
        assert "app not exist or app secret error" in emitted, (
            f"{name} swallowed Lark's own words")
        assert BUG_BANNER not in emitted, (
            f"{name} still presents a wrong App Secret as a possible bug in this library")


def test_the_guidance_is_AUTHORED_ONCE_and_the_two_callers_differ_only_in_the_PAIRS():
    """The reader's arm and the CLI seam must not become two copies of the same paragraph.

    Held structurally: both call the one authored function, and the ONLY difference is how
    precisely each can name the culprit — the reader knows exactly one pair can be at fault, the
    seam covers verbs that write as well as read and says so instead of guessing.
    """
    import inspect

    from larkdocio.common.auth import WRITE_ENV, resolved_read_env, token_mint_refusal_lines

    reader = token_mint_refusal_lines((resolved_read_env(),))
    seam = token_mint_refusal_lines((resolved_read_env(), WRITE_ENV))

    # The invariant half is byte-identical between the two callers.
    assert reader[:2] == seam[:2], "the two callers have drifted into two paragraphs"
    # The reader names one pair and does not mention the write pair at all.
    for var in resolved_read_env():
        assert var in reader[2] and var in seam[2]
    assert WRITE_ENV[0] not in reader[2], (
        "the reader's arm names the WRITE pair — it would send a reader to edit variables no "
        "read call consults")
    assert WRITE_ENV[0] in seam[2]
    # ...and the seam says it does not know, rather than picking one.
    assert "does not say WHICH app" in seam[2]
    assert "does not say WHICH app" not in reader[2]

    # Structural: neither call site re-authors the words.
    from larkdocio import cli as cli_module
    from larkdocio.read import download as download_module

    # The seam's side of this is read off the whole COMMAND CLASS, not off ``invoke`` alone:
    # LD-672 gave it a second arm and moved the shared three lines into one helper on the same
    # class, which is the opposite of the drift this arm guards against.
    for source in (inspect.getsource(cli_module._RefusalUniformCommand),
                   inspect.getsource(download_module._report_error)):
        assert "token_mint_refusal_lines" in source
        assert "CREDENTIAL problem" not in source, (
            "an operator-facing line is written at the call site instead of in the one place "
            "that authors it")


def test_the_reader_keeps_the_NARROWER_answer_and_never_reaches_the_seam(monkeypatch, tmp_path):
    """``download`` converts first, so it keeps the one-pair precision its own path affords.
    If it ever stopped, this would still pass on the seam's wording — hence the negative arm."""
    from larkdocio.common.auth import WRITE_ENV, resolved_read_env

    _patch_env(monkeypatch)

    class _BadSecret:
        def get_docx_content(self, doc_token):
            raise _rejected_token()

    monkeypatch.setattr(download, "Client", lambda *a, **k: _BadSecret())
    result = _invoke(["download", DOCX_URL, "-o", str(tmp_path)])

    folded = " ".join(result.output.split())
    assert "Traceback" not in result.output
    for var in resolved_read_env():
        assert var in folded
    assert WRITE_ENV[0] not in folded, (
        "download fell through to the seam's both-pairs wording; its own arm knows better")


def test_the_credential_guidance_names_the_ENV_FILE_THAT_WAS_READ_not_the_default(
        monkeypatch, tmp_path):
    """**LD-658 fix round, defect 1.** ``_report_error`` called the guidance builder with **no**
    ``env_file``, so it fell back to ``os.path.abspath('.env')`` unconditionally. Executed with
    ``--env-file /somewhere/else.env``, the refusal told the user to edit ``./.env`` — a file that
    is not the one that was read. Follow that advice and you edit the wrong file and the error
    persists: **advice that cannot be followed**, which is the defect class this whole issue
    exists to remove, shipped by the issue itself.
    """
    elsewhere = tmp_path / "somewhere.env"
    elsewhere.write_text("LARK_READ_APP_ID=x\nLARK_READ_APP_SECRET=y\n", encoding="utf-8")
    _patch_env(monkeypatch)

    class _BadSecret:
        def get_docx_content(self, doc_token):
            raise _rejected_token()

    monkeypatch.setattr(download, "Client", lambda *a, **k: _BadSecret())
    result = _invoke(["--env-file", str(elsewhere), "download", DOCX_URL, "-o", str(tmp_path)])

    folded = " ".join(result.output.split())
    assert str(elsewhere) in folded, (
        f"the guidance does not name the .env that was actually read ({elsewhere}):\n"
        f"{result.output}")
    assert "or the file you passed to --env-file" not in folded, (
        "it still hedges about --env-file while holding the answer")


def test_the_guidance_falls_back_to_the_env_INIT_ENV_ITSELF_would_resolve(monkeypatch, tmp_path):
    """The no-``--env-file`` case must stay right, and it is right for a checkable reason rather
    than a coincidence: ``init_env``'s own no-argument resolution IS ``<cwd>/.env`` (its
    docstring), which is exactly what ``os.path.abspath('.env')`` yields. Asserted against the
    resolver rather than against a retyped path."""
    import os

    from larkdocio.common.auth import token_mint_refusal_lines

    lines = token_mint_refusal_lines((("A", "B"),), None)
    assert os.path.abspath(".env") in lines[2]
    # ...and the hedge is present precisely when we do NOT know, and only then.
    assert "or the file you passed to --env-file" in lines[2]
    known = token_mint_refusal_lines((("A", "B"),), str(tmp_path / "x.env"))
    assert "or the file you passed to --env-file" not in known[2]


def test_EVERY_verb_names_ITSELF_in_the_credential_refusal_not_download(caplog):
    """**LD-658 fix round, defect 2.** The refusal was the literal ``"Download failed: …"``,
    written when only ``download`` had this arm. Once the seam carried it for every verb,
    ``roundtrip pull`` printed ``Error: Download failed: …`` — the ruling asked for coverage and
    got a refusal that misnames the command the user typed.

    Walked over the real group, and the subject comes from what **click parsed**, so a future
    subcommand is named correctly without an entry anywhere.
    """
    for name, command in sorted(cli.commands.items()):
        def _raise(*args, **kwargs):
            raise _rejected_token()

        ctx = click.Context(command, info_name=name, parent=click.Context(cli))
        ctx.obj = {}
        original = command.callback
        command.callback = _raise
        try:
            with pytest.raises(click.ClickException) as caught:
                command.invoke(ctx)
        finally:
            command.callback = original

        message = str(caught.value)
        assert name in message, f"{name}'s refusal does not name {name}: {message!r}"
        if name != "download":
            assert "Download failed" not in message, (
                f"`{name}` still calls itself a download: {message!r}")


def test_the_DOWNLOAD_arms_refusal_bytes_are_UNCHANGED_by_the_parameterisation(monkeypatch,
                                                                               tmp_path):
    """``download`` keeps ``"Download failed: …"`` — the spelling every other refusal on that
    path already uses. Parameterising the subject must not have moved a consumer-facing line."""
    from larkdocio.common.auth import token_mint_refusal

    assert token_mint_refusal("Download") == (
        "Download failed: the app credentials were rejected — see the guidance above.")

    _patch_env(monkeypatch)

    class _BadSecret:
        def get_docx_content(self, doc_token):
            raise _rejected_token()

    monkeypatch.setattr(download, "Client", lambda *a, **k: _BadSecret())
    result = _invoke(["download", DOCX_URL, "-o", str(tmp_path)])
    assert token_mint_refusal("Download") in " ".join(result.output.split())


def test_report_error_survives_being_called_OUTSIDE_an_except_block():
    """The cheap one. Path 0 used a bare ``raise``, which needs an ACTIVE exception — so calling
    ``_report_error`` outside an ``except`` replaced the caller's error with
    ``RuntimeError: No active exception to reraise`` and lost the original. Latent (the one
    production call site is inside an ``except``), and ``raise e`` removes the trap for free."""
    original = ValueError("not a recognised Lark URL: 'nope'")
    with pytest.raises(ValueError) as caught:
        download._report_error(original)
    assert caught.value is original, "the original exception was replaced, not re-raised"


# --------------------------------------------------------------------------- #
# LD-658 third round — the token-mint COVERAGE claim, asked of the REAL mint. #
# --------------------------------------------------------------------------- #

#: **There are TWO token-mint paths in this library, and that is the whole finding.**
#:
#: * ``read/client.py`` builds an ``lark_oapi`` client, so the SDK mints and a rejected app pair
#:   arrives as ``lark_oapi``'s own ``ObtainAccessTokenException`` — the class the CLI seam and
#:   the reader's own arm catch.
#: * ``common/transport.fetch_tenant_access_token`` mints by raw HTTP and raises this library's
#:   ``LarkAPIError`` (``common/transport.py``'s token branch) instead. ``drive/client.py``,
#:   ``write/client.py``, ``sheets/*`` and ``preflight.py`` all use it.
#:
#: They share the **seam**; they do not share the **exception class**. So covering "every verb"
#: by catching one class was never possible: **LD-672** gave the seam a second arm, keyed on the
#: token mint's own stamp plus Lark's code rather than on a class, and both rows are now covered.
#:
#: Each row is ``(verb, argv, which mint to break, covered?)``. The mint is broken at its **own**
#: seam, one layer below the code under test, so the client, the command and the CLI boundary all
#: run for real — which is exactly what the injection test above cannot do, and why that one was
#: renamed.
_TOKEN_PATH_ROWS = [
    ("download", ["download", DOCX_URL], "sdk", True),
    ("folder", ["folder", "https://example.larksuite.com/drive/folder/fldrTOKEN"],
     "transport", True),
]


def _break_the_sdk_mint(monkeypatch):
    """Make the ``lark_oapi`` client's token mint fail the way a wrong App Secret does."""
    class _BadSecret:
        def get_docx_content(self, doc_token):
            raise _rejected_token()

    monkeypatch.setattr(download, "Client", lambda *a, **k: _BadSecret())


def _break_the_transport_mint(monkeypatch):
    """Let the REAL ``fetch_tenant_access_token`` run and answer it with Lark's rejection body.

    **This function used to inject.** It monkeypatched ``drive.client``'s *module attribute*
    with a fake that raised a hand-built ``LarkAPIError`` — and ``DriveClient.__init__`` binds
    ``token_fetcher=fetch_tenant_access_token`` as an **import-time default**, so the fake was
    never called and the real mint dialled out to Lark's ``tenant_access_token`` endpoint on
    every suite run since this row landed (measured: two connect attempts to ``101.100.179.x``
    with the socket layer instrumented). It also happened to pass, because the real rejection's
    text and the fake's were the same sentence — an instrument whose failure mode looks like a
    clean result.

    So the mint is now broken where it really is breakable: every one of the package's
    import-time-bound ``urlopen`` defaults **and** the socket layer, derived by a walk rather
    than named (``token_mint_probe.inject_rejecting_urlopen``), with the no-call-left assertion
    the caller runs.
    """
    probe.inject_rejecting_urlopen(monkeypatch)


@pytest.mark.parametrize("verb, argv, path, covered",
                         _TOKEN_PATH_ROWS, ids=[r[0] for r in _TOKEN_PATH_ROWS])
def test_the_token_mint_COVERAGE_is_per_TOKEN_PATH_and_the_gap_is_pinned(
        monkeypatch, tmp_path, verb, argv, path, covered):
    """**LD-658 third round, closed by LD-672.** The consumer-facing claim was *"``download``,
    ``folder`` and ``roundtrip`` all answer this the same way"*. Executed at LD-658: ``folder``
    on a rejected app pair printed **zero bytes** and escaped an uncaught ``LarkAPIError`` — the
    bare traceback the notes said was gone. The claim was narrowed to what was true and this
    test held it, one row per token path, against the real mint rather than an injected
    exception; **LD-672 covered the second path and the ``folder`` row flipped**, which is the
    tripwire firing as designed rather than a defect.

    **The behaviour it closed was PRE-EXISTING on ``develop``** — no release regressed. LD-658
    added the SDK arm and removed nothing; LD-672 added the raw-HTTP arm.

    **What each row does and does not isolate**, so nobody over-reads it: it asserts the
    user-visible OUTCOME (guidance reached the terminal), which on the SDK path can be delivered
    by either the reader's own arm or the CLI seam — disabling just one still passes, and that is
    correct, because a user does not care which arm answered. Red-watched with **both** disabled,
    which reddens (*"download is claimed as COVERED but printed no credential guidance"*). The
    per-arm precision questions are asked by their own tests above
    (``test_the_reader_keeps_the_NARROWER_answer_and_never_reaches_the_seam``).
    """
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: ("id", "secret"))
    monkeypatch.setenv("LARK_READ_APP_ID", "cli_bogus")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "wrongsecret")
    from larkdocio.drive import folder_cmd

    monkeypatch.setattr(folder_cmd, "init_env", lambda *a, **k: None)

    if path == "sdk":
        _break_the_sdk_mint(monkeypatch)
    else:
        _break_the_transport_mint(monkeypatch)

    result = _invoke(argv + ["-o", str(tmp_path)], catch_exceptions=True)
    folded = " ".join(result.output.split())

    assert result.exit_code != 0, f"{verb} did not fail on a rejected app pair"
    if covered:
        assert "CREDENTIAL problem" in folded, (
            f"{verb} is claimed as COVERED but printed no credential guidance:\n{result.output}")
        assert "Traceback" not in result.output
        assert BUG_BANNER not in folded, (
            f"{verb} still presents a rejected app pair as a possible bug in this library")
    else:
        assert "CREDENTIAL problem" not in folded, (
            f"{verb} now DOES answer a rejected app pair with the credential guidance — which "
            f"is good news and a red test on purpose: widen the coverage claim in cli.py and "
            f"the rule sentence in RELEASE_NOTES.md, and flip this row to covered.")
    if path == "transport":
        # The row that used to dial out. Whatever else this asserts, it asserts that offline.
        probe.assert_nothing_dialled_out()


def _edit_one_block(workdir):
    """Rewrite one plain-prose block of the pulled Markdown, through the SHIPPED projection.

    The block is derived from the artefact rather than named, the same discipline
    ``tests/test_roundtrip_verb.py`` uses: a fixture change then moves the target instead of
    silently making this arm test a push that refuses before it ever mints a token.
    """
    from larkdocio import roundtrip
    from larkdocio.model.projection import (
        block_markdown,
        project_block_ids,
        replace_block_markdown,
    )
    from larkdocio.snapshot import load

    projection = project_block_ids(load(str(roundtrip.snapshot_path(workdir))).tree)
    for block_id in projection.block_ids:
        try:
            body = block_markdown(projection, block_id)
        except ValueError:
            continue
        if body.strip() and not body.lstrip().startswith(("#", "|", "`", ">")):
            roundtrip.markdown_path(workdir).write_text(
                replace_block_markdown(projection, block_id, "an edit, so there is a plan"),
                encoding="utf-8")
            return block_id
    raise AssertionError("the fixture document has no plain prose block to edit")


def test_ROUNDTRIPS_TWO_PHASES_answer_a_rejected_PAIR_THE_SAME_WAY_and_name_DIFFERENT_pairs(
        monkeypatch, tmp_path):
    """**AC3 + AC4.** ``roundtrip`` was worse than a plain miss: its **pull** phase answered a
    rejected credential correctly and its **push** phase let a bare traceback out, so one
    command reported one underlying failure two ways depending on how far it got. Both phases
    are driven here through their real transports — pull on the SDK mint, push on the raw-HTTP
    mint — in the same working directory, off a snapshot pair the shipped ``pull`` wrote.

    And they must **not** say the same thing in one respect: the pair. Push resolves
    ``LARK_WRITE_APP_*`` and pull the read pair, so a push failure that named the read pair
    would be advice that cannot be followed — the defect class LD-658 fixed once for ``.env``
    paths, which AC4 forbids reintroducing for pair names.
    """
    import offline_doubles
    from larkdocio import roundtrip
    from larkdocio.common.auth import WRITE_ENV, resolved_read_env

    # A real snapshot pair, written by the SHIPPED pull against the offline doubles — `push`
    # reads from the files alone, so this is the artefact it needs and not a doctored one.
    offline_doubles.stage(monkeypatch, tmp_path)
    workdir = tmp_path / "edit"
    reader = offline_doubles.OfflineDocxReadClient(
        "cli_read_offline", "read-secret-offline", "larksuite.com")
    pulled = roundtrip.pull(
        "https://your-domain.larksuite.com/docx/OfflineDocToken", workdir, reader=reader)
    assert pathlib.Path(pulled.snapshot_path).exists()
    assert pathlib.Path(pulled.markdown_path).exists()
    # ...and ONE edited block, because a push with nothing to apply refuses at the reconciler
    # and never reaches a token at all — the shape that would make this arm vacuous.
    _edit_one_block(workdir)
    monkeypatch.undo()

    # Both mints broken at once, no injection anywhere: the two phases build their own real
    # clients out of this .env and each reaches its own handshake.
    env_file = tmp_path / "credentials.env"
    env_file.write_text(
        "LARK_READ_APP_ID=cli_garbage\nLARK_READ_APP_SECRET=garbage\n"
        "LARK_WRITE_APP_ID=cli_garbage_write\nLARK_WRITE_APP_SECRET=garbage\n",
        encoding="utf-8")
    probe.break_the_sdk_mint(monkeypatch)
    _break_the_transport_mint(monkeypatch)

    pull_result = _invoke(["--env-file", str(env_file), "roundtrip", "pull", DOCX_URL,
                           "-o", str(workdir)], catch_exceptions=True)
    # ``--apply`` because a bare `push` is a rehearsal that reaches no API at all: the plan is
    # built from the snapshot and the edited file, so the handshake this issue is about is the
    # one the APPLY needs. Nothing is written — the credentials are refused first.
    push_result = _invoke(["--env-file", str(env_file), "roundtrip", "push",
                           "-o", str(workdir), "--apply"], catch_exceptions=True)
    pull_folded = " ".join(pull_result.output.split())
    push_folded = " ".join(push_result.output.split())

    for phase, folded, result in (("pull", pull_folded, pull_result),
                                  ("push", push_folded, push_result)):
        assert result.exit_code != 0, f"roundtrip {phase} did not fail on a rejected pair"
        assert "CREDENTIAL problem" in folded, (
            f"roundtrip {phase} did not report a rejected app pair as a credential problem:\n"
            f"{result.output}")
        assert "Traceback" not in result.output, f"roundtrip {phase} printed a traceback"
        assert BUG_BANNER not in folded, f"roundtrip {phase} blamed this library"
        # The verb, not the phase: the phase is a positional ARGUMENT of one command, and the
        # subject comes from what click parsed (LD-658), so both phases name `roundtrip`.
        assert "`larkdocio roundtrip` failed" in folded, (
            f"the refusal does not name the verb the user typed: {folded[-200:]!r}")

    # ...and the pair each phase names is what that phase can honestly say.
    #
    # **push knows and says the ONE pair**: it minted through the raw-HTTP handshake, whose
    # error carries the client's own declared pair. Naming the read pair here would be advice
    # that cannot be followed.
    assert WRITE_ENV[0] in push_folded and WRITE_ENV[1] in push_folded, (
        "push does not name the WRITE pair it actually used")
    assert "LARK_READ_APP_ID" not in push_folded and "LARK_APP_ID" not in push_folded, (
        "push names a READ variable for a failure on the write pair — the 'names the wrong "
        "file' defect, reintroduced for pair names")
    assert "does not say WHICH app" not in push_folded, "push hedged on a pair it knows"
    #
    # **pull says both and says so**: it minted through the SDK, whose exception carries no app
    # id at all, and this seam is reached by verbs that write as well as read. The hedge is the
    # honest answer there, not a lapse — LD-658's own ruling.
    for name in resolved_read_env():
        assert name in pull_folded, f"pull does not name {name}"
    assert "does not say WHICH app" in pull_folded
    probe.assert_nothing_dialled_out()


def test_the_two_token_paths_are_REAL_and_named_from_the_TREE_not_from_this_file():
    """The premise of the table above, derived: two distinct mint sites exist, they raise
    different classes, and the modules on each side are read off the source rather than listed
    in prose. If the tree ever collapses them into one, this reddens and the table is obsolete.
    """
    import pathlib

    from larkdocio.common import transport
    from larkdocio.read import client as read_client

    root = pathlib.Path(read_client.__file__).resolve().parents[1]

    # Path A — the SDK mints; the reader builds an lark_oapi client and never calls the raw one.
    reader_src = pathlib.Path(read_client.__file__).read_text(encoding="utf-8")
    assert "fetch_tenant_access_token" not in reader_src, (
        "the reader now mints through the raw transport too — the two paths have merged and "
        "the coverage table above is obsolete")

    # Path B — the raw transport mints, and raises THIS library's class, not the SDK's.
    transport_src = pathlib.Path(transport.__file__).read_text(encoding="utf-8")
    assert "tenant_access_token error" in transport_src
    assert "ObtainAccessTokenException" not in transport_src, (
        "the raw transport now raises the SDK's class, so the seam would cover it — widen the "
        "narrowed claims and update the table")

    # ...and the modules that ride path B, derived by a walk rather than named in prose.
    riders = sorted(
        str(py.relative_to(root))
        for py in root.rglob("*.py")
        if py.name != "transport.py"
        and "fetch_tenant_access_token" in py.read_text(encoding="utf-8"))
    assert riders, "nothing uses the raw token mint — the table's second row has no subject"
    assert any("drive/" in r for r in riders), (
        f"drive no longer rides the raw mint; the `folder` row above is stale: {riders}")
    assert any("write/" in r for r in riders), (
        f"write no longer rides the raw mint; roundtrip push's exclusion is stale: {riders}")


# --------------------------------------------------------------------------- #
# LD-658 fourth round — the coverage claim is DERIVED, not typed.             #
# --------------------------------------------------------------------------- #

def test_the_DOCUMENTED_coverage_equals_the_MEASURED_coverage(monkeypatch):
    """**LD-658 fourth round. This test exists because the sentence it guards was hand-typed
    three times and wrong three times.**

    Round 2 claimed all three verbs were covered — too wide. Round 3 narrowed it and excluded
    **Base** — too narrow, and inconsistent with the ``CHANGELOG``. Each was falsified by
    execution and none was caught by review, so the claim is no longer maintained by hand: the
    two lists in ``cli._RefusalUniformCommand``'s docstring are held **set-equal** to a probe
    that runs every surface's real client against both mint paths broken at their own seams
    (``tests/token_mint_probe.py``).

    **Set equality, so it cannot drift in either direction** — a surface that stops being
    covered and a surface that starts being covered both redden here. That subsumes the LD-672
    tripwire: when the raw-HTTP path is fixed, ``drive``/``write``/``sheets`` move to the
    measured-covered set and this fails until the claim is corrected.
    """
    import inspect

    import token_mint_probe as probe

    measured = probe.measure(monkeypatch)
    assert set(measured) == set(probe.PROBE_SUBJECTS), "the probe skipped a subject"

    doc = inspect.getdoc(cli_mod._RefusalUniformCommand)
    documented_covered = probe.documented_labels(doc, "Covered: ")
    documented_uncovered = probe.documented_labels(doc, "Not covered: ")

    measured_covered = {f for f, ok in measured.items() if ok}
    measured_uncovered = {f for f, ok in measured.items() if not ok}

    assert documented_covered == measured_covered, (
        f"cli.py's COVERED list is {sorted(documented_covered)} and the probe measures "
        f"{sorted(measured_covered)}. Do not edit the list to a belief — this is measured by "
        f"running each surface's real client. If the difference is `drive`/`write`/`sheets` "
        f"moving to covered, LD-672 has landed: correct this claim and the RULE sentence in "
        f"RELEASE_NOTES.md in the same change.")
    assert documented_uncovered == measured_uncovered, (
        f"cli.py's NOT-COVERED list is {sorted(documented_uncovered)} and the probe measures "
        f"{sorted(measured_uncovered)}")
    # ...and the two lists must partition the population, so a surface cannot be omitted from
    # both and go unclaimed.
    assert documented_covered | documented_uncovered == set(probe.PROBE_SUBJECTS)
    assert not (documented_covered & documented_uncovered)


def _sdk_client_builders():
    """The names in ``common/sdk_client`` that CONSTRUCT an SDK client — by property.

    **AC0(b). This used to be the literal set ``{fetch_tenant_access_token,
    resolve_sdk_client}``, and that list could not see ``read``** — the docx reader builds
    through :func:`build_sdk_client`, deliberately (it has no injectable-client seam and no
    rate limiter, which is what ``resolve_sdk_client`` is for). The population happened to be
    right anyway, because ``read`` also has a probe subject; what was wrong was the
    DERIVATION, which is the half that has to keep being right about a family nobody has
    written yet. A THIRD helper would have gone silently unmeasured.

    So the builders are derived: start from the one place ``lark.Client`` is constructed in this
    package, then close over the module's own callers of it. Two names satisfy that today and
    both are found; a helper added tomorrow that delegates to either is found without this
    function being edited.
    """
    import inspect

    from larkdocio.common import sdk_client

    functions = {name: inspect.getsource(value)
                 for name, value in vars(sdk_client).items()
                 if inspect.isfunction(value) and value.__module__ == sdk_client.__name__}
    builders = {name for name, source in functions.items() if "lark.Client" in source}
    assert builders, ("no function in common/sdk_client constructs a lark.Client — the SDK half "
                      "of this derivation would be empty")
    while True:
        widened = builders | {name for name, source in functions.items()
                              if any(f"{builder}(" in source for builder in builders)}
        if widened == builders:
            return builders
        builders = widened


def test_the_probe_POPULATION_is_complete_against_the_tree(monkeypatch):
    """A probe that measures four of seven families would let the claim be right about the four
    and silent about the rest. The population is held against the modules that actually mint:
    every package under ``src/larkdocio`` reaching either mint seam must have a probe subject —
    and the seams are found **by property** (:func:`_sdk_client_builders`), not by a list of
    names the next family may not use.
    """
    import pathlib

    import token_mint_probe as probe
    from larkdocio import cli as _cli

    seams = {"fetch_tenant_access_token"} | _sdk_client_builders()
    assert "build_sdk_client" in seams and "resolve_sdk_client" in seams, (
        f"the derivation lost an SDK-client builder it used to find: {sorted(seams)}")

    root = pathlib.Path(_cli.__file__).resolve().parent
    minting = set()
    for py in sorted(root.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        rel = py.relative_to(root)
        family = rel.parts[0] if len(rel.parts) > 1 else None
        if family in (None, "common"):
            continue
        if any(f"{seam}(" in text for seam in seams):
            minting.add(family)

    assert minting, "no package reaches a mint seam — this guard would be vacuous"
    assert "read" in minting, (
        "the derivation does not see `read`, which mints through build_sdk_client — that is "
        "exactly the blind spot AC0(b) exists to close, and it means a future family built "
        "through a third helper would go unmeasured too")
    unmeasured = sorted(minting - set(probe.PROBE_SUBJECTS))
    assert not unmeasured, (
        f"these packages mint a tenant token and have no probe subject: {unmeasured}. Add one "
        f"to tests/token_mint_probe.py, because until you do the shipped coverage claim says "
        f"nothing about them.")


def test_the_verb_mapping_names_only_REAL_click_verbs():
    """The probe's family→verb map is the consumer vocabulary; it must not name a verb click
    does not have (which is how prose about `roundtrip` phases stays checkable)."""
    import token_mint_probe as probe

    verbs = {v.split()[0] for names in probe.VERBS_BY_FAMILY.values() for v in names}
    assert verbs, "the mapping names no verb"
    unknown = sorted(v for v in verbs if v not in cli.commands)
    assert not unknown, f"the map names verbs the CLI does not have: {unknown}"
    assert set(probe.VERBS_BY_FAMILY) == set(probe.PROBE_SUBJECTS), (
        "the verb map and the probe population have drifted apart")


def test_EVERY_verb_the_MAP_names_rides_a_family_the_probe_measures_as_COVERED(monkeypatch):
    """**AC5's half of the claim that is about VERBS, derived rather than retyped.**

    The consumer-facing sentence has been wrong in both directions (*"all three verbs"*, then a
    narrowing that outlived its own truth), so no document enumerates verbs any more: the notes
    state the rule, ``cli.py`` names families and is held set-equal to the probe, and the
    verb→family routing is checked against the real click group. This arm closes the last hop —
    that every verb the routing names rides a family the probe MEASURES as covered, so
    *"on every command"* is a derived statement and not a typed one.
    """
    import token_mint_probe as probe

    measured = probe.measure(monkeypatch)
    uncovered = sorted(family for family, ok in measured.items() if not ok)
    assert not uncovered, (
        f"these families do not answer a rejected app pair: {uncovered} — the rule sentence in "
        f"RELEASE_NOTES.md ('both of the ways larkdocio mints a tenant token') is then too wide "
        f"and must be narrowed in the same change that narrows the behaviour")

    routed = {verb: family for family, verbs in probe.VERBS_BY_FAMILY.items() for verb in verbs}
    assert routed, "the verb routing is empty — this arm would be vacuous"
    for verb, family in sorted(routed.items()):
        assert measured[family], f"`larkdocio {verb}` rides {family!r}, which is not covered"
    # ...and the routing covers every verb that reaches a document at all: the three it does not
    # name are the three that make no API call (checked here, so the omission stays deliberate).
    assert set(cli.commands) - {verb.split()[0] for verb in routed} == {
        "config", "guide", "mermaid"}, (
        "a click verb is neither routed to a token-minting family nor one of the three that "
        "reach no API — decide which it is rather than leaving it unclaimed")


def test_the_RELEASE_NOTES_state_the_RULE_and_name_NO_surface():
    """**The deliberate asymmetry, and the reason for it.**

    ``cli.py``'s claim is a *live* docstring: it can be corrected the day the measured set
    changes, so it names surfaces and a probe holds it honest. A dated ``RELEASE_NOTES``
    section is the opposite — it **freezes at the cut** and is never edited again (this repo's
    own rule, and the premise of ``LIVE_NOTES_ALLOWANCE``). Holding a frozen historical document
    set-equal to a live probe would demand editing history the day the measured set changes, so
    the notes state the **RULE** — which cannot go stale per-surface — and point at the live
    claim. LD-672 is that day, and the asymmetry paid for itself: the rule sentence was
    rewritten in the LANDING section (one mint path → both) while no per-surface list had to be,
    because there was none to fix.

    **And the section this reads is DERIVED, which is the repair LD-672 owed** — see
    :func:`_the_landing_section`. It was hard-coded to ``## [1.51.0]``, which was the landing
    zone when LD-658 wrote it and became **released history** when v1.51.0 was cut. A guard
    pointed at history is satisfied by editing history: LD-672's first round put its notes into
    the 1.51.0 section and rewrote a paragraph describing a wheel already in consumers' hands,
    and this guard was green throughout. A guard's scope has to match its subject's mutability.

    This arm is what stops a fourth hand-typed list reappearing there.
    """
    import pathlib
    import re

    import consumer_text

    root = pathlib.Path(__file__).resolve().parents[1]
    raw = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    # the RULE is stated... SOMEWHERE IN THE NOTES, which is the LD-674 correction. It was
    # read out of the LANDING section, and that held only while the release carrying it was
    # still un-cut: v1.52.0 froze the sentence and the next un-cut section — which says nothing
    # about credentials, because nothing about credentials changed — left this arm asserting
    # over a section that never claimed coverage at all. The property worth guarding is that the
    # notes STATE THE RULE and that no claim paragraph anywhere hand-types a surface list; both
    # are now checked where the claim actually is.
    flattened = " ".join(raw.split())
    assert _COVERAGE_RULE in flattened, (
        "the notes must state the RULE (which mint paths are covered), not a surface list")
    # ...and no surface family is named as covered/uncovered IN THE CLAIM'S OWN PARAGRAPHS.
    #
    # **Scoped to the claim, not to the section** (LD-659). The subject of this arm is the
    # coverage claim — its own message says so — and the check was a ban on the WORD across the
    # whole un-cut section, which is a different and much wider rule: a landing section
    # accumulates every issue in the release, and the next one to describe a Base read at all
    # reddened this. It is not hypothetical: LD-659's date-zone disclosure note did, and the
    # word it used ("A Base date read on a machine with no tz database…") makes no claim about
    # which surfaces the credential guidance covers. Narrowed to the paragraphs that carry the
    # rule sentence, which is where a fourth hand-typed list would have to appear; both
    # directions are pinned by the arm below, so the narrowing cannot have narrowed it to
    # nothing.
    claim = _the_coverage_claim_paragraphs(raw)
    assert claim, "the coverage claim's paragraph is not findable — this arm would be vacuous"
    for family in ("base", "sheets", "drive", "bitable"):
        assert not re.search(rf"\b{family}\b", claim, re.IGNORECASE), (
            f"the notes name {family!r} in a coverage claim again. That list has been hand-typed "
            f"three times and wrong three times; state the rule and let cli.py's probe-checked "
            f"claim carry the surfaces.")

    # and the packaged copy says the same thing (the guard reads both).
    packaged = " ".join(
        consumer_text.shipped_docs()["release_notes() (the packaged RELEASE_NOTES.md)"].split())
    assert _COVERAGE_RULE in packaged, (
        "the packaged copy does not carry the rule — run scripts/sync-packaged-notes.sh")


#: The sentence that IS the rule. The claim's paragraphs are the ones carrying it.
#:
#: It changed at LD-672 — *"minted through the Lark SDK"* was the one-path rule, and the rule is
#: now both paths. The phrase is a constant here for the reason the whole arm exists: it is the
#: hook two checks and one both-ways poison test share, and a retyped hook is a fourth place to
#: be wrong.
_COVERAGE_RULE = "both of the ways larkdocio mints a tenant token"


def _the_coverage_claim_paragraphs(text):
    """Every blank-line-separated block of the notes that carries :data:`_COVERAGE_RULE`.

    Blocks rather than whole sections, and blocks rather than one sentence: the claim is
    written as a bullet with continuation lines, and a hand-typed surface list would land inside
    that bullet — not three bullets away under a different subject.

    **SCOPED TO THE CLAIM, NOT TO A SECTION (LD-674), and the reason the old scope existed is
    upheld.** This read the *landing* section, because LD-672's defect was a guard pointed at
    released history and satisfiable by editing it — that reason stands in full and nothing here
    weakens it. What is superseded is only the conclusion that the claim's paragraphs live in the
    landing section: the rule sentence was written into the section that became **1.52.0**, and
    the moment that release was cut and a new un-cut section opened, a landing-scoped read found
    **no claim at all** and the arm failed on a document nobody had broken. A claim-scoped read
    is strictly wider than either fixed section — it sweeps the frozen copy AND every future
    landing zone — so a fourth hand-typed surface list is caught wherever it is written, and no
    edit to history can satisfy it: removing the sentence from the cut section does not silence
    this function, it empties it, and the caller asserts the claim is non-empty.
    """
    lines = text.splitlines()
    blocks, current = [], []
    for line in lines:
        if line.strip():
            current.append(line)
        else:
            blocks.append(current)
            current = []
    blocks.append(current)
    flattened = [" ".join(" ".join(block).split()) for block in blocks]
    return " ".join(block for block in flattened if _COVERAGE_RULE in block)


def _first_line_of_the_claims_block(lines):
    """The index of the first line of the blank-line-separated block that carries the rule."""
    start = 0
    for index, line in enumerate(lines + [""]):
        if not line.strip():
            block = " ".join(" ".join(lines[start:index]).split())
            if _COVERAGE_RULE in block:
                return start
            start = index + 1
    raise AssertionError(f"no block of the notes carries {_COVERAGE_RULE!r}")


def test_the_narrowed_coverage_scope_bites_BOTH_ways():
    """The narrowing above, pinned in both directions on synthetic text — because a scope that
    was narrowed to nothing is the failure mode a green test cannot distinguish from a fix."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    raw = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    claim = _the_coverage_claim_paragraphs(raw)
    assert _COVERAGE_RULE in claim

    # (a) a surface named INSIDE the claim's own paragraph is still caught. Injected by LINE,
    # because the rule sentence is hard-wrapped in the document and a substring replace on the
    # flattened phrase would match nothing — a synthetic that fails to poison anything is a
    # green assertion about nothing.
    #
    # The line is found by locating the claim's own BLOCK rather than by searching for a
    # fragment of the rule: the rule phrase is a constant, it wraps, and which words land on
    # which line is a formatting accident nothing should depend on. (It did until LD-672
    # reworded the rule, at which point the old line search raised StopIteration.)
    lines = raw.splitlines()
    hit = _first_line_of_the_claims_block(lines)
    poisoned = "\n".join(lines[:hit + 1] + ["  (base, sheets and drive)"] + lines[hit + 1:])
    assert re.search(r"\bbase\b", _the_coverage_claim_paragraphs(poisoned), re.IGNORECASE)

    # (b) a surface named in a DIFFERENT bullet of the same section is not.
    lines = raw.splitlines()
    at, _end = _landing_section_bounds(lines)
    elsewhere = "\n".join(
        lines[:at + 2] + ["- A Base date now discloses its zone.", ""] + lines[at + 2:])
    assert _COVERAGE_RULE in _the_coverage_claim_paragraphs(elsewhere)
    assert not re.search(r"\bbase\b", _the_coverage_claim_paragraphs(elsewhere), re.IGNORECASE)


#: A dated version heading — ``## [1.52.0] — 2026-09-09``. The same shape
#: ``tests/test_download_route_contract_pins.py`` derives its own three buckets from, and for
#: the same stated reason: *"the topmost dated section is not history: it is the un-cut landing
#: zone"*.
_VERSION_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")


def _landing_section_bounds(lines):
    """``(first, last)`` line indices of the TOPMOST dated version section.

    **Derived from the headings, never named.** This is the repair LD-672 owed: the predecessor
    of this function hard-coded ``## [1.51.0]`` while calling itself *"the un-cut landing
    section"*, so the moment v1.51.0 was cut the guard was pointing at **released history** —
    and the cheapest way to satisfy it became rewriting a paragraph that describes a shipped
    wheel, which is exactly what happened. Cutting a release now moves what this points at, for
    free, and a hard-coded version cannot satisfy it (red-watched both ways in
    ``test_the_landing_section_FOLLOWS_the_cut_and_a_hard_coded_version_cannot_satisfy_it``).
    """
    headings = [i for i, line in enumerate(lines) if _VERSION_HEADING.match(line)]
    assert headings, "the notes carry no dated version heading"
    top = headings[0]
    end = headings[1] if len(headings) > 1 else len(lines)
    return top, end


def _the_landing_section(text):
    """The un-cut landing section — topmost dated heading to the next one, flattened."""
    lines = text.splitlines()
    top, end = _landing_section_bounds(lines)
    return " ".join(" ".join(lines[top:end]).split())


def test_the_landing_section_FOLLOWS_the_cut_and_a_hard_coded_version_cannot_satisfy_it():
    """**The anti-recurrence arm for LD-672's own defect, in both directions.**

    The rule broken was this tranche's own: *a guard's scope has to match its subject's
    mutability*. ``_the_1_51_0_section`` named a version, so on the day v1.51.0 was cut it
    began pointing at **released bytes** while still calling itself the landing zone — and the
    cheapest way to keep it green became rewriting a paragraph that describes a wheel in
    consumers' hands. Three arms, because a derivation that is right today is not the property
    worth guarding; *following the cut* is.
    """
    import ast
    import inspect
    import pathlib
    import textwrap

    root = pathlib.Path(__file__).resolve().parents[1]
    raw = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    # (a) A CUT moves what the derivation points at — simulated by opening a new topmost
    # section, which is exactly what `scripts/release.sh` + the cutter do.
    cut = "\n".join(["## [9.9.9] — 2026-09-09", "", "### What a caller can observe", "",
                      f"- **A synthetic landing bullet.** {_COVERAGE_RULE}.", ""]) + raw
    lines = cut.splitlines()
    top, end = _landing_section_bounds(lines)
    assert lines[top].startswith("## [9.9.9]"), (
        "the derivation did not follow the cut — it is anchored to something other than the "
        "topmost dated heading")
    assert "A synthetic landing bullet" in _the_landing_section(cut)
    assert "Nothing else" not in _the_landing_section(cut), (
        "the previous landing section is still being read as live after a cut")

    # (b) ...and the section it reads TODAY is not the released one. This is the failure that
    # actually happened: 1.51.0's own rule sentence is history and must be outside the guard's
    # reach, or editing it stays a way to satisfy this file.
    landing = _the_landing_section(raw)
    assert "you do not get it where the token is minted over plain HTTP" not in landing, (
        "the guard is reading a RELEASED section — the sentence it just matched describes a "
        "shipped wheel, and this file must not be satisfiable by editing it")

    # (c) A hard-coded version cannot satisfy any of the four derivations, ever again — checked
    # against their own source, so re-typing one reddens here rather than in two releases.
    for derivation in (_landing_section_bounds, _the_landing_section,
                       _the_coverage_claim_paragraphs, _first_line_of_the_claims_block):
        # The CODE, with the docstring dropped — scoped to its subject in both directions.
        # These docstrings QUOTE the hard-coded heading they exist to warn about, and a
        # guard that fires on the prose explaining what it forbids is the other half of the
        # same mistake.
        tree = ast.parse(textwrap.dedent(inspect.getsource(derivation)))
        body = tree.body[0].body
        if (isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]
        code = "\n".join(ast.unparse(node) for node in body)
        assert not re.search(r"## \\?\[?\d+\.\d+\.\d+", code), (
            f"{derivation.__name__} names a version heading literally. That is the LD-672 "
            f"defect: it is correct until the next cut and then silently points at history.")
        assert code, f"{derivation.__name__} has no body — this arm would be vacuous"
