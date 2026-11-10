"""LD-456 — the access surface's OBJECT TYPE, widened past docx and refused typed past that.

The bug this file pins: ``DriveAccessWriteClient`` hardcoded ``type=docx`` into every request,
so a grant or a member read against a Base or a spreadsheet died as a bare
``Code: 1063001, Msg: Invalid parameter`` at every permission level and for every identifier —
while the library carried the docx-only record twice internally and said **nothing** at the
moment of failure.

Four regions, one per AC that can be proved offline:

* **AC1** — the type is a parameter: ``obj_type=`` in larkdocio's OWN vocabulary
  (``docx`` / ``sheets`` / ``base``, and Lark's own ``sheet`` / ``bitable`` accepted too), or
  read off a URL the caller already holds. A caller therefore never has to know Lark's
  spelling. Every verb carries it, and the value that reaches the wire is asserted per verb.
* **AC3** — everything the widening does NOT cover refuses **locally, before the call**, in the
  library's voice, naming the limit and the way forward; and where Lark itself answers
  ``1063001`` the library wraps it and says what that code means on this family.
* **AC4** — the bare-display-name refusal names ``larkdocio.contacts.resolve_user(name=…)``
  with a one-line example and carries **no file:line citation** (a consumer holding a wheel has
  no source tree to look one up in).
* **AC5** — the supersession: the absence row keeps its ORIGINAL REASON verbatim and replaces
  only its conclusion, and the ``capabilities()`` projection of it moves in the same change.

The live half (AC2 — a grant that really stored on a Base and on a spreadsheet) is
``tests/test_live_drive_access_gate.py``; nothing here claims a type stores.
"""
import inspect
import pathlib

import access_fixtures as afx
import pytest

from larkdocio.drive import access
from larkdocio.drive.access import (
    ABSENCES,
    BARE_NAME_REFUSAL,
    DEFAULT_OBJECT_TYPE,
    INVALID_PARAMETER_MEANS,
    OBJECT_TYPES_MEASURED,
    OBJECT_TYPE_ALIASES,
    OBJECT_TYPE_UNSUPPORTED,
    WIRE_OBJECT_TYPES,
    AccessRefusedError,
    object_target,
)
from larkdocio.drive.access_write import DriveAccessWriteClient
from larkdocio.errors import LarkAPIError

DOC = afx.DOC
GRANTEE = afx.GRANTEE_OPEN_ID

#: A Base and a spreadsheet token, in the shape the live gate's own disposables carry. Neither
#: is a real object: nothing offline reaches the network, and neither is ever addressed live.
BASE_TOKEN = "Z1a2b3c4d5e6f7g8h9i0jklmnopq"
SHEET_TOKEN = "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9S"


def client(route, **kwargs):
    transport = afx.RecordingTransport(route)
    kwargs.setdefault("token_fetcher", afx.token_fetcher)
    kwargs.setdefault("rate_limiter", afx.fast_limiter())
    return DriveAccessWriteClient("app-id", "app-secret", urlopen=transport, **kwargs), transport


def grant_route():
    return afx.access_router(
        member_write=afx.response(afx.GRANT_FULL_ACCESS),
        members_pages=[afx.response(afx.MEMBERS_FULL_ACCESS)],
    )


# --------------------------------------------------------------------------- #
# AC1 — THE TYPE IS A PARAMETER, in the caller's vocabulary.                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("verb", ["grant_access", "update_access", "revoke_access",
                                  "list_members", "set_copy_permissions"])
def test_ac1_EVERY_verb_carries_the_object_type(verb):
    """The fence LD-432 built by construction — *no method takes an object type* — is the exact
    thing LD-456 supersedes. It is transformed, not deleted: the assertion now runs the other
    way and still holds every verb to the same rule."""
    parameters = inspect.signature(getattr(DriveAccessWriteClient, verb)).parameters
    assert "obj_type" in parameters, verb
    assert parameters["obj_type"].default is None, (
        f"{verb} must default to None so the resolution — not the signature — decides")


@pytest.mark.parametrize("spelling,wire", [
    ("docx", "docx"),
    ("sheets", "sheet"), ("sheet", "sheet"), ("spreadsheet", "sheet"),
    ("base", "bitable"), ("bitable", "bitable"),
    ("  Base  ", "bitable"),
])
def test_ac1_the_callers_OWN_vocabulary_reaches_larks(spelling, wire):
    """A caller must be able to succeed **without knowing Lark's type vocabulary**: larkdocio
    says ``sheets`` / ``base`` where Lark says ``sheet`` / ``bitable``, and both spellings are
    accepted here so neither side's word is the one you had to have known."""
    assert object_target(BASE_TOKEN, spelling) == (BASE_TOKEN, wire)


def test_ac1_the_GRANT_sends_the_asked_for_type_and_so_does_its_read_back():
    access_client, transport = client(grant_route())

    access_client.grant_access(BASE_TOKEN, open_id=GRANTEE, perm="full_access",
                               obj_type="base")

    sent, read_back = transport.calls
    assert sent.params == {"type": "bitable", "need_notification": "false"}
    assert read_back.params == {"type": "bitable"}, (
        "the read-back that IS the verdict must address the same object as the write")


