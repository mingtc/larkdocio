"""LD-533 — ONE disposition-boundary core: ``larkdocio.common.disposition``.

**The smell this closes.** The no-exception-escapes boundary of the two plan-gated write
engines was duplicated: ``base/disposition.py`` and ``sheets/disposition.py`` each defined
their own ``WriteWatch``, ``Disposition``, ``_safe_text``, ``_safe_denial`` and denial
paragraphs, and the base module's own ``WriteWatch`` docstring said out loud that *"two copies
of a safety boundary is one copy too many"* while the copy it was describing was still
standing. The drift was **bidirectional**: base's watch had grown a ``seams`` parameter (the
schema engine needs the identical did-it-land accounting over a different set of client
methods) that sheets lacked, and sheets carried the fuller account of ``_safe_denial``'s three
hazards that base lacked. A hazard fixed on one engine was still open on the other, and
nothing in the tree made that visible.

**What this file pins.**

* The **one** mechanism — the watch, the value object, the two never-raising helpers, the two
  denial paragraphs and the detail formatter — lives in the shared leaf
  ``larkdocio.common.disposition``, and BOTH surfaces re-export the **identical objects**
  (identity, not merely equal values). No public path moved: every name each surface published
  before still resolves at the same address.
* Neither surface holds a **second definition** of the watching mechanism — the anti-redrift
  pin, AST-read, so a copy pasted back into either module reddens here before it can drift.
  Each surface's subclass may contribute exactly one thing: its default seam set.
* The ``seams`` parameter is **honoured**, which is what makes one class enough for two
  engines: an explicit set is watched, and a bare construction gets that surface's own set.
  The core alone **refuses to guess** — a watch with no seams would report "nothing landed"
  about a call that landed something.
* The convergence changed **no text a consumer reads**: the two denial paragraphs were already
  byte-identical across the surfaces, so unifying them is a no-op on the wire. That is the
  whole disclosure argument for the move, and it is a test rather than a claim.
* The **hazards the boundary exists to survive hold on BOTH engines** — an exception whose
  ``__str__`` raises, a denial record that is absent / raises on access / raises inside
  ``detail()`` / renders a non-string / renders blank, and an unmodelled reason falling through
  to the surface's own fallback wording. The sheets engine pinned most of these already; the
  Base engine did not, and those are the characterization gaps this file fills.

Scope note: the **classification tables** are deliberately absent from this file. Which
exception becomes which disposition is each surface's own ruled or measured question, pinned by
``tests/test_base_apply.py`` and ``tests/test_apply_disposition_invariant.py``. Share the
mechanism; never the classification.
"""
import ast
import inspect
import pathlib
import types

import pytest

from larkdocio.base import disposition as base_disposition
from larkdocio.common import disposition as core
from larkdocio.errors import LarkAPIError, LarkPermissionError
from larkdocio.sheets import disposition as sheets_disposition

SURFACES = {"base": base_disposition, "sheets": sheets_disposition}


# --------------------------------------------------------------------------- #
# AC1 — ONE mechanism, and both surfaces re-export the IDENTICAL objects        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("surface", sorted(SURFACES))
@pytest.mark.parametrize("core_name,surface_name", [
    ("ENTRY_SCOPED", "ENTRY_SCOPED"),
    ("SYSTEMIC", "SYSTEMIC"),
    ("Disposition", "Disposition"),
    ("safe_text", "_safe_text"),
    ("safe_denial", "_safe_denial"),
    ("DENIAL_ABSENT", "_DENIAL_ABSENT"),
    ("DENIAL_UNRENDERABLE", "_DENIAL_UNRENDERABLE"),
])
def test_ac1_both_surfaces_re_export_the_identical_core_object(surface, core_name,
                                                               surface_name):
    """Identity, not equality. Two objects that merely compare equal are two objects, and two
    objects are what drifted."""
    module = SURFACES[surface]
    assert getattr(module, surface_name) is getattr(core, core_name), (
        f"{surface}.disposition.{surface_name} is not the core's {core_name}")


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac1_each_surfaces_watch_is_the_core_watch(surface):
    """Not a copy that resembles it — the same class, extended only to bind a default."""
    watch = SURFACES[surface].WriteWatch
    assert issubclass(watch, core.WriteWatch)
    assert watch is not core.WriteWatch, "the surface binds a default; the core has none"


