"""LD-179 — the round-3 minors, batched: four truth fixes with nothing shared but their size.

Each of the four is one-to-few lines of *honesty* in the library's own words, and each was
found by a consumer hitting it:

* **F13** — a resolved comment reports ``is_solved=True`` and a populated ``solver_user_id``
  while ``solved_time`` reads ``None``. The round-2 harvest proves the key is **never sent**
  by any comment endpoint, so the model says so rather than leaving a consumer to wonder
  whether it lost a timestamp. Driven here off the **real captured resolved comments**
  (docx + sheet), never a synthetic one.
* **F15** — the library's most-called callables had no docstrings. Asserted **list-driven**
  so the set cannot regress one method at a time, plus the two facts the report asked
  ``get_docx_content`` for by name: its ``(Document, [Block])`` return and that the
  document's ``revision_id`` is what arms ``STALE_DOCUMENT``.
* **F18** — ``api_base()`` returns a domain root while its docstring claimed an OpenAPI base
  URL, and the consumer's first raw call 404'd on the missing ``/open-apis``. The call-site
  census below **is** the verification the issue demanded before choosing which half to fix:
  every caller composes ``/open-apis`` itself, so the return value must not move and the
  docstring is the wrong half. The census is executable, so a new call site reddens the
  suite and forces the same re-confirmation.
* **F20** — the ``not-found`` refusal told a consumer to "re-read the document and copy the
  quote verbatim", which **cannot succeed** for the commonest cause: the quote was copied out
  of the Markdown projection, whose line markers (``- ``, ``# ``, ``> ``, ``1. ``,
  ``- [ ] ``) are not in any block's own text. The refusal family is the library's
  most-praised surface, so the clause is **appended** and the shipped wording is pinned
  **byte-for-byte** here — both that it survives as the hedged detail's prefix and that a
  quote which is simply absent still gets it unchanged.
"""
import ast
import json
import pathlib
import re

import pytest
from harness import build_blocks

import comments_payloads
from consumer_text import dialect_hits

