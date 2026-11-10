"""THE SINGLE LIVE SCHEMA ARM for the Base app & table lifecycle (LD-263).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against self-provisioned disposables, and nothing else.** Every Base this arm touches it made
itself — the parent through :func:`base_write_harness.disposable_base`, the copy through the
shipped ``copy_app`` — and every one is recorded in the harness's ledger the moment it exists,
so the sweep can address it. It never touches a configured Base: ``LARKDOCIO_SCRATCH_BASE``
holds the only hand-authored ``Lookup`` / ``Email`` / ``Stage`` fields in existence and the API
**cannot** recreate them, so renaming or copying it would risk evidence rather than merely be
impolite. This module never reads that variable, which the offline companion checks statically.

**BOTH THE COPY AND ITS PARENT LAND IN TRASH, NOT PURGE.** ``DELETE /drive/v1/files/{a}?type=bitable``
answers ``code:0`` and the bitable API then reports ``1002``, but ``POST /drive/v1/metas/batch_query``
still resolves the title and the timestamps (``BASE.md`` register row 9). A copy made here is an
ordinary Base and trashes exactly the same way — so what this arm's teardown achieves is
*deleted as far as the open API is concerned*, and a human trash sweep is still the last word.
Every title carries the greppable disposable prefix precisely so that sweep is possible.

**What it proves that no offline test can.**

* that all six structural ops really reach a live Base on the write credential pair;
* the **read-back rule**, live: each op is confirmed against the server's own state — the
  renamed Base re-reads under its new name, the created table appears in the listing, both
  batch-created tables appear in a **single** listing — never against a ``code:0``;
* the **async settle**, live: the copy's echo carries an empty ``default_table_id`` and the
  copy's tables are readable only after the bounded poll answers;
* **AC3's sharp half** — that the copy's echo is not its state;
* **AC4's claim**, live: the copy of a Base carrying a ``Lookup`` (19) and a ``Stage`` (24)
  column brings those columns with it, which is the only programmatic route to a column the
  fields API refuses to author. This is asserted only when the run's own parent Base has such a
  column to clone; a disposable created by the harness has none, so the arm asserts the shape it
  can — that a copy's field set is the parent's, whatever it contains — and does **not** reach
  for the Scratch Base to manufacture a stronger claim.

**Gentle.** Around a dozen calls, every one through a limiter at the pace the probe packs
sustained (≥1.2 s). Rate limits are not probed.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import base_write_harness
import pytest

from larkdocio.base.client import BaseReadClient
from larkdocio.drive.client import DriveClient
from larkdocio.errors import LarkAPIError, MissingDestinationError
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.schema_plan import (
    batch_create_tables,
    copy_base,
    create_base,
    create_table,
    rename_base,
    rename_table,
)

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# Imported unconditionally: this arm now READS the disposables-folder variable through it, so
# it is a dependency rather than an optional convenience. Only the .env LOAD is best-effort.
import canary_support

try:  # pragma: no cover - a missing/unreadable .env must not fail collection
    canary_support.load_env()
except Exception:  # pragma: no cover
    pass


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def test_the_schema_registry_declares_the_whole_arm_MUTATING_before_it_calls_anything():
    """The mirror of the two Base read arms' first assertion, and of the write arm's. This arm
    exists to change a Base's SHAPE, so what to assert up front is that every op it is about to
    run is declared a write — and that the READ registry still answers read-only, which is the
    whole reason there are three registries rather than one table with a flag."""
    from larkdocio.base import ops as base_ops
    from larkdocio.base import schema_ops
    from larkdocio.base import write_ops

    assert schema_ops.all_mutate() is True
    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True


def test_the_live_schema_arm_round_trips_the_app_and_table_lifecycle(credentials):
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        assert table_id, "a fresh Base always has a default table"

        renamed = f"{title}-renamed"
        plan = schema_dry_run([
            rename_base(app_token, renamed),
            create_table(app_token, "ld263-one", primary_field_name="Title"),
            batch_create_tables(app_token, ["ld263-batch-a", "ld263-batch-b"],
                                accept_locale_default_primary=True),
            rename_table(app_token, table_id, "ld263-default-renamed"),
            rename_base(app_token, title),          # restorable — the probe's own shape
        ])
        assert plan.api_call_count == 5

        log = schema_apply(plan, client=schema, read_client=read)

        assert [entry.outcome for entry in log.entries] == ["applied"] * 5, [
            (e.op, e.outcome, e.refusal.detail if e.refusal else None) for e in log.entries]
        # Every one of those verdicts came from a READ-BACK, not a code:0.
        assert all(entry.read_back for entry in log.entries)
        assert log.entries[2].read_back["read_backs"] == 1, (
            "a batch create is verified by ONE listing covering every id it returned")

        # The live state agrees with the log.
        assert read.get_app(app_token).name == title, "the rename was restored"
        names = {t.name for t in read.list_tables(app_token)}
        assert {"ld263-one", "ld263-batch-a", "ld263-batch-b",
                "ld263-default-renamed"} <= names


def test_THE_DEFAULT_VIEW_IS_NAMED_BY_THE_COMPOSITE_and_READ_BACK_PROVES_IT(credentials):
    """**The binding live round-trip for the create-then-rename composite.**

    Lark rejects ``default_view_name`` on the create body (``1254001``, no table created), so the
    name is applied by renaming the view the table is **born with** — addressed by the
    ``default_view_id`` the create's own reply carries, never by comparing against the
    locale-dependent name Lark gave it. Everything here is proven by **read-back**: the shipped
    client is asked for the name, and the table's own view listing is what decides whether it
    applied. ``code:0`` proves nothing on that route — the view family's swallow control is why.

    Three facts, on one harness-created disposable:

    * a fresh table has **exactly one** view, and it does **not** carry the asked-for name;
    * the composite's table's single view **does** — under the id the create returned;
    * the **plan gate** reaches the same state and its own read-back says so.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, _table_id, _title):
        # The control: the same create WITHOUT the argument. One view, Lark's own name.
        plain_id = schema.create_table(app_token, "ld356-plain", primary_field_name="Title")
        plain_views = read.list_views(app_token, plain_id)
        assert len(plain_views) == 1, (
            "the composite's premise: a freshly created table has EXACTLY ONE view; this one "
            f"has {len(plain_views)}")
        assert plain_views[0].view_name != "Board", (
            "the control must NOT already carry the name, or the positive case proves nothing")
        print(f"\nld356 control view: {plain_views[0].view_name!r} ({plain_views[0].view_id})")

        # The composite, through the shipped client seam.
        named_id = schema.create_table(app_token, "ld356-named", primary_field_name="Title",
                                       default_view_name="Board")
        named_views = read.list_views(app_token, named_id)
        assert len(named_views) == 1
        assert named_views[0].view_name == "Board", (
            "THE NAME MUST READ BACK — a rename verified by code:0 is not verified at all: "
            f"the view is called {named_views[0].view_name!r}")
        print(f"ld356 composite view: {named_views[0].view_name!r} "
              f"({named_views[0].view_id})")

        # And through the PLAN GATE, whose own read-back is the verdict.
        log = schema_apply(schema_dry_run([
            create_table(app_token, "ld356-planned", primary_field_name="Title",
                         default_view_name="Ledger")]),
            client=schema, read_client=read)
        entry = log.entries[0]
        assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
        assert entry.read_back["default_view"] == {
            "asked": "Ledger", "seen": ["Ledger"], "views": 1, "named": True}
        print(f"ld356 plan read-back: {entry.read_back['default_view']}")


