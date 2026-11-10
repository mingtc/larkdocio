"""larkdocio.base._typed — one by-name walk, for every door a Base field arrives through.

Three doors deliver the same field to the readers in this package, and all three are shipped
paths: the read client's own SDK-typed ``AppTableField``, whose ``property`` is an
``AppTableFieldProperty`` **object**; the bridged dict :func:`larkdocio.base.table.field_spec`
produces with the SDK's own serializer; and a captured payload's wire dict, verbatim. Several
readers ask the same question of all three — *"what does this field's property say?"* — and the
mechanism for asking is one step: **read the name off whatever the node turns out to be.**

**That step used to exist in four copies, and one of them cost a shipped refusal.** A copy that
required a mapping at every step saw the typed door's nested objects and stopped, so a Lookup
whose target table was right there read as one whose provenance had not arrived — and a caller
that treats an unreadable Lookup as a loss it cannot enumerate then refused a whole operation
over a key it was holding the answer for (LD-281; the post-mortem is written at
:func:`larkdocio.base.loss_preview._property_of`). An offline fixture built from a raw capture
is a mapping all the way down and cannot reproduce that mistake. One copy of the walk is
therefore worth more than four correct-looking ones: there is now a single place for that
mistake to be made, and a single place for it to be fixed.

**This module holds no list of field names, and it must not gain one.** Which names a reader
copies out of a property is that reader's own contract, and each list stays at its own call
site: the provenance reader beside this one copies its three, the link reader its two, the
destructive preview its seven, the row-hierarchy reader its one. A default set here would widen
every reader to the union of them all the first time one gained a name — a question about what
this library *reports*, which is not a question a refactor may answer. :func:`_by_name`
therefore takes its names from the caller and has no default.

**One reader deliberately does not walk through here.** ``base.table``'s property projection
round-trips the whole property through the SDK's own serializer, because its contract is *the
wire shape untouched* rather than *these names, read by name*. Different question, different
technique; it is not a fifth copy of this walk.

Nothing here makes a call, needs a credential or imports a transport: every node it is handed
was already fetched.
"""
from typing import Any, Dict, Mapping, Optional, Sequence


def _step(node: Any, key: str) -> Optional[Any]:
    """One step of the walk, **by name, whatever the node is** — the rule a reader applies at
    the top of a property, applied to the inside of it.

    A mapping is read with ``get``; anything else is read with ``getattr``, because the typed
    door nests typed objects rather than dicts: the pinned SDK's ``property.filter_info`` is an
    ``AppTableFieldPropertyLookupFilter``, not a ``dict``. A walk that required a mapping at
    every step saw that object and stopped, so a Lookup whose target table was right there read
    as one whose provenance had not arrived — and a caller that treats an unreadable Lookup as
    a loss it cannot enumerate then refuses a whole operation over a key it was holding.

    A scalar or a sequence answers ``None`` here, which is what ``getattr`` on one already
    does — an absent step, never an error.
    """
    if isinstance(node, Mapping):
        return node.get(key)
    return getattr(node, key, None)


def _nested(prop: Optional[Any], path: Sequence[str]) -> Optional[Any]:
    """Walk a dotted path through a property, answering ``None`` at the first step that is not
    there. An absent nested key is a normal shape, never an error."""
    node: Any = prop
    for step in path:
        if node is None:
            return None
        node = _step(node, step)
    return node


def _by_name(node: Any, keys: Sequence[str]) -> Dict[str, Any]:
    """The one-level copy: each of ``keys``, read off ``node`` **by name**, in the order given.

    A name that is not there materialises as ``None`` rather than being dropped, which is what
    makes a key an SDK model does not declare read identically to a key the wire sent as
    ``null`` — the equivalence the link reading rests on, stated in its own docstring.

    **What is copied through is the value, not a conversion of it.** A nested typed object
    travels as that object; the caller that needs to see inside it walks it with
    :func:`_nested`, which does not care which door it came from either.

    ``keys`` is the caller's own list and there is no default: see this module's docstring for
    why a shared one would be a widening rather than a simplification.
    """
    return {key: _step(node, key) for key in keys}
