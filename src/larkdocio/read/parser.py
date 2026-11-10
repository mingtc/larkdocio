import logging
from typing import Any, Dict, List, Optional
from .config import Config
from .mentions import resolve_mentions
from .references import ReferenceNote
from larkdocio.blocks import get_registry
from larkdocio.model import DocumentNode, MarkdownRenderer, Node, RawBlock, UnknownBlockNode

logger = logging.getLogger("larkdocio")

# ---------------------------------------------------------------------------
# The recursion / indent contract (LD-031; R-S5 teardown LD-038)
# ---------------------------------------------------------------------------
# The spine has ONE recursion primitive (the old single string walk, the
# "minimal guard only" stopgap, and the transitional string-boundary delegate
# are all gone — R-S5 deleted the last of them):
#
#   parse_docx_node(block, indent_level) -> Node
#       The node-producing primitive. Dispatches to the registered handler and
#       returns the typed model node — this is what builds the document object
#       tree. page(1) / the headless DocumentNode descend via this, and every
#       container family recurses its children through it (via `_child_nodes`). A
#       MISSING block (a dangling child id resolving to no block) yields an empty
#       RawBlock sentinel. An UNREGISTERED type logs the `Unknown block type N ...`
#       warning and yields an UnknownBlockNode carrying its children built at the
#       block's own depth — the renderer emits them TRANSPARENTLY (no markup of the
#       unknown block's own; the view/grid precedent), so an unknown CONTAINER
#       surfaces its subtree instead of dropping it (LD-045, Decision e); a leaf
#       unknown renders "". Every handler returns a model Node (the T2 migration is
#       complete — the LD-024 strangler shim's legacy-string arm was removed in
#       LD-032).
#
# Serializing the object tree to Markdown is the renderer's job alone —
#   `render(node, depth) -> str`. R-S1..R-S4 flipped every container family's
#   child carriage from ALREADY-RENDERED strings to child NODES (R-S1 the list
#   family, R-S2 the recurse-at-0 group — heading / callout / quote_container,
#   R-S3 the table family, R-S4 the own-depth recursers grid + source_synced), so
#   the whole document object is a node tree the renderer descends in ONE pass;
#   R-S5 (LD-038) then retired the string-boundary delegate the string-carrying
#   families had needed. There is no longer a separate string recursion entry.
#
# WHO INDENTS: only list items carry a leading indent of `depth` hard tabs — and
#   the LIST-ITEM SERIALIZER (`_list_item`) owns that tab, applying it via the
#   depth threaded through `render(node, depth)` (keyed on the node kind, not the
#   source block_type). Every other serializer ignores depth for its own line, so
#   a block-level child (a table/code/divider nested under a list item) still
#   renders at column 0 — prepending a tab would corrupt it into an indented code
#   block (the guard's whole reason).
# WHO RECURSES AT WHAT DEPTH: list handlers recurse their children one level
#   deeper — the list-item serializer renders each child node at `depth + 1`
#   (mirrored at parse time by the handler building child nodes at
#   `indent_level + 1`); page and every other container recurse at their own
#   level (page/heading/callout/quote_container at 0, grid/source_synced at
#   `indent_level`).
# WHO SEPARATES / OWNS TRAILING NEWLINES: each block node's serializer emits its
#   own trailing newline(s). The page root emits `# {title}\n` (only when the
#   title is non-blank), a blank separator line, then each child's serialization
#   followed by a single `\n` child separator. Container serializers concatenate
#   their child strings verbatim (each child already carries its trailing
#   newline). The headless DocumentNode concatenates its children with NO
#   separator (byte-identical to the prior string fallback).


