"""THE ONE LOOKUP for Lark's error codes — the characterization, the registry, the guards.

**Read § A first, and read it as history.** Section A is the CHARACTERIZATION: every verdict
every affected classifier gave **before** LD-531 moved a single line, frozen as literals rather
than re-derived from the code under test. It was written and run green on the unmoved tree
(``17773 passed, 3 skipped``) and every later section of this file, and
every move LD-531 made, had to keep it green. A characterization test that re-derives its
expectation from the thing it is characterizing proves nothing, so nothing in § A imports a
table and asserts against it — the numbers and the strings are typed out.

The consolidation LD-531 landed, in one sentence: **a code's MEANING and EVIDENCE are authored
once, at package level, in :mod:`larkdocio.common.error_codes`; each surface's CLASSIFICATION
stays exactly where its own ruling put it.** Those are different things and merging them would
have been the defect, not the fix — base's entry-scoped/systemic split (D4′) is load-bearing
batch-halt behavior, sheets' ``_GONE_CODES`` is a teardown-forgiveness set, and the
permissions registry's denial set drives a typed exception class. Three surfaces, three
classifications, **one** authored row per code.

Sections:

* **§ A** — the characterization: 63 frozen verdicts, taken before the moves.
* **§ B** — the registry's own contract: the row shape, meaning-is-not-label, evidence resolves.
* **§ C** — bidirectional completeness, the ``tests/test_permissions_registry.py`` pattern: a
  branch-table code with no row reddens, and a row nothing reaches reddens.
* **§ D** — the per-surface classifications are NOT merged.
* **§ E** — the three measured holes and the object-ACL denial class.
* **§ F** — the reader's typed routing, and the two reach changes it makes on purpose.
"""
import pytest

import private_tree  # (LD-685)

from larkdocio.errors import LarkAPIError, api_error


# =========================================================================== #
# § A — THE CHARACTERIZATION. Frozen verdicts, taken BEFORE any move.          #
# =========================================================================== #

#: ``base.disposition.classify_apply_exception(LarkAPIError(code=c, msg="m"), wrote=False)``
#: → ``(scope, reason.value, outcome, landed)``, for every code in EITHER ruled table, plus
#: three codes in NEITHER (the fall-through default this issue must not disturb) and the two
#: holes LD-531 adds rows for.
#:
#: The two PROTECTED-LAST codes (1254034, 1254023) are in ``ENTRY_SCOPED_CODES`` and reach
#: their verdict through the classifier's **fall-through**, not through a membership test —
#: the LD-307 finding, and the exact reason a "re-home the tables" change is dangerous.
DISPOSITION_BEFORE = {
    1002:     ("systemic",     "api-error", "refused", "no"),
    1254004:  ("systemic",     "api-error", "refused", "no"),
    1254041:  ("systemic",     "api-error", "refused", "no"),
    1254023:  ("entry-scoped", "api-error", "refused", "no"),
    1254034:  ("entry-scoped", "api-error", "refused", "no"),
    1254043:  ("entry-scoped", "api-error", "refused", "no"),
    1254060:  ("entry-scoped", "api-error", "refused", "no"),
    1254069:  ("entry-scoped", "api-error", "refused", "no"),
    1255002:  ("entry-scoped", "api-error", "refused", "no"),
    99992402: ("entry-scoped", "api-error", "refused", "no"),
    # ---- in NEITHER table: the fall-through ---- #
    424242:   ("entry-scoped", "api-error", "refused", "no"),
    1254701:  ("entry-scoped", "api-error", "refused", "no"),
    1254702:  ("entry-scoped", "api-error", "refused", "no"),
    1770040:  ("entry-scoped", "api-error", "refused", "no"),
    99991672: ("entry-scoped", "api-error", "refused", "no"),
}

#: ``halts`` / ``continues`` are derived from ``scope``, and a batch reads THEM rather than the
#: string, so they are pinned separately: a refactor that renamed the scope constant while
#: keeping the string would pass the row above and still break the batch.
DISPOSITION_HALTS_BEFORE = {1002, 1254004, 1254041}


@pytest.mark.parametrize("code", sorted(DISPOSITION_BEFORE))
def test_A1_the_base_apply_classifier_verdict_is_unchanged(code):
    from larkdocio.base import disposition

    disp = disposition.classify_apply_exception(
        LarkAPIError("x", code=code, msg="m"), wrote=False)
    reason = getattr(disp.reason, "value", disp.reason)
    assert (disp.scope, reason, disp.outcome, disp.landed) == DISPOSITION_BEFORE[code], code
    assert disp.halts is (code in DISPOSITION_HALTS_BEFORE), code
    assert disp.continues is (code not in DISPOSITION_HALTS_BEFORE), code


#: ``base.disposition.platform_anomaly``'s clause (4): a code EITHER ruled table knows can
#: never be reported as a platform anomaly. Pinned as the membership question the clause asks,
#: because that is the one thing a re-home could silently invert.
def test_A2_a_ruled_code_is_never_a_platform_anomaly():
    from larkdocio.base import disposition

    for code in (1002, 1254004, 1254041, 1254023, 1254034, 1254043, 1254060, 1254069,
                 1255002, 99992402):
        assert (code in disposition.SYSTEMIC_CODES
                or code in disposition.ENTRY_SCOPED_CODES), code
    for code in (424242, 1254701, 1254702, 1770040, 99991672):
        assert code not in disposition.SYSTEMIC_CODES, code
        assert code not in disposition.ENTRY_SCOPED_CODES, code


#: ``permissions.looks_like_scope_denial(code, msg)`` — the code arm AND the message-marker arm,
#: including all three measured holes (each ``False``: the LD-501 finding, and it is CORRECT —
#: no scope is missing on an object-ACL denial).
SCOPE_DENIAL_BEFORE = [
    ((99991672, "x"), True),
    ((41050, "x"), True),
    ((1069303, "x"), True),
    ((1770040, "no folder permission"), False),
    ((1254701, "DriveNodePermNotAllow"), False),
    ((1254702, "DriveNodeNotExist"), False),
    ((1061004, "x"), False),
    ((99991400, "x"), False),
    ((424242, "x"), False),
    ((424242, "scopes is required"), True),
    ((424242, "scope is required"), True),
    ((424242, "access denied"), True),
    ((424242, "permission denied"), True),
    ((424242, "no permission"), True),
]


@pytest.mark.parametrize("pair,expected", SCOPE_DENIAL_BEFORE)
def test_A3_the_scope_denial_classifier_verdict_is_unchanged(pair, expected):
    from larkdocio import permissions

    assert permissions.looks_like_scope_denial(*pair) is expected, pair


#: ``sheets.write_client.spreadsheet_is_gone`` — both codes, both representations, the
#: non-gone code, and the code-LESS error (where gone-ness is unknown and must not be assumed).
GONE_BEFORE = [(1310249, True), (1061007, True), ("1310249", True), ("1061007", True),
               (424242, False), (None, False)]


@pytest.mark.parametrize("code,expected", GONE_BEFORE)
def test_A4_the_sheets_gone_classifier_verdict_is_unchanged(code, expected):
    from larkdocio.sheets import write_client

    assert write_client.spreadsheet_is_gone(LarkAPIError("x", code=code)) is expected, code


#: ``errors.api_error`` — which TYPE a code becomes, and whether a denial travels with it.
API_ERROR_TYPE_BEFORE = [
    ((99991400, "x"), "LarkRateLimitError", False),
    ((99991672, "scopes is required: [docx:document]"), "LarkPermissionError", True),
    ((1770040, "no folder permission"), "LarkAPIError", False),
    ((1061004, "not found"), "LarkAPIError", False),
    ((424242, "x"), "LarkAPIError", False),
]


@pytest.mark.parametrize("pair,type_name,has_denial", API_ERROR_TYPE_BEFORE)
def test_A5_the_api_error_type_mapping_is_unchanged(pair, type_name, has_denial):
    from larkdocio.errors import api_error

    err = api_error("verbatim message", code=pair[0], msg=pair[1])
    assert type(err).__name__ == type_name, pair
    assert (getattr(err, "denial", None) is not None) is has_denial, pair
    assert str(err) == "verbatim message", "the message is the caller's, verbatim"


#: ``base.errors.note_for`` is BASE-SCOPED and must stay so: a package-level registry that this
#: accessor started answering from would hand a Base caller a sheets row.
NOTE_FOR_BEFORE = [(1002, "note has been deleted"), (1254041, "TableIdNotFound"),
                   (424242, None), (99991672, None), (1770040, None), (1310249, None)]


