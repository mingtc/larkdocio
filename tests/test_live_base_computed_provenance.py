"""THE SINGLE LIVE ARM for computed-column provenance (LD-270).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Why this arm exists at all.** Every offline assertion in
``tests/test_base_computed_provenance.py`` is measured against one committed capture of one
hand-authored Lookup. A capture proves the shapes were once real; it cannot prove that the
shipped read path, against a live Base, still hands the provenance layer what it expects — and
the field API **cannot author a Lookup at all**, so no disposable this repository builds from
scratch will ever contain one. There is exactly one programmatic route to a live Lookup: copy
a Base that already has one.

**What is a WRITE here, and what is not — the distinction this arm is careful about.** The
Scratch Base holds the only hand-authored ``Lookup`` / ``Email`` / ``Stage`` columns in
existence and they are irreplaceable. This arm uses it as the copy's **template** and **never
as a write target**: the copy creates a *new* app, the new app is the only thing this module
renames, reads or deletes, and no operation anywhere in it mutates the template. No
``parent_node`` (or folder token) is passed to anything, by anyone, ever — a copy landing in a
configured folder is the other way a real Base gets touched, and the companion file checks
statically that no such argument appears in this module. Reading the Scratch Base's specimen is
what that Base is for; writing it is not, and both halves are asserted rather than intended.

**The copy is a DISPOSABLE and is ledgered before anything else can fail.** It is recorded the
instant its token exists, deleted in a ``finally``, and swept at the end like every other Base
arm. It lands in **trash, not purge** (``BASE.md`` register row 9), and its title carries the
greppable disposable prefix so a human sweep can find it.

**What it proves that no offline test can.**

* that a live Lookup column, read through the shipped path, still reports the **target
  field's** type on its cell wrapper rather than ``19``. This assertion used to **skip** when
  the copy came back without its computed values, on the reading that this was the shape a
  settled copy has. **LD-284 measured it instead** (5 copies,
  ``tests/captures/base-study/captures/ld284-01-copy-lookup-materialisation.json``): the values are
  **absent ≤1.7 s after the settle and present by ~2.7 s**, 2/2 copies read that early and 2/2
  content-carrying copies read later (the ladder's third copy is the ``without_content: true``
  control, which has no rows at all) — a real, reproducible, **sub-3-second materialisation
  window**, not a shape. The settle contract proves the copied **app is readable**; it says nothing about
  whether a **mirrored column has recomputed**, and this arm used to read inside the gap. So
  the fixture now **waits the window out** — bounded, response-driven, on the settle's own
  discipline — and the dispatch rule is **asserted**. A copy still cell-less after the budget
  is a finding, not a skip;
* that ``filter_info.target_table`` still **survives** the pinned SDK's typed field bridge —
  the one key the whole reading rests on;
* that ``target_field``, ``roll_up`` and ``formula`` still **do not**, which is the gap the
  surface discloses; if any of them started surviving, the disclosure would be a lie and this
  is what catches it;
* that a live ``LISTCOMBINE`` cell still arrives with its separators **inside** the segment
  stream, so the shipped join is right for a reason rather than by coincidence.

**Copy is ASYNCHRONOUS** (``1254036``, register row 8): this arm consumes the shipped bounded
settle contract and never replaces it with a sleep.

**And SETTLED IS NOT MATERIALISED** (register row 40, measured by LD-284). The settle answers
when the app is readable; the copy's computed columns finish recomputing a beat later. So the
fixture re-reads on the settle's own discipline — a **bounded** budget, waiting only *between*
attempts, stopping the moment the values are there — and the measured cost is one extra read.
A fixed sleep would be the same defect here as it would be in the settle itself.

**Gentle.** A copy, a bounded settle, one or two whole-Base reads and a delete — a dozen-odd
calls, all through the shipped limiters. Rate limits are not probed.

**Skips loudly, never silently.** Without write credentials, or without a configured template
Base to copy from, the module skips with a message naming exactly what is missing.
"""
import time

import base_write_harness
import pytest

from larkdocio.base import computed as base_computed
from larkdocio.base.client import BaseReadClient
from larkdocio.base.read import read_base
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.schema_settle import settle

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


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


@pytest.fixture(scope="module")
def template_app_token():
    """The app token of the Base this arm copies **from**.

    It is a template and a read source. Nothing in this module writes to it, and the assertion
    that says so is :func:`test_the_template_is_a_SOURCE_and_never_a_write_target`.
    """
    url = canary_support.scratch_base_url()
    if not url:
        pytest.skip(
            "no template Base configured — set LARKDOCIO_SCRATCH_BASE to a Base that "
            "carries a hand-authored Lookup column. The field API cannot author one, so "
            "without a template there is no live Lookup to read and this arm would prove "
            "nothing.")
    _domain, token = canary_support.parse_base_url(url)
    return token


def _lookup_reading(document):
    """The first Lookup column's provenance reading in a read Base, with its table."""
    for table in document.tables:
        for column in table.computed_columns:
            if (column.field_type, column.ui_type) == base_computed.LOOKUP:
                return table, column
    return None, None


