"""larkdocio.base.hierarchy — the Lark row tree, read honestly and written through what ships.

A Lark row tree ("sub-items") is **not a record concept**. There is no ``parent_id`` on a
record and no hierarchy endpoint anywhere in the Base API. What exists is a **link field
pointed at its own table** — ``SingleLink`` (18) or ``DuplexLink`` (21) whose
``property.table_id`` is the table's OWN id — and **one view property**,
``property.hierarchy_config.field_id``, that names it. The parent edge is an ordinary
link-cell **value**; the read is a **parent pointer, never nesting**.

So this module is mostly *composition*, and that is the point:

* the column is authored by the shipped field family (a self-link is a link whose target
  happens to be itself — :func:`larkdocio.base.field_authoring.build_property`);
* the edge is written by the shipped write-cell encoder (:mod:`larkdocio.base.write_cells`);
* a parent id already resolves to a name through the shipped opt-in resolver
  (:mod:`larkdocio.base.link_resolution`);
* what is **new** is naming the hierarchy field on a view, reconstructing the tree from the
  pointers, and being honest about the two structures Lark accepts that no tree can contain.

**The capability is easy and the honesty is the product.** Lark accepts, at ``code:0``, a row
with **two parents** and a row that is **its own parent**. This library therefore **discloses**
both and refuses neither — see :data:`HAZARDS_ARE_DISCLOSED_NOT_REFUSED` — while the read
**never lies and never hangs**: a cycle terminates with a typed marker on the rows involved,
both parents of a two-parent row survive into the output, a parent id that is not in what was
read takes the honest third state rather than becoming a root, and a table with no hierarchy
reads *not configured* rather than as an empty tree.

**Nothing here makes a call.** Every function is pure over data a read already holds: field
specs, records, and — where the caller has one — an already-read view object and an already
computed :class:`~larkdocio.base.link_resolution.LinkResolution`. No client is imported at
module level, no function takes one, and a guard over this file's own syntax tree says so.

**Nothing here repairs anything.** No verb breaks a cycle, drops a second parent or deletes a
dangling pointer — :mod:`larkdocio.base.referential`'s standing rule governs. Rendering the
structure honestly is the whole product.
"""
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from larkdocio.base._typed import _by_name
from larkdocio.base.link_resolution import (
    LINK_DANGLING,
    LINK_RESOLUTION_STATES,
    LINK_RESOLVED,
    LINK_UNRESOLVABLE,
    STATE_MEANINGS as POINTER_STATE_MEANINGS,
)
from larkdocio.base.referential import LINK_TYPES
from larkdocio.common.citations import dev_repo

_CAPTURES = "tests/captures/base-study/captures"

#: The spike this whole surface rests on.
HIERARCHY_EVIDENCE = dev_repo("dev/base-study/subitems-spike-2026-08-05.md")

#: The per-pointer outcome vocabulary, **re-exported rather than re-spelled**. A parent
#: pointer is a link, so what can be said about it is what
#: :mod:`larkdocio.base.link_resolution` already says about a link: resolved, dangling, or the
#: honest third state that claims nothing in either direction.
PARENT_POINTER_STATES: Tuple[str, ...] = LINK_RESOLUTION_STATES


# --------------------------------------------------------------------------- #
# The mechanism, stated once                                                    #
# --------------------------------------------------------------------------- #

HIERARCHY_IS_A_SELF_LINK_FIELD = (
    "A Lark row tree is a LINK COLUMN POINTED AT ITS OWN TABLE plus one view property. The "
    "column is an ordinary SingleLink (18) or DuplexLink (21) whose property.table_id is the "
    "table's own id — both were created code:0 — and the view property "
    "property.hierarchy_config.field_id names which column it is. There is no other machinery: "
    "the pinned SDK's whole hierarchy footprint is one class with one field."
)

#: **A declared, exported disclosure with no producer in this tree.** Measured 2026-09-03: the
#: only occurrences of this name under ``src/``, ``tests/`` and ``scripts/`` are this definition
#: and its ``__all__`` entry, so no read, plan or refusal in this library attaches the text to
#: anything a caller receives — it is reachable only by importing the name. Of the 34
#: module-level constants in this module it is the only one at that count; every other sits at
#: three occurrences or more. Recorded rather than tested: asserting the string equals itself
#: would prove nothing about a disclosure nothing attaches. **Whether a reading SHOULD carry it
#: is an open product question, deliberately not settled here.**
PARENT_EDGE_IS_A_LINK_VALUE = (
    "The child -> parent edge is written as an ORDINARY LINK-CELL VALUE on the child's "
    "self-referencing column: set the cell to [<parent record_id>], at create time or by "
    "update. Three levels deep, both shapes answered code:0. There is no hierarchy-specific "
    "write route in this library and there is no hierarchy write endpoint in Lark's API — the "
    "shipped record-write path IS the route, and a second one would be a second definition of "
    "a write that already works."
)

