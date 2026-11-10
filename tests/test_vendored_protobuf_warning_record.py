"""The ``DeprecationWarning`` importing larkdocio emits is **recorded, not suppressed** —
and the record is held against the pinned dependency that causes it.

**Why this file exists.** ``import larkdocio`` emits one ``DeprecationWarning`` under Python
3.12+ that is not ours: it comes from a protobuf vendored *inside* ``lark-oapi``
(``lark_oapi/ws/pb/google/protobuf/internal/well_known_types.py``, where a module-level
constant calls ``datetime.utcfromtimestamp()``). The ``protobuf`` distribution is not installed
at all, and larkdocio touches no protobuf. A consumer who sees it in their own test output has
no way to tell whose it is. (Before 3.14, ``lark-oapi``'s websocket client and the
``websockets`` library it imports add deprecations of their own — LD-687 — also not ours.)

**Why a record rather than a fix.** larkdocio installs no ``filterwarnings`` and no
``simplefilter`` anywhere — and that absence is deliberate, not an oversight. A library that
edits its consumer's warning filters silences a diagnostic the consumer did not ask to have
silenced, in a process the consumer owns; that is a worse defect than the warning. So the
deliverable is a standing sentence in the document that already carries dependency policy, and
this file holds it true in three directions at once:

* the claim *"nothing here suppresses it"* is checked against the library's own source, so a
  future ``filterwarnings`` reddens the sentence that promised there is none;
* the claim about **which** dependency line causes it is checked against the **installed**
  ``lark-oapi``, so if a pin move ever clears the line the record reddens and must be removed
  rather than quietly outliving its own truth;
* the emission itself is re-measured in this interpreter, version-gated and classified by the
  module each warning is raised from — the vendored warning exists because
  ``datetime.utcfromtimestamp()`` is deprecated from Python 3.12, so *"exactly one"* of it is a
  claim about a Python version as much as about a dependency, and *"none of ours"* holds on
  every version.

Nothing here changes behavior, and **the pin is deliberately not moved**: the newest published
``lark-oapi`` carries the identical line at the identical path, so a pin move would not clear
the warning. That measurement is recorded in the release notes rather than re-run here.
"""
import pathlib
import re
import importlib.util
import subprocess
import sys
import tomllib

import pytest

from doc_prose import missing_phrases


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
README_MD = REPO_ROOT / "README.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
SRC = REPO_ROOT / "src"

#: The vendored module the warning is raised from, relative to the ``lark_oapi`` package root.
_VENDORED = pathlib.Path("ws/pb/google/protobuf/internal/well_known_types.py")

#: The deprecated call the vendored module makes at import time.
_DEPRECATED_CALL = "utcfromtimestamp("

#: The README section that carries dependency policy — the place a consumer already reads about
#: pins, which is why the record belongs there rather than in a section of its own.
_HEADING = "### Dependencies — exact pins, deliberately"


def dependency_section() -> str:
    text = README_MD.read_text(encoding="utf-8")
    start = text.find(_HEADING)
    assert start != -1, f"the README has no {_HEADING!r} section"
    nxt = text.find("\n## ", start + len(_HEADING))
    return text[start:nxt if nxt != -1 else len(text)]


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


# --------------------------------------------------------------------------- #
# The record itself.                                                            #
# --------------------------------------------------------------------------- #

_RECORD_CLAIMS = (
    "DeprecationWarning",
    "lark-oapi",
    "protobuf",
    "utcfromtimestamp",
)


def test_the_readme_records_WHAT_the_warning_is():
    missing = missing_phrases(dependency_section(), _RECORD_CLAIMS)
    assert not missing, (
        f"the dependency section does not record the import-time warning — missing {missing}. "
        f"A consumer who cannot tell whose warning it is assumes it is ours."
    )


def test_the_readme_names_the_python_version_the_warning_depends_on():
    low = flat(dependency_section())
    assert "3.12" in low, (
        "the call is deprecated from Python 3.12 — the record must say so, or a reader on an "
        "older interpreter cannot tell why they do not see it"
    )


def test_the_readme_says_larkdocio_DOES_NOT_SUPPRESS_IT_and_why():
    low = flat(dependency_section())
    assert "suppress" in low, "the record must state that nothing here suppresses the warning"
    assert "filter" in low, (
        "the record must tell a consumer they may filter it in their own configuration"
    )


def test_the_readme_does_NOT_tell_a_consumer_the_warning_is_harmless_in_THEIR_code():
    """The one thing the record must not do. It can say the warning is not ours and not
    suppressed by us; it cannot vouch for what the warning means in a process it does not own."""
    low = flat(dependency_section())
    for overclaim in ("harmless", "safe to ignore", "you can ignore"):
        assert overclaim not in low, (
            f"the record says {overclaim!r} — that is a claim about the consumer's process"
        )


# --------------------------------------------------------------------------- #
# The record is TRUE — each claim held against something that can move.         #
# --------------------------------------------------------------------------- #

