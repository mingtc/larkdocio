"""The always-on offline half of ``test_live_base_media_gate`` (LD-268).

A live pass proves the round trip happened. It cannot prove the things that make the arm
**safe to have run** — that ``parent_node`` can only ever be a Base the run created, that no
signed link survives anywhere, that the residue is ledgered because nothing can sweep it, and
that this leg did not become a **third** definition of *"download a Lark media token"*. Those
are structural, so they are pinned here, where they run on every ``pytest -q``.
"""
import ast
import re
from pathlib import Path

import pytest

import base_write_harness
from larkdocio.base import media

_TESTS = Path(__file__).resolve().parent
_REPO = _TESTS.parent
GATE = _TESTS / "test_live_base_media_gate.py"
HARNESS = _TESTS / "base_write_harness.py"
MODULE = _REPO / "src/larkdocio/base/media.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def harness_source():
    return HARNESS.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The arms are present BY NAME.                                                #
# --------------------------------------------------------------------------- #

_REQUIRED_ARMS = (
    "test_both_parent_types_round_trip_and_the_HASH_IS_IDENTICAL",
    "test_the_AMPLIFIER_case_a_NON_ASCII_FILE_NAME_round_trips_by_hash",
    "test_the_EMPTY_FILE_probe_records_what_the_SERVER_answered",
    "test_the_uploaded_tokens_feed_the_SHIPPED_ENCODER_and_TWO_ride_in_one_cell",
    "test_the_read_back_carries_the_SIGNED_LINKS_and_NOTHING_HERE_KEEPS_THEM",
    "test_every_minted_token_is_LEDGERED_as_permanent_residue",
    "test_no_parent_node_is_a_CONFIGURED_BASE",
)


def test_every_arm_the_gate_claims_is_actually_defined(gate_source):
    defined = {node.name for node in ast.walk(ast.parse(gate_source))
               if isinstance(node, ast.FunctionDef)}
    assert set(_REQUIRED_ARMS) <= defined, set(_REQUIRED_ARMS) - defined


def test_the_gate_covers_BOTH_parent_types_and_BOTH_amplifier_cases():
    """A live run that quietly dropped one ``parent_type`` — or stopped asking the empty-file
    question once the answer turned out to be a refusal — would still pass. The payload table
    is the pin."""
    from test_live_base_media_gate import EMPTY_PAYLOAD, PAYLOADS

    assert {p[2] for p in PAYLOADS.values()} == set(media.MEDIA_PARENT_TYPES)
    assert any(not p[1].isascii() for p in PAYLOADS.values()), "the non-ASCII NAME case"
    assert EMPTY_PAYLOAD[0] == b"", "the zero-byte probe is required, refusal or not"
    assert b"" not in {p[0] for p in PAYLOADS.values()}, (
        "the empty file is a REFUSAL probe, not a round-trip case — keeping it in the "
        "round-trip table would make the arm fail rather than record what the server said")


def test_the_gate_asserts_the_empty_upload_refusal_against_the_SHIPPED_constant(gate_source):
    """The finding is the server's, so the number lives with the shipped leg and the gate
    references it — two spellings of a captured code drift apart."""
    assert "EMPTY_UPLOAD_REFUSED_CODE" in gate_source
    assert media.EMPTY_UPLOAD_REFUSED_CODE == 1061002


