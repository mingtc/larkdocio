"""LD-131 — refusal TRUTH: the two lying refusals the dogfood session caught (F5 + F4).

Two shipped refusals named the wrong failure and sent a consumer to the wrong repair —
and per the project's own doctrine a misleading error is worse than a crash:

* **(a) docx** — an ``InsertRequest`` with ``position=BEFORE``/``AFTER`` whose anchor
  resolves to a node with **no parent** (the document root / page node) returned
  ``{"reason": "not-found"}`` **with no detail field at all**, while the *identical*
  anchor with ``APPEND_INTO`` resolved to a real ``block_id``. The anchor WAS found; the
  truth is that the resolved block is the root, which has no sibling position. The
  taxonomy already had ``cannot-hold-children`` for the mirror case, so the gap was only
  the **sibling** case → :data:`RefusalReason.CANNOT_HOLD_SIBLINGS`, plus a
  **structurally mandatory** ``detail`` on every docx refusal.
* **(b) sheets** — an A1 range naming a ``sheet_id`` that **never existed** (the guide's
  own ``"Sheet1!A1:A1"``, where ``Sheet1`` is a tab *title*) refused ``tab-vanished`` — a
  *staleness* story that sends the consumer to re-read and re-plan, when the identifier
  *kind* was wrong → a plan-time ``unknown-tab`` carrying a **did-you-mean** listing of
  the spreadsheet's real ``(sheet_id, title)`` pairs, with ``tab-vanished`` **reserved**
  for a tab that was readable at plan time and is gone at apply re-validation.

The two report repros are encoded verbatim (``test_f5_repro_a_*`` / ``test_f4_repro_b_*``),
and the amplifier rigor the issue asked for is here too: the full position matrix on a root
anchor, a **structural** detail-less-construction attempt for every refusal factory (must
fail), an **AST sweep** of every ``Refusal.<factory>(...)`` construction site in the docx
write package (none may omit its detail), a per-path "the detail names the identifier it is
about" matrix, refusal JSON round-trips, and the did-you-mean listing at 1 tab / 2 tabs /
a tab whose title contains a ``!``.

Evidence base: ``dev/dogfood/2026-07-27-session/report.md`` § F5 + § F4.
"""
import ast
import inspect
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import LarkAPIError
from larkdocio.model import PageNode, Text
from larkdocio.sheets.plan import Refusal as SheetsRefusal
from larkdocio.sheets.requests import DeleteRows, MergeCells, ValueWriteRequest
from larkdocio.sheets.write_apply import apply as sheets_apply, dry_run as sheets_dry_run
sheets_apply = reading_the_log(sheets_apply)
from larkdocio.write.apply import apply as docx_apply
docx_apply = reading_the_log(docx_apply)
from larkdocio.write.model import (
    Anchor,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    Refusal,
    RefusalReason,
    SubSpanEditRequest,
)
from larkdocio.write.preview import dry_run
from larkdocio.write.resolve import ResolvedTarget, resolve

from write_harness import (
    StubOpener,
    _block_payload,
    _client,
    _delete,
    _heading,
    _para,
    _req,
    _run,
    _table,
    _treq,
)

TOKEN = "shtxxxTOKEN"


# --------------------------------------------------------------------------- #
# The live-doc shape the dogfood session wrote against: a page titled          #
# "Scratch Doc" holding the one paragraph "Hello World". The page node IS the  #
# tree root, so an anchor on the title resolves to a node with no parent.      #
# --------------------------------------------------------------------------- #

def _scratch_doc():
    return PageNode(
        title=[Text("Scratch Doc")],
        children=[_para("p1", "Hello World")],
        block_id="DocCommeRoot",
    )


def _root_insert(position):
    """The report's Repro A request, verbatim: one anchor, one position."""
    return InsertRequest(
        reference=Anchor(quote="Scratch Doc"),
        position=position,
        content=(NewParagraph("x"),),
    )


# =========================================================================== #
# AC1 + AC4 — F5 Repro A: the three positions on ONE root-resolving anchor      #
# =========================================================================== #

