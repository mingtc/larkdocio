"""The always-on offline half of ``test_live_base_disposable_harness`` — and the unit tests of
the hardened provisioner itself (LD-258).

The live cycle runs only with credentials and a network, which makes every safety claim it
carries exactly the class of claim a credential-less run "verifies" by not running. So the
shape is verified **here**, statically and against a fake SDK, on every plain ``pytest``:

* **the prefix is ENFORCED, not conventional** (AC4) — a create whose title lacks
  ``larkdocio-DISPOSABLE-`` is refused **before** the SDK leg is touched, so an unnamed object
  cannot exist to be swept;
* **disposables only, by allow-list rather than deny-list** (AC5) — a token enters the harness
  in exactly one way, through its own create. The configured Scratch Base is therefore refused
  the same way every other pre-existing Base is, **without the harness ever naming it**: the
  landed guard in ``test_live_base_write_arm_offline.py`` pins that no configured-target
  variable appears in the harness source at all, and a deny-list would have had to break it;
* **delete in a ``finally``, proven by raising** (AC1) — the body throws and the delete still
  runs, with the outcome ledgered;
* **exactly one provisioner in ``tests/``** (AC1) — the ``sheets_write_harness`` precedent, one
  harness per surface;
* **the orphan oracle is the BITABLE API** (AC2) — ``1002`` / ``91402`` for an app, ``1254041``
  for a table path, and Drive metadata is never consulted, because it resolves a deleted Base's
  title forever and would report a false orphan in perpetuity;
* **what accretes is written down** (AC3), citing ``BASE.md`` register rows 9 and 10 rather than
  authoring a second copy of a guarded truth;
* **the skip is loud** (AC6).

It imports nothing from the live cycle and makes no network call.
"""
import ast
import json

import pytest

import base_write_harness as H

from guard_kit import REPO_ROOT

_TESTS = REPO_ROOT / "tests"
_REPO = REPO_ROOT
_HARNESS = _TESTS / "base_write_harness.py"
_ARM = _TESTS / "test_live_base_disposable_harness.py"

#: A token shaped like a real Base token, standing in for something the harness did not create.
FOREIGN_TOKEN = "basFOREIGNbase00000000000000"


# --------------------------------------------------------------------------- #
# A fake SDK: the four legs the provisioner may touch, and the one it may not.  #
# --------------------------------------------------------------------------- #

class _Leg:
    """A bare attribute holder standing in for one SDK resource namespace."""


class _Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the fake SDK was called with no canned response")
        return self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]


class _Forbidden:
    def __init__(self, why):
        self.why = why

    def __call__(self, *args, **kwargs):
        raise AssertionError(self.why)


class _Response:
    """The shape the provisioner reads off an SDK response: ``code`` and ``data``."""

    def __init__(self, code, data=None, msg="fake"):
        self.code = code
        self.msg = msg
        self.data = data

    def success(self):
        return self.code == 0


class _App:
    def __init__(self, app_token="basDISPOSABLE0000000000000000", default_table_id="tblFAKE"):
        self.app_token = app_token
        self.default_table_id = default_table_id


def fake_sdk(*, create=(), get=(), delete=(), fields=()):
    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = v1 = _Leg()
    v1.app = _Leg()
    v1.app.create = _Recorder(create)
    v1.app.get = _Recorder(get)
    v1.app_table_field = _Leg()
    v1.app_table_field.list = _Recorder(fields)
    sdk.drive = _Leg()
    sdk.drive.v1 = dv1 = _Leg()
    dv1.file = _Leg()
    dv1.file.delete = _Recorder(delete)
    # AC2's negative half, wired as a trap: Drive metadata resolves a DELETED Base's title
    # forever (`07-orphan-sweep.json`). An oracle that consulted it would report a false orphan
    # in perpetuity, so the harness must never reach for it.
    dv1.meta = _Forbidden("Drive metadata is inert residue, never the orphan oracle (AC2)")
    return sdk


class _NoWait:
    def acquire(self):
        pass


def provisioner(**legs):
    return H._Provisioner(sdk=fake_sdk(**legs), rate_limiter=_NoWait())


def create_response(token="basDISPOSABLE0000000000000000"):
    data = _Leg()
    data.app = _App(token)
    return _Response(0, data)


def ledger(tmp_path, name="ledger.json"):
    return H.Ledger(tmp_path / name)


# --------------------------------------------------------------------------- #
# AC4 — the fixed prefix is ENFORCED, not conventional.                         #
# --------------------------------------------------------------------------- #

def test_ac4_a_create_without_the_prefix_is_REFUSED_before_the_sdk_is_touched():
    p = provisioner(create=[create_response()])
    with pytest.raises(H.NonDisposableTitleError) as excinfo:
        p.create("Larkdocio Scratch Base")
    assert H.DISPOSABLE_TITLE_PREFIX in str(excinfo.value)
    assert p._sdk.bitable.v1.app.create.requests == [], (
        "the refusal must land BEFORE the create leg — an object that exists under an "
        "unsweepable name is exactly what the prefix is for")


def test_ac4_the_prefixed_create_is_allowed_and_yields_the_token():
    p = provisioner(create=[create_response("basMINTED000000000000000000")])
    token, table = p.create(H.disposable_title("t1"))
    assert token == "basMINTED000000000000000000"
    assert table == "tblFAKE"


def test_ac4_every_title_the_harness_mints_carries_the_greppable_prefix():
    assert H.disposable_title().startswith(H.DISPOSABLE_TITLE_PREFIX)
    assert H.disposable_title("x") == f"{H.DISPOSABLE_TITLE_PREFIX}x"
    assert not H.is_disposable_title("Larkdocio Scratch Base")


# --------------------------------------------------------------------------- #
# AC5 — the Scratch Base (and everything else it did not create) is untouchable. #
# --------------------------------------------------------------------------- #

def test_ac5_the_harness_REFUSES_to_delete_a_token_it_did_not_create():
    p = provisioner(delete=[_Response(0)])
    with pytest.raises(H.NonDisposableTargetError):
        p.delete(FOREIGN_TOKEN)
    assert p._sdk.drive.v1.file.delete.requests == [], (
        "the refusal must land before the delete leg")


def test_ac5_THE_CONFIGURED_SCRATCH_BASE_IS_NEVER_A_TARGET(monkeypatch):
    """The binding one (O2′). That Base holds the only hand-authored Lookup / Email / Stage
    fields in existence and the maintainer's six records, and the API cannot recreate them.

    The enforcement is an **allow-list, not a deny-list**: the harness refuses every token it
    did not mint, so the Scratch Base is refused without the harness naming it — which is what
    keeps the landed `test_live_base_write_arm_offline` guard ("no configured-target variable
    appears in the harness at all") true at the same time.
    """
    scratch = "basSCRATCHspecimens000000000"
    monkeypatch.setenv("LARKDOCIO_SCRATCH_BASE", f"https://x.larksuite.com/base/{scratch}")
    p = provisioner(create=[create_response()], delete=[_Response(0)], get=[_Response(0)])
    p.create(H.disposable_title("mine"))
    for call in (lambda: p.delete(scratch), lambda: p.is_gone(scratch),
                 lambda: p.table_is_gone(scratch, "tblAnything")):
        with pytest.raises(H.NonDisposableTargetError):
            call()
    assert p._sdk.drive.v1.file.delete.requests == []
    assert p._sdk.bitable.v1.app.get.requests == []
    assert "LARKDOCIO_SCRATCH_BASE" not in _HARNESS.read_text(encoding="utf-8"), (
        "the harness enforces by allow-list; naming the variable would break the landed guard "
        "and would be a weaker rule besides")


