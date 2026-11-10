"""File-first is the reconcile recipe's PERSISTENCE MODE — never a fifth editing path (LD-445).

LD-444 shipped ``larkdocio.snapshot.snapshot`` / ``load``. This file pins how they are
**routed**, because the way this library has failed consumers is not absence but routing: a
consumer report found the documentation *complete* and still watched a first-time
integrator hand-roll a **destructive** equivalent of a shipped function. A capability that
arrives as its own new recipe, its own chooser row and its own vocabulary is that failure
repeating — so the maintainer ruling is that persistence folds into the recipe that already teaches the
flow: **one existing row gains one sentence**, the round-trip recipe gains a persistence
passage, and the copy-this script gains a file-first **variant**.

These tests pin **this repository's own shipped text and its own symbols**, so they are
ordinary regression tests — deliberately **not** ``pytest.mark.conformance``
(``process/doctrine/conformance-tier.md`` § A.4), which is for claims about Lark's behaviour.
"""
import builtins
import re

import pytest

import guide_recipes as gr
from larkdocio import capabilities, guide

CHOOSER = "Which write recipe do you need? — add, change, update or delete content in a document"
ROUND_TRIP = (
    "update-an-existing-document-change-or-edit-many-blocks-at-once-without-re-authoring-it"
)
COPY_THIS = "copy-this-the-end-to-end-update-script-from-url-to-applied-edit"

#: The chooser table's row count (measured, not estimated: ``grep -c '^| ' `` over the section
#: body minus the header/rule pair). File-first must NOT add one — it is not an intent a
#: consumer chooses between, it is a property of one of them. **Re-measured at LD-471: 9 → 11**,
#: and neither new row is this one's subject — the router gained *"change PART of a paragraph"*
#: (routing to the sub-span recipe, which the whole-block rows silently flatten) and *"reorganise
#: the whole document"* (routing to the restructure recipe). Both are genuine intents a consumer
#: chooses between at the door; persistence still routes from the many-blocks row alone, which is
#: what the assertion below actually protects.
#: **Re-measured again at LD-474: 11 → 12**, and the new row is not a twelfth editing path
#: either — it is the row *before* editing, *"know whether you need to write at all"*, routing
#: to the ``revision_id`` change detector. It earns a place at this door because the read-back
#: law's own guard requires every recipe that authors (that one authors a paragraph as its
#: falsification leg) to be reachable from the router or declared unrouted, and because the
#: revision it teaches a consumer to record is the value that arms ``STALE_DOCUMENT`` on every
#: other row. The foreclosed thing — a new *editing* path — is still foreclosed, and
#: persistence still routes from the many-blocks row alone.
#: **Re-measured again at LD-569: 12 → 14**, and neither new row is a persistence path
#: either. The router gained *"change a checkbox"* and *"add or remove a table row"* — the two
#: edits consumers arrived wanting and found no row for. Both are genuine intents a consumer
#: chooses between at the door, and both rows exist to state that the **gated** route does not
#: serve them: the checkbox row records an open defect (a flipped checkbox is planned, reported
#: applied, and does not move) and the table-grow row records an absence (no plan-gated verb
#: changes an existing table's grid), each projecting its row of the docx-write ``absences``
#: register rather than restating it. **Re-verified at LD-574 and again at LD-575: still 14.**
#: Both rows' *destinations* moved when the gated routes shipped — the checkbox flip to the
#: reconciliation recipe, the table grow to its own — and neither shipped as a fifteenth row,
#: because a row exists for an intent a consumer arrives with and both intents were already
#: there. What each row now says changed; how many there are did not. The foreclosed thing — file-first as a fifteenth row —
#: is still foreclosed, and persistence still routes from the many-blocks row alone.
CHOOSER_ROWS_BEFORE = 14

#: The boundary line inside the file-first variant. Everything below it must run **alone**,
#: in a later process, with nothing above it in scope — that is the whole claim.
PART_B_MARKER = "PART B"


def _section(title):
    return guide(title)


def _prose(text):
    return re.sub(r"[\s*`_—]+", " ", text).lower()