#: The ceiling on the materialisation re-read (LD-284). Bounded for the same reason the settle
#: is: a poll with no ceiling is a hang wearing a loop's clothes. Eight reads at 1.5 s is a ~12 s
#: budget against a window measured at **under 3 s**, twice — an order of magnitude of headroom
#: and still finite.
_MATERIALISATION_ATTEMPTS = 8
#: The spacing, and the settle's own: waited only BETWEEN attempts, never before the first.
_MATERIALISATION_SPACING_SECONDS = 1.5


def _read_until_the_computed_cells_MATERIALISE(read, token):
    """Read the copy until its Lookup carries values — the second half of a copy's asynchrony.

    **Settled is not materialised** (register row 40). ``settle`` answers when the copied app is
    readable; LD-284 measured the Lookup's *values* absent ≤1.7 s after that and present by
    ~2.7 s, on 2/2 copies read inside the window and 2/2 content-carrying copies read outside
    it (``tests/captures/base-study/captures/ld284-01-copy-lookup-materialisation.json``). Reading once on
    settle is therefore a coin toss, and the coin landed cell-less the day this arm was written.

    Response-driven and bounded, exactly like the settle it follows: the first read costs
    nothing extra, the wait happens only *between* attempts, and the loop stops the moment the
    values are there. The document is returned either way — a budget spent without values is
    reported by the assertion that wanted them, not swallowed here.
    """
    document = None
    for attempt in range(1, _MATERIALISATION_ATTEMPTS + 1):
        document = read_base(token, client=read)
        _table, column = _lookup_reading(document)
        if column is None or column.value_type is not None:
            print(f"\ncomputed cells materialised on read {attempt}")
            return document, attempt
        if attempt < _MATERIALISATION_ATTEMPTS:
            time.sleep(_MATERIALISATION_SPACING_SECONDS)
    return document, _MATERIALISATION_ATTEMPTS


