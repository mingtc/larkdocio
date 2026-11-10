"""LD-467 — the ONE R3 verb that opened: create a folder under a parent.

Offline, against fixtures derived from LD-467's **own committed captures**
(``tests/folders_fixtures.py`` carries the per-name provenance; the probes that produced them
are ``dev/ld467-create-folder/probes/``). One region per AC:

* **AC1** the verb ships, returns what the response ACTUALLY carries (``token`` **and** ``url``,
  measured — not assumed), and states what happens when the parent is omitted or empty;
* **AC2** DUPLICATE NAMES MAKE A SECOND FOLDER — measured, and disclosed on the verb, in the
  guide's text and in ``capabilities()``, the same defect class LD-464 shipped silent;
* **AC3** typed refusals in the library's own voice — a missing/invalid parent, a rejected name,
  a denial — never a bare Lark code;
* **AC4** the R3 rung stays shut, and every absence record that said "no folder-creation verb
  exists" is TRANSFORMED with its reason preserved rather than struck;
* **AC5** the permission row is authored in ``larkdocio.permissions`` with its evidence, and the
  operation appears in ``capabilities()`` automatically (LD-459's derived enumeration,
  collapsed by LD-475 into the surface's one ``operations`` key);
* **AC8** the front door moved here, not in a later sweep.

**Conformance-tier**: everything below that pins a product truth this project does not own —
the two-key response, the duplicate-name behaviour, the ``1061002`` / ``99992402`` bodies, the
empty-name and empty-parent acceptances — is marked ``@pytest.mark.conformance`` per
``process/doctrine/conformance-tier.md`` (a lens, not a gate).
"""
import inspect
import pathlib

import pytest

import private_tree  # noqa: E402  (LD-691)

import folders_fixtures as ffx
from larkdocio import capabilities, permissions
from larkdocio.drive import ops
from larkdocio.drive.folders_write import (
    CREATE_FOLDER_ENDPOINT,
    DUPLICATE_NAME_BEHAVIOUR,
    EMPTY_NAME_ACCEPTED_BY_LARK,
    EMPTY_PARENT_LANDS_IN_THE_BOTS_ROOT,
    R3_NOT_SHIPPED,
    CreatedFolder,
    DriveFolderCreateError,
    DriveFoldersWriteClient,
    check_folder_name,
    check_parent_token,
)
from larkdocio.errors import LarkAPIError

FOLDERS_MODULE = pathlib.Path(inspect.getfile(ops)).parent / "folders_write.py"

PARENT = "nodlgExampleee5c77c8ba65b63"


def writer(route, **kwargs):
    """A WRITE-pair folders client whose whole transport is a recording stub."""
    transport = ffx.RecordingTransport(route)
    kwargs.setdefault("token_fetcher", ffx.token_fetcher)
    kwargs.setdefault("rate_limiter", ffx.fast_limiter())
    return DriveFoldersWriteClient("app-id", "app-secret", urlopen=transport, **kwargs), \
        transport


# --------------------------------------------------------------------------- #
# Provenance — the evidence base is real, and these tests move when it does.     #
# --------------------------------------------------------------------------- #

def test_the_fixtures_are_DERIVED_FROM_THIS_ISSUES_OWN_CAPTURES():
    assert ffx.CAPTURES.is_dir()
    assert ffx.response(ffx.CREATE)["code"] == 0
    assert sorted(ffx.created_data()) == ["token", "url"]
    assert ffx.response(ffx.PARENT_OMITTED)["code"] == 99992402


# --------------------------------------------------------------------------- #
# AC1 — the verb, and what the answer ACTUALLY carries.                          #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac1_the_create_sends_name_and_folder_token_to_the_create_folder_endpoint():
    """One POST, one endpoint, the two keys the route takes and nothing invented beside them."""
    client, transport = writer(ffx.create_folder_router(ffx.response(ffx.CREATE)))
    client.create_folder("Q3 reports", PARENT)

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call.method == "POST"
    assert call.path == CREATE_FOLDER_ENDPOINT
    assert call.body == {"name": "Q3 reports", "folder_token": PARENT}


@pytest.mark.conformance
def test_ac1_the_result_carries_the_TOKEN_AND_THE_URL_because_that_is_what_lark_sent():
    """AC1's *measured, not assumed*: the capture's ``data`` has exactly ``token`` and ``url``,
    so the result carries both — and the ``url`` is Lark's own, never assembled here."""
    data = ffx.created_data()
    client, _ = writer(ffx.create_folder_router(ffx.response(ffx.CREATE)))
    created = client.create_folder("Q3 reports", PARENT)

    assert isinstance(created, CreatedFolder)
    assert created.token == data["token"]
    assert created.url == data["url"]
    assert created.name == "Q3 reports"
    assert created.parent_token == PARENT
    # The URL is Lark's answer, not a host + token this library glued together.
    assert created.token in created.url


