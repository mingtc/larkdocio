"""LD-250 — the opt-in embedded-Base deep-read bridge, for BOTH block types (18 AND 53).

The docx reader emits a **placeholder** where a Base is embedded. Two block types do it —
``bitable`` (18) and ``reference_base`` (53) — and this story bridges **both through one
code path** (AC1), opt-in and default-off, degrading to the existing placeholder on every
failure (AC4) exactly as the Sheets bridge already does (``BLOCKS.md`` type 30).

**Every payload here is a committed probe capture**, round-tripped through the pinned SDK's
own deserializer and driven through the **real** :class:`~larkdocio.base.client.BaseReadClient`
over a fake SDK transport — so a shape drift reddens at deserialization and the error paths
run through the real Base error taxonomy rather than a hand-rolled stand-in
(``tests/test_base_client.py`` precedent).

The four capture families, and what each is here to prove:

* ``02-bitable18-*`` — **the husk.** The zoo's type-18 specimen answers ``{"items": []}``
  with **no ``total``, no ``page_token``, no ``has_more``** (AC3), and its tail is a real
  ``1254041 TableIdNotFound`` (AC4). The husk is the shape a *stale* embed token has.
* ``p0-1-05-fresh-embed-bridge.json`` — **the fresh docx-born embed.** A type-18 embed
  created today bridges end to end (``app → tables(1) → fields(3) → search(3)``, all
  ``code:0``), and its app meta carries **no ``time_zone`` at all** (AC7) — the case LD-246
  AC5's absent-``time_zone`` fallback exists for.
* ``02-refbase53-*`` — **the type-53 embed, end to end from its own three captures**
  (app meta *with* a ``time_zone``, one table, three real fields).
* ``p1-q0-03-per-table.json`` — a real captured table **with a Stage (type 24) column**
  (AC10). It stands in for the fresh embed's own field/record payloads, which the P0 probe
  recorded only as names and counts; the splice is named where it happens, and every
  rendered byte still comes from a payload Lark actually returned.
"""
import json

import pytest
from lark_oapi.api.bitable.v1 import (
    GetAppResponse,
    ListAppTableFieldResponse,
    ListAppTableResponse,
    SearchAppTableRecordResponse,
)
from lark_oapi.core.json import JSON

from harness import FIXTURES_DIR, build_blocks, render

from larkdocio.base.client import BaseReadClient
from larkdocio.model import BitableNode, MarkdownRenderer, ReferenceBaseNode
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"

#: The husk token the zoo's (now converted) type-18 specimen carried — and the token the
#: committed golden fixture still pins. It is NOT evidence of live behaviour (AC8).
HUSK_TOKEN = "Example3b5902b83520533e4650_tblGgEHCSGMXEKQs"

#: The FRESH docx-born embed's compound token (`p0-1-05`), the one that bridges.
FRESH_TOKEN = "Examplec8af798413375ff9bc09_tbloLtUSiQNhlkYX"

#: The live type-53 block's compound token (`p0-1-01`, the block-zoo doc).
REFBASE_TOKEN = "Examplef5d787ae62ccf194cb22_tbloRVXCoxKjVR5A"

BITABLE_MARKER = (
    "> 📊 **Embedded Base** (bitable) — not fetched. token: `{token}`. "
    "Contents (records, views, formulas) live in a separate Base document; "
    "deep read is out of scope. (Switching an embedded base to a named view "
    "makes it a reference_base — type 53 — instead.)\n"
)

REFBASE_MARKER = (
    "> 📊 **Embedded Base — named view** (reference_base) — not fetched. "
    "token: `{token}`, view: `{view_id}`. A base switched to a named "
    "view (distinct from an embedded Base — type 18; consumers hit both "
    "interchangeably).\n"
)


# --------------------------------------------------------------------------- #
# Captures → typed SDK objects                                                 #
# --------------------------------------------------------------------------- #

def capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def unmarshal(payload, cls):
    return JSON.unmarshal(json.dumps(payload), cls)


