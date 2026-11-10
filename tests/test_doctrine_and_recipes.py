# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-147 — the round-2 documentation tranche, pinned at **content** level.

Round 2's verdict was "works much better", and the residue was almost entirely
**documentation of things that already exist**. This module is the guard set for the eight
items the maintainer dispositioned (`progress.md`, item 6 + item 1), each asserted
against the thing it describes rather than against its own prose:

* **(a) the two-level doctrine, VERBATIM** — ``"Author in Markdown. Target by tree. Keep
  requests, not plans."`` plus the compiler explanation (``compose()`` is a Markdown
  front-end onto the typed tree; the engine never works at the Markdown level; a pure-tree
  consumer can ignore ``compose`` entirely). A paraphrase must FAIL — proven by mutating the
  shipped text and re-running the same check.
* **(b) the worked MULTI-TURN recipe** — the request/``Plan`` serializability asymmetry
  (round-2 **T6/T16**: requests ``to_dict``/``from_dict`` round-trip, ``Plan`` deliberately
  does not) demonstrated as a recipe that **executes** in the LD-133 harness: park ≥3
  serialized requests across turns → rebuild → plan → dry-run → apply **fresh** at commit.
* **(c) the non-forgeable-``Plan`` trust property** (round-2 **T5**, filed under [DELIGHT]),
  claimed on purpose: a stale conversational account of "what we planned" can never reach
  ``apply()``. Proven, not just asserted — a snapshot cannot become a ``Plan``, and a real
  ``Plan`` applied against a document that moved refuses with **zero writes**.
* **(d) the two batch contracts SIDE-BY-SIDE** — docx whole-batch-zero-writes
  (``STALE_DOCUMENT``) vs the maintainer-blessed sheets per-entry compare-and-swap with partial
  application **fully disclosed in the apply-log**. Every status name in the guide's table is
  cross-checked against **LD-148's shipped vocabulary** — the scope/outcome/landed columns
  are re-derived by calling the shipped classifier, so the docs cannot drift from the code.
* **(e) the misleading capability-note language** (round-2 **T0**): the scratch/disposable
  rule is *this project's test-suite policy*, **not** an engine restriction. The corrected
  phrasing is asserted and the old phrasing asserted **absent**.
* **(f) ``language=None``** (round-2 **T7/T8**) documented on ``NewBlock.code``'s own
  signature + docstring, alongside the 65 real tokens (the count derived from
  ``supported_code_languages()``, never re-typed).
* **(g) ``SubSpanEditRequest`` + editing a code block** (round-2 **T4/T9**) as **executing**
  recipes, not ``help()``-only knowledge.
* **(h) formula guidance** matching what **LD-149** actually shipped, including the
  ``"="``-prefixed-string dry-run note — the required doc content is derived from the shipped
  ``INERT_STRING_NOTE`` constant itself.

