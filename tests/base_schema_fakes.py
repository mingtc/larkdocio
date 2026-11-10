"""Offline stand-ins for the Base SCHEMA rung (LD-263) — one place, three consumers.

The client tests, the engine tests and the guide-recipe harness all need the same two things:
an SDK whose schema legs answer with **committed captures**, and a read seam that answers about
a Base whose state the test controls. A second definition of either would be two opinions about
what Lark returns.

Every response here is round-tripped through the pinned SDK's own deserializer, so an API drift
reddens at deserialization rather than travelling on as a plausible-looking ``None``
(PROJECT.md § Quality bar).
"""
import json
from pathlib import Path

from lark_oapi.api.bitable.v1 import (
    BatchCreateAppTableResponse,
    CopyAppResponse,
    CreateAppResponse,
    CreateAppTableResponse,
    GetAppResponse,
    ListAppTableResponse,
    PatchAppTableResponse,
    PatchAppTableViewResponse,
    UpdateAppResponse,
)
from lark_oapi.api.drive.v1 import DeleteFileResponse
from lark_oapi.core.json import JSON

from larkdocio.base.schema_client import BaseSchemaClient

CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"

#: LD-466's own AC1 pack — the whole-object delete route, measured before the verb was written.
#: A separate directory rather than a merge into the study's, so the capture that graded the
#: verb stays findable beside the verdict that reads it.
LD466_CAPTURES = (Path(__file__).resolve().parent.parent / "tests" / "captures" / "ld466-delete-base"
                  / "captures")


def capture(name):
    return json.loads((CAPTURES / name).read_text(encoding="utf-8"))


def ld466_capture(name):
    return json.loads((LD466_CAPTURES / name).read_text(encoding="utf-8"))


def unmarshal(payload, cls):
    return JSON.unmarshal(json.dumps(payload), cls)


def copy_steps():
    """The five live steps of ``p1-q4-02`` — the async-copy capture — keyed by note prefix."""
    return {step["_note"].split(" :: ")[0]: step
            for step in capture("p1-q4-02-copy.json")["steps"]}


def parity_steps():
    """``p1-q4-03``'s steps, keyed by the probe's own note prefix."""
    return {step["_note"].split(" :: ")[0]: step
            for step in capture("p1-q4-03-parity-sweep.json")["steps"]}


def create_app_echo():
    return unmarshal(capture("05-01-create-app.json")["response"], CreateAppResponse)


def base_delete_echo():
    """The landed whole-object delete, as Lark answered it (LD-466 AC1, capture ``ld466-04``)."""
    return unmarshal(
        ld466_capture("ld466-04-drive-delete-with-the-bases-own-type.json")["response"],
        DeleteFileResponse)


def base_already_deleted_echo():
    """A second delete of a Base already in the trash — ``1061007`` (capture ``ld466-06``).

    The code is the **Drive** endpoint's own, which is why the library reuses the sheets
    surface's ``FILE_ALREADY_DELETED_CODE`` rather than minting a second name for it.
    """
    return unmarshal(
        ld466_capture("ld466-06-second-delete-of-an-already-trashed-base.json")["response"],
        DeleteFileResponse)


def base_wrong_drive_type_echo():
    """``1061003 not found`` — the same delete sent with Drive ``type=file`` (``ld466-01``).

    The recorded blocker, kept as a fixture so the R12 differential pin has a real answer to
    point at: the type is the whole difference between a Base that vanishes and one that
    reports it does not exist.
    """
    return unmarshal(
        ld466_capture("ld466-01-shipped-type-file-delete-against-a-base.json")["response"],
        DeleteFileResponse)


def copy_app_echo():
    return unmarshal(copy_steps()["copy the Scratch Base"]["response"], CopyAppResponse)


def create_table_echo():
    return unmarshal(capture("05-03-create-table.json")["response"], CreateAppTableResponse)


