"""THE ACCESS GATE (LD-432 AC11, widened by LD-456) — the grant lifecycle against real Lark.

``@pytest.mark.live_write``, deselected by default. Run it explicitly::

    pytest -m live_write

**What only a live run can establish.** The offline tests pin the request bytes and the parsed
shapes against committed captures; they cannot tell you what Lark *did*. Four things here are
live-only:

1. **The grant really landed** — proved by the shipped op's own independent member read, and
   asserted as ``stored``, never as *the call returned 0*. This family was measured **swallowing**
   a member write, which is the whole reason the op reads back at all. Which leg carries that
   proof here is **not** the ADD route — see § THE FOUNDING PREMISE below: the level change is.
2. **The whole lifecycle moves in both directions** — ``edit`` -> ``full_access`` -> ``view`` and
   then a revoke that returns the member list to **exactly the membership the object was born
   with**, each judged by a read. See § THE FOUNDING PREMISE below for why that is stated as a
   delta rather than as an empty list.
3. **The owner is not a member row** — ``metas/batch_query`` reports the app's own bot id as the
   owner while no member row says so. The trap, measured rather than quoted.

**§ THE FOUNDING PREMISE — moved by LD-577, reason preserved (supersession).** Both arms used to
open by asserting that an object this run had just created carried **no** members at all, and
that was written for a real reason: the surface exists because *nobody is on a fresh document at
a level anyone chose*, and an empty birth list is the cleanest way to see a grant arrive. That
premise was measured on a document filed **nowhere**. This gate files every disposable into the
disposables **folder**, and a document filed into a folder **inherits the folder's access** —
each inherited row coming back marked ``perm_type='container'``. The library says so in its own
words and with its own dates: :data:`larkdocio.drive.access.MEMBER_LIST_AT_BIRTH`. As this
tenant's disposables folder is shared, the birth list measured **2026-08-25** (LD-577, filed from
the LD-574 review) held **three** inherited rows — an app, a group and a user — so both arms
failed on their own premise before exercising a single grant.

So the premise is **transformed, not deleted**: the arms still READ the birth membership, and
still judge everything by a read — they now assert the **delta their own grant and revoke
cause** against that measured birth list (grant adds exactly its row; revoke restores exactly the
birth list). It is **not** pinned to the current three rows: the tenant's folder sharing may
change again, and this gate must survive it.

**What the delta form does and does not strengthen — cut leg by leg (LD-577 fix round).** The
delta form is *not* uniformly stronger than the emptiness form, and saying so as a blanket was
wrong:

* **STRENGTHENED — the revoke leg, and the nobody-else leg on both.** The revoke must return the
  list to the *measured* birth membership rather than to ``[]``, and every read-back also asserts
  that no row the arm was not asked about moved. Neither claim was available while the arm died
  on its premise, and the emptiness form could not state the second at all.
* **INHERITANCE-CONFOUNDED — the grant (ADD-route) read-back.** The disposables folder carries
  this gate's grantee at ``full_access`` already, so ``members_after_grant`` equals
  ``members_at_birth`` and a **swallowed** member write would satisfy the level assertion out of
  the birth state. Measured **2026-08-26**: identical member lists before and after the grant on
  all three kinds. That leg proves the op *accepted and read back*, not that it stored.
* **THE UNAMBIGUOUS MEMBER WRITE is ``update_access``**, and every arm now carries one, asking a
  level **nothing inherited reads back as**: the docx arm's ``view`` then ``edit``, the sheet
  arm's ``view`` (it had no member write of its own before this round), the Base arm's ``edit``.
  A swallow there reads back the inherited ``full_access`` and reddens.
4. **The two copy-lever keys store** — each PATCHed alone and confirmed by the settings read,
   with the baseline (``anyone_can_edit`` on both) observed first so the change is a change.
5. **The OBJECT TYPE reaches past docx** (LD-456's second arm) — a grant, a read-back and a
   revoke on a **spreadsheet** and on a **Base** this run created, plus the control that
   reproduces the consumer failure: the same token at the default type still answers Lark's
   ``1063001``, and the library now says what that means.

**Disposables only (D-12).** Every object this gate touches — the document, and (LD-456) the
spreadsheet and the Base — it created itself, in this run, and
trashes in a ``finally`` — acquired **inside** the protected region and ledgered the instant its
id exists, so a create that fails cannot leave an earlier one behind. It names **no**
pre-existing document: not the read canary, not ``LARKDOCIO_WRITE_SCRATCH_DOC``, not either
scratch surface, not either zoo — and not LD-420's living fixture, which is a standing artifact
this issue does not own. Gone-ness is proved by an **independent re-query**, never by the
delete's own return code.

**The grantee is the address already committed as a test constant** (the one
``tests/test_live_contacts_resolve_colleague.py`` uses), so no new identity enters here — and it
is granted access to a document that exists for a few seconds and is then trashed.

**Gentle.** One round, one document, ~15 calls, every one through the client's own limiter. No
burst, no quota probe, and nothing is tried that the spike did not already measure.

**Skips loudly, never silently.** Without write credentials the whole gate skips with a message
naming exactly what is missing.

**It ships WITH its mirror.** Everything it claims *about itself* — the disposables-only
posture, the self-created subject, the teardown, the independent re-query, the read-back rule —
is exactly the class of claim a credential-less run "verifies" by not running, so it is verified
in ``test_live_drive_access_gate_offline.py`` on every plain ``pytest``.
"""
import time