def test_f5_repro_a_root_anchor_before_after_refuse_cannot_hold_siblings():
    """Repro A verbatim: BEFORE / AFTER on an anchor that resolves to the doc root.

    Before LD-131 both returned a detail-less ``{"reason": "not-found"}`` — a lie: the
    anchor WAS found (see the APPEND_INTO leg below).
    """
    root = _scratch_doc()

    for position in (InsertPosition.BEFORE, InsertPosition.AFTER):
        result = resolve(_root_insert(position), root)
        assert isinstance(result, Refusal), position
        assert result.reason is RefusalReason.CANNOT_HOLD_SIBLINGS, position
        assert result.reason.value == "cannot-hold-siblings"
        # the detail must NAME the resolved block and WHY it cannot hold siblings
        assert "DocCommeRoot" in result.detail, result.detail
        assert "PageNode" in result.detail or "page" in result.detail.lower()
        assert "no parent" in result.detail.lower() or "root" in result.detail.lower()
        # and it must point at the repair that actually works
        assert "append-into" in result.detail.lower()


def test_f5_repro_a_the_identical_anchor_with_append_into_still_resolves():
    """The proof the anchor was FOUND all along — the same anchor, APPEND_INTO, resolves."""
    root = _scratch_doc()
    result = resolve(_root_insert(InsertPosition.APPEND_INTO), root)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "DocCommeRoot"
    assert result.insertion.parent_block_id == "DocCommeRoot"
    assert result.insertion.position == "append-into"
    assert result.insertion.index == 1  # appended after the one existing paragraph


def test_f5_repro_a_full_position_matrix_through_dry_run():
    """The amplifier's full matrix, through the public previewer (what a consumer sees)."""
    root = _scratch_doc()
    plan = dry_run(
        [
            _root_insert(InsertPosition.BEFORE),
            _root_insert(InsertPosition.AFTER),
            _root_insert(InsertPosition.APPEND_INTO),
        ],
        root,
    )
    before, after, into = plan.entries
    assert [e.outcome for e in (before, after)] == ["refused", "refused"]
    assert into.outcome == "resolved"
    for entry in (before, after):
        d = entry.to_dict()
        assert d["refusal"]["reason"] == "cannot-hold-siblings"
        assert d["refusal"]["detail"]                      # never empty (AC2)
        assert "DocCommeRoot" in d["refusal"]["detail"]


def test_root_anchor_refusal_no_longer_claims_not_found():
    """The regression bar: the reason must NOT be the old lie."""
    root = _scratch_doc()
    result = resolve(_root_insert(InsertPosition.BEFORE), root)
    assert result.reason is not RefusalReason.NOT_FOUND
    assert result.to_dict()["reason"] != "not-found"


def test_cannot_hold_siblings_is_distinct_from_cannot_hold_children():
    """The sibling reason mirrors — never merges with — the children reason."""
    assert RefusalReason("cannot-hold-siblings") is RefusalReason.CANNOT_HOLD_SIBLINGS
    assert RefusalReason.CANNOT_HOLD_SIBLINGS is not RefusalReason.CANNOT_HOLD_CHILDREN
    assert RefusalReason.CANNOT_HOLD_SIBLINGS.value != RefusalReason.NOT_FOUND.value


def test_append_into_a_leaf_still_refuses_cannot_hold_children():
    """The mirror case is untouched — and now carries an actionable detail too."""
    root = PageNode(title=[Text("Doc")], children=[_para("p1", "leaf line")], block_id="root")
    result = resolve(
        InsertRequest(
            reference=Anchor(quote="leaf line"),
            position=InsertPosition.APPEND_INTO,
            content=(NewParagraph("x"),),
        ),
        root,
    )
    assert result.reason is RefusalReason.CANNOT_HOLD_CHILDREN
    assert "p1" in result.detail
    assert result.detail.strip()


def test_a_non_root_anchor_before_after_still_resolve_normally():
    """The fix must not turn ordinary sibling inserts into refusals."""
    root = _scratch_doc()
    for position, expected_index in ((InsertPosition.BEFORE, 0), (InsertPosition.AFTER, 1)):
        result = resolve(
            InsertRequest(
                reference=Anchor(quote="Hello World"),
                position=position,
                content=(NewParagraph("x"),),
            ),
            root,
        )
        assert isinstance(result, ResolvedTarget), position
        assert result.insertion.parent_block_id == "DocCommeRoot"
        assert result.insertion.index == expected_index


# =========================================================================== #
# AC2 — `detail` is STRUCTURALLY mandatory on every docx refusal               #
# =========================================================================== #

def _refusal_factories():
    """Every public :class:`Refusal` construction factory (classmethods, minus (de)ser)."""
    out = []
    for name, member in vars(Refusal).items():
        if name.startswith("_") or name in {"from_dict", "to_dict"}:
            continue
        if isinstance(member, classmethod):
            out.append((name, getattr(Refusal, name)))
    return sorted(out)


