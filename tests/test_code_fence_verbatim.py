"""LD-146 — a fenced code block's body is emitted VERBATIM, first line included.

The bug (dogfood round 2, finding **T9**, reproduced twice): the reader's fence
assembly ran ``.strip()`` over the **whole joined body**, so the **first** line lost
its leading whitespace while every subsequent line kept its indentation exactly —
and, as collateral, the **last** line lost its trailing whitespace, a **leading blank
line** vanished, and a whitespace-only body collapsed to empty. ``parse_docx_tree``
was always correct; this was read-side (serialization) only.

The rule these tests pin is ONE sentence, and it is the same rule ``compose()``
already states from the other side (``write/compose.py`` ``_fence``: "a fence's
payload always ends with the newline that precedes the closing fence; that newline is
syntax, not content. Everything else is kept verbatim"):

    the fence body is the model content, byte for byte — the renderer adds only the
    two fence lines and the one newline that closes the body.

That symmetry is why the read↔write round-trip for code is exact (a body ending in
``\\n`` emits a trailing blank line inside the fence, and ``compose`` removes exactly
that one syntactic newline again).

Structure: AC1 (the T9 repro), AC3 (the verbatim-preservation property over the
whitespace-torture corpus, asserted against ``parse_docx_tree``'s own raw content —
the exact comparison the bug report made), AC4 (fence integrity), plus the maintainer
amplifier cases. AC2 (the fixture + golden) lives in ``tests/fixtures`` and is
verified by ``test_golden.py``; AC5/AC6/AC7 are golden/matrix/gate-level.
"""
from pathlib import Path

import pytest

from doc_prose import missing_phrases
from harness import build_blocks, render

from larkdocio.model.nodes import CodeNode, StyledText
from larkdocio.model.renderer import MarkdownRenderer
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _code_doc(body: str, *, language: int | None = 49):
    """The block dicts for a page owning ONE type-14 code block carrying ``body``."""
    code: dict = {"elements": [{"text_run": {"content": body}}]}
    if language is not None:
        code["style"] = {"language": language}
    return [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": []}, "children": ["c1"]},
        {"block_id": "c1", "parent_id": "root", "block_type": 14,
         "code": code, "children": []},
    ]


def _render_node(body: str, lang: str = "python") -> str:
    """The renderer's own output for a ``CodeNode`` — the unit under test."""
    node = CodeNode(lang=lang, content=[StyledText(content=body)])
    return MarkdownRenderer().render(node)


def _fence_body(markdown: str, *, lang: str) -> str:
    """Extract the body between the opening and closing fence lines.

    Peels the KNOWN prefix/suffix rather than searching, so it cannot paper over a
    defect — an extra or missing newline at either edge reddens here instead of being
    normalized away. The closing fence is located with ``rindex`` because the body may
    legitimately contain its own ``\\n```\\n`` (the documented fence-in-fence lossiness),
    and the real closer is always the last one.
    """
    prefix = f"```{lang}\n"
    assert markdown.startswith(prefix), f"no {prefix!r} opening fence in {markdown!r}"
    rest = markdown[len(prefix):]
    close = "\n```\n"
    assert close in rest, f"no closing fence in {markdown!r}"
    cut = rest.rindex(close)
    # Everything after the closing fence is the parser's block separator (newlines only).
    assert set(rest[cut + len(close):]) <= {"\n"}, (
        f"unexpected trailing content after the closing fence in {markdown!r}"
    )
    return rest[:cut]


def _tree_code_content(block_dicts) -> str:
    """The raw model content ``parse_docx_tree`` reports for the doc's code block.

    This is the side the bug report proved CORRECT ("``parse_docx_tree``'s raw
    ``StyledText.content`` shows the original whitespace intact"), so the property is
    stated against it rather than against the test's own input string — the assertion
    is then "the two halves of the read path agree", not "the renderer echoes a
    literal I typed twice".
    """
    root = Parser(Config()).parse_docx_tree("root", build_blocks(block_dicts))
    codes = [n for n in _walk(root) if isinstance(n, CodeNode)]
    assert len(codes) == 1, f"expected exactly one CodeNode, got {len(codes)}"
    return "".join(getattr(i, "content", "") for i in codes[0].content)


def _walk(node):
    yield node
    for child in getattr(node, "children", None) or []:
        yield from _walk(child)


