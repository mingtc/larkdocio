"""LD-518 / D-107 — ``compose_check(markdown)``: BATCH DISCOVERY, NOT NEW PERMISSIVENESS.

The consumer moved ~27,000 words and needed **eight** separate attempts, because
:func:`~larkdocio.write.compose.compose` stops at the first inexpressible construct and
never names the other seven. Their own verdict is why this is not a permissiveness ask: they
rated the refusals themselves highly — clear, specific, each naming its fix — and found only
the one-at-a-time discovery expensive.

So this file proves two things, and the second one is the bulk:

1. **Nothing about what is refused changed.** ``compose()`` still refuses the whole batch
   on the **first** construct, with the same construct name, the same 1-based line and the
   **same** :class:`~larkdocio.write.model.Refusal` object it always raised — asserted by
   equality against what ``compose_check`` reports, so the two cannot drift into two
   opinions of the dialect. Nothing becomes newly writable.

2. **COMPLETENESS, proved rather than claimed.** A checker that finds *most* constructs
   sends the caller back for a second pass and has failed at its one job — worse than the
   serial behaviour it replaces, because the caller now believes they hold the whole list.
   The construct set is therefore taken **from the code**
   (:data:`~larkdocio.write.compose.NOT_EXPRESSIBLE_CONSTRUCTS`, **26** keys as of this
   change) and held **bidirectionally** against this file's fixture set: a construct added
   to the compiler without a fixture reddens :func:`test_ac2_every_refusable_construct_has_a_fixture`,
   and a fixture naming a construct the compiler cannot raise reddens the same test.

**Three of the 26 are not reachable from a Markdown fragment**, and each is exercised
anyway rather than excused — see :data:`SEAM_ONLY` and the tests that use it.
"""
from dataclasses import FrozenInstanceError
from typing import Tuple

import pytest

from larkdocio.write import compose, compose_check
from larkdocio.write.compose import (
    NOT_EXPRESSIBLE_CONSTRUCTS,
    READER_PROJECTION_FENCES,
    ComposeCheck,
    ComposeRefusal,
    _Compiler,
)
from larkdocio.write.model import MAX_NEST_DEPTH, RefusalReason, RefusedError


def _refusal_of(markdown: str):
    """The typed refusal ``compose()`` raises for a fragment — the serial behaviour."""
    with pytest.raises(RefusedError) as exc:
        compose(markdown)
    return exc.value.refusal


def _table(cols: int, rows: int) -> str:
    header = "| " + " | ".join(f"h{i}" for i in range(cols)) + " |"
    delim = "|" + "---|" * cols
    body = ["| " + " | ".join("x" for _ in range(cols)) + " |"] * rows
    return "\n".join([header, delim] + body) + "\n"


#: One fragment per construct the compiler can refuse, **keyed by the construct name the
#: refusal uses**. The consumer's own eight (bold, italic, strikethrough, inline code,
#: image, link, ``empty-list-item``, ``html``) are the floor of this set, not the set.
FIXTURES = {
    "image": "![alt](sometoken)\n",
    "link": "see [the doc](https://example.com/x)\n",
    "bold": "**bold** text\n",
    "italic": "*italic* text\n",
    "strikethrough": "~~struck~~ text\n",
    "inline-code": "a `code span` here\n",
    "html": "Lorem <ipsum dolor> sit amet\n",
    "merged-table": "| A | B |\n|---|---|\n| only-one |\n",
    "thematic-break": "---\n",
    "indented-code-block": "    indented code\n",
    "hard-break": "line a  \nline b\n",
    # NOT ``[^1]: note``: that is a well-formed link-reference DEFINITION (label ``^1``,
    # destination ``note``), which CommonMark consumes into nothing at all. Two words in
    # the note make it a footnote definition again.
    "footnote": "[^1]: the note\n",
    "list-item-block-child": "- a bullet\n\n  > a quote under it\n",
    "blockquote-block-child": "> first para\n>\n> second para\n",
    "empty-list-item": "- # opens a heading and leaves the marker empty\n",
    "empty-heading": "# \n",
    "empty-quote": ">\n",
    "empty-mermaid": "```mermaid\n```\n",
    "code-fence-info": "```python title=x\ncode\n```\n",
    "unknown-code-language": "```nosuchlanguage\ncode\n```\n",
    "nesting-too-deep": "".join(
        "  " * level + "- x\n" for level in range(MAX_NEST_DEPTH + 2)),
    "table-cap": _table(5, 120),
    "table-column-cap": _table(101, 1),
}

