"""larkdocio.write.absences — what this surface does NOT do, stated as DATA.

A consumer meets a missing verb in one of two ways. Either the library tells them it is
missing, with the reason and how firmly it was established, or they read a list that does not
contain it and conclude the *platform* cannot do it. The second is what happened: four
separate reports of *"the library cannot do X and no door says so"* — an @mention, character
styling, growing a table that already exists, flipping a checkbox — landed against a surface
that already carried exactly ONE such row and no home for the rest.

**This module is that home, and it deliberately mints no new vocabulary.** The rows use the
shipped ``Surface.absences`` contract — ``id`` / ``statement`` / ``verification`` /
``evidence`` / ``instead``, in that order (:data:`ABSENCE_ROW_KEYS`) — and are projected
verbatim onto the docx-write surface by :mod:`larkdocio.capabilities`, under a guard that
bites in both directions (a row here with no projection reddens; a projected row authored
anywhere else reddens). A second spelling of "absence" on a surface that already had one is
the exact defect these rows describe, one layer up.

**Why every row's own label is** ``derived-from-shipped-code``. A row's ``verification``
covers its ``statement``, and every statement here is about **what this library ships** —
a closed set of request families, a closed enum of block kinds, a helper with one call site.
That is checkable without a call, and it is the weaker of the two strengths a row can carry,
so it stays on the row. The other labels in :data:`ABSENCE_VERIFICATION_LABELS` are worn by
CLAUSES inside ``evidence``, where a fact about somebody else's API belongs: the table row a
probe really did append (``measured``), the routes nobody here has ever called
(``unmeasured``). Promoting a row's single label to ``measured`` would claim this library's
own absence had been established by a live call, which it was not — an over-labelled row is
worse than a verbose one.

**And not one of these rows is a to-do list.** Each says what a caller does *instead*, today,
with what ships.
"""
from typing import Tuple

#: The shipped ``Surface.absences`` row contract, in serialization order. Named here because
#: the register is validated against it at import — a row that grows a sixth key, or spells
#: one differently, is a second vocabulary arriving one field at a time.
ABSENCE_ROW_KEYS = ("id", "statement", "verification", "evidence", "instead")

#: **THE** enumeration of how firmly an absence — or a clause inside one's ``evidence`` — was
#: established. One list, read by the rows below and by every projection of them; a free
#: string in a row's ``verification`` is refused at import.
#:
#: * ``derived-from-shipped-code`` — checkable in this library's own source, with no call;
#: * ``measured`` — a live call established it. A fact about Lark's API, never about this
#:   library's own surface, and it carries its own scope wherever it is used;
#: * ``unmeasured`` — never called here: neither refuted nor supported. The honest label for
#:   a route a reader might otherwise assume was tried and rejected.
ABSENCE_VERIFICATION_LABELS = ("derived-from-shipped-code", "measured", "unmeasured")


def _docx_body_request_families() -> tuple:
    """The body-writing request families this surface ships — READ OFF THE CODE.

    **The derivation is the op-descriptor registry** (:data:`larkdocio.write.ops.OPS`), the one
    seam a write op is registered at: every descriptor names its request class and declares
    what it ``writes``, so this answer is *every registered family whose write target is*
    :data:`~larkdocio.write.ops.DOCUMENT_BODY`. A sixth family joins by being registered — it
    cannot arrive without answering the question, because a descriptor with no valid ``writes``
    is refused at construction.

    **The two comment families are excluded by that criterion, not by a second list.**
    ``CreateCommentRequest`` and ``RemoveCommentRequest`` register as
    :data:`~larkdocio.write.ops.REVIEW_CONVERSATION` — they write the review conversation laid
    over the document, not its body — which is the same distinction
    :attr:`larkdocio.write.preview.PlanEntry.is_comment` asks of one plan entry, asked here of
    a family.

    **LD-586.** This function used to hand-type a four-name tuple under a docstring promising
    "a fifth family would join this answer by existing". ``GrowTableRequest`` shipped at LD-575
    and did not join, so the row below — and the ``derived from the shipped surface`` label the
    guide stamps on it — asserted a closed set of four that the code refuted. The promise is
    now kept; the row's *conclusion* (no move, no reorder, delete-and-recreate) never depended
    on the count and is unchanged.
    """
    from larkdocio.write import ops  # local import — ops sits above the whole engine
    return tuple(sorted(desc.request_type.__name__ for desc in ops.OPS
                        if desc.writes == ops.DOCUMENT_BODY))


