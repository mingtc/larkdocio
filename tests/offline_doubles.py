"""The offline double pool the guide-recipe harness stages on (LD-310).

**Why this module exists.** ``tests/guide_recipes.py`` had grown to 4,492 lines and was
cleanly two things: this pool of ``Offline*`` network doubles + the stage that installs
them, and the recipe corpus (the ``_check_*`` post-conditions and ``RECIPE_SPECS``) that
holds the shipped guide's ``### Recipe:`` blocks true. One file meant a recipe edit and a
double edit were the same file — which is why the 2026-08-03 resume plan had to serialise
"ONE GUIDE.md writer per wave". LD-310 cut the pool out here; ``guide_recipes``
**re-exports every name below**, so all 30 importing test modules stayed byte-unchanged and
``import guide_recipes as gr`` keeps resolving ``gr.OfflineBaseReadClient``, ``gr.stage``
and the rest.

**What lives here:** the fixture payload constants + :func:`fixture_block_dicts`, the 17
``Offline*`` doubles, the zero-Markdown call spy the stage installs (:func:`markdown_calls`
and its machinery — it is installed by :meth:`OfflineStage.install`, so it is stage
machinery, not guide machinery), the anti-drift :data:`DOUBLE_PAIRS` /
:func:`double_signature_mismatches`, and :class:`OfflineStage` / :func:`stage`.

**What deliberately stays in ``guide_recipes``:** everything that reads the *guide* — the
fence extraction, the static-analysis helpers, :func:`guide_recipes.run_recipe`, the
``_check_*`` post-conditions and ``RECIPE_SPECS``. The dependency is **one-way** (
``guide_recipes`` → ``offline_doubles``); the single back-edge, :meth:`OfflineStage.run`
needing ``run_recipe``, is a call-time import so there is no cycle.

**Nothing in here changed behaviour in the split.** Not one canned payload, not one raised
exception, not one recorded call list — the doubles' bodies moved verbatim.
"""
import copy
import functools
import importlib
import inspect
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from larkdocio.common import auth as _auth_module
from larkdocio.common.destination import require_destination
from larkdocio.sheets.client import SheetsReadClient as _ShippedSheetsReadClient
from larkdocio.sheets.export_reader import SheetsExportReader

#: The SHIPPED spreadsheet walk, captured at import — BEFORE any stage patches
#: ``larkdocio.sheets.client.SheetsReadClient`` to the double below. Reaching for the
#: patched name at call time would make the double call itself (LD-383).
_SHIPPED_READ_SPREADSHEET = _ShippedSheetsReadClient.read_spreadsheet


# --------------------------------------------------------------------------- #
# 1. The zero-Markdown CALL SPY — the level thesis, made executable.            #
#                                                                               #
# The claim the guide's level section makes is that Markdown is opt-in at        #
# exactly three call sites, so an object-level path can go from reading a        #
# document to changing it and produce none. A recipe's *source* not naming       #
# those calls is weak evidence — an engine could reach for one internally — so   #
# the stage wraps all three and COUNTS. The object-level recipes then assert     #
# ZERO, and the projection recipes prove the spy is not vacuous by tripping it.  #
# --------------------------------------------------------------------------- #

#: ``(module, class or None, attribute)`` per Markdown call site. ``compose`` is patched at
#: BOTH the package re-export (what a recipe imports) and its defining module (what
#: ``compose_insert`` reaches for internally), so neither route escapes the count.
MARKDOWN_CALL_SITES = (
    ("larkdocio.read.parser", "Parser", "parse_docx_content"),
    ("larkdocio.sheets.table", None, "render_spreadsheet"),
    # LD-251 — the Base projection, patched at BOTH the defining module and the package
    # re-export (a recipe may import either), for the same reason ``compose`` is.
    ("larkdocio.base.read", None, "read_base_markdown"),
    ("larkdocio.base", None, "read_base_markdown"),
    ("larkdocio.write", None, "compose"),
    ("larkdocio.write.compose", None, "compose"),
)

#: ``{attribute: call count}`` for the recipe most recently run on a stage. Cleared by
#: :meth:`OfflineStage.install`, so a count is always per-run and cannot leak between tests.
_MARKDOWN_CALLS: Dict[str, int] = {}


def markdown_calls() -> Dict[str, int]:
    """``{call site: how many times the staged run called it}`` — the zero-Markdown spy.

    Every site is present as a key (at ``0`` when untouched), so an assertion of "no Markdown
    call happened" cannot be satisfied by a site the spy forgot to install.
    """
    return dict(_MARKDOWN_CALLS)


def _reset_markdown_calls() -> None:
    """Zero every counter — called on install AND before each run.

    Per-**run**, not per-stage: one stage legitimately runs a recipe more than once (a
    mutation probe, then the shipped text through the same runner), and a counter that
    accumulated across those runs would make the second run inherit the first one's calls.
    """
    _MARKDOWN_CALLS.clear()
    for _module_name, _class_name, attr in MARKDOWN_CALL_SITES:
        _MARKDOWN_CALLS[attr] = 0


def _counting(name: str, original):
    """``original`` wrapped so every call bumps ``_MARKDOWN_CALLS[name]``, then delegates.

    ``functools.wraps`` keeps ``inspect.signature`` truthful through the wrapper (it follows
    ``__wrapped__``), so a signature-introspecting guard cannot be fooled by the spy.
    """

    @functools.wraps(original)
    def spy(*args, **kwargs):
        _MARKDOWN_CALLS[name] = _MARKDOWN_CALLS.get(name, 0) + 1
        return original(*args, **kwargs)

    return spy


# --------------------------------------------------------------------------- #
# 2. The offline doubles — ONLY the network boundary.                            #
# --------------------------------------------------------------------------- #

_FIXTURE_TITLE = "Q3 Board Update"
_FIXTURE_QUOTE = "Revenue grew 12.4% in Q3."

#: The review anchor the fixture paragraph carries, and the id the comments double answers
#: for. One constant so the block, the double and the recipe cannot drift apart (LD-159).
_FIXTURE_COMMENT_ID = "7667710952829095653"
#: The author of the fixture comment — a RAW open id, exactly as the API reports one. There is
#: deliberately no display name anywhere in this double: the library never resolves one, so a
#: double that offered one would let a recipe teach something untrue.
_FIXTURE_COMMENT_AUTHOR = "ou_examplebot0000000000000000000001"
_FIXTURE_COMMENT_TEXT = "Is this figure final? Audit is still pending."

#: The @mention ids the **mention-bearing** fixture carries (LD-173, dogfood F3), and the
#: names the read double's contacts leg answers with. FOUR SHAPES in ONE paragraph, on
#: purpose: an id the directory resolves, an id it does not answer for at all, an id whose
#: name fields are all null (the shape the 2026-07-29 field-scope diagnosis turned on — the
#: resolver omits it, so it is indistinguishable from the absent one *in the output* and
#: must degrade the same way), and — by holding several in one block — the MIXED case. A
#: single-shape fixture would let a resolver that dropped the degrade path pass.
_FIXTURE_MENTION_RESOLVED = "ou_exampleowner00000000000000000001"
_FIXTURE_MENTION_UNKNOWN = "ou_00000000000000000000000000000000"
_FIXTURE_MENTION_NULL_NAMED = "ou_examplenullnamed0000000000000001"
_FIXTURE_MENTION_NAME = "Example User"
#: What the contacts double resolves. The null-named and unknown ids are ABSENT from it —
#: exactly what ``Client.batch_get_user_names`` returns for them (a user with no usable name
#: field is omitted, and an id the directory does not cover never comes back).
_FIXTURE_MENTION_NAMES = {_FIXTURE_MENTION_RESOLVED: _FIXTURE_MENTION_NAME}


def fixture_block_dicts(
    doc_token: str, *, empty: bool = False, mentions: bool = False,
) -> List[dict]:
    """The docx payload the offline read double serves for ``doc_token``.

    ``empty=False`` → a page + an ``Overview`` heading + the paragraph the write recipes
    anchor on. ``empty=True`` → a page with **no body blocks at all** (the F15 case: no
    quote to anchor to, so ``APPEND_INTO`` the page node is the only way in).

    ``mentions=True`` (LD-173) appends ONE extra paragraph carrying the four @mention shapes
    above. It is **opt-in per stage** precisely so every other recipe's document — and so
    every other recipe's Markdown — stays byte-identical: the mention-bearing document is
    served only to the tests that are about mention resolution.

    **The page block's ``block_id`` IS the document token** — that is how a real docx
    payload comes back, and it is what makes the recipes *parameterized by URL*: the
    recipe derives its token from whatever URL you paste, and the double serves a payload
    keyed to that token, exactly as Lark would. (Getting this wrong is silent: the parser
    falls back to a headless document and every anchor refuses ``not-found``.)
    """
    root = {
        "block_id": doc_token,
        "parent_id": "",
        "block_type": 1,
        "page": {"elements": [{"text_run": {"content": _FIXTURE_TITLE}}]},
        "children": [] if empty else ["h1"],
    }
    if empty:
        return [root]
    blocks = [
        root,
        {
            "block_id": "h1", "parent_id": doc_token, "block_type": 3,
            "heading1": {"elements": [{"text_run": {"content": "Overview"}}]},
            "children": ["p1"] + (["p2"] if mentions else []),
        },
        {
            "block_id": "p1", "parent_id": "h1", "block_type": 2,
            "text": {"elements": [{"text_run": {"content": _FIXTURE_QUOTE}}]},
            "children": [],
            # A REVIEW ANCHOR on the one paragraph the recipes work with (LD-159). Real docx
            # blocks carry this list whenever a reviewer commented there, and the comments
            # recipe's whole point is going from a block to what a reviewer said about it — so
            # without an anchored block that recipe could execute only over an empty result and
            # would teach nothing. It costs no output: the field is consumed into the model and
            # dropped at render, so every other recipe's Markdown is byte-identical.
            "comment_ids": [_FIXTURE_COMMENT_ID],
        },
    ]
    if mentions:
        blocks.append({
            "block_id": "p2", "parent_id": "h1", "block_type": 2,
            "text": {"elements": [
                {"text_run": {"content": "Owner "}},
                {"mention_user": {"user_id": _FIXTURE_MENTION_RESOLVED}},
                {"text_run": {"content": ", reviewers "}},
                {"mention_user": {"user_id": _FIXTURE_MENTION_UNKNOWN}},
                {"text_run": {"content": " and "}},
                {"mention_user": {"user_id": _FIXTURE_MENTION_NULL_NAMED}},
                {"text_run": {"content": "."}},
            ]},
            "children": [],
        })
    return blocks


class _WikiNode:
    """The ``get_wiki_node_info`` reply shape the download pipeline consumes."""

    def __init__(self, obj_type, obj_token):
        self.obj_type = obj_type
        self.obj_token = obj_token


def _documents_for(double_cls) -> "OfflineDocuments":
    """The document store a double must use — installed per stage, never cached on the class.

    :meth:`OfflineStage.install` monkeypatches ``documents`` onto both doubles, so the store is
    **fresh per test** and torn down with the monkeypatch. Deliberately no lazy fallback: a
    double instantiated outside a stage would otherwise quietly mint a store that outlives the
    test and leaks writes into the next one, which is the one bug an offline harness must not
    have.
    """
    store = getattr(double_cls, "documents", None)
    assert store is not None, (
        f"{double_cls.__name__} was used without an OfflineStage — call "
        "guide_recipes.stage(monkeypatch, tmp_path) so the doubles share one per-test document "
        "store"
    )
    return store


class OfflineDocument:
    """One in-memory docx the read and write doubles **share** (LD-137).

    Before LD-137 each double served :func:`fixture_block_dicts` afresh, so a write was
    invisible to the next read. That was enough while every recipe read once and wrote once —
    but the by-id recipe teaches the consumer loop ``apply()`` → ``created_block_ids`` →
    **re-read** → anchor the follow-up by id, and a read that cannot see what was just created
    would make that recipe untestable (or, worse, testable only against a hand-faked id).

    So the stage builds one of these per document token and both doubles go through it:
    ``create_children`` really appends blocks (handing back the ids it minted, and threading
    them into the parent's ordered ``children``), ``_patch_block`` really rewrites a block's
    runs, ``batch_delete`` really removes a child range. Everything else about the doubles is
    unchanged, and a document nobody writes to serves exactly the fixture it always did.
    """

    def __init__(self, doc_token: str, *, empty: bool = False, mentions: bool = False):
        blocks = fixture_block_dicts(doc_token, empty=empty, mentions=mentions)
        self.order: List[str] = [b["block_id"] for b in blocks]
        self.blocks: Dict[str, dict] = {b["block_id"]: dict(b) for b in blocks}
        self._minted = 0
        #: The whole-document ``revision_id`` (LD-139). Modelled the way Lark's really
        #: behaves — live-characterized on a disposable doc: ``1`` on a fresh document, **one
        #: bump per write call**, and **never** bumped by a read. Without this the armed
        #: handshake recipe could not run: ``dry_run(..., document_revision_id=…)`` +
        #: ``apply`` is a genuine compare-and-swap here, so a recipe that captured the
        #: revision at the wrong moment would refuse instead of quietly "passing".
        self.revision = 1
        #: LD-410 — the state each PAST revision described, snapshotted at the moment the
        #: revision advanced. It is what lets the historical read
        #: (``get_docx_content(..., document_revision_id=n)``) be exercised offline against a
        #: document that genuinely had two states, rather than against a re-served fixture
        #: that cannot tell a pinned read from a head one.
        self._history: Dict[int, List[dict]] = {}

    # -- reads ------------------------------------------------------------- #

    def block_dicts(self) -> List[dict]:
        """The whole document as block dicts — what the read double serves."""
        return [dict(self.blocks[bid]) for bid in self.order]

    def block_dicts_at(self, revision: int) -> List[dict]:
        """The document AS OF ``revision`` — and **head** for any revision never snapshotted.

        The fallback is not laziness, it is the measured behaviour: a revision past head is
        answered ``code 0`` with head's body and no marker, so a double that raised for an
        over-range pin would model an API that does not exist and would hide the one trap the
        historical read cannot detect.
        """
        return self._history.get(revision, self.block_dicts())

    def _bump(self) -> None:
        """Advance the revision, keeping what the OLD one described."""
        self._history[self.revision] = self.block_dicts()
        self.revision += 1

    def get(self, block_id: str) -> dict:
        """One block dict — what ``get_block`` serves. ``KeyError`` if it is gone."""
        return dict(self.blocks[block_id])

    def text_of(self, block_id: str) -> str:
        """The block's ``text_run`` text (the assertion surface for a recipe check)."""
        block = self.blocks[block_id]
        for value in block.values():
            if isinstance(value, dict) and isinstance(value.get("elements"), list):
                return "".join(
                    e["text_run"].get("content", "")
                    for e in value["elements"] if e.get("text_run") is not None
                )
        return ""

    # -- writes ------------------------------------------------------------ #

    def _mint(self, parent_id: str, payload: dict) -> str:
        self._minted += 1
        block_id = f"new{self._minted - 1}"
        block = dict(payload)
        block["block_id"] = block_id
        block["parent_id"] = parent_id
        block.setdefault("children", [])
        self.blocks[block_id] = block
        self.order.append(block_id)
        return block_id

    def _provision_table_cells(self, table_id: str) -> None:
        """Auto-provision an R×C cell grid under a freshly created table (LD-138).

        **Lark does this, not the engine** (live-proven by the W2/LD-135 gates): creating a
        ``block_type: 31`` from its grid property makes the API materialize the whole cell
        family — each cell (type 32) wrapping one empty inner text block (type 2) — and the
        engine then fills each cell by patching that inner block. So a harness that stores
        the create payload and stops is not a slow Lark, it is a *different* API: table
        creation would appear to work while the authored cell text went nowhere, and
        ``_fill_table_cells`` would raise "provisioned with 0 cells". Modelling the
        provisioning is what lets the shipped two-step create run for real offline.
        """
        table = self.blocks[table_id]
        prop = (table.get("table") or {}).get("property") or {}
        rows, cols = int(prop.get("row_size") or 0), int(prop.get("column_size") or 0)
        cell_ids = []
        for _ in range(rows * cols):
            cell_id = self._mint(table_id, {"block_type": 32, "table_cell": {}})
            inner_id = self._mint(cell_id, {"block_type": 2, "text": {"elements": []}})
            self.blocks[cell_id]["children"] = [inner_id]
            cell_ids.append(cell_id)
        table["children"] = cell_ids

    #: The docx **file attachment** and the **view wrapper** Lark answers for one (LD-470).
    #: Modelled here for the same reason the image bind is: a file create really does bring
    #: **two** blocks into existence and really does hand back the WRAPPER's id, so a double
    #: that minted one block would make the shipped op's whole wrapper-resolution leg
    #: unreachable offline — and the guide's attachment recipe untestable.
    _FILE_BLOCK_TYPE = 23
    _FILE_VIEW_WRAPPER_BLOCK_TYPE = 33

    def create_children(self, parent_id: str, children: List[dict], index: int) -> List[str]:
        self._bump()
        made = []
        for payload in children:
            if payload.get("block_type") == self._FILE_BLOCK_TYPE:
                # TWO blocks, and the id that goes into the parent's list is the WRAPPER's.
                wrapper_id = self._mint(parent_id, {
                    "block_type": self._FILE_VIEW_WRAPPER_BLOCK_TYPE, "view": {}})
                file_id = self._mint(wrapper_id, dict(payload))
                self.blocks[wrapper_id]["children"] = [file_id]
                made.append(wrapper_id)
                continue
            block_id = self._mint(parent_id, payload)
            if payload.get("block_type") == 31:
                self._provision_table_cells(block_id)
            made.append(block_id)
        self._attach(parent_id, made, index)
        return made

    def _attach(self, parent_id: str, made: List[str], index: int) -> None:
        """Thread newly-minted ids into ``parent_id``'s ordered ``children`` at ``index``."""
        parent = self.blocks[parent_id]
        kids = list(parent.get("children") or ())
        at = len(kids) if index is None or index < 0 else index
        parent["children"] = kids[:at] + made + kids[at:]

    def create_descendant(self, parent_id: str, children_id: List[str],
                          descendants: List[dict], index: int) -> dict:
        """The ``descendant`` subtree create (LD-482), modelled for the same reason the table
        cell provisioning above is: the shipped engine takes this route for a **table on its
        own**, so a double that lacked it would make the one-call table route — and any recipe
        that authors a table — unreachable offline while the create-then-fill route stayed
        testable. That is a *different* API, not a slower one.

        The body is the flat, caller-minted-temp-id shape
        :func:`larkdocio.write.encode.table_subtree` produces, and the answer is Lark's:
        ``block_id_relations`` mapping each temporary id to the real one, plus the created
        top-level ``children``. The relations are returned in **minting order**, which is not
        the order the shipped ``_minted_id`` may assume — it looks its temp id up by name.
        """
        self._bump()
        by_temp = {d["block_id"]: d for d in descendants}
        minted: Dict[str, str] = {}

        def materialise(temp_id: str, parent_real: str) -> str:
            payload = {k: v for k, v in by_temp[temp_id].items()
                       if k not in ("block_id", "children")}
            block_id = self._mint(parent_real, payload)
            minted[temp_id] = block_id
            self.blocks[block_id]["children"] = [
                materialise(child, block_id)
                for child in (by_temp[temp_id].get("children") or ())
            ]
            return block_id

        roots = [materialise(temp_id, parent_id) for temp_id in children_id]
        self._attach(parent_id, roots, index)
        return {
            "block_id_relations": [
                {"temporary_block_id": temp_id, "block_id": block_id}
                for temp_id, block_id in minted.items()
            ],
            "children": [self.get(block_id) for block_id in roots],
        }

    def patch(self, block_id: str, update: dict) -> None:
        self._bump()
        block = self.blocks[block_id]
        # LD-433 — the image BIND. Modelled because the whole point of the shipped op is that
        # the upload's own success is not a bind: a double that answered success without
        # moving the block's token would let the read-back verdict "pass" vacuously.
        replace_image = update.get("replace_image")
        if replace_image is not None:
            block["image"] = dict(block.get("image") or {},
                                  token=replace_image.get("token", ""))
            return
        # LD-470 — the attachment BIND, modelled for the same reason and on the same terms as
        # the image bind above: the upload's own success is not a bind, and a double that
        # answered success without moving the block's token would let the shipped op's
        # read-back verdict "pass" while proving nothing.
        replace_file = update.get("replace_file")
        if replace_file is not None:
            block["file"] = dict(block.get("file") or {},
                                 token=replace_file.get("token", ""))
            return
        # LD-575 — the table-grow APPEND. Modelled for the same reason the two binds above
        # are: Lark really does provision the new row's cells (each wrapping an inner text
        # block), and a double that answered success without lengthening the grid would let
        # the shipped grow op's read-back report an empty ``created_block_ids`` while
        # "passing" — the receipt-shaped silence the op exists to end. The behaviour modelled
        # is the MEASURED one: it appends at the end and leaves every pre-existing cell id
        # untouched and in order (``_grow_table_grid``'s docstring names the captures).
        if update.get("insert_table_row") is not None:
            self._append_table_row(block_id)
            return
        # LD-597 — the checkbox FLIP: ``update_text_style`` with field mask ``2``, the
        # endpoint's fifth oneof (``larkdocio.write.apply.build_todo_done_update``, which is
        # where the spelling and the mask are cited from — neither is invented here).
        # Modelled for the same reason as the three arms above, and the shipped guide is why
        # it earns its keep now: the round-trip recipe carries a WORKED FLIP, and a flip is
        # applied as a BARE done-bit patch (``_apply_narrative`` skips the text patch when
        # the live text already equals the replacement), so a double that answered success
        # without moving the bit would let that recipe — and the read-back it teaches —
        # "pass" against a checkbox that never moved. That is the receipt-shaped silence the
        # flip op exists to end, and the one an example graded by an inert double would
        # manufacture. Only ``done`` moves, exactly as the shipped body carries only
        # ``done``: the item's text, its children and every other property stay untouched,
        # which is mask ``2``'s measured blast radius (cited at the builder, not re-derived).
        style = (update.get("update_text_style") or {}).get("style")
        if style is not None:
            unmodelled = set(style) - {"done"}
            assert not unmodelled, (
                f"update_text_style carried {sorted(unmodelled)}, which this double does not "
                "model — a silent no-op here would grade a write nobody applied as a pass"
            )
            self._set_done(block_id, bool(style["done"]))
            return
        elements = (update.get("update_text_elements") or {}).get("elements")
        if elements is None:
            return
        for key, value in block.items():
            if isinstance(value, dict) and isinstance(value.get("elements"), list):
                block[key] = dict(value, elements=[dict(e) for e in elements])
                return

    def _set_done(self, block_id: str, done: bool) -> None:
        """Move one block's checkbox — ``todo.style.done``, the field the reader reads.

        Written onto the block's text-bearing container (the ``todo`` key on a type-17
        block) rather than onto a key named here, so the arm cannot silently miss when the
        container is spelled differently — and the container's other keys, ``elements``
        included, are carried through untouched.
        """
        block = self.blocks[block_id]
        for key, value in block.items():
            if isinstance(value, dict) and isinstance(value.get("elements"), list):
                block[key] = dict(
                    value, style=dict(value.get("style") or {}, done=done))
                return

    def _append_table_row(self, table_id: str) -> None:
        """One more row's worth of cells at the END of a table's ordered ``children``.

        Reuses :meth:`_mint` so an appended cell gets an id from the same minting sequence a
        created one does, and re-reads ``column_size`` off the block rather than remembering
        it — a grown table's own property is the only thing that knows how wide it is.
        """
        table = self.blocks[table_id]
        prop = (table.get("table") or {}).get("property") or {}
        columns = int(prop.get("column_size") or 0)
        if not columns:
            return
        appended = []
        for _ in range(columns):
            cell_id = self._mint(table_id, {"block_type": 32, "table_cell": {}})
            inner_id = self._mint(cell_id, {"block_type": 2, "text": {"elements": []}})
            self.blocks[cell_id]["children"] = [inner_id]
            appended.append(cell_id)
        table["children"] = list(table.get("children") or ()) + appended
        prop["row_size"] = int(prop.get("row_size") or 0) + 1

    def batch_delete(self, parent_id: str, start_index: int, end_index: int) -> None:
        self._bump()
        parent = self.blocks[parent_id]
        kids = list(parent.get("children") or ())
        removed, parent["children"] = kids[start_index:end_index], (
            kids[:start_index] + kids[end_index:])
        for block_id in removed:
            self.blocks.pop(block_id, None)
            if block_id in self.order:
                self.order.remove(block_id)


