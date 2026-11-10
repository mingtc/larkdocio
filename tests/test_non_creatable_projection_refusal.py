"""A reader-originated fence: the projection refusal, and the fence that OUTGREW it
(LD-177, superseded for mermaid by LD-192).

**LD-177's bug, in one line.** The reader projects a Mermaid diagram (an add-on block, docx
block type 40) into a ```` ```mermaid ```` fence, and ``compose()`` refused that fence as
``unknown-code-language`` — *"use one of supported_code_languages()"* — advice pointed at the
caller for a token **larkdocio itself wrote**, and advice that cannot succeed for that
content. LD-177 gave that case its own construct (``non-creatable-projection``) and recorded a
standing note on the registry it added:

    *a token that later becomes authorable leaves this table in the same change that makes it
    creatable.*

**LD-192 is that change, and this file is updated deliberately rather than relaxed.** A
diagram is now a creatable kind (``NewBlock.mermaid``), so the reader's own ```` ```mermaid ````
fence **composes**, and refusing it would be the new falsehood. What that costs, and how each
cost is paid, is the whole point of the layout below:

* **the mermaid half flips** — the tests that asserted a refusal now assert the *round trip*,
  which is the property LD-177 could only qualify (its own docstring said the misdirection
  "lands on the library's own headline claim"; the claim is now simply true for this fence);
* **the mechanism does NOT go with it.** ``READER_PROJECTION_FENCES`` is empty today, so the
  refusal path has no shipped row to exercise it. It is therefore proven against an
  **injected** row — a hypothetical future projection — so every behavior LD-177 pinned
  (the construct, the wording, the "names our own reader" substance, the recovery, the
  registry contract) is still asserted and will work on the day a real row appears. Deleting
  those tests because nothing ships in the table today is exactly how a refusal path rots;
* **the invariant is generalized, not dropped.** LD-177 pinned "the renderer's emitted fence
  token has a registry row". That is now the *special case* of the true rule — **every fence
  token the reader emits either composes or has a registry row** — which is strictly stronger,
  cannot be satisfied by an empty table, and is what actually protects the caller;
* **everything about the caller-invented case is byte-unchanged**, deliberately: that advice
  was correct and stays correct, and the two paths must stay distinguishable;
* **the reader is byte-unchanged**, now doubly load-bearing. LD-177 guarded against "fixing"
  the round trip by changing what the reader emits; this issue closes the round trip *without*
  touching the projection, and the goldens are the proof.
"""
import json
import re
from pathlib import Path

import pytest

from harness import render
from larkdocio import capabilities, guide
from larkdocio.model.nodes import AddOnsNode
from larkdocio.model.renderer import MarkdownRenderer
from larkdocio.write import NOT_EXPRESSIBLE_CONSTRUCTS, compose
from larkdocio.write.compose import MERMAID_FENCE_TOKEN, READER_PROJECTION_FENCES
from larkdocio.write.model import NewBlockKind, RefusalReason, RefusedError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_MERMAID_COMPONENT_TYPE_ID = "blk_640017963d808005a21a6445"

#: The refusal the caller-invented case must keep, **verbatim** — it is correct there.
_UNKNOWN_LANGUAGE_ADVICE = (
    "Lark has no language enum for that fence token — use one of "
    "larkdocio.langs.supported_code_languages(), or a bare ``` fence (it is never "
    "silently downgraded)"
)

#: The merged-table wording this issue must NOT touch (already disclosed lossiness).
_MERGED_TABLE_WHY = (
    "a merged (colspan/rowspan) table is not expressible — Markdown has no span "
    "syntax, so an authored table is always a plain rectangular grid (give every row "
    "the header's cell count; use an empty string for a blank cell). The grid is never "
    "padded or truncated to fit"
)

#: LD-177's projection wording, which **stays exactly as it shipped**. The construct is still
#: the right answer for a projection fence; only its *membership* changed.
_PROJECTION_WHY = (
    "that fence is a PROJECTION this library's own reader wrote, not a code block: the "
    "block behind it (named below) has no creatable form here today, so the fence token "
    "is not a language and no supported token would author the block back — the token is "
    "not the caller's mistake. Drop the fence and leave that block to the editor, or "
    "keep the text under a bare ``` fence to author it verbatim as a code block; "
    "everything around it composes"
)

