# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Where a download lands, what it is called, and the six-key ``config.json`` schema —
documented where a WHEEL reader can open them, and guarded against the code rather than
against themselves.

**RENAMED, NOT REPLACED (LD-650).** This module was named after a document type. Its
subject was never *that document type* — it was **the documented truth about where a download
lands and what it is called**, which is a permanent question — but half of its arms were
pinned to a document-type-specific derivation the library no longer performs. Those arms
retired with the code they guarded, under the ledger row LD-650 recorded; everything whose
subject SURVIVED the cut was re-homed here rather than deleted, which is why the AC numbering
below is discontinuous. The name is now feature-agnostic so the next placement rule does not
need a third module.

**Why this file exists.** ``-o``'s help text said *"Specify the output directory for the
markdown files"* while the reader was rewriting ``-o`` off a table in the converted body and
welding a local-time stamp onto the filename. The help was once accurate and rotted, because
nothing held it to the code. So every claim is held to a **derivation**:

* the three filename shapes are exercised against the real ``_write_markdown``;
* the placement claims are exercised against the real ``_apply_explicit_route`` and the real
  no-route branch (the deeper contract pins live in
  ``tests/test_download_route_contract_pins.py``);
* the six-key schema's keys, defaults and example file are **projected** off
  ``OutputConfig`` (one authored copy of the meanings, in
  :data:`larkdocio.capabilities.CONFIG_KEY_MEANINGS`), and both documents that carry it hold a
  generated region byte-identical to that projection.
"""
import json
import pathlib
import re
import textwrap
from importlib import import_module

import pytest
from click.testing import CliRunner

#: The capabilities MODULE, not the ``capabilities()`` function ``larkdocio/__init__.py``
#: re-exports under the same name — ``from larkdocio import capabilities`` hands back the
#: callable, which is not what a monkeypatch of a module global can be pointed at.
caps_mod = import_module("larkdocio.capabilities")

#: Where a config-schema global must be patched for ``config_schema()`` to see it. Since
#: LD-244 the registry is a PACKAGE, and a function resolves its globals in the module that
#: DEFINES it, not in the package that re-exports it — so patching ``caps_mod`` would set an
#: attribute nothing reads and the three exit-condition tests below would pass vacuously.
#: DERIVED from the function's own ``__module__`` rather than hard-coded, so it keeps
#: following the code if the schema leg ever moves again.
caps_config_mod = import_module(caps_mod.config_schema.__module__)

from larkdocio.capabilities import (
    CONFIG_KEY_MEANINGS,
    CONFIG_REGENERATE,
    CONFIG_REGION_BEGIN,
    CONFIG_REGION_END,
    config_schema,
    config_schema_markdown,
)
from larkdocio.guide import guide
from larkdocio.permissions import region_of
from larkdocio.read import download as dl
from larkdocio.read.config import Config, OutputConfig
from larkdocio.utils.sanitize import sanitize_path_string

import front_door as fd
from consumer_text import cli_group, cli_help_pages
import private_tree  # noqa: E402  (LD-685)


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS_MD = REPO_ROOT / "TOOLS.md"
README_MD = REPO_ROOT / "README.md"


def flat(text: str) -> str:
    """Prose with its line breaks collapsed, lower-cased.

    Every prose assertion below reads this rather than the raw section: a documented phrase is a
    phrase whatever column the paragraph happened to wrap at, and a guard that a re-wrap can
    redden teaches the next editor to satisfy it by not re-wrapping.
    """
    return re.sub(r"\s+", " ", text).lower()


def readme_bullet(prefix: str) -> str:
    """One README bullet, WHOLE — its continuation lines included.

    The bullets this issue rewrote are multi-line, and a first-line-only read would have
    asserted over a sentence fragment.
    """
    lines = README_MD.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(prefix))
    out = [lines[start]]
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("- ") or line.startswith("#"):
            break
        out.append(line)
    return "\n".join(out)


#: The guide chapter that owns BOTH questions this module guards — where the file lands and
#: what it is called. Its heading moved with LD-650 (the old one named a document format), so
#: it is stated once, here, and every arm reads the chapter through :func:`routing_section`.
PLACEMENT_HEADING = "### Where the file lands: `-o`, and `--route` when you name the subpath"


def routing_section(text: str) -> str:
    """The guide's output-placement chapter — from its heading to the next heading."""
    heading = PLACEMENT_HEADING
    start = text.find(heading)
    assert start != -1, (
        f"the guide has no {heading!r} subsection — the routing rule has no documented home"
    )
    nxt = text.find("\n#", start + len(heading))
    return text[start:nxt if nxt != -1 else len(text)]


# --------------------------------------------------------------------------- #
# AC2 — the no-route path and the three filename shapes.                       #
# --------------------------------------------------------------------------- #

def _written_name(tmp_path, title, markdown="# x", title_as_filename=True):
    """Run the REAL ``_write_markdown`` and return the single filename it produced."""
    config = Config(OutputConfig(title_as_filename=title_as_filename))
    dl._write_markdown(config, str(tmp_path), "doctokenAAA", title, markdown)
    written = sorted(p.name for p in tmp_path.iterdir())
    assert len(written) == 1, written
    return written[0]


_STAMP = r"\[\d{4}-\d{2}-\d{2}_\d{4}\]_"


def test_ac2_shape_one_titled_file_carries_the_local_time_stamp(tmp_path):
    name = _written_name(tmp_path, "Example Document Title")
    assert re.fullmatch(_STAMP + r"Example_Document_Title\.md", name), name


