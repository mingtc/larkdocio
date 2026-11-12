"""THE VERSION- AND RELEASE-DATE-NORMALISED CAPABILITIES ANCHOR — one seam, no second
definition (LD-316, extended by LD-452).

Why this module exists
----------------------
``capabilities()``'s canonical JSON carries ``"version": "<the installed version>"`` as one
top-level leaf. Two files freeze that serialization by digest — the AC4 gate in
``tests/test_capabilities_package_split.py`` and the subtraction guard in
``tests/test_base_field_vocabulary.py`` — and **a release cut moved the digest under both of
them**: ``scripts/release.sh`` runs its gates BEFORE it bumps the version (its header, gate b
= step 3, the bump = step 7), so the v1.27.0 commit reddened the trunk by construction.

**The fix is to anchor the payload MINUS its one version leaf.** Every other byte stays pinned
exactly as before — the digest is still the whole-output digest, not a subset or a "shape"
check — but the one leaf that a release is *supposed* to move is replaced by a constant before
hashing. What the anchors lose is nothing they were built to catch: a version bump was never a
capability change, and the anchors' own standing rule ("a re-anchor without a disclosed
capability change behind it is a defect") could never be satisfied by one.

The leaf is not dropped, it is **substituted** — with :data:`ANCHOR_VERSION`, which is longer
than any real version string, so the byte-length arm keeps biting on the key's presence and
position too. The *real* version leaf is pinned separately, and more strongly than a frozen
literal ever pinned it: ``payload["version"] == larkdocio.__version__``.

The release-heading DATE joins it (LD-452)
-----------------------------------------
LD-443 made a **second** leaf mutable by the cut ritual and by nothing else: both release
documents' newest ``## [X.Y.Z] — YYYY-MM-DD`` heading is re-dated at the cut (``release.sh``
gate f — the header date may not be older than the newest date in its own body). LD-414's
``<accessor>_sections`` convention projects every such heading into
``capabilities()["docs"][…]["sections"]`` as ``heading`` **and** ``slug``, so that one
mandatory edit moved this digest four times over, mid-ritual, after the gates had run — the
identical failure mode LD-316 fixed for ``version``, from a different leaf.

So the anchor normalises the **date portion of a release heading** the same way:

* **only the date** — the ``X.Y.Z`` inside the heading is left exactly as it is. A release
  *section* appearing, vanishing or being re-numbered is a real content change and gets the
  re-anchor ceremony; only re-dating an existing one is tolerated.
* **only the section-index rows** — ``heading`` and ``slug`` under ``docs[…]["sections"]``.
  A date anywhere else in the payload (a note, an evidence line) is untouched and still
  hashed.
* **the payload itself is not changed.** ``capabilities()`` keeps reporting the real dates;
  a consumer may still look a release up by its dated name. Only this derivation substitutes.
* **it may not be a silent no-op** — :func:`release_dates_normalised` refuses a payload in
  which it finds nothing to substitute, for the same reason ``version_normalised`` refuses a
  payload with no ``version`` key: that is exactly how a guard rots into a tautology.
* the real dates are **pinned harder elsewhere**, as the version leaf is — against the
  shipped documents' own headings, in
  ``tests/test_capabilities_package_split.py::test_the_REAL_release_heading_dates_are_pinned_to_the_SHIPPED_DOCUMENTS``.

A PER-ROW BYTE COST IS NOT PORTABLE BETWEEN ANCHORS (LD-490) — CONCLUSION SUPERSEDED IN
PART BY LD-530; THE REASON BELOW IS UNCHANGED AND STAYS
----------------------------------------------------------------------------------------
**THE REASON, verbatim and load-bearing** (CLAUDE.md § House rules § Supersession: preserve
the reason, supersede only the conclusion — a struck reason is how a settled argument gets
re-litigated). Read this paragraph before you touch anything that serialises the payload:

Because of that date substitution, **one dated release row does not cost the same number of
bytes on a normalised anchor as it does on an anchor over the RAW payload** — and the raw kind
exists: ``tests/test_base_person_chat_addressability.py``'s ``_PAYLOAD_WITHOUT_THE_NOTE``
freezes ``json.dumps(payload, default=str, sort_keys=True)`` with no normalisation at all.
:data:`ANCHOR_DATE` (``0000-00-00-anchor``, 17 chars) replaces a ``YYYY-MM-DD`` (10 chars) in
**both** the row's ``heading`` and its ``slug``, so the same row is **+14** bytes here.

Measured across LD-480's two trees (before and after), for the ``[1.36.0]`` row added
to each of ``changelog()`` and ``release_notes()``: **84** bytes each on the raw anchor
(394,317 → 394,648, ``163 + 84 + 84 = 331``) and **98** bytes each here (399,254 → 399,613,
``163 + 98 + 98 = 359``). The row's own canonical JSON is 82 bytes raw, plus the ``, ``
separator.

**The ORIGINAL CONCLUSION (LD-490, 2026-08-15): never copy a per-leaf figure from one anchor's
ledger into another's — re-measure on the anchor you are re-cutting.** LD-480 copied the ``98``
into the raw anchor's ledger and left a sum that did not hold (``394,317 + 359 = 394,676``, not
the measured 394,648); LD-490 derived the real decomposition and wrote it there. It is the date
substitution, **not** ``ensure_ascii``, that separates the two anchors: all three anchor
serialisations call ``json.dumps(payload, default=str, sort_keys=True)`` with ``ensure_ascii``
at its default, so a non-ASCII character escapes identically on every one of them.

**THE CONCLUSION IS SUPERSEDED IN PART (LD-530, 2026-08-20), and only its conclusion.** The
rule told a human *which* anchor to re-measure on, because there were three anchors under two
serialisations and the arithmetic was hand-authored. LD-530 removed the premise rather than
the rule: there is now **one** whole-payload tripwire, **one** serialisation for every pin
(:func:`measure_addresses`, always the version- and release-date-normalised payload), and
**no hand-authored byte arithmetic anywhere** — ``scripts/reanchor-capabilities.sh`` (in the dev repo; :data:`RECUT` says how to
re-cut without it) measures every address on the tree in front of it and writes the numbers itself. So the *hazard* the
rule named — carrying a figure from one ledger to another — is now unreachable rather than
forbidden: there is no second ledger to carry a figure from, and no figure a human types.

**What is still true, and is why the reason above is kept rather than struck:**

* the raw serialisation still exists and still differs from the normalised one
  (:func:`canonical_json` vs :func:`anchor_blob`) — that difference is what
  ``test_the_ANCHOR_IS_INVARIANT_UNDER_A_VERSION_BUMP`` and its release-date sibling use to
  prove the substitutions are not no-ops, so a future reader comparing a raw byte count to a
  normalised one is still comparing two different things;
* the ``+84`` raw / ``+98`` normalised measurement above is the evidence for that, and it is
  the only measurement of it this repo has ever made. Re-deriving it would cost two trees and
  four serialisations; that is why it is preserved verbatim rather than summarised.

**The landing-day (2026-08-20) merged-tree re-derivations that were part of this reason** —
the ``LANDED 2026-08-20 atop …`` annotations that stood in all three anchor ledgers, each
saying in terms *"the LD-490 rule: derive on the anchor being cut"* — are preserved verbatim
in [`dev/capabilities-anchor-ledger.md`](../dev/capabilities-anchor-ledger.md) § "Preserved
history", which is where LD-530 moved the anchor ledgers wholesale. They were not struck; they
were relocated to the one file that is now the anchor's history.

THE LD-530 REGIME — ONE TRIPWIRE, LOCALIZED PINS, A BIDIRECTIONAL COMPLETENESS ARM
----------------------------------------------------------------------------------
Three whole-payload freezes under two serialisations, each with a hand-authored byte-arithmetic
essay beside it, cost every ``capabilities()``-moving landing three re-derivations — twenty
consecutive landings paid it, and the essays reached 77% of the biggest anchor file. LD-530
replaced them with:

* **one generated pin table**, :data:`ANCHOR_PIN` — the whole payload under
  :data:`WHOLE_PAYLOAD`, plus one row per **address** (:func:`anchor_addresses`: every
  top-level key, with ``surfaces`` expanded per surface). Regenerated, never hand-typed, by
  ``scripts/reanchor-capabilities.sh`` (in the dev repo), which also writes the
  acknowledgment-ledger row. The
  diff of a re-cut therefore *names the addresses that moved* — the disclosure is the diff.
* **localized guards** in ``tests/test_capabilities_package_split.py``, one node id per
  address, so a change to one surface reddens that surface's own pin and says which.
* **a bidirectional completeness arm** (:func:`pin_gaps`, :func:`owner_gaps`) modelled on
  ``tests/test_permissions_registry.py``: an address with no pin or no named owner reddens,
  and a pin or owner whose address has vanished reddens. The address set is **derived from the
  payload at runtime**, so a new key or a new surface cannot arrive uncovered.
* **the teeth, mechanised**: the standing rule *"a re-anchor without a disclosed capability
  change behind it is a defect"* used to be a comment. It is now
  ``test_the_PIN_is_DISCLOSED_in_the_acknowledgment_ledger`` — the pin must equal the newest
  row of [`dev/capabilities-anchor-ledger.md`](../dev/capabilities-anchor-ledger.md), so a
  re-cut with no disclosure is red.

Keeping the rule importable from one module is the same discipline ``tests/release_versions.py``
ships under: two callers, one definition, no drift.
"""
import copy
import hashlib
import json
import re
from collections import namedtuple
from pathlib import Path

