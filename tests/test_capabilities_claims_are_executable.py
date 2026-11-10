"""LD-646 — the registry held against ITSELF, by execution.

The defect this file exists for: `capabilities(full=True)['docs'][...]['section_addressing']`
told every packaged document's reader that *"each `###` (and `##`) heading is individually
retrievable"*. Two of the five — `release_notes()` and `changelog()` — are indexed at level 2
only, so the `###` half raised `ValueError` on every call. It was a **generated** false claim
inside the artifact this project tells consumers to trust over prose, and no guard could see
it: the drift guards hold prose against the registry, and nothing held the registry against
its own accessors.

**The check, stated once:** a claim the registry makes about its own accessors must be
EXECUTABLE. So these tests do not read the generator — they read the SHIPPED SENTENCE, parse
the levels out of it the way a consumer would, and then make the calls it promises. A
generator that starts lying again is caught even if it lies consistently with itself.

Everything here is driven off the LIVE document set — `capabilities(full=True)['docs']` and
each document's own headings. There is no hard-coded list of five documents and no hard-coded
level anywhere in this file: a hard-coded list would be the same defect one layer up.
"""
import re

import pytest

import larkdocio
from larkdocio.guide import _atx_headings, _packaged  # noqa: F401  (the raw heading scan)


#: Every ATX mark the sentence spells inside backticks — `##`, `###`. This is the parse a
#: consumer performs when they read the claim, done mechanically.
_MARK = re.compile(r"`(#{1,6})`")


def _docs():
    return larkdocio.capabilities(full=True)["docs"]


def _document_rows():
    """``(label, accessor_name, row)`` for every docs row that MAKES an addressing claim."""
    return [
        (label, label[:-2], row)
        for label, row in _docs().items()
        if row.get("section_addressing") is not None
    ]


def _labels():
    return [label for label, _name, _row in _document_rows()]


def _advertised_levels(row) -> set:
    """The heading levels the SHIPPED SENTENCE advertises — parsed, never taken from the code."""
    return {len(mark) for mark in _MARK.findall(row["section_addressing"])}


def _accessor(name):
    return getattr(larkdocio, name)


def _document_text(name) -> str:
    """The packaged bytes the accessor itself reads, via its own `full=True` door."""
    return _accessor(name)(full=True) if name == "guide" else _accessor(name)()


def test_the_live_document_set_is_what_drives_this_file():
    """A census, so a document silently dropping out of the registry cannot make this file
    vacuously green. The number is DERIVED from the payload, never typed."""
    labels = _labels()
    assert labels, "no docs row makes a section_addressing claim — the corpus went empty"
    assert set(labels) <= set(_docs())
    assert len(labels) == len([r for r in _docs().values() if r.get("sections")])


# --------------------------------------------------------------------------- #
# AC2 — every level the claim advertises is retrievable, by heading AND slug    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("label", _labels())
def test_every_advertised_level_really_retrieves_a_section(label):
    row = _docs()[label]
    name = label[:-2]
    accessor = _accessor(name)
    advertised = _advertised_levels(row)
    assert advertised, f"{label}: the sentence advertises no level at all"

    for level in sorted(advertised):
        candidates = [r for r in row["sections"] if r["level"] == level]
        assert candidates, (
            f"{label}: the claim advertises `{'#' * level}` but the document's own index has "
            f"no section at that level — the claim over-reaches"
        )
        first = candidates[0]
        by_heading = accessor(section=first["heading"])
        by_slug = accessor(section=first["slug"])
        assert by_heading == by_slug
        assert first["heading"] in by_heading


@pytest.mark.parametrize("label", _labels())
def test_a_level_the_claim_does_not_advertise_is_REFUSED(label):
    """The other half: the sentence's silence is load-bearing too. For every heading level the
    document really carries and the claim does NOT advertise, naming such a heading raises."""
    row = _docs()[label]
    name = label[:-2]
    accessor = _accessor(name)
    advertised = _advertised_levels(row)

    unadvertised = [
        (level, heading)
        for level, heading, _start in _atx_headings(_document_text(name))
        if level not in advertised
    ]
    if not unadvertised:
        pytest.skip(f"{label} carries no heading outside the levels it advertises")
    _level, heading = unadvertised[0]
    with pytest.raises(ValueError):
        accessor(section=heading)


# --------------------------------------------------------------------------- #
# AC3 — the claim is held against the accessor, not against the generator       #
# --------------------------------------------------------------------------- #

def test_no_docs_row_advertises_a_level_its_own_index_does_not_carry():
    """THE guard the whole finding turns on, in one assertion over the live set.

    Ablation (LD-646, watched red): restore the old uniform sentence — the one spelling both
    `##` and `###` for every document — and this reddens on `release_notes()` and
    `changelog()`, whose indexes carry level 2 only.
    """
    offenders = {}
    for label, _name, row in _document_rows():
        carried = {r["level"] for r in row["sections"]}
        over = _advertised_levels(row) - carried
        if over:
            offenders[label] = sorted(over)
    assert offenders == {}, (
        f"section_addressing advertises heading levels the document is not indexed at, so "
        f"`section=` raises for them: {offenders}. The sentence is generated — fix the "
        f"derivation in larkdocio.capabilities._addressing, never the document."
    )


def test_the_claim_is_not_asserted_uniformly_across_documents_that_differ():
    """The SHAPE of the bug: one sentence emitted for a population whose members differ.

    The documents genuinely differ in indexed level, so their claims must differ too. If every
    sentence were byte-identical again, the derivation has been short-circuited.
    """
    rows = _document_rows()
    carried = {label: frozenset(r["level"] for r in row["sections"]) for label, _n, row in rows}
    claims = {label: _advertised_levels(row) for label, _n, row in rows}
    assert len(set(carried.values())) > 1, (
        "the packaged documents no longer differ in indexed level; this guard has lost its "
        "specimen — re-derive it rather than deleting it"
    )
    assert len({frozenset(v) for v in claims.values()}) == len(set(carried.values()))
    for label, levels in carried.items():
        assert claims[label] == set(levels), label