def _chooser_rows():
    body = _section(CHOOSER)
    rows = [ln for ln in body.splitlines() if ln.startswith("|")]
    # drop the header row and the |---|---| rule
    return [r for r in rows if not set(r) <= set("|- :")][1:]


# --------------------------------------------------------------------------- #
# AC1 — one row, one sentence. No new chooser row.                             #
# --------------------------------------------------------------------------- #

def test_ac1_the_chooser_table_gains_no_row_for_file_first():
    rows = _chooser_rows()
    assert len(rows) == CHOOSER_ROWS_BEFORE, (
        f"the chooser table now has {len(rows)} rows against {CHOOSER_ROWS_BEFORE} — a new "
        "row for file-first would present it as a fifth editing path, which the ruling "
        "forecloses (if a DIFFERENT issue legitimately added a row, re-measure this anchor "
        "and say so)")
    file_first_rows = [r for r in rows if "`snapshot`" in r or "`load`" in r]
    assert len(file_first_rows) == 1, (
        "persistence must be routed from exactly one existing row, not from a row of its "
        f"own: {file_first_rows}")


def test_ac1_the_many_blocks_row_is_the_one_that_routes_persistence():
    # Matched on the row's own LABEL cell, not on the whole row: the section title this row
    # points at contains the same words, so any row that ROUTES to that section used to
    # satisfy an unqualified search (LD-574 gave the checkbox row that destination).
    row = next(r for r in _chooser_rows()
               if "many blocks at once" in r.split("|")[1])
    prose = _prose(row)
    assert "snapshot" in prose and "load" in prose, (
        "the many-blocks row must name both verbs — a reader who cannot see `load` cannot "
        f"tell what brings the read back: {row}")
    assert "otherwise identical" in prose or "the flow is otherwise" in prose, (
        "the added clause must say the flow is UNCHANGED, which is what stops it reading as "
        f"a second way to edit a document: {row}")


# --------------------------------------------------------------------------- #
# AC2 — the persistence mode lives INSIDE the recipe that teaches the flow.    #
# --------------------------------------------------------------------------- #

def test_ac2_the_round_trip_recipes_preamble_carries_the_persistence_passage():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    for phrase in ("snapshot", "load", "byte-identical"):
        assert phrase in prose, (
            f"the round-trip recipe's preamble must teach persistence itself; missing "
            f"{phrase!r}")
    assert "another process" in prose or "later" in prose, (
        "the passage must say WHEN persistence is for — the read surviving a process "
        "boundary")


def test_ac2_the_passage_restates_the_immutable_snapshot_editable_markdown_boundary():
    """The recipe already says the edited Markdown "is never written back as text; it is
    reconciled against the projection it came from" — the exact sentence a persistence
    feature could be misread as relaxing. So the passage restates it in the recipe's voice."""
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    assert "immutable" in prose, "the passage must say the snapshot is immutable"
    assert "reconcile" in prose, "the passage must name reconcile() as the only bridge"
    assert "editable" in prose or "edited markdown" in prose, (
        "the passage must say which artefact IS the editable one")


def test_ac2_the_byte_identity_property_is_stated_as_the_thing_that_makes_it_usable():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    window = prose[max(0, prose.find("byte-identical") - 400):prose.find("byte-identical") + 400]
    assert "projection" in window, (
        "the byte-identity claim must be about the PROJECTION — a load-then-project is "
        "byte-identical to the projection the snapshot was taken from")


# --------------------------------------------------------------------------- #
# AC3 — the staleness consequence, where a reader hits it.                     #
# --------------------------------------------------------------------------- #

def test_ac3_the_passage_states_that_a_snapshot_ages_and_the_guard_refusing_is_correct():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    assert "stale_document" in prose or "stale document" in prose, (
        "the passage must name the guard a persisted revision arms")
    assert "document_revision_id" in prose or "document revision id" in prose, (
        "the passage must name the field that arms it")
    assert "refus" in prose, (
        "the passage must say the REFUSAL is the correct outcome, not a failure mode")


def test_ac3_the_passage_says_a_snapshot_is_not_a_lock():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    assert "not a lock" in prose, (
        "a persisted revision that reserved something would be a lock; the text must deny "
        "it in as many words")
    assert "reserves nothing" in prose, "…and say what that denial means"


