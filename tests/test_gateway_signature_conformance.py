"""LD-220 / LD-241 / LD-306 — the guard that holds every **client double** under ``tests/`` to
its real client's signature. **N clients, one table.**

The 2026-08-01 refactor audit (§A T3a) AST-swept ``tests/`` for classes standing in for
:class:`~larkdocio.sheets.write_client.SheetsWriteClient` and found **22 gateway doubles /
1,712 lines**, of which **78 methods across 17 method names took parameters whose *names*
diverged from the real client** — ``read_revision(token)`` for the real
``read_revision(spreadsheet_token)``, ``put_values(token, a1, values)`` for
``put_values(spreadsheet_token, a1_range, values)``, and
``insert_dimension_range(...)`` missing the real ``inherit_style`` entirely.

Every one of those passed only because the apply engine calls **positionally**. The day a
production call site switches to a keyword — or the real signature grows a parameter, as
``insert_dimension_range`` already did — the doubles go on agreeing with **each other** and
stop agreeing with the client, and the suite stays green while the contract rots. That is
precisely the failure ``guide_recipes.double_signature_mismatches()`` catches for the *recipe*
doubles; before LD-220 it caught nothing on these nineteen files.

**LD-241 — what the 08-03 re-audit measured and this module now fixes (§B F3).** As shipped,
this guard was hard-wired to *one* client (``CLIENT_CLASS = "SheetsWriteClient"``) and *one*
four-name predicate (``GATEWAY_MARKERS = ("read_revision", "put_values", "batch_update_style",
"merge_cells")``), so its "zero registration" promise held only for doubles of that client that
happened to name one of those four methods. Two holes followed, both now closed:

* **Hole 1 — the docx write client had no guard at all.** :class:`larkdocio.write.client.
  WriteClient` (11 public methods) is stood in for by **5** classes under ``tests/``, **2** of
  which diverged on **4** method signatures, undeclared anywhere.
* **Hole 2 — the 4-name predicate let sheets doubles through.** Sweeping the real client's full
  23-method public surface instead of the 4 markers pulls in **8** further classes the guard
  never asked about (``SpyStyler`` / ``ExplodingStyler``, ``_Geo`` / ``_NoRenderOption``,
  ``NoRenderGateway``, ``SheetsLifecycleGateway`` / ``FakeGateway``,
  ``RecordingLifecycleClient``) — some legitimate token-bound facades of the ``Disposable``/D7
  kind, but the guard never asked, so the distinction was unrecorded either way.

**The shape: a table of client rows.** :data:`CLIENT_ROWS` holds one :class:`ClientRow` per real
client under the guard — ``docx``, ``sheets``, and (LD-306) the **four Base clients**
``base-write`` / ``base-schema`` / ``base-read`` / ``base-media``. **A further client enrols by
adding one row and nothing else**:

.. code-block:: python

    ClientRow(
        label="base-write",
        source=REPO_ROOT / "src" / "larkdocio" / "base" / "write_client.py",
        class_name="BaseWriteClient",
        audit_enumerated=frozenset({("test_base_apply.py", "FakeBase"), ...}),
        pinned={"batch_create_records": ["app_token", "table_id", "rows"]},
    )

and every check below — discovery, the divergence sweep, the floor, the declaration inventory —
picks it up unchanged. ``test_a_third_client_enrols_by_one_row_and_nothing_else`` proves that on
a synthetic client rather than asserting it in prose.

**LD-306 — the Base surface takes the row it shipped without (08-06 audit §T2, the correctness
find).** LD-241 bought the generalization above precisely so the next surface's enrolment would
be a one-row change; the Base write spec/016's Base surface then shipped **without taking the row**, leaving
**34 double classes across 19 files** — every class under ``tests/`` naming a public method of one
of the four Base clients — under no guard at all. The paragraph above used to *pre-write* a single
``label="base"`` row with a ``pinned={"update_records": ...}`` method that does not exist on any
shipped client; both are now corrected against the code (B7). What the enrolment measured:

* **11 divergences**, not the audit's 12 — **3** real name/arity mismatches and **8**
  ``(*args, **kwargs)``-shaped exploders. The audit's twelfth was ``_InertReadClient``
  (``test_live_base_write_gate.py``), which the guard now *asks* and finds **conformant**; the
  distinction the audit wanted recorded is recorded by that fact, not by a declaration.
* **2 mismatches were fixed at the double** — ``WorldWriteClient.batch_create_records``
  (``records`` → the client's ``rows``) and ``ScriptedFieldClient.convert_field``, whose three
  trailing parameters were positional where the real client makes them **keyword-only** after a
  ``*``. The engine already calls them by keyword (``base/schema_ops_fields.py::_issue_convert``),
  so the double was flattening a boundary the client draws.
* **1 mismatch was declared**, with the reason being the find: ``_FakeMedia.download`` doubles the
  pinned **SDK** ``drive.v1.media`` seam, not ``BaseMediaClient``.

**Two structural consequences the four rows forced** (Out of Scope allows exactly this):

1. :data:`DECLARED_DIVERGENT` is now keyed ``(label, file, class, method)``. The old flat key was
   sound only while "no class doubles two clients and no method name is shared" — the very test
   below said so, and told its successor to *"key DECLARED_DIVERGENT by client label"* first.
   Both halves stop holding for the Base family: a Base test world routinely doubles the read
   **and** the write client at once (``test_base_apply.py::FakeBase``, ``Boom``), and the four
   clients each redeclare the shared transport accessors.
2. Cross-client method-name overlap is confined to :data:`SHARED_CLIENT_SURFACE` — the accessors
   and credential constructors every client carries (``api_calls``, ``limiter``,
   ``from_read_credentials``, ``from_write_credentials``). A *gateway* method name shared by two
   rows still reddens, so the invariant kept its bite instead of being deleted.

**How each row's pool is found: by predicate, never by a file list.** A class belongs to a row's
pool iff it defines **any public method name of that row's real client** (LD-241 widened this
from LD-220's hand-listed 4), anywhere under ``tests/``, at module level *or* nested inside a
function body (two of the audit's 22 are). So a double added in a brand-new file comes under the
guard with **zero registration** — now for real, and for every registered client.

**The comparison is an AST one, on both sides**: the doubles are AST-walked (a nested class is
not importable, and a name in a docstring is not a definition), and each real client's public
signatures are read out of its own ``ClassDef`` — never re-typed here, so the client is the
single source of truth for its own parameter names.

**The escape hatch is data, not silence.** :data:`DECLARED_DIVERGENT` records the doubles that
legitimately do *not* mirror their client, one row per method with its reason (LD-212's proven
pattern in ``tests/test_write_harness_double_ownership.py``), keyed
``(client label, file, class, method)`` — one inventory across all rows, unambiguous because the
label is in the key (itself a test below). It is **tight in both directions**: an undeclared
divergence reddens, and a declared row that no longer diverges reddens too — no stale
suppressions. **A row with no written reason is not a declaration**: the reason is what a reader
gets instead of the bite that was spent.

Disjoint from LD-212 by construction: that guard owns the **transport** doubles
(``_FakeHTTPResponse`` / ``FakeClock`` / ``StubOpener``); this one owns the **client** doubles.
Neither should ever be folded into the other.
"""
import ast
import functools
import pathlib
from typing import NamedTuple

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent


class ClientRow(NamedTuple):
    """One real write client under the guard. **Adding a client is adding one of these.**

    ``audit_enumerated`` is the ``(relpath, class)`` floor discovery must still reach — NOT the
    pool, which is discovered — so a predicate that silently stops matching reddens instead of
    passing vacuously. ``pinned`` is a handful of ``method -> positional params`` the reader
    must actually find on the real class, so a mis-pointed row reddens loudly rather than
    reporting an empty surface.
    """

    label: str
    source: pathlib.Path
    class_name: str
    audit_enumerated: frozenset
    pinned: dict


