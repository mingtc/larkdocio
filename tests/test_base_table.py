"""LD-248 — Base table→Markdown assembly and the public read surface.

Offline end to end. Every fixture is a **committed probe capture**
(`tests/captures/base-study/captures/`) round-tripped through the pinned SDK's own deserializer, so an
API drift reddens at deserialization rather than travelling on as a plausible-looking
``None`` (PROJECT.md § Quality bar; the `tests/test_base_client.py` precedent).

The two invariants this story exists for, and the reason each is a test rather than a
comment:

1. **Rows project against the FIELD LIST, never the keys a record happens to carry.** An
   empty cell is an **absent key** in ``records/search``, so a union-of-observed-keys
   assembler silently drops columns and mis-aligns every row. The `p0-3-03` capture is the
   ragged corpus: five fields, three keys per row.
2. **`view_id` is not a column selector.** The same capture proves it from both sides —
   ``fields?view_id=`` returned all five fields in unscoped order, and
   ``records/search {view_id}`` returned the same field keys per row as the unscoped read.
   L1 therefore renders the **table's** schema, and the shipped docs may not say otherwise.
"""
import hashlib
import json

import pytest
from lark_oapi.api.bitable.v1 import AppTableField, GetAppResponse, ListAppTableResponse

import base_captures

from larkdocio.base import cells as base_cells
from larkdocio.base import read as base_read
from larkdocio.base import table as base_table
from larkdocio.base.cells import STAGE_OPAQUE_MARKER, FieldSpec, RenderContext
from larkdocio.errors import LarkConfigError

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"
_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "base_scratch.expected.md"


# --------------------------------------------------------------------------- #
# Fixtures: the committed captures, through the SDK deserializer.              #
# --------------------------------------------------------------------------- #

#: The capture loader lives in ``tests/base_captures.py`` since LD-251: the shipped guide's Base
#: recipe needs the SAME Base behind an offline read client, and two loaders would be two
#: definitions of "the Scratch Base". Re-exported here so every use below reads unchanged.
capture = base_captures.capture
unmarshal = base_captures.unmarshal
scratch_base = base_captures.scratch_base


def assembled_scratch_base():
    """The Scratch Base as the shipped assembler builds it."""
    app, tables, per_table = scratch_base()
    context = RenderContext(time_zone=app.time_zone)
    return base_table.assemble_base(
        app_token=app.app_token,
        name=app.name,
        time_zone=app.time_zone,
        tables=[
            base_table.assemble_table(
                table_id=t.table_id,
                name=t.name,
                fields=per_table[t.table_id][0],
                records=per_table[t.table_id][1],
                context=context,
            )
            for t in tables
        ],
    )


def spec(name, type_, ui_type, **kwargs):
    return FieldSpec(field_name=name, type=type_, ui_type=ui_type, **kwargs)


class _Record:
    """The one thing the assembler reads off a record: its id and its ``fields`` dict."""

    def __init__(self, record_id, fields):
        self.record_id = record_id
        self.fields = fields


# --------------------------------------------------------------------------- #
# AC1 — the documented output shape, pinned by a golden built from captures.   #
# --------------------------------------------------------------------------- #

def test_ac1_the_whole_scratch_base_renders_to_the_committed_golden():
    """AC1: `## <table name>` from `…/tables`, a header row from `…/fields` in field order,
    one row per record from `…/records/search`, each cell rendered by LD-246's registry.

    The golden is built from three committed captures of one real Base, so it pins the
    **shape Lark actually returned** rather than a shape someone found convenient."""
    rendered = base_table.render_base(assembled_scratch_base())
    assert rendered == _GOLDEN.read_text(encoding="utf-8").rstrip("\n"), (
        "the Base render drifted from the committed golden; regenerate ONLY if the change "
        "was intended and reviewed")


def test_ac1_the_heading_is_the_TABLE_NAME_from_the_tables_endpoint():
    _app, tables, _per = scratch_base()
    rendered = base_table.render_base(assembled_scratch_base())
    for t in tables:
        assert f"## {t.name}" in rendered
    assert rendered.startswith("## Table\n")


def test_ac1_the_header_row_is_the_FIELD_LIST_IN_FIELD_ORDER():
    """Field order is the table's own, not sorted, not the order the records' keys happen
    to appear in — the records below list `Email` first and `Text` second."""
    _app, tables, per_table = scratch_base()
    fields, _records = per_table[tables[0].table_id]
    names = [f.field_name for f in fields]
    assert names == ["Text", "lookup", "Email", "stage?"]
    header = base_table.render_base(assembled_scratch_base()).splitlines()[2]
    assert header == "| " + " | ".join(names) + " |"


