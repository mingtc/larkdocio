"""LD-583 — typed ``create_*`` / ``copy_*`` returns, in the DICT-COMPATIBLE shape.

The round paid a live object for this class (`dev/dogfood5/DIGEST.md` § 3 ranked major #8,
``:141-145``): an orphaned spreadsheet whose creator never held its token, an ``InvalidURL``
crash *after* the object already existed, and a false footprint self-report. All three are the
same defect — nothing about the returned value told the caller **what they now hold** or **what
the reply did not answer**.

The fix is the one DIGEST § 6(b)12 (``:426-428``) named: *"consistency, not invention"* —
``drive/folders_write.py``'s ``CreatedFolder`` is the answer key, and the four verbs that make a
new top-level object and did **not** already answer with a type are brought to it.

**The compatibility obligation is PER VERB, because the trunk shape was not uniform:**

* ``create_document`` / ``create_spreadsheet`` returned a **plain dict** → the old **keys** must
  keep answering by subscript, and ``==`` against the old plain dict must still hold. The types
  are ``dict`` subclasses whose body **is** the reply's own dict, so every dict operation is
  ``dict``'s own implementation running on the same bytes.
* ``create_app`` / ``copy_app`` returned the SDK's **``App`` object** → the old **attributes**
  must keep answering. The types are ``App`` subclasses, so ``isinstance(x, App)`` still holds.

Every fixture below is a **real recorded reply**, never a hand-mocked dict (PROJECT.md
§ Quality bar — "tests must pin real payload shapes").
"""
import io
import json
import pathlib
import urllib.error

import pytest
from lark_oapi.api.bitable.v1 import App

import larkdocio
from larkdocio.common.transport import WriteTransport
from larkdocio.base.schema_client import (
    BASE_ECHO_IS_NOT_STATE,
    CopiedBase,
    CreatedBase,
    NEW_BASE_IS_NOT_EMPTY,
)
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_client import (
    CAPTURE_THE_TOKEN,
    CreatedSpreadsheet,
    SheetsWriteClient,
)
from larkdocio.write.client import DOCX_REPLY_CARRIES_NO_URL, CreatedDocument

from base_schema_fakes import copy_app_echo, create_app_echo, schema_client
from write_harness import FakeClock, StubOpener, _client

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GUIDE_PATH = REPO_ROOT / "src" / "larkdocio" / "GUIDE.md"

#: The docx create as Lark actually answered it on a harness-created disposable
#: (``tests/captures/ld478-move-block-spike/captures/sup-01-create-document.json``, 2026-08-16). Note what
#: it carries and what it does not: ``document_id``, ``revision_id``, ``title`` — **no url**.
_DOCX_CREATE = json.loads(
    (REPO_ROOT / "tests" / "captures" / "ld478-move-block-spike" / "captures"
     / "sup-01-create-document.json").read_text(encoding="utf-8")
)["response"]["json_body"]
_DOCX_DOCUMENT = _DOCX_CREATE["data"]["document"]

#: The sheets v3 create as Lark actually answered it (``tests/captures/sheets-write-spike/captures/
#: 00-smoke.json``). Its reply **does** carry a ``url`` — that one is real and is carried as real.
_SHEETS_CREATE = json.loads(
    (REPO_ROOT / "tests" / "captures" / "sheets-write-spike" / "captures" / "00-smoke.json")
    .read_text(encoding="utf-8")
)["create"]["response"]
_SHEETS_SPREADSHEET = _SHEETS_CREATE["data"]["spreadsheet"]

_FOLDER = "fldrLD583DISPOSABLE"


def _sheets_client(opener):
    clock = FakeClock()
    return SheetsWriteClient(
        "app", "secret", "larksuite.com",
        transport=WriteTransport(max_writes_per_sec=3, time_fn=clock.time,
                                 sleep_fn=clock.sleep),
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )


def _created_document():
    return _client(StubOpener([_DOCX_CREATE])).create_document(
        title=_DOCX_DOCUMENT["title"], folder_token=_FOLDER)


def _created_spreadsheet():
    return _sheets_client(StubOpener([_SHEETS_CREATE])).create_spreadsheet(
        title=_SHEETS_SPREADSHEET["title"], folder_token=_FOLDER)


def _created_base():
    return schema_client(create=[create_app_echo()]).create_app("scratch", _FOLDER)


def _copied_base():
    return schema_client(copy=[copy_app_echo()]).copy_app("appTOKEN", "copy",
                                                          folder_token=_FOLDER)


