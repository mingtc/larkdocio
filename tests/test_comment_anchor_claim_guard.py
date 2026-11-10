# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE CONTENT GUARD for what the two docx edit paths CLAIM about comment anchors.

The history this file carries
----------------------------
It began as the guard on a **false reassurance**: ``to_write_elements`` told every reader
that because there is no lossy Markdown round-trip, "per-run bold / inline_code / color /
**comment metadata** is never dropped". The comment half was false and it shipped in the
wheel — ``_clean_style``'s key set is closed and excluded ``comment_ids`` — so an inline
comment anchor on a rebuilt run was always lost. The packaged writer brief repeated the
reassurance in **two** places, one of which a flat substring grep walks straight past
because the phrase splits across a line wrap. That guard deleted the reassurance and
demanded an honest **blanket disclosure** in its place: *"inline comment anchors are
dropped … a fix is planned"*.

The fix landed, and the blanket disclosure is now **false in the other direction**, per
path. So this guard is superseded in place, keeping every side that still bites and
replacing the one that does not:

* **the reassurance stays FORBIDDEN, at full strength** — and it is not a formality now
  that a path really does re-emit the ids. What this library controls is the **payload**;
  whether Lark keeps a comment attached to the text afterwards is the server's own
  behaviour, and the round-2 probe proved it does not re-attach an anchor once a patch has
  dropped it. So a shipped surface may state what each path *does* — in loss and refusal
  terms — and may not promise a reader that their comment survives;
* **the blanket disclosure is now FORBIDDEN too** ("inline comment anchors are dropped",
  "a fix is planned"), because the fix is not planned, it is here, and the loss is no
  longer general;
* **the PER-PATH truth is REQUIRED**, both halves, on every surface that tells a reader
  what the rebuild keeps: the **sub-span** path re-emits each run's anchors on the run that
  replaces its text, and the **element-level** path refuses when the block carries inline
  comment anchors. Coupled on purpose — "refused" alone is a dead end, and "the ids ride
  along" alone invites the whole-block edit that will refuse;
* **the enumeration stays DERIVED from the code** — the shipped slash-list is compared
  against ``_clean_style``'s actual key set in **both** directions. The reducer stayed
  **style-only** (an anchor is not styling, which is exactly why it was invisible to it),
  so that comparison is unchanged and the anchor is pinned at the rebuild instead;
* and the **behaviour pin against a real captured payload** is inverted: the element-level
  body must still be **byte-identical** to what shipped (the rejected leading-run variant
  can never sneak in) while the sub-span body must now carry the ids.

