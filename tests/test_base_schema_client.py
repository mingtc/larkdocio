"""LD-263 — the Base SCHEMA client: AC1's six ops, AC6's feature gate, AC7's R12 discipline.

Every test here is offline. The fixtures are the **committed probe captures**
(`tests/captures/base-study/captures/`) round-tripped through the pinned SDK's own deserializer, the same
way the read and record-write clients' tests do, so an API drift reddens **at deserialization**.

**The discipline this file exists to enforce (R12).** `records/search` treats an unrecognized
body key exactly like the bogus control `{"zzz": 1}` (`p1-q3-01`), and `page_size` in the body
is silently ignored while in the query string it works (`p1-q1-01`). So **a test that a
parameter is sent is not a test that it works.** Every parameter this client ships is pinned by
an assertion that the request **differs from the parameter-free control** and lands where the
endpoint reads it — and a deliberate-defect check moves one to the wrong place and proves the
discipline reddens rather than merely being stated.
"""
import inspect
import io
import json
import re
import tokenize

import pytest
from lark_oapi.core.json import JSON

from base_schema_fakes import (
    base_already_deleted_echo,
    base_delete_echo,
    base_wrong_drive_type_echo,
    batch_create_echo,
    copy_app_echo,
    create_app_echo,
    create_table_echo,
    rename_app_echo,
    rename_table_echo,
    schema_client,
)
from larkdocio.base import errors as base_errors

from larkdocio.base.schema_client import (
    ADVANCED_PERMISSIONS_IS_A_FEATURE_GATE,
    BaseSchemaClient,
    BaseSchemaRefusal,
)
from larkdocio.errors import (
    LarkConfigError,
    LarkPermissionError,
    MissingDestinationError,
)

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_BASE_PKG = _REPO / "src" / "larkdocio" / "base"

#: The Base package's SCHEMA modules — this rung's half of the package scan.
SCHEMA_MODULE_NAMES = (
    "schema_apply.py", "schema_client.py", "schema_ops.py", "schema_ops_app_table.py",
    "schema_plan.py", "schema_settle.py",
)


def body_of(request):
    """The JSON body a built SDK request will actually put on the wire."""
    raw = getattr(request, "body", None)
    if raw is None:
        return {}
    if isinstance(raw, (bytes, bytearray)):
        return json.loads(raw.decode("utf-8"))
    if isinstance(raw, str):
        return json.loads(raw)
    return json.loads(JSON.marshal(raw))


def schema_code():
    """The schema modules' source with every string literal and comment removed.

    The scans below ask *"does any CODE PATH do X"*, and prose explaining why the code
    deliberately does **not** do X would otherwise trip them.
    """
    out = []
    for name in sorted(SCHEMA_MODULE_NAMES):
        text = (_BASE_PKG / name).read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in (tokenize.STRING, tokenize.COMMENT):
                out.append(token.string)
    return "\n".join(out)


def schema_source():
    return "\n".join((_BASE_PKG / name).read_text(encoding="utf-8")
                     for name in sorted(SCHEMA_MODULE_NAMES))


# --------------------------------------------------------------------------- #
# AC1 — the six non-destructive structural ops                                 #
# --------------------------------------------------------------------------- #

def test_create_app_sends_a_NAME_AND_ITS_DESTINATION_and_returns_the_echo():
    client = schema_client(create=[create_app_echo()])
    app = client.create_app("larkdocio-DISPOSABLE-x", "fldrXYZ")
    request = client._sdk.bitable.v1.app.create.requests[0]

    assert body_of(request) == {"name": "larkdocio-DISPOSABLE-x",
                                "folder_token": "fldrXYZ"}
    assert app.app_token == "Example02154ddbd1fe2927e2e6"
    assert client.api_calls == 1


def test_create_app_REFUSES_when_no_folder_token_is_given_R12():
    """TRANSFORMED, NOT DELETED. The old control asserted that a parameter-free create sent no
    ``folder_token`` at all — because the server answers ``folder_token: ""`` for "my space",
    and echoing that back would assert a destination rather than decline to name one. **That
    reasoning stands; its conclusion does not.** "My space" is the application's own storage,
    which no human interface can browse and whose trash cannot be listed, so declining to name
    a destination is not neutral — it is choosing the one place the object cannot be recovered
    from. The create now **requires** the destination and refuses locally, with zero calls."""
    for spelling in (None, "", "   "):
        bare = schema_client(create=[create_app_echo()])
        with pytest.raises(MissingDestinationError):
            bare.create_app("n", spelling)
        assert bare.api_calls == 0

    placed = schema_client(create=[create_app_echo()])
    placed.create_app("n", "fldrXYZ")
    assert body_of(placed._sdk.bitable.v1.app.create.requests[0])["folder_token"] == "fldrXYZ"


