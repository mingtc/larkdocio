"""LD-314 AC3 — THE VIEW-SCOPED READ, proven against the view's OWN saved filter.

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Why this arm needs a write at all, and where those writes go.** The claim is *"a ``view_id``
read returns the rows the saved view shows"*, and it cannot be made against a view with no saved
filter: ``06-05-view-scoping.json`` did exactly that and got ``code:0`` / ``n=11``, which is
R12-shaped non-evidence — an ignored ``view_id`` returns the same. So the fixture is a view with
a **filter that admits some rows and not others**, and nothing like it exists in the configured
Scratch Base, which is a READ fixture and untouchable. Every write here therefore lands on a
Base this arm **created itself** through :func:`base_write_harness.disposable_base`, recorded in
the ledger the instant it exists and deleted in a ``finally``. This module never reads
``LARKDOCIO_SCRATCH_BASE``.

**The differential.** Three reads of the same table in the same run:

* **unscoped** — the whole table;
* **through the FILTERED view** — must be exactly the rows its saved filter admits, which is a
  strict subset;
* **through the DEFAULT view, which has no filter** — the R12 control, and the honest one: it is
  the reading that *looks* like a ``view_id`` being honoured while proving nothing, so it is run
  beside the positive result rather than instead of it.

The saved filter is not assumed either: it is read back from
``property.filter_info`` with :meth:`BaseReadClient.get_view` — the endpoint a view write is
already verified through — and the rows the ``view_id`` read returned are checked against
**that**, not against what the arm asked for.

**Gentle.** Around a dozen calls at ≥1.2 s spacing. **Skips loudly, never silently.**
"""
import base_write_harness
import pytest

from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.view_filters import (
    Condition,
    FieldName,
    FieldRegistry,
    FilterSpec,
    view_filter,
)
from larkdocio.base.view_plan import create_view, set_view_filter
from larkdocio.base.write_client import BaseWriteClient

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

#: The three seeded rows. One is the one the view's filter admits; the other two are what a
#: honoured ``view_id`` must exclude.
ADMITTED = "ld314-admitted"
EXCLUDED = ("ld314-excluded-a", "ld314-excluded-b")


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def _text_column(read, app_token, table_id):
    fields = read.list_fields(app_token, table_id)
    name = next((f.field_name for f in fields if f.type == 1), None)
    assert name, "a fresh disposable always ships a text column"
    return name


def _texts(records, column):
    out = []
    for record in records:
        value = (record.fields or {}).get(column)
        if isinstance(value, list):
            out.append("".join(p.get("text", "") for p in value if isinstance(p, dict)))
        elif value is not None:
            out.append(str(value))
        else:
            out.append("")
    return out


def test_THE_VIEW_ID_READ_AGREES_WITH_THE_VIEWS_OWN_SAVED_FILTER(credentials):
    """AC3, end to end: write a filter onto a view, read the filter back, then read records
    THROUGH that view and check them against what the server says the view stores."""
    read = BaseReadClient.from_read_credentials()
    write = BaseWriteClient.from_write_credentials()
    schema = BaseSchemaClient.from_write_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        column = _text_column(read, app_token, table_id)

        # ---- the fixture: three distinguishable rows -------------------------- #
        write.batch_create_records(app_token, table_id, [
            {column: ADMITTED}, {column: EXCLUDED[0]}, {column: EXCLUDED[1]}])

        # ---- a view whose SAVED filter admits exactly one of them ------------- #
        registry = FieldRegistry.from_read_client(read, app_token, table_id)
        wanted = registry.resolve(
            FilterSpec(conditions=(Condition(FieldName(column), "is", (ADMITTED,)),)))
        made = schema_apply(schema_dry_run([
            create_view(app_token, table_id, "ld314-filtered", "grid")]),
            client=schema, read_client=read)
        assert made.entries[0].outcome == "applied", made.entries[0].refusal
        view_id = made.entries[0].read_back["view_id"]
        set_log = schema_apply(schema_dry_run([
            set_view_filter(app_token, table_id, view_id, view_filter(wanted))]),
            client=schema, read_client=read)
        assert set_log.entries[0].outcome == "applied", set_log.entries[0].refusal

        # ---- the saved filter, READ BACK from the server ---------------------- #
        saved = read.get_view(app_token, table_id, view_id).property.filter_info
        conditions = [{"field_id": c.field_id, "operator": c.operator, "value": c.value}
                      for c in (saved.conditions or ())]
        print(f"\nAC3 saved filter_info :: conjunction={saved.conjunction} "
              f"conditions={conditions}")
        assert len(conditions) == 1 and conditions[0]["operator"] == "is", (
            "the fixture's own premise — a view with ONE `is` condition — did not persist")
        admitted_id = registry.field_id_for(column)
        assert conditions[0]["field_id"] == admitted_id

        # ---- the three reads --------------------------------------------------- #
        unscoped = read.search_records(app_token, table_id)
        scoped = read.search_records(app_token, table_id, view_id=view_id)
        default_view = [v for v in read.list_views(app_token, table_id)
                        if v.view_id != view_id][0]
        control = read.search_records(app_token, table_id, view_id=default_view.view_id)

        print(f"AC3 unscoped        :: n={len(unscoped)} texts={_texts(unscoped, column)}")
        print(f"AC3 through view    :: n={len(scoped)} texts={_texts(scoped, column)} "
              f"view_id={view_id}")
        print(f"AC3 R12 control     :: n={len(control)} through the UNFILTERED default view "
              f"{default_view.view_id}")

        # ---- the assertions ---------------------------------------------------- #
        assert ADMITTED in _texts(unscoped, column), "the seed rows are not in the table"
        assert set(r.record_id for r in scoped) < set(r.record_id for r in unscoped), (
            f"the view-scoped read returned {len(scoped)} of {len(unscoped)} rows — an IGNORED "
            "view_id returns the whole table, which is exactly that shape")
        assert _texts(scoped, column) == [ADMITTED], (
            "the rows a view_id read returned are not the rows the SAVED filter admits: "
            f"{_texts(scoped, column)}")
        for excluded in EXCLUDED:
            assert excluded not in _texts(scoped, column)
        assert len(control) == len(unscoped), (
            "the control is the point: reading through a view with NO saved filter returns the "
            "whole table, so a code:0 there proves nothing — which is why AC3 needed a filtered "
            "view")


def test_A_VIEW_ID_AND_A_REQUEST_FILTER_ARE_REFUSED_TOGETHER_before_any_call(credentials):
    """The Decision's uncaptured edge, asserted where a live arm can show it costs no call: the
    refusal is local, so the combination never reaches a Base at all."""
    from larkdocio.base.view_filters import BaseFilterRefusal, search_filter

    read = BaseReadClient.from_read_credentials()
    before = read.api_calls
    with pytest.raises(BaseFilterRefusal) as excinfo:
        read.search_records("appwhatever", "tblwhatever", view_id="vew1",
                            filter=search_filter(FilterSpec(
                                conditions=(Condition(FieldName("Text"), "isNotEmpty"),))))
    assert "uncaptured" in str(excinfo.value).lower()
    assert read.api_calls == before, "the refusal must cost no API call"
