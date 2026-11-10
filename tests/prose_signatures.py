"""PROSE signature claims — the third face of the "runs as pasted" class (dogfood F5).

Why this module exists
---------------------
The shipped guide promises *"every recipe below runs as pasted"*, and that promise is
enforced by **extracting each ```` ```python ```` fence and executing it**
(``tests/guide_recipes.py``). A precise, testable definition — and **narrower than the
promise a consumer reads**, which is *"the things this document tells me to call, work"*.

The gap has now been found three times, each time in a different unit:

* **commented-out recipe lines** — the harness read only what *executed*, while a consumer
  pastes every line and uncomments the alternative (closed by widening
  ``guide_recipes.static_problems``);
* **pasted helpers** — a helper the guide hands over whose behaviour nothing asserted;
* **prose signature claims** — *this* module. A bullet reading
  **``AppendDimension(sheet_id, dimension="ROWS", length=…)``** shipped for a whole tranche
  while that exact call raises ``TypeError`` (the real parameter is ``major_dimension``).
  The bullet sat **20 lines below the fence that closed above it**, so the extract-and-execute
  harness never saw it. Nothing was neglected; the claim was simply **out of scope**.

So the unit of verification widens again: **every inline ``Symbol(...)`` span in
consumer-reaching prose is checked against the real signature by introspection.**

What is checked, and what deliberately is not
---------------------------------------------
A claim is an inline code span (any backtick run) *outside* a fence whose text is a Python
**call** or a Python **parameter list**. Two forms, checked differently on purpose:

============  ==================================  =====================================
form          example                             what is enforced
============  ==================================  =====================================
**call**      ``AppendDimension(sheet_id,          the call **binds** to the real
              major_dimension="ROWS")``           signature — no unknown keyword, no
                                                  excess positional, no keyword handed
                                                  to a positional-only parameter
**signature** ``AppendDimension(sheet_id: str,     parameter **names, order, kinds and
              major_dimension: str,                DEFAULTS** match exactly
              length: int = 1)``
============  ==================================  =====================================

The split is **syntactic, not a guess**: annotations are illegal in a call, so a span that
parses as an expression is a call claim and a span that only parses as a parameter list is a
signature claim. That matters because this guide writes *illustrative values* in prose all
the time — ``NewBlock.code(text, language="python")`` shows the interesting value, it does
not claim ``"python"`` is the default. Inferring a default claim from a call would redden on
correct prose, and a guard that cries wolf gets weakened until it guards nothing. Writing the
annotated form is how an author **opts in** to having the default guarded.

Four things are deliberately out of scope, each because including it would manufacture false
positives rather than find defects:

* **anything inside a fence** — that is the executing harness's job, and a claim reported by
  both guards would be fixed twice and reported twice;
* **a span that names a symbol without parentheses** (``MergeCells`` keeps the anchor) — it
  claims nothing about a signature;
* **a span that parses as neither an expression nor a parameter list**
  (``NewBlock.heading(7..9, …)`` is prose meaning "levels 7 to 9");
* **annotation *text*** — ``length: int`` vs ``length: numbers.Integral`` is documentation
  sugar; the load-bearing facts are the names, the order, the kinds and the defaults.

Line wrapping is load-bearing, not cosmetic
-------------------------------------------
Every shipped surface is hard-wrapped, and **five call-shaped claims ship wrapped across a
newline today** (``compose(authored) ==\\ncompose(read_back)``, ``NewBlock.code(text,\\n
language=…)``, ``compose_insert(markdown, reference,\\nposition=AFTER)``,
``a1_column_to_number(column_number_to_a1(n))\\n== n`` and ``DeleteRows(first=2,\\nlast=3)``).
A single-line extractor finds **none** of them. So spans are matched across newlines and
:func:`flatten`ed before parsing — reflowing a paragraph can neither hide nor invent a claim.

The escape hatch, and why it is narrow
--------------------------------------
An unresolvable symbol is a **defect** (a rename, a deletion, a symbol that never existed) —
that is the whole point. But prose may legitimately name a callable the *caller* supplies,
which no introspection can resolve. For that, and only that, a surface may carry

    ``<!-- signature-claim: illustrative <symbol> -->``

which excuses that **one named symbol** in that **one surface**, and excuses **only** the
"names no symbol the library has" problem. It cannot keep a real symbol's wrong keyword
alive, and it cannot be written once to cover a document. As measured at the time this guard
landed, **no surface needs it** — it exists so that a future one is not forced to reword
correct prose to satisfy a guard.
"""
import ast
import builtins
import functools
import importlib
import inspect
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import consumer_text

