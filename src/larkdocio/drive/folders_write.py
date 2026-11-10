"""larkdocio.drive.folders_write — create ONE folder under a parent, and nothing else.

*A consumer could read a folder tree and upload a file into a folder, but could not make a
folder* — so "publish these and organise them into subfolders" dead-ended at the last step, and
it dead-ended **structurally**: no folder-creating verb existed anywhere in this library. The
narrow slice was **opened by a product ruling of 2026-08-14** and this module is all of it.

**THE REST OF THE ORGANIZE RUNG STAYS SHUT, AND THAT IS THE SCOPE RATHER THAN AN OVERSIGHT.**
:data:`R3_NOT_SHIPPED` enumerates it as data, with a reason on every row: no move, no rename, no
copy, no bulk *organise by type*, and **no folder delete**. Those are claims about **this
library's surface**, not about Lark's API: the routes are **unmeasured rather than refuted**
here, except where a capture says otherwise on a row. A half-open door with no sign is worse
than a closed one, so the sign is in the code, in ``capabilities()`` and in the guide.

**A module of its own, for the reason** :mod:`larkdocio.drive.versions_write` **is one:** no
console command reaches this write engine — the one console verb that writes,
``roundtrip push --apply``, writes to a docx — guarded **in the source repository** by
``tests/front_door.py::write_reach_paths_bypassing()``, which walks what a CLI handler can
reach, plus the per-command leg
``tests/test_cli_front_door_truth.py::test_ac1_the_reading_commands_own_handlers_reach_NO_write_module``,
so a mutating client may not live beside the read one. Same split, same transport, same
throttle.

**WHAT THE ANSWER CARRIES — MEASURED, NOT ASSUMED.** ``POST
/open-apis/drive/v1/files/create_folder`` answers ``code:0`` with a ``data`` holding **exactly
two keys**: ``token`` and ``url`` (capture ``ld467-01-``). Both are returned; the ``url`` is
**Lark's own answer**, never a host and a token this library glued together, and it is honestly
``None`` when Lark sends none rather than constructed.

**DUPLICATE NAMES MAKE A SECOND FOLDER**, and it is said on the verb, in ``capabilities()`` and
in the guide — see :data:`DUPLICATE_NAME_BEHAVIOUR`. This is the defect class the upload leg
was found shipping silent; it is not shipped silent a second time.

**THE DESTINATION IS ALWAYS THE CALLER'S**, exactly as on the upload leg, and here the fence
earns itself twice over from measurement:

* ``folder_token`` **omitted** is refused by **Lark** — ``99992402 field validation failed``,
  ``field_violations: [{field: folder_token, description: "folder_token is required"}]``
  (capture ``ld467-05-``). There is no default-parent behaviour for an absent key;
* ``folder_token: ""`` is **ACCEPTED** — ``code:0``, a real token back (capture ``ld467-07-``) —
  and the folder **lands in the bot's own root**, confirmed by listing that root and by the
  listing's own ``parent_token`` (that recording is not published). That is a destination *this library
  did not pick*, so it is refused locally rather than passed on
  (:data:`EMPTY_PARENT_LANDS_IN_THE_BOTS_ROOT`).

**AN EMPTY NAME IS ACCEPTED BY LARK AND THAT IS WHY IT IS REFUSED HERE.** ``name: ""`` answered
``code:0`` and the folder's stored name read back as the **empty string** in both the parent's
listing and the metadata route (capture ``ld467-25-``; the listing's recording is not
published). A permanent,
nameless folder in somebody's Drive is worse than a refusal, so the refusal is **this library's
own** and says so instead of blaming the server
(:data:`EMPTY_NAME_ACCEPTED_BY_LARK`).

**THE PARENT'S TYPE *IS* POLICED BY THIS ROUTE — measured, and worth stating because the sibling
route does not.** A real **file** token as the parent was refused ``1061002`` (capture
``ld467-11-``), whereas ``upload_all`` accepted a mismatched ``parent_type`` / ``parent_node``
pair with ``code:0`` (:mod:`larkdocio.drive.files_write`). Two calls in one family, opposite
strictness; neither is inferred from the other.

**RESIDUE, AND THE PART THIS LIBRARY CANNOT CLEAN UP.** A created folder is **permanent as far
as this library is concerned**: it ships **no folder-delete verb** (the ruling opened one verb).
The Drive delete route *does* remove a folder — ``DELETE /open-apis/drive/v1/files/{token}``
with ``type=folder`` answered ``code:0``, after which ``metas/batch_query`` answered ``metas:
[]`` with ``failed_list: [{code: 970005}]``, i.e. **a trashed FOLDER token stops resolving**,
which is the *opposite* of a trashed **file** token (that one still resolves — *trash, not
purge*). Capture ``ld467-13-`` (in the source repository); the delete's own recording is not
published. **The claim rests on a CONTROL
PAIR, not on the negative arm alone**: the same endpoint **does** resolve a LIVE folder token —
``ld467-25-`` answers ``code:0`` with a meta keyed to the token carrying ``doc_type: "folder"``,
an ``owner_id`` and a real ``url`` (2026-08-15), and a folder-cleanup sweep re-queried 43
tokens on 2026-08-19 (recording not published) and got **4 live folders** resolving with their titles beside **36 trashed
folders** answering ``metas: []`` with ``970005``. So *stops resolving* is a difference measured
against a working positive, not an inference from one arm. So the honest sentence is not "a folder cannot be
removed" and not "this library can remove one" — it is that **the route was measured working and
is deliberately unshipped**, and a caller who needs it makes that call themselves.

**WHAT IS MEASURED, AND WHAT IS UNMEASURED.** One tenant, one day (2026-08-15), the WRITE pair,
a ``tenant_access_token``, every write into a folder the probe itself created under the bot's own
root and swept afterwards: the happy path, the duplicate pair plus the parent listing that proves
it, the omitted / empty parent, an unresolvable parent, a file token as the parent, the empty
name plus its two read-backs, an upload into a created folder, and the delete plus its
re-query. Therefore: ``user_access_token`` is untried, other tenants and regions are untried, a
name-length ceiling is **unmeasured** (nothing long was sent), a folder-count quota is
**unmeasured** (four folders in one parent, no warning field, no refusal — which establishes no
absence of a limit), nesting deeper than one level below a created folder is **unmeasured**, and
whether the call succeeds on READ credentials is **not answerable on the tenant these measurements were made on** (its
READ and WRITE pairs named one app — PROJECT.md, in the dev repo, § Credential aliasing), so it is left open rather than manufactured. All of those are **unmeasured, not
refuted**.

Scope requirements are authored only in :mod:`larkdocio.permissions`; nothing here restates one,
and **nothing here widens, requests or escalates** anything — widening a permission is an action
a workspace administrator takes in the Lark console, and no code in this library takes it.
"""
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from larkdocio.common.auth import WRITE_ENV, apply_ipv4_pin, get_write_credentials
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    RateLimiter,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.drive import ops
from larkdocio.drive.errors import DriveError, FOLDER_REFUSED_CODE, REFUSAL_SENTENCE
from larkdocio.errors import LarkConfigError, api_error_as

