"""larkdocio.base.view_client — the **view** family's three client calls.

A mixin rather than three more methods pasted into
:mod:`larkdocio.base.schema_client`, for the reason the aggregator exists at all: a schema-op
family should be **one new file and one new line**, not an edit to a body three stories share.
:class:`BaseSchemaClient` mixes this in, so ``schema_ops.impl_of`` keeps resolving every op to a
method on the one schema client and the engine keeps taking one client.

**The dialect boundary lives on this module's signature, and that is deliberate.** ``PATCH
…/views/{view_id}`` takes a :class:`~larkdocio.base.view_filters.ViewFilterInfo` and nothing
else — not a ``dict``, and emphatically not a
:class:`~larkdocio.base.view_filters.SearchFilter`, which is ``field_name``-keyed and belongs to
``records/search``. There is no expression that sends the wrong dialect here, because there is
no value of the wrong type this signature accepts.

**PROPERTY'S THREE KEYS, AND THIS ROUTE NOW TAKES ALL THREE (D1″(a), amended by LD-296 and
LD-438).** ``filter_info`` was always here; ``hierarchy_config`` joined it when the objection
that kept it out — *"shipping a knob whose effect the library cannot observe"* — was **retired by
measurement**: the effect is captured (the read-back MOVED from one field id to another under a
second patch), and it is read back by this same library. ``hidden_fields`` has now cleared the
**same** bar, and the objection is retired for it the same way — **the rule stands; its premise
was refuted.** The premise was unobservability, and it came from a probe that kept only field
*names* on read-back, so a per-field flag in the payload it discarded could not have been seen:
``GET …/fields?view_id=`` reports ``is_hidden`` **per view** (``true`` on exactly the patched
column, ``false`` on the same column through a control view, the key absent entirely with no
``view_id``), and the maintainer's 2026-08-12 glance settled the human axis on the Lark web client. The
write half was never in doubt — LD-417 § B.6 measured ``hidden_fields`` **stored, moved by a
second patch, held as a set, cleared by ``[]``**, against an invented-key control that changed
nothing, with a nonexistent id **refused** by the server.

**``[]`` IS NOT ``None``.** ``hidden_fields=[…]`` sets the set, ``hidden_fields=[]`` **clears**
it (the capture reads back ``property: null``), and ``hidden_fields=None`` means *not asked for*
and sends no key at all. A caller who reads ``[]`` as *unchanged* silently un-hides a consumer's
columns, which is why the distinction is in every signature that carries this argument rather
than only in the guide.

The hierarchy value is held to the same dialect boundary as the filter: ``hierarchy_config``
takes a :class:`~larkdocio.base.hierarchy.HierarchyConfig` and nothing else — the value
:func:`larkdocio.base.hierarchy.hierarchy_config` produces, which is where the **local**
refusal for a non-link target lives, in the server's own words.

**R12, as everywhere on this surface**: the request is assembled from the pinned SDK's typed
builders, and each call sends exactly the keys its endpoint reads.
"""
from typing import TYPE_CHECKING, List, Optional, Sequence

from lark_oapi.api.bitable.v1 import (
    AppTableViewProperty,
    AppTableViewPropertyFilterInfo,
    AppTableViewPropertyFilterInfoCondition,
    AppTableViewPropertyHierarchyConfig,
    CreateAppTableViewRequest,
    DeleteAppTableViewRequest,
    PatchAppTableViewRequest,
    PatchAppTableViewRequestBody,
    ReqView,
)

from larkdocio.base.view_filters import VIEW_ROUTE_REQUIRES_FIELD_ID, ViewFilterInfo

if TYPE_CHECKING:  # pragma: no cover - the runtime import is lazy, inside the method
    from larkdocio.base.hierarchy import HierarchyConfig