#: The six keys a body-key battery proved **indistinguishable from a deliberately bogus key**.
REFUTED_PARENT_BODY_KEYS: Tuple[str, ...] = (
    "parent_id", "parent_record_id", "parent", "sub_item_parent", "parent_record",
    "hierarchy_parent_id",
)

NO_BODY_KEY_MAKES_A_CHILD = (
    "NO REQUEST-BODY KEY MAKES A RECORD A CHILD. Six candidates were each sent on a record "
    "create carrying the real parent's record_id — " + ", ".join(REFUTED_PARENT_BODY_KEYS) +
    " — and every one answered code:0 and read back empty, exactly as the deliberately bogus "
    "control key larkdocio_not_a_real_key did. The same two keys behaved identically on an "
    "update. This API silently ignores body keys it does not recognise, so code:0 on a "
    "hierarchy body key means the key was thrown away, not that a parent was set."
)

CODE_ZERO_IS_NOT_EVIDENCE = (
    "On the view PATCH route a code:0 proves acceptance and nothing else: an unrecognised key "
    "INSIDE property.hierarchy_config answered code:0 and changed nothing at all. So every "
    "claim this library makes about hierarchy_config is an EFFECT assertion — the read-back "
    "MOVED from one field id to another under a second patch — never a success code."
)

HIERARCHY_FIELD_MUST_BE_A_LINK = (
    "the field must be single_link or duplex_link"
)

UNKNOWN_FIELD_ID_IS_RELAYED = (
    "A field id this library cannot find in the field list it was handed is NOT refused "
    "locally. Lark answers 1254044 Field id is not found for an id that does not exist, and "
    "that answer is relayed typed — because a field list is a read of a moment and an id "
    "missing from it is not proof the id does not exist. The contrast with the local refusal "
    "above is deliberate: this library refuses what it can KNOW (the server itself refuses a "
    "non-link target, so predicting it costs the caller nothing) and never pretends to know "
    "the rest."
)

HIERARCHY_LIVES_ON_THE_VIEW = (
    "THE HIERARCHY FACT LIVES ON THE VIEW, NOT THE TABLE. GET .../fields returns a self-link "
    "column as an ordinary link column — nothing in the schema says 'this is the hierarchy "
    "field'. Only a view's property.hierarchy_config names it, and a view built in the product "
    "returns property: null until something sets it. So a surface that claims to read 'the' "
    "hierarchy must say WHICH VIEW it read that from, or be told the column by name."
)

A_PRODUCT_BUILT_VIEW_READS_NULL = (
    "A view nobody has configured returns property: null entirely — not "
    "{'hierarchy_config': null} — through both the view listing and the single-view read. "
    "That null means NOT CONFIGURED, and it is honest rather than a redaction: a configured "
    "view reads back populated."
)

PARENT_NEVER_NESTING = (
    "THE READ IS A PARENT POINTER, NEVER NESTING. No Lark read route returns children nested "
    "inside a parent: every route returns a flat row list, and the relationship is the "
    "per-row link cell. This accessor exposes the pointer as a pointer and adds an ORDER and "
    "a DEPTH computed from those pointers; it never implies that some endpoint handed back a "
    "nested structure, because none does."
)

TREE_ORDER_IS_RECONSTRUCTED_CLIENT_SIDE = (
    "DEPTH-FIRST ORDER IS RECONSTRUCTED CLIENT-SIDE, FROM THE POINTERS. The tree order the "
    "server offers exists only on the legacy GET .../records?view_id= list — a different "
    "endpoint, which needs a configured view, which carries a different link-cell wire shape "
    "([{'record_ids': [...], 'text': ...}] against records/search's {'link_record_ids': "
    "[...]}), and which sorts a cycle member silently last instead of naming it. Rebuilding "
    "the order here costs no extra API call, no second endpoint and no second cell dialect, "
    "works with no view configured, and is the only route that can report a cycle as a cycle."
)

SEARCH_IS_HIERARCHY_BLIND = (
    "POST .../records/search — the endpoint this library's Base read uses — IS BLIND TO THE "
    "HIERARCHY, and that is disclosed rather than worked around. Its result is byte-identical "
    "before and after a view's hierarchy_config is set, and identical with view_id and "
    "without it. It has no hierarchy knob: with_hierarchy: true and hierarchy: true "
    "each produced a digest identical to the deliberately bogus control key, so both are "
    "ignored rather than honoured. This library never sends either knob, because sending a "
    "key the server throws away would look like a feature in the code and be nothing on the "
    "wire."
)

A_VIEW_ID_HERE_IS_A_CITATION = (
    "A view_id accepted by this accessor is a CITATION for where the hierarchy field's name "
    "was read from — never a projection. read_base still takes no view_id and still will not: "
    "a view is not a projection, it does not narrow the columns a read returns, and nothing "
    "here changes that. What a view answers here is one question only: which column is the "
    "hierarchy?"
)


