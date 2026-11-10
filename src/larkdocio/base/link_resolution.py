"""larkdocio.base.link_resolution — following a Base link to its target, opt-in.

L1 renders a link cell's **record ids** and stops there. This module is the opt-in rung that
follows them: it reads the linked records and renders each one as its target table's
**primary field**. It is **off by default**, and off means *byte-identical* — the
opt-in deep-read discipline the Sheets type-30 read and the embedded-Base bridge already
apply. A new capability never changes an existing consumer's bytes.

**The display-field policy, settled here.** A link's target is a whole record; something has
to stand for it. The answer is the **primary field the target table's own schema designates**
(``is_primary``), read from that table's ``GET …/fields`` — never "the first column", which
happens to be right on most tables and is wrong exactly where it matters. A target table whose
schema designates no primary field has no display policy at all, so its ids resolve to the
honest third state rather than to a guessed column, and **no call is spent** on them.

**The call count is a function of TARGET TABLES, never of cells.** Every id wanted from one
target table is fetched in one ``POST …/records/batch_get``, deduplicated across cells and
across rows and chunked at :data:`~larkdocio.base.client.BATCH_GET_MAX_IDS`. This is a
*gentleness* property before it is a performance one: the Base client paces at ≥1.2 s and rate
limits are deliberately unprobed, so a resolver whose call count followed the cell count would
be a rate-limit incident waiting to happen. A target table the caller has already read hands
its schema in through ``known_schemas`` and costs no field call at all.

**A dangling link is a NORMAL case, not an error.** Lark maintains referential integrity for
``DuplexLink`` and **not** for ``SingleLink`` (``p0-2-07``), so a link cell routinely points at
a record that has been deleted. The batch endpoint reports that *per id*, inside a ``code:0``
body, in its own ``absent_record_ids`` list — and where the whole call answers
``1254043 RecordIdNotFound`` instead, that is caught here rather than allowed to fail a read.
The per-cell answer is typed — :data:`LINK_RESOLVED` / :data:`LINK_DANGLING` /
:data:`LINK_UNRESOLVABLE` — and the third state is the one that carries **no claim in either
direction**, the same discipline :mod:`larkdocio.base.referential` applies at column level: a
confident wrong answer about whether data still exists is worse than an admitted unknown. So a
whole chunk that raises ``1254043`` names the *family* and not the id, and every id in it reads
unresolvable — unless the chunk held exactly one id, which names itself.

**A dangling TARGET TABLE is a normal case too — and it is the one this flag exists for.**
A deleted table leaves its link columns still carrying its id, so following one asks a table
that is gone for its schema and then for its records. Both calls answer ``1254041`` (or its
malformed-id and trashed-Base neighbours), and **neither is allowed to fail the read**: every
id wanted from an unreadable target reads unresolvable, the next target is still asked, and the
document still comes back. A resolver that crashed on exactly the broken reference it was
switched on to diagnose would be useful only on the Bases that did not need it. What is *not*
swallowed is anything outside those two families — a scope denial is a real failure and reading
it as a marker would hide a broken read behind plausible-looking output. The dead target is
asked about **once**: the answer is about the table, so the remaining chunks are typed rather
than re-asked, and an answer about the *Base* stops the calling altogether.

**One path for both link kinds.** The two link types are recognised through
:func:`larkdocio.base.referential.is_link_column` — LD-267's storage-type reading, not a second
copy — and nothing below branches on which kind a column is. What differs is only what the
resolver *finds*: a ``DuplexLink``'s ids are referentially maintained, a ``SingleLink``'s may
dangle. The mirror direction is a link cell like any other and resolves the same way.

**Nothing here repairs anything.** No dangling id is deleted, no cell is rewritten to ``[]``,
and there is no *"clean up dangling links"* verb. Rendering a broken reference honestly is the
product. Nothing here writes at all: the whole module reaches exactly two read methods.

**Determinism is SAME-RUN, and the scoping is honest.** Two resolutions of an unchanged Base
in one run are byte-identical — the ids are asked for in encounter order, never in set order.
But resolution reads a **second table**, so a target record renamed between runs legitimately
changes the output, exactly as the reader's live @mention resolution does
(PROJECT.md, in the dev repo, § Quality bar). Cross-time byte-identity is **not** claimed and cannot be.
"""
from dataclasses import dataclass, field as _dataclass_field
from typing import Dict, Mapping, Optional, Sequence, Tuple

