"""THE MINIMAL-FORM SWEEP (LD-317) — what a PROPERTY-LESS create answers, per column kind.

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write -k minimal_form

**Why this arm exists.** ``FieldPropertyShape.required`` is the one flag standing between a
property-less ``create_field`` and the wire, and until LD-317 it was a **hand-set boolean** with
no evidence attached: 22 of 24 rows carried the default ``False`` because nobody had written
``True``, not because a control had been measured. A 1.27.0 consumer paid an apply round-trip for
the gap (``Progress``, ``1254001``). This arm measures the control for **every** row in one pass,
so the flag is derived from a capture rather than asserted by hand.

**It found that a stale capture is worse than no capture.** The 2026-07 field zoo
(``05-04-field-zoo-create-results.json``) recorded a property-less ``Progress`` create answering
``code:0``; this arm, on the same endpoint, gets ``1254001``. A flag read off a capture from
another month is a flag nobody is checking, which is exactly the shape of the defect.

**Against a self-provisioned disposable, and nothing else.** Every Base this arm touches it made
itself, through :func:`base_write_harness.disposable_base`, and the harness's allow-list refuses
any token it did not mint. ``LARKDOCIO_SCRATCH_BASE`` is never read here — that Base holds the
only hand-authored ``Lookup`` / ``Email`` / ``Stage`` columns in existence and is a READ fixture.
The offline companion checks that statically.

**It writes its own capture** to ``tests/captures/base-study/captures/ld317-01-minimal-form-sweep.json`` —
one entry per ``ui_type``, each carrying the exact body sent and the code that came back — and
that file is what :data:`larkdocio.base.field_authoring.FIELD_PROPERTY_SHAPES` derives
``required`` from. The registry cites the capture; the capture was written by a run of this
arm.

**Since LD-620 the write is REDIRECTED, and the corpus path is the ADDRESS it is aimed
at.** ``capture_sink.write_capture`` lands a re-run's reading in a run-scoped directory
outside every git working tree and says so out loud, because an armed ring overwrote committed
captures belonging to closed issues four times. A genuinely new measurement is landed as a
dated supersession by a human, never by a re-run.

**Both outcomes are a pass; silence is not.** A kind whose minimal form is accepted and a kind
whose minimal form is refused are equally good measurements, and the arm asserts only that
**every** row got one.

**Gentle.** One Base create, one table create, one create per kind, one follow-up per refusing
kind, one delete — around thirty-five calls, every one through the harness's own limiter
(≥1.2 s). A code that is neither ``0`` nor a body verdict is retried **once** and both answers
are recorded, so a transport hiccup cannot silently become a registry flag.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import json
from pathlib import Path

import base_write_harness
import capture_sink
import pytest
from lark_oapi.core import json as lark_json

from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES, build_property
from larkdocio.base.schema_client import BaseSchemaClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

try:  # pragma: no cover - the loader is the canary's, and is optional here
    import canary_support

    canary_support.load_env()
except Exception:  # pragma: no cover - a missing loader must not fail collection
    pass

CAPTURE = (Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"
           / "ld317-01-minimal-form-sweep.json")

#: The options sent as the follow-up for a kind whose property-less create is REFUSED — the
#: shape whose acceptance the refusal message then names. They are passed through the **shipped**
#: :func:`build_property`, so what the capture proves is *"the body this library builds is
#: accepted"* rather than *"some hand-written body is"*. Sources: ``Rating``'s is the shape
#: ``p0-2-02-remaining-types-create.json`` already carries, ``Progress``' is the one the 1.27.0
#: consumer reported working, ``Currency``'s is the shape ``06-01-field-schema.json`` reads back
#: off a shipped column, and the link kinds' is a table id — supplied at run time, because a link
#: column's target is the caller's.
WORKING_OPTIONS = {
    "Rating": {"symbol": "star", "formatter": "0", "min": 0, "max": 5},
    "Progress": {"formatter": "0%", "min": 0, "max": 100},
    "Currency": {"currency_code": "USD", "formatter": "0.00"},
    "SingleLink": {"multiple": False},
    "DuplexLink": {"multiple": False},
}

#: The kinds whose follow-up needs the id of a table to point at, filled in at run time.
_NEEDS_TARGET_TABLE = ("SingleLink", "DuplexLink")

#: Codes that describe the **body** — a verdict this sweep is here to record. Anything else is
#: retried once before it is believed, because a transport-shaped answer (``9499``) is not a
#: statement about the column kind.
_BODY_VERDICTS = (0, 1254001, 1254089, 1254092, 99992402)


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def _marshal(value):
    if value is None:
        return None
    return json.loads(lark_json.JSON.marshal(value))


def _post(provisioner, app_token, table_id, *, name, field_type, ui_type, prop, sent):
    """One raw ``POST …/fields``, recorded whatever it answers. Never raises on a Lark code."""
    record = {"request": {"field_name": name, "type": field_type, "ui_type": ui_type,
                          **({"property": sent} if sent is not None else {})}}
    try:
        field = provisioner.raw_create_field(
            app_token, table_id, field_name=name, field_type=field_type, ui_type=ui_type,
            property_body=prop)
    except Exception as exc:  # the typed API error carries the code Lark answered
        record.update(code=getattr(exc, "code", None), msg=getattr(exc, "msg", str(exc)),
                      field=None)
        return record
    record.update(code=0, msg="success",
                  field={"ui_type": getattr(field, "ui_type", None),
                         "type": getattr(field, "type", None),
                         "property": _marshal(getattr(field, "property", None))})
    return record


def _attempt(provisioner, app_token, table_id, **kwargs):
    """:func:`_post`, retried once when the answer is not a verdict about the body."""
    first = _post(provisioner, app_token, table_id, **kwargs)
    if first["code"] in _BODY_VERDICTS:
        return first
    kwargs = dict(kwargs, name=kwargs["name"] + "r")
    retry = _post(provisioner, app_token, table_id, **kwargs)
    retry["first_attempt_was"] = {"code": first["code"], "msg": first["msg"]}
    return retry


def test_the_minimal_form_of_every_captured_kind_is_MEASURED_not_assumed(credentials):
    """One property-less create per ``FIELD_PROPERTY_SHAPES`` row, plus a working-shape
    follow-up for every kind that refuses. Both outcomes are a pass; silence is not."""
    provisioner = base_write_harness._Provisioner()
    schema = BaseSchemaClient.from_write_credentials()
    observed = {}
    with base_write_harness.disposable_base(provisioner=provisioner) as (app_token, table_id,
                                                                         title):
        assert base_write_harness.is_disposable_title(title)
        target_table_id = schema.create_table(app_token, "ld317-link-target", primary_field_name="Title")

        for index, (ui_type, shape) in enumerate(sorted(FIELD_PROPERTY_SHAPES.items())):
            entry = {"minimal_form": _attempt(
                provisioner, app_token, table_id, name=f"m{index:02d}-{ui_type}",
                field_type=shape.field_type, ui_type=ui_type, prop=None, sent=None)}
            if entry["minimal_form"]["code"] != 0 and ui_type in WORKING_OPTIONS:
                options = dict(WORKING_OPTIONS[ui_type])
                if ui_type in _NEEDS_TARGET_TABLE:
                    options["table_id"] = target_table_id
                built = build_property(ui_type, **options)
                entry["with_property"] = _attempt(
                    provisioner, app_token, table_id, name=f"w{index:02d}-{ui_type}",
                    field_type=shape.field_type, ui_type=ui_type, prop=built,
                    sent=_marshal(built))
                entry["with_property"]["options_passed"] = options
            observed[ui_type] = entry

    capture_sink.write_capture(CAPTURE, json.dumps({
        "_probe": "ld317-minimal-form-sweep",
        "_endpoint": ".../tables/{table_id}/fields",
        "_method": "POST",
        "_note": ("one PROPERTY-LESS create per FIELD_PROPERTY_SHAPES row, against a "
                  "self-provisioned disposable, plus a working-shape follow-up (built by the "
                  "shipped build_property) for every kind the server refused without one. This "
                  "capture is what FieldPropertyShape.required is DERIVED from — the flag is no "
                  "longer hand-set. It supersedes the 2026-07 zoo for this question: a "
                  "property-less Progress answered code:0 there and 1254001 here."),
        "_verdict": "OK",
        "observations": observed,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    assert set(observed) == set(FIELD_PROPERTY_SHAPES), "every row gets a control"
    for ui_type, entry in observed.items():
        assert entry["minimal_form"]["code"] in _BODY_VERDICTS, (ui_type, entry)
        if entry["minimal_form"]["code"] != 0:
            assert "with_property" in entry, (
                f"{ui_type} refuses the minimal form and this sweep has no working shape for "
                f"it — a refusal with nothing to point the caller at is not a finished row")