#: The three constructs **no Markdown fragment can reach today**, each with the reason and
#: the mechanism this file exercises it through instead. Naming them is the point: an
#: unreachable construct quietly dropped from the fixture set is exactly the silent hole
#: this file exists to make impossible.
SEAM_ONLY = {
    # READER_PROJECTION_FENCES is EMPTY today (its one row, ``mermaid``, became authorable
    # in the change that made a diagram creatable), so the refusal is reachable only with a
    # row present — which is how tests/test_non_creatable_projection_refusal.py reaches it.
    "non-creatable-projection": "the projection-fence table is empty today",
    # The two DEFENSIVE fallbacks: every block and inline token type the configured dialect
    # (commonmark + table + strikethrough) can produce is handled by name, so these fire
    # only for a token type this parser configuration does not emit.
    "block": "a defensive fallback for an unhandled block token type",
    "inline": "a defensive fallback for an unhandled inline token type",
}


class _FakeNode:
    """The smallest thing the two fallback branches read: a token type and a source map."""

    def __init__(self, type_: str, line: int):
        self.type = type_
        self.map = (line - 1, line)
        self.children = []
        self.content = ""


# =========================================================================== #
# AC1 — compose() IS UNCHANGED: same refusals, same messages, same codes,      #
#       same first-failure semantics. Nothing became newly writable.           #
# =========================================================================== #

@pytest.mark.parametrize("construct", sorted(FIXTURES))
def test_ac1_compose_still_refuses_every_fixture_naming_the_same_construct(construct):
    """The floor: each fixture is still a REFUSAL out of ``compose()``, naming its own
    construct. If any of these composed, this change would have widened the dialect."""
    refusal = _refusal_of(FIXTURES[construct])
    assert refusal.reason in (
        RefusalReason.NOT_IN_DIALECT, RefusalReason.MERGE_NOT_EXPRESSIBLE)
    assert refusal.detail.startswith(construct), refusal.detail


@pytest.mark.parametrize("construct", sorted(FIXTURES))
def test_ac1_the_checker_reports_the_VERY_refusal_compose_raises(construct):
    """**The anti-drift proof.** For a single-construct fragment the checker's row carries
    the `Refusal` ``compose()`` raises — by dataclass equality, so the reason, the
    construct, the line and every word of the recovery text are the same object's worth of
    bytes. There is no second definition of the dialect and no second wording of the fix."""
    markdown = FIXTURES[construct]
    check = compose_check(markdown)
    assert check.refusals, f"the checker reported nothing for {construct!r}"
    assert check.refusals[0].refusal == _refusal_of(markdown)


def test_ac1_compose_still_stops_at_the_FIRST_construct():
    """First-failure semantics are unchanged: a fragment with three constructs raises for
    the FIRST one and says nothing about the other two — which is the cost the checker
    exists to remove, and the behaviour a shipped caller depends on."""
    markdown = "**bold** here\n\n*italic* there\n\n`code` last\n"
    refusal = _refusal_of(markdown)
    assert refusal.detail.startswith("bold at line 1")
    assert "italic" not in refusal.detail and "inline-code" not in refusal.detail
    # …and the same fragment through the checker gives all three, which is the whole ask.
    assert [row.construct for row in compose_check(markdown).refusals] == [
        "bold", "italic", "inline-code"]


def test_ac1_nothing_the_dialect_refuses_became_composable():
    """Stated as its own test because it is the one invariant that matters: the checker is
    read-only and reports; it never composes a refused fragment into content."""
    for markdown in FIXTURES.values():
        assert not compose_check(markdown).ok
        with pytest.raises(RefusedError):
            compose(markdown)


