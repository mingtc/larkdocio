# larkdocio — the shipped consumer guide

> This guide ships **inside the wheel** (`larkdocio/GUIDE.md`). Read it at runtime with
> `larkdocio.guide()` — which returns this document's **section index**, and
> `larkdocio.guide(full=True)` returns this text in full — so an agent or consumer always has
> the canonical usage in hand without a network round-trip. Its capability matrix is
> **distilled from `larkdocio.capabilities()`** and **drift-guarded** against it
> (`tests/test_guide.py`, in the source repository): every operation, flag, and safety contract named below exists
> in `capabilities()`, and every capability surface has a section here.
>
> Four more documents written for you ship in the wheel beside this one, each with its own
> accessor: `larkdocio.lark_setup()` (the Lark-application walkthrough — the app, its scopes
> and its reach, which is where you start if nothing works yet),
> `larkdocio.writer_brief()` (the writer's long-form dialect brief),
> `larkdocio.release_notes()` (what changed that affects you — read before you re-pin) and
> `larkdocio.changelog()` (the project's changelog). `capabilities(full=True)["docs"]` lists all
> five. (A sixth, `blocks/BLOCK_TYPES.md`, also ships: it is the handler-**authoring** guide
> for contributors and deliberately has no accessor.) See
> [Reading the shipped documents programmatically](#reading-the-shipped-documents-programmatically).
>
> **You do not have to hold this whole document, and by default you do not.** `guide()` with no
> argument returns the **index** — every `##` and `###` heading, named after the failure its
> section cures, each row spelled as the call that fetches it. Every heading is
> **individually addressable** — `guide(section="recipe-the-base-write-handshake")` returns that
> one recipe and nothing else, and `guide_sections()` is the same index as data (it also rides
> `capabilities(full=True)["docs"]["guide()"]["sections"]`). Ask for a `##` name and you get its `###`
> children with it. That is the intended way for an agent to read this file: read the index,
> then fetch the one section. `guide(full=True)` returns the whole document when you really do
> want all of it. Full detail — what comes back, how a slug is derived, what a
> wrong name answers — in [Reading ONE section of this guide](#reading-one-section-of-this-guide).

larkdocio is a **Python toolkit for Lark (Feishu) documents** — read *and* write, across
every surface it reaches. It is a hardened **docx / wiki → Markdown reader** (with its
comments), a **Sheets values → Markdown reader**, a **Base reader** with **record writes** and
**schema writes**, a **Drive folder reader** and its **write legs** (named versions, access
grants, file uploads, folder creation), a **contacts** lookup, and a **plan-gated writeback apply-engine** for
docx and Sheets. The authoritative list is not this sentence: it is
`capabilities(full=True)["surfaces"]`, which this paragraph is a projection of and a drift guard holds
it to. Pure Python (stdlib + `lark-oapi` + `click` + `python-dotenv` + `markdown-it-py`); no
Node, no web tooling.

---

## Choose your level — the tree, or the Markdown projection

**Read this first if you are about to do something on someone's behalf.** larkdocio hands
you the same document at two levels, and picking the wrong one is the most expensive mistake
available here: the change refuses for a reason that looks like nonsense, or it lands in the
wrong place, and the person you are helping has no way to tell you why. Two terms carry the
whole model, and this section uses only these two:

- **the tree** — the document's real structure, exactly as Lark stores it: one entry per
  block, with everything preserved (each block's own id, the review anchors on it, its
  colors, its true heading level).
- **the Markdown projection** — a flattened text rendering of that same document, for a
  person to read. It **drops detail by design**, because Markdown has no form for most of it.

**The tree is the source of truth. The Markdown projection is optional.** A read hands you
whichever of the two you ask for. And **writes never work at the Markdown level** at all: a
document write points at a block *on the tree*; a spreadsheet write points at a cell by its
A1 range. Markdown enters this library at **six** call sites —
`parse_docx_content` (a document's projection), `project_block_ids` (the same projection with
each block's id beside it, for a write-back), `render_spreadsheet` (a spreadsheet's
projection), `render_base` (a Base's projection, callable on a Base you already hold),
`render_folder` (a whole folder's, assembled into one document) and `compose` (an optional
front-end for content you are *authoring*). Two further names are **composites** of a read plus one of
those six rather than call sites of their own: `read_spreadsheet_markdown` and
`read_base_markdown` each do the read, then produce the projection with `render_spreadsheet`
and `render_base` respectively. Call none of them and you can go from
reading a document to changing it **without producing a byte of Markdown**; the two "no
Markdown anywhere" recipes below do exactly that, end to end, for a document and for a
spreadsheet.

### Which level does this ask need?

Read the left column as the words your user actually used.

| The ask, in your user's words | The level | The call | Worked recipe | Why that level |
|---|---|---|---|---|
| "show me what this says" / "summarize it" | the Markdown projection | `parse_docx_content` · `read_spreadsheet_markdown` · `render_spreadsheet` | § "Recipe: download a docx to Markdown" · § "Recipe: read a sheet to Markdown" | A person is going to read it, and the projection *is* the reading form. |
| "pull the figures out into my own tool" | the tree · the values objects | `parse_docx_tree` · `read_used_range` | § "Recipe: change a document at the object level — no Markdown anywhere" · § "Recipe: change a spreadsheet at the object level — no Markdown anywhere" | Structured data comes out of structure. Text you then have to re-parse is a step backwards, and it has already lost the ids. |
| "find where it says X and change it" | the tree, anchored | `EditRequest` · `SubSpanEditRequest` · `AnchorById` | § "Recipe: the docx write handshake" · § "Recipe: edit part of a paragraph (a sub-span edit)" | Replacing a whole paragraph is an `EditRequest`; when the paragraph carries styling you must keep, replace only the words with a `SubSpanEditRequest`. |
| "add a new section for me" | author in Markdown, anchor on the tree | `compose` · `compose_insert` · `InsertRequest` | § "Recipe: author a Markdown fragment into a document" | Typing new content as Markdown is a convenience for *you*; where it lands is still decided on the tree. |
| "change these spreadsheet values" / "add a total" | the spreadsheet's own typed requests | `ValueWriteRequest` · `FormulaWriteRequest` | § "Recipe: the sheets write handshake" · § "Recipe: write a live formula into a sheet" | A cell is a value at a coordinate. There is no text form to route it through, and Markdown is never involved. |
| "check the change landed the way I meant" | compare content, not text | `compose` | § "Recipe: verify what you authored — compose-equivalence, not string equality" | Two projections of the same content can differ harmlessly, so comparing them as strings reports changes nobody made. |
| "what did reviewers comment, and where?" | the tree's review anchors | `comments` · `for_node` | § "Recipe: read the comments on a document" | Review anchors live on the tree; the projection drops them, so the text has nothing to look them up by. |
| "@mention Ada in that cell" | ids, not text — and **the input is an EMAIL**, not a name | `resolve_colleague` (email) · `encode_mention`; `resolve_user` (name) only where the directory reaches | § "Recipe: author a sheet cell that @mentions a teammate" | A mention is an **id** in the payload, never a name in a string, so you resolve to exactly one `open_id` before you author anything and a lookup that does not resolve to exactly one person is a refusal you handle, not a guess. Which verb: **a name is not a usable address here.** The directory search behind `resolve_user` was **measured**, on **one tenant on one day**, to return at most the account owner — so reach for `resolve_colleague(email=…)`, whose endpoint family is different and did answer for another user. Another tenant's contacts data range may differ; that is unmeasured, not refuted. |
| "read that Base for me" / "get its rows into my tool" | the Base objects · then, optionally, the Markdown projection | `read_base` · `read_base_markdown` | § "Recipe: read a Base to Markdown" | Same split, one level down: `read_base` hands back the tables with their field specs, record ids and rendered cells, and `read_base_markdown` is that read plus the reading form. A cell whose value no read route returns says so with a marker rather than a blank. To change a Base, the level is its own objects again, never the Markdown: **record writes** (rows) go through § "Recipe: the Base write handshake" and **schema writes** (tables, columns, views, the Base itself) through § "Recipe: create, rename and copy a Base (the structural handshake)". |
| "read everything in this folder" | the structured result · then, optionally, one Markdown document | `read_folder` · `render_folder` | § "Recipe: read every document in a folder" | The same split, one rung up: `read_folder` returns a structured result you iterate (each child read or disclosed, `accounted()` proving nothing was dropped), and `render_folder` assembles that into one Markdown document. A child it cannot read is disclosed by name rather than dropped. The folder read itself writes nothing; Drive's write legs (named versions, access grants, uploads, folder creation) are separate calls with their own recipes. |

Every read surface states its own level model in the registry too —
`capabilities(full=True)["surfaces"]["docx-read"]["levels"]` names that surface's full-fidelity read
and its projection in machine-readable form (and says so when a surface has only one of the
two), so this table and the code cannot drift apart.

### The tree's own types — which node is a heading, at what level

You do not have to guess at the tree's shape. Every block is a **typed node**, each node class
documents its own fields, and `help(larkdocio.model.nodes)` is that field-level reference —
which node carries text, which carries children, and what each field means. Reading a document
takes two shipped functions and the node classes; nothing here needs to be hand-rolled.

- **`walk(root)`** — every block, outermost first. It follows **all three** container shapes:
  `children`, a table's **`cells`**, and a grid's **`columns`**. This matters more than it
  sounds: a walk that follows only `children` stops at every table, and a table is usually
  where a document keeps its figures — so such a walk reports a costs table as *empty* rather
  than as unreachable, with no error and no warning.
- **`plain_text(node)`** — that block's own words (or one run's), with `@mentions` **included**
  as the raw `@ou_…` token. What "own" means, and what a container reports, is stated right
  beside the branch it matters for, below — not paraphrased twice.

```python
from larkdocio.model import (
    HeadingNode, PageNode, TableCellNode, TableNode, Text, TextNode, plain_text, walk,
)

# Stand-in for the tree `parse_docx_tree` returns — the recipes below read a real document.
# A table is included on purpose: it is the branch a hand-built demo usually skips, and
# skipping it is exactly how this recipe once taught the wrong answer.
root = PageNode(title=[Text("Q3 Proposal")], children=[
    HeadingNode(level=2, content=[Text("Business Case")]),
    TextNode(content=[Text("Revenue grew 12.4% in Q3.")]),
    TableNode(cells=[
        TableCellNode(children=[TextNode(content=[Text("Q3 revenue: 12.4%")])]),
    ]),
])

for node in walk(root):
    if isinstance(node, HeadingNode):        # WHICH node is a heading…
        print("heading", node.level, plain_text(node))   # …and at WHAT level (Lark stores 1-9)
    elif isinstance(node, TableNode):        # a table is a pure CONTAINER — see the rule below
        print("table", plain_text(node) or "(own text is empty on purpose — see below)")
    elif isinstance(node, TableCellNode):    # so is a cell; its words live in the child `walk`
        print("cell", plain_text(node) or "(own text is empty on purpose — see below)")
    else:
        print(type(node).__name__, plain_text(node))
```

**`plain_text` returns a node's OWN text, never its children's — that rule, projected from its
own docstring so the two cannot say something different:** *"Never its child blocks — a
heading's text is its heading line, not the section beneath it — so a pure container (a table,
a table cell, a grid, a callout) reports `""`."* That is why the printed lines above for
`table` and `cell` carry an explanatory note instead of a bare blank line — the emptiness is
the documented contract, not a defect in the tree above — and why the actual words,
`"Q3 revenue: 12.4%"`, print on the very next line: `walk` already reached the cell's own
child, and *that* node has a field `plain_text` reads.

`isinstance` against the node class is the answer to every "what is this block" question:
`HeadingNode` carries its true `level` (1–9, where the Markdown projection stops at 6),
`TableNode` holds its cells, `TextNode` a paragraph, and each of the others is named for what
it is. A `getattr` on a guessed attribute name is what silently returns nothing.

Every node class the model ships answers the same two questions, generated below rather than
hand-kept — a class the model gains or loses moves this table on its own, and a class
answering **no to both** (it carries neither a text field `plain_text` reads nor a container
field `walk` descends into) is visible as such rather than folded into either bucket:

<!-- BEGIN NODE-CLASS-INDEX (generated
     regenerate with:  python -c "from larkdocio.model.node_docs import node_class_markdown as m; print(m())"  -->

Two separate questions per class, never folded into one container/own-text label — a class can answer **no to both** (it carries neither a text field `plain_text` reads nor a container field `walk` descends into), and a binary split would misname it a container:

| Node class | `plain_text` returns its own text? | `walk` descends into it? |
|---|---|---|
| `AddOnsNode` | no | no |
| `AgendaItemContentNode` | no | yes |
| `AgendaItemNode` | no | yes |
| `AgendaItemTitleNode` | yes | no |
| `AgendaNode` | no | yes |
| `BitableNode` | no | no |
| `BoardNode` | no | no |
| `BulletListItemNode` | yes | yes |
| `CalloutNode` | no | yes |
| `CodeNode` | yes | no |
| `DividerNode` | no | no |
| `DocumentNode` | no | yes |
| `EquationBlockNode` | yes | no |
| `FileNode` | no | no |
| `GridColumnNode` | no | no |
| `GridNode` | no | yes |
| `HeadingNode` | yes | yes |
| `IframeNode` | yes | no |
| `ImageNode` | yes | no |
| `OrderedListItemNode` | yes | yes |
| `PageNode` | yes | yes |
| `QuoteContainerNode` | no | yes |
| `QuoteNode` | yes | no |
| `RawBlock` | yes | no |
| `ReferenceBaseNode` | no | no |
| `ReferenceSyncedNode` | no | no |
| `SheetNode` | no | no |
| `SourceSyncedNode` | yes | yes |
| `TableCellNode` | no | yes |
| `TableNode` | no | yes |
| `TextNode` | yes | no |
| `TodoListItemNode` | yes | yes |
| `UnknownBlockNode` | no | yes |
| `ViewNode` | no | yes |

<!-- END NODE-CLASS-INDEX -->

**That table answers `plain_text`'s question, and it does not predict a sub-span refusal** —
they are two different questions about the same block, and the answers part company on four of
the classes above. `plain_text` reads a block's own text wherever the block keeps it: the
`content` runs first, and failing those a `title`, a `caption`, a `url` or a `markup` field. A
**sub-span** edit reaches only the `content` text runs. So a block whose own text lives on one
of those other fields reads **yes** in the column above and yields the **empty string** on the
sub-span basis — and a sub-span edit against it refuses rather than editing nothing. Read that
column as *"can I read this block's text"*, never as *"can I edit part of it"*; which reduction
answers which question is the ladder further down this section.

**When you plan to write the document back: `project_block_ids(root)`.** Markdown from a read
says everything about a document except *which block said it*, which is fine to read and
useless to edit. The projection renders the same tree with one single-line
`<!-- lark:block:<id> -->` marker before each block, and returns the identifiers it emitted
alongside the text (`.markdown` / `.block_ids`, and `.to_dict()` for JSON). It is **opt-in and
strictly additive**: a read that does not ask for it is byte-identical to before, and
`strip_block_id_markers(text, ids)` gives the plain Markdown back exactly. Two things to know
before you build on it. It renders with **literal text escaped**, so that a document whose own
prose is marker-shaped cannot emit something indistinguishable from a real marker — which means
you compare block text through `unescape_literals`, the exact inverse, and never against the
raw projected line. And the strip takes the emitted identifiers **because** it must: removing
every marker-shaped line instead would delete a consumer's own writing about markers. Blocks
that render nothing, and blocks inside a table cell (where a row is one line), carry no marker;
a table is marked at the table block. See `help(larkdocio.model.projection)`.

**Not every marked block is one you may edit.** A block whose Markdown the authoring dialect
cannot compile back — an image, a synced block, an embed, a whiteboard, a type this release has
never heard of — and a block the reader renders in a *different shape* than its own — a table
(a pipe grid, or HTML when merged), a mermaid add-on (a fenced source listing) — carries the
opaque form of the marker instead: `<!-- lark:block:<id> opaque=<kind> -->`, and comes back in
`.opaque_block_ids` as well as `.block_ids`. The content still shows, so the projection stays
readable; the marker is what says an edit to it cannot mean anything. **The contract on such a
block is conservation: it is not edited, not deleted, and not re-created — even if the edited
Markdown omits it entirely.** Destruction is never inferred from an absence. A table is opaque
as a whole and its cells carry no markers of their own; the supported route for changing a cell
is the **cell-patch** path in `larkdocio.write`, which addresses a cell directly. Which types
fall on which side is derived from the handler registry, the creatable set and the per-type
read-lossiness rather than listed by hand — ask `capabilities(full=True)["surfaces"]["docx-read"]
["block_projection_support"]` for the per-type answer and the contract in full.

**One name that looks like a third helper and is not:** `larkdocio.write.block_plain_text`
answers a *different* question — "what text in this block could a person literally quote back"
— because it backs anchor matching for a write, so it leaves a mention out **on purpose** (a
raw id is not something anyone quotes). Use `plain_text` to **read** a document and
`block_plain_text` only when you are building an anchor quote; on a block holding a mention the
two deliberately return different strings.

**Two reductions are all you can call; the library performs five.** Five different questions get
asked of one block, and on a styled paragraph, a mention or a table cell the five answers
genuinely differ — which is why they are five functions and not one. Two are shipped names; the
other three are internal and are named below by the question they answer, because the question
is the contract and the function is not. Knowing which is which is how you tell what a plan
entry or a refusal is quoting at you:

| The question it answers | Who answers it |
|---|---|
| A block's own words, `@mentions` **included** — the **reading** basis | **`plain_text`** — the field-level reference is `help(larkdocio.model.plain_text)` |
| What a person could literally **quote back** — the **anchor-matching** basis, mentions left out on purpose | **`block_plain_text`** — the field-level reference is `help(larkdocio.write.block_plain_text)` |
| A **table cell's** own descendant text — the basis a **whole-cell patch** quotes as its `before` | internal; you meet it as that entry's `before` |
| The **sub-span splitting basis** — the **`content` text runs only**, and nothing else | internal; you meet it as a `span-not-splittable` or `not-found` refusal |
| What the apply engine will **read back live**, immediately before it writes — the **staleness-precondition** basis | internal; you meet it as a stale-target refusal |

Rows three to five are not callable, so there is nothing to import and no name to remember —
but each one *decides* something you can see from outside. The cell row is the `before` a
whole-cell patch shows you. The sub-span row is why a sub-span edit can refuse on a block
`plain_text` reads out loud quite happily. And the last row is why a plan built against a stale
read refuses at write time instead of overwriting a change somebody else made.

### Symptoms you picked the wrong level

Four things you can *see*, after it has already gone wrong. Each is the same mistake wearing
a different coat, and each has a mechanical fix.

| What you are seeing | What actually happened | The fix |
|---|---|---|
| You wrote something, read the document back to check it, and **every list shows a difference** | You are comparing two Markdown projections as **strings**. The projection normalizes a list as it flattens (a tight list comes back with a blank line between items), so the text differs while the content is identical. | Compare the content, not the text: `compose(authored) == compose(read_back)`. See § "Recipe: verify what you authored — compose-equivalence, not string equality". |
| An anchor quote keeps refusing `not-found` **though the text is plainly there** | You quoted the **projection**, not the block. The projection escapes and normalizes as it flattens, so its characters are not the block's characters. | Take the quote off the tree — better, take the block's own `block_id` off the tree and anchor with `AnchorById`. |
| Colors, reviewers' remarks, or a spreadsheet's merged regions look **missing** | They are on the tree (and, for a spreadsheet, on each tab's own `merges`). The projection drops them by design: it is a reading form, not a record. | Read them where they live — `parse_docx_tree` for a document, the `SheetTab` objects for a spreadsheet. |
| You are working out how to **round-trip Markdown** to make a write happen | Nothing here ever needs that. Every write targets a block on the tree or a cell in a spreadsheet; Markdown is only ever a front-end for content you are authoring. | Build the typed request and anchor it — by id for a document, by A1 range for a spreadsheet. The two "no Markdown anywhere" recipes are the whole pattern. |

### What the projection drops — three directions, stated separately

**1. The tree → the Markdown projection drops named things.** Each of these is read into the
tree and then deliberately left out of the text, because Markdown has no form for it: a
block's own `block_id`; the review anchors on a block **and**, separately, the review anchors
on a run of words inside it (`comment_ids` at both granularities); a run's `text_color` and
`background_color`; an embedded component's `iframe_type`; a heading level past 6 (Lark
stores 1–9 and the projection's marker stops at `###### `, so a level-7 heading reads back as
a level-6 one); and a spreadsheet's merge geometry — a covered cell renders **blank**,
indistinguishable from a genuinely empty one, and the geometry survives only on each tab's
own `merges`.

**2. The Markdown projection → typed requests is dialect-bound, so authored Markdown
round-trips.** `compose` reads exactly **the Markdown this library's own reader emits** —
CommonMark plus pipe tables and `~~strike~~`, with the reader's escaping rules read in
reverse — so anything the reader wrote, `compose` turns back into the same content. That is
the one direction Markdown is safe in, and it is why authoring in Markdown is a supported
front-end rather than a hazard. **Stated exactly:** the property holds over the **creatable**
set, and the lossiness table in § "Authoring from Markdown" is the exception list — a
construct outside that set refuses **by name** — including, if one ever exists again, the
case where the text came from us: a block the reader *projects* into Markdown while having no
creatable form for it yet. **That set is empty as this release ships, and it is derivable rather than asserted** — `capabilities(full=True)["surfaces"]["docx-read"]["block_projection_support"]` states per block type what the reader projects, against the
creatable set the authoring dialect declares; do not take the emptiness on trust, read it.
The last such block was the diagram
add-on behind a ```` ```mermaid ```` fence, and it became authorable, so that fence now composes
like any other section — which is precisely what makes this claim hold for a document
containing a diagram instead of merely *almost* holding. Nothing is ever silently approximated
in either direction.

**3. You cannot get back out of the projection what it dropped — which is why targeting is
tree-level.** Nothing in the text says which block a line came from, who commented on it, or
whether a blank cell is covered by a merge. So an anchor computed from the text is a *guess*
about the document, while an anchor taken off the tree is the document's own answer. That is
the whole reason a write is planned against the tree and never against the text.

**Which block types survive the read — ask the library, per type.** The three directions
above are the *shape* of the loss; the **per-type** answer is projected, so you never have to
guess it for the document in front of you.
`capabilities(full=True)["surfaces"]["docx-read"]["block_read_support"]` gives one row per docx block
type answering **all three** questions — is it `handled`, what does it `emit`, and what is its
`lossiness` (a state, explained in the same payload's own `lossiness_vocabulary`, because
"lossy" means something different for a heading that comes back a level shallower than for a
whiteboard whose pixels are a separate file), plus `unlisted_type` for a block type Lark adds
after this release. See § "Capability matrix" for the call.

**An embedded Base inside a docx — and why a doc-owned one is a different animal.** A docx can
embed a Base, and by default the reader emits a traceable placeholder where it sits, for both
block types that carry one: `bitable` (18) and `reference_base` (53, the same Base switched to
a named view). Both can be read **inline** instead, opt-in and off by default — `larkdocio download …
--deep-read-bases` on the command line, or `Parser(deep_read_bases=True, base_client=…)` in
code — which renders **only the referenced table** as a headed GFM table. Off, the reader makes **zero** Base API calls and the Markdown is
byte-identical to before; on, any failure (a stale token, a table that no longer exists, a
missing scope, a network error) **degrades back to the placeholder** rather than failing your
download. It is the embedded-sheet deep read (`deep_read_sheets`, block type 30) replayed for
Base, and the two behave the same way on purpose.

What is **not** obvious: when Lark auto-provisions a Base for an embed block, that Base is
**doc-owned**, and it is a distinct object class from one you created yourself. It has **no
`time_zone`** at all (dates render in the assumed default zone, UTC, and the read discloses that
it assumed it — `date_zone_assumed` / `date_zone_disclosure`), a **blank** drive
`title` and `sec_label_name` (the tenant **security level** — readable, not settable; see §
"The document's SECURITY LEVEL" below), and it is **not an independently deletable drive file** — a
`DELETE /drive/v1/files` against it answers `1061003`, because it dies with its parent
document. Nor can such an embed be pointed at a Base you already have: Lark's docx API accepts
a type-18 create with `{"view_type": 1}` and refuses `1770001` if you name a token. So treat a
doc-owned embedded Base as **part of its document**, not as a Base you can manage on its own.

---

## The two-level design — author in Markdown, target by tree

Three sentences carry the whole writer's mental model. Read them before the API:

> **Author in Markdown. Target by tree. Keep requests, not plans.**

**Author in Markdown.** `compose()` is a **Markdown front-end onto the typed tree** — it
compiles a fragment into exactly the typed `NewBlock` content you could have hand-built, and
nothing else. It is a *compiler*, not a mode: Markdown is an **authoring convenience** for
content you are creating, and the dialect is deliberately the **reader's own output**, so
anything you can read you can compose back — over the **creatable** set, with the lossiness
table in § "Authoring from Markdown" as the exception list; a construct outside it is refused
**by name** rather than composed, never silently approximated. The reader's own ```` ```mermaid ````
diagram fence used to be one of those exceptions and no longer is: a diagram is creatable
(`NewBlock.mermaid`), so it composes. `compose()` **produces requests, never writes**.

**Target by tree.** Anchors and targets are **tree-level** — a block, a `block_id`, a table
cell — never Markdown text. **The engine never works at the Markdown level**: it resolves
against the node tree `parse_docx_tree` hands you and it patches *blocks*. There is no
"Markdown mode" to be in, and **a pure-tree consumer can ignore `compose` entirely** — build
`NewBlock` values directly, anchor by id, and the whole authoring surface still applies.
(That is also why the read call the writer needs is `parse_docx_tree`, not
`parse_docx_content`: Markdown is not something the writer can anchor on.)

**Keep requests, not plans.** Requests (`EditRequest` / `InsertRequest` / `DeleteRequest` /
`SubSpanEditRequest`) are **portable, inert values**: each is frozen and round-trips through
`to_dict()` / `from_dict()`, so a queue of pending edits can be parked in a database, a file,
or a conversation's own state and reloaded later. A `Plan` is the opposite by design — it is
**not** portable, and that is the point. So an agent working across turns keeps the
**requests**, and builds the plan **fresh** at commit time. The § "Recipe: accumulate edits
across turns" recipe below is the worked pattern.

**Why the asymmetry is deliberate — the trust property.** A `Plan` **cannot be reconstructed
from a snapshot**: it serializes for an approval UX (`to_dict` / `to_json`) but ships **no**
`from_dict`, and its constructor refuses every caller but `dry_run`. And `apply()`
**re-validates live immediately before writing** — the anchored block is re-read per entry
(`STALE_ANCHOR`, always on), and the document's own revision once per batch when that guard is
armed (`STALE_DOCUMENT`). Put
those together and a **stale conversational account of "what we planned" can never reach
`apply()`** — **only a freshly computed, freshly validated `Plan` can**. That is claimed as a
**feature**: an agent that has been talking for twenty turns cannot talk a write into
existence; it has to go and look at the document again first.

---

## Install (vendored wheel — the locked distribution model)

Consumers **vendor a built wheel** and pin a local-file requirement — no submodules, no
pip-from-git, no copied source. The reference flow is `consumers/update_larkdocio.sh`,
which builds/refreshes the wheel into `./vendor/` **and drops four of the shipped documents
next to it as a convenience** — this guide (`vendor/larkdocio-GUIDE.md`), the project's
changelog (`vendor/larkdocio-CHANGELOG.md`), the consumer-facing release notes
(`vendor/larkdocio-RELEASE_NOTES.md`), and the Lark-application walkthrough
(`vendor/larkdocio-LARK_SETUP.md`) — then prints the requirement line to pin. Those
`vendor/` copies are extras: all four documents ship **inside** the wheel too, so
`larkdocio.guide(full=True)`, `larkdocio.changelog()`, `larkdocio.release_notes()` and
`larkdocio.lark_setup()` return them whatever way you installed the package. **The vendor
drop is four; the wheel carries five.** The fifth is the writer's long-form brief,
`larkdocio.writer_brief()`, which the drop does not copy out — read it from the wheel like
the others. `capabilities(full=True)["docs"]` is the authoritative list of the five.

```bash
# from the consumer repo root
scripts/update_larkdocio.sh              # build + vendor the LATEST tag (+ refresh the docs)
scripts/update_larkdocio.sh v1.53.0      # a specific tag (every release from 1.53.0 on is one)
scripts/update_larkdocio.sh --check      # report-only: is a newer tag available?
# pin the printed line, e.g.:  larkdocio @ file:./vendor/larkdocio-1.53.0-py3-none-any.whl
```

**Before you re-pin, read the release notes — `larkdocio.release_notes()`.** That call
returns `RELEASE_NOTES.md` straight out of the installed wheel, so it works from a plain
`pip install` as well as a vendored one. The wheel's copy is a window of the newest releases;
the `vendor/larkdocio-RELEASE_NOTES.md` drop, when you have it, is the full history. It is the filtered view of what changed *that affects you* —
public symbols and CLI flags, observable behavior changes, new or renamed refusals,
credential and scope requirements, **every dependency add and pin move**, and known
limitations — release by release. `larkdocio.changelog()` returns `CHANGELOG.md`, the project's
changelog: one entry per release, and a pointer to these notes for earlier versions.
`--check` prints the release-notes section headers for the versions between what you have
vendored and the latest tag, so it answers "should I update?" with the reason.

A downstream clone of a consumer needs **no reachable git host** — it reproduces the env
from the already-vendored wheel (PyPI only, for transitive deps).

---

## Credentials & `.env` setup — the READ / WRITE app split

larkdocio uses **least-privilege read/write credential separation**: a **READ app** for
everything that reads, and a **separate, narrowly-scoped WRITE app** for the writeback
engine. **The read path never consults write creds, and the write path never falls back
to read creds.** Put them in a **gitignored `.env`** (copy `.env.example`, in the source repository);
`.env` is **never** committed.

**The two pairs MAY point at the same app — the split is about ROUTES, not necessarily two
registrations.** If one app of yours legitimately holds both scope sets, put its credentials in
both pairs and everything here works: the engine never compares them, and nothing asks whether
they are one app or two. What the split buys you is that **the read path resolves only the READ
pair and the write path only the WRITE pair, with no fallback either way** — so the day you do
provision a narrowly-scoped write app, you change two lines of `.env` and no code. Two apps
remains the shape to aim for (a read path that cannot write is a property you can only get from
a separate registration, never from one app wearing both hats); one app is a configuration you
are allowed to start from, and neither pair may ever be left unset in the hope that the other
covers it.

```bash
# ── READ app (the reader — the shipped surface) ───────────────────────────────
LARK_READ_APP_ID=cli_xxx
LARK_READ_APP_SECRET=xxx
#   WHICH SCOPES: see "Permissions — what to ask for" below. That table is generated from
#   the library's own permission registry, so it cannot fall behind the code; this block
#   deliberately does not repeat the list.
# Legacy fallback (used whenever the READ pair above is not FULLY set — resolution is
#   pair-wise, so a lone LARK_READ_APP_ID with no matching secret falls back to here):
# LARK_APP_ID= / LARK_APP_SECRET=              (still accepted; `larkdocio config`
#                                               writes the READ pair above, and only
#                                               updates these in place — with a notice —
#                                               on a .env that already uses them)

# ── WRITE pair (the writeback engine — separate credentials; one app or two) ───
LARK_WRITE_APP_ID=cli_yyy
LARK_WRITE_APP_SECRET=yyy
#   WHICH SCOPES: see "Permissions — what to ask for" below. The spreadsheet write engine
#   runs on this same pair; what it needs beyond the document scope is in that table too.
#   NEVER consulted by the read path. WHERE you may write is NOT restricted by the engine:
#   the disposables rule below is this project's own test-suite policy, not an engine
#   restriction — you may write to any document your WRITE app can reach.
```

**Scopes take effect only after the app version is RELEASED** (and admin-approved where
required). For reads, the READ app must also be added to each target document (or be a
member of the wiki space).

### Permissions — what to ask for

Every scope requirement below is **generated from the library's own permission registry**
(`larkdocio.permissions`, which every call site's requirement is derived from), so it cannot
fall behind the code. The same answer is machine-readable per call in
`larkdocio.capabilities(full=True)` under each operation's `permissions` key — and the complete
list of a surface's calls is `capabilities(surface=<id>)["operations"]`, **one key holding every
one of them**, each row carrying its own `kind`: `operation` (a kind the surface's engine
dispatches), `leg` (an API-using call that is not one of those) or `lifecycle` (a call that
creates or destroys the file itself). There is no sibling key for a verb to hide under, so
reading the one obvious key cannot miss `put_image_in_document`, `create_document` or
`read_workbook`. The scope prose each row rests on is carried once, at the top level, under
`scope_evidence` and `unknown_requirements`.

<!-- BEGIN PERMISSIONS (generated
     regenerate with:  python -c "from larkdocio.permissions import consumer_permissions_markdown as m; print(m())"  -->

**What to ask for — one row per surface and scope, so a row is one thing you ask for.** *Must hold* means the surface does not work without it. *Optional* means the surface still works and something specific is lost. What each scope costs is written once, in the per-scope list below the tables, so no cell here carries a paragraph.

**THIS TABLE ANSWERS THE per-SURFACE QUESTION** — *what does this surface stop doing without the scope*. The table after it answers the per-OPERATION one — *what must a grant include for one call to do its whole job* — and they are different questions, so the same scope can be `optional` here and still be listed there. Neither table overrides the other; read the one whose question is yours, and read the per-scope list under *What you lose without each one* for what any one of them actually costs. In code the per-operation answer is `larkdocio.preflight.requirements_for_operations([...])`, and it derives from this same registry.

| Surface | Credential pair | Scope | Must hold? | How firmly established |
|---------|-----------------|-------|------------|------------------------|
| `docx-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `docx:document:readonly` | must hold | grant-verified |
| `docx-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `contact:contact.base:readonly` | optional | grant-verified |
| `docx-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `contact:user.base:readonly` | optional | grant-verified |
| `docx-comments-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `docx:document:readonly` | must hold | grant-verified |
| `contacts-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `directory:employee:search` | must hold | grant-verified |
| `drive-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | — | — | no scope observed demanded |
| `drive-versions-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | `docx:document` | must hold | grant-verified |
| `drive-access-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | — | — | no scope observed demanded |
| `drive-files-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | — | — | no scope observed demanded |
| `drive-folders-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | — | — | no scope observed demanded |
| `sheets-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | — | — | no scope observed demanded |
| `sheets-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `drive:export` | optional | grant-verified |
| `sheets-embedded-deep-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `docx:document:readonly` | must hold | grant-verified |
| `sheets-embedded-deep-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `drive:export` | optional | grant-verified |
| `base-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `bitable:app:readonly` | must hold | grant-verified |
| `base-comments-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `docx:document:readonly` | must hold | grant-verified |
| `base-embedded-deep-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `bitable:app:readonly` | must hold | grant-verified |
| `base-embedded-deep-read` | READ app · `LARK_READ_APP_ID` · `LARK_READ_APP_SECRET` | `docx:document:readonly` | must hold | grant-verified |
| `base-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | `bitable:app` | must hold | grant-verified |
| `base-schema-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | `bitable:app` | must hold | grant-verified |
| `docx-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | `docx:document` | must hold | grant-verified |
| `sheets-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | — | — | no scope observed demanded |
| `sheets-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | `contact:contact.base:readonly` | optional | grant-verified |
| `sheets-write` | WRITE app · `LARK_WRITE_APP_ID` · `LARK_WRITE_APP_SECRET` | `contact:user.base:readonly` | optional | grant-verified |

**Per call, when a surface's answer is not the whole answer — THIS TABLE ANSWERS THE per-OPERATION QUESTION: what must a grant include for this call to do its whole job.** Most calls need exactly what their surface needs. These are the ones that need something extra, and they are the ones worth reading before you plan an integration. A scope listed `optional` above can appear here too, and that is not the two tables disagreeing: a caller-visible graceful degrade exists without it, which is what makes it *optional* at the surface level while still being *required* for the one operation that calls the endpoint. **What absence costs is per scope, not uniform** — for a FIELD-level grant the call even succeeds and the fields it governs come back empty — so it is written once each below, under *What you lose without each one*, and never guessed at here:

| Call | Needs | How firmly established |
|------|-------|------------------------|
| `docx-read` · `batch_get_user_names` | `contact:contact.base:readonly` | grant-verified |
| `docx-read` · `batch_get_user_names` | `contact:user.base:readonly` | grant-verified |
| `docx-read` · `download_board_image` | `board:whiteboard:node:read` | documented-unverified |
| `sheets-embedded-deep-read` · `deep_read_embedded_sheet` | `drive:export` | grant-verified |
| `sheets-read` · `create_export_task` | `drive:export` | grant-verified |
| `sheets-read` · `download_export` | `drive:export` | grant-verified |
| `sheets-read` · `export_xlsx` | `drive:export` | grant-verified |
| `sheets-read` · `poll_export_task` | `drive:export` | grant-verified |
| `sheets-read` · `read_workbook` | `drive:export` | grant-verified |
| `sheets-write` · `dry_run` | `contact:contact.base:readonly` | grant-verified |
| `sheets-write` · `dry_run` | `contact:user.base:readonly` | grant-verified |

**What you lose without each one — written once per scope, never repeated.** Read the entry for any scope a row above named; a scope required for more than one reason carries one line per reason.

- `bitable:app` (grant-verified):
    - without it no record can be created, updated or deleted
- `bitable:app:readonly` (grant-verified):
    - without it no Base can be read at all
- `board:whiteboard:node:read` (documented-unverified · a candidate, never observed demanded):
    - a CANDIDATE, not a confirmed requirement — try it if the image download is denied, and read the denial body, which names what Lark actually wants
- `contact:contact.base:readonly` (grant-verified):
    - opens the directory call — without it no display name resolves at all. What that costs depends on the caller: a document read still completes with every mention left as a raw open id, and a spreadsheet plan still builds, disclosing its mention check as unavailable rather than skipping it silently
- `contact:user.base:readonly` (grant-verified · a FIELD-level grant):
    - the FIELD-LEVEL grant — without it the lookup SUCCEEDS and every name field comes back null, which reads exactly like 'no such user'. A document read degrades to raw open ids; a spreadsheet plan discloses its mention check as unavailable
- `directory:employee:search` (grant-verified):
    - without it a name cannot be turned into an open_id at all — the call is denied outright and the lookup raises rather than reporting the person as absent. There is no degrade: this library will not enumerate the directory to approximate a name search
- `docx:document` (grant-verified):
    - without it no block can be created, patched or deleted
- `docx:document:readonly` (grant-verified):
    - without it no document can be read at all
    - the comment family needs no extra grant beyond the reader's, on any of its three file types; comment authors come back as raw ids either way
- `drive:export` (grant-verified):
    - the whole-cell style and number-format read needs it — without it that read degrades to values only and nothing else changes

**The one that does not look like a permission problem.** `contact:user.base:readonly` is a FIELD-level grant. Without it the call still succeeds and the fields it governs come back empty, which reads exactly like *"there is no such user"*. If a name will not resolve and nothing looks like an error, check this one first.

**Where the requirement is not known, this says so.** A surface listing no required scope is not a promise that none is needed — it means no scope string has ever been observed demanded for those calls, and none is guessed here. Read `larkdocio.capabilities(full=True)` for the per-call detail: each operation's `permissions`, and the top-level `unknown_requirements`, which gives that caveat's reason per endpoint.

**When a call IS denied, you are told exactly what is missing.** The denial record is on `err.denial`, and it carries the exact missing scope(s), Lark's verbatim `code`/`msg`, the console link when Lark supplies one, which credential pair the call used, and the fallback that still works where there is one. `denial.detail()` is one paragraph you can relay as-is. **Test it with `err.denial is not None`, not with the class** — that check means the same thing on every surface. Most surfaces raise `LarkPermissionError` (a `LarkAPIError` subclass, so code that already catches API errors keeps working); a leg with an error family of its own raises its own type and carries the same record — an attachment upload raises `MediaUploadError`, a Drive file upload `DriveFileUploadError`, a chunked upload `DriveFileChunkedUploadError` with the `upload_id` it left behind. Those legs tell you WHICH leg failed and WHY; taking the family away to answer the second question would have cost you the first. **A denial is never reported as an absent thing** — including the case that does not look like a permission problem at all, where the call succeeds and the fields a field-level grant governs come back empty.

**And you can ask before you start — advisory, optional, and honest about it.** `larkdocio.preflight.check_permissions(for_operations=[...])` derives what those operations need and, for the scopes a read can actually decide, checks them with one harmless call each against a deliberately nonexistent target — so nothing of yours is read, altered or created. `larkdocio.preflight.call_cost([...])` tells you how many calls that will be **before** you spend them. Every answer states HOW it knows (`probed`, `derived`, or `unknown`), and the result names its own blind spots: **a write scope cannot be proved by any read, and a field-level grant is invisible to this check** — which is exactly why it is advisory. It is never required: nothing in the library calls it, and skipping it changes nothing about how a real denial is reported.

**Read `result.ok` together with `result.blind_spots` — the boolean on its own is not an answer.** `ok` says one thing only: no probe *found* a scope missing. Where nobody has ever observed what an operation requires, the check now says so as a blind spot naming that operation, and `result.requirements` states for every operation you asked about which kind of answer you got — `known`, `unmeasured` (it calls Lark and no scope string has ever been seen demanded), `no-api-call` (it reaches Lark not at all, so it needs nothing), or `unrecognised`. Ask about **operations**, not surfaces: `check_permissions(['docx-read'])` refuses with a `LarkConfigError` naming that surface's operations, rather than answering an empty result. The whole answer is JSON — `json.dumps(result.to_dict())`.

**This library never widens, requests or escalates a scope. It only describes what a call requires and reports, verbatim, what Lark said when a call was denied — including the console link Lark hands back. Granting a scope is an action a workspace administrator takes in the Lark console.** When a call is denied, what you get back carries Lark's own code and message — which name the missing scope — so the console link in it is the fix.

<!-- END PERMISSIONS -->

**Where to find the advisory pre-check, so you do not have to search for it.** `preflight` is exported from the top level — `larkdocio.preflight.check_permissions` and `larkdocio.check_permissions` are the same function reached two ways, both listed in `larkdocio.__all__`, so `dir(larkdocio)` and `help(larkdocio)` show it — and it has a row in `larkdocio.capabilities(full=True)["entry_points"]` carrying a one-line summary and its call cost (`larkdocio.preflight.call_cost([...])` returns that number for free). It is **never required**, and nothing about it is a gate: it sits in this setup section because this is where you are asking *"have I granted the right things?"*, not because any call needs it run first.


Two things this table will not do. It will not tell you which scopes your app **holds** —
only which ones each call **needs**; and nothing in the library asks Lark for a scope, so a
missing one is always something a workspace administrator grants in the Lark console. Note
also that a scope is not the whole precondition: name resolution additionally needs the app's
**contacts data range** to cover the people being resolved, which is a console setting rather
than a scope.

### Loading `.env` from Python — nothing reads the environment until you do

The CLI takes `--env-file`; **from Python you must load the `.env` yourself.** Every
constructor and resolver that "reads credentials from the environment"
(`get_read_credentials()`, `get_write_credentials()`,
`SheetsWriteClient.from_write_credentials()`, …) reads `os.environ` — and nothing puts
your `.env` there until `init_env` runs. So **every Python recipe below opens with the same
line**, and it is load-bearing, not decoration:

**Skip it and you get a typed refusal, not a mystery.** Both credential resolvers raise
`LarkConfigError` when their pair does not resolve — the read half no longer returns an empty
`('', '')` pair for you to carry into a client constructor. Catch `LarkConfigError` if you want a
boolean instead of a raise (`try: get_read_credentials() / except LarkConfigError: ...`).

**The refusal names the pair that is IN FORCE, and on a clone with nothing configured that is
the LEGACY pair** — resolution is pair-wise, so the preferred pair is in force only when both
its variables are set and non-blank, which is exactly the case in which the getter returns
instead of raising. So the message you will actually see reads:

> Read credentials not configured: set LARK_APP_ID and LARK_APP_SECRET — the pair the read path is resolving right now. The quickest route is `larkdocio config --appId <id> --appSecret <secret>`, which writes a read pair into the .env the reader loads; .env is gitignored, so credentials live only there and never in the repository. The read and write pairs are resolved independently and neither falls back to the other, so a write-scoped app is never borrowed to satisfy a read.

Set only `LARK_READ_APP_ID` and leave its secret unset and you get the same message, naming the
same legacy pair — which is the point of naming the pair in force rather than the pair you may
have meant: it sends you to the variable something is actually reading.

```
init_env(".env")      # from larkdocio.common import init_env
```

Call it once, first, before anything else. Omit it and a write recipe fails with
`LarkConfigError: LARK_WRITE_APP_ID / LARK_WRITE_APP_SECRET …` even though your `.env` is
sitting right there.

Three things `init_env` does that are worth knowing before you call it — `init_env(None)` /
`init_env()` defaults to `<cwd>/.env`:

- **A missing file is created for you — as a commented template, not an empty file.** It
  arrives carrying the read-credential names, the guidance comments that explain them, and
  blank values for you to fill in. **Missing parent directories are created too**, so
  `init_env("config/local/.env")` makes `config/local/` on the way.
- **Pass `create=False` if you want the load without the write.** Nothing is written and no
  directory is created; a missing file then raises `LarkConfigError` naming the path it looked
  for, so you find out about it instead of getting a file you did not ask for. `create` is
  keyword-only and defaults to `True`, so calls you already have are unaffected.
- **Loading overrides variables already set in your process environment.** This is the one
  that can bite. If `LARK_READ_APP_ID` is already exported — by your shell, by CI, by a test
  harness — the value in the `.env` replaces it, and a blank value in the file replaces it
  with nothing. So point `env_path` at a file that agrees with your environment rather than
  expecting the environment to win.

### `domain=` is the Lark **API** domain, not your tenant host

Every client takes `domain=`, and it means the **API** domain — exactly one of
**`larksuite.com`** or **`feishu.cn`**. It is *not* the host in your browser's address
bar: a document at `https://your-domain.larksuite.com/docx/<token>` is still
`domain="larksuite.com"` (the tenant subdomain is irrelevant to the API endpoint). You
never have to work this out by hand — `validate_download_url(url)` returns exactly the
right value as its first element:

| URL you paste | `domain=` you must pass | `url_type` you get back |
|---------------|-------------------------|-------------------------|
| `https://your-domain.larksuite.com/docx/<token>` | `larksuite.com` | `docx` |
| `https://your-domain.larksuite.com/wiki/<token>` | `larksuite.com` | `wiki` |
| `https://your-domain.feishu.cn/docx/<token>` | `feishu.cn` | `docx` |
| `https://your-domain.larksuite.com/sheets/<token>` | `larksuite.com` | `sheets` |
| `https://your-domain.larksuite.com/base/<app_token>` | `larksuite.com` | `base` |

The second column is why this call is worth making even when you already know the token: the
third says **which surface** the URL names, so one function answers "what is this, and what
reads it". A `sheets` type is read through the Sheets surface, and a `base` type through the
Base surface — `larkdocio.base.read_base_markdown(url)` (see *Recipe: read a Base to Markdown*).

**Said once, here, rather than repeated at every example that follows: never copy a tenant host
out of an example into your own code.** A host you see in a URL example
(`your-domain.larksuite.com` or any other) is a value **that example's tenant happened to
have** — it works against that tenant and silently breaks against the next one, whose
subdomain differs. Treat a host as something you read back (`validate_download_url`, a folder
listing's own `url`, a value you
already hold) or take from your own input, never as a literal to hardcode.

### The live-test URLs in `.env.example` are placeholders

`.env.example` names **one disposable, never-real URL per live ring** (`LARKDOCIO_CANARY_DOC`,
`LARKDOCIO_SCRATCH_SHEET`, `LARKDOCIO_WRITE_SCRATCH_DOC`, …), and every value it carries is a
**placeholder** on the `your-domain` host — the shape of the URL, not a document anyone can
read. Credentials there are blank. To run a live ring, replace its placeholder in your `.env`
with a throwaway document, sheet or Base on your own tenant that holds nothing sensitive. A ring
whose URL is unset **or still the placeholder** **skips loudly**, naming the variable — never a
silent pass, and never a run against the placeholder.

### Where a new object goes — you name the destination, or nothing is created

**The rule, and it has no exceptions: if you do not say where a new document, spreadsheet, Base
or folder goes, this library does not create it.** Every create-class call takes a
`folder_token` — the token of a folder **you own, created, or were given access to** — and a
call that names none is refused **locally, before anything is sent**. Nothing is created, and
nothing is half-created.

**Why, and it is not a style preference.** With no destination the platform files the new object
in the *application's own space* — the storage belonging to the app identity your credentials
name. **That space has no human interface.** Nobody can browse it, not even an account holder
with full administrative rights; its trash cannot be listed or emptied; and deleting something
there **trashes rather than purges** it, so a removed object can still answer for itself on
**one of five** routes measured here (§ *"Recipe: read every document in a folder"* → *"Remove a
document and ONE ROUTE IN FIVE still answers for it"* — the number, the route and its limits).
Anything that lands there is reachable only through a token somebody kept, and unreachable
forever once that token is lost. A refusal costs you one argument; the old default cost an
object you could never find again. (Objects in that space may also surface
in search results — **not measured by this project**.)

**What to supply, and how to get one.**

- **A folder you can see.** Open the folder in your own Drive and take the token from its link
  (`https://<host>/drive/folder/<token>` — the last path segment).
- **A folder you make.** `DriveFoldersWriteClient.create_folder(name, parent_token)` creates one
  inside a parent you name — see § "Recipe: create a folder to organise into — and the one thing
  it will do that surprises people". It, too, requires the parent: the library does not invent a
  place to put things, one level up or otherwise.

**Not a destination, though it is a token: `DriveClient.root_folder_token()`.** That accessor answers the token of the *application's own root* — the space described just above — so it must never be passed as a `folder_token` to a create. It stays public, and stays in the drive-read matrix, because reading it is how you inspect that space; using it as a destination is how something ends up where nobody can browse to it. A destination is a folder **a person** can open.

**That one is refused by type, not only by rule — and here is exactly how far that reaches.** The accessor returns an `ApplicationRootToken` (`larkdocio.common.destination.ApplicationRootToken`, also re-exported as `larkdocio.drive.ApplicationRootToken`), which is a `str` subclass: it concatenates, compares, formats, hashes and JSON-serialises exactly as the plain token always did, so nothing you already wrote against it changes. What the type adds is that every create refuses it **locally, before any call** — no extra request, no extra permission. **The limit, stated with the guarantee:** what gets refused is the value this library's own accessor handed you. A raw root token *copied in from elsewhere* — pasted from a log, read out of your own config, or rebuilt from a string — arrives as an ordinary string and cannot be told apart from a folder you own. Closing that gap would mean resolving the root inside the check, which would add a network call and a wider permission requirement to every create, so the check stays local and the gap is disclosed here instead.

**The words the refusal itself uses.** The library carries the sentences below verbatim in the `MissingDestinationError` it raises — the same bytes, held equal by a test — so the message you get in a traceback and the rule you read here cannot drift apart.

<!-- BEGIN DESTINATION-REFUSAL (verbatim from larkdocio.common.destination; byte-equality guarded by tests/test_caller_supplied_destination.py, in the source repository) -->
> **The rule.** the destination is the caller's: this library creates nothing in a place you did not name, because an object created with no destination lands in the application's own space, which no human interface can browse — deleting it there only trashes it, and what you lose track of you cannot recover.
>
> **Not a destination.** that token is the application's own root — the value DriveClient.root_folder_token() answers, and the one place this rule exists to keep objects out of, for the reason the rule above gives. It is refused by type, so what this library can refuse is the value its own accessor handed you: a raw root token copied in from elsewhere arrives here as an ordinary string and cannot be told apart from a folder you own.
>
> **What to supply.** pass folder_token= the token of a folder you own, created, or were given access to.
>
> **How to get one.** to get one: open a folder in your own Drive and use the token from its link, or create a folder with create_folder(name, parent_token).
>
> **What a folder costs.** what making one costs, before you make one: this library ships no verb that deletes a folder — the Drive delete route was measured to work and was left unshipped under the one-verb ruling, so a folder created through larkdocio is permanent as far as this library is concerned — and creating the same name twice under the same parent makes a second folder rather than reusing the first, so a retry is not idempotent.
<!-- END DESTINATION-REFUSAL -->

**An empty string is not "no opinion".** Passing `folder_token=""` is refused here as well —
because the platform *accepts* it and files the object in the application's own root, which is
precisely the outcome this rule removes.

**Which calls this reaches, and which it does not.** It reaches the calls that make a **new
top-level object**: `WriteClient.create_document`, `SheetsWriteClient.create_spreadsheet`,
`BaseSchemaClient.create_app` / `copy_app` and their plan-level twins `create_base` /
`copy_base`, `DriveFoldersWriteClient.create_folder`, and the upload family (`upload`,
`upload_prepare`, `upload_chunked`, `put_file_in_folder`). It does **not** reach a create that
happens *inside* an object you already named — blocks in a document, a table, column, row or
view in a Base, an image anchored in a workbook, a version of a file, a comment on a file —
because there the parent **is** the destination and you have already supplied it.

**And every one of them ANSWERS WITH A VALUE THAT NAMES WHAT WAS MADE.** The same class of verb
gets the same class of answer — a typed value carrying what the reply actually holds, and able
to say what the reply did **not** answer:

| Verb | Answers with | Reads |
|---|---|---|
| `WriteClient.create_document` | `CreatedDocument` (a `dict` subclass) | `.document_id` `.title` `.revision_id` `.folder_token` — and **no `.url`**, because the docx reply carries none |
| `SheetsWriteClient.create_spreadsheet` | `CreatedSpreadsheet` (a `dict` subclass) | `.spreadsheet_token` `.title` `.url` `.folder_token` — the `url` is Lark's own |
| `BaseSchemaClient.create_app` | `CreatedBase` (a subclass of the SDK's `App`) | `.app_token` `.name` `.url` `.folder_token` `.default_table_id` `.time_zone` `.revision` |
| `BaseSchemaClient.copy_app` | `CopiedBase` (same, plus `.echo_is_not_state`) | the same attributes — but the copy is **asynchronous**, so this is an echo, not state |
| `DriveFoldersWriteClient.create_folder` | `CreatedFolder` | `.token` `.url` `.name` `.parent_token` |
| the upload family | `UploadedFile` / `LinkedFile` | `.file_token` `.folder_token` `.name` `.size` `.sha256` |

**Nothing you already wrote breaks.** The two `dict` subclasses **are** their reply's own dict,
so every subscript, `.get`, membership test, `{**splat}`, `json.dumps` and `==` against a plain
dict keeps its old answer; the two `App` subclasses **are** the SDK echo, so every attribute and
`isinstance(x, App)` keeps its old answer. The only thing that changed is `type(x) is dict` /
`type(x) is App` — use `isinstance`. **And no URL is ever assembled from a host and a token**,
on any of them: a link this library constructed would be a guess wearing the shape of an answer.

**Where things you can no longer see should go instead: a folder you keep.** If you are making
throwaways, make them in a folder of your own and delete the folder's contents when you are
done. That is the difference between a cleanup you can verify and one you have to believe in.

### The disposables doctrine — larkdocio's own test-suite policy, not an engine restriction

**Read this first: it is a rule about larkdocio's own tests, not a restriction the engine
imposes on you.** The write engine never inspects *which* document you target — there is no
allow-list, no "scratch only" mode, no refusal keyed on a document id. **You may write to any
document your WRITE app can reach**, and that is the intended use. What follows is
**this project's own test-suite policy**, adopted so that developing the library can never
touch someone's real document.

**Live WRITE calls in this repo's gates only ever run against a disposable doc the harness
itself created — never a real document, never the canary.** The write gate
(`LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write` — the consent variable is not
optional, and without it every marked test loud-skips) **self-provisions its own scratch doc**,
round-trips create →
baseline → download → mutate → diff (the edit must be surgical: only the target region
changes) → **restore to a byte-identical baseline** → delete. Every write round-trip leaves
the world as it found it. Offline, plain `pytest -q` never writes and needs no creds.

**You can do exactly the same, with the shipped calls.** The spreadsheet, document and Base
write surfaces each carry a create/destroy pair, so working against a throwaway file of any of
those three kinds needs nothing beyond this library:

| Surface | Create (the destination is required — § "Where a new object goes") | Destroy (the WHOLE file) |
|---------|--------|--------------------------|
| spreadsheet | `SheetsWriteClient.create_spreadsheet(title, folder_token=…)` | `SheetsWriteClient.delete_spreadsheet(spreadsheet_token)` |
| document | `WriteClient.create_document(title, folder_token=…)` | `WriteClient.delete_document(document_id)` |
| Base | `BaseSchemaClient.create_app(name, folder_token=…, time_zone=…)` | `BaseSchemaClient.delete_base(app_token)` |

**Make your disposables in a folder you can see.** Each create above requires a `folder_token`,
so a throwaway lands somewhere you can open and delete yourself — which is what makes "I cleaned
up" checkable rather than hopeful.

**A DESTROY IS NOT A CLEAN SLATE: uploaded media inside a disposable is PERMANENT RESIDUE.**
Read this before you plan a teardown, because it is the one thing the create/destroy pair above
cannot undo. **No route in Lark's open API purges drive media** — and that is now **measured
rather than asserted**, which is the difference between a fact you can plan around and a
sentence somebody once wrote. A media token
uploaded *into* a document, a Base or a spreadsheet **survives the deletion of the thing it was
uploaded into** — deleting the disposable does not undo the upload. A file uploaded into a
**folder** is the exception and the difference worth knowing: that one **can** be deleted
(`DriveFilesWriteClient.delete`), and even then Lark **trashes rather than purges** it, so the
token still resolves afterwards. So a disposable that only ever held text leaves the world as it
found it, and a disposable you put a picture in does not.

This is stated once and cross-referenced from the places you meet it, rather than said twice in
slightly different words: the whole disclosure, including the expensive case where the **upload
happens before the bind is validated** so a *failed* bind still costs you a permanent token,
lives at the failure sites — § "Recipe: float a picture over a SINGLE-CELL anchor (the
float-image write)" (which hands you the orphan on `exc.orphan_file_token`), § "Recipe: put an
image in a document (create, upload, bind)", § "Recipe: attach a file to a record, and prove the
bytes survived", and § "Recipe: attach a file to a document (the 📎 attachment card)". `capabilities()`
points here rather than restating it. **The practical rule for a disposable: upload the smallest
file that proves your point, and record the tokens you mint — recording them is the only thing
anyone can do with them.** A purge verb is not something this library will invent.

**THE MEASUREMENT BEHIND *"no route purges drive media"*, so you can see the edge of it.** That
sentence used to be a statement about *this library's* surface written in the platform's voice,
with the attempt list left in somebody's head. It is now enumerated: **nine** distinct
destructive request spellings, in **fourteen** sends, against **four** media tokens minted on
**both** of this library's media paths (two on the sheets float-image path, two on the docx
image path). **Not one removed a media token**, and a liveness check answered *still resolves*
after every send. The spellings tried, in full — `DELETE drive/v1/files/:token` with
`type=file`, `type=media`, `type=sheet_image` and `type=docx_image`; `DELETE
drive/v1/medias/:token`; `POST drive/v1/medias/:token/delete`; `POST
drive/v1/medias/batch_delete`; `DELETE drive/explorer/v2/file/:token`; and the **unbind**,
deleting the only block that referenced a successfully bound token.

Three arms carry the weight and are **not averaged into** the rest. The one **documented**
delete route (`DELETE drive/v1/files/:token?type=file`) refuses a media token with **HTTP 404**
identically on both paths, while a **positive control** in the same run under the same
credential deletes a real Drive file (`code: 0`, and an independent re-query answers *is
deleted*) — so the refusal is the token's, not the credential's. That route's own error body
prints a **closed** `type` enum — `file, docx, bitable, folder, doc, sheet, mindnote, shortcut,
slides` — containing neither `media`, nor `sheet_image`, nor `docx_image`; all three were sent
and all three were refused with the server echoing the value it received. And **unbinding is
not a purge**: deleting the only block referencing a bound token answered `code: 0`, the
parent's children read back empty, and **the token still resolved**.

**The scope, which the claim does not exceed.** One tenant, on one day, on `larksuite.com`,
with a `tenant_access_token`. A **`user_access_token` is unmeasured** — and a human trash UI
does exist for a user identity, so a user-scoped route is the most plausible unprobed thing.
Every spelling outside the nine above is **unmeasured, not refuted**, and an API gains
endpoints. The same enumeration is carried in the wheel itself, on
`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`, so a caller can read it without leaving
Python.

**`create_document` takes a `folder_token` too**, and for a disposable it is worth passing: a
document created with no folder lands in the app's own space, where a human cleaning up after a
failed run has nothing to look at. **`create_base` takes one too, spelled and defaulted
identically** — and on a Base it is the *only* way to file it, since this library ships no Base
move. Where a file lands also decides who can already read it; both cases are stated in
§ "Recipe: grant a HUMAN access".

**The runnable create → use → `finally`-delete → confirm-it-is-gone script exists for each
surface, and they are in two different places.** For a **spreadsheet** it is
§ "Recipe: work against a disposable spreadsheet (create, use, delete)"; for a **Base** it is the
**second code block of** § "Recipe: create, rename and copy a Base (the structural handshake)",
which is where
`delete_base` is taught with the three things about it you cannot infer — that Lark's route
**trashes rather than purges**, that the delete's own `code: 0` is acceptance and the **proof
must be asked of the bitable side**, and that a brand-new Base may not be addressable as a Drive
file for some minutes. The document pair takes the same shape as the spreadsheet one. **The Base
was the surface where this exit was missing longest**; it is not missing now, so there is no
surface here on which the doctrine cannot be followed. `capabilities()` reports the two
destroys under `sheets-write` / `docx-write` `lifecycle` alongside their creates, and the Base
destroy under `base-schema-write` `lifecycle`; the Base **create** is reported under that
surface's `operations` instead, because unlike the other two it is a plan-gated schema op.
**A destroy here trashes the whole file**, not one tab and not one table (those are `DeleteTab`
and `delete_table`, both through their plan gates).

---

## Capability matrix

The single source of truth for what larkdocio can do is `larkdocio.capabilities()` (a
typed, JSON-serializable projection over the op registries, the read clients, and the
parser). The matrix below is **distilled from it** and cross-checked bidirectionally by the
drift guard — including the **creatable-content floor**, the one capability fact an op list
cannot carry.

**SEARCHING FOR A TASK RATHER THAN A SURFACE? READ THIS FIRST — this matrix is indexed by
surface and by OPERATION NAME, and the names are the API's, not yours.** Ask it *"can it hide a
tab?"* and it answers nothing, because the word *hide* is not an operation name: that capability
is `set-tab-visibility` on `sheets-write`, written in a plan as `SetTabVisibility`, and neither
spelling contains the word you searched for. Nothing below is missing — you are asking the wrong
index.

**The index that answers a task is `larkdocio.guide()`**, whose every section is named after the
failure it cures, so you scan for your symptom and fetch one section instead of paging through
this matrix. *Hide a tab* is § "Recipe: reorder, retitle and hide a tab (a tab-presentation
write)"; *hide a row* is § "Recipe: set a row's height, a column's width, and hide a row (a
dimension-property write)". **The rule of thumb: this matrix when you know the verb,
`larkdocio.guide()` when you know only the job.** `capabilities(surface=…)` is the same
verb-side answer as a row below, in more detail — it is not the task index either.

<!-- BEGIN CAPABILITY-MATRIX (drift-guarded vs larkdocio.capabilities(); see tests/test_guide.py, in the source repository) -->

**Surfaces** — what you can do, and which credential pair each needs. The exact scopes are
not repeated here: they are generated per surface (and per call) in *Permissions — what to
ask for* above, from `larkdocio.permissions`.

| Surface | Mode | Credential pair | Operations | Legs and lifecycle |
|---------|------|-------------|------------|--------------------|
| `docx-read` | read | READ app — scopes in *Permissions* above | `batch_get_user_names`, `download_board_image`, `download_image`, `get_docx_content`, `get_wiki_node_info`, `read_document_revision`, `parse_docx_content`, `parse_docx_node`, `parse_docx_tree`, `walk`, `plain_text`, `project_block_ids`, `snapshot`, `load` | — |
| `docx-comments-read` | read | READ app — scopes in *Permissions* above | `batch_query_comments`, `comments`, `list_comments`, `list_replies` | — |
| `contacts-read` | read | READ app — scopes in *Permissions* above | `resolve_user`, `resolve_colleague`, `search_employees`, `batch_get_id` | — |
| `drive-read` | read | READ app — scopes in *Permissions* above | `list_folder_children`, `list_folder_children_to_exhaustion`, `find_children_by_name`, `root_folder_token`, `folder_name`, `document_security_level`, `list_versions` | — |
| `sheets-read` | read | READ app — scopes in *Permissions* above | `batch_get_values`, `get_frozen_panes`, `get_sheet_filter`, `get_spreadsheet_meta`, `get_values`, `query_sheets`, `read_revision`, `read_spreadsheet`, `read_spreadsheet_markdown`, `read_tab_filter`, `read_tabs_frozen`, `read_tabs_revision`, `read_used_range` | `create_export_task`, `download_export`, `export_xlsx`, `poll_export_task`, `read_workbook` |
| `sheets-embedded-deep-read` | read · opt-in | READ app — scopes in *Permissions* above | `deep_read_embedded_sheet` | — |
| `base-read` | read | READ app — scopes in *Permissions* above | `get_app`, `list_tables`, `list_views`, `get_view`, `list_fields`, `search_records`, `batch_get_records`, `read_base`, `read_base_markdown`, `record_permalink` | `read_hierarchy` |
| `base-comments-read` | read | READ app — scopes in *Permissions* above | `comments` | — |
| `base-embedded-deep-read` | read · opt-in | READ app — scopes in *Permissions* above | `deep_read_embedded_base` | — |
| `docx-write` | write | WRITE app — scopes in *Permissions* above | `insert`, `delete`, `subspan`, `comment-create`, `comment-remove`, `grow-table`, `edit` | `put_image_in_document`, `put_file_in_document`, `get_block`, `read_document_revision`, `create_document`, `delete_document` |
| `sheets-write` | write | WRITE app — scopes in *Permissions* above | `value`, `formula`, `dropdown`, `structural`, `dimension-property`, `style`, `merge`, `tab`, `freeze-panes` | `dry_run`, `put_image_in_sheet`, `put_float_image_in_sheet`, `remove_float_image_from_sheet`, `put_values`, `query_tabs`, `query_float_images`, `read_values`, `read_value_range`, `read_sheet_geometry`, `read_frozen_panes`, `create_spreadsheet`, `delete_spreadsheet` |
| `base-write` | write | WRITE app — scopes in *Permissions* above | `create_record`, `update_record`, `delete_record`, `batch_create_records`, `batch_update_records`, `batch_delete_records` | `upload_attachment_media`, `download_attachment_media`, `permalink_attachment_media` |
| `drive-versions-write` | write | WRITE app — scopes in *Permissions* above | `create_version` | — |
| `drive-access-write` | write | WRITE app — scopes in *Permissions* above | `grant_access`, `update_access`, `revoke_access`, `list_members`, `set_copy_permissions` | `resolve_grantee_email` |
| `drive-files-write` | write | WRITE app — scopes in *Permissions* above | `put_file_in_folder` | `download`, `permalink`, `delete` |
| `drive-folders-write` | write | WRITE app — scopes in *Permissions* above | `create_folder` | — |
| `base-schema-write` | write | WRITE app — scopes in *Permissions* above | `create_app`, `rename_app`, `copy_app`, `create_table`, `batch_create_tables`, `rename_table`, `create_field`, `update_field`, `convert_field`, `create_view`, `update_view`, `delete_view`, `delete_field`, `delete_table`, `batch_delete_tables` | `migrate_field_type`, `delete_base` |

**Anchor kinds** — *how* each docx write request family points at its target, which an op name
alone cannot express either
(`capabilities(full=True)["surfaces"]["docx-write"]["operations"][*]["anchor_kinds"]`):

| Request family | Points at | Anchor kinds |
|----------------|-----------|--------------|
| `insert` | the **reference** block the new content is placed before / after / inside | `Anchor` (a verbatim quote + a breadcrumb heading-path) · `AnchorById` (a block id) |
| `delete` | the **target** block to remove | `Anchor` · `AnchorById` |
| `subspan` | the block holding the span to rewrite | `Anchor` · `AnchorById` |
| `edit` | the block — or the table **cell** — whose whole text is replaced | `Anchor` · `TableLocator` (a row-key quote + a column target) · `AnchorById` |
| `grow-table` | the **table** whose grid gains a row at the end — never a cell | `AnchorById` (the table's own block id) · `TableLocator` (a row-key quote identifying which table; its column target is not consulted) |
| `comment-create` | the **whole document** — a comment attaches to nothing smaller | `WholeDocument` (its one value, WHOLE_DOCUMENT; no passage anchor exists) |
| `comment-remove` | the **comment thread** to remove | `CommentThread` (the thread id the API assigned) |

An **`Anchor`** reads naturally and needs nothing but the document's text, but it can only
address text that is *unique* (a quote matching five blocks refuses, forever) and it goes stale
the moment the text changes. An **`AnchorById`** takes the document's own stable handle — every
parsed node carries `block_id`, and `apply()` hands back `created_block_ids` — so it is
unambiguous by construction, needs no breadcrumb, and can address a block whose text repeats
(or a whole container, for a delete). Ids are matched by **exact equality**: an id that never
existed, belongs to another document, or has been deleted is **refused with the id named**,
never fuzzy-matched to a near miss.

**Creatable-content floor** — what a write surface can bring into **existence**, which an
op name alone cannot express (`capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]`):

**Four states, not two.** A shape is creatable *through the plan-gated path*, creatable
**out of band** (a typed op outside the plan gate, because the compiler holds no bytes to
give it), editable-but-not-creatable, or not creatable at all. The out-of-band column is the
one a flat NOT-creatable list used to swallow — reading *"image/media: not creatable"* and
concluding an image cannot be put in a document was, for a whole arc, the wrong conclusion
from a true sentence.

| Surface | Creatable | Creatable kinds | Creatable OUT OF BAND | NOT creatable | Editable but NOT creatable |
|---------|-----------|-----------------|-----------------------|---------------|----------------------------|
| `docx-write` | **`NewParagraph`** (a plain unstyled paragraph — still valid, ≡ kind paragraph) and **`NewBlock`**, the typed kind carrier. Created text is *unstyled* — with one exception, the **link anchor**, in the NOT-creatable column | `heading` (level 1–9) · `paragraph` · `bullet` / `ordered` / `todo` (nestable) · `code` (with a language) · `quote` · `table` (an R×C grid whose cells are plain text **or a span sequence carrying a link anchor** + an optional header row) · `mermaid` (a diagram, **create-only**: creatable, but no in-place update exists, so a change is a delete plus a create) | an **image** in the document body (docx block type 27) — `larkdocio.write.media.put_image_in_document` · a **file attachment** in the document body (docx block type 23) — `larkdocio.write.media.put_file_in_document`. Each is one op doing a create → upload-bound-to-that-block → PATCH as a unit, outside the plan gate, and each has its own recipe: § "Recipe: put an image in a document (create, upload, bind)" and § "Recipe: attach a file to a document (the 📎 attachment card)". **Both position with a `parent_block_id` + a zero-based integer `index`, not with `Anchor` / `AnchorById`** — the one asymmetry on this surface, stated in those recipes | **merged / spanned table cells** (colspan / rowspan) · callout · an image / media upload **through the plan-gated path** — the compiler holds no bytes and makes no network call, so a Markdown `![](…)` is refused and no `NewBlock` kind creates one; the bytes route is the out-of-band column, left · board / whiteboard · an in-place update of a mermaid diagram (docx block type 40) · embed (iframe / Base / Sheet) · grid / column layout · colors (text or background) · styled runs on created text — with ONE exception, the **LINK ANCHOR**, authored as a typed `TextSpan` with `link_url=` inside `NewBlock.rich_paragraph`, never through the Markdown dialect · a **styled run other than a link inside a table cell** — **narrowed**, and the reason the old row gave survives in what follows. A **link** in a cell now ships: Lark was measured to accept and store the link-carrying run there on both write routes, so a cell is authored as a `TextSpan` sequence (or as `[label](url)` through the dialect). Every **other** run styling in a cell is still not creatable — none of them is a field on a `TextSpan`, and none was measured in a cell — and the anchor is a **create-time** capability: `EditRequest.replacement` is a plain `str` (no spans) and a sub-span edit inside a cell is out of scope, so a later whole-cell patch replaces an anchored cell with plain text | a **merged** table: it reads (as HTML) and its unmerged cells patch like a paragraph (via a `TableLocator` anchor), but **no merge can be authored** — Markdown has no colspan/rowspan, so an authoring request implying a span is refused (`merge-not-expressible`), never approximated |

**Flags** — the behavior switches and their shipped defaults. All but one are opt-**in** (off
until you ask); `resolve_mentions` is the one that is opt-**out** — it is **on**, so a read
resolves mention names whenever its preconditions are met:

| Flag | Kind | Default | Summary |
|------|------|---------|---------|
| `resolve_mentions` | read config (`Config(OutputConfig(resolve_mentions=…))` / `config.json` → `output.resolve_mentions`) | **on** | Resolve @mention `open_id`s to display names in a document's Markdown projection (`@ou_id` → `@Name`) via `batch_get_user_names`. Applies to **both** read paths: the `download` command does it automatically, and an in-process read does it when the parser is handed the read client — `Parser(Config(), read_client=client)` — while a parser with no client renders the raw `@ou_id`. **Two preconditions, both Lark console settings on your own app:** the field-level `contact:user.base:readonly` scope (without it the directory answers with every name field **null**) **and** the app's **contacts data range** covering those users. Miss either and every id stays raw — a graceful degrade, never an error, and the read logs **one** line naming which of the two it was (users returned with no readable name means the field-level scope; ids that never came back means the data range). See § "Recipe: download a docx to Markdown". |
| `deep_read_sheets` | CLI `--deep-read-sheets` (on `download` **and** `folder`) | off | Deep-read docx embedded sheets (block type 30) into inline Markdown tables. Off ⇒ no Sheets API calls; a failed read degrades to the placeholder. A download says at the end how many sheets it left unfetched — see *What the run did not fetch*. |
| `deep_read_bases` | CLI `--deep-read-bases` (on `download` **and** `folder`; or `Parser(deep_read_bases=True, base_client=…)` in code) | off | Deep-read a Base embedded in a document (both embed block types) into inline Markdown tables. Reachable from the command line **and** in code; either way the deep read needs a Base read client, which the command builds from the READ credentials the way `--deep-read-sheets` builds its own. Off ⇒ no Base API calls and the reader emits the placeholder it always has. Every failure degrades to that same placeholder, byte-identical, so a download never fails because a Base could not be read. A download says at the end how many Bases it left unfetched — see *What the run did not fetch*. |
| `resolve_base_links` | read argument (`read_base(url, resolve_links=True)`) — **not** a CLI flag | off | Follow a Base link cell to its target: each linked record renders as its **target table's schema-designated primary field** (`is_primary`, read from that table's own field list) instead of a bare record id. Off ⇒ **byte-identical**: no extra API call, and a link cell renders the ids it always did. On, it **costs reads and says so** — `read_base(...).link_resolution` discloses how many extra calls were made and which target tables were touched — and the count follows the number of **target tables**, never the number of cells: every id wanted from one table is fetched in one batched `records/batch_get`, deduplicated and chunked. A link whose target record was deleted is a **normal** case, never an error: the per-cell answer is typed *resolved / dangling / unresolvable*, and the last of those claims nothing in either direction. Determinism is **same-run** — a second table is read, so a target renamed between runs legitimately changes the output. |
| `retain_base_raw_values` | read argument (`read_base(url, retain_raw=True)`) — **not** a CLI flag | off | Keep the **raw wire value** of every Base cell beside the rendered one. Every value a Base read otherwise returns is *display-shaped* — a Date arrives as an epoch and leaves as `2025/07/01`, an Email leaves as a `[text](mailto:…)` link, a Person leaves as a comma-joined name — which is right for reading and wrong for comparing, so a dedupe, diff or chart has to re-derive the values itself. Off ⇒ **byte-identical**: the rendered output does not move and **nothing is retained**. On, raw is **the wire shape exactly as Lark returned it** — no key renamed, no absence coerced, no epoch turned into a string, no list flattened or sorted, no type changed — and deliberately **not** a normalized typed middle form: no `datetime`, no `Decimal`, no person class and no per-type converter anywhere behind it. It is evidence, not a model. **Zero extra API calls either way** (the payload is already received; the flag only decides whether it is kept) — **but it costs memory: ≈7× the rendered cells**, ≈260 KB against ≈38 KB on a 64-row read of a real four-column table. Reached as `read_base(...).tables[i].rows[j].raw_fields`, and through `snapshot_table` as `SnapshotRecord.raw(field_name)` / `.raw_as_dict()`; with retention off both **refuse, typed** (`RawNotRetained`) rather than handing back an empty dict that would read as "the cells were empty". See § "Recipe: compare Base rows on the raw values". |
| `fidelity_read_sheets` | CLI `--fidelity-read-sheets` (on `download` **and** `folder`; the docx **embedded**-sheet leg also needs `deep_read_sheets`, a folder's **standalone spreadsheet** child needs nothing else) | off | Read a sheet's **whole-cell (format-level)** bold/italic **and its per-cell background fills** — the style set on the *cell*, which the values API does not carry — via a READ-creds xlsx export. Bold/italic render as MD emphasis; a fill has no Markdown equivalent, so each tab's fills are disclosed in a note above its table (the ARGB against the cells carrying it), which is what makes a colour-encoded sheet readable rather than silently empty. **Run-level** emphasis (bold/italic on a text run *inside* a cell) comes through the values API and is **already** rendered without this flag, so on a run-level-styled sheet this flag correctly changes nothing. A failed export degrades to values-only. |
| `folder_assets` | CLI `--assets` (on `folder` **only**; or `read_folder(url, assets=True)` in code, which *reports* the refs — the fetch is the command's) | off | Fetch a **whole folder's** binaries: every walked document's images and its flowchart / mindmap (whiteboard) PNGs. **The flag a mindmap-only document needs** — without it a document whose entire content is a diagram comes back as a bare token and nothing else. Not a second spelling of a `download` flag, because `download` has none: its asset handling is *unconditional* and config-gated (`output.skip_img_download`). What is shared is the on-disk vocabulary — the same directory (`output.image_dir`, `static`), the same token-derived filenames, the same relative-link rewrite. **Layout: one shared flat pool** beside the single Markdown document a folder read produces, `<-o>/static/<asset token>.<ext>`. **Collisions are impossible by construction** — the filename *is* the globally-unique Lark asset token — and the same token in two documents is the *same* asset: fetched **once** for the whole walk, every reference relinked. (Per-document subdirectories were rejected for the opposite reason: they would be named from a document **title**, and two documents in one folder may legitimately share one.) Off ⇒ inert: no asset call, no client built, no pool directory, Markdown byte-identical. **No new API reach** — the same media download and whiteboard export the docx reader already makes — so no scope moves. A per-asset failure **skips loudly** (Lark's own code and msg, naming the document and the asset, in the log and in an `## Assets not fetched` section) and the remaining documents are still fetched. Attachments are **not** in this set; they are `download`'s own config opt-in. |
| `verify_style` | engine (auto-on) | off | The write-gate style/format fidelity leg (export-based diff). Auto-on for a style / number-format / merge / structure write; a plain value write stays export-free. |

**Safety contracts** — how the write surfaces refuse to do the wrong thing, and (the one read-side entry) which route a historical read is allowed to trust:

| Contract | Applies to | Summary |
|----------|------------|---------|
| `plan-gated` | docx-write, sheets-write, base-write, base-schema-write | `apply()` accepts ONLY a non-forgeable `Plan` from `dry_run` — there is no direct-apply path. |
| `dry-run-mandatory` | docx-write, sheets-write, base-write, base-schema-write | Every write is previewed by a mandatory `dry_run` (zero writes) that builds the `Plan`. |
| `STALE_SHEET` | sheets-write | Sheets staleness in **two tiers**, and tier 1 is **never silently off**. **Tier 1 — the `revision` compare-and-swap, when available:** the revision is cached at plan time and re-read before EACH write; a bump refuses `stale-sheet` (no write) and resyncs so the rest of the batch applies. Some spreadsheets report a constant `0` (or no) revision, so every plan and dry-run output carries `revision_guard` — `active` on a usable (positive) anchor, `unavailable` on `0` / `None` / any non-positive value — plus the WHY in `revision_guard_detail`: **a revision-`0` spreadsheet marks tier 1 `unavailable`** instead of letting the compare-and-swap no-op invisibly. **Tier 2 — the value precondition, always:** each entry's `value_precondition` is `enforced` (value / rich-cell — the target's raw value is re-read right before the write and drift refuses; a **formula** entry compares its target's **expression** instead, because a computed value drifts whenever the referenced data changes) or `none` (dropdown-rule / structural / merge / tab have no cell-value precondition, so on a constant-`0` sheet those entries carry no staleness guard at all). **Self-healing:** ANY nonzero advance still refuses `stale-sheet` from a `0` anchor, and the next plan built on a nonzero anchor marks itself `active`. |
| `STALE_ANCHOR` | docx-write | The anchored block is re-read right before each write and re-validated with **the anchor's own precondition**; drift refuses `stale-anchor` with **no write**, and the rest of the batch still applies. An `Anchor` requires its **quote to still be present** in the live block. An `AnchorById` has no quote — and an id cannot come to mean a different block — so the plan captures the block's text and the write is a **compare-and-swap**: any change to that block since the preview refuses rather than overwrites it. A `TableLocator` cell edit is stricter still (a **double** re-validation: the row's key cell *and* the target cell). A block that cannot be re-read at all — **deleted between plan and apply** — refuses `stale-anchor` too, carrying Lark's own code/msg, never an aborted batch. |
| `STALE_DOCUMENT` | docx-write | The **whole-document** compare-and-swap — what catches drift **around** an anchor, which `STALE_ANCHOR` is structurally blind to (an insertion above a still-matching anchor moves where your content lands). Pass the document's revision to the previewer — `dry_run(requests, root, document_revision_id=document.revision_id)`, the value the reader already hands you from `get_docx_content(...)` — and `apply` re-reads it **once, immediately before the batch**. On **any** difference it refuses the **ENTIRE batch** with `stale-document` and **ZERO writes issued**: partial application is not an outcome, and there is **no auto-mapping** — the engine never re-locates anchors or re-indexes positions to accommodate a document that changed under a plan. The refusal's mandatory `detail` names both revisions and tells you to **re-download and re-plan**. A revision that cannot be read at all refuses **conservatively** (unconfirmable is treated as changed). **Never silently off:** every plan carries `revision_guard` — `active` when it holds a usable revision, `unavailable` otherwise — plus the WHY *and how to activate it* in `revision_guard_detail`, and the apply-log carries the batch's status. With no revision the guard is marked `unavailable`, costs no call, and the per-entry `STALE_ANCHOR` re-validation still runs; it **self-activates** on the next plan that carries one. |
| `STALE_BASE` | base-write | **A client-side read-compare-write on `table.revision` — and the name promises no more than that.** There is **no `If-Match`** on the Base API and no server-side compare-and-swap: a record write carrying a `revision` or `last_modified_time` body key answered **success and applied the write**, so larkdocio sends no such key — sending one would be a lie that reads like safety. Instead the engine **reads `table.revision`, compares it to the value your plan was built on, and only then writes**. What that buys: the window between the plan and the write is closed. What it does **not** buy: the last microsecond between the compare and the write. **The halt scope is per table**, because the anchor is: a table that moved has *its* entries refused with **zero writes for that table**, and every other table is still judged against its own anchor. The refusal is **recoverable** — re-read, re-plan, re-apply — never a dead end. **Tier 1 is NEVER silently off.** A freshly created Base reads `table.revision` as `0`, and so did the standing test Base before it moved — revision-`0` is a **state**, not a property of a particular Base — and comparing `0 == 0` before a write cannot observe an advance, so it would be silently inert. So every table's plan carries `revision_guard` — `active` on a usable (positive) anchor, `unavailable` on `0` / `None` / any non-positive one — plus the WHY in `revision_guard_detail`, and it **self-heals**: the next plan built on a positive anchor marks itself `active`. **A second tier runs underneath it** for every entry that has a `before`: the cells an update writes (or the record a delete removes) are re-read immediately before the batch, and drift refuses `precondition-mismatch` for that entry alone — which is what covers a table whose anchor cannot arm tier 1. And because **success is not evidence a write happened** on this API, every call is followed by a second anchor read: a call that answered success without moving the anchor is reported **`dropped`**, never `applied`. The engine reports it and does **not** retry — re-sending would be a guess about why the value was discarded. |
| `exactly-one-or-refuse` | docx-write, sheets-write, contacts-read | Resolution returns EXACTLY ONE target or a typed refusal — never a guess: an anchor on the write surfaces, a display name on `contacts-read`. |
| `permission-denial-is-never-an-absence` | docx-read, docx-comments-read, sheets-read, sheets-embedded-deep-read, docx-write, sheets-write | **A scope denial never presents as an absent thing.** When Lark refuses because your app lacks a **scope**, you get a distinct `LarkPermissionError` (a `LarkAPIError` subclass, so existing handling is unaffected) whose `denial` carries the **exact missing scope(s)**, Lark's **verbatim** `code`/`msg`, the **console link** when Lark supplies one (never invented — an absent link is stated as absent, not filled with a placeholder), **which credential pair** made the call, and the **fallback that still works** where there is one. It is never folded into `not-found`, "unavailable" or a generic error, because that conflation is how a missing **field-level** grant reads as missing data: the call **succeeds** and the fields that grant governs come back **empty**. **That third case is classified too** — a success whose governed fields are *all* empty is reported as a suspected permission gap naming the grant, conservatively, so a **partial** answer stays an ordinary absence. **The classifier is one shared place** — every surface's non-zero Lark code is judged by the same code, which is why the behaviour is uniform by construction. What the Applies-to column lists is where the contract is **declared**, i.e. the surfaces that carry an enforcing arm for it; it is not a smaller claim about the classifier's reach. |
| `one-tree-one-batch` | docx-write | **One tree, one batch.** Every request in a batch is resolved against a **single consistent snapshot** of the document tree — which is what makes the staleness guards mean anything — so **a batch cannot depend on its own writes**: **every queued request must target content that exists at commit time; commit the insert, then anchor follow-ups by `created_block_ids`.** A deliberate limitation, not a gap: intra-batch dependencies would need sequential re-planning inside `apply()`, and an approved plan would stop describing what will happen. It is **disclosed**, not left to be discovered — the commonest way to trip on it is "insert a section, then refine what you just inserted", so when a `not-found` anchor's text appears in the **same batch's queued insert content** the `detail` names that cause and the recovery that works, instead of the re-read that cannot succeed. Detected at plan time from the batch's own content: **zero extra I/O**, the reason is still `not-found`, and an edit's `replacement` or a delete's target never triggers the insert-specific clause. See § "Recipe: accumulate edits across turns". |
| `comment-anchors-honored-or-refused` | docx-write | **A reviewer's inline comment anchors are honored on the path that can honor them, and every path that cannot refuses — all three paths answered.** A **sub-span** edit **proceeds**: it splits the block's runs at the span boundaries and each rebuilt run re-emits the anchor ids of the text it replaces, so an anchor rides back on the words it was left on (a span crossing runs whose anchors **differ** refuses `span-not-splittable` rather than stretch one reviewer's comment over text they never commented on). A **whole-block** edit refuses **`comment-anchors-present`** — the rebuild collapses the block to one run, leaving per-passage anchors nowhere to attach — with the ids and the sub-span recovery in its `detail`. A **whole-cell** (`TableLocator`) edit refuses on the same collapse, judged on the **inner text block** the patch rewrites, with the row and column named and a sub-span edit **anchored by that inner block's id** — `AnchorById(block_id=…)` — as the recovery (a row-key-and-column locator cannot name a span). No flag overrides either refusal, and a **block-level** comment triggers neither — a run split does not touch it. **And the plan says so on the path that proceeds:** a resolved sub-span entry whose target carries inline anchors carries a **`comment-anchors-present-on-target`** `preview_note` listing the ids, so a human approving the preview can see reviewers are involved and read what they said first (`comments()` joins each id to their words). It costs **zero extra API calls** — the anchors are already on the tree the plan resolved against — and it **composes** with any other disclosure rather than displacing it. Anchors themselves are never **creatable**: Lark has no anchored-comment create at all, which is also why this contract's live proof is a **read-only** arm against a document that already has real anchors. |
| `comment-create-whole-document-only` | docx-write | **A comment can be created — in the one shape Lark's API actually produces.** `CreateCommentRequest(text=…)` attaches a comment to the **whole document**: it appears in the document's comments panel and highlights no passage. Asking for an **anchored** comment — `anchor_block_id=`, `quote=`, or `is_whole=False` — is **refused** (`comment-anchor-not-creatable`), and that refusal is the point of the op rather than a limitation of it: the create route **accepts** those fields, answers `code 0`, and silently creates a plain whole-document comment (six shapes were tried, a bogus block id and a quote absent from the document among them; all accepted, all dropped). Forwarding them would report an anchored comment that was never created. A **spreadsheet** target is refused too (`comment-surface-unsupported`) — creation is enum-limited to `[doc,docx]` at every granularity, whole-file attempt included — and the refusal points at what does work: comment **reading** on a spreadsheet, `comments(token, file_type="sheet")`. Both refusals are decided at **plan** time, so they cost **zero API calls**. **Authorship is disclosed, not discovered:** every resolved create carries a `comment-lands-as-the-app-bot` `preview_note` — the comment lands as your application's own **bot** identity, a bare `open_id` with **no resolvable display name** (the directory answers `41050` for it, and the payload carries no human-vs-application flag) — and the apply-log reports that `author_id`, which is the id a later removal must state. |
| `comment-removal-sole-author-or-refuse` | docx-write | **A thread is removed only when your app authored it and is alone in it — whole, or not at all.** There is no delete-a-comment endpoint (that route answers a gateway-level, non-JSON 404), so `RemoveCommentRequest(comment_id=…, author_id=…)` removes a comment by deleting **every** reply, which the API permits only for replies the caller wrote (anything else is HTTP 403 / `1069303 "forbidden"` — about *who is asking*, not about the file). So the engine **reads the live thread and judges it before the first delete**: a thread carrying anyone else's reply refuses `comment-thread-not-solely-authored` with the foreign author named and **nothing deleted**; a thread already gone or empty refuses `not-found` rather than reporting a removal that did not happen. Because the decision precedes every delete — and a thread that passes has one author, so the API judges each of its deletes identically — **no code path deletes some replies and stops.** A server failure partway through is the one thing no pre-check prevents; it cannot be undone, so it is **recorded**: the refusal carries the ids that did go. `author_id` is **required and never guessed** — the directory answers `41050` for your bot id — and a create's apply-log entry hands you exactly that id. |
| `read-back-is-the-verdict` | drive-access-write | **An accepted call is not a stored one.** `code 0` proves acceptance and nothing else, and this exact endpoint family was measured swallowing a write — a member re-add answered `code 0` with a complete member echo and was absent from an independent read a moment later. So `grant_access` / `update_access` / `revoke_access` each follow their write with a member read, `set_copy_permissions` follows its one-key-per-call PATCHes with a settings read, and a call that was accepted and did not store reports `stored=False` rather than success. |
| `bytes-verified-round-trip` | drive-files-write | **The verdict is the re-download, not the `code 0`.** With `verify_bytes` (the default) `put_file_in_folder` downloads the object it just uploaded and compares it to what went up **by `sha256` and length** — the shared `verify_round_trip`, the same check the Base attachment leg uses — and publishes that verdict as `LinkedFile.bytes_verified`; the bytes are never inspected, and the chunked route above `SINGLE_SHOT_MAX_BYTES` is verified identically. **Two limits, stated:** `verify_bytes=False` turns the check off and `bytes_verified` then reports `False`, which is the absence of a verdict rather than a negative one; and a failure after the upload — a failed verification included — leaves a real file behind, so the exception carries `orphan_file_token` and nothing here issues an unrequested delete. |
| `version-pairing-is-not-a-verdict` | drive-versions-write | **The revision read happens BEFORE the write, and it is a pairing rather than a verdict.** `create_version` reads the head docx revision immediately before the create so a ledger can record `(name, token, revision)` as one row; it never lists the new version back, and **nothing in the shipped call path verifies that the version exists** — the read-back that would exists only in the credential-gated live gate, so `code 0` and a version token prove acceptance. The pairing is exact absent a concurrent edit (the create was measured revision-inert), and an unavailable revision is honestly `None` with the reason in `revision_note`. |
| `apply-log-complete` | sheets-write, base-write, base-schema-write | **A house invariant — one definition wherever it is declared: the apply-log is 1:1 with the plan and every entry ends in a typed disposition, whatever happened.** No Lark error, rate limit, transport failure or library bug escapes `apply()` — each becomes a typed entry rather than a traceback; `len(log.entries) == len(plan.entries)`, in plan order, on every run; a partially-applied batch with no record of what happened is not a reachable state. The ONE exception that does leave `apply()` is deliberate and carries this same complete log: `LarkApplyRefusedError`, raised when the finished log holds entries that did not land — pass `allow_partial=True` to receive that log as a return value instead. It is declared only where it is enforced — the surface column is the list. **On `sheets-write`:** An **entry-scoped** error (Lark answered about that entry — the `90204 id-not-found` class) refuses it `api-error` (a local pre-wire error: `invalid-request`) and the batch **CONTINUES**, per the sheets per-entry doctrine. A **systemic** error **HALTS** the batch — `permission-denied` (your app lacks a required **scope**: nothing landed, and a missing grant would refuse every later entry identically, so continuing would only spend one throttled call per entry on a condition that cannot clear between them) or `rate-limited` (nothing landed), or `transport-failure` / `unexpected-error` where whether it landed is **INDETERMINATE** (outcome `failed`, deliberately not mislabelled a refusal) — and **every remaining entry is logged `not-attempted`**, never silently dropped. A failure **after** the write op returned is logged `applied-unverified`: the change **is** on the sheet, its verification record is not, and the batch halts because the compare-and-swap anchor is then unknown. `ApplyLog.halt` says whether the batch stopped early and why. Paired with the **plan-time @mention check**: `dry_run` proves mention `open_id`s exist in ONE read call and refuses `unknown-mention` at plan time; a check that cannot run (no contact scope / no network) is **disclosed** as `mention_validation: "unavailable"` with the WHY — never silently skipped. **And the `docx-write` position, stated:** docx-write does not declare this invariant, which is a position rather than an omission. The docx apply path is WHOLE-BATCH-ZERO-WRITES — a batch refused by the whole-document compare-and-swap issues zero writes and never partially applies, so there is nothing to enumerate. Each entry of an ACCEPTED batch is dispatched inside a disposition boundary, so a Lark error, a transport failure or a library bug raised while applying an entry becomes a typed, logged entry and the batch's record survives it. What keeps this surface from declaring the invariant is one deliberate escape that happens BEFORE the batch: the whole-document compare-and-swap re-raises a rate-limit error rather than treating throttling as drift, so that one failure leaves apply() with no log. Nothing here promises docx the unqualified whatever-happened guarantee a declaring surface gives you. THAT IS A CLAIM ABOUT A REFUSED BATCH, AND IT IS NOT THE WHOLE STORY OF AN ACCEPTED ONE: once a batch is accepted, each inserted apply-log entry states its own measured cost and the consequence derived from it in mutating_write_calls and atomic, and the stability contract on those two keys — not this position — is what says whether that entry's content landed whole. |
| `destructive-consent-required` | base-schema-write | **A delete costs two deliberate acts, and the second one is minted from the first.** Building the plan is what shows you the loss; applying it takes a consent token minted from **that plan** and no other — `consent_to_destroy(plan)`. A plan applied without it **raises rather than deleting**, consent minted from one plan does not travel to another, and consent **cannot be minted at all** over an entry whose loss the engine could not enumerate: consent is consent to an enumerated loss, and there is nothing to consent to otherwise. It is not a flag and not a keyword you can spell for yourself. **What it does NOT cover — the Base surface loses data in THREE TIERS and this fence is one of them.** A **record** delete (`base-write`) destroys rows through the ordinary `dry_run` → `apply` path, carrying a per-row `before` and a value precondition but **no consent token** — deleting every row of a table is reachable without one. A **view** delete carries **neither**: its `loss_preview` is `None` and no token is required, because it destroys a presentation and not a cell. A **schema** delete that destroys cells — a column, a table, a batch of tables — carries **both**, and it is the only tier this contract speaks for. |
| `cross-table-loss-preview` | base-schema-write | **What a delete would take is enumerated first, across the WHOLE Base — because on a Base the damage leaves the table you named.** Deleting a two-way link column removes its mirror **in another table**, and the preview names that mirror, the table it lives in, and how many of its cells hold data. Deleting a table destroys every link pointing at it, in whatever tables those links live in, and the preview names those too — one-way links survive the delete and dangle, two-way links are removed outright along with their twin inside the doomed table, and both losses are silent — together with every **Lookup** column that mirrors the table, which carries no link into it and yet empties on every row the moment the table it mirrors is gone. A loss the scan cannot fully enumerate is a **refusal**, never a warning: if the engine cannot see everything the delete would take, the delete does not proceed. |
| `revision-guard-field-scoped-only` | base-schema-write | **The compare-and-swap covers COLUMN ops and nothing else, and the gap is disclosed rather than smoothed.** A column op rides the same client-side `table.revision` guard the record engine calls `stale-base`: the plan carries the anchor it was built on, apply re-reads it immediately before the write, and a table that moved refuses with zero writes — and it inherits that guard's own honesty about itself: every entry carries `revision_guard` reading `active` on a usable anchor and `unavailable` on a Base whose table has never moved, so the protection is never silently off. An **app-scoped** op (creating, renaming or copying a Base; creating, renaming or deleting a table) has **no revision guard at all**, and neither does a **view-scoped** one — the Base-level counter exists and moves, but three probe sessions disagreed about what it counts, so a guard built on it would refuse valid plans and pass invalid ones while looking exactly like the guard column ops really have. Those ops are verified by **read-back** instead: the renamed Base re-reads under its new name, the created table appears in the listing, the filter re-reads with the conditions that were sent — and a success code is never accepted as evidence on its own. Every plan entry states which of the two it is. |
| `historical-read-rides-the-measured-route` | docx-read | docx read: A HISTORICAL READ RIDES THE ROUTE THE PIN WAS MEASURED ON, AND NO OTHER. get_docx_content(token, document_revision_id=<n>) reads the document as of revision n through the FLAT BLOCKS LIST (GET …/docx/v1/documents/{id}/blocks) — the one route measured to honour the parameter, falsifiably: an earlier revision returned an earlier body while head returned head's in the same instant. Being MODELLED is not being HONOURED, and this contract exists because two neighbouring routes accept document_revision_id and discard it: raw_content answers head byte-identically to the plain call, and the document meta route answers head's revision_id. So a pinned read never goes through either, and it carries no revision_id or title of its own rather than handing back head's wearing the pinned revision's name — the pin you asked for is on the result as document_revision_id, and the title as of that revision is the page block's own text. THE ONE THING IT CANNOT DO, said plainly: an out-of-range revision is answered code 0 with HEAD's body and no marker, so over-range is UNDETECTABLE here and a caller who pins a bad number is silently reading head. A pin of 0 or below, or anything that is not an int, is refused LOCALLY in Lark's own words before a call is spent; -1 is Lark's head sentinel and is refused by naming the spelling that works, which is None. Reading at a NAMED EDITION is a measured refusal — no route maps an edition token to content and none maps one to a revision — so the pairing is recorded at creation time instead, by create_version. |
| `snapshot-integrity-refusal` | docx-read | docx read: A PERSISTED READ IS REHYDRATED EXACTLY OR REFUSED TYPED — NEVER REPAIRED. larkdocio.snapshot.snapshot() writes the lossless read (the raw block payloads, the document token, the document_revision_id and the api_domain the read was taken against) as one versioned, checksummed file, and load() brings it back offline with one guarantee: a load-then-project is BYTE-IDENTICAL to the projection the snapshot was taken from. A checksum mismatch, a truncated or unreadable file, an unrecognized format_version, or malformed content each raise LarkSnapshotIntegrityError naming what failed and naming the fix — RE-DOWNLOAD the document. Exactly-one-or-refuse: no repair, no salvage, no best-effort load, and NEVER a partially-rehydrated tree. THE CHECKSUM IS FOR INTEGRITY AND NOTHING ELSE: no security boundary exists between a local library and the caller, so what it answers is accidental corruption — a truncated write, a half-synced cloud folder, a corrupted disk, a hand-edited file. There is no encryption and no key material, and the digest is not a signature. THE SNAPSHOT IS OURS AND IMMUTABLE, the Markdown draft is theirs and editable, and the boundary between them is reconcile(): no mutable tree API ships and nothing accepts a caller-mutated tree. The persisted document_revision_id is what arms dry_run's STALE_DOCUMENT compare-and-swap, so a snapshot goes stale the moment somebody edits the document and the guard refusing the batch is the correct outcome; a snapshot is NOT a lock and reserves nothing. AND THE ANCHOR CAN BE ABSENT: a snapshot taken without a revision persists None, the plan's revision_guard then reads unavailable rather than active, and the compare-and-swap is not armed at all — so a caller who wants the guard takes the snapshot with the revision the read handed back. THE API DOMAIN TRAVELS TOO, inside the same digest, because it is the one fact a successor process cannot derive from the token, the revision or the blocks: a token does not say larksuite.com from feishu.cn. It is a routing fact and NOT a credential, and no app id, secret or access token is ever written into a snapshot. An artefact carrying no domain (taken without one, or written by a release older than the field) still loads and reports api_domain None rather than a guessed default, and the format_version did not move for it, so an older release still reads an artefact this one writes. Offline end to end: it reaches no endpoint and needs no credentials. |
| `caller-supplied-destination` | docx-write, sheets-write, base-schema-write, drive-folders-write, drive-files-write | **If you do not say where a new object goes, it is not created.** Every verb that makes a NEW TOP-LEVEL OBJECT — a document, a spreadsheet, a Base, a copy of a Base, a folder, an uploaded file — requires a `folder_token` you supply, and refuses **locally, before any call**, when none is given. Every spelling of *none* is refused alike, including the **empty string**, which Lark itself accepts and files in the calling application's own root. **ONE REAL TOKEN IS REFUSED TOO, AND BY TYPE RATHER THAN BY PROSE** — the application's own root, the value `DriveClient.root_folder_token()` answers — **and the guarantee's limit is stated in the same breath**: it is refused *by type*, so what this library can refuse is the value its own accessor handed you; a raw root token copied in from elsewhere arrives as an ordinary string and cannot be told apart from a folder you own. **The remedy is ORDERED, in the refusal's own words**: pass the token of a folder you own, created or were given access to — from a folder's link, or from `create_folder(name, parent_token)` — and what making one costs, before you make one: this library ships no verb that deletes a folder, so a folder created through larkdocio is permanent as far as it is concerned, and creating the same name twice under the same parent makes a second folder rather than reusing the first. The whole contract, verbatim, is `capabilities(full=True)["safety_contracts"]["caller-supplied-destination"]["summary"]`, projected from `larkdocio.common.destination`'s own constants. The reason is measured: with no destination the object lands in the application's own space, which has **no human interface at all** — it cannot be browsed, its trash cannot be listed, and a delete there **trashes rather than purges**, so the object still resolves afterwards and is reachable only through a token somebody kept. The fence picks no default place for you and makes no folder of its own to put things in — a statement about the fence, **not** a claim that no folder-creating verb ships, because one does (`create_folder`, and the destination refusal itself offers it as the second way to get a folder token); there is no opt-out and no flag restoring the old default. A create INSIDE an object you already named — a block, a table, a column, a row, a view, an anchored image, a version, a comment — is not in scope: the parent is the destination and you supplied it. The whole rule is § "Where a new object goes — you name the destination, or nothing is created". |

<!-- END CAPABILITY-MATRIX -->

**What the command line can reach — six verbs, and exactly one of them writes.** The table
above reports reachability per *flag*, which answers "can I switch this on from a shell" and
says nothing about "can I do this **task** from a shell". Here is that half:

| Console verb | Reads or writes | What it reaches |
|---|---|---|
| `larkdocio download "<url>" -o <dir>` | reads | one docx / wiki document to Markdown plus its images |
| `larkdocio folder "<url>" -o <dir>` | reads | a whole Drive folder as one Markdown document |
| `larkdocio guide` | reads nothing remote | this document, out of the installed wheel |
| `larkdocio config` | reads nothing remote | the local `.env` |
| `larkdocio mermaid` | reads nothing remote | compiles a diagram spec to Mermaid source |
| `larkdocio roundtrip pull "<url>" -o <dir>` → edit `<dir>/document.md` → `larkdocio roundtrip push -o <dir> --apply` | **WRITES** | the file-first round trip below, whole — the only console route that changes a Lark document |

**A download must never be able to mutate the document it is reading**, which is why the five
reading verbs carry no write flag and the writing one is a verb of its own. It is plan-gated
the same way the library is: `push` **always** builds and prints the plan, `--apply` means
*apply the plan you just previewed* and never *skip the preview*, and it is the only place the
command line consults the WRITE credential pair. `capabilities(full=True)["workflows"][…]["command_line"]`
is where that route is reported as data.

Read the machine-readable version any time. `capabilities()` with **no argument** returns the
**summary** — every surface, every operation name with its kind, and the scopes each surface
needs, small enough to read in one call and carrying a `reading` block that spells the next
one. The whole registry is one explicit argument away (`capabilities(full=True)`), and one
surface of it is `capabilities(surface="docx-write")`. Both are JSON-serializable dicts, so
print them as **indented JSON**:

```python
import json
import larkdocio

summary = larkdocio.capabilities()           # the SUMMARY: names, kinds and scopes
print(json.dumps(larkdocio.capabilities(), indent=2))   # ← the human-readable rendering
print(summary["reading"]["everything"])      # …and it tells you the call for all of it
print(sorted(summary["surfaces"]))           # just the surface ids
print([row["name"] for row in summary["surfaces"]["sheets-write"]["operations"]])

caps = larkdocio.capabilities(full=True)     # the WHOLE registry — more than 20× bigger
print(caps["surfaces"]["docx-write"]["content_constraints"]["floor"])  # what you can CREATE
print([row["name"] for row in caps["surfaces"]["sheets-write"]["operations"]
       if row["kind"] == "lifecycle"])       # make / destroy a whole FILE
print(larkdocio.guide())                     # this guide's section index
print(larkdocio.guide(full=True))            # …and its whole text, if you want all of it

# WILL THE THINGS IN MY DOCUMENT SURVIVE THE READ — one row per docx block type, each
# answering all three questions: handled? what does it emit? how lossy is that emission?
support = caps["surfaces"]["docx-read"]["block_read_support"]
print([row["name"] for row in support["types"] if row["lossy"]])   # not whole in the Markdown
callout = next(row for row in support["types"] if row["name"] == "callout")
print(callout["handled"], callout["lossiness"], callout["emits"])
print(support["lossiness_vocabulary"][callout["lossiness"]])   # what that state MEANS
print(support["unlisted_type"])              # …and a type Lark adds after this release
```

**The block-type read projection** is the answer to *"will my callouts / images / boards
survive the read?"* — the one capability fact the op list and the creatable floor both leave
out, because both are about *writing*. `handled` is the live handler registry (not a list that
can go stale); `emits` and `lossiness` are the reader's own per-type facts. It is
**read-only**: no row carries write status, since a type's creatability is the floor's subject
and can change without changing what a read does with it.

Four write surfaces carry `lifecycle` **rows** (`docx-write`, `sheets-write`,
`base-schema-write` and `drive-files-write`): the call that brings a file into existence, the one
that destroys it, or both (`create_spreadsheet` / `delete_spreadsheet`; `create_document` /
`delete_document`; `delete_base`; the files leg's `delete`). The other write surfaces carry none. They sit in the same `operations` list as everything
else the surface can do — one key, so nothing is discoverable only by a reader who knew to look
for a second one — and their `kind` is what says they are **not** plan-gated write ops: a
file's lifecycle is not something `dry_run` previews or `apply` performs, which is why
§ "The disposables doctrine" names it as its own thing.

---

## The Base surface, all of it

The Base surface is the widest one this library carries, and it grew fastest. This page is the
**map**: one place that answers *"which object answers my question, and where do I read about
it?"* — so nothing here has to be found by walking the installed package.

It makes **no capability claim of its own.** Every operation below is one `capabilities()`
reports, and a test holds the two equal in both directions for the call sites of kind
`operation`: a row for something the library does not do fails the suite, and so does an
operation with no row. The Base call sites of the other kinds — the `leg` rows
(`read_hierarchy`, the attachment-media legs, `migrate_field_type`) and the `lifecycle` row
(`delete_base`) — are not on this map; `capabilities(surface="base-...")` lists them.

### Question → the object that answers it

| Your question | The object that answers it | Import path |
|---------------|---------------------------|-------------|
| *Where do this column's values come from?* (Lookup / Formula provenance) | `computed_columns(fields, records)`, and `table.computed_columns` on a structured read | `from larkdocio.base import computed_columns` |
| *What are this column type's **column shapes** — which `property` keys it takes, and which `field_type` goes with which `ui_type`?* | `FIELD_PROPERTY_SHAPES[ui_type]` — `.field_type`, `.keys`, `.required` | `from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES` |
| *Do any of my link columns point at a table that is gone?* (dangling references — free, no extra call) | `dangling_link_columns(fields)`, and `table.dangling_link_columns` | `from larkdocio.base import dangling_link_columns` |
| *What are the linked records actually called?* (link names — an opt-in, costed read) | `read_base(url, resolve_links=True)`, then `document.link_resolution` | `from larkdocio.base import read_base` |
| ***Files** — how do I get one into (or out of) an attachment cell?* | `BaseMediaClient.upload` / `.download`, then `verify_round_trip` | `from larkdocio.base.media import BaseMediaClient` |
| *How many API calls will my import cost, and how do I batch it?* | `dry_run(draft, records_per_call=N)` → `plan.api_call_count`, `entry.call_index` | `from larkdocio.base.apply import dry_run` |
| *What did the wire actually say for this cell?* (raw values, before rendering — **on a READ**) | `read_base(url, retain_raw=True)`, then `document.tables[i].rows[j].raw_fields` — a plain mapping | `from larkdocio.base import read_base` |
| *…and the same question on the object the WRITE engine takes* | `snapshot_table(...)`, then `snapshot.records[j].raw(field_name)` / `.raw_as_dict()` — the loud accessors | `from larkdocio.base.model import snapshot_table` |
| ***Link me straight to this record*** — a shareable URL for specific rows (an opt-in, costed read; per-selection, never a whole table) | `record_permalink(app_token, table_id, [record_id, …])`, then each result's `.url` / `.state` | `from larkdocio.base import record_permalink` |
| ***Open this Base on that table (or that view, or that record's card)*** — a link built from ids you already hold, **costing no API call** | `table_url(base_url, table_id)` / `view_url(base_url, table_id, view_id, record=None)` | `from larkdocio.base import table_url, view_url` |
| *How do I read the parent/child structure of a table?* | `read_hierarchy(...)`, `hierarchy_config(...)` | `from larkdocio.base import read_hierarchy` |
| *How do I change a column's type without losing the data?* | `plan_field_migration(...)` / `apply_field_migration(...)` | `from larkdocio.base import plan_field_migration` |
| *Which scopes does any of this need?* | the permissions section of this guide, generated from the registry | `from larkdocio import permissions` |

**TWO OBJECTS HOLD A BASE'S ROWS, THEY SPELL THINGS DIFFERENTLY, AND THE ROW ABOVE IS SPLIT IN
TWO BECAUSE OF IT.** A sentence naming both at once is how an `AttributeError` gets written down
as documentation, so here they are apart:

| The object | Where it comes from | Its rows are | One row's raw wire body is |
|---|---|---|---|
| `BaseTableRead` — the **read model** | `read_base(url, retain_raw=True).tables[i]` | **`.rows`** (of `BaseRow`) | **`.raw_fields`** — a mapping, or `None` when the read did not retain raw |
| `BaseTableSnapshot` — what the **write engine** takes | `snapshot_table(...)` | **`.records`** (of `SnapshotRecord`) | **`.raw_fields`**, plus the loud accessors **`.raw(field_name)`** / **`.raw_as_dict()`** |

Read the differences rather than the similarities: **the read model has `.rows` and no `.raw()`
method** (its `raw_fields` is an attribute you index yourself), and **the snapshot has `.records`
and both** — the attribute *and* the two accessors that refuse instead of answering. There is no
`.records` on the read model and no `.raw()` on a `BaseRow`; asking for either is the
`AttributeError`, not a permissions problem or a flag you forgot.

**The refusal the accessors raise is `RawNotRetained`, and it is imported from the module that
defines it** — `from larkdocio.base.model import RawNotRetained` — not from `larkdocio.base`,
which does not re-export it. It fires when a snapshot built from a read taken **without**
`retain_raw=True` is asked for a raw value: `.raw_fields` is `None`, and `.raw(...)` /
`.raw_as_dict()` refuse rather than hand back an empty dict that would read as *"the cells were
empty"*. A typo in the field name is the **other** error, `UnknownField`, from the same module.

### Linking to a record — `record_permalink`

The sharpest deep-link ask — *"link me straight to this record"* — is the one Lark actually
supports, at the **record** level. `record_permalink(app_token, table_id, record_ids)` returns
a `RecordPermalink` for each id you name, and a resolved one carries a `.url` of the form
`https://<host>/record/<opaque>`.

Four things are worth knowing before you plan:

- **It is fetched, not minted.** The permalink's opaque token is server-side; it is not
  anything you can build from a `record_id`. So this is a read, and it **costs calls** — **one
  `records/batch_get` call per `BATCH_GET_MAX_IDS` ids** (the same ceiling `batch_get_records`
  documents), batched and de-duplicated for you.
- **Per-selection, never a whole table.** The function takes a **sequence of record ids** and
  nothing else — there is no table-shaped input, no `all=True`, and no convenience that walks a
  table's rows for you. To permalink some rows, read the table, choose them, and pass *their*
  ids. This is deliberate: the cost that matters is also your reader's attention.
- **Absence is typed, never an error.** Each result carries a `.state` — `resolved` (a `.url`
  is present), `unminted` (the record was read but Lark returned no permalink), `absent` (no
  such record in the table), or `forbidden` (the read was refused for that id). A missing
  permalink is a value the record does not have, not an exception, and `.url` is `None` for
  exactly one reason — the *which* lives in `.state`, never overloaded onto `None`. Every state
  has a plain-language `.note`.
- **Stability — measured durable at week scale, and scoped to exactly that.** The permalink was
  measured **byte-identical across sessions** on 2026-08-07/08 (re-fetched with a fresh bearer,
  hours apart), and then **byte-identical again a week later, on 2026-08-15** — five links, five
  identical at seven and eight days, on one tenant, through this same `record_permalink` /
  `records/batch_get` read, with the records intact throughout. The ceiling is part of the
  claim: durability beyond that week, on another tenant, or for a record somebody deletes is not
  yet measured, so this still makes no claim of permanence — treat a permalink as an address
  measured stable at week scale, not a forever-guaranteed one. And a durable address is **no
  promise the content behind it is fetchable**: attachment permalinks came back byte-identical
  while `GET drive/v1/medias/<token>/download` on them answered `HTTP 404` with an empty body.

**Linking to a TABLE or a VIEW — minted, not fetched, and it costs nothing.** The record
permalink above is *fetched*; the other two Base addresses are *built*, offline, from ids you
already hold. `table_url(base_url, table_id)` returns
`https://<tenant-host>/base/<app_token>?table=<table_id>` and
`view_url(base_url, table_id, view_id)` adds `&view=<view_id>`; pass `record=<record_id>` to
`view_url` and the record's card opens too. Both make **zero API calls**, so they need no
scope and cost no quota. What they need is the **Base's own URL**: the tenant host is an
**input**, read off that URL and never derived from the API domain — a working link lives on a
tenant subdomain the API domain cannot produce — and never invented. A hostless URL, a
non-`https` URL, a URL that is not a `/base/<token>` link, a bare `app_token`, or an empty id
is a refusal, not a default. Nothing is resolved or validated: an id that does not exist yields
a link that does not open. Here is exactly how far the click evidence goes, so the claim is
never read wider than what was measured:

> A Base table/view deep link (`…/base/<app_token>?table=<table_id>&view=<view_id>`, and with a record `&record=<record_id>`) IS mintable, offline: `larkdocio.base.table_url(base_url, table_id)` and `larkdocio.base.view_url(base_url, table_id, view_id)` build one from the Base's own URL and ids a Base read already returns, and make zero API calls. Here is the edge of the evidence, so the claim is never read wider than what was measured. MEASURED: the grammar was clicked by hand on 2026-08-17 in the Lark web client, on one tenant, on one Base. The navigating click was made against a NON-FIRST table, and that detail is the measurement rather than a footnote — on that Base's first table the target view is its only view, so a correct navigation and a default landing are indistinguishable, and an earlier click against exactly that target was read as "does not navigate" and was a false negative. Against the non-first table the Base opened directly on the named table and view. A second click carried `&record=<record_id>` and the record card opened. The ids those links were built from were checked alive and byte-identical ten days after they were first read — tables listed, views listed, the record fetched — so no id had been re-minted underneath the reading. UNMEASURED, and therefore neither refuted nor supported: the mobile client, the desktop app client, any other tenant, any other Base, and any span longer than those ten days. Whether such a link navigates is a rendering behaviour of the Lark client, so no API call can widen this measurement — only another click can. FOR A RECORD, PREFER `larkdocio.base.record_permalink`: that address is minted by Lark itself rather than composed here, and it was measured byte-identical across a week (read 2026-08-07/08, re-read 2026-08-15). A constructed `record=` link is the answer for the ids you already hold, not the better address.

```python
from larkdocio.base import table_url, view_url

base_url = "https://your-domain.larksuite.com/base/BaseTOKEN123"
assert table_url(base_url, "tblvHhs6KA9QYNCo").endswith("?table=tblvHhs6KA9QYNCo")
assert view_url(base_url, "tblvHhs6KA9QYNCo", "vewHtny0oX").endswith(
    "?table=tblvHhs6KA9QYNCo&view=vewHtny0oX")

# The host is an INPUT: whatever tenant host you pass is the one that comes back.
assert view_url(base_url, "tbl1", "vew1").startswith(
    "https://your-domain.larksuite.com/")

# A bare app_token carries no host, so it is refused rather than defaulted.
try:
    table_url("BaseTOKEN123", "tbl1")
except ValueError as refusal:
    assert "tenant host" in str(refusal)
```

### Every operation, and where it is taught

Five surfaces. `read` and `records` are the two you reach for first; `schema` is everything that
changes a Base's *shape*; the view family is its own thing because a view write is verified by a
read-back rather than by a response code.

| Operation | Surface | What it is | Where it is taught |
|-----------|---------|------------|--------------------|
| `read_base` | `base-read` | the whole Base as objects — tables, fields, rows | **Recipe: read a Base to Markdown** |
| `read_base_markdown` | `base-read` | the same read, rendered straight to Markdown | **Recipe: read a Base to Markdown** |
| `get_app` | `base-read` | the Base's own metadata, including the time zone every date renders in | **Recipe: read a Base to Markdown** (the five calls a read makes) |
| `list_tables` | `base-read` | the tables, each with the `revision` anchor every write compares against | **Recipe: the Base write handshake** |
| `list_fields` | `base-read` | one table's columns, in schema order | **Recipe: read a Base to Markdown** |
| `search_records` | `base-read` | one table's rows, walked to exhaustion | **Recipe: the Base write handshake** |
| `batch_get_records` | `base-read` | **named** records from one table, in one call — what link resolution spends its budget on | **Recipe: resolve link columns to names — and find the ones pointing at a deleted table** |
| `record_permalink` | `base-read` | a **shareable URL** for named records — fetched, per-selection, typed absent state | § *Linking to a record — `record_permalink`* |
| `list_views` | `base-read` | the views a table has (names and types; no `property`) | **Recipe: create, configure and delete a view — hidden columns ARE settable; grouping and a saved sort are NOT** |
| `get_view` | `base-read` | one view **with** its `property` — the only route that carries it | **Recipe: filter a Base two ways — the rows a read returns, and the rows a person sees** |
| `comments` | `base-comments-read` | a Base's comments, through the comments surface with `file_type="bitable"` | **Recipe: read the comments on a document** |
| `deep_read_embedded_base` | `base-embedded-deep-read` | an opt-in deep read of a Base **embedded in a document** | § *Choose your level* (opt-in; the default docx read is byte-identical without it) |
| `create_record` | `base-write` | add one row | **Recipe: the Base write handshake** |
| `update_record` | `base-write` | change one row | **Recipe: the Base write handshake** |
| `delete_record` | `base-write` | remove one row | **Recipe: the Base write handshake** |
| `batch_create_records` | `base-write` | add rows in one call — the import verb | **Recipe: price a bulk import before you send it** |
| `batch_update_records` | `base-write` | change rows in one call | **Recipe: the Base write handshake** |
| `batch_delete_records` | `base-write` | remove rows in one call | **Recipe: price a bulk import before you send it** |
| `create_app` | `base-schema-write` | make a new Base | **Recipe: create, rename and copy a Base (the structural handshake)** |
| `rename_app` | `base-schema-write` | rename a Base | **Recipe: create, rename and copy a Base (the structural handshake)** |
| `copy_app` | `base-schema-write` | clone a Base — the one **asynchronous** operation, with a bounded settle | **Recipe: create, rename and copy a Base (the structural handshake)** |
| `create_table` | `base-schema-write` | add a table | **Recipe: create, rename and copy a Base (the structural handshake)** |
| `batch_create_tables` | `base-schema-write` | add tables in one call | **Recipe: create, rename and copy a Base (the structural handshake)** |
| `rename_table` | `base-schema-write` | rename a table | **Recipe: create, rename and copy a Base (the structural handshake)** |
| `delete_table` | `base-schema-write` | remove a table — **destructive**: needs an enumerated loss preview and a consent token | **Recipe: create, rename and copy a Base (the structural handshake)** (step 5 — the consent gate, and the module the delete verbs live in) |
| `batch_delete_tables` | `base-schema-write` | remove tables in one call — **destructive**, same fence | **Recipe: create, rename and copy a Base (the structural handshake)** (step 5) |
| `create_field` | `base-schema-write` | add a column | **Recipe: add a column, and change one's name** |
| `update_field` | `base-schema-write` | rename a column or edit its `property` — never its kind | **Recipe: add a column, and change one's name** |
| `convert_field` | `base-schema-write` | change a column's kind, for the pairs a capture carries | **Recipe: add a column, and change one's name** |
| `delete_field` | `base-schema-write` | remove a column — **destructive**, same consent fence | **Recipe: create, rename and copy a Base (the structural handshake)** (step 5, worked end to end); **Recipe: change a column's type (the guided migration — do NOT hand-roll this)** spends the same op as its own last step |
| `create_view` | `base-schema-write` | make a view — **barely configured**; see the recipe for which four knobs are yours | **Recipe: create, configure and delete a view — hidden columns ARE settable; grouping and a saved sort are NOT** |
| `update_view` | `base-schema-write` | patch a view: its name, its filter, its hierarchy field, and the columns it **hides** (`[]` clears). Grouping and a saved sort are still no knob | **Recipe: create, configure and delete a view — hidden columns ARE settable; grouping and a saved sort are NOT** |
| `delete_view` | `base-schema-write` | remove a view (a table keeps a floor of one) | **Recipe: create, configure and delete a view — hidden columns ARE settable; grouping and a saved sort are NOT** |

Two things this map deliberately does not carry. There is **no** operation that reads or writes
a Base's sharing — larkdocio does not control a Base's shareability and exposes no path to it —
and there is **no** grouping and **no** view-sort parameter anywhere, because their effects are
not observable through Lark's API (see the views recipe). A view's **hidden columns** are the one
that left that list: `update_view` sets them, `[]` clears them, and the effect is observable on
both axes (see the same recipe).

**Column / field GROUPING has no API route.** This is grouping COLUMNS in the table UI — the
feature you may be working around today with column-name prefixes like `P0 - Not started`.
It is **NOT** view **record** grouping (rows bucketed under a field's value), which is a
different feature with a confusingly similar name and is classified in **Recipe: create,
configure and delete a view — hidden columns ARE settable; grouping and a saved sort are
NOT**. Conflating the two leads to the wrong conclusion from either measurement. Every shape
that could plausibly carry a column group was tried: the table-level write route answers "the
request body cannot be empty" (`1254001`) for all **7** group-shaped keys tried, byte-identical
to an invented key that means nothing; the field-level write route accepts all **8**
group-shaped keys tried with a success code and **stores nothing** — attributably, because
each attempt also carried a genuine rename that DID land, so the acceptance is not a
coincidental no-op; **5** dedicated endpoint spellings all answer **404**, with no envelope at
all; and a column's own read model carries **no group concept in any spelling** — its keys are
exactly `field_id, field_name, is_extend, is_primary, is_synced, property, type, ui_type`. Not
tried: a user-scoped credential (every attempt here used a tenant-scoped one); any
undocumented product-internal endpoint the web client itself calls; the Base dashboard,
automation and form families; copying an app from a template that already has groups; and
whether a non-grid view type exposes a column-group vocabulary a grid view does not — each
unmeasured, not refuted. **Scope:** this describes what was measured against one tenant with a
tenant-scoped credential — it grounds *"there is no column-group route for that credential"*,
not *"Lark cannot group columns"*; the product's own UI plainly can.

**Column ORDER is settable — once, at table creation, and by no route measured afterward.**
`create_table`'s own `fields=[…]` array **decides the column order**: proved with a reversed
control, two tables created with the same three names in opposite array orders, each reading
back in its own array's order. After creation, no route places or moves a column: **12**
create-time position-shaped parameters (an index, a position, an insertion point named by an
existing column, and a query-string variant) are all accepted with a success code and all
**appended at the end**, identical to an invented-key control; **5** update-time equivalents
are accepted with a success code, the requested rename lands, and the order stays
**unchanged**; and **6** dedicated move/reorder routes all answer **404**. So the honest
statement is not *"column order is not settable"* — it is *"column order is settable **once**,
at table creation, through `create_table(..., fields=[…])`; after that a column cannot be
placed or moved by any route measured."* Not tried: a user-scoped credential; the web client's
internal endpoints; a non-grid view type's own property vocabulary — this one matters, because
a kanban or gantt view is exactly where a field-order property would plausibly live, and only
a grid view was checked; deleting and re-creating columns to force an order, which is a
**data-destroying rebuild**, not an ordering route, and was deliberately never tried; and
copying an app followed by re-authoring.

**AND THE ROUTE THAT SETS THE ORDER IS THE ROUTE THAT REFUSES TWO COLUMN KINDS — read that
sentence twice, because the two facts are documented in two places and the collision only exists
where they meet.** `create_table(..., fields=[…])` will not author a **`Checkbox`** or a
**`Rating`** (Lark answers *"Unsupported field type."* and creates **nothing at all**; the
refusal is local, before any call). So a table that needs one of those kinds **at a chosen
position** cannot have both: adding the column later with `create_field` **appends** it, and
**the position is forfeited permanently** — that is what the enumeration above means in practice.
**Append order IS display order**, measured with an anti-alphabetical control, so the workaround
is real and it is a demotion rather than a cure: author the orderable prefix with `fields=`, then
`create_field` the rest in display order. The whole story, with the measurement and the cost, is
in **Recipe: create, rename and copy a Base (the structural handshake)**, under its paragraph
headed *"THE COLLISION, STATED ONCE AND PLAINLY"*.

---

## The two batch contracts — docx refuses the whole batch, sheets disposes per entry

Both write surfaces run the **same** `dry_run` → `Plan` → `apply` gate, and then they part
company on what a **batch** means. Both shapes are deliberate; neither is a bug in the other's
shape, so read the one for the surface you are writing to:

* **docx = whole-batch, zero writes on refusal.** Document drift refuses the **ENTIRE** batch
  with `stale-document` and **zero writes issued** — partial application is not a reachable
  outcome there, and the engine never re-locates an anchor to accommodate a document that
  moved.
* **sheets = per-entry compare-and-swap, partial application is possible, and it is fully
  disclosed in the apply-log.** An entry that refuses does not stop its neighbours from
  applying — and the log is the record that makes that safe.

**Several inserts into the SAME parent, in one docx batch, are safe.** Each insert lands
immediately beside **its own** reference block, in the position you asked for, whatever order
the requests were submitted in — the engine reads the parent's live child order at write time,
so an insert that has already landed cannot push a later one out of place. (This was **not**
true in earlier releases: a same-parent multi-insert batch silently landed every insert after
the first one position early per earlier insert above it, with a clean plan and a clean apply
log. If you carry a workaround for that — one insert per batch with a fresh read between, or
submitting same-parent inserts in **descending** index order — you can drop it. Nothing else
changes: the only caller affected is one that was relying on the misplacement.) This is about
**position**, and it does not widen `one-tree-one-batch`, which is about **resolution**: a
batch still cannot anchor on content its own earlier entry creates.

**One thing on the plan is advisory, and says so.** A resolved insert's
`insertion_point.index` is the ordinal the reference occupied **when you planned** — the
plan's commitment is the *position beside the reference* (`insertion_point.position` +
the entry's reference block), which is what `apply()` guarantees. In a batch with two or more
inserts into one parent, the first landing write moves every later ordinal, so `index` cannot
also predict the final slot; making it predictive would mean re-planning inside `apply()`,
and an approved plan would stop describing what will happen.

| Question | `docx-write` | `sheets-write` |
|----------|--------------|----------------|
| What is the unit of atomicity? | the **whole batch** for document drift (`STALE_DOCUMENT`), plus a per-entry re-validation (`STALE_ANCHOR`) | the **entry** — a compare-and-swap re-read immediately before each write (`stale-sheet` tier 1 + tier 2) |
| Can a batch apply partially? | **not on document drift** — `stale-document` refuses every entry with **zero writes**. A per-entry refusal (`stale-anchor`, an ambiguous quote) is still a per-entry skip, and the rest of the batch applies | **yes** — any entry may refuse while the entries around it apply. That is the deliberate doctrine, not a gap |
| How do I learn what happened? | the apply-log, **one entry per plan entry, in plan order, on every run**: `applied` / `inserted` / `deleted` / `commented` / `comment-removed` when the change landed, `applied-unverified` when a write **returned** and a step after it failed (it landed; only its verification record is incomplete), `refused` / `failed` / `not-attempted` when it did not — plus `ApplyLog.halt` / `.indeterminate` / `.not_attempted`. Every non-landing entry carries a typed `refusal` with a mandatory `detail` | the apply-log, **1:1 with the plan**: `len(log.entries) == len(plan.entries)`, in plan order, on every run — plus `ApplyLog.halt` / `.halted` / `.indeterminate` / `.not_attempted` |
| Is log completeness a declared contract? | **no** — `apply-log-complete` is not declared on docx-write (it is declared on `sheets-write`, `base-write` and `base-schema-write`), and the docx position is stated rather than left to be inferred: a docx batch refused by the whole-document compare-and-swap issues **zero writes** and never partially applies, so there is nothing to enumerate. Each entry of an *accepted* batch **is** dispatched inside a disposition boundary, so a Lark error, a transport failure or a library bug raised while applying an entry becomes a typed, logged entry rather than a traceback. What keeps the surface from declaring the invariant is one deliberate escape **before** the batch: the whole-document compare-and-swap re-raises a rate-limit error rather than treating throttling as drift, so that one failure leaves `apply()` with no log | **yes** — `apply-log-complete`: **no Lark error, rate limit or transport failure escapes `apply()`** (each becomes a typed entry), and every entry ends in a typed, logged disposition. The one deliberate raise — `LarkApplyRefusedError`, on a log that holds entries which did not land — carries that same complete log |
| What arms the guard? | `dry_run(..., document_revision_id=docx.revision_id)` for `STALE_DOCUMENT`; `STALE_ANCHOR` is always on | tier 1 = the spreadsheet `revision` **when available**, tier 2 = each entry's `value_precondition`, always — both disclosed on the plan |

### The sheets disposition vocabulary — what a per-entry outcome can be

Every entry of a sheets `apply()` ends in **exactly one** typed disposition, always. These are
the shipped names (`larkdocio.sheets.plan.Refusal` + `larkdocio.sheets.disposition`); the
scope decides whether the batch keeps going:

| Refusal reason | Scope | Outcome | Landed? | The batch |
|----------------|-------|---------|---------|-----------|
| `unknown-mention` | plan time — refused by the previewer | — (nothing is applied for it) | no | never started for this entry: fix the `open_id` and re-plan |
| `api-error` | `entry-scoped` | `refused` | no | **continues** to the remaining entries |
| `invalid-request` | `entry-scoped` | `refused` | no | **continues** to the remaining entries |
| `permission-denied` | `systemic` | `refused` | no | **halts**; your app lacks a required **scope**, which would refuse every later entry identically — so the batch stops instead of spending one throttled call per entry on a condition that cannot clear between them. The `detail` relays Lark's own answer (the missing scope, its verbatim `code`/`msg`, the console link when Lark sends one, and which credential pair made the call). Grant it in the Lark console, then re-`dry_run` and apply the remainder |
| `rate-limited` | `systemic` | `refused` | no | **halts**; every remaining entry is logged `not-attempted` |
| `transport-failure` | `systemic` | `failed` | **indeterminate** | **halts**; the call never got an answer, so whether it landed is unknown — and the log says so |
| `unexpected-error` | `systemic` | `failed` | **indeterminate** | **halts**; an un-modelled failure is never assumed entry-local |
| `unverified-write` | `systemic` | `applied-unverified` | **yes** | **halts** — the change **is** on the sheet, its verification record is not |
| `not-attempted` | after a halt | `not-attempted` | no | already stopped: this entry was never attempted, and says so rather than being absent |

**The complete `outcome` vocabulary is six values** — `applied` (landed and verified) ·
`applied-unverified` (**landed**, verification record incomplete) · `stale` (the
compare-and-swap tripped — no write) · `refused` (did not land) · `failed`
(**indeterminate** — deliberately *not* called a refusal, because the engine does not know) ·
`not-attempted` (the batch had already halted).

**The plan discloses its @mention check too.** `dry_run` proves mention `open_id`s exist in
one read call, so the id-not-found class refuses at plan time: `mention_validation` is
`active` (the check ran), `unavailable` (it could not run — no contact scope, no network),
or `not-applicable` (the batch carries no mention), always with the WHY in
`mention_validation_detail` and the ids in `mention_validation_ids`. A check that cannot run
is **disclosed, never silently skipped**.

---

## Where refusals happen, and when — the three channels

This library refuses rather than guesses, everywhere. What is worth knowing **before** you write
a generic *"apply this plan"* wrapper is that a refusal reaches you on **one of three channels**,
and the three fire at three different moments in the handshake. Each is well-behaved on its own;
what costs a consumer a round of trial-and-error is meeting them one at a time and assuming the
one they met is the only one. So, once, the whole taxonomy:

| Channel | What it looks like in your code | When it fires | What it costs | How you detect it |
|---------|--------------------------------|---------------|---------------|-------------------|
| **1. Op-build exception** | the **op constructor itself raises** — `create_field(...)` throws and you never hold a request to put in the list. The refusal classes are named and typed (`UnauthorableFieldError` / `UncapturedFieldPairError` for a kind or `(field_type, ui_type)` pair no registry carries, `UncapturedFieldPropertyError` for a property shape no capture covers, `RefutedFieldAuthoringError` for e.g. a Formula expression that references other columns, `UncapturedConversionError` for a `convert_field` pair, `SelectOptionIdRequiredError` for an `update_field` on a select column whose body would re-mint the option ids and orphan the cells) | while you are **building** the op list — before any plan exists | **nothing.** No plan, no API call, no state anywhere | `try` / `except` around the constructor. Catch `LarkConfigError` to cover the family, or the specific class when you want to branch. The message names the accepted trade-off and what to do instead |
| **2. Plan-entry refusal** | the plan comes back **whole**, and one of its entries carries `entry.refusal is not None` (with `entry.op` naming which). The op was legal to build and is **not** legal to apply here — a loss the engine could not fully enumerate, a destructive request with no read client to scan with, an @mention id the previewer could not find | at **`dry_run`** time — the preview, which costs **zero write calls** | the plan's own read calls, if it made any (a destructive scan does; most previews do not) | walk `plan.entries` **before** you apply: `if entry.refusal is not None: … entry.refusal.reason`. This is the loop the recipes all show, and the one a wrapper most often forgets |
| **3. Apply-time refusal, surfaced by read-back** | an apply-log entry whose `outcome` is **not** `applied` — `dropped` (the call was accepted and the read-back did not show the change), `refused` (did not land), `failed` (**indeterminate** — the engine does not know), `applied-unverified` (it **did** land; the verification record is incomplete) — with the reason in `entry.refusal.detail`, including the server's own `code`/`msg` when the refusal is Lark's | during **`apply`**, after the call went out | the calls already sent. On the sheets surface a neighbour may have applied while this entry refused; on docx a whole-document drift refuses everything with **zero** writes | **it raises**: `LarkApplyRefusedError` (from `larkdocio.errors`) whenever the finished log holds an entry that did not land, carrying `err.log`, `err.applied` and `err.refusals`. Pass `allow_partial=True` to get the log back as a return value instead, and then walk `log.refusals` yourself — `outcome == "applied"` is the only success, and the log is 1:1 with the plan on the sheets surface (`apply-log-complete`) |

**Channel 3 RAISES by default — and that is the one behavior in this section that changed.**
A plan-gated `apply()` whose finished log holds **any** entry that did not land raises
`larkdocio.errors.LarkApplyRefusedError` instead of returning. It is the same log either way:
the exception carries `err.log` (the whole record), `err.applied` (the entries that landed —
nothing is rolled back, ever) and `err.refusals` (one `{"reason", "detail"}` per refused entry,
in log order), and its message names the count both ways — *"3 of 5 entries applied; 2
refused"*. **Which entries apply and which refuse did not change**; only return-vs-raise did.
The reason is a measured one: a caller who never read the log ended runs believing every entry
applied, twice, and both times the library had recorded the refusal faithfully.

**Keeping the old behavior is one argument: `allow_partial=True`.** It is the **same spelling on
every plan-gated apply this library ships** — `larkdocio.write.apply`, `larkdocio.sheets`,
`larkdocio.base.apply` and `larkdocio.base.schema_apply` — and with it `apply()` returns exactly
what it always returned, refusals and all. Use it when your code already reads the log; catch
`LarkApplyRefusedError` and read `err.log` when it does not. Either way you get the same
`ApplyLog`, which **iterates** (`for entry in log:`) and answers **`len(log)`**. Both shapes are
shown, runnable, in § "Recipe: the docx write handshake" and § "Recipe: copy this — the
end-to-end update script".

Two examples, so the shape is concrete rather than abstract. A Formula column that references
another column never gets past channel 1 — `create_field` raises in your own process. A view
filter naming a SingleSelect **option** by its label sails through channel 2 and is refused on
channel 3, by Lark's own error, because nothing local knows the option ids until something reads
them.

**The three are deliberately NOT unified, and the timing differences are the reason.** A refusal
belongs on the earliest channel that can *honestly* produce it: a shape the library can judge
from its own registries belongs in the constructor, where it costs nothing; a loss that needs a
scan of the Base belongs in the plan; and a truth only the server holds cannot be known before
the call, so pretending otherwise would mean guessing. Collapsing the three into one late channel
would make every refusal cost an API call; collapsing them into one early channel would require
the library to invent server state. The three are not unified — the timing differences are
justified — only the taxonomy is named once.
This section is that naming — it **describes** the three channels and changes none of them.

---

## Authoring from Markdown — the dialect, and what it cannot express

`compose(markdown)` compiles a Markdown fragment into the ordered typed content an
`InsertRequest` carries (`compose_insert(markdown, reference)` pairs the two in one call).
**It produces requests, never writes** — no client, no credentials, no transport — so
composed content still reaches Lark only through `dry_run` → `Plan` → `apply`. The recipe is
[below](#recipe-author-a-markdown-fragment-into-a-document).

**The dialect is exactly what larkdocio's own reader emits** — not "Markdown" in general. It
is **CommonMark** plus the two **GFM** extensions the renderer produces (pipe tables,
`~~strike~~`), with the reader's escaping rules **read in reverse**: an **escaped
metacharacter** (`\#`, `\-`, `\*\*`, `1\.`) is **literal text**, never structure. That
symmetry is what makes the round-trip provable — the reader's Markdown for blocks composed
from `X` composes to the same content as `X` — so the safest fragment to author is one the
reader itself could have produced.

**The round-trip is a property of the CONTENT, not of the bytes.** For a fragment already in
the reader's own form the read-back is byte-identical; for anything else the reader applies its
own documented normalizations — a **tight** list comes back **loose** (a blank line between
items), and a space-indented nested item comes back **tab**-indented. Nothing is lost either
way, but it means **verifying your own write by string comparison fails on every list you
author**. Compare with **compose-equivalence, not string equality** — `compose(authored) ==
compose(read_back)` — and see § "Recipe: verify what you authored" for the worked version.

**A FRAGMENT BIGGER THAN ONE CALL — the 50-block cap, and the shape it refuses in.**
`compose()` will compile a fragment of any size; what is bounded is the **request**. One
`InsertRequest` carries at most `larkdocio.write.MAX_CHILDREN_PER_CALL` — **50** — blocks,
because docx v1's `create_children` creates **1–50** blocks per call and one sibling group is
one call (the same cap bounds a list item's `children`). Hand a wider tuple to `InsertRequest`
and it is **refused at construction: a plain `ValueError` raised by the constructor, before
`dry_run` ever sees the request** — deliberately a different shape from the typed refusals a
`Plan` carries, because those describe a request the engine understood and would not guess at,
while this one is a request that cannot be sent at all. Nothing is truncated and nothing is
silently split for you. The way over it — split into groups of ≤50, anchor each batch to what
the last one created, then read the order back — is § "Recipe: author more than one call's worth
of blocks".

<!-- BEGIN AUTHORING-DIALECT (drift-guarded vs NewBlockKind + NOT_EXPRESSIBLE_CONSTRUCTS;
     see tests/test_authoring_discovery.py, in the source repository) -->

**What composes** — one row per creatable kind
(`capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]["creatable_kinds"]`):

| Kind | The Markdown you write | Creates |
|------|------------------------|---------|
| `heading` | `# H` … `###### H`, or setext (`H` then `===`) | heading1..heading6 (Lark stores levels 1–9; Markdown only reaches 6, so H7–H9 are authorable via `NewBlock.heading()` but not from MD — and the reader's marker for them is **capped** at `###### `, so an H7–H9 you author is **read back as H6**: see the heading-level note below) |
| `paragraph` | a plain paragraph (a soft break stays a newline in the text) | text (2) |
| `bullet` | `- x` / `* x` / `+ x`, nested by a tab or by spaces | bullet (12) |
| `ordered` | `1. x` / `1) x` | ordered (13) |
| `todo` | `- [ ] x` / `- [x] x` | todo (17). **The checkbox state is editable in place:** flip `- [ ]` to `- [x]` in an edited block-identity projection and the bit moves, through the same plan-gated route as any other change — or create the item in the state you want with `NewBlock.todo(text, done=True)`. What an edit of an existing todo does **not** carry is every other property of the block, and asking for one is a typed refusal rather than a green log: read `no-block-property-edit-beyond-text` in the absence register below |
| `code` | a fenced block (```` ``` ```` or `~~~`) with a language token | code (14), language from `larkdocio.langs.supported_code_languages()`. **The body is VERBATIM in both directions** — every line's leading whitespace (spaces and tabs), whitespace-only lines, trailing whitespace and blank edge lines survive the read, so an indented snippet or ASCII art round-trips byte-for-byte; pass `language=None` for a bare fence when the content is not code |
| `quote` | `> x` (one paragraph's worth of lines) | quote (15) |
| `table` | a GFM pipe table (`<br>` in a cell ⇒ a newline) | table (31) **and its cells** (32) — Lark provisions the R×C grid, the engine fills each cell |
| `mermaid` | a fenced block whose token is `mermaid` — **the fence the reader itself writes for a diagram**, so a diagram round-trips | a diagram add-on (40). Also authorable directly with `NewBlock.mermaid(source, theme=None)`, taking already-compiled Mermaid source — compile a structured spec with `larkdocio.mermaid`. **CREATE-ONLY:** there is no in-place update, so changing a diagram is **delete + re-create at the same index** and the `block_id` changes — see § "Recipe: author a mermaid diagram" |

**Lossiness — documented, not discovered.** Every construct below is refused with a typed
`not-in-dialect` refusal whose mandatory `detail` names **the construct and its 1-based
line** — never silently dropped, flattened or approximated. `NOT_EXPRESSIBLE_CONSTRUCTS` is
the code truth and this table is guarded against it in both directions:

| Construct | Why it cannot be composed |
|-----------|---------------------------|
| `image` | A `![](…)` carries a path or a token, and this compiler has **no bytes** and makes no network call — so there is nothing to upload. **The picture itself is not out of reach**: author the prose here and put the image in with `larkdocio.write.media.put_image_in_document` (see *Recipe: put an image in a document*), choosing where it lands with `parent_block_id` + a 0-based `index`. A **file** takes the sibling route — see *Recipe: attach a file to a document*. |
| `link` | An inline link is a **styled run** and *this compiler* creates unstyled runs — the original reason, unchanged. **Two exceptions inside the dialect.** (1) The reader's own bare-URL autolink shape (`[url](url)`, where the text *is* the href) composes to the literal URL. (2) **Inside a table cell, `[label](url)` composes** and reads back as the same Markdown — Lark was measured to accept and store the link-carrying run in a cell on both write routes, so the round-trip property this refusal protects is what *admits* that one position. **The conclusion moved, not the reason: an anchored link IS authorable** — in a cell through the dialect, and anywhere else as a typed shape, `NewBlock.rich_paragraph` with a `TextSpan` carrying `link_url` (see *Recipe: link a file from a sentence*). The dialect stays closed in every other position on purpose. |
| `bold` | A styled run — created text is unstyled. Escape the markers to keep them literal. **Colour has no row here at all** — see the note below the table: it is not a refusal, because there is no Markdown for it to refuse. |
| `italic` | A styled run — created text is unstyled. |
| `strikethrough` | A styled run — created text is unstyled. |
| `inline-code` | A styled run — author a fenced block, or escape the backticks. |
| `html` | Raw HTML has no creatable block (the reader emits HTML only for what Markdown cannot express: an `<u>` underline, a merged `<table>`). **The trap, and it is prose rather than markup:** ordinary text in angle brackets is HTML to a Markdown parser — `Lorem <ipsum dolor> sit amet` is a well-formed open tag (element `ipsum`, attribute `dolor`), so one bracketed word nobody thought of as markup refuses the whole fragment. Measured: `<ipsum>` and `<ipsum dolor>` refuse; `<ipsum_dolor>` and `A <= 3` do not, because neither is a well-formed tag. **The repair is to escape the bracket** — a backslash before it, or the `&lt;` entity — both of which compose as literal text. Backticks do **not** help: that is an `inline-code` refusal instead. |
| `merged-table` | **Merged cells are not expressible** — see the note below. |
| `thematic-break` | A divider (block type 22) is not creatable in this rung. |
| `indented-code-block` | Outside the dialect — the reader always emits a **fenced** block. |
| `hard-break` | A hard line break has no docx representation (the reader never emits one). |
| `footnote` | A footnote **definition** has no creatable block; a bare `[^1]` *reference* is literal text in GFM too, so it composes verbatim. |
| `list-item-block-child` | A list item carries its own text plus **nested list items** only; any other block child renders at column 0 — a *sibling* in Markdown — so author it as one. |
| `blockquote-block-child` | The creatable quote block carries **one** text run and a quote *container* (34) is not creatable, so a multi-paragraph / nested / fenced blockquote is not expressible. |
| `empty-list-item` | A marker with no content carries nothing. **The trap that produces one without you writing one:** a list item whose text begins with `#` or `>` — `- # Heading` — parses as a *heading (or a quote) nested inside the item*, which leaves the item itself empty, so the refusal names the line of a bullet you were sure had text on it. (A leading table pipe only does this when the item's own lines form a whole GFM table, delimiter row included; a lone pipe row inside an item is literal text and composes.) **The repair is to escape the marker** — `- \# Heading` — which composes as literal text and round-trips. A sanitiser that rewrites prose into bullets is the usual source, which is why this surfaces late. |
| `empty-heading` | A heading is a marker **plus content**. |
| `empty-quote` | A quote is a marker **plus content**. |
| `code-fence-info` | Lark stores a code block's language as a single enum, so a fence info string carrying more than the bare token is not expressible. |
| `unknown-code-language` | Lark has no enum for that fence token — use `supported_code_languages()`, or a bare fence. Never silently downgraded. |
| `non-creatable-projection` | The fence is **the reader's own projection** of a block this library does not create today, so the token is not a language and swapping it cannot help. Drop the fence, or keep the text under a **bare** fence to author it verbatim as a code block. Distinct from `unknown-code-language` on purpose: that one is a token *you* chose, this one is a token *we* wrote. **No projection ships today** — the only one that ever did was ```` ```mermaid ```` (a **diagram add-on**, block type 40), and it became authorable (`NewBlock.mermaid`), so that fence now **composes**. The refusal remains for the next such block, if there is one. |
| `empty-mermaid` | A ```` ```mermaid ```` fence with **no diagram source**. Lark accepts an empty diagram and stores it, and the reader emits **no fence and no marker** for one — so it would author a block that is *invisible* in Markdown rather than a visible mistake. Give the fence its Mermaid source, or drop the fence. |
| `nesting-too-deep` | Past `larkdocio.write.MAX_NEST_DEPTH` (each level costs its own throttled call). Refused with the cap named — **never flattened**. |
| `table-cap` | Past `larkdocio.write.MAX_TABLE_CELLS` (500) — **larkdocio's own** cap, anchored on a measured platform envelope: Lark takes a 499-cell table subtree in one call and refuses the next. **Not** one of Lark's own ceilings (those are 100 columns, `1770010`, and no row cap). Refused with the cap named **and a size to split into** — **never truncated**. What a table costs to author is in § "What authoring a table costs, and where the 500-cell cap comes from". |
| `table-column-cap` | Past `larkdocio.write.MAX_TABLE_COLUMNS` — a **measured Lark ceiling**, not one of ours: Lark refuses the 101st column itself (`1770010 "too many table column"`). Refused with the cap named — **never truncated**. There is **no row equivalent**: a table of any HEIGHT composes and authors. |
| `block` | Any other block construct the dialect has no creatable block for. |
| `inline` | Any other inline construct (created runs are plain, unstyled text). |

**FINDING THEM ALL AT ONCE — `compose_check(markdown)`.** `compose()` refuses the **first**
construct in the fragment and says nothing about the rest. That is correct — a partial compile
would silently degrade your content — and it makes *discovery* expensive: one migration of
~27,000 words of existing prose needed **eight** separate attempts to find eight constructs,
one round trip each. `compose_check(markdown)` is the read-only checker beside `compose()`: it
returns a `ComposeCheck` whose `refusals` names **every** inexpressible construct in the
fragment, in document order, each row carrying the construct, its **1-based line** and the
*same* refusal text `compose()` would have handed you — so one pass replaces eight. `ok` is
the short answer, `constructs` the de-duplicated kinds. It changes **nothing** about what is
refused: `compose()` still refuses the whole batch on the first construct, with the same
message and the same code, and nothing became composable. A construct inside a fenced code
block is **content, not structure**, and is not reported — which is why this is a function and
not a grep-the-markers recipe. Worked: § "Recipe: find every construct that will refuse".

**Heading levels 7–9 read back as H6.** This is the one construct that is lossy in
its *level* rather than in its structure, and the only heading asymmetry: **H1–H6 round-trip
exactly** — the level you author is the level you read back — while **H7–H9 do not**. Lark
stores levels 1–9 and `NewBlock.heading(7..9, …)` really creates them (the node tree from
`parse_docx_tree` reports the true level), but Markdown's ATX marker stops at six, so the
reader **caps the emitted marker at `###### `** and `compose()` on that output yields an
**H6**. Emitting seven `#` instead — the earlier behavior — was *not valid CommonMark*: a
conforming parser reads `####### x` as a paragraph of literal `#`, losing the heading
altogether and refusing to re-compose. A capped level is the honest trade; nothing about the
document changes when you read it, and an authored H7 stays an H7 in Lark.

**Markdown tables cannot express merged cells.** There is no `colspan`/`rowspan` in Markdown,
so an authored table is always a plain rectangular grid: a **ragged** grid — rows of differing
width, which is the shape a merged table produces — is refused (`merge-not-expressible`) with
the offending row named, and the grid is **never padded or truncated** into shape. Give every
row the header's cell count and use an empty string for a blank cell. Reading a merged table
is unaffected: that is the reader's job, and it emits an HTML `<table>` for one.

**What a READ does to emphasis, and what a round trip does to it.** The reader **does**
emit character styling, which is why this table surprises people: a bold run comes back as
`**x**`, italic as `_x_`, strikethrough as `~~x~~`, inline code inside backticks, and an
underline as `<u>x</u>` (there is no Markdown for underline, so it is the one that leaves as
HTML). So the emphasis is *visible* in the Markdown you read — and then `compose()` **refuses**
each of those markers with the typed row above, because a created run is unstyled. The
consequence, stated plainly: **the reader's own emission of a styled run does not re-compose.**
What styling you did not author is nevertheless safe — an existing block's runs are rebuilt
element by element, so a whole-block edit keeps the styling around your change and a sub-span
edit that would have to split a styled run refuses instead of flattening it. In the file-first
round trip a block you edit is re-written as ONE run carrying the styling the block starts
with, so a colour that differed elsewhere in the paragraph is flattened onto that, while bold,
italics or a link inside the edited text refuse the push rather than being flattened.

**COLOUR is the one that is not in the table above, and that is not an oversight.** A text or
background colour is **captured and never emitted**: the reader reads `text_color` /
`background_color` off the block into the node tree and the Markdown renderer deliberately
never consults them, so a coloured run **reads back as plain text**. There is therefore no
marker for `compose()` to refuse — colour cannot be a refusal row, only an absence — and it is
not authorable either: it is on the NOT-creatable floor in § "Capability matrix"
alongside the styled runs, and no operation on this surface applies it to text that already
exists. The colour itself is not destroyed by a read; it is simply invisible in Markdown, so a
round trip through this dialect neither carries it nor removes it.

**And a table cell cannot carry a link anchor.** The link anchor is the one styling a created
run *can* carry — but not inside a table. It is on the NOT-creatable floor for that reason,
with the shapes it is derived from, and § "Recipe: link a file from a sentence" says the same
thing where a caller building that sentence meets it.

Beyond the refusals there are the shapes with **no Markdown syntax to compose them from at
all** — images/media, boards, embedded surfaces (Base / Sheet), callouts, grids and
colors. The long-form treatment (the normalizations, the asymmetries, and what
`compose()` does when handed the *reader's own emission* for a non-creatable block) lives in
`write/README.md` § "The composable Markdown dialect (`compose`)", which ships in the wheel next to this
guide — **read it with `larkdocio.writer_brief()`**, the same packaged-resource accessor
`larkdocio.guide()` is (so it works from a vendored wheel, where there is no `src/` tree to
open).

<!-- END AUTHORING-DIALECT -->

<!-- BEGIN DOCX-WRITE-ABSENCES (generated
     regenerate with:  python -c "from larkdocio.write.absences import docx_write_absences_markdown as m; print(m())"  -->

**What this surface does NOT do — the whole register.** Every entry below is a missing verb of the docx WRITE surface, stated as data and read straight off `capabilities(full=True)["surfaces"]["docx-write"]["absences"]`. Each one carries how firmly it was established and what to do **instead, today**; none of them is a to-do list. The one to read before you trust an apply log is `no-block-property-edit-beyond-text`: it is what an edit of an existing block can and cannot carry, and it is the row that says what happens — a typed refusal, never a green log — when you ask for a property it cannot write.

**`no-move-or-reorder-operation`** — *derived-from-shipped-code*

There is NO move or reorder operation on this surface. The body-writing request families are DeleteRequest, EditRequest, GrowTableRequest, InsertRequest, SubSpanEditRequest and no more, none of which relocates a block, so every whole-document reorganisation is DELETE-AND-RECREATE by contract. The reconciler states the same absence from the other side: a reorder in an edited block-identity projection is refused typed (marker-order-changed), not approximated, because the only way to express a move would be to delete the block and insert a copy — which destroys the block id every deep link and every anchored comment points at.

*How it was established.* DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): the request families are a closed set in larkdocio.write; the reorder refusal is larkdocio.write.reconcile's marker-order-changed. AND, at a different strength — MEASURED, which is a fact about Lark's API and not about this library: docx v1 exposes no route that moves or reorders an existing block, probed 2026-08-16 over ELEVEN enumerated candidate spellings. Two move operation keys (move_block, move_to) on the documented block PATCH route and its batch_update twin answered 1770001 'invalid param' — the same code an operation key the route has never heard of answers, which a control established, so the refusal means 'unrecognised operation'; adopting an existing block id through .../blocks/{parent}/children was refused by the field-validation code with the violation 'children[*].block_type is required', i.e. a child is a NEW block descriptor and never an adoption; five invented .../move, .../blocks/move, .../children/move, .../children/batch_move and PATCH .../children spellings all answered the gateway's own non-JSON HTTP 404 '404 page not found'; and two bodies went to the documented .../descendant route, the second of which is the copy trap below. The pinned SDK agrees offline — its UpdateBlockRequest declares sixteen operation fields and none moves or re-parents a block — but that is spec-derived, not measured, and the claim does not rest on it. THE TRAP A code 0 HIDES: POST /open-apis/docx/v1/documents/{doc}/blocks/{parent}/descendant, given a well-formed body naming an EXISTING block id, answers HTTP 200 code 0 'success' and CREATES A NEW BLOCK — it reads the live id as a client-side temporary id and hands it back as temporary_block_id beside the new block's real id in data.block_id_relations. Read back, the original was still in its original place and the root child order was unchanged, so a caller who reads code 0 as 'moved' ships a duplicate. SCOPE of the measurement, which the claim may not exceed: one tenant, one day (2026-08-16), a tenant_access_token on the write credential pair, the larksuite.com OpenAPI domain, docx v1, three plain docx documents the probe created and destroyed. Explicitly UNMEASURED, neither refuted nor supported: a user_access_token; any other tenant; wiki-wrapped documents; any docx API version other than v1; the Lark web client's internal reorder API; any move spelling outside the eleven; and whether the descendant route deep-copies a SUBTREE (the block it copied was a leaf). The verdict and the copy trap's captures were retired from the dev repo on 2026-09-18, so the scope above is stated in full rather than cited.

*Instead.* guide(section="recipe-reorganise-a-document-there-is-no-move-so-a-reorder-is-delete-and-recreate") — comments first, insert before delete, keep the blocks that did not move, and verify by reading the order back.

**`no-mention-authoring`** — *derived-from-shipped-code*

There is NO way to author an @mention on this surface — not of a person, a document or a chat. A created run is a text run that may carry ONE styling, the link anchor: larkdocio.write.model.TextSpan has exactly two fields, `text` and `link_url`, and the encoder emits no mention element of any kind. A mention that is ALREADY in a block is preserved rather than dropped: a whole-block edit rebuilds the block's runs element by element, and a sub-span edit whose span overlaps a mention refuses typed (span-not-splittable) instead of writing over it.

*How it was established.* DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): larkdocio.write.model.TextSpan is a two-field frozen value, NewBlockKind is a closed enum with no mention member, and no module under larkdocio.write emits a mention_user or mention_doc element — the mention code this library does ship is the READER's (larkdocio.contacts resolves a mention's open id to a display name at download time), which is what makes the write-side absence easy to miss. UNMEASURED, neither refuted nor supported: whether the docx create and patch routes would ACCEPT a mention element was never called from here, so this row claims only that this library does not send one.

*Instead.* Author the name as plain text, and address the person out of band — this surface's comment operations create a whole-document comment, which notifies the way a caller usually wanted the mention to. A mention already in the text survives any edit that does not overlap it.

**`no-character-style-operation`** — *derived-from-shipped-code*

There is NO operation that applies character styling — bold, italic, underline, strikethrough, inline code or colour — to text, whether the text already exists or is being created. The docx block PATCH route's own update_text_style operation is called by exactly ONE call site in this library and for exactly ONE field, a todo block's done bit (larkdocio.write.apply.build_todo_done_update, field mask 2): a checkbox is block state, not character styling, and no other field of that operation is ever written. A created run carries exactly one styling, the link anchor on larkdocio.write.model.TextSpan. Styling a caller did NOT author is nevertheless PRESERVED: larkdocio.write.client.to_write_elements rebuilds a block's runs element by element, so a whole-paragraph edit and a sub-span edit both leave the surrounding runs byte-identical.

*How it was established.* DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): update_text_style has exactly one call site in this library and it writes exactly one field. The one styling a created run can carry is TextSpan.link_url; bold, italic, strikethrough, inline code and colour are not fields on that type, so they are inexpressible by construction rather than refused at runtime, and no code path assembles a text_element_style for them. That holds inside a TABLE CELL too, where the link anchor is now authorable and nothing else is: the cell's elements come from the same span encoder, which emits link and no other key. SUPERSEDED IN PART, with the original reason preserved: this row used to say update_text_style was called by no module at all, and that its behaviour was UNMEASURED because nothing here had ever called it. Both clauses were true when written and the reason for stating them stands — a route this library names in a table is a description of Lark's surface, not a capability of this library, and saying so is what keeps a reader from deriving a styling recipe from the table. Only the conclusion moved: the done bit's field mask now has a call site. AND, at a different strength — MEASURED, which is a fact about Lark's API: mask 2 moves done and leaves align, folded, the item's own text and a nested child's id / text / state untouched, established on a throwaway document with the masks swept and re-proved by read-back in this library's own live write ring; the measurement is recorded in build_todo_done_update's own docstring, which cites where it was taken. SCOPE of that measurement, which this row may not exceed: the done field under mask 2, on a todo block. UNMEASURED, neither refuted nor supported: every OTHER field of update_text_style — align, folded and the character-style fields — has still never been written from this tree, so nothing here says what writing one would do.

*Instead.* Apply character styling in the Lark editor. In authored content, a link anchor IS available — a TextSpan carrying link_url, on any kind that accepts spans (the write brief lists them) and, at create time, inside a TABLE CELL authored as a TextSpan sequence rather than a string — and existing styling survives an edit untouched, so text can be rewritten without losing the formatting somebody else applied.

**`no-table-grid-change-beyond-appending-a-row`** — *derived-from-shipped-code*

APPENDING a row to a table that already exists IS a shipped operation: GrowTableRequest, anchored by the table's own block id or by a TableLocator, through the same plan gate, the same whole-document revision guard and the same refusal set as every other change, and it preserves the table's block id and every pre-existing cell id, in order. NOTHING ELSE about a table's grid can be changed. There is no operation that REMOVES a row or a column, none that appends a COLUMN, and none that inserts a row anywhere but the end. Asking for the last of those is REFUSED, typed table-grow-unsupported (larkdocio.write.model.refusal.RefusalReason), naming the append spelling as the remedy — never reported as applied. A table's CELLS are editable too (an EditRequest anchored by a TableLocator replaces one cell's whole text), which is a different operation from changing the grid.

*How it was established.* DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): the request families are a closed set and GrowTableRequest is the only one that touches a grid; it carries an anchor and a row index and nothing that could name a removal, a column or a second row; and the append itself is ONE loop with two callers (larkdocio.write.apply._append_table_lines, reached from the create path's _grow_table_grid and from the grow op's own apply leg), so there is no second definition of the operation that could quietly do more. SUPERSEDED, with the original reason preserved: this slot used to hold no-grow-operation-for-an-existing-table, which stated that NO operation added or removed a row or a column of an existing table, because the grow mechanism's only call site was inside the plan-gated insert — so the mechanism shipped and was measured while being unreachable as an operation. Most of the routes left to a caller cost the table's block id and every cell id in it, and the only route that preserved them was outside the plan gate entirely. That reasoning is why this row reads the way it does. Only its conclusion moved, and only for the append case: the rest of the grid is still absent, and the one thing that changed is that a caller no longer has to leave the gate to add a row. AND, at a different strength — MEASURED, which is a fact about Lark's API: insert_table_row {"row_index": -1} on the docx block PATCH route APPENDS at the end and leaves every pre-existing cell id untouched and in order, and the row axis grew to 200 with no refusal at any row — measured on disposable documents the probes created and trashed, and recorded in _grow_table_grid's own docstring, which names where the measurement was taken; the shipped operation re-proves the cell-id half by read-back in this library's own live write ring. It needs no new endpoint and no new scope: it rides the existing block PATCH. SCOPE of that measurement, which this row may not exceed: appending at the end, rows 1-200, on documents the probe made. Explicitly UNMEASURED, neither refuted nor supported: rows 201-500 — the library's own authored-grid ceiling is 500 cells and no platform row cap has ever been found here, so a grow past 200 rows is attempted rather than refused, and nothing here says what Lark would answer — and MID-TABLE insertion at any index other than -1, which has never been called from this tree and which no measurement in it covers, so its refusal is a statement about what larkdocio ships and not about what the API can do. Removal is unmeasured in the same sense: no delete_table_row spelling has been called from this tree in either direction. And the COLUMN axis is a deliberate scope call rather than a missing measurement — the primitive is measured (the axis grew to 100, and Lark refuses the 101st column in its own words, 1770010 'too many table column'), and it is left unshipped because appending a row leaves every pre-existing cell's row-major position exactly where it was while appending a column moves it, so a caller holding an offset into the grid would silently be holding the wrong one.

*Instead.* To add a row to a table that already exists, use the shipped operation: a GrowTableRequest through dry_run and apply, like every other change. N rows are N requests, each previewed and each exactly one write call. For anything else about the grid — removing a row or a column, adding a column, or inserting a row in the middle — author the table again at the shape you want (NewBlock.table takes the whole grid, and a grid wider or taller than the create call accepts is grown to its authored shape inside the same plan-gated insert) and delete the old one, which changes the block id of the table and of every cell in it, as every delete-and-recreate on this surface does; or make the change in the Lark editor. To change what a cell SAYS, patch the cell: an EditRequest with a TableLocator.

**`no-block-property-edit-beyond-text`** — *derived-from-shipped-code*

A whole-block edit of an existing block writes that block's TEXT and — since the checkbox shipped — a todo's done bit (todo.style.done), and NO other property of it. There is no operation that changes a code block's fence language, a diagram's theme, a heading's level, a block's type or a list item's nesting in place. The important half is what happens when a caller asks anyway: an edited projection whose only difference is one of those properties is REFUSED, typed change-not-expressible (larkdocio.write.model.refusal.RefusalReason), naming the property and the delete-and-insert route — never reported as applied. A change this surface cannot write does not become a green apply log.

*How it was established.* DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): larkdocio.write.model.EditRequest carries a replacement string and a todo_done bit and no other property, and the compiler enumerates the rest of a composed block's fields as the residual it refuses (larkdocio.write.compiler.EDIT_UNWRITABLE_BLOCK_FIELDS, held against larkdocio.write.model.NewBlock's own dataclass fields by a guard, so a new authoring field cannot arrive unclassified). A block type or heading level change refuses earlier still, at reconcile time, as block-type-mutation. The whole path — project, edit the marker, reconcile, compile, dry_run, apply — is driven end to end in this library's offline suite for both outcomes: the checkbox flip that writes the bit, and the fence-language change that refuses. SUPERSEDED, with the original reason preserved: this slot used to hold todo-done-bit-is-not-editable, which stated that a todo's done bit could not be changed at all and that an edit which tried reported SUCCESS while the checkbox did not move — recorded as an OPEN DEFECT rather than as a boundary somebody chose, precisely because a banner reading 'not editable' beside an engine answering 'applied' would have documented the bug as a design. That reasoning is why this row reads the way it does. Only its conclusion moved: the done bit is writable now, so the surviving absence is the rest of a block's properties, and the silence the old row was about is closed by a refusal rather than by a banner. AND, at a different strength — MEASURED, and cited rather than re-derived here: the done bit's own wire spelling and its blast radius are recorded in build_todo_done_update's own docstring, which names where the measurement was taken, and they are re-proved by read-back in this library's live write ring. UNMEASURED, neither refuted nor supported: whether Lark's API offers ANY route to the other properties named above has not been established from this tree — the absence is this library's, and no claim is made about the platform's.

*Instead.* For a checkbox, edit it in place: flip - [ ] to - [x] in an edited block-identity projection and the bit moves, or create the item in the state you want with NewBlock.todo(text, done=True). For any other property, delete the block and insert its replacement — two commits, and the block id changes, which takes comment anchors with it — or make the change in the Lark editor.

**`no-document-retitle-operation`** — *derived-from-shipped-code*

There is NO operation that renames or retitles an existing document. This surface's file lifecycle creates a document with a title and destroys one; nothing between the two changes the title of a document that already exists, and no request family carries a title at all. The document's own root Page block is not an exception: it is not creatable through this engine either, and the Markdown projection conserves it rather than inviting an edit to it.

*How it was established.* DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): larkdocio.write.client.WriteClient exposes the file lifecycle and the block routes and no rename among them; no request family carries a title; no module under larkdocio.write names a retitle verb. UNMEASURED, neither refuted nor supported — and said out loud, because a reader will otherwise derive a route from an addressing fact this library DOES publish: the root Page block's id equals the document_id, so a document's page block is addressable by the document's own id. That is how you ADDRESS it, not evidence that patching it retitles anything: whether the block PATCH route on a page block moves the DOCUMENT's title has never been called from this tree, by this library or by any probe recorded in it. It is neither a refusal nor a recipe, and a confident route written from the equivalence alone would be a guess wearing the shape of an answer.

*Instead.* Create the document with the title you want (the lifecycle's create takes one), or rename it in the Lark client. A caller who needs it done programmatically makes that call themselves — this library ships no verb for it and does not pretend the platform lacks one.

<!-- END DOCX-WRITE-ABSENCES -->

<!-- END DOCX-WRITE-ABSENCES -->

### What authoring a table costs, and where the 500-cell cap comes from

A table takes one of **two routes**, and which one it takes is decided for you, from the
content itself. Both produce the same table: the same content authored each way reads back
**identical** through this library's own reader, so a consumer cannot tell which one built a
given table.

**Route 1 — one atomic call, for a table that is an insert's only block and fits Lark's
one-call envelope.** The whole subtree — the grid, every cell and every cell's text — goes out
in a single `POST …/blocks/{block}/descendant`. That call costs **1**, whatever the grid's
shape, and a 6 × 36 = 216-cell table **measured 1 call / 0.82 s** on it. It is
also **atomic**: Lark takes the subtree whole or takes none of it, so a refusal leaves the
document exactly as it was rather than a half-built table in it. The envelope is a count of
**descendants**, not of cells or bytes — a table subtree is `2 × cells + 1` of them (the table,
one cell block per cell, one text block inside each cell) and the ceiling is **1000**, so this
route covers a table of **up to 499 cells**.

**Route 2 — create, grow, fill, for everything else**: a table that shares its insert with
another block, or one over the 499-cell envelope. Lark **auto-provisions** the cell grid from
the table's `row_size` / `column_size`, so the text is written into the provisioned cells
afterwards — and the create call itself validates **9 per axis** (Lark's own ceiling,
`1770001`), so a taller or wider grid is seeded at nine and grown a line at a time. What a
table of `R` rows × `C` columns costs on this route:

```
1 create  +  (R − 9) + (C − 9) grow calls   (each clamped at 0; one row/column per call)
        +  1 re-read of the grown grid       (skipped when nothing had to grow)
        +  ⌈(2 × cells + 1) / 500⌉ block-list reads   (how the cells' inner text-block
                                                       ids are learned, in one paged walk)
        +  ⌈non-empty cells / 48⌉ batched cell writes
```

For the 216-cell shape that is `1 + 27 + 1 + 1 + 5`, and one `apply()` of it **measured 37 API
calls in 12.4 s** live (the two extra are the plan's own anchor re-validation reads). It used
to be **463 calls / 158.41 s**, because each non-empty cell cost its own pair of calls (a read
to find the cell's inner text block, then a patch on it). Both halves are now batched: the ids
come from one paginated block list, and the texts ride `PATCH …/blocks/batch_update` in runs of
**48** — the largest batch an actual capture supports (48, 40 and 3 updates in one call all
answered `code 0` and read back; larger batches are **unmeasured, not refuted**).

Four consequences worth planning around:

- **Only route 1 is atomic.** On route 2 a failure partway through the grow-or-fill sequence
  leaves a real, partly-built table in the document — the create already happened. If that
  matters to you, keep the table as its own insert and inside 499 cells, which is what puts it
  on route 1. Either way nothing is silently truncated: a shortfall raises.

- **The cap is 500 cells** (`larkdocio.write.MAX_TABLE_CELLS`), and it is **larkdocio's own**,
  anchored on a measured platform envelope: Lark accepts a table subtree of **499 cells /
  1000 descendants** in one call and refuses the next. It is **not** a Lark ceiling. Lark's
  own, both measured, are **100 columns** (`1770010 "too many table column"`) and **no row
  cap at all** — a 499-row table read back correctly.
- **The grow path cannot be batched** — on route 2. `insert_table_row` takes one row per call;
  the plural spelling answers `1770001`, and extra `row_size` / `count` fields are accepted and
  ignored. So a very tall table pays one call per row past nine there, and that floor is the
  platform's. Route 1 never meets it: the one call declares the whole grid.
- **An empty cell costs nothing on route 2** — the provisioned cell is already empty, so a
  sparse grid is cheaper than a full one, and a grid of only empty cells does not even read the
  block list. On route 1 every cell is in the one body whether or not it carries text, because
  Lark refuses a cell with no text block inside it (`1770041`); the cost is the same single
  call either way.

**You do not have to work out which route your content took — the apply log tells you what it
cost.** Every `inserted` apply-log entry carries `mutating_write_calls` — a MEASUREMENT, counted
from the write calls the engine actually issued for that entry — and `atomic`, which is true
when that count is one and false otherwise. RELY ON: both keys being present on every `inserted`
entry; the unit being MUTATING write calls, so a paginated read is not one of them and a single
batched call carrying many updates is exactly one; and `atomic: false` meaning a failure partway
through can leave part of that content in the document, where `atomic: true` means it landed
whole or not at all. DO NOT RELY ON: the number itself for any given content. How the engine
gets your content into a document — which calls it uses, how much each one carries, and where it
splits them — is internal and changes without notice. Read the number the entry reports; never
predict it, and never compose to a boundary you inferred from it.

Every number above is either measured on documents the probes created and trashed (one
tenant, `tenant_access_token`, docx v1, block type 31, documents that are **not** wiki-wrapped
— other tenants, `user_access_token` and wiki-wrapped documents are **unmeasured, not
refuted**) or derived from the code that issues the calls.

### Do not edit the document while an authoring session runs (the concurrency doctrine)

**Do not edit the document concurrently.** An authoring session plans against a document it
read a moment ago, so a human editing that document in the meantime makes the engine
**refuse rather than guess** — refusals are **by design**, not a malfunction to retry
around: **the engine refuses when the document changed under the plan** instead of writing
your content into a position that has moved. Recovery is cheap and always the same: a busy
document just needs a **re-download** and a **re-plan**. That trade is deliberate — a
re-plan costs a read, a mispositioned write costs a corrupted document.

Practically: hold the document still for the seconds an authoring batch takes, keep
authoring runs short, and treat a refusal as "read again, plan again", never as "retry
harder".

**The mechanism — arm it, it is one argument.** The refusal above is the `STALE_DOCUMENT`
whole-document compare-and-swap, and it is armed by handing the previewer the `revision_id`
of the document you read: `dry_run(requests, root, document_revision_id=docx.revision_id)`,
where `docx` is the first value `reader.get_docx_content(doc_token)` returned — so the anchor
costs no extra call. The § "Recipe: the docx write handshake" recipe below does exactly this; copy it
from there. `plan.revision_guard` then reads `"active"`.

`apply` then re-reads the document's revision **once, immediately before the batch**. If it
differs **at all**, the **whole batch** is refused with `stale-document` and **zero writes are
issued** — never a partial application, and never an adjustment: the engine does not re-locate
your anchors or re-index your positions to fit a document that moved. Each refusal's `detail`
names both revisions and repeats the recovery, so the fix is mechanical: re-download, re-plan,
apply again.

Why bother when `STALE_ANCHOR` already re-validates every anchor? Because `STALE_ANCHOR` is
per-**anchor** and cannot see drift **around** one: insert three paragraphs above a paragraph
you are anchored to and the quote is still there, the block's text is byte-identical, every
per-anchor precondition passes — while the *position* your content was planned for has moved.
Positioning is a property of the document, so only a document-level check sees it.

**What this guard does not watch — and what a re-plan costs whoever edited beside you.** This guard's
window is plan-to-apply: it compares the revision the plan was built on against the revision
read immediately before the batch, so it sees an edit that lands inside that window and nothing
else. Text that arrived before the plan is already part of the tree the plan was computed from,
the two revisions it compares are the same one, and no refusal is raised for it. That matters
most at the moment you recover from a refusal, because the recovery hands you exactly such a
tree. Read the block before you re-plan it: the re-downloaded tree already contains the other
writer's words, and a whole-block edit re-planned against it replaces the block entire, carrying
those words away with no further refusal. A sub-span edit preserves them where it applies — it
rewrites only the quoted span and leaves every surrounding run byte-identical — and it is
bounded: narrative blocks only (a span inside a table cell is out of scope), the span must occur
exactly once in the block, and a span crossing runs of differing style or overlapping a non-text
inline refuses span_not_splittable. Where it does not apply or refuses, the whole-block edit is
still yours to make: build its replacement text out of the block you just re-read, so it carries
the other writer's words instead of dropping them. Both sentences are the ones each
`stale-document` refusal carries, verbatim.

If you omit `document_revision_id` nothing breaks and nothing is hidden: the plan is **marked**
`revision_guard: "unavailable"` and `revision_guard_detail` says why and how to arm it, the
per-entry `STALE_ANCHOR` re-validation still runs, and the guard **self-activates** on the next
plan that carries a revision. Capture the revision from (or before) the read that builds the
tree, never after — anchoring on the earlier value can only refuse a document that really did
change, which is the safe direction. And note that `-1` is the *"against latest"* request pin
used on block calls, **not** a revision: pass it and the guard reports itself unavailable
rather than pretending to compare.

**Several batches in one session? Re-capture between them.** Every one of your own writes
bumps the document's revision too, so a revision captured before batch 1 is stale by the time
batch 2 is planned — and `STALE_DOCUMENT` cannot tell your edit from somebody else's, by
design. Re-read the document (which you want anyway, to see what your first batch created) and
pass the fresh `document.revision_id` to each `dry_run`. One capture per plan, not one per
session.

---

## Output configuration (`config.json`)

The global `--config` option (it comes **before** the subcommand) points at a JSON file
whose `output` object tunes what the reader writes and how. In process the same settings
are `OutputConfig` — `Config(OutputConfig(title_as_filename=False))`, imported from
`larkdocio.read.config` — and the CLI and the library read the identical keys — the ones in the generated table
below, which is projected off that dataclass rather than counted by hand.
Omit `--config` and you get the defaults below; there is nothing to create to start.

The table is generated from the settings object itself, so a default here is the default
the code holds:

<!-- BEGIN CONFIG-SCHEMA (generated
     regenerate with:  python -c "from larkdocio.capabilities import config_schema_markdown as m; print(m())"  -->

| Key | Default | What it does |
|-----|---------|--------------|
| `image_dir` | `"static"` | Subfolder, created next to the output Markdown, that downloaded images and the flowchart / mindmap PNGs are written into. Image links in the Markdown are rewritten to point at it relatively. |
| `title_as_filename` | `true` | Name the output file after the document's own title, prefixed with a UTC `[YYYY-MM-DD_HHMM]_` stamp — so two downloads of the same document produce two files rather than overwriting one. When `false` the name is `<document token>.md` with no stamp at all, which is how to get a stable, repeatable filename. |
| `use_html_tags` | `false` | Emit HTML tags for the inline styles Markdown cannot express (`<u>` for underline). When `false` only Markdown-native styling is emitted and those styles are dropped. |
| `skip_img_download` | `false` | Leave image tokens unresolved: no network fetch, nothing written into the assets subfolder, and image links are not localized. |
| `download_attachments` | `false` | Opt in to best-effort binary download of file attachments. Default `false`: an attachment surfaces as its name+token marker and no attachment network happens at all. When `true` each queued file token is fetched into `image_dir` alongside the images, warning and continuing past a failure. |
| `resolve_mentions` | `true` | Resolve @mention open ids to display names at download time (`@ou_id` -> `@Name`) through the contacts batch call. A missing contacts scope, an id the directory does not cover, or a failing lookup keeps the raw `@ou_id` after one log line and never fails the read. When `false` resolution is skipped entirely and the contacts surface is never touched. |

The whole file, every key at its default — which is exactly what the package ships as `larkdocio/config.json`, so omitting `--config` and passing this file are the same run:

```json
{
  "output": {
    "image_dir": "static",
    "title_as_filename": true,
    "use_html_tags": false,
    "skip_img_download": false,
    "download_attachments": false,
    "resolve_mentions": true
  }
}
```

Any subset is valid: a key you leave out keeps the default above, and a key the library does not know is ignored.

<!-- END CONFIG-SCHEMA -->

Two of these keys decide **where the file lands and what it is called** — see
[Where the file lands: `-o`, and `--route` when you name the subpath](#where-the-file-lands--o-and---route-when-you-name-the-subpath) in the download recipe, which is the rule
in full.

## Verifying a sheet write — compare values, not their string forms

**Read this before you write a self-check.** The obvious way to verify a sheet write is to read
the range back and compare it to what you sent. Compared as *text*, that check reports a
difference on **every whole number in the sheet**, and nothing is wrong with the write — the
sheets counterpart of the docx side's compose-equivalence trap:

> A SHEET'S NUMERIC READ-BACK IS NORMALIZED, so verifying a write by comparing STRING FORMS reports a phantom difference. Measured live: every whole-valued float comes back as an int — 18.0 reads back as 18, 0.0 as 0, -3.0 as -3, 1e6 as 1000000, and 2.5*4 as 10 — while a non-whole float is returned untouched (22.5 stays 22.5) and a string stays a string ('18.0' stays the text '18.0'). An empty cell reads back as null, and a trailing empty cell may not be returned at all. So str(written) == str(read_back), json.dumps of the two matrices, and a diff of two rendered Markdown tables all report a change on every whole number in the sheet, and none of those changes happened. Compare values, not their string forms: larkdocio.sheets.values_equivalent(written, read_back) compares numbers numerically across int/float, treats an empty cell and an absent trailing cell as the same emptiness, and keeps every REAL difference visible — a text '18.0' is not the number 18, a bool is not 1, and 18.01 is not 18. It is a typed comparison and NOT a tolerance, deliberately: the normalization changes a value's type and never its magnitude, so a fuzz factor would buy nothing and would hide the 18.0-to-18.01 drift you are checking for. larkdocio.sheets.value_differences(written, read_back, origin='A1') returns the same answer cell by cell, each difference carrying its A1 ref. Evidence: tests/captures/sheets-merge-variant-probe/captures/02-numeric-read-back.json in the source repository.

| You write | It reads back as | Comparing strings says |
|-----------|------------------|------------------------|
| `18.0` (a float) | `18` (an **int**) | changed — falsely |
| `22.5` | `22.5` | unchanged — correctly |
| `"18.0"` (a string) | `"18.0"` (still text) | unchanged — correctly |
| `""` (an empty cell) | `None`, or nothing at all in a trailing position | changed — falsely |

`values_equivalent` is pure comparison — no client, no credentials, no call — so a verification
pass costs one read and nothing else.

```python
import json

from larkdocio.sheets import render_cell, value_differences, values_equivalent

# What you wrote, and what the read-back gave you (the shapes put_values and read_values use).
written = [["Q3", 18.0, 22.5], ["Q4", 0.0, None]]
read_back = [["Q3", 18, 22.5], ["Q4", 0]]        # whole floats came back int; trailing cell gone

# THE TRAP — three ways to compare STRINGS, all three reporting a change nobody made.
trap_json = json.dumps(written) == json.dumps(read_back)              # False
trap_str = str(written[0][1]) == str(read_back[0][1])                 # False ('18.0' vs '18')
trap_rendered = render_cell(written[0][1]) == render_cell(read_back[0][1])   # False

# THE COMPARATOR THAT IS TRUE — values, not their string forms.
verified = values_equivalent(written, read_back)                      # True
print(trap_json, trap_str, trap_rendered, verified)

# A REAL difference stays visible, and names the cell it is in.
drifted = [["Q3", 18.0, 22.5], ["Q4", 0.0, None]]
drifted[0][1] = 18.01
print(value_differences(drifted, read_back, origin="A1"))
# [{'ref': 'B1', 'written': 18.01, 'read_back': 18}]
```

- **It is a typed comparison, not a tolerance.** `18.0` and `18` are the same number; `18.0` and
  `18.01` are not, and no fuzz factor is applied that could hide the second. A text `"18.0"` is
  **not** the number `18`, and `True` is **not** `1` — both are real differences you want to see.
- **`value_differences(...)` is the same answer, per cell**, each difference carrying its A1
  `ref` (pass `origin=` as the range's top-left cell, or the range itself).
- **This has nothing to say about styles, borders or a dropdown's colors** — those have their own
  read-back limits, called out in their own recipes.

---

## Reference — the shapes and the law a recipe assumes

### The read-back law — a green apply is not a receipt

**The rule, and it applies to every write in this guide: after an apply, re-read the document
and assert what landed.** Not the return value, not the absence of an exception — the
document. Every write recipe below either performs that read-back in its own runnable code or
points here, and the two incidents that earned the rule are both cases of *the library telling
the truth and nobody reading it*:

* **A typed refusal a caller can ignore.** Exactly-one-or-refuse means a request the engine
  cannot resolve to exactly one target is **refused, per entry, with its reason and detail in
  the log** — never guessed at. A batch of two edits that recorded one
  `ambiguous-N-candidates` refusal (every candidate id named) applied one edit and refused the
  other, exactly as designed; the caller read neither, and ended the run believing both had
  landed. What `apply()` itself now does about a refusal is stated once, where the handshake
  is — § "Recipe: the docx write handshake" — and this law is the step **after** that one: a
  raise tells you an entry refused; only a read-back tells you the entries that did *not*
  refuse are what you meant.
* **A misplacement nothing refused.** A batch of inserts against one tree once landed in an
  order the plan had not described — every entry `applied`, **no refusal anywhere, plan and
  log both clean** — and a document briefly carried its escalation ladder in reverse. It was
  caught by a re-read and by nothing else. (Fixed in 1.34.0 — `larkdocio.release_notes()`. The
  rule outlives the bug: **a clean log has never been evidence of a correct document**, because
  a plan says what was *asked* and a log says what was *accepted*, and neither says what the
  document now *contains*.)

**It is a rule for your code, not a step the library takes for you.** larkdocio does **not**
silently re-download after a write: a read is an API call, and spending one you did not ask for
— on every apply, in every batch loop — is not a decision a library gets to make for its
caller. So the read-back is yours to write. It is one call.

**What a read-back should assert — the thing you meant, never "the call succeeded".** Match
the assertion to the edit:

* **text** → compose-equivalence, never string equality (§ "Recipe: verify what you authored —
  compose-equivalence, not string equality"): your own text is not what the document holds
  after a round trip, and comparing strings reports changes nobody made;
* **order** → read the block ids back and compare the **sequence** (§ "Recipe: reorganise a
  document — there is no move, so a reorder is delete-and-recreate");
* **presence** → the id `apply()` handed back is in the tree the next read returns
  (§ "Recipe: anchor a follow-up by a created block id");
* **a spreadsheet cell** → compare **values, not their string forms** (§ "Verifying a sheet
  write — compare values, not their string forms");
* **a member, a setting, a Base row** → those surfaces already read back for you and say what
  they *found*, which is the same law with the call bundled in.

**And read the log while you are there.** The log is 1:1 with the plan, in plan order,
whatever happened: `for entry in log` iterates it, `len(log)` sizes it, `log.applied` and
`log.refusals` split it, and a refused entry carries `entry.refusal.reason` and
`entry.refusal.detail`. Every write recipe in this guide models that, so a pasted recipe is
already reading it.

### The raw wire shape of every field type

<!-- BEGIN BASE-RAW-SHAPES (generated
     regenerate with:  python -c "from larkdocio.base.shape_docs import raw_shape_markdown as m; print(m())"  -->

One row per `(type, ui_type)` pair the cell registry renders, each shape taken from a committed
capture rather than from prose. The capture files below live **in the source repository**.

| API identity | UI name | What `raw` hands you | Capture it was read from |
|---|---|---|---|
| `1 / Text` | Text | `[{"text": "row", "type": "text"}]` — a segment array, never a joined string | `tests/captures/base-study/captures/p1-q0-03-per-table.json` |
| `3 / SingleSelect` | Single Option | `"Alpha"` — a bare string, the option **name** | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` |
| `4 / MultiSelect` | Multiple Options | `["Red", "Green"]` — a list, in the order stored | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` |
| `11 / User` | Person | `[{"id": …, "name": …, "en_name": …, "email": …, "avatar_url": …}]` — the whole object, **id included**, which the render drops | `tests/captures/base-study/captures/ld256-01-person-write-shapes.json` |
| `23 / GroupChat` | Group | `[{"id": …, "name": …, "avatar_url": …}]` | `tests/captures/base-study/captures/p0-4-04-value-readback.json` |
| `5 / DateTime` | Date | `1785061011000` — **ms epoch, an int**; no timezone is applied and none is implied | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` |
| `17 / Attachment` | Attachment | `[{"file_token": …, "name": …, "size": 108, "type": …, "url": …, "tmp_url": …}]` — the two URLs are short-lived signed links | `tests/captures/base-study/captures/p0-4-04-value-readback.json` |
| `2 / Number` | Number | `42.5` — the JSON number, unformatted | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` |
| `7 / Checkbox` | Checkbox | `true` — and **the key is absent when false** | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` · `tests/captures/base-study/captures/06-02-record-create-echo.json` |
| `15 / Url` | Link | `{"link": …, "text": …, "type": "url"}` | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` |
| `20 / Formula` | Formula | `{"type": 2, "value": [2]}` — a typed wrapper whose `type` is the **result** type | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` |
| `19 / Lookup` | Lookup | `{"type": 1, "value": [segments…]}` — the wrapper's `type` is the **target field's** | `tests/captures/base-study/captures/p1-q0-03-per-table.json` |
| `24 / Stage` | Flow | **nothing at all** — the key is absent from every read route, so raw is silent exactly where the render carries its marker | `tests/captures/base-study/captures/p1-q1-02-stage-read-routes.json` |
| `1005 / AutoNumber` | Numbering | `"1"` — a **string**, not an int | `tests/captures/base-study/captures/p0-5-01-scalar-read-encodings.json` |
| `13 / Phone` | Phone Number | `"+12025550100"` — a bare string | `tests/captures/base-study/captures/06-03-value-read-option-matrix.json` |
| `1 / Email` | Email | `[{"link": "mailto:…", "text": "…", "type": "url"}]` — the address **twice**, prefixed and plain: comparing the rendered form is how one address in two shapes reads as two vendors | `tests/captures/base-study/captures/p1-q0-03-per-table.json` |
| `22 / Location` | Location | `{"location": "103.8198,1.3521", "full_address": …, "pname": …, "cityname": …, "adname": …, "address": …, "name": …}` | `tests/captures/base-study/captures/p0-4-04-value-readback.json` |
| `1 / Barcode` | Barcode | `[{"text": "BC-9", "type": "text"}]` — a segment array, same as Text | `tests/captures/base-study/captures/p0-5-01-scalar-read-encodings.json` |
| `2 / Progress` | Progress | `0.35` — the fraction, not the rendered percent | `tests/captures/base-study/captures/p0-5-01-scalar-read-encodings.json` |
| `2 / Currency` | Currency | `12.5` — no code and no symbol; those live on the field | `tests/captures/base-study/captures/p0-5-01-scalar-read-encodings.json` |
| `2 / Rating` | Rating | `4` — an int, no glyph | `tests/captures/base-study/captures/p0-5-01-scalar-read-encodings.json` |
| `21 / DuplexLink` | Two-way Link | `{"link_record_ids": ["rec…"]}` — an **object**; `null` means never written and `[]` means emptied by a delete, and raw keeps them apart | `tests/captures/base-study/captures/p0-2-05-link-lookup-read-encodings.json` |
| `18 / SingleLink` | One-way Link | the same object shape | `tests/captures/base-study/captures/p0-2-05-link-lookup-read-encodings.json` |
| `1003 / CreatedUser` | Created By | `[{person}]` — the same object shape as Person | `tests/captures/base-study/captures/05-07-record-read-option-matrix.json` |
| `1004 / ModifiedUser` | Modified By | `[{person}]` | `tests/captures/base-study/captures/p0-5-01-scalar-read-encodings.json` |
| `1001 / CreatedTime` | Date Created | `1785693438000` — ms epoch, an int | `tests/captures/base-study/captures/05-07-record-read-option-matrix.json` |
| `1002 / ModifiedTime` | Last Modified Date | `1785693462000` — ms epoch, an int | `tests/captures/base-study/captures/05-07-record-read-option-matrix.json` |

<!-- END BASE-RAW-SHAPES -->

**Person and attachment payloads are the one place raw hands you more than the render does.**
The Markdown projection drops a person's id, address and avatar link on every path by policy,
and drops an attachment's signed URLs because they expire. Raw carries what the API sent, so
treat a retained read as holding the same data the API call did — including the parts the
reading form deliberately does not show.

### What a Base cell TAKES and what it HANDS BACK

The table above says what a cell **hands you**. This one says what it **takes**, and puts the
two side by side — because for several field types they are not the same object at all. Writing
back the shape you just read is the most expensive mistake on this surface: it is refused,
sometimes locally with a typed error naming the shape wanted, and sometimes by the server with a
code that reads like a fault in Lark rather than in the value. Read your type's row before you
write it, and the trap is unhittable.

**FIRST, THE ONE PEOPLE MEET FIRST: what `search_records()` hands back for a Text cell.** It is
the read call every recipe here makes, its records carry a `fields` mapping keyed by **field
name**, and a Text cell in there is **not a string**:

```text
records = read.search_records(app_token, table_id)

records[0].fields                    → {'Title': [{'text': 'row', 'type': 'text'}], …}
records[0].fields["Title"]           → [{'text': 'row', 'type': 'text'}]
records[0].fields["Title"][0]["text"] → 'row'          ← the value itself
```

(The same three lines run, rather than being quoted, in **Recipe: the Base write handshake**,
whose sample reads the table it is about to change.) Measured on a disposable: the string `"row"`
was written to a Text column through
`create_record`, and `search_records` handed it back as `[{'text': 'row', 'type': 'text'}]` — a
**segment array**, one segment, the value on `text`. That is the *read* shape; the *write* shape
for the same cell is the bare string, which is the whole reason the table below has two columns
instead of one. **An empty cell is an ABSENT KEY**, not an empty list — so `.get(name)` on it
returns `None` and `fields[name]` raises. And `Phone`, `Barcode` and `Email` share the segment
shape (`Email`'s segments carry a `link` too), while `SingleSelect`, `Number` and `DateTime` come
back as bare scalars. The per-type answer is the row below; the rendered, human-facing form is
what `read_base` / `read_base_markdown` give you instead.

**How to read the *Field type* column — three names for one column, and they are not
interchangeable.** Each cell is `` `<type> / <ui_type>` · <label> ``, e.g. `1 / Text` · Text.
The **integer** is the *storage* type — the `type` key a read hands back (`FieldSpec.type`, the
SDK object's `.type`), and the one you pass as `field_type=` when you *author* a field. The
**quoted name beside it** is the `ui_type` — the API's own picker-type string, the second half
of the `(type, ui_type)` pair every renderer and encoder dispatches on. The **plain words after
the `·`** are neither: they are the label a human sees in Lark's field picker, carried so you can
find the row from the UI. Those three can all differ for one column — `3 / SingleSelect` · Single
Option is the same field said three ways — so match on the pair and read the label.

<!-- BEGIN BASE-CELL-SHAPES (generated
     regenerate with:  python -c "from larkdocio.base.shape_docs import cell_shape_markdown as m; print(m())"  -->

| Field type | Writable? | The shape you WRITE | The shape you READ BACK | What the difference is |
|---|---|---|---|---|
| `1 / Text` · Text | yes | `"row"` | `[{"text": "row", "type": "text"}]` | the bare string itself — the segment array is the READ shape and is refused rather than unwrapped, because unwrapping it would be a guess about which member carried the value |
| `3 / SingleSelect` · Single Option | yes | `"Alpha"` | `"Alpha"` | one option **name**, as a bare string — the same shape a read hands back |
| `4 / MultiSelect` · Multiple Options | yes | `["Red", "Green"]` | `["Red", "Green"]` | a **list** of option names; a bare string is refused rather than wrapped, since a one-option write is one character away |
| `11 / User` · Person | yes | `[{"id": <open_id>}]` | `[{"id": …, "name": …, "en_name": …, "email": …, "avatar_url": …}]` | **ids only**; everything else a read hands back — the display names, the address, the avatar link — is not a write input, and a display name is not an id |
| `23 / GroupChat` · Group | yes | `[{"id": …}]` | `[{"id": …, "name": …, "avatar_url": …}]` | objects, not bare ids — a bare list is accepted here and wrapped, because the server refuses one |
| `5 / DateTime` · Date | yes | `1785061011000` | `1785061011000` | milliseconds since the epoch, as an `int` — no date object is converted, because every conversion needs a zone and this library will not choose one |
| `17 / Attachment` · Attachment | yes | `[{"file_token": …}]` | `[{"file_token": …, "name": …, "size": 108, "type": …, "url": …, "tmp_url": …}]` | tokens only — a bare list of tokens is accepted here and wrapped, because the server refuses one; the name, size and the two signed URLs a read carries are not write inputs |
| `2 / Number` · Number | yes | `42.5` | `42.5` | a JSON number; the formatter, the currency code and the rating symbol live on the field's own configuration, never in the value |
| `7 / Checkbox` · Checkbox | yes | `True` | `true` | a boolean; `False` is a real write that simply **reads back as an absent key** |
| `15 / Url` · Link | yes | `{"link": …, "text": …}` | `{"link": …, "text": …, "type": "url"}` | **without** the read shape's third `type` key; a bare string is accepted and taken as a link that labels itself |
| `20 / Formula` · Formula | **not writable** | — | `{"type": 2, "value": [2]}` | A Formula is computed by the server from the formula stored on the field. Change the inputs the formula reads, or the formula itself, not the cell. |
| `19 / Lookup` · Lookup | **not writable** | — | `{"type": 1, "value": [segments…]}` | A Lookup mirrors a field on a linked record: the server recomputes it from the link, so there is nothing to set here. Write the value on the LINKED record instead. |
| `24 / Stage` · Flow | **not writable** | — | **nothing at all** | Stage is fully opaque: the schema is readable, the values are not, and a write answers success while changing nothing — the table revision does not move. It cannot be written through the API at all, so this refuses instead of appearing to succeed. Move the record in the product instead — a Stage transition is a drag of the card into the next stage, and no API route reaches it. |
| `1005 / AutoNumber` · Numbering | **not writable** | — | `"1"` | An AutoNumber is allocated by the server when the record is created. It is not a value a caller supplies, and supplying one does not reserve it. |
| `13 / Phone` · Phone Number | yes | `"+12025550100"` | `"+12025550100"` | the bare string itself — the segment array is the READ shape and is refused rather than unwrapped, because unwrapping it would be a guess about which member carried the value |
| `1 / Email` · Email | yes | `"ada@example.com"` | `[{"link": "mailto:…", "text": "…", "type": "url"}]` | the address as a plain string; Lark synthesizes the `mailto:` prefix and the segment wrapper server-side, so what comes back is not what went in |
| `22 / Location` · Location | yes | `"103.8198,1.3521"` | `{"location": "103.8198,1.3521", "full_address": …, "pname": …, "cityname": …, "adname": …, "address": …, "name": …}` | the literal coordinate string, **longitude first** — an address, or the object a read returns, is refused |
| `1 / Barcode` · Barcode | yes | `"BC-9"` | `[{"text": "BC-9", "type": "text"}]` | the bare string itself — the segment array is the READ shape and is refused rather than unwrapped, because unwrapping it would be a guess about which member carried the value |
| `2 / Progress` · Progress | yes | `0.35` | `0.35` | a JSON number; the formatter, the currency code and the rating symbol live on the field's own configuration, never in the value |
| `2 / Currency` · Currency | yes | `12.5` | `12.5` | a JSON number; the formatter, the currency code and the rating symbol live on the field's own configuration, never in the value |
| `2 / Rating` · Rating | yes | `4` | `4` | a JSON number; the formatter, the currency code and the rating symbol live on the field's own configuration, never in the value |
| `21 / DuplexLink` · Two-way Link | yes | `["rec…"]` | `{"link_record_ids": ["rec…"]}` | a **bare list** of record ids, not an object: the read shape `{"link_record_ids": […]}` is refused rather than unwrapped, which is what keeps the asymmetry visible where it bites |
| `18 / SingleLink` · One-way Link | yes | `["rec…"]` | the same object shape | a **bare list** of record ids, not an object: the read shape `{"link_record_ids": […]}` is refused rather than unwrapped, which is what keeps the asymmetry visible where it bites |
| `1003 / CreatedUser` · Created By | **not writable** | — | `[{person}]` | The creating user is the identity the record was created under; it is recorded by the server and no request can set it. |
| `1004 / ModifiedUser` · Modified By | **not writable** | — | `[{person}]` | The last-modifying user is recorded by the server on every edit; it cannot be set, only observed. |
| `1001 / CreatedTime` · Date Created | **not writable** | — | `1785693438000` | The creation timestamp is the server's own audit trail; it is stamped at create time and no request can set it. |
| `1002 / ModifiedTime` · Last Modified Date | **not writable** | — | `1785693462000` | The last-modified timestamp is maintained by the server on every edit; it cannot be set, only observed. |

**Where the two shapes differ enough to cost you an afternoon.** Each of these is a refusal the library makes locally, before anything is sent — so the words below are the words you will read in the exception, not a paraphrase of them.

**Email — you cannot round-trip what you read.** You write `"ada@example.com"`; you read back `[{"link": "mailto:…", "text": "…", "type": "url"}]` — the address as a plain string; Lark synthesizes the `mailto:` prefix and the segment wrapper server-side, so what comes back is not what went in.

```text
AN EMAIL CELL CANNOT BE ROUND-TRIPPED. You write the address as a PLAIN STRING; Lark
synthesizes the mailto: prefix server-side, and the cell reads back as a url-typed segment
inside a text field. Feeding that read-back shape in again is refused 1254060
TextFieldConvFail. Note also that the API performs no address validation of its own: a
malformed address is stored, code:0 — so 1254060 was always about the segment SHAPE, never the
format, and this library does not invent a check Lark does not do. Validating the address is
the caller's.
```

**Text — a string goes in, a segment array comes out.** You write `"row"`; you read back `[{"text": "row", "type": "text"}]` — the bare string itself — the segment array is the READ shape and is refused rather than unwrapped, because unwrapping it would be a guess about which member carried the value.

```text
AND THIS IS NOT ONLY A LOCAL RULE. Fourteen segment spellings were sent to the record-write
routes anyway, and all fourteen are named here because the claim rests on the enumeration
rather than on the number — url-only, mixed text/url/text, the same text/url/text with its
text segments untyped, the reverse order, text-only, an empty array, a mention segment, and
seven malformed variants (a url segment with no link, a link spelled as an empty string, a
segment with its kind unstated, the single segment unwrapped out of its list, an empty label,
a mailto link, and a link with no scheme) — and Lark answered 1254060 TextFieldConvFail to
every one of them, on BOTH the create and the update route, in a run whose bare-string control
answered code:0 on both and read back as a segment array. So a labeled clickable link is not
something this library is withholding: the platform stores segment arrays and hands them back,
and does not take one as a Text WRITE on those two routes. The edge of that evidence, stated
rather than implied, and it has since moved by exactly one route: records/batch_create has now
been asked once, with the doc-mention chip a Base cell reads back after a human touches a
pasted document url, against a disposable Base — and it answered 1254060 TextFieldConvFail
too, so the refusal is not a property of the single-record routes. Its sibling
records/batch_update and table-creation cell seeding were NOT asked, and a shape nobody sent
is UNMEASURED, not refused. AND THE SCOPE OF THIS PARAGRAPH, because it has been read wider
than it is: every sentence above is about a BASE Text field on the record create/update
routes. It says nothing about a SPREADSHEET cell, where a labeled clickable link is a shipped
write that works — RichCellWriteRequest.hyperlink(range, link, text=…), worked through in the
guide's section 'Recipe: write a hyperlink and a styled run into a cell'. Two surfaces, two
answers; this one is the Base's.
```

*What was actually asked, and what was not.* Can a Text cell be WRITTEN as the segment array it reads back as — the labeled clickable link, where the visible words are the link and no URL shows? It was put to `POST …/records (create one record)` and `PUT …/records/{record_id} (update one record)` — and the bare string, sent through the same harness in the same run, answered code:0 on both routes and read back as a segment array. Every shape below came back the same way:

| The value sent | What Lark answered |
|---|---|
| `[{"type": "url", "text": "Example Link", "link": "https://example.com/example-link"}]` — one url segment and nothing else — the label-is-the-link cell | `1254060 TextFieldConvFail` |
| `[{"type": "text", "text": "see "}, {"type": "url", "text": "Example Link", "link": "https://example.com/example-link"}, {"type": "text", "text": " for detail"}]` — text before and after a url segment | `1254060 TextFieldConvFail` |
| `[{"text": "see "}, {"link": "https://example.com/example-link", "text": "Example Link", "type": "url"}, {"text": " for detail"}]` — the same, spelled the way a read-back prints it — key order link/text/type, and the text segments carrying no type key | `1254060 TextFieldConvFail` |
| `[{"type": "url", "text": "Example Link", "link": "https://example.com/example-link"}, {"type": "text", "text": " — see above"}]` — url first, text last | `1254060 TextFieldConvFail` |
| `[{"type": "text", "text": "plain words"}]` — the degenerate case — an array of nothing but text | `1254060 TextFieldConvFail` |
| `[{"type": "url", "text": "Example Link"}]` — malformed on purpose: a url segment with no link | `1254060 TextFieldConvFail` |
| `[{"type": "url", "text": "Example Link", "link": ""}]` — the same omission spelled as an empty string | `1254060 TextFieldConvFail` |
| `[{"text": "Example Link", "link": "https://example.com/example-link"}]` — link and text with the kind unstated | `1254060 TextFieldConvFail` |
| `{"type": "url", "text": "Example Link", "link": "https://example.com/example-link"}` — the single segment unwrapped out of its list | `1254060 TextFieldConvFail` |
| `[{"type": "url", "text": "", "link": "https://example.com/example-link"}]` — no label at all — would the server substitute the link? | `1254060 TextFieldConvFail` |
| `[{"type": "url", "text": "Example Link", "link": "mailto:nobody@example.invalid"}]` — a scheme the platform synthesizes itself on an Email cell | `1254060 TextFieldConvFail` |
| `[{"type": "url", "text": "Example Link", "link": "example.com/example-link"}]` — no scheme — the shape a human pastes | `1254060 TextFieldConvFail` |
| `[{"type": "mention", "text": "@nobody"}]` — a segment kind no write shape claims — is the type token validated? | `1254060 TextFieldConvFail` |
| `[]` — the empty array — a clear, an empty string, or a refusal? | `1254060 TextFieldConvFail` |

**Not tried, and therefore UNMEASURED rather than refused** — the BATCH record route `records/batch_update` — its sibling `records/batch_create` **was** asked, once, with the doc-mention chip a Base cell reads back after a human touches a pasted document url, and answered `1254060 TextFieldConvFail` like the two routes above, so the refusal is not a property of the single-record routes; `batch_update` itself remains unasked; cell values seeded at TABLE-CREATION time; any field type other than `1 / Text` — Phone and Barcode share the write rule and were deliberately left out of the question; segment arrays longer than three members, and nested arrays; a url segment carrying extra unrecognized keys beside link / text / type. A spelling nobody sent is an open question, not a closed one, and this list is here so you can see which is which.

**Link — a list goes in, an object comes out.** You write `["rec…"]`; you read back `{"link_record_ids": ["rec…"]}` — a **bare list** of record ids, not an object: the read shape `{"link_record_ids": […]}` is refused rather than unwrapped, which is what keeps the asymmetry visible where it bites.

**Location — a coordinate string goes in, a geocoded object comes out.** You write `"103.8198,1.3521"`; you read back `{"location": "103.8198,1.3521", "full_address": …, "pname": …, "cityname": …, "adname": …, "address": …, "name": …}` — the literal coordinate string, **longitude first** — an address, or the object a read returns, is refused.

```text
A location cell takes ONE literal shape: the string "<lng>,<lat>" — longitude first. Lark
geocodes it server-side. An address string, or the {full_address, location} object a read
returns, is refused 1254001 WrongRequestBody naming that format.
```

**Person — ids go in, whole people come out.** You write `[{"id": <open_id>}]`; you read back `[{"id": …, "name": …, "en_name": …, "email": …, "avatar_url": …}]` — **ids only**; everything else a read hands back — the display names, the address, the avatar link — is not a write input, and a display name is not an id.

```text
A person cell takes IDS ONLY: a list of {"id": <open_id>} objects. A display name is not an id
and this library will not turn one into one — the server refuses a name-shaped value with
1254066 UserFieldConvFail, and inferring which user was meant is exactly the mistake a silent
write makes expensive. Two honest sources of an id: HARVEST it from a read of a cell that
already names the person, or supply one the CALLER already holds. For the account owner's own
id, larkdocio.contacts.resolve_user resolves a name to exactly one open_id or refuses in a
typed way. A FOURTH source, and it is an ADDRESS route rather than a name one:
larkdocio.contacts.resolve_colleague turns an EMAIL (or a mobile) into exactly one open_id or
refuses the same typed way. Resolving an arbitrary OTHER USER's NAME is still deferred work
with its own mandate, and nothing here stands in for it — an email is not a name, and neither
verb stands in for the other.
```

**Every shape above was measured, not reasoned out.** Each write shape is the one a captured round trip stored and read back, and each read shape is the one a captured read returned; the capture files themselves live in the source repository and the library's own tests resolve every one of them, so a shape here that nothing measured cannot ship.

<!-- END BASE-CELL-SHAPES -->

### The shape of a Base filter condition, per field type

The two tables above say what a cell **hands you** and what it **takes**. This one says what a
**filter condition** on that cell looks like — the missing third answer. It matters because a
filter is keyed one way for the rows a read returns and another way for the rows a saved view
shows, and for a SELECT field even the value differs between them. Look your type up before you
guess a shape, the way a Checkbox once had to be guessed.

<!-- BEGIN BASE-FILTER-SHAPES (generated
     regenerate with:  python -c "from larkdocio.base.shape_docs import filter_shape_markdown as m; print(m())"  -->

A Base filter is described **once** — a `FilterSpec` of `Condition`s — and serialised for one of two routes, which key a condition differently and, for a SELECT field, key its VALUE differently too (that last part is the one that costs an afternoon):

* **The search route** filters the rows one read returns. It keys a condition by the field's **name**, and carries the value as a **real JSON array**.
* **The view route** filters the rows a person sees when they open the view. It keys a condition by the field's **id**, and carries the value as a **string containing** a JSON array; a valueless operator (`isEmpty` / `isNotEmpty`) OMITS the value key entirely there.

**The operator vocabulary is shared BETWEEN THE TWO ROUTES:** `is`, `isNot`, `contains`, `doesNotContain`, `isEmpty`, `isNotEmpty` — the six a capture proved on both routes, on a **Text field** — with conditions joined by `and` / `or`. That is a claim about the two ROUTES and nothing more: **which operators a given field TYPE accepts is claimed only where a row below says so**, and one row already says otherwise — a `7 / Checkbox` condition on the **view** route was measured to take only `is`, with `isNot`, `contains`, `isEmpty` and `isNotEmpty` each answering `1254001`. `FieldRegistry.resolve()` refuses those four locally, before any call. Lark's own view-route list is longer — "property.filter_info.conditions[*].operator is optional, options: [is,isNot,contains,doesNotContain,isEmpty,isNotEmpty,isGreater,isGreaterEqual,isLess,isLessEqual]" — but the four comparison operators in it are **not shipped and are not implied by any row below**: no capture shows one working, and the one that was tried answered `1254018` on a text field.

The table is the value **CONTENT** per field type — what goes inside whichever wrapper the route puts around it. A type with no measured filter value reads **shape not established** rather than a guess.

**Each route half carries its OWN evidence label, and a label never covers the other route. That is not a formatting choice: this table once said a Checkbox view-route condition matched on "the same boolean" as the search route, on the strength of a SEARCH-route observation, and the view route refused every quoted spelling of it. So a half nobody has observed reads `shape not established` rather than borrowing the other half's proof.**

| Field type | Search route matches on (by name) | How we know (search) | View route matches on (by id) | How we know (view) |
|---|---|---|---|---|
| `1 / Text` · Text | the text you match on, e.g. `"Text 1"` | captured | the same text | captured |
| `3 / SingleSelect` · Single Option | the option **name** (e.g. `"Done"`) | measured | the option **id** (`opt…`) — `FieldRegistry.resolve()` translates a name into its id for you, and refuses an unknown one naming the options that exist | measured |
| `4 / MultiSelect` · Multiple Options | each selected option's **name**; the SingleSelect half is the one proven live and MultiSelect rides the identical path | measured | each option's **id** (`opt…`), resolved the same way; the SingleSelect half is the one proven live and MultiSelect rides the identical path | measured |
| `11 / User` · Person | shape not established | unmeasured | shape not established | unmeasured |
| `23 / GroupChat` · Group | shape not established | unmeasured | shape not established | unmeasured |
| `5 / DateTime` · Date | shape not established | unmeasured | shape not established | unmeasured |
| `17 / Attachment` · Attachment | shape not established | unmeasured | shape not established | unmeasured |
| `2 / Number` · Number | shape not established | unmeasured | shape not established | unmeasured |
| `7 / Checkbox` · Checkbox | the boolean, which this library sends as the string `"True"` — `("is", (True,))`; `"true"` and `"1"` were accepted too, so this route is the lenient one | captured | ONE **unquoted JSON boolean** inside the array — `[true]` — which is what `("is", (True,))` now serialises to. Every QUOTED spelling is refused (`["true"]`, `["True"]`, `["1"]` and six more all answer `1254001`), as are both valueless operators (which a text field takes) and `isNot` even carrying the accepted value; a two-element array answers `code:0` and is stored as its first element alone, so the read-back does not echo | captured |
| `15 / Url` · Link | shape not established | unmeasured | shape not established | unmeasured |
| `20 / Formula` · Formula | shape not established | unmeasured | shape not established | unmeasured |
| `19 / Lookup` · Lookup | shape not established | unmeasured | shape not established | unmeasured |
| `24 / Stage` · Flow | shape not established | unmeasured | shape not established | unmeasured |
| `1005 / AutoNumber` · Numbering | shape not established | unmeasured | shape not established | unmeasured |
| `13 / Phone` · Phone Number | shape not established | unmeasured | shape not established | unmeasured |
| `1 / Email` · Email | shape not established | unmeasured | shape not established | unmeasured |
| `22 / Location` · Location | shape not established | unmeasured | shape not established | unmeasured |
| `1 / Barcode` · Barcode | shape not established | unmeasured | shape not established | unmeasured |
| `2 / Progress` · Progress | shape not established | unmeasured | shape not established | unmeasured |
| `2 / Currency` · Currency | shape not established | unmeasured | shape not established | unmeasured |
| `2 / Rating` · Rating | shape not established | unmeasured | shape not established | unmeasured |
| `21 / DuplexLink` · Two-way Link | shape not established | unmeasured | shape not established | unmeasured |
| `18 / SingleLink` · One-way Link | shape not established | unmeasured | shape not established | unmeasured |
| `1003 / CreatedUser` · Created By | shape not established | unmeasured | shape not established | unmeasured |
| `1004 / ModifiedUser` · Modified By | shape not established | unmeasured | shape not established | unmeasured |
| `1001 / CreatedTime` · Date Created | shape not established | unmeasured | shape not established | unmeasured |
| `1002 / ModifiedTime` · Last Modified Date | shape not established | unmeasured | shape not established | unmeasured |

**Every value form above was measured or is labelled by its evidence, never guessed.** The captures and the shipped round-trip tests behind the `captured` and `measured` halves live in the source repository; a `consumer-observed` half is a shape observed working outside this project that this library has not itself captured, and an `unmeasured` one is a route nobody has asked at all. Each says which it is rather than presenting itself as proven — which is exactly the difference that lets you plan against what is not yet established.

<!-- END BASE-FILTER-SHAPES -->

## Recipes

**Every recipe below runs as pasted** — swap in your own URL / token and your `.env` and
nothing else. Each one starts from a URL (or a token) and opens with the `init_env(".env")`
line, so there are **no undefined free variables** to fill in from a previous snippet. The
test suite proves it: it extracts every `python` block from *this document* and **executes
it** against fixtures + injected transports, so a recipe that stops running reddens the
suite before it can ship (`tests/test_discovery_truth.py`, `tests/guide_recipes.py`, in the source repository). No
recipe needs live credentials to prove out.

**The recipes are grouped by the task you are doing**, one `##` section per task, so a
`--section` ask for a task answers with that task and not with the whole document. The
groups, and the address of each:

| The task you are doing | `larkdocio guide --section …` |
|---|---|
| read something out of Lark into Markdown | `task-read-something-out-of-lark-into-markdown` |
| who can open it, where it lives, and which edition you mean | `task-who-can-open-it-where-it-lives-and-which-edition-you-mean` |
| change what a document says | `task-change-what-a-document-says` |
| put a picture, a file or a link into a document | `task-put-a-picture-a-file-or-a-link-into-a-document` |
| rows, columns and tables in a Base | `task-rows-columns-and-tables-in-a-base` |
| cells, tabs and formatting in a spreadsheet | `task-cells-tabs-and-formatting-in-a-spreadsheet` |

The shapes and the law those recipes assume are one section earlier, at
`reference-the-shapes-and-the-law-a-recipe-assumes`.

## Task — read something out of Lark into Markdown

### Recipe: download a docx to Markdown

The one-liner is the CLI (global `--env-file` / `--config` come **before** the
subcommand):

```bash
larkdocio --env-file .env download "https://…/docx/<token>" -o ./out/
# opt-in deep-read of embedded sheets, with cell emphasis:
larkdocio --env-file .env download "https://…/docx/<token>" -o ./out/ \
    --deep-read-sheets --fidelity-read-sheets
```

**The download hands back a value — read it instead of the log lines.** The function the
`download` command runs, `larkdocio.read.download.handle_download_command`, returns a
`DownloadResult`: **where the file landed, and how that destination was decided.** It used to
return nothing, so the only way to learn either was to parse the messages the run prints —
and the `--dump` sidecar, which answers the machine-readable half of the same question, is
written *into* the directory you could not learn. Both are on the value now:

```text
result = handle_download_command(url, "./out/", "", True, None)

result.output_path      # the Markdown file that was written
result.output_dir       # the directory it landed in — NOT always the -o you passed
result.dump_path        # the --dump sidecar, or None when the flag was not given
result.doc_token        # the docx token that was read (a wiki URL resolves to it)
result.title            # the title Lark answered
result.routed           # True when the -o root was rewritten
result.route_reason     # explicit_route | routing_disabled — the whole vocabulary
result.route            # the whole decision as data — the same record the sidecar carries

result.disambiguated    # True when the title was too long and the doc token joined the name
result.replaced_existing  # True when a file already existed at output_path and was overwritten

result.unknown_block_types  # the block types this library does not model, [] when none

result["output_dir"]    # it IS a dict: subscript, .get, in, {**result}, json.dumps, ==
```

**The last two are about the NAME, and they answer questions that used to have no answer.** A
document title longer than the filename budget is truncated, and two documents whose titles
first differ past that cut used to produce **one** file — the second download silently
destroying the first. It does not any more: when, and only when, the title is cut, the
document's own token joins the filename (`[stamp]_<cut title>_<doc token>.md`) and
`result.disambiguated` is `True`. **If you key on the old `[stamp]_<title>.md` shape, that is
the case to handle.** Short titles are untouched.

`result.replaced_existing` is the residual, and it is a disclosure rather than a fault:
re-downloading the same document into the same directory within the same clock minute lands on
the same name by design and reports `True` as well. A filename cannot answer *"is this the same
document?"*, so neither can this key — what it tells you is that bytes were replaced, which is
the question a pipeline previously had no way to ask.

**`result.unknown_block_types` is what a document used that this library does not model** — and
it is there so you never have to parse a log line to find out. One entry per **distinct**
unmodelled type, in first-seen order, four integer keys each:

```text
[{"block_type": 9997, "count": 2, "containers": 1, "children": 3}]

# block_type  the type, as Lark numbers it
# count       how many blocks of it this document carried
# containers  how many of those carried children, whose subtree was surfaced anyway
# children    how many child blocks those containers preserved
```

`count - containers` is how many were **leaves**, and a leaf of an unmodelled type contributes
nothing to the Markdown at all; an unmodelled **container** keeps its subtree, rendered at its
own depth with none of the wrapper's own markup. The key is on **every** successful download
and is `[]` when nothing was lost — an absent key and a clean document must not look the same.

**No block ids ride along**, deliberately: the answer grows with the document's vocabulary, not
with the document. If you want per-block detail, it is in the `Unknown block type N (block_id=…)`
warning and in the `--dump` sidecar's raw payload. **That warning still fires, unchanged** — it
and this key are written by the same recorder, so the two cannot disagree about what a document
lost. Its text is frozen, and the terms are stated in the release notes for the version that
introduced this key.

It is a `dict` subclass whose body holds exactly those keys, so a ledger can `json.dumps` it
straight out, and the attributes above are views onto that same body — an attribute cannot
drift from its key. This is the same shape the create verbs answer in (see
[Where a new object goes](#where-a-new-object-goes-you-name-the-destination-or-nothing-is-created)),
so the read side and the write side answer in one grammar. **Nothing new is read and no
permission, endpoint or scope moved** — a richer return type is a report on work already done.

Two things to know before leaning on it. It is the **command handler**, so a failure arrives as
the command line's own exception rather than a library one, and it writes files and fetches
images the way the command does; if what you want is a Markdown string with no side effects, the
one-call door below (`read_child_markdown`) or the explicit pipeline are the doors to use.

Or from Python — parse the URL, fetch the blocks, then render to Markdown:

```python
from larkdocio.common import get_read_credentials, init_env, validate_download_url
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
# `domain` is the API domain ("larksuite.com" | "feishu.cn"), NOT the tenant host in the
# URL — validate_download_url hands you the right one, plus the doc type and the token.
domain, doc_type, doc_token = validate_download_url(url)
app_id, app_secret = get_read_credentials()      # LARK_READ_APP_* (legacy pair fallback)
client = Client(app_id, app_secret, domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = client.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token
docx, blocks = client.get_docx_content(doc_token)
# `read_client=client` is what resolves @mentions — see below. Drop it and the same
# document reads back with raw `@ou_…` ids where the names belong.
markdown = Parser(Config(), read_client=client).parse_docx_content(doc_token, blocks)
```

**One call, if a Markdown string is all you want: `larkdocio.drive.read_child_markdown`.** It
runs the same pipeline as the block above — URL validation, wiki-to-docx resolution, the block
read, the parse — and hands back that one string. Import it from `larkdocio.drive`: it is
exported there and **not** from the top-level `larkdocio` namespace, which is why it is easy to
miss.

```python
from larkdocio.common import init_env
from larkdocio.drive import read_child_markdown

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
# The first argument is the surface — "docx" | "sheets" | "base". For a docx everything the
# read needs comes off the URL; `token=` is the child's own file token, which the folder walk
# already holds at the point where it calls this.
markdown = read_child_markdown(
    "docx",
    url="https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE",
    token="YOURDOCTOKENHERE")
```

**Four things it does NOT do — if you need any of them, use `download` above instead.** It is
the folder walk's own per-child reader aimed at one document, and it performs **no image fetch**
(image and whiteboard tokens stay as tokens in the text; nothing is downloaded), **no file
write** (nothing lands on disk — the returned string is the whole result), **no routing at all**
(nothing places the output anywhere, because nothing is written; `--route` is the CLI's, and
no derivation from the document exists on either side), and **no @mention resolution** — it parses without a `read_client`, so every mention
comes back as the raw `@ou_…` id, which is exactly the degrade described next.

**`read_client=` is why this recipe and the CLI above produce the same Markdown for the same
document.** The parser renders offline: on its own it *collects* each `@mention`'s `open_id`
and substitutes nothing, so `Parser(Config())` — no client — hands you
`@ou_exampleowner00000000000000000001` where a name belongs. Handing it the read client lets
it finish through `batch_get_user_names`, which is exactly what the `download` command does
internally — the same substitution, called from the same one place. The two paths' output is
compared **byte-for-byte** by the test suite, so the parity is asserted rather than assumed.

**It costs one contacts call per document and it can never fail your read.** The ids are
deduped before the call, and every failure mode — an id the directory does not cover, a user
with no usable name, a missing scope, a lookup that errors outright — **falls back to the raw
`@ou_id`** after one log line. Partial results are normal: the names that resolved are
substituted, the rest stay as ids.

**Two preconditions, and both are settings on your own app in the Lark console** — neither is
something the library can request for you:

- the app carries the **field-level** contacts scope `contact:user.base:readonly` (alongside
  `contact:contact.base:readonly`, which opens the directory call at all). With only the
  latter, the call *succeeds* and every name field comes back **null**, which looks exactly
  like "no such user";
- the app's **contacts data range** covers the users being mentioned. Out of range, they do
  not come back at all.

Miss either half and every mention stays a raw id — which is the graceful degrade above, not
an error. `resolve_mentions` (in `capabilities(full=True)["flags"]`) is the switch, and it is the one
flag here that is **on by default**: to keep ids raw deliberately, either omit `read_client=`
or pass `Config(OutputConfig(resolve_mentions=False))` (imported from
`larkdocio.read.config`), which skips resolution entirely and never touches contacts.

**Refreshing a snapshot: RE-CONVERT the document, do not diff new output against old output.** The renderer keeps improving — a URL that used to come through as bare text is now **linkified** into a real Markdown link, and a table with merged cells that used to flatten now renders as an HTML table carrying real `rowspan` / `colspan`, and content sitting at a merge-**covered** grid position — which used to be dropped outright, text and images alike — now renders inside the covering anchor's cell. Those are deliberate improvements, and they land in the **same diff** as whatever your authors actually changed, so a diff taken across two larkdocio versions mixes the two and reads as a much bigger content change than it is. If you keep converted Markdown under version control, re-convert the whole document with the new version, commit that as its own step, and diff content only between snapshots produced by the **same** version. `larkdocio.release_notes()` names every rendering change per release, so you can tell in advance which refresh will move output; re-pinning is the moment to expect it.

### Where the file lands: `-o`, and `--route` when you name the subpath

**`-o` is the output directory, exactly as you gave it.** The reader does not read the
converted document to decide where the converted document goes: there is no body sniffing, no
title parsing, no metadata-table grammar, no filename heuristic and no defaulting from
document content. A download lands flat in `-o` unless *you* say otherwise.

> **Changed in 1.49.0 — read this if you upgrade.** Earlier releases scanned the rendered
> Markdown for a particular set of key/value table rows and, when all of them were present,
> wrote into a subpath derived from their values — on by default, announced at warning level.
> That derivation is **gone**. Deciding where a document belongs is the caller's job, and a
> caller who wants a derived subpath derives it and passes it as `--route`. A document that
> used to land in a derived subdirectory now lands directly in `-o`; if you keyed anything on
> that location, read `result.output_dir` rather than globbing the tree. The config key that
> switched the derivation off was accepted and ignored, with a notice, up to 1.52.0. **A retired
> output key from earlier versions is no longer accepted:** passed to the `OutputConfig(...)`
> constructor — as a keyword, or as a fifth positional argument — it raises `TypeError`, and in
> `config.json` it is ignored like any other unknown key. Remove it from both.

**The one way to place output under a subpath: `--route SUBPATH`.** It writes beneath `-o`
(e.g. `--route area/section/topic`) — **you** supply the path and larkdocio infers nothing
from the document. Each segment is sanitised through `sanitize_path_string` (spaces become
underscores, the OS-reserved characters `\ / : * ? " < > |` are stripped) but is **not**
lower-cased: the caller's spelling is the caller's. An absolute path, a `.` or `..` segment,
an empty segment, and **a segment that stripping leaves nothing of** (`--route '***'`) are each
**refused with the reason named**, never silently normalised — a supplied subpath cannot escape
`-o`, and no directory name is invented for you. That last refusal is new in 1.51.0: such a
segment used to become the literal directory `untitled`, so output landed under a path nobody
had named. A document *title* that strips to nothing still becomes a name — something has to be
written, and the download prefers the document token — but it now says so in the log. A TRAILING separator is a harmless convenience and
is tolerated; a LEADING one is not — `/area/section` is an absolute path and is refused by
the rule above.

```
larkdocio download <url> -o ./out --route area/section/topic
```

The command line says so as it happens, at **warning level** — `Routing to the
caller-supplied --route path: …` — so a library caller who attached no handler and configured
no logging still sees it on stderr through Python's `logging.lastResort` fallback, which emits
at warning and above. That is the case where larkdocio wrote somewhere other than the bare
`-o`, and warning is the level at which a caller who is not listening still hears it.

**Do not pre-build the subpath into `-o` as well — it double-nests.** Pass the root as `-o`
and the subpath as `--route`.

**A program does not have to read any log line.** The decision is returned as data on the
download's own result — `result.routed`, `result.route_reason`, and `result.route` for the
whole record. With `--dump` the same record is written into the sidecar under `route`, so a
bulk pipeline gets it out of a file rather than out of log text. **The record carries no path** — not the
output root, not the supplied subpath — because the sidecar is byte-identical
between two runs over an unchanged document and a path is specific to the machine and the
invocation; where the file went is on the returned value, which is not a file that has to stay
comparable.

`reason` is one of exactly two values: `explicit_route` when you passed `--route`, and
`routing_disabled` when you did not — the library derives none, so the root is used as given.
The record's other three keys (`derivation_ran`, `labels_found`, `labels_missing`) are still
answered, always, and are now permanently `false` / empty / empty: nothing is looked for, so
nothing is found and nothing is missing. They stay in the shape because a key that appears
only sometimes is harder for a consumer to read than a key that is honestly empty.


**What the file is called is a second, separate rule — and it is welded to
`title_as_filename`** (default `true`). With that key at its default there are two shapes, and
turning it off gives a third:

| `title_as_filename` | The document's title | The filename |
|---------------------|----------------------|--------------|
| `true` (default) | anything that survives normalization | `[YYYY-MM-DD_HHMM]_Example_Document_Title.md` |
| `true` (default) | empty, or normalizing to `untitled` | `[YYYY-MM-DD_HHMM]_<document token>.md` |
| `false` | irrelevant | `<document token>.md` — **no timestamp at all** |

**A long title is shortened, and the budget is in BYTES.** The title is cut to fit a
filesystem's per-component ceiling — 255 **bytes**, not 255 characters — with room reserved
for the stamp and the extension, and the cut always lands on a whole character so the name
stays valid text. That distinction is the whole point: a Chinese, Japanese or Korean character
is 3 bytes in UTF-8, so a title that reads as well under a hundred characters can be three
hundred bytes long. Until 1.51.0 the cut counted characters, and a CJK title of 79 or more
characters **failed the write with an `OSError`** after the download had already succeeded;
that title now writes, shortened. An ASCII title is unaffected — the name is what it always
was.

The stamp is **UTC**, taken when the file is written — so the name is a function of the instant
alone and does not follow the machine's zone. Two downloads of one unchanged
document produce two differently-named files with identical content. If you want a stable,
repeatable filename — to overwrite in place, or to key a cache on it — `title_as_filename:
false` is the knob that gives you one. UTC is the default; pass `--local-time` on the
`download` command to stamp in the machine's own zone instead — the same
`[YYYY-MM-DD_HHMM]_<title>.md` shape, only the digits move and no zone suffix is added — at
the cost of a filename ledger that becomes machine-dependent (the same document downloaded at
one instant on two machines in different zones then lands under different names).

### What the run did not fetch — the end-of-download summary

A document can **reference** content that lives outside it: an embedded sheet, an embedded
Base, a synced block. The reader never drops one silently — each names itself **and its
token** where it sits in the Markdown, which is the right answer when you are reading one
document. Across sixteen it is the wrong granularity: the question is no longer *"what is in
this paragraph"* but *"what did this run not get"*, and answering it by grepping sixteen files
for four marker strings is not an answer.

So a download **ends by saying it**. When a document referenced something this run did not
fetch, the command logs a count per class and then, for each class present, what you can
actually do about it:

```
This document references 2 embedded sheets, 1 embedded Base and 1 synced block that were not fetched. Each one names itself and its token where it sits in the Markdown.
Embedded sheets: pass --deep-read-sheets to read them as inline tables.
Embedded Bases: pass --deep-read-bases to read them as inline tables.
Synced blocks: never fetched — the content lives in another document, and reading it needs a grant this integration usually does not have.
```

**Read the guidance lines literally — they are not three ways of saying "pass a flag".** The
two deep-readable classes (sheets and Bases) each have a command-line switch; the synced block
does **not**, and the summary is careful not to promise a route that does not exist:

| What was referenced | Why it was not fetched | What turns it into content |
|---------------------|------------------------|----------------------------|
| an embedded **sheet** (block type 30) | the sheet deep read is off — the default | `--deep-read-sheets` on the command line, or `deep_read_sheets` in process |
| an embedded **Base** (block types 18 and 53, reported as one class) | the Base deep read is off — the default | `--deep-read-bases` on the command line, or `Parser(deep_read_bases=True, base_client=…)` in process |
| a **synced block** (block type 50) | never fetched, by design | nothing — the content lives in another document and reading it needs a read grant this integration usually does not have |

A fourth case hides inside the first two: a deep read that was **turned on**, attempted, and
came back with nothing (a stale token, a table that no longer exists, a missing scope). That
degrades back to the placeholder rather than failing your download — which is the right
behaviour and also the reason it has to be *said*, because from the output a silent degrade
and a switched-off flag look identical. The summary distinguishes them: *"1 embedded sheet was
deep-read and the read did not come back; it kept its placeholder."*

**A clean document says nothing.** This is a disclosure, not a per-run banner — no line is
logged when there was nothing left unfetched, so the line appearing at all is information.

Two more properties worth knowing. It is **free**: the summary is assembled from the document
tree the reader already built, so it costs **zero** extra API calls and never opportunistically
fetches anything to find out what is there. And it is a **projection of the same nodes** the
per-block markers come from — it can not disagree with them, and it does not replace them: the
markers remain where the tokens are read.

**For a pipeline rather than a person**, `--dump` carries the same thing machine-readably. The
sidecar's `unfetched_references` gives `total`, `by_class`, `by_reason` and one entry per
reference with its identifying token — and, unlike the log, it states an explicit zero, so a
ledger can tell a clean run from an old sidecar. Its `route` key does the same for the routing
decision: `routed`, `reason`, `derivation_ran`, and the two label lists.

**The version anchor a ledger compares between runs — one number, per document, and it does
not cost you the document.** If you keep a record of what you ingested, the question on the
next run is *"did this move since I last saw it?"*. The answer is the document's own
`revision_id`, and there are two ways to hold it:

| Where you get it | How | What it costs |
|------------------|-----|---------------|
| the read you were already doing | `docx, blocks = client.get_docx_content(token)` → `docx.revision_id` | free — you already paid |
| the anchor **on its own**, without reading the document | `client.read_document_revision(token)` | **one** metadata call, no block tree |

Four things about it, because a ledger will act on them:

- **It is comparable to ITSELF ACROSS TIME and to nothing else.** It is per document: comparing
  one document's number with another's — or with a spreadsheet's `revision` or a Base table's —
  means nothing.
- **It is monotonic, and a read never moves it.** Measured on a disposable: a single block
  insert took it from `2` to `3`, and two back-to-back reads returned the same number, so
  polling it is inert. A moved value means *something* in the document changed and says nothing
  about *what* or *where*; an unmoved value means no write landed between the two reads. If you
  need certainty about content, compare the content.
- **The cheap route and the expensive one cannot disagree.** `read_document_revision` returns
  the **same** number `get_docx_content` reports at the same moment — measured both before and
  after an edit — which is what makes it safe to substitute for one. It is also the value the
  writer's `STALE_DOCUMENT` guard compares, so one anchor serves both.
- **`None` means "not known", never revision 0.** An absent or unreadable value is reported as
  unknown rather than rounded down to a number a real document could hold. A refused read
  raises, exactly like any other read here — it is never laundered into "unchanged".

**There is no bulk form, and here is what was tried** (measured 2026-08-10 on two
harness-created disposable documents): the Drive `metas/batch_query` POST *answers* for a list
of docx tokens and returns `create_time`, `doc_token`, `doc_type`, `latest_modify_time`,
`latest_modify_user`, `owner_id`, `request_doc_info`, `sec_label_name`, `title` and `url` —
**not one revision field**; `GET …/docx/v1/documents?document_ids=…` came back `404`; and
`…/documents/batch_get` and `…/documents/batch_query` both came back `99992402 field validation
failed`. So **N documents cost N calls**, one each. Forms beyond those four are **unmeasured,
not refuted**. What the batch query *does* carry is `latest_modify_time`, a second-granularity
timestamp — it is a timestamp, not a revision, larkdocio does not report it as one, and two
edits inside the same second are indistinguishable in it. **`sec_label_name`** in that list is
the document's tenant **security level** — readable here, not settable anywhere in the open API;
see § "The document's SECURITY LEVEL" below for what it means, what was tried, and the
**one-token** read that ships it (`DriveClient.document_security_level`, the single-token form of
this same POST — not the bulk form this paragraph says does not exist).

### Recipe: read a sheet to Markdown

**THE ONE CALL THAT DOES THE WHOLE JOB IS `read_spreadsheet_markdown(url)`.** If what you want
is *"this spreadsheet, as Markdown"*, that is the answer and you are done — it is step (0) of
the code below, and everything after it is the long way round.

It takes the URL you were handed (or a bare `spreadsheet_token`), builds the READ client,
**walks every tab**, renders them, and — the part the hand-rolled loop below does not do —
**keeps going past a tab Lark refuses instead of losing the rest of the workbook**. Its full
treatment, including how to find out what was skipped, is § "Recipe: ghost tabs — read a whole
workbook, skipping tabs Lark refuses", the very next recipe. It lived only there until 1.35,
which is why this recipe — the obviously-named door — used to route everyone into a four-step
loop with no skip handling; that was a findability defect, not a design.

**What the rest of this recipe is for.** Query the tabs, discover each tab's used range, render
one titled GFM table per tab — the **per-tab control path**, for when you need the tab objects
themselves (filter state, merges, the revision anchor) or want to render a subset. **It does
NOT skip a refused tab**: one tab answering `90215` ends the whole read, which is precisely the
silent-gap failure the one-call form above exists to prevent. Reach for it when you need the
control, not when you want the workbook.

This is the values-only read: `fidelity` stays off, and the output is byte-identical run to
run. To add the export leg's per-cell bold/italic, use the § "Recipe: read a sheet at style fidelity (the L2 export leg)"
recipe below — it is a separate recipe because turning that leg on costs an export task, which
is a decision, not a default.

**A HIDDEN TAB IS VISIBLE TO THIS READ — IN THE OBJECTS, NOT IN THE MARKDOWN.** Each tab this
recipe hands you carries `tab.hidden`: `True` the tab is hidden from someone opening the
spreadsheet, `False` it is visible, `None` the payload did not say. **`None` is not `False`** —
"nobody said" and "the tab is visible" are different facts, and this field never reports the
first as the second, so a report that treats `None` as visible is making a claim the library
did not.

It costs you **nothing extra**: the tab query answers visibility on every tab element it
returns, so the one call this recipe already makes is the whole price. No second request, no
extra endpoint, and **no write credentials** — reading which tabs are hidden is a read.

**The rendered Markdown is unchanged, deliberately.** A hidden tab still renders under its own
`##` heading, byte-identical to a visible one, because marking it would change output that
existing consumers already compare against. If the distinction matters in your report — and for
a status document built off somebody's workbook it usually does, since a hidden tab is often a
scratch tab — **read the field and say so yourself**:

    for tab in tabs:
        if tab.hidden:
            print(f"NOTE: '{tab.title}' is hidden in the spreadsheet")

Through 1.35 this was a real gap, disclosed here as one: the read model dropped the field in
projection and the only shipped way to ask was `SheetsWriteClient.query_tabs(spreadsheet_token)`
on the **write** client. That reason is worth keeping, because the write-side call still exists
and is still the right one *for a write* — it is the verification leg a visibility write reads
its own result back through. What changed is that a read-only caller no longer needs it.

**Measured** on `GET /open-apis/sheets/v3/spreadsheets/{token}/sheets/query` with read
credentials, 2026-08-16, on a two-tab spreadsheet with one tab hidden: `hidden` came back on
**both** tab elements — `true` for the hidden one, an explicit `false` for the visible one — and
the hidden state was confirmed independently through the workbook's xlsx export, a different
route. That is the scope of the claim: this route, that day, that tenant, a `tenant_access_token`.
Whether `metainfo` or the v2 routes report visibility is **not** measured here, and this says
nothing about what scopes an app needs — only that the field rides on a read the recipe was
already paying for.

**A cell's background FILL is invisible to this read, and on some sheets the fill *is* the
data.** The values API carries a cell's value, not the colour behind it, so a sheet that
encodes meaning in cell colours — a schedule drawn as coloured bars, a status grid, a
heat-map — comes back through this recipe as its labels with the colour layer silently gone:
technically complete, semantically empty. The fill is recovered by the **same export leg** the
next recipe turns on, which reports each tab's fills as ARGB in a note above its table and
hands them to a program as `{cell: ARGB}`. If you are about to read a sheet whose colours mean
something, read § "Recipe: read a sheet at style fidelity (the L2 export leg)" first rather than this one.

**A PICTURE IN A CELL now reads as an image reference — and a picture FLOATING over cells is
invisible to this read.** Those are two different objects on a spreadsheet and they behave
differently here, so take them one at a time.

A picture that **is a cell's value** comes back as `![](<fileToken>)` — the **same** Markdown
form a document image reads as, so whatever already handles document images handles these
unchanged. The bytes are **not** downloaded by the read: the token is what you get, and you
fetch the bytes yourself from the drive media download route
(`drive/v1/medias/{fileToken}/download`), which hands them back byte-identical. Any caption is
the alt text; the cell image's pixel width and height are not carried into Markdown, which has
no portable way to say them. **This is a change in what the reader emits**: before this release
such a cell rendered as **empty**, with nothing to tell you a picture had been dropped. If you
hold output from an earlier version, a cell that was blank may now carry an image reference —
that is the fix, not a regression.

A picture **anchored over a range** is not a cell value at all, so a values read cannot see it
**in any form, under any option**, and no read op here reports one. So *"the sheet reads
clean"* does not mean *"the sheet has no pictures"* — it means this read cannot tell you
either way. If that distinction matters for your sheet, ask the tab directly:
`SheetsWriteClient.query_float_images(spreadsheet_token, sheet_id)` lists them (it is a leg of
the float-image write route, so it needs the WRITE pair — see § "Recipe: float a picture over
a SINGLE-CELL anchor (the float-image write)").

Both facts were measured on **one tenant, one day, with one small PNG, in one workbook**, using
a tenant token. Other media kinds (video, audio, pdf, gif, svg), merged ranges,
a picture written over a cell that already held a value, a user token, and whether either
picture survives the export-fidelity read are **unmeasured, not refuted** — and whether a
person looking at the spreadsheet *sees* a picture is not something an API can answer at all.

**A sheets URL goes through the same validator a document URL does — one call.**
`validate_download_url(url)` recognises `/sheets/` and `/base/` alongside `/docs/`, `/docx/`
and `/wiki/`, and returns `(domain, url_type, token)` for all of them: `url_type` is
`"sheets"` here, and it is what lets you tell what a URL you were handed actually points at.
Recognition is not reach — only a document type can be handed to `download`; a `sheets` type
is read through this surface, which is what the recipe below does. (A `?sheet=<id>` query
names a *tab*, not the spreadsheet, and is not part of the token.)

**A merged range renders blank, and a sheet merge does NOT survive the round-trip — unlike a
docx one.** This is the one asymmetry between the two surfaces that will bite you, so it is
stated here rather than left to be discovered:

| Surface | A merged region reads back as | Survives read→edit→write-back? |
|---------|-------------------------------|--------------------------------|
| **docx** table | an HTML `<table>` carrying real `rowspan` / `colspan`; a covered position emits **no** cell of its own, and whatever it holds is **absorbed into the covering anchor's cell** (after the anchor's own content, in row-major order, unmarked) | **yes** — the span is in the Markdown you are holding |
| **sheet** range | the **anchor's value**, then a **blank** cell for every covered position (GFM pipe tables have no `rowspan`/`colspan`) | **no** — nothing in the Markdown says a merge was ever there |

So a merge-covered cell is **indistinguishable** from a genuinely empty one: a spreadsheet
with `A1:B1` merged and one with a plain empty `B1` render **byte-identical** Markdown. The
geometry lives only in each tab's **`merges`** array (`tab.merges`, from the v3 tab query —
0-indexed, **end-inclusive**), which is also the authority: a covered cell that still carries
a stray value is blanked anyway, so that value is not recoverable from the Markdown either.

**The two surfaces differ deliberately, and the reason is the output format.** A GFM pipe
table must emit a cell at every column, so the sheet path has nowhere to put a covered cell's
content — and that tab's own values API returns `null` there anyway. The docx path emits HTML
with real spans, so an anchor cell exists that can carry it, which is why a docx covered
position keeps its content while a sheet one is blanked. **What Lark's own UI or export does
with content at a covered docx position is `unmeasured`** — the absorption above is
larkdocio's stated rule, not a claim to match a rendering that was never measured here.

**What to do about it.** Never try to reconstruct a merge from the Markdown. Read
`tab.merges` alongside the values, keep it, and re-issue the merge as a **merge write** (see
§ "Recipe: merge and unmerge cells") after writing the values back. If you only need to
*know* whether a blank cell is covered, `tab.merges` answers that in memory — no extra call,
because the tab query already returned it.

```python
from larkdocio.common import init_env, validate_download_url
from larkdocio.sheets import read_spreadsheet_markdown
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.table import render_spreadsheet

init_env(".env")            # FIRST: from_read_credentials() reads os.environ

# (0) THE ONE CALL. This is the whole job: url in, Markdown out, every tab walked, and a tab
#     Lark refuses SKIPPED (and disclosed) instead of ending the read. If this is what you
#     wanted, stop here — see § "Recipe: ghost tabs" for how to ask what was skipped.
whole_workbook = read_spreadsheet_markdown(
    "https://your-domain.larksuite.com/sheets/YOURSPREADSHEETTOKEN")

# EVERYTHING BELOW IS THE PER-TAB CONTROL PATH — the long way round, for when you need the
# tab objects (filter state, merges, the revision anchor) or only some of the tabs. It does
# NOT skip a refused tab: one 90215 ends this read. That is the difference, stated once.

# FROM A SHEETS URL TO A TOKEN — one call, and it hands back the API domain too.
# validate_download_url recognises /sheets/ and /base/ as well as the document shapes, and
# the type it returns is what you branch on. `domain` is the API domain
# ("larksuite.com" | "feishu.cn"), NOT the tenant host in the url — this is where you get it
# right rather than hard-coding it beside a url that disagrees.
url = "https://your-domain.larksuite.com/sheets/YOURSPREADSHEETTOKEN"
domain, url_type, token = validate_download_url(url)      # -> ("larksuite.com", "sheets", …)
client = SheetsReadClient.from_read_credentials(domain=domain)

# Ask each tab for its filter state. Leave this line out and nothing changes — a tab that
# was never asked discloses nothing, so the render is byte-identical to a filter-unaware
# read. One extra call per tab is what the disclosure costs.
tabs = [client.read_tab_filter(token, tab) for tab in client.query_sheets(token)]

# ONE VALUES READ PER TAB, then one titled table each. This is the plain read: it does not
# skip a refused tab, because there is no refused tab to skip here — for the whole-workbook
# walk that keeps going past one, see § "Recipe: ghost tabs" right after this one.
pairs = [(tab, client.read_used_range(token, tab)) for tab in tabs]
markdown = render_spreadsheet(pairs)            # values-only (fidelity=None)

# A filter hides rows from a viewer; it does NOT remove them from this read. They are still
# in `markdown`, and each filtered tab now carries a note saying which ones.
for tab in tabs:
    if tab.filter_state == "active" and tab.filtered_out_rows:
        hidden_rows = tab.filtered_out_rows                   # 1-indexed, sheet-absolute
        matrix_offsets = tab.sheet_filter.matrix_row_indexes  # 0-indexed, into the values
```

**A filter does NOT hide rows from this read — and unless you ask, nothing tells you a filter
is even there.** A values read returns every row in the used range, including the rows a
filter is hiding from anyone looking at the spreadsheet. So a person sees 4 rows, the read
sees 6, and the Markdown gives you no way to tell the two apart. The row set is *correct* — it
is the complete contents of the sheet — but it is not what a viewer sees, and if you are
summarizing or diffing a filtered sheet that difference matters.

**Which rows render is deliberately unchanged** — the disclosure is added, the row set is
not touched. Dropping hidden rows by default would silently change what every existing
caller gets back, so if you want a viewer's-eye view you filter the matrix yourself using
`matrix_row_indexes` (an opt-in render option for it is an open question, not a shipped
behavior).

**Mind the two row-numbering conventions, because they differ inside the same response
family.** `filtered_out_rows` is **1-indexed and absolute to the sheet** — the numbering a
person sees in the row gutter, and it stays absolute even when the filter covers only part of
the tab. Its neighbour `tab.merges` is **0-indexed and end-inclusive**. Reaching for one
convention while holding the other is an off-by-one that names the wrong rows, which is why
`matrix_row_indexes` exists rather than leaving you to subtract.

**`filter_state` has four values and three of them are not "no filter".** Branch on it rather
than on whether `filtered_out_rows` is empty, because an empty tuple means different things:

| `tab.filter_state` | Meaning | `filtered_out_rows` |
|--------------------|---------|---------------------|
| `not-read` | you never asked — the reader claims no knowledge either way (the default) | empty |
| `none` | asked; the tab has no filter | empty |
| `active` | asked; the tab has a filter, which may currently hide **zero** rows | the hidden rows |
| `unavailable` | asked; the filter **could not be read** (no permission, a call error) — whether rows are hidden is **unknown** | empty |

A filter read never fails your document read: a refused or unreachable filter lookup leaves
you with the full sheet contents and an `unavailable` state carrying the reason, in both the
model (`tab.filter_state_detail`) and the rendered note. It is reported as unknown rather
than as "no filter", because those are different facts and only one of them is safe to act
on. Only filter-hidden rows are covered — a row hidden **by hand** rather than by a filter is
still rendered with no disclosure.

**The version anchor a ledger compares between runs — one number, per spreadsheet.** If you are
keeping a record of what you ingested, the question you will ask on the next run is *"is this the
same version I already have?"*. The answer is the spreadsheet's **`revision`**, and it is the
same value on whichever read path you took:

| Where you get it | How |
|------------------|-----|
| the values read you were already doing | `used = client.read_used_range(token, tab)` → `used.revision` |
| the tab objects, without a values read | `tabs = client.read_tabs_revision(token, client.query_sheets(token))` → `tab.revision` |
| the raw number on its own | `client.read_revision(token)` |

Four things about it, because a ledger will act on them:

- **It is per SPREADSHEET, not per tab.** Every tab of one spreadsheet carries the *same* number —
  measured, not assumed: a values read of two different tabs returns the identical revision, and
  the spreadsheet metadata reports it once at the top. So a change in it tells you *something in
  this spreadsheet changed*; it does **not** tell you **which tab**.
- **It says "something changed", not "the values changed".** Every write bumps it and reads never
  do, but a write that changes no cell still counts — freezing a pane bumps it, for instance —
  while some presentation-only edits do not bump it at all. So treat a moved revision as
  *re-read this*, and treat an unmoved one as *probably unchanged*, never as a guarantee about a
  particular cell. If you need certainty about content, compare the content.
- **It is never invented. `None` means "not known", never revision 0.** `0` is a real revision on
  this API — a brand-new spreadsheet reports it — so an absent or unreadable one is reported as
  unknown instead of being rounded down to zero. `tab.revision_state` is what you branch on:
  `not-read` (you never asked), `known` (`tab.revision` is the anchor, possibly `0`), or
  `unavailable` (asked, could not find out — `tab.revision_state_detail` says why). Like the
  filter read, `read_tabs_revision` **never raises**: a refused metadata call costs you the
  anchor, not the spreadsheet.
- **What it costs, where you pay it.** The tab query carries no revision at all, so
  `read_tabs_revision` spends **one** extra metadata call for the whole spreadsheet — once, not
  per tab — and only when you call it. Leave it out and every tab stays `not-read`; nothing is
  fetched behind your back and the rendered Markdown is byte-identical either way. If a values
  read is already in your flow, `used.revision` is the same number for free.

### Recipe: ghost tabs — read a whole workbook, skipping tabs Lark refuses

**START HERE — one call, from the URL you were handed.** `read_spreadsheet(url)` is the
URL-first entry point (the twin of `read_base` on the Base surface and `read_folder` on Drive):
it parses the URL through the shared validator, builds the READ client for you, **walks every
tab**, and hands back the structured result. `read_spreadsheet_markdown(url)` is that read plus
the render. Both accept **either a Sheets URL or a bare `spreadsheet_token`**, and both take a
`client=` if you want to inject your own.

A URL naming something else is refused **by name, before any credential is read and before any
packet is sent**: hand it a `/docx/` link and it says so and points you at the document
download. A URL whose token region is not a token is refused **whole** rather than truncated.

**A TAB THE API LISTED CAN STILL REFUSE TO BE READ — and that no longer costs you the rest of
the spreadsheet.** `query_sheets` can hand back a tab whose values read then answers
`90215 not found sheetId`, for the very id the same API just listed. It is not rare: one
reported workbook had **20 of 22** tabs behave this way. `read_spreadsheet` therefore **skips a
refused tab and finishes the walk** — you get every tab that reads, plus a disclosure for every
tab that did not:

| What you asked | What you get |
|----------------|--------------|
| `book.pairs` | the tabs that READ, ready for `render_spreadsheet` |
| `book.skips` | one entry per refused tab — `o.tab`, and `o.skip.code` / `o.skip.msg`, **Lark's own words, unedited** |
| `book.skipped_any` | `True` when the read is partial — the one flag to branch on |
| `render_spreadsheet(pairs, skips=…)` | the same Markdown, opening with a blockquote naming the missing tabs |

Three things about that behavior are deliberate and worth knowing before you build on it:

- **It is never silent.** The skip is in the returned object *and* in the rendered Markdown, so
  a partial read cannot reach you disguised as a complete one. Passing `skips=` is what puts it
  in the Markdown; leaving it out renders exactly what it always did.
- **If EVERY tab is refused, you get an exception, not an empty spreadsheet.**
  `LarkSpreadsheetUnreadableError` (a `LarkAPIError`, so an existing `except` still catches it)
  carrying every disclosure. "I could not read any of it" must never arrive looking like "it is
  empty". A spreadsheet that genuinely enumerates **zero** tabs is not that case and returns an
  empty result normally.
- **Only a per-tab refusal is skipped.** A rate limit, a scope denial, a network failure, or a
  refusal of the tab *listing* itself all still fail the read — those are facts about your call,
  not about one tab, and swallowing them would hand you a permanently short document.

**What makes a tab do this is now MEASURED, and none of it is a filter this library will run.**
A ghost's own listing payload has been captured, from a real workbook, and it is not
distinguishable from a readable tab's: the same six keys (`grid_properties`, `hidden`, `index`,
`resource_type`, `sheet_id`, `title`), `resource_type` reporting `"sheet"` on **both** — the one
field a consumer would guess at first, now refuted rather than merely untried — `hidden: false`
on both, and the tab's own single-tab metadata GET (`sheets/v3/…/sheets/{id}`) serving the ghost
happily at `code:0`. **Nothing in the metadata discriminates a ghost from a readable tab; only a
values read does** — the same `90215` body reproduced live on a disposable, and a tab
**deleted through the API stops being enumerated immediately**, so a ghost is not simply a
deleted tab either. That is why the read quotes Lark and stops there rather than filtering your
tab list on a predicate: the shipped skip-on-refusal behaviour was already correct, and this
measurement is the *reason* it is correct, not a gap it still has to close.

One separator was observed, and it is not a licence to use it: `title == sheet_id` held for
every ghost measured (21 of 21) and for neither readable tab measured (0 of 2). **State both
numbers together** — the count alone reads as an endorsement, and the finding is the opposite of
one: it is a naming accident, not a typed field, and a real tab a human titled with its own
sheet id would be filtered out of their own document by the same rule. This library does not
ship it, and neither should you.

What this measurement did **not** reach, and therefore neither refutes nor supports: **why a
ghost exists at all** — the question underneath all of this, which nothing here answers or
could; a second, larger workbook (unmeasured — no report names its token); a
`user_access_token` read; a batched metadata query against a ghost's own ids; the tab's `filter`
and merge sub-routes; and the web UI. The refutation above is itself scoped to what it counted —
**21 ghost tabs and 2 readable tabs, on one tenant, on one day** — because a refutation is a
claim too, and this one does not generalise past what it measured.

```python
from larkdocio.common import init_env
from larkdocio.sheets import read_spreadsheet, read_spreadsheet_markdown

init_env(".env")            # FIRST: from_read_credentials() reads os.environ

# ONE CALL, from the url you were handed. read_spreadsheet_markdown walks every tab and
# SKIPS a tab Lark refuses rather than letting it end the read (see the table above);
# read_spreadsheet is the same walk without the render. Either form also takes a bare
# spreadsheet_token, and a `client=` if you want to inject your own.
markdown = read_spreadsheet_markdown(
    "https://your-domain.larksuite.com/sheets/YOURSPREADSHEETTOKEN")
book = read_spreadsheet(
    "https://your-domain.larksuite.com/sheets/YOURSPREADSHEETTOKEN")

# WAS ANYTHING MISSED? `skips` is empty on a clean workbook; each entry carries the tab and
# Lark's own code and message for it, unedited.
missed = [(o.tab.title, o.skip.code, o.skip.msg) for o in book.skips]
skipped_any = book.skipped_any            # the one flag to branch on
```

### Recipe: read a sheet at style fidelity (the L2 export leg)

The same read, plus the per-cell **bold / italic / background fill** the xlsx export carries
in its own `xl/styles.xml`. Four things about it are worth knowing before you turn it on, and
none of them is visible from the flag's name.

**The fill is the reason to reach for this leg on a colour-encoded sheet.** A cell's
background has no Markdown equivalent — pipe tables have no cell colour — so it is
**disclosed** rather than drawn: each tab gets one note above its table naming every ARGB and
the cells that carry it, with each row's contiguous run compressed to a range
(`FFFFFF00 — C2:E2, B7`). That is what makes a schedule drawn in cell colours recoverable
from the Markdown: the bar's colour *and* its position are both in the note. The same facts
are available to a program as `cell_fills(exported_sheet)` → `{cell: ARGB}`, and per cell as
`exported_sheet.cell("C2").fill_rgb`. **The colour is reported, never interpreted** — you get
`FFFFFF00`, not "in progress".

**An unread fill is not an absent fill.** `cell_fills` answers three different things and
they are worth telling apart: a **non-empty map** (these cells carry these fills), an **empty
map** (the export covered this tab and nothing is filled), and **`None`** (the fill layer was
not recovered for this tab — no export, a failed export, or the leg was never turned on). A
tab whose fills could not be read says so in its own note instead of rendering like a tab with
no colour in it. A cell the export carried with no fill has `fill_rgb` of `None`; it is never
reported as white.

**What it reads — and the reason it may look like it does nothing.** There are **two
different kinds of bold** in a Lark sheet, and this leg reads exactly one of them:

| Where the emphasis lives | Read by | Rendered without this flag? |
|--------------------------|---------|------------------------------|
| the **cell's format** — you selected the cell and made *it* bold (**whole-cell (format-level)**) | **only** the xlsx export — the values API does not carry it | **no** — this is what the flag is for |
| a **run inside the cell's text** — part or all of the text is bold as a text style (**run-level**) | the values API, in each segment's own `segmentStyle` | **yes, already** |

So if the sheet you point this at was styled by bolding *text* rather than *cells*, the
fidelity render is **byte-identical** to the values-only render — and that is the **correct**
answer, not a failed export: the emphasis was already in the output, so there was nothing to
add. The two are **layered**, never exclusive — `fidelity` only ever *adds* to the values
render, so turning it on can never drop a run's own emphasis. To see the leg act, look for a
cell whose bold is a **cell format** (`fidelity[sheet_id].cell("A9").bold` is the leg's own
answer for one cell, and it is `False` for run-level bold **by design**;
`fidelity[sheet_id].cell("A9").fill_rgb` is the same one-cell answer for its background).

**What it costs.** `fidelity` is not a flag on the values read — it is fed by a second,
**asynchronous whole-workbook export task**: `create` → **poll** → `download` → `unzip` →
`parse`, for the *entire* spreadsheet, however many tabs it has. Measured **~1.2 s** on a
small workbook. The poll loop is deliberately gentle and **bounded** —
`poll_interval=0.5s × max_polls=60` — so the **worst case is ~30 s** before it raises rather
than spinning. It also needs a **third scope**, **`drive:export`**, on top of the read
scopes; without it the export call is refused. The values-only read above costs none of
this, which is why it is the default.

**The one awkward step is a join, and it is the trap this guide already warns about.** The
export names each worksheet after the tab's **title**; `render_spreadsheet(fidelity=…)` keys
its per-tab lookup on the tab's **`sheet_id`**. A title is never a `sheet_id`, so the two
have to be joined — `exported_by_sheet_id(tabs, workbook)` is that join, shipped so the
recipe is a call rather than eight lines you have to get right: a tab whose worksheet is
missing is **omitted** (that tab renders values-only rather than borrowing another sheet's
styles), and no ambiguous match is guessed.

```python
from larkdocio.common import init_env
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.export_reader import SheetsExportReader, exported_by_sheet_id
from larkdocio.sheets.table import cell_fills, render_spreadsheet

init_env(".env")            # FIRST: from_read_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
client = SheetsReadClient.from_read_credentials(domain="larksuite.com")
tabs = client.query_sheets(spreadsheet_token)
pairs = [(tab, client.read_used_range(spreadsheet_token, tab)) for tab in tabs]

# THE COST, in one call: an async whole-workbook export task — create -> poll -> download
# -> unzip -> parse. READ creds plus the drive:export scope; ~1.2s measured, and bounded at
# max_polls=60 x poll_interval=0.5s, so ~30s worst case before it raises.
exporter = SheetsExportReader.from_read_credentials(domain="larksuite.com")
workbook = exporter.read_workbook(spreadsheet_token)

# THE JOIN: the export is title-keyed, the renderer is sheet_id-keyed.
fidelity = exported_by_sheet_id(tabs, workbook)       # {sheet_id: ExportedSheet}

markdown = render_spreadsheet(pairs, fidelity=fidelity)
plain = render_spreadsheet(pairs)                     # the same read, values-only

# THE FILLS, for a program rather than for a reader: {cell: ARGB} for the filled cells,
# {} when the export covered this tab and nothing is filled, None when the fill layer was
# not recovered at all. `markdown` already states the same fills in a note per tab.
fills = cell_fills(fidelity["3bf016"])                # -> {"B2": "FFFFFF00"}
```

- **A tab missing from `fidelity` is not an error** — its cells render values-only, and the
  tab says in its own note that its fills could not be read (unknown, which is not the same
  answer as "this tab has no fills"). `sorted(fidelity)` against the tabs you asked for tells
  you which tabs got the leg.
- **`fidelity=None` is byte-identical to the values-only render**, so the flag-off path
  costs nothing and changes nothing.
- **Nothing here writes.** The export leg is a read; it needs no write app and touches no
  cell.

### Recipe: read a Base to Markdown

A **Base** (a bitable) reads much like a spreadsheet and is a different thing underneath: its
columns are *typed fields* with their own presentation rules, so a cell's encoding depends on
the storage type **and** the picker type together. `read_base_markdown(url)` gives you the
reading form — one `##` heading and one GFM table per Base table, in the order the API listed
them. `read_base(url)` gives you the objects, which are the source of truth; `render_base`
turns those into the same Markdown later with **no second network read**.

**A Base URL's slug *is* its `app_token`,** so either form is accepted. A spreadsheet or
document URL handed to this surface is refused **by name** rather than half-attempted.

**The Base READ surface — this one — is read-only, end to end.** There is no create, no edit,
no delete *on the read path*, and nothing here touches a Base's sharing: **larkdocio does not
control a Base's shareability**, and it exposes no operation that would. There is also no
command-line flag for any of it; the Base read is a library call.

**That sentence is about this surface, not about Bases. Base WRITE ships**, on two surfaces —
`base-write` (records) and `base-schema-write` (Bases, tables, fields and views) — and both are
**on by default**, no opt-in flag. What each one actually contains is enumerated, not counted,
in § *Capability matrix*, and driven end to end in § *Recipe: the Base write handshake* and
§ *Recipe: create, rename and copy a Base (the structural handshake)*. Plan a Base as writable
and read this section for what a *read* will and will not hand you.

**Four things to know before you plan around the output.** None is incidental:

| What | What you get | Why |
|------|--------------|-----|
| A **Flow** column (the picker's *Flow*, storage type 24) | every cell carries a visible *unreadable cell* marker, never a blank | its schema is readable and its **values are returned by no read route at all**. A blank would read as "this cell is empty", which is a different fact |
| A **person / group / created-by / modified-by** cell | the display **name** only | no address, no avatar link and no id reaches the Markdown. The objects keep the raw id for a caller that can join it to a real identity |
| A **link** cell (one-way or two-way) | the linked record **ids** | following a link is **opt-in**: `read_base(url, resolve_links=True)` replaces each id with the target's primary field and publishes what it spent on `document.link_resolution`. Off by default because on is not byte-identical. See **Recipe: resolve link columns to names — and find the ones pointing at a deleted table** |
| An **attachment** cell | the file **names** | downloading the bytes is a separate, out-of-band leg — it ships (see **Recipe: the Base write handshake**), and it is a deliberate second call rather than something a read does for you. The `url` / `tmp_url` a read returns are short-lived signed links and deliberately never render |

**How much of a link survives the Markdown — stated plainly, because the honest answer is
"most of it, and here is the edge".** A Base text cell reads back as a *segment array*, and a
segment is a plain run of text, a **link**, or a **doc-mention chip** — the thing Lark mints
when a human touches a cell holding a pasted document url, replacing the url on screen with the
document's title. A chip carries **both**: the title in its text, and the real url — block
anchor included — beside it. `read_base_markdown` renders such a chip `[title](url)`,
byte-identical to how it renders an ordinary link, because both go through the same serializer.
It did not always: a chip used to render as the title alone with the url discarded, which made
a frozen `.md` snapshot silently under-record its anchors, and made the mere act of *chipping* a
cell nobody had edited show up in a diff as though the content had changed.

**Where that guarantee stops.** The chips actually observed in a Base cell are **document**
mentions, on one tenant, on one day. The chips a person (**@user**) or a group chat
(**@chat**) produces are **unmeasured** — nobody has captured one, so nothing is claimed about
what they carry, and this guide will not tell you that `read_base_markdown` is
**link-lossless** for every cell a human has touched. What it can tell you is that the rule
keys on a segment *having* a url, not on what kind of chip carries it, so a kind nobody has
seen is written down by the same rule the day one arrives. And the **plain** projection is
deliberately unchanged: `cell_text` / `plain_value` still hand back the visible text with the
url dropped — that is what "unescaped, undecorated" means, and it is the right string to key a
dict on. When you want the url, take the Markdown projection or read the segments yourself.

**And what the Markdown cannot tell you apart, plus the view that can.** A `Url` cell, a text
cell whose bare URL was autolinked, and a mention chip all render as `[text](url)`, so neither
the cell's type nor the segment's kind is recoverable from the Markdown — and the collision runs
both ways: an **unlabelled** `Url` cell is byte-identical to an autolinked bare-URL `text` cell,
while a **labelled** one is byte-identical to a chip. `read_base(url, retain_raw=True)` is the
view that keeps them apart. It hands every record its `raw_fields` — the API's own `fields`
body, key for key — so a segment arrives as the dict the server sent, with its kind on `type`
(`text`, `url` or `mention`, the three kinds captured so far), its label on `text` and its href
on `link` as separate keys, and a chip's `mentionType` still on it. In the library's own words,
*it costs no extra API call, only memory*. **Take the label and the href from `raw_fields`,
never a parse of the rendered Markdown**: a `[label](url)` pattern is wrong for every link whose
author typed a label, which is exactly the case it looks like it solves. § *Recipe: compare Base
rows on the raw values* works the retained view end to end.

**A view is not a projection.** No entry point takes a view id, because a view does **not**
narrow the columns a read returns: reading under a view with fields hidden still returns every
field, in unscoped order. What you get is the **table's** schema, in field order.

**One level down, the client hands back the vendored SDK's own objects.** `read_base(url)`
returns *this library's* assembled form — each `table.fields` entry is a `FieldSpec` — but a
caller who goes to the client itself (`BaseReadClient.list_fields()` / `search_records()`, as
the write handshake below does) gets the pinned SDK's objects, and they are a different shape: a
field there speaks `.type` (the integer storage type), `.field_name`, `.ui_type` and
`.property`. There is **no** `field_type` attribute on them — that spelling is the most common
wrong guess — and they carry no readable `repr`, so printing one tells you nothing.
`field_spec(field)` (`from larkdocio.base.table import field_spec`, exported from
`larkdocio.base`) is the one-line bridge across that seam: hand it an SDK field, a raw payload
dict, or a `FieldSpec` already, and you get the library's own frozen `FieldSpec` back —
`.field_name`, `.type`, `.ui_type`, `.property` as a plain dict, `.field_id`, `.is_primary`, and
`.pair` for the `(type, ui_type)` the renderers dispatch on.

**And the same integer wears three spellings, so name the seam once and stop guessing.** The
storage type is `field_type` where you *author* a field — `create_field(field_type=2, …)`,
`ComputedColumn.field_type` — and `type` where you *read* one, because that is the key the
payload uses: `FieldSpec(type=2, …)` and the SDK object's `.type`. Two of the three are now
forgiving: `FieldSpec` accepts `field_type=` as an alias of `type=` (naming both in one call
is a `TypeError`) and answers `.field_type` as well as `.type`. The SDK object is not ours to
widen — it has `.type` only, which is what `field_spec(field)` above is for.

**One refusal points somewhere you would not guess.** A Base's *roles* family — the advanced
permission model — answers `1254301 OperationTypeError`, and that is **not a scope denial**:
advanced permissions are switched **off on the Base itself**, and the switch is an action the
**Base's owner** takes in the product. No scope you can be granted in the Lark console reaches
it, and the API refuses to turn it on for you either (`1254302`). So if you meet that code, ask
the Base's owner — not your workspace administrator.

```python
from larkdocio.base import read_base, read_base_markdown, render_base
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: the read client resolves credentials from os.environ

# A Base URL — its slug IS the app_token, and the validator hands back the API domain too
# ("larksuite.com" | "feishu.cn"), which is not the tenant host in the url.
url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, token = validate_download_url(url)      # -> ("larksuite.com", "base", …)

# THE OBJECTS FIRST — the source of truth. Five calls per Base: the app once (for the time
# zone every date cell renders in), the table list once, then fields and records per table.
document = read_base(url)
for table in document.tables:
    print(table.name, [spec.field_name for spec in table.fields], len(table.rows))

# The reading form, two ways. render_base re-renders what you already hold — no second read.
markdown = render_base(document)
same_markdown_from_scratch = read_base_markdown(url)      # reads again, renders the same way

# EVERY ROW IS EXACTLY AS WIDE AS THE FIELD LIST — rows project against the schema, never
# against the keys a record happens to carry — so a field and its cell zip together:
first_table = document.tables[0]
for row in first_table.rows:
    print(row.record_id, dict(zip([s.field_name for s in first_table.fields], row.cells)))

# A Flow column's cells carry a marker rather than a blank, so an unreadable cell stays
# distinguishable from an empty one. Check for the marker instead of guessing at blanks:
unreadable = [
    (table.name, spec.field_name)
    for table in document.tables
    for index, spec in enumerate(table.fields)
    if any("unreadable Base cell" in row.cells[index] for row in table.rows)
]
```

**A DATE CELL IS RENDERED IN A ZONE, AND THE READ TELLS YOU WHICH — INCLUDING WHEN IT HAD TO
ASSUME ONE.** A Base date is stored as an **instant** — milliseconds since the epoch — not as a
calendar date, so *which day it is* is decided entirely by a zone. The read takes that zone from
the Base itself (`get_app`, the first of the five calls above), and three things follow:

- **A Base that declares a zone renders in it, and the round trip is exact.** Declare it at
  create — `create_base(name, folder_token=…, time_zone="Asia/Singapore")` is the one place Lark
  accepts a zone —
  and a date-only value written as local midnight reads back as the same calendar date. Measured
  across a month boundary and a year boundary.
- **A Base that declares none is rendered in an ASSUMED zone, and the read says so.** Lark
  returns no zone for a Base created without one — which is every Base this library minted before
  the zone was declarable, and every Base embedded in a document — so the renderer assumes `UTC`
  and **discloses the assumption on the result**: `document.date_zone`,
  `document.date_zone_assumed` (a bool), `document.date_zone_requested` and
  `document.date_zone_disclosure` (the sentence). The
  rendered Markdown is unchanged by this; the disclosure is on the object, deliberately, so no
  existing output moved to carry it.
- **A Base that declares a zone THIS MACHINE cannot load is the second assumption, and since
  1.51.0 it is disclosed too.** Turning a zone *name* into a zone needs a tz database, and a
  slim container (or Windows without the `tzdata` package) has none — as does any host asked for
  a name its database does not carry. The render falls back to `UTC` exactly as above. **Before
  1.51.0 that fallback was silent and, worse, `date_zone` reported the zone it had been asked
  for and `date_zone_assumed` was `False`**: the dates were converted in the wrong zone and the
  result said they had not been. Now `date_zone` is `'UTC'`, `date_zone_assumed` is `True`,
  `date_zone_requested` is the zone the Base declared, and `date_zone_disclosure` says which
  machine to install the tz database on. `date_zone_requested` is the key that separates the two
  assumptions: `None` means the Base declared nothing, a name means it declared that and this
  host could not honour it. Nothing about the two older cases moved.
- **In an assumed zone a date-only cell can read one calendar day early**, and that is the whole
  reason the disclosure exists rather than a silent default. It is not a rendering bug you can
  correct downstream by adding a day — the instant is genuinely ambiguous without a zone. The
  cure is upstream and permanent: give the Base a zone at create. **The stored integers were
  never wrong**; only the day they are rendered as, and only when nothing said which zone to use.

```text
                                 declared & loadable   | declared none | declared, NOT loadable
document.date_zone            → 'Asia/Singapore'       | 'UTC'         | 'UTC'
document.date_zone_assumed    → False                  | True          | True
document.date_zone_requested  → None                   | None          | 'Asia/Singapore'
document.date_zone_disclosure → ''                     | the sentence  | a DIFFERENT sentence
```

Read `date_zone_assumed` before you trust a date-only cell in a report. If it is `True`, the day
you are looking at is this library's best reading of an instant nobody scoped — and
`date_zone_requested` tells you whether the fix is *declare a zone on the Base* (`None`) or
*install the tz database where this code runs* (a name).

**Comments on a Base come through the comments surface, not this one** — a Base's comments are
not part of the Base API at all. Pass the Base's own token with the bitable file type:
`comments(token, file_type="bitable")`. Each reply carries the **record, table and view** the
reviewer had open, so a comment can be attributed to a row rather than only to the file (a
comment that names no row reports a *file-level* state). Reading is the half that works:
**creating, editing, resolving or deleting a Base comment is refused by Lark's own API** at
every granularity, so no path to it is exposed here.

### Record edit history — "who changed this row?" is a measured refusal

**The failure this cures.** A Base's record carries an edit history in the product UI — who
changed what, and when — and asking the open API for the same thing has no route: the wire
never returns a diff or a timeline of edits, only a snapshot of what a row holds **now**. That
is a measured refusal, not an assumption, and the routes tried are quoted here so the next
person who asks meets the answer instead of re-discovering it:

> A BASE RECORD'S EDIT HISTORY IS NOT SERVED BY THE API: no route returns what changed on a record — only who last touched it, and that is a different call entirely (see THE NEAREST SERVED THING below). Measured against a Base this harness created, edited twice, then independently re-queried after deletion (dev/editions-spike/findings.md § Leg 5, in the dev repo; tests/captures/editions-spike/captures/300-summary-leg-5-base-history.json, in the source repository). TRIED — six record/table/app-scoped spellings, each answering the gateway's own non-JSON HTTP 404 "404 page not found": bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}/history, .../records/{record_id}/histories, .../records/{record_id}/revisions, bitable/v1/apps/{app_token}/tables/{table_id}/record_histories?record_id=<id>, bitable/v1/apps/{app_token}/tables/{table_id}/histories, and bitable/v1/apps/{app_token}/histories; drive/v1/files/{app_token}/versions?obj_type=bitable, which answers HTTP 400 "1068411 params error, param [obj_type] is wrong" — the drive versions family does not cover Bases at all; and drive/v1/files/{app_token}/statistics?file_type=bitable, which answers code 0 with pv/uv/like counters only, no history of any kind. NOT TRIED, stated because a claim's scope may not exceed its evidence's — a user_access_token session on any of the above (everything measured rode a tenant_access_token); and any undocumented product-internal endpoint the web UI itself calls, which this library will not reverse-engineer.

**The nearest thing the API DOES serve is not history at all — it is who touched the row
last** — and naming that call without naming its unit and this library's own policy on it would
send you to a workaround that is not actually offered:

> THE NEAREST SERVED THING IS WHO LAST TOUCHED A RECORD, NOT WHAT CHANGED. GET …/records/{record_id}?automatic_fields=true answers created_by, created_time, last_modified_by and last_modified_time (measured on a live read; the capture was retired from the dev repo on 2026-09-18) — who created or last touched the row and when, never a diff of the row's own fields. The times arrive as epoch MILLISECONDS — a 13-digit int, e.g. 1786403626000 — a DIFFERENT unit from the drive versions family's epoch-SECOND strings (larkdocio.drive.versions), so a consumer meeting both encodings in one release and assuming one is the other is off by 1000x. AND IN THE SAME BREATH: larkdocio pins automatic_fields FALSE by its own person-data policy (larkdocio.base.client.AUTOMATIC_FIELDS) — because created_by and last_modified_by are person objects carrying personal data, and this record read costs a privacy surface for a render that uses none of it. So this is what the API SERVES, not what larkdocio EXPOSES today — a sentence sending a consumer to this call without saying so would describe a workaround the wheel does not actually offer.

Both statements are authored once, in `larkdocio.base.history`, and quoted here verbatim — see
`BASE.md`'s "Not in scope" and "Limitations & revisit-triggers" tables for the same fact in the
matrix's own shape.

### Recipe: compare Base rows on the raw values

Every value the recipe above hands back is **display-shaped**, and for reading that is exactly
right. For *computing* it is a trap. A Date arrives as an epoch and leaves as `2025/07/01`; an
Email arrives as `[{"link": "mailto:billing@example.com", "text": "billing@example.com", "type": "url"}]` and
leaves as `[billing@example.com](mailto:billing@example.com)`; a Person arrives as a list of objects and leaves
as a comma-joined display name. So the first question anyone asks of a table — *"are these two
rows the same vendor?"* — cannot be answered from what a read returns without parsing this
library's own Markdown back apart. **The most common way that goes wrong is the mailto trap:
the same address, one row carrying it as a link and one as plain text, compares as two
different vendors and the dedupe silently reports no matches.**

`read_base(url, retain_raw=True)` keeps the wire value beside the rendered one. **It is the
wire shape exactly as Lark returned it** — no key renamed, no absence coerced, no epoch turned
into a string, no list flattened or sorted, no type changed. It is deliberately **not** a
typed middle form: no `datetime`, no `Decimal`, no person class, no conversion of any kind. If you want
a `datetime`, build it from the epoch below with your own timezone opinion — the library will
not guess one for you.

**Three things to know before you switch it on.**

- **It costs no extra API call.** The payload was already received; the flag only decides
  whether it is kept, and the read makes the same five calls it always made.
- **It does cost memory — ≈7× the rendered cells** (≈260 KB against ≈38 KB on a 64-row read of
  a real four-column table), because a Lookup or Person cell that renders as a short name
  arrives as a nested structure. Retention lives as long as the read you took: drop it and the
  memory goes.
- **With retention off, the accessors refuse rather than answer.** `raw_fields` is `None` and
  `record.raw(...)` raises `RawNotRetained` naming the flag — an empty dict would be a claim
  that the cells were empty, which is a different fact from nobody having kept them.

```python
from larkdocio.base import read_base
from larkdocio.base.client import BaseReadClient
from larkdocio.base.model import ReadProof, snapshot_table
from larkdocio.base.table import assemble_table
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: the read client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

# ONE flag, and nothing else about the read changes: same five calls, same Markdown.
document = read_base(url, retain_raw=True)
table = document.tables[0]
names = [spec.field_name for spec in table.fields]

# The two forms, side by side. `cells` is positional (as wide as the field list, blanks and
# all); `raw_fields` is the wire's own name-keyed body, where an EMPTY CELL IS AN ABSENT KEY.
row = table.rows[0]
rendered = dict(zip(names, row.cells))
raw = row.raw_fields
print(rendered)                       # {'Email': '[billing@example.com](mailto:billing@example.com)', …}
print(raw)                            # {'Email': [{'link': 'mailto:billing@example.com', …}], …}

# DEDUPE ON THE RAW VALUE. An Email cell carries the address twice — once prefixed with
# `mailto:` in `link` and once plain in `text` — so the plain one is the form two identical
# addresses always share, whichever way each was entered.
def addresses(raw_fields, field_name="Email"):
    """The plain addresses in one Email cell; an empty cell is an absent key, so `()`."""
    return tuple(sorted(segment["text"] for segment in raw_fields.get(field_name, [])))

groups = {}
for candidate in table.rows:
    groups.setdefault(addresses(candidate.raw_fields), []).append(candidate.record_id)
duplicates = {key: ids for key, ids in groups.items() if key and len(ids) > 1}
print(duplicates)                     # {('billing@example.com',): ['rec…', 'rec…', …]}

# The same values survive into the SNAPSHOT the write engine takes, so a compare and the
# edit that follows it read from one object rather than two reads of the same table.
client = BaseReadClient.from_read_credentials()
meta = client.list_tables(app_token)[0]
fields = client.list_fields(app_token, meta.table_id)
records = client.search_records(app_token, meta.table_id)
snapshot = snapshot_table(
    assemble_table(table_id=meta.table_id, name=meta.name, fields=fields,
                   records=records, retain_raw=True),
    app_token=app_token,
    revision=meta.revision,
    read_proof=ReadProof.from_pages([{"items": records, "has_more": False,
                                      "page_token": None}]),
)
record = snapshot.records[0]
print(snapshot.raw_retained)          # True — every record here carries its wire body
print(record.value("Email"))          # the RENDERED cell: a Markdown mailto link
print(record.raw("Email"))            # the WIRE value: the segment array, untouched
print(record.raw("Email")[0]["text"]) # the address itself — the thing to compare on
```

**A field the table does not have is still an error.** `record.raw("Emial")` raises
`UnknownField`, exactly as `record.value("Emial")` does — a typo is a programming mistake, not
an empty answer. A field the table **does** have whose cell was empty returns `None` (or the
`default` you pass), because an empty cell really is an absent key on the wire. If you need to
tell an absent key from a `null` **value** — the two empty link forms are exactly this
distinction — read `record.raw_as_dict()` and test the key.

### Recipe: resolve link columns to names — and find the ones pointing at a deleted table

A link cell holds **record ids**, and that is all a default read returns. There are two very
different questions you might be asking about those ids, they cost different amounts, and
**answering one does not answer the other**:

| The question | What answers it | What it costs |
|--------------|-----------------|---------------|
| *Is the target **TABLE** gone?* | `table.dangling_link_columns` — a reading of the column's own configuration | **nothing.** It is already in the read you did |
| *Does this individual linked **RECORD** still exist, and what is it called?* | `read_base(url, resolve_links=True)`, then `document.link_resolution` | one field read per target table not already known, plus **one batched read per target table** (per chunk of ids) |

**The two halves rule, stated because getting it wrong is silent.**
`table.dangling_link_columns` reads a column's `property`: Lark fills in the target's
`table_name` while that table is alive and **omits it once the table is deleted**, which is the
whole free signature. The columns you actually meet in that state are the **one-way** ones — a
two-way link into a deleted table is removed outright along with its twin, so it is not there to
be read — and the reading is applied to both kinds regardless, because which columns survive is
Lark's decision and not this reading's. It therefore stays **empty when only a
record was deleted** — the target table is fine, so the column is fine. An empty `dangling_link_columns` is *not* a statement that
every linked row still exists. Only `resolve_links=True` can say that.

**Why it is off by default: bytes.** With `resolve_links` absent the Markdown is
**byte-identical** to what this library has always emitted — the ids, joined. Turning it on
replaces each id with the target's primary field, which changes the rendered output, so it is
your decision and never a default. `document.link_resolution.disclosure` prices what you spent.

**Three outcomes, and the third claims nothing.** An id that resolved carries the target's
primary-field text; an id Lark reported *absent* is `dangling` and renders a typed marker; an id
that was refused, or that arrived inside an answer about the whole table, is `unresolvable` —
which means *"not established"*, never *"gone"*. An id the resolution never saw still renders as
itself, because "not asked about" is not a finding.

```python
from larkdocio.base import dangling_link_columns, read_base
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: the read client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

# --- 1. THE FREE HALF. Already paid for by the read you were doing anyway. ---
document = read_base(url)
for table in document.tables:
    broken = table.dangling_link_columns           # same as dangling_link_columns(table.fields)
    print(table.name, [column.field_name for column in broken])
    for column in broken:
        # `state` is one of three readings, and only one of them is a claim that data is gone.
        print("   ", column.field_name, column.state, "->", column.target_table_id)
# EMPTY IS THE NORMAL CASE, and it does NOT mean every linked row still exists: a deleted
# RECORD leaves the target table alive, so this reading stays empty. That is the next half.

# --- 2. THE COSTED HALF. Opt in, and read what it spent. ---------------------
resolved = read_base(url, resolve_links=True)
print(resolved.link_resolution.disclosure)
# e.g. 'Link resolution made 2 extra API call(s) against 1 target table(s): tbl…'

for entry in resolved.link_resolution.records.values():
    print(entry.record_id, entry.state, entry.text)
# 'resolved'     -> the target's primary field
# 'dangling'     -> Lark reported the id absent: that row is gone
# 'unresolvable' -> not established. NOT a claim that anything was deleted.

print([link.record_id for link in resolved.link_resolution.dangling])
print(resolved.link_resolution.tables)         # which target tables were actually touched
print(dangling_link_columns(document.tables[0].fields))   # the same reading, as a function
```

### Recipe: read what a Lookup or Formula column rolls up from

A Lookup and a Formula column are **computed**: the server fills them, nobody types into them,
and this library refuses to write one at plan time. What a consumer wants from them is
*provenance* — where did this value come from? — and `computed_columns` is the reading that
answers it, from the schema and cells you already read.

**What comes through, and what does not.** A Lookup column reports the **table** it rolls up
from. Three other facts — **which field** it rolls up (`target_field`), **how it aggregates**
them (`roll_up`), and the **formula string** stored on it (`formula`) — arrive `unavailable`
rather than absent, and the distinction matters: **Lark does return all three on the field's
schema**; the pinned client this library reads through does not carry those keys into the
reading. So it is a transport gap on this side, not Lark withholding, and `unavailable` names it
as such instead of reporting an empty value that would read as *"it aggregates nothing"*.

A **Formula** column is unaffected — its expression and its formatter both come through.

Every column also carries a `note` written to be shown to a person: it says what the column is,
what could not be read, and whose limitation that is.

```python
from larkdocio.base import computed_columns, read_base
from larkdocio.base.client import BaseReadClient
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: the read client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

# --- 1. FROM A STRUCTURED READ. No extra call: it is already on the table. ---
document = read_base(url)
for table in document.tables:
    for column in table.computed_columns:
        print(table.name, column.field_name, column.ui_type)
        print("   rolls up from table:", column.rolls_up_from_table)
        print("   rolls up field:", column.rolls_up_from_field)      # None if unavailable
        print("   aggregation:", column.aggregation)                 # None if unavailable
        print("   formula:", column.formula_expression)              # Formula columns carry it
        print("   unavailable:", column.unavailable)
        print("   note:", column.note)
# `unavailable` is a tuple naming the keys that did NOT arrive — ('formula', 'roll_up',
# 'target_field') for a Lookup. It is the transport, not the server: Lark returns all three
# on the field schema and this library's Lark client does not carry them through.

# --- 2. OR FROM CLIENT OBJECTS you already hold, as a plain function. --------
read = BaseReadClient.from_read_credentials()
table_id = read.list_tables(app_token)[0].table_id
fields = read.list_fields(app_token, table_id)
records = read.search_records(app_token, table_id)
for column in computed_columns(fields, records):
    print(column.field_name, column.value_type, column.unavailable)
```

### Recipe: read every document in a folder

Hand the library **one folder link** and it enumerates the tree and reads every document
inside — at any depth. You get back a structured result you can iterate, plus one Markdown
document. The command line is `larkdocio folder "<url>" -o ./out/`; from Python:

```python
from larkdocio.common import init_env
from larkdocio.drive import read_folder, render_folder

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
# One folder link in. read_folder enumerates the tree, reads every document it can, and
# returns a structured result — plus render_folder serialises that result to ONE Markdown
# document: a tree index, each document under its own heading, then a disclosure of what was
# NOT read. `read_folder` accepts a folder URL or a bare folder token.
result = read_folder("https://your-domain.larksuite.com/drive/folder/YOURFOLDERTOKEN")

# THE INVARIANT THE WHOLE FEATURE IS JUDGED ON: nothing the walk saw is dropped.
assert result.accounted()          # children == read + skipped + folders, always

# Each read child carries its Markdown; each skipped child carries a reason IN LARK'S OWN
# WORDS (a refusal quotes Lark's code + msg; a file with no reader says so). A child that
# fails to read never fails the walk — the other documents still come back.
for child in result.reads:
    print(child.type, child.name, len(child.markdown or ""))
for child in result.skips:
    print("skipped:", child.name, "—", child.skip.reason)

# The one-document rendering (this is what the `folder` CLI verb writes under -o).
markdown = render_folder(result)
```

**A raw uploaded `file` child is skipped — and its bytes are still fetchable.** The walk reads
documents; nothing in this library turns arbitrary uploaded bytes into Markdown, so a `file`
child comes back in `result.skips` with a reason saying so. **That is not the same as the bytes
being unreachable**, and until 1.35 the reason said it was: `DriveFilesWriteClient.download(
file_token)` (`larkdocio.drive.files_write`) returns those bytes in memory, unexamined, on the
WRITE pair — hash them, write them to disk, do what you like with them. Measured 2026-08-15 on a
harness-created disposable: the very token the walk skipped downloaded to bytes whose `sha256`
matched the upload's (`tests/test_live_drive_bytes_leg_gate.py`, in the source repository). What the walk
declines to do is not what the library lacks — so if your ledger needs a **content** digest for
a raw file, this is the leg that gives you one, and it is the only place you can get one (see
*What a folder ledger can and cannot key on* below).

**A `code:0` from `metas/batch_query` is NOT proof the token resolved — read `failed_list`.**
This is the one thing to know before reaching for that endpoint, and it matters most if you reach
the Lark SDK **directly**: larkdocio deliberately does not serve a docx *document*'s metadata
(the recorded reason is `larkdocio.write.client.DOCX_REPLY_CARRIES_NO_URL` — read it there rather
than a restatement here), so a caller who needs it goes to the SDK, and the SDK route has a trap
in it. `POST /open-apis/drive/v1/metas/batch_query` reports `code: 0` `Success` **at the
envelope** and puts the per-token verdict in a sibling key: a token it will not resolve comes back
as an **empty `metas` array** with the reason in **`failed_list`**, e.g.
`failed_list: [{"code": 970005, "token": "<the token you sent>"}]`. **An empty `metas` under a
`code:0` is a refusal in disguise.** Check `code` alone and a refused token reads as resolved. So
iterate `metas` and match each entry by its own `doc_token` — the batch route answers in
its own order — and when `metas` is empty, read `failed_list` and quote what it says. Every leg
in this library that touches this endpoint discloses Lark's own `failed_list` code for exactly
this reason.

**"Does this folder still exist?" — TWO routes discriminate it, and the `doc_type` spelling is
load-bearing.**

1. **The folder listing** (`list_folder_children` / `list_folder_children_to_exhaustion`) — a
   folder that is gone stops answering a listing.
2. **`metas/batch_query` with `doc_type: "folder"`** — the endpoint `DriveClient.folder_name()`
   rides. A live folder token resolves; a removed one answers `code: 0` with `metas: []` and
   `failed_list: [{"code": 970005}]`. This is the route most callers miss, and `folder_name()`
   is therefore usable as an existence oracle and not only as a title read: `name is None` with a
   `disclosure` **is** the negative answer, and the disclosure now carries Lark's own code.

**The `doc_type` spelling decides whether you get an answer at all.** Send the wrong one at a
folder token — `"docx"` is the common slip — and the endpoint answers `code: 0` with an empty
`metas`: the *shape* of an answer with no answer in it, indistinguishable from a real refusal
unless you read `failed_list`. The recorded reason is
`larkdocio.base.media.WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER`, and it is why this library sends one
measured spelling per leg rather than a guess.

**What the two routes establish, and where the edge is.** Both were measured on a control pair
(one tenant, two days; other tenants, regions and token types are **unmeasured, not refuted**):

* **Positive** — a live folder token answers `code: 0` with a meta keyed to the token carrying
  `doc_type: "folder"`, an `owner_id` and a real `url`
  (`tests/captures/ld467-create-folder/captures/ld467-25-r2-metadata-of-the-empty-named-folder.json`,
  2026-08-15, in the source repository — its `title` is `""` because that probe's subject was a folder
  created with an empty name, so it establishes **resolution**, not a title). At scale: a
  folder-cleanup sweep on **2026-08-19** re-queried 43 tokens and **4 live folders** came back
  resolving with non-empty titles and an empty `failed_list` (that recording is not published).
* **Negative** — a trashed folder token answers `code: 0`, `metas: []`,
  `failed_list: [{"code": 970005}]`
  (`tests/captures/ld467-create-folder/captures/ld467-13-re-query-a-trashed-folder-token.json`, 2026-08-15,
  in the source repository), replicated by that same sweep's **36 trashed folder rows** out of the 43
  (2026-08-19).

**Neither route separates TRASHED from PURGED.** Both answer the same way for a folder in the
trash and for one that no longer exists anywhere, so **"removed" is the strongest true statement
you can make** from either of them — *"trashed"* is not measurable here, and neither is
*"restorable"*. If your ledger needs that distinction it has to come from somewhere other than
these two reads. And a **truncated** listing is not evidence of absence: `complete: False` means
the walk stopped, not that a child is gone.

**Remove a document and ONE ROUTE IN FIVE still answers for it — and it is the metadata route.**
The folder answer above has a document twin, and it is worth knowing for the same reason: a
delete here is a **trash, not a purge**, so *"it is gone"* and *"no route answers for it"* are
different sentences, and the route most likely to be believed is the one that keeps answering.
Measured **2026-08-31 on one tenant**, against **one document this project created, seeded and
then removed** with `WriteClient.delete_document` — which answered `code: 0` — probing five
routes **before** the delete, where all five resolved it, and the same five again after:

| # | route | after the delete |
|---|-------|------------------|
| 1 | `POST /open-apis/drive/v1/metas/batch_query` with `doc_type: "docx"` | **still resolves it** — `code: 0` with a meta keyed to the token, carrying the removed document's `title`, its `owner_id`, its create and modify **timestamps** and a `url`, and no `failed_list` entry at all |
| 2 | `GET /open-apis/docx/v1/documents/{document_id}` — the document meta | stops — `1770003` *resource deleted* |
| 3 | `GET …/documents/{id}/blocks/{root}/children` — the reader's own body route | stops — `1770003` *resource deleted* |
| 4 | `GET /open-apis/drive/v1/files` on the parent folder — the listing | stops naming it: `code: 0`, and the token is no longer among the folder's children |
| 5 | `GET /open-apis/drive/v1/files/{token}/versions` | stops — `1068404` *parent file does not exist* |

So **one of five** routes still answered, and it is the one whose answer looks most like the
object being fine — a full, ordinary-looking metadata record. Every route, both legs and the
verbatim request each one sent (including its `doc_type` literal) is captured at
`tests/captures/ld601-trashed-doc-routes/captures/ld601-before-r1.json` through
`tests/captures/ld601-trashed-doc-routes/captures/ld601-after-r5.json`, with the run's roll-up at
`tests/captures/ld601-trashed-doc-routes/captures/ld601-summary.json` (in the source repository).

**What this does NOT establish — and the limit matters more than the number.** None of the five
separates **trashed** from **purged**: the route that answers cannot tell you the object is
recoverable, and the four that refuse cannot tell you it is not — `1770003` says *deleted*, which
is not the same word as *unrecoverable*. So **"removed" is the strongest true statement** you can
make from any of them, exactly as it is for the folder pair above. And the scope is **one tenant,
one document, one run**, on one API domain, against a document that lived in a folder a person
could open: other tenants, regions and object types, and the application's-own-space case, are
**unmeasured, not refuted**. (On another tenant, **two of five** routes answering for a removed
document is **consumer-observed, not measured by this project**. That observation is why this
measurement was taken; it is not the source of the number above, and the number above is ours.)

**The two legs under the read, and the manifest — `walk_folder`, `folder_manifest` and
`folder --dump`.** `read_folder` is enumerate-then-read in one call. Sometimes you want only one
half: the **enumeration** without reading anything (a tree listing, an inventory, a
change-detection sweep), or the **machine-readable projection** of a read you already have.
Those are `walk_folder` and `folder_manifest`, both exported from `larkdocio.drive`, and both
take the same `DriveClient` you can hand `read_folder` through `client=`:

```python
import json

from larkdocio.common import init_env, validate_download_url
from larkdocio.drive import DriveClient, folder_manifest, read_folder, walk_folder

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded

FOLDER = "https://your-domain.larksuite.com/drive/folder/YOURFOLDERTOKEN"

# (a) THE CLIENT, BUILT ONCE. read_folder builds one for you when you do not pass `client=`;
#     walk_folder does NOT — it takes a client as its first positional argument, because it is
#     the layer below. Building it yourself is also how you choose the credential pair and the
#     domain, and how you reuse ONE rate limiter across every call below.
client = DriveClient.from_read_credentials()      # or DriveClient(app_id, app_secret, domain)

# (b) THE ENUMERATION ALONE — no document is read, no reader is touched, one listing call per
#     folder. This is the cheap sweep: what is in here, and did the enumeration finish?
#     NOTE the argument: walk_folder takes a BARE TOKEN, never a URL. read_folder accepts
#     either and parses a link for you; this layer does not, so use the shipped parse.
_domain, _kind, folder_token = validate_download_url(FOLDER)
walk = walk_folder(client, folder_token)
for walked in walk.children:                      # .children — one WalkedChild per node found
    child = walked.child                          # .child is the listing row itself
    print(walked.depth, walked.path or "/", child.type, child.name, child.modified_time)
    # child.url — THE PAVED ROAD to "what is the URL of the object I just created": list the
    # parent folder afterward and read this field back. It is `Optional[str]` (Lark's own
    # answer, never assembled here from a host + a token) — a child Lark did not hand a url
    # for reads back `None`, which is a real answer, not a missing one.
    print("  url:", child.url)
print("complete?", walk.complete, "listing calls:", walk.listing_calls)
print("by type:", walk.by_type(), "truncated:", len(walk.truncations))

# (c) THE READ, ON THE SAME CLIENT — `client=` is the idiom; one construction, both legs.
result = read_folder(FOLDER, client=client)
for outcome in result.outcomes:                   # .outcomes — one per walked child, always
    print(outcome.kind, outcome.surface, outcome.child.name)

# (d) THE LEDGER ROW — the JSON-ready projection of that same read. Built-in types only, so it
#     needs no custom encoder and no import of this library to decode later.
manifest = folder_manifest(result)
json.dumps(manifest)                              # never raises: plain types all the way down
for row in manifest["children"]:
    print(row["title"], row["type"], row["modified_time"], row["revision"]["availability"])
```

`folder --dump` on the command line writes exactly `(d)` — `<folder token>.json` beside the
Markdown in `-o`, the same naming `download --dump` uses. Its own `--help` says *"This is the
input a change-detection ledger wants"*, and it is; what that sentence does not tell you is what
you may key on, which is the next paragraph.

**What a folder ledger can and cannot key on — measured, not assumed.** Every claim here was
re-measured on 2026-08-15 against a harness-created disposable folder holding one document and
one raw uploaded file (`tests/test_live_drive_bytes_leg_gate.py`, in the source repository), because the
answer a report gave was wrong in both directions.

| Field | On which children | What it is | What it costs |
|-------|-------------------|------------|---------------|
| `token`, `title`/`name`, `type`, `url`, `parent_token`, `owner_id` | **every** child | identity, straight from the listing | free — the walk already paid |
| `created_time`, `modified_time` | **every** child | **unix epoch SECONDS, as a string** (measured: `"1786800122"`) | free — same listing row |
| `revision` | only children the run **read**, and only where the surface has one — a docx's `revision_id`, a spreadsheet's `properties.revision` | a true change counter (see § "Recipe: you re-ingested a document that never changed — the revision_id change detector") | free — it rode the read that already happened |

**So "download only what changed" IS buildable, on `modified_time` for the whole folder and on
`revision` where you read the child — and here is exactly where it stops:**

- **There is no size, no digest, no etag, no checksum and no content hash on any row.** Not one
  of `size` / `digest` / `sha256` / `etag` / `checksum` / `content_hash` / `md5` is present, on
  any child kind (asserted absent by the live gate, so this list cannot quietly rot). **You
  therefore cannot compare content identity from a manifest at all** — you can only compare the
  metadata above.
- **`modified_time` is second-granularity.** Two edits inside one second are one value, and a
  re-save that changed nothing still moves it. It answers *probably touched*, never *definitely
  different*.
- **A `revision` is not available for every child.** A raw `file` has none, a folder has none,
  and a **Base** has none at the document level (its revisions are per-table — take
  `larkdocio.base.read_base()` for those). Each such row says `availability: "unavailable"` with
  the reason **in the row**, and `REVISION_SOURCES` ships inside the sidecar so the table you are
  reading now travels with the file.
- **A revision is never fabricated.** There is no third state and no inference from a sibling; a
  read that came back without one is `unavailable`, never `0` — `0` is a revision a real
  spreadsheet and a real Base table can both hold.
- **If you need content identity for a raw `file`, you must fetch and hash the bytes
  yourself** — `DriveFilesWriteClient.download(file_token)` plus your own `hashlib`. That is the
  only route to a content digest for a Drive file in this library, and it costs one call per
  file. For a **document**, use `revision` instead; it is cheaper and exact.
- **`walk.complete` is the honesty flag you must read before trusting any of it.** It is `False`
  whenever anything was truncated, refused or met twice, and the manifest carries the same
  records under `walk`. A ledger that diffs a truncated sweep against a complete one will
  "detect" deletions that never happened.

**The deep reads are the same opt-ins, on the same spelling.** A document inside a folder can
embed a sheet or a Base, and by default those stay the traceable placeholder exactly as they do
on `download` — no Sheets or Base API call is made. To read them, pass the flags you already
know: `larkdocio folder "<url>" -o ./out/ --deep-read-sheets --deep-read-bases` (and
`--fidelity-read-sheets` alongside `--deep-read-sheets` for whole-cell style), or
`read_folder(url, deep_read_sheets=True, deep_read_bases=True)` in code. Same defaults (all
off), same cost posture, same degradation: a deep read that fails falls back to the placeholder
and never fails the child, and a child that fails entirely is disclosed and never fails the
walk. `--fidelity-read-sheets` governs **two** legs whose prerequisites differ: a docx
**embedded** sheet, which also needs `--deep-read-sheets` (without it there is no deep read to
add fidelity to), and a *spreadsheet child of the folder* (a `sheet` in the listing, not an
embed inside a document), which is read through the Sheets surface either way and so needs
**only** the fidelity flag: `larkdocio folder "<url>" -o ./out/ --fidelity-read-sheets`, or
`read_folder(url, fidelity_read_sheets=True)`. That second leg is why the flag matters on a
**colour-encoded** workbook — a schedule whose bars are cell **fills** has blank cells, so a
values-only read of it is a rectangle of empties that looks like an empty sheet; with the flag
each tab carries its fill disclosure (the ARGB against the cells carrying it) and the schedule
is readable. Off (the default) the child is read values-only exactly as before, with **no**
xlsx export issued.

**A document that is entirely a picture needs `--assets`.** A folder walk produces *text*, so a
document whose whole content is a **mindmap or flowchart** comes back by default as a bare
token and nothing else — technically read, semantically empty. `larkdocio folder "<url>" -o
./out/ --assets` also fetches every document's images and its whiteboard PNGs into **one shared
pool** beside the Markdown: `out/static/<asset token>.<ext>`, the same directory name and
token-derived filenames `download` writes for a single document, with every reference in the
Markdown rewritten to that local relative link. **Collisions are impossible by construction** —
the filename *is* the Lark asset token, which is globally unique, so two different assets can
never produce one filename; and the same token referenced by two documents is the *same* asset,
so it is fetched **once** for the whole walk and every reference relinked (a logo shared by ten
pages is one file and one call). It is **off by default** because a whole folder's
binaries are a different cost class from one document's — off, no asset call is made, no pool
directory is created, and the Markdown is byte-identical to a walk without it. A per-asset
failure is **disclosed in Lark's own words**, naming the document and the asset, in an
`## Assets not fetched` section at the end of the document as well as in the log, and the
remaining documents are still fetched. Attachments are not included — that is `download`'s own
separate config opt-in — and nothing is re-encoded, resized or converted. In code,
`read_folder(url, assets=True)` makes each read outcome *report* the refs it saw
(`outcome.assets`) without fetching anything; the fetch and the file writes are the CLI's leg
(`larkdocio.drive.fetch_folder_assets`), because `read_folder` itself writes no files.

**Read the disclosure section — it is not optional.** A real folder is a heterogeneous pile:
some children are documents larkdocio reads (docx / spreadsheets / bases), and some are not
(a raw uploaded `file`, a document a refusal hid). The rendered document ends with a
`## Not read` section listing every child that was skipped and why, and the structured
`result.skips` carries the same. **An empty disclosure section means zero misses** — so its
silence is trustworthy, and a miss is never a silent drop.

**One honesty note about spreadsheets and bases inside a folder.** The enumeration returns
Lark's own child `type`, and a `sheet` child routes to the Sheets reader and a `bitable` child
to the Base reader — but that dispatch is **asserted from the API model, not demonstrated end
to end**: no probe folder has yet contained a spreadsheet or a Base, so those two legs are
pinned by test and selected correctly, while only the `docx` leg has been run from an
enumeration on real data. Reading a document inside uses the same read surfaces (and the same
scopes) the library already provides; the folder read adds no scope of its own.

### Recipe: read the comments on a document

A document's Markdown tells you what it says. Its comments tell you what reviewers objected
to — and, when a reviewer anchored to a passage rather than to the whole file, *which*
passage. **Read them with the token alone: `comments(doc_token)` returns every comment on the
file.** The per-passage half needs nothing extra: every parsed block, and every styled run
inside a block, carries the review anchors the API reported there, so `review.for_node(block)`
is a local lookup on that same result with no extra call.

**Six things to know before you build on it.**

- **Authors are raw ids, not names — and you can resolve one yourself, in one call.** A
  comment carries an opaque `ou_…` id and no human-readable name, because this surface never
  guesses one. Turning it into a name is an explicit call on the read client this recipe
  already builds, with the same credentials:
  `client.batch_get_user_names([comment.user_id]) -> {"ou_exampleowner…": "Example User"}`. An id it
  cannot resolve is simply **absent** from the returned dict, so keep showing the raw id for
  those. **Where that verb lives, said once:** it is a method on the docx reader's own client,
  and `Client.from_read_credentials()` builds one straight from the READ pair when you are not
  already holding a client — the same constructor the comments and contacts clients have.
  `larkdocio.contacts` re-exports that class as `ReadClient` beside the forward direction
  (`resolve_user`, name → id), because both halves of the name↔id question get looked for in
  one place. It is the same call, and the same two preconditions, as @mention resolution in §
  "Recipe: download a docx to Markdown": the app's **contacts data range** must cover those
  users **and** the app must carry the field-level `contact:user.base:readonly` scope — both
  Lark console settings, neither one anything the library can request. **This is a
  precondition, not a permanent limit.** An earlier release of this guide said the directory
  lookup was simply unavailable here; that was accurate for an app without those two settings,
  and the claim moved when the settings did — so check them before concluding names cannot be
  had. To recognize **your own** application's comments, compare `user_id` against your own bot
  id — you know it, the library does not.
- **`scope` has three values, not two.** `whole-document` and `anchored` mean the API told
  us; `unreported` means the endpoint did not say. Read `scope`, not `is_whole`, unless you
  want the three-way distinction yourself, and never treat `unreported` as `anchored`.
- **Check `available` before you believe an empty list.** A failed comments read comes back
  with `available == False` and a reason — it does **not** come back as "this file has no
  comments". An empty list with `available == True` is the real "there are none".
- **`root=` is an optimization with a cost — not a better default.** Pass it and the read is
  **anchor-scoped**: only the anchors your tree carries are requested. The benefit is real and
  narrow — a document with no anchors at all costs **no API call**, because there is nothing to
  ask about. The cost is that on a document that *does* have anchors it costs the **same single
  API call** as the whole-list read and comes back with **fewer comments than the file holds**:
  it **cannot return** a **whole-document comment** at all (one attached to the file, like *"this
  is not ready to ship"*, has no anchor for a tree to carry), and a comment anchored anywhere
  your tree did not carry is missing too. Reach for it when you expect most documents to have no
  comments and want to pay nothing for them — never to get the per-block join, which you have
  either way.
- **`completeness` tells you which read you are holding.** `complete` = the file's whole comment
  list. `anchor-scoped` = the `root=` subset above, which is **not** the file's list; the
  `disclosure` paragraph says so in words too, so relaying it cannot pass a partial review off
  as the full one. `unavailable` = the read failed. And the two ways a result can be short of
  the file are separate fields, because they are separate facts: `missing_ids` is *an anchor that
  resolved to no comment* (normally removed since your read), `unanchored_ids` is *a comment no
  anchor can reach* (a whole-document one).
- **A reply is text plus images, and reactions are not read at all.** An image a reviewer pasted
  in arrives out of band, so it is on the reply as `image_tokens` and deliberately not spliced
  into `text` — check it, or a report built from `text` alone silently drops part of what was
  said. Reactions (a "like") are **not** reported by these endpoints at any granularity, so this
  surface has no reaction field and their absence from a result is **not** evidence there are
  none.

```python
from larkdocio.comments import comments
from larkdocio.common import get_read_credentials, init_env, validate_download_url
from larkdocio.model import walk
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
app_id, app_secret = get_read_credentials()
client = Client(app_id, app_secret, domain)
if doc_type == "wiki":
    node = client.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

# The document read you already do — `parse_docx_tree` gives you the nodes (and their
# review anchors); `parse_docx_content` would give you the Markdown.
docx, blocks = client.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

# EVERY comment on the file — one API call. The tree is NOT passed here: `for_node` below
# reads each node's own anchors, so the per-block join needs no scoping argument. A scoped read
# answers a narrower question — it cannot return a whole-document comment at all, since there
# is no anchor for a tree to hold. (`comments(doc_token, root=root)` is that variant; the
# `root=` note above says when the trade is worth it.)
review = comments(doc_token)
if not review.available:
    # Say so. Do NOT report this as "no comments" — you do not know that.
    print("comments unavailable:", review.unavailable_reason)
else:
    print("this read is:", review.completeness)      # "complete" | "anchor-scoped"
    for comment in review.comments:
        print(comment.scope, comment.user_id, repr(comment.text))
        if comment.image_tokens:
            # The reviewer pasted a picture; `text` alone is not all they said.
            print("   ...and image(s):", comment.image_tokens)
    if review.missing_ids:
        # Anchors whose comment is gone — normally removed since your document read.
        print("anchors that resolved to nothing:", review.missing_ids)
    if review.unanchored_ids:
        # The other direction: comments no block will ever point at (whole-document ones).
        print("comments no anchor can reach:", review.unanchored_ids)

# From ONE block to what a reviewer said about it. The same call takes a styled run, so a
# comment on a few words inside a paragraph is reachable the same way. `walk` is the shipped
# traversal — it follows every container shape, including a table's cells, so a comment left
# inside a table is not missed.
for node in walk(root):
    for comment in review.for_node(node):
        print(node.block_id, "->", comment.text)
    # The WORD-level anchors: a node's own runs. This one lookup is by attribute because a
    # block without text has no runs — it is a per-run read, not a traversal.
    for run in getattr(node, "content", None) or ():
        for comment in review.for_node(run):
            print(node.block_id, "(a run) ->", comment.text)

# One paragraph a caller can relay verbatim: the state of the read and its caveats.
print(review.disclosure)
```

A **spreadsheet's** comments read the same way — pass `file_type="sheet"`. Two asymmetries
come with it, and both are disclosed in `review.notes` rather than left to be discovered: the
API accepts a comment **read** on a spreadsheet while refusing to **create** one there at all,
and a spreadsheet comment carries **no structured cell reference** — its `quote` is often just
a cell label like `C3`, which is text the server chose, not a coordinate. Nothing in this
surface turns that text into a cell anchor.

Mapping a comment **back** to a block id through the API's relation field is not implemented
and not claimed: the field comes back empty for whole-file comments, and a passage-anchored
comment cannot be created through the API at all, so there is no payload against which such a
mapping could be verified. The direction above needs no such field.

## Task — who can open it, where it lives, and which edition you mean

### Recipe: grant a HUMAN access — and who can already read a document the app just created

**The failure this cures.** A human who reaches a document through a link is on it at whatever
the link grants rather than at a level somebody chose. This is the surface that puts a **named
person** on the object at a level you pick — and, before that, the answer to *who is on it
already*, which **depends on where the document was filed** and has two different answers.

**WHO CAN ALREADY READ IT.** `WriteClient.create_document` always takes a `folder_token` — see
§ "Where a new object goes" — so the document you filed **into a folder** is the only case a
caller of this library ever produces, and who is already on it is a fact about that folder.

* **Created INTO a folder (`folder_token=…`) → the document arrives carrying the folder's own
  rows.** Filing is not neutral: the new document **inherits its parent folder's access**, and
  every inherited row comes back with **`perm_type='container'`** — the wire's way of saying
  *this row comes from the container the file sits in, not from the file*. *Measured 2026-08-15*
  on a document a live gate created and deleted in the same run — that gate lives **in the source
  repository**, at `tests/test_live_docx_folder_acl_gate.py`: a document filed into a folder that
  gate had just made read back **one** `container` row, an `openid` at `full_access`. The
  round-4 exercise, on a folder that was already shared with people, measured **three** — two
  accounts at `full_access` and a **chat** (`member_type='openchat'`) holding `edit`. The rows
  are the **folder's**: how many there are, and who they name, is a fact about the folder you
  filed into.
* **A HISTORICAL measurement, preserved rather than deleted, of a state this library no longer
  lets a caller reach: a document filed nowhere → the member list read empty.** Zero member
  rows, and the app was the **owner** without being a member row at all — so a member read
  alone would have made it look as if nobody held anything. *Measured 2026-08-15*, the same run
  as above, before the destination became required — the arm that produced this subject "no
  longer runs, and it cannot" (the gate's own words), because an unaddressed create is exactly
  what § "Where a new object goes" refuses before any call. Kept here because the fact — what
  Lark itself does with an unaddressed object — remains true; it is not a live choice this
  library's `create_document` will honour.

Filing a document somewhere a team can see it is the only case this library's own create
produces, and it is the case most integrations run. § "Recipe: the docx write handshake",
*where the document lands*, is where the argument that decides it is passed.

**You cannot ask the FOLDER who is on it.** The members route takes a file type, and `folder`
is not one of them: Lark itself refuses it (*measured 2026-08-15* — `field validation failed`,
naming the `type` field and listing the object types it does take, `docx` among them). The
inherited rows are readable **from the document**, which is what the `list_members` call below
does; that is also why the shipped surface refuses `folder` locally rather than passing a call
through that cannot work.

```python
from larkdocio.common import init_env
from larkdocio.drive import DriveAccessWriteClient

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded

doc_token = "YOURDOCXTOKEN"
access = DriveAccessWriteClient.from_write_credentials()

# GRANT. The grantee is an EMAIL (resolved through the shipped contacts lookup) or an open_id
# you already hold — exactly one of the two. `full_access` is the manage level; `edit` and
# `view` are the same call with a different perm.
outcome = access.grant_access(doc_token, email="someone@example.com", perm="full_access")

# A BASE OR A SPREADSHEET IS THE SAME CALL PLUS ITS TYPE. Say it in larkdocio's own words
# (`docx` / `sheets` / `base`) or Lark's (`docx` / `sheet` / `bitable`) — every verb here takes
# `obj_type`, and a token with no `obj_type` is addressed as a docx.
base_app_token, spreadsheet_token = "YOURBASETOKEN", "YOURSHEETTOKEN"
on_the_base = access.grant_access(base_app_token, email="someone@example.com",
                                  perm="edit", obj_type="base")
on_the_sheet = access.grant_access(spreadsheet_token, email="someone@example.com",
                                   perm="view", obj_type="sheets")

# OR HAND IT THE URL and name no type at all — the type and the token come out of one parse.
from_a_link = access.list_members("https://your.larksuite.com/base/YOURBASETOKEN")

# THE VERDICT IS THE READ-BACK, not the call's own success. This endpoint family was measured
# ACCEPTING a member write and not storing it, so every op here re-reads the member list and
# tells you what it FOUND.
if not outcome.stored:
    print("accepted but NOT stored — the member list does not carry it:", outcome.stored_perm)

# RAISE, LOWER, and TAKE IT BACK — the same surface, each read back the same way.
access.update_access(doc_token, open_id=outcome.open_id, perm="edit")     # lower
access.update_access(doc_token, open_id=outcome.open_id, perm="full_access")   # raise
access.revoke_access(doc_token, open_id=outcome.open_id)   # removes the row, no tombstone

# READ who is on it — and the OWNER, which is NOT a member row: a reader who checked only the
# member list would conclude the app holds nothing, and that reading is wrong. The rows you get
# back depend on where the document was filed (see the two cases above): a document created with
# no folder has none of its own, while one filed into a folder carries the folder's, each marked
# perm_type='container'.
listing = access.list_members(doc_token)
print("owner:", listing.owner_id,
      "members:", [(m.member_id, m.perm, m.perm_type) for m in listing.members])
inherited = [m for m in listing.members if m.perm_type == "container"]
print("inherited from the folder this document was filed into:", len(inherited))

# THE TWO DOCUMENT SETTINGS whose names govern copying. One key per call (the shape they were
# measured in), each read back, and the accepted values fenced to the two that were measured.
result = access.set_copy_permissions(doc_token, copy_entity="anyone_can_view",
                                     security_entity="anyone_can_view")
print("stored:", result.stored, [(s.key, s.stored) for s in result.settings])
```

**A bare display NAME is refused before any call**, with a message that asks for an email —
**and names the verb that does answer a name**: `larkdocio.contacts.resolve_user(name="Ada
Lovelace")` returns exactly one `open_id` or refuses in a typed way, and you pass that back here
as `open_id=`. It stays a separate call because it searches the directory on its own scope, and
a name matching two people is a question only you can settle. The other half of the rule matters
just as much — when an address does not resolve, that means *the lookup did not resolve it
here*, never *no such person*: the address route's measured reach is two addresses, and whether
it answers for an arbitrary member of a tenant is unmeasured.

**WHICH OBJECT TYPES.** `docx`, `sheet` and `bitable` (Base) are **measured** — a grant, a
revoke and a member read on a spreadsheet and on a Base that a live gate created and deleted in
the same run, each judged by its own read-back, plus a level update on the Base. Everything else
is **refused locally by name**: `file`, `wiki` and every other `type=` value as unmeasured —
not proven impossible — and `folder` on evidence rather than on silence, because on 2026-08-17
(one tenant, one application identity, `tenant_access_token`) a grant addressed to
`drive/v1/permissions/<token>/members?type=folder` answered **HTTP 403 · `1063002` "Permission
denied"** on three enumerated write spellings. That claim is exactly *Lark refused the write*
and nothing wider — never *the grant did not store*, because this tenant has no folder
member-read to tell those two apart; the refusal you get back carries the whole measurement and
the scope it was made in. A wiki node is a wrapper: resolve it to the underlying token and type, then grant on
that. And if Lark answers `1063001 Invalid parameter`, you get Lark's own code and message
**plus** what that code means on this family and which knob answers it — the type this library
sent on your behalf is usually the part that did not fit.

**What this cannot tell you.** Whether a human's **⌘C then works**. No endpoint reachable with a
tenant token reports the effect of a member level or of these settings on copying, printing or
pasting in the Lark client, so this surface reports what **stored** and nothing about what a
person can then do. The mechanism people reach for — a `view` member on a document whose
`copy_entity`/`security_entity` default to `anyone_can_edit` — is a **hypothesis** consistent
with every measurement here and proven by none of them.

**What is not offered, and why.** There is **no ownership transfer**. The route works — it was
measured — and it is deliberately unshipped, because it is **one-way from the app's side**: the
transfer stores, and afterwards the app cannot delete the document, cannot re-add itself as a
member (the re-add is accepted and silently not stored) and cannot transfer ownership back.
Forms tried were `remove_old_owner=false`, transfer-then-transfer-back and a member re-add;
`remove_old_owner=true`, a transfer to a third party and any admin route are **untried, and
untried is not impossible**. There is **no group or department grantee** either: exactly one
call was ever made with a department member type and it carried a synthetic id, so whether
group grants work is **unmeasured rather than refused**. Finally: this grants a **human**
access to an object the **app owns**. It never widens, requests or escalates the app's own
scope — a grant of app scope stays a Lark console action.

### The document's SECURITY LEVEL — readable, not settable, and it can gate an edit before you get here

**Read this if a person tells you they were stopped from editing.** A tenant can carry a
**tenant security level** policy on a docx that requires a **human** to choose a level in
the Lark client before editing is allowed at all: the client asks for a level first, and editing
opens only once one is chosen. Nothing about this is visible from outside that dialog, and no
scope grants around it: it is a client-side gate this library cannot see coming and cannot open.

* **It is READABLE.** `sec_label_name` on `POST /open-apis/drive/v1/metas/batch_query` (see
  § "What the run did not fetch — the end-of-download summary", under *There is no bulk
  form, and here is what was tried* — the same call) carries it: on
  the fixture whose level the maintainer had just set by hand it read back **`"Label A"`**, against its
  own **before control** — the identical call, identical token, taken earlier the same day before
  the document was ever opened that time — which read `""`. A **negative control**, an object with no
  level ever set, also reads `""` on the same key. So `""` means *no level*, never *this object
  has no such field*, and the `"Label A"` is attributable to the human's click and to nothing else.
* **It is NOT SETTABLE through this library, or through any open-API route found.** In the
  vendored SDK, `sec_label*` appears only on **response** `Meta` models
  (`drive/v1/model/meta.py`, `docs/v1/model/meta.py` — `sec_label_name`; `base/v2/model/meta.py`
  — `sec_label_id` / `sec_label_type`, a model no route in the SDK serves) — no request body, no
  PATCH, no dedicated resource anywhere in the package. Forms tried and refused rather than
  assumed: every `"/open-apis/…"` route literal in the SDK filtered on
  `security|label|classif|grade|level|secret` (survivors are unrelated — VC room levels, HR job
  grades, glossary taxonomy, audit-log models); the base-app `meta` route the dangling
  `sec_label_id` model would belong to; and three guessed spellings of a dedicated route — each
  of the four answered **not found**. **No write was attempted anywhere** (there was no
  write-shaped route to aim one at) — not on this fixture, not on a disposable.
* **What is unmeasured, not refuted.** Everything above ran on a **tenant access token**, on
  **one tenant**, against a **docx**: a **`user_access_token`** on any of these routes is
  untried; the **admin / console** APIs, where a tenant-wide classification taxonomy would
  plausibly live, are untried; product-internal endpoints the web client itself calls are
  untried; whether **`"Label A"` is a localised display string** rather than a stable id is unknown
  — the unused `base/v2` model naming a separate `id`/`type` pair suggests such a pair exists
  somewhere; and **whether the level gates the open API at all is unmeasured** — every write
  this project has ever made to that fixture succeeded both before and after the level was set,
  so no denial has ever been observed to attribute to it. Object types other than docx are
  untried beyond one no-level Base control.
* **The confound this sits beside.** The maintainer's *"I can copy and paste now!"* (the § "Recipe: grant a HUMAN access — and who can already read a document the app just
  created" recipe just above) landed in the **same sitting** as **three** things moving at
  once: the member level this library granted, the two `copy_entity` / `security_entity` keys
  this library set, **and** this hand-set tenant security level. Nothing here, and nothing in that
  recipe, may present the library's two levers as the cause of a working paste — the level is a
  third variable neither lever controls or observes, and a one-click anecdote is not an
  attribution.
* **This is a Lark client / console action, never this library's.** Same shape as the
  access-grant recipe above: larkdocio **describes** the requirement and, where a call is
  denied, surfaces Lark's own denial body verbatim — it never adds a code path that requests,
  widens or escalates a scope or a classification. Setting a security level is something a
  **human** does in the Lark client, or an administrator in the console; no grant changes that.

**THE LIBRARY READS IT FOR YOU — one call, READ credentials, nothing to hand-roll.**

```
from larkdocio.drive.client import DriveClient

level = DriveClient.from_read_credentials().document_security_level("<your docx token>")

level.level        -> "Label A" — exactly what Lark said, never normalised, mapped or ranked
level.no_level_set -> True when Lark answered "" — which MEANS no level is set
level.outcome      -> "level-reported" / "no-level-set" / "not-answered"
level.disclosure   -> set ONLY in the third case: the key was absent, or the call could not answer
```

Until 1.36 this section ended by telling you to make the call yourself, because no shipped
operation returned the field. That is superseded — the reason it said so has not changed (a
documentation change does not grow a capability), only the conclusion, now that the capability
landed. What you were **never** being sent to is a private API: the field rides
`POST /open-apis/drive/v1/metas/batch_query`, a **documented open-API route this library already
calls** for other reasons (a folder's own title, and the owner leg of § "Recipe: grant a HUMAN
access — and who can already read a document the app just created"), and
`DriveClient.document_security_level` is a sibling leg on that same route:

```
POST /open-apis/drive/v1/metas/batch_query
{"request_docs": [{"doc_token": "<your docx token>", "doc_type": "docx"}], "with_url": false}
→ data.metas[0] carries sec_label_name beside title, owner_id and latest_modify_time
```

**ONE token per call.** The endpoint accepts a list; this leg sends exactly one entry, and the
batched form is not shipped. **`doc_type` defaults to `docx`** — the one object type the field
was measured on — and any other value is passed through so Lark answers for it rather than this
library refusing a type it never tried. **THREE ANSWERS, NOT TWO:** a level, or `""` meaning *no
level is set*, or a **disclosure** that the call could not answer — an empty string is never
invented to stand in for the third case. **Nothing here writes**: the leg declares
`mutates: False`, and there is no route to write a level with anyway.

**Measured 2026-08-15** on a harness-created disposable docx: the reply carried the
`sec_label_name` key with the value `""` — *no level set*, which is the same reading the negative
control gave and is distinguishable from the `"Label A"` the human's click produced above
(`tests/test_live_drive_bytes_leg_gate.py`, in the source repository, asserts the key is present — and
since 1.36 it takes that measurement **through `DriveClient.document_security_level` itself**, so
the gate proves the shipped call rather than a hand-rolled one, and a route change reddens rather
than silently making this paragraph wrong).

**Verification label: `measured`** for *the key is present and readable on a docx token via that
route, on a tenant access token, on this tenant*. **Unmeasured, not refuted:** the same route
under a `user_access_token`; object types beyond docx and one no-level Base control; and whether
`"Label A"` is a stable id or a localised display string. Nothing here is a workaround and nothing
here is settable — see the bullet above: setting a level is a human's action in the Lark client.

The two existing bare mentions of the key elsewhere in this guide (the batch-query key list in
§ "What the run did not fetch — the end-of-download summary", and the embedded-Base passage in
§ "What the projection drops — three directions, stated separately") point back here rather than
repeating this explanation.

### Recipe: create a folder to organise into — and the one thing it will do that surprises people

You can upload into a folder (above) and read a folder tree, and now you can **make** a folder:
`create_folder` puts one folder inside a parent folder you name. That is the whole verb, and it
is the only organize verb this library ships — see the fence at the end of this recipe before
you plan around anything else.

```python
from larkdocio.common import init_env
from larkdocio.drive.folders_write import DriveFoldersWriteClient

init_env(".env")            # FIRST: every client resolves credentials from os.environ

parent_token = "YOURFOLDERTOKENHERE"   # REQUIRED — the folder the new one goes inside

# A create is a WRITE, so it takes the write pair. The parent is ALWAYS yours to name.
folders = DriveFoldersWriteClient.from_write_credentials()
created = folders.create_folder("Q3 reports", parent_token)

print(created.token)          # pass this to put_file_in_folder as its folder_token
print(created.url)            # LARK'S OWN url for the folder, or None if Lark sent none
print(created.name, created.parent_token)   # echoed, so one ledger row is complete
```

**The answer carries exactly two things, because that is what Lark sends.** A successful create
answers a `token` and a `url` and nothing else — measured, not assumed. The `url` is Lark's own
answer: when Lark omits it you get `None`, never a URL assembled from a host and a token, because
a constructed link is a guess wearing the shape of an answer.

**CREATING THE SAME NAME TWICE MAKES A SECOND FOLDER.** This is the one behaviour to plan around.
Creating a folder whose name already exists under the same parent answered `code:0` with a
**distinct token**, and the parent's own listing then showed **two folders whose names are
byte-identical** — no de-duplication, no rename, no reuse of the first folder, and no warning.
The library does **not** pre-check for a duplicate before creating: a look-then-create is a race
it cannot win. If you need one folder per name, list the parent yourself and decide — and if you
run the same automation twice, expect two folders unless you did.

**The destination is always yours, and both halves of that are measured.** `name` and
`parent_token` are required and are refused *locally, before any call*. Omitting the parent is
refused by **Lark** (`99992402 field validation failed`, `folder_token is required`), so there is
no default-parent behaviour to lean on; sending the parent as the **empty string** is *accepted*
by Lark and puts the folder in **the calling app's own root** — a destination the library did not
pick, so it refuses that rather than passing it on. An **empty name** is likewise accepted by Lark
and stored as the empty string, so that refusal is the library's own and says so instead of
blaming the server.

**When it refuses, it says what happened and what to do.** A parent nothing resolves, a parent
this app cannot reach, and a parent token that is **not a folder at all** (a real file token was
refused this way) all come back as Lark's one `1061002 params error.`; `DriveFolderCreateError`
names all three possibilities, diagnoses none, and says nothing was created. Any code nobody has
measured is surfaced with Lark's own `code` and `msg`, undecorated.

**THE REST OF THE ORGANIZE RUNG IS NOT SHIPPED, and that is the scope rather than an oversight.**
There is **no move, no rename, no copy, no bulk "organise by type" helper,
no shortcut and no folder delete** — one product ruling opened one verb. Read the reasons as data in
`larkdocio.drive.folders_write.R3_NOT_SHIPPED`, one row per absent verb. Two consequences worth
saying out loud: a folder this library creates is **permanent as far as this library is
concerned** (the Drive delete route was measured removing a folder and is deliberately unshipped,
so a caller who needs that makes the call themselves), and **no create-time de-duplication exists
at all**, which is the other half of why a repeated run makes a second folder. What you *can* do
now is look before you create: `DriveClient.find_children_by_name(parent_token, name)` lists the
parent and hands back every child already carrying that name — subfolders included, since the
listing does not distinguish — so the same skip-or-proceed decision the upload recipe describes
is available here. The library still pre-checks nothing on your behalf: a look-then-create is a
race it cannot win.

### Recipe: you re-ingested a document that never changed — the revision_id change detector

**The failure this cures.** A ledger re-downloads twenty documents every night because it has
no way to ask *"did this move since I last looked?"*, or — worse — it skips one that did move
because it keyed on something that does not track edits. The library already surfaces the
answer: a docx's **`revision_id`**. This recipe is the loop, and the paragraph after it is what
the number does **not** tell you.

**It costs one metadata call.** `read_document_revision(token)` is the first half of what
`get_docx_content` already does — the meta reply, no block tree — so deciding whether to
download is far cheaper than downloading. If you were going to read the document anyway, take
`docx.revision_id` off the read you already paid for instead; the two **cannot disagree**
(§ "What the run did not fetch — the end-of-download summary" has the two-route table and the
measurement).

**The last leg of this recipe AUTHORS a paragraph, so the authoring rule applies to it: do not
edit the document while it runs.** The plan is built against the tree it just read, so a
concurrent human edit makes the engine **refuse rather than guess** — it refuses the whole batch
with zero writes issued rather than writing into a position that moved, and here that refusal is
the feature under demonstration, since it is the very revision this recipe teaches you to record
that arms it. A busy document just needs a re-download and a **re-plan** (cheap — one read). See
§ "Do not edit the document while an authoring session runs (the concurrency doctrine)".

```python
import json
import pathlib

from larkdocio.common import get_read_credentials, get_write_credentials, init_env
from larkdocio.model import plain_text, walk
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import Anchor, InsertPosition, InsertRequest, WriteClient, apply, compose, dry_run

init_env(".env")
domain = "larksuite.com"   # the API domain, NOT your tenant host — see "`domain=` is the Lark **API** domain"
doc_token = "YOURDOCTOKENHERE"

read_app, read_secret = get_read_credentials()
client = Client(read_app, read_secret, domain)

# --- THE LEDGER ------------------------------------------------------------------
# Whatever you already use — a JSON file here, so the recipe is complete. One row per
# document: the revision you last ingested at. Nothing else is needed to detect change.
ledger_path = pathlib.Path("ingest-ledger.json")
ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}

# --- THE QUESTION ----------------------------------------------------------------
# ONE metadata call. No block tree, no images, no parse.
current = client.read_document_revision(doc_token)
last_seen = ledger.get(doc_token)
print("last ingested at:", last_seen, "| head is:", current)

if current is None:
    # "not known", NEVER revision 0. An unreadable anchor is never laundered into
    # "unchanged" — treat it exactly as you would treat a failed read.
    raise SystemExit("no revision anchor for this document; re-check the token and scopes")

if current == last_seen:
    print("unchanged since the last ingest — nothing downloaded")
else:
    # ONLY NOW do you pay for the document.
    ingested, ingested_blocks = client.get_docx_content(doc_token)
    tree = Parser(Config()).parse_docx_tree(doc_token, ingested_blocks)
    print("re-ingested", len(ingested_blocks), "blocks at revision", ingested.revision_id)
    # The read's own anchor and the cheap route agree — record either.
    ledger[doc_token] = ingested.revision_id
    ledger_path.write_text(json.dumps(ledger, indent=2))

# --- POLLING IT IS INERT ---------------------------------------------------------
# A read never moves the number, so a detector may run as often as you like.
assert client.read_document_revision(doc_token) == current

# --- AND WHEN SOMEBODY EDITS -----------------------------------------------------
# The demonstration leg, so the claim above is falsifiable rather than asserted: one
# authored paragraph through the ordinary write gate, then ask again. Point this at a
# document you own — § "The disposables doctrine" is how to make one to try it on.
write_app, write_secret = get_write_credentials()
writer = WriteClient(write_app, write_secret, domain)

# A plan is built against a tree you JUST read — so this leg reads it, whichever branch above
# ran. Reusing a tree from an earlier turn is how a plan goes stale; the concurrency doctrine
# section named in the prose above has the rule.
docx, blocks = client.get_docx_content(doc_token)
tree = Parser(Config()).parse_docx_tree(doc_token, blocks)

# `walk` and `plain_text` are FUNCTIONS in larkdocio.model — a node carries no `.walk()` and
# no `.plain_text()` method. walk(tree) chooses WHICH blocks; plain_text(node) says what one
# block says, its own words only. `walk` yields the PAGE ROOT first — which holds the title
# and cannot take a sibling — so the anchor search starts after it.
quote = next(plain_text(node) for node in list(walk(tree))[1:] if plain_text(node).strip())

plan = dry_run(
    [InsertRequest(reference=Anchor(quote=quote),
                   position=InsertPosition.AFTER,
                   content=compose("A line the change detector will see."))],
    tree,
    document_revision_id=docx.revision_id,
)
log = apply(plan, writer, doc_token)

# THE READ-BACK LAW: a green apply is acceptance, not a receipt. Read BOTH sides of the log,
# then let the re-read be the verdict — which here is the same call the detector already makes.
print("applied:", len(log.applied), "refused:", len(log.refusals))
after = client.read_document_revision(doc_token)
print("before:", current, "after one edit:", after, "| moved?", after != current)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt". It
costs nothing extra in this recipe: the re-read that proves the write landed **is** the change
detector, which is the neatest illustration of the law there is.

**What `revision_id` does NOT tell you — four things a ledger will act on:**

- **It is not a content digest.** A moved number means *something* changed and says nothing
  about **what** or **where**. If you need to know that, compare the content: read both states
  and diff them (§ "Recipe: diff a named edition against head (pin a semantic version, not a
  keystroke counter)" is the shape). An unmoved number does mean no write landed between the two
  reads.
- **It is comparable to itself across time and to nothing else.** It is per document. Comparing
  one document's number with another's — or with a spreadsheet's `revision`, or a Base table's —
  means nothing.
- **It says nothing at all about Drive raw files.** A `file` child of a folder has no revision on
  any route this library calls; its only free anchor is `modified_time` from the listing, at
  second granularity, and its only exact one is the `sha256` of bytes you fetch yourself with
  `DriveFilesWriteClient.download(file_token)`. See § "Recipe: read every document in a folder",
  under *What a folder ledger can and cannot key on*, for the whole field list.
- **It is not a lock, and it reserves nothing.** Recording it does not stop anyone editing. What
  it *does* do is arm the writer's whole-document compare-and-swap: hand the same number to
  `dry_run(..., document_revision_id=…)` and a batch planned against a document that has since
  moved refuses entirely rather than writing into a position that shifted. **It is never
  silently on.** Omit the number, or hand one that could not be read, and the guard is
  `unavailable` rather than active — the plan says which on `plan.revision_guard`, with the why
  and how to arm it in `revision_guard_detail`, and the per-entry `STALE_ANCHOR` re-validation
  still runs. That is exactly why `None` above must not be laundered into "unchanged": an
  unreadable anchor buys you no compare-and-swap either.

**Measured.** On a harness-created disposable on 2026-08-15: revision `1` before, `2` after a
single block insert, and `2` again on an immediately following read — so an edit moves it by one
and a read is inert (`tests/test_live_drive_bytes_leg_gate.py`, in the source repository). **Retention is
unmeasured** — how far back `document_revision_id` reaches on an old document was never probed,
and is stated as unknown rather than assumed unbounded.

### Recipe: your version name resolves to nothing later — pin a NAMED version and record the revision it named

**The failure this cures.** A ledger records *"we ingested V1.3"*, and six weeks later nobody
can say which bytes that was. A Lark **named version** is a label a person chose, and it is the
right thing to record — but the version object carries **no `revision_id`**, no url and no size,
and the version token **cannot be resolved back to a revision or to content by any route**. On
its own, a name records a moment it cannot reproduce. The cure is to capture the revision **at
the moment you name it**, which is exactly what `create_version` returns.

```python
from larkdocio.common import init_env
from larkdocio.drive import DriveClient, DriveVersionsWriteClient

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded

doc_token = "YOURDOCXTOKEN"

# NAME THIS MOMENT — and get back what it named. create_version reads the document's head
# revision immediately BEFORE it creates the version, and hands you both in one result. That
# triple is what a ledger stores; the name alone is not enough.
writer = DriveVersionsWriteClient.from_write_credentials()
created = writer.create_version(doc_token, "V1.3")
name, version_token, revision = created.triple
print("pinned:", name, version_token, revision)

# Creating a version is REVISION-INERT (measured: the head revision is identical either side
# of the create), so the triple is exact unless someone edited the document concurrently.

# Lark ALLOWS DUPLICATE NAMES and quietly renames the second one — a second "V1.3" comes back
# as "V1.3(1)" with its own token. The echo is what exists, so record the echo, not the ask.
if created.name_was_changed_by_lark:
    print("Lark renamed it:", created.requested_name, "->", created.version.name)

# Where the revision could not be read, the field is honestly ABSENT — never zero, never
# invented — and says why. The version itself was still created.
if created.revision is None:
    print("no revision paired:", created.revision_note)

# READ THEM BACK — newest first, paging already done for you, and the times converted once.
reader = DriveClient.from_read_credentials()
listing = reader.list_versions(doc_token)
for version in listing:
    print(version.name, version.token, version.created_at)

# A document that has never been versioned answers an EMPTY LIST, not an error — so an empty
# result is a fact about the document, never a denial in disguise.
names = [version.name for version in listing]
```

**What is not offered, and why.** There is **no delete-version call** in this library. The route
works — it was measured — and it is deliberately unshipped: deleting a named version is a
destruction with no restore verb anywhere in the family, and the whole point of a named version
is that a person chose it. **No quota is claimed either**: seven versions were created on one
document, four of them back-to-back, with no warning and no refusal — so the honest words are
*no quota disclosed*, not *there is no quota*. A **300-character** name was accepted whole, so
no length ceiling is claimed. `obj_type` defaults to `"docx"` and `"sheet"` is the other
measured-accepted value; `"bitable"` and `"sheets"` are refused **locally**, in Lark's own
words, before a call is spent. Anything else is passed through for Lark to answer, because it
was never tried and *unmeasured* is not the same as *refused*.

### Recipe: diff a named edition against head (pin a semantic version, not a keystroke counter)

**The failure this cures.** Change detection that re-downloads head and diffs it against the
copy on disk tells you *something moved* and nothing about *since when*. What an ingestion
ledger wants is the other shape: **read the document as it was at the version we ingested, and
diff that against head.** That is available — with one boundary, stated up front so you do not
spend a day looking for the other half.

**A document can be read at a numeric revision. An edition token cannot be resolved to
anything.** So the pairing has to be recorded at the moment the version is made — which
`create_version` does for you, because creating a version is revision-inert.

> **BEFORE YOU RUN IT: `create_version` is PERMANENT RESIDUE, and this library ships no way
> to remove it.** There is deliberately **no delete-version call** in this library, so a
> `create_version` run against a document you do not own leaves a named version on it that
> neither you nor larkdocio can take back — and Lark also **allows duplicate names**, so a
> re-run leaves a second one called `V1.3(1)`. The reasoning is under *What is not offered,
> and why* in § "Recipe: your version name resolves to nothing later — pin a NAMED version and record the revision it named".
> Point the token below at a disposable document of your own until the script is doing what
> you meant. This paragraph sits **above** the example on purpose: it cost one reader
> permanent residue on somebody else's document by sitting below it.

```python
import difflib

from larkdocio.common import get_read_credentials, init_env
from larkdocio.drive import DriveVersionsWriteClient
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded

doc_token = "YOURDOCXTOKEN"

# 1. NAME THIS MOMENT — and record the triple, not the name. The revision is what makes the
#    name resolvable later; on its own a name records a moment it cannot reproduce.
writer = DriveVersionsWriteClient.from_write_credentials()
created = writer.create_version(doc_token, "V1.3")
name, version_token, pinned_revision = created.triple
ledger_row = {"name": name, "token": version_token, "revision": pinned_revision}

# …the document goes on being edited by whoever edits it…

# 2. BOUND THE PIN — the check that has to be IN the script, not beside it. An out-of-range
#    revision is answered code 0 with HEAD's body, silently (first trap below), so a pinned
#    read of a bad number diffs head against head and reports "no change" forever. The only
#    defence is to read the head revision first and refuse a pin above it: ONE metadata call,
#    no block tree. larkdocio cannot make this check for you without spending that call
#    behind your back, so it is yours.
app_id, app_secret = get_read_credentials()
reader = Client(app_id, app_secret, "larksuite.com")
head_revision = reader.read_document_revision(doc_token)
if ledger_row["revision"] is None:
    raise SystemExit("this ledger row has no revision — the version exists, but nothing "
                     "pairs it to content; re-create the pairing on a document you can read")
if head_revision is not None and ledger_row["revision"] > head_revision:
    raise SystemExit(f"revision {ledger_row['revision']} is past head ({head_revision}): "
                     "Lark would answer HEAD for it and this diff would be head vs head")

# 3. READ IT BOTH WAYS. `document_revision_id=<n>` reads the document AS OF revision n;
#    omitting it reads head, exactly as it always did.
pinned_meta, then_blocks = reader.get_docx_content(
    doc_token, document_revision_id=ledger_row["revision"])
head_meta, now_blocks = reader.get_docx_content(doc_token)

# 4. DIFF THEM — a real diff, not a boolean. Both operands are already Markdown strings, so
#    the standard library finishes the job: `difflib` needs no dependency and no service.
then_markdown = Parser(Config()).parse_docx_content(pinned_meta.document_id, then_blocks)
now_markdown = Parser(Config()).parse_docx_content(head_meta.document_id, now_blocks)
diff = list(difflib.unified_diff(
    then_markdown.splitlines(), now_markdown.splitlines(),
    fromfile=f"{ledger_row['name']} (revision {ledger_row['revision']})",
    tofile=f"head (revision {head_meta.revision_id})", lineterm=""))
changed = bool(diff)
print("\n".join(diff) if changed else f"no change since {ledger_row['name']}")

# The pinned result carries the revision YOU asked for and NO revision_id — the metadata route
# ignores the pin and answers head, so there is no honest number to put there. Head's revision
# is on the head read, where it is true, and it is the one to arm a write plan with.
print("pinned at:", pinned_meta.document_revision_id, "head is:", head_meta.revision_id)

# A pin Lark itself refuses is refused HERE — on THIS parameter, on this read, before a call
# is spent: 0 (HistoricalReadRefusedError, code 1770001), any negative number including -1
# (99992402; -1 is Lark's own head sentinel and head here is None), and anything that is not
# a real int — a digit string, a float and a bool included. Re-measured against the shipped
# gate: larkdocio.read.history.check_revision_pin(0) raises before the client is reached.
# THE SAME SPELLING ON THE WRITE PLAN IS A DIFFERENT PARAMETER AND DOES NOT REFUSE — see the
# note below the traps.
```

**The three measured traps around this parameter.** They are one text, met in one place, and
`larkdocio.capabilities(full=True)["safety_contracts"]` carries the same statement:

> AN OUT-OF-RANGE REVISION SILENTLY RETURNS HEAD. Measured: a revision 50 past head on a 4-revision document answered code 0 and head's body, with no error and no marker (tests/captures/editions-spike/captures/205-, in the source repository). So this operation CANNOT DETECT over-range, and it does not pretend to: a caller who pins a bad number is silently reading head. If that matters, bound the number yourself — read the head revision first (read_document_revision) and refuse a pin above it, which is a check larkdocio cannot make for you without spending a call you did not ask for.

> raw_content IGNORES THE PIN, so a historical read is never routed through it. Measured: raw_content with a numeric document_revision_id returned code 0 and HEAD's content, byte-identical to the plain head call (tests/captures/editions-spike/captures/16- vs 17-, in the source repository), and the same route with an edition token did the same (116-, in the dev repo). larkdocio exposes no raw-content read at all, so the pin cannot reach one here; if you call that endpoint yourself, know that the parameter is accepted and discarded.

> THE DOCUMENT META ROUTE IGNORES THE PIN. Measured: GET …/docx/v1/documents/{id} asked for revision 2 answered revision_id 3 — head (tests/captures/editions-spike/captures/19-, in the source repository). So a pinned read does not call it, and hands back no revision_id at all rather than head's number wearing the pinned revision's name; the revision you pinned is carried on the result as document_revision_id, and the title as of that revision is the page block's own text in the blocks the read returned.

**`document_revision_id` is TWO parameters with one name, and only one of them refuses a bad
pin.** This is the trap behind a report that *"the local refusal claim is false"* — it is true
of the read and false of the write plan, and the two are spelled identically:

| Where you pass it | `document_revision_id=0` does what | Measured |
|---|---|---|
| `Client.get_docx_content(token, document_revision_id=0)` — **the historical read** | **Refused locally, no call spent.** `HistoricalReadRefusedError`, Lark's own code `1770001` (`invalid param`); `-1` and any negative give `99992402`; a digit string, a float and a `bool` give `99992402` too | re-measured 2026-08-15 against the shipped gate (`larkdocio.read.history.check_revision_pin`), which raises before the client is reached — so no call is spent and nothing is sent |
| `dry_run(requests, root, document_revision_id=0)` — **the write plan's staleness anchor** | **Not refused at all.** The plan is built and `plan.revision_guard` reads `"unavailable"` — the whole-document compare-and-swap is **off**, and the batch will apply | re-measured 2026-08-15 against `larkdocio.write.revision_guard_status`, which classifies `0`, any negative number and `None` as unavailable |

Both behaviours are deliberate and neither is a bug: the read pin is a **value Lark will be
asked about**, so a value Lark refuses is refused here first; the plan anchor is an
**availability question**, and a number that cannot order two states is not an anchor, so the
plan says so out loud instead of arming a guard that cannot bite. What was missing was the
**scope** of the sentence above — it is a claim about the read, and a reader who tried it on a
plan found the opposite and concluded the guide was wrong. **Read `plan.revision_guard` after
every `dry_run`**: `"active"` is the only value that means the guard is armed, and the recipes
in this guide assert it for that reason.

**Why the pin rides the route it rides.** The historical read goes through the flat blocks list
(`GET …/docx/v1/documents/{id}/blocks`), which is the one route **measured** to honour
`document_revision_id`: on a document with two states it returned the earlier body at an
earlier revision while head returned head's in the same instant, and a four-revision document
walked rung by rung reproduced its edit history exactly. Two neighbouring routes accept the
same parameter and discard it, which is why *being modelled* is not taken here for *being
honoured*.

**And the boundary, said plainly: an edition a HUMAN created in the web UI stays unresolvable.**
There is no route from an edition token to content, and none from an edition to a revision — so
"read the version someone named V1.3 in the browser" is not something this library can do, or
fake. It works for the editions **your ledger created**, because those are the ones whose
revision you were able to record. The search is written out rather than left for you to repeat:

> READING A DOCUMENT AT A NAMED EDITION IS NOT SERVED: no route maps an edition token to content, and none maps an edition to a revision. Measured 2026-08-11 against harness-created disposable documents on tenant_access_token (dev/editions-spike/findings.md § Leg 4, in the dev repo). TRIED — (1) GET one version: the version object carries no content, no url, no revision and no pointer of any kind (captures 12-, 122-); (2) blocks?document_revision_id=<version token> → 99992402, the parameter is an int; (3) blocks?edition_id= / ?version= / ?version_id= / ?obj_edition_id= → code 0 but HEAD, silently ignored (112--115-); (4) raw_content with a numeric pin and with edition_id → head (16-; 116- in the dev repo); (5) the meta route with a numeric pin → head (19-); (6) the version token used as a docx document_id → 99992402 on meta and 1770001 on blocks (20-, 21-); (7) the drive metas batch-query verb on the version token → failed_list [{code: 970005}], so it is not a file token (22-); (8) export_tasks with the version token as the file token → 1069914 export file token invalid (25-); (9) export_tasks with a speculative version field and with a speculative edition_id field → accepted and IGNORED, the result's file_size 4237 identical to the plain export (123--128-) — and byte-identity was not hashed, so it is unmeasured at the byte level; (10) the speculative sub-route …/versions/{version}/content → 404 (26-); (11) docx/v1/documents/{id}/revisions, /history and /versions, and drive/v1/files/{id}/revisions → 404 on all four (117--120-); (12) drive/v1/files/{id}/statistics → pv/uv/like counters only, no version or revision anything (121-). NOT TRIED, stated because a claim's scope may not exceed its evidence's — a user_access_token session on any of the above (everything measured was a tenant_access_token; the web client is a user session); POST/PUT/PATCH spellings of the unknown paths, deliberately, because a probe never risks a mutation on an unknown verb; the wiki/v2 node family at an edition; the legacy doc/v2 family; drive/v2 explorer routes; downloading the export artefacts and hashing them; retention — how far back document_revision_id reaches on an old document, and whether a deleted version's content survives; and whether an edition created while an edit is in flight snapshots before or after it. WHAT WORKS INSTEAD: record the pair yourself at creation time. create_version reads the head revision immediately before it creates the version and hands back (name, token, revision) — exact absent a concurrent edit, because creating a version is revision-inert (101-, 103-) — after which "diff edition vs head" is a pinned read against a head read. For an edition a HUMAN created in the web UI, resolution is a measured refusal: nothing above resolves it, and this library will not guess.

**Want the link, too?** A ledger row that records the name and the token often wants the URL a
human can click. `larkdocio.common.docx_edition_url(doc_url, version_token)` mints
`…/docx/<doc>?edition_id=<token>` offline — see § "Deep links" for it and, more importantly,
for the disclosure it ships with: the query grammar is **click-verified** on the Lark WEB
client, on one tenant, on 2026-08-11 — and on no other client or tenant, which stay
unmeasured. The link is a way for a human to *open* the edition; it is still not a way for
the API to *resolve* one, so the `(name, token, revision)` triple above remains what a pinned
read actually runs on.

**Retention is unmeasured.** How far back `document_revision_id` reaches on an old document was
never probed — a session-length probe cannot see it — so a pin far in the past is worth
checking against the body you get back rather than assumed to work. And remember the first trap:
a revision *past* head comes back as head, silently.

## Task — change what a document says

### Which write recipe do you need? — add, change, update or delete content in a document

**Start here before you write anything.** Every write recipe below answers exactly one of
these questions, and picking the wrong one is expensive in a way a green run never shows: the
path a first-time integrator reaches for — *clear the document, then compose it again* — costs
every block id in the document, and things are attached to those ids.

| What you are trying to do | The recipe that does it |
|---|---|
| **Empty document** — a brand-new document with no body blocks yet | § "Recipe: write into an empty document" |
| **Add to an existing document** — a new section, appended or anchored next to something | § "Recipe: author a Markdown fragment into a document". **More than 50 blocks in one go?** One request carries at most `MAX_CHILDREN_PER_CALL` of them and refuses a wider one at construction, so a long fragment is split, chained and read back in order: § "Recipe: author more than one call's worth of blocks — the 50-per-call cap, batched in order" |
| **Change an existing document — a single known block** you can already point at | § "Recipe: change a document at the object level — no Markdown anywhere" |
| **Change PART of a paragraph** — a few words inside a block, keeping the rest of it as it is | § "Recipe: edit part of a paragraph (a sub-span edit)". **Take this row, not the whole-block rows above, when the block carries styling you mean to keep:** a whole-block change rewrites the block as one **unstyled** run, so bold, italics, colour and links elsewhere in that paragraph are flattened — and the apply log calls that entry `applied`, because it *was* applied. The flattening is not a refusal and nothing in a green run says it happened. A whole-block change also rewrites the block's text as a whole, from the copy you read: text another writer added to that block after your read is replaced along with your own edit. The apply log calls that entry `applied`, because it was — nothing in a green run says a second writer's words were in the block. What the revision guard does and does not watch, and what a re-plan after a refusal costs whoever edited beside you, is § "Do not edit the document while an authoring session runs (the concurrency doctrine)" |
| **Change a checkbox** — tick or untick a `- [ ]` item that is already in the document | **The gated route does this.** Flip `- [ ]` to `- [x]` on that item's line in an edited block-identity projection and re-run the reconciliation: the plan-gated route sets `todo.style.done` on the block itself, inside the same plan gate, the same whole-document revision guard and the same refusal set as every other change — § "Recipe: update an existing document — change or edit many blocks at once, without re-authoring it". A flip that changes nothing else does **not** rewrite the item's text, so styling inside it survives. Two other routes still exist: create the item in the state you want — `NewBlock.todo(text, done=True)` writes the bit at creation — or flip it in the Lark editor. What this route will **not** do is carry any other property of the block, and it says so typed (`change-not-expressible`) rather than reporting success: the machine-readable form of that boundary is the docx-write surface's `absences` register, under `no-block-property-edit-beyond-text` |
| **Change an existing document — the whole document, or many blocks at once** | § "Recipe: update an existing document — change or edit many blocks at once, without re-authoring it" — and if the edit happens later, in another process, or after a handoff, persist the read with `snapshot` and bring it back with `load`; the flow is otherwise identical. **This row is a whole-block change too**, on every block the edited Markdown changed: each one is re-written as one run carrying the styling that block starts with, so a colour that differed elsewhere in that paragraph is flattened onto it — and bold, italics or a **labelled** link inside one refuses the whole batch (`not-in-dialect`) rather than being flattened. A link whose label *is* its own url — `[https://x](https://x)` — is the one link shape that does **not** refuse: it composes as plain unstyled text carrying the url, and the mark-up around it is gone. Blocks you did not edit keep their ids **and** their formatting, and a block outside the dialect is conserved untouched — **and that includes every table in the document**: *A table is opaque as a whole and its cells are not individually addressable through the projection; the supported route for changing one is the table-cell patch path in larkdocio.write, which addresses a cell directly instead of inferring it from prose.* So a row you add, a cell you retype or a whole table you leave out of the edited Markdown compiles to **no request at all** — the plan reports the table conserved and the run is green. What conservation does and does not promise is stated once, in the *"A block the Markdown cannot express is conserved, not destroyed"* paragraph of § "Recipe: update an existing document — change or edit many blocks at once, without re-authoring it", and machine-readably at `capabilities(full=True)["surfaces"]["docx-read"]["block_projection_support"]["contract"]` |
| **Reorganise the whole document** — the same content, in a different order | § "Recipe: reorganise a document — there is no move, so a reorder is delete-and-recreate". **There is no move or reorder operation** (see the note below the table), so this one is its own discipline: comments first, insert before delete, keep the blocks that did not move |
| **Delete content** — remove a block, a list item, a paragraph | § "Recipe: the docx write handshake" (a `DeleteRequest` through the same gate) |
| **Change a diagram** — there is no in-place update, so this one is its own recipe | § "Recipe: author a mermaid diagram (and change one)" |
| **Fix a table** — patch one cell of a table that already exists | § "Recipe: the docx write handshake" (a `TableLocator` cell edit) |
| **Add or remove a table row** — change the *shape* of a table that already exists, not its text | **Adding a row: the gated route does this.** A `GrowTableRequest` appends one row at the end, inside the same plan gate, the same whole-document revision guard and the same refusal set as every other change, and the table keeps its **block ids** — its own and every pre-existing cell's, in the order they were in — § "Recipe: add a row to a table that already exists". Removing a row or a column, adding a **column**, and inserting a row anywhere but the end are not operations here. Asking for a mid-table index is refused typed (`table-grow-unsupported`) naming the append spelling, and inserting at any other index is **unmeasured** from this library — neither refuted nor supported — rather than something Lark was seen to refuse. For those, author the table again at the shape you want and delete the old one, through § "Recipe: the docx write handshake" — that route loses the **block ids** of the table and of every cell in it, and anything anchored to them — or make the change in the Lark editor. Changing what a cell *says* is a different job and it is gated: the *fix a table* row above. The machine-readable form of this row is the docx-write surface's `absences` register, under `no-table-grid-change-beyond-appending-a-row` |
| **Put a picture or a file IN the body** — *"put this image in the document"*, *"attach the file to it"* | § "Recipe: put an image in a document (create, upload, bind)" for the picture; § "Recipe: attach a file to a document (the 📎 attachment card)" for the file. Out of band, outside the plan gate: the compiler holds no bytes. **Where it lands is `parent_block_id` + a 0-based `index`** — the two ops on this surface that do NOT take an `Anchor` |
| **Link to something from inside a sentence** — *"for the full details, open the attached file"* | § "Recipe: link a file from a sentence" (upload to a folder, then a `rich_paragraph` link anchor) |
| **Know whether you need to write at all** — *"has this moved since I last looked?"*, a ledger deciding what to re-ingest | § "Recipe: you re-ingested a document that never changed — the revision_id change detector". It is a **read** recipe whose last leg authors one paragraph, so it appears here too: the revision it teaches you to record is the same value that arms `STALE_DOCUMENT` on every row above |

If what you want is the whole update, preamble and all, in one block you can paste: § "Recipe:
copy this — the end-to-end update script, from url to applied edit".

**None of these rows is `patch_block`, and that is the point — the door it used to open is
closed.** The docx single-block PATCH is the engine's own primitive and calling it directly steps
OUTSIDE everything the gated route gives you: outside the plan gate (nothing previews it, and no
`Plan` records it), outside the `STALE_DOCUMENT` whole-document compare-and-swap (a document
edited under you is not detected), and outside the refusal set (no typed refusal is raised on
your behalf, and no apply-log entry is written). THE CALLER OWNS THE READ-BACK: read the block
back and check it says what you meant, because nothing else will. What it does that the gated
route cannot is IN-PLACE, IDENTITY-PRESERVING mutation — the block keeps its id, and so does
everything anchored to it. That is the whole of its advantage: delete-and-recreate reaches the
same content through the gate, at the price of new block ids. Which is why it is NOT PART OF THE
PUBLIC SURFACE: it is `_patch_block`, internal to this library, and every one of the engine's own
writes goes through it. `patch_block` — the public name it used to carry — still answers, and
refuses, naming the gated route to use instead.

**So there is no "escape hatch" row to reach for, and the two edits it was used for are
rows in the table above.** A `client.patch_block(...)` call raises
`larkdocio.errors.FencedPrimitiveError` — locally, with nothing sent — and the message names the
route: the **checkbox** row for ticking or unticking an item that already exists, and the **add a
row to a table** row for growing a table's grid by one row at the end. Both keep the block ids
you care about, and both go through the plan gate, the whole-document revision guard and the
refusal set like every other change. For anything else the gated recipes above cannot express,
author the replacement and delete the old block through the same gate — that reaches the same
content, at the price of new block ids, and it is the honest price rather than a hidden one.

**How `Anchor(quote=)` matches — read this once and every `not-found` afterwards makes
sense.** The quote is matched **byte-verbatim, as a substring, against the block's RAW STORED
text** — never against the Markdown you read. Those two differ in ways you cannot see: the
Markdown adds line markers (`- `, `# `, `> `, `1. `) and escaping backslashes that are in no
block, and — the one that catches everybody — **stored text can carry a *soft return*, a
literal newline inside a single paragraph, which the Markdown shows as an ordinary line wrap.**
A sentence you copy off a wrapped paragraph therefore differs from what is stored by one
invisible character, and the match refuses. So **quote a short fragment that sits on one side
of a wrap, never a whole sentence** — every example below does — or, steadier, anchor by the
block's own id with `AnchorById(block_id=...)`, which no whitespace can spell wrong. The
library will not normalize whitespace to force a match (exactly-one-or-refuse is the contract),
but the refusal now *names* the near-miss: `block '<id>' differs only in whitespace`, with the
stored spelling and a fragment of your own quote that does match.

**Why the whole-document row is not "clear it and write it again".** Re-creating a block hands it a
new id, so a rewrite that reads to a person like an update is a new document wearing the old
one's name — every deep link into it now points at an id the document no longer has, and so
does every comment anchored there.

> Block ids are what comments anchor to, so re-creating a block orphans every review comment left on it — the conversation is not moved, it is stranded, and nothing in the document says so afterwards. This library ships the join that shows you which comments are at stake before you decide: `review.for_node(block)` answers with what reviewers said about that exact block.

**THERE IS NO MOVE — a reorder is delete-and-recreate, and that is a property of the surface,
not of a recipe.** larkdocio's docx write surface ships five body-writing request families and
no more — `EditRequest`, `InsertRequest`, `DeleteRequest`, `SubSpanEditRequest` and
`GrowTableRequest` (the two comment ops write the review conversation, not the body, which is
how they are excluded); the machine-readable form is
`capabilities(full=True)["surfaces"]["docx-write"]["absences"]`, which carries this same statement.
**None of them moves a block**, and the reconciler says the same
thing from the other side: a reorder in an edited projection is **refused rather than
approximated** (`marker-order-changed`), because expressing it would mean deleting a block and
inserting a copy — which destroys the id everything else is anchored to. So a whole-document
reorganisation is **delete-and-recreate by contract**, and the cost is paid in block ids:
§ "Recipe: reorganise a document — there is no move, so a reorder is delete-and-recreate" is
how to pay as little of it as possible.

**Two facts of different strength, labelled separately — do not read one as the other.**
*(a)* **larkdocio ships no move request family. Verification label: derived from the shipped
surface** — the five families above are a closed set in this library's own code, so that half
is checkable without a call, and the label is literal: the enumeration is **read off the
op-descriptor registry** (`larkdocio.write.ops.OPS`, each descriptor declaring whether it
writes the document body or the review conversation), so a sixth family joins that answer by
being registered. *(b)* **Lark's own docx `v1` API exposes no move or reorder route
either. Verification label: measured** — probed on 2026-08-16 over **eleven enumerated
candidate spellings**. Two move operation keys (`move_block`, `move_to`) on the documented
block `PATCH` route and on its `batch_update` twin answered `1770001 "invalid param"` — the
same code an operation key the route has never heard of answers, which a control established,
so the refusal means *"unrecognised operation"* rather than *"malformed move"*. Adopting an
existing block id through `…/blocks/{parent}/children` was refused `99992402` with
`children[*].block_type is required` — a child is a **new block descriptor**, never an
adoption. Five invented spellings — `…/blocks/{block}/move`, `…/blocks/move`,
`…/children/move`, `…/children/batch_move` and `PATCH …/children` — all answered the
gateway's own non-JSON HTTP 404 `404 page not found`. And two bodies went to the documented
`…/descendant` route, the second of which is the trap below. The pinned SDK agrees from the
offline side — its `UpdateBlockRequest` declares sixteen operation fields and not one of them
moves or re-parents a block — but that is **spec-derived, not measured**, and the claim does
not rest on it. The probe's verdict and captures were retired from the dev repo on
2026-09-18, so the evidence is no longer inspectable there — which is why its scope is stated
in full below rather than cited.

**The scope of that measurement, because a negative claim may not exceed its evidence.** One
tenant, one day (2026-08-16), a `tenant_access_token` on the write credential pair, the
`larksuite.com` OpenAPI domain, docx **`v1`**, on three plain `docx` documents the probe
created and destroyed. **Explicitly unmeasured — neither refuted nor supported:** a
`user_access_token`; any other tenant; **wiki-wrapped** documents; any docx API version other
than `v1`; the Lark web client's internal reorder API; and any move spelling outside the
eleven.

> **A `code 0` FROM THE DESCENDANT ROUTE DOES NOT MEAN "MOVED" — IT MEANS YOU JUST MADE A
> COPY.** `POST /open-apis/docx/v1/documents/{doc}/blocks/{parent}/descendant`, given a
> well-formed body that names an **existing** block id, answers HTTP 200 `code 0 "success"`
> and **creates a NEW block**: it reads the live id as a *client-side temporary* id and hands
> it back as `temporary_block_id`, beside the new block's real id, in
> `data.block_id_relations`. Read back, the original was still in its original place and the
> root child order was **unchanged** — so what you are holding is a duplicate with a new id,
> and the success code says nothing about that. **A caller who reads `code 0` as "moved" ships
> a duplicate.** Measured 2026-08-16 on the same eleven-spelling probe, at the scope stated
> above; the read-back recorded `order_unchanged: true` (the request and read-back captures
> were retired from the dev repo on 2026-09-18).
> Whether that route would deep-copy a whole **subtree** is unmeasured,
> not refuted: the block it copied was a leaf. This is the sharpest reason the read-back law
> below is not optional on a reorganisation — the only thing that tells a move from a
> duplication here is reading the order back.

### Recipe: write into an empty document

A brand-new document has **no body blocks**, so there is **no quote to anchor to** — every
anchor would refuse `not-found`. The way in is the **page node**: anchor on the document
**title** and `APPEND_INTO` it, which appends the paragraph as the page's first child.
(`block_plain_text(root)` gives you the title text; anchoring `BEFORE` / `AFTER` the page
node instead refuses `CANNOT_HOLD_SIBLINGS` — the document root has no siblings.) The
URL → token preamble is the same as above; add the `doc_type == "wiki"` branch if your URL
is a wiki node.

**This recipe is for an EMPTY document. To change a document that already has content, see
§ "Recipe: update an existing document — change or edit many blocks at once, without
re-authoring it" — do not re-author it.** Emptying a document first and writing it again is
not an update: it is a new document wearing the old one's name.

**Do not edit the document concurrently while this runs** — an empty document is the easiest
one for another user to start typing into, and the engine **refuses rather than guessing** when
the document changed under the plan. A busy document just needs a **re-download** and a
**re-plan** (cheap). See § "Do not edit the document while an authoring session runs".

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    WriteClient,
    apply,
    block_plain_text,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOUREMPTYDOCTOKEN"
domain, doc_type, doc_token = validate_download_url(url)
read_id, read_secret = get_read_credentials()
docx, blocks = Client(read_id, read_secret, domain).get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

# No body text exists, so anchor on the PAGE node (the document title) and APPEND_INTO it.
requests = [
    InsertRequest(
        reference=Anchor(quote=block_plain_text(root), breadcrumb=()),
        position=InsertPosition.APPEND_INTO,
        content=(NewParagraph(text="First paragraph in a fresh document."),),
    ),
]
plan = dry_run(requests, root)
write_id, write_secret = get_write_credentials()
log = apply(plan, WriteClient(write_id, write_secret, domain), document_id=doc_token)
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: the docx write handshake

**Read this before you plan an integration — the creatable-content floor.** The content the
engine can CREATE is a **`NewBlock`** of kind `heading` (level 1–9), `paragraph`,
`bullet` / `ordered` / `todo` (list items, **nestable**), `code` (with a language), `quote`
or `table` — plus the legacy **`NewParagraph`**, still valid and equivalent to
`kind=paragraph`. Created text is **unstyled** — with **one** exception, a **link anchor**: a
created run may carry `TextSpan(link_url=…)` inside `NewBlock.rich_paragraph`, or inside a
`NewBlock.table` cell authored as a span sequence rather than a string, and nothing else. A callout, boards, embeds, grids and colors are **not creatable** in this rung —
`NewBlockKind` is a *closed* enum and `NewBlock` carries no block-type escape, image token or
embed url, so a richer shape is not merely refused, it is inexpressible **on this path**.
**"Not on this path" is not "not at all":** an image (docx block type 27) and a file
attachment (type 23) are authored **out of band**, by
`larkdocio.write.media.put_image_in_document` and
`larkdocio.write.media.put_file_in_document` — see § "Recipe: put an image in a document
(create, upload, bind)" and § "Recipe: attach a file to a document (the 📎 attachment card)".
Both place the block with a `parent_block_id` + a 0-based `index` rather than an `Anchor`. **Editable is not creatable:** a **merged** table
*reads* (the reader emits HTML for it) and its unmerged **cells** are *editable* (their text
patches like a paragraph, via a `TableLocator` anchor), but **no merge can be created** — so
do not read the editable surface, or the write-hostile list below, as a list of what you can
create.
Build content with the per-kind constructors — `NewBlock.heading(2, "Findings")`,
`NewBlock.paragraph(text)`, `NewBlock.bullet(text, children=(...))`,
`NewBlock.ordered(text)`, `NewBlock.todo(text, done=False)`,
`NewBlock.code(text, language="python")`, `NewBlock.quote(text)`,
`NewBlock.table([["Metric", "Value"], ["On-time delivery", "97.2%"]], header_row=True)` —
and pass a tuple of them as an `InsertRequest`'s `content`. Nesting is expressed by a list
item's `children` — capped at `larkdocio.write.MAX_NEST_DEPTH` levels and
`MAX_CHILDREN_PER_CALL` siblings per group; deeper or wider is **refused at construction**,
never silently flattened. An unknown code `language` or an out-of-range heading level is
refused the same way. Machine-readable form:
`capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]`.

**A code block's `language` — and when to pass `language=None`.** `NewBlock.code(text,
language=…)` takes a **Markdown fence token** (one of the 65 in
`larkdocio.langs.supported_code_languages()`), and an unknown token is refused at
construction, never downgraded. **`language=None` is a first-class choice, not an omission:**
it authors a **bare fence**, which is the *correct* choice whenever the content is **not
code** — ASCII art, a directory tree, a log excerpt, plain preformatted text. Lark has no
`plaintext` enum, so a near-miss token would be a wrong claim about the content, while a bare
fence is exactly what the reader emits back for it. Either way the body is **verbatim in both
directions**, so an indented diagram round-trips byte for byte. The § "Recipe: edit a
code block's text" recipe below does both.

**Authoring a table — the grid, and its two documented lossinesses.** `NewBlock.table(rows)`
takes an R×C grid of **plain-text** cells, row-major; `header_row` (**default `True`**)
promotes row 0 to the table's header row. The grid is created through the same
`dry_run` → `apply` gate as any other content: Lark provisions the R×C cells from the
table's property, then each authored cell is filled with the same whole-cell patch a cell
edit performs — so a created table is immediately addressable by a `TableLocator`, which is
how you add rich (styled) cell content afterwards. Bounded by
`larkdocio.write.MAX_TABLE_CELLS` cells; a bigger grid is refused with the cap named, never
truncated. **MERGED CELLS ARE NOT EXPRESSIBLE** (documented lossiness): Markdown has no
`colspan`/`rowspan`, so an authored table is always a plain grid — there is no span field to
ask for one, and a **ragged** grid (rows of differing width — the shape a merged table
produces) is refused with the typed `merge-not-expressible` refusal, carried by a
`RefusedError` whose `.refusal.detail` names the offending row. The grid is **never padded
or truncated** into shape. Reading a merged table is unaffected — that is the reader's job,
and it emits an HTML `<table>` for one. A cell containing a `|` is fine (the reader escapes
it); a cell containing a newline reads back with the lines joined by `<br>`.

**AND `header_row=False` cannot be *observed* on read-back** (the second lossiness, live-
verified): the flag **is** sent and **is** stored, but Lark **omits a false `header_row`**
from the block payload it returns, and the reader's documented rule renders an *absent* flag
as "row 0 promoted". So a headerless authored table still reads back through Markdown with
its first row as the header. That is a limit of the **Markdown projection**, not a lost
write — and it is why `header_row` defaults to `True` (what Lark's editor and the reader both
already do) instead of defaulting to a distinction the round-trip cannot show. If your first
row is data, either accept the projection or give the table a real header row.

**WHERE THE DOCUMENT LANDS — the argument to pass when you are creating one.**
`WriteClient.create_document(title="Q3 review", folder_token=folder_token)` takes **two**
arguments and **`folder_token` is the required one** — it is keyword-only, and the destination
it names is **yours to supply, not this library's to guess**. (`title` defaults to the empty
string and is never validated: `create_document(folder_token=f)` creates an *untitled*
document rather than refusing. Only the destination is fenced.) See
§ "Where a new object goes" for the rule and why it has no exceptions. **One refusal, however
you get there wrong.** Omit the keyword, or pass `None`, the empty string, or whitespace, and
you get the same `MissingDestinationError` — raised before any call, with the teaching text
§ "Where a new object goes" quotes verbatim. The keyword *defaults* to `None` for exactly that
reason: so an omitted destination reaches that refusal rather than an interpreter-level
argument error, which would tell you a keyword is missing and nothing about which one to pass
or where to get it. A default is not permission to skip it. The folder token itself is the one in a folder's
URL (`…/drive/folder/<token>`), or the one `create_folder` hands back (§ "Recipe: create a
folder to organise into"). **The
destination also decides who can already read it**: a document filed into a folder inherits
that folder's access, rows and all — see § "Recipe: grant a HUMAN access".

**What the call answers: a `CreatedDocument`.** It **is** the reply's own `data.document`
payload — a `dict` subclass — so the idiom that has always worked still works, unchanged.
Given `created = writer.create_document(title="Q3 review", folder_token=folder_token)`:
`created["document_id"]` is the subscript you have always used and gives the same answer;
`created.document_id` is that same value as an attribute; `created.title` is what Lark stored;
`created.revision_id` is the document's revision at creation; and `created.folder_token` is
where you put it, echoed back so a ledger row is complete without a second call.

`document_id` is the new document's id **and the root Page block's id**, so the create's own
answer is the anchor everything below hangs off. Every dict operation keeps its old answer —
`.get`, `in`, iteration, `json.dumps`, `{**created}`, and `==` against a plain dict — because
the value **is** that dict. The one thing that is no longer true is `type(created) is dict`;
use `isinstance(created, dict)`, which answers `True`. The create → use → `finally`-delete shape
for a throwaway document is § "The disposables doctrine" above, which names the pair.

**What the create's own answer does NOT carry, for docx specifically: a `url` — and now it can
SAY so.** The docx v1 reply hands back `document_id`, `revision_id` and `title`, and nothing
that names a web address; this library never assembles one from a host and a token — a
constructed link is a guess wearing the shape of an answer (the same honest reason
`DriveFilesWriteClient.permalink` states for a file, `drive/files_write.py`). So
`CreatedDocument` has **no `url` attribute at all**: `hasattr(created, "url")` is `False`, and
asking for it raises an `AttributeError` that carries the reason and the paved road instead of
the interpreter's bare message. The same sentence is readable without provoking an exception, on
the value itself, as `created.no_url_reason`. **Why absent rather than `None`:** `None` is
already what `CreatedFolder.url` means when Lark *carried* the key and left it empty — one
spelling for two different facts would leave you unable to tell "Lark did not answer" from "we
did not ask". **The paved road:** list the parent folder afterward (§ "Recipe: read
every document in a folder" above) and read the new document back off it — the listing's
per-child `url` field (`FolderChild.url`, `Optional[str]`) is Lark's own answer, taught
`Optional` on purpose: a child Lark did not hand a url for reads back `None`, which is a real
answer, not a bug to work around. (**This is scoped to docx.** `create_spreadsheet`'s own reply
DOES carry a `url` and its `CreatedSpreadsheet.url` is that value, carried and never
constructed; `create_app`'s reply is the SDK's `App` — `CreatedBase` is a subclass of it — whose
`url` field is real. Only the docx v1 reply lacks one.)

**One title, one H1 — do not add a second.** `create_document(title=…)` already renders as the
document's `# {title}` heading (the page root's own Markdown projection —
`larkdocio.read.parser`, corroborated by the docx block-type registry's `page` row,
`larkdocio.blocks.read_support`): the title is not blank content waiting for a heading, it *is*
one. So a first content block of `NewBlock.heading(1, …)` makes a **second** H1, not the
document's only one — if the first section needs a heading, either author it at level 2 or
lower, or leave the title to stand alone as the H1.

**The authoring cap, before you size your first batch.** One `InsertRequest` carries at most
`larkdocio.write.MAX_CHILDREN_PER_CALL` (**50**) blocks, because docx v1's `create_children`
call takes 1–50 blocks and one sibling group is one call. A wider group is **refused at
construction** — a plain `ValueError` out of the request's constructor, before `dry_run` ever
sees it, which is a different shape from every typed refusal on this surface. The way over it is
§ "Recipe: author more than one call's worth of blocks", which splits and anchors the batches
in order.

Four steps, and the chain **starts from a URL**: read the document, **parse it into the
node tree** the anchors resolve against (`parse_docx_tree` — *not* `parse_docx_content`,
which returns Markdown), `dry_run` (preview a batch → a non-forgeable `Plan`, zero writes),
`apply` (execute — accepts only a `Plan`). The anchor below is a verbatim **quote** + a
**breadcrumb** (the enclosing heading path); **`AnchorById(block_id=...)`** is the other
option and is interchangeable with it in `InsertRequest` / `EditRequest` / `DeleteRequest` /
`SubSpanEditRequest` — see the anchor-kinds table above and the "anchor a follow-up by a
created block id" recipe below.

**Do not edit the document concurrently while this runs** — the plan is built against the
tree you just read, so the engine **refuses rather than guessing** when the document changed
under the plan, and a busy document just needs a **re-download** and a **re-plan** (cheap).
See § "Do not edit the document while an authoring session runs".

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import Anchor, EditRequest, WriteClient, apply, dry_run

init_env(".env")            # FIRST: both credential pairs come from the .env
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)   # domain = the API domain

# 1. READ the document with the READ app.
read_id, read_secret = get_read_credentials()
reader = Client(read_id, read_secret, domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token
docx, blocks = reader.get_docx_content(doc_token)

# 2. PARSE it into the node TREE the writer anchors against. parse_docx_tree returns the
#    tree; parse_docx_content would return Markdown, which the writer cannot anchor on.
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

# 3. DRY-RUN → a non-forgeable Plan. ZERO writes; no client and no write creds involved.
#    document_revision_id ARMS the whole-document guard (STALE_DOCUMENT): the revision the
#    reader just handed back, so apply refuses the WHOLE batch (zero writes) if anyone edits
#    the document between this plan and that apply. Omit it and plan.revision_guard says
#    "unavailable" — the guard is never silently off.
requests = [
    EditRequest(
        anchor=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
        replacement="Revenue grew 15.0% in Q3.",
    ),
]
plan = dry_run(requests, root, document_revision_id=docx.revision_id)
assert plan.revision_guard == "active"
# inspect plan.entries — each is (block_id + before/after) OR a typed Refusal

# 4. APPLY with the WRITE app (a separate, narrowly-scoped app — never the read pair).
write_id, write_secret = get_write_credentials()
writer = WriteClient(write_id, write_secret, domain)
log = apply(plan, writer, document_id=doc_token)      # only a Plan reaches apply

# READ THE LOG. A refused entry RAISES (LarkApplyRefusedError, carrying err.log /
# err.applied / err.refusals), so a batch that wrote nothing cannot pass for a clean run;
# pass allow_partial=True when you would rather read the refusals off the return value.
for entry in log:                                    # the log iterates, and answers len()
    print(entry.outcome, entry.block_id or entry.created_block_ids)
```

**Refusals mean "I would not guess."** A refusal (ambiguous quote, not-found,
`CANNOT_HOLD_SIBLINGS` / `CANNOT_HOLD_CHILDREN`, write-hostile block, or a `STALE_ANCHOR`
on live drift) is a typed skip in the apply-log, never a wrong write; **every docx refusal
carries a mandatory `detail`** saying what was wrong and what to try instead. One reason is
**not** a per-entry skip: `stale-document` (`STALE_DOCUMENT`) means the whole document changed
under the plan, so **every** entry of the batch carries it and **zero writes were issued** —
re-download and re-plan (see § "Do not edit the document while an authoring session runs").
A `not-found` on text **your own batch is about to create** is a different case with a different
fix: **one tree, one batch**, so **every queued request must target content that exists at commit
time; commit the insert, then anchor follow-ups by `created_block_ids`** — the refusal's `detail`
says so when it recognizes the shape (see § "Recipe: accumulate edits across turns").
A **`comment-anchors-present`** refusal means your edit targets a **whole block** — or a
**whole table cell** — that a reviewer has commented **inside**: that edit rebuilds the text as
a single run, so their per-passage anchors would have nowhere to attach, and moving a comment
onto text nobody commented on would misreport what a reviewer objected to. The recovery the
`detail` names is a **sub-span edit** on just the words you mean to change — that path splits
the runs and re-emits each one's anchors (see § "Recipe: edit part of a paragraph"). Resolving
or removing the comments first also clears it. There is no flag to override it, and a
**block-level** comment (one on the block as a whole, not on words inside it) does **not**
trigger it. **On a `TableLocator` cell edit the refusal reads a little differently**, because a
cell is not addressed by a block id and cannot be given a span: the `detail` names the **row and
column** and the cell's **inner text block** — the one block a whole-cell edit rewrites — and
the recovery it names is a sub-span edit anchored by that inner block's id
(`AnchorById(block_id=…)`). Only that inner block's anchors refuse; a comment on the row's key
cell, on another cell, or on a later paragraph inside the same cell is untouched by the edit and
lets it through.
The
**write-hostile** refusal fires when the resolved block is an image / board / embed /
synced block — those hold no patchable text. Note what that list is *not*: it is the list
of block types that refuse an **EDIT**, and it is **not** a creatable list — a `TableNode`
is absent from it because a table's cells are **editable**, and a plain table is
**creatable** too, while a **merged** cell is neither (it refuses `write-hostile-target` on
an edit and a merge cannot be created at all — see the floor above). Insert/delete/sub-span edits use `InsertRequest` /
`DeleteRequest` / `SubSpanEditRequest` the same way.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### What a plan entry's `before` and `after` hold — one row per shape

The handshake above says *each entry is (block_id + before/after) OR a typed Refusal*. That
is true, and it is not the whole answer. The table below is **generated from the write layer's
own serializers**, so it cannot fall behind the code.

<!-- BEGIN PLAN-BEFORE-AFTER-SHAPES (generated
     regenerate with:  python -c "from larkdocio.write.plan_field_docs import plan_field_markdown as m; print(m())"  -->

A plan entry's `before` and `after` do **not** mean one thing. What they hold depends on which shape the entry is — and on one shape there is no `after` key at all, on another `before` is not text, and on a third the two are equal while the entry still changes something. Recognise the shape first, then read the pair. (The edit op is the tagless one: its entries carry no `"op"` key on the wire, so `entry.op` reads `"edit"` by default.)

| Plan entry | The shape | What `before` holds | What `after` holds |
|---|---|---|---|
| `entry.op == "delete"` | a block removal | The text that would be removed. | **Absent — this shape carries no `after` key at all.** |
| `entry.op == "subspan"` | an edit of part of a paragraph | The span only, verbatim — the words being replaced, never the block's whole text. | The replacement for that span only, likewise not the block's whole text. |
| `entry.op == "grow-table"` | a row appended to a table that already exists | **Not text.** A grid phrase — the table's shape as it stands, such as `3 rows × 2 columns`. | The same phrase for the grid as it would be, such as `4 rows × 2 columns`. This pair *is* the whole preview, because appending a row changes no text. |
| `entry.op == "edit"` | a whole-paragraph replace | The resolved block's current plain text, whole. | The replacement text, whole. |
| `entry.op == "edit"`, `entry.cell` set | a table-cell patch | The **cell's** own descendant text — never the whole container block's text. | The replacement text for that cell. |
| `entry.op == "edit"`, `entry.todo_done` set | a checkbox flip | The same string `after` holds: `before` == `after`, because this entry moves a checkbox and not the text. Reading the pair alone shows no change. | Equal to `before`. The change is carried by the separate `entry.todo_done` field, and nowhere else — an entry whose pair matches is not a no-op. |

The remaining ops carry **neither** field, because there is no old-text / new-text pair to show: what each one previews is the fields named beside it — `insert` (`position`, `content`, `block_id`, `insertion_point`) · `comment-create` (`comment`) · `comment-remove` (`comment`). A refused entry of any op carries `refusal` instead, and still carries the intent it was refused for.

<!-- END PLAN-BEFORE-AFTER-SHAPES -->

**On the cell-patch row, one field names the block that is actually written.**
`entry.cell.target_text_block_id` is the id of the **inner text block** the patch rewrites;
`entry.block_id` is the **container** it was addressed through — the cell itself. Both are on
the resolved entry, so you can read the id before you approve; it is also the id the whole-cell
refusals hand back in their `detail`, and the one to anchor a follow-up sub-span edit by.

### Recipe: find every construct that will refuse — one pass, not one attempt each

`compose()` stops at the **first** construct it cannot express, which is right and which
makes discovery cost one round trip per construct: a real migration of ~27,000 words of
existing prose took **eight** attempts — bold, italic, strikethrough, inline code, images,
links (including a nested `[[label]](url)`), then two more shapes the author's own sanitiser
had *produced*: a list item whose text opens with `#`, and angle-bracket text read
as raw HTML. Every one of those refusals was clear and named its fix. Only the one-at-a-time
discovery was expensive.

So run the checker first. `compose_check(markdown)` walks the same parse `compose()` walks and
**reports** instead of raising: every inexpressible construct, in document order, each with
its 1-based line and the same recovery text the refusal carries. It is read-only and offline —
no client, no credential, no network, and nothing here needs `.env` loaded — and it makes
nothing composable that was not composable before: `compose()` still refuses the whole batch
on the first construct.

Two behaviours to expect. Rows are **per occurrence**, not per construct, because two bold
spans on two lines are two edits (`constructs` is the de-duplicated view). And a construct
**inside a fenced code block is not reported** — a fence's body is content, not structure,
which is exactly the distinction a search for `**` cannot make.

```python
from larkdocio import compose_check

# The section you are about to author, lifted out of an existing document —
# emphasis, links and all.
fragment = """## Lorem ipsum

Lorem **ipsum** dolor sit *amet*, consectetur ~~adipiscing~~ elit.

See [the page](https://example.com/page) for more.

- # a bullet whose text opens with a hash

Lorem <ipsum dolor> sit amet.
"""

# …and a fenced code block, built here rather than typed inline so this page's own fence
# does not close early. Everything inside it is CONTENT: none of it is reported.
fence = "`" * 3
fragment += f"\n{fence}python\nleave = \"**this** alone: in a fence it is content\"\n{fence}\n"

report = compose_check(fragment)

print(report.ok)                      # False — this fragment would refuse
for row in report.refusals:           # every construct, in document order
    print(f"line {row.line}: {row.construct}")
    print(f"    {row.detail}")

kinds = report.constructs             # the de-duplicated kinds, for one summary line
lines = [row.line for row in report.refusals]
payload = report.to_dict()            # JSON-ready, if you report it rather than read it
```

Fix what it names, re-run it until `ok` is `True`, and only then compose and insert through
the ordinary gate — § "Recipe: author a Markdown fragment into a document", immediately below.

### Recipe: author a Markdown fragment into a document

Write the content as **Markdown**, compile it with `compose()`, and insert the result through
the same gate as any other write: `compose` → `dry_run` → `apply`. This is the shortest path
from "here is the section to add" to blocks in a document, and it is the reason the dialect
above is the reader's own: you can round-trip a section out of one document and back into
another. The fragment below deliberately uses **every creatable kind** — heading, paragraph,
nested bullet, todo, ordered item, table, fenced code, quote — plus an escaped metacharacter,
plus a **mermaid diagram fence**, so it doubles as a syntax reference.

**Do not edit the document concurrently while this runs.** The plan is built against the tree
you just read, so a concurrent human edit makes the engine **refuse rather than guess** —
by design: the engine refuses when the document changed under the plan rather than writing
into a position that has moved. A busy document just needs a **re-download** and a
**re-plan** (cheap — one read). See § "Do not edit the document while an authoring session
runs".

Two more things worth knowing. `compose()` **refuses** anything outside the dialect with the
construct and its line named (see the lossiness table above) — so a fragment carrying bold,
a link or a merged table fails loudly at compile time, before any write. And the reference
anchor is interchangeable: a verbatim **quote** (shown first) or an **`AnchorById`** carrying
a `block_id` — including one `apply()` just handed back, which is how the second insert below
anchors itself.

**A fragment of more than `MAX_CHILDREN_PER_CALL` (50) blocks does not go in one request.**
`compose()` compiles it happily; the `InsertRequest` below refuses it at construction with a
`ValueError`, before `dry_run` — see § "Recipe: author more than one call's worth of blocks" for
the split, the inter-batch anchoring and the order read-back.

**This recipe ADDS content. To change a document that already has content, see § "Recipe:
update an existing document — change or edit many blocks at once, without re-authoring it" —
do not re-author it.** Clearing a document and composing it again destroys every block id,
and with them every review anchor and every deep link into the document.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    InsertPosition,
    InsertRequest,
    WriteClient,
    apply,
    compose,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
read_id, read_secret = get_read_credentials()
reader = Client(read_id, read_secret, domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token
writer = WriteClient(*get_write_credentials(), domain)

# 1. WRITE THE CONTENT AS MARKDOWN — the reader's own dialect. A raw string keeps the
#    escaped `\#` literal; nesting is by tab or (as here) by spaces.
markdown = r"""## Findings

On-time delivery held at 97.2% for the quarter.

- the week-3 dip recovered by Friday
    - root cause: a stuck approval queue
- [ ] send the summary to the board

1. confirm the number with finance

| Metric | Value |
|--------|-------|
| On-time delivery | 97.2% |

~~~python
print("drafted by the agent")
~~~

> Quoting the brief: author the prose, not the styling.

~~~mermaid
flowchart TD
    A["Draft"] --> B["Shipped"]
~~~

\# An escaped metacharacter is literal text, not a heading.
"""

# 2. COMPILE it to typed content. ZERO writes — no client and no write creds are involved,
#    and a construct outside the dialect refuses HERE, naming the construct and its line.
content = compose(markdown)

# 3. READ + PARSE the document into the node tree the anchor resolves against.
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

# 4. DRY-RUN → a non-forgeable Plan, then APPLY. apply() hands back the ids it created,
#    in authored order (pre-order: a nested list item follows its parent).
plan = dry_run(
    [InsertRequest(
        reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
        position=InsertPosition.AFTER,
        content=content,
    )],
    root,
)
log = apply(plan, writer, document_id=doc_token)
created_block_ids = log.entries[0].created_block_ids

# 5. A FOLLOW-UP FRAGMENT, anchored BY ID — no re-quoting the text you just wrote. Re-read
#    first: a plan always resolves against a freshly parsed tree, and what you just created
#    is not in the tree you planned from.
docx, blocks = reader.get_docx_content(doc_token)
follow_up_plan = dry_run(
    [InsertRequest(
        reference=AnchorById(block_id=created_block_ids[0]),   # the `## Findings` heading
        position=InsertPosition.AFTER,
        content=compose("Composed again, anchored by the id apply() returned.\n"),
    )],
    Parser(Config()).parse_docx_tree(doc_token, blocks),
)
for entry in follow_up_plan.refusals:            # a stale/unknown id refuses, naming the id
    print(entry.refusal.reason, entry.refusal.detail)
follow_up_log = apply(follow_up_plan, writer, document_id=doc_token)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: author more than one call's worth of blocks — the 50-per-call cap, batched in order

**The failure this cures.** You compose a 40-section report, build one `InsertRequest` for it,
and get a **`ValueError` out of the constructor** — before `dry_run`, in a shape nothing else on
this surface raises. The cap is real and it is docx v1's: `create_children` creates **1–50**
blocks per call, one sibling group is one call, and `larkdocio.write.MAX_CHILDREN_PER_CALL` is
that number. Nothing is truncated and nothing is split for you, because a library that silently
issued eleven writes where you asked for one would be choosing your failure mode. Splitting it
yourself is three steps, and none of them is optional.

**The three steps, and why each is not optional.**

1. **Split on TOP-LEVEL blocks.** The cap counts one sibling group, so the groups you make must
   be groups of siblings: slice `compose()`'s output — which is a tuple of top-level blocks,
   each carrying its own nested `children` — into runs of at most `MAX_CHILDREN_PER_CALL`.
2. **Anchor batch *n+1* to what batch *n* created.** `apply()` hands back `created_block_ids`,
   and the next batch goes **`AFTER` the last top-level block of the previous one**
   (`AnchorById`; § "Recipe: anchor a follow-up by a created block id" is the neighbour that
   explains the anchor). **Read `created_block_ids` carefully: it is one id per created block in
   pre-order, so a nested list item's children are in it too** — the last id in the list can be
   a grandchild, and anchoring to it would file the next batch *inside* a list. The recipe below
   counts each top-level block's own descendants to find the right id.
3. **Prove the order by reading it back**, not by counting green applies. Order is exactly what
   an apply-log does not describe (§ "The read-back law — a green apply is not a receipt"), and
   a batch chain is where the question is live: eleven clean logs are compatible with a document
   whose eleventh batch is in the middle.

**Do not edit the document concurrently while this runs** — this script plans once per batch,
each plan against a freshly parsed tree, so the engine **refuses** rather than guessing when a
concurrent human edit moves the document under a plan and the recovery is a **re-download** and a **re-plan**. See § "Do not edit
the document while an authoring session runs".

**Batches are separate applies, so a failure mid-chain leaves a partial document.** That is the
honest trade for not being able to send it all at once: the batches that landed have landed. The
read-back at the end is what tells you which those were — and re-running is not idempotent, so
fix forward from what the read-back shows rather than replaying the whole fragment.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model import plain_text, walk
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    MAX_CHILDREN_PER_CALL,
    Anchor,
    AnchorById,
    InsertPosition,
    InsertRequest,
    WriteClient,
    apply,
    compose,
    dry_run,
)

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token


def read_document():
    """RE-READ before every batch. A plan resolves against a freshly parsed tree, and the
    blocks the previous batch created are not in the tree that planned it."""
    docx, blocks = reader.get_docx_content(doc_token)
    return docx.revision_id, Parser(Config()).parse_docx_tree(doc_token, blocks)


def created_count(block):
    """How many ids ONE authored block will occupy in `created_block_ids` — itself plus every
    descendant, because the ids come back in pre-order rather than one per top-level block."""
    return 1 + sum(created_count(child) for child in getattr(block, "children", ()))


# --- 1. THE FRAGMENT, and the split. 30 sections x 2 blocks = 60 > the 50-per-call cap.
TITLES = [f"Section {number}" for number in range(1, 31)]
markdown = "\n\n".join(f"## {title}\n\nThe body of {title.lower()}." for title in TITLES)
content = compose(markdown)
assert len(content) > MAX_CHILDREN_PER_CALL, (
    "this fragment fits in one call — send it as one InsertRequest and skip this recipe")
batches = [content[start:start + MAX_CHILDREN_PER_CALL]
           for start in range(0, len(content), MAX_CHILDREN_PER_CALL)]

# --- 2. LAND THEM IN ORDER. The first batch anchors where you want the fragment to start;
#        every later batch anchors AFTER the last TOP-LEVEL block the previous one created.
reference = Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",))
created_block_ids = []
for batch in batches:
    revision, root = read_document()
    plan = dry_run(
        [InsertRequest(reference=reference, position=InsertPosition.AFTER, content=batch)],
        root, document_revision_id=revision)
    assert plan.revision_guard == "active"       # armed: a concurrent edit refuses the batch
    log = apply(plan, writer, document_id=doc_token)   # RAISES on a refused entry
    # READ THE LOG, per the read-back law: 1:1 with the plan, applied and refusals split out.
    print(len(log.applied), "applied,", len(log.refusals), "refused")
    for entry in log.refusals:
        print("refused:", entry.refusal.reason, entry.refusal.detail)
    batch_ids = log.entries[0].created_block_ids
    created_block_ids.extend(batch_ids)
    # The id of the LAST TOP-LEVEL block of this batch — NOT batch_ids[-1], which is that
    # block's last descendant whenever the block has children.
    last_top_level = sum(created_count(block) for block in batch) - created_count(batch[-1])
    reference = AnchorById(block_id=batch_ids[last_top_level])

# --- 3. THE READ-BACK, AND IT ASSERTS THE ORDER. A clean log per batch says every call was
#        accepted; only the document says the batches are in the order you authored them.
_revision, root = read_document()
landed = [text for text in (plain_text(node) for node in walk(root)) if text in TITLES]
assert landed == TITLES, f"the fragment landed in this order instead: {landed}"
print(len(created_block_ids), "blocks created in", len(batches), "batches, in order")
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: author a mermaid diagram (and change one)

A diagram is a real creatable block, not a code fence: `NewBlock.mermaid(source)` creates a
docx **type-40 `add_ons`** block, the same kind the editor makes when a person inserts a
Mermaid diagram. Two halves, joined by a plain string:

- **`larkdocio.mermaid`** compiles a **structured spec** (`{"nodes": …, "edges": …}`) into
  Mermaid source, enforcing the dialect Lark's renderer actually accepts. Pure — no network,
  no document.
- **`NewBlock.mermaid(source)`** takes that source and goes through the ordinary
  `dry_run` → `apply` gate. No new op, no special endpoint.

**Why compile rather than write the source by hand.** Lark **validates nothing** inside a
diagram: invalid Mermaid, an unknown theme and an unknown view are all accepted and stored,
and the diagram then simply fails to draw. The compiler is the only place a guarantee can
live, which is why `larkdocio.mermaid.rules()` is worth reading before you hand-write source.

**There is no in-place update — changing a diagram is delete + re-create.** Lark's
block-patch surface has no `add_ons` updater at all, so the second half of this recipe
replaces a diagram rather than editing one, and **the `block_id` changes**. Do not cache a
diagram's `block_id` across an edit; re-resolve after one. That id is not only your handle on
the block:

> Block ids are what comments anchor to, so re-creating a block orphans every review comment left on it — the conversation is not moved, it is stranded, and nothing in the document says so afterwards. This library ships the join that shows you which comments are at stake before you decide: `review.for_node(block)` answers with what reviewers said about that exact block.

**Do not edit the document concurrently while this runs.** The plan is built against the tree
you just read, so a concurrent human edit makes the engine **refuse rather than guess** —
by design: the engine refuses when the document changed under the plan rather than writing
into a position that has moved. A busy document just needs a **re-download** and a
**re-plan** (cheap — one read).

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.mermaid import flowchart
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    WriteClient,
    apply,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
read_id, read_secret = get_read_credentials()
reader = Client(read_id, read_secret, domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token
writer = WriteClient(*get_write_credentials(), domain)

# 1. COMPILE a structured spec to Mermaid source. Pure: no client, no credentials, no writes.
#    An off-dialect spec is REFUSED HERE, before anything reaches a document — it raises
#    rather than compiling. Every construct the renderer cannot draw: an unknown theme,
#    direction, shape, edge style or message arrow; a length outside the sanctioned range; a
#    node, participant or subgraph whose identifier is unusable; an edge, message or subgraph
#    member naming an identifier nothing declares; and a label on an `invisible` edge, which
#    draws nothing and so can carry no text. The refusal names the construct and its value.
#    Two rules only WARN and then compile, because they are judgments about a valid diagram
#    rather than dialect errors: diagram size, and a wide horizontal layout. `rules()` marks
#    each rule enforced or advisory.
source = flowchart({
    "direction": "TD",
    "title": "Approval flow",
    "nodes": [
        {"id": "A", "label": "Draft"},
        {"id": "B", "label": "In review"},
        {"id": "C", "label": "Shipped"},
    ],
    "edges": [
        {"from": "A", "to": "B"},
        {"from": "B", "to": "C", "label": "approved"},
    ],
})

# 2. WRAP it as creatable content. `theme=` is optional and whitelisted; an empty source is
#    refused here, because Lark would store it and the reader emits nothing at all for one.
diagram = NewBlock.mermaid(source)

# 3. READ + PARSE, then DRY-RUN → APPLY through the same gate as any other insert.
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)
plan = dry_run(
    [InsertRequest(
        reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
        position=InsertPosition.AFTER,
        content=(diagram,),
    )],
    root,
)
log = apply(plan, writer, document_id=doc_token)
diagram_block_id = log.entries[0].created_block_ids[0]

# 4. CHANGE THE DIAGRAM — delete + re-create, because no in-place update exists. Insert the
#    new one BEFORE the old block so it lands where the old one was, then delete the old one.
#    Re-read first: a plan always resolves against a freshly parsed tree.
revised = NewBlock.mermaid(flowchart({
    "direction": "TD",
    "title": "Approval flow",
    "nodes": [
        {"id": "A", "label": "Draft"},
        {"id": "B", "label": "In review"},
        {"id": "C", "label": "Shipped"},
        {"id": "D", "label": "Archived"},
    ],
    "edges": [
        {"from": "A", "to": "B"},
        {"from": "B", "to": "C", "label": "approved"},
        {"from": "C", "to": "D"},
    ],
}))
docx, blocks = reader.get_docx_content(doc_token)
replace_plan = dry_run(
    [
        InsertRequest(
            reference=AnchorById(block_id=diagram_block_id),
            position=InsertPosition.BEFORE,
            content=(revised,),
        ),
        DeleteRequest(target=AnchorById(block_id=diagram_block_id)),
    ],
    Parser(Config()).parse_docx_tree(doc_token, blocks),
)
for entry in replace_plan.refusals:              # a stale/unknown id refuses, naming the id
    print(entry.refusal.reason, entry.refusal.detail)
replace_log = apply(replace_plan, writer, document_id=doc_token)

# 5. THE COST, MADE EXPLICIT: the new diagram has a NEW id. The old one no longer exists, so
#    any anchor you were holding for it is stale by construction.
new_diagram_block_id = replace_log.entries[0].created_block_ids[0]
print("the diagram's id changed:", new_diagram_block_id != diagram_block_id)
```

**The CLI variant — `larkdocio mermaid`** compiles step 1 above from a shell, with no Python
and no setup at all. It is the same compiler behind the same rules: a spec (JSON) in, Mermaid
source out. **Pure** — no credentials, no network, no document is touched — so a shell-driven
or agent-driven caller can reach it with nothing configured. It **only compiles**; putting the
source into a document is still the plan-gated library call above.

```bash
cat > spec.json <<'JSON'
{
  "direction": "TD",
  "title": "Approval flow",
  "nodes": [
    {"id": "A", "label": "Draft"},
    {"id": "B", "label": "In review"},
    {"id": "C", "label": "Shipped"}
  ],
  "edges": [
    {"from": "A", "to": "B"},
    {"from": "B", "to": "C", "label": "approved"}
  ]
}
JSON

larkdocio mermaid --flowchart spec.json > diagram.mmd
cat spec.json | larkdocio mermaid --flowchart -      # or read the spec from stdin
```

Either form emits exactly what `flowchart(spec)` returns, and nothing else — `diagram.mmd`
opens with:

```text
%%{init: {'flowchart': {'curve': 'stepAfter'}}}%%
flowchart TD
    %% Approval flow
    A[Draft]
```

**The diagram kind is stated, never guessed.** Pass `--flowchart` or `--sequence`, or give the
spec a `"kind"` key spelling one of them. Stating neither refuses, and a flag that contradicts
the key refuses rather than picking a winner: which keys a spec happens to carry
(`nodes`/`edges` against `participants`/`messages`) is never consulted, because a spec carrying
both — or neither — has no right answer.

**The refusal is the feature.** A spec the renderer could not draw does not compile to
something else; it stops, and the exit status says so, which is what makes this usable in a
script:

```bash
cat > broken.json <<'JSON'
{
  "nodes": [{"id": "A", "label": "Draft"}],
  "edges": [{"from": "A", "to": "ZZ"}]
}
JSON

larkdocio mermaid --flowchart broken.json > diagram.mmd
# Error: the edge 'A' → 'ZZ' names 'ZZ', which no node defines — the renderer draws nothing
# at all for an edge to a node that does not exist; the nodes this spec defines: A
#
# ...on stderr, with a non-zero exit status, an EMPTY stdout, and no `diagram.mmd` written —
# a refusal never leaves a half-finished diagram behind for the next command to read.
```

Two more things worth knowing before you script it. **Every message the command line logs goes
to stderr**, including the two advisory warnings a large or wide diagram earns, so a redirect
of stdout collects diagram source and only diagram source. And **`-o`/`--output` here names the
output *file*** (`larkdocio mermaid --sequence spec.json -o diagram.mmd`) — the same letter as
`larkdocio download`'s `-o`, which names a root that output is written under.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: update an existing document — change or edit many blocks at once, without re-authoring it

**What this is for.** Hand a document to an editing agent as Markdown, take the edited
Markdown back, and land **only what actually changed** — no re-authoring, no guessing which
paragraph the agent meant. `project_block_ids()` renders the document with one **identity
marker** per block; `reconcile()` diffs the edited Markdown against the projection it was made
from and answers, **per block**, whether it is unchanged, edited, newly inserted, deleted or
conserved — as a plan you can read **before** anything is applied. `compile_reconciliation()`
turns that plan into the same edit / insert / delete requests the rest of this guide uses, and
they go through the same `dry_run` → `apply` gate as everything else.

**Nothing about the level model changes here: the tree stays the source of truth.** This
projection is one more optional front-end onto it — exactly as authoring Markdown is — and the
edited Markdown is never written back as text; it is reconciled against the projection it came
from, and only the blocks that moved are edited on the tree. So everything the level chapter
says about the tree holds while you use this recipe, and none of it has to be re-learned to
use it.

**The supported shape is a WHOLE DOCUMENT, in and out — this is a real limitation, so read
it before you design around it.** You give the agent the **whole** projection and you take the
**whole** edited document back. **A patch, a unified diff, or an edited fragment is not
supported and is not tested**: nothing here accepts one, and handing `reconcile()` a fragment
describes a document that lost every block the fragment left out. If your agent emits a patch,
apply that patch to the projection yourself and pass the **complete** result.

**A block the Markdown cannot express is conserved, not destroyed** — this is about the blocks
you do NOT edit; for what an edited block costs, see the routing table above. A block outside
the dialect — an image,
a board, an embed — travels as a marker with no editable text beneath it. Leave it out of the
edited Markdown and it is **conserved**: never edited, never deleted, never re-created. One
shape is refused rather than guessed at, and the refusal names it: if a conserved block's
**marker** is missing while its **content** came back unmarked, planning that content as an
addition would leave the document holding the block twice, so the whole batch refuses
(`conserved-block-re-created`) and the fix is to put that one marker line back.

**Markers are identity, not content.** An identifier the projection never emitted names no
block and refuses (`marker-invented`) rather than matching by similarity; a marker for a block
this document's own projection emitted refuses **anywhere in the text** that would be sent —
on a line of its own or in the middle of a sentence, and nothing is quietly taken out to make
it fit — so **no marker ever reaches the document**; and every comparison
happens in the **decoded** domain, so an editor that only re-escaped the text changes nothing.

**The escaping contract, in one sentence: the projection you edit is ESCAPED, and
`reconcile()` writes back the decoded text — so a line you did not touch lands byte-identical,
and text you type into the projection follows the projection's own escaping.** That holds for
every block kind, the fenced code block included: a code line reading
`deploy rollback \-\-service $SERVICE` in the projection is `deploy rollback --service
$SERVICE` in the document, and is written back as exactly that. (Before **v1.34.0** it was
not: a fenced code block's body reached Lark still escaped, so editing one line of a code
block could put stray backslashes into the *other* lines — `larkdocio.release_notes()` says how
to spot and fix a document written before the fix.) If you
build the edited Markdown yourself rather than editing what you were handed, use
`unescape_literals` to read it and the same escaping to write it — never compare a raw string
against the projection's text.

**Do not edit the document concurrently while this runs** — the plan is built against the
projection you just read, so the engine **refuses rather than guessing** when a concurrent
change lands under the plan, and the recovery is always the same two steps: **re-download**
and **re-plan** (cheap). Pass the revision the read handed back and the whole batch refuses
with **zero writes** on drift, instead of applying half of it.

**Persisting the read — the same flow, with the left-hand side written to disk.** Everything
above stays true when the edit does not happen *now*: in another process, tomorrow, or after a
handoff to somebody else. `snapshot()` writes the read — the raw block payloads, the document
token, the `document_revision_id` and the `api_domain` the read was taken against — as one
versioned, checksummed file, and `load()` brings it back offline, with no credentials and no
call, handing you the same tree the read parsed. The domain travels because it is the one fact
a successor **cannot derive** from the other three: a token does not say `larksuite.com` from
`feishu.cn`. It is a routing fact and **not a credential** — no app id, no secret and no access
token is ever written into a snapshot. An artefact that carries no domain (one taken without
it, or one written by a release older than the field) loads fine and reports `api_domain` as
`None`; it is never defaulted, because the two domains are two different tenants.
The property that makes it usable is that **a load-then-project is byte-identical to the
projection the snapshot was taken from**, so an edit made against yesterday's projection still
reconciles today, against the same markers. Nothing else here moves: the projection, the edit,
`reconcile()`, the preview and the apply are the same steps in the same order.

**Which artefact is editable, and which is not.** The snapshot is **ours and immutable** — a
copy of one read, with no API that changes what it holds — and the **edited Markdown is the
editable artefact**, exactly as above: it is never written back as text, it is reconciled
against the projection it came from, and `reconcile()` is the only bridge between the two. A
snapshot that fails its checksum, arrives truncated, or carries a `format_version` this release
does not know is **refused typed, naming re-download as the fix — never repaired, never
migrated**; no cross-version migration is offered.

**A snapshot ages, and the guard refusing is the correct outcome.** The persisted
`document_revision_id` is what arms the `STALE_DOCUMENT` whole-document compare-and-swap at
`dry_run`, so if the document moved while the snapshot sat on disk the batch **refuses with
zero writes** rather than reconciling against a world that is gone — and the recovery is the
same two cheap steps as ever, re-download and re-plan. A snapshot is **not a lock**: it
reserves nothing, notices nothing, and stops nobody from editing the document. Take it *with*
the revision the read handed back, or the guard is not armed at all and `revision_guard` reads
`unavailable`.

**Scope, stated rather than left to be inferred.** This is **docx** only — there is no sheet
snapshot, no Base snapshot and no folder snapshot. A snapshot is **not a cache** (nothing
consults it to avoid a read), **not a backup** of the document (it is a copy of one read, and
the images and board PNGs a read wrote beside it are not in it), and not a lock. Whether a
snapshot taken by one release rehydrates under a much later one is **unmeasured, not refuted**:
the block payload is pinned exactly as it arrived, and the parser is what may move under it, so
the honest remedy for a snapshot you no longer trust is the same one every refusal names —
re-download.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model import plain_text, walk
from larkdocio.model.projection import (
    block_markdown,
    project_block_ids,
    replace_block_markdown,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    WriteClient,
    apply,
    compile_reconciliation,
    compose,
    dry_run,
    reconcile,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

# 1. READ + PROJECT. The projection is Markdown carrying one marker per block, plus the
#    identifiers it really emitted (block_ids) — identity comes from that list, never from
#    searching the text.
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)
projection = project_block_ids(root)

# 2. THE EDIT. Hand projection.markdown to your agent whole and take the whole document
#    back. Here the "agent" rewrites one paragraph. Splice BY BLOCK, never by line: a
#    paragraph carrying a soft return occupies two projected lines with a marker only above
#    the first, so "replace the line that starts with X" rewrites HALF a block and leaves
#    the rest — a garble reconcile() cannot see, because whatever comes back is authored
#    intent. replace_block_markdown replaces the block's whole segment, however many lines
#    that is. Write the replacement as PLAIN Markdown; the reconciler compares decoded on
#    both sides, so it must not be pre-escaped.
target = next(node for node in walk(root) if "Revenue grew" in plain_text(node))
new_text = "Revenue grew 15.0% in Q3."
edited = replace_block_markdown(projection, target.block_id, new_text)
#    AND AN INSERTION, in the same round: new content is simply text that came back with NO
#    marker of its own, and it is planned as an insert ANCHORED TO THE MARKED BLOCK IT
#    FOLLOWS — so it lands where you wrote it, and never has to be anchored to a block this
#    same batch creates. Add it BESIDE a block you are not editing (`block_markdown` gives
#    that block's own projected text back unchanged): an edit and an addition inside ONE
#    marker's segment is refused `segment-ambiguous`, because nothing could tell which piece
#    is the edited block. Two markers, two intentions, one round.
heading = next(node for node in walk(root) if plain_text(node) == "Overview")
heading_markdown = block_markdown(projection, heading.block_id)
inserted_text = "Gross margin held at 61%, on the same volume."
edited = edited.replace(heading_markdown,
                        f"{heading_markdown}\n\n{inserted_text}", 1)

# 3. RECONCILE — offline, no client, no network. A refusal is a plan that refuses, so read
#    plan.ok before compiling anything.
plan = reconcile(projection, edited)
assert plan.ok, [r.to_dict() for r in plan.refusals]
changed = [entry.state.value for entry in plan.changes]      # ['inserted', 'edited']

# 4. COMPILE → the shipped request families, then the SAME gate as every other write.
#    document_revision_id arms the whole-document guard: any drift under the plan refuses
#    the whole batch with zero writes.
requests = compile_reconciliation(plan, projection)
preview = dry_run(requests, root, document_revision_id=docx.revision_id)
log = apply(preview, WriteClient(*get_write_credentials(), domain), document_id=doc_token)

# 5. VERIFY by compose-equivalence, never string equality (see the recipe above): read the
#    document back and compare what it MEANS to what you asked for.
docx, blocks = reader.get_docx_content(doc_token)
read_back = Parser(Config()).parse_docx_content(doc_token, blocks)
region = next(part for part in read_back.split("\n\n") if "Revenue grew" in part)
same_content = compose(region) == compose(new_text)          # True — the verification
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **Read the plan before you compile it.** `plan.changes` is only the blocks that moved;
  `plan.conserved_block_ids` is what was left alone on purpose. A plan that refused carries
  typed refusals with a `detail` saying what to do — and it issued no request and made no
  network call to find out.
- **A conserved block can tell you whether its body came back changed — as a disclosure, not
  a verdict.** body_differs discloses that the block's body read back differently from the
  Markdown the projection emitted for it. That is one fact and it settles nothing: EITHER the
  consumer edited that body, OR the projection reshaped it and the editor normalised the
  reshaping. The plan asserts neither reading and compiles nothing either way — the block is
  conserved, left exactly alone. None means no opinion, which is not the same as False: a
  conserved block whose marker never came back has no read-back to compare. The key is on
  conserved entries only, and it is absent from the JSON of an entry that has no opinion, so a
  plan with nothing to disclose serializes exactly as it did before the field existed.
  `plan.conserved_block_ids_that_read_back_differently` is the subset it names — useful for
  "which conserved block do I look at first?", never as evidence that an edit happened.
- **A missing marker is not a deletion.** By default a block whose marker did not come back
  **refuses** rather than being deleted; pass `absent=AbsentBlockDisposition.DELETE` to state
  that the omission was meant.
- **Reordering blocks is refused, not approximated.** Expressing a move would mean deleting a
  block and inserting a copy, which destroys its identifier and everything anchored to it.

**Ticking a checkbox is one of these edits — and this is the worked flip.** Change `- [ ]` to
`- [x]` in that item's own segment and reconcile exactly as above; untick is the same edit the
other way round. Two things about the plan will look wrong if you are not expecting them, and
both are read in § "What a plan entry's `before` and `after` hold". The compiled request carries
the moved bit as `todo_done` beside a replacement equal to the item's **own** text, so the
entry's `before` and `after` come back **equal** — the change is the bit, and reading the pair
alone shows nothing. And a counted change whose write would be byte-identical to the block as
it stands is **refused** (`change-not-expressible`) rather than applied: before **v1.41.0** a
flip compiled to exactly that, so the log said `applied` and the box did not move. The block
below **creates** the item it then ticks, so nothing in it depends on the document you point it
at already carrying a checkbox; where one is already there, start at step 1 and splice that
block's id.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model.projection import project_block_ids, replace_block_markdown
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    InsertPosition,
    InsertRequest,
    WriteClient,
    apply,
    compile_reconciliation,
    compose,
    dry_run,
    reconcile,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token
writer = WriteClient(*get_write_credentials(), domain)
item = "send the summary to the board"

# 0. AN UNTICKED ITEM TO FLIP — the ordinary authoring route, so the rest of this block is
#    runnable anywhere. Skip this step for a document that already carries a checkbox.
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)
created = apply(
    dry_run([InsertRequest(
        reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
        position=InsertPosition.AFTER,
        content=compose(f"- [ ] {item}\n"),
    )], root, document_revision_id=docx.revision_id),
    writer, document_id=doc_token,
)
todo_block_id = created.entries[0].created_block_ids[0]

# 1. RE-READ AND PROJECT. What you just created is not in the tree you planned from, and
#    identity still comes from projection.block_ids — never from searching the text.
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)
projection = project_block_ids(root)
revision = docx.revision_id                    # what arms the whole-document guard, below
was_unticked = f"- [ ] {item}" in projection.markdown          # True — the box, as read

# 2. THE EDIT IS THE TICK. One character of one block's segment, spliced BY BLOCK ID; every
#    other line of the projection comes back byte-identical, so nothing else is planned.
edited = replace_block_markdown(projection, todo_block_id, f"- [x] {item}")

# 3. RECONCILE → COMPILE → THE SAME GATE as every other change in this recipe.
plan = reconcile(projection, edited)
assert plan.ok, [r.to_dict() for r in plan.refusals]
flip_states = [entry.state.value for entry in plan.changes]    # ['edited'] — one block moved
requests = compile_reconciliation(plan, projection)
moved_bit = requests[0].todo_done                             # True: the bit is what changed
same_words = requests[0].replacement == item                  # True: the text is not rewritten
preview = dry_run(requests, root, document_revision_id=revision)
log = apply(preview, writer, document_id=doc_token)

# 4. READ THE DOCUMENT BACK — a green apply is not a receipt, and the checkbox is the claim.
docx, blocks = reader.get_docx_content(doc_token)
read_back = Parser(Config()).parse_docx_content(doc_token, blocks)
ticked = f"- [x] {item}" in read_back                         # True — the box really moved
print(len(log.applied), "applied,", len(log.refusals), "refused; ticked:", ticked)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: edit part of a paragraph (a sub-span edit)

`EditRequest` replaces a **whole** block. `SubSpanEditRequest` replaces a **span inside** one
and **preserves the surrounding run styles** — the engine splits the matched run at the span
boundaries, rewrites only the span, and leaves every neighbouring run byte-identical. That is
the request to reach for when a paragraph is bold-and-linked prose and you only need to change
a number: a whole-block edit would flatten the styling to plain text, because created text is
unstyled.

Two rules make it refuse rather than guess. The `span` must occur **exactly once** in the
block's text (zero → `not-found`; more than one → not exactly one region → refused), and at
write time it must map to **exactly one uniformly-styled contiguous region** — a span crossing
runs of **differing style**, or overlapping a non-text inline, refuses `span-not-splittable`.
Anchoring is the usual pair: a verbatim quote + breadcrumb, or an `AnchorById`. The plan entry
shows the span, not the block: `before` / `after` are the **span's** old and new text, which is
how you can tell at a glance that you built a sub-span edit and not a whole-block one.

**A sub-span edit leaves the block permanently segmented, and a digest of it never comes back.**
The split is how the surrounding styles survive, and nothing undoes it: one run becomes up to
three, and this library carries no coalescing step — no request builder, no serializer and no
read path re-merges two adjacent runs that happen to carry the same style. A `snapshot()` digest
is a sha256 over the **raw block payloads**, so once a block has been segmented its digest
**never returns to its pre-edit value** — not even after the words are edited back to exactly
what they said before. Compare the **text** when the question is whether the document says
something different; a digest answers the narrower question *"are these the same payload
bytes"*, and after a sub-span edit the honest answer to that one is permanently no.

Two precisions, because the claim is wrong without either. **Only a proper substring segments
the block:** a span equal to the block's whole text has nothing either side of it to split off,
so that edit leaves the block as one run and its digest behaves as it always did. And **a
whole-block edit is the one path that re-merges** — it rebuilds the block as a single run, which
is the same mechanism that flattens the styling, and is why the routing table sends a styled
paragraph to this recipe instead. So a segmented block *can* be returned to one run; the price
of doing it is that flattening.

**Where the measurement stops.** The no-coalescing half is a statement about *this library*, and
it is held by a guard rather than by good intentions. Whether **Lark's own server** merges
adjacent identically-styled runs on its side is **unmeasured, not refuted** — no control for it
was run — so do not read the permanence claim as a claim about what the server keeps.

**This is also the only path that can edit text your reviewers have commented on.** Each run
the split rebuilds re-emits the inline comment anchors it carried, so the run that replaces
your span goes back to Lark carrying the anchors of the text it replaced, and a run the split
does not touch is sent back exactly as it came. The same uniform-region rule covers the
anchors: a span crossing runs whose anchors **differ** refuses `span-not-splittable` too,
because the replacement's anchors would be a guess — extend one reviewer's comment over text
they never commented on, or drop it. Narrow the span so it lies inside one run.
**The plan tells you when you are in that situation.** A resolved sub-span entry whose target
carries inline anchors carries a **`comment-anchors-present-on-target`** `preview_note` listing
the ids — read it with `entry.preview_notes` — so an approval step can show that reviewers are
involved, and you can join those ids to what they actually said with `comments()` before
approving. It costs **no extra API call**: the anchors are already on the tree you planned
against. A **whole-block**
edit on such a block refuses outright (`comment-anchors-present`, next section): it collapses
the block to one run, so there is nowhere honest to put a per-passage anchor. A **whole-cell**
(`TableLocator`) edit refuses for the same reason, and this recipe is its recovery too — anchor
the sub-span edit by the **inner text block's id** (the refusal's `detail` gives you that id),
since a row-key-and-column locator cannot name a span.

**Do not edit the document concurrently while this runs** — the plan is built against the tree
you just read, so the engine **refuses rather than guessing** when the document changed under
the plan, and a busy document just needs a **re-download** and a **re-plan** (cheap). See
§ "Do not edit the document while an authoring session runs".

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    SubSpanEditRequest,
    WriteClient,
    apply,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)

docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

# Change ONE number inside the sentence; every other run in the block keeps its styling.
requests = [
    SubSpanEditRequest(
        anchor=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
        span="12.4%",                       # must occur EXACTLY once in the block
        replacement="15.0%",
    ),
]
plan = dry_run(requests, root, document_revision_id=docx.revision_id)
entry = plan.entries[0]
print(entry.to_dict()["before"], "→", entry.to_dict()["after"])   # the SPAN, not the block
log = apply(plan, writer, document_id=doc_token)
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: edit a code block's text

A code block is an ordinary `EditRequest` target — its whole body is the "text" being replaced,
so rewriting a snippet is the same call that rewrites a paragraph. The recipe below authors one
(`NewBlock.code`, with a language), then rewrites its body **by the id `apply()` handed back**,
and finally authors a second block with **`language=None`** — a **bare fence**, the right choice
for content that is **not code**.

Three things worth knowing. The body is **verbatim in both directions**: leading
whitespace, whitespace-only lines and trailing whitespace all survive, so an indented snippet
or an ASCII diagram round-trips byte for byte — and a trailing `"\n"` you author is a trailing
blank line you read back. The **language cannot be changed by an edit** (an edit rewrites text,
not the block's style enum), so author the block with the token you want. And an unknown fence
token is refused at construction (`unknown-code-language`), never silently downgraded — if
nothing fits, that is exactly what `language=None` is for.

**Do not edit the document concurrently while this runs** — the plan is built against the tree
you just read, so the engine **refuses rather than guessing** when the document changed under
the plan, and a busy document just needs a **re-download** and a **re-plan** (cheap). See
§ "Do not edit the document while an authoring session runs".

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    WriteClient,
    apply,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)


def parse_tree():
    """Read + parse the CURRENT document — a plan resolves against a fresh tree."""
    docx, blocks = reader.get_docx_content(doc_token)
    return Parser(Config()).parse_docx_tree(doc_token, blocks)


# 1. AUTHOR a code block with a language token, and an ASCII-art block with NO language.
authored = apply(
    dry_run(
        [InsertRequest(
            reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
            position=InsertPosition.AFTER,
            content=(
                NewBlock.code("print('draft')", language="python"),
                # language=None ⇒ a BARE fence: the right choice for content that is not
                # code. The indentation below survives the round trip byte for byte.
                NewBlock.code("  +----+\n  | ok |\n  +----+", language=None),
            ),
        )],
        parse_tree(),
    ),
    writer, document_id=doc_token,
)
code_block_id, ascii_art_block_id = authored.entries[0].created_block_ids

# 2. REWRITE the snippet's body by id — a code block is an ordinary EditRequest target, and
#    the replacement is the block's WHOLE body (indentation included, verbatim).
plan = dry_run(
    [EditRequest(
        anchor=AnchorById(block_id=code_block_id),
        replacement="def total(rows):\n    return sum(rows)",
    )],
    parse_tree(),
)
log = apply(plan, writer, document_id=doc_token)
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: add a row to a table that already exists

`GrowTableRequest` appends one row to the end of a table already in the document, through the
same `dry_run` → `apply` gate, the same whole-document revision guard and the same refusal set
as every other change. **It preserves identity**: the table keeps its `block_id` and every
pre-existing cell keeps its own, in the same order — which is the whole reason to reach for it
rather than authoring the table again at the size you want and deleting the old one (that route
works, and it costs the block ids of the table and of every cell in it, and anything anchored
to them).

Anchor it either way. `AnchorById(block_id=…)` names the table directly — the id you already
hold from a read of the document, or the one `apply` handed back in `created_block_ids` when
you authored it. A `TableLocator` names it by one of its rows, for when you know the content
and not the id; a grow addresses the **table**, so only the parts of the locator that identify
the table are consulted (the column-target is what the *cell* path needs).

**Do not edit the document while this runs** — § "Do not edit the document while an authoring
session runs (the concurrency doctrine)". The plan carries the revision it was built against,
so a concurrent edit refuses the whole batch (`STALE_DOCUMENT`, zero writes) rather than
guessing; the repair is re-download and re-plan.

The script below authors a two-row table first, so it runs end to end against a document that
had none — if your table is already there, take its `block_id` off the read and skip straight
to the grow.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    AnchorById,
    Anchor,
    GrowTableRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    WriteClient,
    apply,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)

docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

# A table to grow. Skip this leg when the table is already in the document — read its
# block_id off the parsed tree instead (every parsed node carries one).
authored = apply(
    dry_run(
        [InsertRequest(
            reference=Anchor(quote="Revenue grew 12.4%"),
            position=InsertPosition.AFTER,
            content=(NewBlock.table([["Step", "Owner"], ["deploy", "ops"]],
                                    header_row=True),),
        )],
        root,
    ),
    writer,
    document_id=doc_token,
)
table_block_id = authored.entries[0].created_block_ids[0]

# Re-read: the plan is built against a tree, and the tree must know the table exists.
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

requests = [
    GrowTableRequest(anchor=AnchorById(block_id=table_block_id)),   # one row, at the end
    GrowTableRequest(anchor=AnchorById(block_id=table_block_id)),   # two rows? two requests
]
plan = dry_run(requests, root, document_revision_id=reader.read_document_revision(doc_token))
for entry in plan.entries:
    print(entry.to_dict()["before"], "→", entry.to_dict()["after"])   # "2 rows × 2 columns" → …
log = apply(plan, writer, document_id=doc_token)
# READ THE LOG — both sides. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.applied:
    # The cells that came into existence, row-major — what you fill next, one EditRequest each.
    print(entry.created_block_ids, entry.to_dict()["mutating_write_calls"])
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**One row per request, on purpose.** A row count would need a bound, and there is no row cap
here to bound it with: the row axis has been taken to 200 with no refusal at any row, so a cap
would memorialise a limit that is not Lark's. One row per request also means every entry is
exactly **one** write call, so its `atomic` is true and the log can never claim a partial
landing it did not have. N rows are N requests, each previewed and each approved.

**What it will not do, and how it says so.** It appends; it does not remove a row or a column,
does not append a column, and does not insert in the middle. A `row_index` other than `-1` is
**refused, typed `table-grow-unsupported`**, naming `-1` as the remedy — and saying plainly
that any other index is *unmeasured* from this library rather than something Lark was seen to
turn down. A grow that would take the grid past the `MAX_TABLE_CELLS` cap refuses under the
same reason, with the cap named and a second table as the remedy; that cap is this library's
own, and it is the same one that refuses an authored grid of the size. Anchor a block that is
not a table and it refuses `write-hostile-target`, naming the block and its kind — and note
that **editable is not creatable and neither is a hostile list a creatable list**: what a block
kind refuses here says nothing about what `NewBlock` can author, which § "Recipe: the docx
write handshake" states in full. The machine-readable form of the whole boundary is the
docx-write surface's `absences` register, under
`no-table-grid-change-beyond-appending-a-row`.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt". A
new row's cells arrive **empty**; the entry's `created_block_ids` is what you write into.

### Recipe: reorganise a document — there is no move, so a reorder is delete-and-recreate

**The failure this cures.** *"Put the escalation ladder back in the right order"* is one
sentence to a person and a **contract-level problem** here: there is no move operation (see
§ "Which write recipe do you need?", the note under the table), so the only way to express a
reorder is to **delete a block and create it again somewhere else** — which hands it a new id
and strands everything anchored to the old one. The discipline that makes that safe is
easy to get wrong one step at a time. Here it is once, in the order it has to happen, each step with the reason it is where it is.

**Why this is not a gap you can wait out — the premise is a measurement, not an inference.**
This recipe used to rest on larkdocio's own closed request-family set: *we* ship no move, so a
reorder has to be expressed the long way. That is still true, and it is now the weaker half of
the reason. The stronger half was measured on 2026-08-16: **Lark's docx `v1` API exposes no
move or reorder route either**, over eleven enumerated candidate spellings, at the scope the
note under the router's table states in full (one tenant, one day, a `tenant_access_token`, the
`larksuite.com` OpenAPI domain, docx `v1`; a `user_access_token`, another tenant, wiki-wrapped
documents, another API version, the web client's internal reorder API and any spelling outside
the eleven are **unmeasured, not refuted**). So delete-and-recreate is not a workaround for a
library that has not caught up — **it is the only shape the surface offers**, and the one
route that answers `code 0` to a request naming an existing block id answers it by making a
**copy** (same note, the boxed warning). Nothing below changes because of that measurement;
what changes is that the five steps are worth paying for rather than worth deferring.

**The five steps, and why each is not optional.**

1. **Comments FIRST, before anything is written.** A block you re-create takes its review
   conversation with it into nothing: the comments are not moved, they are **orphaned**, and
   nothing in the document says so afterwards. The join that tells you what is at stake is a
   read, and a read is free of consequences — so it goes first, while the answer can still
   change your mind. § "Recipe: read the comments on a document" is that leg in full.
2. **Insert the new content BEFORE deleting the old, never the reverse.** Both orders can fail
   half-way; only one of them fails **safely**. Delete-then-insert that dies in the middle
   leaves a document with a **hole** — content that exists nowhere. Insert-then-delete that
   dies in the middle leaves a document with **duplication** — every word still present,
   twice, which a person can read and fix. Prefer the failure a human can undo.
3. **Respect the insert cap.** A run of blocks that move together is **one** `InsertRequest`
   carrying many `NewBlock`s, and that content is capped at `MAX_CHILDREN_PER_CALL` (**50**)
   siblings per group — refused **at construction**, as a `ValueError`, never silently
   truncated. A longer run is split into consecutive requests, each anchored to the block the
   previous one followed: § "Recipe: author more than one call's worth of blocks — the
   50-per-call cap, batched in order" is that split written out, including the trap that
   `created_block_ids` comes back in pre-order.
4. **Preserve identity where you can — the blocks that did not move must not be re-created.**
   Compute the **longest common subsequence** of the current order and the order you want:
   those blocks are already where they belong, so leave them alone: a block this script never
   deletes is a block whose id is never re-minted, and nothing that addresses that id — a deep
   link into it, a review anchor on it, an `AnchorById` you were holding — is touched by the
   reorganisation at all. Only the genuinely-moved blocks are re-created. The LCS is also what gives the moved runs
   something stable to anchor to: **every insert below is anchored to a block that is not
   moving**, which is what keeps the whole reorganisation to one insert batch and one delete
   batch rather than one round trip per block. (It also side-steps the one-tree-one-batch
   rule: a request may not anchor to content another request in the same batch creates.)
5. **Verify by reading the order back** — per § "The read-back law — a green apply is not a
   receipt", and the read-back asserts the **final order**, not that the calls succeeded. This
   is the one operation where a fully-applied, refusal-free log is compatible with a document
   in the wrong order, because order is exactly what the log does not describe.

**Do not edit the document concurrently while this runs** — and here it matters twice, because
this script plans three times. The plan is built against the tree it just read, so the engine
**refuses rather than guessing** when the document changed under the plan, and the recovery is
the usual two cheap steps: **re-download** and **re-plan**. The failure this prevents is
specific to a reorganisation: a batch that half-applies against a moved document leaves the
duplication of step 2 with none of the cleanup of step 5. See § "Do not edit the document while
an authoring session runs".

**What it costs, stated before you run it.** Every moved block gets a **new id**; its old id is
gone, and so is anything anchored to it. Created text is **unstyled** (the creatable-content
floor), so a moved block that carried bold, colour or a link comes back plain — which is why
the LCS half matters: the cheapest way to keep styling is not to move the block. If most of the
document moves, this is not a reorganisation, it is a re-authoring, and the router's fourth-row
note applies.

**AND IF THE DOCUMENT CONTAINS A PICTURE, the arithmetic changes — read this before you plan
one.** An image block **does** delete (measured 2026-08-19; § "Recipe: put an image in a
document (create, upload, bind)" states the measurement and its scope), so the five steps above
still converge on an image-carrying document rather than stranding a copy on every pass. But an
image is **not** re-created by this script's own insert path — the compiler holds no bytes — so
a picture that genuinely moves is a **delete plus a fresh `put_image_in_document`**, and that
upload is a **new permanent media token**: the old one is not reclaimed by deleting its block,
and nothing purges it. Two consequences worth deciding on **before** the run: an image that has
not moved belongs in the LCS keep-set of step 4 for a much stronger reason than styling, and a
picture you do move must be targeted by its **block id** — an image has no quotable text, so
the quote anchor these steps use elsewhere refuses on one.

```python
from larkdocio.comments import comments
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model import plain_text, walk
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    MAX_CHILDREN_PER_CALL,
    AnchorById,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    WriteClient,
    apply,
    dry_run,
)

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

# THE ORDER YOU WANT, as one identifying fragment per block, top to bottom. This is the whole
# input: everything below is derived from it and from the document.
DESIRED = ["Revenue grew", "Step 1", "Step 2", "Step 3"]


def read_section():
    """RE-READ, every time. A plan resolves against a freshly parsed tree, and this script
    plans three times: once for the inserts, once for the deletes, once to verify."""
    meta, blocks = reader.get_docx_content(doc_token)
    tree = Parser(Config()).parse_docx_tree(doc_token, blocks)
    parent = next(node for node in walk(tree) if plain_text(node).startswith("Overview"))
    return meta, tree, parent


def label(text):
    """Which DESIRED fragment this block is — or the text itself when it is none of them."""
    return next((fragment for fragment in DESIRED if fragment in text), text)


def longest_common_subsequence(left, right):
    """The blocks that are ALREADY in the right place, in order. Exact LCS, not a heuristic:
    the more of it there is, the fewer ids this reorganisation destroys."""
    table = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            table[i + 1][j + 1] = (table[i][j] + 1 if a == b
                                   else max(table[i][j + 1], table[i + 1][j]))
    out, i, j = [], len(left), len(right)
    while i and j:
        if left[i - 1] == right[j - 1]:
            out.append(left[i - 1])
            i, j = i - 1, j - 1
        elif table[i - 1][j] >= table[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return out[::-1]


# --- 0. THE SAMPLE'S OWN SETUP — delete this step when you paste the recipe. ---
# Your document already HAS the blocks you want to reorder; this makes three (deliberately
# out of order) so the script below has something to move and runs end to end as printed.
meta, root, parent = read_section()
if len(parent.children) < len(DESIRED):
    setup = dry_run(
        [InsertRequest(reference=AnchorById(block_id=parent.children[-1].block_id),
                       position=InsertPosition.AFTER,
                       content=(NewBlock.paragraph("Step 2 — open an incident channel."),
                                NewBlock.paragraph("Step 3 — brief the duty manager."),
                                NewBlock.paragraph("Step 1 — page the on-call engineer.")))],
        root, document_revision_id=meta.revision_id)
    apply(setup, writer, document_id=doc_token)

# --- 1. THE COMMENTS, FIRST. A read, so it costs nothing but a call — and it is the ONLY
#        moment the orphan risk can still change your plan. Do not read "unavailable" as
#        "there are none": you do not know that.
review = comments(doc_token)
if not review.available:
    raise SystemExit(f"comments unavailable: {review.unavailable_reason} — "
                     "re-run when they can be read; a reorganisation is not a good place "
                     "to assume there is nothing to lose")

# --- 2. WHAT IS ALREADY IN THE RIGHT PLACE. Offline, free, and it decides everything else.
meta, root, parent = read_section()
texts = {child.block_id: plain_text(child) for child in parent.children}
current_ids = [child.block_id for child in parent.children]
desired_ids = []
for fragment in DESIRED:
    matches = [block_id for block_id, text in texts.items() if fragment in text]
    if len(matches) != 1:                        # exactly one or refuse, same as the engine
        raise SystemExit(f"{fragment!r} identifies {len(matches)} blocks, not one — "
                         "give each block a fragment only it carries")
    desired_ids.append(matches[0])
kept = set(longest_common_subsequence(current_ids, desired_ids))
moved_ids = [block_id for block_id in desired_ids if block_id not in kept]
assert kept, ("nothing is staying put, so this is a re-authoring rather than a "
              "reorganisation — see the write router's note on what a rewrite costs")

# --- 3. THE ORPHAN RISK, on the blocks that will actually be re-created. Their comments do
#        not travel; they are stranded. This script stops rather than deciding for you.
at_risk = {child.block_id: [comment.text for comment in review.for_node(child)]
           for child in parent.children if child.block_id in set(moved_ids)}
orphaning = {block_id: said for block_id, said in at_risk.items() if said}
if orphaning:
    raise SystemExit(f"these blocks carry review comments and are about to be re-created, "
                     f"which strands the conversation: {orphaning}. Resolve or relocate "
                     "them first, or accept the loss deliberately and delete this check.")

# --- 4. INSERT THE NEW COPIES — BEFORE any delete, so a failure here leaves duplication
#        rather than a hole. One request per RUN of moved blocks, each anchored to a block
#        that is NOT moving, so no request depends on another request's output.
requests, run, anchor = [], [], None
for block_id in desired_ids:
    if block_id in kept:
        if run:
            requests.append((anchor, tuple(run)))
            run = []
        anchor = block_id
    else:
        run.append(NewBlock.paragraph(texts[block_id]))
if run:
    requests.append((anchor, tuple(run)))
first_kept = next(block_id for block_id in desired_ids if block_id in kept)
inserts = [
    InsertRequest(
        reference=AnchorById(block_id=anchor or first_kept),
        position=InsertPosition.AFTER if anchor else InsertPosition.BEFORE,
        content=content,
    )
    for anchor, content in requests
]
assert all(len(request.content) <= MAX_CHILDREN_PER_CALL for request in inserts), (
    "a run longer than the cap is split into consecutive requests, each anchored to the "
    "block the previous run followed — see step 3 of this recipe's preamble")
plan = dry_run(inserts, root, document_revision_id=meta.revision_id)
assert plan.revision_guard == "active"
log = apply(plan, writer, document_id=doc_token)      # RAISES on a refused entry
recreated = [block_id for entry in log for block_id in entry.created_block_ids]

# --- 5. NOW DELETE THE ORIGINALS. Re-read first: the tree that planned the inserts does not
#        contain them. Each deleted entry carries `removed_payload` — the removed block's own
#        content, captured before the delete — which is the only record of what was there.
meta, root, parent = read_section()
removals = dry_run([DeleteRequest(target=AnchorById(block_id=block_id))
                    for block_id in moved_ids],
                   root, document_revision_id=meta.revision_id)
removal_log = apply(removals, writer, document_id=doc_token)
for entry in removal_log:
    print(entry.outcome, entry.block_id, bool(entry.removed_payload))

# --- 6. THE READ-BACK, AND IT ASSERTS THE ORDER. Not that the calls succeeded: a
#        fully-applied, refusal-free log is compatible with a document in the wrong order,
#        because order is the one thing the log does not describe.
meta, root, parent = read_section()
landed = [label(plain_text(child)) for child in parent.children]
assert landed == DESIRED, f"the document is in this order instead: {landed}"

# And the identity half of the same read-back: every block that did NOT move still has the
# id it had — with its deep links, its anchored comments and any AnchorById you were holding.
survivors = [child.block_id for child in parent.children if child.block_id in kept]
assert survivors == [block_id for block_id in desired_ids if block_id in kept]
print("reordered;", len(recreated), "block(s) re-created,", len(survivors), "id(s) preserved")
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(removal_log.applied), "applied,", len(removal_log.refusals), "refused")
for entry in removal_log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **The two applies are deliberate, and they are the whole safety argument.** One batch cannot
  express "insert these, then delete those" in a way that fails safely, because a refusal
  anywhere in a docx batch is a refusal of that entry only — the raise tells you, but the
  writes that landed have landed. Two applies, inserts first, means the worst outcome is a
  document that says everything twice.
- **`removed_payload` is the undo you will not get any other way.** It is read off the live
  block **before** the delete and carries the block's `block_id` and `block_type`, its
  `elements` with their per-run style, and its block-level `style` — plus, for a block whose
  content is not an `elements` container at all, that block's own content object **verbatim**:
  a diagram's `add_ons`, and an image's `image` (the file `token` and whatever geometry the
  live block carried). Log it somewhere a person can reach if the reorganisation is large.
- **For an image that record is a REFERENCE, not a restore — and the difference is the whole
  point.** Deleting the block destroys no bytes: the captured `token` still names the upload,
  and `DocxMediaClient.download(token)` fetches it back, so you can always say exactly what
  was removed and get the picture. But **nothing in this library re-binds a captured token to
  a new block** — `put_image_in_document` takes no pre-made token — so restoring the picture
  means uploading it again, which mints a **new** permanent media token beside the old one.
  Whether Lark's own API would accept a re-bind is **unmeasured, not refuted**: this library
  does not do it, and the record does not promise it.
- **A block that cannot be re-created cannot be moved.** An image, a board, an embed, a synced
  block — the creatable-content floor is the list of what a re-create can produce, so a
  reorganisation that would move one of those is refused at construction rather than half-done.
  Leave those blocks in the LCS (do not move them) and reorder around them.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: copy this — the end-to-end update script, from url to applied edit

**This flow also ships as ONE COMMAND — run it instead of retyping it.** The **file-first**
half of this recipe (Part A / Part B, below) is the console verb `larkdocio roundtrip`, the
only console verb that writes to Lark; its invocation is shown below the warnings, and **the
script here stays** because a library consumer needs the steps themselves.

**Copy this.** Every write integration re-implements the same preamble: url to token, the wiki
hop, read, parse the tree, project the block ids, edit, reconcile, preview, apply. Here it is
once, whole, in the order it has to happen — paste it, then change the middle. The recipe above
explains **why** each step is what it is; this one is the shape you keep.

**The `dry_run` step stays in.** It is the cheapest place a wrong plan can be caught, it makes
no network call of its own, and `document_revision_id` is what arms the whole-document guard —
without it the plan says `revision_guard == "unavailable"` and a concurrent edit is no longer
refused before the write. Deleting the preview to save a line is the one edit to this script
that costs something.

**Do not edit the document concurrently while this runs** — the plan is built against the
projection you just read, so the engine **refuses rather than guessing** when the document
changed under the plan, and the recovery is always the same two cheap steps: **re-download**
and **re-plan**. See § "Do not edit the document while an authoring session runs".

**The command form of the file-first half, whole:**

```bash
larkdocio roundtrip pull "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./edit/
# ...you (or your agent) edit ./edit/document.md — keep every marker where it is...
larkdocio roundtrip push -o ./edit/            # ALWAYS previews. Writes nothing.
larkdocio roundtrip push -o ./edit/ --apply    # applies THAT plan, then verifies by re-reading
```

Same steps, same order, same gates: `pull` writes `document.snapshot` (ours, immutable) and
`document.md` (yours, editable); `push` reconciles your edited file, **always** builds the
`dry_run` plan armed with the snapshot's revision, applies only under `--apply`, and then
re-reads the document and verifies it by **compose-equivalence**. There is no flag that skips
the preview. In Python it is `larkdocio.roundtrip.pull()` / `.push()` — and the script below is
what both of those do, in the order they do it.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model import plain_text, walk
from larkdocio.model.projection import (
    project_block_ids,
    replace_block_markdown,
)
from larkdocio.errors import LarkApplyRefusedError
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    WriteClient,
    apply,
    compile_reconciliation,
    dry_run,
    reconcile,
)

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded

# 1. URL -> TOKEN, wiki hop included. A wiki URL wraps the real docx token; skip this branch
#    and the read returns an empty document while every later step politely refuses.
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
if doc_type == "wiki":
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

# 2. READ + PARSE. Keep `docx.revision_id` — it is what arms the whole-document guard at
#    step 6. parse_docx_tree gives the NODE TREE (parse_docx_content would give Markdown,
#    which nothing here can anchor on).
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

# 3. PROJECT the block ids. This is the step that makes an update an update instead of a
#    re-authoring: every block travels with an identity marker, so it can be changed in
#    place rather than deleted and made again.
projection = project_block_ids(root)

# 4. THE EDIT. Hand `projection.markdown` out WHOLE and take the WHOLE document back — a
#    fragment describes a document that lost every block it left out. Splice BY BLOCK: a
#    paragraph carrying a soft return spans two projected lines under one marker, so a
#    line-level replacement rewrites half of it and reconcile() cannot tell. Take the
#    identity off the TREE (never off the rendered text) and write plain Markdown back.
target = next(node for node in walk(root) if "Revenue grew" in plain_text(node))
edited = replace_block_markdown(projection, target.block_id, "Revenue grew 15.0% in Q3.")

# 5. RECONCILE — offline, no client, no network. A refusal is a plan that refuses, so read
#    plan.ok before compiling anything.
plan = reconcile(projection, edited)
assert plan.ok, [refusal.to_dict() for refusal in plan.refusals]
changed = [entry.state.value for entry in plan.changes]

# 6. COMPILE -> PREVIEW. The same gate as every other write in this guide.
requests = compile_reconciliation(plan, projection)
preview = dry_run(requests, root, document_revision_id=docx.revision_id)
assert preview.revision_guard == "active"

# 7. APPLY with the WRITE app. Only a Plan reaches apply — and READ THE LOG. A refused
#    entry RAISES (LarkApplyRefusedError), so a run that wrote nothing cannot exit 0 by
#    accident; the whole log rides on the exception and nothing is rolled back. Pass
#    allow_partial=True instead when your caller already handles refusals itself.
try:
    log = apply(preview, WriteClient(*get_write_credentials(), domain), document_id=doc_token)
except LarkApplyRefusedError as refused:
    for why in refused.refusals:            # reason + detail, per refused entry
        print(f"REFUSED — {why['reason']}: {why['detail']}")
    raise                                   # usually: re-download, re-plan, re-apply
applied = [entry.to_dict()["outcome"] for entry in log]   # the log iterates, and has len()
```

- **What you changed is the middle.** Steps 1–3 and 5–7 are the same for every update; step 4
  is your application. Swapping the hand-written line edit for an agent round trip changes
  nothing else in this script.
- **Nothing here deletes and re-creates a block that only changed its text**, which is what
  separates an update from a rewrite. A rewrite hands every block a new id, and everything
  addressed by the old ids — deep links, and any review comments left on them — is then
  pointing at ids the document no longer has.
- **Every refusal is typed and carries a `detail`.** `plan.refusals` on the offline half,
  `log.entries` on the applied half — neither ever guesses.

**The file-first variant of the same script — when the edit happens in a later process.** Same
steps, same order, same gate; the only difference is that the read is written to disk between
them, so the second half can run tomorrow, on another machine, or after a handoff. Part A ends
at `snapshot` and Part B *starts* at `load`; **the `dry_run` step stays in** for the reason
given above, and the revision that arms the guard now comes off the snapshot instead of off a
read that happened seconds ago. Both halves run as written — copy Part B into a file of its own
and it needs nothing from Part A but the two files it left behind.

```python
# ── PART A — THE READ LEG. Run it once. It ends by writing two files: the snapshot
#    (ours, immutable) and the projection (theirs, editable).
from larkdocio.common import (
    get_read_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model.projection import project_block_ids
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.snapshot import snapshot

init_env(".env")

url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
if doc_type == "wiki":
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)
projection = project_block_ids(root)

# The snapshot persists the READ, not the projection: the payload is the evidence, and the
# projection is derived from it — which is why it comes back byte-identical in Part B.
# `api_domain` is the one fact Part B cannot derive from the token: pass it, and the resumed
# half builds its client from the file instead of needing this URL again.
snapshot(blocks, document_token=doc_token, document_revision_id=docx.revision_id,
         api_domain=domain, path="document.snapshot")
with open("document.md", "w", encoding="utf-8") as handle:
    handle.write(projection.markdown)        # THIS is the file your editing agent works on

# ── PART B — RESUME HERE, in a process of its own. Everything below needs nothing above
#    it but the two files; copy from this line down into a script of its own.
from larkdocio.common import (
    get_write_credentials,
    init_env,
)
from larkdocio.model import plain_text, walk
from larkdocio.model.projection import (
    block_markdown,
    project_block_ids,
)
from larkdocio.errors import LarkApplyRefusedError
from larkdocio.snapshot import load
from larkdocio.write import (
    WriteClient,
    apply,
    compile_reconciliation,
    dry_run,
    reconcile,
)

init_env(".env")

snap = load("document.snapshot")             # refuses typed if the file was corrupted
root = snap.tree
projection = project_block_ids(root)         # byte-identical to Part A's projection

with open("document.md", encoding="utf-8") as handle:
    edited = handle.read()

# THE EDIT. In your integration the agent has already changed document.md by now; here it
# is edited in line so the half below is runnable exactly as printed. block_markdown gives
# the block's WHOLE projected Markdown — however many lines a soft return split it across —
# so this swaps a block, not a line, which is the difference between the edit you asked for
# and a half-rewritten sentence nothing downstream can see.
# "Revenue grew" is THIS SAMPLE'S text: searched with a default so pasting it against your
# own document tells you nothing matched instead of raising StopIteration from a bare next().
target = next((node for node in walk(root) if "Revenue grew" in plain_text(node)), None)
if target is None:
    raise SystemExit("no block matched — change the search text to something your "
                     "document actually says")
edited = edited.replace(block_markdown(projection, target.block_id),
                        "Revenue grew 15.0% in Q3.", 1)

plan = reconcile(projection, edited)
assert plan.ok, [refusal.to_dict() for refusal in plan.refusals]

requests = compile_reconciliation(plan, projection)
preview = dry_run(requests, root, document_revision_id=snap.document_revision_id)
assert preview.revision_guard == "active"    # the SNAPSHOT's revision is what arms it

# The snapshot holds the API domain the read was taken against as well as the token, so the
# client is built from the FILE — no URL, no environment beyond the credentials. (An artefact
# written before that field existed reports `api_domain` as None; take a fresh snapshot.)
try:
    log = apply(preview, WriteClient(*get_write_credentials(), snap.api_domain),
                document_id=snap.document_token)
except LarkApplyRefusedError as refused:
    for why in refused.refusals:
        print(f"REFUSED — {why['reason']}: {why['detail']}")
    raise
applied = [entry.to_dict()["outcome"] for entry in log]
```

- **The snapshot is the read, not the plan.** It reserves nothing and locks nothing; if the
  document moved while it sat on disk, `dry_run` refuses the batch and the fix is the usual
  re-download and re-plan.
- **Two files, two owners.** `document.snapshot` is ours and immutable, `document.md` is the
  editable artefact, and `reconcile()` is the only bridge between them — the same boundary the
  recipe above states, with a filesystem in the middle.
- **Both filenames are DERIVED — read them, do not retype them.** `document.snapshot` and
  `document.md` are the current values of `roundtrip.SNAPSHOT_FILENAME` and
  `roundtrip.MARKDOWN_FILENAME`. `roundtrip.snapshot_path(workdir)` and
  `roundtrip.markdown_path(workdir)` join either name onto a working directory, and `pull()`
  hands both back already joined, as `PullResult.snapshot_path` and `PullResult.markdown_path`
  — that pair is what a caller actually holds after the read leg, so read it rather than
  re-deriving anything. **What is promised is the pair of paths on that result; the two
  spellings are NOT promised** — they are the values of two constants, so a hard-coded
  `"document.md"` in your own code is a copy of a value rather than a read of it, and it is the
  copy that goes stale. (Neither name has moved since this verb shipped. That is a fact about
  what happened, not a commitment about what will.) **A shell caller cannot import a
  constant**, so print the current values instead of guessing them:
  `python -c "from larkdocio import roundtrip; print(roundtrip.SNAPSHOT_FILENAME, roundtrip.MARKDOWN_FILENAME)"`

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: anchor a follow-up by a created block id

`apply()` hands back the ids of everything it created (`created_block_ids`, in authored
order), and every parsed node carries its `block_id` — so a follow-up request should point at
the **id**, not at a quote of the text you just wrote. `AnchorById(block_id=...)` goes anywhere
an `Anchor` goes: `InsertRequest(reference=...)`, `EditRequest(anchor=...)`,
`DeleteRequest(target=...)`, `SubSpanEditRequest(anchor=...)`.

**Read that list twice: the keyword differs by request type.** One anchor object, three
names — `reference` on an insert (it is positioned *relative to* a block it does not touch),
`target` on a delete (it names the block being removed), `anchor` on an edit and a sub-span
edit. Passing a delete's `target=` to an insert is a plain `TypeError`, and Python's
did-you-mean does not suggest the sibling spelling — so take the name from this list rather
than from memory.

Two things to know. **A plan always resolves offline against a parsed tree**, so re-read and
`parse_docx_tree` again before the follow-up — the block you just created is not in the tree
you planned from. (That read is not the indirection an id removes; what an id removes is having
to *re-quote* text, which is ambiguous when the text repeats and stale the moment it changes.)
And **an id-anchored write is a compare-and-swap**: the plan captures the block's text and the
write refuses `STALE_ANCHOR` if anything changed it in between. So **do not edit the document
concurrently while this runs** — the engine **refuses rather than guessing** when the document
changed under the plan, and a busy document just needs a **re-download** and a **re-plan**
(cheap). See § "Do not edit the document while an authoring session runs".

An id that never existed, belongs to another document, or has been deleted is **refused with
the id named in the refusal's `detail`** — ids are matched by exact equality and never
fuzzy-matched to a near miss.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    WriteClient,
    apply,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
read_id, read_secret = get_read_credentials()
reader = Client(read_id, read_secret, domain)
writer = WriteClient(*get_write_credentials(), domain)


def parse_tree():
    """Read + parse the CURRENT document — a plan resolves against a fresh tree."""
    docx, blocks = reader.get_docx_content(doc_token)
    return Parser(Config()).parse_docx_tree(doc_token, blocks)


# 1. AUTHOR something, anchored the usual way (a verbatim quote + its heading path).
insert = InsertRequest(
    reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
    position=InsertPosition.AFTER,
    content=(NewBlock.heading(2, "Findings"), NewBlock.paragraph("Drafted by the agent.")),
)
insert_log = apply(dry_run([insert], parse_tree()), writer, document_id=doc_token)

# 2. apply() RETURNS THE IDS IT CREATED, in authored order.
created_block_ids = insert_log.entries[0].created_block_ids
heading_id, paragraph_id = created_block_ids

# 3. FOLLOW UP BY ID against a freshly parsed tree — no re-quoting, no breadcrumb, no
#    ambiguity. (A DeleteRequest(target=AnchorById(...)) removes it just as directly.)
follow_up = EditRequest(
    anchor=AnchorById(block_id=paragraph_id),
    replacement="Drafted by the agent, then revised by id.",
)
plan = dry_run([follow_up], parse_tree())
for entry in plan.refusals:                  # a stale/unknown id refuses, naming the id
    print(entry.refusal.reason, entry.refusal.detail)
follow_up_log = apply(plan, writer, document_id=doc_token)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: accumulate edits across turns (a multi-turn request queue)

**The pattern for a conversational agent** — the one every recipe above deliberately does not
show, because they are all single scripts. An agent talking to a user over many turns collects
edits *as they are agreed* and commits them later, which needs exactly one primitive: something
portable to hold between turns.

**Keep requests, not plans.** Requests are the portable half — `EditRequest`,
`InsertRequest`, `DeleteRequest` and `SubSpanEditRequest` are frozen values that round-trip
through **`to_dict()` / `from_dict()`**, so a pending-edit queue can live in JSON, a database
row, or the conversation's own state. A `Plan` is **deliberately not** portable: it has no
`from_dict`, so there is nothing to reload. At commit time you therefore **rebuild the requests,
read the document, and plan FRESH** — `dry_run` → inspect → `apply`, all inside the same
commit. Everything before that is inert bookkeeping: queuing a request touches no client, no
credentials, and no network.

That is not a limitation to work around, it is the guarantee: because a `Plan` **cannot be
reconstructed from a snapshot** and `apply()` **re-validates live immediately before writing**,
a stale account of "what we planned three turns ago" **can never reach `apply()`**. See § "The
two-level design" for the trust property in full.

Two practical notes. Rebuilding dispatches on the **`"op"` discriminator** each request
serializes with (`insert` / `delete` / `subspan`) — an `EditRequest` is **tagless**, so a record
with no `"op"` key is one of those, which is what the `REBUILD` table below encodes. And a queue
that has been sitting for a while is *supposed* to refuse if the document moved underneath it:
inspect `plan.refusals` before applying, and hand the user back the ones that no longer resolve
rather than retrying them.

**The one rule a queue has to obey: every queued request must target content that exists at
commit time; commit the insert, then anchor follow-ups by `created_block_ids`.** The reason is
**one tree, one batch** — every request in a batch is resolved against a **single consistent
snapshot** of the document, which is exactly what makes the staleness guards mean anything, so
**a batch cannot depend on its own writes**. Queue an `InsertRequest` and then, in the *same*
batch, an `EditRequest` anchored on the text that insert will create, and the second one refuses
`not-found` — correctly: at plan time the block does not exist, and no amount of re-reading will
make it appear. That is the commonest way to get this wrong (insert a section, then refine what
you just inserted), so the refusal **says so**: when the anchor text appears in the same batch's
queued insert content, the `detail` names the intra-batch cause and points at the idiom below
instead of sending you back to re-read.

The idiom is **two commits**, and the recipe ends with it: **commit 1** applies the queue and
`apply()` hands back `created_block_ids`; **commit 2** re-reads and anchors the follow-up by one
of those ids (`AnchorById(block_id=...)`). Across commits there is nothing to work around — the
block really does exist by then — and an id is a better anchor than a quote of your own text
anyway (see § "Recipe: anchor a follow-up by a created block id").

**Do not edit the document concurrently while this runs** — the plan is built against the tree
you just read, so the engine **refuses rather than guessing** when the document changed under
the plan, and a busy document just needs a **re-download** and a **re-plan** (cheap). See
§ "Do not edit the document while an authoring session runs".

```python
import json

from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    SubSpanEditRequest,
    WriteClient,
    apply,
    compose,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)

# Rebuild dispatches on the "op" discriminator each request serializes with; the untagged
# EditRequest is TAGLESS, so a record with no "op" key is one of those.
REBUILD = {
    "insert": InsertRequest.from_dict,
    "delete": DeleteRequest.from_dict,
    "subspan": SubSpanEditRequest.from_dict,
    None: EditRequest.from_dict,
}
queue = []                      # what survives a turn boundary: JSON, not objects


def remember(request):
    """Park an agreed edit as JSON. No client, no credentials, no writes — inert data."""
    queue.append(json.dumps(request.to_dict()))


# ---- TURN 1: the user approves a new section (authored in Markdown) ------------------
remember(InsertRequest(
    reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
    position=InsertPosition.AFTER,
    content=compose("## Findings\n\nOn-time delivery held at 97.2%.\n"),
))

# ---- TURN 2: ...then asks for one number to be corrected in place -------------------
remember(SubSpanEditRequest(
    anchor=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
    span="12.4%",
    replacement="15.0%",
))

# ---- TURN 3: ...and the section retitled (a tagless EditRequest record) -------------
remember(EditRequest(
    anchor=Anchor(quote="Overview", breadcrumb=()),
    replacement="Overview and outlook",
))

# ---- COMMIT 1: rebuild the requests, then plan FRESH against a document read NOW ----
# Every request in this batch targets content that EXISTS NOW. Nothing here may anchor on the
# "## Findings" section turn 1 is about to create: one tree, one batch — a batch cannot depend
# on its own writes, and such an entry would refuse `not-found` (the detail says why).
requests = [REBUILD[record.get("op")](record) for record in map(json.loads, queue)]
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)
plan = dry_run(requests, root, document_revision_id=docx.revision_id)
assert plan.revision_guard == "active"
for refused in plan.refusals:            # a queued edit whose target moved refuses HERE
    print(refused.refusal.reason, refused.refusal.detail)
log = apply(plan, writer, document_id=doc_token)

# ---- COMMIT 2: NOW the new section exists — anchor the follow-up BY ITS ID -----------
# apply() handed back one id per block it created, in authored order. Re-read (a plan always
# resolves against a freshly parsed tree), then target the id — no re-quoting your own text.
created_block_ids = log.entries[0].created_block_ids
findings_heading_id = created_block_ids[0]                # the "## Findings" heading
docx, blocks = reader.get_docx_content(doc_token)
follow_up_plan = dry_run(
    [InsertRequest(
        reference=AnchorById(block_id=findings_heading_id),
        position=InsertPosition.AFTER,
        content=compose("Signed off by the operator.\n"),
    )],
    Parser(Config()).parse_docx_tree(doc_token, blocks),
    document_revision_id=docx.revision_id,
)
for refused in follow_up_plan.refusals:  # a stale/unknown id refuses, naming the id
    print(refused.refusal.reason, refused.refusal.detail)
follow_up_log = apply(follow_up_plan, writer, document_id=doc_token)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: verify what you authored — compose-equivalence, not string equality

**Read this before you write a self-check.** The obvious way to verify your own write is to
read the document back and compare the Markdown to what you authored. That comparison
**fails on every list you will ever author**, and nothing is wrong with the write.

Two normalizations sit between the two strings, and neither loses anything:

| You author | The reader emits | Why |
|------------|------------------|-----|
| `- a`⏎`- b` (a **tight** list) | `- a`⏎⏎`- b` (a **loose** list — blank line between items) | The reader emits one blank line between block-level items, uniformly. |
| a nested item indented with **spaces** | the same item indented with a **tab** | The reader writes one tab per nesting level; both are accepted on the way in. |

So `authored in read_back` is `False`, and it is `False` for a **rendering** reason. The
comparator that tells you the truth is **compose-equivalence, not string equality**: compile
both sides with `compose()` and compare *that*. `compose()` returns a tuple of **frozen**
`NewBlock` values, so `==` is the entire comparison — there is no helper to import, no
normalizer to write, and no diff library to reach for.

`compose(a) == compose(b)` answers "do these two Markdown strings mean the same content?".
If the read-back region contains something outside the dialect (a pre-existing **bold run**,
say), `compose()` refuses it by name and line rather than returning a misleading `False` —
which is why the comparison is left as the two `compose()` calls instead of being wrapped in
a boolean helper that would have to swallow that.

This recipe writes before it verifies, so the authoring doctrine applies to it in full: **do
not edit the document** while it runs. A **concurrent** edit makes the engine **refuse**
`STALE_DOCUMENT` / `STALE_ANCHOR` **rather than guess** where your content should land, and
the recovery is always the same two steps — **re-download** and **re-plan**. Hold the
document still for the seconds the batch takes.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    InsertPosition,
    InsertRequest,
    WriteClient,
    apply,
    compose,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

# 1. AUTHOR a list the way you naturally write one: TIGHT, no blank lines.
authored = "- the week-3 dip recovered by Friday\n- root cause: a stuck approval queue\n"

docx, blocks = reader.get_docx_content(doc_token)
plan = dry_run(
    [InsertRequest(
        reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
        position=InsertPosition.AFTER,
        content=compose(authored),
    )],
    Parser(Config()).parse_docx_tree(doc_token, blocks),
    document_revision_id=docx.revision_id,
)
log = apply(plan, WriteClient(*get_write_credentials(), domain), document_id=doc_token)

# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)

# 2. READ IT BACK — the same read any consumer does. This step IS the read-back law, and it
# is why this recipe exists: the log above says what was ACCEPTED, the read below says what
# the document CONTAINS, and only the second one is the verification.
docx, blocks = reader.get_docx_content(doc_token)
read_back = Parser(Config()).parse_docx_content(doc_token, blocks)

# 3. THE TRAP: string equality. Your own text is NOT in the document you just wrote it
# to, because the reader's list form is LOOSE. False for every list you author.
found_verbatim = authored in read_back                       # False — and nothing is wrong

# 4. THE COMPARATOR THAT IS TRUE: compose-equivalence. The loose form IS what the reader
# emitted, and it composes to the same two bullets — so nothing was lost.
reader_form = "- the week-3 dip recovered by Friday\n\n- root cause: a stuck approval queue\n"
found_loose = reader_form in read_back                       # True — it really is there
same_content = compose(authored) == compose(reader_form)     # True — the verification
```

- **`compose()` writes nothing** (no client, no credentials, no transport), so a
  verification pass costs one read and no risk.
- **Round-tripping is a fixed point.** Feed the read-back through `compose()` again and the
  content stops changing — each normalization is a normalization, not a progressive loss.
- **Do not "fix" your authored Markdown to match the read-back.** Both forms compose to the
  same blocks; authoring tight lists is correct.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: a rate limit interrupted your rewrite and the re-push refuses "stale-anchor" — the idempotent repair

**The failure this cures.** A rewrite of 32 entries
is part-way through when Lark answers **HTTP 429**. The run stops. The obvious recovery —
push the same batch again — comes back
`31 of 32 entries applied; 1 refused (stale-anchor x1)`.

The one refusal was a **delete whose block the interrupted run had already removed**. The
engine re-reads every anchored block immediately before writing to it, and a block it cannot
re-read is by definition not the block the plan previewed — so that entry is refused, **nothing
is written for it**, and the rest of the batch carries on. The refusal says as much in its own
`detail`: *"the block has most likely been DELETED since the plan was built. NO write was
issued."*

**The behaviour is correct, and this recipe does not relax it.** It is
the right reading: exactly-one-or-refuse is what makes every other guarantee here mean anything, and an
anchor allowed to match nothing would make a clean apply-log compatible with a document nobody
touched. **There is no `allow_missing` on `DeleteRequest`** — the flag does not exist, and
nothing below waits for one.

**So the idempotence goes in YOUR plan construction, which is where it belongs.** Express the
repair as *"the document must no longer contain these things"* rather than as *"delete these
ids"*, re-derive it against a **fresh** read every time, and the deletes for blocks that are
already gone are never built in the first place. Run it twice and the second run sends nothing.

Three rules, and each one removes a way the naive retry fails:

1. **Re-read, and plan against that read.** The ids the interrupted run was holding describe a
   document that no longer exists. A plan built on them is a plan built on a memory.
2. **Filter the requests against what the fresh read actually contains.** This is the whole
   trick, and it is four lines: the blocks the interrupted run already removed are simply
   absent from the read, so no request is built for them. Nothing is *suppressed* — there was
   never anything to suppress.
3. **Arm the whole-document guard** with the `revision_id` that same read reported. The repair
   is running because something went wrong once already; if the document moved again while you
   were re-planning, the **whole batch** refuses with zero writes rather than half-repairing it.

**DO NOT EDIT THE DOCUMENT while the repair runs.** It plans against the tree it just read, so
a **concurrent** human edit is the one thing that can make a repair need repairing: the engine
**refuses rather than guessing** when the document changed under the plan, and the recovery is
the same two cheap steps as everywhere else — **re-download** and **re-plan**. That is exactly
what the armed `document_revision_id` below buys you: the whole batch refuses, with zero writes,
rather than half-applying against a document that moved. See § "Do not edit the document while
an authoring session runs".

**And the apply-log is not a receipt** — § "The read-back law — a green apply is not a receipt".
This recipe reads **both** sides of it (what landed and what was refused) and then proves the
outcome by **reading the document again** on the second pass: the deletes it does not build are
the evidence, not the log line that said the first pass was clean.

**If what was interrupted was a reorganisation**, the ordering discipline that got you there —
insert before delete, preserve identity where you can — is § "Recipe: reorganise a document —
there is no move, so a reorder is delete-and-recreate", and it is not restated here. That
recipe is the **move**; this one is the **repair** for when it died in the middle.

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model import plain_text, walk
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    WriteClient,
    apply,
    compose,
    dry_run,
)

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

# WHAT THE DOCUMENT MUST NOT CONTAIN when the repair is finished. This is the whole input:
# an END STATE, not a list of ids. Ids describe the document the interrupted run was looking
# at, and that document is gone.
OBSOLETE = ["Step 1", "Step 2", "Step 3"]


def read_document():
    """RE-READ, every time. The plan resolves against a freshly parsed tree, and the repair
    runs more than once by design."""
    meta, blocks = reader.get_docx_content(doc_token)
    return meta.revision_id, Parser(Config()).parse_docx_tree(doc_token, blocks)


def still_present(root):
    """`{fragment: block_id}` for the obsolete blocks THE DOCUMENT STILL HAS. Everything the
    interrupted run already removed is simply absent from this map, which is exactly why the
    repair below is idempotent."""
    found = {}
    for node in walk(root):
        text = plain_text(node)
        for fragment in OBSOLETE:
            if fragment in text and getattr(node, "block_id", None):
                found[fragment] = node.block_id
    return found


def repair():
    """One pass. Returns the requests it built — an empty list means there was nothing left
    to do, and nothing was sent."""
    revision, root = read_document()
    present = still_present(root)
    requests = [DeleteRequest(target=AnchorById(block_id=block_id))
                for block_id in present.values()]
    if not requests:
        return [], None
    plan = dry_run(requests, root, document_revision_id=revision)
    return requests, apply(plan, writer, doc_token)


# --- 0. THE SAMPLE'S OWN SETUP — delete this step when you paste the recipe. ---
# It manufactures the state a rate limit leaves behind: the three obsolete blocks authored,
# then ONE of them already removed, as if the interrupted run got that far and stopped.
_revision, root = read_document()
if not still_present(root):
    seed = dry_run([InsertRequest(reference=Anchor(quote="Revenue grew 12.4%"),
                                  position=InsertPosition.AFTER,
                                  content=compose("\n\n".join(OBSOLETE)))], root)
    seeded = apply(seed, writer, doc_token).entries[0].created_block_ids
    interrupted = dry_run([DeleteRequest(target=AnchorById(block_id=seeded[0]))],
                          read_document()[1])
    apply(interrupted, writer, doc_token)

# --- 1. THE REPAIR. Two of the three are left, so two deletes are built and both apply.
first_requests, first_log = repair()
print(len(first_requests), "delete(s) built;", len(first_log.entries), "entries,",
      len(first_log.refusals), "refused")

# --- 2. RUN IT AGAIN — the property that makes this a repair rather than a retry. The
#        fresh read finds nothing obsolete, so ZERO requests are built and NOTHING is sent.
second_requests, second_log = repair()
assert second_requests == [] and second_log is None, second_requests
print("second pass:", len(second_requests), "requests — the document already converged")
```

**Why the second pass is the assertion and not a nicety.** A retry that is merely *safe* still
leaves you reading a log to find out what happened. A repair that **converges** can be run by
anything — a supervisor, a queue, a person who is not sure whether the first one finished — and
the answer is always the same document. That is the property the filter in step 2 buys, and it
is why it is worth the four lines.

### Recipe: change a document at the object level — no Markdown anywhere

The whole chain — read, find the block you mean, change it — **without a single Markdown
call**. This is the recipe to reach for when your user asked you to *change* something rather
than to *read* it, and it is the proof that going through Markdown is optional: read the tree,
take the block's own id off it, anchor by that id, preview, apply.

Three things it demonstrates that the projection cannot do. The block is found by walking the
tree, so you are matching the block's **own** text, not escaped-and-normalized text. The
target is the block's **own `block_id`**, so nothing has to be re-quoted and a repeated
sentence is not ambiguous. And the review anchors printed alongside it are simply *there* on
the node — the projection would have dropped them.

**This recipe is for ONE block you can already name. Changing many blocks at once, or landing
an edited copy of the whole document, is § "Recipe: update an existing document — change or
edit many blocks at once, without re-authoring it" below** — that path reconciles an edited
copy against the document it was made from and lands only what moved, so the comparison above
is a comparison of two right answers to two different questions, not a verdict on one.

**Do not edit the document while this runs** (the same rule as any other write). If another
user edits it concurrently, the engine **refuses** rather than guessing — that is by
design, not a malfunction to retry around — and recovery is a **re-download** and a
**re-plan**, which costs one read. See § "Do not edit the document while an authoring session
runs".

```python
from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    init_env,
    validate_download_url,
)
from larkdocio.model import plain_text, walk
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import AnchorById, EditRequest, WriteClient, apply, dry_run

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)
if doc_type == "wiki":                           # a wiki URL wraps the real docx token
    node = reader.get_wiki_node_info(doc_token)
    doc_type, doc_token = node.obj_type, node.obj_token

# 1. READ THE TREE. This is the whole choice: the tree hands you blocks you can point at.
document, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)


# 2. PICK THE BLOCK YOU MEAN and keep its OWN id. Everything the text would have lost is
#    still here on the node — its id, and the review anchors a reviewer left on it.
#    `walk` visits every block, including the cells inside a table and the blocks inside a
#    grid column; `plain_text` is that block's own words, @mentions included. Both are
#    shipped functions — do not hand-roll them, because the shapes they cover are exactly
#    the ones a hand-rolled version misses without saying so.
target = next(node for node in walk(root) if "Revenue grew" in plain_text(node))
print(target.block_id, target.comment_ids)

# 3. CHANGE IT BY THAT ID. Passing the document's revision arms the whole-document guard,
#    so a document that moved under the plan refuses instead of being overwritten.
requests = [EditRequest(anchor=AnchorById(block_id=target.block_id),
                        replacement="Revenue grew 15.0% in Q3.")]
plan = dry_run(requests, root, document_revision_id=document.revision_id)
print(plan.revision_guard)                # "active" | "unavailable" — never silently off
for entry in plan.refusals:               # a stale or unknown id refuses, naming the id
    print(entry.refusal.reason, entry.refusal.detail)
log = apply(plan, writer, document_id=doc_token)
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: leave a comment on a document, and take it back

You can put a comment on a document and remove it again. Both go through the same
`dry_run` → `apply` gate as every other write, and both are narrower than you might expect —
in ways worth reading **before** you build on them, because the API's answers here are
misleading in one direction and strict in the other.

**A comment attaches to the whole document. Only.** `CreateCommentRequest(text=...)` puts one
comment in the document's **comments panel**; it highlights no passage. There is no way to
anchor a comment to a block or a quote — and the sharp part is *how* there isn't: the endpoint
**accepts** an anchor, answers `code 0`, and creates a plain whole-document comment anyway. A
bogus block id is not an error either. So passing an anchoring field through would report an
anchored comment that was never created, and this library refuses instead:
`anchor_block_id=`, `quote=` or `is_whole=False` gets `comment-anchor-not-creatable` at **plan
time**, costing no API call, with the evidence and the alternatives in the refusal's `detail`.
If you want per-passage review, **read** the anchors humans already made — see § "Recipe: read
the comments on a document".

**A spreadsheet cannot be commented on at all.** `file_type="sheet"` is refused
(`comment-surface-unsupported`): Lark's enum for this endpoint is `[doc,docx]`, at every
granularity including a whole-file attempt. Comment **reading** on a spreadsheet does work —
`comments(token, file_type="sheet")` — and the refusal says so.

**It lands as your app, and you cannot make it look like a person.** The comment's author is
your application's own bot identity: a bare `open_id` with **no resolvable display name** (the
directory answers `41050` for it, and nothing in the payload marks it as an application rather
than a human). That is not a gap you can close with a scope, so the plan states it up front —
every resolved create carries a `comment-lands-as-the-app-bot` preview note — and the
apply-log reports the `author_id` it used.

**Removal is yours-only, and whole-thread or nothing.** There is no delete-a-comment endpoint;
a comment's content *is* its replies, so removal deletes every reply and the comment goes with
the last one. Lark permits that only for replies **your** app wrote, so `RemoveCommentRequest`
requires the `author_id` whose thread it must be — and the engine reads the live thread and
checks **every** reply before deleting **any**. A thread carrying someone else's reply is
refused with nothing deleted; a thread already gone is refused `not-found` rather than reported
as removed. You never get a half-deleted thread.

**`author_id` is not busywork:** the create's apply-log entry hands you exactly the id its
removal needs, which is the loop below.

**Concurrency, and the one way it differs here.** A comment carries no anchor, so unlike a body
edit there is no quote or block for a concurrent change to invalidate. But a comment op still
rides the **whole-batch** compare-and-swap like every other entry: if you pass
`document_revision_id=` to `dry_run` (or put a comment op in a batch alongside body edits, where
you certainly should), a document that changed under the plan **refuses** the entire batch with
zero writes — the engine refuses **rather than guess** whether the plan still describes the
document. So **do not edit the document** while a plan is being applied; on a busy document a
**re-download** and a **re-plan** is the cheap, correct recovery. The recipe below omits the
revision deliberately, because a comment-only batch has nothing positional to protect — the plan
then marks its guard `unavailable` and says why, rather than looking guarded. See § "Do not edit
the document while an authoring session runs".

```python
from larkdocio.common import get_write_credentials, init_env, validate_download_url
from larkdocio.comments import comments
from larkdocio.write import (
    CreateCommentRequest,
    RemoveCommentRequest,
    WriteClient,
    apply,
    dry_run,
)

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
writer = WriteClient(*get_write_credentials(), domain)

# 1. CREATE. A comment op points at the file, not at a block, so it needs no parsed tree —
#    pass None where a body-editing plan would pass one.
plan = dry_run([CreateCommentRequest(text="Second paragraph contradicts the summary.")], None)
for note in plan.entries[0].preview_notes:       # read the authorship disclosure BEFORE writing
    print(note["kind"], note["note"])
# allow_partial=True because the branch below IS the refusal handling; the default raises.
log = apply(plan, writer, document_id=doc_token, allow_partial=True)

entry = log.entries[0]
if entry.outcome == "refused":                   # anchored / spreadsheet / server refusal
    print(entry.refusal.reason, entry.refusal.detail)
else:
    comment_id = entry.comment_record["comment_id"]
    author_id = entry.comment_record["author_id"]   # your app's bot id — keep it

    # 2. VERIFY WHAT WAS MADE, not what came back: the create response does not report the
    #    scope at all, so read it back through the comments reader.
    made = comments(doc_token).by_id[comment_id]
    print(made.scope, made.quote)                # -> whole-document None

    # 3. TAKE IT BACK. Whole-thread or nothing; refused if anyone else replied.
    removal = apply(
        dry_run([RemoveCommentRequest(comment_id=comment_id, author_id=author_id)], None),
        writer,
        document_id=doc_token,
    )
    print(removal.entries[0].outcome, removal.entries[0].comment_record)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

## Task — put a picture, a file or a link into a document

### Recipe: put an image in a document (create, upload, bind)

A picture in a document body is **not** something you can author from Markdown: a `![](…)`
carries a path or a token, and the Markdown compiler holds **no bytes** and makes no network
call — so `compose()` refuses it. The picture is authored **out of band**, by one op, and that
op does three calls in a fixed order.

**Attaching a FILE rather than showing a picture is the next recipe** — § "Recipe: attach a
file to a document (the 📎 attachment card)". It is a different product, a different op and a
different trap; the placement rules stated here are the ones it uses.

**The order is not a preference — it is the only order that works.** Create the (empty) image
block first, upload the bytes **bound to that block's id**, then bind them with a
`replace_image` patch. Two traps are why this ships as one op instead of three exposed calls:

- **The block must exist before the upload.** An upload parented on the *document* answers
  success and hands back a real token — and then **no block will ever accept it**: the bind is
  refused with a relation mismatch, because the token carries a relation to whatever node it
  was uploaded against. That token cannot be repaired, and it cannot be deleted either.
- **The upload answering success is not a bind.** After a successful upload the block's image
  token is still **empty**. Nothing points at the bytes until the patch, and the only thing
  that proves the bind is a **fresh read of the block** — never a call's own echo. The op reads
  the block back and refuses if the token it finds is not the token it uploaded. (Related, and
  measured: the upload endpoint does **not** police the parent pairing — it accepted the image
  parent type against a *file* block. The bind is what enforces it.)

**Read this first: media accretes, and nothing purges it.** An uploaded media token is
**permanent** tenant residue — **no route in Lark's open API purges drive media, measured, not
assumed** (nine destructive spellings, fourteen sends, not one removed a token, the docx path
among them; the enumeration and its scope are in § "The disposables doctrine") — and
**deleting the document does not remove the media it carried**. If you are testing, upload the
smallest file that proves your point, and know that it stays. If a step *after* the create
fails, the empty image block is left in the document: nothing here issues an unrequested
delete, so the exception carries `orphan_block_id` and you decide.

**And a docx-bound media token is not an independently shareable object** — it **cannot be
permission-granted**, where a drive-uploaded file token can. The evidence, the reading (an
**inference**, not a measurement) and the route choice it implies are stated in full under
*Recipe: link a file from a sentence*; if the bytes must be shareable on their own, that recipe
is the one you want.

**And "it worked" means the hash matched.** The op downloads the token again and compares it to
the upload by **`sha256` and byte length** (`verify_round_trip` — the same check the attachment
leg uses). Bytes are hashed here, never inspected.

**REMOVING ONE — the block goes, the bytes stay. Two facts, and they are separate.** The image
**block** deletes through the ordinary write gate like any other block: build a
`DeleteRequest(target=AnchorById(block_id=authored.block_id))` and run it through `dry_run` →
`apply`. **Measured 2026-08-19**, and the verdict was taken from a **read-back** rather than
from the delete's own success code: the parent stopped listing the block and a direct read of
the id answered *not found*, with a **control** — the same call, the same parent, the same run,
against a text block — answering identically, so the result belongs to the block type and not
to the harness. Two things to know before you rely on it:

- **Use the id, not a quote.** An image carries no quotable text of its own, so a quote anchor
  is refused, with the id route named in the refusal. `put_image_in_document` hands you exactly
  that id; hold it.
- **Deleting the block reclaims nothing.** The upload is still permanent tenant residue, and
  putting the picture back somewhere else is a **new** upload and therefore a **second**
  permanent token. Blocks move for free; bytes accumulate. Budget an image-heavy
  reorganisation on that basis.
- **The delete's apply-log entry records the image it removed.** `removed_payload` carries
  the block's `image` object verbatim — the file `token` and the geometry — captured from the
  live block before the call, so the record names what was destroyed rather than only which
  id is gone. It is a reference record, not an undo button: see § "Recipe: reorganise a
  document" for what it does and does not let you do.

Board, whiteboard, embed (iframe / Base / Sheet) and synced blocks are a different matter: this
was measured on an **image** and on nothing else, so whether their delete works is
**unmeasured, not refuted** — they still refuse, and the refusal says so.

**WHERE IT LANDS — `parent_block_id` and `index`, and they are MEASURED.** Both media ops take
these two arguments, and by default the block is **appended to the end of the document**, which
is why an unplaced picture always turns up at the bottom:

- **`parent_block_id`** is the block the new block becomes a **child of**. It defaults to the
  document's **root** — and a docx document's root block id **is its document id**, so passing
  the document token is the same as passing nothing. Pass a *block* id instead (a list item, a
  quote, any block that owns children) and the picture lands **inside that block**, not at the
  top level.
- **`index`** is a **0-based position in that parent's ordered `children` list, and the new
  block is inserted BEFORE the child currently at that position.** So `index=0` puts it first,
  `index=1` puts it between the existing first and second children, and the default **`-1`
  appends** to the end.

**Measured, not derived.** A document was created, seeded with three paragraphs, and each case
read back from the parent's own `children` list — never from a create's answer, which names the
block that was made and says nothing about where it went. `index=1` landed at position 1;
`index=0` landed at position 0; the default landed last; and a **non-root** `parent_block_id`
put the block inside that parent while the root's own child list stayed exactly as it was. The
gate is `tests/test_live_docx_media_placement_gate.py` **in the source repository**. An `index` past the
end of the list is **unmeasured, not refuted**; of the parents, the root, a list item and — see
next — a **table cell** are the ones anybody has tried.

**A TABLE CELL IS A LEGAL `parent_block_id` — observed on a disposable
document.** Pass a table cell's own block id and the image is created **inside that cell**:
the bytes verify, and the block reads back carrying `parent_id == <the cell id>`. It earns a
recipe rather than a footnote because a table with one picture per row — a `Variant | Image`
table, say — keeps each picture beside its label, where a column of loose images and captions
drifts out of alignment.

**GETTING THE CELL ID — start from `created_block_ids`, then take ONE more step.** `apply()`
hands back exactly one created id for a table insert: **the table's**, never the cells'. The
cells are that block's own `children`, **row-major**, so a single `get_block` on the id you
were handed turns it into the id you need — `children[row * columns + column]`. The **second
python block below** is that route end to end, and it is a script you can paste.

> **⚠ NEVER find the table by re-reading the document and taking the last one.** It works in a
> sample and it fails on a document with many tables: a document carrying ten or eleven tables
> can end on any of the others, not on the table you just authored. Done that way on a document
> with many tables, **four images landed in the wrong table** and a person had to take them out
> by hand in the Lark client.
>
> **And the cost of a wrong parent is ASYMMETRIC for an image in a way it is not for text.** A
> mis-targeted paragraph costs you a delete. A mis-targeted image also carries an **upload**,
> and the upload is **permanent whatever later happens to the block** — the *media accretes,
> and nothing purges it* paragraph at the top of this recipe says it in full, and
> `larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA` carries the evidence. Whatever it
> costs you to tidy the document, the bytes stay. So the way to be right about an image's
> parent is to be right the **first** time, from an id `apply()` handed you — never from a
> position you guessed.

**DO NOT EDIT THE DOCUMENT while this runs**, and it matters as soon as you target anything
other than the root: the cell-targeting script below plans an insert against the tree it just
read, and a **concurrent** human edit moves the ground under it. The engine **refuses rather
than guessing** when the document changed under the plan, and the recovery is the usual two
cheap steps — **re-download** and **re-plan**. See § "Do not edit the document while an
authoring session runs".

**These two ops are the ONLY docx writes that position with a bare integer.** Everywhere else
in this guide a write says *where* with `Anchor` (a quote) or `AnchorById` (a block id) through
the `dry_run` → `Plan` → `apply` gate. These two are **out of band** — outside the plan gate
entirely — and they accept **neither**: passing an `Anchor` here is a `TypeError`, not a
refusal, because there is no parameter for it. The asymmetry is real and it is disclosed rather
than papered over; what you get back instead is the created **`block_id`**, and that id is
exactly what `AnchorById` wants for whatever you write next — see § "Recipe: anchor a follow-up
by a created block id".

**What is measured, and what is not.** The route above was measured end to end: the block is
created, the bytes bind to it, the block reads back carrying the token, and the bytes
re-download byte-identical. **Whether a client draws the picture on screen is `unmeasured`** —
no API call can observe it, and this library does not claim it. Only a **PNG** has been
uploaded, so other media kinds are unmeasured; alignment, scale and captions were never
measured as create-time fields and are not offered.

**`width` / `height` DO NOT SURVIVE THE BIND — and this is the part that will cost you.** The
create accepts them, and then step 3's `replace_image` **replaces the whole image property**,
geometry included. Read the block back and it carries dimensions you did not choose. **Two
observations, two different files, one conclusion:**

- **consumer-observed on one day, four images** — authored `width=560, height=560`; every one
  read back `width: 2560, height: 2560, scale: 1`.
- **captured, 2026-08-19, one image** — authored `width=120, height=60`; read back
  `width: 1, height: 1, scale: 1, align: 2` — and the file uploaded was a **1x1** PNG.

The numbers disagree because the **files** disagree. Both are consistent with the bind writing
the file's own pixel dimensions, and neither sample isolates that mechanism from any other rule
Lark might apply — so what this guide claims is what both show: **the values you pass are not
the values that come back**, and the property that comes back carries fields you never sent
(`scale`, `align`). Passing either dimension logs a warning saying exactly that.

**No measured route resizes the block afterwards.** Three patch shapes were tried on this route
on 2026-08-18 — each one a body sent to the docx single-block `PATCH` endpoint, which is the
engine's internal primitive and not a public method you can call — and all three were refused:

```text
PATCH …/documents/{doc}/blocks/{block}  {"replace_image": {"width": 300, "height": 560}}
    -> 99992402 field validation failed
PATCH …/documents/{doc}/blocks/{block}  {"update_image": {...}}   -> 1770001 invalid param
PATCH …/documents/{doc}/blocks/{block}  {"image": {...}}          -> 1770001 invalid param
```

`update_image_scale` and `update_block_property` were tried and refused too. That is what
**those spellings, on that route, on that date** answered; every other spelling is
**unmeasured, not refuted**, and this library ships no resize op.

**THE ONE LEVER THAT WORKS: DOWNSCALE THE IMAGE BYTES BEFORE YOU UPLOAD**, so the file's own
pixel size *is* the display size. Decide the size where you decide the file. Afterwards the
only repair is to delete the block and author a smaller file — the block **does** delete, by
its own id through the plan gate — but the re-upload mints a **second** permanent media token,
so the bytes accumulate either way.

**And the extension can lie while you do it.** Lark exports a whiteboard as **JPEG bytes under
a `.png` filename** (consumer-observed on one day, five exports), so a sizing step that
dispatches on the filename returns nothing on exactly the images most likely to be oversized.
Dispatch on the bytes' own header instead. That is a warning about **your** sizing step:
larkdocio never inspects, decodes or re-encodes image bytes, so nothing here is affected by it.

```python
from larkdocio.common import get_write_credentials, init_env, validate_download_url
from larkdocio.write import DocxMediaClient, WriteClient, put_image_in_document

init_env(".env")            # FIRST: every client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)

writer = WriteClient(*get_write_credentials(), domain)
media = DocxMediaClient.from_write_credentials(domain)   # an upload is a WRITE, always

# Your own picture is `Path("diagram.png").read_bytes()`; this recipe carries a 1x1 PNG
# literal so it runs exactly as printed.
image_bytes = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c49444154789c63606060000000040001f61738550000000049454e"
    "44ae426082"
)

# ONE call does all three: create the block -> upload bound to it -> PATCH replace_image,
# then re-read the block and hash-verify the bytes. This upload is permanent residue.
authored = put_image_in_document(
    client=writer,
    media=media,
    document_id=doc_token,
    data=image_bytes,
    name="diagram.png",
    # NO width= / height= HERE, ON PURPOSE. The create accepts them and the bind
    # overwrites them: authored 560x560 read back 2560x2560 (consumer-observed
    # on one day, four images); authored 120x60 read back 1x1 on a 1x1 PNG
    # (captured, 2026-08-19, one image). Passing either logs a warning. No measured
    # route resizes afterwards -- replace_image with size answers 99992402,
    # update_image and a bare image property answer 1770001; other spellings are
    # unmeasured, not refuted. THE ONE LEVER THAT WORKS: downscale the BYTES before
    # you upload, so the file's own pixel size IS the display size -- and dispatch on
    # the bytes' header, not the filename: Lark exports a whiteboard as JPEG named
    # `.png`, so a name-based check skips the biggest images.
    # WHERE IT GOES. parent_block_id defaults to the document root (whose block id IS the
    # document token); index is 0-based and inserts BEFORE the child at that position, so
    # index=1 means "second child". Omit index entirely and the picture is APPENDED.
    parent_block_id=doc_token,
    index=1,
)

# Both handles come back: the block id (to position or delete it later) and the file token
# (to prove what landed). `bytes_verified` is True when the round trip was hash-checked.
print(authored.block_id, authored.file_token)
print(authored.size, authored.sha256, authored.bytes_verified)

# READ BACK — the last step, always. `bytes_verified` says the bytes round-tripped; it does
# NOT say where the block sits. Only the PARENT'S OWN children list says that.
root = writer.get_block(doc_token, doc_token)
landed_at = list(root["children"]).index(authored.block_id)
print("landed at index", landed_at)          # -> 1, the position that was asked for
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt". This op's own read-back proves the **bytes bound**; the re-read of the parent's `children` above is the one that proves **placement**, which is the `order` row of that law's table.

**AN IMAGE INSIDE A TABLE CELL — the whole route, from the insert to the read-back.** This is a
second, self-contained script: it authors a `Variant | Image` table, takes the table's id out
of `created_block_ids`, reads that block's `children` to get the cell it wants, and puts the
picture in it. Note what it never does — it never re-reads the document looking for "a table".

```python
from larkdocio.common import (
    get_read_credentials, get_write_credentials, init_env, validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor, DocxMediaClient, InsertPosition, InsertRequest, NewBlock, WriteClient,
    apply, dry_run, put_image_in_document,
)

init_env(".env")            # FIRST: every client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)

reader = Client(*get_read_credentials(), domain)
writer = WriteClient(*get_write_credentials(), domain)
media = DocxMediaClient.from_write_credentials(domain)   # an upload is a WRITE, always

# Your own picture is `Path("variant-a.png").read_bytes()`; the 1x1 PNG literal keeps this
# script runnable exactly as printed. The upload it makes is permanent residue.
image_bytes = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c49444154789c63606060000000040001f61738550000000049454e"
    "44ae426082"
)

# 1. AUTHOR THE TABLE. A plan resolves against a freshly parsed tree, so read first.
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

COLUMNS = 2
table = NewBlock.table(rows=(("Variant", "Image"), ("Variant A", "")), header_row=True)
plan = dry_run(
    [InsertRequest(reference=Anchor(quote="Revenue grew 12.4%"),
                   position=InsertPosition.AFTER, content=(table,))],
    root,
)
log = apply(plan, writer, doc_token)

# READ BOTH SIDES OF THE LOG. A refusal is a typed skip, not an exception, so a caller that
# only counts successes learns nothing: if the insert was refused there is no table to fill.
for refusal in log.refusals:
    print("REFUSED:", refusal.reason, refusal.detail)
assert log.refusals == (), "the table was not created — nothing below can target its cells"

# 2. THE ID YOU WERE HANDED is the TABLE's — one id for the whole insert, cells included.
table_block_id, = log.entries[0].created_block_ids

# 3. THE ID YOU NEED is a CELL's, and it is one `get_block` away: the table block's own
#    `children`, ROW-MAJOR. Row 1 / column 1 is the empty "Image" cell authored above.
cells = list(writer.get_block(doc_token, table_block_id)["children"])
image_cell_id = cells[1 * COLUMNS + 1]

# 4. PUT THE PICTURE IN THE CELL. `parent_block_id` is the cell; nothing else changes.
shot = put_image_in_document(
    client=writer,
    media=media,
    document_id=doc_token,
    data=image_bytes,
    name="variant-a.png",
    parent_block_id=image_cell_id,
)
print(shot.block_id, shot.file_token, shot.bytes_verified)

# 5. READ BACK — and for a cell-parented image the read-back that matters is the PARENT.
#    `bytes_verified` says the bytes bound; only this says the picture is in the cell.
landed = writer.get_block(doc_token, shot.block_id)
print("parent_id:", landed["parent_id"], "== the cell:", landed["parent_id"] == image_cell_id)
```

### Recipe: attach a file to a document (the 📎 attachment card)

**The ask, in one line:** put a **file** in the document body — a PDF, a CSV, a zip — as the
📎 attachment card a reader clicks. The op is `put_file_in_document`, and it is the sibling of
the image op above: same three calls in the same fixed order, same permanent residue, same
placement arguments.

**READ THIS BEFORE YOU PASTE IT: an attachment card is a DIFFERENT PRODUCT from a link inside a
sentence.** This recipe puts a **block** in the body. If what you actually want is
*"for the full details, **open the attached file**"* — anchor text in a sentence, pointing at a
file — you want the **next** recipe, § "Recipe: link a file from a sentence", which uploads to
a **folder** and authors a `rich_paragraph` link anchor. Two more differences decide it for you:
a folder file **can be deleted**, and it **can be shared on its own**; the bytes this recipe
uploads are **permanent, unpurgeable** media residue and **cannot be permission-granted** (the
evidence and the reading are stated in full in that recipe).

**THE WRAPPER TRAP — a file create makes TWO blocks, and one of them is not the one you want.**
Creating `{"block_type": 23, "file": {}}` brings **two** blocks into existence, and the id the
API hands back is a **type-33 "view" wrapper** whose single child is the real type-23 file
block. That is measured on the wire, and it has consequences for the very next thing you do:

- **The wrapper cannot be patched.** Sending the `replace_file` bind to it is refused with a
  block/operation mismatch — an error that is undecodable if you only ever saw one id.
- **The wrapper cannot be created directly**, so you cannot sidestep it.
- **So the op returns the CHILD's id as `block_id`** — the id a later patch, delete or
  `AnchorById` has to address — and reports the wrapper separately as `wrapper_block_id`.
  Neither is hidden and neither is silently preferred.
- **The wrapper is what occupies the position you asked for.** `parent_block_id` /`index` place
  the **wrapper** in the parent's `children`; the file block is one level deeper, inside it. So
  the id you hold (`block_id`) is deliberately **not** the id you will find in the parent's
  child list — `wrapper_block_id` is. Measured: a non-root parent read back carrying the
  wrapper as its only child, and the file block's `parent_id` being the wrapper.

**Placement works exactly as it does for the image** — `parent_block_id` defaults to the
document root (whose block id is the document token) and `index` is 0-based, inserting **before**
the child at that position, with `-1` (the default) appending. The measurement, and what stays
unmeasured, is stated once in the recipe above.

**And the same two traps as the image**, for the same reasons: the block must exist **before**
the upload (an upload parented on the *document* mints a token no block will ever accept), and
the upload's own success **is not a bind** — the block's `file.token` stays empty until the
patch, and only a fresh read of the block proves it. The op does that read and refuses if what
it finds is not what it uploaded. One measured extra: a create carrying a `name` in the file
property is **refused** — the file's name comes from the upload, and this recipe passes it
there.

**Rendering is `unmeasured`.** No API call can observe what a client draws; what is proven is
that the block exists, carries the bytes, and hands them back byte-identical by `sha256` and
length.

```python
from larkdocio.common import get_write_credentials, init_env, validate_download_url
from larkdocio.write import DocxMediaClient, WriteClient, put_file_in_document

init_env(".env")            # FIRST: every client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)

writer = WriteClient(*get_write_credentials(), domain)
media = DocxMediaClient.from_write_credentials(domain)   # an upload is a WRITE, always

# Your own file is `Path("spec.csv").read_bytes()`; this recipe carries a few literal bytes
# so it runs exactly as printed.
file_bytes = b"section,owner\nintro,ada\n"

# ONE call does all of it: create (which makes the wrapper AND the file block) -> resolve and
# type-check the child -> upload bound to the CHILD -> PATCH replace_file -> re-read and
# hash-verify. This upload is permanent, unpurgeable residue.
attached = put_file_in_document(
    client=writer,
    media=media,
    document_id=doc_token,
    data=file_bytes,
    name="spec.csv",            # the name comes from the UPLOAD; a create carrying one is refused
    parent_block_id=doc_token,  # the document root — the default, spelled out
    index=0,                    # 0-based, inserted BEFORE the current first child
)

# BOTH ids come back, and they are not interchangeable. `block_id` is the type-23 FILE block —
# the one to patch, delete or anchor to. `wrapper_block_id` is the type-33 view wrapper the
# create actually answered, and it is what sits in the parent's children list.
print(attached.block_id, attached.wrapper_block_id)
print(attached.file_token, attached.size, attached.sha256, attached.bytes_verified)

# READ BACK — the last step, always. Two assertions, because two things were claimed: the
# bytes bound, and the card landed where it was asked to.
block = writer.get_block(doc_token, attached.block_id)
print("bound token:", block["file"]["token"])            # == attached.file_token

root = writer.get_block(doc_token, doc_token)
print("wrapper at index", list(root["children"]).index(attached.wrapper_block_id))   # -> 0
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt". Note which id each half of the read-back uses: the **file block** to prove the bind, the **wrapper** to prove the position.

### Recipe: link a file from a sentence

**The ask, in one line:** a sentence whose anchor text is *not* a URL, pointing at a file the
document does not — and sometimes cannot — display inline. An `.html`, for instance, is not
rendered inside a Lark document at all.

**It is TWO pieces, and neither alone serves it.** The file needs an **openable URL**, and the
sentence needs an **anchor on a run of text**:

1. `put_file_in_folder` uploads the bytes into a folder **you name** and hands back the file's
   own web URL. **The folder token is required** — this library picks no default destination,
   because a permanent write into a place you did not choose is a surprise. It does not create
   one for you either; if you need the folder to exist first, make it with `create_folder`
   (below) and pass the token it hands back. The URL is a **permalink**: the object's own address, asked for from Lark and
   never assembled from a token here. It is **not** a signed temporary link, and it **grants
   nobody access** — whoever clicks it still needs access to the file, which you arrange.
2. `NewBlock.rich_paragraph` authors the sentence out of `TextSpan` values; the span carrying
   `link_url` becomes the anchor. It goes through the ordinary `dry_run` → `Plan` → `apply`
   gate like every other write.

**The URL is sent verbatim** — pass it as Lark gave it to you. A **percent-encoded** spelling
is refused at construction, because the reader percent-*decodes* a link URL on the way back
out, so an encoded spelling would not survive the round trip through Markdown. The refusal
names the raw spelling to pass instead.

**A URL with whitespace in it cannot be an anchor at all, and the refusal says so rather than
sending you round a loop.** Both spellings are refused and for different reasons — the raw one
because a space ends the reader's `[anchor](url)` right there, the `%20` one because the reader
decodes it straight back to the raw one — so neither refusal advises the other's input. Two
things do work: link to a space-free URL for the same resource (a redirect, or a shortened
URL), or author the URL as plain text rather than as an anchor.

**Do not edit the document between the read and the apply.** The plan resolves against the
tree you just parsed, and the engine **refuses** rather than guessing if the document moved
under it: **re-download and re-plan** instead — concurrent editing is exactly what
`STALE_DOCUMENT` and `STALE_ANCHOR` exist to catch.

**A `[text](url)` in `compose()` is still refused**, and that is deliberate rather than an
oversight: the Markdown compiler creates unstyled runs, and the round-trip property against the
reader's own dialect is what that refusal protects. Author the anchor as the typed shape above.

**AND A TABLE CELL CARRIES THE ANCHOR TOO — this library offers it.** Author that cell as a
sequence of `TextSpan` instead of a string — the `metrics` table in the recipe above is exactly
that, and it goes out in the same plan as the sentence. The Markdown dialect composes one
directly too, which is the shape most callers want:

```markdown
| Metric | Owner | Detail |
|---|---|---|
| On-time delivery | Logistics | [Method note](https://example.com/method-note) |
```

Hand that to `compose()` and it **reads back as the same Markdown**, which is the whole point:
the labelled link survives the round trip through the cell. A labelled `[text](url)` **inside a
table cell is the one inline construct the dialect accepts**; everywhere else it still refuses,
and the typed `rich_paragraph` above is the route.

**SUPERSEDED, AND THE REASON IS PRESERVED.** This section used to carry the sentence *"AND A
TABLE CELL CANNOT CARRY THE ANCHOR AT ALL — larkdocio offers no route to one"*, on the ground
that `NewBlock.table(rows=…)` took a plain string per cell and there was nowhere to hang a
`TextSpan`. That was a true description of **this library's** surface — which is why a real
document could meet *"link at line 6: not expressible as creatable Lark docx content"* —
and it was never a statement about the platform. The platform has now been
measured: Lark **accepts and stores** a link-carrying run inside a docx table cell, on **both**
of the routes this library writes cells by, read back fresh rather than inferred from a
create's success code. So the absence was ours, and it is closed.

**WHAT IS OFFERED IS A LINK, AND ONLY A LINK.** Bold, italic, strikethrough, inline code,
underline and colour inside a cell are **not** available — they are not fields on a `TextSpan`,
so there is nothing to ask for, and the measurement above covered a link and nothing else.
Nothing here says the platform refuses them; nobody has asked it.

**Two more boundaries worth knowing, both unchanged.** The anchor is authored when the cell is
**created**: a later whole-cell patch (`EditRequest` + `TableLocator`) takes a plain `str` and
replaces the cell's content with plain text. And **merged cells** (colspan / rowspan) are a
different, unrelated thing and are still not authorable at all.

**The bare URL still works, and is still worth knowing.** Put the URL in the cell as plain text
and it comes back a live link, because the reader **auto-links a bare http / https URL**
everywhere it renders literal text (always on, no knob). Authored as
`| Example Item | https://example.com/example-item |`, that cell reads back as
`[https://example.com/example-item](https://example.com/example-item)`. What you lose is the
**label** — which is now exactly what you do not have to lose.

**The other product, named honestly.** If what you want is a 📎 **attachment card in the body**
rather than a link inside a sentence, that is `larkdocio.write.put_file_in_document` — a
different thing, and its bytes are **permanent, unpurgeable** media residue. A file uploaded
into a folder, by contrast, **can** be deleted.

**And the two routes differ in one more way that decides which you want: SHAREABILITY.** A
**docx-bound media token cannot be permission-granted** — both halves of the sharing recipe
that works elsewhere (the public-settings PATCH and the member POST on the drive permission
family) are refused on it with the same internal error, while **the same two calls on a
drive-uploaded file token succeed**. The reading is that the docx-bound token's access **rides
its parent document** — whoever can open the document can fetch its media, and nobody else can
be added to the media itself — and that reading ships **labelled as what it is: an inference
from two refusals, not a measurement of the rule.** No endpoint states it, and the refusals are
that family's internal error rather than a scope denial. **So if the file has to be
independently shareable, you want `put_file_in_folder` above** (route (a) — this recipe), not
the attachment card. Either way larkdocio ships **no sharing verb for a file object**: the
grant another user needs is arranged outside this library.

```python
from larkdocio.common import (
    get_read_credentials, get_write_credentials, init_env, validate_download_url,
)
from larkdocio.drive.files_write import DriveFilesWriteClient, put_file_in_folder
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor, InsertPosition, InsertRequest, NewBlock, TextSpan, WriteClient, apply, dry_run,
)

init_env(".env")            # FIRST: every client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, doc_token = validate_download_url(url)
folder_token = "YOURFOLDERTOKENHERE"      # REQUIRED — no default destination is picked

# 1. THE FILE. One call uploads it and asks Lark for its own web address, then downloads it
#    again and compares by digest. An upload is a WRITE, so it takes the write pair.
files = DriveFilesWriteClient.from_write_credentials(domain)
linked = put_file_in_folder(
    files=files,
    data=b"<!doctype html><title>an attached file</title>",
    name="details.html",
    folder_token=folder_token,
)
print(linked.url, linked.url_class)       # a permalink — not a signed link
print(linked.sha256, linked.bytes_verified)

# 2. THE SENTENCE. The anchor text is NOT the URL. Read the document first: a plan always
#    resolves against a freshly parsed tree.
reader = Client(*get_read_credentials(), domain)
docx, blocks = reader.get_docx_content(doc_token)
root = Parser(Config()).parse_docx_tree(doc_token, blocks)

writer = WriteClient(*get_write_credentials(), domain)
sentence = NewBlock.rich_paragraph((
    TextSpan("For the full details, "),
    TextSpan("open the attached file", link_url=linked.url),
))

# 3. THE SAME ANCHOR, INSIDE A TABLE CELL. A cell is a plain string OR a sequence of
#    TextSpan — the sequence is how the cell carries a labelled link instead of a bare URL.
metrics = NewBlock.table([
    ["Metric", "Owner", "Detail"],
    ["On-time delivery", "Logistics", (TextSpan("Method note", link_url=linked.url),)],
])

plan = dry_run(
    [InsertRequest(
        reference=Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",)),
        position=InsertPosition.AFTER,
        content=(sentence, metrics),
    )],
    root,
)
log = apply(plan, writer, document_id=doc_token)
sentence_block_id = log.entries[0].created_block_ids[0]
metrics_block_id = log.entries[0].created_block_ids[1]

# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**UPLOADING THE SAME NAME TWICE MAKES A SECOND FILE — this is the one thing to plan around
before you automate anything.** An upload is **not idempotent and there is no overwrite**: send
the same name and the same bytes into the same folder again and Lark answers `code:0` with a
**distinct file token**, and the folder then lists two children whose names are byte-identical.
No collision is reported, nothing is de-duplicated, and no warning is emitted. That was measured
rather than assumed, and so was the absence of a way out of it: five spellings of an extra
`upload_all` form field (`overwrite`, `duplicate_handling`, `conflict_strategy`, `mode`,
`upsert`), an `?overwrite=true` query string, and an `overwrite` key on `upload_prepare` were
**all accepted and all ignored** — every one minted another new token. So **if your automation
has ever re-run an upload, it has been creating a new file object every time**, and the folder
holds one per run.

**The library will not overwrite for you, and that is deliberate.** A "replace" that deleted
somebody's file on the way to writing yours would be destroying data as a convenience, with
nothing to consent to. What you get instead is the facts, and the decision:

```python
from larkdocio.common import get_write_credentials, init_env
from larkdocio.drive.client import DriveClient

init_env(".env")            # FIRST: every client resolves credentials from os.environ

domain = "larksuite.com"   # the API domain, NOT your tenant host — see "`domain=` is the Lark **API** domain"
folder_token = "YOURFOLDERTOKENHERE"      # the folder you are about to upload into

# The listing must be made with credentials that can SEE that folder. For a folder your write
# app owns, that is the write pair — this library never crosses the two pairs for you.
lookup = DriveClient(*get_write_credentials(), domain)
already = lookup.find_children_by_name(folder_token, "details.html")

print(already.found, already.tokens)
print(already.describe())     # one sentence, including whether the listing was complete
if already.found:
    print("skipping — or delete already.tokens yourself and then upload; your call")
```

Three fences on that check, all of them measured:

* **it is a check, not a lock.** Another writer can put the same name in the folder between the
  lookup and your upload, and nothing would refuse them. It narrows the race; it does not win it.
* **names only — identical name never means identical bytes.** Neither the folder listing nor the
  metadata query reports a **size** or a **digest**; what comes back is token, name, type, parent,
  url, owner and timestamps. If the question is really *are these the same bytes*, download the
  token and hash it (`verify_round_trip` is the one definition of that here).
* **an incomplete listing is not evidence of absence.** If the page budget fires, `already.complete`
  is `False` and `describe()` says so. Treat that as *unknown*, never as *not there*.

**A big file needs nothing extra from you — and here is exactly what changes.** Above
`SINGLE_SHOT_MAX_BYTES` the same `put_file_in_folder` call sends the bytes in blocks instead of
in one shot, and you get back the same `LinkedFile`, verified the same way. Three things are
worth knowing before you rely on it:

* **the block size is Lark's, asked for on every upload.** The library calls `upload_prepare`
  and partitions by the `block_size` / `block_num` that answer declares. It carries no size
  constant of its own for the partition, because that number is one tenant's answer on one day.
* **`SINGLE_SHOT_MAX_BYTES` is a LIBRARY POLICY, not a server limit** — it only decides
  *whether* to chunk, nobody has observed Lark enforcing it, and you can move it per call by
  passing `put_file_in_folder` a `chunk_above_bytes`. `linked.parts` tells you how many blocks the
  bytes actually went in (`1` = single shot). The optional Adler-32 `checksum` is deliberately
  not sent: it was omitted against Lark and the block was accepted, so sending it buys no
  guarantee this library can point to. The verdict is the same hash-verified read-back either
  way — `upload_finish` answering `code:0` is an acceptance, not a file.
* **a chunked upload that dies part-way leaves something you cannot see or clean up.** The parts
  that got through belong to a pending upload transaction with **no Drive object** — nothing to
  list, nothing to delete. **No cancel verb was found in the SDK's drive v1 surface and none was
  called: that is unmeasured, not "cannot"**, and the transaction's expiry is unmeasured too.
  `DriveFileChunkedUploadError` carries the `upload_id`, how many blocks went and how many were
  declared, so the leftover is at least named. Retrying starts a new upload.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

## Task — rows, columns and tables in a Base

### Recipe: the Base write handshake

**This recipe writes a Base's RECORDS — the rows.** Nothing on *this* path creates, renames,
converts or deletes a column, a table or a view, so plan around the schema this engine read.
Changing a Base's **shape** is a separate, separately-gated path with its own engine, its own
contracts and its own consent fence for anything destructive; see **Recipe: create, rename and
copy a Base (the structural handshake)** below, and read
`capabilities(full=True)["surfaces"]["base-schema-write"]` for the whole of it.

The handshake is the same one the document and spreadsheet engines use, with one difference
that matters: **read a table into a snapshot, edit the snapshot in memory, `dry_run` it into a
`Plan`, then `apply` that plan.** `apply()` takes a `Plan` and nothing else, and it takes
**both** a write client and a read client — because of the difference:

**There is no `If-Match` on the Base API, so the staleness guard is CLIENT-SIDE and says so.**
A record write that carries a `revision` or `last_modified_time` in its body is *accepted* and
the write *lands* — the key is ignored, and sending one would be a lie that reads like safety.
So larkdocio sends none. Instead the engine **reads the table's `revision`, compares it to the
value your plan was built on, and only then writes**. That closes the window between your plan
and your write. It does **not** close the last microsecond between the compare and the write,
and nothing here pretends otherwise. If the table moved, you get a `stale-base` refusal with
**zero writes for that table** — and the cure is always the same: **re-read, re-plan,
re-apply**. Other tables in the same plan are judged against their own anchors, because the
revision is per table.

**The guard is never silently off, and it says which state it is in.** Every table's plan carries `revision_guard`: `active` when the plan-time anchor is a usable (positive) revision, `unavailable` when it read back `0` or nothing — a freshly created Base reads `0`, and comparing `0` to `0` before a write cannot observe an advance, so pretending otherwise would be inert rather than safe. `revision_guard_detail` says which and why. The **value precondition** still enforces on every entry that has a `before`: the cells an update writes (or the record a delete removes) are re-read immediately before the batch, and drift refuses that entry alone. The guard **self-heals** — the next plan built on a positive anchor is `active` again.

**Success is not evidence that a write happened.** Some cells accept a write, answer success,
and store nothing — the table's revision does not move. So every call is followed by a second
revision read, and a call that did not move it is reported `dropped`, never `applied`. The
engine reports it and does **not** retry: re-sending would be a guess about why the value was
discarded. Read `entry.outcome` rather than assuming.

**Read the log through its accessors — the outcomes live on the log, not in the exception
type.** `stale`, `dropped`, `refused`, `indeterminate` and `not-attempted` are *outcomes on the
log*, and no exception type distinguishes them: a caller that only wraps the call in `try` and
looks at the class it caught still learns nothing about **which** entries did what. What did
change is that a log holding any of them **raises** `LarkApplyRefusedError` rather than
returning quietly (§ "Where refusals happen" — channel 3), so the log can no longer be
discarded by accident: read it off `err.log`, or pass `allow_partial=True` and read the return
value. Either way it is the same object. `ApplyLog` carries the readings you would
otherwise hand-roll — `applied`, `dropped`, `stale`, `refusals`, `indeterminate`,
`not_attempted`, `halted`, `of_table(table_id)` for one table out of a multi-table plan, and
`families` — a `{op: count}` breakdown of what **landed**, so `46 applied` reads as its parts
(45 `create_field` + 1 `delete_field`, or a record run's creates/updates/deletes); its keys are
the ops the entries carry, it counts over `applied` only, and its counts add up to exactly
`len(log.applied)` — so filtering `entries` by `outcome`
yourself is re-implementing a shipped accessor. Walk
`entries` itself when the **per-entry** detail is the point (it is 1:1 with the plan, in plan
order); use the accessors for every "did anything refuse?" question.

**One call per family per table — unless you say otherwise.** `dry_run(draft,
records_per_call=N)` chunks each family's batch call into calls of at most `N` records. The
default asserts **no** ceiling: this library has not probed the API's per-call record limit, so
it publishes none, and a bulk import is the caller who knows their own tenant's limit and sets
it. Either way the plan prices itself **before** any call: `plan.api_call_count` is how many
calls it will make, and each entry's `call_index` says which call that record rides in — a free,
offline audit of a batch you have not sent yet.

**CREATING A ROW IS `draft.add(...)`. THERE IS NO `draft.create`.** That is the name most people
guess — this library says `create_record`, `create_table`, `create_field`, `create_base`, so
`draft.create` reads like the obvious fourth — and it is an `AttributeError`, not a refusal
with a message. The draft carries exactly four verbs and they divide the work cleanly:

| On the draft | What it does | What it returns |
|---|---|---|
| **`.add(cells)`** | **create a row** — cells keyed by **field name**, e.g. `draft.add({"Text": "hello"})` | a **local** id (`new:1`, `new:2`, …) — a plan-time handle, never a Lark `record_id`, because nothing has been sent |
| `.set(record_id, field_name, value)` | change **one cell** of an existing row | the draft, so calls chain |
| `.update(record_id, cells)` | change **several cells** of one existing row | the draft |
| `.delete(record_id)` | remove an existing row | the draft |

Three things about `add` that the shape does not tell you. **A field name the table does not have
is refused in memory**, before a plan exists — the draft checks every key against the snapshot's
schema. **The local id is not a reservation**: it exists so the plan and the log can talk about a
row that has no server id yet, and the pairing to the real one is read off the applied log entry's
`created_record_id` (the sample below does exactly that). And **the cell values are write shapes,
not read shapes** — a Text cell takes the bare string `"hello"` and reads back as a segment array;
see § *What a Base cell TAKES and what it HANDS BACK*.

**What is refused before any call is made** — these cost nothing and the plan shows them:

| Refused at plan time | Why |
|----------------------|-----|
| a **computed or opaque** cell — a formula, a lookup, a stage, an auto-number, or any of the four created/modified time and user fields | the server owns the value. A write to one either fails or silently stores nothing, so it is refused where it is free to refuse |
| a value that is **not that field's write shape** | the write shape and the read shape are different objects for several field types, and a mismatched one answers success and stores nothing |

**A person or group cell is written by id — and the cell you get shows a full name chip.** The
value is `[{"id": "<open_id>"}]`, an `open_id`, the same `ou_…` handle a read hands back; in the
Lark UI that cell then renders the person's **full name chip**, exactly like one someone picked
by hand. **The display is unaffected** — that is what was observed in the product, and it is
worth saying before the limitation, which sounds far larger than it is.

**Four honest sources of an id.** (i) **Harvest** one — `read_base(url)` keeps the raw id on
the structured form for every person cell it already read. (ii) Supply one the **caller already
holds**. (iii) For the **account owner's own** id, `larkdocio.contacts.resolve_user` turns a
name into exactly one `open_id` or refuses in a typed way. (iv) **An EMAIL** —
`larkdocio.contacts.resolve_colleague(email=…)` turns one into exactly one `open_id`, or
refuses in the same typed way, on the `contact/v3/users/batch_get_id` family. Read (iv) with
the three sentences the library itself ships about it, quoted below and not paraphrased.
(`batch_get_user_names` on the document reader runs the *other* direction — ids you already
hold into names, for display.)

**Read the fourth source exactly this far, and no further.** These three sentences are the
library's own — `larkdocio.contacts.lookup.UNRESOLVED_IS_UNDIFFERENTIATED`, `MEASURED_REACH`
and `MOBILE_LEG_UNOBSERVED` — and the refusal object hands you the same text at the moment it
matters:

> Lark returned NO ID for this identifier. That means THE LOOKUP DID NOT RESOLVE IT. It does not mean no such person exists, and it does not mean the person exists but is out of this app's reach — because the endpoint answers with the IDENTICAL body for both: code 0, the identifier echoed back, and the user_id key OMITTED (not null, not empty). No field, no code and no envelope separates the two, so this refusal reports what was established and picks neither of what was not.

> REACH IS MEASURED, NOT GENERAL: exactly TWO addresses have been tried on this route, both on the tenant it was measured on, and both resolved. On those two identifiers this route reached further than either other route in this library — the enumerable department range and the directory search each miss another user this route resolved first try. Whether it answers for an arbitrary member of a tenant, or degrades on a larger tenant, is UNMEASURED.

> THE MOBILE LEG IS ACCEPTED BUT HAS NEVER BEEN OBSERVED RESOLVING A PERSON HERE. A mobiles[] request is accepted and answers code 0 with the same unresolved shape; the one number ever sent was synthetic, no real mobile was available to try, and guessing one is out of bounds. The leg is callable and it refuses cleanly. Nothing here promises it will resolve anybody.

And what it is, so the shape is not mistaken for a bigger one:

> This is a POINT QUERY: one identifier in, one open_id out. It is not a roster dump, a lookup table, a directory cache or a best-effort matcher, and it needs none of them — a point query has nothing to cache.

**What larkdocio still cannot do today, said plainly: turn another user's NAME into an id.** The
directory search behind `resolve_user` (`directory/v1/employees/search`) returns, on the tenant
it was measured against, **only the account owner** — another user the reverse lookup names
happily comes back from no query prefix at all. So a name is not a usable address here, and this
library will not invent one: no roster, no directory dump, no closest match. **This is a
statement about what larkdocio does, not a claim about what Lark permits**, and the reach was
measured on one tenant. **An ADDRESS is a different question, and that one now has a verb** —
`resolve_colleague`, source (iv) above, on `contact/v3/users/batch_get_id`: it resolved another
user's `open_id` from that second user's email address, reaching past the directory search
rather than being refused by anything. **The two are not the same route and neither stands in
for the other**: an email you already hold is now an address you can hand this library; another
user's *name* still is not. A clean name→id route stays deferred work with a written
mandate of its own — recorded once, in the dev repo, at `dev/downtime-queue.md` — rather than
something guessed at in this recipe.

**The round trip is asymmetric, deliberately.** A person cell round-trips through the **model**
and not through the **Markdown**: the structured read **keeps the raw id** on every person object
it read, so it can go straight back to the write encoder, while the Markdown projection emits the
**display name only** and drops the id — the reading form carries what a reader consented to
receive, not what a writer needs. Render a cell to Markdown, parse it back, and you are holding a
name; **a name is not an id**.

**A group-chat cell is the same shape with an easier id.** A `GroupChat` cell is written
`[{"id": "oc_…"}]`, and chat ids are obtainable in band: `GET /open-apis/im/v1/chats` answered
`code:0` here and listed the **one** chat the app could see. larkdocio ships **no chat lister**
— that is a different endpoint family with its own grant, and this surface does not buy one for
the sake of a disclosure — so the call is yours to make, and that "one chat" is what was
observed, not a statement about your tenant.

```python
from larkdocio.base.apply import apply, dry_run
from larkdocio.base.client import BaseReadClient
from larkdocio.base.model import ReadProof, snapshot_table
from larkdocio.base.table import assemble_table
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: both clients resolve credentials from os.environ

# A Base URL — its slug IS the app_token.
url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()          # the guard needs to READ
write = BaseWriteClient.from_write_credentials()       # the WRITE pair, no fallback

# --- 1. READ the table you are about to change --------------------------------
table = read.list_tables(app_token)[0]
table_id = table.table_id
fields = read.list_fields(app_token, table_id)
records = read.search_records(app_token, table_id)

# WHAT A CELL LOOKS LIKE ON THE WIRE, before anything renders it: search_records hands
# back records whose `fields` is keyed by FIELD NAME, and a Text cell is a SEGMENT ARRAY,
# never a string — `[{'text': 'row', 'type': 'text'}]`. An EMPTY cell is an ABSENT KEY.
first_cells = dict(records[0].fields or {})
print(first_cells)
print({name: value[0]["text"] for name, value in first_cells.items()
       if isinstance(value, list) and value and isinstance(value[0], dict)
       and "text" in value[0]})

# --- 2. SNAPSHOT it. The proof is a reading of the pages your read really saw:
# search_records walks to exhaustion, and this table fits in one page. A snapshot that
# cannot prove it reached the end is REFUSED rather than built, because a diff over a
# partial read would treat the rows it never saw as deletions.
page = {"items": records, "has_more": False, "page_token": None}
snapshot = snapshot_table(
    assemble_table(table_id=table_id, name=table.name, fields=fields, records=records),
    app_token=app_token,
    revision=table.revision,          # the ONLY compare-and-swap anchor a Base exposes
    read_proof=ReadProof.from_pages([page]),
)

# --- 3. EDIT IN MEMORY. Nothing has been sent yet. ----------------------------
# THE FOUR VERBS ON A DRAFT ARE `add`, `set`, `update` and `delete`. There is no
# `draft.create` — a reasonable guess from this library's op names, and it is an
# AttributeError. CREATING a row is `add`.
draft = snapshot.edit()

# CREATE a row. `add` takes the cells by FIELD NAME and returns a LOCAL id — a plan-time
# handle (`new:1`, `new:2`, …), never a Lark record id, because the server has not been
# asked yet. A field name the table does not have is refused right here, in memory.
new_row = draft.add({"Text": "created by larkdocio"})

# CHANGE a row that already exists. `set` is one cell; `update` is a mapping of them.
target = snapshot.record_ids[0]
draft.set(target, "Text", "written by larkdocio")

# --- 4. PREVIEW. dry_run costs ZERO API calls and returns the Plan apply takes.
# A bulk importer passes records_per_call=N here to chunk each family's batch call; the
# default is one call per family per table. Either way api_call_count and each entry's
# call_index below price the batch before you send it.
plan = dry_run(draft)
print(plan.to_json(indent=2))
for entry in plan.entries:
    if entry.refusal is not None:
        print("refused before any call:", entry.record_id, entry.refusal.reason)
    else:
        print("will", entry.op, entry.record_id, "in call", entry.call_index)
print("API calls this plan will make:", plan.api_call_count)

# --- 5. APPLY. Both clients, because the compare-and-swap is client-side. -----
# allow_partial=True because this recipe means to SHOW you the refusal readings below. Drop
# it — the default — and an entry that did not land raises LarkApplyRefusedError instead,
# carrying this same log on `err.log`. One spelling, on every plan-gated apply here.
log = apply(plan, client=write, read_client=read, allow_partial=True)

# The log is 1:1 with the plan, in plan order, whatever happened. Walk `entries` when the
# per-entry detail is the point — and read the ACCESSORS for everything else.
for entry in log.entries:
    print(entry.outcome, entry.record_id, "revision now", entry.revision, "call",
          entry.call_index)

# THE LOCAL ID BECOMES A REAL ONE, and the log is where you collect it: the entry whose
# `record_id` is the handle `add` gave you carries the server's id on `created_record_id`.
# Nothing rewrites the draft, so this is the ONLY place the pairing exists.
created = {entry.record_id: entry.created_record_id for entry in log.entries
           if entry.created_record_id}
print("new_row", new_row, "landed as", created.get(new_row))

if log.stale:
    # The table moved under the plan. ZERO writes went out for it — re-read and re-plan.
    print("stale:", log.stale[0].refusal.detail)
if log.dropped:
    # Accepted and discarded: the anchor did not move, so it did not happen.
    print("dropped:", log.dropped[0].refusal.detail)
if log.refusals:
    # Every refusal is a value on the log — this is how you find out. WITHOUT the opt-in
    # above, this same log would have arrived on LarkApplyRefusedError instead.
    print("refused:", len(log.refusals), "of", len(plan.entries))

print("landed:", len(log.applied), "of", len(plan.entries))
```

**Verify by reading back, not by trusting the return.** `read_base_markdown(url)` renders the
table again; the apply-log's `revision` is the anchor the next plan will be built on.

**Attaching a FILE is an out-of-band leg beside this handshake, not part of it — and an upload
is permanent.** An attachment cell is written from a *file token*, and
`larkdocio.base.media.BaseMediaClient` is how you get one: `upload(data=…, name=…,
parent_type=…, parent_node=…)` returns the token, and the cell is then written like any other
value in the plan above. Five things about it, none incidental:

- **`parent_type` is `bitable_file` or `bitable_image`** — a file column or an image column.
  Nothing else is sent; another value is refused before any call.
- **`parent_node` is the `app_token` of the Base the file is attached to.** Not a table id, not
  a record id. Point it at the wrong Base and the file attaches there, permanently.
- **The upload is permanent and nothing can undo it.** The file token survives the deletion of
  the table it was attached to and of the Base itself, and **no route in Lark's open API purges
  drive media — measured, not assumed** (nine destructive spellings, fourteen sends, not one
  removed a token; the enumeration and the scope it does not exceed are in § "The disposables
  doctrine"). larkdocio ships no purge verb and no "clean up my uploads"
  helper, because neither could work. Upload deliberately.
- **It reaches a different endpoint family** than every other operation on this surface — the
  drive family, the same one document images ride — so being granted the Base permissions says
  nothing about whether it will be permitted. The per-operation rows in **Permissions — what to
  ask for** carry that separately.
- **Verify by hash, not by status.** `download(file_token)` hands the bytes back in memory and
  `verify_round_trip(uploaded, downloaded)` compares `sha256` digests, raising if they differ.
  A success code proves an answer arrived; the digest proves the file did.

In code that is four lines beside the handshake above: build a
`BaseMediaClient.from_write_credentials()`, call `upload(data=…, name=…,
parent_type="bitable_file", parent_node=app_token)`, put the returned `.file_token` into the
snapshot edit as the cell's value, and pass the upload plus `download(file_token)` to
`verify_round_trip(...)` to prove the bytes survived.

**A read-back's `url` and `tmp_url` are credentials.** An attachment cell reads back with two
short-lived **signed** links beside the token. Treat them as you would a password: larkdocio
never logs one, never stores one and never renders one into Markdown, and
`larkdocio.base.media.scrub_attachment_cell(cell)` is the projection to use before a cell
reaches a log of your own.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: create, rename and copy a Base (the structural handshake)

Changing a Base's **shape** — making one, renaming it, copying it, adding and renaming tables —
goes through the same shape of gate as everything else here: **build the ops, `dry_run` them
into a plan, then apply that plan.** The whole schema surface ships that way: creating,
renaming and copying a Base; creating, renaming and deleting tables; creating, editing,
converting and deleting **columns**; and creating, updating and deleting **views**.

**Deleting IS available, it is taught HERE, and it costs a second deliberate act.**
`delete_field`, `delete_table` and `batch_delete_tables` all run through the same gate, and the
plan for one **enumerates what would be lost across the whole Base before anything happens** —
including the mirror of a two-way link column sitting in a table you never named, and the links
in other tables that a table delete would break — one-way links left dangling, two-way links
removed outright. Applying such a plan takes a **consent
token minted from that same plan** (`consent_to_destroy(plan)`); a plan applied without it raises
rather than deleting, and consent minted from one plan does not travel to another. A loss the
scan cannot fully enumerate is **refused**, not warned about. **And the Base ITSELF can now be
deleted too — `delete_base(app_token)`, taught at the end of this recipe.** Read the difference:
the three verbs above remove something *inside* a Base and are plan-gated because their loss can
be enumerated; `delete_base` removes the Base and takes **no** consent token, because a whole
Base's loss is every table, column, record and view it holds and nothing reads that at plan time.
It is the same whole-object call `delete_document` and `delete_spreadsheet` are. **Lark's route
trashes rather than purges** — that has not changed and it is why the call discloses it: a human
restores from the product's trash, no open-API verb purges anything here, and the Base's uploaded
attachment tokens survive it — **no route in Lark's open API purges drive media, measured, not
assumed**, with the enumeration and the scope it does not exceed in § "The disposables
doctrine".

**Declare the new Base's TIME ZONE while you are creating it.** `create_base(name,
folder_token=…, time_zone="Asia/Tokyo")` is the one place Lark accepts a zone, and every later read of that Base
reports it back. It matters because a Base date is stored as an **instant** — milliseconds since
the epoch — and not as a calendar date, so which day it is depends entirely on a zone: a Base
created without one reports **no zone at all**, any reader then has to assume one (this library
assumes `UTC` and says so on the read — `date_zone_assumed` / `date_zone_disclosure`), and a value
you wrote as local midnight can read back as the previous day. Passing the zone at create is what
makes a date-only value round-trip to the same calendar date.

**A Base you create — or copy — needs a folder, and a create that names none is refused.**
`create_base(name, folder_token=…)` and `copy_base(app_token, name, folder_token=…)` both
**require** the destination, spelled identically, and both refuse locally when it is missing or
empty — the rule in § "Where a new object goes — you name the destination, or nothing is
created". The reason is this surface's own: a Base with no folder came back with
`folder_token: ""`, meaning it belonged to the app that created it and sat in no folder any
person was browsing, so the `app_token` the create returned was the only way back to it — and
that space cannot be browsed at all. So the copy is filed at the moment it is made rather than
hunted for afterwards. What the folder key is measured to do, and what it is not: the copy
endpoint **checks** the folder — a folder-shaped token naming nothing, and a Drive object that is
not a folder, each come back `1254702 DriveNodeNotExist` with **no copy made** — and a copy given
a real folder is read back **inside that folder's own listing**. What was **not** measured is a
folder other than the app's own root, because that is the only one the measuring tenant could
address at the time; treat a different folder as **untested, not broken**, and check the copy's
parent yourself the first time. On this route the two cases DO come apart, and there are three
outcomes: a real folder this app has no permission on is refused `1254701 DriveNodePermNotAllow`
by this route with no copy made; a folder-shaped token naming nothing — or a Drive object that is
not a folder — is refused `1254702 DriveNodeNotExist` by this route with no copy made; and a real
folder the app can reach takes the copy. So a folder this app cannot reach is distinguishable
**here** from one that does not exist, `copy_base` relays whichever code arrived unedited, and
nothing here retries it or asks for a further permission. **So check the code you actually got.**
`1254701` from this route means the folder is real and this application is not allowed into it —
ask a workspace administrator to grant access to that folder; a grant is a Lark console action,
and nothing here widens, requests or escalates a scope. `1254702` from this route means the token
is wrong. The scope of the `1254701` half: measured 2026-08-18, one tenant, one app identity,
`tenant_access_token`, this route, one send with no retries, capture — in the dev repo —
`dev/ld493-caller-supplied-destination/captures/002-copy-app-unreachable-folder.json`. One send
shows the codes come apart **here** and is not a general mapping, so it says nothing about another
route, another tenant, another region or a `user_access_token`. **And which answer you get depends
on the route, so do not carry that lesson across:** `create_document`,
handed a real folder the account holder owns and the app was **not** granted, answers
`403 · 1770040 "no folder permission"` — an actionable denial, distinct from the
`1254702 DriveNodeNotExist` a folder that does not exist draws (measured 2026-08-17: one tenant,
one app identity, `tenant_access_token`, one honest send, capture — in the dev repo —
`dev/ld493-caller-supplied-destination/captures/001-ac4-denial-create-document.json`). Read the code you actually got rather than the one another route taught you. This copy
route's own unreachable-folder case was **parked** until that send was authorised, and the one
`copy_base` send was made on 2026-08-18 and answered `1254701`, which is why this paragraph now
reads the other way round. **MOVING an existing
Base is still a human action in the Lark UI** — this library ships no Base move, so a Base that
landed nowhere stays where it landed and the `app_token` you were handed is how you reach it.
**Trashing one is not**: `delete_base(app_token)` ships (below), so a Base you created for an
experiment is a Base you can clean up.

**AND A NEW BASE IS NOT EMPTY — IT ARRIVES WITH A TABLE LARK MADE, AND `list_tables(...)[0]`
IS THAT TABLE.** This is measured, on a disposable created for the purpose, and it is the single
most expensive assumption on this surface. A `create_base(...)` that reports `applied` hands back
a Base already holding **one table named `Table`**, carrying **four columns nobody asked for** —
`Text` (the primary one), `Single option` (a `SingleSelect`), `Date` (a `DateTime`) and
**`Attachment`** — and **ten blank rows**. The create's own reply names it: `default_table_id` on
the app object is that table's id, and it is the same id `list_tables(app_token)[0].table_id`
returns. Three consequences, all of them things people hit:

- **`list_tables(app_token)[0]` on a Base you just created is LARK'S table, never yours.** Every
  table you create is **appended after** it. Take the table you want **by name** — or keep the
  `table_id` the create handed you — and never by index.
- **The seeded table is telling you nothing about your data.** Its ten rows are blank and its
  columns are Lark's demo set; a read that reports ten rows on a Base you have written nothing to
  is reading it, not losing yours.
- **It is an ordinary table**, so `delete_table` removes it through the ordinary consent gate
  (step 5 below) once you have your own. Nothing here deletes it for you: a library that quietly
  destroyed a table it did not create would be the worse bug.

The count and the column list above are what one measured create produced. **If Lark changes its
seeding, the shape changes and this paragraph is what is stale** — read `list_fields` on that
table rather than trusting the four names, which is exactly what the recipe's step 0 prints.

**Two things about the delete portion below are worth reading before you paste it, because both
are things you cannot infer from the non-destructive calls above.**

1. **The three delete verbs live in their OWN module — `larkdocio.base.schema_ops_destructive` —
   while the consent token is minted by `larkdocio.base.schema_apply`.** Two modules, one gate.
   That split is deliberate (a destructive op is never one import away from a create), and it is
   the one thing here that has to be read rather than guessed: `consent_to_destroy` is **not** in
   `schema_ops_destructive`. Step 5 below carries both import lines.
2. **A DESTRUCTIVE `schema_dry_run` REQUIRES `read_client=`.** The keyword is optional in the
   signature and required in practice: the loss is enumerated by *reading* the whole Base, so
   `schema_dry_run([delete_field(...)])` with no read client **refuses with zero writes** rather
   than guessing at the blast radius. This is the same `read` client you already hold; pass it.
   (Every non-destructive plan above needs no read client at all, which is exactly why the
   destructive one surprises people.)

**Three things about this path are different, and all three are things you can be caught by.**

**1. There is no staleness guard here, and the plan says so on every entry.** A record write is
protected by the table's `revision` — larkdocio re-reads it and refuses if the table moved. A
*structural* op has no such anchor: `app.revision` exists, but it counts something the evidence
cannot pin down (the same probe sessions saw it move `0 → 1`, `0 → 14` and `0 → 5` for very
different amounts of work). A guard built on that would refuse valid plans, pass invalid ones,
and look exactly like the guard the record path really has — so there is none. Instead **every
structural op is verified by a read-back**: the renamed Base is re-read under its new name, a
created table has to appear in the table listing. Read `entry.outcome`: `applied` means the
server's own state showed the change, and `dropped` means the call was accepted and the
read-back did not show it. What this costs you is that **nothing will notice if something else
reshapes the Base between your plan and your apply** — so re-read before you plan, and keep
structural changes to a Base you control.

**2. Copying a Base is ASYNCHRONOUS — the only Base operation that is.** The copy answers with a
new `app_token` *before* the Base exists: `default_table_id` comes back empty, and reading the
new token immediately answers *"Bitable is copying, please try again later"*. That is not an
error and not something to retry by hand — larkdocio settles it with a bounded poll that stops
the moment the read answers, and reports how it settled. If the budget runs out you get
`applied-unverified`: **the copy is on your tenant**, it is simply not readable yet, and asking
again is the whole cure.

**3. A COPY IS THE ONLY WAY TO GET A COLUMN THE API WILL NOT CREATE.** Lark's field-creation
endpoint accepts a fixed list of column types, and **`Lookup`, `Stage` and `Email` are not on
it** — no larkdocio call, and no direct API call, can author one. What a copy does is
**server-side cloning**, so a Base that already has such a column produces a copy that also has
it, fully configured. If somebody asks *"how do I get a Lookup column?"*, this is the honest
answer: **build one in the product once, then copy that Base.** `without_content=True` gives you
the columns without the rows.

**A TABLE CAN LAND WITH ITS WHOLE COLUMN KIT, IN ONE CALL.** `create_table(app_token, name,
fields=[…])` takes the columns inline. **`batch_create_tables` does not** — its request shape
would carry a per-table kit and Lark accepts one, answers success, and then creates every table
**without** it, so larkdocio refuses that argument rather than sending something measured to do
nothing. Tables that need columns get one `create_table` each; the batch verb is for tables that
do not. Each column definition is a plain dict with the same four keys `create_field` takes:
`{"field_name": …, "field_type": …, "ui_type": …, "properties": {…}}`. **The kit rides exactly the
same gate a separate `create_field` rides** — the column-kind allow-list, the identity pair, and
the mandatory-`property` kinds — so a definition `create_field` would refuse is refused here too,
**before any call is made**, and it refuses the **whole** create rather than authoring a table
with one column silently missing. The refusal names the offending entry by **index and by
`field_name`**, so you know which one to fix. Two reasons to prefer this over a create followed by
N column calls: it is **one** HTTP call instead of `1 + N` (the plan prices it as one write), and
it does not touch the column-authoring route at all — so a table full of columns still lands if
that route is having a bad day. Adding a column to a table that already exists is still
`create_field`; this is only for the columns a table should be born with.

**Two things about that array are measured facts, and both will catch you.**

**1. THE ARRAY'S FIRST ENTRY BECOMES THE TABLE'S PRIMARY COLUMN.** A kitted create does not hand
you Lark's own default column *plus* your kit — the kit **is** the table's columns, and entry `0`
is the primary one, under the name you gave. So **order the array deliberately**: entry `0` is the
column your rows are keyed by, and it is the one column you cannot append later. (You can still
rename it afterwards with `update_field` — but **not with a bare name-only call if that column is
a `SingleSelect` or `MultiSelect`**, which this route authors: on a select column an update
carrying no option set empties the options and orphans every cell, so it is refused. Read the
column back with `list_fields` and pass its options through — ids and all — beside the new name,
as **Recipe: add a column, and change one's name** shows. Any other kind renames with the bare
call, exactly as you would expect.)

**2. THIS ROUTE AUTHORS FEWER KINDS THAN `create_field` DOES — AND THAT COLLIDES WITH FACT 1
ABOVE, SO READ THE TWO TOGETHER.** `Rating` and `Checkbox` are refused **before any call** with
the reason and the way forward: Lark answers *"Unsupported field type."* for them on a table
create and creates **nothing at all** — no table, no columns — so larkdocio will not send that
create. Both kinds are perfectly authorable; just not at birth. Measured landing here: `Text`,
`Number`, `DateTime`, `SingleSelect`, `Barcode`, `Currency`, `Progress`. A kind in neither list
was not measured on this route — if Lark refuses it you get its own typed answer, and nothing will
have been half-created.

**THE COLLISION, STATED ONCE AND PLAINLY, BECAUSE IT IS THE ONE THAT COSTS PEOPLE AN
AFTERNOON.** `create_table(fields=[…])` is **the only route that sets column order** — the whole
enumeration behind that is on the Base surface map, under the heading
**Column ORDER is settable — once, at table creation, and by no route measured afterward** —
**and it is the only route that will not author a `Checkbox` or a `Rating`.** Those two facts are
about the same call and they fight: a table that must have a `Checkbox` at position 3 cannot be
created that way. **Adding the column afterwards with `create_field` APPENDS it, and the position
you asked for is forfeited permanently** — no create-time position parameter, no update-time
position parameter and no move/reorder route places or moves a column afterward, and the append
itself was measured again for this paragraph rather than inherited.

**The route that works, and its cost.** Author the **orderable prefix** with `fields=[…]`, then
add the refused kinds with one `create_field` each, **in the display order you want them in** —
because **append order IS display order**. Measured here: a table created with the kit
`["ld473-title", "ld473-score", "ld473-when"]` read back in that order, then three columns
appended one call each — `ld473-open` (a `Checkbox`), `ld473-zeta`, `ld473-alpha`, deliberately
anti-alphabetical so *"the server sorted them"* and *"the server kept call order"* predict
different lists — read back as `[title, score, when, open, zeta, alpha]`: **call order, at the
end, moving nothing that was already there.** So the cost is exact and worth saying out loud:
**every column the create route refuses ends up after every column it accepts, and no
rearrangement afterwards is possible.** If the `Checkbox` must sit in the middle, the only
remaining lever is to put *fewer* columns in the kit — everything from the `Checkbox` rightwards
becomes an append, in the order you make the calls.

**`create_table` WILL NOT CREATE A TABLE WHOSE PRIMARY COLUMN YOU DID NOT NAME.** Passed neither
`primary_field_name=` nor `fields=[…]`, it **refuses before any call is made** — the op
constructor itself raises, channel 1 of the three above. What the refusal prevents: Lark names
that first column itself, in **your tenant's** locale (a Chinese-locale tenant reports `多行文本`,
i.e. "multi-line text"), so the column your rows are keyed by would arrive under a name you did
not choose and cannot predict — and every later write-by-name or schema diff would run through
it. **The one-line fix is `create_table(app_token, "Items", primary_field_name="Title")`**: one
`Text` primary column, under your name, on exactly the same single call. For a table that should
be born with more columns, pass the `fields` kit instead — its **first** entry is the primary one.
The two are **one mechanism** (`primary_field_name=` *is* a one-entry kit), which is why passing
**both** is refused as well: the kit's entry `0` already names that column, and this library will
not pick which of your two names you meant — not even when they agree, because a rule that turns
on string equality is a rule nobody can remember. **larkdocio does not invent a name for you
either.** `"Title"` chosen by the library would still be a name you did not pick, in a language
you happen to read — the same problem one locale down.

Renaming an **existing** table's primary column is unaffected and still an ordinary `update_field`
on the first column of that table (**Recipe: add a column, and change one's name**), one more entry
in the same kind of plan. Read a new table's columns back either way: the primary one is the column
the field listing returns first, and `is_primary` marks it. **That rename sentence is a route, not a
measurement** — it says which call renames the column, not that anyone watched it do so on your
tenant. And the locale *name* depends on your tenant's
own locale, so read it rather than assume it.

**A NEW TABLE'S DEFAULT *VIEW* CAN BE NAMED TOO — BUT IT COSTS A SECOND CALL, AND THE PAIR IS NOT
ATOMIC.** The rule above is about the primary *column*; a table's default *view* is a second name
Lark picks in your tenant's locale (`表格视图 1` on the tenant measured). Lark's create route
**rejects** a default-view name outright — the whole request fails `1254001 WrongRequestBody` and
**no table is created** — so larkdocio applies it one call later instead:
`create_table(app_token, "Items", primary_field_name="Title", default_view_name="Board")` creates
the table and then renames the single view it is born with, addressed by the view id the create's
own reply returns (never by comparing against Lark's locale name). **Omit the argument and nothing
changes: the create is the one call it always was, and the view keeps Lark's name.**

What happens when the second call fails is stated rather than smoothed over, because you are the
one holding the result: **the table exists**, its view keeps Lark's name, and you get
`TableCreatedViewNotNamed` — a `LarkAPIError` subclass carrying `table_id`, `view_id` (or
`view_id_learned=False` when the create's reply named no view), the name you asked for, and Lark's
own `code`/`msg` unedited. **Nothing is rolled back and nothing is retried.** larkdocio does not
delete the table you just created to undo a cosmetic failure — a delete can fail, race, or need a
permission the create did not, and a table with an unwanted view name is strictly better than a
table that is gone. Finishing the job is one call with the ids on the exception:
`update_view(app_token, table_id, view_id, view_name="Board")`. Through the plan gate the same
partial state is logged **applied-unverified**, never "nothing landed", and the name is confirmed
by reading the table's view list back — `code:0` alone is not evidence on that route.

**`batch_create_tables` CANNOT NAME A PRIMARY COLUMN, SO IT ASKS YOU TO SAY SO OUT LOUD.** The
batch route ignores a per-table `fields` array (above), so there is nothing larkdocio could send
to name those columns — every table it creates *will* arrive with Lark's locale-named default. A
silent default is exactly what the rule above exists to stop, so the batch verb refuses too, and
what clears it is an acknowledgement rather than a name:
`batch_create_tables(app_token, ["Notes", "Archive"], accept_locale_default_primary=True)`.
The alternative, when those columns should be named, is one
`create_table(app_token, name, primary_field_name=…)` per table — that route **does** honour the
name, and each is still a single call.

**AND A PLATFORM-SIDE CONDITION STOPS THE BATCH INSTEAD OF PAYING FOR IT N TIMES.** A schema
`apply()` normally treats a Lark refusal as being about *that* entry and carries on — the next
call's arguments are its own question. There is one shape where that is demonstrably wrong: when
**every call the plan has attempted** (at least two of them) refuses with **the same** Lark code
that this library's classification table does not know, on **table ids this run's own read client
listed a moment earlier**. Entries carrying different arguments do not all draw one identical
refusal on ids that were just there; the condition is on the platform side of the call, and it is
not in your plan. So the batch **halts** instead of spending one throttled write per entry on
something that cannot clear between them — the same reasoning that already halts a **missing
scope**. What you get: the refusals that did happen carry Lark's own `code` and `msg` plus a note
saying what the pattern means and that **nothing about your plan should be changed on that
evidence**; `log.halted` is `True`; and **every remaining entry is still in the log, in plan
order**, each one saying that nothing was sent for it, that its own arguments were never judged,
and that a re-run applies it normally once that route answers again. **Nothing is retried and
nothing is waited for** — a backoff would trade a fast, legible failure for a slow one. Two
things this deliberately does *not* do: it does not fire on a **single** unexplained refusal (one
error is not a pattern), and it does not fire on a plan that **landed** anything, because a plan
that is applying writes is not meeting a platform-wide condition. Recovery is the ordinary one:
re-`dry_run`, then apply the remainder.

**And a copy brings everything, including what larkdocio will never render.** A copied Base can
carry a Button column, which this library does not support and does not intend to. Nothing here
filters it, warns about it, or treats it as a problem — it is simply a column whose cells render
as their raw value. That is correct behaviour, not a gap.

```python
from larkdocio.base.client import BaseReadClient
from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES
# `consent_to_destroy` lives HERE, beside apply — NOT in schema_ops_destructive.
from larkdocio.base.schema_apply import consent_to_destroy, schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
# ...and the three DELETE verbs live in their own module, which nothing else imports.
from larkdocio.base.schema_ops_destructive import delete_field
from larkdocio.base.schema_ops_fields import create_field
from larkdocio.base.schema_plan import (
    batch_create_tables,
    copy_base,
    create_base,
    create_table,
    rename_base,
    rename_table,
)
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: both clients resolve credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

# A Drive folder token — the slug of a folder URL. Yours, not this placeholder.
FOLDER_TOKEN = "fldcnYOURFOLDERTOKEN"

read = BaseReadClient.from_read_credentials()      # every op is verified by a READ-BACK
schema = BaseSchemaClient.from_write_credentials()  # the WRITE pair, no fallback

# --- 0. THE HANDSHAKE ITSELF: MAKE A BASE. ------------------------------------
# `folder_token=` decides WHERE it lands, and therefore who can find it. It is REQUIRED:
# omit it (or pass an empty string) and the call refuses locally, before anything is sent,
# because a Base with no folder belongs to the app that made it and sits in a space no
# person can browse — see the rule in "Where a new object goes". Declare `time_zone=` in
# the same breath: it is the one place Lark accepts one, and a Base without it renders
# date-only cells in an assumed zone.
birth_plan = schema_dry_run([create_base("Inventory", folder_token=FOLDER_TOKEN,
                                        time_zone="Asia/Singapore")])
birth = schema_apply(birth_plan, client=schema, read_client=read)
new_app_token = birth.entries[0].created_app_token
print(birth.entries[0].outcome, new_app_token)

# WHAT YOU JUST MADE IS NOT EMPTY, and this is the line that shows it. Lark SEEDS a new
# Base with one table of its own — 4 columns you did not ask for (one of them an
# Attachment) and 10 blank rows — so `list_tables(new_app_token)[0]` is LARK'S table, not
# yours. Read the names; do not index by position.
for table in read.list_tables(new_app_token):
    print(table.table_id, table.name,
          [field.field_name for field in read.list_fields(new_app_token, table.table_id)])

# --- 1. BUILD the ops for a Base you ALREADY have. Nothing has been sent yet. --
# `read.list_tables(app_token)[0]` is safe HERE only because this Base is one you know the
# shape of. On a Base you just created it is the seeded table above.
first_table = read.list_tables(app_token)[0]
requests = [
    rename_base(app_token, "Inventory"),
    # The table AND its columns, in ONE call. Entry 0 becomes the table's PRIMARY column, so
    # its order is a decision. Every definition is gate-checked before anything is sent.
    create_table(app_token, "Items", fields=[
        {"field_name": "Item", "field_type": FIELD_PROPERTY_SHAPES["Text"].field_type,
         "ui_type": "Text"},
        {"field_name": "Unit price", "field_type": FIELD_PROPERTY_SHAPES["Currency"].field_type,
         "ui_type": "Currency", "properties": {"formatter": "0.00", "currency_code": "USD"}},
    ]),
    # A table whose ONLY column should be a named primary one: `primary_field_name=` IS a
    # one-entry Text kit, on the same one call. Without it (or a `fields` kit) the create is
    # REFUSED — see the paragraphs below on the locale-named default.
    create_table(app_token, "Locations", primary_field_name="Location"),
    # The batch verb takes NAMES ONLY — it accepts a `fields` array and ignores it, so
    # larkdocio refuses that argument rather than sending a no-op. It cannot name a primary
    # column at all, so it asks you to acknowledge Lark's locale-named default explicitly.
    batch_create_tables(app_token, ["Notes", "Archive"],
                        accept_locale_default_primary=True),
    rename_table(app_token, first_table.table_id, "Overview"),
]

# --- 2. PREVIEW. dry_run costs ZERO API calls and returns the plan apply takes.
plan = schema_dry_run(requests)
print(plan.to_json(indent=2))
for entry in plan.entries:
    if entry.refusal is not None:
        print("refused before any call:", entry.op, entry.refusal.reason)
    else:
        print("will", entry.op, "— verified by:", entry.read_back)
print("write calls:", plan.api_call_count, "· read calls to verify:", plan.read_calls)

# Every entry says, in writing, what it is NOT guarded by.
print(plan.entries[0].revision_guard_disclosure)

# --- 3. APPLY. Both clients, because verification is a read. -------------------
# allow_partial=True so the `dropped` reading below is reachable; without it a step that did
# not land raises LarkApplyRefusedError, carrying the same log on `err.log`.
log = schema_apply(plan, client=schema, read_client=read, allow_partial=True)
for entry in log.entries:
    print(entry.outcome, entry.op, entry.created_table_ids or "")
    if entry.outcome == "dropped":
        # Accepted and not observed: the read-back did not show it, so it did not happen.
        print("  not observed:", entry.refusal.detail)

# --- 4. COPY: the only route to a Lookup / Stage / Email column. --------------
# `without_content=True` clones the SCHEMA only — the columns without the rows.
# `folder_token=` files the copy as it is made, and is REQUIRED exactly as create_base's
# is — a copy makes a new top-level Base, so it cannot be left to land nowhere. A folder
# that does not exist — or a token that is not a folder — is refused 1254702 by this route
# and copies nothing; a REAL folder this app has no permission on is refused
# 1254701 DriveNodePermNotAllow by this route and copies nothing either. Check the code you
# got: 1254701 from this route means ask a workspace administrator for access to that folder
# (a grant is a Lark console action, never something this library asks for), while 1254702
# from this route means the token is wrong. Which code you get is route-dependent:
# create_document answers 403 / 1770040 "no folder permission" for a folder it cannot reach.
copy_plan = schema_dry_run([copy_base(app_token, "Inventory (template)",
                                      without_content=True,
                                      folder_token=FOLDER_TOKEN)])
copy_log = schema_apply(copy_plan, client=schema, read_client=read)

copied = copy_log.entries[0]
print(copied.outcome, "new Base:", copied.created_app_token)
# The copy is ASYNCHRONOUS, so the log records how it settled — not how long it slept.
print("settled:", copied.settle["status"], "after", copied.settle["attempts"], "read(s)")

if copied.outcome == "applied-unverified":
    # The copy IS on your tenant; it was not readable inside the budget. Ask again.
    print("not settled yet:", copied.refusal.detail)
else:
    # The clone carries the parent's columns — INCLUDING the ones no API can create.
    for table in read.list_tables(copied.created_app_token):
        for field in read.list_fields(copied.created_app_token, table.table_id):
            print(table.name, field.field_name, field.ui_type)

# --- 5. DELETE: the second deliberate act, and the keyword nobody guesses. -----
# A scratch column first, so this portion runs without risking one you care about.
schema_apply(schema_dry_run([
    create_field(app_token, first_table.table_id, "Scratch",
                 FIELD_PROPERTY_SHAPES["Text"].field_type, ui_type="Text"),
]), client=schema, read_client=read)
made = {field.field_name: field
        for field in read.list_fields(app_token, first_table.table_id)}["Scratch"]

# read_client= is REQUIRED for a DESTRUCTIVE plan: the loss is enumerated by READING the
# whole Base. Without it the entry refuses, with zero writes, rather than guessing.
loss_plan = schema_dry_run([delete_field(app_token, first_table.table_id, made.field_id)],
                           read_client=read)
losing = loss_plan.entries[0]
print("cells that would be destroyed:", losing.loss_preview["columns"][0]["cells_with_data"])
print("reads the scan spent:", loss_plan.read_calls, "· write calls:",
      loss_plan.api_call_count)

# Consent is minted from THIS plan and travels to no other; without it, apply RAISES.
gone = schema_apply(loss_plan, client=schema, read_client=read,
                    consent=consent_to_destroy(loss_plan))
print(gone.entries[0].outcome)      # 'applied' — the read-back proves the column is absent
print("Scratch" in {f.field_name for f in read.list_fields(app_token,
                                                           first_table.table_id)})   # False
# `delete_table(app_token, table_id)` and `batch_delete_tables(app_token, [ids])` are the
# same three lines from the same module; their loss preview counts tables and rows instead
# of cells, and names every link into them that the delete would break.
```

**What a clone carries is only part of the story — this is what it rewires, keeps and drops.**
Each item says how it is known, because "a copy is a copy" is exactly the assumption that breaks
a cache or a guard:

- **Internal references are rewired to the clone** (measured). A view filter on the template
  named its own table by id; the clone's copy of that filter came back naming the **clone's**
  table id in `filter_info.target_table`, not the template's. A clone is self-contained — it
  does not point home.
- **`field_id`s are preserved across the copy, while `table_id`s are new** (measured on the same
  clone). So a cache keyed on `field_id` **alone collides across Bases**: key it on the
  `(app_token, table_id, field_id)` triple, or two different columns in two different Bases will
  read as one.
- **A fresh clone reads `revision` 0**, so the first plan you build against it reports
  `revision_guard: unavailable` rather than `active` — comparing 0 to 0 before a write cannot
  observe an advance, and pretending otherwise would be inert rather than safe. Nothing is
  wrong; the per-entry **value precondition** still enforces, and the guard self-heals on the
  next plan built on a positive anchor. This is the general revision-0 rule, met on the very
  first thing you do with a copy.
- **Comments do not follow the copy** (measured **once**, on 2026-08-05: the template answered
  one thread on `file_type="bitable"`, the clone answered none). One measurement, reported as
  one — and deliberately **not** generalised to views, permissions or automations, none of which
  were probed here.

**Deleting a BASE is not on the PLAN-GATED path — it is its own call, and here it is.** Deleting a
table or a field IS on this path, behind the consent gate step 5 shows. Removing the **Base** is
`delete_base(app_token)`: one call on the same schema client, and **no plan and no consent
token**, because a whole Base's loss is every table, column, record and view it holds and nothing
enumerates that at plan time. It is the same whole-object call `delete_document` and
`delete_spreadsheet` are — not a third kind of gate — and it is what makes the disposables
doctrine followable on this surface at all.

Three things to read before you paste it, because none of them is inferable from the calls above:

1. **It is a TRASH, not an erasure**, and Lark's own route is why. A human restores the Base from
   the product's trash; no open-API verb purges anything here. Attachment and image tokens you
   uploaded into the Base survive it, and **no route in Lark's open API purges drive media —
   measured, not assumed** (the enumeration and its scope are in § "The disposables doctrine";
   read the scope, because the four probed tokens were sheets- and docx-parented, so for a
   Base-parented one those spellings are **unmeasured, not refuted**).
2. **The delete's own `code: 0` is acceptance, not proof — and the proof must come from the
   BITABLE side.** After a landed delete the Drive metadata route *still resolves* the token, with
   its title, owner and timestamps intact, so it cannot tell you the Base is gone. Ask for the
   Base again (`read.get_app(app_token)`) and the error you get back is the confirmation.
   `base_is_gone(exc)` is the one predicate to use: the delete of an already-trashed Base and a
   read of a trashed `app_token` report the same fact with two different codes, and it spans both.
   A **code-less** error is `False` — that is a failure below Lark, where whether the Base is gone
   is unknown and must not be assumed.
3. **A brand-new Base is not always addressable as a Drive file yet.** The delete is a Drive-file
   operation, and a Base the bitable API resolves happily can answer not-found-shaped codes to it
   for minutes — over twenty, observed — before the identical request lands. **Nothing is retried
   inside the call**: a retry loop in a destructive verb is not a policy this library gets to
   choose for you. If you provision Bases in a loop, keep every token and re-attempt the ones that
   did not land; *deleted, or recorded and swept* is the contract that survives a run that dies.

```python
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_client import BaseSchemaClient, base_is_gone
from larkdocio.common import init_env
from larkdocio.errors import LarkAPIError

init_env(".env")
schema = BaseSchemaClient.from_write_credentials(domain="larksuite.com")
read = BaseReadClient.from_read_credentials(domain="larksuite.com")

# WHERE the disposable goes — a folder YOU own or created, taken from its Drive link.
# It is required: a create that names no destination is refused before anything is sent.
FOLDER_TOKEN = "fldcnYOURFOLDERTOKEN"

# 1. CREATE the disposable, capturing the token in the SAME statement that made it: a token you
#    drop is a Base nothing can name, and therefore nothing can clean up. Declare the zone —
#    a Base created without one reports none on every later read, and a date-only cell then
#    renders in an assumed zone.
app = schema.create_app("larkdocio-scratch", FOLDER_TOKEN, time_zone="Asia/Singapore")
app_token = app.app_token
confirmed_gone = False
try:
    # 2. USE it. Your real work goes here — normally through schema_dry_run -> schema_apply
    #    above. NOTE WHAT IS ALREADY IN IT: this prints 1, not 0. A new Base arrives with a
    #    table Lark seeded (4 columns, 10 blank rows) and `tables[0]` is THAT table — so the
    #    tables you go on to create are appended after it. `app.default_table_id` names it.
    tables = read.list_tables(app_token)
    print(len(tables), tables[0].name, app.default_table_id)
finally:
    # 3. DELETE IT WHATEVER HAPPENED. In `finally`, so an exception above still cleans up.
    #    Forgive ONLY "already gone" — anything else is a real failure and must be seen.
    try:
        schema.delete_base(app_token)
    except LarkAPIError as exc:
        if not base_is_gone(exc):
            raise

# 4. CONFIRM it landed rather than assuming it from a code-0 reply. Ask the BITABLE side: the
#    Drive metadata route keeps answering for a trashed Base, so it cannot answer this.
try:
    read.get_app(app_token)
except LarkAPIError as exc:
    confirmed_gone = base_is_gone(exc)
print(confirmed_gone)                        # True

# And a SECOND delete does not lie about it: the route raises rather than reporting success,
# which is exactly the one outcome the `finally` above forgives.
try:
    schema.delete_base(app_token)
except LarkAPIError as exc:
    print("already gone:", base_is_gone(exc))         # already gone: True
```

**And `is_advanced` is not on this path either**: turning on advanced permissions is a **Base-owner
action in the product**; the API refuses it outright, so asking for another permission will not
help and larkdocio refuses the argument before sending anything.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: add a column, and change one's name

Adding a column is one call behind the same plan gate everything else rides, and the only part
that is not obvious is **the type**. A Lark column has *two* type coordinates — the integer
storage type (`field_type`) and the picker name (`ui_type`) — and they are not independent:
`Number`, `Currency`, `Progress` and `Rating` are all storage type `2`, while `Text`, `Email`
and `Barcode` are all storage type `1`.

**`FIELD_PROPERTY_SHAPES[ui_type].field_type` is where that pairing lives — read it
before you guess a type int.** The same row tells you which `property` keys the kind takes (`.keys`) and
whether a `property` is mandatory (`.required`): a `SingleSelect` may carry `options`, a
`SingleLink` must be told which `table_id` it points at, and a `Formula` cannot be created
without an expression. A pair no shipped registry carries — `field_type=1` with
`ui_type="Checkbox"`, say — is refused **locally, before any client is touched**.

**Three verbs, and they are not interchangeable.** `create_field` makes a column.
`update_field` changes a column's **name or property — never its kind**. `convert_field`
changes the kind, and only for the pairs a capture proves; everything else is refused at plan
time. If your conversion is refused, you want the guided migration below
(**Recipe: change a column's type**) rather than a hand-rolled sequence.

Every field op is verified by a **read-back**: the column must list with the identity that was
asked for *and* `table.revision` must have moved. A `code:0` with an unmoved anchor is reported
as `dropped`, not `applied`.

**A SELECT column's OPTIONS are the one place `update_field` can destroy data, and it is fenced.**
A select cell stores the option's **`id`**, not its name, and `PUT .../fields/{f}` **replaces** the
whole option set, matching on that id. So an update whose options do not carry their ids makes the
server mint fresh ones, and every cell pointing at an old id is orphaned — measured on a throwaway
Base with six populated cells: ids on the wire kept **6 of 6** cells (`SingleSelect` and
`MultiSelect` alike), ids missing left **0 of 6**, even when the names and colours were
byte-identical; a body with no options at all emptied the option set outright and also left 0 of 6.
Two update shapes are therefore **refused locally, before anything is sent**:

* an update of a select column that carries **no option set** at all — including a bare rename,
  which on this kind is not a rename but a wipe. Rename a select column by passing its options
  through beside the new name, as the recipe below does;
* an update whose options carry **no `id` on any of them**. An option with no id *beside*
  id-carrying ones is an **addition** and is allowed.

Neither refusal asks **whether the column holds data**: that is not knowable from the request's
shape, and an unknown blast radius is not a safe one — so an **empty** select column is refused on
the same shape and pays the same price.

**REMOVING an option is a third destructive shape, and it IS shipped — behind consent.** A body
that carries every surviving option *with its id* and simply **omits** one passes both refusals
above, and it destroys the cells that hold the dropped option: measured on a throwaway Base, a
`SingleSelect` shrink emptied the **2 of 3** records holding the dropped option and left the
survivor untouched, and the same shape on a `MultiSelect` stripped the dropped value from each
cell it was in (`[B, C]` → `[B]`) and **emptied** the cell that held it alone. The two controls in
that run destroyed nothing: **renaming** an option while keeping every id kept every cell (the cell
follows the id, so it reads back under the new name), and dropping an option **no record holds**
left every cell byte-identical.

So an options-carrying update of a select column is planned like a `delete_field`:

* `schema_dry_run` needs **`read_client=`** — the loss is *which records hold a dropped option*,
  and that needs a read. Without it the entry **refuses**, with nothing sent;
* the entry's **`loss_preview`** names every record that loses a value, what its cell keeps, and
  whether the cell empties. A shrink that destroys nothing carries a preview that is **explicitly
  empty and measured** (`destroys: false`) — never `None` — and applies with no token;
* a shrink that **does** destroy cells needs **`consent=consent_to_destroy(plan)`**, the same
  token, the same helper and the same refusal vocabulary a column delete needs. One consent
  doctrine, one blast radius;
* **the safe ordering is REMAP THEN SHRINK** — move the records off the option first (a records
  update onto an option you keep), then send the shrunken set, and the shrink destroys nothing.
  Shrink-first-remap-after is what loses the values before the remap has anything to address.

There is one route this fence cannot reach: `BaseSchemaClient.update_field` called **directly**,
outside a plan, is a plain single API call like `BaseSchemaClient.delete_field` beside it. The
shape refusals still bite there; the consent fence lives at the plan seam, so plan your option
edits.

**Which is why colours belong at CREATE time.** `option.color` is an int the server stores
verbatim — **21 ints spread across `0`–`53`** (`0, 1, 2, 3, 4, 5, 8, 11, 14, 17, 20, 22, 24, 28, 33, 36, 40, 43, 46, 49, 53`)
were sent and **every one read back unchanged**, and a separate probe accepted **`54`** and
stored it, while `-1`, `99` and `1000` were each refused `99992402 field validation failed`.
The ints between the ones listed were **not probed**, so that is a measured spread rather than
a claim about a whole range. Set them in `create_field` (or in a `create_table`
fields kit), where the column has no cells to orphan yet; recolouring afterwards means sending the
whole option set back with every id intact. **What shade an int paints is not something this
library reads**, so it does not name one for you — the API returns the integer it was given. Set a
column's colours once, look at the result, and write down what you see.

```python
from larkdocio.base.client import BaseReadClient
from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.schema_ops_fields import create_field, update_field, convert_field
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: both clients resolve credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()       # every field op is verified by a READ-BACK
schema = BaseSchemaClient.from_write_credentials()  # the WRITE pair, no fallback
tables = read.list_tables(app_token)
table_id, target_table_id = tables[0].table_id, tables[1].table_id

# --- THE PAIRING, LOOKED UP RATHER THAN GUESSED ------------------------------
shape = FIELD_PROPERTY_SHAPES["SingleSelect"]
print(shape.field_type, shape.keys)        # 3 ('options',)  ← the int, and what it accepts

# --- 1. TWO COLUMNS: a select with its options, and a link with its target ---
log = schema_apply(schema_dry_run([
    create_field(app_token, table_id, "Status",
                 FIELD_PROPERTY_SHAPES["SingleSelect"].field_type,
                 ui_type="SingleSelect",
                 properties={"options": [{"name": "Todo"}, {"name": "Done"}]}),
    # A link column is USELESS without its target: table_id is the table it points at.
    create_field(app_token, table_id, "Owner",
                 FIELD_PROPERTY_SHAPES["SingleLink"].field_type,
                 ui_type="SingleLink",
                 properties={"table_id": target_table_id}),
]), client=schema, read_client=read)
print([entry.outcome for entry in log.entries])          # ['applied', 'applied']

# The create does not hand back a field_id — re-list and find it by name, which is also
# how you confirm the property really persisted.
fields = {field.field_name: field for field in read.list_fields(app_token, table_id)}
status = fields["Status"]
print(status.field_id, status.type, status.ui_type)

# --- 2. RENAME — and a SELECT column's options RIDE ALONG, IDS AND ALL. ------
# `PUT .../fields/{f}` REPLACES the option set and matches on each option's `id`, so an
# update that does not name the ids re-mints them and every cell pointing at an old one
# is orphaned. Pass the options you just read back through unchanged, beside whatever you
# are changing. An update of a select column that cannot name its option ids is refused
# locally, before anything is sent.
#
# An options-carrying select update needs `read_client=` at DRY RUN too: dropping an option
# destroys the cells that hold it, so the plan reads the table and enumerates that loss
# before it will let the write through. Pass every option through, as here, and the
# preview comes back measured EMPTY (`destroys: false`) and applies with no consent token.
options = [{"id": option.id, "name": option.name, "color": option.color}
           for option in status.property.options]
plan = schema_dry_run([
    update_field(app_token, table_id, status.field_id, "Workflow status",
                 FIELD_PROPERTY_SHAPES["SingleSelect"].field_type, ui_type="SingleSelect",
                 properties={"options": options}),
], read_client=read)
print(plan.entries[0].loss_preview["destroys"],            # False — nothing is dropped
      plan.entries[0].loss_preview["records_affected"])    # 0, read from the table itself
renamed = schema_apply(plan, client=schema, read_client=read)
print(renamed.entries[0].outcome)

# --- 3. CONVERT — previewed only. The plan states what happens to the CELLS. --
# schema_dry_run costs zero API calls, so this is a free question. An unlisted pair is
# refused right here; a listed one tells you its cell effect before you send anything.
text = fields["Text"]
preview = schema_dry_run([
    convert_field(app_token, table_id, text.field_id, text.field_name, text.type,
                  from_ui_type="Text", to_ui_type="Barcode"),
])
print(preview.entries[0].conversion["cell_effect"])

# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(renamed.applied), "applied,", len(renamed.refusals), "refused")
for entry in renamed.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: change a column's type (the guided migration — do NOT hand-roll this)

**larkdocio will not convert your column, and it will not leave you to rebuild it unsupervised
either.** `convert_field` refuses `Text → Number` — and every other pair no capture covers —
because a conversion rewrites every value in the column server-side, permanently, and nobody has
watched Lark do it. That refusal stands. What used to happen next is the problem this recipe
solves: told no, people hand-write

```
create Estimate__new (Number) → copy 11 values → DELETE Estimate → rename Estimate__new
```

The **delete** in the middle is fenced beautifully — a loss preview, a cell count, a consent
token bound to that plan. **The sequence is not fenced at all.** Nothing in the library knows
that deleting `Estimate` is safe *only if* the copy round-tripped first, so a wrong order, a
process that dies between two steps, or a value the new column could not hold strands data with
every guard still green. That is materially more dangerous than the conversion that was
declined.

`plan_field_migration` / `apply_field_migration` make the **whole sequence** the unit: one call,
one consent, one log.

**What you get, and what you are not promised.**

- **The preview covers all five steps and costs zero writes.** The planner does not even accept
  a write client. The destructive step carries the same loss preview a `delete_field` plan
  carries — same cell count, same enumeration.
- **Consent is the same primitive you already use**, minted from this plan:
  `consent_to_destroy(plan)`. Applied without it, the migration raises before a single call.
- **The delete cannot be reached on an unverified copy.** Every value is read back out of the
  staging column and compared to what was sent; a mismatch, or a count that does not agree,
  halts with a typed refusal and your old column still standing.
- **A value the new column cannot hold refuses the WHOLE migration at plan time**, naming the
  records and the values, before anything is sent. There is no skip mode and no blank mode:
  guessing on your behalf would mean guessing about every value in the column. This is the
  common first answer for `Text → Number` over a column that holds prose, and it is the answer
  you want.
- **It cannot be atomic.** Several HTTP calls, two engines, no transaction to wrap them in. What
  you get instead is an account — one log entry per step, in plan order, every one ending in a
  typed disposition, the rest logged `not-attempted` after a halt — and a halted run's
  `log.halt["recovery"]` naming which columns exist, where the values are, and what a recovery
  would do. Because the delete is gated on the verification, **a partial run leaves you with an
  extra column, never a missing one.**
- **It is not a conversion.** A conversion is a server-side rewrite nobody observed; this is a
  client-side rebuild in which every value passes through your own process.

The runnable example below does both arms against the same Base: the honest **plan-time refusal**
of a `Text → Number` ask over prose, and then a migration whose values the target really can
hold, end to end.

```python
from larkdocio.base.client import BaseReadClient
from larkdocio.base.field_migration import (
    UntranscodableValueError,
    apply_field_migration,
    plan_field_migration,
)
from larkdocio.base.schema_apply import consent_to_destroy
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: every client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()       # every step is verified by a READ-BACK
schema = BaseSchemaClient.from_write_credentials()  # authors and removes the columns
write = BaseWriteClient.from_write_credentials()    # copies the values

table = read.list_tables(app_token)[1]

# --- ARM 1: the honest refusal. A column of prose is not a column of numbers. ---
try:
    plan_field_migration(read, app_token, table.table_id,
                         field_name="Text 2", to_field_type=2, to_ui_type="Number")
except UntranscodableValueError as refusal:
    # Names the offending records and values. NOTHING was sent and nothing was destroyed.
    print("refused at plan time:", str(refusal)[:120], "...")

# --- ARM 2: PREVIEW the whole sequence. ZERO writes. ---------------------------
plan = plan_field_migration(read, app_token, table.table_id,
                            field_name="Text 2", to_field_type=13, to_ui_type="Phone")
print(plan.to_json(indent=2)[:0] or "", end="")     # the whole preview, if you want it
for step in plan.steps:
    print(f"{step.index}. {step.kind} — {step.describe} ({step.writes} write call(s))")
print("values to copy:", len(plan.values), "· empty cells skipped:", len(plan.skipped_empty))
print("staging column:", plan.staging_name)

# The destructive step's preview is the SAME one a delete_field plan carries.
print("cells that would be destroyed:",
      plan.loss_preview["columns"][0]["cells_with_data"])
print(plan.to_dict()["not_atomic"])

# --- 3. CONSENT, minted from THIS plan, and APPLY. -----------------------------
log = apply_field_migration(plan, schema_client=schema, client=write, read_client=read,
                            consent=consent_to_destroy(plan))
for entry in log.entries:
    print(entry.outcome, entry.op)
    if entry.refusal is not None:
        print("   ", entry.refusal.reason)

if log.halt is not None:
    # The migration is NOT atomic, so a halt tells you where you are and what to do next.
    recovery = log.halt["recovery"]
    print("halted at:", recovery["halted_at"])
    print("your data:", recovery["what_a_recovery_would_do"])

names = [f.field_name for f in read.list_fields(app_token, table.table_id)]
print("columns now:", names)   # the OLD name, the NEW kind, and no staging column left
```

**Two things this recipe deliberately does not do.** It does not migrate more than one column —
one column per migration, each with its own consent, because one consent covering three deletes
is one consent nobody read three times. And it does not touch `convert_field`: the pair table is
unchanged, the migration is not registered as a pair, and the refusal you get for an uncaptured
conversion is exactly the refusal you got before.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: create, configure and delete a view — hidden columns ARE settable; grouping and a saved sort are NOT

**Read this before you plan a kanban builder.** `create_view` makes a view and the view arrives
**unconfigured** — it takes a name and a type and nothing else. Four things are settable
afterwards through this library, each verified by
**read-back**: its **name**, its **filter** (see **Recipe: filter a Base two ways**), its
**hierarchy field** (see **Recipe: build and read a row tree**) and the columns it **hides**.
Everything else that makes a view *useful* you must open the product to set. Of the things that
do not move —

* **grouping** — a `property.group_info` PATCH answers `code:0` and the view reads back with
  `property: null`. It is accepted and not stored;
* **a saved sort** — accepted and **not stored**, measured across **eight** spellings:
  `property.sort_info` as `[{field_id, desc}]`, as `[{field_id, order:"desc"}]`, as
  `[{field_name, desc}]` (the search route's own spelling); `sort`; `sorts`; `sort_infos`;
  `sort_info` as an **object** rather than an array; and `sort_info` **+ an `auto_sort` flag** —
  every one answers `code:0` and every one reads back with `property` unchanged, indistinguishable
  from the **invented-key control** (`property.zzz_ld417_control`), in the same run where
  `property.filter_info` — the **positive control** — stored and read back its full
  `conditions`/`conjunction` object. This is the **saved, view-level** sort; `records/search`'s own
  `sort` array is a **different route and it works** — it orders one call's rows, it does not
  persist on the view;
* **a gantt view's start/end date binding** — no route was ever established;

— **none of those three changes anything this library can observe**, so it exposes **no
parameter for any of them**. The rule is unchanged and it is the whole reason: **offering a knob
whose effect cannot be observed would be shipping a lie, and a `code:0` that stores nothing is
the most expensive kind of lie a write surface can tell.**

**Hidden columns used to be on that list, and are not any more — the rule did not change, its
premise was refuted.** The refusal rested on *"what `hidden_fields` stores has no observable
effect"*, and that conclusion came from a probe that read back only field **names**; the flag it
needed was in the payload it discarded. Both halves are now measured:

* **the API half** — `GET …/fields?view_id=<the patched view>` returns `is_hidden: true` on
  exactly the hidden column and `false` on the other four; the **same listing without a
  `view_id` carries no `is_hidden` key at all**; and a **control view** reports `false` for that
  same column. So `is_hidden` is a **per-view projection of `property.hidden_fields`**, not a
  property of the field;
* **the human half** — the column is not visible in the API-patched view and is visible in the
  control view. **Click-verified on the Lark WEB client, on one tenant, on 2026-08-12.** The
  desktop and mobile clients are **unmeasured**, not refuted;
* **the write half was never in doubt** — `property.hidden_fields` stores, a second PATCH
  **moves** it from one field id to another, it holds a set of two, `[]` **clears** it back to
  `property: null`, an invented sibling key changes nothing, and an id that is not a field is
  **refused** (`1254044 "Field id is not found."`) — so this endpoint validates its own payload
  rather than swallowing it.

**One column you cannot hide: the PRIMARY field.** Lark refuses it with `1254001`, naming the
id and the reason — *"the primary field cannot be set as a hidden type"* — and this library
relays that answer rather than predicting it, because which column is primary is a read of a
moment and this route buys no field read. That refusal is also the explanation of an older,
unexplained `1254001` seen on this same route: the answer was never about the body's shape, it
was about **which column** was named.

**What hiding a column does NOT do.** It does not narrow a read. `fields?view_id=` still returns
**every** column (marked, not omitted) and **the records payload through a hidden view is
unchanged** — all values, all keys. A view is **not a column selector** and this is **not access
control**; if you need to withhold data, withhold it, do not hide it. `records/search`'s own
projection is **evidence neither way**: it returned **no rows** in that harness **including at
baseline**.

**The edge of that evidence (nothing here is a claim beyond it).** The whole measurement is a
**grid** view, on **one tenant**, with a `tenant_access_token`. Kanban, gallery and gantt views,
`user_access_token`, other tenants and other regions are **unmeasured**.

So the honest deliverable is: **this call makes the view, and four of its knobs are yours;
open it in the product for the rest.**

**`view_type` is an evidence-keyed allow-list.** `grid`, `kanban`, `gallery` and `gantt` were
each created `code:0`; `calendar`, `board` and `list` were each refused by the server, and this
library refuses them **locally, in the server's own words**, so you do not spend a round trip
discovering it. `form` is refused **by policy** — Lark accepts it, and creating one is one PATCH
away from a public submission URL, which is not a thing this library will mint for you.

**`delete_view` is the lighter ceremony.** Deleting a *column* or a *table* is destructive: it
needs an enumerated loss preview and an explicit **consent token** minted from the plan.
Deleting a view destroys no data — the rows and columns are the table's, not the view's — so
`delete_view` needs **no consent token**, just the ordinary plan gate. A table keeps a floor of
one view, so the last one cannot be deleted.

```python
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.view_plan import (
    clear_view_hidden_fields,
    create_view,
    delete_view,
    rename_view,
    set_view_hidden_fields,
)
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: both clients resolve credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()       # a view write is verified by a READ-BACK
schema = BaseSchemaClient.from_write_credentials()  # the WRITE pair, no fallback
table_id = read.list_tables(app_token)[0].table_id

# --- 1. CREATE. The view exists; it is not configured. -----------------------
made = schema_apply(schema_dry_run([
    create_view(app_token, table_id, "Board view", "kanban"),
]), client=schema, read_client=read)
view_id = made.entries[0].read_back["view_id"]
print(made.entries[0].outcome, view_id)
# It has no grouping and no saved sort, and no call here can give it any.
# Open it once in the product to say what the columns mean.

# --- 2. PATCH. rename_view rides the ONE patch op the family has: update_view.
plan = schema_dry_run([rename_view(app_token, table_id, view_id, "Board view (renamed)")])
print([entry.op for entry in plan.entries])              # ['update_view']
renamed = schema_apply(plan, client=schema, read_client=read)
print(renamed.entries[0].outcome)          # 'applied' — earned by re-reading the view

# --- 2b. HIDE COLUMNS. The list is the WHOLE hidden set: it replaces, never adds.
# `[1:]` skips the PRIMARY field, which Lark refuses to hide (`1254001`, in its own words).
columns = [field.field_id for field in read.list_fields(app_token, table_id)]
hidden = schema_apply(schema_dry_run([
    set_view_hidden_fields(app_token, table_id, view_id, columns[1:]),
]), client=schema, read_client=read)
print(hidden.entries[0].outcome, hidden.entries[0].read_back["persisted_hidden_fields"])

# Show them all again. `[]` is the CLEAR instruction and it is NOT "not asked for" —
# read it as "unchanged" and you un-hide a consumer's columns.
shown = schema_apply(schema_dry_run([
    clear_view_hidden_fields(app_token, table_id, view_id),
]), client=schema, read_client=read)
print(shown.entries[0].outcome, shown.entries[0].read_back["cleared"])

# --- 3. LIST. The listing carries names and types, never `property`. ---------
for view in read.list_views(app_token, table_id):
    print(view.view_id, view.view_name, view.view_type)

# --- 4. DELETE. No loss preview, no consent token — a view holds no data. ----
gone = schema_apply(schema_dry_run([delete_view(app_token, table_id, view_id)]),
                    client=schema, read_client=read)
print(gone.entries[0].outcome, len(read.list_views(app_token, table_id)))

# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(gone.applied), "applied,", len(gone.refusals), "refused")
for entry in gone.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: filter a Base two ways — the rows a read returns, and the rows a person sees

**There are two filters in a Base and they are not the same thing.** One narrows a single read;
the other changes what everybody sees. Both are round trips this library makes — mixing them up
is the single easiest mistake to make here, so read what each one actually gives you before you
pick.

**Filter one — the rows a READ returns. You ask for a subset and larkdocio asks Lark for that
subset.** `search_filter()` spells the exact `records/search` body for the filter you described —
the right key, the right operator spelling, the right value encoding, none of which you should
have to get right by hand — and `read.search_records(app_token, table_id, filter=…)` **sends
it**, so a filtered read costs one narrowed read instead of a whole table plus a list
comprehension. The same call takes `sort=` (a list of `SortKey`s, applied in the order given) and
`view_id=` (read the rows a saved view shows). Nothing about the Base changes on this half — a
read is a read. This dialect is keyed by the field's **name**, the name you see at the top of the
column.

**One combination is refused, and the refusal is the honest part.** `view_id=` does not combine
with `filter=` or `sort=`: how a view's saved filter composes with a request filter is something
no measurement in this library shows, and this endpoint answers success either way, so larkdocio
refuses the pair before sending rather than guessing on your behalf. Read the view, then narrow
in Python; or filter the table directly.

**Filter two — the rows a PERSON sees when they open this view.** You change the Base itself: a
view's saved filter. Anyone who opens that view from now on sees the filtered rows. This filter
is keyed by the field's **id** — the `fld…` string — because that is what the view endpoint
takes.

**A SELECT condition's VALUE splits the same way, and the two halves are opposites.** This is
the detail most likely to cost you an afternoon, so both answers are quoted here in full, as
the library itself states them:

> The view route keys a SELECT condition's VALUE by option `opt…` id, exactly as it keys the
> condition's field by `fld…` id: an option NAME sent there answers Lark's "the option id of
> '\<field\>' is not found" at PATCH time. So FieldRegistry.resolve() translates a known option
> name into its id from the field property it read, and refuses an unknown one here — naming
> the options that do exist — rather than letting the plan gate pass a body the apply cannot
> send. An `opt…` id you already hold passes through unresolved, for the same reason a `fld…`
> id does.

> The records/search route takes a SELECT condition's value as the option NAME — the mirror of
> the view route, measured rather than inferred: `is` / 'Done' returned the 2 matching rows of
> 3, and the same condition carrying that option's `opt…` id answered `1254018 InvalidFilter` —
> the same code a name that does not exist answers, so the route cannot tell them apart and
> this library does not pretend to. search_filter() therefore sends the value as given and
> translates nothing; an option id is not something to send there. Because an `opt…`-shaped
> string is a legitimate value for a TEXT field, no local refusal guesses at the shape of a
> search value — this is a documented measurement, not a check.

So: **name for the read half, id for the view half** — and on the view half you may write the
name and let `FieldRegistry.resolve()` translate it, which is the only place a name is accepted.
A wrong option name is refused locally with the real options listed; a wrong option value on the
search half is not something any local check can catch, and the paragraph above says why.

You describe a filter **once**, in one shape, and say which of the two you want. larkdocio will
not let you send one to the other's endpoint: they are different types, and the wrong one is
refused before anything is sent. (The two endpoints also disagree about small things — one wants
a value as a list, the other as a quoted string — which is exactly the sort of detail you should
not have to hold in your head. Describe the filter; larkdocio writes each dialect.) **What
happens next differs by half:** the read dialect goes out on your next read and narrows what
comes back, while the view dialect goes through the plan gate below and is verified by a
read-back.

```python
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.view_filters import (
    Condition,
    FieldName,
    FieldRegistry,
    FilterSpec,
    SortKey,
    search_filter,
    view_filter,
)
from larkdocio.base.view_plan import create_view, delete_view, set_view_filter
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: both clients resolve credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()       # every view write is verified by a READ-BACK
schema = BaseSchemaClient.from_write_credentials()  # the WRITE pair, no fallback
table = read.list_tables(app_token)[0]
column = read.list_fields(app_token, table.table_id)[0].field_name

# --- ONE description of what you want to see. -------------------------------
wanted = FilterSpec(conditions=(Condition(FieldName(column), "isNotEmpty"),))

# --- 1. THE READ FILTER: by field NAME, and IT IS SENT. ----------------------
#        The body larkdocio spells for you...
print(search_filter(wanted).to_dict())
# {'conjunction': 'and',
#  'conditions': [{'field_name': ..., 'operator': 'isNotEmpty', 'value': []}]}

# ...and the read that sends it. `subset` is what Lark returned, not what you
# filtered out afterwards — the narrowing happened on the server.
everything = read.search_records(app_token, table.table_id)
subset = read.search_records(app_token, table.table_id,
                             filter=search_filter(wanted),
                             sort=(SortKey(FieldName(column), desc=True),))
print(len(everything), "rows in the table,", len(subset), "rows matched")

# How to convince yourself the filter really travelled, in one line: ask for
# something no cell can hold. A filter that is IGNORED comes back with the whole
# table; this comes back empty.
none_at_all = read.search_records(app_token, table.table_id, filter=search_filter(
    FilterSpec(conditions=(Condition(FieldName(column), "is", ("no cell holds this",)),))))
print(len(none_at_all))     # 0

# Across page boundaries nothing changes: the filter and the sort are re-sent on
# every page, the cursor still runs to exhaustion, and `read.last_walk_pages`
# reports a filtered walk exactly as it reports an unfiltered one.

# --- 2. THE VIEW FILTER: by field ID, and it STICKS. -------------------------
# Resolve the name to an id first. The field list is read to exhaustion, so an unknown
# name is a clear refusal naming the columns the table really has.
fields = FieldRegistry.from_read_client(read, app_token, table.table_id)
persistent = view_filter(fields.resolve(wanted))
print(persistent.to_dict())
# {'conjunction': 'and',
#  'conditions': [{'field_id': 'fld…', 'operator': 'isNotEmpty', 'value': []}]}

# Make a view, then save the filter onto it. Same gate as everything else:
# build the ops, dry_run them into a plan, apply that plan.
made = schema_apply(schema_dry_run([
    create_view(app_token, table.table_id, "Rows worth looking at", "grid"),
]), client=schema, read_client=read)
view_id = made.entries[0].read_back["view_id"]

log = schema_apply(schema_dry_run([
    set_view_filter(app_token, table.table_id, view_id, persistent),
]), client=schema, read_client=read)

entry = log.entries[0]
print(entry.outcome)                       # 'applied' — and here is why that word is earned:
print(entry.read_back["echoes"])           # True: the view was RE-READ and the filter is there
print(entry.read_back["persisted"])        # what the server actually stored

# --- 3. Tidy up. A table's LAST view cannot be deleted — Lark keeps a floor of one.
schema_apply(schema_dry_run([delete_view(app_token, table.table_id, view_id)]),
             client=schema, read_client=read)

# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**Step 1 narrowed a read; step 2 changed a Base.** That asymmetry is the recipe's real lesson,
and it survives both halves travelling: the read filter lives exactly as long as the call it
rode on, while the view filter is still there tomorrow for whoever opens the view. Pick by how
long you want the effect to last — and note that only the second one needs write credentials at
all. The rest of this recipe is about how that second one proves it arrived.

**Why the first half is believable.** `records/search` accepts body keys it then ignores, so a
success code is not evidence a filter was honoured — an *ignored* filter comes back `code:0` with
the whole table. Nothing in this library shipped on that reading: the filter, the sort and
`view_id` each landed with a live comparison of two reads of the same table in the same run — a
filtered read against an unfiltered one, a filter that can match nothing coming back empty rather
than full, and a sort whose `desc` is exactly the reverse of its `asc`.

**Why `outcome` is worth reading here.** This endpoint accepts things it then ignores. Setting a
view's *filter* works; setting a view's *grouping* answers success and stores nothing at all. So
larkdocio never treats a successful response as proof: after every view write it **re-reads the
view** and compares what the server stored against what you asked for. `applied` means the
server's own state showed your filter. If it ever comes back `dropped`, the call was accepted
and the change is not there — and you will be told, rather than left believing it worked.

**The comparison absorbs exactly one difference: Lark's own re-typing of a value.** A view
condition's value travels as a *string carrying* a JSON array, and Lark parses that array before
it stores it — so a numeric element comes back **unquoted**. A date filter goes out as
`["ExactDate", "1786147200000"]` and reads back as `["ExactDate",1786147200000]`: two different
strings, one filter. The read-back therefore parses that value on **both** sides and compares the
elements as text, so `dropped` never fires on the server's own quoting. It is not a loosening —
a server that stored a *different* number, dropped an element, added one, or reordered them is
still reported `dropped`, and so is a swallowed write that stored nothing at all.

**What this path does not do.** There is **no staleness guard** on a view write: nothing here
will notice if somebody else edits the same view between your plan and your apply. The read-back
is what you have, and it is honest about what it checks — the state after your write, not a
promise that nothing else happened. Re-read before you plan if a Base is busy.

**Grouping and a saved sort are not offered**, and that is deliberate: setting a grouping is
accepted and does nothing, and every saved-sort spelling tried is accepted and stores nothing.
A knob whose effect cannot be checked is worse than no knob. **Hidden columns ARE offered** —
they used to sit in that same sentence, and they left it on evidence rather than on a change of
mind: the write stores, moves and clears, and the effect is visible both to `fields?view_id=`'s
per-view `is_hidden` flag and to a human opening the view. They ride the same read-back
verification everything else here does; see **Recipe: create, configure and delete a view —
hidden columns ARE settable; grouping and a saved sort are NOT**. **Form views are not offered
either** — creating one works on Lark's side, and one further call would publish a public
submission link, so larkdocio does not control a Base's shareability and stays out of it
entirely. Build a form in the product if you need one.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: build and read a row tree (sub-items) — and the two shapes Lark lets you build that no tree can contain

**A Lark row tree is not a record concept.** There is no `parent_id` on a record — six plausible
body keys were each tried and each behaved exactly like a deliberately made-up key: accepted,
and thrown away. What a row tree really is: **a link column pointed at its own table**, plus
**one view property** naming which column that is. The parent edge is then just a value in that
column, written the way you write any other cell.

**You may already be reading one without being told.** If a Base you read has such a column,
`read_base(url, resolve_links=True)` renders it **today** as a column of parent *names* rather
than raw `rec…` ids — `ROOT-1 / CHILD-1 / LEAF-1` instead of `recvrvyxLVX9TP`. That costs you
nothing and needs none of what follows. What follows is for when you want the *structure*.

```python
from larkdocio.base import hierarchy
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.view_plan import create_view, set_view_hierarchy
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: every client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()       # every write here is verified by a READ-BACK
schema = BaseSchemaClient.from_write_credentials()  # the WRITE pair, no fallback
write = BaseWriteClient.from_write_credentials()
table = read.list_tables(app_token)[0]
title = read.list_fields(app_token, table.table_id)[0].field_name

# --- 1. THE COLUMN: a link whose target is its OWN table. -------------------
# Nothing special: the shipped field family, the captured `table_id` key, this table's id.
parent_field_id = schema.create_field(
    app_token, table.table_id, "Parent", 18, ui_type="SingleLink",
    properties={"table_id": table.table_id})

# --- 2. THE VIEW PROPERTY: name that column as the hierarchy. ---------------
# `hierarchy_config(...)` is the ONLY producer of the value this route accepts, and it is
# where a wrong target is refused LOCALLY: point it at a text column and you get the server's
# own words ("the field must be single_link or duplex_link") without spending the round trip.
fields = read.list_fields(app_token, table.table_id)
config = hierarchy.hierarchy_config(parent_field_id, fields=fields, table_id=table.table_id)

made = schema_apply(schema_dry_run([
    create_view(app_token, table.table_id, "Tree", "grid"),
]), client=schema, read_client=read)
view_id = made.entries[0].read_back["view_id"]

log = schema_apply(schema_dry_run([
    set_view_hierarchy(app_token, table.table_id, view_id, config),
]), client=schema, read_client=read)
print(log.entries[0].outcome)              # 'applied' — the view was RE-READ and the id is there

# --- 3. THE TREE: three ordinary record writes. No hierarchy verb anywhere. --
root = write.create_record(app_token, table.table_id, {title: "ROOT-1"}).record_id
child = write.create_record(
    app_token, table.table_id, {title: "CHILD-1", "Parent": [root]}).record_id
leaf = write.create_record(
    app_token, table.table_id, {title: "LEAF-1", "Parent": [child]}).record_id

# --- 4. READ IT BACK AS A TREE. Depth-first, and it says where it got the ----
#        hierarchy from: the view you just configured.
tree = hierarchy.read_hierarchy(
    read.list_fields(app_token, table.table_id),
    read.search_records(app_token, table.table_id),
    view=read.get_view(app_token, table.table_id, view_id))
print(tree.source_detail)                  # "view vew… 's property.hierarchy_config (field id fld…)"
print([row.depth for row in tree.rows if row.record_id in (root, child, leaf)])   # [0, 1, 2]
print(hierarchy.render_hierarchy(tree))
print(tree.disclosure)                     # rows, roots, cycles, multi-parent rows, detached rows

# --- 5. BEFORE you write a parent edge, ask what it would MAKE. -------------
# Lark accepts a cycle at code:0. This tells you so; it does not stop you.
warning = hierarchy.parent_write_disclosure(
    child_id=root, parent_ids=[leaf], hierarchy=tree)
print(warning["cycle"]["rows"])            # ROOT -> LEAF -> CHILD -> ROOT: it would close a loop
print(warning["refused"])                  # False. Nothing here refuses what Lark permits.

# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**Two shapes Lark accepts that no tree can contain — and larkdocio discloses both rather than
refusing either.** A row may have **two parents** (the column's `multiple` flag defaults on) and
a row may be **its own parent** (nothing enforces acyclicity). Both answer `code:0` on the wire.
So:

- **On the write side** you get a disclosure, before the act, from the pointer graph you already
  hold — and if you pass no graph it tells you **in words that it did not check**. A missing
  warning is never a promise there is no cycle. It will never buy an API call to go looking, and
  it will never refuse: inventing a validation Lark does not perform would make this library the
  only thing standing between you and a structure your own tenant allows.
- **On the read side** nothing lies and nothing hangs. Every row on a cycle is marked `cycle` and
  the walk terminates; a row with two parents keeps **both** ids (picking one quietly is the
  specific bug this exists to prevent); a parent that is not among the rows you read is `detached`
  rather than promoted to a root; and a table with no hierarchy comes back **not configured** with
  a reason, never as an empty tree.

**Where the order comes from, said plainly.** larkdocio rebuilds depth-first order **client-side
from the pointers**. The record search it reads with is blind to the hierarchy in every
direction — before and after the view property is set, with a view id and without — and its
`with_hierarchy` / `hierarchy` knobs are ignored exactly like a made-up key, so larkdocio never
sends them. Lark's own tree ordering lives only on an older list endpoint that speaks a different
link-cell shape and needs a configured view; rebuilding costs no extra call and works with no view
at all.

**And it never guesses the column.** A table can hold several self-referencing link columns and
only a view says which is the hierarchy, so you either name it (`field_name=` / `field_id=`) or
hand over a view — and the result tells you which it used. A `view_id` here is a **citation for
where the hierarchy came from**, not a projection: `read_base` still takes none, because a view
does not narrow the columns a read returns.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: attach a file to a record, and prove the bytes survived

An attachment cell is written from a **`file_token`**, and getting one is an **out-of-band leg**:
upload the bytes to the drive media family, take the token it returns, and write *that* into the
cell. The upload is not part of the record write and does not ride the plan gate — it happens
before it.

**Read this first: media accretes, and nothing purges it.** A `bitable_file` /
`bitable_image` token **survives its table's deletion**, and **no route in Lark's open API
purges drive media — measured, not assumed** (nine destructive spellings, fourteen sends, not
one removed a token; the enumeration and its scope are in § "The disposables doctrine", and
the scope matters here: the four probed tokens were sheets- and docx-parented, so for a
Base-parented one those spellings are **unmeasured, not refuted**). Every upload therefore
leaves **permanent** tenant residue — deleting the
Base afterwards does not undo it. This library's answer is disclosure, not a simulated purge: if
you are testing, upload the smallest file that proves your point, and know that it stays.

**`parent_node` is an `app_token`** — the token of the Base the file is attached to, not a table
id, a record id or a field id. Point it at the wrong Base and you have attached permanent,
unsweepable residue to something you did not mean to touch.

**A read-back's `url` and `tmp_url` are credential-class.** An attachment cell reads back
`{file_token, name, size, type, url, tmp_url}`; the last two are short-lived **signed** links.
Nothing in this library logs one, renders one or puts one in an error — `scrub_attachment_cell`
is the projection to pass a cell through before it goes anywhere.

**And "it worked" means the hash matched, not that a call returned 200.** `verify_round_trip`
compares the download against the upload **by `sha256`** and raises if they differ, reporting the
two digests and the two lengths — never the payloads. Bytes are hashed here, never inspected.

**To send a *person* a link, ask for the permalink** — `media.permalink(file_token)` returns the
file's own `https://<host>/file/<token>` address and its `title`. The cell's own `url` /
`tmp_url` are not it: those are the signed links above, and they are credentials. Three things
travel with that address, and none of them is optional reading:

- **The permalink outlives the bytes.** Measured: after the parent Base was deleted the metadata
  query still returned both permalinks — immediately, and again seven minutes later — while the
  bytes answered **HTTP 404**. So a link you hand out today can outlive the content it points at,
  and this library cannot tell from the permalink whether the bytes are still there. **A permalink
  that resolves is not evidence the bytes are there.** Only fetching them is: `download` the token
  and compare digests.
- **A permalink grants nobody access.** It is the object's own *address*, not a credential. An
  unauthenticated GET answers **302 to a login page** — the route is live and login-gated, which
  is not a proof of human openability — and the two calls that *would* grant somebody something
  are refused on this token class (`1066001`, on both the image and the file spellings), exactly
  as they are on a docx-bound token. A file that must be **independently shareable** belongs in a
  folder (`larkdocio.drive.files_write.put_file_in_folder`), not in an attachment cell. This
  library never widens, requests or escalates a scope: a grant is a Lark console action.
- **A `code:0` from that query is not a permalink.** The endpoint answers *success with an empty
  answer* for a token it cannot resolve, putting the reason in `failed_list`; `permalink` reads
  that and raises `MediaPermalinkNotResolvedError` naming the token and Lark's own code, rather
  than reporting a success it did not get.

Scope of the measurement: one tenant, one day, a `tenant_access_token`, one disposable Base and
two small files. `user_access_token`, other tenants / regions / domains, whether a **restore** of
the trashed parent brings the bytes back, and what a **human clicking** the link actually sees are
all **unmeasured** — a click is not a probe.

```python
from larkdocio.base.apply import apply, dry_run
from larkdocio.base.client import BaseReadClient
from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES
from larkdocio.base.media import (
    BaseMediaClient,
    describe_attachment_cell,
    scrub_attachment_cell,
    verify_round_trip,
)
from larkdocio.base.model import ReadProof, snapshot_table
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.schema_ops_fields import create_field
from larkdocio.base.table import assemble_table
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: every client resolves credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()
schema = BaseSchemaClient.from_write_credentials()
write = BaseWriteClient.from_write_credentials()
media = BaseMediaClient.from_write_credentials()    # an upload is a WRITE, always
table = read.list_tables(app_token)[0]

# --- 0. Somewhere to put it (skip this if the column already exists). --------
schema_apply(schema_dry_run([
    create_field(app_token, table.table_id, "Files",
                 FIELD_PROPERTY_SHAPES["Attachment"].field_type, ui_type="Attachment"),
]), client=schema, read_client=read)

# --- 1. UPLOAD. parent_node is the APP TOKEN. This residue is permanent. -----
payload = b"report,rows\nQ3,42\n"
uploaded = media.upload(data=payload, name="q3-report.csv",
                        parent_type="bitable_file", parent_node=app_token)
print(uploaded.file_token, uploaded.size, uploaded.sha256)
# UploadedMedia carries no link of any kind — there is nothing here to leak.

# --- 2. WRITE THE TOKEN INTO THE CELL, through the ordinary record gate. -----
fields = read.list_fields(app_token, table.table_id)
records = read.search_records(app_token, table.table_id)
page = {"items": records, "has_more": False, "page_token": None}
snapshot = snapshot_table(
    assemble_table(table_id=table.table_id, name=table.name, fields=fields, records=records),
    app_token=app_token,
    revision=read.list_tables(app_token)[0].revision,
    read_proof=ReadProof.from_pages([page]),
)
draft = snapshot.edit()
row = snapshot.record_ids[0]
draft.set(row, "Files", [uploaded.file_token])     # a bare token, or {"file_token": …}
log = apply(dry_run(draft), client=write, read_client=read)
print([entry.outcome for entry in log.entries])

# --- 3. READ IT BACK — through the scrub, because two keys are credentials. --
back = {r.record_id: r for r in read.search_records(app_token, table.table_id)}[row]
cell = back.fields["Files"][0]
print(scrub_attachment_cell(cell))          # file_token / name / size / type — no signed links
print(describe_attachment_cell(cell))       # one safe line for a log

# --- 4. PROVE IT. A status code says an answer arrived; a digest says the FILE did.
downloaded = media.download(cell["file_token"])
print(verify_round_trip(uploaded, downloaded))       # the shared sha256, or it raises

# --- 5. A LINK FOR A PERSON. An address, not access — and not proof of the bytes. -
link = media.permalink(cell["file_token"])
print(link.url, link.title)      # https://<host>/file/<token>  q3-report.csv
# This URL is safe to log and to send; it grants the recipient nothing they did not
# already have, and it would keep resolving even after the bytes stopped coming back.
# Step 4 is what says the file is there. This step only says where it lives.
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: price a bulk import before you send it

An import is the one Base write where the **call count** matters more than the diff. All three
numbers you need are produced by `dry_run`, which costs **zero API calls** — so you can price the
whole thing, change your mind, and re-price it, without touching the network once.

| What you read | What it tells you |
|---------------|-------------------|
| `plan.api_call_count` | how many write calls `apply` will make |
| `entry.call_index` | which call each individual record rides in |
| `records_per_call=N` | the knob that chunks each family's batch call |

**The shipped default is one call per family per table** — every add in one `batch_create`, every
update in one `batch_update`. That is deliberate: this repository has **not probed** Lark's
per-call record ceiling, so the engine asserts none rather than inventing a limit it cannot
justify. **The per-call ceiling is unprobed.** If you know your tenant's, pass it; the plan then
shows you exactly which records ride in which call, before anything is sent.

```python
from larkdocio.base.apply import apply, dry_run
from larkdocio.base.client import BaseReadClient
from larkdocio.base.model import ReadProof, snapshot_table
from larkdocio.base.table import assemble_table
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.common import init_env, validate_download_url

init_env(".env")            # FIRST: both clients resolve credentials from os.environ

url = "https://your-domain.larksuite.com/base/YOURBASETOKEN"
domain, url_type, app_token = validate_download_url(url)

read = BaseReadClient.from_read_credentials()
write = BaseWriteClient.from_write_credentials()
table = read.list_tables(app_token)[0]
fields = read.list_fields(app_token, table.table_id)
records = read.search_records(app_token, table.table_id)

# The snapshot's read proof is what makes an import safe: a diff over a PARTIAL read would
# treat the rows it never saw as deletions, so a snapshot that cannot prove it reached the
# end of the walk is refused rather than built.
page = {"items": records, "has_more": False, "page_token": None}
snapshot = snapshot_table(
    assemble_table(table_id=table.table_id, name=table.name, fields=fields, records=records),
    app_token=app_token,
    revision=table.revision,
    read_proof=ReadProof.from_pages([page]),
)

# --- 1. STAGE THE IMPORT IN MEMORY. Nothing has been sent. -------------------
draft = snapshot.edit()
for number in range(60):
    draft.add({"Text": f"imported row {number:02d}"})

# --- 2. PRICE IT. Both of these cost ZERO API calls. -------------------------
one_call = dry_run(draft)
print(one_call.api_call_count)                     # 1 — the shipped default, unchunked

chunked = dry_run(draft, records_per_call=25)
print(chunked.api_call_count)                      # 3 — 60 adds at 25 a call
print(sorted({entry.call_index for entry in chunked.entries}))          # [0, 1, 2]
print(len([entry for entry in chunked.entries if entry.call_index == 0]))   # 25

# --- 3. AUDIT IT before you commit to it. ------------------------------------
for entry in chunked.entries[:3]:
    print(entry.op, entry.record_id, "rides in call", entry.call_index)
for entry in chunked.refusals:
    # A value that is not its field's write shape is refused HERE, for free.
    print("refused before any call:", entry.record_id, entry.refusal.reason)

# --- 4. SEND IT. The log is 1:1 with the plan, in plan order, whatever happens.
log = apply(chunked, client=write, read_client=read)
print(len(log.applied), "of", len(chunked.entries), "landed")
```

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

## Task — cells, tabs and formatting in a spreadsheet

### Recipe: change a spreadsheet at the object level — no Markdown anywhere

The spreadsheet equivalent, and the same claim: **no Markdown call anywhere**. Read the values
as objects, choose the cell from the *data*, write one typed request back through the same
preview-then-apply gate.

Choosing the cell from the data is the point. The values arrive as a row-major matrix
alongside each tab's own `SheetTab` object, so "the Widget row's quantity" is a row index and a
column index — arithmetic, not text matching against a rendered table. A range takes the tab's
opaque `sheet_id`, never its title.

```python
from larkdocio.common import init_env, validate_download_url
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.extent import column_number_to_a1
from larkdocio.sheets.write_apply import ValueWriteRequest, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.sheets.write_range import parse_write_range

init_env(".env")            # FIRST: the credential resolvers read os.environ
url = "https://your-domain.larksuite.com/sheets/YOURSPREADSHEETTOKEN"
domain, url_type, spreadsheet_token = validate_download_url(url)

# 1. READ THE VALUES AS OBJECTS. query_sheets hands back SheetTab objects (each with its
#    opaque sheet_id); read_used_range hands back the values as a row-major matrix.
read_client = SheetsReadClient.from_read_credentials(domain=domain)
tab = read_client.query_sheets(spreadsheet_token)[0]
used = read_client.read_used_range(spreadsheet_token, tab)

# 2. CHOOSE THE CELL FROM THE DATA — a row index and a column index, then the A1 ref for
#    them, offset by wherever the used range itself starts.
row_index = next(i for i, row in enumerate(used.values) if row and row[0] == "Widget")
column_index = used.values[0].index("Qty")
start = parse_write_range(used.a1_range).start
ref = f"{column_number_to_a1(start.col + column_index)}{start.row + row_index}"
target = f"{tab.sheet_id}!{ref}:{ref}"

# 3. WRITE IT BACK as one typed request through the usual preview-then-apply gate.
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
requests = [ValueWriteRequest.for_a1(target, [[4]])]
plan = dry_run(requests, write_client, spreadsheet_token)   # preview: ZERO writes
print(plan.revision_guard, plan.entries[0].before, plan.entries[0].after)
log = apply(plan, write_client)
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **Nothing renders.** The values are objects on the way in and a typed request on the way
  out; a spreadsheet's Markdown projection never enters this recipe.
- **A merged region is not recoverable from a projection, but it *is* on the objects** — read
  `tab.merges` while you have the tab, and re-issue a merge as a merge write if you rewrote
  the values under one (see § "Recipe: merge and unmerge cells").

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: the sheets write handshake

Same plan → dry-run preview → apply discipline, plus the two-tier `stale-sheet` staleness
guard (tier 1 = the `revision` compare-and-swap **when available**, tier 2 = the value
precondition, always — see the bullets below). Ten request families flow through the one
gate (value / formula / rich-cell / dropdown-rule / structural / dimension-property / style /
merge·unmerge / tab / freeze-panes); the value write is shown here, the **formula** write has
its own recipe below, and the four destructive families — **structural**, **merge·unmerge**,
**dropdown** and **tab** — plus the three presentation-only families,
**dimension-property**, **style** and **freeze-panes**, each have their own recipe further down.

**Ten families, nine operations — the same surface counted two ways.** `capabilities()`
reports **nine** `operations` for `sheets-write`, one fewer than the ten families named
above, and the difference is not a gap: `RichCellWriteRequest` is a **request type of the
`value` op** (`capabilities(full=True)["surfaces"]["sheets-write"]["operations"]` → `value` carries
both `ValueWriteRequest` and `RichCellWriteRequest`) rather than an op of its own, because a
rich cell writes through the same `put_values` seam a plain value does. Count request classes
and you get ten; count endpoints-behind-ops and you get nine.

**Getting the spreadsheet token from a URL is one call** — `validate_download_url(url)`
recognises a `/sheets/` URL and hands back its API domain, its type and its token, exactly as
it does for a document URL. See § "Recipe: read a sheet to Markdown" for the same call on the read
side.

**The two sheets writes that do NOT come through this gate are the ones you would look for
here — and they are DIFFERENT PRODUCTS, not two spellings of one.** Putting a **picture** on a
spreadsheet needs bytes, which the plan compiler cannot carry, so each is a leg beside this
engine rather than a request family inside it. Choose by what you want the picture to *be*:

| What you want | The route | The recipe |
|---|---|---|
| A picture that **IS the cell's value** — it sits in the cell, it is what the cell contains, and clearing the cell removes it | one `values_image` call, verdicted by a fresh read of the cell | § "Recipe: put a picture IN a cell (the in-cell image write)" |
| A picture that **FLOATS OVER the grid**, anchored at ONE cell (a multi-cell `a1_range` is refused `1310202 Wrong Range` — refuted, see the recipe) — the grid underneath is untouched and still holds its own values | three beats: `medias/upload_all` bound to the **workbook** → a `float_images` bind → a fresh `float_images/query` | § "Recipe: float a picture over a SINGLE-CELL anchor (the float-image write)" |

Each has its own verdict (a fresh read, never a call's own `code 0`), its own opt-in byte
proof, and its own disclosures; what neither has is `dry_run`, `Plan`, `apply` or the
`stale-sheet` guard, and they say so rather than letting you assume they inherited them.

**The `sheet_id` trap — the one thing to get right first.** An A1 range is
`<sheet_id>!A1:B2`, and `sheet_id` is the tab's **opaque id** (e.g. `3bf016`), **never its
title**. `Sheet1` looks like a range prefix but it is the *default title* Lark gives every
new tab, so a range built from it is refused (`unknown-tab`, with a did-you-mean naming the
real id). The read side hands you `SheetTab` objects and hides ids, so nothing in the read
flow teaches this. Get the id in-recipe from `query_tabs`, as below. Also note the client:
`dry_run` / `apply` want a **`SheetsWriteClient`** (the WRITE app) — *not* the
`SheetsReadClient` the read recipe above builds. The recipe names the variable
`write_client` so the two can never be confused.

```python
from larkdocio.common import init_env, validate_download_url
from larkdocio.sheets.write_apply import ValueWriteRequest, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ

# FROM A SHEETS URL TO A TOKEN — the same one call the read recipe makes. `domain` is the API
# domain, not the tenant host in the url; `url_type` is "sheets" here, and it is what tells you
# a url you were handed is a spreadsheet at all.
url = "https://your-domain.larksuite.com/sheets/YOURSPREADSHEETTOKEN"
domain, url_type, spreadsheet_token = validate_download_url(url)
write_client = SheetsWriteClient.from_write_credentials(domain=domain)

# An A1 range takes the tab's opaque `sheet_id`, NOT its title. "Sheet1" is a TITLE — it is
# the default title Lark gives every new tab — so "Sheet1!A1:A1" is refused. Ask for the
# real id instead of guessing it:
tabs = write_client.query_tabs(spreadsheet_token)          # [{sheet_id, title, index, …}]
sheet_id = next(t["sheet_id"] for t in tabs if t["title"] == "Sheet1")

requests = [ValueWriteRequest.for_a1(f"{sheet_id}!A1:A1", [["new value"]])]
plan = dry_run(requests, write_client, spreadsheet_token)   # preview: ZERO writes
print(plan.revision_guard)                # "active" | "unavailable" — never silently off
print(plan.revision_guard_detail)         # WHY, and what still guards you either way
# Only a Plan reaches apply — and a refused entry RAISES, so take the log off the exception
# when you mean to inspect refusals rather than stop on them.
from larkdocio.errors import LarkApplyRefusedError

try:
    log = apply(plan, write_client)
except LarkApplyRefusedError as refused:
    log = refused.log                     # the SAME log; nothing was rolled back

# THE RETRY GUARD. `entry.refusal.reason` is a plain string carrying the WIRE value
# (`stale-sheet`), so compare it against the exported constant — a hand-typed SCREAMING_SNAKE
# spelling matches nothing, and the refused write is dropped in silence.
from larkdocio.sheets import RefusalReason

stale = [e for e in log.refusals
         if e.refusal is not None and e.refusal.reason == RefusalReason.STALE_SHEET]
if stale:                                 # someone edited between the plan and the write
    plan = dry_run(requests, write_client, spreadsheet_token)   # re-read, re-plan …
    log = apply(plan, write_client, allow_partial=True)         # … and re-apply
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **Dry-run preview:** `dry_run` reads the current values + spreadsheet `revision` and
  builds the `Plan` (target range + before/after per write). Nothing is written.
- **`stale-sheet` semantics — two tiers, and tier 1 is never silently off:**
  - **Tier 1 — the `revision` compare-and-swap, when the anchor is available.** `apply`
    re-reads the `revision` immediately before EACH write; if it advanced since plan time
    (someone else edited), that entry **refuses `stale-sheet` with no write** and resyncs
    the anchor so the rest of the batch still applies — a compare-and-swap, not a blind
    overwrite. But some spreadsheets genuinely report a **constant `0`** (or no) `revision`,
    which would make that comparison `0 == 0` and leave the guard **silently inert** — so
    every plan and every dry-run output carries `revision_guard`: `active` on a usable
    (positive) anchor, `unavailable` on `0` / `None` / any non-positive value, with
    `revision_guard_detail` spelling out the WHY
    and `revision_guard_tiers` naming both tiers. **A revision-`0` spreadsheet marks tier 1
    `unavailable`** — the guard is never silently off. Read it before you trust the guard:
    `print(plan.revision_guard)`.
  - **Tier 2 — the value precondition, always on.** Every entry states its own
    `value_precondition`: `enforced` for a value / rich-cell write (the target's raw value
    is re-read right before the write, and drift refuses `precondition-mismatch` — this is
    what still protects you when tier 1 is `unavailable`), or `none` for a dropdown-rule /
    structural / merge / tab entry, which has no cell-value precondition at all. On a
    constant-`0` spreadsheet a `none` entry carries **no** staleness guard whatsoever — the
    plan discloses that instead of implying a second tier it does not have.
  - **Self-healing.** A plan cached at `0` still refuses `stale-sheet` on ANY nonzero
    advance before its write, and the next plan built on the now-nonzero anchor marks itself
    `active` with no action from you.
- **What refusals mean:** a `precondition-mismatch` (the live value drifted from what the
  plan previewed), a `stale-sheet`, or a typed encoder refusal (e.g. a dropdown color
  error) is a recorded skip in the apply-log — never a corrupt write.
- **Compare against the exported constant, never a typed-out spelling.**
  `entry.refusal.reason` is a **plain string carrying the wire value** — `stale-sheet`,
  `precondition-mismatch`, `shape-mismatch` — so a guard written against an invented
  SCREAMING_SNAKE spelling silently matches nothing and drops the write it was meant to
  re-issue. Import the vocabulary instead of typing it: `from larkdocio.sheets import
  RefusalReason` (and `REFUSAL_REASONS`, the `{NAME: value}` mapping, if you log or group by
  reason). The Base engine exports the same pair from `larkdocio.base`; the docx engine's
  `RefusalReason` is an **enum**, so there you compare against the member itself
  (`reason == RefusalReason.STALE_DOCUMENT`), never against a string.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: work against a disposable spreadsheet (create, use, delete)

**Try a write against a workbook you made and will destroy, not against someone's data.**
This is the runnable form of § "The disposables doctrine": `create_spreadsheet` brings a
throwaway workbook into existence, you do the work in it, and `delete_spreadsheet` in a
**`finally`** trashes it — so a run that dies half way still leaves nothing behind.

**`delete_spreadsheet` destroys the WHOLE FILE.** Every tab, every value, every rule in it.
It is not the tab delete: removing one tab from a workbook that survives is `DeleteTab`
through the plan gate (see § "Recipe: add, copy and delete a tab"), which previews the removal
and snapshots the tab's identity first. Point this call only at a workbook you are finished
with — normally one you created yourself, a few lines earlier.

**The teardown is loud on purpose, and "already gone" is the only thing to forgive.** Deleting
a workbook that is already in the trash raises `LarkAPIError` — never a silent success — so a
`finally` forgives exactly that outcome and still fails on anything else, such as a permission
problem. Use `spreadsheet_is_gone(exc)` rather than comparing a number: **two endpoints report
"gone" with two different codes** (the Drive delete answers `FILE_ALREADY_DELETED_CODE`
`1061007`; addressing a trashed token from the sheets side answers `SPREADSHEET_GONE_CODE`
`1310249`), and the predicate spans both.

**Confirming the delete is a separate step, and worth taking.** A `code: 0` from the delete
means *accepted*. Ask for the workbook again and the error you get back is the proof it is
gone — which is what the last block below does.

**Documents have the same pair**: `WriteClient.create_document(title="…", folder_token="…")`
— the second argument files it where people will find it, and decides which access it inherits
(§ "Recipe: grant a HUMAN access") — and `WriteClient.delete_document(document_id)`, with the
identical `finally` shape. **And so do
Bases, finally** — the runnable form is at the end of § "Recipe: create, rename and copy a Base
(the structural handshake)" — so the doctrine is followable on all three surfaces. And note the ceiling: spreadsheet creation sits on a
**20/min tier**, so a create-per-run loop is something to budget for.

```python
from larkdocio.common import init_env
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_client import SheetsWriteClient, spreadsheet_is_gone

init_env(".env")            # FIRST: from_write_credentials() reads os.environ

write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")

# WHERE the disposable goes — a folder YOU own or created, taken from its Drive link.
# It is required: a create that names no destination is refused before anything is sent.
FOLDER_TOKEN = "fldcnYOURFOLDERTOKEN"

# 1. CREATE the disposable. Capture the token in the SAME statement that made it: a token
#    you drop is a workbook nothing can name, and therefore nothing can clean up.
spreadsheet = write_client.create_spreadsheet("larkdocio-scratch-2026-07-30",
                                              folder_token=FOLDER_TOKEN)
# The answer is a CreatedSpreadsheet — the reply's own dict, so the subscript below is exactly
# what it always was. `spreadsheet.spreadsheet_token` is the same value as an attribute, and
# `spreadsheet.url` is Lark's own link to the workbook (carried, never assembled).
spreadsheet_token = spreadsheet["spreadsheet_token"]
confirmed_gone = False
try:
    # 2. USE it. A fresh workbook has one tab; ask for its opaque sheet_id (an A1 range
    #    never takes a tab TITLE) and write a cell — this is where your real work goes,
    #    normally through dry_run → apply as the write-handshake recipe shows.
    sheet_id = write_client.query_tabs(spreadsheet_token)[0]["sheet_id"]
    write_client.put_values(spreadsheet_token, f"{sheet_id}!A1:A1", [["disposable"]])
    read_back = write_client.read_values(spreadsheet_token, f"{sheet_id}!A1:A1")
finally:
    # 3. DELETE IT WHATEVER HAPPENED. In `finally`, so an exception above still cleans up.
    #    Forgive ONLY "already gone" — anything else is a real failure and must be seen.
    try:
        write_client.delete_spreadsheet(spreadsheet_token)
    except LarkAPIError as exc:
        if not spreadsheet_is_gone(exc):
            raise

# 4. CONFIRM the file is gone rather than assuming it from a code-0 reply: any call against
#    a trashed token errors, and that error IS the confirmation.
try:
    write_client.query_tabs(spreadsheet_token)
except LarkAPIError as exc:
    confirmed_gone = spreadsheet_is_gone(exc)
print(read_back, confirmed_gone)           # [['disposable']] True
```

- **Where you may write is not restricted by the engine.** This recipe is about *how to
  experiment safely*, not a rule the library enforces: `apply` never inspects which
  spreadsheet you target. Use a disposable while you are still finding out what your code
  does, then point the same code at the real workbook.
- **Zero orphans is the standard to hold yourself to.** One create, one delete, and a
  confirmation that the delete landed. If you provision several, keep the tokens in a list
  and re-confirm each one at the end — a create whose token was never recorded cannot be
  audited, and the file stays in your Drive.

- **A Base has the same exit, and it is the newest of the three.** `BaseSchemaClient.create_app(name, folder_token=…,
  time_zone=…)` and `BaseSchemaClient.delete_base(app_token)`, in the identical `finally` shape,
  with `base_is_gone(exc)` as the predicate that forgives *already gone* and nothing else. Two
  things differ and both are worth knowing before you paste it: the confirmation must be asked of
  the **bitable** side (`BaseReadClient.get_app`), because the Drive metadata route keeps
  resolving a trashed Base and so cannot tell you it is gone; and a **brand-new** Base is not
  always addressable as a Drive file yet, so a delete seconds after a create can answer
  not-found-shaped codes for minutes before the identical request lands. Nothing is retried inside
  the call — keep the token and re-attempt. The runnable version is at the end of § "Recipe:
  create, rename and copy a Base (the structural handshake)".

---

### Recipe: clear cells (there is no clear operation)

**There is no `clear` op** — `capabilities()` lists nine sheets-write operations and none of
them clears anything. **A value write of `None` is the clear**: `[[None]]` restores each cell
to *genuinely absent* (not the string `"None"`, not an empty string), which is what shrinks
the used range back. Everything else about it is an ordinary value write, so it goes through
the same `dry_run` → `Plan` → `apply` gate and gets the same compare-and-swap.

Two things to know before clearing anything:

* **The matrix must match the target's arity.** `A2:B3` is 2×2, so it takes
  `[[None, None], [None, None]]`. A matrix of the wrong shape is refused `shape-mismatch`
  **before any I/O** — the arity is a property of your own payload, so nothing is read to
  find out.
* **Clearing is how you destroy a live formula.** The plan's `before` is read under
  `UnformattedValue`, where a formula answers its *computed value* and so reads exactly like
  data. The previewer therefore spends one extra `Formula`-mode read and attaches an
  **`overwrites-live-formula`** note naming every formula the write will destroy. Read it —
  it is the only thing standing between "clear this column" and a silently deleted model.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import ValueWriteRequest, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

# (a) THE CLEAR: None per cell, shaped like the target. A2:B3 is 2 rows x 2 columns.
target = f"{sheet_id}!A2:B3"
plan = dry_run([ValueWriteRequest.for_a1(target, [[None, None], [None, None]])],
               write_client, spreadsheet_token)
print(plan.entries[0].before)             # exactly what you are about to erase
log = apply(plan, write_client)
after = write_client.read_values(spreadsheet_token, target)   # every cell is None: absent

# (b) THE CASE TO LOOK FOR: a clear over a LIVE FORMULA. Dry-run only here — the point is
# the note, which names each formula being destroyed and its expression.
formula_plan = dry_run([ValueWriteRequest.for_a1(f"{sheet_id}!A4:B4", [[None, None]])],
                       write_client, spreadsheet_token)
note = formula_plan.entries[0].preview_note
print(note["kind"], note["count"], note["cells"])      # 'overwrites-live-formula'
print(note["note"])                                    # the whole story, including the fix
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **Nothing is refused for clearing a formula** — it is a legitimate thing to want. The note
  makes it a decision instead of an accident, and `FormulaWriteRequest.for_a1(range, "=…")`
  is what you want instead if you meant to *rewrite* the formula.
- **An inert `"=…"` string is deliberately not reported** by that note: it computes nothing,
  so nothing computed is lost.
- **A cleared cell is absent, not empty**, so the tab's used range really shrinks — this is
  the "undo my write" step, and it is the reason to prefer `None` over `""`.
- **Clearing a cell that holds a PICTURE is the one place `""` is what was measured**, not
  `None` — see § "Recipe: put a picture IN a cell (the in-cell image write)". Writing `""`
  over an in-cell image removes it and the value reads back as `""`; `None` over an image was
  never measured, so this guide does not tell you it works.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: write a hyperlink and a styled run into a cell

**Both of these ship, both work, and until 1.35 neither appeared anywhere in this guide** —
`RichCellWriteRequest.hyperlink()` and `RichCellWriteRequest.styled_runs()` had **zero**
mentions anywhere in this guide and `__doc__ is None` on both constructors, while their
siblings `mention()` and `multi_select()` each had a recipe. A search for *"put a
clickable link in a cell"* found two passages that read like a **no** (see the note below),
and `hyperlink()` was findable only through `dir()`. This recipe
is the correction; the capability itself is unchanged and has shipped since the sheets
rich-cell write landed.

**A hyperlink cell and a link TO a cell are different questions, and only one of them is
refused.** What this recipe writes is an ordinary cell whose **value** is a clickable,
labelled link — that ships, it is below, and it round-trips. What is UI-only is a URL pointing
**at** a cell (`…?sheet=<id>&rangeId=…`), which is a **deep-link** question answered in
§ "The mintable deep links — a spreadsheet tab, a docx block, and a named edition". If you
came here from that passage, you were reading a true sentence about the other topic.

**A rich cell is always ONE cell.** `RichCellWriteRequest` carries a 1×1 values matrix, so
`A1:A1` (or a bare `A1`, which normalizes to it) is the shape; a wider range is not a rich
write. The gate is otherwise identical to a plain value write — mandatory `dry_run`, the
non-forgeable plan, the `stale-sheet` compare-and-swap, and the value precondition **enforced**
(a rich write is a value write, so tier 2 applies to it, unlike a dropdown rule).

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import RichCellWriteRequest, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

# (a) A HYPERLINK — `text` is the LABEL the cell shows; omit it and the link labels itself.
link = RichCellWriteRequest.hyperlink(
    f"{sheet_id}!A1:A1",
    "https://example.com/q4-plan",
    text="Q4 plan")                      # the cell reads "Q4 plan" and clicks through

# (b) STYLED RUNS — one cell, several differently-styled pieces of text. `runs` is a list of
#     kwargs bundles for the run encoder: only `text` is required, the rest are the style.
runs = RichCellWriteRequest.styled_runs(
    f"{sheet_id}!A2:A2",
    [{"text": "Blocked", "bold": True, "fore_color": "#D93026"},
     {"text": " — waiting on legal", "italic": True}])

# ONE plan, both writes. The gate is the ordinary one: preview first, ZERO writes here.
plan = dry_run([link, runs], write_client, spreadsheet_token)
print([e.value_precondition for e in plan.entries])   # ['enforced', 'enforced'] — a rich
                                                      # cell IS a value write, so tier 2 holds
print(plan.entries[0].after)              # the 1x1 matrix: [[{'type': 'url', 'text': …}]]
log = apply(plan, write_client)
print([e.write_kind for e in log.entries])            # ['value', 'value'] — same put_values seam

# WHAT COMES BACK. A hyperlink reads as `[text](link)` in this library's Markdown, and a
# styled run as inline emphasis — but a run's `fore_color` and `font_size` are DROPPED at
# render, so the red above is written and is not one this library will read back to you.
print(write_client.read_value_range(spreadsheet_token, f"{sheet_id}!A1:A1")["values"])
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **The four rich kinds are one family:** `hyperlink` / `styled_runs` / `mention` /
  `multi_select`. The last two have their own recipes — § "Recipe: author a sheet cell that
  @mentions a teammate" and the multi-select half of § "Recipe: add a dropdown list rule to a
  range" — and all four are built through a classmethod so the wire shape always comes from
  the shared encoder; a caller never hand-assembles a segment object.
- **The style keys a run accepts** are `bold`, `italic`, `strikethrough`, `underline`,
  `fore_color` and `font_size` (snake_case here, mapped to the wire's `strikeThrough` /
  `foreColor` / `fontSize` by the encoder). Only the keys you set are sent.
- **`fore_color` and `font_size` are write-only as far as THIS library's Markdown goes** —
  they go on the wire, they come back on the wire, and the renderer drops them because a GFM
  pipe table has nowhere to put them. Do not plan a
  verification step around reading a colour back through `render_spreadsheet`.
- **A plain `ValueWriteRequest` REFUSES a structured cell** (`rich-cell-target`): the rich
  request is what lifts that refusal, and only for the four encoded kinds. That is the gate
  working, not a bug — it is what stops a hand-assembled segment array reaching the wire.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: author a sheet cell that @mentions a teammate

A mention is an **`open_id`** in the payload, never a name in a string. So you have to resolve
to an id **before** you author anything — and that resolution is a separate, explicit step,
because it is the one that can go wrong in a way you must decide about.

**Lead with the EMAIL: `resolve_colleague(email=…)`.** That is the verb that reaches another
user. The name verb below is the same shape and the same three outcomes, but its
directory search was **measured — on one tenant, on one day** — to return at most the account
owner, so *"I know what they are called"* is usually not enough to address them and *"I know
their address"* is. Another tenant's contacts data range may reach further; that is
**unmeasured, not refuted**. Use `resolve_user(name=…)` when you have measured that your own
tenant answers it.

`resolve_user(name=…)` returns **exactly one** user or a typed refusal. It never fuzzy-matches,
never ranks, and never takes the top hit. Three outcomes and all three are yours to handle:

- **resolved** — `lookup.user.open_id` is the id, and it is the only one that matched exactly;
- **refused** — `lookup.refusal.reason` is `not-found` or `ambiguous-N-candidates`. Ambiguous
  carries `candidate_ids` (**ids only**, never names — a refusal that listed the candidates'
  names would be a directory readout one query at a time). Pass one of them, or the id you
  already have, instead of a name;
- **raised** — `LarkPermissionError` if your app lacks the directory scope. *"I could not look"*
  is deliberately not reported as *"there is no such person"*, and there is no fallback: nothing
  here enumerates the directory to approximate a search.

**If you hold the person's EMAIL rather than their name, ask the other verb.**
`resolve_colleague(email=…)` returns the **same** `NameLookup` — the same three outcomes, the
same `partiality`, the same refusal type — over a different endpoint family
(`contact/v3/users/batch_get_id`) whose reach is not the directory search's. It is the
difference between *"I know what they are called"* and *"I know their address"*, and on this
tenant the address question answered for another user the name question does not reach. Read its
reach as measured and its unresolved answer as undifferentiated — the three quoted sentences in
§ *"Recipe: the Base write handshake"*, under *Four honest sources of an id*, are the whole of what it
claims, and the refusal hands you the same text.

Also read `lookup.partiality`. It is always present, and `is_partial` being true means the
directory's answer did not cover everything it was asked — the resolved id is still exact, but
the negative half of the answer is not to be trusted.

**The lookup does not replace the plan-time check.** `dry_run` still proves the mention id
exists, and it must: *"this name means this id"* and *"this id still exists"* are different
facts. Read `plan.mention_validation` either way.

```python
from larkdocio.common import init_env, validate_download_url
from larkdocio.contacts import resolve_user
from larkdocio.errors import LarkPermissionError
from larkdocio.sheets.write_apply import RichCellWriteRequest, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: nothing sees your creds until the .env is loaded

# NAME -> EXACTLY ONE open_id, or a refusal you handle. Never a guess.
try:
    lookup = resolve_user(name="Example User")
except LarkPermissionError as denied:
    raise SystemExit("could not look up the name: " + denied.denial.detail())

if not lookup.resolved:
    raise SystemExit(
        f"{lookup.refusal.reason.value}: {lookup.refusal.detail} "
        f"candidates={list(lookup.refusal.candidate_ids)}")
open_id = lookup.user.open_id

url = "https://your-domain.larksuite.com/sheets/YOURSPREADSHEETTOKEN"
domain, url_type, spreadsheet_token = validate_download_url(url)
write_client = SheetsWriteClient.from_write_credentials(domain=domain)
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

requests = [RichCellWriteRequest.mention(f"{sheet_id}!A1:A1", open_id)]
plan = dry_run(requests, write_client, spreadsheet_token)   # preview: ZERO writes
print(plan.mention_validation)          # "verified" | "unavailable" | "not-applicable"
print(plan.mention_validation_detail)   # WHY — never a silent skip
# then `apply(plan, write_client)` exactly as in the sheets write handshake below.
```

### Recipe: write a live formula into a sheet

**A `"=SUM(...)"` string is not a formula.** Writing it as an ordinary value stores it as
**inert text** — the cell displays `=SUM(B3:B8)` and computes nothing. Lark has **no**
`valueInputOption` / `USER_ENTERED` mode (probed three ways: the query- and body-level
variants are both answered `code 0` and change nothing), so **no flag can make a plain string
evaluate.** An evaluating formula is a different wire shape — `{"type":"formula","text":"=..."}`
— and `FormulaWriteRequest` is what sends it.

You do not have to remember this: a plain value beginning with `=` gets a **loud dry-run note**
saying exactly what will happen (`plan.entries[i].preview_note`), and building a
`FormulaWriteRequest` from text that does not start with `=` refuses at construction
(`FormulaExpressionError`) rather than after the write.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import FormulaWriteRequest, ValueWriteRequest, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

# (a) THE TRAP: a '='-prefixed PLAIN string. The dry-run says so before anything is written.
trap = dry_run(
    [ValueWriteRequest.for_a1(f"{sheet_id}!C2:C2", [["=SUM(B3:B8)"]])],
    write_client, spreadsheet_token)
print(trap.entries[0].preview_note["note"])     # "LOUD WARNING: ... stored as INERT TEXT ..."

# (b) THE FIX: a formula write. The plan previews the expression + what the cell holds now.
plan = dry_run(
    [FormulaWriteRequest.for_a1(f"{sheet_id}!C1:C1", "=SUM(B3:B8)")],
    write_client, spreadsheet_token)
note = plan.entries[0].preview_note
print(note["expression"], note["current_computed_value"], note["precondition_compares"])

log = apply(plan, write_client)
entry = log.entries[0]
print(entry.formula["computed_value"])          # e.g. 21 — read back AFTER the write
assert not log.formula_not_evaluated and not log.inert_formula_strings   # ← the CI check
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **The precondition compares the EXPRESSION, not the computed value.** A computed value moves
  whenever the referenced data moves, so comparing it would refuse writes nobody made. Editing
  the *formula* between plan and apply refuses `precondition-mismatch`; changing the *data* it
  reads does not.
- **`evaluated: False` is the one thing to assert.** Lark **accepts** an unparsable expression
  (`"=SUM("`) with `code 0` and stores it as inert text — there is no API error to catch. The
  engine therefore reads the cell back after the write and records the truth in
  `entry.formula` (`expression`, `stored_expression`, `computed_value`, `evaluated`,
  `error_value`, `normalized`, plus a mandatory `detail`); a green apply-log alone is **not**
  proof a formula is live.
- **The CI assertion has two halves, and you want both.** `log.formula_not_evaluated` catches a
  `FormulaWriteRequest` that landed as inert text; `log.inert_formula_strings` catches the other
  trap — a `=`-prefixed **plain string** written as an ordinary **value**, which produces no
  formula entry at all and so used to sail through a `formula_not_evaluated`-only check. Every
  applied log entry also **retains the `preview_note` its plan carried**
  (`entry.preview_notes` — a tuple, because an entry can earn more than one warning), so the
  loud dry-run warning is in the batch record a CI job reads, not only on an operator's screen.
- **An error sentinel means the formula IS live but could not compute** — `#NAME?` for an
  unknown function, `#REF!` for a bad reference — flagged as `error_value: True` (distinct from
  inert text).
- **Formula references address a tab by its TITLE** (`=SUM(Other!A1:A2)`), which is the
  *opposite* of an A1 write range (`<sheet_id>!A1:B2`). A reference written with a `sheet_id`
  evaluates to `#REF!`. Lark normalizes titles by quoting them, recorded as `normalized: True`.
- **Reading formulas back:** the values API returns the **computed value** under
  `valueRenderOption=UnformattedValue` / `FormattedValue` and the **expression** under
  `Formula`. Note that `Formula` mode cannot tell inert `=`-text from a real formula — both
  answer the same string; only the computed leg distinguishes them.
- **A plain value write over a formula cell silently replaces the formula with a static
  value** (the engine sees only the computed value). Use a `FormulaWriteRequest` when you mean
  to rewrite the formula.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: put a picture IN a cell (the in-cell image write)

**What this makes is a picture that *is* the cell's value** — not a picture floating over the
grid, and not a link. One call carries the bytes, and then the thing that actually proves it
worked is a **second** call: a fresh read of the cell.

**Read these three before you send anything.**

1. **The call mints its OWN media token.** You do not upload anything and you do not choose
   the token — Lark makes one for the cell. That token is **permanent, unpurgeable residue**:
   **no route in Lark's open API purges drive media — measured, not assumed** (nine
   destructive spellings, fourteen sends, not one removed a token; the enumeration and its
   scope are in § "The disposables doctrine"), and *trashing the workbook does not remove the
   bytes*.
   Treat a write here as permanent before you send it. **This route's residue is smaller than
   the float route's, and the difference is worth knowing.** Here the bytes and the binding go
   up in **one** call, so there is no window in which an upload has landed and a bind has not
   — the failure that leaves an orphan on the float route (§ "Recipe: float a picture over a
   SINGLE-CELL anchor (the float-image write)") cannot happen this way. What *can* leave a
   token you cannot use is a failure **after** the write: the cell reads back with no image
   (`SheetsInCellImageBindError`), or the opt-in byte check fails — and when the token is
   known it is carried on the exception as `exc.orphan_file_token`, because *"a permanent
   token exists"* and *"the call failed"* are different facts. **No purge route exists —
   measured, and enumerated in § "The disposables doctrine"** — and this library does not
   invent one; recording the token is all anyone can do with it.
2. **The clear is an ordinary `""` value write**, not a delete verb. There is no *remove
   image* call, and this library does not invent one.
3. **The bytes go up as a JSON array of integers**, which inflates the request to roughly
   **3–4× the file's own size**. This is a real size ceiling: budget from the *inflated* size,
   not the file's. The exact limit is **unmeasured** — an 88-byte PNG is all that was ever
   sent through it. If your file is big, the multipart routes do not pay this inflation:
   `larkdocio.drive.files_write.put_file_in_folder` (§ "Recipe: link a file from a sentence"),
   or the **float-image** route (`medias/upload_all` with `parent_type: sheet_image`, then a
   `float_images` bind), which anchors a picture *over* a range instead of storing it as a
   cell's value — a different product, and one this library ships as its own op: see
   § "Recipe: float a picture over a SINGLE-CELL anchor (the float-image write)".

**This op is NOT plan-gated.** It does not go through `dry_run` → `Plan` → `apply` and it is
not under the `stale-sheet` compare-and-swap — it needs bytes, which the plan compiler cannot
carry. `capabilities()` reports it as a **leg** on `sheets-write` rather than an operation,
for exactly that reason. What it interacts with under a concurrent writer is **unmeasured**.

```python
from larkdocio.common import init_env
from larkdocio.sheets.media import SheetsMediaClient, put_image_in_sheet
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))
target = f"{sheet_id}!B2:B2"                       # ONE cell; wider is refused, unmeasured

# Your own picture is `Path("picture.png").read_bytes()`; this recipe carries a 1x1 PNG
# literal so it runs exactly as printed.
image_bytes = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c49444154789c63606060000000040001f61738550000000049454e"
    "44ae426082"
)

# (a) THE WRITE + THE VERDICT, as one op. The op re-reads the cell itself; what comes back
#     describes what the cell NOW HOLDS, not what the write answered.
written = put_image_in_sheet(
    client=write_client,
    spreadsheet_token=spreadsheet_token,
    a1_range=target,
    data=image_bytes,
    name="picture.png",
    media=SheetsMediaClient.from_write_credentials(domain="larksuite.com"),  # opt-in (b)
)
print(written.file_token, written.range, written.revision)
print(written.bytes_verified)      # True only because a media client was passed

# (b) BYTE PROOF IS OPT-IN, AND OPT-IN BY CONSTRUCTION. Pass no `media=` and nothing is
#     downloaded: `bytes_verified` is then False, which is the honest answer rather than a
#     claim nobody checked. With one, the token is fetched again and compared by sha256 and
#     length — larkdocio.base.media.verify_round_trip, the same check the document image and
#     Base attachment legs use. The bytes are hashed, never inspected.

# (c) THE CLEAR — an ordinary value write. There is no delete verb.
write_client.put_values(spreadsheet_token, target, [[""]])
print(write_client.read_value_range(spreadsheet_token, target)["values"])   # [['']]
```

- **The verdict is the read-back, and the op refuses rather than lying.** If the write is
  accepted and the cell reads back with no image, you get a raised
  `SheetsInCellImageBindError` — an accepted call is not a stored one.
- **A bad tab is refused loudly.** Naming a tab that does not exist answers
  `90215 can not found sheetId`; that is the control that makes an accepted write mean
  something. (Codes are Lark's and can be renumbered — read the message, not the number.)
- **Reading it back later**: an in-cell image renders as `![]({fileToken})` in this library's
  Markdown — see the sheet-reading recipe. The `link` the value carries is an internal-api
  URL with no signature parameter and **unmeasured** resolvability, so it is never presented
  as a working URL; the measured way to the bytes is the media download the op's `media=` leg
  uses.
- **What was measured, and how narrowly**: one tenant, one day, a `tenant_access_token`, one
  88-byte PNG, one workbook. A `user_access_token`, media kinds other than PNG, larger files,
  a write into a cell that already holds a value, multi-cell and merged-cell ranges, and
  whether the picture survives an xlsx export are all **unmeasured, not refuted**. Whether a
  human looking at the sheet *sees* a picture is not something any API call can observe.

---

### Recipe: float a picture over a SINGLE-CELL anchor (the float-image write)

**What this makes is a picture that floats *over* the grid, anchored at one cell** — the cells
underneath keep their own values, and nothing about the grid changes. That is a **different
product** from the previous recipe: *an in-cell image **IS** the cell's value; a float image
floats **OVER** the grid.* Pick by what you want the picture to be, not by which call you found
first.

**THIS RECIPE WAS TITLED *"float a picture OVER a range"* THROUGH 1.34, AND THAT TITLE WAS A
PROMISE THE ROUTE DOES NOT KEEP.** `a1_range` **refuses every multi-cell range**: an ordinary
4×10 `A1:D10` answers **`1310202 Wrong Range`** and binds nothing, while the single-cell
`A1:A1` in the same run lands. A multi-cell anchor was labelled untried-and-therefore-open
through 1.34; that label is now **false and is replaced by a refutation**, and the
reason the parameter is still spelled `a1_range` is that it takes an A1 **string** (`A1:A1`),
not that it takes a span. **Measured twice, independently** — a field exercise (two
sessions, independently) and re-measured for 1.35 on a harness-created disposable
(`tests/test_live_sheets_ld472_doc_truth_gate.py`, in the source repository, which asserts the multi-cell bind fails and
the single-cell control lands). **The edge of that refutation**, because a refutation is a
claim too: it is one tenant, one day, a `tenant_access_token`, one 88-byte PNG, and the two
shapes `A1:D10` and `A1:A1`. A **merged** range and a multi-cell anchor on another tenant stay
**unmeasured** — but do not plan around either, because the shape that was measured is refused.

**AND A REFUSED BIND COSTS YOU A PERMANENT MEDIA TOKEN.** The upload happens **before** the
bind is validated, so a multi-cell `a1_range` uploads the bytes, is refused, and leaves a drive
media token that nothing points at and **no route purges** (measured — see § "The disposables
doctrine" for the nine spellings tried and the scope) — the error carries it as
`exc.orphan_file_token` so you can at least record it. See the residue note below; this is the
one failure mode that costs you something permanent for a mistake the route could have caught
locally.

It is **three calls in a fixed order**, and one op does all three so the order cannot be got
wrong from outside: upload the bytes → bind the token to a range → **ask the tab what it now
has**.

**Read these four before you send anything. Each was measured, each with a control.**

1. **THE UPLOAD BINDS TO THE WORKBOOK — this is the one place a docx habit will mislead
   you.** `parent_node` is the **spreadsheet token**: *not a cell, not a `sheet_id`*. On the
   document route (§ "Recipe: put an image in a document") you create the image **block**
   first and upload against **that block's id** — carry that shape across and you will reach
   for the tab or the anchor cell, and nothing in the answer will tell you clearly. The tab
   appears for the first time in the *bind*, in its `range`.
2. **The upload answering success is NOT a bind.** After a successful upload the tab holds
   nothing: a fresh `float_images/query` before the bind answers an empty list. Nothing points
   at the bytes until the bind, and the only thing that proves the bind is **the fresh query**
   — never the create's own `code 0`. The op does that query itself and refuses if what it
   just made is not listed.
3. **AN ERROR ON THIS ROUTE IS A REFUSAL, EVEN WHEN IT SAYS "RETRY LATER".** Binding a token
   that was never minted answers **HTTP 500 with `1315203 "Server Error, Retry Later"`** and
   creates nothing — a re-query proves it. **Do not retry it**, and do not classify it as a
   transient failure: nothing in this library retries it, and a client that believes the
   message will loop against a call that can never succeed. Read the read-back, not the
   message.
4. **The bind does not police image-vs-file tokens.** A token uploaded as `sheet_file` is
   **accepted** by the float-image bind and then listed as a float image — so mixing token
   families gets you silence rather than a refusal. You cannot hit this through the op (it
   mints the token it binds, and its upload leg sends only the image spelling), but you can
   hit it if you call the bind yourself with a token from somewhere else.

**Read this too: media accretes, nothing purges it, and A FAILED BIND STILL COSTS YOU BYTES.**
The upload mints a **permanent, unpurgeable** drive media token — **no route in Lark's open API
purges drive media, measured, not assumed** (nine destructive spellings, fourteen sends, not
one removed a token, this very path among them; the enumeration and its scope are in § "The
disposables doctrine") — and **neither removing the float image nor trashing the whole workbook
removes the bytes**. The order is what makes this expensive: **the upload happens BEFORE the
bind is validated**, so every failed bind — a multi-cell `a1_range`, a bad `sheet_id`, anything
the route refuses at bind time — leaves a token nothing points at, **permanently**. You are
told exactly that rather than *"nothing happened"*: a permanent token exists and a picture does
not, and the token is on the raised error as `exc.orphan_file_token` so you can at least record
it. **There is no purge route — measured — and this library does not invent one**; recording the orphans is
the only thing anyone can do with them. Upload the smallest file that proves your point, and
get the range right the first time. Step (d) of the code below
runs that failure on purpose and shows you where the orphan token is.

**The ~60 lines of caveat further down are about a DIFFERENT failure.** Point 3 above — the
`1315203 "Server Error, Retry Later"` that is really a refusal — was measured by binding a
token **that was never minted**, i.e. an invented token with no upload behind it. That case
costs nothing, because nothing was uploaded. The orphaning case is the opposite: a **real**
upload followed by a refused bind. Both are refusals on the same route; only one leaves
residue. They were adjacent and undistinguished until 1.35.

**This op is NOT plan-gated.** No `dry_run` → `Plan` → `apply`, and no `stale-sheet`
compare-and-swap — it needs bytes the plan compiler cannot carry, and what the route does
under a concurrent writer is **unmeasured**. `capabilities()` reports both float-image ops as
**legs** on `sheets-write`, for exactly that reason.

```python
from larkdocio.common import init_env
from larkdocio.sheets.media import (
    FloatImageMediaClient,
    put_float_image_in_sheet,
    remove_float_image_from_sheet,
)
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))
anchor = f"{sheet_id}!A1:A1"                       # where the picture is anchored

# Your own picture is `Path("picture.png").read_bytes()`; this recipe carries a 1x1 PNG
# literal so it runs exactly as printed.
image_bytes = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c49444154789c63606060000000040001f61738550000000049454e"
    "44ae426082"
)

# (a) ALL THREE BEATS, as one op. The upload is parented on `spreadsheet_token` — THE
#     WORKBOOK — inside the op; there is no way to hand it a tab or a cell by mistake, and
#     no way to hand it a token minted somewhere else.
floated = put_float_image_in_sheet(
    client=write_client,
    media=FloatImageMediaClient.from_write_credentials(domain="larksuite.com"),
    spreadsheet_token=spreadsheet_token,
    sheet_id=sheet_id,
    a1_range=anchor,
    data=image_bytes,
    name="picture.png",
    width=120,
    height=120,        # width/height are required: the route was only measured with them
)

# What comes back is what THE FRESH QUERY listed, not what the create answered.
print(floated.float_image_id, floated.float_image_token, floated.a1_range)
print(floated.size, floated.sha256, floated.bytes_verified)

# (b) ASK THE TAB YOURSELF, any time. This query is the only thing that says what exists —
#     and it is also the only shipped call in this library that can see a float image at all
#     (a values read cannot, in any form).
listed = write_client.query_float_images(spreadsheet_token, sheet_id)
print([item["float_image_id"] for item in listed])

# (c) REMOVAL — and its verdict is the same fresh query, never the delete's own code 0.
#     What comes back is what the tab STILL lists. The BYTES are not removed by this or by
#     anything else: the media token is permanent residue.
remaining = remove_float_image_from_sheet(
    client=write_client,
    spreadsheet_token=spreadsheet_token,
    sheet_id=sheet_id,
    float_image_id=floated.float_image_id,
)
print(floated.float_image_id in remaining)      # False — proven by the query, not the delete

# (d) THE RANGE REFUTATION, AND WHAT IT COSTS. A multi-cell a1_range is REFUSED — this
#     recipe was titled "OVER a range" through 1.34 and that was wrong. The upload happens
#     BEFORE the bind is validated, so the refusal leaves a PERMANENT media token behind.
from larkdocio.errors import LarkAPIError

orphan_token = None
try:
    put_float_image_in_sheet(
        client=write_client,
        media=FloatImageMediaClient.from_write_credentials(domain="larksuite.com"),
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        a1_range=f"{sheet_id}!A1:D10",          # FOUR columns by TEN rows — refused
        data=image_bytes,
        name="picture.png",
        width=120,
        height=120,
    )
except LarkAPIError as refused:
    orphan_token = getattr(refused, "orphan_file_token", None)
    print(refused.code, refused.msg)            # 1310202 Wrong Range
print(orphan_token)                             # PERMANENT residue. Record it; nothing purges it.
print(write_client.query_float_images(spreadsheet_token, sheet_id))   # [] — nothing was bound
```

- **Byte proof is on by default here** (unlike the in-cell recipe, where you pass a media
  client to opt in): the token is downloaded again and compared by `sha256` and length —
  `larkdocio.base.media.verify_round_trip`, the same check the document image and Base
  attachment legs use. Pass `verify_bytes=False` to skip it, and `bytes_verified` then says
  `False` rather than claiming something nobody checked. The bytes are hashed, never
  inspected.
- **A values read cannot see this picture.** A float image is not a cell value, so reading the
  sheet to Markdown will not mention it and *"the sheet reads clean"* does not mean *"the
  sheet has no pictures"*. The query in (b) is how you ask.
- **`offset_x` / `offset_y`** default to the measured `0`. `float_images` **PATCH**
  (move / resize) and the GET-one were **never tried** — `unmeasured`, not refuted — so this
  library ships no move or resize; remove and re-create instead.
- **A MULTI-CELL `a1_range` IS REFUTED, NOT UNMEASURED.** `A1:D10` answers `1310202 Wrong
  Range` and binds nothing; the single-cell `A1:A1` control in the same run lands. Two
  independent measurements (a field exercise, and the 1.35 re-measurement in
  `tests/test_live_sheets_ld472_doc_truth_gate.py`, in the source repository). Through 1.34 this bullet filed a
  multi-cell anchor as merely untried, and the recipe was titled as working over a range;
  both are corrected here rather than quietly dropped. A **merged** anchor is still
  **unmeasured** — and the refuted shape is what the old title promised, so do not plan around
  the untried one either.
- **What was measured, and how narrowly**: one tenant, one day, a `tenant_access_token`, one
  88-byte PNG, one workbook, one single-cell anchor. A `user_access_token`, media kinds other
  than PNG, the chunked-upload family, larger files, merged anchors, concurrent
  writers, and whether the picture survives an xlsx export are all **unmeasured, not refuted**.
  Whether a human looking at the spreadsheet *sees* a picture is not something any API call can
  observe.

---

### Recipe: insert and delete rows and columns (a structural write)

**The trap this family exists to make inexpressible.** Lark's insert and delete endpoints take
the *same* `{startIndex, endIndex}` body and read it in **opposite** conventions — insert is
**0-indexed, half-open** `[start, end)`; delete is **1-indexed, INCLUSIVE** `[start, end]`. A
caller who computes one span and reuses it for the other silently corrupts data. So there is
**no raw span on any request**: insert takes a **position + a count**
(`InsertRowsAt(sheet_id, before_row=2, count=1)`), delete takes an **inclusive `first`/`last`**
(`DeleteRows(sheet_id, first=2, last=3)` removes **two** rows), and each converts to its
endpoint's native convention internally. The plan shows you both — `semantic` restates your
intent in English and `convention` names what went on the wire.

**A delete is destructive, so it pays for a read.** At plan time the previewer snapshots the
**removed payload** — the doomed cells' values, the pre-write geometry, and the merges the span
intersects — so the log alone can reconstruct what was destroyed. A delete whose loss cannot be
snapshot is **refused** rather than performed. The values API answers the full *declared* grid
(with the pad as `null`), so the payload is narrowed to the used extent and the narrowing is
disclosed in **`values_trim`** — every deleted row is still listed; only the empty pad is gone.

**Two numbers, two bases — and the plan now names both.** `before_row` / `before_col` are
**1-based against displayed row position** / **1-based against displayed column position**:
`before_col=3` inserts to the left of the column you see as `C`, `before_row=1` inserts above
the first row. The `convention` key beside them — `'0-index-half-open'` — describes the span
larkdocio put **on the wire** (`start_index` / `end_index`), **not** your parameter; for an
insert the two bases genuinely differ. Reading the wire convention as the parameter's own is
how a column lands one slot early, with `code: 0` and no warning, so the `semantic` line spells
out both: `insert 1 column(s) before column 3 (before_col is 1-based against displayed column
position; wire span [2, 3) is 0-index-half-open)`. A **delete** has only one base — `first` /
`last` are 1-based inclusive and go on the wire unchanged.

**One batch is one snapshot.** Every entry of a batch is previewed against the state `dry_run`
read, and `apply` does not re-plan. So do not queue a delete behind an insert on the same axis
in one batch: the delete's indices would name the *pre-insert* sheet. Split them, and re-read
between — which the recipe below does deliberately.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import (
    DeleteRows,
    InsertColsAt,
    InsertRowsAt,
    apply,
    dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

# BATCH 1 — GROW. A position + a count, never a raw span.
grow = dry_run(
    [InsertRowsAt(sheet_id, before_row=2, count=1),      # 1 blank row BEFORE row 2
     InsertColsAt(sheet_id, before_col=3, count=1)],     # 1 blank column BEFORE column 3
    write_client, spreadsheet_token)
print([e.structural["semantic"] for e in grow.entries])
print([e.structural["convention"] for e in grow.entries])   # '0-index-half-open' on the wire
grow_log = apply(grow, write_client)
# The engine re-reads the geometry after every structural write and PROVES the shift.
print([e.structural["shift_verified"] for e in grow_log.entries])

# BATCH 2 — SHRINK, planned fresh (batch 1 moved the rows batch 1's plan described).
shrink = dry_run([DeleteRows(sheet_id, first=2, last=3)],   # rows 2 AND 3 -> 2 rows
                 write_client, spreadsheet_token)
entry = shrink.entries[0]
print(entry.structural["semantic"], entry.structural["convention"])   # '1-index-inclusive'
removed = entry.after["removed"]          # the undo record, snapshot BEFORE the write
print(removed["a1_range"], removed["values"], removed["removed_merges"])
print(removed["values_trim"]["axis"], removed["values_trim"]["used"],
      removed["values_trim"]["declared"])
shrink_log = apply(shrink, write_client)
print(shrink_log.entries[0].structural["reply_count"],
      shrink_log.entries[0].structural["count_mismatch"])

# A span that runs past the tab is NOT refused — Lark accepts it and removes fewer rows than
# you asked for — but the plan says so first, in an `out-of-bounds-dimension` note. Dry-run
# only: this is a preview, and nothing here is applied.
probe = dry_run([DeleteRows(sheet_id, first=9999, last=10000)],
                write_client, spreadsheet_token)
out_of_bounds = probe.entries[0].preview_note
print(out_of_bounds["kind"], out_of_bounds["count"], out_of_bounds["note"])
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(shrink_log.applied), "applied,", len(shrink_log.refusals), "refused")
for entry in shrink_log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **`AppendDimension(sheet_id: str, major_dimension: str, length: int = 1)`** grows the tab at
  the end (`major_dimension` is `"ROWS"` or `"COLUMNS"`; anything else is refused at
  construction), and **`AppendRowsWithValues`** appends rows *carrying values* in one call (its
  rows are appended, not written into a rectangle, so it has no arity to match). `InsertColsAt`
  / `DeleteCols` are the column twins of the two shown above — same conventions, same
  disclosures.
- **A reversed span is refused at construction** with a typed `DimensionSpanError`
  (`DeleteRows(first=5, last=2)`), naming the fault, both repairs and a valid example — never
  a bare `ValueError` after a round trip.
- **The apply-log records the observed delta, not the requested one.** `count_mismatch` is
  `True` when Lark's own `delCount` disagrees with the span you asked for, and
  `shift_verified` is the geometry re-read agreeing with the previewed shift. Parity is never
  assumed.
- **A COLUMN INSERT SILENTLY RELOCATES A DROPDOWN RULE, AND NOTHING WARNS YOU.**
  `InsertColsAt` shifts the cells to the right of the insertion point, and a
  `dataValidation` rule already applied to a range over there **moves with them** — so the
  rule now applies to a different set of cells than the one you last named. **No
  `preview_note` discloses it**: the previewer reads values, geometry and merges, and there is
  no data-validation read leg at all in this library, so the plan cannot see the rule to warn
  about it. That is the whole shape of the gap, stated rather than left to be discovered:
  larkdocio **cannot read a dropdown rule back, cannot delete one, and cannot tell you where
  one ended up** — it can only write list rules (§ "Recipe: add a dropdown list rule to a
  range"). If a tab carries dropdown rules and you are about to insert into it, keep your own
  record of which ranges you ruled and re-issue the rule after the structural write; checking
  it in the Lark UI is the only other way. Adding the missing `preview_note` is engine work
  and is deliberately not minted — the disclosure is the deliverable here.
  **The evidence, so you can size it:** the relocation was observed live in one session
  (a rule added to a range, `InsertColsAt` before it, the rule read back applying elsewhere) —
  **one tenant, one workbook, one insert**, and the row twin is **unmeasured, not refuted**.
  The *absence of the warning* is not an observation at all but a code fact you can check
  yourself: no `preview_note` kind names data validation, and no read leg exists to produce
  one. What the rule does under a *delete* is likewise unmeasured.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: set a row's height, a column's width, and hide a row (a dimension-property write)

**The convention on this endpoint is the opposite of the one next to it, and that is the whole
reason these are typed requests.** Three verbs already live on Lark's dimension path and they do
**not** agree: an **insert** is 0-indexed half-open `[start, end)`, a **delete** is 1-indexed
inclusive `[start, end]`, and the **property** verb (`PUT dimension_range`) is **1-indexed
inclusive** — the delete convention, not the insert one. That was established by probing a
throwaway spreadsheet before the op was built, because guessing it from the neighbour resizes or
hides the wrong rows *silently*. You never write a raw span: `SetRowProperties(sheet_id,
first=2, last=3, fixed_size=60)` sets **two** rows, a single row is `first == last`, and
`entry.structural["convention"]` tells you what went on the wire.

**Hiding is a fidelity event, and the plan says so.** A hidden row's data is still there, and
larkdocio's reader still emits it — so after a hide, a Markdown read of that tab shows rows no
human looking at the spreadsheet can see. Any plan entry that hides carries a
`hidden-dimension-fidelity` note naming exactly which spreadsheet rows or columns become
invisible. A pure height/width change carries **no** note: it hides nothing.

**What cannot even be built.** A reversed band, a band naming neither property, a negative
`fixed_size`, and a band wider than the **5000**-row/column dimension ceiling all raise a typed
`DimensionPropertyError` at **construction** — before any call. So does `fixed_size=0`, which is
the interesting one: Lark **accepts** it and *clears the custom size* (the row springs back to
the tab's default height) rather than hiding anything, so a caller who meant "hide" would get a
success and no hidden row. Pass `visible=False` to hide. A band running past the tab's declared
row/column count refuses at **plan time** with `out-of-bounds-dimension`, naming the tab's real
count and how to grow it first.

**Reading back what you set costs an export.** A row height, a column width and a hidden flag
are visible **only** through the xlsx export leg (`ExportedSheet.row_dimensions` /
`.col_dimensions`) — `metainfo` and the tab query carry none of it. That is why this op is
verified by its own leg and never drags the export into `apply`: an export is an async
whole-workbook task, which is an absurd price for a column width.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import (
    DimensionPropertyError,
    SetColProperties,
    SetRowProperties,
    apply,
    dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

# A size change and a hide, in one batch. `first`/`last` are 1-indexed and INCLUSIVE.
plan = dry_run(
    [SetRowProperties(sheet_id, first=2, last=3, fixed_size=60),   # rows 2 AND 3, 60px tall
     SetColProperties(sheet_id, first=2, last=2, fixed_size=200),  # column B, 200px wide
     SetRowProperties(sheet_id, first=4, last=4, visible=False)],  # hide row 4
    write_client, spreadsheet_token)
print([e.structural["semantic"] for e in plan.entries])
print([e.structural["convention"] for e in plan.entries])   # '1-index-inclusive' on the wire

# The hide is DISCLOSED; the two size changes are not (they hide nothing).
disclosures = [[n["kind"] for n in e.preview_notes] for e in plan.entries]
print(disclosures)                       # [[], [], ['hidden-dimension-fidelity']]
hide_note = plan.entries[2].preview_notes[0]
print(hide_note["hidden_rows"], hide_note["note"])

log = apply(plan, write_client)
print([e.to_dict()["outcome"] for e in log.entries])
# The log names the leg that can verify a dimension property, and why it is not run here.
print(log.entries[0].structural["verified_by"])

# Show the row again — the round trip is idempotent.
show_log = apply(dry_run([SetRowProperties(sheet_id, first=4, last=4, visible=True)],
                         write_client, spreadsheet_token), write_client)
print(show_log.entries[0].to_dict()["outcome"])

# fixed_size=0 is refused, because Lark would accept it and NOT hide the row.
try:
    SetRowProperties(sheet_id, first=4, last=4, fixed_size=0)
except DimensionPropertyError as exc:
    print("refused before any call:", str(exc)[:60])

# A band past the tab's declared rows refuses at PLAN time, with no write issued.
row_count = write_client.read_sheet_geometry(spreadsheet_token, sheet_id)["row_count"]
over = dry_run([SetRowProperties(sheet_id, first=row_count, last=row_count + 5, fixed_size=60)],
               write_client, spreadsheet_token)
print(over.entries[0].refusal.reason, over.entries[0].refusal.detail[:60])
```

- **`fixed_size` is in PIXELS**, but the export reports a row's `ht` in points and a column's
  `width` in character units, and the relation is not 1:1 (60 px came back as `ht="44"`). Compare
  a read-back against `ExportedSheet.default_row_height` / `.default_col_width`, or against a
  before-snapshot — never against a conversion factor.
- **`visible` and `fixed_size` are independent**: pass either, or both in one request.
- **One batch is one snapshot.** Grow the tab (`AppendDimension`) in one batch and set properties
  on the new rows in the next — a plan is previewed against the state `dry_run` read.
- **Word wrap is not here — and it is not writable anywhere.** `dimensionProperties` carries only
  `visible` and `fixedSize`, so wrap was never a dimension property; it is a **cell style** field,
  and it was probed there and refuted. See § "Recipe: set a cell's fill, font, border and number format (a style write)"
  → *"Word wrap"*. Cell **borders**, probed in the same run, ARE writable and that recipe ships
  them.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: set a cell's fill, font, border and number format (a style write)

**One typed style, two wire shapes.** `StyleWriteRequest(range, CellStyle(...))` styles one range
(`PUT …/style`); `BatchStyleWriteRequest` styles **N ranges in ONE call**
(`PUT …/styles_batch_update`), which is the whole reason it exists — twelve ranges through the
single-range op would spend twelve throttled writes and twelve staleness checks. `CellStyle`
carries the fill (`back_color`), the text colour (`fore_color`), the font (`bold` / `italic` /
`font_size`), the **border** (`border_type` / `border_color`) and the number format
(`formatter`); any one of them alone is a legal write.

**Borders: eight types, per-edge, additive, and `NO_BORDER` is the clear.** `border_type` takes
one of `FULL_BORDER` · `OUTER_BORDER` · `INNER_BORDER` · `NO_BORDER` · `LEFT_BORDER` ·
`RIGHT_BORDER` · `TOP_BORDER` · `BOTTOM_BORDER`, and `border_color` its `#RRGGBB` colour. Each was
probed live and read back out of the export's own `xl/styles.xml`, so what follows is measured,
not documented:

| | what it does |
|---|---|
| the four edge values | land **exactly one** edge each |
| `FULL_BORDER` | all four edges, on every cell in the range |
| `OUTER_BORDER` | the **range's perimeter** — a corner cell gets only its two outside edges |
| `INNER_BORDER` | only the grid lines **between** cells; no perimeter |
| `NO_BORDER` | **the clear.** Clears a partial border too, and over a subset of a bordered range clears only the cells it names |

- **Borders ADD, they do not replace.** `LEFT_BORDER` then `TOP_BORDER` on the same cell leaves
  **left and top**; a later font-only write on a bordered cell keeps the border. `NO_BORDER` is the
  only way back.
- **The value is case-sensitive** and the empty string is not a clear: `"full_border"` and `""`
  both land nothing, and both are refused at **construction** so they cost no call. (Lark answers
  the **generic** `WrongRequestBody` code `90204` — the same one a bad font size gets — so its
  accompanying `msg` is what names the cause: here `invalid borderType`.)
- **`border_color` alone is refused, and this one is worth knowing.** Sent without a
  `border_type`, Lark answers `code 0 "success"` with `updatedCells: 1`, bumps the revision — and
  sets no border at all. A write that reports success and does nothing is the worst kind, so it
  raises before any call. A malformed colour with a valid type answers the same generic `90204`
  with `msg` `invalid borderColor`, which is likewise refused up front.
- **A border does not spread across a merge**, exactly as a fill does not: bordering a merge's
  anchor borders the anchor, and the `style-partial-merge` note covers it unchanged.
- **THE GATE CANNOT SEE A BORDER.** A style write turns the export style leg on, and that leg
  reads each cell's bold / italic / fill / number-format — **not its border** (the shipped
  `ExportedCell` has no border field; style READ is a separate surface). The border does land, and
  everything else in the same write is verified as usual, but the border itself is **write-only as
  far as the gate is concerned** — so every plan entry carrying a border says so, in a
  `style-border-not-verifiable` note. Nothing is refused; you are told, rather than left to assume
  a check that did not happen.

**Word wrap: NOT A WRITABLE CELL-STYLE FIELD, and the endpoint will tell you otherwise.** Nine
candidate field names were probed live — `wrap`, `wrapText`, `wrapStrategy` (`"WRAP"` and
`"CLIP"`), `textWrap`, `autoWrap`, `font.wrap`, a bare int `wrap`, and `wrap` alongside a real
alignment field — and **every one answered `code 0 "success"` with `updatedCells: 1` and a
revision bump, while the exported cell came back completely unstyled.** That reply proves nothing,
which is the point: the same probe sent a **deliberately nonsense field name** with no real field
beside it and got the identical `code 0 "success"`, `updatedCells: 1`, revision bumped, nothing
landed. **This endpoint silently ignores fields it does not know.** The distinguishing arm removes
the last doubt — `{"hAlign": 0, "wrap": true}` in ONE request landed the `hAlign` (the export shows
`horizontal="left"`) and not the wrap — so the export does report alignment attributes, and
`wrapText` is absent because nothing set it. So larkdocio ships **no** wrap knob rather than one
that reports success and does nothing; set a wrap by hand in the Lark UI. Evidence:
`tests/captures/sheets-border-wrap-probe/captures/01-border-wrap-characterization.json` (in the source repository).

**`font_size` is an int here, 9..36, and out of range is REFUSED — not clamped.** The wire form
is the string `"<size>pt/1.5"`, which is built for you, once: passing the string yourself is
refused so there is one definition of that shape. A size outside 9..36 raises at
**construction** with Lark's own answer quoted, because Lark refuses the size rather than
clamping it — probed at both ends, 8 and 37 refused, 9 and 36 landed as asked.
(`90204` is Lark's **generic** `WrongRequestBody` code, so its accompanying `msg` is what names
the cause — here `invalid fontSize, fontSize must between 9 and 36`. The same message comes back
for a wrongly-*shaped* size, which is why you pass an int and never the string.)
Line spacing is deliberately not a knob.

**Verifying a style costs an export, and the plan says so before you apply.** Cell style is
readable **only** through the asynchronous whole-workbook xlsx export (§ "Recipe: read a sheet at style fidelity (the L2 export leg)"), so every style plan entry carries a `style-verification-cost` note stating that
price — and a third scope, `drive:export`. That is also why there is **no style precondition**:
the write is protected by the tier-1 staleness anchor alone — and on a spreadsheet whose
`revision_guard` reads `unavailable` (see the handshake recipe's two tiers) a style entry has no
staleness guard at all, which the plan says per entry rather than leaving you to assume.

**A style lands on exactly the cells your range names — a merge does not spread it.** Styling a
merged region's anchor styles the anchor and **nothing else** (probed: `updatedCells: 1`, the
covered cells left with no style), so naming only part of a merge leaves that region with mixed
stored style — invisible while the cells stay merged, plainly visible the moment the merge is
dissolved. A plan whose target clips a merge carries a `style-partial-merge` note naming the
region and handing back the range that covers all of it. Nothing is refused — styling a merged
heading through its anchor is ordinary — you are simply told first.

**Both endpoints reject a bare single cell** (`90202 wrong range=…`), including the batch form's
`ranges` array, so every range is normalized to `Start:End` for you: `A1` goes on the wire as
`A1:A1`.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import (
    BatchStyleWriteRequest, CellStyle, StyleError, StyleSpan, StyleWriteRequest,
    apply, dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

# A header row: bold, filled, one range.
header = StyleWriteRequest(f"{sheet_id}!A1:C1",
                           CellStyle(bold=True, font_size=12, back_color="#D9EAD3"))
plan = dry_run([header], write_client, spreadsheet_token)
print(plan.entries[0].structural["semantic"])
cost = next(n for n in plan.entries[0].preview_notes
            if n["kind"] == "style-verification-cost")
print(cost["verified_by"], cost["scope"])    # the leg, and the extra scope it needs
log = apply(plan, write_client)
print(log.entries[0].to_dict()["outcome"], log.entries[0].structural["verified_by"])

# A number format alone — no font, no fill.
percent = apply(dry_run([StyleWriteRequest(f"{sheet_id}!B2:B9",
                                           CellStyle(formatter="0.00%"))],
                        write_client, spreadsheet_token), write_client)
print(percent.entries[0].to_dict()["outcome"])

# N ranges, ONE call: the same style over two ranges, then a second style beside it.
batch = BatchStyleWriteRequest([
    StyleSpan([f"{sheet_id}!A3:C3", f"{sheet_id}!A5:C5"], CellStyle(back_color="#FFFF00")),
    StyleSpan([f"{sheet_id}!A4:C4"], CellStyle(italic=True, fore_color="#FF0000")),
])
batch_log = apply(dry_run([batch], write_client, spreadsheet_token), write_client)
print(batch_log.entries[0].to_dict()["outcome"], len(batch.ranges), "ranges in one call")

# A size Lark refuses cannot be built — no call is spent finding out.
try:
    CellStyle(font_size=8)
except StyleError as exc:
    print("refused before any call:", str(exc)[:60])

# A tab id that is not on this spreadsheet refuses at PLAN time, with no write issued.
unknown = dry_run([StyleWriteRequest("deadbe!A1:A1", CellStyle(bold=True))],
                  write_client, spreadsheet_token)
print(unknown.entries[0].refusal.reason, unknown.entries[0].refusal.detail[:60])
```

- **Read the style back through the export leg**, not the values API: a values read cannot see a
  cell format at all, and `FormattedValue` shows the number format's *effect* on the text rather
  than the pattern. `SheetsExportReader.read_workbook(token)` → `cell("A1").bold` / `.fill_rgb` /
  `.num_fmt` is the read that can confirm a style write.
- **The export reports no font SIZE**, so a size write is not verifiable through the shipped
  reader — assert what it does report (bold / italic / fill / number format) and treat the size as
  written-not-read-back rather than inventing a field.
- **A colour is `#RRGGBB`**; a three-digit or named colour is refused before the call, because a
  rejected colour would fail the whole style write including the parts that were fine.
- **There is no way to CLEAR a number format through this field.** `formatter="General"` — the
  obvious guess — is refused with the **generic** `90204` code whose `msg` reads `invalid
  formatter`, and nothing establishes what Lark accepts as "no format", so `CellStyle` does not
  invent one. Leave `formatter` unset to leave the cell's format alone; to change it, write the
  pattern you want.
- **Name the whole merged region** when you mean the whole block: the note hands you the range
  (`note["whole_regions"]`), so the repair is a substitution rather than geometry arithmetic.
- **Borders and word wrap are not here.** `CellStyle` ships only the fields with captured
  evidence behind them.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: freeze and unfreeze rows and columns (a freeze-panes write)

**Freeze is the one write with no index-convention question, and one real trap instead.**
`FreezePanes(sheet_id, rows=2)` takes **counts, not indexes** — "pin the first two rows" — so
there is no off-by-one to get wrong. The trap is that `updateSheet`'s `properties` is a
**PATCH**: an axis you do not name is left exactly as it was. So on a tab that already freezes a
column, `FreezePanes(sheet_id, rows=2)` keeps that column frozen, and clearing **both** axes is
`FreezePanes.unfreeze(sheet_id)` — never a rows-only `0`. The request only ever puts the axes you
named on the wire, so it cannot accidentally reset the other one.

**Zero new endpoint.** The `updateSheet` object rides the same `sheets_batch_update` call the tab
ops use; the frozen read-back rides the same `metainfo` call the staleness guard uses. Nothing new
was added to the client for this op.

**A freeze replaces a freeze, and the plan says so before the write.** There is no precondition to
compare and no cell to diff — a freeze simply wins — so any plan entry whose tab already freezes
something carries a `freeze-replaces-freeze` note naming **both** the current counts and the
target ones, including for an unfreeze (which discards someone's frozen band) and for a freeze
that asks for what is already there (still a write: Lark bumps the revision either way).

**What refuses, and when.** A request naming neither axis, a negative count, a bool and a
fractional count all raise a typed `FreezeError` at **construction** — before any call. A count
past the tab's own row/column count refuses at **plan time** with `frozen-count-out-of-range`,
naming the tab's real count. Note the boundary: freezing **every** row is legal, and only
`rowCount + 1` fails — Lark's own message ("must less than sheet `rowCount`") misstates that, so
the refusal carries the tested truth instead.

**Reading back what you froze is cheap**, unlike a row height: the counts live in `metainfo`
(`read_frozen_panes`) and in the tab query, so the verification leg runs inside `apply` and each
entry records the counts **observed** after the write. On the read side,
`SheetsReadClient.read_tabs_frozen(token, tabs)` resolves every tab's frozen state in one call and
**never raises** — a tab whose frozen state could not be established comes back `unavailable`
with the reason, never as "nothing is frozen".

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import FreezeError, FreezePanes, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

# Freeze a header row and a label column — one request, both axes.
plan = dry_run([FreezePanes(sheet_id, rows=1, cols=1)], write_client, spreadsheet_token)
print(plan.entries[0].structural["semantic"])
log = apply(plan, write_client)
print(log.entries[0].to_dict()["outcome"], log.entries[0].structural["observed"])
print(log.entries[0].structural["verified_by"])       # 'metainfo-frozen-leg'

# Freezing MORE rows over the existing freeze is disclosed before the write.
replace_plan = dry_run([FreezePanes(sheet_id, rows=2)], write_client, spreadsheet_token)
note = replace_plan.entries[0].preview_notes[0]
print(note["kind"], note["current"], note["target"], note["preserved_axes"])
apply(replace_plan, write_client)

# Read the frozen state back — the counts, and which read produced them.
frozen = write_client.read_frozen_panes(spreadsheet_token, sheet_id)
print(frozen["frozen_rows"], frozen["frozen_cols"], frozen["source"])

# Unfreeze BOTH axes. A rows-only 0 would leave the frozen column pinned.
unfroze = apply(dry_run([FreezePanes.unfreeze(sheet_id)], write_client, spreadsheet_token),
                write_client)
print(unfroze.entries[0].to_dict()["outcome"], unfroze.entries[0].structural["observed"])

# A request naming no axis cannot be built at all.
try:
    FreezePanes(sheet_id)
except FreezeError as exc:
    print("refused before any call:", str(exc)[:60])

# A count past the tab's rows refuses at PLAN time, with no write issued.
row_count = write_client.read_frozen_panes(spreadsheet_token, sheet_id)["row_count"]
over = dry_run([FreezePanes(sheet_id, rows=row_count + 1)], write_client, spreadsheet_token)
print(over.entries[0].refusal.reason, over.entries[0].refusal.detail[:60])
```

- **Read the frozen state on the READ side too**: `read_tabs_frozen(token, query_sheets(token))`
  gives each tab a `frozen_state` of `not-read` / `none` / `active` / `unavailable` plus a
  `frozen_panes` carrying the counts — the same four-state vocabulary the filter read uses.
- **A freeze changes nothing else.** Values, row/column counts and merges are all untouched, which
  is why this op triggers neither the export style leg nor the merge leg.
- **One batch is one snapshot.** Grow the tab (`AppendDimension`) in one batch and freeze the new
  rows in the next.
- **Freezing every row is allowed** (`rows == row_count`) — it is only `row_count + 1` that fails.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: merge and unmerge cells

**Merging destroys data, and the dry-run enumerates exactly which.** A merge keeps the
**top-left (anchor)** cell's value and discards every covered cell's — so the previewer reads
the range and hands you `lost_values`, cell by cell, before anything is written. Unmerging is
the reverse geometry only: the covered cells become independent **empty** cells, and **no value
is restored** to them (larkdocio does not reconstruct what the merge threw away).

**Merge geometry lives only in the v3 tab query.** A values read cannot see a merge, so the
tab's `merges` array — 0-indexed, **end-inclusive** regions — comes from `query_tabs` (or
`read_sheet_geometry`). Hand it to `dry_run(..., merges=…)` and two disclosures switch on for
free: a value write aimed at a merge-**covered** cell refuses `merged-cell-target`, and an
unmerge that intersects no merge carries a **`no-merge-at-range`** note instead of implying a
dissolve. Re-read the merges between batches — your own merge changed them.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import MergeCells, UnmergeCells, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
tab = write_client.query_tabs(spreadsheet_token)[0]
sheet_id = tab["sheet_id"]

# (a) MERGE — the preview ENUMERATES the values that will be discarded.
plan = dry_run([MergeCells(f"{sheet_id}!B1:C1")], write_client, spreadsheet_token,
               merges=tab["merges"])
loss = plan.entries[0].after
print(loss["anchor"], loss["covered_count"], loss["lost_count"], loss["lost_values"])
merge_log = apply(plan, write_client)
print(merge_log.entries[0].structural["merges_added"])     # re-read AFTER the write

# (b) UNMERGE — re-read the merges first: your own merge just changed them.
merges = write_client.query_tabs(spreadsheet_token)[0]["merges"]
unmerge = dry_run([UnmergeCells(f"{sheet_id}!B1:C1")], write_client, spreadsheet_token,
                  merges=merges)
print(unmerge.entries[0].after["note"])       # covered cells become empty; no value restored
unmerge_log = apply(unmerge, write_client)
print(unmerge_log.entries[0].structural["merges_removed"])

# (c) An unmerge of a range holding NO merge is a harmless NO-OP — not an error, not refused
# (an idempotent unmerge is a legitimate restore step) — and the plan says so rather than
# implying a dissolve. Dry-run only.
noop = dry_run([UnmergeCells(f"{sheet_id}!E9:F9")], write_client, spreadsheet_token,
               merges=write_client.query_tabs(spreadsheet_token)[0]["merges"])
noop_note = noop.entries[0].preview_note
print(noop_note["kind"], noop_note["merges_checked"], noop_note["note"])
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(unmerge_log.applied), "applied,", len(unmerge_log.refusals), "refused")
for entry in unmerge_log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **`MERGE_ALL` is the only merge type, and the other two are REFUSED — not merely untested.**
  Passing `merge_type="MERGE_ROWS"` or `"MERGE_COLUMNS"` raises `MergeTypeError` when you
  *construct* the request, before any call. The reason is not shyness about coverage: the loss
  preview you just read is `MERGE_ALL`'s model, and it was measured **describing those two
  wrongly** — in the library's own words:

  > MERGE_ROWS AND MERGE_COLUMNS ARE REFUSED, and not merely untested: larkdocio's merge loss preview DESCRIBES THEM WRONG. Probed live on a disposable — MERGE_ROWS over a 2x2 produced TWO merged regions, one per row, and BOTH rows' leading cells kept their values; MERGE_COLUMNS is the same fault transposed, one region per column with every column's top cell kept. The shipped preview reports ONE anchor and ONE rectangle, so on that same 2x2 it named a cell as lost that the write KEPT. An over-reported loss on a destructive op is a MIS-DISCLOSURE, so the variants are refused at construction (zero API calls) rather than offered with a preview that cannot be trusted. What to do instead: express the merge you want as MERGE_ALL merges, one per row or per column — a single-row range under MERGE_ROWS is exactly MERGE_ALL, which the same probe confirmed — and each one previews its own loss correctly. Lark itself is strict about the value: a nonsense mergeType, 'merge_rows' and ' MERGE_ROWS ' each answered the generic '90204' with msg 'invalid mergeType' and landed nothing, so nothing is silently repaired here either. Evidence: tests/captures/sheets-merge-variant-probe/captures/01-merge-variant-characterization.json in the source repository.

  So the repair is a loop, not a flag: one `MergeCells` per row (or per column), each previewing
  its own loss correctly.
- **A merge is not authorable in a docx table** (Markdown has no `colspan`), and a merged
  *sheet* range currently renders as a blank cell on read. The write side is the only place
  merge geometry is addressable today.
- **Neither op has a cell-value precondition** (`value_precondition: "none"`) — they are
  geometry, not values — so on a spreadsheet whose `revision` reports a constant `0` a merge
  carries no staleness guard at all. The plan discloses that instead of implying otherwise.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: add a dropdown list rule to a range

A dropdown is a **`dataValidation` rule** on a range, not a cell value: it writes through its
own endpoint, so its plan entry's `write_kind` is `data-validation`, it has **no** value
precondition (there is no `before` value to compare), and it never touches `put_values`. The
encoded wire shape is built for you by `list_rule` — a caller never hand-assembles
`{"dataValidationType": "list", "dataValidation": {...}}`.

**The one caveat is refused at build time.** Turning on `highlight_valid_data` requires a
`colors` array **1:1** with the values; without it Lark answers a generic `90204`
(`WrongRequestBody` — the code says only "your body was wrong", and its `msg` is what names
the cause, so the code alone identifies nothing). The encoder refuses that combination when
you *construct* the request — a typed `DropdownColorsError` — so an unrepresentable rule
cannot reach the wire at all.

```python
from larkdocio.common import init_env
from larkdocio.sheets.rich_encode import DropdownColorsError
from larkdocio.sheets.write_apply import DropdownRuleWriteRequest, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
sheet_id = next(t["sheet_id"] for t in write_client.query_tabs(spreadsheet_token))

rule = DropdownRuleWriteRequest.list_rule(
    f"{sheet_id}!A6:A6", ["Draft", "In review", "Shipped"], multiple_values=False)
plan = dry_run([rule], write_client, spreadsheet_token)
print(plan.entries[0].value_precondition)      # 'none' — a rule has no cell-value before
print(plan.entries[0].after)                   # the encoded rule, exactly as it will be sent
log = apply(plan, write_client)
print(log.entries[0].write_kind)               # 'data-validation'

# The colors caveat is refused when you BUILD the request, not after the write (Lark's own
# answer would be a generic 90204 WrongRequestBody, which names nothing):
try:
    DropdownRuleWriteRequest.list_rule(
        f"{sheet_id}!A6:A6", ["Draft", "Shipped"], highlight_valid_data=True)
    colors_error = "not refused"
except DropdownColorsError as exc:
    colors_error = str(exc)
print(colors_error)
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(log.applied), "applied,", len(log.refusals), "refused")
for entry in log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **`multiple_values=True`** makes it a multi-select. The *cell* that then holds several
  labels is a **rich** cell — write it with `RichCellWriteRequest.multi_select(range, labels)`,
  which is the value-side twin of this rule.
- **larkdocio writes list rules only.** Reading a rule back, updating and deleting one, and
  every non-list validation type are not built — do not plan around them.
- **A LATER COLUMN INSERT WILL MOVE THIS RULE, AND NOTHING WILL WARN YOU.** A rule is attached
  to a range, and `InsertColsAt` shifts the cells that range names — **measured live once**
  (one tenant, one workbook, one insert; the row twin `InsertRowsAt` is **unmeasured, not
  refuted**, and so is what a *delete* does). So a rule written on `A6:A6` today applies
  somewhere else after an insert to its left, and
  **no `preview_note` discloses it** (the previewer has no data-validation read leg to see the
  rule with). Combined with the bullet above, that is the honest position: you can write a
  rule, you cannot read it back, you cannot delete it, and a structural write can move it out
  from under you silently. Keep your own record of which ranges you ruled, and re-issue the
  rule after any insert on that tab. The structural side of this is stated in
  § "Recipe: insert and delete rows and columns (a structural write)", which points back here.
- **The colors you write cannot be read back through larkdocio** — an asymmetry worth knowing
  *before* you plan a verification step around them:

  > A DROPDOWN'S COLORS CANNOT BE READ BACK THROUGH larkdocio. They are written POSITIONALLY as options.colors[] — entry i colours condition value i, which is the only reason the 1:1-length rule that highlightValidData:true enforces matters — but Lark reports them back under a DIFFERENT field, options.colorValueMap (a value-to-colour map, not a positional array), and larkdocio ships no data-validation READ leg at all, so that field appears nowhere in the library. Consequence, plainly: you can set a dropdown's colors and you cannot verify them here — check them in the Lark UI, or keep the colors array you wrote as your own record. The read leg (dataValidation GET/UPDATE/DELETE) is a deliberately deferred rung of its own, not an oversight; what is fixed here is the silence about it.
- **A rule write still goes through the full gate:** mandatory dry-run, non-forgeable plan,
  `stale-sheet` tier 1. Only tier 2 (the value precondition) is absent, and the plan says so.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: add, copy and delete a tab

Tab writes are the one family whose target does not exist yet: **`AddTab` and `CopyTab` mint a
new `sheetId`, and you only learn it from the reply** (`log.entries[i].structural["new_sheet_id"]`).
It is never the title — the title is what *you* chose; the `sheet_id` is what every range,
read and later write must use. So a chain that creates a tab and then writes into it is
**three batches, not one**: each one's plan is built against ids that exist when it is planned.

**A tab delete is the most destructive op on the surface**, so the previewer snapshots the
removed tab's **whole identity** (title, index, geometry, merges) at plan time and carries it
into the apply-log — a consumer could recreate the tab from the log alone. The tab's *contents*
are not snapshot: a delete is not undoable, and the identity record is the audit trail, not a
backup.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import AddTab, CopyTab, DeleteTab, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")

# (a) ADD — the new tab's sheet_id comes back in the apply-log, not from the title.
#     NO `index` PLACES THE TAB FIRST. It does not append; see the note under this block.
add_log = apply(dry_run([AddTab(title="Q4 Draft")], write_client, spreadsheet_token),
                write_client)
new_sheet_id = add_log.entries[0].structural["new_sheet_id"]
print(new_sheet_id)                       # an opaque id, e.g. '0b8s2f' — never 'Q4 Draft'

# (a2) APPEND — the idiom, because omitting `index` is NOT it. Read the order back, count
#      the tabs, and NAME the position: index=len(tabs) puts the new tab last (measured).
tabs_after_add = write_client.query_tabs(spreadsheet_token)
print([t["title"] for t in tabs_after_add][0])     # 'Q4 Draft' — it went FIRST, not last
len_tabs = len(tabs_after_add)
appended_log = apply(
    dry_run([AddTab(title="Q4 Appendix", index=len_tabs)], write_client, spreadsheet_token),
    write_client)
appended_sheet_id = appended_log.entries[0].structural["new_sheet_id"]
print([t["title"] for t in write_client.query_tabs(spreadsheet_token)][-1])  # 'Q4 Appendix'

# (b) COPY — a copy duplicates the source's content INCLUDING its merges, and mints another
# new id. Planned fresh, because the id it points at only came into existence in (a).
copy_log = apply(
    dry_run([CopyTab(source_sheet_id=new_sheet_id, dest_title="Q4 Draft (copy)")],
            write_client, spreadsheet_token),
    write_client)
copy_sheet_id = copy_log.entries[0].structural["new_sheet_id"]
print(copy_sheet_id, copy_log.entries[0].structural["copied_merges"])

# (c) DELETE — the identity snapshot is taken at PLAN time, so the log can describe what is
# gone. Deleting is not undoable; this is the record, not a backup.
delete = dry_run([DeleteTab(sheet_id=copy_sheet_id)], write_client, spreadsheet_token)
removed_identity = delete.entries[0].after["removed_identity"]
print(removed_identity)                   # title / index / row_count / column_count / merges
delete_log = apply(delete, write_client)
print(delete_log.entries[0].structural["result"],
      delete_log.entries[0].structural["removed_identity"]["title"])
# READ THE LOG. A refused entry raises by default; this is the reading either way.
print(len(delete_log.applied), "applied,", len(delete_log.refusals), "refused")
for entry in delete_log.refusals:
    if entry.refusal is not None:               # the reason and the detail, per entry
        print("refused:", entry.refusal.reason, entry.refusal.detail)
```

- **`AddTab(title=…, index=…)`** places the new tab at a position, and **omitting `index`
  places the new tab FIRST, not last.** This guide claimed through 1.34 that leaving `index`
  out would append the tab, and that sentence was false: measured live twice (a field exercise, and re-measured for
  this release on a disposable — a workbook whose tabs read `[(0,'Sheet1'), (1,'Rollout')]`
  came back `[(0,'zz-no-index'), (1,'Sheet1'), (2,'Rollout')]` after an `AddTab` with no
  `index`). **The behaviour is unchanged and is not going to change** — code already written
  against it keeps working; what changed is the sentence. **To append, say so** —
  `index=len(write_client.query_tabs(spreadsheet_token))`, which is step (a2) of the code
  above and was measured landing last in the same run.
  `index` here is the same 0-based target **position** `ReorderTab` takes, so `index=0` is
  explicitly first and `index=len(tabs)` is explicitly last — count the tabs, do not omit the
  argument and hope. **Reordering, retitling and hiding an existing tab** are the next recipe.
- **A tab op has no A1 range and no value precondition**, like merge and structural: tier 2 of
  `stale-sheet` does not apply, and the plan discloses that.
- **`sheet_id` vs title, one more time:** `CopyTab` takes the **source's `sheet_id`** and a
  **destination title**. Passing a title where the id belongs is the same trap the sheets-write
  handshake opens with.

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

### Recipe: reorder, retitle and hide a tab (a tab-presentation write)

**These three change how a tab is *presented*, never what it holds** — no cell moves, the grid
does not change, and merges are untouched. They ride the same `sheets_batch_update` call the
add/copy/delete ops use (nothing new was added to the client), and they are read back through
the same tab query, so each entry records what the tab looks like **after** the write.

**`index` is a target POSITION and it is 0-based.** `ReorderTab(sheet_id, index=0)` makes the
tab first; the tabs it passes close the gap. It is not a delta and not a swap. An index past the
last tab is **refused at plan time**, and the reason matters: Lark *accepts* such a request and
silently clamps the tab to the end, so the position you asked for is not the position you would
get. A reorder to the position the tab already holds is accepted and disclosed as a no-op —
Lark does not even move the spreadsheet revision for it, so nothing downstream would record it.

**Retitling breaks title→`sheet_id` joins, and the plan says so.** The `sheet_id` is
**unchanged** by a rename — that is the point: the id is the stable handle and a title never was
one. Every entry that really renames a tab carries a `retitle-breaks-title-joins` note naming
both titles. A title another tab already holds is refused at plan time; the comparison is exact
and **case-sensitive**, exactly as the API compares, so `gamma` beside `Gamma` is a legal
rename.

**Hiding is not protecting and not removing, and the plan says that too.** A hidden tab is
invisible in the Lark UI and **still fully readable through this library**: a values read of it
returns every cell and a Markdown read still emits the whole tab. So a hide carries a
`hidden-tab-fidelity` note. Hiding the **last visible** tab is refused at plan time (a
spreadsheet cannot hide every tab, and Lark's own answer for it is a bare `server error`).
Hide and show are idempotent.

```python
from larkdocio.common import init_env
from larkdocio.sheets.write_apply import (
    ReorderTab,
    RetitleTab,
    SetTabVisibility,
    TabPresentationError,
    apply,
    dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient

init_env(".env")            # FIRST: from_write_credentials() reads os.environ
spreadsheet_token = "YOURSPREADSHEETTOKEN"
write_client = SheetsWriteClient.from_write_credentials(domain="larksuite.com")
tabs = write_client.query_tabs(spreadsheet_token)
sheet_id = tabs[-1]["sheet_id"]                  # the LAST tab, by id and never by title

# (a) REORDER — move it to the front. index is a target position, 0-based.
plan = dry_run([ReorderTab(sheet_id, index=0)], write_client, spreadsheet_token)
print(plan.entries[0].structural["semantic"])
log = apply(plan, write_client)
print(log.entries[0].to_dict()["outcome"], log.entries[0].structural["observed"])
print(log.entries[0].structural["verified_by"])          # 'v3-tab-query-leg'

# (b) RETITLE — the id does not change, so any cached title->id join is now stale.
retitle = dry_run([RetitleTab(sheet_id, title="Q3 actuals")], write_client, spreadsheet_token)
note = retitle.entries[0].preview_notes[0]
print(note["kind"], note["old_title"], note["new_title"], note["sheet_id_unchanged"])
retitle_log = apply(retitle, write_client)
print(retitle_log.entries[0].structural["observed"]["title"])

# (c) HIDE — invisible to a viewer, still readable here. The plan discloses exactly that.
hide = dry_run([SetTabVisibility.hide(sheet_id)], write_client, spreadsheet_token)
hide_note = hide.entries[0].preview_notes[0]
print(hide_note["kind"], hide_note["hidden"])
hide_log = apply(hide, write_client)
print(hide_log.entries[0].structural["observed"]["hidden"])

# the hidden tab's data is still there, and still readable through this library
hidden_values = write_client.read_values(spreadsheet_token, f"{sheet_id}!A1:A1")
print(hidden_values)                                     # the hide changed nothing here

# ...and show it again (hide/show are idempotent).
show_log = apply(dry_run([SetTabVisibility.show(sheet_id)], write_client, spreadsheet_token),
                 write_client)
print(show_log.entries[0].structural["observed"]["hidden"])

# An empty title cannot even be built.
try:
    RetitleTab(sheet_id, title="")
except TabPresentationError as exc:
    print("refused before any call:", str(exc)[:60])

# A position past the last tab refuses at PLAN time, with no write issued.
over = dry_run([ReorderTab(sheet_id, index=len(tabs))], write_client, spreadsheet_token)
print(over.entries[0].refusal.reason, over.entries[0].refusal.detail[:60])
```

- **Read the visibility back from `query_tabs`**: each tab carries `hidden` (`True` / `False`, or
  `None` when the payload did not say — never silently "visible"). It is the only cheap read that
  carries it; the `metainfo` read does not report visibility at all.
- **A presentation write changes nothing else.** Values, row/column counts and merges are all
  untouched, which is why this op triggers neither the export style leg nor the merge leg.
- **Reorder by id, always.** A title is not a handle, and after (b) any code that addressed this
  tab by name is addressing a tab that no longer answers to it.
- **One batch is one snapshot.** A reorder and a retitle of the same tab may be queued together;
  add a tab in one batch and present it in the next.

---

**The read-back law applies here** — § "The read-back law — a green apply is not a receipt".

## Deep links — what a Lark URL points at, what you can mint, and what you cannot

A whole-document URL is the province of `larkdocio.common.url.validate_download_url`, which
answers "what surface reads this" as a coarse `(domain, type, token)` tuple. A **deep** link
points *below* a document — at a section, a spreadsheet tab or cell, or a single Base record —
and its meaning lives in the fragment or query that tuple drops. Four such grammars have been
observed from the Lark UI, and `larkdocio.common.url.parse_deep_link(url)` recognises them,
returning a typed address that carries every opaque part **unaltered**:

- `…/docx/<doc>#share-<token>` → `DocAnchor(doc_token, share_token)`
- `…/sheets/<tok>?sheet=<id>` → `SheetAnchor(spreadsheet_token, sheet_id, …)` (a tab)
- `…/sheets/<tok>?sheet=<id>&rangeId=<id>_<opaque>&rangeVer=<n>` → `SheetAnchor(…, range_id, range_ver)` (a cell/range)
- `…/record/<token>` → `RecordAnchor(record_token)`

Anything else — including a plain document/spreadsheet/Base URL with no fragment or query —
returns `NotADeepLink(url)`: the parse never guesses and never returns a half-filled anchor.

**The links this library MINTS are deliberately not the links it PARSES, and the clause above
is not what excludes them.** `parse_deep_link` recognises four **UI-observed** grammars — the
four listed above, each seen pasted out of the Lark client. The three grammars larkdocio itself
mints are *not* among them: a bare `#<block_id>` fragment from `docx_block_url`, an
`?edition_id=<version token>` query from `docx_edition_url`, and a `?table=&view=[&record=]`
query from the Base builders `table_url` / `view_url` all answer **`NotADeepLink`**,
measured, even though each plainly carries a fragment or a query — so the *"no fragment or
query"* exclusion above does not cover them and a reader must not conclude it does. The reason
is the parser's own rule and it is preserved: a grammar is recognised because it was
**observed from the UI**, not because this library can build the string. Round-tripping your
own minted link through the parser is therefore a refusal by design, not a bug to report.
The Base `?table=&view=` form is the one where that reason has visibly aged: it was excluded
as *unverified* until 2026-08-17, when it was clicked and found to navigate. The exclusion
still stands, and now on its honest ground — extending the parse would move a shipped typed
return value for an input consumers already pass, which is a change of its own, not a side
effect of new evidence.
**Parsing claims nothing about reachability.** An anchor is an address, not a capability: a
`share_token` cannot be fetched and a `rangeId` cannot be minted or resolved (see below). What
the parse gives you is lossless *carriage* — exactly what an agent maintaining a document full
of human-pasted links needs.

**Only Lark-family hosts, over `https`.** `parse_deep_link` applies
the same host and scheme policy as `validate_download_url`: 0..N subdomain labels
before `feishu.cn` or `larksuite.com`,
plus the opt-in `allow_host` — and over `https` only. Anything else is `NotADeepLink`, without
exception: **a foreign host even over `https`, and plain `http` anywhere**, including on a real
Lark host. The check runs *before* any grammar is tried, so
`https://evil.example.com/record/<token>` is refused rather than reported as a record address —
a typed anchor never carries a token that came from a URL which was not a Lark URL. The
`allow_host` opt-in widens which **hosts** count as Lark-family; it never widens the scheme.

**Full token, or refuse — a token is never truncated.** A token is an unbroken run of letters
and digits filling its **whole** path segment. If the token region of a URL carries anything
else — a hyphen, an underscore, a dot, a space — the URL is refused **whole**:
`validate_download_url` raises `ValueError` naming the region it refused, and `parse_deep_link`
returns `NotADeepLink(url)`. It is never shortened to the leading run. That applies uniformly to
every grammar in the family — doc, spreadsheet, Base, record and Drive folder — because a
truncated token looks exactly like a real one and would become a lookup for a document that does
not exist, or worse, one that does. The rule is about the **token region only**: the opaque
tails a deep link carries — the `share-` fragment, `sheet`, `rangeId`, `rangeVer` — are still
carried byte-for-byte, unvalidated, exactly as they arrived.

```python
from larkdocio.common import validate_download_url

try:
    validate_download_url("https://your-domain.larksuite.com/docx/Ab-c_1")
except ValueError as refusal:
    assert "Ab-c_1" in str(refusal)   # named, not silently shortened to "Ab"
```

The deep-link side answers the same way in its own currency: the same URL with a `#share-…`
fragment is `NotADeepLink`, not a `DocAnchor` holding a token nobody pasted.

### The mintable deep links — a spreadsheet tab, a docx block, and a named edition

`larkdocio.sheets.tab_url(sheet_url, sheet_id)` builds the click-proven
`<tenant-host>/sheets/<spreadsheet_token>?sheet=<sheet_id>` and makes **zero API calls**. The
tenant host is an **input**: it is read off the sheet's own URL (the thing you already hold),
never derived from the API domain — a working link lives on a tenant subdomain the API domain
cannot produce — and never invented. A missing host is a refusal, not a default.

`larkdocio.common.docx_block_url(doc_url, block_id)` is its docx twin, under the same rules:
it builds `<tenant-host>/docx/<doc_token>#<block_id>` from the document's own URL and a block
id the reader already emits, makes **zero API calls**, and refuses a hostless URL rather than
defaulting one. What that link does — and, just as importantly, how far that is known — ships
with the function:

> A docx block link (`…/docx/<doc>#<block_id>`) IS mintable, offline: `docx_block_url(doc_url, block_id)` builds one from the document's own URL and a block id the reader already emits, and makes zero API calls. Here is the edge of the evidence, so the claim is never read wider than what was measured. The bare fragment was clicked on 2026-08-10 in the Lark WEB client, on one tenant, against all six block kinds tried: heading1, heading2, paragraph, table, bullet and code. Every one of them anchors — a heading, paragraph or bullet target is jumped to, while a table or code target is moved to with a momentary highlight, which is how those blocks show a selection. The `?blockId=<block_id>` query form was clicked in the same sitting and does nothing at all. UNMEASURED, and therefore neither refuted nor supported: the mobile client, the desktop app client, wiki-wrapped documents (`…/wiki/<node>`, which this function refuses rather than guess at), and any other tenant. Whether a link scrolls is a rendering behavior of the Lark client, so no API call can widen this measurement — only another click can.

```python
from larkdocio.common import docx_block_url

link = docx_block_url(
    "https://your-domain.larksuite.com/docx/Example300147d45d30d8297a47",
    "doxlgExampled71529fa60d41c2",
)
assert link.endswith("#doxlgExampled71529fa60d41c2")

# The near-miss spelling is refused, not built: `#share-<block_id>` navigates nowhere and
# lies about deleted content, so it can never come out of this function.
try:
    docx_block_url(link.split("#")[0], "share-doxlgExampled71529fa60d41c2")
except ValueError as refusal:
    assert "has been deleted" in str(refusal)
```

**And a third, clicked on exactly one client and labelled so: the named-edition link.**
`larkdocio.common.docx_edition_url(doc_url, version_token)` builds
`<tenant-host>/docx/<doc_token>?edition_id=<version_token>` from the document's own URL and a
version token the versions family returned. It is fenced exactly like its neighbour — a
hostless, non-`https`, non-`/docx/` or wiki-wrapped URL is refused, not defaulted — and it
makes **zero API calls**. What travels with the function, rather than being left for you to
discover, is exactly how far the claim reaches:

> A docx named-edition link (`…/docx/<doc>?edition_id=<version token>`) is mintable offline — `docx_edition_url(doc_url, version_token)` builds one from the document's own URL and a version token, and makes zero API calls — and it ships click-verified — the `?edition_id=` grammar was clicked on 2026-08-11 in the Lark WEB client, on one tenant, and it opened the named version. Here is the edge of the evidence, so the claim is never read wider than what was measured. The click was made against a harness-created two-paragraph document whose two states were proven to differ AT THE API LEVEL first — a read pinned at the version's recorded revision returned the first paragraph only, while a head read taken in the same sitting returned both — so a browser showing one state could not be an accident of the fixture. What was seen: through the edition URL the document showed STATE ONE only, and Lark's own UI labelled that view an older version; through the control URL (the plain document URL, unmodified) it showed both paragraphs, head. MEASURED: the QUERY half, by that click; and the PATH half, `https://<tenant host>/docx/<doc token>`, which is the document's URL as Lark itself reports it (the drive metas/batch_query verb asked `with_url: true`, 2026-08-11), and it is character-for-character the grammar `docx_block_url` already mints; the version token is Lark's own, returned by the versions family. UNMEASURED, and therefore neither refuted nor supported: the mobile client, the desktop app client, wiki-wrapped documents (`…/wiki/<node>`, which this function refuses rather than guess at), any other tenant, and any non-web client. Whether such a link opens the named version is a rendering behavior of the Lark client, so no API call can widen this measurement — only another click can. Separately, and unchanged by the click: no API route resolves an edition token to CONTENT — the versions family answers no url of any kind, and an edition token resolves to nothing — so keep recording the (name, token, revision) triple at creation time, because that pairing is what a pinned historical read actually runs on.

Note the one asymmetry with the block link: because this helper adds a query of its own, any
query or fragment already on the URL you pass in is **dropped**. A `?from=space` does not
survive.

```python
from larkdocio.common import docx_edition_url

edition_link = docx_edition_url(
    "https://your-domain.larksuite.com/docx/Exampled24cabecc0bbfb9e5fa3",
    "kb1v8q",
)
assert edition_link.endswith("?edition_id=kb1v8q")

# Your own query does not survive: the link is rebuilt from the host and the token alone.
assert "from=space" not in docx_edition_url(
    "https://your-domain.larksuite.com/docx/Exampled24cabecc0bbfb9e5fa3?from=space#frag",
    "kb1v8q",
)
```

None of these three helpers reaches an endpoint, so none needs a credential and none adds a
permission requirement: they are string builders over what you already hold.

### The links you cannot mint or fetch — stated plainly so you do not re-run the search

**Docx `#share-` section anchors are UI-only — and the near-miss spelling of one is hazardous.**

> A docx section link (`…/docx/<doc>#share-<token>`) is UI-only: this library cannot mint one and cannot fetch one. The fragment is a share token the Lark web client mints when a person copies a section link; it is NOT a block id (an exhaustive check of a real document's every block found no match, and the block-get endpoint returns not-found for the share token while returning the block for a real id), and no docx share or permalink endpoint exists to turn it into anything the API will accept. This is not a permissions problem: the data does not exist in the API at all, so no grant would change either answer. That verdict is about the `share-` grammar and nothing wider: the OTHER docx fragment grammar — a bare `…/docx/<doc>#<block_id>` — IS mintable, and is a separate measured claim (see `docx_block_url`). Do not try to bridge the two. The obvious guess, `…/docx/<doc>#share-<block_id>`, navigates nowhere and shows a toast reading "The selection content has been deleted" about content that is perfectly intact — observed on every block kind tried, and the same lie-class as the sheets cell-link toast: a reader who sees it will file a data-loss bug against your document or against this library. To point at a passage in band, emit the block ids with `emit_block_ids` and mint the bare-fragment link with `docx_block_url` — a share URL is not available.

**Sheets cell/range links are UI-only, and guessing one is hazardous.**

> A sheets cell or range link is UI-only, and guessing one is hazardous. The `rangeId` in `…?sheet=<id>&rangeId=<id>_<opaque>&rangeVer=<n>` is opaque and versioned — a stored server-side object, not a computed address — and no endpoint in the Sheets surface mints, lists or resolves one. The obvious workaround makes it worse: a guessed `range=<A1>` URL half-works. It lands on the right tab and then shows a toast reading "The cell was deleted" about cells that are perfectly intact — identically for any coordinate, stably across refreshes. Do not build such a URL: a reader who sees that toast will file a data-loss bug against your sheet or against this library. This is not a permissions problem: the data does not exist in the API at all, so no grant would change either answer. Tab-level links ARE mintable — see `larkdocio.sheets.tab_url` — but cell-level ones are not. WHAT THIS IS AND IS NOT ABOUT: it is about a URL that POINTS AT a cell, and it is not about putting a link INSIDE one. Writing a cell whose value is a labeled clickable link SHIPS and works — `RichCellWriteRequest.hyperlink(range, link, text=…)`, worked through in the guide's section `Recipe: write a hyperlink and a styled run into a cell`. This paragraph is easy to misread as a verdict on that question, so the two are separated here rather than left adjacent.

---

## Reading the shipped documents programmatically

Five documents written for a consumer ship inside the wheel, and **each one has an accessor** —
none of them requires `importlib.resources`, a `vendor/` drop, or a source checkout to read:

```python
import larkdocio

index = larkdocio.guide()            # this document's SECTION INDEX — the default answer
text = larkdocio.guide(full=True)    # this document in full, straight from the wheel
setup = larkdocio.lark_setup()       # the Lark-application walkthrough: app, scopes, reach
brief = larkdocio.writer_brief()     # the writer's long-form dialect brief
notes = larkdocio.release_notes()    # what changed THAT AFFECTS YOU — read before re-pinning
log = larkdocio.changelog()          # the project's changelog, one entry per release
assert "Capability matrix" in text and len(index) < len(text)
assert all(doc.strip() for doc in (setup, brief, notes, log))

# and they are listed together, so dir() is not the discovery mechanism:
for label, entry in larkdocio.capabilities(full=True)["docs"].items():
    print(label, "->", entry["resource"])
```

Each accessor reads the packaged resource via `importlib.resources`, so it works identically
from a source checkout and from an installed/vendored wheel. **`lark_setup()` is the one to
read FIRST if nothing works yet** — it is the ten minutes before a first call (create the app,
grant the starter scope, share the documents onto it, prove one read), and none of those three
facts is something this library can do for you. Which of the last two you want:
`release_notes()` is the **filtered** view written to stated relevance criteria (public
symbols, observable behavior changes, refusals, dependency pin moves, known limitations);
`changelog()` is the project's changelog: one entry per release, and a pointer to the release
notes for earlier versions.

### Reading ONE section of this guide

This document is large — hundreds of KB as one string — which is why `guide()` with no argument
answers with the **index** rather than the document, and why it takes a **section**: you ask for
the one part you need instead of holding all of it. The whole document is still one explicit
argument away (`guide(full=True)`), byte for byte.

```python
import larkdocio
from larkdocio import guide_sections

# The index: one row per heading — the heading itself, the slug that also names it, and the
# level, which is what tells you whether a row contains others. Names only, never section
# text, so reading the index to choose is cheap.
index = guide_sections()
assert all(set(row) == {"heading", "slug", "level"} for row in index)
assert {row["level"] for row in index} == {2, 3}

# Ask for a section by its slug, or by its heading exactly as it appears in the document.
# Both spellings are matched case-insensitively, so these are the same request:
by_slug = larkdocio.guide(section="recipe-read-a-sheet-to-markdown")
by_heading = larkdocio.guide(section="RECIPE: read a sheet to Markdown")
assert by_slug == by_heading
assert by_slug.startswith("### Recipe: read a sheet to Markdown")

# A parent section hands you its children with it, so a task name is every recipe for that
# task at once — which is what the `## Task — …` groups are for:
assert "### Recipe: read a sheet to Markdown" in larkdocio.guide(
    section="task-read-something-out-of-lark-into-markdown")

# The same index rides on the capability registry, beside the accessor that reads the file:
assert larkdocio.capabilities(full=True)["docs"]["guide()"]["sections"] == list(index)

# A name this document has no heading for raises ValueError, and the message names every
# section it does have — so recovering from a wrong guess costs no second call.
try:
    larkdocio.guide(section="recipies")
except ValueError as refusal:
    assert "recipe-read-a-sheet-to-markdown" in str(refusal)

# With no argument you get the index — names only, and it names your next call.
assert 'larkdocio.guide("recipe-read-a-sheet-to-markdown")' in larkdocio.guide()
assert "larkdocio.guide(full=True)" in larkdocio.guide()

# And with that explicit argument you get the whole document, byte for byte.
assert larkdocio.guide(full=True).endswith("\n")
assert len(larkdocio.guide()) < len(larkdocio.guide(full=True))
```

**What comes back.** The heading line itself, then that section's text through the character
before the next heading of the **same or higher level** — or the end of the document when none
follows. So a `##` name hands you that whole section *including* its `###` children, while a
`###` name hands you just that one and stops at the next `###` or the next `##`, whichever
comes first. The bytes are this document's own: nothing is stripped, added or re-wrapped.

**Naming a section.** The **slug** is the heading with backticks dropped, lower-cased, and every
run of other characters collapsed to a single `-`; the **heading text** works just as well. Both
are compared case-insensitively and surrounding spaces are ignored. That tolerance is
deliberate: a heading that is later only re-cased or re-punctuated keeps answering to the name
you already wrote down, and a restructure that renames a section outright is announced in
`release_notes()`.

**Where the index lives.** `guide_sections()` is exported from the top level — note that
`larkdocio.guide` is the accessor *function*, so there is no module attribute to reach it
through — and `capabilities(full=True)["docs"]["guide()"]["sections"]` carries the same rows for a caller
already reading the registry. Both are derived from this document's own headings every time they
are called, so neither can fall behind it.

### Reading ONE section of the other four documents

`writer_brief()`, `release_notes()`, `changelog()` and `lark_setup()` take the SAME `section`
this guide does, through the same seam — a `<accessor>_sections()` index beside each one, and a
`capabilities(full=True)["docs"][...]["sections"]` row for every one of them, not only the guide's:

```python
import larkdocio

# The writer brief is indexed like this guide — level-2 AND level-3 headings — because its
# own census supports it: it carries headings at BOTH levels and no two slugs collide.
# No count is quoted here on purpose — derive it, do not read it:
#     collections.Counter(r["level"] for r in larkdocio.writer_brief_sections())
brief_index = larkdocio.writer_brief_sections()
assert {row["level"] for row in brief_index} == {2, 3}
one_brief_section = larkdocio.writer_brief(section=brief_index[0]["slug"])
assert one_brief_section.startswith("#" * brief_index[0]["level"] + " " + brief_index[0]["heading"])

# The release notes and the changelog are each indexed at level-2 ONLY — one row per
# `## [X.Y.Z] — date` release — because both repeat the SAME `###` subsection headings under
# every release ("New capabilities", "Added", ...), and naming those individually would
# collide on every call. A release name hands you the whole release, subsections included,
# by the same boundary rule:
notes_index = larkdocio.release_notes_sections()
assert {row["level"] for row in notes_index} == {2}
latest = notes_index[0]["slug"]                       # newest release, document order
one_release = larkdocio.release_notes(section=latest)  # "what changed in THAT release"
assert one_release.startswith("## " + notes_index[0]["heading"])

log_index = larkdocio.changelog_sections()
assert {row["level"] for row in log_index} == {2}
assert larkdocio.changelog(section=log_index[0]["slug"]).startswith("## ")

# A release is addressable by its BARE VERSION as well — the spelling you already have in
# your pin. The heading carries the release date, so both the heading and the slug derived
# from it carry it too; the bare version is matched after those two exact spellings miss,
# and hands back the same bytes:
version = notes_index[0]["heading"].split("]")[0].lstrip("[")
assert larkdocio.release_notes(section=version) == one_release
assert larkdocio.changelog(section=version).startswith("## ")

# The Lark-application walkthrough is indexed like this guide and the writer brief — level-2
# AND level-3 — because its census supports it: its steps are `##` and its operator-observed
# console walls are `###`, with no slug collision, so BOTH levels are already load-bearing
# here (derive the census the same way: Counter over larkdocio.lark_setup_sections()):
setup_index = larkdocio.lark_setup_sections()
assert {row["level"] for row in setup_index} <= {2, 3}
one_step = larkdocio.lark_setup(section=setup_index[0]["slug"])
assert one_step.startswith("#" * setup_index[0]["level"] + " " + setup_index[0]["heading"])

# Naming a section wrong raises ValueError naming every one this document actually has —
# the same refusal shape `guide(section=...)` uses, pointing at the RIGHT index helper:
try:
    larkdocio.release_notes(section="not a real release")
except ValueError as refusal:
    assert "release_notes_sections" in str(refusal)

# And every one of these rides on the registry, beside the accessor that reads the file:
for label, entry in larkdocio.capabilities(full=True)["docs"].items():
    assert "sections" in entry, label
```

**Why the indexed levels are not the same for all five.** The heading levels a document is
indexed at are a fact about that one document's own structure, measured once rather than
guessed — reusing `(2, 3)` where the census supports it (the guide, the writer brief, the
Lark-application walkthrough) and narrowing to `(2,)` where it does not (the release notes,
the changelog), so that "a slug
collision raises" — the same refusal shape on a genuine duplicate — never fires merely
because the same subsection title appears under every release.