# --------------------------------------------------------------------------- #
# AC3 — the old answers still answer. A guard PER VERB.                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("make,body", [
    (_created_document, _DOCX_DOCUMENT),
    (_created_spreadsheet, _SHEETS_SPREADSHEET),
])
def test_a_dict_returning_create_still_answers_EVERY_dict_operation_it_answered(make, body):
    """AC3 for the two verbs that returned a plain dict.

    The window promised in the issue's Spec/Plan § 1, operation by operation. This is the
    ruling's load-bearing clause: *no existing consumer breaks now*, which is why the
    dict-compatible shape was chosen over a clean break.
    """
    created = make()

    assert isinstance(created, dict)
    # the whole body, key for key, and equal to the plain dict the old code returned
    assert created == body
    assert dict(created) == body
    assert {**created} == body
    assert sorted(created.keys()) == sorted(body.keys())
    for key, value in body.items():
        assert created[key] == value          # subscript
        assert created.get(key) == value      # .get
        assert key in created                 # membership
    assert created.get("no-such-key") is None
    assert created.get("no-such-key", "fallback") == "fallback"
    assert sorted(iter(created)) == sorted(body)      # iteration
    assert len(created) == len(body)
    assert sorted(created.items()) == sorted(body.items())
    assert json.loads(json.dumps(created)) == body    # json.dumps
    assert (lambda **kw: kw)(**created) == body       # **splat


def test_create_document_returns_a_CreatedDocument_carrying_what_the_reply_holds():
    """AC4 for docx: the id, the title, the revision — and the caller's destination echoed."""
    created = _created_document()

    assert type(created) is CreatedDocument
    assert created.document_id == _DOCX_DOCUMENT["document_id"]
    assert created.title == _DOCX_DOCUMENT["title"]
    assert created.revision_id == _DOCX_DOCUMENT["revision_id"]
    # the destination echo — ``CreatedFolder`` echoes ``parent_token`` "so a ledger row is
    # complete without a second call"; this is the same judgement.
    assert created.folder_token == _FOLDER


def test_the_destination_echo_is_NOT_a_dict_key_so_equality_with_the_old_dict_survives():
    """AC3's sharpest edge. Echoing ``folder_token`` as a *key* would have added a key the
    reply never carried, and ``created == resp["data"]["document"]`` would have gone false —
    a break for any consumer comparing or serialising the create's answer."""
    created = _created_document()

    assert "folder_token" not in created
    assert created == _DOCX_DOCUMENT
    assert json.loads(json.dumps(created)) == _DOCX_DOCUMENT


def test_create_spreadsheet_returns_a_CreatedSpreadsheet_carrying_the_REAL_url():
    """AC4: ``create_spreadsheet``'s reply **does** carry a ``url``
    (``sheets/write_client.py`` docstring; ``GUIDE.md`` § the docx no-url paragraph's own
    scoping note) — so it is carried as real, straight off the reply, never assembled."""
    created = _created_spreadsheet()

    assert type(created) is CreatedSpreadsheet
    assert created.spreadsheet_token == _SHEETS_SPREADSHEET["spreadsheet_token"]
    assert created.title == _SHEETS_SPREADSHEET["title"]
    assert created.url == _SHEETS_SPREADSHEET["url"]
    assert created.folder_token == _SHEETS_SPREADSHEET["folder_token"]
    # not assembled: it is the reply's own bytes, and it is the reply's own key
    assert created.url is created["url"]


@pytest.mark.parametrize("make,echo,typ", [
    (_created_base, create_app_echo, CreatedBase),
    (_copied_base, copy_app_echo, CopiedBase),
])
def test_an_SDK_returning_create_still_answers_EVERY_App_attribute_it_answered(make, echo,
                                                                              typ):
    """AC3 for the two verbs that returned the SDK's ``App`` — **not** a dict.

    The mint corrected its own premise here: "plain dict" is not universally true across this
    class, so for these two the compatibility obligation is about **attribute** access. The
    type is an ``App`` subclass, so ``isinstance(x, App)`` — which is what any defensive
    consumer check would have used — still answers ``True``.
    """
    created = make()
    original = echo().data.app

    assert type(created) is typ
    assert isinstance(created, App)
    for attribute in App._types:
        assert getattr(created, attribute) == getattr(original, attribute), attribute
    # nothing was dropped and nothing invented
    assert vars(created) == vars(original)


