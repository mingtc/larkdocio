"""larkdocio.base.schema_ops_views — the **view** schema-op family.

One family module and one line in :data:`larkdocio.base.schema_ops.FAMILY_MODULES`, which is
the contract the app-and-table family established. It knows nothing about the other families,
and this one carries something they do not: the family's **own** apply hooks (``issue``,
``read_back``) and its **own** staleness disclosure, so the engine dispatches through the
registry instead of growing a branch per family.

**Three ops: create a view, patch it, delete it.** The ``view_type`` allow-list is
*evidence-keyed*, not guessed: ``grid`` / ``kanban`` / ``gallery`` / ``gantt`` were each created
``code:0`` in ``p0-3-01``, and ``calendar`` / ``board`` / ``list`` were each refused ``99992402``
by the server, whose own ``field_violations`` body names the accepted enum verbatim. This
library refuses those three **locally, in the server's own words**, so a caller meets the answer
without spending a round trip on it.

**``form`` is refused BY POLICY, and the reason is not "impossible".** ``POST …/views`` with
``view_type: "form"`` **works** — it is in the server's own enum — and the ``view_id`` it returns
**IS** the ``form_id``. One further ``PATCH …/forms/{id} {"shared": true}`` mints a public
submission URL, with Lark self-selecting ``shared_limit: "anyone_editable"``. By a standing
ruling, re-confirmed at this surface's own mint, this surface exposes **no path** to any of it. The
shipped sentence is register row 17's own — quoted, not re-authored.

**WHAT A VIEW PATCH CAN CARRY (D1″(a), amended by LD-296 and LD-438).** Three ``property`` keys
are parameters — ``filter_info``, ``hierarchy_config`` and ``hidden_fields`` — and each one
earned it the same way: **its effect is captured, and this library reads it back.**
``hierarchy_config`` came first (a second PATCH **moved** the read-back from one field id to
another, against a bogus-key control that answered ``code:0`` and changed nothing).
``hidden_fields`` followed under LD-438 on the same terms: LD-417 § B.6 measured it stored,
moved, held as a set and **cleared by ``[]``**, with a nonexistent id **refused** by the server;
what was missing was the *observability* half, and that turned out to be an artefact of a probe
that kept only field **names** — ``GET …/fields?view_id=`` marks the hidden column
``is_hidden: true``, the control view marks the same column ``false``, and the key is absent
entirely with no ``view_id``. **The rule was never wrong; its premise was.**

**GROUPING AND A SAVED VIEW-LEVEL SORT STILL HAVE NO PARAMETER ANYWHERE**, and a gantt view's
date binding has no route at all. ``property.group_info`` answers ``code:0`` and reads back
``property: null``; all **eight** measured sort spellings do the same, indistinguishable from an
invented-key control, in the same run where ``filter_info`` — the positive control — stored. Each
is a register row in the source repository's ``BASE.md``. They are not knobs because there is nothing to
observe, which is the same test ``hidden_fields`` has now passed and they have not.

**``delete_view`` IS A REGISTERED ``DELETE`` AND IS DELIBERATELY NOT DESTRUCTIVE — this family
declares an EMPTY ``DESTRUCTIVE_OPS``, and that empty set is the ruling rather than an
omission.** The three ops :func:`larkdocio.base.schema_ops.destructive_ops` does return —
``delete_field``, ``delete_table``, ``batch_delete_tables`` — share one property: each destroys
**cells**, a column's worth or a table's worth, and a caller cannot tell from the request how
many, which is exactly what the cross-table loss preview and the consent token exist for. A view
delete shares none of it. A view is a **saved presentation** of a table — a filter, a hierarchy
pointer, a hidden-field set — so deleting one destroys **configuration and not one record**:
there is no loss to enumerate, therefore nothing to consent to, and every record it presented is
still there under every other view. It is not an unguarded call, it is a guarded call with
nothing to preview — still ``mutates=True``, still plan-gated, still verified by read-back
(``GET …/views`` no longer lists the id) — and the server keeps a floor of its own, refusing the
last view in a table (``1254023 LastViewDeleteForbidden``).

**THE PRECEDENT, for the next family that ships a delete.** ``DESTRUCTIVE_OPS`` is about **data
loss**, never about the verb: declare an op there when a caller cannot tell from the request how
many cells it will destroy, and write the sentence *here* when the delete loses no data. Silence
is the defect this paragraph exists to prevent — what silence loses is the **reason**, and the
reason is the only thing the next family can reason from.

**Verified by READ-BACK, never by ``code:0``** — and on this rung that rule has a **negative
control** one key away: a ``property.group_info`` ``PATCH`` answers ``code:0`` and the view reads
back ``property: null``. That pairing is the whole argument, and it is why every op below names
a read-back the engine performs.
"""
from typing import Optional

