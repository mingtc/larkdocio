"""larkdocio.blocks.read_support — the per-block-type READ facts the wheel carries.

**The question this answers.** *"Will this document's callouts / images / boards survive
the read, and what will they turn into?"* It is a
three-part question and the honest answer needs all three parts:

1. **is the type handled?** — which is *not* stored here at all. It is
   :func:`larkdocio.blocks.get_registry` membership, read at projection time, so it cannot
   become a stale copy of the registry;
2. **what does it emit?** — the Markdown the reader produces for a block of that type;
3. **is it lossy, and how?** — one state from the closed :data:`LOSSINESS` vocabulary.

Answering only (1) is what a consumer can already do with ``get_registry()``, and doing
only that is why the question stayed open.

**Why the text lives in the package.** The authoring surface for these facts is the block
matrix at the repository root — a repo-level document the wheel deliberately does **not**
carry (``package-data`` cannot reach a file outside the package, and shipping a second copy
of a maintainer's document is not the fix). So the answer a consumer needs travels here
instead, as data beside the handlers it describes, and it is **pinned equal to that matrix's
own cells** by ``tests/test_blocks_md_matrix.py``. What that pin covers, stated cell by cell
so the claim can be checked rather than trusted: **membership** in both directions (a row
with no entry here reddens, an entry with no row reddens, and a handler registered for a
type with no entry makes :func:`larkdocio.capabilities` refuse to build at all), and then
each copied cell against the matrix's own — **name** verbatim (LD-203; a consumer keys rows
by it), **emission** prose-normalized, **lossiness** verbatim. ``handled`` is copied from
nothing at all: it is a live :func:`larkdocio.blocks.get_registry` join. The matrix stays
the place a maintainer edits; this table cannot drift from it.

**Read-only, and one axis only.** Nothing here says what a block type can be *written* —
that axis is projected separately as the creatable-content floor, and mixing the two would
rot this table the moment a type became creatable.
"""

#: ``(state, what the state means)`` — the CLOSED read-lossiness vocabulary, and the whole
#: reason the answer is a state name rather than a boolean: "lossy: true" is the same word
#: for a heading that comes back one level shallower and for a whiteboard whose pixels are a
#: separate file. Both are lossy; a consumer plans differently for each. The meanings ship
#: **with** the projection, because a consumer holding only the wheel cannot open the matrix
#: these words are defined in.
LOSSINESS = (
    (
        "full",
        "The block's text and its structure both come through into the Markdown. What is "
        "left out is only what Markdown has no form for at all — a run's colors, a block's "
        "alignment, the review anchors on it — and each of those is on the node tree, which "
        "is the full-fidelity level this projection is the reading form of.",
    ),
    (
        "projected",
        "The content comes through in a DIFFERENT shape than the block's own, so reading "
        "the Markdown cannot tell you the original shape: a merged table is serialized as "
        "HTML because pipe tables have no spans, a heading past level 6 comes back as a "
        "level-6 one, a layout container is flattened, and a diagram add-on comes back as "
        "its source text in a fenced block. The block's own shape is on the node tree.",
    ),
    (
        "out-of-band",
        "The content is not text and does not travel in the Markdown at all: the reader "
        "downloads it as a separate file and the Markdown carries a link to it. Read the "
        "Markdown alone and you have the reference, not the picture.",
    ),
    (
        "reference-only",
        "A traceable marker naming the block and its id is emitted instead of the content, "
        "because the content lives somewhere this read does not go — another document, a "
        "separate service, or a binary this read does not fetch. The marker is deliberate: "
        "it is what makes the reference findable rather than absent.",
    ),
    (
        "not-handled",
        "No handler is registered for this type. The reader logs one warning, emits nothing "
        "of the block's own, and renders its children transparently — so an unhandled "
        "CONTAINER still surfaces its subtree while an unhandled leaf emits nothing at all.",
    ),
)

