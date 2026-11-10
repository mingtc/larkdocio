"""LD-657 — the block-loss signal stops being prose.

``read/parser.py`` has always emitted the only account of a block type this library does not
model, as a WARNING. That is a log line, so the only way a programmatic caller could learn
*"this document used types you do not render"* was to attach a handler and parse a sentence —
which our one known consumer does, which is why that sentence is frozen by commitment today.

This module holds the structured answer that replaces the parse:

* **AC1** — ``DownloadResult["unknown_block_types"]``: the DISTINCT unmodelled types with a
  count per type, and deliberately **no block ids** (the reason is pinned below, because a
  design judgement that is only in a docstring is one refactor from being reversed by accident).
* **AC2** — present on **every** successful download, ``[]`` when nothing was lost, so a machine
  can tell *"nothing unmodelled"* from *"key missing"* — the discipline ``dump_path`` follows.
* **AC3** — the report and the warning come from **one** place. Held two ways: driven end to end
  (a document with an unknown type yields both, naming the same types; a document with none
  yields neither), and STRUCTURALLY, by an AST walk proving the sole emitter of the protected
  warning sits in the same function that appends to the report. Two sources of truth here is the
  defect the issue exists to remove.
* **AC4** — the two shapes are pinned SEPARATELY: an unknown **container** preserves its subtree
  at its own depth, a leaf unknown emits nothing, and the report is honest about which happened.
* **AC5** — the frozen warning is **byte-unchanged**. Pinned by emission, as a whole-message
  equality for both shapes: the AST arms in
  ``tests/test_download_route_contract_pins.py`` prove there is exactly one emitter in the right
  module at the right level, and this proves what that emitter actually says.
"""

import ast
import inspect
import logging
import pathlib
import re
from types import SimpleNamespace

import pytest

from harness import build_blocks
from larkdocio.read import download as dl
from larkdocio.read.config import Config
from larkdocio.read.download import DownloadResult
from larkdocio.read.parser import Parser

#: The four keys of one report entry. A set equality, so a key that appears reddens too — the
#: report is a shape a consumer reads, and a key that arrives unannounced is as much a change as
#: one that leaves.
ENTRY_KEYS = {"block_type", "count", "containers", "children"}


def _page(children):
    return {"block_id": "root", "block_type": 1,
            "page": {"elements": [{"text_run": {"content": "T"}}]},
            "children": children}


def _parse(block_dicts, parser=None):
    """Parse to Markdown through the REAL parser and hand back (parser, markdown)."""
    parser = parser or Parser(Config())
    blocks = build_blocks(block_dicts)
    markdown = parser.parse_docx_content("root", blocks)
    return parser, markdown


# --------------------------------------------------------------------------- #
# AC1 — the distinct types, with a count per type.                             #
# --------------------------------------------------------------------------- #

def test_the_report_names_each_DISTINCT_unmodelled_type_once_with_its_count():
    """Two occurrences of one unmodelled type and one of another: two entries, not three."""
    parser, _ = _parse([
        _page(["a", "b", "c"]),
        {"block_id": "a", "block_type": 9997, "parent_id": "root", "undefined": {}},
        {"block_id": "b", "block_type": 9997, "parent_id": "root", "undefined": {}},
        {"block_id": "c", "block_type": 9998, "parent_id": "root", "undefined": {}},
    ])
    report = parser.unknown_block_types
    assert [e["block_type"] for e in report] == [9997, 9998]
    assert [e["count"] for e in report] == [2, 1]


def test_every_entry_answers_exactly_the_four_keys():
    parser, _ = _parse([
        _page(["a"]),
        {"block_id": "a", "block_type": 9997, "parent_id": "root", "undefined": {}},
    ])
    assert [set(e) for e in parser.unknown_block_types] == [ENTRY_KEYS]