def _call_args_for(factory, detail):
    """Bind a factory's non-detail params with type-appropriate stand-ins."""
    args, kwargs = [], {}
    for pname, param in inspect.signature(factory).parameters.items():
        if pname == "detail":
            kwargs["detail"] = detail
        elif "candidate_ids" in pname:
            args.append(("cid-a", "cid-b"))
        elif param.default is inspect.Parameter.empty:  # pragma: no cover — guard
            raise AssertionError(
                f"Refusal.{factory.__name__} has an unknown required param {pname!r}; "
                "teach this test how to bind it"
            )
    return args, kwargs


def test_the_refusal_factory_set_is_non_empty_and_every_one_takes_a_detail():
    factories = _refusal_factories()
    assert len(factories) >= 10, [n for n, _ in factories]
    for name, factory in factories:
        params = inspect.signature(factory).parameters
        assert "detail" in params, f"Refusal.{name} takes no detail"
        assert params["detail"].default is inspect.Parameter.empty, (
            f"Refusal.{name}'s detail has a default — it must be REQUIRED"
        )


def test_no_refusal_factory_can_be_called_without_a_detail():
    """The structural half of AC2: omitting the detail is a TypeError, per factory."""
    for name, factory in _refusal_factories():
        args, _ = _call_args_for(factory, "unused")
        with pytest.raises(TypeError):
            factory(*args)


@pytest.mark.parametrize("empty", ["", "   ", "\n\t"])
def test_no_refusal_factory_accepts_an_EMPTY_detail(empty):
    for name, factory in _refusal_factories():
        args, kwargs = _call_args_for(factory, empty)
        with pytest.raises(ValueError):
            factory(*args, **kwargs)


def test_every_refusal_factory_carries_its_detail_through_verbatim():
    sentinel = "LD131-SENTINEL-DETAIL"
    for name, factory in _refusal_factories():
        args, kwargs = _call_args_for(factory, sentinel)
        refusal = factory(*args, **kwargs)
        assert isinstance(refusal.reason, RefusalReason), name
        assert sentinel in refusal.detail, name
        assert refusal.to_dict()["detail"] == refusal.detail


def test_the_refusal_constructor_itself_requires_a_non_empty_str_detail():
    with pytest.raises(TypeError):
        Refusal(RefusalReason.NOT_FOUND)                     # no detail at all
    with pytest.raises(ValueError):
        Refusal(RefusalReason.NOT_FOUND, "")                 # empty
    with pytest.raises(ValueError):
        Refusal(RefusalReason.NOT_FOUND, "   ")              # whitespace-only
    with pytest.raises(TypeError):
        Refusal(RefusalReason.NOT_FOUND, None)               # wrong type
    ok = Refusal(RefusalReason.NOT_FOUND, "why it failed")
    assert ok.detail == "why it failed"


def test_refusal_json_round_trip_preserves_the_detail():
    for refusal in (
        Refusal.not_found(detail="no block matched quote 'zzz'"),
        Refusal.ambiguous(("a", "b"), detail="quote 'x' matched 2 blocks"),
        Refusal.cannot_hold_siblings(detail="block root is the page node"),
    ):
        wire = json.loads(json.dumps(refusal.to_dict()))
        assert wire["detail"] == refusal.detail
        assert Refusal.from_dict(wire) == refusal


def test_refusal_from_dict_refuses_a_detail_less_wire_record():
    """A legacy (pre-LD-131) detail-less record cannot be revived into a lying refusal."""
    with pytest.raises(ValueError):
        Refusal.from_dict({"reason": "not-found"})
    with pytest.raises(ValueError):
        Refusal.from_dict({"reason": "not-found", "detail": ""})


# --------------------------------------------------------------------------- #
# AC2 (the site sweep) — an AST guard: no construction site omits its detail    #
# --------------------------------------------------------------------------- #

_WRITE_PKG = Path(__file__).resolve().parent.parent / "src" / "larkdocio" / "write"