#: The angle-bracket forms the guide's ``html`` row, its refusal text and the release notes
#: call **Measured**. The sentence is held here, so it stays a measurement: a well-formed open
#: tag (bare, or with an attribute) refuses as ``html``; an underscore in the name, or a bare
#: ``<`` comparison, is not a tag and composes as text.
ANGLE_BRACKET_MEASURED = [
    ("Lorem <ipsum> sit amet.\n", True),
    ("Lorem <ipsum dolor> sit amet.\n", True),
    ("Lorem <ipsum_dolor> sit amet.\n", False),
    ("Lorem A <= 3 sit amet.\n", False),
]


@pytest.mark.parametrize("markdown,refuses", ANGLE_BRACKET_MEASURED)
def test_ac1_the_MEASURED_angle_bracket_forms(markdown, refuses):
    constructs = [row.construct for row in compose_check(markdown).refusals]
    if refuses:
        assert constructs == ["html"], constructs
        with pytest.raises(RefusedError):
            compose(markdown)
    else:
        assert constructs == [], constructs
        assert compose(markdown)


def test_ac1_a_clean_fragment_composes_and_checks_clean():
    markdown = "# Plan\n\n- [x] ship it\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    assert compose_check(markdown) == ComposeCheck()
    assert compose_check(markdown).ok
    assert compose(markdown)                      # unchanged, still composes


@pytest.mark.parametrize("markdown", ["", "   \n\n\t\n"])
def test_ac1_an_empty_fragment_is_clean_not_an_error(markdown):
    assert compose_check(markdown).ok
    assert compose(markdown) == ()


def test_ac1_a_non_str_argument_refuses_the_way_compose_does():
    with pytest.raises(TypeError) as exc:
        compose_check(b"# not a str\n")
    assert "compose_check()" in str(exc.value) and "bytes" in str(exc.value)


# =========================================================================== #
# AC2 — COMPLETENESS, bidirectional: every refusable construct is SEEN.        #
# =========================================================================== #

def test_ac2_the_construct_count_is_DERIVED_from_the_code():
    """The number in this file's docstring is derived, not typed from a brief: 26 keys,
    23 of them reachable from a Markdown fragment and 3 only through a seam."""
    assert len(NOT_EXPRESSIBLE_CONSTRUCTS) == 26
    assert len(FIXTURES) == 23 and len(SEAM_ONLY) == 3


def test_ac2_every_refusable_construct_has_a_fixture():
    """**The completeness guard, both directions.** A construct added to the compiler with
    no fixture reddens here (a silent hole in the checker's coverage), and a fixture naming
    a construct the compiler cannot raise reddens here too (a checker claiming a refusal
    that does not exist)."""
    covered = set(FIXTURES) | set(SEAM_ONLY)
    refusable = set(NOT_EXPRESSIBLE_CONSTRUCTS)
    assert covered - refusable == set(), (
        f"fixtures name constructs the compiler cannot refuse: {covered - refusable}")
    assert refusable - covered == set(), (
        f"these refusable constructs have no fixture proving the checker SEES them: "
        f"{refusable - covered} — a checker that silently misses one is worse than the "
        f"serial behaviour it replaces")


@pytest.mark.parametrize("construct", sorted(FIXTURES))
def test_ac2_the_checker_SEES_every_construct_a_fragment_can_reach(construct):
    """One fixture per construct, each asserted to be REPORTED — the per-construct half of
    the completeness proof, which a set-equality test alone cannot give."""
    reported = compose_check(FIXTURES[construct]).refusals
    assert construct in [row.construct for row in reported], (
        f"the checker did not report {construct!r}: {[r.construct for r in reported]}")


