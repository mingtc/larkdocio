"""larkdocio.contacts — turn a **name** or an **address** into an ``open_id``, or refuse in a
typed way.

The forward direction. The library could already turn an ``open_id`` into a display name
(``read.client.batch_get_user_names``); it could not do the reverse, so an agent holding
*"@mention Example User in this cell"* had no honest path to
``sheets.rich_encode.encode_mention(open_id)``. This package is that path, and nothing more:
two read-only, paced POINT queries, and no third.

**TWO forward verbs, two endpoint families, and they are not interchangeable.**

* :func:`~larkdocio.contacts.lookup.resolve_user` — a display **name**, via
  ``POST /open-apis/directory/v1/employees/search``.
* :func:`~larkdocio.contacts.lookup.resolve_colleague` — an **email or mobile**, via the
  contacts family's ``users/batch_get_id``. A *different* endpoint family, which does **not**
  inherit the search route's starved contacts data range: on the two identifiers measured it
  resolved another user the search route reaches by no query at all. Read its reach as
  :data:`~larkdocio.contacts.lookup.MEASURED_REACH` states it and no further, and read an
  unresolved answer as :data:`~larkdocio.contacts.lookup.UNRESOLVED_IS_UNDIFFERENTIATED`
  states it — the rider below binds on that route too, and binds **harder** there precisely
  because it reaches further: a caller who watches it resolve two other users will read a
  third's absence as *"that person isn't here"*, and the wire does not support that reading.

**An address → id route is NOT a name → id route.** Resolving an arbitrary other user's *name*
remains unavailable here, and neither verb stands in for it.

**The reverse direction is re-exported from here, so both halves are found together.**
``ReadClient`` is :class:`larkdocio.read.client.Client` under the name that says why it is in
this namespace: ``ReadClient.from_read_credentials().batch_get_user_names(["ou_…"]) ->
{"ou_…": "Example User"}`` — ids you already hold into names, for display. Nothing is wrapped and
no second call site exists; it is the same method on the same class the document reader uses,
reachable from the package a reader searching for *"name and id"* opens first. The forward verb
here refuses loudly; the reverse one degrades quietly (an id it cannot resolve is simply absent
from the returned dict) — see the posture note below for why the two differ.

**Its posture is the OPPOSITE of the reverse direction's, deliberately.** Rendering a mention
degrades quietly — a name that will not resolve is left as its raw id and the document still
reads. A *lookup* must refuse loudly, because its answer is about to be written into someone
else's document. So: exactly one match or a typed refusal, and never a best guess.

What this surface will NOT do
-----------------------------

* **It will not enumerate the directory to fake a name search.** Walking departments and
  matching names locally was disqualified before this package was written: it is O(directory)
  per lookup, it silently returns the wrong answer whenever a user sits outside the app's
  contacts data range (which is exactly the case that motivated the search endpoint — the
  account owner is provably absent from the complete department enumeration), and it turns
  a lookup into a bulk export of user data. The rejection is recorded here so it is not
  re-derived by the next reader.
* **It will not fuzzy-match, rank, phonetically match, or take the top hit.** Matching is
  casefold + whitespace-normalized **exact** equality over the display strings the directory
  itself reports, and nothing else.
* **It will not name the candidates when it refuses as ambiguous.** A refusal drawn from the
  live directory that listed candidate display names would be a directory-enumeration oracle,
  one query at a time. Candidates are ``open_id``s only.
* **It will not request, widen or escalate a scope.** Without the directory-search grant the
  call is denied and the denial is surfaced verbatim; a grant is a Lark console action.
* **It will not resolve names inside ``dry_run()``.** The lookup is a **pre-authoring** step in
  front of ``encode_mention``; the plan-time mention validation stays an independent second
  gate, because *"this name means this id"* and *"this id still exists"* prove different things.

What the SERVER does, as OBSERVED
---------------------------------

Recorded from ~33 read-only probes run on 2026-08-02, on the READ credential pair, paced
at 1.2 s. One of those probes survives, in the source repository, under
``tests/captures/name-lookup-spike/slice2/captures/``; the sanitized record of the full set was retired
from the dev repo on 2026-09-18. **This
section is what the ENDPOINT does, not what this library does** — the exactly-one-or-refuse
contract above is enforced client-side regardless of any of it.

* **Match breadth: TOKEN-PREFIX, case-insensitive.** Not exact, and not arbitrary substring.
  For an employee whose display name is two tokens, *Given Family*, each of these returned that
  same employee: the first letter in either case, the given name in either case, the family name,
  the whole name less its last letter, and the whole name in upper case. Fragments that begin
  inside a token — the given name or the family name without its first letter, or the given
  name's last letter alone — returned nothing. So the server is *broader* than this surface's
  contract on the left of a token and *narrower* inside one, which is exactly why the contract is re-applied over the returned set
  rather than delegated to the server.
* **The reachable set can be far smaller than the directory.** On the tenant this was measured
  against, every query returns **at most the account owner** — another user whose display name
  the reverse direction (``batch_get_user_names``) resolves happily is returned by **no** query
  prefix, with ``contain_resigned_employee`` false, true, or the filter omitted entirely. Read
  a *not-found* from this endpoint as *"the search did not return them"*, never as *"this
  person does not exist"*; the refusal's own detail says so.
* **Zero-hit shape:** ``code: 0`` with ``employees`` present as an **empty list**, and a
  ``page_response`` carrying ``has_more: false`` and a populated ``page_token``. An absence is
  a normal answer here, not an error — which is what keeps it distinguishable from a denial.
* **Paging and ``count``:** ``page_response`` carries ``has_more`` and ``page_token``. The
  ``count`` field is ``Optional[int]`` in the pinned SDK and was **never sent** — on any
  response, including the ``page_size: 1`` arms. Its meaning (page count or grand total) has
  therefore never been observed here, so *how many* is derived from the returned rows plus
  ``has_more``, and a ``count`` that ever does arrive is carried verbatim and not interpreted.
* **The id field:** with ``employee_id_type=open_id`` the ``ou_`` id arrives at
  ``employees[].base_info.employee_id``; ``user_id`` is absent from the body entirely.
* **Resource accounts (meeting rooms):** three room names returned **no employee at all**. So
  the question *"which field distinguishes a room from a person"* does not arise on this
  endpoint — the employee directory does not carry them. That is a legitimate answer and it is
  recorded as one; this surface resolves **people** and uses **no name-pattern heuristic** to
  guess what a string is.
* **``abnormals``: real, and reachable.** No ordinary query produced one. Deliberately widening
  ``required_fields`` past the granted set did: ``code: 0``, the owner present in
  ``employees[]``, **and** an ``abnormals[]`` naming that same row with ``row_error: 0`` and
  ``field_errors`` of ``2003`` on two field groups. A partial answer wearing the costume of a
  complete one, on the wire, today. That capture is committed beside the probe record in the
  source repository, and it is the fixture the disclosure invariant is proved against — see
  :class:`~larkdocio.contacts.lookup.Partiality`. Note the consequence, which is deliberate:
  a row named in ``abnormals`` is **never** a resolved user, even when it also came back in
  ``employees[]`` looking fine.
"""
from larkdocio.contacts.client import (
    CONTACTS_MIN_REQUEST_SPACING_SECONDS,
    CONTACTS_RATE_WINDOW_SECONDS,
    CONTAIN_RESIGNED_EMPLOYEE,
    DEFAULT_MAX_SEARCHES_PER_WINDOW,
    DEFAULT_PAGE_SIZE,
    EMPLOYEE_ID_TYPE,
    INCLUDE_RESIGNED_USER,
    REQUIRED_FIELDS,
    ContactsSearchClient,
)
#: The REVERSE verb's home, re-exported under a name that says what it is for here. Not a
#: wrapper: the same class, so there is one call site and one permission row for it.
from larkdocio.read.client import Client as ReadClient
from larkdocio.contacts.lookup import (
    AbnormalRow,
    MEASURED_REACH,
    MOBILE_LEG_UNOBSERVED,
    NameLookup,
    POINT_QUERY_ONLY,
    Partiality,
    UNRESOLVED_IS_UNDIFFERENTIATED,
    UserRef,
    candidate_open_ids,
    normalize_name,
    resolve_colleague,
    resolve_user,
)

__all__ = [
    "AbnormalRow", "CONTACTS_MIN_REQUEST_SPACING_SECONDS", "CONTACTS_RATE_WINDOW_SECONDS",
    "CONTAIN_RESIGNED_EMPLOYEE", "ContactsSearchClient", "DEFAULT_MAX_SEARCHES_PER_WINDOW",
    "DEFAULT_PAGE_SIZE", "EMPLOYEE_ID_TYPE", "INCLUDE_RESIGNED_USER", "MEASURED_REACH",
    "MOBILE_LEG_UNOBSERVED", "NameLookup", "POINT_QUERY_ONLY", "Partiality", "REQUIRED_FIELDS",
    "ReadClient", "UNRESOLVED_IS_UNDIFFERENTIATED", "UserRef", "candidate_open_ids",
    "normalize_name", "resolve_colleague", "resolve_user",
]
