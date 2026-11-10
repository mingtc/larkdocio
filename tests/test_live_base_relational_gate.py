"""THE BASE RELATIONAL GATE — the Base RELATIONAL round trip, live (LD-272).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Why this gate exists, in one sentence: `code:0` is not evidence.** Every honesty claim this
rung ships was *asserted* until something watched Lark do it — that a one-way link keeps pointing
at a record that no longer exists, that a two-way link quietly heals itself instead, that a link
column survives the deletion of the whole table it points at while a record search still answers
success, and that a file token really brings the same bytes back. This project has already been
burned by a write that answered ``code:0`` and moved nothing. So the four arms below are the
places where the ladder's claims stop being written down and start being watched.

**THE FOUR ARMS.**

1. **A hash-verified media round trip.** One generated file: upload → attach through the shipped
   encoder → read the cell back → download the token → compare **sha256**. Bytes are hashed,
   never inspected.
2. **The dangling arm — the most valuable one here.** A real two-table link is built and
   populated, a **target record is deleted**, and the source table is read with resolution ON:
   the ``SingleLink`` cell renders the dangling marker for the dead id, the ``DuplexLink`` cell
   has **self-healed**, and the read completes normally with ``1254043`` never raising.
3. **The column-level detector, live.** The **target table** is then deleted, and the source
   table is read again: the surviving link columns read as pointing at a table that is gone, a
   record search still answers ``code:0``, and the detector spends **zero extra calls** — it
   reads a schema the read already fetched. This is the aftermath
   ``larkdocio.base.loss_preview.INBOUND_LINK_DANGLES_SILENTLY`` warns about before the act; that
   warning has one owner and this arm points at it rather than restating it.
4. **Resolution off is byte-identical.** The same Base is read twice with resolution off and once
   with it on: the two off-reads match byte for byte, and the on-read differs in the link cells
   and nowhere else. Opt-in means opt-in.

**THIS ARM MINTS PERMANENT, UNSWEEPABLE RESIDUE, AND THAT WAS BOUGHT KNOWINGLY.** The upload
creates a ``file_token`` that **survives the deletion of the Base it was attached to**, and
**no open-API verb purges drive media at all** (``BASE.md`` register row 10). Exactly **one**
file is uploaded here — the smallest purchase that proves the claim — it is ledgered with its
``parent_type`` (``base_write_harness.attach_media``), there is deliberately **no cleanup leg**
here and there cannot be one, and the ``orphans() == []`` claim this repository's Base arms make
is stated against the **bitable** liveness definition with media residue explicitly **outside**
it.

**THE TARGET IS NEVER THE SCRATCH BASE, AND THAT IS TWO PARAMETERS RATHER THAN ONE.** A write
target is the obvious one; ``parent_node`` is the one a guard watching write targets alone would
miss, and its residue cannot be undone even by deleting the Base. Both go through the harness's
allow-list, which refuses every Base this run did not create — the configured one among them —
**without naming any of them**; this module reads no such variable, and the companion checks that
statically. Reading that Base is legitimate and other arms do it; **writing it is not**, and the
assertion below distinguishes the two.

**THE CREDENTIAL ALIASING RIDER.** On this tenant the READ and WRITE pairs **alias one app with
byte-identical secrets** (PROJECT.md § Credential aliasing). So a green run here proves the write
path works; it proves nothing whatever about the read path lacking write scope, and no conclusion
of that shape may be drawn from it.

**Gentle.** Around fifty calls on ONE disposable, every one through the same limiter the shipped
clients use (≥1.2 s). Rate limits are not probed and nothing is retried on one.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import hashlib
import json
import os
from pathlib import Path

import canary_support
import pytest
from lark_oapi.core.json import JSON

import base_write_harness
import capture_sink
from larkdocio.base import link_resolution as lr
from larkdocio.base import ops as base_ops
from larkdocio.base import referential
from larkdocio.base import write_ops
from larkdocio.base.client import BaseReadClient
from larkdocio.base.media import sha256_of, verify_round_trip
from larkdocio.base.read import DEFAULT_HEADING_LEVEL, read_base
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.table import field_spec, render_base
from larkdocio.base.write_cells import encode_cell
from larkdocio.base.write_client import BaseWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# Load the repo-root ``.env`` if there is one, exactly as the read arms do. Without this the
# gate inherits whichever sibling module happened to load it first, and run ALONE it raises a
# configuration error instead of skipping — which is the "never a silent pass" rule failing in
# the other direction. No variable naming a Base is read here; only the credential pair.
canary_support.load_env()

#: The capture this arm writes — states, ids, digests and counts. **No media bytes, no signed
#: links.**
CAPTURE = Path(__file__).resolve().parent.parent / "tests/captures/base-study/captures" \
    / "ld272-01-relational-round-trip.json"

#: The SECOND capture this arm writes (LD-480) — the **table-delete link semantics**, measured
#: per link kind, labelled with the route each observation was made on, and carrying the
#: 2026-08-05 reading it supersedes **verbatim, with its date**. The file above is a run output
#: that every run overwrites; this one is a dated record, and a git diff is not a record.
SEMANTICS_CAPTURE = CAPTURE.parent / "ld480-table-delete-link-semantics.json"

#: The two link columns this arm authors on the source table, and the target it builds for them.
ONE_WAY = "ld272-one-way"
TWO_WAY = "ld272-two-way"
TARGET_TABLE = "ld272-target"
ATTACHMENT_FIELD = "ld272-files"

#: **Every observation carries the route it was made on and never borrows a sibling's**
#: (``requirements/DECISIONS.md`` **D-59**). Colon-style, the spelling ``BASE.md`` and
#: :mod:`larkdocio.permissions` use.
ROUTE_TABLE_DELETE = "DELETE /open-apis/bitable/v1/apps/:app_token/tables/:table_id"
ROUTE_FIELDS_READ = "GET /open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields"
ROUTE_RECORDS_SEARCH = (
    "POST /open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search")
ROUTE_RECORD_DELETE = (
    "DELETE /open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/:record_id")

#: The route this gate does **NOT** measure and may not re-label from the one above. Deleting a
#: two-way link COLUMN was captured taking its twin with it (``p0-5-02``:
#: ``source_duplex_survived: false``); that is a **field**-route reading, it stands exactly as it
#: is, and no observation below is carried across to it.
ROUTE_FIELD_DELETE_NOT_MEASURED_HERE = (
    "DELETE /open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/:field_id")

#: LD-272's ``table_delete`` observation, quoted **verbatim** from
#: ``ld272-01-relational-round-trip.json`` as committed on **2026-08-05** — and **RE-MEASURED
#: UNCHANGED on 2026-08-14** (LD-480). Kept here because it is the reading this gate asserts and
#: because a *counter*-observation exists beside it; a reader has to be able to see both without
#: reading a git diff (``process/doctrine/supersession.md`` § A.1; the precedent shape is
#: ``BASE.md`` row 40 / LD-284 — **both observations are real**).
TABLE_DELETE_READING_2026_08_05 = {
    "one_way_survived": True,
    "two_way_survived": False,
    "link_columns_surviving": [ONE_WAY],
    "dangling_columns": [ONE_WAY],
    "states": {ONE_WAY: "target-table-missing"},
    "detector_extra_calls": 0,
    "records_search_still_answers": 11,
    "table_is_gone": True,
}

#: Why that reading was taken, preserved so a reader meets the argument rather than a bare value.
READING_REASON = (
    "LD-272 measured, on 2026-08-05, that a two-way link column pointing INTO a deleted table "
    "does NOT survive the table's deletion, while the one-way column does: the two-way column's "
    "mirror lives inside the doomed table, and deleting a mirror COLUMN had been captured taking "
    "its source column with it (p0-5-02, a DIFFERENT route). A measured asymmetry between the "
    "two link kinds is exactly the kind of fact a consumer plans around, so the gate asserts it.")

#: **THE COUNTER-OBSERVATION, ON THE RECORD RATHER THAN EXPLAINED AWAY.** One run — LD-455's QA
#: slice on 2026-08-14 — saw the two-way column SURVIVE, which is what LD-480 was filed on. The
#: re-measurement did not reproduce it, twice, and the one mechanism that would let both be true
#: was tested and refuted; but a real observation is not deleted because a later one disagreed.
COUNTER_OBSERVATION_2026_08_14 = (
    "ONE run disagreed. LD-455's QA slice on 2026-08-14 recorded two_way_survived TRUE — the "
    "two-way column surviving its target table's deletion and dangling — on a diff that touched "
    "no Base code (progress.md, entry '2026-08-14 QA review of LD-455': Base live_write slice 95 "
    "passed / 1 failed, this test the failure). LD-480 re-measured the SAME route twice on "
    "2026-08-14 and read FALSE both times: this gate's own re-run, and a media-free probe on an "
    "independently built shape (dev/base-study/probes/probe_ld480_table_delete_cascade_timing.py "
    "-> tests/captures/base-study/captures/ld480-02-table-delete-cascade-timing.json). The mechanism that "
    "would make both readings true — the source column's removal LAGGING the table delete, so "
    "that a fast enough field read still sees it — was tested directly and REFUTED within its "
    "own scope: the column was already absent 0.9 s after the delete and stayed absent at "
    "t+2/5/10/20/40 s, stable across the whole window, on a QUIET tenant. A busy tenant was not "
    "measured, so the refutation is scoped to the condition it was taken under.")

#: What would move the reading this gate asserts.
REVISIT_TRIGGER = (
    "A SECOND run in which the two-way column SURVIVES its target table's deletion moves this "
    "reading. One such observation exists already and did not reproduce; a second one makes "
    "intermittency the finding, and at that point this arm should assert what the LIBRARY does "
    "(every surviving link column reads dangling) and record Lark's cascade as unstable rather "
    "than assert either outcome. A one-way column that stops surviving, or a survivor still "
    "reporting a live target_table_name, moves it too.")

#: The one file this arm uploads. One, not four: every upload is permanent residue, so the arm
#: buys the smallest purchase that can carry a hash comparison.
PAYLOAD = (b"larkdocio relational gate, one hash-verified attachment", "ld272-file.txt",
           "bitable_file")


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def _rows(markdown):
    """``{heading: [ [cell, …], … ]}`` for every GFM table in a rendered Base."""
    out, heading = {}, None
    for line in markdown.split("\n"):
        if line.startswith("#"):
            heading = line.lstrip("# ").strip()
            out.setdefault(heading, [])
        elif line.startswith("|") and heading is not None:
            out[heading].append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def _cell_differences(left, right):
    """``[(heading, row index, column, left, right)]`` — every cell that is not identical."""
    diffs = []
    for heading, rows in _rows(left).items():
        other = _rows(right).get(heading, [])
        for index, row in enumerate(rows):
            mirror = other[index] if index < len(other) else []
            header = _rows(left)[heading][0] if rows else []
            for column, value in enumerate(row):
                seen = mirror[column] if column < len(mirror) else None
                if value != seen:
                    name = header[column] if column < len(header) else str(column)
                    diffs.append((heading, index, name, value, seen))
    return diffs


@pytest.fixture(scope="module")
def relational(credentials):
    """ONE disposable, one four-phase sequence, shared by every assertion below.

    A single fixture rather than four self-provisioning tests: the phases are **ordered in
    time** — a record must exist before it can be deleted, and a table must exist before its
    deletion can be observed — and every extra disposable is another Base the tenant's teardown
    lag can strand.
    """
    ledger = base_write_harness.Ledger()
    provisioner = base_write_harness._Provisioner()
    schema = BaseSchemaClient.from_write_credentials()
    write = BaseWriteClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    observed = {}

    with base_write_harness.disposable_base(provisioner=provisioner, ledger=ledger) \
            as (app_token, source_table_id, title):
        assert base_write_harness.is_disposable_title(title)

        # ---- build the two-table shape ------------------------------------ #
        target_table_id = schema.create_table(app_token, TARGET_TABLE, primary_field_name="Title")
        target_fields = read.list_fields(app_token, target_table_id)
        target_primary = lr.primary_field_name([field_spec(f) for f in target_fields])
        alpha = write.create_record(app_token, target_table_id,
                                    {target_primary: "ld272-alpha"})
        beta = write.create_record(app_token, target_table_id,
                                   {target_primary: "ld272-beta"})
        link_property = {"table_id": target_table_id, "multiple": True}
        schema.create_field(app_token, source_table_id, ONE_WAY, 18,
                            ui_type="SingleLink", properties=dict(link_property))
        schema.create_field(app_token, source_table_id, TWO_WAY, 21,
                            ui_type="DuplexLink", properties=dict(link_property))

        source_specs = {f.field_name: field_spec(f)
                        for f in read.list_fields(app_token, source_table_id)}
        both = [alpha.record_id, beta.record_id]
        source_record = write.create_record(app_token, source_table_id, {
            ONE_WAY: encode_cell(both, source_specs[ONE_WAY]),
            TWO_WAY: encode_cell(both, source_specs[TWO_WAY]),
        })

        # ---- ARM 4: resolution OFF is byte-identical, ON differs in the cells --- #
        off_first = render_base(read_base(app_token, client=read), DEFAULT_HEADING_LEVEL)
        off_second = render_base(read_base(app_token, client=read), DEFAULT_HEADING_LEVEL)
        resolved_read = read_base(app_token, client=read, resolve_links=True)
        on_markdown = render_base(resolved_read, DEFAULT_HEADING_LEVEL)
        observed["byte_identity"] = {
            "off_reads_identical": off_first == off_second,
            "off_bytes": len(off_first.encode("utf-8")),
            "differing_columns": sorted({
                name for _h, _i, name, _l, _r in _cell_differences(off_first, on_markdown)}),
            # Every link column in the WHOLE Base, derived from the read rather than listed:
            # creating the two-way link auto-created its MIRROR in the target table, and that
            # mirror is a link column too. The claim is "only link cells changed", so the set
            # it is checked against has to be the one the Base actually has.
            "link_columns": sorted({
                column.field_name for table in resolved_read.tables
                for column in table.link_columns}),
            "authored_link_columns": sorted([ONE_WAY, TWO_WAY]),
            "resolution_disclosed_calls": resolved_read.link_resolution.api_calls,
            "resolution_tables": list(resolved_read.link_resolution.tables),
        }

        # ---- ARM 1: the hash-verified media round trip --------------------- #
        payload, name, parent_type = PAYLOAD
        schema.create_field(app_token, source_table_id, ATTACHMENT_FIELD, 17,
                            ui_type="Attachment")
        uploaded = base_write_harness.attach_media(
            app_token, data=payload, name=name, parent_type=parent_type,
            provisioner=provisioner, ledger=ledger)
        attachment_spec = field_spec(
            [f for f in read.list_fields(app_token, source_table_id)
             if f.field_name == ATTACHMENT_FIELD][0])
        write.update_record(app_token, source_table_id, source_record.record_id,
                            {ATTACHMENT_FIELD: encode_cell([uploaded.file_token],
                                                           attachment_spec)})
        read_back = {r.record_id: r for r in read.search_records(app_token, source_table_id)}
        cell = read_back[source_record.record_id].fields[ATTACHMENT_FIELD]
        downloaded = provisioner.download_media(uploaded.file_token)
        observed["media"] = {
            "parent_type": uploaded.parent_type,
            "parent_node_is_the_disposable": uploaded.parent_node == app_token,
            "uploaded_sha256": uploaded.sha256,
            "downloaded_sha256": sha256_of(downloaded),
            "verified": verify_round_trip(uploaded, downloaded),
            "bytes": len(downloaded),
            "cell_tokens": sorted(item.get("file_token") for item in cell),
            "ledgered": uploaded.file_token in {e["file_token"] for e in ledger.media()},
        }

        # ---- ARM 2: delete a target RECORD; SingleLink dangles, DuplexLink heals - #
        write.delete_record(app_token, target_table_id, alpha.record_id)
        dangling_read = read_base(app_token, client=read, resolve_links=True)
        source_table = [t for t in dangling_read.tables if t.table_id == source_table_id][0]
        raw_after_record_delete = {
            r.record_id: r.fields
            for r in read.search_records(app_token, source_table_id)
        }
        raw_cells = raw_after_record_delete[source_record.record_id]
        resolution = dangling_read.link_resolution
        observed["record_delete"] = {
            "dead_record_id": alpha.record_id,
            "surviving_record_id": beta.record_id,
            "one_way_ids": sorted(lr._link_ids(raw_cells.get(ONE_WAY)) or ()),
            "two_way_ids": sorted(lr._link_ids(raw_cells.get(TWO_WAY)) or ()),
            "one_way_state": _state_of(resolution, target_table_id, alpha.record_id),
            "surviving_state": _state_of(resolution, target_table_id, beta.record_id),
            "one_way_rendered": _rendered(source_table, ONE_WAY, source_record.record_id),
            "two_way_rendered": _rendered(source_table, TWO_WAY, source_record.record_id),
            "dangling_marker": lr.dangling_marker(alpha.record_id),
            "read_completed": True,
        }

        # ---- ARM 3: delete the target TABLE; the column-level detector ------ #
        # The auto-created MIRROR is read BEFORE the delete, because afterwards the table it
        # lives in is gone and there is nothing left to ask. Its identity is an observation in
        # its own right: what moved on 2026-08-14 is the fate of the SOURCE column, not the
        # mirror's, and the two are only distinguishable if both were looked at.
        mirror = [field_spec(f) for f in read.list_fields(app_token, target_table_id)
                  if getattr(f, "type", None) == referential.DUPLEX_LINK[0]]
        schema.delete_table(app_token, target_table_id)
        fields_after = read.list_fields(app_token, source_table_id)
        raw_fields_after = {getattr(f, "field_name", ""): json.loads(JSON.marshal(f))
                            for f in fields_after}
        before_calls = read.api_calls
        detected = referential.dangling_link_columns(fields_after)
        surviving_links = referential.link_columns(fields_after)
        detector_calls = read.api_calls - before_calls
        records_after = read.search_records(app_token, source_table_id)
        observed["table_delete"] = {
            "deleted_table_id": target_table_id,
            "link_columns_surviving": [c.field_name for c in surviving_links],
            "dangling_columns": [c.field_name for c in detected],
            "states": {c.field_name: c.state for c in surviving_links},
            "one_way_survived": any(c.field_name == ONE_WAY for c in surviving_links),
            "two_way_survived": any(c.field_name == TWO_WAY for c in surviving_links),
            "detector_extra_calls": detector_calls,
            "records_search_still_answers": len(records_after),
            "table_is_gone": provisioner.table_is_gone(app_token, target_table_id),
        }

        # ---- LD-480: the same delete, measured PER LINK KIND and ROUTE-SCOPED --- #
        # Its own dict, not a key added to ``observed``: the file above is a run output every
        # run overwrites, and keeping this measurement out of it is what keeps that file's churn
        # to the one value that actually moved.
        by_name = {c.field_name: c for c in surviving_links}
        semantics = {
            "table_delete": {
                "_route": ROUTE_TABLE_DELETE,
                "deleted_table_id": target_table_id,
                "per_kind": {
                    ui: _kind_observation(by_name.get(name), raw_fields_after.get(name))
                    for ui, name in (("SingleLink", ONE_WAY), ("DuplexLink", TWO_WAY))
                },
                "mirror_column": {
                    "_route": ROUTE_TABLE_DELETE,
                    "field_names": sorted(spec.field_name for spec in mirror),
                    "lived_in_the_deleted_table": bool(mirror),
                    # The mirror's table is gone, so the mirror is gone with it — and its
                    # disappearance is NOT what happens to the source column, which is the
                    # whole thing that moved on this route.
                    "survives": False,
                    "note": ("the two-way link's mirror was auto-created INSIDE the target "
                             "table, so it went with the table — and so did the SOURCE column "
                             "in the other table. The one-way column, whose target had no "
                             "mirror of it, is the one that survives and dangles."),
                },
                "fields_read": {"_route": ROUTE_FIELDS_READ, "columns": len(fields_after)},
                "records_search": {
                    "_route": ROUTE_RECORDS_SEARCH,
                    # The shipped client RAISES on any non-zero code, so reaching this line is
                    # the proof of ``code:0`` — a status code nobody checked is not evidence.
                    "code": 0,
                    "records": len(records_after),
                },
                "detector_extra_calls": detector_calls,
                "table_is_gone": observed["table_delete"]["table_is_gone"],
            },
            "record_delete": {
                "_route": ROUTE_RECORD_DELETE,
                "one_way_still_holds_the_dead_id":
                    alpha.record_id in observed["record_delete"]["one_way_ids"],
                "two_way_self_healed":
                    alpha.record_id not in observed["record_delete"]["two_way_ids"],
                "one_way_state": observed["record_delete"]["one_way_state"],
                # Re-run and still green, which is what scopes the drift to the TABLE route
                # rather than to link handling in general.
                "unchanged_since": "2026-08-05",
            },
        }

        observed["targets"] = {
            "app_token": app_token,
            "write_targets": sorted({app_token}),
            "parent_nodes": sorted({uploaded.parent_node}),
        }

    capture_sink.write_capture(CAPTURE, json.dumps({
        "_issue": "LD-272",
        "_what": ("the Base relational round trip, live: a two-table link built and populated, "
                  "read with resolution off and on, a TARGET RECORD deleted (one-way dangles, "
                  "two-way self-heals), one attachment hash-verified, then the TARGET TABLE "
                  "deleted and the free column-level detector read off the schema the read "
                  "already had"),
        "_residue": ("the one file_token below is PERMANENT — no open-API verb purges drive "
                     "media. It is ledgered, not swept"),
        "_verdict": "OK",
        "observations": observed,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    # LD-480's own dated record, beside the run output rather than inside it.
    capture_sink.write_capture(SEMANTICS_CAPTURE, json.dumps({
        "_issue": "LD-480",
        "_measured_at": "2026-08-14",
        "_what": ("the TABLE-DELETE link semantics, re-measured per link kind: a SingleLink (18) "
                  "and a DuplexLink (21) pointing into the SAME target table, both populated, "
                  "the target table deleted, and the source table read back. Every observation "
                  "carries the route it was made on"),
        "_reconfirms": {
            "issue": "LD-272",
            "date": "2026-08-05",
            "capture": "dev/base-study/captures/ld272-01-relational-round-trip.json",
            "outcome": "re-measured 2026-08-14, UNCHANGED",
            "why_it_was_recorded": READING_REASON,
            "table_delete": TABLE_DELETE_READING_2026_08_05,
        },
        "_counter_observation": {
            "date": "2026-08-14",
            "issue": "LD-455 (QA slice)",
            "reading": "two_way_survived: true",
            "source": "progress.md, entry '2026-08-14 QA review of LD-455'",
            "reproduced_by_LD_480": False,
            "note": COUNTER_OBSERVATION_2026_08_14,
        },
        "_not_measured_here": {
            "route": ROUTE_FIELD_DELETE_NOT_MEASURED_HERE,
            "standing_reading": "p0-5-02: source_duplex_survived false",
            "note": ("deleting a two-way link COLUMN takes its twin with it. That is a "
                     "field-route reading, it is not re-measured here, and nothing in this "
                     "capture may be carried across to it (D-59)."),
        },
        "_revisit_trigger": REVISIT_TRIGGER,
        "_verdict": "OK",
        "observations": semantics,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    # Attached AFTER the run output is written, so the file above carries exactly what it always
    # carried and its only churn is the value that actually moved.
    observed["_semantics"] = semantics
    return observed


def _kind_observation(reading, payload):
    """One link kind's whole reading after its target table was deleted (LD-480).

    ``reading`` is the shipped detector's :class:`~larkdocio.base.referential.LinkColumn` for the
    surviving column, or ``None`` if the column did not survive at all; ``payload`` is the field
    list entry **as the API produced it**, marshalled back out of the SDK object rather than
    rebuilt by hand, so an offline twin can be pinned against a real shape (``PROJECT.md``
    § Quality bar — fixtures are deserialized from actual API JSON, never hand-mocked).
    """
    prop = (payload or {}).get("property") or {}
    return {
        "survived": reading is not None,
        "state": None if reading is None else reading.state,
        "field_type": None if reading is None else reading.field_type,
        "symmetric": None if reading is None else reading.symmetric,
        "target_table_id": None if reading is None else reading.target_table_id,
        # The detector's whole signature, spelled out rather than inferred from the state slug.
        "target_table_id_persists": bool(prop.get("table_id")),
        "target_table_name_present": "table_name" in prop and prop["table_name"] is not None,
        "field_payload": payload,
    }


def _rendered(table, column, record_id):
    """The rendered value of ``column`` in the row with ``record_id``.

    By id, never by position: a fresh Base's default table arrives carrying **three blank
    rows**, so ``rows[0]`` is somebody else's empty record and an arm that read it would assert
    happily against a blank cell.
    """
    names = [spec.field_name for spec in table.fields]
    index = names.index(column)
    for row in table.rows:
        if row.record_id == record_id:
            return row.cells[index]
    raise AssertionError(f"no row {record_id} in table {table.name}")


def _state_of(resolution, table_id, record_id):
    """The typed outcome for one linked id, or ``None`` when the resolution never saw it —
    which is itself a finding worth capturing rather than smoothing over."""
    entry = resolution.record_for(table_id, record_id)
    return None if entry is None else entry.state


# --------------------------------------------------------------------------- #
# the posture, asserted BEFORE the first call                                   #
# --------------------------------------------------------------------------- #

def test_the_registries_declare_this_arm_MUTATING_before_it_calls_anything():
    """The shape every Base arm ships. This gate writes and deletes, so the write registry is
    asserted mutating; the read registry still answers read-only about itself in the same breath,
    because the resolution half of this gate rides it."""
    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True


# --------------------------------------------------------------------------- #
# AC2 — the hash-verified media arm                                             #
# --------------------------------------------------------------------------- #

def test_the_attachment_round_trips_and_the_SHA256_IS_IDENTICAL(relational):
    """AC2. Upload → attach through the shipped encoder → read back → download → identical
    digest. The bytes are compared by hash and never inspected."""
    media = relational["media"]
    # ``verify_round_trip`` RAISES on a mismatch and returns the digest the two share, so
    # reaching this line at all is half the proof and the equality is the other half.
    assert media["verified"] == media["uploaded_sha256"] == media["downloaded_sha256"]
    assert media["bytes"] == len(PAYLOAD[0])
    assert media["cell_tokens"], "the attachment cell read back empty"


def test_the_minted_token_is_LEDGERED_as_permanent_residue(relational):
    """AC2's other half. The residue is disclosed, not swept: there is no delete leg here
    because there is no verb that would back one."""
    assert relational["media"]["ledgered"] is True
    assert base_write_harness.media_residue(), "this arm minted media; the ledger must say so"


# --------------------------------------------------------------------------- #
# AC3 — the live dangling arm                                                   #
# --------------------------------------------------------------------------- #

def test_the_SINGLE_LINK_still_points_at_the_DELETED_record(relational):
    """AC3(i), and the reason the whole honesty posture exists. Lark does **not** clean a
    one-way link up: the dead id is still in the cell, and the resolution types it as dangling
    and renders the marker rather than an id that looks like data."""
    arm = relational["record_delete"]
    assert arm["dead_record_id"] in arm["one_way_ids"], (
        "the one-way link no longer holds the deleted id — if Lark started maintaining it, this "
        "library's dangling policy is describing a behaviour that has changed")
    assert arm["one_way_state"] == lr.LINK_DANGLING, arm["one_way_state"]
    assert arm["dangling_marker"] in arm["one_way_rendered"], arm["one_way_rendered"]


def test_the_DUPLEX_LINK_SELF_HEALED(relational):
    """AC3(ii). The symmetric link is the one Lark maintains: the deleted id is gone from the
    cell without anybody writing to it, so the pair of columns really do behave differently and
    the register's row 35 is a live fact rather than a capture."""
    arm = relational["record_delete"]
    assert arm["dead_record_id"] not in arm["two_way_ids"], (
        "the two-way link kept a deleted id — the self-healing half of the claim has stopped "
        "being true")
    assert arm["two_way_ids"] in ([], [arm["surviving_record_id"]]), arm["two_way_ids"]


