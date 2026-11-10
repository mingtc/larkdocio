"""Every ``capabilities(...)[...]`` path a consumer document names RESOLVES (LD-714, R11-1).

Why this exists
---------------
The root README — which is also the wheel's ``METADATA`` body — told a reader to take
``credentials`` and each surface's ``safety_contracts`` off a bare ``larkdocio.capabilities()``.
The bare call returns the **summary**, which carries neither, so following the line as written
raised ``KeyError``. The guide spelled the same reads correctly as ``capabilities(full=True)``;
nothing held the other documents to the real return value.

This guard extracts every subscript path written against a ``capabilities(...)`` call — the
``["key"]`` steps, ``.get("key")`` steps and the elided steps (``[...]``, ``[…]``, ``[*]``,
``[<id>]``) — from the consumer documents and resolves it against the **real** payload of the
call the document spells: the summary, ``full=True``, or ``surface=<id>``. An elided step
resolves when **any** member carries the rest of the path, so the guard asks only that the
path a document names can exist, never which member a reader picks.

It is proven to bite on a planted bad path (the R11-1 shape itself) and not to bite on the
good form beside it.
"""
import pathlib
import re

import pytest

import larkdocio

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The consumer documents that name capabilities paths. Skills are globbed, never listed.
DOCS = [
    ROOT / "README.md",
    ROOT / "LARK_SETUP.md",
    ROOT / "src" / "larkdocio" / "LARK_SETUP.md",
    ROOT / "src" / "larkdocio" / "GUIDE.md",
    *sorted((ROOT / "consumers" / "skills").glob("**/*.md")),
]

_CALL = re.compile(
    r"capabilities\((?P<args>[^)]*)\)"
    r"(?P<steps>(?:\[[^\]\n]*\]|\.get\([^)\n]*\))+)"
)
_STEP = re.compile(r"\[([^\]\n]*)\]|\.get\(([^)\n]*)\)")
_QUOTED = re.compile(r"""^\s*(["'])(.*)\1\s*(?:,.*)?$""")


def extract_paths(text):
    """``[(args, [step, ...]), ...]`` — a step is a key string, or ``None`` for an elided step."""
    found = []
    for match in _CALL.finditer(text):
        steps = []
        for sub in _STEP.finditer(match.group("steps")):
            raw = sub.group(1) if sub.group(1) is not None else sub.group(2)
            quoted = _QUOTED.match(raw)
            steps.append(quoted.group(2) if quoted else None)
        found.append((match.group("args").strip(), steps))
    return found


def _resolves(node, steps):
    if not steps:
        return True
    head, rest = steps[0], steps[1:]
    if head is None:
        members = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
        return any(_resolves(member, rest) for member in members)
    if isinstance(node, dict) and head in node:
        return _resolves(node[head], rest)
    return False


_PAYLOADS = {}


def _payloads_for(args):
    """The real return value(s) of the call the document spells."""
    if args not in _PAYLOADS:
        if args == "":
            _PAYLOADS[args] = [larkdocio.capabilities()]
        elif args == "full=True":
            _PAYLOADS[args] = [larkdocio.capabilities(full=True)]
        elif args.startswith("surface="):
            value = _QUOTED.match(args[len("surface="):])
            ids = ([value.group(2)] if value
                   else list(larkdocio.capabilities(full=True)["surfaces"]))
            _PAYLOADS[args] = [larkdocio.capabilities(surface=sid) for sid in ids]
        else:
            raise AssertionError(f"unrecognised capabilities() call form: capabilities({args})")
    return _PAYLOADS[args]


def unresolved(text):
    """Every path in *text* that resolves against none of its call's real payloads."""
    return [
        (args, steps) for args, steps in extract_paths(text)
        if not any(_resolves(payload, steps) for payload in _payloads_for(args))
    ]


def test_the_corpus_names_paths_at_all():
    total = sum(len(extract_paths(doc.read_text(encoding="utf-8"))) for doc in DOCS)
    assert total >= 20, f"only {total} capabilities paths found — has the extractor stopped matching?"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_capabilities_path_a_document_names_resolves(doc):
    bad = unresolved(doc.read_text(encoding="utf-8"))
    assert not bad, f"{doc.relative_to(ROOT)} names capabilities paths the real call lacks: {bad}"


@pytest.mark.parametrize("planted", [
    # The R11-1 shape: the long-form field read off the summary.
    'or as `larkdocio.capabilities()[...]["credentials"]["scopes"]`',
    'each `capabilities()["surfaces"][…]["safety_contracts"]`',
    # The summary's safety_contracts is a list of ids, not a dict.
    '`capabilities()["safety_contracts"]["caller-supplied-destination"]`',
    '`capabilities(full=True)["surfaces"].get("no-such-surface")`',
    '`capabilities(surface=<id>)["credentials"]["nope"]`',
])
def test_the_guard_bites_on_a_planted_bad_path(planted):
    assert unresolved(planted), f"a bad path resolved: {planted}"


@pytest.mark.parametrize("good", [
    '`capabilities(full=True)["surfaces"][...]["credentials"]["scopes"]`',
    '`capabilities()["surfaces"][…]["scopes"]`',
    '`capabilities(full=True)["safety_contracts"]["caller-supplied-destination"]["summary"]`',
    '`capabilities(surface=<id>)["operations"]`',
])
def test_the_guard_does_not_bite_on_the_good_form(good):
    assert extract_paths(good) and not unresolved(good)
