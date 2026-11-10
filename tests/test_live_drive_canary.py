"""THE R1 GATE — the read-only live Drive canary (LD-328).

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live

**What it is.** The Drive twin of the docx canary (LD-003), the Sheets canary (LD-106) and the
Base canary (LD-252): it enumerates one folder **twice back-to-back in one run** through the
shipped :class:`~larkdocio.drive.client.DriveClient` and asserts the two results are
**byte-identical**, so a Drive listing-API drift reddens the suite the way a docx / Sheets /
Base drift already does. It is what turns *"the Drive client passed its unit tests"* into
*"the one endpoint the whole rung stands on cannot change shape unseen"*. It is **not** the
small single read arm — that is ``tests/test_live_drive_enumeration_arm.py`` (LD-324), kept
deliberately cheap so this gate owns what live budget the tranche has.

**THE SUBJECT IS THE BOT'S OWN ROOT FOLDER, DISCOVERED LIVE (the Drive spec § D7), and the reason is
worth writing down.** Every other live gate in this project self-provisions its subject: it
creates a disposable, exercises it, deletes it. A Drive folder **cannot** be self-provisioned
here — ``create_folder`` is a **write** (R2/R3), and Drive writes are **permanent**: no purge
verb exists anywhere in ``drive/v1``, so a folder this gate created would be irreversible
tenant residue on every run. So the canary's subject must be something that **already exists
and costs nothing** — the bot's **own root folder**, resolved live via
``GET /open-apis/drive/explorer/v2/root_folder/meta`` (LD-324's raw leg): no env var required,
no grant, no write, no maintainer resource. The maintainer's real folder is **never a hard dependency**.

**An OPTIONAL maintainer-designated folder, and it skips LOUDLY (AC2).**
``LARKDOCIO_CANARY_FOLDER`` (documented in ``.env.example``) **overrides** the subject when
set. Unset ⇒ the bot's own root (above). Set-and-reachable ⇒ that folder. Set-but-unreachable
⇒ **SKIP with a clear message naming the variable and the refusal** — never a failure, never a
silent pass. A folder's contents legitimately change, so the override is a convenience, never
a contract.

**SAME-RUN determinism, never cross-time.** The two enumerations run back-to-back and must be
byte-identical — a real property of the client on one run. **Cross-time identity is NOT
claimed**, and there is no committed expected-output file on purpose: a folder's contents
legitimately **change** between runs (another user adds a file), so a cross-time assertion would
be a false gate that reddens on someone else's edit rather than on a drift.

**READ-ONLY BY CONSTRUCTION, not by intention (AC3).** Every op in
:data:`larkdocio.drive.ops.OPS` declares ``mutates: False`` — asserted **before** the first
call, so a future write op cannot be smuggled onto this path — the declared verb set is
``GET`` plus exactly one query ``POST``, and the client resolves the **READ** pair only. There
is **no code path in this arm** that can move, copy, delete, upload, shortcut or rename
anything.

**Gentle, and HARD-BUDGETED (AC6).** Every call rides the client's own ``RateLimiter`` at the
spike's 1.2 s spacing, and a :class:`_BudgetLimiter` caps the whole run at
:data:`DRIVE_CANARY_CALL_BUDGET` calls and **raises rather than exceeds** — the probes' own
discipline (budgets of 6 and 20). Rate limits are documented, never probed (the LD-100
posture).

**No capture of a real tree is committed (AC9).** The simplest compliant answer is to commit
no capture at all, and this arm chose it: it reads live, asserts, and writes nothing to disk —
so no real tenant token or signed URL can leak through a committed artifact.

**Skips loudly, never silently (AC7).** Without read credentials the whole gate skips with a
message naming exactly what is missing, so a credential-less ``pytest -q`` stays green without
ever reading as a pass.
"""
import hashlib

import canary_support
import pytest

from larkdocio.drive import ops as drive_ops
from larkdocio.drive.client import DRIVE_MIN_REQUEST_SPACING_SECONDS, DriveClient
from larkdocio.drive.dispatch import DISPATCH, UNKNOWN, dispatch
from larkdocio.drive.errors import DriveObjectNotFoundError, FolderRefusedError
from larkdocio.drive.models import CHILD_FIELDS
from larkdocio.common.transport import RateLimiter

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

canary_support.load_env()

#: The hard live call budget. The two probe rounds ran under budgets of 6 and 20; this gate
#: needs only a handful — resolve the root (≤1) + two enumerations (2) + one malformed-token
#: refusal (1) = 4 — so 6 leaves headroom without licensing a runaway. A leg added past this
#: raises :class:`DriveCanaryBudgetExceeded` rather than silently spending more.
DRIVE_CANARY_CALL_BUDGET = 6

#: A deliberately malformed folder token — a read, safe, and the cheapest possible drift alarm
#: for the family's ``1061002`` catch-all (AC5). Not a real token, and not the shape of one.
_MALFORMED_TOKEN = "larkdocio-not-a-real-folder-token"


