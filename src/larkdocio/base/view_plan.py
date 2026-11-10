"""larkdocio.base.view_plan — the four typed VIEW requests a schema plan is made of.

The app-and-table family authors its request constructors in
:mod:`larkdocio.base.schema_plan`; the view family authors its own here, over the **same**
:class:`~larkdocio.base.schema_plan.SchemaRequest` value. One plan type, one gate, one
apply-log — and one more family that is a new file rather than an edit to a shared body.

**Every refusal this module makes costs zero API calls.** The ``view_type`` allow-list is
checked at request-construction time, so a ``calendar`` view is refused before the previewer
even runs — and ``form`` is refused here too, by policy, in register row 17's own words.

**THREE PROPERTY KEYS, AND NO FOURTH.** :func:`set_view_filter` takes a
:class:`~larkdocio.base.view_filters.ViewFilterInfo`, :func:`set_view_hierarchy` takes a
:class:`~larkdocio.base.hierarchy.HierarchyConfig` — each from its own single producer — and
:func:`set_view_hidden_fields` / :func:`clear_view_hidden_fields` take a list of field ids.
There is still **no grouping and no view-level sort parameter** in this module, and a keyword
argument offering one is a ``TypeError`` from Python itself, which is the strongest form the "no
knob" rule can take. ``hierarchy_config`` left that list when its effect became measured and
read back; ``hidden_fields`` left it the same way and for the same reason — **the rule
did not change, its premise was refuted.** Grouping, the saved view-level sort and a gantt
view's date binding have **not** left it: grouping and all eight sort spellings answer ``code:0``
and store nothing against an invented-key control, in the same run where ``filter_info`` stored,
and the gantt binding has no route at all.
"""
from typing import Sequence

from larkdocio.base.hierarchy import HierarchyConfig
from larkdocio.base.schema_client import BaseSchemaRefusal
from larkdocio.base.schema_ops_views import (
    FORM_IS_REFUSED_BY_POLICY,
    NO_VIEW_ANCHOR,
    SCOPE,
    SERVER_REFUSED_VIEW_TYPES,
    SERVER_VIEW_TYPE_ENUM,
    VIEW_TYPES,
)
from larkdocio.base.schema_plan import SchemaRequest
from larkdocio.base.view_client import (
    HIDDEN_FIELDS_EMPTY_LIST_CLEARS,
    HIDDEN_FIELDS_PRIMARY_IS_REFUSED,
    HIDDEN_FIELDS_UNKNOWN_ID_IS_RELAYED,
    check_hidden_fields,
)
from larkdocio.base.view_filters import VIEW_ROUTE_REQUIRES_FIELD_ID, ViewFilterInfo


def _traits(read_cost: int) -> dict:
    """What this family knows about its own ops that the engine does not.

    Declared per request — the engine's :data:`~larkdocio.base.schema_apply.DECLARABLE_TRAITS`
    seam — rather than branched on anywhere central. ``revision_guard`` is left unset on
    purpose: a view write has **no** anchor at all, and :data:`NO_VIEW_ANCHOR` is the entry's
    own statement of that absence, deliberately not the app-scoped one.
    """
    return {"scope": SCOPE,
            "revision_guard_disclosure": NO_VIEW_ANCHOR,
            "read_cost": read_cost}


def check_view_type(view_type: str) -> str:
    """The allow-list, enforced **locally, with zero transport calls**.

    Three refusals, three different reasons, and each says which kind it is: a type the
    **server** rejects (quoting the server's own accepted enum), a type nothing has ever seen,
    and ``form`` — which the server accepts and **this library** declines.
    """
    if view_type in VIEW_TYPES:
        return view_type
    if view_type == "form":
        raise BaseSchemaRefusal(FORM_IS_REFUSED_BY_POLICY + " Nothing was sent.")
    if view_type in SERVER_REFUSED_VIEW_TYPES:
        raise BaseSchemaRefusal(
            f"Lark refuses `view_type: {view_type!r}` itself, with `99992402 field validation "
            f"failed` and its own accepted list in the body: \"{SERVER_VIEW_TYPE_ENUM}\". That "
            "refusal is met here rather than after a round trip. Nothing was sent.")
    raise BaseSchemaRefusal(
        f"`view_type: {view_type!r}` is not a view type this library creates. The types it "
        f"creates — each proven code:0 against a live Base — are: {', '.join(VIEW_TYPES)}. "
        f"Lark's own accepted list is \"{SERVER_VIEW_TYPE_ENUM}\"; `form` is excluded here by "
        "policy, not by Lark. Nothing was sent.")


