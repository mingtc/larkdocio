"""larkdocio.drive.access — WHO may use a docx the app created: the models, the policy, and
the disclosures that ship with them (LD-432).

**The fact this surface exists for.** The bot is the **owner** of what it mints without being a
member row, and who *else* is on a fresh document depends on where it was filed: created with no
folder it has **no member rows at all**, and created into a folder it carries the folder's,
each marked ``perm_type='container'`` (:data:`MEMBER_LIST_AT_BIRTH` — both cases measured). So
nobody is on such a document *at a level anyone chose* until this surface puts them there. This
module carries the vocabulary for the surface that
fixes that (:mod:`larkdocio.drive.access_write`): the three measured member levels, the two
document settings whose names govern copying, the typed refusals, and the sentences that say
exactly how far the measurements reach.

**The measurement rule, applied without exception.** ``code: 0`` proves **acceptance** and
nothing else; the verdict is always the **separate read-back**. This is not a nicety here: the
spike that measured these routes caught a live **swallow** on the member family — a re-add
answered ``code 0`` with a complete member echo and the independent read-back did not carry it.
Every op on this surface therefore reads its own work back and reports what it *found*, not
what Lark *echoed*.

**Read the module's own words for what it cannot do** — :data:`CLIPBOARD_UNOBSERVABLE`,
:data:`GROUPS_UNMEASURED`, :data:`OBJECT_TYPES_MEASURED`, :data:`TENANT_TOKEN_ONLY`,
:data:`OWNERSHIP_TRANSFER_NOT_SHIPPED`, :data:`LOCK_SWITCH_READ_ONLY`,
:data:`EXTERNAL_ACCESS_REFUSED_HERE` — collected as data in :data:`ABSENCES` so they can be
projected rather than paraphrased.

A capture cited below as ``captures/NNN-`` lives at ``tests/captures/permissions-spike/captures/``
**in the source repository** (LD-420), not in the wheel — except the folder-grant and
member-listing captures 600 to 602 and 620 to 622, which are at
``tests/captures/ld494-app-space-census/captures/`` in the same repository. The transfer's own
calls and the repeat delete were not carried over; the refusal states what they measured.
"""
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from larkdocio.drive import ops
from larkdocio.drive.errors import DriveError

#: The object type a caller who names none gets. **Declared, never inferred**: a Lark token is
#: an unbroken run of letters and digits whatever it points at, so a bare token carries no type
#: to read — and docx is what every caller of this surface addressed before LD-456.
DEFAULT_OBJECT_TYPE = "docx"

#: Kept for the callers and tests that named the docx value directly. It is no longer *the*
#: type this surface sends — see :data:`OBJECT_TYPES_MEASURED` — only docx's own spelling.
DOCX_TYPE = DEFAULT_OBJECT_TYPE

#: **The values this surface will put on the wire**, in Lark's own vocabulary (LD-456).
WIRE_OBJECT_TYPES: Tuple[str, ...] = ("docx", "sheet", "bitable")

#: **Every spelling a caller may hold → the value Lark wants.** larkdocio's own surface
#: vocabulary (``sheets`` / ``base`` — :data:`larkdocio.common.url.URL_TYPE_SURFACES`) and
#: Lark's Drive vocabulary (``sheet`` / ``bitable`` — the same seam
#: :data:`larkdocio.drive.dispatch.SEAM` translates) are BOTH accepted, so neither side's word
#: is the one a caller had to have known. Matching is case-insensitive and space-trimmed.
OBJECT_TYPE_ALIASES = {
    "docx": "docx",
    "sheet": "sheet", "sheets": "sheet", "spreadsheet": "sheet",
    "bitable": "bitable", "base": "bitable",
}

#: **The URL type → the wire type.** ``larkdocio.common.url.validate_download_url`` reports the
#: surface a link names; these three are the ones this family can address. ``docs``, ``wiki``
#: and ``drive`` are recognised URLs whose type this surface does not send, and each is refused
#: by name rather than mapped onto a neighbour.
URL_OBJECT_TYPES = {"docx": "docx", "sheets": "sheet", "base": "bitable"}

#: The one grantee kind measured: an ``open_id``, sent as ``member_type: "openid"``.
MEMBER_TYPE = "openid"