class DriveCanaryBudgetExceeded(RuntimeError):
    """Raised when the canary would spend more than :data:`DRIVE_CANARY_CALL_BUDGET` calls —
    the budget is an assertion enforced at the send seam, not a hope (AC6)."""


class _BudgetLimiter(RateLimiter):
    """A :class:`RateLimiter` that also caps the total number of acquisitions.

    Subclassing keeps the spike's 1.2 s pacing (the ceiling is added ON TOP of it, never
    instead), and placing the count in ``acquire`` — which the client calls once per request
    *before* the send — makes the budget fire **before** the over-budget call reaches the wire.
    """

    def __init__(self, budget, **kwargs):
        super().__init__(**kwargs)
        self._budget = budget
        self.acquired = 0

    def acquire(self):
        if self.acquired >= self._budget:
            raise DriveCanaryBudgetExceeded(
                f"the Drive canary's live call budget of {self._budget} is exhausted; a leg "
                "was added without raising DRIVE_CANARY_CALL_BUDGET")
        self.acquired += 1
        super().acquire()


def make_budget_limiter(budget=DRIVE_CANARY_CALL_BUDGET):
    """The budget-capped limiter the canary injects — one per 1.2 s, capped at ``budget``."""
    return _BudgetLimiter(budget, max_per_sec=1, window=DRIVE_MIN_REQUEST_SPACING_SECONDS)


def missing_reason():
    """Why this gate cannot run, or ``None`` — the skip message, so absence is never silence."""
    if not canary_support.read_creds_available():
        return (
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET (or the "
            "legacy LARK_APP_ID/LARK_APP_SECRET) to run the live Drive canary (THE R1 GATE)."
        )
    return None


def tenant_domain():
    """The API domain to talk to — taken from the canary doc's URL when one is configured (so
    a ``feishu.cn`` tenant is not addressed at ``larksuite.com``), else the package default.

    The canary doc is used **only** as a domain hint; this gate never reads it.
    """
    raw = canary_support.canary_doc_url()
    if not raw:
        return "larksuite.com"
    try:
        from larkdocio.common import validate_download_url

        return validate_download_url(raw)[0]
    except Exception:  # noqa: BLE001 - a malformed hint must not fail the gate
        return "larksuite.com"


def canary_folder_override():
    """The OPTIONAL ``LARKDOCIO_CANARY_FOLDER`` subject, or ``None`` (⇒ the bot's own root)."""
    return canary_support.canary_folder_override()


def resolve_subject(client, override):
    """The folder token to enumerate: the override when set, else the bot's OWN root folder
    discovered live (the Drive spec § D7). A set override never spends a call on ``root_folder/meta``.
    """
    if override is not None:
        return override
    return client.root_folder_token()


def enumerate_twice_or_skip(client, override):
    """Resolve the subject and enumerate it **twice back-to-back**; return ``(subject, first,
    second)``.

    A set-but-unreachable override is Lark's ``1061002`` (or the family's ``1061003``); when
    the **override** is set that is a SKIP naming the variable — never a failure — because the
    Maintainer's designated folder is a convenience, not a contract (AC2). With **no** override the
    subject is the bot's own root, and a refusal there is a genuine failure, so it propagates.
    """
    subject = resolve_subject(client, override)
    try:
        first = client.list_folder_children(subject)
    except (FolderRefusedError, DriveObjectNotFoundError) as exc:
        if override is not None:
            pytest.skip(
                f"{canary_support.CANARY_FOLDER_ENV} is set to {override!r} but Lark refused "
                f"it, so the maintainer-designated canary folder is unreachable: {exc}. Skipping "
                "loudly rather than failing — the override is optional (AC2)."
            )
        raise
    second = client.list_folder_children(subject)
    return subject, first, second


def _serialize(contents):
    """A stable byte-string of a folder listing — every child's declared fields in order, plus
    the paging shape. Two same-run enumerations must produce identical bytes (AC4)."""
    lines = [f"folder_token={contents.folder_token!r}",
             f"has_more={contents.has_more!r}",
             f"next_page_token={contents.next_page_token!r}"]
    for child in contents.children:
        lines.append("|".join(f"{field}={getattr(child, field)!r}" for field in CHILD_FIELDS))
    return "\n".join(lines).encode("utf-8")


# --------------------------------------------------------------------------- #
# AC3 — read-only BEFORE anything is read                                      #
# --------------------------------------------------------------------------- #


def test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_reads_anything():
    # TRANSFORMED, not deleted (LD-409, D-24): this arm touches ONLY the R1 enumeration legs,
    # and that set is still read-only. The whole-registry answer moved when create_version was
    # registered, so the claim is asserted at the scope the arm actually has — and the mutating
    # set is pinned too, so a SECOND write op cannot arrive on this path unnoticed.
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS), (
        "a mutating op reached the Drive registry; this gate runs against a real tenant and "
        "must not be the thing that discovers that")
    # LD-432 widened the registry's verb set (the access family declares PUT, DELETE and
    # PATCH), so the claim is asserted at the scope this arm actually has: the ENUMERATION's
    # own declared verbs. Nothing this arm calls can be anything but a GET or one of the
    # declared query POSTs.
    assert sorted({d.http_method for d in drive_ops.ENUMERATION_OPS}) == ["GET", "POST"]
    # TRANSFORMED, not bumped (LD-487): document_security_level joined folder_name on the
    # metas/batch_query endpoint, so the declared-read POST set is two rather than one. The
    # REASON is unchanged — a documented query POST must be VISIBLY declared a read, or the
    # registry classifies it as a write — so the set is pinned by NAME and every member must
    # declare mutates is False. A THIRD declared-read POST reddens this gate instead of
    # silently joining a count.
    query_posts = {d.name: d for d in drive_ops.query_posts()}
    assert set(query_posts) == {"folder_name", "document_security_level"}
    assert all(d.mutates is False for d in query_posts.values())


