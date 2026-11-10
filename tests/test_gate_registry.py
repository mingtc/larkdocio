# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE LIVE-GATE REGISTRY GUARD (LD-222 / audit T5a) — absence becomes data.

The house invariant is **"a live gate never silently passes."** It is carried today by a
hand-grown set of offline companion files, and until this guard existed the *absence* of a
companion was invisible: a new ``tests/test_live_*.py`` could enter the tree with no
discipline mirror and nothing reddened.

This file is the enforcement half of that invariant's bookkeeping. The data half is
:mod:`gate_registry`, which classifies **every** ``tests/test_live_*.py`` as exactly one of
six kinds and carries a written reason per file. What is checked here:

* **Exhaustive in both directions, over a DISCOVERED set** — the file list is globbed from
  ``tests/``, never hand-typed. Three independently-observable assertions: no discovered file
  is missing from the registry; no registry row names a file that has vanished; every
  companion a row names resolves to a real file.
* **Per-file, reasoned classification** — the harnesses, the offline companions and the
  offline-support file are each classified individually with a reason. A blanket
  ``if "harness" in name: continue`` would be a hole; there is no pattern-skip here.
* **The in-file mirror is verified, not asserted** — ``test_live_write_mermaid_create_gate``
  keeps its discipline self-check *inside the gate file*; the registry records that as its own
  kind and this guard greps the file for the marker.
* **The gap list is published** — the 10 gates with no separate companion file are rendered
  into :mod:`gate_registry`'s own docstring and held byte-identical to the projection, so maintainer
  can read the remaining price without running anything.

This guard **reads files as text**; it never imports or executes a gate module, so it makes
no live API call (LD-222 B3).

Scope note (LD-222): that issue added the registry and this guard. It wrote **no** missing
companion (T5c), extracted **no** shared ``gate_discipline`` helper (T5b), and edited **no**
gate's assertions, skips or provisioning (AC8).

Amendment (LD-245, 2026-08-03): the maintainer bought T5c **at four** — the v1.24.0-arc cohort, whose
absence was a discipline failure rather than a pre-pattern artifact — and ratified the other
nine. So the arithmetic below moved (gaps 14 → 10, companions 18 → 22) and the arc-four
assertions were re-framed from "these four are flagged gaps" to the **positive** direction:
the cohort is still named, and every member is now checked to be mirrored. That direction of
edit is legitimate *here* because this issue changed the **scope** of the coverage and the
guard follows the coverage — the opposite of a behavior-preserving refactor, where editing an
assertion to accommodate a change is the smell. No test was weakened to accommodate the four:
the exhaustiveness, no-stale-row, well-formedness, bidirectional-pairing and no-pattern-skip
checks all stand untouched, and there are four more parametrized cases than before.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import gate_registry as gr

TESTS_DIR = pathlib.Path(__file__).resolve().parent

# The discovered set — globbed, never hand-typed (AC2).
DISCOVERED = sorted(p.name for p in TESTS_DIR.rglob("test_live_*.py"))  # LD-654: recursive


# ---------------------------------------------------------------------------
# AC2 — exhaustive in BOTH directions, three independently observable assertions
# ---------------------------------------------------------------------------


def test_no_discovered_live_file_is_missing_from_the_registry():
    """(a) Every globbed ``tests/test_live_*.py`` has a registry row.

    This is the assertion that makes a NEW live gate impossible to add silently: drop a file
    into ``tests/`` matching the glob and this reddens, naming it.
    """
    missing = sorted(set(DISCOVERED) - set(gr.REGISTRY))
    assert not missing, (
        "live-gate registry is not exhaustive — these discovered tests/test_live_*.py files "
        f"have no row in gate_registry.REGISTRY: {missing}. Add one row per file, choosing a "
        f"kind from {sorted(k.name for k in gr.Kind)} and writing the reason; see "
        "gate_registry's module docstring."
    )


