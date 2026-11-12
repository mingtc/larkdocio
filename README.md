# larkdocio

A Python toolkit for Lark (Feishu) **documents, spreadsheets and bases** — point it at what your team
already writes in Lark and it hands you clean Markdown; where you ask, it makes careful, reviewable
edits. `larkdocio.capabilities()` names every surface that ships: the **reader** (a `docx`/`wiki`
document → clean Markdown, images and flowchart / mindmap PNGs pulled locally), the **writer** (a
plan-gated, block-level apply-engine plus Markdown authoring), **sheets** (values → Markdown plus a
plan-gated write engine), **comments** (the review conversation, resolved onto the blocks each is
anchored to; a whole-document comment is created or removed through the writer's plan), **contacts** (a display name or an email → exactly one `open_id`, or a typed refusal
saying why), **base** — a Base (bitable) → titled Markdown tables
(`larkdocio.base.read_base_markdown`), its comments attributed to the record a reviewer had open, an
opt-in embedded-Base bridge, **and** plan-gated record and schema writes — and **drive**: a folder
**read** (one folder link → the tree, read), *plus four direct-call writes* — a document's named
**versions**, who has **access** to it, a file uploaded into a folder (`drive-files-write`), and
**folders** you create (`drive-folders-write`) — what each one verifies, if anything, stated per leg in that leg's `safety_contracts`.

## Start here — pick your path