from larkdocio.base.client import BATCH_GET_MAX_IDS
from larkdocio.base.referential import is_link_column
from larkdocio.errors import LarkAPIError

#: The linked record was read and its primary field is what the cell renders.
LINK_RESOLVED = "resolved"
#: The linked record is gone — Lark reported the id absent, or named the not-found family for
#: a request that could only have been about this id.
LINK_DANGLING = "dangling"
#: Nothing is claimed. The target could not be read, or the answer did not say which id it was
#: about, or the target table designates no primary field to stand for a record.
LINK_UNRESOLVABLE = "unresolvable"

#: Every per-id outcome, exhaustively. Three, not two — the third is the honest one.
LINK_RESOLUTION_STATES: Tuple[str, ...] = (
    LINK_RESOLVED, LINK_DANGLING, LINK_UNRESOLVABLE,
)

#: What each outcome means, in a caller's words — so a consumer never has to look up a slug to
#: know what was and was not claimed.
STATE_MEANINGS = {
    LINK_RESOLVED: (
        "The linked record was read and its target table's primary field is what this cell "
        "renders. An empty primary field renders empty: that is the record's own value, not a "
        "failure to read it."
    ),
    LINK_DANGLING: (
        "The linked record no longer exists. Lark reported the id absent from the target "
        "table inside an otherwise successful read, which is the ordinary state of a "
        "SingleLink whose target record was deleted — Lark maintains referential integrity "
        "for the symmetric link kind and not for this one."
    ),
    LINK_UNRESOLVABLE: (
        "Whether this linked record still exists cannot be told from what came back: the "
        "target was not readable, or the answer named the not-found family without naming "
        "which id it was about, or the target table designates no primary field for a record "
        "to be rendered as. No claim is made in either direction."
    ),
}

#: The dangling per-cell marker, in the reader's own house register
#: (``[unsupported inline: …]`` / ``[Unsupported Add-On block: …]`` / the Stage cell's
#: ``[unreadable Base cell: …]``). It carries the **record id**, so a broken reference stays
#: traceable back to the id that broke.
DANGLING_LINK_MARKER = (
    "[dangling Base link: {record_id} — the linked record no longer exists in the "
    "target table]"
)

#: The no-claim per-cell marker, same register. It says what it does **not** know.
UNRESOLVABLE_LINK_MARKER = (
    "[unresolved Base link: {record_id} — the target could not be read, so no claim is "
    "made about whether the record exists]"
)

#: Lark's own code for *no such record in this table*. Met as a matter of course by anything
#: that follows a link, which is why this module treats it as a normal case rather than a
#: failure. The taxonomy entry lives in :mod:`larkdocio.base.errors`; this is the one number
#: the resolution policy keys on.
RECORD_ID_NOT_FOUND_CODE = 1254043

#: The codes that answer about the **target table itself** rather than about a record inside
#: it. A link column whose target table has been deleted still carries that table's id, so
#: following it asks a dead table for its schema and then for its records — and **either** call
#: can answer from this family. Every id wanted from such a target reads
#: :data:`LINK_UNRESOLVABLE`: the target was not readable, so nothing is claimed in either
#: direction. **The next target is its own question** and is still asked.
TARGET_UNREADABLE_CODES: Tuple[int, ...] = (
    1254041,   # TableIdNotFound — no such table in this Base
    1254004,   # WrongTableId — the id is malformed
)

#: The same answer one level up: these are about the **Base**, so every remaining target would
#: be refused identically. Resolution stops calling at the first one and types the rest — a
#: *gentleness* property before a tidiness one, since the client paces at ≥1.2 s and re-asking
#: buys an answer already given. This is
#: :data:`larkdocio.base.disposition.SYSTEMIC_CODES`' blast-radius reading, restated for the
#: read path rather than re-derived; both sets are rows of the one taxonomy in
#: :mod:`larkdocio.base.errors`.
BASE_UNREADABLE_CODES: Tuple[int, ...] = (
    1002,      # the Base itself has been trashed
    91402,     # no Base at this app_token
)


def dangling_marker(record_id: str) -> str:
    """The exact bytes a dangling linked record renders as."""
    return DANGLING_LINK_MARKER.format(record_id=record_id)


