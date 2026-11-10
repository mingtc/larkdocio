"""LD-700 (round 3 of the public-export review, T9) — ``TOOLS.md`` calls itself the CLI's schema,
so every long option click defines on the group and on every subcommand appears in it.

The README already carries this forward leg (``test_front_door_doctrine``'s AC5); ``TOOLS.md``
did not, and round 3 found it missing ``--deep-read-*``, ``--fidelity-read-sheets``,
``--local-time``, ``--assets`` and ``--version``. Derived from click, so a new option on any
command widens what the schema owes on its own.
"""
import re

import front_door as fd

TOOLS = fd.REPO_ROOT / "TOOLS.md"


def _documented(option, text):
    return re.search(r"(?<![\w-])" + re.escape(option) + r"(?![\w-])", text) is not None


def test_every_long_option_of_every_command_is_in_the_schema():
    text = TOOLS.read_text(encoding="utf-8")
    missing = {
        label: sorted(o for o in options if o.startswith("--") and not _documented(o, text))
        for label, options in fd.all_command_options().items()
    }
    missing = {label: gone for label, gone in missing.items() if gone}
    assert not missing, f"TOOLS.md is the CLI schema and omits: {missing}"


def test_the_check_bites_on_a_prefix_of_a_real_option():
    assert not _documented("--deep-read", "the --deep-read-sheets flag")
    assert _documented("--dump", "- `--dump` — flag")