@pytest.mark.parametrize("construct", sorted(FIXTURES))
def test_ac2_every_construct_the_checker_reports_is_one_the_compiler_KNOWS(construct):
    """The reverse direction per row: no invented construct names, and every row's recovery
    text is the compiler's own entry for that construct."""
    for row in compose_check(FIXTURES[construct]).refusals:
        assert row.construct in NOT_EXPRESSIBLE_CONSTRUCTS
        assert NOT_EXPRESSIBLE_CONSTRUCTS[row.construct] in row.detail


def test_ac2_the_projection_fence_construct_is_seen_when_the_table_has_a_row(monkeypatch):
    """``non-creatable-projection`` — reachable only with a projection row present, so the
    row is injected exactly as the refusal's own test file does. The checker sees it."""
    monkeypatch.setitem(READER_PROJECTION_FENCES, "boardnote", "a whiteboard block")
    markdown = "```boardnote\nsome projection\n```\n"
    check = compose_check(markdown)
    assert [row.construct for row in check.refusals] == ["non-creatable-projection"]
    assert check.refusals[0].refusal == _refusal_of(markdown)


@pytest.mark.parametrize("construct,kind,fake", [
    ("block", "front_matter", "block"),
    ("inline", "math_inline", "inline"),
])
def test_ac2_the_two_defensive_fallbacks_are_COLLECTED_not_raised(construct, kind, fake):
    """The two fallbacks fire for a token type the configured dialect does not emit, so
    they are exercised through the seam itself with a synthetic node — which is the thing
    that matters: the collecting path records them rather than aborting on them.

    Both are proved in BOTH modes: collecting records the row, and the serial mode still
    raises, so the fallback's own contract is unchanged."""
    node = _FakeNode(kind, line=7)

    collecting = _Compiler("irrelevant", collect=True)
    if fake == "block":
        collecting._blocks([node], depth=1)
    else:
        inline = _FakeNode("inline", line=7)
        inline.children = [node]
        collecting._inline_text(inline)
    assert [(row.construct, row.line) for row in collecting.found] == [(construct, 7)]
    assert kind in collecting.found[0].detail

    serial = _Compiler("irrelevant")
    with pytest.raises(RefusedError) as exc:
        if fake == "block":
            serial._blocks([node], depth=1)
        else:
            inline = _FakeNode("inline", line=7)
            inline.children = [node]
            serial._inline_text(inline)
    assert exc.value.refusal.detail.startswith(construct)


# =========================================================================== #
# AC3 — LINE NUMBERS ARE PART OF THE PRODUCT, on a multi-construct document.   #
# =========================================================================== #

#: The consumer's own migration shape: the eight constructs they met, in one document,
#: **plus a fenced code block whose body is full of them and must NOT be reported** — the
#: parsing this library owns is exactly why "just grep for the markers" was rejected as an
#: alternative. Each row is ``(source line, the constructs expected ON that line)``.
MULTI = (
    ("# Migration plan", ()),
    ("", ()),
    ("A paragraph with **bold** in it.", ("bold",)),
    ("", ()),
    ("Then *italic* and ~~struck~~ together.", ("italic", "strikethrough")),
    ("", ()),
    ("An `inline code` span.", ("inline-code",)),
    ("", ()),
    ("![a diagram](sometoken)", ("image",)),
    ("", ()),
    ("See [the page](https://example.com/page).", ("link",)),
    ("", ()),
    ("```python", ()),
    ("**not bold** and `not code` and <not html> and ![no](img)", ()),
    ("- # not a list item either", ()),
    ("```", ()),
    ("", ()),
    ("- # opens a heading, leaving the marker empty", ("empty-list-item",)),
    ("", ()),
    ("Lorem <ipsum dolor> sit amet.", ("html",)),
)
MULTI_DOC = "\n".join(line for line, _ in MULTI) + "\n"
MULTI_EXPECTED = tuple(
    (number, construct)
    for number, (_line, constructs) in enumerate(MULTI, start=1)
    for construct in constructs
)


def test_ac3_every_construct_is_reported_ONCE_at_its_OWN_line_in_document_order():
    """The product claim: one pass, every construct, each against the line the caller has
    to go and edit. Asserted as the whole ordered list — a wrong line, a missing row, a
    duplicate row or a reordering all redden."""
    reported = tuple(
        (row.line, row.construct) for row in compose_check(MULTI_DOC).refusals)
    assert reported == MULTI_EXPECTED


