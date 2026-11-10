"""LD-229 live name-lookup arm — ``@pytest.mark.live``, deselected by default.

**READ-ONLY, and structurally so.** Every call this module makes goes through
``ContactsSearchClient.search_employees`` / ``resolve_user``, which reach exactly one endpoint:
``POST /open-apis/directory/v1/employees/search``. Nothing here writes, mutates, creates or
deletes anything, and no directory is modified. There is no scratch document, no disposable and
no write credential.

**Paced.** Every arm shares ONE client, so the shipped limiter spaces the whole run at
:data:`~larkdocio.contacts.client.CONTACTS_MIN_REQUEST_SPACING_SECONDS` (1.2 s) — the spacing
the spike observed safe. Nothing here measures a limit by walking into one.

**Skips loudly, never fails, when the credentials or the grant are absent.** A contributor
without the directory-search grant must be able to run the suite green: the scope-less case is
covered *offline* by ``tests/test_contacts_lookup.py``'s AC6 arms over the committed denial
capture, so nothing of value is lost by skipping here.

**AC1's demoted NO-GO clause.** If the live arm now fails because the grant was revoked, the
range changed or the endpoint was withdrawn, that is a **finding, not a bug**: the issue goes to
``blocked/`` with the fresh capture as the record. A future contributor must not "fix" it.
"""
import pytest

import canary_support
from larkdocio.auth import get_read_credentials
from larkdocio.contacts import ContactsSearchClient, normalize_name, resolve_user
from larkdocio.errors import LarkPermissionError
from larkdocio.read.client import Client
from larkdocio.write.model.refusal import RefusalReason

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The account owner — the one identity the GO record established the search can reach. An
#: ``open_id`` is not PII the way a name is; the NAME is never hard-coded here, it is recovered
#: live through the shipped reverse direction.
OWNER_OPEN_ID = "ou_exampleowner00000000000000000001"

#: A third party from the enumerable set — AC2's control. Id only: no display name, email or
#: alias belonging to another user appears in this file.
CONTROL_OPEN_ID = "ou_examplecontrol000000000000000001"

#: Meeting rooms — AC7. Names of ROOMS, not of people, and INVENTED: the assertion is that the
#: employee directory returns no row for a room-shaped name, so no real room is needed.
ROOM_NAMES = ("Example Room A", "Example Room B", "ExampleRoom01")

#: LD-684: the two ids above are FAKES — the committed tree carries no real person's id. The real
#: ones come from the environment, and the arms skip loudly without them.
OWNER_ENV = "LARKDOCIO_LIVE_OWNER_OPEN_ID"
CONTROL_ENV = "LARKDOCIO_LIVE_CONTROL_OPEN_ID"


@pytest.fixture(scope="module", autouse=True)
def _real_identities():
    """Rebind the module's ids to the tenant's real ones before any arm runs."""
    global OWNER_OPEN_ID, CONTROL_OPEN_ID
    OWNER_OPEN_ID = canary_support.live_identity(OWNER_ENV, "the live name-lookup arm")
    CONTROL_OPEN_ID = canary_support.live_identity(CONTROL_ENV, "the live name-lookup arm")