#: The three member levels, **all three measured route with independent read-backs**
#: (``captures/707-``/``708-`` for ``full_access``, ``729-``/``730-`` for ``edit``,
#: ``733-``/``734-`` for ``view``). ``full_access`` is the manage level the primary use case
#: asks for; the other two ride the same route.
MEMBER_PERMS: Tuple[str, ...] = ("view", "edit", "full_access")

#: The two document settings whose names govern copying, and the only two this surface sets.
COPY_LEVER_KEYS: Tuple[str, ...] = ("copy_entity", "security_entity")

#: The value set **fenced to what was measured** on those two keys: the baseline a fresh docx
#: is born with (``anyone_can_edit``) and the value both keys were observed storing
#: (``anyone_can_view`` — ``captures/709-``–``712-``). Any other spelling is UNMEASURED and is
#: refused locally rather than sent, because a value this library never observed being stored
#: is not a value it can report as stored.
MEASURED_COPY_VALUES: Tuple[str, ...] = ("anyone_can_edit", "anyone_can_view")

#: Sent on every member write, exactly as measured — nobody is emailed by this library.
NEED_NOTIFICATION = "false"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OPEN_ID = re.compile(r"^ou_[A-Za-z0-9]+$")


# --------------------------------------------------------------------------- #
# THE DISCLOSURES — authored ONCE here and quoted, never paraphrased.           #
# --------------------------------------------------------------------------- #

# THE REFUSAL A BARE DISPLAY NAME MEETS. The reason is LD-348's and is UNCHANGED — an address
# route is not a name route, and a failed resolve means "unresolved here", never a verdict
# about whether the person exists. What LD-456 changed is the HELP: the refusal used to cite
# two of this library's own source files by line number at a consumer who installed a wheel and
# has no source tree, while denying a capability the library ships one call away. It now NAMES
# that call. Both the issue ids and the source pointers stay in this comment, where the next
# maintainer looks: larkdocio/contacts/__init__.py and larkdocio/contacts/lookup.py's
# MEASURED_REACH carry the ruling. A consumer gets the verb instead.
BARE_NAME_REFUSAL = (
    "A GRANTEE IS AN EMAIL ADDRESS OR AN open_id — GIVE ME ONE OF THOSE. This surface does not "
    "turn a person's display NAME into an id, because an address -> id route is NOT a name -> "
    "id route. THE VERB THAT DOES ANSWER A NAME IS SHIPPED, one call away: "
    "larkdocio.contacts.resolve_user(name='Ada Lovelace') returns exactly one open_id or "
    "refuses in a typed way — pass its answer back here as open_id=... . It stays a separate "
    "call on purpose: it searches the directory on its own scope, and a name that matches two "
    "people is a question only you can settle. And when an ADDRESS does go to the address "
    "route and comes back with nothing, that means the lookup did not resolve it HERE: the "
    "route's measured reach is n = 2 addresses, and whether it answers for an arbitrary member "
    "of a tenant is unmeasured, so an unresolved identifier is never reported as a person who "
    "is absent from the tenant."
)

#: **AC4's trap, stated in the shipped words.** The owner is not a member row.
OWNER_IS_NOT_A_MEMBER = (
    "THE OWNER IS NOT A MEMBER ROW. A document this app owns reads back an EMPTY member list "
    "(captures/702-), while drive/v1/metas/batch_query reports owner_id as the app's own bot "
    "open_id (captures/704-). A reader who checked only the member route would conclude the "
    "bot holds nothing, and that reading is wrong — which is why this read reports the owner "
    "alongside the members instead of handing back an unexplained empty list."
)

#: **The constructive fact behind the whole feature** — SUPERSEDED IN ITS CONCLUSION, not in
#: its reason (LD-469; the rule is ``process/doctrine/supersession.md`` § A.1, in the dev repo).
#: LD-432 measured a freshly minted document's member list **empty** and concluded that of every
#: fresh document. The measurement stands and is repeated below; the conclusion does not, because
#: it was taken on a document created with **no folder**. Filing the document changes the answer,
#: so both cases are stated and neither is an unlabelled absolute. The old name of this constant
#: (``EMPTY_MEMBER_LIST``) said the superseded conclusion out loud, which is why it moved too.
MEMBER_LIST_AT_BIRTH = (
    "WHAT A FRESH DOCUMENT'S MEMBER LIST HOLDS DEPENDS ON WHERE IT WAS FILED. WITH NO "
    "folder_token: it really is empty — by default nobody but the bot is on it (captures/702- "
    "— code 0, items: [], re-measured 2026-08-15 on a self-created disposable), which is why "
    "such a document needs a grant before a human can do anything with it. FILED INTO A FOLDER "
    "(create_document(folder_token=...)): the document INHERITS the folder's access, and every "
    "inherited row comes back marked perm_type='container' — measured 2026-08-15, one "
    "full_access row inherited from a folder created moments earlier, and three rows (two "
    "accounts plus a CHAT holding edit) on a folder already shared with people. Those rows are "
    "the FOLDER's; a grant here is still what puts a named human on the document at a level you "
    "chose."
)