# --------------------------------------------------------------------------- #
# 1. Extraction — prose only, flattened, fences masked out.                     #
# --------------------------------------------------------------------------- #

#: A fence line — opening or closing. Indented fences (inside a list item) count.
_FENCE_RE = re.compile(r"^\s*```")

#: An inline code span: a run of backticks, its content, the same run again. The negative
#: lookarounds keep a ```` `` ```` run from being read as two single-backtick spans, so the
#: RST-style ``double backtick`` a docstring uses is one span like Markdown's single one.
#: ``DOTALL`` is what makes a **wrapped** claim visible at all (see the module docstring).
_SPAN_RE = re.compile(r"(`+)(?!`)(.+?)\1(?!`)", re.DOTALL)

#: ``Symbol(...)`` / ``pkg.mod.Symbol(...)`` — the shape that could be a claim. Applied to
#: the FLATTENED span, so a wrapped claim matches exactly as an unwrapped one does.
_CALL_SHAPE_RE = re.compile(r"^([A-Za-z_][\w.]*)(\(.*\))$", re.DOTALL)

#: The illustrative-pseudo-call marker (see the module docstring). The symbol it names is
#: required, which is what stops it from becoming a document-wide silencer.
_MARKER_RE = re.compile(
    r"<!--\s*signature-claim:\s*illustrative\s+([A-Za-z_][\w.]*)\s*(?:\(\s*\))?[^>]*-->"
)


def flatten(text: str) -> str:
    """Collapse every whitespace run to one space.

    Load-bearing: see the module docstring's wrapping section. Five claims ship wrapped, and
    an extractor that read one line at a time would see none of them.
    """
    return " ".join((text or "").split())


def mask_fenced_code(text: str) -> str:
    """``text`` with every fenced block blanked, **line count preserved**.

    Blanked rather than deleted so a reported line number still points at the surface's own
    line. Fenced code is the executing harness's territory; a claim reported by both guards
    would be reported twice and fixed twice.
    """
    out, in_fence = [], False
    for line in (text or "").splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def inline_spans(text: str) -> List[Tuple[int, str, str]]:
    """``[(1-based line, raw span text, flattened span text)]`` for the PROSE of ``text``.

    A span containing a blank line is dropped: no inline code span survives a paragraph
    break, so such a match is two unbalanced backticks rather than one span.
    """
    prose = mask_fenced_code(text)
    spans = []
    for match in _SPAN_RE.finditer(prose):
        raw = match.group(2)
        if not raw.strip() or "\n\n" in raw:
            continue
        spans.append((prose[: match.start()].count("\n") + 1, raw, flatten(raw)))
    return spans


@dataclass(frozen=True)
class Claim:
    """One signature claim made by consumer-reaching prose."""

    #: which surface carries it — a ``consumer_text`` corpus label.
    surface: str
    #: 1-based line within that surface (the span's opening backtick).
    lineno: int
    #: the claim as written, flattened.
    text: str
    #: the dotted symbol path it names.
    symbol: str
    #: ``"call"`` (parses as an expression) or ``"signature"`` (a parameter list).
    kind: str
    #: the ``ast.Call`` node (``kind == "call"``) or ``ast.arguments`` (``"signature"``).
    node: object

    def __str__(self) -> str:
        return f"{self.surface} line {self.lineno}: `{self.text}` [{self.kind}]"