def test_rename_app_puts_the_NAME_IN_THE_BODY_and_the_TOKEN_IN_THE_PATH():
    """The R12 placement trap in its schema costume: a key in the wrong place is ignored."""
    client = schema_client(update=[rename_app_echo()])
    client.rename_app("BaseScratchExample000000001", "larkdocio-p1-rename-probe")
    request = client._sdk.bitable.v1.app.update.requests[0]

    assert body_of(request) == {"name": "larkdocio-p1-rename-probe"}
    assert request.app_token == "BaseScratchExample000000001"
    assert "app_token" not in body_of(request), (
        "the token is a PATH segment; in the body it is one more key the server ignores")


def test_copy_app_sends_NAME_AND_WITHOUT_CONTENT_and_the_flag_CHANGES_THE_BODY_R12():
    full = schema_client(copy=[copy_app_echo()])
    full.copy_app("BaseScratchExample000000001", "larkdocio-DISPOSABLE-p1-copy",
                  folder_token="fldrXYZ")
    schema_only = schema_client(copy=[copy_app_echo()])
    schema_only.copy_app("BaseScratchExample000000001", "c", without_content=True,
                         folder_token="fldrXYZ")

    with_content = body_of(full._sdk.bitable.v1.app.copy.requests[0])
    without = body_of(schema_only._sdk.bitable.v1.app.copy.requests[0])
    assert with_content == {"name": "larkdocio-DISPOSABLE-p1-copy", "without_content": False,
                            "folder_token": "fldrXYZ"}
    assert without["without_content"] is True
    assert with_content["without_content"] != without["without_content"]


def test_copy_app_REFUSES_without_a_folder_token_and_SENDS_the_one_it_is_given_R12():
    """LD-387 — the copy's half of ``create_app``'s control, and it is NOT a guess.

    The key is measured real on this endpoint (probe ``ld387-01``): a folder-shaped token naming
    nothing and a real Drive object that is **not** a folder each drew ``1254702
    DriveNodeNotExist`` and created **no copy**, so the server reads what is sent rather than
    discarding it — the one thing R12 forbids assuming from a ``code:0``.

    TRANSFORMED: the key used to be optional, and omitting it left the body byte-identical to
    what this op had always sent. A copy makes a **new top-level Base**, and a keyless copy
    lands in the application's own space — the space with no human interface — so the key is
    now required and its absence is a local refusal.
    """
    for spelling in (None, "", "   "):
        bare = schema_client(copy=[copy_app_echo()])
        with pytest.raises(MissingDestinationError):
            bare.copy_app("appSOURCE", "c", folder_token=spelling)
        assert bare.api_calls == 0, "a refused copy costs nothing"

    placed = schema_client(copy=[copy_app_echo()])
    placed.copy_app("appSOURCE", "c", folder_token="fldrXYZ")
    with_param = body_of(placed._sdk.bitable.v1.app.copy.requests[0])
    assert with_param == {"name": "c", "without_content": False, "folder_token": "fldrXYZ"}


def test_copy_app_spells_the_folder_token_THE_WAY_CREATE_APP_DOES():
    """Two sibling creation calls, one grammar. A parameter that is optional on one and
    mandatory-ish, differently named or differently defaulted on the other is a second dialect
    for the same idea."""
    import inspect

    create = inspect.signature(BaseSchemaClient.create_app).parameters["folder_token"]
    copy = inspect.signature(BaseSchemaClient.copy_app).parameters["folder_token"]
    # Both still spell the parameter identically and both still declare ``None`` — which now
    # means "you did not say", and is refused rather than sent.
    assert create.default is None and copy.default is None
    assert create.annotation == copy.annotation


