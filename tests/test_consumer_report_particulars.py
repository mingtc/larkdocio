"""LD-700 (T3) — a cited field report is never named by its file, its date or its version, and
never quoted verbatim.

This holds the class over the exported corpus: a report FILE under the maintainers' feedback
directory is never named (the directory may be, as a category), and no sentence pins an
encounter to a calendar day.

**TRANSFORMED by LD-715 (owner ruling 2026-11-07; `process/doctrine/supersession.md` § A.1).**
The reason this module was written is unchanged: a report's particulars are not the public
tree's to publish. What the ruling superseded is the conclusion that the public tree cites
reports at all, anonymised — it now describes each fix by what changed, and
``tests/test_no_report_narrative.py`` forbids the narrative from returning. So each test here
keeps running in the private repository, where it still holds the anonymisation rules over the
same corpus, and is skipped, with its reason, in the public tree. Ten carry
``@private_tree.reports``. The two that load the private particulars ledger
(``test_no_known_consumer_report_date_sits_beside_a_report_word`` and its version twin) keep the
``@private_tree.dev_record`` they already carried: that reason — they read the private evidence
record under ``dev/`` — is the narrower one and was true before this ruling, and either reason
skips them publicly, so replacing it would only lose information. Nothing was deleted.
"""
import re
from pathlib import Path

from guard_kit import REPO_ROOT
import private_tree

ROOT = Path(REPO_ROOT)

#: Where a reader of the public tree meets this prose: the shipped package, the root matrices
#: and notes, the consumer kit, and the tests (docstrings and comments are read too).
_GLOBS = ("src/larkdocio/**/*.py", "src/larkdocio/**/*.md", "consumers/**/*.md", "tests/*.py",
          "BASE.md", "BLOCKS.md", "DRIVE.md", "LARK_SETUP.md", "PERMISSIONS.md", "README.md",
          "RELEASE_NOTES.md", "SHEETS.md", "TOOLS.md")

#: A named report file — the directory alone (``dev/consumer-feedback/**``) is a category.
_REPORT_FILE = re.compile(r"consumer-feedback/[0-9A-Za-z][^\s`'\")*]*\.md")
#: A consumer's encounter pinned to a day, in either order within one clause.
#: LD-700 QA: also a report pinned to a day by the VERB alone — "reported <date>", "move
#: recorded <date>" — with no consumer word in reach (both shipped that way).
_DATED = re.compile(
    r"(consumer|reporter)[^.;|]{0,60}\b20\d\d-\d\d-\d\d"
    r"|\b20\d\d-\d\d-\d\d[^.;|\n]{0,25}\b(consumer|reporter)\b"
    r"|\b(reported|recorded|report)\b[^.;|\d]{0,12}\b20\d\d-\d\d-\d\d"
    r"|(?<![/\w-])20\d\d-\d\d-\d\d(?![\w-]*/)[^.;|\n]{0,12}\b(report|reported)\b"
    # LD-708 (round 8, Y3): the COMPACT day a Lark ``log_id`` opens with (``yyyymmdd…``) — a
    # consumer's incident handle kept its day while the rest became a placeholder.
    r"|(consumer|reporter)[^|\n]{0,40}\blog_?id\b[^|\d]{0,200}(?<!\d)20\d{6}",
    re.IGNORECASE)
#: A consumer quoted in their own words.
_VERBATIM = re.compile(r"(consumer|reporter)'s (own )?(words|verdict),? \*?\"|\"\*? was the "
                       r"(consumer|reporter)'s own|consumer's ask, verbatim",
                       re.IGNORECASE)

#: LD-703 (round 5, V3): ``_VERBATIM`` matched three fixed framings only, so ten consumer quotes in
#: other words ("stated the requirement exactly — *"…"*", "Their own verdict …: *"…"*", a docstring
#: that IS the quote) survived the rule this module states. The class it means is an emphasised
#: quotation (``*"…"*``) that a consumer, reporter or critique is credited with in the text just
#: before it.
_QUOTE = re.compile(r'\*"[^"]{4,}?"\*|\*“[^”]{4,}?”\*')
_CONSUMER_VOICE = re.compile(
    r"\b(?:consumer|reporter|critique)\w*\b[^.]{0,80}\b(?:stated|put it|asked|verdict|own words|"
    r"wrote|recommendation|ask)\b|\btheir own (?:verdict|words)\b|consumer_said", re.IGNORECASE)