def _dotted(node: ast.AST) -> Optional[str]:
    """``a.b.c`` for a Name/Attribute chain; ``None`` when the callee is any other
    expression (``f()[0]()``, a subscripted receiver) — such a span claims nothing about a
    named symbol's signature."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _signature_form(symbol: str, arglist: str):
    """``ast.arguments`` when ``arglist`` is a **parameter list** — else ``None``.

    Parsed as a ``def``, which is the only place annotations are legal. That is precisely why
    an annotated span is unambiguously a *signature* statement and not a call.
    """
    try:
        tree = ast.parse(f"def __claim__{arglist}: pass")
    except SyntaxError:
        return None
    node = tree.body[0]
    if not isinstance(node, ast.FunctionDef):
        return None
    args = node.args
    annotated = [
        a for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        if a.annotation is not None
    ]
    return args if annotated else None


def prose_claims(text: str, surface: str = "<text>") -> List[Claim]:
    """Every signature claim in ``text``'s prose, in document order.

    Nested calls count: ``compose(authored) == compose(read_back)`` makes **two** claims, and
    ``print(capabilities())`` makes two — a claim is a claim wherever it sits in an
    expression.
    """
    claims: List[Claim] = []
    for lineno, _raw, flat in inline_spans(text):
        shape = _CALL_SHAPE_RE.match(flat)
        try:
            tree = ast.parse(flat.replace("…", "..."))
        except SyntaxError:
            # Not an expression. It may still be an annotated parameter list.
            if shape is not None:
                args = _signature_form(shape.group(1), shape.group(2).replace("…", "..."))
                if args is not None:
                    claims.append(Claim(surface, lineno, flat, shape.group(1),
                                        "signature", args))
            continue
        if shape is not None:
            args = _signature_form(shape.group(1), shape.group(2).replace("…", "..."))
            if args is not None:
                claims.append(Claim(surface, lineno, flat, shape.group(1),
                                    "signature", args))
                continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            symbol = _dotted(node.func)
            if symbol is not None:
                claims.append(Claim(surface, lineno, flat, symbol, "call", node))
    return claims


def illustrative_symbols(text: str) -> set:
    """The symbols a surface explicitly marks as illustrative pseudo-calls."""
    return set(_MARKER_RE.findall(text or ""))


# --------------------------------------------------------------------------- #
# 2. Resolution — the WHOLE library, not the guide's import list.               #
#                                                                              #
#    Scoping this to the modules the guide happens to import is how the         #
#    original guard missed prose in the first place: `supported_code_languages` #
#    is a real, documented symbol that no recipe imports by name, and a         #
#    narrow index would report it as "no symbol the library has" — a false      #
#    positive in the one message that has to be trustworthy.                    #
# --------------------------------------------------------------------------- #

@functools.lru_cache(maxsize=1)
def library_modules() -> tuple:
    """Every importable module under ``src/larkdocio`` (the shipped package)."""
    names = []
    for path in sorted(consumer_text.SRC.rglob("*.py")):
        parts = list(path.relative_to(consumer_text.SRC.parent).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.append(".".join(parts))
    modules = []
    for name in names:
        try:
            modules.append(importlib.import_module(name))
        except Exception:  # pragma: no cover — an unimportable module reddens test_guide.py
            continue
    return tuple(modules)


@functools.lru_cache(maxsize=1)
def _symbol_index() -> Tuple[Dict[str, tuple], Dict[str, tuple]]:
    """``({bare name: module-level callables}, {attr: class members})``.

    The second map is what lets prose name a **method** (``reader.get_docx_content(token)``,
    ``review.for_node(block)``) — the receiver is a local variable no introspection can
    resolve, so the method is looked up by its own name. It is consulted only when the dotted
    path itself resolves to nothing, so a real module path always wins.
    """
    functions: Dict[str, list] = {}
    methods: Dict[str, list] = {}
    for module in library_modules():
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name, None)
            if obj is None or inspect.ismodule(obj):
                continue
            if not (getattr(obj, "__module__", "") or "").startswith("larkdocio"):
                continue
            if callable(obj):
                functions.setdefault(name, []).append((f"{module.__name__}.{name}", obj, False))
            if not inspect.isclass(obj):
                continue
            for attr, member in vars(obj).items():
                if attr.startswith("_"):
                    continue
                if isinstance(member, (staticmethod, classmethod)):
                    member = member.__func__
                if callable(member):
                    methods.setdefault(attr, []).append(
                        (f"{obj.__name__}.{attr}", member, True))
    return ({k: tuple(v) for k, v in functions.items()},
            {k: tuple(v) for k, v in methods.items()})


def _dedupe(candidates):
    seen, out = set(), []
    for name, fn, unbound in candidates:
        key = (id(fn), unbound)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, fn, unbound))
    return out


def resolve_symbol(path: str) -> list:
    """``[(where, callable, is_unbound_method)]`` — every symbol ``path`` could name.

    **Every** candidate, not the first: ``dry_run`` is a real name on both write surfaces
    (``larkdocio.write.dry_run`` takes ``document_revision_id``; ``larkdocio.sheets.dry_run``
    does not), so first-wins resolution would report the guide's correct docx claim as a
    wrong keyword. A claim passes when **any** candidate accepts it — which is the consumer's
    truth: they imported one of them, and that one works.
    """
    functions, methods = _symbol_index()
    parts = path.split(".")
    out = []
    if len(parts) == 1:
        if hasattr(builtins, parts[0]):
            out.append((f"builtins.{parts[0]}", getattr(builtins, parts[0]), False))
        out.extend(functions.get(parts[0], ()))
    else:
        for module in library_modules():
            obj, ok = module, True
            for part in parts:
                obj = getattr(obj, part, None)
                if obj is None:
                    ok = False
                    break
            if ok and callable(obj):
                out.append((f"{module.__name__}.{path}", obj, False))
        for cut in range(len(parts) - 1, 0, -1):
            try:
                module = importlib.import_module(".".join(parts[:cut]))
            except Exception:
                continue
            obj, ok = module, True
            for part in parts[cut:]:
                obj = getattr(obj, part, None)
                if obj is None:
                    ok = False
                    break
            if ok and callable(obj):
                out.append((path, obj, False))
    if not out:
        out.extend(methods.get(parts[-1], ()))
    return _dedupe(out)


def _signature_of(fn, unbound: bool):
    """``inspect.signature(fn)``, with ``self``/``cls`` dropped for a name-resolved method.

    A method reached by its own name is an *unbound* function, but the prose that names it
    (``reader.get_docx_content(doc_token)``) writes the **bound** call. Keeping ``self`` would
    make every such claim look one argument short.
    """
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):      # a C builtin with no introspectable signature
        return None
    if unbound:
        params = list(sig.parameters.values())
        if params and params[0].name in ("self", "cls"):
            sig = sig.replace(parameters=params[1:])
    return sig


# --------------------------------------------------------------------------- #
# 3. Checking — bindability for a call, exact agreement for a signature.        #
# --------------------------------------------------------------------------- #

UNRESOLVED = "names no symbol the library has"

#: Standard-library callables that consumer prose names but that only exist from a given
#: Python version (LD-687). The suite runs on 3.11+ while the dev interpreter is 3.14, so on an
#: older interpreter such a symbol resolves to nothing — the interpreter cannot see it, which
#: is not evidence the prose is wrong. Below its version the claim is not checkable HERE and is
#: excused; at or above it the claim is checked in full. Closed and enumerated, and held both
#: ways by ``test_every_stdlib_since_entry_is_exactly_as_new_as_it_says``.
STDLIB_SINCE: Dict[str, Tuple[int, int]] = {
    "copy.replace": (3, 13),     # the 1.52.0 release notes, beside dataclasses.replace()
}


def _call_problem(node: ast.Call, sig: inspect.Signature) -> Optional[str]:
    """``None`` when the written call **binds**, else why it cannot.

    ``bind_partial`` on purpose, not ``bind``: prose names a function with bare parentheses
    all the time (``compose()``, ``apply()``), which is a reference to the symbol and not a
    claim that it takes no arguments. What ``bind_partial`` still catches is every way a
    written call is **impossible**: an unknown keyword, more positionals than exist, a
    keyword handed to a positional-only parameter.
    """
    positional = [a for a in node.args if not isinstance(a, ast.Starred)]
    keywords = {kw.arg: object() for kw in node.keywords if kw.arg is not None}
    try:
        sig.bind_partial(*[object()] * len(positional), **keywords)
    except TypeError as exc:
        return f"{exc}"
    return None


def _params_of(args: ast.arguments) -> list:
    """``[(name, kind, default source or None)]`` for a written parameter list."""
    out = []
    posonly, pos = list(args.posonlyargs), list(args.args)
    defaults = list(args.defaults)
    positional = posonly + pos
    pad = len(positional) - len(defaults)
    for index, arg in enumerate(positional):
        default = defaults[index - pad] if index >= pad else None
        kind = (inspect.Parameter.POSITIONAL_ONLY if index < len(posonly)
                else inspect.Parameter.POSITIONAL_OR_KEYWORD)
        out.append((arg.arg, kind, default))
    if args.vararg is not None:
        out.append((args.vararg.arg, inspect.Parameter.VAR_POSITIONAL, None))
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        out.append((arg.arg, inspect.Parameter.KEYWORD_ONLY, default))
    if args.kwarg is not None:
        out.append((args.kwarg.arg, inspect.Parameter.VAR_KEYWORD, None))
    return out


def _literal(node) -> Tuple[bool, object]:
    """``(is_literal, value)`` for a written default. Non-literals are not compared."""
    if node is None:
        return False, None
    try:
        return True, ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return False, None


def _signature_problem(args: ast.arguments, sig: inspect.Signature) -> Optional[str]:
    """``None`` when the written parameter list agrees with the real one, else the drift.

    Names, order and kinds must match exactly, and every **written literal default** must be
    the real default — the subtlest drift there is, because the names and the arity can both
    be right while the documented default is wrong, and a default is the one thing a consumer
    trusts without checking. ``…`` stands for "unspecified" and is never compared;
    **annotations are not compared** (see the module docstring).
    """
    written = _params_of(args)
    real = [(p.name, p.kind, p.default) for p in sig.parameters.values()]
    if [n for n, _k, _d in written] != [n for n, _k, _d in real]:
        return (f"documents parameters {[n for n, _k, _d in written]} but the real ones are "
                f"{[n for n, _k, _d in real]}")
    for (name, kind, default), (_rname, rkind, rdefault) in zip(written, real):
        if kind is not rkind:
            return f"documents {name!r} as {kind.description}, really {rkind.description}"
        is_literal, value = _literal(default)
        if not is_literal or value is Ellipsis:
            continue
        if rdefault is inspect.Parameter.empty:
            return f"documents a default for {name!r} ({value!r}); it is a REQUIRED parameter"
        if value != rdefault:
            return (f"documents {name}={value!r} but the real default is {rdefault!r} — "
                    f"names and arity agree, so nothing else would have caught this")
    for (name, _kind, default), (_rname, _rkind, rdefault) in zip(written, real):
        if default is None and rdefault is not inspect.Parameter.empty:
            return (f"documents {name!r} as required; it really defaults to {rdefault!r}")
    return None


def claim_problems(claim: Claim, illustrative=()) -> List[str]:
    """Every way ``claim`` disagrees with the library. Empty ⇒ the claim is true."""
    candidates = resolve_symbol(claim.symbol)
    if not candidates:
        if claim.symbol in illustrative:
            return []
        if sys.version_info[:2] < STDLIB_SINCE.get(claim.symbol, (0, 0)):
            return []                    # newer than this interpreter — checked on one that has it
        return [f"{claim} → {UNRESOLVED}"]
    failures = []
    for where, fn, unbound in candidates:
        sig = _signature_of(fn, unbound)
        if sig is None:
            return []                    # not introspectable — nothing can be claimed
        problem = (_call_problem(claim.node, sig) if claim.kind == "call"
                   else _signature_problem(claim.node, sig))
        if problem is None:
            return []                    # some real symbol accepts it — the claim is true
        failures.append(f"{claim} → {where}{sig}: {problem}")
    return failures[:1]


# --------------------------------------------------------------------------- #
# 4. The sweep — the whole consumer-reaching corpus, in one call.               #
# --------------------------------------------------------------------------- #

def sweep(corpus=None) -> Tuple[List[Claim], List[str]]:
    """``(every claim, every problem)`` over ``corpus`` (default: the full consumer corpus).

    The corpus is ``consumer_text.consumer_corpus()`` — the same four-pass corpus the
    internal-dialect guard greps — so this guard can never be narrower than that one, and a
    surface added there is swept here without anyone widening a list.
    """
    corpus = consumer_text.consumer_corpus() if corpus is None else corpus
    claims, problems = [], []
    for label, text in corpus.items():
        if not isinstance(text, str):
            continue
        marked = illustrative_symbols(text)
        for claim in prose_claims(text, label):
            claims.append(claim)
            problems.extend(claim_problems(claim, marked))
    return claims, problems


def wrapped_claims(corpus=None) -> List[Claim]:
    """Every claim that ships **split across a newline** — the flattening evidence."""
    corpus = consumer_text.consumer_corpus() if corpus is None else corpus
    out = []
    for label, text in corpus.items():
        if not isinstance(text, str):
            continue
        prose = mask_fenced_code(text)
        for match in _SPAN_RE.finditer(prose):
            raw = match.group(2)
            if "\n" not in raw or "\n\n" in raw or not raw.strip():
                continue
            lineno = prose[: match.start()].count("\n") + 1
            for claim in prose_claims(f"`{flatten(raw)}`", label):
                out.append(Claim(label, lineno, claim.text, claim.symbol,
                                 claim.kind, claim.node))
    return out
