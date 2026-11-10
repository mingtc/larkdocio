# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE ABSENCE-CLAIMS DRIFT GUARD — shipped prose that claims ABSENCE or FUTURITY.

Why this file exists
--------------------
This repository holds a claim of **presence** against the code in half a dozen ways: the
capability matrices, the generated permissions projection, the bidirectional front door, the
authoring-dialect table. A claim of **absence** reddened nothing, because nothing was watching
— and that asymmetry is what shipped a false sentence for eight releases. The guide announced
that an editable Markdown projection *"may"* arrive in *"a future release"*; it was written
while it was true and it kept shipping long after ``project_block_ids()`` and ``reconcile()``
had landed **in the same wheel**. A consumer built the wrong thing on it.

A false positive claim fails loudly on first use. A false negative never fails at all: nobody
re-tries a documented *cannot*, and nobody re-checks a promised *later*.

The three properties this guard holds
-------------------------------------
1. **The census.** Every forward-looking phrase in the shipped corpus (:func:`absence_corpus` —
   ``consumer_text.shipped_docs()`` plus the GENERATED front door, and **do not build a second
   corpus**) must be **claimed by exactly one registry row**. A NEW occurrence reddens; a row
   that claims nothing reddens too, so the registry cannot silt up into a suppression file.

   **The generated surface joined at LD-571**, and the miss that put it there is the same shape
   as the one above: ``capabilities()``'s ``drive-files-write`` note denied that a
   folder-creating call existed *anywhere in this library* while ``create_folder`` was listed in
   the same payload — a conclusion superseded in part by a product ruling, whose module-scoped
   half the source module had already corrected and whose library-wide half the projection kept.
   Nothing was watching, for two derivable reasons: the corpus was the authored-prose one, and
   the phrase set was **futurity-only** — a claim of a UNIVERSAL ABSENCE ("no X anywhere in this
   library") is not a promise about later, so no pattern here could see it. Both are fixed
   below, and the fix is the same one this file already makes: a registered claim with a
   falsifier the guard resolves.
2. **The falsifier.** A registration is not a comment. Each row names a **falsifier** — an
   import path, a parameter on a shipped callable, or a key path into ``capabilities()`` — that
   this guard actually resolves. *"We say X does not ship; here is the thing whose existence
   would make that false."* A row with no falsifier is refused.
3. **The bidirectional bite, which is the whole point.** A row declaring ``expect="absent"``
   whose falsifier **now resolves** REDDENS. That is the exact catch the guide needed: the
   moment ``project_block_ids`` became importable, the sentence promising it *later* became
   false, and the suite should have said so that day rather than eight versions later. The
   mirror also bites — an ``expect="present"`` row whose falsifier **vanished** reddens,
   because the prose is then citing something the wheel no longer carries.

Why ``expect="present"`` exists, and why it is not a back door
--------------------------------------------------------------
The phrase set catches two different shapes, and forcing them into one sense would either
redden honest prose forever or blind the guard to the dishonest kind:

* a **live claim of absence** — ``expect="absent"``, the shape that bit;
* prose whose falsifier legitimately DOES exist — a dated record in the append-only release
  notes ("this heading was deleted because ``project_block_ids()`` shipped"), or an
  **unmeasured disclosure**, which ``process/doctrine/negative-claims.md`` § A.1 positively
  *prescribes* ("durability beyond that week … is not yet measured, so this still makes no
  claim of permanence" — the permalink sentence as it reads after the 2026-08-15 cross-week
  measurement superseded its predecessor's conclusion).

So ``expect="present"`` is legal **only** on one of those two grounds, and the guard checks
which: the surface is a dated append-only record (:data:`DATED_RECORD_SURFACES`), or the quote
itself carries § A.1's unmeasured vocabulary (:data:`_UNMEASURED_VOCAB`). Anywhere else — in
the guide, the README, a docstring, the ``--help`` — a forward-looking claim whose falsifier
exists is simply **false**, and there is no registration for it. It is deleted or fixed.

What this guard is NOT
----------------------
It is **not a retro-audit**. ``process/doctrine/negative-claims.md`` § B's rule binds here in
its own mirror: the rule applies going forward, and a sweep that rewrites shipped claims
without fresh evidence is the same error run backwards. This file **registers** what already
ships; the sweep of the live hits was LD-422's, on the routing report's own evidence. Two rows
below are therefore marked OVERTAKEN and left standing: the census MEASURED them and says so
in the open, which is the opposite of an audit that quietly rewrites them.

Scope note: this guard pins a **process** property (does shipped prose keep its promises?), not
a product claim about Lark's API, so it is deliberately **not** conformance-tier — see
``process/doctrine/conformance-tier.md`` § "Product wrong → conformance. Merely different →
leave it".
"""
import dataclasses
import importlib
import inspect
import pathlib
import re
import sys

import consumer_text
import pytest

#: The repository root — the tree the out-of-process proof below copies and shadows.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def flatten(text):
    """Collapse every whitespace run to one space.

    Load-bearing, exactly as in ``tests/test_comment_anchor_claim_guard.py``: a claim that
    splits across a line wrap is one phrase to a reader and two strings to a naive grep, and
    that is precisely how the last one hid. Every side of this guard reads flattened text, so
    reflowing a paragraph can neither hide nor reveal a claim.
    """
    return " ".join((text or "").split())


def absence_corpus():
    """The corpus this census reads: the authored shipped prose **plus the generated front door**.

    Composed, not re-enumerated — both halves are defined in ``consumer_text``, which is the one
    module that owns what "a surface a consumer reaches" means. The generated half is here
    because a claim of absence does not become less binding for having been assembled by a
    function: ``capabilities()`` is the door two of the round-5 legs landed on first.
    """
    return {**consumer_text.shipped_docs(), **consumer_text.shipped_generated_text()}


#: The generated front door's label inside :func:`absence_corpus` — read off the corpus itself so
#: a rename of the label cannot leave a registry row pointing at nothing.
GENERATED_FRONT_DOOR = next(iter(consumer_text.shipped_generated_text()))


# --------------------------------------------------------------------------- #
# 1. THE PHRASE SET — what counts as forward-looking.                          #
#                                                                             #
#    The first five are the routing report's own list, verbatim. Each addition #
#    below states its reason, because a census that is too loose passes        #
#    everything and one that is too tight turns every honest disclosure red    #
#    and gets itself deleted within a month.                                   #
# --------------------------------------------------------------------------- #

FORWARD_LOOKING_PHRASES = (
    ("future-release", re.compile(r"future release", re.IGNORECASE),
     "the report's own list — the exact phrase that shipped the false promise"),
    ("may-add", re.compile(r"may add", re.IGNORECASE),
     "the report's own list — the hedged promise half of the same sentence"),
    ("not-yet", re.compile(r"not yet", re.IGNORECASE),
     "the report's own list — the plainest futurity marker in English"),
    ("a-future-rung", re.compile(r"a future rung", re.IGNORECASE),
     "the report's own list — this repo's in-house spelling of the same promise"),
    ("does-not-ship-today", re.compile(r"does not ship today", re.IGNORECASE),
     "the report's own list — the dated-present spelling"),
    # ---- extensions, each with its reason (D-25: the reason is stated, not inferred) ----
    ("later-release", re.compile(r"\blater release\b", re.IGNORECASE),
     "ADDED: the one-word sibling of 'future release'. A promise that escapes a guard by "
     "swapping a synonym is not guarded at all."),
    ("a-fix-is-planned", re.compile(
        r"\b(?:a|an|the)\s+(?:fix|fast[- ]follow|follow[- ]up|patch|projection|successor"
        r"|replacement|rewrite)\s+(?:is|are)\s+planned\b", re.IGNORECASE),
     "ADDED, and deliberately SCOPED to the promise idiom: this repo already had to forbid "
     "'a fix is planned' by hand once (tests/test_comment_anchor_claim_guard.py::_FIX_PLANNED, "
     "after the fix landed and the prose did not) — that was the class instance and this is "
     "the class. The bare passive is NOT usable as the pattern, because 'is planned' is this "
     "project's own PLANNER verb ('the segment is planned as an insert', 'built against ids "
     "that exist when it is planned'): an unscoped version flags the domain vocabulary on "
     "every recipe, and a guard that cries wolf is a guard somebody deletes."),
    ("has-not-shipped", re.compile(r"\b(?:has|have)\s+not\s+shipped\b|does not ship yet",
                                   re.IGNORECASE),
     "ADDED: the perfect-tense sibling of 'does not ship today'. Same claim, different "
     "auxiliary — and the auxiliary is not what makes it dangerous."),
    ("universal-absence", re.compile(
        r"\bno[a-z]*\b[^.;]{0,90}?\banywhere in this (?:library|module|package|wheel)\b",
        re.IGNORECASE),
     "ADDED (LD-571), and it is a DIFFERENT SENSE from every pattern above: those catch a "
     "promise about later, this catches a claim about EVERYWHERE — 'no folder-creating call "
     "anywhere in this library' while create_folder shipped in the same payload. The scope word "
     "is what makes it dangerous: a claim scoped to a module is checkable by reading that "
     "module, and a claim scoped to the library is a statement about code the writer did not "
     "read, which is exactly the half a partial supersession leaves behind. Deliberately "
     "ANCHORED to that scope idiom rather than to the bare quantifiers: measured on the real "
     "corpus, 'never' occurs 140 times, 'every' 152 and 'nothing' 124 — a pattern reaching for "
     "those flags honest prose by the hundred and gets itself deleted, while this one names the "
     "shape that actually shipped false."),
    ("member-absence", re.compile(
        r"\b(?:there\s+is\s+(?:still\s+)?no|and\s+no)\s+"
        r"\*{0,2}`\.?[A-Za-z_][\w.]*(?:\(\))?`\*{0,2}"
        r"\s+on\s+(?:a|an|the)?\s*\*{0,2}`\.?[A-Za-z_][\w.]*(?:\(\))?`", re.IGNORECASE),
     "ADDED (LD-618), and it is a THIRD SENSE: not a promise about later, not a claim about "
     "everywhere, but a claim that a NAMED MEMBER IS ABSENT FROM A NAMED OWNER — 'There is no "
     "`allow_missing` on `DeleteRequest`'. It needed its own pattern because it carries no "
     "futurity marker at all (it is a claim about NOW, deliberately — the sentence exists to "
     "stop a caller hunting for a flag) and no scope word, so neither the futurity set nor "
     "universal-absence could see it: a product ruling upheld that sentence as a promise on "
     "2026-09-02 while nothing under tests/ greps it and no pattern here matched it, so the flag "
     "could have landed and the shipped sentence become a lie in silence. "
     "**Both identifiers must be BACKTICKED, and that is the deliberate boundary, not an "
     "oversight.** Two identifiers in code voice are what make the claim mechanically "
     "falsifiable — it is precisely the param:<owner>#<member> shape this guard already resolves "
     "by import and introspection, so every hit it produces can be REGISTERED rather than "
     "argued about. The looser readings are what a guard dies of (measured 2026-09-02 over this "
     "same corpus): bare 'does not exist' occurs 29 times and 'no such' 19, nearly all of them "
     "honest prose about Lark's own API or about a record a caller asked for; and dropping the "
     "backtick from the OWNER alone pulls in 'There is no `If-Match` on the Base API' and "
     "'There is no `parent_id` on a record' — claims about LARK, with no importable falsifier "
     "at all. Member-absence claims wearing a PROSE owner ('There is no `.records` on the read "
     "model') are a real and wider class this pattern does not reach: enumerated, and "
     "deliberately not swept, by the issue that added this row. "
     "**AMENDED (LD-623): the opener now also reads the ELIDED conjunct 'and no `<member>` on "
     "a `<owner>`'**, which is the one LD-618's QA named as the highest-value miss of the four "
     "it enumerated — *'missed only for want of a second there is'*. The guide's sentence is "
     "'There is no `.records` on the read model AND NO `.raw()` on a `BaseRow`': the first "
     "half wears the prose owner this sense declines, and the second half wears a BACKTICKED "
     "owner with an importable falsifier and was invisible only because English does not "
     "repeat the verb. Nothing else is loosened — both identifiers are still backticked, and "
     "the whole conjunct measured ONE new hit over the whole shipped corpus (the `.raw()` "
     "half) and zero false positives, 2026-09-03."),
    ("op-absence", re.compile(
        r"\bthere\s+(?:is|are)\s+(?:still\s+)?no\s+\*{0,2}`[A-Za-z_][\w.\-]*`\*{0,2}"
        r"\s+op(?:eration)?s?\b", re.IGNORECASE),
     "ADDED (LD-623), and it is a FOURTH SENSE: a claim that a named OPERATION does not exist "
     "— 'There is no `clear` op'. It is not member-absence and was explicitly excluded from "
     "it (that sense's own calibration probe listed this very sentence under 'honest', with "
     "the reason 'an op, not a member of a named owner'). **That reason is preserved and only "
     "its conclusion moves**: an op has no owner to backtick, but it does have a mechanically "
     "resolvable falsifier of its own — `capabilities()` names every operation of every "
     "surface, so an op that landed would appear there by NAME, which is what the "
     "operation:<surface>#<name> falsifier kind resolves. Anchored to the word 'op' / "
     "'operation' immediately after the backticked name, which is why it does not reach the "
     "hundreds of honest sentences mentioning an op in passing: measured over the whole "
     "shipped corpus on 2026-09-03 it produces exactly ONE hit."),
    ("dotted-member-absence", re.compile(
        r"\bthere\s+is\s+(?:still\s+)?no\s+(?:#\s*)?"
        r"\*{0,2}`[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+(?:\(\.\.\.\)|\(\))?`", re.IGNORECASE),
     "ADDED (LD-623), and it is the SAME CLAIM as member-absence in a DIFFERENT GRAMMAR: the "
     "owner and the member arrive already joined, in one backticked dotted expression — "
     "'THERE IS NO `draft.create`' — so the ' on `<owner>`' clause the member-absence sense "
     "hangs on is simply not there to match. Two name segments are REQUIRED (`\\w+\\.\\w+`), "
     "which is what keeps it off the bare-member spellings the sense above already owns and "
     "off a leading-dot accessor ('no `.records`'). Resolving it needs one human step "
     "member-absence does not — the RECEIVER is a local variable name, not a type — so the "
     "registry row names the class the guide's own recipe binds that variable to, and says "
     "which line binds it. **The '#' tolerance is deliberate and it is the same argument as "
     "flatten():** this claim ships twice in the guide, once in prose and once inside a "
     "commented code example where the line wrap puts a '# ' between 'no' and the name. A "
     "shipped code comment is prose to the consumer reading it, and a claim must not become "
     "invisible for having been wrapped. Measured over the whole shipped corpus on "
     "2026-09-03: exactly TWO hits, both of them that claim."),
)


def forward_looking_hits(corpus):
    """``[(surface, phrase_name, matched, start, end)]`` over the FLATTENED text of each entry.

    Spans are into the flattened text, so a row's quote (also flattened) can claim the
    occurrences that fall inside it by position rather than by fuzzy matching.
    """
    hits = []
    for surface, raw in corpus.items():
        flat = flatten(raw)
        for name, pattern, _reason in FORWARD_LOOKING_PHRASES:
            for match in pattern.finditer(flat):
                hits.append((surface, name, match.group(0), match.start(), match.end()))
    return sorted(hits)


# --------------------------------------------------------------------------- #
# 2. THE REGISTRY — one place, readable as a list of promises.                  #
# --------------------------------------------------------------------------- #

#: The surfaces that are APPEND-ONLY DATED RECORDS. A sentence under a shipped version heading
#: is history: it was true of that release, and history is not edited (the release notes are
#: the one document this project accumulates rather than revises). That is the ONLY structural
#: reason a forward-looking claim may stand next to a falsifier that exists — and it is why an
#: overtaken sentence here is registered-and-labelled rather than rewritten.
DATED_RECORD_SURFACES = frozenset({"release_notes() (the packaged RELEASE_NOTES.md)"})

#: ``process/doctrine/negative-claims.md`` § A.1's prescribed honest shape. A claim wearing it
#: is not promising a capability; it is scoping its own evidence, which the doctrine *requires*.
#: A guard that reddened on this would be punishing the behaviour it exists to encourage.
_UNMEASURED_VOCAB = re.compile(
    r"\bunmeasured\b|\bnot\s+(?:yet\s+)?been\s+measured\b|\bnot\s+(?:yet\s+)?established\b"
    r"|\bno\s+claim\s+of\b|\bnot\s+refuted\b",
    re.IGNORECASE,
)

_FALSIFIER_GRAMMAR = re.compile(
    r"^(?:symbol:(?P<symbol>[A-Za-z_][\w.]*)"
    r"|param:(?P<owner>[A-Za-z_][\w.]*)#(?P<param>[A-Za-z_]\w*)"
    r"|capability:(?P<key>[\w.\-]+)"
    r"|operation:(?P<surface>[\w.\-]+)#(?P<op>[\w.\-]+))$"
)

EXPECTATIONS = ("absent", "present")


@dataclasses.dataclass(frozen=True)
class ForwardClaim:
    """One registered forward-looking claim — a promise, with the thing that would falsify it.

    :param surface: the ``consumer_text.shipped_docs()`` label the claim ships on.
    :param quote: enough of the sentence, FLATTENED, to identify it. Verified to occur in that
        surface exactly once, so a reworded or deleted claim leaves a stale row that reddens
        instead of a silent suppression that does not.
    :param falsifier: ``symbol:<dotted>`` / ``param:<dotted>#<name>`` / ``capability:<key.path>``
        / ``operation:<surface>#<op-name>``
        — **the thing whose existence would make the claim false**. Required; a row without one
        is refused.
    :param expect: ``"absent"`` (the falsifier must NOT resolve — the live claim) or
        ``"present"`` (it must, and the row must earn that on one of the two grounds above).
    :param why: one line a reviewer can read and ask *"is this still true?"* without opening
        the shipped document.
    :param also: further falsifiers **for the same sentence**, each held to ``expect`` exactly
        as :attr:`falsifier` is. It exists because one sentence can deny two things at once —
        the guide's *"There is no ``.records`` on the read model and no ``.raw()`` on a
        ``BaseRow``"* is two claims and one quote, and the alternative (two rows quoting the
        same sentence) makes one of them a DEAD ROW by construction, since only the second half
        produces a census hit. It also lets a row name **both spellings a single member could
        land in** — a dataclass field is visible to ``param:`` and a property to ``symbol:``,
        and a claim that a member is absent is falsified by either. Defaults to empty, so a row
        that denies one thing reads exactly as it did before.
    """

    surface: str
    quote: str
    falsifier: str
    expect: str
    why: str
    also: tuple = ()

    @property
    def falsifiers(self):
        """Every falsifier this row is held to — :attr:`falsifier` first, then :attr:`also`."""
        return (self.falsifier,) + tuple(self.also)


#: THE REGISTRY — read it top to bottom and ask of each row: *is this still true?*
#:
#: The census that seeded it was taken AFTER LD-422's sweep of the live hits (that ordering was
#: the intended one), and it measured **8 phrase occurrences across 7 claims** — 2 in
#: ``guide()`` and 6 in ``release_notes()``. Not one survives in the guide as a *promise*: both
#: guide rows are unmeasured disclosures, which the doctrine prescribes. Every promise left is
#: in the append-only release notes, under a dated version heading.
#:
#: **Three of those six are OVERTAKEN and are labelled so, not rewritten.** That labelling IS
#: the finding: the census, on its first run, caught two class-mates of the report's Finding 1
#: that the sweep did not reach — a create-time default-view name and an email-to-``open_id``
#: verb, both promised as future work and both since shipped. They stand because the release
#: notes are a dated record and this issue is not a retro-audit (§ B's rule, mirrored); a LIVE
#: document may not repeat any of them, and ``registry_defects`` refuses the attempt.
#:
#: No row needs the ``capability:`` kind yet: ``capabilities()``'s ``operations`` are LISTS, so
#: a key path into one is positional and would redden on a cosmetic reorder — a falsifier that
#: cries wolf is a falsifier somebody deletes. Every capability it registers is projected from a
#: symbol, and ``symbol:`` reaches the same fact stably. The kind is supported and exercised in
#: the deliberate-defect proofs below, so it is available the day a keyed region needs it.
REGISTRY = (
    ForwardClaim(
        surface="guide()",
        quote="is not yet measured, so this still makes no claim of permanence",
        falsifier="symbol:larkdocio.base.record_permalink",
        expect="present",
        why="TRANSFORMED, not dropped — the re-probe this row's own 'why' said was owed landed "
            "on 2026-08-15 (five links, five byte-identical at seven and eight days), so the "
            "sentence was rewritten and the row moved onto it. What survives is the same SHAPE: "
            "an unmeasured disclosure scoping a measured claim, now covering what is still "
            "unknown (beyond a week, another tenant, a deleted record) rather than the week "
            "itself. It would be falsified by a measurement past week scale or on a second "
            "tenant — which is a fresh probe, and would rewrite this sentence again. The "
            "falsifier stays the surface it scopes: if the permalink verb goes away, the "
            "paragraph is orphaned prose about a capability the wheel no longer has.",
    ),
    ForwardClaim(
        surface="guide()",
        quote="lets you plan against what is not yet established",
        falsifier="symbol:larkdocio.base.shape_docs.FILTER_EVIDENCE_CLASSES",
        expect="present",
        why="Not a claim about a capability at all — it is the LEGEND for the filter-shape "
            "table's evidence labels, explaining why a row saying 'unmeasured' is worth more "
            "than one presenting itself as proven. The falsifier is the label vocabulary the "
            "legend describes; if that tuple goes, the legend explains nothing and must be "
            "re-read.",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="**Parked for the next release** (a fast-follow is planned)",
        falsifier="symbol:larkdocio.sheets.ops.TAB_PRESENTATION_OPS",
        expect="present",
        why="OVERTAKEN — the fast-follow shipped. Tab reorder / hide / retitle and the cell "
            "style and border writes all landed in later releases, so the parked list is "
            "history. It stands only because it sits under a dated heading in an append-only "
            "record; the falsifier is the tab-presentation op set that closed it.",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="A future release may add an editable Markdown projection",
        falsifier="symbol:larkdocio.model.projection.project_block_ids",
        expect="present",
        why="This is the RECORD OF THE DELETION, not the claim: the note quotes the heading "
            "that was removed and says plainly that it described a capability which has since "
            "shipped. The falsifier is the symbol it names — the record is only readable while "
            "that symbol is in the wheel.",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="naming the default view **as part of a create** is a candidate for a future "
              "release, not something 1.29.0 ships",
        falsifier="param:larkdocio.base.schema_plan.create_table#default_view_name",
        expect="present",
        why="OVERTAKEN, and found by this census rather than by a consumer: the knob shipped "
            "after 1.29.0 as a non-atomic composite (create the table, then rename the view it "
            "is born with). True of 1.29.0, false of the library today. Had this registry "
            "existed at 1.29.0 the row would have read expect='absent' and gone RED the day "
            "that parameter landed — which is the whole point of the sense being declared.",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="so an email is not yet an address you can hand this library",
        falsifier="param:larkdocio.contacts.resolve_colleague#email",
        expect="present",
        why="OVERTAKEN, same class as the row above: the note said the reach was measured but "
            "that no verb offered it, and a later release shipped exactly that verb — an "
            "address now resolves to one open_id or refuses in a typed way. Dated record, left "
            "standing and labelled.",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="what the API returns on a read uses a different shape this library does not yet "
              "decode",
        falsifier="symbol:larkdocio.sheets.read.dropdown_rules",
        expect="absent",
        why="STILL TRUE, and one of the live claims of absence in the corpus: a dropdown's colors "
            "are written positionally and the read-back shape is not decoded, so a written "
            "color cannot be confirmed by reading the rule back. The falsifier is the read-side "
            "accessor that decoding would land as; the day it exists this row goes red and the "
            "sentence gets fixed.",
    ),
    ForwardClaim(
        surface=GENERATED_FRONT_DOOR,
        quote="grids and colors — each a future rung, never silently approximated",
        falsifier="symbol:larkdocio.write.model.requests.NewBlockKind.CALLOUT",
        expect="absent",
        why="STILL TRUE, and surfaced by the corpus widening rather than by a report: the "
            "creatable floor names what a NewBlock cannot be and calls each one a future rung. "
            "NewBlockKind is a CLOSED enum, so any of those shipping arrives as a new member of "
            "it; the falsifier is the head of the list the sentence promises, and the day a "
            "callout is creatable this row reddens and the floor gets re-cut.",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="note claimed there was *no folder-creating call anywhere in this library*",
        falsifier="symbol:larkdocio.drive.folders_write.DriveFoldersWriteClient.create_folder",
        expect="present",
        why="THE RECORD OF THE CORRECTION, not the claim — the same shape as the "
            "project_block_ids row above, and caught by this census on its first run over the "
            "new phrase class rather than by review. The `## [1.41.0]` note quotes the "
            "sentence that was fixed so a consumer who asked an administrator for something "
            "on its strength can find out; the falsifier is the call whose existence made "
            "the old scope false, and the record is only readable while that call is in "
            "the wheel.",
    ),
    # ---- the UNIVERSAL-ABSENCE class, which the futurity-only phrase set could not see ----
    ForwardClaim(
        surface=GENERATED_FRONT_DOOR,
        quote="no default folder, no root-folder resolution and no folder-creating call "
              "anywhere in this module",
        falsifier="symbol:larkdocio.drive.files_write.DriveFilesWriteClient.create_folder",
        expect="absent",
        why="TRANSFORMED, not dropped — and the transformation is the whole of LD-571's first "
            "defect. Registered first as it SHIPPED (*anywhere in this library*, falsifier "
            "larkdocio.drive.folders_write.DriveFoldersWriteClient.create_folder), where it went "
            "RED on the spot because that falsifier resolves and the call is listed in the same "
            "payload. The projection now carries the module's own constant, so the row moved "
            "onto the scoped sentence and its falsifier moved with it: the claim is that THIS "
            "module creates no folder, and a create_folder on its client is what would make "
            "that false. The reason the sentence was written is unchanged. The red state is kept "
            "reproducible, not just recorded — see the deliberate-defect proof below.",
    ),
    ForwardClaim(
        surface="writer_brief()",
        quote="this half does not narrow: there is no op for them anywhere in this library, in "
              "band or out",
        falsifier="symbol:larkdocio.write.model.requests.NewBlockKind.BOARD",
        expect="absent",
        why="STILL TRUE, and found by the new phrase class rather than reported: boards and "
            "embeds are structurally inexpressible and no verb creates one. The falsifier is the "
            "CREATABLE-KIND vocabulary — the enum the creatable-content floor is projected from "
            "— because that is where a board create has to appear for the authoring dialect to "
            "reach it; an out-of-band verb would land as its own operation and move the surface "
            "row too, which the capability matrix guard reads.",
    ),
    # ---- the MEMBER-ABSENCE class: a named flag denied on a named request type (LD-618) ----
    ForwardClaim(
        surface="guide()",
        quote="**There is no `allow_missing` on `DeleteRequest`** — the flag does not exist, and "
              "nothing below waits for one",
        falsifier="param:larkdocio.write.model.requests.DeleteRequest#allow_missing",
        expect="absent",
        why="STILL TRUE, and it is a PRODUCT RULING as of 2026-09-02, which is why the row "
            "exists: the flag was asked for by a consumer, the idempotent-delete recipe this "
            "sentence sits in shipped instead, and adding the flag was declined — it only ever "
            "reaches a caller who disarmed the whole-document compare-and-swap, and it would "
            "write the first exception into exactly-one-or-refuse. The ruling did not weld the "
            "door shut, which is the whole reason a falsifier is needed: reopening it is one "
            "ruling, and the day the field lands on the dataclass this row goes red and the "
            "sentence must be re-cut in the SAME change. The falsifier is the parameter itself, "
            "resolved off the class's own signature — the definition site, not a re-export, and "
            "not a grep of the source text (a grep would pass on a differently spelled field "
            "and fail on a comment).",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="**There is still no `allow_missing` on `DeleteRequest`, and none is promised.**",
        falsifier="param:larkdocio.write.model.requests.DeleteRequest#allow_missing",
        expect="absent",
        why="THE SAME CLAIM, on a SECOND shipped surface — found by the census the moment the "
            "member-absence pattern existed, and the reason the pattern reads 'there is "
            "(still) no' rather than only the guide's spelling. It is 'absent' and not "
            "'present' even though the notes are a dated record: the claim is TRUE today, so a "
            "'present' row would redden as THE GROUND IS GONE. If the flag is ever ruled in, "
            "this row does not simply flip — the guide's sentence is a lie and gets re-cut, "
            "while THIS one is history under a dated heading and becomes an OVERTAKEN "
            "expect='present' row, the same transformation the create-time default-view row "
            "above already went through.",
    ),
    # ---- LD-623: the four claims LD-618's AC6 enumerated and could not yet see ------------ #
    ForwardClaim(
        surface="guide()",
        quote="There is no `.records` on the read model and no `.raw()` on a `BaseRow`",
        falsifier="symbol:larkdocio.base.table.BaseRow.raw",
        expect="absent",
        also=("param:larkdocio.base.table.BaseTableRead#records",
              "symbol:larkdocio.base.table.BaseTableRead.records"),
        why="STILL TRUE, and LD-618's QA called it the highest-value of the four it "
            "enumerated — *'missed only for want of a second there is'*. **One sentence, two "
            "claims, and they are pinned on different grounds; that difference is the point.** "
            "The `.raw()` half wears a BACKTICKED owner, so the census sense reaches it once "
            "the elided conjunct is read and its falsifier is the method itself, resolved off "
            "the class. The `.records` half wears a PROSE owner ('the read model'), which the "
            "SENSE still declines and must keep declining — a pattern that guessed a type from "
            "a noun phrase would be the LD-609 defect, a guard whose subject is its own "
            "invention. But a HAND-AUTHORED row is not a pattern: the guide's own object table "
            "eleven lines above this sentence defines the term — *'`BaseTableRead` — the read "
            "model'* — so the owner here is CITED, not guessed, and both of its landing "
            "spellings are named because a dataclass field is visible to `param:` and a "
            "property only to `symbol:`. If that table is ever re-cut so 'the read model' names "
            "something else, this row's quote still occurs and its falsifiers still resolve — "
            "which is the residual this row cannot close, and the reason the SENSE stays narrow "
            "while the ROW is allowed to reach further.",
    ),
    ForwardClaim(
        surface="guide()",
        quote="**There is no `clear` op** — `capabilities()` lists nine sheets-write operations",
        falsifier="operation:sheets-write#clear",
        expect="absent",
        why="STILL TRUE of the op, and the first row of the operation: kind — an op has no "
            "owner to backtick, so it is addressed by the NAME it publishes in "
            "`capabilities()`, which a cosmetic reorder cannot move (the objection the registry "
            "note above raised against a positional `capability:` path into the same list). The "
            "day a `clear` descriptor is registered in `larkdocio.sheets.ops.OPS` the "
            "projection names it and this row goes red, and the recipe — whose whole point is "
            "that `[[None]]` IS the clear — must be re-cut in the same change. **The COUNT in "
            "this same sentence is a SECOND claim and it is NOT held by this row**: a tenth "
            "op would make 'nine' false without any `clear` appearing, so it is derived "
            "separately in test_the_STATED_COUNTS_are_DERIVED_from_the_code — where LD-626 "
            "reworded the stale 'six' to the derived 'nine' and dropped the quarantine, so "
            "that row now holds the number by derivation alone.",
    ),
    ForwardClaim(
        surface="guide()",
        quote="**CREATING A ROW IS `draft.add(...)`. THERE IS NO `draft.create`.**",
        falsifier="symbol:larkdocio.base.model.TableDraft.create",
        expect="absent",
        why="STILL TRUE. The claim's receiver is a LOCAL VARIABLE ('draft'), not a type, which "
            "is the one step this grammar needs that member-absence does not — so the row names "
            "the binding rather than inferring it: the recipe this sentence heads binds "
            "`draft = snapshot.edit()` (the guide's records-write walkthrough), and "
            "`BaseTableSnapshot.edit()` returns a `TableDraft`, whose four verbs are exactly "
            "the four the sentence's own table lists. The falsifier is a `create` attribute on "
            "that class: the day it exists, the AttributeError the guide promises becomes a "
            "call and the sentence is a lie. It is a `symbol:` and not a `param:` because what "
            "would land is a METHOD.",
    ),
    ForwardClaim(
        surface="guide()",
        quote="There is no # `draft.create` — a reasonable guess from this library's op names",
        falsifier="symbol:larkdocio.base.model.TableDraft.create",
        expect="absent",
        why="THE SAME CLAIM, a second time on the same surface — inside the commented code "
            "example of the same recipe, where the line wrap puts a '# ' between 'no' and the "
            "name (the quote is FLATTENED, so it reads as the census reads it). Registered as "
            "its own row rather than folded into the one above because the two sentences are "
            "eighty lines apart and a re-cut of one would leave the other shipping: a shipped "
            "code comment is prose to the consumer reading it, and this is the second place a "
            "caller is told the verb does not exist.",
    ),
    ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="It will change only in a **later release that names the change in its own "
              "section**",
        falsifier="symbol:larkdocio.read.download.DownloadResult.unknown_block_types",
        expect="present",
        why="KEPT rather than deleted, on the doctrine's own exception: a reader must plan "
            "around this one NOW. The `Unknown block type <N> (block_id=` warning is a de "
            "facto API — a consumer parses it today — and this release ships the structured "
            "key that replaces the parse while deliberately NOT freeing the warning's text. "
            "The sentence is what tells that consumer they may migrate at their own pace and "
            "will not be surprised: without it, the only honest reading of a new key beside an "
            "unchanged line is 'the line is about to move'. The falsifier is the key itself, "
            "`present`: while it is in the wheel the promise has something to promise about, "
            "and the day it leaves, this paragraph is orphaned prose telling a consumer to "
            "migrate onto something the wheel no longer has — which is exactly the state a "
            "reader must be forced to re-read. The freeing itself will be announced in its own "
            "dated section, and THIS row is what makes that a decision: rewording or removing "
            "this sentence leaves a stale row that reddens.",
    ),
)


# --------------------------------------------------------------------------- #
# 3. THE FALSIFIER RESOLVER — three kinds, each really resolved.                #
# --------------------------------------------------------------------------- #

def _resolve_dotted(path):
    """Import as deep as possible, then walk attributes. ``None`` when it does not resolve."""
    parts = path.split(".")
    module, rest = None, parts
    for cut in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        rest = parts[cut:]
        break
    if module is None:
        return None
    obj = module
    for name in rest:
        if not hasattr(obj, name):
            return None
        obj = getattr(obj, name)
    return obj


_MISSING = object()


def _walk_capabilities(key_path):
    """Walk a dot path into ``larkdocio.capabilities()``; ``_MISSING`` when absent."""
    import larkdocio

    node = larkdocio.capabilities(full=True)
    for key in key_path.split("."):
        if isinstance(node, dict) and key in node:
            node = node[key]
            continue
        return _MISSING
    return node


def surface_operation_names(surface):
    """``{op name}`` for one ``capabilities()`` surface — by NAME, never by position.

    The registry's own note said no row needed the ``capability:`` kind because
    ``capabilities()``'s ``operations`` are LISTS, so a key path into one is positional and
    would redden on a cosmetic reorder. That reason is untouched, and this is the answer to it
    (LD-623): an operation is addressed by the **name** it publishes, which is exactly the fact
    a claim of *"there is no ``clear`` op"* denies, and a reorder cannot move it. Every entry is
    read — ``operation``, ``leg`` and ``lifecycle`` alike — because a caller reaching for a
    ``clear`` would not care which kind it arrived as.
    """
    node = _walk_capabilities(f"surfaces.{surface}.operations")
    if node is _MISSING or not isinstance(node, list):
        return None
    return {entry.get("name") for entry in node if isinstance(entry, dict)}


def falsifier_resolves(falsifier):
    """Does the named thing EXIST today? The one question every row is checked against."""
    match = _FALSIFIER_GRAMMAR.match(falsifier or "")
    if not match:
        raise ValueError(f"malformed falsifier: {falsifier!r}")
    if match.group("surface"):
        names = surface_operation_names(match.group("surface"))
        if names is None:
            raise ValueError(
                f"falsifier {falsifier!r} names a surface capabilities() does not publish — "
                f"a falsifier that cannot be resolved reads as coverage and is not coverage")
        return match.group("op") in names
    if match.group("symbol"):
        return _resolve_dotted(match.group("symbol")) is not None
    if match.group("owner"):
        owner = _resolve_dotted(match.group("owner"))
        if owner is None:
            return False
        try:
            signature = inspect.signature(owner)
        except (TypeError, ValueError):
            return False
        return match.group("param") in signature.parameters
    return _walk_capabilities(match.group("key")) is not _MISSING


# --------------------------------------------------------------------------- #
# 4. THE CHECKERS — exposed so the deliberate-defect proofs drive them directly. #
# --------------------------------------------------------------------------- #

#: ``{surface label: the release document it reads}`` — the shipped surfaces that carry a
#: recent-N WINDOW of a document the repository keeps whole (LD-540). A row whose quote sits in a
#: release section that has rolled out of the window is neither STALE nor DEAD: its promise simply
#: stopped shipping, which is the one disposition this registry did not have a name for.
WINDOWED_SURFACES = {
    "release_notes() (the packaged RELEASE_NOTES.md)": "RELEASE_NOTES.md",
}


def window_retired(row, corpus):
    """True if ``row``'s quote is absent from its surface **because the window rolled past the
    release it was written in** — proven, not assumed.

    **Why this disposition exists (LD-540).** The wheel now carries the newest N release sections
    of the notes while the repository keeps every one of them, so a forward-looking promise written
    into an old release stops being a promise the WHEEL makes. The registry's two complaints assume
    otherwise: "the quote no longer occurs" reads as *reworded or deleted*, and "claims no
    forward-looking phrase" reads as *silt*. Neither is true here, and pinning either would turn
    this registry into a per-release re-cut for nothing.

    **Nothing is taken on trust.** The proof is delegated to ``notes_claim_copies``, which raises
    if the quote is gone from the AUTHORING SOURCE too (a real deletion or rewording — still a
    defect, still red) and asserts that a quote missing from the packaged copy has a section
    genuinely older than the window (a quote lost while its section is still in-window — also
    still red). So this returns True only for the one case it names.

    **What is NOT weakened:** an unregistered forward-looking hit still reddens, a row with no
    falsifier still reddens, and a row whose ``expect="absent"`` falsifier now resolves still
    reddens. Retiring with the window costs a row nothing but its census obligation.
    """
    name = WINDOWED_SURFACES.get(row.surface)
    if name is None:
        return False
    if flatten(row.quote) in flatten(corpus.get(row.surface, "")):
        return False
    from test_shipped_notes import notes_claim_copies

    notes_claim_copies(name, row.quote, normalize=flatten)
    return True


def registry_defects(registry, corpus):
    """``[str]`` — every STRUCTURAL fault in the registry (no falsifier, stale quote, …)."""
    defects = []
    for row in registry:
        where = f"{row.surface} :: {row.quote[:60]!r}"
        if row.expect not in EXPECTATIONS:
            defects.append(f"{where}: expect={row.expect!r} is not one of {EXPECTATIONS}")
        if not (row.falsifier or "").strip():
            defects.append(
                f"{where}: NO FALSIFIER. A registration is not a comment — name the import "
                f"path, parameter or capabilities key whose existence would make this claim "
                f"false, or delete the claim."
            )
        for one in row.falsifiers:
            if not (one or "").strip():
                continue  # the primary's blankness is already reported above
            if not _FALSIFIER_GRAMMAR.match(one):
                defects.append(
                    f"{where}: falsifier {one!r} is not symbol:<dotted> / "
                    f"param:<dotted>#<name> / capability:<key.path> / "
                    f"operation:<surface>#<op-name>"
                )
        if len((row.why or "").strip()) < 20:
            defects.append(f"{where}: no usable 'why' — a reviewer cannot re-check a blank")
        if row.surface not in corpus:
            defects.append(f"{where}: surface is not in the census corpus (absence_corpus())")
            continue
        flat = flatten(corpus[row.surface])
        occurrences = flat.count(flatten(row.quote))
        if occurrences == 0 and window_retired(row, corpus):
            # LD-540: the promise stopped SHIPPING because the window rolled past its release —
            # proven against the authoring source by window_retired(), never assumed. The row
            # stands as the record of a promise that was made and is no longer made.
            continue
        if occurrences == 0:
            defects.append(
                f"{where}: the quote no longer occurs on that surface — the claim was reworded "
                f"or deleted, so this row is stale. Re-cut it or drop it."
            )
        elif occurrences > 1:
            defects.append(
                f"{where}: the quote occurs {occurrences} times — widen it so the row names one "
                f"claim, not a class of them"
            )
        if row.expect == "present" and (
            row.surface not in DATED_RECORD_SURFACES
            and not _UNMEASURED_VOCAB.search(row.quote)
        ):
            defects.append(
                f"{where}: expect='present' on a LIVE document. A forward-looking claim whose "
                f"falsifier already exists is simply FALSE there — delete it or fix it. "
                f"'present' is earned only by an append-only dated record "
                f"({sorted(DATED_RECORD_SURFACES)}) or by an unmeasured disclosure in the "
                f"doctrine's own vocabulary."
            )
    return defects


def census_defects(registry, corpus):
    """``[str]`` — unregistered phrase occurrences, and rows that claim nothing."""
    claimed = {id(row): 0 for row in registry}
    spans = []
    for row in registry:
        flat = flatten(corpus.get(row.surface, ""))
        start = flat.find(flatten(row.quote))
        if start >= 0:
            spans.append((row.surface, start, start + len(flatten(row.quote)), row))

    defects = []
    for surface, name, matched, start, end in forward_looking_hits(corpus):
        owners = [row for s, lo, hi, row in spans if s == surface and lo <= start and end <= hi]
        if not owners:
            flat = flatten(corpus[surface])
            snippet = flat[max(0, start - 90):end + 90]
            defects.append(
                f"UNREGISTERED forward-looking claim in {surface} [{name}: {matched!r}]\n"
                f"      …{snippet}…\n"
                f"      Either DELETE it (roadmap prose in a shipped document is "
                f"deletion-first) or register it in REGISTRY with a falsifier."
            )
            continue
        for row in owners:
            claimed[id(row)] += 1

    for row in registry:
        if claimed[id(row)] == 0:
            if window_retired(row, corpus):
                # LD-540: not silt — a promise whose release rolled out of the shipped window.
                continue
            defects.append(
                f"DEAD ROW — {row.surface} :: {row.quote[:60]!r} claims no forward-looking "
                f"phrase. The registry is a list of live promises, not a suppression file."
            )
    return defects


def falsifier_defects(registry):
    """``[str]`` — the bidirectional bite: reality disagrees with what a row declared."""
    defects = []
    for row in registry:
        for one in row.falsifiers:
            if not _FALSIFIER_GRAMMAR.match(one or ""):
                continue  # a malformed falsifier is registry_defects()' complaint, not this one
            exists = falsifier_resolves(one)
            if row.expect == "absent" and exists:
                defects.append(
                    f"THE CLAIM IS NOW FALSE — {row.surface} :: {row.quote[:70]!r}\n"
                    f"      says this does not ship, but its falsifier {one} RESOLVES "
                    f"today. This is the catch the guard exists for: fix or delete the sentence "
                    f"NOW, not when a consumer reports it."
                )
            if row.expect == "present" and not exists:
                defects.append(
                    f"THE GROUND IS GONE — {row.surface} :: {row.quote[:70]!r}\n"
                    f"      cites {one}, which no longer resolves. The prose points at "
                    f"something the wheel does not carry; re-read it."
                )
    return defects


# --------------------------------------------------------------------------- #
# 5. THE LIVE GUARD — the three properties, over the real shipped corpus.        #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def corpus():
    return absence_corpus()


def test_every_forward_looking_claim_IN_THE_WHEEL_is_registered(corpus):
    """Property one. A new forward-looking sentence in any shipped surface reddens here until
    somebody either deletes it or writes down what would make it false."""
    defects = census_defects(REGISTRY, corpus)
    assert not defects, "\n  " + "\n  ".join(defects)


def test_every_registered_claim_carries_a_usable_FALSIFIER(corpus):
    """Property two, structural half: no blank falsifier, no malformed one, no stale quote, and
    no 'present' smuggled onto a live document."""
    defects = registry_defects(REGISTRY, corpus)
    assert not defects, "\n  " + "\n  ".join(defects)


def test_no_registered_claim_has_been_OVERTAKEN_BY_THE_CODE():
    """Property three, live. This is the assertion that would have gone red the day
    ``project_block_ids`` landed, instead of eight releases later in a consumer's report."""
    defects = falsifier_defects(REGISTRY)
    assert not defects, "\n  " + "\n  ".join(defects)


def _repository_release_notes():
    """The complete ``RELEASE_NOTES.md`` — the append-only record itself, not the wheel's window.

    The packaged copy is a recent-N projection (LD-540), so a dated claim rolls off it as
    releases are cut. The registry's ``present`` rows are earned by the record being
    append-only and dated, and that record is this file.
    """
    import inspect
    import pathlib

    import larkdocio

    return (pathlib.Path(inspect.getfile(larkdocio)).parents[2]
            / "RELEASE_NOTES.md").read_text("utf-8")


def test_THE_MEASURED_CENSUS_is_pinned_where_the_claims_actually_are(corpus):
    """The measurement itself, written down rather than assumed (the ordering question the
    issue asks): this census was cut **after** LD-422's sweep landed, so it is the post-sweep
    state and needs no re-cut.

    Eight phrase occurrences across seven claims when this was cut — and **the shape matters more
    than the number**, which was already this docstring's own point: the guide keeps **no promises
    at all**, only two unmeasured disclosures, and every surviving promise sits under a dated
    heading in the append-only release notes.

    **LD-540 dropped the two absolute counts and kept the shape, because the counts stopped being
    a property of a correct tree.** The wheel now ships a recent-N window of the release notes, so
    a promise rolls OFF the shipped surface at some future release with nobody authoring anything
    — the occurrence count and the per-surface tally would move on their own, and a guard that
    reddens at every release is a guard people edit instead of reading. What is asserted instead is
    every claim the note actually makes, each still exact: the registry's own size, the guide's two
    hits and that neither is a promise, and that every hit outside the guide sits on the dated
    append-only record. **What this used to prove and no longer can:** that the shipped corpus
    carries exactly eight forward-looking occurrences. Under a window that is a fact about which
    release is newest, not about whether the prose is honest.

    **LD-571 widened the corpus and the allowance with it, and the SHAPE CHANGED — which is the
    finding, not a bookkeeping edit.** The census used to be able to say that the guide keeps no
    promises and every promise left sits on a dated record. That is still true *of the authored
    prose*, and it was never true of the **generated** front door, which nothing was reading: it
    carries two live claims of absence and one live promise, and the writer brief carries a third
    claim of absence. So the allowance below names those two surfaces explicitly and every hit on
    them is registered with a falsifier — an ``expect='absent'`` row, which is the shape that
    BITES, not the ``present`` shape a dated record earns.

    **LD-618 changed the shape once more, and this time in the GUIDE — the note above said the
    guide keeps no claims of absence, and that is no longer true.** It was never true of the
    prose; it was true of what the phrase set could SEE. The ``member-absence`` sense (a named
    flag denied on a named request type) carries neither a futurity marker nor a scope word, so
    the guide's *"There is no ``allow_missing`` on ``DeleteRequest``"* — a promise a product
    ruling upheld on 2026-09-02 — matched nothing here and was grepped by no test at all. It is
    registered now, on the guide and on the packaged notes where the same claim ships a second
    time, and the guide's absence-row assertion below is INVERTED rather than deleted: the guide
    may carry claims of absence, and every one of them must be an ``expect='absent'`` row whose
    falsifier this guard resolves.

    **LD-623 widened the SENSES, not the corpus, and the guide's tally went 3 → 7.** LD-618
    enumerated four more claims of the same class and proved none of them was reachable; each
    needed a grammar rather than a wider net. Two are now read by an amended ``member-absence``
    (the elided conjunct — *"and no ``.raw()`` on a ``BaseRow``"*) and two by new senses of
    their own (``op-absence``: *"There is no ``clear`` op"*; ``dotted-member-absence``: *"THERE
    IS NO ``draft.create``"*, which ships twice, the second time inside a code comment). All
    four hits are in the **guide**, all four are registered ``expect='absent'``, and the whole
    widening produced **zero** new hits anywhere else in the corpus — measured 2026-09-03 over
    this same corpus.

    **What LD-623 deliberately did NOT add, and the measurement that decided it:** a
    ``key-absence`` sense, for the fourth of LD-618's four — *"on one shape there is no
    ``after`` key at all"*. Read widely enough to catch it, it also catches *"the same listing
    without a ``view_id`` carries no ``is_hidden`` key at all"* — a claim about **Lark's own
    response shape**, with no importable falsifier in this wheel; a registration nobody can
    honestly write is how a guard gets disabled rather than narrowed, which is the same
    measured boundary ``member-absence`` drew at the backticked owner. That claim is not left
    unguarded: it is held by a **stronger, derived mechanism** than a registry row could be —
    ``larkdocio.write.plan_field_docs`` reads ``has_after`` off the serializers themselves and
    **refuses to generate** when a shape's authored prose disagrees with it, while
    ``tests/test_plan_field_docs.py`` holds the guide's region byte-identical to that
    projection. What was missing was only its COUNT, and that is derived in
    :func:`test_the_STATED_COUNTS_are_DERIVED_from_the_code`.
    """
    hits = forward_looking_hits(corpus)
    # 18 since LD-657 — see the note at the equality in
    # test_the_PERMALINK_row_was_TRANSFORMED_by_the_cross_week_measurement_NOT_DROPPED.
    assert len(REGISTRY) == 18
    by_surface = {}
    for surface, _name, _matched, _start, _end in hits:
        by_surface[surface] = by_surface.get(surface, 0) + 1
    # Seven, since LD-623: the two unmeasured disclosures, the member-absence claim LD-618 gave
    # a sense to, and the four LD-618 enumerated as unreachable — `.raw()` on a `BaseRow`, the
    # `clear` op, and `draft.create` twice (prose, and the code comment of the same recipe).
    assert by_surface.get("guide()") == 7, by_surface
    live_absence_surfaces = {GENERATED_FRONT_DOOR, "writer_brief()"}
    assert set(by_surface) <= {"guide()"} | DATED_RECORD_SURFACES | live_absence_surfaces, (
        "a forward-looking phrase appeared on a surface that is neither the guide's two "
        "unmeasured disclosures, an append-only dated record, nor one of the two surfaces "
        f"carrying registered claims of absence: {by_surface}"
    )
    for surface in live_absence_surfaces:
        assert all(row.expect == "absent" for row in REGISTRY if row.surface == surface), (
            f"a claim on {surface} was registered as 'present' — that sense is earned only by a "
            "dated record or an unmeasured disclosure, and this surface is neither"
        )
    # THE FLOOR — that the census machinery still finds the claims at all. **LD-560 moved it
    # off the windowed surface**, which is the same correction LD-540 made to the counts above,
    # one release later: opening `[1.41.0]` rolled the last forward-looking dated-record hit
    # out of the wheel's recent-N projection, with nobody authoring anything. A floor that a
    # release can trip is not a property of a correct tree. So the dated-record half is
    # measured where those claims permanently live — the repository's COMPLETE release notes,
    # which is the append-only record the registry's rows actually cite — while the guide half
    # stays measured on the shipped surface, exactly asserted above.
    record_hits = forward_looking_hits(
        {"RELEASE_NOTES.md (the repository's complete copy)": _repository_release_notes()})
    assert len(by_surface) + len(record_hits) >= 3, (
        f"the census found almost nothing — the corpus or the phrase set broke: "
        f"{by_surface}, plus {len(record_hits)} on the complete record"
    )
    assert record_hits, (
        "the append-only dated record carries NO forward-looking claim — the phrase set or the "
        "record's shape broke; every promise the registry rows cite lives there"
    )
    # LD-618 INVERTED this arm rather than deleting it (supersession: the reason is preserved,
    # the conclusion moves). It used to read "the guide has grown a claim of absence — update the
    # note", which was the right complaint while the guide had none and the note said so. The
    # guide now HAS one, so the property worth holding is the one that made the old arm safe:
    # a claim of absence in the guide is never bare prose — it is a registered row whose
    # falsifier this guard actually resolves, which is what the last unguarded one was not.
    guide_absences = [row for row in REGISTRY
                      if row.surface == "guide()" and row.expect == "absent"]
    assert len(guide_absences) == 5, (
        "the guide's claims of absence moved — the census note above enumerates them, so update "
        f"the note with the same change: {[row.quote[:60] for row in guide_absences]}"
    )
    for row in guide_absences:
        for one in row.falsifiers:
            assert _FALSIFIER_GRAMMAR.match(one), row
            assert not falsifier_resolves(one), (
                f"the guide claims {row.quote[:60]!r} while {one} resolves")


# --------------------------------------------------------------------------- #
# 6. THE DELIBERATE-DEFECT PROOFS — a guard that only ever passes is not          #
#    evidence. Each probe drives the checkers with a synthetic corpus/registry,   #
#    so the bite is demonstrated rather than asserted.                            #
# --------------------------------------------------------------------------- #

_LIVE_CLAIM = "larkdocio does not ship an editable Markdown projection today"


def test_a_NEW_forward_looking_phrase_REDDENS_when_nobody_registered_it():
    """Property one, demonstrated. The census is the half that notices an ADDITION — a grep can
    see a phrase appear; only a registry can insist somebody accounted for it."""
    added = {"guide()": "The tree is the source of truth. A future release may add a projection."}
    defects = census_defects((), added)
    assert defects and "UNREGISTERED" in defects[0], defects
    assert not census_defects((), {"guide()": "The tree is the source of truth."}), (
        "the census fires on prose carrying no forward-looking phrase at all"
    )


def test_THE_FINDING_ONE_CATCH_a_registered_absence_whose_falsifier_NOW_EXISTS_REDDENS():
    """**The property the whole guard exists for**, reconstructed as the report described it.

    The guide said an editable Markdown projection *may* arrive in *a future release*. Then
    ``larkdocio.model.projection.project_block_ids`` became importable **in the same wheel** and
    the sentence became false — and nothing anywhere went red for eight releases, because no
    machine was holding a claim of absence against the code.

    Here the same registration is made against the same symbol, and the guard reddens on the
    spot. The control below is what makes this a proof rather than a coincidence: an identical
    row pointing at a symbol that does NOT exist stays green, so it is the falsifier's
    existence doing the work and not the phrasing.
    """
    landed = ForwardClaim(
        surface="guide()",
        quote=_LIVE_CLAIM,
        falsifier="symbol:larkdocio.model.projection.project_block_ids",
        expect="absent",
        why="the registration as it would have read while the claim was still true",
    )
    defects = falsifier_defects((landed,))
    assert defects, (
        "the guard did not notice that the thing the prose says does not ship is importable — "
        "this is the exact miss the routing report found, reproduced and NOT caught"
    )
    assert "THE CLAIM IS NOW FALSE" in defects[0], defects

    control = dataclasses.replace(
        landed, falsifier="symbol:larkdocio.model.projection.no_such_projection_verb")
    assert not falsifier_defects((control,)), (
        "the control reddened too, so the bite above proves nothing about the falsifier"
    )


def test_THE_LD571_CATCH_a_UNIVERSAL_ABSENCE_in_the_GENERATED_front_door_REDDENS():
    """**The second miss this guard exists for**, reconstructed the same way as the first.

    ``capabilities()``'s ``drive-files-write`` note said there was *no folder-creating call
    anywhere in this library* while ``create_folder`` was listed in the same payload — the
    library-wide half of a conclusion a product ruling had superseded, kept by the projection
    after the source module had already scoped it. Two things had to change for a machine to see
    it, and both are proven here rather than asserted: the phrase set had to grow a sense that is
    not futurity (**a claim about EVERYWHERE, not about later**), and the corpus had to reach a
    surface nobody authored as prose.

    The control is what makes it a proof: the **same sentence** with the falsifier scoped to the
    module the claim is true of stays green, so it is the scope word doing the work — which is
    exactly the correction the fix made.
    """
    shipped_as_it_read = ForwardClaim(
        surface=GENERATED_FRONT_DOOR,
        quote="no root-folder resolution and NO FOLDER-CREATING CALL anywhere in this library",
        falsifier="symbol:larkdocio.drive.folders_write.DriveFoldersWriteClient.create_folder",
        expect="absent",
        why="the generated note as it shipped, denying a call listed in the same payload",
    )
    assert forward_looking_hits({GENERATED_FRONT_DOOR: shipped_as_it_read.quote}), (
        "the phrase set cannot see a universal-absence claim at all — this is the miss that let "
        "the sentence ship, and the futurity-only set is what reproduced it"
    )
    defects = falsifier_defects((shipped_as_it_read,))
    assert defects and "THE CLAIM IS NOW FALSE" in defects[0], defects

    scoped = dataclasses.replace(
        shipped_as_it_read,
        falsifier="symbol:larkdocio.drive.files_write.DriveFilesWriteClient.create_folder")
    assert not falsifier_defects((scoped,)), (
        "the module-scoped claim reddened too, so the bite above proves nothing about the scope "
        "of the claim — which is the only thing the supersession changed"
    )


def _shipped_delete_request():
    """The shipped ``DeleteRequest`` class, imported at module scope for the LD-618 proof below."""
    from larkdocio.write.model.requests import DeleteRequest

    return DeleteRequest


@dataclasses.dataclass(frozen=True)
class _DeleteRequestWithTheFlagLanded(_shipped_delete_request()):
    """``DeleteRequest`` **as it would read if ``allow_missing`` had been added** — the subject of
    the LD-618 bite proof, and nothing else in this file or the wheel.

    It is a real subclass of the shipped frozen dataclass carrying one extra field, so the
    falsifier the proof registers against it resolves through the ordinary
    ``param:<dotted>#<name>`` path — ``inspect.signature`` on a class the ``@dataclass``
    decorator built, which is exactly what it would be reading if the field were typed into
    ``src/larkdocio/write/model/requests.py``. Declaring it here rather than mutating the shipped
    class is what keeps the proof from being able to change its own subject.
    """

    allow_missing: bool = False


def test_THE_D108_CATCH_a_MEMBER_ABSENCE_claim_whose_PARAMETER_LANDS_REDDENS():
    """**The third miss this guard exists for** (LD-618), reconstructed the same way as the two
    above — and the first one caught before it cost anything rather than after.

    The guide tells a consumer, in the idempotent-delete recipe, that *"There is no
    ``allow_missing`` on ``DeleteRequest``"*. A product ruling upheld that sentence on 2026-09-02
    and, in the same reading, found that **nothing enforced it**: no test grepped it, and the
    phrase set had no sense that could see it — the sentence promises nothing about later and
    scopes nothing to a module, so futurity and universal-absence both walked past it. A future
    change could have added the field and the shipped sentence would simply have become false.

    Here the claim is registered as it reads, and the parameter is made to exist the way it would
    if somebody landed it — the guard reddens on the spot. **The control is what makes this a
    proof:** the same row against a field nobody added stays green, so it is the parameter's
    existence doing the work and not the sentence's wording. The out-of-process half — that the
    SUITE fails, by exit code, on a tree where the field really landed in the source file — is
    :func:`test_the_GUARD_ITSELF_FAILS_by_EXIT_CODE_on_a_tree_where_the_flag_really_landed`.
    """
    from larkdocio.write.model import requests as request_module

    row = [claim for claim in REGISTRY
           if claim.falsifier.endswith("DeleteRequest#allow_missing")
           and claim.surface == "guide()"]
    assert len(row) == 1, "the shipped allow_missing claim is not registered exactly once"
    row = row[0]
    assert not falsifier_defects((row,)), (
        "the row is already red on the real tree — either the flag landed (in which case the "
        "guide's sentence is now FALSE and must be re-cut) or the falsifier is misspelled"
    )

    # The parameter is made real on the throwaway SUBCLASS declared at module scope below: the
    # same decorator that would generate the ``__init__`` if the field were typed into
    # ``requests.py`` generates it there, so ``inspect.signature`` answers exactly as it would
    # then, and the falsifier is resolved by IMPORT AND INTROSPECTION — the same code path, no
    # special case. The shipped class is not touched, and the last assertion says so.
    landed = dataclasses.replace(
        row,
        falsifier=f"param:{__name__}._DeleteRequestWithTheFlagLanded#allow_missing")
    assert "allow_missing" in inspect.signature(_DeleteRequestWithTheFlagLanded).parameters
    defects = falsifier_defects((landed,))
    assert defects and "THE CLAIM IS NOW FALSE" in defects[0], defects

    control = dataclasses.replace(landed, falsifier=landed.falsifier.replace(
        "#allow_missing", "#a_flag_nobody_added"))
    assert not falsifier_defects((control,)), (
        "the control reddened too, so the bite above proves nothing about the parameter"
    )
    assert "allow_missing" not in inspect.signature(request_module.DeleteRequest).parameters, (
        "this test mutated the shipped class — the proof must not be able to change the subject"
    )


def test_the_MEMBER_ABSENCE_pattern_is_a_SHAPE_and_not_a_GREP_OF_ONE_SENTENCE():
    """The calibration probe for the newest sense, and the thing AC-shaped review asks first:
    *does the pattern catch the CLASS, or only today's words?*

    A pattern that matched ``allow_missing``/``DeleteRequest`` literally would prove nothing about
    the next sentence of the same shape — and the whole reason this file exists is that the last
    unguarded claim was unguarded by accident, not by spelling. So: a **different** member on a
    **different** owner is caught, the bolded and the plain spellings are both caught, and the
    'still' variant the packaged notes actually use is caught.

    The negative half is the half that decides whether this pattern survives, and every sentence
    below is REAL text from the shipped guide, not an invented straw man. Each is a claim about
    **Lark's API**, about **Markdown**, or about a **prose-named** owner — none has an importable
    falsifier, so a pattern that flagged them would demand registrations nobody can write and be
    disabled instead of narrowed.
    """
    caught = (
        "There is no `allow_missing` on `DeleteRequest`",
        "**There is no `allow_missing` on `DeleteRequest`**",
        "There is still no `allow_missing` on `DeleteRequest`, and none is promised.",
        "there is no `partial` on `InsertRequest`",
        "There is no `.raw()` on a `BaseRow`",
        # LD-623 — the ELIDED conjunct: English does not repeat the verb, and that is the only
        # reason the shipped `.raw()` claim was invisible. A DIFFERENT member on a DIFFERENT
        # owner, so this is the shape and not the sentence.
        "the snapshot has both, and no `rows` on a `BaseTableSnapshot`",
    )
    for sentence in caught:
        hits = forward_looking_hits({"guide()": sentence})
        assert hits, f"the member-absence sense cannot see: {sentence}"
        assert {name for _s, name, *_rest in hits} == {"member-absence"}, hits

    # ---- LD-623: the two senses that carry the claims member-absence deliberately refuses --- #
    # Each was listed under `honest` above while member-absence was the only sense, with its own
    # correct reason. **The reasons are preserved and only the conclusions move** (supersession):
    # an op still has no owner to backtick and a dotted expression still has no ` on ` clause —
    # they are caught by senses of their own, each with its own falsifier kind, not by loosening
    # this one. The final assertion of each loop is what says so.
    for sentence, sense in (
        ("**There is no `clear` op** — `capabilities()` lists six sheets-write operations.",
         "op-absence"),
        ("There is no `rotate` operation on the Sheets write engine.", "op-absence"),
        ("**CREATING A ROW IS `draft.add(...)`. THERE IS NO `draft.create`.**",
         "dotted-member-absence"),
        # the wrapped code-comment spelling, flattened as the census reads it
        ("# THE FOUR VERBS ARE `add`, `set`, `update` and `delete`. There is no "
         "# `draft.create` — a reasonable guess.", "dotted-member-absence"),
    ):
        hits = forward_looking_hits({"guide()": sentence})
        assert {name for _s, name, *_rest in hits} == {sense}, (
            f"expected only the {sense} sense on: {sentence} — got {hits}")

    honest = (
        # LD-623: still NOT reached, and this is the boundary that has to hold — a claim about
        # a wire KEY, whose owner is a shape rather than a type. The shipped example that
        # decided it is about LARK's own response and has no importable falsifier at all.
        "the same listing without a `view_id` carries no `is_hidden` key at all",
        "on one shape there is no `after` key at all, on another `before` is not text",
        # a bare dotted name with no absence verb in front of it
        "Use `draft.add(...)` instead of `draft.create`.",
        # a leading-dot accessor is member-absence's business, not the dotted sense's, and
        # member-absence declines it for want of a backticked owner
        "There is no `.records` on the read model.",
        # about LARK's API — no importable falsifier exists, by construction
        "There is no `If-Match` on the Base API, so the staleness guard is CLIENT-SIDE.",
        "There is no `parent_id` on a record — six plausible body keys were each tried.",
        # about MARKDOWN the language
        "There is no `colspan`/`rowspan` in Markdown, so an authored table is a plain grid.",
        # about the reader's own environment
        "the same packaged-resource accessor, so it works from a vendored wheel, where there is "
        "no `src/` tree to open",
        # A PROSE-NAMED OWNER: the wider class this sense deliberately does not reach.
        # **TRANSFORMED by LD-623, not dropped** (supersession: the reason is preserved, the
        # conclusion moves). This used to be the whole shipped sentence — "There is no
        # `.records` on the read model and no `.raw()` on a `BaseRow`;" — which was the right
        # entry while the sense could not read the elided conjunct, because catching it then
        # would have meant catching it on the PROSE-owner half. It now IS caught, on the
        # second half's backticked owner, and appears in `caught` above; what stays honest is
        # the prose-owner half ON ITS OWN, which is the class this sense still refuses.
        "There is no `.records` on the read model, and that is the AttributeError.",
        # an op, not a member of a named owner — **TRANSFORMED by LD-623**: the reason is
        # unchanged and the sentence is now claimed by `op-absence`, a sense of its own with a
        # falsifier kind of its own, asserted in the sense-attribution loop above. What stays
        # honest here is the same shape with NO op word to anchor on.
        "**There is no `clear`** in the sheets vocabulary at all.",
    )
    for sentence in honest:
        assert not forward_looking_hits({"guide()": sentence}), (
            f"the member-absence sense bites honest prose, which is how a guard gets deleted "
            f"rather than narrowed: {sentence}"
        )


#: The shipped field site of ``DeleteRequest``, quoted so the flagged scratch tree below is built
#: by an EDIT THAT MUST STILL APPLY. If the class is reshaped this string stops matching, and the
#: proof reddens loudly instead of quietly substituting nothing.
_DELETE_REQUEST_FIELD_DECLARATION = "    target: NarrativeAnchor\n"
_DELETE_REQUEST_FIELD_SITE = (
    _DELETE_REQUEST_FIELD_DECLARATION
    + "\n    def to_dict(self) -> dict:\n"
    + '        return {"op": "delete", "target": self.target.to_dict()}'
)
_THE_FLAG_AS_IT_WOULD_LAND = (
    _DELETE_REQUEST_FIELD_DECLARATION + "    allow_missing: bool = False\n"
)


def _scratch_tree(root, edits):
    """Build a scratch ``src/`` tree at ``root`` with ``edits`` applied to the files on disk.

    ``edits`` is ``((path relative to src/, CONTEXT, old, new), …)``. **CONTEXT and ``old`` must
    each occur exactly once** — the tripwire that keeps the proof honest: if the site is reshaped
    the edit stops applying and this raises loudly, rather than quietly substituting nothing and
    reporting a green control as evidence. The uniqueness of ``old`` is not decoration: the
    delete-serializer landing below first patched the ``d["before"] = entry.before`` line of a
    DIFFERENT serializer three functions earlier, the arms stayed green, and the proof read as
    "the guard does not bite" when what had happened was "the edit landed somewhere else".

    Hardlinked, so the 11 MB of packaged documents cost nothing and the guide the census reads is
    byte-identical to the shipped one; each file that changes has its link broken *before* the
    write, so nothing can be written through into the real tree. Returns the scratch ``src``
    directory, or ``None`` when the source layout is not there to copy (never a silent pass — the
    caller skips with a reason).

    Generalised from LD-618's single-edit version by LD-623, which pins four more claims and so
    needs four more landings; the DeleteRequest one is expressed as one of them and is unchanged.
    """
    import os
    import shutil

    src = REPO_ROOT / "src"
    notes = REPO_ROOT / "RELEASE_NOTES.md"
    if not (src.is_dir() and notes.is_file()):
        return None
    originals = {}
    for relative, context, old, _new in edits:
        site = src / relative
        if not site.is_file():
            return None
        text = site.read_text("utf-8")
        if text.count(context) != 1 or text.count(old) != 1:
            raise AssertionError(
                f"the edit site in {relative} has been reshaped, so this proof no longer edits "
                f"anything — re-cut its CONTEXT against the code as it now reads. (If the thing "
                f"the claim DENIES is what landed, the registry rows and the shipped sentences "
                f"are what to fix, not this string.)")
        originals[relative] = text

    def link_or_copy(source, destination):
        try:
            os.link(source, destination)
        except OSError:  # a different filesystem — correctness over speed
            shutil.copy2(source, destination)

    scratch_src = root / "src"
    shutil.copytree(src, scratch_src, copy_function=link_or_copy)
    # The append-only record the registry's dated rows cite is read from the tree ROOT, so the
    # scratch tree needs it too — otherwise the census fails for a reason that is not the flag.
    link_or_copy(notes, root / "RELEASE_NOTES.md")
    for relative, _context, old, new in edits:
        scratch_site = scratch_src / relative
        text = scratch_site.read_text("utf-8")
        scratch_site.unlink()  # break the link BEFORE writing — never write through into src/
        scratch_site.write_text(text.replace(old, new, 1), "utf-8")
    return scratch_src


#: LD-618's landing, as one entry of the general form above.
_DELETE_REQUEST_LANDING = ("larkdocio/write/model/requests.py", _DELETE_REQUEST_FIELD_SITE,
                           _DELETE_REQUEST_FIELD_DECLARATION, _THE_FLAG_AS_IT_WOULD_LAND)


def _flagged_source_tree(root):
    """The LD-618 tree: ``allow_missing`` REALLY IS a field on ``DeleteRequest``, carried by the
    file on disk, the way a change landing the flag would."""
    return _scratch_tree(root, (_DELETE_REQUEST_LANDING,))


#: The guard arms a landing can be proved against, by node id. Named rather than spelled at each
#: call site so a rename of an arm cannot leave a proof selecting nothing (pytest exits non-zero
#: on an unknown node id, which would read as a bite).
_ARMS = {
    "falsifier": (f"{pathlib.Path(__file__).name}"
                  "::test_no_registered_claim_has_been_OVERTAKEN_BY_THE_CODE"),
    "counts": (f"{pathlib.Path(__file__).name}"
               "::test_the_STATED_COUNTS_are_DERIVED_from_the_code"),
    "generated-region": ("test_plan_field_docs.py"
                         "::test_the_region_is_BYTE_IDENTICAL_to_the_projection"),
}


def _run_arms(scratch_src, arms):
    """Run the named guard arms against ``scratch_src`` in a subprocess; return the process.

    ``PYTHONPATH`` precedes the editable install's own ``.pth`` entry, so the scratch tree is the
    ``larkdocio`` that gets imported. Only the arms that owe the bite are selected, by node id —
    which also makes recursion impossible: these proofs are never among the tests that run
    inside.
    """
    import os
    import subprocess

    environment = dict(os.environ, PYTHONPATH=str(scratch_src))
    environment.pop("LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY", None)  # nothing live here, ever
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts=",
         *[_ARMS[arm] for arm in arms]],
        capture_output=True, text=True, cwd=str(REPO_ROOT / "tests"), env=environment)