#: A **hypothetical** future projection, used to exercise the refusal path now that no real
#: row ships. Deliberately not a plausible near-term token: it must be obvious in a failure
#: message that this row is a test fixture and not a shipped capability claim.
_HYPOTHETICAL_TOKEN = "someunshippedprojection"
_HYPOTHETICAL_WHAT = "a hypothetical future add-on block (docx block type 9999)"

_MERMAID_SOURCE = "graph TD\n  A --> B"


def _page(*children):
    return {"block_id": "page", "block_type": 1, "children": [c["block_id"] for c in children],
            "page": {"elements": [{"text_run": {"content": "Doc Title"}}]}}


def _text(block_id, content):
    return {"block_id": block_id, "block_type": 2,
            "text": {"elements": [{"text_run": {"content": content}}]}}


def _mermaid(block_id, source=_MERMAID_SOURCE):
    return {
        "block_id": block_id,
        "block_type": 40,
        "add_ons": {
            "component_id": "",
            "component_type_id": _MERMAID_COMPONENT_TYPE_ID,
            "record": json.dumps({"data": source, "theme": "default", "view": "codeChart"}),
        },
    }


def _document(*blocks):
    """Render a whole document through the SHIPPED read path (the report's repro shape)."""
    return render([_page(*blocks), *blocks])


def _refusal(markdown):
    with pytest.raises(RefusedError) as exc:
        compose(markdown)
    return exc.value.refusal


@pytest.fixture
def hypothetical_projection(monkeypatch):
    """Install one **injected** projection row for the duration of a test.

    This is what keeps LD-177's refusal path proven now that the shipped registry is empty.
    ``compose`` reads the registry at call time, so a ``setitem`` is a faithful stand-in for a
    future row — no production code is touched, and the row is gone when the test ends
    (asserted by :func:`test_the_shipped_registry_is_empty_and_that_is_the_point`, which runs
    without the fixture).
    """
    monkeypatch.setitem(READER_PROJECTION_FENCES, _HYPOTHETICAL_TOKEN, _HYPOTHETICAL_WHAT)
    return _HYPOTHETICAL_TOKEN


# =========================================================================== #
# LD-192 AC4/AC5 — THE FENCE THAT OUTGREW THE REFUSAL                          #
# The tests LD-177 wrote as refusals, flipped to the round trip they blocked.    #
# =========================================================================== #

def test_the_readers_own_mermaid_fence_now_COMPOSES_instead_of_refusing():
    """The exact document LD-177 used as its repro, run through the exact same path — and it
    composes. This is the supersession, stated as a single assertion.
    """
    document = _document(_mermaid("b40"))
    assert "```mermaid" in document, "the fixture must reproduce the reader's projection"

    content = compose(document)
    kinds = [b.kind for b in content]
    assert NewBlockKind.MERMAID in kinds, kinds
    diagram = next(b for b in content if b.kind is NewBlockKind.MERMAID)
    assert diagram.text == _MERMAID_SOURCE


def test_AC5_the_ROUND_TRIP_property_now_HOLDS_for_a_document_carrying_a_diagram():
    """AC5, whole and end to end: read a document containing a diagram → feed **its own reader
    output** back to ``compose()`` → every block composes, the diagram included, in order.

    LD-177 had to qualify this claim; here it simply holds. The prose blocks around the
    diagram are asserted too, because "the diagram composes but the document does not" would
    be a hollow version of the property.
    """
    document = _document(_text("t1", "intro"), _mermaid("b40"), _text("t2", "outro"))
    content = compose(document)
    assert [b.kind for b in content] == [
        NewBlockKind.HEADING,        # the page title
        NewBlockKind.PARAGRAPH,      # intro
        NewBlockKind.MERMAID,        # the diagram — the block this issue made creatable
        NewBlockKind.PARAGRAPH,      # outro
    ]
    assert content[2].text == _MERMAID_SOURCE


def test_AC5_a_MULTI_diagram_document_composes_every_one_of_them():
    """LD-177's multi-diagram loop, pointed the other way: where it asserted the refusal moved
    from the first fence to the second, this asserts **both** now compose, with their own
    sources kept apart."""
    first, second = "graph TD\n  A --> B", "flowchart LR\n  X --> Y"
    document = _document(
        _text("t1", "intro"), _mermaid("b1", first),
        _text("t2", "middle"), _mermaid("b2", second),
    )
    diagrams = [b for b in compose(document) if b.kind is NewBlockKind.MERMAID]
    assert [d.text for d in diagrams] == [first, second]


