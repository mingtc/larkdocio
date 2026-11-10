"""Pytest harness for larkdocio.

larkdocio is a proper package (``src/`` layout). To make a bare ``pytest`` from
the repo root work whether or not the package is pip-installed, we put ``src/``
on ``sys.path`` here — so ``import larkdocio...`` always resolves to the source
tree under test. (When the package is also installed, the source tree still
wins because it is inserted at the front.)

Fixture model — how we build SDK Block objects
-----------------------------------------------
``Parser.parse_docx_content`` consumes a list of ``lark_oapi`` SDK ``Block``
objects (attribute access: ``b.block_type``, ``b.text.elements[0].text_run``...).
We deserialize hand-authored JSON into REAL SDK objects rather than faking the
attribute surface with ``SimpleNamespace``.

Why the real SDK path: every SDK model's ``__init__`` ends with
``init(self, d, self._types)`` (see ``lark_oapi/core/construct.py``). ``init``
walks the supplied dict and, for each key it recognizes in ``_types``,
recursively constructs the nested typed object. So ``Block(d)`` faithfully
reproduces the exact object graph the live API client produces — including the
SDK's own quirk that every unset typed field is initialized to ``None`` (which
is what makes the handlers' ``getattr(..., default)`` calls behave the way they
do in production). A SimpleNamespace wrapper would not reproduce that quirk and
would let typos in fixtures pass silently. The JSON we author is the same shape
the API returns, so fixtures double as realistic payload samples.
"""

import contextlib
import os
import re
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC = _REPO_ROOT / "src"

# Source tree under test wins over any installed copy.
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Make this tests/ directory importable so test modules can do
# ``from harness import render`` regardless of pytest's import mode.
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import pytest

import live_write_fence  # noqa: E402
import media_guardrail  # noqa: E402
import private_tree  # noqa: E402
# LD-707: the private pattern set is read from its ledger ONCE, here, at collection — not by
# whichever test first imports a helper that needs it. A test that lazily imported one used to
# be charged with that read by the private-read guard and fail when run alone. Absent ledger
# (the public export): nothing is read and every name is inert.
import domain_vocabulary  # noqa: E402,F401
from harness import FIXTURES_DIR, build_blocks, render  # noqa: E402


# --------------------------------------------------------------------------
# LD-353 — the offline suite runs under xdist `-n auto` (pyproject `addopts`);
# the live / zoo / live_write rings stay SERIAL by seat ruling: the canary
# asserts byte-identity across two back-to-back downloads (an ordering property
# never proven under scheduling), live_write provisions and tears down real
# tenant documents (its failure mode is residue, not a red test), and both are
# API-bound, so parallelism would buy nothing anyway.
#
# `-m` is last-wins on the command line, so the ring a run selected is readable
# straight off `config.option.markexpr`. Anything that can SELECT a ring test
# (i.e. names it un-negated, or selects everything via `-m ""`) drops back to a
# single process.
# --------------------------------------------------------------------------
_RING_TOKEN_RE = re.compile(r"(?:(not)\s+)?\b(live_write|zoo|live)\b")


def ring_selection_requires_serial(markexpr):
    """True when the ``-m`` expression can select a live/zoo/live_write test."""
    expr = (markexpr or "").strip()
    if not expr:
        return True          # `-m ""` deselects nothing — the rings are in scope
    return any(m.group(1) is None for m in _RING_TOKEN_RE.finditer(expr))


