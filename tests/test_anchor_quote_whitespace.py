"""LD-455 — the anchor quote's whitespace trap: an unhelpful refusal, and one silent garble.

A long paragraph carries a literal ``\\n`` **inside one text run** — a *soft return*. The
reader's Markdown shows it as an ordinary line wrap, indistinguishable from terminal
word-wrap, so a sentence a consumer copies **out of the library's own dump** differs from
the raw stored text by one invisible whitespace character. Two distinct defects fall out of
that one fact, and this module pins both.

**Arm A — the unhelpful refusal (``write/resolve.py``).** ``Anchor(quote=)`` matches raw
stored text byte-verbatim. The engine is holding the tree, knows exactly which block the
consumer means, and said only ``not-found`` with the remedy *"re-read the document and copy
the quote verbatim"* — which is precisely what the consumer just did. The contract is not
the defect: exactly-one-or-refuse stays, and the library still does **not** normalize
whitespace to force a match. The **diagnostic** was the defect, and it is what changes here:
a whitespace-only near-miss is now *named* — ``block '<id>' differs only in whitespace`` —
with the actual stored spelling and a short fragment that does match.

**Arm B — the silent garble (the reconcile round trip).** The shipped copy-this recipe
spliced the projection **by line**. A block whose own text carries a soft return occupies
more than one projected line while only its first line carries a marker, so replacing "the
line that starts with X" rewrites *part* of a block and leaves the rest — and the reconciler
cannot see it, because by contract whatever comes back is authored intent. The outcome was
``plan.ok: True`` over a garbled sentence. Closed by splicing **by block**:
:func:`~larkdocio.model.projection.replace_block_markdown` replaces a block's whole segment,
line count and all, and the recipe uses it.

Every assertion below runs through the shipped surfaces — a real parsed tree, the real
projection, the real resolver — never a hand-written spelling of what they are believed to
emit.
"""
import random
import re

import pytest

from harness import build_blocks

from larkdocio.model import project_block_ids
from larkdocio.model.projection import block_markdown, replace_block_markdown
from larkdocio.model.renderer import unescape_literals
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.compiler import compile_reconciliation
from larkdocio.write.model import Anchor, EditRequest, RefusalReason, SubSpanEditRequest
from larkdocio.write.preview import dry_run
from larkdocio.write.reconcile import reconcile
from larkdocio.write.resolve import block_plain_text, longest_matching_fragment

# The measured shape: one text run whose content carries a literal newline mid-sentence,
# exactly where terminal word-wrap would have put one.
SOFT_RETURN = "Revenue grew 12.4% in\nQ3. The board asked for a breakdown by region."


def _text(bid, parent, content, block_type=2, key="text"):
    return {"block_id": bid, "parent_id": parent, "block_type": block_type,
            key: {"elements": [{"text_run": {"content": content}}]},
            "children": []}


def _document(*body_blocks):
    ids = [b["block_id"] for b in body_blocks]
    blocks = [{"block_id": "root", "parent_id": "", "block_type": 1,
               "page": {"elements": [{"text_run": {"content": "Overview"}}]},
               "children": ids}] + list(body_blocks)
    return Parser(Config()).parse_docx_tree("root", build_blocks(blocks))


def _tree(*, extra=()):
    return _document(_text("p1", "root", SOFT_RETURN), *extra)


def _refusal(quote, root, breadcrumb=()):
    plan = dry_run(
        [EditRequest(anchor=Anchor(quote=quote, breadcrumb=breadcrumb), replacement="X")],
        root,
    )
    entry, = plan.entries
    assert entry.refusal is not None, f"expected a refusal, got {entry}"
    return entry.refusal


# --------------------------------------------------------------------------- #
# The premise, measured rather than assumed.                                   #
# --------------------------------------------------------------------------- #

def test_premise_the_soft_return_survives_into_the_projection_as_a_bare_wrap():
    """The trap exists because the projection shows a soft return as an ordinary line
    break: the block occupies TWO Markdown lines and only the first carries a marker, so
    nothing on the page says the second line belongs to the same block."""
    root = _tree()
    projection = project_block_ids(root)
    assert "\n" in block_plain_text(root.children[0])
    body = block_markdown(projection, "p1")
    assert len(body.splitlines()) == 2, body
    # ...and the two lines are what a consumer reads as one wrapped sentence.
    assert unescape_literals(body).replace("\n", " ") == SOFT_RETURN.replace("\n", " ")


