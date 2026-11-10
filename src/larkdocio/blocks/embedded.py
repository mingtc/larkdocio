"""Embedded-data placeholder handlers — bitable (18), sheet (30),
reference_base (53) (LD-048, Decision a).

Embedded Base / Sheet blocks carry only an id (``token``; ``+ view_id`` for 53) —
the actual records / cells / views live in a SEPARATE Base or Sheet document.
**By default these handlers do zero API interaction**; each block's contents are
reachable only through an **opt-in** deep-read bridge (sheet 30 → LD-105,
:mod:`larkdocio.sheets.embed`; Base 18/53 → LD-250, :mod:`larkdocio.base.embed`),
which is off unless a consumer asks for it and degrades back to the placeholder on
any failure. Per Decision (a) (no silent drops) each CONSTRUCTs a
typed node whose renderer emits a **traceable marker** naming the block + its
id(s) — the ``reference_synced`` (``synced.py``) / file-attachment (``file.py``)
placeholder precedent. This UPGRADES 18/30 from intentionally-skipped and 53 from
unregistered-warn to a ``placeholder``.

The handlers own the falsy-aware ``'unknown'`` default (a data concern, exactly
like :func:`~larkdocio.blocks.synced.handle_reference_synced` /
:class:`~larkdocio.model.nodes.AddOnsNode`): the ``not hasattr`` guard fires only
for a truly absent attribute (yielding a ``None``-token node that renders ``""``);
a present-but-``None`` payload (a mis-routed block) still emits a marker with
``'unknown'`` ids.
"""
from typing import Any, TYPE_CHECKING

from . import register_block
from larkdocio.model import BitableNode, Node, ReferenceBaseNode, SheetNode
from larkdocio.read.references import (
    EMBEDDED_BASE,
    EMBEDDED_SHEET,
    deep_read_reason,
    note_reference,
)

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


def _base_deep_read(parser: "Parser", token: str):
    """The ONE embedded-Base deep-read call site — both embed types (18 and 53) reach the
    bridge through here, never through a copy of it (LD-250).

    Gated on BOTH the flag and an injected client, so the default path never imports the
    Base bridge nor issues a fetch. The bridge is graceful (returns ``None``, never raises),
    and ``None`` keeps the block's own traceable placeholder.
    """
    if not (getattr(parser, "deep_read_bases", False)
            and getattr(parser, "base_client", None)):
        return None
    from larkdocio.base.embed import deep_read_embedded_base

    return deep_read_embedded_base(
        parser.base_client, token, renderer=getattr(parser, "renderer", None))


def _base_deep_read_enabled(parser: "Parser") -> bool:
    """Was a Base deep read actually ATTEMPTED — flag AND client both present?

    The same gate :func:`_base_deep_read` applies, read as a question rather than acted
    on, so the unfetched-references summary can tell *not enabled* from *attempted and
    degraded* (LD-334) without a second definition of the gate.
    """
    return bool(getattr(parser, "deep_read_bases", False)
                and getattr(parser, "base_client", None))


def _note_base(parser: "Parser", node) -> None:
    """Record this embedded Base on the parser's reference queue (LD-334).

    Both Base embed types (18 and 53) report as ONE class, off the node's OWN
    ``deep_read_markdown`` — a Base that came back as a table is *fetched* and is not
    disclosed; one that did not says which of the two reasons applies. Called only where a
    marker is actually emitted, so the summary counts exactly what the reader disclosed.
    """
    fetched = node.deep_read_markdown is not None
    note_reference(
        parser, EMBEDDED_BASE, node.token, fetched=fetched,
        reason=deep_read_reason(enabled=_base_deep_read_enabled(parser), fetched=fetched),
    )


