"""larkdocio.base.schema_client — the throttled, typed Base **schema** client.

The third client on the Base surface, and the first that changes a Base's **shape** rather than
its rows: create a Base, rename it, copy it, create a table, batch-create tables, rename a
table. Its data-losing verbs ride a cross-table loss preview and an explicit-consent fence — and
one verb, the **whole-object delete**, deliberately does not, for a stated reason (below).

**A BASE YOU CAN CREATE, YOU CAN DELETE, and the trash-not-purge record keeps its
reason.** The library used to ship no delete for a Base at all. The recorded reason was *"Lark's
route trashes rather than purges, so nothing here offers one"* — and that reason is **kept, and
re-confirmed by measurement**: after a landed delete, ``POST /drive/v1/metas/batch_query`` still
resolves the trashed ``app_token`` with its title and timestamps (probe pack
``tests/captures/ld466-delete-base/``, capture ``ld466-07``). Only the **conclusion** falls, and it falls
because that same trash route is **already shipped twice** — ``WriteClient.delete_document`` and
``SheetsWriteClient.delete_spreadsheet``. So :meth:`BaseSchemaClient.delete_base` ships, and it
ships as a **lifecycle** call (:data:`LIFECYCLE_OPS`) on the whole-object gate those two
establish, **not** on the plan-and-consent fence — the reason is on the method, and it is
structural: a whole Base's loss is not enumerable at plan time and the endpoint is a **Drive**
endpoint, so there is neither a loss list to consent to nor a bitable read-back to verify with.
``create_app`` remains a registered, plan-gated schema op, so the Base's create and destroy are
published under different keys; that asymmetry is stated at :data:`LIFECYCLE_OPS` rather than
smoothed over. **What this buys is the disposables doctrine becoming followable on this
surface**: until this verb shipped, every Base a consumer created for a test was permanent tenant
residue by construction.

**WRITE credentials only.** The pair is resolved through :mod:`larkdocio.common.auth`'s write
getter, which has **no fallback**: a read-only app is never silently promoted to run a write.
``LARK_READ_APP_*`` is never consulted here and is not named anywhere in this module. *The
aliasing rider stands:* on the tenant these measurements were made on the two pairs named one app,
so no probe run here may be cited as proof of scope separation — only that the code asked for
the write pair.

**R12 — a parameter this client sends is a parameter a test proved changed something.** Lark's
Base API silently ignores body keys it does not recognise (the bogus control ``{"zzz": 1}``
behaves exactly like four plausible grouping keys), so ``code:0`` proves acceptance, never
effect. Two consequences are built in, the shape the record-write client already ships:

* **By construction** — every request is assembled from the pinned SDK's typed builders, never a
  hand-written dict, so a key cannot be misspelled or misplaced without the builder refusing it;
* **By restraint** — each call sends exactly the keys its endpoint reads and nothing else, and
  every one of them is pinned by a test asserting the request **differs from the parameter-free
  control**.

**``time_zone`` ON A ``create_app`` *IS* SENT NOW — and the reason it was withheld is kept.**
It used to be withheld here because *"no test could show which zone a Base ended up in from a
shape this library reads"*. That reason was the right test to demand; probe ``ld463-01``
**ran** it and it came back positive, so the reason is kept and only its conclusion changes.
Measured: ``POST /bitable/v1/apps`` with ``time_zone`` answers ``code:0``, the create's own echo
carries the zone back, and ``GET …/apps/{app}`` reads it back — while the same create *without*
the key produces a Base whose payload has no ``time_zone`` **at all**. That absence was not
Lark's: it was this client's, and it is the root of a real defect — a date-only value read off a
zone-less Base rendered one calendar day early, fifty times out of fifty, because the read side
must then assume a zone (the one policy: :mod:`larkdocio.base.date_zone`). The key is still sent
**only when supplied**, differentially pinned against the parameter-free control like every
other key here.

**What is deliberately NOT sent.** ``default_view_name`` **on the create body** (**not** for
that reason: the endpoint **rejects** a body carrying it — ``1254001 WrongRequestBody``, no table
created — measured twice, raw core + pinned SDK, probe ``ld344-01``; the view name itself *is*
readable via ``list_views``, so it was never unprovable — just refused), and — the sharp one —
**``is_advanced``**.

**The one COMPOSITE on this client, and the one method that makes two calls.**
``create_table(..., default_view_name=…)`` still sends no such key: it creates the table, takes
the ``default_view_id`` the create's **own reply** carries, and renames that view with the
``update_view`` this client already ships. So the goal the rejected key could not reach through the
body is reached one call later — and the honest consequence is stated rather than hidden: **the composite
is not atomic**. A rename that fails after the create landed raises the typed
:class:`~larkdocio.base.errors.TableCreatedViewNotNamed`, carrying the ids and Lark's unedited
denial; **nothing is rolled back and nothing is retried** — a destructive rollback to undo a
cosmetic failure is the wrong risk class.

**``fields`` ON A ``create_table`` *IS* SENT NOW, AND ONLY THROUGH THE FIELD GATE.** It
used to be withheld here on the reasoning that field authoring rides an allow-list and a table
create must not be a side door around it. That **reason stands**; only the conclusion changed.
``create_table`` runs the array through
:func:`larkdocio.base.field_vocabulary.check_authorable` and
:func:`larkdocio.base.field_authoring.build_property` — **the same two seams**
:meth:`BaseSchemaClient.create_field` calls — so a column definition ``create_field`` would
refuse is refused on this route too, **locally, before any call**, and an unauthorable entry
anywhere in the array refuses the whole create. What the amendment buys is a table and its full
column kit in **one** HTTP call, on a route that never touches the ``/fields`` write family.
``batch_create_tables`` is the **exception, and by measurement**: it accepts a kit at ``code:0``
and creates every table without one, so it refuses the argument rather than sending it.

**``is_advanced`` is a PRODUCT FEATURE GATE, and this client refuses it locally.**
``PUT …/apps/{a} {"is_advanced": true}`` answers ``1254302 RolePermNotAllow``: enabling advanced
permissions is a **Base-owner action in the product**, not an API action, and no console grant
reaches it. So the rename op must not silently accept the key, and its refusal must not advise
requesting a scope — the wording that says so is already shipped in the error taxonomy
(:data:`larkdocio.base.errors.BASE_ERROR_CODES`\\ ``[1254302]``) and in the source repository's
``BASE.md`` register, and this module **quotes** it rather than authoring a competing sentence.

**Nothing here is verified by ``code:0``, and this client does not verify at all.** One method,
one API call, and the answer handed straight back — with **exactly one exception, named rather
than quiet**: a ``create_table`` asked for a ``default_view_name`` makes a second **write** call
(the rename above). It still verifies nothing; the **read-back** that decides whether an op
actually happened belongs to :mod:`larkdocio.base.schema_apply`, which holds the read seam. That
split is why the copy's settle is not in this module either: the settle is a *read* loop over a
Base this client just made, and the engine already carries a read client for exactly that reason.

**Be gentle.** Every call passes one shared
:class:`~larkdocio.common.transport.RateLimiter` first, at the spacing the three probe packs
actually sustained — 483 live calls at ≥1.2 s with no limit met. Rate limits were **deliberately
not probed** and are not probed here.
"""
from typing import List, Optional, Sequence

