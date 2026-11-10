"""THE `1254702` INDISTINGUISHABILITY SENTENCE, ROUTE-SCOPED (LD-501).

The Base copy route shipped a **class-level** claim out of a **route-level** measurement:
*"A folder this app cannot reach is not distinguishable from one that does not exist: Lark
answers ``1254702`` to both"* (``base/schema_client.py``'s ``copy_app`` docstring, mirrored in
the packaged guide and in ``BASE.md``). On the endpoint it was observed on that is what was
seen. As a statement about **Lark** it is now demonstrably wrong: the shipped
``create_document`` verb, handed a real folder the account holder owns and the application was
**not** granted, answers ``403 · 1770040 "no folder permission"`` — a clean, actionable denial,
nothing like ``1254702 DriveNodeNotExist`` (measured 2026-08-17, capture
``dev/ld493-caller-supplied-destination/captures/001-ac4-denial-create-document.json``).

Two different endpoints, so **nothing is falsified**: this is a NARROWING, not an overturning
(``process/doctrine/supersession.md`` § A.1 — the reason survives, only the conclusion's *scope*
moves), and the instrument is **D-59**: an evidence label is scoped to the ROUTE it was observed
on. The ``1254702`` observation itself (probe ``ld387-01``) survives untouched; what it stops
doing is speaking for every route.

This module holds four things in place:

* the claim is **route-scoped, not deleted and not vague** (AC1);
* the docx **counter-measurement** is named beside it, with both codes and its own D-59 scope
  (AC2);
* the **census** — the claim's SHAPE, over source text AND runtime values, across
  ``src/larkdocio/**`` and the root matrices — finds **no unscoped survivor** (AC4);
* the paragraph's own **unmeasured concession** (AC5) and the copy-route re-measurement (AC6)
  both still ship.

**SUPERSEDED IN ITS CONCLUSION BY LD-510 (2026-08-18), and TRANSFORMED rather than deleted.**
LD-501's reason — *an evidence label is scoped to the ROUTE it was observed on* (D-59) — is
preserved, still enforced by every test below, and **vindicated**: the one ``copy_app`` send it
named as the thing that would settle the parked half was authorised and made, once, and it
answered the other way. Handed a **real folder the application has no permission on**, the Base
copy route answers ``1254701 DriveNodePermNotAllow`` and copies nothing (capture
``dev/ld493-caller-supplied-destination/captures/002-copy-app-unreachable-folder.json``; one
send, 2026-08-18, no retries). So what moves is only the **conclusion about this route**: the
route DOES distinguish, in three measured outcomes, and the park is **closed rather than
deleted**. LD-387's ``ld387-01`` measurement and its unmeasured-placement concession are
untouched by all of it. The LD-510 half of this module lives in its own section at the bottom;
the AC6 tests above it kept their node ids and had their **bodies** moved to the new conclusion,
because a renamed test is a removed test.
"""
import ast
import importlib
import json
import pkgutil
import re

import pytest

import larkdocio
from larkdocio.base.schema_client import BaseSchemaClient

from guard_kit import REPO_ROOT
import private_tree  # noqa: E402  (LD-685)

COPY_DOC = BaseSchemaClient.copy_app.__doc__


# --------------------------------------------------------------------------- #
# AC1 — the sentence is ROUTE-SCOPED: not deleted, not weakened into vagueness. #
# --------------------------------------------------------------------------- #

#: The class-level form, verbatim as it shipped through 1.36. Its subject is **Lark**; that is
#: the whole defect. Its ABSENCE is only half the criterion — the other half is that what
#: replaced it still carries the measurement (below), because a deletion would have destroyed
#: an observation that was properly made.
CLASS_LEVEL_FORM = (
    "A folder this app cannot reach is not distinguishable "
    "from one that does not exist: Lark answers ``1254702`` to both"
)

#: The same claim as the packaged guide and ``BASE.md`` spelled it.
CLASS_LEVEL_FORM_GUIDE = "A folder this app cannot reach answers the same `1254702` as one"
CLASS_LEVEL_FORM_MATRIX = (
    "A folder this app cannot reach is **indistinguishable** from one that does not exist: "
    "Lark answers `1254702` to both"
)


def _norm(text):
    return " ".join(text.split())


@pytest.mark.conformance
def test_ac1_the_CLASS_LEVEL_form_no_longer_ships_in_the_docstring():
    assert _norm(CLASS_LEVEL_FORM) not in _norm(COPY_DOC)


@pytest.mark.conformance
@pytest.mark.parametrize("path, form", [
    ("src/larkdocio/GUIDE.md", CLASS_LEVEL_FORM_GUIDE),
    ("BASE.md", CLASS_LEVEL_FORM_MATRIX),
])
def test_ac1_the_CLASS_LEVEL_form_no_longer_ships_in_the_PROJECTIONS(path, form):
    assert _norm(form) not in _norm((REPO_ROOT / path).read_text(encoding="utf-8"))


@pytest.mark.conformance
def test_ac1_the_MEASUREMENT_ITSELF_survives_the_scoping():
    """The narrowing moves the claim's scope, never the observation. ``1254702`` and the probe
    that produced it both still ship — a strike would have cost the reader a real finding."""
    assert "1254702" in COPY_DOC
    assert "ld387-01" in COPY_DOC


@pytest.mark.conformance
@pytest.mark.parametrize("marker", [
    "copy_app",            # the verb the observation was made through
    "apps/:app_token/copy",  # the route, spelled as a route
])
def test_ac1_the_claim_NAMES_THE_ROUTE_it_was_observed_on(marker):
    assert marker in COPY_DOC