def _run_the_falsifier_arm(scratch_src):
    """LD-618's single-arm runner, kept as the name its own proof reads."""
    return _run_arms(scratch_src, ("falsifier",))


def test_the_GUARD_ITSELF_FAILS_by_EXIT_CODE_on_a_tree_where_the_flag_really_landed(tmp_path):
    """**The out-of-process half of the LD-618 proof, and the half that answers the real question:
    would the suite have gone red?**

    Every probe above drives the checkers in-process, which proves the CHECKER bites. It does not
    prove the GUARD fails, and this repository has been bitten by that difference twice already —
    a guard whose subject was its own answer, and a claim whose falsifier did not exist. So the
    local convention for an instrument is followed here (``scripts/decisions_index.py``,
    ``scripts/progress_index.py``: *"asserting the drift in-process would only re-prove ``!=``;
    what ``--check`` owes its caller is the EXIT CODE, and only running it says that"*): a scratch
    source tree is built in which ``allow_missing`` **really is** a field on ``DeleteRequest`` in
    the file on disk, and **pytest is run against it**.

    The control run — the same scratch tree with the file restored — is what makes this a proof
    rather than a demonstration that shadowing a source tree breaks something: it must exit 0.
    """
    scratch_src = _flagged_source_tree(tmp_path / "flagged")
    if scratch_src is None:
        pytest.skip("no src/ checkout to copy — this proof needs the repository layout")

    red = _run_the_falsifier_arm(scratch_src)
    assert red.returncode != 0, (
        "THE GUARD PASSED on a tree where allow_missing is a real field on DeleteRequest. The "
        "shipped sentence is false on that tree and nothing said so — which is the exact state "
        f"this issue found.\n{red.stdout}\n{red.stderr}")
    assert "THE CLAIM IS NOW FALSE" in red.stdout, (red.stdout, red.stderr)
    assert "DeleteRequest#allow_missing" in red.stdout, (red.stdout, red.stderr)

    control_src = _flagged_source_tree(tmp_path / "control")
    control_site = control_src / "larkdocio" / "write" / "model" / "requests.py"
    control_site.unlink()
    control_site.write_text(
        (REPO_ROOT / "src" / "larkdocio" / "write" / "model" / "requests.py").read_text("utf-8"),
        "utf-8")
    green = _run_the_falsifier_arm(control_src)
    assert green.returncode == 0, (
        "the CONTROL failed too, so the red above is about the scratch tree rather than about "
        f"the flag.\n{green.stdout}\n{green.stderr}")

    # And the real tree is untouched — a proof that can edit its own subject proves nothing.
    assert "allow_missing" not in (
        REPO_ROOT / "src" / "larkdocio" / "write" / "model" / "requests.py").read_text("utf-8")