@pytest.mark.parametrize("code,label", NOTE_FOR_BEFORE)
def test_A6_the_base_taxonomy_lookup_stays_base_scoped(code, label):
    from larkdocio.base import errors as base_errors

    note = base_errors.note_for(code)
    assert (None if note is None else note.label) == label, code


def test_A7_the_base_taxonomy_holds_exactly_the_codes_it_held():
    """25 rows, and the exact key set. Typed out, not derived."""
    from larkdocio.base import errors as base_errors

    assert sorted(base_errors.BASE_ERROR_CODES) == [
        1002, 91402, 1061003, 1069307, 1254001, 1254004, 1254016, 1254018, 1254023, 1254034,
        1254036, 1254041, 1254043, 1254044, 1254045, 1254050, 1254060, 1254069, 1254301,
        1254302, 1255002, 1770001, 1770029, 99992402, 800074800,
    ]
    assert len(base_errors.BASE_ERROR_CODES) == 25
    assert base_errors.FEATURE_GATE_CODES == (1254301, 1254302)
    assert len(base_errors.WRITE_ERROR_CODES) == 13


def test_A8_the_denial_registry_rows_keep_their_measured_verification_labels():
    """``denial-verified`` vs ``documented-unverified`` is a MEASURED distinction, not a label."""
    from larkdocio import permissions

    assert sorted(permissions.DENIAL_CODES) == [41050, 1069303, 99991672]
    assert permissions.DENIAL_CODES[99991672]["verification"] == "denial-verified"
    assert permissions.DENIAL_CODES[41050]["verification"] == "documented-unverified"
    assert permissions.DENIAL_CODES[1069303]["verification"] == "documented-unverified"
    for code, row in permissions.DENIAL_CODES.items():
        assert row["evidence"].strip(), code
        assert set(row) == {"verification", "evidence"}, code


#: ``comments.read._describe`` — the SIXTH code table, which the issue's own enumeration did not
#: name and which LD-531 deliberately left where it is (it selects WORDING, not control flow).
#: Characterized anyway, because "left alone" is a claim that wants a test.
DESCRIBE_BEFORE = {
    9499: "one of the comment ids was rejected as malformed, which fails the whole batch — "
          "no comment in the batch was returned (code 9499)",
    41050: "the identity lookup was denied on this application's scopes — comment authors are "
           "therefore reported as raw ids (code 41050)",
    1069301: "the comment could not be resolved as requested — most often because it no longer "
             "exists (code 1069301)",
    1069302: "the reply content was empty (code 1069302)",
    1069304: "comments are not available for this file — it may have been deleted "
             "(code 1069304)",
    1069307: "the comment or file does not exist for this request — check the token and that "
             "the file type matches it (code 1069307)",
    99992402: "the file type sent with the request is not one this endpoint accepts for that "
              "operation (code 99992402)",
    424242: "the request failed with code 424242: srvmsg",
}


@pytest.mark.parametrize("code", sorted(DESCRIBE_BEFORE))
def test_A9_the_comments_wording_lookup_is_unchanged(code):
    from larkdocio.comments import read as comments_read

    assert comments_read._describe(code, "srvmsg") == DESCRIBE_BEFORE[code], code


# --------------------------------------------------------------------------- #
# § A.10 — the READER's operator-facing text, byte for byte.                   #
#                                                                             #
# The three branches of ``read.download._report_error`` and the exact lines    #
# each logs, plus the exact ``ClickException`` text each raises. AC4 makes the #
# ROUTING typed; every byte below must survive it.                            #
# --------------------------------------------------------------------------- #

IP_BLOCK_LINES = [
    "LARK API ERROR: IP Address Blocked",
    "Your current IP address is not authorized to use this Lark Application.",
    "Action Required: Please check with your Lark App Administrator to add your current IP "
    "address to the App's IP Allowlist in the Lark Developer Console.",
]
IP_BLOCK_REFUSAL = "Download failed: IP address blocked — see the guidance above."

PERMISSION_LINES = [
    "LARK API ERROR: Missing Document Permissions",
    "The Lark App does not have permission to read this document, or it does not exist.",
    "Action Required: Open the Lark Document in your browser, click 'Share' -> 'Add "
    "Application' (or 'App Application' / 'Add Integration'), and search for your Lark App "
    "to give it read access.",
]
PERMISSION_REFUSAL = "Download failed: missing document permissions — see the guidance above."

BUG_BANNER_TAIL = "Report the following if it is a bug"


def _routed(monkeypatch, exc):
    """``(logged_lines, raised)`` for one trip through ``_report_error``."""
    import click

    from larkdocio.read import download

    lines = []
    monkeypatch.setattr(download.logger, "error", lambda msg, *a: lines.append(str(msg)))
    try:
        download._report_error(exc)
    except click.ClickException as refusal:
        return lines, ("ClickException", str(refusal))
    except BaseException as other:            # noqa: BLE001 — the default arm re-raises
        return lines, (type(other).__name__, str(other))
    return lines, None


def test_A10_the_ip_block_branch_text_is_pinned(monkeypatch):
    """**LD-658 ruling (after AC1): ``str(e)`` is logged first on THIS arm too.**

    The reason is stronger here than on the typed arm, and it is a consequence of AC1's reorder
    rather than an argument that was available before it. Since the reorder this branch fires
    only on what ``_document_access_refusal`` DECLINED — so it is, by construction, the arm where
    this library's own confidence is lowest: a bare ``"ip" and "denied"`` heuristic over somebody
    else's message text. Lark's own body is worth most exactly where our classification is worth
    least.

    **Additive, and the pinned sequence is undisturbed:** the new line goes ABOVE the banner, so
    all three ``IP_BLOCK_LINES`` keep their bytes AND their order, and § F1 still folds them out
    of the source unchanged.
    """
    message = "Failed: Code: 1, Msg: ip address denied"
    exc = LarkAPIError(message, code=1)
    assert getattr(exc, "denial", None) is None, (
        "this fixture must reach the IP arm, which only sees what the typed arm declined")
    lines, raised = _routed(monkeypatch, exc)
    assert lines == [message] + IP_BLOCK_LINES
    assert lines[1:] == IP_BLOCK_LINES, "the pinned banner moved rather than being prepended to"
    assert raised == ("ClickException", IP_BLOCK_REFUSAL)


def _obtain_token_failure():
    """``lark_oapi``'s own token-handshake failure — the shape a wrong App Secret really has."""
    from lark_oapi.core.exception import ObtainAccessTokenException

    return ObtainAccessTokenException(
        "obtain tenant access token failed", 10003, "app not exist or app secret error")


def _router_branch_count():
    """How many TOP-LEVEL branches ``_report_error`` has — **derived from its own source**.

    ``ast``, not a grep: the count is every ``if`` at the top level of the function body, plus
    one for the fall-through tail. A nested ``if`` (the scope-vs-share split inside the
    document-access arm) is a SUB-case of its arm, not an arm, which is why only the top level
    is counted and why the enumeration below groups sub-cases under one key.
    """
    import ast
    import inspect
    import textwrap

    from larkdocio.read import download

    tree = ast.parse(textwrap.dedent(inspect.getsource(download._report_error)))
    body = tree.body[0].body
    return sum(1 for node in body if isinstance(node, ast.If)) + 1


#: One key per top-level arm of ``_report_error``, each mapping to the exceptions that reach it
#: and whether that arm is expected to ECHO Lark's own answer or to stay silent. The exceptions
#: cannot be derived (nothing synthesizes an exception from an AST), but the **arm count** is —
#: see the assertion in the test below — so a new branch reddens and has to be classified here.
_ROUTER_ARMS = {
    # Path 0: the two builtin refusal classes the CLI seam converts. It logs NOTHING on purpose
    # — `check_err`'s bug banner would print before the seam ever saw the exception, which is
    # the measured LD-658 AC4 defect — and re-raises for the seam to word.
    "passthrough": ("silent", [
        ValueError("not a recognised Lark URL: 'nope'"),
        OSError(36, "File name too long", "/out/x.md"),
    ]),
    "document-access": ("echoes", [
        # the scope sub-case...
        api_error(
            "Failed: Code: 99991672, Msg: Access denied. One of the following scopes is "
            "required: [docx:document:readonly]",
            code=99991672,
            msg="Access denied. One of the following scopes is required: "
                "[docx:document:readonly]",
            credential_env=("LARK_READ_APP_ID", "LARK_READ_APP_SECRET")),
        # ...and the denial-less share sub-case.
        LarkAPIError("Failed: Code: 1061004, Msg: not found", code="1061004", msg="not found"),
    ]),
    "ip-block": ("echoes", [
        LarkAPIError("Failed: Code: 1, Msg: ip address denied", code=1),
    ]),
    "token-mint": ("echoes", [
        _obtain_token_failure(),
    ]),
    "default": ("echoes", [
        LarkAPIError("Failed: Code: 424242, Msg: who knows", code=424242),
    ]),
}