def test_ac1_a_response_with_no_token_is_a_typed_refusal_not_a_hollow_result():
    """``code:0`` with no token means nothing was created that can be addressed."""
    client, _ = writer(ffx.create_folder_router({"code": 0, "msg": "Success", "data": {}}))
    with pytest.raises(DriveFolderCreateError) as exc:
        client.create_folder("Q3 reports", PARENT)
    assert "no token" in str(exc.value)


def test_ac1_a_missing_url_is_honestly_None_rather_than_constructed():
    """A URL this library invented would be a guess wearing the shape of an answer."""
    body = {"code": 0, "msg": "Success", "data": {"token": "fldrLD467xxxxxxxxxxxxxxxxxx"}}
    client, _ = writer(ffx.create_folder_router(body))
    created = client.create_folder("Q3 reports", PARENT)
    assert created.token == "fldrLD467xxxxxxxxxxxxxxxxxx"
    assert created.url is None


@pytest.mark.conformance
def test_ac1_the_docstring_states_what_ACTUALLY_happens_for_an_omitted_or_empty_parent():
    """The two halves are DIFFERENT answers and the docstring says both, in Lark's own codes:
    an absent key is refused by Lark (``99992402``); ``""`` is ACCEPTED and lands in the bot's
    own root, which is why this library refuses it locally instead of passing it on."""
    doc = inspect.getdoc(DriveFoldersWriteClient.create_folder)
    assert "99992402" in doc
    assert "own root" in doc
    text = FOLDERS_MODULE.read_text("utf-8")
    # LD-700 (T5): the root-listing capture (ld467-21-) is not published, so the module cites
    # the accepted create (ld467-07-) and says the listing's recording is not published.
    assert "ld467-05-" in text and "ld467-07-" in text and "not published" in text
    assert "99992402" in EMPTY_PARENT_LANDS_IN_THE_BOTS_ROOT or "root" in \
        EMPTY_PARENT_LANDS_IN_THE_BOTS_ROOT


# --------------------------------------------------------------------------- #
# AC2 — DUPLICATE NAMES. Measured, then disclosed in all three places.           #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac2_the_capture_pair_shows_a_SECOND_FOLDER_not_an_error_and_not_a_reuse():
    """The measurement itself, asserted against the two captures rather than a docstring."""
    first = ffx.created_data(ffx.CREATE_DUPLICATE_FIRST)
    second = ffx.created_data(ffx.CREATE_DUPLICATE_SECOND)
    assert ffx.response(ffx.CREATE_DUPLICATE_SECOND)["code"] == 0
    assert first["token"] != second["token"]

    listed = [f for f in ffx.listed_files() if f["type"] == "folder"]
    assert len(listed) == 2
    assert len({f["name"] for f in listed}) == 1, (
        "the whole disclosure rests on the two folders carrying the SAME name")


def test_ac2_the_duplicate_behaviour_is_stated_ON_THE_VERB():
    doc = inspect.getdoc(DriveFoldersWriteClient.create_folder)
    assert "duplicate" in doc.lower()
    assert "second folder" in DUPLICATE_NAME_BEHAVIOUR.lower()
    assert "not deduplicated" in DUPLICATE_NAME_BEHAVIOUR.lower() or \
        "no de-duplication" in DUPLICATE_NAME_BEHAVIOUR.lower()


def test_ac2_the_duplicate_behaviour_is_stated_IN_CAPABILITIES():
    note = capabilities(full=True)["surfaces"]["drive-folders-write"]["credentials"]["note"]
    assert "DUPLICATE" in note.upper()
    assert "second folder" in note.lower()


def test_ac2_the_duplicate_behaviour_is_stated_IN_THE_GUIDE():
    """In the guide's own **folder-creation section**, not merely somewhere in 592 KB of it.

    The section is found by its heading and bounded by the next one, which is stricter than a
    character window around the first mention: the first mention is the capability matrix's
    surfaces table, thousands of lines away from where a consumer reads the recipe.
    """
    from larkdocio import guide

    text = guide(full=True)
    assert "create_folder" in text
    start = text.index("### Recipe: create a folder")
    section = text[start:text.index("\n### ", start + 1)]
    assert "duplicate" in section.lower()
    assert "second folder" in section.lower()
    # AC7's other half: the sign on the half-open door, in the same section.
    for shut in ("no move", "no rename", "no copy", "no folder delete"):
        assert shut in section.lower(), f"the guide must still say {shut!r}"


