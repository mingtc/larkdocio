"""The "larkdocio has no Base surface" CLAIM is gone from shipped text — claim-level, not
phrase-level (LD-279).

Why this file exists
--------------------
Two earlier retractions retired the *write-era* sentences that denied the Base surface, and
each was guarded by a **phrase literal** (``"no Base surface of any kind"``). The reader-era
sentences predate that list and are worded differently, so four shipped texts went on denying
five shipped surfaces while the suite stayed green:

* the ``download`` refusal a consumer meets first ("has no Base surface at all — no read, no
  write, no client"),
* the wheel ``METADATA`` body's opening paragraph ("The fifth, **base**, is **read-only** … It
  changes nothing"),
* ``validate_download_url``'s docstring and the validator's own refusal message ("recognised as
  a type only"),
* the shipped guide's ``domain=`` section.

A phrase-literal guard cannot catch a paraphrase. So this guard holds the **claim** absent —
a small family of patterns, each red-proved against the real surviving sentence it was written
for — over the whole shipped corpus, and it pins the positive replacement too: the refusal now
**routes** a Base URL at ``larkdocio.base.read_base_markdown`` instead of denying it exists.

The read-only half is not a grep
--------------------------------
"Base is read-only" cannot be caught by a text pattern without also catching the true sentence
"the command line stays read-only and Base-free". So that half is checked **structurally**
instead, against ``capabilities()`` itself: a surface the registry reports with
``mode == "write"`` may not be described as read-only in the README's opening paragraph. A
sixth write surface tomorrow enrols itself.

Scope
-----
The corpus pass reuses ``consumer_text.consumer_corpus()`` — every text surface a consumer
reaches through the wheel — so nothing new is excluded here. The raw-source pass adds the
bytes a corpus pass cannot see (``#`` comments, private docstrings, packaged Markdown with no
accessor). ``CHANGELOG.md`` is out of the raw pass on the ``test_front_door_truth.py``
precedent: it is a **historical record** of what was true at the time, and one of its entries
*quotes the retracted claim in order to retract it* — rewriting that would be the actual
falsification. The exclusion is kept honest by
``test_the_changelog_exclusion_is_live_not_dead_weight`` below.
"""
import re

import pytest

import private_tree  # noqa: E402  (LD-691)

from consumer_text import consumer_corpus

import larkdocio

from guard_kit import REPO_ROOT


SRC = REPO_ROOT / "src" / "larkdocio"

#: The claim family: every way the shipped text has ever asserted that no Base surface exists.
#: Each entry is ``(name, pattern)`` and each is red-proved below against the real sentence it
#: was written for — a pattern nothing ever said is dead weight, not a guard.
CLAIM_PATTERNS = (
    ("no-base-<thing>", re.compile(r"\bno\s+Base\s+(?:surface|client|reader|read|write)\b", re.I)),
    ("has-no-base", re.compile(r"\bhas\s+no\s+Base\b", re.I)),
    ("type-only", re.compile(r"\b(?:recognised|recognized)\s+as\s+a\s+type\s+only", re.I)),
    ("nothing-more", re.compile(r"\b(?:recognised|recognized)\s+type\s+and\s+nothing\s+more", re.I)),
)

#: The four sentences that actually shipped in 1.26.0, verbatim. The detector must bite on
#: every one of them or it is not a claim-level guard.
SURVIVING_SENTENCES = {
    "download.py refusal": (
        "that is a BASE url. larkdocio recognises the url type and has no Base surface at "
        "all — no read, no write, no client — so there is nothing here to download it with."
    ),
    "url.py docstring": (
        "``base`` is a recognised type and nothing more — larkdocio has no Base surface."
    ),
    "url.py refusal message": "a base url is recognised as a type only.",
    "GUIDE.md": (
        "a `base` type is recognised as a type only — larkdocio has no Base surface."
    ),
    "the phrase the earlier literal guards pinned": (
        "larkdocio has no Base surface of any kind"
    ),
}


def claim_hits(text):
    """Every "there is no Base surface" assertion in ``text`` as ``[(name, matched)]``."""
    if not isinstance(text, str):
        return []
    return [
        (name, match.group(0))
        for name, pattern in CLAIM_PATTERNS
        for match in pattern.finditer(text)
    ]


def _swept_files():
    """Every shipped source/doc byte, minus the historical log (see the module docstring)."""
    paths = [
        path
        for pattern in ("*.py", "*.md")
        for path in SRC.rglob(pattern)
        if path.name != "CHANGELOG.md"
    ]
    paths += [REPO_ROOT / name for name in ("README.md", "RELEASE_NOTES.md", "BASE.md")]
    return sorted(paths)


# --------------------------------------------------------------------------- #
# The detector itself — red-proved, so it cannot pass by being blind            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("label", sorted(SURVIVING_SENTENCES))
def test_the_detector_bites_on_every_sentence_that_actually_shipped(label):
    assert claim_hits(SURVIVING_SENTENCES[label]), (
        f"the guard is blind to {label!r} — the exact wording that shipped in 1.26.0"
    )


@pytest.mark.parametrize("legitimate", [
    "The command line is read-only: it downloads and converts, and stays Base-free.",
    "A Base URL is read through the Base surface: larkdocio.base.read_base_markdown(url).",
    "`base` is one of the recognised url types; the type says which surface reads it.",
    "There is no Sheets surface flag on this command.",
])
def test_the_detector_does_not_bite_on_true_sentences(legitimate):
    assert claim_hits(legitimate) == [], claim_hits(legitimate)


# --------------------------------------------------------------------------- #
# The claim is GONE — corpus pass and raw-source pass                          #
# --------------------------------------------------------------------------- #