def test_create_table_wraps_the_name_in_TABLE_and_returns_the_id():
    client = schema_client(table_create=[create_table_echo()])
    # LD-322: a create must name its primary column — `primary_field_name=` is the one-entry
    # Text kit that names it, and it rides the same one call.
    table_id = client.create_table("Example02154ddbd1fe2927e2e6", "second",
                                   primary_field_name="Title")

    assert body_of(client._sdk.bitable.v1.app_table.create.requests[0]) == \
        {"table": {"name": "second",
                   "fields": [{"field_name": "Title", "type": 1, "ui_type": "Text"}]}}
    assert table_id == "tblDghjoOXsg03o9"


def test_create_table_SHIPS_A_FIELDS_KEY_ONLY_THROUGH_THE_GATE_and_NEVER_default_view_name():
    """**The AMENDED ruling (LD-336) — amended, not deleted.** `fields` and
    `default_view_name` are both real keys this endpoint takes. The standing ruling was that
    NEITHER is sent, because reaching field authoring through a table create would be a side
    door around the allow-list. That REASON is preserved and only its CONCLUSION is superseded:
    the array now goes THROUGH the gate — the very `check_authorable` `create_field` calls — so
    what this test pins is the pair of facts the amendment must not lose.

    1. **A kit-LESS ``ReqTable`` still sends `{"name"}` alone** — no `fields`, no `null`, no
       `[]` — so that body is byte-identical to the one this ruling produced. **LD-322 moved
       where that body is reachable from, and not what it is**: a kit-less `create_table` is now
       refused outright (a table is never created with a primary column Lark named), so the
       kit-less `ReqTable` is asserted where it still ships — the batch verb, which builds the
       same model;
    2. **`default_view_name` is STILL not sent on the create BODY, by any code path.** Its
       conclusion did not change; the source-text scan that used to guard `fields` guards it
       instead — the assertion that stops this half being silently swept up. **Its REASON was
       corrected (LD-344, Option A):** the key is not withheld as *unprovable* — Lark's
       `create_table` **rejects** a body carrying it (`1254001 WrongRequestBody`, no table
       created; measured twice, raw core + pinned SDK, probe `ld344-01`), and the view name
       itself *is* readable via `list_views`. So the scan still holds because nothing may send
       a key the server refuses.

       **LD-356 TRANSFORMED that scan rather than dropping it.** `default_view_name` is now a
       PARAMETER of `create_table` — the create-then-rename composite renames the view *after*
       the create — so a bare "the identifier appears nowhere" scan would forbid the shipped
       feature instead of the refused key. What it forbids now is exactly what LD-344 measured:
       the key as a **wire key** — a string literal or a builder call — anywhere in the schema
       modules, checked in the same breath as the **body** a named create actually sends. The
       composite's own battery is `tests/test_base_default_view_naming.py`.

    The `fields` path's own guard is the third fact: it calls `check_authorable`. The whole
    refusal battery over it — an unauthorable kind anywhere in the array refusing the WHOLE op,
    at plan time, with zero calls — is `tests/test_base_fields_at_creation.py`.
    """
    client = schema_client(table_create=[create_table_echo()],
                           table_batch_create=[batch_create_echo()])
    client.batch_create_tables("app", ["t"], accept_locale_default_primary=True)
    batch_body = body_of(client._sdk.bitable.v1.app_table.batch_create.requests[0])
    assert set(batch_body["tables"][0]) == {"name"}
    client.create_table("app", "t", primary_field_name="Title")
    body = body_of(client._sdk.bitable.v1.app_table.create.requests[0])
    assert set(body["table"]) == {"name", "fields"}
    code = schema_code()
    assert '"default_view_name"' not in code and "'default_view_name'" not in code, (
        "default_view_name stays unsent as a WIRE KEY — Lark's create_table REJECTS a body "
        "carrying it (1254001 WrongRequestBody, no table created; measured twice in probe "
        "ld344-01) — so no code path may put the string in a body or a dict")
    assert not re.search(r"\.\s*default_view_name\s*\(", code), (
        "nor may any code path hand it to an SDK builder, which is the other way a key "
        "reaches the wire")
    assert "check_authorable" in schema_code(), (
        "the fields path is only legitimate BECAUSE it runs the field gate — the same one "
        "create_field runs. Sending the array without it would be the side door the old "
        "ruling refused")


