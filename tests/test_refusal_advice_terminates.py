"""LD-670 — following the advice in a refusal must not produce another refusal that
advises the original input.

The defect this file exists for was a **composition** defect, not a wording one.
``TextSpan.__post_init__`` ran two link-URL validators in sequence: the percent-encoded one
advised the decoded spelling, the whitespace one advised "a URL with no whitespace in it", and
for a URL whose encoding HIDES whitespace (``%20`` — what every browser produces for a space)
each one's advice was the other one's input. Neither refusal ever said the URL was unauthorable.

So the two string pins here are the small half. **The property is the deliverable** (AC5): a
bounded follow-the-advice walk that extracts the advised spelling out of a refusal, re-submits
it, and fails when obedience is itself refused. A third validator added tomorrow is caught by it
without anybody remembering this issue existed. AC6 runs the same walk over the whole validation
family the defect lived in, and the family is derived by an AST walk rather than hand-listed.

Note the property is *"following the advice must not produce another refusal"* rather than
*"must not point back at the original input"*. The stronger form is the one that works: the
return leg of the shipped loop was **prose** — "pass a URL with no whitespace in it" names no
literal — so a cycle detector would have watched this exact defect and reported nothing.
"""

import ast
import dataclasses
import pathlib
import re
import urllib.parse

import pytest

import private_tree

from larkdocio.write.model.anchors import AnchorById, CommentThread, TableLocator
from larkdocio.write.model.refusal import Refusal, RefusalReason
from larkdocio.write.model.requests import (
    UNAUTHORABLE_WHITESPACE_URL_ADVICE,
    CreateCommentRequest,
    GrowTableRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewBlockKind,
    SubSpanEditRequest,
    TextSpan,
)

WRITE_MODEL = pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio" / "write" / "model"


# --------------------------------------------------------------------------- #
# The instrument: a bounded follow-the-advice walk (AC5)                       #
# --------------------------------------------------------------------------- #

#: An apostrophe INSIDE a word ("the reader's own Markdown") is not a quote, and a naive
#: `'([^']*)'` scan reads the prose between two of them as a spelling — which is how a first cut
#: of this extractor "found advice" in every message and turned the walk into noise. Neutralised
#: before the scan, and restored inside a candidate, so a repr'd value keeps its bytes.
_INTRA_WORD_APOSTROPHE = re.compile(r"(?<=\w)'(?=\w)")
_REPR_QUOTED = re.compile(r"'([^']*)'")
_SENTINEL = "\x00"


def advised_spellings(message, value):
    """Every concrete spelling a refusal hands back that a caller could RE-SUBMIT.

    A refusal quotes two different kinds of string and only one of them is advice. The input's
    own repr is a **quotation** of what was rejected; any *other* repr'd spelling is an
    **instruction** — "pass this instead" — and is what a reader will type next. So the rule is
    exactly that: a repr'd run that differs from the value under test.

    Single quotes only, deliberately: this is what a validator's own ``{x!r}`` emits, whereas a
    double-quoted run in one of these messages is prose quoting somebody else (Lark's
    ``"param error"``), which is a citation and not something to type.

    Deliberately not cleverer than that. Extracting advice by understanding the sentence would
    make the guard as fallible as the code it watches; a caller reads quoted strings too.
    """
    found = []
    cleaned = _INTRA_WORD_APOSTROPHE.sub(_SENTINEL, message)
    for match in _REPR_QUOTED.finditer(cleaned):
        candidate = match.group(1).replace(_SENTINEL, "'")
        if candidate != value and candidate not in found:
            found.append(candidate)
    return found