#: **The one claim this surface must never make.** Stated as the hypothesis it is.
CLIPBOARD_UNOBSERVABLE = (
    "WHAT THIS LIBRARY CANNOT TELL YOU: whether a human's clipboard then obeys. No endpoint "
    "reachable with a tenant token reports the effect of a member level or of these document "
    "settings on copying, printing or pasting in the Lark client, so this surface reports what "
    "STORED and says nothing about what a person can then do. The mechanism HYPOTHESIS — that "
    "a view-level member on a document whose copy_entity/security_entity default to "
    "anyone_can_edit is the reported pain — is consistent with every measurement here and "
    "proven by none of them; only a human's own attempt can close it."
)

#: **D-15 in one sentence**, and the distinction that makes it true.
NOT_A_SCOPE_ESCALATION = (
    "THIS GRANTS A HUMAN ACCESS TO AN OBJECT THE BOT OWNS. It never widens, requests or "
    "escalates the APP's own scope: granting a person a member level on the app's own document "
    "is ordinary use of an already-granted capability, while granting the app a scope is a "
    "Lark console action this library never takes and has no code path for."
)

#: **AC7 — ownership transfer is REPORTED, never shipped.** Measured not clean.
OWNERSHIP_TRANSFER_NOT_SHIPPED = (
    "OWNERSHIP TRANSFER IS NOT OFFERED HERE, and the reason is a measurement rather than a "
    "preference. The transfer STORES (it answered code 0 and the owner read back afterwards was "
    "the grantee) and is one-way from the app's side: afterwards the app cannot delete the "
    "document (1062501, captures/756-, and again on a repeat attempt), re-adding "
    "the app as a full_access member is accepted and NOT stored — a measured swallow "
    "(captures/759- accepted, 760- read back without it) — and transferring ownership back is "
    "denied (1063002, captures/761-). It cost that probe a document only its new human owner "
    "can remove. Forms tried: remove_old_owner=false, transfer to the grantee then back to the "
    "bot, and a member re-add. NOT tried, and therefore unmeasured rather than impossible: "
    "remove_old_owner=true, transferring to a third party, any admin or console route, and any "
    "user_access_token route."
)

#: **AC8 — groups.** One synthetic-id call is not evidence about the member_type.
GROUPS_UNMEASURED = (
    "GROUP AND DEPARTMENT GRANTEES ARE UNMEASURED, NOT REFUSED. Exactly one call was ever made "
    "with member_type: opendepartmentid (captures/735-) and it carried a deliberately SYNTHETIC "
    "department id, so its 1063001 refusal cannot be attributed to the member_type rather than "
    "to the fake id. No real department id, no chat id and no other group type was tried at "
    "all, so nothing here says whether a group grant works."
)

