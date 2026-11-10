"""name → ``open_id``: exactly one user, or a typed refusal. Never a guess, never a top hit.

**The shape of the answer.** :func:`resolve_user` returns one :class:`NameLookup`, and that
type is built so the dangerous answers cannot be expressed:

* a lookup carries **either** a resolved :class:`UserRef` **or** a
  :class:`~larkdocio.write.model.refusal.Refusal` — never both, never neither;
* it carries a :class:`Partiality` **always**, as a constructor argument with no default, so
  there is no way to say *"resolved"* without also saying what (if anything) was incomplete.
  A ``code: 0`` body can carry ``employees[]`` **and** ``abnormals[]`` at the same time — a
  partial answer wearing the costume of a complete one — and the whole reason this surface was
  written the way it was is that the same class of silent incompleteness once presented a
  field-level scope gap as a data-range problem for five days;
* an id Lark named in ``abnormals`` can never be the resolved user: the constructor raises.

**Matching is CLIENT-SIDE and exact.** The server's own match semantics are recorded in
:mod:`larkdocio.contacts` (the package docstring) as **observed**, not assumed. Whatever they
turn out to be, the *contract* is enforced here over the returned set with casefold +
whitespace-normalized **exact** equality and nothing more: no fuzzy distance, no phonetics, no
ranking, no *"take the top hit"*. A similarity threshold is a tuning knob, and a deterministic
library whose answers depend on a magic number is not one.

**A denial is raised, not returned.** *"I could not look"* and *"I looked and nobody matched"*
are different facts, and this module keeps them structurally different: a missing scope reaches
the caller as :class:`~larkdocio.errors.LarkPermissionError` carrying a
:class:`~larkdocio.permissions.PermissionDenial` (the shipped, uniform shape — this surface
mints no refusal reason of its own), while *"the lookup ran and matched nobody"* is a returned
``NameLookup`` whose refusal is ``NOT_FOUND``. A caller branches on the type. The lookup never
falls back to enumeration and never widens a scope; a grant is a Lark console action.
"""
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Sequence, Tuple

from larkdocio.write.model.refusal import Refusal

#: The fields of an ``employees[]`` entry this surface reads. Kept as one tuple so the read is
#: auditable: the search asks for ``base_info`` and looks at exactly two things inside it.
READ_FIELDS = ("base_info.employee_id", "base_info.name.name")


@dataclass(frozen=True)
class UserRef:
    """One resolved user: the ``open_id`` a caller can act on, and the name it was matched by.

    ``display_name`` is the directory's own default display string for that id — carried so a
    caller can echo *which* person they got without a second call. It is never used to make the
    match decision more permissive than exact.
    """

    open_id: str
    display_name: str

    def to_dict(self) -> dict:
        return {"open_id": self.open_id, "display_name": self.display_name}


@dataclass(frozen=True)
class AbnormalRow:
    """One ``abnormals[]`` record, carried **verbatim** — never summarized to a boolean.

    ``row_error`` and ``field_errors`` are Lark's own numbers. They are not translated, ranked
    or thresholded here: a caller who needs to know *which field of which row* the directory
    refused gets exactly that, and a caller who only needs *"was anything incomplete"* reads
    :attr:`Partiality.is_partial`.
    """

    id: Optional[str]
    row_error: Optional[int]
    field_errors: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "row_error": self.row_error,
                "field_errors": dict(self.field_errors)}