def test_AC5_the_composed_diagram_re_encodes_to_the_block_it_was_READ_from():
    """The round trip closed at the **payload**, not just at the type: composing the reader's
    fence and encoding the result reproduces the ``add_ons`` block the document held.

    The one documented normalization: the reader ``strip()``s the source when it writes the
    fence (shipped behavior, untouched here), so a source with surrounding blank lines comes
    back stripped. Asserted rather than glossed over — and the *stripped* form is a fixed
    point, which is the property that actually matters for a read-edit-write loop.
    """
    from larkdocio.write.encode import encode_block

    padded = f"\n\n{_MERMAID_SOURCE}\n\n"
    document = _document(_mermaid("b40", padded))
    diagram = next(b for b in compose(document) if b.kind is NewBlockKind.MERMAID)

    assert diagram.text == _MERMAID_SOURCE, "the reader's strip() is the normalization"
    payload = encode_block(diagram)
    assert payload["block_type"] == 40
    assert payload["add_ons"]["component_type_id"] == _MERMAID_COMPONENT_TYPE_ID
    assert json.loads(payload["add_ons"]["record"])["data"] == _MERMAID_SOURCE

    # …and composing the SECOND read is a fixed point: no further drift on any later pass.
    again = _document(_mermaid("b40", _MERMAID_SOURCE))
    assert next(b for b in compose(again) if b.kind is NewBlockKind.MERMAID).text == \
        _MERMAID_SOURCE


def test_the_mermaid_token_left_the_registry_in_THIS_change():
    """The supersession, asserted against the registry itself so it cannot be half-done: the
    token is out of the table **and** it composes. Either alone would be a bug — still in the
    table and composing means dead code; out of the table and not composing means the caller
    gets the unknown-token advice for a token we wrote, which is the very defect LD-177 fixed.
    """
    assert MERMAID_FENCE_TOKEN not in READER_PROJECTION_FENCES
    content = compose(f"```{MERMAID_FENCE_TOKEN}\n{_MERMAID_SOURCE}\n```\n")
    assert [b.kind for b in content] == [NewBlockKind.MERMAID]


def test_an_EMPTY_mermaid_fence_refuses_rather_than_authoring_an_INVISIBLE_block():
    """The one thing a mermaid fence can still get wrong. An empty diagram source is accepted
    by Lark and renders as nothing at all — no fence, no marker — so composing it would author
    an invisible block. It refuses, with the reason named."""
    refusal = _refusal("```mermaid\n```\n")
    assert "empty-mermaid" in refusal.detail
    assert refusal.reason is RefusalReason.NOT_IN_DIALECT
    low = refusal.detail.lower()
    assert "nothing" in low and "source" in low, refusal.detail


# =========================================================================== #
# LD-192 AC4 — THE CALLER-INVENTED CASE IS BYTE-UNCHANGED                       #
# Nothing below this line was edited for this issue. It is the half that must    #
# NOT move: the old advice is correct for a token the caller really invented.    #
# =========================================================================== #

@pytest.mark.parametrize("token", ["banana", "brainfsck", "myownlang"])
def test_ac2_a_caller_invented_token_keeps_the_existing_advice_verbatim(token):
    """The old message is CORRECT here: the caller really did pick a token Lark has no enum
    for. It must survive byte-for-byte, and must not mention the projection."""
    refusal = _refusal(f"```{token}\nx = 1\n```\n")
    assert "unknown-code-language" in refusal.detail
    assert _UNKNOWN_LANGUAGE_ADVICE in refusal.detail
    assert f"(fence token: {token!r};" in refusal.detail
    assert "non-creatable-projection" not in refusal.detail
    assert "projection" not in refusal.detail.lower()


def test_ac2_the_unknown_language_entry_text_is_unchanged():
    assert NOT_EXPRESSIBLE_CONSTRUCTS["unknown-code-language"] == _UNKNOWN_LANGUAGE_ADVICE