#: **The docx surface's no-move absence** — a contract-level fact, stated where the question is
#: asked. It is what makes a whole-document reorganisation delete-and-recreate, and it was
#: findable only inside one recipe's prose until it was recorded here.
#:
#: **The row carries two facts of DIFFERENT STRENGTH, and the labels are not merged.** The
#: ``statement`` is about **what larkdocio ships** — the body-writing request families are a
#: closed set in this library's own code, DERIVED from the op-descriptor registry rather than
#: typed here, so that half is checkable without a call and the
#: row's ``verification`` stays ``derived-from-shipped-code``. The ``evidence`` additionally
#: reports a **measured** fact about somebody else's API: Lark's docx **v1** exposes no
#: move/reorder route either, over eleven enumerated candidate spellings on one tenant on
#: 2026-08-16. Promoting the row's single label to ``measured`` would claim that larkdocio's own
#: absence was established by a live call, which it was not — so the **weaker label stays on the
#: row** and the measured half carries its own label and its own scope inside ``evidence``.
#: An over-labelled row is worse than a verbose one.
_DOCX_NO_MOVE_ABSENCE = {
    "id": "no-move-or-reorder-operation",
    "statement": (
        "There is NO move or reorder operation on this surface. The body-writing request "
        "families are " + ", ".join(_docx_body_request_families()) + " and no more, none of "
        "which relocates a block, so every whole-document reorganisation is "
        "DELETE-AND-RECREATE by contract. The reconciler states the same absence from the "
        "other side: a reorder in an edited block-identity projection is refused typed "
        "(marker-order-changed), not approximated, because the only way to express a move "
        "would be to delete the block and insert a copy — which destroys the block id every "
        "deep link and every anchored comment points at."
    ),
    "verification": "derived-from-shipped-code",
    "evidence": (
        "DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): the "
        "request families are a closed set in larkdocio.write; the reorder refusal is "
        "larkdocio.write.reconcile's marker-order-changed. "
        "AND, at a different strength — MEASURED, which is a fact about Lark's API and not "
        "about this library: docx v1 exposes no route that moves or reorders an existing "
        "block, probed 2026-08-16 over ELEVEN enumerated candidate spellings. Two move "
        "operation keys (move_block, move_to) on the documented block PATCH route and its "
        "batch_update twin answered 1770001 'invalid param' — the same code an operation key "
        "the route has never heard of answers, which a control established, so the refusal "
        "means 'unrecognised operation'; adopting an existing block id through "
        ".../blocks/{parent}/children was refused by the field-validation code with the "
        "violation 'children[*].block_type is required', i.e. a child is a NEW block "
        "descriptor and never an adoption; five "
        "invented .../move, .../blocks/move, .../children/move, .../children/batch_move and "
        "PATCH .../children spellings all answered the gateway's own non-JSON HTTP 404 '404 "
        "page not found'; and two bodies went to the documented .../descendant route, the "
        "second of which is the copy trap below. The pinned SDK agrees offline — its "
        "UpdateBlockRequest declares sixteen operation fields and none moves or re-parents a "
        "block — but that is spec-derived, not measured, and the claim does not rest on it. "
        "THE TRAP A code 0 HIDES: POST /open-apis/docx/v1/documents/{doc}/blocks/{parent}/"
        "descendant, given a well-formed body naming an EXISTING block id, answers HTTP 200 "
        "code 0 'success' and CREATES A NEW BLOCK — it reads the live id as a client-side "
        "temporary id and hands it back as temporary_block_id beside the new block's real id "
        "in data.block_id_relations. Read back, the original was still in its original place "
        "and the root child order was unchanged, so a caller who reads code 0 as 'moved' "
        "ships a duplicate. SCOPE of the measurement, which the claim may not exceed: one "
        "tenant, one day (2026-08-16), a tenant_access_token on the write credential pair, "
        "the larksuite.com OpenAPI domain, docx v1, three plain docx documents the probe "
        "created and destroyed. Explicitly UNMEASURED, neither refuted nor supported: a "
        "user_access_token; any other tenant; wiki-wrapped documents; any docx API version "
        "other than v1; the Lark web client's internal reorder API; any move spelling outside "
        "the eleven; and whether the descendant route deep-copies a SUBTREE (the block it "
        "copied was a leaf). The verdict and the copy trap's captures were retired from the "
        "dev repo on 2026-09-18, so the scope above is stated in full rather than cited."
    ),
    "instead": (
        "guide(section=\"recipe-reorganise-a-document-there-is-no-move-so-a-reorder-is-"
        "delete-and-recreate\") — comments first, insert before delete, keep the blocks that "
        "did not move, and verify by reading the order back."
    ),
}


