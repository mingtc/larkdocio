"""LD-370 — THE CONFORMANCE TIER's meta-guard: the tier cannot silently evaporate.

The tier is a **lens, not a gate**. Nothing here selects on ``-m conformance`` as a
release or QA gate; ``verify.sh`` is untouched and the full suite remains the gate
exactly as before. What this module pins is that the *lens still exists*:

* the doctrine document (``process/doctrine/conformance-tier.md``) carries the
  definition **verbatim**, its operational question, worked examples in both
  directions naming real tests, and the marking convention for new tests;
* the ``conformance`` marker is registered and points at that document;
* **selection is not perturbed** — ``addopts`` still carries the exact default ``-m``
  expression it carried before the tier existed, and the marker appears nowhere in it;
* the marked tier is **non-empty and above a floor**, per declared family, so a family
  that gets quietly unmarked reddens with a message naming it;
* the marker **overlays** the ring markers rather than replacing them: every ``live`` /
  ``live_write`` test is conformance-tier, is still selected by its ring, and is still
  deselected by default.

The census is taken by a real ``--collect-only`` child run rather than by re-deriving
pytest's marker resolution from source text: a static re-implementation would drift from
what pytest actually selects, and *what pytest actually selects* is the whole claim.
(The child-process pattern, and the ``PYTEST_XDIST_*`` scrubbing it needs so a guard
running on a worker does not read the parent's identity, follow
``tests/test_parallel_offline_suite.py``.)
"""

import os
import re
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pytest
import private_tree  # noqa: E402  (LD-685)

ROOT = Path(__file__).resolve().parent.parent
DOCTRINE = ROOT / "process" / "doctrine" / "conformance-tier.md"
PYPROJECT = ROOT / "pyproject.toml"
VERIFY_SH = ROOT / "scripts" / "verify.sh"

# The default `-m` expression, verbatim. AC3: the tier must not perturb selection, so
# this is pinned as a STRING — a tier that edits what runs by default has changed the
# gate, which is the one thing this issue was told not to do.
EXPECTED_ADDOPTS = "-q -n auto -m 'not live and not zoo and not live_write'"

_NODE_ID_RE = re.compile(r"^(tests/[\w./-]+\.py)::")