# --------------------------------------------------------------------------- #
# The two hazards — accepted by Lark, disclosed by this library, refused by     #
# neither                                                                       #
# --------------------------------------------------------------------------- #

TWO_PARENTS_ARE_ACCEPTED = (
    "A ROW CAN HAVE TWO PARENTS. A self-link column's property.multiple defaults to true, so "
    "writing two record ids into one parent cell answers code:0 and reads back with both — a "
    "shape the product's own row tree cannot draw. Both ids survive into everything this "
    "module produces; silently picking one would be a quiet lie about the data."
)

A_ROW_MAY_BE_ITS_OWN_PARENT = (
    "A ROW CAN BE ITS OWN PARENT. Setting a row's parent cell to its own record id answers "
    "code:0 and reads back holding it — the server enforces no acyclicity — and in the "
    "server's own tree-ordered read that row simply sorted last, unnamed. Longer cycles are "
    "the same story. This module names them instead: every row on a cycle is typed as such "
    "and the traversal terminates."
)

HAZARDS_ARE_DISCLOSED_NOT_REFUSED = (
    "THE LIBRARY NEVER INVENTS A VALIDATION LARK DOES NOT PERFORM. A parent write that would "
    "create a cycle or a second parent is NOT refused here: Lark accepts both at code:0, and "
    "a client-side refusal would make this library the only thing standing between a caller "
    "and a structure their own tenant permits. What happens instead is disclosure BEFORE the "
    "act, the way a destructive schema plan enumerates its loss first: the preview names the "
    "rows involved and what the resulting structure will be, and the caller decides."
)

DISCLOSURE_IS_FREE = (
    "The hazard check reads ONLY the pointer graph already in hand — it must not buy a new "
    "API call to go looking. Where no graph was supplied it says, in words, that it DID NOT "
    "CHECK. A missing disclosure is never a guarantee that there is no cycle."
)

HIERARCHY_WAS_NOT_CHECKED = (
    "This parent write DID NOT CHECK for a cycle or a second parent: no hierarchy was "
    "supplied to check against, and this disclosure will not buy an API call to go looking. "
    "The absence of a hazard here is NOT A GUARANTEE that there is none — it means nobody "
    "looked. Read the table's hierarchy first and pass it in to get a real answer."
)

CYCLE_WHAT = (
    "This write closes a cycle: following the parent pointers from this row leads back to "
    "this row. Lark accepts it at code:0 and its own tree-ordered read will simply sort the "
    "row last. Nothing is refused; the structure will not be a tree."
)

SECOND_PARENT_WHAT = (
    "This write gives the row more than one parent. Lark accepts it at code:0 because the "
    "self-link column's property.multiple defaults to true. Nothing is refused; the structure "
    "will be a graph rather than a tree, and every reader of it has to decide which parent "
    "it means."
)


# --------------------------------------------------------------------------- #
# Placement — a statement about the ROW's position, never about liveness        #
# --------------------------------------------------------------------------- #

#: The row has no parent pointer at all.
PLACEMENT_ROOT = "root"
#: The row's parent pointer names a row that is present in what was read.
PLACEMENT_CHILD = "child"
#: The row lies on a cycle — its own ancestry leads back to it.
PLACEMENT_CYCLE = "cycle"
#: The row has a parent pointer and that parent is not among the rows that were read.
PLACEMENT_DETACHED = "detached"

#: Every placement, exhaustively. Four, and each says a different thing.
PLACEMENTS: Tuple[str, ...] = (
    PLACEMENT_ROOT, PLACEMENT_CHILD, PLACEMENT_CYCLE, PLACEMENT_DETACHED,
)

PLACEMENT_MEANINGS = {
    PLACEMENT_ROOT: (
        "This row has no parent pointer at all, so it is a top of the tree."
    ),
    PLACEMENT_CHILD: (
        "This row's parent pointer names a row that is present in what was read, so it hangs "
        "under that row."
    ),
    PLACEMENT_CYCLE: (
        "This row lies on a cycle: following its parent pointers leads back to it. It is "
        "reported here rather than placed, the traversal terminated, and nothing was repaired."
    ),
    PLACEMENT_DETACHED: (
        "This row carries a parent pointer whose target is not among the rows that were read. "
        "It is NOT a root and it was not dropped; whether that parent record still exists is "
        "a separate question, answered in the pointer's own state."
    ),
}

PLACEMENT_IS_NOT_A_LIVENESS_CLAIM = (
    "A placement says where a row sits in what was read. It is NOT a claim about whether a "
    "parent record still exists — that question is answered per pointer, in the vocabulary "
    "link resolution already established (resolved / dangling / the third state that claims "
    "nothing in either direction), and the two are kept apart deliberately so neither can be "
    "read as the other."
)

