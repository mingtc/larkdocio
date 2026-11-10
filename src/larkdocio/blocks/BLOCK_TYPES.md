# Handler-authoring guide — `larkdocio/blocks/`

*How to add or change a block handler in this package. This file is the **authoring guide**;
it deliberately carries **no per-type status matrix**.*

> **To answer "is type N handled, what does it emit, and is that lossy?" — read the shipped
> projection**, which is reachable from any installed copy of this package:
>
> ```python
> import larkdocio
> support = larkdocio.capabilities(full=True)["surfaces"]["docx-read"]["block_read_support"]
> {row["name"]: (row["handled"], row["lossiness"]) for row in support["types"]}
> ```
>
> Each row answers all three questions — `handled` (the live handler registry), `emits` (the
> Markdown the reader produces) and `lossiness` (one state from `support`'s own shipped
> `lossiness_vocabulary`) — and `support["unlisted_type"]` answers for a block type Lark adds
> later. That projection is where a reader who has this package but not this repository gets
> the answer; **this file only explains how the machinery works and how to extend it.**
>
> Maintainers editing the matrix: the authoring surface for those rows is `BLOCKS.md`,
> **in the source repository**'s root, whose cells the projection is pinned against in both directions.
>
> **The block handlers in this package are read-side only (Lark docx → Markdown);** the
> writeback apply engine lives separately in [`larkdocio/write/`](../write/README.md) (see
> its README). The legacy in-handler write path was removed as too
> lossy — writeback is now a separate, `block_id`-addressed, element-level engine, not a
> per-handler concern.

---

## How the registry works

`larkdocio/blocks/__init__.py` holds a `BLOCK_REGISTRY: Dict[int, BlockHandler]`. Each handler
registers itself with the `@register_block(<type_int>)` decorator:

```python
from larkdocio.blocks import register_block
from larkdocio.model import DividerNode, Node

@register_block(22)  # Divider
def handle_divider(parser, b, indent_level) -> Node:
    return DividerNode()  # the renderer emits "---\n"
```

At parse time, `larkdocio/read/parser.py` looks up `block.block_type` in the registry and calls
the handler. If there is **no** registered handler it logs — and drops the block's OWN content
while rendering its children transparently (see the unknown-type fallback below):

```
Unknown block type <N> (block_id=..., parent_id=..., children=<count>) — content may be missing from output.
```

That warning is no longer the only account of it: the same decision is also reported as **data**,
on the download's returned value — `result.unknown_block_types`, one entry per distinct
unmodelled type with its counts, written by the same recorder that emits the line above (so the
two cannot disagree). A caller asking *"which types did this document use that you do not
model?"* reads that key rather than parsing the sentence.

So **"supported" == "has a registered handler."** An unhandled type is summarized as a warning;
its own attributes are dropped, but its **children are rendered transparently** so an unknown
*container* surfaces its subtree instead of vanishing (a *leaf* unknown emits nothing). That is
the `not-handled` state the shipped projection reports. Whether such a type is *deliberately*
unsupported or simply not-yet-built is an intent distinction the maintainers' matrix records
(`BLOCKS.md`, **in the source repository**) and runtime does not — both warn identically.

### Eager registration is mandatory

The decorators only run when their module is **imported**. `__init__.py` imports every handler
module eagerly (`from . import text`, `from . import headings`, …) so the registry is complete
immediately after `import larkdocio.blocks` — **without** anyone calling `get_registry()`. A
handler module that is *not* eagerly imported registers late (or never), which is a latent bug.
`tests/test_registry.py` guards this: it asserts every supported type is present right after a
fresh import, with no `get_registry()` call.

### The handler contract

A handler has the signature:

```python
def handler(parser: "Parser", block: Any, indent_level: int) -> Node: ...
```

- **`parser`** — the live `Parser`. Useful members: `parser.block_map` (id → block, for
  resolving children), `parser.config`, `parser.img_tokens` / `parser.board_tokens` (append a
  token to queue an asset for download), and `parser.parse_docx_node(child, indent_level)` /
  `parser._child_nodes(block, indent_level)` to recurse children to typed NODES — the way
  EVERY family recurses (R-S4 flipped the last two, grid + source_synced; R-S5 then deleted the
  old string-boundary delegate, so `parse_docx_node` is now the **sole** recursion primitive).
- **`block`** — the SDK `Block`. Read its payload via the type's field (`block.text`,
  `block.code`, `block.callout`, …). Unset typed fields are `None` (SDK quirk), so guard with
  `getattr(...)` / truthiness.
- **`indent_level`** — current nesting depth. **The base parser does not auto-recurse**: a
  handler is responsible for recursing its own children (see the recursion/indent contract
  below). A handler that ignores `block.children` drops nested content.
- **Return** a typed **model node** (see the model-node contract below). If a field can't be
  represented, prefer a **visible marker** over a silent drop (see `text.py`'s
  `[unsupported inline: …]` markers).

### Model-node contract (T2)

An earlier migration (T2) moved every handler from returning Markdown **strings** to constructing typed
**model nodes** (`larkdocio/model/nodes.py`) that a separate renderer serializes. The registry
division is unchanged — **one handler module per block family; handlers build the node; the
renderer (`larkdocio/model/renderer.py`) serializes per node type.** A handler now **returns a
node** (only). Nodes are dumb typed data (no behavior, no renderer import). Through the migration
the LD-024 **strangler shim** also tolerated a legacy string return (wrapping it in a `RawBlock`);
that string arm was **removed in LD-032** once every family returned nodes, so a `Node` is now the
only accepted return type (`BlockHandler` is typed `Callable[..., Node]`).