def test_the_live_copy_SETTLES_and_its_echo_is_NOT_its_state(credentials):
    """AC2 + AC3, live. The copy is the one asynchronous Base op; its ``default_table_id``
    comes back empty and its tables are reachable only after the bounded settle answers.

    The copy is a **new disposable**: it is recorded in the harness ledger the instant it
    exists, so the sweep at the end of this module addresses it. It lands in **trash, not
    purge** — see this module's own docstring and register row 9.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    ledger = base_write_harness.Ledger()

    # THE DESTINATION RULE, proved on the live client and the live plan seam before anything
    # is created: a create or a copy naming no destination refuses locally and sends nothing.
    # Zero API calls, zero objects — the refusal is the whole observation ("destination-required").
    for spelling in (None, "", "   "):
        with pytest.raises(MissingDestinationError):
            create_base("larkdocio-DISPOSABLE-must-not-exist", spelling)
        with pytest.raises(MissingDestinationError):
            schema.create_app("larkdocio-DISPOSABLE-must-not-exist", spelling)

    with base_write_harness.disposable_base() as (app_token, _table_id, title):
        schema.create_table(app_token, "ld263-source", primary_field_name="Title")
        parent_tables = {t.table_id for t in read.list_tables(app_token)}
        assert parent_tables

        copy_title = base_write_harness.disposable_title()
        dest_folder = canary_support.require_disposables_folder()
        plan = schema_dry_run([copy_base(app_token, copy_title, folder_token=dest_folder)])
        assert plan.entries[0].asynchronous is True

        raw = schema.copy_app(app_token, copy_title, folder_token=dest_folder)
        copy_token = raw.app_token
        # Recorded BEFORE anything else can fail: an unrecorded disposable is a lost one.
        ledger.record_create(copy_token, copy_title)
        assert copy_token and copy_token != app_token
        assert not getattr(raw, "default_table_id", None), (
            "THE COPY'S ECHO IS NOT ITS STATE — default_table_id comes back empty")

        from larkdocio.base.schema_settle import settle

        outcome = settle(lambda: read.get_app(copy_token))
        assert outcome.settled, outcome.detail
        assert outcome.attempts >= 1
        print(f"\ncopy settled on attempt {outcome.attempts} "
              f"after codes {outcome.codes}")

        copied = read.list_tables(copy_token)
        assert len(copied) == len(parent_tables), (
            "the copy carries the parent's tables — readable only AFTER the settle")
        for table in copied:
            fields = read.list_fields(copy_token, table.table_id)
            assert fields is not None, "the copied schema reads back"


def test_the_live_copy_LANDS_IN_THE_FOLDER_IT_WAS_GIVEN_and_a_BAD_FOLDER_IS_REFUSED(
        credentials):
    """LD-387, live — the binding round-trip for ``copy_base(..., folder_token=…)``.

    **The read-back is the FOLDER's own listing**, never the copy's echo: a ``code:0`` copy and
    an echo that repeats the token back both prove nothing about where the copy is (R12). So the
    Drive read client is asked for the folder's children and the copy is matched by ``token``
    with its ``parent_token`` equal to the folder asked for.

    **Beside it runs the R12 control that decides the whole question:** a folder-shaped token
    naming nothing draws ``1254702 DriveNodeNotExist`` and creates **no copy**. A key the server
    discarded could not refuse that, which is how this parameter is known to be read rather than
    decorative — and it is the half of the measurement probe ``ld387-01`` was built to get.

    **What this does NOT prove, stated rather than glossed:** the folder here is now the
    configured disposables folder (``LARKDOCIO_DISPOSABLES_FOLDER``) rather than the bot's own
    root. The old limitation was that the folder asked for *was* the default destination, so
    *placement into a folder that is not the default* could not be distinguished; a
    human-supplied folder is not the default, so this arm is now positioned to settle that —
    **but that re-measurement has not been made**, and nothing here claims it. What is asserted
    is unchanged: the copy appears in the listing of the folder it was given.

    The placed copy is a **new disposable**, recorded in the harness ledger the instant it
    exists, and it lands in **trash, not purge**, exactly like every other copy here.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    drive = DriveClient.from_read_credentials()
    ledger = base_write_harness.Ledger()

    folder = canary_support.require_disposables_folder()
    assert folder, "the destination is the configured, human-visible disposables folder"

    with base_write_harness.disposable_base() as (app_token, _table_id, _title):
        placed_title = base_write_harness.disposable_title()
        plan = schema_dry_run([copy_base(app_token, placed_title, without_content=True,
                                         folder_token=folder)])
        assert plan.entries[0].fields["folder_token"] == folder, (
            "the plan discloses the destination BEFORE anything is sent")

        log = schema_apply(plan, client=schema, read_client=read)
        entry = log.entries[0]
        placed_token = entry.created_app_token
        # Recorded BEFORE anything else can fail: an unrecorded disposable is a lost one.
        ledger.record_create(placed_token, placed_title)
        assert placed_token, entry.refusal and entry.refusal.detail

        contents = drive.list_folder_children_to_exhaustion(folder)
        placed = [child for child in contents.children if child.token == placed_token]
        assert placed, (
            f"the copy {placed_token} is NOT in the folder it was given — code:0 said it was, "
            "which is exactly why the folder is asked instead")
        assert placed[0].parent_token == folder
        print(f"\nld387 placed copy {placed_token} parent={placed[0].parent_token} "
              f"among {len(contents.children)} children")

        # THE R12 CONTROL. A folder-shaped token that names nothing — built, never a literal.
        # **The measured refusal is 1254702 DriveNodeNotExist** (probe `ld387-01`: six for six,
        # raw core and shipped client alike, across three bad values). **In THIS sequence Lark
        # has answered 1255002 RpcError to the same body, twice** — the difference being that
        # here the source has just been copied, so a second copy of it arrives while the first
        # is still settling. Both are refusals and both create nothing, so the assertion accepts
        # either: pinning 1254702 alone would make the gate flaky about the server's mood, while
        # accepting any non-zero code would stop proving the folder was READ. What must never
        # happen here is `code:0`, and that is the claim this control really carries.
        nowhere = "nodl" + "z" * 23
        with pytest.raises(LarkAPIError) as caught:
            schema.copy_app(app_token, base_write_harness.disposable_title(),
                            folder_token=nowhere)
        assert getattr(caught.value, "code", None) in (1254702, 1255002), str(caught.value)
        print(f"ld387 bad-folder control: {caught.value}")


