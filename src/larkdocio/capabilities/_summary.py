"""THE SUMMARY — ``capabilities()``'s no-argument answer, DERIVED from the full payload.

Why this module exists
----------------------
The full registry is ~400 KB of JSON. It is the right answer to *"what exactly does this
operation require"* and the wrong answer to *"what can this library do"* — a reader drawing a
conclusion from it can easily draw a wrong one, and reading it whole can overflow a context
window. So the front door swaps, the way ``guide()``'s did (LD-468): the
no-argument call returns **this**, and the whole payload moves behind ``full=True``.

**The one binding design condition (maintainer, 2026-08-16): the summary may not become a second
hand-maintained copy of the truth.** It is therefore a **pure function of the payload** —
:func:`summary` takes the assembled ``dict`` and nothing else. **At module scope it imports
``inspect``, ``json`` and ``._models`` — the stdlib and the payload's own key vocabulary, and
nothing that holds capability truth**, which is the exact set the guard asserts. There is one
import below module scope, ``._assembly`` inside :func:`_reading`, and it reads only that
module's ``capabilities`` **identity and signature** — the function's ``__name__`` and its
parameter names, so the ``reading`` block cannot spell a call that does not exist — never a
capability fact. So there is no name in this module that the payload does not already carry,
and no fact it could state that the payload does not: a structural property rather than a
promise, and held to exactly that scope — module-level imports — by the guard named below.

Beside it, and for the same reason ``larkdocio.permissions`` ships
:func:`~larkdocio.permissions.coverage_gaps` rather than leaving the check to a test file,
:func:`summary_gaps` is the **bidirectional** guard — an operation the payload ships and the
summary omits, and a summary row naming an operation no surface carries. Pure, injectable and
red-provable in-process, so both directions are proved against specimens rather than asserted
(``tests/test_capabilities_summary.py``, in the source repository — a test tree is not importable from
the wheel).

What the summary carries, and what it deliberately does not
-----------------------------------------------------------
**Names, never prose.** Every surface's operations appear as ``{"name", "kind"}`` — the same
discipline :func:`~larkdocio.guide_sections` follows (an index is worth having only if it is
cheaper than the thing it indexes). The scope strings are here because *"what does it need"*
is half the question a caller opens with, and a scope string is a dozen bytes; the evidence
that established it is not, and stays in the payload.

**Every key here is a key there.** ``surfaces``, ``flags``, ``safety_contracts``,
``workflows``, ``docs`` and ``entry_points`` are the payload's own top-level key names, so a
reader who finds a name in the summary knows the address that holds its full row without
being told a mapping.
"""
import inspect
import json

from ._models import CALL_SITES_KEY, PERMISSIONS_KEY, UNKNOWN_REQUIREMENTS_KEY

#: The payload's top-level indexes that the summary reduces to **their key lists** — the id
#: is the address, so a reader who wants a row knows where it is. Derived reduction, not a
#: second enumeration: the keys come from the payload at call time.
_ID_INDEXES = ("flags", "safety_contracts", "workflows", "docs", "entry_points")

#: The short, per-surface fields the summary carries verbatim. Long-form fields
#: (``levels``, ``content_constraints``, ``gate_coverage``, ``block_read_support``, every
#: ``permissions`` block …) are deliberately absent — that is what ``full=True`` and
#: ``surface=`` are for.
_SURFACE_FIELDS = ("title", "domain", "mode", "opt_in", "gated_by")


def json_bytes(obj) -> int:
    """*obj*'s size in canonical JSON — the one serialization this module measures anything in.

    Authored once so the boundedness guard, the size the ``reading`` block discloses and any
    future reader all quote the same figure under the same rules; two measurements of "how big
    is it" that disagree by a serialization option is a defect a reader cannot resolve.
    """
    return len(json.dumps(obj, default=str, sort_keys=True).encode("utf-8"))