#: How the accessor learned which column carries the hierarchy.
SOURCE_NAMED_BY_CALLER = "named-by-caller"
SOURCE_VIEW_HIERARCHY_CONFIG = "view-hierarchy-config"

NEVER_GUESSES_A_COLUMN = (
    "This accessor never guesses a column. A table can hold several self-referencing link "
    "columns and only a view says which one is the hierarchy, so the field is either NAMED by "
    "the caller or read from a NAMED view's property.hierarchy_config. With neither, the "
    "answer is 'not configured' rather than a tree built on a hunch."
)


# --------------------------------------------------------------------------- #
# The view parameter — and the one refusal the server itself makes              #
# --------------------------------------------------------------------------- #

_HIERARCHY_TOKEN = object()


class HierarchyConfig(dict):
    """The one value the view route's ``property.hierarchy_config`` accepts.

    Token-guarded, exactly like :class:`~larkdocio.base.view_filters.ViewFilterInfo` on the
    same endpoint and for the same reason: the only way to hold one is to have gone through
    :func:`hierarchy_config`, which is where the local refusal lives. A bare field id string —
    or a plain ``dict`` that happens to look right — is a :class:`TypeError` at the route's own
    signature, before any call.

    It **is** a ``dict`` (``{"field_id": …}``, the wire body and nothing more), so a plan
    carrying one serialises to JSON with no special case. What it knows *about* the check —
    ``checked``, ``self_referencing``, ``uncaptured_shape`` — rides as attributes rather than
    wire keys, because none of it belongs in the request.
    """

    def __init__(self, body=None, *, checked: bool = False,
                 self_referencing: Optional[bool] = None,
                 uncaptured_shape: Optional[str] = None, _token: object = None):
        if _token is not _HIERARCHY_TOKEN:
            raise TypeError(
                "HierarchyConfig values are produced only by "
                "larkdocio.base.hierarchy.hierarchy_config(field_id, fields=…) — the one place "
                "a non-link target is refused locally, in the server's own words. A hand-built "
                "one would carry the field id past that refusal.")
        super().__init__(body or {})
        self.checked = checked
        self.self_referencing = self_referencing
        self.uncaptured_shape = uncaptured_shape

    @property
    def field_id(self) -> str:
        return self["field_id"]

    def to_dict(self) -> dict:
        """What goes on the wire: one key, one field id."""
        return {"field_id": self["field_id"]}

    def __repr__(self):  # pragma: no cover - a debugging convenience
        return f"HierarchyConfig({dict(self)!r}, checked={self.checked})"


def _field_type(field):
    return getattr(field, "type", None)


def _field_property(field) -> Mapping:
    """A field's ``property`` as a mapping, read **by name** through the one shared step
    (:mod:`larkdocio.base._typed`) so the reading does not depend on which door it came through.

    **One name, deliberately.** ``table_id`` is the only key anything here reads, and the list
    stays local for that reason: a shared default would hand this reader keys it has no use for
    the first time another reader gained one. The consequence is on the typed door only, and it
    is the pre-existing shape LD-311 pinned rather than a new one — a typed object narrows to
    that single key, a mapping is handed back whole — which is invisible in every answer because
    ``table_id`` is all that is ever asked for.
    """
    prop = getattr(field, "property", None)
    if isinstance(prop, Mapping):
        return prop
    if prop is None:
        return {}
    return _by_name(prop, ("table_id",))


def hierarchy_config(field_id: str, *, fields: Sequence,
                     table_id: Optional[str] = None) -> HierarchyConfig:
    """The typed ``hierarchy_config`` value, with the server's own refusal made **local**.

    ``fields`` is the table's field list the caller has **already read** — naming a field id
    means having read one — so the one refusal the server makes is predicted here, before any
    call, in the server's own words. Two deliberate non-refusals:

    * a field id **absent** from that list is passed through (:data:`UNKNOWN_FIELD_ID_IS_RELAYED`);
    * a link pointing at **another** table is disclosed as an uncaptured shape and sent, because
      the server's message names the two field *kinds* and says nothing about the target.
    """
    from larkdocio.base.schema_client import BaseSchemaRefusal

    match = None
    for field in fields or ():
        if getattr(field, "field_id", None) == field_id:
            match = field
            break
    if match is None:
        return HierarchyConfig({"field_id": field_id}, checked=False,
                               _token=_HIERARCHY_TOKEN)
    if _field_type(match) not in LINK_TYPES:
        raise BaseSchemaRefusal(
            f"a view's hierarchy_config can only name a link column: Lark answers "
            f"`1254001 The request body is wrong` for anything else, with its own message "
            f"\"Invalid request parameter: 'property.hierarchy_config.field_id'. Correct "
            f"format : {HIERARCHY_FIELD_MUST_BE_A_LINK}.\" — and "
            f"{getattr(match, 'field_name', field_id)!r} is a "
            f"{getattr(match, 'ui_type', None) or 'non-link'} column "
            f"(type {_field_type(match)}). That refusal is met here rather than after a round "
            f"trip. Nothing was sent.")
    target = _field_property(match).get("table_id")
    self_referencing = None if table_id is None or target is None else target == table_id
    uncaptured = None
    if self_referencing is False:
        uncaptured = (
            f"This hierarchy_config names a link column that points at another table "
            f"({target!r}), not at {table_id!r}. Every capture behind this surface used a "
            f"SELF-referencing link, so what the server does with a cross-table link as a "
            f"hierarchy field is uncaptured — no capture shows it. It is DISCLOSED rather "
            f"than refused: the server's own message constrains the field KIND and says "
            f"nothing about its target, and refusing here would be inventing a validation "
            f"Lark does not perform.")
    return HierarchyConfig({"field_id": field_id}, checked=True,
                           self_referencing=self_referencing, uncaptured_shape=uncaptured,
                           _token=_HIERARCHY_TOKEN)