#: The substitute written over ``payload["version"]`` before hashing. Deliberately NOT a
#: parseable version (nothing may mistake it for one), and deliberately longer than a real
#: ``X.Y.Z`` — the anchored byte count therefore moves if the key ever disappears.
ANCHOR_VERSION = "0.0.0-anchor"


def version_normalised(payload):
    """A deep copy of *payload* with its one top-level ``version`` leaf substituted.

    Refuses a payload with no ``version`` key: the substitution silently doing nothing is
    exactly how this guard would rot into a tautology.
    """
    assert "version" in payload, "capabilities() lost its top-level `version` key"
    normalised = copy.deepcopy(payload)
    normalised["version"] = ANCHOR_VERSION
    return normalised


#: The substitute written over the DATE portion of a release heading (and of its slug) before
#: hashing. Deliberately NOT a parseable date, and deliberately longer than ``YYYY-MM-DD`` —
#: so the byte-length arm keeps biting on a row appearing or disappearing.
ANCHOR_DATE = "0000-00-00-anchor"

#: A release row's ``heading`` (``[1.33.0] — 2026-08-13``) and its ``slug``
#: (``1-33-0-2026-08-13``). The ``X.Y.Z`` half is captured only to be written back verbatim.
_RELEASE_HEADING = re.compile(r"^(\[\d+\.\d+\.\d+\] — )(\d{4}-\d{2}-\d{2})$")
_RELEASE_SLUG = re.compile(r"^(\d+-\d+-\d+-)(\d{4}-\d{2}-\d{2})$")