#: **The object types this surface addresses — SUPERSEDED IN PART by LD-456.**
#:
#: LD-432 shipped this row as *docx only*. Per the supersession doctrine (in the dev repo,
#: ``process/doctrine/supersession.md`` § A.1) the
#: **original reason is preserved verbatim inside the text below** and only the **conclusion**
#: moves: that reason was *"every measurement was made with type=docx"* — a statement about the
#: evidence, never a finding that another type would fail — and LD-456 made the missing
#: measurements. The old conclusion's second half ("no method here takes an object-type
#: argument") was the construction that made the gap unfixable from outside, and it is what the
#: ``obj_type`` parameter replaces.
OBJECT_TYPES_MEASURED = (
    "THE OBJECT TYPE IS A PARAMETER (obj_type=), AND THE MEASURED SET IS docx, sheet AND "
    "bitable (Base). THIS SUPERSEDES AN EARLIER, NARROWER ROW, whose reason is kept rather "
    "than struck: 'Every measurement behind this surface was made with type=docx, and no "
    "method here takes an object-type argument, so no other type can reach the wire.' That was "
    "a statement about the EVIDENCE — not a finding that another type fails — and the "
    "measurements it was missing have since been made, against objects a live gate created and "
    "deleted in the same run: a member read at birth, a grant and a revoke on BOTH a "
    "spreadsheet (type=sheet) and a Base (type=bitable), plus a level update on the Base, each "
    "judged by its own independent read-back exactly as the docx path is — and, as that gate's "
    "own control, each of those tokens addressed as docx still answers Lark's 1063001, which "
    "is the failure this parameter exists to end. "
    "STILL UNMEASURED, and therefore refused locally by name rather than sent: file, "
    "wiki and every other type= value these routes may know. Unmeasured is not impossible — "
    "extending the surface to one of them needs its own measurements, and the refusal says so. "
    "FOLDER IS THE ONE THAT IS NO LONGER UNMEASURED, and the measurement went the other way: a "
    "grant addressed to the member route as type=folder was REFUSED BY LARK — HTTP 403, 1063002 "
    "— on three enumerated write spellings, so it is still refused locally here, now on "
    "evidence rather than on silence. The refusal message carries that measurement and the "
    "scope it was made in."
)

#: **What a type outside the measured set is told — locally, before a call is spent.** It names
#: what IS supported, in both vocabularies; it says what to do with the two types a caller most
#: often holds (a wiki node, a folder); and it says *unmeasured*, never *impossible*.
#:
#: **The FOLDER clause is SUPERSEDED IN PART by LD-500.**
#: Every path named below lives **in the dev repo** (the maintainers' private record), never
#: in the wheel. Per the supersession doctrine
#: (``process/doctrine/supersession.md`` § A.1) the **reason is preserved and only the
#: conclusion moves**: the reason — *an unmeasured type is refused locally rather than guessed
#: onto the wire* — is untouched and still governs ``file``, ``wiki`` and every other value (see
#: :data:`OBJECT_TYPES_MEASURED`). What moved is the conclusion about ``folder`` alone: the
#: clause this replaces declared the container question wholly unasked here and claimed nothing
#: about it. It is quoted verbatim exactly ONCE, in the guard that retired it —
#: ``tests/test_drive_folder_grant_refutation.py``'s ``SUPERSEDED_CLAUSE``, which is also the
#: census that reddens if it comes back anywhere in the shipped corpus. On 2026-08-17 the LD-494
#: leg measured the grant and Lark **refused the write**
#: (``tests/captures/ld494-app-space-census/captures/600-``..``602-``, read addendum ``620-``..``622-``).
#: **The claim is bounded by a MISSING ORACLE** (``process/doctrine/negative-claims.md`` § A.1):
#: it is *Lark refused the write*, never *the grant did not store*, because this tenant has no
#: folder member-read at all — the route's own ``type`` enum omits ``folder`` — so the read that
#: would separate those two readings never existed. The two contradictory ``99992402`` bodies
#: are both reported here and neither is reconciled away.
OBJECT_TYPE_UNSUPPORTED = (
    "obj_type={asked!r} is not one of the object types this access surface has measured "
    "({measured}). Say it in either vocabulary — larkdocio's own docx / sheets / base, or "
    "Lark's own docx / sheet / bitable — or hand this surface the object's URL and the type is "
    "read from it. WHAT TO DO WITH THE TWO THAT ARE NOT HERE: a WIKI node is a wrapper around "
    "an object of another type, so resolve it to the underlying token and type first and grant "
    "on that; a FOLDER is the one type here that is no longer an open question — LARK REFUSED "
    "THE WRITE. On 2026-08-17, on ONE tenant, with ONE application identity and a "
    "tenant_access_token (the write pair), a grant sent to "
    "drive/v1/permissions/<token>/members?type=folder answered HTTP 403 · 1063002 'Permission "
    "denied' on THREE enumerated write spellings: full_access with need_notification false; the "
    "view level; and the same body with need_notification omitted entirely (captures/600- 601- "
    "602-). THAT CLAIM IS 'LARK REFUSED THE WRITE' AND NOTHING WIDER — it is NOT that the grant "
    "failed to store, because the read that would tell those two apart does not exist on that "
    "tenant: the member listing answered 99992402 for type=folder and its own field_violations "
    "printed the route's own type enum — doc, sheet, file, wiki, bitable, docx, mindnote, "
    "minutes, slides — which does not contain folder, while the same listing sent with no type "
    "at all answered 99992402 'type is required'. Those two bodies contradict each other; both "
    "were captured and neither was reconciled away (captures/620- 621- 622-). Outside that "
    "date, that tenant, that application identity, that token kind, that route and that "
    "spelling set, nothing is refuted: no grant was ever attempted on a raw uploaded file, on a "
    "wiki node, or on any other type. Every type outside the measured set is UNMEASURED on this "
    "family, not proven impossible: it is refused here rather than guessed onto the wire, "
    "because a value this library never observed storing is not one it could report as stored. "
    "Folder is refused here for the neighbouring reason — Lark refused it where it was asked."
)

