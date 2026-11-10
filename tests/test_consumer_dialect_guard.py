# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE GREP GUARD — no internal issue-dialect in consumer-reaching text (LD-153 / F7).

The dogfood seat session found this repo's internal dialect leaking into text a consumer is
handed: ``plan.revision_guard_detail`` — a paragraph an agent may relay verbatim to a user —
ended in "…whenever the referenced data changes — **LD-149**", and the docstrings of public
symbols carried ``D2``/``AC3``/``S2``/``T23``/a private-set id, "the PM-adopted choice" and "the
AST guard extends over it". None of it resolves from any surface a consumer can touch.

This module is the **regrowth guard** (the ``tests/test_blocks_md_matrix.py`` /
``tests/test_sheets_md_matrix.py`` pattern-guard precedent): it greps the consumer-reaching
corpus (``tests/consumer_text.py``) for the enumerated dialect classes and fails on a hit.

Its two halves are equally load-bearing:

* it **bites** — one red proof per pattern class, so a partial implementation cannot pass;
* it is **scoped** — internal ``#`` comments, ``tests/``, ``dev/``, ``progress.md``,
  ``requirements/`` and the issue files keep the dialect (it is correct there), and a
  legitimate consumer string like "Document", ``v1.19.0`` or ``Sheet1!A1:D10`` must not trip
  it.