@pytest.mark.parametrize("token", ["json", "python", "markdown"])
def test_ac2_a_reader_emitted_supported_token_still_composes(token):
    """The report's per-token results: the supported tokens the reader emits compose — so
    neither the new mermaid branch nor the projection path can swallow the ordinary case."""
    content = compose(f"```{token}\npayload\n```\n")
    assert [b.kind for b in content] == [NewBlockKind.CODE]
    assert content[0].language == token


def test_a_bare_fence_still_composes_as_an_unlabelled_code_block():
    """The recovery LD-177's refusal advised is still available and still means what it said —
    it is simply no longer the *only* way to get a diagram's text into a document."""
    content = compose(f"```\n{_MERMAID_SOURCE}\n```\n")
    assert [b.kind for b in content] == [NewBlockKind.CODE]
    assert content[0].language is None
    assert content[0].text == _MERMAID_SOURCE


def test_the_mermaid_token_is_still_NOT_a_lark_code_language():
    """Why the new branch sits **before** the language table rather than in it: ``mermaid`` is
    not a code-language enum, so a fall-through would still reach the unknown-token advice."""
    from larkdocio.langs import MD_LANG_TO_DOCX_CODE

    assert MERMAID_FENCE_TOKEN not in MD_LANG_TO_DOCX_CODE


def test_the_three_fence_outcomes_stay_DISTINCT_from_one_shape():
    """One fence shape, three outcomes, chosen by whose token it is and what it names."""
    diagram = compose(f"```mermaid\n{_MERMAID_SOURCE}\n```\n")
    code = compose(f"```python\n{_MERMAID_SOURCE}\n```\n")
    invented = _refusal(f"```banana\n{_MERMAID_SOURCE}\n```\n")

    assert [b.kind for b in diagram] == [NewBlockKind.MERMAID]
    assert [b.kind for b in code] == [NewBlockKind.CODE]
    assert "unknown-code-language" in invented.detail
    assert "non-creatable-projection" not in invented.detail


# =========================================================================== #
# LD-192 AC4 — THE PROJECTION MECHANISM STAYS PROVEN, ON AN INJECTED ROW        #
# Every behavior LD-177 pinned, still pinned. The guard is not weakened.        #
# =========================================================================== #

def test_the_shipped_registry_is_empty_and_that_is_the_point():
    """Deliberately empty, for a stated reason — not empty by accident.

    Runs **without** the injection fixture, so it also proves the fixture leaks nothing into
    the shipped state. The reader emits exactly two fence forms (a code block's language
    token, and the diagram token), and both compose, so there is nothing left to register.
    """
    assert READER_PROJECTION_FENCES == {}


def test_the_projection_construct_STILL_SHIPS_with_its_wording_byte_unchanged():
    """The construct outlives its one row. Its text is what a future projection's refusal will
    say, so it is pinned byte-for-byte exactly as the caller-invented advice is."""
    assert NOT_EXPRESSIBLE_CONSTRUCTS["non-creatable-projection"] == _PROJECTION_WHY


def test_an_injected_projection_still_refuses_as_a_projection(hypothetical_projection):
    """LD-177's headline behavior, re-proven: a registered projection token gets its **own**
    construct, and none of the caller-blaming advice."""
    detail = _refusal(f"```{hypothetical_projection}\nbody\n```\n").detail
    assert "non-creatable-projection" in detail
    assert "supported_code_languages" not in detail, detail
    assert "use one of" not in detail, detail
    assert "Lark has no language enum" not in detail, detail


def test_an_injected_projection_refusal_names_our_reader_the_block_and_the_recovery(
        hypothetical_projection):
    """LD-177's substance test, unchanged in what it demands: whose token it is, what the
    block really is, and what to do."""
    detail = _refusal(f"```{hypothetical_projection}\nbody\n```\n").detail
    low = detail.lower()
    assert "reader" in low, detail
    assert "projection" in low, detail
    assert _HYPOTHETICAL_WHAT in detail, detail
    assert "bare ```" in low or "bare fence" in low, detail
    assert f"{hypothetical_projection!r}" in detail, detail


