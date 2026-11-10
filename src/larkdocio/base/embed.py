"""larkdocio.base.embed — the opt-in embedded-Base deep-read bridge (LD-250).

The docx reader surfaces an **embedded Base** as a compound token
``<app_token>_<table_id>``, and **two** block types carry one: ``bitable`` (18) and
``reference_base`` (53) — embedding a Base yields 18, switching it to a named view converts
it to 53, and a consumer hits both interchangeably. This module is the **one** bridge both
of them ride: split that token on its **last** ``_`` and feed the two halves through the
SAME standalone Base path the library already ships (LD-246 renderers → LD-247 client →
LD-248 assembly), rendering **only the referenced table** — the docx author embedded one
specific table, so the deep read surfaces exactly that one, never its siblings. The Sheets
bridge (:mod:`larkdocio.sheets.embed`, block type 30) is the shape and the precedent.

**Both types, one path — because the evidence says they are one thing.** The opener's
interim posture was to bridge only 53, on the belief that a type-18 embed is a husk. The P0
pack retired that: a freshly docx-born type-18 embed bridges end to end
(``app → tables(1) → fields(3) → records/search(3)``, all ``code:0`` —
``p0-1-05-fresh-embed-bridge.json``), and the zoo's type-18 specimen is a husk only because
the zoo author had already converted it — the live block-zoo doc contains **no type-18 block
at all** (``p0-1-01``). A stale token is a *state*, not a *type*, so both types get the same
bridge and the same degrade.

Three disciplines, all load-bearing:

* **Opt-in only.** This bridge runs solely when a consumer opts in — from the command line
  (``larkdocio download … --deep-read-bases``) or in code
  (``Parser(deep_read_bases=True, base_client=...)``); the default reader path never imports
  or calls it, so default docx Markdown is byte-identical and makes **zero** Base API calls.
* **Graceful — never raises.** A malformed token, a table id that is not in the app, a
  zero-table app, a missing scope, or any API error returns ``None`` so the handler falls
  back to the traceable placeholder. **A docx download must NEVER fail because an embedded
  Base could not be deep-read.**
* **Husk-defensive.** The husk app answers ``{"items": []}`` with **no ``total``, no
  ``page_token`` and no ``has_more``** (``02-bitable18-tables.json``) — a shape no healthy
  app returns. Nothing here consults a counter or a cursor, and a zero-table app degrades to
  the placeholder rather than rendering an empty table that would assert "this Base is
  empty" about a Base nobody could read.

**The degrade path is cheap on purpose.** The table list is read **first**: a husk or a
stale tail is then one call, and the app meta (which exists only to supply the ``time_zone``
every date cell renders in) is fetched only once there is something to render. Three or four
calls per embedded Base, and not one more.

**A doc-owned embedded Base is a distinct object class.** Created by the docx block itself,
it has **no ``time_zone``** at all — so LD-246's absent-``time_zone`` fallback is not a
theoretical branch here, it is the ordinary path — a blank drive ``title`` and
``sec_label_name``, and it is not an independently deletable drive file
(``DELETE /drive/v1/files`` → ``1061003``): it dies with its parent document. The register
``BASE.md`` — in the source repository, not in the wheel — records that under § "Embedded Bases inside
a docx", for a consumer who would otherwise try to manage one as a normal Base.
"""
from typing import Optional, Tuple

from larkdocio.base.cells import RenderContext
from larkdocio.base.table import (
    DEFAULT_HEADING_LEVEL,
    assemble_table,
    render_table,
)


def split_compound_token(compound_token) -> Optional[Tuple[str, str]]:
    """Split a docx type-18 / type-53 compound token into ``(app_token, table_id)``.

    The token is ``<app_token>_<table_id>`` and is split on its **last** ``_``: an
    ``app_token`` may itself contain ``_``, so only the final underscore separates the
    referenced ``table_id``. Returns ``None`` for a malformed token — no ``_`` at all, or an
    empty half — so the caller degrades to the placeholder rather than issuing a doomed
    fetch. Never raises.

    **The Sheets rule replayed, and independently proven for Base** — the two functions are
    asserted byte-identical over a corpus rather than shared by import
    (the bridge's own test module). Base-local is deliberate, the same posture the Markdown
    assembly's ``escape_cell`` takes: reading a Base must not drag in the Sheets surface, and lifting
    a shipped surface's helper into ``common/`` would make a feature story a refactor of that
    surface.
    """
    if not compound_token or "_" not in compound_token:
        return None
    app_token, table_id = compound_token.rsplit("_", 1)
    if not app_token or not table_id:
        return None
    return app_token, table_id


def deep_read_embedded_base(
    client,
    compound_token,
    *,
    renderer=None,
    heading_level: int = DEFAULT_HEADING_LEVEL,
) -> Optional[str]:
    """Deep-read the ONE referenced table of an embedded-Base compound token.

    Splits ``compound_token`` (:func:`split_compound_token`), lists the app's tables, locates
    **only** the referenced ``table_id``, reads that table's fields and records, and renders
    it to a headed GFM table (:func:`~larkdocio.base.table.render_table`). Returns that
    table's Markdown **with a single trailing newline** (block-separation parity with the
    type-18 / type-53 placeholders), or ``None`` to degrade to the placeholder.

    ``renderer`` threads the docx reader's configured
    :class:`~larkdocio.model.MarkdownRenderer`, so a styled cell honors ``use_html_tags``
    exactly as the surrounding docx does.

    **Never raises**: a malformed token, a zero-table app, a table id the app does not know,
    a missing scope, or any API error is caught and returned as ``None``.
    """
    try:
        parts = split_compound_token(compound_token)
        if parts is None:
            return None
        app_token, table_id = parts

        # The table list FIRST: the husk and the stale-tail degrades then cost one call, and
        # the app meta is bought only once there is something to render.
        tables = client.list_tables(app_token) or ()
        table = next((t for t in tables if getattr(t, "table_id", None) == table_id), None)
        if table is None:
            # A zero-table app, or a tail that is not one of this app's tables. Either way
            # the honest answer is the placeholder — never an empty table.
            return None

        app = client.get_app(app_token)
        context = RenderContext(time_zone=getattr(app, "time_zone", None), renderer=renderer)
        assembled = assemble_table(
            table_id=table_id,
            name=getattr(table, "name", "") or table_id,
            fields=client.list_fields(app_token, table_id),
            records=client.search_records(app_token, table_id),
            context=context,
        )
        # Trailing newline so the page serializer's child separator yields a blank line
        # after the table — parity with the placeholder markers' own '\n'.
        return render_table(assembled, heading_level) + "\n"
    except Exception:
        # ANY deep-read failure degrades to the placeholder: a docx download must never fail
        # because an embedded Base could not be read.
        return None
