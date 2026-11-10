"""LD-356 — naming a new table's DEFAULT VIEW: the create-then-rename composite.

LD-344 measured that ``create_table`` **rejects** a body carrying ``default_view_name``
(``1254001 WrongRequestBody``, no table created). The goal survives one call later: a fresh table
has **exactly one** view, and that view can be renamed with the ``update_view`` this library
already ships. This file pins the composite — and, more importantly, pins the **posture when the
second leg fails after the first one landed**, which is the seat's ruling and not a preference:

    **SURFACE THE PARTIAL STATE, TYPED. No auto-rollback. No retry loop.**

Four clauses, each with its own assertion below: the library **never deletes** the table it just
created; it raises a **typed** partial outcome carrying the ``table_id``, the ``view_id`` (or an
explicit *not learned*), the requested name and **Lark's unedited denial**; there is **no silent
success**; and there is **exactly one** rename attempt.

**Everything here is offline.** The create echo is rebuilt from probe ``ld356-01``'s own capture
and the refusal is a real captured code/msg, so a drift in either reddens rather than travelling
on as a plausible-looking ``None``. The failure path needs no live Lark at all.
"""
import io
import tokenize

import pytest

from base_schema_fakes import (
    VIEW_REFUSAL_CODE,
    VIEW_REFUSAL_MSG,
    FakeBaseWorld,
    ScriptedSchemaClient,
    create_table_echo,
    create_table_echo_with_default_view,
    default_view_id,
    measured_default_view_name,
    schema_client,
    view_rename_echo,
    view_rename_refusal,
)
# The ONE body serializer, imported rather than re-defined: two opinions about what a built
# request puts on the wire is one too many.
from test_base_schema_client import body_of
from log_reading_apply import reading_the_log
from larkdocio.base.errors import COMPOSITE_IS_NOT_ATOMIC, TableCreatedViewNotNamed
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
schema_apply = reading_the_log(schema_apply)
from larkdocio.base.schema_plan import create_table as plan_create_table

from guard_kit import REPO_ROOT

APP = "Example02154ddbd1fe2927e2e6"

_BASE_PKG = REPO_ROOT / "src" / "larkdocio" / "base"

#: The modules the composite is written in: the client seam, the view call it composes, the
#: family that carries its doctrine and its read-back, and the plan seam that fronts it.
COMPOSITE_MODULES = ("schema_client.py", "view_client.py", "schema_ops_app_table.py",
                     "schema_plan.py")

#: The two the *write* client is made of. Scanned separately, because the read-back legitimately
#: lists views — from the ENGINE's read seam, which is a different client entirely.
WRITE_CLIENT_MODULES = ("schema_client.py", "view_client.py")


def code_of(*names):
    """Those modules' source with every string literal and comment removed.

    The scans below ask *"does any CODE PATH do X"*, and prose explaining why the code
    deliberately does **not** do X would otherwise trip them.
    """
    out = []
    for name in names:
        text = (_BASE_PKG / name).read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in (tokenize.STRING, tokenize.COMMENT):
                out.append(token.string)
    return "\n".join(out)


def _named_client(view_patch):
    return schema_client(table_create=[create_table_echo_with_default_view()],
                         view_patch=view_patch)


# --------------------------------------------------------------------------- #
# AC2 — the composite ships behind the doctrine's EXISTING grammar              #
# --------------------------------------------------------------------------- #

def test_an_UNNAMED_create_is_STILL_ONE_CALL_and_sends_the_SAME_BODY():
    """The unnamed path stays reachable and stays **one** call.

    This issue must not make every existing ``create_table`` call site do a second write. The
    fake's view PATCH leg is *forbidden* here, so a stray second call is an error rather than an
    assertion nobody reads.
    """
    client = schema_client(table_create=[create_table_echo_with_default_view()])
    table_id = client.create_table(APP, "unnamed", primary_field_name="Title")

    assert table_id == "tbl9dAKfZPqXcPIx" or table_id
    assert client.api_calls == 1, "an unnamed create is ONE call, exactly as it always was"
    assert len(client._sdk.bitable.v1.app_table.create.requests) == 1


def test_a_NAMED_create_renames_the_default_view_in_a_SECOND_call():
    """AC2's positive half: ask for the name, get a table whose default view carries it."""
    client = _named_client([view_rename_echo()])
    client.create_table(APP, "named", primary_field_name="Title",
                        default_view_name="Board")

    patches = client._sdk.bitable.v1.app_table_view.patch.requests
    assert len(patches) == 1, "one create, one rename — the composite is two calls, not three"
    assert body_of(patches[0]) == {"view_name": "Board"}
    assert patches[0].view_id == default_view_id()
    assert client.api_calls == 2