# --------------------------------------------------------------------------- #
# AC1 — a whitespace-only near-miss is NAMED, not hidden.                      #
# --------------------------------------------------------------------------- #

def test_ac1_a_whitespace_only_near_miss_names_the_block():
    """The quote a consumer copies off the wrapped sentence differs from the stored text
    by one character. The refusal now says which block and why."""
    root = _tree()
    refusal = _refusal("Revenue grew 12.4% in Q3.", root)
    assert refusal.reason is RefusalReason.NOT_FOUND
    assert "block 'p1' differs only in whitespace" in refusal.detail


def test_ac1_the_refusal_carries_the_actual_stored_spelling():
    """"Which whitespace?" is answerable only by showing the stored text — and ``repr``
    is what makes an invisible ``\\n`` visible."""
    refusal = _refusal("Revenue grew 12.4% in Q3.", _tree())
    assert repr(SOFT_RETURN) in refusal.detail


def test_ac1_the_refusal_offers_a_short_fragment_that_actually_matches():
    """The concrete repair, not an instruction to try again: a fragment of the caller's
    own quote that IS verbatim in the block. The test proves it by using it."""
    root = _tree()
    refusal = _refusal("Revenue grew 12.4% in Q3.", root)
    fragment = "Revenue grew 12.4% in"
    assert repr(fragment) in refusal.detail
    plan = dry_run([EditRequest(anchor=Anchor(quote=fragment), replacement="X")], root)
    assert plan.entries[0].refusal is None, plan.entries[0]


def test_ac1_the_refusal_stays_a_refusal_and_nothing_is_normalized():
    """The remedy is a diagnostic, never a looser matcher: the near-miss quote still
    refuses, and no plan entry resolves off a whitespace-normalized comparison."""
    root = _tree()
    plan = dry_run(
        [EditRequest(anchor=Anchor(quote="Revenue grew 12.4% in Q3."), replacement="X")],
        root,
    )
    assert plan.entries[0].refusal is not None
    assert plan.entries[0].refusal.reason is RefusalReason.NOT_FOUND


# --------------------------------------------------------------------------- #
# AC2 — the diagnostic is honest when it is NOT certain.                       #
# --------------------------------------------------------------------------- #

def test_ac2_more_than_one_normalized_match_says_ambiguous_and_names_every_candidate():
    """Two blocks that differ from the quote only in whitespace is not a near-miss the
    engine may resolve — it is the ambiguous-N-candidates shape, and every id is named."""
    root = _tree(extra=(_text("p2", "root", SOFT_RETURN),))
    # both p1 and p2 hold the same soft-return text; the root's children carry both.
    refusal = _refusal("Revenue grew 12.4% in Q3.", root)
    assert "ambiguous after whitespace normalization" in refusal.detail
    assert "candidate ids: p1, p2" in refusal.detail
    # ...and no single block is named as THE near-miss: the diagnostic never auto-picks.
    assert "block 'p1' differs only in whitespace" not in refusal.detail


def test_ac2_a_genuinely_absent_quote_keeps_the_ordinary_diagnosis():
    """A typo is still a typo. The evidence gate is what keeps the ordinary wording for
    every case that is not a whitespace near-miss."""
    refusal = _refusal("nothing in this document says this", _tree())
    assert "differs only in whitespace" not in refusal.detail
    assert "ambiguous after whitespace normalization" not in refusal.detail
    assert "no block's own text contains the anchor quote" in refusal.detail


def test_ac2_the_circular_remedy_is_gone_from_the_not_found_detail():
    """"Re-read the document and copy the quote verbatim" is exactly what the consumer
    just did. It is replaced everywhere by advice that is a different action."""
    for quote in ("nothing in this document says this", "Revenue grew 12.4% in Q3."):
        detail = _refusal(quote, _tree()).detail
        assert "re-read the document and copy the quote verbatim" not in detail
        assert "AnchorById" in detail


@pytest.mark.parametrize("quote", ["- ", "# ", "> ", "1. ", "97.2%", "  "])
def test_ac2_a_single_token_quote_never_fires_the_near_miss(quote):
    """The gate is two or more words, and this is why: a lone token normalizes to something
    a long document contains by accident, so "differs only in whitespace" would be
    technically true and useless. Caught in development by the F20 marker guards
    (``tests/test_round3_minors.py``) firing on ``"- "`` against a heading with a hyphen."""
    detail = _refusal(quote, _tree()).detail
    assert "differs only in whitespace" not in detail


