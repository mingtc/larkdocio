"""LD-576 — the door beside the gate is CLOSED, not blessed.

``WriteClient.patch_block`` was a public method that took the raw docx update-block oneof
body **around** everything the library sells: outside the plan gate (nothing previews it, no
``Plan`` records it), outside the ``STALE_DOCUMENT`` whole-document compare-and-swap (a
document edited under you is not detected) and outside the refusal set (no typed refusal is
raised on your behalf, and no apply-log entry is written). Two consumers on two tracks walked
through it in one review round, and one of them fired an unproven field mask at a document a
refusal had just told it was under concurrent edit.

**The fork was disclose-vs-declare-vs-fence and the maintainer ruled FENCE.** LD-562 landed the
disclosure and it is spent. This file guards the fence.

Three properties, each with its own test below:

* **the primitive is PRIVATE and still writes** — this is a rename, not a deletion. The
  engine's own internal call sites keep using it, unchanged, so nothing about what lands on a
  document moves;
* **the public NAME survives and cannot write.** It is a permanent signpost: it raises a typed
  error before anything reaches the wire, and the message names the two supported routes that
  now exist (LD-574's plan-gated ``todo.done`` edit, LD-575's append-only ``GrowTableRequest``)
  rather than saying only "deprecated". A shim that said only "deprecated" would recreate the
  disclosure defect this program exists to fix;
* **it is NEVER DECLARED — a permanent negative.** No ``OpDescriptor``, no ``capabilities()``
  entry, no permissions row, no ``PERMISSIONS.md`` line, no guide capability row. Declaring an
  operation that bypasses the plan gate, the revision guard and the entire refusal set would
  make an unsafe path *supported* — a permissions row, two guarded projections, and a
  capability that can never be removed. That discloses it by **blessing** it. Fencing satisfies
  "no undeclared capability" properly: nothing is undeclared because nothing is public.

Everything here is offline. The live arm — the proof that the renamed primitive still performs
the engine's own writes — is the ``live_write`` ring (``pytest -m live_write``).
"""
import json
import pathlib

import pytest

import larkdocio
from larkdocio import permissions
from larkdocio.errors import LarkDocIOError
from larkdocio.write.client import (
    PATCH_BLOCK_COST,
    PATCH_BLOCK_FENCE,
    WriteClient,
)
from larkdocio.write.model.requests import GrowTableRequest  # noqa: F401  (the named route)

from write_harness import StubOpener, _client, _patch_ok

_REPO = pathlib.Path(__file__).resolve().parents[1]


def _fenced_call():
    """Call the fenced name on a real client whose transport RECORDS every request."""
    opener = StubOpener([_patch_ok()])
    client = _client(opener)
    with pytest.raises(LarkDocIOError) as excinfo:
        client.patch_block("doc-1", "blk-1", {"update_text_elements": {"elements": []}})
    return excinfo.value, opener


# --------------------------------------------------------------------------- #
# AC2 — a RENAME, not a deletion: the primitive is private and still writes     #
# --------------------------------------------------------------------------- #

def test_the_primitive_is_private_and_still_writes():
    opener = StubOpener([_patch_ok()])
    client = _client(opener)
    body = {"update_text_elements": {"elements": []}}

    client._patch_block("doc-1", "blk-1", body)

    assert [r["method"] for r in opener.requests] == ["PATCH"]
    assert opener.requests[0]["body"] == body, "the oneof body on the wire is unchanged"
    assert "/docx/v1/documents/doc-1/blocks/blk-1" in opener.requests[0]["url"]


def test_the_public_name_is_no_longer_the_primitive():
    assert WriteClient.patch_block is not WriteClient._patch_block


# --------------------------------------------------------------------------- #
# AC1 — the fence: it refuses, locally, and tells the caller what to DO         #
# --------------------------------------------------------------------------- #

def test_the_fenced_call_sends_NOTHING_to_lark():
    _error, opener = _fenced_call()
    assert opener.requests == [], (
        "the fence must refuse BEFORE the wire — a fenced call that still writes is the "
        "defect this issue closes, wearing a warning")


def test_the_fence_raises_a_TYPED_error_catchable_both_ways():
    error, _opener = _fenced_call()
    assert isinstance(error, LarkDocIOError), (
        "every larkdocio failure is catchable as LarkDocIOError")
    assert isinstance(error, AttributeError), (
        "a call against a name that is not part of the public surface is, in Python's own "
        "vocabulary, an attribute problem — so a consumer's defensive `except AttributeError` "
        "still catches it")


def test_the_name_still_RESOLVES_so_a_capability_probe_does_not_change_its_answer():
    client = _client(StubOpener([]))
    assert hasattr(client, "patch_block"), (
        "import and attribute lookup are unaffected; the break is at CALL time and it is typed")


def test_the_message_NAMES_BOTH_supported_routes_that_now_exist():
    error, _opener = _fenced_call()
    message = str(error)
    for route in ("todo", "GrowTableRequest"):
        assert route in message, route
    lowered = message.lower()
    assert "checkbox" in lowered, "LD-574's route, in the words a consumer arrives with"
    assert "row" in lowered, "LD-575's route, in the words a consumer arrives with"


def test_the_message_is_not_merely_DEPRECATED():
    error, _opener = _fenced_call()
    lowered = str(error).lower()
    assert "deprecat" not in lowered, (
        'a message that says only "deprecated" tells the caller their code is broken and '
        "nothing about what to do — handoff § 3's F8 mirror")
    assert "larkdocio guide" in lowered, "the door to both routes is named"


def test_the_message_does_NOT_point_at_the_private_spelling():
    error, _opener = _fenced_call()
    assert "_patch_block" not in str(error), (
        "pointing a consumer at the private name re-opens the door under a new spelling — "
        "the disclosure defect wearing an underscore")