def test_the_MIRROR_bite_a_present_row_whose_falsifier_VANISHED_reddens():
    """The other direction, which keeps the registry from rotting the opposite way: prose that
    cites something the wheel no longer carries is just as stale as prose that denies something
    it does."""
    orphaned = ForwardClaim(
        surface="release_notes() (the packaged RELEASE_NOTES.md)",
        quote="a future release may add the vanished verb",
        falsifier="symbol:larkdocio.write.a_verb_that_was_deleted",
        expect="present",
        why="a record citing a symbol somebody has since removed from the wheel",
    )
    defects = falsifier_defects((orphaned,))
    assert defects and "THE GROUND IS GONE" in defects[0], defects


@pytest.mark.parametrize("falsifier", ["", "   ", None])
def test_a_row_with_NO_FALSIFIER_IS_REFUSED(falsifier, corpus):
    """Property two. *"We say X does not ship"* with no *"and here is what would make that
    false"* is a comment, and a comment is what rotted the last one."""
    naked = ForwardClaim(surface="guide()", quote=_LIVE_CLAIM, falsifier=falsifier,
                         expect="absent", why="a registration that explains nothing at all")
    defects = registry_defects((naked,), {"guide()": _LIVE_CLAIM})
    assert any("NO FALSIFIER" in defect for defect in defects), defects