def hierarchy_field_id(view) -> Optional[str]:
    """An **already-read** view → the field id its ``hierarchy_config`` names, or ``None``.

    Costs no call: the view object is the caller's. ``None`` means *not configured* — which is
    what every product-built view returns (:data:`A_PRODUCT_BUILT_VIEW_READS_NULL`).
    """
    prop = getattr(view, "property", None)
    if prop is None:
        return None
    config = (prop.get("hierarchy_config") if isinstance(prop, Mapping)
              else getattr(prop, "hierarchy_config", None))
    if config is None:
        return None
    field_id = (config.get("field_id") if isinstance(config, Mapping)
                else getattr(config, "field_id", None))
    return field_id or None


# --------------------------------------------------------------------------- #
# The read                                                                      #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HierarchyRow:
    """One row's position in the tree — a pointer read, never a nesting."""

    record_id: str
    parent_ids: Tuple[str, ...]
    parent_states: Tuple[str, ...]
    placement: str
    depth: int
    note: str

    @property
    def multi_parent(self) -> bool:
        return len(self.parent_ids) > 1


@dataclass(frozen=True)
class Hierarchy:
    """One table's row tree, as far as the pointers in hand can honestly say.

    ``rows`` is in **depth-first order**, reconstructed client-side; ``cycles`` names every
    cycle found; ``multi_parent`` names every row with more than one parent. When ``configured``
    is ``False`` the tree is empty **and** :attr:`not_configured_reason` says why — an empty
    tree presented as a real one is the specific lie this class refuses to tell.
    """

    configured: bool
    field_name: Optional[str] = None
    field_id: Optional[str] = None
    source: Optional[str] = None
    source_detail: str = ""
    rows: Tuple[HierarchyRow, ...] = ()
    cycles: Tuple[Tuple[str, ...], ...] = ()
    multi_parent: Tuple[str, ...] = ()
    not_configured_reason: str = ""

    def row(self, record_id: str) -> Optional[HierarchyRow]:
        for row in self.rows:
            if row.record_id == record_id:
                return row
        return None

    @property
    def roots(self) -> Tuple[HierarchyRow, ...]:
        return tuple(row for row in self.rows if row.placement == PLACEMENT_ROOT)

    @property
    def disclosure(self) -> str:
        """What this read found, and what it deliberately does not claim — one sentence."""
        if not self.configured:
            return f"No row hierarchy was read: not configured. {self.not_configured_reason}"
        detached = sum(1 for row in self.rows if row.placement == PLACEMENT_DETACHED)
        return (
            f"Row hierarchy read from {self.source_detail}: {len(self.rows)} row(s), "
            f"{len(self.roots)} root(s), {len(self.cycles)} cycle(s), "
            f"{len(self.multi_parent)} row(s) with more than one parent, "
            f"{detached} row(s) whose parent is not among the rows read. "
            f"{PARENT_NEVER_NESTING}"
        )


def _record_id(record) -> str:
    if isinstance(record, Mapping):
        return record.get("record_id") or ""
    return getattr(record, "record_id", "") or ""


def _record_values(record) -> Mapping:
    if isinstance(record, Mapping):
        return record.get("fields") or {}
    return getattr(record, "fields", None) or {}


def _parent_ids(value) -> Tuple[str, ...]:
    """The parent ids in a ``records/search`` link cell, and nothing else.

    Only the one wire shape this library reads is accepted; the legacy list's shape is a
    different dialect and is deliberately not understood here
    (:data:`TREE_ORDER_IS_RECONSTRUCTED_CLIENT_SIDE`).
    """
    if isinstance(value, Mapping):
        ids = value.get("link_record_ids")
    elif isinstance(value, (list, tuple)):
        ids = value
    elif isinstance(value, str):
        ids = [value]
    else:
        ids = None
    if not ids or not isinstance(ids, (list, tuple)):
        return ()
    return tuple(str(i) for i in ids if i)


