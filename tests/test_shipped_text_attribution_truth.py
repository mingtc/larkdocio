"""LD-286 — shipped text that is false as written, and the guard for its class.

Three shipped strings asserted something the code does not do. Two of them are corrected
here and pinned:

* the **destructive schema family**'s module docstring claimed its three verbs were *the
  only ones on the Base surface that can lose data* — a **record** delete destroys rows
  through the ordinary dry-run/apply path with no consent token, and a **view** delete
  carries neither a loss preview nor a token, so the surface has **three tiers** and the
  text asserted one; and
* ``capabilities()`` attributed the ``read_client`` kwarg to
  :meth:`larkdocio.read.parser.Parser.parse_docx_content`, whose real signature is
  ``(self, doc_id, blocks)`` — the kwarg belongs to ``Parser.__init__``. A consumer
  following the machine-readable registry got a ``TypeError``.

The attribution guard below is the defect **class**, not just the pair: every
``Name(kwarg=…)`` call form appearing anywhere in the ``capabilities()`` projection is
resolved against the library's own objects and its kwargs checked with
:func:`inspect.signature`. The prose shape that produced this bug (a kwarg named beside a
callable that does not take it, with no call parentheses) is pinned targetedly, because a
nearest-identifier heuristic over free prose flags legitimate mentions.
"""
import importlib
import inspect
import re

import larkdocio
from larkdocio.base import schema_ops_destructive
from larkdocio.read.parser import Parser


# ── The corpus: every string the capabilities() projection carries ──────────────────────

def _capability_strings():
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str):
            out.append((path, node))

    walk(larkdocio.capabilities(full=True), "capabilities()")
    return out


_RESOLUTION_MODULES = (
    "larkdocio",
    "larkdocio.config",
    "larkdocio.guide",
    "larkdocio.read.parser",
    "larkdocio.read.client",
    "larkdocio.base.read",
    "larkdocio.base.schema_apply",
    "larkdocio.base.schema_plan",
    "larkdocio.write",
    "larkdocio.sheets",
)


def _resolvable_callables():
    """Name → object, over the library's own public callables."""
    found = {}
    for module_name in _RESOLUTION_MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # pragma: no cover - a module that will not import is not a guard
            continue
        for name in dir(module):
            if name.startswith("_") or name in found:
                continue
            obj = getattr(module, name)
            if inspect.isfunction(obj) or inspect.isclass(obj):
                found[name] = obj
    return found


def _accepted_parameters(obj):
    """The parameter names ``obj`` accepts, or ``None`` when the check cannot be made."""
    target = obj.__init__ if inspect.isclass(obj) else obj
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):  # pragma: no cover - builtins / C callables
        return None
    if any(p.kind is p.VAR_KEYWORD for p in signature.parameters.values()):
        return None  # **kwargs accepts anything; nothing to assert
    return set(signature.parameters)


_CALL_FORM = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*)\(([^()]*=[^()]*)\)")
_KWARG = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*)\s*=(?!=)")


def test_capability_call_forms_name_kwargs_the_callable_actually_takes():
    """AC4 — the class: a kwarg written inside ``Name(…)`` exists on that ``Name``."""
    objects = _resolvable_callables()
    checked, violations = [], []
    for path, text in _capability_strings():
        for match in _CALL_FORM.finditer(text):
            name, args = match.group(1), match.group(2)
            obj = objects.get(name)
            if obj is None:
                continue
            accepted = _accepted_parameters(obj)
            if accepted is None:
                continue
            for kwarg in _KWARG.findall(args):
                checked.append((name, kwarg))
                if kwarg not in accepted:
                    violations.append(f"{path}: {name}(… {kwarg}=…) — {name} takes no {kwarg!r}")
    assert not violations, "capabilities() names a kwarg on a callable that does not take it:\n" + "\n".join(violations)
    # Non-vacuity: the guard must actually be resolving pairs, including the LD-286 one.
    assert ("Parser", "read_client") in checked, checked
    assert len(checked) >= 5, checked


def test_read_client_is_attributed_to_the_parser_not_to_parse_docx_content():
    """AC3/AC4 — the prose shape, pinned against the real signatures."""
    assert "read_client" in inspect.signature(Parser.__init__).parameters
    assert "read_client" not in inspect.signature(Parser.parse_docx_content).parameters

    mentions = [(path, text) for path, text in _capability_strings() if "read_client=" in text]
    assert mentions, "no capabilities() string names the read_client kwarg at all"
    for path, text in mentions:
        assert "Parser(" in text, f"{path}: names read_client= without naming Parser(…)"
        for match in re.finditer(r"read_client\s*=", text):
            window = text[max(0, match.start() - 120):match.start()]
            assert "parse_docx_content" not in window.split("Parser(")[-1], (
                f"{path}: read_client= is attributed to parse_docx_content, whose signature is "
                f"{inspect.signature(Parser.parse_docx_content)}"
            )


# ── The destructive-family boundary (AC1/AC2) ──────────────────────────────────────────

def test_destructive_family_docstring_drops_the_only_ones_claim():
    """AC1 — the module no longer claims its verbs are the only Base ops that lose data."""
    doc = schema_ops_destructive.__doc__ or ""
    assert "only ones on the Base surface" not in doc
    assert "the only ones" not in doc
    lowered = doc.lower()
    assert "record" in lowered and "view" in lowered, "the other two tiers are unnamed"
    assert "no consent token" in lowered
    assert "schema" in lowered


def _three_tier_text_is_complete(text):
    lowered = text.lower()
    return all(
        token in lowered
        for token in ("three tiers", "record", "view", "no consent token")
    )


_XREF = re.compile(r":(func|mod):`([\w.]+)`")


def _xref_resolves(role, dotted):
    """Does the dotted path a ``:func:``/``:mod:`` role names resolve to a real object?"""
    if role == "mod":
        try:
            importlib.import_module(dotted)
        except ImportError:
            return False
        return True
    module_path, _, attr = dotted.rpartition(".")
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        return False
    return hasattr(module, attr)


def test_destructive_family_docstring_cross_references_resolve_to_real_objects():
    """LD-298 — the class LD-286 was filed to remove: every ``:func:``/``:mod:`` target this
    module's own docstring names must resolve to a real callable/module, not just be true prose
    pointed at the wrong object."""
    doc = schema_ops_destructive.__doc__ or ""
    refs = _XREF.findall(doc)
    assert refs, "expected at least one :func:/:mod: cross-reference in the docstring"
    violations = [
        f":{role}:`{dotted}` does not resolve"
        for role, dotted in refs
        if not _xref_resolves(role, dotted)
    ]
    assert not violations, "\n".join(violations)


def test_capabilities_consent_contract_states_the_three_tiers():
    """AC2 — machine-readable: the consent contract says what it does NOT cover."""
    summary = larkdocio.capabilities(full=True)["safety_contracts"]["destructive-consent-required"]["summary"]
    assert _three_tier_text_is_complete(summary), summary


def test_guide_states_the_three_tiers_where_a_consumer_reads_them():
    """AC2 — consumer-reachable from the shipped wheel's own guide text."""
    rows = [
        line
        for line in larkdocio.guide(full=True).splitlines()
        if line.startswith("|") and "`destructive-consent-required`" in line
    ]
    assert len(rows) == 1, rows
    assert _three_tier_text_is_complete(rows[0]), rows[0]