def test_no_registry_row_names_a_file_that_does_not_exist():
    """(b) Every registry row names a file still on disk — the registry cannot outlive its
    subject."""
    stale = sorted(set(gr.REGISTRY) - set(DISCOVERED))
    assert not stale, (
        "live-gate registry has stale rows — these files are registered but were not "
        f"discovered under tests/test_live_*.py: {stale}. Delete the row (or fix the "
        "filename) when a gate is removed or renamed."
    )


def test_every_companion_named_by_a_row_resolves_to_a_real_file():
    """(c) Every ``companion=`` / ``subject=`` cross-reference resolves to a real file."""
    dangling = []
    for row in gr.rows():
        for field, value in (("companion", row.companion), ("subject", row.subject)):
            if value is not None and not (TESTS_DIR / value).is_file():
                dangling.append(f"{row.filename}.{field} -> {value}")
    assert not dangling, (
        "live-gate registry points at files that do not exist: "
        f"{sorted(dangling)}"
    )


# ---------------------------------------------------------------------------
# AC1 / AC3 — one well-formed, reasoned row per file (per-file observability)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", DISCOVERED)
def test_every_registry_row_is_well_formed_and_reasoned(filename):
    """One parametrized case per discovered file, so a bad row names itself in the report.

    Every row carries a non-empty reason — including the harnesses and the offline files.
    That is what makes AC3's "classified, not silently skipped" checkable: the exclusions are
    per-file and written down, not a pattern match.
    """
    assert filename in gr.REGISTRY, f"{filename} has no registry row"
    row = gr.REGISTRY[filename]

    assert row.filename == filename, (
        f"registry key {filename!r} disagrees with row.filename {row.filename!r}"
    )
    assert isinstance(row.kind, gr.Kind), f"{filename}: kind is not a gate_registry.Kind"
    assert row.reason.strip(), (
        f"{filename}: every row needs a written reason — this is the field that keeps a "
        "classification from being a silent skip (LD-222 AC3)."
    )

    if row.kind is gr.Kind.HAS_COMPANION:
        assert row.companion, f"{filename}: HAS_COMPANION requires companion=..."
        assert row.subject is None and row.mirror_marker is None, (
            f"{filename}: HAS_COMPANION rows carry only a companion"
        )
    elif row.kind is gr.Kind.DECLARED_NONE:
        assert row.companion is None and row.mirror_marker is None, (
            f"{filename}: DECLARED_NONE means no companion and no in-file mirror"
        )
    elif row.kind is gr.Kind.IN_FILE_MIRROR:
        assert row.mirror_marker, f"{filename}: IN_FILE_MIRROR requires mirror_marker=..."
        assert row.companion is None, (
            f"{filename}: an in-file mirror is not a companion file"
        )
    elif row.kind is gr.Kind.COMPANION:
        assert row.subject, f"{filename}: COMPANION requires subject=... (the gate it mirrors)"
    elif row.kind in (gr.Kind.HARNESS, gr.Kind.OFFLINE_SUPPORT):
        assert row.companion is None, f"{filename}: {row.kind.name} rows name no companion"
    else:  # pragma: no cover - defended by the isinstance check above
        pytest.fail(f"{filename}: unhandled kind {row.kind!r}")


def test_companion_pairings_are_bidirectional():
    """A ``HAS_COMPANION`` gate and its ``COMPANION`` file point at each other.

    Without this, a companion could be re-pointed at the wrong gate and both rows would still
    resolve to real files (assertion (c) alone would not notice).
    """
    broken = []
    for row in gr.rows():
        if row.kind is gr.Kind.HAS_COMPANION:
            other = gr.REGISTRY.get(row.companion)
            if other is None or other.kind is not gr.Kind.COMPANION:
                broken.append(f"{row.filename} -> {row.companion} (not a COMPANION row)")
            elif other.subject != row.filename:
                broken.append(
                    f"{row.filename} -> {row.companion} -> {other.subject} (round-trip broke)"
                )
    assert not broken, f"companion pairings are not bidirectional: {broken}"