def test_A10_the_router_arm_ENUMERATION_is_complete_against_the_ROUTER_ITSELF():
    """**LD-658 fix round, defect 3.** The property below used to claim it covered *"all four
    arms"* and that *"a future fifth arm that forgets is caught by this test"*. Both were false:
    the router has **five** top-level branches, and the enumeration was a hand-written literal of
    four tuples coupled to nothing — so a new arm was not caught, and the sentence promising it
    was exactly the kind of false in-code claim this issue is fixing.

    The **count** is now derived from ``_report_error``'s own AST, so the promise is kept by
    mechanism: add a branch and this reddens until it is classified above.
    """
    derived = _router_branch_count()
    assert len(_ROUTER_ARMS) == derived, (
        f"_report_error has {derived} top-level arms and {len(_ROUTER_ARMS)} are enumerated. "
        f"Classify the new one in _ROUTER_ARMS — 'echoes' if it logs Lark's own answer first, "
        f"'silent' if it deliberately logs nothing (and say why, as `passthrough` does).")
    assert all(mode in ("echoes", "silent") for mode, _ in _ROUTER_ARMS.values())
    assert any(mode == "echoes" for mode, _ in _ROUTER_ARMS.values()), (
        "a population with no echoing arm would make the property below vacuous")


def test_A10_EVERY_arm_of_the_reader_router_logs_LARKS_OWN_ANSWER_FIRST(monkeypatch):
    """The invariant the LD-658 fixes add up to, over **every** arm of the router.

    Before LD-658 only the default arm echoed ``str(e)``; the two that offered advice swallowed
    it, which is how an operator came to see a remedy and never the refusal it was a remedy for.
    Asserted as one property rather than per-arm assertions, and the arm set is held complete
    against the router's own source by the test above — so this is a claim about **all** of them,
    which is what its predecessor said and could not back.

    The one arm that must NOT echo is declared as such rather than omitted: path 0 re-raises a
    ``ValueError``/``OSError`` for the CLI seam to word, and logging there would put
    ``check_err``'s bug banner in front of a refusal.
    """
    for arm, (mode, exceptions) in sorted(_ROUTER_ARMS.items()):
        assert exceptions, f"{arm} enumerates no exception, so it proves nothing"
        for exc in exceptions:
            lines, _raised = _routed(monkeypatch, exc)
            if mode == "silent":
                assert lines == [], (
                    f"the {arm} arm logged {lines!r} — it must stay silent so the seam's "
                    f"wording is not preceded by a bug banner")
            else:
                assert lines and lines[0] == str(exc), (
                    f"the {arm} arm does not lead with Lark's own answer: {lines[:1]}")


@pytest.mark.parametrize("code,msg", [
    ("99991672", "not read permission"),
    ("1061004", "not found"),
    ("1061004", "not read permission"),
])
def test_A10_the_permission_branch_text_is_pinned(monkeypatch, code, msg):
    """The three CODED shapes the reader really raises (``tests/test_client.py`` pins them).

    **LD-658 AC1b prepends one line and reworded nothing.** These three carry **no**
    ``PermissionDenial`` (Lark named no scope, so there is none to build), which is why they keep
    the share-the-document banner byte for byte — that case really is a sharing problem. What is
    new is that ``str(e)`` is logged **first**: Lark's own answer used to be dropped on the floor
    by this arm, so an operator saw advice and never saw what Lark said.
    """
    message = f"Failed to get docx document doc9: Code: {code}, Msg: {msg}"
    exc = LarkAPIError(message, code=code, msg=msg)
    assert getattr(exc, "denial", None) is None, (
        "this shape is in this test BECAUSE it carries no denial; if Lark's msg now names a "
        "scope it belongs in the denial-carrying test below")
    lines, raised = _routed(monkeypatch, exc)
    assert lines == [message] + PERMISSION_LINES
    assert raised == ("ClickException", PERMISSION_REFUSAL)


SCOPE_DENIAL_BANNER = "LARK API ERROR: Missing App Permission (a Lark SCOPE, not a share)"
SCOPE_DENIAL_RELEASE_LINE = (
    "Action Required: grant the permission(s) above on the app in the Lark console "
    "\u2014 and then RELEASE a new version of the app. A grant takes effect on RELEASE, not on "
    "save: an unreleased grant leaves this call failing exactly as it does now."
)
SCOPE_DENIAL_REFUSAL = "Download failed: missing app permission — see the guidance above."


def test_A10_a_SCOPE_denial_prints_the_denial_the_library_ALREADY_HOLDS(monkeypatch):
    """**LD-658 AC1b.** AC1 fixed which branch fires; this is what it prints.

    A genuine scope denial arrives at this function carrying a ``PermissionDenial`` that already
    names the exact missing scope, the credential pair the call was made on, and Lark's own
    console link (``read/client.py::_ensure_success`` passes ``body=`` and
    ``credential_env=resolved_read_env()``). The arm printed **none of it** and offered the
    **Share dialog** — the wrong console for a scope. Nothing here is derived: ``detail()`` is
    the string the record already produces for every other surface.
    """
    exc = api_error(
        "Failed to get docx blocks: Code: 99991672, Msg: Access denied. One of the following "
        "scopes is required: [docx:document:readonly]",
        code=99991672,
        msg="Access denied. One of the following scopes is required: [docx:document:readonly]",
        credential_env=("LARK_READ_APP_ID", "LARK_READ_APP_SECRET"))
    assert exc.denial is not None, "the fixture must be a real denial or this test is vacuous"

    lines, raised = _routed(monkeypatch, exc)

    # (c) Lark's own answer, first — it used to be dropped entirely.
    assert lines[0] == str(exc)
    # a scope is not a share: the banner says which console this is about.
    assert lines[1] == SCOPE_DENIAL_BANNER
    # (a) the record's own detail, printed rather than re-derived.
    assert lines[2] == exc.denial.detail()
    assert "docx:document:readonly" in lines[2]
    assert "LARK_READ_APP_ID" in lines[2]
    # (b) release, not save.
    assert lines[3] == SCOPE_DENIAL_RELEASE_LINE
    assert len(lines) == 4
    # (d) the share-the-document banner is NOT what a scope denial gets.
    assert not any(line in PERMISSION_LINES for line in lines)
    assert raised == ("ClickException", SCOPE_DENIAL_REFUSAL)


def test_A10_the_scope_arm_never_swallows_a_denial_the_download_path_can_raise(monkeypatch):
    """The claim ``LARK_SETUP.md`` § 2 makes — *"each refusal you meet is typed and names what
    was missing"* — held against the CLI download path, for **every** denial code the classifier
    recognises, so the guard is not one hand-picked shape.
    """
    from larkdocio.permissions import SCOPE_DENIAL_CODES

    assert SCOPE_DENIAL_CODES, "an empty population would make this guard vacuous"
    for code in SCOPE_DENIAL_CODES:
        msg = ("Access denied. One of the following scopes is required: "
               "[docx:document:readonly]")
        exc = api_error(f"Failed: Code: {code}, Msg: {msg}", code=code, msg=msg,
                        credential_env=("LARK_READ_APP_ID", "LARK_READ_APP_SECRET"))
        assert exc.denial is not None, code
        lines, raised = _routed(monkeypatch, exc)
        assert "docx:document:readonly" in " ".join(lines), (
            f"code {code}: the missing scope is not named anywhere in what the operator sees")
        assert raised == ("ClickException", SCOPE_DENIAL_REFUSAL), code


