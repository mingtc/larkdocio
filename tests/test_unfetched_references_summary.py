"""The end-of-download UNFETCHED-REFERENCES summary (LD-334, round-2 friction F5a).

The per-block markers answer *"what is in this paragraph?"*. At sixteen documents the
operator's question is *"what did this run not get?"* — the same disclosure discipline,
lifted from per-block to per-run. These tests pin:

* the parser's reference queue — collected during the block walk from the SAME typed nodes
  the renderer uses (never by scanning the rendered Markdown), OFFLINE-PURE and adding
  **zero** API calls on the default path;
* fetched-vs-unfetched taken off the node's own ``deep_read_markdown`` state, not guessed,
  with the three run states kept apart (never-by-design / not-enabled / deep-read-degraded);
* the message: counts per class, the routes that EXIST named and the ones that do not
  **not** promised, and silence when there is nothing to disclose;
* the ``--dump`` sidecar's machine-readable counterpart (which, unlike the log, states an
  explicit zero);
* and the load-bearing one — the rendered **Markdown is byte-identical** and the per-block
  markers are untouched (a pinned keeper).
"""
import logging

from harness import build_blocks

from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.read.references import (
    DEEP_READ_DEGRADED,
    EMBEDDED_BASE,
    EMBEDDED_SHEET,
    NEVER_BY_DESIGN,
    NOT_ENABLED,
    SYNCED_BLOCK,
    ReferenceNote,
    sidecar_payload,
    summary_lines,
)


# --- the fixture document: all four reference block types -------------------

ALL_FOUR = [
    {"block_id": "root", "block_type": 1, "parent_id": "",
     "children": ["s1", "s2", "bt", "rb", "rs"]},
    {"block_id": "s1", "parent_id": "root", "block_type": 30,
     "sheet": {"token": "SHEET_A"}},
    {"block_id": "s2", "parent_id": "root", "block_type": 30,
     "sheet": {"token": "SHEET_B"}},
    {"block_id": "bt", "parent_id": "root", "block_type": 18,
     "bitable": {"token": "BASE_18", "view_type": None}},
    {"block_id": "rb", "parent_id": "root", "block_type": 53,
     "reference_base": {"token": "BASE_53", "view_id": "VIEW53",
                        "layout_mode": "Normal"}},
    {"block_id": "rs", "parent_id": "root", "block_type": 50,
     "reference_synced": {"source_document_id": "DOC_50",
                          "source_block_id": "BLK_50"}},
]


def _parse(blocks_dicts, **parser_kwargs):
    parser = Parser(Config(), **parser_kwargs)
    markdown = parser.parse_docx_content("root", build_blocks(blocks_dicts))
    return parser, markdown


# --- AC2 — the parser collects the queue, offline-pure ----------------------

def test_parser_collects_every_reference_class_during_the_block_walk():
    parser, _ = _parse(ALL_FOUR)

    assert [(n.kind, n.identifier, n.fetched, n.reason) for n in parser.reference_notes] == [
        (EMBEDDED_SHEET, "SHEET_A", False, NOT_ENABLED),
        (EMBEDDED_SHEET, "SHEET_B", False, NOT_ENABLED),
        (EMBEDDED_BASE, "BASE_18", False, NOT_ENABLED),
        (EMBEDDED_BASE, "BASE_53", False, NOT_ENABLED),
        (SYNCED_BLOCK, "DOC_50", False, NEVER_BY_DESIGN),
    ]


def test_collection_costs_zero_api_calls_on_the_default_path():
    """No client of any kind is injected, so a fetch attempt would raise —
    the queue is built from the tree alone."""
    parser, _ = _parse(ALL_FOUR)

    assert parser.sheets_client is None
    assert getattr(parser, "base_client", None) is None
    assert len(parser.reference_notes) == 5


def test_the_queue_resets_per_parse_like_the_other_accumulators():
    parser = Parser(Config())
    blocks = build_blocks(ALL_FOUR)
    parser.parse_docx_content("root", blocks)
    parser.parse_docx_content("root", blocks)

    assert len(parser.reference_notes) == 5