@pytest.mark.conformance
def test_ac1_the_scoped_claim_is_STILL_A_CLAIM_not_a_shrug():
    """Vagueness would be the other way to lose the finding. The scoped sentence still tells a
    caller what this endpoint answered and that the library relays it unedited."""
    lowered = _norm(COPY_DOC).lower()
    assert "distinguishable" in lowered
    assert "unedited" in lowered
    assert "retries" in lowered or "retry" in lowered


# --------------------------------------------------------------------------- #
# AC2 — the docx counter-measurement, named beside it with its own scope.       #
# --------------------------------------------------------------------------- #

#: Every element a reader needs to check the counter-measurement's edge for themselves. The
#: pair of CODES is the actionable half: *which answer you get depends on the route*.
COUNTER_MEASUREMENT_ELEMENTS = [
    ("the docx verb", "create_document"),
    ("the denial code", "1770040"),
    ("Lark's own message", "no folder permission"),
    ("the status", "403"),
    ("the not-found code it is distinct from", "1254702 DriveNodeNotExist"),
    ("the date", "2026-08-17"),
    ("one tenant", "one tenant"),
    ("one app identity", "one app identity"),
    ("the token class", "tenant_access_token"),
    ("one honest send", "one honest send"),
    ("the capture", "001-ac4-denial-create-document.json"),
]


@pytest.mark.conformance
@pytest.mark.parametrize("element, needle", COUNTER_MEASUREMENT_ELEMENTS)
def test_ac2_the_DOCSTRING_names_the_counter_measurement_with_its_scope(element, needle):
    assert needle in _norm(COPY_DOC), element


@pytest.mark.conformance
@pytest.mark.parametrize("element, needle", COUNTER_MEASUREMENT_ELEMENTS)
def test_ac2_the_PACKAGED_GUIDE_names_it_too(element, needle):
    assert needle in _norm(larkdocio.guide(full=True)), element


@pytest.mark.conformance
def test_ac2_the_reader_is_told_the_ANSWER_IS_ROUTE_DEPENDENT():
    """The actionable lesson, in the shipped text rather than only in this test's name: a
    consumer who reads only the copy route's answer stops looking for a denial they could act
    on."""
    for text in (_norm(COPY_DOC), _norm(larkdocio.guide(full=True))):
        assert "depends on the route" in text.lower()


@pytest.mark.conformance
def test_ac2_the_narrowing_does_NOT_claim_a_falsification():
    """Two endpoints, two answers, no contradiction. A text that said the copy measurement was
    *wrong* would be making a claim nobody measured.

    **Re-checked under LD-510 and kept unchanged**, because what that issue overturned was an
    INFERENCE (the unreachable half, explicitly *inferred rather than separately sent*) and not
    a measurement: ``ld387-01`` measured a token naming nothing and a non-folder object, both
    still answer ``1254702``, and calling that measurement falsified would still be a claim
    nobody made.
    """
    lowered = _norm(COPY_DOC).lower()
    for forbidden in ("falsified", "was wrong", "refuted", "mistaken", "no longer true"):
        assert forbidden not in lowered, forbidden


# --------------------------------------------------------------------------- #
# AC4 — THE CENSUS, by the claim's SHAPE, over BOTH readings (the LD-480        #
# lesson: source text catches what only exists as text — a comment, a document; #
# folded/runtime values catch what only exists once assembled).                 #
# --------------------------------------------------------------------------- #

#: A sentence that names the endpoint the answer was observed on — either route: the Base copy
#: one the ``1254702`` was seen on, or the docx create one the ``1770040`` denial was seen on.
#: Deliberately NOT the bare word "copy": ``copies nothing`` is exactly the phrasing one of the
#: survivors used, and a marker that matched it would make the census vacuous on the very site
#: it was built for.
ROUTE_SCOPE_MARKER = re.compile(
    r"(?:copy_app|copy_base|apps/:app_token/copy|"
    r"(?:this|that|the)\s+(?:base\s+)?copy\s+(?:route|endpoint|call)|"
    r"on\s+this\s+route|this\s+endpoint|this\s+route|"
    r"create_document|docx/v1/documents)", re.I)

#: The subject half of the class-level claim: a folder this identity cannot get to.
UNREACHABLE_FOLDER = re.compile(
    r"(?:cannot|can\s*not|can't|could\s+not|couldn't|unable\s+to)\s+(?:be\s+)?reach"
    r"|unreachable|not\s+reachable|(?:no|without)\s+(?:permission|access)\s+to\s+(?:the\s+)?folder",
    re.I)

#: The predicate half: the two cases come back the same. Shapes, not one spelling.
SAMENESS = re.compile(
    r"indistinguishable|not\s+distinguishable|(?:is|are)n't\s+distinguishable"
    r"|answers?\s+the\s+same|same\s+(?:answer|code|`?1254702)"
    r"|to\s+both|either\s+way|cannot\s+tell\s+(?:them\s+)?apart|no\s+way\s+to\s+tell",
    re.I)

#: The other half of the census: an ANSWER claim about ``1254702`` at all. The recipe comment
#: that shipped *"is refused 1254702 and copies nothing"* names no unreachable folder, so the
#: shape above cannot reach it — and it teaches the same route-blind lesson.
#: LD-510 widened it to the DENIAL code as well: ``1254701`` is a one-send observation on this
#: same route, so a sentence stating it is under exactly the same D-59 obligation to name where
#: it was seen. The reason is LD-501's, unchanged; only the alphabet grew.
CODE_ANSWER = re.compile(
    r"1254702|DriveNodeNotExist|1254701|DriveNodePermNotAllow", re.I)