def test_the_report_carries_NO_block_ids_and_that_is_the_recorded_decision():
    """**The one design judgement of LD-657, held mechanically.**

    The warning names the ``block_id`` and the ``parent_id``; the report deliberately does not.
    The consumer needed only which block types a document used that the library does not model,
    and nothing beyond that — and ids would make the answer grow
    with the document rather than with its vocabulary, turning a per-run summary into a per-block
    log by another name. Per-block detail already has a home: the warning (for a human reading
    one document) and the ``--dump`` sidecar (for a machine that wants the raw payload).

    Pinned because a docstring cannot stop a later change from "helpfully" adding them: the
    values here are ints and nothing but ints, so no id can ride along unnoticed.
    """
    parser, _ = _parse([
        _page(["only-block-id-in-this-document"]),
        {"block_id": "only-block-id-in-this-document", "block_type": 9997,
         "parent_id": "root", "undefined": {}},
    ])
    entries = parser.unknown_block_types
    assert entries, "non-vacuity: the document must actually have produced an entry"
    for entry in entries:
        assert all(isinstance(v, int) for v in entry.values()), entry
        assert "only-block-id-in-this-document" not in repr(entry), entry


def test_the_report_is_JSON_native_and_a_COPY_of_the_accumulator():
    """It rides on a ``dict``-bodied result a ledger may ``json.dumps`` straight out — and a
    caller mutating what it was handed must not be able to corrupt the parser's own state."""
    import json

    parser, _ = _parse([
        _page(["a"]),
        {"block_id": "a", "block_type": 9997, "parent_id": "root", "undefined": {}},
    ])
    report = parser.unknown_block_types
    json.dumps(report)
    report[0]["count"] = 99
    report.append({"block_type": 1})
    assert parser.unknown_block_types == [
        {"block_type": 9997, "count": 1, "containers": 0, "children": 0}]


def test_two_sequential_parses_on_one_parser_do_not_merge_their_reports():
    """The accumulator is per-PARSE, like every other one (LD-080)."""
    parser, _ = _parse([
        _page(["a"]),
        {"block_id": "a", "block_type": 9997, "parent_id": "root", "undefined": {}},
    ])
    assert [e["block_type"] for e in parser.unknown_block_types] == [9997]
    _parse([
        _page(["b"]),
        {"block_id": "b", "block_type": 9998, "parent_id": "root", "undefined": {}},
    ], parser=parser)
    assert [e["block_type"] for e in parser.unknown_block_types] == [9998]


# --------------------------------------------------------------------------- #
# AC4 — the container case and the leaf case, pinned SEPARATELY.               #
# --------------------------------------------------------------------------- #

def test_an_unknown_CONTAINER_reports_its_preserved_children():
    """Decision e: an unknown container's subtree is surfaced at the block's own depth. The
    report says so — ``containers`` counts the occurrences that carried children and
    ``children`` counts the child blocks those occurrences preserved."""
    parser, markdown = _parse([
        _page(["unk"]),
        {"block_id": "unk", "block_type": 9997, "parent_id": "root",
         "children": ["kid", "kid2"]},
        {"block_id": "kid", "block_type": 2, "parent_id": "unk",
         "text": {"elements": [{"text_run": {"content": "surfaced body"}}]}},
        {"block_id": "kid2", "block_type": 2, "parent_id": "unk",
         "text": {"elements": [{"text_run": {"content": "also surfaced"}}]}},
    ])
    assert "surfaced body" in markdown and "also surfaced" in markdown, markdown
    assert parser.unknown_block_types == [
        {"block_type": 9997, "count": 1, "containers": 1, "children": 2}]


def test_a_LEAF_unknown_reports_zero_preserved_children():
    """A leaf unknown emits nothing at all, and the report must not imply otherwise."""
    parser, markdown = _parse([
        _page(["leaf"]),
        {"block_id": "leaf", "block_type": 999, "parent_id": "root", "undefined": {}},
    ])
    assert markdown == "# T\n\n\n", repr(markdown)
    assert parser.unknown_block_types == [
        {"block_type": 999, "count": 1, "containers": 0, "children": 0}]


