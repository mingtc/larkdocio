"""THE SINGLE LIVE VIEW ARM — persistent filters, verified by read-back (LD-264).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against a self-provisioned disposable, and nothing else.** Every Base this arm touches it made
itself through :func:`base_write_harness.disposable_base`, and the harness records it in the
ledger the instant it exists. This module never reads ``LARKDOCIO_SCRATCH_BASE`` — that Base
holds the only hand-authored ``Lookup`` / ``Email`` / ``Stage`` fields in existence and is a READ
fixture — and the offline companion checks that statically.

**What it proves that no offline test can.**

* the **loop the seat proved end to end**: create view → set filter → READ BACK → alter filter →
  READ BACK → delete view, all through the shipped plan gate, on a real Base;
* that a filter set through this library **really persists** — the ``property.filter_info`` reads
  back with the conditions that were sent, plus the server's own ``condition_id`` and
  ``field_type``, which the shipped normalisation drops **by name**;
* **THE SWALLOW CONTROL.** A sibling key on the same endpoint — ``property.group_info`` — answers
  ``code:0`` and reads back ``property: null``. The control is what makes the positive result
  mean something: it demonstrates, against the live API, that a read-back verification detects a
  swallowed write, and therefore that the filter's read-back is evidence rather than ceremony;
* **AC3's 2-call vocabulary probe (O5″).** The bundled claim moved *two* variables at once —
  ``field_name`` **and** snake_case operators — so the shipped refusal message could not honestly
  blame either. Two calls separate them: ``field_id`` + a snake_case operator, and ``field_name``
  + a camelCase operator. The result is written to a capture and the register row is corrected
  from it.

The two probe legs are **raw** calls on purpose: the shipped client cannot express either shape
(that is the whole point of the typed dialect boundary), so the probe rides the library's own
raw-HTTP core rather than a hole cut in the client.

**Gentle.** Around fifteen calls at ≥1.2 s spacing. Rate limits are not probed.

**Skips loudly, never silently.**
"""
import json
import os
import pathlib
import time
import urllib.request

import base_write_harness
import capture_sink
import pytest

from log_reading_apply import reading_the_log
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.view_filters import (
    Condition,
    FieldId,
    FieldName,
    FieldRegistry,
    FilterSpec,
    view_filter,
)
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.base.view_plan import (
    clear_view_hidden_fields,
    create_view,
    delete_view,
    set_view_filter,
    set_view_hidden_fields,
)
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    api_base,
    fetch_tenant_access_token,
)