def test_ac5_a_ledger_entry_whose_title_is_not_a_disposable_cannot_be_ADOPTED(tmp_path):
    """The one remaining smuggling route: hand-editing the ledger. A ledger is only ever
    appended to by ``record_create``, and the close-out re-checks the title anyway."""
    led = ledger(tmp_path)
    led._entries.append({"app_token": "basSCRATCHspecimens000000000",
                         "title": "Larkdocio Scratch Base", "deleted": False, "last_code": None})
    led._flush()
    p = provisioner(delete=[_Response(0)])
    with pytest.raises(H.NonDisposableTargetError):
        p.adopt_from_ledger(led)


def test_ac5_the_arm_writes_only_what_the_harness_created():
    source = _ARM.read_text(encoding="utf-8")
    for env_name in ("LARKDOCIO_SCRATCH_BASE", "LARKDOCIO_CANARY_DOC",
                     "LARKDOCIO_BLOCKZOO_DOC", "LARKDOCIO_SCRATCH_SHEET"):
        assert env_name not in source, env_name
    assert "disposable_base(" in source


# --------------------------------------------------------------------------- #
# AC1 — delete in a `finally`, the ledger, and exactly one provisioner.         #
# --------------------------------------------------------------------------- #

class _FakeProvisioner:
    """Records what the context manager asked it to do — no SDK at all."""

    def __init__(self, token="basRAISER00000000000000000", deleted=True, code=0):
        self.token = token
        self._deleted = deleted
        self._code = code
        self.created = []
        self.deletes = []
        self.gone_queries = []

    def create(self, title, time_zone=None, *, folder_token=None):
        # The destination travels through the context manager and is RECORDED here, so a
        # harness that stopped passing one would be visible rather than silently defaulting.
        self.created.append(title)
        self.zones = getattr(self, "zones", []) + [time_zone]
        self.folders = getattr(self, "folders", []) + [folder_token]
        return self.token, "tblFAKE"

    def delete(self, app_token, attempts=H.DELETE_ATTEMPTS):
        self.deletes.append(app_token)
        return self._deleted, self._code

    def is_gone(self, app_token):
        self.gone_queries.append(app_token)
        return self._deleted

    def adopt_from_ledger(self, led):
        pass


def test_ac1_THE_DELETE_RUNS_WHEN_THE_BODY_RAISES(tmp_path):
    """The whole point of the ``finally``: the run that most needs cleaning up is the one that
    crashed."""
    fake = _FakeProvisioner()
    led = ledger(tmp_path)
    with pytest.raises(RuntimeError, match="the body exploded"):
        with H.disposable_base(provisioner=fake, ledger=led) as (token, _table, _title):
            assert token == fake.token
            raise RuntimeError("the body exploded")
    assert fake.deletes == [fake.token], "the finally did not delete"
    entry = led.entries[0]
    assert entry["deleted"] is True and entry["app_token"] == fake.token


def test_ac1_a_delete_that_could_not_land_leaves_a_FLAGGED_ledger_entry(tmp_path):
    fake = _FakeProvisioner(deleted=False, code=1061003)
    led = ledger(tmp_path)
    with H.disposable_base(provisioner=fake, ledger=led):
        pass
    entry = led.entries[0]
    assert entry["deleted"] is False and entry["last_code"] == 1061003
    assert [e["app_token"] for e in led.survivors()] == [fake.token], (
        "a token that could not be deleted is FLAGGED, never dropped")


def test_ac1_the_ledger_survives_the_process_that_wrote_it(tmp_path):
    led = ledger(tmp_path)
    led.record_create("basPERSISTED0000000000000000", H.disposable_title("p"))
    reopened = H.Ledger(tmp_path / "ledger.json")
    assert [e["app_token"] for e in reopened.survivors()] == ["basPERSISTED0000000000000000"]


def test_ac1_there_is_EXACTLY_ONE_provisioner_in_tests():
    """One harness per surface — the ``tests/sheets_write_harness.py`` precedent, twelve gates
    deep. A second private provisioner is how a leak gets its own private ledger."""
    marker = "Create" + "AppRequest"  # assembled so this guard cannot match its own source
    creators = sorted(p.name for p in _TESTS.rglob("*.py")  # LD-654: population must be recursive
                      if marker in p.read_text(encoding="utf-8"))
    assert creators == ["base_write_harness.py"], (
        f"exactly one file in tests/ may provision a Base; found {creators}")


# --------------------------------------------------------------------------- #
# AC2 — `orphans = 0` is defined against the BITABLE API, never Drive metadata.  #
# --------------------------------------------------------------------------- #

def test_ac2_the_app_oracle_is_1002_and_91402():
    assert H.DELETED_CODES == (1002, 91402)


@pytest.mark.parametrize("code", [1002, 91402])
def test_ac2_a_gone_app_answers_a_deleted_code(code):
    p = provisioner(create=[create_response()], get=[_Response(code)])
    token, _ = p.create(H.disposable_title("g"))
    assert p.is_gone(token) is True


def test_ac2_an_app_that_still_resolves_is_NOT_gone():
    p = provisioner(create=[create_response()], get=[_Response(0)])
    token, _ = p.create(H.disposable_title("g"))
    assert p.is_gone(token) is False


def test_ac2_the_table_oracle_is_1254041_and_it_is_a_REAL_capture():
    assert H.TABLE_DELETED_CODES == (1254041,)
    capture = json.loads(
        (_REPO / "tests" / "captures" / "base-study" / "captures" / "02-bitable18-fields.json")
        .read_text(encoding="utf-8"))
    assert capture["_lark_code"] == 1254041 and capture["_lark_msg"] == "TableIdNotFound"
    assert capture["_endpoint"].endswith("/fields"), (
        "the table oracle is a TABLE PATH read; the capture is what pins which one")
    p = provisioner(create=[create_response()], fields=[_Response(1254041)])
    token, _ = p.create(H.disposable_title("t"))
    assert p.table_is_gone(token, "tblGgEHCSGMXEKQs") is True


def test_ac2_a_table_that_still_lists_its_fields_is_NOT_gone():
    p = provisioner(create=[create_response()], fields=[_Response(0)])
    token, _ = p.create(H.disposable_title("t"))
    assert p.table_is_gone(token, "tblLive") is False


def test_ac2_DRIVE_METADATA_IS_NEVER_CONSULTED():
    """`07-orphan-sweep.json`: ``POST /drive/v1/metas/batch_query`` still returns a deleted
    Base's title and timestamps. An oracle built on it would report a false orphan forever."""
    tree = ast.parse(_HARNESS.read_text(encoding="utf-8"))
    # Prose may NAME the residue — that is the disclosure. Executable code may not REACH for
    # it, so the check is over attribute accesses and imported symbols, not over text.
    reached = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imported = {alias.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                for alias in n.names}
    for forbidden in ("metas", "meta", "batch_query"):
        assert forbidden not in reached, (
            f"the harness reaches for .{forbidden} — Drive metadata is inert residue, not the "
            "orphan oracle (AC2)")
    assert not [name for name in imported if "Meta" in name], sorted(imported)
    # And the positive half: the oracle asks BITABLE.
    assert "app" in reached and "bitable" in reached


def test_ac2_the_sweep_reports_ZERO_orphans_when_the_bitable_api_says_gone(tmp_path):
    led = ledger(tmp_path)
    p = provisioner(create=[create_response("basSWEPT0000000000000000000")],
                    delete=[_Response(0)], get=[_Response(1002)])
    with H.disposable_base(provisioner=p, ledger=led):
        pass
    assert H.orphans(provisioner=p, ledger=led) == []