def unresolvable_marker(record_id: str) -> str:
    """The exact bytes a linked record no claim can be made about renders as."""
    return UNRESOLVABLE_LINK_MARKER.format(record_id=record_id)


@dataclass(frozen=True)
class ResolvedLink:
    """One linked record id, and what following it produced."""

    table_id: str
    record_id: str
    state: str
    text: str

    @property
    def dangling(self) -> bool:
        """``True`` only for the outcome that says the record is gone — never for the
        unknown, which claims nothing."""
        return self.state == LINK_DANGLING

    @property
    def note(self) -> str:
        return STATE_MEANINGS[self.state]


@dataclass(frozen=True)
class LinkResolution:
    """Every linked record one read followed, plus what it cost.

    The cost is **disclosed rather than inferable**: a consumer reasoning about latency, a
    throttle budget or failure granularity needs to see how many extra calls were made and
    which tables they were made against — the same discipline the cross-table loss preview
    applies, for the same reason.
    """

    #: ``{(table_id, record_id): ResolvedLink}``.
    records: Mapping[Tuple[str, str], ResolvedLink] = _dataclass_field(default_factory=dict)
    #: How many extra API calls resolution made. Equal to what the client observed.
    api_calls: int = 0
    #: The target tables touched, in the order they were first reached.
    tables: Tuple[str, ...] = ()

    def record_for(self, table_id: str, record_id: str) -> Optional[ResolvedLink]:
        """The outcome for one linked id, or ``None`` if this resolution never saw it."""
        return self.records.get((table_id, record_id))

    def text_for(self, table_id: str, record_id: str) -> Optional[str]:
        """What one linked id renders as, or ``None`` if this resolution never saw it —
        which is a caller's cue to render the raw id, the answer L1 always gave."""
        entry = self.record_for(table_id, record_id)
        return None if entry is None else entry.text

    @property
    def dangling(self) -> Tuple[ResolvedLink, ...]:
        """Only the ids whose target record is gone. Empty is the normal case."""
        return tuple(r for r in self.records.values() if r.dangling)

    @property
    def disclosure(self) -> str:
        """The read cost, as a sentence a consumer can act on."""
        if not self.api_calls:
            return "Link resolution made no extra API calls."
        tables = ", ".join(self.tables)
        return (
            f"Link resolution made {self.api_calls} extra API call(s) against "
            f"{len(self.tables)} target table(s): {tables}. "
            f"{len(self.records)} linked record id(s) were followed, of which "
            f"{len(self.dangling)} no longer exist."
        )


def primary_field_name(fields: Sequence) -> Optional[str]:
    """The field a table's **schema designates** as its primary, by name.

    ``is_primary`` and nothing else. Position is not consulted: the primary column is first on
    most tables, which is exactly what makes a positional implementation pass every test that
    does not deliberately move it. ``None`` when the schema designates none — the caller then
    has no display policy and must not invent one.
    """
    for field in fields or ():
        if getattr(field, "is_primary", False):
            return getattr(field, "field_name", "") or None
    return None


def _link_ids(value):
    """The record ids in a link cell — ``()`` for both empty forms and for a non-link shape.

    The two empty forms (``{"link_record_ids": null}`` never set, ``{"link_record_ids": []}``
    after a target delete) are an already-settled contract and are not re-pinned here; all
    this needs of them is that neither has anything to resolve.
    """
    if not isinstance(value, dict):
        return ()
    ids = value.get("link_record_ids")
    if not ids or not isinstance(ids, (list, tuple)):
        return ()
    return tuple(str(i) for i in ids if i)


def _record_values(record) -> dict:
    if isinstance(record, dict):
        return record.get("fields") or {}
    return getattr(record, "fields", None) or {}


def target_table_of(field) -> Optional[str]:
    """The table a link column points at, from **its own** ``property.table_id``.

    Never inferred from a name, a cell, or the order of the Base's tables. ``None`` for a
    column that is not a link, or a link whose configuration does not carry the id.
    """
    if not is_link_column(field):
        return None
    prop = getattr(field, "property", None)
    if prop is None:
        return None
    # Read by name off whichever shape the field arrived in — the SDK-typed object the client
    # returns, the bridged dict the structured read carries, or a capture's raw dict. The
    # equivalence is LD-267's, restated here rather than re-derived: on the typed object an
    # undeclared key is simply absent, which reads identically to the key being ``None``.
    table_id = (prop.get("table_id") if isinstance(prop, Mapping)
                else getattr(prop, "table_id", None))
    return table_id if isinstance(table_id, str) and table_id else None


