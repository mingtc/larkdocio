"""The always-on offline half of ``test_live_base_relational_gate`` (LD-272).

A live pass proves the four arms ran. It cannot prove the things that make the gate **safe to
have run**, nor the things that make its claims mean what they say — that neither a write target
nor a ``parent_node`` can come from configuration, that exactly **one** file is uploaded because
every upload is permanent, that the byte-identity arm really compares two off-reads against an
on-read rather than an on-read against itself, that the detector's zero-call claim is *measured*
rather than asserted, and that the table-delete arm **points at** the loss preview's warning
instead of restating it. All of that is structural, so it is pinned here, where it runs on every
``pytest -q``.
"""
import ast
import re
from pathlib import Path

import pytest

import base_write_harness
import gate_registry
from larkdocio.base import loss_preview, referential

_TESTS = Path(__file__).resolve().parent
_REPO = _TESTS.parent
GATE = _TESTS / "test_live_base_relational_gate.py"
HARNESS = _TESTS / "base_write_harness.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_doc(gate_source):
    return ast.get_docstring(ast.parse(gate_source))


# --------------------------------------------------------------------------- #
# The four arms are present BY NAME.                                           #
# --------------------------------------------------------------------------- #

_REQUIRED_ARMS = (
    "test_the_attachment_round_trips_and_the_SHA256_IS_IDENTICAL",
    "test_the_minted_token_is_LEDGERED_as_permanent_residue",
    "test_the_SINGLE_LINK_still_points_at_the_DELETED_record",
    "test_the_DUPLEX_LINK_SELF_HEALED",
    "test_the_read_COMPLETED_and_1254043_NEVER_RAISED",
    "test_after_the_TARGET_TABLE_is_deleted_the_column_reads_as_DANGLING",
    "test_the_detector_made_ZERO_EXTRA_CALLS_and_the_search_still_answers",
    "test_resolution_OFF_is_BYTE_IDENTICAL_and_ON_differs_ONLY_in_the_link_cells",
    "test_NEITHER_a_write_target_NOR_a_parent_node_is_EVER_the_configured_base",
)


def test_every_arm_the_gate_claims_is_actually_defined(gate_source):
    defined = {node.name for node in ast.walk(ast.parse(gate_source))
               if isinstance(node, ast.FunctionDef)}
    assert set(_REQUIRED_ARMS) <= defined, sorted(set(_REQUIRED_ARMS) - defined)