def _read_fence_body(body: str, *, language: int | None = 49) -> str:
    """Round the body through the FULL read path and hand back the emitted fence body."""
    blocks = _code_doc(body, language=language)
    markdown = render(blocks, doc_id="root")
    lang = "python" if language == 49 else ""
    # The (untitled) page contributes only leading newlines before the block.
    return _fence_body(markdown.lstrip("\n"), lang=lang)


# --------------------------------------------------------------------------- #
# AC1 — the T9 repro: the first line keeps its leading whitespace              #
# --------------------------------------------------------------------------- #

#: The exact shape dogfood round 2 authored: FIRST line indented four spaces, a later
#: line indented deeper. Pre-fix output dropped only the first line's four spaces.
T9_BODY = "    def f():\n        return 1"


def test_ac1_the_t9_repro_first_line_keeps_its_leading_whitespace():
    assert _render_node(T9_BODY) == (
        "```python\n"
        "    def f():\n"
        "        return 1\n"
        "```\n"
    )


def test_ac1_the_t9_repro_through_the_full_read_path():
    """The same assertion one level up — real SDK blocks through ``Parser``, because
    the defect was reported against ``parse_docx_content`` output, not the renderer."""
    assert _read_fence_body(T9_BODY) == T9_BODY


def test_ac1_the_reader_and_the_tree_agree_on_the_t9_body():
    """The bug report's own comparison: emitted fence body vs. the raw tree content."""
    blocks = _code_doc(T9_BODY)
    assert _read_fence_body(T9_BODY) == _tree_code_content(blocks) == T9_BODY