def create_view(app_token: str, table_id: str, view_name: str,
                view_type: str = "grid") -> SchemaRequest:
    """Create a ``view_type`` view named ``view_name`` on the table ``table_id``."""
    check_view_type(view_type)
    return SchemaRequest(
        op="create_view", app_token=app_token, table_id=table_id,
        arguments={"app_token": app_token, "table_id": table_id, "view_name": view_name,
                   "view_type": view_type},
        describe=f"create a {view_type} view named {view_name!r} in table {table_id}",
        traits=_traits(1))


def rename_view(app_token: str, table_id: str, view_id: str, view_name: str) -> SchemaRequest:
    """Rename the view ``view_id`` to ``view_name``."""
    return SchemaRequest(
        op="update_view", app_token=app_token, table_id=table_id,
        arguments={"app_token": app_token, "table_id": table_id, "view_id": view_id,
                   "view_name": view_name},
        describe=f"rename view {view_id} to {view_name!r}",
        traits=_traits(2))


def set_view_filter(app_token: str, table_id: str, view_id: str,
                    filter_info: ViewFilterInfo) -> SchemaRequest:
    """Set the view ``view_id``'s **persistent filter** — the rows a human sees when they open
    it.

    ``filter_info`` comes from :func:`larkdocio.base.view_filters.view_filter`, which is the
    only producer of the type this signature accepts. A ``records/search`` filter is a
    different language and cannot be named here.
    """
    if not isinstance(filter_info, ViewFilterInfo):
        raise TypeError(
            "set_view_filter takes a ViewFilterInfo — the value "
            "larkdocio.base.view_filters.view_filter(...) produces — and nothing else; got "
            f"{type(filter_info).__name__}. {VIEW_ROUTE_REQUIRES_FIELD_ID}")
    return SchemaRequest(
        op="update_view", app_token=app_token, table_id=table_id,
        arguments={"app_token": app_token, "table_id": table_id, "view_id": view_id,
                   "filter_info": filter_info},
        describe=f"set the persistent filter on view {view_id}",
        traits=_traits(2))


def set_view_hierarchy(app_token: str, table_id: str, view_id: str,
                       hierarchy_config: HierarchyConfig) -> SchemaRequest:
    """Name the view ``view_id``'s **hierarchy field** — the column its row tree hangs on.

    ``hierarchy_config`` comes from :func:`larkdocio.base.hierarchy.hierarchy_config`, the only
    producer of the type this signature accepts, and the place a **non-link** target is refused
    locally in the server's own words (``1254001`` *"the field must be single_link or
    duplex_link"``). A bare field id string is a :class:`TypeError` here, before any call.

    **What this changes is an ORDERING on one legacy endpoint, and nothing else.** The
    relationship itself is the link-cell value and is readable with or without this; setting it
    does not alter ``records/search`` in any direction. See
    :data:`larkdocio.base.hierarchy.SEARCH_IS_HIERARCHY_BLIND`.
    """
    if not isinstance(hierarchy_config, HierarchyConfig):
        raise TypeError(
            "set_view_hierarchy takes a HierarchyConfig — the value "
            "larkdocio.base.hierarchy.hierarchy_config(field_id, fields=…) produces — and "
            f"nothing else; got {type(hierarchy_config).__name__}. That producer is where the "
            "local refusal for a non-link target lives.")
    return SchemaRequest(
        op="update_view", app_token=app_token, table_id=table_id,
        arguments={"app_token": app_token, "table_id": table_id, "view_id": view_id,
                   "hierarchy_config": hierarchy_config},
        describe=f"name field {hierarchy_config.field_id} as the hierarchy on view {view_id}",
        traits=_traits(2))