#: The endpoint, read from the ONE place a Drive endpoint is named.
CREATE_FOLDER_ENDPOINT = ops.FILES_CREATE_FOLDER_ENDPOINT

#: The Drive object type a folder carries. Named here because the **delete** that uses it is
#: deliberately NOT shipped (see :data:`R3_NOT_SHIPPED`) — a caller who makes that call needs
#: the type, and a constant is cheaper than a docstring they have to re-derive it from.
FOLDER_DRIVE_TYPE = "folder"

#: Lark's own refusal for an **omitted** ``folder_token`` — the reason this library never
#: silently supplies one. Measured: ``ld467-05-``.
MISSING_PARENT_REFUSED_CODE = 99992402

#: THE DUPLICATE-NAME DISCLOSURE. Quoted — never re-typed — into ``capabilities()`` and the
#: guide, so the three places cannot drift apart.
DUPLICATE_NAME_BEHAVIOUR = (
    "Creating a folder whose name already exists under the same parent makes A SECOND FOLDER. "
    "Measured 2026-08-15 (tests/captures/ld467-create-folder/captures/ld467-02-, ld467-03-, ld467-04-, in "
    "the source repository): the second create answered code:0 with a DISTINCT token, and the parent's "
    "own listing then showed two folders whose names are byte-identical — no de-duplication, no "
    "rename, no reuse of the first folder, and no warning. larkdocio does not pre-check for a "
    "duplicate before creating: a look-then-create is a race it cannot win, and the by-name "
    "lookup is a different ask this library does not ship. If a caller needs one folder per name, they list the "
    "parent themselves and decide."
)

