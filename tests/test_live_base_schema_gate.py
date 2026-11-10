"""THE BASE SCHEMA GATE — five arms, each one carrying a claim nothing else can make true.

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against a self-provisioned disposable, and nothing else.** Every Base this gate changes it
made itself through :func:`base_write_harness.disposable_base`; the harness records each in the
ledger the instant it exists and deletes it in a ``finally``. This module never reads
``LARKDOCIO_SCRATCH_BASE`` — that Base holds the only hand-authored ``Lookup`` / ``Email`` /
``Stage`` columns in existence, the API can recreate none of them, and it is a READ fixture —
and the offline companion checks that statically as well as at runtime here.

**The five arms, and why each exists.**

* **SURGICAL.** A column is added to a real table and the table is read back: **only** that
  column appeared, every other column is identical field by field, and every existing row's
  every existing cell is byte-identical. The column is then deleted and the table is its old
  shape again. Measured as a **set difference** over columns and over cells, never spot-checked
  — a claim that a schema write touches nothing else is only worth what it was measured with;
* **A REAL CROSS-TABLE LOSS.** A two-way link is built live between two tables, the **dry run**
  is taken first and must name the mirror **in the other table**, the delete is applied under
  consent minted from that same plan, and **both** columns are then gone. This is the arm that
  makes the safety claim true rather than asserted, and it is the reason the loss preview is
  scoped to the whole Base rather than to the table the caller named;
* **A READ-BACK-VERIFIED FILTER, WITH THE SWALLOW CONTROL BESIDE IT.** A filter is set through
  the shipped plan gate and re-read; the comparison is **semantic** and its normalisation is
  explicit, because the server adds a ``condition_id`` and a ``field_type`` of its own. Then a
  sibling key on the same endpoint — ``property.group_info`` — is written **on the same view**,
  answers ``code:0``, reads back with no such key, and is reported **not persisted**. The
  positive result is what makes the negative one mean anything: a verification never shown
  detecting a swallow is not known to detect one;
* **A COLUMN KIT THAT LANDS WITH ITS TABLE.** One table create carries a multi-kind ``fields``
  array — a bare ``Text``, a kind whose ``property`` is mandatory, and one more — and the proof
  is the created table's **own field list**, checked on name, ``type``, ``ui_type`` and
  ``property``, with ``is_primary`` read on every row. ``code:0`` is **not a finding** on this
  route (R12), which is the whole reason the arm reads rather than trusts. Beside it, in the same
  seconds and on the same table path, a **control** on the ``/fields`` write family this route
  exists to avoid — **recorded, never asserted**, because the arm depends neither on that family
  being broken nor on its being fixed. The batch verb rides the same arm with **per-table** kits;
* **A REFUSAL THAT MAKES NO CALL.** A ``Lookup`` / ``Stage`` / ``Email`` / Button-shaped column
  is attempted through the **shipped path** while the schema client's transport is one that
  raises on contact, so zero calls is **structural** rather than counted afterwards. The live
  positive control on the same table shows an allow-listed create really does reach the API and
  move ``table.revision`` — which is what makes the negative reading mean anything.

**THE CREDENTIAL RIDER, restated because this gate is where it would be over-read.** On this
tenant the READ pair and the WRITE pair **alias one single app with byte-identical secrets**
(probe-verified, and recorded in the project's own credential doctrine). So this gate proves the
**write path works**. It proves **nothing** about whether the read path lacks write scope, and
no same-tenant probe may be cited as evidence of scope separation — that claim needs a genuinely
separate app. The library still resolves the two pairs independently and must keep doing so.

**Nothing here uploads media.** An uploaded ``bitable_file`` / ``bitable_image`` token has no
purge verb at all, so a live arm that minted one would leave residue nothing can remove.

**Gentle.** Around forty calls at ≥1.2 s spacing. Rate limits are not probed.

**Skips loudly, never silently.**
"""
import json
import os
import time
import urllib.request
from pathlib import Path

import base_write_harness
import capture_sink
import pytest

from larkdocio.base import field_vocabulary as fv
from larkdocio.base import schema_ops_destructive as destructive
from larkdocio.base import schema_ops_fields as sof
from larkdocio.base.client import BaseReadClient
from larkdocio.base.field_vocabulary import UnauthorableFieldError
from larkdocio.base.schema_apply import consent_to_destroy, schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.schema_plan import batch_create_tables, create_table
from larkdocio.base.view_filters import (
    Condition,
    FieldId,
    FilterSpec,
    echoes,
    normalize_persisted,
    view_filter,
)
from larkdocio.base.view_plan import create_view, delete_view, set_view_filter
from lark_oapi.core.json import JSON

from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    api_base,
    fetch_tenant_access_token,
)

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# Imported unconditionally: this gate READS the disposables-folder variable through it, so it
# is a dependency rather than an optional convenience. Only the .env LOAD is best-effort.
import canary_support

try:  # pragma: no cover - a missing/unreadable .env must not fail collection
    canary_support.load_env()
except Exception:  # pragma: no cover
    pass


# --------------------------------------------------------------------------- #
# The raise-on-contact transport — the structural zero-call proof.              #
# --------------------------------------------------------------------------- #

class RaisesOnContact:
    """A transport that raises the moment anything touches it.

    The zero-call proof for a plan-time refusal is then **structural**: a refusal that failed to
    fire errors instead of calling, so the assertion cannot pass for the wrong reason. The
    record engine's own gate is the precedent.
    """

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(
                f"the schema client touched the transport ({name}) — a local authoring "
                "refusal must cost ZERO transport calls")

    def __getattr__(self, name):
        return RaisesOnContact._Boom()


