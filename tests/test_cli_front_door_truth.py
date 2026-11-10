# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-208 — THE CLI FRONT DOOR TELLS THE TRUTH, and `guide` becomes a subcommand.

Why this module exists
----------------------
``larkdocio --help`` said *"Download lark document to markdown file"* — true at v1.0.0 and
false for twenty-two releases, through a writer, a Sheets read+write surface, a comments
reader, Markdown authoring, mermaid compilers, a capability registry, a packaged consumer
guide, a permissions registry and an advisory preflight. Two consumer reviews in a row raised
it. It was the last front door nothing held against the code, and the asymmetry was the worst
part: every other door had been fixed *structurally*, so a reader who trusts the guarded
surfaces has no reason to distrust this one.

**A sentence is what rotted, so a sentence is not what this guards.** The group help carries a
SURFACE ROLL — the ids ``capabilities()`` reports — and the roll is held against the live
registry **in both directions**: a surface added to the registry with no mention reddens, and
a mentioned surface that does not exist reddens. The read-only doctrine gets the same
treatment: the page says the CLI never writes, and the claim is falsifiable, because the write
engine's own address in the source tree is derived from the registry and no command handler
may reach it.

The rest is discoverability, each with the guard that keeps it:

* ``larkdocio guide`` prints the packaged guide, byte-for-byte, from an **installed wheel** —
  the one claim a repo-only test can pass while the shipped artifact fails;
* ``larkdocio.preflight`` is exported and indexed under ``capabilities()["entry_points"]``
  (**not** ``["docs"]``, which is the packaged-document index and is asserted here to be
  unchanged);
* the guide meets ``preflight`` in its credentials section and carries the re-convert warning
  in the download recipe — both located **structurally**, by section, not by a substring
  anywhere in 3,000-odd lines.

Pure helpers live in ``tests/front_door.py``; every mutation below is driven through the real
render or the real text, never over a hand-built stand-in of it.
"""
import json
import pathlib
import re
import subprocess
import sys

import pytest

import private_tree  # noqa: E402  (LD-691)

import consumer_text
import front_door as fd
import larkdocio
from consumer_text import cli_group, dialect_hits
from larkdocio import capabilities
from larkdocio.cli import cli
from test_index_ratio import is_index_sized  # LD-640 AC5: one spelling of the 20x ratio

# LD-370 — CONFORMANCE-tier: the CLI's own --help text is a consumer-observable contract.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Shared readers                                                               #
# --------------------------------------------------------------------------- #

def _guide_section(heading, text=None):
    """The guide text from ``heading`` up to the next heading of the same level or higher.

    Structural location is the whole point of the AC5 / AC6 guards: *"somewhere in the
    document"* is what a full-text search already gave the consumer who could not find
    ``preflight``, and it is not what either claim owes a reader.

    **Fenced blocks are skipped when looking for the next heading.** Both sections this reader
    is aimed at open with a shell block whose first line is a ``# comment`` — a heading-shaped
    line that is not a heading — so a fence-blind scan ends the section three lines in and the
    guard silently checks almost nothing.
    """
    text = larkdocio.guide(full=True) if text is None else text
    level = len(heading) - len(heading.lstrip("#"))
    start = text.find(heading)
    assert start != -1, f"the guide has no {heading!r} section"
    lines = text[start + len(heading):].split("\n")
    inside, end = False, len(lines)
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside and re.match(rf"#{{1,{level}}} ", line):
            end = index
            break
    return heading + "\n".join(lines[:end])


_CREDENTIALS_HEADING = "## Credentials & `.env` setup — the READ / WRITE app split"
_DOWNLOAD_RECIPE_HEADING = "### Recipe: download a docx to Markdown"

#: What the credential/setup path owes a reader about ``preflight`` — the doctrine from
#: ``preflight``'s own module docstring: advisory, never mandatory, and it says what it costs
#: before you spend it. A gate is exactly what it must not read as.
_PREFLIGHT_CLAIMS = (
    "larkdocio.preflight.check_permissions",
    "advisory",
    "never",
    "call_cost",
)

#: The re-convert warning in the review's own terms. These three are the CONTENT of the
#: warning, not a house phrasing: what to do (re-convert), and the two renderer improvements
#: the review actually got mixed into a content diff.
_RECONVERT_CLAIMS = ("re-convert", "linkified", "rowspan")


def _preflight_gaps(text):
    """Which of the preflight claims ``text`` fails to make."""
    lowered = text.lower()
    return [claim for claim in _PREFLIGHT_CLAIMS if claim.lower() not in lowered]


def _reconvert_gaps(text):
    """Which of the re-convert warning's claims ``text`` fails to make."""
    lowered = text.lower()
    return [claim for claim in _RECONVERT_CLAIMS if claim.lower() not in lowered]


def _rendered():
    """The freshly rendered ``larkdocio --help`` page (re-rendered on every call, so a
    monkeypatched docstring or option really is what the guard reads)."""
    return consumer_text.cli_help_pages()["larkdocio --help"]


# =====================================================================
# AC1 — the group docstring tells the truth, DERIVED against capabilities()
# =====================================================================

def test_ac1_the_group_help_names_every_surface_the_registry_reports():
    """Forward leg: what the install can do ⊆ what the first screen says it can do."""
    missing, _phantom = fd.surface_roll_diff(_rendered())
    assert not missing, (
        "the first screen of `larkdocio --help` never names these surfaces, so a reader who "
        f"reads only it thinks the library cannot do them: {missing}"
    )


def test_ac1_the_group_help_names_no_surface_that_does_not_exist():
    """Reverse leg over the real page: the roll cannot advertise a surface the install lacks."""
    _missing, phantom = fd.surface_roll_diff(_rendered())
    assert not phantom, (
        f"`larkdocio --help` claims surfaces the registry does not report: {phantom}"
    )


def test_ac1_a_surface_ADDED_to_the_registry_reddens_the_help_page():
    """Direction one, proven: the derivation is against the live registry, so a new surface
    family widens what the help owes a reader with nobody editing a word list."""
    # LD-251: ``base-read`` became REAL (and is named on the page), so the probe moved to a
    # surface id the registry does not have — the probe must be a surface nobody documented.
    invented = "telepathy-read"
    assert invented not in fd.surface_ids(), "the probe is stale; pick an id that is fake"
    grown = fd.surface_ids() | {invented}
    missing, phantom = fd.surface_roll_diff(_rendered(), grown)
    assert missing == [invented] and not phantom


def test_ac1_a_surface_the_registry_no_longer_HAS_reddens_as_a_phantom():
    """Direction two, proven: a surface that goes away leaves the page making a false claim,
    and the guard reports it rather than shrugging."""
    real = fd.surface_ids()
    shrunk = real - {"sheets-write"}
    missing, phantom = fd.surface_roll_diff(_rendered(), shrunk)
    assert phantom == ["sheets-write"] and not missing


def test_ac1_the_required_ids_come_out_of_the_registry_not_a_literal_in_this_file():
    """The anti-rot check: the left-hand side is the registry itself."""
    assert fd.surface_ids() == set(capabilities(full=True)["surfaces"])
    assert len(fd.surface_ids()) >= 6


def test_ac1_no_surface_id_is_BROKEN_by_clicks_line_wrapping():
    """The roll is only a derivation if the page really contains the ids: click rewraps
    paragraphs, and a hyphenated id split across two lines would silently read as two
    unknown tokens. The ``\\b`` no-rewrap marker is what prevents that, and this is what
    proves the marker is still doing its job in the RENDERED page."""
    page = _rendered()
    for surface_id in sorted(fd.surface_ids()):
        assert surface_id in page, (
            f"{surface_id!r} does not appear intact in the rendered page — click's wrapping "
            f"broke it, so the surface roll is no longer readable by a human either"
        )