def test_ac2_shape_two_an_empty_title_falls_back_to_the_stamped_TOKEN(tmp_path):
    assert re.fullmatch(_STAMP + r"doctokenAAA\.md", _written_name(tmp_path, ""))


def test_ac2_shape_two_a_title_that_sanitizes_to_untitled_also_falls_back(tmp_path):
    assert re.fullmatch(_STAMP + r"doctokenAAA\.md", _written_name(tmp_path, "untitled"))


def test_ac2_shape_three_title_as_filename_false_has_NO_STAMP_AT_ALL(tmp_path):
    assert _written_name(tmp_path, "Any Title", title_as_filename=False) == "doctokenAAA.md"


def test_ac2_the_guide_documents_all_THREE_filename_shapes():
    section = routing_section(guide(full=True))
    assert "[YYYY-MM-DD_HHMM]_" in section, "the stamp's shape must be shown, not described"
    assert "title_as_filename" in section, (
        "the stamp is welded to title_as_filename — the coupling is the point"
    )
    low = flat(section)
    assert "utc" in low, "the stamp is UTC, not local time; say which"
    assert "untitled" in low, "the empty/untitled fallback shape must be documented"
    assert "no timestamp" in low or "no stamp" in low, (
        "with title_as_filename false there is no timestamp at all — that is the knob a "
        "consumer wanting a stable filename needs"
    )


def test_ac2_the_guide_documents_the_NO_ROUTE_path(tmp_path):
    """TRANSFORMED, not deleted (LD-650). Its subject was *the outcome when the output is NOT
    relocated*, which still exists — what changed is that it is now the only outcome there is
    unless the caller asks for another. The old arms asserted the miss report's level and the
    off-switch's name; both objects are gone, so the claim they held is restated as the one
    the guide must now make."""
    low = flat(routing_section(guide(full=True)))
    assert "flat" in low or "exactly as you gave it" in low, (
        "the guide must state that -o is used as given when no --route is passed"
    )
    assert "infers nothing" in low or "derives no destination" in low or (
        "no body sniffing" in low
    ), "the guide must state that nothing in the document moves the output"


def test_ac2_a_document_with_no_route_is_written_straight_to_the_output_dir(tmp_path):
    """End to end over the real no-route branch and the real writer: no --route, no subpath,
    one file at the root — and the value that branch produces still answers `.record`, which
    is the AttributeError the naive cut would have shipped."""
    out = dl.RoutedPath(str(tmp_path), routed=False, reason=dl.ROUTE_DISABLED,
                        derivation_ran=False)
    assert out == str(tmp_path)
    assert out.record["routed"] is False
    dl._write_markdown(Config(), out, "tok", "Plain Doc", "# A plain document\n")
    assert [p.name for p in tmp_path.iterdir()] and all(
        p.is_file() for p in tmp_path.iterdir()
    )


# --------------------------------------------------------------------------- #
# AC3 — ``-o``'s help text tells the truth.                                    #
# --------------------------------------------------------------------------- #

def _download_help(columns: str = "200") -> str:
    """The rendered ``download --help`` page.

    Wide by default: click hard-wraps help text, and a claim asserted over a narrow render is
    really a claim about where the wrap fell. The eighty-column render — the width the shipped
    corpus renders at — is asked for explicitly where the wrapping itself is the subject.
    """
    runner = CliRunner(env={"COLUMNS": columns})
    return runner.invoke(cli_group(), ["download", "--help"], prog_name="larkdocio").output


def test_ac3_the_help_no_longer_claims_o_is_simply_the_output_directory():
    page = _download_help()
    assert "Specify the output directory for the markdown files" not in page, (
        "the rotted string is back: -o is the ROOT the output directory is derived under"
    )
    assert "root" in page.lower(), "the help must say -o is a root"


def test_ac3_the_help_names_the_ONE_way_output_moves_and_where_to_read_the_rule():
    page = _download_help().lower()
    assert "--route" in page, (
        "--route is the only thing that moves output off -o; -o's own help must send the "
        "reader to it"
    )
    assert "guide" in page, "the help must point at where the full rule is written"


def _download_params() -> dict:
    """``{first option spelling: help text}`` for every ``download`` option that has help."""
    return {
        param.opts[0]: param.help
        for param in cli_group().commands["download"].params
        if getattr(param, "help", None)
    }


def test_ac3_the_help_line_stays_a_help_line():
    """A ``--help`` line, not a paragraph — bounded against the page it shares rather than
    against a number somebody picked: ``-o``'s help must stay no longer than the shortest
    help already on this command that carries a real explanation, and it must render in at
    most six lines at eighty columns (the width the corpus renders the page at)."""
    params = _download_params()
    mine = params["-o"]
    others = [h for opt, h in params.items() if opt != "-o" and len(h) > 60]
    assert others, "no other explanatory option help on `download` to bound against"
    assert len(mine) <= min(len(h) for h in others), (
        f"-o's help ({len(mine)} chars) is longer than every explanatory option help already on "
        f"the page ({sorted(len(h) for h in others)}) — that is a paragraph, not a help line"
    )
    page = _download_help(columns="80").splitlines()
    start = next(i for i, line in enumerate(page) if "-o, --output" in line)
    block = 1 + next(
        i for i, line in enumerate(page[start + 1:]) if line.strip().startswith("--")
    )
    assert block <= 6, f"-o's help renders as {block} lines at 80 columns"