#: The 22 (file, class) pairs the 08-01 audit enumerated for the sheets client (§A T3a, the
#: 15-row table + the 7 smaller sites), PLUS the 8 the 08-03 re-audit measured once the
#: predicate widened to the client's whole public surface (§B F3 hole 2). A floor, never a list.
_SHEETS_ENUMERATED = frozenset({
    # --- LD-220, the 08-01 audit's 22 (unchanged, unweakened) ---
    ("offline_doubles.py", "OfflineSheetsWriteClient"),
    ("test_sheets_destructive_safe_apply.py", "FakeAllOpsGateway"),
    ("test_revision_guard_never_silent.py", "FakeRevisionGateway"),
    ("test_sheets_tab_presentation.py", "TabGateway"),
    ("test_sheets_merge_tab_apply.py", "FakeMergeTabGateway"),
    ("test_sheets_dispatch_characterization.py", "DispatchGateway"),
    ("test_sheets_freeze_panes.py", "FreezeGateway"),
    ("test_sheets_plan_disclosure_completion.py", "Gateway"),
    ("test_sheets_structural_apply.py", "FakeStructuralGateway"),
    ("test_sheets_formula_write.py", "FormulaAwareGateway"),
    ("test_sheets_style_write.py", "FakeStyleGateway"),
    ("test_sheets_dimension_properties.py", "FakeDimensionGateway"),
    ("test_apply_disposition_invariant.py", "InjectingGateway"),
    ("sheets_write_harness.py", "Disposable"),
    ("test_refusal_truth.py", "TabAwareGateway"),
    ("test_sheets_write_apply.py", "FakeSheetGateway"),
    ("test_guide.py", "_FakeSheetGateway"),
    ("test_refusal_truth.py", "NoQueryTabsGateway"),
    ("test_live_sheets_disposition_gate_offline.py", "Inner"),
    ("test_sheets_write_harness.py", "SpyWriter"),
    ("test_sheets_write_harness.py", "ExplodingWriter"),
    ("test_apply_disposition_invariant.py", "Minimal"),
    # --- LD-241, the 8 the widened predicate newly reaches (08-03 audit §B F3 hole 2) ---
    ("sheets_write_harness.py", "SheetsLifecycleGateway"),
    ("test_sheets_formula_write.py", "_Geo"),
    ("test_sheets_formula_write.py", "_NoRenderOption"),
    ("test_sheets_plan_disclosure_completion.py", "NoRenderGateway"),
    ("test_sheets_write_harness.py", "ExplodingStyler"),
    ("test_sheets_write_harness.py", "FakeGateway"),
    ("test_sheets_write_harness.py", "RecordingLifecycleClient"),
    ("test_sheets_write_harness.py", "SpyStyler"),
})

#: The 5 (file, class) pairs the 08-03 re-audit measured standing in for the docx
#: ``WriteClient`` (§B F3 hole 1). Same floor discipline as the sheets row.
_DOCX_ENUMERATED = frozenset({
    ("offline_doubles.py", "OfflineDocument"),
    ("offline_doubles.py", "OfflineWriteClient"),
    ("test_docx_ledger.py", "FakeWriteClient"),
    ("test_live_write_authoring_gate_offline.py", "_LostCellText"),
    ("test_mermaid_create_only.py", "_Client"),
})

#: The four Base pools, measured 2026-08-06 on this tree by the same predicate (LD-306, the
#: 08-06 audit §T2). **Every member is listed, not just the "interesting" ones** — a class that
#: joins a pool only by naming a shared accessor (:data:`SHARED_CLIENT_SURFACE`) is still a class
#: the guard asked about, and B2's contract is that none is left unasked. Union across the four:
#: **34 classes / 19 files**, the population the audit counted (pinned below).
_BASE_WRITE_ENUMERATED = frozenset({
    # --- stands in on the client's own gateway surface ---
    ("offline_doubles.py", "OfflineBaseWriteClient"),
    ("test_base_apply.py", "FakeBase"),
    ("test_base_apply.py", "Boom"),
    ("test_base_field_migration.py", "WorldWriteClient"),
    ("test_live_base_field_migration.py", "_MangledCopy"),
    # --- joins by a shared accessor only (api_calls / limiter / from_write_credentials) ---
    ("offline_doubles.py", "OfflineBaseReadClient"),
    ("offline_doubles.py", "OfflineBaseSchemaClient"),
    ("offline_doubles.py", "OfflineBaseMediaClient"),
    ("offline_doubles.py", "OfflineCommentsReadClient"),
    ("offline_doubles.py", "OfflineSheetsWriteClient"),
    ("sheets_write_harness.py", "SheetsLifecycleGateway"),
    ("test_base_raw_values.py", "SpyClient"),
    ("test_sheets_freeze_panes.py", "FreezeGateway"),
})

_BASE_SCHEMA_ENUMERATED = frozenset({
    ("base_destructive_fakes.py", "ScriptedDestructiveClient"),
    ("base_schema_fakes.py", "ScriptedSchemaClient"),
    ("offline_doubles.py", "OfflineBaseSchemaClient"),
    ("test_base_field_migration.py", "WorldSchemaClient"),
    ("test_base_schema_fields.py", "ScriptedFieldClient"),
    # --- shared-accessor members ---
    ("offline_doubles.py", "OfflineBaseReadClient"),
    ("offline_doubles.py", "OfflineBaseWriteClient"),
    ("offline_doubles.py", "OfflineBaseMediaClient"),
    ("offline_doubles.py", "OfflineCommentsReadClient"),
    ("offline_doubles.py", "OfflineSheetsWriteClient"),
    ("sheets_write_harness.py", "SheetsLifecycleGateway"),
    ("test_base_raw_values.py", "SpyClient"),
    ("test_sheets_freeze_panes.py", "FreezeGateway"),
})

_BASE_READ_ENUMERATED = frozenset({
    ("base_destructive_fakes.py", "ScanWorld"),
    ("base_schema_fakes.py", "FakeBaseWorld"),
    ("offline_doubles.py", "OfflineBaseReadClient"),
    ("test_base_apply.py", "FakeBase"),
    ("test_base_apply.py", "Boom"),
    ("test_base_link_resolution.py", "SpyClient"),
    ("test_base_link_resolution.py", "_Client"),
    ("test_base_raw_values.py", "SpyClient"),
    ("test_base_referential.py", "_SpyClient"),
    ("test_base_row_hierarchy.py", "_ViewStore"),
    ("test_base_schema_fields.py", "FieldWorld"),
    ("test_base_schema_views.py", "_RecordingReadClient"),
    ("test_base_table.py", "_FakeClient"),
    ("test_base_table.py", "_Exploding"),
    ("test_base_view_filters.py", "_Read"),
    ("test_embedded_base_deep_read.py", "ExplodingBaseClient"),
    ("test_live_base_write_gate.py", "_InertReadClient"),
    # --- shared-accessor members ---
    ("offline_doubles.py", "OfflineBaseWriteClient"),
    ("offline_doubles.py", "OfflineBaseSchemaClient"),
    ("offline_doubles.py", "OfflineBaseMediaClient"),
    ("offline_doubles.py", "OfflineSheetsReadClient"),
    ("offline_doubles.py", "OfflineSheetsExportReader"),
    ("offline_doubles.py", "OfflineCommentsReadClient"),
    ("offline_doubles.py", "OfflineContactsSearchClient"),
    ("test_sheets_freeze_panes.py", "FreezeGateway"),
})

_BASE_MEDIA_ENUMERATED = frozenset({
    ("offline_doubles.py", "OfflineBaseMediaClient"),
    ("test_base_media.py", "_FakeMedia"),
    # --- shared-accessor members ---
    ("offline_doubles.py", "OfflineBaseReadClient"),
    ("offline_doubles.py", "OfflineBaseWriteClient"),
    ("offline_doubles.py", "OfflineBaseSchemaClient"),
    ("offline_doubles.py", "OfflineCommentsReadClient"),
    ("offline_doubles.py", "OfflineSheetsWriteClient"),
    ("sheets_write_harness.py", "SheetsLifecycleGateway"),
    ("test_base_raw_values.py", "SpyClient"),
    ("test_sheets_freeze_panes.py", "FreezeGateway"),
})

