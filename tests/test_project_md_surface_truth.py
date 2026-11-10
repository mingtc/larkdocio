"""PROJECT.md's surface descriptions, bound to the code (LD-645).

**Why this file exists.** `PROJECT.md` § "What larkdocio is" is a prose restatement of the
census — and it is the file `CLAUDE.md` orders every session to read FIRST, so an architect
carries its sentences into a plan. It was outside every doc-truth guard: `cli.py`, `README.md`
and `DRIVE.md` sit in guarded corpora and were correct, while `PROJECT.md` said **three** of
the Drive write legs were verified by a read-back (two are), and credited `contacts/` with the
open-id → display-name lookup that lives on the read client. Both survived because nothing
grepped this file except the consent-fence text. **A repeat of that defect must not be free.**

**The shape, borrowed from `tests/test_front_door_doctrine.py`.** Nothing here pins a wording:
each check derives its expectation from `capabilities(full=True)` or from the module that owns
the fact, and asks whether the paragraph still states *that*. A rewrite may word it however it
likes; what reddens is a re-frozen count, an unresolvable symbol, or a file type the code
accepts and the prose omits.

**Not born vacuous.** Every check asserts its population is non-empty before it asserts
anything about the prose (the `EmptyRegistry` arm in `scripts/heading_index.py` is the
precedent), so a guard that stops finding anything to check fails loudly instead of passing.
"""
import re
from pathlib import Path

import pytest

import front_door as fd
from larkdocio import capabilities
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_MD = REPO_ROOT / "PROJECT.md"

#: The number words this file's prose may spell. Anything above ten in a surface claim wants
#: a derived figure rather than a word.
_NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


def _project_md() -> str:
    return PROJECT_MD.read_text(encoding="utf-8")


def _surfaces_section() -> str:
    """The `## What larkdocio is` section — the bullet list that restates the census."""
    text = _project_md()
    marker = "\n## What larkdocio is\n"
    assert marker in text, "PROJECT.md no longer has a 'What larkdocio is' section"
    body = text.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def _bullets() -> dict:
    """`{package name: bullet text}` for every `- **\\`x/\\` — shipped` bullet in the section."""
    out, current = {}, None
    for line in _surfaces_section().splitlines():
        started = re.match(r"- \*\*`([a-z_]+)/`", line)
        if started:
            current = started.group(1)
            out[current] = line
        elif current and line.startswith("  "):
            out[current] += "\n" + line
        elif line.startswith("- "):
            current = None
    return out


@pytest.fixture(scope="module")
def surfaces():
    return capabilities(full=True)["surfaces"]


# --------------------------------------------------------------------------- #
# The section is found at all — the arm that keeps every check below honest.    #
# --------------------------------------------------------------------------- #

@private_tree.process
def test_the_bullet_population_is_NOT_EMPTY_and_covers_the_packages_named_here():
    bullets = _bullets()
    assert bullets, (
        "no `- **`pkg/` — ...` bullets were parsed out of PROJECT.md § What larkdocio is; "
        "either the section was restructured or this guard stopped seeing it — re-read the "
        "parser before deleting a check that now has nothing to check"
    )
    for required in ("drive", "comments", "read"):
        assert required in bullets, f"the {required!r} bullet vanished from PROJECT.md"


# --------------------------------------------------------------------------- #
# AC1's answer, held in the file that stated it wrong.                          #
# --------------------------------------------------------------------------- #

#: THE SPLIT HAS ONE AUTHORING, and it is not here. ``front_door.drive_verification_split``
#: derives it from the census for the README guard as well; a second definition of *which legs
#: verify* is the same defect as a second count of them, one layer down. It also REFUSES on a
#: Drive contract nobody has classified rather than defaulting it to "does not verify".
_split = fd.drive_verification_split