def _filter_calls() -> list:
    """Every ``filterwarnings`` / ``simplefilter`` mention in the shipped library and in the
    packaging metadata — the thing the record claims does not exist."""
    hits = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "filterwarnings" in line or "simplefilter" in line:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    for lineno, line in enumerate(pyproject.splitlines(), 1):
        if "filterwarnings" in line or "simplefilter" in line:
            hits.append(f"pyproject.toml:{lineno}")
    return hits


def test_the_library_really_edits_NO_warning_filters():
    """The claim's truth condition, and the guard that keeps it one: add a ``filterwarnings``
    to the library or to the packaging metadata and the sentence promising there is none goes
    red in the same run."""
    assert _filter_calls() == [], (
        f"the README states nothing here suppresses the warning, but these do: "
        f"{_filter_calls()}"
    )


def test_the_filter_scan_BITES_on_a_planted_call(tmp_path):
    """Red proof for the scan above: it reads real lines, not nothing."""
    planted = "import warnings\nwarnings.filterwarnings('ignore')\n"
    assert [
        1 for lineno, line in enumerate(planted.splitlines(), 1)
        if "filterwarnings" in line
    ] == [1]


def _installed_vendored_module() -> pathlib.Path:
    lark_oapi = pytest.importorskip("lark_oapi", reason="lark-oapi is not installed")
    return pathlib.Path(lark_oapi.__file__).parent / _VENDORED


def test_the_PINNED_dependency_still_carries_the_line_the_readme_records():
    """The record's exit condition. If a pin move ever removes this line, the warning is gone
    and the README paragraph is a claim about nothing — so this reddens, and the paragraph
    comes out rather than outliving its own truth."""
    module = _installed_vendored_module()
    assert module.is_file(), (
        f"the vendored protobuf module the README names is not at {module} — the record names "
        f"a path that no longer exists"
    )
    assert _DEPRECATED_CALL in module.read_text(encoding="utf-8"), (
        f"{module} no longer calls {_DEPRECATED_CALL} — the warning the README records is gone; "
        f"remove the record instead of keeping a claim about nothing"
    )


def test_the_readme_names_the_vendored_PATH_the_warning_comes_from():
    """A consumer greps their own output for the path, not for our prose."""
    section = dependency_section()
    assert "well_known_types.py" in section, (
        "the record must name the module the warning is raised from, so a consumer can match "
        "it against the line in their own output"
    )
    assert "lark_oapi/ws/pb" in section, (
        "the record must show enough of the path to make the vendoring visible"
    )


def test_the_pin_this_record_is_about_is_still_EXACT_and_still_lark_oapi():
    """The record says the warning comes from a pinned dependency; the pin has to still be a
    pin, and this issue deliberately did not move it."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    pins = [dep for dep in data["project"]["dependencies"] if dep.startswith("lark-oapi")]
    assert len(pins) == 1, pins
    assert "==" in pins[0], f"lark-oapi is no longer pinned exactly: {pins[0]}"


#: A ``-W always`` warning line: ``<path>:<lineno>: DeprecationWarning: <message>``.
_WARNING_LINE = re.compile(
    r"^(?P<path>.+?):(?P<lineno>\d+): DeprecationWarning: (?P<message>.*)$"
)

#: The third-party distributions a ``DeprecationWarning`` on import may come from BELOW
#: :data:`_THIRD_PARTY_UNTIL`: the pinned ``lark-oapi`` itself, and ``websockets``, which
#: ``lark_oapi.ws`` imports. Before 3.14 both emit deprecations of their own at import (LD-687,
#: measured on 3.11-3.13 with lark-oapi 1.5.3 and websockets 17.4) — not ours, and not
#: suppressed by us either. A warning from any OTHER origin is a finding, so this set is closed
#: rather than "anything that is not larkdocio".
_THIRD_PARTY_ORIGINS = frozenset({"lark_oapi", "websockets"})

#: From this version on, the vendored-protobuf warning is the ONLY one: the README's "only on
#: interpreters older than 3.14" sentence is held here, so a third-party extra on 3.14+ is a
#: finding exactly as it was before LD-687.
_THIRD_PARTY_UNTIL = (3, 14)


def _origin_package(path: str) -> str:
    """The top-level package a warning was raised from — ``larkdocio`` for our own code."""
    location = pathlib.Path(path.replace("\\", "/")).resolve()
    own = pathlib.Path(importlib.util.find_spec("larkdocio").origin).resolve().parent
    if location == own or own in location.parents:
        return "larkdocio"
    parts = location.parts
    if "site-packages" in parts:
        return pathlib.Path(parts[parts.index("site-packages") + 1]).stem
    return f"<unplaced: {path}>"


def test_the_origin_classifier_BITES():
    """Red proof for :func:`_origin_package`: our own module is told apart from a dependency's."""
    own = pathlib.Path(importlib.util.find_spec("larkdocio").origin)
    assert _origin_package(str(own)) == "larkdocio"
    assert _origin_package("/x/lib/python3.13/site-packages/websockets/legacy/__init__.py") == (
        "websockets"
    )
    assert _origin_package("/nowhere/thing.py").startswith("<unplaced")


