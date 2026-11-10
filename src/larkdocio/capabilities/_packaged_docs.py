"""The packaged-documents leg — projected off the accessor table.

LD-244: the verbatim pre-split slice, lines 1267-1418 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
from ._addressing import section_addressing
from ._models import Doc, EntryPoint

# --------------------------------------------------------------------------- #
# The packaged-documents leg — PROJECTED off the accessor table that lives      #
# beside the accessors themselves, never a second hand-kept list here.          #
# --------------------------------------------------------------------------- #

def _docs() -> dict:
    """``{"accessor()": Doc}`` for every packaged document **written for a consumer**.

    Projected off :data:`larkdocio.guide.DOC_ACCESSORS` — the table that sits beside the
    accessor functions — and each row's accessor is **resolved** here, so a row naming a
    function that does not exist raises at projection time rather than advertising a call a
    consumer cannot make. Imported inside the function because this module is imported while
    the package is still initializing — and by module path, because ``larkdocio.guide`` is
    also the name the package re-exports the *function* under, so an attribute lookup on the
    package would hand back the function.
    """
    import importlib

    _guide_module = importlib.import_module("larkdocio.guide")

    docs = {}
    for name, resource, summary in _guide_module.DOC_ACCESSORS:
        accessor = getattr(_guide_module, name)  # a phantom row cannot survive this
        if not callable(accessor):  # pragma: no cover — defensive; the getattr above is the gate
            raise TypeError(f"larkdocio.guide.{name} is not callable")
        label = f"{name}()"
        # A document's section index, when it has one. Looked up BY CONVENTION — the
        # ``<accessor>_sections`` helper beside the accessor — rather than special-cased for
        # one document, so a second document that ever grows one gains the field here with no
        # change, and a document without one keeps exactly the row shape it always had. The
        # rows themselves are derived from the document at call time, so nothing about the set
        # of section names is written down in this module.
        sections = getattr(_guide_module, f"{name}_sections", None)
        indexed = callable(sections)
        rows = tuple(sections()) if indexed else None
        docs[label] = Doc(
            accessor=label, resource=resource, summary=summary,
            sections=rows,
            # The index says WHAT the document contains; this says the parts are individually
            # ADDRESSABLE — the half a consumer was left to guess (LD-320 / consumer friction
            # 8). The sentence is still authored once, for every document, rather than
            # per-document prose — but it is now BUILT FROM THAT DOCUMENT'S OWN INDEX ROWS
            # (``_addressing.section_addressing``) instead of stating one fixed pair of levels
            # for all five.
            #
            # SUPERSEDED (LD-646), reason preserved. The original argument here was that the
            # sentence "is attached only to a document that really has a section accessor, so
            # it can never become a claim about a document that cannot honour it". The
            # ATTACHMENT half of that reason still holds and is still why the ``indexed``
            # test above gates the field. The CONCLUSION was wrong, and larkdocio shipped the
            # counter-example: having an accessor says nothing about the LEVELS it indexes at,
            # and ``release_notes()`` / ``changelog()`` are level-2-only documents that were
            # told a consumer their ``###`` headings were retrievable — ``ValueError`` on
            # every such call. A row can carry a section accessor and still be unable to
            # honour a claim about it; only a claim derived from the document itself cannot
            # over-reach.
            section_addressing=section_addressing(name, rows) if indexed else None,
        )
    return docs


#: ``name -> (summary, cost)`` for every public top-level symbol. The **only** hand-authored
#: half of the entry-point index: the row set itself is projected off ``larkdocio.__all__``, so
#: a public symbol added without a line here raises at projection time rather than shipping
#: undescribed, and a line whose symbol is gone cannot linger.
_ENTRY_POINT_NOTES = {
    "capabilities": (
        "This registry — every surface, operation, credential, scope, opt-in flag and safety "
        "contract the install actually has, as a JSON-serializable dict.",
        "No API calls; no credentials, no network.",
    ),
    "guide": (
        "The packaged consumer guide: runnable recipes, the capability matrix, the credential "
        "split and the generated permissions table. With NO argument it returns the guide's "
        "section index as text — every heading named after the failure it cures, each row the "
        "call that fetches it — which is the front door and names your next call. Pass "
        "section= for one part of it, or full=True for the whole document byte for byte "
        "(hundreds of KB). Also `larkdocio guide` / `--section` / `--full` on the command "
        "line; guide_sections() is the same index as data.",
        "No API calls; reads a packaged resource.",
    ),
    "guide_sections": (
        "The guide's section index — one row per heading, with the heading, the shorter slug "
        "that also names it, and the level that says what it contains. Names only, no text: "
        "it is what you read to choose which section to ask guide(section=...) for. Derived "
        "from the document's own headings on every call, so it cannot disagree with it; the "
        "same rows ride on capabilities(full=True)['docs']['guide()']['sections'].",
        "No API calls; reads a packaged resource.",
    ),
    "writer_brief": (
        "The packaged writer design brief — the long-form treatment of the authoring dialect "
        "and the writeback contracts the guide cites. Pass section= to get one part of it "
        "instead of the whole document — writer_brief_sections() is the index.",
        "No API calls; reads a packaged resource.",
    ),
    "writer_brief_sections": (
        "The writer brief's section index — one row per heading, same shape as "
        "guide_sections(): the heading, its slug, and the level that says what it contains. "
        "Names only, no text. Derived from the document's own headings on every call.",
        "No API calls; reads a packaged resource.",
    ),
    "release_notes": (
        "The consumer-filtered record of what changed release by release — read this before "
        "re-pinning a newer wheel. Pass section= to get ONE release instead of every release "
        "ever written — release_notes_sections() is the index.",
        "No API calls; reads a packaged resource.",
    ),
    "release_notes_sections": (
        "The release notes' section index — one row per `## [X.Y.Z] — date` release heading, "
        "same shape as guide_sections(). Names only, no text. Derived from the document's own "
        "headings on every call.",
        "No API calls; reads a packaged resource.",
    ),
    "changelog": (
        "The project's changelog: one entry per release, pointing at the release notes for "
        "the detail. Pass section= to get ONE release instead of every release it carries "
        "— changelog_sections() is the index.",
        "No API calls; reads a packaged resource.",
    ),
    "changelog_sections": (
        "The changelog's section index — one row per `## [X.Y.Z] — date` release heading, "
        "same shape as guide_sections(). Names only, no text. Derived from the document's own "
        "headings on every call.",
        "No API calls; reads a packaged resource.",
    ),
    "lark_setup": (
        "The packaged Lark-application walkthrough — the ten minutes BEFORE a first call: "
        "create the app, grant the starter scope, share the documents onto it, put the "
        "credentials where larkdocio reads them, prove one real read. Nothing here works "
        "until an app exists, holds the scopes and can reach the documents, and none of those "
        "three is a code change. Pass section= for one step — lark_setup_sections() is the "
        "index.",
        "No API calls; reads a packaged resource.",
    ),
    "lark_setup_sections": (
        "The walkthrough's section index — one row per step, same shape as guide_sections(): "
        "the heading, its slug, and the level that says what it contains. Names only, no "
        "text. Derived from the document's own headings on every call.",
        "No API calls; reads a packaged resource.",
    ),
    "compose": (
        "Markdown in the reader's own dialect to the typed creatable content the writeback "
        "engine inserts — the authoring entry point.",
        "No API calls; compiles offline.",
    ),
    "compose_insert": (
        "The same compilation, returned as ready-to-gate insert requests for a plan.",
        "No API calls; compiles offline.",
    ),
    "compose_check": (
        "The read-only checker beside compose(): it reports EVERY construct a fragment "
        "cannot express, each with its 1-based line and the same recovery text the refusal "
        "gives, instead of stopping at the first. Run it before a migration — compose() "
        "still refuses the whole batch on the first construct, and nothing here is "
        "composable that was not composable before.",
        "No API calls; compiles offline.",
    ),
    "preflight": (
        "An OPTIONAL, ADVISORY check of whether you hold what an operation set needs, before "
        "you start: check_permissions() derives the scopes and probes the ones a read can "
        "decide, call_cost() prices that first. Never mandatory — nothing in the library "
        "calls it, it never mutates (each probe is a read against a deliberately nonexistent "
        "target), and it never widens, requests or escalates a scope. It states per scope how "
        "it knows, and names the two things it structurally cannot see (a write scope, and a "
        "field-level grant).",
        "check_permissions() spends ONE read call per distinct probeable scope family — "
        "call_cost(for_operations=[...]) returns that number for free, before you spend it. "
        "Needs read credentials only when there is something to probe.",
    ),
    "check_permissions": (
        "The advisory pre-check itself, re-exported from `larkdocio.preflight` so it is "
        "reachable without knowing the module path. Read that module's own documentation "
        "before treating a clean result as reassurance.",
        "ONE read call per distinct probeable scope family; call_cost() prices it first.",
    ),
    "__version__": (
        "The installed version string — the same one the CLI's --version reports.",
        "No API calls.",
    ),
}


def _entry_points() -> dict:
    """``{public name: EntryPoint}`` for every symbol ``larkdocio.__all__`` exports.

    **Projected off ``__all__``, never a hand-list of names.** The defect this closes is a
    discovery one: ``larkdocio.preflight`` existed, was documented in the README's layout table
    and was described inside another surface's credential note, and was still findable only
    by full-text-searching the guide — because no index a consumer would consult named it. This is that index, and because the row set is derived, the next public symbol
    cannot repeat the omission.

    Deliberately NOT ``docs``: that key is an index of packaged **Markdown documents** (one row
    per accessor, held against the packaged document set), so a callable belongs here instead.
    """
    import importlib
    import types

    package = importlib.import_module("larkdocio")
    rows = {}
    for name in package.__all__:
        target = getattr(package, name)  # a phantom export cannot survive this
        try:
            summary, cost = _ENTRY_POINT_NOTES[name]
        except KeyError:  # pragma: no cover — the guard is the projection itself
            raise KeyError(
                f"larkdocio.__all__ exports {name!r} with no entry-point summary; add one to "
                f"capabilities._ENTRY_POINT_NOTES so it is discoverable rather than merely "
                f"reachable"
            ) from None
        if isinstance(target, types.ModuleType):
            kind = "module"
        elif callable(target):
            kind = "function"
        else:
            kind = "value"
        rows[name] = EntryPoint(name=name, kind=kind, summary=summary, cost=cost)
    return rows


