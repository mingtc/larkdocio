"""LD-562 — an insert's apply-log entry discloses what it COST, measured, and what follows.

Two undisclosed things, one file. Both are **disclosure only**: no route changed, nothing was
fenced, and no behaviour moved.

**Part A — the apply log states the consequence, never the predicate.** An insert takes one of
two routes and the consumer could not tell which: a table that is an insert's only block and
fits the one-call envelope goes out whole and atomic; everything else is created, grown and
filled across many calls, and a failure partway through leaves a partly-built table in a real
document. What lands in the log is neither the shape test nor the ceiling — it is a
**measurement**: the number of MUTATING write calls the engine actually issued for that entry,
plus the consequence derived from it. Three properties are load-bearing and each has its own
test here:

* it is on **every** ``inserted`` entry, both routes — absence-means-atomic would be an
  inference, which is the same defect one layer up;
* it is **counted, never predicted** — the engine's own helpers report what they issued, so
  the number cannot drift away from the calls when a batch size or a ceiling changes. The
  proof is an equality against the calls the double actually received, plus a shrunk batch
  ceiling that a re-derived arithmetic would get wrong;
* **"not atomic" derives from the measured count**, never from which branch ran — flat content
  on the create-grow-fill route is exactly one call, so a flag keyed on the branch would be a
  false disclosure.

**Part B — the cost of ``patch_block`` is stated at both doors it is reached through.** It is
outside the plan gate, outside the whole-document compare-and-swap and outside the refusal
set; the caller owns the read-back. Stated once, projected into the method's own docstring and
into the guide's write-recipe router — as prose beside that table, never a row in it.

Everything here is offline. The live arm is ``tests/test_live_write_authoring_gate.py``
(``pytest -m live_write``).
"""
import importlib
import json
import pathlib
import re

import pytest

from larkdocio.write import (
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewParagraph,
    apply,
    dry_run,
)
from larkdocio.write.client import PATCH_BLOCK_COST, WriteClient
from larkdocio.write.model.applylog import (
    INSERT_ATOMIC_KEY,
    INSERT_COST_CONTRACT,
    INSERT_WRITE_CALLS_KEY,
    ApplyLog,
    ApplyLogEntry,
)

from write_harness import LiveTreeOpener, _client, _FakeHTTPResponse, _page, _para, _patch_ok

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio"
GUIDE = PACKAGE / "GUIDE.md"

SEED = [("s1", "Section One"), ("a1", "Alpha body paragraph."),
        ("s2", "Section Two"), ("b1", "Beta body paragraph.")]