def _reading(payload):
    """How to get more, spelled as the calls that do it — **and how big each one is**.

    The function name and its parameter names are read off
    :func:`~larkdocio.capabilities.capabilities`'s **own** identity and signature, and the
    example surface id off the payload's **own** surfaces, so a rename of any of them cannot
    leave this block telling a caller to make a call that does not exist — and nothing here is
    a spelling this module chose.

    **The size is the NEXT call's, never this one's** (LD-571). ``guide()`` set the precedent
    for a reason worth restating: a call cannot state its own size without changing it, so what
    is disclosed is the size of what the caller is being sent to — measured off the payload in
    hand, so it moves with the registry and can never be a stale literal.
    """
    from ._assembly import capabilities as _capabilities

    entry_point = _capabilities.__name__
    params = inspect.signature(_capabilities).parameters
    surface_param = next(iter(params))
    full_param = list(params)[-1]
    example = next(iter(payload.get("surfaces") or {"<surface-id>": None}))
    return {
        "this_is": (
            "the summary — every surface, every operation NAME, and the scopes each surface is "
            "KNOWN to need. Names only, never prose: it is the index of the registry, not the "
            f"registry. Read a surface's scope list together with its "
            f"'{UNKNOWN_REQUIREMENTS_KEY}': an empty or short scope list does not mean no "
            "permission is needed — where no scope was ever observed demanded, the requirement "
            f"is unrecorded, and '{UNKNOWN_REQUIREMENTS_KEY}' names the endpoints it is "
            f"unrecorded for. Why each is unknown is in {entry_point}({full_param}=True)"
            f"['{UNKNOWN_REQUIREMENTS_KEY}']."
        ),
        "one_surface": f"{entry_point}({surface_param}={example!r})",
        "everything": f"{entry_point}({full_param}=True)",
        "everything_is_this_big": (
            f"{json_bytes(payload):,} bytes of JSON. For scale, the one_surface call above "
            f"returns {json_bytes((payload.get('surfaces') or {}).get(example) or {}):,} bytes "
            "of that — ask for one surface unless you need all of them."
        ),
        "the_names_here_are_keys_there": (
            f"a name under 'surfaces' is a key of {entry_point}({full_param}=True)"
            f"['surfaces']; the same holds for " + ", ".join(f"'{k}'" for k in _ID_INDEXES)
        ),
    }


def _unknown_requirements(surface: dict) -> list:
    """*surface*'s own sorted union of the endpoint keys whose scope requirement is **unrecorded**
    — a pure fold over the per-call-site permission blocks the payload already carries.

    Why the summary carries it at all: the collapse above reduces each surface's credentials to
    two flat scope lists, and for six surfaces that leaves a bare ``"scopes": []`` under a header
    calling it *what the surface needs* — which reads as *needs no permission*, while the
    registry's own answer is *nobody has observed a scope demanded for these endpoints and this
    library does not guess*. Seven more print a complete-LOOKING list and reach unrecorded
    endpoints too, so the disclosure is **not** keyed on the list being empty: it is keyed on the
    payload having something unrecorded, which is the only reading that cannot under-report.

    **Names, never prose**, like everything else here: the values are endpoint **keys**, each an
    address into the payload's own top-level catalog of the same name, where the reason each is
    unknown is written out once. Emitted only when non-empty — a surface with nothing unrecorded
    says nothing, so the key's presence is itself information.
    """
    keys = set()
    for op in surface.get(CALL_SITES_KEY) or ():
        block = op.get(PERMISSIONS_KEY) or {}
        keys |= set(block.get(UNKNOWN_REQUIREMENTS_KEY) or ())
    return sorted(keys)


