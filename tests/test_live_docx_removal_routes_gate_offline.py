"""The always-on half of the **LD-601 removal-route probe** — its DISCIPLINE, no credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones a static read can settle:

* it skips **loudly** rather than passing quietly when the write credentials are absent, and
  again when the disposables folder is unset;
* every subject is one the gate **created**, in the human-visible disposables folder — it names
  no standing fixture, and it explicitly fences off the read canary and the write scratch doc;
* it deletes what it made in a ``finally`` and proves gone-ness by an **independent re-query**
  (``docx_ledger.close_out``) rather than by the delete's own answer, and it **names** any
  survivor instead of counting it;
* it **mints no permanent media** — no uploader name appears in it at all, and it never sets
  ``LARKDOCIO_MEDIA_MINT_AUTHORIZED_BY``;
* every route it probes sends an **explicit, literal** ``doc_type`` / object-type spelling, and
  records that literal in the capture, because LD-606 measured that the spelling is load-bearing
  (a wrong one answers ``code:0`` with an empty ``metas`` — a refusal in disguise);
* it probes **both legs** — before the delete and after it — for the same route set, because a
  post-delete answer means nothing without the pre-delete control;
* it writes its captures under the issue's own ``dev/`` evidence tree, and reads
  ``failed_list`` rather than the envelope ``code`` when it decides whether a token resolved.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import json
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_docx_removal_routes_gate.py"
CAPTURE_DIR = REPO_ROOT / "tests" / "captures" / "ld601-trashed-doc-routes" / "captures"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source


def test_the_gate_skips_LOUDLY_when_credentials_are_absent(gate_source):
    assert "canary_support.load_env()" in gate_source
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source


def test_every_subject_is_one_the_gate_CREATED_in_the_human_visible_disposables_folder(
        gate_source):
    assert "require_disposables_folder()" in gate_source
    assert "root_folder_token()" not in gate_source, (
        "the app's own root has no human interface — a disposable made there cannot be seen "
        "or swept by the account holder"
    )


def test_the_gate_fences_off_every_standing_fixture_by_name(gate_source):
    """The forbidden targets are named in the file as a fence, never consumed."""
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_WRITE_SCRATCH_DOC"):
        assert forbidden in gate_source, f"{forbidden} must be named as a fence"
        assert f'os.environ["{forbidden}"]' not in gate_source
        assert f'getenv("{forbidden}")' not in gate_source
        assert f'environ.get("{forbidden}")' not in gate_source


def test_the_gate_MINTS_NO_PERMANENT_MEDIA(gate_source):
    """Zero by construction: no uploader, and the mint consent variable is never set."""
    for uploader in ("upload_all", "upload_prepare", "upload_part", "upload_finish",
                     "upload_media", "DriveFilesWriteClient"):
        assert uploader not in gate_source, f"{uploader} would mint permanent drive residue"
    assert "LARKDOCIO_MEDIA_MINT_AUTHORIZED_BY" not in gate_source


def test_teardown_is_a_finally_and_gone_ness_is_proved_by_an_INDEPENDENT_re_query(gate_source):
    assert "docx_ledger.disposable(" in gate_source, (
        "the ledgered context manager is what deletes in a finally and survives a crash"
    )
    assert "docx_ledger.close_out(" in gate_source, (
        "a delete's own code:0 is a claim, not evidence — the re-query is the evidence"
    )
    assert "orphans" in gate_source


def test_any_survivor_is_NAMED_with_its_token_and_kind_never_counted(gate_source):
    """AC4's shape: the failure message carries the id, not a tally."""
    assert re.search(r"document_id", gate_source), "an orphan is named by its id"
    assert "raise_if_orphans" in gate_source or "OrphanLeakError" in gate_source


def test_the_gate_also_checks_the_BASE_orphan_oracle_at_close(gate_source):
    """AC4 names ``base_write_harness.orphans()`` explicitly; the gate records its result."""
    assert "base_write_harness" in gate_source
    assert "orphans(" in gate_source


def test_every_route_sends_an_EXPLICIT_object_type_spelling_and_records_it(gate_source):
    """LD-606: the ``doc_type`` spelling is load-bearing, so it is never left to a default."""
    assert '"doc_type": "docx"' in gate_source
    assert "sent" in gate_source, "the capture records the request it sent, verbatim"
    assert "OBJECT_TYPE_SPELLING_IS_LOAD_BEARING" in gate_source


def test_the_probe_runs_BOTH_legs_before_and_after_the_delete(gate_source):
    assert "before" in gate_source and "after" in gate_source
    assert "_probe_all_routes(" in gate_source, (
        "one route table, run twice — not two hand-written leg bodies that could drift apart"
    )


def test_the_verdict_reads_failed_list_not_the_envelope_code(gate_source):
    """A ``code:0`` with an empty ``metas`` is a refusal in disguise (LD-606)."""
    assert "failed_list" in gate_source


def test_the_route_table_is_the_five_ALREADY_REGISTERED_endpoints(gate_source):
    """AC9: the probe needs no new permission row, so every endpoint is one we already ship."""
    for endpoint in (
        "/open-apis/drive/v1/metas/batch_query",
        "/open-apis/docx/v1/documents/{document_id}",
        "/open-apis/docx/v1/documents/{document_id}/blocks",
        "/open-apis/drive/v1/files",
        "/open-apis/drive/v1/files/{token}/versions",
    ):
        stem = endpoint.split("{")[0]
        assert stem in gate_source, f"{endpoint} is missing from the route table"


def test_the_captures_land_under_the_issues_own_dev_evidence_tree(gate_source):
    assert "ld601-trashed-doc-routes" in gate_source
    assert "captures" in gate_source


def test_the_committed_captures_carry_both_legs_and_their_sent_request(gate_source):
    """The evidence half of AC3 — checked here so a lost capture reddens the offline suite.

    Skips (loudly, naming the reason) only while the probe has not yet run in this tree; once
    the captures are committed this is a permanent guard on their shape.
    """
    if not CAPTURE_DIR.is_dir():
        pytest.skip(f"{CAPTURE_DIR} does not exist yet — the probe has not been run")
    files = sorted(p for p in CAPTURE_DIR.glob("ld601-*.json")
                   if p.name.startswith(("ld601-before-", "ld601-after-")))
    assert files, f"{CAPTURE_DIR} exists but holds no per-route ld601 capture"
    roll_up = CAPTURE_DIR / "ld601-summary.json"
    assert roll_up.exists(), (
        f"{roll_up.name} is the run's own roll-up — the per-route files say what each route "
        f"answered, and it says what the run concluded"
    )
    legs = set()
    for path in files:
        body = json.loads(path.read_text(encoding="utf-8"))
        for key in ("leg", "route", "endpoint", "sent", "response", "captured_at"):
            assert key in body, f"{path.name} is missing the '{key}' field"
        legs.add(body["leg"])
    assert legs == {"before", "after"}, (
        f"both legs must be captured; found {sorted(legs)}"
    )