import canary_support
import pytest

from larkdocio.common import get_write_credentials
from larkdocio.drive import ops as drive_ops
from larkdocio.drive.access import MEASURED_COPY_VALUES, MEMBER_PERMS
from larkdocio.drive.access_write import DriveAccessWriteClient
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.write.client import WriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The write app's tenant region — matches the toolkit's default OpenAPI domain. NOT a document
#: reference: this gate never addresses a file it did not create.
DOMAIN = "larksuite.com"

#: The grantee, by ADDRESS — already a committed test constant, resolved through the shipped
#: contacts verb by the surface itself. No open_id is hard-coded here.
GRANTEE_EMAIL = "example.user@example.com"
#: LD-684: that address is a FAKE; the real grantee comes from the environment.
GRANTEE_ENV = "LARKDOCIO_LIVE_GRANTEE_EMAIL"


@pytest.fixture(scope="module", autouse=True)
def _real_grantee():
    """Rebind the grantee to the tenant's real address before any arm runs."""
    global GRANTEE_EMAIL
    GRANTEE_EMAIL = canary_support.live_identity(GRANTEE_ENV, "the live Drive access gate")

#: The level the sheet/base arm grants at — ``full_access``, **moved there by LD-577** and for a
#: measured reason, not a preference. This tenant's disposables folder already carries the
#: grantee at ``full_access``, and every object filed into it inherits that row at birth
#: (:data:`~larkdocio.drive.access.MEMBER_LIST_AT_BIRTH`). A ``view`` *grant* against a member
#: already inherited higher was measured **2026-08-26** reading back ``full_access`` —
#: ``('view', 'full_access', stored=False)`` on both the sheet and the Base — so asking for
#: ``view`` on the ADD route here tests Lark's inheritance precedence rather than the library.
#: The level-change claim did not move with it: it is carried by ``update_access``, whose
#: read-back is unambiguous because **nothing inherited reads back as the level this run asked
#: for** (the docx arm's ``view`` then ``edit``, and the Base arm's ``edit``).
GRANT_PERM = "full_access"

#: The level each type arm's UPDATE leg asks for — **the one member write on that arm whose
#: read-back no inherited row can satisfy** (LD-577 fix round). ``view`` for the spreadsheet
#: because the folder confers ``full_access``; ``edit`` for the Base, which is the level that
#: arm has always claimed. Per kind, so neither arm can be left with only the ADD route.
UPDATE_PERM = {"sheets": "view", "base": "edit"}


def _delta(before, after):
    """The member rows ``after`` carries that ``before`` did not.

    The one place an arm's *added-rows* verdict is computed, now that birth is **not** empty
    here (LD-577, § THE FOUNDING PREMISE above). Rows are ``(member_id, perm)`` pairs read back
    from Lark, so a level change shows up as a delta too.
    """
    return sorted(set(after) - set(before))


def _perm_of(rows, member_id):
    """The level ``member_id`` reads at in ``rows``, or ``None`` if it holds no row at all."""
    return next((perm for mid, perm in rows if mid == member_id), None)


def _others(rows, member_id):
    """Everyone but ``member_id``. An arm asked about one grantee, so this is what must NOT
    move — the other half of the delta claim, and the one that catches a write reaching past
    its subject."""
    return sorted((mid, perm) for mid, perm in rows if mid != member_id)


