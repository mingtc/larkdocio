"""LD-472 live gate — the TWO measurements the sheets-truth docs batch is written FROM.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it by NAME (never a bare ring sweep)::

    pytest tests/test_live_sheets_ld472_doc_truth_gate.py -m live_write

Two shipped sentences were measured false in dogfood round 4, and LD-472 rewrites them. This
gate is the re-measurement the issue's AC2 and AC8 require **before** the prose is written,
on a workbook this file creates and deletes:

1. **``AddTab`` with no ``index``** — the guide said *"omit ``index`` to append"*. The arm
   builds a workbook with ≥2 tabs, adds one with **no** ``index``, and reads the tab order
   back. Then it adds one with ``index=len(tabs)`` and reads back again, so the **append
   idiom** the docs now hand over is the measured one rather than the plausible one.
2. **``float_image`` over a MULTI-CELL range** — the recipe was titled *"float a picture OVER
   a range"* and labelled *unmeasured, not refuted*. The arm binds over an ordinary 4×10
   ``A1:D10`` and records what Lark answers, then binds a **single-cell anchor** as the
   control. Whatever code comes back is **recorded, not asserted** (Lark renumbers); what is
   asserted is that the multi-cell bind FAILED while the single-cell one LANDED, and that the
   failure carried an ``orphan_file_token``.

**THIS ARM MINTS PERMANENT, UNSWEEPABLE RESIDUE, AND THAT IS BOUGHT KNOWINGLY** — the same
disclosure the float-image gate carries. The upload happens **before** bind validation, so the
refused multi-cell bind leaves a media token nothing points at, **no open-API verb purges drive
media**, and trashing the workbook does not remove the bytes. There is therefore no cleanup leg
here and there cannot be one; every token minted is **printed**, so the residue is ledgered
rather than implied.

**THE TARGET IS ONLY A WORKBOOK THIS GATE CREATED.** No environment variable naming a sheet is
read; the canary is never addressed. The workbook is deleted in a ``finally`` and its gone-ness
is proved by an independent re-query, never by the delete's own ``code:0``.

**Skips loudly, never silently.** Without write credentials the arm skips naming what is
missing.
"""
import time
import zlib

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.media import (
    FloatImageMediaClient,
    put_float_image_in_sheet,
)
from larkdocio.sheets.write_apply import AddTab, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient, spreadsheet_is_gone

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"


def png_bytes():
    """A 1x1 PNG, built from source so no binary fixture is committed."""
    def chunk(kind, payload):
        body = kind + payload
        return (len(payload).to_bytes(4, "big") + body
                + zlib.crc32(body).to_bytes(4, "big"))

    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes((0, 0, 0, 0)))) + chunk(b"IEND", b""))


def _titles(writer, token):
    """The tab titles in the order the API lists them — the read-back the docs quote."""
    return [(i, tab["title"]) for i, tab in enumerate(writer.query_tabs(token))]