#: **No @mention can be authored.** Reported as *"the library cannot do this and no door says
#: so"*: a caller looking for a mention finds mention handling on the READ side and reasonably
#: concludes the write side has some too.
_NO_MENTION_AUTHORING = {
    "id": "no-mention-authoring",
    "statement": (
        "There is NO way to author an @mention on this surface — not of a person, a document "
        "or a chat. A created run is a text run that may carry ONE styling, the link anchor: "
        "larkdocio.write.model.TextSpan has exactly two fields, `text` and `link_url`, and "
        "the encoder emits no mention element of any kind. A mention that is ALREADY in a "
        "block is preserved rather than dropped: a whole-block edit rebuilds the block's "
        "runs element by element, and a sub-span edit whose span overlaps a mention refuses "
        "typed (span-not-splittable) instead of writing over it."
    ),
    "verification": "derived-from-shipped-code",
    "evidence": (
        "DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): "
        "larkdocio.write.model.TextSpan is a two-field frozen value, NewBlockKind is a closed "
        "enum with no mention member, and no module under larkdocio.write emits a "
        "mention_user or mention_doc element — the mention code this library does ship is the "
        "READER's (larkdocio.contacts resolves a mention's open id to a display name at "
        "download time), which is what makes the write-side absence easy to miss. "
        "UNMEASURED, neither refuted nor supported: whether the docx create and patch routes "
        "would ACCEPT a mention element was never called from here, so this row claims only "
        "that this library does not send one."
    ),
    "instead": (
        "Author the name as plain text, and address the person out of band — this surface's "
        "comment operations create a whole-document comment, which notifies the way a caller "
        "usually wanted the mention to. A mention already in the text survives any edit that "
        "does not overlap it."
    ),
}


#: **No character styling, in either direction.** The reported shape was a caller wanting bold
#: on text they were writing; the more valuable half of the answer is that styling they did NOT
#: write is preserved, which is a different question with a different answer.
_NO_CHARACTER_STYLE = {
    "id": "no-character-style-operation",
    "statement": (
        "There is NO operation that applies character styling — bold, italic, underline, "
        "strikethrough, inline code or colour — to text, whether the text already exists or "
        "is being created. The docx block PATCH route's own update_text_style operation is "
        "called by exactly ONE call site in this library and for exactly ONE field, a todo "
        "block's done bit (larkdocio.write.apply.build_todo_done_update, field mask 2): a "
        "checkbox is block state, not character styling, and no other field of that "
        "operation is ever written. A created run carries exactly one styling, "
        "the link anchor on larkdocio.write.model.TextSpan. Styling a caller did NOT author "
        "is nevertheless PRESERVED: larkdocio.write.client.to_write_elements rebuilds a "
        "block's runs element by element, so a whole-paragraph edit and a sub-span edit both "
        "leave the surrounding runs byte-identical."
    ),
    "verification": "derived-from-shipped-code",
    "evidence": (
        "DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): "
        "update_text_style has exactly one call site in this library and it writes exactly "
        "one field. The one styling a "
        "created run can carry is TextSpan.link_url; bold, italic, strikethrough, inline code "
        "and colour are not fields on that type, so they are inexpressible by construction "
        "rather than refused at runtime, and no code path assembles a text_element_style for "
        "them. That holds inside a TABLE CELL too, where the link anchor is now authorable "
        "and nothing else is: the cell's elements come from the same span encoder, which "
        "emits link and no other key. "
        "SUPERSEDED IN PART, with the original reason preserved: this row used to say "
        "update_text_style was called by no module at all, and that its behaviour was "
        "UNMEASURED because nothing here had ever called it. Both clauses were true when "
        "written and the reason for stating them stands — a route this library names in a "
        "table is a description of Lark's surface, not a capability of this library, and "
        "saying so is what keeps a reader from deriving a styling recipe from the table. "
        "Only the conclusion moved: the done bit's field mask now has a call site. "
        "AND, at a different strength — MEASURED, which is a fact about Lark's API: mask 2 "
        "moves done and leaves align, folded, the item's own text and a nested child's id / "
        "text / state untouched, established on a throwaway document with the masks swept "
        "and re-proved by read-back in this library's own live write ring; the measurement "
        "is recorded in build_todo_done_update's own docstring, which cites where it was "
        "taken. SCOPE of that measurement, which this row may not exceed: the done field "
        "under mask 2, on a todo block. "
        "UNMEASURED, neither refuted nor supported: every OTHER field of update_text_style — "
        "align, folded and the character-style fields — has still never been written from "
        "this tree, so nothing here says what writing one would do."
    ),
    "instead": (
        "Apply character styling in the Lark editor. In authored content, a link anchor IS "
        "available — a TextSpan carrying link_url, on any kind that accepts spans (the write "
        "brief lists them) and, at create time, inside a TABLE CELL authored as a TextSpan "
        "sequence rather than a string — and existing styling survives an edit untouched, so "
        "text can be rewritten without losing the formatting somebody else applied."
    ),
}