from larkdocio.comments.models import Comment
from larkdocio.common.transport import TENANT_TOKEN_PATH, api_base
from larkdocio.read.client import Client
from larkdocio.read.config import Config, read_config_from_file
from larkdocio.read.download import handle_download_command
from larkdocio.read.parser import Parser
from larkdocio.write.model import Anchor, EditRequest, RefusalReason
from larkdocio.write.resolve import (
    NOT_FOUND_REMEDY,
    PROJECTION_QUOTE_HEDGE_TAIL,
    ResolvedTarget,
    block_plain_text,
    projection_quote_hedge,
    resolve,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"
HARVESTS = REPO_ROOT / "tests" / "captures" / "comments-probe-round2-captures"


# =========================================================================== #
# AC1 — F13: is_solved=True with solved_time=None is DOCUMENTED, not dropped   #
# =========================================================================== #

def _harvest(name):
    return json.loads((HARVESTS / name).read_text(encoding="utf-8"))


def _real_resolved_captures():
    """``(label, comment_body)`` for every REAL captured comment reporting ``is_solved``.

    Both surfaces, and both shapes that carry a resolved comment at all: the ``list`` item the
    harvest recorded verbatim and the two ``batch_query`` items (``get``-one answers
    ``1069307 not exist`` for an anchored comment, so it contributes none). Nothing synthetic:
    if the capture moves, these tests fail rather than quietly testing a fixture's opinion.
    """
    out = []
    for surface, filename in (("docx", "10-harvest-docx.json"), ("sheet", "11-harvest-sheet.json")):
        example = _harvest(filename)["examples"]["Resolved"]
        out.append((f"{surface}-list", example["list_item"]))
        for shape, body in example["shapes"].items():
            if not shape.startswith("batch_query"):
                continue
            items = ((body.get("response") or {}).get("data") or {}).get("items") or []
            for item in items:
                if item.get("is_solved"):
                    out.append((f"{surface}-{shape}", item))
    assert len(out) >= 5, f"the harvest stopped carrying the resolved captures: {out!r}"
    return out


@pytest.mark.parametrize("label,body", _real_resolved_captures(),
                         ids=[label for label, _ in _real_resolved_captures()])
def test_ac1_no_real_capture_of_a_resolved_comment_carries_solved_time(label, body):
    # The API fact the docstring has to state: genuinely resolved (is_solved true, a real
    # solver open_id) and yet `solved_time` is ABSENT from the body's key set entirely.
    assert body["is_solved"] is True
    assert body["solver_user_id"].startswith("ou_")
    assert "solved_time" not in body, f"{label} carries solved_time — the API fact moved"


def test_ac1_a_resolved_comment_reports_who_but_never_when():
    body = _harvest("10-harvest-docx.json")["examples"]["Resolved"]["list_item"]
    comment = Comment.from_wire(body)
    assert comment.is_solved is True
    assert comment.solver_user_id == "ou_exampleowner00000000000000000001"
    assert comment.solved_time is None


def test_ac1_the_field_survives_the_json_round_trip_as_none():
    body = _harvest("10-harvest-docx.json")["examples"]["Resolved"]["list_item"]
    comment = Comment.from_wire(body)
    assert comment.to_dict()["solved_time"] is None
    assert Comment.from_dict(comment.to_dict()).solved_time is None


def test_ac1_the_model_documents_the_combination_rather_than_leaving_it_a_surprise():
    doc = Comment.__doc__
    assert doc, "the comment model lost its class docstring"
    text = " ".join(doc.split())
    assert "solved_time" in text
    assert "is_solved" in text and "solver_user_id" in text
    assert "never" in text.lower(), "the docstring has to say the key is never sent"


def _payload_dicts():
    """Every dict-shaped payload the offline comment fixture library exposes."""
    return [(name, value) for name, value in vars(comments_payloads).items()
            if not name.startswith("_") and isinstance(value, dict)]


@pytest.mark.parametrize("name,payload", _payload_dicts(),
                         ids=[name for name, _ in _payload_dicts()])
def test_ac1_no_offline_fixture_claims_a_solved_time_the_api_never_sends(name, payload):
    # A fixture carrying a solved_time would prove the OPPOSITE of the captured reality (and
    # of the new docstring), which is worse than no fixture at all.
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            if "solved_time" in node:
                found.append(path)
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, name)
    assert not found, f"{found} claims a solved_time; no endpoint has ever sent one"


# =========================================================================== #
# AC2 — F15: the seven most-called callables carry a usable docstring          #
# =========================================================================== #

SEVEN_CALLABLES = (
    ("Client.get_docx_content", Client.get_docx_content),
    ("Client.get_wiki_node_info", Client.get_wiki_node_info),
    ("Client.download_image", Client.download_image),
    ("Client.download_board_image", Client.download_board_image),
    ("Parser.parse_docx_content", Parser.parse_docx_content),
    ("read.download.handle_download_command", handle_download_command),
    ("read.config.read_config_from_file", read_config_from_file),
)


@pytest.mark.parametrize("label,callable_", SEVEN_CALLABLES,
                         ids=[label for label, _ in SEVEN_CALLABLES])
def test_ac2_every_most_called_callable_has_a_usable_docstring(label, callable_):
    # List-driven on purpose: the set cannot regress one method at a time.
    doc = (callable_.__doc__ or "").strip()
    assert doc, f"{label} has no docstring"
    assert len(doc.split()) >= 6, f"{label}'s docstring says nothing usable: {doc!r}"


def test_ac2_get_docx_content_names_its_return_shape():
    doc = " ".join((Client.get_docx_content.__doc__ or "").split())
    assert "(Document, [Block])" in doc, doc


def test_ac2_get_docx_content_names_the_guard_its_revision_arms():
    doc = " ".join((Client.get_docx_content.__doc__ or "").split())
    assert "revision_id" in doc and "STALE_DOCUMENT" in doc, doc


# =========================================================================== #
# AC3 — F18: api_base() verified at its call sites FIRST, then its docstring   #
# =========================================================================== #

