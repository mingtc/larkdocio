"""LD-569 — the write-recipe router's two missing rows, its foreign-text mechanism, its
forward pointer to the conservation contract, and the flatten/refuse claim it got wrong.

Every assertion here is a **projection check**, not a spelling check: the facts the two new
rows state are authored once — in :mod:`larkdocio.write.absences` (the checkbox and the
table-grow absences), in :data:`larkdocio.model.conservation.CONSERVATION_CONTRACT` (what
happens to a table when a document is re-authored) and in ``compose()`` itself (which inline
constructs refuse) — and the router carries them. Each test therefore asserts the shared text
on **both** sides, so it reddens whichever side moves.
"""
import re

import pytest

from test_opaque_marker_conservation import _page, _table, _tree

import larkdocio
from larkdocio.model import project_block_ids
from larkdocio.model.conservation import CONSERVATION_CONTRACT
from larkdocio.write.absences import DOCX_WRITE_ABSENCES
from larkdocio.write.compose import compose
from larkdocio.write.reconcile import reconcile
from larkdocio.write.compiler import compile_reconciliation
from domain_vocabulary import RETIRED_ID

ROUTER = ("Which write recipe do you need? — add, change, update or delete content "
          "in a document")

CONCURRENCY_SECTION = ("Do not edit the document while an authoring session runs "
                       "(the concurrency doctrine)")
OBJECT_LEVEL_SECTION = "Recipe: change a document at the object level — no Markdown anywhere"
HANDSHAKE_SECTION = "Recipe: the docx write handshake"
RECONCILE_SECTION = ("Recipe: update an existing document — change or edit many blocks at "
                     "once, without re-authoring it")


def _router() -> str:
    return larkdocio.guide(section=ROUTER)


def _rows():
    rows = [ln for ln in _router().splitlines() if ln.startswith("|")]
    return [r for r in rows if not set(r) <= set("|- :")][1:]


def _row(needle: str) -> str:
    hits = [r for r in _rows() if needle.lower() in r.lower()]
    assert len(hits) == 1, f"expected exactly one router row matching {needle!r}: {hits}"
    return hits[0]


#: LD-569 wrote this file against ``todo-done-bit-is-not-editable``. LD-574 shipped the bit,
#: so that row's slot now holds the residual — the reason is preserved inside the successor's
#: ``evidence``, and this constant is the one place this file follows the move.
CHECKBOX_ABSENCE_ID = "no-block-property-edit-beyond-text"

#: LD-569 wrote this file against ``no-grow-operation-for-an-existing-table``. LD-575 shipped
#: the append, so that row's slot now holds the narrowed residual — the reason is preserved
#: inside the successor's ``evidence``, and this constant is the one place this file follows the
#: move.
TABLE_GRID_ABSENCE_ID = "no-table-grid-change-beyond-appending-a-row"

#: The recipe the grow row routes to, now that a gated route exists to route to.
TABLE_GROW_SECTION = "Recipe: add a row to a table that already exists"


def _absence(row_id: str) -> dict:
    hits = [r for r in DOCX_WRITE_ABSENCES if r["id"] == row_id]
    assert hits, (
        f"the docx-write absence register no longer carries {row_id!r} — the router row that "
        "projects it is now unanchored prose and must be re-derived, not left standing")
    return hits[0]


# --------------------------------------------------------------------------- #
# AC1 — the checkbox row.                                                      #
# --------------------------------------------------------------------------- #

def test_ac1_the_router_has_a_row_for_changing_a_checkbox():
    row = _row("change a checkbox")
    assert "todo.style.done" in row, row


def test_ac1_the_checkbox_row_carries_the_mandated_sentence_and_not_the_false_one():
    """LD-569's reason, unchanged: the row's claim must be scoped to what is true of the
    GATED route, and a sentence wider than the evidence is the defect. What is true of it
    inverted when LD-574 shipped the bit — so the sentence that was mandated
    (*"no plan-gated, declared write operation flips `todo.style.done`"*) is now the false
    one, and it joins the banned list it used to be the fix for."""
    row = _row("change a checkbox")
    assert "the gated route does this" in row.lower(), row
    for banned in ("no plan-gated, declared write operation flips",
                   "reports it applied while the bit does not move",
                   "no shipped op", "no shipped operation flips"):
        assert banned not in row.lower(), f"{banned!r} is now the FALSE claim: {row}"