def test_the_create_BODY_still_carries_NO_default_view_name_KEY():
    """LD-344's measurement is untouched: the key is refused by the server, so no code path may
    put it on the create body — the composite renames **afterwards**, it does not smuggle."""
    client = _named_client([view_rename_echo()])
    client.create_table(APP, "named", primary_field_name="Title", default_view_name="Board")

    body = body_of(client._sdk.bitable.v1.app_table.create.requests[0])
    assert "default_view_name" not in str(body)
    assert set(body["table"]) == {"name", "fields"}


# --------------------------------------------------------------------------- #
# AC3 — the default view is identified WITHOUT a locale-dependent name          #
# --------------------------------------------------------------------------- #

def test_the_default_view_is_found_by_the_CREATES_OWN_ECHO_and_never_by_a_NAME():
    """AC3, and the whole reason this doctrine exists.

    Lark calls a fresh table's single view ``表格视图 1`` **on this tenant** — a locale string.
    The composite never sees it: the create's own response body names the view
    (``default_view_id``, measured on the kitted create in ``ld356-01``, equal to the single
    listed view's id), so the rename is addressed by **id**. No listing, no comparison, nothing
    that could differ per tenant.
    """
    client = _named_client([view_rename_echo()])
    client.create_table(APP, "named", primary_field_name="Title", default_view_name="Board")

    assert client._sdk.bitable.v1.app_table_view.patch.requests[0].view_id == default_view_id()
    locale_name = measured_default_view_name()
    assert locale_name and locale_name not in code_of(*COMPOSITE_MODULES), (
        f"{locale_name!r} is the TENANT'S name for a fresh view; a module that carried it "
        "would be the locale dependence this whole doctrine exists to kill")
    assert "list_views" not in code_of(*WRITE_CLIENT_MODULES), (
        "the write client does not list views to find the default one — the create echo names "
        "it, and the read-back that verifies the rename is the ENGINE's read seam")


# --------------------------------------------------------------------------- #
# AC4 — the failed-rename posture, all four clauses of the seat ruling          #
# --------------------------------------------------------------------------- #

def test_a_FAILED_rename_raises_the_TYPED_partial_outcome_carrying_EVERYTHING():
    """Clauses 2 and 3: typed, complete, and Lark's own words — never a silent success."""
    client = _named_client([view_rename_refusal()])

    with pytest.raises(TableCreatedViewNotNamed) as caught:
        client.create_table(APP, "named", primary_field_name="Title",
                            default_view_name="Board")

    partial = caught.value
    assert partial.table_id == "tbl9dAKfZPqXcPIx" or partial.table_id
    assert partial.view_id == default_view_id()
    assert partial.view_id_learned is True
    assert partial.requested_view_name == "Board"
    # Lark's denial, UNEDITED — code and msg both, reproduced rather than paraphrased.
    assert partial.code == VIEW_REFUSAL_CODE
    assert partial.msg == VIEW_REFUSAL_MSG
    assert VIEW_REFUSAL_MSG in str(partial) and str(VIEW_REFUSAL_CODE) in str(partial)
    # The ids a caller needs to finish the job themselves are in the PAYLOAD, not only in prose.
    assert partial.table_id in str(partial) and partial.view_id in str(partial)
    assert partial.__cause__ is not None, "Lark's own exception is chained, never swallowed"


#: A SCOPE DENIAL on the rename leg, in Lark's own shape: the code, a message naming the scope
#: the way Lark names it (in square brackets — what ``permissions._MSG_SCOPES_RE`` reads), and
#: the ``error.helps`` console deep link, which exists only in a response body.
VIEW_DENIAL_CODE = 99991672
VIEW_DENIAL_MSG = "Forbidden: the app lacks [bitable:app]"
VIEW_DENIAL_CONSOLE = "https://open.larksuite.com/app/cli_x/auth"


def _view_rename_denial():
    from lark_oapi.api.bitable.v1 import PatchAppTableViewResponse
    from base_schema_fakes import unmarshal

    return unmarshal({"code": VIEW_DENIAL_CODE, "msg": VIEW_DENIAL_MSG,
                      "error": {"helps": [{"url": VIEW_DENIAL_CONSOLE}]}},
                     PatchAppTableViewResponse)