def test_ac2_the_not_found_detail_states_that_the_match_is_against_raw_stored_text():
    """The one fact that makes the whole class of failure predictable rather than
    mysterious, said at the moment of failure."""
    detail = _refusal("Revenue grew 12.4% in Q3.", _tree()).detail
    assert "raw stored text" in detail.lower()
    assert "soft return" in detail.lower()


# --------------------------------------------------------------------------- #
# AC1/AC2 — the same trap on the SUB-SPAN path (the flagship recipe's own).     #
# --------------------------------------------------------------------------- #

def test_the_subspan_span_gets_the_same_named_near_miss():
    """``SubSpanEditRequest.span`` is matched byte-verbatim against the block's text runs,
    so it carries the identical trap — and now the identical diagnostic. Only one block is
    in play here, so the answer is never ambiguous."""
    root = _tree()
    plan = dry_run(
        [SubSpanEditRequest(anchor=Anchor(quote="Revenue grew"),
                            span="in Q3. The board",
                            replacement="in Q3. The committee")],
        root,
    )
    refusal = plan.entries[0].refusal
    assert refusal is not None and refusal.reason is RefusalReason.NOT_FOUND
    assert "differs only in whitespace" in refusal.detail
    assert repr(SOFT_RETURN) in refusal.detail


def test_a_span_that_is_simply_absent_keeps_the_ordinary_subspan_diagnosis():
    root = _tree()
    plan = dry_run(
        [SubSpanEditRequest(anchor=Anchor(quote="Revenue grew"),
                            span="not in the block at all",
                            replacement="x")],
        root,
    )
    refusal = plan.entries[0].refusal
    assert refusal is not None
    assert "differs only in whitespace" not in refusal.detail
    assert "does not occur in the text runs of block" in refusal.detail


# --------------------------------------------------------------------------- #
# AC3 — the silent garble is closed.                                           #
# --------------------------------------------------------------------------- #

def _reconciled_text(projection, edited, block_id="p1"):
    """What the round trip would actually WRITE for ``block_id`` — the compiled request's
    replacement, not ``plan.ok``. The garble was invisible to ``plan.ok`` by construction."""
    plan = reconcile(projection, edited)
    assert plan.ok, [r.detail for r in plan.refusals]
    requests = compile_reconciliation(plan, projection)
    replacements = [
        r.replacement for r in requests
        if isinstance(r, EditRequest) and r.anchor.block_id == block_id
    ]
    assert len(replacements) == 1, requests
    return replacements[0]


def test_ac3_the_line_splice_is_what_garbled_the_sentence():
    """Root cause, characterized so the fix cannot be mistaken for a coincidence: the
    recipe's old idiom — find the LINE that starts with X and replace that line — rewrites
    only part of a multi-line block, and the surviving tail duplicates the new text's
    ending. The reconciler is not wrong here; it is being handed a garbled document."""
    projection = project_block_ids(_tree())
    lines = projection.markdown.splitlines(keepends=True)
    i = next(n for n, line in enumerate(lines)
             if unescape_literals(line).startswith("Revenue grew"))
    lines[i] = "Revenue grew 15.0% in Q3.\n"
    written = _reconciled_text(projection, "".join(lines))
    assert written == "Revenue grew 15.0% in Q3.\nQ3. The board asked for a breakdown by region."
    assert written.count("Q3.") == 2          # the garble, in one number


def test_ac3_splicing_by_block_writes_exactly_what_was_asked_for():
    """The fix: replace the BLOCK, not a line. The post-apply text is asserted — the whole
    point is that ``plan.ok`` was already True for the garbled one."""
    projection = project_block_ids(_tree())
    new_text = "Revenue grew 15.0% in Q3."
    edited = replace_block_markdown(projection, "p1", new_text)
    assert _reconciled_text(projection, edited) == new_text


def test_ac3_a_block_safe_splice_leaves_every_other_block_alone():
    """Surgical: only the target block's segment moves, markers and neighbours intact."""
    root = _tree(extra=(_text("p2", "root", "A second paragraph, left alone."),))
    projection = project_block_ids(root)
    edited = replace_block_markdown(projection, "p1", "Revenue grew 15.0% in Q3.")
    plan = reconcile(projection, edited)
    assert plan.ok, [r.detail for r in plan.refusals]
    assert plan.touched_block_ids == ("p1",)