def test_ac1_the_checkbox_row_states_the_RESIDUAL_as_a_typed_refusal():
    """The successor of LD-569's open-defect assertion. Its reason holds: a row may not leave
    a caller thinking a request will quietly do nothing. There is no silent no-op left, so
    what the row owes is the typed refusal that replaced it."""
    row = _row("change a checkbox")
    assert "change-not-expressible" in row, row
    assert "open defect" not in row.lower(), row
    assert "never reported as applied" in _absence(CHECKBOX_ABSENCE_ID)["statement"].lower()


@pytest.mark.parametrize("phrase", ("todo.style.done", "NewBlock.todo(text, done=True)"))
def test_ac1_the_checkbox_row_projects_the_register_row(phrase):
    """Bidirectional: the phrase must be in the register AND in the router. Change either
    side alone and this reddens — which is the whole point of one authoring site."""
    register = _absence(CHECKBOX_ABSENCE_ID)
    joined = " ".join(register[k] for k in ("statement", "evidence", "instead"))
    assert phrase in joined, f"{phrase!r} left the register row"
    assert phrase in _row("change a checkbox"), f"{phrase!r} left the router row"


def test_ac1_the_checkbox_row_names_the_register_by_its_own_id():
    assert CHECKBOX_ABSENCE_ID in _row("change a checkbox")


# --------------------------------------------------------------------------- #
# AC2 — the table-grow row.                                                    #
# --------------------------------------------------------------------------- #

def test_ac2_the_router_has_a_row_for_growing_a_table():
    row = _row("add or remove a table row")
    assert HANDSHAKE_SECTION in row, row


def test_ac2_the_table_grow_row_names_the_GATED_route_and_the_other_ones_cost():
    """TRANSFORMED, not struck (LD-575). LD-569's reason holds: the row must name every route
    that exists **with what it costs**, because the cost is the whole decision. What changed is
    the set of routes — a gated one now exists, and the escape hatch is no longer the only way
    to keep a block id, so demanding the row advertise the hatch's four disclaimers would now
    be demanding it recommend the wrong route. The cost that still has to be stated is the
    recreate route's, and it is the same one it always was: the ids."""
    row = _row("add or remove a table row")
    assert "the gated route does this" in row.lower(), row
    assert TABLE_GROW_SECTION in row, row
    assert "block ids" in row.lower(), "the recreate route's cost is the ids: " + row
    for banned in ("no plan-gated operation grows or shrinks a table",
                   "has no gated verb for its grid"):
        assert banned not in row.lower(), f"{banned!r} is now the FALSE claim: {row}"


def test_ac2_the_escape_hatch_is_DESCRIBED_not_recommended():
    """Same discipline AC3 imposes on the sub-span row: this issue may not adopt a posture
    on behalf of a caller."""
    row = _row("add or remove a table row").lower()
    for word in ("recommend", "prefer", "you should", "always use", "the best way"):
        assert word not in row, f"{word!r} turns a description into a recommendation: {row}"


def test_ac2_the_table_grow_row_stays_inside_the_measurement_it_cites():
    """The register's MEASURED clause covers appending at the end. Mid-table insertion and
    removal are explicitly unmeasured, and the router may not quietly widen either — nor
    restate an unmeasured route as one Lark was seen to refuse."""
    row = _row("add or remove a table row")
    register = _absence(TABLE_GRID_ABSENCE_ID)
    assert "MID-TABLE insertion" in register["evidence"]
    assert "appends" in row.lower() and "end" in row.lower(), row
    assert "unmeasured" in row.lower(), (
        "removal and mid-table insertion have no measurement here and the row must say so: "
        + row)
    for overclaim in ("lark refuses", "impossible", "not possible"):
        assert overclaim not in row.lower(), f"{overclaim!r} exceeds the evidence: {row}"


def test_ac2_the_table_grow_row_projects_the_register_row():
    register = _absence(TABLE_GRID_ABSENCE_ID)
    assert TABLE_GRID_ABSENCE_ID in _row("add or remove a table row")
    assert "REMOVES a row or a column" in register["statement"]