def _refusal_call_sites():
    """Every ``Refusal(...)`` / ``Refusal.<factory>(...)`` call in the docx write package."""
    sites = []
    for path in sorted(_WRITE_PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Refusal":
                sites.append((path, node, None))
            elif (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "Refusal"
                and func.attr not in {"from_dict", "to_dict"}
            ):
                sites.append((path, node, func.attr))
    return sites


def test_the_ast_sweep_finds_the_real_construction_sites():
    sites = _refusal_call_sites()
    assert len(sites) >= 15, len(sites)
    attrs = {attr for (_p, _n, attr) in sites if attr}
    assert {"not_found", "ambiguous", "cannot_hold_children", "cannot_hold_siblings"} <= attrs


def test_no_refusal_construction_site_in_the_write_package_omits_its_detail():
    """Every site must satisfy its factory's REQUIRED arity — i.e. pass a detail."""
    offenders = []
    for (path, node, attr) in _refusal_call_sites():
        supplied = {kw.arg for kw in node.keywords if kw.arg} | set(range(len(node.args)))
        if attr is None:
            required = ["reason", "detail"]
            ok = len(node.args) + len(node.keywords) >= 2
        else:
            params = inspect.signature(getattr(Refusal, attr)).parameters
            required = [
                p for p, prm in params.items() if prm.default is inspect.Parameter.empty
            ]
            positional = len(node.args)
            named = {kw.arg for kw in node.keywords if kw.arg}
            ok = all(
                (i < positional or p in named) for i, p in enumerate(required)
            )
        if not ok:
            offenders.append(f"{path.name}:{node.lineno} Refusal.{attr or '()'} "
                             f"needs {required}, got args={len(node.args)} kw={sorted(supplied)}")
    assert not offenders, "detail-less refusal construction site(s):\n" + "\n".join(offenders)


def test_no_refusal_construction_site_passes_an_empty_literal_detail():
    offenders = []
    for (path, node, attr) in _refusal_call_sites():
        literals = [
            a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ] + [
            kw.value.value
            for kw in node.keywords
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)
        ]
        if any(not lit.strip() for lit in literals):
            offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, offenders


# --------------------------------------------------------------------------- #
# AC2 (behavior) — every docx refusal PATH carries an actionable detail         #
# --------------------------------------------------------------------------- #

def _dup_tree():
    return PageNode(
        title=[Text("Doc")],
        children=[_para("d1", "the same line"), _para("d2", "the same line")],
        block_id="root",
    )


def _metrics_table():
    return PageNode(
        title=[Text("Doc")],
        children=[
            _table("t1", [
                [("c00", "Metric"), ("c01", "Q3"), ("c02", "Q4")],
                [("c10", "On-time delivery"), ("c11", "97.2%"), ("c12", "98.1%")],
            ]),
        ],
        block_id="root",
    )


def _dup_header_table():
    return PageNode(
        title=[Text("Doc")],
        children=[
            _table("t2", [
                [("h0", "Metric"), ("h1", "Q3"), ("h2", "Q3")],
                [("r0", "On-time delivery"), ("r1", "97.2%"), ("r2", "98.1%")],
            ]),
        ],
        block_id="root",
    )


#: (label, tree, request, expected reason, substrings the detail MUST contain)
_RESOLVE_REFUSAL_MATRIX = [
    (
        "narrative-not-found",
        lambda: _scratch_doc(),
        lambda: _req("nothing matches this"),
        RefusalReason.NOT_FOUND,
        ["nothing matches this"],
    ),
    (
        "narrative-empty-quote",
        lambda: _scratch_doc(),
        lambda: _req(""),
        RefusalReason.NOT_FOUND,
        ["quote"],
    ),
    (
        "narrative-breadcrumb-excluded",
        lambda: PageNode(
            title=[Text("Doc")],
            children=[_heading("h1", "Results"), _para("p9", "the same line"),
                      _para("p8", "the same line")],
            block_id="root",
        ),
        lambda: _req("the same line", breadcrumb=("Nowhere",)),
        RefusalReason.NOT_FOUND,
        ["the same line", "Nowhere"],
    ),
    (
        "narrative-ambiguous",
        _dup_tree,
        lambda: _req("the same line"),
        RefusalReason.AMBIGUOUS,
        ["the same line", "d1", "d2"],
    ),
    (
        "subspan-span-absent",
        lambda: _scratch_doc(),
        lambda: SubSpanEditRequest(
            anchor=Anchor(quote="Hello World"), span="zebra", replacement="z"
        ),
        RefusalReason.NOT_FOUND,
        ["zebra", "p1"],
    ),
    (
        "subspan-span-twice",
        lambda: PageNode(
            title=[Text("Doc")], children=[_para("p2", "ha ha")], block_id="root"
        ),
        lambda: SubSpanEditRequest(
            anchor=Anchor(quote="ha ha"), span="ha", replacement="z"
        ),
        RefusalReason.SPAN_NOT_SPLITTABLE,
        ["ha", "p2"],
    ),
    (
        "table-empty-row-key",
        _metrics_table,
        lambda: _treq("", column_header="Q3"),
        RefusalReason.NOT_FOUND,
        ["row_key"],
    ),
    (
        "table-row-key-not-found",
        _metrics_table,
        lambda: _treq("No Such Row", column_header="Q3"),
        RefusalReason.NOT_FOUND,
        ["No Such Row"],
    ),
    (
        "table-column-header-not-found",
        _metrics_table,
        lambda: _treq("On-time delivery", column_header="Q9"),
        RefusalReason.COLUMN_NOT_FOUND,
        ["Q9", "t1"],
    ),
    (
        "table-column-index-out-of-range",
        _metrics_table,
        lambda: _treq("On-time delivery", column_index=7),
        RefusalReason.COLUMN_NOT_FOUND,
        ["7", "t1"],
    ),
    (
        "table-ambiguous-column",
        _dup_header_table,
        lambda: _treq("On-time delivery", column_header="Q3"),
        RefusalReason.AMBIGUOUS,
        ["Q3"],
    ),
]


