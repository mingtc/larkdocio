# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE GUARD for prose signature claims — the class behind dogfood F5.

The defect: the shipped guide documented **``AppendDimension(sheet_id, dimension="ROWS",
length=…)``** in a bullet, and that call raises ``TypeError`` (the parameter is
``major_dimension``). The *class*: the guide's "every recipe runs as pasted" guarantee is
enforced by extracting and executing ```` ```python ```` fences, and that bullet sat 20 lines
**below** the fence that closed above it. Fenced code was guarded; the prose that documents
the sibling APIs was not — and it had drifted, invisibly, because nothing looked.

``tests/prose_signatures.py`` carries the machinery and the reasoning. This file is the
guard, and it is deliberately paranoid about the two ways a guard like this dies:

* **it never bites** — so every failure mode is proven red *separately*
  (unknown keyword, excess arity, renamed symbol, deleted symbol, drifted default), and a
  partial implementation cannot pass;
* **it bites correct prose** — so the must-not-bite side is pinned too (a symbol named
  without a signature, an illustrative literal value, a claim already covered by the
  executing harness inside a fence), because a subject-scoped check that forces correct
  prose to be reworded is a guard that gets deleted rather than obeyed.
"""
import inspect
import re
import sys

import consumer_text
import prose_signatures
from prose_signatures import (
    UNRESOLVED, claim_problems, flatten, illustrative_symbols, mask_fenced_code,
    prose_claims, resolve_symbol, sweep, wrapped_claims,
)

import larkdocio

# --------------------------------------------------------------------------- #
# 0. The sweep, and its recorded size.                                         #
#                                                                              #
#    A single fix with no sweep would leave "was F5 alone?" unknown forever.    #
#    These two numbers are the measurement, taken BEFORE anything was fixed:    #
#    234 claims across the whole consumer corpus, 2 of them wrong.              #
# --------------------------------------------------------------------------- #

#: What the sweep measured, per surface. Recorded as a FLOOR, not an equality: prose is
#: expected to grow, and a guard that reddened whenever someone documented one more call would
#: be teaching authors to avoid documenting calls. What the floor does catch is the failure
#: that matters — a refactor that quietly narrows the sweep back down (a broken extractor, a
#: dropped corpus pass) and then reports "0 problems" because it is looking at nothing.
#:
#: The pre-fix sweep counted **234** claims with **2** wrong; the floor below is the post-fix
#: **233**, because fixing the second defect *removed* a claim rather than correcting it (the
#: dangling ``token()`` reference was deleted, not renamed).
SWEPT_AT_LANDING = {
    "guide()": 135,
    "writer_brief()": 9,
    "release_notes() (the packaged RELEASE_NOTES.md)": 10,
    "README.md (the wheel METADATA body)": 21,
    "public docstrings (all)": 58,
}

#: The whole-corpus total, post-fix. Same floor semantics.
SWEPT_TOTAL_AT_LANDING = 233

#: The two wrong claims the sweep found, both fixed in the same change:
#:
#: 1. ``guide()`` — ``AppendDimension(sheet_id, dimension="ROWS", length=…)``; the real
#:    parameter is ``major_dimension`` and the written call raises ``TypeError``.
#: 2. ``larkdocio.common.fetch_tenant_access_token.__doc__`` — "(the spike's ``token()``)",
#:    a dangling reference to a helper that never shipped, in text a consumer reads via
#:    ``help()``. Nothing resolves it.
#:
#: Everything else was true: 21 claims in the README, 10 in the release notes, 9 in the
#: writer brief, 0 in ``capabilities()`` output, 0 in the emitted string literals and 0 in
#: the rendered CLI ``--help`` — measured, not assumed (see
#: ``test_the_sweep_covers_more_than_the_guide`` for the recorded per-surface answer).
WRONG_AT_LANDING = 2


def test_no_consumer_reaching_prose_claim_contradicts_the_real_signature():
    """THE guard. Every inline ``Symbol(...)`` in shipped prose is held to the standard the
    fenced recipes are held to, because a consumer pastes both."""
    claims, problems = sweep()
    assert not problems, (
        f"{len(problems)} of {len(claims)} prose signature claims disagree with the real "
        "signature. A consumer pastes a bullet as readily as a fence:\n  "
        + "\n  ".join(problems)
    )


def test_the_sweep_is_not_looking_at_nothing():
    """The floor. A guard over an empty corpus reports zero problems and proves nothing."""
    claims, _problems = sweep()
    by_surface = {}
    for claim in claims:
        by_surface[claim.surface] = by_surface.get(claim.surface, 0) + 1
    docstring_labels = set(consumer_text.public_docstrings())
    counted = dict(by_surface)
    counted["public docstrings (all)"] = sum(
        n for label, n in by_surface.items() if label in docstring_labels)
    shortfall = {
        k: (counted.get(k, 0), v) for k, v in SWEPT_AT_LANDING.items() if counted.get(k, 0) < v
    }
    assert not shortfall, (
        "the sweep now finds FEWER claims than it did when it landed — the extractor or the "
        f"corpus narrowed, so 'no problems' means 'nothing looked'. {shortfall} "
        "(counted, floor)"
    )
    assert len(claims) >= SWEPT_TOTAL_AT_LANDING, (
        f"the whole-corpus sweep dropped from {SWEPT_TOTAL_AT_LANDING} to {len(claims)} claims"
    )


def test_the_sweep_covers_more_than_the_guide():
    """The scoping answer, recorded rather than assumed.

    Getting the scope wrong is how prose went unguarded in the first place, so the question
    "which other consumer-reaching surfaces carry signature claims?" was **measured**:
    ``public docstrings`` carry them in quantity (59), ``capabilities()`` output carried
    **none**, and so did the emitted string literals and the rendered CLI ``--help``. The
    guard reads the whole four-pass corpus regardless, so a surface that starts carrying
    claims tomorrow is swept without anyone widening a list — which is exactly what happened
    at LD-320, and the recorded answer below moved rather than the guard narrowing."""
    claims, _ = sweep()
    surfaces = {claim.surface for claim in claims}
    assert "guide()" in surfaces
    assert surfaces & set(consumer_text.public_docstrings()), (
        "public docstrings carry 59 signature claims — if none are found the docstring pass "
        "has dropped out of the corpus"
    )
    capability_labels = set(consumer_text.capabilities_strings())
    # UPDATED, not narrowed (LD-320). ``capabilities()`` output carried no signature claim when
    # this was first measured; it now carries exactly one — the ``docs`` block's
    # ``section_addressing`` sentence, which tells a consumer the guide's headings are
    # individually retrievable and therefore names a call. The guard SWEPT it and held it to
    # the real signature, which is the case this test's own docstring anticipated.
    # UPDATED AGAIN (LD-379), same rule: the docx-read credential note now carries the docx
    # block-anchor measurement, whose opening sentence names ``docx_block_url(doc_url,
    # block_id)`` — a real call, swept and held to the real signature.
    # UPDATED AGAIN (LD-414), same rule: `writer_brief()` / `release_notes()` / `changelog()`
    # each gained their own `docs` row's `section_addressing` sentence — the SAME pattern
    # `guide()`'s row already carried, generalized to the other three documents rather than
    # forked, each naming its own real `<accessor>(section=…)` call.
    # UPDATED AGAIN (LD-472), same rule: the sheets-read credential note carries the
    # cell-link negative, which now disambiguates itself from the shipped hyperlink WRITE and
    # therefore names `RichCellWriteRequest.hyperlink(range, link, text=…)` — a real call,
    # swept and held to the real signature. The claim was added precisely because a consumer
    # read the negative as a verdict on that call, so it naming the call is the point.
    # UPDATED AGAIN (LD-475), same rule: the label prefix is now the CALL that returns the
    # payload the string was found in, because the registry has two doors — the no-argument
    # summary and `full=True` — and the corpus sweeps both. The seven claims are the same seven
    # sentences; they are labelled by the door they came from.
    # UPDATED AGAIN (LD-549), same rule and the same shape as LD-414's: a FIFTH packaged
    # consumer document — the Lark-application walkthrough — gained its `docs` row, so its
    # `section_addressing` sentence joins the four, naming its own real `lark_setup(section=…)`
    # call. The recorded answer is updated, not narrowed: the sentence is authored once for
    # every document and each instance is swept and held to the real signature.
    assert (surfaces & capability_labels) == {
        "capabilities(full=True).docs.guide().section_addressing",
        "capabilities(full=True).docs.writer_brief().section_addressing",
        "capabilities(full=True).docs.release_notes().section_addressing",
        "capabilities(full=True).docs.changelog().section_addressing",
        "capabilities(full=True).docs.lark_setup().section_addressing",
        "capabilities(full=True).surfaces.docx-read.credentials.note",
        "capabilities(full=True).surfaces.sheets-read.credentials.note",
        "capabilities(full=True).surfaces.base-schema-write.credentials.note"}, (
        "capabilities() output carried exactly EIGHT signature claims when this was last "
        "measured (the five docs-block section_addressing sentences, the docx-read and "
        "sheets-read credential notes, and — since the whole-Base delete shipped — the "
        "base-schema-write credential note, which names `base_is_gone(exc)` because that is "
        "what a `finally` needs); if it now carries a different set, that is fine — update "
        "this recorded answer, do not narrow the guard"
    )


def test_the_corpus_the_guard_sweeps_is_the_full_four_pass_corpus():
    """The guard is only as wide as its corpus (the lesson the dialect guard already
    learned), so pin that it really reads all four passes."""
    corpus = consumer_text.consumer_corpus()
    assert set(consumer_text.shipped_docs()) <= set(corpus)
    for pass_fn in (consumer_text.emitted_literals, consumer_text.public_docstrings,
                    consumer_text.runtime_json_strings):
        keys = set(pass_fn())
        assert keys, f"corpus pass {pass_fn.__name__} is empty"
        assert keys <= set(corpus), f"corpus pass {pass_fn.__name__} is not in the corpus"


# --------------------------------------------------------------------------- #
# 1. AC2 — F5's own drift, and the guard's first red-then-green proof.          #
# --------------------------------------------------------------------------- #

#: The bullet as it shipped, wrong. Kept verbatim so the proof is against the real text.
F5_AS_SHIPPED = '- **`AppendDimension(sheet_id, dimension="ROWS", length=…)`** grows the tab'


def test_the_guide_documents_AppendDimension_with_its_REAL_parameter():
    """The specific drift: ``dimension=`` is not a parameter of anything."""
    guide = larkdocio.guide(full=True)
    assert 'AppendDimension(sheet_id, dimension=' not in flatten(guide), (
        "the guide is back to documenting AppendDimension(dimension=…), which raises "
        "TypeError: the parameter is major_dimension"
    )
    from larkdocio.sheets.write_apply import AppendDimension

    parameters = list(inspect.signature(AppendDimension).parameters)
    assert parameters == ["sheet_id", "major_dimension", "length"]
    # and the guide's own claim about it is checked by the sweep, with no problems:
    claims = [c for c in prose_claims(guide, "guide()") if c.symbol == "AppendDimension"]
    assert claims, "the guide no longer documents AppendDimension at all"
    for claim in claims:
        assert not claim_problems(claim), claim_problems(claim)


def test_the_guard_REDDENS_on_the_bullet_exactly_as_it_shipped():
    """The red half of AC2's red-then-green, run against the shipped wording verbatim.

    This is the proof that the guard would have caught F5 on the day it was written — the
    only evidence that matters for a guard whose job is to have caught something."""
    claims = prose_claims(F5_AS_SHIPPED, "the bullet as it shipped")
    assert [c.symbol for c in claims] == ["AppendDimension"], claims
    problems = claim_problems(claims[0])
    assert problems, "the guard does not bite the very defect it was built for"
    assert "dimension" in problems[0]


def test_the_real_call_the_old_bullet_documented_still_raises_TypeError():
    """And the defect is real, not a lint opinion: the documented call fails as pasted."""
    from larkdocio.sheets.write_apply import AppendDimension

    try:
        AppendDimension("shtX", dimension="ROWS", length=1)
    except TypeError as exc:
        assert "dimension" in str(exc)
    else:                                              # pragma: no cover
        raise AssertionError("AppendDimension now accepts dimension= — this probe is stale")


# --------------------------------------------------------------------------- #
# 2. AC3 — each failure mode proven red SEPARATELY, so a partial guard fails.  #
# --------------------------------------------------------------------------- #

def _problems(text: str) -> list:
    claims = prose_claims(text, "a probe")
    marked = illustrative_symbols(text)
    return [p for claim in claims for p in claim_problems(claim, marked)]


def test_red_mode_1_a_WRONG_KEYWORD_NAME():
    problems = _problems("the op is `AppendDimension(sheet_id, dimension=\"ROWS\")`")
    assert problems and "dimension" in problems[0], problems


