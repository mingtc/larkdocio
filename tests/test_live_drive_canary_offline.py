"""The always-on offline half of ``test_live_drive_canary`` (LD-328).

THE R1 GATE runs only with credentials and a network. Everything it *claims about itself* —
that it is read-only **by construction** rather than by intention, that its subject is the
bot's **own** root folder discovered live (never a self-provisioned folder, because a Drive
folder create is a **permanent write**, and never a maintainer's real tree as a hard dependency), that
its optional override skips **loudly** rather than failing when unreachable, that it pins
**same-run** byte-identity rather than a committed cross-time baseline, that it holds a **hard
call budget that raises rather than exceeds**, and that it skips loudly rather than passing
silently — is exactly the class of claim a credential-less run "verifies" by not running. So it
is verified **here**, statically and in-situ against fakes, on every plain ``pytest``.

Unlike the Base canary's companion this file **imports** the arm module (the LD-324 Drive
enumeration arm's precedent), because three of the arm's obligations — the three subject
branches (AC2) and the budget's *enforcement* (AC6) — are proven by driving the arm's own
functions against fakes, not by reading its text. Importing a ``@pytest.mark.live`` module runs
no live test; it only makes the arm's helpers callable offline.
"""
import ast
import json
from pathlib import Path

import canary_support
import pytest

import gate_registry as gr
from larkdocio.drive import ops as drive_ops
from larkdocio.drive.client import DriveClient
from larkdocio.drive.dispatch import DISPATCH
from larkdocio.drive.errors import FOLDER_REFUSED_CODE, folder_refused

import test_live_drive_canary as arm

_TESTS = Path(__file__).resolve().parent
_GATE = _TESTS / "test_live_drive_canary.py"

Skipped = pytest.skip.Exception


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_docstring():
    return ast.get_docstring(ast.parse(_GATE.read_text(encoding="utf-8"))) or ""


@pytest.fixture(scope="module")
def gate_body(gate_source, gate_docstring):
    """The arm minus its module docstring — what the arm *does*, not what it explains. The
    docstring is *required* (AC3) to name the write verbs this arm cannot perform, so a naive
    grep over the whole file would forbid the very sentence that records the rule."""
    return gate_source.replace(gate_docstring, "", 1)


# --------------------------------------------------------------------------- #
# Fakes — a DriveClient stand-in that counts and can be made to refuse         #
# --------------------------------------------------------------------------- #


class _FakeClient:
    """A stand-in for :class:`DriveClient` — records how it was called and, optionally,
    refuses a listing the way Lark's ``1061002`` does."""

    def __init__(self, *, root="ROOTTOKENxxxxxxxxxxxxxxxxx", refuse=False, contents=None):
        self._root = root
        self._refuse = refuse
        self._contents = contents
        self.root_calls = 0
        self.list_calls = 0
        self.listed_tokens = []

    def root_folder_token(self):
        self.root_calls += 1
        return self._root

    def list_folder_children(self, folder_token=None, **kw):
        self.list_calls += 1
        self.listed_tokens.append(folder_token)
        if self._refuse:
            raise folder_refused(folder_token)
        return self._contents


class _FakeResponse:
    def __init__(self, body):
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body


# --------------------------------------------------------------------------- #
# AC7 (partial) — deselected by default, and it skips LOUDLY                    #
# --------------------------------------------------------------------------- #


def test_the_arm_exists_and_is_marked_live(gate_source):
    assert "pytestmark = pytest.mark.live" in gate_source, (
        "the arm must be deselected by default; an unmarked live test runs in every plain "
        "pytest and turns a credential-less clone red")


def test_the_arm_SKIPS_LOUDLY_when_creds_absent_and_names_what_is_missing(monkeypatch):
    monkeypatch.setattr(arm.canary_support, "read_creds_available", lambda: False)
    reason = arm.missing_reason()
    assert reason and "LARK_READ_APP_ID" in reason
    assert "Drive" in reason
    monkeypatch.setattr(arm.canary_support, "read_creds_available", lambda: True)
    assert arm.missing_reason() is None


def test_the_arm_routes_its_unavailability_through_skip(gate_source):
    assert "missing_reason" in gate_source and "pytest.skip" in gate_source, (
        "AC7: the arm must skip via missing_reason — never a silent pass")


# --------------------------------------------------------------------------- #
# AC3 — READ-ONLY BY CONSTRUCTION, not by intention                            #
# --------------------------------------------------------------------------- #