def test_ac1_the_fence_assembly_does_not_strip_the_body():
    """Guard the ROOT CAUSE by shape, not only by output: a whole-body ``strip()``/
    ``lstrip()`` in the code serializer is the defect itself.

    A behavioral test can be satisfied by a per-line re-indent hack that reintroduces
    the same class of bug elsewhere; this pins the one-rule implementation.

    COMMENTS ARE EXCLUDED before matching — the serializer's comment deliberately names
    the removed ``.strip()`` to explain the defect, and a guard that forbade *describing*
    the bug would push the explanation out of the code."""
    import inspect
    import io
    import tokenize

    src = inspect.getsource(MarkdownRenderer._code)
    code_only = "".join(
        tok.string for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        if tok.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    for forbidden in ("strip", "dedent", "textwrap"):
        assert forbidden not in code_only, (
            f"MarkdownRenderer._code still contains {forbidden!r} in executable code — "
            "the fence body is verbatim; trimming it is the LD-146 defect."
        )


# --------------------------------------------------------------------------- #
# AC3 — THE VERBATIM-PRESERVATION PROPERTY (whitespace-torture corpus)        #
# --------------------------------------------------------------------------- #

#: Every position/kind of whitespace the AC names, plus the maintainer amplifier's additions.
#: Each entry is ``(id, body)``; the property is that the emitted fence body is
#: byte-identical to the body the model holds.
TORTURE_CORPUS = [
    # -- leading whitespace, by position ------------------------------------
    ("lead-spaces-first-line", "    def f():\nreturn 1"),
    ("lead-spaces-middle-line", "def f():\n    body()\nreturn 1"),
    ("lead-spaces-last-line", "def f():\nbody()\n    return 1"),
    ("lead-spaces-every-line", "    a\n    b\n    c"),
    # -- tabs, in each of those positions ----------------------------------
    ("lead-tab-first-line", "\tdef f():\nreturn 1"),
    ("lead-tab-middle-line", "def f():\n\tbody()\nreturn 1"),
    ("lead-tab-last-line", "def f():\nbody()\n\treturn 1"),
    ("lead-tabs-nested", "\tif x:\n\t\treturn 1"),
    # -- mixed tabs + spaces ------------------------------------------------
    ("mixed-tab-then-spaces", "\t    a\n    \tb"),
    ("mixed-tabs-and-spaces-first-line", " \t def f():\n \t \t return 1"),
    # -- whitespace-only lines ---------------------------------------------
    ("whitespace-only-line-in-the-middle", "a\n    \nb"),
    ("whitespace-only-body-spaces", "    "),
    ("whitespace-only-body-tab", "\t"),
    ("whitespace-only-first-line", "   \nreal content"),
    ("whitespace-only-last-line", "real content\n   "),
    # -- trailing whitespace ------------------------------------------------
    ("trailing-spaces-last-line", "x = 1   "),
    ("trailing-tab-last-line", "x = 1\t"),
    ("trailing-spaces-every-line", "a   \nb   \nc   "),
    ("trailing-newline", "x = 1\n"),
    ("trailing-blank-lines", "x = 1\n\n"),
    # -- single-line blocks -------------------------------------------------
    ("single-indented-line", "    only()"),
    ("single-tab-indented-line", "\tonly()"),
    ("single-line-indented-both-ends", "    only()    "),
    # -- amplifier: empty first line, CRLF, structural first characters -----
    ("empty-first-line", "\ndef f():"),
    ("empty-first-two-lines", "\n\nx"),
    ("crlf-line-endings", "a = 1\r\nb = 2"),
    ("crlf-with-indent", "    a = 1\r\n        b = 2"),
    ("first-line-hash-indented", "    # a comment, not a heading"),
    ("first-line-dash-indented", "    - not a bullet"),
    ("first-line-pipe-indented", "    | not a table |"),
    ("first-line-gt-indented", "    > not a quote"),
    ("ascii-art", "   /\\_/\\\n  ( o.o )\n   > ^ <"),
    ("yaml-ish-block", "root:\n  child: 1\n  other:\n    - a\n    - b"),
    ("empty-body", ""),
]
TORTURE_IDS = [name for name, _ in TORTURE_CORPUS]
TORTURE_BODIES = [body for _, body in TORTURE_CORPUS]


@pytest.mark.parametrize("body", TORTURE_BODIES, ids=TORTURE_IDS)
def test_ac3_emitted_fence_body_is_byte_identical_to_the_model_content(body):
    """THE property: for every torture body, the emitted fence body **is** the body the
    model holds — no trim, no re-indent, no normalization."""
    blocks = _code_doc(body)
    assert _tree_code_content(blocks) == body, (
        "the tree side must carry the body verbatim (it always did — this guards the "
        "premise of the property, so a tree regression cannot make the property vacuous)"
    )
    assert _read_fence_body(body) == body


@pytest.mark.parametrize("body", TORTURE_BODIES, ids=TORTURE_IDS)
def test_ac3_the_whole_emission_is_exactly_the_fence_plus_the_verbatim_body(body):
    """Stated as full-output equality rather than an extraction, so the extraction
    helper cannot hide a defect (e.g. an extra blank line before the closing fence)."""
    assert _render_node(body, lang="python") == f"```python\n{body}\n```\n"


@pytest.mark.parametrize("body", TORTURE_BODIES, ids=TORTURE_IDS)
def test_ac3_no_line_of_the_body_is_altered(body):
    """Per-line form of the property: the body's line list survives 1:1 — this is what
    reddens for a fix that trims the first line only, or that "helpfully" dedents."""
    emitted = _read_fence_body(body)
    assert emitted.split("\n") == body.split("\n")


def test_ac3_the_corpus_actually_covers_every_position_the_ac_names():
    """Coverage guard on the corpus itself: a shrunken corpus must redden, not pass."""
    bodies = TORTURE_BODIES
    assert any(b.split("\n")[0][:1] in " \t" for b in bodies), "no first-line indent case"
    assert any(len(b.split("\n")) > 2 and b.split("\n")[1][:1] in " \t"
               for b in bodies), "no middle-line indent case"
    assert any(len(b.split("\n")) > 1 and b.split("\n")[-1][:1] in " \t"
               for b in bodies), "no last-line indent case"
    assert any("\t" in b for b in bodies), "no tab case"
    assert any("\t" in b and " " in b for b in bodies), "no mixed tabs+spaces case"
    assert any(line.strip() == "" and line != "" for b in bodies
               for line in b.split("\n")), "no whitespace-only line case"
    assert any(b.endswith((" ", "\t")) for b in bodies), "no trailing-whitespace case"
    assert any(b.endswith("\n") for b in bodies), "no trailing-newline case"
    assert any(b.startswith("\n") for b in bodies), "no empty-first-line case"
    assert any("\r\n" in b for b in bodies), "no CRLF case"
    assert any("\n" not in b and b[:1] in " \t" for b in bodies), \
        "no single-indented-line case"
    assert len(set(TORTURE_IDS)) == len(TORTURE_IDS), "duplicate corpus ids"


# --------------------------------------------------------------------------- #
# AC4 — fence integrity: language tag, markers, fence-in-content              #
# --------------------------------------------------------------------------- #

def test_ac4_language_tag_survives_an_indented_body():
    assert _render_node(T9_BODY, lang="python").startswith("```python\n")
    assert _render_node(T9_BODY, lang="go").startswith("```go\n")


def test_ac4_a_bare_fence_stays_bare_for_an_unmapped_language():
    """No ``style`` at all (language None) is a real live shape — the bare fence must
    not gain a tag, and the indent must still survive."""
    assert _read_fence_body(T9_BODY, language=None) == T9_BODY
    blocks = _code_doc(T9_BODY, language=None)
    assert "```\n" in render(blocks, doc_id="root")


def test_ac4_exactly_two_fence_marker_lines_are_emitted():
    """A body of indented content must not grow or lose fence lines."""
    out = _render_node("    a\n    b")
    assert [line for line in out.split("\n") if line.startswith("```")] == [
        "```python", "```",
    ]
    assert out.split("\n")[-2] == "```"


def test_ac4_content_containing_a_fence_is_unchanged_by_this_fix():
    """The documented `fence-body-containing-a-fence` projection lossiness (shipped, in
    the lossiness table) is NOT touched: the body is still carried verbatim inside a
    3-backtick fence. Pinned so the fix cannot quietly change fence width."""
    body = "```\ninner fence\n```"
    assert _render_node(body, lang="") == f"```\n{body}\n```\n"


def test_ac4_the_existing_inline_backticks_golden_shape_is_unchanged():
    body = "inline ``` and a ` tick"
    assert _render_node(body, lang="markdown") == f"```markdown\n{body}\n```\n"


# --------------------------------------------------------------------------- #
# The cross-seam question LD-144/LD-145 left standing — here it CLOSES         #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("body", [
    "    def f():\n        return 1",
    "\tif x:\n\t\treturn 1",
    "x = 1   ",
    "   ",
], ids=["spaces", "tabs", "trailing-spaces", "whitespace-only"])
def test_the_two_code_seams_now_agree_that_the_body_is_verbatim(body):
    """larkdocio serializes a code block at TWO seams: the Markdown fence
    (``_code``) and the merged-table ``<td>``'s ``<pre><code>`` (``_html_code``,
    LD-144). LD-145 had to make a deliberate DIVERGENCE call between its two seams;
    here there is none to make — ``_html_code`` never stripped, so it was already
    verbatim and the Markdown seam was the odd one out. After LD-146 both carry the
    same rule, and this test pins them TOGETHER so a future edit cannot fix or break
    one seam alone.

    The only difference left is the newline encoding the ``<td>`` context forces
    (``&#10;``, because a literal blank line would tear the HTML table apart) — a
    transport detail, not a whitespace policy."""
    renderer = MarkdownRenderer()
    node = CodeNode(lang="python", content=[StyledText(content=body)])

    md_body = _fence_body(renderer._code(node), lang="python")
    html = renderer._html_code(node)
    assert html.startswith("<pre><code>") and html.endswith("</code></pre>")
    html_body = html[len("<pre><code>"):-len("</code></pre>")].replace("&#10;", "\n")

    assert md_body == body, "the Markdown seam must be verbatim"
    assert html_body == body, "the HTML <td> seam must be verbatim"
    assert md_body == html_body, "the two seams must agree"