# --------------------------------------------------------------------------- #
# AC4 — the copy-this script gains a FILE-FIRST VARIANT, in the same recipe.   #
# --------------------------------------------------------------------------- #

def _variant_source():
    blocks = gr.recipe_blocks()[COPY_THIS]
    assert len(blocks) == 2, (
        f"the copy-this recipe must carry the canonical script AND the file-first variant, "
        f"found {len(blocks)} python blocks")
    return blocks[1].source


def test_ac4_the_variant_is_a_second_block_of_the_SAME_recipe():
    """Not a sibling recipe: the guide's ``### Recipe:`` headings must not have grown."""
    assert COPY_THIS in gr.recipe_blocks()
    _variant_source()


def test_ac4_the_variant_runs_the_whole_chain_and_keeps_the_dry_run():
    src = _variant_source()
    for call in ("snapshot(", "load(", "project_block_ids(", "reconcile(",
                 "compile_reconciliation(", "dry_run(", "apply("):
        assert call in src, f"the file-first variant must show {call} — it is the same flow"
    assert "document_revision_id=" in src, (
        "the variant must pass the SNAPSHOT's revision into dry_run, or the guard is not "
        "armed at all")


def test_ac4_the_variant_elides_nothing_a_copier_would_need():
    src = _variant_source()
    assert not re.search(r"^\s*(#\s*)?\.\.\.", src, re.MULTILINE), (
        "a copy-this script may not elide a step with `...`")
    assert PART_B_MARKER in src, (
        "the variant must mark its resumable entry point so a reader can see where a later "
        "process starts")


def test_ac4_part_b_is_runnable_ALONE_in_a_later_process(monkeypatch, tmp_path):
    """**The load-bearing test.** Part A is executed, its namespace thrown away, and Part B
    then executed **by itself** in a builtins-only namespace — which is what "resume after a
    handoff" means. A Part B that leaned on a name Part A bound would ``NameError`` here."""
    src = _variant_source()
    part_a, part_b = src.split(PART_B_MARKER, 1)
    part_b = part_b.split("\n", 1)[1]          # drop the remainder of the marker comment line

    scratch = tmp_path / "file-first"
    scratch.mkdir()
    monkeypatch.chdir(scratch)
    st = gr.stage(monkeypatch, tmp_path)

    ns_a = gr.run_source(part_a, "copy-this file-first PART A")
    assert (scratch / "document.snapshot").exists(), (
        "Part A must leave the snapshot on disk — that is the whole point of the variant")

    ns_b = gr.run_source(part_b, "copy-this file-first PART B")

    # The property the recipe claims: a load-then-project is byte-identical to the
    # projection the snapshot was taken from.
    assert ns_b["projection"].markdown == ns_a["projection"].markdown

    # …and the resumed half really applied, through the same gate, with the guard armed.
    assert ns_b["preview"].revision_guard == "active"
    assert [e.to_dict()["outcome"] for e in ns_b["log"].entries] == ["applied"]
    assert st is not None


# --------------------------------------------------------------------------- #
# LD-465 — the headline promise is TRUE: Part B needs the two files and         #
#          nothing else, because the domain now travels in the snapshot.        #
# --------------------------------------------------------------------------- #

def _part_b():
    return _variant_source().split(PART_B_MARKER, 1)[1].split("\n", 1)[1]


def test_ld465_part_b_takes_the_DOMAIN_off_the_snapshot_not_off_a_url():
    """The promise the section prints — *needs nothing from Part A but the two files* —
    was false while Part B re-parsed a hard-coded URL to recover the host. The successor's
    domain must come off the artefact."""
    part_b = _part_b()
    assert "api_domain" in part_b, (
        "Part B must read the API domain off the snapshot — it is the one fact a successor "
        "cannot derive from the token, the revision or the blocks")
    assert "https://" not in part_b, (
        "Part B still carries a URL literal, so it does NOT run on the two files alone:\n"
        + part_b)
    assert "validate_download_url" not in part_b, (
        "a resumed process has no URL to validate — that was the dead end")


def test_ld465_part_a_persists_the_domain_it_read_with():
    part_a = _variant_source().split(PART_B_MARKER, 1)[0]
    assert re.search(r"api_domain\s*=", part_a), (
        "Part A must write the domain into the snapshot, or Part B cannot find one there")


