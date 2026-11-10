"""larkdocio.drive.access_write — grant a HUMAN access to an object the app created (LD-432,
widened past docx by LD-456).

*A document nobody chose to be on is not a shared document.* An object this library mints
carries no member row anyone picked — none at all when it was created with no folder, and its
**folder's** inherited rows (``perm_type='container'``) when it was filed into one
(:data:`~larkdocio.drive.access.MEMBER_LIST_AT_BIRTH`, both cases measured) — so the humans who
need it have to be put on it. This module is
the surface that does that, fenced to exactly what has been measured: the object types
``docx``, ``sheet`` and ``bitable`` (Base) — carried as the ``obj_type`` argument every verb
takes, resolvable from a URL, and every other type refused locally by name — a grantee named by
**email** or **open_id**, the three member levels ``view`` / ``edit`` / ``full_access``, the
whole lifecycle (grant, raise, lower, revoke), the member read that reports the **owner** as
well as the members, and the two document settings whose names govern copying.

**A module of its own, for the reason ``versions_write`` is:** no console command reaches this
write engine — the one console verb that writes, ``roundtrip push --apply``, writes to a
docx — and that is falsifiable, guarded **in the source repository** by
``tests/front_door.py::write_reach_paths_bypassing()``, which walks what a CLI handler can
reach and fails if a write engine is in that set, plus the per-command leg
``tests/test_cli_front_door_truth.py::test_ac1_the_reading_commands_own_handlers_reach_NO_write_module``.
So the mutating client lives here, reachable from no CLI command, while the models, the policy
gates and the disclosures sit in :mod:`larkdocio.drive.access`.

**WRITE credentials only, and no pair is ever mixed.** Every leg of every op on this client —
including the contacts lookup that turns an email into an ``open_id`` and the metadata read
that reports the owner — is made on the WRITE pair, which is the pair every capture behind
this surface was recorded on.

**The read-back is the verdict.** ``code: 0`` proves acceptance; the spike caught this very
family accepting a member re-add and **not storing it**, so each op here follows its write
with an independent read and reports what it found.

**What this surface does not do** is authored once in :mod:`larkdocio.drive.access` and quoted
here: it does not transfer ownership, it does not resolve a display name (it names the shipped
verb that does), it says nothing about groups or about the object types outside its measured
set, and it cannot tell you whether a human's clipboard then obeys.
"""
import urllib.request
from typing import Optional

from larkdocio.common.auth import WRITE_ENV, apply_ipv4_pin, get_write_credentials
from larkdocio.common.metas import failed_reason
from larkdocio.contacts.client import ContactsSearchClient
from larkdocio.contacts.lookup import resolve_colleague
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    RateLimiter,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.drive import ops
from larkdocio.drive.access import (
    BARE_NAME_REFUSAL,
    CLIPBOARD_UNOBSERVABLE,
    DEFAULT_OBJECT_TYPE,
    EXTERNAL_ACCESS_REFUSED_HERE,
    GROUPS_UNMEASURED,
    INVALID_PARAMETER_MEANS,
    LOCK_SWITCH_READ_ONLY,
    MEASURED_COPY_VALUES,
    MEMBER_FAMILY_IS_V1,
    MEMBER_LIST_AT_BIRTH,
    MEMBER_PERMS,
    MEMBER_TYPE,
    NEED_NOTIFICATION,
    NOT_A_SCOPE_ESCALATION,
    OBJECT_TYPES_MEASURED,
    OWNERSHIP_TRANSFER_NOT_SHIPPED,
    OWNER_IS_NOT_A_MEMBER,
    THE_ROUTE_DOES_NOT_SWALLOW,
    AccessOutcome,
    CopyPermissions,
    CopySetting,
    Member,
    MemberListing,
    check_copy_settings,
    check_perm,
    grantee_id,
    member_path,
    members_path,
    object_target,
    public_path,
)
from larkdocio.errors import LarkConfigError, api_error