def test_the_read_COMPLETED_and_1254043_NEVER_RAISED(relational):
    """AC3(iii). A dangling link is a **normal outcome**, not an error: the whole read finished,
    the surviving link resolved, and the not-found code never reached the caller as an
    exception."""
    arm = relational["record_delete"]
    assert arm["read_completed"] is True
    assert arm["surviving_state"] == lr.LINK_RESOLVED, arm["surviving_state"]
    assert lr.RECORD_ID_NOT_FOUND_CODE == 1254043


# --------------------------------------------------------------------------- #
# AC4 — the column-level detector, live                                         #
# --------------------------------------------------------------------------- #

def test_after_the_TARGET_TABLE_is_deleted_the_column_reads_as_DANGLING(relational):
    """AC4. Deleting the whole target table leaves the source column pointing at it, and the
    only free evidence is the target table's **name** dropping out of the column's own
    configuration. Every surviving link column must read that way — a survivor still reporting
    a live target would mean the signature has changed.

    **THE TWO LINK KINDS SPLIT ON THIS ROUTE, AND THAT IS RE-MEASURED RATHER THAN INHERITED.**
    On the route ``DELETE /open-apis/bitable/v1/apps/:app_token/tables/:table_id`` the inbound
    one-way column **survives and dangles** while the inbound two-way column is **destroyed
    along with its twin's table** — measured **2026-08-05** (LD-272,
    :data:`TABLE_DELETE_READING_2026_08_05`, reason in :data:`READING_REASON`) and
    **re-measured unchanged 2026-08-14** (LD-480, per link kind, with the field payloads, in
    ``tests/captures/base-study/captures/ld480-table-delete-link-semantics.json``).

    **THE COUNTER-OBSERVATION IS ON THE RECORD, NOT EXPLAINED AWAY** —
    :data:`COUNTER_OBSERVATION_2026_08_14`. One run (LD-455's QA, 2026-08-14) read
    ``two_way_survived: true``; LD-480 re-measured twice and read ``false`` both times, and the
    cascade-lag mechanism that would let both be true was tested and refuted within a 40 s window
    on a quiet tenant. Two real observations disagree and **both stay on the record**.

    **``p0-5-02`` IS A DIFFERENT ROUTE AND IS NOT RE-LABELLED FROM HERE (D-59).** Its
    ``source_duplex_survived: false`` was measured on ``DELETE …/fields/:field_id`` — deleting a
    two-way *column* takes its twin — and nothing measured here is carried across to it.

    **REVISIT TRIGGER:** see :data:`REVISIT_TRIGGER`.
    """
    arm = relational["table_delete"]
    assert arm["table_is_gone"] is True, "the target table did not actually go away"
    assert arm["one_way_survived"] is True, (
        "the ONE-WAY column did not survive its target table's deletion — the silent-dangle "
        "shape this reading exists for has changed")
    assert arm["two_way_survived"] is False, (
        "the TWO-WAY column SURVIVED its target table's deletion. That is the counter-observation "
        "LD-480 was filed on, seen once on 2026-08-14 and NOT reproduced by two re-measurements "
        "the same day (nor by the cascade-lag probe, which found the column already absent 0.9 s "
        f"after the delete and still absent at t+40 s). {REVISIT_TRIGGER} Do NOT relax this "
        "assertion: re-measure it, date the reading, and correct the prose in the same change")
    assert arm["dangling_columns"] == arm["link_columns_surviving"], arm
    assert set(arm["states"].values()) == {referential.TARGET_TABLE_MISSING}, arm["states"]
    assert arm["link_columns_surviving"] == [ONE_WAY], (
        "the ONE-WAY column is the only inbound link expected to survive this route; the "
        "two-way column goes with its twin's table")