# --------------------------------------------------------------------------
# LD-660 — THE SUITE'S PYTHON FLOOR IS 3.11. (LD-713, owner ruling 2026-11-07:
# the WHEEL's floor is now 3.11 too — the two claims coincide; see the
# SUPERSEDED IN PART note below and requirements/DECISIONS.md § D-119.)
# `tests/front_door.py` imports `tomllib` (stdlib from 3.11) to read
# pyproject.toml, so on 3.10 everything that reaches it cannot even be
# COLLECTED. Blast radius re-derived 2026-09-09 by an AST import walk over
# `tests/**` (not hand-listed): 44 test modules name it directly, **84 reach it
# transitively** — chiefly via `guard_kit`, which many guards import — carrying
# **4183 collected tests** under the default `-m`. (LD-660 filed the figure as
# 41 modules / 66 tests, measured another way; the walk is the reproducible
# one, and either way the conclusion is the same.) Two claims were being
# conflated:
#   * the WHEEL's `requires-python = ">=3.10"` — true at the time (nothing
#     under `src/larkdocio/` imported `tomllib` or any 3.11 feature), and
#     LD-660 did not narrow that promise.
#     SUPERSEDED IN PART (LD-713, 2026-11-07): the reason above stands — it was
#     true — but a promise for a version the suite cannot even collect on is a
#     promise nobody tests, so the owner raised the wheel's floor to 3.11 rather
#     than add 3.10 testing. `requires-python = ">=3.11"` now equals this floor.
#   * the SUITE's floor — was never declared, and `>=3.10` was read across from
#     the wheel's field and was FALSE.
# The choice (recorded as requirements/DECISIONS.md § D-119): DECLARE 3.11 rather than gate
# the import. Gating would mean either a `tomli` backport — a new dependency
# the house rules forbid outside the dev-only-pytest-plugin class — or a
# hand-rolled TOML reader inside the guard that reads pyproject, i.e. a second,
# less-trustworthy parser in exactly the place trustworthiness is the point.
# The refusal below is a `UsageError`, so a 3.10 run gets one sentence naming
# the reason instead of 66 collection errors that look like a broken checkout.
# --------------------------------------------------------------------------
SUITE_PYTHON_FLOOR = (3, 11)

SUITE_PYTHON_FLOOR_REASON = (
    "the test suite needs Python 3.11+: tests/front_door.py imports tomllib to read "
    "pyproject.toml. The shipped package's floor is the same — pyproject's "
    "requires-python is >=3.11. Run the suite on 3.11 or newer."
)


# tryfirst: xdist registers its DSession from a trylast `pytest_configure`, so clearing the
# options here is what actually keeps the run serial.
@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if sys.version_info < SUITE_PYTHON_FLOOR:
        floor = ".".join(str(n) for n in SUITE_PYTHON_FLOOR)
        running = ".".join(str(n) for n in sys.version_info[:3])
        raise pytest.UsageError(
            f"larkdocio's test suite requires Python >= {floor} (running {running}): "
            + SUITE_PYTHON_FLOOR_REASON
        )
    # LD-660 — THERE IS NO xdist-ABSENT GUARD HERE, DELIBERATELY, AND THE CASE IS UNDEFENDED
    # ON PURPOSE. This used to open with `if not hasattr(config.option, "numprocesses"):
    # return`, commented "pytest-xdist not installed". TWO measured facts retire it, and both
    # are recorded because either alone would leave the deletion looking careless:
    #
    #   1. THE SHAPE CANNOT REACH THIS HOOK. `-n auto` lives in pyproject's `addopts`, and
    #      pytest's argument parser rejects an unknown `-n` from the ini file before any hook
    #      runs, so an xdist-less install gets `ERROR: unrecognized arguments: -n`, EXIT 4 and
    #      0 collected. `pytest_configure` is never called.
    #   2. AND IF IT COULD, IT WOULD NOT NEED PROTECTING. The body below only ever ASSIGNS to
    #      `config.option` — `numprocesses = 0`, `dist = "no"` — and assignment to an
    #      `argparse.Namespace` cannot raise; it creates the attribute. The one READ,
    #      `markexpr`, already carries a `getattr` default. An earlier LD-660 draft kept the
    #      guard and claimed reading `numprocesses` "would raise AttributeError"; that was
    #      false, and the arm asserting it was vacuous — green with the guard and without it.
    #      One false comment traded for another, in the issue whose subject is exactly that.
    #
    # So the honest record is: the xdist-absent install is NOT defended here, it is not
    # defensible here, and nothing needs defending anyway. If `-n auto` ever leaves `addopts`,
    # fact 1 stops holding and this decision must be re-derived — which is why
    # tests/test_host_assumptions.py pins BOTH facts by execution, including an arm that
    # removes this hook's body-guard question entirely and shows no AttributeError appears.
    if ring_selection_requires_serial(getattr(config.option, "markexpr", "")):
        config.option.numprocesses = 0
        config.option.dist = "no"