def test_red_mode_2_a_WRONG_ARITY():
    """More positionals than the symbol has — the shape a signature drift takes when a
    parameter is removed and the prose keeps passing it."""
    problems = _problems("call `plain_text(node, extra, third)` to flatten a node")
    assert problems, "an over-long argument list was accepted"
    assert "positional" in problems[0].lower(), problems


def test_red_mode_3_a_RENAMED_SYMBOL():
    """The symbol still exists under its new name; the prose keeps the old one."""
    problems = _problems("compile a fragment with `compose_markdown(markdown)`")
    assert problems and UNRESOLVED in problems[0], problems
    # and the rename target really is the live name, so this probe is about a rename:
    assert resolve_symbol("compose"), "compose() has itself gone — this probe is stale"


def test_red_mode_4_a_SYMBOL_THAT_NO_LONGER_EXISTS():
    problems = _problems("the legacy entry point was `download_and_convert(url, out_dir)`")
    assert problems and UNRESOLVED in problems[0], problems


def test_red_mode_5_a_DRIFTED_DEFAULT_VALUE():
    """The subtlest mode, and the amplifier's fifth: names and arity are perfect, only the
    documented **default** is wrong. Nothing else in this file would catch it."""
    from larkdocio.sheets.write_apply import AppendDimension

    real = inspect.signature(AppendDimension)
    assert real.parameters["length"].default == 1, "the real default moved; probe is stale"
    problems = _problems(
        "`AppendDimension(sheet_id: str, major_dimension: str, length: int = 0)` appends")
    assert problems, "a drifted default was accepted"
    assert "default is 1" in problems[0], problems

    # the same claim with the TRUE default is clean — so the check is about the value, not
    # about the annotated form itself
    assert not _problems(
        "`AppendDimension(sheet_id: str, major_dimension: str, length: int = 1)` appends")