@pytest.mark.parametrize("obj_type,wire", [("sheets", "sheet"), ("base", "bitable")])
def test_ac1_the_LIST_and_its_OWNER_leg_both_carry_the_type(obj_type, wire):
    """``metas/batch_query`` takes the same vocabulary in its own ``doc_type`` key — an owner
    leg still saying ``docx`` would report the wrong object's owner or nothing at all."""
    route = afx.access_router(members_pages=[afx.response(afx.MEMBERS_EMPTY)],
                              meta=afx.response(afx.META_OWNER))
    access_client, transport = client(route)

    access_client.list_members(SHEET_TOKEN, obj_type=obj_type)

    members_call, meta_call = transport.calls
    assert members_call.params == {"type": wire}
    assert meta_call.body["request_docs"][0]["doc_type"] == wire


def test_ac1_UPDATE_and_REVOKE_and_the_COPY_LEVER_carry_it_too():
    route = afx.access_router(
        member_write=afx.response(afx.UPDATE_RAISE),
        members_pages=[afx.response(afx.MEMBERS_AFTER_RAISE)],
    )
    access_client, transport = client(route)
    access_client.update_access(BASE_TOKEN, open_id=GRANTEE, perm="full_access",
                                obj_type="base")
    assert transport.calls[0].params["type"] == "bitable"

    route = afx.access_router(member_write=afx.response(afx.REVOKE),
                              members_pages=[afx.response(afx.MEMBERS_AFTER_REVOKE)])
    access_client, transport = client(route)
    access_client.revoke_access(BASE_TOKEN, open_id=GRANTEE, obj_type="bitable")
    assert transport.calls[0].params == {"type": "bitable", "member_type": "openid"}

    route = afx.access_router(public_patch=afx.response(afx.PATCH_COPY),
                              public_pages=[afx.response(afx.PUBLIC_AFTER_COPY)])
    access_client, transport = client(route)
    access_client.set_copy_permissions(SHEET_TOKEN, copy_entity="anyone_can_view",
                                       obj_type="sheets")
    assert [call.params["type"] for call in transport.calls] == ["sheet", "sheet"]


def test_ac1_a_URL_carries_its_own_type_so_a_caller_need_name_none():
    """The library already routes by surface off a URL (``larkdocio.common.url``). Handing this
    surface the link a human pasted is therefore the one way a caller needs **no** type
    vocabulary at all — and the token comes out of the same parse."""
    url = f"https://your-domain.larksuite.com/base/{BASE_TOKEN}"
    assert object_target(url) == (BASE_TOKEN, "bitable")
    assert object_target(f"https://x.larksuite.com/sheets/{SHEET_TOKEN}") == (
        SHEET_TOKEN, "sheet")
    assert object_target(f"https://x.larksuite.com/docx/{DOC}") == (DOC, "docx")


def test_ac1_a_BARE_TOKEN_with_no_type_stays_DOCX_the_documented_default():
    """A bare Lark token carries no type — every shape is the same alphabet — so the default is
    **declared**, not inferred: docx, which is what every caller of this surface got before
    LD-456 and what the docstring names."""
    assert DEFAULT_OBJECT_TYPE == "docx"
    assert object_target(DOC) == (DOC, "docx")
    assert "docx" in DriveAccessWriteClient.grant_access.__doc__


def test_ac1_a_URL_and_an_obj_type_that_DISAGREE_are_refused_not_reconciled():
    with pytest.raises(AccessRefusedError) as excinfo:
        object_target(f"https://x.larksuite.com/base/{BASE_TOKEN}", "docx")
    message = str(excinfo.value)
    assert "base" in message and "docx" in message
    assert "which" in message.lower() or "disagree" in message.lower()


# --------------------------------------------------------------------------- #
# AC3 — WHAT STAYS OUT IS REFUSED IN THE LIBRARY'S VOICE, at the moment of use. #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("unsupported", ["folder", "file", "wiki", "docs", "mindnote", "slides"])
def test_ac3_a_type_this_surface_cannot_vouch_for_is_refused_BEFORE_the_call(unsupported):
    with pytest.raises(AccessRefusedError) as excinfo:
        object_target(DOC, unsupported)
    message = str(excinfo.value)
    assert unsupported in message, "the refusal quotes what was asked for"
    for measured in WIRE_OBJECT_TYPES:
        assert measured in message, f"{measured} is not named as what IS supported"


@pytest.mark.conformance
def test_ac3_the_refusal_names_the_WAY_FORWARD_rather_than_only_the_limit():
    text = OBJECT_TYPE_UNSUPPORTED.lower()
    assert "unmeasured" in text, "untried is not the same as impossible"
    assert "wiki" in text, "the type a caller most often holds is answered by name"
    assert "obj_type" in text


def test_ac3_a_refusal_spends_NO_call():
    route = afx.access_router()          # every branch of this router asserts if reached
    access_client, transport = client(route)
    with pytest.raises(AccessRefusedError):
        access_client.grant_access(DOC, open_id=GRANTEE, obj_type="folder")
    assert transport.calls == []
    assert access_client.api_calls == 0