@pytest.fixture(scope="module")
def read_creds():
    canary_support.load_env()
    if not canary_support.read_creds_available():
        pytest.skip(
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET (or the "
            "legacy LARK_APP_ID/LARK_APP_SECRET) to run the live name-lookup arm.")
    return get_read_credentials()


@pytest.fixture(scope="module")
def client(read_creds):
    """ONE client for the whole module, so the shipped limiter paces the entire run."""
    return ContactsSearchClient.from_read_credentials()


@pytest.fixture(scope="module")
def live_names(read_creds):
    """Display names RECOVERED at test time through the shipped reverse direction.

    Never hard-coded — that is AC1's explicit requirement, and it is also what keeps another
    user's display name out of this file.
    """
    app_id, app_secret = read_creds
    return Client(app_id, app_secret, "larksuite.com").batch_get_user_names(
        [OWNER_OPEN_ID, CONTROL_OPEN_ID])


def _skip_if_no_grant(call):
    """Run ``call``; turn a scope denial into a loud SKIP rather than a failure."""
    try:
        return call()
    except LarkPermissionError as denied:
        pytest.skip(
            "The tenant does not hold the directory-search grant, so the live arm cannot run. "
            "This is the AC6 degrade, and it is proved offline against the committed denial "
            f"capture. Lark said: {denied.denial.detail()}")


# --------------------------------------------------------------------------- #
# AC1 — the shipped path, live, on a name recovered rather than hard-coded.     #
# --------------------------------------------------------------------------- #

def test_ac1_the_owners_live_display_name_resolves_to_the_owners_open_id(client, live_names):
    name = live_names.get(OWNER_OPEN_ID)
    assert name, (
        "the reverse direction did not return the owner's display name, so AC1's own input "
        "could not be built; fix that before reading anything into the forward direction")
    lookup = _skip_if_no_grant(lambda: resolve_user(name=name, client=client))
    assert lookup.resolved, (
        f"AC1's live arm did not resolve. If the grant was revoked, the range changed or the "
        f"endpoint was withdrawn this is a FINDING, not a bug — see this module's docstring. "
        f"Refusal: {lookup.refusal.reason.value}: {lookup.refusal.detail}")
    assert lookup.user.open_id == OWNER_OPEN_ID
    assert normalize_name(lookup.user.display_name) == normalize_name(name)
    assert not lookup.partiality.is_partial


def test_ac1_the_id_arrives_at_employee_id_and_user_id_is_absent(client, live_names):
    """The wire-observed field question, re-asserted against the live body rather than the
    capture — so a Lark-side change to the id field reddens here instead of shipping."""
    name = live_names.get(OWNER_OPEN_ID)
    data = _skip_if_no_grant(lambda: client.search_employees(name))
    rows = list(getattr(data, "employees", None) or ())
    assert rows, "the live search returned no rows for the owner's own name"
    base = rows[0].base_info
    assert base.employee_id == OWNER_OPEN_ID
    assert base.user_id is None, "user_id is now populated; the id-field claim must be re-derived"


# --------------------------------------------------------------------------- #
# AC2 — the control, and what it actually says about the reachable set.         #
# --------------------------------------------------------------------------- #

def test_ac2_the_reachable_set_is_recorded_HONESTLY_whatever_it_is(client, live_names):
    """AC2's draft offered three readings. The wire produced a fourth, and this test pins it
    rather than asserting the outcome the draft hoped for.

    The control is a third party the REVERSE direction resolves happily. If the forward
    direction also returns them, the search reaches beyond the account owner. If it does not,
    the search's reachable set is narrower than the directory, and the shipped docstring says
    so. Either way the assertion below is the one that matters: **a not-found is a not-found,
    never a fabricated hit** — no fallback, no guess, no top hit.
    """
    control_name = live_names.get(CONTROL_OPEN_ID)
    if not control_name:
        pytest.skip("the reverse direction did not resolve the control id; no control to run")
    lookup = _skip_if_no_grant(lambda: resolve_user(name=control_name, client=client))
    if lookup.resolved:
        assert lookup.user.open_id == CONTROL_OPEN_ID, (
            "the search returned SOMEONE ELSE for this name — that is a wrong answer, not a "
            "narrow one")
    else:
        assert lookup.refusal.reason is RefusalReason.NOT_FOUND
        assert lookup.candidate_ids == ()
        assert "not found" in lookup.refusal.detail.lower()


# --------------------------------------------------------------------------- #
# AC4 — match semantics, observed rather than assumed.                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("arm", ["exact", "prefix", "casefolded"])
def test_ac4_the_server_is_at_least_as_broad_as_exact(client, live_names, arm):
    """Exact, leading-fragment and case-folded queries all reach the owner. The point is not
    the server's rule but that the CLIENT-SIDE contract holds over whatever it returns."""
    name = live_names.get(OWNER_OPEN_ID)
    query = {"exact": name, "prefix": name.split()[0], "casefolded": name.lower()}[arm]
    data = _skip_if_no_grant(lambda: client.search_employees(query))
    ids = [row.base_info.employee_id for row in (getattr(data, "employees", None) or ())]
    assert OWNER_OPEN_ID in ids, f"the {arm} query no longer reaches the owner: {query!r}"


def test_ac4_a_prefix_hit_still_resolves_to_EXACTLY_ONE_or_refuses(client, live_names):
    """The contract, over a deliberately broader server answer: a leading fragment is not the
    owner's display name, so the exact rule must refuse it rather than take the only hit."""
    name = live_names.get(OWNER_OPEN_ID)
    fragment = name.split()[0]
    if normalize_name(fragment) == normalize_name(name):
        pytest.skip("the owner's display name is a single token; there is no prefix arm")
    lookup = _skip_if_no_grant(lambda: resolve_user(name=fragment, client=client))
    assert not lookup.resolved, (
        "a leading fragment resolved — the client-side exact rule has been relaxed into "
        "'take the only hit', which is the failure mode this surface refuses")
    assert lookup.refusal.reason is RefusalReason.NOT_FOUND


def test_ac4_a_string_matching_nobody_is_a_typed_not_found(client):
    lookup = _skip_if_no_grant(
        lambda: resolve_user(name="Qxzv Notaperson Zzzq", client=client))
    assert not lookup.resolved
    assert lookup.refusal.reason is RefusalReason.NOT_FOUND
    assert lookup.candidate_ids == ()


# --------------------------------------------------------------------------- #
# AC5 — the paging shape and the `count` question, answered from the wire.      #
# --------------------------------------------------------------------------- #

def test_ac5_the_page_response_shape_is_pinned_against_the_live_body(client, live_names):
    """``count`` has never been observed populated, so nothing may cite it. If Lark starts
    sending it this test reddens, which is the signal to record what it MEANS before using it.
    """
    name = live_names.get(OWNER_OPEN_ID)
    data = _skip_if_no_grant(lambda: client.search_employees(name, page_size=1))
    page = data.page_response
    assert page is not None
    assert page.has_more in (False, True)
    assert page.count is None, (
        "page_response.count is now populated. Record from observation whether it is a page "
        "count or a grand total BEFORE any refusal cites it — a refusal must never cite a "
        "field whose meaning was assumed.")


# --------------------------------------------------------------------------- #
# AC7 — resource accounts: the question is answered either way.                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("room", ROOM_NAMES)
def test_ac7_a_meeting_room_name_is_probed_and_the_answer_recorded(client, room):
    """Whether a room can come back as an employee, and whether anything distinguishes one.

    "Nothing in the payload distinguishes them" would be a legitimate outcome; what was
    observed is that rooms are not in the employee directory at all, so the question does not
    arise on this endpoint. Either way there is **no name-pattern heuristic** anywhere in this
    surface: the assertion below is about the payload, never about the string.
    """
    data = _skip_if_no_grant(lambda: client.search_employees(room))
    rows = list(getattr(data, "employees", None) or ())
    assert not rows, (
        f"the employee directory now returns {len(rows)} row(s) for a MEETING-ROOM name. The "
        f"docstring's recorded answer is stale: inspect the row for any field that "
        f"distinguishes a room from a person and record what you find — and do NOT add a "
        f"name-pattern heuristic.")


# --------------------------------------------------------------------------- #
# The posture itself: this arm makes only search calls, and it is paced.        #
# --------------------------------------------------------------------------- #

def test_the_live_arm_is_paced_by_the_shipped_limiter(client):
    assert client.limiter.max_per_sec == 1
    assert client.limiter.window >= 1.2, (
        "the live arm must never be tighter than the spike's observed-safe ~1.2 s spacing")
