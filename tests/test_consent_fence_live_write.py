"""THE LIVE-WRITE CONSENT FENCE (LD-537) — the guard half.

**The fence being fixed here has been breached twice, on this repository, by correct and
well-warned legs.** Until LD-537 the ``live_write`` ring — 160 collected tests that
self-provision real Drive/Base/Sheets objects in the live tenant — was protected by exactly one
thing: being **deselected** in ``pyproject.toml``'s ``addopts``. A deselection is a *selection*
control, and one typed ``-o addopts=""`` on a run that executes tests clears it:

* **wave 0** — ~3 permanent, unpurgeable drive media tokens minted by an unintended ring run;
  the token ids were lost. (LD-505 closed the *media* half of that class.)
* **wave 2, 2026-08-20** — a full-suite ``--update-golden`` with the deselection cleared created
  **15 disposable Bases** in under three minutes; 14 self-deleted, and one
  (``BaseGoneExample000000000001``) was still live when this was written and read as gone by
  2026-08-25 (``tests/live_write_fence.py``). It was found only by a ``sha256`` of
  ``.base-disposables.json`` taken before and after the leg — **three self-reports and two
  complete QA reviews missed it**, and the leg's own report said *"no live_write run"* in good
  faith, because it never connected a slow run to having fired the rings.

So this suite holds the **second** fence: *selection* and *consent* are two different questions,
and ``-o addopts=""`` may re-select the ring but may not re-arm it. What it checks:

* **AC1 — the fence is at the RING, keyed on the MARKER.** Exhaustive by construction: the
  activation condition is the collected item's own ``live_write`` marker, so a write gate added
  tomorrow is fenced with **no registration step anywhere**. This suite proves that negatively
  (the mechanism names no test file and reads no registry) and positively (a synthetic item
  carrying the marker is fenced; the same item without it is not).
* **AC2 — the variable, the issue-id value, and the message as the product.** Three outcomes,
  not one of them a silent run, and the skip message names all five facts a human needs.
* **AC4 — the OLD fence stays.** ``addopts`` is unchanged and
  ``test_default_addopts_deselects_live_write`` still asserts what it always asserted; only the
  *sufficiency* claim around it was corrected (see that test's own docstring).
* **AC6 — nothing auto-arms it.** The ``.env.example`` line is commented out, so a fresh
  clone's ``./setup.sh`` seeds a ``.env`` in which the ring is **unarmed**, and no script, hook,
  workflow file or committed config exports or defaults the variable.

**Why the filename does not start with ``test_live_``.** That glob is ``gate_registry``'s
population of real live GATES, every member of which owes an offline-mirror row and a media
verdict (LD-505). This file is an **offline guard**, not a gate — it makes no API call — so it
stays out of that population by name rather than by an exemption somebody has to maintain.

This suite is offline. It reads files as text, calls the mechanism in-process with synthetic
items, and makes no API call — the behaviour proof against real collection is LD-537 AC3's
credential-stripped protocol, recorded in the issue's Handoff.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import conftest
import live_write_fence as fence
import media_guardrail as mg
import private_tree  # noqa: E402  (LD-685)

TESTS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FENCE_SOURCE = (TESTS_DIR / "live_write_fence.py").read_text(encoding="utf-8")
#: The mechanism's CODE, with the module docstring cut off. The negative checks below are
#: about what the code DOES (no filename, no registry, no selection-state read); the docstring
#: legitimately discusses all three in order to say why they are absent.
FENCE_CODE = FENCE_SOURCE.split('"""', 2)[2]
CONFTEST_SOURCE = (TESTS_DIR / "conftest.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Synthetic items — the fence is exercised in-process, never by firing a ring   #
# --------------------------------------------------------------------------- #

class _Marker:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs


class _Item:
    """The two pieces of pytest's item API the fence touches, and nothing else."""

    def __init__(self, nodeid, markers=()):
        self.nodeid = nodeid
        self._markers = list(markers)

    def get_closest_marker(self, name):
        for m in self._markers:
            if m.name == name:
                return m
        return None

    def iter_markers(self, name=None):
        return [m for m in self._markers if name is None or m.name == name]


def _ring_item(nodeid="tests/test_live_write_w1_gate.py::test_x", extra=()):
    return _Item(nodeid, [_Marker(fence.RING_MARKER), *extra])


class _Reporter:
    def __init__(self):
        self.lines = []

    def write_line(self, line, **_kw):
        self.lines.append(line)


class _Session:
    def __init__(self, items, reporter):
        self.items = items
        reporter_ = reporter

        class _PM:
            def get_plugin(self, name):
                return reporter_ if name == "terminalreporter" else None

        self.config = type("C", (), {"pluginmanager": _PM()})()


@pytest.fixture
def unset(monkeypatch):
    monkeypatch.delenv(fence.OPT_IN_ENV, raising=False)
    monkeypatch.delenv(mg.OPT_IN_ENV, raising=False)


# =========================================================================== #
# AC2 — the variable, the issue-id value, and the message as the product        #
# =========================================================================== #

def test_the_variable_is_named_for_CONSENT_and_in_the_LD505_dialect():
    """"authorized by whom", not a configuration knob — and the same shape as LD-505's."""
    assert fence.OPT_IN_ENV == "LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY"
    assert fence.OPT_IN_ENV.endswith("_AUTHORIZED_BY")
    assert mg.OPT_IN_ENV.endswith("_AUTHORIZED_BY"), (
        "the two consent variables share one dialect on purpose: a leg who knows one knows "
        "the other, and one .env.example neighbourhood carries both."
    )


def test_what_an_issue_id_IS_has_exactly_ONE_definition_in_this_tree():
    """LD-537 reuses LD-505's regex object rather than restating the grammar."""
    assert fence.ISSUE_ID_RE is mg.ISSUE_ID_RE
    assert not re.search(r"re\.compile", FENCE_SOURCE), (
        "live_write_fence must not compile its own issue-id pattern — one definition, "
        "imported from media_guardrail (LD-537 AC2)."
    )


def test_an_UNSET_variable_REFUSES_and_the_message_carries_all_FIVE_required_facts():
    decision = fence.consent({})
    assert not decision.authorized and decision.state == "absent"
    message = decision.message
    # (1) what the ring does to the live tenant, in the words a human reads
    assert "CREATES REAL OBJECTS IN THE LIVE LARK TENANT" in message, message
    for thing in ("documents", "Bases", "spreadsheets", "folders"):
        assert thing in message, (thing, message)
    assert "uploads bytes" in message and "NOTHING can purge" in message, message
    # (2) the exact variable
    assert fence.OPT_IN_ENV in message, message
    # (3) the value must be an authorizing issue id
    assert "authorizing issue id" in message and "LD-NNN" in message, message
    # (4) clearing addopts RE-SELECTS but does not ARM
    assert 'addopts=""' in message and "does NOT ARM" in message, message
    # (5) where the residue is ledgered
    assert fence.RESIDUE_LEDGER in message and "orphans()" in message, message


def test_a_MALFORMED_value_still_refuses_and_says_what_a_value_must_be():
    for bad in ("1", "true", "yes", "TRUE", "LD", "ld-537", "LD-5", "", "   ", "LD-537x"):
        decision = fence.consent({fence.OPT_IN_ENV: bad})
        assert not decision.authorized, f"{bad!r} must not arm the write ring"
        assert decision.state in ("absent", "malformed"), (bad, decision.state)
        assert "issue id" in decision.message, (bad, decision.message)


def test_a_TRUTHY_FLAG_is_exactly_what_cannot_arm_it_and_that_is_the_TEETH():
    """Both incidents were a TYPED FLAG. No plausible slip types `LD-533`."""
    for flag in ("1", "0", "true", "yes", "on", "y"):
        assert not fence.consent({fence.OPT_IN_ENV: flag}).authorized, flag


def test_a_WELL_FORMED_issue_id_ARMS_the_ring_and_is_ECHOED_into_the_message():
    decision = fence.consent({fence.OPT_IN_ENV: "LD-537"})
    assert decision.authorized and decision.issue_id == "LD-537"
    assert "LD-537" in decision.message and "ARMED" in decision.message


def test_surrounding_whitespace_is_tolerated_rather_than_silently_refused():
    decision = fence.consent({fence.OPT_IN_ENV: "  LD-537\n"})
    assert decision.authorized and decision.issue_id == "LD-537"


def test_the_ECHO_is_not_a_permission_check_and_the_MECHANISM_SAYS_so():
    """LD-537 AC2, the same statement LD-505 makes: no allow-list exists in this tree."""
    assert "not a permission check" in FENCE_SOURCE, (
        "live_write_fence must state, at the mechanism, that the echoed id is a recorded claim "
        "and not an authorization."
    )
    assert "no allow-list of issue ids" in FENCE_SOURCE
    assert not re.search(r"ALLOW(ED)?_ISSUES|AUTHORIZED_IDS|ALLOW_LIST\s*=", FENCE_SOURCE), (
        "no allow-list of issue ids lives in this tree — it would have to be edited by the "
        "very leg it is meant to restrain (LD-537 AC2)."
    )
    armed = fence.consent({fence.OPT_IN_ENV: "LD-537"}).message
    assert "RECORDED CLAIM" in armed and "not a permission check" in armed, armed


# =========================================================================== #
# AC1 — the fence is at the RING, keyed on the MARKER, exhaustive by            #
#       construction: no list, no registry, no registration step               #
# =========================================================================== #

def test_the_activation_condition_is_the_ITEMS_OWN_live_write_MARKER():
    assert fence.RING_MARKER == "live_write"
    unauthorized = fence.consent({})
    assert fence.should_fence(_ring_item(), unauthorized)
    assert not fence.should_fence(_Item("tests/test_anything.py::test_y"), unauthorized)


def test_an_ARMED_run_fences_NOTHING():
    armed = fence.consent({fence.OPT_IN_ENV: "LD-537"})
    assert not fence.should_fence(_ring_item(), armed)


def test_the_MECHANISM_NAMES_NO_TEST_FILE_and_READS_NO_REGISTRY():
    """The exhaustive-by-construction claim, from the negative side.

    LD-505's media guardrail is file-data-driven because *"which file uploads bytes"* is a
    judgement call. *"Is this test in the write ring"* is not — the marker already answers it —
    so a filename or a ``gate_registry`` row here would be a registration step somebody has to
    remember, which is exactly the hole this AC forbids.
    """
    assert "test_live_" not in FENCE_CODE, (
        "live_write_fence names a test file. The fence keys on the MARKER; a filename is a "
        "registration step a future write gate can be forgotten from (LD-537 AC1)."
    )
    assert "gate_registry" not in FENCE_CODE, (
        "live_write_fence must not read gate_registry — the marker is the membership test."
    )
    assert "hook_is_active" not in FENCE_CODE and "hook_is_active" not in _fence_wiring(), (
        "no reading of the run's SELECTION state may be load-bearing for this fence "
        "(LD-537 AC1): if no live_write item executes there is nothing to fence, and if one "
        "does the fence applies."
    )


def _fence_wiring() -> str:
    """The conftest region that wires LD-537, isolated from LD-505's region above it."""
    start = CONFTEST_SOURCE.index("# LD-537")
    return CONFTEST_SOURCE[start:CONFTEST_SOURCE.index("def update_golden_enabled()")]


# =========================================================================== #
# AC1/AC3(c) — the WIRING, exercised in-process                                 #
# =========================================================================== #

def test_the_hook_REFUSES_TO_EXECUTE_a_write_ring_item_when_the_variable_is_unset(unset):
    with pytest.raises(pytest.skip.Exception) as raised:
        conftest.pytest_runtest_setup(_ring_item())
    reason = str(raised.value)
    assert fence.OPT_IN_ENV in reason, reason
    assert "CREATES REAL OBJECTS IN THE LIVE LARK TENANT" in reason, reason


def test_the_hook_LEAVES_EVERY_NON_RING_ITEM_ALONE(unset):
    conftest.pytest_runtest_setup(_Item("tests/test_parser.py::test_offline"))


def test_the_hook_LETS_AN_ARMED_RUN_THROUGH(monkeypatch):
    monkeypatch.setenv(fence.OPT_IN_ENV, "LD-537")
    conftest.pytest_runtest_setup(_ring_item())


def test_a_MALFORMED_value_stops_the_ring_at_the_hook_too(monkeypatch):
    monkeypatch.setenv(fence.OPT_IN_ENV, "1")
    with pytest.raises(pytest.skip.Exception) as raised:
        conftest.pytest_runtest_setup(_ring_item())
    assert "must be an authorizing issue id" in str(raised.value)


def test_the_hook_runs_TRYFIRST_because_a_DOUBLY_GATED_test_must_lose_NEITHER_reason():
    """`_pytest.skipping`'s own runtest_setup is tryfirst; without this ours runs after it.

    29 of the ring's 160 tests are also held by LD-505's media guardrail, which gates at
    collection time by adding a skip marker. pytest reports ONE reason per test, so whichever
    hook runs first decides which reason a human sees — and the AC forbids a doubly gated test
    reporting only the media reason.
    """
    wiring = _fence_wiring()
    assert "@pytest.hookimpl(tryfirst=True)\ndef pytest_runtest_setup(item):" in wiring, wiring


def test_a_DOUBLY_GATED_item_carries_BOTH_reasons_and_loses_neither(unset):
    media_reason = mg.authorization({}).message
    item = _ring_item(extra=[_Marker("skip", reason=media_reason)])
    with pytest.raises(pytest.skip.Exception) as raised:
        conftest.pytest_runtest_setup(item)
    reason = str(raised.value)
    assert fence.OPT_IN_ENV in reason, "the fence's own reason went missing"
    assert mg.OPT_IN_ENV in reason, "LD-505's media reason went missing"
    assert "ALSO GATED, INDEPENDENTLY" in reason, reason


def test_compose_is_a_NO_OP_when_nothing_else_gates_the_item():
    decision = fence.consent({})
    assert fence.compose(decision, []) == decision.message
    assert fence.compose(decision, ["", "   ", None]) == decision.message


# --- the loud line, written from the FINAL selected set --------------------- #

def test_a_LOUD_LINE_is_written_when_the_SELECTED_set_holds_write_ring_tests(unset):
    reporter = _Reporter()
    conftest.pytest_collection_finish(_Session([_ring_item(), _Item("t.py::x")], reporter))
    assert reporter.lines, "a fenced run must say so at the top of the run, not only under -rs"
    line = reporter.lines[0]
    assert fence.OPT_IN_ENV in line and "1 selected test(s)" in line, line
    assert "will be SKIPPED, not run" in line, line


def test_NO_LINE_IS_WRITTEN_when_the_SELECTED_set_holds_no_write_ring_test(unset):
    """The default offline suite deselects the ring, so it must gain no new terminal line."""
    reporter = _Reporter()
    conftest.pytest_collection_finish(_Session(
        [_Item("tests/test_parser.py::a"), _Item("tests/test_guide.py::b")], reporter))
    assert reporter.lines == []


def test_an_ARMED_run_ECHOES_THE_ISSUE_ID_into_the_transcript(monkeypatch):
    monkeypatch.setenv(fence.OPT_IN_ENV, "LD-537")
    reporter = _Reporter()
    conftest.pytest_collection_finish(_Session([_ring_item()], reporter))
    assert reporter.lines and "LD-537" in reporter.lines[0], reporter.lines
    assert "not a permission check" in reporter.lines[0], reporter.lines


def test_the_LINE_is_read_from_the_FINAL_selected_set_not_from_collection():
    """Measured, not reasoned (LD-537 § Dependencies, the flagged hook-ordering hazard).

    A conftest ``pytest_collection_modifyitems`` runs BEFORE pytest's own mark-expression
    deselection, so at collection time the item list still holds every ``live_write`` test even
    on the default selection — a line written there would appear on the plain suite. The line is
    therefore written at ``pytest_collection_finish``, whose ``session.items`` is post-deselection.
    """
    wiring = _fence_wiring()
    assert "def pytest_collection_finish(session):" in wiring
    assert "session.items" in wiring
    assert "runs BEFORE pytest's" in wiring, (
        "the measured hook-ordering fact is what justifies the hook choice; keep it written down"
    )


# =========================================================================== #
# AC4 — the OLD fence stays, and its guard was TRANSFORMED, never deleted       #
# =========================================================================== #

def test_the_addopts_DESELECTION_is_still_there(pytestconfig):
    joined = " ".join(pytestconfig.getini("addopts"))
    assert "not live_write" in joined, (
        "the deselection is the FIRST of two fences and it stays — the consent fence does not "
        "replace it (LD-537 AC4; defense in depth)."
    )


def test_the_OLD_GUARD_was_TRANSFORMED_and_still_asserts_what_it_asserted():
    """`process/doctrine/supersession.md` § A.1 — preserve the reason, supersede the conclusion.

    A rationale-free rewrite of ``test_default_addopts_deselects_live_write`` is a FAIL: the
    guard keeps its assertion and its reason, and what changed is only the **sufficiency** claim
    around it — the deselection is now documented as the first of TWO fences.
    """
    source = (TESTS_DIR / "test_live_write_offline.py").read_text(encoding="utf-8")
    assert "def test_default_addopts_deselects_live_write(" in source, (
        "the old guard was deleted rather than transformed (CLAUDE.md § House rules)."
    )
    assert '"not live_write" in joined' in source, "its assertion must be unchanged"
    assert "LD-537" in source, "the transformation must name the issue that superseded it"
    assert "first of two" in source.lower(), "the sufficiency correction must be written down"


def test_the_TWO_FENCES_ARE_INDEPENDENT_controls_on_DIFFERENT_questions():
    """Selection and consent. Clearing one does not clear the other — that is the whole point."""
    from conftest import ring_selection_requires_serial
    assert ring_selection_requires_serial("")            # `-o addopts=""` selects the ring …
    assert not fence.consent({}).authorized              # … and still cannot arm it.


# =========================================================================== #
# AC6 — NOTHING auto-arms the variable, and this guard says so                  #
# =========================================================================== #

def test_the_env_example_LINE_IS_COMMENTED_OUT_so_setup_sh_leaves_the_ring_UNARMED():
    """``setup.sh`` seeds ``.env`` from ``.env.example`` on a fresh clone (setup.sh:145-149).

    An uncommented line there would arm the ring on every fresh worktree — a consent fence a
    bootstrap script arms is not a fence. LD-505's line is commented for the same reason.
    """
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    hits = [ln for ln in lines if fence.OPT_IN_ENV in ln]
    assert hits, f"{fence.OPT_IN_ENV} must be documented in .env.example (LD-537 AC5)"
    assignments = [ln for ln in hits if re.match(rf"\s*{fence.OPT_IN_ENV}\s*=", ln)]
    assert not assignments, (
        f".env.example carries an UNCOMMENTED {fence.OPT_IN_ENV} assignment: {assignments}. "
        "setup.sh copies that file to .env on a fresh clone, so the line must be commented out "
        "(LD-537 AC6)."
    )
    assert any(ln.strip().startswith("#") and "=" in ln for ln in hits), (
        "the commented example assignment is what a reader uncomments deliberately"
    )


#: What ACTUALLY setting the variable looks like, per file kind — a shell assignment (with or
#: without ``export``), a YAML mapping key, or an explicit environment write from python. A
#: mid-line MENTION is not a setter: ``pyproject.toml``'s marker help and PROJECT.md both quote
#: ``LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write`` as the command a human
#: types, which is documentation, not an auto-arm.
_SETTER_PATTERNS = tuple(re.compile(pat) for pat in (
    rf"^\s*(export\s+)?{fence.OPT_IN_ENV}\s*=",             # shell / dotenv assignment
    rf"^\s*-?\s*{fence.OPT_IN_ENV}\s*:",                    # YAML mapping key
    rf"os\.environ\[[\"']{fence.OPT_IN_ENV}[\"']\]\s*=",     # python env write
    rf"(setdefault|putenv)\(\s*[\"']{fence.OPT_IN_ENV}",     # python env default
))


def _setter_lines(body: str) -> list[str]:
    """Every line that SETS the variable, ignoring commented lines and bare mentions."""
    hits = []
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if fence.OPT_IN_ENV in line and any(r.search(line) for r in _SETTER_PATTERNS):
            hits.append(line.strip())
    return hits

_BOOTSTRAP_TREES = ("scripts", ".github")
# LD-677 dropped the old CI config from this tuple when it was retired. Removing it
# reduces the guard's coverage by NOTHING: ``_bootstrap_paths`` already globs every root-level
# ``*.yml``/``*.yaml`` below, so a root CI config was — and still is — collected generically.
# The named entry was redundant before the deletion and dangling after it.
_BOOTSTRAP_FILES = ("setup.sh", "pyproject.toml", "MANIFEST.in")


def _bootstrap_paths():
    paths = []
    for tree in _BOOTSTRAP_TREES:
        root = REPO_ROOT / tree
        if root.is_dir():
            paths += [p for p in root.rglob("*") if p.is_file()]
    paths += [REPO_ROOT / name for name in _BOOTSTRAP_FILES]
    paths += sorted(REPO_ROOT.glob("*.yml")) + sorted(REPO_ROOT.glob("*.yaml"))
    return sorted({p for p in paths if p.is_file()})


@private_tree.walks_tree
def test_NO_BOOTSTRAP_PATH_exports_or_defaults_the_variable():
    """The property that would rot silently a year from now, held by a test instead of prose.

    Every script, git hook, ``verify.sh`` path, workflow file and committed config in the tree:
    none of them may set, export or default the consent variable. A fence something else can arm
    is not a fence (LD-537 AC6).
    """
    offenders = []
    for path in _bootstrap_paths():
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line in _setter_lines(body):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {line}")
    assert not offenders, (
        f"these bootstrap paths SET {fence.OPT_IN_ENV}: {offenders}. Nothing but a human's "
        "deliberate act may arm the write ring (LD-537 AC6)."
    )


def test_NO_TEST_MODULE_ARMS_THE_RING_FOR_THE_WHOLE_RUN():
    """A test may set the variable in a monkeypatched dict; none may put it in the real env."""
    offenders = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        body = path.read_text(encoding="utf-8")
        if fence.OPT_IN_ENV not in body:
            continue
        for line in body.splitlines():
            if "os.environ[" in line and fence.OPT_IN_ENV in line and not line.lstrip().startswith("#"):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, (
        f"a test writes {fence.OPT_IN_ENV} straight into os.environ: {offenders}. Use "
        "monkeypatch.setenv (undone at teardown) or a plain dict passed to consent()."
    )


# =========================================================================== #
# AC5 — every doc that tells a leg how to run the write gate names the variable #
# =========================================================================== #

# The command as a leg would type it. A file containing this literal states the command
# ITSELF, and so is a candidate for AC5 whether or not anyone remembered to list it.
_BARE_COMMAND = "pytest -m live_write"

# The surfaces a leg or a consumer READS AS CURRENT. Deliberately a set of TREES, not of
# files: a new doc dropped into any of them enters the candidate set by existing.
_LIVE_SURFACE_GLOBS = (
    "*.md",                    # the root matrices + front door
    ".claude/**/*.md",         # role docs
    "process/**/*.md",         # the manual + doctrine
    "src/larkdocio/**/*.md",   # everything shipped in the wheel
    ".env.example",
    "pyproject.toml",
)

# The ONLY escape, and each row must say why in words. A file here states the command but does
# not *instruct* with it. Two classes, no third:
#   (r) a DATED APPEND-ONLY RECORD — the entry says what a past run did on a date; editing it
#       to name a variable that did not exist then would falsify the record, not correct it;
#   (e) an EVIDENCE CITATION in a capability matrix — the ring is named as *what proved a row*,
#       in a cell whose subject is the capability, not the reader's next command.
# A file that instructs is NOT exemptible: it gains the variable (LD-537 AC5).
#
# **FILTER-vs-SKIP: REFUSED, and this is the reason (LD-539 item (d)).** Wave-2 QA proposed
# filtering these rows out of the parametrize list below instead of leaving them as permanent
# skips (measured 2026-09-03: 6 rows, 6 skips, against 13 derived candidates). The refusal:
#   1. A ``pytest.skip`` PRINTS ITS OWN REASON on every run, and the reason string is the whole
#      substance of an exemption. Filtering makes an exemption free — it stops appearing
#      anywhere a run's output can be read, and becomes discoverable only by opening this
#      module. This table is the ONE hand-kept escape from a deliberately derived corpus, so
#      cheapening it is the wrong direction of travel.
#   2. The skip is also the ONLY place the escape is priced against the corpus: a filtered list
#      cannot show a reader that 7 of N candidates were let through.
#   3. It buys nothing but quiet. It changes no verdict, closes no hole, and LD-539 item (c)
#      just showed the failure mode here is an exemption too easily granted, not too loud.
# **What would change this mind, named so the next reader need not re-argue it:** the exempt
# rows outnumbering the non-exempt candidates (the skips would then be the report rather than
# a footnote to it), or the offline suite's total skip count rising far enough that a genuine
# environmental skip is lost in this table's noise. Neither holds at 6 of 13 (2026-09-03).
_AC5_EXEMPT = {
    "CHANGELOG.md": "(r) dated append-only record; entries state what a past run measured",
    # The packaged twin (``src/larkdocio/CHANGELOG.md``) HELD THIS ROW UNTIL LD-625 and its
    # REASON is unchanged and still correct — it is the same append-only record, and editing a
    # dated entry to name a variable that did not exist then would falsify it. What changed is
    # that the row stopped applying: the packaged copy is a recent-N WINDOW (LD-540), not a
    # byte-identical twin, and LD-625's ``[1.46.0]`` section evicted the oldest shipped one, so
    # the packaged bytes no longer state the bare command and the row was stale on the day it
    # stopped mattering. Dropped here rather than in a sweep. If a future release's entry quotes
    # the command again, the packaged copy becomes a candidate again — and the row is re-added
    # with this same reason, not with a new one.
    # ``progress.md`` HELD THIS ROW UNTIL LD-641 and its REASON is unchanged and still correct —
    # it is a dated activity log whose entries quote the command a past leg ran, and editing one
    # to name a variable that did not exist then would falsify the record. What changed is that
    # the row stopped being a claim about the file and became a claim about the WEATHER, and the
    # causal story is TWO commits, not one:
    #   * one commit (the second progress.md rotation) moved the last ten occurrences of the
    #     bare command into ``progress/history/oauth-attempt-and-to-v1.45.md``. That tree is in
    #     no glob of ``_LIVE_SURFACE_GLOBS``, so the bytes left the corpus entirely and the row
    #     went stale in exactly the change that stopped it mattering — which is why the trunk
    #     was red at that commit.
    #   * another (a narration entry, four commits later) UN-staled it by accident: its
    #     prose describing the red quotes the bare command at ``progress.md:572``, so the file
    #     re-entered the candidate set and the row was live again, healed by nothing but someone
    #     writing a string. A reader who sees only the rotation cannot explain why the row was
    #     live on the day it was dropped; that is why both commits are named here.
    # So this row is a PERMANENT exemption for a TRANSIENT membership — it flaps with prose, not
    # with policy — and it is dropped rather than left to go stale a third time. It is also no
    # longer needed on the merits: ``progress.md`` names LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY 7×
    # (2026-09-05), so it PASSES the parametrized arm below unexempted. Dropped here rather than
    # in a sweep. If a future rotation evicts the last bare-command entry AND the file stops
    # naming the variable, it leaves the corpus rather than needing a row; if it ever states the
    # command without naming the variable, the row is re-added with this same reason, not a new
    # one. (The general class — guard corpora derived from globs over live trees while this
    # repo's own file-movement tooling sits outside all of them — is reported by LD-641 AC5 for
    # the seat to rule on; no remedy is implemented here.)
    "ARCHIVE.md": "(e) quotes a closed issue's own title verbatim; retitling it falsifies it",
    "PERMISSIONS.md": "(e) GENERATED projection of larkdocio.permissions; the ring appears in a "
                      "scope row's evidence column, and the authoring source is the module",
    "SHEETS.md": "(e) capability matrix — the ring is cited as the gate proving a row",
    "DRIVE.md": "(e) capability matrix — the ring is cited as the gate proving a row",
}


def _ac5_candidates():
    """DERIVED, not listed: every live surface whose bytes state the bare command."""
    hits = set()
    for pattern in _LIVE_SURFACE_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            if _BARE_COMMAND in path.read_text(encoding="utf-8"):
                hits.add(str(path.relative_to(REPO_ROOT)))
    return sorted(hits)


@private_tree.citations
def test_the_AC5_CORPUS_IS_DERIVED_so_a_new_doc_cannot_escape_it():
    """The pre-fix version of this guard parametrized a hand-list of four files and its
    docstring claimed *"these four each state the command themselves"*. **A fifth did**
    (``src/larkdocio/write/README.md``, found by fresh-eyes QA), so the claim was false and the
    guard was blind to the exact class it polices. The list is now derived from the live
    surfaces; the only hand-kept thing is the EXEMPT table, and every row of it carries a
    reason. Sanity-check the derivation so a broken glob cannot silently empty the corpus.

    **LD-539 item (c) — the hole the derivation left open.** Deriving the corpus stopped a new
    doc escaping by not being listed; it did not stop a listed doc escaping by being
    *exempted*. This guard asserted the five instructing files were **candidates** and that no
    exemption had gone stale, but never that an instructing file was **absent from**
    ``_AC5_EXEMPT`` — so one row with a fabricated reason silenced the AC5 check for that file
    and left the guard green. The added arm closes the list, not the criteria."""
    candidates = _ac5_candidates()
    assert len(candidates) >= 8, f"the AC5 derivation collapsed: {candidates}"
    for relpath in ("PROJECT.md", "pyproject.toml", ".env.example",
                    "src/larkdocio/write/README.md", "src/larkdocio/GUIDE.md"):
        assert relpath in candidates, f"{relpath} states the command but was not derived"
        # LD-539 item (c): being a *candidate* was never the property that mattered. These
        # five INSTRUCT, so none of them is exemptible at all — before this line an
        # exemption with a fabricated reason kept the guard green.
        assert relpath not in _AC5_EXEMPT, (
            f"{relpath} INSTRUCTS a leg how to run the write gate and has been exempted "
            f"({_AC5_EXEMPT.get(relpath)!r}). The two admissible classes are (r) a dated "
            "append-only record and (e) an evidence citation in a capability matrix; an "
            "instructing file is in neither, whatever reason the row carries (LD-539)."
        )
    stale = [k for k in _AC5_EXEMPT if k not in candidates]
    assert not stale, (
        f"these AC5 exemptions no longer state the command: {stale}. An exemption outlives its "
        "reason silently — drop the row in the change that stopped it mattering."
    )


@private_tree.walks_tree
@pytest.mark.parametrize("relpath", _ac5_candidates())
def test_every_doc_that_tells_a_leg_HOW_TO_RUN_THE_WRITE_GATE_names_the_variable(relpath):
    """Consumer-and-operator truth is part of shipping, not a later sweep.

    One rule, one owner: a doc that already *points* at PROJECT.md need not restate the
    command, but **no doc may be left stating a command that no longer runs the ring**. Every
    live surface stating the command itself names the variable beside it, unless it is in
    ``_AC5_EXEMPT`` with a written reason.
    """
    if relpath in _AC5_EXEMPT:
        pytest.skip(f"AC5-exempt: {_AC5_EXEMPT[relpath]}")
    body = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert fence.OPT_IN_ENV in body, (
        f"{relpath} tells a leg how to run the write gate but does not name {fence.OPT_IN_ENV}. "
        "`pytest -m live_write` alone no longer runs the ring (LD-537 AC5). If it CITES the "
        "ring rather than instructing with it, add it to _AC5_EXEMPT with a reason."
    )


def test_the_MARKER_HELP_a_leg_reads_via_pytest_markers_is_no_longer_INCOMPLETE():
    """``pytest --markers`` is documentation. It said "run with `pytest -m live_write`", which
    is now insufficient — that command alone selects the ring and the fence then skips it."""
    body = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    row = [ln for ln in body.splitlines() if ln.strip().startswith('"live_write:')]
    assert row, "the live_write marker row vanished from pyproject.toml"
    assert fence.OPT_IN_ENV in row[0], row[0]


def test_the_ADDOPTS_STRING_ITSELF_did_not_move():
    """AC4/AC7: the one permitted pyproject diff is the marker help string."""
    body = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        'addopts = "-q -n auto -m \'not live and not zoo and not live_write\'"' in body
    ), "addopts moved. The consent fence changes EXECUTION, never SELECTION (LD-537 AC4)."