def needed_record_ids(fields: Sequence, records: Sequence) -> Dict[str, Tuple[str, ...]]:
    """``{target_table_id: (record_id, …)}`` for one table's fields and records.

    **Pure, and it costs no call.** Deduplicated across cells and across rows, in encounter
    order — the order is part of the determinism claim, so a set is never what comes out.
    """
    wanted: Dict[str, dict] = {}
    for record in records or ():
        values = _record_values(record)
        for spec in fields or ():
            target = target_table_of(spec)
            if target is None:
                continue
            name = getattr(spec, "field_name", "")
            if name not in values:
                continue
            for record_id in _link_ids(values[name]):
                wanted.setdefault(target, {})[record_id] = None
    return {table: tuple(ids) for table, ids in wanted.items()}


def _chunks(ids: Sequence[str]):
    size = max(1, int(BATCH_GET_MAX_IDS))
    for start in range(0, len(ids), size):
        yield tuple(ids[start:start + size])


def _rendered_primary(record, primary: str, specs_by_name, context) -> str:
    """One target record → the text its primary field renders as.

    Rendered through the **one** cell registry, with a context carrying **no resolution**: a
    resolved link's own display value is never itself resolved, so following a link cannot
    recurse into another read.
    """
    from larkdocio.base.cells import RenderContext, render_absent, render_cell

    spec = specs_by_name.get(primary)
    if spec is None:
        return ""
    plain = RenderContext(time_zone=getattr(context, "time_zone", None),
                          renderer=getattr(context, "renderer", None))
    values = _record_values(record)
    if primary not in values:
        return render_absent(spec, context=plain)
    return render_cell(values[primary], spec, context=plain)


def _record_id_of(record) -> str:
    if isinstance(record, dict):
        return record.get("record_id") or ""
    return getattr(record, "record_id", "") or ""


def _mark_unresolvable(resolved, target, ids) -> None:
    """Type every id of one target the honest third state — without overwriting an answer.

    ``setdefault`` and not assignment: a chunk that already came back keeps whatever it said,
    so a target that fails **part** way through does not lose the answers it had already
    earned.
    """
    for record_id in ids:
        resolved.setdefault((target, record_id), ResolvedLink(
            table_id=target, record_id=record_id, state=LINK_UNRESOLVABLE,
            text=unresolvable_marker(record_id)))