def follow_the_advice(build, start, max_steps=8):
    """Submit ``start``; do exactly what each refusal says; fail if obedience is refused.

    **The property, stated once:** a refusal that names a spelling to use instead must name one
    this same constructor ACCEPTS. Anything else hands a caller an instruction and then rejects
    their compliance — and it does not matter whether the second refusal points literally back
    at the first input (the ``%20`` ping-pong) or merely sideways: either way the advice was not
    a way out. This is a strictly stronger property than "no cycle", and it is mechanical, which
    "no cycle" is not: the return leg of the shipped loop was prose ("pass a URL with no
    whitespace in it"), so a cycle detector alone would have watched the defect and said nothing.

    Returns the trace — ``(value, message_or_None)`` per step, ``None`` meaning ACCEPTED. A walk
    terminates two legitimate ways: the value is accepted, or the refusal names no alternative
    spelling at all — a **terminating refusal**, which is the honest answer when nothing the
    caller can type would work, and is exactly what LD-670 added.
    """
    trace = []
    refused = {}
    pending = [start]
    while pending:
        value = pending.pop(0)
        if len(trace) >= max_steps:
            raise AssertionError(
                f"the follow-the-advice walk from {start!r} did not terminate in {max_steps} "
                f"steps; trace so far: {[v for v, _ in trace]}")
        try:
            build(value)
        except (ValueError, TypeError) as exc:
            message = str(exc)
        else:
            trace.append((value, None))
            continue
        trace.append((value, message))
        if value != start:
            raise AssertionError(
                f"ADVICE REFUSED: {refused[value]!r} was refused with advice to pass "
                f"{value!r} instead, and {value!r} is refused too — the caller was told to do "
                f"something and then told off for doing it. Second message: {message}")
        for advised in advised_spellings(message, value):
            refused[advised] = value
            pending.append(advised)
    return trace


def _span(url):
    return TextSpan("x", link_url=url)


# --------------------------------------------------------------------------- #
# AC5 — the loop itself is the test                                            #
# --------------------------------------------------------------------------- #

# Every row is a link URL a caller can plausibly hold. The two `%20`/`%09` rows are the defect;
# `%2D` is the CONTROL that keeps the fix small — its advice is correct and must stay.
FOLLOW_THE_ADVICE_URLS = [
    "https://example.com/a%20b",     # the browser-copied case: encoding HIDES whitespace
    "https://example.com/a b",       # the same URL from the other side
    "https://example.com/a%09b",     # a tab, hidden the same way
    "https://example.com/a%2Db",     # CONTROL: decodes to a-b, which is authorable
    "https%3A%2F%2Fexample.com",      # CONTROL: a wholly encoded URL, decodes clean
    "https://example.com/a-b",       # accepted outright
]


@pytest.mark.parametrize("url", FOLLOW_THE_ADVICE_URLS)
def test_following_a_link_url_refusal_never_produces_another_refusal(url):
    """AC5. The assertion that would have caught the defect, and it is worth more than the two
    string pins below: it knows nothing about whitespace or percent-encoding."""
    trace = follow_the_advice(_span, url)
    assert trace and trace[0][0] == url


def test_the_walk_is_NON_VACUOUS_it_really_does_follow_advice_somewhere():
    """A walk that never found any advice would pass every row above while measuring nothing.
    The control row proves the extractor works: it is refused, it advises a different spelling,
    and that spelling is ACCEPTED — three steps of real following."""
    trace = follow_the_advice(_span, "https://example.com/a%2Db")
    assert [v for v, _ in trace] == ["https://example.com/a%2Db", "https://example.com/a-b"]
    assert trace[0][1] is not None and trace[1][1] is None


def test_the_walk_CATCHES_the_defect_when_the_old_advice_is_put_back():
    """The instrument's own red-watch, in-process: a stand-in constructor that gives exactly the
    advice the shipped code used to give is caught as a loop. Without this, a green walk above
    might mean 'terminates' or might mean 'the extractor found nothing'."""
    def old_shape(url):
        if any(ch.isspace() for ch in url):
            raise ValueError(f"the link URL {url!r} carries whitespace: pass a URL with no "
                             f"whitespace in it")
        decoded = urllib.parse.unquote(url)
        if decoded != url:
            raise ValueError(f"the link URL {url!r} is PERCENT-ENCODED. Pass the URL "
                             f"undecorated: {decoded!r}")

    with pytest.raises(AssertionError, match="ADVICE REFUSED"):
        follow_the_advice(old_shape, "https://example.com/a%20b")
    # and the control still terminates under the OLD shape, which is why the fix is small
    follow_the_advice(old_shape, "https://example.com/a%2Db")