def test_an_injected_projection_refusal_claims_no_permanent_impossibility(
        hypothetical_projection):
    """LD-177's AC1 wording rule, and this issue is the proof it was the right rule: the
    refusal said the library does not create one **today**, and today arrived for mermaid."""
    detail = _refusal(f"```{hypothetical_projection}\nbody\n```\n").detail.lower()
    for forbidden in ("never creatable", "cannot ever", "impossible", "will never"):
        assert forbidden not in detail, f"{forbidden!r} asserts permanence: {detail}"
    assert "today" in detail or "yet" in detail, detail


def test_an_injected_projection_refusal_names_the_offending_fences_own_line(
        hypothetical_projection):
    """A real document carries several fences — the refusal must say WHICH one."""
    markdown = (
        f"intro\n\n```{hypothetical_projection}\nbody\n```\n\nouter\n"
    )
    line = markdown.split("\n").index(f"```{hypothetical_projection}") + 1
    assert f"at line {line}" in _refusal(markdown).detail


def test_an_injected_projection_stays_DISTINCT_from_a_caller_invented_token(
        hypothetical_projection):
    """The two-path distinction LD-177 exists to preserve, still preserved."""
    projection = _refusal(f"```{hypothetical_projection}\nbody\n```\n")
    invented = _refusal("```banana\nbody\n```\n")
    assert "non-creatable-projection" in projection.detail
    assert "unknown-code-language" in invented.detail
    assert projection.detail != invented.detail
    assert "non-creatable-projection" not in invented.detail
    assert "unknown-code-language" not in projection.detail


def test_the_registry_contract_holds_for_whatever_is_in_it(hypothetical_projection):
    """LD-177's registry contract, applied to the table's contents whatever they are — so it
    binds a real future row exactly as it bound mermaid: a key is never a code language, its
    value reads as a lowercase noun phrase, and it refuses as a projection naming that value.
    """
    from larkdocio.langs import MD_LANG_TO_DOCX_CODE

    assert READER_PROJECTION_FENCES
    for token, what in READER_PROJECTION_FENCES.items():
        assert token not in MD_LANG_TO_DOCX_CODE, (
            f"{token!r} IS a supported code language — it is not a projection")
        assert what and what[0].islower()
        detail = _refusal(f"```{token}\nbody\n```\n").detail
        assert "non-creatable-projection" in detail
        assert what in detail


# =========================================================================== #
# LD-192 AC4 — THE INVARIANT, GENERALIZED (strictly stronger than LD-177's)     #
# =========================================================================== #

def _renderer_fence_token():
    """The fence token the renderer really emits for a diagram add-on — read off its own
    output, never hand-written, exactly as LD-177 read it."""
    emitted = MarkdownRenderer().render(AddOnsNode(mermaid_source=_MERMAID_SOURCE))
    return re.match(r"^```([A-Za-z0-9_+-]+)\n", emitted).group(1)


def test_EVERY_fence_token_the_reader_emits_either_COMPOSES_or_has_a_registry_row():
    """**The generalized invariant** — LD-177's guard was the special case of this one.

    Its version asked "is the renderer's token a registry key?", which an authorable token
    would fail for a *good* reason and which an empty table trivially fails. The real rule is
    that the caller must never be blamed for a token we wrote: so the token must either
    compose, or be registered so the refusal can name the real cause. That is what is asserted
    here, and it cannot be satisfied by emptying the table.
    """
    token = _renderer_fence_token()
    if token in READER_PROJECTION_FENCES:
        detail = _refusal(f"```{token}\nbody\n```\n").detail
        assert "non-creatable-projection" in detail
        return
    content = compose(f"```{token}\n{_MERMAID_SOURCE}\n```\n")
    assert content, f"the reader emits ```{token} and compose() produced nothing for it"
    detail_free = [b for b in content if b.kind is not NewBlockKind.CODE]
    assert detail_free, (
        f"the reader emits ```{token} for a NON-code block, so composing it as a code block "
        f"would be a silent downgrade")


def test_the_renderers_token_is_the_constant_the_compiler_reads():
    """One word, two halves. LD-177 guarded this pairing through the registry; with the
    registry empty it is guarded directly, so the renderer and the compiler still cannot
    drift apart on the spelling of the fence."""
    assert _renderer_fence_token() == MERMAID_FENCE_TOKEN


# =========================================================================== #
# LD-192 AC8 — mermaid is FINDABLE, and now findable as CREATABLE               #
# =========================================================================== #