def test_a_MALFORMED_falsifier_is_REFUSED_rather_than_silently_ignored():
    """A falsifier this guard cannot resolve is worse than none: it looks like coverage."""
    bad = ForwardClaim(surface="guide()", quote=_LIVE_CLAIM,
                       falsifier="see the projection module", expect="absent",
                       why="prose where a resolvable pointer belongs, which reads as coverage")
    defects = registry_defects((bad,), {"guide()": _LIVE_CLAIM})
    assert any("is not symbol:" in defect for defect in defects), defects


def test_expect_PRESENT_is_REFUSED_on_a_LIVE_document_the_anti_suppression_rule():
    """The back door, nailed shut. If ``expect='present'`` were available anywhere, every
    overtaken promise could be re-filed as green with one word — so it is earned only by an
    append-only dated record or by the doctrine's own unmeasured vocabulary, and the guide is
    neither."""
    smuggled = ForwardClaim(
        surface="guide()",
        quote=_LIVE_CLAIM,
        falsifier="symbol:larkdocio.model.projection.project_block_ids",
        expect="present",
        why="an overtaken promise re-filed as a record to make the suite green again",
    )
    defects = registry_defects((smuggled,), {"guide()": _LIVE_CLAIM})
    assert any("LIVE document" in defect for defect in defects), defects