def inert_schema_client():
    """A real :class:`BaseSchemaClient` whose SDK raises on contact."""
    return BaseSchemaClient("id", "secret", sdk_client=RaisesOnContact())


class _RawProbe(CredentialedRawHttpClient):
    """The library's own raw-HTTP core, used for the ONE shape the typed client refuses.

    ``property.group_info`` has no parameter anywhere in the shipped surface — that is the
    feature, not a gap — so the swallow control cannot ride the client without cutting a hole
    in it. It rides the library's own raw core instead, and this class lives in ``tests/`` so
    the probe can never be mistaken for a shipped capability. LD-264 established the shape.
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


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def _clients():
    return BaseSchemaClient.from_write_credentials(), BaseReadClient.from_read_credentials()


def columns_of(read, app_token, table_id):
    """``{field_id: (name, type, ui_type)}`` — the identity of every column, for set work."""
    return {field.field_id: (field.field_name, field.type, getattr(field, "ui_type", None))
            for field in read.list_fields(app_token, table_id)}


def cells_of(read, app_token, table_id):
    """``{(record_id, field_name): value}`` over every row — the per-cell oracle.

    ``search_records`` hands back the SDK's own record objects, so the values are stringified
    here: the comparison this arm needs is *did anything move*, and a repr is a stable answer to
    that for every cell shape a Base can hold.
    """
    cells = {}
    for record in read.search_records(app_token, table_id) or []:
        record_id = getattr(record, "record_id", None)
        for name, value in (getattr(record, "fields", None) or {}).items():
            cells[(record_id, name)] = repr(value)
    return cells


def normalised_filter(persisted):
    """The server's own additions dropped BY NAME, so the comparison is semantic and says so.

    ``condition_id`` and ``field_type`` are stamped by Lark on every condition it stores; they
    were not sent and cannot be predicted, so a byte comparison would fail for a reason that has
    nothing to do with whether the filter persisted.
    """
    conditions = []
    for condition in (persisted or {}).get("conditions") or []:
        conditions.append({key: value for key, value in condition.items()
                           if key not in {"condition_id", "field_type"}})
    return {"conjunction": (persisted or {}).get("conjunction"), "conditions": conditions}


# --------------------------------------------------------------------------- #
# The fence, asserted at runtime as well as statically.                         #
# --------------------------------------------------------------------------- #

def test_the_gate_NEVER_TOUCHES_THE_CONFIGURED_SCRATCH_BASE(credentials):
    """Restated on this ring because its verbs could destroy the hand-authored specimens the
    API cannot recreate. Whatever the variable holds, the Base this gate changes is one it
    made."""
    configured = (os.environ.get("LARKDOCIO_SCRATCH_BASE") or "").strip()
    with base_write_harness.disposable_base() as (app_token, _table_id, title):
        assert base_write_harness.is_disposable_title(title)
        assert app_token, "the harness always yields a token"
        if configured:
            assert app_token not in configured and configured not in app_token, (
                "the schema gate must never change the configured READ fixture")


# --------------------------------------------------------------------------- #
# ARM 1 — a schema write is SURGICAL.                                           #
# --------------------------------------------------------------------------- #

def test_arm1_a_FIELD_WRITE_IS_SURGICAL_and_the_table_returns_to_its_prior_shape(credentials):
    """Add one column, read the table back, and measure what moved as a set difference over
    columns AND over every cell of every row. Then remove it and compare against the baseline
    the arm captured before it touched anything."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        columns_before = columns_of(read, app_token, table_id)
        cells_before = cells_of(read, app_token, table_id)
        revision_before = sof.table_revision(read, app_token, table_id)

        log = schema_apply(schema_dry_run([
            sof.create_field(app_token, table_id, "ld266-surgical", 1, ui_type="Text",
                             revision=revision_before)]),
            client=schema, read_client=read)
        assert log.entries[0].outcome == "applied", log.entries[0].refusal

        columns_after = columns_of(read, app_token, table_id)
        added = set(columns_after) - set(columns_before)
        assert len(added) == 1, ("EXACTLY ONE column appeared", added)
        new_id = added.pop()
        assert columns_after[new_id][0] == "ld266-surgical"
        assert set(columns_before) - set(columns_after) == set(), "nothing was lost"
        unchanged = {fid: columns_after[fid] for fid in columns_before}
        assert unchanged == columns_before, (
            "EVERY OTHER COLUMN IS IDENTITY-IDENTICAL — name, type and kind alike")
        assert cells_of(read, app_token, table_id) == cells_before, (
            "AND EVERY EXISTING CELL OF EVERY EXISTING ROW IS BYTE-IDENTICAL — the new column "
            "added no value anywhere")
        print(f"\nsurgical: +1 column ({new_id}), {len(columns_before)} columns and "
              f"{len(cells_before)} cells untouched")

        # ---- and back to the prior shape ---------------------------------- #
        plan = schema_dry_run([destructive.delete_field(app_token, table_id, new_id)],
                              read_client=read)
        removal = schema_apply(plan, client=schema, read_client=read,
                               consent=consent_to_destroy(plan))
        assert removal.entries[0].outcome == "applied", removal.entries[0].refusal
        assert columns_of(read, app_token, table_id) == columns_before, (
            "the table is its baseline shape again, column for column")
        assert cells_of(read, app_token, table_id) == cells_before