class OfflineDocuments:
    """The per-stage store of :class:`OfflineDocument`s, keyed by document token.

    Lazy by token because the recipes are **parameterized by URL** — the token comes from
    whatever URL is pasted (including the wiki-node variant the suite substitutes), and the
    document is materialized from the fixture on first touch.
    """

    def __init__(self, *, empty: bool = False, mentions: bool = False):
        self.empty = empty
        self.mentions = mentions
        self._docs: Dict[str, OfflineDocument] = {}
        #: ``{doc_token: {comment_id: {"user_id", "text", "replies": [reply_id]}}}`` — the
        #: comments the WRITE double created, shared with the comments READ double for the
        #: same reason the block store is shared: a recipe that creates a comment and then
        #: reads it back must be able to *see* it, or the read-back step teaches nothing. The
        #: read double still serves its captured anchored fixture as well, so the comments-read
        #: recipe's payload is unchanged.
        self.comments: Dict[str, Dict[str, dict]] = {}

    def for_token(self, doc_token: str) -> OfflineDocument:
        doc = self._docs.get(doc_token)
        if doc is None:
            doc = self._docs[doc_token] = OfflineDocument(
                doc_token, empty=self.empty, mentions=self.mentions)
        return doc

    def comments_for(self, doc_token: str) -> Dict[str, dict]:
        return self.comments.setdefault(doc_token, {})


@dataclass(frozen=True)
class _DocumentMeta:
    """The docx meta the read leg returns — the SDK ``Document``'s two load-bearing fields.

    ``revision_id`` is the whole-document staleness anchor (LD-139): the armed handshake
    recipe passes it to ``dry_run(..., document_revision_id=…)``, so it must be the *live*
    revision of the shared :class:`OfflineDocument`, not a constant.
    """

    document_id: str
    revision_id: int


class OfflineDocxReadClient:
    """Stands in for :class:`larkdocio.read.client.Client` at the HTTP boundary only.

    Serves the stage's :class:`OfflineDocument` as **real SDK ``Block`` objects**, so the
    recipe's ``Parser`` step is the shipped parser running on the shipped payload shape — and
    a **re-read after a write sees the write** (LD-137: the by-id recipe's second read must
    contain the blocks the first ``apply`` created). The constructor asserts it was handed real
    (env-resolved) credentials — which is what makes the recipes' ``init_env`` line
    load-bearing here.
    """

    #: set by :meth:`OfflineStage.install` — serve an empty document instead.
    empty_document: bool = False
    #: set by :meth:`OfflineStage.install` — the per-stage store shared with the write double.
    documents: Optional[OfflineDocuments] = None
    #: set by :meth:`OfflineStage.install` — what the contacts leg resolves (LD-173).
    user_names: Optional[Dict[str, str]] = None
    #: every id list the contacts leg was asked for, CLASS-level (the recipe builds its own
    #: client, so no instance is reachable from the recipe's namespace) and reset per stage.
    #: It is what lets a test assert the resolution cost — ONE call for a whole document.
    contact_calls: List[List[str]] = []

    def __init__(self, app_id: str, app_secret: str, domain: str):
        assert app_id and app_secret, (
            "the read client was constructed with empty credentials — the recipe's "
            "init_env(...) / get_read_credentials() chain did not resolve"
        )
        self.app_id, self.app_secret, self.domain = app_id, app_secret, domain
        self.calls: List[tuple] = []

    def get_docx_content(self, doc_token: str, document_revision_id=None):
        import harness  # tests/ is on sys.path (conftest)

        document = _documents_for(type(self)).for_token(doc_token)
        if document_revision_id is not None:
            # LD-410 — the HISTORICAL read. The pin gate and the metadata half are the
            # SHIPPED code running for real; only the transport is the double, and it serves
            # the state that revision described (head for a revision it never held, which is
            # the measured over-range behaviour rather than a convenience).
            from larkdocio.read.history import check_revision_pin, pinned_meta

            pin = check_revision_pin(document_revision_id)
            self.calls.append(("get_docx_content", doc_token, pin))
            return pinned_meta(doc_token, pin), harness.build_blocks(
                document.block_dicts_at(pin))

        self.calls.append(("get_docx_content", doc_token))
        blocks = document.block_dicts()
        # The real leg returns the SDK ``Document`` from ``GetDocumentRequest``, which
        # carries ``document_id`` + ``revision_id`` (LD-139: the whole-document staleness
        # anchor, free on the read that builds the tree). The double used to return a bare
        # ``object()``; a recipe that arms the guard needs the real fields.
        return _DocumentMeta(doc_token, document.revision), harness.build_blocks(blocks)

    def get_wiki_node_info(self, token: str):
        self.calls.append(("get_wiki_node_info", token))
        return _WikiNode("docx", token)

    def read_document_revision(self, doc_token: str):
        """The cheap change-detection anchor — one metadata call, no block tree (LD-471).

        The ledger recipe bounds its pin against this before spending a read on it, because an
        out-of-range revision is answered ``code 0`` with head's body and no marker. Recorded
        in ``calls`` like every other read, so the bound check is a step the suite can see.
        """
        self.calls.append(("read_document_revision", doc_token))
        return _documents_for(type(self)).for_token(doc_token).revision

    def batch_get_user_names(self, ids):
        """The contacts batch leg — the resolver the read path injects (LD-173).

        Answers ONLY for the ids the stage's directory covers and **omits** every other one,
        which is exactly the shipped client's contract: an id the contacts data range does
        not cover never comes back, and a user whose name / en_name / nickname are all null
        is dropped because there is nothing to substitute. So the degrade path in the fixture
        (an unknown id and a null-named one) is modelled by absence, not by a special case.
        """
        type(self).contact_calls.append(list(ids))
        self.calls.append(("batch_get_user_names", tuple(ids)))
        names = type(self).user_names or {}
        return {uid: names[uid] for uid in ids if uid in names}


class OfflineBaseReadClient:
    """Stands in for :class:`larkdocio.base.client.BaseReadClient` at the HTTP boundary only.

    Serves the **committed captures of one real Base** — the same three the Base golden is built
    from — round-tripped through the pinned SDK's own deserializer, so the recipe's
    ``read_base`` / ``render_base`` steps are the shipped assembler and the shipped renderer
    running on payload shapes Lark actually returned. Nothing about the read is faked above the
    transport: the field-order projection, the ragged-record widening rule, the Flow column's
    absent-with-reason marker and the date rendering in the app's own time zone are all real.

    The token is deliberately ignored: the recipe is parameterized by URL, and a Base URL's slug
    IS its ``app_token``, so whatever token the pasted URL yields gets this Base — exactly as the
    docx double serves a payload keyed to whatever document token it is asked for.
    """

    #: ``[(op, args)]`` — inspectable by a recipe check, and reset per stage.
    calls: List[tuple] = []

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the Base read client was constructed with empty credentials — the recipe's "
            "init_env(...) / get_read_credentials() chain did not resolve"
        )
        self.domain = domain

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_read_credentials
        from larkdocio.errors import LarkConfigError

        app_id, app_secret = get_read_credentials()
        if not (app_id and app_secret):
            raise LarkConfigError("no READ credentials in the environment (offline double)")
        return cls(app_id, app_secret, domain, **kwargs)

    @staticmethod
    def _captured():
        import base_captures  # tests/ is on sys.path (conftest)

        return base_captures.scratch_base()

    #: How many more reads must answer ``1254036 "Bitable is copying"`` before this Base is
    #: readable. Set by the schema double's ``copy_app``, because the copy is the one
    #: ASYNCHRONOUS Base operation and a double that answered instantly would let a recipe
    #: teach that the settle is decorative.
    copying: int = 0

    #: App tokens the schema double's ``delete_base`` has trashed. A read of one answers
    #: ``1002`` — a member of ``loss_preview.OBJECT_GONE_CODES`` — because that is what the live
    #: API answers and it is the ONLY proof a whole-Base delete landed (the delete's own
    #: ``code:0`` is acceptance, and the Drive metadata route keeps resolving the token). A
    #: double that kept serving a trashed Base would let the disposables recipe teach that the
    #: confirmation step is decorative.
    trashed_apps: List[str] = []

    #: The SCHEMA overlay (LD-263). A structural op is verified by a **read-back**, so the
    #: schema double has to actually change what this one serves — exactly as the record-write
    #: double has to move the revision. A double that landed nothing would make every
    #: structural op in a recipe report itself ``dropped``.
    app_name_override: Optional[str] = None
    extra_tables: List[tuple] = []
    table_renames: Dict[str, str] = {}

    @classmethod
    def _remember_kit(cls, table_id, fields):
        """Record a table create's inline column kit onto the existing ``created_fields``
        overlay, so the columns land on the SAME seam a ``create_field`` lands on.

        Reused rather than mirrored: a second overlay for "columns that arrived with their
        table" would be two answers to *what columns does this table have*, and the read-back
        under test asks exactly that question.
        """
        made = list(cls.created_fields)
        configured = dict(cls.created_field_properties)
        for offset, column in enumerate(fields or ()):
            field_id = f"fldKIT{len(made) + offset + 1:02d}"
            made.append((table_id, field_id, column["field_name"],
                         column.get("field_type"), column.get("ui_type") or "Text"))
            configured[(table_id, field_id)] = dict(column.get("properties") or {})
        cls.created_fields = made
        cls.created_field_properties = configured

    def get_app(self, app_token):
        type(self).calls.append(("get_app", app_token))
        if app_token in type(self).trashed_apps:
            from larkdocio.base.errors import raise_for_base_code

            raise_for_base_code(
                {"code": 1002, "msg": "app not exist"},
                context=f"read Base {app_token}")
        if type(self).copying:
            from larkdocio.base.errors import raise_for_base_code

            type(self).copying -= 1
            raise_for_base_code(
                {"code": 1254036, "msg": "Bitable is copying, please try again later."},
                context=f"read Base {app_token}")
        app = self._captured()[0]
        if type(self).app_name_override is not None:
            app = copy.copy(app)
            app.name = type(self).app_name_override
        return app

    #: How far the table revision has advanced under this stage's writes. A real Base moves
    #: it on every landed write, and the shipped apply engine reads it back to decide whether
    #: the write actually happened — so a double that held it constant would make every write
    #: in a recipe report itself ``dropped``.
    revision_bump: int = 0

    def list_tables(self, app_token):
        type(self).calls.append(("list_tables", app_token))
        tables = self._captured()[1]
        renames = type(self).table_renames
        extra = type(self).extra_tables
        if not (type(self).revision_bump or renames or extra):
            return self._proven(tables)
        moved = []
        for table in tables:
            clone = copy.copy(table)
            clone.revision = (getattr(table, "revision", 0) or 0) + type(self).revision_bump
            if clone.table_id in renames:
                clone.name = renames[clone.table_id]
            moved.append(clone)
        for table_id, name in extra:
            made = copy.copy(tables[0])
            made.table_id, made.name, made.revision = table_id, name, 0
            moved.append(made)
        return self._proven(moved)

    #: The VIEW overlay (LD-264). A view write is verified by a **read-back**, so the schema
    #: double has to change what this one serves — and a view a recipe filtered has to come
    #: back carrying that filter, with the server's own `condition_id` / `field_type`
    #: additions, or the shipped normalisation would never be exercised.
    views: Dict[str, dict] = {}

    def list_views(self, app_token, table_id):
        """The listing — and, as the live API does, it carries **no** ``property``."""
        type(self).calls.append(("list_views", app_token, table_id))
        return [_OfflineView(view_id, blob["view_name"], blob["view_type"])
                for view_id, blob in type(self).views.items()]

    def get_view(self, app_token, table_id, view_id):
        """The single-view read — the only one that carries ``property``, which is why a view
        write's read-back spends it."""
        type(self).calls.append(("get_view", app_token, table_id, view_id))
        blob = type(self).views[view_id]
        view = _OfflineView(view_id, blob["view_name"], blob["view_type"])
        view.property = _offline_view_property(blob.get("filter_info"),
                                              blob.get("hierarchy_config"),
                                              blob.get("hidden_fields"))
        return view

    #: The FIELD overlay (LD-291). A column op is verified by a read-back and the guided
    #: column-type migration is five of them in a row, so the schema double has to really
    #: author, rename and remove columns here — a double that served the captured field list
    #: unchanged would make every step of the migration report itself ``dropped``.
    created_fields: List[tuple] = []          # (table_id, field_id, name, type, ui_type)
    deleted_field_ids: List[tuple] = []       # (table_id, field_id)
    field_renames: Dict[tuple, str] = {}      # (table_id, field_id) -> new name

    #: The CELL overlay, the other half of the same story: the migration reads its copy back
    #: and compares it, so a write that changed nothing readable would make the verification
    #: refuse — correctly, and uselessly. Keyed ``(table_id, record_id) -> {name: wire value}``.
    cell_writes: Dict[tuple, dict] = {}

    #: The RECORD overlay (LD-296). A row-hierarchy recipe writes its tree with ordinary
    #: record creates and then READS THE TREE BACK, so a double whose creates were
    #: invisible to the next search would make the whole point unobservable. Keyed
    #: ``(table_id, record_id) -> {name: wire value}``, in creation order.
    created_records: List[tuple] = []       # (table_id, record_id, {name: value})

    #: The FIELD-PROPERTY overlay (LD-283). A created column's ``property`` is what makes a
    #: link column *point* anywhere and a select column *offer* anything, so a double that
    #: served ``property = None`` for everything it authored could not carry the link-target
    #: reading, the option list, or the difference between the two. Keyed
    #: ``(table_id, field_id) -> {the properties the create asked for}``.
    created_field_properties: Dict[tuple, dict] = {}

    #: The PAGING PROOF the destructive scan is required to ask for (LD-265, reached by
    #: LD-291's migration). The real client publishes the page bodies its last walk saw; this
    #: double's walks are single captured pages that really did end, so the proof it publishes
    #: is a reading rather than a claim. Set by every walk below, exactly as the real one does.
    _walk_pages: tuple = ()

    @property
    def api_calls(self):
        """What the real client publishes, and what the link resolver subtracts to price
        itself. A double that reported ``0`` would make every cost disclosure a recipe prints
        say *"no extra API calls"* — which would be teaching the opposite of the truth."""
        return len(type(self).calls)

    @property
    def last_walk_pages(self):
        return type(self)._walk_pages

    def _proven(self, items):
        type(self)._walk_pages = ({"items": list(items), "has_more": False,
                                   "page_token": None},)
        return items

    def list_fields(self, app_token, table_id):
        type(self).calls.append(("list_fields", app_token, table_id))
        per_table = self._captured()[2]
        if table_id not in per_table:
            # A table this stage's SCHEMA double created, or one inside a copy. A real copy
            # carries its parent's columns — including the `Lookup` (19) and `Stage` (24) the
            # fields API refuses to author — so the honest stand-in is the parent's field list.
            # The captured ids are always present, so the read recipe never reaches this.
            inherited = per_table[next(iter(per_table))][0]
            kitted = [(field_id, name, kind, ui)
                      for owner, field_id, name, kind, ui in type(self).created_fields
                      if owner == table_id]
            if not kitted:
                return self._proven(inherited)
            # A table created WITH an inline column kit has EXACTLY the kit — measured: the
            # locale-named default primary is not also there, and the kit's FIRST entry is the
            # primary one. A double that served both would let a test assert the older guess.
            return self._proven([
                self._kitted_column(inherited[0], table_id, made, primary=(offset == 0))
                for offset, made in enumerate(kitted)])
        fields = per_table[table_id][0]
        gone = {field_id for owner, field_id in type(self).deleted_field_ids
                if owner == table_id}
        renames = type(self).field_renames
        made = [(field_id, name, kind, ui)
                for owner, field_id, name, kind, ui in type(self).created_fields
                if owner == table_id]
        if not (gone or renames or made):
            return self._proven(fields)
        out = []
        for field in fields:
            if field.field_id in gone:
                continue
            clone = copy.copy(field)
            new_name = renames.get((table_id, field.field_id))
            if new_name is not None:
                clone.field_name = new_name
            out.append(clone)
        for field_id, name, kind, ui in made:
            if field_id in gone:
                continue
            clone = copy.copy(fields[0])
            clone.field_id, clone.type, clone.ui_type = field_id, kind, ui
            clone.field_name = renames.get((table_id, field_id), name)
            clone.property = _offline_field_property(
                ui, type(self).created_field_properties.get((table_id, field_id)),
                self._live_table_names())
            clone.is_primary = False
            out.append(clone)
        return self._proven(out)

    def _kitted_column(self, template, table_id, made, primary=False):
        """One column of an inline kit, cloned onto the captured shape the same way a
        ``create_field`` column is — one clone routine, not two."""
        field_id, name, kind, ui = made
        clone = copy.copy(template)
        clone.field_id, clone.type, clone.ui_type = field_id, kind, ui
        clone.field_name = name
        clone.property = _offline_field_property(
            ui, type(self).created_field_properties.get((table_id, field_id)),
            self._live_table_names())
        clone.is_primary = primary
        return clone

    def _live_table_names(self) -> dict:
        """``{table_id: name}`` for the tables that EXIST right now — the capture's plus this
        stage's creations, minus nothing (no double here deletes a table).

        It is what makes a link column's ``property.table_name`` a *reading* rather than an
        echo: Lark fills the name in when the target is alive and **omits it when the target
        table is gone**, which is the entire free dangling signature. A double that echoed the
        caller's ``table_id`` back with a name attached could never show the second state.
        """
        names = {table.table_id: table.name for table in self._captured()[1]}
        names.update({table_id: name for table_id, name in type(self).extra_tables})
        return names

    def batch_get_records(self, app_token, table_id, record_ids):
        """``POST …/records/batch_get`` — the second POST read, and the one link resolution
        spends its budget on.

        The body carries **three** lists, exactly as the captured one does: the records that
        came back, the ``absent_record_ids`` Lark could not find, and the
        ``forbidden_record_ids`` it would not hand over. The middle one is the whole reason a
        resolver need not treat a missing record as an error — the absence is reported *per
        id*, inside a ``code:0`` body — so a double that answered only ``records`` would make
        a deleted row indistinguishable from a broken read.
        """
        type(self).calls.append(("batch_get_records", app_token, table_id, tuple(record_ids)))
        by_id = {record.record_id: record for record in self.search_records(app_token, table_id)}
        found = [by_id[record_id] for record_id in record_ids if record_id in by_id]
        absent = [record_id for record_id in record_ids if record_id not in by_id]
        return _OfflineBatchGet(found, absent)

    @staticmethod
    def _cell_text(record, column):
        value = (record.fields or {}).get(column)
        if isinstance(value, list):
            return "".join(part.get("text", "") for part in value
                           if isinstance(part, dict))
        return "" if value is None else str(value)

    @classmethod
    def _narrow(cls, records, search_filter, sort):
        """Apply a read filter / sort to the served rows **for real**.

        A double that accepted the parameters and ignored them would teach a recipe exactly the
        R12 failure the shipped client is built against — ``code:0`` and the whole table. So the
        narrowing is genuine, over the same six operators the library ships, and the recipe's
        printed row count is a result rather than a decoration.
        """
        out = list(records)
        if search_filter is not None:
            body = search_filter.to_dict()
            groups = [body] + list(body.get("children") or ())

            def admits(record):
                for group in groups:
                    conditions = group.get("conditions") or ()
                    results = []
                    for condition in conditions:
                        text = cls._cell_text(record, condition["field_name"])
                        values = list(condition.get("value") or ())
                        operator = condition["operator"]
                        results.append({
                            "is": lambda: text in values,
                            "isNot": lambda: text not in values,
                            "contains": lambda: any(v in text for v in values),
                            "doesNotContain": lambda: not any(v in text for v in values),
                            "isEmpty": lambda: not text,
                            "isNotEmpty": lambda: bool(text),
                        }[operator]())
                    if not results:
                        continue
                    joined = (all(results) if group.get("conjunction", "and") == "and"
                              else any(results))
                    if not joined:
                        return False
                return True

            out = [record for record in out if admits(record)]
        for key in reversed(list(sort or ())):
            out.sort(key=lambda record: cls._cell_text(record, key.field.name),
                     reverse=key.desc)
        return out

    def search_records(self, app_token, table_id, *, filter=None, view_id=None, sort=None):
        type(self).calls.append(("search_records", app_token, table_id))
        assert view_id is None, (
            "the offline double serves ONE capture of a table and has no per-view row sets; a "
            "view-scoped read is proven live (tests/test_live_base_view_scoped_read.py), not in "
            "a recipe")
        records = self._captured()[2][table_id][1]
        writes = type(self).cell_writes
        made = [(record_id, body) for owner, record_id, body
                in type(self).created_records if owner == table_id]
        gone = {field_id for owner, field_id in type(self).deleted_field_ids
                if owner == table_id}
        names_gone = {field.field_name
                      for field in self._captured()[2][table_id][0]
                      if field.field_id in gone}
        renames = {name: type(self).field_renames[(table_id, field_id)]
                   for owner, field_id, name, _k, _u in type(self).created_fields
                   if owner == table_id and (table_id, field_id) in type(self).field_renames}
        if not (writes or names_gone or renames or made):
            return self._proven(self._narrow(records, filter, sort))
        kinds = {name: kind for _o, _f, name, kind, _u in type(self).created_fields
                 if _o == table_id}
        out = []
        for record in records:
            clone = copy.copy(record)
            body = dict(record.fields or {})
            body.update(_as_read_shape(writes.get((table_id, record.record_id), {}), kinds))
            for name in names_gone:
                body.pop(name, None)
            for old, new in renames.items():
                if old in body:
                    body[new] = body.pop(old)
            clone.fields = body
            out.append(clone)
        for record_id, body in made:
            clone = copy.copy(records[0])
            clone.record_id = record_id
            clone.fields = _as_read_shape(body, kinds)
            out.append(clone)
        return self._proven(self._narrow(out, filter, sort))


