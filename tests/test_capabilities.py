"""Tests for ``larkdocio.capabilities()`` — the typed, JSON-serializable capability
registry PROJECTED over the op registries + drift-guarded (LD-127).

``capabilities()`` is a **projection**, not a hand-list: its operations come from
``larkdocio.write.ops.OPS`` (docx write) + ``larkdocio.sheets.ops.OPS`` (sheets write)
+ the read clients' introspected public ops. This module is the **bidirectional drift
guard** (the SHEETS.md / BLOCKS.md guard pattern): every enumerated operation resolves
to a real symbol, and every ``OPS`` entry appears in ``capabilities()``. If the code
grows/loses an op without the projection following, this suite reddens — the projection
cannot silently drift from code truth.
"""
import inspect
import json
import pathlib

import pytest

import capability_rows as rows
import larkdocio
from larkdocio import capabilities
from larkdocio import __version__
from larkdocio.common.auth import READ_ENV, LEGACY_ENV, WRITE_ENV
from larkdocio.read.client import Client as DocxReadClient
from larkdocio.read.parser import Parser as DocxParser
from larkdocio.comments.client import CommentsReadClient
from larkdocio.model import projection as ModelProjection
from larkdocio.model import tree as ModelTree
from larkdocio import snapshot as SnapshotModule
from larkdocio.sheets.client import SheetsReadClient
import larkdocio.sheets.read as SheetsReadModule
from larkdocio.write.ops import OPS as DOCX_WRITE_OPS
from larkdocio.sheets.ops import OPS as SHEETS_WRITE_OPS


# --------------------------------------------------------------------------- #
# Shared helpers — the code-truth sources the projection is guarded against.   #
# --------------------------------------------------------------------------- #

def _public_ops(cls) -> set:
    """Public (non-underscore, non-classmethod/staticmethod) method names on ``cls``
    — the SHEETS.md guard's ``_shipped_read_ops`` shape, reused so the read-op
    projection is checked against the exact same notion of a client's public op."""
    ops = set()
    for name, member in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        raw = cls.__dict__.get(name)
        if isinstance(raw, (classmethod, staticmethod)):
            continue
        if inspect.isfunction(member) or inspect.ismethod(member):
            ops.add(name)
    return ops


def _phantom_and_missing(documented, truth):
    """THE bidirectional drift check (used by the guard tests AND the red-then-green
    bite test, so the check that guards is provably the check that bites).

    Returns ``(phantom, missing)`` — the ops the projection claims that code truth
    does not have, and the ops code truth has that the projection dropped. Both empty
    ⇒ the projection agrees with code truth in both directions.
    """
    d, t = set(documented), set(truth)
    return sorted(d - t), sorted(t - d)


def _op_names(surface_dict):
    """The names of the surface's DISPATCHED operations — the ``operation`` kind.

    LD-475 put every call site under one key, each row carrying its ``kind``, so "the op
    registry's own list" is a filter on the kind rather than a read of a sibling key. Every
    assertion here that meant *the dispatched ops* still means exactly that.
    """
    return rows.names(surface_dict, rows.OPERATION)


#: ``projected_from`` string → the class the projection claims to have read (LD-133). Used
#: to resolve every enumerated op against ITS OWN declared source, so an op cannot be
#: attributed to a class that does not have it, and an unknown source is a hard failure.
_PROJECTION_SOURCES = {
    "larkdocio.read.client.Client": DocxReadClient,
    "larkdocio.read.parser.Parser": DocxParser,
    "larkdocio.sheets.client.SheetsReadClient": SheetsReadClient,
    # not a client either: the sheets walk's URL-first front door (LD-405), the composed
    # entry point a consumer holding a link actually calls.
    "larkdocio.sheets.read": SheetsReadModule,
    "larkdocio.comments.client.CommentsReadClient": CommentsReadClient,
    # not a client: the two tree-reading helpers a caller needs once they have the tree.
    "larkdocio.model.tree": ModelTree,
    # nor a client: the opt-in block-identity projection, which re-renders a tree the
    # caller already holds and reaches no endpoint.
    "larkdocio.model.projection": ModelProjection,
    # nor a client, and the only one whose subject is a FILE: the persistence seam that
    # keeps a read on disk and rehydrates it. Offline end to end — it reaches no endpoint.
    "larkdocio.snapshot": SnapshotModule,
}


# The guard's spec: each surface's operations projection ↔ its code-truth source.
def _truth_for(surface_id):
    if surface_id == "docx-write":
        return {d.kind for d in DOCX_WRITE_OPS}
    if surface_id == "sheets-write":
        return {d.kind for d in SHEETS_WRITE_OPS}
    if surface_id == "docx-read":
        # The client fetches blocks; the Parser turns them into Markdown or into the node
        # tree the writer anchors against (LD-133 / dogfood F13 — the parser leg was
        # missing, so `parse_docx_tree` was discoverable in neither discovery surface).
        # PLUS the two tree-reading helpers a caller needs once they hold that tree
        # (LD-171): reaching the tree and then losing its table cells to a hand-rolled walk
        # was the whole defect, so the functions that do it right are part of the surface.
        # PLUS the block-identity projection, the one entry point that turns that
        # tree into editable Markdown; the module's other exports are its inverse and
        # its marker form rather than operations of the surface, so it is named.
        # PLUS the file-first persistence seam (LD-444): the two verbs that keep a read
        # across processes and bring it back byte-identically. Named the same way
        # ``project_block_ids`` is — the module's other exports are its format version,
        # its refusal type and its result container rather than operations of the surface.
        return (
            _public_ops(DocxReadClient)
            | _public_ops(DocxParser)
            | set(ModelTree.__all__)
            | {"project_block_ids"}
            | {"snapshot", "load"}
        )
    if surface_id == "sheets-read":
        # The client's read ops PLUS the composed Markdown entry point (LD-405), named the
        # way docx-read names `project_block_ids`: it is not a client method, and its
        # structured partner `read_spreadsheet` is deliberately NOT a second row — it
        # composes the client method of the same name, which is already here.
        return _public_ops(SheetsReadClient) | {"read_spreadsheet_markdown"}
    if surface_id == "docx-comments-read":
        # The client's read ops PLUS the one composed entry point a consumer actually calls
        # (``comments``, which joins the list/batch legs to a parsed document's own anchors).
        # The composed op is not a client method, so it is enumerated here the way the
        # embedded deep-read bridge's composed op is.
        return _public_ops(CommentsReadClient) | {"comments"}
    raise AssertionError(f"no code-truth source for surface {surface_id!r}")