def test_ac3_mermaid_is_findable_in_the_guide_and_in_capabilities():
    """The 0-hit condition the report measured (``mermaid`` appeared 0 times in the guide
    and 0 times in the capability registry) cannot return."""
    assert "mermaid" in guide(full=True).lower()
    assert "mermaid" in json.dumps(capabilities(full=True)).lower()


def test_the_capability_floor_now_names_mermaid_as_CREATABLE_not_as_a_refusal():
    """The floor is the discovery surface a consumer plans against, so it is the one that must
    stop saying *"this rung does not author one"*.

    The assertion is on the **claim**, not on the word: ``mermaid`` legitimately still appears
    in ``not_creatable`` — because the **in-place update** genuinely is not available — so a
    crude "the word is gone" check would force the honest disclosure out. What must be gone is
    the specific falsehood, and what must be present is the diagram among the creatable kinds.
    """
    floor = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    assert "mermaid" in floor["creatable_kinds"], floor["creatable_kinds"]
    assert 40 in floor["creatable_block_types"], floor["creatable_block_types"]

    not_creatable = " ".join(floor["not_creatable"]).lower()
    for stale in ("this rung does not author one", "non-creatable-projection",
                  "never the caller's language choice"):
        assert stale not in not_creatable, (
            f"the floor still carries the pre-LD-192 claim {stale!r}: {floor['not_creatable']}")


def test_AC3_the_floor_DISCLOSES_the_in_place_update_no_go_rather_than_hiding_it():
    """AC3's other half. The NO-GO is a real constraint on a consumer's architecture — an
    id-anchored projection that caches a type-40 block id across an edit is unsound — so the
    discovery surface has to *say* so, not merely omit an update op and let the consumer find
    out. Every load-bearing word is asserted."""
    floor = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    disclosure = next(
        (row for row in floor["not_creatable"] if "mermaid" in row.lower()), None)
    assert disclosure is not None, floor["not_creatable"]
    low = disclosure.lower()
    for required in ("in-place", "block_id", "delete", "same index", "unsound"):
        assert required in low, f"the disclosure omits {required!r}: {disclosure}"


def test_the_guide_and_the_writer_brief_document_BOTH_the_construct_and_the_diagram():
    """The packaged docs must carry the projection construct (it still ships) **and** must say
    the diagram is authorable — a doc that kept only the old half would deny a capability the
    same wheel provides."""
    from larkdocio import writer_brief

    for name, text in (("guide", guide(full=True)), ("writer brief", writer_brief())):
        assert "`non-creatable-projection`" in text, f"{name} has no projection row"
        low = text.lower()
        assert "mermaid" in low, name
        assert "block type 40" in low, name
        assert "newblock.mermaid" in low, f"{name} does not name the authoring call"


# =========================================================================== #
# LD-177 AC4 — THE ROUND-TRIP CLAIM IS STILL GUARDED WHERE IT IS STATED         #
#                                                                               #
# These are LD-177's own claim guards, KEPT. They are not incidental to this     #
# issue: LD-177 wrote them because the guide states the round-trip property as   #
# the reason authoring in Markdown is safe, so that sentence is the library's    #
# headline claim and must neither vanish nor lose its qualification. LD-192      #
# rewrote both paragraphs — which is exactly when a claim guard earns its keep,  #
# and exactly when it is easiest to drop by accident.                            #
#                                                                               #
# Re-pointed, not relaxed: both claim sentences survive the rewrite verbatim, so #
# the assertions are LD-177's, and a third check is added for the half LD-192    #
# changed (the paragraph must record that the diagram fence composes now), so a  #
# later edit cannot quietly restore the old hedge while keeping the claim.       #
# =========================================================================== #

_ROUNDTRIP_CLAIMS = (
    "anything you can read you can compose back",
    "turns back into the same content",
)


def claim_problems(text):
    """Every way ``text`` fails the round-trip-claim contract — the ONE predicate.

    Factored out so the shipped assertions and the must-bite arm below run the *same* code
    over different input. A guard whose only evidence is that it passes on the shipped text is
    indistinguishable from a guard that cannot fail.
    """
    problems = []
    for claim in _ROUNDTRIP_CLAIMS:
        if claim not in text:
            problems.append(f"the round-trip claim {claim!r} was weakened away")
            continue
        paragraph = next(p for p in text.split("\n\n") if claim in p)
        low = paragraph.lower()
        if "creatable" not in low:
            problems.append(f"{claim!r}'s paragraph does not scope it to the creatable set")
        if "lossiness" not in low:
            problems.append(f"{claim!r}'s paragraph does not point at the lossiness table")
    return problems


