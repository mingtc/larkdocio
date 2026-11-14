"""larkdocio.base.date_zone — **the one policy** about Base dates and time zones (LD-463).

This module exists because the library used to tell two different stories about the same fact.
The **write** side refused to convert a date-like object *because every conversion needs a zone
it cannot know* (correct), while the **read** side quietly substituted ``UTC`` to turn a stored
integer into a calendar date (an assumption nobody had measured) — and the documented route to
the answer, ``get_app().time_zone``, came back ``None``. Date-only values written and read back
could each come back one calendar day early, with nothing said.

**The measurement this policy is derived from** — probe ``ld463-01-date-only-zone``, whose
capture lives **in the source repository** and not in the wheel
(``tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json``; its written verdict was retired
on 2026-09-18, so the findings are stated here in full):

* **Lark stores the ms-epoch verbatim** — ``stored_equals_sent`` for 21 of 21 records, across a
  month boundary, a year boundary and three midnight conventions. A stored Base date therefore
  carries **no calendar date at all**: the same integer is two different dates under two zones
  (``1772294400000`` is ``2026/03/01`` in ``Asia/Singapore`` and ``2026/02/28`` in ``UTC``).
* **The server has a day zone even when the app payload does not state one.** Twelve records at
  two-hourly steps across one UTC day, filtered by the server's own ``is ["Today"]``, matched at
  00…14 UTC and not at 16…22 — the server's day rolls over at **16:00 UTC** (UTC+8) for the
  tenant measured. That is a measurement **on one tenant**, so it is recorded here as evidence
  and is deliberately **not** a constant this library renders from: it falsifies ``UTC`` as a
  silent default without licensing a different silent default.
* **``POST /bitable/v1/apps`` accepts ``time_zone``**, echoes it, and ``GET …/apps/{app}`` reads
  it back; a Base born in the Lark product already carries one. The ``None`` was **this
  library's own create** omitting the key — not Lark withholding an answer.

**What follows, and it is one sentence long in three places** — :data:`POLICY`.

Nothing here reads the host clock, the host locale or the host zone: rendering stays a pure
function of ``(value, date_formatter, time_zone)``, which is what makes two offline conversions
of one payload byte-identical.
"""
import datetime
from dataclasses import dataclass
from typing import Optional

#: **THE policy.** Authored once, here; the read side, the write side, the schema client and the
#: plan all reference this module rather than restating it.
POLICY = (
    "A Lark Base date value is an instant — milliseconds since the epoch — and not a calendar "
    "date. The calendar date is manufactured at render time out of a time zone, so the same "
    "stored value is two different dates under two zones. Therefore: the WRITE side takes a "
    "ms-epoch integer and converts no date-like object, because every conversion would need a "
    "zone it cannot know; the zone is DECLARED once, at the only place Lark accepts it — the "
    "Base's create; and the READ side renders in the zone the Base declares, falling back to "
    "UTC and DISCLOSING that it did so — for a Base that declares none, AND for a Base that "
    "declares one this machine has no tz database to load."
)

#: The write side's half of :data:`POLICY`, in the words the schema client and the plan cite.
CREATE_IS_WHERE_A_ZONE_IS_DECLARED = (
    "A Base's time zone is declared when the Base is created — `POST /bitable/v1/apps` takes "
    "`time_zone` and every later read of that Base reports it. Nothing else on the app payload "
    "carries a zone, and no other write route sets one."
)

#: The zone the read side falls back to when a Base declares none. It is **UTC** rather than a
#: measured offset on purpose: a fixed zone keeps rendering a pure function of
#: ``(value, date_formatter, time_zone)``, and the *assumption* is disclosed rather than tuned.
ASSUMED_ZONE = "UTC"

#: What a consumer is told when the zone was assumed. Plain language: this reaches a caller.
ASSUMED_DISCLOSURE = (
    "This Base declares no time_zone, so its date values were rendered in UTC. A Lark date is "
    "stored as an instant rather than a calendar date, and Lark decides which calendar day that "
    "instant falls on using the Base's own zone — which this Base does not report. A value "
    "authored as midnight in a zone ahead of UTC therefore renders one calendar day early. "
    "Declare the zone when the Base is created to remove the assumption."
)


