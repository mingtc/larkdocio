"""LD-700 — the private-ledger helpers find what they hold. Self-tests use invented values."""
import private_tree
from retired_particulars import load, phrase_hits, value_hits


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
    for group in ("dates", "versions", "capture_values", "setup_values", "example_phrases",
                  "retired_set_pattern", "retired_set_word", "retired_set_id",
                  "retired_set_id_example", "retired_set_must_match",
                  "retired_set_must_not_match", "retired_set_file_plants"):
        assert load(group)