def test_the_engines_own_reply_reader_keeps_working_on_the_typed_Base():
    """AC3's one internal cross-module consumer: ``base/schema_apply.py``'s ``_token_of``
    reads ``getattr(reply, "app_token")``. It is not updated by this change and must not need
    to be."""
    from larkdocio.base.schema_apply import _token_of

    assert _token_of(_created_base()) == create_app_echo().data.app.app_token


# --------------------------------------------------------------------------- #
# AC4 — the docx-no-url truth, kept ABSOLUTE.                                  #
# --------------------------------------------------------------------------- #

def test_CreatedDocument_HAS_NO_url_attribute_at_all():
    """AC4's decision, and the issue's permanent Out-of-scope line.

    The docx v1 reply carries no url and this library never assembles one — a constructed link
    is a guess wearing the shape of an answer (the reason ``DriveFilesWriteClient.permalink``
    states for a file). A structurally-always-``None`` ``url`` was rejected because ``None`` is
    already what ``CreatedFolder.url`` means when **Lark answered and omitted it**: one
    spelling for two different facts is exactly the confusion this AC forbids.
    """
    created = _created_document()

    assert not hasattr(created, "url")
    assert "url" not in created


def test_asking_a_CreatedDocument_for_a_url_TEACHES_rather_than_bare_AttributeError():
    """AC4: *a caller must be able to tell "Lark did not answer" from "we did not ask".*

    A bare ``AttributeError: 'CreatedDocument' object has no attribute 'url'`` says neither.
    """
    created = _created_document()

    with pytest.raises(AttributeError) as raised:
        created.url

    message = str(raised.value)
    assert DOCX_REPLY_CARRIES_NO_URL in message
    assert "url" in message


def test_the_no_url_reason_is_RESTATED_ON_THE_VALUE_readable_without_an_exception():
    """The ``CreatedFolder`` pattern, verbatim in shape: a disclosure "restated on the value
    itself, so a caller reading a returned object — not the module — still meets" it."""
    created = _created_document()

    assert created.no_url_reason == DOCX_REPLY_CARRIES_NO_URL
    assert "never assembles" in DOCX_REPLY_CARRIES_NO_URL
    assert "guess wearing the shape of an answer" in DOCX_REPLY_CARRIES_NO_URL


def test_NO_URL_IS_ASSEMBLED_anywhere_in_the_docx_create_answer():
    """The permanent prohibition, asserted structurally rather than promised: no value the
    docx create hands back contains a scheme, and no attribute of the type does either."""
    created = _created_document()

    for value in created.values():
        assert "http" not in str(value)
    assert "http" not in str(created.document_id)


# --------------------------------------------------------------------------- #
# AC4 — the shipped disclosures TRAVEL ONTO THE VALUE.                         #
# --------------------------------------------------------------------------- #

def test_capture_the_token_disclosure_travels_onto_the_spreadsheet_value():
    """AC4: "A returned object that silently drops a shipped disclosure is a regression, not a
    refactor." The orphaned spreadsheet is cost #1 of the three this issue exists for."""
    created = _created_spreadsheet()

    assert created.capture_the_token == CAPTURE_THE_TOKEN
    assert "orphan by construction" in CAPTURE_THE_TOKEN
    # authored ONCE and cited at both doors — the docstring points at the constant rather
    # than re-typing it, so the value and the prose cannot drift apart.
    assert "CAPTURE_THE_TOKEN" in SheetsWriteClient.create_spreadsheet.__doc__
    assert "Capture the token" in SheetsWriteClient.create_spreadsheet.__doc__


def test_the_no_token_raise_is_UNCHANGED_so_the_type_cannot_exist_without_a_token():
    """The issue's binding Dev note: *do not weaken ``create_spreadsheet``'s no-token raise.*"""
    reply = {"code": 0, "msg": "success", "data": {"spreadsheet": {"title": "t"}}}
    with pytest.raises(LarkAPIError):
        _sheets_client(StubOpener([reply])).create_spreadsheet(title="t",
                                                               folder_token=_FOLDER)


def test_the_new_Base_is_not_empty_disclosure_travels_onto_the_CreatedBase():
    """LD-572 put this fact in ``create_app``'s docstring; AC4 puts it where a caller reading
    the *returned object* meets it."""
    created = _created_base()

    assert created.default_table_disclosure == NEW_BASE_IS_NOT_EMPTY
    assert "not empty" in NEW_BASE_IS_NOT_EMPTY.lower()