def test_ac3_the_double_nesting_warning_is_reachable_from_the_WHEEL():
    """The single most actionable sentence in the repo-side docs, still where a consumer is.
    It survives LD-650 with its subject changed from the DERIVED subpath to the caller's own:
    pre-building `--route`'s path into `-o` double-nests exactly as pre-building a derived one
    used to."""
    low = guide(full=True).lower()
    assert "double-nest" in low, (
        "'do not pre-build the subpath into -o as well — it double-nests' must reach the wheel"
    )


def test_ac3_the_double_nesting_warning_is_in_the_readme_too():
    assert "double-nest" in README_MD.read_text(encoding="utf-8").lower()


# --------------------------------------------------------------------------- #
# AC4 — the RETIRED config key: accepted, ignored, and no CLI flag ever existed. #
# --------------------------------------------------------------------------- #

def test_ac4_the_guide_tells_an_UPGRADING_reader_what_became_of_the_retired_key():
    """TRANSFORMED twice (LD-650, then LD-704 absorbing LD-674). The old arm held the guide to
    naming the off-switch; then to naming the retired key and its tolerance window. The window
    is discharged and the key is no longer special-cased, so the claim a reader needs now is
    the rule it falls under — stated without naming it (`D-121` (8)): refused as a constructor
    argument, ignored in config.json like any unknown key."""
    import larkdocio.read.config as config_module

    section = flat(re.sub(r"(?m)^>\s?", "", routing_section(guide(full=True))))
    assert "a retired output key from earlier versions is no longer accepted" in section, (
        "the guide must tell an upgrading reader the retired key is no longer accepted")
    assert "typeerror" in section and "unknown key" in section, (
        "say what each door does now: the constructor refuses, config.json ignores")
    assert not hasattr(config_module, "RETIRED_OUTPUT_KEYS"), (
        "the guide says the tolerance is discharged; the module still declares one")


def test_ac4_a_retired_key_meets_the_UNKNOWN_KEY_rule_at_BOTH_doors(caplog):
    """TRANSFORMED (LD-650 → LD-704). The behaviour ruling (b) bought — accepted, ignored,
    reported — was a one-release tolerance; discharged, a retired key is an unknown key: a
    stale config.json still loads and the key is ignored, the constructor keyword is refused.
    A stand-in name: the real one is held by tests/test_config.py's private-ledger census."""
    key = "a_retired_switch"
    with caplog.at_level("WARNING", logger="larkdocio"):
        from_file = OutputConfig.from_dict({"image_dir": "x", key: False})
    assert from_file.to_dict()["image_dir"] == "x"
    assert key not in from_file.to_dict() and not hasattr(from_file, key)
    assert not [r for r in caplog.records if key in r.message]
    with pytest.raises(TypeError):
        OutputConfig(**{key: False})


def _declared_window():
    """The tolerance window ``read/config.py`` declares, or ``None`` when no key is tolerated.

    **LD-704 discharged the only one there was** (the LD-650 key, extended under LD-658 and
    LD-674). The rule below and its ledger are KEPT, transformed rather than deleted
    (supersession § A.1): a future retirement that declares a window again meets the same
    three arms the day it lands. While none is declared, the arms are exercised on the newest
    window the ledger ever authorised — a fixed historical release, so no version literal is
    typed and nothing moves under a cut.
    """
    import larkdocio.read.config as config_module

    return getattr(config_module, "RETIRED_OUTPUT_KEYS_TOLERATED_IN", None)


def _window_under_test():
    declared = _declared_window()
    if declared is not None:
        return declared
    return ".".join(str(part) for part in max(TOLERANCE_AUTHORIZATIONS))


def _version_tuple(v):
    return tuple(int(part) for part in v.split("."))


def _release_note_sections():
    """Every release the notes carry a section for — derived, never a literal."""
    from pathlib import Path

    from release_versions import section_starts

    notes = (Path(__file__).resolve().parents[1] / "RELEASE_NOTES.md")
    return [version for version, _date, _i in section_starts(
        notes.read_text(encoding="utf-8").splitlines())]


#: **The tolerance window's authorisation ledger — LD-671 AC3, option (b).**
#:
#: Each row is ``(major, minor, patch) -> the issue that authorised the window``. Moving the
#: window means adding a row, which means naming the decision in the diff.
#:
#: **The judgement, and why the other two options lose.** LD-671 § 3 offered three ways to give
#: the tolerance a real limit:
#:
#: * *(a) a hard expiry* — "at most N extensions", or "within N releases of packaged". Rejected:
#:   N is a deadline nobody agreed to, and larkdocio's version numbers carry **no** major/minor
#:   semantics (maintainer directive), so "within N releases" is a distance in an arbitrary unit. A
#:   deadline invented by a guard is the kind of rule that gets raised rather than met.
#: * *(c) accept indefinite extensibility and say so* — honest, and it gives up the thing
#:   ``read/config.py``'s own comment promises ("discharge in the SAME change"). Rejected
#:   because a documented ratchet-with-no-teeth is still no teeth, and the cost of (b) is one
#:   line.
#: * **(b) require an extension to cite an authorising issue — CHOSEN.** It invents no deadline,
#:   costs a Dev one row, and makes each deferral **visible in the diff and attributable**: the
#:   next reader asking "why is this still tolerated three releases later" gets three issue ids
#:   instead of a constant that drifted.
#:
#: What it does NOT claim: this cannot stop a determined extension, and it is not meant to. It
#: converts a silent one into a recorded one. Guard (ii) below cannot do that job — it is
#: satisfied by every cut release **by construction**, because cutting a release creates its
#: notes section; all it forbids is an invented far-future version like ``9.9.9``.
#:
#: Written as tuples of ints, not ``"X.Y.Z"`` strings, and that is not a style choice: a bare
#: string equal to the packaged version is exactly what ``tests/test_version_bump_tolerance.py``
#: forbids, and a ledger of version windows must not itself be the landmine it records.
TOLERANCE_AUTHORIZATIONS = {
    (1, 49, 0): "LD-650",      # declared the window when the retirement was disclosed
    (1, 51, 0): "LD-658",      # extended it: the removal announced for 1.50.0 did not happen
    (1, 52, 0): "LD-674",      # extended it again: the v1.52.0 cut shipped a notice naming
                               # 1.51.0, so this bought a TRUE notice now; the discharge (a
                               # consumer break) was deferred under the same issue, and
                               # LD-704 (which absorbed it) took it: no window is declared now
}