def test_the_gate_is_marked_live_write_and_SKIPS_LOUDLY(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source
    assert "base_write_harness.missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source


def test_the_gate_LOADS_ENV_AT_IMPORT_so_its_own_per_file_command_works(gate_source):
    """LD-276: every sibling live gate calls ``canary_support.load_env()`` at module import,
    so the file's own documented per-file command (``pytest -m live_write
    tests/test_live_base_media_gate.py``) resolves write creds on a configured machine without
    depending on a sibling module's import-time side effect to have populated ``os.environ``
    first. Pinned here, where the offline companion already greps the gate's source."""
    assert "canary_support.load_env()" in gate_source


# --------------------------------------------------------------------------- #
# parent_node — the parameter no deletion takes back (AC6).                    #
# --------------------------------------------------------------------------- #

class _NoTransport:
    def __getattr__(self, name):
        raise AssertionError(f"the allow-list must refuse BEFORE any call; touched {name!r}")


def test_an_upload_onto_a_base_the_harness_did_not_create_is_refused_STRUCTURALLY():
    """The allow-list is what makes the Scratch Base untouchable **without naming it**, and it
    has to cover ``parent_node`` — which is not a write target — or an upload could attach
    permanent residue to a Base a delete would then fail to un-attach it from."""
    provisioner = base_write_harness._Provisioner(sdk=_NoTransport(),
                                                  rate_limiter=_CountingLimiter())
    with pytest.raises(base_write_harness.NonDisposableTargetError):
        provisioner.upload_media("someone-elses-app-token", data=b"x", name="x",
                                 parent_type="bitable_file")


class _CountingLimiter:
    def __init__(self):
        self.acquired = 0

    def acquire(self):
        self.acquired += 1


def test_the_gate_and_the_harness_NAME_NO_CONFIGURED_TARGET(gate_source, harness_source):
    """The static half of the two-parameter assertion: neither file reads an environment
    variable naming a Base, so neither a write target nor a ``parent_node`` can come from
    configuration. The gate's own env read is a *refusal* check, which is why it is asserted
    as a comparison rather than as an assignment."""
    for source, label in ((harness_source, "the harness"), (gate_source, "the gate")):
        for forbidden in ("LARKDOCIO_SCRATCH_BASE", "LARKDOCIO_CANARY"):
            if forbidden == "LARKDOCIO_SCRATCH_BASE" and label == "the gate":
                continue
            assert forbidden not in source, f"{label} names {forbidden}"
    assert "os.environ" not in harness_source.replace("os.getpid", ""), (
        "the harness reads no environment variable naming a target")
    assert "assert parent_node not in configured" in gate_source, (
        "the gate must ASSERT the configured token is never a parent_node")


def test_the_harness_media_leg_ledgers_BEFORE_it_can_be_forgotten(harness_source):
    """``attach_media`` is the one route that mints residue, so the ledger write lives beside
    the call rather than in each caller."""
    tree = ast.parse(harness_source)
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "attach_media"][0]
    calls = {ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert "ledger.record_media" in calls
    assert "provisioner.upload_media" in calls


def test_there_is_NO_MEDIA_DELETE_LEG_and_there_cannot_be_one(harness_source):
    """The honest response to un-purgeable residue is a ledger and a sentence, never a verb
    that pretends. A ``record_media_delete`` would be a claim no endpoint backs."""
    defined = {node.name for node in ast.walk(ast.parse(harness_source))
               if isinstance(node, ast.FunctionDef)}
    assert not {"record_media_delete", "delete_media", "purge_media"} & defined
    ledger = base_write_harness.Ledger(path=_TESTS / "__nonexistent_ledger__.json")
    ledger._entries = [{"kind": "media", "file_token": "boxcn1",
                        "parent_type": "bitable_file", "app_token": "appX"}]
    assert ledger.survivors() == [], "a media token is never a sweep candidate"
    assert ledger.entries == [], "the base half never sees a media entry"
    assert [e["file_token"] for e in ledger.media()] == ["boxcn1"]


def test_a_legacy_ledger_entry_with_no_kind_is_still_a_BASE_entry():
    """The extension must not orphan what the harness already wrote: an entry from before the
    media half existed is a base entry, which is what it was."""
    ledger = base_write_harness.Ledger(path=_TESTS / "__nonexistent_ledger__.json")
    ledger._entries = [{"app_token": "appOLD", "title": "larkdocio-DISPOSABLE-1",
                        "deleted": False, "last_code": 1061003}]
    assert [e["app_token"] for e in ledger.survivors()] == ["appOLD"]


# --------------------------------------------------------------------------- #
# url / tmp_url — credential-class, structurally (AC4).                        #
# --------------------------------------------------------------------------- #

def test_every_cell_the_gate_touches_goes_through_the_SCRUBBER(gate_source):
    assert "scrub_attachment_cell(item)" in gate_source
    assert gate_source.count("fields[FIELD_NAME]") == 2, (
        "the raw cell is read exactly twice — once to scrub, once to prove the keys are "
        "there; a third raw read is a leak waiting to happen")


def test_the_capture_the_gate_writes_carries_NO_LINK_AND_NO_BYTES(gate_source):
    assert '"_residue"' in gate_source
    assert "read_back_scrubbed" in gate_source
    for leaky in ("payload,", '"payload":', "downloaded_bytes"):
        assert f'"{leaky}"' not in gate_source
    assert "sha256" in gate_source


def test_the_scrubber_drops_exactly_the_two_signed_link_keys():
    cell = {"file_token": "t", "name": "n", "size": 1, "type": "x",
            "url": "<not-committed>", "tmp_url": "<not-committed>"}
    assert set(media.scrub_attachment_cell(cell)) == {"file_token", "name", "size", "type"}


_LINK_LITERAL = re.compile(r'"(?:tmp_)?url"\s*:\s*"\s*http')


def test_neither_the_gate_nor_the_module_carries_a_LINK_LITERAL(gate_source):
    for path, source in ((GATE, gate_source), (MODULE, MODULE.read_text(encoding="utf-8"))):
        assert not _LINK_LITERAL.search(source), path


# --------------------------------------------------------------------------- #
# The substrate call — ONE definition of "download a Lark media token".        #
# --------------------------------------------------------------------------- #

def test_the_media_leg_rides_the_SAME_SDK_REQUEST_CLASS_as_the_docx_image_leg():
    """The within-story call, pinned rather than merely written down: the reader's docx image
    leg and this one build the **same** pinned-SDK request class, so a third independent
    definition of the download cannot appear without this reddening."""
    from lark_oapi.api.drive.v1 import DownloadMediaRequest

    reader = (_REPO / "src/larkdocio/read/client.py").read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")
    assert "DownloadMediaRequest" in reader and "DownloadMediaRequest" in module
    assert DownloadMediaRequest.builder().build().uri == media.DOWNLOAD_ENDPOINT


def test_the_module_records_WHY_it_did_not_open_a_raw_http_media_leg():
    doc = media.__doc__
    assert "transport" in doc, "the substrate that was NOT used is named"
    assert "download_image" in doc, "the existing definition is named"


def test_the_endpoints_the_registry_joins_on_are_the_SDKS_OWN():
    from lark_oapi.api.drive.v1 import UploadAllMediaRequest

    assert UploadAllMediaRequest.builder().build().uri == media.UPLOAD_ENDPOINT


# --------------------------------------------------------------------------- #
# The residue disclosure (AC5).                                                #
# --------------------------------------------------------------------------- #

def test_the_gate_docstring_says_MEDIA_ACCRETES_AND_CANNOT_BE_SWEPT(gate_source):
    header = ast.get_docstring(ast.parse(gate_source)).lower()
    assert "no open-api verb purges drive media" in header
    assert "row 10" in header
    assert "there is no cleanup leg here" in header


def test_the_gate_states_the_ORPHAN_CLAIM_against_the_bitable_definition(gate_source):
    header = ast.get_docstring(ast.parse(gate_source)).lower()
    assert "bitable" in header and "orphans() == []" in header
    assert "outside it" in header, (
        "media residue must be named as explicitly outside the orphan claim")


def test_the_gate_reports_residue_and_orphans_SEPARATELY(gate_source):
    assert "media_residue()" in gate_source and "orphans()" in gate_source


# --------------------------------------------------------------------------- #
# Classification.                                                              #
# --------------------------------------------------------------------------- #

def test_this_gate_is_classified_in_the_gate_registry():
    import gate_registry

    row = gate_registry.REGISTRY[GATE.name]
    assert row.kind is gate_registry.Kind.HAS_COMPANION
    assert row.companion == Path(__file__).name
    assert gate_registry.REGISTRY[Path(__file__).name].subject == GATE.name