class _OfflineBatchGet:
    """The ``records/batch_get`` response body — three lists, never one.

    ``forbidden_record_ids`` is always empty here and deliberately still present: the resolver
    reads it to keep *refused* apart from *absent*, and a body missing the key would let a
    reading that conflated the two pass.
    """

    def __init__(self, records, absent):
        self.records = list(records)
        self.absent_record_ids = list(absent)
        self.forbidden_record_ids = []


def _as_read_shape(body: dict, kinds) -> dict:
    """One record's written cells, as the **read** route hands them back.

    Two column kinds are where the write shape and the read shape genuinely differ, and both
    are modelled because a double that echoed the write back would let a recipe teach a round
    trip that does not exist:

    * a **link** cell is written as the bare id list and read back as
      ``{"link_record_ids": [...]}`` — the shipped encoder's own docstring says so;
    * an **attachment** cell is written as ``[{"file_token": …}]`` and read back with the
      durable ``name`` / ``size`` / ``type`` **and two short-lived signed links**, which are
      credential-class. Serving them is the point: a recipe can only demonstrate
      ``scrub_attachment_cell`` dropping them if they are there to drop.

    Every other cell is echoed unchanged, because for every other type the two shapes really
    are the same. ``kinds`` is ``{field_name: storage type}``.
    """
    out = dict(body or {})
    for name, kind in (kinds or {}).items():
        value = out.get(name)
        if kind in (18, 21) and isinstance(value, (list, tuple)):
            out[name] = {"link_record_ids": [str(i) for i in value]}
        elif kind == 17 and isinstance(value, (list, tuple)):
            out[name] = [_attachment_read_back(item) for item in value]
    return out


def _attachment_read_back(item) -> dict:
    """One written ``{"file_token": …}`` → the six-key object a read-back carries."""
    token = item.get("file_token") if isinstance(item, dict) else str(item)
    name, data = OfflineBaseMediaClient.store.get(token, ("unknown", b""))
    return {"file_token": token, "name": name, "size": len(data),
            "type": "application/octet-stream",
            "url": f"https://open.larksuite.com/open-apis/drive/v1/medias/{token}/download",
            "tmp_url": f"https://internal-api-drive-stream.larksuite.com/{token}?sign=OFFLINE"}


def _offline_field_property(ui_type, properties, live_table_names):
    """The ``property`` a created column **reads back** with — never merely what was sent.

    Three of the read-back's facts are the server's, not the caller's, and all three are
    modelled: a link column's ``table_name`` is filled in **only while the target table is
    alive** (its absence is the free dangling signature this library reads); a column the create
    gave no properties reads back ``property: null``, which is the shape the auto fields have
    and which the date renderer keys its default formatter off; and **a select column's options
    come back carrying the ids the server minted for them**, which a create cannot supply and an
    update must not lose (measured in
    ``tests/captures/base-study/captures/ld339-01-select-option-id-remint.json``). A double that echoed
    id-less options back would let a recipe teach the shape that orphans every cell.
    """
    if not properties:
        return None
    from larkdocio.base.field_authoring import build_property

    prop = build_property(ui_type, **properties)
    for position, option in enumerate(getattr(prop, "options", None) or ()):
        if not option.id:
            option.id = f"optOFFLINE{position + 1:02d}"
    target = properties.get("table_id")
    if target is not None and hasattr(prop, "table_name"):
        prop.table_name = (live_table_names or {}).get(target)
    return prop


class _OfflineView:
    """What ``list_views`` hands back — the pinned SDK's view shape, as far as the engine
    reads it."""

    def __init__(self, view_id, view_name, view_type):
        self.view_id, self.view_name, self.view_type = view_id, view_name, view_type
        self.property = None


class _OfflineFilterCondition:
    def __init__(self, blob, index):
        self.field_id = blob["field_id"]
        self.operator = blob["operator"]
        # A STRING on this route, and `None` when the condition omitted the key — which is what
        # a valueless operator does, and what the server echoes back as `value: null`.
        self.value = blob.get("value")
        # The server's OWN additions, which the shipped comparison must normalise away by
        # name. A double that omitted them would let a loose comparison pass.
        self.condition_id = f"conOFFLINE{index}"
        self.field_type = 1


def _offline_view_property(filter_info, hierarchy_config=None, hidden_fields=None):
    if filter_info is None and hierarchy_config is None and not hidden_fields:
        # LD-438: a CLEARED hidden set reads back as `property: null`, exactly as the live
        # capture shows — so an empty list must land here and not in a `hidden_fields: []`.
        return None
    info = None
    if filter_info is not None:
        info = type("_OfflineFilterInfo", (), {})()
        info.conjunction = filter_info["conjunction"]
        info.conditions = [_OfflineFilterCondition(blob, index)
                           for index, blob in enumerate(filter_info["conditions"])]
    prop = type("_OfflineViewProperty", (), {})()
    prop.filter_info = info
    prop.hidden_fields = list(hidden_fields) if hidden_fields else None
    prop.hierarchy_config = (
        type("_OfflineHierarchyConfig", (),
             {"field_id": hierarchy_config["field_id"]})()
        if hierarchy_config else None)
    return prop


class OfflineBaseWriteClient:
    """Stands in for :class:`larkdocio.base.write_client.BaseWriteClient` at the HTTP
    boundary only.

    The engine above it is the shipped one: the mandatory previewer, the plan gate, the
    client-side compare-and-swap and the write-effect oracle all run for real. What this
    replaces is the six transport calls — and the ONE thing it has to model to be honest is
    that **a write moves the table's revision**, because the shipped ``apply`` re-reads that
    anchor after every call and reports a call that did not move it as ``dropped`` rather than
    ``applied``. So each landed call bumps a counter the read double adds to the revision it
    reports, exactly as a real Base does.
    """

    #: ``[(op, args)]`` — inspectable by a recipe check, and reset per stage.
    calls: List[tuple] = []

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the Base write client was constructed with empty credentials — the recipe's "
            "init_env(...) / get_write_credentials() chain did not resolve"
        )
        self.domain = domain

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials
        from larkdocio.errors import LarkConfigError

        app_id, app_secret = get_write_credentials()
        if not (app_id and app_secret):
            raise LarkConfigError("no WRITE credentials in the environment (offline double)")
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def api_calls(self):
        return len(type(self).calls)

    def _landed(self, op, *args):
        type(self).calls.append((op,) + args)
        OfflineBaseReadClient.revision_bump += 1

    def create_record(self, app_token, table_id, fields):
        self._landed("create_record", app_token, table_id)
        # A DISTINGUISHABLE id, and the row is visible to the next read (LD-296): a
        # recipe that writes a parent edge and then reads the tree back needs both, and
        # a double that answered `recNEW1` to every create could not carry an edge at all.
        record_id = f"recNEW{len(OfflineBaseReadClient.created_records) + 1}"
        OfflineBaseReadClient.created_records = (
            list(OfflineBaseReadClient.created_records)
            + [(table_id, record_id, dict(fields or {}))])
        return _CreatedRecord(record_id)

    def update_record(self, app_token, table_id, record_id, fields):
        self._landed("update_record", app_token, table_id, record_id)
        return _CreatedRecord(record_id)

    def delete_record(self, app_token, table_id, record_id):
        self._landed("delete_record", app_token, table_id, record_id)
        return True

    def batch_create_records(self, app_token, table_id, rows):
        self._landed("batch_create_records", app_token, table_id)
        return [_CreatedRecord(f"recNEW{index + 1}") for index in range(len(rows))]

    def batch_update_records(self, app_token, table_id, updates):
        self._landed("batch_update_records", app_token, table_id)
        # The value really lands, in the read double's cell overlay: the guided column-type
        # migration READS ITS COPY BACK and compares it before it destroys anything, so a
        # double that stored nothing would make that verification refuse for the wrong reason.
        for record_id, fields in updates:
            key = (table_id, record_id)
            OfflineBaseReadClient.cell_writes[key] = dict(
                OfflineBaseReadClient.cell_writes.get(key, {}), **dict(fields or {}))
        return [_CreatedRecord(record_id) for record_id, _fields in updates]

    def batch_delete_records(self, app_token, table_id, record_ids):
        self._landed("batch_delete_records", app_token, table_id)
        return True


class _CreatedRecord:
    """What a Base record write hands back: the record's id, and nothing the engine reads."""

    def __init__(self, record_id):
        self.record_id = record_id


class _CopiedApp:
    """The copy's **echo** — and the one thing about it that matters offline is what it does
    NOT carry: ``default_table_id`` comes back **empty** on a real copy, so a double that
    filled it in would let a recipe teach that the echo is the state."""

    def __init__(self, app_token, name):
        self.app_token = app_token
        self.name = name
        self.default_table_id = ""
        self.folder_token = ""


class OfflineBaseSchemaClient:
    """Stands in for :class:`larkdocio.base.schema_client.BaseSchemaClient` at the HTTP
    boundary only.

    The engine above it is the shipped one: the mandatory previewer, the plan gate, the bounded
    settle and the read-back rule all run for real. What this replaces is the six transport
    calls — and the two things it has to model to be honest are that **a copy's echo is not its
    state** (``default_table_id`` empty) and that **the copy is not readable immediately**: the
    read double is told to answer ``1254036`` once, so the recipe's settle really settles
    something rather than being decorative.
    """

    #: ``[(op, args)]`` — inspectable by a recipe check, and reset per stage.
    calls: List[tuple] = []

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the Base schema client was constructed with empty credentials — the recipe's "
            "init_env(...) / get_write_credentials() chain did not resolve"
        )
        self.domain = domain

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials
        from larkdocio.errors import LarkConfigError

        app_id, app_secret = get_write_credentials()
        if not (app_id and app_secret):
            raise LarkConfigError("no WRITE credentials in the environment (offline double)")
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def api_calls(self):
        return len(type(self).calls)

    def _landed(self, op, *args):
        type(self).calls.append((op,) + args)

    def create_app(self, name, folder_token=None, time_zone=None):
        """A CREATE's echo, unlike a copy's, **carries a ``default_table_id``** — and it names
        a table Lark seeded, not one the caller asked for (measured, probe ``ld473-01``: one
        table, four columns, ten blank rows). The double models that, because the recipes now
        teach a consumer to read it rather than to index ``list_tables(...)[0]`` and hope."""
        require_destination(folder_token, what="a Base")
        self._landed("create_app", name)
        OfflineBaseReadClient.app_name_override = name
        app = _CopiedApp("appNEWOFFLINE", name)
        app.default_table_id = "tblSEEDEDOFFLINE"
        return app

    def rename_app(self, app_token, name, **unsupported):
        self._landed("rename_app", app_token, name)
        OfflineBaseReadClient.app_name_override = name
        return _CopiedApp(app_token, name)

    def copy_app(self, app_token, name, without_content=False, folder_token=None):
        require_destination(folder_token, what="a copy of a Base")
        self._landed("copy_app", app_token, name, without_content)
        # The captured shape: the copy races the read that follows it.
        OfflineBaseReadClient.copying = 1
        return _CopiedApp("appCOPYOFFLINE", name)

    def create_table(self, app_token, name, fields=None, primary_field_name=None,
                     default_view_name=None):
        """``fields`` is the inline column kit. The read double grows the columns it names, for
        the same reason every other schema leg here moves state: the shipped read-back verifies
        a kitted create against the table's OWN field list, so a double that landed the table
        and not its columns would make a recipe teach that ``code:0`` is evidence."""
        # LD-322: the naming GATE is upstream (the plan constructor and the client seam);
        # this stand-in only has to speak the signature. `primary_field_name` is
        # normalised the ONE way the shipped code normalises it, so the world grows the
        # column it names rather than a phantom.
        if primary_field_name is not None:
            from larkdocio.base.schema_ops_app_table import check_primary_naming
            fields = list(check_primary_naming(fields, primary_field_name))
        self._landed("create_table", app_token, name)
        # One id PER create. It used to be a constant, which was invisible while a recipe made
        # exactly one create; LD-322's recipe makes two, and a shared id would pile the second
        # table's columns onto the first and make the read-back answer about the wrong table.
        table_id = f"tblOFFLINE{len(OfflineBaseReadClient.extra_tables) + 1:02d}"
        OfflineBaseReadClient.extra_tables = (
            list(OfflineBaseReadClient.extra_tables) + [(table_id, name)])
        OfflineBaseReadClient._remember_kit(table_id, fields)
        return table_id

    def batch_create_tables(self, app_token, names, fields=None,
                            accept_locale_default_primary=False,
                            primary_field_name=None):
        """``fields`` is one column kit per table, parallel to ``names`` (``None`` for none)."""
        names = list(names)
        kits = list(fields) if fields else [None] * len(names)
        self._landed("batch_create_tables", app_token, tuple(names))
        ids = [f"tblOFFLINEB{index}" for index in range(len(names))]
        OfflineBaseReadClient.extra_tables = (
            list(OfflineBaseReadClient.extra_tables) + list(zip(ids, names)))
        for table_id, kit in zip(ids, kits):
            OfflineBaseReadClient._remember_kit(table_id, kit)
        return ids

    def rename_table(self, app_token, table_id, name):
        self._landed("rename_table", app_token, table_id, name)
        OfflineBaseReadClient.table_renames = dict(
            OfflineBaseReadClient.table_renames, **{table_id: name})
        return name

    # ---- the FIELD families (LD-263 / LD-265, reached by LD-291's migration) -- #
    #
    # A column op is verified by TWO facts — the column reads back with the identity that was
    # asked for, and `table.revision` moved — so each of these has to move both, or the shipped
    # read-back would report a landed call as `dropped`.

    def create_field(self, app_token, table_id, field_name, field_type, ui_type=None,
                     properties=None):
        self._landed("create_field", table_id, field_name, ui_type)
        field_id = f"fldOFFLINE{len(OfflineBaseReadClient.created_fields) + 1:02d}"
        OfflineBaseReadClient.created_fields = (
            list(OfflineBaseReadClient.created_fields)
            + [(table_id, field_id, field_name, field_type, ui_type or "Text")])
        # The column's CONFIGURATION, kept so the read double can serve it back: a link column
        # that forgot where it points, or a select column that forgot its options, is not the
        # column that was authored.
        configured = dict(OfflineBaseReadClient.created_field_properties)
        configured[(table_id, field_id)] = dict(properties or {})
        OfflineBaseReadClient.created_field_properties = configured
        OfflineBaseReadClient.revision_bump += 1
        return field_id

    def update_field(self, app_token, table_id, field_id, field_name, field_type,
                     ui_type=None, properties=None):
        self._landed("update_field", table_id, field_id, field_name)
        renames = dict(OfflineBaseReadClient.field_renames)
        renames[(table_id, field_id)] = field_name
        OfflineBaseReadClient.field_renames = renames
        OfflineBaseReadClient.revision_bump += 1
        return field_id

    def delete_field(self, app_token, table_id, field_id):
        self._landed("delete_field", table_id, field_id)
        OfflineBaseReadClient.deleted_field_ids = (
            list(OfflineBaseReadClient.deleted_field_ids) + [(table_id, field_id)])
        OfflineBaseReadClient.revision_bump += 1
        return field_id

    # ---- the VIEW family (LD-264) ------------------------------------------ #
    #
    # The dialect boundary is NOT modelled here: `update_view` takes whatever the engine hands
    # it, and what the engine hands it is whatever the plan carried — which can only ever be a
    # ViewFilterInfo, because that is the only value `set_view_filter` accepts. The type check
    # lives on the shipped client's signature and is unit-tested there; a double that
    # re-implemented it would be testing the double.

    def create_view(self, app_token, table_id, view_name, view_type="grid"):
        self._landed("create_view", table_id, view_name, view_type)
        view_id = f"vewOFFLINE{len(OfflineBaseReadClient.views) + 1:02d}"
        OfflineBaseReadClient.views = dict(
            OfflineBaseReadClient.views,
            **{view_id: {"view_name": view_name, "view_type": view_type,
                         "filter_info": None}})
        return view_id

    def update_view(self, app_token, table_id, view_id, *, view_name=None, filter_info=None,
                    hierarchy_config=None, hidden_fields=None):
        self._landed("update_view", view_id)
        blob = dict(OfflineBaseReadClient.views[view_id])
        if view_name is not None:
            blob["view_name"] = view_name
        if filter_info is not None:
            blob["filter_info"] = filter_info.to_dict()
        if hierarchy_config is not None:
            blob["hierarchy_config"] = hierarchy_config.to_dict()
        if hidden_fields is not None:
            # `[]` is the CLEAR and it is a VALUE, not an absence — `is not None`, never a
            # truthiness test, or a clear would silently become a no-op here.
            blob["hidden_fields"] = list(hidden_fields)
        OfflineBaseReadClient.views = dict(
            OfflineBaseReadClient.views, **{view_id: blob})
        return blob

    def delete_view(self, app_token, table_id, view_id):
        self._landed("delete_view", view_id)
        OfflineBaseReadClient.views = {
            key: value for key, value in OfflineBaseReadClient.views.items()
            if key != view_id}
        return True

    # ---- the WHOLE-OBJECT delete (LD-466) ---------------------------------- #

    def delete_base(self, app_token):
        """Trash the whole Base, and model the two things a recipe must not be able to fake.

        (a) The read side stops serving it, answering ``1002`` — so the recipe's confirmation
        step is a real read of a real refusal rather than a printed hope. (b) A **second** delete
        raises the typed error carrying ``FILE_ALREADY_DELETED_CODE``, which is what the live
        route answers and what ``base_is_gone`` exists to forgive: a double that returned success
        twice would let the recipe teach that the call is idempotent, which it is not.
        """
        from larkdocio.base.errors import raise_for_base_code
        from larkdocio.sheets.write_client import FILE_ALREADY_DELETED_CODE

        self._landed("delete_base", app_token)
        if app_token in OfflineBaseReadClient.trashed_apps:
            raise_for_base_code(
                {"code": FILE_ALREADY_DELETED_CODE, "msg": "file has been delete."},
                context=f"TRASH the whole Base {app_token}")
        OfflineBaseReadClient.trashed_apps = (
            list(OfflineBaseReadClient.trashed_apps) + [app_token])
        return None