#: What happens to a block type this table does not list — the forward-compat answer, which
#: a per-type table structurally cannot give row by row. Lark adds block types; the reader
#: does not fail on one.
UNLISTED_TYPE = (
    "A block type not listed here is treated exactly as the 'not-handled' state describes: "
    "one warning, the block's own content emitted nowhere, and its children rendered "
    "transparently. That is the forward-compatible path for a type Lark adds after this "
    "release, and it is also what block type 999 (the API's own undefined fallback) takes."
)

#: The one paragraph a consumer — or an agent relaying to one — can read to decide whether
#: the Markdown projection is enough for the document they hold.
SUMMARY = (
    "Per docx block type: is it handled, what Markdown does the reader emit for it, and is "
    "that emission lossy. This is the answer to 'will the things in my document survive the "
    "read', and it is about the MARKDOWN PROJECTION only — the node tree is the "
    "full-fidelity level, and a type that reads lossily into Markdown still arrives whole "
    "there. Handled-ness is the live handler registry, not a list; the other two answers are "
    "pinned against the block matrix in the development repository, whose cells they are."
)

#: ``(block_type, name, lossiness, what it emits)`` — one row per docx block type, plus the
#: API's ``999`` undefined fallback. Every row's name, state and emission is the matching
#: cell of the block matrix in the development repository, pinned equal by the drift guard;
#: ``handled`` is deliberately absent, because the registry answers it.
READ_SUPPORT = (
    (
        1, 'page', 'full',
        '`# {title}\\n`, then recurses children',
    ),
    (
        2, 'text', 'full',
        'Inline text run(s) + `\\n`; **literal Markdown metacharacters in PLAIN text are backslash-escaped so text can never parse as structure (always on)**; **bare URLs are auto-linkified (always on)**; @mention text is resolved to `@Name` by default at download time',
    ),
    (
        3, 'heading1', 'full',
        '`# ` + text + child NODES',
    ),
    (
        4, 'heading2', 'full',
        '`## ` + text + children',
    ),
    (
        5, 'heading3', 'full',
        '`### ` + text + children',
    ),
    (
        6, 'heading4', 'full',
        '`#### ` + text + children',
    ),
    (
        7, 'heading5', 'full',
        '`##### ` + text + children',
    ),
    (
        8, 'heading6', 'full',
        '`###### ` + text + children',
    ),
    (
        9, 'heading7', 'projected',
        '`###### ` + text — **capped**, never a longer marker',
    ),
    (
        10, 'heading8', 'projected',
        '`###### ` + text — **capped**',
    ),
    (
        11, 'heading9', 'projected',
        '`###### ` + text — **capped**',
    ),
    (
        12, 'bullet', 'full',
        '`- ` + text; child NODES rendered at `depth + 1`',
    ),
    (
        13, 'ordered', 'full',
        '`N. ` + text; child NODES at `depth + 1`',
    ),
    (
        14, 'code', 'full',
        '```` ```{lang}\\n…\\n``` ````',
    ),
    (
        15, 'quote', 'full',
        '`> ` per line',
    ),
    (
        16, 'equation', 'full',
        '`$$\\n{content}\\n$$\\n`',
    ),
    (
        17, 'todo', 'full',
        '`- [ ] ` / `- [x] ` + text; child NODES at `depth + 1`',
    ),
    (
        18, 'bitable', 'reference-only',
        "`> 📊 **Embedded Base** (bitable) — not fetched. token: `{token}`. …\\n` (default) · the referenced table's GFM table (opt-in deep-read)",
    ),
    (
        19, 'callout', 'projected',
        'Renders its own children, prefixes **every** output line with `> ` (a true blockquote)',
    ),
    (
        20, 'chat_card', 'not-handled',
        '(warns, dropped)',
    ),
    (
        21, 'diagram', 'not-handled',
        '(warns, dropped)',
    ),
    (
        22, 'divider', 'full',
        '`---\\n`',
    ),
    (
        23, 'file', 'reference-only',
        '`📎 **File Attachment:** {name} (token: `{token}`)\\n`',
    ),
    (
        24, 'grid', 'projected',
        'Flattens grid columns → their children, joined by a blank line',
    ),
    (
        25, 'grid_column', 'projected',
        '`""` (nothing directly)',
    ),
    (
        26, 'iframe', 'projected',
        '`[{url}]({url})\\n` (the decoded embed URL as a Markdown link)',
    ),
    (
        27, 'image', 'out-of-band',
        '`![{caption}]({token})\\n`',
    ),
    (
        28, 'isv', 'not-handled',
        '(warns, dropped)',
    ),
    (
        29, 'mindnote', 'not-handled',
        '(warns, dropped)',
    ),
    (
        30, 'sheet', 'reference-only',
        "`> 📊 **Embedded Sheet** — not fetched. token: `{token}`. …\\n` (default) · the referenced tab's GFM table (opt-in deep-read)",
    ),
    (
        31, 'table', 'projected',
        'Markdown pipe table; **HTML `<table>`** when the table has merged cells',
    ),
    (
        32, 'table_cell', 'projected',
        "The cell's children, rendered inline (pipe path) · **structure-preserving HTML** (merged/`<td>` path)",
    ),
    (
        33, 'view', 'full',
        'Renders its children (each rendered by its own handler); adds no markup of its own',
    ),
    (
        34, 'quote_container', 'full',
        'Renders children, prefixes every line with `> `',
    ),
    (
        35, 'task', 'not-handled',
        '(warns, dropped)',
    ),
    (
        36, 'okr', 'not-handled',
        '(warns, dropped)',
    ),
    (
        37, 'okr_objective', 'not-handled',
        '(warns, dropped)',
    ),
    (
        38, 'okr_key_result', 'not-handled',
        '(warns, dropped)',
    ),
    (
        39, 'okr_progress', 'not-handled',
        '(warns, dropped)',
    ),
    (
        40, 'add_ons', 'projected',
        '```` ```mermaid\\n{source}\\n``` ```` for the Mermaid component; otherwise `[Unsupported Add-On block: {id}]\\n`',
    ),
    (
        41, 'jira_issue', 'not-handled',
        '(warns, dropped)',
    ),
    (
        42, 'wiki_catalog', 'not-handled',
        '(warns, dropped)',
    ),
    (
        43, 'board', 'out-of-band',
        '`![Whiteboard]({token})\\n`',
    ),
    (
        44, 'agenda', 'full',
        '(transparent — emits its children)',
    ),
    (
        45, 'agenda_item', 'full',
        '(transparent — emits its children)',
    ),
    (
        46, 'agenda_item_title', 'full',
        "The title's own inline `elements`, then `\\n`",
    ),
    (
        47, 'agenda_item_content', 'full',
        '(transparent — emits its children)',
    ),
    (
        48, 'link_preview', 'not-handled',
        '(warns, dropped)',
    ),
    (
        49, 'source_synced', 'full',
        "The block's own inline `elements`, then **recurses into child blocks**",
    ),
    (
        50, 'reference_synced', 'reference-only',
        '`> 🔗 **Synced content** referenced from document `{source_document_id}` (block `{source_block_id}`) — not fetched. …\\n`',
    ),
    (
        51, 'sub_page_list', 'not-handled',
        '(warns, dropped)',
    ),
    (
        52, 'ai_template', 'not-handled',
        '(warns, dropped)',
    ),
    (
        53, 'reference_base', 'reference-only',
        "`> 📊 **Embedded Base — named view** (reference_base) — not fetched. token: `{token}`, view: `{view_id}`. …\\n` (default) · the referenced table's GFM table (opt-in deep-read)",
    ),
    (
        999, 'undefined', 'not-handled',
        '(warns, dropped)',
    ),
)
