"""LD-700 (round 3 of the public-export review, T18) — a placeholder host is a reserved one.

``x.com``, ``b.com``, ``e.com``, ``ex.com``, ``evil.com`` and ``acme.<lark host>`` are real
registrable names (some are busy sites), so using them as placeholders points a reader — or a
test that ever resolves one — at somebody's real server. Placeholders use ``example.com`` /
``example.org`` (RFC 2606), a ``.invalid`` name, or ``your-domain.<lark host>``. This sweeps the
package, the tests (recorded responses excepted: what Lark sent is kept as sent) and the root
documents for the short-name and stock-placeholder shapes.

**What it allows, stated so the rule is no stricter on paper than in code:** a single-label
generic subdomain of a Lark host in a test (``x.``, ``foo.``, ``tenant-1.``, ``example.`` before
``larksuite.com`` and its siblings). Such a name sits on Lark's own domain rather than on a
server somebody else registered, and an offline test never resolves it. Only ``acme.`` is
caught there, because it is the stock company placeholder.
"""
import re
from pathlib import Path

from guard_kit import REPO_ROOT
import private_tree

ROOT = Path(REPO_ROOT)
_ROOT_DOCS = ("BASE.md", "BLOCKS.md", "DRIVE.md", "LARK_SETUP.md", "PERMISSIONS.md",
              "README.md", "RELEASE_NOTES.md", "SHEETS.md", "TOOLS.md")
_PLACEHOLDER_HOST = re.compile(
    r"(?:https?://|https?%3A%2F%2F|@)(?:[a-z]{1,3}|acme|evil|foo|bar)\.(?:com|net|org|io)\b"
    r"|\bacme\.(?:larksuite\.com|feishu\.cn|larkoffice\.com)")


def _files():
    for top in ("src/larkdocio", "tests", "consumers"):
        for path in sorted((ROOT / top).rglob("*")):
            if (path.is_file() and path.suffix in (".py", ".md", ".json", ".sh")
                    and "__pycache__" not in path.parts and "captures" not in path.parts):
                yield path
    for name in _ROOT_DOCS:
        yield ROOT / name


def test_the_shapes_are_caught_and_the_reserved_names_pass():
    for bad in ("https://x.com/a", "mailto:a@b.com", "https://evil.com/x", "https%3A%2F%2Fe.com",
                "https://acme.feishu.cn/docx/T"):
        assert _PLACEHOLDER_HOST.search(bad), bad
    for good in ("https://example.com/a", "https://evil.invalid/x", "a@example.org",
                 "https://your-domain.larksuite.com/docx/T", "https://www.google.com"):
        assert not _PLACEHOLDER_HOST.search(good), good


@private_tree.walks_tree
def test_no_placeholder_uses_a_registrable_name():
    offenders = []
    for path in _files():
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        offenders += [f"{path.relative_to(ROOT)}: {m.group(0)}" for m in _PLACEHOLDER_HOST.finditer(text)]
    assert not offenders, offenders