def test_ac1_the_help_ALSO_covers_the_surface_words_the_wheel_Summary_owes():
    """The same requirement the ``Summary`` carries, applied to the other first screen — so the
    two front doors cannot disagree about which surfaces exist."""
    assert fd.description_surface_gaps(_rendered()) == []


def test_ac1_reverting_the_docstring_to_the_OLD_SENTENCE_reddens(monkeypatch):
    """THE mutation this issue exists for, driven through the real click render: restore the
    v1.0.0 sentence and every surface the registry reports goes unnamed."""
    monkeypatch.setattr(cli_group(), "help", "Download lark document to markdown file")
    missing, _phantom = fd.surface_roll_diff(_rendered())
    assert sorted(missing) == sorted(fd.surface_ids()), (
        "the old one-line docstring did not redden the surface-roll guard, which means the "
        "guard would not have caught the defect it was written for"
    )


# --------------------------------------------------------------------------- #
# AC1 — and the CLI stays READ-ONLY and SAYS SO (the maintainer ruling, guarded)         #
# --------------------------------------------------------------------------- #

def test_ac1_the_help_page_says_WHICH_commands_read_and_WHICH_ONE_writes():
    """TRANSFORMED BY LD-492 — the conclusion moved, the reason did not.

    This asserted the group page said the command line *never writes*. That claim became false
    the moment ``roundtrip`` shipped, and a claim a reader can disprove in one invocation is
    worse than no claim. So the page now owes the **finer** statement the old one was a coarse
    approximation of: name the one verb that writes, and say plainly that the reading verbs do
    not — because the **reason** the old sentence existed is untouched, and it is that *a
    download must never be able to mutate the document it is reading*.

    Whitespace-normalized, because click rewraps the paragraph."""
    page = " ".join(_rendered().split()).lower()
    assert "roundtrip push --apply" in page, (
        "the group help does not name the one command that writes to Lark — a reader cannot "
        "tell which verb is the dangerous one"
    )
    assert "exactly one command here writes" in page, (
        "the group help never says how many commands write, which is the fact that replaced "
        "'it never writes' — a reader left to count for themselves will guess"
    )
    assert "change nothing in lark" in page, (
        "the group help no longer says that the READING verbs write nothing — that half of "
        "the old doctrine is still true and is the half a reader needs before a download"
    )
    assert "never writes" not in page, (
        "the group help still carries the superseded blanket claim; it is false now, and a "
        "false sentence beside a true one is worse than either"
    )


def test_ac1_the_write_engine_is_REACHABLE_ONLY_THROUGH_THE_ONE_WRITING_VERB():
    """TRANSFORMED BY LD-492, and this is the guard that carries the reason forward.

    It asserted ``cli_write_reach() == []`` — *no* command handler may reach the write engine.
    One command now legitimately does, so the guard is re-pointed rather than struck: every
    path from ``larkdocio.cli`` into the write engine must pass through
    ``larkdocio.roundtrip``. Both halves stay falsifiable and both stay derived — the write
    engine's modules still come out of the registry's own ``projected_from`` paths, and the
    paths are still walked from the real import graph. **A write import added to `download`,
    `folder`, `config`, `guide` or `mermaid` reddens this**, which is precisely the defect the
    original guard existed to make impossible.
    """
    bypassing = fd.write_reach_paths_bypassing()
    assert bypassing == {}, (
        f"the command line reaches the write engine WITHOUT going through "
        f"{fd.CLI_WRITE_GATEWAY_MODULE}: {bypassing} — a second writing route is not what the "
        f"front door describes"
    )
    reached = fd.write_reach_paths()
    assert reached, (
        "no path into the write engine at all — the one writing verb has stopped reaching it, "
        "so either the verb was removed (say so at the front door) or this walk has gone slack"
    )


def test_ac1_the_reading_commands_own_handlers_reach_NO_write_module():
    """The per-command half, and the one that keeps `download` honest.

    The check above is about the whole `larkdocio.cli` module, which necessarily imports the
    writing verb. This one walks each READING command's own handler module — the code that
    actually runs when that command is invoked — and requires it to reach nothing in the write
    engine. `download` growing a write import reddens here even though `larkdocio.cli` is
    allowed one.
    """
    for handler in READING_HANDLERS:
        assert fd.module_source(handler) is not None, f"{handler} moved; re-point this guard"
        reached = fd.write_reach_paths(start=handler)
        assert reached == {}, (
            f"{handler} — a READING command's own handler — reaches the write engine "
            f"{sorted(reached)}. A download must never be able to mutate the document it is "
            f"reading; that is the reason the blanket claim existed and it did not change"
        )


#: The reading commands whose own handler module must reach no write module. Named once, so
#: the assertion and its own precondition below cannot drift apart.
READING_HANDLERS = ("larkdocio.read.download", "larkdocio.drive.folder_cmd",
                    "larkdocio.read.config_cmd", "larkdocio.mermaid", "larkdocio.guide")


#: A named start whose walk is LEGITIMATELY just itself, with the reason (LD-632 AC4).
#:
#: The precondition below turns "the walk found nothing" from a pass into a failure, and it
#: found a second vacuous arm besides the ``larkdocio.mermaid`` one this issue is about — but
#: this one is vacuous **for a real reason rather than as an artefact**: ``larkdocio.guide``
#: imports no ``larkdocio`` module at all. It reads a packaged text resource
#: (``importlib.resources``) and formats it; ``re`` and ``textwrap`` are the only other
#: imports. So "it reaches no write module" is a true and complete statement about it, not a
#: walk that gave up. The entry is held BIDIRECTIONALLY: give ``guide`` an intra-package
#: import and it stops being a leaf, this exemption reddens, and the reason must be re-earned.
HANDLERS_WITH_NO_LARKDOCIO_IMPORTS = {
    "larkdocio.guide": "reads a packaged text resource; it imports no larkdocio module",
}


@pytest.mark.parametrize("handler", sorted(HANDLERS_WITH_NO_LARKDOCIO_IMPORTS))
def test_ld632_a_LEAF_handlers_empty_walk_is_recorded_with_its_reason(handler):
    """LD-632 AC4 — the exemption is a recorded fact, not a silence."""
    assert handler in READING_HANDLERS
    assert fd._imported_larkdocio_modules(handler) == set(), (
        f"{handler} now imports larkdocio modules "
        f"({sorted(fd._imported_larkdocio_modules(handler))}) so it is no longer the leaf this "
        f"exemption asserts — drop the HANDLERS_WITH_NO_LARKDOCIO_IMPORTS entry and let the "
        f"non-vacuity precondition cover it"
    )
    assert fd.reach_from(handler) == {handler}


@pytest.mark.parametrize("handler", [h for h in READING_HANDLERS
                                     if h not in HANDLERS_WITH_NO_LARKDOCIO_IMPORTS])
def test_ld632_the_reach_walk_from_each_named_start_IS_NOT_VACUOUS(handler):
    """LD-632 AC4 — the precondition the five-arm assertion above was missing.

    ``larkdocio.mermaid`` is a **package**, and both walks skipped a module whose source is an
    ``__init__.py``. The skip was applied to the START as well as to interior nodes, so the
    walk from that handler visited exactly one node, followed none of its five submodules and
    returned ``{}`` — an arm that asserts ``reached == {}`` and can only ever see nothing.

    A start that resolves to nothing is now a FAILURE, not a pass. If a handler genuinely
    imports no ``larkdocio`` module, this is the test that says so out loud.
    """
    reached = fd.reach_from(handler)
    assert handler in reached
    assert len(reached) > 1, (
        f"the reach walk from {handler} visits only {handler} itself, so every assertion over "
        f"what it reaches is vacuous — either the walk is refusing to leave its own start, or "
        f"{handler} genuinely imports no larkdocio module, in which case say so in "
        f"HANDLERS_WITH_NO_LARKDOCIO_IMPORTS with the reason"
    )


