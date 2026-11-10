"""LD-457 — the refusal-reason VOCABULARY: one spelling, exported, and drift-guarded.

**The defect.** The sheets compare-and-swap refuses with the wire value ``'stale-sheet'``.
The shipped guide wrote ``STALE_SHEET`` 14 times and ``stale-sheet`` zero times, and no
refusal-reason constant sat on the package's export surface. So the retry guard the guide
taught — ``if entry.refusal.reason == "STALE_SHEET": retry()`` — **never fired**, and the
write it was supposed to re-issue was dropped in silence. The mechanism was right; only its
vocabulary lied.

**The three vocabularies, and why only two are guarded here.**

* ``larkdocio.sheets`` and ``larkdocio.base`` type a refusal reason as a **plain string**, so
  the only spelling that can appear in a consumer's ``==`` is the **wire value**
  (``stale-sheet`` / ``stale-base``). A SCREAMING_SNAKE spelling in prose is therefore a
  spelling the comparison can never match — the defect.
* ``larkdocio.write`` (docx) types it as an **Enum**, whose member name *is*
  ``STALE_DOCUMENT`` and whose exported member is what a consumer compares against. There the
  prose spelling resolves to a real, exported, comparison-correct symbol, so it is **not** the
  same defect — the measured negative recorded by
  :func:`test_the_docx_vocabulary_needs_no_correction_its_names_are_the_exported_enum`.

**The one excused occurrence.** ``STALE_SHEET`` / ``STALE_BASE`` are also **safety-contract
ids** (``capabilities()["safety_contracts"]``), and the guide's contract table lists each id
in its row's leading cell — a different namespace, pinned bidirectionally by
``tests/test_guide.py``. The guard excuses exactly that position and nothing else, and
:func:`test_every_excused_occurrence_is_a_safety_contract_id` keeps the excuse from widening
into a loophole.
"""
import pathlib
import re

import pytest

import consumer_text

import larkdocio
import larkdocio.base as base_pkg
import larkdocio.sheets as sheets_pkg
import larkdocio.write as write_pkg
from log_reading_apply import reading_the_log
from larkdocio.base.plan import Refusal as BaseRefusal
from larkdocio.sheets.plan import Refusal as SheetsRefusal
from larkdocio.write.model import RefusalReason as DocxRefusalReason


# --------------------------------------------------------------------------- #
# The vocabularies, enumerated from the CLASSES — never from a hand-kept list,  #
# so a reason added tomorrow enrols itself in every check below.                #
# --------------------------------------------------------------------------- #

def reason_map(cls) -> dict:
    """``{ATTRIBUTE_NAME: wire value}`` for a string-valued refusal vocabulary."""
    return {n: v for n, v in vars(cls).items() if n.isupper() and isinstance(v, str)}


#: ``surface -> (the package a consumer imports, the refusal class)``.
STRING_VOCABULARIES = {
    "sheets": (sheets_pkg, SheetsRefusal),
    "base": (base_pkg, BaseRefusal),
}


# =========================================================================== #
# AC1 / AC2 — every reason is EXPORTED, under the one true spelling            #
# =========================================================================== #

@pytest.mark.parametrize("surface", sorted(STRING_VOCABULARIES))
def test_every_refusal_reason_the_plan_can_emit_is_exported(surface):
    """The reason vocabulary is reachable from the package a consumer imports, whole.

    Enumerated from the refusal class itself, so a reason added later cannot ship
    unexported — which is the property that makes this more than a one-time transcription.
    """
    package, refusal_cls = STRING_VOCABULARIES[surface]
    reasons = reason_map(refusal_cls)
    assert reasons, f"{surface}: the refusal class carries no reasons — enumeration broke"

    assert "RefusalReason" in package.__all__, (
        f"{surface}: the refusal-reason vocabulary is not on the export surface")
    assert "REFUSAL_REASONS" in package.__all__, (
        f"{surface}: the enumerable name->value mapping is not on the export surface")

    exported = package.RefusalReason
    missing = sorted(n for n in reasons if getattr(exported, n, None) != reasons[n])
    assert not missing, (
        f"{surface}: reasons the refusal class carries that RefusalReason does not export "
        f"(or exports under a different value): {missing}")

    assert dict(package.REFUSAL_REASONS) == reasons, (
        f"{surface}: REFUSAL_REASONS drifted from the refusal class")
    # The WIRE VALUES ARE UNCHANGED — this issue exports the vocabulary, it renames nothing:
    # every reason is still a PLAIN str (not an enum member, not a subclass), so an existing
    # consumer's `reason == "stale-sheet"` keeps working byte for byte.
    assert all(type(value) is str for value in reasons.values())
    assert all(type(getattr(exported, name)) is str for name in reasons)