def test_no_consumer_reaching_text_denies_the_base_surface():
    offenders = {
        label: hits for label, text in consumer_corpus().items() if (hits := claim_hits(text))
    }
    assert not offenders, (
        f"shipped text still denies a surface that ships: {offenders}"
    )


def test_no_shipped_source_byte_denies_the_base_surface():
    offenders = {
        str(path.relative_to(REPO_ROOT)): hits
        for path in _swept_files()
        if (hits := claim_hits(path.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        f"the claim survives outside the corpus pass (a comment, a private docstring, or a "
        f"packaged doc with no accessor): {offenders}"
    )


@private_tree.internal_log
def test_the_changelog_exclusion_is_live_not_dead_weight():
    """The historical log really does carry the retracted wording — it quotes the claim in order to
    record its retraction. That is why it is excluded, and this is the check that stops the
    exclusion from quietly becoming a hole.

    **LD-540 moved the liveness claim to the AUTHORING SOURCE, and kept it unconditional there.**
    The wheel now carries a recent-N window of the changelog, so whether the PACKAGED copy quotes
    the retraction depends on which release disclosed it — a property a release can move with
    nothing wrong. The exclusion's justification is permanent and belongs to the document, and the
    root copy keeps every retraction quote forever, so that is where the claim is asserted in full.
    The packaged copy goes through ``notes_claim_copies``, which reddens if the quote is missing
    there while its section is still INSIDE the window — so the exclusion cannot become a hole
    without something reddening. **What this used to prove and no longer can:** that the wheel's own
    copy quotes the retraction at every moment."""
    from test_shipped_notes import notes_claim_copies

    root = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    hits = claim_hits(root)
    assert hits, (
        "CHANGELOG.md no longer quotes the retracted claim, so excluding it from the sweep now "
        "hides nothing and should be dropped"
    )
    notes_claim_copies("CHANGELOG.md", hits[0][1])


# --------------------------------------------------------------------------- #
# The positive replacement: route, do not deny                                 #
# --------------------------------------------------------------------------- #

def test_the_download_refusal_routes_a_base_url_at_the_base_reader():
    from larkdocio.read.download import _NON_DOCUMENT_URL_MESSAGES

    message = _NON_DOCUMENT_URL_MESSAGES["base"]
    assert claim_hits(message) == [], claim_hits(message)
    assert "read_base_markdown" in message, (
        "the refusal must name the call that DOES read a Base, the way the sheets refusal "
        "names the Sheets reader — a consumer meets this message before any doc"
    )
    assert "larkdocio.base" in message


def test_the_url_docstring_and_refusal_name_the_surface_that_reads_a_base():
    from larkdocio.common import url as url_module

    source = (SRC / "common" / "url.py").read_text(encoding="utf-8")
    assert claim_hits(source) == [], claim_hits(source)
    assert re.search(r"base.*surface", url_module.validate_download_url.__doc__, re.I)
    # …and the discriminator is untouched: this is a text retraction, not a behavior change.
    assert url_module.URL_TYPE_SURFACES["base"] == "base"


def test_the_shipped_guide_routes_a_base_url_too():
    guide = larkdocio.guide(full=True)
    assert claim_hits(guide) == [], claim_hits(guide)
    assert "read_base_markdown" in guide


# --------------------------------------------------------------------------- #
# The read-only half — structural, derived from capabilities()                  #
# --------------------------------------------------------------------------- #

def readme_opening():
    """The README's opening prose — everything above the first ``##`` heading."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    return text[: text.index("\n## ")]


def write_mode_families():
    """``{family}`` for every surface ``capabilities()`` reports as writing.

    Derived, so a sixth write surface enrols itself instead of waiting for someone to widen a
    literal list — the same rule the Summary guard runs on.
    """
    return {
        surface_id.split("-")[0]
        for surface_id, surface in larkdocio.capabilities(full=True)["surfaces"].items()
        if surface.get("mode") == "write"
    }


def read_only_claims(text, families):
    """``[(family, sentence)]`` for every sentence calling a WRITING family read-only."""
    # Emphasis markers are stripped first, or `read-only.**` reads as mid-sentence and two
    # sentences fuse into one — which is how a true sentence would look like a false claim.
    flat = re.sub(r"[*_`]+", "", " ".join(text.split()))
    claims = []
    for sentence in re.split(r"(?<=[.:])\s+", flat):
        if "read-only" not in sentence.lower():
            continue
        for family in sorted(families):
            if re.search(rf"\b{re.escape(family)}\b", sentence, re.I):
                claims.append((family, sentence))
    return claims


def test_the_registry_reports_base_as_a_writing_surface():
    """The premise the check below rests on, asserted rather than assumed."""
    assert "base" in write_mode_families()


def test_the_readme_opening_never_calls_a_WRITING_surface_read_only():
    claims = read_only_claims(readme_opening(), write_mode_families())
    assert not claims, (
        f"the wheel's METADATA body describes a surface capabilities() reports as writable "
        f"as read-only: {claims}"
    )


def test_the_read_only_check_bites_on_the_paragraph_that_actually_shipped():
    shipped = (
        "Five surfaces ship; four read **and** write: the **reader** … The fifth, **base**, "
        "is\n**read-only**: a Base (bitable) → titled Markdown tables. It changes nothing."
    )
    assert read_only_claims(shipped, write_mode_families()), (
        "the check would not have caught the paragraph it was written for"
    )


def test_the_read_only_check_leaves_the_true_cli_sentence_alone():
    true_sentence = (
        "**The command line is read-only.** It downloads and converts; it never writes to a "
        "Lark document, and it has no Base flag."
    )
    assert read_only_claims(true_sentence, write_mode_families()) == []
