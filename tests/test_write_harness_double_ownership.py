"""LD-212 — the guard that holds ``tests/write_harness.py``'s "one place" claim TRUE.

The harness has said since LD-088 that "a change to a payload shape or the transport
doubles is edited in exactly **one** place". The tree falsified that sentence nine
times over: ``_FakeHTTPResponse`` had **nine** module-level definitions (one sha256
across all nine), ``FakeClock`` eight, ``StubOpener`` nine — and copy #9 of
``_FakeHTTPResponse``/``StubOpener`` landed with LD-186 within twenty-four hours of
the refactor audit measuring eight.

This module is the permanent net. It reads the inventory **off the harness itself**
(``write_harness.OWNED_DOUBLES`` / ``write_harness.DECLARED_DIVERGENT``) rather than
typing it a second time, and AST-walks ``tests/**`` — the same detection method the
audit used to find the copies — so:

* an **owned** name may have exactly ONE module-level definition in ``tests/**``, and
  it must be the harness's;
* a **declared-divergent** name's site inventory must match the harness's declaration
  exactly, so a NEW copy reddens too — the divergence is a recorded decision, not a
  licence to keep copying.

Deliberately NOT a regex over source text: a class named in a docstring, a comment or
a string literal is not a definition, and a genuinely test-local double defined inside
a function body is not the failure this guard exists to stop (§ the harness docstring
records that ruling).
"""
import ast
import pathlib

import pytest

import write_harness

TESTS_DIR = pathlib.Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# the scanner — an AST walk, parameterized on a root so it can be bite-tested  #
# --------------------------------------------------------------------------- #

