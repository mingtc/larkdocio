"""LD-700 (round 3 of the public-export review, T14) — the public tree names no commit of the
private history.

The export is one commit with no history, so a hash of a maintainers' commit resolves to nothing
a reader can open — and it lets anyone holding the private history line the two trees up. The
prose around such a hash stays; the hash goes. This sweeps the whole public tree (the package,
the tests, the consumer kit and the root documents) for 7 to 40 hex characters after ``commit``,
``at``, ``baseline``, ``tip``, ``trunk``, ``@``, ``sha`` or ``revision``, or alone in backticks.
"""
import re
from pathlib import Path

from guard_kit import REPO_ROOT
import private_tree

ROOT = Path(REPO_ROOT)
_ROOT_DOCS = ("BASE.md", "BLOCKS.md", "DRIVE.md", "LARK_SETUP.md", "PERMISSIONS.md",
              "README.md", "RELEASE_NOTES.md", "SHEETS.md", "TOOLS.md")
#: A hash ALONE in backticks must look like one — a letter and a digit — or every backticked
#: number would be a commit.
_HEX = r"(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}"
#: After a commit word any 7-40 hex run is one: a short hash can be all digits or all letters
#: (LD-703, round 5 V6: an eight-digit ``baseline`` hash passed the letter-and-digit form above).
_HEX_AFTER_WORD = r"[0-9a-f]{7,40}"
#: Lowercase hex only, as git prints a hash: an uppercase run is a colour (``FFFFFF00``) or a
#: Lark log id, never a commit.
_COMMIT_HASH = re.compile(
    r"(?:(?:\b(?:[Cc]ommits?|at|[Bb]aseline|tip|trunk|sha|revision|rev)|@)\s*[:=#]?\s*[`*(]*"
    + _HEX_AFTER_WORD + r"(?![0-9a-zA-Z])|(?<![\w/.-])`+" + _HEX + r"`)")


#: LD-712 (round 10, R10-30): the recorded responses under ``tests/captures/`` are swept too, and
#: so are the test fixtures' ``.json`` files. They were skipped wholesale until then; a sweep found
#: no hash in them, so no keyed field (a content digest, a revision id) needs an exclusion today.
#: A digest is not a commit word, so ``"sha256": "<hex>"`` does not match (the test below says so).
_SUFFIXES = (".py", ".md", ".sh", ".json", "")


def _files():
    for top in ("src/larkdocio", "tests", "consumers"):
        for path in sorted((ROOT / top).rglob("*")):
            if (path.is_file() and path.suffix in _SUFFIXES
                    and "__pycache__" not in path.parts):
                yield path
    for name in _ROOT_DOCS:
        yield ROOT / name


def hashes(text):
    return [m.group(0) for m in _COMMIT_HASH.finditer(text)]


def test_the_sweep_catches_the_forms_and_spares_a_content_digest_word():
    assert hashes("the baseline 1a2b3c4d was green")
    assert hashes("measured at commit `abc1234`.")
    assert hashes("reverted in `0f1e2d3c4b`")
    # ``@`` is not a word character, so it cannot sit behind a ``\b``: these were the hole.
    assert hashes("measured on the pre-change tree (main @ 1a2b3c4d)")
    assert hashes("main@1a2b3c4d")
    assert not hashes("ask user@example.com about it")
    assert not hashes("sha256 of the payload")
    assert not hashes("at 2026-08-19 the run")
    # a recorded content digest, keyed as the captures key it, is not a commit
    assert not hashes('"sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"')


def test_LD712_the_recorded_responses_are_swept_too():
    """Round 10 (R10-30): the captures were skipped wholesale; they are in the sweep now."""
    swept = {path.relative_to(ROOT).parts[:2] for path in _files()}
    assert ("tests", "captures") in swept
    assert any(path.suffix == ".json" and "captures" in path.parts for path in _files())


def test_LD703_an_all_digit_or_all_letter_hash_after_a_commit_word_is_caught():
    """Round 5 (V6): a short hash need not mix letters and digits."""
    assert hashes("baseline ``12345678``, 17773 passed")
    assert hashes("measured at commit abcdefab")
    assert hashes("main @ 7654321")
    assert not hashes("`1234567` bytes")         # alone in backticks, a number stays a number


@private_tree.walks_tree
def test_no_public_file_names_a_private_commit():
    offenders = []
    for path in _files():
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        offenders += [f"{path.relative_to(ROOT)}: {h}" for h in hashes(text)]
    assert not offenders, offenders
