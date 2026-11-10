# tests/captures/ — recorded API responses, with tenant values replaced

Each file here is a response Lark actually returned during a probe or spike, kept as an offline
fixture: the tests read these instead of calling the API. The layout mirrors where each recording
was first made, and a file's own `_provenance` / `_note` fields describe that original recording.

**These copies are not byte-identical to what was recorded.** Two kinds of change were made.
Every placeholder form in these files, and every replaced value, is one of the schemes below. The
**probe-invented** and **kept** lists that follow are not exhaustive: they name the classes of
value left as recorded or invented by a probe, and the cases worth calling out, and no guard
checks them for completeness.

## 1. Redacted when the probe recorded it

Some probes wrote placeholders at capture time, before anything was committed. These are not
reversible and no test depends on the value:

- `<redacted:email>`, `<redacted:person-id>`, `<redacted:person-name>`, `<redacted:en_name>`,
  `<redacted:user_id>`, `<redacted:avatar_url>` / `<redacted:avatar-url>`, `<redacted:chat-id>`,
  `<redacted:chat-name>`,
  `<redacted:shared_url>`, `<redacted:tenant-host>` / `<redacted-tenant-host>`, `<APP_TOKEN>` in a
  recorded path, and a bare `<redacted>` (most often `Bearer <redacted>` in a recorded request
  header).
- `<SECOND-USER-EMAIL-REDACTED>`: another user's address (`name-lookup-spike/batch-get-id/B3`,
  whose request writes it as `<SECOND-USER-EMAIL-REDACTED>@example.com`).
- A probe's own descriptive placeholder for a value it chose not to record:
  `<the LARKDOCIO_GRANT_EMAIL holder's open_id — redacted>` (`ld494-app-space-census/600`, `601`
  and `602`),
  `<redacted — a disposable, deleted in the finally below>` (`base-study/ld497-02`),
  `<REDACTED signed link: len=…, scheme=…, query_keys=…>`, `<NOT CAPTURED — …>`,
  `<binary — hashed, not captured>`, `<omitted>`, `<key omitted>`, `<disposable title>`,
  `<generated>`, `<the table's OWN id>` and `<the id GET just accepted>`.
- `your-domain.larksuite.com`, and a literal `…` where a reporter removed their own host.

Not placeholders, and so not listed above: a path parameter in a recorded request template
(`?version=<token>` in `editions-spike/113`, `<field_id>`, `<target>` in `base-study/ld387-01`,
`<27ch>` in `anchor-links-spike/04`, `{app_token}`), and the
element names of a recorded `.xlsx` (`<sheetData>`, `<cols>`, `<fill>`, `<v>` …).

## 2. Replaced when the copy was committed here

One substitution map was then applied to these files and to the tests together. The same real
value always becomes the same fake in every file, so every equality a test checks across files
still holds. Each token, id and hash fake is derived from the real value under a private key,
so nothing of the real value can be recovered or confirmed from it. People's names and addresses
are different: they are role substitutions, assigned by hand (see "People" below), and they keep
some relations between the originals, such as which two fields carried the same address:

- **27-character Lark tokens** (documents, folders, Bases, blocks, files, wiki nodes) keep their
  length and their lowercase type prefix, if any. Most become `<prefix>Example<hex>`
  (`doxlgExamplee119a78dfb61647`, `Example3a5beaf6a136e401cc42`). A few long-lived objects get a
  named form padded with zeros: `BaseScratchExample000000001`, `BaseConsumerExample00000001`,
  `DocCommentZooExample0000001`, `DocScratchExample0000000001`, `FolderRootExample0000000001`,
  `SheetCommentZooExample00001` and `SheetScratchExample00000001`, and no others. The named forms are not applied to every
  long-lived object:
  another standing scratch Base, for one, has an `Example<hex>` fake like the rest. Outside
  these captures — in the tests, their fixtures and `.env.example` — the same map gives four
  more objects a named form: `DocCanaryExample00000000001`, `DocBlockZooExample000000001`,
  `BaseGoneExample000000000001` and `WikiPageExample000000000001`. Three other named forms
  there replace nothing; a test invented them: `DocProbeExample0000000000001`,
  `DocRealShapeExample00000001` and `SheetRealShapeExample000001`, plus short invented tokens of
  other lengths in the same style, which replace nothing either.
- **A truncated token**, such as a prefix quoted in a note, becomes the same-length prefix of that
  token's fake.
