"""LD-497 — a Base **mention** segment carrying a link renders as a link.

The consumer's finding, in one sentence: Lark mints a ``type:"mention"`` segment whenever a
human touches a Base text cell holding a pasted doc url, converting it into a doc-mention
chip; the chip carries the document's **title** in ``text`` and the **real url** — block
anchor included — in ``link``; and ``render_segment`` read that link and threw it away
through a branch written for *genuinely unknown* segment kinds. On their table, links were
**absent outright** from a ``read_base_markdown`` snapshot and every absent one was
mention-carried — plus phantom row diffs every time Lark chipped a cell nobody had edited.
(Their counts from their own production table are not published in this tree.)

**Every payload here is real in shape; its values are replaced** (tests/captures/README.md).
The specimen is
``tests/captures/base-study/captures/ld497-01-consumer-mention-segment.json``, which carries the
shape of the consumer's reported API JSON with its title and values replaced. No hand-invented
mention payload is used anywhere in this module: a hand-mocked dict would
make this regression test prove only that two hand-rolled halves agree
(PROJECT.md § Quality bar, in the dev repo).

The **characterization** arm (AC2) is the half that makes "unchanged" a measurement: the
link-less mention and the invented kind were pinned to these exact bytes on the pre-change
tree and are pinned to the same bytes here.
"""
import json
import re
from pathlib import Path

import pytest

from guard_kit import REPO_ROOT

from larkdocio.base import cells, plain
from larkdocio.model import MarkdownRenderer, StyledText, Text
import private_tree  # noqa: E402  (LD-685)
from retired_particulars import load, value_hits

REPO_ROOT = Path(REPO_ROOT)
CAPTURES = REPO_ROOT / "tests" / "captures" / "base-study" / "captures"

#: The consumer's own payload, on disk, attributed in-file (AC7).
CONSUMER_CAPTURE = "ld497-01-consumer-mention-segment.json"

#: The seat's own extension of LD-416's enumeration onto the batch record route (AC5 rung a).
BATCH_ROUTE_CAPTURE = "ld497-02-batch-record-mention-write.json"

#: The READ-ONLY scan of the Scratch Base for a human-chipped cell (AC5 rung b).
SCRATCH_SCAN_CAPTURE = "ld497-03-scratch-base-mention-scan.json"


def _capture(name):
    return json.loads((CAPTURES / name).read_text(encoding="utf-8"))


def consumer_mention_segment():
    """The consumer's quoted ``mention`` segment, read off the committed capture."""
    return dict(_capture(CONSUMER_CAPTURE)["segment"])


# --------------------------------------------------------------------------- #
# AC7 — the fixtures are REAL and say where they came from                     #
# --------------------------------------------------------------------------- #

#: TRANSFORMED (LD-699, round 2 of the public-export review; supersession.md § A.1). The REASON
#: is unchanged — the specimen names its own provenance, and D-59 scopes the label to the route,
#: field, tenant and day it was observed on. The CONCLUSION moved: the public copy no longer names
#: the consumer, their report's file, its date or the wheel version (a downstream user's data is
#: generic in the public tree), so the citation of the report is held against the PRIVATE
#: original, and the public copy is held to a scope that says "one day" without dating it.
def test_ac7_the_specimen_is_a_committed_capture_that_names_its_own_provenance():
    payload = _capture(CONSUMER_CAPTURE)
    assert "CONSUMER REPORT" in payload["_provenance"]
    # The host is redacted exactly as the consumer redacted it — the literal ellipsis.
    assert payload["segment"]["link"].startswith("https://…/docx/")
    assert "redact" in payload["_redaction"].lower()
    # D-59: the label is scoped to the route / field / tenant / day it was observed on.
    for token in ("records/search", "(1, Text)", "one day", "Docx", "UNMEASURED"):
        assert token in payload["_scope"], token