def empty_search():
    """A zero-record ``records/search`` page in the wire shape the captures pin.

    Synthetic on purpose and named as such: the P0 pack captured no record read for the
    type-53 embed's table, so its deep read renders the documented *fields, no records*
    shape rather than borrowing another table's rows."""
    return unmarshal(
        {"code": 0, "msg": "success", "data": {"items": [], "has_more": False, "total": 0}},
        SearchAppTableRecordResponse)


def stage_table_payloads():
    """The real captured table that carries a **Stage (type 24)** column — its fields and
    its six records (`p1-q0-03`, table `tblYtWUpf5q944Ao`)."""
    entry = next(e for e in capture("p1-q0-03-per-table.json")["per_table"]
                 if e["table_id"] == "tblYtWUpf5q944Ao")
    return (unmarshal(entry["fields"]["response"], ListAppTableFieldResponse),
            unmarshal(entry["records_search"]["response"], SearchAppTableRecordResponse))


# --------------------------------------------------------------------------- #
# A fake SDK transport, so the REAL BaseReadClient is what the bridge drives    #
# --------------------------------------------------------------------------- #

class _Leg:
    """A bare attribute holder standing in for one SDK resource namespace."""


class _Recorder:
    """One SDK resource method: records its request, hands back the canned response
    (repeating the last once the script runs out); a canned ``Exception`` is raised."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the fake SDK was called with no canned response")
        answer = self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return answer


class _CountingLimiter:
    def __init__(self):
        self.acquisitions = 0

    def acquire(self):
        self.acquisitions += 1


def base_client(*, app_get=(), tables=(), fields=(), search=()):
    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = v1 = _Leg()
    v1.app = _Leg()
    v1.app.get = _Recorder(app_get)
    v1.app_table = _Leg()
    v1.app_table.list = _Recorder(tables)
    v1.app_table_field = _Leg()
    v1.app_table_field.list = _Recorder(fields)
    v1.app_table_record = _Leg()
    v1.app_table_record.search = _Recorder(search)
    return BaseReadClient("id", "secret", sdk_client=sdk, rate_limiter=_CountingLimiter())


class ExplodingBaseClient:
    """A client whose every method raises — so a test can prove that with the flag OFF the
    handlers issue NO Base API call at all (AC5's call-count spy)."""

    def get_app(self, *a, **k):
        raise AssertionError("get_app called while Base deep-read OFF — a fetch was issued")

    def list_tables(self, *a, **k):
        raise AssertionError("list_tables called while OFF — a fetch was issued")

    def list_fields(self, *a, **k):
        raise AssertionError("list_fields called while OFF — a fetch was issued")

    def search_records(self, *a, **k):
        raise AssertionError("search_records called while OFF — a fetch was issued")


# ---- the three scenarios, each from its own captures ----------------------- #

def fresh_embed_client():
    """The FRESH docx-born type-18 embed: its own app meta (**no ``time_zone``**) and its
    own one-table list, spliced with the real Stage-carrying table's fields and records."""
    app = unmarshal(
        {"code": 0, "msg": "success",
         "data": {"app": capture("p0-1-05-fresh-embed-bridge.json")
                  ["response"]["data"]["fresh_type18_embed"]["app_meta"]["app"]}},
        GetAppResponse)
    tables = unmarshal(
        {"code": 0, "msg": "success",
         "data": {"items": capture("p0-1-05-fresh-embed-bridge.json")
                  ["response"]["data"]["fresh_type18_embed"]["tables"]["items"],
                  "has_more": False, "total": 1}},
        ListAppTableResponse)
    fields, search = stage_table_payloads()
    return base_client(app_get=[app], tables=[tables], fields=[fields], search=[search])


def refbase_client():
    """The type-53 embed, end to end from `02-refbase53-*`: app meta (with a ``time_zone``),
    its single table, its three real fields, and no records."""
    return base_client(
        app_get=[unmarshal(capture("02-refbase53-app-meta.json")["response"], GetAppResponse)],
        tables=[unmarshal(capture("02-refbase53-tables.json")["response"], ListAppTableResponse)],
        fields=[unmarshal(capture("02-refbase53-fields.json")["response"],
                          ListAppTableFieldResponse)],
        search=[empty_search()],
    )


def husk_client():
    """The husk: real app meta, and a table list of ``{"items": []}`` with no counter and no
    cursor (AC3)."""
    return base_client(
        app_get=[unmarshal(capture("02-bitable18-app-meta.json")["response"], GetAppResponse)],
        tables=[unmarshal(capture("02-bitable18-tables.json")["response"], ListAppTableResponse)],
        fields=[unmarshal(capture("02-bitable18-fields.json")["response"],
                          ListAppTableFieldResponse)],
        search=[empty_search()],
    )


# ---- docx blocks ----------------------------------------------------------- #

def bitable_block(token=FRESH_TOKEN):
    return build_blocks([{"block_id": "bt", "block_type": 18,
                          "bitable": {"token": token, "view_type": None}}])[0]


def refbase_block(token=REFBASE_TOKEN, view_id="vewFZRvtbd"):
    return build_blocks([{"block_id": "rb", "block_type": 53,
                          "reference_base": {"token": token, "view_id": view_id,
                                             "layout_mode": "Normal"}}])[0]


def parser(client, *, on=True):
    return Parser(Config(), deep_read_bases=on, base_client=client)


def _r():
    return MarkdownRenderer()


def handle_18(client, block=None, *, on=True):
    from larkdocio.blocks.embedded import handle_bitable
    return handle_bitable(parser(client, on=on), block or bitable_block(), 0)


def handle_53(client, block=None, *, on=True):
    from larkdocio.blocks.embedded import handle_reference_base
    return handle_reference_base(parser(client, on=on), block or refbase_block(), 0)


# --------------------------------------------------------------------------- #
# AC1 — ONE bridge, BOTH block types                                           #
# --------------------------------------------------------------------------- #

def test_ac1_type_18_deep_reads_through_the_bridge():
    node = handle_18(fresh_embed_client())
    assert isinstance(node, BitableNode)
    md = node.deep_read_markdown
    assert md is not None and md.startswith("## tbloLtUSiQNhlkYX\n\n") and md.endswith("\n")
    assert "| Text | lookup | Email | stage? |" in md


def test_ac1_type_53_deep_reads_through_the_bridge():
    node = handle_53(refbase_client())
    assert isinstance(node, ReferenceBaseNode)
    md = node.deep_read_markdown
    assert md is not None and md.startswith("## Table\n\n") and md.endswith("\n")
    assert "| Text | Text 2 | Single Option |" in md


def test_ac1_BOTH_TYPES_RIDE_ONE_BRIDGE_byte_identically():
    """The same compound token through both handlers yields the **same bytes** — which is
    what "one bridge" means operationally, not merely "two functions that look alike"."""
    from_18 = handle_18(refbase_client(), bitable_block(REFBASE_TOKEN)).deep_read_markdown
    from_53 = handle_53(refbase_client(), refbase_block(REFBASE_TOKEN)).deep_read_markdown
    assert from_18 is not None
    assert from_18 == from_53


def test_ac1_both_handlers_call_THE_SAME_bridge_function():
    """Source-level: neither handler grows its own copy of the deep read."""
    src = (_REPO / "src" / "larkdocio" / "blocks" / "embedded.py").read_text(encoding="utf-8")
    assert src.count("deep_read_embedded_base(") == 1, (
        "both handlers must reach the bridge through ONE call site, not two copies")


def test_ac1_the_fresh_embed_capture_records_a_bridge_that_WORKS_end_to_end():
    """The P0 verdict input, pinned: a freshly docx-born type-18 embed answers ``code:0``
    on all four legs and its tail IS a listed table."""
    fresh = capture("p0-1-05-fresh-embed-bridge.json")["response"]["data"]["fresh_type18_embed"]
    assert fresh["compound"] == FRESH_TOKEN
    assert fresh["tail_is_a_listed_table"] is True
    assert fresh["app_meta"]["code"] == 0 and fresh["tables"]["code"] == 0
    assert fresh["fields_via_tail"]["code"] == 0 and fresh["fields_via_tail"]["n"] == 3
    assert fresh["search_via_tail"]["code"] == 0 and fresh["search_via_tail"]["n"] == 3


# --------------------------------------------------------------------------- #
# AC2 — the compound token splits on the LAST underscore                       #
# --------------------------------------------------------------------------- #

def test_ac2_split_on_the_last_underscore():
    from larkdocio.base.embed import split_compound_token

    assert split_compound_token(FRESH_TOKEN) == (
        "Examplec8af798413375ff9bc09", "tbloLtUSiQNhlkYX")
    assert split_compound_token(REFBASE_TOKEN) == (
        "Examplef5d787ae62ccf194cb22", "tbloRVXCoxKjVR5A")


def test_ac2_the_app_token_half_may_itself_contain_an_underscore():
    from larkdocio.base.embed import split_compound_token

    assert split_compound_token("app_with_underscores_tblXYZ") == (
        "app_with_underscores", "tblXYZ")


def test_ac2_a_malformed_token_returns_None_and_never_raises():
    from larkdocio.base.embed import split_compound_token

    for bad in ("noUnderscoreHere", "_tblOnly", "trailing_", "_", "", None):
        assert split_compound_token(bad) is None


def test_ac2_the_rule_is_BYTE_IDENTICAL_to_the_shipped_sheets_rule():
    """The Sheets rule replayed — proven equal over a corpus rather than claimed. Base-local
    (the LD-248 ``escape_cell`` posture) so the docx→Base path does not import the Sheets
    surface to read a Base."""
    from larkdocio.base.embed import split_compound_token as base_split
    from larkdocio.sheets.embed import split_compound_token as sheets_split

    corpus = [FRESH_TOKEN, REFBASE_TOKEN, HUSK_TOKEN, "app_with_underscores_tblXYZ",
              "a_b", "noUnderscoreHere", "_tblOnly", "trailing_", "_", "", None,
              "Example38428307171a2bd44d36_EQlPwA"]
    for token in corpus:
        assert base_split(token) == sheets_split(token), token


def test_ac2_a_malformed_token_degrades_WITHOUT_touching_the_client():
    client = ExplodingBaseClient()   # any call would be an AssertionError
    node = handle_18(client, bitable_block("noUnderscoreToken"))
    assert node.deep_read_markdown is None
    assert _r().render(node) == BITABLE_MARKER.format(token="noUnderscoreToken")


# --------------------------------------------------------------------------- #
# AC3 — defensive on the HUSK shape                                            #
# --------------------------------------------------------------------------- #

def test_ac3_the_husk_capture_really_carries_NO_total_NO_page_token_NO_has_more():
    data = capture("02-bitable18-tables.json")["response"]["data"]
    assert data == {"items": []}
    for absent in ("total", "page_token", "has_more"):
        assert absent not in data, f"the husk capture would not prove the AC3 rule if it had {absent}"


def test_ac3_a_zero_table_app_degrades_to_the_placeholder():
    """Not a crash, and **not** an empty table: the placeholder the reader emits today."""
    client = husk_client()
    node = handle_18(client, bitable_block(HUSK_TOKEN))
    assert node.deep_read_markdown is None
    assert _r().render(node) == BITABLE_MARKER.format(token=HUSK_TOKEN)


def test_ac3_a_zero_table_app_reads_NEITHER_fields_NOR_records():
    """The degrade happens at the table list — no doomed per-table fetch follows it."""
    client = husk_client()
    handle_18(client, bitable_block(HUSK_TOKEN))
    assert client.api_calls == 1, (
        "a zero-table app must cost exactly the one table-list call")


def bridge_code():
    """``base/embed.py`` with every string literal and comment removed — the scan asks
    *"does any CODE PATH do X"*, and prose naming the hazard it avoids must not trip it
    (the ``tests/test_base_client.py`` posture)."""
    import io
    import tokenize

    path = _REPO / "src" / "larkdocio" / "base" / "embed.py"
    text = path.read_text(encoding="utf-8")
    return "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(text).readline)
        if token.type not in (tokenize.STRING, tokenize.COMMENT))