# ---------------------------------------------------------------------------
# AC3 — the non-gate files are classified per file, with no pattern-skip anywhere
# ---------------------------------------------------------------------------


def test_the_provisioning_harnesses_are_classified_individually():
    """Two when LD-222 wrote this; three since LD-258 added the Base self-provision cycle. The
    assertion is the set, not the count — a harness is classified per file, with a reason,
    never by a name pattern."""
    harnesses = {r.filename for r in gr.rows() if r.kind is gr.Kind.HARNESS}
    assert harnesses == {
        "test_live_base_disposable_harness.py",
        "test_live_sheets_write_harness.py",
        "test_live_write_harness.py",
    }, f"the HARNESS classification drifted: {sorted(harnesses)}"
    for name in sorted(harnesses):
        assert gr.REGISTRY[name].reason.strip(), f"{name}: a harness still needs its reason"


def test_the_offline_support_file_is_classified_and_is_not_counted_a_companion():
    """``test_live_write_offline.py`` is offline but is NOT one of the 14 gate companions —
    its subject is the W0 harness, which the audit classifies as a harness, not a gate."""
    row = gr.REGISTRY["test_live_write_offline.py"]
    assert row.kind is gr.Kind.OFFLINE_SUPPORT
    assert row.subject == "test_live_write_harness.py"
    assert row.filename not in {r.companion for r in gr.rows()}, (
        "test_live_write_offline.py must not be claimed as any gate's companion — that is the "
        "distinction that keeps the companion count at 14"
    )