def _tolerance_window_refusals(tolerated, running):
    """**The whole rule the tolerance constant lives under, in ONE place.**

    Returns a tuple of refusals — empty means the window is sound. Every guard below calls
    this rather than restating a comparison, which is the LD-671 AC0 correction: the test that
    asserted the rule's *prediction* used to inline its own copy of the predicate, so it went on
    passing whatever the real rule became, and (being two tautologies of tuple comparison) it
    also passed for every possible constant — ``0.0.1``, ``9.9.9``, ``77.0.0`` all included.

    All three arms are reported, not short-circuited, so each can be probed on its own; a rule
    that stopped at the first failure could only ever be exercised through its first arm.
    """
    refusals = []
    if _version_tuple(tolerated) < _version_tuple(running):
        refusals.append(
            f"the tolerance notice names {tolerated} while the running release is {running}, "
            f"so every caller is told the key was removed in a release where it is still being "
            f"tolerated. Either DISCHARGE the tolerance (remove the key and the placeholder "
            f"field together — see read/config.py's positional-rebind note) or EXTEND the "
            f"constant to {running} or later, with the reason recorded in the notes.")
    sections = _release_note_sections()
    if not sections:
        refusals.append(
            "the release notes carry no sections at all — this rule cannot check the window it "
            "is asked about, which is a failure and not a pass.")
    elif tolerated not in sections:
        refusals.append(
            f"the tolerance window names {tolerated}, which the release notes carry no section "
            f"for. A window pointing at a release nobody is cutting is a deferral, not a "
            f"decision. Sections present: {sections[:5]}…")
    if _version_tuple(tolerated) not in TOLERANCE_AUTHORIZATIONS:
        refusals.append(
            f"the tolerance window names {tolerated}, which no row of "
            f"TOLERANCE_AUTHORIZATIONS authorises. Extending the window is a DEFERRAL of the "
            f"retirement read/config.py promises to discharge 'in the SAME change'; it may be "
            f"taken, but not silently. Add "
            f"`{_version_tuple(tolerated)}: \"LD-NNN\"` naming the issue that decided it.")
    return tuple(refusals)


def test_ac4_the_tolerance_NOTICE_can_never_name_a_release_older_than_the_one_running():
    """**LD-658 AC3 — the guard the constant never had.**

    The notice tells a caller the key is *"accepted-and-ignored in larkdocio X and removed in
    the release after it"*. That sentence is a **falsehood** the moment ``X`` is older than the
    release the caller is running: at ``1.50.0`` the constant still read ``1.49.0``, so a
    1.50.0 caller was told the removal had already happened in the very release where the key
    was still being tolerated. Nothing tied the two together, which is why a deliberate
    extension (disclosed in the notes) left the runtime message behind.

    The invariant is one-sided on purpose. ``>=`` permits a deliberate forward extension — the
    tolerance window may be re-declared for a future release with the reason recorded — and
    forbids only the drift into the past. What it guarantees is that **the first bump PAST the
    release this constant names** forces the decision, and the fix is then either discharging
    the tolerance or extending the constant on purpose.

    **The bump the constant names is deliberately NOT the one that reddens**, and that is what
    makes the guard cut-tolerant: ``scripts/release.sh`` gates at step 3 and bumps at step 7, so
    a guard that reddened on the named release would fail on a trunk whose gates had just
    passed — the LD-316 / LD-652 landmine. No version is quoted in this sentence, because a
    version quoted in prose is the same photograph in a different frame; the prediction is
    asserted executably by
    ``test_ac4_the_tolerance_guards_PREDICTION_is_asserted_rather_than_narrated`` below, so it
    cannot rot the way an earlier draft of this docstring did (it claimed the *named* release
    reddens, which is executably false — the LD-658 fix round caught it).
    """
    from larkdocio import __version__

    tolerated = _declared_window()
    if tolerated is not None:
        assert _tolerance_window_refusals(tolerated, __version__) == (), (
            _tolerance_window_refusals(tolerated, __version__))
    # ...and the not-older arm is LIVE, not merely satisfied: a window behind the running
    # release is refused, and refused with the sentence that names the fix.
    behind = _tolerance_window_refusals("0.0.1", __version__)
    assert any("still being" in refusal for refusal in behind), behind