It also scans **plan JSON values**, not only source literals — that is where F7's worst
instance lived (a runtime-composed field), so a source-only grep would have missed it.
"""
import pathlib
import re

import pytest

import consumer_text
from consumer_text import (
    DIALECT_PATTERNS,
    consumer_corpus,
    corpus_dialect_report,
    dialect_hits,
    emitted_literals,
    public_docstrings,
    runtime_json_strings,
    shipped_docs,
)
import private_tree  # noqa: E402  (LD-685)
from domain_vocabulary import RETIRED_ID_EXAMPLE

# LD-370 — CONFORMANCE-tier: shipped text must not leak internal dialect — a promise about the product's documents, not about how they are built.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

REPO_ROOT = pathlib.Path(consumer_text.REPO_ROOT)


# --------------------------------------------------------------------------- #
# AC1 / AC2 / AC3 — THE GUARD                                                  #
# --------------------------------------------------------------------------- #

def test_no_internal_dialect_anywhere_in_consumer_reaching_text():
    """The whole-corpus guard: every consumer-reaching string is dialect-free."""
    report = corpus_dialect_report()
    if report:
        lines = [
            f"  {label}\n      [{name}] {matched!r} in: …{snippet}…"
            for label, name, matched, snippet in report[:60]
        ]
        pytest.fail(
            f"{len(report)} internal-dialect reference(s) in consumer-reaching text.\n"
            "A consumer has only the wheel: an issue id, a private-set id, an AC/decision/story ref "
            "or an internal role name resolves to nothing. Say what happened, why, and what "
            "to do instead — or move the reference into a `#` comment.\n"
            + "\n".join(lines)
        )


@pytest.mark.parametrize("pattern_name", [name for name, _p, _a in DIALECT_PATTERNS])
def test_each_enumerated_pattern_class_is_absent_from_the_corpus(pattern_name):
    """AC2, one assertion per class — a failure names the class that regrew."""
    offenders = [
        (label, matched, snippet)
        for label, name, matched, snippet in corpus_dialect_report()
        if name == pattern_name
    ]
    assert offenders == [], (
        f"dialect class {pattern_name!r} present in consumer text: "
        + "; ".join(f"{label}: {matched!r}" for label, matched, _s in offenders[:12])
    )


# --------------------------------------------------------------------------- #
# The guard BITES — one red proof per pattern class (AC3). Each probe is the    #
# real shape found in the dogfood report, so a guard weakened to pass a         #
# partial sweep fails here.                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "probe, expected_class",
    [
        ("the reader escaping fix (LD-130) changed this", "issue-id"),
        ("carried over from LD-149", "issue-id"),
        # the probe is private (LD-705, LD-707): it runs in the private repository only
        pytest.param(f"the escaping fix ({RETIRED_ID_EXAMPLE})", "private-id",
                     marks=private_tree.dev_record),
        ("the mandatory-detail discipline (AC3)", "ac-ref"),
        ("the whole-document compare-and-swap (D9)", "decision-ref"),
        ("previews through the S2 resolver", "decision-ref"),
        ("the round-2 T27 blocker", "decision-ref"),
        ("closing dogfood F14", "decision-ref"),
        # a trailing colon must NOT excuse a story ref — this shape escaped the first
        # cut of the pattern (the A1-notation exclusion was too generous)
        ("S5: the opt-in deep read", "decision-ref"),
        ("**Read surface.** S1: the read client", "decision-ref"),
        ("credential doctrine D1: a write's own reads use WRITE creds", "decision-ref"),
        # THE HYPHENATED SPELLING — the one the decision sheet actually uses, and the one
        # this class was blind to until LD-603. Every probe above is un-hyphenated, so the
        # probe set was drawn from the same intuition as the pattern and confirmed it
        # forever. These bite from the other side.
        ("the whole-document compare-and-swap (D-73)", "decision-ref"),
        ("the refusal shape settled by D-59", "decision-ref"),
        ("previews through the S-2 resolver", "decision-ref"),
        ("the round-2 T-27 blocker", "decision-ref"),
        ("closing finding F-14", "decision-ref"),
        # THREE DIGITS — the sheet is past D-100, so a two-digit cap is a second, independent
        # blindness in the same expression. Both spellings must reach three digits.
        ("the plan-gate ruling D-103", "decision-ref"),
        ("the plan-gate ruling D103", "decision-ref"),
        ("W3 added insert/delete", "ladder-rung"),
        ("the R-S2 carriage flip", "ladder-rung"),
        ("the W-ladder's third rung", "ladder-rung"),
        ("the PM-adopted choice", "role-attribution"),
        ("per the PM directive they live in the core", "role-attribution"),
        ("the PM-blessed per-entry doctrine", "role-attribution"),
        ("the AST guard extends over it", "machinery"),
        ("a dogfood finding", "machinery"),
    ],
)
def test_guard_bites_on_each_dialect_shape(probe, expected_class):
    hits = dialect_hits(probe)
    assert hits, f"guard blind to {probe!r}"
    assert expected_class in {name for name, _m in hits}, (
        f"{probe!r} classified as {sorted({n for n, _ in hits})}, expected {expected_class!r}"
    )


def test_guard_bites_when_a_dialect_string_is_added_to_a_real_consumer_surface(monkeypatch):
    """Red-then-green in situ: inject dialect into a real corpus pass, guard reddens."""
    clean = corpus_dialect_report()
    assert clean == [], "corpus must be clean before the injection probe is meaningful"

    def dirty():
        return {"guide()": "the guard is armed whenever the plan carries one — LD-149"}

    monkeypatch.setattr(consumer_text, "shipped_docs", dirty)
    injected = corpus_dialect_report()
    assert [(name, matched) for _l, name, matched, _s in injected] == [("issue-id", "LD-149")]


# --------------------------------------------------------------------------- #
# The guard does NOT false-positive (AC3 / the rigor amplifier)                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "legitimate",
    [
        "Document",                                   # a leading `D` + word, not `D9`
        "the document's revision_id",
        "larkdocio v1.19.0",                          # a version, not a decision ref
        "1.19.0",
        "Sheet1!A1:D10",                              # A1 notation, not decision ref `D10`
        "the range D4:F9 spans two columns",          # a range START is not `D4`
        "read A1:S3 back",                            # `S3` after a colon is a cell
        "put it in D4:$F$9",                          # absolute-notation range end
        "the used range is s1!A1:T200",
        "$D$4",
        "a 3D chart",
        "block_type 34",
        "test_live_write_w1_gate.py",                 # a gate module name, not rung `W1`
        "SheetTab, ValueRange, UsedRange",
        "the T-shaped merge region",
        "at 9 PM the token expires",                  # time-of-day, not the PM role
        "9PM",
        "DELETE, PUT and POST",
        "F-string interpolation",
        "columns A through F",
    ],
)
def test_guard_does_not_flag_legitimate_consumer_strings(legitimate):
    assert dialect_hits(legitimate) == [], f"false positive on {legitimate!r}"


# --------------------------------------------------------------------------- #
# The guard is SCOPED — internal surfaces keep the dialect (AC6)                #
# --------------------------------------------------------------------------- #

def test_internal_comments_in_src_are_out_of_scope_and_still_carry_the_dialect():
    """A `#` comment is the sanctioned home for an internal reference.

    Proven both ways: such comments still EXIST in ``src/`` (so the sweep did not rewrite
    them), and none of them is in the corpus the guard greps.
    """
    comment_dialect = []
    for path in sorted((REPO_ROOT / "src" / "larkdocio").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") and dialect_hits(stripped):
                comment_dialect.append((path.name, lineno, stripped))
    assert comment_dialect, "expected internal `#` comments in src/ to keep the dialect"

    corpus_text = "\n".join(consumer_corpus().values())
    for name, lineno, line in comment_dialect:
        assert line not in corpus_text, f"{name}:{lineno} comment leaked into the corpus"


@pytest.mark.parametrize(
    "internal_path",
    ["progress.md", "CLAUDE.md", "tests/consumer_text.py", "tests/test_guide.py"],
)
@private_tree.process
def test_internal_files_keep_the_dialect_and_are_not_in_the_corpus(internal_path):
    text = (REPO_ROOT / internal_path).read_text(encoding="utf-8")
    assert dialect_hits(text), f"{internal_path} unexpectedly dialect-free — was it swept?"
    assert internal_path not in " ".join(consumer_corpus()), (
        f"{internal_path} must not be a corpus surface"
    )


@private_tree.citations
def test_dev_docs_and_issue_files_keep_the_dialect():
    dev_docs = list((REPO_ROOT / "dev").rglob("*.md"))
    assert dev_docs, "dev/ docs missing"
    assert any(dialect_hits(p.read_text(encoding="utf-8")) for p in dev_docs)
    labels = " ".join(consumer_corpus())
    assert "dev/" not in labels and "progress/" not in labels and "requirements/" not in labels


def test_the_corpus_covers_no_file_outside_the_shipped_package():
    for label in consumer_corpus():
        if label.startswith("src/"):
            assert label.startswith("src/larkdocio/"), label
        else:
            assert not label.startswith(("tests/", "dev/", "progress", "requirements/")), label


# --------------------------------------------------------------------------- #
# The corpus is REAL — each pass is populated and reaches what it claims        #
# --------------------------------------------------------------------------- #

def test_the_corpus_composes_ALL_FOUR_PASSES():
    """The guard's scope cannot silently shrink.

    Without this, deleting one ``corpus.update(...)`` line from
    :func:`consumer_text.consumer_corpus` leaves the whole suite green while the guard stops
    looking at a third of the shipped text — which is how a regrowth guard rots.
    """
    corpus = consumer_corpus()
    for pass_name, pass_fn in (
        ("shipped docs", shipped_docs),
        ("emitted literals", emitted_literals),
        ("public docstrings", public_docstrings),
        ("runtime plan JSON", runtime_json_strings),
    ):
        produced = pass_fn()
        assert produced, f"{pass_name} pass produced nothing"
        missing = [label for label in produced if label not in corpus]
        assert not missing, (
            f"consumer_corpus() dropped the {pass_name} pass "
            f"({len(missing)}/{len(produced)} labels absent, e.g. {missing[:3]})"
        )


def test_shipped_docs_pass_covers_the_accessors_AND_THE_FRONT_DOOR():
    """The two accessor-backed deep docs are still here, still substantial — and no longer
    alone.

    They were the *whole* pass for months, which is why the README (the wheel's ``METADATA``
    body), the ``METADATA`` header fields and the CLI ``--help`` rotted unwatched. The exact
    membership pin is ``tests/test_front_door_doctrine.py``'s contract; what this keeps is the
    original assertion's substance, so a widening cannot quietly have *replaced* the docs it
    started from.
    """
    docs = shipped_docs()
    assert len(docs["guide()"]) > 20_000 and len(docs["writer_brief()"]) > 10_000
    assert {"README.md (the wheel METADATA body)", "larkdocio --help"} <= set(docs), (
        "the front door is not in the shipped-docs pass — the widening was reverted"
    )


def test_public_docstring_pass_enumerates_the_public_surface_by_introspection():
    docs = public_docstrings()
    # The symbols the shipped recipes actually name.
    for expected in [
        "larkdocio.write.Plan",
        "larkdocio.write.dry_run",
        "larkdocio.write.apply",
        "larkdocio.sheets.dry_run",
        "larkdocio.sheets.Plan.revision_guard_detail",
        "larkdocio.capabilities",
        "help(larkdocio.write)",
        "help(larkdocio.sheets)",
    ]:
        assert expected in docs, f"public docstring pass missed {expected}"
    assert len(docs) > 250, f"public surface suspiciously small: {len(docs)}"


def test_emitted_literal_pass_reaches_refusal_details_and_registry_text():
    literals = emitted_literals()
    joined = "\n".join(literals.values())
    assert "stale-document" in joined and "precondition-mismatch" in joined
    # LD-244: derive over the whole ``capabilities`` PACKAGE rather than naming one file —
    # strictly stronger, since a submodule added tomorrow is covered without an edit.
    assert any(label.startswith("src/larkdocio/capabilities/") for label in literals)
    # docstrings are pass three's job, so the literal pass must not double-count them
    assert not any("Return the shipped consumer guide" in text for text in literals.values())


def test_no_comment_is_ever_yielded_by_the_literal_pass():
    """The AC6 boundary, mechanically: `ast` yields no comment, so one cannot leak."""
    marker = "# LD-000-COMMENT-CANARY"
    path = REPO_ROOT / "src" / "larkdocio" / "guide.py"
    assert marker not in path.read_text(encoding="utf-8")
    literals = emitted_literals()
    assert not any(marker in text for text in literals.values())


# --------------------------------------------------------------------------- #
# The guard scans PLAN JSON VALUES, not only source literals (the amplifier)    #
# --------------------------------------------------------------------------- #

def test_runtime_pass_scans_real_plan_json_values():
    runtime = runtime_json_strings()
    guard_details = {
        label: text
        for label, text in runtime.items()
        if label.endswith(".revision_guard_detail")
    }
    assert len(guard_details) >= 4, f"expected both surfaces × both statuses, got {guard_details}"
    assert any("dry_run" in label for label in guard_details)
    # …and the refused entry's detail is in there too
    assert any(label.endswith(".detail") for label in runtime)


def test_a_runtime_only_dialect_value_is_caught_even_though_no_source_literal_has_it(
    monkeypatch,
):
    """The F7 shape: the value is COMPOSED at runtime.

    A guard that only grepped ``src/**`` literals would pass this; the runtime pass fails it.
    """
    import larkdocio.common.staleness as staleness_core
    from larkdocio.write import preview as docx_preview

    sentinel = "the anchor moves whenever the referenced data changes — LD-149"

    def dialect_semantics(revision):
        return {"status": staleness_core.REVISION_GUARD_ACTIVE, "detail": sentinel}

    monkeypatch.setattr(docx_preview, "revision_guard_semantics", dialect_semantics)

    assert sentinel not in "\n".join(emitted_literals().values()), "must be runtime-only"
    caught = [
        (label, matched)
        for label, name, matched, _s in corpus_dialect_report(runtime_json_strings())
        if matched == "LD-149"
    ]
    assert caught, "the runtime plan-JSON pass did not catch a runtime-composed dialect value"


# --------------------------------------------------------------------------- #
# AC5 — plan.revision_guard_detail specifically: dialect-free AND still the     #
# paragraph the seat session praised (substance retained, not deleted).         #
# --------------------------------------------------------------------------- #

def _guard_details():
    from larkdocio.sheets.plan import revision_guard_semantics as sheets_semantics
    from larkdocio.write.revision import revision_guard_semantics as docx_semantics

    return {
        "docx/active": docx_semantics(7)["detail"],
        "docx/unavailable": docx_semantics(None)["detail"],
        "sheets/active": sheets_semantics(12)["detail"],
        "sheets/unavailable": sheets_semantics(0)["detail"],
    }


@pytest.mark.parametrize("which", ["docx/active", "docx/unavailable",
                                   "sheets/active", "sheets/unavailable"])
def test_revision_guard_detail_is_dialect_free(which):
    assert dialect_hits(_guard_details()[which]) == []


@pytest.mark.parametrize(
    "which, must_say",
    [
        ("docx/active", ["compare-and-swap", "re-read", "immediately before",
                         "STALE_DOCUMENT", "ZERO writes"]),
        ("docx/unavailable", ["UNAVAILABLE", "document_revision_id", "self-activates",
                              "STALE_ANCHOR"]),
        ("sheets/active", ["tier 1", "tier 2", "compare-and-swap", "stale-sheet",
                           "value precondition"]),
        ("sheets/unavailable", ["tier 1", "UNAVAILABLE", "tier 2", "self-heals",
                                "unguarded"]),
    ],
)
def test_revision_guard_detail_retains_its_substance(which, must_say):
    """The praised paragraph survives the sweep: every load-bearing clause still there."""
    detail = _guard_details()[which]
    missing = [phrase for phrase in must_say if phrase not in detail]
    assert missing == [], f"{which} lost substance: {missing}"


def test_the_formula_precondition_reason_survives_in_consumer_language():
    """The exact string F7 named: it explained WHY via "— LD-149"; the WHY must remain."""
    from larkdocio.sheets.plan import revision_guard_semantics

    for revision in (12, 0):
        detail = revision_guard_semantics(revision)["detail"]
        assert "compares the EXPRESSION" in detail
        assert "a computed value drifts whenever the referenced data changes" in detail
        assert dialect_hits(detail) == []


def test_a_relayable_plan_paragraph_reads_as_prose_not_as_a_tracker_dump():
    """No leftover em-dash-then-nothing or empty parenthetical from the sweep."""
    for detail in _guard_details().values():
        assert not re.search(r"—\s*[.;)]", detail), f"dangling em-dash in: {detail}"
        assert "()" not in detail and "( " not in detail
        assert "  " not in detail.replace("\n", " ").strip(), "double space left behind"
        assert not detail.rstrip().endswith("—")