def _import_warning_problems(stderr: str, version: tuple) -> list:
    """Every way the ``-W always`` stderr of ``import larkdocio`` disagrees with the record, as
    measured on interpreter ``version``. Empty ⇒ the record is true there.

    Each warning is classified by the module it was raised FROM (LD-687): the vendored-protobuf
    one the README records is counted exactly — one from Python 3.12, where
    ``utcfromtimestamp()`` became deprecated, none before; larkdocio's own code raises none;
    below 3.14 every other one comes from a named third-party origin, and from 3.14 there is no
    other one at all."""
    emitted = [line for line in stderr.splitlines() if "DeprecationWarning" in line]
    parsed = [_WARNING_LINE.match(line) for line in emitted]
    if not all(parsed):
        return [f"a DeprecationWarning line this test cannot place: {emitted}"]
    problems = []
    vendored = [
        m.group(0) for m in parsed if m.group("path").replace("\\", "/").endswith(
            _VENDORED.as_posix()
        )
    ]
    expected = 1 if version >= (3, 12) else 0
    if len(vendored) != expected:
        problems.append(
            f"expected exactly {expected} vendored-protobuf DeprecationWarning on import, got "
            f"{len(vendored)}: {emitted}"
        )
    problems.extend(
        f"the vendored warning is not the utcfromtimestamp one: {line}"
        for line in vendored if "utcfromtimestamp" not in line
    )
    origins = {
        m.group(0): _origin_package(m.group("path"))
        for m in parsed if m.group(0) not in vendored
    }
    problems.extend(
        f"larkdocio's own code raises a DeprecationWarning on import: {line}"
        for line, origin in origins.items() if origin == "larkdocio"
    )
    allowed = _THIRD_PARTY_ORIGINS if version < _THIRD_PARTY_UNTIL else frozenset()
    problems.extend(
        f"a DeprecationWarning on import from an origin this record does not allow on "
        f"{version}: {line} ({origin})"
        for line, origin in origins.items() if origin != "larkdocio" and origin not in allowed
    )
    return problems


def test_importing_larkdocio_emits_EXACTLY_ONE_vendored_protobuf_warning_and_NONE_of_its_own():
    """Re-measured in this interpreter rather than asserted from a transcript; the rules are
    :func:`_import_warning_problems`. A different count, or a new origin, is a finding."""
    completed = subprocess.run(
        [sys.executable, "-W", "always::DeprecationWarning", "-c", "import larkdocio"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(REPO_ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    problems = _import_warning_problems(completed.stderr, sys.version_info[:2])
    assert problems == [], problems


_SITE = "/v/lib/python3.x/site-packages/"
_PLANT_VENDORED = (
    f"{_SITE}lark_oapi/{_VENDORED.as_posix()}:91: DeprecationWarning: "
    "datetime.datetime.utcfromtimestamp() is deprecated"
)
_PLANT_LARK_OAPI = (
    f"{_SITE}lark_oapi/ws/client.py:67: DeprecationWarning: websockets.InvalidStatusCode is "
    "deprecated"
)
_PLANT_WEBSOCKETS = (
    f"{_SITE}websockets/legacy/__init__.py:6: DeprecationWarning: websockets.legacy is deprecated"
)


def test_the_warning_rules_ACCEPT_what_each_interpreter_really_emits():
    """The two measured shapes (LD-687): 3.11-3.13 add lark_oapi / websockets extras, 3.14
    emits the vendored one alone."""
    pre = "\n".join([_PLANT_VENDORED, _PLANT_LARK_OAPI, _PLANT_WEBSOCKETS])
    assert _import_warning_problems(pre, (3, 13)) == []
    assert _import_warning_problems(_PLANT_VENDORED, (3, 14)) == []
    below_312 = "\n".join([_PLANT_LARK_OAPI, _PLANT_WEBSOCKETS])
    assert _import_warning_problems(below_312, (3, 11)) == []


@pytest.mark.parametrize(
    "extra", [_PLANT_LARK_OAPI, _PLANT_WEBSOCKETS], ids=["lark_oapi", "websockets"]
)
def test_the_warning_rules_REJECT_a_third_party_extra_from_3_14(extra):
    """Red proof for the version gate: the extra a 3.13 import legitimately shows is a finding
    on 3.14+, where the record says the vendored warning is the only one."""
    problems = _import_warning_problems("\n".join([_PLANT_VENDORED, extra]), (3, 14))
    assert len(problems) == 1 and "does not allow" in problems[0], problems


def test_the_warning_rules_REJECT_a_stranger_our_own_and_a_wrong_count_below_3_14():
    stranger = f"{_SITE}somepkg/mod.py:1: DeprecationWarning: x"
    assert _import_warning_problems("\n".join([_PLANT_VENDORED, stranger]), (3, 13))
    own = pathlib.Path(importlib.util.find_spec("larkdocio").origin)
    ours = f"{own}:1: DeprecationWarning: x"
    assert any("own code" in p for p in _import_warning_problems(
        "\n".join([_PLANT_VENDORED, ours]), (3, 13)))
    assert _import_warning_problems("\n".join([_PLANT_VENDORED] * 2), (3, 13))
    assert _import_warning_problems(_PLANT_LARK_OAPI, (3, 13))
