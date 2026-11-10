"""The offline doc-double for the LD-136 binding round-trip property (the Markdown-authoring spec § F1-S3).

``compose(X)`` yields typed content; the property is about what the **reader** emits once
that content exists in a document. This module is the missing middle — with **no network
and no transport**:

1. :func:`doc_double` encodes the content with the **real** encoder
   (``larkdocio.write.encode``) and builds the block payloads **Lark itself would hold**
   afterwards: the flat pre-order tree re-hung as ``children`` lists, and — for a table —
   the cell family Lark **auto-provisions** from the grid property (each type-32 cell
   wrapping one type-2 text block carrying the authored cell text). It reproduces the one
   live-verified faithfulness detail LD-135 found: Lark **omits a false ``header_row``**
   from the payload it hands back.
2. :func:`reader_markdown` renders that document with the **real** ``Parser`` +
   ``MarkdownRenderer`` and strips the page wrapper, so the result is the Markdown a
   consumer would get back from ``larkdocio download``.

Both are deterministic (ids are positional, no clock, no randomness), which is what lets
the corpus property assert exact strings.
"""
from harness import build_blocks, render  # noqa: F401  (build_blocks re-exported for tests)

from larkdocio.write.encode import encode_content


def _cell_faithful(payload: dict) -> dict:
    """Reproduce Lark's omission of a **false** ``header_row`` (live-verified, LD-135)."""
    table = payload.get("table")
    if not table or table.get("property", {}).get("header_row") is not False:
        return payload
    return {**payload, "table": {"property": {
        k: v for k, v in table["property"].items() if k != "header_row"
    }}}


#: The five style keys Lark stores **beside** a link on a cell's inner run, all false —
#: quoted from LD-517's fresh read-back
#: (``tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json``
#: § ``read_back.route_A_cell_inner_block.runs[0]``, identical on route B and on the control
#: paragraph). The encoder sends ``{"link": {"url": …}}`` alone; **Lark hands back all six**,
#: and this doc-double holds what LARK holds, so the reader is exercised against the shape
#: that actually comes off the wire. Same class of faithfulness detail as the omitted false
#: ``header_row`` above.
_STORED_STYLE_SIBLINGS = {
    "bold": False, "inline_code": False, "italic": False,
    "strikethrough": False, "underline": False,
}


def _stored_cell_elements(text, spans):
    """The elements a cell's inner text block HOLDS — plain, or a link-carrying run."""
    if not spans:
        return [{"text_run": {"content": text}}]
    out = []
    for span in spans:
        run = {"content": span.text}
        if span.link_url is not None:
            run["text_element_style"] = dict(
                _STORED_STYLE_SIBLINGS, link={"url": span.link_url})
        out.append({"text_run": run})
    return out


def doc_double(content, *, doc_id="root", title=""):
    """The block dicts a Lark document holds after ``content`` was created in it.

    ``content`` is a ``compose()`` result (or any ``InsertRequest.content`` tuple). The
    page is deliberately **untitled** by default so the rendered Markdown is the authored
    fragment alone.
    """
    encoded = encode_content(tuple(content))
    ids = [f"nb{i}" for i in range(len(encoded))]
    kids = {i: [] for i in range(len(encoded))}
    roots = []
    for i, ec in enumerate(encoded):
        (roots if ec.parent is None else kids[ec.parent]).append(ids[i])

    page = {
        "block_id": doc_id, "parent_id": "doc", "block_type": 1,
        "page": {"elements": [{"text_run": {"content": title}}] if title else []},
        "children": roots,
    }
    blocks = [page]
    for i, ec in enumerate(encoded):
        parent_id = doc_id if ec.parent is None else ids[ec.parent]
        children = list(kids[i])
        cell_ids = [f"{ids[i]}c{j}" for j in range(len(ec.cell_texts))]
        if cell_ids:
            # A table's cells are NOT encoder children — Lark provisions them from the
            # grid property, row-major, and the apply engine fills each one afterwards.
            children = cell_ids
        blocks.append({
            "block_id": ids[i], "parent_id": parent_id, "children": children,
            **_cell_faithful(ec.payload),
        })
        spans_per_cell = ec.cell_spans or (None,) * len(ec.cell_texts)
        for cell_id, text, spans in zip(cell_ids, ec.cell_texts, spans_per_cell):
            blocks.append({
                "block_id": cell_id, "parent_id": ids[i], "block_type": 32,
                "table_cell": {}, "children": [f"{cell_id}t"],
            })
            blocks.append({
                "block_id": f"{cell_id}t", "parent_id": cell_id, "block_type": 2,
                "text": {"elements": _stored_cell_elements(text, spans)},
                "children": [],
            })
    return blocks


def reader_markdown(content, *, doc_id="root") -> str:
    """The Markdown the **reader** emits for ``content`` — page wrapper stripped.

    The page contributes a leading blank line and a trailing child separator that belong
    to the document, not to the authored fragment; they are normalized away so the result
    is comparable to the fragment that was composed. Interior blank lines are left exactly
    as the renderer emitted them (they are part of the dialect).
    """
    out = render(doc_double(content, doc_id=doc_id), doc_id=doc_id)
    body = out.strip("\n")
    return body + "\n" if body else ""
