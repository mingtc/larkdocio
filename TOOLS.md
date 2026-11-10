# larkdocio Usage Schema

Primary CLI reference for AI agents interacting with the `larkdocio` **CLI** — every
command it registers: `download`, `folder`, `config`, `guide`, `mermaid` and
`roundtrip`. **Exactly one of them writes to Lark** (`roundtrip push --apply`); the
rest read. The library-only surfaces (Sheets, the Base engines, the Drive write legs)
have **no** CLI verb of their own — a sheet or a Base is read from the CLI only through
`download`'s or `folder`'s opt-in `--deep-read-sheets` / `--fidelity-read-sheets` /
`--deep-read-bases` flags; see § Overview for where their contracts live.

**DO NOT deep-dive into the Python source (`src/larkdocio/…`) unless you are
actively debugging a crash or implementing a feature.** Use this document as the
schema.

## Overview

`larkdocio` is a Lark (Feishu) document, spreadsheet and Base library. **The list below
enumerates what the CLI reaches, plus the library surfaces this document has to point at —
never the whole library.** `larkdocio.capabilities()` is the complete, generated census
(it reports the Base read and write engines, the contacts lookup and the Drive write legs,
none of which the command line can reach); read it there rather than counting here — **no
count of them is typed in this file on purpose**, because a number retyped here is stale the
moment the next leg lands, which is exactly how this sentence came to say *three* after a
fourth shipped.

1. **The docx reader** — converts `docx`/`wiki` documents to Markdown, pulling
   images and flowchart/mindmap PNGs into a local `static/` folder. This is what
   the `download` command drives, and it is most of what this document covers.
2. **The Sheets surface** — reading spreadsheets, plus a gated write surface
   (values, rich/structural, dimension and presentation ops). Contract:
   [`SHEETS.md`](SHEETS.md).
3. **The gated docx write/apply engine** — a `plan → dry-run → apply` engine you
   approve a plan through before anything is written. **Of the commands this
   document covers, exactly one of them writes**: `roundtrip`, and it writes only
   under `push --apply` (the shipped guide carries the same sentence, so the two
   documents cannot drift apart on this fact). The warning the older wording carried
   still stands, narrowed to what is true: **no other CLI command mutates a
   document**, no reading verb has a write flag, and every other entry point into
   this engine is a library call with no CLI route — **a download must never be able
   to mutate the document it is reading.** See § CLI Commands § `roundtrip`.
4. **`larkdocio.mermaid`** — a pure spec→Mermaid-source compiler, exposed as the
   `mermaid` command below.
5. **The Drive folder read** — hand one folder link and it enumerates the tree
   and reads every document inside, as one Markdown document plus a structured
   result. This is what the `folder` command drives, and **that command is
   read-only**: the walk moves, uploads and writes nothing. The Drive *package*
   is not — named-version writes, access grants, file writes (upload single-shot
   or chunked, download, delete) and folder creation ship beside the walk,
   reachable only as library calls. The per-verb census is
   `larkdocio.capabilities()`; the contract is [`DRIVE.md`](DRIVE.md).

**Scope note for agents: this document is the schema for the CLI only.** Surface 2
is a library API with no Sheets verb — it is read from the CLI only through `download`'s
or `folder`'s opt-in flags (below) — and surface 3 has no CLI equivalent apart from `roundtrip`
(above) — for those, run
`larkdocio guide` (or call `larkdocio.guide()`), which is the packaged, shipped
contract with runnable recipes, the capability matrix, and the permissions table.

## Authentication

Set credentials in the environment or a `.env` (loaded from the current
directory, or passed via `--env-file`). Resolution order:

1. `LARK_READ_APP_ID` + `LARK_READ_APP_SECRET` (both required), else
2. legacy `LARK_APP_ID` + `LARK_APP_SECRET`, else
3. **`LarkConfigError` is raised** — resolution is pair-wise, so no complete pair means a
   typed refusal naming the pair *in force*, not an empty pair handed back silently.

`LARK_WRITE_APP_ID` / `LARK_WRITE_APP_SECRET` are used only by the write surfaces and
are never used by the read path.

- Optional: `LARK_DISABLE_IPV4_PIN` — the CLI pins DNS to **IPv4 only** before
  contacting the Lark API (Lark's allowlist is IPv4-only; an IPv6-resolved host
  is rejected). On by default; set it — **in your `.env`** or the shell
  environment — to `1`/`true`/`yes` to restore stock resolution. The knob is read
  after the `.env` is loaded, so a value in `.env` is honored (not only a shell
  export).