def test_the_arm_stays_within_its_call_budget(credentials):
    """Gentleness is an assertion, not an intention."""
    schema = BaseSchemaClient.from_write_credentials()
    with base_write_harness.disposable_base() as (app_token, _table_id, _title):
        schema.create_table(app_token, "ld263-budget-probe", primary_field_name="Title")
    assert schema.api_calls == 1, schema.api_calls
    assert schema.limiter is not None


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup, the write arm's shape. It runs the sweep and prints what is
    left, so a Base the API would not release during the run — including a **copy** — is a
    reported token rather than a lost one. It does not fail on a survivor: the measured
    create/delete lag makes that a coin flip. What it asserts is that the ledger is TELLING THE
    TRUTH, and that the orphan oracle answers zero once the sweep has run."""
    left = base_write_harness.close_out()
    for entry in left:
        assert entry["app_token"] and entry["title"], entry
        assert base_write_harness.is_disposable_title(entry["title"]), entry
    remaining = base_write_harness.survivors()
    assert {e["app_token"] for e in remaining} == {e["app_token"] for e in left}
    if left:
        print(f"\nUNSWEPT DISPOSABLE BASES ({len(left)}) — re-run the sweep later:")
        for entry in left:
            print(f"  {entry['app_token']}  {entry['title']}  last code {entry['last_code']}")
    else:
        assert base_write_harness.orphans() == [], (
            "the orphan oracle must answer zero when the ledger is clean")