def test_ac2_a_token_the_bitable_api_still_resolves_IS_an_orphan(tmp_path):
    led = ledger(tmp_path)
    p = provisioner(create=[create_response("basLEAKED000000000000000000")],
                    delete=[_Response(1061003)], get=[_Response(0)])
    with H.disposable_base(provisioner=p, ledger=led):
        pass
    leaked = H.orphans(provisioner=p, ledger=led)
    assert [e["app_token"] for e in leaked] == ["basLEAKED000000000000000000"]
    assert H.is_disposable_title(leaked[0]["title"]), (
        "an orphan is reported BY NAME, so a human sweep is a grep away")


def test_ac2_the_close_out_forgives_nothing_and_drops_nothing(tmp_path):
    """A token leaves the ledger only when the API says it is gone."""
    led = ledger(tmp_path)
    led.record_create("basSTUCK0000000000000000000", H.disposable_title("stuck"))
    p = provisioner(delete=[_Response(1061003)], get=[_Response(0)])
    still = H.close_out(provisioner=p, ledger=led, attempts=1)
    assert [e["app_token"] for e in still] == ["basSTUCK0000000000000000000"]
    assert [e["app_token"] for e in H.survivors(ledger=led)] == ["basSTUCK0000000000000000000"]


# --------------------------------------------------------------------------- #
# AC3 — the docstring says, in plain words, what accretes.                      #
# --------------------------------------------------------------------------- #

def test_ac3_the_docstring_says_DELETE_IS_TRASH_NOT_PURGE_and_cites_register_row_9():
    doc = H.__doc__
    lowered = doc.lower()
    assert "trash" in lowered and "purge" in lowered
    assert "row 9" in lowered, "the fact is authored in BASE.md row 9; the harness cites it"
    assert "table" in lowered, "deleted TABLES sit in the Base's trash too (P0 addendum § 6)"


def test_ac3_the_docstring_says_UPLOADED_MEDIA_HAS_NO_PURGE_VERB_and_cites_row_10():
    lowered = H.__doc__.lower()
    assert "file_token" in lowered and "row 10" in lowered
    assert "no purge verb" in lowered


def test_ac3_the_docstring_says_THE_REVISION_MOVES_AND_CANNOT_BE_RESTORED():
    lowered = H.__doc__.lower()
    assert "revision" in lowered
    assert "0 → 14" in H.__doc__ or "0 -> 14" in H.__doc__, (
        "the measurement is what makes the warning credible (P0 moved the Scratch Base 0 → 14)")


def test_ac3_the_cited_register_rows_really_say_what_the_docstring_says_they_say():
    """The citation is checked, not asserted: rows 9 and 10 are read out of BASE.md itself, so
    a re-worded register reddens here rather than leaving a dangling reference."""
    rows = {}
    for line in (_REPO / "BASE.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| 9 |") or line.startswith("| 10 |"):
            rows[line.split("|")[1].strip()] = line
    assert set(rows) == {"9", "10"}, sorted(rows)
    assert "TRASH, not purge" in rows["9"]
    assert "UN-PURGEABLE" in rows["10"] and "file_token" in rows["10"]


def test_ac3_this_story_authored_NO_new_register_row():
    """Rows 9 and 10 already carry the residue facts; a second copy in a length-pinned table is
    how a guarded truth drifts from itself."""
    harness = _HARNESS.read_text(encoding="utf-8")
    assert "`refused-by-server`" not in harness and "| :---" not in harness, (
        "the harness cites the register; it does not re-author a row")


# --------------------------------------------------------------------------- #
# AC6 / AC7 — loud skips, and the live cycle's own shape.                       #
# --------------------------------------------------------------------------- #

def test_ac6_the_skip_is_LOUD_and_names_exactly_what_is_missing(monkeypatch):
    monkeypatch.setattr(H, "get_write_credentials", lambda: ("", ""))
    reason = H.missing_reason()
    assert reason and "LARK_WRITE_APP_ID" in reason and "LARK_WRITE_APP_SECRET" in reason


def test_ac6_the_harness_reports_READY_when_the_credentials_are_present(monkeypatch):
    monkeypatch.setattr(H, "get_write_credentials", lambda: ("id", "secret"))
    assert H.missing_reason() is None


def test_ac7_the_live_cycle_is_marked_live_write_and_deselected_by_default():
    assert "pytestmark = pytest.mark.live_write" in _ARM.read_text(encoding="utf-8"), (
        "an unmarked live cycle would create real Bases on every plain pytest")


def test_ac7_the_live_cycle_uses_its_OWN_per_run_ledger():
    """The session ledger at the repository root is the sweep list for everything; a cycle that
    asserted zero orphans over it would be asserting about other runs' leftovers."""
    source = _ARM.read_text(encoding="utf-8")
    assert "tmp_path" in source and "H.Ledger(" in source


def test_ac7_the_live_cycle_asserts_ZERO_ORPHANS_against_the_bitable_oracle():
    source = _ARM.read_text(encoding="utf-8")
    assert "orphans(" in source
    tree = ast.parse(source)
    assert any(isinstance(n, ast.Assert) for n in ast.walk(tree)), "the cycle must assert"


def test_ac7_the_harness_resolves_the_WRITE_pair_and_never_the_READ_one():
    source = _HARNESS.read_text(encoding="utf-8")
    assert "get_write_credentials" in source
    assert "get_read_credentials" not in source and "LARK_READ_APP" not in source


def test_ac7_nothing_in_the_harness_PROBES_a_rate_limit():
    source = _HARNESS.read_text(encoding="utf-8")
    assert "99991400" not in source, "a rate-limit retry is a probe by another name"


# --------------------------------------------------------------------------- #
# LD-275 — the oracle was BLIND during the addressability lag.                  #
#                                                                               #
# Two independent holes, both reproduced below against the fake SDK:            #
#                                                                               #
# (b) LEDGER AMNESIA — the measured one. The ledger resolved to                 #
#     ``<this checkout>/.base-disposables.json``, so a leg running in a linked   #
#     git worktree wrote its record into the worktree and the record died with  #
#     ``git worktree remove``. Evidence: the six Bases found alive on           #
#     2026-08-04 appear in NO surviving ledger entry (483 entries, zero title   #
#     matches) — no ``orphans()`` call could ever have seen them.               #
#                                                                               #
# (a) A NOT-FOUND ANSWER TAKEN AS PROOF — the structural one. A token whose     #
#     delete never landed, asked of the bitable API inside the same lag window, #
#     was scored *deleted* on a single 1002/91402 with nothing corroborating    #
#     it, and left the ledger for ever.                                         #
# --------------------------------------------------------------------------- #

LAGGED = "basLAGGED000000000000000000"


def _backdate(led, app_token, seconds):
    """Age one entry by rewriting its ``created_at`` — the lag horizon is a clock question."""
    from datetime import datetime, timedelta, timezone
    when = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    for entry in led._entries:
        if entry.get("app_token") == app_token:
            entry["created_at"] = when.isoformat()
    led._flush()


def _lagged_ledger(tmp_path, code=1061003):
    """A token whose delete answered a lag code moments ago — the leak's exact state."""
    led = ledger(tmp_path)
    led.record_create(LAGGED, H.disposable_title("lagged"))
    led.record_delete(LAGGED, code, False)
    return led