#: The only method names two client rows may share: the transport accessors and credential
#: constructors **every** client redeclares in its own body. They can never carry a positional
#: divergence (``api_calls`` / ``limiter`` take nothing), so they add pool members rather than
#: bite — which is right, B2 wants every class *asked*. A **gateway** name shared by two rows is
#: a different animal and still reddens (see the test below).
SHARED_CLIENT_SURFACE = frozenset({
    "api_calls", "limiter", "from_read_credentials", "from_write_credentials",
})

#: **The table.** One row per real client. A further client joins by appending one row (see the
#: module docstring for its exact shape). Kept label-sorted — the first test below pins that.
CLIENT_ROWS = (
    ClientRow(
        label="base-media",
        source=REPO_ROOT / "src" / "larkdocio" / "base" / "media.py",
        class_name="BaseMediaClient",
        audit_enumerated=_BASE_MEDIA_ENUMERATED,
        pinned={
            "download": ["file_token"],
        },
    ),
    ClientRow(
        label="base-read",
        source=REPO_ROOT / "src" / "larkdocio" / "base" / "client.py",
        class_name="BaseReadClient",
        audit_enumerated=_BASE_READ_ENUMERATED,
        pinned={
            "search_records": ["app_token", "table_id"],
            "list_fields": ["app_token", "table_id"],
        },
    ),
    ClientRow(
        label="base-schema",
        source=REPO_ROOT / "src" / "larkdocio" / "base" / "schema_client.py",
        class_name="BaseSchemaClient",
        audit_enumerated=_BASE_SCHEMA_ENUMERATED,
        pinned={
            # five positional, then a ``*``: the keyword-only boundary a double flattened.
            "convert_field": ["app_token", "table_id", "field_id", "field_name", "field_type"],
            "delete_field": ["app_token", "table_id", "field_id"],
        },
    ),
    ClientRow(
        label="base-write",
        source=REPO_ROOT / "src" / "larkdocio" / "base" / "write_client.py",
        class_name="BaseWriteClient",
        audit_enumerated=_BASE_WRITE_ENUMERATED,
        pinned={
            "batch_create_records": ["app_token", "table_id", "rows"],
            "update_record": ["app_token", "table_id", "record_id", "fields"],
        },
    ),
    ClientRow(
        label="docx",
        source=REPO_ROOT / "src" / "larkdocio" / "write" / "client.py",
        class_name="WriteClient",
        audit_enumerated=_DOCX_ENUMERATED,
        pinned={
            "create_children": ["document_id", "block_id", "children", "index"],
            "batch_delete": ["document_id", "block_id", "start_index", "end_index"],
        },
    ),
    ClientRow(
        label="sheets",
        source=REPO_ROOT / "src" / "larkdocio" / "sheets" / "write_client.py",
        class_name="SheetsWriteClient",
        audit_enumerated=_SHEETS_ENUMERATED,
        pinned={
            "read_revision": ["spreadsheet_token"],
            "put_values": ["spreadsheet_token", "a1_range", "values"],
        },
    ),
)

ROW_BY_LABEL = {row.label: row for row in CLIENT_ROWS}
SHEETS = ROW_BY_LABEL["sheets"]
DOCX = ROW_BY_LABEL["docx"]
BASE_WRITE = ROW_BY_LABEL["base-write"]
BASE_SCHEMA = ROW_BY_LABEL["base-schema"]
BASE_READ = ROW_BY_LABEL["base-read"]
BASE_MEDIA = ROW_BY_LABEL["base-media"]
BASE_ROWS = (BASE_MEDIA, BASE_READ, BASE_SCHEMA, BASE_WRITE)