def test_red_mode_5b_a_DEFAULT_CLAIMED_FOR_A_REQUIRED_PARAMETER():
    """The other half of the default class: documenting a default that does not exist tells a
    consumer they may omit an argument they may not."""
    problems = _problems(
        '`AppendDimension(sheet_id: str, major_dimension: str = "ROWS", length: int = 1)` x')
    assert problems and "REQUIRED" in problems[0], problems


def test_red_mode_5c_a_REQUIRED_PARAMETER_THAT_REALLY_HAS_A_DEFAULT():
    problems = _problems(
        "`AppendDimension(sheet_id: str, major_dimension: str, length: int)` appends")
    assert problems and "really defaults to 1" in problems[0], problems


def test_red_mode_6_a_DRIFTED_PARAMETER_NAME_ORDER():
    problems = _problems(
        "`AppendDimension(major_dimension: str, sheet_id: str, length: int = 1)` appends")
    assert problems and "real ones are" in problems[0], problems


# --------------------------------------------------------------------------- #
# 3. AC4 — MUST NOT BITE. The other half of the boundary.                      #
# --------------------------------------------------------------------------- #

def test_must_not_bite_a_symbol_NAMED_without_a_signature_claim():
    """The AC's own example. Naming a symbol claims nothing about its parameters, and a
    guard that demanded parentheses everywhere would force every mention into a call."""
    assert not _problems(
        "`MergeCells` keeps the anchor cell's value, and `AppendDimension` grows the tab; "
        "`larkdocio.write.MAX_NEST_DEPTH` is the cap and `NewBlock` is the factory."
    )