def test_ac2_the_verb_does_NOT_pre_check_for_a_duplicate_it_only_discloses():
    """One call on the wire. A silent name lookup would be the by-name behaviour LD-464 owns —
    and a check-then-create would be a race this library cannot win."""
    client, transport = writer(ffx.create_folder_router(
        ffx.response(ffx.CREATE_DUPLICATE_SECOND)))
    client.create_folder("dup", PARENT)
    assert len(transport.calls) == 1


# --------------------------------------------------------------------------- #
# AC3 — typed refusals, in the library's own voice.                              #
# --------------------------------------------------------------------------- #

def test_ac3_a_missing_parent_is_refused_LOCALLY_before_any_call():
    client, transport = writer(ffx.create_folder_router({"code": 0}))
    for parent in (None, "", "   "):
        with pytest.raises(DriveFolderCreateError) as exc:
            client.create_folder("Q3 reports", parent)
        message = str(exc.value)
        assert "parent folder token" in message
        assert "root" in message, "the message must say where an empty parent would have landed"
    assert transport.calls == [], "nothing may reach Lark for an unaddressed create"


def test_ac3_an_empty_name_is_refused_LOCALLY_with_the_measured_reason():
    """Lark ACCEPTS ``name: ""`` and stores the empty string (captures ``ld467-09-`` / ``24-`` /
    ``25-``), so the refusal is this library's and says so rather than blaming the server."""
    client, transport = writer(ffx.create_folder_router({"code": 0}))
    for name in (None, "", "  \t "):
        with pytest.raises(DriveFolderCreateError) as exc:
            client.create_folder(name, PARENT)
        assert "name" in str(exc.value)
        assert "Lark accepts" in str(exc.value)
    assert transport.calls == []
    assert "empty" in EMPTY_NAME_ACCEPTED_BY_LARK.lower()


@pytest.mark.conformance
def test_ac3_larks_1061002_becomes_the_drive_familys_three_causes_refusal_not_a_bare_code():
    """``1061002`` collapses three distinct causes, so the refusal names them and diagnoses
    none — the ``REFUSAL_SENTENCE`` this family already authored, reused rather than reworded."""
    from larkdocio.drive.errors import REFUSAL_SENTENCE

    client, _ = writer(ffx.create_folder_router(ffx.response(ffx.PARENT_NOT_FOUND)))
    with pytest.raises(DriveFolderCreateError) as exc:
        client.create_folder("Q3 reports", "fldExample000000000001")
    message = str(exc.value)
    assert REFUSAL_SENTENCE in message
    assert "1061002" in message
    assert exc.value.code == 1061002
    assert "Nothing was created" in message


@pytest.mark.conformance
def test_ac3_a_file_token_as_the_parent_gets_the_same_answer_and_the_message_says_so():
    """Measured (``ld467-11-``): this route DOES police the parent's type — unlike
    ``upload_all``, which accepted a mismatched pair with ``code:0``. Same code, so the same
    honest refusal, and the message names *not a folder* as one of the possibilities."""
    client, _ = writer(ffx.create_folder_router(ffx.response(ffx.PARENT_IS_A_FILE)))
    with pytest.raises(DriveFolderCreateError) as exc:
        client.create_folder("Q3 reports", "ExampleFilexxxxxxxxxxxxxxxx")
    assert "not a folder" in str(exc.value)


@pytest.mark.conformance
def test_ac3_an_unmeasured_code_is_surfaced_with_larks_own_body_never_swallowed():
    """A code nobody measured is not decorated with an invented diagnosis; the shared
    ``raise_for_lark_code`` seam types it and carries Lark's ``code``/``msg`` through."""
    client, _ = writer(ffx.create_folder_router(
        {"code": 1061004, "msg": "some unmeasured drive answer"}))
    with pytest.raises(LarkAPIError) as exc:
        client.create_folder("Q3 reports", PARENT)
    assert exc.value.code == 1061004
    assert "some unmeasured drive answer" in str(exc.value)


def test_ac3_the_local_checks_are_reusable_and_return_the_value_they_accept():
    assert check_folder_name(" Q3 reports ") == " Q3 reports "
    assert check_parent_token(PARENT) == PARENT
    with pytest.raises(DriveFolderCreateError):
        check_folder_name("")
    with pytest.raises(DriveFolderCreateError):
        check_parent_token(None)