# --------------------------------------------------------------------------- #
# AC1 / AC3 / AC4 — pinned by EMISSION, both messages, both entry orders       #
# --------------------------------------------------------------------------- #

def _refusal(url):
    with pytest.raises(ValueError) as exc:
        _span(url)
    return str(exc.value)


def test_ac1_the_percent_refusal_of_a_whitespace_HIDING_url_states_the_truth():
    message = _refusal("https://example.com/a%20b")
    # the WHY survives — the reason the round trip fails is still stated
    assert "PERCENT-ENCODED" in message and "unescape_url" in message
    # …and the advice that used to close it, and was itself refused, is gone
    assert "Pass the URL undecorated" not in message
    # …replaced by the terminating sentence: no spelling works, and here are the two ways out
    assert UNAUTHORABLE_WHITESPACE_URL_ADVICE in message
    assert "NO spelling of this URL can be authored as a link anchor" in message
    assert "PLAIN TEXT" in message and "redirect" in message


def test_ac3_the_WHITESPACE_refusal_carries_the_same_terminating_sentence():
    """AC3, decided by execution: it does need it. A caller who starts from ``a b`` is told 'no
    whitespace', re-encodes to ``a%20b`` in good faith, and lands in the loop from the other
    side — so the truth has to be on the door they came in through as well."""
    message = _refusal("https://example.com/a b")
    assert "carries whitespace" in message           # the original reason, unchanged
    assert UNAUTHORABLE_WHITESPACE_URL_ADVICE in message


def test_ac3_neither_entry_order_leaves_a_caller_without_a_terminating_answer():
    for url in ("https://example.com/a%20b", "https://example.com/a b"):
        trace = follow_the_advice(_span, url)
        assert len(trace) == 1                        # a terminating refusal: no new advice
        assert UNAUTHORABLE_WHITESPACE_URL_ADVICE in trace[0][1]


# The EXACT bytes develop emitted for the non-looping case. Pinned as a literal on purpose:
# AC2 is a claim about what a previous release said, and a literal is the only thing that can
# hold it. Derived, not typed — produced by evaluating develop's own raise expression at the
# time and comparing (Dev handoff records the run; both control rows came back identical).
_DEVELOP_PERCENT_MESSAGE = (
    "the link URL 'https://example.com/a%2Db' is PERCENT-ENCODED, and this library authors a link "
    "URL VERBATIM. Lark itself accepts both spellings and echoes each back unchanged "
    "(measured), so the server does not settle this; what settles it is that the reader "
    "percent-DECODES a link URL on the way back out (larkdocio.common.url.unescape_url), so "
    "an encoded spelling does not survive the round trip through the reader's own Markdown. "
    "The raw spelling is the one a click confirmed opens. Pass the URL undecorated: "
    "'https://example.com/a-b'"
)


def test_ac2_the_NON_LOOPING_percent_refusal_is_unchanged_byte_for_byte():
    """AC2 — this is what keeps the fix small. Where the decoded spelling is whitespace-free the
    advice is CORRECT (a click confirmed the raw spelling opens), so not one byte moves."""
    assert _refusal("https://example.com/a%2Db") == _DEVELOP_PERCENT_MESSAGE
    assert UNAUTHORABLE_WHITESPACE_URL_ADVICE not in _refusal("https%3A%2F%2Fexample.com")


def test_ac2_the_refusal_SET_did_not_move_only_what_it_says():
    """No previously-accepted input becomes refused and no previously-refused input becomes
    accepted — the consumer-facing promise the release notes make."""
    refused = ["https://example.com/a%20b", "https://example.com/a b", "https://example.com/a%2Db", ""]
    accepted = ["https://example.com/a-b", "https://example.com/a+b", "https://example.com/a~b",
                "https://example.com/100%", "mailto:someone@example.com"]
    for url in refused:
        with pytest.raises(ValueError):
            _span(url)
    for url in accepted:
        assert _span(url).link_url == url


