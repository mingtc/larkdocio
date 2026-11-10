"""THE MERMAID GATE — the binding **diagram-creation** round-trip (LD-192 / AC9).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**What this gate exists to rule out.** A type-40 create returning ``code 0`` proves nothing on
its own: an add-on block can be accepted and stored as an **inert shell** that renders as
nothing. AC9 calls that a **FALSE GO**. So acceptance is the *weakest* thing asserted here.
The gate instead measures three independent projections of the created block:

1. **the stored payload**, re-read from the API and compared **field by field against the maintainer
   specimen** — a diagram a person typed by hand. If our block and theirs are
   shape-identical, Lark's renderer cannot tell them apart either;
2. **our own reader's Markdown**, which must carry a ```` ```mermaid ```` fence with the source
   intact — not the ``[Unsupported Add-On block: …]`` marker, and not nothing.

*(The spike additionally checked Lark's own ``raw_content`` text projection. That is **not**
re-derived here, and deliberately not faked: no shipped client exposes that endpoint, so
asserting it would mean either adding an accessor this issue does not need or writing a
``hasattr`` branch that never fires. Two independent projections plus specimen-shape
identity is what this gate can honestly measure.)*

**The record's binding claim is the DECODED payload (LD-218).** The raw ``add_ons.record``
string is *characterized* rather than pinned: the server was observed on 2026-08-01
re-serializing it with ``<`` ``>`` ``&`` decoded, and the drift flaps, so the gate accepts
membership of the two observed serializations of the same JSON (:func:`accepted_record_forms`)
and nothing wider.

**The specimen is never touched.** The comparison target is the spike's **committed capture**
of it (``tests/captures/mermaid-gate-captures/20-specimen.json``), read off disk; in this tree its diagram
words are a project-written stand-in of the same shape (``tests/captures/README.md``). The maintainer
specimen document is READ-ONLY forever, and this gate makes **zero** requests to it: there is no
code path here that could.

**Disposables only, zero orphans.** The gate provisions its own document
(``WriteClient.create_document``), does every write on it, and deletes it in a ``finally`` — on
success and on failure. It never touches the read canary, the write scratch doc, the block-zoo
doc, or any standing surface.

The teardown reads its child range **off the live root**, never off a count held in the test:
a freshly created document's root may hold zero children, and the replace route changes how
many blocks sit at the top level, so a held count can overshoot and be refused ``1770001`` —
which would fail the gate *in teardown* and leave the disposable behind. The evidence print
therefore lives **inside** the ``finally`` too, so a failing run still reports the disposable's
id and whether it was emptied and trashed.

**The replace route is exercised too** (AC3/AC9): delete the diagram and re-create it at the
same index, asserting the new source renders, the old one is gone, and **the ``block_id``
changed** — the cost the docs state, measured live rather than repeated.

Writes ride the shared throttle (≤3/sec). Credentials: writes use ``get_write_credentials()``
only; the reader half prefers ``get_read_credentials()`` and falls back to the owning write app,
because a separate read-only app is not a collaborator on a doc this gate created.
"""
import json
import time
from pathlib import Path

import pytest

import canary_support
from larkdocio.blocks.diagram import MERMAID_COMPONENT_TYPE_ID
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.model import AddOnsNode
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    apply,
    dry_run,
)
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.encode import _GO_JSON_ESCAPED_CHARS, go_json_escape, mermaid_record
from larkdocio.write.resolve import _collect_blocks

#: Marked per-test rather than module-wide on purpose: the disposables-only structural check
#: at the bottom needs no credentials and no network, and it should be enforced on **every**
#: run rather than only when someone remembers to run the ring.
DOMAIN = "larksuite.com"
CAPTURES = Path(__file__).resolve().parents[1] / "tests" / "captures" / "mermaid-gate-captures"

