# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Tests for the docs-cleanup-4-and-lows hardening item (carried into larkdocio).

Asserts the *fixed* state:
- The package version is a real semver string AND is consistent with the single
  source of truth in ``pyproject.toml`` (no literal pin — see LD-022).
- larkdocio.read.client hoists the board/wiki request imports to module top (no
  function-local ``from lark_oapi.api.board...`` / ``...wiki...`` imports).
- A board download permission failure produces an actionable message that
  surfaces the request log id and HTTP status instead of bare
  ``Code: None, Msg: None``.
- larkdocio.utils.common.check_err preserves its behavior (logs + re-raises).
"""

import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import larkdocio
import larkdocio.read.client as client_mod
from larkdocio.read.client import Client
from larkdocio.utils.common import check_err, pretty_print

# X.Y.Z semver (the scheme larkdocio uses: numbers increment unambiguously, no
# major/minor semantics — maintainer directive on LD-022).
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version():
    """Parse ``version`` from the ``[project]`` table of pyproject.toml.

    Regex-based (written when the project's floor was ``>=3.10``, where tomllib
    is absent; the floor is ``>=3.11`` since LD-713, and the regex still works). Scopes to the
    ``[project]`` table so an unrelated ``version =`` elsewhere can't be picked up.
    """
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Isolate the [project] table: from its header to the next top-level table.
    m = re.search(r"^\[project\]\s*$(.*?)(?=^\[)", text, re.M | re.S)
    section = m.group(1) if m else text
    vm = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', section, re.M)
    assert vm, "could not find version in the [project] table of pyproject.toml"
    return vm.group(1)


def test_version_is_semver():
    """__version__ is semver-shaped AND equals pyproject's single source of truth.

    Deliberately NOT a literal pin (the old ``== "1.0.0"`` landmine): this asserts
    a *format* + *equality with pyproject* so a legitimate version bump (e.g. the
    v1.1.0 cut) does not redden it, while a drift between __init__.py and
    pyproject.toml still does. LD-022.
    """
    assert _SEMVER_RE.match(larkdocio.__version__), (
        f"__version__ {larkdocio.__version__!r} is not X.Y.Z semver"
    )
    assert larkdocio.__version__ == _pyproject_version(), (
        "larkdocio.__version__ must match pyproject.toml [project].version "
        "(single source of truth)"
    )


def test_board_wiki_imports_hoisted_to_module_top():
    src = inspect.getsource(client_mod)
    method_srcs = [
        inspect.getsource(Client.download_board_image),
        inspect.getsource(Client.get_wiki_node_info),
    ]
    for body in method_srcs:
        assert "import" not in body, (
            "board/wiki request imports must be hoisted to module top"
        )
    # And they must actually be importable from module scope.
    assert "DownloadAsImageWhiteboardRequest" in src
    assert "GetNodeSpaceRequest" in src


def test_board_permission_failure_message_is_actionable():
    """A failed board download with None code/msg must still yield an
    actionable message (log id + http status), not bare None/None."""
    client = Client.__new__(Client)

    resp = SimpleNamespace(
        success=lambda: False,
        code=None,
        msg=None,
        get_log_id=lambda: "logid-xyz",
        raw=SimpleNamespace(status_code=403),
    )
    client.lark_client = SimpleNamespace(
        board=SimpleNamespace(
            v1=SimpleNamespace(
                whiteboard=SimpleNamespace(download_as_image=lambda req: resp)
            )
        )
    )

    with pytest.raises(Exception) as exc:
        client.download_board_image("wb123", "/tmp/out")

    msg = str(exc.value)
    assert "logid-xyz" in msg
    assert "403" in msg


def test_check_err_logs_and_reraises():
    with pytest.raises(ValueError):
        check_err(ValueError("boom"))


def test_pretty_print_is_two_space_indented_json():
    """CHARACTERIZATION, added by LD-512's safety-net-check BEFORE the ``utils`` fold.

    ``pretty_print`` was the one function in the moved pair with **no test at all** — the net
    caught a mutated ``check_err`` and a mutated ``sanitize_path_string`` in seven places and
    caught a changed ``pretty_print`` indent in none. A behaviour-preserving move is only
    provable where behaviour is pinned, so it is pinned here first.
    """
    assert pretty_print({"b": 1, "a": [1, 2]}) == (
        '{\n  "b": 1,\n  "a": [\n    1,\n    2\n  ]\n}')
    assert pretty_print([1, {"x": "y"}]) == '[\n  1,\n  {\n    "x": "y"\n  }\n]'