def test_a_document_with_no_references_collects_nothing():
    parser, _ = _parse([
        {"block_id": "root", "block_type": 1, "parent_id": "", "children": ["t"]},
        {"block_id": "t", "parent_id": "root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "plain"}}]}},
    ])

    assert parser.reference_notes == []


# --- AC3 — fetched vs unfetched comes off the node's own state --------------

class _StubSheets:
    """Stands in for a sheets client; the bridge is monkeypatched, so it is inert."""


def test_a_successful_deep_read_is_not_reported_as_unfetched(monkeypatch):
    import larkdocio.sheets.embed as embed

    monkeypatch.setattr(embed, "deep_read_embedded_sheet",
                        lambda *a, **k: "| a |\n| - |\n| 1 |\n")
    parser, _ = _parse(ALL_FOUR, deep_read_sheets=True, sheets_client=_StubSheets())

    sheets = [n for n in parser.reference_notes if n.kind == EMBEDDED_SHEET]
    assert [n.fetched for n in sheets] == [True, True]
    assert [n.kind for n in parser.reference_notes if not n.fetched] == [
        EMBEDDED_BASE, EMBEDDED_BASE, SYNCED_BLOCK,
    ]


def test_an_attempted_deep_read_that_came_back_empty_is_its_own_state(monkeypatch):
    import larkdocio.sheets.embed as embed

    monkeypatch.setattr(embed, "deep_read_embedded_sheet", lambda *a, **k: None)
    parser, _ = _parse(ALL_FOUR, deep_read_sheets=True, sheets_client=_StubSheets())

    sheets = [n for n in parser.reference_notes if n.kind == EMBEDDED_SHEET]
    assert [n.reason for n in sheets] == [DEEP_READ_DEGRADED, DEEP_READ_DEGRADED]


def test_a_successfully_deep_read_base_is_not_reported_as_unfetched(monkeypatch):
    import larkdocio.base.embed as embed

    monkeypatch.setattr(embed, "deep_read_embedded_base",
                        lambda *a, **k: "| a |\n| - |\n| 1 |\n")
    parser, _ = _parse(ALL_FOUR, deep_read_bases=True, base_client=object())

    bases = [n for n in parser.reference_notes if n.kind == EMBEDDED_BASE]
    assert [n.fetched for n in bases] == [True, True]


def test_no_unfetched_references_produces_no_summary_at_all():
    assert summary_lines([]) == []
    assert summary_lines([ReferenceNote(EMBEDDED_SHEET, "T", True, None)]) == []


# --- AC4 — the report is useful, and honest about routes --------------------

CONSUMER_SHAPE = (
    "This document references 2 embedded sheets, 1 embedded Base and 1 synced block "
    "that were not fetched. Each one names itself and its token where it sits in the "
    "Markdown."
)


def test_the_headline_counts_by_class_in_the_consumer_s_own_shape():
    notes = [
        ReferenceNote(EMBEDDED_SHEET, "A", False, NOT_ENABLED),
        ReferenceNote(EMBEDDED_SHEET, "B", False, NOT_ENABLED),
        ReferenceNote(EMBEDDED_BASE, "C", False, NOT_ENABLED),
        ReferenceNote(SYNCED_BLOCK, "D", False, NEVER_BY_DESIGN),
    ]
    lines = summary_lines(notes)

    assert lines[0] == CONSUMER_SHAPE
    assert lines[1:] == [
        "Embedded sheets: pass --deep-read-sheets to read them as inline tables.",
        # LD-340: the Base twin now HAS a command-line route, so the guidance names it the
        # same way the sheet guidance does (was: "there is no command-line switch for this").
        "Embedded Bases: pass --deep-read-bases to read them as inline tables.",
        "Synced blocks: never fetched — the content lives in another document, and "
        "reading it needs a grant this integration usually does not have.",
    ]


def test_a_single_reference_reads_in_the_singular():
    lines = summary_lines([ReferenceNote(SYNCED_BLOCK, "D", False, NEVER_BY_DESIGN)])

    assert lines[0].startswith("This document references 1 synced block that were not") is False
    assert lines[0].startswith("This document references 1 synced block that was not fetched.")


def test_a_degraded_deep_read_says_so_in_the_headline():
    lines = summary_lines([ReferenceNote(EMBEDDED_SHEET, "A", False, DEEP_READ_DEGRADED)])

    assert lines[0].endswith(
        "1 embedded sheet was deep-read and the read did not come back; "
        "it kept its placeholder."
    )


def test_guidance_is_emitted_only_for_the_classes_actually_present():
    lines = summary_lines([ReferenceNote(EMBEDDED_SHEET, "A", False, NOT_ENABLED)])

    assert len(lines) == 2
    assert "Embedded Bases" not in "\n".join(lines)
    assert "Synced blocks" not in "\n".join(lines)


def test_no_route_that_does_not_exist_is_ever_advertised():
    every_note = [
        ReferenceNote(EMBEDDED_SHEET, "A", False, NOT_ENABLED),
        ReferenceNote(EMBEDDED_BASE, "C", False, DEEP_READ_DEGRADED),
        ReferenceNote(SYNCED_BLOCK, "D", False, NEVER_BY_DESIGN),
    ]
    text = "\n".join(summary_lines(every_note))

    # LD-340: --deep-read-bases is now a REAL route, so the summary advertises it (transformed
    # from "not in text"); the synced-block route still does not exist and must not appear.
    assert "--deep-read-bases" in text
    assert "--deep-read-synced" not in text
    assert "--deep-read-sheets" in text


def test_the_download_pipeline_logs_the_summary_at_info(caplog):
    from larkdocio.read import download

    parser, _ = _parse(ALL_FOUR)
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        download._report_unfetched_references(parser)

    records = [r for r in caplog.records if "not fetched" in r.message]
    assert records and all(r.levelno == logging.INFO for r in caplog.records)
    # The fixture carries BOTH Base embed types (18 and 53) — reported as one class.
    assert records[0].message == (
        "This document references 2 embedded sheets, 2 embedded Bases and 1 synced block "
        "that were not fetched. Each one names itself and its token where it sits in the "
        "Markdown."
    )


def test_a_clean_document_logs_nothing(caplog):
    from larkdocio.read import download

    parser, _ = _parse([
        {"block_id": "root", "block_type": 1, "parent_id": "", "children": []},
    ])
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        download._report_unfetched_references(parser)

    assert caplog.records == []


# --- AC1(d) — the --dump sidecar -------------------------------------------

def test_the_sidecar_carries_the_machine_readable_counts(tmp_path):
    import json

    from larkdocio.read import download

    parser, _ = _parse(ALL_FOUR)
    download._dump_json(object(), [], str(tmp_path), "TOK", parser=parser)
    payload = json.loads((tmp_path / "TOK.json").read_text(encoding="utf-8"))

    assert payload["unfetched_references"] == {
        "total": 5,
        "by_class": {"embedded_sheet": 2, "embedded_base": 2, "synced_block": 1},
        "by_reason": {"not_enabled": 4, "deep_read_degraded": 0,
                      "never_fetched_by_design": 1},
        "references": [
            {"kind": "embedded_sheet", "reason": "not_enabled", "id": "SHEET_A"},
            {"kind": "embedded_sheet", "reason": "not_enabled", "id": "SHEET_B"},
            {"kind": "embedded_base", "reason": "not_enabled", "id": "BASE_18"},
            {"kind": "embedded_base", "reason": "not_enabled", "id": "BASE_53"},
            {"kind": "synced_block", "reason": "never_fetched_by_design", "id": "DOC_50"},
        ],
    }


def test_the_sidecar_states_an_explicit_zero_unlike_the_log():
    assert sidecar_payload([]) == {
        "total": 0,
        "by_class": {"embedded_sheet": 0, "embedded_base": 0, "synced_block": 0},
        "by_reason": {"not_enabled": 0, "deep_read_degraded": 0,
                      "never_fetched_by_design": 0},
        "references": [],
    }


def test_the_sidecar_key_is_absent_when_no_parser_is_supplied(tmp_path):
    """The helper's own contract: a caller with no parse in hand writes the payload
    it always wrote."""
    import json

    from larkdocio.read import download

    download._dump_json(object(), [], str(tmp_path), "TOK")
    payload = json.loads((tmp_path / "TOK.json").read_text(encoding="utf-8"))

    assert "unfetched_references" not in payload


# --- AC6 — the shipped guide tells the landed truth -------------------------

def _guide_text():
    from pathlib import Path

    import larkdocio

    return (Path(larkdocio.__file__).parent / "GUIDE.md").read_text(encoding="utf-8")


def test_the_guide_documents_the_summary_and_its_relationship_to_the_flags():
    guide = _guide_text()

    assert "### What the run did not fetch — the end-of-download summary" in guide
    # The valuable sentence: which flag turns which class of reference into content.
    assert "`--deep-read-sheets` on the command line" in guide
    # LD-340: the Base twin now HAS a command-line route, so the guide names it the same way
    # (was: "**no command-line switch**: `Parser(...)`").
    assert "`--deep-read-bases` on the command line" in guide
    # Both deep-read flag rows point at it.
    assert guide.count("see *What the run did not fetch*") == 2


def test_the_guide_names_the_real_base_command_line_flag():
    # LD-340 transformed the old "never invents a Base CLI flag" guard: the flag is now REAL,
    # so the guide MUST name it (and must never claim there is no command-line switch for it).
    guide = _guide_text()
    assert "--deep-read-bases" in guide
    assert "no command-line switch" not in guide


# --- AC5 — the Markdown is byte-identical, the markers untouched ------------

MARKDOWN_BEFORE_LD334 = (
    "\n"
    "> 📊 **Embedded Sheet** — not fetched. token: `SHEET_A`. "
    "The spreadsheet's cells live in a separate Sheet document; deep read is "
    "out of scope.\n\n"
    "> 📊 **Embedded Sheet** — not fetched. token: `SHEET_B`. "
    "The spreadsheet's cells live in a separate Sheet document; deep read is "
    "out of scope.\n\n"
    "> 📊 **Embedded Base** (bitable) — not fetched. token: `BASE_18`. "
    "Contents (records, views, formulas) live in a separate Base document; "
    "deep read is out of scope. (Switching an embedded base to a named view "
    "makes it a reference_base — type 53 — instead.)\n\n"
    "> 📊 **Embedded Base — named view** (reference_base) — not fetched. "
    "token: `BASE_53`, view: `VIEW53`. A base switched to a named view (distinct "
    "from an embedded Base — type 18; consumers hit both interchangeably).\n\n"
    "> 🔗 **Synced content** referenced from document `DOC_50` (block `BLK_50`) "
    "— not fetched. The source document must grant this integration read access "
    "for its content to be pulled.\n\n"
)


def test_the_rendered_markdown_is_byte_identical_and_the_markers_are_unchanged():
    """The load-bearing assertion: collecting the queue adds a level, it does not
    change one byte of what the reader emits (the markers are a pinned keeper)."""
    _, markdown = _parse(ALL_FOUR)

    assert markdown == MARKDOWN_BEFORE_LD334