def test_the_echo_is_not_state_disclosure_travels_onto_the_CopiedBase():
    """``copy_app``'s docstring is explicit that "the copy's **echo** … is not its state" — the
    copy is the one asynchronous Base operation, and ``default_table_id`` comes back empty."""
    copied = _copied_base()

    assert copied.echo_is_not_state == BASE_ECHO_IS_NOT_STATE
    assert "asynchronous" in BASE_ECHO_IS_NOT_STATE.lower()
    assert "default_table_id" in BASE_ECHO_IS_NOT_STATE
    # and the measured fact the disclosure is about is visible on the value itself
    assert not copied.default_table_id


def test_the_created_types_are_EXPORTED_through_the_SAME_DOOR_AS_THEIR_CLIENT():
    """A type a consumer cannot import is a type they cannot check against — and it is
    exported exactly where its own client already is, never one door wider.

    ``WriteClient`` and ``SheetsWriteClient`` are in their packages' ``__all__``, so their
    created types are too. ``BaseSchemaClient`` is **not** in ``larkdocio.base.__all__`` (a
    caller reaches it at ``larkdocio.base.schema_client``), so ``CreatedBase`` / ``CopiedBase``
    are reached the same way rather than promoted past their own client.
    """
    import larkdocio.base as base_pkg
    import larkdocio.sheets as sheets_pkg
    import larkdocio.write as write_pkg

    assert write_pkg.CreatedDocument is CreatedDocument
    assert "CreatedDocument" in write_pkg.__all__
    assert sheets_pkg.CreatedSpreadsheet is CreatedSpreadsheet
    assert "CreatedSpreadsheet" in sheets_pkg.__all__
    # the Base pair rides its client's door, not a wider one
    assert "BaseSchemaClient" not in base_pkg.__all__
    assert "CreatedBase" not in base_pkg.__all__


# --------------------------------------------------------------------------- #
# AC5 — NO NEW CAPABILITY CLAIMS. A richer return type is not a new capability. #
# --------------------------------------------------------------------------- #

#: The four verbs' endpoints and scope requirements, pinned as they stand **before and after**
#: this change. A richer return type is not a new capability: it reaches no new endpoint, needs
#: no new scope, and adds no operation.
#: Derived from ``capabilities(full=True)`` on the branch point (LD-582's landed tip) and
#: re-asserted here after the change: ``{verb: (endpoints, scopes)}``.
_VERB_PERMISSIONS = {
    "create_document": (("/open-apis/docx/v1/documents",), ["docx:document"]),
    "create_spreadsheet": (("/open-apis/sheets/v3/spreadsheets",), []),
    "create_app": (("/open-apis/bitable/v1/apps",), ["bitable:app"]),
    "copy_app": (("/open-apis/bitable/v1/apps/:app_token/copy",), ["bitable:app"]),
}
_VERB_ENDPOINTS = {verb: endpoints
                   for verb, (endpoints, _scopes) in _VERB_PERMISSIONS.items()}


def test_no_capability_row_operation_endpoint_or_scope_moved():
    """AC5's guard, structural rather than textual.

    A *summary* legitimately names the new type (the projection quotes each method's own
    docstring, which is exactly where the type belongs). What must not move is a **capability
    row**: no new operation name, no new endpoint, no new scope, and no new surface.
    """
    surfaces = larkdocio.capabilities(full=True)["surfaces"]
    operations = {op["name"]: op
                  for surface in surfaces.values()
                  for op in surface.get("operations", ())}

    # (a) no operation is named after a type, and no type is a surface
    for name in ("CreatedDocument", "CreatedSpreadsheet", "CreatedBase", "CopiedBase"):
        assert name not in operations
        assert name not in surfaces

    # (b) each verb reaches exactly the endpoints it already reached — no new call site —
    #     and carries exactly the scopes it already carried: none widened, none escalated.
    for verb, (endpoints, scopes) in _VERB_PERMISSIONS.items():
        assert verb in operations, verb
        permission = operations[verb]["permissions"]
        assert tuple(permission["endpoints"]) == endpoints, verb
        assert permission["scopes"] == scopes, verb
        assert permission["optional_scopes"] == [], verb


# --------------------------------------------------------------------------- #
# AC5 — the same-change doc duty, asserted as the PRESENCE of every transformed  #
# hit rather than the absence of grep hits (AC8).                               #
# --------------------------------------------------------------------------- #

