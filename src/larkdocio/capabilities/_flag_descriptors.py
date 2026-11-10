"""The opt-in flags — the first half of the static-descriptor region.

A flag's prose names the scope its behaviour needs; the scope itself is owned by the
permission registry (``larkdocio.permissions``, which ``capabilities()`` projects) and is
never asserted here.

LD-244: the verbatim pre-split slice, lines 1577-1657 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
from ._models import Flag

# --------------------------------------------------------------------------- #
# The static descriptors — flags + safety contracts (truthful against the       #
# shipped CLI / engine; drift-guarded by the test).                            #
# --------------------------------------------------------------------------- #

def _flags() -> dict:
    return {
        "deep_read_sheets": Flag(
            id="deep_read_sheets",
            cli="--deep-read-sheets",   # on `download` and on `folder`
            default=False,
            mode="cli",
            requires=[],
            summary=(
                "Opt in to deep-reading docx embedded sheets (block type 30) into inline "
                "Markdown tables. Carried by BOTH read verbs — download and folder — with one "
                "spelling, one default and one meaning. Off by default: NO Sheets API calls; a "
                "failed read degrades to the placeholder and never fails the read."
            ),
        ),
        "fidelity_read_sheets": Flag(
            id="fidelity_read_sheets",
            cli="--fidelity-read-sheets",
            default=False,
            mode="cli",
            # The prerequisite is PER LEG, not per flag (LD-385), so it cannot be stated
            # here as one hard edge: the docx EMBEDDED-sheet leg needs --deep-read-sheets
            # (without it there is no deep read to add fidelity to), while a folder's
            # SPREADSHEET child is read by the Sheets surface either way and needs nothing
            # else. Declaring the embedded leg's prerequisite for both would say this flag
            # does nothing on its own — which, since LD-385, is false for the leg a
            # colour-encoded workbook actually travels.
            requires=[],
            summary=(
                "Opt in to reading a sheet's whole-cell (format-level) "
                "bold/italic AND its per-cell background fills — the style set on the CELL, "
                "which the values API does not carry — via a READ-creds xlsx export. Bold "
                "and italic render as MD emphasis; a fill has no Markdown equivalent, so "
                "each tab's fills are disclosed in a note above its table (the ARGB against "
                "the cells carrying it), which is what makes a colour-encoded sheet "
                "readable rather than silently empty. Carried by BOTH read verbs (download "
                "and folder), and it governs TWO legs whose prerequisites differ: the docx "
                "EMBEDDED-sheet leg, which needs --deep-read-sheets, and a folder's "
                "STANDALONE SPREADSHEET child, which needs nothing else because that child "
                "is read through the Sheets surface either way — which is the leg a workbook "
                "whose meaning IS its cell colours travels, its cells otherwise blank. "
                "Run-level "
                "emphasis (bold/italic on a text run inside a cell) travels in the values "
                "API's own segmentStyle and is ALREADY rendered without this flag, so on a "
                "sheet whose emphasis is run-level this leg correctly adds nothing — "
                "expected, not broken. A failed export degrades to values-only and SAYS so "
                "per tab: an unread fill layer is not an absent one."
            ),
        ),
        "deep_read_bases": Flag(
            id="deep_read_bases",
            cli="--deep-read-bases",
            default=False,
            mode="cli",
            requires=[],
            summary=(
                "Opt in to deep-reading a Base embedded in a document (both embed block "
                "types) into inline Markdown tables. Reachable from the command line "
                "(--deep-read-bases, on download AND folder) AND in code (Parser("
                "deep_read_bases=True, "
                "base_client=…)) — the deep read still needs a Base read client, which the "
                "command builds from the READ credentials the way --deep-read-sheets builds "
                "its own. Off by default: NO Base API calls are made and the reader emits "
                "exactly the placeholder it always has. Every failure degrades to that same "
                "placeholder, byte-identical, so a read never fails because a Base could not "
                "be read."
            ),
        ),
        "folder_assets": Flag(
            id="folder_assets",
            cli="--assets",   # on `folder` only — see the summary for why
            default=False,
            mode="cli",
            requires=[],
            summary=(
                "Opt in to fetching a WHOLE FOLDER's binaries: every walked document's images "
                "and its flowchart / mindmap (whiteboard) PNGs. THE FLAG A MINDMAP-ONLY "
                "DOCUMENT NEEDS — a document whose entire content is a diagram otherwise comes "
                "back from a folder walk as a bare token and nothing else, technically read and "
                "semantically empty. Carried by `folder` ONLY, and deliberately not a second "
                "spelling of a download flag, because download has none: download's asset "
                "handling is UNCONDITIONAL and config-gated (output.skip_img_download, default "
                "off), so a single document's assets are always fetched. What IS shared is the "
                "on-disk vocabulary — the same directory name (output.image_dir, `static`), the "
                "same token-derived filenames, the same relative-link rewrite. THE LAYOUT IS "
                "ONE SHARED FLAT POOL beside the one Markdown document a folder read produces: "
                "<-o>/static/<asset token>.<ext>. COLLISIONS ARE IMPOSSIBLE BY CONSTRUCTION — "
                "the filename IS the Lark asset token and a token is globally unique, so two "
                "different assets cannot produce one filename; the same token referenced by two "
                "documents is the SAME asset and is fetched ONCE for the whole walk, with every "
                "reference relinked. (Per-document subdirectories were rejected for the "
                "opposite reason: they would be named from a document TITLE, and two documents "
                "in one folder may legitimately share one.) OFF BY DEFAULT because a folder's "
                "binaries are a different cost class from one document's, and off is inert: no "
                "asset call, no credential resolved, no client built, no pool directory "
                "created, and Markdown byte-identical to a walk without it. NO NEW API REACH — "
                "the same media download and whiteboard PNG export the docx reader already "
                "makes, from a second caller, so no permission row moves. A per-asset failure "
                "SKIPS LOUDLY: Lark's own code and msg, naming the document and the asset, in "
                "the log and in an `## Assets not fetched` section, and the remaining documents "
                "are still fetched. Attachments (uploaded file blocks) are NOT in this set — "
                "they are download's own separate config opt-in. Nothing is re-encoded, resized "
                "or converted; the bytes land as Lark served them."
            ),
        ),
        "resolve_base_links": Flag(
            id="resolve_base_links",
            cli="larkdocio.base.read_base(url, resolve_links=True)",
            default=False,
            mode="config",
            requires=[],
            summary=(
                "Opt in to following a Base link cell to its target: each linked record "
                "renders as its TARGET TABLE'S SCHEMA-DESIGNATED PRIMARY FIELD (is_primary, "
                "read from that table's own field list) instead of as a bare record id. A "
                "READ ARGUMENT, NOT A COMMAND-LINE FLAG — no subcommand ships a switch for "
                "it, and the Base surface is not reachable from the command line at "
                "all. OFF by default, and off is BYTE-IDENTICAL: no extra "
                "API call is made and a link cell renders exactly the ids it always did. "
                "SWITCHED ON IT COSTS READS, and the cost is DISCLOSED on the result "
                "(read_base(...).link_resolution says how many extra calls were made and "
                "which target tables were touched): every id wanted from one target table is "
                "fetched in ONE batched records/batch_get, deduplicated across cells and rows "
                "and chunked, so the call count follows the number of TARGET TABLES and never "
                "the number of cells. A LINK WHOSE TARGET RECORD WAS DELETED IS A NORMAL "
                "CASE, not an error — Lark maintains referential integrity for the symmetric "
                "link kind and not for the one-way one — so it never fails a read: the "
                "per-cell answer is typed resolved / dangling / unresolvable and the last of "
                "those claims nothing in either direction. Determinism is SAME-RUN: a second "
                "table is read, so a target record renamed between runs legitimately changes "
                "the output."
            ),
        ),
        "retain_base_raw_values": Flag(
            id="retain_base_raw_values",
            cli="larkdocio.base.read_base(url, retain_raw=True)",
            default=False,
            mode="config",
            requires=[],
            summary=(
                "Opt in to keeping the RAW WIRE VALUE of every Base cell beside the rendered "
                "one. Every value a Base read otherwise returns is DISPLAY-SHAPED — a Date "
                "arrives as an epoch and leaves as 2025/07/01, an Email leaves as a "
                "[text](mailto:…) link, a Person leaves as a comma-joined display name — "
                "which is right for reading and wrong for comparing, so a consumer who wants "
                "to dedupe, diff or chart has to re-derive the values themselves. A READ "
                "ARGUMENT, NOT A COMMAND-LINE FLAG — no subcommand ships a switch for it, "
                "and the Base surface is not reachable from the command line at all. "
                "OFF by default, and off is BYTE-IDENTICAL: the rendered "
                "output does not move, and NOTHING is retained. RAW MEANS THE WIRE SHAPE "
                "EXACTLY AS LARK RETURNED IT — no key renamed, no absence coerced, no epoch "
                "turned into a string, no list flattened or sorted, no type changed — and it "
                "is deliberately NOT a normalized typed middle form: there is no datetime, no "
                "Decimal, no person class and no per-type converter anywhere behind it, "
                "because a third value vocabulary after the wire's and the renderer's is one "
                "this library would have to define, defend and version for every type. It is "
                "evidence, not a model. ZERO EXTRA API CALLS in either mode — the payload is "
                "already received and the flag only decides whether it is kept — BUT IT COSTS "
                "MEMORY, measured rather than hand-waved: ≈7× the rendered cells (≈260 KB "
                "against ≈38 KB on a 64-row read of a real four-column table), because a "
                "Lookup or Person cell that renders as a short name arrives as a nested "
                "structure. Reached as read_base(...).tables[i].rows[j].raw_fields, and "
                "through snapshot_table into SnapshotRecord.raw(field_name) / raw_as_dict(); "
                "with retention off both refuse, typed, rather than returning an empty dict "
                "that would read as 'the cells were empty'."
            ),
        ),
        "resolve_mentions": Flag(
            id="resolve_mentions",
            cli="read Config(OutputConfig(resolve_mentions=…)) / config.json output.resolve_mentions",
            default=True,
            mode="config",
            requires=[],
            summary=(
                "Resolve @mention open ids to display names in a document's Markdown "
                "projection (@ou_id -> @Name) via the contacts batch call "
                "batch_get_user_names. ON by default — the one switch here that is opt-OUT — "
                "and it applies to BOTH read paths: the download command does it "
                "automatically, and an in-process read does it when the parser is handed the "
                "read client (Parser(config, read_client=client)); a parser with no client "
                "renders the raw @ou_id, which is what a documented read used to do while the "
                "command resolved. TWO PRECONDITIONS, both settings on your own app in the "
                "Lark console rather than anything the library can request: the app must carry "
                "the field-level contacts scope contact:user.base:readonly (without it the "
                "directory answers but every name field comes back null), AND the app's "
                "contacts data range must cover the mentioned users (out of range they do not "
                "come back at all). Miss either one and every id stays raw. GRACEFUL DEGRADE: "
                "an unresolvable id, a missing scope, or a failing lookup keeps the raw "
                "@ou_id after one log line — mention resolution never fails a read. THAT LINE "
                "SAYS WHICH WAY IT FELL SHORT: users returned with no readable name (the "
                "field-scope signature) and ids that never came back (the data range) are "
                "reported as different things, once per read, because the two used to be "
                "indistinguishable and each points at a different fix. Set it "
                "False to skip resolution entirely (the contacts surface is never touched)."
            ),
        ),
        "verify_style": Flag(
            id="verify_style",
            cli="--verify-style",
            default=False,
            mode="engine",
            auto_on=True,
            requires=[],
            summary=(
                "The write-gate style/format fidelity leg (export-based diff). AUTO-ON for a "
                "style / number-format / merge / structure write; a plain value write stays "
                "export-free. Engine trigger (larkdocio.sheets.requests.effective_verify_style / "
                "requires_style_leg), not a download flag."
            ),
        ),
    }

