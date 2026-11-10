# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-263 AC8 / AC9 — the SCHEMA half of `/BASE.md`, and the permission rows behind it.

The drift guard for the third operations table, held **bidirectionally against the code**: every
registered schema op has exactly one row and every row a registered op, with the endpoint and
verb cross-checked against the **SDK request class** rather than against the descriptor's own
strings — so the doc and the descriptor cannot agree with each other and both be wrong.

Register row 28 (*app-scoped structural ops carry no revision guard*) is held against the
constant it quotes, and rows 8 and 9 are held to have been **extended**, not replaced: the
copy row now states the shipped settle contract while keeping its copy-status revisit trigger,
and the trash-not-purge row still covers a copied app.

AC8's half: every endpoint the six new call sites reach **resolves** in
:data:`larkdocio.permissions.ENDPOINT_SCOPES` — on the WRITE mode, to the one scope that row
already carries. **No scope is widened, requested or escalated**, and this file asserts that in
both directions.
"""
import re

import pytest

from base_md import register_rows as _register_rows
from base_md import table_with as _table_with
from test_base_md_matrix import _ANCHOR, _REPO_PATH

from larkdocio import permissions as perm
from larkdocio.base import schema_ops
from larkdocio.base.schema_plan import NO_APP_REVISION_CAS
from larkdocio.base.schema_settle import ASYNC_SETTLE_CONTRACT

from guard_kit import REPO_ROOT
import private_tree  # noqa: E402  (LD-685)

# LD-370 — CONFORMANCE-tier: the Base schema surface's matrix rows are product claims, drift-guarded against real code.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

_REPO = REPO_ROOT

_SCHEMA_COLUMNS = ("Operation", "Endpoint", "Verb", "`mutates`", "Family", "Settles",
                   "Code anchor", "Evidence")


@pytest.fixture(scope="module")
def base_md():
    return (_REPO / "BASE.md").read_text(encoding="utf-8")


def _schema_rows(text):
    tables = _table_with(text, "Operation", "`mutates`", "Settles")
    assert len(tables) == 1, "the schema-operations table must be exactly one table"
    return tables[0][1]


def _op_name(row):
    match = re.search(r"`([a-z_]+)`", row["Operation"])
    assert match, row["Operation"]
    return match.group(1)


def _resolves_deep(anchor):
    import importlib

    parts = anchor.split(".")
    for split in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        for name in parts[split:]:
            if not hasattr(obj, name):
                return False
            obj = getattr(obj, name)
        return True
    return False


# --------------------------------------------------------------------------- #
# AC9 — the schema-operations table, bidirectional                             #
# --------------------------------------------------------------------------- #

def test_the_schema_table_has_the_EIGHT_declared_columns(base_md):
    assert tuple(_table_with(base_md, "Operation", "`mutates`", "Settles")[0][0]) == \
        _SCHEMA_COLUMNS


def test_every_registered_SCHEMA_op_has_exactly_one_row_and_vice_versa(base_md):
    documented = [_op_name(row) for row in _schema_rows(base_md)]
    assert len(documented) == len(set(documented)), f"a duplicated op row: {documented}"
    assert set(documented) == {d.name for d in schema_ops.schema_ops()}, (
        "the schema-operations table and the aggregator disagree — touch the surface, update "
        f"the matrix. Documented {sorted(documented)}")


def test_every_SCHEMA_row_states_the_MUTATES_VALUE_THE_REGISTRY_HAS(base_md):
    for row in _schema_rows(base_md):
        descriptor = schema_ops.schema_op(_op_name(row))
        documented = row["`mutates`"].strip().strip("`*").lower()
        assert documented in ("true", "false"), (descriptor.name, documented)
        assert (documented == "true") is descriptor.mutates, descriptor.name


def test_every_SCHEMA_row_states_THE_ENDPOINT_AND_VERB_THE_SDK_ACTUALLY_CALLS(base_md):
    for row in _schema_rows(base_md):
        descriptor = schema_ops.schema_op(_op_name(row))
        built = descriptor.request_cls.builder().build()
        assert row["Endpoint"].strip().strip("`") == built.uri, descriptor.name
        assert row["Verb"].strip().strip("`") == built.http_method.name, descriptor.name


def test_every_SCHEMA_row_states_the_FAMILY_AND_SETTLES_FLAGS_THE_REGISTRY_HAS(base_md):
    for row in _schema_rows(base_md):
        descriptor = schema_ops.schema_op(_op_name(row))
        assert row["Family"].strip() == descriptor.family, descriptor.name
        settles = row["Settles"].strip().strip("*").lower()
        assert settles in ("yes", "no"), (descriptor.name, settles)
        assert (settles == "yes") is descriptor.settles, descriptor.name


def test_EXACTLY_ONE_documented_op_settles_and_it_is_COPY(base_md):
    settling = [_op_name(row) for row in _schema_rows(base_md)
                if "yes" in row["Settles"].lower()]
    assert settling == ["copy_app"]


def test_every_SCHEMA_row_names_a_RESOLVING_code_anchor(base_md):
    offenders = []
    for row in _schema_rows(base_md):
        anchors = _ANCHOR.findall(row["Code anchor"])
        if not anchors:
            offenders.append((_op_name(row), "no anchor"))
        offenders += [(_op_name(row), a) for a in anchors if not _resolves_deep(a)]
    assert not offenders, f"dead anchors in the schema-operations table: {offenders}"


@private_tree.citations
def test_every_SCHEMA_row_carries_evidence_that_EXISTS(base_md):
    missing = []
    for row in _schema_rows(base_md):
        assert row["Evidence"].strip() not in ("", "—", "-", "n/a"), _op_name(row)
        for path in _REPO_PATH.findall(row["Evidence"]):
            target = path.split("::")[0].rstrip(".,;)`")
            if not (_REPO / target).exists():
                missing.append(target)
    assert not missing, f"the schema table cites paths that do not exist: {missing}"


def test_the_THREE_operation_tables_are_DISJOINT(base_md):
    from test_base_md_matrix import _operation_rows, _write_operation_rows

    read_names = {_op_name(r) for r in _operation_rows(base_md)}
    write_names = {_op_name(r) for r in _write_operation_rows(base_md)}
    schema_names = {_op_name(r) for r in _schema_rows(base_md)}
    assert not (read_names & schema_names)
    assert not (write_names & schema_names)
    for row in _schema_rows(base_md):
        assert row["`mutates`"].strip().strip("`*").lower() == "true", _op_name(row)


def test_EVERY_DOCUMENTED_DELETE_NAMES_ITS_BLAST_RADIUS(base_md):
    """Revised deliberately when the destructive family landed.

    The table used to document exactly one delete. It now documents four, and the guard's
    subject moves with them: every documented delete must **name its own blast radius in its
    own row**, because they are not the same size — a view carries no data, a column delete can
    take a second column in another table, and a table delete dangles links app-wide.
    """
    deletes = {_op_name(row): row for row in _schema_rows(base_md)
               if row["Verb"].strip().strip("`") == "DELETE"}
    assert sorted(deletes) == ["delete_field", "delete_table", "delete_view"], sorted(deletes)

    batch = [row for row in _schema_rows(base_md) if "batch_delete" in row["Endpoint"]]
    assert [_op_name(row) for row in batch] == ["batch_delete_tables"], (
        "the one POST-verbed delete — named because a verb-derived reading would miss it")

    for name, row in list(deletes.items()) + [(_op_name(r), r) for r in batch]:
        if name == "delete_view":
            assert row["Endpoint"].strip().strip("`").endswith("/views/:view_id")
            continue
        assert "blast radius" in row["Operation"].lower(), (
            f"{name} can lose data and its row does not name what it reaches")


def test_DEFECT_a_registered_op_with_no_row_reddens(base_md):
    """The guard's own falsification, the completeness half: strike a row and the
    bidirectional check must catch it rather than shrug."""
    stripped = "\n".join(line for line in base_md.splitlines()
                         if not line.startswith("| `rename_table` |"))
    documented = {_op_name(row) for row in _schema_rows(stripped)}
    assert documented != {d.name for d in schema_ops.schema_ops()}
    assert "rename_table" not in documented


def test_DEFECT_a_PHANTOM_row_reddens_the_other_direction(base_md):
    # `delete_app` — the drive-file delete that removes a Base — is the phantom now that the
    # destructive family has made `delete_table` a real, documented op.
    phantom = base_md.replace(
        "| `rename_table` |",
        "| `delete_app` | `/open-apis/drive/v1/files/:file_token` | "
        "`DELETE` | `true` | app-and-table | no | `larkdocio.nope` | `dev/base-study/` |\n"
        "| `rename_table` |", 1)
    documented = {_op_name(row) for row in _schema_rows(phantom)}
    assert "delete_app" in documented
    assert documented != {d.name for d in schema_ops.schema_ops()}


# --------------------------------------------------------------------------- #
# AC9 — register row 28, and the two EXTENSIONS                                #
# --------------------------------------------------------------------------- #

def test_row_28_states_the_NO_APP_REVISION_CAS_fact_and_is_DISTINCT_from_row_25(base_md):
    from larkdocio.base.plan import NO_SERVER_SIDE_CAS

    row = [r for r in _register_rows(base_md) if r["#"] == "28"]
    assert len(row) == 1
    cell = row[0]["Limitation / workaround"]
    assert "app.revision" in cell
    for reading in ("0 → 1", "0 → 14", "0 → 5"):
        assert reading in cell, reading
    assert "read-back" in cell.lower()
    assert "Distinct from row 25" in cell
    assert NO_APP_REVISION_CAS != NO_SERVER_SIDE_CAS
    assert row[0]["Revisit trigger — the observable API change"].strip()


def test_row_8_was_EXTENDED_not_replaced_and_KEEPS_its_copy_status_revisit_trigger(base_md):
    row = [r for r in _register_rows(base_md) if r["#"] == "8"][0]
    cell = row["Limitation / workaround"]
    assert "Base copy is ASYNC-ONLY" in cell, "the original claim survives"
    assert "1254036" in cell
    assert "settle" in cell.lower() and "sleep" in cell.lower()
    assert "larkdocio.base.schema_settle.ASYNC_SETTLE_CONTRACT" in cell
    assert "copy-status endpoint" in row["Revisit trigger — the observable API change"], (
        "the revisit trigger this row shipped with must survive the extension")
    assert row["Status"].strip().strip("`") == "supported", (
        "the ladder step landed; the row is no longer `uncaptured`")


def test_row_9_still_covers_a_COPIED_app_and_now_says_why_that_clause_MATTERS(base_md):
    row = [r for r in _register_rows(base_md) if r["#"] == "9"][0]
    cell = row["Limitation / workaround"]
    assert "DELETE is TRASH, not purge" in cell
    assert "copied apps" in cell
    assert "copy_app" in cell, "the clause is load-bearing now that a copy is a shipped op"


def test_the_settle_contract_QUOTED_in_row_8_is_the_ONE_the_code_exports():
    """The doc names the constant; the constant is the source of truth."""
    assert "BOUNDED" in ASYNC_SETTLE_CONTRACT.upper()
    assert "FIXED SLEEP" in ASYNC_SETTLE_CONTRACT.upper()


def test_the_schema_section_POINTS_AT_rows_8_16_25_and_27_rather_than_restating_them(base_md):
    section = base_md.split("### Schema writes")[1].split("**Error taxonomy")[0]
    for pointer in ("register row 8", "Register row 16", "register row 28", "row 25"):
        assert pointer in section, pointer


# --------------------------------------------------------------------------- #
# AC8 — the permission rows, derived and never widened                         #
# --------------------------------------------------------------------------- #

#: Every endpoint this story's six new call sites reach, derived from the descriptors.
#: **Filtered to this story's own family** now that LD-262 has registered a second one: the
#: claim below is about the six app-and-table call sites, and it stays exactly that claim
#: rather than silently becoming a claim about another family's ops. The field family asserts
#: its own two endpoints, and the view family its own two, in the same three directions, in
#: ``tests/test_base_schema_fields.py`` and ``tests/test_base_schema_views.py``.
def _new_endpoints():
    return sorted({d.endpoint for d in schema_ops.schema_ops()
                   if d.family == "app-and-table"})


def test_the_SCHEMA_call_sites_reach_exactly_the_endpoints_their_ACs_name():
    """LD-263's six app-and-table endpoints, **derived from the descriptors** and filtered to
    this story's own family. The field family asserts its two in
    ``tests/test_base_schema_fields.py`` and the view family its two in
    ``tests/test_base_schema_views.py``, each in the same three directions — which is what
    keeps a family registered later from silently widening *this* claim."""
    assert _new_endpoints() == sorted({
        "/open-apis/bitable/v1/apps",
        "/open-apis/bitable/v1/apps/:app_token",
        "/open-apis/bitable/v1/apps/:app_token/copy",
        "/open-apis/bitable/v1/apps/:app_token/tables",
        "/open-apis/bitable/v1/apps/:app_token/tables/batch_create",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id",
    })


def test_EVERY_new_endpoint_RESOLVES_to_a_write_mode_row_with_its_evidence_and_label():
    for endpoint in _new_endpoints():
        scopes = perm.scopes_for_endpoints((endpoint,), "write")
        assert scopes, f"{endpoint} resolves to no scope row — the requirement is nowhere"
        for scope in scopes:
            assert scope.evidence.strip(), (endpoint, scope.scope)
            assert scope.verification in perm.VERIFICATION_LABELS, scope.verification


def test_NO_SCOPE_IS_WIDENED_the_new_call_sites_need_exactly_what_the_record_writes_need():
    from larkdocio.base import write_ops

    record = {s.scope for d in write_ops.WRITE_OPS
              for s in perm.scopes_for_endpoints((d.endpoint,), "write")}
    schema = {s.scope for e in _new_endpoints()
              for s in perm.scopes_for_endpoints((e,), "write")}
    assert schema == record == {"bitable:app"}


def test_the_READ_MODE_row_is_UNTOUCHED_a_read_still_needs_only_the_readonly_scope():
    from larkdocio.base import ops as base_ops

    read = {s.scope for d in base_ops.OPS
            for s in perm.scopes_for_endpoints((d.endpoint,), "read")}
    assert read == {"bitable:app:readonly"}


def test_NO_ENDPOINT_this_story_adds_is_UNMAPPED():
    for endpoint in _new_endpoints():
        assert perm._table_row(endpoint, "write") is not None, endpoint


def test_the_permissions_TABLE_COMMENT_no_longer_claims_no_schema_write_exists():
    """The comment above the bitable write row said *"No schema write exists yet: every call
    this row covers is a record op."* That sentence became false the moment this rung landed,
    and a false comment above a permission row is exactly the kind of rot the generated matrix
    exists to prevent."""
    source = (_REPO / "src" / "larkdocio" / "permissions.py").read_text(encoding="utf-8")
    assert "No schema write exists yet" not in source
    note = source.split("---- Base (bitable) — the WRITE families")[1][:2000]
    assert "SCHEMA ops" in note
    assert "non-destructive" in note, (
        "the comment has to say which schema ops the row covers")
    # THE BOUNDARY MOVED A SECOND TIME, DELIBERATELY. The claim used to be "one delete verb
    # reaches this row, and no delete that can lose DATA does". The three data-losing deletes
    # now do reach it — so the comment must say so plainly, must say they arrived WITH their
    # fence rather than by widening the row, and must still record the one delete that is
    # STILL not here: the drive-file delete that removes a Base.
    # Flattened, so a comment re-wrap cannot redden a claim that is still there.
    flat = " ".join(note.replace("#", " ").split())
    assert "Four delete verbs reach this row" in flat
    assert "lose DATA" in flat and "batch_delete" in flat
    assert "explicit consent" in flat, (
        "a row that now covers data-losing deletes has to name what fences them")
    assert "drive-file delete" in flat and "not a shipped op" in flat


def test_the_library_still_REQUESTS_WIDENS_AND_ESCALATES_NOTHING():
    base_pkg = _REPO / "src" / "larkdocio" / "base"
    for name in sorted(p.name for p in base_pkg.rglob("schema*.py")):  # LD-654: recursive
        text = (base_pkg / name).read_text(encoding="utf-8").lower()
        for forbidden in ("request_scope", "grant_scope", "escalate"):
            assert forbidden not in text, (name, forbidden)