def test_ac2_the_table_grow_rows_typed_refusal_is_the_registers_own():
    """The one-constant rule: the router names the refusal by the WIRE value the enum carries,
    and the register names the same one — never a second spelling of either."""
    from larkdocio.write.model import RefusalReason

    wire = RefusalReason.TABLE_GROW_UNSUPPORTED.value
    assert wire in _absence(TABLE_GRID_ABSENCE_ID)["statement"]
    assert wire in _row("add or remove a table row")


def test_ac2_editing_a_cell_stays_a_different_job_from_growing_the_grid():
    """The register draws the line — a cell's TEXT is one operation and the GRID is another —
    and the two router rows must not blur into one another."""
    register = _absence(TABLE_GRID_ABSENCE_ID)
    assert "CELLS are editable" in register["statement"]
    assert "fix a table" in _row("add or remove a table row").lower()


# --------------------------------------------------------------------------- #
# AC3 — foreign TEXT, as a mechanism, in its own indicative sentence.          #
# --------------------------------------------------------------------------- #

FOREIGN_TEXT_NEEDLE = "text another writer added to that block after your read"


def _sentences(cell: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", cell) if s.strip()]


def test_ac3_the_sub_span_row_names_foreign_TEXT_not_only_styling():
    row = _row("change PART of a paragraph")
    assert FOREIGN_TEXT_NEEDLE in row, row
    assert "`applied`" in row, "the undetectability half is the point: " + row


def test_ac3_the_foreign_text_statement_is_a_SEPARATE_INDICATIVE_sentence():
    """The trap this test exists for: the cell's first sentence is an imperative
    (*"Take this row … when …"*), and a foreign-text clause appended to it would inherit
    that recommendation and adopt a posture on shared documents by grammar alone."""
    row = _row("change PART of a paragraph")
    sentence = next(s for s in _sentences(row) if FOREIGN_TEXT_NEEDLE in s)
    assert "Take this row" not in sentence, (
        "the foreign-text statement has been folded into the imperative sentence, which "
        f"turns a mechanism into a recommendation: {sentence}")
    lowered = sentence.lower()
    for verb in ("prefer", "should", "always", "take this row", "instead of the whole-block"):
        assert verb not in lowered, f"{verb!r} states a posture, not a mechanism: {sentence}"


def test_ac3_the_imperative_sentence_itself_is_untouched():
    row = _row("change PART of a paragraph")
    assert ("**Take this row, not the whole-block rows above, when the block carries styling "
            "you mean to keep:**") in row, row


def test_ac3_the_guard_window_is_cross_referenced_by_SECTION_NAME_not_restated():
    """LD-566 authored the window sentence; this row points at it."""
    row = _row("change PART of a paragraph")
    assert CONCURRENCY_SECTION in row, row
    assert "plan-to-apply" not in row.lower(), (
        "the window sentence has been restated in the router — it has one authoring site "
        "and this row points at it: " + row)
    assert larkdocio.guide(section=CONCURRENCY_SECTION).startswith("### " + CONCURRENCY_SECTION)


# --------------------------------------------------------------------------- #
# AC4 / AC5 — tables in the whole-document row, and the forward pointer.       #
# --------------------------------------------------------------------------- #

TABLE_SENTENCE = CONSERVATION_CONTRACT[CONSERVATION_CONTRACT.index("A table is opaque"):]


def test_ac4_the_whole_document_row_names_tables_by_PROJECTING_the_contract():
    """Not a parallel sentence — the contract's own words, so the two cannot drift."""
    row = _row("the whole document, or many blocks at once")
    assert TABLE_SENTENCE in row, (
        "the whole-document row must carry the conservation contract's table sentence "
        f"verbatim:\n{TABLE_SENTENCE!r}\n{row}")


def test_ac4_the_table_claim_is_what_the_engine_actually_does():
    """The derivation, run rather than asserted: an edited table cell in the edited
    Markdown compiles to nothing at all, and the plan says so."""
    blocks, _cells = _table("tbl", "doc")
    tree = _tree([_page(children=["p0", "tbl"]),
                  {"block_id": "p0", "parent_id": "doc", "block_type": 2,
                   "text": {"elements": [{"text_run": {"content": "keep"}}]}},
                  *blocks])
    projection = project_block_ids(tree)
    edited = projection.markdown.replace("r0c0", "r0c0 CHANGED")
    assert edited != projection.markdown

    plan = reconcile(projection, edited)
    assert plan.ok, plan
    assert "tbl" in plan.conserved_block_ids, plan.entries
    assert compile_reconciliation(plan, projection) == (), (
        "an edited table cell must compile to zero requests — the silence the router row "
        "now discloses")


def test_ac5_the_router_carries_the_FORWARD_pointer_to_the_conservation_contract():
    router = _router()
    assert RECONCILE_SECTION in router, router[:400]
    assert "A block the Markdown cannot express is conserved, not destroyed" in router, (
        "the forward pointer must name the paragraph that states the contract, not just the "
        "recipe it lives in")
    assert 'block_projection_support' in router, (
        "the machine-readable form of the contract belongs beside the prose one")


def test_ac5_the_existing_back_pointer_is_still_there():
    """The contract → router direction already existed; this issue adds the other one and
    mints no second statement."""
    body = larkdocio.guide(section=RECONCILE_SECTION)
    assert "for what an edited block costs, see the routing table above" in body


def test_ac5_the_contract_is_not_re_authored_in_the_router():
    """Everything the router says about conservation is either the contract's own bytes or
    a pointer at them."""
    router = _router()
    minted = "Conservation is the default posture and destruction is never inferred"
    assert minted in CONSERVATION_CONTRACT
    assert minted not in router, (
        "the router has grown a second copy of the contract's body: " + minted)


# --------------------------------------------------------------------------- #
# AC5b — the flatten/refuse claim, against measured compose().                 #
# --------------------------------------------------------------------------- #

def _composes(markdown: str) -> bool:
    try:
        compose(markdown)
    except Exception:
        return False
    return True


def test_ac5b_the_url_as_label_link_shape_really_does_compose():
    assert _composes("Reference: [https://x](https://x)")
    assert not _composes("Reference: [the doc](https://x)")
    assert not _composes("**bold** text")
    assert not _composes("*italic* text")


def test_ac5b_the_router_row_no_longer_says_every_link_refuses():
    row = _row("the whole document, or many blocks at once")
    assert "or a link inside one refuses the whole batch" not in row, (
        "the uncorrected claim is still here — a link whose label is its own url composes: "
        + row)
    assert "labelled link" in row.replace("*", "").lower(), row
    assert "[https://x](https://x)" in row, (
        "the one link shape that does NOT refuse is named, because that is the shape a "
        "consumer writes by accident: " + row)


def test_ac5b_the_refusal_token_the_row_names_is_the_one_the_engine_raises():
    row = _row("the whole document, or many blocks at once")
    assert "`not-in-dialect`" in row
    try:
        compose("[the doc](https://x)")
    except Exception as exc:  # RefusedError
        assert exc.refusal.reason.value == "not-in-dialect", exc.refusal.reason
    else:  # pragma: no cover - the shape above refuses
        pytest.fail("a labelled link must refuse")


# --------------------------------------------------------------------------- #
# AC8 — the two new rows are routed, counted and enrolled.                     #
# --------------------------------------------------------------------------- #

def test_ac8_the_router_now_has_fourteen_rows():
    assert len(_rows()) == 14, [r[:60] for r in _rows()]


@pytest.mark.parametrize("needle,section", [
    # LD-574 moved the checkbox row's destination, and only its destination: the escape
    # hatch it used to route to is no longer the route, so it points at the reconciliation
    # recipe that now performs the flip. The row COUNT is untouched (14).
    ("change a checkbox", RECONCILE_SECTION),
    ("add or remove a table row", HANDSHAKE_SECTION),
])
def test_ac8_each_new_row_routes_to_a_section_that_resolves(needle, section):
    assert section in _row(needle)
    assert larkdocio.guide(section=section).startswith("### " + section)


@pytest.mark.parametrize("needle", ("change a checkbox", "add or remove a table row"))
def test_ac9_the_new_rows_ship_consumer_language_only(needle):
    """GUIDE.md is in the consumer corpus: no issue ids, no round vocabulary, no roles."""
    row = _row(needle)
    for pattern in (r"LD-\d+", RETIRED_ID.pattern, r"AC\d", r"\b[DSTF]\d{1,2}\b", r"\bPM\b",
                    r"dogfood"):
        assert not re.search(pattern, row), f"{pattern!r} reached shipped bytes: {row}"