def test_ld632_a_package_start_is_walked_THROUGH_so_a_submodules_reach_is_seen():
    """LD-632 AC7's watched red for Part B, kept as a permanent arm.

    The falsifier for the falsifier: point the walk at a package start and declare one of its
    own submodules forbidden. Before the fix this returned ``{}`` — proving the emptiness of
    the five-arm assertion was an artefact of the start being a re-export shelf and not a fact
    about the code. It must now report the path.
    """
    assert fd.module_source("larkdocio.mermaid").name == "__init__.py", (
        "larkdocio.mermaid is no longer a package — re-point this arm at one that is, or the "
        "shelf-as-start case stops being covered"
    )
    hits = fd.write_reach_paths(start="larkdocio.mermaid",
                                write_modules={"larkdocio.mermaid.ruleset"})
    assert "larkdocio.mermaid.ruleset" in hits, (
        "a package start's submodules are not reached, so a forbidden module sitting one import "
        "below a shelf handler is invisible to this guard"
    )
    assert hits["larkdocio.mermaid.ruleset"][0] == "larkdocio.mermaid", (
        "the reported chain must start at the walk's own start"
    )


def test_ld632_an_INTERIOR_shelf_is_still_not_walked_through():
    """LD-632 AC5 — the transformation's other half, and the reason it is not a relaxation.

    The ``__init__``-skip exists because *following a shelf would make every module reachable
    from every other one and the check would mean nothing*. That reason is **unchanged** and
    still binding for interior nodes: only the START is exempt. ``larkdocio.read.download``
    imports the bare ``larkdocio`` shelf, which re-exports ``write.compose``; if interior
    shelves were followed, ``download`` would "reach" the write engine through it and the
    whole guard would collapse into a tautology.
    """
    assert "larkdocio.sheets" in fd._imported_larkdocio_modules("larkdocio.read.download"), (
        "larkdocio.read.download no longer imports the larkdocio.sheets shelf — re-point this "
        "arm at a handler that imports an interior shelf, or the carve-out stops being covered"
    )
    assert fd.module_source("larkdocio.sheets").name == "__init__.py"
    assert "larkdocio.sheets.write_client" in fd._imported_larkdocio_modules("larkdocio.sheets")
    reached = fd.reach_from("larkdocio.read.download")
    assert "larkdocio.sheets" in reached, "the shelf is REACHED — that half never changed"
    assert "larkdocio.sheets.write_client" not in reached, (
        "an interior shelf was walked THROUGH: larkdocio.sheets re-exports its write engine "
        "beside the reader, so following it makes every module reachable from every other one "
        "and the read/write isolation check means nothing. Interior nodes keep the skip; only "
        "the start is exempt"
    )


def test_ac1_the_write_engine_ADDRESS_is_derived_from_the_registry():
    """Guard precondition: the forbidden set is real and comes from the write surfaces, so the
    test above cannot be passing because it is comparing against nothing. It also covers the
    re-export hole — the write-ONLY package counts, so importing the shelf is the same act."""
    modules = fd.write_surface_modules()
    assert {"larkdocio.write.ops", "larkdocio.write.client", "larkdocio.sheets.ops",
            "larkdocio.sheets.write_client"} <= modules
    forbidden = fd.forbidden_write_modules()
    assert "larkdocio.write" in forbidden, "the write-only package shelf is not counted"
    assert "larkdocio.sheets" not in forbidden, (
        "the mixed read+write sheets package must NOT be forbidden — the reader imports it, and "
        "a guard that fired on the reader would be deleted"
    )
    assert all(fd.module_source(name) is not None for name in forbidden)


@pytest.mark.parametrize("pretend_module", ["larkdocio.write.ops", "larkdocio.write",
                                           "larkdocio.sheets.write_client"])
def test_ac1_the_read_only_check_BITES_when_a_handler_reaches_the_write_engine(pretend_module):
    """The red proof, per shape: a handler chain that reaches the docx write ops, the write
    package shelf, or the Sheets write client — which is what a `larkdocio edit` would do.

    Driven over a **synthetic** reachable set rather than the real one, because since LD-492
    the real set legitimately contains write modules (the one writing verb reaches them). What
    is under test here is that the *matcher* bites, which is why both sides are injectable;
    the routing question — through which module — is
    :func:`test_ac1_the_write_engine_is_REACHABLE_ONLY_THROUGH_THE_ONE_WRITING_VERB`'s.
    """
    pretend = {"larkdocio.cli", "larkdocio.read.download", pretend_module}
    assert fd.cli_write_reach(pretend) == [pretend_module]


def test_ac1_the_reachability_walk_really_walks_the_handler_chain():
    """Guard precondition for the check above: the walk reaches the read path it should
    (so an empty result is a fact about the CLI, not about a broken walk), and it does not
    treat the package shelf as a hop."""
    reach = fd.cli_reachable_modules()
    for expected in ("larkdocio.cli", "larkdocio.read.download", "larkdocio.read.client",
                     "larkdocio.read.parser", "larkdocio.guide"):
        assert expected in reach, f"the walk never reached {expected}"
    # A shelf is REACHED but not walked THROUGH: `larkdocio/__init__` imports
    # `write.compose` so that `larkdocio.compose` exists, and following that would make every
    # module reachable from every other one.
    #
    # LD-492 RE-POINTED THE EXAMPLE, not the rule. The old witness was
    # `larkdocio.write.compose not in reach`, and it stopped witnessing anything the moment
    # the roundtrip verb imported `compose` by name — it is now reached for a real reason,
    # through the verb, not through the shelf. The Sheets pair below demonstrates the same
    # rule and nothing on the command line reaches it, so it is the witness that still works.
    assert "larkdocio" in reach
    assert "larkdocio.sheets" in reach and "larkdocio.sheets.write_apply" not in reach


# --------------------------------------------------------------------------- #
# LD-495 — the blanket claim cannot reappear anywhere under src/, ever         #
# --------------------------------------------------------------------------- #

def test_ld495_the_blanket_read_only_claim_is_gone_from_every_module_docstring():
    """The repo-wide grep guard LD-495 asks for: no live prose under ``src/`` may still assert
    the BLANKET *"the command line is read-only"* / *"...stays read-only"* — false since
    ``roundtrip push --apply`` shipped (LD-492). A **scoped** claim (a surface with no CLI route
    at all) is untouched by this guard; only the blanket phrasing is forbidden.

    ``CHANGELOG.md`` / ``RELEASE_NOTES.md`` are exempt **inside their cut, dated** ``##
    [x.y.z]`` **sections only** — a cut section is a historical record and must never be
    edited — via :func:`fd.stale_read_only_claims`.
    """
    offenders = fd.stale_read_only_claims()
    assert offenders == [], (
        "the superseded blanket read-only claim is still live in src/ outside a cut changelog "
        "section: "
        + "; ".join(f"{path}:{lineno}: {line!r}" for path, lineno, line in offenders)
    )