def test_expect_PRESENT_is_ALLOWED_for_an_UNMEASURED_disclosure_the_must_not_bite():
    """The other side of that rule, and the one that decides whether this guard survives a
    month: ``negative-claims.md`` § A.1 *prescribes* "unmeasured" language, so a guard that
    reddened on it would punish the behaviour it exists to encourage."""
    # The shipped permalink disclosure as it reads AFTER the 2026-08-15 cross-week measurement:
    # the week itself is now measured, and what is still unknown is scoped in § A.1's vocabulary.
    honest = ("durability beyond that week, on another tenant, or for a record somebody deletes "
              "is not yet measured, so this still makes no claim of permanence")
    row = ForwardClaim(surface="guide()", quote=honest,
                       falsifier="symbol:larkdocio.base.record_permalink", expect="present",
                       why="the honest disclosure shape the negative-claim doctrine asks for")
    assert not registry_defects((row,), {"guide()": honest})


def test_a_row_whose_QUOTE_NO_LONGER_OCCURS_is_REFUSED_so_the_registry_cannot_silt_up():
    """The registry is a list of LIVE promises. A row whose sentence was reworded or deleted is
    a suppression nobody will ever re-read, so it reddens and gets re-cut or dropped."""
    stale = ForwardClaim(surface="guide()", quote="a sentence nobody ships any more",
                         falsifier="symbol:larkdocio.guide", expect="present",
                         why="a row left behind after the prose it covered was rewritten")
    defects = registry_defects((stale,), {"guide()": "the guide as it reads today"})
    assert any("stale" in defect for defect in defects), defects


