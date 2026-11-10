"""THE L1 GATE for the Base surface — the read-only live Base canary (LD-252).

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live

**What it is.** The Base twin of the docx canary (LD-003) and the Sheets canary (LD-106): it
reads the Scratch Base named by ``LARKDOCIO_SCRATCH_BASE`` **twice in one run** through the
whole shipped L1 path (client → cell registry → table assembly → ``render_base``) and asserts
the two reads are **byte-identical**. It is what turns *"the Base reader passed its unit
tests"* into *"a Base API drift reddens the suite"*. It is **not** the single small read arm —
that is ``tests/test_live_base_read_arm.py`` (LD-247), kept deliberately cheap so the
tranche's live budget belonged to this gate.

**SAME-RUN determinism, never cross-time.** ``04-determinism.json`` proved one SHA-256
across two back-to-back runs because the bitable API's success bodies carry no
``log_id`` nonce — so same-run byte-identity is a real property of the reader. Cross-time
identity is **not** a property of this target: **a human owns this Base.** The maintainer
hand-authors its Lookup / Email / Stage / comment specimens, and the P1 parity pack left
``ok@example.invalid`` behind in an Email cell. This gate therefore **characterizes** what it
finds — tables, fields, row counts, a digest — and depends on **no specimen it did not itself
seed** remaining unchanged. There is no committed expected-output file, on purpose: one would
redden on the maintainer's next hand-edit instead of on a drift.

**Seeds-and-characterizes (AC1, O3's resolution).** ``.env``'s Base was **pristine at grant
time** (revision 1, granted in session 2026-08-03), so "uncharacterized" resolves at **first
run** rather than by decree — the sheets-canary precedent, where the gate pins determinism on
content it seeded. The reading below *is* the seeding: the ``[base-canary]`` line it prints is
the baseline of record.

**READ-ONLY, and provably so.** Every op in :data:`larkdocio.base.ops.OPS` declares
``mutates: False`` — asserted **before** the first call, so a future write op cannot be
smuggled onto this path — and ``table.revision`` is recorded before and after and asserted
unmoved. The Base is maintainer-granted **free-fire**; that is not a licence for this gate to write.
**L1 has nothing to write.**

**Gentle.** Two revision probes plus two full reads, all through the client's own limiter.
Rate limits are not probed.

D3 — WHAT "LIVE" MEANS FOR A BASE (the doctrine the Base write spec inherits)
----------------------------------------------------------------

This gate creates nothing, but it is the **first Base gate**, so D3's ruling is written down
here for the write ladder to inherit rather than re-derive. It agrees with — and must stay in
agreement with — **`BASE.md` § Limitations & revisit-triggers register rows 8, 9 and 10**.

* **Liveness is defined against the bitable API, never against Drive metadata.** An app is
  gone when the bitable API says so: ``1002`` (or ``91402``) for an app, ``1254041`` for a
  table. ``POST /drive/v1/metas/batch_query`` **still resolves a deleted app's title and
  timestamps** — that is **inert residue, not an orphan**, and a sweep that counts it will
  report orphans that do not exist.
* **DELETE is trash, not purge** (register row 9). Deleted apps, **copied apps** and
  **deleted tables** all land in trash — the tables in the Base's own trash — and stay
  resolvable through Drive metadata. So **trash accretes**, and the only remedy is a human
  sweep: every disposable this project creates carries the fixed **``larkdocio-DISPOSABLE-``**
  prefix precisely so that sweep is greppable.
* **Uploaded media accretes too, and with no purge verb at all** (register row 10).
  ``bitable_file`` / ``bitable_image`` file tokens survive their table's deletion and **no
  purge verb** exists for them anywhere in the open API. Unlike trash, this residue cannot
  even be swept.
* **Copy is async** (register row 8) — ASYNC-ONLY, ``1254036`` *"Bitable is copying, please
  try again later"*: the first non-synchronous Base operation found. A write harness that
  copies and then immediately reads is racing the server, and the Base write spec's harness will meet
  this.

**Skips loudly, never silently.** Without ``LARKDOCIO_SCRATCH_BASE`` or read credentials the
whole module skips with a message naming exactly what is missing, so a credential-less
``pytest -q`` stays green without ever reading as a pass.
"""
import hashlib
import re