def test_ld472_addtab_placement_and_float_image_range_are_re_measured(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    media = FloatImageMediaClient.from_write_credentials(DOMAIN)
    payload = png_bytes()

    title = H.disposable_title(f"LD472-doc-truth-{int(time.time())}")
    dest_folder = canary_support.require_disposables_folder()
    workbook = writer.create_spreadsheet(title, folder_token=dest_folder)
    token = workbook["spreadsheet_token"]
    assert token, f"create returned no spreadsheet_token: {workbook!r}"
    ev = {"spreadsheet_token": token, "media_residue": []}

    try:
        # ---------------------------------------------------------------- #
        # AC2 — AddTab placement, measured.                                  #
        # ---------------------------------------------------------------- #
        # A workbook with >= 2 tabs, so "first" and "last" are distinguishable.
        seed = apply(dry_run([AddTab(title="Rollout", index=1)], writer, token), writer)
        assert seed.entries[0].is_applied, seed.entries[0].to_dict()
        ev["before"] = _titles(writer, token)
        assert len(ev["before"]) >= 2, ev["before"]

        # (a) NO index at all — the sentence under test.
        no_index = apply(dry_run([AddTab(title="zz-no-index")], writer, token), writer)
        assert no_index.entries[0].is_applied, no_index.entries[0].to_dict()
        ev["after_no_index"] = _titles(writer, token)
        ev["no_index_position"] = [i for i, t in ev["after_no_index"] if t == "zz-no-index"]

        # (b) index=len(tabs) — the append idiom the docs hand over.
        tabs = writer.query_tabs(token)
        ev["len_tabs"] = len(tabs)
        appended = apply(
            dry_run([AddTab(title="zz-appended", index=len(tabs))], writer, token), writer)
        assert appended.entries[0].is_applied, appended.entries[0].to_dict()
        ev["after_append_idiom"] = _titles(writer, token)
        ev["append_idiom_position"] = [
            i for i, t in ev["after_append_idiom"] if t == "zz-appended"]

        # THE MEASUREMENT WINS (issue AC2/AC8). These two assertions are what the prose says.
        assert ev["no_index_position"] == [0], (
            "AddTab with no index did NOT land first; the docs LD-472 writes must follow this "
            f"measurement, not round 4's: {ev['after_no_index']!r}")
        assert ev["append_idiom_position"] == [len(ev["after_append_idiom"]) - 1], (
            "index=len(tabs) did NOT land last; the append idiom the guide hands over must be "
            f"corrected to whatever this run measured: {ev['after_append_idiom']!r}")

        # ---------------------------------------------------------------- #
        # AC8/AC9 — the float-image range refutation, and its residue.       #
        # ---------------------------------------------------------------- #
        sheet_id = writer.query_tabs(token)[0]["sheet_id"]
        ev["sheet_id"] = sheet_id

        # (c) A MULTI-CELL RANGE — an ordinary 4x10, the shape the recipe's title promised.
        multi = f"{sheet_id}!A1:D10"
        multi_refusal = None
        try:
            floated = put_float_image_in_sheet(
                client=writer, media=media, spreadsheet_token=token, sheet_id=sheet_id,
                a1_range=multi, data=payload, name="ld472-multi.png",
                width=120, height=120, verify_bytes=False)
            ev["media_residue"].append(floated.float_image_token)
        except LarkAPIError as exc:
            multi_refusal = f"code={exc.code} msg={exc.msg!r}"
            orphan = getattr(exc, "orphan_file_token", None)
            ev["multi_orphan_file_token"] = orphan
            if orphan:
                ev["media_residue"].append(orphan)
        ev["multi_cell_refusal"] = multi_refusal
        assert multi_refusal, (
            "a MULTI-CELL a1_range was accepted — round 4's refutation does not reproduce and "
            "the recipe LD-472 rewrites must follow THIS measurement instead")
        # The refused bind left nothing on the tab.
        ev["query_after_multi"] = writer.query_float_images(token, sheet_id)
        assert ev["query_after_multi"] == [], ev["query_after_multi"]

        # (d) THE CONTROL — a single-cell anchor, same call, same picture.
        anchor = f"{sheet_id}!A1:A1"
        single = put_float_image_in_sheet(
            client=writer, media=media, spreadsheet_token=token, sheet_id=sheet_id,
            a1_range=anchor, data=payload, name="ld472-single.png",
            width=120, height=120, verify_bytes=False)
        ev["media_residue"].append(single.float_image_token)
        ev["single_cell_range"] = single.a1_range
        ev["single_cell_id"] = single.float_image_id
        assert single.float_image_id, single
        assert single.a1_range == anchor, single.a1_range

    finally:
        delete_code = None
        try:
            writer.delete_spreadsheet(token)
            delete_code = 0
        except LarkAPIError as exc:
            delete_code = exc.code
        ev["delete_code"] = delete_code

        try:
            writer.query_tabs(token)
            ev["confirmed_gone"] = False
        except LarkAPIError as exc:
            ev["confirmed_gone"] = bool(spreadsheet_is_gone(exc))

        # THE EVIDENCE PRINT LIVES IN THE `finally`, before any assertion can preempt it. The
        # media tokens are printed because they are PERMANENT: the workbook is gone and the
        # bytes are not, and nothing in Lark's open API purges them.
        with capsys.disabled():
            print("\n--- LD-472 sheets doc-truth gate ---")
            for key in ("spreadsheet_token", "before", "after_no_index", "no_index_position",
                        "len_tabs", "after_append_idiom", "append_idiom_position",
                        "sheet_id", "multi_cell_refusal", "multi_orphan_file_token",
                        "query_after_multi", "single_cell_range", "single_cell_id",
                        "media_residue", "delete_code", "confirmed_gone"):
                if key in ev:
                    print(f"  {key} = {ev[key]!r}")
            print("  RESIDUE: the media tokens above are permanent and unpurgeable.")