def _sentences(text):
    """Whitespace-folded sentences. A sentence is the unit a claim's scope lives in: a
    paragraph-wide check would let a scoped neighbour vouch for an unscoped sentence, which is
    precisely how the class-level form survived beside a properly scoped one."""
    folded = _norm(text)
    return [s for s in re.split(r"(?<=[.!?;])\s+|\n", folded) if s.strip()]


def _is_bare_lark_token(sentence):
    """``"DriveNodeNotExist"`` — Lark's own ``msg``, alone, making no claim about any route.

    **LD-531 TRANSFORMED THIS CENSUS; IT DID NOT WEAKEN IT, AND THE REASON IS UNCHANGED.** The
    reason LD-501 wrote and LD-510 widened still binds in full: *an evidence label is scoped to
    the ROUTE it was observed on* (D-59), so a **sentence** stating what a route answers must
    name that route, and every such sentence is still caught below.

    What LD-531 added to the corpus is a different kind of string. The one authored error-code
    lookup (``larkdocio.common.error_codes``) carries, per row, Lark's ``msg`` **verbatim** in a
    ``label`` field, precisely so somebody grepping a log finds the row — and ``DriveNodeNotExist``
    verbatim is a bare token, not a proposition. It asserts nothing about which route answers
    what, so there is nothing for a route scope to scope. Scoping it would mean writing a
    sentence into a field whose whole contract is *Lark's words and nothing added*.

    The exemption is deliberately the **narrowest shape that can express it**, and it is the
    same instrument ``tests/test_dev_repo_citations.py`` uses for a composition fragment: a
    single whitespace-free token. Anything with a space in it is a sentence and is judged as
    one, which is why the row's ``meaning`` — where the claim actually lives — is fully inside
    the census and had to name its route to get in.
    """
    stripped = sentence.strip().strip('`"\'.,;')
    return bool(stripped) and not any(c.isspace() for c in stripped) \
        and bool(CODE_ANSWER.fullmatch(stripped))


def _survivors(text):
    """Every sentence that makes one of the two claims WITHOUT naming its route."""
    found = []
    for sentence in _sentences(text):
        makes_claim = (
            (UNREACHABLE_FOLDER.search(sentence) and SAMENESS.search(sentence))
            or CODE_ANSWER.search(sentence)
        )
        if not makes_claim:
            continue
        if ROUTE_SCOPE_MARKER.search(sentence):
            continue
        if _is_bare_lark_token(sentence):
            continue
        found.append(sentence)
    return found


def test_ld531_the_bare_token_exemption_is_NARROW_and_cannot_hide_a_sentence():
    """The exemption's own guard: it excuses a token and nothing that says anything."""
    for excused in ("DriveNodeNotExist", "`DriveNodePermNotAllow`", "1254702", '"1254701"'):
        assert _is_bare_lark_token(excused), excused
        assert not _survivors(excused), excused
    for caught in ("1254702 is what an unreachable folder answers.",
                   "DriveNodeNotExist means the folder is not there.",
                   "A bad folder value answers 1254701.",
                   "the answer is 1254702 either way"):
        assert not _is_bare_lark_token(caught), caught
        assert _survivors(caught), caught


#: The dated release records, excluded BY NAME and for a reason that is not convenience: an
#: entry published under a version already shipped says what was claimed **then**. Rewriting it
#: destroys the record instead of superseding it. Both copies — root and packaged — are
#: excluded, and the exclusion is answered by
#: :func:`test_ac4_the_DATED_RELEASE_RECORD_exclusion_is_ANSWERED_by_the_OPEN_SECTION`, so it
#: cannot become a hiding place.
DATED_RELEASE_RECORDS = ("CHANGELOG.md", "RELEASE_NOTES.md")

#: The root matrices — where a claim about a surface is also authored.
ROOT_MATRICES = ("BLOCKS.md", "SHEETS.md", "BASE.md", "DRIVE.md", "PERMISSIONS.md", "README.md")

#: Beyond the AC's corpus, and deliberately: the decision register is a **projection of current
#: state** (``requirements/DECISIONS.md`` § How to read this file), so D-55 stating the
#: class-level form would leave the superseded reach alive in the one document a maintainer opens
#: to ask *what is true now*. The census found it there; it is scoped there too.
EXTRA_REGISTERS = ("requirements/DECISIONS.md",)


def _census_files():
    shipped = sorted((REPO_ROOT / "src/larkdocio").rglob("*.py"))
    shipped += sorted((REPO_ROOT / "src/larkdocio").rglob("*.md"))
    shipped += [REPO_ROOT / name for name in ROOT_MATRICES]
    shipped += [REPO_ROOT / name for name in EXTRA_REGISTERS]
    return [p for p in shipped if p.name not in DATED_RELEASE_RECORDS]


def _folded_string_values(path):
    """Every string literal **as the interpreter sees it** — implicit concatenations folded."""
    values = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            values.append("".join(
                part.value if isinstance(part, ast.Constant) and isinstance(part.value, str)
                else " " for part in node.values))
    return values


def _runtime_string_values():
    """The values the **imported** package actually holds, plus its two published projections."""
    values = [larkdocio.guide(full=True),
              json.dumps(larkdocio.capabilities(full=True), ensure_ascii=False)]
    package = importlib.import_module("larkdocio")
    for info in pkgutil.walk_packages(package.__path__, prefix="larkdocio."):
        module = importlib.import_module(info.name)
        values.append(module.__doc__ or "")
        for name in dir(module):
            attribute = getattr(module, name, None)
            if isinstance(attribute, str):
                values.append(attribute)
            elif callable(attribute) and getattr(attribute, "__doc__", None):
                values.append(attribute.__doc__)
    return values