from lark_oapi.api.bitable.v1 import (
    CreateAppTableViewRequest,
    DeleteAppTableViewRequest,
    PatchAppTableViewRequest,
)

from larkdocio.base.schema_ops import BaseSchemaOpDescriptor, SchemaOpFamily
from larkdocio.base.view_filters import (
    SERVER_ADDED_CONDITION_KEYS,
    ViewFilterInfo,
    echoes,
    normalize_persisted,
)
from larkdocio.common.citations import dev_repo

_CAPTURES = "tests/captures/base-study/captures"
_P0 = "dev/base-study/p0-addendum-2026-08-03.md"
_PARITY = "dev/base-study/ui-parity-matrix-2026-08-03.md"
#: LD-417 leg B's own capture home, and the attribution pack that refuted the observability
#: premise (the `is_hidden` per-view flag). Separate constants because they are a separate
#: spike's evidence and must stay traceable to it.
_HIDDEN_CAPTURES = "dev/base-authoring-spike/captures"
_ATTRIBUTION = "tests/captures/permissions-spike/captures"

#: The family's name, used by the aggregator and quoted in the source repository's ``BASE.md``
#: schema-ops table.
FAMILY_NAME = "view"

#: The scope every entry in this family carries. A view is not app-scoped and not a row.
SCOPE = "view"

# --------------------------------------------------------------------------- #
# The view_type allow-list — evidence-keyed in BOTH directions                 #
# --------------------------------------------------------------------------- #

#: The four types a capture actually created (``p0-3-01``, each ``code:0`` with a ``view_id``).
VIEW_TYPES = ("grid", "kanban", "gallery", "gantt")

#: The three the **server** refused ``99992402`` (``p0-3-01``). Refused locally using the
#: server's own vocabulary rather than re-derived.
SERVER_REFUSED_VIEW_TYPES = ("calendar", "board", "list")

#: The accepted enum **verbatim from Lark's own ``error.field_violations`` body**. It contains
#: ``form``, which this library excludes by policy — quoting the server's list unedited is the
#: point: a caller sees what Lark says and then sees what larkdocio does with it.
SERVER_VIEW_TYPE_ENUM = "view_type is optional, options: [grid,kanban,gallery,gantt,form]"

#: Register row 17's sentence, **quoted**. The one authoring of the shareability policy lives
#: in the source repository's ``BASE.md``; this module must not write a second one that could drift from it.
SHAREABILITY_IS_NOT_OURS = "larkdocio does not control a Base's shareability"

#: Why ``form`` is not in :data:`VIEW_TYPES`. A statement about **this library** — the API half
#: plainly works, and saying otherwise would be false.
FORM_IS_REFUSED_BY_POLICY = (
    f"`form` is a view type Lark accepts — it is in the server's own enum and creating one "
    f"works — and this library still will not create one, by POLICY: a form view's "
    f"`view_id` IS the `form_id`, and one further `PATCH …/forms/{{id}} {{\"shared\": true}}` "
    f"mints a PUBLIC submission URL, with Lark selecting `anyone_editable` by itself. "
    f"{SHAREABILITY_IS_NOT_OURS}: no operation on this surface reaches a forms or a "
    f"permissions endpoint. If you need a form, make it in the product."
)

#: ``1254023``'s actionable half, authored once: what the caller can actually do about it.
LAST_VIEW_IS_PROTECTED = (
    "A table's last view cannot be deleted (`1254023 LastViewDeleteForbidden`): Lark keeps "
    "every table on a floor of one view. Create a view first, then delete this one. This "
    "answer is about THIS view only — every other entry in the plan is judged on its own."
)

# --------------------------------------------------------------------------- #
# AC6 — there is NO anchor for a view write, and the plan says so              #
# --------------------------------------------------------------------------- #