from lark_oapi.api.bitable.v1 import (
    App,
    BatchCreateAppTableRequest,
    BatchCreateAppTableRequestBody,
    BatchDeleteAppTableRequest,
    BatchDeleteAppTableRequestBody,
    CopyAppRequest,
    CopyAppRequestBody,
    CreateAppRequest,
    CreateAppTableRequest,
    CreateAppTableRequestBody,
    DeleteAppTableFieldRequest,
    DeleteAppTableRequest,
    PatchAppTableRequest,
    PatchAppTableRequestBody,
    ReqApp,
    UpdateAppRequest,
    UpdateAppRequestBody,
)
from lark_oapi.api.drive.v1 import DeleteFileRequest

from larkdocio.base.errors import (
    BASE_ERROR_CODES,
    raise_for_base_code,
    table_created_view_not_named,
)
from larkdocio.base.field_authoring import check_conversion
from larkdocio.base.schema_ops_app_table import (
    check_batch_column_kits,
    check_batch_primary_naming,
    check_primary_naming,
    req_table,
)
from larkdocio.base.loss_preview import OBJECT_GONE_CODES
from larkdocio.base.schema_ops_fields import build_create_request, build_update_request
from larkdocio.common.auth import WRITE_ENV, get_write_credentials
from larkdocio.common.destination import require_destination
from larkdocio.common.sdk_client import (
    require_credentials,
    resolve_rate_limiter,
    resolve_sdk_client,
)
from larkdocio.base.view_client import BaseViewOps
from larkdocio.errors import LarkConfigError
# The Drive endpoint's own "already in the trash" code, IMPORTED rather than re-spelled. It is
# authored once, on the sheets write client, because that is where the first shipped whole-object
# trash-and-confirm pair measured it (``1061007 file has been delete.``, live 2026-07-30). A
# second definition here would be a second opinion about the same wire answer — and the question
# "is it gone" gets one answer on this surface too (:func:`base_is_gone`).
from larkdocio.sheets.write_client import FILE_ALREADY_DELETED_CODE

#: The window the pace is expressed over: one minute.
BASE_SCHEMA_RATE_WINDOW_SECONDS = 60.0

#: Client-side cap per :data:`BASE_SCHEMA_RATE_WINDOW_SECONDS`. 50/minute is a **1.2 s**
#: spacing — the pace the three probe packs sustained across 483 live calls without meeting a
#: limit. A number measured in this repository's own evidence, not read off a doc page.
DEFAULT_MAX_SCHEMA_WRITES_PER_WINDOW = 50


# --------------------------------------------------------------------------- #
# THE WHOLE-OBJECT LIFECYCLE (LD-466) — a Base you can create, you can delete.  #
# --------------------------------------------------------------------------- #

#: The Base's own **Drive object type** — the whole difference between a delete that works and
#: one that reports the Base does not exist. Measured 2026-08-15 on two Bases the probe created
#: itself (``tests/captures/ld466-delete-base/``): ``?type=bitable`` answered ``code:0`` on the first
#: attempt, while the same request with Drive's generic ``type=file`` — what
#: :meth:`larkdocio.drive.files_write.DriveFilesWriteClient.delete` hardcodes for an uploaded
#: file object — answered ``1061003 not found`` for a Base the same credentials had just made.
BASE_DRIVE_FILE_TYPE = "bitable"

#: The Base's path on the Drive file family. There is **no bitable-native app delete**:
#: ``DELETE /open-apis/bitable/v1/apps/{app_token}`` is answered below Lark's API layer with a
#: non-JSON HTTP 404 and carries no code at all (capture ``ld466-02``, in the dev repo; not
#: published), so it is not a route this library could call. A Base is a Drive file for deletion,
#: exactly as a spreadsheet is.
_DRIVE_FILE_PATH = "/open-apis/drive/v1/files/:file_token"