def _field_by(fields, *, field_name=None, field_id=None):
    for field in fields or ():
        if field_name is not None and getattr(field, "field_name", None) == field_name:
            return field
        if field_id is not None and getattr(field, "field_id", None) == field_id:
            return field
    return None


def _strongly_connected(parents: Mapping[str, Tuple[str, ...]]) -> Tuple[frozenset, ...]:
    """Tarjan's SCCs over the parent edges — **iterative**, so depth costs stack space nothing.

    A row on a cycle is exactly a row in a component of size > 1, or one whose parent set
    contains itself. Computing it properly (rather than by walking one parent chain) is what
    makes the cycle report honest for a row with two parents.
    """
    index = {}
    low = {}
    on_stack = set()
    stack = []
    components = []
    counter = 0
    for start in parents:
        if start in index:
            continue
        work = [(start, 0)]
        while work:
            node, child_index = work[-1]
            if child_index == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            edges = parents.get(node, ())
            while child_index < len(edges):
                nxt = edges[child_index]
                child_index += 1
                if nxt not in parents:
                    continue
                if nxt not in index:
                    work[-1] = (node, child_index)
                    work.append((nxt, 0))
                    recursed = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if recursed:
                continue
            work[-1] = (node, child_index)
            work.pop()
            if low[node] == index[node]:
                component = set()
                while True:
                    popped = stack.pop()
                    on_stack.discard(popped)
                    component.add(popped)
                    if popped == node:
                        break
                components.append(frozenset(component))
            if work:
                parent_node, _ = work[-1]
                low[parent_node] = min(low[parent_node], low[node])
    return tuple(components)


def _cycle_walk(start: str, parents: Mapping[str, Tuple[str, ...]],
                members: frozenset) -> Tuple[str, ...]:
    """One cycle, written down in the order its parent pointers actually walk."""
    walk = [start]
    seen = {start}
    node = start
    while True:
        nxt = next((p for p in parents.get(node, ()) if p in members), None)
        if nxt is None or nxt in seen:
            return tuple(walk)
        walk.append(nxt)
        seen.add(nxt)
        node = nxt


def read_hierarchy(fields: Sequence, records: Sequence, *,
                   field_name: Optional[str] = None,
                   field_id: Optional[str] = None,
                   view=None,
                   links=None) -> Hierarchy:
    """Turn a self-link column into parent/child structure — **opt-in, pure, zero calls**.

    ``fields`` and ``records`` are what a Base read already holds for one table. The hierarchy
    column is either **named** (``field_name`` / ``field_id``) or read from an **already-read**
    ``view``'s ``property.hierarchy_config``; it is never guessed
    (:data:`NEVER_GUESSES_A_COLUMN`). ``links`` is an optional
    :class:`~larkdocio.base.link_resolution.LinkResolution` the caller already computed: where
    it has already established that a parent record is gone, that answer is carried through
    rather than re-derived.

    What comes back is a :class:`Hierarchy` in **depth-first order**, with every hazard named:
    a cycle is typed and terminated, both parents of a two-parent row survive, and a parent
    that is not among the rows read is *detached* rather than promoted to a root.
    """
    source = None
    detail = ""
    if view is not None and field_name is None and field_id is None:
        source = SOURCE_VIEW_HIERARCHY_CONFIG
        view_id = getattr(view, "view_id", None) or "?"
        field_id = hierarchy_field_id(view)
        if field_id is None:
            return Hierarchy(configured=False, source=source, not_configured_reason=(
                f"view {view_id} names no hierarchy field: its "
                f"property.hierarchy_config is not set. {A_PRODUCT_BUILT_VIEW_READS_NULL}"))
        detail = f"view {view_id}'s property.hierarchy_config (field id {field_id})"
    elif field_name is not None or field_id is not None:
        source = SOURCE_NAMED_BY_CALLER
        detail = f"the column named by the caller ({field_name or field_id})"
    else:
        return Hierarchy(configured=False, not_configured_reason=NEVER_GUESSES_A_COLUMN)

    spec = _field_by(fields, field_name=field_name, field_id=field_id)
    if spec is None:
        return Hierarchy(configured=False, source=source, source_detail=detail,
                         not_configured_reason=(
                             f"no field named {(field_name or field_id)!r} is in this table's "
                             f"schema, so there is no hierarchy column to read."))
    if _field_type(spec) not in LINK_TYPES:
        return Hierarchy(configured=False, source=source, source_detail=detail,
                         not_configured_reason=(
                             f"{getattr(spec, 'field_name', field_id)!r} is not a link column "
                             f"(type {_field_type(spec)}), and a row hierarchy is only ever a "
                             f"link column. {HIERARCHY_IS_A_SELF_LINK_FIELD}"))

    name = getattr(spec, "field_name", "") or ""
    order = []
    parents = {}
    for record in records or ():
        record_id = _record_id(record)
        if not record_id:
            continue
        order.append(record_id)
        parents[record_id] = _parent_ids(_record_values(record).get(name))

    present = set(parents)
    components = _strongly_connected(parents)
    in_cycle = set()
    cycles = []
    for record_id in order:
        if record_id in in_cycle:
            continue
        for component in components:
            if record_id not in component:
                continue
            looped = len(component) > 1 or record_id in parents.get(record_id, ())
            if looped:
                in_cycle |= set(component)
                cycles.append(_cycle_walk(record_id, parents, component))
            break

    resolution = links
    children = {}
    placements = {}
    states = {}
    for record_id in order:
        pointer_states = []
        for parent in parents[record_id]:
            if parent in present:
                pointer_states.append(LINK_RESOLVED)
            elif resolution is not None and getattr(
                    resolution.record_for(_field_property(spec).get("table_id") or "", parent),
                    "state", None) == LINK_DANGLING:
                pointer_states.append(LINK_DANGLING)
            else:
                pointer_states.append(LINK_UNRESOLVABLE)
        states[record_id] = tuple(pointer_states)
        anchor = next((p for p in parents[record_id] if p in present), None)
        if record_id in in_cycle:
            placements[record_id] = PLACEMENT_CYCLE
        elif not parents[record_id]:
            placements[record_id] = PLACEMENT_ROOT
        elif anchor is None:
            placements[record_id] = PLACEMENT_DETACHED
        else:
            placements[record_id] = PLACEMENT_CHILD
        if anchor is not None:
            children.setdefault(anchor, []).append(record_id)

    rows = []
    visited = set()

    def _emit(start):
        stack = [(start, 0)]
        while stack:
            record_id, depth = stack.pop()
            if record_id in visited:
                continue
            visited.add(record_id)
            pointer_states = states[record_id]
            note = PLACEMENT_MEANINGS[placements[record_id]]
            for state in dict.fromkeys(s for s in pointer_states if s != LINK_RESOLVED):
                note = f"{note} {POINTER_STATE_MEANINGS[state]}"
            rows.append(HierarchyRow(
                record_id=record_id, parent_ids=parents[record_id],
                parent_states=pointer_states, placement=placements[record_id],
                depth=depth, note=note))
            for child in reversed(children.get(record_id, ())):
                if child not in visited:
                    stack.append((child, depth + 1))

    for record_id in order:
        if placements[record_id] == PLACEMENT_ROOT:
            _emit(record_id)
    for record_id in order:
        if placements[record_id] == PLACEMENT_DETACHED:
            _emit(record_id)
    for record_id in order:
        _emit(record_id)

    return Hierarchy(
        configured=True, field_name=name, field_id=getattr(spec, "field_id", None) or None,
        source=source, source_detail=detail, rows=tuple(rows), cycles=tuple(cycles),
        multi_parent=tuple(r for r in order if len(parents[r]) > 1),
    )