def test_ld275_the_durable_ledger_lives_in_the_MAIN_CHECKOUT_not_the_linked_worktree(tmp_path):
    """Root cause (b). A linked worktree's ``.git`` is a FILE pointing into the main
    checkout's ``.git/worktrees/<name>``; the ledger must follow it home, or every leg the
    wave-runner runs in ``/tmp/wt-*`` records its disposables into a directory that is deleted
    minutes later."""
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt-LD-999").mkdir(parents=True)
    wt = tmp_path / "wt-LD-999"
    (wt / "tests").mkdir(parents=True)
    (wt / ".git").write_text(
        f"gitdir: {main / '.git' / 'worktrees' / 'wt-LD-999'}\n", encoding="utf-8")

    assert H.durable_ledger_path(wt / "tests" / "base_write_harness.py") == \
        main / ".base-disposables.json"


def test_ld275_a_plain_checkout_keeps_its_own_repository_root_ledger(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "tests").mkdir()
    assert H.durable_ledger_path(repo / "tests" / "base_write_harness.py") == \
        repo / ".base-disposables.json"


def test_ld275_the_SHIPPED_ledger_path_is_the_resolved_durable_one():
    assert H.LEDGER_PATH == H.durable_ledger_path()
    assert H.LEDGER_PATH.name == ".base-disposables.json"


class _RealMintingProvisioner(_FakeProvisioner):
    """A stand-in for a provisioner whose tokens are REAL — the mirror's trigger."""

    mints_real_objects = True


def test_ld275_a_per_run_ledger_ALSO_records_into_the_durable_one(tmp_path, monkeypatch):
    """Root cause (b), the second leg: the live cycle keeps a ``tmp_path`` ledger so its
    zero-orphan claim is about *its* cycle — but a token recorded ONLY there is lost when
    pytest sweeps the temp dir. Every real token lands in the durable ledger too."""
    durable = tmp_path / "durable.json"
    monkeypatch.setattr(H, "LEDGER_PATH", durable)
    per_run = ledger(tmp_path, "run_ledger.json")
    fake = _RealMintingProvisioner(token="basMIRRORED00000000000000000", deleted=False,
                                   code=1061003)

    with H.disposable_base(provisioner=fake, ledger=per_run):
        pass

    assert [e["app_token"] for e in per_run.survivors()] == ["basMIRRORED00000000000000000"]
    reopened = H.Ledger(durable)
    assert [e["app_token"] for e in reopened.survivors()] == ["basMIRRORED00000000000000000"], (
        "a token kept by a failed delete must be sweepable by the NEXT session, which means "
        "the durable ledger, not a temp file")
    assert reopened.entries[0]["last_code"] == 1061003


def test_ld275_an_OFFLINE_double_never_writes_the_durable_ledger(tmp_path, monkeypatch):
    """The mirror's other half, and the one that keeps this suite safe: a fake token written
    to the durable ledger would be adopted by a later live sweep and deleted against the real
    tenant. Only a provisioner that mints real objects mirrors."""
    durable = tmp_path / "durable.json"
    monkeypatch.setattr(H, "LEDGER_PATH", durable)
    with H.disposable_base(provisioner=_FakeProvisioner(), ledger=ledger(tmp_path)):
        pass
    assert not durable.exists(), "an offline double must leave no live-sweep instructions"


def test_ld275_only_a_REAL_sdk_client_mints_real_objects():
    import lark_oapi as lark

    assert provisioner().mints_real_objects is False
    real = H._Provisioner(sdk=lark.Client.builder().app_id("x").app_secret("y").build(),
                          rate_limiter=_NoWait())
    assert real.mints_real_objects is True


def test_ld275_a_YOUNG_token_whose_delete_NEVER_LANDED_is_PENDING_not_gone(tmp_path):
    """**The bug, as a test.** Delete answered a lag code; the bitable API answers 91402 inside
    the same window. Scored ``gone``, the token left the accounting for ever while the Base
    lived on. A not-found answer is proof only when something corroborates it."""
    led = _lagged_ledger(tmp_path)
    p = provisioner(get=[_Response(91402)])
    reported = H.orphans(provisioner=p, ledger=led)
    assert [e["app_token"] for e in reported] == [LAGGED], (
        "an unverified disappearance inside the lag window is an OPEN question, not a clean "
        "sweep — this is exactly the silence that leaked six live Bases on 2026-08-04")
    assert reported[0]["state"] == H.VERDICT_PENDING
    assert H.is_disposable_title(reported[0]["title"])


def test_ld275_a_DELETE_THAT_LANDED_corroborates_the_not_found_answer(tmp_path):
    """The healthy path stays clean and stays fast: ``code:0`` from the delete is the
    corroboration, so a young token is ``gone`` with no waiting."""
    led = ledger(tmp_path)
    led.record_create("basCLEAN0000000000000000000", H.disposable_title("clean"))
    led.record_delete("basCLEAN0000000000000000000", 0, True)
    p = provisioner(get=[_Response(1002)])
    assert H.orphans(provisioner=p, ledger=led) == []


def test_ld275_past_the_measured_LAG_HORIZON_a_not_found_answer_IS_proof(tmp_path):
    """And the pending verdict expires: a token older than the measured lag that the bitable
    API will not serve is gone, or the ledger would grow a permanent false orphan."""
    led = _lagged_ledger(tmp_path)
    _backdate(led, LAGGED, H.LAG_HORIZON_SECONDS + 60)
    p = provisioner(get=[_Response(91402)])
    assert H.orphans(provisioner=p, ledger=led) == []
    assert H.LAG_HORIZON_SECONDS >= 20 * 60, (
        "the measured lag ran to over twenty minutes; a shorter horizon re-opens the hole")


def test_ld275_a_token_that_still_RESOLVES_is_an_orphan_whatever_its_age(tmp_path):
    led = _lagged_ledger(tmp_path)
    _backdate(led, LAGGED, H.LAG_HORIZON_SECONDS + 60)
    p = provisioner(get=[_Response(0)])
    reported = H.orphans(provisioner=p, ledger=led)
    assert [e["state"] for e in reported] == [H.VERDICT_ALIVE]


def test_ld275_close_out_KEEPS_a_pending_token_for_the_next_session(tmp_path):
    """The close-out's rescue branch was the second mouth of the same hole: a failed delete
    plus one not-found answer marked the entry deleted and dropped it from every future
    sweep."""
    led = _lagged_ledger(tmp_path)
    p = provisioner(delete=[_Response(1061003)], get=[_Response(91402)])
    still = H.close_out(provisioner=p, ledger=led, attempts=1)
    assert [e["app_token"] for e in still] == [LAGGED]
    assert [e["state"] for e in still] == [H.VERDICT_PENDING]
    assert [e["app_token"] for e in H.survivors(ledger=led)] == [LAGGED], (
        "the token stays on the sweep list until something corroborates its disappearance")


def test_ld275_close_out_RETIRES_a_token_the_api_has_stopped_serving_for_long_enough(tmp_path):
    led = _lagged_ledger(tmp_path)
    _backdate(led, LAGGED, H.LAG_HORIZON_SECONDS + 60)
    p = provisioner(delete=[_Response(1061003)], get=[_Response(1002)])
    assert H.close_out(provisioner=p, ledger=led, attempts=1) == []
    assert H.survivors(ledger=led) == []