def test_batch_create_tables_carries_EVERY_name_in_ONE_call():
    client = schema_client(table_batch_create=[batch_create_echo()])
    ids = client.batch_create_tables("BaseScratchExample000000001", ["p1sw-A", "p1sw-B"],
                                     accept_locale_default_primary=True)

    request = client._sdk.bitable.v1.app_table.batch_create.requests[0]
    assert body_of(request) == {"tables": [{"name": "p1sw-A"}, {"name": "p1sw-B"}]}
    assert len(client._sdk.bitable.v1.app_table.batch_create.requests) == 1
    assert ids == ["tblqiWbEHKCHOqWd", "tbl8DhUNQDpj9gDK"]
    assert client.api_calls == 1, "a batch is ONE call — that is what makes it a batch"


def test_rename_table_puts_the_NAME_IN_THE_BODY_and_BOTH_IDS_IN_THE_PATH():
    client = schema_client(table_patch=[rename_table_echo()])
    client.rename_table("BaseScratchExample000000001", "tblYtWUpf5q944Ao", "Table")
    request = client._sdk.bitable.v1.app_table.patch.requests[0]

    assert body_of(request) == {"name": "Table"}
    assert request.app_token == "BaseScratchExample000000001"
    assert request.table_id == "tblYtWUpf5q944Ao"


def test_DEFECT_a_parameter_moved_to_the_wrong_place_is_INVISIBLE_in_the_body():
    """The falsification of the R12 discipline: the rename's name put on the request object
    instead of in the body vanishes from the wire entirely — `code:0` and nothing renamed."""
    from lark_oapi.api.bitable.v1 import UpdateAppRequest, UpdateAppRequestBody

    shipped = UpdateAppRequest.builder().app_token("a").request_body(
        UpdateAppRequestBody.builder().name("new").build()).build()
    defective = UpdateAppRequest.builder().app_token("a").request_body(
        UpdateAppRequestBody.builder().build()).build()
    assert body_of(shipped) == {"name": "new"}
    assert body_of(defective) != body_of(shipped)
    assert "name" not in body_of(defective)


# --------------------------------------------------------------------------- #
# AC6 — 1254302 is a FEATURE GATE, not a scope denial                          #
# --------------------------------------------------------------------------- #

def test_the_rename_REFUSES_is_advanced_LOCALLY_and_sends_nothing():
    client = schema_client(update=[rename_app_echo()])
    with pytest.raises(BaseSchemaRefusal) as caught:
        client.rename_app("app", "n", is_advanced=True)
    assert client.api_calls == 0, "the refusal is local — nothing went out"
    assert "is_advanced" in str(caught.value)


def test_the_refusal_QUOTES_THE_LANDED_TAXONOMY_ROW_rather_than_authoring_a_rival_sentence():
    """AC6, corrected at the mint: the wording is ALREADY SHIPPED. This module reads it."""
    assert ADVANCED_PERMISSIONS_IS_A_FEATURE_GATE == \
        base_errors.BASE_ERROR_CODES[1254302].meaning
    assert 1254302 in base_errors.FEATURE_GATE_CODES


def test_the_refusal_message_DOES_NOT_SEND_ANYBODY_TO_THE_SCOPE_CONSOLE():
    client = schema_client(update=[rename_app_echo()])
    with pytest.raises(BaseSchemaRefusal) as caught:
        client.rename_app("app", "n", is_advanced=True)
    message = str(caught.value).lower()
    assert "not a missing permission" in message, (
        "the refusal has to say what it is NOT, or a reader reaches for the console anyway")
    for misdirection in ("request the scope", "grant the scope", "add the scope",
                         "ask for the scope", "open.larksuite.com/app"):
        assert misdirection not in message, misdirection


def test_the_landed_register_row_16_wording_is_ASSERTED_AGAINST_not_re_authored():
    """A content test against `BASE.md` row 16, which shipped in L1. This story adds no
    competing sentence anywhere in `src/`."""
    base_md = (_REPO / "BASE.md").read_text(encoding="utf-8")
    row = [line for line in base_md.splitlines() if line.startswith("| 16 |")]
    assert len(row) == 1
    assert "PRODUCT FEATURE GATE, not a scope denial" in row[0]
    assert "1254302" in row[0]
    assert "describing it as a missing **scope** would send a consumer to the Lark console" \
        in row[0]
    assert "RolePermNotAllow" not in schema_code(), (
        "the label belongs to the taxonomy row; a second spelling in a shipped string would "
        "be a second definition")