@pytest.mark.parametrize(
    "label,tree_fn,req_fn,reason,must_contain",
    _RESOLVE_REFUSAL_MATRIX,
    ids=[row[0] for row in _RESOLVE_REFUSAL_MATRIX],
)
def test_every_resolve_refusal_path_detail_names_its_identifier(
    label, tree_fn, req_fn, reason, must_contain
):
    result = resolve(req_fn(), tree_fn())
    assert isinstance(result, Refusal), f"{label}: expected a refusal, got {result!r}"
    assert result.reason is reason, f"{label}: {result.reason}"
    assert result.detail and result.detail.strip(), label
    for needle in must_contain:
        assert needle in result.detail, f"{label}: {needle!r} not in {result.detail!r}"


def test_write_hostile_refusal_detail_names_the_block_and_its_type():
    from larkdocio.model import ImageNode

    root = PageNode(
        title=[Text("Doc")],
        children=[ImageNode(token="tok", caption="a chart caption", block_id="img1")],
        block_id="root",
    )
    result = resolve(_req("a chart caption"), root)
    assert result.reason is RefusalReason.WRITE_HOSTILE
    assert "img1" in result.detail
    assert "Image" in result.detail or "image" in result.detail


def test_delete_target_not_found_detail_names_the_quote():
    result = resolve(_delete("no such target"), _scratch_doc())
    assert result.reason is RefusalReason.NOT_FOUND
    assert "no such target" in result.detail


# --------------------------------------------------------------------------- #
# AC2 (apply-time) — the write-time refusals carry actionable details too        #
# --------------------------------------------------------------------------- #

def test_apply_time_stale_anchor_detail_names_the_quote_and_block():
    root = _scratch_doc()
    plan = dry_run([_req("Hello World", "REPLACED")], root)
    # the live block no longer carries the quote → stale-anchor
    opener = StubOpener([_block_payload("p1", [_run("something else entirely")])])
    log = docx_apply(plan, _client(opener), "docTOKEN")
    entry = log.entries[0]
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "Hello World" in entry.refusal.detail
    assert "p1" in entry.refusal.detail


def test_apply_time_subspan_refusals_carry_details():
    root = PageNode(
        title=[Text("Doc")], children=[_para("p1", "the quick brown fox")], block_id="root"
    )
    req = SubSpanEditRequest(
        anchor=Anchor(quote="the quick brown fox"), span="quick", replacement="slow"
    )

    # (a) the span drifted out of the live text → stale-anchor
    plan = dry_run([req], root)
    opener = StubOpener([_block_payload("p1", [_run("the brown fox")])])
    entry = docx_apply(plan, _client(opener), "docTOKEN").entries[0]
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "quick" in entry.refusal.detail and "p1" in entry.refusal.detail

    # (b) the span now occurs twice → span-not-splittable
    plan = dry_run([req], root)
    opener = StubOpener([_block_payload("p1", [_run("quick quick")])])
    entry = docx_apply(plan, _client(opener), "docTOKEN").entries[0]
    assert entry.refusal.reason is RefusalReason.SPAN_NOT_SPLITTABLE
    assert "quick" in entry.refusal.detail and "p1" in entry.refusal.detail

    # (c) the span crosses runs of differing style → span-not-splittable (no guess)
    plan = dry_run([req], root)
    opener = StubOpener([
        _block_payload("p1", [_run("the qui", bold=True), _run("ck brown fox")]),
    ])
    entry = docx_apply(plan, _client(opener), "docTOKEN").entries[0]
    assert entry.refusal.reason is RefusalReason.SPAN_NOT_SPLITTABLE
    assert "quick" in entry.refusal.detail