# --------------------------------------------------------------------------- #
# Amplifier — code is verbatim, so LD-130 escaping must not reach it          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("body", [
    "# a comment",
    "    # an indented comment",
    "- not a bullet",
    "    - an indented dash",
    "> not a quote",
    "| not | a table |",
    "1. not an ordered item",
    "---",
    "*emphasis* and _underscores_ and ~tilde~",
], ids=lambda b: b[:24])
def test_amplifier_ld130_escaping_never_reaches_code_content(body):
    """LD-130's ALWAYS-ON escaping of structural metacharacters applies to PLAIN text;
    inside a fence the content is source code and a backslash would corrupt it. No
    ``\\`` may appear that the body did not already contain (BLOCKS.md row 2: "NEVER
    escaped: … code-fence + inline-code content")."""
    node = CodeNode(lang="python", content=[StyledText(content=body)])
    assert MarkdownRenderer().render(node) == f"```python\n{body}\n```\n"


def test_amplifier_the_optin_escape_literals_sledgehammer_is_unchanged():
    """PRE-EXISTING, DELIBERATELY UNTOUCHED (issue § Out of Scope: "Escaping inside code
    content … asserted in the amplifier, not changed here").

    The opt-in ``escape_literals`` policy is documented in BLOCKS.md row 2 as "the wider
    sledgehammer" and it *does* reach code content — that is its pre-LD-146 behavior and
    LD-146 does not alter it. Pinned so the difference is visible and reviewed rather
    than mistaken for a regression: the INDENT survives either way; only the escape
    differs, exactly as before this fix."""
    node = CodeNode(lang="python", content=[StyledText(content="    # a comment")])
    assert MarkdownRenderer(escape_literals=True).render(node) == (
        "```python\n    \\# a comment\n```\n"
    )