#: The constructions in which a number word is COUNTING THE LEGS rather than counting
#: something else — *"one call and only one"* is about a call, not about the four legs, and a
#: guard that cannot tell the two apart is a guard nobody can write true prose under.
#:
#: **NARROWED after review, and the narrowing is the point.** The first pattern used to be a
#: bare ``all <word>``, which read *"`grant_access` / `update_access` / `revoke_access` — all
#: three read the member list back"* — a TRUE, code-accurate sentence — as a claim that three
#: legs exist, and turned red on it. Every pattern is now bound to its SUBJECT: the counted
#: noun must be the legs (named or elided into the split's own two verbs), never whatever word
#: happens to follow a number. A guard that forbids correct writing gets weakened until it
#: guards nothing, so it is better for one to be narrow and trusted.
_COUNTING = (
    # "all four are direct calls", "all four write legs", "all four of them" — the counted
    # noun must be the legs or the split's own copula, so "all three READ …" is not a count.
    r"\ball\s+(?:\*\*)?(\w+)(?:\*\*)?(?=\s+(?:(?:write\s+)?legs\b|are\b|of\s+them\b))",
    # "three of them", "two of the four legs"
    r"\b(\w+)(?:\*\*)?\s+of\s+(?:them\b|the\s+(?:\w+\s+)?(?:write\s+)?legs\b)",
    # "four write legs", "the four legs"
    r"\b(\w+)\s+(?:write\s+)?legs\b",
    # the split statement itself, whose subject is elided: "two verify in-library", "two do not"
    r"\b(\w+)(?:\*\*)?\s+verify\s+in-library\b",
    r"\b(\w+)(?:\*\*)?\s+do\s+not\b",
)


def _counting_words(text: str) -> set:
    words = set()
    for pattern in _COUNTING:
        words |= set(re.findall(pattern, text.lower()))
    return {w for w in words if w in set(_NUMBER_WORDS.values())}


@private_tree.process
def test_the_drive_bullet_spells_only_the_DERIVED_counts(surfaces):
    """The defect itself: *"three of them are ... verified by an independent read-back"* over
    an enumeration of four legs, of which two verify. Every number word in the bullet must be
    one the census can produce — the total, the verified count, or the unverified count."""
    legs, verified, unverified = _split(surfaces)
    assert legs, "no Drive write surfaces at all; the bullet's whole subject is gone"
    assert verified and unverified, (
        "the verified/unverified split collapsed to one side — the bullet's 'stated per leg' "
        "shape may no longer be the right shape; re-read it rather than re-pointing this guard"
    )
    allowed = {_NUMBER_WORDS[len(legs)], _NUMBER_WORDS[len(verified)],
               _NUMBER_WORDS[len(unverified)]}
    found = _counting_words(_bullets()["drive"])
    assert found, (
        "the drive bullet states no count of the legs at all where it used to state a "
        "split; a paragraph that stopped counting is not what this guard was written for"
    )
    assert found <= allowed, (
        f"PROJECT.md's drive bullet spells {sorted(found - allowed)}, which the census does "
        f"not produce: {len(legs)} write legs, {len(verified)} verified in-library "
        f"({sorted(verified)}), {len(unverified)} not ({sorted(unverified)})"
    )


@private_tree.process
def test_every_drive_write_leg_is_NAMED_in_the_bullet_by_one_of_its_own_ops(surfaces):
    """Bidirectional the way it matters: a fifth Drive write leg reddens this file until the
    paragraph accounts for it, and a leg that loses its op name here reddens too."""
    legs, _verified, _unverified = _split(surfaces)
    bullet = _bullets()["drive"]
    for sid, spec in legs.items():
        names = [op["name"] for op in spec.get("operations") or ()]
        assert names, f"{sid} publishes no operations; the projection changed shape"
        assert any(name in bullet for name in names), (
            f"PROJECT.md's drive bullet names no operation of {sid} — a reader cannot tell "
            f"which leg the verification sentence is about. Its ops: {names}"
        )


@private_tree.process
def test_no_drive_write_leg_is_called_PLAN_GATED_here(surfaces):
    """The other half of the same sentence: none of these legs carries the plan gate, so the
    bullet may not borrow the word. Derived, so shipping a gated Drive leg frees the word."""
    legs, _v, _u = _split(surfaces)
    assert legs, (
        "no Drive write surfaces at all — with an empty population this arm passes without "
        "checking anything, which is the one thing this file's docstring forbids"
    )
    gated = {sid for sid, spec in legs.items()
             if "plan-gated" in (spec.get("safety_contracts") or ())}
    if not gated:
        assert not re.search(r"are\s+plan-gated", _bullets()["drive"]), (
            "no Drive write leg declares plan-gated, so the bullet must not say they are"
        )


# --------------------------------------------------------------------------- #
# The peripherals paragraph — the half that was attributed to the wrong module. #
# --------------------------------------------------------------------------- #