@private_tree.dev_record
def test_ac7_the_public_copy_carries_none_of_the_reporters_particulars():
    """LD-700: the capture carries none of the values in the private ledger's
    ``capture_values`` list (tests/retired_particulars.py), which is read at run time."""
    payload = json.dumps(_capture(CONSUMER_CAPTURE), ensure_ascii=False)
    assert not value_hits(payload, load("capture_values"))


@private_tree.citations
def test_ac7_the_private_original_cites_the_consumer_report():
    """LD-700 (T3): the report is found by its label, never named here — the file name carried
    the report's date and the consumer's version."""
    original = json.loads((REPO_ROOT / "dev" / "base-study" / "captures" / CONSUMER_CAPTURE)
                          .read_text(encoding="utf-8"))
    assert "CONSUMER REPORT" in original["_provenance"]
    cited = re.findall(r"dev/consumer-feedback/[^\s`'\")]+\.md", original["_provenance"])
    assert cited, "the private original no longer cites the consumer report it came from"
    assert all((REPO_ROOT / path).is_file() for path in cited), cited


def test_ac7_the_consumer_quoted_payload_is_the_one_the_issue_carries():
    """The four keys the report quotes, verbatim — a fixture that drifted from the report
    would make every assertion below a claim about a different payload."""
    seg = consumer_mention_segment()
    assert seg["type"] == "mention"
    assert seg["mentionType"] == "Docx"
    assert seg["token"] == "Example09c5f37ea54fdaa4a226"
    assert seg["text"] == "Example Document Title"
    assert seg["link"].endswith("#Example9475ce2dda1cd28747db")


# --------------------------------------------------------------------------- #
# AC1 — the SAME serializer path as `url`, byte-identical                      #
# --------------------------------------------------------------------------- #

def test_ac1_a_mention_carrying_a_link_renders_the_link():
    seg = consumer_mention_segment()
    out = cells.render_segment(seg)
    assert out.startswith("["), out
    assert f"]({seg['link']})" in out, out


def test_ac1_the_SAME_text_and_link_render_IDENTICALLY_as_url_and_as_mention():
    """The AC's own proof shape: render the *same* ``(text, link)`` pair under both kinds and
    assert the two outputs are **equal strings** — escaping, emphasis and all. Not "both
    contain a link": equal."""
    seg = consumer_mention_segment()
    as_mention = cells.render_segment(seg)
    as_url = cells.render_segment({**seg, "type": "url"})
    assert as_mention == as_url
    # …and equal to what the shared serializer composes for a docx link, which is the parity
    # `_url_segment` already advertises (`cells.py`'s "a Base link and a docx link are
    # byte-identical").
    shared = MarkdownRenderer().render_inline(
        [StyledText(content=seg["text"], link_url=seg["link"])])
    assert as_mention == shared


def test_ac1_it_goes_through_the_url_serializer_rather_than_a_second_link_writing_branch():
    """A second branch that happened to emit the same bytes today would drift tomorrow. The
    mention is routed into ``_url_segment`` itself, which this proves by replacing that one
    function and watching the mention follow it."""
    seg = consumer_mention_segment()
    original = cells._url_segment
    try:
        cells._url_segment = lambda s, ctx: "«the url serializer»"
        assert cells.render_segment(seg) == "«the url serializer»"
    finally:
        cells._url_segment = original


def test_ac1_a_mention_inside_a_segment_array_survives_the_walk():
    """The shape a real cell arrives in: the walker joins with nothing, so the link has to
    survive ``render_segments`` and not only ``render_segment``."""
    seg = consumer_mention_segment()
    out = cells.render_segments([{"type": "text", "text": "see "}, seg])
    assert out.startswith("see [")
    assert f"]({seg['link']})" in out


def test_ac1_the_cell_renderer_above_it_carries_the_link_too():
    """``read_base_markdown``'s own path: a ``(1, Text)`` cell whose segment array holds a
    chip. This is the projection the consumer's frozen snapshots are taken from."""
    field = cells.FieldSpec(field_name="Source Links", type=1, ui_type="Text")
    out = cells.render_cell([consumer_mention_segment()], field)
    assert f"]({consumer_mention_segment()['link']})" in out