#: **What a URL and an explicit ``obj_type`` that disagree are told.** Never reconciled: one of
#: the two is wrong and only the caller knows which.
OBJECT_TYPE_DISAGREEMENT = (
    "the url names a {from_url} object and obj_type={asked!r} says {from_arg} — they disagree, "
    "and this surface will not pick one for you. Granting on the wrong object is not an error "
    "that shows up as an error: Lark answers about whichever object the token really is. Drop "
    "the obj_type and let the url speak, or pass the bare token with the obj_type you mean."
)

#: **What Lark's own 1063001 means on this family**, added to Lark's verbatim code and message
#: rather than replacing them. This is the sentence whose absence made the failure that earned
#: this surface's widening unreadable: a bare *Invalid parameter* with no library voice at all.
INVALID_PARAMETER_MEANS = (
    "WHAT 1063001 MEANS HERE: it is the code this permission family answers when the request "
    "does not fit the object — and the type= value is the part of it this library sends on "
    "your behalf. This call sent type={obj_type!r}. If that is not what the token actually is, "
    "say which it is — obj_type='docx' | 'sheets' | 'base' (Lark's own 'sheet' / 'bitable' are "
    "accepted too), or pass the object's url instead of the bare token and the type is read "
    "from it. A bare token carries no type: every Lark token is the same alphabet whatever it "
    "points at, so this library asks rather than guesses. The same code is also what an "
    "unsupported KEY gets on the neighbouring settings route, so it is not by itself proof "
    "that the type was the problem."
)

#: **AC8 — the principal, and the aliasing that forbids a scope-separation claim.**
TENANT_TOKEN_ONLY = (
    "EVERY MEASUREMENT HERE WAS MADE WITH A tenant_access_token, on ONE tenant and ONE app. A "
    "user_access_token is a different principal with a different permission model and nothing "
    "here predicts it — untried, therefore unmeasured. And because on the tenant these "
    "measurements were made on the READ and WRITE credential pairs aliased one app, no "
    "scope-separation claim may be drawn from anything measured on it."
)

#: **AC5 — lock_switch.** Returned by the GET, refused by the PATCH.
LOCK_SWITCH_READ_ONLY = (
    "lock_switch IS READ-ONLY ON THIS PATCH ROUTE. The GET returns it and the PATCH refuses it "
    "with 1063001 — the SAME code an invented key gets (captures/721-, 725-). Two forms were "
    "tried: the value true as a JSON boolean, and the key alone in the body. Any other "
    "spelling, body type or route is unmeasured, so this surface offers no way to set it "
    "rather than claiming it cannot be set."
)

#: **AC5 — external_access_entity.** Refused here, and left refused.
EXTERNAL_ACCESS_REFUSED_HERE = (
    "external_access_entity WAS REFUSED HERE WITH 91009 (captures/715-), with an empty msg, "
    "and the baseline value was unchanged on the read-back. One form was tried: "
    "closed -> open, alone in the body. No attempt was made to acquire whatever would lift "
    "that refusal, so it ships as a documented fact rather than as an option."
)

#: **AC4 — the route family, with the one spelling that was tried.**
MEMBER_FAMILY_IS_V1 = (
    "THE MEMBER FAMILY IS v1. drive/v2/permissions/{token}/members answered '404 page not "
    "found' as PLAIN TEXT — not a Lark error envelope — so it is not a route at all "
    "(captures/703-). One spelling was tried. Only the PUBLIC settings family is v2, which is "
    "why the two halves of this surface sit on different API versions."
)