def release_dates_normalised(payload):
    """A deep copy of *payload* with every release row's date substituted.

    Walks only ``payload["docs"][…]["sections"]`` and only the rows whose ``heading`` /
    ``slug`` is a **dated release name**; everything else — including a date sitting anywhere
    else in the payload — is left to be hashed. Refuses a payload in which nothing matched,
    because a substitution that silently does nothing is how this guard rots into a tautology.
    """
    normalised = copy.deepcopy(payload)
    substitutions = 0
    for doc in (normalised.get("docs") or {}).values():
        for row in (doc.get("sections") or ()) if isinstance(doc, dict) else ():
            for key, pattern in (("heading", _RELEASE_HEADING), ("slug", _RELEASE_SLUG)):
                match = pattern.match(str(row.get(key, "")))
                if match:
                    row[key] = match.group(1) + ANCHOR_DATE
                    substitutions += 1
    assert substitutions, (
        "capabilities() carries no dated release heading in any docs[…]['sections'] index — "
        "the date normalisation found nothing to substitute, so it is now a no-op"
    )
    return normalised


def canonical_json(payload):
    """The one canonical serialization every anchor here is measured in."""
    return json.dumps(payload, default=str, sort_keys=True).encode("utf-8")


def anchor_blob(payload):
    """The version- and release-date-normalised canonical serialization — what the anchors
    freeze. Both leaves a *cut* is supposed to move are substituted; every other byte of the
    whole output stays pinned exactly."""
    return canonical_json(release_dates_normalised(version_normalised(payload)))


def anchor_digest(payload):
    """``(sha256_hexdigest, byte_length)`` of :func:`anchor_blob`."""
    blob = anchor_blob(payload)
    return hashlib.sha256(blob).hexdigest(), len(blob)


#: The probe body the cold-interpreter arm runs, so the child process measures the payload
#: through THIS module rather than through a hand-copied second implementation of the rule.
COLD_PROBE = (
    "import sys\n"
    "sys.path.insert(0, {tests_dir!r})\n"
    "import larkdocio\n"
    "from capabilities_anchor import anchor_digest\n"
    "digest, length = anchor_digest(larkdocio.capabilities(full=True))\n"
    "print(digest, length, larkdocio.__version__)\n"
)