# --------------------------------------------------------------------------- #
# AC2 — a link-LESS mention and a genuinely unknown kind are UNCHANGED         #
# --------------------------------------------------------------------------- #

#: Measured on the PRE-change tree and pinned here, so "unchanged" is a
#: measurement rather than an assertion. LD-416's own probe spelling is the specimen — it is a
#: real sent shape (``tests/captures/base-study/captures/ld416-01-text-url-segment-write.json``), not an
#: invention of this test.
_LINKLESS_MENTION = {"type": "mention", "text": "@nobody"}
_INVENTED_KIND = {"type": "zzz-not-a-kind", "text": "surface me *anyway*"}


@pytest.mark.parametrize("seg,expected", [
    (_LINKLESS_MENTION, "@nobody"),
    ({**_LINKLESS_MENTION, "link": None}, "@nobody"),
    ({**_LINKLESS_MENTION, "link": ""}, "@nobody"),
    (_INVENTED_KIND, "surface me \\*anyway\\*"),
])
def test_ac2_the_text_only_fall_through_still_catches_these_exact_bytes(seg, expected):
    assert cells.render_segment(seg) == expected


def test_ac2_a_link_less_mention_is_not_an_error_and_never_raises():
    for seg in (_LINKLESS_MENTION, {"type": "mention"}, {"type": "mention", "link": None}):
        assert isinstance(cells.render_segment(seg), str)


def test_ac2_the_fall_through_comment_describes_what_it_NOW_catches():
    """The comment above the fall-through was written for *genuinely* unknown kinds and a
    known one was falling into it. After the fix it catches a link-less mention too, and it
    says so — a stale comment here is exactly how the next reader repeats the mistake."""
    source = (REPO_ROOT / "src" / "larkdocio" / "base" / "cells.py").read_text(
        encoding="utf-8")
    body = source.split("def render_segment(")[1].split("\ndef ")[0]
    assert "never raise, never guess" in body, "the standing posture line was dropped"
    assert re.search(r"#.*link-less mention", body), (
        "the fall-through's comment must name the link-less mention it now catches")


def test_ac2_the_LD416_probe_spelling_is_a_real_sent_shape_not_an_invention():
    """The link-less specimen above is the exact value LD-416 put on both record-write
    routes, so even the characterization arm reads from a committed capture."""
    text = (CAPTURES / "ld416-01-text-url-segment-write.json").read_text(encoding="utf-8")
    assert '"type": "mention"' in text and '"@nobody"' in text


# --------------------------------------------------------------------------- #
# AC3 — the PLAIN projection does not move                                     #
# --------------------------------------------------------------------------- #

def test_ac3_cell_text_on_the_specimen_is_the_title_and_only_the_title():
    """As the consumer reported: the plain projection dropping the link is **correct** — it
    documents itself as unescaped, undecorated plain text, and it behaves."""
    seg = consumer_mention_segment()
    assert plain.cell_text([seg]) == seg["text"]
    assert plain.cell_text(seg) == seg["text"]
    assert seg["link"] not in plain.cell_text([seg])


def test_ac3_plain_value_on_the_specimen_is_the_title_and_only_the_title():
    seg = consumer_mention_segment()
    assert plain.plain_value([seg]) == seg["text"]
    assert plain.plain_value(seg) == seg["text"]


def test_ac3_the_two_projections_still_read_the_segment_through_ONE_reader():
    """They must keep agreeing about *what a segment says* and differ only in how they write
    it down. One reader (``_segment_parts``), two compositions."""
    seg = consumer_mention_segment()
    seg_type, text, link = cells._segment_parts(seg)
    assert (seg_type, text, link) == ("mention", seg["text"], seg["link"])
    assert plain._segment_parts is cells._segment_parts
    # The plain module holds no second walk of its own.
    plain_source = (REPO_ROOT / "src" / "larkdocio" / "base" / "plain.py").read_text(
        encoding="utf-8")
    assert 'seg_type == "mention"' not in plain_source, (
        "the plain projection must not grow a mention branch — it does not write links down")