#: Why an empty parent token is refused locally instead of forwarded. Measured: ``ld467-07-``
#: (accepted); the listing that found it in the bot's own root is not published.
EMPTY_PARENT_LANDS_IN_THE_BOTS_ROOT = (
    "An EMPTY parent token is not an empty ask — Lark ACCEPTS folder_token: \"\" with code:0 and "
    "puts the folder in the CALLING APP'S OWN ROOT (measured: tests/captures/ld467-create-folder/captures/"
    "ld467-07-, in the source repository, records the accepted create; the folder was then found by "
    "listing that root and by the listing's own parent_token, a recording not published). That is a permanent write into a destination this "
    "library picked, so it is refused here rather than passed on. Omitting the key entirely is "
    "refused by LARK — 99992402 field validation failed, folder_token is required "
    "(ld467-05-) — so there is no default-parent behaviour to rely on either way."
)

#: Why an empty name is refused locally. Measured: ``ld467-25-`` (the create and the listing
#: legs' recordings are not published).
EMPTY_NAME_ACCEPTED_BY_LARK = (
    "Lark accepts an EMPTY folder name: name: \"\" answered code:0, and the folder's stored name "
    "read back as the empty string in both the parent's listing and the metadata route "
    "(the metadata leg is tests/captures/ld467-create-folder/captures/"
    "ld467-25-r2-metadata-of-the-empty-named-folder.json, in the source repository). A "
    "permanent nameless folder in somebody's Drive is worse than a refusal, so larkdocio "
    "refuses it — this refusal is the library's own and does not pretend to be the server's."
)

#: **THE REST OF THE R3 ORGANIZE RUNG, ENUMERATED AS DATA WITH A REASON EACH.** The maintainer ruling
#: that opened folder creation opened *one verb*; these are the ones it did not, and each row
#: says why rather than leaving a reader to guess whether it was forgotten. Every row is a claim
#: about **this library's surface** — the routes themselves are **unmeasured rather than
#: refuted** unless the reason says otherwise.
R3_NOT_SHIPPED: Tuple[Tuple[str, str], ...] = (
    ("move a folder or a file to another folder",
     "Not shipped. The 2026-08-14 ruling opened folder CREATION only. A move relocates an "
     "object a caller may not own out of a place other people look for it, and no route for it "
     "was called here — unmeasured, not refuted."),
    ("rename a folder",
     "Not shipped. Same ruling, same one-verb scope. A rename is the edit most likely to break "
     "a link somebody else stored; no route for it was called here — unmeasured, not refuted."),
    ("copy a folder or its contents",
     "Not shipped. Same ruling. A recursive copy is a bulk permanent write whose failure mode "
     "is a half-copied tree, and this library ships no verb that can leave one; no route for it "
     "was called here — unmeasured, not refuted."),
    ("organise a folder's children by type, date or any other rule",
     "Not shipped, and deliberately not offered as a convenience either: it would be a move "
     "loop wearing a helper's clothing, and the move rung is shut."),
    ("delete a folder",
     "Not shipped. The Drive route DOES work — DELETE /open-apis/drive/v1/files/{token} with "
     "type=folder answered code:0, and a re-query then reported the token gone (metas: [] with "
     "failed_list [{code: 970005}]); the re-query is capture ld467-13- in the source repository, the "
     "delete's own recording is not published — so this "
     "is a MEASURED route left unshipped under the one-verb ruling, not an unmeasured one. The "
     # LD-606 added the positive arm; the issue id stays in this comment, not in the row.
     "gone-ness reading rests on a CONTROL PAIR rather than that one arm: the same "
     "re-query RESOLVES a live folder token, with its doc_type, owner_id and url (ld467-25-, "
     "2026-08-15) and with its title (a folder-cleanup sweep, recording not published: 4 live folders beside 36 trashed "
     "ones out of 43 tokens, 2026-08-19). A folder this library creates is therefore permanent "
     "as far as this library is concerned, and a caller who needs it removed makes that call "
     "themselves."),
    ("create a shortcut to a folder or a file",
     "Not shipped. Outside the ruling; no route for it was called here — unmeasured, not "
     "refuted."),
)