def _census_hits():
    hits = []
    for path in _census_files():
        text = path.read_text(encoding="utf-8")
        for sentence in _survivors(text):
            hits.append(("source", str(path.relative_to(REPO_ROOT)), sentence))
        if path.suffix == ".py":
            for value in _folded_string_values(path):
                for sentence in _survivors(value):
                    hits.append(("value", str(path.relative_to(REPO_ROOT)), sentence))
    for value in _runtime_string_values():
        for sentence in _survivors(value):
            hits.append(("runtime", None, sentence))
    return list(dict.fromkeys(hits))


@private_tree.register
@pytest.mark.conformance
def test_ac4_NO_SHIPPED_TEXT_still_answers_1254702_WITHOUT_NAMING_ITS_ROUTE():
    assert _census_hits() == [], _census_hits()


@pytest.mark.conformance
def test_ac4_the_census_READS_BOTH_the_source_text_AND_the_runtime_values():
    """A census that silently degraded to one reading would go green on exactly the site it was
    built for. Both readings are proven to really hold the shipped text."""
    names = {p.name for p in _census_files()}
    assert {"schema_client.py", "GUIDE.md", "BASE.md"} <= names
    folded = _folded_string_values(REPO_ROOT / "src/larkdocio/base/schema_client.py")
    # Python 3.13+ dedents a docstring at compile time, so the folded literal is the same text
    # with its source indentation still on it — compare folded-whitespace, not byte-for-byte.
    assert any(_norm(COPY_DOC) == _norm(value) for value in folded), (
        "the folded reading really holds the docstring")
    values = _runtime_string_values()
    assert any("1254702" in v for v in values), "the runtime reading really reaches the claim"


#: The three sites known at mint plus the fourth the CENSUS found (``BASE.md``'s ``folder_token``
#: row — named by no list, caught by the shape). Each is quoted **as it shipped before this
#: change**; restoring one in situ is what proves the census bites rather than decorates.
SURVIVORS_BEFORE = (
    (
        "src/larkdocio/base/schema_client.py",
        "A folder this app cannot reach is not distinguishable\n        "
        "from one that does not exist: Lark answers ``1254702`` to both, unedited, and nothing\n"
        "        here asks for a further permission or retries.",
    ),
    (
        "src/larkdocio/GUIDE.md",
        "A folder this app cannot reach answers the same `1254702` as one\n"
        "that does not exist, and nothing here retries it or asks for a further permission.",
    ),
    (
        "src/larkdocio/GUIDE.md",
        "A folder\n"
        "# that does not exist — or a token that is not a folder — is refused 1254702 and copies\n"
        "# nothing.",
    ),
    (
        "BASE.md",
        "A folder this app cannot reach is **indistinguishable** from one that does not exist: "
        "Lark answers `1254702` to both and the library surfaces that answer unedited, asking "
        "for no further permission.",
    ),
)


@pytest.mark.conformance
@pytest.mark.parametrize("path, survivor", SURVIVORS_BEFORE,
                         ids=[f"{i}-{p}" for i, (p, _) in enumerate(SURVIVORS_BEFORE)])
def test_ac4_the_census_BITES_on_each_survivor_AS_IT_SHIPPED(path, survivor):
    """A census you have not watched redden is decoration. Each of the four phrasings the
    corpus really carried before this change is a hit — by SHAPE, none of them by an
    allow-list of files or an incidental spelling."""
    assert _survivors(survivor), f"the census cannot reach the {path} survivor"


@pytest.mark.conformance
def test_ac4_the_census_is_SATISFIED_BY_SCOPE_not_by_deletion():
    """The counter-check: the same sentences, route-named, are clean. Otherwise the only way to
    go green would be to delete the finding."""
    for _, survivor in SURVIVORS_BEFORE:
        scoped = "On the Base copy route (copy_app), " + _norm(survivor)
        assert not _survivors(scoped), scoped


@private_tree.internal_log
@pytest.mark.conformance
def test_ac4_the_DATED_RELEASE_RECORD_exclusion_is_ANSWERED_by_the_OPEN_SECTION():
    """The exclusion is asserted rather than assumed, so it cannot become a hiding place: the
    four excluded files are excluded by name, and the change is nonetheless disclosed to
    consumers in the OPEN ``## [1.37.0]`` section of both records."""
    excluded = [REPO_ROOT / "CHANGELOG.md", REPO_ROOT / "RELEASE_NOTES.md",
                REPO_ROOT / "src/larkdocio/CHANGELOG.md",
                REPO_ROOT / "src/larkdocio/RELEASE_NOTES.md"]
    read = {p.resolve() for p in _census_files()}
    for path in excluded:
        assert path.exists()
        assert path.resolve() not in read, f"{path.name} is a dated release record"
    for path in (REPO_ROOT / "CHANGELOG.md", REPO_ROOT / "RELEASE_NOTES.md"):
        text = path.read_text(encoding="utf-8")
        section = text.split("## [1.37.0]", 1)[1].split("\n## [", 1)[0]
        assert "1770040" in section and "1254702" in section and "1254701" in section, (
            f"{path.name}'s open section does not disclose the route-dependent answer")