def test_amplifier_bare_urls_are_not_linkified_inside_an_indented_fence():
    """LD-054 AC2 (code is verbatim) must keep holding for an INDENTED first line —
    the linkify pass and the verbatim pass are separate flags on the same call."""
    body = "    curl https://api.example.com/v1"
    assert _read_fence_body(body) == body


# --------------------------------------------------------------------------- #
# Amplifier — the compose→read round trip (the Markdown-authoring spec § D4) for an indented body #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("body", [
    "    def f():\n        return 1",
    "\tif x:\n\t\treturn 1",
    "   /\\_/\\\n  ( o.o )",
    "x = 1   ",
    "\nleading blank line",
], ids=["spaces", "tabs", "ascii-art", "trailing-spaces", "leading-blank"])
def test_amplifier_compose_read_round_trip_is_exact_for_an_indented_fence(body):
    """The Markdown-authoring spec § D4 for code fences: authoring an indented block with ``compose()`` and
    reading it back yields the SAME body — which only works because the reader is
    verbatim and ``compose`` removes exactly the one syntactic newline it added."""
    from compose_roundtrip import reader_markdown
    from larkdocio.write import compose

    authored = f"```python\n{body}\n```\n"
    emitted = reader_markdown(compose(authored))
    assert emitted == authored
    # And the second pass returns the same typed block — a genuine fixed point.
    assert compose(emitted) == compose(authored)


def test_amplifier_compose_carries_the_indent_into_the_block_it_creates():
    """Proof the write side was never the problem (issue § Out of Scope): the composed
    ``NewBlock`` already holds the indented body byte-for-byte."""
    from larkdocio.write import compose

    (block,) = compose(f"```python\n{T9_BODY}\n```\n")
    assert block.text == T9_BODY


# --------------------------------------------------------------------------- #
# AC6 — the docs record the verbatim guarantee, and no longer claim the strip  #
# --------------------------------------------------------------------------- #

_ROOT = Path(__file__).resolve().parents[1]
_BLOCKS_MD = _ROOT / "BLOCKS.md"
_WRITE_README = _ROOT / "src" / "larkdocio" / "write" / "README.md"
_GUIDE = _ROOT / "src" / "larkdocio" / "GUIDE.md"

#: The claims that must be GONE from every shipped doc. Before LD-146 the strip was
#: written down as if it were a decision — BLOCKS.md said the renderer "fences the
#: (stripped) inline body" and the dialect lossiness list stated the reader strips a
#: fence body's edge whitespace as a *normalization*. That is exactly how the corruption
#: survived into a second dogfood session, so the words are guarded, not just the code.
_RETIRED_CLAIMS = (
    "the renderer fences the (stripped) inline body",
    "a fence body's edge whitespace / blank lines are stripped by the reader",
)

#: The verbatim pre-LD-146 sentences, lifted from the two docs at ``develop``. Each must
#: be caught by the guard below — otherwise the "no longer claimed" assertions are vacuous.
_PRE_FIX_DOC_TEXT = {
    "BLOCKS.md": (
        "| 14 | code | rendered | creatable | `text.py` | ```` ```{lang}\\n…\\n``` ```` | "
        "~65 languages mapped via `DOCX_CODE_LANG_TO_MD`; PlainText and unmapped languages "
        "emit a fence with **no** language tag. Constructs a `CodeNode` (LD-025 migration); "
        "the renderer fences the (stripped) inline body. Byte-identical. |"
    ),
    "write/README.md": (
        "- a **fence body's edge whitespace / blank lines** are stripped by the reader on "
        "emission;"
    ),
}