#: **What a table's grid CANNOT be changed to, now that appending a row ships.** This row
#: occupies the slot ``no-grow-operation-for-an-existing-table`` held, and it is a NARROWING
#: rather than a strike: that row said no operation changes an existing table's grid at all,
#: and the half of it about **appending a row** is now false while its reason — that the grow
#: mechanism shipped, was measured, and was simply not reachable as an operation — is exactly
#: why the operation exists. The register must never claim an absence beside a shipped op, and
#: it must not delete the parts still absent either; so the conclusion moves and the reason
#: travels inside ``evidence`` (a rationale-free strike is what gets a settled argument
#: re-litigated).
_NO_TABLE_GRID_CHANGE_BEYOND_APPEND = {
    "id": "no-table-grid-change-beyond-appending-a-row",
    "statement": (
        "APPENDING a row to a table that already exists IS a shipped operation: "
        "GrowTableRequest, anchored by the table's own block id or by a TableLocator, through "
        "the same plan gate, the same whole-document revision guard and the same refusal set "
        "as every other change, and it preserves the table's block id and every pre-existing "
        "cell id, in order. NOTHING ELSE about a table's grid can be changed. There is no "
        "operation that REMOVES a row or a column, none that appends a COLUMN, and none that "
        "inserts a row anywhere but the end. Asking for the last of those is REFUSED, typed "
        "table-grow-unsupported (larkdocio.write.model.refusal.RefusalReason), naming the "
        "append spelling as the remedy — never reported as applied. A table's CELLS are "
        "editable too (an EditRequest anchored by a TableLocator replaces one cell's whole "
        "text), which is a different operation from changing the grid."
    ),
    "verification": "derived-from-shipped-code",
    "evidence": (
        "DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): the "
        "request families are a closed set and GrowTableRequest is the only one that touches "
        "a grid; it carries an anchor and a row index and nothing that could name a removal, "
        "a column or a second row; and the append itself is ONE loop with two callers "
        "(larkdocio.write.apply._append_table_lines, reached from the create path's "
        "_grow_table_grid and from the grow op's own apply leg), so there is no second "
        "definition of the operation that could quietly do more. "
        "SUPERSEDED, with the original reason preserved: this slot used to hold "
        "no-grow-operation-for-an-existing-table, which stated that NO operation added or "
        "removed a row or a column of an existing table, because the grow mechanism's only "
        "call site was inside the plan-gated insert — so the mechanism shipped and was "
        "measured while being unreachable as an operation. Most of the routes left to a caller "
        "cost the table's block id and every "
        "cell id in it, and the only route that preserved them was outside the plan gate "
        "entirely. That reasoning is why this row reads the way it does. Only its conclusion "
        "moved, and only for the append case: the rest of the grid is still absent, and the "
        "one thing that changed is that a caller no longer has to leave the gate to add a row. "
        "AND, at a different strength — MEASURED, which is a fact about Lark's API: "
        "insert_table_row {\"row_index\": -1} on the docx block PATCH route APPENDS at the "
        "end and leaves every pre-existing cell id untouched and in order, and the row axis "
        "grew to 200 with no refusal at any row — measured on disposable documents the probes "
        "created and trashed, and recorded in _grow_table_grid's own docstring, which names "
        "where the measurement was taken; the shipped operation re-proves the cell-id half by "
        "read-back in this library's own live write ring. It needs no new endpoint and no new "
        "scope: it rides the existing block PATCH. SCOPE of that measurement, which this row "
        "may not exceed: appending at the end, rows 1-200, on documents the probe made. "
        "Explicitly UNMEASURED, neither refuted nor supported: rows 201-500 — the library's "
        "own authored-grid ceiling is 500 cells and no platform row cap has ever been found "
        "here, so a grow past 200 rows is attempted rather than refused, and nothing here says "
        "what Lark would answer — and MID-TABLE insertion at any index other than -1, which "
        "has never been called from this tree and which no measurement in it covers, so its "
        "refusal is a statement about what larkdocio ships and not about what the API can do. "
        "Removal is unmeasured in the same sense: no delete_table_row spelling has been called "
        "from this tree in either direction. And the COLUMN axis is a deliberate scope call "
        "rather than a missing measurement — the primitive is measured (the axis grew to 100, "
        "and Lark refuses the 101st column in its own words, 1770010 'too many table column'), "
        "and it is left unshipped because appending a row leaves every pre-existing cell's "
        "row-major position exactly where it was while appending a column moves it, so a "
        "caller holding an offset into the grid would silently be holding the wrong one."
    ),
    "instead": (
        "To add a row to a table that already exists, use the shipped operation: a "
        "GrowTableRequest through dry_run and apply, like every other change. N rows are N "
        "requests, each previewed and each exactly one write call. For anything else about the "
        "grid — removing a row or a column, adding a column, or inserting a row in the middle "
        "— author the table again at the shape you want (NewBlock.table takes the whole grid, "
        "and a grid wider or taller than the create call accepts is grown to its authored "
        "shape inside the same plan-gated insert) and delete the old one, which changes the "
        "block id of the table and of every cell in it, as every delete-and-recreate on this "
        "surface does; or make the change in the Lark editor. To change what a cell SAYS, "
        "patch the cell: an EditRequest with a TableLocator."
    ),
}