# --------------------------------------------------------------------------- #
# AC4 — ONE verb. The rest of R3 stays shut, visibly.                            #
# --------------------------------------------------------------------------- #

def test_ac4_the_module_ships_EXACTLY_ONE_public_verb():
    """The discipline, mechanically: a convenience helper, a bulk organiser or a rename added
    'while in the file' reddens here."""
    public = sorted(name for name, value in vars(DriveFoldersWriteClient).items()
                    if not name.startswith("_")
                    and (inspect.isfunction(value) or isinstance(value, (classmethod,
                                                                        staticmethod))))
    assert public == ["create_folder", "from_write_credentials"]


def test_ac4_the_rest_of_the_R3_RUNG_IS_ENUMERATED_AS_DATA_with_a_reason_each():
    """An absence a caller can read, not prose they have to trust. Every row carries WHY."""
    names = [row[0] for row in R3_NOT_SHIPPED]
    for expected in ("move", "rename", "copy", "delete"):
        assert any(expected in name for name in names), f"{expected!r} is not enumerated"
    for _name, reason in R3_NOT_SHIPPED:
        assert len(reason) > 40, "an absence row with no reason is a rationale-free strike"


def test_ac4_no_folder_MOVE_RENAME_COPY_or_DELETE_verb_is_reachable_on_the_drive_package():
    """The falsifier for the shipped 'the rest of R3 is not shipped' sentence: if any of these
    names becomes importable, that sentence is false and this test says so the same day."""
    import larkdocio.drive as drive

    for forbidden in ("move_folder", "rename_folder", "copy_folder", "delete_folder",
                      "organise_by_type", "organize_by_type", "create_shortcut"):
        assert not hasattr(drive, forbidden), f"{forbidden} appeared — R3 was widened"
        assert not hasattr(DriveFoldersWriteClient, forbidden)


def test_ac4_the_absence_records_that_said_no_folder_creation_verb_exists_are_TRANSFORMED():
    """D-24: preserve the reason, supersede only the conclusion. The upload module's fence —
    *the destination is always the caller's* — is unchanged and still says so; what it no
    longer says is that this library ships no folder-creating call anywhere."""
    upload = (pathlib.Path(inspect.getfile(ops)).parent / "files_write.py").read_text("utf-8")
    assert "no folder-creating call anywhere in this module" in upload, (
        "the module-scoped claim is TRUE and must survive")
    assert "LD-467" in upload, "the transformation must name the ruling that caused it"
    assert "folders_write" in upload, (
        "the reader of the upload module must be pointed at where the verb now lives")


# --------------------------------------------------------------------------- #
# AC5 — the op registry, the permission row, and the AUTOMATIC projection.       #
# --------------------------------------------------------------------------- #

def test_ac5_the_op_is_registered_with_mutates_DECLARED_true():
    descriptor = ops.op("create_folder")
    assert descriptor.endpoint == CREATE_FOLDER_ENDPOINT
    assert descriptor.http_method == "POST"
    assert descriptor.mutates is True
    assert descriptor.paged is False
    assert "ld467" in descriptor.evidence
    # The enumeration's own read-only claim is untouched — it was never a claim about this op.
    assert ops.read_only(ops.ENUMERATION_OPS) is True
    assert ops.read_only() is False


def test_ac5_the_endpoint_has_a_permission_row_with_its_evidence_and_no_guessed_scope():
    scopes = permissions.scopes_for_endpoints((CREATE_FOLDER_ENDPOINT,), "write")
    assert scopes == (), "no scope string was ever observed demanded — none may be invented"
    unknowns = permissions.unknown_requirements_for((CREATE_FOLDER_ENDPOINT,), "write")
    assert unknowns, "an endpoint with no scope must carry its reason"
    reason = " ".join(unknowns)
    assert "ld467-create-folder" in reason, "the reason must cite its own captures"
    assert "unknown" in reason.lower() or "not guessed" in reason.lower()


def test_ac5_the_new_call_site_is_neither_undeclared_nor_uncovered():
    """The two ways a new API-using call site hides: an endpoint nobody wrote a row for, and
    an operation no permission row covers. Neither may be this one.

    ``undeclared_endpoints()`` carries a **pre-existing** baseline — three call sites that
    reach the token-fetch route — so this asserts the create is not among them rather than
    asserting the list is empty, which it never was.
    """
    undeclared = permissions.undeclared_endpoints()
    assert [site for site, endpoint in undeclared
            if endpoint == CREATE_FOLDER_ENDPOINT] == []
    assert sorted({endpoint for _site, endpoint in undeclared}) == [
        "/open-apis/auth/v3/tenant_access_token/internal"], (
        "the baseline moved — a new endpoint went undeclared")
    gaps = permissions.coverage_gaps()
    assert gaps.uncovered == () or gaps.uncovered == []