def test_ld275_the_stale_sweep_adopts_PRIOR_sessions_and_leaves_this_one_alone(tmp_path):
    """The adopt-stale-at-start half: a session opens by sweeping what earlier sessions could
    not delete — and touches nothing young, because a fresh disposable belongs to whoever is
    still using it."""
    led = ledger(tmp_path)
    for token, nonce in ((LAGGED, "old"), ("basFRESH0000000000000000000", "new")):
        led.record_create(token, H.disposable_title(nonce))
        led.record_delete(token, 1061003, False)
    _backdate(led, LAGGED, H.LAG_HORIZON_SECONDS + 60)

    p = provisioner(delete=[_Response(0)], get=[_Response(1002)])
    assert H.sweep_stale(provisioner=p, ledger=led, attempts=1) == []
    assert [r.file_token for r in p._sdk.drive.v1.file.delete.requests] == [LAGGED], (
        "only the stale entries are swept; a live run's own disposable is not somebody else's "
        "to delete")
    assert [e["app_token"] for e in H.survivors(ledger=led)] == ["basFRESH0000000000000000000"]


def test_ld275_minted_MEDIA_is_mirrored_into_the_durable_ledger_too(tmp_path, monkeypatch):
    """Media residue is permanent and undeletable (register row 10), so an amnesiac record of
    it is worse than a leaked Base: nothing can ever recover the token."""
    durable = tmp_path / "durable.json"
    monkeypatch.setattr(H, "LEDGER_PATH", durable)

    class _Uploader(_RealMintingProvisioner):
        def upload_media(self, app_token, *, data, name, parent_type):
            uploaded = _Leg()
            uploaded.file_token = "fileTOKEN0000000000000000000"
            return uploaded

    per_run = ledger(tmp_path, "run_ledger.json")
    H.attach_media("basOWNED0000000000000000000", data=b"x", name="x.bin",
                   parent_type="bitable_file", provisioner=_Uploader(), ledger=per_run)
    assert [e["file_token"] for e in H.Ledger(durable).media()] == ["fileTOKEN0000000000000000000"]


def test_ld275_the_docstring_explains_the_CROSS_SESSION_ledger_and_the_pending_verdict():
    lowered = H.__doc__.lower()
    assert "worktree" in lowered, "the amnesia had a mechanism; naming it is what stops it"
    assert "pending" in lowered and "corroborat" in lowered


# --------------------------------------------------------------------------- #
# LD-275, the other edge of a SHARED ledger: adoption must be of the STALE.     #
#                                                                              #
# Making the ledger cross-session is what stops the amnesia — and it is also    #
# what puts a PARALLEL leg's in-flight disposable on this session's sweep list. #
# A token another run is still using is not this run's to delete, so an         #
# inherited entry is adopted only once it has outlived the lag horizon. Until   #
# then it is REPORTED (never dropped, never silently deleted).                  #
# --------------------------------------------------------------------------- #

FOREIGN_SESSION = "0000000000000000000000000000ffff"


def _foreign_entry(led, token, code=1061003):
    """A survivor recorded by a DIFFERENT session — what a parallel leg leaves behind."""
    led.record_create(token, H.disposable_title("theirs"))
    led.record_delete(token, code, False)
    for entry in led._entries:
        if entry.get("app_token") == token:
            entry["session"] = FOREIGN_SESSION
    led._flush()
    return led


def test_ld275_every_recorded_create_STAMPS_the_session_that_minted_it(tmp_path):
    """Whose token this is, is a question the ledger could not answer before — and it must,
    now that one file is shared by every session and every worktree."""
    led = ledger(tmp_path)
    led.record_create("basSTAMPED00000000000000000", H.disposable_title("mine"))
    assert led.entries[0]["session"] == H.SESSION_ID
    assert H.SESSION_ID and len(H.SESSION_ID) >= 16, "a session id must not collide by luck"


def test_ld275_close_out_NEVER_DELETES_another_live_sessions_YOUNG_disposable(tmp_path):
    """The regression the cross-session ledger would otherwise introduce: two wave-runner legs
    now share one sweep list, and a teardown that deleted a Base a parallel run was still
    writing to would turn this fix into a worse bug than the one it closes."""
    led = _foreign_entry(ledger(tmp_path), "basTHEIRS000000000000000000")
    p = provisioner(delete=[_Response(0)], get=[_Response(0)])

    left = H.close_out(provisioner=p, ledger=led, attempts=1)

    assert p._sdk.drive.v1.file.delete.requests == [], (
        "another session's young disposable is not this session's to delete")
    assert [e["app_token"] for e in left] == ["basTHEIRS000000000000000000"]
    assert left[0]["state"] == H.VERDICT_PENDING
    assert [e["app_token"] for e in H.survivors(ledger=led)] == ["basTHEIRS000000000000000000"]


def test_ld275_close_out_ADOPTS_another_sessions_disposable_once_it_is_STALE(tmp_path):
    """And the deferral expires — otherwise a leg that died mid-run would leak exactly as
    before, just with a record nobody acts on."""
    led = _foreign_entry(ledger(tmp_path), "basTHEIRS000000000000000000")
    _backdate(led, "basTHEIRS000000000000000000", H.LAG_HORIZON_SECONDS + 60)
    p = provisioner(delete=[_Response(0)], get=[_Response(1002)])

    assert H.close_out(provisioner=p, ledger=led, attempts=1) == []
    assert [r.file_token for r in p._sdk.drive.v1.file.delete.requests] == [
        "basTHEIRS000000000000000000"]


def test_ld275_close_out_still_finishes_THIS_sessions_own_young_token_at_once(tmp_path):
    """The common path must not slow down: a token this run minted is swept the moment its
    ``finally`` could not, with no waiting for any horizon."""
    led = _lagged_ledger(tmp_path)
    p = provisioner(delete=[_Response(0)], get=[_Response(1002)])

    assert H.close_out(provisioner=p, ledger=led, attempts=1) == []
    assert [r.file_token for r in p._sdk.drive.v1.file.delete.requests] == [LAGGED]


def test_ld275_the_sweep_and_the_ledger_never_disagree_about_what_is_LEFT(tmp_path):
    """The invariant every shipped Base arm asserts (``{survivors} == {left}``) — pinned here
    with a deferred foreign entry in play, because a skipped token that vanished from the
    report would be the LD-275 hole re-cut at a different angle."""
    led = _foreign_entry(ledger(tmp_path), "basTHEIRS000000000000000000")
    led.record_create(LAGGED, H.disposable_title("mine"))
    led.record_delete(LAGGED, 1061003, False)
    p = provisioner(delete=[_Response(1061003)], get=[_Response(91402)])

    left = H.close_out(provisioner=p, ledger=led, attempts=1)

    assert {e["app_token"] for e in left} == {e["app_token"] for e in H.survivors(ledger=led)}
    assert all(H.is_disposable_title(e["title"]) and e["app_token"] for e in left)


# --------------------------------------------------------------------------- #
# LD-297 — the SHARED ledger is written concurrently, so a flush MERGES.        #
# --------------------------------------------------------------------------- #

A_TOKEN = "basAAA00000000000000000000a"
B_TOKEN = "basBBB00000000000000000000b"