#: **AC5 / D-59 — why an accepted value may be read as a stored value on this route.**
THE_ROUTE_DOES_NOT_SWALLOW = (
    "THIS ROUTE DOES NOT SWALLOW, AND THAT GUARANTEE IS SCOPED TO THIS ROUTE. An INVENTED key "
    "sent to drive/v2/permissions/{token}/public was REFUSED with 1063001 rather than accepted "
    "and ignored (captures/725-), and a positive control moved on the same round — so on this "
    "route an accepted value really is a stored value. Nothing about any other route follows "
    "from it: the neighbouring member family produced a measured swallow, which is why every "
    "op on this surface still reads its own work back."
)

#: The absences, as **data** rather than as scattered prose — projected by the guide and the
#: capability surface instead of being restated in either.
ABSENCES: Tuple[str, ...] = (
    CLIPBOARD_UNOBSERVABLE,
    OWNERSHIP_TRANSFER_NOT_SHIPPED,
    GROUPS_UNMEASURED,
    OBJECT_TYPES_MEASURED,
    TENANT_TOKEN_ONLY,
    LOCK_SWITCH_READ_ONLY,
    EXTERNAL_ACCESS_REFUSED_HERE,
    MEMBER_FAMILY_IS_V1,
)


class AccessRefusedError(DriveError):
    """A refusal larkdocio makes **locally, before spending a call**.

    Only ever raised for something this library can decide on its own: which question the
    caller meant (an email or an ``open_id``, exactly one), an identifier that is neither, a
    member level outside the three measured ones, and a copy-lever value outside the two
    measured ones. Lark's own refusals are never impersonated here — those arrive from the
    wire with Lark's code and message.
    """

    def __init__(self, message, *, value=None):
        super().__init__(message)
        self.value = value


# --------------------------------------------------------------------------- #
# The wire paths — the registry's own constants with the token substituted.     #
# --------------------------------------------------------------------------- #

def members_path(file_token) -> str:
    """The tokenised wire path for one document's permission members (v1)."""
    return ops.PERMISSION_MEMBERS_ENDPOINT.replace(":file_token", str(file_token))


def member_path(file_token, open_id) -> str:
    """One member's own path — the members path with the grantee's ``open_id`` appended."""
    return f"{members_path(file_token)}/{open_id}"


def public_path(file_token) -> str:
    """The tokenised wire path for one document's PUBLIC settings (v2)."""
    return ops.PERMISSION_PUBLIC_ENDPOINT.replace(":file_token", str(file_token))


# --------------------------------------------------------------------------- #
# The gates — every one of them decided BEFORE any request is built.            #
# --------------------------------------------------------------------------- #

def check_object_type(obj_type) -> str:
    """One caller-supplied ``obj_type`` → the value Lark wants, or a typed refusal.

    Accepts either vocabulary (:data:`OBJECT_TYPE_ALIASES`), case-insensitively. Anything else
    is refused **locally**, with :data:`OBJECT_TYPE_UNSUPPORTED` — the same posture
    :func:`check_perm` takes and for the same reason: a type this surface has never observed
    storing is not one it could report as stored, so it is not sent.
    """
    value = "" if obj_type is None else str(obj_type).strip().lower()
    wire = OBJECT_TYPE_ALIASES.get(value)
    if wire is None:
        raise AccessRefusedError(
            OBJECT_TYPE_UNSUPPORTED.format(asked=obj_type, measured=", ".join(
                WIRE_OBJECT_TYPES)),
            value=obj_type)
    return wire