def test_ac5_the_operation_appears_in_capabilities_AUTOMATICALLY_under_the_ONE_KEY():
    """LD-459's claim, unchanged: a new operation reaches the enumeration a consumer reads
    without a second hand-kept list. LD-475 collapsed that enumeration — the index pointing at
    three sibling keys became the one ``operations`` key with a ``kind`` on every row — so the
    row is asserted where a consumer now reads it. Still PER-SURFACE, not top-level."""
    surface = capabilities(full=True)["surfaces"]["drive-folders-write"]
    assert [(row["name"], row["kind"]) for row in surface["operations"]] == [
        ("create_folder", "operation")]
    unprojected, phantom = permissions.projection_gaps()
    assert unprojected == [] and phantom == []
    row = permissions.permission_registry()[("drive-folders-write", "create_folder")]
    assert row.endpoints == (CREATE_FOLDER_ENDPOINT,)
    assert row.mode == "write"
    assert row.scopes == ()


def test_ac5_the_surface_is_a_WRITE_surface_on_the_WRITE_pair_with_no_fallback():
    surface = capabilities(full=True)["surfaces"]["drive-folders-write"]
    assert surface["mode"] == "write"
    assert surface["credentials"]["env_primary"] == ["LARK_WRITE_APP_ID",
                                                     "LARK_WRITE_APP_SECRET"]
    assert surface["credentials"]["env_fallback"] == [], "least-privilege: no read fallback"
    source = FOLDERS_MODULE.read_text("utf-8")
    assert "get_read_credentials" not in source
    assert "LARK_READ" not in source


def test_ac5_nothing_here_widens_requests_or_escalates_a_scope():
    source = FOLDERS_MODULE.read_text("utf-8")
    for forbidden in ("scopes=", "scope=", "add_scope", "request_scope", "grant"):
        assert forbidden not in source.replace("scope requirement", ""), forbidden


# --------------------------------------------------------------------------- #
# AC8 — the front door moved HERE.                                              #
# --------------------------------------------------------------------------- #

def test_ac8_the_wheel_summary_names_the_new_surface():
    import front_door as fd

    assert fd.description_surface_gaps(fd.pyproject()["project"]["description"]) == []


@private_tree.internal_log
def test_ac8_the_changelog_and_release_notes_carry_the_entry_under_the_open_section():
    """Both notes documents, under the ``[1.34.0]`` section this change opened.

    The issue id is asserted of the **CHANGELOG only**, and that is a rule rather than a
    slip: ``RELEASE_NOTES.md`` is consumer-reaching text in the dialect corpus
    (``tests/consumer_text.py``), which forbids an issue id in it, while the CHANGELOG is by
    design the internal engineering log that carries them.

    **TRANSFORMED (LD-621, ruled by D-111), and only the LOCATOR moved.** This read the copies
    that SHIP and split above ``[1.33.0]`` so that the window rolling past it could not redden
    the guard — which stopped the false failure but left the assertion resting on whichever text
    the window happens to carry: ``[1.34.0]`` is already outside it, so the claim was passing on
    a recurrence of the word rather than on its own entry. The invariant now reads the CANONICAL
    ROOT documents, which are complete and stay complete, and the wheel-facing arm is kept for
    as long as it can be true — asserted only while the window still carries the publishing
    section, and then byte-for-byte against the root's own.
    """
    root = pathlib.Path(inspect.getfile(ops)).parents[3]
    section_header = "## [1.34.0]"
    for name in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        text = (root / name).read_text("utf-8")
        # Everything ABOVE [1.33.0] — the entry landed in [1.34.0], so an entry found here is
        # an entry in a section at or newer than that one.
        head = text.split("## [1.33.0]", 1)[0]
        assert "create_folder" in head, f"{name} has no folder-creation entry"
        if name == "CHANGELOG.md":
            assert "LD-467" in head, "the engineering log must name the issue"
        else:
            assert "LD-467" not in head, (
                "a consumer document may not carry an issue id — the dialect guard forbids it")

        packaged = (root / "src" / "larkdocio" / name).read_text("utf-8")
        if section_header in packaged:
            authored = text.split(section_header, 1)[1].split("\n## [", 1)[0]
            shipped = packaged.split(section_header, 1)[1].split("\n## [", 1)[0]
            assert shipped == authored, (
                f"the packaged {name} still carries the publishing section but not verbatim — "
                "the projection must never reflow or edit a byte")