def test_ld297_a_parallel_legs_SURVIVOR_is_never_erased_by_the_second_flusher(tmp_path):
    """The issue's own interleaving. Two legs share one durable ledger; the one that flushes
    LAST held a snapshot taken before the other leg existed. A write-all-back would amputate
    the list — and an amputated list is LD-275's unnameable leaked Base, re-cut."""
    path = tmp_path / "shared.json"
    a = H.Ledger(path)
    a.record_create(A_TOKEN, H.disposable_title("a"))
    b = H.Ledger(path)                          # a parallel leg opens the SAME ledger
    b.record_create(B_TOKEN, H.disposable_title("b"))
    b.record_delete(B_TOKEN, 1061003, False)    # B leaks: its delete never landed
    a.record_delete(A_TOKEN, 0, True)           # A finishes AFTER B, flushing its snapshot

    on_disk = H.Ledger(path)
    assert [e["app_token"] for e in on_disk.entries] == [A_TOKEN, B_TOKEN]
    assert [e["app_token"] for e in on_disk.survivors()] == [B_TOKEN]
    assert on_disk.survivors()[0]["last_code"] == 1061003


def test_ld297_a_parallel_legs_MEDIA_token_survives_the_same_interleaving(tmp_path):
    """The media half is residue no verb deletes, so losing its record is losing it forever."""
    path = tmp_path / "shared.json"
    a = H.Ledger(path)
    a.record_create(A_TOKEN, H.disposable_title("a"))
    b = H.Ledger(path)
    b.record_media("filABC00000000000000000000", "bitable_image", B_TOKEN)
    a.record_delete(A_TOKEN, 0, True)

    assert [e["file_token"] for e in H.Ledger(path).media()] == ["filABC00000000000000000000"]


def test_ld297_the_merge_is_an_UPSERT_so_a_shared_entry_is_never_duplicated(tmp_path):
    """Keyed on identity (``kind`` + token), because a merge that appended would grow a second
    row per flush and make ``survivors()`` double-count what it must count exactly once."""
    path = tmp_path / "shared.json"
    a = H.Ledger(path)
    a.record_create(A_TOKEN, H.disposable_title("a"))
    b = H.Ledger(path)
    b.record_delete(A_TOKEN, 1061003, False)
    a.record_delete(A_TOKEN, 1061003, False)

    assert len(H.Ledger(path).entries) == 1


def test_ld297_a_merge_NEVER_resurrects_a_verified_deleted_entry_as_pending(tmp_path):
    """LD-275's accounting must survive the union: ``deleted`` is MONOTONIC. A stale snapshot
    saying ``deleted: false`` is an older opinion, never a retraction of the delete another
    leg watched land — the sweep list may only shrink by evidence."""
    path = tmp_path / "shared.json"
    a = H.Ledger(path)
    a.record_create(A_TOKEN, H.disposable_title("a"))
    stale = H.Ledger(path)                      # a snapshot taken while it was still pending
    a.record_delete(A_TOKEN, 0, True)           # the delete lands, and is written down

    stale.record_create(B_TOKEN, H.disposable_title("b"))   # any later flush by the stale leg

    fresh = H.Ledger(path)
    assert [e["app_token"] for e in fresh.survivors()] == [B_TOKEN]
    assert fresh.entries[0]["deleted"] is True and fresh.entries[0]["last_code"] == 0


def test_ld297_a_recorded_delete_reaches_an_entry_ANOTHER_leg_created(tmp_path):
    """The sweep's side of the same coin: ``close_out`` may adopt a stale token this instance
    never held in memory, and its verdict has to land on the shared file, not on nothing."""
    path = tmp_path / "shared.json"
    keeper = H.Ledger(path)                     # opened BEFORE the other leg's create
    H.Ledger(path).record_create(B_TOKEN, H.disposable_title("b"))

    keeper.record_delete(B_TOKEN, 0, True)

    fresh = H.Ledger(path)
    assert [(e["app_token"], e["deleted"], e["last_code"]) for e in fresh.entries] == [
        (B_TOKEN, True, 0)]
    assert fresh.survivors() == []