@lru_cache(maxsize=None)
def _collect(markexpr, *paths):
    """Node ids collected by a child ``pytest --collect-only`` under the repo's own config."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST")}
    argv = [sys.executable, "-m", "pytest", "--collect-only", "-n0",
            "-p", "no:cacheprovider", *paths]
    if markexpr is not None:
        argv += ["-m", markexpr]
    res = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
    assert res.returncode in (0, 5), (          # 5 = "no tests collected", a legal answer
        f"collection child failed for -m {markexpr!r}:\n{res.stdout}\n{res.stderr}")
    return tuple(line.strip() for line in res.stdout.splitlines()
                 if _NODE_ID_RE.match(line.strip()))


def _by_file(node_ids):
    return Counter(_NODE_ID_RE.match(n).group(1).split("/", 1)[1] for n in node_ids)


# --------------------------------------------------------------------------- #
# The declared families — AC4. This table IS the "what got marked, by family"
# answer, and each entry is a family whose disappearance must redden. It is
# deliberately PARTIAL (AC5): the pass marked the obvious families, not the whole
# suite, and new tests join by the convention in the doctrine document. No suite size
# is written here — this module collects it (LD-649: the figure that stood here was 49%
# low, in a file whose whole job is counting).
# --------------------------------------------------------------------------- #
FAMILIES = {
    "golden / round-trip": [
        "test_golden.py",
        "test_sheets_golden.py",
        "test_compose_roundtrip_corpus.py",
    ],
    "capability matrix guards": [
        "test_blocks_md_matrix.py",
        "test_sheets_md_matrix.py",
        "test_base_md_matrix.py",
        "test_base_schema_matrix.py",
        "test_drive_md_matrix.py",
        "test_mermaid_rules_matrix.py",
    ],
    "front door / consumer dialect": [
        "test_front_door_doctrine.py",
        "test_front_door_truth.py",
        "test_cli_front_door_truth.py",
        "test_consumer_dialect_guard.py",
        "test_consumer_first_readme.py",
    ],
    "permissions": [
        "test_permissions_registry.py",
        "test_permissions_docs.py",
        "test_consumer_permissions_paste_ready.py",
    ],
    "release-notes consumer promises": [
        "test_release_notes.py",
        "test_release_notes_accessor.py",
        "test_shipped_notes.py",
    ],
    "refusal characterization (LD-363)": [
        "test_reconcile_refusal_characterization.py",
    ],
    # LD-389 — the url / deep-link grammars, marked PER ASSERTION (the regeneration
    # spike's own recommendation): the grammars, their returned field values, the
    # accepted shape vocabulary and the negatives are in; parameter names, docstring
    # prose, refusal wording and source-literal greps stay out. `test_url.py` is the
    # one file whose every case qualifies, so it alone carries a module-level mark.
    "url / deep links (LD-389)": [
        "test_url.py",
        "test_deep_link.py",
        "test_deep_link_negatives.py",
        "test_sheets_url_parsing.py",
        "test_drive_folder_url.py",
        "test_sheets_tab_url.py",
        # LD-379 — the docx twin: the six-kind construction table is CLICKED truth.
        "test_docx_block_url.py",
        # LD-411 — the docx EDITION link: the construction is pinned the same way, and its
        # claim is a product claim about Lark's own web client, not this project's own code
        # — click-verified on one client, one tenant (LD-419), with the other axes still
        # named unmeasured, which is why it earns the same conformance-tier treatment. The
        # disclosure-presence cases are regression-tier and stay unmarked.
        "test_docx_edition_url.py",
        # LD-396 — full-token-or-refuse: the token alphabet and the refusal it now
        # produces are the PRODUCT (a rewrite from the corpus must still refuse), so the
        # whole file qualifies and carries a module-level mark.
        "test_url_token_charset.py",
    ],
}

# The floor, and why it is a floor rather than an equality (AC6). Measured at LD-370's
# marking pass: 1518 cases — 415 golden/round-trip, 417 front door, 237 matrix guards,
# 162 release-notes, 89 permissions, 34 refusal characterization, 164 live + live_write.
# 1200 sits below that with room for ordinary churn, and above "any of the three LARGEST
# families disappeared" (losing golden or the front door lands at ~1100). An equality
# would redden on every conformance test a contributor ADDS, which is the opposite of what
# this guard wants to encourage; the per-family test below is what catches a small family
# going missing, so the total is only the coarse backstop.
#
# LD-389 re-measured it at **1642** after marking the url / deep-link family (+124). The
# floor STAYS at 1200 deliberately: it is a floor, never an equality, and its sizing rule
# is unchanged — it must sit below "the largest family vanished" (1642 - 415 golden = 1227,
# still above 1200) and above nothing in particular. Raising it to hug the new census would
# convert every future test deletion into a floor edit, which is the churn the `>=` exists
# to avoid.
TIER_FLOOR = 1200


@lru_cache(maxsize=None)
def tier():
    return _collect("conformance")


# =========================================================================== #
# AC1 — the doctrine document, with the definition VERBATIM                    #
# =========================================================================== #

VERBATIM_DEFINITION = (
    "A test is **CONFORMANCE-tier** iff it **must still pass after a full rewrite of the "
    "implementation from the corpus** — it pins the **PRODUCT** (consumer-observable "
    "contracts, measured external truths, PM/seat rulings). A test is **regression-tier** "
    "iff a rewrite may legitimately break it (it pins **THIS implementation**)."
)
VERBATIM_QUESTION = (
    'The operational question: **"if this fails after regeneration, is the product wrong, '
    'or merely different?"**'
)


def _doctrine_text():
    """The document as one whitespace-normalized line, blockquote markers stripped.

    The definition is quoted (`> `) because it is a citation of the seat's own words, so the
    `>` prefixes are markdown, not part of the text being pinned.
    """
    assert DOCTRINE.is_file(), (
        f"{DOCTRINE.relative_to(ROOT)} is missing — the marker without the doctrine is a "
        "label nobody can apply (LD-370 AC1)")
    body = DOCTRINE.read_text(encoding="utf-8")
    return " ".join(re.sub(r"^\s*>\s?", "", body, flags=re.M).split())


@private_tree.citations
def test_ac1_the_definition_lands_VERBATIM():
    text = _doctrine_text()
    for fragment in (VERBATIM_DEFINITION, VERBATIM_QUESTION):
        assert " ".join(fragment.split()) in text, (
            "the doctrine document must carry the seat's definition UNPARAPHRASED; missing:\n"
            + fragment)


@private_tree.process
def test_ac1_worked_examples_name_REAL_tests_in_both_directions():
    """An abstract doctrine nobody can apply is a FAIL — the examples must be checkable."""
    text = DOCTRINE.read_text(encoding="utf-8")
    named = {m.group(1) for m in re.finditer(r"`(tests/[\w./-]+\.py)[^`]*`", text)}
    assert len(named) >= 4, f"too few worked examples naming real test files: {sorted(named)}"
    missing = sorted(p for p in named if not (ROOT / p).exists())
    assert not missing, f"the doctrine's worked examples name files that do not exist: {missing}"

    marked_files = set(_by_file(tier()))
    conformance_examples = {p for p in named if Path(p).name in marked_files}
    regression_examples = named - conformance_examples
    assert len(conformance_examples) >= 2, (
        f"fewer than two worked examples are actually IN the tier: {sorted(named)}")
    assert len(regression_examples) >= 2, (
        f"fewer than two worked examples are actually OUT of the tier: {sorted(named)}")


@private_tree.citations
def test_ac5_the_doctrine_carries_the_marking_CONVENTION_and_owns_the_non_goal():
    text = _doctrine_text().lower()
    for phrase in ("convention", "not a complete classification"):
        assert phrase in text, (
            f"the doctrine document must state {phrase!r} — the tier grows by rule, not by "
            "sweep, and the marked total is the floor of a deliberately partial pass (AC5)")


@private_tree.citations
def test_ac10_the_doctrine_says_LENS_NOT_GATE_and_verify_sh_does_not_select_on_it():
    assert "lens, not a gate" in _doctrine_text(), (
        "the doctrine must say, in those words, that the tier is a lens and not a gate")
    for script in ("verify.sh", "release.sh"):
        body = (ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "conformance" not in body, (
            f"scripts/{script} selects on the conformance tier — the tier is a LENS; the full "
            "suite remains the QA and release gate (AC10)")


# =========================================================================== #
# AC2 / AC3 — the marker is registered, and selection is NOT perturbed         #
# =========================================================================== #

def test_ac2_the_marker_is_registered_and_points_at_the_doctrine():
    body = PYPROJECT.read_text(encoding="utf-8")
    rows = [line for line in body.splitlines() if line.strip().startswith('"conformance:')]
    assert rows, "`conformance` is not registered in pyproject.toml's `markers` (AC2)"
    assert "process/doctrine/conformance-tier.md" in rows[0], (
        "the marker description must name the doctrine document so `pytest --markers` is "
        f"self-explanatory; got: {rows[0].strip()}")


def test_ac3_the_default_selection_expression_is_UNTOUCHED():
    body = PYPROJECT.read_text(encoding="utf-8")
    assert f'addopts = "{EXPECTED_ADDOPTS}"' in body, (
        "`addopts` changed. The conformance tier must not perturb selection: it adds marker "
        "METADATA only, and the default `-m` expression is load-bearing (AC3)")
    assert "conformance" not in EXPECTED_ADDOPTS


# =========================================================================== #
# AC6 / AC4 — the tier is non-empty, above its floor, and family by family     #
# =========================================================================== #

def test_ac6_the_tier_is_NON_EMPTY_and_above_its_floor():
    total = len(tier())
    assert total > 0, (
        "`pytest -m conformance` collects nothing — the tier has evaporated entirely "
        "(LD-370 AC6)")
    assert total >= TIER_FLOOR, (
        f"the conformance tier collects {total} cases, below the floor of {TIER_FLOOR}. "
        "Something that was marked is no longer marked: compare `pytest -m conformance "
        "--collect-only` against process/doctrine/conformance-tier.md's family list. The "
        "floor is deliberately slack, so falling under it means a FAMILY went missing, not "
        "that a test was deleted.")


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_ac4_every_declared_family_is_STILL_MARKED(family):
    counts = _by_file(tier())
    missing = [name for name in FAMILIES[family] if not counts.get(name)]
    assert not missing, (
        f"the {family!r} conformance family lost members: {missing} collect no conformance "
        "cases. Either the module-level `pytestmark` was dropped, or the file was renamed "
        "without updating this guard and process/doctrine/conformance-tier.md.")


# =========================================================================== #
# AC8 — the marker OVERLAYS the ring markers without disturbing them           #
# =========================================================================== #

RING_WITNESS = "tests/test_live_write_w1_gate.py"


def test_ac8_the_whole_live_and_live_write_RINGS_are_conformance_tier():
    stragglers = _collect("(live or live_write) and not conformance")
    assert not stragglers, (
        "these live / live_write tests are not conformance-tier: "
        f"{sorted(set(_by_file(stragglers)))} — the live rings measure the real API, which is "
        "external truth a rewrite cannot legitimately change (LD-370 AC4/AC8)")


def test_ac8_a_conformance_marked_ring_test_is_still_selected_by_its_ring():
    selected = _collect("live_write", RING_WITNESS)
    assert selected, (
        f"{RING_WITNESS} collects nothing under `-m live_write` — the conformance marker "
        "REPLACED the ring marker instead of overlaying it (AC8)")


def test_ac8_a_conformance_marked_ring_test_is_still_DESELECTED_by_default():
    assert not _collect(None, RING_WITNESS), (
        f"{RING_WITNESS} is collected by a DEFAULT run — marking the ring conformance-tier "
        "has pulled credential-gated live-write tests into the offline suite (AC3/AC8)")
