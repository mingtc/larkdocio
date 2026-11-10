"""LD-658 AC5 — the documentary commands stop writing zero bytes on a legacy code page.

Nothing in the package set an output encoding (`grep reconfigure src/` → 0 matches), so Python
used the locale's. On Windows a **redirected** stdout gets the active code page, and every
documentary surface this CLI has carries characters a legacy code page cannot encode. Executed
at the pin, across four code pages: `larkdocio guide` → exit **1**, **0 bytes written**,
`UnicodeEncodeError` on cp1252, cp936, cp932 and cp437; the root `--help` failed on cp932 and
cp437. The `guide` command's own shipped help advertises the failing recipe.

**The reproduction here is real, not a mock, and it runs on any host**: a `TextIOWrapper` opened
on a `BytesIO` with `encoding="cp1252", errors="strict"` behaves exactly as a redirected Windows
stdout does — same encoder, same exception. So the red-watch is a genuine failure of the shipped
text, not an assertion about a call.
"""
import io
import sys

import pytest
from click.testing import CliRunner

from larkdocio import cli as cli_mod
from larkdocio.cli import cli
from larkdocio.guide import guide as packaged_guide

#: The four code pages the finding was executed against.
CODE_PAGES = ["cp1252", "cp936", "cp932", "cp437"]


def _redirected_stdout(code_page):
    """A stdout that behaves like Windows' redirected one on ``code_page``."""
    buf = io.BytesIO()
    return io.TextIOWrapper(buf, encoding=code_page, errors="strict", newline=""), buf


@pytest.mark.parametrize("code_page", CODE_PAGES)
def test_the_shipped_guide_CANNOT_be_written_on_a_legacy_code_page_unconfigured(code_page):
    """The red-watch, kept as a permanent statement of WHY the fix exists.

    This is the pre-fix behaviour, asserted directly on the shipped text rather than on the
    command: without a reconfigure, the guide's own bytes cannot be encoded at all. If this ever
    stops failing, the fix below has stopped being necessary and this file should say so.
    """
    stream, _buf = _redirected_stdout(code_page)
    with pytest.raises(UnicodeEncodeError):
        stream.write(packaged_guide())
        stream.flush()


@pytest.mark.parametrize("code_page", CODE_PAGES)
def test_the_reconfigure_lets_the_SHIPPED_GUIDE_reach_a_legacy_code_page_stream(
        monkeypatch, code_page):
    """The fix, on the same stream that just failed: after the CLI's reconfigure, the guide's
    real bytes are written and the count is non-zero (the measured symptom was **0 bytes**)."""
    stream, buf = _redirected_stdout(code_page)
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)

    cli_mod._reconfigure_output_encoding()

    assert sys.stdout.encoding.lower().replace("-", "") == "utf8", sys.stdout.encoding
    assert sys.stdout.errors == "backslashreplace"

    text = packaged_guide()
    sys.stdout.write(text)
    sys.stdout.flush()
    written = buf.getvalue()
    assert len(written) > 0, "still zero bytes — the measured Windows symptom"
    assert written.decode("utf-8") == text, "the guide did not survive the round trip verbatim"


def test_the_reconfigure_leaves_a_NON_reconfigurable_stream_alone():
    """Best-effort, never a reason to fail before the command starts: a stream with no
    ``reconfigure`` (a ``StringIO``, or a stream someone already detached) must not raise."""
    class _Bare:
        encoding = "ascii"

        def write(self, _text):
            return 0

    import contextlib
    with contextlib.ExitStack() as stack:
        stack.enter_context(_swapped(sys, "stdout", _Bare()))
        stack.enter_context(_swapped(sys, "stderr", io.StringIO()))
        cli_mod._reconfigure_output_encoding()      # must not raise


import contextlib  # noqa: E402


@contextlib.contextmanager
def _swapped(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def test_the_group_reconfigures_BEFORE_click_parses_so_bare_help_is_covered(monkeypatch):
    """The root ``--help`` is one of the two measured-broken surfaces, and click answers it
    during parsing — before any group callback runs. So the call has to sit in ``main()``, and
    this pins that it does by invoking the surface that has no callback."""
    calls = []
    monkeypatch.setattr(cli_mod, "_reconfigure_output_encoding", lambda: calls.append(1))

    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert calls == [1], (
        "the reconfigure did not run for a bare --help, which is answered before any callback")


def test_EVERY_subcommands_help_is_reachable_on_a_legacy_code_page(monkeypatch):
    """Walked, not hand-named: the rendered ``--help`` of the group AND every subcommand is
    consumer-facing text (PROJECT.md § Quality bar), and each one is checked to survive the
    narrowest code page measured."""
    stream, buf = _redirected_stdout("cp437")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    cli_mod._reconfigure_output_encoding()

    import click

    names = sorted(cli.commands)
    assert names, "the group has no subcommands to walk"
    for name in [None] + names:
        command = cli if name is None else cli.commands[name]
        ctx = click.Context(command, info_name=name or "larkdocio")
        before = len(buf.getvalue())
        sys.stdout.write(command.get_help(ctx))
        sys.stdout.flush()
        assert len(buf.getvalue()) > before, f"{name or 'the group'} wrote zero bytes"