import canary_support
import pytest

from larkdocio.base import cells as base_cells
from larkdocio.base import ops as base_ops
from larkdocio.base.client import BaseReadClient
from larkdocio.base.read import read_base
from larkdocio.base.table import render_base

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

canary_support.load_env()


# --------------------------------------------------------------------------- #
# Derived detectors — nothing below is hand-listed                            #
# --------------------------------------------------------------------------- #

#: The person-bearing ``(type, ui_type)`` pairs, **derived by renderer identity** rather than
#: typed out, so a new person-bearing pair joins the live PII sweep automatically. D1 is a
#: property of every column whose renderer is the persons renderer, not of four names.
_PERSON_PAIRS = tuple(
    pair for pair in base_cells.PAIRS
    if base_cells.renderer_for(*pair) is base_cells.renderer_for(11, "User")
)

#: A Lark person / chat / department id in any of its prefixed spellings.
_PERSON_ID = re.compile(r"(?:ou_|on_|od-|ug_|oc_)[A-Za-z0-9]{10,}")

#: An avatar or CDN image URL — D1's second forbidden class.
_AVATAR_OR_CDN = re.compile(r"https?://\S*(?:avatar|/cdn|/static/)\S*", re.IGNORECASE)

#: Anything address-shaped, used only INSIDE a person-bearing column (an Email column's own
#: value is field-sourced, not person-sourced, and is legitimate output).
_ADDRESS_SHAPED = re.compile(r"[^\s|]+@[^\s|]+\.[A-Za-z]{2,}")


def _read_base_once(domain, app_token):
    """One independent read + render cycle through the whole shipped L1 path.

    A fresh client per cycle, so the two reads share no cache, no token and no limiter state —
    the same posture the sheets canary takes. Returns
    ``(document, markdown, api_calls)``. Any client failure raises (surfacing as a test
    failure), never a swallowed ``None``. READ-ONLY.
    """
    client = BaseReadClient.from_read_credentials(domain)
    document = read_base(app_token, client=client, domain=domain)
    return document, render_base(document), client.api_calls


def _revisions(client, app_token):
    """``{table_id: revision}`` — the no-write detector.

    The packs proved ``table.revision`` is the one reliable one on a Base: a Stage write
    returns ``code:0`` and leaves the revision alone, while a real Text write moves it.
    """
    return {table.table_id: table.revision for table in client.list_tables(app_token) or ()}


def _first_line_diff(a, b):
    """The first differing line (1-indexed) between two strings, or ``None`` if equal."""
    a_lines, b_lines = a.splitlines(), b.splitlines()
    for i, (x, y) in enumerate(zip(a_lines, b_lines), start=1):
        if x != y:
            return i, x, y
    if len(a_lines) != len(b_lines):
        n = min(len(a_lines), len(b_lines))
        return (
            n + 1,
            a_lines[n] if n < len(a_lines) else "<no line>",
            b_lines[n] if n < len(b_lines) else "<no line>",
        )
    return None


def _determinism_failure_msg(a, b):
    """Assertion message (evaluated ONLY on failure) naming the first divergence."""
    diff = _first_line_diff(a, b)
    if diff is None:
        return "the two Base renders differ but no line-level diff was found"
    line_no, a_line, b_line = diff
    return (
        "the Base reader is non-deterministic: two back-to-back read-only renders of the "
        f"same Base in the SAME RUN differ at line {line_no}: {a_line!r} != {b_line!r}"
    )