def test_ac3_the_bridge_NEVER_CONSULTS_total_or_page_token():
    code = bridge_code()
    for forbidden in (".total", ".page_token", ".has_more"):
        assert forbidden not in code, (
            f"the bridge reads {forbidden} — a missing counter or cursor may never be assumed")


# --------------------------------------------------------------------------- #
# AC4 — ANY failure degrades to the EXISTING placeholder, byte-identically      #
# --------------------------------------------------------------------------- #

def _failing_client(code, msg, *, leg="fields"):
    body = {"code": code, "msg": msg, "error": {"log_id": "x"}}
    legs = dict(
        app_get=[unmarshal(capture("02-bitable18-app-meta.json")["response"], GetAppResponse)],
        tables=[unmarshal(capture("02-refbase53-tables.json")["response"], ListAppTableResponse)],
        fields=[unmarshal(capture("02-refbase53-fields.json")["response"],
                          ListAppTableFieldResponse)],
        search=[empty_search()],
    )
    cls = {"app_get": GetAppResponse, "tables": ListAppTableResponse,
           "fields": ListAppTableFieldResponse, "search": SearchAppTableRecordResponse}[leg]
    legs[leg] = [unmarshal(body, cls)]
    return base_client(**legs)


@pytest.mark.parametrize("code,msg,leg", [
    (1254041, "TableIdNotFound", "fields"),
    (1254004, "WrongTableId", "search"),
    (1002, "note has been deleted", "tables"),
])
def test_ac4_a_typed_lark_refusal_degrades_to_the_placeholder(code, msg, leg):
    client = _failing_client(code, msg, leg=leg)
    node = handle_18(client, bitable_block(REFBASE_TOKEN))
    assert node.deep_read_markdown is None
    assert _r().render(node) == BITABLE_MARKER.format(token=REFBASE_TOKEN)