#: Every code that means **"this Base is already gone"**, spanning the two endpoints that can
#: say so — assembled from the two definitions that already exist rather than a third list:
#: :data:`~larkdocio.base.loss_preview.OBJECT_GONE_CODES` is the **bitable** side (the oracle the
#: live harness's zero-orphan check uses, ruled to ask its confirmation of the bitable
#: API and never of Drive metadata), and
#: :data:`~larkdocio.sheets.write_client.FILE_ALREADY_DELETED_CODE` is the **Drive** side.
BASE_GONE_CODES = tuple(OBJECT_GONE_CODES) + (FILE_ALREADY_DELETED_CODE,)

#: Kept as strings so the comparison is representation-agnostic — the wire may hand back an int
#: or a str, the same discipline ``spreadsheet_is_gone`` keeps.
_GONE_CODES = frozenset(str(code) for code in BASE_GONE_CODES)

#: ``(destroy,)`` — the file-lifecycle calls on this client, named beside the method itself so
#: the discovery registry (``larkdocio.capabilities()``) can PROJECT them instead of keeping a
#: second hand-maintained list. A name here that is not a method on the class fails at
#: projection time.
#:
#: **One member, and the asymmetry is disclosed rather than smoothed over.** The Base's create
#: half is :meth:`BaseSchemaClient.create_app` — a **registered, plan-gated schema op** on a
#: bitable endpoint — so it is published under the surface's ``operations``, where a consumer
#: reading the plan gate will find it. The destroy half is a **Drive** call with no plan of its
#: own, so it is published here. Naming ``create_app`` in both keys would collapse its two
#: permission rows into one and claim a plan for a call that has none. A one-member lifecycle is
#: the shape :data:`larkdocio.drive.files_write.LIFECYCLE_OPS` already ships.
LIFECYCLE_OPS = ("delete_base",)


def base_is_gone(error) -> bool:
    """True iff ``error`` says the Base is **already gone**.

    THE one check a teardown needs, so nobody has to know which endpoint answers which number:
    a delete of an already-trashed Base and a read of a trashed ``app_token`` report the fact
    with **different** codes, and both mean the same thing. Use it to forgive exactly that
    outcome in a ``finally`` — and to *confirm* a delete landed — while every other failure (a
    permission problem, a transport failure, the wrong Drive type) still surfaces:

    .. code-block:: python

        try:
            client.delete_base(app_token)
        except LarkAPIError as exc:
            if not base_is_gone(exc):
                raise

    Anything that is not a Lark error carrying one of :data:`BASE_GONE_CODES` is ``False`` —
    including a **code-less** error, where the failure happened below Lark and whether the Base
    is gone is unknown and must not be assumed, and including ``1061003 not found``, which is
    what the *wrong Drive type* answers about a Base that is very much still there.
    """
    code = getattr(error, "code", None)
    return code is not None and str(code) in _GONE_CODES


class BaseSchemaRefusal(LarkConfigError, ValueError):
    """A schema request refused **locally, before any call**.

    The shape the write encoder already ships: a refusal a caller can read beats a round trip
    that answers with a code they have to look up.

    Under :class:`~larkdocio.errors.LarkConfigError` (a local, pre-API unsupported-input
    problem), so ``except LarkConfigError`` / ``except LarkDocIOError`` catch it — which is
    exactly what the base class promises. ``ValueError`` is **retained**, so every
    ``except ValueError`` written against the earlier shape still catches it.
    """


#: The one sentence about ``is_advanced``, taken from the landed taxonomy rather than written
#: again here. ``BASE.md`` (in the source repository) register row 16 carries the same fact in the same
#: wording, and this module deliberately adds no competing sentence to the pair.
ADVANCED_PERMISSIONS_IS_A_FEATURE_GATE = BASE_ERROR_CODES[1254302].meaning


#: **A new Base is NOT empty** — LD-572 put this in :meth:`BaseSchemaClient.create_app`'s
#: docstring; LD-583 restates it on the returned value, so a caller reading the object they now
#: hold meets it too. The thorough version lives in one place and this points at it rather than
#: competing with it.
NEW_BASE_IS_NOT_EMPTY = (
    "this Base is not empty: it arrives holding one table Lark made — not one you asked for — "
    "with its own columns and blank rows, and every table you go on to create is appended "
    "after it. See `larkdocio.guide()`, section \"Recipe: create, rename and copy a Base (the "
    "structural handshake)\", the paragraph beginning \"AND A NEW BASE IS NOT EMPTY\"."
)

#: **A copy's echo is not its state.** :meth:`BaseSchemaClient.copy_app`'s docstring has said so
#: since the async copy was measured; this is that fact carried on the value, because the empty
#: ``default_table_id`` is precisely the field a caller would otherwise read as an answer.
BASE_ECHO_IS_NOT_STATE = (
    "this is the copy's ECHO, not its state: the Base copy is ASYNCHRONOUS — the one "
    "non-synchronous Base operation this library has found — so default_table_id comes back "
    "empty and an immediate read of the new app_token answers 1254036. Settling it belongs to "
    "the engine, which holds the read seam; this value is the echo exactly as it arrived"
)


class _AppEcho(App):
    """The SDK's own ``App``, subclassed so a create can answer with a value that **says
    something** while still being the value it always was.

    ``create_app`` and ``copy_app`` returned ``response.data.app`` — the SDK's ``App`` — so the
    compatibility obligation here is about **attributes**, not dict keys. Every attribute of the
    echo is copied across verbatim, ``isinstance(x, App)`` still answers ``True``, and ``App``
    defines no ``__eq__`` so ``==`` was identity before and is identity now. What each subclass
    adds is a disclosure its own docstring already carried.

    Copying ``vars(app)`` rather than re-deserialising means a pinned SDK that grows a field
    carries it through untouched.
    """

    __slots__ = ()

    def __init__(self, app=None):
        super().__init__()
        if app is not None:
            vars(self).update(vars(app))