_EXPECTED_SURFACES = {
    "docx-read",
    "docx-comments-read",
    "contacts-read",
    # LD-327 — the Drive spec § F1-S5 published the Drive folder-read surface, the THIRTEENTH: a
    # read-only enumeration of a folder tree whose three endpoint families all land as
    # recorded-unknown scope rows (no drive scope has ever been observed demanded). Reading the
    # documents inside rides the docx / Sheets / Base read surfaces already here.
    "drive-read",
    # LD-409 — the FOURTEENTH surface, and the Drive family's first mutating one: creating a
    # NAMED VERSION of a file, on the WRITE pair, returning the new token paired with the head
    # revision read immediately before it. A surface of its own rather than an operation on
    # `drive-read` because a surface carries ONE mode and ONE credential pair — a write filed
    # under a read surface would publish "this needs read credentials". Its scope rows are
    # recorded-unknown for the same reason every other Drive row is.
    "drive-versions-write",
    # LD-432 — the FIFTEENTH surface, and the Drive family's second mutating one: WHO may use a
    # docx the app created. Grant / raise / lower / revoke one human's member level, read the
    # members WITH the owner (the owner is not a member row), and move the two document
    # settings whose names govern copying. Its own surface for the same reason the versions one
    # is, and its scope rows are recorded-unknown like every other Drive row.
    "drive-access-write",
    "drive-files-write",
    # LD-467 — the Drive family's fourth mutating surface, and the ONE rung of the organize
    # ladder a product ruling (2026-08-14) opened: create a folder under a parent. Its own
    # surface for the reason every Drive write is, and it carries exactly one operation —
    # no move, rename, copy, shortcut or folder delete ships, deliberately. Its scope row is
    # recorded-unknown like every other Drive row.
    "drive-folders-write",
    "docx-write",
    "sheets-read",
    "sheets-write",
    "sheets-embedded-deep-read",
    # LD-251 — the Base front-door close-out published the three READ surfaces the Base ladder
    # built: the standalone read, its comments read (the shipped comments client with a third
    # accepted file type) and the opt-in embedded-Base bridge. All three are read-only.
    "base-read",
    "base-comments-read",
    "base-embedded-deep-read",
    # LD-260 — THE BASE WRITE GATE published the fourth Base surface, and the first that is not
    # read-only: the plan-gated RECORD write engine. It writes rows and it does NOT write
    # schema — the rows, not the shape.
    "base-write",
    # LD-266 — THE BASE SCHEMA GATE published the fifth Base surface, and the second that writes:
    # the plan-gated SCHEMA engine. Columns across the server-declared allow-list, tables,
    # views carrying a persistent filter, and a destructive family behind a Base-wide loss
    # preview and a consent token minted from its own plan.
    "base-schema-write",
}


# --------------------------------------------------------------------------- #
# AC1 — capabilities() exists, is typed + JSON-serializable, round-trips.       #
# --------------------------------------------------------------------------- #

def test_capabilities_is_public_callable_returning_a_dict():
    """AC1: ``larkdocio.capabilities()`` is a public callable returning a dict."""
    assert callable(larkdocio.capabilities)
    caps = capabilities(full=True)
    assert isinstance(caps, dict)


def test_capabilities_json_round_trips_losslessly():
    """AC1: the structure round-trips via ``json.dumps``/``loads`` losslessly (no
    tuples / sets / non-JSON types leak — a tuple would fail ``== `` after a round-trip)."""
    caps = capabilities(full=True)
    assert json.loads(json.dumps(caps)) == caps


def test_capabilities_top_level_shape():
    """AC1: the top level enumerates version + surfaces + flags + safety contracts."""
    caps = capabilities(full=True)
    assert caps["version"] == __version__
    assert set(caps["surfaces"]) == _EXPECTED_SURFACES
    assert set(caps["flags"]) == {
        # LD-173 (dogfood F3) — the read knob that changes what a read RETURNS and had
        # no row here at all, which is why it was undiscoverable: it is ON by default.
        "resolve_mentions",
        "deep_read_sheets", "fidelity_read_sheets", "verify_style",
        # LD-251 — the Base deep-read knob. LD-340 AMENDED it into a CLI flag
        # (--deep-read-bases), so its row's mode is now "cli"; it stays discoverable here.
        "deep_read_bases",
        # LD-269 — the Base link-resolution knob, the same shape and for the same reason: a
        # read argument that changes what a read RETURNS, so it is discoverable here or not
        # at all (the LD-173 lesson, applied at birth this time).
        "resolve_base_links",
        # LD-293 — the Base RAW-value knob, declared for the same reason once more: it
        # changes what a read HANDS BACK (a second artefact beside the rendered cells) and
        # it is the one knob here that costs measurable memory, so a consumer must be able
        # to find it and its price without reading the source.
        "retain_base_raw_values",
        # LD-386 — the folder-scale asset fetch. Declared here for the same reason and one
        # more: it is the only knob whose cost is a whole FOLDER's binaries, and its LAYOUT
        # (one shared token-named pool, collisions impossible by construction) is a decision
        # a consumer has to be able to look up rather than discover on disk.
        "folder_assets",
    }
    assert set(caps["safety_contracts"]) == {
        "plan-gated", "dry-run-mandatory", "STALE_SHEET", "STALE_ANCHOR",
        # LD-139 (the Markdown-authoring spec § D9) — the docx whole-document compare-and-swap, the sibling of
        # STALE_ANCHOR that sees drift AROUND an anchor.
        "STALE_DOCUMENT",
        "exactly-one-or-refuse",
        # LD-200 (backlog K legs 3+4) — the CROSS-CUTTING one: a scope denial is a distinct
        # typed permission error on every surface, never folded into not-found/unavailable,
        # and the success-with-empty-governed-fields case is classified too. It is the only
        # contract that applies to READ surfaces as well. Nothing can prove it live without
        # revoking a scope; it is proved offline against captured denial bodies instead. That
        # reason once kept it out of docx-write's own list; since LD-707 every surface's list
        # is derived from the catalogue's applies_to, so it is listed there and the live-proof
        # guard below exempts it by name, for that same reason.
        "permission-denial-is-never-an-absence",
        # LD-148 (dogfood round-2 T27) — the sheets disposition / apply-log completeness
        # invariant: no exception escapes apply(), every entry ends in a typed logged
        # disposition, and the plan-time @mention id check is never silently skipped.
        "apply-log-complete",
        # LD-151 (dogfood F14) — the docx batch-semantics contract: one tree, one batch, so a
        # batch cannot depend on its own writes; commit the insert, then anchor follow-ups by
        # created_block_ids (and the not-found detail says so for the intra-batch case).
        "one-tree-one-batch",
        # LD-172 (round-3, the re-scoped F8) — the three-path reviewer-anchor contract:
        # sub-span re-emits, whole-block and whole-cell refuse, and the plan discloses an
        # anchored target on the path that proceeds.
        "comment-anchors-honored-or-refused",
        # LD-202 — the two comment WRITE contracts. Note how they sit against the one above:
        # that contract is about editing text reviewers have commented ON; these are about
        # creating and removing the comments themselves.
        "comment-create-whole-document-only",
        "comment-removal-sole-author-or-refuse",
        # LD-432 — the Drive access surface's contract, and the first one whose subject is the
        # difference between ACCEPTED and STORED: the family was measured swallowing a write,
        # so every op reads its own work back and an accepted-but-unstored call reports
        # stored=False rather than success.
        "read-back-is-the-verdict",
        # LD-260 — the Base record-write engine's staleness guard. A CLIENT-SIDE
        # read-compare-write on table.revision (this API has no If-Match), whose halt scope is
        # per-table because the anchor is.
        "STALE_BASE",
        # LD-266 — the three the Base SCHEMA engine is the first to need. The last of them is
        # the one that matters most: it states where the compare-and-swap applies and, just as
        # loudly, where it does NOT, rather than letting a caller assume a uniform guard.
        "destructive-consent-required",
        "cross-table-loss-preview",
        "revision-guard-field-scoped-only",
        # LD-410 — the first contract a READ surface declares: the docx historical read
        # rides the route its pin was MEASURED on, and the two routes that accept the pin
        # and discard it are named rather than left to be discovered.
        "historical-read-rides-the-measured-route",
        # LD-444 — the second READ-surface contract, and the first about an artefact on
        # DISK: a persisted read rehydrates byte-identically or is refused typed (naming
        # re-download), the checksum answers accidental corruption and nothing else, and the
        # snapshot stays immutable with reconcile() as the only boundary.
        "snapshot-integrity-refusal",
        # LD-493 — the caller-supplied-destination rule, and the first contract whose subject
        # is WHERE a new object goes: every create-class verb that makes a new top-level
        # object refuses locally when no destination is named, on every spelling including the
        # empty string, because the default landing place is a space no human interface can
        # browse and where a delete is a trash rather than a purge.
        "caller-supplied-destination",
        # LD-645 — the two that stop the OTHER non-plan-gated Drive legs answering the
        # verification question with silence: the file leg carries the strongest
        # verification in the package (a sha256 + length round trip) and used to declare
        # only where the object goes, and the versions leg declared nothing at all while
        # reading a revision BEFORE its write. Two opposite facts had one answer.
        "bytes-verified-round-trip",
        "version-pairing-is-not-a-verdict",
    }