# --------------------------------------------------------------------------- #
# AC5 — the paragraph's own UNMEASURED concession is PRESERVED.                 #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
@pytest.mark.parametrize("element, needle", [
    ("the unmeasured case", "placement into a folder that is not the default destination"),
    ("why it could not be measured", "the only addressable folder was the app's own root"),
    ("the reason a second folder could not be provisioned",
     "``create_folder`` is a permanent Drive write with no purge verb"),
    ("the honest claim it leaves", "the folder you name is read, checked, and is where the copy is"),
])
def test_ac5_the_UNMEASURED_CONCESSION_still_ships_in_the_docstring(element, needle):
    """It is the reason the sentence was scopeable at all — and a rationale-free strike is what
    gets a settled argument re-litigated (``process/doctrine/supersession.md`` § A.1)."""
    assert needle in _norm(COPY_DOC), element


@pytest.mark.conformance
def test_ac5_the_concession_still_ships_in_the_GUIDE_and_the_MATRIX():
    guide = _norm(larkdocio.guide(full=True))
    assert "What was **not** measured is a folder other than the app's own root" in guide
    assert "untested, not broken" in guide
    matrix = _norm((REPO_ROOT / "BASE.md").read_text(encoding="utf-8"))
    assert ("*placement into a folder that is not the default* is **unmeasured, not refuted**"
            in matrix)


# --------------------------------------------------------------------------- #
# AC6 — the parked re-measurement is NAMED as still parked, not silently closed.#
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac6_the_PARKED_copy_route_re_measurement_is_NAMED_in_the_shipped_text():
    """**Body superseded by LD-510; node id kept, because a renamed test is a removed test.**

    LD-501's reason for this test stands word for word: the parked re-measurement must be
    *named* in the shipped text rather than left as a silent gap, so a reader learns the state
    of the question instead of discovering a hole. Only its conclusion moved — the park is now
    **closed**, so what has to be named is the closure: that the one ``copy_app`` send was made,
    when, and what it answered. Asserting the OPEN park here would now assert a falsehood.
    """
    text = _norm(COPY_DOC)
    assert "**parked**" in text, "the park is still named — closed, not vanished"
    assert "one ``copy_app`` send was made on 2026-08-18" in text
    assert "1254701" in text
    for still_open in ("not been re-measured", "would settle it", "unmade"):
        assert still_open not in text, still_open


@private_tree.register
@pytest.mark.conformance
def test_the_REGISTER_records_the_narrowing_where_it_is_LOOKED_UP():
    """``requirements/DECISIONS.md`` is a projection of what is true **now**, so D-55 — the
    ruling that shipped the sentence — carries the narrowing, its counter-measurement and the
    park, and keeps its own reason and measurement untouched (supersession § A.1)."""
    register = _norm((REPO_ROOT / "requirements/DECISIONS.md").read_text(encoding="utf-8"))
    d55 = register.split("### D-55")[1].split("### D-87")[0]
    assert "NARROWED by LD-501" in d55 and "not overturned" in d55
    assert "1770040" in d55 and "1254702 DriveNodeNotExist" in d55
    assert "depends on the route" in d55
    # LD-510: the park is CLOSED in the register too, and LD-501's narrowing is kept as HISTORY
    # rather than overwritten — the register is a projection of what is true now, so it has to
    # carry both the ruling that moved and the reason it was ever written.
    assert "that park is CLOSED by LD-510 below" in d55
    assert "SUPERSEDED IN ITS CONCLUSION by LD-510" in d55
    assert "NARROWED by LD-501" in d55, "the earlier narrowing survives as history"
    # the reason and the original measurement survive
    assert "probe `ld387-01`" in d55
    assert "unmeasured, not refuted" in d55


# RETIRED 2026-09-18 (pre-export evidence-tree retirement, was @pytest.mark.conformance) — its
# narrative home, dev/README.md (in the dev repo)'s LD-493 entry, went with the evidence tree; the park's CODE-side
# claims are still pinned by the other AC legs in this file.
#


# =========================================================================== #
# LD-510 — THE SUPERSESSION OVER A SUPERSESSION.                               #
#                                                                             #
# LD-501 scoped a class-level claim to one route and parked the one send that  #
# would settle that route's own unreachable-folder case. The send was made     #
# (once, 2026-08-18) and answered ``1254701 DriveNodePermNotAllow``, so the    #
# route DOES distinguish. Everything below reuses the census engine above —    #
# ``_census_files`` / ``_folded_string_values`` / ``_runtime_string_values`` / #
# ``_sentences`` — rather than standing up a second one.                       #
# =========================================================================== #

#: The claim LD-510 retires OUTRIGHT: the unreachable-folder case and the not-found case coming
#: back the same. LD-501 made this sentence survivable by naming its route; it is not survivable
#: any more, on this route or off it, because on the only route it was ever measured on the two
#: answers are now known to differ and nowhere else has been measured at all.
SAMENESS_CLAIM_IS_RETIRED = True

#: A park clause about THIS route: *not re-measured · would settle it · parked · unmade*.
PARK_CLAUSE = re.compile(
    r"not\s+been\s+re-?measured|has\s+not\s+been\s+re-?sent|not\s+re-?measured"
    r"|would\s+settle\s+it|park(?:ed|s)?\b|unmade", re.I)

#: …scoped to the Base copy route, because a park about some other question is not this one.
COPY_ROUTE_MARKER = re.compile(
    r"copy_app|copy_base|apps/:app_token/copy|"
    r"(?:this|that|the)\s+(?:base\s+)?copy\s+(?:route|endpoint|call)|"
    r"on\s+this\s+route|this\s+route|this\s+endpoint", re.I)

#: What turns a park sentence from an OPEN gap into recorded HISTORY: the send's date, the code
#: it answered, or the word that says the question is settled. A park may still be *named* —
#: closing it silently is the failure this shape polices, exactly as leaving it open is.
PARK_CLOSURE = re.compile(r"1254701|DriveNodePermNotAllow|2026-08-18|clos(?:e|ed|ure)", re.I)

