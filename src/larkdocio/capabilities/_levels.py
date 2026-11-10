"""The level model, per READ surface — object read vs Markdown projection.

LD-244: the verbatim pre-split slice, lines 2244-2369 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
from ._models import LevelDescriptor

# --------------------------------------------------------------------------- #
# The level model, per READ surface — which entry point is the full-fidelity     #
# object read and which is the Markdown projection.                             #
# --------------------------------------------------------------------------- #

def _docx_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "TWO LEVELS, and the objects are the source of truth. parse_docx_tree returns "
            "the document's real structure as Lark stores it — one typed node per block, "
            "each carrying its own block_id, the review anchors on it, its colors and its "
            "true heading level. parse_docx_content returns the Markdown projection of the "
            "same read: a flattened text rendering for a person to read, which drops all of "
            "that by design. The projection is OPTIONAL — a caller that works with the "
            "objects never has to produce any Markdown, and every write targets a block, "
            "never text."
        ),
        object_entry_point="larkdocio.read.parser.Parser.parse_docx_tree",
        object_returns=(
            "the tree — one typed larkdocio.model.Node per block, carrying its own "
            "block_id, the review-anchor ids the API reported on it and on each run inside "
            "it (comment_ids at both granularities), its colors and its true heading level"
        ),
        projection_entry_point="larkdocio.read.parser.Parser.parse_docx_content",
        projection_returns=(
            "the Markdown projection — one string, flattened for a person to read, dropping "
            "every field that has no Markdown form"
        ),
    )


def _comments_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "OBJECTS ONLY — there is no Markdown projection of a review conversation, and "
            "there could not be one: the Markdown projection drops review anchors, so a "
            "comment is reachable only from the objects. comments() joins each comment to "
            "the block (or the run of words inside a block) a reviewer anchored to, using "
            "the anchors the parsed tree already carries. comments(token) reads the file's "
            "WHOLE comment list and the join needs nothing more — for_node reads each node's "
            "own anchors off that result. Passing root= instead makes the read ANCHOR-SCOPED: "
            "it costs no API call on a document with no anchors, but on one that has them it "
            "costs the same single call and returns FEWER comments, because a whole-document "
            "comment has no anchor and can never come back; such a result marks itself "
            "completeness 'anchor-scoped' and its disclosure says it is not the file's list. "
            "WHAT IS AND IS NOT IN A REPLY: the text plus, out of band, image_tokens for any "
            "picture pasted in (not spliced into the text, which the payload gives it no "
            "position in) — and REACTIONS ARE NOT READ AT ALL: no comment endpoint reports a "
            "reaction field, so a 'like' is invisible here and its absence is not evidence "
            "there is none."
        ),
        object_entry_point="larkdocio.comments.read.comments",
        object_returns=(
            "a CommentsRead — the comment objects plus the block-to-comment join "
            "(for_node), with authors as raw ids and an availability flag"
        ),
    )


def _contacts_read_levels() -> LevelDescriptor:
    # LD-348: the second verb's three disclosures are QUOTED off the module that authors them,
    # never re-typed here — the dual truth, the measured reach and the mobile caveat each exist
    # in exactly one place in this library, and this is a citation of that place.
    from larkdocio.contacts.lookup import (
        MEASURED_REACH,
        MOBILE_LEG_UNOBSERVED,
        POINT_QUERY_ONLY,
        UNRESOLVED_IS_UNDIFFERENTIATED,
    )

    return LevelDescriptor(
        summary=(
            "TWO FORWARD VERBS, ONE ANSWER TYPE. resolve_user takes a display NAME; "
            "resolve_colleague takes an EMAIL or a MOBILE, on a different endpoint family "
            "(contact/v3/users/batch_get_id) that does not inherit the search route's starved "
            "contacts data range. An address route is NOT a name route: resolving an arbitrary "
            "user's NAME remains unavailable here and neither verb stands in for it. "
            + POINT_QUERY_ONLY + " " + UNRESOLVED_IS_UNDIFFERENTIATED + " " + MEASURED_REACH
            + " " + MOBILE_LEG_UNOBSERVED + " "
            "OBJECTS ONLY, and there is nothing to project: a lookup's answer is one id or a "
            "refusal, not a document. resolve_user(name=...) returns a NameLookup carrying "
            "EITHER exactly one UserRef OR a typed Refusal — never both, never neither — plus "
            "a MANDATORY partiality disclosure, so a partially-failed lookup cannot be "
            "reported as a clean answer. Matching is done CLIENT-SIDE with casefold + "
            "whitespace-normalized EXACT equality over the display strings the directory "
            "itself reports; the server is broader than that (token-prefix, case-insensitive, "
            "observed live), which is exactly why the contract is re-applied rather than "
            "delegated. A missing scope RAISES LarkPermissionError instead of returning a "
            "refusal, because 'I could not look' and 'I looked and nobody matched' are "
            "different facts and a caller must be able to branch on which one happened."
        ),
        object_entry_point="larkdocio.contacts.resolve_user",
        object_returns=(
            "a NameLookup — exactly one UserRef (open_id + the display name it matched) or a "
            "typed Refusal (not-found / ambiguous, with open_id candidates and never their "
            "names), always alongside the partiality disclosure. resolve_colleague returns the "
            "SAME type, so a caller branches on one shape whichever question it asked; on that "
            "route the UserRef carries no display name, because the endpoint returns none and "
            "an address is not a name"
        ),
    )


def _drive_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "THE STRUCTURED RESULT IS THE SOURCE OF TRUTH. read_folder returns a FolderRead — "
            "the walked tree (each child's token / type / name / url / depth), a per-child "
            "outcome (read, with its Markdown; skipped, with the reason IN LARK'S OWN WORDS; or "
            "folder, the structural third kind), and the walk's own truncation records. The "
            "mechanical promise the whole surface is judged on holds on that result: accounted() "
            "is True when every walked child appears exactly once as a read or a disclosed miss "
            "— nothing the walk saw is dropped, and a miss is never silent. render_folder "
            "assembles ONE Markdown document from a FolderRead — a tree index, each read "
            "document under its own heading, then a disclosure section naming every child that "
            "was not read — but it is a COMPOSITION over the per-child Markdown the docx / "
            "Sheets / Base readers already produced, not one of the library's own "
            "Markdown-generating call sites, so it is named here rather than listed as a "
            "projection entry point. THE SAME RESULT HAS A MACHINE-READABLE PROJECTION: "
            "folder_manifest turns a FolderRead into a JSON-ready object with one flat row per "
            "walked child carrying its title, token, type and revision, plus the listing's "
            "created_time / modified_time / owner_id / url, the read-or-disclosed outcome, and "
            "the walk's truncations, cycles and refusals — the input a change-detection ledger "
            "wants, written by the folder command's --dump flag as <folder token>.json. A "
            "revision is reported ONLY where the read already held one (a document's "
            "revision_id, a spreadsheet's revision) and is marked unavailable WITH THE REASON "
            "everywhere else: never fabricated, never inferred, never silently omitted, and no "
            "extra API call is ever made to obtain one. The library writes no files for a "
            "folder read; the on-disk shape is the folder CLI command's. THE PER-DOCUMENT DEEP "
            "READS ARE THE SAME OPT-INS THE DOWNLOAD VERB CARRIES — deep_read_sheets, "
            "fidelity_read_sheets and deep_read_bases, one spelling and one default (OFF) "
            "across both verbs. Off, a walk makes NO Sheets and NO Base API call and every "
            "embed stays the traceable placeholder; on, the documents inside read their embeds "
            "as inline tables, a deep read that fails degrades to that same placeholder without "
            "failing the child, and a child that fails outright is disclosed without failing "
            "the walk. They reach no endpoint the walk did not already reach."
        ),
        object_entry_point="larkdocio.drive.read.read_folder",
        object_returns=(
            "a FolderRead — the walked tree, each child's read/skipped/folder outcome (a read "
            "carries its Markdown; a skip carries its reason in Lark's own words), and the "
            "walk's truncation records; accounted() proves children == read + skipped + folders. "
            "render_folder turns it into one Markdown document (tree index · each document · a "
            "disclosure of what was not read)"
        ),
    )


def _sheets_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "TWO LEVELS, and the objects are the source of truth. query_sheets + "
            "read_used_range return the spreadsheet as objects — a SheetTab per tab (its "
            "opaque sheet_id, its geometry, its filter state, its merge regions) and a "
            "row-major values matrix. render_spreadsheet is a SEPARATE, optional call that "
            "turns those objects into titled Markdown tables for a person to read; it drops "
            "the merge geometry (a covered cell renders blank) and every id. A caller "
            "writing values back never needs it — a spreadsheet write targets a cell by its "
            "A1 range."
        ),
        object_entry_point="larkdocio.sheets.client.SheetsReadClient.read_used_range",
        object_returns=(
            "a UsedRange — the values as a row-major matrix, alongside the SheetTab objects "
            "query_sheets returns (sheet_id, geometry, filter state, merges)"
        ),
        projection_entry_point="larkdocio.sheets.table.render_spreadsheet",
        projection_returns=(
            "the Markdown projection — one titled GFM table per tab, dropping merge "
            "geometry and ids"
        ),
    )


def _base_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "TWO LEVELS, and the objects are the source of truth. read_base returns the "
            "structured intermediate — the app's name and time zone, then one table per table "
            "in the order the API listed them, each carrying its field specs, its record ids "
            "and its rendered cells. read_base_markdown is that read plus the Markdown "
            "rendering, which is the reading form: one heading and one GFM table per Base "
            "table. render_base turns a document you already hold into that Markdown with NO "
            "second network read. FIVE LIMITS TO PLAN AROUND, none of them incidental. (1) A "
            "STAGE COLUMN CANNOT BE READ: a Flow field's schema is readable and its values are "
            "returned by no read route at all, so every cell in such a column carries a "
            "visible absent-with-reason marker rather than a blank — a blank would read as an "
            "empty cell, which is a different fact. (2) A VIEW NARROWS ROWS, NEVER COLUMNS: "
            "neither read_base nor read_base_markdown takes a view id, because what a rendered "
            "table shows is the TABLE's schema in field order and a view cannot change that. "
            "What a view CAN change is which rows come back, and that is reachable one level "
            "down: search_records takes view_id and returns the rows the saved view shows. On "
            "the same call it takes filter (the field-NAME-keyed body search_filter() builds "
            "from a FilterSpec) and sort (SortKey, applied in the order given), so a subset can "
            "be asked for rather than read whole and trimmed in Python — all three are re-sent "
            "on every page of the walk. view_id does not combine with filter or sort: how a "
            "view's saved filter composes with a request one is unmeasured, and this endpoint "
            "reports success either way, so the pair is refused locally instead of guessed. "
            "None of the three shipped on a success code — records/search silently ignores body "
            "keys it does not recognise, so each was proven by comparing a narrowed read with "
            "an unnarrowed read of the same table in the same run. (3) PEOPLE ARE RENDERED "
            "NAME ONLY: a person, chat, created-by or modified-by cell renders the display "
            "name and nothing else — no address, no avatar link, no id reaches the Markdown — "
            "while the structured form keeps the raw id for a caller that can join it to a "
            "real identity. (4) A LINK IS A REFERENCE, AND A REFERENCE CAN BREAK — silently. "
            "Lark keeps one of its two link kinds intact and not the other: deleting a linked "
            "record leaves a two-way link self-healed and a one-way link still holding the id "
            "of a record that is gone, and deleting a whole link-target table leaves the "
            "source column pointing at a table that no longer exists while a record search on "
            "that source table still answers success and nothing anywhere reports an error. "
            "So the read reports what it can see for free: every link column carries what its "
            "own configuration says about the table it points at — named and live, an id "
            "whose table name has dropped out (which is what a deleted target table reads "
            "like), or cannot-determine wherever the shape answers neither way, because a "
            "confident wrong answer about whether data still exists is worse than an admitted "
            "unknown. That reading costs NO extra call, is not behind a flag, and is a "
            "reading of an observed shape rather than a promise the API makes. It is never a "
            "repair either: no dangling id is deleted and no cell is rewritten to imitate the "
            "link kind that self-heals, because rendering a broken reference honestly is the "
            "product. Two related things the server does on your behalf, disclosed here "
            "because neither is visible in the table you are looking at: creating a two-way "
            "link column also creates its mirror column in the target table, named after the "
            "source table and the source column, and writing a two-way link cell populates "
            "the reverse link over there with no write to that table at all. (5) A COMPUTED "
            "COLUMN IS A MIRROR, NOT DATA SOMEONE TYPED — and the read says so for free. Every "
            "Lookup, Formula, Stage and auto column in a table carries a provenance reading "
            "beside the rows: what kind it is, the type of value it computes (which is the "
            "TARGET field's type, never the column's own — a Lookup on a text field reports "
            "text), a Formula's expression verbatim, and, for a Lookup, the TABLE it rolls up "
            "from. Three things it deliberately does NOT report, and the reason is this "
            "library rather than Lark: which FIELD a Lookup rolls up, how it aggregates, and "
            "the formula string stored on a Lookup are returned by Lark and are not carried "
            "through by the client this library pins, so they are named unavailable instead of "
            "quietly omitted. Nothing computes a Base value here and no formula string is ever "
            "parsed, tokenized or evaluated — a computed cell shows what the server already "
            "computed. One consequence worth planning around: an aggregated Lookup's values "
            "arrive with the server's own separators inside the cell, so the rendered text "
            "joins them exactly as sent and a comma that came from the aggregation cannot "
            "afterwards be told apart from a comma inside a value. That reading costs no extra "
            "call either, and none of these columns can be written. AND ONE OPT-IN READ THAT "
            "IS NOT A LIMIT BUT A CAPABILITY: A LARK ROW TREE (sub-items) IS READABLE, AND IT "
            "IS NOT A RECORD CONCEPT. There is no parent field on a record and no hierarchy "
            "endpoint anywhere; a row tree is a LINK COLUMN POINTED AT ITS OWN TABLE plus one "
            "view property naming which column that is. So the parent edge is an ordinary link "
            "cell — which means a plain read with link resolution switched on ALREADY renders "
            "a parent-name column today — and read_hierarchy turns that column into "
            "parent/child structure in depth-first order, reconstructed here from the pointers "
            "rather than fetched: the record search this read uses is blind to the hierarchy in "
            "every direction and has no hierarchy knob, so no extra call and no second endpoint "
            "is bought. IT IS A PARENT POINTER, NEVER NESTING — no route returns children "
            "nested — and the column is NEVER GUESSED: name it, or hand over a view whose "
            "hierarchy property names it, and the answer says which. TWO STRUCTURES LARK "
            "ACCEPTS THAT NO TREE CAN CONTAIN, disclosed rather than refused because the "
            "server permits both: a row with TWO PARENTS and a row that is ITS OWN PARENT. "
            "Both parents survive into the output, every row on a cycle is typed as such and "
            "the traversal terminates, a parent that is not among the rows read is reported "
            "detached rather than promoted to a root, and a table with no hierarchy reads NOT "
            "CONFIGURED rather than as an empty tree. It costs no call, changes no default, "
            "and repairs nothing. The read is "
            "read-only end to end and paced by one shared limiter, "
            "and it costs five calls per Base: the app once, the table list once, then fields "
            "and records per table."
        ),
        object_entry_point="larkdocio.base.read.read_base",
        object_returns=(
            "a BaseRead — the app's name and time zone plus one table per Base table, each "
            "with its field specs, record ids and rendered (unescaped) cells"
        ),
        projection_entry_point="larkdocio.base.read.read_base_markdown",
        projection_returns=(
            "the Markdown projection — one heading and one GFM table per Base table, dropping "
            "the record ids and every field's schema detail"
        ),
    )


def _base_comments_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "OBJECTS ONLY, and it is the SAME comments read a document gets — a Base's "
            "comments are not part of the Base API at all: they are listed by the drive "
            "comment family, with the Base's own token as the file token and the bitable file "
            "type. So there is one comments client and one entry point, with a third accepted "
            "file type, rather than a second surface with its own transport. WHAT IT CAN TELL "
            "YOU THAT A DOCUMENT'S CANNOT: a reply carries the record, the table and the view "
            "the reviewer had open, surfaced as structured data on the thread and on every "
            "reply, with a named file-level state for a comment that names no row. The read is "
            "the whole half that works: creating, editing, resolving or deleting a Base "
            "comment is refused by the server at every granularity, and no path to it is "
            "exposed. Commenter identity is a redacted marker, never an id or an address."
        ),
        object_entry_point="larkdocio.comments.read.comments",
        object_returns=(
            "a CommentsRead — the comment objects plus the record/table/view attribution each "
            "reply carries, with authors as raw ids and an availability flag"
        ),
    )


def _base_embedded_deep_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "PROJECTION ONLY, by construction, and NOT a call site of its own: this opt-in "
            "bridge exists to inline a Base embedded in a document as Markdown tables inside "
            "that document's Markdown projection, so you reach it by turning the knob on and "
            "calling the document read — from the command line (--deep-read-bases) or in code "
            "(Parser(deep_read_bases=True, base_client=…)) — and "
            "deep_read_embedded_base is the leg that fires inside it. BOTH docx embed block "
            "types ride the one bridge and produce the same bytes for the same token. Every "
            "failure degrades to the placeholder the reader emits today, byte-identical, so a "
            "document download never fails because a Base could not be read. For a Base's "
            "data as objects, read the Base itself through the standalone read surface."
        ),
        projection_entry_point="larkdocio.read.parser.Parser.parse_docx_content",
        projection_returns=(
            "the document's Markdown projection with the referenced Base table inlined (or the "
            "placeholder, when the deep read degrades)"
        ),
    )


def _embedded_deep_read_levels() -> LevelDescriptor:
    return LevelDescriptor(
        summary=(
            "PROJECTION ONLY, by construction, and NOT a call site of its own: this opt-in "
            "bridge exists to inline an embedded sheet as a Markdown table inside a "
            "document's Markdown projection, so you reach it by turning the flag on and "
            "calling the document read — deep_read_embedded_sheet is the leg that fires "
            "inside it. There is no object-level form of this surface: for the same tab's "
            "values as objects, read the tab through the sheets-read surface instead."
        ),
        projection_entry_point="larkdocio.read.parser.Parser.parse_docx_content",
        projection_returns=(
            "the document's Markdown projection with the referenced tab inlined as a table "
            "(or the placeholder, when the deep read degrades)"
        ),
    )