def test_a_row_that_CLAIMS_NOTHING_is_REFUSED():
    """The same rot from the other end: a row covering prose that carries no forward-looking
    phrase at all is dead weight, and dead weight is how a registry becomes a .gitignore."""
    idle = ForwardClaim(surface="guide()", quote="the tree is the source of truth",
                        falsifier="symbol:larkdocio.guide", expect="present",
                        why="a row covering a sentence that promises nothing whatsoever")
    corpus = {"guide()": "the tree is the source of truth"}
    defects = census_defects((idle,), corpus)
    assert any("DEAD ROW" in defect for defect in defects), defects


def test_all_FALSIFIER_KINDS_really_resolve():
    """Each kind is checked against something real in BOTH directions, so a kind cannot quietly
    become a no-op that answers the same way whatever it is handed."""
    # operation: — the fourth kind (LD-623). Both directions on the SAME surface, so a pass
    # cannot come from the surface lookup silently failing open.
    assert falsifier_resolves("operation:sheets-write#merge")
    assert not falsifier_resolves("operation:sheets-write#clear")
    with pytest.raises(ValueError):
        # and a surface capabilities() does not publish REFUSES rather than answering "absent",
        # which is the failure mode that would make every operation: row read as coverage
        falsifier_resolves("operation:no-such-surface#clear")
    assert falsifier_resolves("symbol:larkdocio.model.projection.project_block_ids")
    assert not falsifier_resolves("symbol:larkdocio.model.projection.nope")
    assert falsifier_resolves("param:larkdocio.base.schema_plan.create_table#default_view_name")
    assert not falsifier_resolves("param:larkdocio.base.schema_plan.create_table#no_such_param")
    assert falsifier_resolves("capability:surfaces.docx-read.mode")
    assert not falsifier_resolves("capability:surfaces.docx-read.no_such_key")
    assert not falsifier_resolves("symbol:larkdocio.no_such_module.at_all")
    with pytest.raises(ValueError):
        falsifier_resolves("just some prose")