def test_must_not_bite_an_ILLUSTRATIVE_LITERAL_VALUE_in_a_call():
    """The guide shows the *interesting* value all the time — ``language="python"`` when the
    real default is ``None``, ``resolve_mentions=False`` when it is ``True``. Those are
    correct prose. Inferring a default claim from a call would redden on both, and the first
    "fix" would be to weaken the guard."""
    assert not _problems(
        'author code with `NewBlock.code(text, language="python")` and read plainly with '
        "`Config(OutputConfig(resolve_mentions=False))`"
    )
    # …and the values really are non-default, so this test is about the ambiguity it claims:
    from larkdocio.read.config import OutputConfig
    from larkdocio.write import NewBlock

    assert inspect.signature(NewBlock.code).parameters["language"].default is None
    assert inspect.signature(OutputConfig).parameters["resolve_mentions"].default is True


def test_must_not_bite_a_BARE_PARENTHESES_reference_to_a_function():
    """``compose()`` in prose means "the compose function", not "compose takes no arguments".
    The guide does this ~20 times."""
    assert not _problems(
        "`compose()` compiles a fragment, `apply()` executes a plan, and `capabilities()` "
        "reports the surfaces; `larkdocio.guide()` returns this document."
    )


def test_must_not_bite_a_claim_INSIDE_A_FENCE_and_does_not_double_report_it():
    """Fenced code is the executing harness's territory. A claim reported by both guards
    would be fixed twice and reported twice — and worse, the fence's own guard is the
    stronger one (it *runs* the code), so this one must stay out of its way."""
    fenced = (
        "Prose above.\n\n"
        "```python\n"
        'AppendDimension(sheet_id, dimension="ROWS", length=1)\n'
        "```\n\n"
        "Prose below.\n"
    )
    assert not prose_claims(fenced, "a fenced probe"), (
        "a fenced claim was picked up — the executing harness already covers it")
    assert "AppendDimension" not in mask_fenced_code(fenced)

    # and the identical text OUTSIDE the fence is still caught, so the masking is not a
    # blanket amnesty:
    assert _problems('Prose above. `AppendDimension(sheet_id, dimension="ROWS")` grows it.')