def test_one_type_seen_BOTH_ways_reports_both_without_conflating_them():
    """The mixed case is where a single ``children`` total would lie: the leaf occurrence
    emitted nothing and the container occurrence preserved one child. ``count`` is 2,
    ``containers`` is 1, and the leaf count is the difference — stated, not guessed."""
    parser, _ = _parse([
        _page(["leaf", "cont"]),
        {"block_id": "leaf", "block_type": 9997, "parent_id": "root", "undefined": {}},
        {"block_id": "cont", "block_type": 9997, "parent_id": "root", "children": ["kid"]},
        {"block_id": "kid", "block_type": 2, "parent_id": "cont",
         "text": {"elements": [{"text_run": {"content": "x"}}]}},
    ])
    assert parser.unknown_block_types == [
        {"block_type": 9997, "count": 2, "containers": 1, "children": 1}]


def test_a_document_with_no_unmodelled_type_reports_an_EMPTY_list():
    parser, _ = _parse([
        _page(["d"]),
        {"block_id": "d", "block_type": 22, "parent_id": "root", "divider": {}},
    ])
    assert parser.unknown_block_types == []


# --------------------------------------------------------------------------- #
# AC3 — ONE decision. The warning and the report cannot disagree.              #
# --------------------------------------------------------------------------- #

def test_the_warning_and_the_report_name_the_same_types(caplog):
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        parser, _ = _parse([
            _page(["a", "b"]),
            {"block_id": "a", "block_type": 9997, "parent_id": "root", "undefined": {}},
            {"block_id": "b", "block_type": 9998, "parent_id": "root", "children": ["kid"]},
            {"block_id": "kid", "block_type": 2, "parent_id": "b",
             "text": {"elements": [{"text_run": {"content": "x"}}]}},
        ])
    warned = sorted(
        int(r.getMessage().split("Unknown block type ", 1)[1].split(" ", 1)[0])
        for r in caplog.records if r.getMessage().startswith("Unknown block type ")
    )
    assert warned == sorted(e["block_type"] for e in parser.unknown_block_types) == [9997, 9998]
    # and the occurrence counts agree with the number of warnings
    assert sum(e["count"] for e in parser.unknown_block_types) == len(warned)


def test_a_document_with_none_yields_NEITHER_a_warning_nor_a_report(caplog):
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        parser, _ = _parse([
            _page(["d"]),
            {"block_id": "d", "block_type": 22, "parent_id": "root", "divider": {}},
        ])
    assert not [r for r in caplog.records if "Unknown block type" in r.getMessage()]
    assert parser.unknown_block_types == []


def _unknown_branch_source():
    """The source of the ONE function in the shipped package that emits the protected warning.

    Found by an AST walk over log-call arguments rather than by name, so renaming the helper
    cannot make this guard go quiet — the same instrument
    ``tests/test_download_route_contract_pins.py`` uses, for the same reason.
    """
    src = pathlib.Path(inspect.getsourcefile(Parser))
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    owners = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "warning" and inner.args):
                head = inner.args[0]
                first = head.values[0] if isinstance(head, ast.JoinedStr) and head.values else head
                if (isinstance(first, ast.Constant) and isinstance(first.value, str)
                        and first.value.startswith("Unknown block type ")):
                    owners.append(node)
    assert len(owners) == 1, [getattr(n, "name", None) for n in owners]
    return owners[0]


def test_the_warning_and_the_report_are_written_by_the_SAME_function():
    """AC3, structurally: two sources of truth cannot exist if there is only one writer.

    The function that emits the warning must also be the function that records the report —
    otherwise a future branch can warn without reporting (a consumer's migration silently loses
    a type) or report without warning (the frozen line stops arriving).
    """
    owner = _unknown_branch_source()
    writes = [
        n for n in ast.walk(owner)
        if isinstance(n, ast.Attribute) and n.attr == "_unknown_blocks"
    ]
    assert writes, (
        f"{owner.name} emits the protected warning but never touches the report accumulator — "
        f"the log line and the structured signal have become two decisions")