class OfflineBaseMediaClient:
    """Stands in for :class:`larkdocio.base.media.BaseMediaClient` at the HTTP boundary only.

    The two legs are modelled as what they are — an **out-of-band** pair that mints a token and
    hands the same bytes back — and everything the shipped module does above them runs for
    real: the ``parent_type`` allow-list, the ``sha256`` computed over the bytes as sent, and
    :func:`~larkdocio.base.media.verify_round_trip`'s digest comparison. Nothing here decodes,
    parses or inspects a payload, which is the standing rule for binary artifacts.

    **The residue is modelled too.** Every upload appends to :attr:`minted`, so a recipe's
    check can assert what a live run would have left behind permanently — the disclosure the
    recipe carries is a fact about the real leg, and a double that quietly forgot its tokens
    would make it look like a formality.
    """

    #: ``[(op, args)]`` — inspectable by a recipe check, and reset per stage.
    calls: List[tuple] = []
    #: ``[(file_token, parent_type, parent_node)]`` — the permanent residue an upload leaves.
    minted: List[tuple] = []
    #: ``{file_token: (name, bytes)}`` — the store the download leg reads back, and the
    #: source of the ``name`` / ``size`` an attachment cell's READ-BACK carries.
    store: Dict[str, tuple] = {}
    #: The ``parent_type`` allow-list this double enforces. A subclass standing in for a
    #: different surface's leg re-states it, exactly as the shipped clients do.
    parent_types: tuple = ()
    #: The token prefix minted tokens carry, so a recipe check can tell the legs apart.
    token_prefix = "boxbcOFFLINE"

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the Base media client was constructed with empty credentials — the recipe's "
            "init_env(...) / get_write_credentials() chain did not resolve"
        )
        self.domain = domain

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials
        from larkdocio.errors import LarkConfigError

        app_id, app_secret = get_write_credentials()
        if not (app_id and app_secret):
            raise LarkConfigError("no WRITE credentials in the environment (offline double)")
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def api_calls(self):
        return len(type(self).calls)

    def upload(self, *, data: bytes, name: str, parent_type: str, parent_node: str):
        from larkdocio.base.media import (
            MEDIA_PARENT_TYPES,
            MediaUploadError,
            UploadedMedia,
            sha256_of,
        )

        # The two local refusals the shipped leg makes before any call — kept here so a recipe
        # that reached for a bogus parent_type meets the same answer offline.
        allowed = type(self).parent_types or MEDIA_PARENT_TYPES
        if parent_type not in allowed:
            raise MediaUploadError(
                f"parent_type must be one of {allowed}; got {parent_type!r}")
        if not data:
            raise MediaUploadError(
                "Lark refuses a zero-byte upload with 1061002 params error (offline double)")
        type(self).calls.append(("upload", name, parent_type, parent_node))
        token = f"{type(self).token_prefix}{len(type(self).minted) + 1:02d}"
        type(self).store = dict(type(self).store, **{token: (name, bytes(data))})
        type(self).minted = list(type(self).minted) + [(token, parent_type, parent_node)]
        return UploadedMedia(file_token=token, parent_type=parent_type,
                             parent_node=parent_node, size=len(data),
                             sha256=sha256_of(data))

    def download(self, file_token: str) -> bytes:
        from larkdocio.base.media import MediaDownloadError, MediaTokenNotFoundError

        if not file_token:
            raise MediaDownloadError(
                "a download needs a file_token (offline double)")
        if file_token not in type(self).store:
            raise MediaTokenNotFoundError(
                f"no media for {file_token!r} (offline double)")
        type(self).calls.append(("download", file_token))
        return type(self).store[file_token][1]

    #: The host this double's permalinks are minted under — the same host the recipes' Base
    #: URL uses, so a recipe's printed address is one a reader would recognise.
    permalink_host = "your-domain.larksuite.com"

    def permalink(self, file_token: str):
        """Stands in for the drive META family's answer, not for the media route.

        The double mints the address because the **server** mints it: the shipped leg never
        constructs a URL from a token, so a double that let one through would be modelling
        the one thing the op refuses to do. The unresolved case is modelled as what it really
        is — ``code:0`` with no meta — which the shipped leg turns into a typed refusal.
        """
        from larkdocio.base.media import (
            MediaPermalink,
            MediaPermalinkError,
            MediaPermalinkNotResolvedError,
        )

        if not file_token:
            raise MediaPermalinkError("a permalink needs a file_token (offline double)")
        if file_token not in type(self).store:
            raise MediaPermalinkNotResolvedError(
                f"metas/batch_query answered success with no meta for {file_token!r} "
                f"(offline double)")
        type(self).calls.append(("permalink", file_token))
        return MediaPermalink(
            file_token=file_token,
            url=f"https://{type(self).permalink_host}/file/{file_token}",
            title=type(self).store[file_token][0],
        )


class OfflineDocxMediaClient(OfflineBaseMediaClient):
    """Stands in for :class:`larkdocio.write.media.DocxMediaClient` at the HTTP boundary.

    The same out-of-band pair, with the document surface's own ``parent_type`` vocabulary —
    and its own class-level ledgers, so a recipe check can tell an image upload from a Base
    attachment one. Everything the shipped op does above it (the fixed order, the read-back
    verdict, the hash comparison) runs for real.
    """

    calls: List[tuple] = []
    minted: List[tuple] = []
    store: Dict[str, tuple] = {}
    #: BOTH spellings the shipped ``DocxMediaClient`` allows — the image leg and the
    #: attachment leg. Held against ``DocxMediaClient.ALLOWED_PARENT_TYPES`` by
    #: :func:`double_signature_mismatches`, because a double narrower than the real client
    #: refuses a route the library ships (LD-470).
    parent_types = ("docx_image", "docx_file")
    token_prefix = "boxcnOFFLINEIMG"


class OfflineSheetsMediaClient(OfflineBaseMediaClient):
    """Stands in for :class:`larkdocio.sheets.media.SheetsMediaClient` — the DOWNLOAD-only
    leg of the in-cell image route.

    ``parent_types`` is empty because the shipped client's is: that route has **no** upload
    leg, so a double carrying one would model a product that does not exist. What fills this
    double's ``store`` is the **write** client's ``put_values_image`` — which is exactly the
    fact the op discloses, that Lark mints the token itself and the caller uploads nothing.
    """

    calls: List[tuple] = []
    minted: List[tuple] = []
    store: Dict[str, tuple] = {}
    parent_types = ()
    token_prefix = "boxcnOFFLINECELLIMG"


class OfflineFloatImageMediaClient(OfflineBaseMediaClient):
    """Stands in for :class:`larkdocio.sheets.media.FloatImageMediaClient` — the FLOAT
    route's upload+download leg.

    Its own ledgers, so a recipe check can tell a float-image upload from an in-cell mint:
    the two routes mint tokens independently and merging the doubles would hide exactly the
    fact the module discloses. ``parent_types`` is the shipped client's one spelling, so a
    recipe reaching for ``sheet_file`` meets the same local refusal offline.
    """

    calls: List[tuple] = []
    minted: List[tuple] = []
    store: Dict[str, tuple] = {}
    parent_types = ("sheet_image",)
    token_prefix = "boxcnOFFLINEFLOATIMG"


class OfflineSheetsReadClient:
    """Stands in for :class:`larkdocio.sheets.client.SheetsReadClient` at the HTTP
    boundary only — returns real ``SheetTab`` / ``UsedRange`` value objects so the
    recipe's ``render_spreadsheet`` step is the shipped renderer."""

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, "sheets read client got empty credentials"
        self.domain = domain

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_read_credentials

        app_id, app_secret = get_read_credentials()
        if not (app_id and app_secret):
            from larkdocio.errors import LarkConfigError

            raise LarkConfigError("no READ credentials in the environment")
        return cls(app_id, app_secret, domain, **kwargs)

    def query_sheets(self, spreadsheet_token):
        from larkdocio.sheets.models import SheetTab

        return [SheetTab(sheet_id="3bf016", title="Sheet1", index=0,
                         row_count=2, column_count=2)]

    def read_used_range(self, spreadsheet_token, tab, **kwargs):
        from larkdocio.sheets.extent import UsedRange

        return UsedRange(sheet_id=tab.sheet_id, a1_range=f"{tab.sheet_id}!A1:B2",
                         revision=34, values=[["Name", "Qty"], ["Widget", 3]])

    def get_sheet_filter(self, spreadsheet_token, sheet_id):
        """A tab WITH a filter, hiding the sheet's row 2 — so the recipe's disclosure step
        has something real to disclose and the executed render actually carries the note.

        Row numbers here are the API's own convention (1-indexed, absolute to the sheet),
        which is what makes row ``2`` the ``Widget`` row of the used range above."""
        from larkdocio.sheets.models import SheetFilter

        return SheetFilter(range=f"{sheet_id}!A1:B2", filtered_out_rows=(2,))

    def read_tab_filter(self, spreadsheet_token, tab):
        return tab.with_filter(self.get_sheet_filter(spreadsheet_token, tab.sheet_id))

    def read_spreadsheet(self, spreadsheet_token, **kwargs):
        """The SHIPPED walk, run on this double's ``query_sheets`` / ``read_used_range``.

        Deliberately not a re-implementation: the recipe's skip-loudly step must exercise the
        real orchestration (LD-383), and the only thing this double stands in for is the HTTP
        boundary. Called unbound so the shipped method's own body runs with this object as
        ``self``."""
        return _SHIPPED_READ_SPREADSHEET(self, spreadsheet_token, **kwargs)


def captured_export_workbook() -> bytes:
    """The **captured** xlsx export the fidelity recipe reads (LD-152 / dogfood F17+F19).

    One worksheet named ``Sheet1`` — the title :class:`OfflineSheetsReadClient` serves — whose
    header cells ``A1``/``B1`` carry **bold** and ``B2`` carries a **fill** (``FFFFFF00``), so
    the L2 render differs observably from the values-only one on both axes — the emphasis in
    the table, the fill in the disclosure note above it (LD-331). The bytes are synthesized from committed text by ``tests/xlsx_synth``
    (the kit commits no binary blobs) and are parsed by the **shipped** stdlib parser, so the
    recipe's fidelity step exercises real ``parse_xlsx`` output — never a hand-built
    ``ExportedSheet``. No live export runs in the suite: an export is an async
    whole-workbook task (F19), which is exactly the cost the recipe has to disclose.
    """
    import xlsx_synth  # tests/ is on sys.path (conftest)

    styles = xlsx_synth.styles_xml(
        fonts=[{}, {"bold": True}],
        fills=[{"pattern": "none"}, {"pattern": "gray125"},
               {"pattern": "solid", "fg_rgb": "FFFFFF00"}],
        cell_xfs=[{"numFmtId": 0, "fontId": 0, "fillId": 0},
                  {"numFmtId": 0, "fontId": 1, "fillId": 0},
                  {"numFmtId": 0, "fontId": 0, "fillId": 2}],
    )
    return xlsx_synth.build_workbook(
        [{
            "name": "Sheet1",
            "cells": [
                ("A1", {"s": 1, "t": "inlineStr", "inline": "Name"}),
                ("B1", {"s": 1, "t": "inlineStr", "inline": "Qty"}),
                ("A2", {"t": "inlineStr", "inline": "Widget"}),
                ("B2", {"s": 2, "v": "3"}),
            ],
        }],
        styles=styles,
    )


class OfflineSheetsExportReader(SheetsExportReader):
    """Stands in for :class:`larkdocio.sheets.export_reader.SheetsExportReader` at the HTTP
    boundary **only** — a real subclass, overriding exactly the three network calls.

    ``export_xlsx`` (create → poll → download) and ``read_workbook`` (+ the stdlib
    ``parse_xlsx``) are therefore the **shipped** implementations running for real over a
    captured workbook; only the three HTTP legs are replaced. Subclassing also means
    :func:`double_signature_mismatches` compares against the class it inherits, so a drifted
    override cannot hide.

    ``from_read_credentials`` re-resolves the READ pair (so the recipe's ``init_env`` line
    stays load-bearing here as everywhere) but skips the real classmethod's production side
    effect — the process-wide IPv4 socket pin.
    """

    #: set by :meth:`OfflineStage.install` — the captured xlsx the download leg serves.
    workbook_bytes: Optional[bytes] = None

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_read_credentials
        from larkdocio.errors import LarkConfigError

        app_id, app_secret = get_read_credentials()
        if not (app_id and app_secret):
            raise LarkConfigError(
                "Sheets export reader: no READ credentials resolved (offline double)")
        return cls(lambda: "offline-export-token", domain, **kwargs)

    def create_export_task(self, spreadsheet_token) -> str:
        return f"ticket-for-{spreadsheet_token}"

    def poll_export_task(self, ticket, spreadsheet_token) -> dict:
        return {"job_status": 0, "file_token": f"file-{ticket}"}

    def download_export(self, file_token) -> bytes:
        blob = type(self).workbook_bytes
        assert blob, (
            "the export double was used without an OfflineStage — call "
            "guide_recipes.stage(monkeypatch, tmp_path) so the captured workbook is installed")
        return blob


class OfflineCommentsReadClient:
    """Stands in for :class:`larkdocio.comments.client.CommentsReadClient` at the HTTP
    boundary only (LD-159).

    Answers with the **captured** comment shape — the listing form, which is the one that
    reports a comment's scope — so the recipe's projection step runs the shipped model over a
    real payload. The two properties the recipe's execution depends on are honoured exactly as
    the real client honours them:

    * the id it answers for is the id the fixture paragraph carries, so the recipe's
      block-to-comments lookup resolves for real rather than over an empty result;
    * ``batch_query_comments`` returns ``[]`` for an empty id list **without recording a
      call**, so the "no anchors costs nothing" property the shipped client has is not
      quietly lost at the boundary.

    It resolves the READ credential pair on construction, which keeps the recipe's opening
    ``init_env(...)`` line load-bearing here as it is everywhere else in this harness.
    """

    #: The endpoint each construction of this double touched, in order — CLASS-level, reset
    #: per stage by :meth:`OfflineStage.install`, because the recipe builds its own client
    #: inside ``comments()`` and no instance is reachable from the recipe's namespace. It is
    #: what lets a recipe check assert **which** read the recipe made: the whole-list call and
    #: the anchor-scoped one differ only at the transport on a one-comment fixture, and getting
    #: that choice wrong is exactly how the shipped recipe read 5 of 7 comments (LD-172).
    ops: List[str] = []

    #: ``[(op, args)]`` — inspectable by a recipe check, and the reason the double exists at
    #: all rather than a monkeypatched function.
    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the comments read client was constructed with empty credentials — the recipe's "
            "init_env(...) / get_read_credentials() chain did not resolve"
        )
        self.domain = domain
        self.calls: List[tuple] = []
        self.api_calls = 0

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_read_credentials
        from larkdocio.errors import LarkConfigError

        app_id, app_secret = get_read_credentials()
        if not (app_id and app_secret):
            raise LarkConfigError("no READ credentials in the environment (offline double)")
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def limiter(self):
        from larkdocio.common.transport import RateLimiter

        return RateLimiter(60, window=60.0)

    def _comment(self, comment_id):
        from lark_oapi.api.drive.v1 import FileComment

        return FileComment({
            "comment_id": comment_id,
            "user_id": _FIXTURE_COMMENT_AUTHOR,
            "create_time": 1785278076,
            "update_time": 1785278076,
            "is_solved": False,
            "is_whole": False,
            "quote": _FIXTURE_QUOTE,
            "reply_list": {"replies": [{
                "content": {"elements": [{
                    "docs_link": None, "person": None,
                    "text_run": {"text": _FIXTURE_COMMENT_TEXT}, "type": "text_run"}]},
                "create_time": 1785278076,
                "extra": {"image_list": None},
                "reply_id": "7667710952845889243",
                "update_time": 1785278076,
                "user_id": _FIXTURE_COMMENT_AUTHOR,
            }]},
        })

    def _created_comment(self, record):
        """One comment the WRITE double made, in the **listing** shape.

        The listing form matters: it is the only endpoint that reports ``is_whole``, and a
        whole-document comment reads ``is_whole: true`` with ``quote: null`` — which is exactly
        what the create-and-take-it-back recipe reads back to check what it actually made. A
        double that answered the *create* shape here would let that check pass vacuously.
        """
        from lark_oapi.api.drive.v1 import FileComment

        return FileComment({
            "comment_id": record["comment_id"],
            "user_id": record["user_id"],
            "create_time": 1785316956,
            "update_time": 1785316956,
            "is_solved": False,
            "is_whole": True,
            "quote": None,
            "reply_list": {"replies": [{
                "content": {"elements": [{
                    "docs_link": None, "person": None,
                    "text_run": {"text": record["text"]}, "type": "text_run"}]},
                "create_time": 1785316956,
                "extra": {"image_list": None},
                "reply_id": reply_id,
                "update_time": 1785316956,
                "user_id": record["user_id"],
            } for reply_id in record["replies"]]},
        })

    def _created(self, file_token):
        """The comments the write double created on ``file_token``, if the stores are shared."""
        documents = _documents_for(OfflineWriteClient)
        return list(documents.comments_for(file_token).values())

    def list_comments(self, file_token, *, file_type="docx"):
        self.calls.append(("list_comments", file_token, file_type))
        type(self).ops.append("list_comments")
        self.api_calls += 1
        # The captured ANCHORED fixture (unchanged — the comments-read recipe's payload) plus
        # anything the write double created on this file, so a recipe that creates a comment and
        # reads it back sees its own comment rather than only the fixture.
        return ([self._comment(_FIXTURE_COMMENT_ID)]
                + [self._created_comment(r) for r in self._created(file_token)])

    def batch_query_comments(self, file_token, comment_ids, *, file_type="docx"):
        ids = list(comment_ids)
        if not ids:
            return []          # no ids, no call — the shipped client's own rule
        self.calls.append(("batch_query_comments", file_token, tuple(ids), file_type))
        type(self).ops.append("batch_query_comments")
        self.api_calls += 1
        return [self._comment(cid) for cid in ids if cid == _FIXTURE_COMMENT_ID]

    def list_replies(self, file_token, comment_id, *, file_type="docx", page_token=None):
        self.calls.append(("list_replies", file_token, comment_id, file_type))
        type(self).ops.append("list_replies")
        self.api_calls += 1
        return []