def render_hierarchy(tree: Hierarchy) -> str:
    """The tree as indented text — one line per row, **parent ids and all**.

    Every parent id survives into this rendering, which is the point: silently rendering one
    parent of a two-parent row is the specific defect this surface exists to prevent.
    """
    if not tree.configured:
        return f"[no row hierarchy: not configured — {tree.not_configured_reason}]"
    lines = []
    for row in tree.rows:
        marks = []
        if row.placement != PLACEMENT_CHILD:
            marks.append(row.placement)
        if row.parent_ids:
            marks.append("parents: " + ", ".join(row.parent_ids))
        suffix = f"  [{'; '.join(marks)}]" if marks else ""
        lines.append(f"{'  ' * row.depth}- {row.record_id}{suffix}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The write side — disclosure before the act, and never a refusal               #
# --------------------------------------------------------------------------- #

def _cycle_path(child_id: str, parent_ids: Sequence[str],
                tree: Hierarchy) -> Optional[Tuple[str, ...]]:
    """The path back to ``child_id`` this write would close, or ``None``.

    Depth-first over **every** parent edge already in the tree, in encounter order, so a row
    with two parents cannot hide a cycle behind its second pointer. Bounded: each row is
    entered once.
    """
    if child_id in parent_ids:
        return (child_id,)
    by_id = {row.record_id: row for row in tree.rows}
    stack = [(parent, (child_id, parent)) for parent in reversed(list(parent_ids))]
    seen = set()
    while stack:
        node, path = stack.pop()
        if node == child_id:
            return path[:-1]
        if node in seen:
            continue
        seen.add(node)
        row = by_id.get(node)
        if row is None:
            continue
        for parent in reversed(row.parent_ids):
            stack.append((parent, path + (parent,)))
    return None


def parent_write_disclosure(*, child_id: str, parent_ids: Sequence[str],
                            hierarchy: Optional[Hierarchy] = None) -> dict:
    """What one parent write would produce — **disclosed, never refused**.

    Follows the destructive-plan precedent: state the consequence *before* the act. Two
    consequences are named — a **cycle** and a **second parent** — because Lark accepts both at
    ``code:0`` and no reader of the result can tell they were intended.

    ``hierarchy`` is the pointer graph **already in hand**. Without it the answer is an honest
    *did not check* (:data:`HIERARCHY_WAS_NOT_CHECKED`): this function never buys an API call
    (:data:`DISCLOSURE_IS_FREE`).
    """
    ids = tuple(str(i) for i in (parent_ids or ()) if i)
    second = None
    if len(ids) > 1:
        second = {"what": SECOND_PARENT_WHAT, "parent_ids": ids,
                  "evidence": HIERARCHY_EVIDENCE}
    if hierarchy is None or not hierarchy.configured:
        return {"record_id": child_id, "parent_ids": ids, "refused": False, "checked": False,
                "cycle": None, "second_parent": second, "note": HIERARCHY_WAS_NOT_CHECKED,
                "evidence": HIERARCHY_EVIDENCE}
    path = _cycle_path(child_id, ids, hierarchy)
    cycle = None
    if path is not None:
        cycle = {"what": CYCLE_WHAT, "rows": path, "evidence": HIERARCHY_EVIDENCE}
    return {"record_id": child_id, "parent_ids": ids, "refused": False, "checked": True,
            "cycle": cycle, "second_parent": second,
            "note": HAZARDS_ARE_DISCLOSED_NOT_REFUSED, "evidence": HIERARCHY_EVIDENCE}


def hierarchy_write_preview(draft, *, hierarchy: Optional[Hierarchy] = None,
                            field_name: Optional[str] = None) -> dict:
    """Every parent write held on a draft, disclosed **before** the plan is built.

    ``draft`` is the value :func:`larkdocio.base.apply.dry_run` itself takes — its pending
    edits and additions carry the values the caller wrote, before any encoding — so this
    preview is over the same intent the plan will act on, and it costs **zero calls**. The
    shape is the cross-table loss preview's: a scan already in hand, a disclosure out.
    """
    name = field_name or (hierarchy.field_name if hierarchy is not None else None)
    entries = []
    pending = list((draft.pending_edits or {}).items()) + list(draft.pending_additions or ())
    for record_id, cells in pending:
        if name is None or name not in (cells or {}):
            continue
        entries.append(parent_write_disclosure(
            child_id=record_id, parent_ids=_parent_ids(cells[name]), hierarchy=hierarchy))
    return {
        "field_name": name,
        "checked": bool(hierarchy is not None and hierarchy.configured),
        "entries": tuple(entries),
        "what": HAZARDS_ARE_DISCLOSED_NOT_REFUSED,
        "free": DISCLOSURE_IS_FREE,
        "evidence": HIERARCHY_EVIDENCE,
    }


__all__ = [
    "A_PRODUCT_BUILT_VIEW_READS_NULL",
    "A_ROW_MAY_BE_ITS_OWN_PARENT",
    "A_VIEW_ID_HERE_IS_A_CITATION",
    "CODE_ZERO_IS_NOT_EVIDENCE",
    "CYCLE_WHAT",
    "DISCLOSURE_IS_FREE",
    "HAZARDS_ARE_DISCLOSED_NOT_REFUSED",
    "HIERARCHY_EVIDENCE",
    "HIERARCHY_FIELD_MUST_BE_A_LINK",
    "HIERARCHY_IS_A_SELF_LINK_FIELD",
    "HIERARCHY_LIVES_ON_THE_VIEW",
    "HIERARCHY_WAS_NOT_CHECKED",
    "Hierarchy",
    "HierarchyConfig",
    "HierarchyRow",
    "LINK_TYPES",
    "NEVER_GUESSES_A_COLUMN",
    "NO_BODY_KEY_MAKES_A_CHILD",
    "PARENT_EDGE_IS_A_LINK_VALUE",
    "PARENT_NEVER_NESTING",
    "PARENT_POINTER_STATES",
    "PLACEMENTS",
    "PLACEMENT_CHILD",
    "PLACEMENT_CYCLE",
    "PLACEMENT_DETACHED",
    "PLACEMENT_IS_NOT_A_LIVENESS_CLAIM",
    "PLACEMENT_MEANINGS",
    "PLACEMENT_ROOT",
    "REFUTED_PARENT_BODY_KEYS",
    "SEARCH_IS_HIERARCHY_BLIND",
    "SECOND_PARENT_WHAT",
    "SOURCE_NAMED_BY_CALLER",
    "SOURCE_VIEW_HIERARCHY_CONFIG",
    "TREE_ORDER_IS_RECONSTRUCTED_CLIENT_SIDE",
    "TWO_PARENTS_ARE_ACCEPTED",
    "UNKNOWN_FIELD_ID_IS_RELAYED",
    "hierarchy_config",
    "hierarchy_field_id",
    "hierarchy_write_preview",
    "parent_write_disclosure",
    "read_hierarchy",
    "render_hierarchy",
]