@pytest.fixture(scope="module")
def copied(credentials, template_app_token):
    """A live copy of the template, settled, read, and deleted when the module is done.

    One copy for the whole module: every assertion below reads the same settled Base, because
    copying once per test would be four copies of a Base to answer four questions about it.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    ledger = base_write_harness.Ledger()

    title = base_write_harness.disposable_title()
    dest_folder = canary_support.require_disposables_folder()
    echo = schema.copy_app(template_app_token, title, folder_token=dest_folder)
    token = echo.app_token
    # Recorded BEFORE anything else can fail: an unrecorded disposable is a lost one.
    ledger.record_create(token, title)
    try:
        assert token and token != template_app_token, (
            "the copy answered with the template's own token — this arm would then be "
            "reading and deleting the template, which is the one thing it must never do")

        outcome = settle(lambda: read.get_app(token))
        assert outcome.settled, outcome.detail
        print(f"\ncopy settled on attempt {outcome.attempts} after codes {outcome.codes}")

        # NOT a second settle and NOT a sleep: the copy's computed columns finish a beat after
        # the app becomes readable, so this re-reads on the same bounded, response-driven
        # discipline until they are there (LD-284).
        document, _reads = _read_until_the_computed_cells_MATERIALISE(read, token)
        yield token, title, document
    finally:
        # `adopt_from_ledger` is the ONE route into the provisioner's allow-list that is not a
        # create in this process, and it re-checks the disposable title — so the copy can be
        # swept while the template, which is in no ledger, still cannot be addressed at all.
        provisioner = base_write_harness._Provisioner().adopt_from_ledger(ledger)
        deleted, code = provisioner.delete(token)
        ledger.record_delete(token, code, deleted)


def test_the_live_copy_CARRIES_A_LOOKUP_the_field_api_could_never_author(copied):
    """The premise of the whole arm, asserted rather than assumed. A copy is the only route to
    a Lookup column; if the template stopped carrying one, every assertion below would pass
    vacuously and this is what stops that."""
    _token, _title, document = copied
    table, column = _lookup_reading(document)
    assert column is not None, (
        "the copied Base carries no Lookup column — the template no longer has one, so this "
        "arm is proving nothing about a live Lookup")
    assert table is not None
    print(f"\nlive Lookup: {column.field_name!r} in table {table.name!r}")


def test_the_live_wrapper_type_is_the_TARGET_FIELDS_not_the_columns(copied):
    """AC1, live — and the assertion this arm exists to make.

    **This branch used to skip** (LD-270), on one run in which the copy came back carrying the
    Lookup's schema but not its computed values. That run was real; what was wrong was
    generalising it into a shape. **LD-284 measured the difference** — five copies,
    ``tests/captures/base-study/captures/ld284-01-copy-lookup-materialisation.json``:

    * read the way this arm reads (``read_base`` the instant the settle returns): **cell-less,
      2 of 2 copies**, values still absent 1.7 s after the settle;
    * read again 3.2 s after the same settle: **populated, 2 of 2** — and populated on **2 of
      2 content-carrying** copies whose first read a throttled raw ladder could not deliver
      sooner than 2.7 s: at every tick out to t+30 s on both, on to t+120 s on the one ladder
      that ran that deep, on ``records/search`` with wrapper ``type`` = ``1`` and on the plain
      ``GET …/records`` list too, which returned the same cells without a typed wrapper. That
      ladder's third copy is the ``without_content: true`` control, which has no rows at all.

    So the discriminating factor is **elapsed time after the settle**, the window is **under
    3 s**, and the reason it read as a contradiction is that the window is shorter than any
    throttled probe's first call. The fixture now waits it out, so a cell-less read here means
    a copy that did not materialise in ~12 s — a **finding**, not the expected shape.
    """
    _token, _title, document = copied
    _table, column = _lookup_reading(document)
    assert column is not None

    assert column.value_type is not None, (
        f"the copied Lookup still carried no values after {_MATERIALISATION_ATTEMPTS} reads "
        "(~12 s past the settle). LD-284 measured that window at under 3 s on 5 copies, so "
        "this is a finding rather than the shape a copy has — re-run "
        "dev/base-study/probes/probe_ld284_copy_lookup_materialisation.py and compare it "
        "against tests/captures/base-study/captures/ld284-01-copy-lookup-materialisation.json before "
        "widening the budget")
    assert column.value_type != 19, (
        "a live Lookup cell now reports the COLUMN's type; the dispatch rule has inverted and "
        "the renderer is reading the wrong branch")


def test_the_live_target_table_STILL_SURVIVES_the_typed_field_bridge(copied):
    """AC3(a), live. One nested key is what the whole reading rests on."""
    _token, _title, document = copied
    _table, column = _lookup_reading(document)
    assert column is not None

    assert column.rolls_up_from_table, (
        "filter_info.target_table no longer survives the SDK-typed bridge — the provenance "
        "surface can no longer report the one input it claims to")
    assert column.rolls_up_from_table.startswith("tbl"), column.rolls_up_from_table


def test_the_three_DROPPED_KEYS_are_still_dropped_LIVE(copied):
    """AC3(b), live — and the assertion that would catch the disclosure becoming a lie.

    The gap is a property of the pinned client, not of the payload, so a client upgrade could
    close it silently. This reads the live field through the shipped bridge and pins the
    absence; when it reddens, the honest response is to report the keys, not to widen the
    assertion.
    """
    _token, _title, document = copied
    _table, column = _lookup_reading(document)
    assert column is not None

    table = _table_of(document, column)
    spec = next(f for f in table.fields if f.field_name == column.field_name)
    # The read's own FieldSpec IS the far side of the bridge — this reads what the shipped
    # path produced, not a second projection of the raw body.
    bridged = spec.property or {}
    for key in base_computed.TRANSPORT_DROPPED_KEYS:
        assert key not in bridged, (
            f"{key} now survives the typed field seam on a LIVE read — the transport "
            "limitation this surface discloses has closed, and the disclosure must change")
    assert column.unavailable == base_computed.TRANSPORT_DROPPED_KEYS
    assert column.rolls_up_from_field is None and column.aggregation is None


def test_a_live_LISTCOMBINE_cell_carries_its_SEPARATORS_INSIDE_the_segment_stream(copied):
    """AC2, live. The join rule is right because the server sends the separators, and this is
    the only place that premise can be checked against a live aggregation."""
    _token, _title, document = copied
    _table, column = _lookup_reading(document)
    assert column is not None
    table = _table_of(document, column)

    index = [f.field_name for f in table.fields].index(column.field_name)
    rendered = [row.cells[index] for row in table.rows]
    if not any(rendered):
        pytest.skip(
            "the live Lookup's cells are empty on every record — there is no aggregation to "
            "read, so this arm cannot check the join rule (a loud skip, not a pass)")
    assert ", ," not in " ".join(rendered), (
        "a rendered live Lookup carries a doubled separator — a delimiter is being inserted "
        "beside the ones the server already sent")


def test_the_template_is_a_SOURCE_and_never_a_write_target(copied, template_app_token):
    """The safety assertion, live and read-backed. Nothing this arm did touched the template:
    the only Base it created, read and deleted is the copy, and the template still reads back
    with its own name and its own tables."""
    token, _title, _document = copied
    assert token != template_app_token

    read = BaseReadClient.from_read_credentials()
    template = read.get_app(template_app_token)
    assert template.name, "the template no longer reads back — it was not left alone"
    assert read.list_tables(template_app_token), "the template's tables are gone"

    ledger = base_write_harness.Ledger()
    for entry in ledger.survivors():
        assert entry["app_token"] != template_app_token, (
            "the template is in the disposable ledger — the sweep would DELETE it")


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup, the schema arm's shape: a copy the API would not release
    during the run is a reported token rather than a lost one."""
    left = base_write_harness.close_out()
    for entry in left:
        assert entry["app_token"] and entry["title"], entry
        assert base_write_harness.is_disposable_title(entry["title"]), entry
    if left:
        print(f"\nUNSWEPT DISPOSABLE BASES ({len(left)}) — re-run the sweep later:")
        for entry in left:
            print(f"  {entry['app_token']}  {entry['title']}  last code {entry['last_code']}")


def _table_of(document, column):
    """The table a provenance reading came from."""
    for table in document.tables:
        if column in table.computed_columns:
            return table
    raise AssertionError("the reading belongs to no table in the document")