# --------------------------------------------------------------------------- #
# AC2 — operations are PROJECTED (with projected metadata), not hand-listed.    #
# --------------------------------------------------------------------------- #

def test_sheets_write_op_carries_projected_registry_metadata():
    """AC2: a representative sheets-write op appears with its PROJECTED descriptor
    metadata (kind / write_kind / entry_ops / request_types) straight off ``sheets/ops/``."""
    ops = {op["name"]: op for op in capabilities(full=True)["surfaces"]["sheets-write"]["operations"]}
    value = ops["value"]
    assert value["projected_from"] == "larkdocio.sheets.ops.OPS"
    assert value["write_kind"] == "value"
    assert value["entry_ops"] == []
    assert "ValueWriteRequest" in value["request_types"]

    structural = ops["structural"]
    assert structural["write_kind"] == "structure"
    assert "insert" in structural["entry_ops"] and "delete" in structural["entry_ops"]


def test_docx_write_op_carries_projected_registry_metadata():
    """AC2: a representative docx-write op is projected off ``write/ops.py`` with its
    request type."""
    ops = {op["name"]: op for op in capabilities(full=True)["surfaces"]["docx-write"]["operations"]}
    insert = ops["insert"]
    assert insert["projected_from"] == "larkdocio.write.ops.OPS"
    assert insert["request_types"] == ["InsertRequest"]


def test_docx_write_content_constraints_are_projected_not_hand_listed():
    """AC2 (LD-133): the docx-write **creatable-content floor** is a projection over
    ``write/`` code truth — ``creatable`` from the content types of
    ``InsertRequest.content`` and ``creatable_content_fields`` from their dataclass fields
    — so the projection cannot advertise a richer creatable surface than the model accepts
    (dogfood F14). LD-134 widened that annotation to a ``Union``, which the projection
    flattens; the assertion below re-derives from the annotation, so it tracks the code
    rather than pinning a snapshot."""
    import dataclasses
    import typing

    from larkdocio.capabilities import _flatten_content_types
    from larkdocio.write.model import InsertRequest

    cc = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    types = _flatten_content_types(typing.get_type_hints(InsertRequest)["content"])
    assert types, "the content annotation must project at least one creatable type"
    assert cc["creatable"] == sorted(t.__name__ for t in types)
    expected_fields = []
    for cls in sorted(types, key=lambda c: c.__name__):
        for f in dataclasses.fields(cls):
            if f.name not in expected_fields:
                expected_fields.append(f.name)
    assert cc["creatable_content_fields"] == expected_fields
    assert cc["projected_from"] == "larkdocio.write.model.InsertRequest.content"
    # the F9 nuance is carried, and cannot overlap the creatable set.
    assert cc["editable_not_creatable"]
    assert not set(cc["editable_not_creatable"]) & set(cc["creatable"])
    assert not set(cc["not_creatable"]) & set(cc["creatable"])


def test_both_write_surfaces_project_their_file_lifecycle_calls():
    """LD-176 AC3: ALL FOUR lifecycle calls are discoverable HERE.

    ``create_document`` / ``delete_document`` shipped well-docstringed and appeared **0 times**
    in this registry: the round-3 dogfood seat found them with ``dir()``. The sheets twins did
    not exist at all, so a consumer following the guide's whole section on working against
    disposables had to leave the library for raw HTTP. A lifecycle call is not a plan-gated
    write op — it brings the FILE into existence or destroys it — so it carries its own
    ``kind`` rather than being an indistinguishable ``operations`` row. (LD-475: the
    distinction moved from a sibling KEY, which varied per surface and which no shipped
    document defined, onto the row itself, where it travels with a row a consumer copied.)
    """
    surfaces = capabilities(full=True)["surfaces"]
    projected = {
        sid: rows.names(surfaces[sid], rows.LIFECYCLE)
        for sid in ("docx-write", "sheets-write")
    }
    assert projected["docx-write"] == ["create_document", "delete_document"]
    assert projected["sheets-write"] == ["create_spreadsheet", "delete_spreadsheet"]


def test_the_lifecycle_projection_matches_the_clients_own_tables_bidirectionally():
    """LD-176 AC3: the lifecycle list is PROJECTED off the table that sits beside the methods
    (``LIFECYCLE_OPS``), and every row resolves to a real method on the class it names — so a
    rename cannot leave a phantom row, and a third lifecycle call cannot ship undiscoverable."""
    from larkdocio.sheets.write_client import (
        LIFECYCLE_OPS as SHEETS_LIFECYCLE,
        SheetsWriteClient,
    )
    from larkdocio.write.client import LIFECYCLE_OPS as DOCX_LIFECYCLE, WriteClient

    surfaces = capabilities(full=True)["surfaces"]
    truth = {
        "docx-write": (DOCX_LIFECYCLE, WriteClient, "larkdocio.write.client.WriteClient"),
        "sheets-write": (SHEETS_LIFECYCLE, SheetsWriteClient,
                         "larkdocio.sheets.write_client.SheetsWriteClient"),
    }
    for sid, (ops, cls, projected_from) in truth.items():
        documented = rows.names(surfaces[sid], rows.LIFECYCLE)
        phantom, missing = _phantom_and_missing(documented, ops)
        assert not phantom, f"{sid}: lifecycle claims calls the client lacks: {phantom}"
        assert not missing, f"{sid}: the client has lifecycle calls the registry drops: {missing}"
        for op in rows.call_sites(surfaces[sid], rows.LIFECYCLE):
            assert op["projected_from"] == projected_from, op
            assert hasattr(cls, op["name"]), op