def test_the_registry_the_arm_leans_on_really_is_read_only():
    """The arm's first assertion, made here too — so the claim is checked on every run and not
    only on the runs that have credentials."""
    # TRANSFORMED, not deleted (LD-409, D-24) — see the arm's own comment: the claim is
    # asserted at the scope the arm has, and the mutating set is pinned so a second write op
    # on this path reddens rather than passing silently.
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS)
    assert all(descriptor.mutates is False for descriptor in drive_ops.ENUMERATION_OPS)
    assert not [d for d in drive_ops.ENUMERATION_OPS if d.mutates], (
        "a mutating op joined the ENUMERATION set — this arm runs against a real tenant "
        "and must not be the thing that discovers that")
    # LD-432 widened the registry's verb set (the access family declares PUT, DELETE and
    # PATCH), so the claim is asserted at the scope this arm actually has: the ENUMERATION's
    # own declared verbs. Nothing this arm calls can be anything but a GET or one of the
    # declared query POSTs.
    assert sorted({d.http_method for d in drive_ops.ENUMERATION_OPS}) == ["GET", "POST"]
    # LD-487 added a SECOND declared-read POST on the metas endpoint, outside the enumeration
    # set. The claim this arm needs is not a count but that every declared-read POST really is
    # a read — asserted here on all of them, so a mutating one cannot hide in a grown set.
    assert len(drive_ops.query_posts()) >= 1
    assert all(d.mutates is False for d in drive_ops.query_posts())


def test_the_arm_asserts_read_only_BEFORE_it_calls_anything(gate_source):
    tree = ast.parse(gate_source)
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    first = "test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_reads_anything"
    assert first in names, f"{first} is missing from the arm"
    others = [n for n in names if n.startswith("test_") and n != first]
    assert others, "the arm has no other test — the ordering claim would be vacuous"
    assert names.index(first) < min(names.index(n) for n in others), (
        "the read-only assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching a real tenant")


def test_the_arm_names_NO_write_credential_and_NO_write_verb(gate_body):
    """Scanned over the BODY, not the docstring: AC3 REQUIRES the docstring to say the arm
    cannot move/copy/delete/upload/shortcut/rename, so a whole-file grep would forbid its own
    rule. The body is what actually runs."""
    for forbidden in ("LARK_WRITE_APP", "get_write_credentials", "from_write_credentials",
                      "write_client", "upload", "create_folder", "shortcut", ".move(",
                      ".copy(", ".delete("):
        assert forbidden not in gate_body, f"the arm names {forbidden!r}"


def test_the_arm_resolves_only_the_READ_credential_pair(gate_source):
    assert "from_read_credentials" in gate_source, (
        "AC3: the arm builds its client from the READ pair only")


def test_the_arms_enumerated_verbs_are_the_declared_read_only_set(gate_source):
    """AC3: the arm's HTTP verbs are ENUMERATED and asserted, not assumed.

    The enumeration is now read off ``ENUMERATION_OPS`` rather than off the whole registry —
    LD-432's access family declares PUT, DELETE and PATCH, and a whole-registry equality would
    make this arm assert something about ops it never calls. The property being pinned is
    unchanged: the arm's own verbs are enumerated in its source and checked before it calls
    anything.
    """
    assert 'sorted({d.http_method for d in drive_ops.ENUMERATION_OPS}) == ["GET", "POST"]' \
        in gate_source
    assert "query_posts()" in gate_source


# --------------------------------------------------------------------------- #
# AC1 — the SUBJECT is the bot's own root folder, discovered live              #
# --------------------------------------------------------------------------- #


def test_the_arm_resolves_its_subject_via_the_root_folder_meta_leg(gate_source):
    assert "root_folder_token()" in gate_source, (
        "AC1: the subject is resolved live via the root_folder/meta leg (LD-324's raw leg)")
    for suspicious in ("fldr", "nodl"):
        assert f'"{suspicious}' not in gate_source, (
            f"AC1: the arm hard-codes a {suspicious}… token instead of discovering the root")


@pytest.mark.parametrize("phrase", ["permanent", "create_folder", "root"])
def test_the_docstring_records_WHY_a_self_provisioned_folder_is_unavailable(
        gate_docstring, phrase):
    """AC1: the docstring must record WHY — a self-provisioned folder would be a permanent
    write (create_folder is R2/R3, no purge verb exists), so the gate reads a space the app
    already owns."""
    assert phrase in gate_docstring.lower() if phrase != "create_folder" else (
        phrase in gate_docstring), (
        f"the docstring does not record {phrase!r} — AC1 requires the reason to be readable "
        "without running anything")