#: ``(client label, relpath, class, method) -> reason``. A double method that deliberately does
#: NOT mirror its client's signature. Keyed without a line number on purpose: an unrelated edit
#: above it must not churn this inventory, but a rename of the file/class/method must. **The
#: label is part of the key since LD-306** — a Base test world doubles the read and the write
#: client at once, so a bare ``(file, class, method)`` could no longer name one contract.
DECLARED_DIVERGENT = {
    # ------------------------------------------------------------------ drive, LD-449 --- #
    ("base-media", "test_drive_chunked_upload.py", "_FakeFile", "download"): (
        "the chunked half's twin of the LD-434 row below, and for exactly the same reason: it "
        "doubles the pinned SDK's own ``drive.v1.file`` RESOURCE — which takes a built request "
        "object — and is caught by the predicate only because that resource and the media "
        "client happen to name the same leg 'download'. It carries upload_prepare / "
        "upload_part / upload_finish beside it, none of which the media client has at all."
    ),
    # ------------------------------------------------------------------ drive, LD-434 --- #
    ("base-media", "test_drive_files_write.py", "_FakeFile", "download"): (
        "NOT a media-client double at all — it doubles the pinned SDK's own "
        "``drive.v1.file`` RESOURCE, which takes a built request object, and it is caught by "
        "the predicate only because the SDK resource and the media client happen to name the "
        "same leg 'download'. Mirroring BaseMediaClient.download(file_token) here would make "
        "the double stop resembling the thing it actually stands in for."
    ),
    # ------------------------------------------------------------------ sheets, LD-220 --- #
    ("sheets", "sheets_write_harness.py", "Disposable", "put_values"): (
        "NOT a gateway double — a live disposable spreadsheet BOUND TO ITS OWN TOKEN (D7). "
        "Its whole invariant is that 'there is no way to point them at another document'; "
        "taking a spreadsheet_token would destroy it. It matches the predicate only because "
        "it names its delegating leg after the client's."
    ),
    ("sheets", "sheets_write_harness.py", "Disposable", "put_style"): (
        "Same D7 token-bound facade as Disposable.put_values — delegates to the injected "
        "styler with self.token bound."
    ),
    ("sheets", "sheets_write_harness.py", "Disposable", "append_values"): (
        "Same D7 token-bound facade as Disposable.put_values."
    ),
    ("sheets", "sheets_write_harness.py", "Disposable", "read_values"): (
        "Same D7 token-bound facade as Disposable.put_values."
    ),
    ("sheets", "test_sheets_write_harness.py", "ExplodingWriter", "put_values"): (
        "A deliberate ``(*a, **k)`` exploder proving the harness's finally-delete fires on a "
        "mid-populate crash. It accepts EVERY call shape, so it cannot drift from the client; "
        "pinning it to the client's parameter names would only make the test lie about what "
        "it exercises."
    ),
    # ------------------------------------- sheets, LD-241 (the widened predicate's 8) --- #
    # TRANSFORMED, NOT DELETED — the two lifecycle-create rows that used to sit here.
    #
    # THE REASON THEY EXISTED, preserved: the harness's lifecycle seam took a title only,
    # never the client's folder_token, because a disposable was minted in the WRITE app's
    # DEFAULT location and nowhere a caller chooses (D7 — "none of them accepts an
    # externally-sourced doc URL/token as a target"), and accepting a folder was read as
    # widening the live harness's blast radius.
    #
    # THE CONCLUSION IS SUPERSEDED: the default location is the application's own space, which
    # no human interface can see — so "the default" was never the safe choice, it was the
    # unrecoverable one. The seam now takes the destination (a folder a human owns, named by
    # LARKDOCIO_DISPOSABLES_FOLDER), which NARROWS the blast radius rather than widening it:
    # every disposable lands somewhere the account holder can open and delete. D7's rule that
    # no target is externally sourced is untouched — the object is still one the harness made.
    # With the seam mirroring the client, the rows no longer diverge, and a stale suppression
    # is what this guard's own second direction exists to catch.
    ("sheets", "test_sheets_formula_write.py", "_NoRenderOption", "read_values"): (
        "The MISSING value_render_option IS the test: this seam exists to prove that a "
        "duck-typed gateway which cannot serve a render read is refused with INVALID_REQUEST "
        "naming value_render_option. Carrying the parameter would delete the case."
    ),
    ("sheets", "test_sheets_plan_disclosure_completion.py", "NoRenderGateway", "read_values"): (
        "Same deliberate omission as _NoRenderOption.read_values — it proves the disclosure "
        "leg DEGRADES (best-effort, no crash) on a seam without value_render_option. "
        "Carrying the parameter would delete the case."
    ),
    ("sheets", "test_sheets_write_harness.py", "ExplodingStyler", "put_style"): (
        "The style-leg twin of the already-declared ExplodingWriter.put_values: a deliberate "
        "``(*a, **k)`` exploder proving the harness's finally-delete fires on a mid-style "
        "crash. It accepts EVERY call shape, so it cannot drift from the client."
    ),
    # -------------------------------------------------------------------- docx, LD-471 --- #
    ("docx", "offline_doubles.py", "OfflineDocxReadClient", "read_document_revision"): (
        "WRONG CLIENT, not wrong signature: this double stands in for the docx READ client "
        "(``larkdocio.read.client.Client``), whose own definition of this method takes "
        "``doc_token`` — the double mirrors ITS client exactly. It is caught by this row only "
        "because the WRITE client happens to carry a method of the same name (spelled "
        "``document_id``, and doubled conformingly by OfflineWriteClient right beside it). "
        "Renaming it here would make the double stop resembling the client it doubles."
    ),
    # -------------------------------------------------------------------- docx, LD-241 --- #
    ("docx", "offline_doubles.py", "OfflineDocument", "create_children"): (
        "NOT a client double — an in-memory docx BOUND TO ONE document token, shared by the "
        "read and write doubles (LD-137). It IS the document, so it takes no document_id; the "
        "client-shaped surface belongs to OfflineWriteClient, which wraps it and DOES conform. "
        "Same document-bound-facade shape as the sheets Disposable (D7)."
    ),
    ("docx", "offline_doubles.py", "OfflineDocument", "create_descendant"): (
        "Same document-bound facade as OfflineDocument.create_children — one document, so no "
        "document_id parameter, and the parent block is named parent_id for symmetry with the "
        "other two writes on this class; OfflineWriteClient.create_descendant carries the "
        "client-shaped signature and DOES conform."
    ),
    ("docx", "offline_doubles.py", "OfflineDocument", "batch_delete"): (
        "Same document-bound facade as OfflineDocument.create_children — one document, so no "
        "document_id parameter; OfflineWriteClient carries the client-shaped signature."
    ),
    # ------------------------------------------------------- base, LD-306 (nine rows) --- #
    # Each was READ at its site before being written down; the anti-goal for this issue is a
    # blanket declaration, so the reason below says what that particular double is FOR and why
    # the client's parameter names would be the wrong thing for it to carry.
    ("base-media", "test_base_media.py", "_FakeMedia", "download"): (
        "WRONG LAYER, not wrong signature: _FakeMedia doubles the pinned SDK seam "
        "``drive.v1.media`` — _FakeSDK wires it in as ``sdk.drive.v1.media`` — not "
        "BaseMediaClient, which is the thing under test on the other side of it. Its sibling "
        "``upload_all(request)`` is an SDK method name with no client counterpart at all, which "
        "is the giveaway. The SDK's download takes a REQUEST OBJECT and this double reads "
        "``request.file_token`` off it; renaming the parameter to the client's ``file_token`` "
        "would name an SDK request 'file_token' and make the double lie about which contract it "
        "mirrors. It matches the predicate only because the client named its own leg after the "
        "SDK's."
    ),
    ("base-write", "test_base_apply.py", "Boom", "batch_update_records"): (
        "A deliberate ``(*_a, **_k)`` exploder, nested inside "
        "test_ac6_the_write_watch_reports_only_a_seam_that_RETURNED: it raises LarkAPIError so "
        "the test can prove WriteWatch reports a seam as *issued* but not *completed*. It "
        "accepts EVERY call shape, so it cannot drift from the client; pinning it to "
        "``app_token, table_id, updates`` would only make the test lie about what it exercises. "
        "Same shape as the already-declared sheets ExplodingWriter.put_values."
    ),
    ("base-read", "test_base_apply.py", "Boom", "list_tables"): (
        "The read leg of the same ``(*_a, **_k)`` exploder — Boom is one class doubling the "
        "write client AND the read client, which is why this inventory now carries the client "
        "label in its key. ``list_tables`` returns ``[]`` so the anchor read the apply engine "
        "does can complete while the write seam blows up; a positional signature would add "
        "nothing to that."
    ),
    ("base-read", "test_base_table.py", "_Exploding", "get_app"): (
        "A ``(*a, **k)`` tripwire whose body is ``raise AssertionError('unreachable')``, "
        "declared inside test_ac7_the_read_surface_does_NOT_list_views to NAME the two ops the "
        "L1 read surface must never call. It is never instantiated — the test reads "
        "base_read's own source — so its parameters are documentation of an op name, not a call "
        "shape."
    ),
    ("base-read", "test_base_table.py", "_Exploding", "list_views"): (
        "Same never-instantiated tripwire as _Exploding.get_app, and this is the op the test is "
        "actually about: a view is not a projection, so L1 calling ``list_views`` would be a "
        "per-table API call bought for nothing. Carrying ``app_token, table_id`` here would "
        "dress a source-text assertion up as a gateway."
    ),
    ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "get_app"): (
        "A ``(*a, **k)`` exploder whose every method raises with a message naming itself, so "
        "AC5's call-count spy can prove that with the embedded-Base deep-read flag OFF the "
        "handlers issue NO Base API call at all. The proof is that the call never happens; a "
        "signature the call could satisfy is exactly what it must not have."
    ),
    ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "list_tables"): (
        "Same flag-OFF exploder as ExplodingBaseClient.get_app — this is the leg that would "
        "fire if the deep-read walked the app's tables while the flag is off."
    ),
    ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "list_fields"): (
        "Same flag-OFF exploder as ExplodingBaseClient.get_app — the per-table schema read, "
        "which is the costliest thing a wrongly-enabled deep read would issue."
    ),
    ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "search_records"): (
        "Same flag-OFF exploder as ExplodingBaseClient.get_app — the paginated record read. "
        "Note its conformant counterpart in the same file: the real BaseReadClient built by "
        "_client_with(...) IS used when the flag is on, so this file holds both sides."
    ),
}


# --------------------------------------------------------------------------- #
# the two AST readers — both row-parameterized                                 #
# --------------------------------------------------------------------------- #

def _positional_params(fn):
    """The positional parameter **names** of ``fn``, in order, minus ``self``.

    ``*args`` / ``**kwargs`` / keyword-only parameters are deliberately not included: the
    contract this guard holds is the *positional* call shape the apply engine actually uses.
    A pure ``(*a, **k)`` double therefore reads as ``[]`` and diverges — which is right, it
    mirrors nothing — and is handled by declaring it.
    """
    args = fn.args
    return [p.arg for p in (args.posonlyargs + args.args)][1:]


