"""Golden-file regression tests.

Each ``fixtures/<case>.input.json`` is a hand-authored block list (the shape
``Parser.parse_docx_content`` consumes). We deserialize it into real SDK Block
objects, render, and byte-compare against ``fixtures/<case>.expected.md``.

These fixtures lock CURRENT-CORRECT behavior for already-good blocks so a later
hardening edit that changes output is caught. When a change is intentional,
regenerate with::

    pytest tests/test_golden.py --update-golden
    # or
    LARKDOCIO_UPDATE_GOLDEN=1 pytest tests/test_golden.py

and review the resulting diff in code review — that diff IS the spec-change
record.
"""
import json

import pytest

from harness import FIXTURES_DIR, render

# LD-370 — CONFORMANCE-tier: the reader's Markdown for a corpus of real block payloads IS the product; a rewrite that renders differently has changed what consumers get.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

INPUTS = sorted(FIXTURES_DIR.glob("*.input.json"))
CASE_IDS = [p.name[: -len(".input.json")] for p in INPUTS]


@pytest.mark.parametrize("input_path", INPUTS, ids=CASE_IDS)
def test_golden(input_path, update_golden):
    case = input_path.name[: -len(".input.json")]
    expected_path = FIXTURES_DIR / f"{case}.expected.md"

    block_dicts = json.loads(input_path.read_text(encoding="utf-8"))
    actual = render(block_dicts)

    if update_golden:
        expected_path.write_text(actual, encoding="utf-8")
        pytest.skip(f"updated golden for {case}")

    assert expected_path.exists(), (
        f"Missing golden file {expected_path.name}. "
        f"Run with --update-golden to create it."
    )
    expected = expected_path.read_text(encoding="utf-8")
    assert actual == expected, f"Output drift for case '{case}'"


def test_at_least_one_fixture():
    assert INPUTS, "No golden fixtures found under tests/fixtures/"