def test_the_sheets_stale_reason_is_the_wire_value_not_the_screaming_spelling():
    """The regression pin, stated as the bug: a hand-typed ``"STALE_SHEET"`` matches nothing.

    This is the comparison the guide taught for 14 releases. It is pinned FALSE forever so
    nobody re-introduces the spelling believing it works.
    """
    assert SheetsRefusal.STALE_SHEET == "stale-sheet"
    assert SheetsRefusal.STALE_SHEET != "STALE_SHEET"
    assert BaseRefusal.STALE_BASE == "stale-base"
    assert BaseRefusal.STALE_BASE != "STALE_BASE"


def test_the_docx_vocabulary_needs_no_correction_its_names_are_the_exported_enum():
    """AC2's measured NEGATIVE for docx — the sibling audit's result, recorded as a test.

    ``larkdocio.write`` types the reason as an Enum: the guide's ``STALE_DOCUMENT`` spelling
    IS the exported member name, and the member is what a consumer compares against. A reader
    who copies that spelling lands on a symbol that exists and compares correctly — the
    opposite of the sheets/base story. Nothing to fix there, and this test says so in code so
    the negative cannot quietly rot.
    """
    assert "RefusalReason" in write_pkg.__all__
    assert DocxRefusalReason.STALE_DOCUMENT.value == "stale-document"
    assert DocxRefusalReason["STALE_DOCUMENT"] is DocxRefusalReason.STALE_DOCUMENT
    # ... and the enum is deliberately NOT a str-enum, so `reason == "stale-document"` is
    # false too: the member is the only correct comparison, which is exactly what the guide's
    # SCREAMING spelling points a reader at.
    assert DocxRefusalReason.STALE_DOCUMENT != "stale-document"
    assert DocxRefusalReason.STALE_DOCUMENT != "STALE_DOCUMENT"


# =========================================================================== #
# AC4 — the drift guard: no shipped text names a spelling the code cannot carry #
# =========================================================================== #

#: docx's names are excused wholesale: there the SCREAMING spelling is the exported enum
#: member name (see the measured negative above), not a value that fails a comparison.
_ENUM_NAMES = {member.name for member in DocxRefusalReason}


def guarded_names() -> set:
    """Every SCREAMING_SNAKE name a **string-valued** refusal vocabulary carries."""
    names = set()
    for _package, refusal_cls in STRING_VOCABULARIES.values():
        names |= set(reason_map(refusal_cls))
    return names - _ENUM_NAMES


def _leading_cell(line: str, name: str) -> bool:
    """True when the line is a Markdown table row whose FIRST cell is ``` `NAME` ```.

    That is the safety-contract table's id column — a different namespace, pinned to
    ``capabilities()["safety_contracts"]`` by ``tests/test_guide.py``.
    """
    return re.match(r"^\|\s*`" + re.escape(name) + r"`\s*\|", line) is not None


def bare_reason_hits(text: str) -> list:
    """``[(lineno, name, line)]`` — every bare SCREAMING spelling of a string-valued reason.

    ``(?<![.\\w])`` lets a **qualified** reference through (``Refusal.STALE_SHEET``,
    ``RefusalReason.STALE_SHEET``), which is what a recipe should teach; a bare token is what
    a consumer copies into a comparison that cannot match.
    """
    hits = []
    names = guarded_names()
    for lineno, line in enumerate(text.splitlines(), 1):
        for name in names:
            excusable = _leading_cell(line, name)
            for match in re.finditer(r"(?<![.\w])" + re.escape(name) + r"\b", line):
                if excusable:
                    excusable = False  # the id cell itself, once — the row's prose is not
                    continue
                hits.append((lineno, name, line.strip()[:140]))
    return hits


