# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Characterization + split guard for the ``capabilities`` package split (LD-244).

The 2,770-line ``capabilities.py`` was split into a ``capabilities/`` package along its
banner-delimited regions, behind a re-export shim. The precedent and template is
``tests/test_sheets_requests_package_split.py`` (LD-224), itself modelled on
``tests/test_write_model_package_split.py`` (LD-087). This guard is the strictest of the
three, for two reasons this module has and those two did not:

* ``capabilities()`` returns **data a consumer reads** — a 136 KB dict that the shipped
  guide, ``PERMISSIONS.md``, the front-door doctrine guards and downstream callers all
  project off. So the gate here is not "the suite is green", it is **the output is
  byte-identical**: its canonical JSON is pinned by SHA-256 *and* by byte length below.
* ``larkdocio.capabilities`` **resolves two different ways on purpose.**
  ``larkdocio/__init__.py`` does ``from .capabilities import capabilities``, so the
  *attribute* ``larkdocio.capabilities`` is the **function**, while
  ``importlib.import_module("larkdocio.capabilities")`` is the **module**. Both are live
  and both are consumer-reachable. Turning the module into a package is exactly the change
  that can silently flip which one wins at import time, so both are asserted explicitly,
  and the AC3 arm re-asserts them from a **cold interpreter** where import order is real
  rather than an artefact of whatever the test session already imported.

Every baseline number below is **captured from the tag**
``refactor-baseline-2026-08-03-LD-244`` by introspection, not hand-typed:

* **B1 — the full pre-split vocabulary still resolves** from ``larkdocio.capabilities``,
  all 93 names (37 public + 56 private), and each of the 62 the package defines is the
  **same object** as the definition in the submodule it moved to (identity, not presence).
* **the public name set is EXACTLY the baseline's** — no name lost, and none gained.
  ``tests/consumer_text.py`` enrols ``larkdocio.capabilities`` by name and builds the
  shipped-docstring corpus from its ``dir()`` minus underscored names, so a submodule named
  without a leading underscore would silently enlarge the corpus the dialect guard greps.
  Every submodule is ``_``-prefixed and this assertion is what holds that.
* **the module docstring is byte-identical** — shipped prose a consumer reaches through
  ``help()``, and the one text this refactor physically moves file. Pinned by SHA-256.
* **``capabilities()``'s output is byte-identical** — the AC4 gate.