#: The call-site census, pinned by module. This IS the verification the issue demanded
#: before choosing which half of the mismatch to fix: change the return value and all five
#: double the segment. A NEW call site reddens this and forces the same re-confirmation.
API_BASE_CALL_SITES = {
    "common/transport.py": 1,   # api_base(domain) + TENANT_TOKEN_PATH
    "write/client.py": 1,       # self._base = api_base(domain)
    "sheets/client.py": 1,
    "sheets/write_client.py": 1,
    "sheets/export_reader.py": 1,
    # The preflight's probe client is a fifth raw client on the same skeleton, and it obeys the
    # same contract this census exists to protect: api_base() returns the base WITHOUT the
    # /open-apis segment, and every path this module appends begins with it. Re-confirmed by
    # reading its probe table, which is where those paths live.
    "preflight.py": 1,
    # The Drive enumeration client is the sixth raw client on the same skeleton, and the
    # contract was re-confirmed for it the way this census demands: api_base() returns the
    # domain ROOT, and every Drive path is declared in `drive/ops.py` — all three of them
    # beginning with /open-apis, checked below.
    "drive/client.py": 1,
    # LD-409's named-version write client is the SEVENTH raw client on the same skeleton, and
    # the contract was re-confirmed for it the same way: api_base() returns the domain ROOT,
    # and the one path it sends is composed from the op registry's own
    # /open-apis/drive/v1/files/:file_token/versions constant.
    "drive/versions_write.py": 1,
    # LD-432's access client is the EIGHTH raw client on the same skeleton, and the contract
    # was re-confirmed for it the same way: api_base() returns the domain ROOT, and every path
    # it sends is composed from the op registry's own
    # /open-apis/drive/v1/permissions/:file_token/members and
    # /open-apis/drive/v2/permissions/:file_token/public constants (plus the metas/batch_query
    # constant already in that registry), all of which begin with /open-apis.
    "drive/access_write.py": 1,
    # LD-467's folder-creation client is the NINTH raw client on the same skeleton, and the
    # contract was re-confirmed for it the same way: api_base() returns the domain ROOT, and
    # the one path it sends is composed from the op registry's own
    # /open-apis/drive/v1/files/create_folder constant, which begins with /open-apis.
    "drive/folders_write.py": 1,
}

#: The raw clients that keep the base on ``self._base`` and append their own paths.
RAW_CLIENT_MODULES = (
    "write/client.py",
    "sheets/client.py",
    "sheets/write_client.py",
    "sheets/export_reader.py",
    "preflight.py",
    # The Drive client keeps the base on self._base like the others, but declares its paths in
    # its op registry rather than at the call site — so the registry is what carries the path
    # roots this check reads.
    "drive/ops.py",
)


def _api_base_calls():
    """``{relative module path: number of api_base(...) calls}`` across the package."""
    census = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) == "api_base"
                 or getattr(node.func, "attr", None) == "api_base")
        )
        if calls:
            census[str(path.relative_to(SRC))] = calls
    return census


#: A request path's ROOT is recognisable by its version segment (``/v1/``, ``/v3``): that is
#: the piece ``api_base()``'s return value is concatenated with. A bare suffix fragment
#: (``"/children"``, ``"/values/"``, ``"/sheets/query"``) carries no version and is appended to
#: a root that already did, so it is not a call site's beginning and is not scanned.
_PATH_ROOT = re.compile(r"^/.*?/v\d(?:/|$)")


def _path_roots(module):
    """Every request-path ROOT literal in ``module``, including f-string literal prefixes.

    Fails the caller (empty list) rather than passing quietly if the module stops declaring
    paths in a readable shape — which is the point: an unresolvable path shape should force a
    human to look, not slip through a scan that found nothing.
    """
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and _PATH_ROOT.match(node.value)
    ]


def test_ac3_the_call_site_census_is_exactly_what_was_verified():
    assert _api_base_calls() == API_BASE_CALL_SITES


def test_ac3_api_base_returns_a_domain_root_not_an_endpoint_prefix():
    assert api_base() == "https://open.larksuite.com"
    assert api_base("feishu.cn") == "https://open.feishu.cn"
    assert "/open-apis" not in api_base("feishu.cn")