def resolve_links(
    *,
    client,
    app_token: str,
    sources: Sequence[Tuple[str, Sequence, Sequence]],
    known_schemas: Optional[Mapping[str, Sequence]] = None,
    context=None,
) -> LinkResolution:
    """Follow every link in ``sources`` and answer what each linked id renders as.

    ``sources`` is ``[(table_id, fields, records), …]`` — the tables a read already holds, in
    the order it holds them. ``known_schemas`` is ``{table_id: fields}`` for tables whose
    schema is already in hand; a target found there costs **no** field call.

    The traffic this makes is a function of the **target tables**: at most one field read per
    target table not already known, plus one ``records/batch_get`` per
    :data:`~larkdocio.base.client.BATCH_GET_MAX_IDS`-sized chunk of ids wanted from it. It is
    never a function of how many cells or rows those ids came from.
    """
    from larkdocio.base.cells import RenderContext
    from larkdocio.base.table import field_spec

    wanted: Dict[str, dict] = {}
    for _table_id, fields, records in sources or ():
        for target, ids in needed_record_ids(fields, records).items():
            for record_id in ids:
                wanted.setdefault(target, {})[record_id] = None

    schemas = dict(known_schemas or {})
    render_context = context if context is not None else RenderContext()
    calls_before = getattr(client, "api_calls", 0)
    resolved: Dict[Tuple[str, str], ResolvedLink] = {}
    touched = []

    base_is_gone = False
    for target, id_map in wanted.items():
        ids = tuple(id_map)
        if not ids:
            continue
        if base_is_gone:
            # The Base itself answered gone. Every remaining target is the same answer, so it
            # is typed rather than asked about again.
            _mark_unresolvable(resolved, target, ids)
            continue
        fields = schemas.get(target)
        if fields is None:
            try:
                fields = client.list_fields(app_token, target)
            except LarkAPIError as error:
                # **A target table that is GONE is the state this module exists to report**,
                # not a failure to escape through it: the schema call meets it exactly as the
                # record call below meets a deleted record, and answers the same honest third
                # state. Anything outside the two families still raises — swallowing a scope
                # denial would hide a broken read behind plausible-looking markers.
                if error.code not in TARGET_UNREADABLE_CODES + BASE_UNREADABLE_CODES:
                    raise
                base_is_gone = error.code in BASE_UNREADABLE_CODES
                _mark_unresolvable(resolved, target, ids)
                continue
            schemas[target] = fields
        specs = [field_spec(f) for f in fields or ()]
        primary = primary_field_name(specs)
        if primary is None:
            # No display policy is derivable, so there is nothing a call could buy.
            _mark_unresolvable(resolved, target, ids)
            continue
        specs_by_name = {spec.field_name: spec for spec in specs}
        touched.append(target)
        for chunk in _chunks(ids):
            try:
                body = client.batch_get_records(app_token, target, list(chunk))
            except LarkAPIError as error:
                if error.code in TARGET_UNREADABLE_CODES + BASE_UNREADABLE_CODES:
                    # The other half of the same seam. A caller that handed this target's
                    # schema in (``known_schemas``) never made the field call, so this is
                    # where a dead table is first met; and the answer is about the TABLE, so
                    # the remaining chunks would be told the same thing at ≥1.2 s each.
                    base_is_gone = error.code in BASE_UNREADABLE_CODES
                    _mark_unresolvable(resolved, target, ids)
                    break
                if error.code != RECORD_ID_NOT_FOUND_CODE:
                    # Only the not-found family is normal here. A scope denial or a bad token
                    # is a real failure, and swallowing it would hide a broken read behind
                    # plausible-looking markers.
                    raise
                # Lark named the family, not the id — unless the chunk held exactly one, which
                # names itself. Re-asking per id would be the N+1 this module exists to avoid.
                state = LINK_DANGLING if len(chunk) == 1 else LINK_UNRESOLVABLE
                for record_id in chunk:
                    resolved[(target, record_id)] = ResolvedLink(
                        table_id=target, record_id=record_id, state=state,
                        text=(dangling_marker(record_id) if state == LINK_DANGLING
                              else unresolvable_marker(record_id)))
                continue
            absent = {str(i) for i in (getattr(body, "absent_record_ids", None) or ())}
            forbidden = {str(i) for i in (getattr(body, "forbidden_record_ids", None) or ())}
            seen = set()
            for record in (getattr(body, "records", None) or ()):
                record_id = _record_id_of(record)
                if not record_id:
                    continue
                seen.add(record_id)
                resolved[(target, record_id)] = ResolvedLink(
                    table_id=target, record_id=record_id, state=LINK_RESOLVED,
                    text=_rendered_primary(record, primary, specs_by_name, render_context))
            for record_id in chunk:
                if record_id in seen:
                    continue
                # An id Lark called absent is gone; an id it refused, or simply did not
                # mention, is an unknown this module refuses to turn into a claim.
                dangling = record_id in absent and record_id not in forbidden
                resolved[(target, record_id)] = ResolvedLink(
                    table_id=target, record_id=record_id,
                    state=LINK_DANGLING if dangling else LINK_UNRESOLVABLE,
                    text=(dangling_marker(record_id) if dangling
                          else unresolvable_marker(record_id)))

    return LinkResolution(
        records=resolved,
        api_calls=getattr(client, "api_calls", 0) - calls_before,
        tables=tuple(touched),
    )


__all__ = [
    "BASE_UNREADABLE_CODES",
    "DANGLING_LINK_MARKER",
    "LINK_DANGLING",
    "LINK_RESOLUTION_STATES",
    "LINK_RESOLVED",
    "LINK_UNRESOLVABLE",
    "LinkResolution",
    "RECORD_ID_NOT_FOUND_CODE",
    "ResolvedLink",
    "STATE_MEANINGS",
    "TARGET_UNREADABLE_CODES",
    "UNRESOLVABLE_LINK_MARKER",
    "dangling_marker",
    "needed_record_ids",
    "primary_field_name",
    "resolve_links",
    "target_table_of",
    "unresolvable_marker",
]