def _characterize(document):
    """AC1's record of what was found — the baseline, discovered rather than decreed."""
    return {
        "tables": len(document.tables),
        "fields": sum(len(t.fields) for t in document.tables),
        "rows": sum(len(t.rows) for t in document.tables),
        "time_zone": document.time_zone,
        "opaque_columns": sum(
            1 for t in document.tables for f in t.fields if f.pair in base_cells.OPAQUE_PAIRS
        ),
        "unregistered_columns": sorted(
            {
                (f.type, f.ui_type)
                for t in document.tables
                for f in t.fields
                if f.pair not in base_cells.PAIRS
            }
        ),
    }


# --------------------------------------------------------------------------- #
# AC4 — read-only BEFORE anything is read                                      #
# --------------------------------------------------------------------------- #


def test_the_registry_declares_the_whole_gate_read_only_BEFORE_it_reads_anything():
    assert base_ops.read_only(), (
        "a mutating op reached the registry; this gate runs against the maintainer's real Scratch "
        "Base and must not be the thing that discovers that")


# --------------------------------------------------------------------------- #
# THE GATE                                                                     #
# --------------------------------------------------------------------------- #


def test_the_L1_gate_reads_the_scratch_base_twice_and_is_byte_identical(capsys):
    # Load the repo .env (local runs) — a no-op where creds + URL are already injected. Then
    # skip LOUDLY if we cannot run: never a silent pass (AC5).
    canary_support.load_env()
    reason = canary_support.base_missing_reason()
    if reason:
        pytest.skip(reason)

    domain, app_token = canary_support.parse_base_url(canary_support.scratch_base_url())

    # --- AC4: the no-write detector, armed before the first read. ---
    probe = BaseReadClient.from_read_credentials(domain)
    revisions_before = _revisions(probe, app_token)
    assert revisions_before, "the Base reported no tables — a Base always has at least one"

    # --- Two independent read + render cycles through the shipped L1 path. ---
    document1, md1, calls1 = _read_base_once(domain, app_token)
    document2, md2, calls2 = _read_base_once(domain, app_token)

    # --- AC3: sane output, not merely "no exception". ---
    assert document1.tables, "the read produced no tables"
    assert md1.strip(), "the produced Base Markdown is empty"
    assert "---" in md1, "the produced Base Markdown has no GFM table separator row"
    for table in document1.tables:
        assert table.fields, f"table {table.table_id!r} came back with no fields"
        assert all(spec.field_name for spec in table.fields), (
            f"table {table.table_id!r} has a nameless column — the header must be non-empty")
        assert all(len(row.cells) == table.width for row in table.rows), (
            "a row is not as wide as the field list; rows project against the FIELDS")
        assert all(row.record_id for row in table.rows), "a record came back with no id"

    # (a) No typed-unknown where a known type was expected: every column the live Base
    #     reports resolves to a registered pair — the one exemption being the maintainer's
    #     will-not-support ruling, which is recorded rather than silently tolerated.
    for table in document1.tables:
        for spec in table.fields:
            if spec.pair in base_cells.PAIRS:
                continue
            assert spec.ui_type in base_cells.WILL_NOT_SUPPORT, (
                f"column {spec.field_name!r} is {spec.pair} — an unregistered pair that is "
                "not a will-not-support ruling either. The registry has drifted from the "
                "live field vocabulary.")

    # (b) Markers appear EXACTLY where the registry says they should, and nowhere else.
    #     The Stage column is the deliberate exception (LD-246 AC7c): a real type-24 field
    #     exists on this Base and its absent-with-reason marker is CORRECT output. The
    #     assertion is therefore a biconditional, not "no markers".
    licensed_cells = 0
    for table in document1.tables:
        for index, spec in enumerate(table.fields):
            licensed = spec.pair in base_cells.OPAQUE_PAIRS
            for row in table.rows:
                cell = row.cells[index]
                if licensed:
                    licensed_cells += 1
                    assert cell == base_cells.STAGE_OPAQUE_MARKER, (
                        f"column {spec.field_name!r} is {spec.pair}, which the registry says "
                        f"renders the absent-with-reason marker; it rendered {cell!r}")
                else:
                    assert base_cells.STAGE_OPAQUE_MARKER not in cell, (
                        f"the Stage marker leaked into column {spec.field_name!r} "
                        f"({spec.pair}), which is not an opaque pair")
    assert (base_cells.STAGE_OPAQUE_MARKER in md1) == (licensed_cells > 0), (
        "the rendered Markdown and the structured read disagree about the marker: "
        f"{licensed_cells} licensed cells, marker in output "
        f"{base_cells.STAGE_OPAQUE_MARKER in md1}")

    # (c) D1's invariant, live: zero person ids, zero avatar/CDN URLs anywhere, and zero
    #     person-sourced address strings — checked per COLUMN, because an Email column's own
    #     value is field-sourced and is legitimate output.
    assert not _PERSON_ID.findall(md1), (
        f"a person/chat id reached the Markdown: {sorted(set(_PERSON_ID.findall(md1)))[:3]}")
    assert not _AVATAR_OR_CDN.findall(md1), (
        f"an avatar/CDN URL reached the Markdown: "
        f"{sorted(set(_AVATAR_OR_CDN.findall(md1)))[:3]}")
    assert "avatar" not in md1.lower(), "the string 'avatar' reached the Markdown"
    for table in document1.tables:
        for index, spec in enumerate(table.fields):
            if spec.pair not in _PERSON_PAIRS:
                continue
            for row in table.rows:
                cell = row.cells[index]
                assert not _ADDRESS_SHAPED.search(cell), (
                    f"person-bearing column {spec.field_name!r} rendered an address: {cell!r} "
                    "— D1 is name-only")
                assert "http" not in cell, (
                    f"person-bearing column {spec.field_name!r} rendered a URL: {cell!r}")

    # --- AC2: THE GATE. Same-run byte-identity. On a deviation the offending line is named
    #     (the message is evaluated only when the assertion fails). ---
    assert md1 == md2, _determinism_failure_msg(md1, md2)
    assert _characterize(document1) == _characterize(document2), (
        "the two reads agree byte-for-byte on the Markdown but not on the structured read — "
        "which would mean the renderer is hiding a difference")

    # --- AC4: nothing moved. ---
    revisions_after = _revisions(probe, app_token)
    assert revisions_after == revisions_before, (
        f"table.revision moved {revisions_before} -> {revisions_after}; THE L1 GATE is "
        "READ-ONLY and L1 has nothing to write")

    # --- Gentle: the two cycles cost the same, and the whole gate stays inside a bound that
    #     scales with the Base rather than with a hard-coded census. ---
    assert calls1 == calls2, (
        f"the two read cycles spent different call counts ({calls1} vs {calls2}) — the read "
        "path is not doing the same work twice")
    total = probe.api_calls + calls1 + calls2
    budget = 8 + 8 * len(document1.tables)
    assert total <= budget, f"the gate spent {total} live calls; its budget is {budget}"

    # --- AC1: the characterization IS the baseline. Visible under `pytest -m live -s`. ---
    found = _characterize(document1)
    digest = hashlib.sha256(md1.encode("utf-8")).hexdigest()
    with capsys.disabled():
        print(
            f"\n[base-canary] tables={found['tables']} "
            f"fields={found['fields']} "
            f"rows={found['rows']} "
            f"time_zone={found['time_zone']!r} "
            f"opaque_columns={found['opaque_columns']} "
            f"unregistered_columns={found['unregistered_columns']} "
            f"md_bytes={len(md1.encode('utf-8'))} "
            f"md_lines={md1.count(chr(10)) + 1} "
            f"sha256={digest} "
            f"deterministic={md1 == md2} "
            f"live_calls={total} "
            f"revision_unmoved={revisions_after == revisions_before}"
        )