SUFFIX = "ld192gate-7f3c1a9e"
SECTION_HEADING = f"MERMAID-GATE-SECTION {SUFFIX}"
ANCHOR_LINE = f"anchor paragraph for the diagram insert :: {SUFFIX}"

# Our own diagram, with a `<br/>` and an `&` so the record's Go-form escaping is exercised
# live rather than only offline.
OUR_SOURCE = (
    "flowchart TD\n"
    f'    A["Draft {SUFFIX}<br/>step one & two"] --> B["Review"]\n'
    '    B --> C["Shipped"]\n'
)
REVISED_SOURCE = (
    "flowchart TD\n"
    f'    A["Draft {SUFFIX}<br/>step one & two"] --> B["Review"]\n'
    '    B --> C["Shipped"]\n'
    f'    C --> D["Archived {SUFFIX}"]\n'
)


def accepted_record_forms(source, theme=None):
    """The TWO raw ``add_ons.record`` serializations this gate accepts (LD-218).

    The binding round-trip claim is the **decoded** record (see the gate's docstring); this
    set is the narrower, *characterizing* check that the raw string is still one of the two
    server behaviours actually observed — anything else is real drift and must fail.

    1. ``mermaid_record(source)`` itself — Go's ``encoding/json`` form with ``<`` ``>`` ``&``
       escaped, which is what the library SENDS and what the server echoed back verbatim in
       every ring run through **2026-08-01** (and again in the 27- and 29-arm runs that day).
    2. **the server's literal re-serialization of that same JSON** — byte-identical except
       that the three escapes come back decoded. First observed **2026-08-01** in one ring
       run; the drift FLAPS (green rings on either side of it), so both forms stay accepted.

    Form 2 is DERIVED from form 1 by exactly one stated transform — undo
    :func:`go_json_escape` for each character in the encoder's own
    ``_GO_JSON_ESCAPED_CHARS`` — never a second hand-written literal that could drift on its
    own away from the encoder.
    """
    ours = mermaid_record(source, theme)
    server = ours
    for char in _GO_JSON_ESCAPED_CHARS:
        server = server.replace(go_json_escape(char), char)
    return (ours, server)


def _specimen():
    """The maintainer specimen as the spike captured it — read off DISK, never off the network."""
    capture = json.loads((CAPTURES / "20-specimen.json").read_text(encoding="utf-8"))
    (only,) = capture["specimens"].values()
    return only


def _download(document_id):
    """Download + parse via the shipped reader: ``(markdown, tree)``."""
    attempts = []
    if canary_support.read_creds_available():
        attempts.append(get_read_credentials())
    attempts.append(get_write_credentials())

    last_err = None
    for (app_id, app_secret) in attempts:
        try:
            client = ReadClient(app_id, app_secret, DOMAIN)
            docx, blocks = client.get_docx_content(document_id)
            parser = Parser(new_config())
            markdown = parser.parse_docx_content(docx.document_id, blocks)
            tree = parser.parse_docx_tree(docx.document_id, blocks)
            return markdown, tree
        except Exception as e:  # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


def _diagrams(tree):
    """Every :class:`AddOnsNode` in the parsed tree, in document order."""
    return [n for n, _p in _collect_blocks(tree) if isinstance(n, AddOnsNode)]


@pytest.mark.live_write
@pytest.mark.conformance          # LD-370: the live rings are conformance-tier; this
                                  # module is MIXED (offline encoders + one live arm), so
                                  # the mark is per-test rather than module-level.