def test_must_not_bite_a_METHOD_named_on_a_LOCAL_RECEIVER():
    """The guide writes ``reader.get_docx_content(doc_token)`` and ``review.for_node(block)``.
    No introspection can resolve ``reader``; the method is looked up by its own name so the
    claim is checked rather than skipped **and** rather than falsely reported."""
    assert not _problems(
        "`reader.get_docx_content(doc_token)` returns the payload and "
        "`review.for_node(block)` returns what a reviewer said."
    )
    # a genuinely wrong method claim on the same shape is still caught:
    assert _problems("`reader.get_docx_content(a, b, c, d)` returns the payload")


def test_must_not_bite_a_span_THAT_IS_NOT_PYTHON():
    """``NewBlock.heading(7..9, …)`` is prose meaning "levels 7 to 9"; ``Sheet1!A1:B2`` is a
    range. Neither parses, and neither claims a signature."""
    assert not _problems(
        "`NewBlock.heading(7..9, …)` is refused, and the range is `Sheet1!A1:B2` "
        "(or `<sheet_id>!A1:B2`)."
    )


def test_the_ILLUSTRATIVE_MARKER_is_honored_and_is_NARROW():
    """The escape hatch AC4 requires — and the three ways it must not become a loophole."""
    marked = (
        "Pass a callable that returns a fresh credential, e.g. `token()`.\n"
        "<!-- signature-claim: illustrative token -->\n"
    )
    assert not _problems(marked), "the marker was not honored"

    # 1. it does not silence a DIFFERENT symbol
    other = (
        "Pass `token()` or `refresh_token()` — either works.\n"
        "<!-- signature-claim: illustrative token -->\n"
    )
    problems = _problems(other)
    assert problems and "refresh_token" in problems[0], problems

    # 2. it cannot keep a REAL symbol's wrong keyword alive
    real_but_wrong = (
        '`AppendDimension(sheet_id, dimension="ROWS")` grows the tab.\n'
        "<!-- signature-claim: illustrative AppendDimension -->\n"
    )
    assert _problems(real_but_wrong), (
        "the marker excused a resolvable symbol's impossible call — it must only excuse the "
        f"{UNRESOLVED!r} class"
    )

    # 3. it must NAME a symbol; a bare marker silences nothing
    assert _problems(
        "Pass `token()`.\n<!-- signature-claim: illustrative -->\n")



