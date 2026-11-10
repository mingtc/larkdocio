"""LD-702 (U4) — every security-label value the library states in its own text is the placeholder.

The shipped text (``src/larkdocio`` — code, docstrings, constants and the packaged documents)
and the root matrices state one example label value, ``"Label A"``, and one empty value, ``""``
(no level set). This guard finds every quoted literal sitting in a sentence frame that states a
label value — *whether "X" is a stable id / a localised display string*, *read back "X"*,
*chose "X"*, *level.level -> "X"*, *a non-empty string ("X")*, *sec_label_name … reads "X"* —
in plain, backticked, emphasised or backslash-escaped quoting, and holds each to those two.
A runtime constant is read by callers, so it is held to the same rule as the guide.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDERS = {"Label A", ""}
_ROOT_DOCS = ("DRIVE.md", "BASE.md", "README.md")

_QUOTED = r'(?:``|`)?\*{0,2}\\?"([^"\\\n]{0,40})\\?"'
_FRAMES = (
    re.compile(_QUOTED + r'\*{0,2}(?:``|`)?\*{0,2}\s+is\s+(?:a\s+)?'
               r'(?:stable\s+id|localised\s+display\s+string)', re.I),
    re.compile(r'(?:read\s+back|chose|level\.level\s*->|non-empty\s+string\s*\()[\s`*(]*'
               + _QUOTED, re.I),
    re.compile(r'sec_label_name[^.\n]{0,120}?\breads\s+[\s`*]*' + _QUOTED, re.I),
)


#: A frame counts only in a passage about a level: "read back" is said of cell values too.
_ABOUT_A_LEVEL = re.compile(r"sec_label|security[ _]level|\blevel\b", re.I)


def stated_label_values(text):
    """Every ``(line, literal)`` a label-value frame in ``text`` quotes."""
    for frame in _FRAMES:
        for match in frame.finditer(text):
            if _ABOUT_A_LEVEL.search(text, max(0, match.start() - 400), match.end()):
                yield text.count("\n", 0, match.start()) + 1, match.group(1)


def _shipped_texts():
    for path in sorted((ROOT / "src" / "larkdocio").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".md"} and "__pycache__" not in path.parts:
            yield path
    for name in _ROOT_DOCS:
        yield ROOT / name


def test_the_frames_catch_every_quoting_form_a_label_value_is_written_in():
    """Regression cases, with invented values: each form must be seen."""
    cases = (
        'whether \\"Other Label\\" is a stable id or a localised display string',
        'whether **`"Other Label"` is a localised display string** rather than',
        'whether ``"Other Label"`` is a stable id',
        'it read back **`"Other Label"`**, against its own before control',
        'chose *"Other Label"* by hand',
        'level.level        -> "Other Label" — exactly what Lark said',
        '* ``level`` is a non-empty string (``"Other Label"``) — a level was reported',
        '`sec_label_name` on `POST /drive/v1/metas/batch_query` reads `"Other Label"` on a fixture',
    )
    for case in cases:
        found = [value for _, value in stated_label_values("Its security level: " + case)]
        assert found == ["Other Label"], case
    assert list(stated_label_values('a cell: write "row", read back "+10000000000"')) == []


def test_no_shipped_text_states_a_label_value_other_than_the_placeholder():
    offenders = []
    for path in _shipped_texts():
        text = path.read_text(encoding="utf-8")
        for line, value in stated_label_values(text):
            if value not in PLACEHOLDERS:
                offenders.append(f"{path.relative_to(ROOT)}:{line}: {value!r}")
    assert not offenders, offenders


def test_the_guard_sees_the_label_examples_it_exists_for():
    """A frame that silently matches nothing would pass the sweep above vacuously."""
    seen = {path.name for path in _shipped_texts()
            if any(v == "Label A" for _, v in stated_label_values(path.read_text("utf-8")))}
    assert {"GUIDE.md", "models.py", "client.py", "DRIVE.md"} <= seen, seen


#: LD-703 (round 5, V9): the TESTS state label values too — as a fixture's ``sec_label_name=``
#: and as the ``.level ==`` they assert back — and the sweep above never read ``tests/``. An
#: odd value a test needs (to prove nothing normalises it) is invented, from this set.
TEST_PLACEHOLDERS = PLACEHOLDERS | {"Other Label", "标签 B / Label B"}
_TEST_FRAMES = (
    re.compile(r"""sec_label_name["']?\s*[=:]\s*["']([^"'\n]{0,40})["']"""),
    re.compile(r"""\.level\s*==\s*["']([^"'\n]{0,40})["']"""),
)


def test_LD703_the_test_frames_read_a_fixture_value_and_an_asserted_level():
    text = 'client(sec_label_name="Some Label")\nassert x.level == "Some Label"\n'
    assert [m.group(1) for f in _TEST_FRAMES for m in f.finditer(text)] == ["Some Label"] * 2


def test_LD703_no_test_states_a_label_value_outside_the_placeholders():
    offenders = []
    for path in sorted((ROOT / "tests").glob("*.py")):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        for frame in _TEST_FRAMES:
            for match in frame.finditer(text):
                if match.group(1) not in TEST_PLACEHOLDERS:
                    offenders.append(f"{path.name}: {match.group(1)!r}")
    assert not offenders, offenders