def test_mermaid_gate_diagram_creation_round_trip(capsys):
    """THE ROUND-TRIP GUARANTEE IS THE **DECODED** RECORD (LD-218).

    What this gate binds is that the record Lark stores *decodes* to exactly what was
    authored — ``data`` byte-exact to the source sent, plus ``theme`` and ``view``. It does
    **not** promise the raw string comes back byte-identical to what the library sent: on
    2026-08-01 the server was observed re-serializing the record with ``<`` ``>`` ``&``
    decoded, and that drift **flaps** (green rings on either side of the one red).

    The raw string is still checked, as **set membership** over the two serializations of the
    same JSON that have actually been observed (:func:`accepted_record_forms`) — so a genuine
    third encoding still reddens the gate rather than passing unnoticed.
    """
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    specimen = _specimen()
    wc = WriteClient(*get_write_credentials(), DOMAIN)

    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-LD192-mermaid-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}
    seed = [
        {"block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": SECTION_HEADING}}]}},
        text_block(ANCHOR_LINE),
    ]

    try:
        wc.create_children(doc_id, doc_id, seed, index=0)

        # 1) Baseline + the determinism control that makes any later diff attributable.
        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ")
        assert not _diagrams(tree_baseline), "the baseline must carry no diagram yet"

        # 2) AUTHOR THE DIAGRAM THROUGH THE GATE — the capability under test.
        insert = InsertRequest(
            reference=Anchor(quote=ANCHOR_LINE, breadcrumb=(SECTION_HEADING,)),
            position=InsertPosition.AFTER,
            content=(NewBlock.mermaid(OUR_SOURCE),),
        )
        plan = dry_run([insert], tree_baseline)
        assert len(plan.refusals) == 0, f"dry-run refused the insert: {plan.refusals!r}"
        assert len(plan.resolved) == 1, f"dry-run did not resolve the insert: {plan!r}"
        assert [c.kind.value for c in plan.resolved[0].content] == ["mermaid"]

        log = apply(plan, wc, doc_id)
        assert len(log.entries) == 1, f"apply-log is not 1:1 with the plan: {log!r}"
        created = log.entries[0]
        assert created.outcome == "inserted", created.to_dict()
        (diagram_id,) = created.created_block_ids
        assert diagram_id, "the created diagram id came back empty"
        evidence["diagram_block_id"] = diagram_id

        # 3) PROJECTION ONE — the stored payload, diffed against the SPECIMEN field by field.
        live = wc.get_block(doc_id, diagram_id)
        add_ons = live.get("add_ons") or {}
        assert live.get("block_type") == 40, live
        assert sorted(add_ons) == sorted(specimen["add_ons_keys"]), (
            f"our add_ons key set differs from a hand-typed block's: "
            f"{sorted(add_ons)} vs {sorted(specimen['add_ons_keys'])}")
        assert add_ons.get("component_type_id") == specimen["component_type_id"] == \
            MERMAID_COMPONENT_TYPE_ID, add_ons
        assert add_ons.get("component_id") == specimen["component_id"] == "", (
            f"component_id must come back EMPTY exactly as a hand-typed block's does: "
            f"{add_ons.get('component_id')!r}")
        record = json.loads(add_ons["record"])
        assert sorted(record) == sorted(specimen["record_keys"]), record
        assert record["data"] == OUR_SOURCE, "the stored source is not what was authored"
        assert record["theme"] == specimen["record_decoded"]["theme"] == "default"
        assert record["view"] == specimen["record_decoded"]["view"] == "codeChart"

        # …and the RAW record is one of the two serializations of that same JSON the server
        # has actually been observed returning (LD-218; see `accepted_record_forms`). A third
        # encoding is real drift and reddens here.
        sent, reserialized = accepted_record_forms(OUR_SOURCE)
        assert add_ons["record"] in (sent, reserialized), (
            "the server returned a THIRD record serialization — neither accepted form:\n"
            f" accepted A (what we sent, <>& escaped; observed through 2026-08-01): {sent!r}\n"
            f" accepted B (server re-serialization, escapes decoded; observed 2026-08-01):"
            f" {reserialized!r}\n got : {add_ons['record']!r}")
        evidence["record_serialization"] = (
            "sent-form" if add_ons["record"] == sent else "server-reserialized")
        evidence["specimen_shape_match"] = True

        # 4) PROJECTION TWO — OUR READER renders it as a DIAGRAM. This is the FALSE-GO check:
        #    an inert shell would come back as the unsupported-add-on marker or as nothing.
        md_created, tree_created = _download(doc_id)
        assert "```mermaid" in md_created, (
            f"FALSE GO: the created block did not render as a diagram fence:\n{md_created}")
        assert "[Unsupported Add-On block:" not in md_created, (
            f"FALSE GO: the block came back as an unsupported add-on:\n{md_created}")
        for line in OUR_SOURCE.strip().split("\n"):
            assert line in md_created, f"the diagram source lost a line: {line!r}"
        created_diagrams = _diagrams(tree_created)
        assert len(created_diagrams) == 1, created_diagrams
        assert created_diagrams[0].mermaid_source.strip() == OUR_SOURCE.strip()
        evidence["reader_renders_fence"] = True

        # the write was purely ADDITIVE — no baseline line changed or disappeared
        removed = [ln for ln in md_baseline.splitlines() if ln not in md_created.splitlines()]
        assert not removed, f"the insert was not purely additive; lost lines: {removed}"

        # 5) THE REPLACE ROUTE (AC3) — there is no in-place update, so change it by
        #    insert-at-the-same-index + delete, and MEASURE the block_id cost.
        replace_plan = dry_run(
            [
                InsertRequest(reference=AnchorById(block_id=diagram_id),
                              position=InsertPosition.BEFORE,
                              content=(NewBlock.mermaid(REVISED_SOURCE),)),
                DeleteRequest(target=AnchorById(block_id=diagram_id)),
            ],
            tree_created,
        )
        assert len(replace_plan.refusals) == 0, replace_plan.refusals
        replace_log = apply(replace_plan, wc, doc_id)
        assert [e.outcome for e in replace_log.entries] == ["inserted", "deleted"], (
            [e.to_dict() for e in replace_log.entries])
        (new_diagram_id,) = replace_log.entries[0].created_block_ids
        assert new_diagram_id != diagram_id, (
            "THE DOCUMENTED COST DID NOT MATERIALIZE: the replace route must yield a NEW "
            f"block_id, got {new_diagram_id!r} both times")
        evidence["new_diagram_block_id"] = new_diagram_id
        evidence["block_id_changed"] = True

        # the delete's recovery record must carry the diagram it removed (a diagram has no
        # `elements` container, so this is the one payload shape that could come back empty)
        removed_payload = replace_log.entries[1].removed_payload
        assert removed_payload.get("add_ons"), (
            f"the destructive-delete record lost the diagram: {removed_payload}")
        assert json.loads(removed_payload["add_ons"]["record"])["data"] == OUR_SOURCE
        evidence["removed_payload_reconstructable"] = True

        # 6) …and the REPLACEMENT renders, with the old source gone.
        md_replaced, tree_replaced = _download(doc_id)
        assert "```mermaid" in md_replaced, md_replaced
        assert f'Archived {SUFFIX}' in md_replaced, (
            "the revised diagram did not render its new source")
        assert len(_diagrams(tree_replaced)) == 1, (
            "the replace route must leave exactly ONE diagram, not two")
        assert _diagrams(tree_replaced)[0].mermaid_source.strip() == REVISED_SOURCE.strip()
        evidence["replacement_renders"] = True

    finally:
        # 6) Teardown so NOTHING persists — on success AND failure. ZERO ORPHANS.
        #
        # THE CHILD RANGE COMES OFF THE LIVE ROOT, never off a count held here. A held count
        # is wrong in two directions and was wrong in this gate's first version: the root of a
        # freshly created document may hold ZERO children rather than the one Lark's editor
        # shows, and the replace route changes how many blocks exist at the top level — so
        # `end_index` past the real child count is refused `1770001`, the refusal is swallowed
        # by the except below, `emptied` stays False and the gate fails *in teardown* while the
        # disposable survives. Reading the live range also makes this idempotent: a second call
        # finds zero children and issues no write at all. This is the pattern
        # `tests/authoring_gate.py::authoring_teardown` already ships and documents.
        emptied = False
        deleted = None
        try:
            children = wc.get_block(doc_id, doc_id).get("children") or []
            evidence["children_at_teardown"] = len(children)
            if children:
                wc.batch_delete(doc_id, doc_id, 0, len(children))
                evidence["children_removed"] = len(children)
            md_empty, tree_empty = _download(doc_id)
            emptied = (
                "```mermaid" not in md_empty
                and SUFFIX not in md_empty
                and not _diagrams(tree_empty)
            )
        except LarkDocIOError as e:
            evidence["empty_error"] = str(e)
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["emptied"] = emptied
        evidence["deleted"] = deleted

        # THE EVIDENCE PRINT LIVES IN THE `finally`, before any assertion can preempt it. On a
        # failing run the disposable's lifecycle — its id, whether it emptied, whether it was
        # trashed — is exactly what a reviewer needs in order to confirm zero orphans, and it
        # is precisely then that a print after the assert would be discarded.
        with capsys.disabled():
            print(
                "\n[live_write:LD192-mermaid-gate] "
                f"doc_id={evidence['doc_id']} "
                f"diagram_block_id={evidence.get('diagram_block_id')} "
                f"specimen_shape_match={evidence.get('specimen_shape_match')} "
                f"record_serialization={evidence.get('record_serialization')} "
                f"reader_renders_fence={evidence.get('reader_renders_fence')} "
                f"new_diagram_block_id={evidence.get('new_diagram_block_id')} "
                f"block_id_changed={evidence.get('block_id_changed')} "
                f"removed_payload_reconstructable="
                f"{evidence.get('removed_payload_reconstructable')} "
                f"replacement_renders={evidence.get('replacement_renders')} "
                f"children_at_teardown={evidence.get('children_at_teardown')} "
                f"children_removed={evidence.get('children_removed')} "
                f"empty_error={evidence.get('empty_error')} "
                f"emptied={evidence.get('emptied')} deleted={evidence.get('deleted')}"
            )

    assert emptied, "teardown failed: authored diagram content still present after restore"


