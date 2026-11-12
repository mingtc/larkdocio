"""LD-700 — the private-ledger helpers find what they hold. Self-tests use invented values."""
import json
import re
from pathlib import Path

import private_tree
from retired_particulars import LEDGER, load, phrase_hits, value_hits


def test_a_value_is_found_case_insensitively_anywhere_in_the_text():
    assert value_hits("prefix EXAMPLE particular suffix", ["Example Particular"])
    assert value_hits("nothing here", ["Example Particular"]) == []


def test_a_phrase_is_found_however_its_words_are_separated():
    for text in ("an Example-Phrase here", "example_phrase", "EXAMPLE  phrase"):
        assert phrase_hits(text, ["example phrase"]), text
    assert phrase_hits("examplephrase", ["example phrase"]) == []
    assert phrase_hits("an example phrases", ["example phrase"]) == []


@private_tree.dev_record
def test_every_group_the_guards_read_is_present_and_non_empty():
    """Every group in the ledger is a non-empty list, and every group a guard reads is in it.

    The groups are not named here (LD-719): a list of them spelled out the ledger's structure in
    a public file. The ledger's own keys are iterated instead (a key starting ``_`` is a note,
    not a group), and the groups the guards read are derived from the guards' own source: each
    ``load("<group>")`` call, and each name :mod:`domain_vocabulary` reads under its
    ``retired_set_`` prefix. A guard that reads a group the ledger lost reddens here, as does an
    emptied group, exactly as the hand-kept list did."""
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    groups = [key for key in ledger if not key.startswith("_")]
    assert groups, "the private ledger holds no groups"
    for group in groups:
        assert isinstance(ledger[group], list), f"ledger group {group!r} is not a list"
        assert load(group)
    tests = Path(__file__).resolve().parent
    by_load, by_prefix = set(), set()
    for path in sorted(tests.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        by_load |= set(re.findall(r'\bload\("([a-z_]+)"\)', text))
        by_prefix |= {"retired_set_" + name for name in
                      re.findall(r'\b(?:_one\(|_SET\[)"([a-z_]+)"', text)}
    assert by_load and by_prefix, (
        "no guard was found reading the ledger: the derivation has stopped seeing the reads")
    missing = sorted((by_load | by_prefix) - set(groups))
    assert not missing, f"guards read ledger groups the ledger does not hold: {missing}"