def test_the_TWO_LINK_KINDS_SPLIT_on_the_TABLE_DELETE_route_PER_KIND(relational):
    """LD-480, the measurement this issue exists to take, **per link kind and route-scoped
    (D-59)**: everything below was observed on ``DELETE …/tables/:table_id`` and on the two reads
    that follow it, and none of it is carried across to ``DELETE …/fields/:field_id`` — where the
    standing ``p0-5-02`` reading (deleting a two-way *column* takes its twin) is left exactly as
    it is.

    The **one-way** column survives with the detector's whole signature — ``property.table_id``
    persists, ``property.table_name`` drops out — and the **two-way** column does not survive at
    all: its twin lived inside the doomed table and the source column went with it. The record
    search still answers ``code:0`` either way, which is the silence the loss preview warns about
    **before** the act.

    The record-delete arm above is re-run and still green, which is what scopes this reading to
    the table route rather than to link handling in general.
    """
    arm = relational["_semantics"]["table_delete"]
    assert arm["_route"] == ROUTE_TABLE_DELETE
    single = arm["per_kind"]["SingleLink"]
    assert single["survived"] is True
    assert single["state"] == referential.TARGET_TABLE_MISSING, single["state"]
    # The detector's whole signature: the id persists, the name drops out.
    assert single["target_table_id"] == arm["deleted_table_id"]
    assert single["target_table_id_persists"] is True
    assert single["target_table_name_present"] is False
    assert single["symmetric"] is False
    assert single["field_payload"], "no field payload to pin an offline twin against"

    duplex = arm["per_kind"]["DuplexLink"]
    assert duplex["survived"] is False, (
        "the inbound TWO-WAY column survived — see the counter-observation on this arm's "
        f"sibling assertion. {REVISIT_TRIGGER}")
    assert duplex["field_payload"] is None
    # The mirror lived inside the doomed table and went with it, and the SOURCE column went too:
    # the two are only distinguishable because both were looked at.
    assert arm["mirror_column"]["lived_in_the_deleted_table"] is True
    assert arm["records_search"]["code"] == 0
    assert relational["_semantics"]["record_delete"]["two_way_self_healed"] is True