def test_this_gate_never_addresses_the_specimen_document():
    """A structural assertion, not a promise: the gate's own source contains no specimen token
    and no env-var reference to one, so there is no code path by which it could write to — or
    even read — the maintainer-provided document. The specimen comparison is against a committed
    capture on disk.
    """
    whole = Path(__file__).read_text(encoding="utf-8")
    # Scope to the code ABOVE this test — that is the gate itself, and it keeps the check from
    # matching its own forbidden-name literals (a self-referential guard that always reddens
    # teaches nothing and gets deleted).
    marker = "def test_this_gate_never_addresses_the_specimen_document"
    gate_source = whole.split(marker, 1)[0]
    assert marker in whole and len(gate_source) > 1000, "the split marker moved"

    # The specimen's own token is read from the committed capture, so the guard forbids the
    # document the specimen actually came from. LD-695: it used to be a literal that matched no
    # token in the capture (the original never equalled the specimen's id, and its fake still
    # did not), so it forbade nothing.
    specimen_token = json.loads(
        (CAPTURES / "20-specimen.json").read_text(encoding="utf-8"))["file_token"]
    assert specimen_token, "the specimen capture lost its file_token"
    for forbidden in ("LARKDOCIO_MERMAID_SPECIMEN" + "_DOC",
                      specimen_token,
                      "LARKDOCIO_CANARY" + "_DOC",
                      "LARKDOCIO_SCRATCH" + "_DOC"):
        assert forbidden not in gate_source, (
            f"this gate must not reference {forbidden} — disposables only")
    assert "create_document" in gate_source and "delete_document" in gate_source, (
        "the gate must provision and destroy its own disposable")
    # …and the teardown is in a `finally`, so a mid-gate failure still cleans up.
    assert "finally:" in gate_source, "the disposable must be deleted in a finally block"


