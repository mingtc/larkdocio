"""Live read-canary (LD-003) — ``@pytest.mark.live``, deselected by default.

Runs only under ``pytest -m live`` (needs real read creds + network). It drives
the reader through its **real client + parser** — the same modules the CLI uses,
so this exercises the actual package API — against the disposable scratch doc
named by ``LARKDOCIO_CANARY_DOC``. It deliberately does NOT go through
``handle_download_command``: that entry point swallows every exception (logging
+ returning ``None``) and rewrites image tokens to local links after download,
which is a poor fit for clean pass/fail + raw image-token assertions.

The canary reads the doc **twice** (two independent client+parse cycles, each
written to its own temp dir) and asserts the reader still:
  (a) succeeds — a client failure surfaces as a test failure, not a swallowed None;
  (b) returns sane, nonzero output (block count + markdown lines);
  (c) is **byte-identical across the two runs** (reader determinism — the
      invariant the golden-master strategy rests on);
  (d) drops no image-link token (every token the parser recorded is present in
      the produced, pre-substitution markdown; vacuously true when there are none).

READ-ONLY — the canary never writes to Lark.
"""
import os

import pytest

import canary_support
from larkdocio.auth import get_read_credentials
from larkdocio.read.client import Client
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.sheets import SheetsReadClient, render_spreadsheet
from larkdocio.utils.url import validate_download_url

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]


def _read_once(url, app_id, app_secret):
    """One independent client+parse cycle against the scratch doc.

    Returns ``(blocks, markdown, img_tokens)``. Any client failure raises
    (surfacing as a test failure), never a swallowed ``None``.
    """
    domain, doc_type, token = validate_download_url(url)
    client = Client(app_id, app_secret, domain)

    if doc_type == "wiki":
        node = client.get_wiki_node_info(token)
        doc_type, token = node.obj_type, node.obj_token

    docx, blocks = client.get_docx_content(token)

    parser = Parser(new_config())
    markdown = parser.parse_docx_content(docx.document_id, blocks)

    # The parser's markdown is PRE image-substitution, so raw image tokens are
    # still present in it; img_tokens is what the parser recorded while walking.
    return blocks, markdown, list(parser.img_tokens)