#: **Why an unknown field id is RELAYED rather than predicted.** Authored once and quoted by
#: every signature that takes a hidden set, so the split between a local refusal and a relayed
#: one is stated wherever a caller meets it. The precedent is this surface's own: a non-link
#: hierarchy target is refused **locally** because the target's *kind* is already in the schema
#: the caller has, while an unknown field id is relayed, *"because a field list is a read of a
#: moment"* — predicting it would mean buying a ``list_fields`` read this route does not
#: otherwise spend, and still racing the answer.
HIDDEN_FIELDS_UNKNOWN_ID_IS_RELAYED = (
    "An id that is not a field on this table is NOT refused locally — it is RELAYED: Lark "
    "answers `1254044 \"Field id is not found.\"` and this library hands you that answer "
    "unedited, because a field list is a read of a moment and a local check would have to buy "
    "a `list_fields` read this route does not otherwise spend, then race the result anyway. "
    "What IS refused locally, before any call, is the SHAPE: a non-list, or a member that is "
    "not a string."
)

#: **THE TABLE'S PRIMARY FIELD CANNOT BE HIDDEN**, and this is Lark's own sentence for it —
#: measured on the live route (LD-438's live arm), not inferred. It is also the explanation of
#: an older, unexplained ``1254001`` on this same route: the answer was never about the body's
#: shape, it was about *which column* was named.
HIDDEN_FIELDS_PRIMARY_IS_REFUSED = (
    "A table's PRIMARY field cannot be hidden. Lark refuses it with `1254001` and says why in "
    "its own words — \"Invalid request parameter: 'property.hidden_fields[0].<fld…>'. Correct "
    "format : the primary field cannot be set as a hidden type.\" — naming the offending id. "
    "This library RELAYS that answer rather than predicting it, for the same reason it relays "
    "an unknown id: which column is primary is a read of a moment, and this route buys no "
    "field read. Hide the other columns and leave the primary one showing."
)

#: The three-way instruction contract, authored once. ``[]`` is a value, not silence.
HIDDEN_FIELDS_EMPTY_LIST_CLEARS = (
    "`[…]` sets the hidden set, `[]` CLEARS it (the view reads back with `property: null`), "
    "and `None` means NOT ASKED FOR and sends no key at all. Read `[]` as \"unchanged\" and "
    "you will silently un-hide a consumer's columns."
)


def check_hidden_fields(hidden_fields: Sequence[str]) -> List[str]:
    """The **local** half of the validation, with **zero transport calls** — and a copy.

    A bare ``str`` is the footgun this exists for: it is iterable, so a naive implementation
    would hide one column per character. A tuple or a set is refused too — the wire value is a
    JSON array and its **membership** is the contract, so accepting an unordered container here
    would make the read-back's comparison depend on a coincidence.
    """
    if isinstance(hidden_fields, str):
        raise TypeError(
            "hidden_fields takes a LIST of field ids, and a bare string is not a list of one: "
            f"{hidden_fields!r} would hide one column per character. Write "
            f"[{hidden_fields!r}]. Nothing was sent.")
    if not isinstance(hidden_fields, list):
        raise TypeError(
            "hidden_fields takes a list of field id strings — the `fld…` ids "
            "`list_fields` returns — and nothing else; got "
            f"{type(hidden_fields).__name__}. Nothing was sent.")
    for index, member in enumerate(hidden_fields):
        if not isinstance(member, str):
            raise TypeError(
                f"hidden_fields[index {index}] is a {type(member).__name__}, not a field id "
                f"string: {member!r}. Every member must be a `fld…` id. Nothing was sent.")
    return list(hidden_fields)