class Parser:
    def __init__(
        self,
        config: Optional[Config] = None,
        *,
        deep_read_sheets: bool = False,
        sheets_client: Any = None,
        fidelity_read_sheets: bool = False,
        sheets_export_reader: Any = None,
        deep_read_bases: bool = False,
        base_client: Any = None,
        read_client: Any = None,
    ):
        self.config = config or Config()
        # Opt-in embedded-sheet deep-read (LD-105). BOTH default
        # off / absent, so a default Parser is byte-identical to today: the type-30
        # handler (`blocks.embedded.handle_sheet`) emits the traceable placeholder
        # and makes ZERO Sheets API calls (D2/D8). Only when a consumer opts in
        # (`deep_read_sheets=True`) AND a `sheets_client` is supplied does the
        # handler deep-read the referenced tab; ANY failure degrades back to the
        # placeholder (a docx download never fails because of deep-read). These are
        # keyword-only so every existing `Parser(config)` construction is unchanged.
        self.deep_read_sheets = deep_read_sheets
        self.sheets_client = sheets_client
        # Opt-in WHOLE-CELL (format-level) style FIDELITY read (LD-117 D5a), the deep_read_sheets
        # twin. Off/absent by default: no xlsx export is issued and a deep-read
        # renders values-only (byte-identical to the LD-105 deep read). Only when a
        # consumer ALSO opts in (`fidelity_read_sheets=True`) AND a
        # `sheets_export_reader` is supplied does a deep-read run the READ-creds xlsx
        # export (D1, scope PROVEN) and render whole-cell bold/italic as MD emphasis;
        # an export failure degrades to values-only (never fails the deep-read).
        self.fidelity_read_sheets = fidelity_read_sheets
        self.sheets_export_reader = sheets_export_reader
        # Opt-in embedded-BASE deep-read (LD-250) — the sheets pair above
        # replayed for the two docx embed types, `bitable` (18) and `reference_base` (53),
        # which ride ONE bridge (`larkdocio.base.embed`). BOTH default off / absent, so a
        # default Parser is byte-identical to today: each handler emits its traceable
        # placeholder and makes ZERO Base API calls. Only with `deep_read_bases=True` AND a
        # `base_client` does a handler deep-read the referenced table; ANY failure — a
        # malformed token, a zero-table husk app, a stale table id, an API error — degrades
        # back to the placeholder, because a docx download must never fail on a Base it
        # could not read.
        self.deep_read_bases = deep_read_bases
        self.base_client = base_client
        # The READ-CLIENT seam (LD-173, dogfood F3). The parser renders offline; the ONE
        # thing it cannot finish on its own is @mention resolution, because the resolver
        # (`batch_get_user_names`) lives on the read client. Absent (the default) it stays
        # exactly as offline-pure as before — a mention renders as its raw `@ou_id` and NO
        # contacts surface is reachable from here, so a default Parser's output is
        # byte-identical. Supplied, `parse_docx_content` finishes the substitution the
        # download pipeline has always done, through the SAME implementation
        # (`read.mentions.resolve_mentions`) — which is what makes the documented in-process
        # recipe and the `download` command produce the same Markdown for the same document
        # instead of quietly differing by one line. Keyword-only, like the sheets seams, so
        # every existing `Parser(config)` construction is unchanged.
        self.read_client = read_client
        # The per-PARSE accumulators live on the instance, but they are scoped
        # per parse: both parse entries reset them first (LD-080), so two sequential
        # parses on one Parser are independent (no doubled token lists / merged
        # block_maps). __init__ seeds them via the same helper for a clean initial
        # state. See `_reset_accumulators`.
        self._reset_accumulators()
        # Load the registry
        self.registry = get_registry()
        # The ONE renderer over the model. Escape-literals policy stays at its
        # default (OFF = raw passthrough); nothing flips it (Decision Log #3).
        # use_html_tags is fed from config so the renderer's styled-run
        # composition (bold/italic/strike as HTML tags) matches config exactly.
        self.renderer = MarkdownRenderer(
            use_html_tags=self.config.output.use_html_tags
        )

    def _reset_accumulators(self) -> None:
        """(Re)seed the per-PARSE accumulators to empty (LD-080).

        Called from ``__init__`` for a clean initial state, and as the FIRST
        statement of both parse entries so each parse starts fresh — two sequential
        parses on one Parser are independent (no doubled token lists / merged
        block_maps). The handlers APPEND to these during a parse:

        * ``img_tokens`` / ``board_tokens`` — image / whiteboard tokens the T1
          pipeline downloads + substitutes.
        * ``file_tokens`` — queued type-23 file-attachment tokens (LD-040); fetched
          only when ``config.output.download_attachments`` is True (opt-in).
        * ``mention_user_ids`` — distinct @mention open_ids collected offline-pure
          (LD-053); resolved to display names by the download pipeline (dedup,
          first-seen order ⇒ deterministic within a run).
        * ``reference_notes`` — one record per reference this document makes to content
          living OUTSIDE it (embedded sheet 30, embedded Base 18/53, synced block 50) and
          whether the run actually fetched it (LD-334). Appended by the same handlers that
          build those nodes, from the node's own state — so the end-of-download summary is a
          projection of the tree, never a second reading of the Markdown. Collecting is
          offline-pure: zero API calls, no deep read triggered. Consumed by
          ``read.download`` (see :mod:`larkdocio.read.references`).
        * ``_unknown_blocks`` — one entry per DISTINCT block type this parse met no handler
          for, written by :meth:`_note_unknown_block` — the same call that emits the
          ``Unknown block type N …`` warning, so the log line and the structured report are
          one decision and cannot disagree (LD-657). Read through the
          :attr:`unknown_block_types` projection, never directly.
        * ``block_map`` — id → source Block, populated by the parse entries.
        """
        self.img_tokens: List[str] = []
        self.board_tokens: List[str] = []
        self.file_tokens: List[str] = []
        self.mention_user_ids: List[str] = []
        self.reference_notes: List[ReferenceNote] = []
        self._unknown_blocks: Dict[Any, Dict[str, int]] = {}
        self.block_map: Dict[str, Any] = {}

    @property
    def unknown_block_types(self) -> List[Dict[str, int]]:
        """What this document used that this library does not model — as DATA.

        One entry per **distinct** block type with no registered handler, in first-seen order
        (the ``mention_user_ids`` precedent: dedup + first-seen ⇒ deterministic within a run,
        with no sort key to invent for a value the API chooses). Each entry answers four keys,
        all ints:

        * ``block_type`` — the unmodelled type, as Lark numbered it.
        * ``count`` — how many blocks of that type this document carried.
        * ``containers`` — how many of those carried children, whose subtree was surfaced at
          the unknown block's own depth (Decision e). The remainder — ``count - containers`` —
          were leaves, and a leaf unknown emits nothing at all.
        * ``children`` — how many child blocks those containers preserved.

        **No block ids ride along, deliberately.** The
        question this answers is only which block types a document used that the
        library does not model, and nothing beyond that — and
        an id list would make the answer grow with the document rather than with its
        vocabulary, turning a per-run summary into a per-block log by another name. Per-block
        detail already has two homes: the warning, for a human reading one document, and the
        ``--dump`` sidecar, for a machine that wants the raw payload.

        The list and its entries are **copies**: a caller may mutate what it is handed without
        reaching this parse's state.
        """
        return [dict(entry) for entry in self._unknown_blocks.values()]

    def _note_unknown_block(self, b: Any) -> None:
        """Record ONE unregistered block **and** emit the warning that reports it (LD-657).

        The two used to be one statement and one absence: the branch warned, and a programmatic
        caller who wanted the same fact had to attach a handler and parse the sentence. Both now
        leave from here, off the same locals, so no future branch can warn without reporting (a
        consumer's migration silently loses a type) or report without warning (the frozen line
        stops arriving). That is the point — not tidiness.

        **The warning's bytes are unchanged**, and are frozen by commitment until the consumer
        has migrated onto :attr:`unknown_block_types`; the text becomes free to change only in a
        later, separately named release. ``block_type`` and ``children`` are read into locals
        first, so the report is built from exactly the values the message prints.
        """
        block_type = b.block_type
        children = len(b.children or [])
        entry = self._unknown_blocks.setdefault(
            block_type,
            {"block_type": block_type, "count": 0, "containers": 0, "children": 0},
        )
        entry["count"] += 1
        if children:
            entry["containers"] += 1
            entry["children"] += children
        logger.warning(f"Unknown block type {block_type} (block_id={b.block_id}, parent_id={b.parent_id}, children={children}) — content may be missing from output.")

    def parse_docx_content(self, doc_id: str, blocks: List[Any]) -> str:
        """Parse ``blocks`` and return the document's **Markdown projection**.

        With a ``read_client`` injected (see ``__init__``) the @mention open ids collected
        during the render are resolved to display names before the Markdown is returned —
        the same substitution, through the same code, that the ``download`` command applies,
        so the two paths agree byte-for-byte. Without one, every mention stays a raw
        ``@ou_id`` and no contacts call is made. Resolution never fails a read: an
        unresolvable id keeps its raw form.
        """
        self._reset_accumulators()
        for block in blocks:
            self.block_map[block.block_id] = block

        # Build the document object tree, then serialize it ONCE (the spine no
        # longer stitches strings — LD-031).
        markdown = self.renderer.render(self._build_document(doc_id, blocks))

        # The only network the parser can do, and only when a caller opted in by handing
        # over a client (LD-173). `parse_docx_tree` deliberately does NOT resolve: it hands
        # back the object tree, where a mention is a node carrying its open id and a display
        # name would be a lossy substitution into it.
        if self.read_client is not None:
            markdown = resolve_mentions(
                markdown,
                self.mention_user_ids,
                self.read_client,
                enabled=self.config.output.resolve_mentions,
            )

        return markdown

    def parse_docx_tree(self, doc_id: str, blocks: List[Any]) -> Node:
        """Assemble and return the parsed document node tree WITHOUT rendering it.

        The non-rendering counterpart of :meth:`parse_docx_content`: it populates the
        block map and builds the same root :class:`Node` tree (via
        :meth:`_build_document`), but returns the tree instead of its Markdown. The
        writer's anchor resolver (``larkdocio.write.resolve``) needs the
        assembled tree — the ``block_id`` provenance on each block node is the
        addressing key. This is purely ADDITIVE: :meth:`parse_docx_content` is
        untouched, so reader Markdown output is byte-identical (goldens zero-drift);
        rendering the returned tree reproduces :meth:`parse_docx_content` exactly.
        """
        self._reset_accumulators()
        for block in blocks:
            self.block_map[block.block_id] = block
        return self._build_document(doc_id, blocks)

    def _build_document(self, doc_id: str, blocks: List[Any]) -> Node:
        """Build the document ROOT node.

        Normally the page(1) block (present in the payload). If that block is
        absent, synthesize a headless :class:`DocumentNode` from the top-level
        children (``parent_id == doc_id``) — byte-identical to the prior string
        fallback that concatenated them with no separator.
        """
        entry_block = self.block_map.get(doc_id)
        if entry_block:
            return self.parse_docx_node(entry_block, 0)

        return DocumentNode(children=[
            self.parse_docx_node(block, 0)
            for block in blocks
            if block.parent_id == doc_id
        ])

    def parse_docx_node(self, b: Any, indent_level: int) -> Node:
        """Produce the typed model node for a block (the node-producing primitive).

        See the recursion/indent contract at the top of this module. Does NOT
        apply the list-item indent tab — the renderer's list-item serializer
        (`_list_item`) owns that, via the depth threaded through `render`.
        """
        if not b:
            # The empty sentinel a dangling child id resolves to: no source Block,
            # so nothing to stamp — block_id legitimately stays absent (LD-062).
            return RawBlock("")

        handler = self.registry.get(b.block_type)
        if handler is None:
            # Genuinely-unknown type (no registered handler). Warn ONCE naming the
            # type + block_id (unchanged message shape), then render its children
            # TRANSPARENTLY (LD-045, Decision e) — build child nodes
            # at this block's OWN depth and carry them on an UnknownBlockNode the
            # renderer emits with no markup of the unknown block's own (the
            # view/grid precedent). This replaces the old warn+drop-subtree, which
            # silently lost an unknown CONTAINER's entire subtree (the agenda /
            # file-in-view class). A leaf unknown (no children) still emits nothing.
            # Design ruling (Decision e): known types keep their registered
            # handlers, so this warn stays a MEANINGFUL signal.
            # ONE call, because the warning and the structured report
            # (`unknown_block_types`, LD-657) are one decision: `_note_unknown_block`
            # records the type and emits the unchanged warning off the same locals.
            self._note_unknown_block(b)
            node = UnknownBlockNode(children=self._child_nodes(b, indent_level))
        else:
            # Every registered handler returns a model Node (the T2 migration is
            # complete). The LD-024 strangler shim's legacy-string arm — which
            # wrapped a bare Markdown string in a RawBlock — was removed in LD-032;
            # the handler's node is returned directly and the renderer serializes it.
            node = handler(self, b, indent_level)

        # Thread the SOURCE block_id onto the node (LD-062):
        # consumed-into-model, dropped-at-render (the LD-042 colors pattern) so a
        # future writer can recover which live block a node came from, while the
        # renderer keeps ignoring it (byte-identical output). Stamp IN PLACE so a
        # handler's own node object is returned unchanged (the `is` identity
        # contract in test_strangler_shim), and guard on `isinstance(node, Node)`
        # so an (illegal) bare-string handler return passes straight through
        # un-stamped to surface its TypeError at the renderer, exactly as before.
        #
        # The block-level review anchors ride along on the same stamp (LD-158): a
        # `comment_ids` list is a field on `Block` itself, not on one block kind, so
        # stamping it in this ONE primitive is what makes the capture type-blind —
        # every registered handler's node, plus the unknown-type fallback, gets it
        # for free. Same contract: consumed-into-model, dropped-at-render (the
        # renderer never reads it), so output stays byte-identical. The raw attribute
        # is passed through UNCHANGED — absent stays None and a present-but-empty
        # list stays [], because those are different facts to a future writer, and
        # the ids keep the API's own order (no sort, no dedup).
        #
        # The SOURCE block type rides the same stamp (LD-231), for the same reason and
        # under the same contract: it is a field on `Block` itself, the renderer's
        # default output never reads it, and the block-identity projection needs it to
        # say whether a block is editable or conserved. Stamping it here is what makes
        # that answer type-blind — including for the unknown-type fallback above, whose
        # node class deliberately says nothing about WHICH unhandled type it was.
        if isinstance(node, Node):
            node.block_id = b.block_id
            node.comment_ids = getattr(b, "comment_ids", None)
            node.block_type = getattr(b, "block_type", None)
        return node

    def _child_nodes(self, b: Any, indent_level: int) -> List[Node]:
        """Recurse a block's children to typed NODES at ``indent_level``.

        The shared child-recursion primitive (the six-times-repeated per-handler
        loop, consolidated here): resolve each child id in ``b.children`` and build
        its typed node at ``indent_level``. A dangling child id resolves to no
        block and yields the empty ``RawBlock`` sentinel via
        :meth:`parse_docx_node`. The list family (R-S1) is the first caller — it
        recurses at ``indent_level + 1``; R-S2..S4 move the remaining container
        families onto this helper as their carriage flips to child nodes.
        """
        return [
            self.parse_docx_node(self.block_map.get(cid), indent_level)
            for cid in (b.children or [])
        ]