#: **What a whole-block edit cannot carry, now that the checkbox is not on the list.** This
#: row occupies the slot ``todo-done-bit-is-not-editable`` held, and it is a NARROWING rather
#: than a strike: that row recorded an open defect — a flipped checkbox reported *applied*
#: while the bit did not move — and the defect is fixed, so the row's conclusion is false
#: while its reason is exactly why this successor exists. A silent success is worse than a
#: refusal; the residual therefore refuses, typed, instead of inheriting the old behaviour
#: under a property nobody had named yet. (A rationale-free strike is what gets a settled
#: argument re-litigated, so the reason travels inside ``evidence``.)
_NO_NON_TEXT_BLOCK_PROPERTY_EDIT = {
    "id": "no-block-property-edit-beyond-text",
    "statement": (
        "A whole-block edit of an existing block writes that block's TEXT and — since the "
        "checkbox shipped — a todo's done bit (todo.style.done), and NO other property of it. "
        "There is no "
        "operation that changes a code block's fence language, a diagram's theme, a heading's "
        "level, a block's type or a list item's nesting in place. The important half is what "
        "happens when a caller asks anyway: an edited projection whose only difference is one "
        "of those properties is REFUSED, typed change-not-expressible "
        "(larkdocio.write.model.refusal.RefusalReason), naming the property and the "
        "delete-and-insert route — never reported as applied. A change this surface cannot "
        "write does not become a green apply log."
    ),
    "verification": "derived-from-shipped-code",
    "evidence": (
        "DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): "
        "larkdocio.write.model.EditRequest carries a replacement string and a todo_done bit "
        "and no other property, and the compiler enumerates the rest of a composed block's "
        "fields as the residual it refuses "
        "(larkdocio.write.compiler.EDIT_UNWRITABLE_BLOCK_FIELDS, held against "
        "larkdocio.write.model.NewBlock's own dataclass fields by a guard, so a new authoring "
        "field cannot arrive unclassified). A block type or heading level change refuses "
        "earlier still, at reconcile time, as block-type-mutation. The whole path — project, "
        "edit the marker, reconcile, compile, dry_run, apply — is driven end to end in this "
        "library's offline suite for both outcomes: the checkbox flip that writes the bit, and "
        "the fence-language change that refuses. "
        "SUPERSEDED, with the original reason preserved: this slot used to hold "
        "todo-done-bit-is-not-editable, which stated that a todo's done bit could not be "
        "changed at all and that an edit which tried reported SUCCESS while the checkbox did "
        "not move — recorded as an OPEN DEFECT rather than as a boundary somebody chose, "
        "precisely because a banner reading 'not editable' beside an engine answering "
        "'applied' would have documented the bug as a design. That reasoning is why this row "
        "reads the way it does. Only its conclusion moved: the done bit is writable now, so "
        "the surviving absence is the rest of a block's properties, and the silence the old "
        "row was about is closed by a refusal rather than by a banner. "
        "AND, at a different strength — MEASURED, and cited rather than re-derived here: "
        "the done bit's own wire spelling and its blast radius are recorded in "
        "build_todo_done_update's own docstring, which names where the measurement was taken, "
        "and they are re-proved by read-back in this library's live write ring. "
        "UNMEASURED, neither refuted nor supported: whether Lark's API offers ANY route to "
        "the other properties named above has not been established from this tree — the "
        "absence is this library's, and no claim is made about the platform's."
    ),
    "instead": (
        "For a checkbox, edit it in place: flip - [ ] to - [x] in an edited block-identity "
        "projection and the bit moves, or create the item in the state you want with "
        "NewBlock.todo(text, done=True). For any other property, delete the block and insert "
        "its replacement — two commits, and the block id changes, which takes comment anchors "
        "with it — or make the change in the Lark editor."
    ),
}