def create_table_echo_with_default_view():
    """LD-356: the create echo that **names the table's default view** — measured, not composed.

    The plain create's echo (``05-03``, above) carries ``table_id`` alone. The **kitted** create
    — the only shape the shipped ``create_table`` sends, since a nameless primary is refused —
    answers with ``default_view_id`` as well, and that id is the single listed view's
    (``ld356-01``). The body is rebuilt from the capture's own ``data_keys``, so if Lark ever
    stops returning the key the fixture loses it and every test that renames through it reddens.
    """
    measured = capture("ld356-01-create-then-rename.json")["response"]["kitted_create"]
    data = {key: measured[key] for key in measured["data_keys"]}
    return unmarshal({"code": 0, "msg": "success", "data": data}, CreateAppTableResponse)


def default_view_id():
    """The ``view_id`` :func:`create_table_echo_with_default_view` echoes."""
    return capture("ld356-01-create-then-rename.json")["response"]["kitted_create"][
        "default_view_id"]


def measured_default_view_name():
    """What Lark calls a fresh table's single view on the reporting tenant — MEASURED.

    ``表格视图 1`` (``ld356-01``, and ``ld344-01`` before it). Served by the fakes so a test can
    prove the shipped code never compares against it: the whole naming doctrine exists because
    this string is the **tenant's locale**, not a constant.
    """
    return capture("ld356-01-create-then-rename.json")["response"][
        "default_view_name_on_this_tenant"]


def view_rename_echo():
    """The view PATCH's own echo (``p0-3-02`` § rename) — a real ``code:0`` view reply."""
    return unmarshal(capture("p0-3-02-view-patch.json")["response"]["data"]["rename"]["response"],
                     PatchAppTableViewResponse)


#: A **real** refusal from the view family's own capture (``p0-3-01``): Lark's code and its
#: verbatim ``msg``. Which code it is does not matter to the failed-rename tests — that the
#: partial outcome reproduces it **unedited** does.
VIEW_REFUSAL_CODE, VIEW_REFUSAL_MSG = 99992402, "field validation failed"


def view_rename_refusal():
    """The view PATCH answering Lark's own refusal, so the failure path is driven by a real
    denial rather than by an invented one."""
    return unmarshal({"code": VIEW_REFUSAL_CODE, "msg": VIEW_REFUSAL_MSG},
                     PatchAppTableViewResponse)


def batch_create_echo():
    return unmarshal(parity_steps()["tables/batch_create"]["response"],
                     BatchCreateAppTableResponse)


def rename_app_echo():
    return unmarshal(parity_steps()["PUT app (rename)"]["response"], UpdateAppResponse)


def rename_table_echo():
    return unmarshal(parity_steps()["PATCH table (rename)"]["response"],
                     PatchAppTableResponse)


def copy_tables_listing():
    """The copy's ``…/tables`` read — the read-back that is reachable only after settling."""
    return unmarshal(copy_steps()["copy: tables"]["response"], ListAppTableResponse)


def app_meta():
    return unmarshal(capture("p1-q0-01-app-meta.json")["response"], GetAppResponse)


class Leg:
    """A bare attribute holder standing in for one SDK resource namespace."""