def test_ac1_the_body_is_ONE_ROW_PER_RECORD_in_search_order():
    _app, tables, per_table = scratch_base()
    _fields, records = per_table[tables[0].table_id]
    assembled = assembled_scratch_base().tables[0]
    assert [row.record_id for row in assembled.rows] == [r.record_id for r in records]


# --------------------------------------------------------------------------- #
# AC2 — rows project against the FIELD LIST (LD-246 AC4 at the assembly seam). #
# --------------------------------------------------------------------------- #

def test_ac2_every_row_has_exactly_len_fields_cells_over_a_ragged_corpus():
    """AC2: the ragged corpus is `p0-3-03` — **five** fields, **three** keys per record.

    A union-of-observed-keys assembler would emit three-cell rows under a five-cell header,
    which is a corrupt table, not a narrow one."""
    data = capture("p0-3-03-view-projection.json")["response"]["data"]
    fields = [spec(name, 1, "Text") for name in data["unscoped_field_order"]]
    key_sets = data["search_no_view_id"]["field_keys_per_row"]
    assert len(fields) == 5 and all(len(keys) == 3 for keys in key_sets), (
        "the capture stopped being ragged; this test needs a ragged corpus to mean anything")

    records = [_Record(f"rec{i}", {k: [{"text": k, "type": "text"}] for k in keys})
               for i, keys in enumerate(key_sets)]
    assembled = base_table.assemble_table(
        table_id="tbl", name="Ragged", fields=fields, records=records)
    assert all(len(row.cells) == len(fields) for row in assembled.rows)
    for line in base_table.render_table(assembled).splitlines():
        if line.startswith("|"):
            assert line.count("|") == len(fields) + 1


def test_ac2_a_field_MISSING_from_every_record_still_gets_its_column():
    """The sharpest form: a populated-but-empty column appears in **no** record at all, so a
    union implementation drops the column entirely and shifts every cell left."""
    fields = [spec("A", 1, "Text"), spec("Never", 1, "Text"), spec("B", 1, "Text")]
    records = [_Record("rec1", {"A": [{"text": "a", "type": "text"}],
                                "B": [{"text": "b", "type": "text"}]})]
    assembled = base_table.assemble_table(
        table_id="tbl", name="T", fields=fields, records=records)
    assert assembled.rows[0].cells == ("a", "", "b")


def test_ac2_a_record_carrying_an_UNKNOWN_key_does_not_grow_the_row():
    """The projection is one-directional: the field list decides the columns, so a key the
    schema does not know is not a column and cannot widen the row."""
    fields = [spec("A", 1, "Text")]
    records = [_Record("rec1", {"A": [{"text": "a", "type": "text"}], "Ghost": "boo"})]
    assembled = base_table.assemble_table(
        table_id="tbl", name="T", fields=fields, records=records)
    assert assembled.rows[0].cells == ("a",)


def test_ac2_checkbox_false_is_an_ABSENT_KEY_and_renders_unchecked_at_the_seam():
    """LD-246's absent-value rule has to survive the assembly seam: `Checkbox` false is an
    absent key, so its cell is `[ ]`, never blank and never "unknown"."""
    fields = [spec("Done", 7, "Checkbox")]
    rows = base_table.assemble_table(
        table_id="tbl", name="T", fields=fields, records=[_Record("r", {})]).rows
    assert rows[0].cells == ("[ ]",)


# --------------------------------------------------------------------------- #
# AC3 — the TABLE's schema, not the VIEW's. Proven against the capture.        #
# --------------------------------------------------------------------------- #

def test_ac3_the_capture_proves_view_id_is_not_a_column_selector():
    """AC3, from the capture rather than from a claim: with fields hidden in the view,
    `fields?view_id=` returned **all** fields in the **unscoped** order, and
    `records/search {view_id}` returned the **same** field keys per row as the unscoped
    read. Neither leg narrows anything."""
    data = capture("p0-3-03-view-projection.json")["response"]["data"]
    assert data["view_scoped_field_order"] == data["unscoped_field_order"]
    assert data["view_scoped_fields_code"] == 0
    assert (data["search_with_view_id"]["field_keys_per_row"]
            == data["search_no_view_id"]["field_keys_per_row"])
    assert data["search_with_view_id"]["n"] == data["search_no_view_id"]["n"]


def test_ac3_the_shipped_read_surface_NEVER_SENDS_A_VIEW_ID():
    """The library's answer to a non-selector is not to expose it: no entry point on the
    read surface takes a `view_id`, so a consumer cannot be misled into thinking it
    narrows the render."""
    import inspect

    for fn in (base_read.read_base, base_read.read_base_markdown,
               base_table.assemble_table, base_table.assemble_base):
        assert "view_id" not in inspect.signature(fn).parameters, (
            f"{fn.__name__} takes a view_id; L1 renders the table's schema")