# --------------------------------------------------------------------------
# LD-505 — THE MEDIA-MINTING GUARDRAIL. A live ring that mints PERMANENT,
# unpurgeable drive media does not run unless the run NAMES the issue that
# authorized the spend. The data is `gate_registry.MEDIA_VERDICTS`, the
# decision is `media_guardrail`, and this is the wiring — deliberately thin,
# so the judgement stays where it is written down.
#
# THE PLAIN OFFLINE SUITE IS UNTOUCHED. The hook returns immediately unless the
# run's `-m` expression can select a ring test, which `pyproject.toml`'s default
# addopts cannot: no mark is added, no line is written, the collected set and
# the skip count are exactly what they were.
#
# THE SKIP IS LOUD. A skip *reason* is only rendered under `-rs`, so a gated run
# also gets one line straight from the terminal reporter — and an AUTHORIZED run
# gets one too, echoing the issue id into the transcript a QA leg pastes. The
# echo is a recorded claim, never a permission check; see media_guardrail.
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _private_read_guard(request):
    """LD-685 AC3: a test that reads a file the public export lacks must carry `private_tree` (or
    `walks_tree`). Inert in the public tree. See tests/private_tree.py."""
    guard = private_tree.install(_REPO_ROOT)
    if not guard.active:
        yield
        return
    guard.begin(request.node)
    yield
    seen = guard.end()
    if seen:
        pytest.fail(
            f"{request.node.nodeid} read {len(seen)} file(s) the public export does not carry, "
            f"e.g. {seen[:3]}, without declaring it. Mark it @private_tree.<reason> if its subject "
            "is private, or @private_tree.walks_tree if it scans the whole repository and still "
            "checks the public subset; or point it at a public file (tests/captures/ for a "
            "recorded response). See tests/private_tree.py.", pytrace=False)


def pytest_collection_modifyitems(config, items):
    # LD-685: in the public export (no dev/), a test whose subject is private is skipped WITH its
    # reason; in this repository it runs. See tests/private_tree.py.
    private_tree.apply(items, _REPO_ROOT)
    if not media_guardrail.hook_is_active(getattr(config.option, "markexpr", "")):
        return
    decision = media_guardrail.authorization()
    gated = [item for item in items if media_guardrail.should_gate(item.nodeid, decision)]
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if decision.authorized:
        if reporter is not None and any(
            media_guardrail.should_gate(item.nodeid, media_guardrail.Authorization(
                "absent", None, "")) for item in items
        ):
            reporter.write_line(decision.message, bold=True)
        return
    if not gated:
        return
    for item in gated:
        item.add_marker(pytest.mark.skip(reason=decision.message))
    if reporter is not None:
        reporter.write_line(
            f"{decision.message} "
            f"({len(gated)} collected test(s) across "
            f"{len({i.nodeid.split('::', 1)[0] for i in gated})} minting file(s))",
            bold=True,
        )