#: The third shape the census must reach: a bare claim that this route answers ``1254702`` to
#: BOTH cases. It is the class-level form's last hiding place — a sentence that never says
#: "unreachable" and never says "indistinguishable", only *"either way"*.
BOTH_CASES = re.compile(r"to\s+both|both\s+cases|either\s+way|to\s+either", re.I)


def _survivors_ld510(text):
    """Every sentence still carrying one of the three superseded shapes.

    Same sentence unit and same folding as :func:`_survivors` — a claim's scope lives in a
    sentence, and a paragraph-wide read lets a corrected neighbour vouch for an uncorrected
    clause.
    """
    found = []
    for sentence in _sentences(text):
        if UNREACHABLE_FOLDER.search(sentence) and SAMENESS.search(sentence):
            found.append(("sameness", sentence))
            continue
        if (PARK_CLAUSE.search(sentence) and COPY_ROUTE_MARKER.search(sentence)
                and not PARK_CLOSURE.search(sentence)):
            found.append(("open-park", sentence))
            continue
        if re.search(r"1254702", sentence) and BOTH_CASES.search(sentence):
            found.append(("answers-both", sentence))
    return found


def _census_hits_ld510():
    """The LD-510 census over the SAME corpus and the SAME two readings as AC4's."""
    hits = []
    for path in _census_files():
        text = path.read_text(encoding="utf-8")
        for kind, sentence in _survivors_ld510(text):
            hits.append((kind, "source", str(path.relative_to(REPO_ROOT)), sentence))
        if path.suffix == ".py":
            for value in _folded_string_values(path):
                for kind, sentence in _survivors_ld510(value):
                    hits.append((kind, "value", str(path.relative_to(REPO_ROOT)), sentence))
    for value in _runtime_string_values():
        for kind, sentence in _survivors_ld510(value):
            hits.append((kind, "runtime", None, sentence))
    return list(dict.fromkeys(hits))


@private_tree.register
@pytest.mark.conformance
def test_ld510_NO_SHIPPED_TEXT_still_says_the_two_cases_DO_NOT_COME_APART():
    """The census, as a census: no survivor of any of the three shapes, in either reading."""
    assert _census_hits_ld510() == [], _census_hits_ld510()


#: Every phrasing the corpus really carried before this change — the four sites the census
#: reaches, each in BOTH of its halves (the sameness claim and its park clause). Quoted
#: verbatim as it shipped; restoring one in situ is what proves the census bites.
SURVIVORS_BEFORE_LD510 = (
    ("src/larkdocio/base/schema_client.py", "sameness",
     "**On this route the two cases have not come apart**: every bad folder value ``copy_app``\n"
     "        was handed came back ``1254702``, unedited, and nothing here asks for a further\n"
     "        permission or retries — so a folder this app cannot reach is not distinguishable, "
     "*here*,\n        from one that does not exist."),
    ("src/larkdocio/base/schema_client.py", "open-park",
     "The copy route's own unreachable-folder\n        case has **not been re-measured** since — "
     "one ``copy_app`` send against that same\n        ungranted token would settle it, and it "
     "is deliberately **parked**, unmade."),
    ("src/larkdocio/GUIDE.md", "sameness",
     "On this route the two cases have not come apart — a folder this\napp cannot reach is not "
     "distinguishable **here** from one that does not exist, `copy_base` relays\nthat `1254702` "
     "unedited, and nothing here retries it or asks for a further permission."),
    ("src/larkdocio/GUIDE.md", "open-park",
     "the copy\nroute's own unreachable-folder case has not been re-measured since."),
    ("BASE.md", "sameness",
     "**On this route** the two cases have not come apart: a folder this app cannot reach is not "
     "distinguishable **here** from one that does not exist, the copy endpoint answers `1254702` "
     "and the library surfaces that answer unedited, asking for no further permission."),
    ("BASE.md", "open-park",
     "The copy route's own unreachable-folder case has not been re-measured since: one `copy_app` "
     "send against that same ungranted token would settle it and it stays **parked** (LD-501)."),
    ("requirements/DECISIONS.md", "sameness",
     "**No scope\nmoves** — the endpoint set is unchanged — and **on this route** a folder this "
     "app cannot reach\nis not distinguishable from one that does not exist: the copy endpoint "
     "answers `1254702` and the\nlibrary surfaces that answer unedited, asking for no further "
     "permission."),
    ("requirements/DECISIONS.md", "open-park",
     "The copy route's own unreachable-folder case\nhas **not** been re-measured — one `copy_app` "
     "send against that same ungranted token would settle\nit, and it stays **parked**; LD-501 "
     "spent zero live-API calls."),
    # The class-level form's last hiding place, which no site actually shipped — kept because a
    # shape nobody can demonstrate biting is a shape nobody should trust.
    ("(synthetic — the answers-both shape)", "answers-both",
     "The copy endpoint answers `1254702` either way."),
)


@pytest.mark.conformance
@pytest.mark.parametrize("path, kind, survivor", SURVIVORS_BEFORE_LD510,
                         ids=[f"{i}-{k}-{p}" for i, (p, k, _) in
                              enumerate(SURVIVORS_BEFORE_LD510)])
def test_ld510_the_census_BITES_on_each_survivor_AS_IT_SHIPPED(path, kind, survivor):
    """A census you have not watched redden is decoration (the charter's Phase-4 bar)."""
    hits = _survivors_ld510(survivor)
    assert hits, f"the census cannot reach the {path} {kind} survivor"
    assert kind in {k for k, _ in hits}, (kind, hits)