def test_every_lifecycle_row_carries_a_summary_projected_from_its_docstring():
    """LD-176 AC3: each row's summary is the method's own first docstring line, so the
    registry cannot describe a call differently from the code — and a lifecycle call shipped
    without a docstring is caught here rather than discovered by a consumer."""
    import inspect

    from larkdocio.sheets.write_client import SheetsWriteClient
    from larkdocio.write.client import WriteClient

    classes = {"docx-write": WriteClient, "sheets-write": SheetsWriteClient}
    for sid, cls in classes.items():
        for op in rows.call_sites(capabilities(full=True)["surfaces"][sid], rows.LIFECYCLE):
            first_line = (inspect.getdoc(getattr(cls, op["name"])) or "").strip().splitlines()
            assert first_line, f"{sid}.{op['name']} has no docstring to project"
            assert op["summary"] == first_line[0]


def test_the_sheets_delete_row_states_it_destroys_the_whole_file():
    """LD-176 AC6, in the discovery layer: the registry lists a tab delete (the ``tab`` write
    op) and a FILE delete, and a consumer reading the two names alone could lose a workbook.
    The lifecycle row says which one it is."""
    surface = capabilities(full=True)["surfaces"]["sheets-write"]
    delete = rows.by_name(surface, rows.LIFECYCLE)["delete_spreadsheet"]
    low = delete["summary"].lower()
    assert "whole" in low and "file" in low, delete
    assert "not a tab" in low, delete
    # ...and the tab op it must not be confused with is still a separate operation.
    assert "tab" in rows.names(surface, rows.OPERATION)


def test_a_lifecycle_call_is_not_smuggled_into_the_operations_projection():
    """LD-176 AC3, transformed by LD-475 with its reason intact: the ``operation`` KIND stays
    exactly the plan-gated op registry. The lifecycle pair is reachable from the registry but
    not counted as a write op — a create is not something ``dry_run`` can preview or ``apply``
    can perform. What LD-475 moved is *where* that distinction is written: one key, and the
    ``kind`` on the row says which sort of call it is, so the two can no longer be told apart
    only by a reader who knew there were sibling keys."""
    for sid in ("docx-write", "sheets-write"):
        surface = capabilities(full=True)["surfaces"][sid]
        op_names = set(rows.names(surface, rows.OPERATION))
        lifecycle = set(rows.names(surface, rows.LIFECYCLE))
        assert not (op_names & lifecycle), sorted(op_names & lifecycle)
        assert op_names == _truth_for(sid)


def test_read_surfaces_declare_no_file_lifecycle():
    """LD-176 AC3: a read surface carries no row of the lifecycle kind at all — claiming one
    would say a read can create or destroy a file, which is the opposite of what it does."""
    for sid, surface in capabilities(full=True)["surfaces"].items():
        if surface["mode"] == "read":
            assert rows.call_sites(surface, rows.LIFECYCLE) == [], sid


def test_read_ops_are_projected_from_the_clients():
    """AC2: read ops are projected from the read CLIENTS (introspected), not hand-listed."""
    caps = capabilities(full=True)
    sheets_read = {op["name"]: op for op in caps["surfaces"]["sheets-read"]["operations"]}
    assert "get_values" in sheets_read
    assert sheets_read["get_values"]["projected_from"] == "larkdocio.sheets.client.SheetsReadClient"

    docx_read = {op["name"]: op for op in caps["surfaces"]["docx-read"]["operations"]}
    assert "get_docx_content" in docx_read
    assert docx_read["get_docx_content"]["projected_from"] == "larkdocio.read.client.Client"


# --------------------------------------------------------------------------- #
# AC3 — bidirectional drift guard (both directions, every registry).           #
# --------------------------------------------------------------------------- #

def test_every_registry_op_appears_in_capabilities_and_vice_versa():
    """AC3 (both directions): for each projected surface, the operations projection
    equals its code-truth source — no phantom op, no dropped op."""
    caps = capabilities(full=True)
    for surface_id in ("docx-write", "sheets-write", "docx-read", "sheets-read"):
        documented = _op_names(caps["surfaces"][surface_id])
        phantom, missing = _phantom_and_missing(documented, _truth_for(surface_id))
        assert not phantom, f"{surface_id}: projection claims ops absent from code truth: {phantom}"
        assert not missing, f"{surface_id}: code truth has ops the projection dropped: {missing}"


def test_every_enumerated_operation_resolves_to_a_real_symbol():
    """AC3 (forward): every enumerated op resolves to a real symbol — a read op is a
    real client method; a write op's name is a real registry kind AND its request types
    are real classes."""
    caps = capabilities(full=True)

    # read surfaces — each op resolves on the class its OWN ``projected_from`` names (so a
    # parser op cannot be attributed to the client, or vice-versa; LD-133).
    for sid in ("sheets-read", "docx-read"):
        for op in rows.call_sites(caps["surfaces"][sid], rows.OPERATION):
            source = _PROJECTION_SOURCES[op["projected_from"]]
            assert hasattr(source, op["name"]), (
                f"{sid}: {op['name']!r} does not resolve on {op['projected_from']}")

    # docx write — name is a real kind; each request type resolves on the model package.
    docx_kinds = {d.kind for d in DOCX_WRITE_OPS}
    import larkdocio.write.model as docx_model
    for op in rows.call_sites(caps["surfaces"]["docx-write"], rows.OPERATION):
        assert op["name"] in docx_kinds
        for rt in op["request_types"]:
            assert hasattr(docx_model, rt), f"docx request type {rt!r} does not resolve"

    # sheets write — name is a real kind; each request type resolves on the requests module.
    sheets_kinds = {d.kind for d in SHEETS_WRITE_OPS}
    import larkdocio.sheets.requests as sheets_requests
    for op in rows.call_sites(caps["surfaces"]["sheets-write"], rows.OPERATION):
        assert op["name"] in sheets_kinds
        for rt in op["request_types"]:
            assert hasattr(sheets_requests, rt), f"sheets request type {rt!r} does not resolve"

    # the embedded deep-read composed op resolves to a real bridge symbol.
    import larkdocio.sheets.embed as embed
    for op in caps["surfaces"]["sheets-embedded-deep-read"]["operations"]:
        assert hasattr(embed, op["name"])


# --------------------------------------------------------------------------- #
# AC4 — opt-in flags + per-surface creds/scopes are truthful.                   #
# --------------------------------------------------------------------------- #

def test_flags_match_the_shipped_cli_and_engine_surface():
    """AC4: the three flags are truthful — the two CLI flags are real ``download``
    params; ``verify_style`` names the real engine auto-on trigger."""
    caps = capabilities(full=True)
    flags = caps["flags"]

    from larkdocio.cli import download as cli_download
    cli_params = {p.name for p in cli_download.params}
    assert "deep_read_sheets" in cli_params
    assert "fidelity_read_sheets" in cli_params
    assert flags["deep_read_sheets"]["cli"] == "--deep-read-sheets"
    assert flags["deep_read_sheets"]["default"] is False
    # LD-385: the prerequisite is PER LEG, so `requires` carries no hard edge and the summary
    # states both. The docx EMBEDDED-sheet leg needs --deep-read-sheets; a folder's standalone
    # SPREADSHEET child needs only this flag, and declaring the embedded leg's prerequisite for
    # both would tell a consumer this flag does nothing on its own — false for the leg a
    # colour-encoded workbook actually travels.
    assert flags["fidelity_read_sheets"]["requires"] == []
    summary = flags["fidelity_read_sheets"]["summary"]
    assert "needs --deep-read-sheets" in summary
    assert "needs nothing else" in summary

    # verify_style is the ENGINE style-leg auto-on trigger, not a CLI flag.
    import larkdocio.sheets.requests as sheets_requests
    assert flags["verify_style"]["mode"] == "engine"
    assert flags["verify_style"]["auto_on"] is True
    assert hasattr(sheets_requests, "effective_verify_style")
    assert hasattr(sheets_requests, "requires_style_leg")