# --------------------------------------------------------------------------- #
# ARM 2 — a REAL cross-table loss, predicted first.                             #
# --------------------------------------------------------------------------- #

def test_arm2_a_REAL_CROSS_TABLE_LOSS_happens_and_the_PREVIEW_PREDICTED_IT(credentials):
    """The arm that makes the safety claim true rather than asserted. The mirror really is lost
    from a table the caller never named, and the preview said so **before** the delete."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, main_id, _title):
        made = schema_apply(schema_dry_run([
            batch_create_tables(app_token, ["ld266-target"],
                                accept_locale_default_primary=True)]),
            client=schema, read_client=read)
        assert made.entries[0].outcome == "applied", made.entries[0].refusal
        target_id = made.entries[0].created_table_ids[0]

        source = schema.create_field(app_token, main_id, "ld266-duplex", 21,
                                     ui_type="DuplexLink",
                                     properties={"table_id": target_id, "multiple": True})
        mirrors_before = set(columns_of(read, app_token, target_id))
        assert mirrors_before, "the mirror column must exist before the delete is planned"

        # ---- THE PREVIEW COMES FIRST, and names the OTHER table ------------ #
        plan = schema_dry_run(
            [destructive.delete_field(app_token, main_id, source.field_id)], read_client=read)
        loss = plan.entries[0].loss_preview
        assert loss is not None, plan.entries[0].refusal
        previewed_tables = [column["table_id"] for column in loss["columns"]]
        assert previewed_tables == [main_id, target_id], (
            "the preview must name BOTH tables — the mirror lives in the one nobody named")
        predicted_mirror = loss["mirror"]["field_id"]
        assert predicted_mirror in mirrors_before
        print(f"\ncross-table preview predicted {loss['mirror']['field_name']!r} in "
              f"{target_id}; applying now")

        # ---- and then the loss really happens ------------------------------ #
        applied = schema_apply(plan, client=schema, read_client=read,
                               consent=consent_to_destroy(plan))
        assert applied.entries[0].outcome == "applied", applied.entries[0].refusal
        assert source.field_id not in columns_of(read, app_token, main_id)
        assert predicted_mirror not in columns_of(read, app_token, target_id), (
            "BOTH COLUMNS ARE GONE — the predicted mirror really left the other table")


# --------------------------------------------------------------------------- #
# ARM 3 — a read-back-verified filter, with the swallow control.                #
# --------------------------------------------------------------------------- #

def test_arm3_a_FILTER_IS_VERIFIED_BY_READ_BACK_and_the_SWALLOW_CONTROL_bites(credentials):
    """The positive result and the negative control, on the SAME view, so the control is a
    control and not a difference between two Bases."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        field_id = read.list_fields(app_token, table_id)[0].field_id
        made = schema_apply(schema_dry_run([
            create_view(app_token, table_id, "ld266-gate", "grid")]),
            client=schema, read_client=read)
        assert made.entries[0].outcome == "applied", made.entries[0].refusal
        view_id = made.entries[0].read_back["view_id"]

        wanted = view_filter(FilterSpec(
            conditions=(Condition(FieldId(field_id), "isNotEmpty"),)))
        set_log = schema_apply(schema_dry_run([
            set_view_filter(app_token, table_id, view_id, wanted)]),
            client=schema, read_client=read)
        entry = set_log.entries[0]
        assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
        assert entry.read_back["echoes"] is True
        # SEMANTIC, and its normalisation is explicit: the server stamps a condition id and a
        # field type of its own that were never sent and cannot be predicted.
        assert normalised_filter(entry.read_back["persisted"]) == normalised_filter(
            wanted.to_dict()), entry.read_back["persisted"]
        print(f"\nfilter persisted and read back on view {view_id}")

        # ---- THE SWALLOW CONTROL, on the SAME view ------------------------- #
        probe = _raw()
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"
        answered = probe.call("PATCH", path, body={
            "property": {"group_info": [{"field_id": field_id, "desc": False}]}})
        assert str(answered.get("code")) == "0", ("the control must be ACCEPTED", answered)

        # Read back RAW, deliberately: the pinned SDK's typed view model does not carry
        # group_info at all, so asking it could not tell a swallow from a model gap.
        raw = probe.call("GET", path)
        prop = ((raw.get("data") or {}).get("view") or {}).get("property")
        assert not (prop or {}).get("group_info"), (
            "THE SWALLOW: code:0 and nothing persisted — which is exactly why this library "
            f"verifies a view write by read-back. property={prop!r}")

        # AND THE SWALLOW CHANGED NOTHING AT ALL: the filter this arm really did persist is
        # still exactly what was sent, so the accepted call landed neither its own key nor a
        # side effect. That is the sharpest reading of the control — `code:0` bought nothing.
        assert normalize_persisted((prop or {}).get("filter_info")) == normalize_persisted(
            wanted.to_dict()), prop

        # And the TYPED not-persisted verdict comes from the SHIPPED classifier rather than
        # from this test's own opinion: fed a read-back that does not echo, it says so.
        assert echoes(wanted, None) is False
        assert echoes(wanted, {"conjunction": "and", "conditions": []}) is False
        print(f"\nswallow control: group_info code:0, view property reads back {prop!r}")

        gone = schema_apply(schema_dry_run([delete_view(app_token, table_id, view_id)]),
                            client=schema, read_client=read)
        assert gone.entries[0].outcome == "applied", gone.entries[0].refusal