def test_reader_canary_scratch_doc(tmp_path, capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds + URL are
    # injected as CI variables. Then skip loudly if we cannot run.
    canary_support.load_env()
    reason = canary_support.missing_reason()
    if reason:
        pytest.skip(reason)

    url = canary_support.canary_doc_url()
    app_id, app_secret = get_read_credentials()

    # --- Two independent download+parse cycles, each into its own temp dir. ---
    run1_dir = tmp_path / "run1"
    run2_dir = tmp_path / "run2"
    run1_dir.mkdir()
    run2_dir.mkdir()

    blocks1, md1, img1 = _read_once(url, app_id, app_secret)
    blocks2, md2, img2 = _read_once(url, app_id, app_secret)

    md1_path = run1_dir / "canary.md"
    md2_path = run2_dir / "canary.md"
    md1_path.write_text(md1, encoding="utf-8")
    md2_path.write_text(md2, encoding="utf-8")

    # (a) Download + parse succeeded (no exception raised above).
    # (b) Nonzero + sane output. Generous lower bound — avoid brittle exact
    #     counts (this doc is ~659 blocks).
    assert len(blocks1) >= 50, (
        f"expected a substantial doc; got only {len(blocks1)} blocks"
    )
    assert md1.strip(), "produced markdown is empty"
    md1_line_count = md1.count("\n") + 1
    assert md1_line_count > 0, "produced markdown has no lines"

    # (c) Determinism: the two runs must be byte-identical. Compare what was
    #     actually written to the two temp dirs (read back), which equals the
    #     in-memory strings.
    md1_readback = md1_path.read_text(encoding="utf-8")
    md2_readback = md2_path.read_text(encoding="utf-8")
    assert md1_readback == md2_readback, (
        "reader is non-deterministic: two downloads of the unchanged doc differ"
    )

    # (d) No image-link token silently dropped: every token the parser recorded
    #     appears in the produced (pre-substitution) markdown. Vacuously true
    #     when the doc has no images.
    assert all(tok in md1 for tok in img1), (
        "an image token the parser recorded is missing from the produced markdown"
    )

    # Evidence for the QA/Activity log (visible under `pytest -m live -s`).
    with capsys.disabled():
        print(
            f"\n[canary] blocks={len(blocks1)} "
            f"md_bytes={len(md1.encode('utf-8'))} "
            f"md_lines={md1_line_count} "
            f"img_tokens={len(img1)} "
            f"deterministic={md1 == md2}"
        )


# ===========================================================================
# LD-106 — THE L1 GATE: the live SHEETS canary (the Sheets read spec § F1-S6). Read-only,
# byte-identical determinism against LARKDOCIO_SCRATCH_SHEET, rendered through
# the full L1 path (S1 client → S2 trim → S3 render → S4 assemble). It lives in
# THIS file so one `pytest -m live` run exercises BOTH the docx canary above and
# this sheets canary. READ-ONLY — it never writes to Lark.
# ===========================================================================


def _render_sheet_once(domain, spreadsheet_token):
    """One independent query + used-range-read + render cycle through the L1 path.

    Rides S1 (:class:`SheetsReadClient`) → S2 (used-range trim) → S3 (cell render)
    → S4 (table assembly): one tab-query, then one bounded used-range read per tab,
    then :func:`render_spreadsheet` → the full standalone Markdown (every tab as a
    titled GFM table). Returns ``(tabs, markdown)``. Any client failure raises
    (surfacing as a test failure), never a swallowed ``None``. READ-ONLY.
    """
    client = SheetsReadClient.from_read_credentials(domain=domain)
    tabs = client.query_sheets(spreadsheet_token)
    pairs = [(tab, client.read_used_range(spreadsheet_token, tab)) for tab in tabs]
    markdown = render_spreadsheet(pairs)
    return tabs, markdown


def _first_line_diff(a, b):
    """The first differing line (1-indexed) between two strings, or ``None`` if
    equal — surfaces the offending field on a determinism failure (AC2)."""
    a_lines, b_lines = a.splitlines(), b.splitlines()
    for i, (x, y) in enumerate(zip(a_lines, b_lines), start=1):
        if x != y:
            return i, x, y
    if len(a_lines) != len(b_lines):
        n = min(len(a_lines), len(b_lines))
        extra_a = a_lines[n] if n < len(a_lines) else "<no line>"
        extra_b = b_lines[n] if n < len(b_lines) else "<no line>"
        return n + 1, extra_a, extra_b
    return None


def _determinism_failure_msg(a, b):
    """Assertion message (evaluated ONLY on failure) naming the first divergence."""
    diff = _first_line_diff(a, b)
    if diff is None:
        return "sheets render differs but no line-level diff was found"
    line_no, a_line, b_line = diff
    return (
        "sheets reader is non-deterministic: two back-to-back read-only renders of "
        f"the unchanged scratch sheet differ at line {line_no}: "
        f"{a_line!r} != {b_line!r}"
    )


def test_sheets_reader_canary_scratch_sheet(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds + URL are injected
    # as CI variables. Then skip LOUDLY if we cannot run (never a silent pass).
    canary_support.load_env()
    reason = canary_support.sheets_missing_reason()
    if reason:
        pytest.skip(reason)

    domain, spreadsheet_token = canary_support.parse_sheet_url(
        canary_support.scratch_sheet_url()
    )

    # --- Two independent query+read+render cycles through the L1 path. ---
    tabs1, md1 = _render_sheet_once(domain, spreadsheet_token)
    tabs2, md2 = _render_sheet_once(domain, spreadsheet_token)

    # (a) The reads + render succeeded (no exception raised above).
    # (b) Sane, nonzero output: at least one tab and a real GFM table separator.
    assert len(tabs1) >= 1, "expected at least one tab in the scratch sheet"
    assert md1.strip(), "produced sheet Markdown is empty"
    assert "---" in md1, "produced sheet Markdown has no GFM table separator row"

    # (c) Determinism — THE L1 gate: the two back-to-back renders of the unchanged
    #     sheet must be byte-identical. On a deviation the offending field/line is
    #     surfaced (the message is evaluated only when the assertion fails).
    assert md1 == md2, _determinism_failure_msg(md1, md2)

    # Evidence for the QA/Activity log (visible under `pytest -m live -s`).
    md1_line_count = md1.count("\n") + 1
    with capsys.disabled():
        print(
            f"\n[sheets-canary] tabs={len(tabs1)} "
            f"md_bytes={len(md1.encode('utf-8'))} "
            f"md_lines={md1_line_count} "
            f"deterministic={md1 == md2}"
        )


# --------------------------------------------------------------------------- #
# LD-465 — THE HANDOFF, PROVED IN A FRESH PROCESS.                             #
#                                                                              #
# The claim `snapshot()`/`load()` makes is that a read survives a process       #
# death and a handoff. A same-process assertion cannot show that: the domain,   #
# the URL and the parsed tree are all still in memory. So this gate writes the  #
# artefact, then spawns a **bare** interpreter — cwd outside the repo, an       #
# environment holding the credentials and nothing else (no canary URL, no       #
# .env in reach) — and has it complete the successor's step from the file       #
# alone: load, validate a URL rebuilt from the artefact, and read the document. #
# READ-ONLY, like the rest of this file.                                        #
# --------------------------------------------------------------------------- #

#: What the successor runs. Deliberately imports only what a consumer would, takes every
#: routing fact off the artefact, and prints one line of JSON for the parent to assert on.
_SUCCESSOR = r"""
import json, os, sys
from larkdocio.common import get_read_credentials, validate_download_url
from larkdocio.read.client import Client
from larkdocio.snapshot import load

leaked = [k for k in os.environ if k.startswith("LARKDOCIO_")]
snap = load(sys.argv[1])
url = "https://%s/docx/%s" % (snap.api_domain, snap.document_token)
domain, url_type, token = validate_download_url(url)
docx, blocks = Client(*get_read_credentials(), domain).get_docx_content(token)
print(json.dumps({
    "leaked_env": leaked,
    "api_domain": snap.api_domain,
    "validated": [domain, url_type, token],
    "snapshot_blocks": len(snap.blocks),
    "read_blocks": len(blocks),
    "revision_in_file": snap.document_revision_id,
    "revision_now": docx.revision_id,
}))
"""


def test_snapshot_handoff_survives_a_process_boundary(tmp_path, capsys):
    """LD-465 AC5: the successor completes the read with **only** the artefact and creds."""
    import json
    import subprocess
    import sys

    from larkdocio.snapshot import load, snapshot

    canary_support.load_env()
    reason = canary_support.missing_reason()
    if reason:
        pytest.skip(reason)

    url = canary_support.canary_doc_url()
    app_id, app_secret = get_read_credentials()
    domain, doc_type, token = validate_download_url(url)

    client = Client(app_id, app_secret, domain)
    if doc_type == "wiki":
        node = client.get_wiki_node_info(token)
        doc_type, token = node.obj_type, node.obj_token
    docx, blocks = client.get_docx_content(token)

    artefact = tmp_path / "document.snapshot"
    snapshot(blocks, document_token=token, document_revision_id=docx.revision_id,
             api_domain=domain, path=artefact)
    assert load(artefact).api_domain == domain

    # The successor's world: credentials, and nothing else. No canary URL, no PWD in the
    # repo, no .env within reach — so a domain it did not read off the file cannot exist.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "LARK_READ_APP_ID": app_id,
        "LARK_READ_APP_SECRET": app_secret,
    }
    proc = subprocess.run([sys.executable, "-c", _SUCCESSOR, str(artefact)],
                          cwd=str(tmp_path), env=env, capture_output=True, text=True,
                          timeout=180)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    assert result["leaked_env"] == [], (
        f"the successor could see {result['leaked_env']} — its read is then not proof that "
        "the artefact carried the routing facts")
    assert result["api_domain"] == domain
    assert result["validated"] == [domain, "docx", token], result["validated"]
    assert result["read_blocks"] >= 50, result["read_blocks"]

    with capsys.disabled():
        print(f"\n[snapshot-handoff] api_domain={result['api_domain']} "
              f"validated={result['validated'][:2]} "
              f"snapshot_blocks={result['snapshot_blocks']} "
              f"successor_read_blocks={result['read_blocks']} "
              f"revision_in_file={result['revision_in_file']} "
              f"revision_now={result['revision_now']} "
              f"artefact_bytes={artefact.stat().st_size}")