@dataclass(frozen=True)
class CreatedFolder:
    """One folder created under a parent: **what Lark answered, and what was asked for**.

    ``token`` and ``url`` are the two keys the response actually carries (capture
    ``ld467-01-``). ``url`` is Lark's own — it is honestly ``None`` when the answer omits it,
    because a URL assembled from a host and a token would be a guess wearing the shape of an
    answer.

    ``name`` and ``parent_token`` are what the caller asked for, echoed so a ledger row is
    complete without a second call. **Lark does not rename a duplicate** (unlike the named-version
    family, where a second ``"V1.0"`` comes back ``"V1.0(1)"``): the name under the parent is
    exactly what was sent, and a second folder with the same name is simply a second folder —
    :data:`DUPLICATE_NAME_BEHAVIOUR`.
    """

    token: str
    url: Optional[str]
    name: str
    parent_token: str

    #: Restated on the value itself, so a caller reading a returned object — not the module —
    #: still meets the disclosure that made this the LD-464 defect class avoided.
    duplicate_name_behaviour: str = DUPLICATE_NAME_BEHAVIOUR


class DriveFolderError(DriveError):
    """A failure on the folder-creation leg. Its own family under the Drive errors: creating a
    **container** is not uploading an object into one, and folding the two would tell a caller
    the wrong thing about what is now in their Drive."""


class DriveFolderCreateError(DriveFolderError):
    """A folder create refused — locally, before any call, or by Lark.

    Carries the ``name`` and ``parent_token`` that were asked for, so a traceback says which
    create failed without the caller re-deriving it from the message.
    """

    def __init__(self, message, *, code=None, msg=None, denial=None,
                 name=None, parent_token=None):
        super().__init__(message, code=code, msg=msg, denial=denial)
        self.name = name
        self.parent_token = parent_token


def check_folder_name(name) -> str:
    """The name gate: required, non-blank, **refused locally** — and it says whose refusal it is.

    Lark itself accepts an empty name (:data:`EMPTY_NAME_ACCEPTED_BY_LARK`), so this refusal
    cannot be attributed to the server and is not. The value is returned **unchanged** —
    surrounding whitespace is a caller's business and is not silently trimmed, because a name
    this library edited would not be the name the caller can search for.
    """
    if not name or not str(name).strip():
        raise DriveFolderCreateError(
            f"a folder needs a name; {name!r} is blank. Nothing was sent. "
            f"{EMPTY_NAME_ACCEPTED_BY_LARK}",
            name=name)
    return name


