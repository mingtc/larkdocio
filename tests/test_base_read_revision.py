"""LD-333 — the per-table REVISION the Base read already fetched and used to drop.

Every test here is **offline**, against committed probe captures of real `GET …/tables`
replies, deserialized through the pinned SDK (PROJECT.md § Quality bar) — so the field is
compared against the bytes Lark actually returned, not against a hand-written idea of them.

The four disciplines this file holds:

1. **The revision reaches the structured result, at ZERO extra calls.** The value rides the
   ``list_tables`` reply the read already receives; a call-count spy is the fence, not prose.
2. **``None`` means "not known" and ``0`` is NEVER synthesized.** ``table.revision`` reads a
   real ``0`` on a fresh Base (``base/plan.py:24-25``), so an absent revision must stay
   distinguishable from a genuine zero. Same discipline the write side already applies at
   ``base/apply.py:114``.
3. **Zero drift.** The Markdown form does not move by one byte: the revision rides the
   structured result only, and that is a deliberate, documented choice.
4. **The meaning is written down** — the four measured facts and the honest limitation, in
   ``/BASE.md`` and in the shipped docstring, reusing the library's own vocabulary.
"""
import inspect
import json
import re

import pytest
from lark_oapi.api.bitable.v1 import ListAppTableResponse
from lark_oapi.core.json import JSON

import base_captures
from base_md import BASE_MD
from guard_kit import REPO_ROOT
from larkdocio.base import read as base_read
from larkdocio.base import table as base_table

_REPO = REPO_ROOT
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"
_GOLDEN = _REPO / "tests" / "fixtures" / "base_scratch.expected.md"


def golden():
    """The committed golden of the whole captured Base, trailing newline normalized the way
    ``tests/test_base_table.py`` already does it."""
    return _GOLDEN.read_text(encoding="utf-8").rstrip("\n")


def capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def tables_from(name):
    """A committed ``GET …/tables`` capture → the SDK's own ``List[AppTable]``."""
    payload = capture(name)["response"]
    return JSON.unmarshal(json.dumps(payload), ListAppTableResponse).data.items


class SpyClient:
    """The captured Scratch Base behind the read client's five verbs, counting calls.

    Byte-identical in shape to ``tests/test_base_raw_values.py::SpyClient`` — the way this
    codebase already proves "no new call".
    """

    def __init__(self, tables=None):
        self.app, captured, self.per_table = base_captures.scratch_base()
        self.tables = captured if tables is None else tables
        self.calls = []

    @property
    def api_calls(self):
        return len(self.calls)

    def get_app(self, app_token):
        self.calls.append(("get_app", app_token))
        return self.app

    def list_tables(self, app_token):
        self.calls.append(("list_tables", app_token))
        return self.tables

    def list_fields(self, app_token, table_id):
        self.calls.append(("list_fields", table_id))
        return self.per_table[table_id][0]

    def search_records(self, app_token, table_id):
        self.calls.append(("search_records", table_id))
        return self.per_table[table_id][1]


# --------------------------------------------------------------------------- #
# AC1 — the revision reaches the result, at zero extra API calls.               #
# --------------------------------------------------------------------------- #

def test_ac1_the_captured_tables_reply_CARRIES_a_revision_per_table():
    """The premise, pinned off the wire before anything is asserted about the reader: the
    reply the read already receives has the number on every element."""
    tables = tables_from("p1-q0-02-tables.json")
    assert [(t.table_id, t.revision) for t in tables] == [
        ("tblYtWUpf5q944Ao", 25), ("tblvHhs6KA9QYNCo", 25)]


def test_ac1_read_base_EXPOSES_the_per_table_revision():
    read = base_read.read_base("appSCRATCH", client=SpyClient())
    assert [table.revision for table in read.tables] == [25, 25]


def test_ac1_the_revision_is_the_one_the_TABLES_REPLY_CARRIED_table_by_table():
    """Not "some revision" — each table's own, matched by ``table_id``, in reply order."""
    spy = SpyClient()
    read = base_read.read_base("appSCRATCH", client=spy)
    wire = {t.table_id: t.revision for t in spy.tables}
    assert [(t.table_id, t.revision) for t in read.tables] == [
        (table_id, wire[table_id]) for table_id in wire]


def test_ac1_ZERO_extra_api_calls_still_FIVE_READS_PER_BASE_AND_NOT_ONE_MORE():
    """The fence. App meta once + the table list once + fields and records per table — the
    count ``base/read.py``'s own docstring claims, unchanged by exposing the field."""
    spy = SpyClient()
    read = base_read.read_base("appSCRATCH", client=spy)
    assert spy.api_calls == 1 + 1 + 2 * len(read.tables) == 6
    assert [name for name, _arg in spy.calls] == [
        "get_app", "list_tables",
        "list_fields", "search_records", "list_fields", "search_records"]


def test_ac1_no_extra_call_hides_behind_an_ABSENT_revision_either():
    """AC2's ``None`` must not become a fetch: a table whose reply carried no revision is
    read at exactly the same call count."""
    payload = capture("p1-q0-02-tables.json")["response"]
    for item in payload["data"]["items"]:
        item.pop("revision", None)
    stripped = JSON.unmarshal(json.dumps(payload), ListAppTableResponse).data.items
    spy = SpyClient(tables=stripped)
    read = base_read.read_base("appSCRATCH", client=spy)
    assert [table.revision for table in read.tables] == [None, None]
    assert spy.api_calls == 6


# --------------------------------------------------------------------------- #
# AC2 — None means "not known"; 0 is a REAL value and is never synthesized.      #
# --------------------------------------------------------------------------- #