def test_ac4_the_tolerance_window_names_a_RELEASE_THAT_EXISTS_or_is_being_cut():
    """The second arm of the rule, and the one that keeps ``>=`` from being an escape hatch.

    ``>=`` alone could be satisfied forever by writing ``9.9.9`` — a deferral dressed as a
    decision. So the constant must also name a release the **release documents themselves carry a
    section for**: a shipped one, or the one being cut (``tests/release_versions.py``'s
    ``AHEAD_ALLOWANCE`` of one, which is the same allowance the notes run on and the reason the
    constant may legitimately sit one ahead of the packaged version — ``scripts/release.sh``
    gates before it bumps, so a constant equal to the packaged version is stale the instant the
    bump lands, which is the LD-316 / LD-652 landmine).

    **What this arm does NOT do, stated because its docstring used to imply otherwise** (LD-671
    AC3): it is satisfied by every cut release **by construction** — cutting a release creates
    its notes section — so it bounds the window's *plausibility*, never its *lifetime*. Paired
    with a one-sided ``>=`` it would leave the tolerance extensible one line per release,
    forever. The limit on that is the third arm, :data:`TOLERANCE_AUTHORIZATIONS`.

    Derived from the file, never a literal: a version string typed here would itself become that
    landmine the moment it was cut (``tests/test_version_bump_tolerance.py``).
    """
    from larkdocio import __version__

    tolerated = _window_under_test()

    assert _release_note_sections(), "the release notes carry no sections — a vacuous guard"
    assert _tolerance_window_refusals(tolerated, tolerated) == (), (
        _tolerance_window_refusals(tolerated, tolerated))
    # LIVE: the far-future escape this arm exists to close is actually refused. `9.9.9` is a
    # synthetic in a major nobody will package, so it can never be the packaged version.
    invented = _tolerance_window_refusals("9.9.9", __version__)
    assert any("no section for" in refusal for refusal in invented), invented


@private_tree.citations
def test_ac3_extending_the_tolerance_window_must_CITE_the_issue_that_authorized_it():
    """**LD-671 AC3, option (b) — the arm that gives the ratchet teeth.**

    Guards (i) and (ii) permit the window to be moved forward one line per release, forever,
    with nothing recording that a decision was taken; the reasoning for choosing this over a
    hard expiry or a documented shrug is at :data:`TOLERANCE_AUTHORIZATIONS`.

    Three things are checked, and the last two are what stop the ledger becoming a formality:
    the current window is authorised; every id is a real ``LD-NNN``; and every id names an issue
    file that exists on the board, so a row cannot cite a number nobody ever filed.
    """
    import re
    from pathlib import Path

    tolerated = _window_under_test()

    assert TOLERANCE_AUTHORIZATIONS, "an empty ledger would authorise nothing and refuse nothing"
    assert _tolerance_window_refusals(tolerated, tolerated) == (), (
        _tolerance_window_refusals(tolerated, tolerated))

    board = Path(__file__).resolve().parents[1] / "progress"
    assert board.is_dir(), f"{board} is not readable — this arm cannot check, so it fails"
    for window, issue in sorted(TOLERANCE_AUTHORIZATIONS.items()):
        assert re.fullmatch(r"LD-\d+", issue), (window, issue)
        assert list(board.rglob(f"{issue}-*.md")), (
            f"{issue} authorises the {window} window but no issue file by that id is on the "
            f"board — a citation nobody can follow is not an authorisation.")

    # LIVE: a window nothing authorises is refused. Derived — the newest release the notes
    # carry that the ledger does NOT list — so no version literal is typed here.
    unauthorized = next(
        (v for v in _release_note_sections()
         if _version_tuple(v) not in TOLERANCE_AUTHORIZATIONS), None)
    assert unauthorized, "every released version is in the ledger — this arm cannot be probed"
    refusals = _tolerance_window_refusals(unauthorized, "0.0.1")
    assert any("TOLERANCE_AUTHORIZATIONS" in refusal for refusal in refusals), refusals


def test_ac4_the_tolerance_guards_PREDICTION_is_asserted_rather_than_narrated():
    """**LD-658 fix round, defect 4 — and LD-671 AC0, which found the fix inert.**

    The guard above used to *narrate* its own future in prose, and the narration was executably
    false: it said the release the constant names is the one that reddens, when that release is
    precisely the one that must stay GREEN (the cut-tolerance reason is in that docstring). So
    LD-658 asserted the prediction instead — with ``at_named >= named`` and
    ``not (named >= past_named)``, which are **tautologies of tuple comparison**. They hold for
    every constant that could ever be written (QA probed ``0.0.1``, ``9.9.9``, ``1.2.3`` and
    ``77.0.0``), and they were computed from an inlined copy of the predicate rather than the
    real one, so a drift in the rule could not reach them either.

    Both halves are corrected here: the rule is **invoked**
    (:func:`_tolerance_window_refusals`), and the boundaries are asserted **on its verdict**, so
    the test now says something a constant can falsify. It goes red for ``9.9.9`` — the exact
    escape LD-658 AC3 set out to close, and the constant the old form accepted.
    """
    tolerated = _window_under_test()

    named = _version_tuple(tolerated)
    # "the first bump PAST it" — derived by incrementing the last component, which is ordering
    # only; larkdocio's version numbers carry no major/minor semantics (maintainer directive), so this
    # is a NEXT VALUE for the comparison, never a claim about what the next release will be.
    past_named = ".".join(str(part) for part in named[:-1] + (named[-1] + 1,))

    assert _tolerance_window_refusals(tolerated, tolerated) == (), (
        "the release the constant names must stay GREEN — release.sh gates before it bumps, so "
        "reddening there would fail a trunk whose gates just passed (LD-316 / LD-652). Verdict: "
        f"{_tolerance_window_refusals(tolerated, tolerated)}")
    assert _tolerance_window_refusals(tolerated, past_named) != (), (
        "the first bump PAST the named release must REDDEN — otherwise the tolerance is "
        "extensible by inaction, which is the defect the guard exists to prevent")