Plus LD-149's recorded **Minor**: every ``dev/probes/...`` path the repo's markdown cites
must exist (the dead-reference guard).
"""
import inspect
import json
import re

import pytest

import guide_recipes as gr
from doc_prose import missing_phrases, prose
from guard_kit import REPO_ROOT as _ROOT
from guard_kit import is_separator_row, md_table_cells, section
from log_reading_apply import reading_the_log
from larkdocio import capabilities, guide
from larkdocio.langs import supported_code_languages
from larkdocio.sheets.disposition import ENTRY_SCOPED, SYSTEMIC, classify_apply_exception
from larkdocio.sheets.formula import INERT_STRING_NOTE
from larkdocio.sheets.plan import ApplyLogEntry, Refusal
from larkdocio.write import NewBlock, Plan
import private_tree  # noqa: E402  (LD-685)


#: **(a)** The doctrine, verbatim. Asserted through :func:`_states_the_doctrine`, the
#: predicate's ONE home (LD-547) — a paraphrase must fail it
#: (``test_ac1_the_verbatim_guard_bites_on_a_paraphrase``).
DOCTRINE = "Author in Markdown. Target by tree. Keep requests, not plans."

#: The recipe slugs LD-147 adds. Derived checks below refuse to let any of them ship
#: without an execution spec.
MULTI_TURN_SLUG = "accumulate-edits-across-turns-a-multi-turn-request-queue"
SUBSPAN_SLUG = "edit-part-of-a-paragraph-a-sub-span-edit"
CODE_EDIT_SLUG = "edit-a-code-block-s-text"
NEW_SLUGS = (MULTI_TURN_SLUG, SUBSPAN_SLUG, CODE_EDIT_SLUG)

_DOCTRINE_HEADING = "## The two-level design"
_CONTRACTS_HEADING = "## The two batch contracts"


# --------------------------------------------------------------------------- #
# Shared readers over the shipped guide text.                                   #
# --------------------------------------------------------------------------- #

def _section(heading: str) -> str:
    """The guide text from ``heading`` up to the next heading of the same-or-higher level.

    **Fence-aware on purpose.** A ``# ``-prefixed *comment* inside a fenced block (every
    recipe has several) looks exactly like an H1 to a line-anchored regex, which would cut a
    section off at its first code sample and make a content guard silently vacuous — the
    LD-132 failure mode in the guard itself. Lines inside a ``` fence are therefore never
    read as headings.

    LD-242: that walk is now :func:`guard_kit.section`, shared with the other guards that
    slice the shipped guide; this stays as the module's one-argument reader over
    :func:`~larkdocio.guide`.
    """
    return section(guide(full=True), heading)


_TOKEN_RE = re.compile(r"`([^`]+)`")


def _tables(region: str):
    """``[(headers, rows)]`` for every Markdown table in ``region`` (headers lower-cased)."""
    lines, out, i, n = region.splitlines(), [], 0, len(region.splitlines())
    while i < n:
        line = lines[i].strip()
        if (line.startswith("|") and line.endswith("|") and i + 1 < n
                and is_separator_row(lines[i + 1])):
            headers = [re.sub(r"[*`]", "", c).strip().lower()
                       for c in md_table_cells(line)]
            rows, j = [], i + 2
            while j < n and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
                if not is_separator_row(lines[j]):
                    rows.append(dict(zip(headers, md_table_cells(lines[j]))))
                j += 1
            out.append((headers, rows))
            i = j
            continue
        i += 1
    return out


def _table_with(region: str, *signature):
    matches = [rows for headers, rows in _tables(region)
               if all(col in headers for col in signature)]
    assert len(matches) == 1, (
        f"expected exactly one table with columns {signature}; found {len(matches)}")
    return matches[0]


def _first_token(cell: str):
    m = _TOKEN_RE.search(cell or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# AC1 (a) — the two-level doctrine, VERBATIM, with the compiler explanation.     #
# --------------------------------------------------------------------------- #

def _states_the_doctrine(text: str) -> bool:
    """Does ``text`` state the doctrine VERBATIM? — the check itself, with ONE home.

    Extracted by **LD-547** for the same reason LD-512 extracted
    :func:`~tests.test_read_back_law_and_restructure._reaches_the_law`: the bite proof below
    used to spell a *second copy* of this expression over a string it had just mutated
    itself, so it could only ever demonstrate that ``str.replace`` removes what it replaces —
    it never asked the check that greens the shipped text. Both callers now call THIS, so a
    future loosening of the verbatim rule (case-folding, prose-normalizing, accepting a
    near-match) reddens the bite instead of sailing past it.
    """
    return DOCTRINE in text


def test_ac1_the_doctrine_ships_verbatim_in_the_guide():
    """AC1: the three sentences appear in ``guide()`` **exactly** as the maintainer wrote them."""
    assert _states_the_doctrine(guide(full=True)), (
        "the guide must state the doctrine VERBATIM: " + DOCTRINE)


def test_ac1_the_doctrine_has_its_own_named_section():
    """AC1: the doctrine is a section a consumer can be pointed at — not a sentence buried
    inside one recipe (the LD-132 anti-rot rule: placement is part of the claim)."""
    section = _section(_DOCTRINE_HEADING)
    assert _states_the_doctrine(section), "the doctrine sentence must live in its own section"


def test_ac1_the_compiler_explanation_is_stated():
    """AC1: the *why* behind "author in Markdown, target by tree" — ``compose()`` is a
    Markdown **front-end onto the typed tree**, the engine never works at the Markdown
    level, and a pure-tree consumer can ignore ``compose`` entirely."""
    missing = missing_phrases(_section(_DOCTRINE_HEADING), [
        "compose() is a markdown front-end onto the typed tree",
        "the engine never works at the markdown level",
        "a pure-tree consumer can ignore compose entirely",
    ])
    assert not missing, f"the doctrine section does not explain the compiler: {missing}"


def test_ac1_each_clause_of_the_doctrine_is_explained():
    """AC1: all three clauses are unpacked where the doctrine is stated — anchors/targets are
    **tree-level**, Markdown is an **authoring convenience**, and the queue holds **requests**
    (a ``Plan`` is not portable)."""
    section = prose(_section(_DOCTRINE_HEADING))
    for claim in ("anchors", "tree", "authoring convenience", "requests", "plan"):
        assert claim in section, f"the doctrine section never mentions {claim!r}"


def test_ac1_the_verbatim_guard_bites_on_a_paraphrase():
    """AC1 (red-then-green on the check itself): the same substring check that greens the
    shipped text **fails** on a faithful paraphrase — which is what "verbatim" has to mean
    for the guard to be worth anything.

    **TRANSFORMED by LD-547.** It used to assert ``DOCTRINE not in paraphrased`` — a second,
    hand-rolled copy of the predicate over a string this test had itself mutated, which is a
    statement about ``str.replace`` and not about the guard. It now runs
    :func:`_states_the_doctrine`, the one home of the check, against both the shipped text and
    the paraphrase.
    """
    text = guide(full=True)
    assert _states_the_doctrine(text), (
        "the shipped guide does not state the doctrine even before crippling")
    paraphrased = text.replace(
        DOCTRINE,
        "Author in Markdown; target by the tree; keep the requests rather than the plans.")
    assert paraphrased != text, "the mutation did not apply — the proof would be vacuous"
    assert not _states_the_doctrine(paraphrased), (
        "the verbatim check ACCEPTED a faithful paraphrase")


# --------------------------------------------------------------------------- #
# AC2 (b) — the worked MULTI-TURN recipe, executing.                            #
# --------------------------------------------------------------------------- #

def test_ac2_the_multi_turn_recipe_ships_with_an_execution_spec():
    """AC2: the recipe exists in the guide and is wired into the LD-133 harness (so the
    1:1 spec guard in ``test_discovery_truth`` executes it every run)."""
    assert MULTI_TURN_SLUG in gr.recipe_blocks(), sorted(gr.recipe_blocks())
    assert MULTI_TURN_SLUG in gr.SPEC_BY_SLUG, sorted(gr.SPEC_BY_SLUG)


def test_ac2_the_recipe_parks_at_least_three_serialized_requests(monkeypatch, tmp_path):
    """AC2 (the amplifier's ≥3-request queue): the recipe accumulates **≥3** requests as
    **JSON text** — not live objects — and reloads them at commit time."""
    ns = gr.stage(monkeypatch, tmp_path).run(MULTI_TURN_SLUG)
    queue = ns["queue"]
    assert len(queue) >= 3, f"the multi-turn queue must hold ≥3 requests; got {len(queue)}"
    assert all(isinstance(record, str) for record in queue), (
        "the queue must hold SERIALIZED requests — a queue of live objects proves nothing "
        f"about surviving a turn boundary: {[type(r).__name__ for r in queue]}")
    for record in queue:
        assert isinstance(json.loads(record), dict), record


def test_ac2_every_request_family_the_recipe_uses_round_trips(monkeypatch, tmp_path):
    """AC2: every request the recipe queues survives ``to_dict`` → ``from_dict`` **by
    identity** (frozen dataclass equality), and the queue covers ≥3 distinct families —
    including the **tagless** ``EditRequest`` form, the one a naive ``"op"``-keyed rebuild
    would drop."""
    ns = gr.stage(monkeypatch, tmp_path).run(MULTI_TURN_SLUG)
    requests = ns["requests"]
    assert len({type(r) for r in requests}) >= 3, [type(r).__name__ for r in requests]
    for request in requests:
        assert type(request).from_dict(request.to_dict()) == request, request
    assert any("op" not in r.to_dict() for r in requests), (
        "the queue must include the TAGLESS EditRequest form, so the recipe's rebuild "
        "dispatcher is proven to handle a record with no 'op' key")


def test_ac2_the_recipe_plans_fresh_at_commit_time(monkeypatch, tmp_path):
    """AC2: the plan is built **after** the last turn, from a document read at commit time —
    asserted on the recipe's own source order (the queue is filled before the read) and on
    the plan it produced (armed whole-document guard, every entry applied)."""
    src = gr.recipe_source(MULTI_TURN_SLUG)
    last_queued = src.rindex("remember(")
    assert "get_docx_content" in src, src
    assert src.index("get_docx_content") > last_queued, (
        "the recipe must read the document AFTER the last turn — a tree captured before the "
        "queue was filled is exactly the staleness the pattern exists to avoid")
    assert src.index("parse_docx_tree") > last_queued, src

    ns = gr.stage(monkeypatch, tmp_path).run(MULTI_TURN_SLUG)
    assert ns["plan"].revision_guard == "active", ns["plan"].to_dict()
    outcomes = [e.to_dict()["outcome"] for e in ns["log"].entries]
    assert len(outcomes) == len(ns["requests"]) and "refused" not in outcomes, outcomes


def test_ac2_the_guide_explains_the_asymmetry_that_makes_the_pattern_work():
    """AC2: the recipe's prose states the primitive — **requests** serialize, a ``Plan``
    deliberately does not — because that asymmetry IS the pattern (round-2 T6/T16)."""
    missing = missing_phrases(gr.recipe_preamble(MULTI_TURN_SLUG), [
        "to_dict", "from_dict", "plan", "fresh",
    ])
    assert not missing, f"the multi-turn recipe preamble omits {missing}"


# --------------------------------------------------------------------------- #
# AC3 (c) — the non-forgeable-Plan trust property, claimed on purpose.           #
# --------------------------------------------------------------------------- #

def test_ac3_the_trust_property_is_claimed_as_a_feature():
    """AC3: the guide states the property **as a feature**, in the terms round-2 found it:
    a ``Plan`` cannot be reconstructed from a snapshot, ``apply()`` always re-validates live
    immediately before writing, so a stale account of "what we planned" can never reach
    ``apply()`` — only a freshly computed, freshly validated ``Plan`` can."""
    section = _section(_DOCTRINE_HEADING)
    missing = missing_phrases(section, [
        "cannot be reconstructed from a snapshot",
        "re-validates live immediately before writing",
        "can never reach apply()",
        "only a freshly computed, freshly validated plan can",
    ])
    assert not missing, f"the trust property is not claimed: {missing}"


def test_ac3_a_plan_cannot_be_rebuilt_from_its_own_snapshot():
    """AC3 (the code half): ``Plan`` serializes for an approval UX but has **no**
    ``from_dict``, and its constructor refuses a hand-built call — so the guide's claim is
    structural, not aspirational."""
    assert hasattr(Plan, "to_dict") and hasattr(Plan, "to_json")
    assert not hasattr(Plan, "from_dict"), (
        "a Plan.from_dict would re-open the forge vector the trust property rests on")
    with pytest.raises(TypeError):
        Plan(entries=())


def test_ac3_a_stale_account_of_what_we_planned_cannot_reach_apply(monkeypatch, tmp_path):
    """AC3 (the amplifier's "deliberately stale reloaded plan"): three attempts, all closed.

    1. the plan's own **snapshot** (what a conversational agent would carry between turns)
       cannot be turned back into a ``Plan`` — there is nothing to call;
    2. handing that snapshot to ``apply()`` raises rather than writing;
    3. even the **real** ``Plan`` refuses once the document moves under it — ``apply`` re-reads
       and re-validates immediately before writing, and issues **zero** writes.
    """
    st = gr.stage(monkeypatch, tmp_path)          # install the doubles FIRST, then import
    from larkdocio.read.client import Client
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser
    from larkdocio.write import Anchor, EditRequest, WriteClient, apply, dry_run
    apply = reading_the_log(apply)

    doc_token = "STALEPLANDOCTOKEN"
    reader = Client("cli_x", "secret", "larksuite.com")
    docx, blocks = reader.get_docx_content(doc_token)
    root = Parser(Config()).parse_docx_tree(doc_token, blocks)
    plan = dry_run(
        [EditRequest(anchor=Anchor(quote="Revenue grew 12.4% in Q3.", breadcrumb=("Overview",)),
                     replacement="Revenue grew 15.0% in Q3.")],
        root, document_revision_id=docx.revision_id)

    snapshot = json.loads(plan.to_json())          # "what we planned", three turns ago
    assert snapshot["entries"] and snapshot["revision_guard"] == "active"

    writer = WriteClient("cli_y", "secret", "larksuite.com")
    with pytest.raises((TypeError, AttributeError)):
        apply(snapshot, writer, document_id=doc_token)   # (2) the snapshot is not a Plan

    # (3) the document moves under the plan — a human edits the anchored paragraph.
    st.documents.for_token(doc_token).patch("p1", {"update_text_elements": {
        "elements": [{"text_run": {"content": "Revenue grew 9.1% in Q3."}}]}})
    log = apply(plan, writer, document_id=doc_token)
    outcomes = [e.to_dict()["outcome"] for e in log.entries]
    assert outcomes == ["refused"], [e.to_dict() for e in log.entries]
    assert writer.patches == [], "a stale plan must issue ZERO writes"
    assert st.documents.for_token(doc_token).text_of("p1") == "Revenue grew 9.1% in Q3."


# --------------------------------------------------------------------------- #
# AC4 (d) — the two batch contracts, side by side, in LD-148's vocabulary.       #
# --------------------------------------------------------------------------- #

#: Every batch-disposition refusal reason, taken from the **code constants** so a rename
#: reddens here instead of silently diverging from the docs. LD-148 shipped eight; LD-206
#: added `permission-denied` (a scope denial reclassified SYSTEMIC).
LD148_REASONS = {
    Refusal.UNKNOWN_MENTION, Refusal.API_ERROR, Refusal.INVALID_REQUEST,
    Refusal.RATE_LIMITED, Refusal.TRANSPORT_FAILURE, Refusal.UNEXPECTED_ERROR,
    Refusal.UNVERIFIED_WRITE, Refusal.NOT_ATTEMPTED, Refusal.PERMISSION_DENIED,
}


def _shipped_dispositions() -> dict:
    """``{reason: Disposition}`` re-derived by CALLING the shipped classifier.

    Not a hand-list and not a read of the private table: each row is produced by handing
    ``classify_apply_exception`` the real exception class that provokes it, so the doc table's
    scope / outcome / landed columns are checked against the behaviour the engine actually
    has."""
    from larkdocio.errors import (
        LarkAPIError,
        LarkConfigError,
        LarkPermissionError,
        LarkRateLimitError,
    )

    probes = (
        (LarkAPIError("Code: 90204", code=90204, msg="id not found"), False),
        (LarkAPIError("connection reset"), False),              # code-less ⇒ the URLError wrap
        (LarkRateLimitError("slow down", code=99991400), False),
        # LD-206 — a scope denial: a CODED LarkAPIError subclass that is nevertheless
        # systemic, so it must not read as the entry-scoped `api-error` row above.
        (LarkPermissionError("Code: 99991672", code=99991672, msg="Access denied"), False),
        (LarkConfigError("un-emittable range"), False),
        (RuntimeError("a library bug"), False),
        (RuntimeError("failed after the write returned"), True),
    )
    out = {}
    for exc, wrote in probes:
        disposition = classify_apply_exception(exc, wrote=wrote)
        out[disposition.reason] = disposition
    assert len(out) == 7, out
    return out


def _apply_log_outcomes() -> set:
    """Every ``outcome`` a sheets :class:`ApplyLogEntry` factory can produce — read off the
    class's own source, so the vocabulary is code truth rather than a list to maintain."""
    outcomes = set(re.findall(r'cls\(outcome="([a-z-]+)"', inspect.getsource(ApplyLogEntry)))
    assert len(outcomes) >= 6, outcomes
    return outcomes


def _reason_rows() -> list:
    return _table_with(_section(_CONTRACTS_HEADING), "refusal reason", "scope", "outcome")


def test_ac4_the_contracts_section_states_both_contracts_side_by_side():
    """AC4: ONE place states both — docx **whole-batch, zero writes on refusal**; sheets
    **per-entry compare-and-swap, partial application possible, fully disclosed in the
    apply-log** (the maintainer-blessed doctrine)."""
    section = _section(_CONTRACTS_HEADING)
    missing = missing_phrases(section, [
        "whole batch",
        "zero writes",
        "per-entry compare-and-swap",
        "partial application is possible",
        "fully disclosed in the apply-log",
    ])
    assert not missing, f"the batch-contracts section omits {missing}"
    # side-by-side means one table with a column per surface, not two prose blocks.
    rows = _table_with(section, "docx-write", "sheets-write")
    assert len(rows) >= 4, f"the side-by-side table needs a row per question; got {len(rows)}"


def test_ac4_the_docx_contract_names_stale_document_and_the_zero_write_rule():
    """AC4: docx's whole-batch rule is named by its shipped refusal reason — and the
    per-entry ``stale-anchor`` skip is distinguished from it, because conflating the two is
    how "the whole batch refuses" becomes a claim the engine does not make."""
    from larkdocio.write.model.refusal import RefusalReason

    section = _section(_CONTRACTS_HEADING)
    assert RefusalReason.STALE_DOCUMENT.value in section, section
    assert RefusalReason.STALE_ANCHOR.value in section, (
        "the docx column must distinguish the per-entry stale-anchor skip from the "
        "whole-batch stale-document refusal")


def test_ac4_the_documented_reason_names_are_exactly_the_shipped_ones():
    """AC4: the reason column equals LD-148's shipped vocabulary — **bidirectionally**. A
    phantom name (a doc typo) and a dropped name (a reason shipped but undocumented) both
    redden."""
    documented = {_first_token(row["refusal reason"]) for row in _reason_rows()}
    phantom = sorted(documented - LD148_REASONS)
    missing = sorted(LD148_REASONS - documented)
    assert not phantom, f"the guide names refusal reasons the code lacks: {phantom}"
    assert not missing, f"the code has refusal reasons the guide omits: {missing}"


def test_ac4_the_scope_column_uses_only_the_shipped_scope_constants():
    """AC4: every code-quoted token in the scope column is one of the two shipped scope
    constants (``larkdocio.sheets.disposition``) — the two rows the classifier cannot produce
    say "plan time" / "after a halt" in prose instead of inventing a third scope."""
    for row in _reason_rows():
        token = _first_token(row["scope"])
        assert token in (None, ENTRY_SCOPED, SYSTEMIC), (row["refusal reason"], row["scope"])


def test_ac4_each_documented_row_matches_the_shipped_classifier():
    """AC4 (the load-bearing half): for every reason the **classifier** produces, the guide's
    scope / outcome / landed cells are re-derived from ``classify_apply_exception`` and
    compared. A doc that says "continues" where the engine halts reddens."""
    shipped = _shipped_dispositions()
    seen = 0
    for row in _reason_rows():
        reason = _first_token(row["refusal reason"])
        disposition = shipped.get(reason)
        if disposition is None:                      # unknown-mention / not-attempted
            continue
        seen += 1
        assert _first_token(row["scope"]) == disposition.scope, (reason, row)
        assert _first_token(row["outcome"]) == disposition.outcome, (reason, row)
        assert disposition.landed in prose(row["landed?"]), (reason, row)
        expected_batch = "halts" if disposition.halts else "continues"
        assert expected_batch in prose(row["the batch"]), (reason, row)
    assert seen == len(shipped), (
        f"only {seen} of {len(shipped)} classifier-produced reasons appear in the table")


def test_ac4_the_two_plan_time_and_post_halt_reasons_are_documented_as_such():
    """AC4: the two reasons the classifier cannot produce are still in the table, marked for
    what they are — ``unknown-mention`` is refused at **plan time**, ``not-attempted`` is
    what every entry after a halt gets."""
    rows = {_first_token(r["refusal reason"]): r for r in _reason_rows()}
    assert "plan" in prose(rows[Refusal.UNKNOWN_MENTION]["scope"]), rows[Refusal.UNKNOWN_MENTION]
    assert "halt" in prose(rows[Refusal.NOT_ATTEMPTED]["scope"] +
                           rows[Refusal.NOT_ATTEMPTED]["the batch"]), rows[Refusal.NOT_ATTEMPTED]


def test_ac4_the_complete_outcome_vocabulary_is_documented():
    """AC4: the six-value ``outcome`` vocabulary is stated in full, cross-checked against the
    outcomes the shipped ``ApplyLogEntry`` factories can produce."""
    section = _section(_CONTRACTS_HEADING)
    for outcome in sorted(_apply_log_outcomes()):
        assert f"`{outcome}`" in section, (
            f"the shipped apply-log outcome {outcome!r} is not documented in the "
            "batch-contracts section")


def test_ac4_the_mention_validation_disclosure_vocabulary_is_documented():
    """AC4: the plan's three mention-validation statuses are named (the disclosure half of
    the sheets contract — a check that cannot run is disclosed, never silently skipped)."""
    from larkdocio.sheets.plan import (
        MENTION_VALIDATION_ACTIVE,
        MENTION_VALIDATION_NOT_APPLICABLE,
        MENTION_VALIDATION_UNAVAILABLE,
    )

    section = _section(_CONTRACTS_HEADING)
    for status in (MENTION_VALIDATION_ACTIVE, MENTION_VALIDATION_UNAVAILABLE,
                   MENTION_VALIDATION_NOT_APPLICABLE):
        assert f"`{status}`" in section, f"mention_validation status {status!r} undocumented"
    assert "mention_validation" in section


def test_ac4_apply_log_complete_is_NOT_documented_as_a_docx_contract():
    """AC4 (honesty): ``apply-log-complete`` is **not** declared on docx-write — LD-148 said
    claiming it for docx would be a lie — so the side-by-side must say so, and this test
    derives the fact from the registry.

    **LD-586 transformed this arm; its reason is unchanged.** The reason was, and is, that the
    docx side of the comparison must not claim a guarantee docx does not declare. What changed
    is the phrase it required: ``sheets-write only`` was true when LD-148 wrote it and stopped
    being true when the two Base write surfaces adopted the contract — ``applies_to`` is now
    three surfaces, and the guard was pinning the exclusivity rather than the absence it cares
    about. So the surface list is now DERIVED from the registry and the docx absence is asserted
    directly.
    """
    caps = capabilities(full=True)["surfaces"]
    declared = {name for name, surface in caps.items()
                if "apply-log-complete" in surface.get("safety_contracts", [])}
    assert "sheets-write" in declared
    assert "docx-write" not in declared
    section = _section(_CONTRACTS_HEADING)
    assert "apply-log-complete" in section
    assert "sheets-write only" not in section, (
        "the contract is declared on more than sheets-write; do not restate the exclusivity"
    )
    for name in sorted(declared):
        assert name in section, f"{name} declares apply-log-complete and the section omits it"


def test_ac4_the_vocabulary_guard_bites_red_then_green():
    """AC4 (red-then-green): the SAME name check reddens on a renamed status and greens on
    the shipped table — so the cross-check is not decorative."""
    documented = {_first_token(row["refusal reason"]) for row in _reason_rows()}
    assert not (documented - LD148_REASONS) and not (LD148_REASONS - documented)

    typo = (documented - {Refusal.API_ERROR}) | {"api-failure"}
    assert sorted(typo - LD148_REASONS) == ["api-failure"]
    assert sorted(LD148_REASONS - typo) == [Refusal.API_ERROR]


# --------------------------------------------------------------------------- #
# AC5 (e) — the capability notes stop reading as an engine restriction.          #
# --------------------------------------------------------------------------- #

#: The verbatim sentences round-2 T0 flagged. Asserted **absent** — a doc fix that leaves the
#: misleading sentence in place next to the correction is not a fix.
OLD_MISLEADING = (
    "Writes run ONLY against API-created scratch docs, never a real document.",
    "writes run ONLY against self-provisioned disposable spreadsheets, never a real document.",
    "writes run ONLY against disposable scratch docs.",
)

_POLICY_PHRASES = (
    "this project's own test-suite policy",
    "not an engine restriction",
)


def _write_notes() -> dict:
    surfaces = capabilities(full=True)["surfaces"]
    return {sid: surfaces[sid]["credentials"]["note"]
            for sid in ("docx-write", "sheets-write")}


@pytest.mark.parametrize("surface_id", ["docx-write", "sheets-write"])
def test_ac5_the_capability_note_states_it_is_a_test_suite_policy(surface_id):
    """AC5 (T0): the note says plainly that the disposable-target rule is **this project's
    test-suite policy**, **not an engine restriction** on where a consumer may write."""
    note = _write_notes()[surface_id]
    missing = missing_phrases(note, _POLICY_PHRASES)
    assert not missing, f"{surface_id} note does not correct the misreading: {missing}\n{note}"


@pytest.mark.parametrize("surface_id,target", [
    ("docx-write", "may write to any document"),
    ("sheets-write", "may write to any spreadsheet"),
])
def test_ac5_the_capability_note_says_a_consumer_may_write_to_any_reachable_target(
        surface_id, target):
    """AC5: the positive half — the engine imposes no target restriction, so the note cannot
    be read as "this library refuses to write to my real document"."""
    note = prose(_write_notes()[surface_id])
    assert target in note, note


def test_ac5_the_old_misleading_sentences_are_gone_from_every_shipped_surface():
    """AC5 (the negative test the amplifier asks for): the exact pre-fix sentences appear
    **nowhere** in ``capabilities()`` or ``guide()``."""
    haystacks = {"capabilities()": json.dumps(capabilities(full=True)), "guide()": guide(full=True)}
    for where, text in haystacks.items():
        normalized = prose(text)
        for sentence in OLD_MISLEADING:
            assert prose(sentence) not in normalized, (
                f"{where} still ships the misleading T0 phrasing: {sentence!r}")


def test_ac5_the_guide_makes_the_same_correction_where_a_consumer_reads_it():
    """AC5: the guide's own write-testing section and its ``.env`` credential block carry the
    correction — the two places a consumer meets the rule."""
    text = guide(full=True)
    creds = _section("## Credentials & `.env` setup — the READ / WRITE app split")
    assert missing_phrases(creds, _POLICY_PHRASES) == [], creds
    assert missing_phrases(text, ["not an engine restriction"]) == []


def test_ac5_the_disposables_doctrine_is_still_stated_for_the_test_suite():
    """AC5 (the fix must not throw the rule away): larkdocio's OWN live write gates still
    write only to a disposable the harness provisioned — the correction is about whose rule
    it is, not about relaxing it."""
    section = _section("### The disposables doctrine")
    missing = missing_phrases(section, [
        "never a real document", "never the canary", "self-provisions",
    ])
    assert not missing, f"the disposables doctrine lost its own claims: {missing}"


# --------------------------------------------------------------------------- #
# AC6 (f) — language=None documented on NewBlock.code itself.                    #
# --------------------------------------------------------------------------- #

def test_ac6_the_signature_default_is_none():
    """AC6: ``language`` really defaults to ``None`` — the docstring below documents a fact
    about the signature, so pin the signature too."""
    assert inspect.signature(NewBlock.code).parameters["language"].default is None


def test_ac6_new_block_code_documents_the_bare_fence_choice():
    """AC6 (T7/T8): ``NewBlock.code``'s own docstring says ``None`` is the **correct** choice
    for content that is not code (ASCII art / plain preformatted text) — the fact that only
    surfaced in round 2 as a side-effect of an unrelated refusal message."""
    doc = NewBlock.code.__doc__ or ""
    missing = missing_phrases(doc, [
        "bare fence", "ascii art", "not code", "supported_code_languages",
    ])
    assert not missing, f"NewBlock.code's docstring omits {missing}:\n{doc}"


def test_ac6_the_docstring_states_the_token_count_the_code_actually_has():
    """AC6: "alongside the 65 real language tokens" is a number that must not rot — it is
    checked against ``supported_code_languages()``, so adding a token reddens the doc."""
    doc = NewBlock.code.__doc__ or ""
    count = len(supported_code_languages())
    assert str(count) in doc, (
        f"the docstring must name the real token count ({count}) — got:\n{doc}")


def test_ac6_the_guide_documents_the_bare_fence_choice_too():
    """AC6: the same guidance is in the shipped guide, where a consumer authoring content
    reads it (the docstring alone is ``help()``-only knowledge — the round-2 complaint)."""
    text = guide(full=True)
    assert "language=None" in text
    missing = missing_phrases(_section("### Recipe: the docx write handshake"), [
        "language=none", "bare fence",
    ])
    assert not missing, f"the write-handshake section omits {missing}"


# --------------------------------------------------------------------------- #
# AC7 (g) — SubSpanEditRequest + editing a code block, as EXECUTING recipes.     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slug", NEW_SLUGS)
def test_ac7_each_new_recipe_ships_specced_and_warned(slug):
    """AC7/AC9: each new recipe is in the guide, has an execution spec, carries exactly one
    python block, and — since all three author into a document — carries the D9 concurrency
    warning in its own preamble (the derived ``authoring_recipe_slugs`` set covers them)."""
    assert slug in gr.recipe_blocks(), sorted(gr.recipe_blocks())
    assert slug in gr.SPEC_BY_SLUG
    assert len(gr.recipe_blocks()[slug]) == 1
    assert slug in gr.authoring_recipe_slugs(), gr.authoring_recipe_slugs()
    assert missing_phrases(gr.recipe_preamble(slug), gr.CONCURRENCY_WARNING_PHRASES) == []


def test_ac7_the_subspan_recipe_changes_only_the_span(monkeypatch, tmp_path):
    """AC7 (T4): the sub-span recipe executes, and its plan entry proves the difference from
    an ``EditRequest`` — ``before``/``after`` are the **span**, not the whole block, and the
    surrounding text is intact afterwards."""
    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run(SUBSPAN_SLUG)
    (entry,) = ns["plan"].entries
    d = entry.to_dict()
    assert d["op"] == "subspan" and d["outcome"] == "resolved", d
    assert d["before"] == "12.4%" and d["after"] == "15.0%", d
    document = st.documents.for_token(ns["doc_token"])
    assert document.text_of("p1") == "Revenue grew 15.0% in Q3.", document.text_of("p1")
    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"]


def test_ac7_the_subspan_preamble_states_the_exactly_once_rule():
    """AC7: the recipe teaches the two things a sub-span edit refuses on — a span that is not
    **exactly once** in the block, and a span crossing runs of differing style."""
    missing = missing_phrases(gr.recipe_preamble(SUBSPAN_SLUG), [
        "exactly once", "style",
    ])
    assert not missing, f"the sub-span recipe preamble omits {missing}"


def test_ac7_the_code_edit_recipe_rewrites_a_code_block(monkeypatch, tmp_path):
    """AC7 (T9): the code-block recipe executes — it authors a fenced block, then rewrites
    the block's body with an ``EditRequest`` (the operation that was ``help()``-only), and the
    reader renders the new body back inside its language fence."""
    import harness

    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run(CODE_EDIT_SLUG)
    document = st.documents.for_token(ns["doc_token"])
    body = document.text_of(ns["code_block_id"])
    assert "def total(rows):" in body and "    return sum(rows)" in body, repr(body)
    markdown = harness.render(document.block_dicts(), doc_id=ns["doc_token"])
    assert "```python\ndef total(rows):\n    return sum(rows)" in markdown, markdown
    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])


def test_ac7_the_code_edit_recipe_demonstrates_the_bare_fence(monkeypatch, tmp_path):
    """AC7 + AC6: the same recipe authors a ``language=None`` block for content that is not
    code, and the reader emits a **bare** fence for it — so (f)'s guidance has a worked
    example, not just a sentence."""
    import harness

    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run(CODE_EDIT_SLUG)
    document = st.documents.for_token(ns["doc_token"])
    markdown = harness.render(document.block_dicts(), doc_id=ns["doc_token"])
    assert re.search(r"^```$", markdown, flags=re.MULTILINE), (
        "the recipe must produce a BARE fence (language=None):\n" + markdown)
    assert ns["ascii_art_block_id"], ns.keys()


# --------------------------------------------------------------------------- #
# AC8 (h) — formula guidance matches what LD-149 actually shipped.               #
# --------------------------------------------------------------------------- #

def _formula_section() -> str:
    return _section("### Recipe: write a live formula into a sheet")


def test_ac8_the_guide_documents_the_formula_capability_the_registry_projects():
    """AC8: the formula family is a real projected op, and the guide names it and its request
    type — cross-checked against ``capabilities()`` rather than trusted."""
    ops = {op["name"]: op for op in capabilities(full=True)["surfaces"]["sheets-write"]["operations"]}
    assert "formula" in ops, sorted(ops)
    request_type = "FormulaWriteRequest"
    assert request_type in ops["formula"]["request_types"], ops["formula"]
    section = _formula_section()
    assert request_type in section
    assert "formula" in _section("### Recipe: the sheets write handshake")


def test_ac8_the_equals_prefix_note_behavior_is_documented_from_the_shipped_note():
    """AC8: the ``"="``-prefixed-plain-string dry-run note's load-bearing claims are required
    of the guide **by deriving them from the shipped constant** — so a change to
    ``INERT_STRING_NOTE`` cannot leave the guide describing the old behaviour."""
    section = _formula_section()
    assert "preview_note" in section, section
    for claim in ("INERT TEXT", "valueInputOption", "FormulaWriteRequest.for_a1"):
        assert claim in INERT_STRING_NOTE, claim          # the constant really says it
        assert claim in section, (
            f"the guide's formula section must state {claim!r} — the shipped note does")


def test_ac8_the_precondition_semantics_match_the_shipped_decision():
    """AC8: LD-149 decided the precondition compares the **expression**, not the computed
    value. The requirement is read off the shipped preview note the engine actually stamps,
    so a change of basis in code would redden the doc guard."""
    from larkdocio.sheets.formula import formula_preview_note

    note = formula_preview_note("=SUM(B3:B8)", current_expression="=SUM(A1:A2)",
                                current_computed_value=3)
    assert note["precondition_compares"] == "expression", note
    missing = missing_phrases(_formula_section(), [
        f"the precondition compares the {note['precondition_compares']}",
        "not the computed value",
    ])
    assert not missing, f"the formula section omits {missing}"


def test_ac8_the_inert_string_trap_is_stated_as_a_limitation():
    """AC8: the one genuine limitation the probe found — a plain ``"="`` string can **never**
    evaluate, because this API has no ``valueInputOption`` — is stated loudly, so a consumer
    cannot ship inert text believing it is a total (round-2 T23)."""
    missing = missing_phrases(_formula_section(), [
        "is not a formula", "inert text", "no flag can make a plain string evaluate",
    ])
    assert not missing, f"the formula section omits {missing}"


# --------------------------------------------------------------------------- #
# AC9 — every new claim is content-guarded and every new recipe EXECUTES.        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slug", NEW_SLUGS)
def test_ac9_each_new_recipe_executes_offline(slug, monkeypatch, tmp_path):
    """AC9: the recipe is extracted from the shipped guide verbatim and executed in a
    builtins-only namespace against fixtures + injected transports, then checked for what it
    claims to have produced (the LD-133 harness; ``test_discovery_truth`` runs the same spec
    set, this pins the three new ones by name)."""
    spec = gr.SPEC_BY_SLUG[slug]
    st = gr.stage(monkeypatch, tmp_path, empty_document=spec.empty_document,
                   base_links=spec.base_links)
    spec.check(st.run(slug))


@pytest.mark.parametrize("slug", NEW_SLUGS)
def test_ac9_each_new_recipe_has_no_undefined_free_variable(slug):
    """AC9 (the F13 check, applied to the new recipes): a recipe cannot ship loading a name
    it never binds — the failure a ``compile()``-only gate is blind to."""
    assert gr.undefined_free_names(gr.recipe_source(slug)) == []


def test_ac9_a_recipe_naming_a_nonexistent_op_would_redden(monkeypatch, tmp_path):
    """AC9 (the amplifier's negative case): the harness that greens the shipped multi-turn
    recipe **fails** when the recipe names an op that does not exist — so the execution guard
    is what makes the recipe trustworthy, not the prose around it."""
    src = gr.recipe_source(MULTI_TURN_SLUG)
    broken = src.replace("SubSpanEditRequest", "SubSpanReplaceRequest")
    assert broken != src, "the mutation did not apply"
    st = gr.stage(monkeypatch, tmp_path)
    with pytest.raises((ImportError, AttributeError, NameError)):
        st.run(MULTI_TURN_SLUG, source=broken)
    gr.SPEC_BY_SLUG[MULTI_TURN_SLUG].check(st.run(MULTI_TURN_SLUG))


def test_ac9_the_new_sections_are_reachable_from_the_guides_own_structure():
    """AC9: the two new doctrine/contract sections are real ``##`` sections (so the section
    readers above are not asserting against an accident of substring order), and the recipe
    headings are inside the ``## Recipes`` section."""
    text = guide(full=True)
    for heading in (_DOCTRINE_HEADING, _CONTRACTS_HEADING):
        assert re.search(rf"^{re.escape(heading)}", text, flags=re.MULTILINE), heading
    for slug in NEW_SLUGS:
        blocks = gr.recipe_blocks()[slug]
        assert all(b.in_recipes_section for b in blocks), slug


# --------------------------------------------------------------------------- #
# LD-149's recorded Minor — the dead `dev/probes/...` reference.                 #
# --------------------------------------------------------------------------- #

_PROBE_PATH_RE = re.compile(r"dev/probes/[0-9A-Za-z._/-]+")


@private_tree.citations
def test_every_dev_probes_path_the_repo_cites_exists():
    """LD-149's Minor: its issue file cites ``dev/probes/2026-07-28-LD-149-formula/``
    (README + script + raw JSON) as committed, and the handoff tells QA to RUN that script.

    The guard is the general form of the fix: every ``dev/probes/...`` path referenced from
    any markdown under ``progress/`` or ``dev/`` must exist on disk, so a probe-evidence
    reference cannot go dead again (nor be "fixed" by deleting the artifacts)."""
    sources = sorted(_ROOT.glob("progress/**/*.md")) + sorted(_ROOT.glob("dev/**/*.md"))
    assert sources, "no markdown found to scan"
    dead = []
    cited = 0
    for source in sources:
        for raw in _PROBE_PATH_RE.findall(source.read_text(encoding="utf-8")):
            path = raw.rstrip(".,;:)`")
            cited += 1
            if not (_ROOT / path).exists():
                dead.append(f"{source.relative_to(_ROOT)} → {path}")
    assert cited, "expected at least one dev/probes/... citation (LD-149's)"
    assert not dead, "dead dev/probes references:\n" + "\n".join(sorted(set(dead)))