def summary(payload: dict) -> dict:
    """The summary of *payload* — a JSON-serializable ``dict``, derived and nothing else.

    Bounded at **more than 20× smaller** than what it summarises — that is the ratio the size
    guard beside this module enforces, re-measured on every run rather than recorded here, and
    the whole point of the default door. Every leaf in it is
    a leaf of *payload*: pass it a payload and the same summary comes back, pass it a
    reshaped payload and the summary reshapes with it. No literal name of a surface, an
    operation, a flag or a document appears in this module.
    """
    surfaces = {}
    for surface_id, surface in (payload.get("surfaces") or {}).items():
        credentials = surface.get("credentials") or {}
        row = {field: surface[field] for field in _SURFACE_FIELDS if field in surface}
        row[CALL_SITES_KEY] = [{"name": op["name"], "kind": op.get("kind")}
                               for op in surface.get(CALL_SITES_KEY) or ()]
        row["scopes"] = list(credentials.get("scopes") or ())
        row["optional_scopes"] = list(credentials.get("optional_scopes") or ())
        unrecorded = _unknown_requirements(surface)
        if unrecorded:
            row[UNKNOWN_REQUIREMENTS_KEY] = unrecorded
        surfaces[surface_id] = row
    out = {
        "version": payload.get("version"),
        "reading": _reading(payload),
        "counts": {
            "surfaces": len(surfaces),
            CALL_SITES_KEY: sum(len(row[CALL_SITES_KEY]) for row in surfaces.values()),
            **{key: len(payload.get(key) or ()) for key in _ID_INDEXES},
        },
        "surfaces": surfaces,
    }
    for key in _ID_INDEXES:
        out[key] = sorted(payload.get(key) or ())
    return out


def summary_bytes(payload_summary: dict) -> int:
    """The summary's own size in canonical JSON — the figure the boundedness guard reads, so
    nothing anywhere has to re-derive the serialisation to state it."""
    return json_bytes(payload_summary)


def summary_gaps(payload: dict, payload_summary=None):
    """``(omitted, phantom)`` — the bidirectional check the maintainer's condition rests on.

    * ``omitted`` — ``(surface_id, name)`` for a call site the **payload** ships and the
      summary does not list. This is the failure that matters: a consumer reading the
      default answer would conclude a shipped verb does not exist, which is exactly the
      defect the three-key split caused through 1.33.0;
    * ``phantom`` — ``(surface_id, name)`` the summary lists and the payload's surface does
      not carry: a name a caller cannot follow to a row.

    Both sides are derived — the summary from :func:`summary` when not supplied, the payload
    from itself — and the payload side is duck-typed off the emitted rows rather than off
    :data:`CALL_SITES_KEY` alone, so a call site that escapes the one collapsed key is
    ``omitted`` here instead of vanishing quietly.
    """
    payload_summary = summary(payload) if payload_summary is None else payload_summary
    omitted, phantom = [], []
    summarised = {sid: {op["name"] for op in row.get(CALL_SITES_KEY) or ()}
                  for sid, row in (payload_summary.get("surfaces") or {}).items()}
    for surface_id, surface in sorted((payload.get("surfaces") or {}).items()):
        listed = summarised.get(surface_id, set())
        shipped = set()
        for key, rows in sorted(surface.items()):
            if not _is_call_site_rows(rows):
                continue
            shipped |= {row["name"] for row in rows}
        omitted += [(surface_id, name) for name in sorted(shipped - listed)]
        phantom += [(surface_id, name) for name in sorted(listed - shipped)]
    for surface_id in sorted(set(summarised) - set(payload.get("surfaces") or {})):
        phantom += [(surface_id, name) for name in sorted(summarised[surface_id])]
    return omitted, phantom


def _is_call_site_rows(value):
    """Duck-typed recognition of a list of projected call-site rows — a ``name`` plus the
    ``projected_from`` that says which code it came out of.

    The same two-independent-derivations discipline
    :func:`larkdocio.permissions.projection_gaps` is built on: recognising the rows by their
    own shape rather than by the key they sit under is what makes :func:`summary_gaps` a
    check instead of a comparison of a thing with itself.
    """
    return (isinstance(value, list) and bool(value)
            and all(isinstance(row, dict) and "name" in row and "projected_from" in row
                    for row in value))