def test_the_registry_declares_the_ACCESS_OPS_MUTATING_before_anything_is_called():
    """Asserted **before** the first call, so a mis-declared op fails here rather than against
    a real tenant. The member READ declares ``False`` beside four writes that declare ``True``
    — the declaration, not the verb, is what says so."""
    assert drive_ops.op("list_members").mutates is False
    for name in ("grant_access", "update_access", "revoke_access", "set_copy_permissions"):
        assert drive_ops.op(name).mutates is True, name
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS) is True


def test_the_grant_lifecycle_round_trips_on_a_disposable_this_run_created(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    app_id, app_secret = get_write_credentials()
    wc = WriteClient(app_id, app_secret, DOMAIN)
    access = DriveAccessWriteClient(app_id, app_secret, DOMAIN)

    nonce = str(int(time.time()))
    row = {"file_token": None, "members_at_birth": None, "owner_at_birth": None,
           "granted": None, "members_after_grant": None, "raised": None, "lowered": None,
           "revoked": None, "members_after_revoke": None, "copy_baseline": None,
           "copy_stored": None, "file_absent_after_delete": None}

    ledger = []
    try:
        dest_folder = canary_support.require_disposables_folder()
        doc = wc.create_document(title=f"larkdocio-access-gate {nonce}",
                                 folder_token=dest_folder)
        doc_id = doc["document_id"]
        ledger.append((doc_id, "file_absent_after_delete"))
        row["file_token"] = doc_id

        # (0) BIRTH: whatever membership this tenant confers on a document filed into a folder
        # — RECORDED, never assumed empty (LD-577, § THE FOUNDING PREMISE) — and an owner who
        # is not among those rows.
        birth = access.list_members(doc_id)
        row["members_at_birth"] = [(m.member_id, m.perm) for m in birth.members]
        row["owner_at_birth"] = birth.owner_id

        # (1) GRANT the manage level, by EMAIL, through the shipped resolver. The op's own
        # read-back listing is the other end of the delta this arm asserts.
        granted = access.grant_access(doc_id, email=GRANTEE_EMAIL, perm="full_access")
        row["granted"] = (granted.open_id, granted.requested_perm, granted.stored_perm,
                          granted.stored)
        row["members_after_grant"] = [(m.member_id, m.perm) for m in granted.listing.members]

        # (2) LOWER, then RAISE — one route, both directions, each judged by a read.
        lowered = access.update_access(doc_id, open_id=granted.open_id, perm="view")
        row["lowered"] = (lowered.stored_perm, lowered.stored)
        raised = access.update_access(doc_id, open_id=granted.open_id, perm="edit")
        row["raised"] = (raised.stored_perm, raised.stored)

        # (3) THE COPY LEVER: the baseline first (so the change is a change), then both keys.
        row["copy_baseline"] = None
        copy = access.set_copy_permissions(doc_id, copy_entity="anyone_can_view",
                                          security_entity="anyone_can_view")
        row["copy_baseline"] = {k: copy.public.get(k) for k in
                                ("copy_entity", "security_entity", "lock_switch")}
        row["copy_stored"] = [(s.key, s.requested, s.stored) for s in copy.settings]

        # (4) REVOKE — and the member list must be back to its BIRTH membership, with no
        # tombstone left where the grant was.
        revoked = access.revoke_access(doc_id, open_id=granted.open_id)
        row["revoked"] = (revoked.stored_perm, revoked.stored)
        row["members_after_revoke"] = [(m.member_id, m.perm)
                                       for m in revoked.listing.members]

        print(f"[access gate {nonce}] {row}")
    finally:
        for token, key in ledger:
            try:
                wc.delete_document(token)
            except Exception as exc:            # pragma: no cover - teardown must not mask
                row[f"{key}_delete_error"] = str(exc)
            # ZERO ORPHANS, verified INDEPENDENTLY: re-query and require Lark to say it is gone.
            try:
                wc.get_document(token)
                row[key] = False
            except LarkAPIError:
                row[key] = True
        with capsys.disabled():
            print(f"[access gate close-out] {row}")

    grantee = row["granted"][0]
    assert row["members_at_birth"] is not None, (
        "the birth member read never happened — every delta below has no baseline")
    assert row["owner_at_birth"], (
        "the owner read came back empty — a document nobody owns is not what was measured")
    assert row["granted"][2] == "full_access" and row["granted"][3] is True, (
        f"the grant did not STORE (code 0 is not storage): {row['granted']!r}")
    assert _perm_of(row["members_after_grant"], grantee) == "full_access", (
        "the grantee does not READ at the level that was granted: "
        f"after_grant={row['members_after_grant']!r}")
    assert _others(row["members_after_grant"], grantee) == _others(row["members_at_birth"],
                                                                  grantee), (
        "the grant moved a member it was never asked about — a write reaching past its own "
        f"subject: birth={row['members_at_birth']!r} after={row['members_after_grant']!r}")
    # The level-change legs are where a DIRECT member write is unambiguous: birth may already
    # carry the grantee at full_access (inherited), but nothing inherited reads back as view.
    assert row["lowered"] == ("view", True), row["lowered"]
    assert row["raised"] == ("edit", True), row["raised"]
    assert row["copy_stored"] == [("copy_entity", "anyone_can_view", "anyone_can_view"),
                                  ("security_entity", "anyone_can_view", "anyone_can_view")], (
        f"a copy-lever key did not store: {row['copy_stored']!r}")
    assert row["revoked"] == (None, True), row["revoked"]
    assert _perm_of(row["members_after_revoke"], grantee) is None, (
        "the revoke left the grantee holding a row — a tombstone by another name: "
        f"{row['members_after_revoke']!r}")
    assert _others(row["members_after_revoke"], grantee) == _others(row["members_at_birth"],
                                                                   grantee), (
        "the revoke took somebody else's access with it: "
        f"birth={row['members_at_birth']!r} after_revoke={row['members_after_revoke']!r}")
    assert _delta(row["members_at_birth"], row["members_after_revoke"]) == [], (
        "the lifecycle ADDED a row that birth did not have and the revoke did not take back: "
        f"{_delta(row['members_at_birth'], row['members_after_revoke'])!r}")
    assert row["file_absent_after_delete"] is True, "the disposable survived its delete"
    assert set(MEMBER_PERMS) == {"view", "edit", "full_access"}
    assert "anyone_can_view" in MEASURED_COPY_VALUES


def test_the_grant_reaches_a_BASE_and_a_SPREADSHEET_and_the_old_docx_default_still_refuses(
        capsys):
    """LD-456's AC2 — **the measurement the docx-only row was missing.**

    The earlier row said *docx only*, and its reason was that every measurement had been made
    with ``type=docx``. This arm makes the other two, on objects it creates in this run and
    tears down: a **spreadsheet** (``type=sheet``) and a **Base** (``type=bitable``), each put
    through the same lifecycle the docx arm above proves, and each judged by the **read-back**
    rather than by ``code: 0``.

    **Its own control rides along**: the same freshly minted token addressed at the DEFAULT
    type reproduces the exact consumer failure that earned this widening — Lark's
    ``1063001 Invalid parameter`` — and this gate asserts the library now says what that means
    instead of relaying it bare. A green offline suite cannot tell you either half.

    **Disposables only (D-12).** The spreadsheet is created here and deleted in the same
    ``finally``; the Base rides the disposable-Base harness, whose ledgered teardown and
    ``close_out`` sweep are what a Base's measured delete lag needs. Zero orphans is asserted,
    not assumed.
    """
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    import base_write_harness as base_harness

    app_id, app_secret = get_write_credentials()
    access = DriveAccessWriteClient(app_id, app_secret, DOMAIN)
    sheets = SheetsWriteClient.from_write_credentials(DOMAIN)

    nonce = str(int(time.time()))
    row = {"sheet": {}, "base": {}, "orphans": None, "sheet_deleted": None}

    book_token = None
    try:
        dest_folder = canary_support.require_disposables_folder()
        book = sheets.create_spreadsheet(base_harness.disposable_title(f"access-sheet-{nonce}"),
                                         folder_token=dest_folder)
        book_token = book["spreadsheet_token"]
        assert book_token, f"the create returned no spreadsheet token: {book!r}"
        row["sheet"] = _type_arm(access, book_token, obj_type="sheets",
                                 update_perm=UPDATE_PERM["sheets"])

        with base_harness.disposable_base(nonce=f"access-base-{nonce}") as (app_token, _t, _n):
            row["base"] = _type_arm(access, app_token, obj_type="base",
                                    update_perm=UPDATE_PERM["base"])
    finally:
        if book_token:
            try:
                sheets.delete_spreadsheet(book_token)
                row["sheet_deleted"] = True
            except Exception as exc:       # pragma: no cover - teardown must not mask
                row["sheet_deleted"] = f"delete failed: {exc}"
        row["orphans"] = base_harness.close_out()
        with capsys.disabled():
            print(f"[access type gate close-out {nonce}] {row}")

    for kind in ("sheet", "base"):
        arm = row[kind]
        grantee = arm["granted"][0]
        assert arm["members_at_birth"] is not None, (
            f"the {kind}'s birth member read never happened — the delta has no baseline")
        assert arm["owner"], f"the {kind}'s owner read came back empty"
        assert arm["granted"][2] == GRANT_PERM and arm["granted"][3] is True, (
            f"the {kind} grant did not STORE (code 0 is not storage): {arm['granted']!r}")
        assert _perm_of(arm["members_after_grant"], grantee) == GRANT_PERM, (
            f"the {kind}'s grantee does not READ at the level granted: "
            f"after_grant={arm['members_after_grant']!r}")
        # THE UNAMBIGUOUS MEMBER WRITE (LD-577 fix round). The assertion above is
        # inheritance-confounded — the folder already carries this grantee at full_access — so
        # each arm also asks for a level NOTHING INHERITED reads back as, and a swallow reddens.
        assert arm["moved"] == (arm["update_asked"], True), (
            f"the {kind}'s level change did not STORE: asked {arm['update_asked']!r}, read back "
            f"{arm['moved']!r} — the one member write on this arm inheritance cannot satisfy")
        assert _others(arm["members_after_grant"], grantee) == _others(arm["members_at_birth"],
                                                                      grantee), (
            f"the {kind} grant moved a member it was never asked about: "
            f"birth={arm['members_at_birth']!r} after={arm['members_after_grant']!r}")
        assert arm["revoked"] == (None, True), arm["revoked"]
        assert _perm_of(arm["members_after_revoke"], grantee) is None, (
            f"the {kind} revoke left the grantee holding a row: "
            f"{arm['members_after_revoke']!r}")
        assert _others(arm["members_after_revoke"], grantee) == _others(
            arm["members_at_birth"], grantee), (
            f"the {kind} revoke took somebody else's access with it: "
            f"birth={arm['members_at_birth']!r} after_revoke={arm['members_after_revoke']!r}")
        assert _delta(arm["members_at_birth"], arm["members_after_revoke"]) == [], (
            f"the {kind} lifecycle added a row birth did not have: "
            f"{_delta(arm['members_at_birth'], arm['members_after_revoke'])!r}")
        # THE CONTROL: the dogfood failure, reproduced — and now answered in the library's own
        # voice rather than as a bare Lark code.
        assert "1063001" in arm["as_docx"], (
            f"the {kind} addressed as docx did not reproduce the reported failure: "
            f"{arm['as_docx']!r}")
        assert "obj_type" in arm["as_docx"], (
            "Lark's bare 1063001 reached the caller with no library voice — the whole defect")

    assert row["sheet_deleted"] is True, "the disposable spreadsheet survived its delete"
    assert row["orphans"] == [], f"the Base teardown left survivors: {row['orphans']!r}"


def _type_arm(access, token, *, obj_type, update_perm):
    """One object type's whole lifecycle, judged by reads. Returns the evidence row.

    Birth membership is **recorded, not assumed empty** (LD-577, § THE FOUNDING PREMISE) — a
    spreadsheet and a Base filed into the disposables folder inherit its rows exactly as the
    document does.

    ``update_perm`` has **no default on purpose** (LD-577 fix round): the ADD-route read-back is
    inheritance-confounded here, so the level change is this arm's only unambiguous member write
    and an arm added later must name the level it asks for rather than inherit a skip.
    """
    arm = {}
    birth = access.list_members(token, obj_type=obj_type)
    arm["members_at_birth"] = [(m.member_id, m.perm) for m in birth.members]
    arm["owner"] = birth.owner_id

    granted = access.grant_access(token, email=GRANTEE_EMAIL, perm=GRANT_PERM,
                                  obj_type=obj_type)
    arm["granted"] = (granted.open_id, granted.requested_perm, granted.stored_perm,
                      granted.stored)
    arm["members_after_grant"] = [(m.member_id, m.perm) for m in granted.listing.members]
    arm["update_asked"] = update_perm
    moved = access.update_access(token, open_id=granted.open_id, perm=update_perm,
                                 obj_type=obj_type)
    arm["moved"] = (moved.stored_perm, moved.stored)
    revoked = access.revoke_access(token, open_id=granted.open_id, obj_type=obj_type)
    arm["revoked"] = (revoked.stored_perm, revoked.stored)
    arm["members_after_revoke"] = [(m.member_id, m.perm) for m in revoked.listing.members]

    try:
        access.list_members(token, with_owner=False)
        arm["as_docx"] = "ACCEPTED — the default type reached an object of another kind"
    except LarkAPIError as exc:
        arm["as_docx"] = str(exc)
    return arm