def test_ac3_no_shipped_doc_describes_view_id_as_a_column_selector():
    """AC3's documentation half. The claim is easy to make by accident ("scope the read to a
    view"), so the corpus is swept for the phrasings that would make it."""
    import consumer_text

    forbidden = (
        "view_id selects", "view_id to select", "scope the columns",
        "select the columns", "column selector for", "limits the fields",
        "narrows the fields", "restrict the fields",
    )
    docs = dict(consumer_text.shipped_docs())
    docs["BASE.md"] = (_REPO / "BASE.md").read_text(encoding="utf-8")
    for name, text in docs.items():
        lowered = text.lower()
        for phrase in forbidden:
            assert phrase not in lowered, f"{name} describes a view as a column selector"


def test_ac3_BASE_md_states_the_finding_and_names_the_only_real_projection():
    text = (_REPO / "BASE.md").read_text(encoding="utf-8")
    assert "not a column selector" in text
    assert "field_names" in text, (
        "the only genuine server-side projection must be named where the negative is stated")


def test_ac3_the_read_surface_docstring_says_what_a_view_does_and_does_not_do():
    """AC3 [AMENDED]: `PATCH property.hidden_fields` is accepted and has no API effect, so
    neither hiding fields nor scoping by view changes what a reader sees. Anywhere the
    surface could imply otherwise, it says so."""
    doc = base_read.read_base.__doc__ or ""
    assert "view" in doc.lower()
    assert "not a column selector" in doc.lower()


# --------------------------------------------------------------------------- #
# AC4 — a whole Base renders as its tables, in `GET …/tables` order.           #
# --------------------------------------------------------------------------- #

def test_ac4_tables_render_in_the_order_the_tables_endpoint_returned():
    rendered = base_table.render_base(assembled_scratch_base())
    assert rendered.index("## Table\n") < rendered.index("## Table 2\n")


def test_ac4_the_order_is_the_LIST_ORDER_not_a_sort():
    """Proven by reversing the input: a sorted-by-name implementation would be unmoved."""
    fields = [spec("A", 1, "Text")]
    tables = [base_table.assemble_table(table_id=f"tbl{i}", name=name,
                                        fields=fields, records=[])
              for i, name in enumerate(("Zebra", "Apple"))]
    doc = base_table.assemble_base(app_token="app", name="B", time_zone=None, tables=tables)
    rendered = base_table.render_base(doc)
    assert rendered.index("## Zebra") < rendered.index("## Apple")


def test_ac4_the_heading_level_is_stable_and_configurable_without_changing_the_default():
    doc = assembled_scratch_base()
    assert base_table.render_base(doc).startswith("## ")
    assert base_table.render_base(doc, heading_level=3).startswith("### ")


# --------------------------------------------------------------------------- #
# AC5 — degenerate shapes are well-formed, not crashes.                        #
# --------------------------------------------------------------------------- #

def test_ac5_a_table_with_fields_and_no_records_renders_a_header_and_no_rows():
    assembled = base_table.assemble_table(
        table_id="tbl", name="Empty", fields=[spec("A", 1, "Text"), spec("B", 1, "Text")],
        records=[])
    assert base_table.render_table(assembled) == "## Empty\n\n| A | B |\n|---|---|"


def test_ac5_a_table_with_ZERO_FIELDS_renders_a_named_heading_and_the_documented_marker():
    assembled = base_table.assemble_table(
        table_id="tbl", name="No schema", fields=[], records=[])
    rendered = base_table.render_table(assembled)
    assert rendered == f"## No schema\n\n{base_table.EMPTY_TABLE_MARKER}"
    assert "|" not in rendered, "a fieldless table must not emit a zero-column table"


def test_ac5_a_base_with_ZERO_TABLES_renders_the_documented_marker():
    doc = base_table.assemble_base(app_token="app", name="Husk", time_zone=None, tables=[])
    assert base_table.render_base(doc) == base_table.EMPTY_BASE_MARKER


def test_ac5_the_husk_capture_is_the_zero_table_case_AND_CARRIES_NO_TOTAL():
    """AC5: the zero-table Base is reachable in the wild — the husk app `Example3…` answers
    `{"items": []}` with **no `total`, no `page_token`, no `has_more`**, which no healthy
    app does. The rule it teaches is wider than this one case: **a missing `total` or
    `page_token` may never be assumed present.**"""
    body = capture("02-bitable18-tables.json")["response"]["data"]
    assert body == {"items": []}
    tables = unmarshal(capture("02-bitable18-tables.json")["response"],
                       ListAppTableResponse).data.items
    doc = base_table.assemble_base(
        app_token="Example3", name="Husk", time_zone=None,
        tables=[base_table.assemble_table(table_id=t.table_id, name=t.name,
                                          fields=[], records=[])
                for t in (tables or ())])
    assert base_table.render_base(doc) == base_table.EMPTY_BASE_MARKER