# This gate's subject is the LOG — which entry landed, which refused, with which typed
# reason — not the return-vs-raise policy (pinned offline in
# tests/test_apply_refusal_policy.py, proved live in
# tests/test_live_write_refusal_policy_gate.py). So it opts into partial application
# once, here, the same way the offline log-reading suites do.
schema_apply = reading_the_log(schema_apply)

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The select column a **fresh** disposable Base already carries (`options: []` until a record
#: writes one). LD-318's fixture route: `POST …/fields` is answering `9499` externally (LD-329),
#: so the options are created by WRITING RECORDS with their names, not by authoring a column.
_SELECT_COLUMN = "Single option"

#: Where AC3's probe leaves its evidence. Committed, sanitized, and cited by the register row
#: this story corrects.
VOCABULARY_CAPTURE = (pathlib.Path(__file__).resolve().parents[1] /
                      "dev" / "base-study" / "captures" /
                      "ld264-01-view-filter-vocabulary.json")

try:  # pragma: no cover - the loader is the canary's, and is optional here
    import canary_support

    canary_support.load_env()
except Exception:  # pragma: no cover - a missing loader must not fail collection
    pass


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


class _RawProbe(CredentialedRawHttpClient):
    """The library's own raw-HTTP core, used for the two shapes the typed client REFUSES.

    It exists so the probe cannot be mistaken for a shipped capability: nothing in
    ``src/larkdocio`` can build a ``group_info`` body or a wrong-dialect filter, and this class
    lives in ``tests/``.
    """

    def __init__(self, app_id, app_secret, domain="larksuite.com"):
        self._app_id, self._app_secret, self._domain = app_id, app_secret, domain
        self._base = api_base(domain)
        self._urlopen = urllib.request.urlopen
        self._token_fetcher = fetch_tenant_access_token
        self._timeout = 30
        self._token = None

    def call(self, method, path, body=None):
        time.sleep(1.2)                      # the pace the three probe packs sustained
        return self._send(method, path, body=body)


def _raw():
    from larkdocio.common.auth import get_write_credentials

    return _RawProbe(*get_write_credentials())


def test_this_arm_NEVER_TOUCHES_THE_CONFIGURED_SCRATCH_BASE(credentials):
    """The binding fence, asserted at runtime as well as statically: whatever
    ``LARKDOCIO_SCRATCH_BASE`` holds, the Base this arm writes is one it created."""
    configured = (os.environ.get("LARKDOCIO_SCRATCH_BASE") or "").strip()
    with base_write_harness.disposable_base() as (app_token, _table_id, title):
        assert base_write_harness.is_disposable_title(title)
        assert app_token, "the harness always yields a token"
        if configured:
            assert app_token not in configured and configured not in app_token, (
                "the view arm must never write the configured READ fixture")


def test_THE_LOOP_create_view_set_filter_READ_BACK_alter_READ_BACK_delete(credentials):
    """The maintainer's top functional ask, end to end and verified at every step by a **read-back**."""
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        # A field to filter on — resolved by NAME against the read registry, which is the
        # consumer-facing path (AC4).
        registry = FieldRegistry.from_read_client(read, app_token, table_id)
        assert registry.exhaustive is True
        name = registry.names[0]
        first = view_filter(registry.resolve(FilterSpec(
            conditions=(Condition(FieldName(name), "isNotEmpty"),))))
        second = view_filter(registry.resolve(FilterSpec(
            conditions=(Condition(FieldName(name), "isEmpty"),))))

        # ---- create ------------------------------------------------------ #
        made = schema_apply(schema_dry_run([
            create_view(app_token, table_id, "ld264-filtered", "grid")]),
            client=schema, read_client=read)
        assert made.entries[0].outcome == "applied", made.entries[0].refusal
        view_id = made.entries[0].read_back["view_id"]

        # ---- set the filter, and READ IT BACK ---------------------------- #
        set_log = schema_apply(schema_dry_run([
            set_view_filter(app_token, table_id, view_id, first)]),
            client=schema, read_client=read)
        entry = set_log.entries[0]
        assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
        assert entry.read_back["echoes"] is True
        assert entry.read_back["persisted"] == first.to_dict()
        print(f"\nfilter persisted on view {view_id}: {entry.read_back['persisted']}")

        # ---- ALTER it, and read back the SECOND filter, not a merge ------- #
        alter_log = schema_apply(schema_dry_run([
            set_view_filter(app_token, table_id, view_id, second)]),
            client=schema, read_client=read)
        altered = alter_log.entries[0]
        assert altered.outcome == "applied", altered.refusal and altered.refusal.detail
        assert altered.read_back["persisted"] == second.to_dict(), (
            "the second read-back must reflect the SECOND filter and not a merge of both")

        # ---- delete, verified by absence from the listing ----------------- #
        gone = schema_apply(schema_dry_run([delete_view(app_token, table_id, view_id)]),
                            client=schema, read_client=read)
        assert gone.entries[0].outcome == "applied", gone.entries[0].refusal
        assert gone.entries[0].read_back["gone"] is True
        assert view_id not in {v.view_id for v in read.list_views(app_token, table_id)}


def test_LD438_THE_HIDDEN_FIELDS_LOOP_set_READ_BACK_move_clear_READ_BACK(credentials):
    """**LD-438's live arm, and it is a loop with a CONTROL in it.**

    set → read back → **move** → hold a set of two → **clear** → read back, all through the
    shipped plan gate on a Base this harness made and then deletes. The move is what makes the
    first read-back mean something (a stuck value would look identical to a landed one), and
    the **invented-key control** at the end is what makes an ACCEPTANCE mean something: the same
    endpoint answers ``code:0`` to a key it stores nothing for, so a run without the control
    cannot tell a real write from a swallowed one.

    The clear is the arm's sharpest assertion: ``[]`` reads the view's ``property`` back as
    ``null``, and the shipped read-back must report that as **applied**. An implementation that
    treated an empty list as *not asked for* would leave the columns hidden and still say so.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    probe = _raw()

    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        fields = read.list_fields(app_token, table_id)
        assert len(fields) >= 4, "the disposable always ships more than three columns"
        # THE FIRST COLUMN IS THE PRIMARY FIELD AND LARK REFUSES TO HIDE IT — measured below,
        # in its own arm. Everything the positive loop hides is therefore fields[1:].
        primary = fields[0].field_id
        alpha, beta, gamma = (f.field_id for f in fields[1:4])

        view_id = schema.create_view(app_token, table_id, "ld438-hidden", "grid")

        # ---- THE PRIMARY-FIELD REFUSAL, measured FIRST because it explains an old
        #      observation. `1254001` on this route is not a mystery and not a body-shape
        #      accident: Lark answers "the primary field cannot be set as a hidden type" and
        #      NAMES the offending id. This is the same code the 2026-08-03 seat addendum saw,
        #      and this arm is what turns that from an unreproduced contradiction into a rule.
        refused_primary = probe.call(
            "PATCH",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}",
            body={"property": {"hidden_fields": [primary]}})
        assert refused_primary.get("code") != 0, refused_primary
        detail = json.dumps(refused_primary)
        assert "primary field" in detail, (
            "the refusal must name the REASON, not merely the code, or the shipped "
            f"disclosure has nothing to quote: {refused_primary}")
        print(f"\nprimary field refused: code={refused_primary.get('code')} "
              f"detail={detail[:300]}")

        # ---- SET, and read it back --------------------------------------- #
        set_log = schema_apply(schema_dry_run([
            set_view_hidden_fields(app_token, table_id, view_id, [alpha])]),
            client=schema, read_client=read)
        entry = set_log.entries[0]
        assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
        assert entry.read_back["persisted_hidden_fields"] == [alpha]
        assert entry.read_back["echoes"] is True

        # ---- MOVE it. A stuck value would mean the first write only LOOKED landed.
        move_log = schema_apply(schema_dry_run([
            set_view_hidden_fields(app_token, table_id, view_id, [beta])]),
            client=schema, read_client=read)
        moved = move_log.entries[0]
        assert moved.outcome == "applied", moved.refusal and moved.refusal.detail
        assert moved.read_back["persisted_hidden_fields"] == [beta], (
            "the second read-back must be the SECOND set, not a merge and not the first")

        # ---- hold a SET of two ------------------------------------------- #
        pair_log = schema_apply(schema_dry_run([
            set_view_hidden_fields(app_token, table_id, view_id, [beta, gamma])]),
            client=schema, read_client=read)
        assert pair_log.entries[0].outcome == "applied"
        assert set(pair_log.entries[0].read_back["persisted_hidden_fields"]) == {beta, gamma}

        # ---- the FILTER is untouched by all of that ----------------------- #
        view = read.get_view(app_token, table_id, view_id)
        assert getattr(view.property, "filter_info", None) is None, (
            "a hidden-fields patch must not invent a filter")

        # ---- CLEAR, and read back the null --------------------------------#
        clear_log = schema_apply(schema_dry_run([
            clear_view_hidden_fields(app_token, table_id, view_id)]),
            client=schema, read_client=read)
        cleared = clear_log.entries[0]
        assert cleared.outcome == "applied", cleared.refusal and cleared.refusal.detail
        assert cleared.read_back["cleared"] is True
        assert cleared.read_back["persisted_hidden_fields"] in (None, [])
        print(f"\nhidden set cleared on view {view_id}: "
              f"{cleared.read_back['persisted_hidden_fields']!r}")

        # ---- THE INVENTED-KEY CONTROL, so an acceptance is known to be real #
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"
        control = probe.call("PATCH", path,
                             body={"property": {"zzz_ld438_control": [alpha]}})
        assert control.get("code") == 0, (
            "the control's whole point is that this endpoint ACCEPTS a key it stores "
            f"nothing for: {control}")
        after = read.get_view(app_token, table_id, view_id)
        assert getattr(getattr(after, "property", None), "hidden_fields", None) in (None, []), (
            "an invented key must change nothing — if it did, the positive results above "
            "would be measuring something other than what they claim")

        # ---- an UNKNOWN FIELD ID is RELAYED, not predicted ---------------- #
        relayed = probe.call("PATCH", path,
                             body={"property": {"hidden_fields": ["fldNONEXISTENT"]}})
        # The numeric code is QUOTED, never pinned (LD-417 AC10): what is asserted is that the
        # server REFUSED — which is the fact the shipped relay decision rests on.
        assert relayed.get("code") != 0, (
            "this endpoint validates its own payload rather than swallowing it; today's "
            f"answer is 1254044 'Field id is not found.' — got {relayed}")
        print(f"\nunknown field id relayed: code={relayed.get('code')} "
              f"msg={relayed.get('msg')!r}")

        schema.delete_view(app_token, table_id, view_id)


def test_THE_SWALLOW_CONTROL_group_info_answers_code_0_and_persists_NOTHING(credentials):
    """**The negative control, live.** Without it the filter's read-back proves nothing: a
    verification that has never seen a failure is not known to detect one."""
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    probe = _raw()

    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        fields = read.list_fields(app_token, table_id)
        field_id = fields[0].field_id
        view_id = schema.create_view(app_token, table_id, "ld264-swallow", "grid")

        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"
        answer = probe.call("PATCH", path, body={
            "property": {"group_info": [{"field_id": field_id, "desc": False}]}})
        assert str(answer.get("code")) == "0", answer

        # Read back RAW, deliberately: the pinned SDK's typed view model carries only
        # filter_info / hidden_fields / hierarchy_config, so asking it about group_info could
        # not tell a swallow from a model gap (register row 12's lossy-property class). The
        # raw body is what settles it.
        raw = probe.call("GET", path)
        prop = ((raw.get("data") or {}).get("view") or {}).get("property")
        assert not (prop or {}).get("group_info"), (
            "THE SWALLOW: code:0 and nothing persisted — which is exactly why this library "
            f"verifies a view write by read-back. property={prop!r}")
        print(f"\nswallow control: group_info code:0, view property reads back {prop!r}")

        # And the positive half on the SAME view, so the control is a control and not a
        # difference between two Bases.
        landed = schema_apply(schema_dry_run([set_view_filter(
            app_token, table_id, view_id,
            view_filter(FilterSpec(conditions=(Condition(
                __import__("larkdocio.base.view_filters", fromlist=["FieldId"]).FieldId(
                    field_id), "isNotEmpty"),))))]),
            client=schema, read_client=read)
        assert landed.entries[0].outcome == "applied", landed.entries[0].refusal
        schema.delete_view(app_token, table_id, view_id)


def test_AC3_THE_2_CALL_VOCABULARY_PROBE_separates_the_key_from_the_operator_case(credentials):
    """O5″'s in-story capture. Two calls, one variable each, against a disposable.

    * **call A** — ``field_id`` + a **snake_case** operator (``is_not``);
    * **call B** — ``field_name`` + a **camelCase** operator (``isNotEmpty``).

    Whatever they answer, the capture records it and the shipped refusal message says only what
    the probe supports. An inconclusive result is a pass; an overstated message is not.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    probe = _raw()

    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        field = read.list_fields(app_token, table_id)[0]
        view_id = schema.create_view(app_token, table_id, "ld264-vocab", "grid")
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"

        def patch(conditions, note):
            body = {"property": {"filter_info": {"conjunction": "and",
                                                 "conditions": [conditions]}}}
            answer = probe.call("PATCH", path, body=body)
            return {"_note": note, "_endpoint": f"…/views/{{view_id}}", "_method": "PATCH",
                    "request": body, "code": answer.get("code"), "msg": answer.get("msg"),
                    "error": answer.get("error")}

        call_a = patch({"field_id": field.field_id, "operator": "is_not", "value": ["x"]},
                       "A: field_id + snake_case operator — isolates OPERATOR CASE")
        call_b = patch({"field_name": field.field_name, "operator": "isNotEmpty", "value": []},
                       "B: field_name + camelCase operator — isolates the KEY")

        a_refused = str(call_a["code"]) != "0"
        b_refused = str(call_b["code"]) != "0"
        verdict = {
            (True, True): "both independently",
            (False, True): "field_name-key alone",
            (True, False): "operator-case alone",
            (False, False): "inconclusive",
        }[(a_refused, b_refused)]

        capture = {
            "_probe": "ld264-view-filter-vocabulary",
            "_note": ("O5″: the bundled probe moved `field_name` and snake_case operators "
                      "at once. These two calls move ONE variable each."),
            "verdict": verdict,
            "steps": [call_a, call_b],
        }
        capture_sink.write_capture(VOCABULARY_CAPTURE,
                                   json.dumps(capture, indent=1) + "\n")
        print(f"\nVOCABULARY PROBE verdict={verdict} "
              f"A={call_a['code']} B={call_b['code']}")

        schema.delete_view(app_token, table_id, view_id)

    from larkdocio.base import view_filters

    assert view_filters.VOCABULARY_PROBE["verdict"] == verdict, (
        "the shipped VOCABULARY_PROBE verdict and the register row's wording are written FROM "
        f"this capture; the probe now says {verdict!r}")


def test_LD318_A_SELECT_FILTER_NAMED_BY_OPTION_NAME_IS_TRANSLATED_AND_HONOURED(credentials):
    """**LD-318's binding live gate — the translated filter is HONOURED, proven by READ-BACK
    and by the ROWS, never by ``code:0``.**

    The consumer's report: an option NAME sailed through ``dry_run`` and died at ``apply`` on
    Lark's own *"the option id of 'Single Option' is not found"*. Both halves are proven here in
    one run, against the same live select column:

    * **the control** — the same filter carrying the option's NAME, sent **without** the
      registry's translation (the shipped path can still express it: a ``FieldId`` plus a raw
      value), is **refused by Lark**, which is the reported bug confirmed rather than trusted;
    * **the fix** — the identical spec run through ``FieldRegistry.resolve()`` goes out carrying
      the ``opt…`` id, and the view's ``property.filter_info`` **reads back** with that id;
    * **the rows** — the view, read through ``search_records(view_id=…)``, returns exactly the
      records whose option matches, against the unfiltered count of the same table in the same
      run. ``code:0`` proves acceptance and nothing else on this endpoint (this module's own
      swallow control is why), and a read-back that echoes still would not prove the server
      *applies* the filter — so the differential is the third leg.

    **The fixture route, and why it is this one.** ``POST …/fields`` is answering ``9499``
    externally (LD-329), so no column is authored here. None needs to be: a fresh disposable
    Base already carries a ``SingleSelect`` named ``Single option`` with ``options: []``, and
    writing records through the shipped write client with option NAMES makes Lark create the
    options — which is where the ``opt…`` ids this leg translates to come from. No ``/fields``
    write, no copy, and never ``LARKDOCIO_SCRATCH_BASE``.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    write = BaseWriteClient.from_write_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        # ---- the fixture: rows whose select values CREATE the options ------- #
        for value in ("Done", "Todo", "Done"):
            write.create_record(app_token, table_id,
                                {"Text": f"row-{value}", _SELECT_COLUMN: value})

        registry = FieldRegistry.from_read_client(read, app_token, table_id)
        assert registry.exhaustive is True
        assert _SELECT_COLUMN in registry.names, (
            f"a fresh disposable no longer carries a {_SELECT_COLUMN!r} column — this leg's "
            "fixture route is gone and it would otherwise prove nothing")
        select_id = registry.field_id_for(_SELECT_COLUMN)

        spec = FilterSpec(conditions=(Condition(FieldName(_SELECT_COLUMN), "is", ("Done",)),))
        resolved = registry.resolve(spec)
        option_id = resolved.conditions[0].values[0]
        assert option_id.startswith("opt"), (
            f"resolve() must translate the option NAME to an `opt…` id; got {option_id!r}")
        print(f"\nLD-318 translated 'Done' -> {option_id} on {select_id}")

        made = schema_apply(schema_dry_run([
            create_view(app_token, table_id, "ld318-select", "grid")]),
            client=schema, read_client=read)
        assert made.entries[0].outcome == "applied", made.entries[0].refusal
        view_id = made.entries[0].read_back["view_id"]

        # ---- THE CONTROL: the UNTRANSLATED name is refused BY LARK ---------- #
        untranslated = view_filter(FilterSpec(conditions=(
            Condition(FieldId(select_id), "is", ("Done",)),)))
        control = schema_apply(schema_dry_run([
            set_view_filter(app_token, table_id, view_id, untranslated)]),
            client=schema, read_client=read)
        control_entry = control.entries[0]
        detail = str(control_entry.refusal and control_entry.refusal.detail)
        assert control_entry.outcome != "applied", (
            "the option NAME was ACCEPTED by the view route — the defect LD-318 fixes has "
            f"changed shape and the translation's premise needs re-measuring: {detail}")
        print(f"\nLD-318 control (option NAME, untranslated) refused: {detail}")

        # ---- THE FIX: the translated filter is set and READ BACK ------------ #
        translated = view_filter(resolved)
        set_log = schema_apply(schema_dry_run([
            set_view_filter(app_token, table_id, view_id, translated)]),
            client=schema, read_client=read)
        entry = set_log.entries[0]
        assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
        assert entry.read_back["echoes"] is True
        persisted = entry.read_back["persisted"]
        assert persisted == translated.to_dict()
        assert option_id in json.dumps(persisted), (
            "the persisted filter_info must carry the OPTION ID that was sent")
        print(f"\nLD-318 sent      : {translated.to_dict()}")
        print(f"LD-318 persisted : {persisted}")

        # ---- THE ROWS: the view really filters, against its own control ----- #
        # A fresh disposable ships EMPTY starter rows of its own — 13 here, the 10 blank ones
        # plus the 3 written above — so the count is a DIFFERENTIAL against the same table in
        # the same run and never an absolute (BASE.md row 45's discipline).
        everything = read.search_records(app_token, table_id)
        through_view = read.search_records(app_token, table_id, view_id=view_id)
        assert len(through_view) == 2, (
            "the view's translated filter must select exactly the 2 'Done' rows; the whole "
            f"table is {len(everything)} rows, and getting all of them back is R12 reasserting "
            f"itself: {[r.fields for r in through_view]}")
        assert len(everything) > len(through_view), (
            "the differential is the proof: the unfiltered read must return MORE rows than the "
            f"view does ({len(everything)} vs {len(through_view)})")
        for record in through_view:
            cell = record.fields.get(_SELECT_COLUMN)
            assert cell == "Done" or (isinstance(cell, dict) and cell.get("text") == "Done"), (
                f"a row the view returned does not match the filter: {record.fields}")
        print(f"\nLD-318 rows through the view: {len(through_view)} of {len(everything)}")

        gone = schema_apply(schema_dry_run([delete_view(app_token, table_id, view_id)]),
                            client=schema, read_client=read)
        assert gone.entries[0].outcome == "applied", gone.entries[0].refusal


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup, the schema arm's shape."""
    left = base_write_harness.close_out()
    for entry in left:
        assert entry["app_token"] and entry["title"], entry
        assert base_write_harness.is_disposable_title(entry["title"]), entry
    remaining = base_write_harness.survivors()
    assert {e["app_token"] for e in remaining} == {e["app_token"] for e in left}
    if left:
        print("\nledger survivors (recorded, sweepable):",
              [e["app_token"] for e in left])
    else:
        assert base_write_harness.orphans() == [], (
            "the orphan oracle must answer zero when the ledger is clean")
