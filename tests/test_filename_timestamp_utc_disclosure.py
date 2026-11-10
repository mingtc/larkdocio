"""LD-335 — the generated filename's ``[YYYY-MM-DD_HHMM]`` stamp is UTC, and the places an
operator actually looks now say so.

A **disclosure only**: the basis (``datetime.now(timezone.utc)``) and the rendered filename
shape are unchanged, and this module's first test is the fence that proves it. What changes is
text that DESCRIBES the behaviour — the ``download`` help page's epilog, and one additive
field on the ``--dump`` sidecar, because the consumer failure this answers was a *ledger*
timestamping its own ingestion off the filename, and a ledger reads JSON rather than help text.
"""

import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

from click.testing import CliRunner

from larkdocio.cli import cli
from larkdocio.read import download
from larkdocio.read.config import Config, OutputConfig


def _normalize(text: str) -> str:
    """Collapse all whitespace so assertions survive click's line-wrapping."""
    return " ".join(text.split())


# --------------------------------------------------------------------------- #
# AC1 — the fence: basis and rendered filename shape unchanged                 #
# --------------------------------------------------------------------------- #

def test_filename_shape_is_unchanged_by_the_disclosure(monkeypatch, tmp_path):
    """Both filename paths still render exactly what they rendered before: a UTC-derived
    ``[YYYY-MM-DD_HHMM]_<title>.md`` under ``title_as_filename``, and a stamp-free
    ``<token>.md`` with it off. **No offset, no ``Z``, no ``UTC`` suffix in the name.**

    LD-340 NARROWED this to the **default path** (``local_time`` absent): it remains the fence
    that the default basis is UTC and the shape unchanged. The flag-on path has its own sibling
    below (``test_local_time_stamps_in_the_machines_clock_same_shape``).
    """
    class _FrozenUTC(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc, "the stamp must be taken in UTC, not the local clock"
            return datetime(2026, 8, 8, 4, 5, tzinfo=timezone.utc)

    monkeypatch.setattr(download, "datetime", _FrozenUTC)

    on_dir = tmp_path / "on"
    on_dir.mkdir()
    download._write_markdown(Config(), str(on_dir), "TOK", "My Doc", "# body\n")
    names = [p.name for p in on_dir.iterdir()]
    assert names == ["[2026-08-08_0405]_My_Doc.md"], names

    off_dir = tmp_path / "off"
    off_dir.mkdir()
    download._write_markdown(
        Config(OutputConfig(title_as_filename=False)),
        str(off_dir), "TOK", "My Doc", "# body\n",
    )
    assert [p.name for p in off_dir.iterdir()] == ["TOK.md"]

    # The disclosure lives in prose and JSON, never in the name itself.
    for name in names:
        assert not re.search(r"(?i)utc|[+-]\d{4}|Z\.md$", name), name


def test_local_time_stamps_in_the_machines_clock_same_shape(monkeypatch, tmp_path):
    """LD-340 sibling for the flag-on path: with ``local_time=True`` the stamp is the local
    wall clock (``datetime.now()`` with no tz), the SHAPE is unchanged, and still no offset /
    ``Z`` / zone suffix leaks into the name — only the digits move."""
    class _FrozenLocal(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is None, "local-time path must read the local wall clock (no tz)"
            return datetime(2026, 8, 8, 12, 5)

    monkeypatch.setattr(download, "datetime", _FrozenLocal)
    download._write_markdown(Config(), str(tmp_path), "TOK", "My Doc", "# body\n", local_time=True)
    names = [p.name for p in tmp_path.iterdir()]
    assert names == ["[2026-08-08_1205]_My_Doc.md"], names
    assert not re.search(r"(?i)utc|[+-]\d{4}|Z\.md$", names[0]), names[0]


# --------------------------------------------------------------------------- #
# AC2 — the operator is told, where they look                                  #
# --------------------------------------------------------------------------- #

def test_download_help_says_the_stamp_is_UTC_and_why():
    """The help page carries the timezone fact **and** its reason in a few words — a consumer
    who knows the reason will not try to "fix" it — with the filename shape still unbroken.
    """
    result = CliRunner().invoke(cli, ["download", "--help"])
    assert result.exit_code == 0
    normalized = _normalize(result.output)

    assert "UTC" in normalized, "the help page never says the filename stamp is UTC"
    assert "local" in normalized.lower(), (
        "the help page says UTC but does not rule out the reader's local clock")
    # The reason, in the page's own words: one instant, one name, any machine.
    assert "same name" in normalized, (
        "the help page states the timezone but not why it is that way")
    # The no-rewrap block still delivers the shape whole.
    assert "[YYYY-MM-DD_HHMM]_<title>.md" in normalized


def test_download_epilog_stays_within_eighty_columns():
    """The epilog's no-rewrap (``\\b``) block is unwrapped by click, so every line must fit
    eighty columns on its own or the shape breaks on a narrow terminal anyway.
    """
    epilog = cli.commands["download"].epilog
    long_lines = [line for line in epilog.splitlines() if len(line) > 79]
    assert long_lines == [], long_lines


# --------------------------------------------------------------------------- #
# AC3 — the ledger surface: the --dump sidecar carries the fact                #
# --------------------------------------------------------------------------- #

def test_dump_sidecar_declares_the_filename_stamp_timezone(tmp_path):
    """The sidecar is the ledger's own input, so the timezone fact is a FIELD there — and the
    addition is purely additive: ``document`` and ``blocks`` are untouched keepers.
    """
    docx = SimpleNamespace(title="T", document_id="DOCID")
    blocks = [SimpleNamespace(block_id="b1"), SimpleNamespace(block_id="b2")]

    download._dump_json(docx, blocks, str(tmp_path), "TOK")

    data = json.loads((tmp_path / "TOK.json").read_text(encoding="utf-8"))

    # Pinned keepers, unchanged in name and content.
    assert data["document"]["title"] == "T"
    assert len(data["blocks"]) == 2

    stamp = data["filename_timestamp"]
    assert stamp["timezone"] == "UTC"
    assert stamp["format"] == "[%Y-%m-%d_%H%M]"


def test_dump_sidecar_reports_local_basis_when_local_time(tmp_path):
    """LD-340 sibling: the sidecar stops lying. With ``local_time=True`` the ``timezone`` VALUE
    reports the run's actual basis (``"local"``); the KEYS are unchanged (pinned keeper), so a
    ledger reading the sidecar is never told UTC while the filename is the local clock."""
    docx = SimpleNamespace(title="T", document_id="DOCID")

    download._dump_json(docx, [], str(tmp_path), "TOK", local_time=True)
    stamp = json.loads((tmp_path / "TOK.json").read_text(encoding="utf-8"))["filename_timestamp"]
    assert stamp == {"timezone": "local", "format": "[%Y-%m-%d_%H%M]"}


def test_dump_sidecar_stays_deterministic_across_runs(tmp_path):
    """The sidecar is a function of the payload alone — the disclosure must not smuggle a
    run-varying clock reading into it (that is the filename's job, not the sidecar's).
    """
    docx = SimpleNamespace(title="T", document_id="DOCID")

    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    download._dump_json(docx, [], str(first), "TOK")
    download._dump_json(docx, [], str(second), "TOK")

    assert (first / "TOK.json").read_bytes() == (second / "TOK.json").read_bytes()