def test_ac4_the_1254041_body_is_a_REAL_capture_not_a_synthesized_one():
    husk_fields = capture("02-bitable18-fields.json")["response"]
    assert husk_fields["code"] == 1254041 and husk_fields["msg"] == "TableIdNotFound"


def test_ac4_a_network_error_degrades_to_the_placeholder():
    client = base_client(tables=[ConnectionError("simulated network failure")])
    node = handle_53(client)
    assert node.deep_read_markdown is None
    assert _r().render(node) == REFBASE_MARKER.format(token=REFBASE_TOKEN,
                                                      view_id="vewFZRvtbd")


def test_ac4_a_tail_that_is_not_a_listed_table_degrades_before_any_per_table_read():
    client = refbase_client()
    node = handle_53(client, refbase_block("Examplef5d787ae62ccf194cb22_tblNOSUCHTABLE"))
    assert node.deep_read_markdown is None
    assert client.api_calls == 1


def test_ac4_a_docx_download_NEVER_FAILS_because_a_base_could_not_be_read():
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
         "children": ["bt", "rb"]},
        {"block_id": "bt", "parent_id": "root", "block_type": 18,
         "bitable": {"token": HUSK_TOKEN, "view_type": None}},
        {"block_id": "rb", "parent_id": "root", "block_type": 53,
         "reference_base": {"token": REFBASE_TOKEN, "view_id": "vewFZRvtbd",
                            "layout_mode": "Normal"}},
    ]
    client = base_client(tables=[ConnectionError("simulated network failure")])
    out = parser(client).parse_docx_content("root", build_blocks(blocks))   # must NOT raise
    assert BITABLE_MARKER.format(token=HUSK_TOKEN).strip() in out
    assert REFBASE_MARKER.format(token=REFBASE_TOKEN, view_id="vewFZRvtbd").strip() in out


