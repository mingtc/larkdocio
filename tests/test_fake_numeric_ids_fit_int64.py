"""LD-700 (round 3 of the public-export review, T8) — every fake numeric id fits int64, and its
derivation is stated.

A fake person / folder id used to be ``99000000`` plus a digest of the real id cut to length: at
19 digits that is above int64's maximum, so a recorded response carrying it unquoted
(``"ownerUser": 99…``) was an invalid fixture for any typed parser — and a digest of the real id
lets a holder of a guess confirm it. The fakes are now counter-assigned (``9``, then a small
counter zero-padded to the id's length); ``tests/captures/README.md`` states it.
"""
import json
import re
from pathlib import Path

INT64_MAX = 2 ** 63 - 1
TESTS = Path(__file__).resolve().parent
CAPTURES = TESTS / "captures"

_FAKE = re.compile(r"(?<!\d)9000000000\d{6,10}(?!\d)")
_RETIRED_FORM = re.compile(r"(?<!\d)99000000\d{8,12}(?!\d)")


def _ints(node):
    if isinstance(node, bool):
        return
    if isinstance(node, int):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _ints(value)
    elif isinstance(node, list):
        for value in node:
            yield from _ints(value)


def _text_files():
    for path in sorted(TESTS.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".json", ".md") and "__pycache__" not in path.parts:
            yield path


def test_every_integer_in_every_recorded_response_fits_int64():
    over = []
    for path in sorted(CAPTURES.rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        over += [f"{path.relative_to(TESTS)}: {n}" for n in _ints(doc) if not -INT64_MAX - 1 <= n <= INT64_MAX]
    assert not over, over


def test_no_fake_id_is_in_the_retired_digest_form_and_every_fake_fits_int64():
    retired, too_big = [], []
    for path in _text_files():
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        retired += [path.name for _ in _RETIRED_FORM.finditer(text)]
        too_big += [m.group(0) for m in _FAKE.finditer(text) if int(m.group(0)) > INT64_MAX]
    assert not retired, sorted(set(retired))
    assert not too_big, too_big


def test_the_retired_form_would_have_failed_the_range_check():
    assert int("99" + "0" * 17) > INT64_MAX
    assert int("9" + "0" * 15 + "123") <= INT64_MAX


def test_the_captures_readme_states_the_derivation():
    readme = (CAPTURES / "README.md").read_text(encoding="utf-8")
    flat = " ".join(readme.split())
    assert "counter-assigned" in flat
    assert "fits int64" in flat