- **User and union ids** (`ou_` / `on_` + 32 hex) become named, zero-padded forms:
  `ou_exampleowner…1`, `ou_examplebot…1`, `ou_examplesecond…1`, `on_exampleunionone…1`,
  `on_exampleuniontwo…1`. (`ou_0000…probe` is a value a probe invented, not a replacement, and
  `ou_examplenullnamed…1` in `tests/offline_doubles.py` is a test's invention.) The
  live tests use the same scheme for an id they read from the environment at run time:
  `ou_examplecontrol…1` (`tests/test_live_contacts_lookup.py`) is the stand-in until the real
  control id is supplied.
- **Numeric Lark ids** of 16–20 digits that name a person or a folder are **counter-assigned**:
  `9`, then a small counter (1, 2, 3 …) zero-padded to the real id's length, so
  `9000000000000000001` for a 19-digit id. Nothing of the real id is in the fake, and the fake
  fits int64 (a typed parser reads it). These are Sheets' `ownerUser`, an @mention's `token`, and
  a Drive folder's numeric `id`.
- **The app id** becomes `cli_example000000001`.
- **Truncated hashes of real values** are replaced too. The Drive walk's pseudonymised tokens
  become `<tok:ex<hex>>`, and every `*app_fingerprint*` value becomes `ex<hex>`.
- **People** become roles (`Example User`, `Example Second User`, `example.user@example.com`). Other
  addresses are on `example.com` / `example.invalid`, and profile photos are
  `https://avatar.example.invalid/photo.png`. One recorded address keeps a subdomain
  (`exampleuser@mail.example.com`, `name-lookup-spike/P6`); the owner's
  `enterprise_email_aliases` list is recorded empty (`name-lookup-spike/reprobe/R8`, `slice2/S1`).
- **A document security-label name** is the example name `Label A` (`drive-spike/06`,
  `base-study/07`), the same one the documentation uses; an unset level stays `""`, which is the
  distinction the classification tests read.
- **The Drive times in `drive-spike/02` and `drive-spike/11`** are rescaled: every time in those
  two files is mapped linearly into [project start, the file's latest stamp], keeping their order
  and scaling their spacing. Some of the objects they list are older than the project. `drive-spike/06` carries
  the real times of objects that pin the map, so the older ones can be computed: the rescale keeps
  the times off the files' face but does not hide them. No test reads an absolute time. Rounding to whole seconds can make two close times equal.
- **Drive titles** from a person's real folder become `Example Folder 01`,
  `Example Document 07`, `example-spec.yaml` and `example-reference.html` (`drive-spike/11`,
  `drive-spike/15`). Every `path` in `drive-spike/11-real-tree-walk.json` is rebuilt from those
  replaced names. Two documents that were already in the app's own Drive root when the probe
  ran are both `Example Pre-existing Document` (`drive-spike/02`). The project's three dogfood Bases in that
  root are `Example Dogfood Base 01` to `03` (`drive-spike/02`, `06`).
- **Document content a person wrote** is replaced. `mermaid-gate-captures/20-*` and `21-*` carry
  a flowchart this project wrote instead. It has the same nodes, edges, decisions, edge labels,
  `<br/>` / `&`, `classDef` and `class` lines, and the same 1,646-byte record as the hand-typed
  original. Every encoding of it was replaced together, along with its `record_sha256_12`: the
  decoded source, the Go-escaped record, the server's unescaped echo, and the error message that
  quotes it. The server's verdict on each row is the one recorded for the original.
- **A downstream user's data**: their row in `ld517-in-cell-link` is a 1×2 table with no header
  row (`header_row: false`) holding `EX-01` and a link with a generic label, in both what was sent
  and what was read back. `base-study/ld497-01` names neither the consumer nor the date or
  version of their report, paraphrases rather than quotes it, and leaves out the counts from their
  own production table; their Base is `BaseConsumerExample00000001`, and the document titles in
  `base-study/ld497-01` to `ld497-03` are `Example Document Title`.
- **Digests of a pre-replacement read.** `base-study/04-determinism.json` recorded the SHA-256 of
  two identical live reads; both now carry the SHA-256 of the text `example spine read`, so the
  equality the probe measured is kept and nothing of the original read is.
- **Synthetic contact data** the probes wrote is in ranges reserved for fiction: the phone
  number is `+12025550100` (the North American 555-0100–0199 block).

## 3. Invented by a probe

A probe sometimes sends a value it made up — to see how Lark answers an id or token that names
nothing, or as a stand-in it never meant to resolve. These were never real, so nothing replaced
them: `ou_0000…probe`, `7667000000000000001` (`comments-probe-captures/05`), `od_ld420_shape_probe`
(`permissions-spike/735`), `zzzz0000ldioprobegroupnope`, `Zzzz0000LdIoProbe…`, `ZZZZbogus0000…ZZ`,
`nodlbrLD387NOSUCHFOLDERxxxxx`, `boxbcnLD435InventedTokenNothingMinted` and
`basNONEXISTENTTOKEN00` (`base-study/03-app-not-found`), and `blkNONEXISTENT` / `wflNONEXISTENT`
(`base-study/p1-q4-03`), `fldZZZnotreal` (`base-study/subitems-b-05`), the sheet id `gh0st1`
(`ghost-tabs-probe/01`), and the temporary block ids `larkdocio_t`, `larkdocio_c0`/`_c1` and
`larkdocio_x0`/`_x1` a descendant create names its own blocks with (`ld517-in-cell-link/001`).
Probes also invent field, key and operator names
the same way: `larkdocioNonsenseFieldXyz` and `zzz_ld420_control`, the name `nope`
(`base-study/p1-q3-01`, `p1-q6-01`), the operator `wibble` and the body key `zzz`
(`base-study/p1-q3-01`), and the key `larkdocio_not_a_real_key` (`base-study/subitems-b-05`,
`subitems-b-06`). They also choose comparison inputs: the
`America/New_York` zone `ld463-date-only/ld463-01` renders each date in beside UTC and the
recorded region's zone.

## 4. Kept as recorded

None of these identifies a person, and none is usable without a token the map replaced:

- table, field, view, record, option and filter-condition ids (`tbl…`, `fld…`, `vew…`, `rec…`,
  `opt…`, `con…`). They name
  rows and columns inside Bases whose app tokens are replaced. Most of those Bases are the
  project's disposable scratch Bases; several are standing Bases, at least one of which a person
  owns and granted the project.
- sheet tab ids, comment and reply ids (numeric), document version and revision ids, `upload_id`
  values, export `ticket` values, page cursors and `client_token` UUIDs. One cursor is replaced
  rather than kept: the directory-search `page_token` in `name-lookup-spike/reprobe/R8` and
  `slice2/S1` is `FP0/Example0…=`, the same length, because it answered a query whose text was
  replaced and a cursor may encode its query.
- request and log ids (`log_id`, `x-tt-logid`, `x-request-id`), error codes and messages, and
  timestamps.
- the SHA-256 digests of the project's own uploaded test files, and Lark's own public values: the
  Mermaid add-on's `blk_…` type id and a helpdesk link inside Lark's error text.
- region and locale facts: an `Asia/Singapore` time zone, `-sg` hosts, an `SGD` currency code
  (`base-study/p0-5-02`), and Lark's Chinese
  default names for a view (`表格视图 1`) and a long-text field (`多行文本`). Also kept is visibly synthetic contact data: an unassignable `+1-000…` mobile
  (`name-lookup-spike/batch-get-id/B5`), and a location at a country's centroid, sent under a
  public landmark's name (`base-study/p0-4-02`) and read back with Lark's geocoded region label
  (`p0-4-04`).
- Lark-assigned ids inside objects whose tokens are replaced, such as a spreadsheet's
  `float_image_id` (`sheets-media-spike`).
- Lark's own masked example id and documentation link inside an error message
  (`permissions-preflight-probe/Q5`); the scope-grant links Lark's denial bodies carry, on
  `open.larksuite.com` with the app id replaced (`permissions-preflight-probe/Q1`, `Q2`, `Q12`,
  `name-lookup-spike/reprobe/R1`); Lark's media download and temporary-link URLs, on the same
  host with the file token replaced (`base-study/p0-4-04`); the public XML namespace URIs inside a recorded `.xlsx`
  (`sheets-dimension-probe/02`, `sheets-write-spike/02b`); Lark's English default names for a
  new Base (`Untitled base`, `Untitled bitable`: `base-study/02-refbase53-app-meta`,
  `ld463-01`); and the link targets the project put in its own test cells
  and documents (`www.google.com`, `www.larksuite.com` and `open.larksuite.com` pages).
- the names of the project's own disposable test documents, and the generic file names
  (`final_test.txt`, `test_data.json`, `test_document.txt`) already in the app's Drive root.

A note inside a capture that says "nothing else is altered", "verbatim" or "unmodified" describes
the original recording, not this copy. The schemes above apply to every file here.