def test_apply_time_table_cell_refusals_carry_details():
    root = _metrics_table()
    req = _treq("On-time delivery", column_header="Q3", replacement="99.9%")

    # (a) the row key drifted out of the live KEY cell → stale-anchor
    plan = dry_run([req], root)
    opener = StubOpener([_block_payload("c10__t", [_run("Renamed row")])])
    entry = docx_apply(plan, _client(opener), "docTOKEN").entries[0]
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "On-time delivery" in entry.refusal.detail

    # (b) the target cell's content drifted since plan time → stale-anchor
    plan = dry_run([req], root)
    opener = StubOpener([
        _block_payload("c10__t", [_run("On-time delivery")]),
        _block_payload("c11__t", [_run("96.0%")]),
    ])
    entry = docx_apply(plan, _client(opener), "docTOKEN").entries[0]
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "c11__t" in entry.refusal.detail
    assert "96.0%" in entry.refusal.detail


# =========================================================================== #
# AC3 + AC4 — sheets: `unknown-tab` (plan time) vs `tab-vanished` (mid-flight)  #
# =========================================================================== #

class TabAwareGateway:
    """A sheets client seam that knows its own tabs — the shape the real
    :class:`~larkdocio.sheets.write_client.SheetsWriteClient` has (``query_tabs``).

    ``values`` maps an A1 range to a matrix (or an ``Exception`` to raise). A range whose
    ``{sheet_id}!`` prefix is not in ``tabs`` raises the Lark ``90215 not found sheetId``
    error the live API returns — the exact failure the dogfood session hit.
    """

    def __init__(self, *, revision=1, tabs=(), values=None, geometry=None, tabs_error=None):
        self.revision = revision
        self.tabs = [dict(t) for t in tabs]
        self.values = dict(values or {})
        self.geometry = dict(geometry or {})
        self.tabs_error = tabs_error
        self.tab_queries = 0
        self.puts = []

    # -- reads ------------------------------------------------------------- #
    def query_tabs(self, spreadsheet_token):
        self.tab_queries += 1
        if self.tabs_error is not None:
            raise self.tabs_error
        return [dict(t) for t in self.tabs]

    def read_revision(self, spreadsheet_token):
        return self.revision

    def _known(self, a1_range):
        sid = a1_range.split("!")[0] if "!" in a1_range else None
        return sid is None or any(t.get("sheet_id") == sid for t in self.tabs)

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        if not self._known(a1_range):
            raise LarkAPIError(
                f"sheets value read failed: Code: 90215, Msg: not found sheetId, "
                f"range {a1_range}"
            )
        v = self.values.get(a1_range)
        if isinstance(v, Exception):
            raise v
        return [] if v is None else v

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        return self.geometry.get(sheet_id)

    # -- writes ------------------------------------------------------------ #
    def put_values(self, spreadsheet_token, a1_range, values):
        self.puts.append((a1_range, values))
        self.revision += 1
        return {"revision": self.revision}


class NoQueryTabsGateway:
    """A client seam WITHOUT ``query_tabs`` — the tab listing is unobtainable, so the
    engine must degrade honestly to ``tab-vanished`` rather than invent a did-you-mean."""

    def __init__(self, *, revision=1, values=None):
        self.revision = revision
        self.values = dict(values or {})

    def read_revision(self, spreadsheet_token):
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        v = self.values.get(a1_range)
        if isinstance(v, Exception):
            raise v
        if v is None:
            raise LarkAPIError("sheets value read failed: Code: 90215, Msg: not found sheetId")
        return v


_SHEET1 = {"sheet_id": "3bf016", "title": "Sheet1", "index": 0}
_DATA = {"sheet_id": "9ab77c", "title": "Data", "index": 1}
_BANG = {"sheet_id": "0f12de", "title": "Q3!Raw", "index": 2}