#: THE ONE REGISTERED ERRATUM. A release note whose entire job is to tell a consumer to grep
#: their own code for the dead spelling has to print it, or the reader cannot grep. Registered
#: by its exact sentence, with :func:`test_every_registered_erratum_is_still_in_the_text`
#: asserting each entry is still present — so an exemption cannot rot into a loophole, and a
#: mention anywhere else still reddens.
REGISTERED_ERRATA = (
    (
        '`== "STALE_SHEET"` never fired',
        # The release this erratum is about is 1.34.0 — said in a COMMENT, because a version
        # literal used as a value freezes the packaged version and reddens at the next cut
        # (test_version_bump_tolerance.py). LD-471 moved it here after that guard caught it.
        "the release-note erratum: it names the dead spelling so a consumer can grep for it",
    ),
)


def _without_errata(text: str) -> str:
    for sentence, _why in REGISTERED_ERRATA:
        text = text.replace(sentence, "<registered erratum>")
    return text


def test_every_registered_erratum_is_still_in_the_text():
    """An exemption that no longer matches anything is a loophole waiting to be reused.

    **The reason is unchanged; only WHERE the entry must still match has widened (LD-588).**
    The wheel's copy of the release notes is a **rolling window** of the newest N sections, so
    a 1.34.0-era erratum leaves the *shipped* corpus the moment an N+1-th section lands — a
    fact about the projection, not evidence that the erratum was never real or that the
    exemption was a guess. So liveness is read against the **canonical root documents** as
    well: the entry must still match text this repository owns. What the exemption *does* is
    untouched — it still excuses that one sentence in the shipped corpus and nothing else, and
    :func:`test_the_guard_bites_on_the_sentence_that_shipped` still proves the guard bites.
    """
    corpus = "\n".join(consumer_text.shipped_docs().values())
    root = pathlib.Path(__file__).resolve().parent.parent
    canonical = "\n".join(
        (root / name).read_text(encoding="utf-8")
        for name in ("RELEASE_NOTES.md", "CHANGELOG.md")
    )
    for sentence, why in REGISTERED_ERRATA:
        assert sentence in corpus or sentence in canonical, (
            f"registered erratum matches nothing this repo owns, shipped or canonical "
            f"({why}): {sentence!r}"
        )


def test_no_shipped_consumer_text_names_a_refusal_reason_the_wire_does_not_carry():
    """AC4 — the guard. Red against the 1.33.0 guide (14 ``STALE_SHEET`` + 2 ``STALE_BASE``
    + 1 ``MERGED_CELL_TARGET``, plus 4 in the packaged release notes)."""
    report = []
    for label, text in consumer_text.shipped_docs().items():
        for lineno, name, line in bare_reason_hits(_without_errata(text)):
            report.append(f"{label}:{lineno} {name} -> {line}")
    assert not report, (
        "shipped consumer text names a refusal-reason spelling the wire does not carry "
        "(write the wire value, or a qualified `RefusalReason.<NAME>`):\n" + "\n".join(report))


def test_every_excused_occurrence_is_a_safety_contract_id():
    """The excuse cannot widen into a loophole: the only positions the guard forgives are
    safety-contract id cells, and every one of them is a real id in ``capabilities()``."""
    contract_ids = set(larkdocio.capabilities(full=True)["safety_contracts"])
    excused = set()
    for text in consumer_text.shipped_docs().values():
        for line in text.splitlines():
            for name in guarded_names():
                if _leading_cell(line, name):
                    excused.add(name)
    assert excused, "the safety-contract table vanished — the guard's excuse is now dead code"
    assert excused <= contract_ids, (
        f"excused spellings that are not safety-contract ids: {sorted(excused - contract_ids)}")


def test_the_guard_bites_on_the_sentence_that_shipped():
    """Red-then-green on the exact line 1.33.0 shipped — the guard is proven to bite."""
    shipped = "    (someone else edited), that entry **refuses `STALE_SHEET` with no write**"
    assert bare_reason_hits(shipped), "the guard is blind to the defect it exists for"
    assert not bare_reason_hits(shipped.replace("`STALE_SHEET`", "`stale-sheet`"))
    # a QUALIFIED reference is what a recipe teaches, and is never a hit
    assert not bare_reason_hits("compare against `RefusalReason.STALE_SHEET`")
    # the contract table's id cell is excused ONCE — its prose is not
    row = "| `STALE_SHEET` | sheets-write | a bump refuses `STALE_SHEET` |"
    assert len(bare_reason_hits(row)) == 1


