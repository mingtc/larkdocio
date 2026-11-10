"""Offline unit tests for the leak-proof Sheets self-provision harness
(LD-112).

The harness (``tests/sheets_write_harness.py``) promotes the LD-107 spike's proven
``disposable()`` lifecycle (``dev/sheets-write-spike/probes/_lib.py``) into reusable
test infrastructure — the Sheets twin of the docx ``tests/write_harness.py`` /
``tests/test_live_write_harness.py`` W0 gate. It **create → populate → mutate →
verify → DELETE-in-``finally`` → not-found re-query**, records every created token to
a **persisted ledger**, and audits with a **zero-orphan close-out**.

Everything here is **offline** (a duck-typed fake gateway, an injected raw-``request``
double, a temp-file ledger — no network). The binding **live** create→delete→close-out
cycle on a real disposable is ``tests/test_live_sheets_write_harness.py`` (``live_write``),
gated on ``LARK_WRITE_APP_*`` and skipped by default.

The AC mapping:

* **AC1** — ``disposable()`` create → yield → delete-in-``finally`` (fires on BOTH the
  success and the exception path), ledger records create + marks deleted;
* **AC2** — zero-orphan close-out re-queries EVERY ledger token; a survivor fails loudly;
* **AC3** — disposables only (D7): no code path references ``LARKDOCIO_SCRATCH_SHEET`` /
  the canary / the zoo as a write/delete target; value writes bind to the self-provisioned
  token; titles carry the grep-able ``larkdocio-harness-DISPOSABLE-<nonce>`` prefix;
* **AC4** — the create (v3) / delete (drive v1) wire shapes (the SHEETS.md ops rows); the
  matrix guard (``tests/test_sheets_md_matrix.py``) enforces the row update;
* **the amplifier** — an injected mid-lifecycle crash still deletes; a forced-survivor
  ledger makes the close-out bite; an idempotent double-delete is handled, not a crash;
  a simulated delete failure leaves the token flagged in the ledger (never silently dropped).
"""
import json

import pytest

import sheets_write_harness as H
from sheets_write_harness import (
    DISPOSABLE_TITLE_PREFIX,
    HarnessError,
    Ledger,
    OrphanLeakError,
    SheetsLifecycleGateway,
    close_out,
    disposable,
    disposable_title,
    is_disposable_title,
)
from larkdocio.errors import LarkAPIError


# --------------------------------------------------------------------------- #
# Test doubles (offline — no network).                                          #
# --------------------------------------------------------------------------- #

class FakeGateway:
    """A duck-typed stand-in for :class:`SheetsLifecycleGateway`.

    Mints tokens on create, tracks which are "alive", records every call, and
    models the real API's idempotent double-delete (a gone token → ``1310249``).
    ``refuse_delete`` simulates a delete that fails (a non-``0``, non-not-found
    code) so the token stays alive AND flagged in the ledger.
    """

    def __init__(self):
        self._n = 0
        self.live = set()
        self.calls = []
        self.refuse_delete = set()
        self.delete_failure_code = 1310213
        self.fail_create = False

    def create_spreadsheet(self, title, *, folder_token=None):
        if self.fail_create:
            self.calls.append(("create", title, None))
            return {"code": 1310213, "msg": "create failed (simulated)", "data": {}}
        self._n += 1
        tok = f"DISPOSABLE-TOKEN-{self._n}"
        self.live.add(tok)
        self.calls.append(("create", title, tok))
        return {"code": 0, "data": {"spreadsheet": {"spreadsheet_token": tok, "title": title}}}

    def delete_spreadsheet(self, spreadsheet_token):
        token = spreadsheet_token
        self.calls.append(("delete", token))
        if token in self.refuse_delete:
            return {"code": self.delete_failure_code, "msg": "delete refused (simulated)"}
        if token in self.live:
            self.live.discard(token)
            return {"code": 0, "data": {}}
        return {"code": H.NOT_FOUND_CODE, "msg": "not found"}  # idempotent double-delete

    def query_spreadsheet(self, token):
        self.calls.append(("query", token))
        if token in self.live:
            return {"code": 0, "data": {"sheets": [{"sheet_id": "sht_first"}]}}
        return {"code": H.NOT_FOUND_CODE, "msg": "spreadsheet not found (deleted)"}

    # -- introspection helpers ------------------------------------------------ #
    def ops(self, kind):
        return [c for c in self.calls if c[0] == kind]