@pytest.mark.conformance
def test_ac3_LARKS_OWN_1063001_is_WRAPPED_and_explained_rather_than_relayed_bare():
    """The dogfood failure verbatim: ``Code: 1063001, Msg: Invalid parameter`` with no library
    voice at all. Lark's code and message survive — they are the evidence — and the library
    adds what that code MEANS on this family."""
    refusal = {"code": 1063001, "msg": "Invalid parameter"}
    access_client, _transport = client(afx.access_router(member_write=refusal))

    with pytest.raises(LarkAPIError) as excinfo:
        access_client.grant_access(BASE_TOKEN, open_id=GRANTEE, obj_type="base")

    message = str(excinfo.value)
    assert excinfo.value.code == 1063001, "Lark's own code is preserved, never swallowed"
    assert "Invalid parameter" in message, "Lark's own msg is preserved"
    assert "bitable" in message, "the type that was actually sent is named"
    assert "obj_type" in message, "the knob that fixes it is named"
    assert message != "drive grant_access failed: Code: 1063001, Msg: Invalid parameter"


def test_ac3_a_1063001_on_a_type_LARK_answered_for_still_reaches_the_caller_typed():
    assert "1063001" in INVALID_PARAMETER_MEANS
    assert "{obj_type}" in INVALID_PARAMETER_MEANS or "obj_type" in INVALID_PARAMETER_MEANS


# --------------------------------------------------------------------------- #
# AC4 — THE NAME REFUSAL names the shipped verb, and cites no source line.       #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac4_the_name_refusal_NAMES_the_verb_that_answers_it():
    assert "larkdocio.contacts.resolve_user" in BARE_NAME_REFUSAL
    assert "name=" in BARE_NAME_REFUSAL, "a one-line example, not just a module path"


@pytest.mark.conformance
def test_ac4_the_name_refusal_CITES_NO_SOURCE_LINE():
    """A consumer installs a wheel. ``larkdocio/contacts/lookup.py line 383`` is an instruction
    to open a file they do not have."""
    lowered = BARE_NAME_REFUSAL.lower()
    assert " line " not in lowered
    assert ".py" not in lowered
    assert "lookup.py" not in lowered and "__init__.py" not in lowered


@pytest.mark.conformance
def test_ac4_the_refusal_ITSELF_stands_a_name_is_still_not_an_id():
    """The maintainer did not rule the refusal away — naming a person is still not an id, and the
    address route's reach is still what it was. Only the *help* changed."""
    lowered = BARE_NAME_REFUSAL.lower()
    assert "email" in lowered and "open_id" in lowered
    assert "unmeasured" in lowered or "measured reach" in lowered
    with pytest.raises(AccessRefusedError):
        access.grantee_id(email="Some Person")


def test_ac4_the_shipped_verb_the_refusal_names_really_exists_and_takes_a_name():
    from larkdocio.contacts import resolve_user

    assert "name" in inspect.signature(resolve_user).parameters


# --------------------------------------------------------------------------- #
# AC5 — THE SUPERSESSION: the reason survives, the conclusion moves.             #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac5_the_absence_row_keeps_its_ORIGINAL_REASON_verbatim():
    """`process/doctrine/supersession.md` § A.1: preserve the reason, supersede only the
    conclusion. The original sentence is quoted inside the new row, not struck from it."""
    assert "Every measurement behind this surface was made with type=docx" in \
        OBJECT_TYPES_MEASURED
    assert "supersedes" in OBJECT_TYPES_MEASURED.lower(), (
        "the shipped row says it replaced a narrower one, so the reason it quotes reads as a "
        "quotation rather than as a live claim")
    # The issue id lives in the MODULE's own comment, never in the shipped sentence: a consumer
    # holds only the wheel, where an issue id resolves to nothing (the same rule the bare-name
    # refusal has always been held to, and what the consumer-dialect guard reddens on).
    source = pathlib.Path(inspect.getfile(access)).read_text(encoding="utf-8")
    assert "LD-456" in source and "supersession" in source
    assert "LD-456" not in OBJECT_TYPES_MEASURED


@pytest.mark.conformance
def test_ac5_the_new_conclusion_is_the_one_that_ships_and_the_old_one_does_not():
    lowered = OBJECT_TYPES_MEASURED.lower()
    assert "docx only" not in lowered, "the superseded conclusion may not still be asserted"
    assert not hasattr(access, "DOCX_ONLY"), (
        "the docx-only row is superseded; a constant still named DOCX_ONLY would read as a "
        "live claim")


def test_ac5_the_row_is_still_carried_as_DATA_in_the_projected_absences():
    assert OBJECT_TYPES_MEASURED in ABSENCES
    assert not any("DOCX ONLY." in text for text in ABSENCES)


def test_ac5_the_CAPABILITIES_projection_moved_with_it():
    import larkdocio

    surface = larkdocio.capabilities(full=True)["surfaces"]["drive-access-write"]
    note = surface["credentials"]["note"].lower()
    assert "docx only" not in note
    for measured in ("sheet", "bitable"):
        assert measured in note
    assert "obj_type" in note