def test_every_stdlib_since_entry_is_exactly_as_new_as_it_says():
    """LD-687 — the version excuse cannot outlive its truth in either direction: on an
    interpreter at or above the entry's version the symbol MUST resolve (else the entry is
    wrong and is hiding real drift), and below it the symbol must NOT (else the entry is not
    needed and should go)."""
    assert prose_signatures.STDLIB_SINCE, "an empty table needs no test — remove both"
    for symbol, since in prose_signatures.STDLIB_SINCE.items():
        assert symbol.split(".")[0] in sys.stdlib_module_names, symbol
        if sys.version_info[:2] >= since:
            assert resolve_symbol(symbol), f"{symbol} should exist from Python {since}"
        else:
            assert not resolve_symbol(symbol), f"{symbol} already exists before {since}"


def test_the_stdlib_since_excuse_does_not_cover_an_UNLISTED_stdlib_symbol():
    """Red proof: the excuse is per named symbol, never "anything in the stdlib"."""
    problems = _problems("Use `copy.no_such_function(x)`.")
    assert problems and UNRESOLVED in problems[0]


def test_no_shipped_surface_actually_NEEDS_the_marker():
    """Measured, and worth keeping measured: the hatch exists so a future author is not
    forced to reword correct prose, not as a place to park drift."""
    used = {
        label: sorted(illustrative_symbols(text))
        for label, text in consumer_text.consumer_corpus().items()
        if isinstance(text, str) and illustrative_symbols(text)
    }
    assert not used, (
        "a shipped surface now marks a claim illustrative. That may be right — but say so "
        f"here, so the exception is visible rather than silent: {used}"
    )


# --------------------------------------------------------------------------- #
# 4. AC6 — line-wrap awareness, proven on the SHIPPED text.                    #
# --------------------------------------------------------------------------- #

def test_the_extractor_finds_a_claim_SPLIT_ACROSS_A_LINE_BREAK():
    """The lesson a previous guard learned the hard way: its first draft's flat grep found 4
    of 6 real hits because two shipped wrapped inside a docstring."""
    wrapped = 'the op is `AppendDimension(sheet_id,\n  dimension="ROWS", length=…)` — grows it'
    problems = _problems(wrapped)
    assert problems and "dimension" in problems[0], problems

    # and a single-line extractor really is blind to it, which is what makes the DOTALL span
    # and flatten() earn their place rather than being defensive noise:
    naive = re.compile(r"`([^`\n]+)`")
    assert not [m for m in naive.findall(wrapped) if "AppendDimension" in m], (
        "the wrap no longer splits the span; this probe is stale")


def test_wrapped_claims_REALLY_SHIP_so_the_flattening_is_load_bearing():
    """Not a hypothetical: five call-shaped claims ship split across a newline today. If this
    ever reports zero, the flattening has become dead code — check that before deleting it."""
    wrapped = wrapped_claims()
    assert len(wrapped) >= 7, (
        f"only {len(wrapped)} wrapped claims found; seven shipped when this landed "
        f"({[str(c) for c in wrapped]})"
    )
    assert not [p for c in wrapped for p in claim_problems(c)]


def test_the_DEFAULT_arm_is_live_on_SHIPPED_text_not_dead_machinery():
    """The corrected ``AppendDimension`` bullet is written in the annotated **signature**
    form, so the strictest arm of this guard — names, order, kinds and **defaults** — runs
    against the shipped guide rather than only against probes. A check that only ever fires on
    synthetic text is a check nobody notices breaking."""
    signature_claims = [c for c in sweep()[0] if c.kind == "signature"]
    assert signature_claims, (
        "no shipped surface writes a claim in annotated signature form any more — the "
        "default/order/kind arm is now exercised only by probes"
    )
    assert any(c.symbol == "AppendDimension" and c.surface == "guide()"
               for c in signature_claims), [str(c) for c in signature_claims]