## Execution

Installed as a console command — **no working-directory constraint** and no
`python main.py`. Run it from anywhere the venv is active (or by absolute path
to the venv's `bin/larkdocio`):

```bash
larkdocio [GLOBAL OPTIONS] download <LARK_DOC_URL> [OPTIONS]
# or, without activating the venv:
/path/to/.venv/bin/larkdocio [GLOBAL OPTIONS] download <URL> [OPTIONS]
```

## CLI Commands

### 1. `download` (Lark → Markdown)

Extracts a Lark document into a structured Markdown file.

`<LARK_DOC_URL>` must be a **full Lark document URL** — `https://…/docx/…` or
`https://…/wiki/…` (a wiki node that resolves to a `docx`). A legacy `https://…/docs/…` URL
is recognised but refused ("lark Docs is no longer supported"): pass the document's `/docx/`
URL instead. A bare document token is **not** accepted: `validate_download_url` requires the
`https://` URL form and raises `ValueError` otherwise.

```bash
larkdocio [GLOBAL OPTIONS] download <LARK_DOC_URL> [OPTIONS]
```

**Global options** (must come *before* the `download` subcommand):
- `--version` — print the installed larkdocio version and exit.
- `--config` — path to a `config.json` file (output-formatting options). Defaults
  to the built-in package config; see [Output configuration](#output-configuration-configjson).
  `download` and `config` read it; `folder` does not.
- `--env-file` — path to the `.env` file containing Lark credentials.

**`download` options:**
- `-o, --output` — output directory path. Defaults to `./`.
- `--allowHost` — additional allowed host for the OPEN API (when validating the URL).
- `--dump` — flag; additionally writes `<token>.json` with the raw Lark API payload,
  beside the Markdown in the directory the output landed in. It also carries the
  filename-stamp basis, `unfetched_references`, and a `route` record of the routing
  decision (`routed` and `reason`; `derivation_ran` is always `false` and `labels_found` /
  `labels_missing` are always empty, kept so a reader of the record does not break).
  **No path appears in it** — two dumps of one unchanged document are byte-identical, so
  the output path is reported on the download's return value instead.
- `--route <subpath>` — place the output under this subpath beneath `-o`; each segment is
  sanitised but never lower-cased, and an absolute path, a `..` segment or an empty segment is
  refused.
- `--local-time` — stamp the output filename in the machine's local clock instead of UTC (the
  default). The shape is unchanged; the same document downloaded at the same instant on two
  machines in different zones then lands under different names.
- `--deep-read-sheets` — opt in to reading an embedded sheet (block type 30) into an inline
  Markdown table. Off by default: no Sheets call is made and the sheet stays a placeholder; a
  read that fails degrades to the placeholder.
- `--fidelity-read-sheets` — opt in to a sheet's whole-cell bold/italic and its background
  fills, through a READ-credential xlsx export. For an embedded sheet it also needs
  `--deep-read-sheets`; for a folder's standalone spreadsheet it is enough on its own. An
  export that fails degrades to the values-only table.
- `--deep-read-bases` — opt in to reading a Base embedded in the document into inline Markdown
  tables (the referenced table only). Off by default: no Base call is made; every failure
  degrades to the placeholder.

**Example:**
```bash
larkdocio --env-file /absolute/path/.env download https://your-domain.larksuite.com/wiki/ABC... -o /absolute/path
```

**Capabilities:**
- Reads Text, Headings, Tables, Lists, code, quotes, callouts, equations, etc.
- Downloads internal images into a `static/` subfolder next to the output Markdown.
- Extracts Type 40 Mermaid diagrams directly into fenced code blocks.
- **Type 21 (Flowcharts) and Type 29 (Mindmaps) arrive as Type 43 and are
  downloaded as high-resolution PNGs** and embedded as standard image links.
- Writes into `-o` exactly as given — the library derives no destination from a
  document's own contents. `--route <subpath>` is the one way to place the output
  under a subpath, and it is the CALLER's path (do not pre-build it into `-o` as
  well — it double-nests).