def test_the_accumulator_is_written_NOWHERE_ELSE_in_the_parser():
    """The other half of the same claim: one writer, not one writer plus a second scan."""
    owner = _unknown_branch_source()
    src = pathlib.Path(inspect.getsourcefile(Parser))
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    stores = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "_unknown_blocks":
            stores.append(node.lineno)
    inside = [n for n in ast.walk(owner)
              if isinstance(n, ast.Attribute) and n.attr == "_unknown_blocks"]
    seed_and_read = [
        ln for ln in stores if ln not in {n.lineno for n in inside}
    ]
    # The only touches outside the emitting function are the per-parse reseed and the read-only
    # projection property — both of which are named here so a third one is a decision.
    owners = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            isinstance(n, ast.Attribute) and n.attr == "_unknown_blocks"
            for n in ast.walk(node)
        ):
            owners.append(node.name)
    assert sorted(owners) == sorted(
        ["_reset_accumulators", "_note_unknown_block", "unknown_block_types"]), owners
    assert seed_and_read, "non-vacuity: the reseed and the projection must exist"


# --------------------------------------------------------------------------- #
# AC5 — the frozen warning, byte for byte, driven.                             #
# --------------------------------------------------------------------------- #

FROZEN_CONTAINER_WARNING = (
    "Unknown block type 9997 (block_id=unk, parent_id=root, children=2) — content may be "
    "missing from output."
)
FROZEN_LEAF_WARNING = (
    "Unknown block type 999 (block_id=leaf, parent_id=root, children=0) — content may be "
    "missing from output."
)