def test_ac3_the_token_call_site_composes_open_apis_itself():
    assert TENANT_TOKEN_PATH.startswith("/open-apis/")


@pytest.mark.parametrize("module", RAW_CLIENT_MODULES)
def test_ac3_every_raw_client_composes_open_apis_itself(module):
    roots = _path_roots(module)
    assert roots, f"{module} declares no readable request path — the shape moved, go look"
    for root in roots:
        assert root.startswith("/open-apis"), (
            f"{module} carries the request path {root!r}, which does not compose /open-apis "
            f"itself — api_base()'s contract (it returns a domain ROOT) no longer holds"
        )


def test_ac3_the_docstring_says_what_it_actually_returns():
    doc = " ".join((api_base.__doc__ or "").split())
    assert "https://open.larksuite.com" in doc, doc
    assert "/open-apis" in doc, "the docstring must show the composition callers do"
    assert "root" in doc.lower(), "the docstring must say it is a domain ROOT"


# =========================================================================== #
# AC4 / AC5 — F20: the not-found refusal covers its commonest cause            #
# =========================================================================== #

#: The shipped ``not-found`` detail, spelled out here rather than imported, so this file is
#: the byte-for-byte record of the praised wording. Nothing may rewrite the DIAGNOSIS half;
#: the projection clause is appended after it.
#:
#: **Amended by LD-455 — the reason stands, the remedy is superseded.** The diagnosis ("no
#: block's own text contains …, matched verbatim (substring) against each block's OWN text")
#: is unchanged byte for byte and is still what this file pins. What was struck is the
#: trailing REMEDY, "re-read the document and copy the quote verbatim": dogfood round 4
#: measured it failing 5/5 across three tiers on a soft-return paragraph, where re-reading
#: and re-copying reproduces the refusal exactly — the advice names the action the consumer
#: has just taken. It is replaced by an action that is a different action
#: (:data:`~larkdocio.write.resolve.NOT_FOUND_REMEDY`), imported rather than re-spelled so
#: the remedy has one home.
def _shipped_detail(quote):
    return (
        f"no block's own text contains the anchor quote {quote!r} — the quote is "
        f"matched verbatim (substring) against each block's OWN text, never its "
        f"children's; {NOT_FOUND_REMEDY}"
    )


#: A small document holding one block of every marker-bearing kind the projection emits.
PROJECTION_DOC = [
    {"block_id": "root", "parent_id": "", "block_type": 1,
     "page": {"elements": [{"text_run": {"content": "Round-trip doc"}}]},
     "children": ["h", "b", "o", "t", "q"]},
    {"block_id": "h", "parent_id": "root", "block_type": 3,
     "heading1": {"elements": [{"text_run": {"content": "Findings"}}]}},
    {"block_id": "b", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [{"text_run": {"content": "Ship the reader fix"}}]}},
    {"block_id": "o", "parent_id": "root", "block_type": 13,
     "ordered": {"elements": [{"text_run": {"content": "Measure the latency"}}]}},
    {"block_id": "t", "parent_id": "root", "block_type": 17,
     "todo": {"style": {"done": False},
              "elements": [{"text_run": {"content": "Draft the release note"}}]}},
    {"block_id": "q", "parent_id": "root", "block_type": 15,
     "quote": {"elements": [{"text_run": {"content": "Nobody reads the manual"}}]}},
]

#: ``(block_id, the projection LINE, the block's OWN text)`` — the five marker dialects.
PROJECTION_LINES = (
    ("h", "# Findings", "Findings"),
    ("b", "- Ship the reader fix", "Ship the reader fix"),
    ("o", "1. Measure the latency", "Measure the latency"),
    ("t", "- [ ] Draft the release note", "Draft the release note"),
    ("q", "> Nobody reads the manual", "Nobody reads the manual"),
)


def _projection():
    return Parser(Config()).parse_docx_content("root", build_blocks(PROJECTION_DOC))


def _tree():
    return Parser(Config()).parse_docx_tree("root", build_blocks(PROJECTION_DOC))