def test_ac5_the_assembler_reads_NEITHER_total_NOR_page_token():
    """The husk's rule, enforced on the code rather than on one payload: the assembly seam
    never names a counter it cannot rely on."""
    source = (_REPO / "src" / "larkdocio" / "base" / "table.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    body = code.split('"""', 2)[-1] if code.count('"""') >= 2 else code
    for counter in (".total", '"total"', ".page_token", '"page_token"'):
        assert counter not in body, f"the assembler leans on {counter}"


def test_ac5_a_record_whose_fields_are_missing_entirely_is_a_row_of_empties():
    """A record with no `fields` key at all is not a crash and not a dropped row: it is a
    row of absent cells, because the field list still says how wide the row is."""
    fields = [spec("A", 1, "Text"), spec("B", 7, "Checkbox")]
    for empty in (None, {}, "not-a-dict"):
        rows = base_table.assemble_table(
            table_id="t", name="T", fields=fields,
            records=[_Record("r", empty)]).rows
        assert rows[0].cells == ("", "[ ]")


# --------------------------------------------------------------------------- #
# AC6 — GFM safety.                                                            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("a|b", "a\\|b"),
    ("line1\nline2", "line1<br>line2"),
    ("  padded  ", "padded"),
    ("\n  a | b \n", "a \\| b"),
])
def test_ac6_a_hostile_cell_cannot_break_the_table(raw, expected):
    assert base_table.escape_cell(raw) == expected


def test_ac6_the_escape_is_BYTE_IDENTICAL_to_the_docx_and_sheets_convention():
    """AC6's precedent is `BLOCKS.md` type 31 — the docx table serializer's own escape,
    which the Sheets surface already re-uses verbatim. Three copies of a convention is two
    too many to trust by eye, so the equivalence is asserted rather than claimed."""
    from larkdocio.sheets.table import escape_cell as sheets_escape

    corpus = ["a|b", "x\ny", "  s  ", "", "|", "\n", "a\\|b", "a | b\nc | d", "★ 4"]
    for text in corpus:
        assert base_table.escape_cell(text) == sheets_escape(text)


def test_ac6_a_hostile_cell_keeps_the_rendered_table_rectangular():
    fields = [spec("A", 1, "Text"), spec("B", 1, "Text")]
    records = [_Record("r", {"A": [{"text": "a|b\nc", "type": "text"}],
                             "B": [{"text": "  padded  ", "type": "text"}]})]
    assembled = base_table.assemble_table(
        table_id="t", name="T", fields=fields, records=records)
    lines = [ln for ln in base_table.render_table(assembled).splitlines()
             if ln.startswith("|")]
    assert all(ln.count("|") - ln.count("\\|") == 3 for ln in lines), lines


def test_ac6_the_structured_intermediate_carries_the_UNESCAPED_cell():
    """The escape is a Markdown concern. A consumer that took the structured route asked
    precisely not to be handed Markdown, so it gets the cell as rendered."""
    fields = [spec("A", 1, "Text")]
    records = [_Record("r", {"A": [{"text": "a|b", "type": "text"}]})]
    assembled = base_table.assemble_table(
        table_id="t", name="T", fields=fields, records=records)
    assert assembled.rows[0].cells == ("a|b",)
    assert "a\\|b" in base_table.render_table(assembled)


# --------------------------------------------------------------------------- #
# AC7 — the public read surface, and the URL-vs-token question ON ITS MERITS.  #
# --------------------------------------------------------------------------- #

def test_ac7_both_entry_points_exist_and_are_re_exported_from_the_package():
    from larkdocio import base as base_pkg

    assert base_pkg.read_base is base_read.read_base
    assert base_pkg.read_base_markdown is base_read.read_base_markdown
    assert base_pkg.render_base is base_table.render_base


def test_ac7_one_returns_MARKDOWN_and_one_returns_THE_STRUCTURED_INTERMEDIATE():
    """AC7: a consumer is not forced through the string. `read_base` hands back the typed
    document — field specs, record ids, rendered cells — and `render_base` turns that into
    Markdown with no second network read."""
    doc = assembled_scratch_base()
    assert isinstance(doc, base_table.BaseRead)
    assert isinstance(doc.tables[0], base_table.BaseTableRead)
    assert isinstance(doc.tables[0].fields[0], FieldSpec)
    assert isinstance(doc.tables[0].rows[0], base_table.BaseRow)
    assert isinstance(base_table.render_base(doc), str)
    assert base_read.read_base.__annotations__["return"] is base_table.BaseRead
    assert base_read.read_base_markdown.__annotations__["return"] is str


def test_ac7_the_docstring_states_WHICH_IT_TAKES_a_url_or_an_app_token():
    for fn in (base_read.read_base, base_read.read_base_markdown):
        doc = (fn.__doc__ or "").lower()
        assert "app_token" in doc and "url" in doc, (
            f"{fn.__name__}'s docstring must state which it takes")


def test_ac7_A_BASE_URLS_SLUG_IS_THE_APP_TOKEN_verified_on_its_own_merits():
    """**AC7's amendment, verified rather than inherited.** The spec warned that a Base URL's
    slug "is not necessarily the `app_token`" because `.env`'s `LARKDOCIO_SCRATCH_BASE` slug
    and the token every capture uses differ. **That was two different Bases, not a
    slug/token mismatch** (O3, resolved 2026-08-03).

    Checked here from the artifacts rather than from the correction: the slug in the
    committed `.env.example` URL is **byte-identical** to the `app_token` the same Base's
    own `GET …/apps/{app_token}` capture reports, and to the token the tables and per-table
    captures were taken against. So the slug **is** the app_token, and the surface may
    resolve a URL."""
    from larkdocio.common import validate_download_url

    env_example = (_REPO / ".env.example").read_text(encoding="utf-8")
    url = [line.split("=", 1)[1].strip() for line in env_example.splitlines()
           if line.startswith("LARKDOCIO_SCRATCH_BASE=")][0]
    domain, url_type, slug = validate_download_url(url)
    assert (domain, url_type) == ("larksuite.com", "base")

    app = unmarshal(capture("p1-q0-01-app-meta.json")["response"], GetAppResponse).data.app
    assert slug == app.app_token, (
        "the URL slug and the app_token diverged — AC7's warning would be back, and the "
        "surface's URL resolution would have to go")
    assert capture("p1-q0-03-per-table.json")["app_token"] == slug


def test_ac7_resolve_base_takes_a_url_OR_a_bare_token():
    assert base_read.resolve_base(
        "https://your-domain.larksuite.com/base/BaseScratchExample000000001"
    ) == ("larksuite.com", "BaseScratchExample000000001")
    assert base_read.resolve_base("BaseScratchExample000000001") == (
        None, "BaseScratchExample000000001")


@pytest.mark.parametrize("bad,why", [
    ("https://x.feishu.cn/sheets/Shtcn1", "sheets"),
    ("https://x.feishu.cn/docx/Docx1", "docx"),
])
def test_ac7_a_NON_BASE_url_is_refused_by_name_not_read_as_a_token(bad, why):
    """Recognising a URL is not the same as it naming a Base. Handing a docx token to the
    Base client would fail later and vaguer, so it is refused here, by name."""
    with pytest.raises(LarkConfigError) as exc:
        base_read.resolve_base(bad)
    assert why in str(exc.value)


@pytest.mark.parametrize("bad", ["", "   ", "not a token", "has/slash", None])
def test_ac7_a_garbage_token_is_refused_rather_than_sent_to_lark(bad):
    with pytest.raises(LarkConfigError):
        base_read.resolve_base(bad)


def test_ac7_read_base_drives_the_client_and_never_touches_a_write_credential(monkeypatch):
    """The whole surface over a fake client: five reads, the app's `time_zone` threaded into
    the render context, and `get_write_credentials` wired to explode."""
    import larkdocio.common.auth as auth

    def boom(*_a, **_kw):
        raise AssertionError("the Base read surface consulted a WRITE credential")

    monkeypatch.setattr(auth, "get_write_credentials", boom, raising=False)

    app, tables, per_table = scratch_base()
    calls = []

    class _FakeClient:
        def get_app(self, app_token):
            calls.append(("get_app", app_token))
            return app

        def list_tables(self, app_token):
            calls.append(("list_tables", app_token))
            return tables

        def list_fields(self, app_token, table_id):
            calls.append(("list_fields", table_id))
            return per_table[table_id][0]

        def search_records(self, app_token, table_id):
            calls.append(("search_records", table_id))
            return per_table[table_id][1]

    doc = base_read.read_base("BaseScratchExample000000001", client=_FakeClient())
    assert doc.name == "Scratch Base" and doc.time_zone == "Asia/Singapore"
    assert [c[0] for c in calls] == [
        "get_app", "list_tables",
        "list_fields", "search_records", "list_fields", "search_records"]
    assert base_read.read_base_markdown(
        "BaseScratchExample000000001", client=_FakeClient()
    ) == base_table.render_base(doc)


def test_ac7_the_read_surface_does_NOT_list_views():
    """`list_views` is a real op, and L1 has no use for it: a view changes nothing about the
    projection (AC3), so calling it would be a per-table API call bought for nothing."""
    class _Exploding:
        def get_app(self, *a, **k):
            raise AssertionError("unreachable")

        def list_views(self, *a, **k):
            raise AssertionError("the read surface listed views; a view is not a projection")

    import inspect
    source = inspect.getsource(base_read)
    assert "list_views" not in source.split('"""')[-1]


def test_ac7_the_surface_is_REGISTERED_but_still_not_a_TOP_LEVEL_export():
    """LD-251 opened the front door and drew the line where it drew it, so both halves are
    pinned rather than one.

    The registry now reports the Base surfaces — that is what makes them discoverable from an
    installed wheel — while the package's own export list deliberately does **not** carry
    ``base``: reaching the surface is ``import larkdocio.base``, exactly as the README's layout
    row says, and quietly adding it to ``__all__`` would change the shape of
    ``capabilities()["entry_points"]`` (projected off that list) as a side effect."""
    import larkdocio

    assert not [n for n in getattr(larkdocio, "__all__", ()) if "base" in n.lower()]
    registered = sorted(sid for sid in larkdocio.capabilities(full=True)["surfaces"] if "base" in sid)
    assert registered == [
        "base-comments-read", "base-embedded-deep-read", "base-read",
        "base-schema-write", "base-write"]
    # LD-260 published the fourth, and it is the first that is NOT read-only. The line this
    # test pins is unchanged and is the one that matters here: the registry reports the
    # surfaces, and `__all__` still carries nothing Base — so reaching either half is still
    # `import larkdocio.base`.
    modes = {sid: larkdocio.capabilities(full=True)["surfaces"][sid]["mode"] for sid in registered}
    assert modes == {"base-comments-read": "read", "base-embedded-deep-read": "read",
                     "base-read": "read", "base-write": "write",
                     "base-schema-write": "write"}


# --------------------------------------------------------------------------- #
# AC8 — determinism.                                                           #
# --------------------------------------------------------------------------- #

def test_ac8_two_assemblies_of_the_same_capture_are_byte_identical():
    first = base_table.render_base(assembled_scratch_base())
    second = base_table.render_base(assembled_scratch_base())
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_ac8_the_success_bodies_carry_no_nonce_to_be_deterministic_about():
    """AC8's grounding, read off the capture rather than asserted: two back-to-back live
    reads of the whole spine hashed the same, and the probe's own note records **why** that
    is achievable — a `code:0` body carries no `log_id`, so there is no per-request nonce to
    be deterministic in spite of."""
    data = capture("04-determinism.json")["response"]["data"]
    assert data["byte_identical"] is True
    assert data["read1_sha256"] == data["read2_sha256"]
    # LD-699: the recorded digest was of a read taken before the tenant values were replaced, so
    # this copy carries a stand-in — the SHA-256 of the text "example spine read"
    # (tests/captures/README.md § 2). The equality the probe measured is what is kept.
    assert data["read1_sha256"] == hashlib.sha256(b"example spine read").hexdigest()
    assert "log_id is NOT present in a code:0 body" in data["note"]


def test_ac8_rendering_does_not_depend_on_the_hosts_clock_or_locale(monkeypatch):
    """A date cell is a pure function of `(value, formatter, time_zone)`; the assembly seam
    must not reintroduce the host."""
    fields = [spec("When", 5, "DateTime", property={"date_formatter": "yyyy/MM/dd HH:mm"})]
    records = [_Record("r", {"When": 1754179200000})]
    monkeypatch.setenv("TZ", "America/Denver")
    a = base_table.assemble_table(table_id="t", name="T", fields=fields, records=records,
                                  context=RenderContext(time_zone="Asia/Singapore"))
    monkeypatch.setenv("TZ", "Europe/London")
    b = base_table.assemble_table(table_id="t", name="T", fields=fields, records=records,
                                  context=RenderContext(time_zone="Asia/Singapore"))
    assert a.rows[0].cells == b.rows[0].cells


# --------------------------------------------------------------------------- #
# AC10 — Stage renders ABSENT-WITH-REASON at the assembly seam too (R14).      #
# --------------------------------------------------------------------------- #

def test_ac10_the_stage_column_exists_and_EVERY_ROW_carries_the_marker():
    """AC10: a type-24 column is in `fields`, so it **is** a column of the rendered table,
    and every row's cell in it carries LD-246's absent-with-reason marker — never blank. A
    blank would silently assert "no data" about data that demonstrably exists (R14)."""
    doc = assembled_scratch_base()
    table = doc.tables[0]
    stage = [i for i, f in enumerate(table.fields) if f.pair == (24, "Stage")]
    assert stage, "the golden Base lost its type-24 column; AC10 needs one"
    index = stage[0]
    assert table.fields[index].field_name == "stage?"
    assert table.rows, "AC10 needs rows to assert 'every row'"
    for row in table.rows:
        assert row.cells[index] == STAGE_OPAQUE_MARKER

    rendered = base_table.render_table(table)
    body = [ln for ln in rendered.splitlines() if ln.startswith("| ")][2:]
    assert body and all(STAGE_OPAQUE_MARKER in ln for ln in body)


def test_ac10_the_marker_survives_the_gfm_escape_unmangled():
    """The marker contains an em dash and brackets but no pipe, so the escape must leave it
    byte-identical — pinned, because a future marker edit that adds a pipe would silently
    change the rendered bytes."""
    assert base_table.escape_cell(STAGE_OPAQUE_MARKER) == STAGE_OPAQUE_MARKER


# --------------------------------------------------------------------------- #
# The SDK-typed field seam: what the pinned SDK's property model drops.        #
# --------------------------------------------------------------------------- #

def _every_captured_field():
    def walk(node):
        if isinstance(node, dict):
            if {"field_name", "ui_type", "type"} <= set(node):
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    for path in sorted(_CAPTURES.glob("*.json")):
        yield from walk(json.loads(path.read_text(encoding="utf-8")))


def test_the_sdk_typed_field_is_projected_back_to_the_DICT_the_renderers_read():
    """LD-247's client returns SDK-typed `AppTableField`s; LD-246's renderers read a plain
    `property` **dict**. This seam is where the two meet, and it is the SDK's own serializer
    that bridges them — not a hand-rolled attribute walk."""
    raw = next(f for f in _every_captured_field()
               if isinstance(f.get("property"), dict) and f["ui_type"] == "Rating")
    field = unmarshal(raw, AppTableField)
    projected = base_table.field_spec(field)
    assert isinstance(projected, FieldSpec)
    assert isinstance(projected.property, dict)
    assert projected.property["rating"]["symbol"] == raw["property"]["rating"]["symbol"]
    assert projected.pair == (raw["type"], raw["ui_type"])
    assert projected.field_name == raw["field_name"]


def _property_key_paths(value, prefix=""):
    """Every **dotted** key path in a property, list indices collapsed and ``None`` values
    skipped (an undeclared key on a typed object reads identically to a ``None`` one).

    Dotted, because the pin below used to compare **top-level keys only** — and a key dropped
    one level down was therefore invisible to it. ``filter_info.conditions`` is exactly that
    case: the Lookup specimen's whole filter-condition subtree does not survive the typed
    seam, and for as long as the comparison stayed flat the guard said nothing about it.
    """
    paths = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if child is None:
                continue
            path = f"{prefix}{key}"
            paths.add(path)
            paths |= _property_key_paths(child, path + ".")
    elif isinstance(value, list):
        for item in value:
            paths |= _property_key_paths(item, prefix)
    return paths


def _maximal(paths):
    """Drop every path whose parent is already in the set — a subtree that is gone is
    reported once, at the top of the subtree, rather than once per leaf inside it."""
    return {p for p in paths
            if not any(p.startswith(other + ".") for other in paths if other != p)}


def test_the_SDK_PROPERTY_MODEL_IS_LOSSY_and_the_dropped_set_is_PINNED():
    """**A limitation found by LD-248** (BASE.md register row 12), **DEEPENED to nested keys
    by LD-270**. The pinned SDK's `AppTableFieldProperty` only carries the keys it declares,
    so a property key Lark returns and the model does not know is **silently dropped** on the
    way through.

    Measured over every field in every committed capture, the dropped set is exactly six
    paths — the five top-level keys this pin always knew, **plus `filter_info.conditions`,
    which the pin could not see while it compared top-level keys only**. Not one of them is
    read by any renderer or by the free schema readings beside them, which is why L1 is
    unaffected. The set is pinned rather than described: a *read-relevant* key joining it
    would be a silent wrong render, and this test is what makes that a red suite instead."""
    dropped = set()
    checked = 0
    for raw in _every_captured_field():
        if not isinstance(raw.get("property"), dict):
            continue
        checked += 1
        projected = base_table.field_spec(unmarshal(raw, AppTableField)).property or {}
        dropped |= (_property_key_paths(raw["property"])
                    - _property_key_paths(projected))

    assert checked >= 70, f"only {checked} captured properties were checked"
    assert _maximal(dropped) == {
        "back_field_id", "input_type", "formula", "roll_up", "target_field",
        "filter_info.conditions",
    }
    shadowed = [(path, key)
                for path in _maximal(dropped)
                for key in base_table.RENDERER_PROPERTY_KEYS
                if key == path or key.startswith(path + ".") or path.startswith(key + ".")]
    assert not shadowed, (
        f"a property key the read surface READS is now silently dropped by the SDK model "
        f"{shadowed} — the render is wrong, not merely narrow. The comparison is by PATH, so "
        "a dropped parent shadows a guarded child: losing `filter_info` wholesale would take "
        "`filter_info.target_table` with it and must redden here.")


def test_reverting_the_row_12_pin_to_TOP_LEVEL_ONLY_goes_BLIND():
    """The deliberate-defect check for the deepening. Comparing top-level keys only — which
    is what this guard did before — sees five drops and misses `filter_info.conditions`
    entirely, so a reverted pin would pass while saying nothing about a whole dropped
    subtree. That gap is the reason the pin was deepened, and this is what re-proves it."""
    def top_level_only(value):
        return {k for k, v in value.items() if v is not None} if isinstance(value, dict) else set()

    flat, deep = set(), set()
    for raw in _every_captured_field():
        if not isinstance(raw.get("property"), dict):
            continue
        projected = base_table.field_spec(unmarshal(raw, AppTableField)).property or {}
        flat |= top_level_only(raw["property"]) - top_level_only(projected)
        deep |= _property_key_paths(raw["property"]) - _property_key_paths(projected)

    assert "filter_info.conditions" not in flat, (
        "the reverted (top-level-only) comparison is no longer blind — the deepening's whole "
        "justification has changed and the row must change with it")
    assert "filter_info.conditions" in _maximal(deep)
    assert _maximal(deep) - flat == {"filter_info.conditions"}, (
        "the deepening bought exactly one previously-invisible drop; it now buys a different "
        "set, which the register row has to say")


def test_the_renderer_property_keys_are_the_ones_the_read_surface_ACTUALLY_READS():
    """The pin above is only as good as its key list, so the list is checked against the
    reading source rather than maintained by hope.

    Two modules, not one: the cell registry reads a property to render, and the free
    schema readings beside it (link targets, computed-column provenance) read a property to
    disclose. Both are ways for a silent drop to become a wrong answer, so both count.
    """
    sources = "".join(
        (_REPO / "src" / "larkdocio" / "base" / name).read_text(encoding="utf-8")
        for name in ("cells.py", "computed.py", "referential.py"))
    for key in base_table.RENDERER_PROPERTY_KEYS:
        leaf = key.rsplit(".", 1)[-1]
        assert f'"{leaf}"' in sources, (
            f"{key} is not read anywhere in the Base read surface")


def test_a_field_whose_property_is_NULL_projects_to_None_not_an_empty_dict():
    """`property: null` is the shape the auto fields (1001 / 1002) read back, and LD-246's
    date renderer keys its documented-default formatter off exactly that."""
    raw = next(f for f in _every_captured_field() if f.get("property") is None)
    assert base_table.field_spec(unmarshal(raw, AppTableField)).property is None


def test_a_raw_capture_dict_can_be_projected_too_so_a_fixture_needs_no_sdk_round_trip():
    """The seam accepts either shape — the SDK object the client returns, or the raw dict a
    capture holds — because a test fixture that had to go through the SDK to be readable
    would make the captures harder to use than they are."""
    raw = next(f for f in _every_captured_field()
               if isinstance(f.get("property"), dict) and f["ui_type"] == "Rating")
    assert base_table.field_spec(raw) == base_table.field_spec(unmarshal(raw, AppTableField))


# --------------------------------------------------------------------------- #
# Cross-cutting: PII, and the marker bytes at the seam.                        #
# --------------------------------------------------------------------------- #

def test_no_person_payload_leaks_through_the_assembly_seam():
    """D1 is a property of the render, and the assembly seam is a new place to lose it."""
    fields = [spec("Owner", 11, "User")]
    person = {"id": "ou_deadbeef", "name": "Ada", "en_name": "Ada L",
              "email": "ada@example.com", "avatar_url": "https://cdn/x.png"}
    records = [_Record("r", {"Owner": [person]})]
    rendered = base_table.render_table(base_table.assemble_table(
        table_id="t", name="T", fields=fields, records=records))
    assert "Ada" in rendered
    for leak in ("ou_deadbeef", "ada@example.com", "cdn", "avatar"):
        assert leak not in rendered


def test_the_assembly_seam_renders_cells_THROUGH_THE_REGISTRY_and_does_not_re_render():
    """The seam arranges rendered cells; it does not own a second opinion about a cell.
    Asserted by comparing every cell of the golden Base against `render_cell` directly."""
    app, tables, per_table = scratch_base()
    context = RenderContext(time_zone=app.time_zone)
    for t in tables:
        fields, records = per_table[t.table_id]
        assembled = base_table.assemble_table(
            table_id=t.table_id, name=t.name, fields=fields, records=records,
            context=context)
        for row, record in zip(assembled.rows, records):
            expected = base_cells.render_row(record.fields, assembled.fields,
                                             context=context)
            assert list(row.cells) == expected