# --------------------------------------------------------------------------- #
# AC6 — does any OTHER validator in this family loop?                          #
# --------------------------------------------------------------------------- #

def _post_init_validators():
    """The family, DERIVED: every ``__post_init__`` under ``write/model/**`` and how many raise
    sites it has. A hand-listed population cannot notice a validator it was never told about."""
    found = {}
    for path in sorted(WRITE_MODEL.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for node in cls.body:
                if isinstance(node, ast.FunctionDef) and node.name == "__post_init__":
                    raises = [n for n in ast.walk(node) if isinstance(n, ast.Raise)]
                    found[(path.name, cls.name)] = len(raises)
    return found


# One row per validator that can refuse at all, with a probe that MAKES it refuse. The set is
# held equal to the AST-derived population below, so this table cannot quietly fall behind.
FAMILY_WALKS = {
    ("requests.py", "TextSpan"): (lambda v: TextSpan("x", link_url=v), "https://example.com/a%20b"),
    ("requests.py", "NewBlock"): (
        lambda v: NewBlock(kind=NewBlockKind.CODE, text="x", language=v), "kotlinn"),
    ("requests.py", "InsertRequest"): (
        lambda v: InsertRequest(reference=AnchorById(v), position=InsertPosition.AFTER,
                                content=()), "blk123"),
    ("requests.py", "SubSpanEditRequest"): (
        lambda v: SubSpanEditRequest(anchor=AnchorById("blk123"), span=v, replacement="x"), ""),
    ("requests.py", "GrowTableRequest"): (
        lambda v: GrowTableRequest(anchor=TableLocator(row_key="r", column_index=0),
                                   row_index=v), "1"),
    ("requests.py", "CreateCommentRequest"): (lambda v: CreateCommentRequest(text=v), ""),
    ("anchors.py", "TableLocator"): (lambda v: TableLocator(row_key=v), "Example Item"),
    ("anchors.py", "AnchorById"): (lambda v: AnchorById(block_id=v), ""),
    ("anchors.py", "CommentThread"): (lambda v: CommentThread(comment_id=v), ""),
    ("refusal.py", "Refusal"): (
        lambda v: Refusal(reason=RefusalReason.NOT_FOUND, detail=v), ""),
}


def test_ac6_the_walk_table_covers_EXACTLY_the_validators_that_can_refuse():
    """The population question, kept live. A new ``__post_init__`` with a raise in it — or an
    existing one that grows its first raise — reddens here until somebody has run the walk over
    it, which is the check the two-validator composition never got."""
    population = _post_init_validators()
    assert population, "the AST walk found no __post_init__ at all — the guard has gone blind"
    can_refuse = {key for key, count in population.items() if count}
    silent = {key for key, count in population.items() if not count}
    assert set(FAMILY_WALKS) == can_refuse, (
        f"walk table vs derived family: missing {sorted(can_refuse - set(FAMILY_WALKS))}, "
        f"stale {sorted(set(FAMILY_WALKS) - can_refuse)}")
    # …and the ones with no raise are named rather than counted, so 'the family' is complete:
    # a validator that only normalises cannot advise anything and has nothing to walk.
    assert silent == {("anchors.py", "Anchor"), ("applylog.py", "ApplyLogEntry"),
                      ("applylog.py", "ApplyLog")}


@pytest.mark.parametrize("key", sorted(FAMILY_WALKS))
def test_ac6_no_other_validator_in_the_family_advises_a_spelling_it_then_refuses(key):
    build, probe = FAMILY_WALKS[key]
    trace = follow_the_advice(build, probe)
    # Non-vacuity, per row: the probe must actually reach a refusal, or this row tests nothing.
    assert trace[0][1] is not None, f"{key} probe {probe!r} was accepted — pick a refusing probe"


# Values chosen to trip a validator in as many different ways as this family allows: an empty
# string, a whitespace-bearing one, both percent-encoded shapes, and one over every documented
# cap. Fed to EVERY row, because a validator only advises when something actually refuses.
ADVERSARIAL_PROBES = (
    "", " ", "x", "https://example.com/a b", "https://example.com/a%20b", "https://example.com/a%2Db",
    "https%3A%2F%2Fexample.com", "kotlinn", "1", "-1", "9" * 60, "文" * 3,
)


def test_ac6_exactly_ONE_validator_in_the_family_hands_back_a_RE_SUBMITTABLE_spelling():
    """The derived figure the AC asks for — derived by EXECUTION, not by reading source.

    Every row of the family is driven with every adversarial probe and each refusal it produces
    is put through the same extractor the walk uses. A validator "hands back a re-submittable
    spelling" when some refusal of it names a literal other than the input — which is the only
    shape another validator can trip over.

    Across the family (13 ``__post_init__`` validators under ``write/model/**``, of which 10 can
    refuse at all and 3 only normalise) **exactly one** does so, and it is the one this issue is
    about. Every other refusal advises a *kind* of repair — "drop the span", "split the
    authoring into batches", "use one of larkdocio.langs.supported_code_languages()" — and names
    no literal for a second validator to refuse. So the answer to AC6 is **none**: no other pair
    in this family loops.
    """
    advising = {}
    for key, (build, _probe) in FAMILY_WALKS.items():
        for probe in ADVERSARIAL_PROBES:
            try:
                build(probe)
            except (ValueError, TypeError) as exc:
                advice = advised_spellings(str(exc), probe)
                if advice:
                    advising.setdefault(key, []).append((probe, advice))
    assert sorted(advising) == [("requests.py", "TextSpan")], (
        f"a second validator now hands back a re-submittable spelling: {sorted(advising)}")
    # Non-vacuity: the one row that does advise, advises only where the advice is TRUE — the
    # whitespace-hiding probes are refused with no literal at all.
    advised_from = {probe for probe, _ in advising[("requests.py", "TextSpan")]}
    assert "https://example.com/a%2Db" in advised_from
    assert "https://example.com/a%20b" not in advised_from


def test_ac6_the_one_re_submittable_site_is_the_one_that_is_now_SCOPED():
    """And that site is only reached when the advice is true: the branch that emits a decoded
    spelling cannot be entered when the decoding carries whitespace."""
    assert "https://example.com/a b" not in _refusal("https://example.com/a%20b")
    assert "https://example.com/a-b" in _refusal("https://example.com/a%2Db")


@private_tree.internal_log
def test_the_SHIPPED_note_quotes_the_derived_population_rather_than_a_typed_one():
    """Eleven numbers were wrong in one session on this repo and every one that reached a
    packaged document had been typed by hand. So the three figures the `[1.51.0]` CHANGELOG
    states about this change are held to the walk that produces them: change the family and the
    packaged note reddens rather than quietly becoming false in the wheel.

    Whitespace-flattened before matching — the note is wrapped prose, so a phrase straddling a
    line break is the same claim and a line-sensitive match would fail on a re-wrap.
    """
    population = _post_init_validators()
    total = len(population)
    refusing = len([1 for count in population.values() if count])
    # LD-691: the note is an INTERNAL-log entry, read at the root; the packaged changelog is the
    # public one (maintainer ruling 2) and does not carry it.
    changelog = " ".join((WRITE_MODEL.parent.parent.parent.parent / "CHANGELOG.md")
                         .read_text(encoding="utf-8").split())
    assert f"**{total}**, of which **{refusing}** can refuse and **{total - refusing}** only" \
        in changelog, (
            f"the shipped CHANGELOG does not state the derived family: {total} validators, "
            f"{refusing} of which can refuse")


def test_the_shared_sentence_is_authored_ONCE():
    """One constant, two messages. Two hand-kept copies of a sentence is how one of them starts
    telling a caller something the other one contradicts."""
    source = (WRITE_MODEL / "requests.py").read_text(encoding="utf-8")
    body = UNAUTHORABLE_WHITESPACE_URL_ADVICE.split(":")[0]
    assert source.count(body[:40]) == 1
    assert dataclasses.is_dataclass(TextSpan)