@private_tree.process
def test_every_backticked_dotted_SYMBOL_in_the_section_resolves(surfaces):
    """`contacts/` was credited with a lookup that lives on the read client. A claim written
    as a symbol is checkable, so every symbol claimed here is imported and resolved."""
    import importlib

    section = _surfaces_section()
    candidates = set(re.findall(r"`((?:[a-z_]+\.)+[A-Za-z_][A-Za-z_0-9.]*)`", section))
    symbols = {c for c in candidates if not c.endswith((".md", ".py", ".toml", ".json"))}
    assert len(symbols) >= 3, (
        f"only {len(symbols)} dotted symbol(s) found in PROJECT.md's surface section; this "
        f"guard is checking almost nothing — re-read the pattern before trusting it: {symbols}"
    )
    for dotted in sorted(symbols):
        parts = dotted.split(".")
        obj, resolved = None, False
        for split_at in range(len(parts), 0, -1):
            try:
                obj = importlib.import_module("larkdocio." + ".".join(parts[:split_at]))
            except ImportError:
                continue
            resolved = True
            break
        assert resolved, f"PROJECT.md names `{dotted}`, which is not a larkdocio module path"
        for attr in parts[split_at:]:
            assert hasattr(obj, attr), (
                f"PROJECT.md names `{dotted}`, but {attr!r} does not exist on "
                f"{obj!r} — the attribution is wrong or the symbol moved"
            )
            obj = getattr(obj, attr)


@private_tree.process
def test_the_comments_bullet_names_EVERY_file_type_the_reader_accepts():
    """`comments()` branches on three `file_type` values; the bullet said two."""
    from larkdocio.comments import read as comments_read

    file_types = sorted(
        value for name, value in vars(comments_read).items()
        if name.startswith("FILE_TYPE_") and isinstance(value, str)
    )
    assert len(file_types) >= 2, (
        f"only {file_types} found; the FILE_TYPE_ constants moved and this guard would pass "
        f"on an empty claim"
    )
    bullet = _bullets()["comments"]
    missing = [ft for ft in file_types if f"`{ft}`" not in bullet]
    assert not missing, (
        f"PROJECT.md's comments/contacts bullet omits the file type(s) {missing} that "
        f"larkdocio.comments.read branches on"
    )


@private_tree.process
def test_the_contacts_bullet_names_the_FORWARD_verbs_that_actually_ship():
    """The two verbs `contacts/` does own, derived from the package's own exports."""
    import larkdocio.contacts as contacts

    forward = sorted(
        name for name in getattr(contacts, "__all__", dir(contacts))
        if name.startswith("resolve_")
    )
    assert forward, "larkdocio.contacts exports no resolve_* verb; the surface changed shape"
    bullet = _bullets()["comments"]
    missing = [name for name in forward if name not in bullet]
    assert not missing, (
        f"PROJECT.md's comments/contacts bullet does not name the shipped forward verb(s) "
        f"{missing} — the paragraph describes the package by something other than what it "
        f"exports, which is how the reverse lookup came to be credited here"
    )


# --------------------------------------------------------------------------- #
# The counting check's own bite proofs — both directions, as pure functions.    #
#                                                                              #
# Written after review refuted the first version BY MUTATION: a true sentence   #
# turned it red. The must-not-bite half is therefore not a footnote here, it is #
# half of what this guard is for.                                              #
# --------------------------------------------------------------------------- #

def test_the_counting_check_BITES_on_the_sentence_THAT_SHIPPED():
    """The defect itself, verbatim from PROJECT.md before this issue."""
    assert _counting_words(
        "**The walk is read-only; the write legs are not**, and three of them are direct "
        "calls verified by an independent read-back rather than plan-gated."
    ) == {"three"}


def test_the_counting_check_BITES_on_a_wrong_TOTAL_however_it_is_spelled():
    for wrong in ("all **three** are direct calls",
                  "the three write legs are direct calls",
                  "two of the three legs verify"):
        assert "three" in _counting_words(wrong), wrong


def test_the_counting_check_does_NOT_bite_on_TRUE_prose_about_something_else():
    """Each of these is code-accurate and counts something that is not the legs. The first is
    the sentence review used to refute the original pattern."""
    for legitimate in (
        "`grant_access` / `update_access` / `revoke_access` — all three read the member list "
        "back",
        "`create_folder` is one call with no read-back at all",
        "all three file types are accepted: `docx`, `sheet` and `bitable`",
    ):
        assert not _counting_words(legitimate), (
            f"the counting check rejects true prose: {legitimate!r}"
        )