# --------------------------------------------------------------------------- #
# THE ADDRESS SET — derived from the payload at RUNTIME, never hard-coded.     #
# --------------------------------------------------------------------------- #

#: The pin-table key for the whole normalised payload — the ONE tripwire. Deliberately not a
#: legal payload key (no ``capabilities()`` key may start with ``@``), so it can never collide
#: with an address however the payload is reshaped.
WHOLE_PAYLOAD = "@payload"

#: The one top-level key that is expanded per member rather than pinned whole. One guard
#: nominally owning ``surfaces`` while seventeen surfaces drift inside it would satisfy the
#: letter of a completeness arm and defeat its purpose, so ``surfaces`` is the granularity
#: exception: each surface is its own address, its own pin and its own node id.
EXPANDED_KEYS = ("surfaces",)


def anchor_addresses(payload):
    """The addresses the localized guards must cover — **derived from *payload* at runtime**.

    Every top-level key is an address, except that each key in :data:`EXPANDED_KEYS` is
    replaced by one address per member (``surfaces/docx-read`` and friends). Nothing here is
    a literal key list: LD-475 collapses payload keys in wave 2, and a hard-coded set would
    let the completeness arm silently shrink instead of reddening.
    """
    addresses = []
    for key in sorted(payload):
        value = payload[key]
        if key in EXPANDED_KEYS and isinstance(value, dict):
            addresses.extend(f"{key}/{member}" for member in sorted(value))
        else:
            addresses.append(key)
    return tuple(addresses)


def address_value(payload, address):
    """The sub-object *address* names inside *payload*."""
    if address == WHOLE_PAYLOAD:
        return payload
    key, _, member = address.partition("/")
    return payload[key][member] if member else payload[key]


def _pin(obj):
    blob = canonical_json(obj)
    return len(blob), hashlib.sha256(blob).hexdigest()


def measure_addresses(payload):
    """``{address: (bytes, sha256)}`` for the whole payload and every address.

    **One serialisation for every row** — the version- and release-date-normalised payload,
    normalised ONCE here and then sliced, which is what makes the LD-490 hazard (a figure
    carried between two differently-serialised anchors) structurally unreachable.
    """
    normalised = release_dates_normalised(version_normalised(payload))
    table = {WHOLE_PAYLOAD: _pin(normalised)}
    for address in anchor_addresses(normalised):
        table[address] = _pin(address_value(normalised, address))
    return table


#: ``unpinned`` — an address the live payload has and the pin table does not (audit B's named
#: failure shape: *a leaf not covered by any localized guard drifts and the auto-regenerated
#: tripwire silently blesses it*). ``orphaned`` — a pin whose address has vanished.
#: ``moved`` — an address whose measurement differs from its pin.
PinGaps = namedtuple("PinGaps", "unpinned orphaned moved")


def pin_gaps(measured, pinned):
    """Bidirectional coverage of the pin table, plus the drift. Pure, injectable, red-provable
    in-process — the ``tests/test_permissions_registry.py::coverage_gaps`` pattern."""
    return PinGaps(
        unpinned=sorted(set(measured) - set(pinned)),
        orphaned=sorted(set(pinned) - set(measured)),
        moved=sorted(a for a in set(measured) & set(pinned) if measured[a] != pinned[a]),
    )


# --------------------------------------------------------------------------- #
# THE OWNERSHIP DECLARATION — every top-level key answers to a NAMED guard.    #
# --------------------------------------------------------------------------- #