def object_target(file_token, obj_type=None) -> Tuple[str, str]:
    """``(token, wire_type)`` for one object — **the one place a type is decided.**

    Three ways in, in the order a caller reaches for them:

    1. **A URL** (whatever a human pasted). Parsed by the shipped
       :func:`larkdocio.common.url.validate_download_url`, which already reports which surface a
       link names, so the type and the token come out of ONE parse and the caller needs no type
       vocabulary at all. A recognised URL whose type this family cannot address (``docs``,
       ``wiki``, ``drive``) is refused by name.
    2. **A bare token plus ``obj_type``** — in larkdocio's vocabulary (``docx`` / ``sheets`` /
       ``base``) or Lark's (``docx`` / ``sheet`` / ``bitable``).
    3. **A bare token alone** → :data:`DEFAULT_OBJECT_TYPE` (``docx``). **Declared, not
       inferred**: every Lark token is one unbroken run of letters and digits whatever it points
       at, so there is nothing in a token to read a type off — and inventing an inference would
       be exactly the guess this surface refuses everywhere else. docx is the type every caller
       of this surface addressed before the parameter existed, so the default is also the
       compatible answer.

    A URL and an ``obj_type`` that **disagree** are refused rather than reconciled
    (:data:`OBJECT_TYPE_DISAGREEMENT`): granting on the wrong object does not surface as an
    error, so a silent pick would be the worst of the three answers.
    """
    text = "" if file_token is None else str(file_token).strip()
    if "://" in text:
        from larkdocio.common.url import validate_download_url

        _domain, url_type, token = validate_download_url(text)
        wire = URL_OBJECT_TYPES.get(url_type)
        if wire is None:
            raise AccessRefusedError(
                OBJECT_TYPE_UNSUPPORTED.format(
                    asked=url_type, measured=", ".join(WIRE_OBJECT_TYPES)),
                value=url_type)
        if obj_type is not None:
            asked = check_object_type(obj_type)
            if asked != wire:
                raise AccessRefusedError(
                    OBJECT_TYPE_DISAGREEMENT.format(from_url=url_type, asked=obj_type,
                                                    from_arg=asked),
                    value=obj_type)
        return token, wire
    if obj_type is None:
        return text, DEFAULT_OBJECT_TYPE
    return text, check_object_type(obj_type)


def check_perm(perm) -> str:
    """The member-level gate: one of the three **measured** levels, or a typed refusal.

    Unlike the version family's ``obj_type`` gate, an unmeasured value is **not** passed
    through to Lark here. A permission level is a claim about who can read a document; sending
    a level nobody has observed and reporting whatever comes back would be this surface
    guessing on the caller's behalf about exactly the thing it exists to be careful with.
    """
    value = "" if perm is None else str(perm).strip()
    if value not in MEMBER_PERMS:
        raise AccessRefusedError(
            f"perm={perm!r} is not one of the three measured member levels "
            f"{MEMBER_PERMS}. full_access is the manage level; edit and view ride the same "
            f"route. Any other value is unmeasured on this family and is not sent.",
            value=perm)
    return value


def grantee_id(*, email=None, open_id=None, resolver=None) -> str:
    """Resolve the grantee to one ``open_id`` — or refuse, **typed and before any call**.

    Exactly one of ``email`` / ``open_id``. An ``open_id`` already in hand is passed straight
    through; an email goes through the **shipped** ``resolve_colleague`` (never a second
    resolver) and its answer is used only when it carries exactly one user.

    {BARE_NAME}
    """
    given = [(kind, value) for kind, value in (("email", email), ("open_id", open_id))
             if isinstance(value, str) and value.strip()]
    if len(given) != 1:
        raise AccessRefusedError(
            "a grant takes EXACTLY ONE of `email` or `open_id`; neither and both are a "
            "caller's bug rather than a question about a person, and neither spends a "
            f"request. {BARE_NAME_REFUSAL}")
    kind, value = given[0]
    value = value.strip()
    if kind == "open_id":
        if not _OPEN_ID.match(value):
            raise AccessRefusedError(
                f"{value!r} is not an open_id (the measured shape is ou_ followed by hex). "
                f"{BARE_NAME_REFUSAL}", value=value)
        return value
    if not _EMAIL.match(value):
        raise AccessRefusedError(
            f"{value!r} is not an email address. {BARE_NAME_REFUSAL}", value=value)
    if resolver is None:
        from larkdocio.contacts.lookup import resolve_colleague as resolver
    lookup = resolver(email=value)
    if getattr(lookup, "user", None) is None:
        from larkdocio.contacts.lookup import (
            MEASURED_REACH,
            UNRESOLVED_IS_UNDIFFERENTIATED,
        )

        detail = getattr(getattr(lookup, "refusal", None), "detail", "")
        raise AccessRefusedError(
            f"the address {value!r} did not resolve to exactly one open_id, so there is "
            f"nobody to grant access to. {UNRESOLVED_IS_UNDIFFERENTIATED} {MEASURED_REACH} "
            f"{detail}".strip(), value=value)
    return lookup.user.open_id