def test_the_detector_made_ZERO_EXTRA_CALLS_and_the_search_still_answers(relational):
    """AC4's other two halves. The reading is free — it comes off a schema the read already
    fetched — and the aftermath is exactly what the loss preview warned about **before** the
    act: nothing anywhere reports an error, and ``records/search`` still answers success."""
    arm = relational["table_delete"]
    assert arm["detector_extra_calls"] == 0, (
        f"the column-level detector spent {arm['detector_extra_calls']} call(s); it is supposed "
        "to read a schema that is already in hand")
    assert arm["records_search_still_answers"] >= 1, (
        "the source table stopped answering after its link target was deleted")


# --------------------------------------------------------------------------- #
# AC5 — resolution off is byte-identical                                        #
# --------------------------------------------------------------------------- #

def test_resolution_OFF_is_BYTE_IDENTICAL_and_ON_differs_ONLY_in_the_link_cells(relational):
    """AC5. Two back-to-back reads with resolution off match byte for byte (same-run
    determinism), and switching it on changes **link cells and nothing else**. An opt-in that
    quietly reshaped a neighbouring cell would not be opt-in.

    The set it is checked against is **derived from the Base**, not listed: creating the
    two-way link auto-created its mirror in the target table, and that mirror is a link column
    that resolves too. A hard-coded pair would have called a correct resolution a failure.
    """
    arm = relational["byte_identity"]
    assert arm["off_reads_identical"] is True
    differing, links = set(arm["differing_columns"]), set(arm["link_columns"])
    assert differing <= links, (
        f"resolution changed a cell that is not in a link column: {sorted(differing - links)}")
    assert set(arm["authored_link_columns"]) <= differing, (
        "one of the two link columns this arm authored did not change at all, so the on-read "
        "proved nothing about it")


