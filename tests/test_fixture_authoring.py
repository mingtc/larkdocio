"""Fixture-authoring completeness guards (LD-012, folds assessment C10).

Every ``tests/fixtures/*.input.json`` must be **authored** by
``tests/_make_fixtures.py`` — no orphan hand-edited JSON. This is what makes a
``blocks/``/``parser.py`` change a reviewable golden diff: the input side is
regenerable from a single module, the output side is the committed
``*.expected.md``.

These tests fail if:
* an ``*.input.json`` exists with no matching ``CASES`` entry (an orphan), or
* the committed ``*.input.json`` is not byte-identical to what
  ``_make_fixtures.write_inputs()`` would regenerate (drifted-by-hand JSON).
"""
import json

import _make_fixtures as mf
from harness import FIXTURES_DIR

_INPUTS = sorted(FIXTURES_DIR.glob("*.input.json"))
_INPUT_STEMS = [p.name[: -len(".input.json")] for p in _INPUTS]


def test_every_input_json_has_an_authoring_source():
    """No orphan ``*.input.json``: each has a ``CASES`` entry in the module."""
    orphans = sorted(set(_INPUT_STEMS) - set(mf.CASES))
    assert not orphans, (
        f"Orphan fixture inputs with no _make_fixtures.CASES source: {orphans}. "
        "Add an authoring entry so the JSON regenerates from the module."
    )


def test_no_case_without_a_committed_input():
    """Every ``CASES`` entry has produced a committed ``*.input.json``."""
    missing = sorted(set(mf.CASES) - set(_INPUT_STEMS))
    assert not missing, (
        f"CASES entries with no committed input.json: {missing}. "
        "Run `python tests/_make_fixtures.py` to write them."
    )


def test_every_registered_block_type_has_a_fixture():
    """AC2 guard: every block type in the live registry appears in at least one
    committed fixture input, so a new/changed handler always has a golden."""
    from larkdocio.blocks import get_registry

    registered = set(get_registry())
    seen = set()
    for path in _INPUTS:
        for block in json.loads(path.read_text(encoding="utf-8")):
            seen.add(block["block_type"])
    missing = sorted(registered - seen)
    assert not missing, (
        f"Registered block types with no fixture exercising them: {missing}. "
        "Author a case in _make_fixtures.py so the handler has a golden."
    )


def test_committed_inputs_regenerate_byte_identical():
    """Each committed ``*.input.json`` is byte-identical to a fresh regen from
    its ``CASES`` entry — proof the JSON is authored, not hand-edited."""
    drifted = []
    for name, blocks in mf.CASES.items():
        committed = (FIXTURES_DIR / f"{name}.input.json").read_text(encoding="utf-8")
        regen = json.dumps(blocks, indent=2) + "\n"
        if committed != regen:
            drifted.append(name)
    assert not drifted, (
        f"Committed input JSON differs from _make_fixtures regeneration: {drifted}. "
        "Regenerate with `python tests/_make_fixtures.py`."
    )
