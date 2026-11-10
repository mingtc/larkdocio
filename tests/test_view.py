"""Type-33 `view` transparent-wrapper tests (LD-040).

Lark wraps embedded content — notably **every** ``/file`` attachment — in a
type-33 ``view`` block (``view_type=1``, sole child = the wrapped block). Before
LD-040 type 33 was unregistered, so real file attachments were **silently
dropped** (only an "Unknown block type 33" warning fired) — the type-23 file
handler was unreachable in real docs.

The view handler is **transparent**: it renders its children by their OWN
handlers with **no markup of its own**. Views are **not** homogeneous — a child
may be a file, a bitable, a sheet, … — so each child reaches its own status.
"""
import logging

from harness import render

from builders import text_block as _text


def _view(bid, parent, child_ids, view_type=1):
    """A type-33 view block (``view_type`` display mode) wrapping ``child_ids``."""
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 33,
        "view": {"view_type": view_type},
        "children": list(child_ids),
    }


def _file(bid, parent, token, name):
    """A type-23 file block (the real payload shape: sole child of a view)."""
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 23,
        "file": {"token": token, "name": name},
    }


# --- AC1: view registered as a handler -------------------------------------

def test_view_type_33_is_registered():
    """Type 33 must have a registered handler (was intentionally-skipped before)."""
    from larkdocio.blocks import get_registry

    assert 33 in get_registry(), (
        "type 33 (view) must be registered — Lark wraps file attachments in a "
        "type-33 view, so an unregistered 33 silently drops attachments."
    )


# --- AC1: a view-wrapped file reaches the file marker (transparent) --------

def test_view_wrapping_file_renders_file_marker_transparently():
    """The real shape: view(33, view_type=1) -> file(23). The file 📎 marker (name
    + token) must appear, and the view itself must add NO markup of its own."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["v1"]},
        _view("v1", "root", ["f1"]),
        _file("f1", "v1", "Example083a49b9eab9c77d38e0", "sample_logo.svg"),
    ]
    out = render(blocks, doc_id="root")
    assert "📎 **File Attachment:** sample_logo.svg" in out, out
    assert "Example083a49b9eab9c77d38e0" in out, (
        "the file token must be surfaced through the transparent view: " + out
    )
    # The view adds no wrapper markup of its own — the ONLY attachment line is the
    # file handler's own output (no "view", no "view_type", no extra decoration).
    assert "view" not in out.lower(), f"view emitted markup of its own: {out!r}"


def test_view_wrapped_file_matches_a_bare_file(caplog):
    """Transparency proof: a view-wrapped file renders byte-identically to the same
    file as a direct page child — the wrapper is invisible."""
    wrapped = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["v1"]},
        _view("v1", "root", ["f1"]),
        _file("f1", "v1", "TOK", "a.zip"),
    ]
    bare = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["f1"]},
        _file("f1", "root", "TOK", "a.zip"),
    ]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out_wrapped = render(wrapped, doc_id="root")
    out_bare = render(bare, doc_id="root")
    assert out_wrapped == out_bare, (
        f"view wrapper is not transparent:\nwrapped={out_wrapped!r}\nbare={out_bare!r}"
    )
    # And no "Unknown block type 33" warning — the view is now handled.
    assert not any("33" in r.getMessage() for r in caplog.records
                   if r.levelno >= logging.WARNING), (
        "a handled view must not warn 'Unknown block type 33'"
    )


# --- AC1: a NON-file view child reaches its OWN status (no homogeneity) -----

def test_view_wrapping_text_child_renders_it_transparently():
    """Views are not homogeneous: a view wrapping a plain TEXT block renders the
    text through its own handler (transparent), not a file marker."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["v1"]},
        _view("v1", "root", ["t1"]),
        _text("t1", "v1", "plain body under a view"),
    ]
    out = render(blocks, doc_id="root")
    assert "plain body under a view" in out, out
    assert "📎" not in out, f"a non-file view child must not become a file marker: {out!r}"


def test_view_wrapping_embedded_data_child_reaches_its_own_placeholder(caplog):
    """A view wrapping a NON-file embedded-data child (a type-18 bitable) must
    reach THAT child's own status — since LD-048 that is a 📊 traceable
    placeholder marker (the child is a registered placeholder handler now, no
    longer warn+drop), emitted transparently through the wrapper. The view makes
    no homogeneity assumption and adds no markup of its own."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["v1"]},
        _view("v1", "root", ["bt1"]),
        {"block_id": "bt1", "parent_id": "v1", "block_type": 18, "bitable": {}},
    ]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = render(blocks, doc_id="root")
    # The bitable child reaches its OWN placeholder status: a 📊 marker, not a warn.
    assert "📊 **Embedded Base**" in out, (
        f"the view-wrapped bitable (18) must reach its own placeholder marker: {out!r}"
    )
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("18" in m for m in warnings), (
        f"a registered bitable (18) placeholder must NOT warn: {warnings}"
    )
    assert "📎" not in out, f"a bitable view child must not become a file marker: {out!r}"
    # Transparency: the view adds NO markup of its own — the output is byte-identical
    # to the SAME bitable rendered un-wrapped (directly under the page).
    bare = render(
        [
            {"block_id": "root", "block_type": 1,
             "page": {"elements": [{"text_run": {"content": "Doc"}}]},
             "children": ["bt1"]},
            {"block_id": "bt1", "parent_id": "root", "block_type": 18, "bitable": {}},
        ],
        doc_id="root",
    )
    assert out == bare, f"the view wrapper must be transparent: {out!r} != {bare!r}"