def test_the_phrase_set_does_NOT_bite_this_project_s_own_PLANNER_VOCABULARY():
    """The calibration probe, and the reason ``a-fix-is-planned`` is scoped rather than bare.
    "is planned" is a domain verb all over the shipped recipes; a census that flagged it would
    redden on honest prose every week and be deleted within a month."""
    planner_prose = {
        "guide()": (
            "Content you write inside a marker's segment is planned as an insert anchored to "
            "that surviving marker, and each batch is built against ids that exist when it is "
            "planned."
        ),
    }
    assert not forward_looking_hits(planner_prose), forward_looking_hits(planner_prose)
    promise = {"guide()": "This is a known limitation of the rebuild and a fix is planned."}
    assert forward_looking_hits(promise), "the promise idiom itself must still be caught"


def test_the_census_reads_THROUGH_a_line_wrap():
    """The miss that hid a claim from a bug report once already: a phrase split across a wrap is
    one phrase to a reader and two strings to a naive grep."""
    wrapped = {"guide()": "the projection is not\n  yet shipped by this library"}
    assert forward_looking_hits(wrapped), "flatten() is not doing its job"


def test_the_DATED_RECORD_surfaces_are_real_members_of_the_corpus(corpus):
    """A label typo in :data:`DATED_RECORD_SURFACES` would silently widen the 'present'
    allowance to nothing — or, worse, fail to widen it where it was meant to."""
    assert DATED_RECORD_SURFACES <= set(corpus), sorted(DATED_RECORD_SURFACES - set(corpus))


def test_the_PERMALINK_row_was_TRANSFORMED_by_the_cross_week_measurement_NOT_DROPPED():
    """``process/doctrine/supersession.md`` § A.1, executed rather than promised.

    The 2026-08-15 cross-week re-probe answered the question this row said was owed, so the
    shipped sentence changed — and the temptation at exactly that moment is to delete the row
    along with the sentence it quoted, which would take the coverage with it. The row moved
    onto the new text instead: **same surface, same falsifier, same sense, and the registry is
    no smaller than it was.**
    """
    # 17 -> 18 at LD-657, which is a ROW ADDED and not a supersession: the release note that
    # tells a consumer the frozen `Unknown block type` warning stays frozen is a forward-looking
    # claim a reader must plan around, so it is registered rather than deleted. The equality is
    # kept (never relaxed to >=) precisely so an addition and a deletion cannot cancel out.
    assert len(REGISTRY) == 18, "the registry lost (or gained) a row in a supersession"
    rows = [row for row in REGISTRY
            if row.falsifier == "symbol:larkdocio.base.record_permalink"]
    assert len(rows) == 1, "the permalink row was dropped rather than transformed"
    row = rows[0]
    assert row.surface == "guide()" and row.expect == "present"
    assert "has not yet been measured" not in row.quote, (
        "the row still quotes the superseded sentence")
    assert "2026-08-15" in row.why, "the transformed row does not say what superseded it"


def test_every_phrase_in_the_set_carries_its_REASON():
    """D-25 in miniature: a pattern whose reason lives only in a commit message is a pattern the
    next worker deletes as noise."""
    for name, pattern, reason in FORWARD_LOOKING_PHRASES:
        assert pattern.pattern, name
        assert len(reason) > 40, f"{name}: the reason is too thin to act on"


# --------------------------------------------------------------------------- #
# 7. THE COUNTS INSIDE A CLAIM — derived, never restated (LD-623).             #
#                                                                             #
#    A claim of absence can rot in TWO directions and the registry above only  #
#    watches one of them. *"There is no `clear` op — `capabilities()` lists    #
#    nine sheets-write operations"* is two claims in one sentence: the op,     #
#    held by an `operation:` row, and the NUMBER, which goes false the day     #
#    somebody registers a tenth descriptor with no `clear` in sight. It        #
#    ALREADY went false once — the sentence shipped "six" (found by LD-623,    #
#    reworded by LD-626) — which is why the number is READ off the prose here  #
#    and never re-typed.                                                      #
#    `process/doctrine/staleness.md`: derived, dated, or not stated. So the    #
#    numbers are derived off the code and held against the shipped prose —     #
#    the prose's own number is READ, never re-typed here, because a number     #
#    typed twice is a number that can agree with itself while both are wrong.  #
# --------------------------------------------------------------------------- #

#: The number words a shipped sentence may spell a small count with. Deliberately not a
#: general parser: a claim whose count is large enough to need one has no business being
#: hand-written in prose at all.
NUMBER_WORDS = {"zero": 0, "no": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
                "twelve": 12}


def derived_sheets_write_operation_count():
    """How many **operations** ``capabilities()`` lists for the sheets write surface.

    Entries of kind ``operation`` only — the projection labels each entry, and the same list
    also carries ``leg`` (``dry_run``, the image puts) and ``lifecycle``
    (``create_spreadsheet`` / ``delete_spreadsheet``) entries. The sentence this derivation
    answers to is about the write **operations** a caller would scan for a ``clear``, and it is
    the denominator the guide itself settled on before that sentence existed: its sheets-write
    section reconciles *"Ten families, nine operations"* against this same projection, a count
    already derived by ``tests/test_guide_sheets_completion.py``. LD-626 landed the reword that
    makes the two agree — the guide shipped "six" until then (see :data:`STATED_COUNTS`) — and
    the wider fifteen-entry reading (the four ``leg`` entries plus the ``lifecycle`` pair) would
    have contradicted the already-guarded sentence.
    """
    node = _walk_capabilities("surfaces.sheets-write.operations")
    if node is _MISSING or not isinstance(node, list):
        raise AssertionError(
            "capabilities() no longer publishes surfaces.sheets-write.operations — the "
            "derivation this count is held against is gone, which is a bigger defect than a "
            "stale number")
    return len([entry for entry in node if entry.get("kind") == "operation"])


def derived_shapes_with_no_after_key():
    """How many plan-entry shapes carry **no** ``after`` key — read off the serializers.

    ``larkdocio.write.plan_field_docs`` derives ``has_after`` from each serializer's own AST,
    which is why the *claim* needs no registry row: the generator **refuses to generate** when
    a shape's authored prose and its derived ``has_after`` disagree, and the guide's region is
    held byte-identical to that projection. The **count** in the region's intro sentence is the
    one thing neither of those reaches — it is authored, and it says "one".
    """
    from larkdocio.write.plan_field_docs import before_after_shapes

    return sum(1 for shape in before_after_shapes() if not shape.has_after)


@dataclasses.dataclass(frozen=True)
class StatedCount:
    """One number a shipped sentence states, beside the code that derives it.

    :param pattern: matched against the FLATTENED surface; **exactly one group**, holding the
        number as the prose spells it. Required to occur exactly once, so a reworded sentence
        leaves a loud stale row rather than a silent pass.
    :param derive: zero-argument callable returning the number the code actually says.
    :param stale: ``(stated, derived, "YYYY-MM-DD", note)`` — **the one disposition for a
        count that is ALREADY WRONG.** A guard cannot be landed red, and a false number in a
        shipped document cannot be blessed either, so a known mismatch is quarantined as a
        *measured, dated pair*: this exact stated number against this exact derived one. Any
        further movement on either side reddens, and so does the mismatch being **fixed** —
        a quarantine that outlived its defect is silt and is refused.
    """

    name: str
    surface: str
    pattern: "re.Pattern"
    derive: object
    why: str
    stale: tuple = ()


STATED_COUNTS = (
    StatedCount(
        name="sheets-write-operations",
        surface="guide()",
        pattern=re.compile(r"`capabilities\(\)` lists (\w+) sheets-write operations",
                           re.IGNORECASE),
        derive=derived_sheets_write_operation_count,
        why="The second claim in the `clear`-op sentence, and the one the `operation:` row "
            "beside it cannot hold: a tenth descriptor in `larkdocio.sheets.ops.OPS` makes "
            "'nine' false with no `clear` anywhere in sight, which is exactly the rot "
            "staleness.md § 'derived, dated, or not stated' is about. LD-626 landed the "
            "reword LD-623's AC7 fenced (six → nine) and dropped the `stale=` quarantine "
            "with it, so this row now holds the number by DERIVATION alone — the prose is "
            "right, not excused. `nine` is the guide's OWN settled denominator: the "
            "sheets-write section says '**Ten families, nine operations — the same surface "
            "counted two ways**', a count already derived by "
            "tests/test_guide_sheets_completion.py, so the entries-of-kind-`operation` reading "
            "is the one the document means and the wider fifteen-entry reading would have "
            "contradicted that already-guarded sentence earlier in the same section.",
    ),
    StatedCount(
        name="plan-shapes-with-no-after-key",
        surface="guide()",
        pattern=re.compile(r"on (\w+) shape there is no `after` key at all", re.IGNORECASE),
        derive=derived_shapes_with_no_after_key,
        why="The fourth claim LD-618 enumerated, and the half of it that was genuinely "
            "unguarded. That the DELETE shape carries no `after` key is held by a stronger "
            "mechanism than any registry row — `plan_field_docs` refuses to generate when a "
            "shape's prose disagrees with its derived `has_after`, and the guide's region is "
            "byte-identical to that projection. But the intro sentence says the absence holds "
            "on exactly ONE shape, and that number is authored: a second pair-less op would "
            "leave it shipping 'one shape' while two shapes had none.",
    ),
)