#: Top-level payload key -> the name of the guard in
#: ``tests/test_capabilities_package_split.py`` that owns it. Declared, not derived: a derived
#: mapping would make direction 1 vacuously true, which is the one thing the completeness arm
#: exists to prevent. The two parametrized owners are held to their **effective** granularity
#: by ``test_a_NAMED_OWNER_covers_its_addresses_ONE_NODE_ID_EACH``, which reads their
#: ``parametrize`` argvalues and requires them to equal the runtime-derived address set — so
#: "owned" cannot mean "named once and drifting inside".
KEY_OWNERS = {
    "docs": "test_a_TOP_LEVEL_INDEX_is_ANCHORED",
    "entry_points": "test_a_TOP_LEVEL_INDEX_is_ANCHORED",
    "flags": "test_a_TOP_LEVEL_INDEX_is_ANCHORED",
    "safety_contracts": "test_a_TOP_LEVEL_INDEX_is_ANCHORED",
    "workflows": "test_a_TOP_LEVEL_INDEX_is_ANCHORED",
    # LD-475's two provenance catalogs — the prose every permission row rests on, carried once
    # at the top level instead of re-typed per operation. They arrived here rather than in a
    # hand-edited pin because this arm is bidirectional: an unowned new key reddens, which is
    # exactly what it did when they first appeared.
    "scope_evidence": "test_a_TOP_LEVEL_INDEX_is_ANCHORED",
    "unknown_requirements": "test_a_TOP_LEVEL_INDEX_is_ANCHORED",
    "surfaces": "test_a_SURFACE_is_ANCHORED",
    # ``version`` is the one address whose pin is a CONSTANT by construction — the
    # normalisation substitutes ANCHOR_VERSION for it, so its pin can never move and a pin
    # alone would be a tautology. Its owner asserts the real leaf instead, against the
    # installed version, which is the stronger claim (see the module docstring's opening).
    "version": "test_the_version_leaf_is_pinned_to_the_INSTALLED_version",
}

#: ``unowned`` — a live top-level key no entry in :data:`KEY_OWNERS` names. ``orphaned`` — an
#: entry naming a key the payload no longer has.
OwnerGaps = namedtuple("OwnerGaps", "unowned orphaned")


def owner_gaps(payload, owners=None):
    """Bidirectional ownership coverage. ``owners`` is injectable so both directions can be
    red-proved in-process as well as by a planted payload change."""
    declared = KEY_OWNERS if owners is None else owners
    live = set(payload)
    return OwnerGaps(
        unowned=sorted(live - set(declared)),
        orphaned=sorted(set(declared) - live),
    )


# --------------------------------------------------------------------------- #
# THE ACKNOWLEDGMENT LEDGER — the teeth, mechanised.                          #
# --------------------------------------------------------------------------- #

#: The acknowledgment ledger LD-530 moved the three anchor essays into, and the file
#: ``scripts/reanchor-capabilities.sh`` appends a row to on every re-cut. The standing rule
#: "a re-anchor without a disclosed capability change behind it is a defect" is enforced
#: against it: the newest row's payload figures must equal :data:`ANCHOR_PIN`'s.
LEDGER_PATH = Path(__file__).resolve().parents[1] / "dev" / "capabilities-anchor-ledger.md"

#: The one machine-read table in the ledger. Everything below the marker is prose and
#: preserved history; everything in the table is a disclosure row.
LEDGER_TABLE_MARKER = "<!-- ANCHOR-LEDGER-TABLE -->"

LedgerRow = namedtuple("LedgerRow", "date issue addresses why payload_bytes payload_sha256")


def ledger_rows(text=None):
    """Every disclosure row of the acknowledgment ledger, oldest first.

    Reads only the pipe table under :data:`LEDGER_TABLE_MARKER`, so the preserved-history
    prose below it can say anything without becoming a claim this guard checks.
    """
    if text is None:
        text = LEDGER_PATH.read_text(encoding="utf-8")
    body = text.split(LEDGER_TABLE_MARKER, 1)[-1]
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if rows:
                break          # the table ended; the prose below is not a row
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 6 or set(cells[0]) <= set("- :"):
            continue           # the header rule row
        if cells[0] == "Date":
            continue           # the header itself
        rows.append(LedgerRow(cells[0], cells[1], cells[2], cells[3],
                              int(cells[4].replace(",", "")), cells[5]))
    return tuple(rows)


#: How to re-cut the pin, for a failure message. The script lives in the maintainers' repository
#: only (LD-708, Y10), so the message also gives the by-hand route a clone can take.
RECUT = (
    "./scripts/reanchor-capabilities.sh (in the dev repo) --issue LD-NNN --why '<one line>'; "
    "without that script, replace the block between the GENERATED ANCHOR PIN fences in "
    "tests/capabilities_anchor.py with measure_addresses(larkdocio.capabilities(full=True)), "
    "one '\"<address>\": (<bytes>, \"<sha256>\"),' row per address"
)


# --------------------------------------------------------------------------- #
# THE GENERATED PIN TABLE. Do not hand-edit; do not hand-compute a delta.      #
#                                                                             #
#   ./scripts/reanchor-capabilities.sh --issue LD-NNN --why "<one line>"       #
#                                                                             #
# regenerates the block below FROM THE TREE IN FRONT OF IT and appends the     #
# matching disclosure row to dev/capabilities-anchor-ledger.md. There is no    #
# byte arithmetic to do, and none may be written: the script measures.         #
# --------------------------------------------------------------------------- #