#: **What a view write is NOT guarded by.** Quoted verbatim by every view plan entry and by the
#: apply-log, so the two cannot drift — and deliberately a **different** statement from the
#: app-scoped one: that fact is about ``app.revision`` counting inconsistently, this one is
#: about there being nothing to count at all.
NO_VIEW_ANCHOR = (
    "A view write carries NO staleness guard of any kind. There is no view revision in any "
    "capture, and what `table.revision` does in response to a view PATCH was never measured — "
    "so no compare-and-swap is built on either, and this library does not imply one. What a "
    "view write has instead is a READ-BACK: the view is re-read and its persisted "
    "`property.filter_info` must echo the conditions that were sent. That is not decoration. "
    "On this endpoint `code:0` proves acceptance and nothing else — the sibling key "
    "`property.group_info` answers `code:0` and reads back `property: null` — so a call whose "
    "read-back does not echo is reported NOT PERSISTED, never applied. If something else "
    "changes this view between your plan and your apply, nothing here will notice."
)

#: The engine reads this off the family module — the same "ask the family" seam the handler
#: dicts below are found over; see :func:`larkdocio.base.schema_plan.disclosure_for_op`.
REVISION_GUARD_DISCLOSURE = NO_VIEW_ANCHOR


#: **EMPTY ON PURPOSE — the ruling, stated rather than defaulted.** ``destructive_ops()`` unions
#: whatever the registered families publish under this name, so a family that simply omits it and
#: a family that publishes nothing are indistinguishable to the fence and to a reader. This
#: family's delete is a **configuration** delete (the paragraph above argues it), so the set is
#: empty by decision; declaring it says so, where silence only failed to say the opposite.
DESTRUCTIVE_OPS = frozenset()


SCHEMA_OP_FAMILY = SchemaOpFamily(
    name=FAMILY_NAME,
    module=__name__,
    ops=(
        BaseSchemaOpDescriptor(
            name="create_view",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views",
            http_method="POST",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back="GET …/views lists the returned view_id under the name that was asked for",
            request_cls=CreateAppTableViewRequest,
            evidence=dev_repo(f"{_CAPTURES}/p0-3-01-view-create-matrix.json · {_P0} § 3"),
        ),
        BaseSchemaOpDescriptor(
            name="update_view",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views/:view_id",
            http_method="PATCH",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=("GET …/views/{v} re-reads the view — the LISTING does not carry a "
                       "property at all — and its persisted property.filter_info must ECHO "
                       "the conditions sent, its property.hierarchy_config the field id sent, "
                       "and its property.hidden_fields the SET of field ids sent (an empty "
                       "list is the CLEAR, and it reads back as property: null, which counts "
                       "as confirmed); the sibling key group_info answers code:0 and reads "
                       "back null, and so does an unrecognised key inside hierarchy_config, "
                       "which is why code:0 is not evidence on this route"),
            request_cls=PatchAppTableViewRequest,
            evidence=(dev_repo(f"{_PARITY} § Seat addendum item 4 · "
                      f"{_CAPTURES}/p0-3-02-view-patch.json · "
                      f"{_CAPTURES}/p1-q3-02-view-grouping.json · "
                      f"{_CAPTURES}/subitems-b-05-hierarchy-config-patch-matrix.json · "
                      f"{_HIDDEN_CAPTURES}/ld417-b-03-hidden-fields-persistence.json · "
                      f"{_ATTRIBUTION} (is_hidden per view: 778-/787-/772-/788-)")),
        ),
        BaseSchemaOpDescriptor(
            name="delete_view",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views/:view_id",
            http_method="DELETE",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back="GET …/views no longer lists the view_id",
            request_cls=DeleteAppTableViewRequest,
            evidence=dev_repo(f"{_CAPTURES}/p0-3-05-view-delete.json · {_P0} § 3"),
        ),
    ),
)


# --------------------------------------------------------------------------- #
# The family's OWN apply hooks — the engine dispatches, it does not branch      #
# --------------------------------------------------------------------------- #