def test_ANY_unknown_keyword_to_the_rename_is_refused_rather_than_dropped():
    client = schema_client(update=[rename_app_echo()])
    with pytest.raises(BaseSchemaRefusal):
        client.rename_app("app", "n", zzz=1)
    assert client.api_calls == 0


# --------------------------------------------------------------------------- #
# AC6b — a copy can clone a column the library will never support               #
# --------------------------------------------------------------------------- #

def test_the_copy_path_adds_NO_BUTTON_HANDLING_ANYWHERE():
    """Register rows 4 and 13: Button is a maintainer ruling with a two-part revisit trigger, and an
    API change alone does not reopen it. A copy may clone one; the copy path must not care."""
    code = schema_code()
    assert "Button" not in code
    assert "3001" not in code


def test_the_copy_path_REGISTERS_NO_RENDERER_and_the_read_registry_is_UNCHANGED():
    import importlib

    from larkdocio.base import cells

    before = dict(cells._RENDERERS)
    for name in ("schema_client", "schema_apply", "schema_plan", "schema_ops_app_table"):
        importlib.import_module(f"larkdocio.base.{name}")
    assert dict(cells._RENDERERS) == before
    assert len(cells.PAIRS) == 27, "the registry is the landed 27 pairs; this story adds none"
    for name in sorted(SCHEMA_MODULE_NAMES):
        text = (_BASE_PKG / name).read_text(encoding="utf-8")
        assert "_RENDERERS" not in text, name
        assert "renderer_for" not in text, name


def test_the_UNREGISTERED_PAIR_DEGRADE_is_the_landed_one_and_this_story_did_not_move_it():
    """A copied Base may legitimately read back an unregistered `(3001, 'Button')` column
    whose documented degrade is `str(value)`. That is the shipped behaviour, unchanged."""
    from larkdocio.base import cells
    from larkdocio.base.table import FieldSpec

    assert cells.renderer_for(3001, "Button") is None
    button = FieldSpec(field_id="fldB", field_name="Button", type=3001, ui_type="Button",
                       property=None, is_primary=False)
    assert cells.render_cell("x", button) == "x"
    assert (3001, "Button") not in cells.PAIRS


# --------------------------------------------------------------------------- #
# Credentials, pacing, and the destructive fence                               #
# --------------------------------------------------------------------------- #

def test_the_client_resolves_the_WRITE_pair_and_NEVER_names_the_read_one():
    code = schema_code()
    assert "get_write_credentials" in code
    assert "LARK_READ_APP" not in code and "get_read_credentials" not in code
    assert "WRITE_ENV" in code, "every refusal names the credential pair it used"


def test_from_write_credentials_raises_TYPED_when_the_environment_has_none(monkeypatch):
    monkeypatch.delenv("LARK_WRITE_APP_ID", raising=False)
    monkeypatch.delenv("LARK_WRITE_APP_SECRET", raising=False)
    with pytest.raises((LarkConfigError, Exception)) as caught:
        BaseSchemaClient.from_write_credentials()
    assert isinstance(caught.value, Exception)


def test_EVERY_call_passes_the_shared_limiter_exactly_once():
    client = schema_client(create=[create_app_echo()], update=[rename_app_echo()],
                           copy=[copy_app_echo()], table_create=[create_table_echo()],
                           table_batch_create=[batch_create_echo()],
                           table_patch=[rename_table_echo()])
    client.create_app("a", "fldrXYZ")
    client.rename_app("t", "b")
    client.copy_app("t", "c", folder_token="fldrXYZ")
    client.create_table("t", "d", primary_field_name="Title")
    client.batch_create_tables("t", ["e"], accept_locale_default_primary=True)
    client.rename_table("t", "tbl", "f")
    assert client.limiter.acquisitions == client.api_calls == 6


