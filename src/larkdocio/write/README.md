# `larkdocio.write` — the writeback apply-engine

This package is the **shipped**, block-level Lark **docx v1** writeback apply-engine:
a plan-gated pipeline that resolves a consumer's edit to **exactly one block or
refuses**, requires a **mandatory dry-run** before any write, re-validates every
anchor against the **live** block immediately before patching, and rebuilds runs
**element by element** so no edit round-trips through lossy Markdown. It was built as
four build stages (write-foundations → narrative-text apply → table-cell
patches → insert/delete + style-preserving sub-span edits) and is complete — see
`dev/roadmap-2026-07.md` (in the dev repo) for the tranche history. The engine
shipped across v1.6.0..v1.9.0; the release notes start at 1.14.0, so those
versions are recorded only in the maintainers' records. The feasibility evidence
this engine was built on lives under `dev/write-spike/`, also in the dev repo
(see § "Design history").

The read path (`larkdocio/read/`) is untouched by writes: reader Markdown stays
byte-identical. The write path is deliberately separate — a separate package, a
separate credential app (below), and a separate stdlib-`urllib` transport (the reader
uses the Lark SDK; the writer uses raw `urllib`, both on the shared `common/` core).

## Public API surface

Everything a consumer needs is re-exported from `larkdocio.write` (`write/__init__.py`).
The engine is **findings-agnostic**: it knows nothing about a consumer's findings
schema, layer labels, or status vocabulary. A consumer maps its own accepted edits onto
the typed request values below, owns its approval UX, and does its own status-flipping
afterward; larkdocio only **resolves**, **previews**, **applies**, and returns an
**apply-log**.

**The pipeline (three calls):**

| Function | Signature | Role |
|----------|-----------|------|
| `resolve` | `resolve(request, root) -> ResolvedTarget \| Refusal` | Locate exactly one block for a request against a parsed node tree, **or a typed refusal — never a guess**. Fully offline; no network. |
| `dry_run` | `dry_run(requests, root) -> Plan` | Preview a **batch** of requests → a non-forgeable `Plan` (per request: `block_id` + before/after, or a typed refusal). **Zero writes** — it takes no client. |
| `apply` | `apply(plan, client, document_id, *, allow_partial=False) -> ApplyLog` | Execute a `Plan` via a `WriteClient`. Accepts **only** a `Plan` from `dry_run` (a non-`Plan` raises `TypeError`); re-validates each anchor live, then patches. Dispatches each entry inside the **disposition boundary** (`larkdocio.write.disposition`), so a write that fails becomes a typed log entry and the batch halts rather than the exception escaping: the `ApplyLog` is 1:1 with the plan **whatever happened**. **By default it RAISES `LarkApplyRefusedError` rather than returning that log when the log carries entries that did not land**; pass `allow_partial=True` to receive the log as a return value instead. Either way the log is complete. |

**The request vocabulary** (`larkdocio.write.model`) — dumb, frozen, JSON-round-trippable
typed data, stdlib-only:

- **`EditRequest`** — replace one **whole paragraph** *or* one **whole table cell**:
  an `anchor` (an `Anchor` **or** a `TableLocator`) + a whole-block `replacement` string.
- **`InsertRequest`** — insert typed block(s): a `reference` `Anchor`, an
  `InsertPosition` (`BEFORE` / `AFTER` / `APPEND_INTO`), and non-empty `content` — a tuple
  of **`NewBlock`** values (kind `heading` at level 1–9 / `paragraph` / `bullet` /
  `ordered` / `todo`, the three list kinds **nestable** via `children` / `code` with a
  language / `quote` / `table` — an R×C grid whose cells are plain text **or a `TextSpan`
  sequence carrying a link anchor**, with an optional
  `header_row`) and/or the legacy **`NewParagraph`** (still valid, equivalent to
  `kind=paragraph`, tagless on the wire) — plus **`mermaid`**, a diagram (docx block type
  40, an `add_ons` block) taking already-compiled Mermaid source. Created text is
  **unstyled** — with **one** exception, the **LINK anchor**, allowed because a link is a
  *destination* rather than a decoration, while every actual style stays inexpressible by
  construction because none of them is a field on a `TextSpan`: a created run may carry
  `TextSpan(link_url=…)` inside `NewBlock.rich_paragraph` — **or inside a `NewBlock.table`
  cell** — and nothing else. The cell position is **measured, not extended by analogy**: Lark
  accepts and stores the link-carrying run inside a docx table cell on both write routes,
  read back fresh (the capture, both routes' sent bodies, read-backs and verdicts, is kept
  **in the source repository** at `tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json`).
  Every other run styling in a cell is inexpressible
  for the same reason it is inexpressible in a paragraph — it is not a field on a
  `TextSpan` — and nothing about it was measured. The types this **plan-gated path** does not author (image / board /
  embed / bitable / sheet) stay **structurally inexpressible on it** — `NewBlockKind` is a
  *closed* enum and
  `NewBlock` carries no block-type escape, image token, embed url or sheet reference to
  smuggle one through — and that closed-ness is now stated as **larkdocio's own design
  choice, not an API limit**. **Mermaid is the case that proves the difference.** An earlier
  write spike recorded a *naive* type-40 create rejected `1770001 invalid param` and this
  brief called the whole group write-hostile; a later probe against the live API narrowed
  that to a **malformed-payload artifact** — a *specimen-shaped* `add_ons` create is accepted
  `code 0` on both create endpoints and at both positions, and `1770001` is what Lark answers
  for a type-40 body carrying **no `add_ons` object at all**. So mermaid is **API-creatable**
  and it ships. **Nothing here is claimed about bitable (18) or sheet (30)**: that probe
  covered mermaid only, so those two stand exactly as the earlier spike left them and are the
  only part of the original sentence the `1770001` code still describes.
  **Two of those five ARE authorable — just not here.** An image and a file attachment go
  into the body **out of band**, outside the plan gate, via
  `larkdocio.write.media.put_image_in_document` (docx block type 27) and
  `larkdocio.write.media.put_file_in_document` (type 23) — each one op doing a create →
  upload-bound-to-that-block → PATCH as a unit, because the bytes are a network call this
  compiler does not make. **Both say WHERE with a `parent_block_id` + a 0-based integer
  `index`, and neither takes an `Anchor` / `AnchorById`** — they are outside the plan gate, so
  they are outside its positioning vocabulary too. `parent_block_id` defaults to the document
  root (a docx root block id **is** the document id) and `index` inserts **before** the child
  at that position, with the default `-1` appending; measured on a disposable, and stated for
  a consumer in the guide's two media recipes. For the attachment the block that occupies that
  position is the **type-33 view wrapper**, not the type-23 file block whose id the op returns. Board, embed, bitable and sheet have no such route.
  **A table is the one two-step kind.** Its payload is the grid *property*
  (`row_size` / `column_size` / `header_row`) and Lark **auto-provisions the cell family**
  from it — each cell (type 32) wrapping one inner text block — so `apply` fills each
  authored cell by patching that inner block with the **same** whole-cell
  `update_text_elements` body a `TableLocator` edit uses (no new endpoint; the shape the table-cell
  gate live-proved). A created table is therefore immediately addressable by a
  `TableLocator`, which is how rich cell content is authored after creation. **Merged cells
  are not expressible from Markdown** (no colspan/rowspan): the grid carries no span field,
  and a **ragged** grid is refused at construction with the typed `merge-not-expressible`
  refusal (a `RefusedError` carrying it) — never padded or truncated into shape. Grids are
  bounded by `MAX_TABLE_CELLS` (500 — **larkdocio's own** cap, anchored on the measured
  one-call platform envelope of 499 cells; the fill itself is **batched**, so the reason the
  old 200 encoded — a throttled read + patch per non-empty cell — no longer describes what a
  table costs: it is `~2 list + ⌈cells/48⌉ batch_update`. Collapsing the whole construction
  into a single `descendant` subtree call is **SHIPPED** — the park was superseded and
  its reason kept: the worry was positioning and atomicity semantics, and a spike
  answered it at real scale (1 call, 0.82 s measured, a 499-cell envelope), so a single-table
  insert that fits `fits_one_call` now takes the `descendant` route and everything else keeps
  seed-and-grow). **`header_row` is a projection lossiness, not a write lossiness**
  (live-verified): it is stored either way, but Lark **omits a false flag** from
  the block payload and the reader's documented absent ⇒ promoted default then applies, so a
  `header_row=False` table reads back with row 0 promoted — which is why the default is
  `True`, matching both ends.
  Per-kind payloads are built by **`write/encode.py`**, whose shapes are the *reader's own*
  parse shapes (`heading{L}.elements`, `todo.style.done`, `code.style.language`, …), so
  what the reader parses is what the encoder emits. Because `create_children` creates **one
  level deep**, a nested tree is encoded to a flat pre-order sequence with parent pointers
  and applied as **one call per parent** (each deeper call parented on the real id Lark
  returned); flat content stays exactly one call with a byte-identical body. Nesting is
  capped at a documented depth and a group at the endpoint's 50-per-call limit — **deeper or
  wider is refused at construction, never silently flattened**.
- **`DeleteRequest`** — delete the single block a `target` `Anchor` designates
  (contiguous-range delete is a documented non-goal; issue N deletes for N blocks).
- **`SubSpanEditRequest`** — edit a quoted **span within** a paragraph, preserving the
  surrounding run styles: an `Anchor` + the verbatim `span` + its `replacement`.
- **`GrowTableRequest`** — append to an existing table's grid, **at the end only**:
  an `AnchorById` or `TableLocator` naming the table + how many rows / columns to add. It is
  the one operation that changes an existing grid, it preserves every existing cell id, and
  a request to insert anywhere but the end refuses typed (`table-grow-unsupported`).
- **`Anchor`** — the narrative locator: a verbatim **quote** + a **breadcrumb**
  (the ordered enclosing heading path).