def _assert_documents_verbatim(text: str) -> None:
    """``text`` states the verbatim guarantee and no longer claims the strip."""
    assert not missing_phrases(text, ["verbatim"]), text
    still_claimed = [c for c in _RETIRED_CLAIMS if not missing_phrases(text, [c])]
    assert not still_claimed, f"retired claim still documented: {still_claimed} in {text}"


def test_ac6_the_blocks_md_code_row_records_the_verbatim_guarantee():
    """AC6: type 14's matrix row is where a consumer looks up what the reader promises."""
    rows = [ln for ln in _BLOCKS_MD.read_text(encoding="utf-8").split("\n")
            if ln.startswith("| 14 |")]
    assert len(rows) == 1, rows
    _assert_documents_verbatim(rows[0])
    # It must say WHICH whitespace survives — "verbatim" alone is the kind of word that
    # stays true-sounding while the detail rots.
    assert not missing_phrases(rows[0], ["leading whitespace", "trailing whitespace",
                                         "byte-for-byte"]), rows[0]


def test_ac6_the_dialect_doc_no_longer_lists_the_strip_as_a_normalization():
    """The shipped lossiness/normalization list must not describe the defect as a rule."""
    text = _WRITE_README.read_text(encoding="utf-8")
    still_claimed = [c for c in _RETIRED_CLAIMS if not missing_phrases(text, [c])]
    assert not still_claimed, f"retired claim still in write/README.md: {still_claimed}"
    assert not missing_phrases(text, ["a code fence body is the one thing not normalized"]), (
        "the dialect doc must state the verbatim carve-out positively"
    )


def test_ac6_the_shipped_guide_records_the_same_guarantee():
    """The in-wheel guide (`larkdocio.guide()`) must not disagree with write/README.md."""
    rows = [ln for ln in _GUIDE.read_text(encoding="utf-8").split("\n")
            if ln.startswith("| `code` |")]
    assert len(rows) == 1, rows
    _assert_documents_verbatim(rows[0])


@pytest.mark.parametrize("doc", sorted(_PRE_FIX_DOC_TEXT))
def test_ac6_the_docs_guard_bites_on_the_real_pre_fix_text(doc):
    """The guard earns its lines only by failing on the text it replaced (the LD-138
    red-then-green discipline for a prose guard). Fed the VERBATIM pre-LD-146 sentence, it
    must redden — which also keeps ``_RETIRED_CLAIMS`` honest: a phrase spelled with the
    wrong punctuation would match nothing and pass every doc vacuously."""
    stale = _PRE_FIX_DOC_TEXT[doc]
    with pytest.raises(AssertionError):
        _assert_documents_verbatim(stale)
    caught = [c for c in _RETIRED_CLAIMS if not missing_phrases(stale, [c])]
    assert caught, f"no retired claim matches the real pre-fix {doc} text: {stale!r}"


def test_ac6_every_retired_claim_is_detectable_in_the_pre_fix_text():
    """No dead entry in ``_RETIRED_CLAIMS`` — each must really appear in a pre-fix row, so
    the tuple cannot silently decay into decoration."""
    for claim in _RETIRED_CLAIMS:
        assert any(not missing_phrases(t, [claim]) for t in _PRE_FIX_DOC_TEXT.values()), (
            f"{claim!r} matches none of the pre-fix rows — it guards nothing")


def test_ac6_the_verbatim_guard_is_not_satisfied_by_the_word_alone():
    """The trap this guard must not fall into: BLOCKS.md row 2 and the LD-054 comments
    already used the word "verbatim" loosely about code content while the body was in fact
    stripped, so a bare "mentions verbatim" check would have passed the whole pre-fix
    tree. The row-level guard therefore also demands the specific whitespace claims."""
    hand_wavy = "| 14 | code | the renderer fences the (stripped) inline body, verbatim. |"
    with pytest.raises(AssertionError):
        _assert_documents_verbatim(hand_wavy)