def test_ac3_replacing_a_block_that_the_projection_never_emitted_refuses():
    """Identity comes from the emitted id set here too — a helper that accepted any string
    would be a second, weaker identity test living next to the strong one."""
    projection = project_block_ids(_tree())
    with pytest.raises(ValueError) as excinfo:
        replace_block_markdown(projection, "not-an-emitted-id", "x")
    assert "not-an-emitted-id" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# AC4 — the taught example stops teaching the failure.                         #
# --------------------------------------------------------------------------- #

#: A literal anchor **construction** — ``Anchor(quote=...)``. Deliberately not every
#: ``quote=`` in the corpus: the release notes quote the OLD example verbatim to say it was
#: replaced, and a guard that could not tell a citation from an instruction would force the
#: history to be rewritten to stay green.
_ANCHOR_QUOTE = re.compile(r'Anchor\(quote=(?:"([^"\n]*)"|\'([^\'\n]*)\')')


def _taught_quotes():
    """Every literal anchor quote a consumer meets, per shipped surface."""
    from consumer_text import shipped_docs

    out = []
    for label, text in shipped_docs().items():
        for match in _ANCHOR_QUOTE.finditer(text):
            out.append((label, match.group(1) if match.group(1) is not None else match.group(2)))
    return out


def test_ac4_no_shipped_anchor_quote_example_teaches_a_whole_sentence():
    """The habit the guide taught is the habit that failed: a full sentence spanning a wrap.
    A taught quote is a **short fragment** — no sentence terminator, and short enough that it
    cannot straddle a soft return. Bidirectional in spirit: the corpus is scanned rather than
    a known list of files checked, so a new recipe cannot reintroduce the old example."""
    taught = _taught_quotes()
    assert taught, "the scan found no anchor-quote examples at all — the regex went stale"
    offenders = [
        (label, quote) for label, quote in taught
        if quote.rstrip().endswith((".", "!", "?")) or len(quote.split()) > 6
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("surface", ["guide", "writer_brief", "anchor-docstring"])
def test_ac4_the_anchor_doctrine_names_raw_stored_text_and_the_soft_return(surface):
    """One sentence, in every place the doctrine is looked up: the match is against RAW
    STORED text, which may carry a soft return the Markdown does not show."""
    import larkdocio

    text = {
        "guide": lambda: larkdocio.guide(full=True),
        "writer_brief": lambda: larkdocio.writer_brief(),
        "anchor-docstring": lambda: Anchor.__doc__,
    }[surface]()
    flat = " ".join(text.split()).lower()
    assert "raw stored" in flat
    assert "soft return" in flat


def test_block_markdown_round_trips_through_replace():
    """``replace_block_markdown(p, b, block_markdown(p, b))`` is the identity — the pair is
    a read/write pair over the same segment, not two independent guesses at where a block
    starts and stops."""
    for extra in ((), (_text("p2", "root", "Tail."),)):
        projection = project_block_ids(_tree(extra=extra))
        for block_id in projection.block_ids:
            if block_id in projection.opaque_block_ids:
                continue
            same = replace_block_markdown(
                projection, block_id, block_markdown(projection, block_id)
            )
            assert same == projection.markdown, block_id


# --------------------------------------------------------------------------- #
# LD-636 — the SAME-RESULT speedup of the explanation the refusal computes.    #
#                                                                              #
# ``longest_matching_fragment`` runs ONLY on the refusal path — in exactly the  #
# scenario the hedge above exists to diagnose — and the scan it used to do was  #
# superlinear: 3.3 s end-to-end through ``dry_run`` on a 1200-word quote on the #
# host that cut these tests, multiplied per plan entry. Nothing is written and  #
# the answer is right, so the whole cost buys the EXPLANATION; a preview that   #
# feels hung is one a consumer kills, losing the refusal detail that was the    #
# point. The replacement binary-searches the maximum run per start (containment #
# is monotone in run length for a fixed start), which is a cheaper search for   #
# the SAME string — never a cap and never a truncation, which would change what #
# the consumer is told and would not be a refactor at all.                      #
# --------------------------------------------------------------------------- #

def _oracle_longest_matching_fragment(quote, stored):
    """The pre-LD-636 exhaustive scan, kept as the ORACLE rather than the implementation.

    It is the definition of the answer — including the tie-break, which is what a rewrite
    could silently move: the winner is the longest run in *characters*, and among equal-length
    runs the one whose start comes earliest (``>`` never ``>=``, over ``i`` then ``j``
    ascending). Slow by construction; that is why it is here and not in ``src``.
    """
    words = quote.split()
    best = ""
    for i in range(len(words)):
        piece = ""
        for j in range(i, len(words)):
            piece = words[j] if j == i else f"{piece} {words[j]}"
            if piece not in stored:
                break
            if len(piece) > len(best):
                best = piece
    return best


def test_ld636_the_realistic_case_still_returns_THE_SAME_FRAGMENT():
    """The pinned string from ``test_ac1_...offers_a_short_fragment`` is the anchor case, and
    the oracle agrees with the shipped function on it. Asserted here as an equality against
    the oracle too, so this file cannot drift into pinning only a literal."""
    quote = "Revenue grew 12.4% in Q3."
    assert longest_matching_fragment(quote, SOFT_RETURN) == "Revenue grew 12.4% in"
    assert (longest_matching_fragment(quote, SOFT_RETURN)
            == _oracle_longest_matching_fragment(quote, SOFT_RETURN))


@pytest.mark.parametrize("quote,stored,expected", [
    # A GENUINE TIE — added by LD-628 AC1e because the two cases below it are NOT ties and
    # were documented as if they were. Both ``aa bb`` and ``cc dd`` are contained in the
    # stored text at 5 characters each, so the earliest start decides, and this is the ONE
    # case in this list that flipping the oracle's ``>`` to ``>=`` reddens (measured: with
    # ``>=`` the oracle answers ``cc dd``). Do not "simplify" the stored spelling: the ZZ is
    # what keeps ``bb cc`` from matching and so keeps the two runs equal and disjoint.
    ("aa bb cc dd", "aa bb ZZ cc dd", "aa bb"),
    # A LONE WINNER at 5 characters — the longest-run rule itself, not the tie-break. Its
    # docstring used to read "two runs of EQUAL character length"; measured by LD-636's QA and
    # re-measured here, ``aa bb`` (5) is the only maximal run and ``dd``/``cc`` trail at 2, so
    # the sentence was false about its own fixture while the assertion stayed true.
    ("aa bb cc dd", "aa bb ZZ dd cc", "aa bb"),
    # ...and the mirror: a lone winner at 7 characters that starts LATER, so the two cases
    # above are not passing for the trivial reason that earlier always wins.
    ("aa bb ccc ddd", "aa bb ZZ ccc ddd", "ccc ddd"),
    # A single word that matches, and a single word that does not.
    ("solo word", "a solo elsewhere", "solo"),
    ("nothing here matches", "unrelated text", ""),
    # Empty and whitespace-only quotes reach the function from the sub-span path.
    ("", "anything", ""),
    ("   ", "anything", ""),
    # The whole quote is present: the answer is the whole quote.
    ("all of it", "and all of it too", "all of it"),
])
def test_ld636_tie_breaking_and_the_edges_are_pinned_by_case(quote, stored, expected):
    """By-case pins for the edges and for the tie-break, each case labelled with what it
    actually proves (LD-628 AC1e: the labels had drifted off the fixtures — only the case
    added there ties at all; the rest pin the longest-run rule and the empty edges, and the
    randomized oracle agreement below is what exercises ties in bulk)."""
    assert longest_matching_fragment(quote, stored) == expected
    assert _oracle_longest_matching_fragment(quote, stored) == expected


def test_ld636_the_fast_search_agrees_with_the_oracle_over_RANDOMIZED_inputs():
    """The property, not a sample: for arbitrary quote/stored pairs the two implementations
    return the **identical string**. A small repeating vocabulary is deliberate — it is what
    manufactures equal-length runs and accidental matches, i.e. the tie-breaks a hand-picked
    case never reaches. Seeded, so a failure is reproducible."""
    rng = random.Random(20260903)
    vocab = ["a", "ab", "abc", "b", "bb", "x", "yy", "zzz", "the", "of", "12.4%"]
    checked = 0
    for _ in range(2000):
        quote = " ".join(rng.choice(vocab) for _ in range(rng.randint(0, 9)))
        stored = rng.choice([" ", " ", " ", "\n", "", "  "]).join(
            rng.choice(vocab) for _ in range(rng.randint(0, 14))
        )
        assert (longest_matching_fragment(quote, stored)
                == _oracle_longest_matching_fragment(quote, stored)), (quote, stored)
        checked += 1
    assert checked == 2000


#: Ceiling on the CPU the whole refusal — resolution, the hedge, and the fragment it
#: computes — burns **per word of the quote**, measured end-to-end through ``dry_run`` on the
#: reachable soft-return scenario. ``time.process_time()`` for the same reason
#: ``tests/test_no_test_reads_live_git.py`` uses it: a contended host must not be able to
#: inflate it. Cut 2026-09-03 (LD-636) at ~3.5x the value measured on the host that cut it —
#: **83-87 us/word** at 1200 words (Apple Silicon, CPython 3.14) — against **~2725 us/word**
#: for the scan this replaced, so the bound sits an order of magnitude below the regression it
#: exists to catch. What would legitimately move it: a host materially slower per word. What
#: must NOT move it: a busy machine (excluded by construction) or a longer quote (the cost
#: divides out only if the search stays sub-quadratic, which is the whole claim).
MAX_REFUSAL_CPU_MICROSECONDS_PER_WORD = 300.0


def test_ld636_the_refusal_path_stays_CHEAP_PER_WORD_OF_CPU():
    """The win, kept won. This is the reachable scenario and nothing else: a 1200-word quote
    that differs from the stored text by exactly one space-turned-newline, resolved through
    the shipped ``dry_run`` — never the inner function alone, because a component's cost is
    not a finding until the reachable path that pays it is shown."""
    import time

    vocab = ("revenue grew in the third quarter and the board asked for a breakdown by "
             "region while margin held broadly flat across every line of business").split()
    words = [vocab[i % len(vocab)] for i in range(1200)]
    quote = " ".join(words)
    cut = quote.index(" ", len(quote) // 2)           # one space becomes a soft return
    stored = quote[:cut] + "\n" + quote[cut + 1:]
    root = _document(_text("p1", "root", stored))

    started = time.process_time()
    plan = dry_run([EditRequest(anchor=Anchor(quote=quote), replacement="X")], root)
    per_word = (time.process_time() - started) * 1e6 / len(words)

    refusal = plan.entries[0].refusal
    assert refusal is not None and "differs only in whitespace" in refusal.detail
    assert per_word < MAX_REFUSAL_CPU_MICROSECONDS_PER_WORD, f"{per_word:.1f} us/word"

    # AND THE ANSWER, NOT ONLY THE COST (LD-628 AC1e(ii)). LD-636's AC forbade buying the
    # speedup with a cap or a truncation, and nothing in this file could see one: LD-636's QA
    # introduced an 8-word cap and all 70 tests stayed green, because the randomized
    # vocabulary never produces an 8-word verbatim match at any quote length. This fixture is
    # the one that can see it — its correct answer is the whole prefix before the soft return,
    # which is 600 words long — so any cap or truncation reddens HERE, at no extra cost.
    assert longest_matching_fragment(quote, stored) == quote[:cut]


def test_ld636_the_batch_that_multiplied_the_cost_is_the_same_bound_per_entry():
    """The finding was not one slow refusal but ten: the fragment is recomputed per plan
    entry, so a ``dry_run`` of ten near-miss edits paid it ten times (measured 2.5 s before
    the fix, 0.12 s after, for ten 500-word entries). Asserted per entry-word so the bound
    above is the same bound here."""
    import time

    vocab = ("revenue grew in the third quarter and the board asked for a breakdown by "
             "region while margin held broadly flat across every line of business").split()
    words = [vocab[i % len(vocab)] for i in range(500)]
    quote = " ".join(words)
    cut = quote.index(" ", len(quote) // 2)
    stored = quote[:cut] + "\n" + quote[cut + 1:]
    root = _document(_text("p1", "root", stored))
    requests = [EditRequest(anchor=Anchor(quote=quote), replacement=f"X{n}")
                for n in range(10)]

    started = time.process_time()
    plan = dry_run(requests, root)
    per_word = (time.process_time() - started) * 1e6 / (len(words) * len(requests))

    assert all(entry.refusal is not None for entry in plan.entries)
    assert per_word < MAX_REFUSAL_CPU_MICROSECONDS_PER_WORD, f"{per_word:.1f} us/word"