def test_ac3_the_fenced_code_block_is_NOT_reported():
    """Four constructs sit inside the ``python`` fence and none of them is a refusal: a
    fence's body is content, not structure. This is the claim a grep-based workaround
    cannot make, and it is asserted separately so it cannot be lost in a reflow of the
    document above."""
    fence_lines = {
        number for number, (line, _c) in enumerate(MULTI, start=1)
        if line.startswith("```") or "not bold" in line or "not a list item" in line
    }
    reported = {row.line for row in compose_check(MULTI_DOC).refusals}
    assert not (reported & fence_lines), (
        f"the checker reported a construct inside a code fence: {reported & fence_lines}")
    # …and the same document, with the fence removed, is a different story — so the guard
    # above is not passing because the fence's content is unparsed noise.
    assert "**not bold**" in MULTI_DOC


def test_ac3_the_serial_compiler_agrees_about_the_first_line():
    """The checker's first row and ``compose()``'s single refusal are the same row — the
    two cannot disagree about where the trouble starts."""
    first = compose_check(MULTI_DOC).refusals[0]
    assert first.refusal == _refusal_of(MULTI_DOC)
    assert (first.line, first.construct) == MULTI_EXPECTED[0]


def test_ac3_the_eight_the_consumer_MET_are_all_in_one_pass():
    """The floor named in the issue: the consumer's eight discovered over eight attempts,
    all reported by a single call."""
    theirs = {"bold", "italic", "strikethrough", "inline-code", "image", "link",
              "empty-list-item", "html"}
    assert theirs <= set(compose_check(MULTI_DOC).constructs)


def test_ac3_a_line_number_survives_a_soft_break_inside_a_paragraph():
    """Line counting inside one paragraph is per-line, not per-block: the construct on the
    third physical line is reported against line 3."""
    check = compose_check("plain one\nplain two\nwith **bold** on three\n")
    assert [(row.line, row.construct) for row in check.refusals] == [(3, "bold")]


def test_ac3_a_nested_construct_inside_a_refused_one_is_reported_too():
    """``[[label]](url)`` — the nested shape one of the consumer's source documents used —
    and a styled anchor: the outer construct does not hide what is inside it, because the
    caller has to fix both before the batch lands."""
    assert [row.construct for row in
            compose_check("a [[label]](https://example.com/x) here\n").refusals] == ["link"]
    nested = compose_check("a [**bold label**](https://example.com/x) here\n")
    assert [row.construct for row in nested.refusals] == ["link", "bold"]


def test_ac3_two_bad_items_in_ONE_list_are_both_reported():
    """A sibling loop is not the only loop a refusal can abort: two items of the same list,
    and two rows of the same ragged grid, each report per occurrence."""
    items = compose_check("- one with **bold**\n- two with `code`\n")
    assert [(row.line, row.construct) for row in items.refusals] == [
        (1, "bold"), (2, "inline-code")]
    grid = compose_check("| A | B |\n|---|---|\n| x |\n| y | z | w |\n")
    assert [(row.line, row.construct) for row in grid.refusals] == [
        (3, "merged-table"), (4, "merged-table")]