#: Lark's code for *Invalid parameter* on this family — the answer a type= value that does not
#: fit the token produces, and the bare code this surface answered before it explained it.
INVALID_PARAMETER_CODE = "1063001"

#: Why an owner could not be reported — stated, never synthesized.
OWNER_UNAVAILABLE_READ_FAILED = (
    "the owner was not read: drive/v1/metas/batch_query failed ({error}). The member list "
    "below is complete; the owner is simply unknown here, and it is NOT the empty list's "
    "explanation."
)

#: Why an owner is absent when the caller declined the leg.
OWNER_UNAVAILABLE_NOT_ASKED = (
    "the owner was not read because with_owner=False was asked for, so this listing carries "
    "the member rows only — and the owner is not one of them."
)


class DriveAccessWriteClient(CredentialedRawHttpClient):
    """The Drive surface's access-management client: **who may use this document**.

    **WRITE credentials only**, resolved through :func:`~larkdocio.common.auth.
    get_write_credentials`; nothing here consults, infers or falls back to the READ pair, and a
    denial is surfaced with Lark's own code and message rather than retried on another pair.

    Throttled by the same evidence-anchored limiter the enumeration client rides, so every
    Drive leg paces alike — and each op makes at most three calls (a write, a read-back, and
    for the member read an optional owner leg), because a lever over who can read a document is
    not a thing to be gentle about only in prose.

    {D15}
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
        resolver=None,
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
        #: The address -> id route, injectable for tests. ``None`` means the SHIPPED
        #: ``resolve_colleague``, ridden on this client's OWN credential pair.
        self._resolver = resolver

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
                f"Drive access write client: no WRITE credentials resolved. Set "
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

    # ----------------------------------------------------------------- #
    # The lifecycle.                                                     #
    # ----------------------------------------------------------------- #

    def grant_access(self, file_token, *, email=None, open_id=None,
                     perm: str = "view", obj_type=None) -> AccessOutcome:
        """Put a human on this object at ``perm``, and **read the member list back**.

        ``POST /open-apis/drive/v1/permissions/:file_token/members?type=<obj_type>
        &need_notification=false`` with ``{{"member_type": "openid", "member_id": …,
        "perm": …}}`` — the request shape measured at ``captures/707-`` — followed by an
        independent ``GET`` of the member list, which is what the returned
        :class:`~larkdocio.drive.access.AccessOutcome` judges ``stored`` by.

        ``perm`` is one of {PERMS}. **``full_access`` is the manage level**; it was measured
        granted and read back on the first attempt, and ``edit`` and ``view`` ride the same
        route.

        **THE GRANTEE.** Exactly one of ``email`` / ``open_id``.

        **THE OBJECT TYPE — ``obj_type``, EXPLICIT RATHER THAN INFERRED, and defaulting to
        ``docx``.** Pass larkdocio's own word (``docx`` / ``sheets`` / ``base``) or Lark's
        (``docx`` / ``sheet`` / ``bitable``), or hand ``file_token`` the object's **URL** and
        the type is read off it with the token in one parse. **Why not inferred from the
        token:** every Lark token is the same unbroken run of letters and digits whatever it
        points at, so there is nothing in one to read — a library that guessed would be
        guessing about which object it is changing who can read. The resolution is one function
        (:func:`~larkdocio.drive.access.object_target`) and every verb on this client takes the
        same argument.

        {BARE_NAME}

        {EMPTY_LIST}

        {TRANSFER}

        {GROUPS}

        {TYPES}

        {D15}
        """
        file_token, wire_type = object_target(file_token, obj_type)
        perm = check_perm(perm)
        open_id = grantee_id(email=email, open_id=open_id,
                             resolver=self._resolver or self.resolve_grantee_email)
        self._call("POST", members_path(file_token),
                   body={"member_type": MEMBER_TYPE, "member_id": open_id, "perm": perm},
                   params={"type": wire_type, "need_notification": NEED_NOTIFICATION},
                   context="drive grant_access", obj_type=wire_type)
        return self._outcome(file_token, open_id, requested_perm=perm, obj_type=wire_type)

    def update_access(self, file_token, *, email=None, open_id=None,
                      perm: str = "view", obj_type=None) -> AccessOutcome:
        """Raise or lower an existing member's level, and **read it back**.

        ``PUT …/members/{{open_id}}?type=<obj_type>&need_notification=false`` with
        ``{{"member_type": "openid", "perm": …}}`` — one route for both directions, measured
        raising ``edit`` -> ``full_access`` (``captures/731-``/``732-``) and lowering
        ``full_access`` -> ``view`` (``733-``/``734-``), each confirmed by an independent list
        read.

        The same grantee rule as :meth:`grant_access`: exactly one of ``email`` / ``open_id``,
        and a bare display name is refused before any call — and the same ``obj_type`` rule,
        resolved by the same one function.
        """
        file_token, wire_type = object_target(file_token, obj_type)
        perm = check_perm(perm)
        open_id = grantee_id(email=email, open_id=open_id,
                             resolver=self._resolver or self.resolve_grantee_email)
        self._call("PUT", member_path(file_token, open_id),
                   body={"member_type": MEMBER_TYPE, "perm": perm},
                   params={"type": wire_type, "need_notification": NEED_NOTIFICATION},
                   context="drive update_access", obj_type=wire_type)
        return self._outcome(file_token, open_id, requested_perm=perm, obj_type=wire_type)

    def revoke_access(self, file_token, *, email=None, open_id=None,
                      obj_type=None) -> AccessOutcome:
        """Take the grant back, and **prove it on a read** rather than on the delete's code.

        ``DELETE …/members/{{open_id}}?type=<obj_type>&member_type=openid``
        (``captures/736-``), followed by the independent member read that measured ``items:
        []`` (``737-``) — a revoke leaves an **empty list, not a tombstone**. The returned
        outcome reports ``stored`` only when the grantee really is absent from that read.

        *A grant surface that cannot take a grant back is not shippable* — this one can, on
        every type it can grant on (``obj_type``, as on :meth:`grant_access`).
        """
        file_token, wire_type = object_target(file_token, obj_type)
        open_id = grantee_id(email=email, open_id=open_id,
                             resolver=self._resolver or self.resolve_grantee_email)
        self._call("DELETE", member_path(file_token, open_id),
                   params={"type": wire_type, "member_type": MEMBER_TYPE},
                   context="drive revoke_access", obj_type=wire_type)
        return self._outcome(file_token, open_id, requested_perm=None, obj_type=wire_type)

    def list_members(self, file_token, *, with_owner: bool = True,
                     obj_type=None) -> MemberListing:
        """Who is on this object — **and who owns it**.

        ``GET /open-apis/drive/v1/permissions/:file_token/members?type=<obj_type>``, plus
        (unless ``with_owner=False``) one ``POST /open-apis/drive/v1/metas/batch_query`` for the
        owner — which takes the **same** type in its own ``doc_type`` key, so both legs address
        the same object rather than one of them silently asking about a docx.

        {OWNER}

        The owner leg **degrades rather than fails**: where it cannot be read, ``owner_id`` is
        honestly ``None`` with the reason in ``owner_note``, and the member rows still come
        back.

        {MEMBER_V1}
        """
        file_token, wire_type = object_target(file_token, obj_type)
        response = self._call("GET", members_path(file_token),
                              params={"type": wire_type}, context="drive list_members",
                              obj_type=wire_type)
        items = ((response.get("data") or {}).get("items")) or []
        members = tuple(Member.from_payload(item) for item in items if isinstance(item, dict))
        owner_id, owner_note = None, OWNER_UNAVAILABLE_NOT_ASKED
        if with_owner:
            owner_id, owner_note = self._read_owner(file_token, wire_type)
        return MemberListing(file_token=str(file_token), members=members,
                             owner_id=owner_id, owner_note=owner_note)

    # ----------------------------------------------------------------- #
    # The copy lever.                                                    #
    # ----------------------------------------------------------------- #

    def set_copy_permissions(self, file_token, *, copy_entity: Optional[str] = None,
                             security_entity: Optional[str] = None,
                             obj_type=None) -> CopyPermissions:
        """Move the document settings whose names govern copying — **one key per call**.

        ``PATCH /open-apis/drive/v2/permissions/:file_token/public?type=<obj_type>`` with a body of
        exactly one key (``captures/709-``, ``711-``), then ONE independent ``GET`` of the same
        route, which is what the returned
        :class:`~larkdocio.drive.access.CopyPermissions` judges ``stored`` by. A multi-key body
        is unmeasured on this route and is never sent.

        The accepted value set is fenced to what was measured: {VALUES}. A fresh docx is born
        with both keys at ``anyone_can_edit`` — Lark's spelling of *only people who can EDIT
        may copy* — and both were measured storing ``anyone_can_view``.

        {NO_SWALLOW}

        {LOCK_SWITCH}

        {EXTERNAL}

        {CLIPBOARD}
        """
        file_token, wire_type = object_target(file_token, obj_type)
        asked = check_copy_settings(copy_entity=copy_entity, security_entity=security_entity)
        for key, value in asked:
            self._call("PATCH", public_path(file_token), body={key: value},
                       params={"type": wire_type}, context="drive set_copy_permissions",
                       obj_type=wire_type)
        read_back = self._call("GET", public_path(file_token), params={"type": wire_type},
                               context="drive set_copy_permissions read-back",
                               obj_type=wire_type)
        public = ((read_back.get("data") or {}).get("permission_public")) or {}
        settings = tuple(CopySetting(key=key, requested=value, stored=public.get(key))
                         for key, value in asked)
        return CopyPermissions(file_token=str(file_token), settings=settings, public=public)

    # ----------------------------------------------------------------- #
    # The legs underneath.                                               #
    # ----------------------------------------------------------------- #

    def resolve_grantee_email(self, *, email):
        """The address -> id leg, on **this client's own credential pair**.

        The shipped ``resolve_colleague`` — never a second resolver — handed a contacts client
        built from the WRITE pair, which is the pair the measurement itself was made on
        (a recording in the dev repo, not among the published
        permissions-spike captures). No credential pair is mixed and none is fallen back to.

        Imported at module level rather than inside this method on purpose: the permission
        derivation walks a call site's own source, and a leg whose endpoint is reachable only
        through a function-local import would project as needing no permission at all.
        """
        contacts = ContactsSearchClient(self._app_id, self._app_secret, self._domain)
        return resolve_colleague(email=email, client=contacts)

    def _read_owner(self, file_token, obj_type=DEFAULT_OBJECT_TYPE):
        """``(owner_id, note)`` from ``drive/v1/metas/batch_query`` — honest ``None`` on any
        failure, because a synthesized owner would be worse than an admitted unknown.

        ``obj_type`` is the SAME resolved wire type the member read used: this endpoint's
        ``doc_type`` key takes Lark's own vocabulary, and a leg still saying ``docx`` about a
        Base would answer about nothing at all.
        """
        try:
            response = self._call(
                "POST", ops.METAS_BATCH_QUERY_ENDPOINT,
                body={"request_docs": [{"doc_token": str(file_token),
                                        "doc_type": obj_type}], "with_url": False},
                context="drive list_members owner", obj_type=obj_type)
            data = response.get("data") or {}
            metas = data.get("metas") or []
            owner = (metas[0].get("owner_id") if metas else None) or None
            if owner is None:
                # An empty `metas` here is a REFUSAL wearing a code:0 — the per-token verdict
                # lives in `failed_list` — so Lark's own reason is appended rather than leaving
                # "no owner_id" to read as a fact about the object (LD-606).
                return None, OWNER_UNAVAILABLE_READ_FAILED.format(
                    error=("the metadata answered with no owner_id. "
                           + failed_reason(data, str(file_token))))
            return owner, None
        except Exception as exc:  # noqa: BLE001 - the owner degrades; the member read does not
            return None, OWNER_UNAVAILABLE_READ_FAILED.format(error=exc)

    def _outcome(self, file_token, open_id, *, requested_perm,
                 obj_type=DEFAULT_OBJECT_TYPE) -> AccessOutcome:
        """The read-back that turns an accepted call into a **verdict** — on the same object
        the write addressed, which is why the resolved type travels with it."""
        listing = self.list_members(file_token, with_owner=False, obj_type=obj_type)
        return AccessOutcome(
            file_token=str(file_token), open_id=open_id, listing=listing,
            requested_perm=requested_perm, stored_perm=listing.perm_of(open_id))

    def _call(self, method, path, *, body=None, params=None, context, obj_type=None):
        self._limiter.acquire()
        self._api_calls += 1
        response = self._send(method, path, body=body, params=params)
        code = response.get("code") if isinstance(response, dict) else None
        if not (code in (0, None) or str(code) == "0"):
            if str(code) == INVALID_PARAMETER_CODE:
                # THE ONE PLACE LARK'S OWN CODE IS ANNOTATED RATHER THAN RELAYED BARE. Lark's
                # code and msg are preserved verbatim — they are the evidence — and the library
                # adds what that code means on this family and which knob answers it. Built
                # through the shared `api_error` seam so the classification (and a denial's
                # console link) is exactly what every other surface produces.
                message = (f"{context} failed: Code: {code}, "
                           f"Msg: {response.get('msg')}. "
                           f"{INVALID_PARAMETER_MEANS.format(obj_type=obj_type)}")
                raise api_error(message, code=code, msg=response.get("msg"), body=response,
                                credential_env=WRITE_ENV)
            raise_for_lark_code(response, context=context, credential_env=WRITE_ENV)
        return response if isinstance(response, dict) else {}


DriveAccessWriteClient.__doc__ = (DriveAccessWriteClient.__doc__ or "").format(
    D15=NOT_A_SCOPE_ESCALATION)
DriveAccessWriteClient.grant_access.__doc__ = (
    DriveAccessWriteClient.grant_access.__doc__ or "").format(
        PERMS=MEMBER_PERMS, BARE_NAME=BARE_NAME_REFUSAL, EMPTY_LIST=MEMBER_LIST_AT_BIRTH,
        TRANSFER=OWNERSHIP_TRANSFER_NOT_SHIPPED, GROUPS=GROUPS_UNMEASURED,
        TYPES=OBJECT_TYPES_MEASURED, D15=NOT_A_SCOPE_ESCALATION)
DriveAccessWriteClient.update_access.__doc__ = (
    DriveAccessWriteClient.update_access.__doc__ or "").format()
DriveAccessWriteClient.revoke_access.__doc__ = (
    DriveAccessWriteClient.revoke_access.__doc__ or "").format()
DriveAccessWriteClient.list_members.__doc__ = (
    DriveAccessWriteClient.list_members.__doc__ or "").format(
        OWNER=OWNER_IS_NOT_A_MEMBER, MEMBER_V1=MEMBER_FAMILY_IS_V1)
DriveAccessWriteClient.set_copy_permissions.__doc__ = (
    DriveAccessWriteClient.set_copy_permissions.__doc__ or "").format(
        VALUES=MEASURED_COPY_VALUES, NO_SWALLOW=THE_ROUTE_DOES_NOT_SWALLOW,
        LOCK_SWITCH=LOCK_SWITCH_READ_ONLY, EXTERNAL=EXTERNAL_ACCESS_REFUSED_HERE,
        CLIPBOARD=CLIPBOARD_UNOBSERVABLE)