#: **No retitle.** The row a reader is most likely to write a confident workaround into,
#: because this library publishes an ADDRESSING fact that looks like one.
_NO_DOCUMENT_RETITLE = {
    "id": "no-document-retitle-operation",
    "statement": (
        "There is NO operation that renames or retitles an existing document. This surface's "
        "file lifecycle creates a document with a title and destroys one; nothing between the "
        "two changes the title of a document that already exists, and no request family "
        "carries a title at all. The document's own root Page block is not an exception: it "
        "is not creatable through this engine either, and the Markdown projection conserves "
        "it rather than inviting an edit to it."
    ),
    "verification": "derived-from-shipped-code",
    "evidence": (
        "DERIVED-FROM-SHIPPED-CODE (this row's label, and it covers the statement above): "
        "larkdocio.write.client.WriteClient exposes the file lifecycle and the block routes "
        "and no rename among them; no request family carries a title; no module under "
        "larkdocio.write names a retitle verb. "
        "UNMEASURED, neither refuted nor supported — and said out loud, because a reader will "
        "otherwise derive a route from an addressing fact this library DOES publish: the root "
        "Page block's id equals the document_id, so a document's page block is addressable by "
        "the document's own id. That is how you ADDRESS it, not evidence that patching it "
        "retitles anything: whether the block PATCH route on a page block moves the DOCUMENT's "
        "title has never been called from this tree, by this library or by any probe recorded "
        "in it. It is neither a refusal nor a recipe, and a confident route written from the "
        "equivalence alone would be a guess wearing the shape of an answer."
    ),
    "instead": (
        "Create the document with the title you want (the lifecycle's create takes one), or "
        "rename it in the Lark client. A caller who needs it done programmatically makes that "
        "call themselves — this library ships no verb for it and does not pretend the "
        "platform lacks one."
    ),
}


#: **THE REGISTER.** Authored here, projected verbatim onto the docx-write surface's
#: ``absences`` — the no-move row FIRST, because it shipped first and a consumer's stored
#: index into this list should not move under them for a reason that is not a capability
#: change.
DOCX_WRITE_ABSENCES: Tuple[dict, ...] = (
    _DOCX_NO_MOVE_ABSENCE,
    _NO_MENTION_AUTHORING,
    _NO_CHARACTER_STYLE,
    # LD-575 took this SLOT from ``no-grow-operation-for-an-existing-table`` rather than
    # appending beside it, the same call LD-574 made for the row below: the tuple's order is
    # load-bearing, and a narrowing is not a capability change for any row but its own, so no
    # other row's index moves under a consumer.
    _NO_TABLE_GRID_CHANGE_BEYOND_APPEND,
    # LD-574 took this SLOT from ``todo-done-bit-is-not-editable`` rather than appending
    # beside it: the tuple's order is load-bearing and a narrowing is not a capability
    # change for any row but its own, so no other row's index moves under a consumer.
    _NO_NON_TEXT_BLOCK_PROPERTY_EDIT,
    _NO_DOCUMENT_RETITLE,
)