@pytest.mark.parametrize("exc_factory,label", [
    (lambda: LarkAPIError(
        "Failed to get docx document Zipax7Qm2bd9: Code: 99991672, Msg: Permission denied",
        code="99991672", msg="Permission denied"),
     "coded 99991672, token contains 'ip'"),
    (lambda: LarkAPIError(
        "Failed to get docx document ZIPax7Qm2bd9: Code: 1061004, Msg: Permission denied",
        code="1061004", msg="Permission denied"),
     "coded 1061004, token contains 'IP' in another case"),
    (lambda: api_error(
        "Failed to get docx blocks WhipXQ: Code: 41050, Msg: Access denied. One of the "
        "following scopes is required: [docx:document:readonly]",
        code=41050,
        msg="Access denied. One of the following scopes is required: "
            "[docx:document:readonly]"),
     "typed LarkPermissionError, token contains 'ip'"),
])
def test_A10_a_TYPED_permission_refusal_is_never_misrouted_to_the_IP_BANNER(
        monkeypatch, exc_factory, label):
    """**LD-658 AC1.** The IP branch is a bare ``"ip" and "denied"`` substring test, and a Lark
    document token is 22-24 base62 characters — so ~2.15% of tokens contain a case-insensitive
    ``ip`` (measured over 200,000 synthetic tokens; ~doubled for a wiki url, whose refusal text
    carries two tokens). Lark's denial ``msg`` supplies the ``denied``. Every case below is
    classified CORRECTLY by ``_document_access_refusal`` and was then handed the wrong remedy:
    go and edit an IP allowlist, when the fix is Share -> Add Application.

    The fix is ordering, not new classification: the typed arm runs first, and the substring arm
    is what is left over. Nothing here asserts new text — ``PERMISSION_LINES`` is the same
    banner these cases always deserved.
    """
    lines, raised = _routed(monkeypatch, exc_factory())
    assert not any(line in IP_BLOCK_LINES for line in lines), (
        f"misrouted to the IP-allowlist banner ({label}) — the user is sent to fix an IP "
        f"allowlist when the fix is in the document's own Share dialog or the app's scopes")
    assert raised[0] == "ClickException"
    # WHICH of the document-access arms fires is AC1b's question, not AC1's; both are correct
    # answers here and neither is the IP one.
    assert raised[1] in (PERMISSION_REFUSAL, SCOPE_DENIAL_REFUSAL), raised


def test_A10_the_default_branch_reraises_with_the_bug_banner(monkeypatch):
    lines, raised = _routed(monkeypatch, LarkAPIError("Failed: Code: 424242, Msg: who knows",
                                                     code=424242))
    assert raised == ("LarkAPIError", "Failed: Code: 424242, Msg: who knows")
    assert lines[0] == "Failed: Code: 424242, Msg: who knows"
    assert BUG_BANNER_TAIL in lines[1]


def test_A10_the_not_found_OVERREACH_is_recorded_as_it_stood_BEFORE_LD531(monkeypatch):
    """**The behavior question AC4 exists to name — recorded, then answered.**

    **THE NODE ID IS KEPT AND THE BODY MOVED TO THE NEW CONCLUSION** (a renamed test is a
    removed test — this repo's own precedent, ``tests/test_base_copy_folder_route_scope.py``).

    **What this test asserted before LD-531, verbatim, and it PASSED:** the bare words
    ``not found`` — in ANY message, from any exception, carrying no Lark code at all — routed to
    the missing-document-permissions banner::

        lines, raised = _routed(monkeypatch, RuntimeError("template asset not found on disk"))
        assert lines == PERMISSION_LINES
        assert raised == ("ClickException", PERMISSION_REFUSAL)

    **The reason that reach existed is preserved and still honoured:** ``not found`` is Lark's
    own ``msg`` for ``1061004`` on the docx read, and an operator who cannot read a document
    must be told to share it. Nothing about that changed. What changed is *how the case is
    recognised* — by the code Lark sent, not by two words that any unrelated failure can also
    contain. So the real case is still caught (§ A10's coded shapes, all three still green) and
    an unrelated ``not found`` no longer is.

    **The conclusion that moved:** an exception whose message merely contains ``not found``,
    with no Lark document-access code and no scope denial, takes the DEFAULT arm now. It still
    exits non-zero — the guarantee that mattered — and it now shows its own message and the
    bug-report banner instead of advice about sharing a Lark document it has nothing to do with.
    """
    lines, raised = _routed(monkeypatch, RuntimeError("template asset not found on disk"))
    assert lines != PERMISSION_LINES, (
        "the 'not found' over-reach is back: an unrelated failure is being reported as a "
        "document-permissions problem")
    assert raised == ("RuntimeError", "template asset not found on disk"), (
        "the default arm must re-raise, so the exit stays non-zero and the real error shows")
    assert lines[0] == "template asset not found on disk"
    assert BUG_BANNER_TAIL in lines[1]


# =========================================================================== #
# § B — THE REGISTRY'S OWN CONTRACT.                                           #
# =========================================================================== #

import pathlib  # noqa: E402

from larkdocio.common.citations import cites_dev_repo, label_for  # noqa: E402
from larkdocio.common.error_codes import (  # noqa: E402
    DENIAL_CLASSES,
    ERROR_CODES,
    LABEL_NOT_CAPTURED,
    VERIFICATION_LABELS,
    ErrorCodeNote,
    note_for,
    notes_for,
)

_REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_B1_every_row_is_well_formed(code):
    note = ERROR_CODES[code]
    assert isinstance(note, ErrorCodeNote)
    assert note.code == code, "a row filed under a key that is not its own code"
    assert note.verification in VERIFICATION_LABELS, note.verification
    assert note.denial_class in (None, *DENIAL_CLASSES), note.denial_class
    assert note.evidence.strip(), "a row with no evidence is a memory, not a fact"


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_B2_a_meaning_is_not_the_label_spelled_out(code):
    """LD-247's own rule, inherited: a row whose meaning restates the label told nobody
    anything. Length is the crude half; the strict half is that the meaning is not the label."""
    note = ERROR_CODES[code]
    assert len(note.meaning) > 40, (code, note.meaning)
    assert note.meaning.strip().rstrip(".").lower() != note.label.strip().rstrip(".").lower()


@private_tree.citations
@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_B3_every_evidence_pointer_that_names_a_path_RESOLVES(code):
    """Inherited from ``tests/test_base_client.py``'s AC7 guard, widened to every surface."""
    for token in ERROR_CODES[code].evidence.split():
        token = token.strip("`,;()").split("§")[0].rstrip()
        if token.startswith("dev/"):
            assert (_REPO / token).exists(), (code, token)


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_B4_a_maintainer_repo_citation_wears_its_label(code):
    """The wheel carries no captures, so a bare ``dev/…`` path reads as a next step and dangles.
    ``tests/test_dev_repo_citations.py`` enforces this library-wide; asserted here too because
    this table is where evidence pointers are now AUTHORED."""
    evidence = ERROR_CODES[code].evidence
    if cites_dev_repo(evidence):
        # LD-699: the label the citation earns — private record or source repository.
        assert label_for(evidence) in evidence, (code, evidence)


def test_B5_a_blank_label_is_a_DECLARED_absence_both_ways():
    """The anti-rubber-stamp guard, in both directions (the LD-307 ``DECLARED_UNWIRED`` shape).

    An empty ``label`` means *nobody recorded Lark's own words for this code*. That is a real
    and honest state — inventing a plausible message would launder a document reference into a
    capture — but it has to be **declared**, with a reason, or it becomes indistinguishable
    from a row somebody left half-written.
    """
    blank = {code for code, note in ERROR_CODES.items() if not note.label}
    assert blank == set(LABEL_NOT_CAPTURED), (
        f"blank labels {sorted(blank)} vs declared {sorted(LABEL_NOT_CAPTURED)} — a blank "
        "label with no written reason, or a reason whose row has since gained a real label")
    for code, reason in LABEL_NOT_CAPTURED.items():
        assert len(reason) > 60, (code, reason)


def test_B6_a_wire_observed_row_carries_the_words_it_arrived_with():
    """The teeth on ``verification``: *observed* means somebody wrote down what Lark said —
    **or** wrote down that they did not, which is a different and equally honest row.

    ``99991400`` is the live example: the write spike tripped it three times and recorded the
    code and the request rate, not Lark's message text. Claiming a label for it would be an
    invention; claiming it was never observed would be false. So the absence is declared.
    """
    for code, note in ERROR_CODES.items():
        if note.verification in ("wire-observed", "denial-verified"):
            assert note.label or code in LABEL_NOT_CAPTURED, (
                f"{code} claims to have been observed but carries no message text and no "
                "written reason for the gap — either it was not observed, or its words were "
                "not recorded, and those are different rows")


def test_B7_the_lookup_is_representation_agnostic_and_total():
    assert note_for(1002) is note_for("1002") is ERROR_CODES[1002]
    assert note_for(424242) is None
    assert note_for(None) is None and note_for("banana") is None and note_for(object()) is None


def test_B8_notes_for_REFUSES_a_code_with_no_row():
    assert list(notes_for((1002, 91402))) == [1002, 91402]
    with pytest.raises(KeyError):
        notes_for((1002, 424242))