#: How far before a quotation its credit is looked for (characters, whitespace flattened).
_VOICE_REACH = 160
#: Quotations the voice pattern reaches that are NOT a consumer's words, each with why.
_NOT_A_CONSUMER_QUOTE = {
    ("tests/test_front_door_guide_swap.py", "*\"swap it"): "the maintainer's ruling, not a consumer's",
    ("BLOCKS.md", "*\"will my"): "a question a reader may have, written by this project",
}

#: This file states the rule, so it names the patterns it forbids.
_EXEMPT = {"tests/test_consumer_report_particulars.py"}


def _corpus():
    seen = set()
    for pattern in _GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            if rel in _EXEMPT or rel in seen or not path.is_file():
                continue
            seen.add(rel)
            yield rel, path.read_text(encoding="utf-8")


def _unquoted(text):
    """``text`` with every emphasised quotation (``_QUOTE``) cut to ``*"q"*``, its newlines kept so
    line numbers still hold. LD-707 (round 7, X5): a quoted message between "consumer" and a date
    pushed the date past ``_DATED``'s reach, so the date shipped; the quote is not prose distance."""
    return _QUOTE.sub(lambda m: '*"q"*' + "\n" * m.group(0).count("\n"), text)


def _offences(regex):
    found = []
    for rel, text in _corpus():
        if regex is _DATED:
            text = _unquoted(text)
        for match in regex.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append(f"{rel}:{line}")
    return found


@private_tree.reports
def test_no_consumer_report_file_is_named():
    assert not _offences(_REPORT_FILE)


@private_tree.reports
def test_no_consumer_encounter_is_dated():
    assert not _offences(_DATED)


@private_tree.reports
def test_no_consumer_is_quoted_in_their_own_words():
    assert not _offences(_VERBATIM)


def consumer_quotes(rel, text):
    """``[line]`` of every emphasised quotation in ``text`` credited to a consumer just before it.

    **Every section of ``RELEASE_NOTES.md`` is read** (LD-710, round 9 Z6). This read only the
    topmost section, on the reason that a released section is history — and a verbatim consumer
    quote survived in a released section the guard never read. The reason still holds for what
    a section *says*; it does not hold for a quotation, which the public copy carries whatever
    its age, so the scope now covers the whole file."""
    found = []
    for match in _QUOTE.finditer(text):
        if any(rel == f and match.group(0).startswith(q) for f, q in _NOT_A_CONSUMER_QUOTE):
            continue
        before = " ".join(text[max(0, match.start() - _VOICE_REACH):match.start()].split())
        if _CONSUMER_VOICE.search(before):
            found.append(text.count("\n", 0, match.start()) + 1)
    return found


@private_tree.reports
def test_the_voice_class_catches_the_framings_round_5_found():
    """Each framing round 5 found, with an invented quotation."""
    for text in (
        'The consumer stated the requirement exactly — *"some words here"* — and',
        'needed eight attempts. Their own verdict is why: *"some words here"*',
        'The consumer ask that produced this section put it best:\n*"some words here"*',
        'def test_the_caveat_the_consumer_said_would_help():\n    """*"some words here"*',
        "The consumer ask this file guards, in the words it was asked in: *\"some words here\"*",
    ):
        assert consumer_quotes("x.py", text), text
    assert not consumer_quotes("x.py", 'a consumer looking for *"put a link in a cell"* finds')
    assert not consumer_quotes("x.py", 'The guide promises *"every recipe runs as pasted"*.')


@private_tree.reports
def test_no_consumer_is_quoted_in_their_own_words_in_ANY_framing():
    offenders = [f"{rel}:{line}" for rel, text in _corpus() for line in consumer_quotes(rel, text)]
    assert not offenders, offenders


@private_tree.reports
def test_a_quoted_message_does_not_carry_a_dated_encounter_past_the_guard():
    """LD-707 (round 7, X5): the shape that shipped — a consumer, a long quoted message, then the
    day — with an invented message and date."""
    text = ('which is why a consumer\nmet *"some long message: not expressible as anything this '
            'library\ncan write"* on a real document on\n**2000-01-01** — and it was never')
    assert not _DATED.search(text)
    assert _DATED.search(_unquoted(text))
    assert _unquoted(text).count("\n") == text.count("\n")