Written and passing (its baseline half) **before** the split, so it pins the pre-split
surface rather than whatever the split happened to produce.
"""
import ast
import copy
import hashlib
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import private_tree  # (LD-685)

import larkdocio
from capabilities_anchor import (
    ANCHOR_DATE, ANCHOR_PIN, ANCHOR_VERSION, COLD_PROBE, KEY_OWNERS, LEDGER_PATH, RECUT,
    WHOLE_PAYLOAD, anchor_addresses, anchor_blob, anchor_digest, ledger_rows,
    measure_addresses, owner_gaps, pin_gaps, release_dates_normalised, version_normalised,
)

# --------------------------------------------------------------------------- #
# Baseline data — captured at refactor-baseline-2026-08-03-LD-244 by           #
# introspecting the un-split module and its own source's banner regions.       #
# --------------------------------------------------------------------------- #

#: The re-exported stdlib / sibling-module names. They are part of the surface because
#: ``dir()`` reports them, and the consumer-docstring corpus is built from ``dir()`` —
#: dropping one would shrink the corpus the dialect guard greps.
_INHERITED_IMPORTS = (
    "LEGACY_ENV", "List", "Optional", "READ_ENV", "WRITE_ENV", "_CREATABLE_BLOCK_TYPES",
    "_CommentsReadClient", "_ContactsSearchClient", "_DOCX_LIFECYCLE_OPS",
    "_DOCX_WRITE_OPS", "_DocxParser", "_DocxReadClient", "_DocxWriteClient",
    "_InsertRequest", "_NewBlockKind", "_SHEETS_LIFECYCLE_OPS", "_SHEETS_WRITE_OPS",
    "_SheetsExportReader", "_SheetsReadClient", "_SheetsWriteClient", "_comments_read",
    "_deep_read_embedded_sheet", "_perm", "_project_block_ids", "_resolve_user",
    "_sheets_dry_run", "dataclass", "dataclasses", "field", "inspect", "typing",
)

#: ``{name: the submodule that DEFINES it}`` for every name the split moves out of the flat
#: module. The value is what identity is asserted against (B1's "same object"). The line
#: ranges are the pre-split slices each submodule carries **verbatim** — they tile
#: ``capabilities.py``'s body (115-2770) contiguously, with no overlap and no hole.
_DEFINED_IN = {
    # _models — pre-split lines 115-812 (the 17 frozen dataclasses of the typed layer)
    "BlockProjectionSupport": "_models",
    "BlockReadSupport": "_models",
    "BlockTypeSupport": "_models",
    "Capabilities": "_models",
    "ContentConstraints": "_models",
    "Credentials": "_models",
    "Doc": "_models",
    "EntryPoint": "_models",
    "Flag": "_models",
    "GateCoverage": "_models",
    "GateMember": "_models",
    "LevelDescriptor": "_models",
    "LifecycleOp": "_models",
    "Operation": "_models",
    "Reconciliation": "_models",
    "SafetyContract": "_models",
    "Surface": "_models",
    # _projections — pre-split lines 813-1239 (the projection legs)
    "NOT_READ_BACK_FIELDS": "_projections",
    "NOT_WRITABLE_STYLE_FIELDS": "_projections",
    "_docx_anchor_kinds": "_projections",
    "_docx_block_projection_support": "_projections",
    "_docx_block_read_support": "_projections",
    "_docx_content_constraints": "_projections",
    "_docx_reconciliation": "_projections",
    "_docx_write_operations": "_projections",
    "_flatten_anchor_types": "_projections",
    "_flatten_content_types": "_projections",
    "_lifecycle_operations": "_projections",
    "_merge_types": "_projections",
    "_public_ops": "_projections",
    "_read_operations": "_projections",
    "_refused_merge_types": "_projections",
    "_sheets_write_operations": "_projections",
    "_style_fields": "_projections",
    "_tree_helper_operations": "_projections",
    # _credentials — pre-split lines 1240-1266 (the READ/WRITE app split)
    "_read_credentials": "_credentials",
    "_write_credentials": "_credentials",
    # _packaged_docs — pre-split lines 1267-1418 (the packaged-documents leg)
    "_ENTRY_POINT_NOTES": "_packaged_docs",
    "_docs": "_packaged_docs",
    "_entry_points": "_packaged_docs",
    # _config — pre-split lines 1419-1576 (the config.json output schema)
    "CONFIG_KEY_MEANINGS": "_config",
    "CONFIG_REGENERATE": "_config",
    "CONFIG_REGION_BEGIN": "_config",
    "CONFIG_REGION_END": "_config",
    "ConfigKey": "_config",
    "_output_config_defaults": "_config",
    "config_schema": "_config",
    "config_schema_markdown": "_config",
    # _flag_descriptors — pre-split lines 1577-1657 (the opt-in flags)
    "_flags": "_flag_descriptors",
    # _contracts — pre-split lines 1658-1954 (the safety contracts)
    "_safety_contracts": "_contracts",
    # _gates — pre-split lines 1955-2243 (the two GateCoverage builders)
    "_comments_read_gate_coverage": "_gates",
    "_docx_write_gate_coverage": "_gates",
    # _levels — pre-split lines 2244-2369 (the level model, per READ surface)
    "_comments_read_levels": "_levels",
    "_contacts_read_levels": "_levels",
    "_docx_read_levels": "_levels",
    "_embedded_deep_read_levels": "_levels",
    "_sheets_read_levels": "_levels",
    # _permissions — pre-split lines 2370-2460 (the permissions leg)
    "_IMPL_SEEDS": "_permissions",
    "_surface_with_permissions": "_permissions",
    "_with_permissions": "_permissions",
    # _assembly — pre-split lines 2461-2770 (assembly)
    "_build": "_assembly",
    "capabilities": "_assembly",
}

#: The complete baseline vocabulary — 93 names.
_BASELINE_VOCABULARY = tuple(sorted(set(_DEFINED_IN) | set(_INHERITED_IMPORTS)))

#: The eleven banner-derived submodules.
_SUBMODULES = tuple(sorted(set(_DEFINED_IN.values())))

#: SHA-256 of ``larkdocio.capabilities.__doc__`` — captured at the LD-244 baseline tag
#: (``87cd53d5370e27731c51876461e9ca924fd5777cf0d3ad98c7dc92dcc7bc90eb``, 5,878 chars), where it
#: held through the split it was captured for.
#:
#: **Every re-anchor since that tag was deliberate and its reason is written down below** — the
#: sibling JSON gate below is the precedent for the ceremony (the count is the length of the list
#: that follows, so it is not stated here as a figure a later landing would age):
#:
#: 1. **LD-313** (2026-08-07, paying LD-300's deferred ``sibling-matrix`` citation debt)
#:    labels this docstring's citations of ``SHEETS.md`` / ``BLOCKS.md`` / ``PERMISSIONS.md``
#:    with ``DEV_REPO_LABEL`` (``"in the dev repo"``). The three living matrices are cited
#:    here as sources of truth and **the wheel carries none of them**, so a wheel-only reader
#:    was being sent to files they do not have; each citation now says where it lives and, in
#:    the two places a shipped equivalent exists, names it (``larkdocio.capabilities()`` /
#:    ``larkdocio.guide()``). **5,878 → 6,208 chars**, all of it label text — no claim about
#:    a projection, a registry or an op changed.
#:
#:    **This move does NOT reach ``capabilities()``'s output.** The module docstring is
#:    shipped prose a consumer reads through ``help()``; it is not projected into the
#:    payload, and the AC4 gate below is **unchanged at its 228,472 bytes** across this change —
#:    which is the assertion that proves it rather than the claim.
#: 2. **LD-459** (2026-08-14) adds the four sentences that name **`operation_index`** as each
#:    surface's complete call-site enumeration. The docstring's own promise — "a single
#:    machine-readable answer to what can this toolkit do" — was false in one specific way: the
#:    key it sent a reader to (`operations`) held 96 of the registry's 108 `(surface, op)`
#:    pairs, and the paragraph said nothing about the two sibling keys holding the other 20.
#:    **6,208 → 6,492 chars**, all of it the new pointer — no claim about a projection, a
#:    registry or an op was rewritten.
#: 3. **LD-475** (2026-08-20) re-pins it for the shape change the maintainer ruled: the paragraph that
#:    sent a reader to ``operation_index`` and three sibling keys now describes **one**
#:    ``operations`` key with a ``kind`` on every row, and a new paragraph states the two doors
#:    (the no-argument summary, ``full=True`` for the whole registry). LD-459's own reason is
#:    kept, not struck — the sentence that says a reader of the obvious key cannot miss a verb
#:    is still there; what changed is that the obvious key is now the only one.
#:    **6,492 → 7,284 chars.** The claims about the projection discipline, the per-block read
#:    support, the gate coverage and the permission derivation are byte-identical. The last
#:    73 of those chars are a **correction inside this same change**: the size sentence first
#:    read "about two orders of magnitude smaller than the registry it indexes", which nobody
#:    had measured — the measured ratio is 23.8× on the landing tree and the shipped size guard
#:    binds it at more than 20× — so it now states the bound its guard enforces rather than an
#:    order of magnitude, and states that the guard re-measures it on every run rather than
#:    recording a figure here that a release would age.
#: 4. **LD-596** (2026-08-31) re-pins it because the summary's own description was **untrue by
#:    omission** and had to move here too. It read "the scopes each surface needs", and for six
#:    surfaces the summary printed a bare ``scopes: []`` beside it — which reads as *needs no
#:    permission*, where the registry's answer is *no scope was ever observed demanded for these
#:    endpoints and this library does not guess*. Seven more printed a complete-LOOKING list and
#:    reached unrecorded endpoints as well. The summary now carries a per-surface
#:    ``unknown_requirements`` list of endpoint keys (13 of 17 surfaces on the landing tree,
#:    computed by the test, never spelled), and this paragraph says the scope list is what a
#:    surface is **known** to need and names the key that sits beside it. LD-475's own reason is
#:    kept, not struck — the two-doors paragraph and the ratio-its-guard-enforces sentence are
#:    byte-identical. **7,284 → 7,465 chars**, all of it the new pointer plus the word "known";
#:    no claim about a projection, a registry, an op or a scope requirement changed.
#:
#:    **This move does NOT reach ``capabilities()``'s output either.** The new key is emitted by
#:    the **summary**, a derived projection; ``capabilities(full=True)`` is byte-identical across
#:    the change (sha256 ``0d6e04c1…``, 326,871 bytes, measured both sides) and the whole-payload
#:    tripwire below is unchanged — which is the assertion that proves it rather than the claim.
#: 5. **LD-699** (2026-11-01, round 2 of the public-export review, R13) re-pins it for three
#:    labels and nothing else: ``SHEETS.md``, ``BLOCKS.md`` and ``PERMISSIONS.md`` live at the
#:    root of every clone, so the docstring now says **in the source repository** where it said
#:    **in the dev repo** — the phrase now reserved for the maintainers' private record.
#:    **7,465 → 7,492 chars** (three × nine); no other byte moved.
#: 6. **LD-714** (2026-11-07, round 11 of the public-export review, R11-23) re-pins it for one
#:    added paragraph: the "complete enumeration of its call sites" sentence gains its carve-out
#:    — ``drive-read``'s operations are the ``DriveClient`` methods alone, and the composed
#:    ``read_folder`` / ``render_folder`` are not rows. **7,492 → 7,925 chars**; no claim about a
#:    projection, a registry, an op or a scope requirement changed, and ``capabilities()``'s
#:    output does not move for it.
_BASELINE_DOCSTRING_SHA256 = (
    "52d0091055b6a31934e7758730e02e5ec3d43a2d1073ca609b79c6cb6a2e761f"
)

#: **THE ONE WHOLE-PAYLOAD TRIPWIRE, and it is GENERATED (LD-530).**
#:
#: This was three whole-payload freezes under two serialisations, each with a hand-authored
#: byte-arithmetic essay beside it — **1,795 `#:` lines stood right here**, and twenty
#: consecutive landings paid the re-derivation. The essays are **relocated verbatim, not
#: struck**, to [`dev/capabilities-anchor-ledger.md`](../dev/capabilities-anchor-ledger.md)
#: § "Preserved history" § 1, where they stay readable and stop being suite LOC.
#:
#: **What replaced them.** `capabilities_anchor.ANCHOR_PIN` — one generated table holding the
#: whole normalised payload under `@payload` plus **one row per address** (every top-level
#: key, `surfaces` expanded per surface). Re-cut with
#: `./scripts/reanchor-capabilities.sh --issue LD-NNN --why "<one line>"` (in the dev repo;
#: `capabilities_anchor.RECUT` gives the by-hand route), which measures the tree, rewrites the block and appends the ledger row. **There is no arithmetic to do and
#: none may be written**: the diff of the generated block names the addresses that moved, and
#: that diff IS the disclosure. `--check` reports which addresses moved without writing.
#:
#: The two names below are kept — four assertions read them and their claims are unchanged —
#: but they are **derived from the generated pin**, so no whole-payload constant is
#: hand-authored in this repo any more.
_BASELINE_OUTPUT_BYTES, _BASELINE_OUTPUT_SHA256 = ANCHOR_PIN[WHOLE_PAYLOAD]


def _capabilities_module():
    """The MODULE — and it has to be fetched this way.

    ``import larkdocio.capabilities as m`` does **not** work here: since Python 3.7 that
    form binds ``getattr(larkdocio, "capabilities")``, which the parent ``__init__`` has
    shadowed with the *function*. See
    :func:`test_the_import_as_form_binds_the_FUNCTION_not_the_module`, which pins that
    third resolution rather than letting it be a surprise twice.
    """
    return importlib.import_module("larkdocio.capabilities")


def _canonical_json(payload):
    """The one canonical serialization the AC4 gate is measured in."""
    return json.dumps(payload, default=str, sort_keys=True).encode("utf-8")


# --------------------------------------------------------------------------- #
# Baseline half — these pass at the tag, and pin what must survive.            #
# --------------------------------------------------------------------------- #

def test_the_baseline_vocabulary_is_the_full_93_names():
    """The fixture data itself is the captured baseline, not a hand-typed subset:
    62 names the module defines + 31 it re-exports from its imports."""
    assert len(_DEFINED_IN) == 62, len(_DEFINED_IN)
    assert len(_INHERITED_IMPORTS) == 31, len(_INHERITED_IMPORTS)
    assert len(_BASELINE_VOCABULARY) == 93, len(_BASELINE_VOCABULARY)


@pytest.mark.parametrize("name", _BASELINE_VOCABULARY)
def test_every_baseline_name_still_resolves(name):
    """B1 (first half) — no name importable from ``larkdocio.capabilities`` before the
    split stopped being importable from it after."""
    assert hasattr(_capabilities_module(), name), (
        f"{name} no longer importable from larkdocio.capabilities"
    )


def test_the_public_name_set_is_EXACTLY_the_baseline_set():
    """No name lost — and none GAINED. ``tests/consumer_text.py`` enrols this module by
    name and builds the shipped-docstring corpus from its ``dir()`` minus underscored
    names, so a non-underscored submodule would quietly enrol a new docstring in the
    consumer corpus. Every split-out module is ``_``-prefixed; this holds it."""
    public = {n for n in dir(_capabilities_module()) if not n.startswith("_")}
    expected = {n for n in _BASELINE_VOCABULARY if not n.startswith("_")}
    assert len(expected) == 37, len(expected)
    assert public == expected, {
        "gained": sorted(public - expected),
        "lost": sorted(expected - public),
    }


def test_the_module_docstring_is_byte_identical_to_the_baseline():
    """The module docstring is shipped prose a consumer reaches via ``help()`` (enrolled by
    ``tests/consumer_text.py``), and the one text this refactor physically moves file.
    ZERO-DRIFT, pinned by digest."""
    doc = _capabilities_module().__doc__
    assert doc is not None
    digest = hashlib.sha256(doc.encode("utf-8")).hexdigest()
    assert digest == _BASELINE_DOCSTRING_SHA256, (
        "the capabilities module docstring changed — it is shipped consumer prose; "
        "LD-244 is behavior- and text-preserving"
    )


def test_the_capabilities_OUTPUT_is_byte_identical_to_the_baseline():
    """**The AC4 gate.** ``capabilities()`` is the one part of this module consumers read
    as *data* — the shipped guide, ``PERMISSIONS.md`` and the front-door guards all project
    off it. A green suite is not the standard here; **zero output drift** is. A single
    differing byte fails this outright.

    Note what this pins that no other test does: not "same keys", not "equivalent" — the
    exact canonical serialization, by digest and by length.

    **LD-530: this is now the ONE whole-payload tripwire.** The top-level KEY SET it used to
    freeze as a literal seven-tuple is no longer asserted here — that claim moved to the
    bidirectional completeness arm below, which derives the key set from the payload at
    runtime (so LD-475's coming key collapse reddens instead of silently shrinking the arm)
    and names the guard that owns each key. The installed-version claim moved to
    :func:`test_the_version_leaf_is_pinned_to_the_INSTALLED_version`, its named owner.
    """
    payload = _capabilities_module().capabilities(full=True)
    blob = anchor_blob(payload)
    assert len(blob) == _BASELINE_OUTPUT_BYTES, (
        f"capabilities() canonical JSON is {len(blob)} bytes, baseline is "
        f"{_BASELINE_OUTPUT_BYTES} — the registry's OUTPUT moved"
    )
    assert hashlib.sha256(blob).hexdigest() == _BASELINE_OUTPUT_SHA256, (
        "capabilities() output drifted from its anchor — LD-244 is a pure relocation and its "
        "whole gate is that this hash does not move; if the payload genuinely SHOULD move, the "
        "anchor is re-cut in the same change that discloses the capability (see the constant's "
        "own note), never quietly"
    )


def test_the_output_is_json_round_trippable_and_stable_within_a_run():
    """Two calls in one process serialize identically, and the payload survives a
    ``json.dumps``/``loads`` round trip with no ``default=str`` coercion needed — the
    JSON-native-types-only discipline the module docstring claims."""
    m = _capabilities_module()
    first, second = m.capabilities(full=True), m.capabilities(full=True)
    assert _canonical_json(first) == _canonical_json(second)
    strict = json.dumps(first, sort_keys=True)
    assert json.loads(strict) == first


# --------------------------------------------------------------------------- #
# AC3 — the dual resolution. Live before the split, and it must stay live.     #
# --------------------------------------------------------------------------- #

def test_the_larkdocio_capabilities_ATTRIBUTE_is_the_FUNCTION():
    """AC3(a). ``larkdocio/__init__.py`` does ``from .capabilities import capabilities``,
    so the package attribute shadows the module. Consumers reach ``larkdocio.capabilities()``
    that way; if the split flipped the shadowing, every one of them would get a module and
    ``TypeError: 'module' object is not callable``."""
    import larkdocio

    attr = getattr(larkdocio, "capabilities")
    assert callable(attr), f"larkdocio.capabilities is {type(attr)}, not the function"
    assert attr is _capabilities_module().capabilities
    assert attr.__name__ == "capabilities"


def test_import_module_gives_the_MODULE_not_the_function():
    """AC3(b). The other half of the same coin: the import system still resolves the dotted
    path to the module object, whatever the parent package's attribute says."""
    mod = importlib.import_module("larkdocio.capabilities")
    assert mod.__name__ == "larkdocio.capabilities"
    assert not callable(mod)
    assert mod is sys.modules["larkdocio.capabilities"]


def test_the_import_as_form_binds_the_FUNCTION_not_the_module():
    """AC3(c) — the resolution the issue's own two-way statement did not name, found by
    this guard failing on its first run against the **un-split** module.

    Since Python 3.7, ``import a.b as c`` binds ``getattr(a, "b")`` (falling back to
    ``sys.modules["a.b"]`` only on ``AttributeError``). The attribute here is the shadowing
    *function*, so ``import larkdocio.capabilities as m`` hands back a callable, not a
    module — today, before the split. It is pinned because it is exactly the kind of quirk
    a package split silently flips, and because the LD-224 template used precisely this
    form (correctly, there: ``sheets.requests`` has no shadowing parent).
    """
    import larkdocio.capabilities as bound

    assert callable(bound), (
        "the shadowing changed: `import larkdocio.capabilities as m` used to bind the "
        "function; a consumer doing this now gets a module"
    )
    assert bound is _capabilities_module().capabilities
    assert bound is not _capabilities_module()


_COLD_PROBE = r"""
import importlib, json, sys
import larkdocio
import larkdocio.capabilities
import larkdocio.cli
mod = importlib.import_module("larkdocio.capabilities")
attr = getattr(larkdocio, "capabilities")
print(json.dumps({
    "attr_is_callable": callable(attr),
    "attr_is_the_function": attr is mod.capabilities,
    "module_is_module": type(mod).__name__ == "module",
    "module_name": mod.__name__,
    "from_import_works": all(
        hasattr(mod, n) for n in %(names)r
    ),
    "cli_ok": hasattr(larkdocio.cli, "cli"),
}))
"""


def test_a_COLD_interpreter_resolves_both_ways_and_imports_the_cli_clean():
    """AC3's real arm. In-process assertions are contaminated by whatever the test session
    already imported; a fresh interpreter is where import order actually happens. Three
    entry points import clean (``larkdocio``, ``larkdocio.capabilities``, ``larkdocio.cli``
    — the last is the circular-import canary, since ``cli`` imports the registry and the
    registry imports ``larkdocio.__version__``), and the dual resolution holds there."""
    probe = _COLD_PROBE % {"names": list(_BASELINE_VOCABULARY)}
    proc = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"cold import failed:\n{proc.stderr[-3000:]}"
    out = json.loads(proc.stdout)
    assert out == {
        "attr_is_callable": True,
        "attr_is_the_function": True,
        "module_is_module": True,
        "module_name": "larkdocio.capabilities",
        "from_import_works": True,
        "cli_ok": True,
    }, out


def test_a_COLD_interpreter_produces_the_SAME_OUTPUT_BYTES():
    """AC4 from a cold process — the hash is not an artefact of this session's import
    order or of some module the suite happened to warm up first."""
    probe = COLD_PROBE.format(tests_dir=str(Path(__file__).resolve().parent))
    proc = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    digest, length, version = proc.stdout.split()
    assert digest == _BASELINE_OUTPUT_SHA256
    assert int(length) == _BASELINE_OUTPUT_BYTES
    # The normalised leaf, pinned from the cold process too: the substitution may never hide a
    # registry that reports a version other than the installed one.
    assert version == larkdocio.__version__


def test_the_ANCHOR_IS_INVARIANT_UNDER_A_VERSION_BUMP():
    """**The LD-316 arm.** Bump the version under the assembly and the anchor must not move —
    while the RAW canonical output must. Both halves matter: the first is the cut-tolerance
    the release ritual needs (``release.sh`` gates at step 3, bumps at step 7), the second
    proves the normalisation is not a no-op dressed up as a guard."""
    assembly = importlib.import_module("larkdocio.capabilities._assembly")
    before = _capabilities_module().capabilities(full=True)
    original = assembly.__version__
    try:
        assembly.__version__ = "9.99.9"
        after = _capabilities_module().capabilities(full=True)
    finally:
        assembly.__version__ = original

    assert after["version"] == "9.99.9", "the probe did not actually move the version leaf"
    assert _canonical_json(after) != _canonical_json(before), (
        "the RAW output must move with the version — otherwise this test proves nothing"
    )
    assert anchor_digest(after) == anchor_digest(before) == (
        _BASELINE_OUTPUT_SHA256, _BASELINE_OUTPUT_BYTES)
    assert ANCHOR_VERSION not in _canonical_json(before).decode("utf-8"), (
        "the substitute must never be a string the real payload could contain"
    )


def _with_release_heading_date(text, date):
    """*text* with its FIRST ``## [X.Y.Z] — <date>`` heading re-dated — a scratch copy."""
    return re.sub(
        r"^(## \[\d+\.\d+\.\d+\] — )\d{4}-\d{2}-\d{2}",
        lambda m: m.group(1) + date, text, count=1, flags=re.MULTILINE,
    )


def _patched_packaged(mutate):
    """A stand-in for ``larkdocio.guide._packaged`` that runs *mutate* over the two release
    documents' text and hands every other resource back untouched."""
    guide_module = importlib.import_module("larkdocio.guide")
    real = guide_module._packaged
    dated = {guide_module.RELEASE_NOTES_RESOURCE, guide_module.CHANGELOG_RESOURCE}

    def _fake(resource, package="larkdocio"):
        text = real(resource, package)
        return mutate(text) if resource in dated else text

    return guide_module, real, _fake


def test_the_ANCHOR_IS_INVARIANT_UNDER_A_RELEASE_HEADING_DATE_BUMP():
    """**The LD-452 arm, parallel to the version one.** LD-443 made *setting the release
    header's date at the cut* a required ritual step, and the release ``##`` headings project
    into ``docs[…]["sections"]`` as ``heading`` + ``slug`` — so that mandatory edit moved this
    digest at every cut. Re-date a **scratch copy** of both documents under the assembly: the
    RAW output must move (or this proves nothing) and the anchor must not."""
    before = _capabilities_module().capabilities(full=True)
    guide_module, real, fake = _patched_packaged(
        lambda text: _with_release_heading_date(text, "2099-12-31"))
    try:
        guide_module._packaged = fake
        after = _capabilities_module().capabilities(full=True)
    finally:
        guide_module._packaged = real

    assert after["docs"]["release_notes()"]["sections"][0]["heading"].endswith("2099-12-31"), (
        "the probe did not actually move the release-heading date")
    assert _canonical_json(after) != _canonical_json(before), (
        "the RAW output must move with the date — otherwise this test proves nothing"
    )
    assert anchor_digest(after) == anchor_digest(before) == (
        _BASELINE_OUTPUT_SHA256, _BASELINE_OUTPUT_BYTES)
    assert ANCHOR_DATE not in _canonical_json(before).decode("utf-8"), (
        "the substitute must never be a string the real payload could contain"
    )


def test_the_ANCHOR_STILL_MOVES_when_a_release_heading_changes_by_anything_BUT_its_date():
    """The other direction — the tolerance removed the date and **nothing else**. Rename the
    heading (its ``X.Y.Z``) rather than re-dating it and the anchor must redden: a new or
    re-numbered release *section* is a genuine content change, re-anchored with the ceremony."""
    before = _capabilities_module().capabilities(full=True)
    guide_module, real, fake = _patched_packaged(
        lambda text: re.sub(r"^## \[\d+\.\d+\.\d+\]", "## [9.99.9]", text,
                            count=1, flags=re.MULTILINE))
    try:
        guide_module._packaged = fake
        after = _capabilities_module().capabilities(full=True)
    finally:
        guide_module._packaged = real

    assert after["docs"]["changelog()"]["sections"][0]["heading"].startswith("[9.99.9]")
    assert anchor_digest(after) != anchor_digest(before), (
        "only the DATE portion may be normalised — a moved X.Y.Z must still move the anchor"
    )


def test_the_REAL_release_heading_dates_are_pinned_to_the_SHIPPED_DOCUMENTS():
    """The positive pin the normalisation owes (AC1's fourth sub-condition): the date leaves
    the digest and does **not** leave the suite. Every release row's date in the payload is
    the date that document's own ``##`` heading carries — so the substitution can never hide a
    registry reporting dates the shipped documents do not."""
    payload = _capabilities_module().capabilities(full=True)
    guide_module = importlib.import_module("larkdocio.guide")
    for accessor, resource in (
        ("release_notes()", guide_module.RELEASE_NOTES_RESOURCE),
        ("changelog()", guide_module.CHANGELOG_RESOURCE),
    ):
        in_document = re.findall(
            r"^## (\[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2})$",
            guide_module._packaged(resource), flags=re.MULTILINE)
        reported = [row["heading"] for row in payload["docs"][accessor]["sections"]]
        assert in_document, f"{resource} carries no dated release heading at all"
        assert reported == in_document, accessor
        # ...and the newest release's date is the one the header promise (LD-443) sets.
        assert reported[0].endswith(in_document[0][-10:])


# --------------------------------------------------------------------------- #
# Post-split half — RED before the split, GREEN after. The structural goal.    #
# --------------------------------------------------------------------------- #

def test_capabilities_is_a_package():
    """After the split ``larkdocio.capabilities`` is a PACKAGE (has ``__path__``)."""
    assert hasattr(_capabilities_module(), "__path__"), (
        "larkdocio.capabilities should be a package after the split"
    )


@pytest.mark.parametrize("submodule", _SUBMODULES)
def test_each_banner_submodule_imports_cleanly(submodule):
    """One module per banner-delimited region of the pre-split file."""
    assert importlib.import_module(f"larkdocio.capabilities.{submodule}") is not None


@pytest.mark.parametrize("name,submodule", sorted(_DEFINED_IN.items()))
def test_each_name_is_the_SAME_OBJECT_as_its_split_out_definition(name, submodule):
    """B1 (second half) — identity, not presence: the shim re-exports the very object the
    submodule defines, so no duplicate definition can drift behind it."""
    mod = importlib.import_module(f"larkdocio.capabilities.{submodule}")
    assert getattr(_capabilities_module(), name) is getattr(mod, name), (
        f"{name} is not the same object as larkdocio.capabilities.{submodule}.{name}"
    )


def test_every_submodule_name_is_underscore_prefixed():
    """The mitigation the migration plan chose, asserted directly: the package's internals
    are private, so none of them can join the consumer-reachable ``dir()`` surface that
    ``tests/consumer_text.py`` builds the shipped-docstring corpus from."""
    for submodule in _SUBMODULES:
        assert submodule.startswith("_"), submodule


def test_no_submodule_carries_a_docstring_into_the_consumer_corpus():
    """Belt and braces on the same risk from the other side: even a ``_``-prefixed module
    would be reachable if something enrolled it, so the submodule docstrings are one-line
    internal signposts, not shipped prose."""
    for submodule in _SUBMODULES:
        mod = importlib.import_module(f"larkdocio.capabilities.{submodule}")
        doc = mod.__doc__ or ""
        assert len(doc) < 400, (
            f"{submodule}'s docstring is {len(doc)} chars — submodule docstrings are "
            f"internal signposts; shipped prose belongs in the package docstring"
        )


# --------------------------------------------------------------------------- #
# LD-530 — THE LOCALIZED GUARDS, THE BIDIRECTIONAL COMPLETENESS ARM, AND THE   #
# DISCLOSURE GATE.                                                            #
#                                                                             #
# The design direction is RECONCILIATION § 1.1 (audit B's, maintainer-approved         #
# 2026-08-18); the failure shape it is built against is audit B § T1 § Risk:   #
# "a leaf NOT COVERED BY ANY LOCALIZED GUARD drifts and the auto-regenerated   #
# tripwire silently blesses it." The pattern is this repo's own exemplar,      #
# tests/test_permissions_registry.py — pure injectable gap functions, both     #
# directions red-proved, nothing derived that would make a direction vacuous.  #
# --------------------------------------------------------------------------- #

#: The parametrization source is the GENERATED pin table, so collection costs no
#: ``capabilities()`` call — and ``test_a_NAMED_OWNER_covers_its_addresses_ONE_NODE_ID_EACH``
#: below holds these ids equal to the set derived from the LIVE payload, which is what stops
#: a stale parametrization from quietly shrinking the localized coverage.
_PINNED_SURFACES = tuple(a for a in ANCHOR_PIN if a.startswith("surfaces/"))
_PINNED_TOP_LEVEL = tuple(
    a for a in ANCHOR_PIN if "/" not in a and a not in (WHOLE_PAYLOAD, "version"))


@pytest.fixture(scope="module")
def measured_addresses():
    """``{address: (bytes, sha256)}`` for the live payload — measured once per worker."""
    return measure_addresses(_capabilities_module().capabilities(full=True))


# ---- the localized guards: one node id per address, so a failure NAMES the drift ---- #

@pytest.mark.parametrize("address", _PINNED_TOP_LEVEL)
def test_a_TOP_LEVEL_INDEX_is_ANCHORED(address, measured_addresses):
    """One node id per non-``surfaces`` top-level key. The whole-payload tripwire above says
    *something* moved; this says **which index**, without any arithmetic."""
    assert measured_addresses[address] == ANCHOR_PIN[address], (
        f"capabilities()[{address!r}] moved: {measured_addresses[address]} vs the pin "
        f"{ANCHOR_PIN[address]}. Re-cut with {RECUT} — and if there is no capability change "
        f"behind it, the drift is the defect, not the pin."
    )


@pytest.mark.parametrize("address", _PINNED_SURFACES)
def test_a_SURFACE_is_ANCHORED(address, measured_addresses):
    """**The granularity answer for ``surfaces``.** One guard nominally owning ``surfaces``
    while seventeen surfaces drift inside it would satisfy the letter of a completeness arm
    and defeat its purpose, so every surface is its own address, its own pin and its own node
    id. This is also what makes a CROSS-SURFACE LEAK legible: when one surface's landing moves
    another surface's projection — a shared permission-evidence string, a shared scope note —
    the **victim** surface's own node id reddens and names it, which is the case audit A
    § T1 § Risk demanded be red-proved specifically."""
    assert measured_addresses[address] == ANCHOR_PIN[address], (
        f"capabilities()['surfaces'][{address.split('/', 1)[1]!r}] moved: "
        f"{measured_addresses[address]} vs the pin {ANCHOR_PIN[address]}. If the landing that "
        f"moved it was about a DIFFERENT surface, this is a cross-surface leak — find the "
        f"shared string before re-cutting."
    )


def test_the_version_leaf_is_pinned_to_the_INSTALLED_version(measured_addresses):
    """``version``'s named owner. Its pin is a **constant by construction** — the
    normalisation substitutes :data:`ANCHOR_VERSION` for it — so a pin alone would be a
    tautology, and this guard asserts the real leaf instead, against the installed version.
    That is the stronger claim, and it is the reason ``version`` is the one key whose owner is
    not one of the two parametrized guards (``capabilities_anchor.KEY_OWNERS``' own note)."""
    payload = _capabilities_module().capabilities(full=True)
    assert payload["version"] == larkdocio.__version__, (
        "the registry must report the INSTALLED version — the one leaf the anchor "
        "normalises away is pinned here instead, and to the real thing"
    )
    assert measured_addresses["version"] == ANCHOR_PIN["version"], (
        "the normalised version address moved, which can only mean the substitution stopped "
        "being applied — see capabilities_anchor.version_normalised"
    )


# ---- the completeness arm, both directions, against the RUNTIME-derived set ---- #

def test_every_ADDRESS_of_the_live_payload_is_PINNED(measured_addresses):
    """**Direction 1 (pins).** Audit B's named failure shape, refused: a leaf that no
    localized guard owns cannot exist, because the address set is derived from the payload at
    runtime and every address must have a row in the generated table."""
    gaps = pin_gaps(measured_addresses, ANCHOR_PIN)
    assert not gaps.unpinned, (
        "these addresses exist in capabilities() and have NO pin, so a drift inside them "
        f"would be blessed silently: {gaps.unpinned}. Run "
        f"{RECUT}."
    )


def test_no_PIN_outlives_its_ADDRESS(measured_addresses):
    """**Direction 2 (pins).** A pin whose address has vanished is a guard asserting nothing —
    the ``tests/test_permissions_registry.py::…_a_row_whose_operation_vanished`` shape."""
    gaps = pin_gaps(measured_addresses, ANCHOR_PIN)
    assert not gaps.orphaned, (
        f"these pins name addresses capabilities() no longer has: {gaps.orphaned}"
    )


def test_every_TOP_LEVEL_KEY_is_OWNED_by_a_named_guard():
    """**Direction 1 (owners).** Every top-level key answers to a guard **named** in
    ``capabilities_anchor.KEY_OWNERS``. The live set is read off the payload — never a
    hard-coded seven — so LD-475's key collapse (wave 2) reddens here rather than silently
    shrinking the arm."""
    gaps = owner_gaps(_capabilities_module().capabilities(full=True))
    assert not gaps.unowned, (
        f"these top-level payload keys have no named owning guard: {gaps.unowned} — add the "
        f"key to capabilities_anchor.KEY_OWNERS and name the guard that pins it."
    )


def test_no_OWNER_names_a_key_the_payload_no_longer_has():
    """**Direction 2 (owners).**"""
    gaps = owner_gaps(_capabilities_module().capabilities(full=True))
    assert not gaps.orphaned, (
        f"KEY_OWNERS names keys capabilities() no longer has: {gaps.orphaned}"
    )


def test_every_NAMED_OWNER_actually_EXISTS_in_this_module():
    """A name is not a guard. Every value in ``KEY_OWNERS`` must resolve to a callable here —
    otherwise "owned" could survive its owner's deletion."""
    missing = sorted({name for name in KEY_OWNERS.values()
                      if not callable(globals().get(name))})
    assert not missing, (
        f"KEY_OWNERS names guards that do not exist in {Path(__file__).name}: {missing}"
    )


def _parametrized_ids(func):
    """The ``argvalues`` of *func*'s own ``parametrize`` mark — its collected node-id set."""
    for mark in getattr(func, "pytestmark", ()):
        if mark.name == "parametrize":
            return tuple(mark.args[1])
    return ()


def test_a_NAMED_OWNER_covers_its_addresses_ONE_NODE_ID_EACH():
    """**The anti-rubber-stamp arm.** ``KEY_OWNERS`` says ``surfaces`` is owned by
    ``test_a_SURFACE_is_ANCHORED``; this asserts what that actually BUYS — that the guard's
    own ``parametrize`` argvalues equal the address set derived from the **live** payload, one
    node id per surface. Without it, "owned" could mean "named once, seventeen surfaces
    drifting inside", which is the letter of a completeness arm and the opposite of its
    purpose."""
    payload = _capabilities_module().capabilities(full=True)
    live = anchor_addresses(payload)
    surfaces = tuple(a for a in live if a.startswith("surfaces/"))
    top_level = tuple(a for a in live
                      if "/" not in a and KEY_OWNERS.get(a) == "test_a_TOP_LEVEL_INDEX_is_ANCHORED")
    assert _parametrized_ids(test_a_SURFACE_is_ANCHORED) == surfaces, {
        "collected": _parametrized_ids(test_a_SURFACE_is_ANCHORED), "live": surfaces}
    assert _parametrized_ids(test_a_TOP_LEVEL_INDEX_is_ANCHORED) == top_level, {
        "collected": _parametrized_ids(test_a_TOP_LEVEL_INDEX_is_ANCHORED), "live": top_level}


# ---- the arm's own red proofs, in-process and injectable (the exemplar's shape) ---- #

#: A HERMETIC specimen table for the three gap proofs below. Deliberately not the live
#: measurement: a proof of the guard function's own behaviour must not itself redden when a
#: plant moves the real payload — otherwise the AC2 transcripts would be full of noise from
#: tests that are not detecting the plant, only reacting to it.
_SPECIMEN_PINS = {
    WHOLE_PAYLOAD: (10, "a" * 64),
    "docs": (2, "b" * 64),
    "surfaces/one": (3, "c" * 64),
    "surfaces/two": (4, "d" * 64),
}


def test_the_pin_arm_bites_RED_on_an_UNPINNED_ADDRESS():
    """Direction 1, proven on the SAME function that guards — not a look-alike. This is audit
    B § T1 § Risk's named failure shape: *a leaf not covered by any localized guard drifts and
    the auto-regenerated tripwire silently blesses it.*"""
    measured = dict(_SPECIMEN_PINS)
    measured["surfaces/a-brand-new-surface"] = (1, "0" * 64)
    gaps = pin_gaps(measured, _SPECIMEN_PINS)
    assert gaps.unpinned == ["surfaces/a-brand-new-surface"]
    assert not gaps.orphaned and not gaps.moved


def test_the_pin_arm_bites_RED_on_an_ORPHANED_PIN():
    """Direction 2, proven."""
    pinned = dict(_SPECIMEN_PINS)
    pinned["surfaces/a-surface-that-was-deleted"] = (1, "0" * 64)
    gaps = pin_gaps(_SPECIMEN_PINS, pinned)
    assert gaps.orphaned == ["surfaces/a-surface-that-was-deleted"]
    assert not gaps.unpinned and not gaps.moved


def test_the_pin_arm_bites_RED_on_a_MOVED_ADDRESS():
    """The drift direction — and note it is the *localized* address that is reported, which is
    the whole point of the redesign: the failure names the surface, not "the payload"."""
    pinned = dict(_SPECIMEN_PINS)
    byte_length, digest = pinned["surfaces/two"]
    pinned["surfaces/two"] = (byte_length + 1, digest)
    gaps = pin_gaps(_SPECIMEN_PINS, pinned)
    assert gaps.moved == ["surfaces/two"]
    assert not gaps.unpinned and not gaps.orphaned


#: A HERMETIC key/owner pair for the two ownership proofs below — same reasoning as
#: :data:`_SPECIMEN_PINS`: a proof of the guard function's behaviour must not react to a plant
#: that moves the real payload, or the AC2/AC3 transcripts fill with noise.
_SPECIMEN_PAYLOAD = {"alpha": {}, "beta": {}}
_SPECIMEN_OWNERS = {"alpha": "test_alpha_is_ANCHORED", "beta": "test_beta_is_ANCHORED"}


def test_the_owner_arm_bites_RED_on_an_UNOWNED_KEY():
    """Direction 1 (owners), proven on the SAME function that guards: a top-level key with no
    named owner reddens."""
    payload = dict(_SPECIMEN_PAYLOAD, a_brand_new_top_level_key={})
    gaps = owner_gaps(payload, _SPECIMEN_OWNERS)
    assert gaps.unowned == ["a_brand_new_top_level_key"]
    assert not gaps.orphaned


def test_the_owner_arm_bites_RED_on_an_ORPHANED_OWNER():
    """Direction 2 (owners), proven: an owner whose key vanished reddens. This is the shape
    LD-475's key collapse (wave 2) will take, which is why the arm derives the live set from
    the payload instead of hard-coding it."""
    owners = dict(_SPECIMEN_OWNERS, a_key_that_was_collapsed="test_a_TOP_LEVEL_INDEX_is_ANCHORED")
    gaps = owner_gaps(_SPECIMEN_PAYLOAD, owners)
    assert gaps.orphaned == ["a_key_that_was_collapsed"]
    assert not gaps.unowned


def test_the_completeness_arm_GREENS_on_the_truth(measured_addresses):
    payload = _capabilities_module().capabilities(full=True)
    assert pin_gaps(measured_addresses, ANCHOR_PIN) == ([], [], [])
    assert owner_gaps(payload) == ([], [])


# ---- the two no-op refusal shapes: a substitution that silently does nothing ---- #

def test_version_normalised_REFUSES_a_payload_with_no_version_key():
    """``capabilities_anchor.py:version_normalised``'s refusal, still biting after the
    redesign. Feed it the payload that would make the substitution a no-op and watch it
    refuse — *"the substitution silently doing nothing is exactly how this guard would rot
    into a tautology."*"""
    payload = {k: v for k, v in _capabilities_module().capabilities(full=True).items()
               if k != "version"}
    with pytest.raises(AssertionError, match="lost its top-level `version` key"):
        version_normalised(payload)


def test_release_dates_normalised_REFUSES_a_payload_where_NOTHING_MATCHED():
    """The sibling refusal, still biting. Strip every dated release heading out of
    ``docs[…]["sections"]`` — the substitution then finds nothing, which is the no-op the
    assertion exists to refuse."""
    payload = copy.deepcopy(_capabilities_module().capabilities(full=True))
    for doc in payload["docs"].values():
        doc["sections"] = []
    with pytest.raises(AssertionError, match="the date normalisation found nothing"):
        release_dates_normalised(payload)


def test_release_dates_normalised_STILL_SUBSTITUTES_on_the_real_payload():
    """The other half — the refusal above must not be the only thing keeping this function
    honest. On the real payload the substitution actually fires."""
    payload = _capabilities_module().capabilities(full=True)
    normalised = release_dates_normalised(payload)
    assert ANCHOR_DATE in json.dumps(normalised, default=str, sort_keys=True)
    assert ANCHOR_DATE not in json.dumps(payload, default=str, sort_keys=True)


# ---- the teeth: a re-anchor without a disclosed capability change is a defect ---- #

@private_tree.dev_record
def test_the_PIN_is_DISCLOSED_in_the_acknowledgment_ledger():
    """**The standing rule, mechanised (LD-530).** It used to be a sentence in a comment; it
    is now this assertion. The newest row of
    ``dev/capabilities-anchor-ledger.md``'s disclosure table must carry the pin's own figures,
    so a re-cut with no disclosure beside it is red — and
    ``./scripts/reanchor-capabilities.sh`` (in the dev repo) writes both in one invocation, which is why the
    honest path is also the cheap one."""
    rows = ledger_rows()
    assert rows, f"{LEDGER_PATH.name} carries no disclosure row"
    newest = rows[-1]
    assert (newest.payload_bytes, newest.payload_sha256) == ANCHOR_PIN[WHOLE_PAYLOAD], (
        f"the pin is {ANCHOR_PIN[WHOLE_PAYLOAD]} but the newest ledger row "
        f"({newest.issue}, {newest.date}) discloses "
        f"({newest.payload_bytes}, {newest.payload_sha256}). A re-anchor without a disclosed "
        f"capability change behind it is a defect — re-cut with "
        f"./scripts/reanchor-capabilities.sh (in the dev repo), which writes both."
    )


@private_tree.dev_record
def test_every_LEDGER_ROW_is_well_formed():
    """A disclosure that does not say who and why is not a disclosure."""
    offenders = [
        row for row in ledger_rows()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.date)
        or not re.fullmatch(r"LD-\d+", row.issue)
        or len(row.why) < 20
        or not re.fullmatch(r"[0-9a-f]{64}", row.payload_sha256)
    ]
    assert offenders == [], offenders