def test_EVERY_DESTRUCTIVE_VERB_on_this_client_IS_ONE_THE_CONSENT_FENCE_KNOWS_ABOUT():
    """Revised deliberately when LD-265 landed the three deletes that can **lose data**.

    The guard's subject moves with the surface: it used to say *"the view delete is the only
    delete here"*, and it now says the stronger thing — **every delete on this client is either
    the view delete or an op the engine declares destructive**, so none of them can be reached
    without consent to an enumerated loss. A delete method nobody declared would be a delete
    the fence never sees, which is the one failure this rung cannot have.

    **REVISED AGAIN by LD-466, and the earlier reason is kept.** It used to close with *"the
    drive-file delete that removes a Base is not on this client at all"*, on the reasoning that
    every delete here must be one the consent fence can see. **That reason stands** — and it is
    why the list below is still exhaustive and still checked against
    ``destructive_ops()``. What changed is that a **fourth** kind of delete now exists on this
    client, and it is not a schema op: ``delete_base`` trashes the whole object through a
    **Drive** endpoint, so it has no plan to be fenced by, exactly as
    ``WriteClient.delete_document`` and ``SheetsWriteClient.delete_spreadsheet`` have none.
    It is therefore declared in :data:`~larkdocio.base.schema_client.LIFECYCLE_OPS` instead, and
    this guard pins that **every** delete here is in one of the two enumerations — a delete in
    neither would be the delete nobody declared, which is the failure this test exists to
    prevent.
    """
    from larkdocio.base.schema_client import LIFECYCLE_OPS
    from larkdocio.base.schema_ops import destructive_ops

    public = {name for name in dir(BaseSchemaClient) if not name.startswith("_")}
    deletes = sorted(n for n in public if "delete" in n or "remove" in n)
    assert deletes == ["batch_delete_tables", "delete_base", "delete_field", "delete_table",
                       "delete_view"]
    fenced = set(deletes) - {"delete_view", "delete_base"}
    assert fenced == set(destructive_ops()), (
        "every data-losing delete on this client is declared destructive, and therefore fenced")
    assert set(deletes) - fenced - {"delete_view"} == set(LIFECYCLE_OPS), (
        "a delete that is neither fenced by the consent doctrine nor declared a lifecycle call "
        "is a delete nobody declared")
    assert "drive" in schema_code().lower(), (
        "the whole-object delete IS a Drive call, and the module is where it lives now — the "
        "harness's teardown primitive is no longer the only route to it")


def test_a_SCOPE_DENIAL_still_arrives_as_the_librarys_own_typed_permission_error():
    denial = {"code": 99991672,
              "msg": "Access denied. One of the following scopes is required: [bitable:app]",
              "error": {"permission_violations": [{"type": "scope", "subject": "bitable:app"}]}}
    client = schema_client(create=[type("R", (), {"code": 99991672, "msg": denial["msg"],
                                                  "raw": None, **denial})()])
    with pytest.raises(LarkPermissionError):
        client.create_app("x", "fldrXYZ")


def test_the_client_WIDENS_REQUESTS_AND_ESCALATES_NO_SCOPE():
    source = schema_source().lower()
    for forbidden in ("request_scope", "widen", "escalate", "grant_scope"):
        assert forbidden not in source, forbidden
    assert not re.search(r"\bbitable:app\b", schema_code()), (
        "a scope string is authored in larkdocio.permissions and nowhere else")


# --------------------------------------------------------------------------- #
# LD-466 — THE WHOLE-OBJECT DELETE. Graded against tests/captures/ld466-delete-base/.      #
# --------------------------------------------------------------------------- #
#
# AC3, stated: the gate followed is the **whole-object** one that `delete_document` and
# `delete_spreadsheet` already establish, NOT the plan-and-consent fence. The reason is the
# consent fence's own doctrine — consent is consent to an ENUMERATED loss
# (`loss_preview.LOSS_MUST_BE_ENUMERABLE`), minted from a `SchemaPlan` — and a whole Base's loss
# is every table, column, record and view it holds, which no plan-time read enumerates. The
# endpoint is a Drive endpoint too, so it cannot carry a bitable read-back the way every
# registered schema op does. That is the identical split the sheets surface already ships:
# `DeleteTab` is plan-gated, `delete_spreadsheet` is not.


def delete_client(**legs):
    return schema_client(**legs)