def test_ac1_the_mechanism_is_defined_EXACTLY_ONCE_in_the_package():
    """``class WriteWatch`` appears once under ``src/larkdocio``. The success metric, read off
    the tree rather than asserted in prose."""
    src = pathlib.Path(inspect.getfile(core)).resolve().parent.parent
    hits = [
        path.relative_to(src).as_posix()
        for path in sorted(src.rglob("*.py"))
        if "__pycache__" not in path.parts
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef) and node.name == "WriteWatch"
    ]
    assert hits == ["common/disposition.py"], hits


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac1_a_surface_watch_subclass_contributes_NOTHING_BUT_ITS_DEFAULT(surface):
    """The anti-redrift pin. A surface may bind ``DEFAULT_SEAMS`` and nothing else — the
    moment one of them re-defines ``__getattr__``, ``__init__``, ``issued``, ``completed`` or
    ``wrote``, the second copy is back and this reddens before it can drift."""
    module = SURFACES[surface]
    tree = ast.parse(pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    subclasses = [node for node in ast.walk(tree)
                  if isinstance(node, ast.ClassDef)
                  and any(getattr(b, "id", getattr(b, "attr", None)) == "_SharedWriteWatch"
                          for b in node.bases)]
    assert len(subclasses) == 1, f"expected one watch subclass in {surface}: {subclasses}"
    body = subclasses[0].body
    assigned, defined = [], []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.append(node.name)
        elif isinstance(node, ast.Assign):
            assigned += [t.id for t in node.targets if isinstance(t, ast.Name)]
    assert defined == [], f"{surface} re-defines mechanism members: {defined}"
    assert sorted(assigned) == ["DEFAULT_SEAMS", "__slots__"], assigned


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac1_no_surface_module_re_defines_a_core_helper(surface):
    """The same pin for the functions and the value object: a paraphrase pasted back into a
    surface module is a second definition, whatever it is called."""
    tree = ast.parse(pathlib.Path(inspect.getfile(SURFACES[surface])).read_text(
        encoding="utf-8"))
    top_level = {node.name for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    for banned in ("_safe_text", "_safe_denial", "Disposition", "safe_text", "safe_denial"):
        assert banned not in top_level, f"{surface} defines {banned} again"


def test_ac1_the_shared_core_is_a_LEAF():
    """Standard library only. A core that imported a surface could not be imported BY both
    surfaces, and the whole point is that a third engine can adopt it for free."""
    tree = ast.parse(pathlib.Path(inspect.getfile(core)).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported == {"dataclasses"}, imported


# --------------------------------------------------------------------------- #
# AC1 — every preserved import path still resolves                             #
# --------------------------------------------------------------------------- #

#: The names each surface published before the extraction, re-derived from the call sites and
#: the test estate. A name that stopped resolving here is an ImportError for a sibling module.
PRESERVED = {
    "base": (
        "ENTRY_SCOPED", "SYSTEMIC", "WRITE_SEAMS", "READ_SEAMS", "SYSTEMIC_CODES",
        "ENTRY_SCOPED_CODES", "WriteWatch", "Disposition", "ReadVouch", "AttemptedWrite",
        "PlatformAnomaly", "attempted_write", "classify_apply_exception",
        "disposition_refusal", "plan_wide_platform_anomaly", "platform_anomaly_halted",
        "platform_anomaly_not_attempted", "protected_last_advice",
        "PLATFORM_ANOMALY_NOT_YOUR_PLAN", "PLATFORM_ANOMALY_MIN_ATTEMPTS",
        "PLATFORM_ANOMALY_HALTED", "PLATFORM_ANOMALY_NOT_ATTEMPTED",
        "_safe_text", "_safe_denial", "_DENIAL_ABSENT", "_DENIAL_UNRENDERABLE",
        "_CONTINUED", "_HALTED", "_DETAIL_TEMPLATES", "_DETAIL_FALLBACK", "_code_of", "_PERMISSION_DENIED",
    ),
    "sheets": (
        "ENTRY_SCOPED", "SYSTEMIC", "WRITE_SEAMS", "READ_SEAMS", "FILE_LIFECYCLE_SEAMS",
        "WriteWatch", "Disposition", "classify_apply_exception", "disposition_refusal",
        "_safe_text", "_safe_denial", "_DENIAL_ABSENT", "_DENIAL_UNRENDERABLE",
        "_DETAIL_TEMPLATES", "_DETAIL_FALLBACK", "_UNVERIFIED", "_UNEXPECTED",
        "_PERMISSION_DENIED",
    ),
}


@pytest.mark.parametrize("surface,name", [
    (surface, name) for surface, names in sorted(PRESERVED.items()) for name in names
])
def test_ac1_every_pre_extraction_name_still_resolves_at_its_old_address(surface, name):
    assert hasattr(SURFACES[surface], name), (
        f"larkdocio.{surface}.disposition.{name} no longer resolves")


# --------------------------------------------------------------------------- #
# AC2 — what stays per-surface STAYS, and stays DIFFERENT                      #
# --------------------------------------------------------------------------- #

def test_ac2_the_two_classification_tables_are_still_two():
    """The divergence encodes ruled and measured semantics. Collapsing it is the failure this
    guard names, so it is asserted rather than trusted: the tables differ, and they differ
    where they are supposed to."""
    base_src = inspect.getsource(base_disposition.classify_apply_exception)
    sheets_src = inspect.getsource(sheets_disposition.classify_apply_exception)
    assert base_src != sheets_src
    # base-only arms, each ruled or precedent-bound.
    for arm in ("TableCreatedViewNotNamed", "BaseMediaError", "SYSTEMIC_CODES"):
        assert arm in base_src and arm not in sheets_src, arm


def test_ac2_the_detail_TEMPLATES_are_still_per_surface():
    """The words a consumer reads are surface-specific — a Base call rides many records, a
    sheets entry is one entry — and the shared formatter formats each surface's own table."""
    assert base_disposition._DETAIL_TEMPLATES is not sheets_disposition._DETAIL_TEMPLATES
    assert base_disposition._DETAIL_FALLBACK != sheets_disposition._DETAIL_FALLBACK
    assert base_disposition._DETAIL_TEMPLATES != sheets_disposition._DETAIL_TEMPLATES


def test_ac2_the_seam_sets_are_still_per_surface_and_disjoint_in_kind():
    assert base_disposition.WRITE_SEAMS != sheets_disposition.WRITE_SEAMS
    assert base_disposition.READ_SEAMS != sheets_disposition.READ_SEAMS
    assert not hasattr(base_disposition, "FILE_LIFECYCLE_SEAMS"), (
        "the file-lifecycle category is the sheets client's; base has no workbook")


@pytest.mark.parametrize("name", [
    "SYSTEMIC_CODES", "ENTRY_SCOPED_CODES", "ReadVouch", "AttemptedWrite", "PlatformAnomaly",
    "plan_wide_platform_anomaly", "platform_anomaly_halted", "platform_anomaly_not_attempted",
    "protected_last_advice", "PLATFORM_ANOMALY_NOT_YOUR_PLAN",
])
def test_ac2_base_only_machinery_stayed_base_only(name):
    """Enumerated as deliberately not extracted: none of it has a sheets counterpart, so
    hoisting any of it would be inventing a shared abstraction over one client."""
    assert hasattr(base_disposition, name)
    assert not hasattr(sheets_disposition, name), f"{name} leaked onto sheets"
    assert not hasattr(core, name), f"{name} leaked into the shared core"


# --------------------------------------------------------------------------- #
# AC4 — the seams parameter is honoured, and the core refuses to guess          #
# --------------------------------------------------------------------------- #

def _attribute_surface(*names, **returns):
    """An attribute surface carrying exactly ``names`` as recording callables.

    Named for what it is, and built as a ``SimpleNamespace`` rather than a class, on purpose
    twice over. The watch is generic — it forwards whatever the client exposes — so this needs
    to *carry a name*, not to model a client: a class here would join the client-double
    conformance pools (``tests/test_gateway_signature_conformance.py``) and be asked to mirror
    a real client's parameter names, and mirroring them would be a false claim. It is not
    called ``_client`` for the same reason: that name is a registered write-harness flavour
    with its own recorded inventory, and this is not one of them.
    """
    calls = []
    namespace = types.SimpleNamespace(calls=calls)

    def _make(name):
        def _leg(*a, **k):
            calls.append(name)
            return returns.get(name, "ok")
        return _leg

    for name in names:
        setattr(namespace, name, _make(name))
    return namespace


@pytest.mark.parametrize("surface,seam", [
    ("base", "batch_update_records"),
    ("sheets", "put_values"),
])
def test_ac4_a_bare_construction_gets_THAT_SURFACES_seam_set(surface, seam):
    """The behaviour every landed caller had before the extraction, unchanged: no call site
    names a seam set, and each surface's watch still watches its own."""
    module = SURFACES[surface]
    assert module.WriteWatch.DEFAULT_SEAMS == module.WRITE_SEAMS
    assert seam in module.WRITE_SEAMS
    watch = module.WriteWatch(_attribute_surface(seam))
    assert watch.wrote is False
    getattr(watch, seam)()
    assert watch.issued == (seam,) and watch.completed == (seam,)
    assert watch.wrote is True


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac4_an_explicit_seams_set_OVERRIDES_the_default_on_both_surfaces(surface):
    """The base module's schema engine is this parameter's one real client
    (``WriteWatch(client, seams=SCHEMA_WRITE_SEAMS)``). After the extraction it works on
    either surface, which is what makes one class enough for two engines — and on sheets it is
    new capability, because that copy read a module global."""
    watch = SURFACES[surface].WriteWatch(_attribute_surface("put_values", "read_revision"),
                                         seams={"read_revision"})
    watch.put_values()
    assert watch.issued == (), "a name outside the explicit set is not watched"
    watch.read_revision()
    assert watch.issued == ("read_revision",) and watch.wrote is True


def test_ac4_the_sheets_watch_reads_its_seams_from_the_INSTANCE_not_a_module_global():
    """The one mechanical convergence, named as a behaviour change and pinned. Before the
    extraction the sheets ``__getattr__`` consulted ``sheets.disposition.WRITE_SEAMS``
    directly, so an explicit ``seams=`` could not have been honoured (there was no such
    parameter) and a rebinding of the global would have retargeted a live watch. Now the seam
    set is captured per instance. Nothing in this tree rebinds that global; the pin exists so
    a future reader knows which of the two semantics is the live one."""
    watch = sheets_disposition.WriteWatch(_attribute_surface("put_values"), seams={"put_values"})
    assert watch._seams == frozenset({"put_values"})
    assert watch._seams != sheets_disposition.WRITE_SEAMS


def test_ac4_the_shared_core_REFUSES_to_watch_no_seams():
    """A watch with an empty seam set would answer "nothing landed" about a call that landed
    something — the one failure the whole boundary exists to prevent. So the leaf, which
    cannot name either surface's registry without becoming a surface, raises instead of
    defaulting."""
    assert core.WriteWatch.DEFAULT_SEAMS is None
    with pytest.raises(TypeError) as caught:
        core.WriteWatch(_attribute_surface("put_values"))
    assert "seams" in str(caught.value)
    assert "nothing landed" in str(caught.value)


def test_ac4_the_watch_still_forwards_a_NON_SEAM_attribute_verbatim():
    """Duck-typed probing has to keep working: the engine asks the client for optional legs by
    ``getattr``, and the watch is the object it asks."""
    for module in SURFACES.values():
        watch = module.WriteWatch(_attribute_surface("read_revision", read_revision=7))
        assert watch.read_revision() == 7, "a read seam is forwarded, not watched"
        assert watch.issued == ()


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac4_the_watch_forwards_duck_typed_ABSENCE_on_both_surfaces(surface):
    """``getattr(watch, "nope", None)`` is ``None`` exactly when the client has no ``nope``.
    The sheets engine pinned this; the Base engine did not — a characterization gap."""
    watch = SURFACES[surface].WriteWatch(_attribute_surface("read_revision"))
    assert getattr(watch, "no_such_leg", None) is None
    with pytest.raises(AttributeError):
        watch.no_such_leg


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac4_a_seam_that_RAISED_is_issued_but_never_completed(surface):
    """The did-it-land distinction itself, on both engines: a write that raised did not land.
    Pinned per surface because a proof on one engine is not a proof on the other."""
    class Boom:
        def go(self, *a, **k):
            raise LarkAPIError("late")

    watch = SURFACES[surface].WriteWatch(Boom(), seams={"go"})
    with pytest.raises(LarkAPIError):
        watch.go()
    assert watch.issued == ("go",)
    assert watch.completed == ()
    assert watch.wrote is False, "a raised write must not be reported as landed"


# --------------------------------------------------------------------------- #
# AC4 — the convergence changed no text a consumer reads                       #
# --------------------------------------------------------------------------- #

def test_ac4_the_two_denial_paragraphs_were_ALREADY_byte_identical():
    """The disclosure argument, as a test. Unifying two byte-identical strings changes no
    refusal a consumer reads, which is why this extraction is an internal refactor and not a
    disclosure event. The lengths are asserted so a future edit to either paragraph has to
    come here and say so."""
    assert core.DENIAL_ABSENT == base_disposition._DENIAL_ABSENT
    assert core.DENIAL_ABSENT == sheets_disposition._DENIAL_ABSENT
    assert core.DENIAL_UNRENDERABLE == base_disposition._DENIAL_UNRENDERABLE
    assert core.DENIAL_UNRENDERABLE == sheets_disposition._DENIAL_UNRENDERABLE
    assert (len(core.DENIAL_ABSENT), len(core.DENIAL_UNRENDERABLE)) == (202, 170)
    assert "none is invented" in core.DENIAL_ABSENT


def test_ac4_the_scope_vocabulary_was_already_the_same_two_strings():
    assert (core.ENTRY_SCOPED, core.SYSTEMIC) == ("entry-scoped", "systemic")
    for module in SURFACES.values():
        assert (module.ENTRY_SCOPED, module.SYSTEMIC) == (core.ENTRY_SCOPED, core.SYSTEMIC)


def test_ac4_the_shared_Disposition_still_answers_halts_and_continues():
    entry = core.Disposition(core.ENTRY_SCOPED, "api-error", "refused", "no")
    systemic = core.Disposition(core.SYSTEMIC, "api-error", "refused", "no")
    assert (entry.continues, entry.halts) == (True, False)
    assert (systemic.continues, systemic.halts) == (False, True)


# --------------------------------------------------------------------------- #
# AC3 — the hazards hold on BOTH engines (the Base side is characterization)    #
# --------------------------------------------------------------------------- #

class _Unprintable(Exception):
    """An exception whose ``__str__`` raises — the shape ``safe_text`` exists for."""

    def __str__(self):
        raise ValueError("cannot render me")


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac3_a_detail_survives_an_exception_whose_str_EXPLODES(surface):
    """Defense in depth on the one path whose whole job is not raising. The sheets engine
    pinned this; the Base engine did not — the characterization gap this fills."""
    module = SURFACES[surface]
    disposition = module.classify_apply_exception(_Unprintable(), wrote=False)
    refusal = module.disposition_refusal(disposition, _Unprintable(), where="somewhere")
    assert "unprintable _Unprintable" in refusal.detail
    assert refusal.detail.strip(), "a typed reason with no WHY is a riddle"


class _Denial:
    def __init__(self, behaviour):
        self._behaviour = behaviour

    def detail(self):
        if self._behaviour == "raises":
            raise RuntimeError("someone else's code")
        if self._behaviour == "not-a-string":
            return object()
        if self._behaviour == "blank":
            return "   "
        return "Lark's own denial paragraph."


def _permission_error(behaviour):
    exc = LarkPermissionError("denied", code=99991672, msg="scope required")
    if behaviour == "absent":
        return exc
    if behaviour == "raising-property":
        # A coded subclass whose `denial` is a property that raises. Every api error now
        # ASSIGNS `self.denial` in `LarkAPIError.__init__` — a surface's own typed family
        # carries the record too, not only LarkPermissionError — so the double needs a
        # discarding setter to be constructible at all. The hazard is unchanged and is the
        # READ: the getter still raises, which is what `safe_denial` has to survive.
        class Raising(LarkAPIError):
            code = 99991672
            msg = "scope required"

            @property
            def denial(self):
                raise RuntimeError("the attribute access itself raises")

            @denial.setter
            def denial(self, value):
                pass

        return Raising("denied")
    exc.denial = _Denial(behaviour)
    return exc


@pytest.mark.parametrize("surface", sorted(SURFACES))
@pytest.mark.parametrize("behaviour,expected", [
    ("absent", "DENIAL_ABSENT"),
    ("raising-property", "DENIAL_UNRENDERABLE"),
    ("raises", "DENIAL_UNRENDERABLE"),
    ("not-a-string", "DENIAL_ABSENT"),
    ("blank", "DENIAL_ABSENT"),
])
def test_ac3_every_denial_hazard_yields_a_STATED_absence_on_both_engines(surface, behaviour,
                                                                        expected):
    """Five hazards, all real, all inside the boundary whose entire job is not raising: the
    record may be absent, the attribute access may raise, ``detail()`` is someone else's code,
    and its answer may be a non-string or blank. **No scope name is ever invented.** The sheets
    engine pinned three of these; the Base engine pinned none — the characterization gap."""
    module = SURFACES[surface]
    exc = _permission_error(behaviour)
    # The scope-denial disposition is handed in directly rather than classified: the hazard
    # under test is the DENIAL RENDERING, and the permission template is the only one that
    # names `{denial}`. (A hostile subclass cannot be classified into it anyway — the base
    # class's __init__ owns `code`.) Each surface's own constant, each surface's own template.
    refusal = module.disposition_refusal(module._PERMISSION_DENIED, exc, where="somewhere")
    assert getattr(core, expected) in refusal.detail


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac3_a_working_denial_paragraph_is_relayed_VERBATIM_on_both_engines(surface):
    module = SURFACES[surface]
    exc = _permission_error("ok")
    refusal = module.disposition_refusal(module._PERMISSION_DENIED, exc, where="somewhere")
    assert "Lark's own denial paragraph." in refusal.detail


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac3_an_UNMODELLED_reason_falls_through_to_the_surfaces_own_fallback(surface):
    """The formatter runs INSIDE the boundary that must never raise, so a reason with no
    template of its own must not ``KeyError``. Neither engine pinned this; the shared skeleton
    makes it one code path, so one pin covers both — asserted per surface anyway, because each
    surface's fallback WORDING is its own."""
    module = SURFACES[surface]
    disposition = core.Disposition(core.SYSTEMIC, "a-reason-no-template-knows",
                                   "failed", "indeterminate")
    refusal = module.disposition_refusal(disposition, LarkAPIError("boom", code=1, msg="m"),
                                         where="somewhere")
    assert "a-reason-no-template-knows" in refusal.detail
    assert "indeterminate" in refusal.detail.lower()


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac3_a_lark_message_full_of_BRACES_cannot_break_the_formatter(surface):
    """Lark's ``msg`` is data, not a template. It is substituted, never re-formatted — the
    reason base appends its protected-last advice AFTER formatting rather than inside it."""
    module = SURFACES[surface]
    exc = LarkAPIError("boom {not_a_field} {{}}", code=1254043, msg="{also} {this}")
    disposition = module.classify_apply_exception(exc, wrote=False)
    refusal = module.disposition_refusal(disposition, exc, where="{where} itself")
    assert "{not_a_field}" in refusal.detail
    assert "{where} itself" in refusal.detail


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac3_a_write_that_RETURNED_outranks_the_exceptions_own_class(surface):
    """The did-it-land shape at the classifier: once a seam returned, the only truthful record
    is applied-unverified and the batch must halt, because the compare-and-swap anchor is no
    longer known. A post-write read that fails is NOT "nothing landed"."""
    module = SURFACES[surface]
    disposition = module.classify_apply_exception(LarkAPIError("post-write read failed"),
                                                 wrote=True)
    assert disposition.outcome == "applied-unverified"
    assert disposition.landed == "yes"
    assert disposition.halts is True
    refusal = module.disposition_refusal(disposition, LarkAPIError("post-write read failed"),
                                         where="somewhere", wrote_seams=("a_seam",))
    assert "a_seam" in refusal.detail
    assert "RETURNED" in refusal.detail
    assert "NOTHING landed" not in refusal.detail, (
        "a post-write read that failed must not be reported as nothing landed")


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_ac3_wrote_seams_that_are_EMPTY_still_render_a_detail(surface):
    """The boundary cannot raise on a missing name either — an unknown seam is named as
    unknown rather than left as a formatting hole."""
    module = SURFACES[surface]
    disposition = module.classify_apply_exception(LarkAPIError("x"), wrote=True)
    refusal = module.disposition_refusal(disposition, LarkAPIError("x"), where="somewhere")
    assert "unknown seam" in refusal.detail