def test_the_teardown_reads_its_child_range_off_the_LIVE_root():
    """A regression guard on the bug that failed this gate's first review.

    The teardown used ``batch_delete(doc, doc, 0, <count held in the test>)``. In a tenant where
    ``create_document`` returns a root with ZERO children that end index overshoots the real
    child count, Lark refuses ``1770001``, the refusal is swallowed by the teardown's ``except``,
    and the gate fails *in teardown* with the disposable still alive. Reading the live root is
    both correct and idempotent, so it is pinned here rather than left to reviewer memory.
    """
    whole = Path(__file__).read_text(encoding="utf-8")
    # Scope to the gate itself, so the check does not match the held-count name in its own
    # explanation (the same self-reference trap the disposables guard above documents).
    gate_source = whole.split("def test_this_gate_never_addresses_the_specimen_document", 1)[0]
    teardown = gate_source.split("    finally:", 1)[1].split("\n    assert emptied", 1)[0]

    assert "get_block(doc_id, doc_id)" in teardown, (
        "the teardown must read the LIVE root's children before deleting")
    assert "len(children)" in teardown, (
        "the delete range must be derived from the live child list")
    held_count_name = "n" + "_top"
    assert held_count_name not in gate_source, (
        "a held top-level count is exactly the bug this guard exists for")


