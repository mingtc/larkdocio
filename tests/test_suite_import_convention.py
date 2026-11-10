"""LD-273 — the suite's harness-import convention, enforced.

``tests/`` has no ``__init__.py``: it is not a real package, so ``from tests import
<module>`` only resolves as an accidental namespace-package import, and only when the repo
root happens to be on ``sys.path`` (true for ``python -m pytest``, false for the plain
``pytest`` entry script — see ``tests/conftest.py``'s own sys.path insert, which is what
makes the top-level form work under both). The suite's real convention, followed by every
sibling harness import, is the top-level form: ``import comments_harness as harness``. This
guard scans every test module's source for the package-style form and fails loudly if one
ever creeps back in — the exact defect that broke ``pytest -m live`` under the entry script.
"""
import re
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_BAD_IMPORT = re.compile(r"^\s*(from tests(\.\w+)? import |import tests(\.\w+)?\b)")


def test_no_package_style_tests_import():
    offenders = []
    for path in sorted(_TESTS_DIR.rglob("*.py")):  # LD-654: population must be recursive
        if path.name == Path(__file__).name:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _BAD_IMPORT.match(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "package-style 'from tests import ...' resolves only under `python -m pytest` "
        "(namespace-package accident); use the sibling convention instead "
        "(e.g. `import comments_harness as H`) — offenders: " + "; ".join(offenders)
    )