def _issue(watch, entry):
    """Make ONE view call. The engine finds this in :data:`ISSUE_HANDLERS`, so a new family is
    still one file plus one line."""
    arguments = dict(entry.fields or {})
    if entry.op == "create_view":
        return watch.create_view(arguments["app_token"], arguments["table_id"],
                                 arguments["view_name"], arguments["view_type"])
    if entry.op == "delete_view":
        return watch.delete_view(arguments["app_token"], arguments["table_id"],
                                 arguments["view_id"])
    return watch.update_view(arguments["app_token"], arguments["table_id"],
                             arguments["view_id"],
                             view_name=arguments.get("view_name"),
                             filter_info=arguments.get("filter_info"),
                             hierarchy_config=arguments.get("hierarchy_config"),
                             # `.get` returns None for "not in the entry", which is exactly the
                             # NOT-ASKED-FOR meaning — and an entry that carries `[]` keeps it,
                             # because `[]` is the CLEAR instruction and not an absence.
                             hidden_fields=arguments.get("hidden_fields"))


def _views_by_id(read_client, app_token, table_id) -> dict:
    return {getattr(view, "view_id", None): view
            for view in (read_client.list_views(app_token, table_id) or ())}


def _persisted_filter(view) -> Optional[dict]:
    """The view's ``property.filter_info`` as a plain dict, or ``None``.

    The SDK hands back typed objects; the comparison is over plain data, so the conversion is
    here and it is explicit — including the two keys the server adds, which are carried through
    so :func:`~larkdocio.base.view_filters.normalize_persisted` can drop them **by name**.
    """
    prop = getattr(view, "property", None)
    info = getattr(prop, "filter_info", None) if prop is not None else None
    if info is None:
        return None
    conditions = []
    for condition in (getattr(info, "conditions", None) or ()):
        blob = {"field_id": getattr(condition, "field_id", None),
                "operator": getattr(condition, "operator", None),
                # A STRING on this route, and `None` for a valueless operator whose key was
                # omitted — the normalisation drops that `None` by name.
                "value": getattr(condition, "value", None)}
        for key in SERVER_ADDED_CONDITION_KEYS:
            value = getattr(condition, key, None)
            if value is not None:
                blob[key] = value
        conditions.append(blob)
    return {"conjunction": getattr(info, "conjunction", None), "conditions": conditions}


def _persisted_hierarchy(view):
    """The view's ``property.hierarchy_config`` as a plain dict, or ``None``.

    ``None`` covers both *not configured at all* (``property: null`` — every product-built
    view) and *the key is unset*, which read identically in every capture and mean the same
    thing to a read-back: nothing landed.
    """
    from larkdocio.base.hierarchy import hierarchy_field_id

    field_id = hierarchy_field_id(view)
    return None if field_id is None else {"field_id": field_id}


def _persisted_hidden_fields(view):
    """The view's ``property.hidden_fields`` as a plain list, or ``None``.

    ``None`` covers *nothing is hidden* in both the shapes the live API serves for it: the whole
    ``property`` read back as ``null`` (what a ``hidden_fields=[]`` clear produces — measured,
    LD-417 § B.6 arm 4) and the key simply unset. Both mean the same thing to a read-back.
    """
    prop = getattr(view, "property", None)
    hidden = getattr(prop, "hidden_fields", None) if prop is not None else None
    return None if hidden is None else list(hidden)