def test_ld465_the_promise_the_section_prints_is_the_one_the_code_keeps():
    prose = _prose(guide(full=True))
    assert "needs nothing from part a but the two files" in prose, (
        "the headline promise must be stated — it is what this recipe is for")
    for admission in ("not the host", "not the domain", "the domain still comes from the "
                      "url"):
        assert admission not in _prose(_variant_source()), (
            f"the code still admits {admission!r} four lines after promising otherwise")


def test_ld465_neither_half_raises_StopIteration_when_pasted_literally():
    """A bare ``next(<genexp>)`` over the reader's OWN document raises ``StopIteration`` the
    moment their text differs from the sample's — the defect the dogfood grid recorded
    against this very block. A guarded lookup that names what to change is the fix."""
    for half, source in (("A", _variant_source().split(PART_B_MARKER, 1)[0]),
                         ("B", _part_b())):
        calls = [ln for ln in source.splitlines()
                 if "next(" in ln and not ln.lstrip().startswith("#")]
        for call in calls:
            assert ", None)" in call, (
                f"Part {half} calls next() with no default — pasted literally against a "
                f"document without the sample's text it raises StopIteration:\n{call}")
        if calls:
            assert "if target is None" in source, (
                f"Part {half} must say what to do when nothing matched, in the block itself")


def test_ac4_the_variant_is_registered_in_the_execution_harness():
    """AC10: the new fence joins the guard the existing fences are held to — it is executed
    by the extract-and-run harness, not merely compiled."""
    spec = gr.SPEC_BY_SLUG[COPY_THIS]
    assert len(spec.extra_checks) == 1, (
        "the file-first variant needs its own post-condition in RECIPE_SPECS, or the harness "
        "runs it without checking what it produced")
    assert spec.persists_to_disk, (
        "a recipe that writes an artefact must declare it, so the harness runs it in a "
        "scratch cwd instead of littering the repository")


# --------------------------------------------------------------------------- #
# AC5 / AC6 — `download --projection` was DEFERRED. The CLI stays read-only.   #
# --------------------------------------------------------------------------- #

def test_ac5_no_half_flag_shipped():
    """Dev's call, recorded: the flag does **not** land in LD-445 (reasons in the issue and
    in ``requirements/DECISIONS.md``). So no half-flag exists anywhere — the artefacts are
    produced by the library call, and this guard reddens if a later change lands the CLI half
    without landing the front-door half with it."""
    from click.testing import CliRunner

    from larkdocio.cli import cli

    out = CliRunner().invoke(cli, ["download", "--help"]).output
    assert "--projection" not in out, (
        "a --projection flag appeared on `download` — land it WITH its README row, its "
        "capabilities() flag entry and AC6's front-door checks, never on its own")
    assert "--projection" not in guide(full=True)
    cli_spellings = [entry.get("cli") for entry in capabilities(full=True)["flags"].values()]
    assert "--projection" not in cli_spellings


def test_ac5_the_command_line_grew_exactly_ONE_writing_verb_and_the_readers_are_unchanged():
    """TRANSFORMED BY LD-492 — the fence moved by exactly one command, deliberately.

    AC5's fence held the CLI's command set against the shipped claim *"The command line is
    read-only"*. LD-492 landed ``roundtrip``, which writes, so that claim was corrected at
    every place it was published and this fence is re-cut rather than dropped: the FIVE
    reading commands are still exactly the five, none of them gained a write, and the sixth
    is named. **The reason the fence exists is untouched** — this issue's own AC5 was that
    file-first persistence must not grow a ``--projection`` flag on ``download``, and the
    check above still holds that; a sixth command arriving without this list moving still
    reddens.
    """
    from larkdocio.cli import cli
    from larkdocio.roundtrip import COMMAND_NAME as THE_WRITING_VERB

    assert sorted(cli.commands) == [
        "config", "download", "folder", "guide", "mermaid", THE_WRITING_VERB
    ], (
        "the CLI grew or lost a command — re-check which commands read and which one writes, "
        "in README.md and in the group help, before re-cutting this anchor")
    assert THE_WRITING_VERB == "roundtrip", (
        "the one writing verb was renamed; the front door names it in prose, so the rename is "
        "a documentation change too")


