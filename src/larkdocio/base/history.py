"""larkdocio.base.history — Base record-level edit history: a measured refusal.

A Base record's edit history is visible in the product UI (who changed what, and when) and
**no route in the open API serves it**. LD-404 § Leg 5 probed it against a Base this harness
created, edited twice, then independently re-queried after deletion: six record/table/app-scoped
route spellings each answer the gateway's own non-JSON HTTP 404, the drive **versions** family
(the one LD-409 shipped ``list_versions`` / ``create_version`` against) refuses
``obj_type=bitable`` outright, and the drive **statistics** family answers ``code 0`` with
view-count telemetry and nothing about history. That is a measured refusal
(:data:`RECORD_HISTORY_NOT_SERVED`), in the shape a negative claim has to take — what was tried,
what came back, and what was **not** tried, because a claim's scope may not exceed its evidence's.

**The nearest thing that IS served** is not history at all: ``automatic_fields=true`` on a plain
record read answers who created or last touched the row and when
(:data:`NEAREST_SERVED_RECORD_TOUCH`) — never what changed inside it. Two facts have to travel
together there or the sentence is a footgun: the timestamps arrive as epoch **milliseconds**, a
different unit from the drive versions family's epoch-**second** strings
(:mod:`larkdocio.drive.versions`); and this library pins ``automatic_fields`` **false** by its
own PII policy (:data:`larkdocio.base.client.AUTOMATIC_FIELDS` — name-only), so
naming the call without naming the pin would send a consumer to something this wheel declines to
do today.

This module mints **no operation, no endpoint, no client call, and no permission row** — it is
documentation, authored once here and quoted verbatim into the shipped guide's Base section, and
referenced by dotted name (in the source repository) from ``BASE.md``'s "Not in scope" and "Limitations &
revisit-triggers" tables — the same split ``larkdocio.read.history`` uses for the sibling
docx-edition refusal (LD-410).
"""
from larkdocio.common.citations import dev_repo

#: **The measured refusal** (LD-404 § Leg 5). Quoted verbatim into the shipped guide; never
#: re-typed. Authored once here so ``BASE.md`` (in the source repository) and the guide cannot drift
#: against each other (one authoring, never two).
RECORD_HISTORY_NOT_SERVED = dev_repo(
    "A BASE RECORD'S EDIT HISTORY IS NOT SERVED BY THE API: no route returns what changed on a "
    "record — only who last touched it, and that is a different call entirely (see THE NEAREST "
    "SERVED THING below). Measured against a Base this harness created, edited twice, then "
    "independently re-queried after deletion "
    "(tests/captures/editions-spike/captures/300-summary-leg-5-base-history.json, in the source "
    "repository). "
    "TRIED — six record/table/app-scoped spellings, each answering the gateway's own non-JSON "
    "HTTP 404 \"404 page not found\": "
    "bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}/history, "
    ".../records/{record_id}/histories, .../records/{record_id}/revisions, "
    "bitable/v1/apps/{app_token}/tables/{table_id}/record_histories?record_id=<id>, "
    "bitable/v1/apps/{app_token}/tables/{table_id}/histories, and "
    "bitable/v1/apps/{app_token}/histories; "
    "drive/v1/files/{app_token}/versions?obj_type=bitable, which answers HTTP 400 "
    "\"1068411 params error, param [obj_type] is wrong\" — the drive versions family does not "
    "cover Bases at all; and drive/v1/files/{app_token}/statistics?file_type=bitable, which "
    "answers code 0 with pv/uv/like counters only, no history of any kind. "
    "NOT TRIED, stated because a claim's scope may not exceed its evidence's — a "
    "user_access_token session on any of the above (everything measured rode a "
    "tenant_access_token); and any undocumented product-internal endpoint the web UI itself "
    "calls, which this library will not reverse-engineer."
)

#: **The nearest thing the API DOES serve**, named with its unit AND with this library's own
#: policy in the same breath — a sentence naming one without the other would send a consumer to
#: a call larkdocio declines to make without saying so. Quoted verbatim into the shipped guide.
NEAREST_SERVED_RECORD_TOUCH = dev_repo(
    "THE NEAREST SERVED THING IS WHO LAST TOUCHED A RECORD, NOT WHAT CHANGED. "
    "GET …/records/{record_id}?automatic_fields=true answers created_by, created_time, "
    "last_modified_by and last_modified_time "
    "(measured on a live read; the capture was retired on 2026-09-18) — who "
    "created or last touched the row and when, never a diff "
    "of the row's own fields. The times arrive as epoch MILLISECONDS — a 13-digit int, e.g. "
    "1786403626000 — a DIFFERENT unit from the drive versions family's epoch-SECOND strings "
    "(larkdocio.drive.versions), so a consumer meeting both encodings in one release and "
    "assuming one is the other is off by 1000x. "
    "AND IN THE SAME BREATH: larkdocio pins automatic_fields FALSE by its own person-data "
    "policy (larkdocio.base.client.AUTOMATIC_FIELDS) — because created_by and last_modified_by "
    "are person objects carrying personal data, and this record read costs a privacy surface "
    "for a render that uses none of it. So this is what the API SERVES, not what larkdocio "
    "EXPOSES today — a sentence sending a consumer to this call without saying so would "
    "describe a workaround the wheel does not actually offer."
)