- **File attachments** (type-23) surface as a `📎` name+token marker; the binary
  is **not** fetched by default. Opt in to best-effort binary download with the
  `download_attachments` config key (default `false`, LD-040) — see
  [Output configuration](#output-configuration-configjson).
- **@mention display-name resolution:** at download time an `@ou_id` mention is
  resolved to `@Name` via the contacts batch API (`resolve_mentions` config key,
  **default `true`**, LD-053). Missing the contacts scope → the whole run
  **gracefully degrades to the raw `@ou_id`** after one info log (never errors);
  see [Authentication](#authentication).
- **Bare-URL auto-linkify** — a bare URL in text is rendered as a Markdown link,
  **always on** (no knob, LD-054).

> **Full block-type support matrix:** see [`BLOCKS.md`](BLOCKS.md) — the single source of
> truth for how the reader treats every block type. (Handler-**authoring** mechanics live
> in [`src/larkdocio/blocks/BLOCK_TYPES.md`](src/larkdocio/blocks/BLOCK_TYPES.md), which
> deliberately carries no status table.)
> If a download logs `Unknown block type N`, that type has no handler and its
> content was dropped — check the matrix.

### 2. `folder` (Lark folder → Markdown)

Reads a whole Drive **folder**: enumerates the tree, reads every document inside
(at any depth), and writes **one** Markdown document — a tree index, then each
document under its own heading, then a disclosure of what could not be read —
into the output directory.

`<LARK_FOLDER_URL>` must be a **full Lark folder URL** — `https://…/drive/folder/…`.
Hand a folder URL to `download` and it refuses and points here; hand a document
URL to `folder` and the URL validator refuses it as not a folder. The two verbs
do not overlap: `download` writes one document plus its images, `folder` writes
the whole tree as one file.

```bash
larkdocio [GLOBAL OPTIONS] folder <LARK_FOLDER_URL> [OPTIONS]
```

**`folder` options:**
- `-o, --output` — output directory (a directory, always). Defaults to `./`. The
  file is named for the folder; the library itself writes no files for a folder
  read — this on-disk shape is the CLI's.
- `--dump` — **also** write the machine-readable child manifest, `<folder
  token>.json`, into the same `-o` directory (the naming and placement `download
  --dump` already uses). One flat row per walked child carrying its **title,
  token, type and revision**, plus the listing's `created_time` /
  `modified_time` / `owner_id` / `url`, the read-or-disclosed outcome, and the
  walk's truncations, cycles and refusals — so a truncated walk cannot read as a
  complete folder. Purely additive: the Markdown is byte-identical either way. A
  revision is reported only where the read already carried one and is marked
  **unavailable with the reason** everywhere else; no extra API call is made for
  it, and every row carries `modified_time` regardless. The per-type table is in
  [`DRIVE.md`](DRIVE.md) and ships inside the sidecar as `revision_sources`.
- `--assets` — **also** fetch every document's images and its flowchart / mindmap PNGs into
  one shared pool, `<-o>/static/<asset token>.<ext>`, and relink each reference to it. Off by
  default (no asset call is made). An asset that fails is disclosed in an `## Assets not
  fetched` section and never fails the walk; attachments are not included.
- `--deep-read-sheets`, `--fidelity-read-sheets`, `--deep-read-bases` — the same opt-ins as on
  `download`, applied to every document the walk reads (`--fidelity-read-sheets` also governs a
  standalone spreadsheet child).

**Read-only.** It reads on the READ credentials and never writes, moves, uploads
or deletes anything in Lark. A child it cannot read — a raw uploaded file, an
unreadable document — is **disclosed by name** in the output, never silently
dropped, and never fails the rest of the walk. Reading the documents inside uses
the same docx / Sheets / Base read surfaces the library already ships. Contract:
[`DRIVE.md`](DRIVE.md); the library entry point is `larkdocio.drive.read_folder`.

**Example:**
```bash
larkdocio --env-file /absolute/path/.env folder https://your-domain.larksuite.com/drive/folder/ABC... -o /absolute/path
```

### 3. `config`

Reads the effective config (and, when `--appId`/`--appSecret` are given, writes
the preferred read names `LARK_READ_APP_ID` / `LARK_READ_APP_SECRET` into the
`.env` — or updates the legacy pair in place, with a notice, on a `.env` that
already uses it; it never re-keys an existing credential file, and never writes
the separate `LARK_WRITE_APP_*` pair):

```bash
larkdocio config --appId YOUR_APP_ID --appSecret YOUR_APP_SECRET
```

### 4. `guide` (print the packaged consumer guide)

Prints the packaged consumer guide's **section index** to stdout — the same text
`larkdocio.guide()` returns: every section named after the failure it cures, with
the call that fetches it. `--full` prints the whole document instead — recipes that
run as pasted, the capability matrix, the READ / WRITE credential split, and the
generated permissions table. It is read out of the **installed package**, so it needs
**no network, no credentials and no source tree**.

The bytes are the document's own — no pager, no colorization, no reflow and no
added trailing newline — so piping it to a file or into another program is
exactly what it is for. **This is the command to reach for when you need a
surface `TOOLS.md` does not cover** (the Sheets surface, the gated write/apply
engine).

```bash
larkdocio guide                  # the index: what sections there are, and how to ask
larkdocio guide --section recipes              # just one part of it
larkdocio guide --full > GUIDE.md              # the whole document, kept
```

Two options, `--section <name>` and `--full`, and no arguments; they cannot be
combined. Name a section by its heading exactly as it appears or by the slug
derived from it (both case-insensitive); what comes back is that section's own
bytes, and a top-level name includes the subsections nested under it. Omit both
and the index prints; pass `--full` and the whole guide prints. An unrecognised
name prints **nothing** on stdout — it refuses on stderr with a non-zero exit
status, listing every section there is, so a redirect is never left half-written.

### 5. `mermaid` (diagram spec JSON → Mermaid source)

Compiles a structured diagram spec to Lark-safe Mermaid source: a spec in, source
out.

**This is PURE:** no credentials, no network, no document is touched, and nothing
leaves the machine. It compiles text and stops — **it never writes a diagram into
a Lark document.** Putting a compiled diagram into a document is a library call
whose plan you approve first; `larkdocio guide` has that recipe.

| Argument / option | Meaning |
| --- | --- |
| `[SPEC]` | Path to a JSON spec file, or `-` (**the default**) to read the spec from stdin. |
| `--flowchart` | State that the spec is a flowchart. |
| `--sequence` | State that the spec is a sequence diagram. |
| `-o`, `--output FILE` | Write the source into this **file** instead of stdout. (Unlike `download`'s `-o`, which is a *root directory* output is written under.) Nothing is written when the spec is refused, so a refusal never leaves a half-finished diagram behind. |

**The diagram kind is stated, never guessed.** Pass `--flowchart` or
`--sequence`, or give the spec a `"kind"` key spelling one of them. Stating
neither **refuses**, and a flag that contradicts the key **refuses** rather than
picking a winner. Which keys a spec happens to carry is never consulted.

**Refusals are loud, not silently corrected.** A spec the renderer could not draw
refuses: the message names the construct and its value, goes to **stderr**, exits
**non-zero**, and leaves **stdout empty** with no output file written. Advisory
warnings about a valid diagram (its size, a wide horizontal layout) also go to
stderr, so stdout carries only diagram source and redirecting it is safe.

```bash
larkdocio mermaid --flowchart spec.json > diagram.mmd
cat spec.json | larkdocio mermaid --sequence -
```

### 6. `roundtrip` (edit a document as a Markdown file — **the one verb that writes**)

**THIS IS THE ONE SUBCOMMAND THAT WRITES TO LARK, and the only docx edit route this
document covers — the targeted and sub-span edits are library calls with no
command-line route, taught in the packaged guide's § "Which write recipe do you
need?". It re-writes every block your edited file changed as one run carrying the
styling that block starts with, so a colour that differed elsewhere in the paragraph
is flattened onto that, and bold, italics or a link inside one refuses the push. It
writes only under
`push --apply`.** `PHASE` is `pull` or `push` — two invocations of one verb, because
your edit happens *between* them, possibly in another process or tomorrow.

```bash
larkdocio --env-file .env roundtrip pull "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./edit/
# ...you (or your agent) edit ./edit/document.md — keep every marker where it is...
larkdocio --env-file .env roundtrip push -o ./edit/            # preview only, writes NOTHING
larkdocio --env-file .env roundtrip push -o ./edit/ --apply    # applies THAT plan, then verifies
```

| Argument / option | Meaning |
| --- | --- |
| `PHASE` | `pull` or `push`. Required. |
| `[URL]` | The document URL. Required by `pull`; `push` takes none. |
| `-o`, `--workdir DIR` | The **directory** (default `./`) holding the two files the phases pass between them. Both phases must be given the **same** directory. |
| `--apply` | On `push` only: apply the plan that was just previewed. **It does not skip the preview.** |

`pull` reads on the **READ** credentials and writes **two files** into `-o`:
`document.snapshot`, which is **ours and immutable** (the read, checksummed, carrying
the revision and the tenant domain), and `document.md`, which is **yours and
editable**. Every block in `document.md` carries an identity marker comment; keeping
each marker where it is is what makes this an **update** rather than a re-authoring.
Change the text under a marker; never move a marker onto another block's text.

`push` loads the snapshot, reconciles your edited `document.md` against it, and
**always builds and prints the plan first**. **There is no flag that skips the
preview** — `--apply` means *apply the plan you just previewed*, and the write goes
only through that plan. The plan carries the revision the snapshot recorded, which
arms the whole-document compare-and-swap: if the document changed while your edit sat
on disk the batch is **refused whole, with zero writes**, and the fix is to pull again
and re-apply your edit. A snapshot that carried no revision cannot arm it, and the
command says so loudly instead of writing as if it had. After a successful apply it
**re-reads the document and verifies it by compose-equivalence** — what the document
now means, against what you authored — and a block outside the authoring dialect is
reported **unverifiable by name**, never quietly counted as clean.

**Credentials.** `pull` uses the READ pair. `push` is the **first and only place this
command line consults the WRITE pair** (`LARK_WRITE_APP_ID` / `LARK_WRITE_APP_SECRET`)
and it also needs the READ pair for the read-back. The two pairs are separate credentials
(one app or two; two recommended), resolved separately and never borrowed for one another; a `push` with no WRITE pair
refuses before any call, naming both variables.

Every refusal is typed, says what to do next, and names the guide section covering the
recovery. **Nothing is half-written: a refused push writes nothing at all.**

## Output configuration (`config.json`)

The global `--config` option points at a JSON file whose `output` object tunes
Markdown rendering and download behavior. Omit `--config` to use the built-in
package defaults (`src/larkdocio/config.json`). The full schema is the
`OutputConfig` fields (`src/larkdocio/read/config.py`), generated from that dataclass:

<!-- BEGIN CONFIG-SCHEMA (generated
     regenerate with:  python -c "from larkdocio.capabilities import config_schema_markdown as m; print(m())"  -->

| Key | Default | What it does |
|-----|---------|--------------|
| `image_dir` | `"static"` | Subfolder, created next to the output Markdown, that downloaded images and the flowchart / mindmap PNGs are written into. Image links in the Markdown are rewritten to point at it relatively. |
| `title_as_filename` | `true` | Name the output file after the document's own title, prefixed with a UTC `[YYYY-MM-DD_HHMM]_` stamp — so two downloads of the same document produce two files rather than overwriting one. When `false` the name is `<document token>.md` with no stamp at all, which is how to get a stable, repeatable filename. |
| `use_html_tags` | `false` | Emit HTML tags for the inline styles Markdown cannot express (`<u>` for underline). When `false` only Markdown-native styling is emitted and those styles are dropped. |
| `skip_img_download` | `false` | Leave image tokens unresolved: no network fetch, nothing written into the assets subfolder, and image links are not localized. |
| `download_attachments` | `false` | Opt in to best-effort binary download of file attachments. Default `false`: an attachment surfaces as its name+token marker and no attachment network happens at all. When `true` each queued file token is fetched into `image_dir` alongside the images, warning and continuing past a failure. |
| `resolve_mentions` | `true` | Resolve @mention open ids to display names at download time (`@ou_id` -> `@Name`) through the contacts batch call. A missing contacts scope, an id the directory does not cover, or a failing lookup keeps the raw `@ou_id` after one log line and never fails the read. When `false` resolution is skipped entirely and the contacts surface is never touched. |

The whole file, every key at its default — which is exactly what the package ships as `larkdocio/config.json`, so omitting `--config` and passing this file are the same run:

```json
{
  "output": {
    "image_dir": "static",
    "title_as_filename": true,
    "use_html_tags": false,
    "skip_img_download": false,
    "download_attachments": false,
    "resolve_mentions": true
  }
}
```

Any subset is valid: a key you leave out keeps the default above, and a key the library does not know is ignored.

<!-- END CONFIG-SCHEMA -->

The **shipped consumer guide** carries this same generated region — a consumer on a
vendored wheel reads it with `larkdocio guide` or `larkdocio.guide()`, under
*Output configuration*. This file is the repo-side CLI contract; neither copy is hand-kept.

## Common failure modes

- **`No such option: --env-file`** → the global flag was placed *after*
  `download`; move it before the subcommand.
- **Auth / credential error** → the `.env` Lark keys are missing or wrong. With **no complete
  read pair** it is a typed `LarkConfigError` whose message names the pair the read path is
  resolving **right now** (the legacy pair on a clone with nothing set) and echoes no
  credential value — edit the pair it names, not the other one.
- **Double-nested output path** → a full area/section/topic path was passed
  to `-o`; pass only the base output dir.