def test_a_REFLOW_can_neither_hide_nor_invent_a_claim():
    """The property the flattening buys: the same sentence wrapped at any column makes the
    same claims."""
    sentence = ('`AppendDimension(sheet_id, major_dimension="ROWS", length=…)` grows the tab '
                'at the end, and `AppendRowsWithValues` appends rows carrying values.')
    baseline = [(c.symbol, c.text) for c in prose_claims(sentence, "flat")]
    assert baseline
    for width in (24, 36, 48, 60, 72):
        rewrapped, line = [], ""
        for word in sentence.split():
            if len(line) + len(word) + 1 > width:
                rewrapped.append(line)
                line = "  " + word
            else:
                line = f"{line} {word}".strip()
        rewrapped.append(line)
        text = "\n".join(rewrapped)
        assert [(c.symbol, c.text) for c in prose_claims(text, "wrapped")] == baseline, (
            f"wrapping at {width} columns changed the claims found:\n{text}")


# --------------------------------------------------------------------------- #
# 5. The resolver — the half that decides whether a report is trustworthy.     #
# --------------------------------------------------------------------------- #

def test_resolution_considers_EVERY_candidate_not_the_first():
    """``dry_run`` is a real name on both write surfaces and only the docx one takes
    ``document_revision_id``. First-wins resolution reported the guide's correct docx claim
    as a wrong keyword — the exact false positive that makes a guard untrustworthy."""
    # Asserted on the CALLABLES, not on their names (LD-492). The resolver dedupes by identity
    # and keeps the alphabetically-first alias, so the docx `dry_run` is reported under
    # whichever module happens to sort first among the ones re-exporting it — that used to be
    # `larkdocio.write`, and the roundtrip verb's own re-import now sorts ahead of it. Which
    # alias wins is an accident of module naming; that BOTH surfaces' functions are candidates
    # is the property this guard is about, and identity says it without depending on the
    # accident.
    import larkdocio.sheets
    import larkdocio.write

    resolved = {id(fn) for _name, fn, _unbound in resolve_symbol("dry_run")}
    assert id(larkdocio.write.dry_run) in resolved, "the docx dry_run is not a candidate"
    assert id(larkdocio.sheets.dry_run) in resolved, "the sheets dry_run is not a candidate"
    assert not _problems(
        "`dry_run(requests, root, document_revision_id=document.revision_id)` arms the guard")
    # neither surface accepts this, so ambiguity is not a blanket pass:
    assert _problems("`dry_run(requests, root, revision_guard=7)` arms the guard")


def test_resolution_reaches_a_module_NO_RECIPE_IMPORTS():
    """Scoping resolution to the guide's own imports is how prose went unguarded before:
    ``supported_code_languages`` is documented by name and imported by no recipe. A narrow
    index would have called it a missing symbol — a false positive in the one message that
    has to be believed."""
    assert resolve_symbol("supported_code_languages"), (
        "the resolver cannot see larkdocio.langs — every claim naming it would be reported "
        "as a missing symbol"
    )
    assert not _problems("use `supported_code_languages()`, or a bare fence")


def test_the_library_index_covers_the_whole_shipped_package():
    modules = {m.__name__ for m in prose_signatures.library_modules()}
    for expected in ("larkdocio", "larkdocio.write", "larkdocio.sheets", "larkdocio.langs",
                     "larkdocio.sheets.requests", "larkdocio.common.transport"):
        assert expected in modules, f"{expected} missing from the resolver's index"


# --------------------------------------------------------------------------- #
# 6. AC7 — the new/changed text is dialect-free.                               #
# --------------------------------------------------------------------------- #

def test_the_corrected_bullet_is_dialect_free():
    line = next((ln for ln in larkdocio.guide(full=True).splitlines()
                 if "AppendDimension" in ln), None)
    assert line is not None
    assert not consumer_text.dialect_hits(line), consumer_text.dialect_hits(line)


def test_the_corrected_docstring_is_dialect_free_and_names_no_dangling_symbol():
    from larkdocio.common.transport import fetch_tenant_access_token

    doc = fetch_tenant_access_token.__doc__
    assert not consumer_text.dialect_hits(doc), consumer_text.dialect_hits(doc)
    assert not _problems(doc), _problems(doc)