# =========================================================================== #
# § C — BIDIRECTIONAL COMPLETENESS (the tests/test_permissions_registry.py     #
#       pattern: a table code with no row reddens, a row nothing reaches too). #
# =========================================================================== #

def _branch_table_codes():
    """Every code a **classification** in ``src/`` compares against, gathered from the tables
    themselves rather than from a list somebody keeps by hand."""
    from larkdocio import errors as errors_module
    from larkdocio import permissions
    from larkdocio.base import disposition
    from larkdocio.base import errors as base_errors
    from larkdocio.base import field_authoring
    from larkdocio.base import schema_settle
    from larkdocio.sheets import write_client

    found = {}

    def _add(where, codes):
        for code in codes:
            found.setdefault(int(str(code)), []).append(where)

    _add("base.errors.BASE_TAXONOMY_CODES", base_errors.BASE_TAXONOMY_CODES)
    _add("base.errors.FEATURE_GATE_CODES", base_errors.FEATURE_GATE_CODES)
    _add("base.errors.WRITE_ERROR_CODES", base_errors.WRITE_ERROR_CODES)
    _add("base.disposition.SYSTEMIC_CODES", disposition.SYSTEMIC_CODES)
    _add("base.disposition.ENTRY_SCOPED_CODES", disposition.ENTRY_SCOPED_CODES)
    _add("base.field_authoring.FIELD_OP_ERROR_CODES", field_authoring.FIELD_OP_ERROR_CODES)
    _add("base.schema_settle.ASYNC_SETTLE_CODES", schema_settle.ASYNC_SETTLE_CODES)
    _add("sheets.write_client._GONE_CODES", write_client._GONE_CODES)
    _add("permissions.SCOPE_DENIAL_CODES", permissions.SCOPE_DENIAL_CODES)
    _add("errors.RATE_LIMIT_CODE", (errors_module.RATE_LIMIT_CODE,))
    _add("read.download.DOCUMENT_ACCESS_CODES", _download_access_codes())
    return found


def _download_access_codes():
    from larkdocio.read import download

    return download.DOCUMENT_ACCESS_CODES


# --------------------------------------------------------------------------- #
# THE SECOND GATHERER: the COMPARISON SITES THEMSELVES (LD-531 fix round).     #
#                                                                             #
# The first gatherer above reads eleven named TABLES. That is a real half of   #
# the census and a demonstrably incomplete one: four codes — 90202, 1061002,   #
# 1063001, 99992351 — reached a control-flow comparison through a MODULE-LEVEL #
# NAMED CONSTANT and sat in no table, so a table-only gatherer passed green    #
# with the hole open while its own docstring claimed comparison coverage. That #
# is a claim wider than its evidence (D-59 / negative-claims § A.1), and the   #
# fix is to widen the EVIDENCE: this gatherer enumerates the comparisons.      #
#                                                                             #
# METHOD, stated because a census whose method is unstated proves nothing:     #
#   pass 1 — for every ``src/larkdocio/**/*.py``, record the module-level      #
#     simple assignments whose value ``literal_eval``s (int / digit-str /      #
#     tuple / set / list, including one level of ``frozenset(...)`` wrapping), #
#     plus that module's ``import`` bindings.                                  #
#   pass 2 — walk every ``ast.Compare``. Peel ``str()`` / ``int()`` /          #
#     ``.strip()`` / ``.lower()`` wrappers off each operand and resolve it to  #
#     numbers via: a literal; a Name bound to a const in THIS module; a Name   #
#     bound by ``from M import N`` to a const in M (**the cross-module arm is  #
#     the one that catches the four**); an ``M.N`` attribute on an imported    #
#     module; or a container literal of those.                                 #
#   filter — a resolved number counts as a CODE only if some OTHER operand of  #
#     the same Compare mentions ``code`` case-insensitively. The wire field is #
#     always ``code``, so this is the discriminator that separates an error    #
#     code from a size, an index or a Base field-type id.                      #
#                                                                             #
# FALSE POSITIVES it admits, and they are declared rather than filtered by     #
# taste: the filter matches any operand whose SOURCE TEXT contains "code", so  #
# ``len(codes) != 1`` and ``len(encoded) == 1`` offer up ``1``, and Lark's     #
# SUCCESS sentinel ``0`` is compared against ``code`` all over the library.    #
# Both are declared in :data:`NOT_ERROR_CODES` with a written reason and       #
# guarded in BOTH directions, so the exemption list cannot grow silently.      #
#                                                                             #
# FALSE NEGATIVES it still admits, named because an unstated limit is the      #
# defect this round exists to fix: (a) a code reached through a name this      #
# resolver cannot follow — a function-parameter default, a class attribute, a  #
# dict lookup, a value computed at runtime; (b) a code compared against an     #
# operand whose text never says ``code``. Neither is hypothetical-only, so the #
# TABLE gatherer above is kept and UNIONED with this one rather than replaced: #
# the two have different blind spots, and a code needs to hide from both.      #
# --------------------------------------------------------------------------- #

import ast  # noqa: E402
import functools  # noqa: E402
import re  # noqa: E402

_SRC = _REPO / "src"
_PACKAGE = _SRC / "larkdocio"

#: The operand-text discriminator. Lark's wire field is ``code`` on every route.
_CODEISH = re.compile(r"code", re.I)

#: Numbers that reach a comparison against something the filter reads as code-ish and are **not
#: Lark error codes**. One written reason each, guarded in both directions by
#: :func:`test_C4_a_non_code_number_is_a_DECLARED_exemption_both_ways` — an exemption nobody can
#: still reach reddens, and a new unexplained number reddens too, so this cannot become the
#: place where a real hole is quietly parked.
NOT_ERROR_CODES = {
    0: (
        "Lark's SUCCESS sentinel. Every surface tests `code in (0, None)` or `str(code) == '0'` "
        "before it looks for a failure at all, so 0 is compared against `code` more often than "
        "any real code is — and a row explaining that 0 means nothing went wrong would be a "
        "row about the absence of an error, in a table of errors"
    ),
    1: (
        "a CARDINALITY, not a code: `len(codes) != 1` in base.disposition's platform-anomaly "
        "clause asks whether every attempt failed the same way, and `len(encoded) == 1` in "
        "write.apply asks whether the entry compiled to a single block. Both are offered up "
        "only because the words 'codes' and 'encoded' contain 'code' — the declared price of a "
        "text-level discriminator, paid here rather than by narrowing the census"
    ),
    128: (
        "a UTF-8 CONTINUATION-BYTE MARKER, not a code: common.sanitize's byte-budget "
        "truncation walks back off a partial sequence with `(encoded[cut] & 0xC0) == 0x80`, so "
        "the number offered up is the bit pattern 0b10xxxxxx and the operand that looks "
        "code-ish is the local name `encoded` — the same declared price entry 1 above pays for "
        "the words 'codes' and 'encoded'. Paid here rather than by renaming the variable or "
        "narrowing the census, for exactly the reason entry 1 states"
    ),
}


def _literal(node):
    """``ast.literal_eval``, plus one level of ``frozenset(...)`` / ``set(...)`` wrapping."""
    try:
        return ast.literal_eval(node)
    except Exception:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("frozenset", "set", "tuple", "list") and len(node.args) == 1:
            try:
                return ast.literal_eval(node.args[0])
            except Exception:
                return None
        return None


