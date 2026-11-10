"""LD-634 — *"the other seven"* is a DERIVED count, and the site that ships it derives it.

The fact is *which block types refuse a delete* — the most consequential thing the
write-hostile list says. It was hand-typed at three sites (``resolve.py``'s module
docstring, ``write/README.md``, and ``capabilities/_projections.py``, which ships it in
``capabilities(full=True)`` as data a consumer reads) and at a fourth in the dev repo's own
``BLOCKS.md``. The **set** is guarded fourteen ways including explicit membership
assertions; the **count** was guarded by nothing, and the set has already moved once —
LD-507 narrowed ``ImageNode`` — which is exactly the change that moves the number. All four
sentences would have gone stale simultaneously and silently, one of them inside the payload
(`process/doctrine/staleness.md`: derive it, or do not state it).

So: the shipped site derives it, the prose sites name where the answer is read instead of
restating it, and this file holds both halves. The derivation excludes the measured type
**by name** rather than subtracting one, so a second measured type or a ninth hostile type
moves the number instead of leaving a plausible wrong one.
"""
import importlib
import pathlib
import re

import pytest

from larkdocio.capabilities import _projections
from larkdocio.capabilities._projections import (
    _hostile_types_still_refusing_delete,
    _spelled,
)

#: By module. ``from larkdocio.write import resolve`` binds the package's exported
#: ``resolve`` FUNCTION, which shadows the module of the same name.
resolve = importlib.import_module("larkdocio.write.resolve")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The count stated in prose, in either register. Not applied to CHANGELOG /
#: RELEASE_NOTES — a dated release record states what was true on its date and is not
#: rewritten (`process/doctrine/staleness.md`).
HAND_TYPED_COUNT = re.compile(r"other\s+(?:seven|eight|nine|\d+)\b", re.I)

#: Every site that used to hold the count. Paths are relative to the repo root.
FORMERLY_HAND_TYPED = (
    "src/larkdocio/write/resolve.py",
    "src/larkdocio/write/README.md",
    "src/larkdocio/capabilities/_projections.py",
    "BLOCKS.md",
)


def test_the_count_is_what_the_two_tuples_say_it_is_today():
    """The number LD-634 verified before changing anything: 8 hostile, 1 measured, 7 left.

    A tripwire, not a second definition: the *set* is already guarded fourteen ways
    (``test_ld507_image_delete_narrowing.py`` names all eight members and pins the measured
    tuple), and every sentence about the count now derives. If the set legitimately moves,
    this line moves with it — and the shipped sentence follows on its own, which is the
    whole point.
    """
    assert len(resolve.WRITE_HOSTILE_NODE_TYPES) == 8
    assert len(resolve.DELETE_MEASURED_NODE_TYPES) == 1
    assert _hostile_types_still_refusing_delete() == 7
    assert _spelled(7) == "seven"


def test_the_shipped_sentence_carries_the_derived_count():
    prose = _projections._docx_content_constraints().floor
    assert "while the other seven types on that list still refuse delete" in prose


@pytest.mark.parametrize("measured, hostile_extra, expected", [
    ((), 0, "eight"),          # nothing measured — every hostile type refuses delete
    (None, 1, "eight"),        # a ninth hostile type, image still the only measured one
    (None, 4, "eleven"),
])
def test_the_sentence_FOLLOWS_the_tuples_which_is_what_derived_means(
        monkeypatch, measured, hostile_extra, expected):
    """The positive binding: substitute the tuples and the shipped sentence moves with them.

    Without this the assertion above would prove only that a hard-coded 'seven' is still
    spelled 'seven' — exactly the defect this issue closed.
    """
    hostile = resolve.WRITE_HOSTILE_NODE_TYPES + tuple(
        type(f"_Extra{n}", (), {}) for n in range(hostile_extra))
    monkeypatch.setattr(resolve, "WRITE_HOSTILE_NODE_TYPES", hostile)
    if measured is not None:
        monkeypatch.setattr(resolve, "DELETE_MEASURED_NODE_TYPES", measured)

    prose = _projections._docx_content_constraints().floor
    assert f"while the other {expected} types on that list still refuse delete" in prose


def test_the_measured_type_is_excluded_BY_NAME_not_by_subtracting_one(monkeypatch):
    """A second measured type must lower the count. Subtracting one would not notice."""
    monkeypatch.setattr(
        resolve, "DELETE_MEASURED_NODE_TYPES",
        resolve.WRITE_HOSTILE_NODE_TYPES[:3])
    assert _hostile_types_still_refusing_delete() == 5

    # And a measured type that is NOT on the hostile list cannot reduce it: the count is a
    # set difference, not arithmetic on two lengths.
    monkeypatch.setattr(
        resolve, "DELETE_MEASURED_NODE_TYPES",
        (resolve.ImageNode, type("_NotHostile", (), {})))
    assert _hostile_types_still_refusing_delete() == 7


def test_no_site_hand_types_the_count_any_more():
    hits = []
    for name in FORMERLY_HAND_TYPED:
        path = REPO_ROOT / name
        assert path.exists(), name
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HAND_TYPED_COUNT.search(line):
                hits.append(f"{name}:{number}: {line.strip()}")
    assert hits == [], hits


def test_the_detector_above_can_actually_fail():
    """The ablation. A green built on a regex that matches nothing proves nothing."""
    for caught in ("the other seven hostile types refuse every op",
                   "the **other seven** types still refuse delete",
                   "while the other 7 types on that list",
                   "the other eight write-hostile types"):
        assert HAND_TYPED_COUNT.search(caught), caught
    for allowed in ("every other hostile type refuses every op",
                    "WRITE_HOSTILE_NODE_TYPES minus DELETE_MEASURED_NODE_TYPES",
                    "the other types on that list"):
        assert not HAND_TYPED_COUNT.search(allowed), allowed