# --------------------------------------------------------------------------- #
# ARM 4 — an allow-list refusal that makes ZERO calls, with a live control.     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("ui_type,field_type", [
    ("Lookup", 19), ("Stage", 24), ("Email", 1), ("Button", 1),
])
def test_arm4_an_UNAUTHORABLE_COLUMN_is_refused_with_ZERO_TRANSPORT_CALLS(
        ui_type, field_type, credentials):
    """The refusal proven against the SHIPPED path, with the transport armed to raise: if the
    local refusal failed to fire, this errors instead of quietly authoring a column."""
    client = inert_schema_client()
    assert ui_type not in fv.AUTHORABLE_UI_TYPES, ui_type
    with pytest.raises(UnauthorableFieldError) as caught:
        schema_apply(schema_dry_run([
            sof.create_field("appTOKEN", "tblTABLE", f"ld266-{ui_type}", field_type,
                             ui_type=ui_type)]),
            client=client, read_client=None)
    message = str(caught.value)
    assert ui_type in message
    assert "THE SERVER" in message or "server" in message.lower(), message
    for accepted in fv.AUTHORABLE_UI_TYPES[:3]:
        assert accepted in message, ("the refusal lists the accepted set", accepted)


def test_arm4_the_LIVE_POSITIVE_CONTROL_reaches_the_api_and_MOVES_table_revision(credentials):
    """Without it the zero-call reading means nothing: the same shipped path, one allow-listed
    kind, really does call and really does move the anchor."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        before = sof.table_revision(read, app_token, table_id)
        log = schema_apply(schema_dry_run([
            sof.create_field(app_token, table_id, "ld266-control", 1, ui_type="Text",
                             revision=before)]),
            client=schema, read_client=read)
        assert log.entries[0].outcome == "applied", log.entries[0].refusal
        after = sof.table_revision(read, app_token, table_id)
        assert before is None or after is None or after > before, (before, after)
        print(f"\nlive positive control: table.revision {before} → {after}")


# --------------------------------------------------------------------------- #
# ARM 5 — a table lands WITH ITS WHOLE COLUMN KIT, proved by its OWN field list. #
# --------------------------------------------------------------------------- #

#: A three-kind kit: a bare ``Text``, a kind whose ``property`` is MANDATORY (``Currency`` — one
#: of ``field_authoring.REQUIRED_PROPERTY_KINDS``) and one more. ``Rating`` is the obvious
#: mandatory-property kind and is deliberately **not** here: this route refuses it outright
#: (`1254012`, measured in probe `ld336-02`), which the shipped gate refuses locally and the
#: refusal arm below covers.
ARM5_KIT = (
    {"field_name": "ld336-title", "field_type": 1, "ui_type": "Text"},
    {"field_name": "ld336-budget", "field_type": 2, "ui_type": "Currency",
     "properties": {"formatter": "0.00", "currency_code": "USD"}},
    {"field_name": "ld336-due", "field_type": 5, "ui_type": "DateTime",
     "properties": {"date_formatter": "yyyy/MM/dd"}},
)

_CAPTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"

#: The capture's own ``_note``, formatted from what was MEASURED — the two open questions
#: answered in writing, whichever way they fell.
_ARM5_NOTE = (
    "arm 5 (fields-at-creation). (i) OUTAGE-IMMUNITY PREMISE: a create carrying an inline "
    "`fields` array was sent while the /fields WRITE family was probed in the same seconds on "
    "the same table path. The kitted create reported `{outcome}` — verified by the created "
    "table's own field list, never by code:0 — and the same-window POST .../fields control "
    "answered `{control}` ({control_msg!r}). Read the two together: a kitted create that "
    "applied beside a 9499 control is the premise HOLDING; a kitted create that dropped or "
    "failed beside a code:0 control refutes it, and the capability still ships either way "
    "because it is the right shape for the surface independent of any outage. (ii) PRIMARY "
    "COLUMN: after the kitted create the columns flagged is_primary were {primary}; the kit's "
    "first entry BECAME the primary: {became}. True is what probe ld336-02 measured across nine "
    "cases — a kitted create does NOT also get the locale-named default column, so entry 0 of "
    "the array is the column the rows are keyed by and the array's ORDER is a decision."
)

#: The one-line verdict, also formatted from what was measured rather than from what was hoped.
_ARM5_VERDICT = (
    "create_table carrying an inline `fields` array: {outcome} (verified against the created "
    "table's OWN field list, never code:0), measured beside a same-window POST .../fields "
    "control answering {control}."
)


def _write_capture(name, blob):
    """One probe capture, on this directory's own convention, in the dev repo."""
    path = capture_sink.write_capture(
        _CAPTURE_DIR / name,
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n")
    print(f"\ncapture written: {path} (aimed at dev/base-study/captures/{name})")
    return path


def _refusal_of_a_batch_kit(app_token):
    """The shipped batch verb, asked for a column kit: its refusal message, or ``None``.

    Driven with a client whose transport RAISES on contact, so "it refused before calling" is
    **structural** here exactly as it is in the refusal arm.
    """
    from larkdocio.base.field_authoring import FieldAuthoringRefusal

    try:
        schema_apply(schema_dry_run([batch_create_tables(
            app_token, ["never-sent"],
            fields=[[{"field_name": "x", "field_type": 1, "ui_type": "Text"}]])]),
            client=inert_schema_client(), read_client=None)
    except FieldAuthoringRefusal as refusal:
        return str(refusal)
    return None


def _property_blob(field):
    """A column's ``property`` as plain data, or ``None`` — the SDK object is not JSON."""
    prop = getattr(field, "property", None)
    if prop is None:
        return None
    try:
        return json.loads(JSON.marshal(prop))
    except Exception:                       # pragma: no cover — a shape we cannot serialise
        return repr(prop)


def test_arm5_a_TABLE_lands_WITH_ITS_COLUMN_KIT_and_the_FIELD_LIST_is_the_proof(credentials):
    """One call, one table, three columns — and the evidence is the table's OWN field list.

    ``code:0`` is **not a finding** here (R12): this endpoint silently ignores what it does not
    recognise, so an accepted create carrying a ``fields`` array proves only that the body was
    accepted. So the arm reads the created table's columns back and checks **name, type,
    ui_type and property** for each, plus ``is_primary`` on every row — which also answers, from
    the tenant rather than from prose, whether the kit's first entry BECOMES the primary column
    or arrives BESIDE the locale-named one Lark creates itself.

    Beside it, in the SAME probe and the same seconds, a **control** on the route this whole
    capability exists to avoid: a plain ``POST …/tables/{t}/fields``. Its code is recorded next
    to the treatment's, because "immune to the outage" is only readable as an answer if the
    outage is shown to be present or absent while the treatment ran. The control is **recorded,
    never asserted**: this arm depends neither on that family being broken nor on its being
    fixed.

    **THE CAPTURE IS WRITTEN WHETHER OR NOT THE ARM PASSES**, in a ``finally``. What the
    platform answers to a create carrying an inline array is a *finding*; an arm that recorded
    it only on success would turn the one interesting failure into silence.
    """
    schema, read = _clients()
    control = _raw()
    observed = {}
    # THE DESTINATION IS RESOLVED **BEFORE** THE `try`, and that placement is load-bearing:
    # a skip raised INSIDE it would run the capture-writing `finally` and overwrite a committed
    # capture with a run that measured nothing. The disposables folder is a precondition of the
    # arm, not a step in it.
    dest_folder = canary_support.require_disposables_folder()
    try:
        with base_write_harness.disposable_base(folder_token=dest_folder) as (
                app_token, factory, title):
            assert base_write_harness.is_disposable_title(title)
            observed["disposable"] = {"app_token": app_token, "title": title}

            # --- the TREATMENT: one create carrying the whole kit ---------------
            plan = schema_dry_run([create_table(app_token, "ld336-kit", fields=ARM5_KIT)])
            entry = plan.entries[0]
            assert entry.refusal is None, entry.refusal
            assert plan.api_call_count == 1, "a table and its columns are ONE write"
            assert entry.read_cost == 2, "one table listing plus one field listing, disclosed"
            assert "ld336-budget" in entry.request.describe, (
                "the dry run must disclose the column kit BEFORE the call is made")
            observed["dry_run"] = {"describe": entry.request.describe,
                                   "api_call_count": plan.api_call_count,
                                   "read_calls": plan.read_calls}

            log = schema_apply(plan, client=schema, read_client=read)
            landed = log.entries[0]
            table_id = landed.created_table_ids[0] if landed.created_table_ids else None
            observed["create_table_with_fields"] = {
                "outcome": landed.outcome,
                "table_id": table_id,
                "read_back": landed.read_back,
                "refusal": landed.refusal.to_dict() if landed.refusal else None,
            }

            # --- the SAME-WINDOW CONTROL on the /fields write family ------------
            control_path = (f"/open-apis/bitable/v1/apps/{app_token}/tables/"
                            f"{table_id or factory}/fields")
            control_reply = control.call("POST", control_path,
                                        {"field_name": "ld336-control", "type": 1})
            observed["fields_write_control"] = {
                "endpoint": control_path,
                "code": control_reply.get("code"),
                "msg": control_reply.get("msg"),
            }

            # --- the PROOF: the created table's own columns ---------------------
            served = list(read.list_fields(app_token, table_id) or ()) if table_id else []
            columns = {field.field_name: field for field in served}
            observed["field_list"] = [
                {"field_name": field.field_name, "type": field.type,
                 "ui_type": getattr(field, "ui_type", None),
                 "is_primary": bool(getattr(field, "is_primary", False)),
                 "property": _property_blob(field)}
                for field in served]
            primary = [field.field_name for field in served
                       if getattr(field, "is_primary", False)]
            observed["primary_after_kit"] = primary
            observed["kit_first_entry_became_primary"] = (
                primary == [ARM5_KIT[0]["field_name"]])

            # --- the BATCH verb: the REFUTATION, measured live ------------------
            # The shipped path REFUSES a kit here, so the swallow is measured through the raw
            # core — the only way to show the refusal is earned rather than merely cautious. If
            # Lark ever starts honouring the array, this is what reddens, and the refusal it
            # justifies is what must then be revisited.
            batch_reply = control.call(
                "POST", f"/open-apis/bitable/v1/apps/{app_token}/tables/batch_create",
                {"tables": [{"name": "ld336-batch-A",
                             "fields": [{"field_name": ARM5_KIT[0]["field_name"],
                                         "type": ARM5_KIT[0]["field_type"],
                                         "ui_type": ARM5_KIT[0]["ui_type"]}]},
                            {"name": "ld336-batch-B"}]})
            batch_ids = (batch_reply.get("data") or {}).get("table_ids") or []
            observed["batch_create_ignores_the_kit"] = {
                "code": batch_reply.get("code"),
                "msg": batch_reply.get("msg"),
                "table_ids": list(batch_ids),
                "columns_per_table": {
                    table_id: [{"field_name": f.field_name,
                                "is_primary": bool(getattr(f, "is_primary", False))}
                               for f in read.list_fields(app_token, table_id) or ()]
                    for table_id in batch_ids},
            }
            observed["shipped_batch_verb_refuses_a_kit"] = _refusal_of_a_batch_kit(app_token)

            # --- and NOW the assertions, with everything already recorded -------
            assert landed.outcome == "applied", (
                f"the kitted create reported {landed.outcome}: "
                f"{landed.refusal.detail if landed.refusal else ''}")
            for asked in ARM5_KIT:
                field = columns.get(asked["field_name"])
                assert field is not None, (
                    f"{asked['field_name']!r} is absent from the created table's own field "
                    f"list — the create reported {landed.outcome} and the column is not there")
                assert field.type == asked["field_type"], (asked["field_name"], field.type)
                assert getattr(field, "ui_type", None) == asked["ui_type"], asked["field_name"]
                if asked.get("properties"):
                    assert _property_blob(field), (
                        f"{asked['field_name']!r} landed with no property at all, though its "
                        f"kind's property is what a create for it must carry")
            assert all(hasattr(field, "is_primary") for field in served), (
                "is_primary must be readable on every row, or the primary question is "
                "unanswerable")
            assert observed["primary_after_kit"] == [ARM5_KIT[0]["field_name"]], (
                "the MEASURED answer (probe ld336-02, nine cases): the kit's FIRST entry "
                "becomes the primary column. If this ever flips, the shipped sentence in "
                "schema_ops_app_table.KIT_FIRST_ENTRY_IS_THE_PRIMARY is wrong and the guide "
                "with it — which is why it is asserted here and not merely recorded")

            swallowed = observed["batch_create_ignores_the_kit"]
            assert swallowed["code"] == 0, (
                "the batch ACCEPTED the body — that acceptance is the whole refutation; an "
                "outright refusal here would be a different, and better, world")
            for table_id, cols in swallowed["columns_per_table"].items():
                assert not any(c["field_name"] == ARM5_KIT[0]["field_name"] for c in cols), (
                    f"{table_id} carries the kit column — Lark has started HONOURING a "
                    f"batch_create `fields` array, so BATCH_CREATE_IGNORES_A_COLUMN_KIT is now "
                    f"false and the shipped refusal must be revisited: {cols}")
            assert observed["shipped_batch_verb_refuses_a_kit"], (
                "and the shipped batch verb must REFUSE a kit rather than send a no-op")
    finally:
        treatment = observed.get("create_table_with_fields") or {}
        gate = observed.get("fields_write_control") or {}
        _write_capture("ld336-01-fields-at-creation.json", {
            "_probe": "ld336-01",
            "_endpoint": ("/open-apis/bitable/v1/apps/{app_token}/tables (and "
                          ".../tables/batch_create), with the /fields WRITE family as the "
                          "SAME-WINDOW control"),
            "_method": "POST table create carrying an inline `fields` array",
            "_http_status": 200,
            "_lark_code": (f"create_table+fields: {treatment.get('outcome')} (read-back "
                           f"verified, never code:0) · POST .../fields control: "
                           f"{gate.get('code')}"),
            "_lark_msg": gate.get("msg"),
            "_batch_verdict": (
                "batch_create carrying a per-table `fields` array: code "
                f"{(observed.get('batch_create_ignores_the_kit') or {}).get('code')} and the "
                "created tables carry NONE of the kit — which is why the shipped batch verb "
                "refuses the argument instead of forwarding a silent no-op."),
            "_verdict": _ARM5_VERDICT.format(
                outcome=treatment.get("outcome"), control=gate.get("code")),
            "_note": _ARM5_NOTE.format(
                outcome=treatment.get("outcome"),
                control=gate.get("code"),
                control_msg=gate.get("msg"),
                primary=observed.get("primary_after_kit"),
                became=observed.get("kit_first_entry_became_primary"),
            ),
            "_transport": ("larkdocio.base.schema_client.BaseSchemaClient through the shipped "
                           "plan gate; the control on larkdocio.common.transport."
                           "CredentialedRawHttpClient, paced 1.2 s"),
            "_disposable": ("one, harness-created; deleted in the harness finally, "
                            "ledger-backed"),
            "response": observed,
        })


# --------------------------------------------------------------------------- #
# ARM 6 — what a NEW Base is SEEDED with, and WHERE a later column LANDS.        #
# --------------------------------------------------------------------------- #

#: The kit arm 6 creates its own table with, so the ORDER question has a control: three named
#: columns whose positions were chosen by the array, against which the appended ones are read.
ARM6_KIT = (
    {"field_name": "ld473-title", "field_type": 1, "ui_type": "Text"},
    {"field_name": "ld473-score", "field_type": 2, "ui_type": "Number",
     "properties": {"formatter": "0"}},
    {"field_name": "ld473-when", "field_type": 5, "ui_type": "DateTime",
     "properties": {"date_formatter": "yyyy/MM/dd"}},
)

#: Appended AFTER the create, in this order, each one its own ``create_field`` call. The names
#: are deliberately anti-alphabetical (``zeta`` before ``alpha``) so "append order is display
#: order" cannot be confused with the server sorting by name — the two hypotheses predict
#: different lists, and only one of them can match.
ARM6_APPENDED = (
    ("ld473-open", 7, "Checkbox", None),
    ("ld473-zeta", 1, "Text", None),
    ("ld473-alpha", 1, "Text", None),
)


def test_arm6_A_NEW_BASE_IS_SEEDED_and_a_LATER_COLUMN_IS_APPENDED(credentials):
    """Three shipped-guide sentences, measured on one disposable rather than repeated.

    * **WHAT A CREATE PRODUCES.** ``create_app`` answers a ``default_table_id``, and the guide
      teaches ``list_tables(app_token)[0]`` in eleven places as *"the table I just made"*. So
      the seeded table is read whole — its name, its columns and its rows — and the two ids are
      compared. Every number written into the guide comes from this reading; nothing about the
      seeding is asserted against a remembered shape, because a seeding Lark changes is a
      finding rather than a failure. The one thing asserted is the **collision**: the seeded
      table IS ``list_tables()[0]``, which is what makes the guide's sentence wrong;

    * **WHERE A LATER COLUMN LANDS.** A table is created with a three-entry kit, then three more
      columns are appended one ``create_field`` at a time. The kit's order is the control; the
      appended list is the treatment. This answers both halves of the shipped claim at once —
      that ``create_field`` **appends** (so the position asked for is forfeited) and that
      **append order is display order** (so the forfeit has a workaround). One of the appended
      kinds is ``Checkbox``, the kind the create route refuses, so the workaround is measured on
      the very column that forces it;

    * **WHAT A TEXT CELL COMES BACK AS.** One record is written through the shipped write
      client, then read back through ``search_records`` — the call a consumer makes — and the
      cell's wire value recorded. The guide shows this shape; it is confirmed here rather than
      copied.

    Cleanup is the shipped ``delete_base`` inside the ``with``, confirmed on the **bitable**
    side (Drive metadata keeps answering for a trashed Base), with the harness's own ledgered
    ``finally`` behind it.
    """
    from larkdocio.base.schema_client import base_is_gone
    from larkdocio.base.write_client import BaseWriteClient
    from larkdocio.errors import LarkAPIError

    schema, read = _clients()
    write = BaseWriteClient.from_write_credentials()
    observed = {}
    # THE DESTINATION IS RESOLVED **BEFORE** THE `try`, and that placement is load-bearing:
    # a skip raised INSIDE it would run the capture-writing `finally` and overwrite a committed
    # capture with a run that measured nothing. The disposables folder is a precondition of the
    # arm, not a step in it.
    dest_folder = canary_support.require_disposables_folder()
    try:
        with base_write_harness.disposable_base(folder_token=dest_folder) as (
                app_token, factory, title):
            assert base_write_harness.is_disposable_title(title)
            observed["disposable"] = {"app_token": app_token, "title": title,
                                      "default_table_id": factory}

            # --- (i) WHAT THE CREATE PRODUCED, read rather than remembered -------
            seeded = list(read.list_tables(app_token) or ())
            seeded_id = seeded[0].table_id if seeded else None
            seed_fields = list(read.list_fields(app_token, seeded_id) or ()) if seeded_id else []
            seed_rows = list(read.search_records(app_token, seeded_id) or ()) if seeded_id else []
            observed["seeding"] = {
                "tables": [{"table_id": t.table_id, "name": t.name,
                            "revision": getattr(t, "revision", None)} for t in seeded],
                "default_table_id_from_create": factory,
                "list_tables_0_is_the_default_table": bool(seeded_id) and seeded_id == factory,
                "columns": [{"field_name": f.field_name, "type": f.type,
                             "ui_type": getattr(f, "ui_type", None),
                             "is_primary": bool(getattr(f, "is_primary", False))}
                            for f in seed_fields],
                "row_count": len(seed_rows),
                "rows_all_empty": all(not (getattr(r, "fields", None) or {})
                                      for r in seed_rows),
            }

            # --- (ii) WHERE A LATER COLUMN LANDS ---------------------------------
            plan = schema_dry_run([create_table(app_token, "ld473-order", fields=ARM6_KIT)])
            log = schema_apply(plan, client=schema, read_client=read)
            landed = log.entries[0]
            table_id = landed.created_table_ids[0] if landed.created_table_ids else None
            assert landed.outcome == "applied", landed.refusal
            after_kit = [f.field_name for f in read.list_fields(app_token, table_id) or ()]

            for field_name, field_type, ui_type, properties in ARM6_APPENDED:
                step = schema_dry_run([sof.create_field(app_token, table_id, field_name,
                                                        field_type, ui_type=ui_type,
                                                        properties=properties)])
                step_log = schema_apply(step, client=schema, read_client=read)
                assert step_log.entries[0].outcome == "applied", step_log.entries[0].refusal
            after_appends = [f.field_name for f in read.list_fields(app_token, table_id) or ()]
            observed["column_order"] = {
                "kit_asked": [entry["field_name"] for entry in ARM6_KIT],
                "after_kit": after_kit,
                "appended_in_call_order": [name for name, _t, _u, _p in ARM6_APPENDED],
                "after_appends": after_appends,
            }

            # --- (iii) WHAT A TEXT CELL COMES BACK AS ----------------------------
            write.create_record(app_token, table_id, {"ld473-title": "row"})
            read_back = list(read.search_records(app_token, table_id) or ())
            cells = [dict(getattr(record, "fields", None) or {}) for record in read_back]
            observed["text_cell_wire_shape"] = {
                "written": "row",
                "search_records_fields": cells,
                "text_cell": next((cell.get("ld473-title") for cell in cells
                                   if cell.get("ld473-title")), None),
            }

            # --- and NOW the assertions, with everything already recorded --------
            assert observed["seeding"]["list_tables_0_is_the_default_table"], (
                "the guide teaches `list_tables(app_token)[0]` as 'the table I just made'. If "
                "the seeded table is NOT index 0 the guide's sentence is merely unlucky rather "
                "than wrong, and the disclosure it earns is a different one: "
                f"{observed['seeding']}")
            assert after_kit[:len(ARM6_KIT)] == [e["field_name"] for e in ARM6_KIT], (
                f"the kit's ARRAY ORDER is the table's column order: {after_kit}")
            appended = [name for name, _t, _u, _p in ARM6_APPENDED]
            assert after_appends[-len(appended):] == appended, (
                "`create_field` APPENDS, in call order — which is BOTH halves of the shipped "
                "claim: a column asked for at position N does not land there (the position is "
                "forfeited), and the order the calls are made in IS the order they display in "
                f"(so the forfeit has a workaround): {after_appends}")
            assert after_appends[:len(after_kit)] == after_kit, (
                "and an append moves nothing that was already there")
            text_cell = observed["text_cell_wire_shape"]["text_cell"]
            assert isinstance(text_cell, list) and text_cell, (
                f"a Text cell must come back from search_records as a SEGMENT ARRAY: {text_cell}")
            assert text_cell[0].get("text") == "row" and text_cell[0].get("type") == "text", (
                "the shipped guide prints [{'text': …, 'type': 'text'}] for a Text cell read "
                f"through search_records; what came back was {text_cell!r}")

            # --- CLEANUP through the SHIPPED verb, confirmed on the bitable side --
            schema.delete_base(app_token)
            confirmed_gone = False
            try:
                read.get_app(app_token)
            except LarkAPIError as exc:
                confirmed_gone = base_is_gone(exc)
            observed["delete_base"] = {"confirmed_gone": confirmed_gone}
            assert confirmed_gone, (
                "the shipped delete_base must leave the bitable side answering a gone-shaped "
                "code — a code:0 on the delete is acceptance, never proof")
    finally:
        seeding = observed.get("seeding") or {}
        order = observed.get("column_order") or {}
        _write_capture("ld473-01-seeding-and-append-order.json", {
            "_probe": "ld473-01",
            "_endpoint": ("POST /open-apis/bitable/v1/apps (the create), GET .../tables, "
                          "GET .../tables/{t}/fields, POST .../tables/{t}/fields, "
                          "POST .../records, POST .../records/search, "
                          "DELETE /open-apis/drive/v1/files/{token}"),
            "_method": "create a Base, read what it came with, append columns, read the order",
            "_http_status": 200,
            "_lark_code": 0,
            "_verdict": (
                f"a created Base arrives holding {len(seeding.get('tables') or ())} table(s) "
                f"with {len(seeding.get('columns') or ())} column(s) and "
                f"{seeding.get('row_count')} row(s); list_tables()[0] IS that seeded table: "
                f"{seeding.get('list_tables_0_is_the_default_table')}. create_field APPENDS in "
                f"call order: asked {order.get('appended_in_call_order')}, read back "
                f"{order.get('after_appends')}."),
            "_note": (
                "Measured for the shipped guide's Base truth batch. (i) SEEDING: the create's "
                "own reply carries a default_table_id and that table is what list_tables() "
                "returns at index 0, so every recipe teaching `list_tables(app_token)[0]` as "
                "'the table I just made' names Lark's table, not the caller's. Its columns and "
                "row count are recorded above exactly as read — a seeding Lark changes is a "
                "finding, not a failure. (ii) ORDER: a table created with a three-entry kit "
                "reads back in the array's order; three columns appended afterwards, one "
                "create_field call each and deliberately anti-alphabetical, read back at the "
                "END in CALL order. Both halves of the shipped claim: the position asked for is "
                "forfeited, and append order is display order. One appended kind is Checkbox — "
                "the kind the table-create route refuses (1254012, probe ld336-02) — so the "
                "workaround is measured on the column that forces it. (iii) A Text cell written "
                "as a bare string reads back through search_records as a segment array."),
            "_transport": ("larkdocio.base.schema_client.BaseSchemaClient / BaseWriteClient / "
                           "BaseReadClient through the shipped plan gate; no raw core"),
            "_disposable": ("one, harness-created; deleted by the SHIPPED delete_base inside "
                            "the with-block and confirmed on the bitable side, with the "
                            "harness's ledgered finally behind it"),
            "response": observed,
        })


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup, every Base arm's shape."""
    left = base_write_harness.close_out()
    for entry in left:
        assert entry["app_token"] and entry["title"], entry
        assert base_write_harness.is_disposable_title(entry["title"]), entry
    remaining = base_write_harness.survivors()
    assert {e["app_token"] for e in remaining} == {e["app_token"] for e in left}
    if left:
        print("\nledger survivors (recorded, sweepable):", [e["app_token"] for e in left])
    else:
        assert base_write_harness.orphans() == [], (
            "the orphan oracle must answer zero when the ledger is clean")
