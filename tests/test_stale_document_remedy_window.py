"""LD-566 — the ``STALE_DOCUMENT`` remedy, and the guard's WINDOW.

**The finding (dogfood round 5, ``dev/dogfood5/FINDINGS-BANKED.md`` §§ F17, F18).** A consumer
that recovers **correctly** from a ``STALE_DOCUMENT`` refusal — re-download, rebuild the tree,
re-plan, exactly as ``REPLAN_GUIDANCE`` instructs — wiped the concurrent editor's text, because
the re-planned tree now contains that text and a whole-block edit replaces the whole block. The
remedy was correct and incomplete. And the sentence that frames the whole class — *the
compare-and-swap catches drift between plan and apply, not text that arrived before the plan* —
shipped in no document at all.

**The window claim is DERIVED, not asserted.** The plan's anchor is captured at the read that
builds the tree (``write/preview.py:483-488``) and apply compares that cached value against one
live read taken immediately before the batch (``write/apply.py:609-629``) — so foreign text that
landed **before** the plan is inside ``cached`` and the comparison is ``cached == cached``.

**The rule these tests hold.** Both statements are authored ONCE, as module constants beside
``CONCURRENCY_WARNING`` / ``REPLAN_GUIDANCE``, consumed by the **two refusal detail builders
only**, and projected into the shipped guide's concurrency section — guarded in both
directions, the shape LD-561 landed for its own label. Behaviour is unchanged: no new refusal,
no new state, and neither constant reaches a success path.
"""
import ast
import re
from pathlib import Path

from click.testing import CliRunner

from larkdocio import guide
from larkdocio.write.preview import dry_run
from larkdocio.write.revision import (
    GUARD_WINDOW,
    REPLAN_CARRIES_FOREIGN_TEXT,
    revision_guard_semantics,
    stale_document_detail,
    unconfirmable_document_detail,
)

from write_harness import _page, _para, _req

SRC = Path(__file__).resolve().parents[1] / "src" / "larkdocio"
REVISION_PATH = SRC / "write" / "revision.py"

#: The one heading the shipped guide states the concurrency doctrine under.
GUIDE_SECTION = "### Do not edit the document while an authoring session runs"


def _tree():
    return _page(_para("p1", "first line"), _para("p2", "second line"))


def _details():
    """Both refusal details — every consumer that ever meets the guard reads one of these."""
    return (
        stale_document_detail(document_id="d", cached=1, live=2),
        unconfirmable_document_detail(document_id="d", cached=1, why="a read failed"),
    )


def _doctrine_section():
    text = guide(full=True)
    assert GUIDE_SECTION in text, "the guide no longer states the concurrency doctrine"
    return text.split(GUIDE_SECTION)[1].split("\n## ")[0]