def test_ld297_concurrent_writers_lose_nothing_under_the_lock(tmp_path):
    """The read-modify-write window is serialized by an OS-level exclusive lock, so N writers
    interleaving on one file leave N records — the invariant, exercised rather than argued."""
    import threading

    path = tmp_path / "shared.json"
    tokens = [f"basCONCURRENT{i:015d}" for i in range(24)]

    def write(token):
        H.Ledger(path).record_create(token, H.disposable_title("c"))

    threads = [threading.Thread(target=write, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert {e["app_token"] for e in H.Ledger(path).entries} == set(tokens)


def test_ld297_the_ledger_docstring_explains_the_MERGE_and_the_lock():
    """The concurrency contract is part of the ledger's promise, so it is written where the
    next reader of ``Ledger`` will meet it."""
    doc = H.Ledger.__doc__
    assert "merge" in doc.lower() and "lock" in doc.lower()
    assert "LD-297" in doc


# --------------------------------------------------------------------------- #
# LD-535 — the oracle re-PROVED what it had already proved, seven times a ring. #
#                                                                              #
# `orphans()` asked the bitable API about every base row the file had ever      #
# held and then threw the verdict away, so the cost of the safety machinery     #
# grew with the whole history of disposables instead of with what is            #
# outstanding — 67 base rows and SEVEN oracle call sites in this tree, i.e.     #
# 469..819 probes per full Base ring, measured in                              #
# dev/2026-08-21-orphan-ledger-cost-model.md.                                   #
#                                                                              #
# The fix is to WRITE THE VERDICT DOWN (`probe_gone_at`) and stop re-asking —    #
# and the fence is that only a verdict reached ON A PROBE ANSWER may be         #
# written. `deleted: true` is not a ticket: it can come from the delete's own    #
# answer, which is a claim about a drive FILE, and that is the exact claim six   #
# Bases rode past a green gate on (LD-275; D-55 — a read-back, never a code:0).  #
# --------------------------------------------------------------------------- #

GONE_TOKEN = "basGONE0000000000000000000g"
SURVIVOR_TOKEN = "basSURVIVOR000000000000000s"
MARKED_TOKEN = "basMARKED00000000000000000m"


def _flat(text):
    """One line, single-spaced — a docstring guard must police the words, not the wrapping."""
    return " ".join(text.split())


def _probes(p):
    """How many bitable app-get calls this provisioner has issued — the oracle's real cost."""
    return len(p._sdk.bitable.v1.app.get.requests)


def _settled_ledger(tmp_path, token=GONE_TOKEN):
    """One row in the state 66 of this checkout's 67 base rows are in: deleted, its delete
    landed, and long past the lag horizon — but never yet corroborated by a probe."""
    led = ledger(tmp_path)
    led.record_create(token, H.disposable_title("settled"))
    led.record_delete(token, 0, True)
    _backdate(led, token, H.LAG_HORIZON_SECONDS + 60)
    return led


def test_ld535_a_row_the_oracle_has_never_PROBED_is_asked_about_however_settled_it_looks(
        tmp_path):
    """The fence, stated as the default. ``deleted: true`` + a landed code + an age past the
    horizon is what 66 of this checkout's 67 rows look like, and it buys **nothing**: the first
    oracle pass still asks. Anything else would be trusting the delete's own answer, which is
    LD-275's hole reopened by a performance argument."""
    led = _settled_ledger(tmp_path)
    assert [e["app_token"] for e in led.probe_set()] == [GONE_TOKEN]
    assert led.archived() == []
    p = provisioner(get=[_Response(1002)])
    assert H.orphans(provisioner=p, ledger=led) == []
    assert _probes(p) == 1, "the settled-looking row was asked about, not assumed"


def test_ld535_the_verdict_is_WRITTEN_DOWN_so_the_next_ring_does_not_re_prove_it(tmp_path):
    """The whole win, in probes. The first pass asks and records; the second asks nothing."""
    led = _settled_ledger(tmp_path)
    first = provisioner(get=[_Response(1002)])
    assert H.orphans(provisioner=first, ledger=led) == []
    assert _probes(first) == 1
    assert [e["app_token"] for e in led.archived()] == [GONE_TOKEN]
    assert led.probe_set() == []

    second = provisioner(get=[_Response(1002)])
    assert H.orphans(provisioner=second, ledger=H.Ledger(led.path)) == []
    assert _probes(second) == 0, (
        "a probe-corroborated disappearance is re-proved zero times, not once per oracle call")


def test_ld535_A_SURVIVOR_IS_NEVER_ARCHIVED_whatever_a_probe_said(tmp_path):
    """AC2's first refusal, and it lives in the ledger so no call site can route around it.
    ``close_out`` and ``survivors()`` are the authorities on a ``deleted: false`` row; hiding
    one from the oracle while still listing it as a survivor would be two answers to one
    question."""
    led = ledger(tmp_path)
    led.record_create(SURVIVOR_TOKEN, H.disposable_title("alive"))
    led.record_probe_gone([SURVIVOR_TOKEN])          # asked for it directly — still refused
    assert led.archived() == []
    assert [e["app_token"] for e in led.probe_set()] == [SURVIVOR_TOKEN]
    assert [e["app_token"] for e in led.survivors()] == [SURVIVOR_TOKEN]
    assert H.PROBE_GONE_FIELD not in led.entries[0]


def test_ld535_the_ORACLE_never_offers_a_deleted_false_row_for_archival_either(tmp_path):
    """The same refusal at the other layer. Past the lag horizon a not-found answer IS proof of
    absence — so the verdict here is ``gone`` and the row is correctly not reported — but the
    row still reads ``deleted: false``, so it stays on the sweep list and in the probe set."""
    led = ledger(tmp_path)
    led.record_create(SURVIVOR_TOKEN, H.disposable_title("aged-out"))
    _backdate(led, SURVIVOR_TOKEN, H.LAG_HORIZON_SECONDS + 60)
    p = provisioner(get=[_Response(1002)])
    assert H.orphans(provisioner=p, ledger=led) == []
    assert led.archived() == []
    assert [e["app_token"] for e in led.probe_set()] == [SURVIVOR_TOKEN]


def test_ld535_a_DELETE_that_answered_success_archives_NOTHING(tmp_path):
    """The sharpest edge of the fence, in the sweep. ``close_out`` reaches ``gone`` two ways:
    the delete answered success (a claim about a drive file — LD-275, **D-55**) or a probe said
    so. Only the second may archive, so this sweep must issue no probe and write no stamp."""
    led = ledger(tmp_path)
    led.record_create(MARKED_TOKEN, H.disposable_title("swept"))
    p = provisioner(delete=[_Response(0)], get=[_Response(1002)])
    assert H.close_out(provisioner=p, ledger=led, attempts=1) == []
    assert led.entries[0]["deleted"] is True
    assert _probes(p) == 0, "the delete's own answer sufficed, so nothing was probed"
    assert led.archived() == [], (
        "and because nothing was probed, nothing may leave the probe set")
    assert [e["app_token"] for e in led.probe_set()] == [MARKED_TOKEN]


def test_ld535_the_sweeps_PROBE_branch_is_the_one_that_archives(tmp_path):
    """The positive control for the test above: same sweep, but the delete answers a lag code
    and the bitable API is asked. That answer, past the horizon, is corroboration — so this is
    the one branch of ``_sweep`` that stamps."""
    led = ledger(tmp_path)
    led.record_create(MARKED_TOKEN, H.disposable_title("probed"))
    _backdate(led, MARKED_TOKEN, H.LAG_HORIZON_SECONDS + 60)
    p = provisioner(delete=[_Response(1061003)], get=[_Response(1002)])
    assert H.close_out(provisioner=p, ledger=led, attempts=1) == []
    assert _probes(p) == 1
    assert [e["app_token"] for e in led.archived()] == [MARKED_TOKEN]


def test_ld535_AN_ARCHIVED_ROW_IS_STILL_COUNTED_and_one_grep_finds_it(tmp_path):
    """AC2's disclosure half. Archival relocates nothing: the row stays in the file with its
    token, title, session and ``last_code``, ``archived()`` names it and ``grep probe_gone_at``
    finds it. ``probe_set()`` and ``archived()`` partition the base half exactly, so a row can
    never fall between them."""
    led = _settled_ledger(tmp_path)
    led.record_create(SURVIVOR_TOKEN, H.disposable_title("still-here"))
    H.orphans(provisioner=provisioner(get=[_Response(1002)]), ledger=led)

    reopened = H.Ledger(led.path)
    assert len(reopened.entries) == 2
    assert ({e["app_token"] for e in reopened.probe_set()}
            | {e["app_token"] for e in reopened.archived()}) == {GONE_TOKEN, SURVIVOR_TOKEN}
    assert not ({e["app_token"] for e in reopened.probe_set()}
                & {e["app_token"] for e in reopened.archived()})
    archived = reopened.archived()[0]
    assert archived["app_token"] == GONE_TOKEN and H.is_disposable_title(archived["title"])
    assert archived["session"] == H.SESSION_ID and archived["last_code"] == 0
    # The grep, run for real over the file a human would grep.
    raw = led.path.read_text(encoding="utf-8")
    assert [line for line in raw.splitlines() if H.PROBE_GONE_FIELD in line]
    assert GONE_TOKEN in raw, "the archived token is still a name somebody can act on"


def test_ld535_MEDIA_NEVER_LEAVES_THE_COUNT_because_it_is_never_stamped(tmp_path):
    """The disclosure doctrine, held across the change: the residue this project has created
    stays *countable rather than merely acknowledged*. A media row is not a bitable object, so
    there is no probe that could corroborate it gone — ``record_probe_gone`` refuses it by
    ``kind``, even when a caller names its token."""
    led = _settled_ledger(tmp_path)
    led.record_media("filMEDIA0000000000000000000", "bitable_file", GONE_TOKEN)
    before = len(led.media())
    led.record_probe_gone([GONE_TOKEN, "filMEDIA0000000000000000000"])
    assert len(led.media()) == before == 1
    assert H.PROBE_GONE_FIELD not in led.media()[0]
    assert len(H.media_residue(ledger=H.Ledger(led.path))) == 1
    # And the archival did happen for the BASE row beside it — so this is a refusal, not a no-op.
    assert [e["app_token"] for e in led.archived()] == [GONE_TOKEN]


def test_ld535_the_stamp_is_MONOTONIC_so_a_re_probe_cannot_re_date_it(tmp_path):
    """``deleted`` is monotonic because a Base does not come back (LD-297); the corroboration of
    its disappearance is monotonic for the same reason."""
    led = _settled_ledger(tmp_path)
    led.record_probe_gone([GONE_TOKEN])
    first = led.archived()[0][H.PROBE_GONE_FIELD]
    led.record_probe_gone([GONE_TOKEN])
    assert led.archived()[0][H.PROBE_GONE_FIELD] == first


def test_ld535_ARCHIVAL_IS_A_LOCKED_MERGE_so_it_cannot_amputate_a_parallel_legs_list(tmp_path):
    """LD-297's lost update, re-cut at the archival step. The instance that stamps holds a
    snapshot taken before the other leg's Base existed; a write-back of that snapshot would
    erase it, and an amputated list is LD-275's unnameable leaked Base."""
    path = tmp_path / "shared.json"
    a = H.Ledger(path)
    a.record_create(A_TOKEN, H.disposable_title("a"))
    a.record_delete(A_TOKEN, 0, True)
    b = H.Ledger(path)                             # a parallel leg opens the SAME ledger
    b.record_create(B_TOKEN, H.disposable_title("b"))
    b.record_delete(B_TOKEN, 1061003, False)       # B leaks: its delete never landed
    a.record_probe_gone([A_TOKEN])                 # A archives on a snapshot that predates B

    on_disk = H.Ledger(path)
    assert [e["app_token"] for e in on_disk.entries] == [A_TOKEN, B_TOKEN]
    assert [e["app_token"] for e in on_disk.archived()] == [A_TOKEN]
    assert [e["app_token"] for e in on_disk.probe_set()] == [B_TOKEN]
    assert [e["app_token"] for e in on_disk.survivors()] == [B_TOKEN]


def test_ld535_an_oracle_run_that_corroborates_NOTHING_NEW_writes_nothing(tmp_path):
    """``orphans()`` gained a write; it must not gain a *gratuitous* one. A pass over a leaked
    token leaves the file byte-identical, so the read-only oracle stays read-only whenever it
    has nothing to record."""
    led = ledger(tmp_path)
    led.record_create(SURVIVOR_TOKEN, H.disposable_title("leaked"))
    led.record_delete(SURVIVOR_TOKEN, 1061003, False)
    before = led.path.read_bytes()
    leaked = H.orphans(provisioner=provisioner(get=[_Response(0)]), ledger=led)
    assert [e["app_token"] for e in leaked] == [SURVIVOR_TOKEN]
    assert led.path.read_bytes() == before


def test_ld535_include_archived_RESTORES_THE_PRE_LD535_SWEEP_EXACTLY(tmp_path):
    """AC3's escape hatch, and the reason the narrowing is recoverable rather than lost: the old
    power is one keyword away, and it asks about the whole base half."""
    led = _settled_ledger(tmp_path)
    led.record_probe_gone([GONE_TOKEN])
    assert led.probe_set() == []
    p = provisioner(get=[_Response(0)])
    still = H.orphans(provisioner=p, ledger=led, include_archived=True)
    assert _probes(p) == len(led.entries) == 1
    assert [e["app_token"] for e in still] == [GONE_TOKEN], (
        "with include_archived the resurrected Base is reported, exactly as before LD-535")


def test_ld535_a_LEGACY_ledger_needs_NO_MIGRATION_because_absent_means_probe_it(tmp_path):
    """The fail-safe default, which is why this issue ships no migration step and never touched
    the operator's own file: a row with no stamp — every row of every file written before
    LD-535 — is in the probe set."""
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps([
        {"kind": "base", "app_token": GONE_TOKEN, "title": H.disposable_title("legacy"),
         "created_at": "2026-08-15T18:51:05.696010+00:00", "deleted": True, "last_code": 0},
        {"app_token": MARKED_TOKEN, "title": H.disposable_title("no-kind-field"),
         "deleted": True, "last_code": 0},
        {"kind": "media", "file_token": "filLEGACY000000000000000000",
         "parent_type": "bitable_file", "app_token": GONE_TOKEN},
    ]), encoding="utf-8")
    led = H.Ledger(path)
    assert [e["app_token"] for e in led.probe_set()] == [GONE_TOKEN, MARKED_TOKEN]
    assert led.archived() == [] and len(led.media()) == 1


def test_ld535_the_ORACLES_docstring_states_what_it_used_to_ask_and_what_it_asks_now():
    """Supersession, not a rewrite: LD-275's reason for distrusting a delete's own answer is
    still the reason the fence exists, so it stays in the text beside the new policy — and the
    narrowing is named in the docstring rather than only in a pass doc."""
    doc = _flat(H.orphans.__doc__)
    assert "LD-535" in doc and "LD-275" in doc
    assert "probe set" in doc and "include_archived=True" in doc
    assert "came back" in doc, "the one narrowed class is NAMED where the oracle is read"
    # LD-539: the same class has TWO causes and the docstring must name both — a human
    # restoring the Base, and a `gone` verdict that was never true (a past-horizon `1002`).
    # Transformed, not replaced: LD-535's assertion above is unchanged.
    assert "recycle bin" in doc and "past-horizon" in doc, (
        "the narrowed class names only one of its two causes — a wrong past-horizon `1002` "
        "presents as the same shape and must be named beside the human restore (LD-539)")
    assert "no ``D-`` ruling needed" in doc, (
        "the ruling LD-535 asked for is unchanged by the widening and must stay stated")
    assert "claim about a *drive file*" in doc, (
        "the pre-existing reason — a delete's answer is about a drive FILE — is preserved")


def test_ld535_the_LEDGER_docstring_keeps_the_merge_law_and_adds_the_archival_one():
    doc = _flat(H.Ledger.__doc__)
    assert "LD-297" in doc and "merge" in doc.lower() and "lock" in doc.lower()
    assert "LD-535" in doc and "countable rather than merely acknowledged" in doc
    assert "record_probe_gone" in doc


def test_ld535_record_media_still_says_PERMANENT_and_now_says_UNARCHIVABLE_too():
    doc = _flat(H.Ledger.record_media.__doc__)
    assert "Permanent by construction" in doc and "no verb it could report" in doc
    assert "LD-535" in doc and "never stamped" in doc


def test_ld535_the_stamp_has_EXACTLY_ONE_writer_in_the_harness():
    """The fence is only a fence if it cannot be walked around. Every assignment of the field
    is inside ``record_probe_gone``, so the three refusals apply to every archival there is."""
    source = _HARNESS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    writer = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "record_probe_gone")
    inside = {id(node) for node in ast.walk(writer)}
    assignments = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Subscript)
                   and isinstance(node.ctx, ast.Store)
                   and isinstance(node.slice, ast.Name)
                   and node.slice.id == "PROBE_GONE_FIELD"]
    assert assignments, "the field must actually be written somewhere"
    assert all(id(node) in inside for node in assignments), (
        "PROBE_GONE_FIELD is assigned outside record_probe_gone — the fence has a bypass")