#: The fence that delimits the generated absence region in a document that carries it. The
#: BEGIN fence is the region's FIRST LINE VERBATIM — the HTML comment it opens is closed on the
#: next line, which carries the regeneration command — so a reader of these constants can find
#: the region with them unmodified. Same shape as the CONFIG-SCHEMA region, deliberately: the
#: precedent is a projection pinned by BYTE IDENTITY, which is the only guard shape that
#: actually stops a hand-kept second copy from drifting.
ABSENCE_REGION_BEGIN = "<!-- BEGIN DOCX-WRITE-ABSENCES (generated"
ABSENCE_REGION_END = "<!-- END DOCX-WRITE-ABSENCES -->"

#: The one-liner that regenerates the region, quoted into the region's own header so the
#: instruction cannot drift away from the thing it regenerates.
ABSENCE_REGENERATE = (
    'python -c "from larkdocio.write.absences import docx_write_absences_markdown as m; '
    'print(m())"'
)


def docx_write_absences_markdown() -> str:
    """The generated absence region: **the whole register**, one entry per row, in order.

    **Why the whole register and not a subset.** The document that carries this region is the
    packaged guide's authoring section, which is *responsible for* two of these rows on any
    narrow reading — but there is no subset marker on a row, so a subset would have to be named
    in a second place, and a hand-typed list of which absences a table owns is itself the
    duplicate this projection exists to remove. "Responsible for" is therefore **all of them**,
    and the guard is byte identity.

    Rendered as labelled paragraphs rather than a table on purpose: the ``evidence`` fields
    carry whole enumerations with their scope, which no table cell can hold, and a table here
    would also sit in the guide's dialect section beside two tables that are looked up by their
    HEADERS — a third table there is a hijack waiting to happen.
    """
    lines = [
        ABSENCE_REGION_BEGIN,
        f"     regenerate with:  {ABSENCE_REGENERATE}  -->",
        "",
        "**What this surface does NOT do — the whole register.** Every entry below is a "
        "missing verb of the docx WRITE surface, stated as data and read straight off "
        "`capabilities(full=True)[\"surfaces\"][\"docx-write\"][\"absences\"]`. Each one carries "
        "how firmly it was established and what to do **instead, today**; none of them is a "
        "to-do list. The one to read before you trust an apply log is "
        "`no-block-property-edit-beyond-text`: it is what an edit of an existing block can "
        "and cannot carry, and it is the row that says what happens — a typed refusal, never "
        "a green log — when you ask for a property it cannot write.",
    ]
    for row in DOCX_WRITE_ABSENCES:
        lines += [
            "",
            f"**`{row['id']}`** — *{row['verification']}*",
            "",
            row["statement"],
            "",
            f"*How it was established.* {row['evidence']}",
            "",
            f"*Instead.* {row['instead']}",
        ]
    lines += ["", ABSENCE_REGION_END]
    return "\n".join(lines)


def _validate_register() -> None:
    """Refuse a malformed row **at import**, not at the guard that would have caught it.

    The register is data a consumer reads through ``capabilities()``; a row missing its
    ``instead``, or wearing a ``verification`` label nobody enumerated, is exactly the drift
    this module exists to make impossible. The offline suite asserts the same properties —
    this is the cheaper of the two and it fires first.
    """
    seen = set()
    for row in DOCX_WRITE_ABSENCES:
        if tuple(row) != ABSENCE_ROW_KEYS:
            raise ValueError(
                f"absence row {row.get('id')!r} does not carry the shipped Surface.absences "
                f"contract {ABSENCE_ROW_KEYS} in order, it carries {tuple(row)}")
        if row["verification"] not in ABSENCE_VERIFICATION_LABELS:
            raise ValueError(
                f"absence row {row['id']!r} wears the free-string verification label "
                f"{row['verification']!r}; the enumeration is "
                f"{ABSENCE_VERIFICATION_LABELS}")
        if not all(isinstance(value, str) and value.strip() for value in row.values()):
            raise ValueError(f"absence row {row['id']!r} carries an empty field")
        if row["id"] in seen:
            raise ValueError(f"two absence rows share the id {row['id']!r}")
        seen.add(row["id"])


_validate_register()