- **`TableLocator`** — the table-cell locator: a **`row_key`** (key-cell quote) + a
  column-target (**exactly one** of `column_header` or `column_index`) + a `breadcrumb`.
- **`AnchorById`** — the by-id locator: a bare **`block_id`**, accepted by
  `InsertRequest.reference`, `DeleteRequest.target`, `EditRequest.anchor` and
  `SubSpanEditRequest.anchor` interchangeably with an `Anchor`. `apply()` returns
  `created_block_ids` and every parsed node carries `block_id`, so the natural consumer loop
  is *author → take the ids back → anchor the follow-up by them* (before this,
  the only way was to re-quote the text you had just written — indirection with a staleness
  risk, and impossible when the text is not unique). Matched by **exact equality** — never a
  prefix or a fuzzy match — so an id that never existed, belongs to another document, or has
  been deleted refuses **with the id named**; a hostile target refuses *hostile*, not
  not-found. Because an id can address a **container** a quote never could, a whole-block or
  sub-span *text* edit of one (a table, a cell, a grid) refuses `write-hostile-target` naming
  the child-id / `TableLocator` repair — while **deleting** a container by id is legitimate and
  allowed.
- **`Refusal`** / **`RefusalReason`** — the typed skip reasons (below).
- **`ApplyLog`** / **`ApplyLogEntry`** — the JSON-serializable record of processing each
  request. The outcomes the engine emits are `applied` / `refused` / `inserted` / `deleted`
  and, for the two comment ops, `commented` / `comment-removed`. An entry also carries
  `mutating_write_calls` (the write calls that entry actually spent — **counted, never
  predicted**, and present only where measured) and `todo_done` (the checkbox bit an edit
  moved).

**The client + helpers:**

- **`WriteClient`** — the throttled, typed docx v1 write client (below).
- **`Plan`** / **`PlanEntry`** — the dry-run output (non-forgeable; below).
- **`ResolvedTarget`** / **`ResolvedCell`** / **`ResolvedInsertion`** — the success arm of
  `resolve`, carrying the resolved `block_id` + node (+ table/insertion context).
- **`block_plain_text`**, **`WRITE_HOSTILE_NODE_TYPES`**, **`to_write_elements`**,
  **`text_block`**, **`build_whole_paragraph_update`**, **`build_subspan_update`** — the
  resolver/apply building blocks (a block's own quotable text, the write-hostile node
  set, the style-preserving run rebuild, and the two `update_text_elements` body builders).

### Which created kinds accept `spans=` — and which cannot

<!-- spannable-kinds: begin -->