@private_tree.register
@pytest.mark.conformance
def test_ld510_the_census_is_SATISFIED_BY_CORRECTION_not_by_deletion():
    """The counter-check, in the LD-501 shape: the corrected text is clean **and still says
    something** — every site names the denial code, the not-found code and the route, so the only
    way to go green was to state the measured truth rather than to strike the paragraph."""
    for path in ("src/larkdocio/base/schema_client.py", "src/larkdocio/GUIDE.md", "BASE.md",
                 "requirements/DECISIONS.md"):
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert not _survivors_ld510(text), path
        assert "1254701" in text and "1254702" in text, path
        assert "copy_app" in text or "copy_base" in text, path


# --------------------------------------------------------------------------- #
# LD-510 AC2 — the THREE-OUTCOME truth, and the three boundaries it may not     #
# cross.                                                                        #
# --------------------------------------------------------------------------- #

#: The docstring and the packaged guide are what a caller actually reads.
THREE_OUTCOME_ELEMENTS = [
    ("the denial code", "1254701"),
    ("Lark's own denial message", "DriveNodePermNotAllow"),
    ("the not-found code", "1254702"),
    ("the not-found message", "DriveNodeNotExist"),
    ("the banked capture", "002-copy-app-unreachable-folder.json"),
    ("the send's date", "2026-08-18"),
    ("the one-send scope", "one send"),
    ("no retries", "no retries"),
    ("the token class", "tenant_access_token"),
]


@pytest.mark.conformance
@pytest.mark.parametrize("element, needle", THREE_OUTCOME_ELEMENTS)
def test_ld510_the_DOCSTRING_carries_the_three_outcome_truth(element, needle):
    assert needle in _norm(COPY_DOC), element


@pytest.mark.conformance
@pytest.mark.parametrize("element, needle", THREE_OUTCOME_ELEMENTS)
def test_ld510_the_PACKAGED_GUIDE_carries_it_too(element, needle):
    assert needle in _norm(larkdocio.guide(full=True)), element


@pytest.mark.conformance
def test_ld510_the_ONE_SEND_scope_is_stated_and_NOT_generalised():
    """Boundary 1. One send establishes that the codes come apart *here*. A text that made it a
    mapping would be claiming what nobody measured — the exact defect D-59 exists to prevent."""
    for text in (_norm(COPY_DOC), _norm(larkdocio.guide(full=True))):
        lowered = text.lower()
        assert "not a general mapping" in lowered
        assert "another route" in lowered and "user_access_token" in lowered


@private_tree.register
@pytest.mark.conformance
def test_ld510_LD387s_measurement_is_NOT_restated_re_scoped_or_weakened():
    """Boundary 2. Parts 2 and 3 of the three-outcome truth rest on ``ld387-01``; this change
    added a third part beside it and touched neither the probe citation nor its wording."""
    assert "ld387-01" in _norm(COPY_DOC)
    matrix = _norm((REPO_ROOT / "BASE.md").read_text(encoding="utf-8"))
    assert "probe `ld387-01`" in matrix
    assert "`tests/captures/base-study/captures/ld387-01-copy-folder-token.json`" in matrix
    register = _norm((REPO_ROOT / "requirements/DECISIONS.md").read_text(encoding="utf-8"))
    assert "probe `ld387-01`" in register


@private_tree.register
@pytest.mark.conformance
def test_ld510_the_UNMEASURED_PLACEMENT_concession_survives_IN_SUBSTANCE():
    """Boundary 3. The half LD-387 could not measure — placement into a folder that is **not**
    the default destination — is still *unmeasured, not refuted*, with the reason (the only
    addressable folder on the measuring tenant was the app's own root) intact. A rewrite that
    quietly dropped it would have broken the issue; this is the assertion that says so."""
    assert "placement into a folder that is not the default destination" in _norm(COPY_DOC)
    assert "the only addressable folder was the app's own root" in _norm(COPY_DOC)
    matrix = _norm((REPO_ROOT / "BASE.md").read_text(encoding="utf-8"))
    assert ("*placement into a folder that is not the default* is **unmeasured, not refuted**"
            in matrix)
    register = _norm((REPO_ROOT / "requirements/DECISIONS.md").read_text(encoding="utf-8"))
    assert "**unmeasured, not refuted**" in register
    guide = _norm(larkdocio.guide(full=True))
    assert "What was **not** measured is a folder other than the app's own root" in guide
    assert "untested, not broken" in guide


@pytest.mark.conformance
@pytest.mark.parametrize("where, text_of", [
    ("the docstring", lambda: _norm(COPY_DOC)),
    ("the packaged guide", lambda: _norm(larkdocio.guide(full=True))),
])
def test_ld510_a_CALLER_FACING_instruction_appears_where_a_caller_acts(where, text_of):
    """The reason the correction is worth shipping at all: the two codes call for two different
    actions, and a reader told the route *cannot* tell them apart has no reason to look."""
    text = text_of()
    assert "Check the code you actually got" in text or "check the code you actually got" in text
    assert "ask a workspace administrator" in text
    assert "the token is wrong" in text


@pytest.mark.conformance
@pytest.mark.parametrize("where, text_of", [
    ("the docstring", lambda: _norm(COPY_DOC)),
    ("the packaged guide", lambda: _norm(larkdocio.guide(full=True))),
    ("the matrix", lambda: _norm((REPO_ROOT / "BASE.md").read_text(encoding="utf-8"))),
    ("the register",
     lambda: _norm((REPO_ROOT / "requirements/DECISIONS.md").read_text(encoding="utf-8"))),
])
@private_tree.register
def test_ld510_NO_TEXT_implies_the_library_WIDENS_OR_ASKS_FOR_A_SCOPE(where, text_of):
    """A grant is a Lark console action. The instruction tells a human to ask an administrator;
    it must never read as something the library does, and the sites that carry the instruction
    say the negative out loud."""
    text = text_of()
    lowered = text.lower()
    for forbidden in ("requests the scope", "escalates the scope", "will request access",
                      "grants itself the", "escalates its scope"):
        assert forbidden not in lowered, forbidden
    assert "grant is a lark console action" in lowered, where


