"""LD-348 live arm — ``resolve_colleague`` against the real tenant. ``@pytest.mark.live``.

**READ-ONLY, and structurally so.** Every call goes through
``ContactsSearchClient.batch_get_id``, which reaches exactly one endpoint:
``POST /open-apis/contact/v3/users/batch_get_id``. Nothing here writes, mutates, creates or
deletes anything. **No document, sheet or Base is touched. No scope is requested or widened.**
There is no scratch doc and no write credential.

**Paced.** Every arm shares ONE client, so the shipped limiter spaces the whole run.

**NO THIRD PARTY'S IDENTIFIER IS COMMITTED.** The owner's address and ``open_id`` in this file
are placeholders (``OWNER_EMAIL`` / ``OWNER_OPEN_ID``, below); the live values are read from the
environment. The second user's address is **read from the environment** — ``LD348_COLLEAGUE_EMAIL`` — and never
written to a file, a log line or an assertion message by this module; only its ``open_id``,
which is already committed, is compared. That is the slice-2 redaction precedent the spike
itself followed.

**Skips loudly, never silently.** An unset credential or an unset user address is a
``pytest.skip`` naming the exact variable to set. Nothing here passes by doing nothing.

**A failure here is a FINDING, not a bug.** If the route stops resolving, the endpoint was
withdrawn or the reach changed, that is the measurement moving — record it, do not "fix" it.
"""
import os
import re

import pytest

import canary_support
from larkdocio.contacts import ContactsSearchClient, resolve_colleague
from larkdocio.contacts.lookup import (
    MEASURED_REACH,
    UNRESOLVED_IS_UNDIFFERENTIATED,
)
from larkdocio.write.model.refusal import RefusalReason

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The account owner. Both halves are already in the committed record, so both are verbatim.
OWNER_EMAIL = "example.user@example.com"
OWNER_OPEN_ID = "ou_exampleowner00000000000000000001"

#: The second user B3 resolved. **The ID only** — their address is never committed.
SECOND_USER_OPEN_ID = "ou_examplesecond0000000000000000001"

#: The environment variable carrying the second user's real address for this arm.
SECOND_USER_ENV = "LD348_COLLEAGUE_EMAIL"

#: The fake-email control. ``.invalid`` is reserved by RFC 2606 and can never be a real domain,
#: so this is a synthetic address by construction rather than by hope.
NOWHERE_EMAIL = "nobody.does.not.exist@example.invalid"

#: LD-684: OWNER_EMAIL, OWNER_OPEN_ID and SECOND_USER_OPEN_ID above are FAKES. The real values come
#: from the environment, and the arms skip loudly without them.
OWNER_EMAIL_ENV = "LARKDOCIO_LIVE_OWNER_EMAIL"
OWNER_ENV = "LARKDOCIO_LIVE_OWNER_OPEN_ID"
SECOND_USER_ID_ENV = "LARKDOCIO_LIVE_COLLEAGUE_OPEN_ID"


@pytest.fixture(scope="module", autouse=True)
def _real_identities():
    """Rebind the module's identities to the tenant's real ones before any arm runs."""
    global OWNER_EMAIL, OWNER_OPEN_ID, SECOND_USER_OPEN_ID
    why = "the live resolve_colleague arm"
    OWNER_EMAIL = canary_support.live_identity(OWNER_EMAIL_ENV, why)
    OWNER_OPEN_ID = canary_support.live_identity(OWNER_ENV, why)
    SECOND_USER_OPEN_ID = canary_support.live_identity(SECOND_USER_ID_ENV, why)