def test_the_guard_uses_no_blanket_pattern_skip():
    """A structural self-check: this guard's own source contains no name-pattern exclusion
    (a loop skip keyed on "harness" or the offline suffix), so the classification cannot
    quietly become a filter (AC3)."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]  # skip this file's module docstring
    # Tokens are assembled at runtime so this check cannot match its own source text.
    forbidden_tokens = (
        "if " + '"harness"' + " in",
        "if " + "'harness'" + " in",
        "_offline" + '.py" in',
        "cont" + "inue",
    )
    for forbidden in forbidden_tokens:
        assert forbidden not in body, (
            f"the exhaustiveness guard grew a pattern-skip ({forbidden!r}); AC3 requires the "
            "exclusions to be per-file registry rows, not a filter in the guard"
        )


# ---------------------------------------------------------------------------
# AC6 — the 15th spelling: the in-file mirror is its own kind, and it is verified
# ---------------------------------------------------------------------------


def test_the_mermaid_gate_is_classified_as_an_in_file_mirror():
    row = gr.REGISTRY["test_live_write_mermaid_create_gate.py"]
    assert row.kind is gr.Kind.IN_FILE_MIRROR, (
        "test_live_write_mermaid_create_gate.py carries its discipline self-check inside the "
        "gate file itself — it is neither HAS_COMPANION nor DECLARED_NONE (LD-222 AC6)"
    )


def test_every_in_file_mirror_marker_is_actually_present_in_its_gate():
    """The mirror claim is *verified* against the gate's text, not taken on trust — delete the
    in-file self-check and this reddens."""
    for row in gr.rows():
        if row.kind is gr.Kind.IN_FILE_MIRROR:
            text = (TESTS_DIR / row.filename).read_text(encoding="utf-8")
            assert row.mirror_marker in text, (
                f"{row.filename} is registered as an in-file mirror but its marker "
                f"{row.mirror_marker!r} is gone — either restore the self-check or reclassify "
                "the row as DECLARED_NONE with a reason"
            )


# ---------------------------------------------------------------------------
# AC7 — the deliberate first-pass exclusion is recorded, not acted on
# ---------------------------------------------------------------------------


def test_the_comments_read_companion_is_classified_and_flagged_excluded():
    row = gr.REGISTRY["test_live_comments_read_gate_offline.py"]
    assert row.kind is gr.Kind.COMPANION
    assert row.subject == "test_live_comments_read_gate.py"
    assert row.first_pass_excluded is True, (
        "test_live_comments_read_gate_offline.py (module-scoped fixture + forbidden-env sweep) "
        "is the file both audits keep out of the first normalization pass — the registry "
        "records that call so a later T5b does not rediscover it (LD-222 AC7)"
    )
    assert gr.first_pass_excluded() == ("test_live_comments_read_gate_offline.py",), (
        "exactly one file carries the first-pass exclusion"
    )


# ---------------------------------------------------------------------------
# AC5 — the gap list is data, published, and readable without running the guard
# ---------------------------------------------------------------------------

_ARC_FOUR = (
    "test_live_sheets_border_write_gate.py",
    "test_live_sheets_freeze_write_gate.py",
    "test_live_sheets_style_write_gate.py",
    "test_live_sheets_tab_presentation_gate.py",
)


def test_the_gap_list_is_ten_gates_none_of_them_from_the_v1_24_0_arc():
    gaps = gr.gap_list()
    assert len(gaps) == 10, (
        "the count is 10 gates with no separate offline companion file — the 14 that stood "
        "before LD-245, minus the four v1.24.0-arc companions the maintainer bought on 2026-08-03 "
        f"(the other nine are RATIFIED, not arrears); the registry now derives {len(gaps)}: "
        f"{[r.filename for r in gaps]}"
    )
    assert [r.filename for r in gaps if r.arc_v1_24_0] == [], (
        "no v1.24.0-arc gate may remain a gap — LD-245 bought all four of them. A gate from "
        "that cohort reappearing here means a companion was deleted or a row was flipped back."
    )
    # 9 of the 10 are outright DECLARED_NONE; the 10th is the mermaid in-file mirror.
    kinds = sorted(r.kind.name for r in gaps)
    assert kinds.count("DECLARED_NONE") == 9 and kinds.count("IN_FILE_MIRROR") == 1, (
        f"the gap list's kind split drifted: {kinds}"
    )


def test_the_arc_four_cohort_is_still_nameable_and_every_one_is_mirrored():
    """The positive half of what used to be the arc-gap assertion (LD-245 AC6c).

    The cohort must not evaporate the moment it stops being a gap list: it is still named
    here, still named in the registry's own data, and every member is now checked to be a
    ``HAS_COMPANION`` row whose companion file really exists and points back.
    """
    assert frozenset(_ARC_FOUR) == gr.ARC_V1_24_0_COHORT, (
        "the guard's arc-four tuple and the registry's ARC_V1_24_0_COHORT disagree — the "
        f"cohort is data and this list is its check: {sorted(_ARC_FOUR)} vs "
        f"{sorted(gr.ARC_V1_24_0_COHORT)}"
    )
    for name in _ARC_FOUR:
        row = gr.REGISTRY[name]
        assert row.kind is gr.Kind.HAS_COMPANION, (
            f"{name} is a v1.24.0-arc gate; LD-245 bought its offline companion, so it must be "
            f"HAS_COMPANION and not {row.kind.name}"
        )
        assert row.arc_v1_24_0 is True, (
            f"{name} lost its arc_v1_24_0 flag — the cohort stays nameable in the DATA after "
            "it stops being a gap (that is what the flag is for now)"
        )
        assert row.companion and (TESTS_DIR / row.companion).is_file(), (
            f"{name}'s companion {row.companion!r} is not on disk"
        )
        back = gr.REGISTRY[row.companion]
        assert back.kind is gr.Kind.COMPANION and back.subject == name, (
            f"{name} ↔ {row.companion} is not a bidirectional pairing: {back!r}"
        )


def test_the_published_gap_table_is_a_byte_identical_projection_of_the_registry():
    """The rendered table inside :mod:`gate_registry`'s docstring is generated from the rows,
    and pinned here — so the published artifact maintainer prices T5c against cannot drift from the
    data. Regenerate with ``gate_registry.render_gap_table()``."""
    source = (TESTS_DIR / "gate_registry.py").read_text(encoding="utf-8")
    match = re.search(
        re.escape(gr.GAP_TABLE_BEGIN) + r"\n(.*?)" + re.escape(gr.GAP_TABLE_END),
        source,
        re.DOTALL,
    )
    assert match, (
        "the generated gap-table region markers are missing from gate_registry.py — "
        f"expected {gr.GAP_TABLE_BEGIN!r} … {gr.GAP_TABLE_END!r}"
    )
    assert match.group(1) == gr.render_gap_table(), (
        "the published gap table in gate_registry.py's docstring is no longer byte-identical "
        "to the projection of REGISTRY. Replace the region with the output of "
        "gate_registry.render_gap_table()."
    )


def test_the_gap_table_names_every_gap_and_no_longer_lists_the_arc_four():
    """Readable-without-running (AC5): the rendered text itself carries all 10 gap names — and
    none of the arc four, which are the visible payoff of LD-245."""
    table = gr.render_gap_table()
    for row in gr.gap_list():
        assert row.filename.removesuffix(".py") in table, f"{row.filename} missing from table"
    for arc in _ARC_FOUR:
        assert arc.removesuffix(".py") not in table, (
            f"{arc} is still published as a gap — it has a companion now, so either the row "
            "was not flipped or the table was not regenerated from the rows"
        )
    assert "v1.24.0" not in table, (
        "no gap remains from the v1.24.0 arc, so the table must carry no arc marker at all"
    )


# ---------------------------------------------------------------------------
# AC1 — the population arithmetic the audit stated, now derived from the data
# ---------------------------------------------------------------------------


def test_the_population_counts_match_the_audit():
    counts = gr.counts()
    assert counts == {
        "discovered": 159,
        "offline_files": 74,
        "live_files": 85,
        "harnesses": 3,
        "gates": 82,
        "companions": 72,
        "gaps": 10,
    }, (
        "the live-gate population drifted from the 2026-08-01 audit's re-verified counts, as "
        "extended three times since: +1 gate / +1 gap for the LD-229 read-only name-lookup "
        "arm; +4 gates / +4 companions (gaps UNCHANGED) for LD-236's four round-trip "
        "arms, each of which was given a companion rather than declared unmirrored; and "
        "LD-245 (T5c at the maintainer-bought scope, 2026-08-03) writing the four v1.24.0-arc "
        "companions — +4 discovered / +4 offline_files / +4 companions and gaps 14 -> 10, with "
        "live_files, harnesses and gates DELIBERATELY unchanged because a companion is not a "
        "gate. LD-247 then added the Base read arm **with its companion in the same change** "
        "— +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, and gaps "
        "DELIBERATELY unchanged at 10: the 2026-08-03 ruling's direction applied to a NEW arm "
        "rather than only to arrears, so a new gate no longer means a new gap. LD-252 added "
        "the Base canary (THE L1 GATE for the Base surface) the same way, with the same "
        "deltas and gaps again unchanged at 10. LD-255 added the Base WRITE arm the same way "
        "again — same deltas, gaps still 10. LD-258 then added the Base self-provision CYCLE, "
        "which is a HARNESS rather than a gate: +2 discovered / +1 offline_file / +1 "
        "live_file / +1 harness, with gates, companions and gaps ALL deliberately unchanged — "
        "a provisioning harness is excluded from the gate arithmetic by the audit's own rule, "
        "and its offline half is support, not a companion. LD-263 then added the Base SCHEMA "
        "arm — the app and table lifecycle — the same way every Base arm before it did: +2 "
        "discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps AGAIN "
        "deliberately unchanged at 10, because a new gate ships with its mirror. LD-262 added "
        "the Base FIELD-authoring arm on exactly the same terms — +2 discovered / +1 "
        "offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-264 then "
        "added the Base VIEW arm — the view lifecycle and the persistent filter, carrying the "
        "grouping swallow as its NEGATIVE CONTROL — with exactly the same deltas again: +2 "
        "discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps unchanged "
        "at 10. LD-265 added the Base DESTRUCTIVE arm — the only live gate whose verbs can "
        "destroy data — on exactly the same terms: +2 discovered / +1 offline_file / +1 "
        "live_file / +1 gate / +1 companion, gaps STILL 10, because the arm that could do the "
        "most damage is the last one that should ship without its mirror. LD-268 added the "
        "Base ATTACHMENT MEDIA arm — the first gate that mints permanent, unsweepable tenant "
        "residue — on the same terms once more: +2 discovered / +1 offline_file / +1 "
        "live_file / +1 gate / +1 companion, gaps unchanged at 10. LD-270 added the Base COMPUTED-PROVENANCE arm — the first gate whose subject is a column NO disposable can be built with, so its only route to one is copying a template — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-272 added THE BASE RELATIONAL GATE — the relational round trip, and the Base ladder's last planned arm — on exactly the same terms one final time: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps unchanged at 10, so the ladder closes with every one of its own arms mirrored. LD-293 then added the Base RAW-VALUE arm — the opt-in wire view, whose whole claim is about what the transport received on THAT call and so cannot be proven by a fixture — on the same terms the ladder set: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-291 then added the Base GUIDED-MIGRATION arm — the only gate whose central claim is a NEGATIVE, that a FORCED copy defect leaves the source column standing — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps unchanged at 10, because the arm that can destroy the most is again the last one that should ship without its mirror. LD-296 then added the Base ROW-HIERARCHY arm — the one gate whose route answers code:0 for a key it throws away, so it ships its own R12 control beside its effect assertion — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. The Base READ-FILTER transport then added TWO arms in one change, because its three parameters were one signature decision and the view_id half needs a WRITE the read half must never make — so the proof is two files, each with its own companion: +4 discovered / +2 offline_files / +2 live_files / +2 gates / +2 companions, gaps unchanged at 10. LD-317 then added the Base MINIMAL-FORM SWEEP — the arm whose capture a SHIPPED registry flag is derived from, so its companion re-derives every row offline rather than only checking the arm's posture — on exactly the same terms once more: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-348 then added the CONTACTS EMAIL-LOOKUP arm — the first READ arm since the ruling to earn a companion, and it earns one for a reason no Base arm had: its second question can only be asked with a real user's live address, so the guard that the address never enters the repository has to run in the credential-LESS run, which is the only run that can prove it — on the same terms regardless: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-324 then added the DRIVE ENUMERATION arm — the first live arm on a fourth surface, whose subject is the bot's OWN root folder discovered live rather than any designated document — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because a new gate still ships with its mirror. LD-328 then added THE R1 GATE — the Drive determinism canary, whose subject is the bot's OWN root folder discovered live (a self-provisioned folder is unavailable because create_folder is a PERMANENT write) with an OPTIONAL maintainer-designated override that skips loudly — on exactly the same terms one more time: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps unchanged at 10. LD-383 then added the SHEETS GHOST-TAB arm — the first live arm whose subject is a REFUSAL rather than a success, so it ships a CLEAN CONTROL read beside its skip assertion (an arm that only ever sees a skip proves half of what it claims) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-386 then added the DRIVE ASSET arm — the first live arm whose IDEAL subject is unprovisionable (a disposable folder would be a permanent Drive write with no purge verb), so it runs a real folder leg that skips LOUDLY on an empty asset set beside a leg driving the same shipped code against the standing disposable zoo — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps unchanged at 10. LD-409 then added the DRIVE NAMED-VERSION gate — the FIRST live gate for a MUTATING Drive op, and the arm that proves this surface's read-only claim was RE-SCOPED rather than dropped — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because the first arm that can change a real user's file is the last one that should ship without its mirror. LD-410 then added the DOCX HISTORICAL-READ gate — a WRITE gate for a READ capability, because a read-only canary cannot produce the two states a pinned read has to be falsified against — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-431 then added the DOCX TABLE-GROWTH gate — a gate for a CONSTRUCTION change, which is the class of change an offline call-sequence assertion can get internally consistent and still have wrong on the wire — on exactly the same terms once more: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-432 then added the DRIVE ACCESS gate — the first gate whose subject is WHO may use a document, and one whose central claim is the difference between an accepted call and a stored one — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-433 then added the DOCX IMAGE-AUTHORING gate — the first arm that writes BYTES into a document, and so the first whose leftovers CANNOT be cleaned up (no verb purges drive media), which is exactly why it ships with the mirror that pins disclosure-instead-of-purge — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-434 then added the UPLOADED-FILE SENTENCE-LINK gate — the first arm whose subject spans TWO surfaces in ONE round trip (a Drive file and a docx run, because either half alone leaves the ask unserved) and the first whose destination is a token the CALLER supplies rather than anything the harness may create — on exactly the same terms once more: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-447 then added the SHEETS IN-CELL IMAGE gate — the first arm that writes BYTES into a SPREADSHEET, and the first whose permanent residue is minted by LARK rather than uploaded by the caller, which is precisely why it ships with the mirror that pins disclosure-instead-of-purge and an independent read-back of the cell — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-449 then added the DRIVE CHUNKED-UPLOAD gate — the first arm whose subject is a MULTI-PART upload, and the first Drive arm that CREATES its own destination folder (D-12 plumbing in the harness, never in the library, which still ships no folder-creating call) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because the arm that turns an unmeasured partition into a measured one is the last one that should ship without its mirror. LD-454 then added the ROUND-TRIP ESCAPE-IDENTITY arm — the fifth the round-trip-editing spec round-trip member, whose subject is a line the caller never edited and whose control is the PRE-FIX compile re-created in place, because a gate never shown failing on its own defect is not known to detect it — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-455 then added the ANCHOR SOFT-RETURN arm — the sixth the round-trip-editing spec round-trip member, and the first whose PREMISE is itself an API fact (that Lark keeps a literal newline inside one text run), so the arm proves that on the wire before claiming either behaviour built on it — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-458 then added the REFUSAL-POLICY arm — the first gate whose subject is what apply() DOES with its own log rather than what it writes, so its claim is a COMPARISON of two self-created documents rather than an assertion about either — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. LD-467 then added the DRIVE FOLDER-CREATE gate — the arm for the ONE R3 organize verb a product ruling opened, and the first Drive arm that creates EVERY object it touches (its parent folder included) and then deletes each with its OWN raw call, because the library deliberately ships no folder-delete verb — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because an arm whose subject is a PERMANENT write it must clean up itself is the last one that should ship without its mirror. LD-464 then added the DRIVE UPLOAD-IDENTITY gate — the arm for the finding an automation hits on its SECOND run, and the first whose central claim is that a call SHOULD have produced a duplicate (an upload that quietly started de-duplicating would make the shipped disclosure wrong, and this is where that is found out) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because an arm whose subject is a wrong sentence that already shipped is the last one that should ship without its mirror. LD-481 then added the DOCX BATCHED-FILL gate — the second gate for a CONSTRUCTION change, and the first whose central assertion is a COUNT of API calls on the wire rather than a property of what was written (the read-back is still the verdict; the count is what the change bought) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps 10. LD-471 then added the RESTRUCTURE arm — the first gate whose subject is the ORDER of a document rather than its content, and so the first whose central assertion cannot be made from an apply-log at all (a fully-applied, refusal-free log is compatible with a document in the wrong order) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10: LD-469 then added the DOCX FOLDER-ACL arm — the first gate whose subject is a SHIPPED SENTENCE that was measured FALSE (a fresh docx was called a document only the app can use; one created into a folder comes back carrying inherited rows), and so the first that ships a CONTROL as the point rather than as a courtesy — on exactly the same terms once more: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10: LD-470 then added the DOCX MEDIA-PLACEMENT arm — the first gate whose subject is WHERE a media block lands rather than whether its bytes bound, and the first whose central assertion cannot be made from a create's own answer at all (an echo names the block that was made, never the order it was made into) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because an arm whose measurement two shipped sentences are quoted from is the last one that should ship without its mirror. LD-472 then added the SHEETS DOC-TRUTH arm — the first gate whose subject is a SENTENCE, run BEFORE the sentence was rewritten so the docs quote a measurement rather than a memory, and the first whose own refusal leg ORPHANS permanent media by construction (the upload precedes bind validation, which is the finding it exists to establish) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because an arm that decides what the shipped guide says is the last one that should ship without its mirror. LD-474 then added the DRIVE BYTES-LEG gate — the first gate whose subject is a shipped sentence measured FALSE about this library's OWN surface (the folder read said the file download leg was not shipped; it is, and one consumer run returned partial results on five of seven items because it believed that), so the arm is a DISPROOF rather than a demonstration: it downloads the very token the walk skipped and hash-matches it against the upload — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, because an arm whose measurements four shipped paragraphs are quoted from is the last one that should ship without its mirror. LD-477 then added the SHEETS HIDDEN-TAB READ-ROUTE gate — the first arm whose WRITE credentials exist only to build the situation while the claim itself is made by a READ client, so the assertion under test is a different client's answer rather than a write verifying its own work — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10, and it is also the rare write-ring arm that mints no permanent residue at all. LD-492 then added the ROUND-TRIP VERB gate — the first arm whose subject is a CONSOLE COMMAND rather than a library call, and so the first that has to cross a process boundary and a file system to make its claim at all (the caller's edit happens BETWEEN the two phases, on disk) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10; and its companion carries one thing no other does, the proof that the arm's SKIP PATH fires and names its variable, because this arm's live half was parked at landing for a missing precondition and a parked gate that cannot be shown to skip loudly is indistinguishable from one that passed. LD-482 then added the ONE-CALL TABLE gate — the third gate for a CONSTRUCTION change, and the first whose binding claim is POSITIONAL (a whole table subtree lifted onto a different endpoint has to land beside its own reference in a MIXED batch, and only Lark decides what an index means on that route), carrying an ATOMICITY leg whose verdict is a read-back proving a refused subtree left NOTHING — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10. "
        f"LD-583 then added the TYPED-CREATE-RETURNS gate — the first arm whose subject is a RETURN TYPE, and the first whose central assertion is a NEGATIVE about the wire (that the docx v1 create reply carries NO url, which is the fact the shipped type encodes by having no url attribute at all, so a reply that grew one is a finding rather than a pass) — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10; and it is the rare write-ring arm that mints no permanent residue at all, because all four of its objects are reclaimable and nothing is uploaded. "
        f"LD-601 then added the REMOVAL-ROUTE probe — the first arm minted because an EVIDENCE CLASS was declined rather than because a capability was added (a third-party consumer measurement may not be the source of a shipped claim), so its captures are the sole provenance of a shipped guide paragraph and its BEFORE control leg is the load-bearing half — on exactly the same terms: +2 discovered / +1 offline_file / +1 live_file / +1 gate / +1 companion, gaps STILL 10; and it mints no permanent residue at all, because its one object is reclaimable and nothing is uploaded. "
        f"{counts}")
    assert len(DISCOVERED) == counts["discovered"], (
        "the registry's arithmetic is derived from rows; it must agree with the glob"
    )


# ---------------------------------------------------------------------------
# B3 — this guard reads text; it never imports or runs a gate
# ---------------------------------------------------------------------------


def test_this_guard_never_imports_a_gate_module():
    # Tokens assembled at runtime, so the check cannot trip over its own source text.
    dynamic_import = ("import" + "lib", "ex" + "ec(", "__im" + "port__", "pytest." + "main")
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for forbidden in dynamic_import:
        assert forbidden not in source, (
            f"{forbidden!r} appears in the registry guard — it must classify by reading files, "
            "never by importing or executing a live gate (LD-222 B3)"
        )
    registry_source = (TESTS_DIR / "gate_registry.py").read_text(encoding="utf-8")
    for forbidden in dynamic_import[:3]:
        assert forbidden not in registry_source, (
            f"{forbidden!r} appears in gate_registry.py — the registry is pure data"
        )