# --------------------------------------------------------------------------- #
# LD-510 AC4 — the code is RECORDED for a later, lookup-only register, and the  #
# record is written in exactly ONE place.                                       #
# --------------------------------------------------------------------------- #

#: The chosen home, and the marker that makes it findable by the issue that builds the register.
REGISTER_RECORD_MARKER = "FOR THE ERROR-CODE REGISTER"


@private_tree.register
@pytest.mark.conformance
def test_ld510_the_1254701_record_is_DISCOVERABLE_with_everything_a_register_needs():
    register = (REPO_ROOT / "requirements/DECISIONS.md").read_text(encoding="utf-8")
    record = _norm(register.split(REGISTER_RECORD_MARKER, 1)[1].split("**Why.**", 1)[0])
    for element, needle in [
        ("the code", "1254701"),
        ("Lark's name for it", "DriveNodePermNotAllow"),
        ("its meaning", "is real and this application is not permitted on it"),
        ("its route", "POST /open-apis/bitable/v1/apps/:app_token/copy"),
        ("its evidence", "002-copy-app-unreachable-folder.json"),
        ("its verification label", "MEASURED"),
        ("what is NOT claimed", "not claimed"),
    ]:
        assert needle in record, element


@private_tree.citations
@pytest.mark.conformance
def test_ld510_the_record_is_written_ONCE_and_NO_REGISTER_IS_BUILT_HERE():
    """The record stays written ONCE, the register now EXISTS elsewhere, and it is lookup-only.

    **The node id is kept deliberately, and the name still reads true under its own scope**:
    *HERE* is LD-510's change, which did not build the register — this file's own precedent is
    that a superseded test keeps its node id and has its BODY moved to the new conclusion,
    because a renamed test is a removed test.

    **SUPERSEDED IN ITS CONCLUSION BY LD-531 (2026-08-20) — TRANSFORMED, NOT DELETED, AND THE
    REASON IS UNCHANGED.** What this test asserted before, verbatim: *"A second copy of a
    code's record is the duplication this round exists to remove, and the register itself is
    later work ruled lookup-only — so this change leaves a record, not a home for one: no new
    module, no lookup function, no fourth generated matrix."* Three limbs, and only ONE of them
    moves.

    * **"no second copy of a code's record"** — UNCHANGED and still asserted below. It is the
      whole reason LD-531 exists, and LD-531 is how it finally gets kept rather than merely
      promised: ``requirements/DECISIONS.md`` is still the one prose record, and the marker
      still appears in exactly two files.
    * **"lookup-only — no fourth generated matrix, no ``ERRORS.md``"** — UNCHANGED, still the
      Maintainer's standing ruling (2026-08-18), and still asserted below, now against the register
      that actually shipped rather than against its absence.
    * **"no new module, no lookup function" — THIS is the conclusion that moves, and it moves
      because it was spent by completion, not overturned.** LD-510 said *this change* leaves a
      record rather than a home for one; it named a later issue as the one that would build the
      home. That issue is LD-531, and the home is
      ``src/larkdocio/common/error_codes.py``. A guard that kept asserting the module's absence
      after the issue it was waiting for had landed would be asserting that the work was never
      done. So the negative becomes the positive it was holding a place for: the register must
      EXIST, and ``1254701``'s record must resolve through it.
    """
    corpus = sorted(REPO_ROOT.glob("*.md")) + sorted((REPO_ROOT / "src").rglob("*")) \
        + sorted((REPO_ROOT / "requirements").rglob("*.md")) \
        + sorted((REPO_ROOT / "tests").rglob("*.py"))
    written_in = [str(p.relative_to(REPO_ROOT)) for p in corpus
                  if p.is_file() and p.suffix in {".md", ".py"}
                  and REGISTER_RECORD_MARKER in p.read_text(encoding="utf-8")]
    assert written_in == ["requirements/DECISIONS.md",
                          "tests/test_base_copy_folder_route_scope.py"], written_in

    # The home LD-510 recorded FOR, now landed — and the record resolves through it.
    from larkdocio.common.error_codes import note_for

    note = note_for(1254701)
    assert note is not None, "the register the record was written for does not carry 1254701"
    assert note.label == "DriveNodePermNotAllow", note.label
    assert note.denial_class == "object-acl", (
        "1254701 is an OBJECT-ACL denial, not a scope denial — the distinction is the point")
    assert "002-copy-app-unreachable-folder.json" in note.evidence, note.evidence

    # Still LOOKUP-ONLY. The maintainer ruling is unchanged: no fourth generated matrix, no ERRORS.md,
    # and the register grew no projection of its own.
    assert not any("ERRORS.md" == p.name for p in REPO_ROOT.glob("*.md"))
    assert not any("ERRORS.md" == p.name
                   for p in (REPO_ROOT / "src/larkdocio").rglob("*.md"))
    import larkdocio
    payload_keys = set(larkdocio.capabilities())
    for fancy in ("error_codes", "errors", "error_registry"):
        assert fancy not in payload_keys, (
            f"capabilities() grew an {fancy!r} key — the ruling was LOOKUP-ONLY")