@dataclass(frozen=True)
class Partiality:
    """What the answer did NOT cover — the typed, branchable disclosure.

    Two shapes of incompleteness, and they are the same class of problem:

    * ``abnormal_rows`` — rows Lark itself flagged, with their error codes intact;
    * ``rows_without_an_id`` — rows that came back with no id field at all. Such a row is not a
      resolved user and must never be reported as one; counting it here is what stops it from
      being dropped silently, which would be indistinguishable from it never existing.

    An empty :class:`Partiality` is a positive statement — *"the answer was complete"* — and it
    is the same object the partial case uses, so a caller reads one field either way.
    """

    abnormal_rows: Tuple[AbnormalRow, ...] = ()
    rows_without_an_id: int = 0

    def __post_init__(self):
        object.__setattr__(self, "abnormal_rows", tuple(
            row if isinstance(row, AbnormalRow) else AbnormalRow(**row)
            for row in self.abnormal_rows))

    @property
    def is_partial(self) -> bool:
        """``True`` when the directory's answer did not fully cover what it was asked."""
        return bool(self.abnormal_rows) or self.rows_without_an_id > 0

    @property
    def abnormal_ids(self) -> Tuple[str, ...]:
        return tuple(row.id for row in self.abnormal_rows if row.id)

    def detail(self) -> str:
        """One sentence a caller may relay. Empty string when the answer was complete."""
        if not self.is_partial:
            return ""
        parts = []
        if self.abnormal_rows:
            parts.append(
                f"{len(self.abnormal_rows)} row(s) came back abnormal: "
                + "; ".join(
                    f"{row.id or '<no id>'} row_error={row.row_error} "
                    f"field_errors={dict(row.field_errors)}"
                    for row in self.abnormal_rows))
        if self.rows_without_an_id:
            parts.append(
                f"{self.rows_without_an_id} row(s) carried no id field and are therefore not "
                "resolved users")
        return (" ".join(parts)
                + " This answer is PARTIAL: the rows above were not searched over.")

    def to_dict(self) -> dict:
        return {
            "is_partial": self.is_partial,
            "abnormal_rows": [row.to_dict() for row in self.abnormal_rows],
            "rows_without_an_id": self.rows_without_an_id,
            "detail": self.detail(),
        }


@dataclass(frozen=True)
class NameLookup:
    """The ONE answer type — exactly one user, or a refusal, and always the disclosure.

    ``partiality`` has **no default on purpose**: ``NameLookup(query=…, user=…)`` is a
    ``TypeError``, so a bare success object is structurally unreachable rather than merely
    discouraged.

    ``reported_count`` is ``page_response.count`` **only when the server actually sent it**.
    The GO capture carried ``has_more`` and ``page_token`` and no ``count`` key at all, so the
    field's meaning — page count or grand total — has never been observed here. It is therefore
    carried verbatim and **never interpreted**, and *how many* is derived from the returned
    rows plus ``has_more``. A refusal must never cite a field whose meaning was assumed.
    """

    query: str
    partiality: Partiality
    user: Optional[UserRef] = None
    refusal: Optional[Refusal] = None
    candidate_ids: Tuple[str, ...] = ()
    has_more: bool = False
    reported_count: Optional[int] = None

    def __post_init__(self):
        if (self.user is None) == (self.refusal is None):
            raise ValueError(
                "a NameLookup carries exactly one of `user` or `refusal` — 'resolved and "
                "refused' and 'neither' are both unrepresentable answers")
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        if self.user is not None and self.user.open_id in self.partiality.abnormal_ids:
            raise ValueError(
                f"{self.user.open_id} was reported abnormal by the directory and cannot be "
                "returned as a resolved user — a partially-failed lookup is never a clean "
                "answer")

    @property
    def resolved(self) -> bool:
        """``True`` when exactly one user matched. Read with :attr:`Partiality.is_partial`:
        an answer can be resolved AND partial, and that combination is the dangerous one."""
        return self.user is not None

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "resolved": self.resolved,
            "user": self.user.to_dict() if self.user else None,
            "refusal": None if self.refusal is None else {
                "reason": self.refusal.reason.value,
                "detail": self.refusal.detail,
                "candidate_ids": list(self.refusal.candidate_ids),
            },
            "partiality": self.partiality.to_dict(),
            "candidate_ids": list(self.candidate_ids),
            "has_more": self.has_more,
            "reported_count": self.reported_count,
        }


def normalize_name(name: str) -> str:
    """The one normalization the match rule allows: collapse whitespace, then casefold.

    ``casefold`` rather than ``lower`` because it folds the cases ``lower`` misses, and it is
    the same normalization applied to **both** sides. Nothing else happens here — no accent
    stripping, no punctuation removal, no transliteration — because each of those would make
    two different names compare equal, which is the failure mode this surface refuses.
    """
    return " ".join((name or "").split()).casefold()