Three roles read this file — **consumer** (use it in your project), **vendor-integrator** (vendor
and re-pin the wheel), **developer** (work on larkdocio itself). Take yours, skip the rest — this
repository is where larkdocio is **published** (tags `vX.Y.Z`, the wheel on `dist`), and a
consumer never needs to read or build its source. One prerequisite for everyone: **a Lark application** (credentials + scopes + sharing);
[LARK_SETUP.md](src/larkdocio/LARK_SETUP.md) is the ten-minute walkthrough — it ships in the wheel, so `larkdocio.lark_setup()` returns it ([Requirements](#requirements) has the summary).

### Consumer — use larkdocio in your project

**Step 0 gets you the wheel** from the `dist` branch: no build, no credential, no nested `.git`.

```bash
git clone --branch dist --depth 1 https://github.com/mingtc/larkdocio.git /tmp/ld-dist && mkdir -p vendor && cp /tmp/ld-dist/larkdocio-*.whl vendor/  # 0. wheel → ./vendor/
scripts/update_larkdocio.sh                                # …or build from the tag, once onboarding (below) has copied the script in
pip install ./vendor/larkdocio-*-py3-none-any.whl          # 1. install what step 0 dropped
```

```python
import larkdocio                      # then read the manual the wheel carries — no
                                      # credentials, no network, no source-reading:
print(larkdocio.guide())              # the INDEX: one row per section, each named after the
                                      # failure it cures, and the call that fetches it.
                                      # No count is quoted — len(guide_sections()) is it
print(larkdocio.guide("install-vendored-wheel-the-locked-distribution-model"))
                                      # …then one section, by the name the index gave you
```

**The TAG is authoritative when `dist` lags** — `dist` carries only the current release and is
replaced on each cut, so if its wheel's version is not the tag you want, build from the tag.

Step 0's script is copied into your repo once, by the onboarding walkthrough under
[Consuming larkdocio](#consuming-larkdocio) — that walkthrough is the only part below this
router you need. Then the [Quickstart](#quickstart--six-steps-from-an-installed-wheel) adds
credentials and runs one real read and one real write.

### Vendor-integrator — vendor and re-pin the wheel

The refresh loop is always deliberate: nothing here ever auto-updates.

```bash
scripts/update_larkdocio.sh            # build + vendor the latest tag
scripts/update_larkdocio.sh vX.Y.Z     # …or one specific tag
scripts/update_larkdocio.sh --check    # report-only: is a newer tag available?
```

Re-pin the requirement line it prints, then re-install. **Before you re-pin, read what
changed:** `larkdocio.release_notes()` is the consumer-filtered view (public symbols,
observable behavior changes, every dependency pin move, known limitations) and
`larkdocio.changelog()` is the project's changelog beside it. Both read straight from the
installed wheel, which carries a window of the newest releases, so for a re-pin inside that
window you need no copy beside it — and a refresh also drops
`larkdocio-RELEASE_NOTES.md` into `./vendor/` for convenience. The
[full walkthrough](#consuming-larkdocio) covers onboarding and the optional update nag.

### Developer — work on larkdocio itself

Everything is under [Developing larkdocio](#developing-larkdocio) at the foot of this page:
the clone quickstart, the package layout, the capability matrices, the test rings and
the consumer-onboarding scripts. None of it is needed to *use* the library.

## Quickstart — six steps from an installed wheel

**Step 4 is the one that matters.** The wheel carries its own guide, and
`larkdocio.guide()` opens it: the capability matrix, a copy-paste recipe for every read
and write handshake, and the safety contracts. No clone, no network call, no source-reading.
**With no argument you get the index** — every section named after the failure it cures, with
the call that fetches it — so you read a page of names and then ask for the one section
you need.
`larkdocio.guide(full=True)` still returns the whole document, byte for byte.

```bash
pip install ./vendor/larkdocio-*-py3-none-any.whl    # 1. install what step 0 dropped
printf 'LARK_READ_APP_ID=cli_a1b2\nLARK_READ_APP_SECRET=s3cr3t\n' > .env  # 2. credentials
```

```python
import larkdocio
from larkdocio.common import init_env

init_env(".env")                     # 3. load that .env — nothing sees your credentials first
print(larkdocio.guide())             # 4. …then read THIS: the shipped guide's index
```

Then one read. Every block below runs on its own — paste it into a file, swap the URL for
yours, and it works as written:

```python
from larkdocio.common import get_read_credentials, init_env, validate_download_url
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, token = validate_download_url(url)  # 5. one read: url → domain, type, token
client = Client(*get_read_credentials(), domain)      # `domain` is the API domain
_meta, blocks = client.get_docx_content(token)
markdown = Parser(Config(), read_client=client).parse_docx_content(token, blocks)
print(markdown)
```

And one write. **The docx, Sheets and Base content and schema writes are plan-gated**: `dry_run`
returns a non-forgeable plan and touches nothing, you inspect it, then `apply` executes that plan
and only that plan. **Not every write on those three surfaces goes through a plan, and each
says which per leg:** the media legs (`put_image_in_document` and `put_file_in_document`;
`put_image_in_sheet`, `put_float_image_in_sheet` and `remove_float_image_from_sheet`; the Base
attachment upload, `BaseMediaClient.upload`) are direct calls, with no plan, and so are the
whole-object lifecycle calls (`create_document` and `delete_document`, `create_spreadsheet` and
`delete_spreadsheet`, and for a Base `delete_base` only, since a Base is created through the
plan-gated schema writes) and the documented direct cell write, `put_values` on
`SheetsWriteClient` (its other public value writes, `append_values`, `prepend_values` and
`batch_update_values`, are direct calls with no plan as well when you call them yourself).

**The four Drive write legs are not plan-gated either**:
a named version, an access grant, a file uploaded into a
folder and a folder you create are direct calls rather than a plan you approve first — and
**what verifies each one is stated per leg, not as one promise. Two of the four verify inside
the library and two do not.** `drive-access-write` declares `read-back-is-the-verdict` (every
grant / update / revoke is followed by an independent member read) and `drive-files-write`
declares `bytes-verified-round-trip` (an upload is re-downloaded and compared by `sha256` and
length, and the verdict ships as `LinkedFile.bytes_verified`). The other two verify nothing
here: `drive-versions-write` reads the head revision *before* its write — a pairing, not a
verdict, and it declares `version-pairing-is-not-a-verdict` to say so — and `create_folder` is
one call with nothing read back. Each surface's own `safety_contracts` in
`larkdocio.capabilities(full=True)` is the census, and it agrees with the top-level catalogue's
`applies_to` both ways. An
anchor points at a block on the **tree**, which is why the chain parses the tree rather
than the Markdown above:

```python
from larkdocio.common import (
    get_read_credentials, get_write_credentials, init_env, validate_download_url,
)
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import Anchor, EditRequest, WriteClient, apply, dry_run

init_env(".env")
url = "https://your-domain.larksuite.com/docx/YOURDOCTOKENHERE"
domain, doc_type, token = validate_download_url(url)
reader = Client(*get_read_credentials(), domain)
meta, blocks = reader.get_docx_content(token)
root = Parser(Config()).parse_docx_tree(token, blocks)   # 6. one write: anchor on the tree

plan = dry_run(                       # ZERO writes; inspect plan.entries before going on
    [EditRequest(
        # A SHORT fragment, matched byte-verbatim against the block's RAW STORED text —
        # a whole sentence copied off wrapped Markdown can differ from it by a soft return.
        anchor=Anchor(quote="Revenue grew 12.4%"),
        replacement="Revenue grew 15.0% in Q3.",
    )],
    root,
    document_revision_id=meta.revision_id,   # arms the whole-document staleness guard
)
assert plan.revision_guard == "active"
log = apply(plan, WriteClient(*get_write_credentials(), domain), token)
print([entry.to_dict() for entry in log.entries])
```

Three things the six lines leave out, all of them answered in the guide step 4 prints: a
`/wiki/` URL wraps the real document token and needs one extra hop; write work uses the
WRITE credential pair, ideally a second, write-scoped Lark app (recommended, not required — see
[Credentials & `.env`](#credentials--env)); and a
spreadsheet is a different surface with its own reader and its own plan-gated writes.

## Discovering the surface — the installed package describes itself

You never have to read source, and you never have to guess:

- `larkdocio.capabilities()` — the machine-readable capability registry's summary: every
  operation across the surfaces by name, each surface's scopes and opt-in status, plus the ids
  of the flags and safety contracts. `larkdocio.capabilities(full=True)` is the whole registry: every
  read/write operation, its required credentials and scopes, its opt-in flags, and each
  surface's safety contracts (plan-gated, dry-run-mandatory, the staleness guards). Both are
  projected straight off the library's own operation registries, so they cannot silently drift
  from the code. `json.dumps(larkdocio.capabilities(), indent=2)` is the readable form.
- `larkdocio.guide()` — the human-readable guide: a capability matrix distilled from
  `larkdocio.capabilities()` and drift-guarded against it, plus a runnable recipe for every
  handshake. This is the document to read first, and **with no argument you get its index**
  rather than the document: one row per section, each named after the failure it cures and
  spelled as the call that fetches it — a page of names, not a document.
  `larkdocio.guide(section=...)` returns one
  part — named by a heading or by the slug derived from it, either case-insensitively — and an
  unknown name raises `ValueError` naming every section there is.
  `larkdocio.guide(full=True)` returns the whole document, hundreds of KB as one string, which
  is a context decision you now make deliberately rather than by calling with no argument.
- `larkdocio.guide_sections()` — the guide's section index: one row per heading (`heading`,
  `slug`, `level`), names only and never text, so choosing a section costs nothing. Derived from
  the document's own headings on every call; the same rows appear on
  `larkdocio.capabilities(full=True)["docs"]["guide()"]["sections"]`.
- `larkdocio.writer_brief()` — the writer's long-form brief, including the Markdown
  authoring dialect. Also takes `section=...`, indexed by `larkdocio.writer_brief_sections()`
  — the same seam as `guide()`, at the same `(2, 3)` levels.
- `larkdocio.release_notes()` — what changed that affects you: public symbols, observable
  behavior changes, every dependency-pin move, known limitations. **Read it before you
  re-pin.** `section=...` returns ONE release (indexed by `larkdocio.release_notes_sections()`,
  one row per `## [X.Y.Z] — date` heading — level-2 only, because every release repeats the
  same `###` subsection titles).
- `larkdocio.changelog()` — the project's changelog: one entry per release, pointing at those
  notes for the detail. Same
  `section=...` / `larkdocio.changelog_sections()` pair, indexed the same way.
- `larkdocio.preflight.check_permissions()` — **optional and advisory**: do I hold what these
  operations need, before I start? It never mutates (each probe is a read against a
  deliberately nonexistent target), it is never required by anything, and
  `larkdocio.preflight.call_cost()` prices the check before you spend it. Read its `ok`
  **together with its `blind_spots`**: an operation whose requirement nobody has ever observed
  is named there, so an empty answer never reads as *needs nothing*.
- `larkdocio guide` — the same guide from a shell, with no Python: it prints
  `larkdocio.guide()`'s bytes to stdout — the index by default, one section with
  `--section <name>`, the whole document with `--full`.

**Every callable here is exported from the top level** (`larkdocio.__all__`), and
`larkdocio.capabilities(full=True)["entry_points"]` indexes them with a one-line summary and what each
one costs in API calls — so `dir()` is not the discovery mechanism for the calls either.

**The order to ask in.** Start with `larkdocio.capabilities()` to see *which* surfaces and
operations exist and what each one needs — and, because a task is not always one operation,
`["workflows"]` beside them, where a **compound workflow** (updating a document that already
has content is the one that exists today) names the module that performs it, the request
families it compiles down to through the same plan gate, and the guide section that teaches
it; then read the one that matters with
`larkdocio.guide(section=…)`, choosing its name from `larkdocio.guide_sections()` so you never
hold the whole document; and for the per-field-type detail — the raw wire shape a read hands
back, the shape a cell takes versus hands back, and the shape a filter condition takes on each
route — read the generated reference tables inside the guide. Each of those is a projection of
the library's own registries, so none can drift from the code. Asking in that order is how a
consumer stops discovering a capability *after* building around its absence.

**Every document written for a consumer has an accessor**, so none of them is reachable only
by knowing where the package unpacked, and `larkdocio.capabilities(full=True)["docs"]` lists all five
with the accessor that reads each — `dir()` is not the discovery mechanism. (The wheel also
carries the handler-authoring `blocks/BLOCK_TYPES.md`, a contributor doc with no accessor by
design.) Everything here resolves from an installed wheel with no network round-trip.

## Requirements

> **You will need:** **(1) a Lark (Feishu) application** — its App ID + App Secret are the
> credentials; nothing runs anonymously. **(2) Scopes granted to that app**, and **(3) the app
> shared onto the documents you'll read** — scopes are not access, and both are console actions
> on your side (this library never requests or escalates a scope).
> **[LARK_SETUP.md](src/larkdocio/LARK_SETUP.md) is the ten-minute walkthrough** — create the
> app, grant the starter scope, prove the first download. It **ships inside the wheel**, so an
> installed consumer reads the same text with `larkdocio.lark_setup()` and no clone. The full
> permissions table is PERMISSIONS.md at the root of this repository (not in the wheel) —
> generated from the code, never hand-kept; from an installed wheel the same truth is
> `larkdocio.guide()` / `larkdocio.capabilities()`.

- Python 3.11+
- A Lark app with read access to the target documents (App ID + App Secret) — **new to Lark
  apps? [LARK_SETUP.md](src/larkdocio/LARK_SETUP.md) is the ten-minute walkthrough** (create the
  app, grant the starter scope, share the documents onto it, prove the first download), and
  `larkdocio.lark_setup()` is the same document from an installed wheel.
- For **write work** — every surface `larkdocio.capabilities(full=True)` reports on the WRITE
  credential pair, whichever they are on the day you read this — the WRITE pair, naming a Lark app
  holding the write scopes those surfaces need (`larkdocio.guide(section="permissions-what-to-ask-for")`
  lists them per operation, generated from `larkdocio.permissions`). A second app kept separate from
  the read app is recommended, not required (see [Credentials & `.env`](#credentials--env)).

### Dependencies — exact pins, deliberately

larkdocio **pins its own runtime requirements to exact versions** (`==`, not `>=`). Those
requirements are `lark-oapi`, `click`, `python-dotenv` and `markdown-it-py`; the versions are not
retyped here, because a copy is where drift starts — read them off the wheel you installed
(`pip show -f larkdocio`, or its `Requires-Dist` metadata). That is a deliberate policy rather
than an oversight: the distribution model is a vendored wheel plus a pinned local-file
requirement, so a fresh clone of a consumer resolves **those requirements** to the same versions
the wheel was tested against.
**Every pin move is announced in the release notes** of the version that moves it (read
them with `larkdocio.release_notes()`), so a consumer sees the change before vendoring it.

**The policy stops at the requirements named above — it does not pin the transitive closure.**
Each of them has dependencies of its own, and those carry whatever constraint their authors
chose; several carry none at all, including direct children of `lark-oapi`. So a fresh clone can
resolve a *transitive* package to a version this wheel was never tested against, and pinning the
requirements named above is not a guarantee about the whole graph. If you need the closure
reproducible, that is a lockfile in your own project — this policy covers only the requirements
larkdocio itself declares, and it is stated this narrowly on purpose rather than implying more.

**Import-time `DeprecationWarning`s you will see, and none of them is ours.** On Python 3.14,
importing larkdocio emits exactly one `DeprecationWarning`:
`lark_oapi/ws/pb/google/protobuf/internal/well_known_types.py` calls
`datetime.utcfromtimestamp()` at module scope, and Python deprecated that call in 3.12. That
module is a **protobuf vendored inside `lark-oapi`** — the `protobuf` distribution is not
installed at all, and larkdocio's own code touches no protobuf. On Python 3.12 and 3.13 you see
that one plus deprecations raised by `lark-oapi`'s own websocket client
(`lark_oapi/ws/client.py`) and by the `websockets` library it imports; on 3.11 you see
only those, because the vendored one needs 3.12. **Nothing in larkdocio suppresses any of
them**, and that is deliberate rather than an omission: a library that edits its consumer's
warning filters silences a diagnostic the consumer never asked to have silenced, in a process
the consumer owns. So they are recorded here instead. **You may filter them in your own test
configuration** — a `filterwarnings` entry naming those modules — which is a decision about
your process, and yours to make.

## Credentials & `.env`

The reader resolves its credentials in this order:

1. `LARK_READ_APP_ID` + `LARK_READ_APP_SECRET` — used when **both** are set.
2. Legacy `LARK_APP_ID` + `LARK_APP_SECRET` — the fallback (every existing
   `.env` keeps working).
3. **Neither pair complete → `get_read_credentials()` RAISES `LarkConfigError`.** It is
   pair-wise, so a lone `LARK_READ_APP_ID` with no matching secret falls back to the legacy
   pair rather than half-resolving; when no complete pair resolves you get one refusal that
   **names the pair that is in force** — on a clone with nothing configured, the legacy pair —
   and echoes no credential value. It used to return an empty pair and no signal.

`LARK_WRITE_APP_ID` / `LARK_WRITE_APP_SECRET` are used only by the **write surfaces**, and
that is a class rather than a list: every surface `larkdocio.capabilities(full=True)` reports with
`credentials["app"] == "write"` needs the pair, and each one's scopes are the rows
`larkdocio.permissions` generates (read them with `larkdocio.guide(section="permissions-what-to-ask-for")`,
or as `larkdocio.capabilities(full=True)["surfaces"][...]["credentials"]["scopes"]`). Ask the registry
rather than trusting a sentence — the enumeration here went stale twice. They are never
consulted by the read path (least-privilege read/write separation).

Provide credentials by either:

```bash
# bootstrap a local .env (writes LARK_READ_APP_ID / LARK_READ_APP_SECRET)
larkdocio config --appId YOUR_APP_ID --appSecret YOUR_APP_SECRET
```

On a `.env` that already uses the legacy names, that command updates **those** in place
and tells you so — it never re-keys an existing credential file for you. It writes the
read side only; `LARK_WRITE_APP_*` are separate credentials (one app or two; two recommended) and are yours to add.

…or create a `.env` in the directory you run from:

```env
LARK_READ_APP_ID=cli_a123...
LARK_READ_APP_SECRET=abc...
# (or the legacy LARK_APP_ID / LARK_APP_SECRET)
```

…or point at an external `.env` — note `--env-file` is a **global** option and
must come **before** the subcommand:

```bash
larkdocio --env-file /path/to/.env download "<URL>" -o ./out/
```

## CLI

Installing the wheel installs the `larkdocio` console command.

```bash
larkdocio --version
larkdocio download "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./out/
larkdocio folder "https://your-domain.larksuite.com/drive/folder/AbCdEfG" -o ./out/
larkdocio guide --full > larkdocio-guide.md
larkdocio mermaid --flowchart spec.json > diagram.mmd
larkdocio roundtrip pull "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./edit/
larkdocio roundtrip push -o ./edit/
larkdocio roundtrip push -o ./edit/ --apply
```

**Exactly one command here writes to Lark: `roundtrip push --apply`.** The other five —
`download`, `folder`, `guide`, `config`, `mermaid` — read and convert, and none of them can
change a Lark document, spreadsheet or Base. That split is the point rather than an accident:
**a download must never be able to mutate the document it is reading**, so the reading verbs
carry no write flag and never will, and writing lives in a verb of its own. That verb is
**plan-gated**: `roundtrip pull` writes the document to a Markdown file you edit, and
`roundtrip push` reconciles your edited file, **always** builds and prints the plan, and
writes only under `--apply` and only through that plan — refusing whole, with zero writes,
when the document moved while your edit sat on disk. It is also the only place the command
line consults the WRITE credential pair. Everything **else** a consumer can write is still a
library call with no flag here — Sheets and Base writes are a plan you approve first, while
the four Drive write legs (a named version, an access grant, a file into a folder, a folder you
create) are direct calls, each stating its own verification — **two of the four verify inside the
library and two do not**: an independent member read-back on the access leg, a `sha256` + length
re-download on the file leg, a pre-write revision read (a pairing, not a verdict) on versions,
and nothing read back on folder create. Each
surface's `safety_contracts` in `larkdocio.capabilities(full=True)` states which; the recipes are in `larkdocio.guide()`.

**Every message the CLI logs goes to stderr; stdout carries a command's output.** So
`larkdocio mermaid … > diagram.mmd` gets diagram source and nothing else, and `larkdocio
download`'s progress lines arrive on stderr (add `2>&1` if you were reading them off stdout).

**Subcommands:**
- `download` — a docx/wiki URL to Markdown + `static/` images (options below).
- `folder` — a Drive **folder** URL to one Markdown document: it enumerates the tree and reads
  the documents inside, disclosing what it cannot read. Read-only, and the counterpart of
  `download` (which handles one document and refuses a folder URL by naming this verb). Takes
  `-o` (an output directory) and `--dump`, which **also** writes a machine-readable child
  manifest — `<folder token>.json` beside the Markdown, the same naming and placement
  `download --dump` uses. One row per child carrying its title, token, type and revision, plus
  the listing's `created_time` / `modified_time` / `owner_id` / `url`, the read-or-disclosed
  outcome, and the walk's own truncations — the input a change-detection ledger wants. The flag
  is purely additive: the Markdown is byte-identical with or without it. A **revision is
  reported only where the read already carried one** (a document's `revision_id`, a
  spreadsheet's `revision`) and is marked *unavailable, with the reason*, everywhere else — it
  is never fabricated, never inferred, never silently omitted, and no extra API call is made to
  obtain one. It also takes `download`'s three deep-read opt-ins — `--deep-read-sheets`,
  `--fidelity-read-sheets` and `--deep-read-bases` — with the **same spelling, the same
  semantics and the same default (off)**, so a document inside the folder can read its embedded
  sheets and Bases as content instead of as a placeholder. Off (the default) the walk is exactly
  what it always was and makes no Sheets or Base API call; on, a deep read that fails degrades
  to the placeholder and never fails the child, and a child that fails is disclosed and never
  fails the walk. Finally, `--assets` **also fetches every document's images and its
  flowchart / mindmap (whiteboard) PNGs** — the flag a *mindmap-only* document needs, since
  without it such a document comes back as a bare token and nothing else. They land in **one
  shared pool** beside the Markdown, `static/<asset token>.<ext>`: the same directory name and
  the same token-derived filenames `download` writes for a single document, with every
  reference in the Markdown rewritten to that local relative link. **Collisions are impossible
  by construction** — the filename *is* the Lark asset token, which is globally unique, so the
  same token in two documents is the *same* asset: fetched once, written once, every reference
  relinked. Off by default (a whole folder's binaries are a different cost class from one
  document's, and `download`'s own handling is unconditional rather than flagged): off, no
  asset call is made, no pool directory is created, and the Markdown is byte-identical to a
  walk without it. An asset that fails is disclosed in Lark's own words — naming the document
  and the asset, in the log and in an `## Assets not fetched` section — and never fails the
  walk. Attachments are not included; those are `download`'s own separate config opt-in.
- `roundtrip` — **edit a document as a Markdown file, and the one subcommand that writes to
  Lark** (options below). Two invocations of one verb, because your edit happens *between*
  them — in another process, or tomorrow. `roundtrip pull "<url>" -o ./edit/` reads the
  document on the **READ** credentials and writes **two files** into `-o`:
  `document.snapshot`, which is **ours and immutable** (the read itself, checksummed, carrying
  the revision and the tenant domain), and `document.md`, which is **yours and editable** and
  is the file to hand a person or an agent. Every block in it carries an identity marker
  comment; keeping each marker where it is is what makes this an **update** rather than a
  re-authoring: a block that only changed its text is patched in place and keeps its id,
  where a re-authoring deletes it and makes a new one under a new id, leaving everything
  addressed by the old id pointing at an id the document no longer has. The patched block is
  re-written from your Markdown as one run carrying the styling the block starts
  with, so a colour that differed elsewhere in the paragraph is flattened onto that, and
  styling the authoring dialect cannot create refuses the push rather than being flattened.
  **Text is not the only thing an edit carries**: flipping `- [ ]` to `- [x]` under a marker
  really moves the checkbox, through the same plan-gated route, and those two — the text and
  a todo's `done` bit — are what a roundtrip edit can move. An edit that compiles to a
  byte-identical write is **refused typed** (`change-not-expressible`) rather than reported
  applied. That is all.
  Then `roundtrip push -o ./edit/` loads the snapshot, reconciles your edited file
  against it, and **always builds and prints the plan** — and writes nothing at all until you
  add `--apply`. **There is no flag that skips the preview**; `--apply` means *apply the plan
  you just previewed*, and the write goes only through that plan. The plan carries the
  revision the snapshot recorded, which arms the whole-document compare-and-swap: if the
  document changed while your edit sat on disk the batch is **refused whole, with zero
  writes**, and the fix is to pull again and re-apply your edit. A snapshot that carried no
  revision cannot arm it, and the command **says so loudly** instead of writing as if it had.
  After a successful apply it **re-reads the document and verifies it by compose-equivalence**
  — what the document now *means*, against what you authored — never by comparing two
  Markdown strings, which reports a false difference on every list; a block whose content is
  outside the authoring dialect is reported *unverifiable by name*, never counted as clean.
  It is the **first and only** place this command line consults the **WRITE** credential pair
  (`LARK_WRITE_APP_ID` / `LARK_WRITE_APP_SECRET`), it also needs the READ pair for the
  read-back, and the two are resolved **separately** — neither is ever borrowed for the other,
  and a `push` with no WRITE pair refuses *before it makes any call*, naming both variables.
  Every refusal is typed, says what to do next, and names the guide section that covers the
  recovery. The same flow as a library call, with the same gates in the same order, is
  `larkdocio.roundtrip.pull()` / `.push()`, and the runnable Python it was promoted from is in
  the packaged guide.
- `config` — bootstrap or read the local `.env` (see [Credentials & `.env`](#credentials--env)).
- `guide` — print the packaged consumer guide to stdout: the same text `larkdocio.guide()`
  returns, read out of the installed package, so it needs no network, no credentials and no
  source tree. With no option it prints the **section index** — every section named after the
  failure it cures, with the call that fetches it. `--section <name>` prints one part of the
  document — name a section by its heading or by the slug derived from it (both
  case-insensitive), and a top-level name brings its subsections with it; an unrecognised name
  prints nothing, refuses, and lists every section there is. `--full` prints the whole
  document, hundreds of KB as one string (this is what the bare command printed before the
  index became the default); it cannot be combined with `--section`. The bytes are the
  document's own (no pager, no colorization, no reflow), so `larkdocio guide --full > guide.md`
  and piping it into another program both work.
- `mermaid` — compile a structured diagram spec (JSON) to Lark-safe Mermaid source: a spec
  file, or `-` for stdin, in; source out on stdout or into a file (options below). **Pure** —
  no credentials, no network, no document is touched — and it never writes the diagram into a
  Lark document; that is the library call in the packaged guide's mermaid recipe. A spec the
  renderer could not draw **refuses**: the message names the construct and its value on
  stderr, the exit status is non-zero, stdout stays empty and no output file is left behind.

**Global options (before the subcommand):**
- `--env-file` — path to the `.env` file.
- `--config` — path to a `config.json` whose `output` object tunes what the reader writes.
  The full schema — every key, its default and what it does, plus the whole file at
  its defaults — is in the packaged guide (`larkdocio guide`, or `larkdocio.guide()`) under
  *Output configuration*; omit `--config` to use those defaults. `download` and `config` read
  it; `folder` does not.
- `--version` — print the installed larkdocio version and exit.

**`download` options (after the subcommand):**
- `-o`, `--output` — the **root** the Markdown + `static/` images are written under (default
  `./`). The file lands there **flat**: nothing in the document's own contents moves it —
  larkdocio reads no metadata table, no title convention and no filename grammar to decide a
  destination. Pass `--route` to place it under a subpath **you** name, and pass the root as
  `-o` rather than pre-building the subpath into it — **it double-nests**. The rule in full
  (the sanitization, the refusals, the filename stamp) is in the packaged guide under
  *Where the file lands*.
- `--allowHost` — additionally allow a non-default Lark host when validating the URL.
- `--dump` — also write `<token>.json` with the raw API payload (debugging).
- `--deep-read-sheets` — opt in to reading sheets **embedded in the document** into inline
  Markdown tables. Off by default: an embedded sheet stays a traceable placeholder and no
  Sheets API call is made. A failed read degrades to the placeholder, never to an error.
- `--fidelity-read-sheets` — opt in to whole-cell (format-level) bold/italic **and per-cell
  background fills** on a deep-read sheet, via an xlsx export of the spreadsheet. Needs
  `--deep-read-sheets`. Bold/italic render as Markdown emphasis; a fill has no Markdown
  equivalent, so each tab's fills are disclosed in a note above its table (the ARGB against
  the cells carrying it) — which is what makes a colour-encoded sheet readable rather than
  silently empty. Run-level emphasis inside a cell already renders without this flag, so on
  such a sheet the flag correctly changes nothing for emphasis. A failed export degrades to
  the values-only table and says so.
- `--deep-read-bases` — opt in to reading a **Base embedded in the document** (both embed
  block types) into inline Markdown tables — the command-line route the Base twin of
  `--deep-read-sheets` previously lacked. Off by default: no Base API call is made and the
  reader emits the placeholder it always has. A failed read degrades to that placeholder,
  never to an error, so a download never fails because a Base could not be read.
- `--local-time` — stamp the output filename in the machine's **local** clock instead of the
  default **UTC**. The `[YYYY-MM-DD_HHMM]_<title>.md` shape is unchanged — only the digits
  move, no zone suffix is added. **The trade-off, disclosed:** the same document downloaded
  at the same instant on two machines in different zones then lands under **different** names,
  so a ledger keyed on the filename becomes machine-dependent; UTC (the default) keeps that
  name identical on every machine. `--dump` records which basis a run used.
- `--route` — place the output under a caller-supplied **subpath** beneath `-o` (e.g.
  `area/section/topic`). It is **the only thing that ever moves output off `-o`**: you
  supply the path and larkdocio infers nothing from the document. Each segment is sanitized
  (spaces to underscores, OS-reserved characters stripped) but **not** lower-cased — your
  spelling is yours; an absolute path, a `..` segment or an empty segment is refused, never
  normalized — it cannot escape `-o`.

**`roundtrip` options (after the subcommand):**
- `-o`, `--workdir` — a **directory**, always (default `./`): the one holding the two files
  the verb passes between its phases — `document.snapshot` (ours, immutable) and
  `document.md` (yours, the file you edit). `pull` writes both into it and `push` reads both
  out of it, so **both phases must be given the same directory**.
- `--apply` — on `push` only: apply the plan that was just previewed. **It does not skip the
  preview** — the plan is built, armed with the snapshot's revision and printed either way,
  and the write goes only through that plan. Without it, `push` is a rehearsal that writes
  nothing, which is what to run first; with it, the apply is followed by a re-read and a
  compose-equivalence verification of every edited block.

**`mermaid` options (after the subcommand):**
- `--flowchart` — state that the spec is a flowchart.
- `--sequence` — state that the spec is a sequence diagram. **The diagram kind is stated,
  never guessed:** pass one of these two flags, or give the spec a `"kind"` key spelling one
  of them. Stating neither refuses, and a flag that contradicts the key refuses rather than
  picking a winner — which keys a spec happens to carry is never consulted.
- `-o`, `--output` — write the Mermaid source into this **file** instead of stdout. (Note the
  collision: `download`'s `-o` is a **root** that output is written under; this one is the
  output file itself.) Nothing is written when the spec is refused, so a refusal never leaves
  a half-finished diagram behind.

`larkdocio.capabilities()` and `larkdocio.guide()` answer the same questions offline, from
the install — including what the reader does with every block type.

### IPv4 pinning (`LARK_DISABLE_IPV4_PIN`)

On startup the CLI pins Python's DNS resolver to **IPv4 only**, because Lark's
IP allowlist is IPv4-only — an IPv6-resolved host leaves from an off-allowlist
source and Lark rejects the request. On by default; set
`LARK_DISABLE_IPV4_PIN=1` (also `true`/`yes`) to restore stock resolution (e.g.
on an IPv6-only host).

## Troubleshooting

- **IP Blocked** — add your current IP to the allowlist in the Lark Developer Console.
- **Permission Denied** — open the doc in a browser, Share → Add Integration, grant the app
  read access.
- **`@mentions` come back as raw `@ou_…` ids** — expected and documented: mention
  resolution needs the contacts scope and a data range that covers those users, and it
  degrades to the raw id rather than failing your read. `larkdocio.guide()` states both
  preconditions.

---

## Developing larkdocio

Everything from here down is **in the source repository** — the clone. A vendored wheel carries
none of it as files at these paths: the package is installed as `larkdocio/` rather than
`src/larkdocio/` (see [Package layout](#package-layout)), and the consumer-onboarding scripts,
the CLI contract, the capability matrices and the example environment file are not in it at all. If you are
reading this as the installed package's description and only want to *use* the library, the six steps
above are the whole story and `larkdocio.guide()` is the rest of it.

### Quickstart (from a clone)

One package carries every surface. `./setup.sh` creates
`.venv`, installs larkdocio plus the dev extras, seeds a `.env` from `.env.example` on first
run, and runs the test suite. Then put your read credentials into that `.env` — it is
gitignored and never committed — using either the `LARK_READ_APP_*` pair or the legacy
`LARK_APP_*` one, and run the CLI:

```bash
./setup.sh
source .venv/bin/activate
larkdocio --version
larkdocio download "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./out/
```

Installing from source: `python -m venv .venv && source .venv/bin/activate && pip install .`
(or `pip install larkdocio-<ver>-py3-none-any.whl` for a built wheel). Building the wheel and
sdist is `python -m build`.

### Reference docs

- [`TOOLS.md`](TOOLS.md) — the full CLI contract. Its
  [`config.json` schema](TOOLS.md#output-configuration-configjson) is a **generated projection**
  of the reader's own settings object, and the packaged guide (`larkdocio guide` /
  `larkdocio.guide()`, under *Output configuration*) carries the same generated region — so a
  consumer holding only a wheel reads the schema there rather than here.
- [`BLOCKS.md`](BLOCKS.md) — the block-type → Markdown support matrix, the single source of
  truth for what the reader does with every block type.
- [`SHEETS.md`](SHEETS.md) — the same for the Sheets surface.
- [`BASE.md`](BASE.md) — the Base (bitable) surface: what reads, what writes, and the register
  of what was measured rather than assumed.
- [`DRIVE.md`](DRIVE.md) — the Drive surface: the folder read plus the write legs beside it
  (named versions, access, files into a folder, folder creation) and the fences on each. The
  per-verb census is the Operations table in that file, not a count typed here.
- [`PERMISSIONS.md`](PERMISSIONS.md) — which Lark scopes each operation needs, on which
  credential pair. Unlike the matrices above it is **generated**: it is a projection of
  `larkdocio.permissions` (as is the packaged guide's permissions section), held byte-identical
  to it by `tests/test_permissions_docs.py`, so it is read and never hand-edited.
- [`src/larkdocio/blocks/BLOCK_TYPES.md`](src/larkdocio/blocks/BLOCK_TYPES.md) — handler-
  authoring mechanics (how to add a block type to the registry). It ships inside the wheel
  and deliberately carries no support table; status lives only in `BLOCKS.md`.
- [`LARK_SETUP.md`](LARK_SETUP.md) — the consumer's Lark-application walkthrough (the app, its
  scopes, its reach). This root copy is **canonical**; the packaged
  [`src/larkdocio/LARK_SETUP.md`](src/larkdocio/LARK_SETUP.md) is its **generated twin**,
  materialised from it by `./scripts/sync-packaged-notes.sh` exactly as the two release
  documents are. Edit the root file and regenerate — `--check` reports drift and the suite
  refuses a stale copy, so a hand-edited packaged copy cannot reach a release.

### Package layout

The paths below are in this clone. A vendored wheel installs the same tree as the
importable `larkdocio` package, minus the `src/` prefix; of the Markdown in it, only
`GUIDE.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, `LARK_SETUP.md`, `blocks/BLOCK_TYPES.md` and
`write/README.md` travel inside the wheel.

| Path | What it is |
|------|------------|
| `src/larkdocio/read/` | The reader: block fetch + pagination (`client.py`), Markdown rendering (`parser.py`), image/board download, and the `download`/`config` command handlers. |
| `src/larkdocio/blocks/` | The shared block model + per-type handler registry, and the handler-**authoring** guide ([`BLOCK_TYPES.md`](src/larkdocio/blocks/BLOCK_TYPES.md) — how to add a type; it carries no support table). |
| `src/larkdocio/write/` | The writer: plan-gated writeback apply-engine (anchor resolution `resolve.py`, dry-run `preview.py`, `apply.py`, throttled `client.py`, Markdown authoring `compose.py`, request/refusal/apply-log model `model/`). |
| `src/larkdocio/sheets/` | The Sheets surface: values→Markdown reader, the xlsx-export fidelity reader, and the plan-gated value / rich-cell / structural write engine. |
| `src/larkdocio/base/` | The Base (bitable) surface — **records AND schema writable, each through its own plan-gated engine**: the `(type, ui_type)` cell-renderer registry — the storage type and the presentation type together decide a cell's encoding — a throttled read client, the Markdown assembly plus its two entry points (`read_base_markdown` for the reading form, `read_base` for the structured intermediate), the opt-in bridge that inlines a Base embedded in a document, the **opt-in cross-table link resolver** (`read_base(url, resolve_links=True)` — a link cell's ids followed to their targets and rendered as each target table's schema-designated primary field; **off by default and byte-identical when off**, batched per target table rather than per cell, its extra read cost disclosed on the result, and a link whose target record was deleted typed as a normal outcome rather than raised), a **plan-gated record-write engine** (snapshot a table, edit it in memory, preview the change as a `Plan`, then apply) and a **plan-gated schema-write engine**: it creates, renames and copies a Base, creates, renames and deletes tables, creates, edits, converts and deletes **columns** across a published allow-list, and creates, updates and deletes **views** carrying a persistent **filter**. Every delete is enumerated by a Base-wide loss preview first and applied only under consent minted from that same plan. Hidden columns are settable; grouping and a view-level sort are not offered, and a form view is out by policy. **Attachment media moves too, out of band** — an upload hands back the file token an attachment cell is written from, and the same token downloads back so the round trip can be verified by comparing **sha256** digests rather than by trusting a success code. It is a **leg beside** the read and the write rather than part of either: a read still renders file **names** only, the short-lived signed links a cell reads back are treated as credentials and never render, no media byte is ever inspected, and an upload is **permanent** — **no route in Lark's open API purges drive media, measured rather than assumed** (nine destructive request spellings, fourteen sends, not one removed a token — measured on sheets- and docx-minted tokens, and unmeasured, not refuted, for a Base-parented one; the enumeration and the scope it does not exceed ship on `larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA` and in the guide's disposables doctrine), so the leg says so instead of pretending otherwise. `capabilities()` reports it as five surfaces (`base-read`, `base-comments-read`, `base-embedded-deep-read`, `base-write`, `base-schema-write`), each with its scopes and its limits. Reached by importing `larkdocio.base`: it is **not** re-exported at the top level, and its read/write engines carry no CLI flag. The command-line touchpoint is `download --deep-read-bases` (and `folder --deep-read-bases` for a folder walk), which inlines a Base **embedded in a document** as Markdown tables — a read; the Base write engines have **no command-line route at all** and stay library calls, and the one command-line verb that writes anything (`roundtrip push --apply`) writes to a **docx**. |
| `src/larkdocio/comments/` | The comments reader: list/batch-fetch a file's comments and resolve them onto the block each one is anchored to. A **Base's** comments come through the same client and entry point (a third accepted file type) and carry the record / table / view the reviewer had open. |
| `src/larkdocio/contacts/` | The forward lookups: **exactly one** `open_id` out — or a typed refusal saying which of *not-found* / *ambiguous* / *could-not-look* happened. `resolve_user` takes a display **name**; `resolve_colleague` takes an **email** (or a mobile, accepted but never yet observed resolving anybody) on a different endpoint family whose reach is measured at two identifiers and stated no further. Read-only, paced, two point queries. Neither fuzzy-matches, takes the top hit, or enumerates the directory to fake a search — and an address route is not a name route. |
| `src/larkdocio/drive/` | Folder **read**: hand it one folder link and it enumerates the tree and reads the documents inside — a throttled, read-only client for the one Drive listing endpoint, paged to exhaustion on Lark's own opaque cursor, a depth-first walk that carries a visited-set so a cycle cannot loop it, a `type`→reader dispatcher, and `read_folder()`, which runs the docx / Sheets / Base readers over the walk and returns one structured result plus one Markdown document (a tree index, then the read documents, then a disclosure of what could not be read). Every child arrives with the fields Lark reported, including the ready-to-use `url`, and Lark's own `type` word is carried through untouched. Caps (depth, total children, total calls, pages per folder) are explicit parameters with documented defaults, and a cap that fires is **disclosed** on the result — an enumeration never silently truncates. A child that fails to read never fails the walk; it is disclosed by name. When Lark refuses a folder token it answers one code for three different causes, so the refusal says the folder *may not exist or you may not have access* and does not guess which. The folder **read** is read-only: the walk moves, uploads and writes nothing — a claim about that walk, not about the package, which also carries the four write legs below. Reached from the CLI as `larkdocio folder "<url>" -o ./out/`, or by importing `larkdocio.drive`; `capabilities()` reports it as the `drive-read` surface. The package also carries the file's **named versions**: `list_versions` reads them (newest first, paged for you, an empty list where a document has never been versioned) and `DriveVersionsWriteClient.create_version` adds one, returning the new token **paired with the head revision read immediately before it** — because a version token resolves to nothing on its own. It needs the WRITE credential pair and is reported separately as the `drive-versions-write` surface; there is deliberately **no delete-version call**. The package also carries **who may use a document**: `DriveAccessWriteClient` grants a named human `view` / `edit` / `full_access` on a **docx, spreadsheet or Base the app created** (the object type is the `obj_type` argument, in larkdocio's vocabulary or Lark's, or read off the object's URL) — by email or `open_id`, a bare display name refused before any call — raises, lowers and revokes it, reads the members **and the owner** (the owner is not a member row; and what the member rows hold depends on where the document was filed — none at all when it was created with no folder, the folder's own rows marked `perm_type='container'` when it was created into one, both measured), and moves the two document settings whose names govern copying, one key per call. Every one of those reports what an independent **read-back** found rather than what the call returned. It is reported as the `drive-access-write` surface, and it deliberately does **not** transfer ownership (measured one-way: the app loses its delete right), does not grant to a group (unmeasured), refuses locally every object type it has not measured — `file` and `wiki` as unmeasured rather than impossible, and `folder` on evidence rather than on silence: a grant sent as `type=folder` was **refused by Lark** (`403 · 1063002`, three enumerated write spellings, 2026-08-17, one tenant, one application identity, `tenant_access_token`), a claim bounded to *Lark refused the write* because that tenant has no folder member-read to say more (the shipped refusal message carries the measurement; [`DRIVE.md`](DRIVE.md) carries the row), and claims nothing about whether a human's clipboard then obeys. The package also carries **one file into a folder**: `put_file_in_folder` uploads a single local file to a folder token and hands back the uploaded file paired with the link it reads back for it — sending it in the blocks **Lark itself declares** when it is too large for one shot, which is a size story the caller does not have to choose between, `DriveFilesWriteClient` carries the upload / download / permalink / delete legs behind it, and a `LinkedFile` is the read-back verdict rather than the call's own answer. It needs the WRITE credential pair, is reported as the `drive-files-write` surface, and — like the versions and access legs — carries **no plan gate**: there is no dry run to approve, so the read-back is the proof. It is reached at `larkdocio.drive.files_write` and is deliberately **not** re-exported on `larkdocio.drive` — the versions and access clients are; the files and folders clients are not (a re-export is a public-surface addition, and the issue that corrected this prose was forbidden to move a capability). The package also carries **one folder created under a parent**: `DriveFoldersWriteClient.create_folder(name, parent_token)` in `larkdocio.drive.folders_write`, reported as the `drive-folders-write` surface. It is **one call and only one** — there is no read-back; you get Lark's own answer for the new folder, its token and the url when Lark supplies one — and it declares `caller-supplied-destination`, not `read-back-is-the-verdict`. Creating one is the whole of what this package does to a folder: **a folder made through larkdocio is permanent as far as larkdocio is concerned**, and creating the same name twice under the same parent makes a second folder rather than reusing the first — so choose the name once. What the surface reaches is the Operations table in [`DRIVE.md`](DRIVE.md). Like the files client it is deliberately **not** re-exported on `larkdocio.drive`. |
| `src/larkdocio/mermaid/` | The Mermaid compilers: a structured diagram spec in, Lark-safe flowchart or sequence-diagram source out, plus the dialect rule set as constants and the rule document `larkdocio.mermaid.rules()` returns. Pure text in, text out — it makes no API call. |
| `src/larkdocio/model/` | The typed document model — nodes (dumb data) plus the `MarkdownRenderer` that serializes them. |
| `src/larkdocio/common/` | The shared read/write core: **the typed error taxonomy every surface raises** and the Lark error-code lookup beside it, tenant-token auth + the IPv4 pin, URL validation, the throttled HTTP transport, the staleness-marker vocabulary, output-filename sanitizing, and the operator-facing reporting helpers. It is the bottom tier and imports nothing above itself. |
| `src/larkdocio/utils/` | Back-compat shims only. Every name here is re-exported from `larkdocio.common`, which is where the code lives and where new imports should point; these modules stay so existing imports keep working. |
| `src/larkdocio/auth.py` | A **back-compat shim** — every name here is re-exported from `larkdocio.common.auth`, which is where credential resolution, `.env` handling and the refusal text actually live. Import from `larkdocio.common.auth`; this module stays so existing imports keep working. |
| `src/larkdocio/capabilities/` | `larkdocio.capabilities()` — the machine-readable capability registry, projected off the op registries. |
| `src/larkdocio/guide.py` | `larkdocio.guide()` / `larkdocio.writer_brief()` / `larkdocio.release_notes()` / `larkdocio.changelog()` — `larkdocio.lark_setup()` — an accessor per packaged **consumer** document, each readable from an installed wheel; each also takes `section=...`, indexed by its own `<accessor>_sections()` sibling (`guide_sections()`, `writer_brief_sections()`, `release_notes_sections()`, `changelog_sections()`, `lark_setup_sections()`) so one part of a document can be read instead of all of it. The set is `capabilities(full=True)["docs"]`; do not count it from this row. |
| `src/larkdocio/permissions.py` | `larkdocio.permissions` — which Lark scopes each operation needs, on which credential pair, with the evidence for each. Derived from the code that makes the calls, and the single source the capability registry and both permissions documents are projected from. Also the uniform permission-refusal shape: a scope denial carries the exact missing scope, Lark's verbatim answer and its console link, and is never reported as an absent thing. |
| `src/larkdocio/preflight.py` | `larkdocio.preflight.check_permissions()` — an **optional, advisory** check of whether you hold what an operation set needs, before you start. Never mandatory, never mutates (each probe is a read against a deliberately nonexistent target), discloses its own call cost, and states per scope how it knows — including the blind spots it cannot see. |
| `src/larkdocio/snapshot.py` | `larkdocio.snapshot.snapshot()` / `load()` — keep a docx read on disk and bring it back. One versioned, checksummed file carrying the **raw block payloads**, the `document_revision_id` and the document token; `load()` rehydrates it offline to the same node tree, with one guarantee: a **load-then-project is byte-identical** to the projection the snapshot was taken from, so edits made against a projection still reconcile against one taken a day later. A checksum mismatch, a truncated file, an unrecognized format version or malformed content is a **typed refusal naming re-download** — no repair, no salvage, never a partly-rehydrated tree. The checksum is for **integrity only**: no security boundary exists between a local library and its caller, so what it answers is accidental corruption (a truncated write, a half-synced cloud folder, a corrupted disk, a hand-edited file) and nothing else — there is no encryption and no key material. The snapshot is **immutable** and the editable artefact is the **Markdown**; the boundary between them stays `reconcile()`, and no mutable tree API ships. Reached by importing `larkdocio.snapshot`; it is not re-exported at the top level, reaches **no endpoint**, and needs **no credentials**. docx only — sheets, Base and folder reads are not covered. |
| `src/larkdocio/roundtrip.py` | The **file-first round trip**, as one verb: `larkdocio.roundtrip.pull()` writes the two files (`document.snapshot`, ours and immutable; `document.md`, yours and editable), you edit the Markdown, and `push()` reconciles it, **always** previews the plan, applies only when asked, and verifies the result by **compose-equivalence** against a fresh read. It **composes shipped operations and opens no endpoint of its own** — `snapshot`/`load`, `project_block_ids`, `reconcile`, `compile_reconciliation`, `dry_run`, `apply`, the read client and the write client, in the order the packaged guide's own recipe puts them — so no permission row moves and no request family is minted here. The preview is **structurally unskippable**: `apply()` accepts only the plan `dry_run()` returned and no argument removes that step, which is the whole reason the flow became a verb instead of eighty lines a consumer retypes. Reached by importing `larkdocio.roundtrip`, or from the command line as `larkdocio roundtrip pull` / `push` — **the one console command that writes to Lark**. It uses the READ pair to read and the WRITE pair to write, resolved separately and never substituted for one another. docx only. |
| `src/larkdocio/errors.py` | **The import path for the typed error taxonomy** (`LarkDocIOError` and its family) — and the one to keep using: every recipe in the packaged guide says `from larkdocio.errors import ...`, and nothing about that is deprecated. The family is *authored* one tier down, in `larkdocio/common/errors.py`, because the shared core raises these types and nearly every module imports them; the names bound here are the **same objects** the core defines, so `except` and `isinstance` answer identically on either path. One visible consequence: a class reports where it is defined, so a traceback prints `larkdocio.common.errors.LarkConfigError`. |
| `src/larkdocio/langs.py` | The one code-block language table, both directions (fence token ↔ Lark's enum). |
| `src/larkdocio/cli.py` | The `larkdocio` console entrypoint (click group). |

### Tests

```bash
pip install .[dev]
pytest
```

The default suite is **large and fully offline** — deterministic, run against JSON
fixtures (real SDK `Block` objects deserialized from payloads: recorded API responses with
identifying values replaced — `tests/captures/README.md` lists what was replaced and what was
kept — and hand-written ones) plus
packaging, auth-fallback, and golden-output tests. It needs no credentials and no
network; run `pytest -q` for the current count. (No count is quoted here on purpose: a
number in prose is stale the moment the next test lands.)

Three opt-in rings sit alongside it, all **deselected by default** (plain `pytest`
never runs them). The first two read a disposable scratch document whose URL comes from the
environment — the names are documented in `.env.example`:

- **Live canary** — `pytest -m live`. Downloads the disposable scratch doc twice
  via the package API and asserts the reader still succeeds and is byte-identical
  across the two runs (the binding round-trip gate for reader changes). Needs read
  credentials + `LARKDOCIO_CANARY_DOC`; skips with a clear message when unset.
- **Zoo ring** — `pytest -m zoo`. **Advisory, never a gate.** Reads the disposable
  "block zoo" doc to re-harvest offline fixtures; skips when unset. See `.env.example`.
- **Live-write ring** — `pytest -m live_write`. **Never a gate.** Creates its own disposable
  document on the write credentials, round-trips it and tears it down. Selecting the ring is
  not enough: it also refuses to run unless `LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY` names the
  issue that authorizes the run (see the marker's description in `pyproject.toml`). The
  live-write ring is maintainer-only: the value is a maintainer issue id of the form `LD-<n>`,
  and a contributor leaves the variable unset, so the ring skips.

### Consuming larkdocio

`larkdocio` never tracks who consumes it. Consumers **self-serve** via the
scripts in [`consumers/`](consumers/) (the locked distribution decision:
vendor a built wheel + pin a local-file requirement — no submodules, no
pip-from-git, no copied source). A **downstream clone of a consumer** — which already
vendors the built wheel — needs **no reachable git host** (PyPI only, for transitive
deps). Only *building or refreshing* that wheel reaches the larkdocio repository — the public
one at `https://github.com/mingtc/larkdocio`, over HTTPS, with no credential: its `dist` branch
for the current wheel, its `vX.Y.Z` tags to build any release.

> **New consumer?** The full **zero-knowledge walkthrough** — nothing to know
> beforehand, including wiring the advisory update nag — lives in
> [`consumers/README.md`](consumers/README.md). It assumes no knowledge of this
> repo's internals. The summary below is the same path in brief.

#### One-time onboarding

From a consumer repo root — the onboarding kit comes from a shallow clone of this repository,
which you can delete afterwards (you never read or build from it):

```bash
git clone --depth 1 https://github.com/mingtc/larkdocio.git /tmp/larkdocio
/tmp/larkdocio/consumers/setup-consumer.sh
```

This copies `update_larkdocio.sh` (and the advisory git-hook template) into the
consumer's `scripts/`, installs the skill pack into the consumer's `.claude/skills/`, runs the
refresh script (which builds + vendors the latest
tagged wheel into `./vendor/`), and prints what remains for the human/agent: the
requirement line to pin, the `.env` credential names, and the recommended
update-nag wiring.

#### Refreshing (deliberate, pull-based)

The consumer keeps its own copy of `scripts/update_larkdocio.sh`. Run it to pull
a new wheel (network happens **only** on explicit invocation — never on
`git pull`):

```bash
scripts/update_larkdocio.sh            # latest tag
scripts/update_larkdocio.sh vX.Y.Z     # a specific tag
scripts/update_larkdocio.sh --check    # report-only: is a newer tag available?
```

It first tries the `dist` branch (no build); when that is absent or is not the
version you asked for, it clones the repository in a temp dir, checks out the tag
and builds the wheel. Only after the wheel's version is checked does it copy the
wheel and its documents into `./vendor/` (removing older `larkdocio` wheels), and it
prints the exact requirement line to pin:

```
larkdocio @ file:./vendor/larkdocio-<ver>-py3-none-any.whl
```

Add that line to the consumer's requirements so a fresh clone **of the consumer**
reproduces the environment from the local wheel — **no git host reachable required**
(PyPI only, for transitive deps).

The clone URL lives in **exactly one variable** at the top of
`update_larkdocio.sh`, so a future host migration changes one line of that script. The
project's other links (the package metadata, the READMEs, the changelogs, the CLI's
bug-report line) are typed by hand and must be moved with it.

#### Advisory update nag (optional, never auto-updates)

So a consumer learns a new larkdocio is out **without** having to remember to run
`--check`. The wiring is **advisory only** — it reports, never updates, never
touches `./vendor/`, and never fails the consumer's workflow. Updating stays the
deliberate `update_larkdocio.sh [tag]` above.

**Git hook** — after onboarding, the template sits at
  `scripts/larkdocio-post-merge.hook`. Let git name the destination rather than
  typing it, because `core.hooksPath` may point git somewhere other than
  `.git/hooks` — and a hook left in `.git/hooks` is then **never run**: no
  warning, no error, exit 0.
  `HOOKS="$(git rev-parse --git-path hooks)" && mkdir -p "$HOOKS" && cp scripts/larkdocio-post-merge.hook "$HOOKS/post-merge" && chmod +x "$HOOKS/post-merge"`
  (that primitive answers in every case; `git config --get core.hooksPath` does
  not — it prints nothing and exits 1 when unset). Then prove it with
  `git hook run post-merge`, which resolves the hook the way git does and fails
  loudly when the file is somewhere git does not read (git 2.36+). Worth doing
  once: the nag is quiet when you are up to date, so silence alone is not
  evidence it is wired. A future `git pull` then prints
  `[larkdocio] UPDATE AVAILABLE …` when there is one.

See [`consumers/README.md`](consumers/README.md) for the step-by-step.