class Recorder:
    """One SDK resource method: records the request it was handed, hands back the next canned
    response (repeating the last one once the script runs out)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the fake SDK was called with no canned response")
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]


class Forbidden:
    """A leg the shipped schema client must never call."""

    def __init__(self, why):
        self.why = why

    def __call__(self, *args, **kwargs):
        raise AssertionError(self.why)


def fake_sdk(*, create=(), update=(), copy=(), get=(),
             table_create=(), table_batch_create=(), table_patch=(), view_patch=(),
             file_delete=()):
    sdk = Leg()
    sdk.bitable = Leg()
    sdk.bitable.v1 = v1 = Leg()
    v1.app = app = Leg()
    app.create = Recorder(create)
    app.update = Recorder(update)
    app.copy = Recorder(copy)
    app.get = Recorder(get) if get else Forbidden(
        "the settle probe is the ENGINE's read seam, not the schema client's")
    v1.app_table = table = Leg()
    table.create = Recorder(table_create)
    table.batch_create = Recorder(table_batch_create)
    table.patch = Recorder(table_patch)
    # Every destructive verb: LD-265's, behind the cross-table loss preview and the consent
    # fence. Not wired, so a shipped call to one would raise here rather than delete anything.
    table.delete = Forbidden("table delete is LD-265's, behind the consent fence")
    table.batch_delete = Forbidden("table batch_delete is LD-265's")
    table.list = Forbidden("the table listing is the READ client's")
    v1.app_table_field = Forbidden("no field write at this rung — LD-262 owns it")
    # LD-356: the create-then-rename composite reaches the view PATCH — and ONLY the PATCH.
    # Every other view verb stays forbidden, which is what makes "the composite never deletes,
    # never lists, never creates a second view" a structural assertion rather than a promise.
    v1.app_table_view = view = Leg()
    view.patch = Recorder(view_patch) if view_patch else Forbidden(
        "this test wired no view PATCH — a create that renames its default view must be asked "
        "for it explicitly")
    view.create = Forbidden("the composite renames the view a table is BORN with; it makes none")
    view.delete = Forbidden(
        "THE SEAT RULING: a rename that fails after the create landed is SURFACED, never rolled "
        "back — nothing on this path may delete anything")
    view.list = Forbidden(
        "the default view is identified by the CREATE's own default_view_id echo; the write "
        "client lists nothing (the read-back is the engine's read seam)")
    v1.app_table_record = Forbidden("records are the record-write client's")
    # LD-466 — the WHOLE-OBJECT delete. A Drive endpoint, not a bitable one, which is exactly
    # why it is a lifecycle call rather than a schema op: it has no plan, no anchor and no
    # target inside the Base, because it *is* the Base. Unwired by default, so a shipped call
    # that reached it without a test asking for it would raise here rather than trash anything.
    sdk.drive = Leg()
    sdk.drive.v1 = drive_v1 = Leg()
    drive_v1.file = drive_file = Leg()
    drive_file.delete = Recorder(file_delete) if file_delete else Forbidden(
        "this test wired no Drive file delete — trashing the whole Base must be asked for "
        "explicitly")
    return sdk


class CountingLimiter:
    """Stands in for the shared ``RateLimiter`` and counts acquisitions."""

    def __init__(self):
        self.acquisitions = 0

    def acquire(self):
        self.acquisitions += 1


def schema_client(**legs):
    return BaseSchemaClient("id", "secret", sdk_client=fake_sdk(**legs),
                            rate_limiter=CountingLimiter())


class FakeApp:
    def __init__(self, app_token, name):
        self.app_token = app_token
        self.name = name


class FakeTable:
    def __init__(self, table_id, name, revision=1):
        self.table_id = table_id
        self.name = name
        self.revision = revision


class FakeField:
    """One column as the read seam answers it — LD-336's read-back reads these.

    ``is_primary`` is modelled because a fresh table's primary column is one **Lark** creates,
    under a locale-dependent name: a kit's columns arrive *beside* it, so a read-back that could
    not tell the two apart could not answer the question the kit exists to answer.
    """

    def __init__(self, field_name, type=None, ui_type=None, property=None, is_primary=False):
        self.field_name = field_name
        self.type = type
        self.ui_type = ui_type
        self.property = property
        self.is_primary = is_primary


class FakeView:
    """One view as the read seam answers it (the LISTING shape — no ``property``)."""

    def __init__(self, view_id, view_name, view_type="grid"):
        self.view_id = view_id
        self.view_name = view_name
        self.view_type = view_type


class FakeBaseWorld:
    """A read seam over a tenant whose state the test owns.

    ``apps`` is ``{app_token: name}`` and ``tables`` ``{app_token: {table_id: name}}``.
    ``copying`` names the app tokens that still answer ``1254036`` and how many times each has
    left to do so — which is how the asynchronous copy is reproduced without a network.

    ``fields`` is ``{app_token: {table_id: [FakeField, …]}}`` and is filled by
    :class:`ScriptedSchemaClient` as tables are created, so a create carrying a column kit
    (LD-336) really does become a table whose **own field list** can be read back — the only
    evidence R12 accepts that the inline array was processed.
    """

    #: The locale-named primary column a **kit-less** table arrives with (a Chinese-locale
    #: tenant answers ``多行文本``). Deliberately NOT served for a kitted create: the kit's first
    #: entry becomes the primary and this column does not exist there at all.
    DEFAULT_PRIMARY = "多行文本"

    #: The name Lark gives a fresh table's ONE view on the reporting tenant — measured in
    #: ``ld356-01`` (and ``ld344-01``). A **locale** string, modelled here precisely so a test
    #: can prove the shipped composite never compares against it.
    DEFAULT_VIEW = "表格视图 1"

    def __init__(self, apps=None, tables=None, copying=None, fields=None, views=None):
        self.apps = dict(apps or {})
        self.tables = {token: dict(rows) for token, rows in (tables or {}).items()}
        self.copying = dict(copying or {})
        self.fields = {token: {table_id: list(columns) for table_id, columns in rows.items()}
                       for token, rows in (fields or {}).items()}
        self.views = {token: {table_id: list(items) for table_id, items in rows.items()}
                      for token, rows in (views or {}).items()}
        self.calls = []

    def stock_table(self, app_token, table_id, kit=()):
        """The columns a just-created table really has — **measured**, not guessed.

        With **no** kit: one primary column Lark named itself, in the tenant's locale. With a
        kit: **the kit, and only the kit**, its FIRST entry primary — a kitted create does not
        also get the locale-named default (probe ``ld336-02``, nine cases). A double that served
        both would let a test assert the older guess and pass.
        """
        if not kit:
            columns = [FakeField(self.DEFAULT_PRIMARY, type=1, ui_type="Text", is_primary=True)]
        else:
            columns = [
                FakeField(column["field_name"], type=column.get("field_type"),
                          ui_type=column.get("ui_type"), is_primary=(offset == 0))
                for offset, column in enumerate(kit)]
        self.fields.setdefault(app_token, {})[table_id] = columns
        # EXACTLY ONE view, under the name Lark chose in the tenant's locale — measured on both
        # the plain and the kitted create (``ld356-01``: total 1, both times).
        self.views.setdefault(app_token, {})[table_id] = [
            FakeView(f"vew{table_id[-6:]}", self.DEFAULT_VIEW)]

    def list_fields(self, app_token, table_id):
        self.calls.append(("list_fields", app_token, table_id))
        return list(self.fields.get(app_token, {}).get(table_id, ()))

    def list_views(self, app_token, table_id):
        self.calls.append(("list_views", app_token, table_id))
        return list(self.views.get(app_token, {}).get(table_id, ()))

    # -- the read seam the engine uses -------------------------------------- #

    def get_app(self, app_token):
        from larkdocio.base.errors import raise_for_base_code

        self.calls.append(("get_app", app_token))
        remaining = self.copying.get(app_token, 0)
        if remaining > 0:
            self.copying[app_token] = remaining - 1
            raise_for_base_code(
                {"code": 1254036, "msg": "Bitable is copying, please try again later."},
                context=f"read Base {app_token}")
        if app_token not in self.apps:
            raise_for_base_code({"code": 91402, "msg": "NOTEXIST"},
                                context=f"read Base {app_token}")
        return FakeApp(app_token, self.apps[app_token])

    def list_tables(self, app_token):
        self.calls.append(("list_tables", app_token))
        return [FakeTable(table_id, name)
                for table_id, name in self.tables.get(app_token, {}).items()]


class ScriptedSchemaClient:
    """A schema client whose six methods mutate a :class:`FakeBaseWorld`.

    The honest offline stand-in for "the call landed": the world really changes, so a read-back
    that confirms is confirming something. ``deaf`` names ops that answer ``code:0`` and change
    **nothing** — the deliberate defect the read-back discipline has to catch.
    """

    def __init__(self, world, deaf=(), raises=None, counter=None):
        self.world = world
        self.deaf = set(deaf)
        self.raises = dict(raises or {})
        self.calls = []
        self._next = counter or (lambda: f"tbl{len(self.calls):04d}")

    def _record(self, name, *args):
        self.calls.append((name,) + args)
        if name in self.raises:
            raise self.raises[name]

    def create_app(self, name, folder_token=None, time_zone=None):
        self._record("create_app", name, folder_token, time_zone)
        token = f"app{len(self.calls):04d}"
        if "create_app" not in self.deaf:
            self.world.apps[token] = name
            self.world.tables.setdefault(token, {})
        return FakeApp(token, name)

    def rename_app(self, app_token, name, **unsupported):
        self._record("rename_app", app_token, name)
        if "rename_app" not in self.deaf:
            self.world.apps[app_token] = name
        return FakeApp(app_token, name)

    def copy_app(self, app_token, name, without_content=False, folder_token=None):
        self._record("copy_app", app_token, name, without_content, folder_token)
        token = f"copy{len(self.calls):04d}"
        if "copy_app" not in self.deaf:
            self.world.apps[token] = name
            self.world.tables[token] = dict(self.world.tables.get(app_token, {}))
        # The echo is NOT the state: default_table_id comes back empty, and the copy is not
        # readable until it settles.
        return FakeApp(token, name)

    def create_table(self, app_token, name, fields=None, primary_field_name=None,
                     default_view_name=None):
        """LD-336: ``fields`` is the inline column kit, and the world really grows the columns.

        ``deaf`` still means *"answers ``code:0`` and changes nothing"* — including the kit,
        which is what lets a test prove the read-back catches a create whose array was silently
        ignored. ``deaf={"create_table_fields"}`` is the narrower defect: the table appears and
        the columns do not, which is exactly the outage-shaped failure AC6 asks about.

        **LD-356: ``default_view_name`` is the second leg of the composite**, and it mutates the
        world's view the way the shipped rename does. ``deaf={"create_table_default_view"}`` is
        this leg's own silent defect — the table lands, the view keeps Lark's locale name — which
        is what proves the engine's read-back catches a rename that answered and did nothing.
        """
        # LD-322: the naming GATE is upstream (the plan constructor and the client seam);
        # this stand-in only has to speak the signature. `primary_field_name` is
        # normalised the ONE way the shipped code normalises it, so the world grows the
        # column it names rather than a phantom.
        if primary_field_name is not None:
            from larkdocio.base.schema_ops_app_table import check_primary_naming
            fields = list(check_primary_naming(fields, primary_field_name))
        self._record("create_table", app_token, name, tuple(
            column["field_name"] for column in (fields or ())))
        table_id = self._next()
        if "create_table" not in self.deaf:
            self.world.tables.setdefault(app_token, {})[table_id] = name
            self.world.stock_table(
                app_token, table_id,
                () if "create_table_fields" in self.deaf else (fields or ()))
            if default_view_name is not None \
                    and "create_table_default_view" not in self.deaf:
                self.world.views[app_token][table_id][0].view_name = default_view_name
        return table_id

    def batch_create_tables(self, app_token, names, fields=None,
                            accept_locale_default_primary=False,
                            primary_field_name=None):
        """LD-336: ``fields`` is one kit per table, parallel to ``names`` (``None`` for none)."""
        names = list(names)
        kits = list(fields) if fields else [None] * len(names)
        self._record("batch_create_tables", app_token, tuple(names))
        ids = []
        for offset, name in enumerate(names):
            table_id = f"tblB{len(self.calls):03d}{offset}"
            ids.append(table_id)
            if "batch_create_tables" not in self.deaf:
                self.world.tables.setdefault(app_token, {})[table_id] = name
                self.world.stock_table(
                    app_token, table_id,
                    () if "create_table_fields" in self.deaf else (kits[offset] or ()))
        return ids

    def rename_table(self, app_token, table_id, name):
        self._record("rename_table", app_token, table_id, name)
        if "rename_table" not in self.deaf:
            self.world.tables.setdefault(app_token, {})[table_id] = name
        return name


class NoSleep:
    """A wait that records instead of waiting."""

    def __init__(self):
        self.sleeps = []

    def __call__(self, seconds):
        self.sleeps.append(seconds)