def _methods(node):
    return {
        m.name: _positional_params(m)
        for m in node.body
        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


@functools.lru_cache(maxsize=None)
def _real_signatures(source, class_name, label):
    tree = ast.parse(pathlib.Path(source).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return tuple((n, tuple(p)) for n, p in _methods(node).items()
                         if not n.startswith("_"))
    raise AssertionError(
        f"{class_name} is no longer defined in {source} — re-point the {label!r} row of "
        "CLIENT_ROWS"
    )


def real_signatures(row):
    """``method name -> positional parameter names`` for every PUBLIC method ``row``'s real
    client defines, read out of its own source. The client is the source of truth."""
    return {n: list(p) for n, p in _real_signatures(row.source, row.class_name, row.label)}


@functools.lru_cache(maxsize=None)
def _class_defs(root):
    """Every ``ClassDef`` under ``root``, AST-swept **once** per root.

    LD-306 took the row count from 2 to 6, and every row asks the same question of the same
    ~290 files across ~100 parametrizations. Re-parsing the tree per question cost the suite
    minutes of wall clock and told nobody anything new, so the sweep is memoized — keyed by
    root, in an immutable form, so no caller can mutate another's answer. Purely a cost move:
    the tree is read-only for the whole run.
    """
    root = pathlib.Path(root)
    out = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                out.append((
                    str(path.relative_to(root)), node.lineno, node.name,
                    tuple((n, tuple(p)) for n, p in _methods(node).items()),
                ))
    return tuple(out)


def public_surface(row):
    """**The predicate.** Any public method name of the real client — derived, never listed.

    LD-220 hand-listed four names here; LD-241 replaced that literal with this, which is why
    the sheets pool went 22 → 30 and the docx client got a pool at all.
    """
    return frozenset(real_signatures(row))


def client_doubles(row, root):
    """Every double of ``row``'s client under ``root``, discovered by :func:`public_surface`.

    Returns a sorted list of ``(relpath, lineno, class name, {method: params})``. Uses
    ``ast.walk``, so a double nested inside a test function body is found too (two of the
    audit's 22 are), and a mere mention in prose never is.
    """
    surface = public_surface(row)
    found = []
    for relpath, lineno, name, methods in _class_defs(pathlib.Path(root)):
        if {n for n, _p in methods} & surface:
            found.append((relpath, lineno, name, {n: list(p) for n, p in methods}))
    return sorted(found, key=lambda entry: entry[:3])


class Divergence(NamedTuple):
    relpath: str
    cls: str
    method: str
    got: list
    want: list


def divergences(row, root):
    """Every :class:`Divergence` under ``root`` whose parameter names/order differ from
    ``row``'s real client. A double method with no counterpart on the client is a test-local
    helper, not a stand-in, and is not this guard's business."""
    real = real_signatures(row)
    out = []
    for relpath, _cls_line, cls, methods in client_doubles(row, root):
        for name, got in sorted(methods.items()):
            if name.startswith("_") or name not in real:
                continue
            if got != real[name]:
                out.append(Divergence(relpath, cls, name, got, real[name]))
    return out


def undeclared(row, root):
    """The divergences with no :data:`DECLARED_DIVERGENT` row — the ones that must redden."""
    return [d for d in divergences(row, root)
            if (row.label, d.relpath, d.cls, d.method) not in DECLARED_DIVERGENT]


def _cite(row, d):
    return (f"{d.relpath}: {d.cls}.{d.method}({', '.join(d.got)}) "
            f"!= {row.class_name}.{d.method}({', '.join(d.want)})")


def _rows():
    return [pytest.param(row, id=row.label) for row in CLIENT_ROWS]


def _pool_params():
    out = []
    for row in CLIENT_ROWS:
        for relpath, _l, cls, _m in client_doubles(row, TESTS_DIR):
            out.append(pytest.param(row, relpath, cls, id=f"{row.label}-{relpath}::{cls}"))
    return out


# --------------------------------------------------------------------------- #
# AC1 — the table: N clients, and a third enrols by ONE row                     #
# --------------------------------------------------------------------------- #

def test_the_guard_covers_every_registered_client_and_at_least_sheets_docx_and_the_four_base():
    labels = [row.label for row in CLIENT_ROWS]
    assert labels == sorted(set(labels)), f"duplicate/unsorted client rows: {labels}"
    assert {"sheets", "docx"} <= set(labels), (
        "LD-241 registered both write clients; a row was dropped: " + str(labels)
    )
    assert {"base-write", "base-schema", "base-read", "base-media"} <= set(labels), (
        "LD-306 enrolled all four Base clients — the surface shipped once already with the row "
        "the docstring had pre-written for it missing; a dropped row is that hole reopening: "
        + str(labels)
    )
    for row in CLIENT_ROWS:
        assert row.source.exists(), f"{row.label}: {row.source} is gone — re-point the row"


def test_each_base_row_points_at_the_client_the_audit_named():
    """B1's four clients, by class and by measured public-surface size (08-06 audit §T2, with
    Maintainer's corrected line refs). A row re-pointed at a neighbouring class reddens here rather than
    reporting a plausible-looking but wrong pool."""
    measured = {
        "base-write": ("BaseWriteClient", 9),
        # 15 → 16 at LD-466: the whole-Base delete joined this client, beside the create it
        # undoes — a lifecycle call, not a sixteenth schema op.
        "base-schema": ("BaseSchemaClient", 16),
        "base-read": ("BaseReadClient", 11),
        # 5 → 6 at LD-450: the permalink leg joined upload/download on this client.
        "base-media": ("BaseMediaClient", 6),
    }
    for label, (class_name, count) in measured.items():
        row = ROW_BY_LABEL[label]
        assert row.class_name == class_name
        surface = public_surface(row)
        assert len(surface) == count, (
            f"{class_name} now has {len(surface)} public methods, not the {count} the audit "
            f"measured: {sorted(surface)}. Re-count deliberately — the pools move with it."
        )


def test_a_third_client_enrols_by_one_row_and_nothing_else(tmp_path):
    """AC1, proven rather than asserted: a client this module has never heard of comes fully
    under the guard by constructing **one** :class:`ClientRow` — no edit to any function, any
    predicate, or any other row. This is exactly the shape the Base write spec/016's Base write client
    will add (see the module docstring)."""
    src = tmp_path / "base_write_client.py"
    src.write_text(
        "class BaseWriteClient:\n"
        "    def update_records(self, app_token, table_id, records):\n"
        "        return {}\n"
        "\n"
        "    def delete_field(self, app_token, table_id, field_id):\n"
        "        return {}\n"
        "\n"
        "    def _private(self, whatever):\n"
        "        return whatever\n"
    , encoding="utf-8")
    tests = tmp_path / "basetests"
    tests.mkdir()
    (tests / "test_base_apply.py").write_text(
        "class FakeBaseGateway:\n"
        "    def update_records(self, app_token, table_id, records):\n"
        "        return {}\n"
        "\n"
        "    def delete_field(self, token, table_id, field_id):\n"
        "        return {}\n"
    , encoding="utf-8")
    base = ClientRow(
        label="base",
        source=src,
        class_name="BaseWriteClient",
        audit_enumerated=frozenset({("test_base_apply.py", "FakeBaseGateway")}),
        pinned={"delete_field": ["app_token", "table_id", "field_id"]},
    )

    assert public_surface(base) == {"update_records", "delete_field"}
    found = divergences(base, tests)
    assert [(d.cls, d.method, d.got) for d in found] == [
        ("FakeBaseGateway", "delete_field", ["token", "table_id", "field_id"]),
    ]
    discovered = {(r, c) for r, _l, c, _m in client_doubles(base, tests)}
    assert base.audit_enumerated - discovered == set()
    assert "BaseWriteClient.delete_field" in _cite(base, found[0])
    assert undeclared(base, tests) == found


# --------------------------------------------------------------------------- #
# AC2 — the predicate is DERIVED from the client, not hand-listed               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("row", _rows())
def test_the_predicate_is_the_clients_whole_public_surface(row):
    real = real_signatures(row)
    assert public_surface(row) == frozenset(real)
    assert not any(name.startswith("_") for name in real)
    for method, params in row.pinned.items():
        assert real.get(method) == params, (
            f"{row.class_name}.{method} is no longer {params} — the row's pin is stale, or "
            "the reader is pointed at the wrong class"
        )


def test_the_sheets_predicate_is_the_full_23_method_surface_not_four_markers():
    """AC2's measurement: LD-220's ``GATEWAY_MARKERS`` was 4 names; the 08-03 audit measured
    the real client at 23 public methods. The predicate is now all of them."""
    surface = public_surface(SHEETS)
    assert len(surface) >= 23, f"only {len(surface)} public methods read off SheetsWriteClient"
    assert {"read_revision", "put_values", "merge_cells"} <= surface     # LD-220's markers…
    assert {"put_style", "read_values", "read_sheet_geometry", "append_values",
            "create_spreadsheet", "delete_spreadsheet"} <= surface       # …and hole 2's rest


def test_widening_the_predicate_reaches_doubles_the_four_markers_missed():
    """The eight classes hole 2 named define **no** LD-220 marker, so the old guard could not
    see them. Losing any of them again means the predicate silently narrowed."""
    ld220_markers = {"read_revision", "put_values", "batch_update_style", "merge_cells"}
    discovered = {(r, c): m for r, _l, c, m in client_doubles(SHEETS, TESTS_DIR)}
    newly = {
        ("sheets_write_harness.py", "SheetsLifecycleGateway"),
        ("test_sheets_formula_write.py", "_Geo"),
        ("test_sheets_formula_write.py", "_NoRenderOption"),
        ("test_sheets_plan_disclosure_completion.py", "NoRenderGateway"),
        ("test_sheets_write_harness.py", "ExplodingStyler"),
        ("test_sheets_write_harness.py", "FakeGateway"),
        ("test_sheets_write_harness.py", "RecordingLifecycleClient"),
        ("test_sheets_write_harness.py", "SpyStyler"),
    }
    assert newly <= set(discovered), f"no longer discovered: {sorted(newly - set(discovered))}"
    for key in sorted(newly):
        assert not (set(discovered[key]) & ld220_markers), (
            f"{key} now defines an LD-220 marker, so it is no longer evidence that the "
            "widened predicate reaches further than the old four"
        )


def test_the_docx_client_has_a_pool_at_all():
    """Hole 1: before LD-241 the docx ``WriteClient`` had no guard whatsoever."""
    pool = {(r, c) for r, _l, c, _m in client_doubles(DOCX, TESTS_DIR)}
    assert len(pool) >= 5, f"docx pool collapsed to {sorted(pool)}"


# --------------------------------------------------------------------------- #
# AC4 — the pool is DISCOVERED, and each row still reaches its measured floor   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("row", _rows())
def test_the_pool_is_discovered_by_predicate_and_is_not_empty(row):
    pool = client_doubles(row, TESTS_DIR)
    assert pool, (
        f"no {row.label} double was discovered — the predicate derived from "
        f"{row.class_name} stopped matching, so this row is passing vacuously"
    )
    assert len(pool) >= len(row.audit_enumerated)


@pytest.mark.parametrize("row", _rows())
def test_the_discovered_pool_covers_every_class_the_audit_enumerated(row):
    """The audits' enumerations are a FLOOR, not the list: discovery may find more."""
    discovered = {(relpath, cls) for relpath, _l, cls, _m in client_doubles(row, TESTS_DIR)}
    missing = row.audit_enumerated - discovered
    assert not missing, (
        "the audits (dev/refactor-audit-2026-08-01.md §A T3a, "
        f"dev/refactor-audit-2026-08-03.md §B F3) enumerated these {row.label} doubles and "
        f"discovery no longer finds them: {sorted(missing)}. Either they were "
        "renamed/removed (update the row's audit_enumerated with the reason) or the "
        "predicate broke."
    )


def test_all_40_base_doubles_across_22_files_are_classified_and_none_is_left_unasked():
    """B2, the population the 08-06 audit counted, pinned as a number and then discharged.

    The pin is the union of the four Base pools — *every* class under ``tests/`` that names a
    public method of a Base client, including the ones that join only by naming a shared
    accessor. Being in a pool is being **asked**; the second half of this test is the answer:
    nothing the four rows find is left undeclared.

    **The count is a DELIBERATE re-count, not a nudge.** The 08-06 audit measured
    ``34 classes / 19 files``; LD-333 added one Base read double
    (``tests/test_base_read_revision.py::SpyClient``, the per-table-revision call-count spy) and
    re-counted to ``35 / 20``; LD-337 added two more in one file
    (``tests/test_base_platform_anomaly.py::World``, the vouching read seam, and ``::Client``,
    the ``create_field`` double that refuses from LD-329's capture) and re-counted to
    ``37 / 21``; LD-345 added one Base read double
    (``tests/test_base_record_permalink.py::FakeBatchClient``, the injected ``batch_get_records``
    client the permalink fetch composes over — its signature carries the new ``with_shared_url``
    keyword and matches the real method, so it is conformant) and re-counted to ``38 / 22``;
    LD-327 added one more in an existing file (``tests/offline_doubles.py::OfflineDriveClient``,
    the Drive enumeration double, which joins the Base pool only by naming the shared
    ``from_read_credentials`` accessor) and re-counted to ``39 / 22``; LD-409 added one more in
    the same file (``tests/offline_doubles.py::OfflineDriveVersionsWriteClient``, the
    named-version create double, which joins the pool the same way — by naming a shared
    credential accessor, here ``from_write_credentials``) and re-counted to ``40 / 22``; LD-432
    added one more in the same file (``tests/offline_doubles.py::OfflineDriveAccessWriteClient``,
    the docx access double, which joins the pool the same way — by naming
    ``from_write_credentials`` — and which stands in at the HTTP boundary only, building the
    REAL client rather than re-implementing it) and re-counted to ``41 / 22``; LD-433 added one
    more in a new file (``tests/test_docx_image_authoring.py::FakeMediaClient``, the injected
    media leg the docx image op uploads and downloads through — it joins the Base pool only by
    naming the shared ``upload`` / ``download`` methods, and its signature matches the real
    leg's keyword-only shape) and re-counted to ``42 / 23`` — all asked by
    discovery and conformant, so none carries a declaration. LD-438 added one more in a new
    file (``tests/test_base_view_hidden_fields.py``'s schema double, which names
    ``update_view`` / ``create_view`` / ``delete_view`` and whose ``update_view`` carries the
    new keyword-only ``hidden_fields`` — it is in the pool precisely so that a double which
    drifted from the shipped signature would be caught rather than silently pass a read-back
    it never really performed) and re-counted to ``46 / 26``. LD-447 added one more in a new
    file (``tests/test_sheets_in_cell_image_write.py::FakeMedia``, the DOWNLOAD-ONLY media leg
    the in-cell image op verifies bytes through — it joins the Base pool only by naming the
    shared ``download`` method, and it is download-only on purpose: that route has no upload
    leg at all, so a double carrying one would model a product that does not exist) and
    re-counted to ``47 / 27``. LD-448 added one more in a new file
    (``tests/test_sheets_float_image_authoring.py::FakeMediaClient``, the injected media leg
    the FLOAT-image op uploads and downloads through — it joins the Base pool by naming the
    shared ``upload`` / ``download`` methods, and unlike the in-cell double it DOES carry an
    upload, because that route really has one) and re-counted to ``48 / 28``. LD-449 added one
    more in a new file (``tests/test_drive_chunked_upload.py::_FakeFile``, the SDK
    ``drive.v1.file`` resource double the chunked upload legs run against — it joins the Base
    pool the same way its LD-434 twin does, by naming a leg the media client also calls
    ``download``, and it is DECLARED divergent for that same reason: it stands in for the SDK
    resource, not for a media client) and re-counted to ``49 / 29``. LD-462 added one more in a
    new file (``tests/test_base_select_option_shrink.py::_ShrinkingClient``, the schema double
    whose ``update_field`` really REPLACES the option set in the scan world and bumps
    ``table.revision`` — it is in the pool precisely so that a double which drifted from the
    shipped signature could not pass a read-back it never really performed, and its signature
    matches the real method's) and re-counted to ``50 / 30``. LD-467 added one more in an
    EXISTING file (``tests/offline_doubles.py::OfflineDriveFoldersWriteClient``, the
    folder-creation double the shipped guide recipe runs through — it joins the Base pool the
    way its LD-434 sibling does, by carrying the ``from_write_credentials`` classmethod, and it
    stands in at the HTTP boundary only, building the REAL client over a routing transport
    rather than re-implementing it) and re-counted to ``51 / 30`` — the file count does not
    move, because the file was already in the population.
    """
    pool, files = set(), set()
    for row in BASE_ROWS:
        for relpath, _l, cls, _m in client_doubles(row, TESTS_DIR):
            pool.add((relpath, cls))
            files.add(relpath)
    assert (len(pool), len(files)) == (51, 30), (
        f"the Base double population measured {len(pool)} classes / {len(files)} files, not the "
        f"51/30 currently pinned. That is not automatically wrong — but it is a deliberate "
        f"re-count, not a number to nudge. Files: {sorted(files)}"
    )
    left = [(row.label, d.relpath, d.cls, d.method)
            for row in BASE_ROWS for d in undeclared(row, TESTS_DIR)]
    assert not left, f"unasked/unresolved Base divergences: {left}"


def test_the_exploding_and_inert_base_doubles_are_now_RECORDED_either_way():
    """B4. The audit's complaint about the ``*args``-shaped Base doubles was not that they were
    wrong — it was that *"the guard never asks, so the distinction is unrecorded either way"*.

    It asks now, and the answers differ, which is the whole point of recording them: the eight
    exploder methods are declared facades, while ``_InertReadClient`` — named in the same breath
    by the audit as one of "their kin" — turns out to **conform**, and so carries no declaration.
    That is the audit's twelfth divergence accounted for: it was never one.
    """
    exploders = {
        ("base-write", "test_base_apply.py", "Boom", "batch_update_records"),
        ("base-read", "test_base_apply.py", "Boom", "list_tables"),
        ("base-read", "test_base_table.py", "_Exploding", "get_app"),
        ("base-read", "test_base_table.py", "_Exploding", "list_views"),
        ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "get_app"),
        ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "list_tables"),
        ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "list_fields"),
        ("base-read", "test_embedded_base_deep_read.py", "ExplodingBaseClient", "search_records"),
    }
    missing = sorted(exploders - set(DECLARED_DIVERGENT))
    assert not missing, f"the exploder declarations went missing: {missing}"

    inert = [d for d in divergences(BASE_READ, TESTS_DIR) if d.cls == "_InertReadClient"]
    assert inert == [], (
        "_InertReadClient stopped conforming to BaseReadClient. It was the one member of the "
        f"audit's 'exploding/inert kin' that needed no declaration: {inert}"
    )
    assert not any(key[2] == "_InertReadClient" for key in DECLARED_DIVERGENT), (
        "_InertReadClient conforms — declaring it would be a suppression over nothing"
    )