class OfflineContactsSearchClient:
    """Stands in for :class:`larkdocio.contacts.client.ContactsSearchClient` at the HTTP
    boundary only (LD-229).

    Answers with the **wire shape** the committed GO capture established — the id at
    ``base_info.employee_id``, the display name at ``base_info.name.name.default_value``, a
    ``page_response`` with ``has_more`` and **no** ``count`` — so the recipe's resolution step
    runs the shipped matcher, the shipped exactly-one-or-refuse contract and the shipped
    partiality disclosure over a payload with the real field layout.

    The directory it answers from is the SAME ``_FIXTURE_MENTION_NAMES`` map the read double's
    reverse direction serves, keyed the other way round. That is the point: the two directions
    of the id↔name pair cannot disagree in this harness, so a recipe that resolves a name and
    then reads a mention back sees one consistent world.
    """

    #: ``[query]`` — CLASS-level and reset per stage, because the recipe lets ``resolve_user``
    #: build its own client and no instance is reachable from the recipe's namespace.
    queries: List[str] = []

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the contacts search client was constructed with empty credentials — the "
            "recipe's init_env(...) chain did not resolve"
        )
        self.domain = domain
        self.api_calls = 0
        self.last_request = None
        self.limiter = None

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_read_credentials

        app_id, app_secret = get_read_credentials()
        return cls(app_id, app_secret, domain, **kwargs)

    def search_employees(self, query, *, page_size=None, page_token=None,
                         required_fields=None):
        type(self).queries.append(query)
        self.api_calls += 1
        wanted = " ".join((query or "").split()).casefold()
        rows = [
            {"base_info": {"employee_id": open_id,
                           "name": {"name": {"default_value": name,
                                             "i18n_value": {"en_us": "", "ja_jp": "",
                                                            "zh_cn": ""}}}}}
            for open_id, name in _FIXTURE_MENTION_NAMES.items()
            if wanted in " ".join(name.split()).casefold()
        ]
        return _AttrBag({"employees": [_AttrBag(row) for row in rows],
                         "page_response": _AttrBag({"has_more": False, "page_token": "tok"}),
                         "abnormals": None})


class _AttrBag:
    """A dict as an attribute bag — the SDK's deserialized shape, where an unreported field
    reads as ``None`` rather than raising."""

    def __init__(self, mapping):
        for key, value in (mapping or {}).items():
            setattr(self, key, _AttrBag(value) if isinstance(value, dict) else value)

    def __getattr__(self, item):
        return None


class OfflineWriteClient:
    """Stands in for :class:`larkdocio.write.client.WriteClient` at the HTTP boundary.

    Reads and writes the **same** :class:`OfflineDocument` the read double serves (so what
    ``apply`` re-validates against is what ``dry_run`` planned from, and what the *next* read
    returns is what ``apply`` actually wrote): ``get_block`` serves the live block, and
    ``_patch_block`` / ``create_children`` / ``batch_delete`` mutate the document *and* record
    the write. The shipped ``apply`` engine — its STALE_ANCHOR re-validation, its element-level
    patch building, its apply-log — runs for real.
    """

    empty_document: bool = False
    #: set by :meth:`OfflineStage.install` — the per-stage store shared with the read double.
    documents: Optional[OfflineDocuments] = None

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the write client was constructed with empty credentials — the recipe's "
            "init_env(...) / get_write_credentials() chain did not resolve"
        )
        self.domain = domain
        self.patches: List[tuple] = []
        self.created: List[tuple] = []
        self.descended: List[tuple] = []
        self.deleted: List[tuple] = []
        self.comments_created: List[tuple] = []
        self.replies_deleted: List[tuple] = []

    def _document(self, document_id) -> OfflineDocument:
        return _documents_for(type(self)).for_token(document_id)

    def get_block(self, document_id, block_id):
        return self._document(document_id).get(block_id)

    def list_document_blocks(self, document_id, page_size=500):
        """The whole document as flat block dicts — the paginated block list the batched
        table fill reads every cell's inner block id from (LD-481).

        Served off the SAME store every other method here uses, so the ids a fill addresses
        are the ids ``create_children`` actually minted. Pagination is the API's affair and
        the shipped client walks it; the double answers one exhausted page.
        """
        return self._document(document_id).block_dicts()

    def batch_update_blocks(self, document_id, requests):
        """Patch many blocks in one call — the batched cell fill's write route (LD-481).

        Applied through the same :meth:`OfflineDocument.patch` every single patch goes
        through, one request at a time, so what the next read serves is what the batch said.
        Recorded in :attr:`patches` under the same shape a single patch records: a spy that
        counted a batch as one write would make the "how many writes did this recipe make"
        assertions read false.
        """
        if not requests:
            return None
        document = self._document(document_id)
        for request in requests:
            update = {k: v for k, v in request.items() if k != "block_id"}
            self.patches.append((request["block_id"], update))
            document.patch(request["block_id"], update)
        return {"blocks": []}

    def read_document_revision(self, document_id):
        """The document's live ``revision_id`` — the whole-document compare-and-swap read
        the shipped ``apply`` makes immediately before a batch (LD-139). A read, so it does
        **not** bump the revision (which is what makes an armed batch able to apply at all)."""
        return self._document(document_id).revision

    def _patch_block(self, document_id, block_id, update):
        self.patches.append((block_id, update))
        self._document(document_id).patch(block_id, update)
        return {"block_id": block_id}

    def create_children(self, document_id, block_id, children, index=-1):
        self.created.append((block_id, children, index))
        made = self._document(document_id).create_children(block_id, children, index)
        # The real answer is a list of BLOCK objects, so each entry carries its own
        # ``block_type`` — the field the image op checks before it binds bytes to anything —
        # and, for a block that owns children, its child ID LIST. Both are read off the store
        # rather than off the request, because a **file** create answers a block the request
        # never named: the type-33 view wrapper whose child is the real file block (LD-470).
        doc = self._document(document_id)
        return {"children": [dict(doc.get(bid), children=list(doc.get(bid).get("children") or ()))
                             for bid in made]}

    def create_descendant(self, document_id, block_id, *, children_id, descendants,
                          index=-1):
        self.descended.append((block_id, children_id, descendants, index))
        return self._document(document_id).create_descendant(
            block_id, list(children_id), list(descendants), index)

    def batch_delete(self, document_id, block_id, start_index, end_index):
        self.deleted.append((block_id, start_index, end_index))
        self._document(document_id).batch_delete(block_id, start_index, end_index)
        return {}

    # -- the comment family, into the store the comments READ double serves ----- #
    #
    # Same discipline as the block store above: what the next read returns is what the write
    # actually did. So a recipe can create a comment and then genuinely read it back — which is
    # the only way the "verify what was MADE, not what came back" step teaches anything.

    #: The bot ``open_id`` the create answers with. A real one is opaque and unresolvable (the
    #: directory answers 41050 for it), which is the whole point of the recipe's disclosure —
    #: so the double answers an opaque id too rather than something name-shaped.
    BOT_AUTHOR_ID = "ou_examplebot0000000000000000000001"

    def create_whole_document_comment(self, document_id, text, *, file_type="docx"):
        store = _documents_for(type(self)).comments_for(document_id)
        comment_id = f"76678779388507624{len(store) + 10}"
        reply_id = f"{comment_id}-r0"
        store[comment_id] = {"comment_id": comment_id, "user_id": self.BOT_AUTHOR_ID,
                             "text": text, "replies": [reply_id]}
        self.comments_created.append((document_id, comment_id, text))
        # The CREATE shape, which — as the captures show — does NOT report is_whole at all.
        # Answering it faithfully is what keeps a recipe honest about needing a read-back.
        return {"comment_id": comment_id, "user_id": self.BOT_AUTHOR_ID,
                "create_time": 1785316956, "update_time": 1785316956, "is_solved": False,
                "solver_user_id": None,
                "reply_list": {"replies": [{"reply_id": reply_id,
                                            "user_id": self.BOT_AUTHOR_ID}]}}

    def list_comment_replies(self, document_id, comment_id, *, file_type="docx"):
        store = _documents_for(type(self)).comments_for(document_id)
        record = store.get(comment_id)
        if record is None:
            from larkdocio.errors import api_error
            raise api_error(f"comment {comment_id} not found", code=1069307, msg="not exist")
        return [{"reply_id": rid, "user_id": record["user_id"]} for rid in record["replies"]]

    def delete_comment_reply(self, document_id, comment_id, reply_id, *, file_type="docx"):
        store = _documents_for(type(self)).comments_for(document_id)
        record = store.get(comment_id)
        if record is None or reply_id not in record["replies"]:
            from larkdocio.errors import api_error
            raise api_error(f"reply {reply_id} not found", code=1069307, msg="not exist")
        record["replies"].remove(reply_id)
        self.replies_deleted.append((document_id, comment_id, reply_id))
        # THE CASCADE, modelled: a comment's content IS its replies, so the comment goes with
        # the last one. A double that kept the comment alive would let a removal recipe "pass"
        # while leaving a comment behind.
        if not record["replies"]:
            del store[comment_id]
        return {"code": 0}