def test_the_guides_docx_create_recipe_shows_BOTH_the_subscript_and_the_attribute():
    """The compatibility promise is only useful if the guide states it where the idiom is
    taught. The old ``created["document_id"]`` line stays, beside the new ``.document_id``."""
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    assert 'created["document_id"]' in guide
    assert "created.document_id" in guide
    assert "CreatedDocument" in guide


def test_the_guides_docx_no_url_paragraph_is_TRANSFORMED_and_keeps_its_REASON():
    """`process/doctrine/supersession.md` § A.1 — the reason is preserved and only the
    conclusion moves. What changed is that the create's own answer can now *say* it has no
    url; the reason (a constructed link is a guess) and the paved road both survive."""
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    # the reason, kept
    assert "a guess wearing the shape of an answer" in guide
    assert "DriveFilesWriteClient.permalink" in guide
    # the paved road, kept
    assert "FolderChild.url" in guide
    # the conclusion, moved: the value can now say it
    assert 'hasattr(created, "url")' in guide
    assert "created.no_url_reason" in guide


def test_the_guides_destination_section_names_what_EACH_create_answers_with():
    """The "Where a new object goes" section already enumerates this exact class of verb, so
    it is where the class's answer belongs — one table, all six rows."""
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    section = guide[guide.index("**Which calls this reaches, and which it does not.**"):]
    section = section[:section.index("### The disposables doctrine")]
    for typename in ("CreatedDocument", "CreatedSpreadsheet", "CreatedBase", "CopiedBase",
                     "CreatedFolder", "UploadedFile"):
        assert typename in section, typename
    assert "type(x) is dict" in section          # the one thing that changed, said


def test_the_sheets_disposables_recipe_keeps_its_subscript_and_names_the_type():
    guide = GUIDE_PATH.read_text(encoding="utf-8")

    assert 'spreadsheet_token = spreadsheet["spreadsheet_token"]' in guide
    assert "The answer is a CreatedSpreadsheet" in guide


def test_the_release_notes_state_the_window_AND_that_the_dict_answers_are_PERMANENT():
    """AC6's load-bearing clause. A dated promise nobody can enforce is worse than a stated
    permanence, so the notes say *permanently*, with the reason."""
    notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    section = notes[notes.index("## [1.41.0]"):notes.index("## [1.40.0]")]

    for verb, typename in (("create_document", "CreatedDocument"),
                           ("create_spreadsheet", "CreatedSpreadsheet"),
                           ("create_app", "CreatedBase"),
                           ("copy_app", "CopiedBase")):
        assert verb in section, verb
        assert typename in section, typename
    assert "PERMANENTLY" in section
    assert "no deprecation window and no" in section
    assert "type(x) is dict" in section
    # the three costs, in consumer language (an issue id would fail the dialect guard)
    assert "token dropped" in section
    assert "InvalidURL" in section
    assert "reported what it had created and was wrong" in section


def test_the_packaged_notes_are_the_projection_and_carry_the_same_promise():
    """The packaged twins are regenerated by ``./scripts/sync-packaged-notes.sh`` only — this
    asserts the regeneration ran, rather than trusting that it did.

    **TRANSFORMED (D-111), and only the LOCATOR moved.** The packaged copy carries a WINDOW of
    the newest releases, so the section this promise was published in eventually rolls off it —
    which happened with the 1.49.0 cut. The claim is unchanged and is now read where it is
    COMPLETE (the root document); the wheel-facing arm is kept for as long as it can be true,
    exactly as the eviction notice prescribes. Losing the assertion because the window moved
    would be the guard quietly stopping rather than the promise ceasing to hold."""
    root = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    packaged = (REPO_ROOT / "src" / "larkdocio" / "RELEASE_NOTES.md").read_text(
        encoding="utf-8")

    assert "CreatedSpreadsheet" in root
    assert "PERMANENTLY" in root
    # The wheel-facing half: still there, or evicted with the section — never a THIRD state in
    # which the packaged copy carries one of the two and not the other.
    assert ("CreatedSpreadsheet" in packaged) == ("PERMANENTLY" in packaged)


def test_the_permissions_matrix_names_no_type_and_no_new_endpoint():
    """The generated projection is a **scope** document: a return type has no business in it."""
    matrix = (REPO_ROOT / "PERMISSIONS.md").read_text(encoding="utf-8")

    for name in ("CreatedDocument", "CreatedSpreadsheet", "CreatedBase", "CopiedBase"):
        assert name not in matrix
    for endpoints in _VERB_ENDPOINTS.values():
        for endpoint in endpoints:
            assert endpoint in matrix