def test_ac3_an_empty_marker_is_not_INVENTED_by_the_collecting_pass():
    """The trap this guard exists for: a heading whose only content is a refused construct
    must report **that construct** and NOT an ``empty-heading`` the serial compiler would
    never raise. The collecting pass keeps the construct's own plain text so the enclosing
    block is not left looking empty.

    The second half is the shape that actually holds this guard up (LD-518 fix round): a
    refused construct whose **own text is empty or whitespace** — an alt-less image, an
    empty link label, a blank code span. Keeping the construct's own text is no defence
    there, so the stand-in has to be non-empty. Every fixture above carries visible text
    and so could never have failed on it."""
    for markdown, expected in (
        ("# **bold heading**\n", ["bold"]),
        ("# ![alt text](tok)\n", ["image"]),
        ("- `only code`\n", ["inline-code"]),
        ("> *only italic*\n", ["italic"]),
        # …and the same shapes with NO text of their own.
        ("- ![](media/dashboard.png)\n", ["image"]),   # the default exporter spelling
        ("# ![](tok)\n", ["image"]),
        ("> ![](tok)\n", ["image"]),
        ("# [](url)\n", ["link"]),
        ("#   `  `\n", ["inline-code"]),               # whitespace-only, not just empty
    ):
        rows = compose_check(markdown).refusals
        assert [row.construct for row in rows] == expected, markdown
        # The strong form: the one row IS the Refusal the serial compiler raises, by
        # dataclass equality — so a phantom row cannot hide behind a matching name list.
        assert rows[0].refusal == _refusal_of(markdown), markdown


# =========================================================================== #
# AC4 — the RESULT SHAPE: a read-only object carrying typed refusals.          #
# =========================================================================== #

def test_ac4_the_result_and_its_rows_are_FROZEN():
    check = compose_check("**bold**\n")
    row = check.refusals[0]
    assert isinstance(check, ComposeCheck) and isinstance(row, ComposeRefusal)
    with pytest.raises(FrozenInstanceError):
        check.refusals = ()
    with pytest.raises(FrozenInstanceError):
        row.line = 99


def test_ac4_the_row_carries_the_construct_the_line_and_the_typed_refusal():
    row = compose_check("prose\n\n![alt](tok)\n").refusals[0]
    assert (row.construct, row.line) == ("image", 3)
    assert row.reason is RefusalReason.NOT_IN_DIALECT
    assert row.detail == row.refusal.detail
    assert row.detail.startswith("image at line 3:")


def test_ac4_the_refusals_are_a_TUPLE_and_ok_says_whether_there_are_any():
    clean, dirty = compose_check("plain prose\n"), compose_check("**bold**\n")
    assert isinstance(clean.refusals, Tuple.__origin__) and clean.refusals == ()
    assert clean.ok is True and dirty.ok is False


def test_ac4_constructs_is_the_unique_construct_list_in_first_seen_order():
    check = compose_check("**b** and *i*\n\n**b again**\n")
    assert [row.construct for row in check.refusals] == ["bold", "italic", "bold"]
    assert check.constructs == ("bold", "italic")


def test_ac4_the_result_is_JSON_ready_through_to_dict():
    import json

    payload = compose_check("prose\n\n**bold**\n").to_dict()
    assert payload["ok"] is False
    assert payload["refusals"][0]["construct"] == "bold"
    assert payload["refusals"][0]["line"] == 3
    assert payload["refusals"][0]["reason"] == "not-in-dialect"
    assert payload["refusals"][0]["detail"].startswith("bold at line 3:")
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert compose_check("plain\n").to_dict() == {"ok": True, "refusals": []}


# =========================================================================== #
# AC5 — READ-ONLY AND OFFLINE: no client, no credential, no transport.         #
# =========================================================================== #

def test_ac5_the_checker_is_pure_and_holds_no_state_across_calls():
    """Two calls of the same fragment give the same answer, and a call after a dirty one is
    not polluted by it — the collecting state lives on one compile, not on the module."""
    dirty = compose_check(MULTI_DOC)
    assert compose_check(MULTI_DOC) == dirty
    assert compose_check("plain prose\n").ok


def test_ac5_the_checker_never_touches_a_network_or_a_credential():
    """Same claim ``compose()`` already carries (pinned for the module as a whole in
    ``tests/test_compose_markdown.py``'s AC6), restated for the new entry point at the one
    level prose cannot fake: the **names the compiled function actually reaches for**.
    A client, a transport or a credential resolver would have to appear here."""
    assert set(compose_check.__code__.co_names) <= {
        "isinstance", "str", "TypeError", "type", "__name__",
        "ComposeCheck", "_Compiler", "check",
    }, sorted(compose_check.__code__.co_names)