def test_ac2_a_GENUINE_zero_reads_as_zero_off_a_real_capture():
    """``00-tables.json`` is a real ``GET …/tables`` reply whose single table sat at
    ``revision: 0``. Zero is an observation, not a stand-in."""
    tables = tables_from("00-tables.json")
    assert [t.revision for t in tables] == [0]
    read = base_table.assemble_table(
        table_id=tables[0].table_id, name=tables[0].name, fields=(), records=(),
        revision=tables[0].revision)
    assert read.revision == 0
    assert read.revision is not None


def test_ac2_an_ABSENT_revision_reads_None_and_the_TWO_ARE_DISTINGUISHABLE():
    absent = base_table.assemble_table(table_id="t", name="T", fields=(), records=())
    zero = base_table.assemble_table(
        table_id="t", name="T", fields=(), records=(), revision=0)
    assert absent.revision is None
    assert zero.revision == 0
    assert absent.revision is not zero.revision, (
        "a table with no revision must not read as a table genuinely at revision 0 — that is "
        "the whole reason the consumer's ledger said 'unknown' rather than guessing")


def test_ac2_the_default_is_None_on_every_seam_that_takes_it():
    for function in (base_table.assemble_table,):
        parameter = inspect.signature(function).parameters["revision"]
        assert parameter.default is None
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    field = base_table.BaseTableRead.__dataclass_fields__["revision"]
    assert field.default is None


def test_ac2_the_read_never_COERCES_the_revision():
    """No ``or 0``, no ``int(...)``, no ``if revision is None: revision = 0`` anywhere on the
    read path. The write side reads it defensively and so does this."""
    banned = re.compile(r"revision\s*(or|\|\|)\s*0|revision\s*=\s*0\b|int\(\s*revision")
    for name in ("read.py", "table.py"):
        source = (_REPO / "src" / "larkdocio" / "base" / name).read_text(encoding="utf-8")
        assert not banned.search(source), f"{name} coerces the revision"


def test_ac2_the_read_takes_the_field_DEFENSIVELY_like_the_write_side_does():
    """``base/apply.py:114`` reads ``getattr(table, "revision", None)``; the read inherits the
    same discipline, so an SDK model that drops the attribute degrades to ``None`` instead of
    raising mid-read."""
    source = (_REPO / "src" / "larkdocio" / "base" / "read.py").read_text(encoding="utf-8")
    assert 'getattr(table, "revision", None)' in source


# --------------------------------------------------------------------------- #
# AC1/AC4 — ZERO DRIFT: the Markdown form does not move by one byte.             #
# --------------------------------------------------------------------------- #

def test_ac4_the_MARKDOWN_is_byte_identical_to_the_committed_golden():
    read = base_read.read_base("appSCRATCH", client=SpyClient())
    assert base_table.render_base(read) == golden()


def test_ac4_read_base_markdown_DELIBERATELY_does_not_surface_the_revision():
    """The projection stays lossy on purpose — the same ruling the ``retain_raw`` half took.
    ``read_base`` is where the version lives, and the docstring says so where a caller of the
    Markdown form will read it."""
    baseline = golden()
    assert base_read.read_base_markdown("appSCRATCH", client=SpyClient()) == baseline
    doc = base_read.read_base_markdown.__doc__
    assert "revision" in doc and "read_base" in doc


# --------------------------------------------------------------------------- #
# AC3 — the MEANING, in the library's own measured vocabulary.                   #
# --------------------------------------------------------------------------- #

#: The four established facts + the limitation, each as a needle a reader would look for.
_FACTS = {
    "per-table isolated": ("per-table", "isolated"),
    "the app revision does not move": ("app revision",),
    "an op counter, not a row counter": ("op counter", "not a row counter"),
    "0 is a real value": ("`0` is a real",),
    "None means not known": ("`None`", "not known"),
    "there is no If-Match": ("If-Match", "read-compare-write"),
    "the limitation": ("no tables",),
}


@pytest.mark.parametrize("fact,needles", sorted(_FACTS.items()))
def test_ac3_BASE_md_states_the_fact(fact, needles):
    text = BASE_MD.read_text(encoding="utf-8")
    start = text.index("### The per-table REVISION")
    end = text.index("\n## ", start)
    passage = text[start:end]
    missing = [needle for needle in needles if needle not in passage]
    assert not missing, f"BASE.md's revision passage does not state {fact!r}: {missing}"


def test_ac3_the_SHIPPED_DOCSTRING_carries_the_meaning_too():
    """A consumer decides at the call site, not in the repo's root matrix."""
    doc = base_table.BaseTableRead.__doc__ or ""
    for needle in ("per-table", "op counter", "`None`", "If-Match"):
        assert needle in doc, f"BaseTableRead's docstring drops {needle!r}"


def test_ac3_NO_base_level_or_app_level_revision_IS_INVENTED():
    """Explicitly out of scope: the app revision was probed and does not move, so a
    synthesized Base-wide number would be a derived value presented as an API fact."""
    assert not hasattr(base_table.BaseRead, "revision")
    assert "revision" not in base_table.BaseRead.__dataclass_fields__
    source = (_REPO / "src" / "larkdocio" / "base" / "table.py").read_text(encoding="utf-8")
    assert not re.search(r"max\(\s*[^)]*revision", source)


# --------------------------------------------------------------------------- #
# AC6 — no new endpoint, no scope widening.                                     #
# --------------------------------------------------------------------------- #

def test_ac6_the_read_surfaces_OP_SET_is_exactly_what_it_was():
    from larkdocio.base import ops as base_ops

    assert {descriptor.name for descriptor in base_ops.OPS} == {
        "get_app", "list_tables", "list_views", "get_view", "list_fields", "search_records",
        "batch_get_records"}
    assert base_ops.read_only()