def test_delete_base_sends_the_BASES_OWN_DRIVE_TYPE_and_DIFFERS_from_the_type_file_control():
    """R12 on the one key that matters here, with a measured control rather than a plausible one.

    ``type=file`` is not a hypothetical wrong value: it is what the shipped
    ``DriveFilesWriteClient.delete`` hardcodes, and capture ``ld466-01`` is Lark answering
    ``1061003 not found`` to it for a Base the same credentials had just created.
    """
    from larkdocio.base.schema_client import BASE_DRIVE_FILE_TYPE

    client = delete_client(file_delete=[base_delete_echo()])
    client.delete_base("appTOKEN")
    request = client._sdk.drive.v1.file.delete.requests[0]
    assert request.file_token == "appTOKEN"
    assert request.type == BASE_DRIVE_FILE_TYPE == "bitable"
    assert request.type != "file", (
        "the type=file control answers 1061003 for a Base — capture ld466-01")
    assert request.uri == "/open-apis/drive/v1/files/:file_token"


def test_delete_base_makes_exactly_ONE_paced_call_and_hands_the_reply_back():
    client = delete_client(file_delete=[base_delete_echo()])
    reply = client.delete_base("appTOKEN")
    assert client.api_calls == client.limiter.acquisitions == 1
    assert reply is not None


def test_delete_base_TOUCHES_NO_BITABLE_LEG_AT_ALL():
    """The blast radius said structurally: trashing the whole object is not a table op, and a
    Base delete that also called a bitable verb would be doing something nobody asked for."""
    client = delete_client(file_delete=[base_delete_echo()])
    client.delete_base("appTOKEN")
    assert client._sdk.bitable.v1.app.create.requests == []
    assert client._sdk.bitable.v1.app.update.requests == []
    assert client._sdk.bitable.v1.app_table.create.requests == []


def test_delete_base_is_NOT_IDEMPOTENT_and_the_already_gone_answer_arrives_TYPED():
    """Capture ``ld466-06``: the second delete answers ``1061007``, never a silent success."""
    from larkdocio.base.schema_client import base_is_gone
    from larkdocio.errors import LarkAPIError
    from larkdocio.sheets.write_client import FILE_ALREADY_DELETED_CODE

    client = delete_client(file_delete=[base_already_deleted_echo()])
    with pytest.raises(LarkAPIError) as caught:
        client.delete_base("appTOKEN")
    assert caught.value.code == FILE_ALREADY_DELETED_CODE == 1061007
    assert base_is_gone(caught.value), "the one predicate a finally needs must forgive this"


def test_the_WRONG_TYPE_answer_is_NOT_forgiven_as_gone():
    """``1061003`` is the *hardcode's* answer, and it is not evidence the Base is gone — the
    Base in capture ``ld466-01`` was alive and was deleted successfully three calls later."""
    from larkdocio.base.schema_client import base_is_gone
    from larkdocio.errors import LarkAPIError

    client = delete_client(file_delete=[base_wrong_drive_type_echo()])
    with pytest.raises(LarkAPIError) as caught:
        client.delete_base("appTOKEN")
    assert caught.value.code == 1061003
    assert not base_is_gone(caught.value)


def test_base_is_gone_SPANS_BOTH_ENDPOINTS_and_DEFINES_NO_SECOND_CODE():
    """One question, one answer — assembled from the two definitions that already exist.

    The bitable side's confirmation codes are ``loss_preview.OBJECT_GONE_CODES`` (the oracle the
    live harness's zero-orphan check uses); the Drive side's already-trashed code is the sheets
    surface's ``FILE_ALREADY_DELETED_CODE``. Both are IMPORTED. A literal re-spelling of either
    would be the second disagreeing opinion this test exists to forbid.
    """
    from larkdocio.base import schema_client as sc
    from larkdocio.base.loss_preview import OBJECT_GONE_CODES
    from larkdocio.sheets.write_client import FILE_ALREADY_DELETED_CODE

    assert set(sc.BASE_GONE_CODES) == set(OBJECT_GONE_CODES) | {FILE_ALREADY_DELETED_CODE}
    for code in sc.BASE_GONE_CODES:
        assert sc.base_is_gone(type("E", (), {"code": code})())
        assert sc.base_is_gone(type("E", (), {"code": str(code)})()), (
            "the wire may hand back an int or a str — the same discipline spreadsheet_is_gone "
            "keeps")
    assert not sc.base_is_gone(type("E", (), {"code": 99991672})())
    assert not sc.base_is_gone(type("E", (), {"code": None})()), (
        "a code-less error is a failure BELOW Lark: whether the Base is gone is unknown there "
        "and must not be assumed")
    assert not sc.base_is_gone(ValueError("not a Lark answer"))

    source = inspect.getsource(sc)
    for literal in ("1061007", "1002", "91402", "1254041"):
        assert literal not in schema_code(), (
            f"{literal} is authored elsewhere and must be imported, not re-spelled")
    assert "OBJECT_GONE_CODES" in source and "FILE_ALREADY_DELETED_CODE" in source


