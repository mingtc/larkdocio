"""LD-561 — a guard that is ARMED may not be described in the words of a guard that FIRED.

**The finding (dogfood round 5, ``dev/dogfood5/FINDINGS-BANKED.md`` § F1).** Three shipped
surfaces put the refusal token ``STALE_DOCUMENT``, and whole-batch-refusal prose, into the
output of an operation that **succeeded** — the first line of every ``roundtrip push``, the
programmatic ``revision_guard_detail``, and a stderr warning on a push that went through. None
of the three sentences was false; each described the guard's *availability*. The defect was
that they described it in the vocabulary of the outcome the guard would produce **if it fired**,
in the stream that reports outcomes. Measured, not inferred: round 5's own oracle, fed a
verbatim successful push, returned ``outcome: 'refused'``.

**The rule these tests hold.** The success path reports an **availability**, never an outcome,
and the noun it uses to do so is checked against the live :class:`RefusalReason` enumeration —
a PRESENT-check against the enum, never an absence-check against intuition, because the obvious
replacement noun (*"revision anchor"*) is itself a live refusal token (``STALE_ANCHOR``).
Behaviour is unchanged throughout: only the words move.
"""
import ast
from pathlib import Path

from larkdocio import roundtrip
from larkdocio.common.staleness import REVISION_GUARD_ACTIVE
from larkdocio.roundtrip import _CONCURRENCY_GUARD_LABEL
from larkdocio.write.model.refusal import RefusalReason
from larkdocio.write.revision import revision_guard_semantics

SRC = Path(__file__).resolve().parents[1] / "src" / "larkdocio"
CLI_PATH = SRC / "cli.py"
ROUNDTRIP_PATH = SRC / "roundtrip.py"


def _function_source(path, name):
    """The source text of the top-level function ``name`` in ``path`` — read, never retyped."""
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node)
    raise AssertionError(f"{path.name} no longer defines {name}()")


def _refusal_vocabulary():
    """Every live refusal token, name AND wire value — the enum is the authority, not a hunch."""
    return sorted({member.name for member in RefusalReason}
                  | {member.value for member in RefusalReason})


def _refusal_tokens_in(text):
    return [token for token in _refusal_vocabulary() if token in text]


# --------------------------------------------------------------------------- #
# AC1 — the CLI's success line stops speaking in refusal vocabulary            #
# --------------------------------------------------------------------------- #

def test_ac1_the_push_output_names_no_refusal_token():
    """The line printed on EVERY push — preview and ``--apply``, success included."""
    body = _function_source(CLI_PATH, "roundtrip")
    assert _refusal_tokens_in(body) == [], (
        "the roundtrip command's own prose names a refusal token on the success path")


def test_ac1_the_push_output_reports_the_guards_availability():
    body = _function_source(CLI_PATH, "roundtrip")
    assert "_CONCURRENCY_GUARD_LABEL} {result.revision_guard}" in body, (
        "the push line no longer reports the guard's availability from the projected label")


# --------------------------------------------------------------------------- #
# AC2 — the programmatic detail separates ARMED from what firing WOULD do      #
# --------------------------------------------------------------------------- #

def test_ac2_the_active_detail_states_a_state_not_an_outcome():
    detail = revision_guard_semantics("rev-7")["detail"]
    assert "ARMED" in detail
    assert "nothing has been refused" in detail
    assert "refuses the ENTIRE batch" not in detail, (
        "the armed detail still reports a refusal in the present tense")
    assert "would refuse the ENTIRE batch" in detail


def test_ac2_the_active_detail_keeps_all_five_pinned_phrases():
    """``tests/test_consumer_dialect_guard.py:367-384``'s contract, restated at the source."""
    detail = revision_guard_semantics("rev-7")["detail"]
    missing = [phrase for phrase in ("compare-and-swap", "re-read", "immediately before",
                                     "STALE_DOCUMENT", "ZERO writes")
               if phrase not in detail]
    assert missing == [], missing


def test_ac2_the_behaviour_of_the_guard_did_not_change():
    assert revision_guard_semantics("rev-7")["status"] == REVISION_GUARD_ACTIVE
    assert revision_guard_semantics(None)["status"] == "unavailable"


# --------------------------------------------------------------------------- #
# AC2b — the third site, and the literal three lines above it                  #
# --------------------------------------------------------------------------- #

def test_ac2b_the_success_path_warning_names_no_refusal_token():
    """``roundtrip.push``'s WARNING is printed on a push that SUCCEEDS. Its own prose is held;
    the interpolated ``revision_guard_detail`` is site 2's string and carries its own contract."""
    body = _function_source(ROUNDTRIP_PATH, "push")
    warning = [ast.get_source_segment(ROUNDTRIP_PATH.read_text(encoding="utf-8"), node)
               for node in ast.walk(ast.parse(ROUNDTRIP_PATH.read_text(encoding="utf-8")))
               if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and node.func.attr == "warning"]
    assert warning, "roundtrip.py no longer warns about an unarmed guard"
    for call in warning:
        assert _refusal_tokens_in(call) == [], call
    assert "_CONCURRENCY_GUARD_LABEL" in body


def test_ac2b_the_guard_comparison_imports_the_constant_instead_of_typing_it():
    source = ROUNDTRIP_PATH.read_text(encoding="utf-8")
    assert "REVISION_GUARD_ACTIVE" in source
    assert '!= "active"' not in source, (
        "the round-4 STALE_SHEET shape — a hard-typed guard literal — is back")
    assert '"active"' not in _function_source(ROUNDTRIP_PATH, "push")


# --------------------------------------------------------------------------- #
# AC3 — one authoring site, projected, guarded in BOTH directions              #
# --------------------------------------------------------------------------- #

def _string_literals(path):
    return [node.value for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def test_ac3_the_shared_label_is_typed_exactly_once_in_the_shipped_source():
    """Direction 1: no second hand-typed copy anywhere under ``src/larkdocio``."""
    typed = [(path, literal) for path in sorted(SRC.rglob("*.py"))
             for literal in _string_literals(path)
             if _CONCURRENCY_GUARD_LABEL in literal]
    assert len(typed) == 1, typed
    assert typed[0][0] == ROUNDTRIP_PATH


def test_ac3_every_surface_that_states_the_label_projects_it():
    """Direction 2: both statements of it reference the constant by name, never its text."""
    for path, function in ((CLI_PATH, "roundtrip"), (ROUNDTRIP_PATH, "push")):
        body = _function_source(path, function)
        assert "_CONCURRENCY_GUARD_LABEL" in body, path.name
        assert _CONCURRENCY_GUARD_LABEL not in body, f"{path.name} retypes the label"


def test_ac3_the_label_stays_private_and_surface_local():
    assert _CONCURRENCY_GUARD_LABEL.startswith("concurrency")
    assert "_CONCURRENCY_GUARD_LABEL" not in roundtrip.__all__
    assert not hasattr(__import__("larkdocio.common.staleness", fromlist=["x"]),
                       "_CONCURRENCY_GUARD_LABEL"), (
        "the label was promoted onto a re-exported public path — a new public surface")


def test_ac3_the_label_is_not_itself_a_refusal_token():
    """The trap F1 re-enters through: ``STALE_ANCHOR`` is live, so *"revision anchor"* is out."""
    assert _refusal_tokens_in(_CONCURRENCY_GUARD_LABEL) == []
    for member in RefusalReason:
        assert member.value.replace("-", " ") not in _CONCURRENCY_GUARD_LABEL