class OfflineSheetsWriteClient:
    """Stands in for :class:`larkdocio.sheets.write_client.SheetsWriteClient` at the HTTP
    boundary — the duck-typed gateway the shipped ``dry_run`` / ``apply`` read and write
    through (monotonic ``revision``, a per-range value store, ``query_tabs``).

    **It enforces the ``sheet_id`` rule the real API enforces**: a range whose tab part is
    not a known ``sheet_id`` raises Lark's real ``90215 not found sheetId``, so a
    title-shaped range (dogfood F4's ``"Sheet1!A1:A1"``) is refused *by the shipped engine's
    own refusal mapping* here, not merely by a hand-written assertion. Without that the
    harness would happily "apply" the very write a real spreadsheet rejects.
    """

    tabs: List[dict] = [
        {"sheet_id": "3bf016", "title": "Sheet1", "index": 0, "hidden": False,
         "row_count": 100, "column_count": 20, "merges": []},
        # LD-187 — a SECOND tab, because the presentation recipe hides one and a spreadsheet
        # cannot hide its only tab (probed: Lark answers `95201 server error`). Every other
        # recipe takes the FIRST tab, so the addition is invisible to them.
        {"sheet_id": "7cd112", "title": "Notes", "index": 1, "hidden": False,
         "row_count": 100, "column_count": 20, "merges": []},
    ]
    #: The demo tab's cells, by A1 ref. **Per-cell, not per-range** (LD-152): the real values
    #: API answers whatever rectangle you ask for — the full requested span, with absent cells
    #: as ``null`` — so a per-range fixture could only answer the exact ranges someone
    #: remembered to seed. Modelling cells is what lets the destructive recipes read a
    #: removed-payload range they never wrote (the F12 declared-width pad appears on its own,
    #: instead of being hand-faked) and what makes ``[[None]]`` clearing observable: a cleared
    #: cell really becomes absent and reads back as ``None``.
    cells: Dict[str, Dict[str, object]] = {
        "3bf016": {
            "A1": "old value",
            "B1": "Qty", "C1": "Notes",
            "A2": "Widget", "B2": 3,
            "A3": "Gadget", "B3": 5,
            # A LIVE formula, in the object form Lark stores an evaluating one as. Under the
            # value render modes it answers its computed result (which is why the clear
            # recipe's `before` cannot show it) and under `Formula` it answers the
            # expression — the asymmetry the `overwrites-live-formula` note is built on.
            "A4": "Total", "B4": {"type": "formula", "text": "=SUM(B2:B3)"},
        },
    }

    #: The fake server's stand-in **evaluator** (LD-149). The real API computes; this double
    #: replaces only the network boundary, so it maps the guide recipe's expression to a
    #: plausible computed value. What the recipe actually proves here is the *engine* plumbing
    #: — the object-form write, the two render-mode legs, and the ``evaluated`` verification —
    #: not Lark's arithmetic (that is the live gate's job,
    #: ``tests/test_live_sheets_formula_write_gate.py``). An expression absent from this map
    #: models Lark's **accepts-but-stores-inert** behaviour, which is exactly the case whose
    #: computed leg answers the expression itself.
    computed: Dict[str, object] = {"=SUM(B3:B8)": 21, "=SUM(B2:B3)": 8}

    #: the most recently constructed instance — the ONE way a test that runs a recipe to a
    #: raised exception can still inspect what the recipe did before it died (the namespace
    #: never comes back). Used by the disposables recipe's ``finally``-delete proof.
    last_instance: Optional["OfflineSheetsWriteClient"] = None

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the sheets write client was constructed with empty credentials — the "
            "recipe's init_env(...) / get_write_credentials() chain did not resolve"
        )
        self.domain = domain
        self.revision = 34
        self.grid = {sid: dict(cells) for sid, cells in type(self).cells.items()}
        self.puts: List[tuple] = []
        #: the FILE lifecycle this double models (LD-176): tokens it minted, tokens it
        #: trashed, and the trashed set every other op then refuses for — so a recipe that
        #: uses a workbook after deleting it fails here exactly as it would live.
        self.created: List[str] = []
        self.deleted: List[str] = []
        type(self).last_instance = self
        #: the live tab set — a per-instance COPY of the class fixture, so a recipe that
        #: adds/copies/deletes a tab cannot leak that tab into the next recipe's run.
        self.tab_state: List[dict] = [
            {**t, "merges": [dict(m) for m in t.get("merges") or ()]}
            for t in type(self).tabs
        ]
        self.validations: List[tuple] = []
        self.dimension_writes: List[tuple] = []
        self.merge_writes: List[tuple] = []
        self.tab_writes: List[dict] = []
        #: the freeze journal + the per-tab frozen state this double keeps, so the freeze
        #: recipe's read-backs answer what its own writes actually did (LD-186). PATCH
        #: semantics are modelled, not asserted: an axis a request does not name is untouched.
        self.freeze_writes: List[tuple] = []
        #: the cell-STYLE journal (LD-188) — one entry per style seam call, so the style
        #: recipe's check measures the wire shape it actually produced (and that N ranges
        #: really cost ONE call).
        self.style_writes: List[tuple] = []
        #: the tab-PRESENTATION journal (LD-187) — one entry per `updateSheet` naming an
        #: index / title / hidden, so the recipe's check measures what it actually wrote.
        self.presentation_writes: List[tuple] = []
        self.frozen: Dict[str, Dict[str, int]] = {
            t["sheet_id"]: {"frozen_rows": 0, "frozen_cols": 0} for t in self.tab_state
        }
        #: the FLOAT images anchored on each tab (LD-448), keyed by ``sheet_id``. Server
        #: state, deliberately: the whole point of the route is that the fresh QUERY — not
        #: any call's own answer — is what says what exists, and a double that answered the
        #: create's echo would let a recipe pass without ever proving that.
        self.float_images: Dict[str, List[dict]] = {}
        self._minted = 0

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials

        app_id, app_secret = get_write_credentials()
        return cls(app_id, app_secret, domain, **kwargs)

    def _require_known_tab(self, a1_range):
        """Raise Lark's real ``90215 not found sheetId`` for an unknown tab part.

        Checked against the **live** tab set (``tab_state``), not the class fixture, so a
        recipe that deletes a tab and then writes to it refuses exactly as it would live."""
        from larkdocio.errors import LarkAPIError

        tab_part = str(a1_range).split("!")[0]
        if tab_part not in {t["sheet_id"] for t in self.tab_state}:
            raise LarkAPIError(
                f"Failed to read range {a1_range}. Code: 90215, Msg: not found sheetId",
                code=90215, msg="not found sheetId",
            )

    # -- the FILE lifecycle (LD-176) --------------------------------------- #
    #
    # Modelled the way the real endpoints behave where the recipe depends on it: a create
    # mints a token, a delete makes that token STOP RESOLVING, and any later call against it
    # answers Lark's deleted-token code. A double that recorded the calls and stopped would
    # let the disposables recipe "confirm" a delete that never happened — which is the one
    # claim that recipe exists to make.

    def _require_live_token(self, spreadsheet_token):
        """Raise Lark's real deleted-token error for a token this double already trashed."""
        from larkdocio.errors import LarkAPIError
        from larkdocio.sheets.write_client import SPREADSHEET_GONE_CODE

        if spreadsheet_token in self.deleted:
            raise LarkAPIError(
                f"Failed. Code: {SPREADSHEET_GONE_CODE}, Msg: Path param "
                f":spreadsheet_token is deleted",
                code=SPREADSHEET_GONE_CODE,
                msg="Path param :spreadsheet_token is deleted",
            )

    def create_spreadsheet(self, title="", *, folder_token):
        """Mint a disposable the way the v3 create does — a NEW opaque token, echoed title.

        The **destination fence is mirrored, not skipped**: a recipe that forgets where to put
        the workbook must fail here exactly as it fails live, or the offline run would certify
        a recipe the library refuses."""
        require_destination(folder_token, what="a spreadsheet")
        token = f"DISPOSABLETOKEN{len(self.created) + 1:03d}"
        self.created.append(token)
        return {"spreadsheet_token": token, "title": title, "folder_token": folder_token,
                "url": f"https://example.invalid/sheets/{token}"}

    def delete_spreadsheet(self, spreadsheet_token):
        """Trash the file: the token stops resolving, and a second delete raises the DRIVE
        already-deleted error.

        The code matters and is not the sheets one: the live lifecycle arm observed
        ``1061007 file has been delete.`` from this endpoint while a *sheets* call against the
        same trashed token answers ``1310249``. Modelling the endpoint's own code is what
        makes the recipe's ``finally`` (which forgives "already gone") provably correct here
        rather than accidentally correct against a single-code assumption."""
        from larkdocio.errors import LarkAPIError
        from larkdocio.sheets.write_client import FILE_ALREADY_DELETED_CODE

        if spreadsheet_token in self.deleted:
            raise LarkAPIError(
                f"delete spreadsheet failed: Code: {FILE_ALREADY_DELETED_CODE}, "
                f"Msg: file has been delete.",
                code=FILE_ALREADY_DELETED_CODE, msg="file has been delete.",
            )
        self.deleted.append(spreadsheet_token)
        return {}

    def query_tabs(self, spreadsheet_token):
        self._require_live_token(spreadsheet_token)
        # `hidden` is projected the way the shipped client projects it (LD-187): a bool when
        # the payload says, `None` when it does not — never a defaulted False.
        return [{**t, "merges": [dict(m) for m in t.get("merges") or ()],
                 "hidden": t["hidden"] if isinstance(t.get("hidden"), bool) else None}
                for t in sorted(self.tab_state, key=lambda t: t["index"])]

    def read_revision(self, spreadsheet_token):
        return self.revision

    def read_value_range(self, spreadsheet_token, a1_range, value_render_option=None):
        """The whole ``valueRange`` — the verdict read the in-cell image op rides. The
        matrix is :meth:`read_values`' (one implementation here, as in the shipped client);
        the range and the revision come with it, because a write whose proof is *what the
        cell now holds* reports the READ's numbers, not the write's."""
        values = self.read_values(spreadsheet_token, a1_range,
                                  value_render_option or "UnformattedValue")
        return {"range": a1_range, "revision": self.revision,
                "majorDimension": "ROWS", "values": values}

    def put_values_image(self, spreadsheet_token, a1_range, data, name):
        """Store bytes as the cell's VALUE, and mint the media token Lark would mint.

        The disclosure modelled rather than recited: the token is made **here**, by the
        write — nothing was uploaded — and it lands in :class:`OfflineSheetsMediaClient`'s
        store, which is the only place the op's opt-in byte verification can read it from.
        The cell's value becomes the measured ``embed-image`` dict, so the shipped read-back
        parse runs for real."""
        from larkdocio.sheets.extent import column_number_to_a1
        from larkdocio.sheets.write_range import parse_write_range

        self._require_live_token(spreadsheet_token)
        self._require_known_tab(a1_range)
        media = OfflineSheetsMediaClient
        token = f"{media.token_prefix}{len(media.minted) + 1:02d}"
        media.store = dict(media.store, **{token: (name, bytes(data))})
        media.minted = list(media.minted) + [(token, "values_image", spreadsheet_token)]

        wr = parse_write_range(a1_range)
        ref = f"{column_number_to_a1(wr.start.col)}{wr.start.row}"
        self.grid.setdefault(wr.sheet_id, {})[ref] = {
            "type": "embed-image", "fileToken": token, "width": 24, "height": 24,
            "text": "", "link": (
                f"internal-api-space-sg.larksuite.com/space/api/box/stream/download/v2/"
                f"cover/{token}?height=1280&width=1280&policy=equal"
                f"&mount_point=sheet_image&mount_node_token={spreadsheet_token}"),
        }
        self.revision += 1
        return {"revision": self.revision, "spreadsheetToken": spreadsheet_token,
                "updateRange": a1_range}

    # -- the FLOAT-image family (LD-448) ---------------------------------- #

    def create_float_image(self, spreadsheet_token, sheet_id, *, float_image_token,
                           a1_range, width, height, offset_x=0, offset_y=0):
        """Anchor an already-uploaded token over a SINGLE CELL, and REFUSE what Lark refuses.

        Two refusals, both measured and modelled rather than recited:

        * a **multi-cell ``a1_range``** answers ``1310202 "Wrong Range"`` and binds nothing —
          LD-472's refutation of the recipe's own former title (*"float a picture OVER a
          range"*), measured twice live (``tests/test_live_sheets_ld472_doc_truth_gate.py``:
          ``A1:D10`` refused, ``A1:A1`` landed in the same run);
        * a token **nothing minted** answers ``1315203 "Server Error, Retry Later"`` — an HTTP
          500 that is a **refusal** — and creates nothing.

        So a recipe that got the range or the order wrong meets the same answer offline as it
        would live.
        """
        from larkdocio.errors import LarkAPIError
        from larkdocio.sheets.write_client import normalize_write_range

        self._require_live_token(spreadsheet_token)
        normalized = normalize_write_range(a1_range)
        start, _, end = normalized.partition(":")
        if end and start.split("!")[-1] != end:
            raise LarkAPIError(
                "sheets float image create failed: Code: 1310202, Msg: Wrong Range "
                "(offline double — a float image anchors to ONE cell; a multi-cell range is "
                "refused, and the upload that preceded it is already permanent residue)",
                code=1310202, msg="Wrong Range")
        if float_image_token not in OfflineFloatImageMediaClient.store:
            raise LarkAPIError(
                "sheets float image create failed: Code: 1315203, Msg: Server Error, "
                "Retry Later (offline double — a REFUSAL, not a retryable server error)",
                code=1315203, msg="Server Error, Retry Later")
        item = {
            "float_image_id": f"OFFLINEFLOAT{len(self.float_images.get(sheet_id, ())) + 1:02d}",
            "float_image_token": float_image_token,
            "range": normalize_write_range(a1_range),
            "width": width, "height": height,
            "offset_x": offset_x, "offset_y": offset_y,
        }
        self.float_images.setdefault(sheet_id, []).append(item)
        self.revision += 1
        return dict(item)

    def query_float_images(self, spreadsheet_token, sheet_id):
        """The tab's float images — **the verdict read**, answered off server state."""
        self._require_live_token(spreadsheet_token)
        return [dict(item) for item in self.float_images.get(sheet_id, ())]

    def delete_float_image(self, spreadsheet_token, sheet_id, float_image_id):
        """Remove the anchor. **The bytes stay** — the media double's ledger is untouched,
        which is exactly the residue disclosure the shipped op makes."""
        self._require_live_token(spreadsheet_token)
        self.float_images[sheet_id] = [
            item for item in self.float_images.get(sheet_id, ())
            if item["float_image_id"] != float_image_id
        ]
        self.revision += 1
        return {}

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        """The requested rectangle — **every** cell of it, absent cells as ``None``.

        This is how the real values API answers (it never trims server-side), which is the
        behaviour the shipped removed-payload trim exists for: a 2-row delete on a
        20-column tab really does come back 2×20 with 18 ``null``s per row (dogfood F12)."""
        from larkdocio.sheets.extent import column_number_to_a1
        from larkdocio.sheets.write_range import parse_write_range

        self._require_live_token(spreadsheet_token)
        self._require_known_tab(a1_range)
        wr = parse_write_range(a1_range)
        cells = self.grid.get(wr.sheet_id, {})
        return [
            [
                self._render(cells.get(f"{column_number_to_a1(col)}{row}"),
                             value_render_option)
                for col in range(wr.start.col, wr.end.col + 1)
            ]
            for row in range(wr.start.row, wr.end.row + 1)
        ]

    def _render(self, cell, mode):
        """Model Lark's **render modes** for a formula cell (LD-149).

        A cell stored as the object form answers its **expression** under ``Formula`` and its
        **computed value** under the value modes — the asymmetry the whole formula family is
        built on. Any other cell renders the same in every mode (which is also precisely why
        an inert ``=``-string is indistinguishable under ``Formula``).
        """
        from larkdocio.sheets.formula import EXPRESSION_RENDER_OPTION, formula_expression

        expression = formula_expression(cell)
        if expression is None:
            return cell
        if mode == EXPRESSION_RENDER_OPTION:
            return expression
        return type(self).computed.get(expression, expression)

    def put_values(self, spreadsheet_token, a1_range, values):
        """Write the rectangle cell by cell. A ``None`` cell **removes** the cell — which is
        what makes ``[[None]]`` a clear (dogfood F10) rather than a write of the string
        ``"None"``."""
        from larkdocio.sheets.extent import column_number_to_a1
        from larkdocio.sheets.write_range import parse_write_range

        self._require_live_token(spreadsheet_token)
        self._require_known_tab(a1_range)
        self.puts.append((a1_range, values))
        wr = parse_write_range(a1_range)
        cells = self.grid.setdefault(wr.sheet_id, {})
        for i, row in enumerate(values):
            for j, cell in enumerate(row if isinstance(row, list) else [row]):
                ref = f"{column_number_to_a1(wr.start.col + j)}{wr.start.row + i}"
                if cell is None:
                    cells.pop(ref, None)
                else:
                    cells[ref] = cell
        self.revision += 1
        return {"revision": self.revision}

    # -- the destructive half of the surface (LD-152 / dogfood F1) --------- #
    #
    # The four families that had no recipe — structural / merge / dropdown / tab — write
    # through their own seams, so the double has to model those seams for their recipes to
    # execute at all. Each one is modelled the way the REAL endpoint behaves where the
    # engine depends on it: geometry really changes (the engine re-reads it and verifies the
    # shift), the merges array really gains and loses regions (the merge leg diffs it), and
    # `sheets_batch_update` really mints a new `sheetId` and really removes a deleted tab.
    # A double that stored the call and stopped would let a recipe "pass" while teaching a
    # shape the engine's own verification would reject.

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        for tab in self.tab_state:
            if tab["sheet_id"] == sheet_id:
                return {"row_count": tab["row_count"], "column_count": tab["column_count"],
                        "merges": [dict(m) for m in tab.get("merges") or ()]}
        return None                      # a vanished tab — what the real read returns

    def _tab(self, sheet_id):
        for tab in self.tab_state:
            if tab["sheet_id"] == sheet_id:
                return tab
        raise AssertionError(f"the recipe wrote to an unknown tab {sheet_id!r}")

    def set_data_validation(self, spreadsheet_token, a1_range, rule):
        self._require_known_tab(a1_range)
        self.validations.append((a1_range, rule))
        self.revision += 1
        return {}

    def insert_dimension_range(self, spreadsheet_token, sheet_id, major_dimension,
                               start_index, end_index, inherit_style=None):
        tab = self._tab(sheet_id)
        span = end_index - start_index                    # 0-idx half-open
        self.dimension_writes.append(("insert", sheet_id, major_dimension, span))
        key = "row_count" if major_dimension == "ROWS" else "column_count"
        tab[key] += span
        self.revision += 1
        return {}                                        # the insert reply omits a count

    def delete_dimension_range(self, spreadsheet_token, sheet_id, major_dimension,
                               start_index, end_index):
        tab = self._tab(sheet_id)
        span = end_index - start_index + 1                # 1-idx INCLUSIVE
        self.dimension_writes.append(("delete", sheet_id, major_dimension, span))
        key = "row_count" if major_dimension == "ROWS" else "column_count"
        tab[key] -= span
        self.revision += 1
        return {"delCount": span, "majorDimension": major_dimension}

    def append_dimension(self, spreadsheet_token, sheet_id, major_dimension, length):
        tab = self._tab(sheet_id)
        self.dimension_writes.append(("append-dim", sheet_id, major_dimension, length))
        key = "row_count" if major_dimension == "ROWS" else "column_count"
        tab[key] += length
        self.revision += 1
        return {"addCount": length, "majorDimension": major_dimension}

    def set_dimension_properties(self, spreadsheet_token, sheet_id, major_dimension,
                                 start_index, end_index, properties):
        """The dimension-PROPERTY seam. Its span is **1-indexed INCLUSIVE** — the opposite of
        the insert above it — so the double records the band as the caller's own rows/columns
        and asserts nothing shifts: a property write changes presentation only, which is why
        `row_count` / `column_count` are deliberately untouched here."""
        self._tab(sheet_id)
        self.dimension_writes.append(
            ("dimension-property", sheet_id, major_dimension,
             (start_index, end_index), dict(properties)))
        self.revision += 1
        return {}                     # the reply carries neither a count nor a revision

    def put_style(self, spreadsheet_token, a1_range, style):
        """The single-range style seam. The reply nests its revision under `updates`, exactly as
        the live endpoint does (probed), so the recipe exercises the real read-back path."""
        self._require_known_tab(a1_range)
        self.style_writes.append(("put_style", a1_range, dict(style)))
        self.revision += 1
        return {"updates": {"revision": self.revision, "updatedCells": 1,
                            "updatedRange": a1_range}}

    def batch_update_styles(self, spreadsheet_token, style_ranges):
        """The batch style seam — ONE call however many ranges. The reply carries **no**
        revision (probed: only per-range `responses`), so the apply leg's metainfo fallback is
        what the recipe actually runs."""
        for item in style_ranges:
            for a1_range in item["ranges"]:
                self._require_known_tab(a1_range)
        self.style_writes.append(
            ("batch_update_styles",
             tuple(tuple(i["ranges"]) for i in style_ranges),
             tuple(dict(i["style"]) for i in style_ranges)))
        self.revision += 1
        return {"responses": [{"updatedRange": r, "updatedCells": 1}
                              for item in style_ranges for r in item["ranges"]]}

    def append_values(self, spreadsheet_token, a1_range, values, insert_data_option=None):
        self._require_known_tab(a1_range)
        self.dimension_writes.append(("append-values", a1_range, insert_data_option,
                                      len(values)))
        if insert_data_option == "INSERT_ROWS":
            self._tab(str(a1_range).split("!")[0])["row_count"] += len(values)
        self.revision += 1
        return {"revision": self.revision, "updates": {"updatedRows": len(values)}}

    def _region(self, a1_range):
        from larkdocio.sheets.write_range import parse_write_range

        wr = parse_write_range(a1_range)
        return {"start_row_index": wr.start.row - 1, "end_row_index": wr.end.row - 1,
                "start_column_index": wr.start.col - 1, "end_column_index": wr.end.col - 1}

    def merge_cells(self, spreadsheet_token, a1_range, merge_type="MERGE_ALL"):
        self._require_known_tab(a1_range)
        tab = self._tab(str(a1_range).split("!")[0])
        tab.setdefault("merges", []).append(self._region(a1_range))
        self.merge_writes.append(("merge", a1_range, merge_type))
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def unmerge_cells(self, spreadsheet_token, a1_range):
        self._require_known_tab(a1_range)
        tab = self._tab(str(a1_range).split("!")[0])
        target = self._region(a1_range)
        tab["merges"] = [m for m in tab.get("merges") or () if m != target]
        self.merge_writes.append(("unmerge", a1_range))
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def batch_update_sheets(self, spreadsheet_token, requests):
        from larkdocio.errors import LarkAPIError

        self.tab_writes.extend(requests)
        replies = []
        for request in requests:
            if "addSheet" in request:
                props = dict(request["addSheet"]["properties"])
                props["sheetId"] = self._mint_sheet_id(props.get("title", ""),
                                                       at=props.get("index"))
                replies.append({"addSheet": {"properties": props}})
            elif "copySheet" in request:
                source = request["copySheet"]["source"]["sheetId"]
                title = request["copySheet"]["destination"]["title"]
                # A COPY's placement is UNMEASURED — LD-472 measured `addSheet` with no
                # `index` and nothing about `copySheet`, so this double keeps the append it
                # has always modelled rather than generalising a neighbouring measurement.
                sheet_id = self._mint_sheet_id(title, copy_of=source,
                                               at=len(self.tab_state))
                replies.append({"copySheet": {"properties": {"sheetId": sheet_id,
                                                             "title": title, "index": 1}}})
            elif "deleteSheet" in request:
                sheet_id = request["deleteSheet"]["sheetId"]
                self.tab_state = [t for t in self.tab_state if t["sheet_id"] != sheet_id]
                replies.append({"deleteSheet": {"result": True, "sheetId": sheet_id}})
            elif "updateSheet" in request:
                # LD-186 — the FREEZE arm, on the SAME endpoint the tab ops above use. A
                # PATCH, exactly as the live probe characterized it: an axis this request
                # does not name keeps its current value.
                props = dict(request["updateSheet"]["properties"])
                sheet_id = props["sheetId"]
                self._require_known_tab(sheet_id)
                state = self.frozen.setdefault(sheet_id,
                                               {"frozen_rows": 0, "frozen_cols": 0})
                if "frozenRowCount" in props:
                    state["frozen_rows"] = props["frozenRowCount"]
                if "frozenColCount" in props:
                    state["frozen_cols"] = props["frozenColCount"]
                if "frozenRowCount" in props or "frozenColCount" in props:
                    self.freeze_writes.append((sheet_id, props.get("frozenRowCount"),
                                               props.get("frozenColCount")))
                # LD-187 — tab PRESENTATION on the same element, PATCH-wise and with the
                # semantics the live probe characterized: `index` is a target position applied
                # as remove-then-insert (an out-of-range one is CLAMPED, never an error), a
                # duplicate title is refused 90210 (exact, case-SENSITIVE), an empty title
                # 90207, and hiding the last visible tab 95201.
                tab = next(t for t in self.tab_state if t["sheet_id"] == sheet_id)
                if {"index", "title", "hidden"} & set(props):
                    self.presentation_writes.append(
                        (sheet_id, props.get("index"), props.get("title"),
                         props.get("hidden")))
                if "index" in props:
                    target = min(max(props["index"], 0), len(self.tab_state) - 1)
                    order = [t for t in sorted(self.tab_state, key=lambda t: t["index"])
                             if t is not tab]
                    order.insert(target, tab)
                    for position, moved in enumerate(order):
                        moved["index"] = position
                if "title" in props:
                    if not props["title"]:
                        raise LarkAPIError("Code 90207, Msg: sheetTitle should not be empty")
                    if any(t["title"] == props["title"] and t is not tab
                           for t in self.tab_state):
                        raise LarkAPIError(
                            "Code 90210, Msg: sheetTitle already exist in snapshot")
                    tab["title"] = props["title"]
                if "hidden" in props:
                    if props["hidden"] and not any(not t.get("hidden")
                                                   for t in self.tab_state if t is not tab):
                        raise LarkAPIError("Code 95201, Msg: server error")
                    tab["hidden"] = props["hidden"]
                replies.append({"updateSheet": {"properties": dict(props)}})
        self.revision += 1
        return {"replies": replies}

    def read_frozen_panes(self, spreadsheet_token, sheet_id=None):
        """The `metainfo` frozen read (LD-186) — the freeze family's plan-time read AND its
        post-write verification leg, answered off this double's own frozen state so the
        recipe's read-back reflects what its writes actually did."""
        self._require_live_token(spreadsheet_token)
        sheets = {}
        for tab in self.tab_state:
            state = self.frozen.get(tab["sheet_id"], {"frozen_rows": 0, "frozen_cols": 0})
            sheets[tab["sheet_id"]] = {
                "frozen_rows": state["frozen_rows"], "frozen_cols": state["frozen_cols"],
                "row_count": tab["row_count"], "column_count": tab["column_count"],
                "title": tab["title"], "index": tab["index"], "source": "metainfo",
            }
        if sheet_id is None:
            return {"revision": self.revision, "sheets": sheets}
        return sheets.get(sheet_id)

    def _mint_sheet_id(self, title, copy_of=None, at=None):
        """Mint a new tab the way an ``addSheet`` / ``copySheet`` reply does — a NEW opaque
        ``sheetId``, never the title. A copy duplicates the source's merges (which is what
        the engine re-reads to record the duplicated geometry).

        **``at=None`` PLACES THE TAB FIRST** (LD-472). This double used to append in that
        case, matching the guide's *"omit ``index`` to append"* — and both were wrong: an
        ``addSheet`` carrying no ``index`` puts the new tab at position **0**, measured live
        twice (dogfood round 4, re-measured on a disposable for 1.35 —
        ``tests/test_live_sheets_ld472_doc_truth_gate.py``). The double now models what the
        API does, so a recipe teaching the append idiom (``index=len(tabs)``) is proved here
        rather than merely asserted in prose.
        """
        self._minted += 1
        sheet_id = f"new{self._minted:03d}"
        source = next((t for t in self.tab_state if t["sheet_id"] == copy_of), None)
        minted = {
            "sheet_id": sheet_id, "title": title, "index": 0, "hidden": False,
            "row_count": (source or {}).get("row_count", 100),
            "column_count": (source or {}).get("column_count", 20),
            "merges": [dict(m) for m in (source or {}).get("merges") or ()],
        }
        order = sorted(self.tab_state, key=lambda t: t["index"])
        position = 0 if at is None else min(max(int(at), 0), len(order))
        order.insert(position, minted)
        for slot, tab in enumerate(order):
            tab["index"] = slot
        self.tab_state = order
        return sheet_id


#: ``double class -> the shipped class it stands in for`` — the anti-drift pairs.
DOUBLE_PAIRS = [
    ("larkdocio.read.client", "Client", OfflineDocxReadClient),
    ("larkdocio.sheets.client", "SheetsReadClient", OfflineSheetsReadClient),
    ("larkdocio.write.client", "WriteClient", OfflineWriteClient),
    ("larkdocio.sheets.write_client", "SheetsWriteClient", OfflineSheetsWriteClient),
    ("larkdocio.sheets.export_reader", "SheetsExportReader", OfflineSheetsExportReader),
    ("larkdocio.base.client", "BaseReadClient", OfflineBaseReadClient),
    ("larkdocio.base.write_client", "BaseWriteClient", OfflineBaseWriteClient),
    ("larkdocio.base.schema_client", "BaseSchemaClient", OfflineBaseSchemaClient),
    ("larkdocio.base.media", "BaseMediaClient", OfflineBaseMediaClient),
    ("larkdocio.write.media", "DocxMediaClient", OfflineDocxMediaClient),
    ("larkdocio.sheets.media", "SheetsMediaClient", OfflineSheetsMediaClient),
    ("larkdocio.sheets.media", "FloatImageMediaClient", OfflineFloatImageMediaClient),
]


#: class attributes on the doubles that configure them (not stand-ins for real methods).
_DOUBLE_KNOBS = ("empty_document", "documents", "tabs", "values", "computed",
                 "workbook_bytes", "cells", "grid", "user_names", "contact_calls",
                 "copying", "minted", "store", "trashed_apps")


def double_signature_mismatches() -> List[str]:
    """Every way an offline double has drifted from the shipped class it replaces.

    For each public method a double defines, the real class must have a method whose
    positional parameters **start with the same names in the same order**, and the double
    must accept every parameter the real one *requires*. A double may omit a real
    parameter that has a default (it is not exercised); it may never rename, reorder, or
    drop a required one. Guards the harness against the failure mode where a recipe keeps
    passing here against an API that changed underneath it.
    """
    import importlib

    problems: List[str] = []
    for module_name, class_name, double in DOUBLE_PAIRS:
        real = getattr(importlib.import_module(module_name), class_name)
        for name, member in vars(double).items():
            if name.startswith("_") or name in _DOUBLE_KNOBS:
                continue
            func = member.__func__ if isinstance(member, classmethod) else member
            if not callable(func):
                continue
            if not hasattr(real, name):
                problems.append(f"{double.__name__}.{name} has no counterpart on "
                                f"{module_name}.{class_name}")
                continue
            real_attr = getattr(real, name)

            def _positional(sig):
                return [p for p in sig.parameters.values()
                        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]

            want = _positional(inspect.signature(real_attr))
            got = _positional(inspect.signature(getattr(double, name)))
            want_names = [p.name for p in want]
            got_names = [p.name for p in got]
            required = [p.name for p in want if p.default is inspect.Parameter.empty]
            ok = (
                got_names == want_names[: len(got_names)]
                and all(r in got_names for r in required)
            )
            if not ok:
                problems.append(
                    f"{double.__name__}.{name}{inspect.signature(getattr(double, name))} "
                    f"drifted from {class_name}.{name}{inspect.signature(real_attr)}"
                )

        # LD-470 — the VOCABULARY drift, which a signature comparison cannot see. A media
        # double's ``parent_types`` is the allow-list it refuses against, so a double narrower
        # than the shipped client refuses a spelling the real one accepts: a recipe teaching
        # the shipped route then fails offline for a reason that exists nowhere but the
        # harness. (That is exactly what happened — the docx double knew ``docx_image`` and
        # not ``docx_file``, so the attachment recipe could not run.)
        allowed = getattr(real, "ALLOWED_PARENT_TYPES", None)
        if allowed is not None and hasattr(double, "parent_types"):
            got = tuple(double.parent_types or ())
            if got and set(got) != set(allowed):
                problems.append(
                    f"{double.__name__}.parent_types={got!r} drifted from "
                    f"{class_name}.ALLOWED_PARENT_TYPES={tuple(allowed)!r}"
                )
    return problems