class GrowingTreeOpener(LiveTreeOpener):
    """:class:`LiveTreeOpener`, plus the ONE thing the create-grow-fill route needs of a live
    document that the base double leaves as a no-op: an ``insert_table_row`` /
    ``insert_table_column`` PATCH really appends the line's cells.

    Without it a grown table's fill addresses the seed grid and raises, so the grow calls
    could never be counted against a table that actually grew. Local to this file on purpose
    — it is this issue's measurement rig, not a change to the shared harness.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.grids = {}

    def _provision_cells(self, table_id, payload):
        provisioned = super()._provision_cells(table_id, payload)
        if payload.get("block_type") == 31:
            prop = (payload.get("table") or {}).get("property") or {}
            self.grids[table_id] = [int(prop.get("row_size") or 0),
                                    int(prop.get("column_size") or 0)]
        return provisioned

    def _new_cell(self):
        cell_id, inner_id = self._new_id(), self._new_id()
        self.block_types[cell_id], self.block_types[inner_id] = 32, 2
        self.texts[inner_id] = ""
        self.children[cell_id] = [inner_id]
        return cell_id

    def _append_line(self, table_id, body):
        rows, columns = self.grids.get(table_id, [0, 0])
        cells = list(self.children.get(table_id, ()))
        if "insert_table_row" in body:
            cells += [self._new_cell() for _ in range(columns)]
            rows += 1
        else:
            grown = []
            for row in range(rows):
                grown += cells[row * columns:(row + 1) * columns] + [self._new_cell()]
            cells, columns = grown, columns + 1
        self.children[table_id] = cells
        self.grids[table_id] = [rows, columns]

    def __call__(self, req, timeout=30):
        body = json.loads(req.data.decode()) if req.data else None
        if req.get_method() == "PATCH" and isinstance(body, dict) and (
                "insert_table_row" in body or "insert_table_column" in body):
            path = req.full_url.split(".com", 1)[-1]
            self.calls.append({"method": "PATCH", "path": path, "body": body})
            self._append_line(path.rsplit("/blocks/", 1)[-1].split("?")[0], body)
            return _FakeHTTPResponse(_patch_ok())
        return super().__call__(req, timeout)


def _seed_tree():
    return _page(*[_para(bid, text) for bid, text in SEED])


def _seed_opener(**kwargs):
    return GrowingTreeOpener(children={"root": [bid for bid, _ in SEED]},
                             texts=dict(SEED), **kwargs)


def _table(rows, columns):
    return NewBlock.table([[f"r{r}c{c}" for c in range(columns)] for r in range(rows)])


def _insert(block_id, content, position=InsertPosition.AFTER):
    return InsertRequest(reference=AnchorById(block_id=block_id), position=position,
                         content=tuple(content))


def _applied(content, *, block_id="a1"):
    """Apply ONE insert of ``content`` and hand back ``(entry, opener)``.

    One entry per plan, so every mutating call the double received belongs to that entry —
    which is what makes the equality assertions below a measurement rather than a guess.
    """
    opener = _seed_opener()
    log = apply(dry_run([_insert(block_id, content)], _seed_tree()), _client(opener), "doc562")
    return log.entries[0], opener


# --------------------------------------------------------------------------- #
# AC1(a) — present on EVERY inserted entry, both routes                         #
# --------------------------------------------------------------------------- #

def test_a_plain_paragraph_insert_discloses_its_measured_cost():
    entry, opener = _applied((NewParagraph("just a paragraph"),))

    assert entry.outcome == "inserted"
    payload = entry.to_dict()
    assert payload[INSERT_WRITE_CALLS_KEY] == len(opener.writes) == 1
    assert payload[INSERT_ATOMIC_KEY] is True


def test_the_one_call_table_route_discloses_one_call_and_atomic():
    entry, opener = _applied((_table(6, 4),))

    assert opener.of("POST", "/descendant"), "this shape must take the one-call route"
    assert entry.mutating_write_calls == len(opener.writes) == 1
    assert entry.atomic is True


def test_the_create_grow_fill_route_discloses_the_measured_cost_and_not_atomic():
    """An intro line AND a table — the natural composition, and the one that loses atomicity
    silently. The count is whatever the engine issued; the flag follows from it."""
    entry, opener = _applied((NewParagraph("Findings"), _table(12, 4)))

    assert opener.of("POST", "/descendant") == [], "this shape must NOT take the one-call route"
    assert opener.of("PATCH", "/blocks/"), "this shape must have GROWN the grid"
    assert entry.mutating_write_calls == len(opener.writes) > 1
    assert entry.atomic is False
    assert entry.to_dict()[INSERT_ATOMIC_KEY] is False


def test_every_inserted_entry_in_a_mixed_batch_carries_the_disclosure():
    """Absence-means-atomic is an inference. A mixed batch legitimately carries a different
    count per entry, and every entry states its own."""
    opener = _seed_opener()
    plan = dry_run(
        [_insert("a1", (NewParagraph("one line"),)),
         _insert("b1", (_table(4, 3),)),
         _insert("s2", (NewParagraph("intro"), _table(12, 3)))],
        _seed_tree(),
    )
    log = apply(plan, _client(opener), "doc562")

    inserted = [e for e in log.entries if e.outcome == "inserted"]
    assert len(inserted) == 3
    for entry in inserted:
        assert entry.mutating_write_calls is not None
        assert INSERT_WRITE_CALLS_KEY in entry.to_dict()
        assert INSERT_ATOMIC_KEY in entry.to_dict()
    assert sum(e.mutating_write_calls for e in inserted) == len(opener.writes)
    assert [e.atomic for e in inserted] == [True, True, False]


# --------------------------------------------------------------------------- #
# AC1(b) — COUNTED from the calls actually issued, never predicted              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("content", [
    pytest.param((NewParagraph("solo"),), id="one-paragraph"),
    pytest.param((NewParagraph("a"), NewParagraph("b"), NewParagraph("c")), id="flat-three"),
    pytest.param((_table(3, 3),), id="lone-small-table"),
    pytest.param((NewParagraph("intro"), _table(3, 3)), id="mixed-small-table"),
    pytest.param((NewParagraph("intro"), _table(14, 5)), id="mixed-grown-table"),
    pytest.param((NewParagraph("intro"), _table(4, 4), _table(11, 4)), id="mixed-two-tables"),
])
def test_the_disclosed_count_equals_the_calls_the_double_actually_received(content):
    entry, opener = _applied(content)

    assert entry.mutating_write_calls == len(opener.writes)
    assert entry.mutating_write_calls == len(
        [c for c in opener.calls if c["method"] != "GET"])


def test_a_smaller_batch_ceiling_moves_the_count_because_the_count_is_measured(monkeypatch):
    """The engine already publishes an arithmetic for this cost. A count re-derived from that
    formula would agree with the calls today and drift the moment a ceiling moved — so move
    one, and require the disclosure to follow the wire rather than the formula."""
    apply_module = importlib.import_module("larkdocio.write.apply")

    wide, _ = _applied((NewParagraph("intro"), _table(14, 5)))
    monkeypatch.setattr(apply_module, "MAX_BATCH_UPDATES_PER_CALL", 3)
    narrow, opener = _applied((NewParagraph("intro"), _table(14, 5)))

    assert narrow.mutating_write_calls == len(opener.writes)
    assert narrow.mutating_write_calls > wide.mutating_write_calls


# --------------------------------------------------------------------------- #
# AC1(c) — "not atomic" derives from the measured N, never from the branch      #
# --------------------------------------------------------------------------- #

def test_flat_content_off_the_one_call_route_is_still_disclosed_atomic():
    """Three paragraphs do not take the one-call table route, and they are still exactly one
    call. A flag keyed on the branch would ship a FALSE disclosure here."""
    entry, opener = _applied((NewParagraph("a"), NewParagraph("b"), NewParagraph("c")))

    assert opener.of("POST", "/descendant") == []
    assert len(opener.writes) == 1
    assert entry.mutating_write_calls == 1
    assert entry.atomic is True


def test_the_flag_is_a_function_of_the_count_and_of_nothing_else():
    for count, atomic in ((1, True), (2, False), (27, False)):
        entry = ApplyLogEntry.inserted(anchor=AnchorById(block_id="x"),
                                       created_block_ids=("b",),
                                       mutating_write_calls=count)
        assert entry.atomic is atomic
        assert entry.to_dict()[INSERT_ATOMIC_KEY] is atomic


# --------------------------------------------------------------------------- #
# AC2 — the stability contract, the unit, and the round trip                    #
# --------------------------------------------------------------------------- #

def test_the_contract_pins_the_unit_as_mutating_write_calls():
    lowered = INSERT_COST_CONTRACT.lower()
    assert "mutating" in lowered
    assert INSERT_WRITE_CALLS_KEY in INSERT_COST_CONTRACT
    assert INSERT_ATOMIC_KEY in INSERT_COST_CONTRACT
    # what may be relied on, and what may not — both halves stated
    assert "rely on" in lowered and "do not rely on" in lowered


def test_the_contract_states_no_number_of_its_own():
    """Every number in the disclosure is computed at runtime; a number in the prose would be a
    claim with no measurement behind it."""
    assert not re.search(r"\d", INSERT_COST_CONTRACT)


def test_the_payload_is_a_measurement_and_not_a_route_name():
    entry, _ = _applied((NewParagraph("intro"), _table(12, 4)))
    wire = json.dumps(entry.to_dict()).lower()

    assert isinstance(entry.to_dict()[INSERT_WRITE_CALLS_KEY], int)
    for token in ("route", "one-call", "descendant", "create-seed-grow-fill",
                  "stale", "refus"):
        assert token not in wire, token


def test_the_new_key_round_trips_through_from_dict():
    entry, _ = _applied((NewParagraph("intro"), _table(12, 4)))
    restored = ApplyLogEntry.from_dict(entry.to_dict())

    assert restored.mutating_write_calls == entry.mutating_write_calls
    assert restored.atomic is entry.atomic
    assert restored.to_dict() == entry.to_dict()


def test_a_whole_log_round_trips_through_json():
    entry, _ = _applied((NewParagraph("intro"), _table(12, 4)))
    log = ApplyLog(entries=(entry,))

    assert ApplyLog.from_json(log.to_json()).to_dict() == log.to_dict()


def test_the_key_is_OMITTED_when_it_was_never_measured():
    """The omit-when-unset pattern, so every log written before this shipped — and every
    hand-built one — serialises byte-identically."""
    bare = ApplyLogEntry.inserted(anchor=AnchorById(block_id="x"), created_block_ids=("b",))

    assert bare.mutating_write_calls is None and bare.atomic is None
    assert bare.to_dict() == {"outcome": "inserted",
                              "anchor": AnchorById(block_id="x").to_dict(),
                              "created_block_ids": ["b"]}
    assert ApplyLogEntry.from_dict(bare.to_dict()).to_dict() == bare.to_dict()


# --------------------------------------------------------------------------- #
# AC3 — one constant, projected, guarded in BOTH directions                     #
# --------------------------------------------------------------------------- #

def _flat(text):
    """``text`` with every space, newline and string-literal quote removed.

    A projection guard has to be insensitive to two things that are not drift: Markdown wraps
    the sentence at the column the document uses, and Python authors it as adjacent string
    literals. Flattening both sides compares what is *said*, not how it was typeset.
    """
    return re.sub(r'[\s"]+', "", text)


def _guide_text():
    return GUIDE.read_text(encoding="utf-8")


def _package_python():
    return sorted(PACKAGE.rglob("*.py"))


def test_the_guide_projects_the_contract_verbatim():
    assert _flat(INSERT_COST_CONTRACT) in _flat(_guide_text())


def test_every_write_call_spelling_the_guide_uses_is_the_constant():
    """The backward direction: a documented spelling with no constant behind it reddens."""
    spelled = set(re.findall(r"`([A-Za-z_]*write_calls?[A-Za-z_]*)`", _guide_text()))
    assert spelled == {INSERT_WRITE_CALLS_KEY}, spelled


def test_the_key_is_authored_exactly_once_in_the_package_python():
    """One authoring — which is also what keeps the disclosure off every other surface: no
    CLI page, plan summary or preview can spell it without appearing here."""
    hits = [(path.name, n)
            for path in _package_python()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if f'"{INSERT_WRITE_CALLS_KEY}"' in line]
    assert [name for name, _ in hits] == ["applylog.py"], hits


def test_the_contract_is_authored_exactly_once_in_the_package_python():
    core = _flat(INSERT_COST_CONTRACT.split(".")[0])
    files = [path.name for path in _package_python()
             if core in _flat(path.read_text(encoding="utf-8"))]
    assert files == ["applylog.py"], files


# --------------------------------------------------------------------------- #
# AC4 — on the entry it describes and NOWHERE else                              #
# --------------------------------------------------------------------------- #

def test_no_other_outcome_carries_the_disclosure():
    opener = _seed_opener()
    plan = dry_run(
        [_insert("a1", (NewParagraph("added"),)),
         EditRequest(anchor=AnchorById(block_id="b1"), replacement="edited"),
         DeleteRequest(target=AnchorById(block_id="s2"))],
        _seed_tree(),
    )
    log = apply(plan, _client(opener), "doc562")

    outcomes = [e.outcome for e in log.entries]
    assert outcomes == ["inserted", "applied", "deleted"], outcomes
    for entry in log.entries[1:]:
        payload = entry.to_dict()
        assert INSERT_WRITE_CALLS_KEY not in payload, entry.outcome
        assert INSERT_ATOMIC_KEY not in payload, entry.outcome
        assert entry.mutating_write_calls is None


def test_a_refusal_carries_no_disclosure():
    opener = _seed_opener()
    plan = dry_run([_insert("no-such-block", (NewParagraph("x"),))], _seed_tree())
    log = apply(plan, _client(opener), "doc562", allow_partial=True)

    refusals = [e for e in log.entries if e.outcome == "refused"]
    assert refusals, "the shape must refuse for this test to say anything"
    for entry in refusals:
        assert INSERT_WRITE_CALLS_KEY not in json.dumps(entry.to_dict())
        assert entry.mutating_write_calls is None


def test_the_plan_and_the_preview_state_no_cost():
    """The disclosure is a MEASUREMENT of what happened, so it cannot exist before the
    write — nothing in the plan may claim it."""
    plan = dry_run([_insert("a1", (NewParagraph("intro"), _table(12, 4)))], _seed_tree())

    rendered = plan.to_json() + repr(plan)
    assert INSERT_WRITE_CALLS_KEY not in rendered
    assert f'"{INSERT_ATOMIC_KEY}"' not in rendered


# --------------------------------------------------------------------------- #
# AC5 — patch_block's cost, stated at BOTH doors                                #
# --------------------------------------------------------------------------- #

def test_the_docstring_states_the_cost():
    doc = WriteClient._patch_block.__doc__
    assert PATCH_BLOCK_COST in doc
    assert "<<" not in doc, "the projection placeholder survived into the shipped docstring"


def test_the_cost_names_all_three_things_it_sits_outside_of():
    lowered = PATCH_BLOCK_COST.lower()
    for phrase in ("plan gate", "stale_document", "refusal set", "read-back"):
        assert phrase in lowered, phrase


def test_the_cost_names_what_is_actually_unique_and_never_claims_only():
    lowered = PATCH_BLOCK_COST.lower()
    assert "in-place" in lowered and "identity-preserving" in lowered
    assert "only" not in lowered, (
        "delete-and-recreate reaches the same content through the gate — the load-bearing "
        "word is not 'only'")


def test_the_guide_router_states_the_cost_beside_the_table():
    assert _flat(PATCH_BLOCK_COST) in _flat(_guide_text())


def test_the_cost_sentence_is_authored_exactly_once_in_the_package_python():
    core = _flat(PATCH_BLOCK_COST.split(".")[0])
    files = [path.name for path in _package_python()
             if core in _flat(path.read_text(encoding="utf-8"))]
    assert files == ["client.py"], files