def _read_back(read_client, entry, reply, created_app_token):
    """``(confirmed, disclosure)`` for one landed view op, read from the server's own state.

    One listing per entry. **Never ``code:0``** — and for a filter patch the comparison is
    semantic and whole-value: the server's ``condition_id`` / ``field_type`` additions are
    normalised away by name, and anything else that differs makes this ``False``.
    """
    arguments = dict(entry.fields or {})
    views = _views_by_id(read_client, arguments["app_token"], arguments["table_id"])

    if entry.op == "create_view":
        view = views.get(reply)
        seen = getattr(view, "view_name", None) if view is not None else None
        return (view is not None and seen == arguments["view_name"]), {
            "how": entry.read_back, "view_id": reply, "view_name": seen,
            "expected": arguments["view_name"]}

    if entry.op == "delete_view":
        gone = arguments["view_id"] not in views
        return gone, {"how": entry.read_back, "view_id": arguments["view_id"], "gone": gone,
                      "listed": sorted(v for v in views if v)}

    if arguments["view_id"] not in views:
        return False, {"how": entry.read_back, "view_id": arguments["view_id"],
                       "listed": False}
    # THE LISTING IS NOT ENOUGH, and that is measured rather than assumed: `GET …/views` does
    # not carry a view's `property` at all — the same view returns `filter_info` from
    # `GET …/views/{view_id}` and has the key absent entirely from the listing. So the listing
    # answers "does this view still exist", and the SINGLE-view read answers "did the filter
    # persist". Both are reads; neither is a `code:0`.
    view = read_client.get_view(arguments["app_token"], arguments["table_id"],
                                arguments["view_id"])
    disclosure = {"how": entry.read_back, "view_id": arguments["view_id"],
                  "view_name": getattr(view, "view_name", None)}
    if arguments.get("view_name") is not None:
        disclosure["expected"] = arguments["view_name"]
        if disclosure["view_name"] != arguments["view_name"]:
            return False, disclosure
    hierarchy = arguments.get("hierarchy_config")
    if hierarchy is not None:
        # THE SAME RULE AS THE FILTER, and here it is the whole argument: an unrecognised key
        # inside `property.hierarchy_config` answered `code:0` and changed nothing, so only the
        # ECHO of the field id proves the patch landed.
        persisted = _persisted_hierarchy(view)
        disclosure.update({
            "sent_hierarchy_config": hierarchy.to_dict(),
            "persisted_hierarchy_config": persisted,
            "echoes": persisted == hierarchy.to_dict(),
        })
        if persisted != hierarchy.to_dict():
            return False, disclosure

    hidden = arguments.get("hidden_fields")
    if hidden is not None:
        # THE SAME RULE, THIRD KEY — and here `code:0` is at its least trustworthy, because the
        # write was accepted on a route where a sibling key is silently swallowed. The
        # comparison is over the SET: a hidden set is membership, not order, and no field
        # ORDERING route exists on this surface for an order to be a contract about.
        persisted = _persisted_hidden_fields(view)
        confirmed = set(persisted or ()) == set(hidden)
        disclosure.update({
            "sent_hidden_fields": list(hidden),
            "persisted_hidden_fields": persisted,
            # An empty list is the CLEAR, and a cleared view reads back `property: null` — so
            # `None` is the CONFIRMATION of a clear, never a failure to land it.
            "cleared": not hidden,
            "echoes": confirmed,
        })
        if not confirmed:
            return False, disclosure

    sent = arguments.get("filter_info")
    if sent is None:
        return True, disclosure
    persisted = _persisted_filter(view)
    confirmed = echoes(sent if isinstance(sent, ViewFilterInfo) else _reforge(sent), persisted)
    disclosure.update({
        "sent": sent.to_dict() if isinstance(sent, ViewFilterInfo) else dict(sent),
        "persisted": normalize_persisted(persisted),
        "normalized_away": list(SERVER_ADDED_CONDITION_KEYS),
        "echoes": confirmed,
    })
    return confirmed, disclosure


def _reforge(body):  # pragma: no cover - a plan entry always carries the typed value
    raise TypeError(
        "a view filter reached the read-back as a plain body rather than a ViewFilterInfo; "
        "the plan carries the typed value precisely so the comparison cannot be run against "
        "something that never passed the view dialect's serialiser.")


#: **The engine's dispatch table for this family**, keyed by op name — published beside the
#: descriptors so :mod:`larkdocio.base.schema_apply` never grows a branch per family. Derived
#: from :data:`SCHEMA_OP_FAMILY` rather than hand-listed, so an op added above cannot be
#: forgotten here.
ISSUE_HANDLERS = {descriptor.name: _issue for descriptor in SCHEMA_OP_FAMILY.ops}

#: Every view op is verified by the SAME read-back, which branches on the op inside itself.
READ_BACK_HANDLERS = {name: _read_back for name in ISSUE_HANDLERS}


__all__ = [
    "DESTRUCTIVE_OPS",
    "FAMILY_NAME",
    "FORM_IS_REFUSED_BY_POLICY",
    "LAST_VIEW_IS_PROTECTED",
    "NO_VIEW_ANCHOR",
    "REVISION_GUARD_DISCLOSURE",
    "SCHEMA_OP_FAMILY",
    "SCOPE",
    "SERVER_REFUSED_VIEW_TYPES",
    "SERVER_VIEW_TYPE_ENUM",
    "SHAREABILITY_IS_NOT_OURS",
    "VIEW_TYPES",
    "ISSUE_HANDLERS",
    "READ_BACK_HANDLERS",
]