class RecordingRequest:
    """A ``(method, path, body, params) -> (status, dict)`` double for testing the
    real :class:`SheetsLifecycleGateway`'s method/path/body wire shapes offline."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, method, path, body=None, params=None):
        self.calls.append({"method": method, "path": path, "body": body, "params": params})
        return 200, self._responses[len(self.calls) - 1]


#: The destination these offline cases hand the gateway. An explicit token rather than the
#: environment's: nothing here creates anything on any tenant, so the disposables folder is
#: neither needed nor consulted, and a skip would be noise rather than protection. The key
#: still travels, so what these cases exercise is the shape a live run sends.
DEST = "fldrOFFLINEDOUBLEDESTINATION"


class RecordingLifecycleClient:
    """A stand-in for the shipped client's two lifecycle methods, recording each call.

    The gateway no longer builds create/delete requests itself (LD-176) — it delegates to
    ``SheetsWriteClient``, whose byte-exact wire shapes are pinned in
    ``tests/test_sheets_lifecycle.py`` (against the write spike's captured live create) and
    again *through this gateway* there. What is left to prove **here** is the delegation and
    the two adaptations the harness needs, which is what this double isolates.
    """

    def __init__(self, *, delete_error=None):
        self.calls = []
        self._delete_error = delete_error
        self._n = 0

    def create_spreadsheet(self, title="", *, folder_token):
        self._n += 1
        # The destination is RECORDED, so a gateway that stopped passing one is visible here
        # rather than silently filing a workbook where nobody can see it.
        self.calls.append(("create_spreadsheet", title, folder_token))
        return {"spreadsheet_token": f"TOK{self._n}", "title": title,
                "url": f"https://example.invalid/sheets/TOK{self._n}"}

    def delete_spreadsheet(self, spreadsheet_token):
        self.calls.append(("delete_spreadsheet", spreadsheet_token))
        if self._delete_error is not None:
            raise self._delete_error
        return {}


def _ledger(tmp_path):
    return Ledger(tmp_path / "harness_ledger.json")


# --------------------------------------------------------------------------- #
# AC1 — disposable(): create → yield → delete-in-finally (both paths)           #
# --------------------------------------------------------------------------- #

def test_disposable_creates_records_yields_and_deletes_on_success(tmp_path):
    gw, led = FakeGateway(), _ledger(tmp_path)

    with disposable(gw, led, title="larkdocio-harness-DISPOSABLE-happy") as d:
        assert d.token == "DISPOSABLE-TOKEN-1"
        assert d.first_sheet_id == "sht_first"
        # created + ledgered, not yet deleted while the body runs.
        assert gw.ops("create")
        assert led.entries()[0]["spreadsheet_token"] == d.token
        assert led.entries()[0]["deleted"] is False
        assert d.token in gw.live

    # finally fired: deleted on the wire AND marked in the ledger.
    assert ("delete", "DISPOSABLE-TOKEN-1") in gw.calls
    assert gw.live == set()
    assert led.entries()[0]["deleted"] is True


def test_disposable_deletes_in_finally_even_when_body_raises(tmp_path):
    """A mid-``with`` crash still deletes the disposable — the ``finally`` proof."""
    gw, led = FakeGateway(), _ledger(tmp_path)

    with pytest.raises(RuntimeError, match="boom"):
        with disposable(gw, led) as d:
            tok = d.token
            raise RuntimeError("boom")

    assert ("delete", tok) in gw.calls
    assert gw.live == set()
    assert led.entries()[0]["deleted"] is True


def test_disposable_create_failure_raises_loudly_and_deletes_nothing(tmp_path):
    """A failed create is loud (never a silent yield of a bogus token) and leaves
    no delete attempt / no ledger entry behind."""
    gw, led = FakeGateway(), _ledger(tmp_path)
    gw.fail_create = True

    with pytest.raises(HarnessError):
        with disposable(gw, led):
            pass

    assert gw.ops("delete") == []
    assert led.entries() == []


# --------------------------------------------------------------------------- #
# AC2 — zero-orphan close-out re-queries every token; a survivor fails loudly    #
# --------------------------------------------------------------------------- #

def test_close_out_all_gone_is_clean(tmp_path):
    gw, led = FakeGateway(), _ledger(tmp_path)
    for _ in range(3):
        with disposable(gw, led):
            pass

    report = close_out(gw, led)

    assert report.ledger_count == 3
    assert report.orphans == []
    assert report.all_clean is True
    report.raise_if_orphans()  # no-op when clean


def test_close_out_requeries_every_ledger_token(tmp_path):
    gw, led = FakeGateway(), _ledger(tmp_path)
    created = []
    for _ in range(3):
        with disposable(gw, led) as d:
            created.append(d.token)

    gw.calls.clear()
    close_out(gw, led)

    queried = [c[1] for c in gw.calls if c[0] == "query"]
    assert queried == created  # every ledger token re-queried, in order


def test_close_out_flags_a_simulated_survivor(tmp_path):
    """A ledger token that still resolves (a leak) is reported as an orphan — the
    close-out bites (forced-survivor amplifier)."""
    gw, led = FakeGateway(), _ledger(tmp_path)
    with disposable(gw, led) as d:
        survivor = d.token
    # Force a leak: resurrect the token behind the harness's back.
    gw.live.add(survivor)

    report = close_out(gw, led)

    assert report.all_clean is False
    assert [o["token"] for o in report.orphans] == [survivor]
    assert report.orphans[0]["still_resolves"] is True


def test_close_out_raise_if_orphans_is_loud_and_names_the_survivor(tmp_path):
    gw, led = FakeGateway(), _ledger(tmp_path)
    with disposable(gw, led) as d:
        survivor = d.token
    gw.live.add(survivor)

    report = close_out(gw, led)
    with pytest.raises(OrphanLeakError, match=survivor):
        report.raise_if_orphans()


# --------------------------------------------------------------------------- #
# AC3 — disposables only (D7)                                                    #
# --------------------------------------------------------------------------- #

_FORBIDDEN_TARGETS = (
    "LARKDOCIO_SCRATCH_SHEET",
    "LARKDOCIO_CANARY_DOC",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_BLOCKZOO_WIKI",
    "scratch_sheet_url",
    "canary_doc_url",
    "blockzoo_doc_url",
)


def test_harness_never_references_a_non_disposable_env_target():
    """Static D7 guard: the harness source must not name the canary / scratch-sheet /
    zoo env targets (or their getters) — it can ONLY act on tokens it self-provisions,
    so no future edit can point a write/delete at a real document."""
    from pathlib import Path

    src = Path(H.__file__).read_text(encoding="utf-8")
    for name in _FORBIDDEN_TARGETS:
        assert name not in src, (
            f"harness references {name!r} — a non-disposable target; the harness must "
            f"only ever act on self-provisioned disposables (D7)."
        )


def test_disposable_title_is_grep_able_and_prefixed():
    title = disposable_title()
    assert title.startswith(DISPOSABLE_TITLE_PREFIX)
    assert DISPOSABLE_TITLE_PREFIX == "larkdocio-harness-DISPOSABLE-"
    assert is_disposable_title(title)
    assert not is_disposable_title("some real project document")


def test_disposable_default_title_is_a_disposable_title(tmp_path):
    gw, led = FakeGateway(), _ledger(tmp_path)
    with disposable(gw, led) as d:
        assert is_disposable_title(d.title)


def test_value_writes_bind_to_the_self_provisioned_token(tmp_path):
    """The Disposable's populate/verify legs always target ITS OWN token — there is
    no API surface that accepts an externally-supplied doc token/URL."""

    class SpyWriter:
        def __init__(self):
            self.puts = []
            self.reads = []

        def put_values(self, spreadsheet_token, a1_range, values):
            self.puts.append((spreadsheet_token, a1_range, values))
            return {"revision": 1}

        def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
            self.reads.append((spreadsheet_token, a1_range))
            return [["v"]]

    gw, led, writer = FakeGateway(), _ledger(tmp_path), SpyWriter()
    with disposable(gw, led, writer=writer) as d:
        d.put_values("sht_first!A1:A1", [["v"]])
        d.read_values("sht_first!A1:A1")

    assert writer.puts[0][0] == d.token   # write bound to the disposable's own token
    assert writer.reads[0][0] == d.token  # verify read bound to the same token


def test_value_write_leg_requires_a_writer(tmp_path):
    """Calling the value-write leg with no writer wired is a clear error, not a
    silent no-op."""
    gw, led = FakeGateway(), _ledger(tmp_path)
    with disposable(gw, led) as d:
        with pytest.raises(HarnessError):
            d.put_values("sht_first!A1:A1", [["v"]])


# --------------------------------------------------------------------------- #
# AC3 (LD-118, S5) — the STYLE-write leg. The style leg (like the value legs)    #
# always binds to the disposable's OWN token (D7) and needs an injected styler.  #
# --------------------------------------------------------------------------- #

class SpyStyler:
    """A duck-typed stand-in for the shipped client's ``put_style`` — records the token +
    range + style every ``put_style`` targets (so the D7 own-token binding is
    provable offline)."""

    def __init__(self):
        self.styles = []

    def put_style(self, spreadsheet_token, a1_range, style):
        self.styles.append((spreadsheet_token, a1_range, style))
        return {"code": 0, "data": {"updates": {"revision": 2}}}


def test_style_write_leg_binds_to_the_self_provisioned_token(tmp_path):
    """The Disposable's style leg always targets ITS OWN token — no API surface
    accepts an externally-supplied doc token/URL (the value-leg D7 guarantee,
    extended to the S5 style leg)."""
    gw, led, styler = FakeGateway(), _ledger(tmp_path), SpyStyler()
    with disposable(gw, led, styler=styler) as d:
        d.put_style("sht_first!A1:A1", {"font": {"bold": True}})

    assert styler.styles[0][0] == d.token   # style write bound to the disposable's own token
    assert styler.styles[0][1] == "sht_first!A1:A1"
    assert styler.styles[0][2] == {"font": {"bold": True}}


def test_style_write_leg_requires_a_styler(tmp_path):
    """Calling the style leg with no styler wired is a clear error, not a silent no-op
    (mirrors the value-leg guard)."""
    gw, led = FakeGateway(), _ledger(tmp_path)
    with disposable(gw, led) as d:
        with pytest.raises(HarnessError):
            d.put_style("sht_first!A1:A1", {"font": {"bold": True}})


def test_mid_style_crash_still_deletes_the_disposable(tmp_path):
    """An exception mid-style-write still fires the finally-delete — the harness leaves
    nothing behind on a crash, on the style leg too."""

    class ExplodingStyler:
        def put_style(self, *a, **k):
            raise RuntimeError("style exploded")

    gw, led = FakeGateway(), _ledger(tmp_path)
    with pytest.raises(RuntimeError, match="style exploded"):
        with disposable(gw, led, styler=ExplodingStyler()) as d:
            tok = d.token
            d.put_style("sht_first!A1:A1", {"font": {"bold": True}})  # explodes

    assert ("delete", tok) in gw.calls
    assert led.entries()[0]["deleted"] is True
    assert gw.live == set()


# --------------------------------------------------------------------------- #
# AC4 — the lifecycle seams: create/delete DELEGATE to the shipped client        #
# (LD-176 — the harness's raw create/delete is gone; the wire shapes are pinned   #
# in tests/test_sheets_lifecycle.py), and the close-out re-query is still raw.   #
# --------------------------------------------------------------------------- #

def test_gateway_create_delegates_to_the_shipped_create_spreadsheet():
    client = RecordingLifecycleClient()
    gw = SheetsLifecycleGateway(RecordingRequest([]), client=client)

    resp = gw.create_spreadsheet("larkdocio-harness-DISPOSABLE-x", folder_token=DEST)

    assert client.calls == [("create_spreadsheet", "larkdocio-harness-DISPOSABLE-x", DEST)]
    assert resp["spreadsheet_token"] == "TOK1"


def test_gateway_delete_delegates_to_the_shipped_delete_spreadsheet():
    client = RecordingLifecycleClient()
    gw = SheetsLifecycleGateway(RecordingRequest([]), client=client)

    resp = gw.delete_spreadsheet("TOK123")

    assert client.calls == [("delete_spreadsheet", "TOK123")]
    assert resp["code"] == 0


def test_gateway_delete_turns_the_shipped_typed_error_into_a_ledger_code():
    """The one adaptation: the shipped delete is loud, a ``finally`` must be quiet enough to
    record. A gone token comes back as the gone CODE (so the ledger marks it deleted); any
    other failure comes back as its own code (so the token stays flagged)."""
    gone = SheetsLifecycleGateway(
        RecordingRequest([]),
        client=RecordingLifecycleClient(delete_error=LarkAPIError(
            "deleted", code=H.NOT_FOUND_CODE, msg="Path param :spreadsheet_token is deleted")),
    )
    assert gone.delete_spreadsheet("TOK")["code"] == H.NOT_FOUND_CODE

    refused = SheetsLifecycleGateway(
        RecordingRequest([]),
        client=RecordingLifecycleClient(delete_error=LarkAPIError(
            "nope", code=1310213, msg="no permission")),
    )
    assert refused.delete_spreadsheet("TOK")["code"] == 1310213


def test_gateway_with_no_client_refuses_loudly_instead_of_pretending():
    """A gateway built with no lifecycle client cannot create or delete — and says so, rather
    than silently doing nothing (which would leave a gate believing it had a disposable)."""
    gw = SheetsLifecycleGateway(RecordingRequest([]))
    with pytest.raises(HarnessError) as exc:
        gw.create_spreadsheet("larkdocio-harness-DISPOSABLE-x", folder_token=DEST)
    assert "SheetsWriteClient" in str(exc.value)


def test_gateway_query_hits_v3_sheets_query():
    req = RecordingRequest([{"code": 0, "data": {"sheets": [{"sheet_id": "s1"}]}}])
    gw = SheetsLifecycleGateway(req)

    gw.query_spreadsheet("TOK123")

    call = req.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/open-apis/sheets/v3/spreadsheets/TOK123/sheets/query"


# --------------------------------------------------------------------------- #
# The STYLE-write wire shape MOVED (LD-188). It was asserted here against the      #
# harness's own `SheetsStyleWriter`; that class was promoted into                   #
# `SheetsWriteClient.put_style` / `.batch_update_styles`, so its wire shape, its    #
# Start:End (90202) guard and its loud-on-non-zero posture are now pinned in        #
# tests/test_sheets_style_write.py against the SHIPPED client — byte-exact vs the   #
# same captures. What stays here is the harness's own concern: that the style leg   #
# binds to the disposable's OWN token and refuses without a styler (above).         #
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# The amplifier — forced-failure coverage                                       #
# --------------------------------------------------------------------------- #

def test_mid_populate_crash_still_deletes_the_disposable(tmp_path):
    """An exception mid-populate (the writer blows up) still fires the finally-delete
    — the harness leaves nothing behind on a crash (the ``finally`` proof, live-shape)."""

    class ExplodingWriter:
        def put_values(self, *a, **k):
            raise RuntimeError("populate exploded")

    gw, led = FakeGateway(), _ledger(tmp_path)
    with pytest.raises(RuntimeError, match="populate exploded"):
        with disposable(gw, led, writer=ExplodingWriter()) as d:
            tok = d.token
            d.put_values("sht_first!A1:A1", [["v"]])  # explodes

    assert ("delete", tok) in gw.calls
    assert led.entries()[0]["deleted"] is True
    assert gw.live == set()


def test_simulated_delete_failure_leaves_token_flagged_in_ledger(tmp_path):
    """A delete that FAILS (a non-zero, non-not-found code) must leave the token in
    the ledger flagged deleted=False with its failure code — never silently dropped."""
    gw, led = FakeGateway(), _ledger(tmp_path)

    # Create first so we know the token, then make its delete refuse.
    with disposable(gw, led) as d:
        gw.refuse_delete.add(d.token)
        tok = d.token

    entry = led.entries()[0]
    assert entry["spreadsheet_token"] == tok
    assert entry["deleted"] is False               # flagged, not dropped
    assert entry["delete_code"] == gw.delete_failure_code
    # and the audit catches the leak (the sheet is still alive).
    report = close_out(gw, led)
    assert report.all_clean is False


def test_idempotent_double_delete_is_handled_not_a_crash(tmp_path):
    """Deleting an already-gone token (the API returns 1310249) is handled — the
    ledger stays marked deleted and nothing raises."""
    gw, led = FakeGateway(), _ledger(tmp_path)
    with disposable(gw, led) as d:
        tok = d.token
    # disposable() already deleted it once; a second explicit delete must be a no-crash.
    resp = gw.delete_spreadsheet(tok)
    led.record_delete(tok, resp.get("code"))

    assert resp["code"] == H.NOT_FOUND_CODE
    assert led.entries()[0]["deleted"] is True  # a not-found delete == gone


# --------------------------------------------------------------------------- #
# The persisted ledger                                                          #
# --------------------------------------------------------------------------- #

def test_ledger_persists_to_disk_and_reloads_across_instances(tmp_path):
    """The ledger is PERSISTENT — a fresh Ledger over the same path sees prior
    tokens (so a close-out in a later process can still audit them)."""
    path = tmp_path / "ledger.json"
    led = Ledger(path)
    led.record_create("TOK-A", "larkdocio-harness-DISPOSABLE-a")
    led.record_delete("TOK-A", 0)

    assert path.exists()
    reloaded = Ledger(path)
    assert reloaded.tokens() == ["TOK-A"]
    assert reloaded.entries()[0]["deleted"] is True
    # and it is real JSON on disk (auditable by a human / a sweep script).
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk[0]["spreadsheet_token"] == "TOK-A"


def test_ledger_records_create_before_delete_marks_it(tmp_path):
    led = _ledger(tmp_path)
    led.record_create("TOK-B", "larkdocio-harness-DISPOSABLE-b")

    assert led.entries()[0]["deleted"] is False
    assert led.entries()[0]["delete_code"] is None

    led.record_delete("TOK-B", 0)
    assert led.entries()[0]["deleted"] is True
    assert led.entries()[0]["delete_code"] == 0
