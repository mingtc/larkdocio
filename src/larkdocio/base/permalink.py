"""larkdocio.base.permalink — a record you can link to: :func:`record_permalink`.

The single sharpest ask on the deep-link card — *"link me straight to this record"* — is the
one Lark actually supports, and it is a **fetch**, not a mint: a Base record's permalink is
**server-minted** and lives at ``https://<host>/record/<27ch opaque>``, an opaque token that is
not any id this library holds. What the library holds is the ``record_id``, and the address is
asked for with ``with_shared_url=true``.

**Which field carries it was MEASURED before this shipped** (read-only, against a disposable
Base):

* On the **batch** route (``records/batch_get``) the permalink arrives under ``shared_url``;
  ``record_url`` stays absent. Without the flag **neither** key is present, so the flag is
  necessary, not decorative (the flag-off control, and the record list, both carry no url).
* It is **byte-identical** to the ``record_url`` the single-record GET returns for the same id,
  and that ``record_url`` is proven **stable across sessions with a fresh bearer**. So the two
  keys are the SAME address under two names, and this address is an **address** — its measured
  shape is ``https://<host>/record/<27ch>`` with **no signature, no expiry, and no query
  parameters**, none of the marks that make a link credential-class.

**The cost is one call per :data:`~larkdocio.base.client.BATCH_GET_MAX_IDS` ids, not one per
record.** The batch route was measured to honour the flag — proven by the url actually
appearing in the response, never by a bare success code, because this endpoint family ignores
an unrecognised body key — so ``record_permalink`` batches, deduplicates and chunks exactly as
link resolution does.

**Per-selection, by construction — never a whole-table default.** :func:`record_permalink`
takes a **sequence of record ids**, never a table, a view, a snapshot or a filter. There is no
``all=True`` and no convenience that walks a table's ids for you: a caller cannot accidentally
buy a permalink for every row, because the cost that matters is also the reader's attention.
To permalink a table's rows, read the table, choose the rows, and pass *their* ids.

**Absence is a NORMAL per-id outcome, never an error and never a bare ``None``.** Lark's own
answer already partitions the ask three ways — ``records`` (found), ``absent_record_ids`` (no
such record) and ``forbidden_record_ids`` (not permitted) — and a found record may itself carry
no permalink. Each id gets a typed :class:`RecordPermalink` naming exactly which of those
happened; the vocabulary is authored once, below. The model is the link resolver's
``resolved / dangling / unresolvable`` (:mod:`larkdocio.base.link_resolution`) — **cited, not
copied**: this surface's outcomes are its own, because "the linked record was deleted" and "you
asked for a record you cannot see" are different facts.

**READ-only.** This reaches ``records/batch_get`` on the READ client and writes nothing.
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

#: The permalink was fetched: this record carries a stable ``…/record/<opaque>`` address.
PERMALINK_RESOLVED = "resolved"
#: The record was read, but Lark returned no permalink for it (the field absent or empty). An
#: ordinary state, not a failure to read — reported so a caller never reads a blank as an error.
PERMALINK_UNMINTED = "unminted"
#: No such record: the id came back in ``absent_record_ids``. The record does not exist in this
#: table (deleted, or never there) — so there is no address to fetch.
PERMALINK_ABSENT = "absent"
#: The read was refused for this id: it came back in ``forbidden_record_ids``. Lark would not
#: hand the record over — a permission fact about the id, inside an otherwise ``code:0`` body.
PERMALINK_FORBIDDEN = "forbidden"

#: Every per-id outcome, exhaustively.
PERMALINK_STATES: Tuple[str, ...] = (
    PERMALINK_RESOLVED, PERMALINK_UNMINTED, PERMALINK_ABSENT, PERMALINK_FORBIDDEN,
)

#: What each outcome means, in a caller's words — so a consumer never has to look up a slug.
STATE_MEANINGS = {
    PERMALINK_RESOLVED: (
        "A stable per-record permalink was fetched. It is an address of the form "
        "https://<host>/record/<opaque>, and it has been read twice: proven byte-identical "
        "across sessions on the same day (2026-08-07/08), then re-read byte-identical a week "
        "later (2026-08-15) — five links, five identical at seven and eight days, on one "
        "tenant, through this same record_permalink / records/batch_get read, with the "
        "records intact throughout. So the address is measured durable at week scale and "
        "nothing further: beyond that week, on another tenant, or once a record is deleted, "
        "durability is unmeasured, so no permanence is claimed — and a durable address is no "
        "promise the content behind it is still fetchable (attachment permalinks came back "
        "byte-identical while a download of their bytes answered HTTP 404, empty body)."
    ),
    PERMALINK_UNMINTED: (
        "The record was read, but Lark returned no permalink for it (the field absent or "
        "empty). This is a value the record does not have, not a failure to read it — no "
        "address is claimed, and nothing is raised."
    ),
    PERMALINK_ABSENT: (
        "No such record in this table: Lark reported the id in absent_record_ids inside an "
        "otherwise successful read. The record does not exist (deleted, or never there), so "
        "there is no address to fetch."
    ),
    PERMALINK_FORBIDDEN: (
        "The read was refused for this id: Lark reported it in forbidden_record_ids. That is "
        "a permission fact about the id — the record may well exist — and no claim is made "
        "about its address."
    ),
}


@dataclass(frozen=True)
class RecordPermalink:
    """One record id, and what asking for its permalink produced."""

    table_id: str
    record_id: str
    state: str
    #: The permalink, present **only** for :data:`PERMALINK_RESOLVED`; ``None`` otherwise —
    #: and ``None`` here means exactly one thing (no address), because *which* not-an-address
    #: it is lives in :attr:`state`, never overloaded onto this field.
    url: Optional[str] = None

    @property
    def resolved(self) -> bool:
        """``True`` only when a permalink was fetched."""
        return self.state == PERMALINK_RESOLVED

    @property
    def note(self) -> str:
        return STATE_MEANINGS[self.state]


def _permalink_of(record) -> Optional[str]:
    """The permalink a returned record carries, route-agnostic. On the batch route it is
    ``shared_url`` (measured, LD-345); the single-record GET puts the same address in
    ``record_url``. Either is the ``…/record/<opaque>`` address; whichever is populated is it."""
    for attr in ("shared_url", "record_url"):
        value = getattr(record, attr, None)
        if value:
            return value
    return None


def _checked_ids(record_ids) -> List[str]:
    """The ids to fetch, or a refusal. Guards AC3 **by construction**: a table-shaped input
    cannot be expressed here, and a bare string is refused rather than iterated character by
    character (the classic ``for c in "rec…"`` footgun)."""
    if isinstance(record_ids, str):
        raise TypeError(
            "record_permalink takes a SEQUENCE of record ids, not a single string. Pass "
            "[record_id] for one. (A bare string would iterate character by character — "
            "refused rather than silently fetching one permalink per letter.)")
    try:
        ids = list(record_ids)
    except TypeError:
        raise TypeError(
            "record_permalink takes a sequence of record ids — never a table, a view, a "
            "snapshot or a filter. There is no whole-table default: read the table, choose "
            "the rows, and pass their record ids.")
    for rid in ids:
        if not isinstance(rid, str):
            raise TypeError(
                f"each record id must be a string; got {type(rid).__name__}. "
                "record_permalink permalinks NAMED records, never a table.")
    return ids


def _dedup(ids: Sequence[str]) -> List[str]:
    """Preserve first-seen order, drop repeats — a permalink is a property of the id, so asking
    twice buys nothing and should cost nothing."""
    seen = set()
    out = []
    for rid in ids:
        if rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _chunks(ids: Sequence[str], size: int):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def record_permalink(
    app_token: str,
    table_id: str,
    record_ids,
    *,
    client=None,
    domain: Optional[str] = None,
) -> Tuple[RecordPermalink, ...]:
    """Fetch the stable per-record permalink for each of ``record_ids`` in one table.

    ``record_ids`` is a **sequence of record ids** — never a table, view, snapshot or filter,
    and there is no whole-table default (enforced by :func:`_checked_ids`). The result is
    one :class:`RecordPermalink` per **distinct** id, in first-seen order, each typed
    :data:`PERMALINK_RESOLVED` / :data:`PERMALINK_UNMINTED` / :data:`PERMALINK_ABSENT` /
    :data:`PERMALINK_FORBIDDEN` — absence is a normal outcome, never a raised error and never a
    bare ``None`` standing in for three different things.

    **Cost: one ``records/batch_get`` call per**
    :data:`~larkdocio.base.client.BATCH_GET_MAX_IDS` **ids** (measured — the batch route honours
    ``with_shared_url``), reusing that method's own chunking ceiling. An empty ask costs
    zero calls and returns an empty result — Lark refuses ``record_ids: []`` and this library
    never sends one.

    ``client`` is injectable — the default builds a read-only
    :class:`~larkdocio.base.client.BaseReadClient` from the READ credentials; ``domain`` selects
    the API domain when one is built. Nothing here writes to any Base.
    """
    from larkdocio.base.client import BATCH_GET_MAX_IDS

    ids = _dedup(_checked_ids(record_ids))
    if not ids:
        return ()

    if client is None:
        from larkdocio.base.client import BaseReadClient
        client = (BaseReadClient.from_read_credentials(domain) if domain
                  else BaseReadClient.from_read_credentials())

    by_id = {}
    for chunk in _chunks(ids, BATCH_GET_MAX_IDS):
        answer = client.batch_get_records(
            app_token, table_id, chunk, with_shared_url=True)
        for record in (getattr(answer, "records", None) or ()):
            rid = getattr(record, "record_id", None)
            url = _permalink_of(record)
            by_id[rid] = RecordPermalink(
                table_id=table_id, record_id=rid,
                state=PERMALINK_RESOLVED if url else PERMALINK_UNMINTED, url=url)
        for rid in (getattr(answer, "absent_record_ids", None) or ()):
            by_id.setdefault(rid, RecordPermalink(
                table_id=table_id, record_id=rid, state=PERMALINK_ABSENT))
        for rid in (getattr(answer, "forbidden_record_ids", None) or ()):
            by_id[rid] = RecordPermalink(
                table_id=table_id, record_id=rid, state=PERMALINK_FORBIDDEN)

    # In the asked order; an id Lark returned in none of the three lists is reported ABSENT —
    # Lark did not hand it back as found, and absent is the outcome that claims no address
    # without claiming a permission fact.
    return tuple(
        by_id.get(rid, RecordPermalink(
            table_id=table_id, record_id=rid, state=PERMALINK_ABSENT))
        for rid in ids)


__all__ = [
    "PERMALINK_ABSENT",
    "PERMALINK_FORBIDDEN",
    "PERMALINK_RESOLVED",
    "PERMALINK_STATES",
    "PERMALINK_UNMINTED",
    "RecordPermalink",
    "STATE_MEANINGS",
    "record_permalink",
]