# --- BEGIN GENERATED ANCHOR PIN ---
ANCHOR_PIN = {
    "@payload":                           (339760, "b6273b3da329a2196061ccacaadf010db725345394292051c99f6e82147cc4d5"),
    "docs":                               (27518, "6cb414c027ef1f8e78ea85fd7eff552f49a3a1bf6bd43c39fb88fe4bc5c7cab9"),
    "entry_points":                       (6853, "4041d528e418a3584f0a29530cd53dc13ab504c5abc294b4d5f6b46777053320"),
    "flags":                              (10475, "c386b91c7f49807bb66aac66a0df4d129bff82315c8fc873fbbfa252e0b7966c"),
    "safety_contracts":                   (36523, "af4a87cbac2dee765eeb01f53d6ecceee3af9c976ada8b31464e522a31f1394c"),
    "scope_evidence":                     (7110, "c3eef8f3480062a21bfd8d14ea15d152b03d048c4a755a7485055b940ee98333"),
    "surfaces/base-comments-read":        (2865, "c376f6748ad3d836b0b766070572b7b3c4f25fff83ced24e6dd1bb9ad8e1c214"),
    "surfaces/base-embedded-deep-read":   (2495, "f9449435f644a4d2a5970a6b15cc59e763f77ef32c8d5c2c481afd0b6dfeebde"),
    "surfaces/base-read":                 (17415, "13bc823f2242c8265c5468409d55628ac4a223fa0ea00f3bf4888708bc1e1233"),
    "surfaces/base-schema-write":         (24280, "e0a6234d7d06776068a1a873ecd5521a8bc4e3f172d3bd6bf792e53516e719e1"),
    "surfaces/base-write":                (13907, "75e6727d182e10792fef5cb078761552f5cd185225d9024f85dc17e0052d6131"),
    "surfaces/contacts-read":             (7335, "8d8802a0efed0ac69ded3995f668e4f735877d39b8296e3a539e1d7e9f6c824f"),
    "surfaces/docx-comments-read":        (6431, "5ace6cfb68caa446ef8640993b87af7ec7100af9c2dd72d13113e10d8ec531d0"),
    "surfaces/docx-read":                 (25865, "2bcd2ea92b13d6e858dfb949d72b2759641a9ebc702b611b4cf8f0a0b7f40a9d"),
    "surfaces/docx-write":                (68647, "9d2e6a7775cc803670b497ce3952a5d7beeb32d58b9807c9f24db6e40ca95b12"),
    "surfaces/drive-access-write":        (7431, "30e0b40fb2b4c834c18d59b762dea98e00ba0e5fb0b878f2d1a71cba1e6e6188"),
    "surfaces/drive-files-write":         (7165, "b4ab425b435aea117d7525b0b53bcb9695ea7076cea6a5ff9200d18526804b6c"),
    "surfaces/drive-folders-write":       (3515, "5fd0b8237cdb49d2c3c017114ee77171aaf29d414fcffd2e8a635818b28ebfa9"),
    "surfaces/drive-read":                (9683, "77d51a7c62b18712f717380606571b2b3c2afe801f5f1711ee0a12c5c3adb834"),
    "surfaces/drive-versions-write":      (2596, "4c419151849f25e5592649e23e558fc12a702461ec15460b2431126c723cf495"),
    "surfaces/sheets-embedded-deep-read": (2092, "49de746edb713ee5fab6d40c1126f5f1760de2fdeac0a49694b5e5a459eca16e"),
    "surfaces/sheets-read":               (11042, "0cd7485f362463245fda7ee58d43f502989fdbd2568f04c5df3405cfa9819173"),
    "surfaces/sheets-write":              (13307, "62e8ed2df9627074e999c21dd11addb1854f9204707c3be2fdd10993bc7a0343"),
    "unknown_requirements":               (22430, "427044c1a218d113db79e0531351f11db6fa06a9e7391af1f0ad5a25953d874a"),
    "version":                            (14, "6af2e06b2a0e6b9fcda1bbd8e46343401e19d3facc4ba8f918f439d87b5717e1"),
    "workflows":                          (2256, "fb8f7c6a4494d068311a15881694b0dd2df4627023924c425dad27e03d7786e4"),
}
# --- END GENERATED ANCHOR PIN ---