def test_the_gate_is_marked_live_write_and_SKIPS_LOUDLY(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source
    assert "base_write_harness.missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source


# --------------------------------------------------------------------------- #
# The two-parameter fence (AC6).                                               #
# --------------------------------------------------------------------------- #

class _NoTransport:
    def __getattr__(self, name):
        raise AssertionError(f"the allow-list must refuse BEFORE any call; touched {name!r}")


class _CountingLimiter:
    def __init__(self):
        self.acquired = 0

    def acquire(self):
        self.acquired += 1


def test_a_parent_node_the_harness_did_not_create_is_refused_STRUCTURALLY():
    """``parent_node`` is the parameter no deletion takes back, so the refusal is proven against
    a transport that raises on contact: zero calls is structural rather than counted."""
    limiter = _CountingLimiter()
    provisioner = base_write_harness._Provisioner(sdk=_NoTransport(), rate_limiter=limiter)
    with pytest.raises(base_write_harness.NonDisposableTargetError):
        provisioner.upload_media("someone-elses-app-token", data=b"x", name="x",
                                 parent_type="bitable_file")
    assert limiter.acquired == 0, "the refusal must happen before the limiter, let alone the SDK"


def test_a_write_target_the_harness_did_not_create_is_refused_the_SAME_WAY():
    """The other parameter, refused by the same allow-list — one mechanism, two parameters,
    which is what makes the pair impossible to drift apart."""
    provisioner = base_write_harness._Provisioner(sdk=_NoTransport(),
                                                  rate_limiter=_CountingLimiter())
    with pytest.raises(base_write_harness.NonDisposableTargetError):
        provisioner.delete("someone-elses-app-token")


def test_the_gate_NAMES_NO_CONFIGURED_TARGET_except_to_refuse_it(gate_source):
    """The static half: the gate reads the environment in exactly one place and only to
    **compare** against it. Nothing in it assigns a configured token to a target."""
    assert "LARKDOCIO_CANARY" not in gate_source
    assert gate_source.count("LARKDOCIO_SCRATCH") == 1, (
        "the configured prefix appears more than once; the only legitimate use is the refusal "
        "check")
    assert "assert token not in configured" in gate_source
    assert "os.environ" in gate_source
    # The refusal covers BOTH parameters in one loop, which is what the AC asks for.
    assert 'targets["write_targets"]' in gate_source
    assert 'targets["parent_nodes"]' in gate_source


def test_the_gate_distinguishes_READING_the_configured_base_from_WRITING_it(gate_doc):
    """The distinction matters: a sibling arm legitimately READS the configured Base for a
    specimen the API cannot recreate. A gate that blurred the two would either forbid something
    legitimate or permit something it must not."""
    assert "Reading that Base is legitimate" in gate_doc
    assert "writing it is not" in gate_doc.lower()


# --------------------------------------------------------------------------- #
# The residue purchase (AC2).                                                  #
# --------------------------------------------------------------------------- #

def test_the_gate_uploads_EXACTLY_ONE_FILE(gate_source):
    """Every upload is permanent, unsweepable tenant residue. The claim needs one file; a
    second would be residue bought for nothing, and a payload *table* here would invite one."""
    from test_live_base_relational_gate import PAYLOAD

    assert isinstance(PAYLOAD, tuple) and len(PAYLOAD) == 3
    assert gate_source.count("attach_media(") == 1, (
        "more than one upload call; each mints residue nothing can reclaim")
    assert PAYLOAD[0], "a zero-byte upload is refused by Lark — that probe belongs to its own arm"


def test_the_gate_docstring_says_the_residue_CANNOT_BE_SWEPT(gate_doc):
    lower = gate_doc.lower()
    assert "no open-api verb purges drive media" in lower
    assert "row 10" in lower
    assert "no cleanup leg" in lower
    assert "orphans() == []" in lower and "outside" in lower


def test_there_is_still_NO_MEDIA_DELETE_LEG_anywhere(gate_source):
    """Checked over **defined names**, not over text: the harness's own docstring says the words
    ``record_media_delete`` precisely to record that no such function exists, and a text sweep
    would punish the disclosure it is supposed to protect."""
    harness = HARNESS.read_text(encoding="utf-8")
    for source in (gate_source, harness):
        defined = {node.name for node in ast.walk(ast.parse(source))
                   if isinstance(node, ast.FunctionDef)}
        assert not {"record_media_delete", "delete_media", "purge_media"} & defined


_LINK_LITERAL = re.compile(r'"(?:tmp_)?url"\s*:\s*"?\s*http')


def test_the_gate_verifies_the_round_trip_by_HASH_and_never_by_a_status_code(gate_source):
    """The digests are compared and the signed links are not carried. The gate does *name*
    ``tmp_url`` — in the assertion that proves its own capture has none — so the check is for a
    link **literal**, which is the thing that would actually leak."""
    assert "verify_round_trip" in gate_source and "sha256_of" in gate_source
    assert "downloaded_sha256" in gate_source and "uploaded_sha256" in gate_source
    assert not _LINK_LITERAL.search(gate_source)
    assert 'assert "tmp_url" not in blob' in gate_source, (
        "the gate must prove its own committed capture carries no signed link")


# --------------------------------------------------------------------------- #
# The byte-identity arm (AC5).                                                 #
# --------------------------------------------------------------------------- #

def test_the_byte_identity_arm_reads_OFF_TWICE_and_ON_ONCE(gate_source):
    """An arm that compared one off-read against itself would prove determinism and nothing
    about the flag; one that compared on against on would prove nothing at all."""
    assert gate_source.count("read_base(app_token, client=read)") == 2
    assert "resolve_links=True" in gate_source
    assert "off_first == off_second" in gate_source


def test_the_comparison_is_CELL_LEVEL_rather_than_a_substring_check(gate_source):
    """*"Differs only in the resolved cells"* is a claim about columns, so the comparison walks
    cells and names the differing column. A whole-document ``in`` check could not tell a
    resolved link from a neighbouring cell that moved."""
    assert "_cell_differences" in gate_source
    assert "differing_columns" in gate_source
    tree = ast.parse(gate_source)
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "_cell_differences"][0]
    assert "heading" in ast.unparse(fn), "the comparison must be per table, not per file"


# --------------------------------------------------------------------------- #
# The detector arm (AC4) — measured, and POINTING at the warning.              #
# --------------------------------------------------------------------------- #

def test_the_zero_call_claim_is_MEASURED_at_the_client_boundary(gate_source):
    """*"Zero extra calls"* is only evidence if something counted. The arm brackets the detector
    with the client's own call counter, which is the same seam the resolver's cost disclosure is
    checked against."""
    assert "before_calls = read.api_calls" in gate_source
    assert "read.api_calls - before_calls" in gate_source
    assert 'arm["detector_extra_calls"] == 0' in gate_source