def test_ac3_a_URL_segment_inside_an_array_is_still_plain_text_downstream():
    """The neighbouring rule the fix must not disturb: ``cell_text`` of a url segment is its
    label, not its link. If a mention now behaved differently from a url here, the two
    projections would have stopped agreeing."""
    seg = consumer_mention_segment()
    assert plain.cell_text([{**seg, "type": "url"}]) == seg["text"]


# --------------------------------------------------------------------------- #
# AC4 — the bounded, probe-first pass: what is measured, and what is DISCLOSED #
# --------------------------------------------------------------------------- #

def test_ac4_the_measured_segment_kinds_are_exactly_the_three_with_a_captured_payload():
    assert cells.MEASURED_SEGMENT_KINDS == ("text", "url", "mention")


def test_ac4_the_only_measured_mention_type_is_the_one_a_capture_carries():
    assert cells.MEASURED_MENTION_TYPES == ("Docx",)
    assert consumer_mention_segment()["mentionType"] in cells.MEASURED_MENTION_TYPES


def test_ac4_the_unmeasured_mention_types_are_DISCLOSED_BY_NAME():
    """`process/doctrine/negative-claims.md`: the untried forms are **unmeasured, not
    refuted**, and they are named so a reader can see the edge of the evidence."""
    assert cells.UNMEASURED_MENTION_TYPES == ("Chat", "User")
    disclosure = cells.SEGMENT_KIND_DISCLOSURE
    for name in cells.UNMEASURED_MENTION_TYPES:
        assert name in disclosure, name
    assert "@user" in disclosure and "@chat" in disclosure
    assert "unmeasured" in disclosure.lower()


def test_ac4_the_disclosure_says_UNMEASURED_rather_than_impossible():
    disclosure = cells.SEGMENT_KIND_DISCLOSURE.lower()
    for forbidden in ("cannot", "impossible", "is not supported", "does not exist"):
        assert forbidden not in disclosure, forbidden
    # D-59: scoped to what was actually observed, and to where it was observed. (LD-699: "one
    # day" rather than a date. LD-715, owner ruling 2026-11-07: "outside this project's tenant"
    # rather than who observed it — the reason holds, the evidence is still labelled as not this
    # project's own measurement; only the attribution wording is superseded.)
    assert "one tenant" in disclosure
    assert "outside this project's tenant on one day" in disclosure


def test_ac4_NO_handler_ships_for_a_kind_nobody_captured():
    """No ``mentionType`` is branched on — speculatively or otherwise. The rule is *a link is
    a link*, whatever kind of chip carries it, so the dispatch reads ``link`` and never
    ``mentionType``."""
    source = (REPO_ROOT / "src" / "larkdocio" / "base" / "cells.py").read_text(
        encoding="utf-8")
    body = source.split("def render_segment(")[1].split("\ndef ")[0]
    # The CODE, with the prose stripped: a comment may name `mentionType` (and does, to say
    # why nothing keys on it); an executable line may not.
    code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
    assert "mentionType" not in code, (
        "render_segment must not branch on mentionType — no kind was captured to justify it")
    for name in cells.UNMEASURED_MENTION_TYPES:
        assert f'"{name}"' not in code


def test_ac4_an_UNMEASURED_mention_type_carrying_a_link_still_renders_its_link():
    """The disclosure is about *coverage of the evidence*, not about behaviour: because the
    rule keys on the presence of a ``link`` and not on the kind of chip, a mention of a kind
    nobody has captured is handled the same way the moment one arrives. That is why the
    caveat is about what has been **seen**, not about what would happen."""
    seg = {**consumer_mention_segment(), "mentionType": "User"}
    assert cells.render_segment(seg) == cells.render_segment({**seg, "type": "url"})


# --------------------------------------------------------------------------- #
# AC5 — the live-evidence ladder's own record                                  #
# --------------------------------------------------------------------------- #