# ============================================================================= #
# LD-539 item (a) — the SHIPPED PAYLOAD half of AC5: capabilities() states the   #
# command too, and no .md glob can ever see it                                   #
# ============================================================================= #

# AC5's corpus above globs `*.md`, `.claude/**/*.md`, `process/**/*.md`,
# `src/larkdocio/**/*.md`, `.env.example` and `pyproject.toml`. It reaches **no python
# source**, which is exactly why LD-537 could land the fence and still leave the four
# `capabilities/_gates.py` gate descriptors telling a consumer to run the bare command
# (found by the wave-2 close report, fixed by LD-539). A consumer reading
# `capabilities(full=True)` never opens a .md file, so the payload is a live instructing
# surface in its own right and is guarded here on the same rule.
_PY_SURFACE_GLOB = "src/larkdocio/**/*.py"

# The same two-classes-no-third escape as `_AC5_EXEMPT`, for python source. A line here
# states the bare command but does not *instruct* with it:
#   (e) an EVIDENCE CITATION — the ring is named as *what proved* a claim, in prose whose
#       subject is the claim, not the reader's next command.
# There is no (r) class here: python source is not a dated record.
# Accounted for BY NAME rather than by a glob, so a new bare occurrence must declare itself.
_AC5_PY_EXEMPT = {
    "src/larkdocio/permissions.py":
        "(e) evidence citation — the `docx:document` scope's `evidence` string names the ring "
        "that behaviourally confirmed the scope; the subject is the scope, not a command. It "
        "is also the authoring source of PERMISSIONS.md, itself AC5-exempt for the same reason",
    "src/larkdocio/write/apply.py":
        "(e) evidence citation — the module docstring names the ring that is the engine's "
        "binding end-to-end gate; the subject is the engine's proof, not the reader's command",
}


