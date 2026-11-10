"""Shared scaffolding for THE ROUND-TRIP GATE — the four live round-trip arms (LD-236).

The arms live in four ``tests/test_live_write_round_trip_*_gate.py`` modules (one per
invariant, so a failure names the invariant it broke). Everything they have in common — the
reader-side download, the project → edit → reconcile → compile → dry-run → apply chain, the
write counter, the marker scan and the seeding — is here, written once.

**No arm may reach Lark through anything but the shipped surfaces.** The chain below is the
shipped one end to end: :func:`~larkdocio.model.projection.project_block_ids` →
:func:`~larkdocio.write.reconcile.reconcile` →
:func:`~larkdocio.write.compiler.compile_reconciliation` →
:func:`~larkdocio.write.preview.dry_run` → :func:`~larkdocio.write.apply.apply`. Nothing here
re-implements a step; the point of a live gate is that the shipped path is the exercised path.

**Disposables discipline (the round-trip-editing spec § gate 3).** Every document an arm writes to is one the arm
itself created via ``create_document`` and trashes in a ``finally``, with the id ledgered by
:mod:`docx_ledger` and the ledger independently re-queried at close. No arm ever names the
read canary (``LARKDOCIO_CANARY_DOC``), the block-zoo doc, or any pre-existing document —
there is no code path here that takes a document id from the environment.
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager

import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.model.projection import project_block_ids
from larkdocio.model.renderer import BLOCK_ID_MARKER_LINE_RE
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    InsertPosition,
    InsertRequest,
    apply,
    compile_reconciliation,
    compose,
    dry_run,
    reconcile,
)

#: The write app's tenant region (the toolkit's default OpenAPI domain). NOT a document URL —
#: no arm in this ring addresses a pre-existing document.
DOMAIN = "larksuite.com"

#: One suffix per ring, so every seeded line is identifiable in a diff and a teardown can tell
#: the gate's own content from anything else. Deliberately carries NO Markdown metacharacter
#: (a hyphen escapes to ``\-`` in the projection), so an arm can name a seeded line by the
#: same literal in the reader's Markdown and in the escaped projection.
SUFFIX = "ld236ring"

#: The paragraph every arm seeds first and anchors its content after.
ANCHOR_LINE = f"anchor paragraph for the round-trip ring :: {SUFFIX}"

#: Marker-shaped text, matched WITHOUT the line anchor the shipped scan uses — deliberately
#: wider than the projection's own recognizer, because the question an arm asks is "did a
#: marker reach Lark ANYWHERE", including mid-line where the reconciler's line-anchored scan
#: does not look.
MARKER_RE = re.compile(r"<!--\s*lark:block:([^\s>]+?)\s*-->")


def marker_hits(blob):
    """Every marker-shaped occurrence in ``blob`` — ``[(whole, block_id), …]``."""
    return [(m.group(0), m.group(1)) for m in MARKER_RE.finditer(blob or "")]


def segment_of(projection, block_id):
    """``(marker_line, body)`` for ``block_id`` inside ``projection.markdown``.

    The two halves are returned separately because the conservation arm needs to omit them
    **independently**: dropping both is an editor deleting a block it could not represent;
    dropping only the marker while keeping the content is the LD-238 shape — the one that was
    reported conserved *and* re-created. ``marker_line + body`` is a verbatim substring of the
    projection, so an arm removes a region by :meth:`str.replace` rather than by re-rendering.
    """
    lines = projection.markdown.splitlines(keepends=True)
    known = set(projection.block_ids)
    start = None
    for i, line in enumerate(lines):
        match = BLOCK_ID_MARKER_LINE_RE.match(line.rstrip("\r\n"))
        if match and match.group(1) == block_id:
            start = i
            break
    assert start is not None, f"{block_id!r} has no marker line in the projection"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        match = BLOCK_ID_MARKER_LINE_RE.match(lines[j].rstrip("\r\n"))
        if match and match.group(1) in known:
            end = j
            break
    return lines[start], "".join(lines[start + 1:end])


def opaque_body_ids(projection, document_id):
    """The conserved block ids that are real content — the page root is not one of them."""
    return [b for b in projection.opaque_block_ids if b != document_id]


# --------------------------------------------------------------------------- #
# The reader side                                                              #
# --------------------------------------------------------------------------- #

def download(document_id):
    """``(markdown, tree, revision)`` through the SHIPPED reader — one read, all three.

    Prefers the READ credentials (the two-app least-privilege separation) and falls back to
    the owning WRITE app, because a separate read-only app is not a collaborator on a document
    this ring just provisioned. A **read** fallback only, never the other way.
    """
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
            return (parser.parse_docx_content(docx.document_id, blocks),
                    parser.parse_docx_tree(docx.document_id, blocks),
                    docx.revision_id)
        except Exception as e:      # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


#: The tenant host the disposables live behind. Paired with :func:`document_url` below.
TENANT_HOST = "your-domain.larksuite.com"


def document_url(document_id):
    """The tenant-host URL for a document **this ring created** — the input a caller pastes.

    It lives here rather than in an arm for the reason ``gate_shape.FORBIDDEN_TARGETS`` bans a
    ``/docx/`` literal from a gate file at all: a URL written into an arm is how an arm comes
    to address a document it did not create. This takes the id as an argument, so the only URL
    an arm can build is one for a document it is already holding, and the ban on the literal
    stays absolute where it matters.
    """
    assert document_id, "document_url needs the id of a document this ring created"
    return f"https://{TENANT_HOST}/docx/{document_id}"


def raw_block_payload(document_id):
    """The document's RAW block payload as one JSON blob — the *other* representation.

    The reader's Markdown is a projection; a marker could survive in a block's stored text and
    never be rendered (an unrendered property, a table cell the Markdown escapes). So the
    no-marker arm scans the payload the API answered with as well, serialized whole. Every SDK
    object is dumped by its own ``__dict__``, so nothing is filtered on the way.
    """
    attempts = []
    if canary_support.read_creds_available():
        attempts.append(get_read_credentials())
    attempts.append(get_write_credentials())

    last_err = None
    for (app_id, app_secret) in attempts:
        try:
            _docx, blocks = ReadClient(app_id, app_secret, DOMAIN).get_docx_content(
                document_id)
            return json.dumps(
                blocks, ensure_ascii=False,
                default=lambda o: getattr(o, "__dict__", None) or str(o),
            )
        except Exception as e:      # noqa: BLE001
            last_err = e
    raise last_err


def project(document_id):
    """``(markdown, tree, revision, projection)`` — a read plus the id-anchored projection."""
    markdown, root, revision = download(document_id)
    return markdown, root, revision, project_block_ids(root)


# --------------------------------------------------------------------------- #
# The write side                                                               #
# --------------------------------------------------------------------------- #

@contextmanager
def measured_writes(write_client):
    """Count every MUTATING call the client makes while the block runs.

    Yields the list the calls are appended to, so ``assert calls == []`` is the zero-write
    proof measured **at the client boundary** rather than inferred from a document diff. The
    read legs (``get_block`` / ``get_document``) are deliberately not counted: re-validating
    is not writing.
    """
    calls = []
    originals = {}
    for name in ("create_children", "_patch_block", "batch_delete"):
        original = getattr(write_client, name)
        originals[name] = original

        def spy(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        setattr(write_client, name, spy)
    try:
        yield calls
    finally:
        for name, original in originals.items():
            setattr(write_client, name, original)


def seed_paragraphs(write_client, document_id, lines):
    """Put ``lines`` at the top of the document as plain paragraphs (the arm's fixture).

    Deliberately the RAW ``create_children`` leg rather than the plan gate: this is a fixture,
    not the thing under test, and one arm needs text ``compose()`` would refuse to author
    (the adversarial marker-shaped control), which is exactly the shape an editor's own typing
    produces.
    """
    from larkdocio.write.client import text_block

    return write_client.create_children(
        document_id, document_id, [text_block(line) for line in lines], index=0)


def seed_markdown(write_client, document_id, markdown, *, after=ANCHOR_LINE):
    """Author ``markdown`` after the ``after`` line THROUGH THE PLAN GATE.

    The one way structure (a table, a heading) gets into a document here — via ``compose`` →
    ``dry_run`` → ``apply``, so Lark provisions a table's cells from the grid property and the
    engine fills them, exactly as a consumer's authoring call does. Returns the apply-log.
    """
    _markdown, root, revision = download(document_id)
    plan = dry_run(
        [InsertRequest(reference=Anchor(quote=after, breadcrumb=()),
                       position=InsertPosition.AFTER,
                       content=compose(markdown))],
        root,
        document_revision_id=revision,
    )
    assert not plan.refusals, [e.to_dict() for e in plan.refusals]
    return apply(plan, write_client, document_id=document_id)


def reconcile_only(projection, edited_markdown, **kwargs):
    """``reconcile`` alone — for the arms whose expected outcome is a REFUSAL (zero writes)."""
    return reconcile(projection, edited_markdown, **kwargs)


def apply_edited_projection(
    write_client, document_id, *, root, revision, projection, edited_markdown, **kwargs
):
    """The whole shipped chain for one edited projection, in one call.

    Returns ``{"plan", "requests", "preview", "log", "writes"}``. A plan that REFUSED returns
    early with ``requests``/``preview``/``log`` at ``None`` and ``writes == []`` — a refusal
    is a plan that refuses, and there is nothing to compile, so the zero-write claim is
    structural rather than measured after the fact.
    """
    result = {"plan": None, "requests": None, "preview": None, "log": None, "writes": []}
    plan = reconcile(projection, edited_markdown, **kwargs)
    result["plan"] = plan
    if not plan.ok:
        return result
    requests = compile_reconciliation(plan, projection)
    result["requests"] = requests
    with measured_writes(write_client) as writes:
        preview = dry_run(requests, root, document_revision_id=revision)
        result["preview"] = preview
        result["log"] = apply(preview, write_client, document_id=document_id)
    result["writes"] = writes
    return result


def empty_document(write_client, document_id):
    """Delete every top-level child — the restore-to-baseline half of teardown.

    Idempotent by construction: the range comes off the LIVE root rather than a count held in
    the arm, so a second call finds nothing and issues no write at all.
    """
    children = write_client.get_block(document_id, document_id).get("children") or []
    if children:
        write_client.batch_delete(document_id, document_id, 0, len(children))
    return len(children)


# --------------------------------------------------------------------------- #
# Diffing — "surgical" has to mean something checkable                           #
# --------------------------------------------------------------------------- #

def changed_lines(before, after):
    """``(only_in_before, only_in_after)`` as line multisets — the surgical-diff evidence.

    A multiset rather than a set difference, so a line duplicated by a botched apply shows up
    instead of collapsing into the copy that was already there.
    """
    from collections import Counter

    b, a = Counter(before.splitlines()), Counter(after.splitlines())
    gone = sorted((b - a).elements())
    added = sorted((a - b).elements())
    return gone, added