def test_ac5_the_batch_route_leg_committed_its_capture_with_a_D59_scope_sentence():
    payload = _capture(BATCH_ROUTE_CAPTURE)
    assert payload["_probe"] == "ld497-02"
    assert "batch_create" in payload["_endpoint"]
    assert payload["_verdict"]
    assert "D-59" in payload["_scope"]
    assert payload["_sends"] <= 4, "the leg was capped at four sends, no retries"
    assert payload["_disposable"]["folder_env"] == "LARKDOCIO_DISPOSABLES_FOLDER"


@private_tree.citations
def test_ac5_the_probe_script_is_committed_beside_its_capture():
    """LD-491: a spike commits the script that produced its evidence, or says it ran none."""
    script = (REPO_ROOT / "dev" / "base-study" / "probes"
              / "probe_ld497_batch_mention_write.py")
    assert script.is_file(), "the probe script that produced ld497-02 must be committed"
    assert "batch_create" in script.read_text(encoding="utf-8")
    assert _capture(BATCH_ROUTE_CAPTURE)["_script"] == str(
        script.relative_to(REPO_ROOT))


def test_ac5_the_batch_route_answer_NARROWS_the_LD416_not_tried_list_in_shipped_text():
    """Whichever way the write answer went, it is a **shipped** fact — and here it went the
    same way the fourteen single-record spellings went. What moves is the *edge of the
    evidence*: `records/batch_create` was listed as untried and is not untried any more, so
    the shipped sentence that said so is corrected in the same change. LD-416's own record —
    its two routes, its fourteen attempts, its control — is left exactly as measured: this
    leg sent one shape on one route with no control of its own, and folding it into that
    sweep would put a claim on evidence that does not carry it (D-59)."""
    from larkdocio.base import shape_docs, write_cells

    record = shape_docs.MEASURED_REFUSALS[(1, "Text")]
    assert len(record.routes) == 2, "LD-416's own two-route scope is not this leg's to widen"
    remaining = " ".join(record.not_tried)
    assert "`records/batch_update`" in remaining, (
        "the batch route nobody sent on stays disclosed as unmeasured")
    assert "1254060" in remaining and "batch_create" in remaining, (
        "the measured batch answer must be visible where the untried list used to claim it")
    assert "TABLE-CREATION" in remaining, "seeding at table-creation time is still untried"

    prose = write_cells.TEXT_SEGMENT_ARRAY_IS_SERVER_REFUSED_TOO
    assert "records/batch_create has now been asked once" in prose
    assert "records/batch_update" in prose and "UNMEASURED, not refused" in prose


#: **THE RUNG-(b) SCAN HAS TWO DATED READINGS (LD-512, superseding LD-497's single one).**
#:
#: ``(date, mentions_found, tables_scanned, cells_scanned)`` — and the order matters, because
#: the LATER reading does not retroactively falsify the earlier one:
#:
#: * **2026-08-17, at LD-497's landing — 0 chips across 2 tables / 28 cells.** Nobody had
#:   chipped a cell in the Scratch Base, so the scan could not find one. That is what made the
#:   live half of the READ specimen a parked remainder and the offline half — the consumer's own
#:   API JSON — the thing the story stands on. **That reason is preserved, unchanged.**
#: * **2026-08-18, after a cell in table 1 was chipped by hand — 1 chip across 2 tables / 31 cells.** A
#:   pasted docx URL became a title chip and the same committed 3-read probe found it. The
#:   parked remainder is now observed.
#:
#: Only the CONCLUSION moves. A D-59 scope is a claim about one tenant on one date
#: (``_scope`` in the capture says exactly that), so two dates are two readings, not a
#: contradiction — "the scan found none" was true on the 17th and stays true about the 17th.
#: What is superseded is the sentence that treated the 17th's absence as the standing state of
#: the world.
#:
#: The committed capture carries the LATER reading, because the probe rewrites it in place. The
#: earlier reading survives only here, which is precisely why it is written down: when the
#: seat's capture commit reddened these tests and was reverted, the lesson recorded was *"the
#: run output is not the record"* (the ld317-01 shape). This constant is the record.
SCAN_READINGS = (
    ("2026-08-17", 0, 2, 28),
    ("2026-08-18", 1, 2, 31),
)