def stated_count_defects(rows, corpus):
    """``[str]`` — every stated count that disagrees with its derivation, plus every quarantine
    that no longer describes reality (in either direction)."""
    defects = []
    for row in rows:
        flat = flatten(corpus.get(row.surface, ""))
        found = row.pattern.findall(flat)
        if len(found) != 1:
            defects.append(
                f"{row.name}: the sentence carrying this count occurs {len(found)} times on "
                f"{row.surface} — it was reworded or deleted, so this row is stale. Re-cut the "
                f"pattern against the sentence as it now reads, or drop the row.")
            continue
        word = found[0].lower()
        if word not in NUMBER_WORDS and not word.isdigit():
            defects.append(f"{row.name}: cannot read {found[0]!r} as a number")
            continue
        stated = int(word) if word.isdigit() else NUMBER_WORDS[word]
        derived = row.derive()
        if row.stale:
            known_stated, known_derived, measured, _note = row.stale
            if stated == derived:
                defects.append(
                    f"{row.name}: THE QUARANTINE OUTLIVED ITS DEFECT — the prose and the "
                    f"derivation now agree at {derived}, so the `stale=` tuple (measured "
                    f"{measured}) is silt. Drop it; the row keeps working without it.")
            elif (stated, derived) != (known_stated, known_derived):
                defects.append(
                    f"{row.name}: THE STALE COUNT MOVED — quarantined on {measured} as "
                    f"stated={known_stated} vs derived={known_derived}, and it now reads "
                    f"stated={stated} vs derived={derived}. Fix the shipped sentence (the "
                    f"reword the quarantine was waiting for) and drop the tuple, or re-measure "
                    f"it with a fresh date and say what moved.")
            continue
        if stated != derived:
            defects.append(
                f"{row.name}: THE COUNT IS NOW FALSE — {row.surface} states {stated} and the "
                f"code derives {derived}. The sentence is wrong today: fix the prose in the "
                f"same change that moved the number. ({row.why})")
    return defects


def test_the_STATED_COUNTS_are_DERIVED_from_the_code(corpus):
    """AC3. A count inside a claim of absence is a claim of its own, and it rots on its own."""
    defects = stated_count_defects(STATED_COUNTS, corpus)
    assert not defects, "\n  " + "\n  ".join(defects)


def test_every_STATED_COUNT_row_reads_ONE_sentence_and_carries_its_REASON(corpus):
    """Structural, so a row cannot become decorative: one occurrence, one group, a real
    derivation, and a reason a reviewer can act on."""
    for row in STATED_COUNTS:
        assert row.pattern.groups == 1, row.name
        assert len(row.why) > 40, row.name
        assert callable(row.derive), row.name
        assert isinstance(row.derive(), int), row.name
        assert len(row.pattern.findall(flatten(corpus[row.surface]))) == 1, row.name
        if row.stale:
            assert len(row.stale) == 4 and row.stale[3], (
                f"{row.name}: a quarantined count with no note is a suppression")
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", row.stale[2]), row.name


def test_a_COUNT_that_DRIFTS_reddens_even_when_the_ABSENCE_CLAIM_stays_true():
    """The bite, in process and on a synthetic pair — the whole reason this section exists.

    The registry row beside this sentence watches for a ``clear`` op appearing. It cannot see a
    SEVENTH operation of any other name, and that is the rot that actually happened here.
    """
    row = StatedCount(name="probe", surface="guide()",
                      pattern=re.compile(r"lists (\w+) operations"),
                      derive=lambda: 6, why="a count stated in prose beside a claim of absence")
    agreeing = {"guide()": "There is no `clear` op — it lists six operations."}
    assert not stated_count_defects((row,), agreeing)

    seventh = dataclasses.replace(row, derive=lambda: 7)
    defects = stated_count_defects((seventh,), agreeing)
    assert defects and "THE COUNT IS NOW FALSE" in defects[0], defects
    # …and the absence claim in that same sentence is still TRUE on that tree, which is the
    # point: the registry arm would have stayed green through it.
    assert not falsifier_defects(
        [claim for claim in REGISTRY if claim.falsifier == "operation:sheets-write#clear"])


def test_a_QUARANTINED_count_cannot_SILT_it_reddens_when_FIXED_and_when_it_MOVES():
    """The anti-suppression arm. ``stale=`` is the one disposition for a number that is already
    wrong, and it is a *measured dated pair*, not a mute button: fix the prose and it reddens,
    let the derivation drift further and it reddens."""
    quarantined = StatedCount(
        name="probe", surface="guide()", pattern=re.compile(r"lists (\w+) operations"),
        derive=lambda: 9, why="a count already wrong when it was first derived",
        stale=(6, 9, "2026-09-03", "measured and filed as its own issue"))
    stale_prose = {"guide()": "There is no `clear` op — it lists six operations."}
    assert not stated_count_defects((quarantined,), stale_prose), "the quarantine must hold"

    fixed = {"guide()": "There is no `clear` op — it lists nine operations."}
    defects = stated_count_defects((quarantined,), fixed)
    assert defects and "OUTLIVED ITS DEFECT" in defects[0], defects

    moved = dataclasses.replace(quarantined, derive=lambda: 10)
    defects = stated_count_defects((moved,), stale_prose)
    assert defects and "THE STALE COUNT MOVED" in defects[0], defects


def test_the_AFTER_KEY_claim_is_held_by_the_GENERATOR_and_its_count_by_this_file():
    """Why the fourth of LD-618's four claims is DECLINED from the registry rather than added
    to it — driven, not argued.

    Doctor the docx write-op registry so the **delete** serializer emits an ``after`` key, the
    way a change landing a preview pair on a removal would, and two things happen at once: the
    generator **refuses to generate** the region at all (so the byte-identity guard in
    ``tests/test_plan_field_docs.py`` reddens), and this file's derived count for the intro
    sentence falls to zero (so :func:`test_the_STATED_COUNTS_are_DERIVED_from_the_code`
    reddens). A registry row resolving a symbol could not have seen either.
    """
    from larkdocio.write import ops as write_ops
    from larkdocio.write import plan_field_docs

    assert derived_shapes_with_no_after_key() == 1

    def _delete_with_a_pair(entry):
        d = {}
        if entry.is_resolved:
            d["block_id"] = entry.block_id
            d["before"] = entry.before
            d["after"] = entry.after
        else:
            d["refusal"] = None
        return d

    saved = write_ops.OPS
    try:
        write_ops.OPS = tuple(
            dataclasses.replace(desc, serialize=_delete_with_a_pair)
            if desc.kind == "delete" else desc
            for desc in saved)
        # plan_field_docs read OPS at import, so the doctored table is put where it reads it —
        # the same shape tests/test_plan_field_docs.py uses for its own census probe.
        assert plan_field_docs._ops is write_ops
        assert derived_shapes_with_no_after_key() == 0, (
            "the shape census did not follow the serializer — this proof is not driving the "
            "mechanism it claims to")
        with pytest.raises(Exception) as raised:
            plan_field_docs.plan_field_markdown()
        # the MESSAGE, not merely "something raised" — a bare `raises` would be satisfied by
        # the proof breaking its own subject
        assert "says one thing about its `after` key and its serializer says the other" in str(
            raised.value), raised.value
    finally:
        write_ops.OPS = saved

    assert derived_shapes_with_no_after_key() == 1, "the proof did not restore its subject"


# --------------------------------------------------------------------------- #
# 8. RED FIRST, PER CLAIM, FROM THE REAL MECHANISM (LD-623 AC2).               #
#                                                                             #
#    A row that matches today's prose proves nothing about whether it would    #
#    catch the change it exists to catch. So for every claim this issue pins,  #
#    the member is made to EXIST in the file on disk — and the guard is run    #
#    against that tree, in a subprocess, and must fail BY EXIT CODE. The       #
#    shadow-PYTHONPATH tree is LD-618's instrument, reused: cheaper than a     #
#    worktree, and it avoids the two worktree-only phantoms in this suite.     #
# --------------------------------------------------------------------------- #

_LANDINGS = {
    # ---- claim 1: THERE IS NO `draft.create` (twice in the guide, one falsifier) --------- #
    "draft.create": dict(
        edits=(("larkdocio/base/model.py",
                '    def set(self, record_id: str, field_name: str, value: str) -> "TableDraft":',
                '    def set(self, record_id: str, field_name: str, value: str) -> "TableDraft":',
                '    def create(self, cells=None) -> str:\n'
                '        """The fourth verb, as it would land."""\n'
                '        return self.add(cells)\n\n'
                '    def set(self, record_id: str, field_name: str, value: str)'
                ' -> "TableDraft":'),),
        arms=("falsifier",),
        expect=("THE CLAIM IS NOW FALSE", "TableDraft.create"),
    ),
    # ---- claim 3: no `.raw()` on a `BaseRow` (the half with a backticked owner) ---------- #
    "BaseRow.raw": dict(
        edits=(("larkdocio/base/table.py",
                "    raw_fields: Optional[Mapping[str, Any]] = None\n",
                "    raw_fields: Optional[Mapping[str, Any]] = None\n",
                "    raw_fields: Optional[Mapping[str, Any]] = None\n\n"
                "    def raw(self, field_name):\n"
                '        """The loud accessor, as it would land on the READ model\'s row."""\n'
                "        return (self.raw_fields or {})[field_name]\n"),),
        arms=("falsifier",),
        expect=("THE CLAIM IS NOW FALSE", "BaseRow.raw"),
    ),
    # ---- claim 2: no `clear` op — AND the count in the same sentence --------------------- #
    "the clear op": dict(
        edits=(("larkdocio/sheets/ops/__init__.py",
                "OPS: Tuple[SheetsOpDescriptor, ...] = (\n",
                "OPS: Tuple[SheetsOpDescriptor, ...] = (\n",
                "OPS: Tuple[SheetsOpDescriptor, ...] = (\n"
                "    SheetsOpDescriptor(\n"
                '        kind="clear",\n'
                "        request_type=(),\n"
                '        write_kind="value",\n'
                "        entry_ops=(),\n"
                "        preview=_preview_value,\n"
                "        apply=_apply_value_one,\n"
                "    ),\n"),),
        arms=("falsifier", "counts"),
        # the op row reddens, AND the count row reddens on its own account — a tenth descriptor
        # makes the shipped "nine" false, so the two halves of one sentence each bite. Before
        # LD-626 this arm expected "THE STALE COUNT MOVED" instead: the count was quarantined as
        # a dated pair because the prose said six, and the landing moved the derived side of it.
        # The quarantine went with the reword, so the bite is now by DERIVATION, which is
        # strictly the stronger arm — it no longer depends on a tuple existing.
        expect=("THE CLAIM IS NOW FALSE", "sheets-write#clear", "THE COUNT IS NOW FALSE"),
    ),
    # ---- claim 4: "on ONE shape there is no `after` key at all" -------------------------- #
    "the delete shape's after key": dict(
        edits=(("larkdocio/write/ops.py",
                'def _serialize_delete(entry) -> dict:\n'
                '    d: dict = {}\n'
                '    if entry.is_resolved:\n'
                '        d["block_id"] = entry.block_id\n'
                '        d["before"] = entry.before\n',
                'def _serialize_delete(entry) -> dict:\n'
                '    d: dict = {}\n'
                '    if entry.is_resolved:\n'
                '        d["block_id"] = entry.block_id\n'
                '        d["before"] = entry.before\n',
                'def _serialize_delete(entry) -> dict:\n'
                '    d: dict = {}\n'
                '    if entry.is_resolved:\n'
                '        d["block_id"] = entry.block_id\n'
                '        d["before"] = entry.before\n'
                '        d["after"] = entry.after\n'),),
        arms=("counts", "generated-region"),
        # the claim's own half is held by the GENERATOR (it refuses to generate, so the
        # byte-identity arm reddens); its COUNT is held here
        expect=("THE COUNT IS NOW FALSE",),
    ),
}


@pytest.mark.parametrize("claim", sorted(_LANDINGS))
def test_the_GUARD_FAILS_by_EXIT_CODE_on_a_tree_where_THE_CLAIM_IS_FALSE(claim, tmp_path):
    """AC2, one case per pinned claim: the member really exists in the file on disk, and the
    guard must fail by exit code.

    The shared control — :func:`test_the_CONTROL_scratch_tree_is_GREEN_on_every_arm` — is what
    makes each of these a proof rather than a demonstration that shadowing a source tree breaks
    something.
    """
    landing = _LANDINGS[claim]
    scratch_src = _scratch_tree(tmp_path / "landed", landing["edits"])
    if scratch_src is None:
        pytest.skip("no src/ checkout to copy — this proof needs the repository layout")

    red = _run_arms(scratch_src, landing["arms"])
    assert red.returncode != 0, (
        f"THE GUARD PASSED on a tree where {claim} really exists. The shipped sentence is false "
        f"on that tree and nothing said so — which is the exact state LD-618's AC6 found for "
        f"all four of these claims.\n{red.stdout}\n{red.stderr}")
    for expected in landing["expect"]:
        assert expected in red.stdout, (expected, red.stdout, red.stderr)

    # And the real tree is untouched — a proof that can edit its own subject proves nothing.
    for relative, _context, _old, new in landing["edits"]:
        assert new not in (REPO_ROOT / "src" / relative).read_text("utf-8"), relative


def test_the_CONTROL_scratch_tree_is_GREEN_on_every_arm(tmp_path):
    """The control for section 8, run once for all four landings: an UNEDITED scratch tree, the
    same shadowed ``PYTHONPATH``, every arm the landings use — and it must exit 0.

    Without this, each red above would be evidence that copying ``src/`` and shadowing it breaks
    something, not evidence about the claim.
    """
    scratch_src = _scratch_tree(tmp_path / "control", ())
    if scratch_src is None:
        pytest.skip("no src/ checkout to copy — this proof needs the repository layout")
    green = _run_arms(scratch_src, sorted(_ARMS))
    assert green.returncode == 0, (
        "the CONTROL failed, so every red in this section is about the scratch tree rather than "
        f"about the claim.\n{green.stdout}\n{green.stderr}")