def test_the_fence_message_is_authored_ONCE():
    error, _opener = _fenced_call()
    assert PATCH_BLOCK_FENCE in str(error)
    core = "NOT part of larkdocio's public surface and nothing was sent"
    assert core in PATCH_BLOCK_FENCE, "the anchor this test greps for moved"
    hits = [path.name for path in (_REPO / "src" / "larkdocio").rglob("*.py")
            if core in path.read_text(encoding="utf-8")]
    assert hits == ["client.py"], hits


# --------------------------------------------------------------------------- #
# AC3 — the permanent negative, and its reason carried IN THE TREE              #
# --------------------------------------------------------------------------- #

def test_the_only_public_patch_block_spelling_on_the_class_is_the_fence():
    public = sorted(name for name in dir(WriteClient)
                    if "patch_block" in name and not name.startswith("_"))
    assert public == ["patch_block"], public
    _error, opener = _fenced_call()
    assert opener.requests == [], "and that one refuses"


def _without_the_private_spelling(text):
    """Drop every ``_patch_block`` mention, so what is left is any PUBLIC spelling.

    The private primitive is legitimately named in prose that ``capabilities(full=True)``
    projects (the W0 gate's own summary describes the mutation it performs), and naming the
    engine's internal primitive is not declaring an operation. What must not appear is the
    fenced PUBLIC name.
    """
    return text.replace("_patch_block", "«private»")


@pytest.mark.parametrize("full", [False, True])
def test_patch_block_is_declared_in_no_capabilities_payload(full):
    rendered = _without_the_private_spelling(
        json.dumps(larkdocio.capabilities(full=full), default=str))
    assert "patch_block" not in rendered


def test_patch_block_has_no_permissions_row_and_no_operation_row():
    rows = permissions.permission_registry()
    assert not [key for key in rows if "patch_block" in str(key)]
    inventory = permissions.operation_inventory()
    assert not [key for key, _ in inventory if "patch_block" in str(key)]


def test_patch_block_appears_in_no_shipped_capability_matrix():
    for name in ("PERMISSIONS.md", "BLOCKS.md", "SHEETS.md", "README.md", "TOOLS.md"):
        assert "patch_block" not in (_REPO / name).read_text(encoding="utf-8"), name


def test_the_fence_docstring_carries_the_RULINGS_REASONING_not_a_pointer_to_it():
    doc = " ".join((WriteClient.patch_block.__doc__ or "").split()).lower()
    for phrase in ("plan gate", "revision guard", "refusal set", "supported",
                   "permissions row", "never be removed", "blessing",
                   "nothing is undeclared because nothing is public"):
        assert phrase in doc, phrase


def test_the_fence_carries_its_PROVENANCE_in_the_source_beside_the_code():
    """The reasoning is consumer-safe prose and lives in the docstring; the *provenance* —
    which ruling, in which document — is repo dialect, so it lives in a comment beside the
    method instead. Both are in the tree; only one is in the wheel's docstring corpus."""
    raw = (_REPO / "src" / "larkdocio" / "write" / "client.py").read_text(encoding="utf-8")
    source = " ".join(raw.replace("#", " ").split())
    # LD-676: the handoff was pruned on 2026-09-18, so it is named, not path-cited — same
    # provenance, same ruling, no dangling pointer.
    for phrase in ("LD-576", "round-5 fix-program handoff", "§ 2.1",
                   "declare it only if you intend to keep it"):
        assert phrase in source, phrase


def test_no_internal_dialect_leaked_into_the_consumer_facing_docstrings():
    """The fence's own docstring and the error class's are read by a wheel-only consumer, so
    an issue id or a role name in either is the dialect defect the corpus guard exists for."""
    from larkdocio.errors import FencedPrimitiveError
    for doc in (WriteClient.patch_block.__doc__, FencedPrimitiveError.__doc__):
        assert "LD-5" not in (doc or ""), doc


# --------------------------------------------------------------------------- #
# AC4 — LD-562's reason is PRESERVED; only its conclusion is superseded          #
# --------------------------------------------------------------------------- #

def test_the_cost_constant_survives_and_keeps_every_substance_claim():
    lowered = PATCH_BLOCK_COST.lower()
    for phrase in ("plan gate", "stale_document", "refusal set", "read-back",
                   "in-place", "identity-preserving"):
        assert phrase in lowered, phrase


def test_the_cost_constant_is_projected_into_the_PRIVATE_primitives_docstring():
    doc = WriteClient._patch_block.__doc__ or ""
    assert PATCH_BLOCK_COST in doc
    assert "<<" not in doc, "the projection placeholder survived into the shipped docstring"


def test_the_cost_constants_CONCLUSION_moved_there_is_no_public_door():
    lowered = PATCH_BLOCK_COST.lower()
    assert "not part of the public surface" in lowered or "no public" in lowered, (
        "the reason survives; the conclusion (disclose the public door) is superseded")


# --------------------------------------------------------------------------- #
# The guards BITE — each negative above would catch its own regression          #
# --------------------------------------------------------------------------- #

def test_the_declaration_guard_would_catch_a_declared_patch_block():
    planted = json.dumps({"surfaces": {"docx-write": {"operations": ["patch_block"]}}})
    assert "patch_block" in planted


def test_the_fence_guard_would_catch_a_delegating_shim():
    """A shim that delegated would leave a PATCH on the recorder — which the fence test
    asserts is empty, so the guard bites."""
    opener = StubOpener([_patch_ok()])
    client = _client(opener)
    client._patch_block("doc-1", "blk-1", {"update_text_elements": {"elements": []}})
    assert opener.requests != []