def test_ac4_the_tolerance_guards_comparator_orders_versions_NUMERICALLY():
    """The guard above compares release strings; a lexical compare would call ``1.9.0`` newer
    than ``1.50.0`` and pass on exactly the drift it exists to catch. Exercised over synthetic
    values, so the arm is not vacuous while the real pair happens to be equal.

    The synthetic versions are deliberately in a major nobody will ever package: a literal equal
    to the CURRENT packaged version is what ``tests/test_version_bump_tolerance.py`` forbids,
    and a demonstration of the trap must not itself be the trap.
    """
    assert _version_tuple("9.50.0") > _version_tuple("9.9.0")
    assert _version_tuple("9.49.0") < _version_tuple("9.50.0")
    assert not _version_tuple("9.49.0") >= _version_tuple("9.50.0")
    assert "9.50.0" < "9.9.0", "if this ever fails, the lexical trap above stopped existing"


def test_ac4_NO_notice_is_emitted_once_the_tolerance_is_discharged(caplog):
    """TRANSFORMED (LD-674 AC3 → LD-704). This arm pinned the notice BY EMISSION so the
    sentence a caller read named the running release. The tolerance is discharged, so the true
    emission is none: the module declares no window and a config carrying an unknown key logs
    nothing. If a window is ever declared again, the arm reverts to its LD-674 form: the
    window must not be older than the running release."""
    from larkdocio import __version__

    tolerated = _declared_window()
    if tolerated is not None:
        assert _version_tuple(tolerated) >= _version_tuple(__version__), tolerated
        return
    with caplog.at_level("WARNING", logger="larkdocio"):
        OutputConfig.from_dict({"a_retired_switch": False})
    assert not [r for r in caplog.records if r.name == "larkdocio"], (
        [r.message for r in caplog.records])


def test_ac4_an_UNRETIRED_unknown_key_is_still_ignored_in_SILENCE(caplog):
    """The project's rule for an unknown key, which every retired key now falls under (LD-704):
    a typo earns no notice in config.json, and the constructor refuses it."""
    with caplog.at_level("WARNING", logger="larkdocio"):
        OutputConfig.from_dict({"image_dirr": "x"})
    assert not [r for r in caplog.records if "image_dirr" in r.message]
    with pytest.raises(TypeError):
        OutputConfig(image_dirr="x")


def test_ac4_no_routing_TOGGLE_flag_was_ever_added_to_the_cli():
    """The claim in the document is only true while it is true — so it is asserted over the
    real click params, in both spellings a flag would plausibly take."""
    opts = {
        opt
        for command in cli_group().commands.values()
        for param in command.params
        for opt in getattr(param, "opts", [])
    }
    assert not [o for o in opts if "routing" in o], sorted(opts)


# --------------------------------------------------------------------------- #
# AC5 — the six-key schema is a PROJECTION of OutputConfig, and it ships.       #
# --------------------------------------------------------------------------- #

def test_ac5_the_projection_covers_every_output_config_field_bidirectionally():
    projected = [row.name for row in config_schema()]
    fields = list(OutputConfig().to_dict())
    assert projected == fields, (
        "the schema is projected off OutputConfig's own fields, in declaration order"
    )


def test_ac5_every_projected_default_IS_the_dataclass_default():
    defaults = OutputConfig().to_dict()
    assert {row.name: row.default for row in config_schema()} == defaults


def test_ac5_AN_EXTRA_field_with_no_meaning_reddens_the_projection(monkeypatch):
    """The exit condition of a projection: a new key cannot ship undocumented. Proved by
    adding a field to what the projection reads, not by editing the shipped dataclass.
    (Named for the PROPERTY rather than for a field count, so retiring a key — LD-650 took
    the seventh — does not make the test's own name a lie.)"""
    extra = dict(OutputConfig().to_dict(), keep_html_comments=False)
    monkeypatch.setattr(caps_config_mod, "_output_config_defaults", lambda: extra)
    with pytest.raises(ValueError, match="keep_html_comments"):
        config_schema()


def test_ac5_a_meaning_for_a_field_that_does_not_exist_reddens_too(monkeypatch):
    monkeypatch.setattr(
        caps_config_mod,
        "CONFIG_KEY_MEANINGS",
        dict(CONFIG_KEY_MEANINGS, image_dir_v2="a key nobody declared"),
    )
    with pytest.raises(ValueError, match="image_dir_v2"):
        config_schema()


def test_ac5_the_render_carries_every_key_its_default_and_its_meaning():
    rendered = config_schema_markdown()
    for row in config_schema():
        assert f"`{row.name}`" in rendered
        assert f"`{json.dumps(row.default)}`" in rendered
        assert row.meaning.split(".")[0] in rendered


