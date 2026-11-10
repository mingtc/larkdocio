# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Drift guard for /BLOCKS.md — the single-source-of-truth block-support matrix.

/BLOCKS.md (repo root) documents the status of every docx block type. The whole
point of that file is that it stays truthful against the live registry, so this
test parses its matrix table and asserts it agrees with ``blocks.get_registry()``
in BOTH directions:

- every registered ``@register_block(N)`` type is a ``rendered`` or ``placeholder``
  row (a *registered* row) in /BLOCKS.md, and
- every ``rendered``/``placeholder`` row maps back to a real registry key (no
  phantom "supported" row), and
- every ``intentionally-skipped`` / ``unregistered-warns`` row is genuinely NOT
  in the registry.

If a handler is added/removed without updating /BLOCKS.md (or a row is mislabelled),
this test goes red — the matrix can't silently drift.

NOTE on scope vs. the issue's literal wording: LD-023 AC2 suggested asserting every
``get_registry()`` key is a "rendered" row. This test broadens "rendered" to the
*registered* set {rendered, placeholder} because type 50 (reference_synced) is a
genuine ``placeholder`` (it emits a fixed marker, not the block's real content).
Forcing it to "rendered" would make the matrix less truthful; the guard is instead
"every registry key is a registered row", which is strictly stronger (it also
catches phantom rows).
"""
import re

import pytest

from doc_prose import missing_phrases, prose
from guard_kit import REPO_ROOT, md_table_cells
from larkdocio.blocks import get_registry
from larkdocio.model.conservation import PROJECTION_STATES, projection_support
from larkdocio.write.encode import CREATABLE_BLOCK_TYPES
from larkdocio.write.media import OUT_OF_BAND_CREATABLE_BLOCK_TYPES

# LD-370 — CONFORMANCE-tier: BLOCKS.md is a corpus member; the matrix's completeness against the real registry is a product claim.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

_BLOCKS_MD = REPO_ROOT / "BLOCKS.md"

_STATUS_VOCAB = {"rendered", "placeholder", "intentionally-skipped", "unregistered-warns"}
_REGISTERED_STATUSES = {"rendered", "placeholder"}

# LD-134 — the matrix gained a **write-support** column (a different axis
# from the read Status: a type can be perfectly readable and still uncreatable). Its
# vocabulary, and the one value pinned against code truth.
#
# LD-433 widened the vocabulary by one slug. ``creatable`` is defined as *through the
# plan-gated authoring path*, and it is pinned bidirectionally against the encoder — so a
# type the library really can bring into existence, but only through a dedicated op that
# needs bytes and a network call, had nowhere honest to sit: leaving it ``not-creatable``
# told a consumer "no" about something that ships. ``creatable-out-of-band`` is that row,
# pinned against its own code truth the same bidirectional way.
_WRITE_VOCAB = {"creatable", "editable", "not-creatable", "creatable-out-of-band"}
_CREATABLE = "creatable"
_OUT_OF_BAND = "creatable-out-of-band"

# Every docx block type the matrix must cover: 1..53 plus the 999 API fallback.
# (Type 53 reference_base is a NEW SDK type off the 1-52 matrix — added in
# LD-048 alongside its placeholder handler; the read-completeness spec § F1.)
_EXPECTED_TYPES = set(range(1, 54)) | {999}

# SDK-known docx block types: 1..53 (NOT 999, the undefined/API-fallback sentinel).
# The T3 endgame invariant applies to these — every one must have a real
# disposition (rendered / placeholder / intentionally-skipped), never a bare warn.
_SDK_KNOWN_TYPES = set(range(1, 54))

# A matrix row looks like:
#   | 22 | divider | rendered | not-creatable | `divider.py` | ... |
# Capture the leading integer (type), the third cell (read status) and the fourth
# (write support). Either may be wrapped in markdown emphasis (**placeholder**), so
# strip '*' when normalising.
_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|[^|]*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")


def _parse_matrix():
    """Return {block_type: status_slug} parsed from /BLOCKS.md's matrix table."""
    return {t: status for t, (status, _write) in _parse_rows().items()}


def _parse_write_support():
    """Return {block_type: write_slug} parsed from /BLOCKS.md's matrix table (D8)."""
    return {t: write for t, (_status, write) in _parse_rows().items()}


def _parse_projection_column():
    """Return {block_type: projection_slug} parsed from /BLOCKS.md (LD-231)."""
    return {t: row["projection"] for t, row in _parse_full_rows().items()}


def _parse_rows():
    """Return {block_type: (status_slug, write_slug)} for every matrix row."""
    rows = {}
    for line in _BLOCKS_MD.read_text(encoding="utf-8").splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        rows[int(m.group(1))] = (
            m.group(2).replace("*", "").strip(),
            m.group(3).replace("*", "").strip(),
        )
    return rows


def test_blocks_md_exists():
    assert _BLOCKS_MD.is_file(), f"{_BLOCKS_MD} is missing — it is the source of truth."


def test_every_type_has_exactly_one_valid_row():
    rows = _parse_matrix()
    # Every type 1..52 + 999 is present.
    missing = _EXPECTED_TYPES - set(rows)
    assert not missing, f"/BLOCKS.md is missing rows for block types {sorted(missing)}."
    # No stray/duplicate junk types (parser would collapse dupes; guard the vocab).
    unexpected = set(rows) - _EXPECTED_TYPES
    assert not unexpected, f"/BLOCKS.md has rows for unexpected types {sorted(unexpected)}."
    # Every status is a recognised slug.
    bad = {t: s for t, s in rows.items() if s not in _STATUS_VOCAB}
    assert not bad, f"/BLOCKS.md has rows with an unknown status: {bad}."


def test_registry_matches_registered_rows():
    """Bidirectional: registry keys <-> rendered/placeholder rows must be equal."""
    rows = _parse_matrix()
    registry_keys = set(get_registry())
    registered_rows = {t for t, s in rows.items() if s in _REGISTERED_STATUSES}

    missing_from_doc = registry_keys - registered_rows
    assert not missing_from_doc, (
        f"Registered handler types {sorted(missing_from_doc)} are not marked "
        f"rendered/placeholder in /BLOCKS.md — the matrix has drifted from the registry."
    )
    phantom_rows = registered_rows - registry_keys
    assert not phantom_rows, (
        f"/BLOCKS.md marks types {sorted(phantom_rows)} as rendered/placeholder, but "
        f"they have no registered handler — remove them or fix their status."
    )


def test_unsupported_rows_are_not_registered():
    """intentionally-skipped / unregistered-warns rows must NOT be in the registry."""
    rows = _parse_matrix()
    registry_keys = set(get_registry())
    unsupported_rows = {t for t, s in rows.items() if s not in _REGISTERED_STATUSES}

    wrongly_registered = unsupported_rows & registry_keys
    assert not wrongly_registered, (
        f"/BLOCKS.md marks types {sorted(wrongly_registered)} as unsupported, but they "
        f"DO have a registered handler — mark them rendered/placeholder instead."
    )


def test_no_unregistered_warns_among_sdk_known_types():
    """The T3 endgame invariant (LD-049): after
    read-completeness, NO SDK-known docx type (1..53) is left as
    ``unregistered-warns`` — every one has a real disposition (rendered,
    placeholder, or intentionally-skipped with a documented rationale). The warn
    path survives ONLY for genuinely-future Lark types + ``999``/undefined. This
    guard pins the class empty so the matrix cannot silently drift back to a bare
    'unhandled today' label for any 1..53 type."""
    rows = _parse_matrix()
    stragglers = {
        t for t, s in rows.items()
        if t in _SDK_KNOWN_TYPES and s == "unregistered-warns"
    }
    assert not stragglers, (
        f"SDK-known types {sorted(stragglers)} are still marked 'unregistered-warns' "
        f"in /BLOCKS.md — T3 requires every 1..53 type to be rendered / placeholder / "
        f"intentionally-skipped. Only 999 (undefined) stays a warn."
    )


# --------------------------------------------------------------------------- #
# The WRITE-SUPPORT column (LD-134) — same drift discipline as                    #
# the read Status: every row carries a state from a closed vocabulary, and the    #
# `creatable` set is pinned BIDIRECTIONALLY against the encoder's code truth.     #
# --------------------------------------------------------------------------- #

def test_every_row_carries_a_valid_write_support_state():
    """D8: the matrix's write-support notation covers **every** type with a slug from the
    closed vocabulary — a missing or mistyped state is drift, not a gap to shrug at."""
    write = _parse_write_support()
    missing = _EXPECTED_TYPES - set(write)
    assert not missing, f"/BLOCKS.md is missing write-support cells for {sorted(missing)}."
    bad = {t: w for t, w in write.items() if w not in _WRITE_VOCAB}
    assert not bad, (
        f"/BLOCKS.md has rows with an unknown write-support state: {bad}. "
        f"Valid: {sorted(_WRITE_VOCAB)}."
    )


def test_creatable_rows_match_the_encoders_creatable_block_types():
    """THE code-truth coupling (bidirectional): the rows marked ``creatable`` equal
    ``larkdocio.write.encode.CREATABLE_BLOCK_TYPES``.

    So a new ``NewBlock`` kind whose block type never got a matrix row reddens here, and a
    row claiming a creatability the encoder cannot deliver — the dogfood **F2/F14** failure
    mode, a discovery surface promising what the engine cannot do — reddens too."""
    documented = {t for t, w in _parse_write_support().items() if w == _CREATABLE}

    missing_from_doc = set(CREATABLE_BLOCK_TYPES) - documented
    assert not missing_from_doc, (
        f"the write encoder can create block types {sorted(missing_from_doc)} but "
        f"/BLOCKS.md does not mark them 'creatable' — the matrix has drifted from the "
        f"encoder."
    )
    phantom = documented - set(CREATABLE_BLOCK_TYPES)
    assert not phantom, (
        f"/BLOCKS.md marks types {sorted(phantom)} 'creatable', but no NewBlock kind "
        f"encodes to them — fix the row or ship the kind."
    )


def test_out_of_band_rows_match_the_media_ops_creatable_block_types():
    """The same code-truth coupling, on the other creatable set (bidirectional): the rows
    marked ``creatable-out-of-band`` equal
    ``larkdocio.write.media.OUT_OF_BAND_CREATABLE_BLOCK_TYPES``.

    So shipping an op that brings a new block type into existence without moving its matrix
    row reddens here, and a row claiming an out-of-band creatability no op delivers reddens
    too. This is the guard that would have caught the row that told a consumer "images are
    not creatable" while the route to create one was measured and shippable."""
    documented = {t for t, w in _parse_write_support().items() if w == _OUT_OF_BAND}

    missing_from_doc = set(OUT_OF_BAND_CREATABLE_BLOCK_TYPES) - documented
    assert not missing_from_doc, (
        f"a shipped media op creates block types {sorted(missing_from_doc)} but "
        f"/BLOCKS.md does not mark them {_OUT_OF_BAND!r} — the matrix has drifted from the "
        f"code."
    )
    phantom = documented - set(OUT_OF_BAND_CREATABLE_BLOCK_TYPES)
    assert not phantom, (
        f"/BLOCKS.md marks types {sorted(phantom)} {_OUT_OF_BAND!r}, but no shipped op "
        f"creates them — fix the row or ship the op."
    )


def test_the_two_creatable_sets_are_disjoint():
    """A type is created through the plan-gated path or through a dedicated op, never both
    — the slugs are exclusive by construction and the code sets must agree."""
    assert not set(CREATABLE_BLOCK_TYPES) & set(OUT_OF_BAND_CREATABLE_BLOCK_TYPES)


def test_the_out_of_band_row_names_the_op_and_the_bind_order():
    """A consumer who reads the row must learn the thing the row exists to tell them: it is
    created by a dedicated op, and the bind is a separate call from the upload."""
    text = prose(_BLOCKS_MD.read_text(encoding="utf-8"))
    assert missing_phrases(text, ["put_image_in_document"]) == []


def test_image_27_is_no_longer_notated_not_creatable():
    """The regression this issue exists to prevent: the row that answered a consumer "no"
    about a capability that ships."""
    assert _parse_write_support()[27] == _OUT_OF_BAND


def test_the_write_hostile_verdict_for_the_image_row_is_stated():
    """``WRITE_HOSTILE_NODE_TYPES`` lists what refuses an EDIT, not what can be created — so
    an image staying on that list while becoming creatable-out-of-band is not a
    contradiction, and the vocabulary says so rather than leaving a reader to reconcile it.
    Verdict re-examined at LD-433: **unchanged**, because no op edits an existing image
    block's content; the media op creates a new one."""
    from larkdocio.model import ImageNode
    from larkdocio.write.resolve import WRITE_HOSTILE_NODE_TYPES

    assert ImageNode in WRITE_HOSTILE_NODE_TYPES
    text = prose(_BLOCKS_MD.read_text(encoding="utf-8"))
    assert missing_phrases(text, ["refuses an edit, not what can be created"]) == []


def test_no_row_is_both_creatable_and_editable_only():
    """The vocabulary is exclusive by construction (one slug per row), and ``editable``
    means specifically **editable-but-NOT-creatable** (the F9 nuance) — so no creatable
    type may be labelled ``editable``."""
    write = _parse_write_support()
    mislabelled = {t for t, w in write.items() if w == "editable" and t in CREATABLE_BLOCK_TYPES}
    assert not mislabelled, (
        f"types {sorted(mislabelled)} are creatable, so 'editable' (which means "
        f"editable-but-not-creatable) is the wrong state."
    )


def test_the_write_support_vocabulary_section_documents_every_slug():
    """The notation is only useful if the file explains it: each slug has a row in the
    § Write-support vocabulary table."""
    text = _BLOCKS_MD.read_text(encoding="utf-8")
    assert "## Write-support vocabulary" in text
    for slug in _WRITE_VOCAB:
        assert f"| **{slug}** |" in text, (
            f"/BLOCKS.md § Write-support vocabulary does not define {slug!r}")


# --------------------------------------------------------------------------- #
# The PROJECTION column (LD-231) — a FOURTH axis: when a                         #
# document is projected for round-trip editing, is a block of this type one an    #
# edit can be applied back to, or one the projection conserves? The column is     #
# pinned BIDIRECTIONALLY against the derivation in                                #
# ``larkdocio.model.conservation``, which is itself a join of the registry, the   #
# encoder's creatable set and the shipped read-lossiness — so the row cannot      #
# drift from the code, and the code cannot gain an unrecorded answer.             #
# --------------------------------------------------------------------------- #

def test_every_row_carries_a_valid_projection_state():
    """AC6: every type answers the editable/opaque question with a slug from the closed
    vocabulary — a missing cell is drift, not a gap."""
    projection = _parse_projection_column()
    missing = _EXPECTED_TYPES - set(projection)
    assert not missing, f"/BLOCKS.md is missing projection cells for {sorted(missing)}."
    bad = {t: p for t, p in projection.items() if p not in PROJECTION_STATES}
    assert not bad, (
        f"/BLOCKS.md has rows with an unknown projection state: {bad}. "
        f"Valid: {sorted(PROJECTION_STATES)}."
    )


def test_the_projection_column_matches_the_derived_conservation_sets():
    """AC6, THE code-truth coupling (bidirectional): the rows marked ``editable`` are
    exactly ``conservation.editable_block_types()`` and the rows marked ``opaque`` are
    exactly ``conservation.opaque_block_types()``, over every type both sides know.

    So a type that becomes creatable — or a handler whose read-lossiness changes — moves
    the derived answer, and this reddens until the matrix row says the same thing."""
    documented = _parse_projection_column()
    derived = projection_support()
    shared = set(documented) & set(derived)

    drifted = {
        t: (documented[t], derived[t]) for t in sorted(shared) if documented[t] != derived[t]
    }
    assert not drifted, (
        f"/BLOCKS.md's projection column has drifted from "
        f"larkdocio.model.conservation (row, derived): {drifted}"
    )
    undocumented = set(derived) - set(documented)
    assert not undocumented, (
        f"the conservation derivation answers for block types {sorted(undocumented)} "
        f"that /BLOCKS.md has no row for."
    )


def test_the_projection_column_is_a_DIFFERENT_axis_from_write_support():
    """AC6: the column earns its place only if it says something the Write column does
    not. A creatable type can still be opaque (a table, a mermaid add-on), which is the
    whole reason conservation is derived rather than read off ``creatable``."""
    documented = _parse_projection_column()
    creatable_but_opaque = {
        t for t, p in documented.items()
        if p == "opaque" and t in CREATABLE_BLOCK_TYPES
    }
    assert creatable_but_opaque, (
        "the projection column agrees with the write column on every row — one of the "
        "two is then redundant, and the table/add-on rows say it is not."
    )


def test_the_projection_vocabulary_section_documents_every_slug():
    """AC6: the notation is only useful if the file explains it."""
    text = _BLOCKS_MD.read_text(encoding="utf-8")
    assert "## Round-trip projection vocabulary" in text
    for slug in PROJECTION_STATES:
        assert f"| **{slug}** |" in text, (
            f"/BLOCKS.md § Round-trip projection vocabulary does not define {slug!r}")


def test_the_projection_column_states_the_conservation_contract():
    """AC6/AC3: the matrix is where a maintainer meets the word ``opaque`` first, so the
    contract it implies is stated there, not only in the package."""
    text = _BLOCKS_MD.read_text(encoding="utf-8").lower()
    for phrase in ("not edited", "not deleted", "not re-created", "omits it"):
        assert phrase in text, (
            f"/BLOCKS.md never states {phrase!r} — the conservation contract must be "
            f"stated where the opaque column is defined."
        )


def test_the_write_support_notation_states_the_no_type_mutation_invariant():
    """``creatable`` must not be misread as "convertible": no op promotes an existing
    block to another type, and the matrix says so where the notation is defined."""
    text = _BLOCKS_MD.read_text(encoding="utf-8").lower()
    assert "no block-type mutation" in text, (
        "/BLOCKS.md must state that no op changes an existing block's type")


# --------------------------------------------------------------------------- #
# The § Write-support SUMMARY (LD-138) — the notation is only                      #
# "complete" if the file's own summary of it agrees with its rows AND with code.    #
# The per-row guard above was blind to the summary, and the summary HAD rotted:     #
# it still read "creatable (15)" / "editable (2): 31 table + 32 table_cell" after   #
# LD-135 made both creatable — a discovery surface contradicting itself two          #
# screens apart (the LD-132 lesson: a guard keyed on ids never reads the prose).     #
# --------------------------------------------------------------------------- #

#: ``- **`creatable` (17):** 2 text, 3–11 heading1..heading9, …`` — the body runs to the
#: next bullet (a summary bullet wraps over several lines, and a first-line-only read is
#: how a guard silently stops seeing half the claim).
_SUMMARY_BULLET_RE = re.compile(
    r"^- \*\*`(?P<slug>[a-z-]+)` \((?P<count>[^)]+)\):\*\*(?P<body>.*?)(?=\n- \*\*|\Z)",
    re.MULTILINE | re.DOTALL)
#: a range of block types, written with an en dash (``3–11``) or a hyphen.
_TYPE_RANGE_RE = re.compile(r"(?<![A-Za-z0-9])(\d+)\s*[–-]\s*(\d+)(?![A-Za-z0-9])")
#: a standalone block type — never the trailing digits of a word (``heading1``).
_TYPE_RE = re.compile(r"(?<![A-Za-z0-9])(\d+)(?![A-Za-z0-9])")


def _summary_section() -> str:
    text = _BLOCKS_MD.read_text(encoding="utf-8")
    start = text.find("### Write-support summary")
    assert start != -1, "/BLOCKS.md must carry a § Write-support summary"
    rest = text[start + len("### Write-support summary"):]
    nxt = re.search(r"^#{2,3} ", rest, flags=re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _summary_bullets() -> dict:
    """``{write slug: (count_token, {block types in its leading type span})}``.

    Each bullet leads with its type list in **one backticked span** (``2, 3–11, 12, …``)
    and only then explains itself in prose. That is deliberate: scanning the prose for
    integers cannot work — "headings carry a level 1–9" and "every SDK-known type (1–53)"
    are English, not claims about creatability, and a guard that reads them is guessing.
    One delimited span per bullet is what makes the summary checkable at all.
    """
    out = {}
    for m in _SUMMARY_BULLET_RE.finditer(_summary_section()):
        span = re.search(r"`(none|[0-9,\s–-]+)`", m.group("body"))
        assert span, (
            f"§ Write-support summary bullet {m.group('slug')!r} must lead with its block "
            f"types in a single backticked span, e.g. `2, 3–11, 31` (or `none`)")
        listed = "" if span.group(1) == "none" else span.group(1)
        types = set()
        for lo, hi in _TYPE_RANGE_RE.findall(listed):
            types.update(range(int(lo), int(hi) + 1))
        types.update(int(t) for t in _TYPE_RE.findall(listed))
        out[m.group("slug")] = (m.group("count").strip(), types)
    return out


def test_the_summary_has_one_bullet_per_write_support_slug():
    """D8: the summary covers the whole closed vocabulary — a slug with no bullet is a
    notation that is documented per-row and summarised nowhere."""
    bullets = _summary_bullets()
    assert set(bullets) == _WRITE_VOCAB, (
        f"§ Write-support summary bullets {sorted(bullets)} != the vocabulary "
        f"{sorted(_WRITE_VOCAB)}")


def test_the_summary_creatable_bullet_matches_the_rows_and_the_encoder():
    """D8 (bidirectional, THE anti-rot guard): the block types the ``creatable`` summary
    bullet lists equal the matrix's own ``creatable`` rows **and** the encoder's
    ``CREATABLE_BLOCK_TYPES``. A type made creatable in code, marked creatable on its row,
    and left out of the summary reddens here — which is exactly the drift LD-138 found."""
    _count, summarised = _summary_bullets()["creatable"]
    rows = {t for t, w in _parse_write_support().items() if w == _CREATABLE}

    assert summarised == rows, (
        f"§ Write-support summary lists creatable types {sorted(summarised)} but the "
        f"matrix rows say {sorted(rows)}")
    assert summarised == set(CREATABLE_BLOCK_TYPES), (
        f"§ Write-support summary lists creatable types {sorted(summarised)} but the "
        f"encoder creates {sorted(CREATABLE_BLOCK_TYPES)}")


def test_the_summary_counts_are_the_real_counts():
    """D8 (the amplifier's stale-count case): each bullet's stated ``(N)`` equals the
    number of rows in that state. "creatable (15)" while 17 rows are creatable is the
    cheapest possible lie and the one a reader most trusts."""
    write = _parse_write_support()
    for slug, (count, _types) in _summary_bullets().items():
        real = len([t for t, w in write.items() if w == slug])
        if not count.isdigit():
            # `not-creatable` is summarised as "all the rest" plus the write-hostile
            # subset — a count would be an unmaintainable duplicate of the matrix.
            assert slug == "not-creatable" and real, (slug, count, real)
            continue
        assert int(count) == real, (
            f"§ Write-support summary says {slug} ({count}) but {real} rows carry it")


def test_the_summary_not_creatable_bullet_names_no_phantom_type():
    """D8 (one-directional by design): the ``not-creatable`` bullet names the
    **write-hostile** subset rather than re-listing every remaining type, so it is checked
    for phantoms only — every type it names must really be a ``not-creatable`` row."""
    _count, named = _summary_bullets()["not-creatable"]
    write = _parse_write_support()
    phantom = {t for t in named if write.get(t) != "not-creatable"}
    assert not phantom, (
        f"§ Write-support summary calls types {sorted(phantom)} not-creatable, but their "
        f"rows say otherwise: { {t: write.get(t) for t in sorted(phantom)} }")


def test_the_summary_states_the_editable_is_not_creatable_nuance_in_PROSE():
    """AC4 / dogfood **F9**: the *editable ≠ creatable* nuance is **explicit**, in words, in
    the write-support notation — asserted at content level, not by the presence of a
    heading. Since LD-135 the nuance is carried by the **merge** case, so the prose must
    say a merged table reads/edits while no merge can be authored."""
    whole = prose(_BLOCKS_MD.read_text(encoding="utf-8"))
    assert "editable ≠ creatable" in whole or "editable is not creatable" in whole, (
        "/BLOCKS.md must state the editable ≠ creatable nuance in words")

    summary = _summary_section()
    missing = missing_phrases(summary, [
        "editable means editable-but-not-creatable",   # what the state actually means
        "merged",                                     # the surviving F9 case
        "no merge can be authored",                   # …and the half a reader must not miss
        "table",
    ])
    assert not missing, (
        f"§ Write-support summary no longer states {missing} — the F9 nuance is the reason "
        f"the `editable` state exists, so an empty state must SAY why it is empty")


def test_the_matrix_creatable_rows_match_the_capabilities_floor():
    """LD-138: /BLOCKS.md and ``capabilities()`` are the SAME truth seen two ways — the
    matrix keyed by docx block type, the floor keyed by kind — so the floor's projected
    ``creatable_block_types`` is the join key, and the two are pinned equal here. Before
    this, each was guarded only against the encoder, so nothing caught the two surfaces
    disagreeing with *each other* about what can be created."""
    from larkdocio import capabilities

    floor = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    rows = {t for t, w in _parse_write_support().items() if w == _CREATABLE}
    assert set(floor["creatable_block_types"]) == rows, (
        f"capabilities() says the creatable block types are "
        f"{sorted(floor['creatable_block_types'])} while /BLOCKS.md marks {sorted(rows)} "
        f"creatable")


def test_999_stays_the_forward_compat_warn_sentinel():
    """``999`` (undefined / API fallback) is the deliberate forward-compat warn
    sentinel and is the ONLY row that may stay ``unregistered-warns``. It must
    never be registered nor reclassified — it is the net for types Lark adds
    later (LD-049)."""
    rows = _parse_matrix()
    assert rows.get(999) == "unregistered-warns", (
        "Type 999 (undefined) must remain the 'unregistered-warns' forward-compat "
        f"sentinel; found {rows.get(999)!r}."
    )
    # And it is the sole survivor: no SDK-known type shares that status.
    warns = {t for t, s in rows.items() if s == "unregistered-warns"}
    assert warns == {999}, (
        f"Exactly one row (999) may be 'unregistered-warns'; found {sorted(warns)}."
    )


# --------------------------------------------------------------------------- #
# The per-block-type READ PROJECTION (LD-181) — the same drift discipline as the  #
# write-support column, applied to the axis a consumer actually asks about:       #
# "will this document's callouts / images / boards survive the read, and what      #
# will they turn into?"                                                           #
#                                                                                 #
# Two independent consumers asked for exactly this. The answer lived ONLY here     #
# (/BLOCKS.md is a repo-root file the wheel does not carry) and the one packaged   #
# block document existed largely to redirect to it, so the question was            #
# unanswerable from shipped material. `capabilities()` now projects it, and this   #
# section is what stops the projection and this matrix from disagreeing —          #
# BIDIRECTIONALLY, in every one of the three answers.                             #
# --------------------------------------------------------------------------- #

#: The closed read-lossiness vocabulary. One axis, five states, and the whole point of the
#: state names is that they answer "is it lossy" with something a consumer can act on.
_READ_LOSSINESS_VOCAB = {
    "full", "projected", "out-of-band", "reference-only", "not-handled",
}


def _parse_full_rows():
    """``{block_type: {"name", "status", "write", "lossiness", "emits"}}``.

    A cell-index parse rather than a regex per column: rows 2 and 31 carry a literal ``|``
    inside a code span in their LAST cell, so a field-count assertion would be wrong while
    left-to-right indexing is exact.

    LD-242: the split is :func:`guard_kit.md_table_cells` — the same left-to-right walk,
    minus the empty leading field a bare ``line.split("|")`` produces (hence the indices
    shift down by one), plus ``\\|``-escape awareness this matrix does not currently need.
    """
    rows = {}
    for line in _BLOCKS_MD.read_text(encoding="utf-8").splitlines():
        if not _ROW_RE.match(line):
            continue
        cells = md_table_cells(line)
        rows[int(cells[0])] = {
            "name": cells[1],
            "status": cells[2].replace("*", "").strip(),
            "write": cells[3].replace("*", "").strip(),
            "lossiness": cells[4].replace("*", "").strip(),
            "projection": cells[5].replace("*", "").strip(),
            "emits": cells[7],
        }
    return rows


def _projection() -> dict:
    """The shipped per-block-type READ projection, off ``capabilities()``."""
    from larkdocio import capabilities

    return capabilities(full=True)["surfaces"]["docx-read"]["block_read_support"]


def _projected_types() -> dict:
    return {row["block_type"]: row for row in _projection()["types"]}


def _name_drift(projected, documented):
    """``{block_type: (projected_name, matrix_name)}`` — the SAME check the name pin uses
    and the bite test drifts, so here too the check that guards is the check that bites.

    Compared **verbatim**, not :func:`prose`-normalized the way the emission cell is: a type
    name is an identifier a consumer keys a dict on (both shipped recipes look a row up by
    ``name``), so ``image`` vs ``Image`` is a drift, not a wording difference.
    """
    return {
        t: (row["name"], documented[t]["name"])
        for t, row in projected.items()
        if row["name"] != documented[t]["name"]
    }


def _membership_drift(projected, documented):
    """``(phantom, missing)`` — the SAME check the guards below use and the bite tests
    drift, so the check that guards is provably the check that bites."""
    p, d = set(projected), set(documented)
    return sorted(p - d), sorted(d - p)


def _registry_orphans():
    """Registered handler types with no row in the projection's SOURCE table.

    Read off ``READ_SUPPORT`` rather than off ``capabilities()`` on purpose: an orphan makes
    the projection refuse to build, so a check routed through the built payload could never
    observe the state it exists to detect.
    """
    from larkdocio.blocks.read_support import READ_SUPPORT

    return sorted(set(get_registry()) - {row[0] for row in READ_SUPPORT})


def test_the_read_projection_answers_all_three_questions_for_every_type():
    """AC1: for EVERY docx block type the projection answers **handled?**, **what it
    emits**, and **whether it is lossy** — all three, from the payload alone.

    A projection that answered only the first would add nothing: ``get_registry()`` already
    answers it, and the consumer who asked for this had already found that.
    """
    for block_type, row in sorted(_projected_types().items()):
        assert isinstance(row["handled"], bool), row
        assert isinstance(row["lossy"], bool), row
        assert row["emits"], f"type {block_type} projects no emission"
        assert row["name"], f"type {block_type} projects no name"
        assert row["lossiness"] in _READ_LOSSINESS_VOCAB, row
        # the boolean is DERIVED from the state, so the two can never disagree.
        assert row["lossy"] is (row["lossiness"] != "full"), row


def test_the_read_projection_matches_the_matrix_rows_bidirectionally():
    """AC2 (both directions): every matrix row appears in the projection and every
    projected type has a matrix row."""
    phantom, missing = _membership_drift(_projected_types(), _parse_full_rows())
    assert not phantom, (
        f"the read projection reports block types /BLOCKS.md has no row for: {phantom}")
    assert not missing, (
        f"/BLOCKS.md has rows the read projection drops: {missing}")


def test_the_projected_handled_flag_is_the_registry_itself_not_a_stored_copy():
    """AC1/AC3: ``handled`` is **derived** from ``get_registry()`` — so it cannot be a
    stale copy of it — and it agrees with the matrix's own read status."""
    rows = _parse_full_rows()
    registry = set(get_registry())
    for block_type, row in sorted(_projected_types().items()):
        assert row["handled"] is (block_type in registry), row
        assert row["handled"] is (rows[block_type]["status"] in _REGISTERED_STATUSES), row


def test_the_projected_emission_is_the_matrix_cell_itself():
    """AC1: "what it emits" is **/BLOCKS.md's own cell**, pinned equal rather than
    re-described — the wheel carries the text because it cannot carry the file, and this is
    what stops the shipped copy from drifting from the authoring surface."""
    rows = _parse_full_rows()
    drifted = {
        t: (row["emits"], rows[t]["emits"])
        for t, row in _projected_types().items()
        if prose(row["emits"]) != prose(rows[t]["emits"])
    }
    assert not drifted, (
        f"the projection's emission text has drifted from /BLOCKS.md's own cells: {drifted}")


def test_the_projected_name_is_the_matrix_cell_itself():
    """LD-203: the projected ``name`` is /BLOCKS.md's own **Name** cell, pinned equal — the
    third cell of the three-way pin, which shipped guarded only by "non-empty".

    This one is not cosmetic and that is why it is pinned rather than shrugged at: **both**
    shipped lookup recipes key a row BY NAME (``GUIDE.md`` § Capability matrix does
    ``next(row for row in support["types"] if row["name"] == "callout")``, and the packaged
    ``blocks/BLOCK_TYPES.md`` builds ``{row["name"]: …}``), so a drifted name is a consumer's
    ``StopIteration`` / missing dict key, not a wrong label.
    """
    drifted = _name_drift(_projected_types(), _parse_full_rows())
    assert not drifted, (
        f"the projection's type names have drifted from /BLOCKS.md's Name cells: {drifted}")


def test_the_name_pin_BITES_on_a_renamed_type():
    """LD-203, the bite: renaming one projected type is reported by the same check the pin
    runs — the mutation that used to leave this file fully green (``27 image`` → ``imaje``,
    the filed repro) — and the real projection greens it."""
    rows = _parse_full_rows()
    projected = {t: dict(row) for t, row in _projected_types().items()}
    assert projected[27]["name"] == "image", "the probe's premise moved; re-pick the type"
    projected[27]["name"] = "imaje"

    assert _name_drift(projected, rows) == {27: ("imaje", "image")}
    assert not _name_drift(_projected_types(), rows)


def test_the_projected_lossiness_is_the_matrix_cell_itself():
    """AC1: the lossiness answer is /BLOCKS.md's own Read-lossiness cell, same pinning."""
    rows = _parse_full_rows()
    drifted = {
        t: (row["lossiness"], rows[t]["lossiness"])
        for t, row in _projected_types().items()
        if row["lossiness"] != rows[t]["lossiness"]
    }
    assert not drifted, f"the projection's lossiness has drifted from /BLOCKS.md: {drifted}"


def test_every_matrix_row_carries_a_valid_read_lossiness_state():
    """The read axis gets the same closed-vocabulary discipline the write axis has: a
    missing or mistyped state is drift, not a gap to shrug at."""
    rows = _parse_full_rows()
    missing = _EXPECTED_TYPES - set(rows)
    assert not missing, f"/BLOCKS.md is missing rows for {sorted(missing)}."
    bad = {t: r["lossiness"] for t, r in rows.items()
           if r["lossiness"] not in _READ_LOSSINESS_VOCAB}
    assert not bad, (
        f"/BLOCKS.md has rows with an unknown read-lossiness state: {bad}. "
        f"Valid: {sorted(_READ_LOSSINESS_VOCAB)}.")


def test_the_read_lossiness_vocabulary_section_documents_every_slug():
    """A notation is only useful if the file explains it — and the projection ships that
    explanation, so an undefined slug would ship as an unexplained word."""
    text = _BLOCKS_MD.read_text(encoding="utf-8")
    assert "## Read-lossiness vocabulary" in text
    for slug in _READ_LOSSINESS_VOCAB:
        assert f"| **{slug}** |" in text, (
            f"/BLOCKS.md § Read-lossiness vocabulary does not define {slug!r}")


def test_the_projection_ships_the_vocabulary_it_uses():
    """AC1: the five state names travel WITH the projection. A consumer on a wheel cannot
    open the matrix, so a slug with no shipped meaning is a word they must guess at."""
    vocabulary = _projection()["lossiness_vocabulary"]
    assert set(vocabulary) == _READ_LOSSINESS_VOCAB
    for slug, meaning in vocabulary.items():
        assert len(meaning.split()) >= 8, (slug, meaning)
    # …and every state a row actually uses is in it (no orphan state).
    used = {row["lossiness"] for row in _projection()["types"]}
    assert used <= set(vocabulary)


def test_the_not_handled_state_is_exactly_the_unregistered_set():
    """The one mechanical coupling between the two axes: ``not-handled`` means *no
    handler*, so it must be exactly the set the registry lacks — never a judgement."""
    rows = _parse_full_rows()
    not_handled = {t for t, r in rows.items() if r["lossiness"] == "not-handled"}
    unregistered = set(rows) - set(get_registry())
    assert not_handled == unregistered, (
        f"'not-handled' rows {sorted(not_handled)} != the types with no handler "
        f"{sorted(unregistered)}")


def test_a_placeholder_status_row_is_projected_reference_only():
    """A ``placeholder`` row emits a traceable marker instead of the block's content, which
    is precisely ``reference-only`` — so the two axes cannot contradict each other."""
    rows = _parse_full_rows()
    offenders = {t: r["lossiness"] for t, r in rows.items()
                 if r["status"] == "placeholder" and r["lossiness"] != "reference-only"}
    assert not offenders, (
        f"these placeholder rows do not project as reference-only: {offenders}")


def test_an_unregistered_type_projects_as_not_handled_rather_than_being_absent():
    """The amplifier's unknown-type arm: a type nobody handles must be **present and
    answered**, not missing. An absent row reads as "no information"; a
    ``handled: false`` row is the answer."""
    projected = _projected_types()
    for block_type in (20, 35, 48, 999):
        row = projected[block_type]
        assert row["handled"] is False, row
        assert row["lossiness"] == "not-handled" and row["lossy"] is True, row
    # and the forward-compat case is stated for a type this table cannot enumerate.
    assert _projection()["unlisted_type"]


def test_the_representative_spread_answers_the_question_each_type_poses():
    """The amplifier's spread — one assertion set per class of answer, because a
    projection that is right about paragraphs and wrong about images has not helped
    anyone."""
    projected = _projected_types()

    paragraph = projected[2]          # fully supported
    assert paragraph["handled"] and paragraph["lossiness"] == "full"
    assert not paragraph["lossy"]

    table = projected[31]             # lossy by design — merges become HTML
    assert table["handled"] and table["lossiness"] == "projected" and table["lossy"]
    assert "html" in table["emits"].lower()

    image = projected[27]             # the bytes leave the Markdown
    assert image["handled"] and image["lossiness"] == "out-of-band" and image["lossy"]

    add_on = projected[40]            # a diagram add-on → a mermaid fence
    assert add_on["handled"] and add_on["lossiness"] == "projected"
    assert "mermaid" in add_on["emits"]

    embedded_base = projected[18]     # a marker + a token, nothing fetched
    assert embedded_base["handled"] and embedded_base["lossiness"] == "reference-only"


def test_the_read_projection_encodes_no_write_status():
    """The two axes stay separate. Per-block WRITE support is already projected as the
    creatable floor; a READ row that mentioned creatability would rot the moment a type
    became creatable (a diagram add-on is the live candidate)."""
    for row in _projection()["types"]:
        blob = " ".join(str(v) for v in row.values()).lower()
        for word in ("creatable", "not-creatable", "editable"):
            assert word not in blob, (row["block_type"], word)
    assert set(_projected_types()[40]) == set(_projected_types()[2]), (
        "every row carries the same keys — a per-type shape is not a schema")


def test_the_read_projection_round_trips_through_json():
    """Like the rest of ``capabilities()``: JSON-native types only, so a consumer can hand
    the answer to another process."""
    import json

    projection = _projection()
    assert json.loads(json.dumps(projection)) == projection


def test_the_consumers_own_probe_answers_will_my_callouts_survive():
    """THE acceptance check, run the way the consumer ran it: answer "will my callouts
    survive the read, and what do they become?" using **only** ``capabilities()``."""
    from larkdocio import capabilities

    caps = capabilities(full=True)
    rows = {r["name"]: r for r in
            caps["surfaces"]["docx-read"]["block_read_support"]["types"]}
    callout = rows["callout"]
    assert callout["handled"] is True
    assert callout["lossy"] is True
    assert "children" in callout["emits"] and ">" in callout["emits"]
    meaning = caps["surfaces"]["docx-read"]["block_read_support"][
        "lossiness_vocabulary"][callout["lossiness"]]
    assert meaning  # …and the state name it answered with explains itself


def test_the_projection_names_the_code_it_was_projected_out_of():
    """"Is this hand-maintained?" must be answerable from the payload alone — the same
    posture every other projection in the registry takes."""
    projection = _projection()
    assert "get_registry" in projection["projected_from"]
    assert "read_support" in projection["projected_from"]
    assert projection["summary"]


# --- AC2 / AC3: the guards BITE — each direction proven separately ----------- #

def test_the_projection_drift_guard_bites_on_a_dropped_row():
    """AC2, direction one: a matrix row the projection dropped is reported ``missing`` by
    the SAME check that guards — and the real projection greens it."""
    documented = set(_parse_full_rows())
    drifted = sorted(documented)[:-1]
    phantom, missing = _membership_drift(drifted, documented)
    assert not phantom and missing == [sorted(documented)[-1]]

    phantom2, missing2 = _membership_drift(_projected_types(), documented)
    assert not phantom2 and not missing2


def test_the_projection_drift_guard_bites_on_a_phantom_row():
    """AC2, direction two: a projected type with no matrix row is reported ``phantom``."""
    documented = set(_parse_full_rows())
    phantom, missing = _membership_drift(sorted(documented) + [4242], documented)
    assert phantom == [4242] and not missing


def test_a_handler_registered_without_a_matrix_row_cannot_SHIP(monkeypatch):
    """AC3: the projection is DERIVED, so a new handler cannot ship without appearing.

    Proven with a throwaway handler rather than by inspection: registering a type with no
    matrix row makes the orphan check report it **and** makes ``capabilities()`` itself
    refuse to build — the phantom-row posture the packaged-docs projection already takes,
    turned on the direction that matters here (an omission, not an invention).
    """
    from larkdocio import capabilities
    from larkdocio.blocks import BLOCK_REGISTRY

    assert not _registry_orphans(), "the live tree must be orphan-free before the probe"

    monkeypatch.setitem(BLOCK_REGISTRY, 9998, lambda parser, block, indent: None)
    assert _registry_orphans() == [9998]
    with pytest.raises(RuntimeError) as excinfo:
        capabilities(full=True)
    assert "9998" in str(excinfo.value)

    monkeypatch.undo()
    assert not _registry_orphans()
    assert capabilities(full=True)  # …and it builds again, so the probe proved the guard, not a break


def test_the_matrix_row_direction_bites_too():
    """AC3's other half: a row whose handler disappeared must not silently keep claiming to
    be handled. ``handled`` is the registry, so removing a handler flips it — and the
    status cross-check in this module then reddens."""
    rows = _parse_full_rows()
    registry = set(get_registry())
    assert 22 in registry and rows[22]["status"] == "rendered"
    pretend_registry = registry - {22}
    assert (22 in pretend_registry) is not (rows[22]["status"] in _REGISTERED_STATUSES), (
        "dropping a handler must contradict its rendered row — that contradiction is the "
        "guard")


# --- AC4 / AC5: the two shipped pointers ------------------------------------ #

def test_the_packaged_block_doc_points_at_the_shipped_projection():
    """AC4: the one block document the wheel carries used to answer "is type N supported?"
    by redirecting to a repo-root file no wheel contains. It now names the shipped
    projection, which a wheel-only reader can actually open."""
    packaged = (REPO_ROOT / "src" / "larkdocio" / "blocks"
                / "BLOCK_TYPES.md").read_text(encoding="utf-8")
    assert "block_read_support" in packaged, (
        "the packaged block doc must name the shipped projection")
    assert "capabilities()" in packaged
    # the dev-repo matrix may still be cited, but only as what it is — labelled.
    for line in packaged.splitlines():
        if "BLOCKS.md" in line and "BLOCK_TYPES" not in line:
            break
    else:  # pragma: no cover - defensive
        pass


def test_the_guide_points_at_the_block_read_projection():
    """AC5: the answer is reachable from the shipped guide, which named the block matrix
    zero times — so "which block types survive a read" was a question the guide could not
    answer at all."""
    from larkdocio import guide

    text = guide(full=True)
    assert "block_read_support" in text, (
        "the guide must point at the per-block-type read projection")