@pytest.fixture(scope="module")
def client():
    canary_support.load_env()
    if not canary_support.read_creds_available():
        pytest.skip(
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET (or the legacy "
            "LARK_APP_ID/LARK_APP_SECRET) to run the live resolve_colleague arm. This arm is "
            "READ-ONLY and needs no write credential.")
    return ContactsSearchClient.from_read_credentials()


@pytest.fixture(scope="module")
def second_user_email():
    canary_support.load_env()
    address = (os.environ.get(SECOND_USER_ENV) or "").strip()
    if not address:
        pytest.skip(
            f"{SECOND_USER_ENV} is unset, so the OTHER USER half of AC8 cannot run. Set it to one "
            "real user address on this tenant. It is deliberately NOT committed: a third "
            "party's live identifier does not enter this repository, and the arm skips loudly "
            "rather than quietly reducing itself to the owner-only case.")
    return address


# --------------------------------------------------------------------------- #
# (a) the OWNER's address resolves to the owner's ou_…                          #
# --------------------------------------------------------------------------- #

def test_ac8a_the_owners_email_resolves_to_the_owners_open_id(client):
    answer = resolve_colleague(email=OWNER_EMAIL, client=client)
    assert answer.resolved, (
        "the owner's own address no longer resolves. If the endpoint was withdrawn or the "
        "grant changed this is a FINDING, not a bug — see this module's docstring. Refusal: "
        f"{answer.refusal.reason.value}: {answer.refusal.detail}")
    assert answer.user.open_id == OWNER_OPEN_ID
    assert answer.query == OWNER_EMAIL
    assert not answer.partiality.is_partial


# --------------------------------------------------------------------------- #
# (b) ONE OTHER USER's address resolves to a DIFFERENT ou_…                      #
# --------------------------------------------------------------------------- #

def test_ac8b_a_second_users_email_resolves_to_a_DIFFERENT_open_id(client, second_user_email):
    """The whole reason this feature exists, re-proved live: another user **no other route in
    this library reaches** — absent from the app's contacts data range and unreachable via the
    directory search — comes back from this one.

    The address never appears in this test's output: every assertion message below names ids
    and shapes only.
    """
    answer = resolve_colleague(email=second_user_email, client=client)
    assert answer.resolved, (
        "the second user address supplied in the environment did not resolve. That is a "
        "measurement, not a bug: read the refusal for what it does and does not establish "
        f"({answer.refusal.reason.value if answer.refusal else 'n/a'})")
    assert answer.user.open_id == SECOND_USER_OPEN_ID, (
        "the second user address resolved to an open_id other than the one B3 recorded — either "
        "a different user was supplied, or the mapping moved")
    assert answer.user.open_id != OWNER_OPEN_ID, "reach beyond the owner is the whole finding"
    assert not answer.partiality.is_partial


# --------------------------------------------------------------------------- #
# (c) the FAKE-EMAIL CONTROL — unresolved, key OMITTED, and AC2's refusal.      #
# --------------------------------------------------------------------------- #

def test_ac8c_the_fake_email_control_is_UNRESOLVED_with_the_user_id_key_OMITTED(client):
    """The undifferentiated shape, live. The raw body is read off the client so the OMISSION
    is checked on the wire and not through the reader that already interprets it."""
    data = client.batch_get_id(emails=[NOWHERE_EMAIL])
    rows = list(getattr(data, "user_list", None) or ())
    assert len(rows) == 1, f"the control returned {len(rows)} rows, not one"
    assert getattr(rows[0], "user_id", None) is None, (
        "an address that exists nowhere came back WITH an id — the unresolved shape has "
        "changed and every claim built on it must be re-derived")

    answer = resolve_colleague(email=NOWHERE_EMAIL, client=client)
    assert not answer.resolved
    assert answer.refusal.reason is RefusalReason.NOT_FOUND
    assert UNRESOLVED_IS_UNDIFFERENTIATED in answer.refusal.detail, (
        "the live refusal must carry the dual truth verbatim, not a paraphrase of it")
    assert MEASURED_REACH in answer.refusal.detail
    assert answer.partiality.is_partial, "an unresolved input is a partiality, not a clean no"


# --------------------------------------------------------------------------- #
# The posture: paced, read-only, and no third-party identifier in this file.    #
# --------------------------------------------------------------------------- #

def test_the_live_arm_is_paced_by_the_shipped_limiter(client):
    assert client.limiter.window >= 1.2, (
        "this arm must never be tighter than the spike's observed-safe ~1.2 s spacing")


def test_NO_THIRD_PARTY_ADDRESS_IS_COMMITTED_IN_THIS_MODULE():
    """The redaction rule, asserted against this file's own bytes rather than promised in prose.

    The only committed address here is the OWNER's, which is already in the committed capture
    record. Any other address literal would be a third party's identifier entering the
    repository, which the slice-2 precedent forbids.
    """
    with open(__file__, encoding="utf-8") as handle:
        source = handle.read()
    addresses = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", source))
    assert addresses == {OWNER_EMAIL, NOWHERE_EMAIL}, sorted(addresses)