def module_level_definitions(root, names):
    """Map each name in ``names`` → the list of ``(relpath, lineno)`` **module-level**
    ``ClassDef``/``FunctionDef`` definitions of that name under ``root``/``**.py``.

    Only the module body is inspected: a definition nested inside a function or a
    class is not a module-level double, and a mere textual mention is not a
    definition at all (this is an AST walk, never a text grep).

    **A file that vanishes between the glob and the read is skipped, not an error**
    (LD-359). ``sorted(rglob(...))`` is materialised in full and only then read, so
    a file deleted inside that window would raise ``FileNotFoundError`` from a guard
    with nothing to say about it — and under ``-n auto`` other workers are running
    while this walk happens. A file that is already gone cannot hold a
    double-ownership violation, so the skip loses no coverage; the same ruling
    ``front_door.argv_literal_sites`` records for the same reason.
    """
    root = pathlib.Path(root)
    found = {name: [] for name in names}
    for path in sorted(root.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:      # transient, deleted mid-walk — see above
            continue
        tree = ast.parse(source)
        for node in tree.body:          # module level ONLY — no recursion
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in found:
                    found[node.name].append((str(path.relative_to(root)), node.lineno))
    return found


def _sites(pairs):
    return sorted({rel for rel, _ in pairs})


def _cited(pairs):
    return ", ".join(f"{rel}:{line}" for rel, line in sorted(pairs))


# --------------------------------------------------------------------------- #
# AC5 — the owned names have exactly one definition, and it is the harness's    #
# --------------------------------------------------------------------------- #

def test_the_harness_declares_its_inventory_itself():
    """The owned/divergent sets are read off the harness — not typed here twice."""
    assert write_harness.OWNED_DOUBLES, "the harness must declare what it owns"
    for name in write_harness.OWNED_DOUBLES:
        assert hasattr(write_harness, name), (
            f"write_harness claims to own {name!r} but does not define it"
        )
    overlap = set(write_harness.OWNED_DOUBLES) & set(write_harness.DECLARED_DIVERGENT)
    assert not overlap, f"a name cannot be both owned and declared-divergent: {overlap}"


@pytest.mark.parametrize("name", sorted(write_harness.OWNED_DOUBLES))
def test_an_owned_double_has_exactly_one_definition_in_the_tree(name):
    found = module_level_definitions(TESTS_DIR, write_harness.OWNED_DOUBLES)[name]
    assert len(found) == 1, (
        f"{name} is owned by tests/write_harness.py, so exactly ONE module-level "
        f"definition may exist under tests/ — found {len(found)}: {_cited(found)}. "
        f"Import it from write_harness instead of re-authoring it."
    )
    (rel, _line) = found[0]
    assert rel == "write_harness.py", (
        f"{name}'s one definition must live in tests/write_harness.py, not {rel}"
    )


# --------------------------------------------------------------------------- #
# AC5(b) — a declared divergence is an exact, guarded inventory                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(write_harness.DECLARED_DIVERGENT))
def test_a_declared_divergent_name_matches_its_recorded_inventory(name):
    record = write_harness.DECLARED_DIVERGENT[name]
    found = module_level_definitions(TESTS_DIR, list(write_harness.DECLARED_DIVERGENT))[name]
    declared = sorted(record["sites"])
    actual = _sites(found)
    assert actual == declared, (
        f"{name} is DELIBERATELY left duplicated (reason: {record['reason']}), and the "
        f"harness records the exact site list. The tree no longer matches it.\n"
        f"  declared: {declared}\n  actual:   {actual}\n"
        f"  definitions: {_cited(found)}\n"
        f"Either import the harness's flavour, or — if the new site is genuinely "
        f"divergent too — add it to write_harness.DECLARED_DIVERGENT with its reason."
    )
    assert "write_harness.py" in actual, (
        f"{name} is declared divergent but the harness keeps no flavour of it"
    )


def test_the_harness_docstring_cannot_be_silently_false():
    """The one-place claim must name its guard and each declared divergence."""
    doc = write_harness.__doc__
    assert "test_write_harness_double_ownership" in doc, (
        "the harness's one-place claim must cite the guard that holds it"
    )
    for name in write_harness.DECLARED_DIVERGENT:
        assert name in doc, (
            f"{name} is left duplicated on purpose — the docstring must say so by name"
        )


# --------------------------------------------------------------------------- #
# AC5 — the guard BITES a planted tenth copy, naming file and line              #
# --------------------------------------------------------------------------- #

def test_a_planted_tenth_copy_is_reported_by_file_and_line(tmp_path):
    (tmp_path / "write_harness.py").write_text(
        "class _FakeHTTPResponse:\n    pass\n"
    , encoding="utf-8")
    (tmp_path / "test_some_new_family.py").write_text(
        "import json\n"
        "\n"
        "\n"
        "class _FakeHTTPResponse:\n"
        "    def __init__(self, payload):\n"
        "        self._b = json.dumps(payload).encode()\n"
    , encoding="utf-8")
    found = module_level_definitions(tmp_path, ["_FakeHTTPResponse"])["_FakeHTTPResponse"]
    assert len(found) == 2
    assert ("test_some_new_family.py", 4) in found
    assert "test_some_new_family.py:4" in _cited(found)


# --------------------------------------------------------------------------- #
# AC6 — the guard cannot cry wolf                                              #
# --------------------------------------------------------------------------- #

def test_the_harness_own_definition_is_the_one_legal_copy(tmp_path):
    (tmp_path / "write_harness.py").write_text("class FakeClock:\n    pass\n", encoding="utf-8")
    found = module_level_definitions(tmp_path, ["FakeClock"])["FakeClock"]
    assert found == [("write_harness.py", 1)]


def test_a_double_nested_in_a_function_body_does_not_bite(tmp_path):
    """A genuinely test-local double is not the failure this guard exists to stop."""
    (tmp_path / "test_local.py").write_text(
        "def test_something():\n"
        "    class FakeClock:\n"
        "        now = 0.0\n"
        "\n"
        "    assert FakeClock.now == 0.0\n"
    , encoding="utf-8")
    assert module_level_definitions(tmp_path, ["FakeClock"])["FakeClock"] == []


def test_a_mere_mention_in_a_docstring_or_comment_does_not_bite(tmp_path):
    (tmp_path / "test_prose.py").write_text(
        '"""Talks about FakeClock and class _FakeHTTPResponse: in prose."""\n'
        "# class CountingTransport:  <- a commented-out copy is not a definition\n"
        'MENTION = "class FakeClock:"\n'
    , encoding="utf-8")
    found = module_level_definitions(
        tmp_path, ["FakeClock", "_FakeHTTPResponse", "CountingTransport"]
    )
    assert found == {"FakeClock": [], "_FakeHTTPResponse": [], "CountingTransport": []}


# --------------------------------------------------------------------------- #
# LD-359 — a file that vanishes between the glob and the read is SKIPPED        #
# --------------------------------------------------------------------------- #
# `sorted(root.rglob("*.py"))` is materialised in full and only then read, so
# any file deleted inside that window raises FileNotFoundError from a guard that
# has nothing to say about it. LD-353's probe module was the observed instance
# (2 reds in 2 `verify.sh` runs); it now lives outside the repo, but the window
# belongs to the scanner, so the scanner closes it. A file that is gone by the
# time it is read cannot hold a double-ownership violation, so skipping it loses
# no coverage — the same ruling `front_door.argv_literal_sites` already records.


def test_a_file_deleted_between_the_glob_and_the_read_is_skipped(tmp_path, monkeypatch):
    """Force the exact interleaving: the transient is unlinked while the walk is
    parsing the file that sorts ahead of it, i.e. after the glob, before its read."""
    (tmp_path / "aaa_first.py").write_text("class FakeClock:\n    pass\n", encoding="utf-8")
    transient = tmp_path / "probe_zzz_transient.py"
    transient.write_text("class FakeClock:\n    pass\n", encoding="utf-8")

    real_parse = ast.parse

    def parse_then_vanish(source, *args, **kwargs):
        transient.unlink(missing_ok=True)      # mid-walk, exactly as xdist does it
        return real_parse(source, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", parse_then_vanish)
    found = module_level_definitions(tmp_path, ["FakeClock"])["FakeClock"]
    assert found == [("aaa_first.py", 1)], (
        "a file that vanished mid-walk must be skipped, not crash the scan"
    )


def test_a_dangling_symlink_does_not_crash_the_scan(tmp_path):
    """The same vanish, with no monkeypatching: the entry is listed by the glob and
    is unreadable by the time it is opened."""
    (tmp_path / "write_harness.py").write_text("class FakeClock:\n    pass\n", encoding="utf-8")
    (tmp_path / "probe_gone.py").symlink_to(tmp_path / "never_existed.py")
    assert module_level_definitions(tmp_path, ["FakeClock"])["FakeClock"] == [
        ("write_harness.py", 1)
    ]


def test_the_live_gate_harness_is_not_folded_in():
    """``tests/sheets_write_harness.py`` is a DIFFERENT module with a different job.

    It holds the credential-carrying live-gate arms (``pytest -m live_write``); it is
    explicitly out of T4's scope and must never be reported by this guard.
    """
    live_harness = TESTS_DIR / "sheets_write_harness.py"
    assert live_harness.exists(), "the live-gate harness moved — re-point this guard"
    names = list(write_harness.OWNED_DOUBLES) + list(write_harness.DECLARED_DIVERGENT)
    found = module_level_definitions(TESTS_DIR, names)
    offenders = {
        name: pairs
        for name, pairs in found.items()
        if any(rel == "sheets_write_harness.py" for rel, _ in pairs)
    }
    assert not offenders, (
        f"the live-gate harness is out of scope but defines: {sorted(offenders)}"
    )