grantee_id.__doc__ = (grantee_id.__doc__ or "").format(BARE_NAME=BARE_NAME_REFUSAL)


def check_copy_settings(copy_entity=None, security_entity=None) -> Tuple[Tuple[str, str], ...]:
    """The copy-lever gate: at least one key, each value inside the **measured** set.

    Returns ``((key, value), …)`` in :data:`COPY_LEVER_KEYS` order — the order the ops sends
    them in, one key per call, because one key per call is how they were measured.
    """
    asked = tuple((key, value) for key, value in
                  (("copy_entity", copy_entity), ("security_entity", security_entity))
                  if value is not None)
    if not asked:
        raise AccessRefusedError(
            "set_copy_permissions needs at least one of `copy_entity` / `security_entity`; a "
            "call that sets nothing would spend a request to change nothing. The measured "
            f"values are {MEASURED_COPY_VALUES}.")
    for key, value in asked:
        if value not in MEASURED_COPY_VALUES:
            raise AccessRefusedError(
                f"{key}={value!r} is outside the measured value set {MEASURED_COPY_VALUES} "
                f"for this route. Other spellings Lark may accept are unmeasured here and are "
                f"not sent, because a value never observed storing cannot be reported stored.",
                value=value)
    return asked


# --------------------------------------------------------------------------- #
# The typed answers.                                                           #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Member:
    """One row of a document's member list, exactly as the measured payload carries it."""

    member_id: str
    member_type: str
    perm: str
    perm_type: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Mapping) -> "Member":
        return cls(
            member_id=payload.get("member_id") or "",
            member_type=payload.get("member_type") or "",
            perm=payload.get("perm") or "",
            perm_type=payload.get("perm_type"),
        )


@dataclass(frozen=True)
class MemberListing:
    """A document's members **plus its owner**, because the owner is not a member row.

    ``owner_id`` is ``None`` — never synthesized, never the bot's id assumed — when the owner
    could not be read, and ``owner_note`` then says why (the same honest-absence shape
    ``CreatedVersion.revision`` uses).
    """

    file_token: str
    members: Tuple[Member, ...] = ()
    owner_id: Optional[str] = None
    owner_note: Optional[str] = None

    def perm_of(self, open_id) -> Optional[str]:
        """The level ``open_id`` currently holds as a MEMBER, or ``None``.

        ``None`` means *not a member row* — which, for the owner, is the normal answer
        (:data:`OWNER_IS_NOT_A_MEMBER`).
        """
        for member in self.members:
            if member.member_id == open_id:
                return member.perm
        return None


@dataclass(frozen=True)
class AccessOutcome:
    """What a grant / update / revoke **actually did**, judged by the read-back.

    ``requested_perm`` is what the caller asked for (``None`` for a revoke). ``stored_perm`` is
    what an **independent** member read then found (``None`` when the grantee is not a member
    row). ``stored`` is the two agreeing — the only thing on this object that answers *did it
    work*, because ``code: 0`` answers *was it accepted*.
    """

    file_token: str
    open_id: str
    listing: MemberListing
    requested_perm: Optional[str] = None
    stored_perm: Optional[str] = None
    accepted: bool = True

    @property
    def stored(self) -> bool:
        return self.stored_perm == self.requested_perm


@dataclass(frozen=True)
class CopySetting:
    """One document setting this call asked for, and what the read-back found."""

    key: str
    requested: str
    stored: Optional[str] = None

    @property
    def stored_ok(self) -> bool:
        return self.stored == self.requested


@dataclass(frozen=True)
class CopyPermissions:
    """The copy-lever result: every key asked for, each judged by the same read-back.

    ``public`` is the whole settings payload the read-back returned, verbatim, so a caller can
    see the neighbouring keys this surface deliberately does not set.
    """

    file_token: str
    settings: Tuple[CopySetting, ...] = ()
    public: Optional[Mapping] = None

    def setting(self, key) -> Optional[CopySetting]:
        for setting in self.settings:
            if setting.key == key:
                return setting
        return None

    @property
    def stored(self) -> bool:
        return bool(self.settings) and all(s.stored_ok for s in self.settings)