@private_tree.reports
def test_the_dated_class_catches_a_compact_day_at_the_head_of_a_consumer_log_id():
    """LD-708 (round 8, Y3): the shape that shipped — a consumer's ``log_id`` "replaced by a
    placeholder of the same length" that kept its leading ``yyyymmdd`` — with an invented day."""
    shipped = ("#: the consumer's own ``log_id``, replaced by a placeholder of the same length in this\n"
               '#: tree (the test only needs it to flow through intact).\n'
               'LOG_ID = "20000101000000000000000000EXAMPLE1"\n')
    assert _DATED.search(shipped)
    assert not _DATED.search(shipped.replace("20000101", "00000000"))
    # The project's own probe log_ids carry their recording day and name no consumer.
    assert not _DATED.search('the probe answered 1254045 (log_id "20000101123456ABCDEF")')


@private_tree.reports
def test_the_dated_class_catches_the_three_wordings_round_3_QA_found():
    """The three survivors QA found carried no consumer word in reach of the date; each wording
    is reproduced here with an invented date, so the pattern is proven without re-publishing the
    real one."""
    for text in (
        "the observed chips are one tenant's Docx mentions, reported 2000-01-01; the rest",
        "The 1.0.0-to-1.3.0 move recorded 2000-01-01 is four sections by the same count",
        "document mentions, on one tenant, reported 2000-01-01. The chips a person makes",
    ):
        assert _DATED.search(text), text


#: The words that make a date a REPORT's date when they sit beside it.
_REPORT_WORDS = re.compile(r"consumer|reporter|reported|recorded|critique", re.IGNORECASE)


def report_dated(text, dates, reach=40):
    """``[(date, context)]`` for every known report date with a report word within ``reach``
    characters — whatever the wording, with or without the word "consumer"."""
    found = []
    for date in dates:
        for match in re.finditer(re.escape(date), text):
            window = text[max(0, match.start() - reach):match.end() + reach]
            if _REPORT_WORDS.search(window):
                found.append((date, window))
    return found


@private_tree.reports
def test_the_known_date_check_catches_the_three_wordings_without_the_word_consumer():
    for text in ("Docx mentions, reported 2000-01-01; the rest",
                 "move recorded 2000-01-01 is four sections",
                 "on one tenant, reported 2000-01-01. The chips"):
        assert report_dated(text, ["2000-01-01"]), text
    assert not report_dated("probed on 2000-01-01 over eleven spellings", ["2000-01-01"])


@private_tree.dev_record
def test_no_known_consumer_report_date_sits_beside_a_report_word():
    """LD-700 QA: no date in the private ledger's ``dates`` list (tests/retired_particulars.py,
    read at run time) sits within reach of a report word anywhere in the public corpus. The same
    date beside the project's own measurement ("probed on …") is not a report's date and passes."""
    from retired_particulars import load

    dates = load("dates")
    offenders = [f"{rel}: {window!r}" for rel, text in _corpus()
                 for _date, window in report_dated(text, dates)]
    assert not offenders, offenders


@private_tree.dev_record
def test_no_known_consumer_version_sits_beside_a_report_word():
    """LD-700 QA (third review): no version in the private ledger's ``versions`` list sits within
    reach of a report word. Release headings use the same numbers legitimately, so a version is
    held only beside a report word."""
    from retired_particulars import load

    versions = load("versions")
    offenders = [f"{rel}: {window!r}" for rel, text in _corpus()
                 for _v, window in report_dated(text, versions)]
    assert not offenders, offenders


@private_tree.reports
def test_a_quote_in_a_RELEASED_section_is_caught_too():
    """LD-710 (round 9, Z6): the plant sits below the second release heading, where the old
    topmost-only read never looked."""
    text = ("# Notes\n\n## [9.9.9] — top\n\nNothing here.\n\n## [9.9.8] — released\n\n"
            'One consumer run wrote that there was *"some words here"* and stopped.\n')
    assert consumer_quotes("RELEASE_NOTES.md", text) == [9]