def test_ld535_a_HAND_EDITED_media_row_reading_deleted_true_is_STILL_refused_by_kind(tmp_path):
    """The ``kind`` refusal, pinned on its own.

    ``record_probe_gone``'s three refusals overlap: a media row written by
    :meth:`Ledger.record_media` carries no ``deleted`` field at all, so the survivor refusal
    already stops it and the ``kind`` refusal never gets to speak. That overlap is exactly what
    lets a fence rot unnoticed, so the ``kind`` half is pinned here against the one shape that
    reaches it.

    And that shape is not exotic. A media row carries the ``app_token`` of the **Base it was
    attached to** — so archiving that Base names its media rows too, and the only thing standing
    between a base-token archival and a stamped media row is the ``kind`` check. The
    ``deleted: true`` below is hand-applied (``record_media`` writes no such field, which is the
    other, shadowing fence) purely to let the ``kind`` half speak. Media is not a bitable object;
    no probe can corroborate it gone; the count is a disclosure and it stays whole whatever the
    file says."""
    led = ledger(tmp_path)
    led.record_media("filFORGED000000000000000000", "bitable_file", GONE_TOKEN)
    for entry in led._entries:
        entry["deleted"] = True                      # the corruption, applied by hand
    led._flush()
    led.record_probe_gone([GONE_TOKEN])              # the PARENT Base's token — the normal call
    reopened = H.Ledger(led.path)
    assert len(reopened.media()) == 1
    assert H.PROBE_GONE_FIELD not in reopened.media()[0]
    assert len(H.media_residue(ledger=reopened)) == 1