# --------------------------------------------------------------------------- #
# AC2 — the optional maintainer-designated folder, and its three branches              #
# --------------------------------------------------------------------------- #


def test_UNSET_override_falls_back_to_the_bots_own_root(monkeypatch):
    monkeypatch.delenv(canary_support.CANARY_FOLDER_ENV, raising=False)
    fake = _FakeClient()
    subject = arm.resolve_subject(fake, arm.canary_folder_override())
    assert subject == fake._root, "unset ⇒ the discovered root folder is the subject"
    assert fake.root_calls == 1, "the root_folder/meta leg must be the source of the default"


def test_SET_and_reachable_override_REPLACES_the_subject_without_resolving_root():
    fake = _FakeClient()
    subject = arm.resolve_subject(fake, "OVERRIDEfolderTOKENxxxxxxx")
    assert subject == "OVERRIDEfolderTOKENxxxxxxx"
    assert fake.root_calls == 0, "a set override must not spend a call on root_folder/meta"


def test_SET_but_unreachable_override_SKIPS_LOUDLY_naming_the_variable():
    """AC2's third branch, with a simulated refusal (Lark's 1061002)."""
    fake = _FakeClient(refuse=True)
    with pytest.raises(Skipped) as excinfo:
        arm.enumerate_twice_or_skip(fake, "UNREACHABLEfolderTOKENxxxx")
    message = str(excinfo.value)
    assert canary_support.CANARY_FOLDER_ENV in message, (
        "the skip must name the overriding variable so the refusal is never silent")
    assert "unreachable" in message.lower()


def test_a_refusal_with_NO_override_set_is_a_real_FAILURE_not_a_skip():
    """The default subject is the bot's own root; if THAT is refused something is genuinely
    wrong, so it must surface as a failure rather than a silent skip."""
    fake = _FakeClient(refuse=True)
    with pytest.raises(type(folder_refused("x"))):
        arm.enumerate_twice_or_skip(fake, None)


def test_canary_folder_override_reads_a_bare_token_or_a_folder_URL(monkeypatch):
    monkeypatch.setenv(canary_support.CANARY_FOLDER_ENV, "  BAREtoken123  ")
    assert canary_support.canary_folder_override() == "BAREtoken123"
    monkeypatch.setenv(
        canary_support.CANARY_FOLDER_ENV,
        "https://x.sg.larksuite.com/drive/folder/URLtoken456?from=space")
    assert canary_support.canary_folder_override() == "URLtoken456"
    monkeypatch.delenv(canary_support.CANARY_FOLDER_ENV, raising=False)
    assert canary_support.canary_folder_override() is None


# --------------------------------------------------------------------------- #
# AC4 — SAME-RUN byte-identity, and the calibration is stated                  #
# --------------------------------------------------------------------------- #


def test_the_arm_enumerates_TWICE_and_compares_the_two_reads(gate_source):
    assert "enumerate_twice_or_skip" in gate_source
    assert "first_bytes == second_bytes" in gate_source, (
        "AC4: the two back-to-back enumerations must be compared byte-for-byte")


def test_the_docstring_calibrates_SAME_RUN_and_says_why_not_cross_time(gate_docstring):
    lowered = gate_docstring.lower()
    assert "same-run" in lowered, "AC4: same-run identity is the claim"
    assert "cross-time" in lowered, "AC4: the docstring must say cross-time is NOT claimed"
    assert "change" in lowered, (
        "AC4: the reason cross-time is not claimed — a folder's contents legitimately change "
        "between runs")


def test_the_arm_commits_NO_cross_time_baseline(gate_source):
    for forbidden in ("write_text", "read_text(", "fixtures/", ".golden"):
        assert forbidden not in gate_source, (
            f"{forbidden!r} in the arm — a cross-time baseline is exactly what AC4 forbids")


# --------------------------------------------------------------------------- #
# AC5 — it asserts the things that would actually drift                        #
# --------------------------------------------------------------------------- #


def test_the_arm_pins_the_drift_bearing_shape(gate_source):
    for claim in ("CHILD_FIELDS", ".url", "has_more", "next_page_token", "DISPATCH"):
        assert claim in gate_source, f"AC5: the arm does not pin {claim!r}"