# --------------------------------------------------------------------------- #
# 3. The stage — install the doubles + a tmp .env, then run a recipe.            #
# --------------------------------------------------------------------------- #

_ENV_VARS = (
    "LARK_READ_APP_ID", "LARK_READ_APP_SECRET",
    "LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET",
    "LARK_APP_ID", "LARK_APP_SECRET",
)

#: The shipped ``init_env`` — captured ONCE, at import, so a stage can find every module
#: that still binds it (LD-430). ``from larkdocio.common import init_env`` takes a per-module
#: COPY, so patching one module's attribute never reached the others: ``read.download``'s copy
#: kept running the real thing, which bootstraps an empty ``.env`` into the **cwd** and loads
#: it with ``override=True`` — clobbering the stage's offline credentials to ``""``. Identity
#: (not a name list) is the test, so a module that takes the binding later is caught too.
REAL_INIT_ENV = _auth_module.init_env


class OfflineDriveClient:
    """Stands in for :class:`larkdocio.drive.client.DriveClient` at the HTTP boundary only.

    It replaces the two network legs ``walk_folder`` and ``read_folder`` reach — the listing
    (``list_folder_children_to_exhaustion``) and the folder title (``folder_name``) — and returns
    a fixed two-child folder: one ``docx`` to READ (served by the offline docx store through the
    real read pipeline) and one ``file`` to DISCLOSE. Everything else the folder-read recipe
    teaches runs for real: the walk, the ``type``→reader dispatch, the per-child read-or-skip,
    the ``children == read + disclosed`` invariant, and the one-document render.
    """

    #: The listing/title calls made, fresh per stage — a check can assert what it did.
    calls: List = []

    FOLDER_TITLE = "Q3 launch — working folder"
    #: A docx child the offline docx store serves (lazy by token), with a real Lark host so the
    #: shipped URL validator accepts it.
    DOCX_TOKEN = "RECIPEFOLDERDOCXTOKEN"
    DOCX_URL = "https://your-domain.larksuite.com/docx/RECIPEFOLDERDOCXTOKEN"
    #: A raw ``file`` child no reader takes — disclosed by name, never downloaded (R1).
    FILE_TOKEN = "RECIPEFOLDERFILETOKEN"
    #: The listing's per-child identity fields, in the SHAPE the live gate measured them
    #: (``tests/test_live_drive_bytes_leg_gate.py``, 2026-08-15): **unix epoch SECONDS as a
    #: string**, populated on every child kind. They are here because the ledger recipe teaches
    #: what a change detector may key on, and a double serving ``None`` would make the recipe
    #: demonstrate the opposite of what a real folder answers.
    CREATED_TIME = "1786800122"
    MODIFIED_TIME = "1786800122"
    OWNER_ID = "ou_recipefolderowner"

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        """Exercise the credential chain like every other double, then stand in."""
        from larkdocio.common import get_read_credentials

        app_id, app_secret = get_read_credentials()
        if not app_id or not app_secret:
            from larkdocio.errors import LarkConfigError
            raise LarkConfigError(
                "the drive client was constructed with empty credentials — the recipe's "
                "init_env(...) line is load-bearing")
        return cls()

    def list_folder_children_to_exhaustion(self, folder_token=None, *, page_size=None,
                                           max_pages=None):
        from larkdocio.drive.models import FolderChild, FolderContents
        type(self).calls.append(("list", folder_token))
        children = (
            FolderChild(token=self.DOCX_TOKEN, name="Kickoff notes", type="docx",
                        parent_token=folder_token, url=self.DOCX_URL,
                        created_time=self.CREATED_TIME, modified_time=self.MODIFIED_TIME,
                        owner_id=self.OWNER_ID),
            FolderChild(token=self.FILE_TOKEN, name="diagram-source.excalidraw", type="file",
                        parent_token=folder_token, url=None,
                        created_time=self.CREATED_TIME, modified_time=self.MODIFIED_TIME,
                        owner_id=self.OWNER_ID),
        )
        return FolderContents(folder_token=folder_token, children=children, pages=1,
                              has_more=False)

    def folder_name(self, folder_token):
        from larkdocio.drive.models import FolderName
        type(self).calls.append(("name", folder_token))
        return FolderName(token=folder_token, name=self.FOLDER_TITLE)

    #: The by-name lookup, run for REAL over this double's own listing — the SHIPPED function
    #: object, grafted on below at import time. The double replaces the HTTP boundary and
    #: nothing above it, so the pagination loop, the byte-identical matching and the
    #: truncation carry-through are the library's own code: a recipe that teaches *check
    #: before you upload* has to be executing the real check. It is captured **at import**
    #: rather than looked up per call because the stage monkeypatches
    #: ``larkdocio.drive.client.DriveClient`` to this very class, and a per-call lookup would
    #: therefore resolve to the double and recurse.
    find_children_by_name = None

    def list_versions(self, file_token, obj_type="docx", *, page_size=None, max_pages=None):
        """The versions LISTING leg (LD-409), answered from the shared version store.

        The double replaces the HTTP boundary only: the payloads it serves are the shapes the
        editions probe captured (``version`` as the token, epoch-SECOND strings, ``status``
        ``0``), and every line of larkdocio logic the recipe teaches — the rename, the one
        conversion, the newest-first sort — runs for real through ``Version.from_payload``.
        """
        from larkdocio.drive.versions import Version, VersionListing

        type(self).calls.append(("versions", file_token))
        rows = tuple(Version.from_payload(payload)
                     for payload in type(self).versions.get(file_token, ()))
        return VersionListing(
            file_token=file_token, obj_type=obj_type,
            versions=tuple(sorted(rows, key=lambda version: version._sort_key())),
            pages=1, truncation=None,
        )


#: The version store both drive doubles share, keyed by file token — installed fresh per stage
#: so one recipe's create is visible to its own list and to nobody else's.
OfflineDriveClient.versions = {}


def _graft_the_shipped_lookup():
    """Bind the REAL ``find_children_by_name`` onto the double, once, at import time."""
    from larkdocio.drive.client import DriveClient

    OfflineDriveClient.find_children_by_name = DriveClient.find_children_by_name


_graft_the_shipped_lookup()


class OfflineDriveVersionsWriteClient:
    """Stands in for ``DriveVersionsWriteClient`` at the HTTP boundary only.

    The create is served from the same fixed payload shape the probe captured — ``data`` IS the
    version object, and it carries **no** ``update_time`` — and the head revision is the store's
    own. ``check_obj_type`` / ``check_name`` and the whole ``CreatedVersion`` pairing (including
    the duplicate-name echo) are the shipped code, running for real.
    """

    #: The head revision a create pairs with when NO stage is installed. Under a stage the
    #: pairing comes off the document store itself (LD-471) — which is what the shipped op
    #: does: it reads the document's head revision immediately before it creates the version.
    #: A constant made the two doubles disagree, and the ledger recipe's own bound check
    #: ("refuse a pin above head") then fired on a mismatch the harness had invented.
    HEAD_REVISION = 7
    #: What Lark echoes back for a name it has seen before, appended per collision.
    calls: List = []

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials

        app_id, app_secret = get_write_credentials()
        if not app_id or not app_secret:
            from larkdocio.errors import LarkConfigError
            raise LarkConfigError(
                "the drive versions write client was constructed with empty credentials — "
                "the recipe's init_env(...) line is load-bearing")
        return cls()

    @classmethod
    def _head_revision_for(cls, file_token):
        """The document's own head revision when the docx store holds it (LD-471)."""
        store = getattr(OfflineDocxReadClient, "documents", None)
        if store is None:                       # no stage installed — nothing to read
            return cls.HEAD_REVISION
        return store.for_token(file_token).revision

    def create_version(self, file_token, name, obj_type="docx", *, revision_reader=None):
        from larkdocio.drive.versions import Version, check_name, check_obj_type
        from larkdocio.drive.versions_write import CreatedVersion

        obj_type = check_obj_type(obj_type)
        name = check_name(name)
        type(self).calls.append(("create", file_token, name))
        existing = OfflineDriveClient.versions.setdefault(file_token, [])
        taken = sum(1 for row in existing if row["name"].split("(")[0] == name)
        echoed = name if not taken else f"{name}({taken})"
        payload = {
            "create_time": "1786403291",
            "creator_id": "ou_offline_recipe_creator",
            "name": echoed,
            "obj_type": obj_type,
            "owner_id": "ou_offline_recipe_creator",
            "parent_token": file_token,
            "parent_type": obj_type,
            "status": 0,
            "version": f"OFFLINE{len(existing)}",
        }
        # The LIST payload carries update_time; the CREATE echo does not — the shape the model
        # is asserted against, kept different here on purpose.
        existing.append(dict(payload, update_time="1786403292"))
        return CreatedVersion(
            version=Version.from_payload(payload),
            requested_name=name,
            revision=type(self)._head_revision_for(file_token),
            revision_note=None,
        )


class OfflineDriveFilesWriteClient:
    """Stands in for ``DriveFilesWriteClient`` at the **HTTP boundary only**.

    The three legs are modelled as what they are — an upload that mints a token, a metadata
    query that answers the object's own web address, and a download that hands the same bytes
    back — and everything the shipped module does above them runs for real: the
    ``parent_type`` allow-list, the **required folder token**, the ``sha256`` over the bytes as
    sent, and ``verify_round_trip``'s digest comparison.

    **The permalink is SERVED, not constructed by the shipped code.** The double is where the
    address comes from, exactly as Lark is on a live run — so a recipe check can prove the
    library asked for it rather than assembling one out of a host and a token.

    **The residue is modelled the other way round from media, on purpose.** A file object is
    **deletable**, so :attr:`store` really loses it — which is the difference the recipe
    discloses, and a double that kept it would make the disclosure look like a formality.
    """

    #: ``[(op, args…)]`` — inspectable by a recipe check, and reset per stage.
    calls: List[tuple] = []
    #: ``{file_token: (name, folder_token, bytes)}`` — what the Drive would be holding.
    store: Dict[str, tuple] = {}
    #: The host the served permalink is spelled against. Never assembled by shipped code.
    host = "https://your-domain.larksuite.com"
    token_prefix = "boxcnOFFLINEFILE"

    def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
        assert app_id and app_secret, (
            "the drive files write client was constructed with empty credentials — the "
            "recipe's init_env(...) / get_write_credentials() chain did not resolve"
        )
        self.domain = domain

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials
        from larkdocio.errors import LarkConfigError

        app_id, app_secret = get_write_credentials()
        if not (app_id and app_secret):
            raise LarkConfigError("no WRITE credentials in the environment (offline double)")
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def api_calls(self):
        return len(type(self).calls)

    def upload(self, *, data: bytes, name: str, folder_token: str,
               parent_type: str = "explorer"):
        from larkdocio.base.media import sha256_of
        from larkdocio.drive.files_write import (
            EXPLORER_PARENT_TYPE,
            DriveFileUploadError,
            UploadedFile,
        )

        if parent_type != EXPLORER_PARENT_TYPE:
            raise DriveFileUploadError(
                f"parent_type must be {EXPLORER_PARENT_TYPE!r}; got {parent_type!r}")
        if not folder_token:
            raise DriveFileUploadError(
                "an upload needs a folder token — no default destination (offline double)")
        if not data:
            raise DriveFileUploadError(
                "Lark refuses a zero-byte upload with 1061002 params error (offline double)")
        type(self).calls.append(("upload", name, parent_type, folder_token))
        token = f"{type(self).token_prefix}{len(type(self).store) + 1:02d}"
        type(self).store = dict(
            type(self).store, **{token: (name, folder_token, bytes(data))})
        return UploadedFile(file_token=token, folder_token=folder_token, name=name,
                            size=len(data), sha256=sha256_of(data))

    def permalink(self, file_token: str) -> str:
        from larkdocio.drive.files_write import DriveFileMetaError

        if file_token not in type(self).store:
            raise DriveFileMetaError(f"no file for {file_token!r} (offline double)")
        type(self).calls.append(("permalink", file_token))
        return f"{type(self).host}/file/{file_token}"

    def download(self, file_token: str) -> bytes:
        from larkdocio.drive.files_write import DriveFileDownloadError

        if file_token not in type(self).store:
            raise DriveFileDownloadError(f"no file for {file_token!r} (offline double)")
        type(self).calls.append(("download", file_token))
        return type(self).store[file_token][2]

    def delete(self, file_token: str) -> None:
        from larkdocio.drive.files_write import DriveFileDeleteError

        if file_token not in type(self).store:
            raise DriveFileDeleteError(f"no file for {file_token!r} (offline double)")
        type(self).calls.append(("delete", file_token))
        store = dict(type(self).store)
        store.pop(file_token)
        type(self).store = store


def _real_class(module_name: str, class_name: str):
    """The shipped class named ``class_name``, resolved **now** rather than at call time.

    A double that stands in for a class on the *module* a recipe imports from cannot re-import
    its own subject: by then the module attribute is the double, and the "build the real client
    over a routing transport" pattern would recurse forever. Resolving at import time — this
    module loads before any stage patches anything — keeps that pattern usable.
    """
    import importlib

    return getattr(importlib.import_module(module_name), class_name)


class OfflineDriveFoldersWriteClient:
    """Stands in for ``DriveFoldersWriteClient`` at the **HTTP boundary only** (LD-467).

    The :class:`OfflineDriveAccessWriteClient` shape, for its reason: ``from_write_credentials``
    builds the **REAL** client over a routing transport, so the local name / parent gates, the
    wire body and the refusal typing are the shipped code running for real, and only Lark's
    answer is the double's.

    **The duplicate-name behaviour is MODELLED, not smoothed:** the store is keyed by token, so
    the same ``(name, parent)`` twice really does leave two folders — the measured truth the
    recipe discloses. A double that de-duplicated would make the disclosure look like a
    formality.
    """

    #: ``{folder_token: (name, parent_token)}`` — what the Drive would be holding.
    store: Dict[str, tuple] = {}
    calls: List[tuple] = []
    #: The host the served folder url is spelled against. Never assembled by shipped code.
    host = "https://your-domain.larksuite.com"
    token_prefix = "fldrOFFLINEFOLDER"

    #: The **REAL** client, captured at import time — i.e. before any stage monkeypatches the
    #: module attribute this double replaces. The access double can re-import its subject
    #: because it is patched on the *package*; this one is patched on the *module* the shipped
    #: recipe imports from, so a re-import here would hand back the double and recurse.
    real = _real_class("larkdocio.drive.folders_write", "DriveFoldersWriteClient")

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials
        from larkdocio.common.transport import RateLimiter

        app_id, app_secret = get_write_credentials()
        if not app_id or not app_secret:
            from larkdocio.errors import LarkConfigError
            raise LarkConfigError(
                "the drive folders write client was constructed with empty credentials — "
                "the recipe's init_env(...) line is load-bearing")
        return cls.real(
            app_id, app_secret, domain,
            urlopen=cls._transport,
            token_fetcher=lambda *a, **k: "t-offline-token",
            rate_limiter=RateLimiter(10 ** 6, window=0.000001),
        )

    @classmethod
    def _transport(cls, request, timeout=None):
        import io
        import json
        import urllib.parse

        parsed = urllib.parse.urlsplit(request.full_url)
        body = json.loads(request.data.decode()) if request.data else None
        assert parsed.path.endswith("/files/create_folder"), parsed.path
        name, parent = body["name"], body["folder_token"]
        cls.calls.append(("create_folder", name, parent))
        token = f"{cls.token_prefix}{len(cls.store) + 1:02d}"
        cls.store = dict(cls.store, **{token: (name, parent)})
        answer = {"code": 0, "msg": "success",
                  "data": {"token": token, "url": f"{cls.host}/drive/folder/{token}"}}
        return io.BytesIO(json.dumps(answer).encode())


class OfflineDriveAccessWriteClient:
    """Stands in for ``DriveAccessWriteClient`` at the **HTTP boundary only** (LD-432).

    Nothing about the surface is re-implemented here: ``from_write_credentials`` builds the
    REAL client and gives it a routing transport plus a fixed address resolver, so the gates,
    the wire paths and parameters, the one-key-per-call PATCH sequence and — above all — the
    **read-back** that turns an accepted call into a verdict are the shipped code running for
    real. The store below is what Lark would have remembered.
    """

    #: ``{file_token: {open_id: perm}}`` — the member list this "tenant" holds.
    members: dict = {}
    #: ``{file_token: {key: value}}`` — the public settings, seeded at the MEASURED baseline.
    public: dict = {}
    #: The owner of every document here: the bot's own id, which is NOT a member row.
    OWNER_ID = "ou_0ff11ne0rec1pe0b0100000000000bot"
    #: What the address route answers with — one id, so ``exactly one`` is satisfied for real.
    GRANTEE_ID = "ou_0ff11ne0rec1pe09ra17ee00000000ee"
    calls: List = []

    #: The baseline a freshly minted docx really carries (capture ``705-``).
    BASELINE = {
        "comment_entity": "anyone_can_view", "copy_entity": "anyone_can_edit",
        "external_access_entity": "closed", "link_share_entity": "tenant_readable",
        "lock_switch": False, "manage_collaborator_entity": "collaborator_can_edit",
        "security_entity": "anyone_can_edit", "share_entity": "anyone",
    }

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        from larkdocio.common import get_write_credentials
        from larkdocio.common.transport import RateLimiter
        from larkdocio.drive.access_write import DriveAccessWriteClient

        app_id, app_secret = get_write_credentials()
        if not app_id or not app_secret:
            from larkdocio.errors import LarkConfigError
            raise LarkConfigError(
                "the drive access write client was constructed with empty credentials — "
                "the recipe's init_env(...) line is load-bearing")
        return DriveAccessWriteClient(
            app_id, app_secret, domain,
            urlopen=cls._transport,
            token_fetcher=lambda *a, **k: "t-offline-token",
            rate_limiter=RateLimiter(10 ** 6, window=0.000001),
            resolver=cls._resolve,
        )

    @classmethod
    def _resolve(cls, *, email):
        from larkdocio.contacts.lookup import NameLookup, Partiality, UserRef

        cls.calls.append(("resolve", email))
        return NameLookup(query=email, partiality=Partiality(),
                          user=UserRef(open_id=cls.GRANTEE_ID, display_name="A Second User"))

    @classmethod
    def _transport(cls, request, timeout=None):
        import io
        import json
        import urllib.parse

        method = request.get_method()
        parsed = urllib.parse.urlsplit(request.full_url)
        path = parsed.path
        body = json.loads(request.data.decode()) if request.data else None
        cls.calls.append((method, path))
        answer = {"code": 0, "data": {}, "msg": "Success"}

        if path.endswith("/metas/batch_query"):
            token = body["request_docs"][0]["doc_token"]
            answer = {"code": 0, "msg": "Success", "data": {"metas": [
                {"doc_token": token, "doc_type": "docx", "owner_id": cls.OWNER_ID}]}}
        elif "/permissions/" in path and path.endswith("/public"):
            token = path.split("/permissions/")[1].split("/")[0]
            settings = cls.public.setdefault(token, dict(cls.BASELINE))
            if method == "PATCH":
                assert len(body) == 1, f"one key per call, got {sorted(body)}"
                settings.update(body)
                answer = {"code": 0, "msg": "", "data": {"permission_public": dict(body)}}
            else:
                answer = {"code": 0, "msg": "",
                          "data": {"permission_public": dict(settings)}}
        elif "/permissions/" in path:
            token = path.split("/permissions/")[1].split("/")[0]
            roster = cls.members.setdefault(token, {})
            tail = path.split("/members")[1].lstrip("/")
            if method == "GET":
                answer = {"code": 0, "msg": "Success", "data": {"items": [
                    {"member_id": mid, "member_type": "openid", "perm": perm,
                     "perm_type": "container"} for mid, perm in roster.items()]}}
            elif method == "POST":
                roster[body["member_id"]] = body["perm"]
                answer = {"code": 0, "msg": "Success", "data": {"member": dict(body)}}
            elif method == "PUT":
                roster[tail] = body["perm"]
                answer = {"code": 0, "msg": "Success",
                          "data": {"member": {"member_id": tail, "perm": body["perm"]}}}
            elif method == "DELETE":
                roster.pop(tail, None)
        return io.BytesIO(json.dumps(answer).encode())