def test_delete_base_TAKES_NO_CONSENT_TOKEN_and_is_NOT_A_REGISTERED_SCHEMA_OP():
    """AC3's decision, pinned rather than merely written down.

    The whole-object precedent means: no ``consent`` parameter (there is no plan to mint one
    from), and no descriptor in the schema-op registry (the endpoint is not a bitable one and
    there is nothing for ``schema_dry_run`` to preview). Both halves are asserted, because
    either one alone would leave a third gate shape reachable.
    """
    from larkdocio.base import schema_ops

    parameters = inspect.signature(BaseSchemaClient.delete_base).parameters
    assert list(parameters) == ["self", "app_token"]
    registered = {d.name for d in schema_ops.schema_ops()}
    assert "delete_base" not in registered and "delete_app" not in registered


def test_the_verb_DISCLOSES_trash_not_purge_and_that_the_RE_READ_is_the_proof():
    """The original reason survives as the docstring's honest statement of what the call does."""
    doc = inspect.getdoc(BaseSchemaClient.delete_base)
    lowered = doc.lower()
    assert "trash" in lowered and "purge" in lowered
    assert "base_is_gone" in doc
    assert "code: 0" in lowered or "code:0" in lowered
    assert "metas/batch_query" in doc, (
        "the measured half of trash-not-purge on a Base: Drive metadata STILL resolves the "
        "trashed token (capture ld466-07) — the disclosure names the read that shows it")
    assert "ld466" in doc.lower(), "a measured claim cites the capture that measured it"


def test_LIFECYCLE_OPS_declares_the_DESTROY_HALF_and_says_where_the_CREATE_half_lives():
    """A one-member lifecycle, on the ``DriveFilesWriteClient.LIFECYCLE_OPS`` precedent.

    The asymmetry is real and is disclosed rather than smoothed over: the Base's create is
    ``create_app``, a **registered, plan-gated schema op** on a bitable endpoint, so it is
    published under ``operations``; the destroy is a Drive call with no plan of its own, so it is
    published under ``lifecycle``. Naming ``create_app`` in both would collapse two permission
    rows into one.
    """
    from larkdocio.base import schema_client as sc

    assert sc.LIFECYCLE_OPS == ("delete_base",)
    for name in sc.LIFECYCLE_OPS:
        assert callable(getattr(BaseSchemaClient, name))
    module_doc = inspect.getdoc(sc)
    assert "create_app" in module_doc and "LIFECYCLE_OPS" in module_doc


def test_the_verbs_DERIVED_permission_row_is_EXACTLY_the_endpoint_IT_CALLS():
    """A docstring is prose, not a call site — and the derivation cannot tell the difference.

    Caught during this change: the trash-not-purge disclosure originally spelled Drive's
    metadata route as a full ``/open-apis/...`` path, and ``permissions.endpoints_of`` — which
    reads string literals out of the function's own source, because that is what makes a
    raw-path call site derivable at all — reported ``delete_base`` as **reaching** that endpoint.
    It does not: it makes exactly one call. An over-claimed row is the same class of defect as a
    missing one (it tells a consumer to hold a requirement nothing here demands), so the
    disclosure names the route without spelling a path and this pins the consequence.
    """
    from larkdocio.permissions import endpoints_of, permission_registry

    assert endpoints_of(BaseSchemaClient.delete_base) == (
        "/open-apis/drive/v1/files/:file_token",)
    row = permission_registry()[("base-schema-write", "delete_base")]
    assert row.endpoints == ("/open-apis/drive/v1/files/:file_token",)
    assert row.kind == "lifecycle" and row.mode == "write"
    doc = inspect.getdoc(BaseSchemaClient.delete_base)
    assert "metas/batch_query" in doc, "the disclosure still names the route it measured"
    assert "/open-apis/drive/v1/metas" not in doc, (
        "spelling it as a path makes the derivation claim a call this verb never makes")