def test_the_resolution_DISCLOSES_what_it_cost(relational):
    """AC5's price tag. The cost is batched per **target table**, so one target table is one
    extra read however many cells pointed at it — and the number is published rather than
    guessed at by the caller."""
    arm = relational["byte_identity"]
    assert arm["resolution_disclosed_calls"] >= 1
    assert len(arm["resolution_tables"]) == arm["resolution_disclosed_calls"], arm


# --------------------------------------------------------------------------- #
# AC6 / AC7 — the fence and the credential rider                                #
# --------------------------------------------------------------------------- #

def test_NEITHER_a_write_target_NOR_a_parent_node_is_EVER_the_configured_base(relational):
    """AC6, as one assertion over **two** parameters and no exception. A write target is the
    obvious one; ``parent_node`` is the one a guard watching write targets alone would miss, and
    its residue survives the Base's deletion. Reading the configured Base is legitimate — other
    arms do exactly that — and this checks the thing that is not: addressing it as a destination.
    """
    configured = {value for key, value in os.environ.items()
                  if key.startswith("LARKDOCIO_SCRATCH") and value}
    targets = relational["targets"]
    for token in list(targets["write_targets"]) + list(targets["parent_nodes"]):
        assert token not in configured
        assert not any(token and token in value for value in configured)