def test_per_surface_credentials_match_the_credential_doctrine():
    """AC4: each surface's READ/WRITE app + env-var pair matches the credential doctrine
    (``common.auth`` env tuples — code truth); the documented docx scopes are present."""
    caps = capabilities(full=True)
    surfaces = caps["surfaces"]

    read_surfaces = ("docx-read", "sheets-read", "sheets-embedded-deep-read")
    for sid in read_surfaces:
        cred = surfaces[sid]["credentials"]
        assert cred["app"] == "read"
        assert cred["env_primary"] == list(READ_ENV)
        assert cred["env_fallback"] == list(LEGACY_ENV)

    for sid in ("docx-write", "sheets-write"):
        cred = surfaces[sid]["credentials"]
        assert cred["app"] == "write"
        assert cred["env_primary"] == list(WRITE_ENV)
        assert cred["env_fallback"] == []  # write NEVER falls back (credential doctrine)

    # Documented scope strings (PROJECT.md / write/README.md / .env.example).
    assert "docx:document:readonly" in surfaces["docx-read"]["credentials"]["scopes"]
    assert "docx:document" in surfaces["docx-write"]["credentials"]["scopes"]
    # The fidelity xlsx-export leg's READ-app scope (SHEETS.md).
    assert "drive:export" in surfaces["sheets-embedded-deep-read"]["credentials"]["optional_scopes"]


def test_embedded_deep_read_is_opt_in_and_gated_by_the_flags():
    """AC4: the embedded deep-read surface is opt-in and gated by the two read flags."""
    surface = capabilities(full=True)["surfaces"]["sheets-embedded-deep-read"]
    assert surface["opt_in"] is True
    assert "deep_read_sheets" in surface["gated_by"]


# --------------------------------------------------------------------------- #
# AC1/AC4 — safety-contract descriptors are truthful (staleness resolves).      #
# --------------------------------------------------------------------------- #

def test_write_surfaces_carry_the_right_safety_contracts():
    """AC1: each write surface enumerates its safety contracts; the staleness guards
    are surface-correct (docx = STALE_ANCHOR, sheets = STALE_SHEET)."""
    caps = capabilities(full=True)
    docx = caps["surfaces"]["docx-write"]["safety_contracts"]
    sheets = caps["surfaces"]["sheets-write"]["safety_contracts"]
    for token in ("plan-gated", "dry-run-mandatory", "exactly-one-or-refuse"):
        assert token in docx and token in sheets
    assert "STALE_ANCHOR" in docx and "STALE_SHEET" not in docx
    assert "STALE_SHEET" in sheets and "STALE_ANCHOR" not in sheets


def test_staleness_descriptors_resolve_to_real_refusal_machinery():
    """AC4/AC3: the staleness safety descriptors name refusal machinery that exists —
    a phantom safety claim would be a lie."""
    from larkdocio.sheets.plan import Refusal as SheetsRefusal
    from larkdocio.write.model import Refusal as DocxRefusal, RefusalReason
    assert callable(SheetsRefusal.stale_sheet)
    assert callable(DocxRefusal.stale_anchor)
    assert RefusalReason.STALE_ANCHOR.value == "stale-anchor"


# --------------------------------------------------------------------------- #
# AC5 — the guard bites red-then-green (drift reddens; truth greens).           #
# --------------------------------------------------------------------------- #

def test_drift_guard_bites_on_a_dropped_op():
    """AC5: dropping a real registry op from the projection makes the SAME bidirectional
    check that guards report a ``missing`` op — i.e. the guard would go red."""
    truth = _truth_for("sheets-write")
    truthful = sorted(truth)
    drifted = truthful[:-1]  # drop one real op
    phantom, missing = _phantom_and_missing(drifted, truth)
    assert not phantom and missing == [truthful[-1]]
    # And the truthful projection greens the very same check.
    phantom2, missing2 = _phantom_and_missing(truthful, truth)
    assert not phantom2 and not missing2


def test_drift_guard_bites_on_a_phantom_op():
    """AC5: a phantom capability (an op the registry does not have) makes the guard
    report a ``phantom`` — red — while the real projection is clean."""
    truth = _truth_for("docx-write")
    drifted = sorted(truth) + ["totally-made-up-op"]
    phantom, missing = _phantom_and_missing(drifted, truth)
    assert phantom == ["totally-made-up-op"] and not missing

    # The live projection passes the same check with zero drift.
    documented = _op_names(capabilities(full=True)["surfaces"]["docx-write"])
    phantom2, missing2 = _phantom_and_missing(documented, truth)
    assert not phantom2 and not missing2


# --------------------------------------------------------------------------- #
# LD-140 (the Markdown-authoring spec § F1-S7 AC6) — GATE COVERAGE: how a write surface's contracts  #
# are proved LIVE. Bidirectionally guarded against the test tree itself, so the   #
# registry cannot claim a gate that does not exist — nor omit one that does       #
# (which is AC4's "zero orphans", mechanized).                                   #
# --------------------------------------------------------------------------- #

_TESTS_DIR = pathlib.Path(__file__).resolve().parent