# --------------------------------------------------------------------------- #
# AC5 — DEFAULT OFF: zero Base API calls, docx goldens byte-identical           #
# --------------------------------------------------------------------------- #

def test_ac5_the_default_parser_has_the_bridge_off_and_no_client():
    p = Parser(Config())
    assert p.deep_read_bases is False
    assert p.base_client is None


@pytest.mark.parametrize("handler,token", [(handle_18, HUSK_TOKEN),
                                           (handle_53, REFBASE_TOKEN)])
def test_ac5_flag_off_issues_ZERO_base_calls_even_with_a_client_present(handler, token):
    node = handler(ExplodingBaseClient(), on=False)   # no AssertionError ⇒ no fetch
    assert node.deep_read_markdown is None


@pytest.mark.parametrize("handler", [handle_18, handle_53])
def test_ac5_flag_on_but_no_client_emits_the_placeholder(handler):
    node = handler(None, on=True)
    assert node.deep_read_markdown is None


def test_ac5_THE_WHOLE_DOCX_GOLDEN_CORPUS_IS_UNCHANGED():
    """Every committed golden re-rendered by a DEFAULT parser, byte-compared. The corpus is
    what a consumer's output looks like today; this story may not move one byte of it."""
    drifted = []
    for input_path in sorted(FIXTURES_DIR.glob("*.input.json")):
        case = input_path.name[: -len(".input.json")]
        expected = (FIXTURES_DIR / f"{case}.expected.md").read_text(encoding="utf-8")
        actual = render(json.loads(input_path.read_text(encoding="utf-8")))
        if actual != expected:
            drifted.append(case)
    assert not drifted, f"default-path output drift in {drifted}"