def _detail_for(quote, tree=None):
    result = resolve(EditRequest(anchor=Anchor(quote=quote), replacement="X"),
                     tree if tree is not None else _tree())
    assert not isinstance(result, ResolvedTarget), f"{quote!r} unexpectedly resolved"
    assert result.reason is RefusalReason.NOT_FOUND
    return result.detail


@pytest.mark.parametrize("block_id,line,own_text", PROJECTION_LINES,
                         ids=[bid for bid, _, _ in PROJECTION_LINES])
def test_ac4_the_projection_line_really_is_what_the_reader_emits(block_id, line, own_text):
    # The premise of the whole fix, proven rather than assumed: the reader emits the marker,
    # and the marker is NOT part of the block's own text — so the quote cannot match.
    assert line in _projection().splitlines()
    node = [n for n in _blocks_of(_tree()) if n.block_id == block_id][0]
    assert block_plain_text(node) == own_text
    assert line != own_text


def _blocks_of(root):
    out = []

    def walk(node):
        out.append(node)
        for child in getattr(node, "children", ()) or ():
            walk(child)

    walk(root)
    return out


@pytest.mark.parametrize("block_id,line,own_text", PROJECTION_LINES,
                         ids=[bid for bid, _, _ in PROJECTION_LINES])
def test_ac4_a_projection_quote_gains_the_new_clause(block_id, line, own_text):
    detail = _detail_for(line)
    # EXTENDED, never rewritten: the praised wording is the prefix, byte-for-byte.
    assert detail.startswith(_shipped_detail(line))
    clause = detail[len(_shipped_detail(line)):]
    assert clause, "a projection quote gained no clause at all"
    assert "projection" in clause


@pytest.mark.parametrize("block_id,line,own_text", PROJECTION_LINES,
                         ids=[bid for bid, _, _ in PROJECTION_LINES])
def test_ac4_the_clause_names_the_block_the_consumer_actually_meant(block_id, line, own_text):
    detail = _detail_for(line)
    assert repr(block_id) in detail
    assert "AnchorById" in detail
    assert own_text in detail, "the clause should show the text that DOES match"


@pytest.mark.parametrize("block_id,line,own_text", PROJECTION_LINES,
                         ids=[bid for bid, _, _ in PROJECTION_LINES])
def test_ac4_the_clause_points_at_the_guides_own_symptoms_table(block_id, line, own_text):
    assert "Symptoms you picked the wrong level" in _detail_for(line)


def test_ac4_the_cited_symptoms_table_exists_in_the_shipped_guide():
    guide = (SRC / "GUIDE.md").read_text(encoding="utf-8")
    assert "### Symptoms you picked the wrong level" in guide
    # …and it really does diagnose THIS case, which is why the clause cites it.
    assert "You quoted the **projection**, not the block." in guide


def test_ac4_a_nested_items_indent_and_marker_are_both_dropped():
    # The projection indents a nested item with a tab BEFORE its marker.
    assert _detail_for("\t- Ship the reader fix").startswith(
        _shipped_detail("\t- Ship the reader fix"))
    assert "AnchorById" in _detail_for("\t- Ship the reader fix")


#: Two bullets carrying the SAME text — the tree the clause must not pick a winner from.
AMBIGUOUS_DOC = [
    {"block_id": "root", "parent_id": "", "block_type": 1,
     "page": {"elements": [{"text_run": {"content": "Doc"}}]},
     "children": ["b1", "b2"]},
    {"block_id": "b1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [{"text_run": {"content": "Ship it"}}]}},
    {"block_id": "b2", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [{"text_run": {"content": "Ship it"}}]}},
]


def _ambiguous_tree():
    return Parser(Config()).parse_docx_tree("root", build_blocks(AMBIGUOUS_DOC))


def test_ac4_a_marker_quote_matching_several_blocks_says_so_without_picking_one():
    detail = _detail_for("- Ship it", _ambiguous_tree())
    assert detail.startswith(_shipped_detail("- Ship it"))
    assert "2 blocks" in detail
    # It must NOT pretend one of the two is the answer.
    assert "b1" not in detail and "b2" not in detail