# --------------------------------------------------------------------------- #
# AC3 — every divergence is fixed or declared, and the inventory is TIGHT       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("row,relpath,cls", _pool_params())
def test_a_client_double_conforms_to_the_real_client_or_is_declared(row, relpath, cls):
    mine = [d for d in undeclared(row, TESTS_DIR) if (d.relpath, d.cls) == (relpath, cls)]
    assert not mine, (
        f"{relpath}: the {row.label} double {cls} takes parameter names the real "
        f"{row.class_name} does not:\n"
        + "\n".join("  " + _cite(row, d) for d in mine)
        + "\nThese pass today only because the apply engine calls positionally. Rename the "
        "double's parameters to the client's (the engine's call sites are unchanged), or — "
        "if the double genuinely must not mirror the client — add a row to "
        "DECLARED_DIVERGENT in tests/test_gateway_signature_conformance.py with its reason."
    )


def test_no_declared_divergence_is_stale():
    """A declared row that no longer diverges is a suppression with nothing under it."""
    live = {(row.label, d.relpath, d.cls, d.method)
            for row in CLIENT_ROWS for d in divergences(row, TESTS_DIR)}
    stale = sorted(set(DECLARED_DIVERGENT) - live)
    assert not stale, (
        f"these DECLARED_DIVERGENT rows no longer diverge: {stale}. Delete them — a stale "
        "suppression hides the next real drift."
    )