def test_the_arm_pins_the_1061002_refusal_on_a_malformed_token(gate_source):
    assert "FolderRefusedError" in gate_source, (
        "AC5: the malformed-token refusal is the cheapest drift alarm for the family's "
        "catch-all — the arm must assert it still behaves as captured")
    assert ("FOLDER_REFUSED_CODE" in gate_source or str(FOLDER_REFUSED_CODE) in gate_source)


def test_the_dispatch_vocabulary_is_the_KNOWN_type_set_the_arm_leans_on():
    """The arm's 'known type or a disclosed unknown-type marker' assertion rests on LD-325's
    dispatch table; pinned here so a drift in the known set is visible offline too."""
    assert set(DISPATCH) == {"docx", "sheet", "bitable", "folder", "shortcut", "file"}


# --------------------------------------------------------------------------- #
# AC6 — gentle, and HARD-BUDGETED (raises rather than exceeds)                 #
# --------------------------------------------------------------------------- #


def test_the_budget_is_a_small_declared_constant(gate_source):
    assert "DRIVE_CANARY_CALL_BUDGET" in gate_source
    assert 0 < arm.DRIVE_CANARY_CALL_BUDGET <= 20, (
        "AC6: the probes' own discipline was budgets of 6 and 20 — a Drive canary needs only a "
        f"handful; {arm.DRIVE_CANARY_CALL_BUDGET} is out of that range")


def test_the_arm_ASSERTS_its_own_call_count_against_the_budget(gate_source):
    assert "api_calls" in gate_source and "DRIVE_CANARY_CALL_BUDGET" in gate_source, (
        "AC6: the budget is an assertion over the observed call count, not merely a constant")


def test_the_budget_limiter_RAISES_rather_than_exceeding_IN_SITU():
    """AC6: enforcement, not declaration — driven through the real client's own send path so
    the ceiling cannot be bypassed by a leg added at the call site."""
    empty = {"code": 0, "data": {"files": [], "has_more": False}}
    client = DriveClient(
        "id", "secret", "larksuite.com",
        urlopen=lambda req, timeout=None: _FakeResponse(empty),
        token_fetcher=lambda *a, **k: "tok",
        # A zero-window limiter so the offline check does not spend the spike's 1.2 s pacing.
        rate_limiter=arm._BudgetLimiter(2, max_per_sec=1, window=0),
    )
    client.list_folder_children()   # 1
    client.list_folder_children()   # 2
    with pytest.raises(arm.DriveCanaryBudgetExceeded):
        client.list_folder_children()  # 3 — over budget, raises before the send
    assert client.api_calls == 2, "the over-budget call must raise BEFORE it is counted/sent"


def test_the_budget_limiter_still_PACES_through_the_real_RateLimiter():
    """The budget limiter is a RateLimiter subclass, so it inherits the 1.2 s spacing the
    spike ran at — the ceiling is added ON TOP of pacing, never instead of it."""
    from larkdocio.common.transport import RateLimiter

    assert isinstance(arm.make_budget_limiter(1), RateLimiter)


# --------------------------------------------------------------------------- #
# AC8 — the classified gate_registry row and its offline mirror                #
# --------------------------------------------------------------------------- #


def test_the_arm_has_a_CLASSIFIED_registry_row_pointing_at_THIS_file():
    row = gr.REGISTRY.get(_GATE.name)
    assert row is not None, f"{_GATE.name} has no gate_registry row (AC8)"
    assert row.kind is gr.Kind.HAS_COMPANION, (
        f"the Drive canary ships WITH its mirror, so its row is HAS_COMPANION, not "
        f"{row.kind.name}")
    assert row.companion == Path(__file__).name
    assert row.reason.strip(), "every row carries a written reason — that is the point"
    back = gr.REGISTRY[row.companion]
    assert back.kind is gr.Kind.COMPANION and back.subject == _GATE.name


def test_the_new_gate_adds_NO_new_GAP():
    assert _GATE.name not in [row.filename for row in gr.gap_list()]
    assert len(gr.gap_list()) == 10


# --------------------------------------------------------------------------- #
# AC9 — no capture of a real tree is committed                                 #
# --------------------------------------------------------------------------- #


def test_the_arm_writes_NO_capture_of_a_real_tree(gate_source):
    """AC9: the simplest compliant answer is to commit no capture at all, and this arm chose
    it — so the arm never writes an artifact from what it read live."""
    for forbidden in ("open(", "write_text", ".write(", "json.dump"):
        assert forbidden not in gate_source, (
            f"{forbidden!r} in the arm — AC9's chosen answer is to commit NO capture, so the "
            "arm must not write one")