def test_ac5_a_changed_DEFAULT_moves_the_render_so_the_documents_go_red(monkeypatch):
    """The defaults are held against the dataclass rather than typed twice: change one and the
    projection — and therefore both documents' regions — no longer match."""
    before = config_schema_markdown()
    monkeypatch.setattr(
        caps_config_mod,
        "_output_config_defaults",
        lambda: dict(OutputConfig().to_dict(), title_as_filename=False),
    )
    after = config_schema_markdown()
    assert before != after
    assert "| `title_as_filename` | `false` |" in after
    assert "| `title_as_filename` | `true` |" in before
    assert region_of(guide(full=True), CONFIG_REGION_BEGIN, CONFIG_REGION_END) != after, (
        "a changed default must leave the shipped region disagreeing with the projection"
    )


def test_ac5_the_GUIDE_carries_the_generated_region_byte_identically():
    region = region_of(guide(full=True), CONFIG_REGION_BEGIN, CONFIG_REGION_END)
    assert region, "the shipped guide carries no generated config-schema region"
    assert region == config_schema_markdown(), (
        f"the guide's config-schema region is stale — regenerate with: {CONFIG_REGENERATE}"
    )


def test_ac5_TOOLS_MD_carries_THE_SAME_generated_region():
    """One authored copy, two projections — the repo-side CLI contract and the shipped guide
    cannot disagree about a key, a default or what it does."""
    region = region_of(TOOLS_MD.read_text(encoding="utf-8"), CONFIG_REGION_BEGIN, CONFIG_REGION_END)
    assert region == config_schema_markdown(), (
        f"TOOLS.md's config-schema region is stale — regenerate with: {CONFIG_REGENERATE}"
    )


def test_ac5_there_is_exactly_ONE_authored_table_of_the_keys():
    """The hard constraint. Both documents' tables are the same generated bytes, so a hand-kept
    second table would show up as a key row OUTSIDE the region."""
    for label, text in (
        ("the shipped guide", guide(full=True)),
        ("TOOLS.md", TOOLS_MD.read_text(encoding="utf-8")),
    ):
        region = region_of(text, CONFIG_REGION_BEGIN, CONFIG_REGION_END)
        outside = text.replace(region, "")
        # DERIVED over every key rather than pinned to one (LD-650 retired the key this arm
        # used to name). A "schema row" is the generated shape — the key backticked in
        # column one and its JSON default backticked in column two — so a prose table that
        # happens to mention a key in a sentence is not mistaken for a second schema table.
        rows = [
            line
            for line in outside.splitlines()
            if any(
                line.startswith(f"| `{key}` | `{json.dumps(default)}` |")
                for key, default in OutputConfig().to_dict().items()
            )
        ]
        assert not rows, f"{label} carries a second, hand-kept schema table row: {rows}"


def test_ac5_the_example_file_in_the_region_IS_the_packaged_config_json():
    """The example is the real default file, so it cannot drift from what the wheel ships."""
    rendered = config_schema_markdown()
    fenced = re.search(r"```json\n(.*?)```", rendered, re.DOTALL)
    assert fenced, "the region must show an example config.json"
    packaged = (REPO_ROOT / "src" / "larkdocio" / "config.json").read_text(encoding="utf-8")
    assert json.loads(fenced.group(1)) == json.loads(packaged)
    assert json.loads(fenced.group(1)) == Config().to_dict()


def test_ac5_the_schema_is_reachable_from_the_PACKAGED_guide_alone():
    """The reach claim, from the accessor a wheel-only consumer has: every key, its default,
    and the shape of the file, with no repository on the path."""
    text = guide(full=True)
    for key, default in OutputConfig().to_dict().items():
        assert f"`{key}`" in text
        assert f"`{json.dumps(default)}`" in text
    assert '"output"' in text


# --------------------------------------------------------------------------- #
# AC6 — the README's dead TOOLS.md pointers, and the ratchet's exit condition.  #
# --------------------------------------------------------------------------- #

def test_ac6_tools_md_has_LEFT_the_citation_debt_ratchet():
    """*"A fixed citation must leave this table"* — the ratchet's own stated exit condition, so
    the entry's removal IS the proof the debt was paid."""
    from test_consumer_first_readme import _COUNTED_CLASSES

    assert not [cls for cls in _COUNTED_CLASSES if "TOOLS.md" in cls[1]], (
        "TOOLS.md is still recorded as citation debt"
    )
    assert _COUNTED_CLASSES, "the ratchet must not have been emptied wholesale"


def test_ac6_the_ratchet_STILL_BITES_if_a_TOOLS_MD_citation_returns_to_the_consumer_half():
    """The entry could have been deleted from a guard that stopped biting. It has not: the
    label-blind check reports a re-added citation in the real consumer half."""
    consumer, _dev = fd.split_at_development_heading(README_MD.read_text(encoding="utf-8"))
    assert not fd.unshipped_citations(consumer), "the consumer half must be clean to start"
    reinjected = consumer + "\nSee [`TOOLS.md`](TOOLS.md) for the config schema.\n"
    assert [raw for _n, raw in fd.unshipped_citations(reinjected)] == ["TOOLS.md"]


def test_ac6_the_consumer_facing_config_option_points_at_something_a_WHEEL_reader_can_open():
    """The pointer that sent a consumer looking up a consumer-facing option into the developer
    half. It must now name a packaged home."""
    consumer, _dev = fd.split_at_development_heading(README_MD.read_text(encoding="utf-8"))
    bullet = readme_bullet("- `--config`")
    assert bullet in consumer, "the --config bullet must stay in the consumer half"
    assert "Developing larkdocio" not in bullet and "#developing-larkdocio" not in bullet, (
        f"the --config bullet still sends a consumer into the developer half: {bullet}"
    )
    assert "larkdocio guide" in bullet or "larkdocio.guide()" in bullet, (
        f"the --config bullet must name the packaged document that carries the schema: {bullet}"
    )