# =========================================================================== #
# AC5 — the guide's OWN retry guard, extracted verbatim, fires on a stale plan  #
# =========================================================================== #

_RECIPE_HEADING = "### Recipe: the sheets write handshake"


def _recipe_block() -> str:
    """The sheets-write recipe's python block, verbatim out of the shipped guide."""
    text = larkdocio.guide(full=True)
    start = text.index(_RECIPE_HEADING)
    end = text.index("### Recipe:", start + len(_RECIPE_HEADING))
    blocks = re.findall(r"```python\n(.*?)```", text[start:end], flags=re.DOTALL)
    assert blocks, "the sheets write recipe carries no python block"
    return blocks[0]


def retry_guard_source() -> str:
    """The retry-guard lines of that recipe — from its own import of the constant on."""
    lines = _recipe_block().splitlines()
    starts = [i for i, line in enumerate(lines) if "RefusalReason" in line]
    assert starts, (
        "the sheets write recipe does not teach the retry guard against the exported "
        "constant — a consumer is still left to hand-type the reason")
    return "\n".join(lines[starts[0]:]) + "\n"


def test_the_guides_retry_guard_fires_on_a_stale_refusal_and_recovers():
    """AC5 — the recipe's own snippet, run EXACTLY as the guide now teaches it, against a
    manufactured stale refusal: the branch is taken and the refused write lands on retry.

    Nothing is retyped here. The source is sliced out of ``guide()`` itself, so a guide edit
    that re-breaks the spelling (or drops the guard) reddens this test rather than shipping.
    """
    from test_sheets_write_apply import FakeSheetGateway

    from larkdocio.sheets.write_apply import ValueWriteRequest, apply, dry_run
    apply = reading_the_log(apply)

    gateway = FakeSheetGateway(revision=34, values={"s1!A1:A1": [["old"]]})
    requests = [ValueWriteRequest.for_a1("s1!A1:A1", [["new value"]])]
    plan = dry_run(requests, gateway, "shtTOKEN")
    gateway.external_bumps = {gateway._rev_reads + 1: 1}  # another user edits, mid-flight
    log = apply(plan, gateway)

    assert gateway.puts == [], "precondition: the compare-and-swap must have refused the write"
    assert log.entries[0].refusal.reason == SheetsRefusal.STALE_SHEET

    namespace = {
        "requests": requests,
        "write_client": gateway,
        "spreadsheet_token": "shtTOKEN",
        "dry_run": dry_run,
        "apply": apply,
        "plan": plan,
        "log": log,
    }
    exec(compile(retry_guard_source(), "<guide retry guard>", "exec"), namespace)

    assert gateway.puts == [("s1!A1:A1", [["new value"]])], (
        "the guide's retry guard did not fire: the refused write was dropped in silence, "
        "which is the whole defect")
    assert [e.outcome for e in namespace["log"].entries] == ["applied"]


def test_the_spelling_that_shipped_would_not_have_fired():
    """The counterfactual, pinned: the pre-1.34.0 guard silently skips a real stale refusal."""
    from test_sheets_write_apply import FakeSheetGateway

    from larkdocio.sheets.write_apply import ValueWriteRequest, apply, dry_run
    apply = reading_the_log(apply)

    gateway = FakeSheetGateway(revision=34, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1("s1!A1:A1", [["new"]])], gateway, "shtTOKEN")
    gateway.external_bumps = {gateway._rev_reads + 1: 1}
    log = apply(plan, gateway)

    fired = [e for e in log.entries
             if e.refusal is not None and e.refusal.reason == "STALE_SHEET"]
    assert fired == [], "the SCREAMING spelling must stay proven non-matching"
    assert [e for e in log.entries
            if e.refusal is not None
            and e.refusal.reason == sheets_pkg.RefusalReason.STALE_SHEET]