def test_a_rename_refused_for_a_MISSING_SCOPE_carries_the_denial_out_with_the_partial_outcome():
    """The composite is a WRAPPER, and a wrapper that keeps ``code``/``msg`` but drops the
    classification hands a caller a scope problem wearing the costume of an ordinary one.

    This is the one path on which the promise the shipped guide makes — *test a denial with*
    ``err.denial is not None``, *not with the class* — was false: the CREATE landed, the rename
    was refused for a missing grant, and the typed partial outcome carried Lark's code and
    message but no record of what was missing, no console link and no credential attribution.

    Driven through the real ``create_table`` seam, not through the builder, because the whole
    question is whether the record survives the leg that raises it.
    """
    client = _named_client([_view_rename_denial()])

    with pytest.raises(TableCreatedViewNotNamed) as caught:
        client.create_table(APP, "named", primary_field_name="Title",
                            default_view_name="Board")

    partial = caught.value
    assert partial.denial is not None, (
        "the denial record was dropped by the wrapper — on this path a missing scope is "
        "indistinguishable from any other rename failure")
    assert partial.denial.scopes == ("bitable:app",)
    assert partial.denial.console_url == VIEW_DENIAL_CONSOLE, (
        "the console link lives only in the response body; re-deriving the record from "
        "code/msg here would silently lose it")
    assert partial.denial.credential_env, "a denial must say WHICH credential pair to fix"
    # FORWARDED, not rebuilt — the same object the classifying seam already made.
    assert partial.denial is partial.__cause__.denial
    # And the partial state is unchanged: the wrapper gained an attribute, it lost nothing.
    assert partial.code == VIEW_DENIAL_CODE and partial.msg == VIEW_DENIAL_MSG
    assert partial.table_id and partial.view_id == default_view_id()
    assert partial.requested_view_name == "Board"


def test_an_ORDINARY_rename_refusal_still_carries_NO_denial_and_the_SAME_message_bytes():
    """The control. Adding the classification must not make an ordinary refusal read as a
    scope denial, and the sentence a caller reads is byte-for-byte what it was — the local
    that holds Lark's quoted words was renamed in the same change, so this is the assertion
    that the rename moved no text."""
    client = _named_client([view_rename_refusal()])

    with pytest.raises(TableCreatedViewNotNamed) as caught:
        client.create_table(APP, "named", primary_field_name="Title",
                            default_view_name="Board")

    partial = caught.value
    assert partial.denial is None
    assert str(partial) == (
        f"the table was CREATED and its default view was NOT renamed. "
        f"table_id={partial.table_id!r}, view_id={partial.view_id!r}, requested name="
        f"'Board'. Lark's own answer, unedited: Code: {VIEW_REFUSAL_CODE}, "
        f"Msg: {VIEW_REFUSAL_MSG}. NOTHING was rolled back — this library never "
        f"deletes a table to undo a cosmetic failure — and NOTHING was retried. "
        f"{COMPOSITE_IS_NOT_ATOMIC}")


def test_a_FAILED_rename_DELETES_NOTHING_and_attempts_the_rename_EXACTLY_ONCE():
    """Clauses 1 and 4: no rollback, no retry — both **structural**, not intentions.

    The fake SDK's every delete leg raises on contact, so a rollback would fail this test with
    its own message rather than with a count nobody reads.
    """
    client = _named_client([view_rename_refusal()])

    with pytest.raises(TableCreatedViewNotNamed):
        client.create_table(APP, "named", primary_field_name="Title", default_view_name="Board")

    assert len(client._sdk.bitable.v1.app_table_view.patch.requests) == 1, (
        "ONE attempt. A retry hides which call failed and multiplies calls against a "
        "rate-limited surface")
    assert client.api_calls == 2, "the create and the one rename — nothing else was sent"


def test_the_partial_outcome_says_the_view_id_was_NOT_LEARNED_when_the_echo_carries_NONE():
    """The honest third state. ``05-03`` is a real create echo that carries ``table_id`` alone.

    The composite does **not** guess, does not list, and does not quietly succeed: it says the
    view id was not learned, hands back the table id, and names the one call that finds it.
    """
    client = schema_client(table_create=[create_table_echo()])

    with pytest.raises(TableCreatedViewNotNamed) as caught:
        client.create_table(APP, "named", primary_field_name="Title", default_view_name="Board")

    partial = caught.value
    assert partial.view_id is None
    assert partial.view_id_learned is False
    assert partial.code is None and partial.msg is None, (
        "there was no Lark denial to reproduce here — the create simply did not name the view — "
        "and none is invented")
    assert "list_views" in str(partial), "the caller is told the one call that finds the view"
    assert partial.table_id in str(partial)