def _reachable_by_import(start: str):
    """``(every shipped module reachable from ``start`` by an in-package import, everything the
    whole closure imports from outside the package)`` — both as sets, read off the syntax trees.
    """
    src = _REPO / "src"

    def resolve(dotted, aliases):
        direct = src / (dotted.replace(".", "/") + ".py")
        if direct.exists():
            return [direct.relative_to(src).as_posix()]
        found = [src / dotted.replace(".", "/") / f"{alias}.py" for alias in aliases]
        found = [path for path in found if path.exists()]
        package = src / dotted.replace(".", "/") / "__init__.py"
        if not found and package.exists():
            found = [package]
        return [path.relative_to(src).as_posix() for path in found]

    reached, outside, queue = set(), set(), [start]
    while queue:
        rel = queue.pop()
        if rel in reached:
            continue
        reached.add(rel)
        for node in ast.walk(ast.parse((src / rel).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                pairs = [(node.module or "", [alias.name for alias in node.names])]
            elif isinstance(node, ast.Import):
                pairs = [(alias.name, []) for alias in node.names]
            else:
                continue
            for dotted, aliases in pairs:
                if dotted.startswith("larkdocio"):
                    queue += resolve(dotted, aliases)
                else:
                    outside.add(dotted.split(".")[0])
    return reached, outside


def test_the_detector_the_arm_calls_is_the_SHIPPED_FREE_ONE():
    """The reading is derived from a schema the read already holds — no client, no transport, no
    credential — and the shipped modules' own syntax trees are what say so.

    Until LD-312 this was checked as *"``referential.py`` imports nothing from the package"*,
    which was a proxy: it happened to hold, and it said nothing at all about what the module
    imports from **outside** the package — where an SDK, an HTTP client and ``os.environ`` all
    live. LD-312 made the by-name property walk one shared primitive (``base/_typed.py``), so the
    proxy stopped being sayable and the claim is now checked where it lives: every in-package
    import is **followed transitively**, and the entire closure may import nothing but the two
    standard-library names below. No ``lark_oapi``, no transport, nothing that can read a
    credential — proven for the closure rather than for one file.
    """
    reached, outside = _reachable_by_import("larkdocio/base/referential.py")

    assert reached == {"larkdocio/base/referential.py", "larkdocio/base/_typed.py"}, reached
    assert outside == {"dataclasses", "typing"}, outside
    assert referential.TARGET_TABLE_MISSING in referential.TARGET_TABLE_STATES


def test_the_arm_POINTS_AT_the_loss_preview_and_does_NOT_RESTATE_it(gate_source):
    """One rule, one owner. ``loss_preview`` warns about this aftermath **before** the act; the
    arm names that warning and must not carry a second copy of its words, because two statements
    of one contract drift and the drift is silent."""
    assert "loss_preview" in gate_source
    assert "INBOUND_LINK_DANGLES_SILENTLY" in gate_source
    for chunk in [p.strip() for p in re.split(r"[.;]\s+", loss_preview.INBOUND_LINK_DANGLES_SILENTLY)
                  if len(p.strip()) >= 40]:
        assert chunk not in gate_source, f"the arm restates the owner's prose: {chunk[:60]!r}"


# --------------------------------------------------------------------------- #
# The credential rider (AC7).                                                  #
# --------------------------------------------------------------------------- #

def test_the_gate_docstring_carries_the_CREDENTIAL_ALIASING_RIDER(gate_doc):
    """A gate that quietly dropped the rider would invite exactly the over-read it exists to
    prevent: on this tenant the pairs alias one app, so a green run says nothing about the read
    path lacking write scope."""
    lower = gate_doc.lower()
    assert "alias" in lower
    assert "byte-identical secrets" in lower
    assert "nothing whatever about the read path" in lower


def test_the_gate_uses_the_WRITE_pair_for_writes_and_the_READ_pair_for_reads(gate_source):
    assert "BaseWriteClient.from_write_credentials()" in gate_source
    assert "BaseSchemaClient.from_write_credentials()" in gate_source
    assert "BaseReadClient.from_read_credentials()" in gate_source


# --------------------------------------------------------------------------- #
# Classification (AC9).                                                        #
# --------------------------------------------------------------------------- #

def test_this_gate_is_classified_in_the_gate_registry():
    row = gate_registry.REGISTRY[GATE.name]
    assert row.kind is gate_registry.Kind.HAS_COMPANION
    assert row.companion == Path(__file__).name
    assert gate_registry.REGISTRY[Path(__file__).name].subject == GATE.name