A `TextSpan` carries the **one** styling a created run can have — the link anchor
(`link_url`) — and `NewBlock.rich_paragraph(spans)` is the paragraph's convenience
constructor for it. **Six kinds accept `spans=`**, every one of them through the plain
constructor — and, beside them, a **table cell** carries the same anchor by being authored as
a `TextSpan` sequence in `rows=` rather than as a `str` (a table *block* still refuses
`spans=`, because a table's content lives in its rows); the block's `text` is derived as the concatenation, so everything that reads a
`NewBlock`'s plain text keeps working unchanged.

| Kind | Authored as |
|---|---|
| `paragraph` | `NewBlock.rich_paragraph(spans)` — or `NewBlock(kind=NewBlockKind.PARAGRAPH, spans=…)` |
| `heading` | `NewBlock(kind=NewBlockKind.HEADING, level=…, spans=…)` |
| `bullet` | `NewBlock(kind=NewBlockKind.BULLET, spans=…)` — `children=` still nests |
| `ordered` | `NewBlock(kind=NewBlockKind.ORDERED, spans=…)` |
| `todo` | `NewBlock(kind=NewBlockKind.TODO, spans=…, done=…)` |
| `quote` | `NewBlock(kind=NewBlockKind.QUOTE, spans=…)` |

**Three kinds are absent, and the reasons are the engine's own**: `code`'s Markdown
projection is a **fence** — verbatim content, inside which the reader emits no `[…](…)`, so
an anchor there would be a silent content drop; `mermaid`'s payload is a **JSON record** and
not text elements at all; and `table`'s content lives in its `rows`. Passing `spans=` to one
of the three raises `ValueError` **naming the kinds that can**, rather than dropping the
anchor quietly.

<!-- spannable-kinds: end -->

The table above is a **projection** of the engine's own `_SPANNABLE_KINDS`, held to it in
both directions by the offline suite: a kind added to the constant with no row here reddens,
and so does a row naming a kind the constant does not carry. It is never a second hand-typed
list.

## How the engine behaves

### Exactly-one-or-refuse resolution — the one hard problem

The spike surfaced that **a verbatim quote is not a unique locator**: on the scratch doc
one sentence matched **5** blocks and the value `97.2%` matched **6**. So "grep the quote
and patch it" is ambiguous and unsafe, and the engine never does it. `resolve` walks the
reader's **parsed node tree** (each block node carries its `block_id`) and returns exactly
one block or a typed refusal:

- the **quote** matches verbatim (substring) against a block's **own** plain text
  (`block_plain_text` — never its child blocks', so a section-spanning quote can't match a
  heading);
- the **breadcrumb** (contiguous sub-path of the block's heading path) narrows when the
  quote alone is ambiguous;
- a quote matching **no** block → `not-found`; still ambiguous after breadcrumb narrowing →
  `ambiguous-N-candidates` (carrying the candidate ids — **never auto-picks**); resolving to
  a **write-hostile** type → `write-hostile-target`, even if otherwise unique.

**The match is against RAW STORED text, and stored text can carry a soft return** — a literal
`\n` inside one paragraph, which the Markdown shows as an ordinary line wrap. So a whole
sentence copied off a wrapped paragraph differs from what is stored by one invisible character
and refuses. **Quote a short fragment that sits on one side of a wrap**, or anchor by
`AnchorById`. The matcher does not move — nothing is whitespace-normalized to force a match —
but a whitespace-only near-miss is **named** rather than hidden: `not-found` gains
`block '<id>' differs only in whitespace` with the stored spelling and a fragment of the
caller's own quote that does match, or *ambiguous after whitespace normalization* with every
candidate id when more than one block is that close. The same clause is appended to
the sub-span `span`-absent refusal, which carries the identical trap.

**Table cells** are located by coordinates instead of text (a bare value is useless in a
table): the row is the one whose **key cell** (column 0) matches `row_key`; the column is
`column_index` or the header cell matching `column_header`; the breadcrumb narrows *which*
table. A cell **covered by** or **anchoring** a merge span refuses `write-hostile-target`
(merges are refuse-only), computed from the shared occupancy grid.

**Every block-level op resolves its anchor through ONE seam** (`_resolve_anchor`): an
`AnchorById` routes to the by-id arm, anything else to the narrative arm, and both return the
same `ResolvedTarget | Refusal` — so a quote and an id reach *identical* downstream semantics
(position computation, staleness, apply path) and no op can be left behind when an anchor shape
is added. The text-replacing ops (whole-block edit, sub-span) additionally require the target to
carry text of its **own**; for a quote that is unreachable by construction, which is why the
quote path's behavior is byte-unchanged.

**Insert/delete** reuse the same narrative resolver for the reference/target anchor, then
insert computes the **insertion point** (parent `block_id` + index) from the reference and
the requested position. The two **position-capability** refusals are mirrors: an
`APPEND_INTO` whose reference is a leaf paragraph refuses `cannot-hold-children`, and a
`BEFORE`/`AFTER` whose reference resolved to a block with **no parent** — the document root /
page node, which the doc *title* anchors to — refuses `cannot-hold-siblings`. Both
name the **resolved** block in their `detail`: the anchor *was* found, so the repair is the
*position*, not the quote. (An earlier release collapsed the sibling case into `not-found` — a lie
that sent consumers hunting for a better quote.)

**Sub-span** resolves the block anchor, then requires the `span` to occur **exactly once**
in the block's text (0 → `not-found`; >1 → `span-not-splittable`).

**The typed refusals** (`RefusalReason`) — shared by the resolver and apply engine:
`ambiguous-N-candidates`, `not-found`, `write-hostile-target`, `stale-anchor`,
`column-not-found`, `cannot-hold-children` and `span-not-splittable`,
`cannot-hold-siblings`, and `comment-anchors-present` (a whole-block **or whole-cell** edit
whose target carries inline comment anchors — the sub-span edit is the recovery its `detail`
names, aimed by the inner block's id in the cell case), plus `change-not-expressible` (a
compiled no-op — a non-text block-property edit is refused typed rather than reported
applied), `table-grow-unsupported` (a mid-table row/column insertion) and
`stale-document` (the whole-batch compare-and-swap). **The enum is the census, not this
sentence** — the reconciler and the comment ops carry further reasons of their own; read
`RefusalReason` for the complete list. Missing / ambiguous / write-hostile cases across all paths
**reuse** the first four (one vocabulary); a new reason is added only when a case genuinely
differs in kind (the mapping rationale lives in `model/refusal.py`).

**Every refusal carries a MANDATORY `detail`**. `Refusal.detail` is a
**required, non-empty** constructor argument — on the dataclass *and* on every factory — so a
detail-less refusal is structurally unconstructable (`TypeError` when omitted, `ValueError`
when blank), `to_dict()` always carries it, and `from_dict` refuses a detail-less wire record
rather than revive a lying refusal. Each detail names the **identifier it is about** (the
quote, the span, the row-key, the resolved `block_id`) plus the recovery, because a consumer
agent reading a bare `{"reason": "not-found"}` has nothing to act on.

### The non-forgeable Plan + mandatory dry-run (the hard gate)

The safety gate is a **mandatory dry-run**: nothing is written until a human (or a
consumer's approval UX) has seen exactly what will change. `dry_run` produces a `Plan`,
and **`apply` accepts only a `Plan`** — there is no "apply directly" entry point:

- a `Plan`'s constructor is guarded by a module-private token, so `Plan(...)` from
  arbitrary records raises `TypeError`. The **only** way to obtain one is `dry_run`, which
  resolves every request through the resolver;
- a `Plan` is read-only/inspectable (`to_dict` / `to_json`, and the `resolved` / `refusals`
  partitions) so a consumer can render the before/after preview, but there is deliberately
  **no** `Plan.from_dict` — reconstructing a *trusted* plan from JSON would re-open the
  forge vector the gate closes;
- `apply` rejects any non-`Plan` argument with `TypeError`, so a bag of raw
  `EditRequest`s can never reach a write.

### Apply — element-level, style-preserving, stale-safe, throttled, logged

`apply` executes the plan in order. Refused entries are carried into the apply-log
verbatim (no write). Each resolved entry is patched **surgically**:

- **Whole-paragraph / whole-cell** edits collapse to a single replacement run rebuilt from
  the live block's leading run via `to_write_elements`, so the leading run's clean style
  (bold / italic / inline_code / strikethrough / underline / text_color / background_color /
  link) survives. This is an **element-level** `update_text_elements` patch — **never** a
  lossy Markdown round-trip, which would silently degrade per-run style and colour.
  **A whole-block edit is refused when the block carries inline comment anchors**
  (`comment-anchors-present`): the collapse to one run leaves a reviewer's per-passage
  anchors nowhere to attach, and the refusal's `detail` names the sub-span edit as the way
  through rather than move a comment onto text nobody commented on. **A whole-cell edit is
  refused on the same collapse when the cell's inner text block carries inline comment
  anchors** — that inner block is the one block the patch rewrites, so a comment on the row's
  key cell, on another cell, or on a later paragraph in the same cell is not in danger and
  does not refuse. Its `detail` names the row and column rather than a block id, and its
  recovery is a sub-span edit anchored **by the inner block's id** (`AnchorById`), because a
  row-key-and-column locator has no way to name a span.
- **Sub-span** edits split the matched run(s) at the span boundaries and mutate **only** the
  span, leaving every surrounding run byte-identical; the span must map to **exactly one
  uniformly-styled contiguous run region**, or the engine refuses `span-not-splittable`
  rather than guess a replacement style (a span crossing differing run styles, or
  overlapping a non-text inline like a mention/equation, refuses). Every rebuilt run
  re-emits the inline comment anchors its source run carried, so a sub-span edit's
  replacement run takes the review anchors of the region it replaces and an untouched run
  comes through anchors and all — and a span whose runs disagree about their anchors refuses
  for the same reason a disagreeing style does. This is the path the whole-block refusal
  points at.
- **Insert** re-validates the reference, then `create_children` at the plan's computed
  parent + index (plain text blocks, one level deep). **Delete** re-validates the target,
  captures the **full removed-block payload** (elements + per-run style + block-level style,
  plus the own content object of a block that has no elements container: a diagram's
  `add_ons`, an image's `image`) *before* the irreversible remove so the destructive edit
  stays describable — and, for a text block, reconstructable — then `batch_delete`s the
  single live child range.

**Stale-anchor re-validation (docx writes are NOT compare-and-swap).** The API defaults to
`document_revision_id=-1` ("latest"), so there is no revision lock. Immediately before each
write the engine `get_block`s the target and re-validates it with **the anchor's own
precondition**; on drift → `stale-anchor` skip, no write.

- An **`Anchor`** requires its **quote to still be a substring** of the live block text — a
  quote is a fragile locator (the text under it can change, leaving the anchor pointing at
  something else), so re-finding it is the check.
- An **`AnchorById`** has no quote, and an id cannot come to mean a different block, so
  staleness means *the content changed since you previewed it*: the plan captures the block's
  **live-basis** text (`PlanEntry.precondition_text` — text runs only, the offline mirror of
  what the engine reads back) and the write requires the live text to still **equal** it. That
  makes an id-anchored write a **compare-and-swap on the anchored block** — strictly stronger
  than the quote check, and the strict-concurrency posture the writer commits to. It is a
  trailing, **conditional** wire field, so a quote-anchored plan's JSON is byte-unchanged.
  **One basis per node kind, shared by both sides**: the capture mirrors what the live
  read returns for *that* block — its inline `content` runs, or, for the **page (root) node**,
  its `title` runs (the root's own text lives under `page.elements`, which the engine's content-
  container lookup finds like any other). Reading `content` alone previewed `''` against a live
  document title, so every id-anchored write against the document ROOT refused a false
  `stale-anchor` — on the one anchor an empty document offers.
- **Table-cell** edits run a **double** re-validation (stricter still): the **key cell** (row
  identity — `row_key` still matches) **and** the **target cell** (content still equals the
  captured `before`) are both re-read live, and **either** drift → `stale-anchor` skip.

**A block that cannot be re-read at all refuses too**. If the pre-write read itself
fails — the commonest cause being the block **deleted between plan and apply** — what the plan
previewed cannot be confirmed, so the entry refuses `stale-anchor` carrying **Lark's own
`code`/`msg`** in its `detail`, with no write issued and the rest of the batch unaffected. An
exception there would break two engine contracts at once (every processed request yields
exactly one apply-log entry; a refusal is a *skip*, not a failure of the batch) and would hand
the consumer no apply-log for the writes that already landed. A **rate-limit** error is not
called staleness: the shared transport owns backoff, and a limit that survives it is typed
`rate-limited` by the disposition boundary below rather than reported as drift.

**THE DISPOSITION BOUNDARY — what makes the 1:1 claim above true when a WRITE fails.** The
paragraph above is about a re-validation *read*. The engine's own write calls used to sit
outside any `try`, so a `LarkAPIError` from a create / patch / delete escaped the per-entry
loop and the caller got **no apply-log at all** — for the entries that had already written as
much as for the ones that never ran. That was the one reachable state in which the 1:1 claim
was false, and it is closed: each resolved entry is dispatched inside
`larkdocio.write.disposition`, which classifies any exception into a typed outcome —

| outcome | means | landed? |
|---|---|---|
| `refused` | Lark answered about this entry (`api-error`), refused it for a missing scope (`permission-denied`), or throttled it (`rate-limited`) | no |
| `failed` | the call failed below Lark (`transport-failure`), a paged read it depends on could not run to exhaustion (`pagination-unterminated`), or something un-modelled raised (`unexpected-error`) | **indeterminate** — never called a refusal, because "nothing landed" would be a guess |
| `applied-unverified` | a write seam **returned** and a step after it failed (`unverified-write`) | **yes** — the change is in the document; only its verification record is incomplete |
| `not-attempted` | the batch halted at an earlier entry | no |

— and then **halts**, logging every remaining entry `not-attempted`. Halting is the
pre-existing behaviour preserved rather than a new policy: entries after a mid-batch failure
were never attempted before the boundary existed either, and this change adds a *record*, not
a write. `ApplyLog.halt` says which entry stopped the batch and why. The classification rows
are docx's own — the *mechanism* is the shared `common/disposition.py` leaf that the sheets and
Base engines ride, and this surface adds no second copy of it.

The one exception that still leaves `apply()` without a log is the **whole-document
compare-and-swap's** rate-limit re-raise, which happens before the batch: throttling is not
drift, and telling a caller to re-plan a document that never changed would be a lie.

**Throttle + backoff.** Every write routes through the shared core's `WriteTransport`, which
paces writes to **≤3/sec** and **backs off on Lark's `99991400`** rate-limit code; the
engine never opens a socket of its own. The engine issues **one single-block `PATCH` per oneof** (throttled) — which is one per edit
for a plain text rewrite, and **two on the same block** when a whole-block edit also moves a
checkbox (`update_text_elements`, then `update_text_style`), because the endpoint takes one
oneof per call; a grow likewise sends one PATCH per appended line. The **one place it
batches is a created table's cell fill**, which used to
cost a read + a patch per non-empty cell: those go out through `batch_update` in runs of
`MAX_BATCH_UPDATES_PER_CALL` (48, a measured envelope) after one paginated document block list
supplies the inner block ids. Nothing about the body a cell receives changed.

**EVERY plan entry yields exactly one `ApplyLogEntry`** — applied, refused, failed mid-flight
or never attempted — so `len(log.entries) == len(plan.entries)`, in plan order, on every run.
That is an absolute, and the disposition boundary above is what earns it: before it, an API
failure mid-batch escaped with the log. **The log is not always RETURNED, and that is the
default:** `apply(plan, client, document_id, *, allow_partial=False)` ends in `gate_refusals`,
which returns the log only when it carries no refusals and otherwise raises
`LarkApplyRefusedError` **carrying that same complete log**. So `log = apply(...)` followed by
iterating `log.entries` sees an exception on the first refusal unless you pass
`allow_partial=True` (or catch the error and read its log). See live-gate family 17.

## The `WriteClient` and the docx v1 write surface

`WriteClient` rides the shared `common/` core: tenant-token auth and the throttle/backoff
transport above, born typed (a non-zero Lark `code` raises the error taxonomy). Its methods
map to the docx v1 block API: `create_document(title="", *, folder_token=None)` — **the one
consumer-facing lifecycle verb here**, and `folder_token` is **required and keyword-only**:
every way of not giving one — omitted, `None`, empty, whitespace — is refused
**locally, before any call**, with `MissingDestinationError`. The default of `None` is what
lets *this library* answer an omitted destination with its own teaching text instead of an
interpreter-level argument error; it is not a licence to skip it. **The reason the fence
exists, preserved:** `folder_token` used to default to `""`, which Lark accepts and files in
the app's own space, where nobody browsing Drive will find it. Given a folder the document
lands there **and inherits that folder's access** (the guide's
"grant a HUMAN access" recipe states both measured cases, including the `perm_type='container'`
rows an inherited grant comes back as) — `create_children` (1–50 children one level
deep — the `MAX_CHILDREN_PER_CALL` cap the engine refuses a wider group at, in the request's own
constructor), `get_block` (the live re-validation read), `_patch_block` (the single-block
`update_text_elements` PATCH), `batch_delete` (a contiguous child range), and
`delete_document` (Drive trash, for teardown). The request-building, throttling, and
error-typing are unit-testable offline via injectable `transport` / `urlopen` /
`token_fetcher`.

Every addressable block has a `block_id` (the root Page block's id equals the
`document_id`). **There is no whole-document write/replace endpoint** — that absence is the
core safety property: a write locates a block by id and fires a surgical PATCH at only that
block, so blocks the tooling doesn't understand are never serialized or resubmitted and an
edit **cannot** corrupt them. (The historical "edit-one-thing-garbles-the-rest" failure came
from the legacy `doc` generation's whole-document payload model, which docx v1 superseded.)
The docx v1 block write surface:

| Method | Path | Purpose | Used by the engine |
|--------|------|---------|--------------------|
| POST | `…/docx/v1/documents` | Create a document — `title` (optional, defaults to untitled) plus the **required** `folder_token` that decides where it lands; every spelling of none is refused locally before the call. | `create_document` (consumer-facing; also how the gates self-provision) |
| POST | `…/docx/v1/documents/:doc/blocks/:block/children` | Create 1–50 child blocks at an index (one level deep). | **insert** (`create_children`) |
| POST | `…/docx/v1/documents/:doc/blocks/:block/descendant` | Create a nested subtree in one call (1–1000). | **insert, when the content is exactly one table that fits the measured one-call envelope** (`create_descendant`, via `_insert_table_in_one_call` — a documented future extension until a spike measured it at real scale) |
| PATCH | `…/docx/v1/documents/:doc/blocks/:block` | Update **one** block (oneof: `update_text_elements`, `update_text_style`, table row/col/merge ops, `replace_image`/`replace_file`, `update_task`). One oneof per call. | **edit / sub-span / table-cell** (`_patch_block`, `update_text_elements`) and a **todo's checkbox** (`update_text_style`, field mask `2` — `build_todo_done_update`; the mask is round 5's measurement, cited at the builder), plus the **table grow** — TWO operations, not one: `insert_table_row {"row_index": -1}` for extra rows and `insert_table_column {"column_index": -1}` for extra columns (the one append loop, `_append_table_lines`, reached from the create path's seed-and-grow — which is what an authored grid wider than `MAX_CREATE_GRID_AXIS` takes — and from the `grow-table` op; **no new endpoint and no new scope**) |
| PATCH | `…/docx/v1/documents/:doc/blocks/batch_update` | Update many blocks in one call (no duplicate `block_id`). Lark's own documented ceiling is ≤200; **48 is the largest batch an actual capture supports** here, so that is what the engine chunks by. | **table cell fill** (`batch_update_blocks`) |
| GET | `…/docx/v1/documents/:doc/blocks` | List every block of a document, paged (`page_size`/`page_token`). | **table cell fill** (`list_document_blocks` — one paginated read replaces one `get_block` per cell) |
| DELETE | `…/docx/v1/documents/:doc/blocks/:block/children/batch_delete` | Delete a contiguous child range `[start, end)`. | **delete** (`batch_delete`) |
| POST | `…/docx/v1/documents/blocks/convert` | Stateless Markdown/HTML → block objects (no write). | not used (engine builds blocks directly) |

**Table row/column edits are operations *inside* the single-block PATCH body**
(`insert`/`delete_table_rows`/`columns`, `merge`/`unmerge_table_cells`,
`update_table_property`) — not separate endpoints. The shipped engine's table support is
whole-cell text patching (via the cell's inner text block) **plus an APPEND-ONLY grid change**:
`GrowTableRequest` is a public export, planned and applied through the same gate, and it sends
`insert_table_row {"row_index": -1}` / `insert_table_column {"column_index": -1}`. What is
still not exposed is everything else — mid-table insertion (refused typed,
`table-grow-unsupported`), removal, and merge/unmerge (see § Non-goals and the docx-write
absence register).

## The composable Markdown dialect (`compose`)

`compose(markdown)` compiles a Markdown fragment into the ordered typed
`NewBlock` content an `InsertRequest` carries; `compose_insert(markdown, reference,
position=AFTER)` is the thin convenience that pairs that content with an anchor. Both are
re-exported from `larkdocio` itself (`from larkdocio import compose`). **They produce
requests, never writes** — no client, no credential, no transport — so composed content
still reaches Lark only through `dry_run` → `Plan` → `apply`.

**The dialect is exactly what our own reader emits** — not "Markdown" in general. It is
CommonMark plus the two GFM extensions the renderer produces (pipe tables, `~~strike~~`),
**including the reader's escaping rules read in reverse**: an escaped metacharacter
(`\#`, `\-`, `\*\*`, `1\.`) is **literal text, never structure**. That symmetry is what
makes the round-trip property provable: *the reader's Markdown for blocks composed from `X`
is `X` again* (or `X`'s documented normalization below), and composing that output is a
fixed point. The corpus that proves it lives in
`tests/test_compose_roundtrip_corpus.py` — fragments lifted **verbatim from the reader's own
goldens**, the reported gaps, every escape class, adversarial cases, and 200 seeded generated
fragments.

**What composes:**

| Markdown | becomes |
|----------|---------|
| `# H` … `###### H`, and setext (`H` + `===`) | `NewBlock.heading(1..6, text)` |
| a paragraph (a soft break becomes `\n` in the text) | `NewBlock.paragraph(text)` |
| `- x` / `* x` / `+ x`, nested by tab **or** spaces | `NewBlock.bullet(text, children=…)` |
| `1. x` / `1) x` | `NewBlock.ordered(text, children=…)` |
| `- [ ] x` / `- [x] x` | `NewBlock.todo(text, done=…, children=…)` |
| ` ```lang ` … ` ``` ` (or `~~~`) | `NewBlock.code(text, language=lang)` |
| `> x` (one paragraph's worth of lines) | `NewBlock.quote(text)` |
| a GFM pipe table (`<br>` in a cell ⇒ a newline) | `NewBlock.table(rows, header_row=True)` |

### The 50-per-call cap — not a `compose` refusal

`compose()` places no ceiling on the number of top-level blocks it returns: a fragment of
any size composes in full, and the count is `len(compose(markdown))`. The 50-per-call limit
lives one step later. `create_children` creates 1–50 blocks per call, so wrapping the
composed content in an `InsertRequest` raises past `MAX_CHILDREN_PER_CALL` (50) — a plain
**`ValueError`** from `InsertRequest`'s own constructor, **not a `RefusedError`** (that
shape is reserved for the compiler's own refusals, documented in the lossiness table
below). Check `len(compose(markdown)) > MAX_CHILDREN_PER_CALL` before building the request
(both re-exported from `larkdocio.write`), and split a longer fragment across more than one
insert.

### Finding every refusal in one pass — `compose_check`

`compose()` refuses the **first** inexpressible construct and says nothing about the rest.
That is the right behaviour — a partial compile would silently degrade an author's content —
and it makes *discovery* O(attempts): a consumer migrating ~27,000 words of existing prose
needed **eight** separate attempts, because each attempt surfaced one construct. Their own
verdict is why the answer is not a permissive mode: they rated the refusals themselves highly —
clear, specific, each naming its fix — and found only the one-at-a-time discovery expensive.

`compose_check(markdown)` is that answer — a **read-only checker**, not a mode:

```python
report = compose_check(fragment)      # a ComposeCheck; nothing is compiled or written
report.ok                             # False if the fragment names anything inexpressible
report.refusals                       # one ComposeRefusal per OCCURRENCE, document order
report.refusals[0].construct          # e.g. "bold"
report.refusals[0].line               # its 1-based source line
report.refusals[0].refusal            # the very Refusal compose() would have raised
report.constructs                     # the de-duplicated construct names
report.to_dict()                      # JSON-native, for a caller that reports the list
```

Three properties hold it honest:

* **Nothing about what is refused changed.** Every row is built by the compiler's own single
  refusal builder, at the same place, with the same construct, the same line and the same
  words — `refusals[n].refusal` is the object `compose()` raises, so the two cannot drift into
  two opinions of the dialect. `compose()` itself is untouched: same refusals, same codes,
  first-failure semantics, and **nothing became composable**.
* **It is one walk of the same parse**, not a second definition of the dialect — the checker
  differs from `compose()` by exactly one thing: whether a refusal ends the walk or is
  recorded and walked past. The blocks it builds on the way are discarded, so there is no
  partial compile and nothing an insert could reach.
* **Completeness is proved, not claimed.** The fixture set in the source repository —
  `tests/test_compose_check_batch_discovery.py` — carries a fixture per refusable construct and holds the fixture set **bidirectionally**
  against `NOT_EXPRESSIBLE_CONSTRUCTS`: a construct added to the compiler with no fixture
  reddens, and a fixture naming a construct the compiler cannot raise reddens. A checker that
  quietly misses one is worse than the serial behaviour it replaces, because the caller now
  believes they hold the whole list.

Same purity as `compose()`: no client, no credential, no transport, no network call. The
worked flow is the guide's § "Recipe: find every construct that will refuse".

### Lossiness — documented, not discovered

**(a) Constructs that REFUSE.** Each is a typed `not-in-dialect` refusal (a `RefusedError`
carrying a `Refusal` whose mandatory `detail` names **the construct and its 1-based line**)
— never a silent drop, never a best-effort approximation. `NOT_EXPRESSIBLE_CONSTRUCTS` is
the code truth and this table is guarded against it.

| Construct | Why it cannot be composed |
|-----------|---------------------------|
| `image` | A `![](…)` carries a path or a token, and this compiler has **no bytes** and makes no network call — so there is nothing to upload. **The picture itself is not out of reach**: author the prose here and put the image in with `larkdocio.write.media.put_image_in_document` (create the image block → upload the bytes bound to that block → `PATCH replace_image`). |
| `link` | An inline link is a **styled run** and *this compiler* creates unstyled runs — the original reason, unchanged. **Two positions are excepted.** (1) The reader's own bare-URL autolink shape (`[url](url)` where the text *is* the http(s) href) composes back to the literal URL. (2) **Inside a TABLE CELL, `[label](url)` composes** — Lark was measured to accept and store the link-carrying run there on both write routes, and the reader already projects it back as `[label](url)`, so the round-trip property this refusal protects is what *admits* that position. **What moved is the conclusion, not the reason: an anchored link IS authorable** — in a cell through the dialect, and anywhere spans are accepted as a typed shape, `NewBlock.rich_paragraph` with a `TextSpan` carrying `link_url`. The dialect stays closed in every other position on purpose: the round-trip property is what that closure protects. |
| `bold` | A styled run — created text is unstyled. Escape the markers to keep them literal. |
| `italic` | A styled run — created text is unstyled. |
| `strikethrough` | A styled run — created text is unstyled. |
| `inline-code` | A styled run — use a fenced block, or escape the backticks. |
| `html` | Raw HTML has no creatable block (the reader emits HTML only for what Markdown cannot express: an `<u>` underline run, a merged `<table>`). |
| `merged-table` | **Merged cells are not expressible** — Markdown has no colspan/rowspan. Both an HTML `<table>` (the reader's merged-table emission) and a **ragged** pipe table refuse, reusing the `merge-not-expressible` reason. GFM would silently pad a short row and truncate a long one, so raggedness is checked against the **source**, not the tokens. |
| `thematic-break` | A divider (docx block type 22) is not creatable in this rung. |
| `indented-code-block` | Outside the dialect — the reader always emits a **fenced** block. |
| `hard-break` | A hard line break has no docx representation (the reader never emits one). |
| `footnote` | A footnote **definition** (`[^1]: the note`) has no creatable block; composing it as text would author a visibly broken footnote. Deliberately narrow: a bare `[^1]` *reference* — and a regex class like `[^a-z]`, the identical shape — is literal text in GFM too without a definition, so it composes verbatim and round-trips. |
| `empty-heading` | A heading is a marker **plus content**; a bare marker carries nothing. |
| `empty-quote` | A quote is a marker **plus content**; a bare marker carries nothing. |
| `empty-mermaid` | A ```` ```mermaid ```` fence with **no diagram source**. Lark accepts an empty diagram and stores it, and the reader emits **no fence and no marker** for one — so it would author a block that is *invisible* in Markdown rather than a visible mistake. |
| `list-item-block-child` | A list item carries its own text plus **nested list items** only; any other block child renders at column 0 — a *sibling* in Markdown — so author it as a sibling. |
| `blockquote-block-child` | The creatable quote block (type 15) carries **one** text run and a quote *container* (type 34) is not creatable, so a multi-paragraph / nested / fenced blockquote is not expressible. |
| `empty-list-item` | A marker with no content carries nothing. |
| `code-fence-info` | Lark stores a code block's language as a single enum, so a fence info string carrying more than the bare token is not expressible. |
| `unknown-code-language` | Lark has no enum for that fence token — use `larkdocio.langs.supported_code_languages()`, or a bare fence. Never silently downgraded. |
| `non-creatable-projection` | **The fence came from our own reader**, not from you: it is the reader's projection of a block this library does not create today, so the fence token is not a language and no supported token would author the block back. One projection ships — ```` ```mermaid ````, a **diagram add-on** (docx block type 40) the reader renders as a fence and this rung does not author. Drop the fence, or keep the text under a **bare** fence to author it verbatim as a code block; everything around it composes. Deliberately **distinct** from `unknown-code-language`: that refusal is right about a token *you* invented and stays exactly as it was, while blaming you for a token *we* wrote would be advice that cannot succeed. |
| `nesting-too-deep` | Past `MAX_NEST_DEPTH` (each level costs its own throttled `create_children` call). Refused with the cap named — **never flattened**. |
| `table-cap` | Past `MAX_TABLE_CELLS` — **larkdocio's own** 500-cell authoring cap, anchored on a MEASURED platform envelope (Lark takes a 499-cell table subtree in one `descendant` call — 1000 descendants — and refuses the next). It is **not** one of Lark's own ceilings: those are 100 columns (`1770010`) and no row cap at all. Refused with the cap named and a size to split into — **never truncated**. The number superseded an earlier `200`, which budgeted a per-cell fill that no longer exists (the fill is batched: `~2 list + ⌈cells/48⌉ batch_update`). |
| `table-column-cap` | Past `MAX_TABLE_COLUMNS` — a **measured LARK ceiling**, not one of ours: it refuses the 101st column itself (`1770010 "too many table column"`). Refused with the cap named — **never truncated**. There is deliberately **no row equivalent**: a table's HEIGHT is not limited this way (the engine seeds a tall grid at the create endpoint's 9-row ceiling and appends the rest), so a table of any height composes. |
| `block` | Any other block construct the dialect has no creatable block for. |
| `inline` | Any other inline construct (created runs are plain, unstyled text). |

**(b) Not creatable in this rung at all.** There is no
Markdown syntax to compose them from, and the *reader's* own emission for them does not
compose back either, which is the honest end of the round-trip:

| Not creatable | What the reader emits for it | What `compose()` does with that |
|---------------|------------------------------|---------------------------------|
| images / media, whiteboards (**boards**) | `![caption](token)` / `![Whiteboard](token)` | refuses `image` — an image is authored out of band instead (`larkdocio.write.media.put_image_in_document`); a board is not authored at all |
| **embedded surfaces** (Base / Sheet / Base named-view), synced blocks | a `> 📊`/`> 🔗` marker carrying **bold** | refuses `bold` |
| **file attachments** | a `📎` marker carrying **bold** | refuses `bold` — the attachment is authored out of band instead, and the two products are different things: the attachment **BLOCK** in the body (docx block type 23) is `larkdocio.write.media.put_file_in_document`, while a file that lives in a folder and is *linked from a sentence* is `put_file_in_folder` plus a `rich_paragraph` link anchor (`BLOCKS.md` **in the source repository** — the wheel ships no matrix — says them apart the same way at row 23) |
| **callouts** | `> ` lines (a callout is indistinguishable from a quote in Markdown) | composes to a **quote** block — the reader's own projection already collapsed it |
| **grids** / grid columns | each column's blocks, separated by a blank line | composes to those blocks as **siblings** — the grid itself is gone from the Markdown |
| **colors** (and any other run styling **except a link**) | nothing — color is dropped by the reader | nothing to compose; created runs are unstyled. The one styling a created run **can** carry is a **link anchor**, authored as a typed `TextSpan` — and, in a **table cell** only, through the dialect's own `[label](url)` |
| equations (`$$…$$`, `$…$`) | `$$`-fenced / `$`-wrapped text | `$`-syntax is not a CommonMark construct, so it composes as **literal text** (the equation *rendering* is not preserved) |
| a **doc mention** | `[title](url)` | refuses `link` (the text is not the href) |
| an **iframe** | `[url](url)` | composes to a paragraph carrying the URL as text — the same reader-side ambiguity a bare URL has (the emission is identical) |
| heading levels **7–9** | `###### ` + text — the marker is **capped** at six `#` (Markdown has no H7+) | composes to a **heading level 6** — the one asymmetric heading case: the level is *capped*, not lost as structure. H7–H9 remain creatable at their true level via `NewBlock.heading()`, and the reader's tree still reports 7/8/9 |

**The heading-level asymmetry, stated plainly.** Headings are the one row above
that is *lossy in the level rather than in the structure*, so it is worth spelling out:
**H1–H6 are exactly symmetric** — the level you author is the level the reader emits and
the level `compose()` gives back. **H7–H9 are not**: Lark stores them, `NewBlock.heading()`
creates them, `parse_docx_tree` reports them — but Markdown's ATX marker stops at six, so
the reader **caps the marker at `######`** and composing that output yields an **H6**.
The alternative (one `#` per level) is *not valid CommonMark*: a conforming parser reads
`####### x` as a paragraph whose text begins with seven `#`, which lost the heading
entirely and refused to round-trip — a capped level is the honest trade, and this is the
record of it. Reading a document never changes it, and the write side is untouched: an
authored H7 is still an H7 in Lark.

**(c) Normalizations — the reader's canonical form wins.** Each is proven to be a
*normalization* (idempotent) and not a corruption, by the corpus's fixed-point tier:

- an **ordered list renumbers from 1** — Lark computes an item's ordinal from its position,
  so an authored number is never carried;
- a **tight list renders loose** — consecutive top-level blocks are separated by the
  document's own blank line (a table or a quote adds one more of its own);
- `*`/`+` bullets become `-`; `1)` becomes `1.`; a **setext** heading becomes ATX;
- **CRLF** becomes LF; leading/trailing blank lines and a paragraph's edge whitespace are
  dropped; space-indented nesting becomes the reader's tab indent;
- a **bare URL gains link syntax** (`[url](url)`) — the reader's always-on linkify (
  no knob) is the one place it *adds* Markdown syntax;
- a **code fence body is the one thing NOT normalized — it is verbatim**: every
  line's leading whitespace (spaces and tabs), whitespace-only lines, trailing whitespace,
  and blank edge lines inside the fence all survive a read, so an indented snippet or ASCII
  art round-trips exactly. (An earlier release stripped the whole joined body, which
  silently dropped the **first** line's indentation while keeping every later line's — the
  CRLF and edge-whitespace normalizations above are `compose()`'s, and they never applied
  to what the reader emits for a fence.)
- **`header_row=False` is not composable** — `compose()` always promotes row 0, because Lark
  omits a false flag from the payload it returns and the reader's absent ⇒ promoted rule then
  applies (the table-projection lossiness).

**(d) Two known asymmetries (recorded, deliberately not "fixed" here — both would be a
reader output change, which needs a deliberate decision):**

1. **A fence body containing a fence line** (` ``` ` inside a code block) is authored
   faithfully — Lark stores it — but the reader always emits a 3-backtick fence, so the inner
   fence closes the outer one when the document is read back and the block splits. A reader
   **projection** lossiness, not a write lossiness.
2. **`[`-bracket shapes in literal text.** The reader escapes line-leading block markers and
   pairable emphasis runs, **not** bracket shapes — so a paragraph whose *literal* text looks
   like a link or an image (`[a](b)`, `![x](y)`) comes back from the reader unescaped and
   **refuses on re-composition**. Refusing is the honest outcome: the alternative is
   authoring a link the consumer never wrote. (A bare `[^1]` or `[^a-z]` is *not* in this
   class — it composes as literal text and round-trips.)

### Mermaid diagrams — creatable, and **create-only**

A Mermaid diagram is a docx **type-40 `add_ons`** block, and it is the one creatable kind whose
payload is not text elements: its content is a **`record` JSON string** carrying `data` (the
Mermaid source), `theme` and `view`.

```python
from larkdocio.mermaid import flowchart
from larkdocio.write import NewBlock

source = flowchart({                        # or hand over source you already have
    "direction": "TD",
    "nodes": [{"id": "A", "label": "Draft"}, {"id": "B", "label": "Shipped"}],
    "edges": [{"from": "A", "to": "B"}],
})
block = NewBlock.mermaid(source)             # theme= is optional, whitelisted
```

Three things about it are worth knowing before you plan around it.

**1. What is sent is the shape a person's own diagram has.** The payload carries all three
`add_ons` fields — `component_id` (empty, exactly as a hand-typed block carries it), the
`component_type_id` of the Mermaid component, and the `record` — and the `record` is emitted in
Go's default `encoding/json` form (**sorted keys, compact separators, `<`/`>`/`&` escaped**),
which is the form the server stores. A diagram authored through this path is therefore
**byte-shape-indistinguishable** from one typed into the editor.

**2. Nothing validates the diagram except this library.** The server accepts and stores whatever
the `record` contains — invalid Mermaid, an unknown theme, an unknown `view`, extra keys — and a
diagram it cannot draw simply fails to appear. So `larkdocio.mermaid`'s rules are the *only*
guard there is, which is why an off-whitelist `theme` is **refused** rather than passed through,
and why an **empty** source is refused too: Lark stores it and the reader then emits nothing at
all for it, so it would be an invisible block rather than a visible mistake.

**3. THERE IS NO IN-PLACE UPDATE. Editing a diagram is delete + re-create.** The docx
block-patch surface carries **no `add_ons` updater** — 17 update descriptors, none of them
`add_ons`, and three plausible field spellings each refused `1770001 invalid param` against the
live API. The replace route works and is the whole recipe:

```python
from larkdocio.write import AnchorById, DeleteRequest, InsertPosition, InsertRequest, NewBlock

# 1. insert the new diagram immediately BEFORE the old one, so it lands at the same position
# 2. delete the old one
# …each through the ordinary dry_run -> Plan -> apply gate; there is no special diagram op.
```

The cost is stated plainly because it constrains consumer design: **the `block_id` changes.**
A diagram's block id is only valid until that diagram is next edited, so **caching a type-40
block id across an edit is unsound** — re-resolve after one. A whole-block `EditRequest`
aimed at a diagram refuses `write-hostile-target` and names this route rather than pretending to
patch. larkdocio invents no `add_ons` updater to hide the shape of the operation.

The consequence of a lost block id reaches past your own bookkeeping:

> Block ids are what comments anchor to, so re-creating a block orphans every review comment left on it — the conversation is not moved, it is stranded, and nothing in the document says so afterwards. This library ships the join that shows you which comments are at stake before you decide: `review.for_node(block)` answers with what reviewers said about that exact block.

## Constraints the engine honors

- **Rate limits** (empirically confirmed): per-app **5 reads/sec, 3 writes/sec**; per-document
  **3 edits/sec**. Overflow → HTTP 400 code **`99991400`**. The `WriteTransport` throttles and
  backs off; `batch_update` counts as **one** per-document edit however many blocks it
  carries, which is why a batched table fill is cheap in throttle budget as well as in calls.
- **Style fidelity → patch at the element level.** Runs are rebuilt via `to_write_elements`,
  never a Markdown round-trip (which degrades per-run style and colour outright).
  Whole-paragraph edits keep the leading run's style; sub-span edits keep every surrounding
  run byte-identical. **Inline comment anchors ride with their run**: a sub-span edit
  re-emits each rebuilt run's anchors, so its replacement run takes the anchors of the text
  it replaces, while a whole-block edit — which collapses the block to one run — is refused
  when the block carries inline comment anchors (`comment-anchors-present`), and a whole-cell
  edit is refused the same way when the cell's inner text block carries them.
- **Write-hostile block types → detect by block type, refuse.** `WRITE_HOSTILE_NODE_TYPES`
  is image, board/whiteboard, embed (iframe / Base / Sheet / Base named-view), and synced
  (origin / reference). Text, heading, list, and **table** are writable; anything resolving
  to a hostile type refuses `write-hostile-target`. Hostile *creatable* types are
  additionally inexpressible by construction (`NewBlockKind` is a closed enum with no
  block-type escape). **Editable is not creatable:** a plain table *is*
  creatable, but a **merged** table only reads and (for its unmerged cells) edits — no merge
  can be authored, and a covered/anchoring merge cell refuses `write-hostile-target` on the
  edit path too. `WRITE_HOSTILE_NODE_TYPES` lists what refuses an EDIT, not what can be
  created. `BLOCKS.md`'s **write-support** column — **in the source repository; the wheel ships no
  matrix** — is the per-block truth.
  **DELETE IS NARROWER THAN THE FENCE.** The list was cut from a statement about
  *patching text*, and a delete patches no text — it removes a child range. Measured
  2026-08-19: Lark's own `children/batch_delete` **removes an image block (27)** and it stays
  removed (parent's `children` no longer lists it; a direct `get_block` answers `1770002 not
  found`), with a same-run **text-block control** in the same table cell answering the same,
  so the result belongs to the block type and not to the harness. Evidence, in the source repository:
  `tests/captures/ld507-image-block-delete/captures/001-image-block-delete.json`. So `_resolve_delete`
  owns its own hostility rule: an image anchored **by id** resolves; an image anchored by
  **quote** still refuses (an image's only quotable text is its caption, which is absent from
  the live block's `text_run` elements, so the apply-time precondition could never hold); and
  **every other type on that list** — `WRITE_HOSTILE_NODE_TYPES` minus
  `DELETE_MEASURED_NODE_TYPES`, read off the code rather than counted in prose — still
  refuses delete because their delete is **unmeasured, not
  refuted** — a measurement covers exactly the block type it was taken on and never a
  sibling, so widening `DELETE_MEASURED_NODE_TYPES` needs its own measurement, not an
  analogy.
- **Stale ids / anchor drift → re-validate before writing.** `get_block` immediately before
  each patch and confirm the quote still matches (double-check for table cells); mismatch →
  `stale-anchor` skip.
- **`batch_delete` / `create_children` limits:** delete removes a contiguous
  `[start, end)` child range; `create_children` creates 1–50 blocks one level deep. A
  **table** counts as one block in that budget — its cells are provisioned by Lark from the
  grid property, then filled by patching each cell's inner text block.

## Credential doctrine (least privilege — two apps, enforced in code)

Read and write use **separate, narrowly-scoped Lark apps** so read-only downloads and write
operations stay isolated — read and write credentials never cross. The split **is enforced
in code** in [`larkdocio/common/auth.py`](../common/auth.py):

- **Read path** (`get_read_credentials`) resolves `LARK_READ_APP_ID` / `LARK_READ_APP_SECRET`
  when both are set, else falls back to legacy `LARK_APP_ID` / `LARK_APP_SECRET`
  (compat with every existing `.env`). Read scope: `docx:document:readonly`. It **never**
  consults the write credentials. **And when neither pair resolves it raises the same typed
  `LarkConfigError` the write path does** — resolution is pair-wise, so "no complete pair" is a
  configuration error rather than an answer, and the empty `('','')` pair it used to return
  (which travelled into a client constructor and surfaced one layer away, as whatever Lark says
  about a blank app id) is retired. The refusal names the pair that is *in force*, which on a
  clone with nothing configured is the legacy pair; rendered on the preferred pair it reads:

  > Read credentials not configured: set LARK_READ_APP_ID and LARK_READ_APP_SECRET — the pair the read path is resolving right now. The quickest route is `larkdocio config --appId <id> --appSecret <secret>`, which writes a read pair into the .env the reader loads; .env is gitignored, so credentials live only there and never in the repository. The read and write pairs are resolved independently and neither falls back to the other, so a write-scoped app is never borrowed to satisfy a read.
- **Write path** (`get_write_credentials`) resolves `LARK_WRITE_APP_ID` /
  `LARK_WRITE_APP_SECRET` — the `WRITE_ENV` pair — and **never falls back** to the read or
  legacy credentials. A missing or half-configured write pair is a loud, typed
  `LarkConfigError`, not a silent fallback: a read-only app must never be silently promoted
  to run a write-scoped operation. Write scope: `docx:document`. Write credentials are used
  **only** by writer work — and the engine puts **no restriction on the target**: a consumer
  **may write to any document** its WRITE app can reach. larkdocio's own live write gates
  write only to disposable, API-created docs the harness provisions itself — **never a real
  document** — but that is **this project's own test-suite policy**, **not an engine
  restriction**. (See § "Live-test discipline" below for the rule as it binds *this* repo.)

(`src/larkdocio/auth.py` survives only as a **transparent back-compat shim** re-exporting the
same objects from `common/auth.py`; new code imports from `larkdocio.common`.)

**The scope names above are a reference, not the source.** Which scopes each individual write
operation requires — and the evidence behind each one — is derived and held in
`larkdocio.permissions`, projected onto every operation in `larkdocio.capabilities()`. If this
paragraph and that registry ever disagree, the registry is right and the guard that holds them
together has been removed.

**Two independent grants are both required** for a write: (1) the write app must hold the
`docx:document` scope (enabled + released + admin-approved in the Developer Console), and
(2) the app must be added to the target doc as an **editor** collaborator (viewer is
insufficient — with a `tenant_access_token` the identity is the app itself). A
self-provisioned doc the write app **creates** satisfies (2) automatically — it owns what it
creates.

## Live-test discipline (the binding write gate)

Writer work is validated **only against a disposable, API-created scratch doc — never a real
document** and **never the read canary or block-zoo doc**. The write gate is
`LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write` — **the consent variable is
not optional**: `pytest -m live_write` on its own *selects* the ring and the harness then
**refuses to execute** it, loud-skipping every marked test. Selection and consent are two
different questions and this repo's suite answers both, because the ring provisions real
objects in a live tenant. The value is the **id of the work item that authorized the run**,
never a truthy flag; unset or malformed is a loud skip, never a silent run. Beyond consent it
needs `LARK_WRITE_APP_*` + network; missing creds skip cleanly with a clear message — never a
silent pass — and it is **never part of `verify.sh`**. It runs **21 gate families that must all pass together**, twenty of them in that
one run, each against a doc it **creates and destroys itself** — plus **one read-only arm that
runs under `pytest -m live` instead**, for the one contract no write gate can prove (family 8
below) (the list below is drift-guarded against
`larkdocio.capabilities(full=True)["surfaces"]["docx-write"]["gate_coverage"]`, which is itself guarded
against the test tree — so a gate cannot ship undocumented and a paragraph cannot outlive its
gate):

1. **Transport harness** (`test_live_write_harness.py`) — the transport round-trip with the
   low-level `get_block` / `_patch_block` primitives: create a baseline (incl. a bold
   sentinel), download twice (byte-identity = the determinism control), one surgical
   mutation, re-download and diff (only the target region changed; the bold `**` survived),
   teardown.
2. **Narrative-apply gate** (`test_live_write_w1_gate.py`) — the **narrative apply engine** end-to-end:
   the real `EditRequest → resolve → dry_run → apply` pipeline against a live paragraph; the
   diff proves exactly one Markdown line changed and the paragraph kept its bold style. Its
   green means manual transcription is dead.
3. **Table-cell gate** (`test_live_write_w2_gate.py`) — the **table-cell** round-trip: a
   `TableLocator` `EditRequest` through the same pipeline (via the double re-validation); the
   diff proves only the target cell's row line changed, the row identity held, and every
   other line stayed byte-identical.
4. **Insert/delete/sub-span gate** (`test_live_write_w3_gate.py`) — **insert / delete / sub-span**, whose surgical
   proof needs a whole-document diff (insert/delete change the block count): only the inserted
   paragraph appeared / only the deleted block disappeared (with its full removed payload
   captured) / only the span's line changed with surrounding run styles preserved.
5. **Table-create gate** (`test_live_write_table_create_gate.py`) — **table CREATION**:
   an R×C grid authored through the two-step create — Lark auto-provisions the cell
   family from the grid property, the engine then fills each authored cell — read back as a
   Markdown table and immediately edited as a first-class target.
6. **By-id anchor gate** (`test_live_write_anchor_by_id_gate.py`) — **`AnchorById`**:
   author, take `created_block_ids` back, insert `AFTER` a returned id, delete by id (removed
   payload captured), plus the two staleness arms only a real document can prove — a
   concurrent rewrite of the anchored block, and a plan applied after that block was deleted.
7. **Authoring gate — THE MARKDOWN-AUTHORING GATE** (`test_live_write_authoring_gate.py`) — the
   **authoring round-trip**: a multi-block Markdown fragment covering **every** creatable kind
   (heading · paragraph · nested bullet / ordered / todo · code · quote · table) plus escaped
   metacharacters is `compose()`d, applied, and re-downloaded through the shipped reader as
   **byte-identically the same Markdown** (the round-trip property, live); the whole-document
   diff proves only the authored lines appeared; the blocks are then deleted **by the ids
   `apply` returned** until the document is byte-identical to its baseline. Its second arm is
   the **`STALE_DOCUMENT` concurrency proof**: an armed plan, a real out-of-band edit from
   a **second client** that deliberately leaves the anchored block alone (so `STALE_ANCHOR` is
   blind to it), then `apply` → the whole batch refuses with **zero writes measured**, the
   document is byte-unchanged, and a **re-plan applies** — the refusal is *recoverable*, not a
   dead end. The ring is written once (`tests/authoring_gate.py`) and also run offline against
   the fake-Lark doubles, so its assertions are exercised on every `pytest -q`.
8. **Reviewer-anchor arm — READ-ONLY, and run under `pytest -m live`**
   (`test_live_comment_anchor_zoo_arm.py`) — the one family that **writes nothing** and needs
   only **read** credentials, because the contract it proves
   (`comment-anchors-honored-or-refused`) cannot be set up by a write gate: **Lark has no
   anchored-comment create** on either surface, so a self-provisioned disposable **cannot be
   given** an inline review anchor. So this arm **reads** a document that already carries real
   ones and drives the plan-time half against it — a whole-block edit of a really-anchored block
   refuses `comment-anchors-present` naming the real ids — with the apply engine wired to a
   transport that **raises on contact**, which makes the zero-write proof *structural*: a
   refusal that failed to fire errors instead of writing. It is a member of this ring (the
   registry records its marker override) rather than a stray test, so it cannot be dropped
   without the coverage guard noticing. The payload leg it cannot cover — which ids land on
   which emitted run — is pinned offline against the same document's captured bytes, by
   `tests/test_comment_anchor_real_payloads.py` **in the source repository** (the wheel ships no tests).
9. **Comment-op gate** (`test_live_write_comment_op_gate.py`) — the two **comment write** ops
   (`comment-create` / `comment-remove`), and the family whose live half matters most because
   the API's success codes here are misleading: the create response does **not** report the
   comment's scope, so `code 0` says nothing about what was made. So it creates a
   whole-document comment through the plan gate, **reads it back** through the shipped comments
   reader and requires `is_whole is True` / `quote is None` from the **listing** endpoint, then
   removes it through the shipped removal op and proves it is gone by **re-reading** — never by
   a return code. Two of its arms write nothing at all and are *structurally* incapable of it:
   an anchored create and a spreadsheet create are both refused at plan time with the engine
   wired to a transport that **raises on contact**, so "zero API calls" is a property of the run
   rather than a count someone remembered to assert. It closes out by trashing its disposable
   and **re-fetching** it to confirm the deletion, and runs twice on two fresh disposables.
10. **Round-trip — surgical** (`test_live_write_round_trip_surgical_gate.py`) — the
    **ID-anchored round trip** end to end: download → **project** the document to Markdown
    carrying one identity marker per block → edit one block's text in the projection →
    **reconcile** → compile → apply → re-download and **diff**. Only the target region
    changed, every other line byte-identical, and exactly **one** patch measured at the client
    boundary. The same chain in reverse then **restores the document to a byte-identical
    baseline** — which is the claim "surgical" actually makes: not merely that the edit landed,
    but that the trip leaves no residue.
11. **Round-trip — conservation** (`test_live_write_round_trip_conservation_gate.py`) — the arm
    that catches the catastrophe the projection's design exists to prevent. Its subject is a
    **table**: opaque to the projection *and* creatable by `compose()`, which is what lets both
    omission shapes reach the reconciler (an image would refuse `not-in-dialect` at compile,
    for unrelated reasons, and the arm would go green without ever deciding conservation).
    **Marker and content omitted** → the block is conserved, never edited, never deleted, never
    re-created, and comes back **byte-identical** beside an edit that did land. **Marker
    omitted, content kept** → the whole batch refuses `conserved-block-re-created` with **zero
    writes**, so a plan that would leave the document holding the block *twice* is refused
    rather than applied.
12. **Round-trip — `STALE_DOCUMENT`** (`test_live_write_round_trip_stale_document_gate.py`) —
    the concurrency guard **on the reconciliation path**, and **recoverable**: a plan built
    against the document as read, a real out-of-band edit from a **second client** that
    deliberately leaves the planned block alone (so `STALE_ANCHOR` is blind to it), then
    `apply` → the whole batch refuses with **zero writes measured** and the document
    byte-unchanged; then a re-download, re-project and re-plan that **applies**.
13. **Round-trip — no marker reaches Lark**
    (`test_live_write_round_trip_no_marker_gate.py`) — the invariant with **no natural
    barrier**, since Lark stores marker-shaped text **verbatim** (measured live against a
    disposable before this ring was written). After a reconciliation the
    **whole** re-read document is scanned in **both** representations — the raw stored block
    payload and the reader's re-rendered Markdown — for every identifier the projection
    emitted, and finds **zero**. An **adversarial control** whose legitimate prose is
    marker-shaped (a non-emitted identifier, mid-line) survives the round trip **unchanged**,
    which is what makes the zero a statement about our strip rather than about the platform.

14. **Round-trip — escape identity on an untouched line**
    (`test_live_write_round_trip_escape_identity_gate.py`) — the arm whose subject is a line the
    caller **never edited**. The projection escapes literal text, and a fenced code block's body
    is the one place the authoring dialect will **not** decode that again (a backslash inside a
    fence is a backslash to CommonMark itself), so a two-line code block is seeded, **one** line
    is edited through the shipped chain, and the document is read back in **both**
    representations: the untouched line is **byte-identical**, carrying none of the projection's
    backslashes. It carries its own teeth — the **pre-fix compile is re-created in place** from
    the same plan, applied, and asserted to really corrupt the untouched line, then repaired
    through the shipped chain and the repair verified. A gate never shown failing on the defect
    it guards is not known to detect it.

15. **Round-trip — the anchor soft return**
    (`test_live_write_anchor_whitespace_gate.py`) — the arm whose **premise is itself an API
    fact**: Lark stores a literal newline **inside one text run**, and the Markdown shows it as
    an ordinary line wrap. The arm authors one on the wire and reads the block back to prove
    that before claiming anything built on it, then proves both behaviours that rest on it — a
    whole sentence copied off the wrapped paragraph refuses `not-found` with a `detail` that
    **names the block**, quotes its stored spelling and offers a fragment that does match,
    with **zero writes measured at the client boundary**; and the shipped recipe's **old
    line-splice idiom is re-created in place**, applied, and asserted to really come back with
    the sentence's ending written twice while the plan reported ok — then the same block is
    repaired through the block-safe splice and read back verbatim. The whole finding is that
    the plan was already clean over the garbled one, so the control is the point.

16. **Table-growth gate** (`test_live_write_table_growth_gate.py`) — a table **past the
    create endpoint's per-axis grid ceiling**, on both axes. Two grids that each exceed it on
    a different axis are `compose()`d from Markdown, planned and applied, then re-downloaded
    through the shipped reader: the round trip is the verdict, the **live** `row_size` /
    `column_size` are asserted so a grid created short cannot pass on Markdown alone, and the
    whole-document diff proves the write was purely additive. It exists because the fix is a
    *construction* change — the one class of change an offline call-sequence assertion can get
    internally consistent and still have wrong on the wire.

17. **Refusal-policy gate** (`test_live_write_refusal_policy_gate.py`) — the arm that proves
    the one sentence the partial-application ruling rests on: **nothing about the writes
    changed, only return-vs-raise**. The same two-entry batch — one entry that resolves uniquely, one whose
    quote is deliberately **ambiguous** (the measured consumer shape, refusing
    `ambiguous-N-candidates`) — is applied **twice, on two documents this arm creates itself**:
    once by default, where `apply()` raises `LarkApplyRefusedError` carrying the whole log,
    what applied and every refusal's reason and detail; and once with `allow_partial=True`,
    where it returns that same log. Both documents are read back and their bodies **compared**,
    because the claim is about the pair — and the raising arm separately proves the applied
    entry **stayed landed** (a report, never a rollback) and that the refused one wrote
    nothing. An offline suite can prove the raise fires; only a round trip can prove it did not
    move which entries land. Both disposables are emptied in a `finally` and closed out by the
    ledger's independent re-query.

18. **Batched table-fill gate** (`test_live_write_batched_table_fill_gate.py`) — a
    grid of **6 columns × 36 rows = 216 cells**, `compose()`d from Markdown,
    planned, applied — with **every HTTP request the write client issues counted on the
    wire**. The pin is the **call count**: ≤60 API calls for 216 cells, where the per-cell
    fill spent **463** (measured 2026-08-15: **37 calls, 12.4 s**, of which 1 block list and 5
    batched writes), and the batch arithmetic (`⌈216/48⌉ = 5` batched calls) is asserted by
    URL rather than by counting client-method calls. Elapsed seconds are **recorded as
    evidence and gate nothing** — the thing this change bought is calls, not seconds. The
    verdict is a fresh read-back: live `row_size` / `column_size`, 216 cells, and **row-major
    cell order** at four fixed probe points, because a transposed fill would otherwise pass on
    cell count alone. The write is proved purely additive. It exists for the same reason the
    table-growth gate does — this is a *construction* change, the class an offline
    call-sequence assertion can get internally consistent and still have wrong on the wire.
19. **Round-trip VERB gate** (`test_live_write_roundtrip_verb_gate.py`) — the file-first round
    trip **as the shipped console verb** (`larkdocio roundtrip pull` → the caller edits
    `document.md` on disk → `larkdocio roundtrip push --apply`), which is the first family
    whose subject is a *command* rather than a library call and so the first that has to cross
    a **process boundary and a file system** to make its claim at all. It runs the shipped
    verb, never the engine under it: pull to two files, edit the Markdown on disk, push once as
    a **rehearsal** — writes counted at the client boundary AND the document re-read against
    its baseline, because a preview that quietly wrote would otherwise pass — then push with
    `--apply`. The verdict is three separate things: the change landed, an independent diff
    proves it **surgical**, and the verb's **own** compose-equivalence read-back verified
    something (an empty verified list with a clean verdict is a vacuous pass). Its disposable
    is created into the **caller-supplied** disposables folder, named explicitly, and the arm
    **skips loudly** naming that variable when it is unset.
20. **One-call table gate** (`test_live_write_one_call_table_gate.py`) — the same 216-cell
    grid, authored as **one atomic subtree call** and inside a **MIXED batch**, because this
    family's binding claim is *positional*: a paragraph insert and the table insert go out
    together, and the read-back asserts each landed beside **its own** anchor, read off the
    **live child order** rather than the rendered Markdown. The table's cost is pinned at
    **exactly one** `/descendant` call with **no** grow or fill `PATCH` behind it — a bound
    with slack could not tell a one-call construction from a two-call one — and the verdict is
    the same fresh read-back the batched-fill family earns: live `row_size` / `column_size`,
    216 cells, row-major order at the same four probe points, write purely additive. Its
    second leg is the **atomicity** proof: a subtree **one cell** past the measured envelope is
    refused, the document is re-read to show **nothing** was created, and a control one cell
    inside it lands — so the boundary is attributable to the envelope rather than to the body.
    Both legs create their disposables into the **caller-supplied** folder and **skip loudly**
    naming that variable when it is unset.

21. **Todo-checkbox gate** (`test_live_write_todo_done_edit_gate.py`) — the family whose whole
    reason is that the field mask this engine sends for a checkbox was measured **elsewhere**
    and is **cited** rather than re-derived, and a citation is not this library proving its own
    shipped operation. A nested todo tree is seeded through the plan gate, **one** parent
    checkbox is flipped in the projection and nothing else, and the verdict is a read-back of
    the **raw block payload** — not the reader's Markdown, because `align`, `folded` and a
    nested child's identity are exactly the properties the mask must leave alone and not all
    of them are projected. Property by property against the pre-image: `done` moved; the
    target's own text, `align`, `folded` and child list did not; the nested child's id, text
    and state did not. The flip is measured at **one** write call, which is what proves a pure
    flip does not rewrite the block's text and flatten a styled item's runs for the sake of a
    boolean. The reverse flip restores the document to a **byte-identical** baseline, and is
    also the only leg that exercises the mask writing `False`.

Families 10–14 and 15 are the **round-trip ring**. Each self-provisions its document, restores
it, trashes it in a `finally`, and **closes out by independently re-querying every id it
ledgered** — a best-effort delete is not a zero-orphan proof (`tests/docx_ledger.py`, the docx
port of the Sheets ledger pattern; the re-query seam is `WriteClient.get_document`).

Because the reader is deterministic (two clean downloads are byte-identical), any post-edit
diff is attributable to the edit alone, and every content edit must be **surgical**. Each
family **restores** its disposable doc to a byte-identical baseline and best-effort trashes
it in a `finally`, so nothing persists even on a mid-round-trip failure. Writes ride the
shared throttle (≤3/sec, `99991400` backoff). (The read-only determinism half already ships
as the `pytest -m live` canary; see PROJECT.md § "The binding QA gate" (in the dev repo).)

## Non-goals

> **The machine-readable form of this section is the surface's own absence register** —
> `capabilities(full=True)["surfaces"]["docx-write"]["absences"]`, authored as data in
> `larkdocio/write/absences.py` and projected onto the surface verbatim. Each row carries a
> `statement`, how firmly it was established (`verification`, from one enumerated set), the
> `evidence`, and what a caller does `instead`. Read it rather than inferring an absence from
> a list that does not contain the verb you wanted: no move or reorder, no @mention authoring,
> no character styling, no change to an existing table's grid BEYOND appending a row (the
> append ships — `GrowTableRequest` — while removal, a column append and mid-table insertion
> do not, and asking for the last of those **refuses, typed**), no edit of a block's properties
> beyond its text and a todo's checkbox (asking for one **refuses, typed** — it is never
> reported applied), and no document retitle.

- **No unattended auto-apply** — a `Plan` (mandatory dry-run) is the only input to `apply`.
- **No guessing** — ambiguous / not-found / write-hostile / stale / non-splittable cases
  **refuse**, never best-effort.
- **No creation of images or file attachments through the plan-gated Markdown path** — and
  the reason is unchanged: **the compiler holds no bytes** and makes no network call, so a
  Markdown `![](…)` is refused and no `NewBlockKind` creates one. That is a statement about
  *this path*, not about the document. Both are authored **out of band**, each as one op
  doing its create → upload-bound-to-that-block → PATCH as a unit:
  `larkdocio.write.media.put_image_in_document` (docx block type 27) and
  `larkdocio.write.media.put_file_in_document` (docx block type 23). See § "Lossiness —
  documented, not discovered" for what the dialect does with the reader's own emission for
  one.
- **No creation of boards / embeds** — **structurally inexpressible**, and this half does not
  narrow: there is no op for them anywhere in this library, in band or out.
- **No full-document regeneration** — there is no whole-document write endpoint.
- **Contiguous-range delete** is a documented future extension, not shipped this ladder.
  **Three things have LEFT this bullet, each by a landing that kept its reason.**
  (a) `batch_update` **batching** ships, for the one path whose cost was linear in cells (a
  created table's fill); it is not a general batching layer over ordinary edits, which still
  issue one `PATCH` each. (b) **Nested-subtree creation** (the `descendant` endpoint) ships
  for the single-table insert that fits the measured one-call envelope. (c)
  **Structural table row/column APPENDS** ship, as `GrowTableRequest` — inside the plan
  gate, append-only. What is still absent is **merge/unmerge**, **removal**, and
  **mid-table insertion** (that last one refuses typed, `table-grow-unsupported`).

## Design history

The feasibility evidence this engine was built on — the write-feasibility spike (run against
an early scratch doc), including the sandwich demo (a patch between two mermaid blocks
left both byte-identical), the full round-trip diff evidence, and the harness sketch
(`to_write_elements` style-preserving rebuild) — is preserved as a historical record under
`dev/write-spike/` (in the dev repo). It is the primary source; this README
documents the engine as shipped.