class BaseViewOps:
    """The three view calls, mixed into :class:`~larkdocio.base.schema_client.BaseSchemaClient`.

    Rides the host's transport unchanged — ``_checked`` is the paced, error-typed seam every
    schema call goes through — so no view call can bypass the rate limiter or the refusal seam.
    """

    def create_view(self, app_token: str, table_id: str, view_name: str,
                    view_type: str = "grid") -> str:
        """Create one view, returning its ``view_id``.

        The ``view_type`` allow-list is enforced **before** this, at the plan request
        (:func:`larkdocio.base.view_plan.create_view`), so a refused type costs zero calls.
        """
        body = ReqView.builder().view_name(view_name).view_type(view_type).build()
        request = CreateAppTableViewRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(body) \
            .build()
        response = self._checked(
            self._sdk.bitable.v1.app_table_view.create, request,
            f"create a {view_type} view named {view_name!r} in table {table_id}")
        return getattr(response.data.view, "view_id", None)

    def update_view(self, app_token: str, table_id: str, view_id: str, *,
                    view_name: Optional[str] = None,
                    filter_info: Optional[ViewFilterInfo] = None,
                    hierarchy_config: Optional["HierarchyConfig"] = None,
                    hidden_fields: Optional[List[str]] = None):
        """Rename a view, set its **persistent filter**, name its **hierarchy field**, and/or
        set the columns it **hides**.

        ``filter_info`` is a :class:`~larkdocio.base.view_filters.ViewFilterInfo` — the only
        value this route accepts, and one that can be obtained solely from
        :func:`larkdocio.base.view_filters.view_filter`. A ``dict`` or a ``SearchFilter`` is a
        :class:`TypeError` here, **before** any call.

        ``hierarchy_config`` is a :class:`~larkdocio.base.hierarchy.HierarchyConfig`, obtainable
        solely from :func:`larkdocio.base.hierarchy.hierarchy_config` — which refuses a non-link
        target **locally**, in the server's own words, so this route never relays a ``1254001``
        it could have predicted. A raw field id string is a :class:`TypeError` here.

        ``hidden_fields`` is a **list of field id strings** — the columns a human does not see
        when they open this view. THE THREE-WAY DISTINCTION IS THE CONTRACT:
        ``hidden_fields=[…]`` sets the set, ``hidden_fields=[]`` **CLEARS** it (the view reads
        back with ``property: null``), and ``hidden_fields=None`` means **not asked for** and
        sends no key at all — a caller who reads ``[]`` as *unchanged* will silently un-hide a
        consumer's columns. The shape is checked **locally**, before any call; an id that is not
        a field on this table is **relayed** (``1254044 "Field id is not found."``) rather than
        predicted, because a field list is a read of a moment and predicting it would mean
        buying a ``list_fields`` read this route does not otherwise spend.

        **The table's PRIMARY field cannot be hidden** — Lark refuses that with ``1254001``,
        naming the id and the reason, and this library relays it (see
        :data:`HIDDEN_FIELDS_PRIMARY_IS_REFUSED`).

        **Hiding a column hides it from a human and from the field listing's per-view flag —
        not from a read.** ``GET …/fields?view_id=`` still returns every column, marked
        ``is_hidden``; the records payload through a hidden view is measurably unchanged. This
        is not a projection and it is not access control.

        Each key is sent only when it was asked for: the SDK omits an unset key entirely, so a
        filter patch cannot disturb the view's hierarchy or its hidden columns, and a
        hidden-fields patch cannot disturb its filter.
        """
        from larkdocio.base.hierarchy import HierarchyConfig
        from larkdocio.base.schema_client import BaseSchemaRefusal

        if (view_name is None and filter_info is None and hierarchy_config is None
                and hidden_fields is None):
            raise BaseSchemaRefusal(
                "update_view was asked to change nothing: give it a view_name, a filter_info, "
                "a hierarchy_config, a hidden_fields list, or any combination. An empty PATCH "
                "would answer code:0 and mean nothing, which is exactly the class of call this "
                "surface refuses to make. NOTE hidden_fields=[] is NOT nothing — it is the "
                "instruction to CLEAR the hidden set, and it is sent.")
        if filter_info is not None and not isinstance(filter_info, ViewFilterInfo):
            raise TypeError(
                "the view route takes a ViewFilterInfo — the value "
                "larkdocio.base.view_filters.view_filter(...) produces — and nothing else; got "
                f"{type(filter_info).__name__}. {VIEW_ROUTE_REQUIRES_FIELD_ID} Nothing was "
                "sent.")
        if hierarchy_config is not None and not isinstance(hierarchy_config, HierarchyConfig):
            raise TypeError(
                "the view route takes a HierarchyConfig for hierarchy_config — the value "
                "larkdocio.base.hierarchy.hierarchy_config(field_id, fields=…) produces — and "
                f"nothing else; got {type(hierarchy_config).__name__}. That producer is where "
                "the local refusal lives: a target that is not a single_link or duplex_link "
                "column is refused there, before any call. Nothing was sent.")
        if hidden_fields is not None:
            hidden_fields = check_hidden_fields(hidden_fields)
        builder = PatchAppTableViewRequestBody.builder()
        if view_name is not None:
            builder = builder.view_name(view_name)
        if filter_info is not None or hierarchy_config is not None or hidden_fields is not None:
            builder = builder.property(
                _property_of(filter_info, hierarchy_config, hidden_fields))
        request = PatchAppTableViewRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .view_id(view_id) \
            .request_body(builder.build()) \
            .build()
        response = self._checked(
            self._sdk.bitable.v1.app_table_view.patch, request,
            f"update view {view_id} in table {table_id}")
        return getattr(response.data, "view", None)

    def delete_view(self, app_token: str, table_id: str, view_id: str) -> bool:
        """Delete one view. ``True`` when the call returned; the **read-back** decides whether
        it happened — and a table's LAST view answers ``1254023`` rather than deleting."""
        request = DeleteAppTableViewRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .view_id(view_id) \
            .build()
        self._checked(self._sdk.bitable.v1.app_table_view.delete, request,
                      f"delete view {view_id} from table {table_id}")
        return True