@pytest.mark.parametrize("claim", _ROUNDTRIP_CLAIMS)
def test_ac4_the_claim_is_still_made(claim):
    """Do not over-hedge: the property is true and load-bearing, so the sentence stays.

    It is MORE true after this issue than before — the diagram fence was the one construct
    that made it "almost" hold — so weakening it here would be exactly backwards.
    """
    assert claim in guide(full=True), f"the round-trip claim {claim!r} was weakened away"


@pytest.mark.parametrize("claim", _ROUNDTRIP_CLAIMS)
def test_ac4_the_claim_carries_its_exception_list_in_the_same_paragraph(claim):
    """Precisely qualified where it is stated: the paragraph making the claim also says the
    claim is over the CREATABLE set and points at the lossiness table as the exceptions."""
    paragraph = next(p for p in guide(full=True).split("\n\n") if claim in p)
    low = paragraph.lower()
    assert "creatable" in low, paragraph
    assert "lossiness" in low, paragraph


def test_ac4_the_shipped_guide_satisfies_the_claim_contract():
    assert claim_problems(guide(full=True)) == []


@pytest.mark.parametrize("claim", _ROUNDTRIP_CLAIMS)
def test_the_claim_guard_BITES_when_the_sentence_is_deleted(claim):
    """The anti-vacuity arm — the reason the predicate is factored out.

    Deleting either claim sentence from the guide's text must be *detected*. Run against a
    mutated copy in memory (no file is touched), which is how this can be proven on every run
    rather than once by hand.
    """
    mutated = guide(full=True).replace(claim, "")
    problems = claim_problems(mutated)
    assert problems, f"deleting {claim!r} went undetected — the guard is vacuous"
    assert any(claim in p for p in problems), problems


@pytest.mark.parametrize("dropped", ["creatable", "lossiness"])
def test_the_claim_guard_BITES_when_the_qualification_is_dropped(dropped):
    """The qualification half must bite too: a claim that keeps its sentence but loses its
    scope is the over-claim LD-177 was written to prevent."""
    text = guide(full=True)
    claim = _ROUNDTRIP_CLAIMS[0]
    paragraph = next(p for p in text.split("\n\n") if claim in p)
    stripped = paragraph.replace(dropped, "XXX").replace(dropped.capitalize(), "XXX")
    problems = claim_problems(text.replace(paragraph, stripped))
    assert problems, f"dropping {dropped!r} from the claim's paragraph went undetected"


def test_ac4_the_claim_paragraphs_record_THIS_ISSUES_correction():
    """The half LD-192 changed. Both paragraphs used to name the diagram fence as a *standing
    exception* to the round trip; they now record that it composes. Guarded so a future edit
    cannot restore the old hedge while leaving the claim sentence in place — which would read
    as correct and be false.
    """
    text = guide(full=True)
    for claim in _ROUNDTRIP_CLAIMS:
        paragraph = next(p for p in text.split("\n\n") if claim in p)
        low = " ".join(paragraph.lower().split())
        assert "mermaid" in low, (
            f"{claim!r}'s paragraph no longer mentions the diagram fence at all: {paragraph}")
        for stale in ("has no creatable form for it yet, projected as a",
                      "one entry of which is the reader's own projection of a block it does "
                      "not create today"):
            assert stale not in low, (
                f"{claim!r}'s paragraph restored the pre-LD-192 hedge: {stale!r}")


# =========================================================================== #
# AC6 — the merged-table half is NOT re-opened                                 #
# =========================================================================== #

def test_ac6_the_readers_merged_table_still_refuses_with_its_own_reason():
    merged = (FIXTURES / "merged_table.expected.md").read_text(encoding="utf-8")
    refusal = _refusal(merged)
    assert "merged-table" in refusal.detail
    assert refusal.reason is RefusalReason.MERGE_NOT_EXPRESSIBLE
    assert "non-creatable-projection" not in refusal.detail