### The recursion / indent contract

The parser spine (`read/parser.py`) has **one recursion primitive** — every handler recurses its
children through it, and the renderer alone turns the resulting node tree into Markdown:

- **`parser.parse_docx_node(child, indent_level) → Node`** — produces the child's typed node.
  Every parent node carries **real child NODES**: `page(1)`, the **list family** — bullet 12 /
  ordered 13 / todo 17 — the recurse-at-0 containers **heading** 3..11, **callout** 19 and
  **quote_container** 34, the **table family** — table 31 / table_cell 32, and the **own-depth
  recursers grid** 24 and **source_synced** 49 (R-S4 flipped these last two); the document root
  and the whole document object below it is a node tree the renderer descends.
  `parser._child_nodes(block, indent_level)` is the shared loop over `block.children` that calls
  it. A **missing** block (a dangling `child_id` resolving to no block) yields an empty `RawBlock`
  sentinel; an **unregistered** type logs the `Unknown block type N …` warning and yields an
  `UnknownBlockNode` carrying its children (built at the block's own depth) that the renderer emits
  transparently — no markup of the unknown block's own, the `view`/`grid` precedent (LD-045,
  Decision e). Does **not** apply the list-item indent tab (the renderer's list-item serializer
  owns that).

**Serializing to Markdown** is the renderer's job alone — `render(node, depth) → str`. R-S5
(LD-038) deleted the transitional string-boundary delegate the string-carrying families had
needed; there is no longer a separate string recursion entry.

**Who indents:** only list items (12 bullet / 13 ordered / 17 todo) carry a leading indent of
`depth` hard tabs — and the **list-item serializer** (`_list_item` in `model/renderer.py`) owns
that tab, applying it via the `depth` threaded through `render(node, depth)` (keyed on the node
kind, no longer prepended at the string boundary keyed on block_type). **Every other serializer
ignores depth for its own line** — so a block-level child (a table/code/divider nested under a
list item) still renders at column 0; a tab there would corrupt it into an indented code block
(the guard's whole reason). **Who recurses at what depth:** the list-item serializer renders each
child node one level deeper (`depth + 1`), mirrored at parse time by the handler building child
nodes at `indent_level + 1`; page and every other container recurse at their own level
(page/heading/callout/quote_container/table/table_cell at 0, grid/source_synced at `indent_level`).
**Who separates / owns trailing newlines:** each block node's serializer emits its own trailing
newline(s); a container concatenates its child strings verbatim (each child already carries its
newline). See the contract block at the top of `read/parser.py` for the authoritative statement.

**List-breakout separation (LD-051):** the list-item serializer emits a **blank line before a
block-level child that breaks out of list context** — any non-list-family child that renders at
column 0 (a table 31, code 14, quote 15, divider 22, …). The marker line ends with a single `\n`;
the serializer emits one more so the list paragraph **terminates**, then the breakout block parses
as its own block. Without it, CommonMark **lazy continuation** folds the block into the list
paragraph — a table renders as literal `|` pipes; a fenced block can mis-parse. The separator is
suppressed when the prior child already left a trailing blank line (no triple newline). Two kinds
of child are **excluded** and stay in list context: the **list family** (12/13/17 — indented, not
broken out) and a plain **`TextNode`** paragraph breakout — the latter is already text (no block
re-parse to protect), and separating a bare interruption cleanly also needs re-separating a
following list, a distinct list-run concern this contract does not cover. The empty `RawBlock`
sentinel renders nothing and takes no separator.

---

## Adding a new block type

1. Create or extend a module in `larkdocio/blocks/` with a function decorated
   `@register_block(<type_int>)`.
2. If it's a **new module**, add `from . import <module>` to `larkdocio/blocks/__init__.py` so
   the decorator runs at import time (see "Eager registration is mandatory").
3. Implement the handler per the contract above — render your own children; emit a visible
   marker rather than dropping data you can't represent.
4. **Verify the integer against the
   [official Feishu enum](https://open.larkoffice.com/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/document-docx/docx-v1/data-structure/block)**
   before trusting any inline comment — mis-registration (right handler, wrong integer) has bitten
   this codebase before.
5. **Update the matrix AND the shipped read-support row — both, in the same change.** In
   `BLOCKS.md` (**in the source repository**) move the type's row to `rendered` (or `placeholder`),
   describe what it emits and give it a **Read-lossiness** state; then carry the same name /
   emission / lossiness into [`read_support.py`](read_support.py), which is what the wheel
   ships. `tests/test_blocks_md_matrix.py` pins the two cell-for-cell in both directions, and
   a handler registered with no read-support row makes `larkdocio.capabilities()` refuse to
   build — so neither half can be skipped.
6. Add fixtures + a behavioral test (fixtures are real SDK `Block` objects deserialized from
   hand-authored JSON — see `tests/conftest.py` / `tests/harness.py`).

## Packaging note

This file ships with the wheel (`[tool.setuptools.package-data] "larkdocio.blocks" =
["BLOCK_TYPES.md"]` in `pyproject.toml`), so it's available next to the code it documents in an
installed package. The maintainers' matrix is a repo-level document `package-data` cannot reach
and is **not** packaged — which is why its per-type read answers ship as
[`read_support.py`](read_support.py) and are projected into `capabilities()` instead. A wheel-only
reader follows the projection, never a repository path.