def _display_names(employee) -> Tuple[str, ...]:
    """Every display string the DIRECTORY ITSELF reports for one employee.

    The default value plus each non-empty localization it sent. Widening the comparison to the
    localized forms is not fuzzy matching: they are the directory's own strings for that same
    person, compared with the same exact rule. Nothing is generated here.
    """
    name = _get(_get(_get(employee, "base_info"), "name"), "name")
    if name is None:
        return ()
    out = []
    for value in (_get(name, "default_value"),) + tuple(
            (_as_dict(_get(name, "i18n_value")) or {}).values()):
        if isinstance(value, str) and value.strip() and value not in out:
            out.append(value)
    return tuple(out)


def _as_dict(value) -> Optional[Dict]:
    if isinstance(value, dict):
        return value
    if value is None:
        return None
    return {k: v for k, v in vars(value).items() if not k.startswith("_")}


def _get(obj, key):
    """``obj[key]`` for a mapping, ``obj.key`` for an object, ``None`` otherwise. The two
    transports hand back different things and the answer must not depend on which."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _partiality_of(data, employees) -> Partiality:
    rows = tuple(
        AbnormalRow(
            id=_get(record, "id"),
            row_error=_get(record, "row_error"),
            field_errors=_as_dict(_get(record, "field_errors")) or {},
        )
        for record in (_get(data, "abnormals") or ())
    )
    missing = sum(
        1 for employee in employees
        if not _get(_get(employee, "base_info"), "employee_id"))
    return Partiality(abnormal_rows=rows, rows_without_an_id=missing)


def resolve_user(*, name: str, client=None, domain: str = "larksuite.com") -> NameLookup:
    """Resolve a display ``name`` to **exactly one** ``open_id``, or refuse in a typed way.

    ``client`` is a :class:`~larkdocio.contacts.client.ContactsSearchClient`; when omitted one
    is built from the environment's READ credentials. It is a parameter so pacing, credentials
    and the transport are all injectable, and so a caller making several lookups pays the
    limiter once rather than per call.

    Raises :class:`~larkdocio.errors.LarkPermissionError` when the tenant does not hold the
    directory-search grant — *"I could not look"*, never reported as an absence. Raises
    ``ValueError`` for an empty name, **before** any call is made: a blank query is not a
    question worth spending a request on.
    """
    if not (name or "").strip():
        raise ValueError(
            "resolve_user needs a non-empty `name`; a blank query is not a lookup")
    if client is None:
        from larkdocio.contacts.client import ContactsSearchClient

        client = ContactsSearchClient.from_read_credentials(domain)

    data = client.search_employees(name)
    employees = list(_get(data, "employees") or ())
    partiality = _partiality_of(data, employees)
    page = _get(data, "page_response")
    has_more = bool(_get(page, "has_more"))
    reported_count = _get(page, "count")

    wanted = normalize_name(name)
    abnormal = set(partiality.abnormal_ids)
    excluded = 0
    matches: list = []
    for employee in employees:
        open_id = _get(_get(employee, "base_info"), "employee_id")
        if not open_id or open_id in abnormal:
            # No id, or an id the directory itself flagged: not a resolved user. Both are
            # already counted in the disclosure; neither becomes a candidate. This is the
            # absolute half of the invariant, and it holds even when the row LOOKS fine —
            # the wire really does return a row in `employees[]` and name that same row in
            # `abnormals[]` (row_error 0, two field groups refused 2003), and certifying it
            # as a clean answer is exactly the mistake this surface exists to refuse.
            excluded += 1
            continue
        names = _display_names(employee)
        if any(normalize_name(candidate) == wanted for candidate in names):
            matches.append(UserRef(open_id=open_id, display_name=names[0] if names else ""))

    common = dict(query=name, partiality=partiality, has_more=has_more,
                  reported_count=reported_count,
                  candidate_ids=tuple(match.open_id for match in matches))
    if len(matches) == 1:
        return NameLookup(user=matches[0], **common)
    if not matches:
        return NameLookup(refusal=Refusal.not_found(_not_found_detail(
            len(employees), excluded, has_more, partiality)), **common)
    return NameLookup(
        refusal=Refusal.ambiguous(
            [match.open_id for match in matches],
            _ambiguous_detail(len(matches), has_more, partiality)),
        **common)


def _how_many(returned: int, has_more: bool) -> str:
    """*How many* — derived from what came back plus ``has_more``, never from ``count``."""
    return f"{returned}" + (" (and the directory says there are more)" if has_more else "")


def _ambiguous_detail(matched: int, has_more: bool, partiality: Partiality) -> str:
    """The ambiguous refusal's detail. **Ids only, never candidate display names** — a refusal
    drawn from the live directory that named its candidates would be a directory-enumeration
    oracle, one query at a time. It says how to disambiguate, not who the candidates are.

    The query string is deliberately not echoed either: the caller already holds it, and a
    refusal that repeats a person's name is one copy of it more than the refusal needs.
    """
    detail = (
        f"the directory returned {_how_many(matched, has_more)} employees whose own display "
        f"name matches this query exactly, so it does not identify one person. "
        f"Pass the intended open_id directly instead of a name; the candidate open_ids are "
        f"carried on this refusal."
    )
    return detail + (" " + partiality.detail() if partiality.is_partial else "")


def _not_found_detail(returned: int, excluded: int, has_more: bool,
                      partiality: Partiality) -> str:
    detail = (
        f"no employee the directory returned has that display name. The search ran and "
        f"answered with {_how_many(returned, has_more)} row(s), none of them an exact "
        f"(case-insensitive, whitespace-normalized) match. This is 'searched and not found' "
        f"— a missing permission raises LarkPermissionError instead, and is never reported "
        f"here."
    )
    if excluded:
        detail += (
            f" {excluded} of those row(s) were EXCLUDED before matching because the directory "
            f"reported them abnormal or sent them with no id, so this is not a clean negative: "
            f"narrow required_fields (or read the disclosure below) before concluding the "
            f"person does not exist."
        )
    return detail + (" " + partiality.detail() if partiality.is_partial else "")


# --------------------------------------------------------------------------- #
# The EMAIL-or-MOBILE route — a different endpoint family, and a different       #
# honesty problem. LD-348.                                                       #
# --------------------------------------------------------------------------- #

#: **THE DUAL TRUTH — authored ONCE and quoted, never paraphrased.**
#:
#: ``POST /open-apis/contact/v3/users/batch_get_id`` cannot tell you *why* it did not resolve
#: an identifier. An address that exists nowhere and a real user this app cannot see
#: produce the **identical** body, observed on the wire and committed:
#: ``batch-get-id/captures/B2-unknown-email-CONTROL.json``. So the refusal states **both**
#: halves and picks **neither** — which is the contract requirement, not a nicety.
UNRESOLVED_IS_UNDIFFERENTIATED = (
    "Lark returned NO ID for this identifier. That means THE LOOKUP DID NOT RESOLVE IT. It "
    "does not mean no such person exists, and it does not mean the person exists but is out "
    "of this app's reach — because the endpoint answers with the IDENTICAL body for both: "
    "code 0, the identifier echoed back, and the user_id key OMITTED (not null, not empty). "
    "No field, no code and no envelope separates the two, so this refusal reports what was "
    "established and picks neither of what was not."
)

#: **REACH, AS MEASURED — n = 2.** Quoted wherever the route's reach is described. The
#: out-reaching claim is proven (the enumerated department range and the directory search both
#: miss another user this route resolved first try); the generalisation is not, and is refused.
MEASURED_REACH = (
    "REACH IS MEASURED, NOT GENERAL: exactly TWO addresses have been tried on this route, "
    "both on the tenant it was measured on, and both resolved. On those two identifiers this "
    "route reached further than either other route in this library — the enumerable "
    "department range and the directory search each miss another user this route resolved "
    "first try. Whether it answers for an arbitrary member of a tenant, or degrades on a "
    "larger tenant, is UNMEASURED."
)

#: **THE MOBILE LEG — accepted, never observed resolving.** ``B5`` proves a ``mobiles[]``
#: request is accepted and answers ``code: 0`` with the same unresolved shape for a synthetic
#: number. No real mobile was available, and guessing one is out of bounds. So the leg ships
#: callable and says exactly that: no promise, no *"should work"*.
MOBILE_LEG_UNOBSERVED = (
    "THE MOBILE LEG IS ACCEPTED BUT HAS NEVER BEEN OBSERVED RESOLVING A PERSON HERE. A "
    "mobiles[] request is accepted and answers code 0 with the same unresolved shape; the one "
    "number ever sent was synthetic, no real mobile was available to try, and guessing one is "
    "out of bounds. The leg is callable and it refuses cleanly. Nothing here promises it will "
    "resolve anybody."
)

#: What this route is, said in the shipped voice so the mandate's prohibition is not softened:
#: one identifier in, one id out. It needs no cache, which is the whole reason it is not the
#: roster hack that was ruled out by name.
POINT_QUERY_ONLY = (
    "This is a POINT QUERY: one identifier in, one open_id out. It is not a roster dump, a "
    "lookup table, a directory cache or a best-effort matcher, and it needs none of them — a "
    "point query has nothing to cache."
)

#: The two identifier kinds, and the request key each takes. One tuple so the accepted set is
#: auditable and a third kind cannot be added by accident.
IDENTIFIER_KINDS = (("email", "emails"), ("mobile", "mobiles"))


def _identifier_of(entry, kind: str) -> str:
    """The identifier this ``user_list`` entry echoes back, or ``""``."""
    value = _get(entry, kind)
    return value if isinstance(value, str) else ""


def _same_identifier(asked: str, echoed: str, kind: str) -> bool:
    """Whether an echoed identifier is the one that was asked about.

    An email is compared casefolded (addresses are case-insensitive on their domain half and
    Lark echoes whatever it stored); a mobile is compared verbatim after whitespace-stripping,
    because normalising a phone number means guessing a country code.
    """
    if kind == "email":
        return asked.strip().casefold() == echoed.strip().casefold()
    return asked.strip() == echoed.strip()


def resolve_colleague(*, email: Optional[str] = None, mobile: Optional[str] = None,
                      client=None, domain: str = "larksuite.com") -> NameLookup:
    """Resolve an **email or mobile** to exactly one ``open_id``, or refuse in a typed way.

    The *other* forward direction. :func:`resolve_user` turns a **display name** into an id via
    the directory search; this turns an **address** into one via the contacts family's
    ``contact/v3/users/batch_get_id`` — a different endpoint family, which does not inherit the
    search route's starved contacts data range. (The endpoint is written without its
    ``/open-apis`` prefix on purpose: this surface's permission row is DERIVED from the code
    that calls it, and a path in prose must never be what satisfies that derivation.)

    Exactly one of ``email`` / ``mobile`` is required: neither and both are a ``ValueError``
    raised **before** any call, not a refusal object, because "which question did you mean" is
    a caller's bug rather than an answer about a person.

    The answer is the same :class:`NameLookup` :func:`resolve_user` returns — one
    :class:`UserRef` **or** one :class:`~larkdocio.write.model.refusal.Refusal`, never both,
    never neither, always with the :class:`Partiality` disclosure. ``query`` carries the
    identifier that was asked about. A scope denial is raised as
    :class:`~larkdocio.errors.LarkPermissionError`, never returned as an absence.

    **The three things this verb says about itself, quoted rather than summarised:**

    {POINT_QUERY}

    {DUAL_TRUTH}

    {REACH}

    {MOBILE}
    """
    given = [(kind, key, value) for (kind, key), value in zip(IDENTIFIER_KINDS,
                                                              (email, mobile))
             if isinstance(value, str) and value.strip()]
    if len(given) != 1:
        raise ValueError(
            "resolve_colleague takes EXACTLY ONE of `email` or `mobile`; neither and both are "
            "a caller's bug, not a question about a person, and neither spends a request")
    kind, request_key, identifier = given[0]
    identifier = identifier.strip()
    if client is None:
        from larkdocio.contacts.client import ContactsSearchClient

        client = ContactsSearchClient.from_read_credentials(domain)

    data = client.batch_get_id(**{request_key: [identifier]})
    entries = list(_get(data, "user_list") or ())

    mine, foreign, resolved = [], [], []
    for entry in entries:
        echoed = _identifier_of(entry, kind)
        if not _same_identifier(identifier, echoed, kind):
            foreign.append(entry)
            continue
        mine.append(entry)
        open_id = _get(entry, "user_id")
        if isinstance(open_id, str) and open_id.strip():
            resolved.append(UserRef(open_id=open_id, display_name=""))

    # An entry with no id, and an input the body never echoed at all, are the SAME class of
    # incompleteness: something was asked and nothing was answered about it. Counting both
    # here is what stops either from reading as a clean negative.
    unanswered = len(mine) - len(resolved) + (0 if mine else 1)
    partiality = Partiality(rows_without_an_id=unanswered)
    common = dict(query=identifier, partiality=partiality, has_more=False,
                  reported_count=None,
                  candidate_ids=tuple(ref.open_id for ref in resolved))

    if foreign or len(resolved) > 1:
        seen = [ref.open_id for ref in resolved]
        for entry in foreign:
            open_id = _get(entry, "user_id")
            if isinstance(open_id, str) and open_id and open_id not in seen:
                seen.append(open_id)
        return NameLookup(
            refusal=Refusal.ambiguous(seen, _address_ambiguous_detail(
                len(resolved), len(foreign), partiality)),
            **common)
    if len(resolved) == 1:
        return NameLookup(user=resolved[0], **common)
    return NameLookup(
        refusal=Refusal.not_found(
            _address_unresolved_detail(kind, bool(mine), partiality)),
        **common)


resolve_colleague.__doc__ = (resolve_colleague.__doc__ or "").format(
    POINT_QUERY=POINT_QUERY_ONLY,
    DUAL_TRUTH=UNRESOLVED_IS_UNDIFFERENTIATED,
    REACH=MEASURED_REACH,
    MOBILE=MOBILE_LEG_UNOBSERVED,
)


def _address_unresolved_detail(kind: str, echoed: bool, partiality: Partiality) -> str:
    """The unresolved refusal — the dual truth first, then what was measured.

    The identifier is deliberately **not** echoed: the caller already holds it, and a refusal
    that repeats an address is one copy of it more than the refusal needs.
    """
    parts = [UNRESOLVED_IS_UNDIFFERENTIATED]
    if not echoed:
        parts.append(
            "Note further that the body did not echo this identifier at all, so not even the "
            "'asked and answered nothing' shape was returned for it.")
    parts.append(MEASURED_REACH)
    if kind == "mobile":
        parts.append(MOBILE_LEG_UNOBSERVED)
    if partiality.is_partial:
        parts.append(partiality.detail())
    return " ".join(parts)


def _address_ambiguous_detail(mine: int, foreign: int, partiality: Partiality) -> str:
    """Ids only — never the identifier, never a pick.

    One address meaning one person is an **assumption** until observed, and no arm of the
    probe ever saw a second entry. So a second entry, or an entry echoing an identifier the
    caller did not ask about, refuses here rather than being adopted.
    """
    parts = [
        f"the lookup came back with {mine} entr(y/ies) for the identifier asked about and "
        f"{foreign} for identifier(s) that were not asked about, so it does not identify one "
        f"person. One identifier meaning one person is an assumption this library will not "
        f"make on your behalf: pass the intended open_id directly. The open_ids the body "
        f"carried are on this refusal, and nothing else about them is."
    ]
    if partiality.is_partial:
        parts.append(partiality.detail())
    return " ".join(parts)


def candidate_open_ids(lookup: NameLookup) -> Sequence[str]:
    """The open_ids an ambiguous lookup matched. A thin accessor so a caller does not have to
    know that the candidates live on the shipped ``Refusal``."""
    return lookup.refusal.candidate_ids if lookup.refusal is not None else ()