def _marked_modules(glob: str, marker: str = "live_write") -> set:
    """CODE TRUTH for one ring: every ``tests/<glob>`` module that really carries ``marker``.

    Read off the filesystem, not a list — a new gate file joins the truth set the moment it is
    written, which is what makes the bidirectional guards below unable to miss an orphan.

    Two exclusions, both load-bearing:

    * the marker must be a **module-level statement** (the line starts with it), not merely a
      substring somewhere in the file. A companion that *asserts about* the marker quotes it
      verbatim, and a substring match counts that companion as a ring member — which reports a
      missing gate row for a file that is not a gate at all;
    * a ``*_offline.py`` companion is never a ring member. It is the always-on half of a gate
      (the discipline a credential-gated file cannot prove on an ordinary run), so it must not
      demand its own coverage row.
    """
    statement = f"pytestmark = pytest.mark.{marker}"
    out = set()
    for path in sorted(_TESTS_DIR.rglob(glob)):  # LD-654: recursive population
        if path.name.endswith("_offline.py"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if any(line.startswith(statement) for line in lines):
            out.add(f"tests/{path.name}")
    return out


def _live_write_modules() -> set:
    """The docx-write ring's truth set.

    Two globs, because one member of this ring is deliberately **not** a write gate (LD-172).
    The reviewer-anchor contract cannot be proved by writing: Lark has no anchored-comment
    create, so a self-provisioned disposable cannot be given an inline anchor, and the only
    honest live proof is a READ-ONLY arm against a document that already has real ones. That arm
    carries the ``live`` marker and its own name, so the truth set is the union — which keeps
    zero-orphans in **both** directions: a second ``test_live_comment_anchor_*.py`` arm added
    without a coverage row still reddens, exactly as a write gate would.
    """
    return (_marked_modules("test_live_write_*.py")
            | _marked_modules("test_live_comment_anchor_*.py", marker="live"))


def _live_base_read_modules() -> set:
    """The Base READ ring's truth set (LD-260 / O6′).

    Two globs, because the ring is two arms with different names and the same marker: the
    whole-client read arm and THE L1 GATE, the Base canary. Both are read-only and carry the
    ``live`` marker rather than the write ring's — which is exactly why keying on the marker
    alone would be wrong, and why each ring gets its own glob.
    """
    return (_marked_modules("test_live_base_read_*.py", marker="live")
            | _marked_modules("test_live_base_canary*.py", marker="live"))


def _live_base_write_modules() -> set:
    """The Base WRITE ring's truth set: the transport arm, the engine gate and the relational
    gate.

    Deliberately narrower than ``test_live_base_*``: the Base self-provisioning HARNESS carries
    the same marker and is not a member of any surface's ring — it provisions, it proves no
    shipped behavior, and enrolling it here would report the coverage as missing a row for a
    file that is not a gate.

    **Two globs, because the third member's name does not share the stem.** The relational gate
    is a record-surface member — its writes are record writes and the attachment leg it
    hash-verifies is declared on this surface — but it is named for what it proves rather than
    for the family it rides, so a stem glob would miss it and the ring would silently under-claim
    its own coverage.
    """
    return (_marked_modules("test_live_base_write_*.py")
            | _marked_modules("test_live_base_relational_*.py"))


def _live_base_schema_modules() -> set:
    """The Base SCHEMA-write ring's truth set — four family arms plus the rung's own gate.

    Four globs rather than one, and each is deliberate: the ring is the app/table arm, the
    field arm, the view arm, the destructive arm, the guided-migration arm and the gate, and
    their names do not share a stem. A single wide ``test_live_base_*`` glob would swallow the
    record ring and the self-provisioning HARNESS, which is a member of no surface's ring at
    all — it provisions, it proves no shipped behavior, and enrolling it here would report a
    missing row for a file that is not a gate.

    The guided COLUMN-TYPE MIGRATION arm is enrolled by its own glob for the same reason every
    other member has one: it is a schema-write gate whose name shares no stem with the others,
    and a ring that could not see it would let a gate be claimed without being checked.
    """
    return (_marked_modules("test_live_base_schema_*.py")
            | _marked_modules("test_live_base_views*.py")
            | _marked_modules("test_live_base_field_migration*.py")
            | _marked_modules("test_live_base_destructive*.py"))


def _live_comments_modules() -> set:
    """The comments-read ring's truth set.

    A separate glob, not a widening of the docx one: the two rings prove different surfaces
    and each owes its own bidirectional join. The comments gate shares the ``live_write``
    MARKER (it needs write credentials to create the comment it reads) while being a member of
    a different ring — so keying the truth set on the marker alone would silently merge them,
    and each surface's coverage would then appear to claim the other's members.
    """
    return _marked_modules("test_live_comments_*.py")


#: surface id → the ring's code-truth source. Every surface carrying ``gate_coverage`` must
#: appear here; the scope pin below enforces that, so a surface cannot gain a live-gate claim
#: without gaining a bidirectional check of it.
_GATE_TRUTH_SOURCES = {
    "docx-write": _live_write_modules,
    "docx-comments-read": _live_comments_modules,
    # LD-260 — the two Base rings. `base-read`'s claim was correctly refused by LD-251 (its
    # ring was still LD-252's unlanded product) and is declarable now; `base-write` arrives
    # with its own. Each brings its OWN code-truth source, which is the rule the scope pin
    # below states: claiming a live gate and having that claim checked are the same act.
    "base-read": _live_base_read_modules,
    "base-write": _live_base_write_modules,
    # LD-266 — the schema ring, arriving with its own code-truth source for the reason the pin
    # below states: claiming a live gate and having that claim checked are the same act.
    "base-schema-write": _live_base_schema_modules,
}


def _gate_coverage(surface_id="docx-write") -> dict:
    return capabilities(full=True)["surfaces"][surface_id]["gate_coverage"]


def test_the_docx_write_surface_declares_its_live_gate_coverage():
    """AC6: the authoring surface's gate coverage names the marker, the command that runs it,
    and the credentials it needs — so "how is this proved?" is answerable from the registry
    alone, which used to be answerable only by reading the test tree."""
    coverage = _gate_coverage()
    assert coverage["marker"] == "live_write"
    # LD-539: the payload states the command a consumer can TYPE, and the bare
    # command has not run the ring since LD-537 armed the consent fence.
    assert coverage["command"] == "LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write"
    assert coverage["credentials_env"] == list(WRITE_ENV)
    assert coverage["members"], "the coverage must enumerate the ring's members"
    # The target policy is part of the contract, not a footnote (AC5).
    assert "self-provision" in coverage["target_policy"]


def test_the_gate_coverage_records_the_authoring_member_and_the_concurrency_arm():
    """AC6 verbatim: the coverage records **the `live_write` member** for authoring **and
    the `STALE_DOCUMENT` concurrency arm**. The arm is called out separately on purpose — a
    member id alone cannot say that the drift refusal is proved against real Lark, and D9 is
    the Critical-class contract of the tranche."""
    members = {m["id"]: m for m in _gate_coverage()["members"]}
    authoring = members["authoring-round-trip"]
    assert authoring["module"] == "tests/test_live_write_authoring_gate.py"
    assert "STALE_DOCUMENT" in authoring["proves_contracts"]
    assert "STALE_ANCHOR" not in authoring["arms"]
    assert "STALE_DOCUMENT-concurrency" in authoring["arms"], (
        "the concurrency arm must be recorded as its own arm of the authoring member")
    assert "authoring-round-trip" in authoring["arms"]


@pytest.mark.parametrize("surface_id", sorted(_GATE_TRUTH_SOURCES))
def test_every_gate_member_resolves_to_a_real_marked_test_module(surface_id):
    """AC6 (forward), for EVERY surface that claims a live ring: every module the coverage
    names exists **and** carries the marker it is claimed under — a phantom gate is a phantom
    safety claim.

    A member may declare its **own** ``marker``, overriding the ring's (LD-172: the read-only
    reviewer-anchor arm). The check follows the declaration rather than the ring, which is
    stricter than it sounds: a member that claims an override it does not carry reddens here
    just as loudly as one missing the ring's marker."""
    coverage = _gate_coverage(surface_id)
    for member in coverage["members"]:
        path = _TESTS_DIR.parent / member["module"]
        assert path.exists(), f"gate coverage names a missing module: {member['module']}"
        declared = member.get("marker") or coverage["marker"]
        marker = f"pytestmark = pytest.mark.{declared}"
        assert marker in path.read_text(encoding="utf-8"), (
            f"{member['module']} is claimed as a {declared} gate member but does "
            f"not carry the marker — it would never run in the ring")


@pytest.mark.parametrize("surface_id", sorted(_GATE_TRUTH_SOURCES))
def test_every_ring_matches_its_own_truth_source_bidirectionally(surface_id):
    """Zero orphans per ring, mechanized: the modules a surface's coverage names equal the
    modules its own glob really finds carrying the marker. A gate added without its row
    reddens; a row whose gate was deleted reddens too."""
    documented = [m["module"] for m in _gate_coverage(surface_id)["members"]]
    assert len(documented) == len(set(documented)), f"duplicate gate rows: {documented}"
    phantom, missing = _phantom_and_missing(
        documented, _GATE_TRUTH_SOURCES[surface_id]())
    assert not phantom, f"{surface_id} claims modules the test tree lacks: {phantom}"
    assert not missing, f"{surface_id}'s ring has members its coverage omits: {missing}"


def test_the_truth_source_excludes_offline_companions_and_quoted_markers():
    """The two exclusions above, proved rather than assumed.

    Both are real failure modes met while writing this: an ``*_offline.py`` companion asserts
    ON the marker string, so a substring scan enrolls it as a ring member and then reports the
    gate coverage as missing a row for a file that runs offline by design.
    """
    offline = _TESTS_DIR / "test_live_comments_read_gate_offline.py"
    assert offline.exists()
    text = offline.read_text(encoding="utf-8")
    assert "pytestmark = pytest.mark.live_write" in text, (
        "this companion is expected to QUOTE the marker — that is what makes it the probe")
    assert not any(line.startswith("pytestmark = pytest.mark.live_write")
                   for line in text.splitlines()), (
        "the companion must not actually carry the marker at module level")
    assert f"tests/{offline.name}" not in _live_comments_modules()
    assert f"tests/{offline.name}" not in _live_write_modules()

    # And the real gate IS in its ring.
    assert "tests/test_live_comments_read_gate.py" in _live_comments_modules()


def test_the_two_rings_do_not_overlap():
    """The comments gate shares the write ring's MARKER but not its ring. Pinned so a future
    rename cannot quietly make one ring swallow the other's members — which would let a
    surface appear to prove a gate it has nothing to do with."""
    write_ring = _live_write_modules()
    comments_ring = _live_comments_modules()
    assert write_ring and comments_ring, "a ring's truth source found nothing"
    assert not (write_ring & comments_ring), (
        f"the two rings claim the same modules: {sorted(write_ring & comments_ring)}")


def test_the_gate_coverage_matches_the_docx_ring_bidirectionally():
    """AC6/AC4 (both directions — **zero orphans**, mechanized): the modules the coverage
    names equal the ``test_live_write_*`` modules that really carry the marker. A gate added
    without its row (an orphan nobody can discover) reddens; a row whose gate was deleted
    reddens too."""
    documented = [m["module"] for m in _gate_coverage()["members"]]
    assert len(documented) == len(set(documented)), f"duplicate gate rows: {documented}"
    phantom, missing = _phantom_and_missing(documented, _live_write_modules())
    assert not phantom, f"gate coverage claims modules the test tree lacks: {phantom}"
    assert not missing, f"the docx live_write ring has members the coverage omits: {missing}"


def test_every_contract_a_gate_member_claims_is_a_real_contract_of_the_surface():
    """AC6: a member cannot claim to prove a contract the surface does not carry (or that
    does not exist at all) — the two truth lists are joined, not separately believed."""
    surface = capabilities(full=True)["surfaces"]["docx-write"]
    catalog = capabilities(full=True)["safety_contracts"]
    for member in surface["gate_coverage"]["members"]:
        for contract in member["proves_contracts"]:
            assert contract in catalog, (
                f"{member['id']} claims a contract absent from the catalog: {contract}")
            assert contract in surface["safety_contracts"], (
                f"{member['id']} claims {contract}, which is not a contract of docx-write")


def test_every_write_surface_safety_contract_is_proved_by_some_gate_member():
    """The direction that matters most: a safety contract nothing proves live is a claim, not
    a guarantee. Every docx-write contract must be named by at least one ring member — which
    is what makes ``STALE_DOCUMENT`` unable to ship again without a live arm.

    One exemption, by name and with its reason (LD-200, kept by LD-707):
    ``permission-denial-is-never-an-absence`` cannot be proved live without revoking a scope,
    so it is proved offline against captured denial bodies. The exemption must stay true: an
    exempted contract that a member starts to prove, or that docx-write stops carrying, is
    reported, so the list cannot go stale."""
    offline_proved = {"permission-denial-is-never-an-absence"}
    surface = capabilities(full=True)["surfaces"]["docx-write"]
    proved = {c for m in surface["gate_coverage"]["members"] for c in m["proves_contracts"]}
    unproved = sorted(set(surface["safety_contracts"]) - proved - offline_proved)
    assert not unproved, (
        f"docx-write claims safety contracts no live gate member proves: {unproved}")
    stale = sorted(c for c in offline_proved
                   if c in proved or c not in surface["safety_contracts"])
    assert not stale, f"stale offline-proved exemption: {stale}"


def test_the_gate_coverage_drift_guard_bites_red_then_green():
    """AC6 (the guard bites): the SAME bidirectional check that guards reports a phantom for
    an invented module and a missing one for a dropped row, and is clean on the real
    projection."""
    truth = _live_write_modules()
    phantom, missing = _phantom_and_missing(
        sorted(truth) + ["tests/test_live_write_imaginary_gate.py"], truth)
    assert phantom == ["tests/test_live_write_imaginary_gate.py"] and not missing
    dropped = sorted(truth)[:-1]
    phantom2, missing2 = _phantom_and_missing(dropped, truth)
    assert not phantom2 and missing2 == [sorted(truth)[-1]]
    documented = [m["module"] for m in _gate_coverage()["members"]]
    phantom3, missing3 = _phantom_and_missing(documented, truth)
    assert not phantom3 and not missing3


def test_every_surface_claiming_gate_coverage_has_its_own_truth_source():
    """The scope pin, kept as a **rule** rather than a hard-coded surface list.

    Its original form named exactly one surface and told the next person to extend the guard
    with a code-truth source instead of widening the pin. That is what LD-159 did — the
    comments-read surface arrived with its own ring, its own glob and its own bidirectional
    join above — so the pin now states the rule directly: claiming a live gate and having that
    claim checked are the same act. A surface with coverage but no truth source reddens here;
    the sheets write ring is still deliberately unclaimed, and stays honest either way.
    """
    covered = {sid for sid, s in capabilities(full=True)["surfaces"].items()
               if s.get("gate_coverage") is not None}
    assert covered == set(_GATE_TRUTH_SOURCES), (
        f"gate_coverage surfaces {sorted(covered)} do not match the guarded set "
        f"{sorted(_GATE_TRUTH_SOURCES)} — add the new surface's own code-truth source (a "
        f"marker glob over the test tree), do not widen this assertion alone")
    # And the sheets write ring is still unclaimed — recorded, not silent.
    assert "sheets-write" not in covered


# --------------------------------------------------------------------------- #
# Consumer-view — the dict answers: what can I do / what creds / what flags.    #
# --------------------------------------------------------------------------- #

def test_consumer_view_answers_the_three_questions():
    """A consumer can read, from the dict alone: what can I do (operations), what
    creds do I need (credentials), and what flags exist (flags)."""
    caps = capabilities(full=True)

    # What can I do on the sheets write surface?
    sheets_write = caps["surfaces"]["sheets-write"]
    assert _op_names(sheets_write)  # non-empty projected op list
    assert {"value", "formula", "dropdown", "structural", "dimension-property", "style",
            "merge", "tab", "freeze-panes"} == set(
        _op_names(sheets_write))   # "formula" joined in LD-149, "dimension-property" in
                                   # LD-185, "freeze-panes" in LD-186, "style" in LD-188
                                   # (promoted out of the test harness)

    # What creds do I need for it?
    assert sheets_write["credentials"]["app"] == "write"
    assert sheets_write["credentials"]["env_primary"] == list(WRITE_ENV)

    # What flags exist across the toolkit?
    assert set(caps["flags"]) == {
        # LD-173 (dogfood F3) — the read knob that changes what a read RETURNS and had
        # no row here at all, which is why it was undiscoverable: it is ON by default.
        "resolve_mentions",
        "deep_read_sheets", "fidelity_read_sheets", "verify_style",
        # LD-251 — the Base deep-read knob. LD-340 AMENDED it into a CLI flag
        # (--deep-read-bases), so its row's mode is now "cli"; it stays discoverable here.
        "deep_read_bases",
        # LD-269 — the Base link-resolution knob, the same shape and for the same reason: a
        # read argument that changes what a read RETURNS, so it is discoverable here or not
        # at all (the LD-173 lesson, applied at birth this time).
        "resolve_base_links",
        # LD-293 — the Base RAW-value knob, declared for the same reason once more: it
        # changes what a read HANDS BACK (a second artefact beside the rendered cells) and
        # it is the one knob here that costs measurable memory, so a consumer must be able
        # to find it and its price without reading the source.
        "retain_base_raw_values",
        # LD-386 — the folder-scale asset fetch. Declared here for the same reason and one
        # more: it is the only knob whose cost is a whole FOLDER's binaries, and its LAYOUT
        # (one shared token-named pool, collisions impossible by construction) is a decision
        # a consumer has to be able to look up rather than discover on disk.
        "folder_assets",
    }
    # Every gated surface names a flag that actually exists in the flags catalog.
    for surface in caps["surfaces"].values():
        for flag_id in surface["gated_by"]:
            assert flag_id in caps["flags"]


# --------------------------------------------------------------------------- #
# LD-181 — the PER-BLOCK-TYPE READ projection. The registry projected the WRITE   #
# side per block type (the creatable floor) and NOTHING for read, so "will this   #
# document's callouts / images / boards survive the read?" was unanswerable from   #
# shipped material. The cell-for-cell pinning against the block matrix lives in    #
# tests/test_blocks_md_matrix.py (the guard it extends); this is the registry half. #
# --------------------------------------------------------------------------- #

def test_the_docx_read_surface_projects_per_block_type_read_support():
    """The projection is on the surface a consumer would look on, and every row answers
    all three questions rather than only "is it registered" (which ``get_registry()``
    already answered — and which is exactly how far the consumer got alone)."""
    support = capabilities(full=True)["surfaces"]["docx-read"]["block_read_support"]
    assert support["summary"] and support["unlisted_type"]
    assert support["lossiness_vocabulary"]
    assert len(support["types"]) > 50, "the projection must cover the docx block enum"
    for row in support["types"]:
        assert set(row) == {"block_type", "name", "handled", "emits", "lossiness", "lossy"}
        assert row["lossiness"] in support["lossiness_vocabulary"]


def test_the_read_support_handled_flag_is_the_live_registry():
    """It is a JOIN, not a stored copy: ``handled`` is ``get_registry()`` membership, so it
    cannot answer "yes" for a handler that was deleted."""
    from larkdocio.blocks import get_registry

    support = capabilities(full=True)["surfaces"]["docx-read"]["block_read_support"]
    registry = set(get_registry())
    assert {row["block_type"] for row in support["types"] if row["handled"]} == registry


def test_only_the_docx_read_surface_claims_a_block_read_projection():
    """The scope pin, kept as a rule: a surface that gains this projection must also gain a
    matrix to be pinned against. Sheets has its own capability matrix and its own guard, and
    a WRITE surface claiming one would be describing reads it does not do."""
    claimed = {sid for sid, s in capabilities(full=True)["surfaces"].items()
               if s.get("block_read_support") is not None}
    assert claimed == {"docx-read"}, (
        f"block_read_support surfaces {sorted(claimed)} != {{'docx-read'}} — extend the "
        f"matrix guard for the new surface, do not widen this pin alone")


def test_the_read_support_projection_names_no_write_status():
    """The two axes stay separate: per-block WRITE support is the creatable floor, and a read
    row that mentioned creatability would rot the moment a type became creatable."""
    support = capabilities(full=True)["surfaces"]["docx-read"]["block_read_support"]
    blob = json.dumps(support).lower()
    for word in ("creatable", "editable"):
        assert word not in blob, word


def test_a_registered_handler_with_no_read_support_row_refuses_to_project(monkeypatch):
    """The omission direction, mechanized: a handler is the direction a missing row hides in
    (a new handler would simply not appear), so the join raises instead of shipping a
    projection that under-reports what the reader handles."""
    from larkdocio.blocks import BLOCK_REGISTRY

    monkeypatch.setitem(BLOCK_REGISTRY, 9997, lambda parser, block, indent: None)
    with pytest.raises(RuntimeError) as excinfo:
        capabilities(full=True)
    assert "9997" in str(excinfo.value) and "read_support" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# LD-707 (round 7, X3) — ONE safety-contract census, both directions.            #
# --------------------------------------------------------------------------- #

def test_the_contract_census_agrees_with_itself_in_both_directions():
    """Which surfaces carry contract C has one answer: the catalogue's ``applies_to`` and the
    surfaces whose own ``safety_contracts`` list C are the same set, for every C, and no
    surface lists a contract the catalogue lacks."""
    caps = capabilities(full=True)
    catalogue, surfaces = caps["safety_contracts"], caps["surfaces"]
    for cid, contract in catalogue.items():
        listing = {sid for sid, surface in surfaces.items() if cid in surface["safety_contracts"]}
        assert set(contract["applies_to"]) == listing, cid
    for sid, surface in surfaces.items():
        assert set(surface["safety_contracts"]) <= set(catalogue), sid


def test_a_surface_claiming_a_contract_the_catalogue_does_not_name_it_for_is_refused():
    """The derivation's refusal direction bites: a surface list that the catalogue does not
    name back cannot be published."""
    import dataclasses

    from larkdocio.capabilities import _assembly
    from larkdocio.capabilities._contracts import _safety_contracts

    contracts = _safety_contracts()
    surface = _assembly._surface_drive_folders_write()
    claimed = dataclasses.replace(surface, safety_contracts=["STALE_ANCHOR"])
    with pytest.raises(AssertionError, match="STALE_ANCHOR"):
        _assembly._with_contract_census({"drive-folders-write": claimed}, contracts)
    derived = _assembly._with_contract_census({"docx-read": _assembly._surface_docx_read()},
                                              contracts)
    assert "permission-denial-is-never-an-absence" in derived["docx-read"].safety_contracts