def test_f4_repro_b_guide_verbatim_sheet1_range_refuses_unknown_tab_with_did_you_mean():
    """Repro B verbatim: the guide's own ``"Sheet1!A1:A1"``, where ``Sheet1`` is a TITLE.

    Before LD-131 this refused ``tab-vanished`` — the staleness story — sending the
    consumer to re-read and re-plan a tab that never existed.
    """
    gw = TabAwareGateway(revision=7, tabs=[_SHEET1], values={"3bf016!A1:A1": [["old"]]})
    plan = sheets_dry_run(
        [ValueWriteRequest.for_a1("Sheet1!A1:A1", [["x"]])], gw, TOKEN
    )
    entry = plan.entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason == SheetsRefusal.UNKNOWN_TAB == "unknown-tab"
    detail = entry.refusal.detail
    assert "Sheet1" in detail                     # the wrong identifier, named
    assert "3bf016" in detail                     # the did-you-mean sheet_id
    assert "sheet_id" in detail                   # the identifier KIND
    assert "title" in detail.lower()
    # nothing was written, and the plan is still a plan
    assert gw.puts == []


def test_f4_repro_b_no_longer_claims_tab_vanished():
    gw = TabAwareGateway(revision=7, tabs=[_SHEET1])
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("Sheet1!A1:A1", [["x"]])], gw, TOKEN
    ).entries[0]
    assert entry.refusal.reason != SheetsRefusal.TAB_VANISHED


def test_f4_repro_b_the_right_sheet_id_resolves():
    """The paired half of the repro: ``'3bf016!A1:A1'`` resolves (as it did live)."""
    gw = TabAwareGateway(revision=7, tabs=[_SHEET1], values={"3bf016!A1:A1": [["old"]]})
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("3bf016!A1:A1", [["x"]])], gw, TOKEN
    ).entries[0]
    assert entry.outcome == "resolved"
    assert entry.before == [["old"]]


def test_unknown_tab_detail_flags_a_wrong_kind_id_that_is_actually_a_real_TITLE():
    gw = TabAwareGateway(revision=1, tabs=[_SHEET1, _DATA])
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("Data!B2:B2", [["x"]])], gw, TOKEN
    ).entries[0]
    assert entry.refusal.reason == SheetsRefusal.UNKNOWN_TAB
    # it must say plainly: that string is a TITLE, and here is the id to use instead
    assert "title" in entry.refusal.detail.lower()
    assert "9ab77c" in entry.refusal.detail


@pytest.mark.parametrize(
    "tabs,expected_ids",
    [
        ([_SHEET1], ["3bf016"]),
        ([_SHEET1, _DATA], ["3bf016", "9ab77c"]),
        ([_SHEET1, _DATA, _BANG], ["3bf016", "9ab77c", "0f12de"]),
    ],
    ids=["one-tab", "two-tabs", "three-tabs-incl-bang-title"],
)
def test_unknown_tab_did_you_mean_lists_every_actual_pair(tabs, expected_ids):
    gw = TabAwareGateway(revision=1, tabs=tabs)
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("nope!A1:A1", [["x"]])], gw, TOKEN
    ).entries[0]
    detail = entry.refusal.detail
    assert entry.refusal.reason == SheetsRefusal.UNKNOWN_TAB
    for sid in expected_ids:
        assert sid in detail, detail
    for tab in tabs:
        assert tab["title"] in detail, detail
    assert gw.tab_queries == 1  # exactly one listing read, on the failure path only


def test_unknown_tab_did_you_mean_quotes_a_title_containing_a_bang_unambiguously():
    """A tab titled ``Q3!Raw`` must not read as ``Q3`` + a range separator."""
    gw = TabAwareGateway(revision=1, tabs=[_BANG])
    detail = sheets_dry_run(
        [ValueWriteRequest.for_a1("Q3!A1:A1", [["x"]])], gw, TOKEN
    ).entries[0].refusal.detail
    assert "'Q3!Raw'" in detail or '"Q3!Raw"' in detail, detail
    assert "0f12de" in detail