# --------------------------------------------------------------------------
# LD-537 — THE LIVE-WRITE CONSENT FENCE. The `live_write` ring does not
# EXECUTE unless the run NAMES the issue that authorized it. The judgement is
# `live_write_fence`; this is the wiring, deliberately thin.
#
# WHY A SECOND FENCE. `addopts` DESELECTS the ring, and that stays — its reason
# (a default run must never reach the tenant) is untouched. What is superseded
# is the SUFFICIENCY claim: a deselection is a SELECTION control, and one typed
# `-o addopts=""` on an executing run clears it. That flag has been typed twice
# (wave 0: ~3 permanent media tokens; wave 2, 2026-08-20: 15 disposable Bases,
# one still live). So `-o addopts=""` RE-SELECTS the ring but cannot RE-ARM it.
#
# KEYED ON THE MARKER, never on a file list — a write gate added tomorrow is
# fenced with no registration step anywhere (contrast LD-505 above, which is
# file-data-driven because "which file uploads bytes" is a judgement).
#
# WHY `pytest_runtest_setup` AND NOT `pytest_collection_modifyitems`. Measured,
# not reasoned: a conftest `pytest_collection_modifyitems` runs BEFORE pytest's
# own mark-expression deselection, so at collection time the item list still
# holds every `live_write` test even on the default selection. Fencing at
# EXECUTION needs no reading of the run's selection state to be correct, and is
# inert by construction on any run where no ring item survives selection.
#
# THE SKIP IS LOUD. A skip *reason* renders only under `-rs`, so a fenced run
# also gets one line straight from the terminal reporter — written from the
# FINAL selected item set at `pytest_collection_finish` (after deselection), so
# the default suite gets no new line. An ARMED run gets a line too, echoing the
# issue id into the transcript a QA leg pastes. The echo is a recorded claim,
# never a permission check; see live_write_fence.
# --------------------------------------------------------------------------


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Refuse to EXECUTE a write-ring test that no issue id authorized.

    `tryfirst` is load-bearing: `_pytest.skipping`'s own `pytest_runtest_setup` is tryfirst
    too, so without it a test held by BOTH this fence and LD-505's media guardrail would raise
    the media skip first and this reason would never be seen. Running first lets the message
    carry the other gate's reason alongside its own (`live_write_fence.compose`) — an item can
    be gated twice, pytest reports one reason, and neither is allowed to be lost.
    """
    decision = live_write_fence.consent()
    if not live_write_fence.should_fence(item, decision):
        return
    others = [m.kwargs.get("reason", "") for m in item.iter_markers(name="skip")]
    pytest.skip(live_write_fence.compose(decision, others))


def pytest_collection_finish(session):
    """One loud line when the SELECTED set actually holds write-ring tests.

    Read from `session.items`, i.e. after every `pytest_collection_modifyitems` including
    pytest's own deselection — so the default offline suite, which selects none, gets no line.
    """
    ring = [item for item in session.items if live_write_fence.in_the_write_ring(item)]
    if not ring:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    decision = live_write_fence.consent()
    if decision.authorized:
        reporter.write_line(decision.message, bold=True)
        return
    files = {item.nodeid.split("::", 1)[0] for item in ring}
    reporter.write_line(
        f"{decision.message} ({len(ring)} selected test(s) across {len(files)} write-ring "
        f"file(s) will be SKIPPED, not run)",
        bold=True,
    )


def update_golden_enabled():
    """Golden files are regenerated when LARKDOCIO_UPDATE_GOLDEN is truthy or
    pytest is invoked with --update-golden."""
    return os.environ.get("LARKDOCIO_UPDATE_GOLDEN", "").lower() in ("1", "true", "yes")


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Regenerate golden .expected.md files from current parser output.",
    )


@pytest.fixture
def update_golden(request):
    return request.config.getoption("--update-golden") or update_golden_enabled()


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def build_blocks_fixture():
    return build_blocks


@pytest.fixture
def render_fixture():
    return render


# --------------------------------------------------------------------------
# LD-393 — ONE `larkdocio` module object per worker, whatever a test does.
#
# A test that pops a `larkdocio.*` entry out of `sys.modules` and re-imports it
# (LD-079's import-time-side-effect characterization in
# `test_cli_logging_config.py`, LD-042's eager-registration check in
# `test_registry.py`) leaves a SECOND live module object behind: every module
# that already did `from larkdocio.cli import cli` keeps the first one, while a
# later `monkeypatch.setattr("larkdocio.cli.handle_folder_command", ...)`
# resolves the second. The patch then lands on a module the invoked `cli` group
# never reads, the real handler runs, and the test dies on a symptom
# (`KeyError`) far from the cause — a verdict that depends on which xdist worker
# scheduled which test, i.e. a random FAIL on the binding gate.
#
# The fix is isolation at the root rather than a per-test dodge: the reload is
# legitimate INSIDE the test that wants it and is undone the moment that test
# ends, so no test can inherit a duplicate module object from a neighbour.
# --------------------------------------------------------------------------

_MISSING = object()


def _larkdocio_modules():
    return {
        name: module
        for name, module in sys.modules.items()
        if name == "larkdocio" or name.startswith("larkdocio.")
    }


@contextlib.contextmanager
def stable_larkdocio_modules():
    """Restore any `larkdocio.*` module object a block replaced in `sys.modules`.

    Modules merely *added* (a first-time import) are left alone — they are the
    same object graph everyone else already sees. Only a REPLACED entry is put
    back, which is exactly the duplicate-module leak.

    The parent package's ATTRIBUTE is restored to the VALUE it held, not to the
    module: a re-import rebinds `larkdocio.cli` on the `larkdocio` package object
    (and `import larkdocio.cli as m` reads that attribute, so `sys.modules` alone
    is not enough) — but several submodules are deliberately shadowed by an
    exported callable of the same name (`larkdocio.capabilities` is the FUNCTION),
    and there the pre-block value is the export, which the re-import clobbered.
    """
    snapshot = _larkdocio_modules()
    attrs = {}
    for name in snapshot:
        parent_name, _, child = name.rpartition(".")
        parent = sys.modules.get(parent_name) if parent_name else None
        if parent is not None:
            attrs[name] = (parent, child, getattr(parent, child, _MISSING))
    try:
        yield snapshot
    finally:
        for name, module in snapshot.items():
            if sys.modules.get(name) is not module:
                sys.modules[name] = module
        for parent, child, held in attrs.values():
            if held is _MISSING:
                continue
            if getattr(parent, child, _MISSING) is not held:
                setattr(parent, child, held)


@pytest.fixture(autouse=True)
def _stable_larkdocio_modules():
    with stable_larkdocio_modules():
        yield


# --------------------------------------------------------------------------- #
# LD-700 (QA note) — the suite leaves no bootstrap ./.env behind.              #
# --------------------------------------------------------------------------- #
#: A CLI verb resolves credentials through ``init_env()``, which CREATES an empty ``.env`` in the
#: working directory when none exists (documented behaviour, for a first-run user). A test that
#: invokes a verb without ``monkeypatch.chdir(tmp_path)`` therefore wrote one into the checkout —
#: into a fresh public export, an empty ``.env`` that nobody made. The tests that showed it chdir
#: now; this is the backstop for the rest: a ``.env`` the run created that is still exactly the
#: bootstrap template (blank values) is removed when the whole run ends (the xdist controller
#: only, after every worker is done). A ``.env`` that existed before the run, or one anybody
#: wrote a value into, is never touched.
_ENV_AT_START = {}


def pytest_sessionstart(session):
    if not hasattr(session.config, "workerinput"):
        root = Path(str(session.config.rootpath))
        _ENV_AT_START["path"] = root / ".env"
        _ENV_AT_START["existed"] = (root / ".env").exists()


def pytest_sessionfinish(session, exitstatus):
    path = _ENV_AT_START.get("path")
    if path is None or _ENV_AT_START["existed"] or not path.is_file():
        return
    from larkdocio.common.auth import BOOTSTRAP_ENV_TEMPLATE

    if path.read_text(encoding="utf-8") in ("", BOOTSTRAP_ENV_TEMPLATE):
        path.unlink()