@register_block(18)
def handle_bitable(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse an embedded Base (bitable, type 18) into a traceable placeholder — or,
    **opt-in**, its deep-read table (LD-250).

    Payload is ``{token, view_type}``; only the ``token`` is marked (the zoo's
    live specimen carried a null ``view_type``). Switching an embedded base to a
    named view converts it to a :func:`handle_reference_base` (type 53)
    instead — the marker names that relationship (AC2).

    **Deep-read is opt-in and default-off.** With the parser's ``deep_read_bases`` flag off
    (the default) — or on with no ``base_client`` — this emits the traceable placeholder and
    makes **zero** Base API calls, so default docx Markdown is byte-identical to today. When
    a consumer opts in, the compound ``token`` (``<app_token>_<table_id>``) is bridged
    through the standalone Base path to render **only the referenced table** in place of the
    marker. The zoo's committed type-18 fixture is a **husk** (a zero-table app) and a
    freshly docx-born embed is not — a stale token is a state, not a type — so 18 and 53
    share :func:`_base_deep_read` and the same degrade.
    """
    if not b or not hasattr(b, "bitable"):
        return BitableNode()
    token = getattr(b.bitable, "token", None) or "unknown"
    node = BitableNode(token=token)
    node.deep_read_markdown = _base_deep_read(parser, token)
    _note_base(parser, node)
    return node


@register_block(30)
def handle_sheet(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse an embedded Sheet (type 30) into a placeholder — or, **opt-in**, its
    deep-read values table (LD-105).

    Payload is ``{token, row_size, column_size}``, but the live dims arrive
    ``None`` — so the placeholder marker is **token-only** (there is nothing else
    to mark).

    **Deep-read is opt-in and default-off (D2/D8).** With the parser's
    ``deep_read_sheets`` flag off (the default) — or on but with no
    ``sheets_client`` supplied — this emits the traceable placeholder and makes
    **zero** Sheets API calls, so default docx Markdown is byte-identical to today.
    When a consumer opts in, the compound ``token``
    (``<spreadsheet_token>_<sheet_id>``) is bridged through the standalone Sheets
    path to render **only the referenced ``sheet_id`` tab** (D3) in place of the
    marker. ANY deep-read failure (malformed token, unresolvable tab, API error,
    missing scope) degrades back to the placeholder — a docx download never fails
    because an embedded sheet could not be read (:mod:`larkdocio.sheets.embed`).
    """
    if not b or not hasattr(b, "sheet"):
        return SheetNode()
    token = getattr(b.sheet, "token", None) or "unknown"
    node = SheetNode(token=token)
    enabled = bool(getattr(parser, "deep_read_sheets", False)
                   and getattr(parser, "sheets_client", None))

    # Opt-in deep-read: gated on BOTH the flag and an injected client, so the
    # default path never imports the sheets bridge nor issues a fetch. The bridge
    # is graceful (returns None, never raises) — None keeps the placeholder.
    if enabled:
        from larkdocio.sheets.embed import deep_read_embedded_sheet

        deep = deep_read_embedded_sheet(
            parser.sheets_client,
            token,
            renderer=getattr(parser, "renderer", None),
            # Opt-in whole-cell (format-level) style fidelity (LD-117 D5a): both the flag and an
            # injected export reader must be present, else NO export is issued.
            fidelity_read=getattr(parser, "fidelity_read_sheets", False),
            export_reader=getattr(parser, "sheets_export_reader", None),
        )
        if deep is not None:
            node.deep_read_markdown = deep

    # LD-334: disclose this sheet on the parser's reference queue — fetched (it came back
    # as a table, so nothing to report) or unfetched with WHICH of the two reasons applies.
    fetched = node.deep_read_markdown is not None
    note_reference(
        parser, EMBEDDED_SHEET, token, fetched=fetched,
        reason=deep_read_reason(enabled=enabled, fetched=fetched),
    )
    return node


@register_block(53)
def handle_reference_base(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse an embedded Base switched to a named view (reference_base, type 53).

    A NEW SDK type off the 1-52 matrix; the "named-view" form of an embedded
    base — distinct from bitable (18), which a consumer hits interchangeably.
    Payload is ``{token, view_id, layout_mode}``; the marker carries the ``token``
    **and** the ``view_id`` (``layout_mode`` is dropped — no Markdown form) and
    names the 18-vs-53 relationship (AC2).

    **Opt-in deep-read, the SAME bridge type 18 rides** (:func:`_base_deep_read`, LD-250):
    default-off, zero Base API calls with the flag off, and any failure degrades back to
    this placeholder. The ``view_id`` takes no part in it — a view is **not** a column
    selector, so the deep read renders the **table's** schema exactly as the standalone Base
    read does.
    """
    if not b or not hasattr(b, "reference_base"):
        return ReferenceBaseNode()
    rb = b.reference_base
    token = getattr(rb, "token", None) or "unknown"
    view_id = getattr(rb, "view_id", None) or "unknown"
    node = ReferenceBaseNode(token=token, view_id=view_id)
    node.deep_read_markdown = _base_deep_read(parser, token)
    _note_base(parser, node)
    return node