@dataclass
class OfflineStage:
    """The offline stage a guide recipe executes on.

    ``install`` (a) strips every ``LARK_*`` credential from the process env so nothing
    can leak in, (b) writes a tmp ``.env`` and redirects ``init_env`` to load *it*,
    (c) swaps the four network clients for their doubles at the module attributes the
    recipes import them from, and (d) gives the docx read + write doubles **one fresh
    document store** so a recipe's writes are visible to its later reads (and so no state
    leaks between tests). Everything else is the shipped code.
    """

    monkeypatch: object
    tmp_path: object
    empty_document: bool = False
    #: serve the MENTION-BEARING document (LD-173) — opt-in, so every other stage's document
    #: (and therefore every other recipe's Markdown) is byte-identical to before.
    mentions: bool = False
    #: serve a Base whose first table carries a LINK COLUMN with one live and one dead target
    #: (LD-283) — opt-in for exactly the reason ``mentions`` is: the captured Base has no link
    #: column, and seeding one for every stage would change what every other Base recipe reads.
    #: The link-resolution recipe is a pure READ, so the shape it reads has to come from the
    #: stage — the same division of labour the mention-bearing document already uses.
    base_links: bool = False
    #: the per-stage document store, set by :meth:`install` (inspectable by a recipe check).
    documents: Optional[OfflineDocuments] = None
    env: Dict[str, str] = field(default_factory=lambda: {
        "LARK_READ_APP_ID": "cli_read_offline",
        "LARK_READ_APP_SECRET": "read-secret-offline",
        "LARK_WRITE_APP_ID": "cli_write_offline",
        "LARK_WRITE_APP_SECRET": "write-secret-offline",
    })
    init_env_calls: List[Optional[str]] = field(default_factory=list)

    def install(self) -> "OfflineStage":
        import larkdocio.base as base_pkg
        import larkdocio.base.client as base_client
        import larkdocio.comments as comments_pkg
        import larkdocio.comments.client as comments_client
        import larkdocio.comments.read as comments_read
        import larkdocio.contacts as contacts_pkg
        import larkdocio.contacts.client as contacts_client
        import larkdocio.common as common
        import larkdocio.read.client as read_client
        import larkdocio.sheets.client as sheets_client
        import larkdocio.sheets.export_reader as sheets_export_reader
        import larkdocio.sheets.write_client as sheets_write_client
        import larkdocio.write as write_pkg
        import larkdocio.write.client as write_client
        from dotenv import load_dotenv

        for var in _ENV_VARS:
            self.monkeypatch.delenv(var, raising=False)

        env_file = self.tmp_path / ".env"
        env_file.write_text(
            "".join(f"{k}={v}\n" for k, v in self.env.items()), encoding="utf-8")

        calls = self.init_env_calls

        def _offline_init_env(env_path=None, *, create=True):
            """``init_env`` minus the two production side effects (creating a ``.env``
            in the cwd, pinning the socket to IPv4) — it still LOADS an env file, so the
            recipes' opening line stays load-bearing.

            ``create`` is accepted to keep the signature identical to the shipped
            function's (the stand-in is patched onto every module that binds it, so a
            drift surfaces far from its cause) and is then ignored: the file this loads
            is the stage's own tmp ``.env``, which always exists, so neither branch the
            keyword selects between is reachable here."""
            calls.append(env_path)
            load_dotenv(dotenv_path=str(env_file), override=True)
            return str(env_file)

        # Patch the redirect onto EVERY module that binds ``init_env``, not just
        # ``larkdocio.common`` (LD-430). ``from larkdocio.common import init_env`` copies the
        # function onto the importing module, so one setattr left ``read.download`` (and
        # therefore the folder read's ``_dl.init_env(None)``) calling the shipped one — which
        # bootstraps an empty ``.env`` into the cwd and loads it with ``override=True``, wiping
        # the stage's credentials. The CLI entry points are imported first so their bindings
        # exist to be found; the sweep is by identity, so a future binding is covered without
        # this list growing.
        for module_name in ("larkdocio.auth", "larkdocio.read.config_cmd",
                            "larkdocio.read.download", "larkdocio.drive.folder_cmd"):
            importlib.import_module(module_name)
        for module in [m for m in list(sys.modules.values()) if m is not None]:
            if getattr(module, "__name__", "").split(".")[0] != "larkdocio":
                continue
            if getattr(module, "init_env", None) is REAL_INIT_ENV:
                self.monkeypatch.setattr(module, "init_env", _offline_init_env)
        # The defining module last, so the sweep above could still recognise the original.
        self.monkeypatch.setattr(_auth_module, "init_env", _offline_init_env)
        self.monkeypatch.setattr(common, "init_env", _offline_init_env)

        self.monkeypatch.setattr(
            OfflineDocxReadClient, "empty_document", self.empty_document)
        self.monkeypatch.setattr(OfflineWriteClient, "empty_document", self.empty_document)

        # ONE store, shared by the read + write doubles, fresh per stage (monkeypatch undoes
        # it), so a recipe's writes are visible to its later reads and nothing leaks between
        # tests.
        self.documents = OfflineDocuments(empty=self.empty_document, mentions=self.mentions)
        self.monkeypatch.setattr(OfflineDocxReadClient, "documents", self.documents)
        self.monkeypatch.setattr(OfflineWriteClient, "documents", self.documents)

        # The contacts directory the read double answers from, and its call log — both fresh
        # per stage (LD-173), so one test's resolution cost cannot leak into the next's.
        self.monkeypatch.setattr(
            OfflineDocxReadClient, "user_names", dict(_FIXTURE_MENTION_NAMES))
        self.monkeypatch.setattr(OfflineDocxReadClient, "contact_calls", [])

        # The comments double's endpoint log, fresh per stage for the same reason (LD-172).
        self.monkeypatch.setattr(OfflineCommentsReadClient, "ops", [])

        # The contacts (name -> id) double's query log, fresh per stage for the same reason
        # (LD-229). Swapped at BOTH the module attribute resolve_user imports lazily and the
        # package re-export, because a recipe may reach either path.
        self.monkeypatch.setattr(OfflineContactsSearchClient, "queries", [])
        self.monkeypatch.setattr(
            contacts_client, "ContactsSearchClient", OfflineContactsSearchClient)
        self.monkeypatch.setattr(
            contacts_pkg, "ContactsSearchClient", OfflineContactsSearchClient)

        # The captured xlsx the fidelity recipe's export leg serves (LD-152) — installed on
        # the double per stage, so no test can leak a workbook into the next one.
        self.monkeypatch.setattr(
            OfflineSheetsExportReader, "workbook_bytes", captured_export_workbook())
        self.monkeypatch.setattr(
            sheets_export_reader, "SheetsExportReader", OfflineSheetsExportReader)

        self.monkeypatch.setattr(read_client, "Client", OfflineDocxReadClient)
        # The docx download PATH binds ``Client`` at its own module scope
        # (``from .client import Client``), and the folder read reaches the docx reader through
        # it (``drive.read._read_docx_markdown`` → ``download._resolve_doc``). Patch that binding
        # too, so a folder recipe reading a docx child never touches the network.
        import larkdocio.read.download as read_download
        self.monkeypatch.setattr(read_download, "Client", OfflineDocxReadClient)
        # The Drive enumeration client — the network legs the folder read reaches. Swapped at
        # the name ``drive.read`` imports it under, fresh call log per stage.
        import larkdocio.drive.read as drive_read
        self.monkeypatch.setattr(OfflineDriveClient, "calls", [])
        self.monkeypatch.setattr(drive_read, "DriveClient", OfflineDriveClient)
        # …and at its DEFINING module too, because the upload recipe's by-name lookup imports
        # it from there (``from larkdocio.drive.client import DriveClient``). A patch that
        # reached only the folder-read binding would let that block touch the network.
        import larkdocio.drive.client as drive_client
        self.monkeypatch.setattr(drive_client, "DriveClient", OfflineDriveClient)
        # LD-409 — the named-version legs. Swapped at the PACKAGE re-exports, because that is
        # the path the versions recipe imports them from, and given a fresh shared version
        # store per stage so one recipe's create cannot leak into the next one's listing.
        import larkdocio.drive as drive_pkg
        self.monkeypatch.setattr(OfflineDriveClient, "versions", {})
        self.monkeypatch.setattr(OfflineDriveVersionsWriteClient, "calls", [])
        self.monkeypatch.setattr(drive_pkg, "DriveClient", OfflineDriveClient)
        self.monkeypatch.setattr(
            drive_pkg, "DriveVersionsWriteClient", OfflineDriveVersionsWriteClient)
        # LD-432 — the ACCESS legs. Swapped at the package re-export for the same reason, with
        # a fresh member roster and settings store per stage so one recipe's grant cannot leak
        # into the next one's read-back — which, on this surface, IS the verdict.
        self.monkeypatch.setattr(OfflineDriveAccessWriteClient, "members", {})
        self.monkeypatch.setattr(OfflineDriveAccessWriteClient, "public", {})
        self.monkeypatch.setattr(OfflineDriveAccessWriteClient, "calls", [])
        self.monkeypatch.setattr(
            drive_pkg, "DriveAccessWriteClient", OfflineDriveAccessWriteClient)
        # The comments read (LD-159) — swapped at BOTH the module attribute and the package
        # re-export, because a recipe may import either path.
        self.monkeypatch.setattr(
            comments_client, "CommentsReadClient", OfflineCommentsReadClient)
        self.monkeypatch.setattr(
            comments_read, "CommentsReadClient", OfflineCommentsReadClient)
        self.monkeypatch.setattr(
            comments_pkg, "CommentsReadClient", OfflineCommentsReadClient)
        self.monkeypatch.setattr(sheets_client, "SheetsReadClient", OfflineSheetsReadClient)
        # The Base read (LD-251). Swapped at the module attribute ``read_base`` imports lazily
        # AND at the package re-export, because a recipe may reach either path; the call log is
        # fresh per stage for the same reason every other double's is.
        self.monkeypatch.setattr(OfflineBaseReadClient, "calls", [])
        self.monkeypatch.setattr(OfflineBaseReadClient, "revision_bump", 0)
        self.monkeypatch.setattr(OfflineBaseReadClient, "copying", 0)
        self.monkeypatch.setattr(OfflineBaseReadClient, "trashed_apps", [])
        self.monkeypatch.setattr(OfflineBaseReadClient, "app_name_override", None)
        self.monkeypatch.setattr(OfflineBaseReadClient, "extra_tables", [])
        self.monkeypatch.setattr(OfflineBaseReadClient, "table_renames", {})
        self.monkeypatch.setattr(OfflineBaseReadClient, "views", {})
        # The FIELD and CELL overlays (LD-291) — fresh per stage like every other one, or a
        # migration recipe would find the previous stage's staging column already there.
        self.monkeypatch.setattr(OfflineBaseReadClient, "created_fields", [])
        self.monkeypatch.setattr(OfflineBaseReadClient, "deleted_field_ids", [])
        self.monkeypatch.setattr(OfflineBaseReadClient, "field_renames", {})
        self.monkeypatch.setattr(OfflineBaseReadClient, "cell_writes", {})
        self.monkeypatch.setattr(OfflineBaseReadClient, "created_records", [])
        # The FIELD-PROPERTY overlay (LD-283) — fresh per stage for the same reason: a link
        # column left pointing somewhere by the previous stage is a target this one never made.
        self.monkeypatch.setattr(OfflineBaseReadClient, "created_field_properties", {})
        if self.base_links:
            self._seed_base_link_column()
        self.monkeypatch.setattr(base_client, "BaseReadClient", OfflineBaseReadClient)
        if hasattr(base_pkg, "BaseReadClient"):
            self.monkeypatch.setattr(base_pkg, "BaseReadClient", OfflineBaseReadClient)
        # The Base RECORD WRITE (LD-260). Same two seams, same fresh-per-stage call log.
        import larkdocio.base.write_client as base_write_client
        self.monkeypatch.setattr(OfflineBaseWriteClient, "calls", [])
        self.monkeypatch.setattr(base_write_client, "BaseWriteClient", OfflineBaseWriteClient)
        if hasattr(base_pkg, "BaseWriteClient"):
            self.monkeypatch.setattr(base_pkg, "BaseWriteClient", OfflineBaseWriteClient)
        # The Base SCHEMA write (LD-263). Same two seams, same fresh-per-stage call log.
        import larkdocio.base.schema_client as base_schema_client
        self.monkeypatch.setattr(OfflineBaseSchemaClient, "calls", [])
        self.monkeypatch.setattr(
            base_schema_client, "BaseSchemaClient", OfflineBaseSchemaClient)
        if hasattr(base_pkg, "BaseSchemaClient"):
            self.monkeypatch.setattr(base_pkg, "BaseSchemaClient", OfflineBaseSchemaClient)
        # The Base MEDIA leg (LD-283). Same two seams; the token store and the residue ledger
        # are fresh per stage, so no recipe can hash bytes another one uploaded.
        import larkdocio.base.media as base_media
        self.monkeypatch.setattr(OfflineBaseMediaClient, "calls", [])
        self.monkeypatch.setattr(OfflineBaseMediaClient, "minted", [])
        self.monkeypatch.setattr(OfflineBaseMediaClient, "store", {})
        self.monkeypatch.setattr(base_media, "BaseMediaClient", OfflineBaseMediaClient)
        if hasattr(base_pkg, "BaseMediaClient"):
            self.monkeypatch.setattr(base_pkg, "BaseMediaClient", OfflineBaseMediaClient)
        # The docx IMAGE media leg (LD-433). Same discipline as the Base one above, on its
        # own ledgers so an image upload and an attachment upload are never confused.
        import larkdocio.write.media as docx_media
        self.monkeypatch.setattr(OfflineDocxMediaClient, "calls", [])
        self.monkeypatch.setattr(OfflineDocxMediaClient, "minted", [])
        self.monkeypatch.setattr(OfflineDocxMediaClient, "store", {})
        self.monkeypatch.setattr(docx_media, "DocxMediaClient", OfflineDocxMediaClient)
        if hasattr(write_pkg, "DocxMediaClient"):
            self.monkeypatch.setattr(write_pkg, "DocxMediaClient", OfflineDocxMediaClient)
        # The DRIVE FILES write leg (LD-434) — the folder-upload slice. Its store is reset per
        # stage like every other double's, and it is the leg that SERVES the permalink, so a
        # recipe check can prove the shipped code asked for an address rather than built one.
        import larkdocio.drive.files_write as drive_files
        self.monkeypatch.setattr(OfflineDriveFilesWriteClient, "calls", [])
        self.monkeypatch.setattr(OfflineDriveFilesWriteClient, "store", {})
        self.monkeypatch.setattr(
            drive_files, "DriveFilesWriteClient", OfflineDriveFilesWriteClient)
        # The DRIVE FOLDERS write leg (LD-467) — the one R3 organize verb. Fresh store per
        # stage like every other double's, and it MODELS the duplicate-name behaviour rather
        # than smoothing it, because that is what the recipe discloses.
        import larkdocio.drive.folders_write as drive_folders
        self.monkeypatch.setattr(OfflineDriveFoldersWriteClient, "calls", [])
        self.monkeypatch.setattr(OfflineDriveFoldersWriteClient, "store", {})
        self.monkeypatch.setattr(
            drive_folders, "DriveFoldersWriteClient", OfflineDriveFoldersWriteClient)
        self.monkeypatch.setattr(write_client, "WriteClient", OfflineWriteClient)
        self.monkeypatch.setattr(write_pkg, "WriteClient", OfflineWriteClient)
        self.monkeypatch.setattr(
            sheets_write_client, "SheetsWriteClient", OfflineSheetsWriteClient)
        # The SHEETS MEDIA leg (LD-447) — download-only, and its store is filled by the write
        # double above rather than by an upload, which is the route's own disclosure.
        import larkdocio.sheets.media as sheets_media
        self.monkeypatch.setattr(OfflineSheetsMediaClient, "calls", [])
        self.monkeypatch.setattr(OfflineSheetsMediaClient, "minted", [])
        self.monkeypatch.setattr(OfflineSheetsMediaClient, "store", {})
        self.monkeypatch.setattr(sheets_media, "SheetsMediaClient", OfflineSheetsMediaClient)
        # The FLOAT-image media leg (LD-448) — its OWN ledgers, because the two sheet media
        # routes mint tokens independently and one shared ledger would hide that.
        self.monkeypatch.setattr(OfflineFloatImageMediaClient, "calls", [])
        self.monkeypatch.setattr(OfflineFloatImageMediaClient, "minted", [])
        self.monkeypatch.setattr(OfflineFloatImageMediaClient, "store", {})
        self.monkeypatch.setattr(
            sheets_media, "FloatImageMediaClient", OfflineFloatImageMediaClient)
        # the sheets package re-exports the write client; recipes may import either path.
        import larkdocio.sheets as sheets_pkg
        if hasattr(sheets_pkg, "SheetsWriteClient"):
            self.monkeypatch.setattr(sheets_pkg, "SheetsWriteClient", OfflineSheetsWriteClient)
        if hasattr(sheets_pkg, "SheetsReadClient"):
            self.monkeypatch.setattr(sheets_pkg, "SheetsReadClient", OfflineSheetsReadClient)
        if hasattr(sheets_pkg, "SheetsExportReader"):
            self.monkeypatch.setattr(
                sheets_pkg, "SheetsExportReader", OfflineSheetsExportReader)

        # The zero-Markdown call spy — installed for EVERY staged run (it only counts and
        # delegates), so any recipe's check can assert what it did or did not touch.
        _reset_markdown_calls()
        for module_name, class_name, attr in MARKDOWN_CALL_SITES:
            module = importlib.import_module(module_name)
            owner = getattr(module, class_name) if class_name else module
            self.monkeypatch.setattr(owner, attr, _counting(attr, getattr(owner, attr)))
        return self

    #: The dead record id the seeded link cell points at. It is deliberately **not** a plausible
    #: id: a reader of a failure message should be able to tell at a glance which of the two
    #: targets was the one that no longer exists.
    DEAD_LINK_TARGET = "recDELETEDLONGAGO"

    def _seed_base_link_column(self) -> None:
        """Give the captured Base one link column whose cell holds **one live and one dead**
        target, so a pure-read recipe has the shape it is about.

        The captured Base carries no link column — the real one it was captured from had none —
        so a recipe that only reads could otherwise demonstrate nothing. Seeding it here rather
        than inside the recipe is the point: the shipped text stays a *read*, and does not teach
        a consumer to manufacture a broken reference in order to look at one. The two targets
        together are the whole lesson: the target **table** is alive (so the free schema reading
        stays empty) while one linked **record** is gone (which only resolution can find).
        """
        import base_captures

        _app, tables, per_table = base_captures.scratch_base()
        source, target = tables[0], tables[1]
        live_id = per_table[target.table_id][1][0].record_id
        field_id = "fldOFFLINELINK"
        self.monkeypatch.setattr(
            OfflineBaseReadClient, "created_fields",
            [(source.table_id, field_id, "Owner", 18, "SingleLink")])
        self.monkeypatch.setattr(
            OfflineBaseReadClient, "created_field_properties",
            {(source.table_id, field_id): {"table_id": target.table_id}})
        self.monkeypatch.setattr(
            OfflineBaseReadClient, "cell_writes",
            {(source.table_id, per_table[source.table_id][1][0].record_id):
                {"Owner": [live_id, self.DEAD_LINK_TARGET]}})

    def run(self, slug: str, *, source: Optional[str] = None) -> dict:
        # ``run_recipe`` belongs to the RECIPE side (``guide_recipes``); imported at CALL
        # time so the dependency between the two halves stays one-way and cycle-free — and
        # so a test that patches ``guide_recipes.run_recipe`` is still honoured here, which
        # a module-level import would defeat.
        from guide_recipes import run_recipe

        _reset_markdown_calls()          # per-run counts, never accumulated across runs
        return run_recipe(slug, source=source)


def stage(monkeypatch, tmp_path, **kwargs) -> OfflineStage:
    """Build + install an :class:`OfflineStage` (the one-liner the tests use)."""
    return OfflineStage(monkeypatch=monkeypatch, tmp_path=tmp_path, **kwargs).install()