A ``#`` comment is out of scope by construction (the AST never yields one): a maintainer
standing in this repo may write whatever shorthand they like next to the code.
"""
import ast
import inspect
import json
import pathlib
import re
import zipfile

import consumer_text
import front_door
import pytest

from larkdocio.write import client as client_mod
from larkdocio.write.apply import build_subspan_update, build_whole_paragraph_update
from larkdocio.write.client import to_write_elements

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"


def flatten(text: str) -> str:
    """Collapse every whitespace run to one space.

    **Load-bearing, not cosmetic.** The second false claim in the packaged brief shipped as
    ``"per-run bold / inline-code / color / comment\\n  metadata"`` — a flat substring grep
    for "comment metadata" reports one occurrence where there are two, which is exactly how
    the second one hid from the bug report. Every side of this guard reads flattened text, so
    reflowing a paragraph can neither hide nor reveal a claim.
    """
    return " ".join((text or "").split())


# --------------------------------------------------------------------------- #
# 1. THE KEY SET, DERIVED FROM THE CODE (so the prose cannot drift again).      #
# --------------------------------------------------------------------------- #

def emitted_style_keys() -> set:
    """``_clean_style``'s closed output key set, **derived from its own source**.

    Two collectors, because the function names its keys two ways: the boolean flags come from
    the ``_STYLE_FLAGS`` tuple, and ``text_color`` / ``background_color`` / ``link`` are
    string literals inside the body. Walking the AST for the literals (docstring excluded)
    means a **new** key added to the function widens this set automatically — the prose then
    has to name it or :func:`test_every_preservation_claim_enumerates_exactly_the_emitted_keys`
    reddens.
    """
    keys = set(client_mod._STYLE_FLAGS)
    tree = ast.parse(inspect.getsource(client_mod._clean_style).lstrip())
    fn = tree.body[0]
    docstring = ast.get_docstring(fn, clean=False)
    for node in ast.walk(fn):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value == docstring:
            continue
        if re.fullmatch(r"[a-z][a-z_]*", node.value):
            keys.add(node.value)
    return keys


def test_the_derived_key_set_matches_what_clean_style_actually_emits():
    """The derivation must not be able to over- or under-collect: probe the real function
    with every derived key truthy and assert the output key set is exactly the same set."""
    derived = emitted_style_keys()
    probe = {key: True for key in derived}
    probe["text_color"] = 5
    probe["background_color"] = 7
    probe["link"] = {"url": "https://example.test/"}
    assert set(client_mod._clean_style(probe)) == derived, (
        "the AST-derived key set disagrees with the function's real output — fix the "
        "derivation, not the assertion"
    )


def test_the_STYLE_reducer_stays_style_only():
    """The reducer's key set is still closed to **styling**, and that is deliberate: an
    anchor is not a style, and treating it as one is exactly the conflation that made the
    field invisible to this function for four releases. Keeping it out is what lets the
    derived-vs-prose enumeration check above keep meaning one thing."""
    assert "comment_ids" not in emitted_style_keys()
    assert client_mod._clean_style(
        {"bold": True, "comment_ids": ["7667000000000000001"]}) == {"bold": True}


def test_the_REBUILD_emits_the_ANCHOR_the_style_reducer_does_not():
    """The premise of the fix, pinned at the seam that owns it: the anchor leaves the rebuild
    beside the style flag in the same run, which is what the original bug report proved it
    did not do (``bold: true`` survived while the ids vanished)."""
    live = [{"text_run": {"content": "12.4%", "text_element_style": {
        "bold": True, "comment_ids": ["7667000000000000001"]}}}]
    assert to_write_elements(live) == [
        {"text_run": {"content": "12.4%", "text_element_style": {
            "bold": True, "comment_ids": ["7667000000000000001"]}}}
    ]


def test_the_anchor_carry_is_declared_in_ONE_place():
    """One helper, so "does the rebuild carry the anchor?" has a single answer to read and a
    single place to change (the reducer split is the point of the design)."""
    assert callable(client_mod._carried_comment_ids)
    assert client_mod._COMMENT_IDS_KEY == "comment_ids"


# --------------------------------------------------------------------------- #
# 2. THE DETECTORS — every claim, scoped to its own sentence.                   #
# --------------------------------------------------------------------------- #

#: Sentence boundaries. Every side of this guard is sentence-scoped rather than
#: window-scoped because the corrected prose deliberately puts adjacent statements about
#: adjacent paths; a character window would make one path's truth indistinguishable from the
#: other's.
_SENTENCE_SPLIT = re.compile(r"(?<=[.;!?])\s+")

#: The subject the claim has to be about. A sentence that mentions no comment cannot be
#: making the false claim, however many preservation verbs it carries.
_COMMENT_SUBJECT = re.compile(r"\bcomments?\b|\bcomment[_ -]?ids?\b", re.IGNORECASE)

#: The reassurance itself, in all three shapes it shipped in:
#:
#: * a **negated loss** — "comment metadata is never dropped" (``client.py``);
#: * a **positive preservation** — "survives", "is preserved", "carried through";
#: * a **displaced loss** — "never a lossy Markdown round-trip, **which would silently drop**
#:   per-run style / … / comment metadata". This third shape is the one the bug report's own
#:   grep missed twice over: it never says "preserved" at all, it blames the loss on an
#:   alternative we do not take, which reassures the reader just as effectively. Both
#:   instances in the packaged brief were this shape, so leaving it out would have let the
#:   guard pass with the brief still lying.
#:
#: **Still at full strength after the fix**, for a reason the fix itself supplies: what the
#: library controls is the payload it emits, and the round-2 probe proved the server does not
#: re-attach an anchor a patch dropped (a re-PATCH carrying ids the block no longer has is
#: refused ``1770001``). "Your comment survives an edit" is therefore a promise about
#: someone else's system; "the run that replaces the span takes its region's anchors" is a
#: statement about ours.
_REASSURANCE = re.compile(
    r"never\s+(?:silently\s+)?(?:drop|drops|dropped|lose|loses|lost)"
    r"|\b(?:not|isn't|aren't|is\s+not|are\s+not)\s+(?:dropped|lost)\b"
    r"|\bnever\s+lost\b"
    r"|\bpreserv\w*"
    r"|\bsurviv\w*"
    r"|\bretain\w*"
    r"|\bkept\b"
    r"|\bcarried\s+(?:through|over)\b"
    # the displaced-loss shape: the loss is attributed to the road not taken
    r"|(?:never|no|not)\b[^.;]{0,40}?(?:lossy\s+)?markdown\s+round-?trip"
    r"|\bwh(?:ich|at)\s+(?:would\s+)?(?:silently\s+)?(?:drop|drops|lose|loses)"
    r"|\bwould\s+(?:silently\s+)?(?:drop|lose)",
    re.IGNORECASE,
)

#: The **superseded blanket disclosure** — the honest interim text this fix replaces. It says
#: the loss is general ("both paths lose them") when it is now specific per path, so leaving
#: it in place would send a consumer to the sub-span path *believing it also loses the
#: anchor*, and would leave the whole-block refusal undiscoverable.
_OLD_BLANKET_LOSS = re.compile(
    r"inline\s+comment\s+anchors?[^.;]{0,160}?\b(?:are|is)\s+(?:dropped|lost)"
    r"|\b(?:dropped|lost)[^.;]{0,80}?inline\s+comment\s+anchors?",
    re.IGNORECASE,
)

#: The interim promise. The fix is not planned any more, so a surface still saying so is
#: telling a consumer to wait for something they already have.
_FIX_PLANNED = re.compile(r"a\s+fix\s+is\s+planned", re.IGNORECASE)

#: What every claim surface must now say, half one: the **element-level** path REFUSES. The
#: three parts are the refusal, the reason (the collapse to one run) and the subject.
_ELEMENT_LEVEL_REFUSES = re.compile(r"\brefus\w+", re.IGNORECASE)
_THE_COLLAPSE = re.compile(
    r"one\s+run|single\s+run|collaps\w+|whole[- ](?:paragraph|block|cell)", re.IGNORECASE)

#: Half two: the **sub-span** path re-emits each region's anchors onto the run it rebuilds.
#: The verbs are deliberately payload verbs (ride / re-emit / take / carry), never
#: preservation verbs — :data:`_REASSURANCE` forbids those and this must not smuggle one in.
_SUBSPAN_PATH = re.compile(r"sub-span|span\s+boundaries", re.IGNORECASE)
_SUBSPAN_CARRIES = re.compile(
    r"re-emit\w*|\brides?\b|\btakes?\b|\bcarr(?:y|ies)\b|\bride\s+with\b", re.IGNORECASE)

#: Half three: the **whole-CELL** (table) path. It shares the whole-block path's collapse and
#: gives the same answer, and it was the surviving silent drop for a while precisely *because*
#: every surface said "a whole-**block** edit" and was silent about a cell — a reader with a
#: commented table cell could read all of this and conclude their edit was safe. So a surface
#: enumerating what the rebuild keeps owes the cell path by name, not by implication.
#: The ``[*_`]*`` runs are load-bearing, not defensive noise: these surfaces are Markdown and
#: reStructuredText, where "whole-**cell**" is the same phrase to a reader and a different
#: string to a naive grep — the exact class of miss that let a claim hide behind a line wrap
#: before (see :func:`flatten`). A bolded half-word must not fall out of the guard.
_WHOLE_CELL_PATH = re.compile(
    r"whole[-\s]*[*_`]*cell|table[-\s]*[*_`]*cells?|cell\s+edit", re.IGNORECASE)


def _sentences(text: str) -> list:
    return _SENTENCE_SPLIT.split(flatten(text))


def comment_reassurance_hits(corpus: dict) -> list:
    """``[(label, sentence)]`` for every sentence that reassures a reader about comments.

    Exposed so the red-then-green probes below can drive the detector directly.
    """
    hits = []
    for label, raw in corpus.items():
        for sentence in _sentences(raw):
            if _COMMENT_SUBJECT.search(sentence) and _REASSURANCE.search(sentence):
                hits.append((label, sentence))
    return hits


def superseded_claim_hits(corpus: dict) -> list:
    """``[(label, sentence)]`` for every sentence still carrying the interim blanket text."""
    hits = []
    for label, raw in corpus.items():
        for sentence in _sentences(raw):
            if _OLD_BLANKET_LOSS.search(sentence):
                hits.append((label, sentence))
                continue
            if _FIX_PLANNED.search(sentence) and _COMMENT_SUBJECT.search(sentence):
                hits.append((label, sentence))
    return hits


def _element_level_claim(text: str) -> list:
    return [s for s in _sentences(text)
            if _COMMENT_SUBJECT.search(s) and _ELEMENT_LEVEL_REFUSES.search(s)
            and _THE_COLLAPSE.search(s)]


def _subspan_claim(text: str) -> list:
    return [s for s in _sentences(text)
            if _COMMENT_SUBJECT.search(s) and _SUBSPAN_PATH.search(s)
            and _SUBSPAN_CARRIES.search(s)]


def _cell_claim(text: str) -> list:
    return [s for s in _sentences(text)
            if _COMMENT_SUBJECT.search(s) and _WHOLE_CELL_PATH.search(s)
            and _ELEMENT_LEVEL_REFUSES.search(s)]


def test_the_detector_BITES_the_original_docstring_claim():
    """Red-then-green, surface one: the exact sentence that shipped in ``client.py``."""
    original = {
        "client.py (as shipped)": (
            "Non-text elements (mentions, equations, …) are passed through with their\n"
            "``None``-valued keys dropped (the shape the write API accepts). No lossy\n"
            "Markdown round-trip, so per-run bold / inline_code / color / comment metadata\n"
            "is never dropped.\n"
        ),
    }
    assert comment_reassurance_hits(original), (
        "the detector walked past the very sentence the reassurance guard exists to delete"
    )


def test_the_detector_BITES_the_original_brief_claim_ACROSS_ITS_LINE_WRAP():
    """Red-then-green, surface two — in the shape that hid it from the bug report: the
    packaged brief's second instance splits ``comment`` from ``metadata`` at a line wrap.

    A naive flat grep for the phrase finds nothing here, which is why :func:`flatten` is part
    of the guard rather than a convenience.
    """
    wrapped = {
        "write/README.md (as shipped, second instance)": (
            "- **Style fidelity → patch at the element level.** Runs are rebuilt via\n"
            "  `to_write_elements`, never a Markdown round-trip (which drops per-run bold /\n"
            "  inline-code / color / comment\n  metadata).\n"
        ),
    }
    assert comment_reassurance_hits(wrapped), (
        "the detector missed a line-wrapped claim — flatten() is not doing its job"
    )
    assert "comment metadata" not in "".join(wrapped.values()), (
        "the wrap no longer splits the phrase; this probe is stale"
    )


def test_the_SUPERSEDED_detector_BITES_the_interim_blanket_text_verbatim():
    """Red-then-green for the half this fix adds: the exact wording the interim disclosure
    shipped in — on both surfaces it shipped on — must be caught, or "superseded" would be a
    claim this file cannot check."""
    interim = {
        "client.py (interim)": (
            "**Inline comment anchors are dropped.** An inline comment anchored to a run "
            "this rebuild touches is lost, so a review comment on text an edit rewrites "
            "disappears from the document. It is a known limitation of the element-level "
            "rebuild and a fix is planned."
        ),
        "write/README.md (interim)": (
            "**Inline comment anchors are dropped** by both edit paths — a known\n"
            "  limitation of the element-level rebuild, and a fix is planned."
        ),
    }
    hits = {label for label, _ in superseded_claim_hits(interim)}
    assert hits == set(interim), f"the superseded-claim detector missed a surface: {hits}"


def test_the_superseded_detector_does_NOT_bite_the_PER_PATH_truth():
    """The boundary that makes the pair usable: the corrected prose says "refused" for one
    path and "rides along" for the other, in adjacent sentences, and neither detector may
    fire on it."""
    corrected = {
        "the corrected pair": (
            "Each run's clean style — bold / italic / inline_code / strikethrough / "
            "underline / text_color / background_color / link — is rebuilt element by "
            "element. Inline comment anchors ride with the run they belong to: a sub-span "
            "edit's replacement run takes its region's anchors, and a whole-paragraph edit "
            "is refused when the block carries inline comment anchors, because it collapses "
            "the block to one run."
        ),
    }
    assert not superseded_claim_hits(corrected), superseded_claim_hits(corrected)
    assert not comment_reassurance_hits(corrected), comment_reassurance_hits(corrected)
    assert _element_level_claim(corrected["the corrected pair"])
    assert _subspan_claim(corrected["the corrected pair"])


def test_the_detector_does_NOT_bite_the_UNRELATED_refusal_contract():
    """``larkdocio.write``'s "never dropped, flattened or approximated" is about **Markdown
    constructs outside the dialect**, not comments, and is true as written. A guard that
    forced that sentence to be reworded would be the tail wagging the dog."""
    unrelated = {
        "write/__init__.py's compose() contract": (
            "A construct outside the dialect is refused with the construct and its line "
            "named (``not-in-dialect``) — never dropped, flattened or approximated."
        ),
    }
    assert not comment_reassurance_hits(unrelated)
    assert not superseded_claim_hits(unrelated)


def test_the_subject_scoping_is_not_so_narrow_that_it_never_bites():
    """And the scoping must not become a loophole: rephrasing the claim without the word
    "metadata" is the same lie and is still caught."""
    rephrased = {
        "a plausible regrowth": (
            "The element-level patch is style-preserving, so a run's inline comments "
            "survive an edit."
        ),
    }
    assert comment_reassurance_hits(rephrased)


def test_a_HALF_TRUTH_does_not_satisfy_the_per_path_rule():
    """The coupling, probed: each half alone must fail its own detector, so a surface cannot
    satisfy the rule by stating the convenient half."""
    only_refuses = (
        "A whole-paragraph edit is refused when the block carries inline comment anchors, "
        "because it collapses the block to one run."
    )
    only_carries = (
        "A sub-span edit's replacement run takes the comment anchors of the region it "
        "replaces."
    )
    assert _element_level_claim(only_refuses) and not _subspan_claim(only_refuses)
    assert _subspan_claim(only_carries) and not _element_level_claim(only_carries)


def test_the_CELL_detector_BITES_the_two_path_prose_that_was_SILENT_about_a_cell():
    """Red-then-green for the third half, on the exact shape that shipped: prose naming the
    whole-**block** refusal and the sub-span carry, and saying nothing at all about a table
    cell. It satisfied both older halves, which is why the cell path's silent drop survived a
    guard that was already at full strength — and it must not satisfy this one."""
    two_path_only = (
        "Inline comment anchors ride with the run they belong to: a sub-span edit's "
        "replacement run takes its region's anchors, and a whole-paragraph edit is refused "
        "when the block carries inline comment anchors, because it collapses the block to "
        "one run."
    )
    assert _element_level_claim(two_path_only), "the older halves must still be satisfied"
    assert _subspan_claim(two_path_only), "the older halves must still be satisfied"
    assert not _cell_claim(two_path_only), (
        "the cell detector accepted prose that never mentions a cell — it would pass the "
        "pre-fix wording and guard nothing"
    )


def test_the_CELL_detector_reads_THROUGH_markdown_emphasis():
    """The phrase must be found however it is marked up, because these surfaces are Markdown
    and reStructuredText: "whole-**cell**" reads as one phrase and greps as two."""
    for phrasing in ("a whole-cell edit", "a whole-**cell** edit", "a whole-``cell`` edit"):
        sentence = (
            f"{phrasing} is refused when the cell's inner text block carries inline comment "
            f"anchors."
        )
        assert _cell_claim(sentence), phrasing


def test_the_CELL_detector_does_NOT_bite_a_cell_sentence_that_is_not_about_the_REFUSAL():
    """The must-not-bite boundary: naming a cell is not the claim. A surface may talk about
    cells (a created table's cells are unstyled, a merged cell is write-hostile) without that
    counting as "this path refuses on inline anchors"."""
    unrelated = (
        "A created table's cells are unstyled, and a merged cell refuses "
        "write-hostile-target."
    )
    assert not _cell_claim(unrelated), _cell_claim(unrelated)


def test_the_CELL_detector_ACCEPTS_the_corrected_three_path_prose():
    corrected = (
        "A whole-cell edit is refused on the same collapse when the cell's inner text block "
        "carries inline comment anchors."
    )
    assert _cell_claim(corrected)
    assert not comment_reassurance_hits({"corrected": corrected})
    assert not superseded_claim_hits({"corrected": corrected})


# --------------------------------------------------------------------------- #
# 3. THE SHIPPED-TEXT CORPUS — everything the wheel carries.                    #
# --------------------------------------------------------------------------- #

_PACKAGE_DATA_ENTRY = re.compile(
    r'^\s*(?:"?(?P<pkg>[\w.]+)"?)\s*=\s*\[(?P<files>[^\]]*)\]', re.MULTILINE
)


def packaged_markdown() -> dict:
    """``{label: path}`` for every Markdown file ``pyproject.toml`` packages into the wheel.

    Parsed out of ``[tool.setuptools.package-data]`` rather than hand-listed, so packaging a
    new doc widens this guard without anyone remembering to.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    start = text.find("[tool.setuptools.package-data]")
    assert start != -1, "pyproject.toml has no [tool.setuptools.package-data] table"
    end = text.find("\n[", start + 1)
    table = text[start:end if end != -1 else len(text)]

    out = {}
    for match in _PACKAGE_DATA_ENTRY.finditer(table):
        pkg = match.group("pkg")
        if not pkg.startswith("larkdocio"):
            continue
        subdir = pathlib.Path(*pkg.split(".")[1:])
        for name in re.findall(r'"([^"]+)"', match.group("files")):
            if not name.endswith(".md"):
                continue
            path = SRC / subdir / name
            assert path.is_file(), f"pyproject packages a missing file: {path}"
            out[str(path.relative_to(REPO_ROOT))] = path
    assert out, "no packaged Markdown found — the package-data parse broke"
    return out


def shipped_docstrings() -> dict:
    """``{label: docstring}`` for every module / class / function docstring under ``src/``.

    Wider than the consumer corpus on purpose: a *module* docstring has no public accessor,
    but it still ships in the wheel and a reader opening ``client.py`` reads it first — which
    is precisely where a second incomplete enumeration was sitting.
    """
    out = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            doc = ast.get_docstring(node, clean=False)
            if not doc:
                continue
            name = getattr(node, "name", "<module>")
            line = getattr(node, "lineno", 1)
            out[f"{rel}:{line} {name}.__doc__"] = doc
    return out


def shipped_text_surfaces() -> dict:
    """``{label: text}`` — every text surface the wheel carries, three passes wide."""
    out = {}
    out.update(shipped_docstrings())
    for label, path in packaged_markdown().items():
        out[label] = path.read_text(encoding="utf-8")
    out.update(consumer_text.consumer_corpus())
    return out


def test_the_corpus_covers_all_three_passes():
    """The guard is only as wide as its corpus, so pin that each pass is non-empty and
    present — a dropped pass would silently narrow every assertion below to nothing."""
    corpus = shipped_text_surfaces()
    for label in (
        "src/larkdocio/write/README.md",
        "src/larkdocio/blocks/BLOCK_TYPES.md",
        "src/larkdocio/GUIDE.md",
    ):
        assert label in corpus, f"{label} is packaged but not in the guard's corpus"
    assert set(shipped_docstrings()) <= set(corpus)
    assert set(consumer_text.consumer_corpus()) <= set(corpus)
    assert any("client.py" in label for label in shipped_docstrings())


# --------------------------------------------------------------------------- #
# 4. THE NEGATIVE HALF — neither the reassurance NOR the superseded blanket      #
#    survives anywhere in the wheel.                                            #
# --------------------------------------------------------------------------- #

def test_no_shipped_surface_reassures_a_reader_about_comment_survival():
    hits = [f"{label}: {sentence}" for label, sentence in
            comment_reassurance_hits(shipped_text_surfaces())]
    assert not hits, (
        "a surface that ships in the wheel tells a reader that a comment anchor survives an "
        "edit. That is a promise about Lark's behaviour, not ours: the round-2 probe proved "
        "the server does not re-attach an anchor a patch dropped, and it validates the ids a "
        "patch sends against the block's live anchors. State what the path DOES with the "
        "payload instead.\n  " + "\n  ".join(hits)
    )


def test_no_shipped_surface_still_carries_the_SUPERSEDED_blanket_disclosure():
    hits = [f"{label}: {sentence}" for label, sentence in
            superseded_claim_hits(shipped_text_surfaces())]
    assert not hits, (
        "a surface still says inline comment anchors are dropped (or that a fix is planned). "
        "Neither is true any more, and the blanket is worse than useless per path: it sends a "
        "consumer to the sub-span edit believing it loses the anchor too, and hides the "
        "whole-block refusal that would tell them otherwise.\n  " + "\n  ".join(hits)
    )


# --------------------------------------------------------------------------- #
# 5. THE POSITIVE HALF — every surface that says what SURVIVES says what each    #
#    PATH does. Coupled on purpose: the enumeration is the reassuring half, so   #
#    it is the half that owes both truths.                                       #
# --------------------------------------------------------------------------- #

#: A slash-separated enumeration of style fields — the shape every surface states the
#: preserved set in. Three tokens is the floor, not four: the apply engine's module docstring
#: shipped the shortest wrong list of all, ``(bold / color / link)``.
_SLASH_LIST = re.compile(r"[A-Za-z_][A-Za-z_-]*(?:\s*/\s*[A-Za-z_][A-Za-z_-]*){2,}")


def style_enumerations(text: str) -> list:
    """Every style-field slash list in ``text``, each as a list of tokens.

    Selected by containing ``bold`` so an unrelated slash list ("insert / edit / delete") is
    never mistaken for one.
    """
    found = []
    for match in _SLASH_LIST.finditer(flatten(text)):
        tokens = [token.strip() for token in match.group(0).split("/")]
        if "bold" in tokens:
            found.append(tokens)
    return found


#: The scope predicate. ``_clean_style``'s key set describes the **docx run rebuild** and
#: nothing else, so a Sheets surface enumerating its own ``bold / italic / fill / numFmt``
#: set is a different (and correct) closed set — comparing it against this one would force
#: true prose to be reworded to satisfy a guard. A surface is in scope when it lives on the
#: docx writeback surface or names the rebuild function itself.
_REBUILD_NAME = re.compile(r"to_write_elements")


def _lives_on_the_docx_write_surface(label: str) -> bool:
    """The LABEL half of the scope: the whole file is about the writeback surface."""
    return "larkdocio/write/" in label or label.startswith("larkdocio.write")


def _describes_the_docx_rebuild(label: str, text: str) -> bool:
    return _lives_on_the_docx_write_surface(label) or bool(_REBUILD_NAME.search(text))


#: **LD-568 — the scope is the CLAIM, not the file.** The label half of the predicate above
#: excluded the Sheets style set by *filename*, which works only while one file describes one
#: surface. The packaged guide describes them all: it documents the Sheets fidelity leg's own
#: correct ``bold / italic / fill / numFmt`` sets **and** — since the docx absence register is
#: projected into it — names ``to_write_elements``. Under a whole-file scope that one mention
#: made every Sheets enumeration in a 400 KB document owe the docx key set, which is exactly
#: the rewording-true-prose-to-satisfy-a-guard failure the comment above forbids.
#:
#: **The conclusion moved, not the reason.** A surface that is *about* the writeback path
#: (the label half) still owes the derived key set for every enumeration it carries — nothing
#: there is relaxed. A surface that qualifies only by NAMING the rebuild owes it for the
#: enumerations in the **paragraph that names it**, which is the unit a claim is actually made
#: in. ``test_the_paragraph_scope_still_BITES_on_a_wrong_list_beside_the_rebuild`` pins that
#: the narrowing did not defang the guard.
def _claim_text(label: str, text: str) -> str:
    if _lives_on_the_docx_write_surface(label):
        return text
    return "\n\n".join(
        para for para in text.split("\n\n") if _REBUILD_NAME.search(para))


def preservation_claim_surfaces() -> dict:
    """``{label: claim text}`` — every shipped surface that enumerates what the docx rebuild
    keeps, reduced to the text in which it makes that claim.

    Discovered by *reading the text*, not hand-listed: any shipped surface that grows a
    ``bold / …`` enumeration on the writeback surface joins this set automatically and
    immediately owes both the derived key set and both halves of the per-path truth.
    """
    found = {}
    for label, text in shipped_text_surfaces().items():
        if not _describes_the_docx_rebuild(label, text):
            continue
        claim = _claim_text(label, text)
        if style_enumerations(claim):
            found[label] = claim
    return found


def test_the_scope_predicate_excludes_the_SHEETS_style_set():
    """A must-not-bite: the Sheets fidelity leg enumerates ``bold / italic / fill / numFmt``,
    a correct and unrelated closed set. It must stay out of this guard entirely."""
    labels = " || ".join(preservation_claim_surfaces())
    assert "sheets" not in labels, (
        f"a Sheets surface leaked into the docx-rebuild claim set: {labels}"
    )


def test_at_least_the_known_preservation_surfaces_are_found():
    """Pin the discovery so a reworded enumeration cannot quietly empty this set: the
    rebuild's own docstring, both apply-path builders, and the packaged brief."""
    labels = " || ".join(preservation_claim_surfaces())
    for expected in (
        "to_write_elements",
        "build_whole_paragraph_update",
        "build_subspan_update",
        "write/README.md",
    ):
        assert expected in labels, (
            f"no preservation-claim surface found for {expected!r} — either the enumeration "
            f"was reworded out of shape or the discovery regex broke"
        )


def test_the_paragraph_scope_still_BITES_on_a_wrong_list_beside_the_rebuild():
    """LD-568's narrowing must not defang the guard. A document that is not *about* the
    writeback surface but states the preserved set **in the paragraph that names the
    rebuild** is still held to the derived key set — which is the shape of the original
    defect (the apply engine's ``bold / color / link``). And the Sheets set two paragraphs
    away is still out of scope, which is the whole point of the narrowing."""
    doc = (
        "Reading a sheet's own fidelity leg gives you bold / italic / fill / numFmt.\n\n"
        "A whole-block edit rebuilds the runs through to_write_elements, keeping "
        "bold / color / link.\n\n"
        "Unrelated prose with no enumeration at all."
    )
    claim = _claim_text("larkdocio/GUIDE.md", doc)
    assert "to_write_elements" in claim and "numFmt" not in claim
    named = [{t.replace("-", "_") for t in tokens} for tokens in style_enumerations(claim)]
    assert named == [{"bold", "color", "link"}]
    assert named[0] != emitted_style_keys(), "the wrong list must still disagree"

    # And the label half is untouched: a write-surface file keeps whole-file scope.
    assert _claim_text("src/larkdocio/write/README.md", doc) == doc


def test_every_preservation_claim_enumerates_exactly_the_emitted_keys():
    """The anti-drift half of the enumeration fix: the shipped list is compared against
    ``_clean_style``'s **derived** key set in both directions, so neither a missing field
    (the original ``strikethrough`` / ``underline`` omission) nor an invented one can ship.

    Unchanged by the anchor fix, because the reducer stayed style-only: ``comment_ids`` is
    **not** a member of this list and must not be smuggled into one — a style enumeration
    that named it would be claiming an anchor is a style, which is the original conflation."""
    expected = emitted_style_keys()
    wrong = []
    for label, text in preservation_claim_surfaces().items():
        for tokens in style_enumerations(text):
            named = {token.replace("-", "_") for token in tokens}
            if named != expected:
                wrong.append(
                    f"{label}: names {sorted(named)}, "
                    f"missing {sorted(expected - named)}, "
                    f"invented {sorted(named - expected)}"
                )
    assert not wrong, (
        "a shipped style enumeration disagrees with _clean_style's actual key set "
        f"({sorted(expected)}):\n  " + "\n  ".join(wrong)
    )


def test_every_preservation_claim_surface_states_the_ELEMENT_LEVEL_REFUSAL():
    missing = [label for label, text in preservation_claim_surfaces().items()
               if not _element_level_claim(text)]
    assert not missing, (
        "these surfaces tell a reader what the rebuild keeps but not that a whole-block edit "
        "REFUSES when the block carries inline comment anchors — the reassuring half without "
        f"the half a consumer has to plan around: {missing}"
    )


def test_every_preservation_claim_surface_states_the_SUB_SPAN_CARRY():
    missing = [label for label, text in preservation_claim_surfaces().items()
               if not _subspan_claim(text)]
    assert not missing, (
        "these surfaces state the refusal but not that the sub-span path re-emits each run's "
        "anchors — a refusal with no recovery is a dead end, and the recovery IS the other "
        f"path: {missing}"
    )


def test_every_preservation_claim_surface_states_the_WHOLE_CELL_REFUSAL():
    """The third path, added because being silent about it is exactly how its silent drop
    outlived a guard that already demanded both other halves. "A whole-**block** edit is
    refused" is not a statement about a table cell, and a reader with a commented cell would
    reasonably read the two-path prose as clearing them to edit it."""
    missing = [label for label, text in preservation_claim_surfaces().items()
               if not _cell_claim(text)]
    assert not missing, (
        "these surfaces state the whole-BLOCK refusal and the sub-span carry but say nothing "
        "about a whole-CELL (table) edit, which rides the same collapse and refuses the same "
        f"way — the omission a reader would read as permission: {missing}"
    )


def test_the_two_surfaces_the_bug_named_are_covered_by_name():
    """Belt and braces on the class guard: the two surfaces the bug report named must carry
    every half, whatever the discovery regex does."""
    for label, text in (
        ("to_write_elements.__doc__", to_write_elements.__doc__),
        ("writer_brief() — packaged write/README.md", consumer_text.shipped_docs()
         ["writer_brief()"]),
    ):
        assert _element_level_claim(text), f"{label} does not state the refusal"
        assert _subspan_claim(text), f"{label} does not state the sub-span carry"
        assert _cell_claim(text), f"{label} does not state the whole-cell refusal"


# --------------------------------------------------------------------------- #
# 6. THE NEW PROSE IS DIALECT-FREE (these are consumer-facing shipped strings). #
# --------------------------------------------------------------------------- #

def test_the_per_path_prose_is_dialect_free():
    """Unlike this repo's ``dev/`` docs, a shipped surface may not carry the internal
    dialect: no issue id, no requirement id, no criterion number, no tranche label, no role
    attribution. The claim sentences are checked on their own so a pre-existing hit
    elsewhere in a long document cannot mask a new one."""
    offenders = []
    for label, text in preservation_claim_surfaces().items():
        for sentence in _element_level_claim(text) + _subspan_claim(text) + _cell_claim(text):
            hits = consumer_text.dialect_hits(sentence)
            if hits:
                offenders.append(f"{label}: {hits} in {sentence!r}")
    assert not offenders, (
        "the per-path prose carries internal dialect on a shipped surface:\n  "
        + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# 7. THE BEHAVIOUR PIN — against a REAL captured payload, all three geometries.  #
#    Inverted by the fix: the element-level body is still byte-identical, the     #
#    sub-span body now carries the ids.                                          #
# --------------------------------------------------------------------------- #

_CAPTURE = REPO_ROOT / "tests" / "captures" / "comments-probe-captures" / "05-edit-path-comment-ids.json"

#: The mutations the capture was taken with, read back off its own recorded bodies.
_WHOLE_PARAGRAPH_REPLACEMENT = "REPLACED WHOLE PARAGRAPH"
_SPAN, _SPAN_REPLACEMENT = "12.4%", "15.0%"


def _geometries() -> dict:
    payload = json.loads(_CAPTURE.read_text(encoding="utf-8"))
    legs = payload["leg1"]
    assert set(legs) == {"inside", "spanning", "neighbour"}, (
        "the capture no longer holds all three comment geometries"
    )
    return legs


@pytest.mark.parametrize("geometry", ["inside", "spanning", "neighbour"])
def test_the_ELEMENT_LEVEL_body_is_still_byte_identical_to_the_capture(geometry):
    """The rejected leading-run variant, structurally excluded from the common path: the
    whole-paragraph body for a real anchored payload is exactly the body that shipped before
    the fix — no anchor rides the collapsed run, so no reviewer's comment is relocated onto
    the whole new paragraph."""
    leg = _geometries()[geometry]
    live = leg["live_elements_in"]
    assert any("comment_ids" in (e["text_run"].get("text_element_style") or {})
               for e in live), "this geometry's input carries no comment_ids at all"

    body = build_whole_paragraph_update(live, _WHOLE_PARAGRAPH_REPLACEMENT)
    assert body == leg["element_level_body"]
    assert "comment_ids" not in json.dumps(body)


@pytest.mark.parametrize("geometry", ["inside", "spanning", "neighbour"])
def test_the_SUB_SPAN_body_now_carries_the_ids_the_capture_recorded_losing(geometry):
    """The other half of the same real-payload pin. The capture recorded
    ``subspan_emits_comment_ids: false`` for all three geometries — that was the defect, and
    it must now be true for each of them, with the ids landing on the runs whose text is
    inside the anchored region (which run, exactly, is pinned per geometry in
    ``tests/test_comment_anchor_preservation.py``)."""
    leg = _geometries()[geometry]
    assert leg["subspan_emits_comment_ids"] is False, (
        "the capture no longer records the loss this test exists to invert"
    )
    body = build_subspan_update(leg["live_elements_in"], _SPAN, _SPAN_REPLACEMENT)
    assert "comment_ids" in json.dumps(body), body


def test_the_targeted_nature_of_the_loss_is_inverted_at_the_function_it_came_from():
    """The bug report's one-line demonstration, now green in the other direction: the style
    flag and the anchor leave the rebuild together in the same run."""
    live = [{"text_run": {"content": "12.4%", "text_element_style": {
        "bold": True, "comment_ids": ["7667000000000000001"]}}}]
    assert to_write_elements(live) == [
        {"text_run": {"content": "12.4%", "text_element_style": {
            "bold": True, "comment_ids": ["7667000000000000001"]}}}
    ]


#: The READ-side capture sites, named one by one. The reader turned ``comment_ids`` from a
#: globally-dropped field into a consumed-into-model / dropped-at-render one at both
#: granularities — the block-level list is stamped in the parser's node primitive and the
#: word-level list is read off ``text_element_style`` into ``StyledText``. Naming the files
#: (rather than dropping the census) is what keeps this guard biting: a reference in ANY
#: unlisted shipped file still reddens, and so does a named site that stops referencing it.
#: The typed comments READ surface JOINS on the captured anchors, so it necessarily names the
#: field — the read client passes the ids to the batch-fetch endpoint, and the read module
#: walks the node tree collecting them. The two **discovery** surfaces (the shipped guide and
#: the capability registry) describe that capture to a consumer, so they name it too.
_READ_CAPTURE_SITES = {
    "src/larkdocio/blocks/text.py",
    "src/larkdocio/model/nodes.py",
    "src/larkdocio/read/parser.py",
    "src/larkdocio/comments/client.py",
    "src/larkdocio/comments/read.py",
    "src/larkdocio/GUIDE.md",
    # LD-244 turned ``capabilities.py`` into a package; the registry's comment-ids claim
    # lives in the level model. The census stays EXACT (naming the one file, not the
    # directory) — that is the guard's whole point in both directions.
    "src/larkdocio/capabilities/_levels.py",
}

#: The WRITE-side sites, named the same way — the half that used to be a blanket ban. The ban
#: existed because the behaviour fix was parked and this file's disclosure prose depended on
#: the field being absent from the write surface; the fix is here, so the rule the ban was
#: standing in for is now an exact census of the three seams that carry the anchor:
#:
#: * ``client.py`` — the rebuild that re-emits a run's ids (``_carried_comment_ids``);
#: * ``apply.py`` — the collapsed-run guard that strips them for the element-level body, and
#:   the sub-span refusal detail that names them;
#: * ``resolve.py`` — the plan-time word-level scan that drives the refusal;
#: * ``preview.py`` — LD-172: the plan-time DISCLOSURE on the one path that proceeds. It reads
#:   the same ``_inline_comment_ids`` reduction ``resolve.py`` refuses on (deliberately the same
#:   function, so the note and the refusal cannot disagree about what counts as an anchor) and
#:   puts the ids in a ``comment-anchors-present-on-target`` ``preview_note``, so a human
#:   approving a sub-span edit into commented text can see that reviewers are involved. It emits
#:   no write body and changes no anchor: a **disclosure** seam, not a fourth carry.
#:
#: A **fifth** file naming the field on the write surface reddens here, which is the point:
#: the field's write-side footprint is a named census, not "wherever it turns out to be needed".
_WRITE_SURFACE_SITES = {
    "src/larkdocio/write/client.py",
    "src/larkdocio/write/apply.py",
    "src/larkdocio/write/resolve.py",
    "src/larkdocio/write/preview.py",
}

_WRITE_SURFACE = SRC / "write"


def _comment_ids_census():
    """``{repo-relative path: [line numbers]}`` for every shipped file naming the field."""
    census = {}
    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md", ".json"}:
            continue
        lines = [i for i, line in
                 enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if "comment_ids" in line]
        if lines:
            census[str(path.relative_to(REPO_ROOT))] = lines
    return census


def test_comment_ids_is_referenced_ONLY_at_the_NAMED_capture_and_carry_sites():
    """The bug report's one-line reproduction (``grep -rn comment_ids src/`` → nothing), kept
    as an **exact census** rather than a blanket, in both directions."""
    census = _comment_ids_census()
    allowed = _READ_CAPTURE_SITES | _WRITE_SURFACE_SITES
    unexpected = sorted(set(census) - allowed)
    assert not unexpected, (
        "comment_ids is referenced in a shipped file that is neither a read-side capture "
        f"site nor one of the three write-side carry seams: { {k: census[k] for k in unexpected} }"
    )
    missing = sorted(allowed - set(census))
    assert not missing, (
        f"these files are allowed to reference comment_ids but no longer do — a capture or "
        f"carry seam was removed or moved, so this census is stale: {missing}"
    )


def test_the_WRITE_SURFACE_census_is_exactly_the_three_carry_seams():
    """The load-bearing half, re-pointed rather than dropped: the write surface names the
    field at exactly three seams. A new one is a design change and must be argued for here —
    in particular, a *fourth* site would most likely be a caller re-implementing the carry
    instead of going through the rebuild."""
    hits = {path for path in _comment_ids_census()
            if path.startswith(str(_WRITE_SURFACE.relative_to(REPO_ROOT)))}
    assert hits == _WRITE_SURFACE_SITES, (
        f"the writeback surface's comment_ids footprint changed: {sorted(hits)} vs the "
        f"declared {sorted(_WRITE_SURFACE_SITES)}"
    )


# --------------------------------------------------------------------------- #
# 8. THE STRINGS SHIP — both corrected surfaces are confirmed INSIDE the wheel.  #
# --------------------------------------------------------------------------- #

def test_the_writer_brief_is_declared_as_package_data():
    """The fast, always-on half: the mechanism that lands the corrected brief in the wheel."""
    assert "src/larkdocio/write/README.md" in packaged_markdown()


def test_both_corrected_surfaces_are_inside_the_built_wheel():
    """The binding proof (the ``GUIDE.md`` in-wheel precedent): re-check the built wheel's
    ``RECORD`` and read the corrected sentences **out of the archive** — the docstring inside
    ``larkdocio/write/client.py`` and the packaged ``larkdocio/write/README.md``.

    LD-221: the wheel comes from ``front_door.packaging_artifacts()`` (LD-215's session-cached
    seam) rather than a build of its own, which also retires the two ``pytest.skip`` paths —
    LD-215's arming posture applies to this guard for the same reason it applies to that one.
    """
    _, wheel = front_door.packaging_artifacts()
    with zipfile.ZipFile(wheel) as archive:
        record = next((n for n in archive.namelist() if n.endswith("/RECORD")), None)
        assert record, "the built wheel has no RECORD"
        record_text = archive.read(record).decode("utf-8")
        for member in ("larkdocio/write/client.py", "larkdocio/write/README.md"):
            assert member in record_text, f"{member} is not in the wheel RECORD"
        in_wheel = {
            member: flatten(archive.read(member).decode("utf-8"))
            for member in ("larkdocio/write/client.py", "larkdocio/write/README.md")
        }

    for member, text in in_wheel.items():
        assert _element_level_claim(text), f"{member} ships without the refusal half"
        assert _subspan_claim(text), f"{member} ships without the sub-span half"
        assert not comment_reassurance_hits({member: text}), (
            f"{member} ships with the reassurance in it"
        )
        assert not superseded_claim_hits({member: text}), (
            f"{member} ships with the superseded blanket disclosure in it"
        )