def test_ac6_the_merged_table_wording_is_byte_unchanged():
    assert NOT_EXPRESSIBLE_CONSTRUCTS["merged-table"] == _MERGED_TABLE_WHY


# =========================================================================== #
# AC7 — the READER is byte-unchanged (this issue changes the WRITE side only)   #
# =========================================================================== #

def test_ac7_the_reader_still_emits_the_same_mermaid_fence_byte_for_byte():
    """The trap this test exists to catch, and it matters MORE here than it did in LD-177:
    that issue could only have been tempted to change the reader; this one closes the round
    trip and could have "closed" it by making the reader emit something easier to compose.
    It does not. The projection is out of scope — the goldens are the contract."""
    assert MarkdownRenderer().render(AddOnsNode(mermaid_source=_MERMAID_SOURCE)) == (
        "```mermaid\ngraph TD\n  A --> B\n```\n"
    )
    golden = (FIXTURES / "mermaid.expected.md").read_text(encoding="utf-8")
    produced = render(json.loads(
        (FIXTURES / "mermaid.input.json").read_text(encoding="utf-8")))
    assert produced == golden


def test_ac7_an_empty_diagram_source_still_renders_as_NOTHING():
    """The shipped reader rule the ``empty-mermaid`` refusal is derived from, pinned here so
    the derivation cannot rot: a falsy source emits nothing at all."""
    assert MarkdownRenderer().render(AddOnsNode(mermaid_source="")) == ""
    assert MarkdownRenderer().render(AddOnsNode(mermaid_source=None)) == ""


# =========================================================================== #
# The corpus-level sanity check — LD-177's 25 / 2 becomes 26 / 1                 #
# =========================================================================== #

def _corpus_sections():
    """26 sections in the reader's own dialect + the 1 that still refuses.

    LD-177 measured 25 composable / 2 refusing. The diagram section **moved across the line**
    — which is the whole issue in one number — leaving the merged table as the only refusal.
    """
    composable = [
        "# Overview",
        "## Scope",
        "### Detail",
        "A plain paragraph of prose.",
        "A second paragraph, with a soft break\nover two lines.",
        "- a bullet\n- another bullet",
        "- outer\n\t- nested",
        "1. first\n2. second",
        "- [ ] open task\n- [x] done task",
        "> a quoted line",
        "```json\n{\"a\": 1}\n```",
        "```python\nx = 1\n```",
        "```markdown\n# not a heading, it is content\n```",
        "```\na bare fence body\n```",
        "| a | b |\n| --- | --- |\n| 1 | 2 |",
        "Escaped structure: \\# not a heading.",
        "A bare URL: https://example.com/x",
        "#### Deeper heading",
        "##### Deeper still",
        "###### The sixth level",
        "Another paragraph.",
        "* a star bullet",
        "+ a plus bullet",
        "1) a paren-ordered item",
        "```yaml\nkey: value\n```",
        # the section that crossed the line in this issue
        (FIXTURES / "mermaid.expected.md").read_text(
            encoding="utf-8").split("# Doc Title\n\n", 1)[1].strip(),
    ]
    assert len(composable) == 26
    refusing = [
        (FIXTURES / "merged_table.expected.md").read_text(
            encoding="utf-8").split("# Doc Title\n\n", 1)[1].strip(),
    ]
    return composable, refusing


def test_the_corpus_composes_26_and_refuses_1_section_by_section():
    composable, refusing = _corpus_sections()
    composed, refused = 0, []
    for section in composable + refusing:
        try:
            compose(section + "\n")
            composed += 1
        except RefusedError as refusal:
            refused.append(refusal.refusal.detail)
    assert composed == 26, refused
    assert len(refused) == 1, refused
    assert "merged-table" in refused[0], refused


def test_the_whole_corpus_document_refuses_only_at_the_merged_table():
    """LD-177's whole-document check: the first refusing construct is named with its line. For
    a document whose diagram used to come first, that used to be the projection — now the
    diagram passes straight through and the merged table is the only stop left."""
    composable, refusing = _corpus_sections()
    document = "\n\n".join(composable + refusing) + "\n"
    detail = _refusal(document).detail
    assert "merged-table" in detail
    assert "non-creatable-projection" not in detail
    assert "```mermaid" in document, "the corpus must still contain the diagram section"