def test_tab_vanished_is_RESERVED_for_a_tab_that_vanished_MID_FLIGHT():
    """The tab was readable at plan time and is gone at apply re-validation."""
    gw = TabAwareGateway(revision=5, tabs=[_SHEET1], values={"3bf016!A1:A1": [["old"]]})
    plan = sheets_dry_run([ValueWriteRequest.for_a1("3bf016!A1:A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].outcome == "resolved"

    # ... and now the tab disappears under us (the apply-time re-read fails)
    gw.values["3bf016!A1:A1"] = LarkAPIError(
        "sheets value read failed: Code: 90215, Msg: not found sheetId"
    )
    log = sheets_apply(plan, gw)
    entry = log.entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason == SheetsRefusal.TAB_VANISHED
    assert gw.puts == []


def test_plan_time_read_failure_on_an_EXISTING_tab_still_refuses_tab_vanished():
    """The listing PROVES the tab exists → the read failed for another reason → staleness."""
    gw = TabAwareGateway(
        revision=1,
        tabs=[_SHEET1],
        values={"3bf016!A1:A1": LarkAPIError("sheets value read failed: Code: 1310214")},
    )
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("3bf016!A1:A1", [["x"]])], gw, TOKEN
    ).entries[0]
    assert entry.refusal.reason == SheetsRefusal.TAB_VANISHED
    assert "3bf016!A1:A1" in entry.refusal.detail


def test_an_unobtainable_tab_listing_degrades_honestly_to_tab_vanished():
    """No ``query_tabs`` on the seam ⇒ we cannot PROVE the tab never existed."""
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("whatever!A1:A1", [["x"]])], NoQueryTabsGateway(), TOKEN
    ).entries[0]
    assert entry.refusal.reason == SheetsRefusal.TAB_VANISHED


@pytest.mark.parametrize(
    "tabs_error",
    [LarkAPIError("tab query failed: Code: 1310213"), RuntimeError("seam exploded")],
    ids=["typed-api-error", "unexpected-error"],
)
def test_a_failing_tab_listing_degrades_honestly_to_tab_vanished(tabs_error):
    """Enriching a refusal must never ESCALATE it into a crash — even on a surprise."""
    gw = TabAwareGateway(revision=1, tabs=[_SHEET1], tabs_error=tabs_error)
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("nope!A1:A1", [["x"]])], gw, TOKEN
    ).entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason == SheetsRefusal.TAB_VANISHED


def test_a_garbage_tab_listing_degrades_honestly_to_tab_vanished():
    """``query_tabs`` answering something unusable proves nothing about the tab set."""
    for tabs in ([], [{"title": "id-less"}]):
        gw = TabAwareGateway(revision=1, tabs=tabs)
        entry = sheets_dry_run(
            [ValueWriteRequest.for_a1("nope!A1:A1", [["x"]])], gw, TOKEN
        ).entries[0]
        assert entry.refusal.reason == SheetsRefusal.TAB_VANISHED, tabs


def test_unknown_tab_also_covers_the_merge_preview_plan_time_read():
    gw = TabAwareGateway(revision=1, tabs=[_SHEET1])
    entry = sheets_dry_run([MergeCells(a1_range="nope!A1:C1")], gw, TOKEN).entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason == SheetsRefusal.UNKNOWN_TAB
    assert "3bf016" in entry.refusal.detail


def test_unknown_tab_also_covers_the_destructive_delete_snapshot():
    """A row delete whose removed payload cannot be snapshot because the tab is UNKNOWN
    names that — not staleness (it still refuses; nothing is destroyed)."""
    gw = TabAwareGateway(revision=1, tabs=[_SHEET1], geometry={})
    entry = sheets_dry_run([DeleteRows(sheet_id="nope", first=2, last=2)], gw, TOKEN).entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason == SheetsRefusal.UNKNOWN_TAB
    assert "nope" in entry.refusal.detail


def test_destructive_delete_on_a_KNOWN_tab_with_unreadable_geometry_stays_tab_vanished():
    gw = TabAwareGateway(revision=1, tabs=[_SHEET1], geometry={"3bf016": None})
    entry = sheets_dry_run(
        [DeleteRows(sheet_id="3bf016", first=2, last=2)], gw, TOKEN
    ).entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason == SheetsRefusal.TAB_VANISHED


def test_unknown_tab_refusal_json_round_trips():
    gw = TabAwareGateway(revision=1, tabs=[_SHEET1])
    entry = sheets_dry_run(
        [ValueWriteRequest.for_a1("nope!A1:A1", [["x"]])], gw, TOKEN
    ).entries[0]
    wire = json.loads(json.dumps(entry.to_dict()))
    assert wire["refusal"]["reason"] == "unknown-tab"
    assert wire["refusal"]["detail"] == entry.refusal.detail
    assert SheetsRefusal.from_dict(wire["refusal"]) == entry.refusal


def test_unknown_tab_and_tab_vanished_are_distinct_reasons():
    assert SheetsRefusal.UNKNOWN_TAB != SheetsRefusal.TAB_VANISHED
    assert SheetsRefusal.unknown_tab("d").reason == "unknown-tab"
    assert SheetsRefusal.tab_vanished("d").reason == "tab-vanished"