# --------------------------------------------------------------------------- #
# AC5 — the NON-ATOMICITY is documented where the caller meets it               #
# --------------------------------------------------------------------------- #

def test_the_NON_ATOMICITY_is_stated_in_the_docstrings_a_caller_reads():
    from larkdocio.base.schema_client import BaseSchemaClient

    for doc in (BaseSchemaClient.create_table.__doc__, plan_create_table.__doc__):
        lowered = (doc or "").lower()
        assert "not atomic" in lowered, (
            "the composite is two calls and this library does not pretend otherwise — naming "
            "the non-atomicity is the truthful move, and the one a caller can act on")
        assert "tablecreatedviewnotnamed" in lowered.replace("`", ""), (
            "the docstring must name the typed partial outcome a caller has to catch")


# --------------------------------------------------------------------------- #
# The PLAN seam and the ENGINE — the same composite, verified by READ-BACK      #
# --------------------------------------------------------------------------- #

def test_the_plan_seam_carries_the_name_and_PRICES_the_second_read():
    request = plan_create_table(APP, "named", primary_field_name="Title",
                                default_view_name="Board")

    assert request.arguments["default_view_name"] == "Board"
    assert "Board" in request.describe, "a dry run shows the view name BEFORE the call is made"
    assert request.traits["read_cost"] == 3, (
        "the table listing, the column listing and now the VIEW listing — the plan prices the "
        "read-back before anything is sent")
    plain = plan_create_table(APP, "plain", primary_field_name="Title")
    assert "default_view_name" not in plain.arguments
    assert plain.traits["read_cost"] == 2, "an unnamed create's price is exactly what it was"


def test_the_engine_READS_THE_VIEW_BACK_and_confirms_the_name_LANDED():
    world = FakeBaseWorld(apps={APP: "Base"}, tables={APP: {}})
    client = ScriptedSchemaClient(world)

    log = schema_apply(schema_dry_run([
        plan_create_table(APP, "named", primary_field_name="Title",
                          default_view_name="Board")]),
        client=client, read_client=world)

    entry = log.entries[0]
    assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
    assert entry.read_back["default_view"] == {
        "asked": "Board", "seen": ["Board"], "views": 1, "named": True}


def test_a_DEAF_rename_is_NOT_confirmed_R12():
    """The negative control. ``code:0`` proves acceptance and nothing else on the view route —
    the sibling key ``group_info`` answers ``code:0`` and persists nothing — so a rename that
    changed nothing must come back **not confirmed** rather than applied."""
    world = FakeBaseWorld(apps={APP: "Base"}, tables={APP: {}})
    client = ScriptedSchemaClient(world, deaf={"create_table_default_view"})

    log = schema_apply(schema_dry_run([
        plan_create_table(APP, "named", primary_field_name="Title",
                          default_view_name="Board")]),
        client=client, read_client=world)

    entry = log.entries[0]
    assert entry.outcome != "applied", (
        "a rename that answered and did nothing must not be reported applied — that is the "
        "whole reason this rung verifies by read-back")
    assert entry.read_back["default_view"]["named"] is False
    assert entry.read_back["default_view"]["seen"] == [FakeBaseWorld.DEFAULT_VIEW]


def test_a_PARTIAL_OUTCOME_at_apply_is_logged_APPLIED_UNVERIFIED_never_NOTHING_LANDED():
    """The engine's boundary must not tell the opposite of the truth.

    The table **is** on the Base when the rename fails, so classifying the partial outcome as an
    ordinary API error — whose wording is *"NOTHING landed"* — would be a lie about a Base the
    caller now has to reconcile. It is classified as the landed-but-unverified write it is.
    """
    from larkdocio.base.disposition import classify_apply_exception

    partial = TableCreatedViewNotNamed(
        "the table landed; the view keeps Lark's name", table_id="tblX", view_id="vewY",
        view_id_learned=True, requested_view_name="Board",
        code=VIEW_REFUSAL_CODE, msg=VIEW_REFUSAL_MSG)
    disposition = classify_apply_exception(partial, wrote=False)

    assert disposition.outcome == "applied-unverified"
    assert disposition.landed == "yes"