#: The reading the committed capture holds — the newest one, by the probe's own write-in-place.
LATEST_SCAN_READING = SCAN_READINGS[-1]


def test_ac5_rung_b_RAN_read_only_and_recorded_what_it_did_NOT_find():
    """Rung (a) refused, so the ladder went on to (b): a READ-ONLY scan of the Scratch Base
    for the cell a human would have chipped. **On 2026-08-17 it found none** — and a negative
    live claim is only usable with its enumeration attached (D-59), so the scan records the
    routes it used, the tables it walked and the number of cells it looked at.

    **LD-512 — the node id and the claim above are unchanged; the pin is not.** This asserted
    ``_mentions_found == []`` as a standing fact. It is now asserted against
    :data:`SCAN_READINGS`, which carries **both** dated readings, because on 2026-08-18 the maintainer
    chipped a cell and the same probe found it. What never moves — and is what this test is
    really for — is that the scan is READ-ONLY and spends nothing: zero writes, zero
    disposables, zero media tokens, on the pinned read route, D-59 scoped.
    """
    payload = _capture(SCRATCH_SCAN_CAPTURE)
    assert payload["_probe"] == "ld497-03"
    assert payload["_writes"] == 0, "the Scratch Base is READ-ONLY, always"
    assert payload["_disposables_created"] == 0
    assert payload["_media_tokens_created"] == 0

    _date, mentions, tables, cells = LATEST_SCAN_READING
    assert len(payload["_mentions_found"]) == mentions, (
        f"the committed capture holds {len(payload['_mentions_found'])} mention-carrying "
        f"cell(s); the readings on record are {SCAN_READINGS} — a THIRD reading is a third "
        "row here (with its date and its D-59 scope), never an edit to an existing one")
    assert len(payload["_tables_scanned"]) == tables and payload["_cells_scanned"] == cells
    assert len(payload["_tables_scanned"]) >= 1 and payload["_cells_scanned"] >= 1, (
        "a scan that walked nothing is not evidence of absence")
    assert "records/search" in payload["_endpoint"], "the pinned read route, named"
    assert "D-59" in payload["_scope"]


def test_ac5_the_two_dated_readings_do_not_contradict_each_other():
    """The supersession made checkable (LD-512): the readings are dated, ordered, and the
    later one is a *find* against the earlier one's *absence* — which is what a chipped cell
    is supposed to produce. An absence recorded on one date is not a claim about every date,
    and this is the assertion that says so out loud."""
    dates = [row[0] for row in SCAN_READINGS]
    assert dates == sorted(dates) and len(set(dates)) == len(dates), SCAN_READINGS
    assert SCAN_READINGS[0][1] == 0, "the landing-time reading was an ABSENCE — the reason the "\
        "offline half of the specimen stands on the consumer's own JSON"
    assert SCAN_READINGS[-1][1] >= 1, "the parked remainder is observed on the later date"
    assert SCAN_READINGS[-1][3] > SCAN_READINGS[0][3], (
        "the later scan walked MORE cells, which is why the two counts are not comparable as "
        "a before/after of the same population")


def test_ac5_the_observed_chip_is_a_REAL_mention_segment_shaped_like_the_consumers():
    """The later reading is only worth landing if it is the same shape the whole module is
    about: a ``type: "mention"`` segment carrying a link the plain projection used to drop."""
    found = _capture(SCRATCH_SCAN_CAPTURE)["_mentions_found"]
    assert found, "the committed capture holds no chip — see SCAN_READINGS"
    segment = found[0]["segment"]
    assert segment["type"] == "mention" and segment["link"] and segment["text"]
    assert "<redacted" in segment["link"], (
        "the tenant host must stay redacted — tests/test_base_cells.py's nine-pattern PII "
        "sweep reads every capture in that directory")