def test_ac6_the_output_option_bullet_names_route_and_carries_the_double_nesting_warning():
    """The other half of the same rot: the README described ``-o`` the way the help string did.
    Since LD-650 the thing it must send the reader to is ``--route`` rather than a derived
    subpath — the double-nesting hazard is unchanged, only its cause moved to the caller."""
    bullet = flat(readme_bullet("- `-o`"))
    assert "--route" in bullet
    assert "double-nest" in bullet


def test_ac6_the_reference_docs_pointer_names_the_packaged_home_of_the_schema():
    text = README_MD.read_text(encoding="utf-8")
    _consumer, dev = fd.split_at_development_heading(text)
    bullet = readme_bullet("- [`TOOLS.md`]")
    assert bullet in dev, "TOOLS.md is still the repo-side CLI contract and stays cited there"
    assert "guide" in flat(bullet), (
        "the reference-docs pointer must say where a wheel reader reads the schema instead"
    )


def test_ac6_the_help_pages_and_the_guide_are_all_in_the_guarded_corpus():
    """The strings this issue changed are consumer-reaching, so they are swept for dialect by
    the existing corpus guard — asserted here so a later corpus narrowing is visible."""
    pages = cli_help_pages()
    assert "larkdocio download --help" in pages
    assert "root" in pages["larkdocio download --help"].lower()




# --------------------------------------------------------------------------- #
# LD-650 round 2 — NO SHIPPED DOCUMENT STATES THE SCHEMA'S SIZE AS A CARDINAL. #
# --------------------------------------------------------------------------- #

#: A bare cardinal attached to keys/fields — "the identical seven keys", "its 7-key schema",
#: and "the 7 `OutputConfig` fields", which is why ONE intervening token is allowed: the real
#: shipped sentence put a backticked type name between the number and the noun, and a pattern
#: without that hole matched none of it. (Found by red-watching the arm against the exact
#: sentence it was written for — reading it, it looked right.)
_CARDINAL_KEYS = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)[- ]"
    r"(?:[`\w.()]+[ ])?(keys?|fields?)\b",
    re.IGNORECASE,
)

#: Narrowed to THIS subject, deliberately. A repo-wide cardinal ban would be noise; what rots
#: is a hand-typed count of a GENERATED table sitting next to it.
_CONFIG_SUBJECT = re.compile(r"config\.json|OutputConfig", re.IGNORECASE)

#: Every document that publishes the config schema: the shipped guide, the wheel's METADATA
#: body, and the repo-side CLI contract that carries the twin generated region.
_SCHEMA_PUBLISHERS = (
    REPO_ROOT / "src" / "larkdocio" / "GUIDE.md",
    REPO_ROOT / "README.md",
    TOOLS_MD,
)


@pytest.mark.parametrize("path", _SCHEMA_PUBLISHERS, ids=lambda p: p.name)
def test_no_shipped_document_states_the_schema_size_as_a_hand_typed_CARDINAL(path):
    """The schema table is GENERATED; a cardinal beside it is hand-kept, and it rots on the
    first key added or retired. Four sites shipped saying "seven" while the dataclass declared
    six — one of them in `README.md`, which IS the wheel's `METADATA` body on PyPI, and two of
    them a line or two above the generated table that already showed the truth.

    This project's staleness rule is that a number in a document presenting itself as current
    is **derived, dated, or not stated**. A count of a generated table has a fourth option that
    is better than all three: point at the table. So the assertion is that the cardinal is
    absent, not that it is correct — a correct cardinal is simply the same defect with a
    shorter fuse.
    """
    # The subject is matched over a WINDOW, not the matched line alone: these documents are
    # hard-wrapped prose, and the guide's own site had `OutputConfig` on the line ABOVE the
    # cardinal — a same-line context made this arm pass on the exact sentence it was written
    # for (caught by red-watching it, not by reading it).
    # BOTH halves are matched across the WRAP, because these documents are hard-wrapped prose
    # and this arm was written for sentences that straddle a line break. Red-watching found
    # two separate ways a same-line read went vacuous on the very sites it exists for: the
    # guide had `OutputConfig` on the line ABOVE its cardinal, and TOOLS.md ends a line on
    # "the 7" with "`OutputConfig` fields" beginning the next. A guard that reads one physical
    # line is a guard for text nobody wrapped.
    lines = path.read_text(encoding="utf-8").splitlines()
    offenders = []
    for i, line in enumerate(lines, 1):
        head = re.sub(r"\s+", " ", line)
        probe = re.sub(r"\s+", " ", " ".join(lines[i - 1:i + 1]))
        # A match BEGINNING on this line — so a claim split over the break is caught once,
        # attributed to the line the cardinal is on.
        if not any(m.start() < len(head) for m in _CARDINAL_KEYS.finditer(probe)):
            continue
        window = "\n".join(lines[max(0, i - 3):i + 2])
        if _CONFIG_SUBJECT.search(window):
            offenders.append((i, line.strip()[:110]))
    assert offenders == [], (
        f"{path.name} states the config schema's size as a hand-typed cardinal at "
        f"{offenders}. Name the generated table instead — it cannot disagree with the code."
    )
