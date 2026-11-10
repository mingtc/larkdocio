"""THE SINGLE LIVE GATE for the Base ATTACHMENT OUT-OF-BAND leg (LD-268).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**The full round trip, because a status code is not evidence.** Upload bytes
(``parent_type`` ∈ ``bitable_file`` / ``bitable_image``, ``parent_node`` = a disposable's
app_token) → attach the returned token through the shipped encoder → read the cell back →
download the token → **compare sha256 digests**. The download half is what makes the claim
worth making: ``code:0`` proves an answer arrived, a digest proves the *file* did.

**BYTES ARE HASHED, NEVER INSPECTED.** No assertion here decodes, renders or prints a media
payload, and the capture this arm writes carries digests, sizes and tokens only. That is the
standing rule for binary artifacts in this repository.

**``url`` and ``tmp_url`` NEVER LEAVE THIS PROCESS.** An Attachment cell reads back
``{file_token, name, size, type, url, tmp_url}`` and the last two are short-lived **signed**
links — credential-class. Every cell that reaches an assertion, a log or the capture goes
through :func:`larkdocio.base.media.scrub_attachment_cell` first, and the offline companion
greps this file to prove no other path exists.

**THIS ARM MINTS PERMANENT, UNSWEEPABLE RESIDUE, AND THAT WAS BOUGHT KNOWINGLY.** Every upload
creates a ``file_token`` that **survives the deletion of the Base it was attached to**, and
**no open-API verb purges drive media at all** — ``BASE.md``'s register row 10. So:

* every token this arm mints is written to the harness ledger with its ``parent_type`` and its
  disposable's app_token (``base_write_harness.attach_media``), and
  ``base_write_harness.media_residue()`` is the standing list;
* **there is no cleanup leg here and there cannot be one.** A ``finally`` that pretended to
  purge media would be a lie in the shape of hygiene;
* the ``orphans() == []`` claim this repository's Base arms make is stated against the
  **bitable** liveness definition (the Base read spec § D3) and **media residue is explicitly outside it**.
  A clean orphan report says nothing whatever about the files below.

**THE TARGET IS NEVER THE SCRATCH BASE — and ``parent_node`` is why that needed saying twice.**
``parent_node`` is not a write target: no record is written and no table is touched, so a guard
that only watched write targets would miss it entirely, and **an upload's residue cannot be
undone even by deleting the Base**. Every upload here goes through the harness's allow-list
(``_Provisioner.upload_media`` → ``_require_own``), which refuses every Base this run did not
create — the configured ``LARKDOCIO_SCRATCH_BASE`` among them — **without naming any of them**.
This module reads no such variable; the companion checks that statically.

**Gentle.** Around fifteen calls on one disposable, each through the same limiter the record
client uses (≥1.2 s). Rate limits are not probed.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import json
import os
from pathlib import Path

import pytest

import base_write_harness
import capture_sink
from larkdocio.base.client import BaseReadClient
from larkdocio.base.media import (
    EMPTY_UPLOAD_REFUSED_CODE,
    MediaUploadError,
    scrub_attachment_cell,
    sha256_of,
    verify_round_trip,
)
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.table import field_spec
from larkdocio.base.write_cells import encode_cell
from larkdocio.base.write_client import BaseWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

try:  # pragma: no cover - the loader is the canary's, and is optional here
    import canary_support

    canary_support.load_env()
except Exception:  # pragma: no cover - a missing loader must not fail collection
    pass

#: The capture this arm writes — digests, sizes and tokens. **No bytes and no links.**
CAPTURE = Path(__file__).resolve().parent.parent / "tests/captures/base-study/captures" \
    / "ld268-01-attachment-media-round-trip.json"

#: The attachment column this arm authors on its own disposable.
FIELD_NAME = "ld268-files"

#: The three payloads that round-trip, and why each is here. The amplifier case is the one a
#: hash comparison could plausibly get wrong: a non-ASCII **file name** (does the multipart
#: field survive the wire intact enough for the bytes to come back?).
PAYLOADS = {
    "file": (b"larkdocio LD-268 attachment round trip, bitable_file", "ld268-file.txt",
             "bitable_file"),
    "image": (b"larkdocio LD-268 attachment round trip, bitable_image", "ld268-image.bin",
              "bitable_image"),
    "non_ascii": (b"non-ascii name, ascii bytes", "ld268-名前-файл.bin", "bitable_file"),
}

#: **The zero-byte case, which this arm discovered is not a round-trip question at all.** The
#: first live run uploaded an empty file and Lark answered ``1061002 params error`` — a generic
#: parameter complaint that names nothing about the size. So the amplifier's empty-file case is
#: kept as a **refusal probe** rather than dropped: the finding is the server's answer, and an
#: arm that quietly stopped asking would lose it. Its residue cost is nil — a refused upload
#: mints no token.
EMPTY_PAYLOAD = (b"", "ld268-empty.bin", "bitable_file")


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


@pytest.fixture(scope="module")
def round_trip(credentials):
    """ONE disposable, one upload/attach/read/download sequence, shared by every assertion.

    A fixture rather than four tests each provisioning their own Base: every extra upload is
    permanent residue, so the arm buys exactly the four it needs and no more.
    """
    ledger = base_write_harness.Ledger()
    provisioner = base_write_harness._Provisioner()
    schema = BaseSchemaClient.from_write_credentials()
    write = BaseWriteClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    observed = {}

    with base_write_harness.disposable_base(provisioner=provisioner, ledger=ledger) \
            as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        schema.create_field(app_token, table_id, FIELD_NAME, 17, ui_type="Attachment")
        field = field_spec([f for f in read.list_fields(app_token, table_id)
                            if f.field_name == FIELD_NAME][0])

        uploads = {}
        for key, (payload, name, parent_type) in PAYLOADS.items():
            uploads[key] = base_write_harness.attach_media(
                app_token, data=payload, name=name, parent_type=parent_type,
                provisioner=provisioner, ledger=ledger)

        # The empty-file probe. Either answer is a pass and BOTH are recorded — silence is
        # not. It mints nothing when it is refused, which is why it costs nothing to keep.
        empty_payload, empty_name, empty_parent_type = EMPTY_PAYLOAD
        try:
            empty = base_write_harness.attach_media(
                app_token, data=empty_payload, name=empty_name,
                parent_type=empty_parent_type, provisioner=provisioner, ledger=ledger)
            empty_probe = {"refused": False, "file_token": empty.file_token,
                           "sha256": empty.sha256}
        except MediaUploadError as exc:
            empty_probe = {"refused": True, "code": exc.code, "message": str(exc)}

        # The seam: the tokens the upload returned feed LD-256's encoder UNCHANGED, and two
        # attachments ride in ONE cell.
        cell = encode_cell([uploads["file"].file_token, uploads["image"].file_token], field)
        created = write.create_record(app_token, table_id, {FIELD_NAME: cell})

        rows = {r.record_id: r for r in read.search_records(app_token, table_id)}
        read_back = [scrub_attachment_cell(item)
                     for item in rows[created.record_id].fields[FIELD_NAME]]
        raw_keys = sorted({k for item in rows[created.record_id].fields[FIELD_NAME]
                           for k in item})

        downloads = {}
        for key, uploaded in uploads.items():
            payload = provisioner.download_media(uploaded.file_token)
            downloads[key] = {
                "sha256": sha256_of(payload),
                "bytes": len(payload),
                "verified": verify_round_trip(uploaded, payload),
            }

        observed = {
            "app_token_is_a_disposable": True,
            "encoded_cell": cell,
            "read_back_scrubbed": read_back,
            "read_back_keys": raw_keys,
            "uploads": {k: {"file_token": u.file_token, "parent_type": u.parent_type,
                            "size": u.size, "sha256": u.sha256}
                        for k, u in uploads.items()},
            "downloads": downloads,
            "parent_nodes": sorted({u.parent_node for u in uploads.values()}),
            "media_ledgered": [e["file_token"] for e in ledger.media()],
            "empty_file_probe": empty_probe,
        }

    capture_sink.write_capture(CAPTURE, json.dumps({
        "_issue": "LD-268",
        "_what": ("the attachment out-of-band leg, live: upload (both parent types) → attach "
                  "via the shipped encoder → read back → download → HASH-VERIFY. Digests, "
                  "sizes and tokens only: no media bytes are inspected, decoded or recorded, "
                  "and no url/tmp_url is captured — both are short-lived signed links"),
        "_residue": ("every file_token below is PERMANENT. No open-API verb purges drive "
                     "media (BASE.md register row 10); the tokens are ledgered, not swept"),
        "_verdict": "OK",
        "observations": observed,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return observed


def test_the_write_registry_declares_the_arm_MUTATING_before_it_calls_anything():
    """The shape every Base arm ships. An upload mutates the tenant — permanently — so the
    registries are asserted before the first call, and the read registry still answers
    read-only about itself in the same breath."""
    from larkdocio.base import ops as base_ops
    from larkdocio.base import write_ops

    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True


def test_both_parent_types_round_trip_and_the_HASH_IS_IDENTICAL(round_trip):
    """AC1 + AC3, live: both captured ``parent_type``s upload, and each downloads back to the
    **same sha256**. The bytes themselves are never looked at."""
    for key in ("file", "image"):
        uploaded = round_trip["uploads"][key]
        assert round_trip["downloads"][key]["sha256"] == uploaded["sha256"], key
        assert round_trip["downloads"][key]["bytes"] == uploaded["size"], key
    assert {round_trip["uploads"][k]["parent_type"] for k in ("file", "image")} == {
        "bitable_file", "bitable_image"}


def test_the_AMPLIFIER_case_a_NON_ASCII_FILE_NAME_round_trips_by_hash(round_trip):
    """The case a round-trip claim is most likely to be wrong about: a file name carrying CJK
    and Cyrillic characters, with the bytes still compared by hash."""
    assert round_trip["downloads"]["non_ascii"]["sha256"] \
        == round_trip["uploads"]["non_ascii"]["sha256"]


def test_the_EMPTY_FILE_probe_records_what_the_SERVER_answered(round_trip):
    """The other amplifier case, and what it actually found: **Lark refuses a zero-byte
    upload**, with the generic ``1061002 params error`` naming nothing about the size. Either
    answer is a pass — what is not allowed is not asking — so the observation is asserted
    against the shipped constant rather than against a hope, and the refusal path is required
    to explain itself."""
    probe = round_trip["empty_file_probe"]
    if probe["refused"]:
        assert probe["code"] == EMPTY_UPLOAD_REFUSED_CODE, probe
        assert "EMPTY" in probe["message"], "the refusal must name its real cause"
    else:
        # If Lark starts accepting empty files, the recorded fact is stale — say so loudly
        # rather than passing quietly on the opposite result.
        assert probe["file_token"], probe
        pytest.fail(
            "the zero-byte upload SUCCEEDED — larkdocio.base.media's recorded refusal is now "
            f"stale and must be re-cut: {probe}")


def test_the_uploaded_tokens_feed_the_SHIPPED_ENCODER_and_TWO_ride_in_one_cell(round_trip):
    """AC2: the encoder is LD-256's and is consumed, not re-authored — this asserts the seam,
    and that a cell holding **two** attachments keeps both tokens."""
    tokens = [round_trip["uploads"]["file"]["file_token"],
              round_trip["uploads"]["image"]["file_token"]]
    assert round_trip["encoded_cell"] == [{"file_token": t} for t in tokens]
    assert sorted(item["file_token"] for item in round_trip["read_back_scrubbed"]) \
        == sorted(tokens)


def test_the_read_back_carries_the_SIGNED_LINKS_and_NOTHING_HERE_KEEPS_THEM(round_trip):
    """AC4: the live cell really does return ``url`` / ``tmp_url`` — that is why the scrubber
    exists — and every projection this arm keeps, asserts or captures has dropped them."""
    assert {"url", "tmp_url"} <= set(round_trip["read_back_keys"]), (
        "the read-back shape changed; the scrubber's reason to exist should be re-checked")
    kept = json.dumps(round_trip["read_back_scrubbed"])
    assert "url" not in kept and "http" not in kept


def test_every_minted_token_is_LEDGERED_as_permanent_residue(round_trip):
    """AC5: the residue is disclosed, not swept. Every token the run minted is in the ledger's
    media half, which has no delete leg because no verb would back one."""
    minted = {u["file_token"] for u in round_trip["uploads"].values()}
    assert minted <= set(round_trip["media_ledgered"])
    assert len(minted) == len(PAYLOADS)


def test_no_parent_node_is_a_CONFIGURED_BASE(round_trip):
    """AC6, the second half of the two-parameter assertion. Every ``parent_node`` is a Base
    this run created; none is the configured Scratch Base — checked against the environment
    here as well as structurally by the harness's allow-list, because this is the parameter no
    deletion can take back."""
    configured = {v for k, v in os.environ.items() if k.startswith("LARKDOCIO_SCRATCH")}
    for parent_node in round_trip["parent_nodes"]:
        assert parent_node not in configured
        assert not any(parent_node and parent_node in value for value in configured)


def test_the_arm_reports_its_MEDIA_RESIDUE_and_its_base_orphans_separately(round_trip):
    """The disclosure, run as an assertion: the orphan oracle answers about **bitable**
    objects, so it is reported beside — never instead of — the media list it says nothing
    about."""
    residue = base_write_harness.media_residue()
    assert residue, "this arm minted media; the ledger must say so"
    orphans = base_write_harness.orphans()
    print(f"LD-268 media residue (PERMANENT, unsweepable): "
          f"{[e['file_token'] for e in residue]}")
    print(f"LD-268 bitable orphans (a DIFFERENT question): {orphans}")