@private_tree.citations
def test_ac5_rung_b_committed_its_probe_script_too():
    script = (REPO_ROOT / "dev" / "base-study" / "probes"
              / "probe_ld497_scratch_base_mention_scan.py")
    assert script.is_file()
    source = script.read_text(encoding="utf-8")
    assert "READ-ONLY" in source
    for writer in ("batch_create", "batch_update", "create_table", "disposable_base",
                   "from_write_credentials"):
        assert writer not in source, (
            f"the rung (b) script names {writer!r} — it must not be able to write")


def test_ac5_the_ladder_LANDED_ON_RUNG_C_and_the_offline_half_stands_on_real_json():
    """(a) ran and was refused; (b) ran and found nothing; so the live half of the READ
    specimen is the parked remainder and the offline half carries the story. That offline
    half is **actual API JSON** — the consumer's own measured payload — which is what makes
    it a legal fixture rather than a hand-mocked dict."""
    assert "1254060" in _capture(BATCH_ROUTE_CAPTURE)["_answer"]        # rung (a): refused
    # rung (b): NONE **at landing** — SCAN_READINGS[0], 2026-08-17. LD-512: the pin moved off
    # the live capture and onto the dated reading, because the capture now holds the 2026-08-18
    # re-read (1 chip, after a cell was chipped by hand) and that later find does not un-make the
    # reason rung (c) was reached. The ladder landed where it landed, on the date it landed.
    assert SCAN_READINGS[0] == ("2026-08-17", 0, 2, 28)
    assert "CONSUMER REPORT" in _capture(CONSUMER_CAPTURE)["_provenance"]   # rung (c)
    assert consumer_mention_segment()["link"], (
        "the offline specimen must carry the very link the projection was dropping")


def test_ac5_the_capture_says_the_answer_and_the_probe_says_zero_media():
    payload = _capture(BATCH_ROUTE_CAPTURE)
    assert "1254060" in payload["_answer"], payload["_answer"]
    assert payload["_media_tokens_created"] == 0
    assert payload["_no_retries"] is True
    assert len(payload["_send_log"]) == payload["_sends"] == 4


# --------------------------------------------------------------------------- #
# AC6 — the falsified shipped sentence is SUPERSEDED, reason preserved         #
# --------------------------------------------------------------------------- #

_CELLS_SOURCE = (REPO_ROOT / "src" / "larkdocio" / "base" / "cells.py").read_text(
    encoding="utf-8")


def test_ac6_the_falsified_evidence_clause_is_GONE():
    """`cells.py`'s own note said Base's vocabulary is *just* ``text`` and ``url`` — "the only
    two evidenced", "no mention". A production Base mints a third kind."""
    assert "the only two evidenced" not in _CELLS_SOURCE
    assert "and no mention" not in _CELLS_SOURCE


def test_ac6_the_REASON_around_it_survives_unchanged():
    """`process/doctrine/supersession.md` § A.1 — the record keeps the original reason and
    replaces only the conclusion. The reason here is *three walkers, three vocabularies,
    lifting the Sheets one reddens a shipped guard*."""
    for kept in (
        "Three walkers exist in this repo",
        "_BRANCH_MARKERS",
        "reddens a shipped drift guard",
        "a refactor of the Sheets surface",
    ):
        assert kept in _CELLS_SOURCE, kept


def test_ac6_the_superseding_clause_carries_its_attribution_and_its_scope():
    walker_note = _CELLS_SOURCE.split("**Why a Base-local segment walker")[1].split('"""')[0]
    # LD-699: the scope token is "one day", no longer a date (see test_ac7 above). LD-715: the
    # attribution token is "outside this project", no longer who observed it.
    for token in ("mention", "one day", "outside this project"):
        assert token in walker_note, token