@private_tree.citations
def test_the_REGENERATION_PATH_is_a_COMMITTED_INVOCABLE_ARTIFACT():
    """AC1(a): a re-cut recipe that lives only in a handoff is not a regeneration path. This
    runs the committed script's ``--check`` mode and requires it to agree with the pin — so
    the artifact is *exercised* by the suite, not merely present in it."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "reanchor-capabilities.sh"
    assert script.exists() and script.stat().st_mode & 0o111, script
    proc = subprocess.run([str(script), "--check"], capture_output=True, text=True,
                          cwd=str(script.parent.parent))
    assert proc.returncode == 0, (
        "./scripts/reanchor-capabilities.sh --check reports the pin does not match the tree:\n"
        f"{proc.stdout[-3000:]}{proc.stderr[-2000:]}"
    )


def test_NO_hand_authored_whole_payload_constant_survives_in_the_anchor_files():
    """The regression guard for the tax itself. The three anchor test modules may not carry a
    six-digit byte constant or a 64-hex payload digest of their own again: the pin is
    generated, and re-introducing a hand-cut whole-payload freeze beside it is how the three
    re-derivations per landing would come back."""
    tests_dir = Path(__file__).resolve().parent
    offenders = {}
    for name in ("test_capabilities_package_split.py", "test_base_field_vocabulary.py",
                 "test_base_person_chat_addressability.py"):
        tree = ast.parse((tests_dir / name).read_text(encoding="utf-8"), filename=name)
        hits = [
            (node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and ((isinstance(node.value, int) and not isinstance(node.value, bool)
                  and 10 ** 5 <= node.value < 10 ** 7)   # spelled as powers so this
                 # guard's own bounds are not six-digit literals it would flag

                 or (isinstance(node.value, str)
                     and re.fullmatch(r"[0-9a-f]{64}", node.value)
                     and node.value != _BASELINE_DOCSTRING_SHA256))
        ]
        if hits:
            offenders[name] = hits
    assert offenders == {}, (
        "a hand-authored whole-payload byte count or payload digest is back in an anchor "
        f"file: {offenders}. The pin is GENERATED — {RECUT}."
    )