def _property_of(filter_info: Optional[ViewFilterInfo] = None,
                 hierarchy_config=None,
                 hidden_fields: Optional[List[str]] = None) -> AppTableViewProperty:
    """The typed ``property`` a view patch sends — **only the keys that were asked for**.

    All three wire keys are reachable now, and the omission is load-bearing in **every**
    direction: the SDK leaves an unset key out of the body entirely, so a filter patch cannot
    disturb a view's hierarchy or its hidden columns, a hierarchy patch cannot disturb its
    filter, and a hidden-fields patch cannot disturb either. That symmetry is proven by
    round-trip tests rather than asserted in this sentence.

    ``hidden_fields=[]`` is set **deliberately**: an empty array is the CLEAR instruction and it
    must reach the wire, which is exactly why the ``is not None`` test below is not a truthiness
    test. ``property.group_info`` and every ``sort`` spelling remain unreachable — they are
    ``code:0``-and-not-stored, so there is nothing to send.
    """
    builder = AppTableViewProperty.builder()
    if hidden_fields is not None:
        builder = builder.hidden_fields(list(hidden_fields))
    if hierarchy_config is not None:
        builder = builder.hierarchy_config(
            AppTableViewPropertyHierarchyConfig.builder()
            .field_id(hierarchy_config.field_id).build())
    if filter_info is None:
        return builder.build()
    body = filter_info.to_dict()
    conditions = []
    for condition in body["conditions"]:
        leg = AppTableViewPropertyFilterInfoCondition.builder() \
            .field_id(condition["field_id"]) \
            .operator(condition["operator"])
        # `value` is a STRING carrying a JSON array on this route (the SDK's own `_types` says
        # so, and the live probe agrees: an array answers 9499). A valueless operator omits the
        # key entirely — the builder leaves an unset key out, which is the only shape the route
        # accepts: `""` answers 1254001 and `[]` answers 9499.
        if "value" in condition:
            leg = leg.value(condition["value"])
        conditions.append(leg.build())
    info = AppTableViewPropertyFilterInfo.builder() \
        .conjunction(body["conjunction"]) \
        .conditions(conditions) \
        .build()
    return builder.filter_info(info).build()


__all__ = [
    "BaseViewOps",
    "HIDDEN_FIELDS_EMPTY_LIST_CLEARS",
    "HIDDEN_FIELDS_PRIMARY_IS_REFUSED",
    "HIDDEN_FIELDS_UNKNOWN_ID_IS_RELAYED",
    "check_hidden_fields",
]