# --------------------------------------------------------------------------- #
# AC7 — no fifth editing path anywhere in the text.                            #
# --------------------------------------------------------------------------- #

def test_ac7_no_new_recipe_heading_for_this_feature():
    headings = re.findall(r"^### Recipe: (.+)$", guide(full=True), re.MULTILINE)
    offenders = [h for h in headings
                 if "file-first" in h.lower() or "snapshot" in h.lower()
                 or "offline edit" in h.lower() or "persist" in h.lower()]
    assert not offenders, (
        f"file-first is a persistence MODE of the reconcile recipe, not a recipe: {offenders}")


@pytest.mark.parametrize("banned", ["file-first mode", "offline editing", "file-first editing",
                                    "file-first path", "file-first workflow"])
def test_ac7_the_guide_coins_no_second_vocabulary_for_the_same_flow(banned):
    assert banned not in guide(full=True).lower(), (
        f"{banned!r} names a mental model the reader now has to hold beside 'reconcile' — "
        "the routing failure this issue exists to avoid")


def test_ac7_persistence_is_never_presented_as_an_alternative_to_reconcile():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP) + gr.recipe_preamble(COPY_THIS))
    for shape in ("instead of reconcile", "rather than reconcile", "without reconcile",
                  "alternative to reconcile"):
        assert shape not in prose, (
            f"{shape!r} presents persistence as a way AROUND the reconcile flow rather than "
            "a property of it")


# --------------------------------------------------------------------------- #
# AC8 — the negative claims, enumerated.                                       #
# --------------------------------------------------------------------------- #

def test_ac8_the_scope_is_stated_docx_only():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    assert "docx" in prose, "the passage must scope itself to docx"
    for absent in ("sheet", "base", "folder"):
        assert absent in prose, (
            f"the scope statement must name what is NOT covered, including {absent!r} — a "
            "claim's scope may not exceed its evidence's")


def test_ac8_a_snapshot_is_not_a_lock_not_a_cache_and_not_a_backup():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    for denial in ("not a lock", "not a cache", "not a backup"):
        assert denial in prose, f"the passage must deny being a {denial[8:]!r}"
    assert "one read" in prose, (
        "…and say what it IS instead: a copy of one read")


def test_ac8_payload_shape_drift_is_labelled_unmeasured_not_refuted():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    assert "unmeasured" in prose, (
        "whether a snapshot survives a Lark payload-shape change is unmeasured — saying "
        "nothing invites the reader to assume it does, and saying 'it does not' would "
        "exceed the evidence")
    window = prose[prose.find("unmeasured") - 300:prose.find("unmeasured") + 300]
    assert "parser" in window or "payload" in window, (
        "the unmeasured claim must name what may drift: the payload is pinned as it "
        "arrived, and the parser is what may move under it")


def test_ac8_no_cross_version_migration_is_offered():
    prose = _prose(gr.recipe_preamble(ROUND_TRIP))
    assert "format_version" in prose or "format version" in prose, (
        "the passage must name the artefact's version field")
    assert "migrat" in prose, (
        "…and state that an unrecognised version is REFUSED, never migrated — LD-444 ships "
        "no migration")


# --------------------------------------------------------------------------- #
# Anti-vacuity: the guards above bite.                                         #
# --------------------------------------------------------------------------- #

def test_the_row_count_guard_would_catch_a_new_chooser_row():
    rows = _chooser_rows()
    planted = rows + ["| **Edit a document from a file** | § \"Recipe: file-first editing\" |"]
    assert len(planted) != CHOOSER_ROWS_BEFORE

def test_the_part_b_isolation_check_is_not_vacuous():
    """A Part B that re-imported nothing would fail the isolation test — proven by showing
    the split really produces two halves that both bind names."""
    part_a, part_b = _variant_source().split(PART_B_MARKER, 1)
    assert "import" in part_a and "import" in part_b, (
        "both halves must carry their own imports, or 'runnable as written' is untrue")
    assert "init_env(" in part_b, (
        "Part B resolves credentials in a process of its own; without init_env it cannot")
    assert builtins is not None