# --------------------------------------------------------------------------- #
# THE GATE                                                                     #
# --------------------------------------------------------------------------- #


def test_the_R1_gate_enumerates_the_subject_twice_and_is_byte_identical(capsys):
    # Load the repo .env (local runs) — a no-op where creds are already injected. Then skip
    # LOUDLY if we cannot run: never a silent pass (AC7).
    canary_support.load_env()
    reason = missing_reason()
    if reason:
        pytest.skip(reason)

    domain = tenant_domain()
    override = canary_folder_override()

    # One client, one limiter, one budget for the whole gate — so the budget spans every leg.
    client = DriveClient.from_read_credentials(domain, rate_limiter=make_budget_limiter())

    subject, first, second = enumerate_twice_or_skip(client, override)
    assert subject, "no folder token resolved — neither an override nor the bot's own root"

    # --- AC5: the shape the whole rung stands on. A brand-new tenant's root can legitimately
    #     be empty, so the per-child assertions are vacuous rather than false when there are
    #     no children — what must hold is that whatever came back is the shape claimed. ---
    for child in first.children:
        assert child.token, "a child arrived with no token"
        assert child.url, (
            f"child {child.token!r} arrived with no url — the field the docx reader depends "
            "on (9/9 and 27/27 in the spike)")
        for field in CHILD_FIELDS:
            assert hasattr(child, field), field
        # A known type routes to a reader; an unknown one is DISCLOSED, never crashed on.
        outcome = dispatch(child)
        if child.type in DISPATCH:
            assert outcome.kind != UNKNOWN, (
                f"child type {child.type!r} is in the dispatch table yet routed to UNKNOWN")
        else:
            assert outcome.kind == UNKNOWN and outcome.reason, (
                f"child type {child.type!r} is unknown but was not disclosed with a marker")

    assert first.has_more in (True, False), "has_more is not a well-typed boolean"
    assert first.next_page_token is None or isinstance(first.next_page_token, str), (
        "next_page_token is neither absent nor a string")

    # --- AC4: THE GATE. Same-run byte-identity. ---
    first_bytes = _serialize(first)
    second_bytes = _serialize(second)
    assert first_bytes == second_bytes, (
        "the Drive enumeration is non-deterministic: two back-to-back read-only enumerations "
        "of the same folder in the SAME RUN differ")

    # --- AC5: the 1061002 refusal still behaves as captured on a deliberately malformed token
    #     (a read, safe — the cheapest drift alarm for the family's catch-all). ---
    with pytest.raises(FolderRefusedError) as excinfo:
        client.list_folder_children(_MALFORMED_TOKEN)
    assert str(excinfo.value.code) == "1061002", (
        f"the malformed-token refusal drifted off 1061002: code={excinfo.value.code!r}")

    # --- AC6: gentle. The whole gate stayed inside its hard budget (which would otherwise
    #     have raised before overspending). ---
    assert client.api_calls <= DRIVE_CANARY_CALL_BUDGET, (
        f"the gate spent {client.api_calls} live calls; its budget is "
        f"{DRIVE_CANARY_CALL_BUDGET}")

    # --- The characterization IS the baseline. Visible under `pytest -m live -s`. ---
    digest = hashlib.sha256(first_bytes).hexdigest()
    with capsys.disabled():
        print(
            f"\n[drive-canary] subject={'override' if override else 'own-root'} "
            f"children={len(first.children)} "
            f"has_more={first.has_more} "
            f"types={sorted({c.type for c in first.children})} "
            f"bytes={len(first_bytes)} "
            f"sha256={digest} "
            f"deterministic={first_bytes == second_bytes} "
            f"live_calls={client.api_calls} "
            f"budget={DRIVE_CANARY_CALL_BUDGET}"
        )