def test_every_declared_divergence_carries_a_reason():
    for key, reason in DECLARED_DIVERGENT.items():
        assert isinstance(reason, str) and len(reason) > 40, (
            f"{key} is declared divergent without a usable reason"
        )


def test_every_declaration_names_a_registered_client_and_the_key_resolves():
    """LD-306 did what the predecessor test told its successor to do — *"key DECLARED_DIVERGENT
    by client label"* — because the Base family broke both halves of the old flat key's premise.
    So the inventory is now unambiguous by construction, and this pins that: every key names a
    row that exists, and ``undeclared`` looks the key up under that same label."""
    labels = {row.label for row in CLIENT_ROWS}
    for key in DECLARED_DIVERGENT:
        assert len(key) == 4, f"{key} is not a (label, file, class, method) key"
        assert key[0] in labels, (
            f"{key} is declared against client {key[0]!r}, which is not a row of CLIENT_ROWS"
        )


def test_a_double_may_stand_in_for_two_clients_which_is_why_the_key_carries_the_label():
    """Non-vacuity for the test above: the old flat key really did stop being sound. A Base test
    world doubles the **read** and the **write** client at once, so the same
    ``(file, class, method)`` space is now shared by two contracts."""
    pools = {row.label: {(r, c) for r, _l, c, _m in client_doubles(row, TESTS_DIR)}
             for row in CLIENT_ROWS}
    both = pools["base-read"] & pools["base-write"]
    assert ("test_base_apply.py", "FakeBase") in both, (
        "FakeBase no longer doubles both Base clients — re-read whether the flat "
        f"(file, class, method) key became sound again. base-read/base-write overlap: {sorted(both)}"
    )


def test_only_the_shared_transport_accessors_may_be_named_by_two_clients():
    """The old test forbade **any** cross-client method-name overlap. That is untrue of the Base
    family — each of the four redeclares ``api_calls`` / ``limiter`` / ``from_*_credentials`` in
    its own body — so the invariant was narrowed to the honest one rather than deleted: a
    **gateway** name shared by two rows still reddens, which is the case that would make a
    declaration cover a contract nobody meant."""
    surfaces = {row.label: public_surface(row) for row in CLIENT_ROWS}
    for i, a in enumerate(CLIENT_ROWS):
        for b in CLIENT_ROWS[i + 1:]:
            shared = surfaces[a.label] & surfaces[b.label]
            assert shared <= SHARED_CLIENT_SURFACE, (
                f"{a.label}/{b.label} share the GATEWAY method name(s) "
                f"{sorted(shared - SHARED_CLIENT_SURFACE)} — decide which row owns the "
                "contract before declaring anything about either"
            )
    assert surfaces["docx"] & surfaces["sheets"] == frozenset(), (
        "docx/sheets shared no name at LD-241 and the rows were not touched here"
    )


def test_the_shared_accessor_set_is_not_a_dumping_ground():
    """``SHARED_CLIENT_SURFACE`` buys the narrowing above, so it stays exactly what it claims:
    accessors that take nothing, plus the credential constructors. A name that carries a real
    positional argument cannot hide in here."""
    for row in CLIENT_ROWS:
        for name, params in real_signatures(row).items():
            if name not in SHARED_CLIENT_SURFACE:
                continue
            assert params in ([], ["domain"]), (
                f"{row.class_name}.{name}({', '.join(params)}) is no longer a bare accessor or "
                "a from_*_credentials constructor — take it out of SHARED_CLIENT_SURFACE"
            )


# --------------------------------------------------------------------------- #
# the inherit_style case, settled explicitly (LD-220 AC5)                       #
# --------------------------------------------------------------------------- #

def test_the_inherit_style_parameter_is_carried_or_declared():
    """``SheetsWriteClient.insert_dimension_range`` grew ``inherit_style``; at audit time
    NO double declared it. Silence about it is a FAIL — each double either carries it or
    is a declared row."""
    real = real_signatures(SHEETS)
    assert "inherit_style" in real["insert_dimension_range"], (
        "the real client no longer takes inherit_style — retire this test with the reason"
    )
    silent = []
    for relpath, _line, cls, methods in client_doubles(SHEETS, TESTS_DIR):
        if "insert_dimension_range" not in methods:
            continue
        got = methods["insert_dimension_range"]
        if "inherit_style" in got:
            continue
        if (relpath, cls, "insert_dimension_range") in DECLARED_DIVERGENT:
            continue
        silent.append(f"{relpath}: {cls}.insert_dimension_range({', '.join(got)})")
    assert not silent, (
        "these doubles neither carry the client's inherit_style nor declare its absence:\n"
        + "\n".join("  " + s for s in silent)
    )


