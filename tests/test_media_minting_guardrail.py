"""THE MEDIA-MINTING GUARDRAIL (LD-505) — the cost of a live ring becomes data, the
default becomes a LOUD SKIP, and the exception has to name the issue that authorized it.

The house invariant is **"a live gate never silently passes"** (PROJECT.md § The binding QA
gate). :mod:`gate_registry` already made the *absence of an offline mirror* into data. It said
nothing about the other cost of running a ring: **an upload mints a PERMANENT, UNPURGEABLE
drive media token** — ``larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA``, D-95, measured over
nine destructive spellings in fourteen sends — and **deleting the document does not remove it**.
So the price of a live run was invisible at exactly the moment somebody decided to pay it.

This guard is the enforcement half of three things:

* **AC1 — the classification.** :data:`gate_registry.MEDIA_VERDICTS` carries one verdict plus a
  written reason for **every** discovered ``tests/test_live_*.py``, exhaustive in both
  directions over the same globbed set the offline-mirror classification uses. Every filename is
  named **literally** in the registry source — there is no pattern derivation, for the same
  reason ``test_gate_registry`` forbids one — and the verdicts are **cross-checked against the
  files' own text**: a file that names one of the library's minting ops and declares itself
  mint-free reddens here, so a new uploading live gate cannot enter the tree silently.
* **AC2 / AC3 — the mechanism.** :mod:`media_guardrail` turns that data into a collection-time
  skip, wired in ``tests/conftest.py``. Unset opt-in ⇒ loud skip. Set-but-unparseable ⇒ loud
  skip naming what a well-formed value looks like. Never a silent run either way.
* **AC5 — the reuse pointer.** ``dev/media-token-ledger.md`` answers *"what has this project
  already minted, and where is each capture?"* out of **committed captures cited by path**. Every
  path it cites is checked to resolve here, because a pointer that dangles is worse than none.

AC4's doctrine (``requirements/DECISIONS.md`` D-97) is checked for its two grounds, its named
founding instances, and its statement of what is **not** a ground.

This guard reads files as text. It never imports or executes a gate module and makes no live
API call.
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest

import gate_registry as gr
import media_guardrail as mg
import private_tree  # noqa: E402  (LD-685)
from domain_vocabulary import RETIRED_ID

TESTS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent

DISCOVERED = sorted(p.name for p in TESTS_DIR.rglob("test_live_*.py"))  # LD-654: recursive
REGISTRY_SOURCE = (TESTS_DIR / "gate_registry.py").read_text(encoding="utf-8")

#: The library's own minting and uploading vocabulary, spelled as a caller writes it. Derived
#: from the four upload surfaces `larkdocio` ships — docx image/attachment
#: (`larkdocio.write.media`), sheets in-cell/float (`larkdocio.sheets.media`), Base attachment
#: (`larkdocio.base.media`) and the Drive file leg (`larkdocio.drive.files_write`) — plus the
#: two harness verbs a Base arm reaches them through.
UPLOAD_MARKERS = (
    "put_image_in_document",
    "put_file_in_document",
    "put_image_in_sheet",
    "put_float_image_in_sheet",
    "put_file_in_folder",
    "upload_all",
    "upload_chunked",
    "upload_prepare",
    "attach_media",
    "upload_media",
    "media.upload",
    "BaseMediaClient",
)


def _text(filename: str) -> str:
    return (TESTS_DIR / filename).read_text(encoding="utf-8")


def _markers_in(filename: str) -> list[str]:
    body = _text(filename)
    return [m for m in UPLOAD_MARKERS if m in body]


# ---------------------------------------------------------------------------
# AC1(c) — exhaustive in BOTH directions over the DISCOVERED set
# ---------------------------------------------------------------------------


def test_every_discovered_live_file_carries_a_media_verdict():
    """Drop a new ``tests/test_live_*.py`` into the tree and this reddens, naming it."""
    missing = sorted(set(DISCOVERED) - set(gr.MEDIA_VERDICTS))
    assert not missing, (
        "the media-minting classification is not exhaustive — these discovered "
        f"tests/test_live_*.py files carry no verdict: {missing}. Add one entry per file to "
        "gate_registry's media section, choosing a MediaMint value and writing the reason."
    )


def test_no_media_verdict_names_a_file_that_does_not_exist():
    stale = sorted(set(gr.MEDIA_VERDICTS) - set(DISCOVERED))
    assert not stale, (
        "the media-minting classification has stale entries — these files are classified but "
        f"were not discovered under tests/test_live_*.py: {stale}."
    )


def test_the_media_classification_covers_exactly_the_offline_mirror_classification():
    """The two classifications sit beside each other over one population, never two."""
    assert set(gr.MEDIA_VERDICTS) == set(gr.REGISTRY), (
        "the media verdicts and the offline-mirror rows disagree about the file population; "
        "they are two fields of one registry and must cover the same globbed set."
    )


# ---------------------------------------------------------------------------
# AC1(b) — a reasoned verdict per file, and NO pattern derivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", DISCOVERED)
def test_every_media_verdict_is_well_formed_and_reasoned(filename):
    """One case per discovered file, so a bad verdict names itself in the report."""
    assert filename in gr.MEDIA_VERDICTS, f"{filename} carries no media verdict"
    verdict = gr.MEDIA_VERDICTS[filename]
    assert verdict.filename == filename
    assert isinstance(verdict.mint, gr.MediaMint)
    assert verdict.reason.strip(), (
        f"{filename}: every verdict needs a written reason — including a verdict of NONE, so "
        '"no" is a recorded decision rather than a blank (LD-505 AC1b).'
    )


@pytest.mark.parametrize("filename", DISCOVERED)
def test_every_classified_file_is_named_LITERALLY_in_the_registry_source(filename):
    """No blanket pattern-skip: each filename is written out, never matched by shape.

    ``test_gate_registry`` forbids ``if "offline" in name: continue`` for the offline-mirror
    classification; the same hole is forbidden here, and this is what makes the prohibition
    observable rather than promised.
    """
    assert f'"{filename}"' in REGISTRY_SOURCE, (
        f"{filename} is classified but never named literally in tests/gate_registry.py — a "
        "verdict derived from a name pattern is the hole LD-505 AC1(b) forbids."
    )


# ---------------------------------------------------------------------------
# AC1(a)/(c) — the verdicts are CROSS-CHECKED against the files' own text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", DISCOVERED)
def test_a_file_that_NAMES_an_upload_op_is_not_quietly_declared_mint_free(filename):
    """The teeth. A new uploading live gate cannot enter the tree declaring NONE.

    A file naming one of the library's upload ops must either declare that it mints, or carry
    an explicit ``note`` saying why the marker is there and nothing is minted — which is the
    Maintainer's own superset trap written down (a file may merely *name* a token, or address a
    document/folder token that is not media at all).
    """
    markers = _markers_in(filename)
    if not markers:
        return
    verdict = gr.MEDIA_VERDICTS[filename]
    assert verdict.mint is not gr.MediaMint.NONE or verdict.note, (
        f"{filename} names the upload op(s) {markers} but is classified "
        f"{verdict.mint.name} with no note. Either it mints — say so — or write the note that "
        "says why the marker is present and nothing is minted."
    )


@pytest.mark.parametrize(
    "filename", sorted(gr.media_minting_gates()) or ["<no minting gate classified>"]
)
def test_a_declared_MINTER_really_names_a_minting_op(filename):
    """The other direction: an over-declaration is caught too."""
    assert filename in gr.MEDIA_VERDICTS, filename
    assert _markers_in(filename), (
        f"{filename} is classified PERMANENT_MEDIA but names none of the library's upload ops "
        f"{UPLOAD_MARKERS}. A verdict that outlives its call site is a false price."
    )


@pytest.mark.parametrize(
    "filename", [f for f in DISCOVERED if f.endswith("_offline.py")]
)
def test_no_OFFLINE_file_declares_a_mint(filename):
    """An offline file makes no API call, so it cannot mint anything."""
    assert gr.MEDIA_VERDICTS[filename].mint is gr.MediaMint.NONE, (
        f"{filename} is an offline file and cannot mint: it reads its subject as text."
    )


def test_the_published_media_table_is_byte_identical_to_the_projection():
    """The minting list is readable without running anything, and cannot drift."""
    rendered = gr.render_media_mint_table()
    begin = REGISTRY_SOURCE.index(gr.MEDIA_TABLE_BEGIN) + len(gr.MEDIA_TABLE_BEGIN) + 1
    end = REGISTRY_SOURCE.index(gr.MEDIA_TABLE_END)
    assert REGISTRY_SOURCE[begin:end] == rendered, (
        "the published media-minting table in gate_registry's docstring has drifted from "
        "render_media_mint_table(). Regenerate it; do not hand-edit the region."
    )


# ---------------------------------------------------------------------------
# AC2 / AC3 — the loud skip, and the opt-in that names its authorizing issue
# ---------------------------------------------------------------------------


def test_an_UNSET_opt_in_refuses_and_the_message_carries_all_four_required_facts():
    decision = mg.authorization({})
    assert not decision.authorized
    assert decision.state == "absent"
    message = decision.message
    assert "PERMANENT" in message and "unpurgeable" in message.lower(), message
    assert mg.OPT_IN_ENV in message, message
    assert "issue id" in message, message
    assert "D-97" in message and "requirements/DECISIONS.md" in message, message


def test_a_MALFORMED_value_still_refuses_and_says_what_a_value_must_be():
    for bad in ("1", "true", "yes", "LD", "ld-507", "LD-5", "", "   "):
        decision = mg.authorization({mg.OPT_IN_ENV: bad})
        assert not decision.authorized, f"{bad!r} must not authorize a mint"
        assert decision.state in ("absent", "malformed"), (bad, decision.state)
        assert "issue id" in decision.message, (bad, decision.message)


def test_a_WELL_FORMED_issue_id_authorizes_and_is_ECHOED_into_the_message():
    decision = mg.authorization({mg.OPT_IN_ENV: "LD-507"})
    assert decision.authorized
    assert decision.issue_id == "LD-507"
    assert "LD-507" in decision.message, decision.message


def test_the_ECHO_is_not_a_permission_check_and_the_mechanism_SAYS_so():
    """LD-505 AC3: this issue does not decide which issues are authorized."""
    source = (TESTS_DIR / "media_guardrail.py").read_text(encoding="utf-8")
    assert "not a permission check" in source, (
        "media_guardrail must state, at the mechanism, that the echoed id is a recorded claim "
        "and not an authorization — there is no allow-list of ids in this tree."
    )
    assert not re.search(r"ALLOW(ED)?_ISSUES|AUTHORIZED_IDS", source), (
        "no allow-list of issue ids lives in the tree (LD-505 AC3)."
    )


def test_the_gate_decision_is_driven_by_the_REGISTRY_not_a_hand_typed_list():
    assert mg.gated_files() == frozenset(gr.media_minting_gates())
    assert mg.gated_files(), "no minting gate is classified — the guardrail would gate nothing"


@pytest.mark.parametrize("nodeid", [
    "tests/test_live_sheets_float_image_gate.py::test_x",
    "tests/test_live_base_media_gate.py::test_y",
])
def test_a_minting_nodeid_is_gated_when_the_opt_in_is_absent(nodeid):
    assert mg.should_gate(nodeid, mg.authorization({}))


@pytest.mark.parametrize("nodeid", [
    "tests/test_live_canary.py::test_x",
    "tests/test_live_write_w1_gate.py::test_y",
])
def test_a_NON_minting_nodeid_is_never_gated(nodeid):
    assert not mg.should_gate(nodeid, mg.authorization({}))
    assert not mg.should_gate(nodeid, mg.authorization({mg.OPT_IN_ENV: "LD-507"}))


def test_an_authorized_run_does_not_gate_the_minting_file():
    decision = mg.authorization({mg.OPT_IN_ENV: "LD-506"})
    assert not mg.should_gate("tests/test_live_base_media_gate.py::test_x", decision)


def test_the_DEFAULT_offline_selection_is_untouched_by_the_hook():
    """The plain suite must stay byte-identically unaffected (AC2 / AC6).

    The hook is inert whenever the ``-m`` expression cannot select a ring test, which is
    exactly what ``pyproject.toml``'s default ``addopts`` says.
    """
    assert not mg.hook_is_active("not live and not zoo and not live_write")
    assert mg.hook_is_active("live_write")
    assert mg.hook_is_active("live")
    assert mg.hook_is_active("")


def test_the_env_variable_is_documented_in_env_example():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert mg.OPT_IN_ENV in text, (
        f"{mg.OPT_IN_ENV} must be documented in .env.example beside the other live-ring names "
        "(LD-505 AC3)."
    )


# ---------------------------------------------------------------------------
# AC4 — the doctrine is written down, with BOTH grounds
# ---------------------------------------------------------------------------


def _d97() -> str:
    text = (REPO_ROOT / "requirements" / "DECISIONS.md").read_text(encoding="utf-8")
    start = text.index("### D-97 —")
    end = text.find("\n### D-", start + 1)
    return text[start: end if end != -1 else len(text)]


@private_tree.register
def test_the_doctrine_entry_exists_in_the_registers_own_three_part_shape():
    entry = _d97()
    for part in ("**Ruling.**", "**Why.**", "**Provenance.**"):
        assert part in entry, f"D-97 is missing {part}"


@private_tree.register
def test_the_doctrine_carries_BOTH_grounds_with_their_founding_instances():
    entry = _d97()
    assert "upload" in entry and "bind" in entry, "ground 1 (the code paths under test)"
    assert "LD-507" in entry, "ground 1's founding instance is LD-507"
    assert "fixture" in entry.lower() and "hand-mock" in entry.lower(), (
        "ground 2 (fixture acquisition for a payload shape no committed capture carries, which "
        "PROJECT.md § Quality bar forbids hand-mocking)"
    )
    assert "LD-506" in entry, "ground 2's founding instance is LD-506"


@private_tree.register
def test_the_doctrine_records_what_is_NOT_a_ground():
    entry = _d97().lower()
    for word in ("convenience", "tidiness", "already captured"):
        assert word in entry, f"D-97 must record {word!r} as NOT a ground"


@private_tree.register
def test_the_doctrine_points_at_the_mechanism_and_the_reuse_pointer():
    entry = _d97()
    assert mg.OPT_IN_ENV in entry
    assert "dev/media-token-ledger.md" in entry


# ---------------------------------------------------------------------------
# AC5 — the reuse pointer RESOLVES
# ---------------------------------------------------------------------------

LEDGER = REPO_ROOT / "dev" / "media-token-ledger.md"
_CAPTURE_PATH_RE = re.compile(r"`(dev/[^`\s]+)`")
_ISSUE_RE = re.compile(r"\bLD-\d{3}\b|\bP0\b|" + RETIRED_ID.pattern)


@private_tree.citations
def test_the_reuse_pointer_exists():
    assert LEDGER.is_file(), f"{LEDGER} is the one addressable place AC5 asks for"


@private_tree.dev_record
def test_every_dev_path_the_ledger_CITES_resolves_on_disk():
    cited = sorted(set(_CAPTURE_PATH_RE.findall(LEDGER.read_text(encoding="utf-8"))))
    assert cited, "the ledger cites no capture at all — it is built from committed captures"
    dangling = [p for p in cited if not (REPO_ROOT / p).exists()]
    assert not dangling, (
        f"the media-token ledger points at paths that do not exist: {dangling}. It is built "
        "from committed captures cited by path — never from memory or a run's stdout."
    )


@private_tree.dev_record
def test_every_ledger_ROW_names_the_issue_that_minted_it():
    rows = [
        line for line in LEDGER.read_text(encoding="utf-8").splitlines()
        if line.startswith("| [") and "dev/" in line
    ]
    assert rows, "the ledger has no capture rows"
    unattributed = [r for r in rows if not _ISSUE_RE.search(r)]
    assert not unattributed, (
        f"every ledger row names the issue that minted it (AC5b); these do not: {unattributed}"
    )


@private_tree.dev_record
def test_the_ledger_is_HONEST_about_how_far_it_reaches():
    text = LEDGER.read_text(encoding="utf-8")
    assert "NOT A TOTAL" in text, (
        "AC5(c): the ledger must say it is not a total census and say how far it reaches, "
        "rather than implying a total."
    )


# RETIRED 2026-09-18 (pre-export evidence-tree retirement) — dev/README.md (in the dev repo) went with the evidence
# tree; dev/media-token-ledger.md itself is RETAINED and the AC5 content legs above still hold it.


class _FakeItem:
    def __init__(self, nodeid):
        self.nodeid = nodeid
        self.markers = []

    def add_marker(self, marker):
        self.markers.append(marker)


class _FakeReporter:
    def __init__(self):
        self.lines = []

    def write_line(self, line, **_kw):
        self.lines.append(line)


class _FakePluginManager:
    def __init__(self, reporter):
        self._reporter = reporter

    def get_plugin(self, name):
        return self._reporter if name == "terminalreporter" else None


class _FakeConfig:
    def __init__(self, markexpr, reporter):
        self.option = type("O", (), {"markexpr": markexpr})()
        self.pluginmanager = _FakePluginManager(reporter)


def _run_hook(markexpr, env, nodeids):
    import conftest

    reporter = _FakeReporter()
    items = [_FakeItem(n) for n in nodeids]
    saved = {k: os.environ.get(k) for k in (mg.OPT_IN_ENV,)}
    try:
        os.environ.pop(mg.OPT_IN_ENV, None)
        if env.get(mg.OPT_IN_ENV) is not None:
            os.environ[mg.OPT_IN_ENV] = env[mg.OPT_IN_ENV]
        conftest.pytest_collection_modifyitems(_FakeConfig(markexpr, reporter), items)
    finally:
        os.environ.pop(mg.OPT_IN_ENV, None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    return items, reporter


_MINTING_NODE = "tests/test_live_sheets_float_image_gate.py::test_float"
_PLAIN_NODE = "tests/test_live_canary.py::test_canary"


def test_the_hook_is_INERT_on_the_default_offline_selection():
    """No mark, no line — the plain suite is byte-identically unaffected (AC6)."""
    items, reporter = _run_hook(
        "not live and not zoo and not live_write", {}, [_MINTING_NODE, _PLAIN_NODE])
    assert [i.markers for i in items] == [[], []]
    assert reporter.lines == []


def test_the_hook_SKIPS_the_minting_ring_LOUDLY_when_the_opt_in_is_absent():
    items, reporter = _run_hook("live_write", {}, [_MINTING_NODE, _PLAIN_NODE])
    minting, plain = items
    assert len(minting.markers) == 1 and minting.markers[0].name == "skip"
    assert plain.markers == []
    reason = minting.markers[0].kwargs["reason"]
    assert mg.OPT_IN_ENV in reason and "D-97" in reason
    assert reporter.lines and mg.OPT_IN_ENV in reporter.lines[0], reporter.lines
    assert "1 collected test(s)" in reporter.lines[0], reporter.lines


def test_the_hook_LETS_AN_AUTHORIZED_RUN_THROUGH_and_ECHOES_the_issue_id():
    items, reporter = _run_hook("live_write", {mg.OPT_IN_ENV: "LD-507"}, [_MINTING_NODE])
    assert items[0].markers == []
    assert reporter.lines and "LD-507" in reporter.lines[0], reporter.lines
    assert "not a permission check" in reporter.lines[0], reporter.lines


def test_a_MALFORMED_opt_in_still_skips_rather_than_running():
    items, _reporter = _run_hook("live_write", {mg.OPT_IN_ENV: "1"}, [_MINTING_NODE])
    assert len(items[0].markers) == 1
    assert "must be an issue id" in items[0].markers[0].kwargs["reason"]


def test_no_LINE_is_written_when_the_selected_ring_holds_no_minting_file():
    items, reporter = _run_hook("live", {}, [_PLAIN_NODE])
    assert items[0].markers == []
    assert reporter.lines == []