class CreatedBase(_AppEcho):
    """One Base created in a folder: the server's app echo, plus what it does not say.

    Carries the SDK ``App``'s own ``app_token``, ``name``, ``revision``, ``folder_token``,
    ``url``, ``default_table_id`` and ``time_zone`` unchanged — ``url`` is Lark's own answer,
    carried as it arrived and never assembled.

    :data:`NEW_BASE_IS_NOT_EMPTY` is restated on the value as :attr:`default_table_disclosure`.
    """

    __slots__ = ()

    #: Restated on the value itself, so a caller reading a returned object meets it.
    default_table_disclosure = NEW_BASE_IS_NOT_EMPTY


class CopiedBase(_AppEcho):
    """One copy of a Base: the copy's **echo**, which is not its state.

    Same attributes as :class:`CreatedBase`, same values, same ``isinstance(x, App)``. What it
    adds is :attr:`echo_is_not_state` (:data:`BASE_ECHO_IS_NOT_STATE`) — the disclosure that
    stops a caller reading the empty ``default_table_id`` as an answer.
    """

    __slots__ = ()

    #: Restated on the value itself — the asynchronous-copy fact, where a caller will meet it.
    echo_is_not_state = BASE_ECHO_IS_NOT_STATE


class BaseSchemaClient(BaseViewOps):
    """Changes a Base's shape: create, rename and copy an app; create and rename tables; create,
    patch and delete **views** (the last three mixed in from
    :mod:`larkdocio.base.view_client`, so that family stays one file plus one line).

    ``sdk_client`` and ``rate_limiter`` are injectable so request construction, pacing and error
    typing are all testable without a network — the two landed clients' shape. The defaults are
    a real SDK client built from the supplied credentials and a limiter at
    :data:`DEFAULT_MAX_SCHEMA_WRITES_PER_WINDOW` per
    :data:`BASE_SCHEMA_RATE_WINDOW_SECONDS`.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "larksuite.com",
        *,
        sdk_client=None,
        rate_limiter=None,
        timeout: int = 30,
    ):
        self._domain = domain
        self._api_calls = 0
        self._limiter = resolve_rate_limiter(
            rate_limiter, DEFAULT_MAX_SCHEMA_WRITES_PER_WINDOW,
            BASE_SCHEMA_RATE_WINDOW_SECONDS)
        self._sdk = resolve_sdk_client(
            sdk_client, app_id, app_secret, domain, timeout=timeout,
            no_credentials="Cannot change a Base's schema: no credentials were resolved")

    @classmethod
    def from_write_credentials(cls, domain: str = "larksuite.com", **kwargs):
        """Build from the environment's WRITE credentials.

        The write getter has no fallback, so an environment carrying only read credentials
        fails here with a typed configuration error rather than quietly attempting a schema
        change on a read-only app.
        """
        app_id, app_secret = get_write_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot change a Base's schema: no write credentials in the environment")
        return cls(app_id, app_secret, domain, **kwargs)

    # ---- pacing ----------------------------------------------------------- #

    @property
    def limiter(self):
        """The limiter every call on this client passes through."""
        return self._limiter

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made. Incremented in exactly one place, so it
        counts real requests rather than intentions."""
        return self._api_calls

    def _paced(self, call, request):
        """Acquire a slot, then make exactly one API call. Every call in this module goes
        through here, so no op can be added that bypasses the pace."""
        self._limiter.acquire()
        self._api_calls += 1
        return call(request)

    def _checked(self, call, request, context):
        return raise_for_base_code(self._paced(call, request), context=context,
                                   credential_env=WRITE_ENV)

    # ---- the operations --------------------------------------------------- #

    def create_app(self, name: str, folder_token: Optional[str] = None,
                   time_zone: Optional[str] = None) -> "CreatedBase":
        """Create a Base in the folder ``folder_token``, returning a :class:`CreatedBase`.

        **It IS the server's app echo** — a subclass of the SDK's ``App`` built from that echo's
        own attributes, so ``isinstance(result, App)`` still holds and ``app_token``, ``name``,
        ``revision``, ``folder_token``, ``url``, ``default_table_id`` and ``time_zone`` all
        answer exactly what they answered when this returned ``response.data.app``. What it adds
        is :attr:`~CreatedBase.default_table_disclosure`, the paragraph below carried on the
        value itself.

        **The destination is the caller's** — ``folder_token`` is **required** (it keeps its
        positional place, so no call site moves), and every spelling of "none" — ``None``, the
        empty string, whitespace — is refused **locally, before any call**, with
        :class:`~larkdocio.errors.MissingDestinationError`. It used to be optional and omitted
        when absent, which files the Base in the application's own space: a space with no human
        interface, whose trash cannot be listed and where a delete is a trash rather than a
        purge (``"my space"`` is exactly what the server's empty echo means). The rule and its
        measurements are on :mod:`larkdocio.common.destination`; nothing here creates a folder
        to put the Base in.

        **The Base this hands back is not empty.** It arrives holding one table Lark made —
        not one you asked for — with its own columns and blank rows, and every table you go on
        to create is appended after it. This is documented in one place, thoroughly, and this
        sentence only points at it rather than restating it: ``larkdocio.guide()``, section
        "Recipe: create, rename and copy a Base (the structural handshake)", the paragraph
        beginning "AND A NEW BASE IS NOT EMPTY".

        ``time_zone`` declares the Base's own zone (an IANA name, e.g. ``"Asia/Singapore"``) and
        is **the only place Lark accepts one** — see
        :data:`larkdocio.base.date_zone.CREATE_IS_WHERE_A_ZONE_IS_DECLARED`. Sent only when
        supplied, for the same reason as ``folder_token``. **Supply it**: a Base created without
        it reports no zone on any later read, so every date cell read out of it is rendered in an
        assumed zone, which is how a date-only value ends up one calendar day early. The module
        docstring carries what was measured and what the withheld-key record used to say.
        """
        require_destination(folder_token, what="a Base")
        builder = ReqApp.builder().name(name).folder_token(folder_token)
        if time_zone:
            builder = builder.time_zone(time_zone)
        request = CreateAppRequest.builder().request_body(builder.build()).build()
        response = self._checked(self._sdk.bitable.v1.app.create, request,
                                 f"create a Base named {name!r}")
        return CreatedBase(response.data.app)

    def rename_app(self, app_token: str, name: str, **unsupported):
        """Rename a Base, returning the server's app echo.

        **``is_advanced`` is refused here, locally.** It is the one other key this endpoint
        takes, and it is a *product feature gate*: the API answers ``1254302`` to it, because
        enabling advanced permissions is a Base-owner action in the product that no console
        grant reaches. Accepting the key silently would be worse than refusing it — the call
        would look like it had done something.
        """
        if "is_advanced" in unsupported:
            raise BaseSchemaRefusal(
                "`is_advanced` is not something this rename can set: "
                f"{ADVANCED_PERMISSIONS_IS_A_FEATURE_GATE} Nothing was sent. This is not a "
                "missing permission and asking for another one will not change it.")
        if unsupported:
            raise BaseSchemaRefusal(
                f"rename_app does not take {sorted(unsupported)!r}: this endpoint reads a "
                "name, and a key it does not recognise is silently ignored rather than "
                "refused, so an unknown key is stopped here instead of looking like it "
                "worked.")
        body = UpdateAppRequestBody.builder().name(name).build()
        request = UpdateAppRequest.builder() \
            .app_token(app_token) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app.update, request,
                                 f"rename Base {app_token} to {name!r}")
        return response.data.app

    def copy_app(self, app_token: str, name: str, without_content: bool = False,
                 folder_token: Optional[str] = None) -> "CopiedBase":
        """Copy a Base, returning a :class:`CopiedBase` — the copy's **echo**, not its state.

        **It IS the server's app echo** — a subclass of the SDK's ``App`` built from that echo's
        own attributes, so ``isinstance(result, App)`` still holds and every attribute answers
        what it answered before. What it adds is :attr:`~CopiedBase.echo_is_not_state`, which is
        the next paragraph carried on the value itself.

        ``default_table_id`` comes back **empty** and an immediate read of the new token
        answers ``1254036``: the copy is ASYNCHRONOUS, the one non-synchronous Base operation
        this library has found. Settling it belongs to the engine, which holds the read seam;
        this method makes the one call and hands the echo back exactly as it arrived.

        ``without_content: true`` gives a **schema-only** copy — the columns without the rows.

        ``folder_token`` places the copy in a Drive folder, spelled and **required** exactly as
        :meth:`create_app` spells it — a copy makes a **new top-level Base**, and a keyless copy
        lands in the application's own space, so the caller-supplied-destination rule reaches
        the copy exactly as it reaches the create (:mod:`larkdocio.common.destination`).
        **What that key is measured to do, and what it is not** (probe ``ld387-01``): the
        **Base copy** route (``apps/:app_token/copy``) **validates**
        it — a folder-shaped token naming nothing, and a real Drive object that is not a folder,
        each answered ``1254702 DriveNodeNotExist`` and created **no copy** — and a copy carrying
        a real folder reads back inside that folder in the folder's **own** listing, with the
        copy's echo carrying the token back where a keyless copy's echo carries ``""``. What is
        **not** measured is placement into a folder that is not the default destination: on the
        measuring tenant the only addressable folder was the app's own root, which is also where
        a keyless copy lands, and a second folder could not be provisioned because
        ``create_folder`` is a permanent Drive write with no purge verb. So the honest claim is
        *the folder you name is read, checked, and is where the copy is* — not *the copy would
        otherwise have gone elsewhere*.

        **On this route the two cases DO come apart, and there are THREE outcomes.** Handed a
        real folder this application has no permission on, ``copy_app`` answers
        ``1254701 DriveNodePermNotAllow`` and copies nothing. Handed a folder-shaped token
        naming nothing — or a real Drive object that is not a folder — this route answers
        ``1254702 DriveNodeNotExist`` and copies nothing (probe ``ld387-01``, above). Handed a
        real folder it can reach, this route takes the copy and the copy reads back inside that
        folder's own listing. So a folder this app cannot reach is distinguishable, *here*, from
        one that does not exist, and the library relays whichever code arrived unedited, asking
        for no further permission and retrying nothing.
        **Check the code you actually got.** ``1254701`` from this route means the folder is real
        and this application is not allowed into it: ask a workspace administrator to grant
        access to that folder. A grant is a Lark console action, made by a person in the Lark
        console: this library asks for no further permission of any kind, and it retries
        nothing. ``1254702`` from this route means the token is wrong.
        **The ``1254701`` half's scope.** Evidence covers exactly the route it was observed
        on and never a sibling route, so: measured 2026-08-18, one tenant, one app
        identity, ``tenant_access_token``, this route, **one send, no retries**, capture (in the
        dev repo)
        ``dev/ld493-caller-supplied-destination/captures/002-copy-app-unreachable-folder.json``.
        One send establishes that the codes come apart **here** — it is not a general mapping,
        and it says nothing about another route, another tenant, another region or a
        ``user_access_token``. **That answer is this endpoint's, not Lark's** — same rule — and a third
        route answers differently again. The shipped :meth:`larkdocio.write.WriteClient.create_document`,
        handed a real folder the account holder owns and the application was **not** granted,
        answers ``403 · 1770040 "no folder permission"`` (with Lark's own
        ``无权限在此文件夹下创建文档``) — an actionable denial, distinct from the
        ``1254702 DriveNodeNotExist`` a folder that does not exist draws. Its scope, on that same
        route-bounded rule:
        measured 2026-08-17, one tenant, one app identity, ``tenant_access_token``, one honest
        send, capture (in the dev repo)
        ``dev/ld493-caller-supplied-destination/captures/001-ac4-denial-create-document.json``.
        So **which answer you get depends on the route**: do not carry this route's answer to
        another one. **The history rather than a gap:** this route's unreachable-folder case once
        shipped as *inferred rather than separately sent*, and its re-measurement stayed
        **parked** until it was authorised — that one ``copy_app`` send was made on 2026-08-18
        and answered ``1254701``, which is why this paragraph now reads the other way round.
        """
        require_destination(folder_token, what="a copy of a Base")
        body = CopyAppRequestBody.builder() \
            .name(name) \
            .without_content(bool(without_content)) \
            .folder_token(folder_token) \
            .build()
        request = CopyAppRequest.builder() \
            .app_token(app_token) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app.copy, request,
                                 f"copy Base {app_token} to {name!r}")
        return CopiedBase(response.data.app)

    def create_table(self, app_token: str, name: str, fields=None,
                     primary_field_name=None, default_view_name=None) -> str:
        """Create one table, returning its ``table_id`` — with its primary column NAMED.

        **Exactly one of ``primary_field_name=`` or ``fields=[…]`` is required**, here as at the
        plan seam: a create carrying neither would land a primary column Lark names in the
        tenant's locale, and this library does not create a table under a name the caller did
        not choose. The refusals (``NAMELESS_PRIMARY_IS_REFUSED``,
        ``PRIMARY_FIELD_NAME_AND_KIT``) are re-raised **here too** for the reason
        :meth:`create_field`'s docstring gives: this is a public seam, and a caller coming
        through this door deserves the same sentence as one coming through the plan's.
        ``primary_field_name=`` is normalised into a one-entry ``Text`` kit and then travels the
        ordinary kit path — one transport, no second shape table.

        ``fields`` is a sequence of ``{"field_name", "field_type", "ui_type", "properties"}``
        column definitions and it lands **in this one call**, on a route that never touches the
        ``/fields`` write family. **The kit goes THROUGH the field gate rather than around it**:
        every definition is checked by the same ``check_authorable`` /
        ``build_property`` seams :meth:`create_field` uses, so a column ``create_field`` would
        refuse is refused here too, locally, with **zero** calls — the old ruling's *reason*
        (field authoring rides an allow-list) preserved, its *conclusion* (``not sent``)
        superseded. The check runs **again** here even when the plan already ran it, for the
        reason :meth:`create_field`'s own docstring gives: this is a public seam.

        **The array's ORDER IS the table's column order — and this is the ONLY point at which
        column order is settable.** Measured with a reversed control: two tables in one Base,
        the same three names sent in opposite ``fields=`` orders, each reading back in its own
        array's order. After the table exists, no measured route places or moves a column — a
        dozen create-time position-shaped parameters on :meth:`create_field` are accepted and
        ignored, five update-time equivalents rename a column without moving it, and every
        dedicated move/reorder route answers ``404`` — so if you want columns in a particular
        order, hand this array to this call in that order; there is no second chance.

        ``default_view_name`` names the table's DEFAULT VIEW — and it is **not sent on the
        create body**, because the endpoint **rejects** a body carrying that key (``1254001
        WrongRequestBody``, no table created — measured twice, raw core + pinned SDK, probe
        ``ld344-01``). It is applied **one call later** instead, by renaming the view the table
        is born with: a fresh table has exactly one view, and the create's own response names it
        (``default_view_id``, measured equal to the single listed view's id on the kitted create
        this method always sends — probe ``ld356-01``). So the view is found by **id**, never by
        a comparison against the locale-dependent name Lark gave it (``表格视图 1`` on the
        reporting tenant). **Omitted, this method makes exactly the one call it always made.**

        **THE COMPOSITE IS NOT ATOMIC, and this library does not pretend it is.** If the create
        lands and the rename does not, the table **exists** carrying Lark's own view name, and
        :class:`~larkdocio.base.errors.TableCreatedViewNotNamed` is raised carrying the
        ``table_id``, the ``view_id`` (or an explicit *not learned*), the requested name and
        **Lark's unedited denial**. Nothing is rolled back — this library does not delete a
        table to undo a cosmetic failure, because a delete can itself fail, can race, and can
        need a permission the create did not — and nothing is retried: one attempt, and the
        caller who wants a second has every id it needs.
        See :data:`~larkdocio.base.errors.COMPOSITE_IS_NOT_ATOMIC`.
        """
        table = req_table(name, check_primary_naming(fields, primary_field_name))
        body = CreateAppTableRequestBody.builder().table(table).build()
        request = CreateAppTableRequest.builder() \
            .app_token(app_token) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table.create, request,
                                 f"create table {name!r} in Base {app_token}")
        table_id = response.data.table_id
        if default_view_name is None:
            return table_id
        # The SERVER's own handle on the view, taken from the reply that created it. No listing
        # is made here: a write client that quietly starts reading is one whose call budget
        # nobody can predict, and the echo is what ``ld356-01`` measured.
        view_id = getattr(response.data, "default_view_id", None)
        if not view_id:
            raise table_created_view_not_named(table_id, None, default_view_name)
        try:
            self.update_view(app_token, table_id, view_id, view_name=default_view_name)
        except Exception as exc:      # noqa: BLE001 — see the ruling below
            # EVERY failure of the second leg, not only a Lark refusal: the caller asked for a
            # name, did not get it, and holds a table they now have to reconcile — so they are
            # told, with the ids they need, whatever the cause. The original is CHAINED, never
            # swallowed. No delete, no retry: one attempt, structurally (there is no loop here).
            raise table_created_view_not_named(
                table_id, view_id, default_view_name, cause=exc) from exc
        return table_id

    def batch_create_tables(self, app_token: str, names: Sequence[str], fields=None,
                            accept_locale_default_primary: bool = False,
                            primary_field_name=None) -> List[str]:
        """Create many tables in one call, in the order given, returning their ids.

        **This verb cannot name a primary column, so it requires the acknowledgement** that
        every table will arrive with Lark's locale-named default
        (``accept_locale_default_primary=True``). Same posture, same sentence, same public-seam
        reasoning as :meth:`create_table`'s.

        **``fields`` is REFUSED on this verb, and the refusal is a measurement.** The batch's
        ``tables`` are the same ``ReqTable`` model the single create uses, so a kit is
        transportable here — and Lark accepts it at ``code:0`` and creates every table
        **without** it. Forwarding a parameter measured to do nothing is exactly what this
        client's R12 discipline forbids, so a kit refuses locally with what to do instead: one
        :meth:`create_table` per table.
        """
        names = list(names)
        check_batch_column_kits(names, fields)
        check_batch_primary_naming(accept_locale_default_primary, primary_field_name)
        tables = [req_table(name) for name in names]
        body = BatchCreateAppTableRequestBody.builder().tables(tables).build()
        request = BatchCreateAppTableRequest.builder() \
            .app_token(app_token) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table.batch_create, request,
                                 f"create {len(tables)} table(s) in Base {app_token}")
        return list(response.data.table_ids or ())

    def rename_table(self, app_token: str, table_id: str, name: str) -> str:
        """Rename one table, returning the name the server echoed back."""
        body = PatchAppTableRequestBody.builder().name(name).build()
        request = PatchAppTableRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table.patch, request,
                                 f"rename table {table_id} to {name!r}")
        return getattr(response.data, "name", None)

    # ---- the FIELD family (its shapes and refusals live in its own module) ---- #

    def create_field(self, app_token: str, table_id: str, field_name: str, field_type: int,
                     ui_type: Optional[str] = None, properties: Optional[dict] = None):
        """Create one column, returning the server's field echo.

        The allow-list and the captured property shapes are checked **again** here, and not
        only in the request constructor: this method is a public seam, and a refusal a caller
        can read beats a round trip to an opaque code whichever door they came in through.
        """
        request = build_create_request(app_token, table_id, field_name, field_type,
                                       ui_type=ui_type, properties=properties)
        response = self._checked(
            self._sdk.bitable.v1.app_table_field.create, request,
            f"create column {field_name!r} in table {table_id}")
        return response.data.field

    def update_field(self, app_token: str, table_id: str, field_id: str, field_name: str,
                     field_type: int, ui_type: Optional[str] = None,
                     properties: Optional[dict] = None):
        """Edit a column's name or property — **never** its kind. Returns the field echo.

        The allow-list applies to any ``ui_type`` in the body because the server applies it to
        this route identically to the create route: it is the vocabulary that blocks, not the
        verb.
        """
        request = build_update_request(app_token, table_id, field_id, field_name, field_type,
                                       ui_type=ui_type, properties=properties)
        response = self._checked(
            self._sdk.bitable.v1.app_table_field.update, request,
            f"edit column {field_id} in table {table_id}")
        return response.data.field

    def convert_field(self, app_token: str, table_id: str, field_id: str, field_name: str,
                      field_type: int, *, from_ui_type: str, to_ui_type: str,
                      properties: Optional[dict] = None):
        """Convert a column's kind — **only** for a pair a capture carries.

        The pair table is consulted before the request is built, so an unlisted conversion is
        refused here with no call at all. Changing a column's kind rewrites every value in it,
        server-side and permanently; a pair with no captured evidence of what that did to the
        cells is not one this library performs.
        """
        check_conversion(from_ui_type, to_ui_type)
        request = build_update_request(app_token, table_id, field_id, field_name, field_type,
                                       ui_type=to_ui_type, properties=properties)
        response = self._checked(
            self._sdk.bitable.v1.app_table_field.update, request,
            f"convert column {field_id} from {from_ui_type} to {to_ui_type}")
        return response.data.field

    # ---- the DESTRUCTIVE family (its previews and its fence live elsewhere) ---- #
    #
    # These three are the only methods on this client that can LOSE DATA, and none of them is
    # reachable from a default engine call: the plan-gated engine refuses to apply a plan
    # carrying one without explicit consent to that plan's own enumerated loss
    # (`larkdocio.base.schema_apply.consent_to_destroy`). The methods themselves are the plain
    # single API calls the rest of this client ships — one call, the answer handed straight
    # back, no verification here — because the read-back that decides whether a delete actually
    # happened belongs to the engine, which holds the read seam.
    #
    # Lark's DELETE is a TRASH, not a purge: a deleted table sits in the Base's trash and a
    # human can restore it from the product. Nothing here purges, and no open-API verb does.

    def delete_field(self, app_token: str, table_id: str, field_id: str) -> str:
        """Delete ONE column, returning the ``field_id`` the server reports deleted.

        **Destroys every value in that column**, and — when the column is a two-way link — the
        mirror column in ANOTHER table with it. That second table is named in the plan's loss
        preview before this is ever called.
        """
        request = DeleteAppTableFieldRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .field_id(field_id) \
            .build()
        response = self._checked(
            self._sdk.bitable.v1.app_table_field.delete, request,
            f"DELETE column {field_id} in table {table_id}")
        return getattr(response.data, "field_id", None)

    def delete_table(self, app_token: str, table_id: str) -> None:
        """Delete ONE table. Returns nothing — the endpoint answers with an empty ``data``.

        The Base's **last** table cannot be deleted: Lark answers ``1254034`` and keeps every
        Base on a floor of one table.
        """
        request = DeleteAppTableRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .build()
        self._checked(self._sdk.bitable.v1.app_table.delete, request,
                      f"DELETE table {table_id} in Base {app_token}")
        return None

    def batch_delete_tables(self, app_token: str, table_ids: Sequence[str]) -> List[str]:
        """Delete several tables in ONE call, returning the ids that were asked for.

        Only ``table_ids`` is sent — the one key this endpoint reads.
        """
        table_ids = list(table_ids)
        body = BatchDeleteAppTableRequestBody.builder().table_ids(table_ids).build()
        request = BatchDeleteAppTableRequest.builder() \
            .app_token(app_token) \
            .request_body(body) \
            .build()
        self._checked(self._sdk.bitable.v1.app_table.batch_delete, request,
                      f"DELETE {len(table_ids)} table(s) in Base {app_token}")
        return table_ids

    # ---- the WHOLE-OBJECT delete (LD-466) — a lifecycle call, not a schema op ---- #
    #
    # WHICH GATE THIS RIDES, AND WHY. Not the plan-and-consent fence above it — the
    # `delete_document` / `delete_spreadsheet` one, which is the gate the library already
    # establishes for trashing a whole object, and the split is the same on both surfaces
    # (`DeleteTab` is plan-gated; `delete_spreadsheet` is not). Two reasons, both structural
    # rather than stylistic:
    #
    #   * consent here is consent to an ENUMERATED loss (`loss_preview.LOSS_MUST_BE_ENUMERABLE`),
    #     minted from a `SchemaPlan` — and a whole Base's loss is every table, column, record and
    #     view it holds. No plan-time read enumerates that, so a consent token over it would be
    #     consent to a list nobody produced;
    #   * every registered schema op is a BITABLE endpoint verified by a bitable read-back. This
    #     one is a Drive endpoint, and the object it removes is the one the read-back would have
    #     been asked of.
    #
    # So it is declared in `LIFECYCLE_OPS` instead, where the registry publishes it as what it
    # is. Adding a third gate shape for it — a bespoke confirmation argument, a dry-run-only
    # helper — would leave this library with two answers to "how do I destroy a whole file".

    def delete_base(self, app_token: str):
        """Trash the **whole Base** — every table, column, record and view it holds.

        **Not the table delete.** To remove ONE table from a Base that survives, use the
        plan-gated ``delete_table`` (through ``schema_dry_run`` → ``consent_to_destroy`` →
        ``schema_apply``), which enumerates the loss across the whole Base first — including the
        mirror of a two-way link in a table you did not name. Reach for *this* call only for a
        Base you are finished with, typically one you created yourself with :meth:`create_app`.

        **TRASH, NOT PURGE, and that is measured rather than assumed.** Lark's route puts the
        Base in the trash, where a **human** can restore it from the product; no open-API verb
        purges anything here and this library offers none. After a landed delete, Drive's
        ``metas/batch_query`` route **still resolves the token**, with its title, owner and
        timestamps intact — probed on a Base created for the purpose
        (``tests/captures/ld466-delete-base/captures/ld466-07-*.json``, in the source repository). There is no API
        undo, and nothing here retries or reverses a destructive call.

        **Not idempotent, on purpose:** deleting a Base that is already in the trash raises the
        typed :class:`~larkdocio.errors.LarkAPIError` carrying
        :data:`~larkdocio.sheets.write_client.FILE_ALREADY_DELETED_CODE` — never a silent success
        — so a teardown can forgive exactly that one outcome (:func:`base_is_gone`) and still
        fail loudly on anything else, such as a permission problem.

        **Confirming it landed is a separate act, and worth doing:** a ``code: 0`` here means
        *accepted*. Address the ``app_token`` again (``GET …/bitable/v1/apps/{a}``, e.g. through
        ``BaseReadClient``) and the bitable side answers a
        :data:`~larkdocio.base.loss_preview.OBJECT_GONE_CODES` member — measured ``1002``
        (capture ``ld466-05``) — and *that* error is the proof. The confirmation is asked of the
        bitable API and never of Drive metadata, which as above keeps answering. The two codes
        differ because the two endpoints do; :func:`base_is_gone` spans both.

        **A freshly created Base may not be addressable as a Drive file yet.** On this tenant the
        identical delete has answered a rotating set of not-found-shaped codes for over twenty
        minutes before landing (``BASE.md`` register row 21) — while the probe pack above saw none of
        it, landing first try on both Bases, which refutes nothing about an intermittent window.
        Nothing is retried here: a retry loop inside a destructive call is a policy this library
        does not get to choose for a caller. Keep the token, re-attempt, and treat *deleted or
        recorded* as the contract.
        """
        request = DeleteFileRequest.builder() \
            .file_token(app_token) \
            .type(BASE_DRIVE_FILE_TYPE) \
            .build()
        return self._checked(self._sdk.drive.v1.file.delete, request,
                             f"TRASH the whole Base {app_token}")


__all__ = [
    "ADVANCED_PERMISSIONS_IS_A_FEATURE_GATE",
    "BASE_DRIVE_FILE_TYPE",
    "BASE_GONE_CODES",
    "BASE_SCHEMA_RATE_WINDOW_SECONDS",
    "BaseSchemaClient",
    "BaseSchemaRefusal",
    "DEFAULT_MAX_SCHEMA_WRITES_PER_WINDOW",
    "LIFECYCLE_OPS",
    "base_is_gone",
]