def test_the_arm_reports_its_MEDIA_RESIDUE_and_its_base_orphans_SEPARATELY(relational):
    """AC6's ledger half. ``orphans() == []`` is a claim about **bitable** objects; the media
    list is a different question and is reported beside it, never instead of it."""
    residue = base_write_harness.media_residue()
    orphans = base_write_harness.orphans()
    print(f"LD-272 media residue (PERMANENT, unsweepable): "
          f"{[e['file_token'] for e in residue]}")
    print(f"LD-272 bitable orphans (a DIFFERENT question): {orphans}")
    assert isinstance(orphans, list)


def test_the_capture_carries_no_media_bytes_and_no_signed_link(relational):
    """The standing rule for binary artifacts, checked on the artifact this arm commits."""
    blob = capture_sink.destination_for(CAPTURE).read_text(encoding="utf-8")
    assert "tmp_url" not in blob and "http" not in blob
    assert hashlib.sha256(PAYLOAD[0]).hexdigest() in blob, (
        "the capture should carry the digest — that is what makes it re-checkable")
    # Both captures, same rule. The LD-480 one carries field payloads and route strings only.
    semantics = capture_sink.destination_for(SEMANTICS_CAPTURE).read_text(encoding="utf-8")
    assert "tmp_url" not in semantics and "http" not in semantics
