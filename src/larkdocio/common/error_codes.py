"""larkdocio.common.error_codes — THE ONE LOOKUP for Lark's error codes (LD-531).

**What this module is, in one sentence: a code's MEANING and EVIDENCE are authored here, once.
What it is deliberately NOT: a classifier.**

That split is the whole design, and merging the two halves would have been the defect rather
than the cure. Before LD-531 the knowledge of what a Lark code *means* lived in five
disconnected branch tables plus a large mass of docstring provenance, so a code that arrived on
two surfaces was explained twice — and three codes nobody had tabled at all were classified by
message-shape guessing or not classified. This module ends the first problem and fills those
three holes. It does not touch the second: **every surface keeps its
own classification**, because each one is a ruled, measured, surface-true decision:

* :mod:`larkdocio.base.disposition`'s ``SYSTEMIC_CODES`` / ``ENTRY_SCOPED_CODES`` split is
  **D4′**, and it decides whether a write batch HALTS. Its per-code ``#`` reasons are the
  ruling, not commentary.
* :mod:`larkdocio.sheets.write_client`'s ``_GONE_CODES`` is a *teardown-forgiveness* set
  spanning two endpoints that answer the same fact with different numbers.
* :mod:`larkdocio.permissions`' ``DENIAL_CODES`` drives a typed exception class, and carries a
  **measured** ``denial-verified`` / ``documented-unverified`` distinction per row.
* :mod:`larkdocio.base.errors`' ``BASE_ERROR_CODES`` is the Base surface's own view, and its
  lookup stays base-scoped: a Base caller asking about a sheets code still gets ``None``.

So a row here says *what Lark means*; a surface says *what to do about it*. A code appears in
this table once and in as many per-surface classifications as have a measured reason to hold it.

**Nothing is invented, and no row claims more than its evidence.** ``verification`` is the
instrument (:data:`VERIFICATION_LABELS`), and it is the same discipline
:mod:`larkdocio.permissions` applies to a scope requirement, for the same reason: **a claim's
scope is exactly its evidence's.** A code named in this project's own documents but never seen
on the wire here says so. A code seen
on the wire whose ``msg`` nobody recorded carries an **empty label** and a written reason in
:data:`LABEL_NOT_CAPTURED`, rather than a plausible message somebody reconstructed.

**The library still never widens, requests or escalates a scope.** A row describes a
requirement and quotes Lark's own answer; it does not act. See
:data:`larkdocio.permissions.NEVER_WIDENS`.

**Why there is no generated ``ERRORS.md``.** Maintainer ruling 2026-08-18, recorded in the 2026-08
refactor audit's reconciliation § 5.3: *lookup-only* — *"they're error codes… no need to get
fancy."* The reason is the one audit A gave: a fourth generated matrix
would add per-landing ceremony of its own, and the lookup was what was actually asked for. So
this module is a lookup and a lookup only — no projection, no ``capabilities()`` key, no
consumer accessor, no CLI surface.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from larkdocio.common.citations import dev_repo

# The Base study's three probe packs and their capture tree — the provenance for the rows LD-247
# authored, moved here verbatim by LD-531 with their evidence pointers unchanged.
_PARITY = "dev/base-study/ui-parity-matrix-2026-08-03.md"
_P0 = "dev/base-study/p0-addendum-2026-08-03.md"
_OPENER = "dev/base-study-2026-08-03.md"
_CAPTURES = "tests/captures/base-study/captures"
_SPIKE = "dev/base-authoring-spike"
# LD-493/LD-501/LD-510's caller-supplied-destination captures — the object-ACL measurements.
_DESTINATION = "dev/ld493-caller-supplied-destination/captures"
# The three packs the non-Base families' rows were measured in.
_WRITE_SPIKE = "dev/write-spike/07-report.md"
_SHEETS_MEDIA = "dev/sheets-media-spike/findings.md"
_SPIKE_FINDINGS = "dev/base-authoring-spike/findings.md"
# The docx removal-route probe's evidence tree (the ONE source of the shipped removal claim).
_REMOVAL_ROUTES = "tests/captures/ld601-trashed-doc-routes/captures"
#: LD-494's app-space census — the two ``99992402`` field-violation bodies (LD-606).
_LD494 = "tests/captures/ld494-app-space-census/captures"
# The packs behind the four rows LD-531's FIX ROUND added — the codes that reach a control-flow
# comparison only THROUGH A NAMED CONSTANT, which is the false-negative class a literal-role
# scan cannot see. Each pack is the capture that established its own row.
_DRIVE_SPIKE = "tests/captures/drive-spike/captures"
_LD467 = "tests/captures/ld467-create-folder/captures"
_PERMISSIONS_SPIKE = "tests/captures/permissions-spike/captures"
_PREFLIGHT_PROBE = "tests/captures/permissions-preflight-probe/captures"
_SHEETS_WRITE_SPIKE = "tests/captures/sheets-write-spike/captures"
# 90202's finding record is the 2026-07-28 seat-session report § F20 in the dev repo (LD-150).
# It is NOT cited in the row's evidence string and must not be: the folder name and the section
# label are both patterns tests/test_consumer_dialect_guard.py forbids in shipped text, and a
# consumer holds only the wheel. The row cites the CAPTURE instead, which is the primary
# evidence anyway; this comment is where the internal provenance lives.

#: How firmly a CODE's reading is established. Ordered strongest-first, and deliberately
#: overlapping :data:`larkdocio.permissions.VERIFICATION_LABELS` where the two speak about the
#: same thing — ``denial-verified`` and ``documented-unverified`` are that registry's own words
#: and they travel into this one unchanged, because the distinction they draw is a measurement
#: rather than a label.
#:
#: * ``denial-verified`` — a captured Lark **denial body** carries this code and names the
#:   missing scope in it;
#: * ``wire-observed`` — this code was recorded arriving from Lark in a capture or a probe here;
#: * ``documented-unverified`` — named in this project's own documents or in Lark's, never
#:   observed on the wire here. Read it as an honest unknown, not a fact.
VERIFICATION_LABELS: Tuple[str, ...] = (
    "denial-verified", "wire-observed", "documented-unverified",
)

#: The two kinds of *"you may not"* Lark answers, kept apart because **the fixes are different
#: fixes** (LD-531 / RECONCILIATION § 1.4). Forcing one into the other's shape is how an
#: object-level refusal gets reported as a missing grant, and sends somebody to a console that
#: cannot help them.
#:
#: * ``scope`` — the APPLICATION does not hold the permission. Fixed by a workspace
#:   administrator granting it in the Lark console; Lark names the scope string in the body.
#: * ``object-acl`` — the application holds the scope and is not on **this object's** access
#:   list. Fixed by sharing the document/folder with the application. No scope is missing, so
#:   :func:`larkdocio.permissions.denial_from` correctly returns ``None`` for one of these —
#:   that is the LD-501 finding, and it is the right answer, not a gap.
DENIAL_CLASSES: Tuple[str, ...] = ("scope", "object-acl")


@dataclass(frozen=True)
class ErrorCodeNote:
    """One Lark code: its own words, what it means, where it was recorded, and how firmly.

    * ``code`` — Lark's numeric code, as an ``int``. Compare it representation-agnostically
      (``str(code)``): the wire hands back an int on some routes and a str on others.
    * ``label`` — Lark's ``msg`` **verbatim**, so a reader grepping a log finds this row.
      **Empty** where the code was recorded by number alone; such a row is listed in
      :data:`LABEL_NOT_CAPTURED` with the reason, because a reconstructed message would be a
      guess wearing a capture's clothes.
    * ``meaning`` — the actionable sentence. Not a restatement of the label: a row whose
      meaning is the label spelled out has told the caller nothing.
    * ``evidence`` — the capture, probe or document that established it. Guarded: an evidence
      pointer that names a path is checked to exist, and a maintainer-repo path wears
      :data:`larkdocio.common.citations.DEV_REPO_LABEL`.
    * ``verification`` — one of :data:`VERIFICATION_LABELS`.
    * ``denial_class`` — one of :data:`DENIAL_CLASSES`, or ``None`` for a code that is not a
      refusal-to-let-you at all. ``None`` is the honest default: most codes are a not-found, a
      bad body or a conversion failure, and typing them as denials would be an over-claim.
    """

    code: int
    label: str
    meaning: str
    evidence: str
    verification: str = "wire-observed"
    denial_class: Optional[str] = None


def _note(code, label, meaning, evidence, verification="wire-observed", denial_class=None):
    return ErrorCodeNote(code=code, label=label, meaning=meaning, evidence=evidence,
                         verification=verification, denial_class=denial_class)


#: Why a row carries an EMPTY ``label`` — one written reason per code, so the empty string is a
#: recorded absence rather than an oversight. Guarded in **both** directions by this
#: repository's own suite: a blank label with no entry here reddens, and an entry whose row has
#: since gained a real label reddens too, so the list cannot rot into a rubber stamp.
LABEL_NOT_CAPTURED: Dict[int, str] = {
    99991400: (
        "the rate limit was tripped by NUMBER in the write spike's 12-read burst (three 400s "
        "at 8.8 req/s) and the report recorded the code and the rate, not Lark's message "
        "text; every later encounter is backed off by the transport before anyone reads a msg"
    ),
    1061004: (
        "named in this library's own reader routing since its first release and pinned only as "
        "a MESSAGE SHAPE in tests/test_client.py, where the msg is the fixture author's, not "
        "Lark's; no capture here records what Lark actually said"
    ),
    41050: (
        "documented-unverified: never observed on the wire here at all, so there is no message "
        "to quote — an invented one would launder a document reference into a capture"
    ),
    1069303: (
        "documented-unverified: never observed on the wire here at all, so there is no message "
        "to quote — an invented one would launder a document reference into a capture"
    ),
}


#: **THE TABLE.** Code → note, authored once. Ordered by family for reading, not by number: the
#: Base study's own vocabulary first (LD-247's rows, moved here verbatim by LD-531), then the
#: families that had no authored row at all before.
ERROR_CODES: Dict[int, ErrorCodeNote] = {
    note.code: note for note in (
        # ---- the app itself ----
        _note(1002, "note has been deleted",
              "The Base has been deleted. Lark's DELETE is a TRASH, not a purge, so the "
              "drive metadata still resolves the title while the bitable API reports the app "
              "as gone — a token that reads here may still look alive elsewhere.",
              dev_repo(f"{_OPENER} R2 · {_CAPTURES}/05-11-refetch-after-delete.json")),
        _note(91402, "NOTEXIST",
              "No Base exists at this app_token. Check the token you extracted from the URL: "
              "a Base URL's token is the /base/<token> segment, not a table or view id.",
              dev_repo(f"{_CAPTURES}/03-app-not-found.json")),
        _note(1061003, "drive file not found",
              "The drive file behind this Base cannot be addressed on its own. A docx-born "
              "embedded Base is owned by its parent document and is neither independently "
              "readable by file token nor independently deletable.",
              dev_repo(f"{_P0} § 6 · {_CAPTURES}/p0-1-07-ledger.json")),
        _note(1254036, "Bitable is copying, please try again later.",
              "The Base is still being copied. Copy is the one ASYNCHRONOUS Base operation "
              "found: the new app_token is returned before the copy exists, so a read must "
              "be retried rather than treated as a failure.",
              dev_repo(f"{_PARITY} § 5 · {_CAPTURES}/p1-q4-02-copy.json")),
        # ---- tables, records, views ----
        _note(1254004, "WrongTableId",
              "The table id is malformed. A Base table id looks like tbl…; passing a view id "
              "or a record id here produces exactly this.",
              dev_repo(f"{_CAPTURES}/03-zoo18-records-search.json")),
        _note(1254041, "TableIdNotFound",
              "No such table in this Base. The id is well-formed but belongs to no table "
              "here — list the tables first rather than assuming a remembered id.",
              dev_repo(f"{_CAPTURES}/02-bitable18-fields.json")),
        _note(1254043, "RecordIdNotFound",
              "No such record in this table. Records are deleted permanently, so a stale "
              "record id from an earlier read produces this rather than an empty result.",
              dev_repo(f"{_CAPTURES}/06-06-destructive-ops.json")),
        _note(1254023, "LastViewDeleteForbidden",
              "A table's last view cannot be deleted — Lark keeps every table with at least "
              "one view, so the view set has a floor of one.",
              dev_repo(f"{_CAPTURES}/p0-3-05-view-delete.json")),
        _note(1254034, "The last table cannot be deleted.",
              "A Base's last table cannot be deleted, so a Base cannot be reduced to zero "
              "tables. Deleting the Base itself is the only way to remove the final one.",
              dev_repo(f"{_CAPTURES}/p0-1-06-husk-reduction-test.json")),
        _note(1254001, "WrongRequestBody",
              "The request body is the wrong shape for this endpoint. The message names the "
              "offending path when Lark can identify it — read it before re-shaping. IT IS "
              "NOT ALWAYS ABOUT THE SHAPE: on `PATCH …/views/{v}` with "
              "`property.hidden_fields` this code means the named column MAY NOT BE HIDDEN — "
              "\"the primary field cannot be set as a hidden type\" — so the fix is to drop "
              "that id, not to re-shape the body. Read the detail before assuming either.",
              dev_repo(f"{_CAPTURES}/p1-q3-02-view-grouping.json · "
                       f"{_SPIKE}/findings.md § B.6")),
        # ---- the search parameters, and the vocabulary asymmetry ----
        _note(1254016, "InvalidSort",
              "The sort parameter is invalid. `sort` is keyed by field NAME: a field_id is "
              "refused here, and so is a name no field carries.",
              dev_repo(f"{_PARITY} § 4 · {_CAPTURES}/p1-q3-01-filter-sort.json")),
        _note(1254018, "InvalidFilter",
              "The filter parameter is invalid. The body names the offending field and its "
              "type; a Stage (type 24) field is refused outright, which is the only place in "
              "the API that admits type 24 exists in a value context.",
              dev_repo(f"{_PARITY} § 4 · {_CAPTURES}/p1-q3-01-filter-sort.json")),
        _note(1254044, "FieldIdNotFound",
              "A field id in the body is not a field on this table. Measured on "
              "`PATCH …/views/{v}` with `property.hidden_fields`, where it is the proof that "
              "this endpoint VALIDATES its payload rather than swallowing it — the sibling key "
              "`group_info` answers code:0 and stores nothing. larkdocio RELAYS this instead "
              "of predicting it: a field list is a read of a moment, so a local check would "
              "buy a `list_fields` read and still race the answer.",
              dev_repo(f"{_SPIKE}/findings.md § B.6 · "
                       f"{_SPIKE}/captures/ld417-b-03-hidden-fields-persistence.json")),
        _note(1254045, "FieldNameNotFound",
              "`field_names` is keyed by field NAME, not by field_id. Passing an fld… id here "
              "is a hard refusal — one of the few things on this endpoint that fails loudly "
              "instead of being silently ignored.",
              dev_repo(f"{_PARITY} § 3 row 12 · {_CAPTURES}/p1-q1-02-stage-read-routes.json")),
        _note(99992402, "field validation failed",
              "A field failed the server's own validation, and the body says exactly how: "
              "`error.field_violations` names the offending field, the value sent, and the "
              "COMPLETE accepted enum. Read the violations — they are the answer. "
              "IT IS A REQUEST-LAYER REJECTION, DECIDED ON THE REQUEST BEFORE THE TARGET IS "
              "LOOKED AT, so it says NOTHING WHATEVER ABOUT THE TARGET: not that a target is "
              "absent, not that it is present, not that it is live, not that it has been "
              "removed. Reading it as evidence about the object named in the call is the one "
              "wrong turn this row exists to stop. That reading is DERIVED from the violation "
              "body's own shape rather than measured against a control pair: the rejection "
              "names a REQUEST FIELD and prints the route's accepted enum, so no target lookup "
              "can have occurred. Both captures cited below were taken against a LIVE object "
              "(the application's own root folder); this tree holds NO capture of this code "
              "against a removed one, so the live-versus-removed identity is unmeasured, not "
              "refuted.",
              dev_repo(f"{_PARITY} § 1.1 · {_CAPTURES}/p1-q2-01-button-sweep.json · "
                       f"{_LD494}/620-root-members-read-r1.json · "
                       f"{_LD494}/621-root-members-read-r2.json")),
        _note(1254060, "TextFieldConvFail",
              "The value cannot be converted to this text-shaped field. An Email cell reads "
              "back as a {link,text} object but only accepts a plain string on write, so what "
              "was read cannot be written back unchanged.",
              dev_repo(f"{_PARITY} § 2 · {_CAPTURES}/p1-q6-01-value-writes.json")),
        _note(1254069, "AttachFieldConvFail",
              "The value cannot be converted to an attachment. An attachment cell takes an "
              "uploaded file_token, so the upload is a separate call that has to come first.",
              dev_repo(f"{_CAPTURES}/p0-4-01-attachment-population.json")),
        _note(1255002, "internal error",
              "Lark reported an internal error. Observed for a well-formed request carrying a "
              "semantically impossible value — a Location written as latitude,longitude "
              "instead of longitude,latitude — so re-check the value before retrying.",
              dev_repo(f"{_CAPTURES}/p0-4-02-location-population.json")),
        # ---- the feature gate: NOT a scope denial ----
        _note(1254301, "OperationTypeError",
              "This Base does not have advanced permissions enabled (app.is_advanced is "
              "false), so the roles family is unavailable. This is a PRODUCT FEATURE GATE: "
              "the Base's owner turns it on in the Base's own settings. It is not something "
              "any API call, and not something any Lark app credential, can change.",
              dev_repo(f"{_PARITY} § 4 roles row · {_CAPTURES}/03-roles.json")),
        _note(1254302, "RolePermNotAllow",
              "Advanced permissions cannot be enabled through the API at all — the other half "
              "of the roles gate. Only the Base's owner can turn the feature on, in the "
              "product.",
              dev_repo(f"{_PARITY} § 4 · {_CAPTURES}/p1-q4-03-parity-sweep.json")),
        # ---- neighbouring families a Base read can touch ----
        _note(1254050, "Source block is not found.",
              "The dashboard source block does not exist. A not-found, not a refusal — the "
              "verb is reachable and permitted, there is simply no such block.",
              dev_repo(f"{_PARITY} § 4 · {_CAPTURES}/p1-q4-03-parity-sweep.json")),
        _note(800074800, "WorkflowID is not a valid workflow ID",
              "No such workflow on this Base. Again a not-found rather than a refusal, so the "
              "workflow family is reachable once a real id exists.",
              dev_repo(f"{_PARITY} § 4 · {_CAPTURES}/p1-q4-03-parity-sweep.json")),
        _note(1069307, "not exist",
              "The drive comment target does not exist. A Base RECORD is not a commentable "
              "drive object — record-level comment routes do not exist at all.",
              dev_repo(f"{_PARITY} § 4 comments rows · {_CAPTURES}/p1-q4-01-comments.json")),
        _note(1770001, "invalid param",
              "The docx block request is invalid. Seen when authoring an embedded-Base block "
              "with a shape the document API does not accept.",
              dev_repo(f"{_CAPTURES}/p0-1-03-docx-embed-block-create-attempts.json")),
        _note(1770029, "block not support to create",
              "This docx block type cannot be created through the API. An embedded Base block "
              "is provisioned by the product, not authored by a caller.",
              dev_repo(f"{_CAPTURES}/p0-1-03-docx-embed-block-create-attempts.json")),
        # ---- the RATE LIMIT: the one code errors.py already centralized ---- #
        _note(99991400, "",
              "Lark's per-app / per-document rate limit. Measured: 5 calls/sec read, 3 "
              "calls/sec write per app and 3 edits/sec per document — a 12-read burst at 8.8 "
              "req/s drew three of these. It is NOT a caller error and not a retry-by-hand "
              "answer: the shared transport backs off on it, so a caller normally never sees "
              "one. Prefer batch_update, which counts as ONE per-document edit however many "
              "blocks it touches.",
              dev_repo(f"{_WRITE_SPIKE} § Q3"),
              verification="wire-observed"),
        # ---- the SCOPE denials: the application does not hold the permission ---- #
        _note(99991672, "Access denied. One of the following scopes is required:",
              "The APPLICATION does not hold a scope this call requires, and Lark names which "
              "one(s) — in the message text after the label above, and again in "
              "error.permission_violations[].subject. The label stops at the colon on purpose: "
              "the bracketed scope list that follows it differs per call, so quoting one "
              "call's list here would misdescribe every other. A workspace administrator "
              "grants it in the console, from the deep link Lark returns in error.helps[].url; "
              "this library never requests one.",
              "captured repeatedly across two probe rounds — tests/captures/permissions-preflight-probe "
              "(captures Q1, Q2 and Q12) and tests/captures/name-lookup-spike (reprobe capture R1), "
              "in the source repository; the spike's captures P1, P8, P12, R2, R3, R4, R5 and R7 drew the "
              "same body and are recorded in dev/name-lookup-spike/reprobe/reprobe-verdict.md "
              "(in the dev repo). The body carries permission_violations[].subject and "
              "helps[].url",
              verification="denial-verified", denial_class="scope"),
        _note(41050, "",
              "Named as a permission-denied code in this project's own backlog notes and never "
              "observed on the wire here. It is classified by MESSAGE SHAPE rather than "
              "asserted as a known denial code, which is why the code arm and the marker arm "
              "of larkdocio.permissions.looks_like_scope_denial both exist.",
              "named as a permission-denied code in this project's own backlog notes; never "
              "observed on the wire here, so it is classified by message shape rather than "
              "asserted as a known denial code",
              verification="documented-unverified", denial_class="scope"),
        _note(1069303, "",
              "Named as a permission-denied code in this project's own backlog notes and never "
              "observed on the wire here. Same standing as 41050: classified by message shape, "
              "not asserted as observed.",
              "named as a permission-denied code in this project's own backlog notes; never "
              "observed on the wire here, so it is classified by message shape rather than "
              "asserted as a known denial code",
              verification="documented-unverified", denial_class="scope"),
        # ---- the OBJECT-ACL denials: a DIFFERENT fix from a scope denial ---- #
        _note(1770040, "no folder permission",
              "The application holds the scope and is not on THIS FOLDER's access list — an "
              "object-ACL denial, not a scope denial, so the fix is to SHARE the folder with "
              "the application rather than to grant anything in the console. Measured on the "
              "docx create_document route, handed a real folder the account holder owns and "
              "the application was not granted: HTTP 403, with error.helps[0].description "
              "'无权限在此文件夹下创建文档'. larkdocio reports it as a plain LarkAPIError "
              "carrying Lark's code and msg unedited, and permissions.denial_from returns None "
              "for it — CORRECTLY, since no scope is missing. Scope of the measurement: one "
              "tenant, one app identity, 2026-08-17, tenant_access_token, and the docx "
              "create_document route alone; every other route and object type is UNMEASURED "
              "rather than refuted.",
              dev_repo(f"{_DESTINATION}/001-ac4-denial-create-document.json"),
              verification="wire-observed", denial_class="object-acl"),
        _note(1254701, "DriveNodePermNotAllow",
              "The application is not on the target folder's access list, answered by the Base "
              "COPY route — the second object-ACL denial: handed a real folder it has no "
              "permission on, copy_app answers this and copies nothing. Distinguishable from "
              "1254702, which is what a genuinely absent folder answers on this route. "
              "Scope of the measurement: one send, 2026-08-18, that one route, no retries; "
              "every other route is unmeasured rather than refuted.",
              dev_repo(f"{_DESTINATION}/002-copy-app-unreachable-folder.json"),
              verification="wire-observed", denial_class="object-acl"),
        _note(1254702, "DriveNodeNotExist",
              "No drive node at this token — a NOT-FOUND, not a refusal, "
              "measured on the Base copy route where it is the answer that means the folder "
              "is genuinely absent. "
              "On this route 1254701 is the other answer: the folder is really there and this "
              "application is not on its access list. "
              "An earlier class-level reading of this code was first narrowed to the one route "
              "it had been seen on, and then overturned FOR that route when the route was "
              "re-measured. The original observation (probe ld387-01) is untouched; what it "
              "stopped doing is speaking for every route.",
              dev_repo(f"{_SPIKE_FINDINGS} § ld387-01"),
              verification="wire-observed"),
        # ---- the SPREADSHEET / DRIVE-FILE gone-ness pair: two endpoints, one fact ---- #
        _note(1310249, "Path param :spreadsheet_token is deleted",
              "The spreadsheet token is trashed, as any SHEETS call against it answers. This "
              "is the CONFIRMATION code: reading a token you just deleted and getting this is "
              "how you prove the file is really gone, which a code:0 from the delete does not.",
              dev_repo(_SHEETS_MEDIA)),
        _note(1061007, "file has been delete.",
              "The DRIVE FILE delete answers this for a file that is already in the trash — a "
              "different endpoint from 1310249's, with its own number for the same fact, which "
              "is why a teardown forgives both. Live-observed 2026-07-30, correcting an "
              "offline assumption that both endpoints answered 1310249. Lark's delete of a "
              "drive FILE is a trash, not a purge: metas/batch_query still resolves the trashed "
              "FILE token. That is a fact about a file and does not generalise to the family — "
              "a trashed FOLDER token does the opposite, answering code:0 with metas: [] and "
              "failed_list [{code: 970005}].",
              dev_repo(f"{_DESTINATION} § the object-ACL measurements")),
        _note(1770003, "resource deleted",
              "The DOCX endpoints answer this for a document that has been removed — the third "
              "number in the gone-ness family above, for a third endpoint. Two routes answer "
              "it: the document meta and the reader's own body route, so it is what a read of "
              "a removed document looks like. What it does NOT tell you is whether the "
              "document is recoverable: Lark's word here is DELETED, and a probe cannot "
              "separate a trashed object from a purged one, so 'removed' is the strongest true "
              "statement it supports. And it is not the whole picture on its own — the same "
              "document's drive metadata (metas/batch_query with doc_type docx) still resolved "
              "the token afterwards, title, owner, timestamps and url intact, so a caller who "
              "asks only that route never sees this code at all.",
              dev_repo(f"{_REMOVAL_ROUTES}/ld601-after-r2.json + "
                       f"{_REMOVAL_ROUTES}/ld601-after-r3.json — both legs and all five "
                       f"routes are captured in that directory")),
        # ---- the DRIVE family's ONE collapsed refusal, and the permissions family's ---- #
        # Both reach control flow only through a NAMED CONSTANT, which is why LD-531's first
        # census missed them and why the completeness arm now enumerates comparison SITES.
        _note(1061002, "params error.",
              "The generic parameter refusal the WHOLE DRIVE FAMILY answers with, and the one "
              "thing to know about it is that it cannot be narrowed: four distinct causes "
              "collapse onto this single number — a malformed folder token, a well-formed "
              "token of the identical 27-character shape naming a folder this caller cannot "
              "reach, a bad parameter value, and a ZERO-BYTE upload. The two token cases are "
              "BYTE-IDENTICAL in the response, so a typed not-found is not expressible from "
              "what Lark returns; larkdocio names both possibilities and attributes neither, "
              "and says outright that it does not guess. That is also why denial_class is "
              "None: a refusal whose cause is unknowable may not be typed as a denial. On the "
              "create-folder route the same "
              "code is how the parent's TYPE is policed — a real file token as the parent was "
              "refused with it, while upload_all accepted a mismatched pair with code:0.",
              dev_repo(f"{_DRIVE_SPIKE}/04-list-files-invalid-folder.json · "
                       f"{_DRIVE_SPIKE}/13-wellformed-fake-folder.json · "
                       f"{_LD467}/ld467-11-parent-token-that-is-a-FILE-not-a-folder.json"),
              verification="wire-observed"),
        _note(1063001, "Invalid parameter",
              "The DRIVE PERMISSIONS family's parameter refusal, and the one place this "
              "library annotates Lark's own code instead of relaying it bare — the code and "
              "the msg still travel verbatim; what is added is which knob answers it. Three "
              "measured causes on that family: a type= value that does not fit the token, an "
              "INVENTED body key (refused rather than accepted-and-ignored, which is what "
              "proves this route does not silently swallow), and lock_switch sent to the "
              "PATCH — a key the GET returns and the PATCH refuses, making it read-only here "
              "rather than unsettable anywhere. Not a denial: it names no scope.",
              dev_repo(f"{_PERMISSIONS_SPIKE}/"
                       f"721-ld420-ac3-patch-lock-switch-to-true-candidate-lever.json · "
                       f"{_PERMISSIONS_SPIKE}/"
                       f"725-ld420-ac3-invented-key-control-patch-zzz-ld420-control.json"),
              verification="wire-observed"),
        # ---- SHEETS: the range Lark will not accept ---- #
        _note(90202, "validate RangeVal fail",
              "The RANGE is not an addressable Start:End — and it is NEVER a statement about "
              "the tab, which is the whole distinction: this code was once laundered into the "
              "staleness story, which sent a caller whose tab was perfectly fine off to "
              "re-plan for a vanished one. A reversed range (C3:A1), a bare single cell on a "
              "route that demands a band, and a dimension band running past the tab's "
              "declared row/column count all answer it, each with its own message text on the "
              "one number — so the label above is the reversed-range form, and a log may carry "
              "'wrong range=<sheet_id>!B2' or 'dimension endIndex wrong, endIndex must less "
              "than or equal to sheetMaxRowCount' for the same code.",
              dev_repo(f"{_SHEETS_WRITE_SPIKE}/01-endpoint-matrix.json"),
              verification="wire-observed"),
        # ---- CONTACTS: the one code that PROVES an id does not exist ---- #
        _note(99992351, "The request you send is not a valid {open_id} or not exists",
              "Positive proof that an id does not exist, and the only contacts answer that is: "
              "error.field_violations[] attributes the rejection to the individual ids BY "
              "VALUE, which is why every id check here falsifies against this code rather than "
              "trusting a populated reply. It is a MALFORMED-INPUT answer and not a denial — "
              "it names no scope and no grant changes it — so the repair is the id, not a "
              "permission. The label stops before the variable part on purpose: the message "
              "goes on to quote an example id and list the offending ones, and quoting one "
              "probe's ids here would misdescribe every other call.",
              dev_repo(f"{_PREFLIGHT_PROBE}/Q5-contacts-bogus-READ.json"),
              verification="wire-observed"),
        # ---- the READER's document-access code ---- #
        _note(1061004, "",
              "The docx/drive read could not reach the document: either the application is not "
              "on the document's access list or there is nothing at that token. Lark does not "
              "separate the two on this route, which is why the reader's operator guidance "
              "names both outcomes in one sentence rather than picking one. Carried as "
              "documented-unverified: this library has routed on the number since its first "
              "release, and no capture here records Lark's own message for it.",
              "named in this library's own reader routing since v1.0.0 and pinned there only "
              "as a message shape; never observed on the wire here in any recorded capture",
              verification="documented-unverified"),
    )
}


def note_for(code) -> Optional[ErrorCodeNote]:
    """The authored row for a Lark code, or ``None`` for a code nobody here has explained.

    Representation-agnostic: the wire hands back an ``int`` on some routes and a ``str`` on
    others, and a caller should not have to know which.

    **This is the package-level lookup, and it answers about every surface.** A per-surface
    accessor that is deliberately narrower stays narrower — :func:`larkdocio.base.errors.note_for`
    answers only about the Base vocabulary, on purpose, so a Base caller is never handed a
    sheets row.
    """
    try:
        return ERROR_CODES.get(int(str(code)))
    except (TypeError, ValueError):
        return None


def notes_for(codes) -> Dict[int, ErrorCodeNote]:
    """The rows for ``codes``, **in the order given** — how a surface builds its own view.

    Raises ``KeyError`` on a code with no authored row, deliberately and at import time: a
    surface that classifies a code this table cannot explain is exactly the hole LD-531 closed,
    and discovering it lazily would let it ship.
    """
    return {code: ERROR_CODES[code] for code in codes}