def _ac5_py_offenders():
    """DERIVED: every shipped python line stating the bare command without the variable."""
    offenders = []
    for path in sorted(REPO_ROOT.glob(_PY_SURFACE_GLOB)):
        relpath = str(path.relative_to(REPO_ROOT))
        if relpath in _AC5_PY_EXEMPT:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _BARE_COMMAND in line and fence.OPT_IN_ENV not in line:
                offenders.append(f"{relpath}:{line_no}: {line.strip()}")
    return offenders


def test_NO_SHIPPED_PYTHON_SOURCE_states_the_bare_command_without_the_variable():
    """The gap AC5 could not see: a fifth `_gates.py` descriptor reddens here.

    `pytest -m live_write` alone no longer runs the ring (LD-537 AC5), and
    `capabilities()`'s `gate_coverage.command` is read as *the thing to type*. Every
    `live_write` command the wheel ships names the variable beside it, or is in
    `_AC5_PY_EXEMPT` with a written reason.
    """
    offenders = _ac5_py_offenders()
    assert not offenders, (
        f"these shipped python lines state {_BARE_COMMAND!r} without naming "
        f"{fence.OPT_IN_ENV}: {offenders}. A consumer typing that command selects the ring "
        "and the fence then skips it (LD-537 AC5). If the line CITES the ring rather than "
        "instructing with it, add the file to _AC5_PY_EXEMPT with a reason."
    )