def check_parent_token(parent_token) -> str:
    """The destination gate: the parent folder token is **required**, refused locally.

    The reason is measured rather than stylistic: an empty token is *accepted* by Lark and puts
    the folder in the calling app's own root (:data:`EMPTY_PARENT_LANDS_IN_THE_BOTS_ROOT`), and
    this library picks no destination.
    """
    if not parent_token or not str(parent_token).strip():
        raise DriveFolderCreateError(
            f"a folder needs a parent folder token — the token of the folder it goes in; "
            f"{parent_token!r} is blank. Nothing was sent: this library picks no default "
            f"destination. {EMPTY_PARENT_LANDS_IN_THE_BOTS_ROOT}",
            parent_token=parent_token)
    return parent_token


class DriveFoldersWriteClient(CredentialedRawHttpClient):
    """Creates **one folder under a parent**. That is the whole surface.

    **WRITE credentials only**, resolved through :func:`~larkdocio.common.auth.
    get_write_credentials`; nothing here consults, infers or falls back to the READ pair, and a
    denial is surfaced with Lark's own code and message rather than retried on another pair (the
    credential doctrine in PROJECT.md, in the dev repo — and its § Credential aliasing: on this
    tenant the two pairs happen to be one app, which the code must keep treating as a
    coincidence).

    Throttled by the same evidence-anchored limiter the enumeration and named-version clients
    ride (one call per :data:`~larkdocio.drive.client.DRIVE_MIN_REQUEST_SPACING_SECONDS`), so
    every Drive leg paces alike.
    """

    def __init__(
        self,
        app_id,
        app_secret,
        domain="larksuite.com",
        *,
        urlopen=urllib.request.urlopen,
        token_fetcher=fetch_tenant_access_token,
        rate_limiter=None,
        timeout=30,
    ):
        from larkdocio.drive.client import DRIVE_MIN_REQUEST_SPACING_SECONDS

        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._base = api_base(domain)
        self._urlopen = urlopen
        self._token_fetcher = token_fetcher
        self._limiter = rate_limiter if rate_limiter is not None else RateLimiter(
            1, window=DRIVE_MIN_REQUEST_SPACING_SECONDS)
        self._timeout = timeout
        self._token = None
        self._api_calls = 0

    def _credential_pair(self):
        """The WRITE pair — this client resolves no other, so a rejected credential here
        names ``LARK_WRITE_APP_*`` and never the pair a reader is resolving (LD-672)."""
        return WRITE_ENV

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        """Build from the environment's **WRITE** pair (+ the shared IPv4 pin)."""
        app_id, app_secret = get_write_credentials()
        if not app_id or not app_secret:
            raise LarkConfigError(
                f"Drive folders write client: no WRITE credentials resolved. Set "
                f"{WRITE_ENV[0]}/{WRITE_ENV[1]}."
            )
        apply_ipv4_pin()
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made on its own transport."""
        return self._api_calls

    @property
    def limiter(self):
        """The limiter every call on this client passes through."""
        return self._limiter

    def create_folder(self, name, parent_token) -> CreatedFolder:
        """Create a folder called ``name`` inside ``parent_token``.

        ``POST /open-apis/drive/v1/files/create_folder`` with ``{"name": …, "folder_token": …}``
        — **one call, and only one.** What comes back is a :class:`CreatedFolder` carrying the
        two keys the response actually holds, ``token`` and ``url`` (capture ``ld467-01-``); the
        ``url`` is Lark's own answer and is ``None`` rather than constructed when absent.

        **THE DESTINATION IS THE CALLER'S, and both halves of that are measured.** ``name`` and
        ``parent_token`` are required and are refused **locally, before any call**
        (:func:`check_folder_name`, :func:`check_parent_token`). Omitting the parent is refused
        by **Lark** — ``99992402 field validation failed``, ``folder_token is required``
        (capture ``ld467-05-``) — so there is no default-parent behaviour; and sending it as the
        **empty string** is *accepted* by Lark and lands the folder in the calling app's
        **own root** (capture ``ld467-07-``; the root listing's recording is not published), which is precisely why this library
        refuses that rather than forwarding it. An empty **name** is likewise accepted by Lark
        and stored as the empty string (capture ``ld467-25-``), so that
        refusal is this library's own and says so.

        **DUPLICATE NAMES MAKE A SECOND FOLDER.** Same name, same parent, ``code:0``, a distinct
        token, and the parent's listing then shows two byte-identically named folders — no
        de-duplication, no rename, no reuse, no warning. Nothing is pre-checked here: see
        :data:`DUPLICATE_NAME_BEHAVIOUR` for the measurement and for why a look-then-create is
        not offered.

        **REFUSALS SAY WHAT HAPPENED AND WHAT TO DO.** ``1061002`` is the drive family's
        one-code-three-causes answer — a parent that does not exist, one this caller cannot
        reach, or a token that is **not a folder** (measured: a real file token as the parent was
        refused with it, capture ``ld467-11-``) — so the refusal names the possibilities and
        diagnoses none, reusing :data:`~larkdocio.drive.errors.REFUSAL_SENTENCE` rather than
        wording a second version of it. Any other code is surfaced with Lark's own body through
        the shared seam, undecorated: a diagnosis nobody measured would be a guess.

        **THIS IS THE ONLY ORGANIZE VERB.** No move, no rename, no copy, no bulk organiser and
        no folder delete — :data:`R3_NOT_SHIPPED`, with a reason on every row.
        """
        name = check_folder_name(name)
        parent_token = check_parent_token(parent_token)

        descriptor = ops.op("create_folder")
        self._limiter.acquire()
        self._api_calls += 1
        response = self._send(
            descriptor.http_method, CREATE_FOLDER_ENDPOINT,
            body={"name": name, "folder_token": parent_token})
        code = response.get("code") if isinstance(response, dict) else None
        if not (code in (0, None) or str(code) == "0"):
            self._refuse(code, response, name, parent_token)
        data = (response.get("data") or {}) if isinstance(response, dict) else {}
        token = data.get("token")
        if not token:
            raise DriveFolderCreateError(
                f"the create of folder {name!r} under {parent_token!r} answered success with "
                f"no token, so nothing addressable was reported. A folder may exist; this "
                f"library will not invent a token for it",
                name=name, parent_token=parent_token)
        return CreatedFolder(token=token, url=data.get("url"), name=name,
                             parent_token=parent_token)

    def _refuse(self, code, response, name, parent_token) -> None:
        """Type what Lark said. The measured codes get the family's honest sentence; anything
        else goes through the shared seam **undecorated**, because a diagnosis this library
        invented for an unmeasured code would be worse than Lark's own words."""
        msg = response.get("msg") if isinstance(response, dict) else None
        if code == FOLDER_REFUSED_CODE or str(code) == str(FOLDER_REFUSED_CODE):
            raise api_error_as(
                DriveFolderCreateError,
                f"the folder {name!r} was not created under {parent_token!r}. "
                f"{REFUSAL_SENTENCE} On this route that same code is also the answer when the "
                f"token is not a folder at all — a real file token as the parent was refused "
                f"with it. Nothing was created. Check that the token names a FOLDER this app "
                f"may write to, then retry",
                code=code, msg=msg, body=response, credential_env=WRITE_ENV,
                name=name, parent_token=parent_token)
        if code == MISSING_PARENT_REFUSED_CODE or str(code) == str(MISSING_PARENT_REFUSED_CODE):
            raise api_error_as(
                DriveFolderCreateError,
                f"Lark rejected the request for folder {name!r} as failing its own field "
                f"validation ({MISSING_PARENT_REFUSED_CODE}): Msg: {msg}. On this route that is "
                f"what an absent folder_token answers. Nothing was created. Pass the token of "
                f"the folder the new folder goes in",
                code=code, msg=msg, body=response, credential_env=WRITE_ENV,
                name=name, parent_token=parent_token)
        raise_for_lark_code(response, context="drive create_folder",
                            credential_env=WRITE_ENV)