def set_view_hidden_fields(app_token: str, table_id: str, view_id: str,
                           hidden_fields: Sequence[str]) -> SchemaRequest:
    """Set the columns the view ``view_id`` **hides** — what a human does not see when they
    open it.

    ``hidden_fields`` is a list of ``fld…`` ids, and the list is the WHOLE set: this replaces
    whatever was hidden before, it does not add to it. THE THREE-WAY DISTINCTION IS THE
    CONTRACT — ``[…]`` sets, ``[]`` **clears** (spell it :func:`clear_view_hidden_fields` and
    the intent is unmistakable), and **not asked for** is a different request constructor
    entirely, which sends no key at all. A caller who reads ``[]`` as "unchanged" un-hides a
    consumer's columns.

    The **shape** is refused here, locally, with zero calls; an unknown field id is
    **relayed**, because a field list is a read of a moment and predicting it would mean buying
    a ``list_fields`` read this route does not otherwise spend. **The table's PRIMARY field
    cannot be hidden** and is relayed for the same reason — see
    :data:`~larkdocio.base.view_client.HIDDEN_FIELDS_PRIMARY_IS_REFUSED` for Lark's own
    sentence.

    **What this changes, exactly.** A human opening the view stops seeing those columns
    (click-verified on the Lark web client, one tenant, 2026-08-12), and
    ``GET …/fields?view_id=`` marks them ``is_hidden: true`` — the same columns, plus a
    per-view flag. It is **not** a projection and **not** access control: the records payload
    through a hidden view is unchanged, and every value is still readable.
    """
    hidden = check_hidden_fields(hidden_fields)
    return SchemaRequest(
        op="update_view", app_token=app_token, table_id=table_id,
        arguments={"app_token": app_token, "table_id": table_id, "view_id": view_id,
                   "hidden_fields": hidden},
        describe=(f"hide {len(hidden)} column(s) on view {view_id}: {', '.join(hidden)}"
                  if hidden else
                  f"hide no columns on view {view_id} — CLEAR its hidden set, showing every "
                  f"column again"),
        traits=_traits(2))


def clear_view_hidden_fields(app_token: str, table_id: str, view_id: str) -> SchemaRequest:
    """**Show every column again** on the view ``view_id`` — the clear, spelled as a verb.

    Exactly :func:`set_view_hidden_fields` with an empty list, and it exists because the clear
    should not have to be written as a falsy argument: the measured behaviour is that ``[]``
    reads the ``property`` back as ``null``, and a reader who takes ``[]`` for *not asked for*
    gets the opposite of what they meant.
    """
    return set_view_hidden_fields(app_token, table_id, view_id, [])


def delete_view(app_token: str, table_id: str, view_id: str) -> SchemaRequest:
    """Delete the view ``view_id``. A table's **last** view answers ``1254023`` instead."""
    return SchemaRequest(
        op="delete_view", app_token=app_token, table_id=table_id,
        arguments={"app_token": app_token, "table_id": table_id, "view_id": view_id},
        describe=f"delete view {view_id} from table {table_id}",
        traits=_traits(1))


__all__ = [
    "HIDDEN_FIELDS_EMPTY_LIST_CLEARS",
    "HIDDEN_FIELDS_PRIMARY_IS_REFUSED",
    "HIDDEN_FIELDS_UNKNOWN_ID_IS_RELAYED",
    "check_view_type",
    "clear_view_hidden_fields",
    "create_view",
    "delete_view",
    "rename_view",
    "set_view_filter",
    "set_view_hidden_fields",
    "set_view_hierarchy",
]