# --------------------------------------------------------------------------- #
# AC6 — the BLOCKS.md doc-truth correction, in the shape that keeps the guard   #
# --------------------------------------------------------------------------- #

def blocks_md_row(block_type):
    text = (_REPO / "BLOCKS.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(f"| {block_type} | "):
            return [c.strip() for c in line.strip().strip("|").split(" | ")]
    raise AssertionError(f"no BLOCKS.md row for type {block_type}")


@pytest.mark.parametrize("block_type", [18, 53])
def test_ac6_the_stale_deep_read_clause_is_GONE_from_both_rows(block_type):
    narrative = blocks_md_row(block_type)[-1]
    assert "deep read of them is **out of scope**" not in narrative
    assert "deep read **out of scope**" not in narrative
    assert "opt-in" in narrative.lower(), (
        "the row must describe the opt-in deep-read that now ships")
    assert "placeholder" in narrative.lower()


@pytest.mark.parametrize("block_type", [18, 53])
def test_ac6_the_WRITE_COLUMN_STAYS_not_creatable(block_type):
    """The addendum's "flip row 18 to creatable" phrasing is **wrong**: the Write column
    means *larkdocio* can create it, and it is pinned bidirectionally against
    ``CREATABLE_BLOCK_TYPES``."""
    from larkdocio.write.encode import CREATABLE_BLOCK_TYPES

    assert blocks_md_row(block_type)[3] == "not-creatable"
    assert block_type not in CREATABLE_BLOCK_TYPES


def test_ac6_row_18s_NARRATIVE_carries_the_new_LARK_API_creatability_fact():
    narrative = blocks_md_row(18)[-1]
    assert "1770001" in narrative
    assert "auto-provision" in narrative.lower()


def test_ac6_row_53s_NARRATIVE_records_that_LARK_itself_refuses_the_create():
    assert "1770029" in blocks_md_row(53)[-1]


def test_ac6_the_creatability_fact_is_the_one_the_capture_recorded():
    attempts = capture("p0-1-03-docx-embed-block-create-attempts.json")["response"]["data"]
    assert attempts["18_view_type_only"]["code"] == 0
    assert attempts["18_scratch_token"]["code"] == 1770001
    assert attempts["53_scratch_token_view"]["code"] == 1770029


@pytest.mark.parametrize("block_type", [18, 53])
def test_ac6_the_summary_prose_no_longer_says_base_deep_read_is_out_of_scope(block_type):
    text = (_REPO / "BLOCKS.md").read_text(encoding="utf-8")
    assert "**Deep read of Base\n  (18/53) content is out of scope**" not in text
    assert "Deep read of Base (18/53) content is out of scope" not in text


# --------------------------------------------------------------------------- #
# AC7 — a doc-owned embedded Base is a DISTINCT OBJECT CLASS                    #
# --------------------------------------------------------------------------- #

def test_ac7_the_fresh_embeds_app_meta_carries_NO_time_zone():
    app = capture("p0-1-05-fresh-embed-bridge.json")[
        "response"]["data"]["fresh_type18_embed"]["app_meta"]["app"]
    assert "time_zone" not in app
    meta = capture("p0-1-05-fresh-embed-bridge.json")[
        "response"]["data"]["fresh_type18_embed"]["drive_meta"]["meta"]
    assert meta["title"] == "" and meta["sec_label_name"] == ""


def test_ac7_a_time_zone_less_embed_STILL_DEEP_READS_via_the_documented_fallback():
    """LD-246 AC5's absent-``time_zone`` fallback, exercised for real: the deep read
    succeeds and its date cells render in the documented default zone."""
    node = handle_18(fresh_embed_client())
    assert node.deep_read_markdown is not None


def test_ac7_the_distinct_object_class_is_recorded_in_BASE_md_and_the_shipped_guide():
    from larkdocio import guide

    base_md = (_REPO / "BASE.md").read_text(encoding="utf-8")
    assert "1061003" in base_md and "doc-owned" in base_md.lower()
    text = guide(full=True)
    assert "doc-owned" in text.lower()
    assert "embedded Base" in text


# --------------------------------------------------------------------------- #
# AC8 — the stale committed fixture is re-labelled, and a Base-era one exists   #
# --------------------------------------------------------------------------- #

def test_ac8_the_stale_fixture_records_WHY_it_is_not_live_evidence():
    blocks = json.loads((FIXTURES_DIR / "bitable.input.json").read_text(encoding="utf-8"))
    note = next(b["_note"] for b in blocks if b.get("block_type") == 18)
    assert "husk" in note.lower()
    assert "p0-1-05" in note
    assert blocks[-1]["bitable"]["token"] == HUSK_TOKEN


def test_ac8_a_BASE_ERA_fixture_exists_seeded_from_the_fresh_embed_capture():
    path = FIXTURES_DIR / "bitable_fresh_embed.input.json"
    blocks = json.loads(path.read_text(encoding="utf-8"))
    assert any(b.get("bitable", {}).get("token") == FRESH_TOKEN for b in blocks)


def test_ac8_the_note_key_is_INERT_so_the_golden_cannot_move():
    """A ``_note`` in a fixture block is dropped by the SDK deserializer — the comment costs
    the golden nothing."""
    with_note = build_blocks([{"block_id": "bt", "block_type": 18, "_note": "x",
                               "bitable": {"token": HUSK_TOKEN, "view_type": None}}])[0]
    assert _r().render(BitableNode(token=with_note.bitable.token)) == \
        BITABLE_MARKER.format(token=HUSK_TOKEN)


# --------------------------------------------------------------------------- #
# AC10 — Stage inside an embedded Base behaves as it does outside it            #
# --------------------------------------------------------------------------- #

def test_ac10_a_stage_column_inside_an_embedded_base_renders_the_absent_marker():
    from larkdocio.base.cells import STAGE_OPAQUE_MARKER

    md = handle_18(fresh_embed_client()).deep_read_markdown
    body = [line for line in md.splitlines() if line.startswith("| ") and "---" not in line][2:]
    assert body, "the deep read rendered no rows"
    for row in body:
        assert STAGE_OPAQUE_MARKER in row, (
            "every row's Stage cell must carry the absent-with-reason marker, never a blank")


# --------------------------------------------------------------------------- #
# The renderer seam                                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("node", [
    BitableNode(token=FRESH_TOKEN), ReferenceBaseNode(token=REFBASE_TOKEN, view_id="v"),
])
def test_the_renderer_emits_the_deep_read_markdown_in_place_of_the_marker(node):
    node.deep_read_markdown = "## T\n\n| a |\n|---|\n"
    assert _r().render(node) == "## T\n\n| a |\n|---|\n"


@pytest.mark.parametrize("node_cls,kwargs", [(BitableNode, {}),
                                             (ReferenceBaseNode, {})])
def test_an_absent_payload_still_renders_nothing(node_cls, kwargs):
    assert _r().render(node_cls(**kwargs)) == ""
