# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE FOURTH DIRECTION — a shipped call site the DECLARATION never named (LD-442, D-78).

`tests/test_permissions_registry.py` holds the registry's three completeness directions: an
API-using operation with no row, a row whose operation vanished, and an endpoint with no row in
the scope table. All three are seeded on **both** sides from ``capabilities()`` — the rows come
from a surface's declared operations / legs / lifecycle calls, and so does the inventory they
are checked against. A **public method that reaches Lark and is declared nowhere** is therefore
missing from both sides at once, so the bidirectional check compares two copies of the same
omission and passes.

That is not hypothetical. ``DriveFilesWriteClient.delete`` shipped, is public, is exercised by
the live round trip, and is named in D-72's own ruling text as part of what makes the Drive
upload slice reversible — and it had **no permission row** while this suite stayed green. The
direction guarded here is seeded from the **code** instead, so the next one cannot hide either.

**Tier: unmarked regression, deliberately.** This module pins one internal projection (what the
package's own callables reach) against another (the registry's rows). Nothing here is a claim
about Lark; the scope requirements themselves are guarded — and conformance-marked — next door.
"""
import pytest

from larkdocio import permissions as perm


# --------------------------------------------------------------------------- #
# THE FOURTH DIRECTION (LD-442) — a shipped call site the DECLARATION never     #
# named. The three checks above are all seeded from ``capabilities()``: an      #
# operation, a leg or a lifecycle call. A public method that reaches Lark and   #
# is declared NOWHERE is therefore invisible to every one of them — which is    #
# how ``DriveFilesWriteClient.delete`` shipped, was exercised by the live       #
# round trip, and still had no permission row while this suite stayed green.    #
# This direction is seeded from the CODE instead.                               #
# --------------------------------------------------------------------------- #

#: Endpoints a shipped public callable reaches that NO permission row carries, each with the
#: reason it is nonetheless allowed. Same discipline as ``EXPECTED_UNREACHED_ROWS`` above: the
#: exemption is named, carries a real reason, and reddens when it goes stale.
EXPECTED_UNDECLARED_ENDPOINTS = {
    "/open-apis/auth/v3/tenant_access_token/internal": (
        "the tenant-token mint sits BELOW the operation layer — it is the credential exchange "
        "every other call rides on, made inside the shared transport rather than by any "
        "operation, and no scope governs it. It has its own ENDPOINT_SCOPES row (see "
        "EXPECTED_UNREACHED_ROWS above, which exempts the same call from the mirror "
        "direction); what it does not have, and should not have, is a per-operation row."
    ),
}


def test_no_shipped_public_callable_reaches_an_endpoint_no_permission_row_carries():
    """The direction the audit found open. Seeded from the package's own public callables, so
    a client method nobody declared cannot hide."""
    undeclared = perm.undeclared_endpoints()
    unexplained = sorted(
        (path, endpoint) for path, endpoint in undeclared
        if endpoint not in EXPECTED_UNDECLARED_ENDPOINTS)
    assert not unexplained, (
        "these shipped public callables reach a Lark endpoint that appears in NO permission "
        "row — declare the call site in capabilities() (an operation, a leg or a lifecycle "
        f"call) so its requirement is authored somewhere: {unexplained}")
    stale = sorted(set(EXPECTED_UNDECLARED_ENDPOINTS)
                   - {endpoint for _path, endpoint in undeclared})
    assert not stale, (
        f"these endpoints are now carried by a row, so their exemption is obsolete: {stale}")
    for endpoint, reason in EXPECTED_UNDECLARED_ENDPOINTS.items():
        assert len(reason) > 60, f"{endpoint} is exempted without a real reason"


def test_the_scan_sees_call_sites_the_operation_inventory_CANNOT():
    """The reason this direction exists at all: the scan is seeded from the code, so it covers
    public methods that are not the impl of any declared operation."""
    scanned = {path for path, _endpoints in perm.shipped_call_sites()}
    declared = {name for _surface, name in dict(perm.operation_inventory())}
    assert "larkdocio.drive.files_write.DriveFilesWriteClient.download" in scanned
    assert "larkdocio.drive.files_write.DriveFilesWriteClient.delete" in scanned
    # LD-710 moved this premise, as the message below always said it might: ``download`` is now
    # a declared leg of drive-files-write (the census below is why). Re-pointed, not dropped, at
    # a public method that is still undeclared — an upload primitive of put_file_in_folder.
    assert "download" in declared
    assert "larkdocio.drive.files_write.DriveFilesWriteClient.upload_part" in scanned
    assert "upload_part" not in declared, (
        "if upload_part became a declared operation this assertion's premise moved — "
        "re-point it at whatever public method is still undeclared")
    assert len(scanned) > len(declared), (
        f"the scan found {len(scanned)} API-reaching public callables against {len(declared)} "
        "declared operations — it is seeded from the code precisely so it can exceed the "
        "declaration, and a scan that no longer does has stopped guarding")


def test_every_scanned_call_site_derives_its_endpoints_from_the_code():
    """The scan reuses the SAME derivation the registry does, so the two cannot disagree about
    what a callable reaches."""
    sites = dict(perm.shipped_call_sites())
    assert sites["larkdocio.drive.files_write.DriveFilesWriteClient.delete"] == \
        ("/open-apis/drive/v1/files/:file_token",)


def test_the_undeclared_check_bites_RED_on_a_call_site_nobody_declared():
    """Direction four, proven red on the REAL function rather than on set arithmetic."""
    undeclared = perm.undeclared_endpoints(
        sites=(("larkdocio.somewhere.NewClient.new_call", ("/open-apis/im/v1/messages",)),))
    assert undeclared == [("larkdocio.somewhere.NewClient.new_call",
                           "/open-apis/im/v1/messages")]


def test_the_undeclared_check_bites_RED_on_THE_call_site_the_old_walk_MISSED():
    """The regression this direction was written for: drop the row(s) that now declare the file
    delete and the shipped call site must be reported again.

    It used to drop the ONE row named ``delete``. **Two** declared rows now carry this endpoint —
    the drive-file delete and ``base-schema-write.delete_base``, which trashes a whole Base
    through the same Drive path — so dropping by name would leave the other one declaring it and
    the check would (correctly) stay green, testing nothing. The filter is therefore by
    **endpoint**, which is what the check itself is about.
    """
    endpoint = "/open-apis/drive/v1/files/:file_token"
    rows = {key: row for key, row in perm.permission_registry().items()
            if endpoint not in row.endpoints}
    assert len(rows) < len(perm.permission_registry()) - 1, (
        "more than one declared row must carry this endpoint for the filter above to be the "
        "right shape")
    undeclared = perm.undeclared_endpoints(rows=rows)
    assert ("larkdocio.drive.files_write.DriveFilesWriteClient.delete",
            "/open-apis/drive/v1/files/:file_token") in undeclared


def test_the_undeclared_check_greens_on_a_call_site_a_row_DOES_carry():
    assert perm.undeclared_endpoints(
        sites=(("larkdocio.somewhere.f", ("/open-apis/docx/v1/documents",)),)) == []


def test_a_prose_path_spelling_is_not_reported_as_an_undeclared_endpoint():
    """``{whiteboard_id}`` in a docstring and ``:whiteboard_id`` in the SDK's own uri are one
    endpoint. Without this the scan reports its own documentation."""
    assert perm.undeclared_endpoints(sites=((
        "larkdocio.somewhere.f",
        ("/open-apis/board/v1/whiteboards/{whiteboard_id}/download_as_image",)),)) == []


# --------------------------------------------------------------------------- #
# THE CENSUS (LD-710) — every public method of a REGISTERED client is held to a #
# surface. ``capabilities()`` calls its call-site list the complete            #
# enumeration; the fourth direction above only proves every ENDPOINT has a row,#
# which ``DriveFilesWriteClient.download`` passed while it was declared nowhere #
# (``put_file_in_folder`` reaches the same endpoint). This holds the METHOD.    #
# --------------------------------------------------------------------------- #

import sys

from larkdocio import capabilities as _capabilities
from larkdocio.capabilities import _resolution

#: Public API-reaching methods that are deliberately NOT call sites of their own, each with
#: its reason. A whole class is named only where every public method is a transport the
#: surface's dispatched op kinds drive; anything else is named method by method. Each entry is
#: checked: it must still be a shipped call site, still undeclared, and every endpoint it
#: reaches must be carried by a permission row on the surface its class is registered on — so
#: an exemption can never hide a requirement written down nowhere.
TRANSPORT_PRIMITIVES = {
    # LD-711 — WriteClient used to be named here WHOLE, on the reason "apply() drives these
    # methods from the dispatched op kinds". That reason is kept, and now holds method by
    # method: the class also carries reads the guide sends a consumer to by name
    # (``get_block``, ``read_document_revision``), which the whole-class entry hid from
    # capabilities(). Those two are declared legs of docx-write; only what apply() (or a
    # declared leg) drives internally stays exempt, each with the op kinds that drive it.
    **{f"larkdocio.write.client.WriteClient.{name}": (
        "docx write engine transport: apply() drives it from the dispatched block op kinds "
        "(insert, delete, edit ...), which are the surface's rows; a caller is sent to the "
        "plan, never to the wire call")
       for name in ("batch_delete", "batch_update_blocks", "create_descendant")},
    "larkdocio.write.client.WriteClient.create_children": (
        "docx write engine transport: apply() drives it for the insert op kinds and the "
        "declared put_image_in_document / put_file_in_document legs drive it for their block; "
        "a caller is sent to those, never to the wire call"),
    "larkdocio.write.client.WriteClient.list_document_blocks": (
        "docx write engine transport: apply() lists the document's blocks with it to find the "
        "cells of a table it just created before filling them; a caller reads a document "
        "through docx-read"),
    "larkdocio.write.client.WriteClient.get_document": (
        "the wire half of read_document_revision, the declared docx-write leg that projects "
        "the one field a caller is sent to (revision_id) off this metadata call"),
    **{f"larkdocio.write.client.WriteClient.{name}": (
        "docx write engine transport: apply() drives it from the dispatched comment op kinds "
        "(comment-create, comment-remove), which are the surface's rows; a caller is sent to "
        "the plan, never to the wire call")
       for name in ("create_whole_document_comment", "list_comment_replies",
                    "delete_comment_reply")},
    # LD-711 — SheetsWriteClient was named here WHOLE too, on the reason "apply() and
    # dry_run() drive these methods from the dispatched op kinds". The reason is kept and now
    # holds method by method: the guide's recipes call seven of the class's methods by name
    # (put_values and six reads), and those are declared legs of sheets-write instead.
    **{f"larkdocio.sheets.write_client.SheetsWriteClient.{name}": (
        "Sheets write engine transport: apply() drives it from the dispatched structural op "
        "kinds (insert, delete, append), which are the surface's rows; a caller is sent to "
        "the plan, never to the wire call")
       for name in ("append_dimension", "append_values", "delete_dimension_range",
                    "insert_dimension_range")},
    **{f"larkdocio.sheets.write_client.SheetsWriteClient.{name}": (
        "Sheets write engine transport: apply() drives it from the dispatched style op kind, "
        "which is the surface's row; a caller is sent to the plan, never to the wire call")
       for name in ("put_style", "batch_update_styles")},
    **{f"larkdocio.sheets.write_client.SheetsWriteClient.{name}": (
        "Sheets write engine transport: apply() drives it from the dispatched merge op kind, "
        "which is the surface's row; a caller is sent to the plan, never to the wire call")
       for name in ("merge_cells", "unmerge_cells")},
    "larkdocio.sheets.write_client.SheetsWriteClient.batch_update_sheets": (
        "Sheets write engine transport: apply() drives it from the dispatched tab and "
        "freeze-panes op kinds, which are the surface's rows; a caller is sent to the plan"),
    "larkdocio.sheets.write_client.SheetsWriteClient.set_data_validation": (
        "Sheets write engine transport: apply() drives it from the dispatched dropdown op "
        "kind, which is the surface's row; a caller is sent to the plan, never to the wire"),
    "larkdocio.sheets.write_client.SheetsWriteClient.set_dimension_properties": (
        "Sheets write engine transport: apply() drives it from the dispatched "
        "dimension-property op kind, the surface's row; a caller is sent to the plan"),
    "larkdocio.sheets.write_client.SheetsWriteClient.read_revision": (
        "Sheets write engine transport: dry_run() caches the sheet revision with it and "
        "apply() re-reads it for the STALE_SHEET compare-and-swap; a caller reads a revision "
        "through sheets-read's own read_revision"),
    "larkdocio.sheets.write_client.SheetsWriteClient.validate_user_ids": (
        "Sheets write engine transport: dry_run() makes the plan-time @mention id check with "
        "it (the declared dry_run leg carries its contacts endpoint); a caller is sent to "
        "dry_run, never to the check"),
    "larkdocio.sheets.write_client.SheetsWriteClient.put_values_image": (
        "the wire half of the declared put_image_in_sheet leg, which writes the in-cell "
        "picture and re-reads the cell for its verdict; a caller is sent to the leg"),
    **{f"larkdocio.sheets.write_client.SheetsWriteClient.{name}": (
        "the wire half of the declared put_float_image_in_sheet / "
        "remove_float_image_from_sheet legs, which bind or remove the anchor and re-query "
        "the tab for their verdict; a caller is sent to the legs")
       for name in ("create_float_image", "delete_float_image")},
    **{f"larkdocio.sheets.write_client.SheetsWriteClient.{name}": (
        "a write seam of the client (sheets.disposition.WRITE_SEAMS) that no shipped op or "
        "leg calls today and no consumer doc names; its endpoint is the v2 values family "
        "the surface's value rows already carry")
       for name in ("batch_update_values", "prepend_values")},
    **{f"larkdocio.drive.files_write.DriveFilesWriteClient.{name}": (
        "an upload step of put_file_in_folder, which chooses single-shot or chunked and runs "
        "the steps in order; a caller is sent to the operation, never to a step")
       for name in ("upload", "upload_chunked", "upload_prepare", "upload_part",
                    "upload_finish")},
}


#: LD-711 — BaseSchemaClient was exempted WHOLE, on the reason "each method is the wire half of
#: one dispatched schema op descriptor". That reason is kept and is now CHECKED rather than
#: asserted: each method below is held to the declared base-schema-write OPERATION of the same
#: name (a schema op descriptor, which ``_declared_call_sites`` cannot resolve to a callable),
#: and that operation's permission row must carry every endpoint the method reaches. The guide
#: names several of them as direct client calls (``create_app``, ``copy_app``, ``create_field``,
#: ``update_field``, ``delete_field``) beside their plan-level twins, so they are DECLARED call
#: sites through the descriptor row — never transport primitives.
DECLARED_AS_SCHEMA_OPS = {
    f"larkdocio.base.schema_client.BaseSchemaClient.{name}": ("base-schema-write", name)
    for name in ("create_app", "rename_app", "copy_app", "create_table", "batch_create_tables",
                 "rename_table", "create_field", "update_field", "convert_field",
                 "delete_field", "delete_table", "batch_delete_tables")
}


def _declared_call_sites():
    """``{dotted path: surface ids}`` for every declared call site whose row resolves to a
    plain callable — read off the published answer, never off a second list."""
    out = {}
    for surface_id, surface in _capabilities(full=True)["surfaces"].items():
        for row in surface["operations"]:
            target = _resolution.resolve(
                row["name"], row["projected_from"],
                row.get("resolves_by", _resolution.ATTRIBUTE), row.get("entry_point"))
            if callable(target) and hasattr(target, "__qualname__"):
                path = _resolution.entry_point_of(target)
                out.setdefault(path, set()).add(surface_id)
    return out


def _owner(path):
    return path.rpartition(".")[0]


def _exemption(path):
    return TRANSPORT_PRIMITIVES.get(path) or TRANSPORT_PRIMITIVES.get(_owner(path))


def test_every_public_method_of_a_registered_client_is_a_call_site_or_a_named_primitive():
    declared = _declared_call_sites()
    owners = {}
    for path, surfaces in declared.items():
        owners.setdefault(_owner(path), set()).update(surfaces)
    rows = perm.permission_registry()
    carried = {}
    for (surface_id, _op), row in rows.items():
        carried.setdefault(surface_id, set()).update(row.endpoints)
    unheld, uncarried = [], []
    for path, endpoints in perm.shipped_call_sites():
        if _owner(path) not in owners or path in declared:
            continue
        if path in DECLARED_AS_SCHEMA_OPS:
            continue                 # held to its descriptor row by the test below
        if not _exemption(path):
            unheld.append(path)
            continue
        on = set().union(*(carried.get(s, set()) for s in owners[_owner(path)]))
        missing = sorted(set(endpoints) - on)
        if missing:
            uncarried.append((path, missing))
    assert not unheld, (
        "these public methods of a client capabilities() registers reach Lark and are neither "
        "a call site nor a named transport primitive — declare each as an operation, a leg or "
        f"a lifecycle call on its surface: {sorted(unheld)}")
    assert not uncarried, (
        "these exempted primitives reach an endpoint no row on their surface carries, so the "
        f"exemption hides a requirement: {uncarried}")


def test_the_census_carries_drive_files_writes_download_and_permalink():
    declared = _declared_call_sites()
    for name in ("download", "permalink"):
        path = f"larkdocio.drive.files_write.DriveFilesWriteClient.{name}"
        assert declared.get(path) == {"drive-files-write"}, path


def test_every_named_primitive_is_still_a_shipped_UNDECLARED_call_site():
    scanned = {path for path, _endpoints in perm.shipped_call_sites()}
    declared = _declared_call_sites()
    owners = {_owner(p) for p in scanned}
    for key, reason in TRANSPORT_PRIMITIVES.items():
        assert len(reason) > 60, f"{key} is exempted without a real reason"
        if key in owners:            # a whole class: it must still carry an undeclared one
            assert any(_owner(p) == key and p not in declared for p in scanned), (
                f"every API-reaching method of {key} is now declared — the exemption is stale")
        else:
            assert key in scanned, f"{key} no longer reaches Lark — the exemption is stale"
            assert key not in declared, f"{key} is now declared — drop the exemption"


def test_the_census_bites_RED_when_a_declared_leg_is_dropped(monkeypatch):
    """Proven red on the real registry: without the LD-710 legs, ``download`` is unheld."""
    real = _declared_call_sites()
    path = "larkdocio.drive.files_write.DriveFilesWriteClient.download"
    trimmed = {k: v for k, v in real.items() if k != path}
    monkeypatch.setattr(sys.modules[__name__], "_declared_call_sites", lambda: trimmed,
                        raising=True)
    with pytest.raises(AssertionError, match="DriveFilesWriteClient.download"):
        test_every_public_method_of_a_registered_client_is_a_call_site_or_a_named_primitive()


# --------------------------------------------------------------------------- #
# A METHOD THE CONSUMER DOCS NAME IS NEVER A PRIMITIVE (LD-711). The census    #
# above let ``WriteClient`` be exempted whole, and so ``get_block`` — which    #
# the guide's in-cell picture recipe tells a consumer to call — sat outside    #
# capabilities() with a green suite. An exemption's premise is "a caller is    #
# sent elsewhere"; a method the consumer docs call by name refutes it.         #
# --------------------------------------------------------------------------- #

import pathlib
import re

_REPO = pathlib.Path(__file__).resolve().parent.parent

#: Classes still exempted WHOLE — none, and none may return (LD-711). A whole-class entry is
#: how ``get_block`` (WriteClient), ``query_tabs`` / ``put_values`` (SheetsWriteClient) and the
#: direct schema calls (BaseSchemaClient) sat outside capabilities() with a green suite.
_WHOLE_CLASS_EXEMPTIONS = {k for k in TRANSPORT_PRIMITIVES
                           if k.rpartition(".")[2][:1].isupper()}

def _consumer_doc_text():
    docs = [_REPO / "src" / "larkdocio" / "GUIDE.md", _REPO / "README.md",
            *sorted((_REPO / "consumers" / "skills").glob("**/*.md"))]
    for doc in docs[:2]:
        assert doc.is_file(), f"{doc} is missing — the consumer-doc scan would pass vacuously"
    return "\n".join(doc.read_text(encoding="utf-8") for doc in docs)


def _named_in(text, path):
    """``Class.method`` anywhere, or ``<receiver>.method(`` where the docs bind ``receiver``
    to that class (``writer = WriteClient(...)``) — a call a consumer is shown. The receiver
    is resolved rather than wildcarded, because a same-named method on ANOTHER client
    (``media.upload(...)`` on the Base media client) is not a call of this one."""
    cls, _, method = path.rpartition(".")
    short = cls.rpartition(".")[2]
    if re.search(rf"\b{short}\.{method}\b", text):
        return True
    receivers = set(re.findall(rf"\b(\w+) = {short}\b[.(]", text))
    return any(re.search(rf"\b{r}\.{method}\(", text) for r in receivers)


def _documented_exempted(text, primitives):
    return sorted(key for key in primitives
                  if key.rpartition(".")[2][:1].islower() and _named_in(text, key))


def test_no_exempted_method_is_one_the_consumer_docs_tell_a_caller_to_call():
    hits = _documented_exempted(_consumer_doc_text(), TRANSPORT_PRIMITIVES)
    assert not hits, (
        "these methods are exempted as transport primitives, but the guide, the README or a "
        "skill tells a consumer to call them — declare each as a leg (or an operation) on "
        f"its surface instead: {hits}")


def test_no_client_is_exempted_whole():
    assert not _WHOLE_CLASS_EXEMPTIONS, (
        "a whole-class exemption hides every public method of the class, including the ones "
        f"the consumer docs call — name the internal methods one by one: {_WHOLE_CLASS_EXEMPTIONS}")


def test_writeclient_is_exempted_method_by_method_never_whole():
    declared = _declared_call_sites()
    for name in ("get_block", "read_document_revision"):
        path = f"larkdocio.write.client.WriteClient.{name}"
        assert declared.get(path) == {"docx-write"}, path
        assert path not in TRANSPORT_PRIMITIVES, path


def test_sheets_write_client_calls_the_guide_makes_are_declared_legs():
    declared = _declared_call_sites()
    for name in ("put_values", "query_tabs", "query_float_images", "read_values",
                 "read_value_range", "read_sheet_geometry", "read_frozen_panes"):
        path = f"larkdocio.sheets.write_client.SheetsWriteClient.{name}"
        assert declared.get(path) == {"sheets-write"}, path
        assert path not in TRANSPORT_PRIMITIVES, path


def _documented_and_undeclared(text, declared):
    owners = {_owner(path) for path in declared}
    documented = [path for path, _endpoints in perm.shipped_call_sites()
                  if _owner(path) in owners and _named_in(text, path)]
    return documented, sorted(p for p in documented
                              if p not in declared and p not in DECLARED_AS_SCHEMA_OPS)


def test_every_public_method_the_consumer_docs_call_is_a_declared_call_site():
    """The direction stated positively: every API-reaching public method of a registered
    client that the guide, the README or a skill shows a caller calling is a declared call
    site — directly, or through the same-named schema op descriptor that carries it."""
    documented, undeclared = _documented_and_undeclared(
        _consumer_doc_text(), _declared_call_sites())
    assert len(documented) > 10, documented    # the scan must actually find calls
    assert not undeclared, (
        "the consumer docs tell a caller to call these methods, and capabilities() declares "
        f"none of them — declare each as a leg (or an operation) on its surface: {undeclared}")


def test_every_schema_client_method_is_carried_by_its_same_named_declared_operation():
    """The check behind ``DECLARED_AS_SCHEMA_OPS``: the descriptor row exists as a declared
    OPERATION on its surface and its permission row carries every endpoint the method
    reaches, so the direct call's requirement is the row a consumer reads."""
    sites = dict(perm.shipped_call_sites())
    rows = perm.permission_registry()
    surfaces = _capabilities(full=True)["surfaces"]
    for path, (surface_id, op) in DECLARED_AS_SCHEMA_OPS.items():
        assert path in sites, f"{path} no longer reaches Lark — the entry is stale"
        assert op in {row["name"] for row in surfaces[surface_id]["operations"]
                      if row["kind"] == "operation"}, (surface_id, op)
        missing = sorted(set(sites[path]) - set(rows[(surface_id, op)].endpoints))
        assert not missing, (path, missing)


def test_the_documented_call_check_bites_RED_on_a_dropped_leg():
    """Drop one LD-711 Sheets leg from the declaration and the positive check names it."""
    path = "larkdocio.sheets.write_client.SheetsWriteClient.query_tabs"
    declared = {k: v for k, v in _declared_call_sites().items() if k != path}
    _documented, undeclared = _documented_and_undeclared(_consumer_doc_text(), declared)
    assert undeclared == [path]


def test_the_consumer_doc_check_bites_RED_on_a_documented_method_exempted():
    """Proven red on the real docs: exempt ``get_block`` again and the check names it."""
    path = "larkdocio.write.client.WriteClient.get_block"
    planted = {**TRANSPORT_PRIMITIVES, path: "x" * 80}
    assert _documented_exempted(_consumer_doc_text(), planted) == [path]


def test_the_census_bites_RED_when_get_block_is_undeclared(monkeypatch):
    """Drop the LD-711 leg and, with no whole-class exemption left to hide it, the census
    names the method."""
    path = "larkdocio.write.client.WriteClient.get_block"
    trimmed = {k: v for k, v in _declared_call_sites().items() if k != path}
    monkeypatch.setattr(sys.modules[__name__], "_declared_call_sites", lambda: trimmed,
                        raising=True)
    with pytest.raises(AssertionError, match="WriteClient.get_block"):
        test_every_public_method_of_a_registered_client_is_a_call_site_or_a_named_primitive()