def test_the_PY_EXEMPT_ROWS_have_not_gone_stale():
    """An exemption outlives its reason silently — drop the row in the change that stopped
    it mattering (the same law `_AC5_EXEMPT`'s staleness arm holds for the .md corpus)."""
    stale = []
    for relpath in _AC5_PY_EXEMPT:
        path = REPO_ROOT / relpath
        if not path.is_file() or _BARE_COMMAND not in path.read_text(encoding="utf-8"):
            stale.append(relpath)
    assert not stale, (
        f"these python AC5 exemptions no longer state the command: {stale}."
    )


def test_EVERY_live_write_COMMAND_IN_THE_SHIPPED_PAYLOAD_names_the_variable():
    """The property from the consumer's side, read off `capabilities()` rather than off the
    source — so a gate descriptor wired into the payload from anywhere is covered, and the
    placeholder is proved not to read as a truthy flag (LD-539 AC1: a rendered `=1` or
    `=true` would be a FAIL, because the fence's teeth are that the value is an issue id).
    """
    from larkdocio import capabilities

    commands = [
        coverage["command"]
        for surface in capabilities(full=True)["surfaces"].values()
        if (coverage := surface.get("gate_coverage")) and coverage["marker"] == "live_write"
    ]
    assert len(commands) >= 4, f"the payload derivation collapsed: {commands}"
    for command in commands:
        assert command == f"{fence.OPT_IN_ENV}=LD-NNN {_BARE_COMMAND}", command