@functools.lru_cache(maxsize=1)
def _module_index():
    """``{dotted module: (tree, relpath, consts, imports)}`` for the whole shipped package."""
    index = {}
    for path in sorted(_PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        dotted = ".".join(path.relative_to(_SRC).with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        consts, imports = {}, {}
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = _literal(node.value)
                if value is None:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        consts[target.id] = value
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = (node.module, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split(".")[0]] = (alias.name, None)
        index[dotted] = (tree, str(path.relative_to(_REPO)), consts, imports)
    return index


_UNRESOLVED = object()


def _const(module, name, seen=()):
    """A module-level constant's value, following ``from M import N`` one hop at a time."""
    if (module, name) in seen:
        return _UNRESOLVED
    entry = _module_index().get(module)
    if entry is None:
        return _UNRESOLVED
    _tree, _rel, consts, imports = entry
    if name in consts:
        return consts[name]
    source_module, source_name = imports.get(name, (None, None))
    if source_module and source_name:
        return _const(source_module, source_name, seen + ((module, name),))
    return _UNRESOLVED


def _numbers(value):
    """Flatten a resolved constant to the list of ints in it, or ``None`` if it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [int(value)] if value.isdigit() else None
    if isinstance(value, (tuple, list, set, frozenset)):
        flat = []
        for element in value:
            got = _numbers(element)
            if got is None:
                return None
            flat += got
        return flat
    return None


def _unwrap(node):
    """Peel the representation-agnostic wrappers this library compares codes through."""
    while isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in ("str", "int") \
                and len(node.args) == 1:
            node = node.args[0]
        elif isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("strip", "lower", "upper"):
            node = node.func.value
        else:
            break
    return node


def _resolve_operand(node, module):
    """``(numbers, provenance)`` for one Compare operand, or ``(None, None)``."""
    node = _unwrap(node)
    if isinstance(node, ast.Constant):
        return _numbers(node.value), "literal"
    if isinstance(node, ast.Name):
        value = _const(module, node.id)
        return (_numbers(value), node.id) if value is not _UNRESOLVED else (None, None)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        _tree, _rel, _consts, imports = _module_index()[module]
        base = imports.get(node.value.id, (None, None))[0]
        if base:
            value = _const(base, node.attr)
            if value is not _UNRESOLVED:
                return _numbers(value), f"{node.value.id}.{node.attr}"
        return None, None
    if isinstance(node, (ast.Tuple, ast.Set, ast.List)):
        flat, provenance = [], []
        for element in node.elts:
            got, prov = _resolve_operand(element, module)
            if got is None:
                return None, None
            flat += got
            provenance.append(prov)
        return flat, "inline{%s}" % ",".join(sorted(set(provenance)))
    return None, None


@functools.lru_cache(maxsize=1)
def _comparison_site_codes():
    """``{code: (site, ...)}`` — every number a CONTROL-FLOW comparison in ``src/`` tests a
    ``code`` against, resolved through module-level constants and ``str()`` wrappers.

    Read the block comment above for the method and for both of its error directions. The
    declared non-codes in :data:`NOT_ERROR_CODES` are excluded here, not silently dropped.
    """
    found = {}
    for module, (tree, relpath, _consts, _imports) in _module_index().items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left] + list(node.comparators)
            for position, operand in enumerate(operands):
                numbers, provenance = _resolve_operand(operand, module)
                if not numbers:
                    continue
                others = " | ".join(ast.unparse(_unwrap(other))
                                    for index, other in enumerate(operands)
                                    if index != position)
                if not _CODEISH.search(others):
                    continue
                site = f"{relpath}:{operand.lineno} via {provenance}"
                for number in numbers:
                    if number in NOT_ERROR_CODES:
                        continue
                    found.setdefault(number, set()).add(site)
    return {code: tuple(sorted(sites)) for code, sites in found.items()}


def _every_reached_code():
    """The UNION of both gatherers — eleven named tables, and every comparison site."""
    reached = {code: sorted(set(where)) for code, where in _branch_table_codes().items()}
    for code, sites in _comparison_site_codes().items():
        reached.setdefault(code, []).extend(sites)
    return reached


def test_C1_every_branch_table_code_HAS_AN_AUTHORED_ROW():
    """Direction one, and it now measures what its own sentence says: every code that reaches a
    branch **or a comparison** in ``src/`` resolves through ONE authored lookup.

    **What this test asserted before LD-531's fix round, and it passed:** the same emptiness,
    over ``_branch_table_codes()`` alone — eleven tables and not one comparison site. The
    reason for reading the tables at runtime is unchanged and still honoured (a list somebody
    keeps by hand goes stale, and the tables are the classifications). What moved is the
    **scope of the evidence**: four codes reached a comparison through a named constant and
    were in no table, so the docstring's *"or a comparison"* was a claim wider than the
    gatherer. The gatherer was widened to match the claim rather than the claim narrowed to
    match the gatherer — AC1's requirement is coverage.
    """
    holes = {code: where for code, where in _every_reached_code().items()
             if code not in ERROR_CODES}
    assert not holes, (
        f"{len(holes)} code(s) a classification compares against have no authored row: {holes} "
        "— a code this library branches on and cannot explain is exactly the hole LD-531 closed")


def test_C1_the_census_is_NOT_VACUOUS():
    """A completeness guard that reaches nothing passes by construction. Floors, not a frozen
    count: eleven named tables, and every one of them non-empty."""
    tables = _branch_table_codes()
    assert len(tables) >= 30, len(tables)
    wheres = {w for where in tables.values() for w in where}
    assert len(wheres) == 11, sorted(wheres)


def test_C3_the_comparison_census_RESOLVES_A_CODE_BEHIND_A_NAMED_CONSTANT():
    """**The anti-vacuity guard for the second gatherer, and it pins the exact blind spot that
    made the first one useless.**

    A census that silently stops resolving names would go quiet, not red — it would simply find
    fewer codes, and ``test_C1`` would keep passing. So the four codes whose named-constant
    indirection defeated the literal scan are named here **with the site and the constant they
    resolve through**, one of them cross-module. Break the import arm of ``_const`` and this
    reddens immediately.
    """
    census = _comparison_site_codes()
    expected = {
        90202: ("src/larkdocio/sheets/ops/_shared.py", "MALFORMED_RANGE_CODE"),
        1061002: ("src/larkdocio/drive/client.py", "FOLDER_REFUSED_CODE"),
        1063001: ("src/larkdocio/drive/access_write.py", "INVALID_PARAMETER_CODE"),
        99992351: ("src/larkdocio/read/client.py", "_INVALID_USER_IDS_CODE"),
    }
    for code, (path, constant) in expected.items():
        assert code in census, (
            f"{code} reaches a control-flow comparison in {path} through {constant} and the "
            "comparison census no longer sees it — the resolver is broken, and a broken "
            "resolver makes test_C1 pass by finding nothing")
        assert any(site.startswith(path) and site.endswith(f"via {constant}")
                   for site in census[code]), (code, census[code])
    # The cross-module arm specifically: FOLDER_REFUSED_CODE is defined in drive/errors.py and
    # compared in drive/client.py and drive/folders_write.py, which is the hop a same-module
    # resolver would miss.
    assert any("drive/folders_write.py" in site for site in census[1061002]), census[1061002]
    assert len(census) >= 19, sorted(census)
    assert len(_module_index()) >= 150, len(_module_index())


def test_C4_a_non_code_number_is_a_DECLARED_exemption_both_ways():
    """The exemption list is where a real hole would hide, so it is guarded like one.

    Both directions: a declared non-code that no comparison offers up any more is a stale
    exemption and reddens; a number the census would have to exclude that nobody declared
    cannot exist, because ``_comparison_site_codes`` only ever drops what is declared here.
    """
    for number, reason in NOT_ERROR_CODES.items():
        assert len(reason) > 60, (number, reason)
        assert number not in ERROR_CODES, (
            f"{number} is declared as NOT an error code and also carries a row — one of the "
            "two is wrong")
    undeclared = _comparison_site_codes()
    assert not (set(NOT_ERROR_CODES) & set(undeclared)), "an exemption leaked into the census"
    # Direction two: each exemption is still REACHED, so the list cannot rot into a rubber stamp.
    reached_without_exemptions = set()
    for module, (tree, _rel, _consts, _imports) in _module_index().items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left] + list(node.comparators)
            for position, operand in enumerate(operands):
                numbers, _prov = _resolve_operand(operand, module)
                if not numbers:
                    continue
                others = " | ".join(ast.unparse(_unwrap(other))
                                    for index, other in enumerate(operands)
                                    if index != position)
                if _CODEISH.search(others):
                    reached_without_exemptions.update(numbers)
    stale = sorted(set(NOT_ERROR_CODES) - reached_without_exemptions)
    assert not stale, (
        f"declared non-code(s) {stale} are no longer compared against anything code-shaped — "
        "the exemption is spent and its reason should be retired, not left standing")


def test_C2_every_AUTHORED_ROW_is_reached_or_DECLARED_prose_only():
    """Direction two: a row nothing reaches is either dead surface or an honest disclosure.

    **The rows in no classification are declared in :data:`PROSE_ONLY_ROWS`, each for its own
    written reason rather than by a permitted count** — which is why no number is stated here.
    The original members were exactly the measured holes of the census that created this guard,
    and that is the finding rather than a coincidence: a code nobody had tabled is a code nobody
    branches on, and writing its meaning down is the whole point. A row joins them by carrying a
    reason, never by making the arithmetic work.
    """
    reached = set(_every_reached_code())
    unreached = sorted(set(ERROR_CODES) - reached)
    assert unreached == sorted(PROSE_ONLY_ROWS), (
        f"rows reached by no classification: {unreached}; declared: "
        f"{sorted(PROSE_ONLY_ROWS)}")
    for code, reason in PROSE_ONLY_ROWS.items():
        assert len(reason) > 60, (code, reason)
        assert code in ERROR_CODES, code


#: A row that exists because a code arrives in **prose** — a docstring, a shipped guide
#: sentence, an operator-facing message — and no classification compares against it. Each is
#: allowed for its own written reason, and the guard above reddens if one gains a classifier or
#: if a classified code slips in here.
PROSE_ONLY_ROWS = {
    1770003: (
        "the docx *resource deleted* answer, measured on two docx routes at once. Deliberately "
        "in NO classification: this library's teardowns already treat ANY typed failure of the "
        "re-query as gone-ness, so a branch on this number would buy nothing and would quietly "
        "assert it is the only way a removed document refuses. The row exists so the reading is "
        "written down — Lark's word is DELETED, which is not the same word as unrecoverable"
    ),
    1770040: (
        "the object-ACL denial. Deliberately in NO classification: it is not a scope denial, so "
        "permissions must keep answering None for it, and no surface has measured a reason to "
        "branch on it — the row exists so the distinction is written down instead of guessed"
    ),
    1254701: (
        "the copy route's object-ACL denial. Recorded rather than classified for the same "
        "reason as 1770040: one send on one route is evidence for a row, not for a branch"
    ),
    1254702: (
        "the copy route's not-found, the third of that route's three answers. Its value is "
        "telling it APART from 1254701, which is a reading a caller does, not a branch this "
        "library takes"
    ),
}


# =========================================================================== #
# § D — THE PER-SURFACE CLASSIFICATIONS ARE NOT MERGED.                        #
# =========================================================================== #

def test_D1_the_ruled_base_split_is_STILL_base_disposition_s_OWN():
    """D4′ is load-bearing batch-halt behavior, and it is not the shared lookup's business.

    The registry carries no halt/continue field at all — the strongest form of *not merged*:
    there is nothing there for a second surface to accidentally inherit.
    """
    for note in ERROR_CODES.values():
        for forbidden in ("scope", "halts", "continues", "systemic", "entry_scoped",
                          "outcome", "landed"):
            assert not hasattr(note, forbidden), (
                f"the shared row grew a {forbidden!r} field — a per-surface classification is "
                "leaking into the one place every surface reads")


def test_D2_two_surfaces_that_hold_the_SAME_code_still_classify_it_THEIR_OWN_WAY():
    """``99992402`` is the proof: one authored row, three different surface readings."""
    from larkdocio.base import disposition
    from larkdocio.base import errors as base_errors
    from larkdocio.comments import read as comments_read

    assert 99992402 in ERROR_CODES, "the shared row"
    assert 99992402 in disposition.ENTRY_SCOPED_CODES        # base: the batch CONTINUES
    assert 99992402 not in disposition.SYSTEMIC_CODES
    assert 99992402 in base_errors.WRITE_ERROR_CODES         # base write: an expected refusal
    assert 99992402 in comments_read.COMMENT_ERROR_CODES     # comments: its own wording
    assert (comments_read.COMMENT_ERROR_CODES[99992402]
            != ERROR_CODES[99992402].meaning), (
        "the comments surface's route-specific wording collapsed into the shared meaning")


def test_D3_the_base_lookup_and_the_package_lookup_are_DIFFERENT_reaches():
    from larkdocio.base import errors as base_errors

    assert base_errors.note_for(1310249) is None, "the Base lookup answered about a sheets code"
    assert note_for(1310249) is not None, "the package lookup should answer about every surface"
    assert base_errors.note_for(1002) is note_for(1002), "and they agree where they overlap"


def test_D4_the_ruling_is_LOOKUP_ONLY___no_matrix_no_key_no_projection():
    """The maintainer's binding constraint, asserted rather than promised."""
    import larkdocio

    assert not list(_REPO.glob("ERRORS.md"))
    assert not list((_REPO / "src/larkdocio").rglob("ERRORS.md"))
    payload = larkdocio.capabilities()
    for fancy in ("error_codes", "errors", "error_registry", "error_matrix"):
        assert fancy not in payload, fancy
    assert not hasattr(larkdocio, "error_codes_matrix")
    assert "error" not in {k.lower() for k in payload}


# =========================================================================== #
# § E — THE THREE MEASURED HOLES, AND THE OBJECT-ACL CLASS.                    #
# =========================================================================== #

def test_E1_the_object_acl_class_is_DISTINCT_from_the_scope_denial_class():
    from larkdocio import permissions

    object_acl = {c for c, n in ERROR_CODES.items() if n.denial_class == "object-acl"}
    scope = {c for c, n in ERROR_CODES.items() if n.denial_class == "scope"}
    assert object_acl == {1770040, 1254701}, sorted(object_acl)
    assert scope == set(permissions.SCOPE_DENIAL_CODES), sorted(scope)
    assert not (object_acl & scope), "a code cannot be both"
    for code in object_acl:
        assert code not in permissions.DENIAL_CODES, (
            f"{code} is an object-ACL denial and must NOT be in the scope-denial set — the two "
            "have different fixes (share the object vs grant in the console)")


def test_E2_the_1770040_row_records_the_LD501_finding_as_a_finding():
    """``is_permission_error: false, denial: null`` — and that is the CORRECT answer, not a gap.

    The row must say so, and the behavior must still be so. If a later change ever makes
    ``denial_from`` classify this code, this test is where it gets caught and argued.
    """
    from larkdocio.permissions import denial_from, looks_like_scope_denial

    note = ERROR_CODES[1770040]
    assert note.label == "no folder permission"
    assert note.denial_class == "object-acl"
    assert note.verification == "wire-observed"
    assert "001-ac4-denial-create-document.json" in note.evidence
    lowered = note.meaning.lower()
    assert "denial_from returns none" in lowered.replace("permissions.", "")
    assert "correctly" in lowered, "the row must say the None is right, not merely report it"
    assert "share the folder" in lowered, "the object-ACL fix, named"
    # and the behavior the row describes:
    assert looks_like_scope_denial(1770040, "no folder permission") is False
    assert denial_from(1770040, "no folder permission") is None


def test_E3_the_copy_route_pair_is_DISTINGUISHABLE_and_neither_row_over_claims():
    perm, absent = ERROR_CODES[1254701], ERROR_CODES[1254702]
    assert (perm.label, absent.label) == ("DriveNodePermNotAllow", "DriveNodeNotExist")
    assert perm.denial_class == "object-acl" and absent.denial_class is None
    assert "002-copy-app-unreachable-folder.json" in perm.evidence
    assert "ld387-01" in absent.evidence
    # D-59: each row states the reach of its own measurement.
    assert "one send" in perm.meaning and "2026-08-18" in perm.meaning
    assert "unmeasured rather than refuted" in perm.meaning


def test_E4_a_row_never_asserted_beyond_its_evidence():
    """The ``documented-unverified`` precedent, applied. A row that has never been seen must not
    read as observed — and it must not carry a capture path, which would be the laundering."""
    for code, note in ERROR_CODES.items():
        if note.verification != "documented-unverified":
            continue
        assert not cites_dev_repo(note.evidence), (
            code, "an unverified row citing a capture is claiming what it does not have")
        assert ("never observed" in note.evidence.lower()
                or "no capture" in note.evidence.lower()
                or "not " in note.evidence.lower()), (code, note.evidence)


def test_E5_the_library_still_never_widens_or_asks_for_a_scope():
    """A row DESCRIBES a requirement; it does not act. Same negative the permissions registry
    states, asserted over the new table's own text."""
    text = " ".join(f"{n.label} {n.meaning} {n.evidence}" for n in ERROR_CODES.values()).lower()
    for forbidden in ("requests the scope", "escalates the scope", "will request access",
                      "grants itself the", "escalates its scope", "we will grant"):
        assert forbidden not in text, forbidden


# =========================================================================== #
# § F — THE READER'S TYPED ROUTING, AND ITS TWO NAMED REACH CHANGES.           #
# =========================================================================== #

def _operator_facing_literals(module):
    """Every string literal *module* hands straight to ``logger.error`` or ``ClickException``.

    Derived by AST, and returned as a **set of whole literals** so a caller can compare by
    EQUALITY. That is the whole point (LD-671 AC1): the folded-substring form this replaces
    could not see a pinned line that had GAINED a suffix — a verifier appended text to an
    operator-facing line and the test stayed green, because the pinned bytes were still a
    substring of the longer line. Equality against the literal the call site actually passes
    has no such blind spot, and it is available here precisely because every operator-facing
    line in ``read/download.py`` is ONE literal (the file says so at the site, and says why).
    """
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=module.__file__)
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in {"error", "ClickException"}:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.add(arg.value)
    return out


def test_F1_the_operator_facing_TEXT_is_byte_identical():
    """Both banners and both refusals, quoted from the tree, held against § A's frozen bytes.

    The text is consumer-reaching (``tests/test_cli_refusal_uniformity.py`` covers the fork it
    sits in), so LD-531 changed **how** an exception arrives at it and not one byte of it.

    **The comparison is EQUALITY against the literal the call site passes** — see
    :func:`_operator_facing_literals` for why the folded-substring form it replaces was named by
    its strongest possible property and delivered a much weaker one (LD-671 AC1).
    """
    from larkdocio.read import download

    literals = _operator_facing_literals(download)
    pinned = (IP_BLOCK_LINES + PERMISSION_LINES
              + [IP_BLOCK_REFUSAL, PERMISSION_REFUSAL,
                 # LD-658 AC1b's scope arm — new text, held here with the rest of it.
                 SCOPE_DENIAL_BANNER, SCOPE_DENIAL_RELEASE_LINE, SCOPE_DENIAL_REFUSAL])
    # Anti-vacuity, in the shape tests/test_packaging.py models: a guard that found no call
    # sites would pass its equality checks by having nothing to disagree with. It must fail
    # because it COULD NOT CHECK, distinctly from passing because the bytes held.
    assert len(literals) >= len(pinned), (
        f"only {len(literals)} operator-facing literal(s) derived from {download.__file__} — "
        f"fewer than the {len(pinned)} pinned below, so this guard is inert. Either the "
        f"logger.error / ClickException call shape moved, or the lines stopped being one "
        f"literal each (which is the thing the site's own comment asks a maintainer to keep).")
    for line in pinned:
        assert line in literals, (
            f"not one of the literals {download.__name__} passes to logger.error / "
            f"ClickException:\n  {line!r}\nThis is EQUALITY, not containment: a line that "
            f"gained a prefix or a suffix fails here, which is the mutation the folded form "
            f"this replaced survived (LD-671 AC1).")


def test_F2_the_routing_is_TYPED_not_grepped():
    """The condition no longer greps for a code number or for ``not found``."""
    from larkdocio.read import download

    source = pathlib.Path(download.__file__).read_text(encoding="utf-8")
    branch = [l for l in source.splitlines() if "_document_access_refusal(e)" in l]
    assert branch, "the typed predicate is not what the branch asks"
    assert '"99991672" in error_msg' not in source
    assert '"1061004" in error_msg' not in source
    assert '"not found" in error_msg' not in source
    assert download.DOCUMENT_ACCESS_CODES == ("99991672", "1061004")


@pytest.mark.parametrize("code", ["99991672", "1061004", 99991672, 1061004])
def test_F3_the_CODED_cases_still_route_to_the_banner_in_both_representations(monkeypatch, code):
    """LD-658 AC1b prepends Lark's own answer; a bare ``LarkAPIError`` carries no denial, so the
    share-the-document banner that follows it is unchanged."""
    exc = LarkAPIError("Failed: whatever", code=code)
    assert getattr(exc, "denial", None) is None
    lines, raised = _routed(monkeypatch, exc)
    assert lines == ["Failed: whatever"] + PERMISSION_LINES
    assert raised == ("ClickException", PERMISSION_REFUSAL)


def test_F4_REACH_CHANGE_ONE_narrowed__an_unrelated_not_found_no_longer_routes(monkeypatch):
    """Named, not absorbed. Three unrelated shapes that used to get the sharing advice."""
    from larkdocio.errors import LarkConfigError

    for exc in (RuntimeError("template asset not found on disk"),
                LarkConfigError("config key not found in .env"),
                LarkAPIError("Failed: Code: 424242, Msg: workflow not found", code=424242)):
        lines, raised = _routed(monkeypatch, exc)
        assert lines != PERMISSION_LINES, exc
        assert raised[0] == type(exc).__name__, exc      # re-raised → still non-zero exit
        assert BUG_BANNER_TAIL in lines[1], exc


def test_F5_REACH_CHANGE_TWO_widened__a_typed_scope_denial_routes_whatever_its_code(monkeypatch):
    """A ``LarkPermissionError`` is what this banner is FOR, so it reaches it now.

    Before, only the two code numbers appearing as TEXT in the message did, so a denial that
    named its missing scope under any other code fell through to the bug-report banner.

    **The widening is exactly as wide as the type is, and no wider** — which is narrow, because
    :func:`larkdocio.permissions.denial_from` builds the type only when Lark actually NAMED the
    scope (in the body or in the message's bracketed list). ``api_error(41050, "access denied")``
    is still a plain ``LarkAPIError`` and still takes the default arm.
    """
    from larkdocio.errors import api_error

    scope_named = "Access denied. One of the following scopes is required: [drive:drive]"
    for code, msg in [(41050, scope_named), (1069303, scope_named), (424242, scope_named)]:
        err = api_error(f"Failed: Code: {code}, Msg: {msg}", code=code, msg=msg)
        assert type(err).__name__ == "LarkPermissionError", (code, msg)
        lines, raised = _routed(monkeypatch, err)
        # LD-658 AC1b: a typed denial still reaches THIS branch (the widening F5 records), and
        # now reaches the branch's SCOPE arm rather than its share-the-document arm — because
        # `drive:drive` is a scope, and no share dialog grants one. What F5 pins is the reach.
        #
        # LD-671 AC1 takes the same repair as § F1: the WHOLE four-line sequence, in order, by
        # equality. `"drive:drive" in " ".join(lines)` was true of any output that mentioned the
        # scope anywhere, in any order, alongside any amount of other text — so it could not see
        # a line gaining a suffix, a line being inserted, or the share-the-document arm being
        # printed as well. The sequence is available at every one of these codes, so pin it.
        assert lines == [str(err), SCOPE_DENIAL_BANNER, err.denial.detail(),
                         SCOPE_DENIAL_RELEASE_LINE], (code, msg)
        assert "drive:drive" in lines[2], (code, msg)
        assert raised == ("ClickException", SCOPE_DENIAL_REFUSAL)

    # ...and no wider: a denial Lark did not spell out is not a LarkPermissionError, so it is
    # not routed here by the type arm. The `.code` arm still catches the reader's own codes.
    vague = api_error("Failed: Code: 41050, Msg: access denied", code=41050,
                      msg="access denied")
    assert type(vague).__name__ == "LarkAPIError"


def test_F6_the_substring_FALLBACKS_that_stay_are_named_with_their_reason():
    """Two substrings survive, each because **no code is available on its path** — and the tree
    says so, at the site, in prose a later reader will actually meet."""
    from larkdocio.read import download

    assert download._NO_READ_PERMISSION_MARKER == "not read permission"
    source = " ".join(pathlib.Path(download.__file__).read_text(encoding="utf-8").split())

    # (1) `not read permission` — kept for the code-LESS raises on the read path.
    assert "a code-less error can carry it" in source
    assert "has none at all" in source
    assert "there is nothing to type, so a substring is not a shortcut" in source

    # (2) the IP-block branch stays substring-only, and the reason is that there is no code.
    report = " ".join((download._report_error.__doc__ or "").split())
    assert ("no measurement here has ever recorded a Lark code for an IP-allowlist refusal"
            in report), report

    # and both reach changes are named where a maintainer reads the function, not only here.
    assert "Two reach changes, both deliberate, both pinned by tests." in report
    assert "*Narrowed.*" in report and "*Widened.*" in report


def test_F7_the_typed_predicate_is_TOTAL_over_the_shapes_the_reader_can_raise():
    """Every arm, plus the no-match case, so the predicate cannot be vacuously true or false."""
    from larkdocio.errors import LarkConfigError, api_error
    from larkdocio.read.download import _document_access_refusal

    denial = api_error("x", code=41050,
                       msg="Access denied. One of the following scopes is required: [drive:drive]")
    assert _document_access_refusal(denial) is True                      # arm 1: the type
    assert _document_access_refusal(LarkAPIError("x", code="1061004")) is True   # arm 2: code
    assert _document_access_refusal(LarkAPIError("x", code=99991672)) is True
    assert _document_access_refusal(
        LarkAPIError("Failed: not read permission")) is True              # arm 3: the fallback
    assert _document_access_refusal(RuntimeError("asset not found")) is False
    assert _document_access_refusal(LarkConfigError("no credentials")) is False
    assert _document_access_refusal(LarkAPIError("x", code=424242)) is False