def test_the_accepted_record_serializations_are_exactly_two_and_derived():
    """LD-218 (AC3) — the raw-record membership set, pinned OFFLINE so it cannot widen.

    The gate accepts **two** raw serializations of the same decoded record and nothing else.
    Both are *derived* from :func:`mermaid_record`'s own output — there is no second
    hand-written literal here that could drift away from the encoder on its own.
    """
    ours, server = accepted_record_forms(OUR_SOURCE)

    # exactly two, distinct, and the second is the first with the three escapes decoded
    assert ours == mermaid_record(OUR_SOURCE)
    assert server != ours, "the two accepted forms must actually differ for this source"
    assert "\\u003c" in ours and "<br/>" not in ours, ours
    assert "<br/>" in server and "\\u003c" not in server, server
    assert "&" in server and "\\u0026" not in server, server

    # …and they are the SAME decoded record — that is the binding round-trip claim (AC1).
    assert json.loads(ours) == json.loads(server) == {
        "data": OUR_SOURCE, "theme": "default", "view": "codeChart"}

    # membership accepts both…
    assert ours in accepted_record_forms(OUR_SOURCE)
    assert server in accepted_record_forms(OUR_SOURCE)
    # …and REJECTS a third mutation: one escape flipped, everything else identical.
    half_decoded = ours.replace("\\u0026", "&", 1)
    assert half_decoded not in (ours, server), "the mutation must be a genuine third form"
    assert half_decoded not in accepted_record_forms(OUR_SOURCE), (
        "the accepted set silently widened: a half-decoded record was accepted")
    # …and a record whose *decoded* content differs is never accepted, whichever escaping.
    for form in accepted_record_forms(OUR_SOURCE + "    D --> E\n"):
        assert form not in accepted_record_forms(OUR_SOURCE)


def test_the_evidence_print_is_INSIDE_the_finally():
    """A print after ``assert emptied`` is discarded on the runs that need it most — a failing
    teardown is when the disposable's lifecycle has to be visible."""
    whole = Path(__file__).read_text(encoding="utf-8")
    gate_source = whole.split("def test_this_gate_never_addresses_the_specimen_document", 1)[0]
    after_finally = gate_source.split("    finally:", 1)[1]
    print_at = after_finally.index("[live_write:LD192-mermaid-gate]")
    assert_at = after_finally.index("assert emptied")
    assert print_at < assert_at, (
        "the evidence print must come before the post-teardown assertion")