def test_ld495_the_guard_BITES_on_a_freshly_reintroduced_blanket_claim(tmp_path, monkeypatch):
    """The red proof: plant the exact superseded sentence in a throwaway module under a
    temporary ``src/`` tree and confirm the guard finds it — driven over an injected root so the
    real tree is never touched to prove the negative."""
    fake_src = tmp_path / "src" / "larkdocio" / "drive"
    fake_src.mkdir(parents=True)
    (fake_src / "reintroduced.py").write_text(
        '"""A module of its own — the command line is read-only and says so."""\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(fd, "REPO_ROOT", tmp_path)
    offenders = fd.stale_read_only_claims()
    assert offenders == [
        ("src/larkdocio/drive/reintroduced.py", 1,
         '"""A module of its own — the command line is read-only and says so."""'),
    ], f"the guard did not catch a freshly reintroduced blanket claim: {offenders}"


def test_ld495_the_guard_EXEMPTS_only_the_cut_dated_changelog_sections(tmp_path, monkeypatch):
    """Precondition for the guard's exemption, corrected by LD-502: a blanket claim inside a
    **cut** (closed, historical) ``## [x.y.z]`` section of ``CHANGELOG.md``/``RELEASE_NOTES.md``
    is exempt, but the same phrase sitting in the file's preamble OR its currently-open,
    un-cut topmost section is NOT — cut-ness starts at the file's **second** ``## [`` header,
    never its first, because the topmost section is normally still un-cut (LD-502: the old
    "first header" boundary wrongly exempted that open section too).
    """
    fake_root = tmp_path
    changelog_dir = fake_root / "src" / "larkdocio"
    changelog_dir.mkdir(parents=True)
    (changelog_dir / "CHANGELOG.md").write_text(
        "# Changelog\n"
        "the command line is read-only, said in the preamble before any release was cut.\n"
        "## [2.0.0] - 2026-08-17\n"
        "- open entry: the command line stays read-only, planted into the still-open section.\n"
        "## [1.0.0] - 2026-01-01\n"
        "- old entry: the command line stays read-only, quoted verbatim from that release.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fd, "REPO_ROOT", fake_root)
    offenders = fd.stale_read_only_claims()
    assert offenders == [
        ("src/larkdocio/CHANGELOG.md", 2,
         "the command line is read-only, said in the preamble before any release was cut."),
        ("src/larkdocio/CHANGELOG.md", 4,
         "- open entry: the command line stays read-only, planted into the still-open section."),
    ], f"exemption is not scoped to CUT sections only: {offenders}"


@pytest.mark.parametrize("filename", sorted(fd.STALE_READ_ONLY_CLAIM_EXEMPT_FILES))
def test_ld502_a_claim_freshly_injected_into_the_open_section_is_caught(
    tmp_path, monkeypatch, filename
):
    """AC1 — the defect, reproduced in-suite so it cannot return. A present-tense claim planted
    into the CURRENTLY-OPEN, un-cut topmost section of either notes file must be caught, naming
    the file and the line — this is exactly the miss QA reproduced in a tmp copy. Driven over an
    injected ``REPO_ROOT`` (``tmp_path``) so the real tree is never touched; ``git status
    --porcelain`` around this test stays empty (see the Handoff for the session-wide proof).
    """
    target = tmp_path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Notes\n"
        "## [2.0.0] — 2026-08-17\n"
        "- freshly injected: the command line is read-only, planted by this test.\n"
        "## [1.0.0] — 2026-01-01\n"
        "- old entry: the command line stays read-only, a historical record.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fd, "REPO_ROOT", tmp_path)
    offenders = fd.stale_read_only_claims()
    assert offenders == [
        (filename, 3,
         "- freshly injected: the command line is read-only, planted by this test."),
    ], f"a false claim planted into {filename}'s open section was not caught: {offenders}"


#: The canonical, COMPLETE document behind a packaged path. The sweep under test walks ``src/``
#: and keys its exemptions on the packaged paths, so those keys must not move — but the packaged
#: copies carry only a WINDOW of the newest releases, and both LD-492 supersession entries live
#: in ``## [1.37.0]``. LD-621 (**D-111**) is the cut that rolls that section off the window, with
#: nothing edited and nothing wrong. A cut, dated section in the root file is byte-identical to
#: the one that shipped, so the root document is where the "these two entries exist, unedited,
#: exactly twice" half is asserted PERMANENTLY; the wheel-facing half is kept for as long as it
#: can be true.
def _canonical_of(packaged_rel):
    return packaged_rel.split("src/larkdocio/", 1)[1]


@private_tree.internal_log
def test_ld502_the_two_ld492_supersession_entries_pass_unedited():
    """AC2 — with the tree exactly as it stands, the two legitimate LD-492 supersession entries
    — the ``CHANGELOG.md`` one and the ``RELEASE_NOTES.md`` one — report NO offender. Located by
    CONTENT via the guard's own quotation-exemption fragment, never a hard-coded line number (the
    issue's own caution: line numbers are as-of mint), so a later reflow of either file does not
    silently stop testing anything. These entries are never reworded to make this pass — the
    guard adapts to them, not the other way round.

    **TRANSFORMED (LD-621, ruled by D-111), and only the LOCATOR moved.** ``checked == 2`` is
    unchanged and is now asserted of the CANONICAL ROOT documents, which are complete and stay
    complete — so a reflow, a rewording or a deletion reddens with the full force it always had.
    The not-flagged arm still runs over the PACKAGED copies, because those are the paths the
    sweep under test walks; it asserts over whatever lines the window still carries, which is the
    only shape that can stay true across a cut.
    """
    offenders = {(path, lineno) for path, lineno, _ in fd.stale_read_only_claims()}
    checked = 0
    for rel, entries in fd.STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT.items():
        for source, packaged in ((_canonical_of(rel), False), (rel, True)):
            text = (fd.REPO_ROOT / source).read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(text, 1):
                if not fd.STALE_READ_ONLY_CLAIM.search(line):
                    continue
                if not any(fragment in line for _reason, fragment in entries):
                    continue
                if packaged:
                    assert (rel, lineno) not in offenders, (
                        f"{rel}:{lineno} is a legitimate LD-492 supersession quotation and must "
                        f"not be flagged: {line.strip()!r}"
                    )
                else:
                    checked += 1
    assert checked == 2, (
        f"expected to locate exactly the two known LD-492 supersession entries by content in "
        f"the canonical root documents, found {checked} — a reflow may have moved them out of "
        f"the allow-list's reach"
    )


@private_tree.internal_log
def test_ld502_the_quotation_exemption_allow_list_is_held_honest():
    """AC4 — LD-483-style: every quotation-exemption entry is checked against the shipped text
    it claims to describe. An entry's fragment must sit on a real
    :data:`fd.STALE_READ_ONLY_CLAIM` match line, and on EXACTLY ONE such line — a fragment that
    no longer matches has gone stale (the text moved); one matching more than one line is too
    generic to honestly identify a single quotation. Either way it must redden, so this
    allow-list cannot become the same hiding place LD-502 closes one level down.
    """
    for rel, entries in fd.STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT.items():
        assert rel in fd.STALE_READ_ONLY_CLAIM_EXEMPT_FILES, (
            f"{rel} carries a quotation exemption but is not one of the two exempt files"
        )
        canonical = _canonical_of(rel)
        root_lines = (fd.REPO_ROOT / canonical).read_text(encoding="utf-8").splitlines()
        packaged_lines = (fd.REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
        for reason, fragment in entries:
            assert fragment, f"entry with reason {reason!r} carries no fragment"
            assert len(reason) > 60, (
                f"entry fragment {fragment!r} carries too thin a reason to be LD-483-honest: "
                f"{reason!r}"
            )

            def _matches(lines):
                return [
                    lineno
                    for lineno, line in enumerate(lines, 1)
                    if fd.STALE_READ_ONLY_CLAIM.search(line) and fragment in line
                ]

            assert len(_matches(root_lines)) == 1, (
                f"{canonical}: quotation-exemption fragment {fragment!r} must bind to EXACTLY "
                f"ONE real STALE_READ_ONLY_CLAIM match line — found {_matches(root_lines)}. Zero "
                "means the authored text moved out from under it or it was never a real match; "
                "more than one means the fragment is too generic to be an honest, specific "
                "exemption."
            )
            # The wheel-facing arm, kept for as long as it can be true (D-111): the packaged
            # copy either still carries that quotation or the window has moved past the section
            # it was published in, and only ONE case is a defect — more than one match, which
            # is a fragment too generic to identify a single quotation no matter which copy it
            # is read in.
            assert len(_matches(packaged_lines)) <= 1, (
                f"{rel}: quotation-exemption fragment {fragment!r} binds to more than one real "
                f"STALE_READ_ONLY_CLAIM match line — found {_matches(packaged_lines)}"
            )


# --------------------------------------------------------------------------------------- #
# LD-502 round 2 — THE BINDING PROOF: the exemption is bound to the matched line itself,   #
# not a neighbourhood, so an unrelated false claim landing near a real quotation is CAUGHT #
# at every gap, including gap 0 (adjacent to the real quotation line).                     #
# --------------------------------------------------------------------------------------- #

#: How to find each file's real LD-492 quotation line, AND the real production markers QA's
#: pre-fix window keyed on, by CONTENT — never a hard-coded line number — so the sweep below
#: reproduces the actual vulnerability QA measured (CHANGELOG.md:71-73's "Superseded:" / "Each
#: now states"; RELEASE_NOTES.md:100-102's "said the command line is read-only" / "is false
#: now"), through an injected REPO_ROOT so the real tree is never touched.
#:
#: **LD-540 — ``source`` is the ROOT document, and the key stays the PACKAGED one.** The key is
#: the path the sweep under test reads (``fd.stale_read_only_claims()`` walks ``src/`` and keys
#: its exemptions on these two packaged paths), so it must not move — but the packaged copies now
#: carry only a WINDOW of the newest releases, and the real production context this sweep needs
#: lives in the ``## [1.37.0]`` section, which will roll off that window in a few releases with
#: no authored change at all. Locating the context by content in a windowed file is therefore a
#: fuse: it passes today and StopIterations the day the section leaves. The ROOT document is
#: complete and stays complete (LD-540 shape (A) windows only the packaged projection), and a
#: cut, dated section in it is byte-identical to the one that shipped — so reading the context
#: from the root is the SAME bytes, permanently, while the file under test stays the packaged
#: path. The lookup below is also fail-loud rather than fail-raw: a locator that stops matching
#: reports what it was looking for and why, instead of raising ``StopIteration`` out of a
#: generator.
_LD502_ROUND2_LOCATORS = {
    "src/larkdocio/CHANGELOG.md": dict(
        source="CHANGELOG.md",
        quote=lambda line: "layout table's" in line and "command line stays read-only" in line,
        # the quote line itself ends in "Each now states"; "Superseded:" sits two lines above.
        context_offsets=(-2, -1, 0),
        markers=("Superseded:", "Each now states"),
    ),
    "src/larkdocio/RELEASE_NOTES.md": dict(
        source="RELEASE_NOTES.md",
        quote=lambda line: "said the command line is read-only" in line,
        # the quote line itself carries the first marker; "is false now" is the next line.
        context_offsets=(0, 1),
        markers=("said the command line is read-only", "is false now"),
    ),
}


@pytest.mark.parametrize("filename", [
    # LD-691: the CHANGELOG locator reads the INTERNAL root log, where the quotation lives.
    pytest.param(f, marks=private_tree.internal_log) if f.endswith("CHANGELOG.md") else f
    for f in sorted(_LD502_ROUND2_LOCATORS)])
@pytest.mark.parametrize("gap", range(8))
def test_ld502_round2_a_new_false_claim_near_the_real_quotation_is_caught_at_every_gap(
    tmp_path, monkeypatch, filename, gap
):
    """THE BINDING PROOF. QA's FAIL (fresh eyes, bounded fix round): the pre-fix window-based
    exemption checked a +-5-line joined window around a candidate match for marker
    co-occurrence, so ANY stale-claim match landing near the real LD-492 markers was exempted —
    including a brand-new, unrelated false claim with nothing to do with the quotation. QA
    measured the pre-fix guard missing the injection at gap 0-4 and only catching it at gap>=5.

    This carries the REAL production context that contains the markers the old window keyed on
    (located by content in the COMPLETE ROOT document, never a hard-coded number and never the
    windowed packaged copy — see :data:`_LD502_ROUND2_LOCATORS` for why LD-540 makes that
    distinction load-bearing), then plants a genuinely new *"the command line is read-only"*
    claim at every gap 0..7 below it,
    inside the OPEN section, over an injected ``REPO_ROOT`` so the real tree is never touched.
    Asserts the new claim is CAUGHT at every single gap — including gap 0 — while the real
    quotation itself stays exempt throughout.
    """
    spec = _LD502_ROUND2_LOCATORS[filename]
    source = spec["source"]
    real_lines = (fd.REPO_ROOT / source).read_text(encoding="utf-8").splitlines()
    quote_idx = next(
        (i for i, line in enumerate(real_lines) if spec["quote"](line)), None
    )
    assert quote_idx is not None, (
        f"{source}: the real LD-492 quotation line this sweep plants next to could not be "
        f"located by content. This file is the COMPLETE root document (LD-540 reads the context "
        f"from the root, not from the windowed packaged copy at {filename}, precisely so a "
        f"section rolling off the window cannot break this proof), so the line has genuinely "
        f"moved or been edited — re-locate it and keep the sweep binding rather than skipping "
        f"it. The exemption it proves is still in "
        f"fd.STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT[{filename!r}]."
    )
    context_lines = [real_lines[quote_idx + off] for off in spec["context_offsets"]]
    joined_context = "\n".join(context_lines)
    assert all(marker in joined_context for marker in spec["markers"]), (
        f"{filename}: expected the real production markers {spec['markers']!r} in the captured "
        f"context — a reflow may have moved them out of this sweep's reach: {context_lines!r}"
    )
    quote_line = real_lines[quote_idx]
    filler = [f"  (filler line {n}, not a stale claim, just spacing.)" for n in range(gap)]
    new_claim = "- unrelated: the command line is read-only, freshly introduced by this test."
    synthetic = (
        ["# Notes", "## [9.9.9] — 2026-08-17"]
        + context_lines
        + filler
        + [new_claim, "## [1.0.0] — 2026-01-01",
           "- old: the command line stays read-only, historical."]
    )
    target = tmp_path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(synthetic) + "\n", encoding="utf-8")
    monkeypatch.setattr(fd, "REPO_ROOT", tmp_path)

    offenders = fd.stale_read_only_claims()
    offending_lines = {line for _path, _lineno, line in offenders}

    assert new_claim in offending_lines, (
        f"{filename} gap={gap}: the freshly injected false claim was NOT caught — the "
        f"exemption is still proximity-based: {offenders}"
    )
    assert quote_line not in offending_lines, (
        f"{filename} gap={gap}: the real LD-492 quotation was wrongly flagged: {offenders}"
    )


# --------------------------------------------------------------------------------------- #
# LD-502 round 3 — THE BINDING PROOF: a NEW false claim sharing a LINE with a verbatim     #
# copy of the exempt fragment is CAUGHT, whether the claim sits BEFORE or AFTER it.        #
# --------------------------------------------------------------------------------------- #

#: One (filename, fragment) pair per real exemption entry, read straight off the shipped
#: allow-list — never hand-copied — so this sweep always forges the CURRENT real fragment.
_LD502_ROUND3_FRAGMENTS = [
    (rel, fragment)
    for rel, entries in fd.STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT.items()
    for _reason, fragment in entries
]


@pytest.mark.parametrize("filename,fragment", _LD502_ROUND3_FRAGMENTS)
@pytest.mark.parametrize("position", ["before", "after"])
def test_ld502_round3_a_new_claim_sharing_a_line_with_the_verbatim_fragment_is_caught(
    tmp_path, monkeypatch, filename, fragment, position
):
    """THE BINDING PROOF, round 3. QA's FAIL: round 2 bound the exemption to "the matched LINE
    contains the fragment" — but a line can carry MORE THAN ONE :data:`fd.STALE_READ_ONLY_CLAIM`
    match, so a line holding both a verbatim copy of the exempt fragment AND a brand-new,
    unrelated false claim was exempted whole, new claim included. QA reproduced this same-line
    forgery with the real production fragment; a separate-line variant QA also reported could
    not be reproduced as described (recorded as a correction in the Handoff, not a dismissal).

    This plants exactly the same-line forgery, with the new claim placed BEFORE the fragment
    (``position="before"``) and AFTER it (``position="after"``), and asserts the new claim is
    still CAUGHT — the exemption is now bound to each match's own span inside the fragment's own
    span, not to "this line contains the fragment somewhere".
    """
    new_claim = "the command line is read-only, freshly forged for this test"
    if position == "before":
        combined = f"- {new_claim}; also quoting: {fragment}"
    else:
        combined = f"- quoting: {fragment}; also newly claims {new_claim}"
    target = tmp_path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Notes\n"
        "## [9.9.9] — 2026-08-17\n"
        f"{combined}\n"
        "## [1.0.0] — 2026-01-01\n"
        "- old: the command line stays read-only, historical.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fd, "REPO_ROOT", tmp_path)

    offenders = fd.stale_read_only_claims()

    assert offenders == [(filename, 3, combined)], (
        f"{filename} position={position}: a new false claim sharing a line with a verbatim "
        f"copy of the exempt fragment was NOT caught (same-line forgery): {offenders}"
    )


def test_ac1_the_help_points_the_reader_at_the_two_TRUTH_SURFACES():
    """What the review asked for: the page names the two calls that answer *"what is this?"* —
    now including the subcommand form, which needs no Python at all.

    Read over the WHITESPACE-NORMALIZED page: click rewraps the prose, so ``larkdocio guide``
    legitimately spans a line break there. Only the surface roll is protected from wrapping,
    and it is protected deliberately (the ``\\b`` marker) because a broken *id* would break a
    derivation, while a broken sentence is just a sentence.
    """
    page = " ".join(_rendered().split())
    assert "larkdocio guide" in page
    assert "capabilities()" in page


# =====================================================================
# AC2 / AC3 — `larkdocio guide` prints the packaged guide, unmangled
# =====================================================================

def test_ac2_the_guide_subcommand_exists_and_is_enrolled_like_every_other():
    assert "guide" in cli.commands
    assert "larkdocio guide --help" in consumer_text.cli_help_pages()


def test_ac3_the_subcommand_prints_the_guide_BYTE_FOR_BYTE():
    """Through click's own runner: no wrapping, no reflow, no colorization, and no added or
    swallowed trailing newline.

    Both answers, since the swap: the bare command prints the index and ``--full`` prints the
    document, and each must be its API call's bytes exactly.
    """
    from click.testing import CliRunner

    for args, expected in ((["guide"], larkdocio.guide()),
                           (["guide", "--full"], larkdocio.guide(full=True))):
        result = CliRunner().invoke(cli, args)
        assert result.exit_code == 0, result.output
        assert result.output == expected


def test_ac3_the_subcommand_takes_NO_MANGLING_OPTIONS():
    """The Dev call recorded in the Activity log: no pager flag, no ``--raw``, no colorization
    switch. Raw bytes is not the default among several modes — it is the only mode.

    ``--section`` (LD-228) and ``--full`` (the front-door swap) each choose *how much* of the
    document comes back, never how it is rendered, so the claim this test defends is unchanged;
    the exact set is pinned so a mode flag cannot slip in beside them.
    """
    assert fd.click_options(("guide",)) == {"--section", "--full"}


def test_ac3_the_subcommand_writes_THE_SAME_BYTES_TO_A_PIPE(tmp_path):
    """How an agent consumer will actually call it: stdout is a pipe, not a tty. Run it in a
    real child process, from a directory that is not the repo, and compare bytes."""
    for args, expected in ((["guide"], larkdocio.guide()),
                           (["guide", "--full"], larkdocio.guide(full=True))):
        proc = subprocess.run(
            [sys.executable, "-m", "larkdocio.cli"] + args,
            cwd=str(tmp_path), capture_output=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src"),
                 "PYTHONDONTWRITEBYTECODE": "1"},
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-2000:]
        assert proc.stdout == expected.encode("utf-8")
        assert proc.stderr == b"", "the guide subcommand wrote to stderr as well"


def test_ac3_the_pipe_run_is_not_secretly_reading_the_repo_it_RUNS_FROM(tmp_path):
    """Guard precondition: the child above is not resolving the guide off a relative path that
    happens to exist in the repo root — it is run from ``tmp_path``, and the packaged resource
    is what answers."""
    assert not (tmp_path / "GUIDE.md").exists()
    assert not (tmp_path / "src").exists()


# --------------------------------------------------------------------------- #
# AC2's binding evidence — the INSTALLED WHEEL, in a clean venv                  #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def clean_venv():
    """A throwaway venv with the built wheel installed **offline**, or a skip.

    LD-355: the construction moved verbatim to ``front_door.clean_wheel_venv`` (the single
    ``python -m venv`` site) and is produced ONCE PER RUN — this module and
    ``test_cli_mermaid_subcommand`` held byte-identical copies of it, and
    ``test_release_notes_accessor`` a third inline one. Same venv, same offline install,
    same ``{"python", "console", "env"}`` contract, same skips; six constructions per
    ``-n auto`` run became one.
    """
    return fd.clean_wheel_venv()


def test_ac2_larkdocio_guide_works_FROM_AN_INSTALLED_WHEEL_with_no_repo_on_the_path(
    clean_venv, tmp_path
):
    """The binding AC2 evidence. A ``guide`` subcommand that resolved a repo-relative path
    would pass every test above and die on a consumer's machine, so the console script is run
    out of a clean venv, from a directory outside the repo, and its bytes are compared to that
    installation's **own** ``larkdocio.guide()``.

    **LD-468 transformed this, it did not weaken it.** The parity claim used to be one pair
    because there was one answer; the swap made two — the CLI's default is the index and
    ``--full`` is the document — so BOTH pairs are compared here, each against the same
    installation's own API call. The 100 KB floor moves onto the ``--full`` half, where the
    document now lives.
    """
    def probe(expression, extra=""):
        return subprocess.run(
            [str(clean_venv["python"]), "-c",
             f"import sys, larkdocio; sys.stdout.buffer.write({expression}.encode('utf-8'));"
             + extra],
            cwd=str(tmp_path), capture_output=True, env=clean_venv["env"],
        )

    api = probe("larkdocio.guide()", "sys.stderr.write(larkdocio.__file__)")
    assert api.returncode == 0, api.stderr.decode("utf-8", "replace")[-2000:]
    where = api.stderr.decode("utf-8", "replace")
    assert "/v/" in where or "\\v\\" in where, (
        f"the probe imported {where}, not the installed copy in the clean venv"
    )
    api_full = probe("larkdocio.guide(full=True)")
    assert api_full.returncode == 0, api_full.stderr.decode("utf-8", "replace")[-2000:]

    for args, expected, label in (
        (["guide"], api.stdout, "larkdocio.guide()"),
        (["guide", "--full"], api_full.stdout, "larkdocio.guide(full=True)"),
    ):
        cli_run = subprocess.run(
            [str(clean_venv["console"])] + args,
            cwd=str(tmp_path), capture_output=True, env=clean_venv["env"],
        )
        assert cli_run.returncode == 0, cli_run.stderr.decode("utf-8", "replace")[-2000:]
        assert cli_run.stdout == expected, (
            f"`larkdocio {' '.join(args)}` from the installed wheel is not byte-identical to "
            f"that installation's own {label}"
        )
    assert len(api_full.stdout) > 100_000, "the installed guide came back suspiciously short"
    assert len(api.stdout) > 0 and is_index_sized(len(api.stdout), len(api_full.stdout)), (
        "the installed wheel's default guide answer is not an index"
    )


def test_ac5_and_ac6_the_two_GUIDE_EDITS_ship_in_the_wheel(clean_venv, tmp_path):
    """Both prose ACs are claims about what a **consumer** reads, so they are proved where the
    consumer reads them: out of the installed wheel's own ``guide()``, in the right section."""
    out = subprocess.run(
        [str(clean_venv["python"]), "-c",
         "import sys, larkdocio; sys.stdout.buffer.write(larkdocio.guide(full=True).encode('utf-8'))"],
        cwd=str(tmp_path), capture_output=True, env=clean_venv["env"],
    )
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")[-2000:]
    shipped = out.stdout.decode("utf-8")
    assert shipped == larkdocio.guide(full=True), "the in-wheel guide is not the source guide"
    assert _preflight_gaps(_guide_section(_CREDENTIALS_HEADING, shipped)) == []
    assert _reconvert_gaps(_guide_section(_DOWNLOAD_RECIPE_HEADING, shipped)) == []


# =====================================================================
# AC4 — `larkdocio.preflight` is discoverable from the top level
# =====================================================================

def test_ac4a_preflight_is_exported_not_merely_importable():
    """``dir(larkdocio)`` / ``help(larkdocio)`` / ``from larkdocio import *`` all read
    ``__all__``, which is why *"it exists if you know the module path"* was not enough."""
    assert "preflight" in larkdocio.__all__
    assert "check_permissions" in larkdocio.__all__
    assert larkdocio.check_permissions is larkdocio.preflight.check_permissions
    assert callable(larkdocio.preflight.call_cost)


def test_ac4b_preflight_has_a_ROW_in_the_entry_point_index():
    """Leg (b): a named, machine-readable home — ``capabilities()["entry_points"]``, the index
    of what a consumer can call from the top level. Not ``["docs"]``: that key is the packaged
    **document** index, projected off ``guide.DOC_ACCESSORS``."""
    row = capabilities(full=True)["entry_points"]["preflight"]
    assert row["kind"] == "module"
    assert "advisory" in row["summary"].lower()
    assert row["cost"], "the preflight row does not disclose what calling it costs"
    assert "call" in row["cost"].lower()


def test_ac4b_the_entry_point_index_is_DERIVED_from_dunder_all_both_ways():
    """So a public symbol added later cannot ship without a one-line summary, and a row whose
    symbol was removed cannot linger. The whole of ``__all__``, with no exceptions carved out —
    an exception list is where the next omission would hide."""
    rows = set(capabilities(full=True)["entry_points"])
    exported = set(larkdocio.__all__)
    assert rows == exported, (
        f"entry_points and __all__ disagree: only in the index {sorted(rows - exported)}, "
        f"only in __all__ {sorted(exported - rows)}"
    )


def test_ac4b_a_NEW_export_WITH_NO_SUMMARY_cannot_ship(monkeypatch):
    """The forward leg proven red at the projection itself: the index is built by resolving
    ``__all__``, so an undescribed export raises instead of appearing as a blank row."""
    monkeypatch.setattr(larkdocio, "__all__", list(larkdocio.__all__) + ["errors"])
    monkeypatch.setattr(larkdocio, "errors", larkdocio.preflight, raising=False)
    with pytest.raises(KeyError, match="entry-point summary"):
        capabilities(full=True)


def test_ac4b_every_entry_point_row_is_complete_and_RESOLVES():
    """A row that names something the install does not have is the defect this whole area
    exists to prevent, so each row is resolved against the package."""
    import types

    for name, row in capabilities(full=True)["entry_points"].items():
        assert row["name"] == name
        assert row["kind"] in {"module", "function", "value"}
        assert row["summary"].strip() and row["cost"].strip()
        target = getattr(larkdocio, name)
        assert (row["kind"] == "module") == isinstance(target, types.ModuleType)
        assert (row["kind"] == "function") == (
            callable(target) and not isinstance(target, types.ModuleType)
        )


def test_ac4_the_entry_point_index_round_trips_as_JSON():
    caps = capabilities(full=True)
    assert json.loads(json.dumps(caps))["entry_points"] == caps["entry_points"]


def test_ac4_the_DOCS_INDEX_IS_UNCHANGED_and_still_the_packaged_document_set():
    """The hard constraint, asserted rather than assumed: ``["docs"]`` did not gain a
    non-document row, so nobody can conclude later that one is acceptable there."""
    import importlib

    guide_module = importlib.import_module("larkdocio.guide")
    docs = capabilities(full=True)["docs"]
    assert set(docs) == {f"{name}()" for name, _r, _s in guide_module.DOC_ACCESSORS}
    assert "preflight" not in docs
    for row in docs.values():
        assert row["resource"].endswith(".md"), (
            f"a non-document row reached capabilities()['docs']: {row}"
        )


# =====================================================================
# AC5 — the guide meets `preflight` where someone would LOOK
# =====================================================================

def test_ac5_the_credentials_section_itself_names_preflight_and_its_CHARACTER():
    """Structurally located: the mention is inside the credential/setup section a consumer
    walks on their way in — not merely somewhere in 3,000-odd lines, which is the state that
    made a full-text search the only way to find it."""
    section = _guide_section(_CREDENTIALS_HEADING)
    gaps = _preflight_gaps(section)
    assert gaps == [], (
        f"the guide's credentials/setup path never says {gaps} about preflight, so a reader "
        f"walking it still cannot find (or correctly read) the check"
    )


def test_ac5_the_mention_does_not_read_as_a_GATE():
    """The doctrine in ``preflight``'s own module docstring and in ``permissions``: the library
    never widens, requests or escalates a scope, and nothing requires the check. A setup
    section that implied a mandatory pre-step would be a new false claim."""
    section = _guide_section(_CREDENTIALS_HEADING).lower()
    assert "never required" in section or "never mandatory" in section
    for forbidden in ("you must run", "run this first", "required before"):
        assert forbidden not in section, f"the preflight mention reads as a gate: {forbidden!r}"


def test_ac5_the_section_check_BITES_when_the_mention_is_removed():
    """Red proof over the real text: strip the paragraph and the guard reports it."""
    section = _guide_section(_CREDENTIALS_HEADING)
    stripped = "\n".join(
        line for line in section.splitlines()
        if "larkdocio.preflight" not in line
    )
    assert _preflight_gaps(stripped), "removing the preflight paragraph did not redden AC5"


def test_ac5_a_mention_ELSEWHERE_would_not_satisfy_the_guard():
    """The point of locating it structurally: a paragraph in the recipes chapter is not the
    credential path, and the guard must not accept one.

    **Transformed by LD-541 to keep its force, not to fix a failure.** It probed
    ``## Recipes``, which the guide restructure turned into a 26-line index — a section that
    trivially lacks any paragraph, so the claim would have gone on passing while proving
    nothing. It now probes the docx-write task group, which really does carry seventeen recipes
    and thousands of lines of runnable prose: a guard that accepted a mention *anywhere* would
    accept one there.
    """
    haystack = _guide_section("## Task — change what a document says")
    assert len(haystack.splitlines()) > 500, (
        "the probe section is too small to be a meaningful ELSEWHERE — pick the task group that "
        "actually holds the write recipes")
    assert _preflight_gaps(haystack) != []


# =====================================================================
# AC6 — the download recipe carries the re-convert warning
# =====================================================================

def test_ac6_the_download_recipe_carries_the_RECONVERT_warning():
    """In the recipe's own section, in the review's own terms: re-convert rather than diffing
    against old output, because a renderer improvement lands in the same diff as content —
    and it names the two shapes that actually did it (linkified URLs, real ``rowspan``
    tables)."""
    section = _guide_section(_DOWNLOAD_RECIPE_HEADING)
    gaps = _reconvert_gaps(section)
    assert gaps == [], (
        f"the download recipe — where a consumer building a snapshot-diff workflow actually "
        f"is — never mentions {gaps}"
    )


def test_ac6_the_warning_is_about_a_SHIPPED_DELIBERATE_behavior_not_a_bug():
    """The framing the issue insists on: this is a warning about renderer *improvements*, so
    it must not read as a correctness caveat."""
    section = _guide_section(_DOWNLOAD_RECIPE_HEADING).lower()
    assert "improve" in section, (
        "the warning does not say the change it warns about is an improvement"
    )
    for wrong in ("bug", "broken", "unreliable", "corrupt"):
        assert wrong not in section, f"the re-convert warning reads as a defect report: {wrong!r}"


def test_ac6_the_recipe_check_BITES_when_the_warning_is_dropped():
    """Red proof over the real section text: delete the paragraph that carries the warning and
    every one of its claims goes missing — the guard reports all three, not a subset."""
    section = _guide_section(_DOWNLOAD_RECIPE_HEADING)
    assert _reconvert_gaps(section) == []
    stripped = "\n".join(
        line for line in section.splitlines() if "re-convert" not in line.lower()
    )
    assert sorted(_reconvert_gaps(stripped)) == ["linkified", "re-convert", "rowspan"]
    # …and the section really did lose only that paragraph.
    assert len(stripped) < len(section) and "init_env" in stripped


def test_ac6_the_warning_is_in_THAT_recipe_not_only_in_the_release_notes():
    """The defect § N3 reports: the note existed, but in the notes of a release the arriving
    consumer skipped. Pin that the recipe now carries it on its own."""
    section = _guide_section(_DOWNLOAD_RECIPE_HEADING)
    assert "re-convert" in section.lower()
    assert len(section) < len(larkdocio.guide(full=True)), "the section reader matched the whole guide"


# =====================================================================
# AC7 — the front-door guards are EXTENDED to the new claims
# =====================================================================

def test_ac7_every_subcommand_is_SHOWN_BEING_INVOKED_in_the_readme():
    """Derived from ``cli.commands``, so ``guide`` enrolled itself and LD-211's subcommand
    will too: a new command owes the README an invocation on its own."""
    assert fd.undocumented_subcommands() == [], (
        f"these subcommands exist and the README never shows one being run: "
        f"{fd.undocumented_subcommands()}"
    )


def test_ac7_the_readme_shows_no_subcommand_that_does_not_exist():
    assert fd.phantom_subcommands() == []


def test_ac7_the_invocation_scan_really_reads_the_readme_and_finds_them_all():
    """Guard precondition: the scan is not returning an empty set for both legs, which would
    make the two tests above vacuous."""
    found = fd.invoked_subcommands(fd.readme_text())
    assert found == set(cli.commands), found
    assert "guide" in found


def test_ac7_dropping_the_GUIDE_documentation_from_the_readme_reddens():
    """The AC7 mutation, over the real README text: remove the lines that show
    ``larkdocio guide`` and the completeness guard reports it."""
    stripped = "\n".join(
        line for line in fd.readme_text().splitlines()
        if not line.strip().startswith("larkdocio guide")
    )
    assert fd.undocumented_subcommands(stripped) == ["guide"]


def test_ac7_a_PHANTOM_subcommand_in_the_readme_reddens():
    """Direction two, over synthetic text in the README's own shape."""
    fake = fd.readme_text() + "\n```bash\nlarkdocio publish --to prod\n```\n"
    assert fd.phantom_subcommands(fake) == ["publish"]


def test_ac7_the_invocation_scan_does_not_read_PROSE_as_a_subcommand():
    """The false-positive half, and it is not hypothetical: the README's prose really does say
    "larkdocio itself", "larkdocio repo" and "the installed larkdocio version". A guard that
    reported five phantoms on a correct README would be deleted."""
    prose = (
        "larkdocio itself is the dev repo, and larkdocio repo history is not vendored; "
        "print the installed larkdocio version with --version."
    )
    assert fd.invoked_subcommands(prose) == set()
    assert fd.invoked_subcommands("Run `larkdocio` in the larkdocio repo.") == set()


def test_ac7_the_invocation_scan_reads_a_GLOBAL_OPTION_before_the_subcommand():
    """The documented calling convention — globals come first — is handled structurally."""
    block = '```bash\nlarkdocio --env-file /path/to/.env download "<URL>" -o ./out/\n```'
    assert fd.invoked_subcommands(block) == {"download"}


def test_ac7_the_option_documentation_leg_covers_the_new_subcommand_too():
    """The guard the issue predicted at mint: ``guide`` auto-enrols into the every-option-is-
    documented leg. LD-228 gave it its first option, which is exactly the case the enrolment was
    for; the front-door swap gave it its second (``--full``, the whole document now that the
    index is the default). Both are pinned here and the README must carry both literally."""
    covered = fd.all_command_options()
    assert "larkdocio guide" in covered
    assert covered["larkdocio guide"] == {"--section", "--full"}
    for option in ("--section", "--full"):
        assert option in fd.readme_text()


def test_ac7_the_whole_front_door_family_still_agrees_about_the_LAYOUT_TABLE():
    """AC7's *"the layout table stays complete both ways"* — re-asserted here because AC4 added
    a public export and this issue is the one that could have skipped it."""
    documented = fd.documented_layout_paths(fd.readme_text())
    undocumented, phantom = fd.two_way_diff(documented, fd.real_top_level())
    assert not undocumented and not phantom, (undocumented, phantom)


# =====================================================================
# AC8 — the new `--help` page is in the dialect corpus and dialect-free
# =====================================================================

def test_ac8_the_guide_help_page_is_in_the_corpus_and_speaks_no_dialect():
    page = consumer_text.shipped_docs()["larkdocio guide --help"]
    assert dialect_hits(page) == [], dialect_hits(page)
    assert dialect_hits(_rendered()) == []


def test_ac8_the_dialect_guard_BITES_on_a_string_added_to_the_GUIDE_page(monkeypatch):
    """The red proof on the newly enrolled page specifically.

    Injected into the command's ``epilog`` rather than its ``help``: the help string is also
    what the GROUP page lists the command by, so a help injection would be caught twice and
    the assertion would stop showing that the new page itself is in scope.
    """
    monkeypatch.setattr(cli.commands["guide"], "epilog", "See LD-208 for the rationale.")
    report = consumer_text.corpus_dialect_report()
    assert [(label, matched) for label, _n, matched, _s in report] == [
        ("larkdocio guide --help", "LD-208")
    ], report


def test_ac8_the_widened_group_page_did_not_bring_dialect_with_it(monkeypatch):
    """…and the same proof for the group's own page, since its whole text is new."""
    monkeypatch.setattr(cli_group(), "help", "A reader and a writer. See LD-208.")
    report = consumer_text.corpus_dialect_report()
    assert [(label, matched) for label, _n, matched, _s in report] == [
        ("larkdocio --help", "LD-208")
    ], report