# --- AC5 — MUST NOT BITE ---------------------------------------------------- #

def test_ac5_a_genuinely_absent_quote_keeps_the_shipped_wording_byte_for_byte():
    quote = "a sentence that is nowhere in this document"
    assert _detail_for(quote) == _shipped_detail(quote)


ABSENT_MARKER_QUOTES = (
    "- an item that does not exist",
    "# a heading that does not exist",
    "1. a step that does not exist",
    "> a quote that does not exist",
    "- [ ] a task that does not exist",
    "\t- a nested item that does not exist",
)


@pytest.mark.parametrize("quote", ABSENT_MARKER_QUOTES)
def test_ac5_a_marker_alone_does_not_fire_the_clause(quote):
    # The clause is EVIDENCE-gated: a marker with nothing behind it is the ordinary
    # not-found, and the ordinary wording is correct for it.
    assert _detail_for(quote) == _shipped_detail(quote)


def test_ac5_a_marker_with_nothing_after_it_is_the_ordinary_refusal():
    for quote in ("- ", "# ", "> ", "1. "):
        assert _detail_for(quote) == _shipped_detail(quote)


def test_ac5_a_tree_accurate_quote_still_resolves():
    result = resolve(EditRequest(anchor=Anchor(quote="Ship the reader fix"), replacement="X"),
                     _tree())
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "b"


def test_ac5_the_helper_is_empty_for_a_quote_carrying_no_marker():
    assert projection_quote_hedge("nothing marker-ish here", _tree()) == ""


def test_ac5_the_helper_is_empty_when_the_stripped_quote_still_matches_nothing():
    assert projection_quote_hedge("- absent", _tree()) == ""


def test_ac5_the_empty_quote_refusal_is_untouched():
    result = resolve(EditRequest(anchor=Anchor(quote=""), replacement="X"), _tree())
    assert result.reason is RefusalReason.NOT_FOUND
    assert result.detail == (
        "the anchor carries an empty quote — an empty quote is a substring of "
        "every block, so it locates nothing; supply the verbatim text you want "
        "to anchor to"
    )


def test_ac5_the_breadcrumb_refusal_is_untouched():
    # Breadcrumb narrowing only runs on an AMBIGUOUS quote, so this needs the two-block doc.
    result = resolve(
        EditRequest(anchor=Anchor(quote="Ship it", breadcrumb=("Nowhere",)),
                    replacement="X"),
        _ambiguous_tree())
    assert result.reason is RefusalReason.NOT_FOUND
    assert "breadcrumb" in result.detail
    assert "projection" not in result.detail


# =========================================================================== #
# AC6 — gates: the new strings are dialect-free; the projection is unchanged    #
# =========================================================================== #

def _strings_this_issue_added():
    strings = {
        "api_base.__doc__": api_base.__doc__,
        "Comment.__doc__": Comment.__doc__,
        "projection-hedge": projection_quote_hedge("- Ship the reader fix", _tree()),
        "projection-hedge-constant": PROJECTION_QUOTE_HEDGE_TAIL,
    }
    for label, callable_ in SEVEN_CALLABLES:
        strings[label] = callable_.__doc__
    return sorted(strings.items())


@pytest.mark.parametrize("label,text", _strings_this_issue_added(),
                         ids=[label for label, _ in _strings_this_issue_added()])
def test_ac6_every_string_this_issue_added_is_dialect_free(label, text):
    assert dialect_hits(text) == [], f"{label} carries internal dialect"


def test_ac6_the_projection_is_deterministic_and_marker_bearing():
    # Reader output is untouched by this issue (no reader code changed) — pinned here too,
    # because the whole fix rests on what the projection emits.
    first = _projection()
    assert first == _projection()
    for _bid, line, _own in PROJECTION_LINES:
        assert line in first.splitlines()


def test_ac6_the_marker_is_read_at_the_line_start_only():
    # A marker in the MIDDLE of a quote is not a projection marker; stripping it would
    # invent matches the post-fix retry would still refuse.
    assert projection_quote_hedge("Ship the - reader fix", _tree()) == ""