def _string_literals(path):
    return [node.value for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _flat(text):
    return " ".join(text.split())


# --------------------------------------------------------------------------- #
# AC1 — the remedy says what a re-plan does to text that arrived before it     #
# --------------------------------------------------------------------------- #

def test_ac1_both_refusal_details_carry_the_replan_cost_beside_the_replan_guidance():
    from larkdocio.write.revision import REPLAN_GUIDANCE

    for detail in _details():
        assert REPLAN_CARRIES_FOREIGN_TEXT in detail
        assert detail.index(REPLAN_GUIDANCE) < detail.index(REPLAN_CARRIES_FOREIGN_TEXT), (
            "the cost of the re-plan must read after the instruction to re-plan")


def test_ac1_the_clause_names_the_whole_block_harm_and_the_route_that_avoids_it():
    clause = _flat(REPLAN_CARRIES_FOREIGN_TEXT).lower()
    for claim in ("other writer", "whole-block", "sub-span"):
        assert claim in clause, f"the re-plan clause never says {claim!r}"


def test_ac1_the_sub_span_clause_carries_ITS_FOUR_LIMITS():
    """An unqualified *"use a sub-span edit"* would be the same defect one sentence later,
    inside the very refusal this issue exists to complete. The four limits are the route's
    own (``write/model/requests.py:1013-1029``)."""
    clause = _flat(REPLAN_CARRIES_FOREIGN_TEXT).lower()
    for limit in ("narrative", "table cell", "exactly once", "span_not_splittable"):
        assert limit in clause, f"the sub-span clause omits its limit: {limit!r}"


def test_ac1_the_clause_survives_the_sub_span_route_REFUSING():
    """The remedy must stay actionable for the caller the surgical route turns away."""
    clause = _flat(REPLAN_CARRIES_FOREIGN_TEXT).lower()
    assert "where it does not apply or refuses" in clause
    assert "re-read" in clause or "just re-read" in clause


# --------------------------------------------------------------------------- #
# AC2 — one shipped sentence states the guard's window                         #
# --------------------------------------------------------------------------- #

def test_ac2_both_refusal_details_state_the_window():
    for detail in _details():
        assert GUARD_WINDOW in detail


def test_ac2_the_window_states_BOTH_halves_in_from_and_out_of():
    window = _flat(GUARD_WINDOW).lower()
    assert "plan" in window and "apply" in window
    assert "before the plan" in window, "the complement — pre-plan drift — is the missing half"


def test_ac2_the_window_sentence_is_PRESENT_TENSE():
    """The absence-claims census pins forward-looking phrasing; this sentence states what the
    guard does now, so it registers nothing and must trip nothing."""
    from test_absence_claims_guard import FORWARD_LOOKING_PHRASES

    for name, pattern, _why in FORWARD_LOOKING_PHRASES:
        for constant in (GUARD_WINDOW, REPLAN_CARRIES_FOREIGN_TEXT):
            assert not pattern.search(_flat(constant)), name


def test_ac2_the_window_does_NOT_land_in_the_guards_success_path_disclosure():
    """``revision_guard_semantics`` rides a plan that has refused nothing — it is the other
    surface of the round's armed-vs-fired finding and is not this issue's to write."""
    source = ast.get_source_segment(
        REVISION_PATH.read_text(encoding="utf-8"),
        next(node for node in ast.walk(ast.parse(REVISION_PATH.read_text(encoding="utf-8")))
             if isinstance(node, ast.FunctionDef) and node.name == "revision_guard_semantics"),
    )
    for name in ("GUARD_WINDOW", "REPLAN_CARRIES_FOREIGN_TEXT"):
        assert name not in source, f"{name} reached the success-path disclosure"


# --------------------------------------------------------------------------- #
# AC3 — one constant, projected, guarded in BOTH directions                    #
# --------------------------------------------------------------------------- #

def test_ac3_each_statement_is_typed_exactly_once_in_the_shipped_source():
    """Direction 1: no second hand-typed copy anywhere under ``src/larkdocio``."""
    for constant in (GUARD_WINDOW, REPLAN_CARRIES_FOREIGN_TEXT):
        typed = [(path, literal) for path in sorted(SRC.rglob("*.py"))
                 for literal in _string_literals(path)
                 if constant in literal]
        assert len(typed) == 1, typed
        assert typed[0][0] == REVISION_PATH


def test_ac3_the_guide_states_both_and_states_them_VERBATIM():
    """Direction 2a: the shipped guide's concurrency section carries each constant's own
    bytes, so the refusal a consumer reads at 2am and the guide agree by construction."""
    section = _flat(_doctrine_section())
    for constant in (GUARD_WINDOW, REPLAN_CARRIES_FOREIGN_TEXT):
        assert _flat(constant) in section


def test_ac3_a_guide_statement_with_NO_constant_behind_it_reddens():
    """Direction 2b — the direction the round-4 ``STALE_SHEET`` defect escaped through: a
    second, hand-typed statement of either fact inside this section is a drift waiting to
    happen, so every occurrence of the fact's own marker must sit inside a constant."""
    section = _flat(_doctrine_section())
    markers = (
        (re.compile(r"before (?:the|your) plan", re.IGNORECASE), GUARD_WINDOW),
        (re.compile(r"other writer", re.IGNORECASE), REPLAN_CARRIES_FOREIGN_TEXT),
    )
    for marker, constant in markers:
        spans = [(m.start(), m.end())
                 for m in re.finditer(re.escape(_flat(constant)), section)]
        stray = [m.group(0) for m in marker.finditer(section)
                 if not any(s <= m.start() and m.end() <= e for s, e in spans)]
        assert stray == [], (
            f"the concurrency section states {marker.pattern!r} outside the constant: {stray}")


# --------------------------------------------------------------------------- #
# AC4 — words on an existing refusal, and nowhere else                         #
# --------------------------------------------------------------------------- #

def test_ac4_neither_statement_reaches_an_ARMED_or_an_UNARMED_plan():
    armed = dry_run([_req("first line")], _tree(), document_revision_id=7).to_dict()
    unarmed = dry_run([_req("first line")], _tree()).to_dict()
    for plan in (armed, unarmed):
        detail = plan["revision_guard_detail"]
        for constant in (GUARD_WINDOW, REPLAN_CARRIES_FOREIGN_TEXT):
            assert constant not in detail
    for revision in (7, None):
        detail = revision_guard_semantics(revision)["detail"]
        for constant in (GUARD_WINDOW, REPLAN_CARRIES_FOREIGN_TEXT):
            assert constant not in detail


def test_ac4_neither_statement_reaches_the_command_lines_push_output(monkeypatch, tmp_path):
    """The CLI renders no refusal detail — and a push that SUCCEEDS must not start reading
    like one. Driven through the real command, the way a consumer reaches it."""
    import offline_doubles
    import test_roundtrip_verb as verb
    from larkdocio import roundtrip
    from larkdocio.cli import cli

    offline_doubles.stage(monkeypatch, tmp_path)
    reader = offline_doubles.OfflineDocxReadClient(
        "cli_read_offline", "read-secret-offline", "larksuite.com")
    writer = offline_doubles.OfflineWriteClient(
        "cli_write_offline", "write-secret-offline", "larksuite.com")
    workdir = tmp_path / "edit"
    monkeypatch.setattr(roundtrip, "Client", lambda *a, **k: reader)
    monkeypatch.setattr(roundtrip, "WriteClient", lambda *a, **k: writer)

    runner = CliRunner()
    pulled = runner.invoke(
        cli, [roundtrip.COMMAND_NAME, roundtrip.PHASE_PULL, verb.DOC_URL, "-o", str(workdir)])
    assert pulled.exit_code == 0, pulled.output
    verb._edit(workdir, "Rewritten through the command line.")
    pushed = runner.invoke(
        cli, [roundtrip.COMMAND_NAME, roundtrip.PHASE_PUSH, "-o", str(workdir)])
    assert pushed.exit_code == 0, pushed.output
    for constant in (GUARD_WINDOW, REPLAN_CARRIES_FOREIGN_TEXT):
        assert _flat(constant) not in _flat(pushed.output)


def test_ac4_no_new_refusal_reason_and_no_new_plan_key():
    from larkdocio.write.model.refusal import RefusalReason

    assert {m.value for m in RefusalReason} >= {"stale-document"}
    plan = dry_run([_req("first line")], _tree(), document_revision_id=7).to_dict()
    assert "guard_window" not in plan and "replan_cost" not in plan
