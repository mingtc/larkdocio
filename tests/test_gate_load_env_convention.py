"""LD-276 — every live gate must load ``.env`` at import, so its own per-file command works.

``tests/test_live_base_media_gate.py`` was the one live/live_write gate of 40+ that never called
``canary_support.load_env()`` at module import — the per-file command every gate's own
docstring prescribes (``pytest -m live_write tests/test_....py``) only resolved write
credentials because a **sibling** module's import-time side effect had already populated
``os.environ`` during collection. This guard scans every ``test_live_*.py`` gate module (the
``_offline.py`` companions carry no ``pytestmark`` and are excluded) for the
``canary_support.load_env()`` call, so the next gate cannot ship without it — a cheap,
repo-wide analogue of the file-scoped pin in ``test_live_base_media_gate_offline.py``.
"""
import re
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_LIVE_MARK = re.compile(r"^pytestmark\s*=\s*pytest\.mark\.(live|live_write)\b", re.MULTILINE)


def _live_gate_modules():
    for path in sorted(_TESTS_DIR.rglob("test_live_*.py")):  # LD-654: recursive population
        if path.name.endswith("_offline.py"):
            continue
        source = path.read_text(encoding="utf-8")
        if _LIVE_MARK.search(source):
            yield path, source


def test_every_live_gate_loads_env_at_import():
    offenders = [path.name for path, source in _live_gate_modules()
                 if "canary_support.load_env()" not in source]
    assert not offenders, (
        "every live/live_write gate must call canary_support.load_env() at module import so "
        "its own documented per-file pytest command resolves credentials without depending on "
        "a sibling module having run first (LD-276) — offenders: " + ", ".join(offenders)
    )


def test_the_guard_actually_found_gates_to_scan():
    """A regex that stopped matching anything would make the guard above vacuously green."""
    assert len(list(_live_gate_modules())) >= 40