def test_the_frozen_warning_is_byte_identical_for_an_unknown_CONTAINER(caplog):
    """The consumer parses this sentence today. LD-657 ships the structured signal that EARNS
    the right to change it — later, in a separately named release. Not now."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        _parse([
            _page(["unk"]),
            {"block_id": "unk", "block_type": 9997, "parent_id": "root",
             "children": ["kid", "kid2"]},
            {"block_id": "kid", "block_type": 2, "parent_id": "unk",
             "text": {"elements": [{"text_run": {"content": "a"}}]}},
            {"block_id": "kid2", "block_type": 2, "parent_id": "unk",
             "text": {"elements": [{"text_run": {"content": "b"}}]}},
        ])
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert messages == [FROZEN_CONTAINER_WARNING], messages


def test_the_frozen_warning_is_byte_identical_for_a_LEAF_unknown(caplog):
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        _parse([
            _page(["leaf"]),
            {"block_id": "leaf", "block_type": 999, "parent_id": "root", "undefined": {}},
        ])
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert messages == [FROZEN_LEAF_WARNING], messages


# --------------------------------------------------------------------------- #
# AC2 — on the RESULT, stated rather than absent.                              #
# --------------------------------------------------------------------------- #

def _download(monkeypatch, out_dir, block_dicts, **kwargs):
    from test_download_pipeline import DOCX_URL, _StubClient, _patch_env

    _patch_env(monkeypatch)
    docx = SimpleNamespace(title="Doc Title", document_id="root")
    blocks = build_blocks(block_dicts)
    monkeypatch.setattr(dl, "Client", lambda *a, **k: _StubClient(docx=docx, blocks=blocks))
    return dl.handle_download_command(DOCX_URL, str(out_dir), "", False, "", **kwargs)


def test_the_key_is_on_EVERY_successful_download_and_is_empty_when_nothing_was_lost(
    monkeypatch, tmp_path
):
    result = _download(monkeypatch, tmp_path, [
        _page(["d"]),
        {"block_id": "d", "block_type": 22, "parent_id": "root", "divider": {}},
    ])
    assert "unknown_block_types" in result, sorted(result)
    assert result["unknown_block_types"] == []
    assert result.unknown_block_types == []


def test_the_key_carries_the_report_when_a_type_WAS_lost(monkeypatch, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        result = _download(monkeypatch, tmp_path, [
            _page(["unk", "leaf"]),
            {"block_id": "unk", "block_type": 9997, "parent_id": "root", "children": ["kid"]},
            {"block_id": "kid", "block_type": 2, "parent_id": "unk",
             "text": {"elements": [{"text_run": {"content": "surfaced"}}]}},
            {"block_id": "leaf", "block_type": 999, "parent_id": "root", "undefined": {}},
        ])
    assert result["unknown_block_types"] == [
        {"block_type": 9997, "count": 1, "containers": 1, "children": 1},
        {"block_type": 999, "count": 1, "containers": 0, "children": 0},
    ]
    # the same run still emits the frozen warning for each occurrence — AC3 end to end
    warned = [r.getMessage() for r in caplog.records
              if r.getMessage().startswith("Unknown block type ")]
    assert len(warned) == 2, warned
    # and the file really was written: this is a successful download, not a refusal
    assert result.output_path.endswith(".md")
    assert pathlib.Path(result.output_path).exists()


def test_a_parser_with_no_report_at_all_still_yields_the_key(monkeypatch, tmp_path):
    """A stub/older parser handed in at the seam has no accumulator. The key is stated anyway —
    ``[]`` is an answer, a missing key is not."""
    from test_download_pipeline import DOCX_URL, _StubClient, _StubParser, _patch_env

    _patch_env(monkeypatch)
    monkeypatch.setattr(dl, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(dl, "Parser", lambda config: _StubParser(markdown="# plain\n"))
    result = dl.handle_download_command(DOCX_URL, str(tmp_path), "", False, "")
    assert result["unknown_block_types"] == []


def test_DownloadResult_exposes_the_key_as_a_property_that_is_a_VIEW_onto_the_body():
    assert isinstance(getattr(DownloadResult, "unknown_block_types", None), property)
    body = [{"block_type": 9997, "count": 1, "containers": 0, "children": 0}]
    result = DownloadResult({"unknown_block_types": body})
    assert result.unknown_block_types is body
    assert DownloadResult({}).unknown_block_types == []


@pytest.mark.parametrize("key", ["output_path", "output_dir", "doc_token", "title",
                                 "dump_path", "route", "disambiguated", "replaced_existing",
                                 "unknown_block_types"])
def test_the_result_body_keeps_every_key_it_has_ever_answered(monkeypatch, tmp_path, key):
    """The new key is ADDITIVE: nothing a consumer already reads may leave with it."""
    result = _download(monkeypatch, tmp_path, [_page([])])
    assert key in result, sorted(result)


#: Every place the release notes state, in one sentence, what TYPE the value of the new key is.
#: Anchored on the key's own name so it cannot drift onto another key's sentence.
_NOTES_TYPE_CLAIM = re.compile(
    r"unknown_block_types.{0,120}?the value is (?:a |an |the |the same )?`([A-Za-z]+)`",
    re.DOTALL,
)


def test_the_release_notes_name_the_REAL_type_of_the_new_key():
    """The notes shipped `dict` for a value that is a `list` (the fix round on LD-657), which is
    exactly the class of claim nothing was holding. Bind the prose to the executed type.

    Reads the ROOT copy, per D-111: the packaged copy is a window and this section will fall out
    of it, while the claim stays true in the complete document. The packaged copy is a byte
    projection of this one (``tests/test_shipped_notes.py``), so correcting the root corrects it.
    """
    actual = type(DownloadResult({}).unknown_block_types).__name__
    notes = (pathlib.Path(__file__).resolve().parents[1] / "RELEASE_NOTES.md").read_text(
        encoding="utf-8"
    )
    claims = _NOTES_TYPE_CLAIM.findall(notes)
    assert claims, (
        "no sentence in RELEASE_NOTES.md states the type of `unknown_block_types` — this guard "
        "went vacuous; re-anchor it on the sentence that does."
    )
    assert set(claims) == {actual}, (claims, actual)