# --------------------------------------------------------------------------- #
# the guard BITES, in a new file and inside a function body                     #
# --------------------------------------------------------------------------- #

def test_a_double_planted_in_a_brand_new_file_is_caught_with_zero_registration(tmp_path):
    (tmp_path / "test_some_new_sheets_family.py").write_text(
        "class BrandNewGateway:\n"
        "    def read_revision(self, token):\n"
        "        return 1\n"
        "\n"
        "    def put_values(self, token, a1, values):\n"
        "        return {}\n"
    , encoding="utf-8")
    found = divergences(SHEETS, tmp_path)
    assert [(d.cls, d.method, d.got) for d in found] == [
        ("BrandNewGateway", "put_values", ["token", "a1", "values"]),
        ("BrandNewGateway", "read_revision", ["token"]),
    ]
    assert "test_some_new_sheets_family.py" in _cite(SHEETS, found[0])


def test_a_docx_double_planted_in_a_brand_new_file_is_caught_with_zero_registration(tmp_path):
    """Hole 1 closed: the same zero-registration promise, now for the docx client."""
    (tmp_path / "test_some_new_docx_family.py").write_text(
        "class BrandNewWriteDouble:\n"
        "    def create_children(self, doc, parent_id, children, index=-1):\n"
        "        return []\n"
    , encoding="utf-8")
    found = divergences(DOCX, tmp_path)
    assert [(d.cls, d.method, d.got, d.want) for d in found] == [
        ("BrandNewWriteDouble", "create_children",
         ["doc", "parent_id", "children", "index"],
         ["document_id", "block_id", "children", "index"]),
    ]
    assert "WriteClient.create_children" in _cite(DOCX, found[0])


def test_a_double_nested_in_a_test_function_body_is_discovered(tmp_path):
    """Two of the audit's 22 (``Inner``, ``Minimal``) live inside function bodies."""
    (tmp_path / "test_nested.py").write_text(
        "def test_something():\n"
        "    class Inner:\n"
        "        def read_revision(self, token):\n"
        "            return 7\n"
        "\n"
        "    assert Inner().read_revision('t') == 7\n"
    , encoding="utf-8")
    assert [(d.cls, d.method) for d in divergences(SHEETS, tmp_path)] == [
        ("Inner", "read_revision")
    ]


def test_a_renamed_parameter_in_an_existing_double_is_reported_by_file_class_method(tmp_path):
    (tmp_path / "test_existing.py").write_text(
        "class FakeStyleGateway:\n"
        "    def put_values(self, spreadsheet_token, a1_range, values):\n"
        "        return {}\n"
        "\n"
        "    def batch_update_styles(self, token, style_ranges):\n"
        "        return {}\n"
    , encoding="utf-8")
    found = divergences(SHEETS, tmp_path)
    assert len(found) == 1
    message = _cite(SHEETS, found[0])
    assert "test_existing.py" in message
    assert "FakeStyleGateway" in message
    assert "batch_update_styles" in message


# --------------------------------------------------------------------------- #
# the guard cannot cry wolf                                                     #
# --------------------------------------------------------------------------- #

def test_a_conformant_double_produces_no_divergence(tmp_path):
    (tmp_path / "test_clean.py").write_text(
        "class CleanGateway:\n"
        "    def read_revision(self, spreadsheet_token):\n"
        "        return 1\n"
        "\n"
        "    def merge_cells(self, spreadsheet_token, a1_range, merge_type='MERGE_ALL'):\n"
        "        return {}\n"
    , encoding="utf-8")
    assert divergences(SHEETS, tmp_path) == []


def test_a_conformant_docx_double_produces_no_divergence(tmp_path):
    (tmp_path / "test_clean_docx.py").write_text(
        "class CleanWriteDouble:\n"
        "    def create_children(self, document_id, block_id, children, index=-1):\n"
        "        return []\n"
        "\n"
        "    def batch_delete(self, document_id, block_id, start_index, end_index):\n"
        "        return {}\n"
    , encoding="utf-8")
    assert divergences(DOCX, tmp_path) == []


def test_a_docx_double_is_not_a_sheets_double():
    """Cross-client hygiene, on the real tree — the LD-241 claim, unchanged. It is asserted of
    ``docx``/``sheets`` specifically rather than of every pair, because the four Base rows DO
    share pool members (see the label-keying tests above): those two surfaces share no method
    name at all, so a class in both pools would be a genuine mix-up."""
    pool = {(r, c) for r, _l, c, _m in client_doubles(DOCX, TESTS_DIR)}
    other_pool = {(r, c) for r, _l, c, _m in client_doubles(SHEETS, TESTS_DIR)}
    assert not (pool & other_pool)


@pytest.mark.parametrize("row", _rows())
def test_a_class_in_two_pools_matched_a_gateway_name_in_at_most_one_of_them(row):
    """The Base pools overlap, but not *arbitrarily*: a class either stands in for this row's
    client on its own gateway surface, or it merely happens to name a shared accessor. The one
    exception is a test world that deliberately doubles two Base clients at once, which is
    enumerated so that a **new** cross-client stand-in has to be looked at rather than absorbed."""
    multi_client = {("test_base_apply.py", "FakeBase"), ("test_base_apply.py", "Boom")}
    gateway = {label: public_surface(r) - SHARED_CLIENT_SURFACE
               for label, r in ROW_BY_LABEL.items()}
    for relpath, _l, cls, methods in client_doubles(row, TESTS_DIR):
        if not (set(methods) & gateway[row.label]) or (relpath, cls) in multi_client:
            continue
        others = [label for label, names in gateway.items()
                  if label != row.label and (set(methods) & names)]
        assert not others, (
            f"{relpath}: {cls} matches the gateway surface of {row.label} AND of {others} — "
            "decide which client it doubles, or add it to this test's multi_client set with the "
            "reason it doubles both"
        )


def test_a_class_that_is_not_a_client_double_is_ignored(tmp_path):
    (tmp_path / "test_other.py").write_text(
        "class SomeOtherDouble:\n"
        "    def totally_unrelated(self, token):\n"
        "        return []\n"
    , encoding="utf-8")
    for row in CLIENT_ROWS:
        assert client_doubles(row, tmp_path) == []
        assert divergences(row, tmp_path) == []


def test_a_mention_in_prose_is_not_a_double(tmp_path):
    (tmp_path / "test_prose.py").write_text(
        '"""Talks about class FakeAllOpsGateway: with def read_revision(self, token)."""\n'
        "# class CommentedGateway:\n"
        "#     def put_values(self, token, a1, values): ...\n"
        'MENTION = "def read_revision(self, token)"\n'
    , encoding="utf-8")
    for row in CLIENT_ROWS:
        assert client_doubles(row, tmp_path) == []


def test_a_double_helper_with_no_counterpart_on_the_client_is_not_flagged(tmp_path):
    (tmp_path / "test_helper.py").write_text(
        "class HelperGateway:\n"
        "    def read_revision(self, spreadsheet_token):\n"
        "        return 1\n"
        "\n"
        "    def _remember(self, whatever):\n"
        "        return whatever\n"
        "\n"
        "    def calls_recorded(self, anything):\n"
        "        return []\n"
    , encoding="utf-8")
    assert divergences(SHEETS, tmp_path) == []


def test_this_guard_and_ld212s_ownership_guard_stay_disjoint():
    """LD-212 owns the TRANSPORT doubles; this owns the WRITE-CLIENT doubles. B3."""
    import write_harness

    owned = set(write_harness.OWNED_DOUBLES) | set(write_harness.DECLARED_DIVERGENT)
    for row in CLIENT_ROWS:
        names = {cls for _r, _l, cls, _m in client_doubles(row, TESTS_DIR)}
        assert not (owned & names), (
            "the transport-double and write-client-double pools must stay disjoint; "
            f"{row.label} overlap: {sorted(owned & names)}"
        )