def _runtime_text_of_src():
    """Every string a consumer could be handed at runtime, concatenated — the other half of
    the LD-480 census (each grep misses what the other catches)."""
    import larkdocio

    parts = [json.dumps(larkdocio.capabilities(full=True), default=str, sort_keys=True)]
    for accessor in ("guide", "writer_brief", "release_notes", "changelog"):
        parts.append(getattr(larkdocio, accessor)(full=True)
                     if accessor == "guide" else getattr(larkdocio, accessor)())
    return "\n".join(parts)


def _flat(text):
    """Whitespace-normalised — the clause was wrapped across two source lines, so a raw
    substring search would miss the very copy this census exists to find."""
    return " ".join(text.split())


@pytest.mark.parametrize("phrase", [
    "the only two evidenced",
    "no style and no mention",
    "vocabulary is just ``text`` and ``url``",
])
def test_ac6_the_census_finds_NO_surviving_copy_of_the_falsified_claim(phrase):
    """Both halves of the census: the source text of ``src/larkdocio/**`` and the
    concatenated runtime values, plus the root matrices."""
    needle = _flat(phrase)
    src = REPO_ROOT / "src" / "larkdocio"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted(src.rglob("*"))
        if path.is_file() and path.suffix in (".py", ".md")
        and needle in _flat(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    for matrix in ("BASE.md", "BLOCKS.md", "SHEETS.md", "PERMISSIONS.md", "README.md"):
        if needle in _flat((REPO_ROOT / matrix).read_text(encoding="utf-8")):
            offenders.append(matrix)
    assert offenders == [], offenders
    assert needle not in _flat(_runtime_text_of_src())


# --------------------------------------------------------------------------- #
# AC8 — the guide states the link-losslessness truth EITHER WAY                #
# --------------------------------------------------------------------------- #

def _packaged_guide():
    return (REPO_ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")


def test_ac8_the_guide_says_a_link_carrying_chip_IS_preserved():
    guide = _packaged_guide()
    assert "doc-mention chip" in guide
    assert "[title](url)" in guide or "`[text](link)`" in guide


def test_ac8_the_guide_carries_the_CAVEAT_the_consumer_said_would_have_saved_them():
    """The consumer said one sentence in the guide — that ``read_base_markdown`` is not
    link-lossless for cells humans have touched — would have saved them the investigation; the
    caveat is **scoped** to the kinds nobody has measured rather than dropped, because AC4's
    pass is bounded by evidence and does not cover every kind Lark can mint."""
    guide = _packaged_guide()
    assert "link-lossless" in guide
    for name in ("@user", "@chat"):
        assert name in guide, name
    window = guide[guide.index("link-lossless") - 1200:guide.index("link-lossless") + 1600]
    assert "unmeasured" in window.lower()
    assert "read_base_markdown" in window


def test_ac8_the_guide_says_the_PLAIN_projection_is_unchanged():
    guide = _packaged_guide()
    window = guide[guide.index("link-lossless") - 1600:guide.index("link-lossless") + 2000]
    assert "cell_text" in window


# --------------------------------------------------------------------------- #
# AC9 — BASE.md moves with the surface                                         #
# --------------------------------------------------------------------------- #

def test_ac9_the_matrix_text_row_carries_the_mention_kind_and_its_rule():
    base_md = (REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    text_row = [line for line in base_md.splitlines()
                if line.startswith("| Text | `1` / `Text` |")]
    assert len(text_row) == 1, text_row
    assert "mention" in text_row[0]
    assert "`[text](link)`" in text_row[0]


def test_ac9_the_R13_principles_row_carries_the_kind_vocabulary():
    base_md = (REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    r13 = [line for line in base_md.splitlines()
           if "segment walker dispatches on EACH SEGMENT" in line]
    assert len(r13) == 1, r13
    assert "mention" in r13[0]
    assert "test_base_mention_segment_link.py" in r13[0]


def test_ac9_the_link_row_still_states_the_shared_serializer_parity():
    base_md = (REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    link_row = [line for line in base_md.splitlines()
                if line.startswith("| Link | `15` / `Url` |")]
    assert len(link_row) == 1, link_row
    assert "shared" in link_row[0] and "mention" in link_row[0]