#: What a consumer is told when the Base DECLARED a zone and this host could not load it —
#: **a second, different assumption from** :data:`ASSUMED_DISCLOSURE`, and the one LD-659 found
#: undisclosed. ``{zone}`` is the zone that was asked for.
#:
#: The defect it closes: ``ZoneInfo`` raises ``ZoneInfoNotFoundError`` where the tz database is
#: absent (a slim container; Windows without the ``tzdata`` package) or the name is unknown, the
#: read side caught that and rendered in UTC, and the disclosure keyed on ``declared`` — which
#: was still ``True``. So every date in the Base was converted in the **wrong zone** and the
#: result reported the zone it had been *asked* for. Executed on ``develop``: the fallback fired
#: and the disclosure did not change.
#:
#: **Adding ``tzdata`` as a runtime dependency is a separate decision** (LD-664) and is not what
#: this fixes: disclosing the fallback is right whether or not the dependency is ever added.
UNAVAILABLE_DISCLOSURE = (
    "This Base declares the time zone {zone}, but this machine could not load it — either the "
    "tz database is not installed here (a slim container, or Windows without the `tzdata` "
    "package) or that name is not in it. The date values above were therefore rendered in "
    f"{ASSUMED_ZONE}, NOT in {{zone}}, so a value near midnight can show the wrong calendar "
    "day. Install the tz database on this machine (`pip install tzdata`) and re-read to get "
    "the zone the Base actually declares."
)


def load_zone(name: Optional[str]):
    """The :class:`datetime.tzinfo` for ``name``, or ``None`` when this host cannot load it.

    **The one place a zone name becomes a zone**, so the rendering and the disclosure cannot
    reach two different conclusions — which is exactly what went wrong: ``cells._zone`` decided
    to fall back to UTC and :func:`resolve_zone` decided what to disclose, independently, and
    only one of them knew.

    :data:`ASSUMED_ZONE` is answered from :mod:`datetime` rather than from ``zoneinfo``, which
    is what makes the fallback total: on a host with no tz database, ``ZoneInfo("UTC")`` raises
    too, and a fallback that can itself fail is not a fallback.
    """
    if not name or name == ASSUMED_ZONE:
        return datetime.timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:            # no tz database on this host, or a name it does not carry
        return None


@dataclass(frozen=True)
class ZoneProvenance:
    """Where the zone a date was rendered in came from.

    ``declared`` is the whole point: a zone the Base stated and a zone this library assumed are
    two different facts, and only the second one needs saying out loud.

    There are **two** ways this library ends up choosing the zone, and they are different facts
    too, so they are reported separately: the Base declared none (``declared`` is ``False``), or
    the Base declared one this host cannot load (``declared`` is ``True`` and ``requested``
    names it). :attr:`assumed` is the question a caller actually asks — *did larkdocio pick this
    zone?* — and it is ``True`` for both.
    """

    zone: str
    declared: bool
    disclosure: Optional[str] = None
    #: The zone the Base declared, when it could not be used. ``None`` in every other case,
    #: including the ordinary success — a field that always had a value could not distinguish
    #: "asked for and got" from "asked for and did not get".
    requested: Optional[str] = None

    @property
    def assumed(self) -> bool:
        """Did this library choose :attr:`zone` rather than the Base's declaration governing?

        ``not declared`` alone was the old answer and it is the defect: a declared zone this
        host could not load is just as much an assumption as no declaration at all, and it is
        the more dangerous one, because the caller believes a zone was honoured.
        """
        return not self.declared or self.requested is not None


def resolve_zone(time_zone: Optional[str]) -> ZoneProvenance:
    """The app's ``time_zone`` → the zone to render in, plus how that zone was arrived at.

    A missing zone has two spellings on the wire — an **absent key** (a Base this library
    created before this release; a docx-born embedded Base) and an **empty value** — and they
    are one fact, so both resolve to the assumed zone with its disclosure attached.

    A zone the Base **did** declare is returned only when this host can actually load it
    (:func:`load_zone`); otherwise the answer is the assumed zone, with the declared name in
    ``requested`` and :data:`UNAVAILABLE_DISCLOSURE` attached. ``zone`` is therefore always the
    zone the dates were **really** rendered in, never the one that was hoped for.
    """
    if not time_zone:
        return ZoneProvenance(zone=ASSUMED_ZONE, declared=False, disclosure=ASSUMED_DISCLOSURE)
    if load_zone(time_zone) is None:
        return ZoneProvenance(
            zone=ASSUMED_ZONE,
            declared=True,
            disclosure=UNAVAILABLE_DISCLOSURE.format(zone=time_zone),
            requested=time_zone,
        )
    return ZoneProvenance(zone=time_zone, declared=True, disclosure=None)


def zone_disclosure(time_zone: Optional[str]) -> Optional[str]:
    """The disclosure when the zone had to be assumed, else ``None``.

    Which sentence depends on WHY it was assumed: :data:`ASSUMED_DISCLOSURE` when the Base
    declared no zone, :data:`UNAVAILABLE_DISCLOSURE` when it declared one this host cannot load.

    ``None`` is deliberate rather than an empty string: a Base whose declared zone was honoured
    has nothing to disclose, and a disclosure that is always present is a disclosure nobody
    reads.
    """
    return resolve_zone(time_zone).disclosure
