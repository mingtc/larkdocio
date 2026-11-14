# Release notes — larkdocio

What changed **that affects you**, release by release. Written for someone who consumes
larkdocio as a vendored wheel and wants to know, before re-vendoring, what moved under them.

**This file is deliberately distinct from `CHANGELOG.md`.** `CHANGELOG.md` records what changed
in each release. These notes are the filtered view: only what a consumer can observe, install,
call, or be broken by. Neither file replaces the other.

**INCLUDE — apply these criteria, do not re-derive them:**

- **Public symbols and CLI flags** — a public symbol added, renamed, or removed; a new CLI
  flag, a changed flag default, a changed command name.
- **Observable behavior changes** — anything that makes the output, the return shape, or the
  failure mode differ for the same input. A change to rendered Markdown is always an
  observable behavior change, even when it is a fix.
- **New or changed refusals and disclosures** — a new or renamed refusal code, a refusal that
  now fires earlier or later, a new preview note, and any new field on a plan or an apply
  log. These are the disclosures a caller reads programmatically, so a rename is a break.
- **Credential and scope requirements** — a capability that needs a credential or an API
  scope you may not have granted yet.
- **Dependency adds and pin moves** — every dependency added or dropped, and every pin move,
  runtime or otherwise. Dependencies are pinned exactly, and every move is announced here.
- **Known limitations** — what still does not work, what is deliberately refused, and what
  costs more than it looks like it should.

**EXCLUDE — if it is one of these, it does not belong here:**

- **Internal refactors** — module splits, extracted functions, shared cores. If the
  observable surface did not move, the reorganization is not news.
- **Test, build, and process work** — test counts, new guards, coverage or mutation numbers,
  continuous-integration wiring, board mechanics, and any other process work.
- **Issue ids and design-record ids** — they resolve only inside the development
  repository, so quoting one tells a consumer nothing. State what changed and why instead.
- **Role names and internal labels** — a role name, a work-wave label, or a tranche or
  ladder name describes how we organized the work, not what you need to do.
- **How a defect came to light** — who met it, what was said about it, or how many runs it
  took. Describe the fix by what changed: *"X now refuses Y"*.

**The shape of a section.** Each release is `## [X.Y.Z] — YYYY-MM-DD`. Through 1.50.0 it is
followed by exactly four subsections, always in this order: **New capabilities** · **Behavior
changes you can observe** · **Upgrade & compatibility** · **Known limitations**, and a
subsection with nothing to say is written `None.` rather than omitted. From 1.51.0 on, every
section has **What a caller can observe** and **Upgrade & compatibility**; a **Changed**, **New
capabilities** or **Known limitations** subsection, or one headed by the single kind of change
it holds, appears only when there is something to put under it. In both shapes **Upgrade &
compatibility carries every dependency add and pin move** — including an explicit "no
dependency moved", because otherwise a reader cannot tell that from nobody having checked.

**When a section is written.** At the **cut**, by whoever cuts the release, applying the
criteria above. The maintainers' release tooling refuses to tag a version that has no section
here — and, with a separate refusal, none in `CHANGELOG.md` — so these notes cannot quietly
fall behind the tags.

**Whose the date is.** A section's **date belongs to the cutter**, set at the cut, and it is
the day the release was cut. Until then the topmost section is **un-cut**: its
date is a **placeholder with no authority**, it may be days or weeks older than the newest
work described beneath it, and **nothing landing into an un-cut section edits that date**.
This is enforced rather than promised — the release tooling refuses to tag a section whose
header date is **earlier** than the newest date written inside that same section, naming both
dates, because a release dated before the changes it contains is a date nobody can use. So:
read the topmost section for **what** changed; read a **cut** section's date for **when**.

**Where the history starts.** These notes begin at **1.14.0**, the span across which a
consumer had to reconstruct dependency and behavior changes out of the internal log. Changes
before 1.14.0 are recorded only in the maintainers' engineering log, which is not published.

> **This copy carries a WINDOW of the newest 8 releases, not the whole history.** Everything
> below this line is verbatim — 1.48.0 up to 1.53.2 — and the releases older than 1.48.0,
> 1.47.0 and down, ship with the publishing repository instead of inside the wheel. That is
> deliberate: the reader this copy exists for is deciding whether to re-pin, and a full
> history costs them every release they can no longer act on before it reaches the one they
> can.
>
> The full history is at `vendor/larkdocio-RELEASE_NOTES.md`, which the consumer refresh
> script drops beside the vendored wheel on every refresh, and the publishing repository's own
> complete copy of this document at its root.
>
> `larkdocio.release_notes(section=...)` refuses a release older than the window by name and
> repeats those addresses; `larkdocio.release_notes_sections()` lists the 8 releases this copy
> carries.

## [1.53.2] — 2026-11-14

### What a caller can observe

- **No pointer you cannot follow.** The `evidence` strings carried by refusals, loss previews,
  error-code notes, permission rows and `capabilities()`, and the library's docstrings, comments
  and packaged documents, used to point at files in the maintainers' private working repository,
  which neither the wheel nor the public repository carries. Those pointers are gone. Where a
  sentence stood on its own, the pointer was dropped; where it carried evidence, the fact is
  stated, a published recording is cited instead (a `tests/captures/…` path, in the source
  repository), or the text says the recording is unpublished. No fact
  changed and nothing a call does changed. If you match an `evidence` string by exact text,
  re-check it; the permissions section of the guide changed with them.
- **A correction to the 1.53.1 notes.** They say "This release changes no code that ships in the
  wheel." That was not exact. In 1.53.1 one message string in `guide.py` changed — the text
  `changelog()` shows read "The same text is at" and now reads "The same entries are at" — one
  sentence of the shipped guide changed (the release-notes drop "holds every section from
  1.14.0"), and one comment changed. No behaviour changed.
- **Release dates.** A section's date is the day the release was cut. The public tag can follow
  the cut: v1.53.0 and v1.53.1 were tagged on the public repository three days after their cut
  dates. From 1.53.2 on, the public release commit and its tag carry the cut's time, in UTC
  (`+0000`), whenever they are pushed.

### Upgrade & compatibility

- No dependency was added, dropped or moved. Upgrading from 1.53.1 changes nothing you call.

## [1.53.1] — 2026-11-10

### What a caller can observe

- **Nothing a call does changed.** This release changes no code that ships in the wheel.
- **The test suite passes at this version.** At 1.53.0, one test in a source checkout failed:
  it pinned an example naming the release's own version, which a separate check refuses once
  that version is the installed one. The example is version-neutral now.
- **A correction to the 1.53.0 notes.** Their entry on the import-time warning record says the
  test suite runs green on Python 3.11 through 3.14. At the 1.53.0 tag it did not, on any of
  them: the one failure above was red on every interpreter. It is fixed in 1.53.1.
- **The README's refresh example names a placeholder tag.** `scripts/update_larkdocio.sh
  vX.Y.Z` stands for any release tag; substitute the one you want.

### Upgrade & compatibility

- No dependency was added, dropped or moved. Upgrading from 1.53.0 changes nothing you call.

## [1.53.0] — 2026-11-08

### Changed

- **The guide and `capabilities()` no longer call the shipped changelog the "full engineering
  log".** It is the project's changelog, one entry per release, pointing at these notes for the
  detail. If you match `capabilities(full=True)`'s `changelog` summary by exact text, re-check it.

- **Install and refresh from the public repository, over HTTPS.** larkdocio's public
  repository is its release home: every release from this one on is a `vX.Y.Z` tag there and its `dist` branch
  carries the current wheel. The consumer refresh script's default URL is now
  `https://github.com/mingtc/larkdocio.git`, so no git credential is needed; set
  `LARKDOCIO_REPO_URL` to use a mirror. Re-copy `update_larkdocio.sh` from the consumer kit over
  your `scripts/update_larkdocio.sh` to pick this up.
- **A refused refresh leaves `./vendor/` exactly as it was.** The refresh script used to copy the
  new tag's four documents into `./vendor/` before building, so a build failure or a version
  refusal left your old wheel beside the new tag's documents. It now vendors the wheel and the
  documents together, after every check passes. A `dist` branch that carries more than one wheel
  is refused rather than chosen from by sort order; the script then builds from the tag.
- **The skill pack's version stamp is written when you copy it.** `install-skills.sh` stamps each
  copied router with the larkdocio version it was copied from and the date, so a re-copy is never
  stamped with an old version.
- **Evidence paths for recorded API responses now name a copy you can open.** Where a refusal,
  loss preview or guide sentence cites a recorded response, the path now names a copy that is
  in the source repository, under `tests/captures/`, which a clone of the public repository
  has; the label beside it says so (see below). The wheel still does not include it.

- **Examples and recorded test data use placeholder values.** The guide, docstrings, some
  messages and `capabilities()` texts, and a few sentences in earlier sections of these notes
  read accordingly. Nothing a call does changed; if you match a message by exact text, re-check
  it.
- **Some entries in earlier sections of these notes were reworded for clarity.** They now
  describe each fix by what changed, and nothing else. Nothing a call does changed.
- **The `html` refusal's recovery text has a new example.** Its sample of bracketed prose that
  parses as an open tag is now `Lorem <ipsum dolor>`. The construct, the reason code and the
  repair (escape the bracket, or write `&lt;`) are unchanged, and so is what refuses: a
  well-formed open tag. If you match that message by exact text, re-check it. The guide's
  matching examples, and the same sentence in the 1.37.0 section below, read the same way.
- **`larkdocio.changelog()` now returns the project's public changelog.** It has one entry per
  release from 1.52.0 on and is far shorter than the document it replaces: for the user-facing
  changes of earlier releases, read these notes, which go back to 1.14.0. If you read old
  releases with `changelog(section=...)`, use `release_notes(section=...)` instead — the
  changelog refuses a release it does not record and says so. The `capabilities()` summary for
  `changelog()` changed with it, and the shipped copy's opening note says when it carries every
  release rather than a window. These notes' own introduction no longer names
  maintainer-only scripts.

- **A path labelled "(in the dev repo)" that points into the maintainers' evidence records is a
  note, not a file you can open.** The sentence carrying it already states the fact; the path points at the maintainers'
  own records, which the public repository does not carry. Nothing you call changes.
- **A citation of a file any clone carries now says "(in the source repository)".** A recorded
  API response under `tests/captures/`, a root matrix such as `BASE.md`, or a test is in any
  clone of the public repository, so the label now tells you that you can open it; "(in the dev
  repo)" is reserved for the maintainers' private records. This holds across the library's own
  text — `evidence` in refusals and loss previews, the `capabilities()` registry, the guide,
  docstrings and the root capability matrices. In the sections of these notes for earlier releases
  the labels keep the wording they were released with. If you match an `evidence` string by exact text,
  re-check it.
- **The guide's first routing table no longer calls a Base or a Drive folder read-only.** Its
  Base row names record writes and schema writes and their recipes; its folder row points at
  Drive's write legs.
- **The Drive read surface's note names every Drive write surface.** In
  `capabilities(full=True)`, the `drive-read` note said the Drive family had exactly one write
  surface and that no sharing call existed, while `drive-access-write` grants, changes and
  revokes a named person's access. The note now names the four Drive write surfaces and what
  each does. If you match that note by exact text, re-check it.
- **`update_larkdocio.sh` logs a shorter note when a tag lacks one of the vendored documents**
  (the trailing "a tag older than …" clause is gone); the run still succeeds as before.
- **The consumer kit's optional CI include is gone.** It depended on one hosting service's CI. If you copied
  it, your copy keeps working; for an update reminder use the `post-merge` git hook the consumer
  walkthrough describes, which works everywhere. Nothing in the library changes.

- **larkdocio is licensed under the Apache License 2.0.** The wheel and sdist now carry the
  `LICENSE` file, and package metadata reads `License-Expression: Apache-2.0` instead of
  `Proprietary`. Building from source needs `setuptools` 77 or newer (pip fetches it for you in
  an isolated build). Nothing you call changes.

- **The package's `Author` metadata is now `mingtc`.** It carried a placeholder. Nothing you
  call changes.

### What a caller can observe

- **Evidence notes no longer point at files that do not exist.** Refusal messages, preview
  notes, the `capabilities()` absence register, the guide's permissions tables and docstrings cite
  the project's own recorded measurements as provenance. A number of those recordings were
  retired from the maintainers' records, so their citations led nowhere. Each one now either
  points at a recording that is still kept or says the recording was retired, and states the
  measured fact itself. **The facts did not change** — only where the text sends you to verify
  them. Two messages you may read programmatically changed wording: the note on a border-style
  write plan no longer names a probe script (it still tells you to read the exported workbook's
  `xl/styles.xml` or check the Lark UI), and the refusal for an empty Drive folder name now cites
  the one recording that survives. If you match either message by exact text, re-check it.

- **The console link in `larkdocio.permissions.OBSERVED_DENIALS` no longer names a specific
  Lark app.** The `directory:employee:search` denial's `help_url` now reads
  `https://open.larksuite.com/app/<your-app-id>/auth?q=directory:employee:search&…` — put your
  own application id where `<your-app-id>` is. It used to carry a concrete app id: the
  maintainers' own app, the one the denial was captured with, so following it led to a console
  page for an app that is not yours. The
  scope, the query string and the host did not change. A console link Lark returns **at run
  time**, inside a refusal, is unaffected: that one is Lark's, and it names your app.

- **A retired output key from earlier versions is no longer accepted.** The `config.json`
  `output` key that switched off the output-relocating derivation removed in 1.49.0 was accepted
  and ignored, with a warning, through 1.52.0. It is now an unknown key like any other: passed
  to `OutputConfig(...)` as a keyword it raises `TypeError`; passed as a fifth positional
  argument it raises `TypeError` too, instead of landing on `download_attachments` — every field
  after `skip_img_download` is now keyword-only; and in `config.json`'s `output` object it is
  ignored, without a warning, as every unknown key is. Remove it from both. If you want output
  placed somewhere derived, pass `--route <subpath>` (or `route=` to `handle_download_command`).

- **What 1.52.0 shipped, said plainly, because the 1.52.0 section keeps the wording it was
  released with on this point.** In **1.52.0** the warning for that key named **1.51.0** — a release you were already
  past — so it read as though the key had already been removed, in the very release where it was
  still being accepted and ignored. It was accepted and ignored throughout 1.52.0; the sentence
  was wrong, and your calls were not affected.

- **Examples generalised.** Earlier sections of these notes, the guide and the reference
  documents now state their examples in general terms. No behaviour is described differently. The `--route` help and its refusal
  messages now give `area/section/topic` as the example subpath; if you match a refusal by
  exact text, re-check it.

- **Two claims in `larkdocio --help` are corrected.** It now says hidden columns on a Base view
  are settable (it said hidden fields were not offered), and names the files leg's byte round
  trip beside the other Drive write legs' verification. If you match the help by exact text,
  re-check it.
- **The consumer kit's text is corrected.** `consumers/README.md` says comments can be created
  and removed (an unanchored comment on a docx) where it said no comment write ships; the
  refresh script and hook say `--check` can make a second remote query (for the `dist` branch)
  when an update is available; and no example names a tag older than v1.53.0, the first public
  release.

- **The import-time warning record was wrong for Python 3.12 and 3.13, and is corrected.** The
  1.44.0 section of these notes and the README said `import larkdocio` emits exactly one
  `DeprecationWarning` on Python 3.12 and newer. That holds on 3.14 only. On 3.12 and 3.13 the
  import also shows deprecations raised by `lark-oapi`'s websocket client
  (`lark_oapi/ws/client.py`) and by the `websockets` library it imports, and on 3.11 only
  those, since the vendored-protobuf one needs 3.12. None of them comes from larkdocio and
  nothing here suppresses them; the README's dependency section now says so per version.
  Nothing a call does changed. The test suite also runs green on Python 3.11 through 3.14 now;
  it was red on 3.13 and older.

### Upgrade & compatibility

- **The supported Python floor is now 3.11** (`Requires-Python: >=3.11`; it read `>=3.10`). The
  test suite has always needed 3.11, so 3.10 was declared but never tested; rather than add 3.10
  testing, the declared floor now matches the tested one. On Python 3.10, pip refuses to install
  this release; use Python 3.11 or newer.
- **No runtime dependency was added, dropped, or re-pinned in this release.** Building from
  source now needs `setuptools` 77 or newer (for the `License-Expression` metadata); pip fetches
  it for you in an isolated build.
- **One thing you pass can stop working: the retired output key** (see above). Passing it to
  `OutputConfig(...)` — as a keyword, or as a fifth positional argument — now raises
  `TypeError`; in `config.json` it is silently ignored. Nothing else you pass stops working: no
  other public symbol, CLI flag or return shape moved. Three behaviours changed, each described
  above: the consumer refresh script's **default URL** is the public repository over HTTPS; the
  refresh script **refuses** a `dist` branch carrying more than one wheel and builds from the tag
  instead; and `changelog(section=...)` **refuses** a release the public changelog does not
  record, pointing you at `release_notes(section=...)`. Every other change in this release is to
  **text** a caller reads — warnings, help, a documented console link, and evidence notes — and
  none of them changes what a call does.

## [1.52.0] — 2026-09-09

### What a caller can observe

- **`DownloadResult` gains `unknown_block_types` — the block types a document used that this
  library does not model, as data, so nothing has to parse a warning to find out.** A list, one
  entry per **distinct** unmodelled type in first-seen order, each answering four integer keys:
  `block_type` (the type, as Lark numbers it), `count` (how many blocks of it the document
  carried), `containers` (how many of those carried children — whose subtree is surfaced anyway,
  at the unknown block's own depth) and `children` (how many child blocks those containers
  preserved). `count - containers` is how many were **leaves**, and a leaf of an unmodelled type
  contributes nothing to the Markdown. **The key is on every successful download and is `[]` when
  nothing was lost**, so "nothing unmodelled" and "key missing" are never the same reading — the
  discipline `dump_path` already follows. **No block ids ride along, deliberately**: the answer is
  meant to grow with a document's vocabulary rather than with the document, and per-block detail
  is still in the warning and in the `--dump` sidecar's raw payload.

- **The `Unknown block type <N> (block_id=…)` warning is UNCHANGED and stays frozen.** It fires
  exactly as before, byte for byte, and both it and the new key are written by the same recorder,
  so they cannot disagree about what a document lost. If you parse that line today, `result
  .unknown_block_types` is what replaces the parse — and this release deliberately does **not**
  free the text. It will change only in a **later release that names the change in its own
  section**, so you can move at your own pace and retire the parse when you choose, not when a
  release surprises you. (Where to read the new key: `result.unknown_block_types`, or
  `result["unknown_block_types"]` — the value is the same `list` either way.)

- **A rejected App ID / App Secret is now a refusal you can act on, on every command — stated
  as the RULE, because a per-command list here would be wrong by the time you read it.** You
  get it on both of the ways larkdocio mints a tenant token, so whichever transport the failing
  call was using, a wrong credential exits non-zero with one `Error:` line saying it is a
  credential problem, naming the variables to fix and the `.env` that was read. 1.51.0 covered
  one of the two ways and said so in its own section; that half is what this release finishes.
  **The authoritative, per-surface answer is not in this file**: it lives in the library, on
  `larkdocio.cli`'s command class, where a test holds it **set-equal** to a probe that runs each
  surface's real client against both mint paths and asks the shipped seam what a consumer would
  be told. This note states the rule and names no list precisely because earlier drafts named a
  list and were wrong twice, once too widely and once too narrowly.

- **Which surfaces change for you: `larkdocio folder`, `roundtrip`'s `push` phase, the
  spreadsheet clients and `preflight`.** On a rejected pair they used to print a bare traceback
  — and `folder` printed **zero bytes** — with no `Error:` line and no indication which of the
  two credential pairs was at fault. They now give the same refusal and the same guidance the
  reader has given since 1.51.0, and they can be **more** precise about it: where the failing
  call used one specific pair, the refusal names that pair (a `push` failure names
  `LARK_WRITE_APP_*`, a read names the read pair in force) instead of offering you both. On
  `roundtrip push --apply` the old answer was worse than a traceback: the rejected credential
  was reported as document **drift** (*0 of 1 entries applied; 1 refused (stale-document)*),
  advising a re-read and re-plan that could not have helped. **None of this was a regression** —
  every one of those surfaces behaved that way in every release up to this one, and nothing
  here removed a message you used to get.

- **Nothing else.** Apart from the new result key above, every other line this release changed
  is a test or a comment inside the project's own repository. It is recorded here because these
  notes are a continuous record of releases, not only of behaviour — if a section were skipped, a
  reader could not tell "nothing changed for you" from "nobody wrote it down".

What else changed is the project's own safety net. Four checks whose names promised a stronger
property than they actually verified can now fail: a check named for exact bytes that compared
folded text and could not see a line that had *gained* a suffix; a check that forbade a stale
version string but looked only in the test tree, never in the shipped package; a
retirement-window check that every release satisfied automatically, so the window could be
extended indefinitely without anyone deciding to; and a check whose two assertions were true of
every value it could ever be given. Each correction was verified by breaking the code in the
exact way the old form survived.

None of that is visible from the outside, which is the point of saying so plainly. The
engineering detail is in the internal log.

### Upgrade & compatibility

- **Nothing to do.** No dependency was added, removed or repinned. No config key moved. The one
  public name added is `DownloadResult`'s `unknown_block_types` key, which is **additive** — every
  key the result already answered is still there, unchanged, and code that never reads the new one
  is unaffected. No message you already relied on changed
  text — what changed is that four surfaces which used to raise an untyped error on a rejected
  credential now refuse in words. The refusal goes to **stderr**, like every other line this
  CLI says *about* a run; **stdout** still carries only a command's product, unchanged. So if
  you detect this case by scraping for a `tenant_access_token` traceback, match the `Error:`
  line instead — and if you catch exceptions from the library, the class is unchanged
  (`LarkAPIError`), so nothing you catch stops being caught.

## [1.51.0] — 2026-09-09

### What a caller can observe

**One behaviour change stands above the rest: what you are told to do when Lark refuses a
document read.**

- **A long-titled document's output filename can now differ, and two documents that used to
  collapse into one file no longer do.** A document title longer than the filename budget is
  cut, and until now two documents whose titles first differed **past** that cut produced the
  same filename — the second download overwriting the first, with no error and no message. That
  is fixed, and the fix is visible in the name: **when, and only when, the title is cut**, the
  document's own token joins it —

  ```text
  [2026-09-09_1200]_<cut title>_<doc token>.md      # larkdocio download
  <cut folder name>_<root token>.md                 # larkdocio folder
  ```

  **A title short enough to fit is untouched** — the overwhelming majority of names do not move.
  If you key on the old `[stamp]_<title>.md` shape, the cut case is the one to handle, and
  `DownloadResult.disambiguated` tells you when it happened without your having to parse the
  name. Re-downloading the **same** document into the same directory still overwrites its own
  file rather than accumulating copies.

- **`DownloadResult` gains `replaced_existing`.** It is `True` when a file already existed at
  `output_path` and this download replaced it. **This is a disclosure, not a fault**: two
  documents can legitimately share a title, and re-downloading the same document into the same
  directory within the same clock minute lands on the same name by design and reports `True` as
  well. A filename cannot answer *"is this the same document?"*, so neither can this field —
  what it answers is *did this download replace bytes?*, which previously had no answer at all.
  The `folder` verb discloses the same fact in its log; it returns `None`, so it has nowhere
  else to put it. **If you were relying on the old silence, this is the signal to key on.**

  Scope, stated rather than implied: this is about **length** and about a **collision**. It
  settles nothing about Windows — `NAME_MAX` there is a third unit again (UTF-16 code units) —
  it makes no claim that this library or its suite is Windows-clean, and the one filesystem
  constant it uses (255 **bytes**) is treated as bytes on every platform because
  `os.pathconf(..., "PC_NAME_MAX")` returns the same 255 on macOS/APFS while meaning
  *characters* there. One number, two units; the constant is the conservative reading and
  nothing beyond that is settled.

- **A permission error is no longer reported as an IP block.** The IP-allowlist branch tested
  for the substrings `ip` and `denied` and ran before the typed permission check. A Lark
  document token is 22-24 base62 characters, so about 2.15% of them contain a case-insensitive
  `ip` (measured over 200,000 synthetic tokens, roughly doubled for a wiki url whose refusal
  text carries two tokens), and Lark's denial message supplies the `denied`. If you hit that,
  you were sent to add your IP to an allowlist when the fix was **Share → Add Application**. If
  you relay our refusal text to your own users, this is the line that changes.
  **The false positives were not only permission errors, either.** Because the old test ran
  before any typed check and looked only at message text, *any* failure whose text happened to
  contain `ip` and `denied` was reported as an IP block — a real filesystem `PermissionError` on
  an output path containing the word `clips` did it, verified by execution. Those now reach the
  handler they belong to.

- **A SCOPE denial now tells you the scope.** When Lark refuses because the app lacks a
  permission, the library was already holding a record naming the exact missing scope, which
  credential pair made the call, and Lark's own console link — and printed none of it, offering
  the Share dialog instead, which does not grant a scope. It now prints that record, and says
  that **a grant takes effect when you RELEASE a new app version, not when you save it**. The
  refusal line for this case is new: `Download failed: missing app permission — see the guidance
  above.` The existing `Download failed: missing document permissions …` line is unchanged and
  still fires for the case that really is a sharing problem.

- **Lark's own answer is now logged on EVERY arm of that router**, ahead of our advice. It used
  to be dropped on the two arms that offered a remedy, so you saw the remedy and never the
  refusal it was a remedy for. That includes the IP-allowlist arm, which — now that the typed
  check runs first — only ever fires on what the typed check declined, and is therefore the arm
  where Lark's own words are worth the most. **The advice lines themselves are unchanged, and so
  is their order**; one line is added above them.

- **A mistyped URL, a wrong App Secret, and an OS error are refusals now, not tracebacks — on
  every subcommand.** A mistyped download url printed its refusal and then a bug-report banner
  and a ~45-line traceback; `larkdocio folder <bad url>` printed a bare traceback with no
  refusal line at all. Both now exit non-zero with one `Error:` line. A wrong App ID or App
  Secret — previously a traceback labelled a possible bug — now says it is a credential problem
  and names the credential variables to check and the `.env` that was read. An OS error refuses
  with a line saying it may be about your path or may be ours, and names `LOG_LEVEL=DEBUG` for
  the traceback.

- **Which commands the credential guidance reaches — stated as the RULE, because a per-command
  list here would be wrong by the time you read it.** larkdocio mints a tenant token two
  different ways, and the guidance covers one of them: **you get it wherever the token is minted
  through the Lark SDK, and you do not get it where the token is minted over plain HTTP** — there
  a rejected app pair still surfaces as an uncaught error with no guidance and no `Error:` line.
  `larkdocio download` and `roundtrip`'s `pull` phase are on the covered path; `larkdocio folder`
  and `roundtrip`'s `push` phase are not. **The authoritative, per-surface answer is not in this
  file**: it lives in the library, on `larkdocio.cli`'s command class, where a test measures it
  by running each surface against both mint paths — this note names the rule and not a list
  precisely because earlier drafts of it named a list and were wrong twice, once too widely and
  once too narrowly. **This is not a regression**: the uncovered path behaves exactly as it did
  in previous releases on every command, and nothing here removed a message you used to get —
  this release adds the guidance on the SDK path and leaves the other as it was. Closing the gap
  is filed as its own change, because it alters how several modules report an error.
  **Superseded in 1.52.0 — see that section.** The sentence above describes the wheel
  you are reading it in and stays as it was published; the second mint path is covered
  from 1.52.0 on.

- **`larkdocio guide` and `--help` work when redirected on Windows.** With no output encoding
  set, a redirected stdout got the active code page: measured across four code pages, `guide`
  exited 1 having written **0 bytes**, and the root `--help` also failed on two of them. The CLI
  now writes utf-8 regardless of locale. A real console was always fine; this is the redirect.

- **`--route` can no longer write outside `-o`.** The navigation-segment check ran before the
  path sanitiser, and the sanitiser manufactured `..` by stripping reserved characters:
  `--route '.?./.?./escaped'` produced `<out>/../../escaped` and created it. Those inputs are
  refused now. If you were relying on one, it was writing somewhere you did not ask for.

**Four more places the library gave you a wrong answer without saying so. Three of them change
what you can observe, and one of those changes a filename.**

- **A long Chinese, Japanese or Korean document title no longer fails the download.** The output
  filename was shortened by counting **characters** (100 of them) against a filesystem limit
  measured in **bytes** (255). A CJK character is 3 bytes in utf-8, so a title of 79 or more of
  them produced a name too long to write, and the download failed **after** the fetch had
  succeeded — you paid for it and got nothing. The budget is now in bytes, cut on a whole
  character. **What you can observe:** such a title now writes, shortened; an ASCII title's
  filename is **byte-identical to what you got before** — the character limit is still there
  underneath. If a name you were shortened to is longer than about 74 CJK characters, it will now
  be shorter than the crash length rather than being a crash.
  **Two documents can still land on ONE filename.** If two titles share the shortened prefix and
  you download them into the same directory within the same minute, the second overwrites the
  first, with nothing said. That was true before this release too — at the character cut — and it
  is not what this change fixed. If your titles are long and share prefixes, download to separate
  directories or turn the title-based name off (`title_as_filename: false`).

- **`--route` refuses a segment there is nothing left of.** `--route '***'` used to write to
  `<out>/untitled/` — a directory you never named — because the path sanitiser substitutes
  `untitled` for a name that strips to nothing. Now it refuses and names the segment. A segment
  you really typed as `untitled` still works. A document **title** that strips to nothing still
  gets a name (the file is named after the document token, as before), and the substitution is
  now announced in the log rather than happening in silence.

- **A Mermaid label carrying a line break is now refused instead of corrupting the diagram.**
  The compiled source is line-oriented — one node, one edge, one message, one comment per line —
  so a `\n` inside a label ended that statement and everything after it was read as diagram
  syntax: a label of `Start` + newline + `flowchart LR` compiled to a valid-looking diagram with a
  **second declaration in it**. Every string that reaches the source is now refused if it carries
  a control character (the C0 controls including tab, `DEL`, `NEL`, and the Unicode line and
  paragraph separators), naming the codepoint and which construct it was in: node, subgraph and
  edge labels, participant aliases, message text, and the diagram `title` that becomes a comment.
  **Nothing is substituted, and `<br/>` is not the escape hatch it looks like** — this dialect has
  no safe line-break substitute, and a `<br/>` you write yourself is stripped by the no-HTML rule,
  so inserting one for you would answer the same request two different ways. Shorten the text, or
  split the construct in two. **What you can observe:** a spec that used to compile now raises,
  and a spec that compiled correctly is byte-identical.

- **A Base date read on a machine with no time-zone database now says so.** Rendering a Base's
  declared zone needs a tz database; a slim container, or Windows without the `tzdata` package,
  has none. The read fell back to `UTC` — and reported the zone it had been **asked** for, so
  every date was converted in the wrong zone and nothing said so. **The shape of the disclosure,
  because you may be keying on the old one:** on such a machine `date_zone` is now `'UTC'` (it
  used to be the declared zone), `date_zone_assumed` is now `True` (it used to be `False`), the
  new `date_zone_requested` names the zone that could not be loaded (`None` in every other case),
  and `date_zone_disclosure` carries a sentence telling you to install the tz database on that
  machine. A Base that declares no zone, and one whose zone loads, answer exactly as they did
  before. The rendered Markdown is unchanged either way — this is provenance on the result
  object, never a marker in the output. **No dependency was added for this**: whether `tzdata`
  becomes a requirement is a separate decision, and disclosing the fallback is right either way.

- **A deprecation notice stops accusing you of setting a key you never set.** Making a copy of
  an `OutputConfig` with `dataclasses.replace()` (or `copy.replace()`) re-passes every field for
  you, including the retired output-config key, so the notice told you to drop a key that was
  nowhere in your call. It now says what the call looked like and that there is nothing for you
  to fix. Two smaller things with it: the copy no longer resets that field to its default, and a
  call in which you really did name the key reads exactly as before.

### Text corrections — not behaviour

These change what you READ, not what the library does:

- The invalid-url refusal no longer denies that the folder read exists. It has existed since
  the release that added `larkdocio folder`; the copy that renders was never corrected.
- Two refusals no longer refer you to a Readme/Release section that does not exist.
- The retired output-config key's deprecation notice named a release older than the one you
  were running. **Two things are true here and they were run together in an earlier draft of
  this note, so they are separated now.** (1) **The BEHAVIOUR is unchanged**: the key is still
  accepted and ignored, at all four doors, exactly as before — no code path moved. (2) **The
  announced REMOVAL DEADLINE has moved, and that is a thing to plan around**: the notice used to
  say the key was tolerated in 1.49.0 and removed in the release after it, and the removal did
  not happen; it now names **1.51.0**, so the removal is announced for the release after this
  one. If you were working to the old deadline you have gained two releases — and if you still
  pass the key, that is the window you have left. A guard now holds the notice to the running
  version, so it cannot silently name a release you are past again.
- The README's dependency-pin policy no longer reads as a promise about the whole dependency
  closure. It never was one: our own requirements are pinned exactly, their dependencies carry
  whatever their authors chose, and several carry nothing. If you need the closure reproducible,
  that is a lockfile in your project. **No pin moved in this release.**
- The install path now says the **tag is authoritative** when it disagrees with the `dist`
  branch. `dist` carries only the current release and is republished on each cut, so between
  the tag and the republish it serves the previous release's wheel.

### Running on a host whose locale is not UTF-8

**On a UTF-8 host — macOS, and any Linux with a UTF-8 locale — nothing in this section changes
anything you can observe.** It is here for the other case.

- **The permission-coverage machinery stops crashing on a non-UTF-8 host.** One shipped helper
  read this package's own `.py` sources with the **host locale** codec rather than UTF-8. On a
  Windows default (cp1252/cp932/cp936) that either raised `UnicodeDecodeError` on the shipped
  files that are not cp1252-decodable, or silently decoded the rest to mojibake — and the guard
  around it caught only `OSError`, so the decode failure escaped as a traceback. It now reads
  UTF-8 explicitly, on every host. If you never saw this, that is because your locale was
  already UTF-8; there is nothing to do either way.
- **The `.env` bootstrap file is written as UTF-8.** This is hardening, not a fix: the template
  it writes is pure ASCII, so no locale could have mangled it. Nothing about the file you get
  changes.
- **What is NOT claimed.** This does not make the test suite — or the library as a whole — pass
  on Windows. Other Windows-specific concerns (path separators, line-ending translation) are
  untouched by this release, and the rest of the work behind this note was in the project's own
  test suite, which ships in no wheel and changes nothing a caller can observe.

### Upgrade & compatibility

- **Nothing to do.** No dependency was added, removed or repinned. No config key moved. One
  public addition, no removals and no renames: Base read results carry a new
  `date_zone_requested` alongside the three zone keys they already had.
- **Two things can newly RAISE where they used to return**, both of them cases that produced a
  wrong answer before: a Mermaid spec whose label or title carries a control character, and a
  `--route` segment that the path sanitiser would leave nothing of. Both raise the library's
  ordinary configuration error, and from the CLI both are a clean non-zero exit with one
  `Error:` line.
- **One filename shape can differ**, for CJK titles only, and only where the download used to
  fail: see the byte-budget note above.
- **If you parse our log stream**, read the new lines above: the scope-denial banner and its
  refusal line are new text, the credential-rejection banner and its refusal line are new text,
  and Lark's own message now precedes the advice on every arm of the reader's error router.
  Every pre-existing advice line keeps its bytes and its relative order — the additions are
  above them, never in place of them.
  (Unchanged, and worth restating: every log line goes to **stderr**, and **stdout** carries
  only a command's own output.)
- **If you handled a traceback from a mistyped url or bad credentials**, you now get a clean
  non-zero exit with one `Error:` line instead.
- This package now declares project urls, so `pip show larkdocio` carries a Source and an
  Issues url.
- **A link URL you copied out of a browser gets a straight answer instead of a loop.** If you
  authored a `TextSpan` with `link_url="https://…/a%20b"`, the refusal told you to pass
  `https://…/a b` instead — and passing that was refused too, for carrying whitespace, whose
  advice pointed back at the encoded spelling. Neither message ever said the thing you needed to
  know. Now both of them do: **when a URL's decoded spelling contains whitespace, no spelling of
  it can be authored as a link anchor**, and the refusal names the two things that do work —
  link to a space-free URL for the same resource (a redirect, or a shortened URL), or author the
  URL as plain text rather than as an anchor. The same sentence appears whichever spelling you
  arrived with, because either one can be the door you came in through.

  **Nothing you could author before is refused now, and nothing that was refused is accepted** —
  the refusal set does not move; only what it tells you does. In particular a percent-encoded
  URL whose decoding has **no** whitespace (`%2D`, `%3A%2F%2F`) is refused with exactly the
  message it has always had, byte for byte, because there the advice was correct all along: the
  raw spelling is a real URL and a click confirmed it opens. **If you match on our refusal
  text**, the two whitespace-related messages are the ones that gained a sentence.

## [1.50.0] — 2026-09-08

### New capabilities

None.

### Behavior changes you can observe

- **`help()` on a shipped module no longer points you at documents you do not have.** 103
  citations of this project's own internal design records are gone from comments and
  docstrings across 54 modules — each one rewritten to keep the fact it carried and drop the
  pointer you could never follow. If you read the installed source or call `help()`, that text is
  cleaner. **Nothing else moved:** no behaviour, no API, no refusal text, no log line, no output.

  That is proven rather than claimed — a recursive code-object comparison across every changed
  module found zero differences, and `capabilities(full=True)` is byte-identical.

  This finishes what [1.49.0] started: that release removed the routing *mechanism* it describes;
  this one removes the last of its vocabulary from the bytes you install.

### Upgrade & compatibility

- **Nothing to do.** **No dependency was added, removed or repinned.** No public symbol was added,
  removed or renamed; no config key moved; no message text changed. The one-release tolerance of
  the retired output key disclosed in [1.49.0] still stands and is unchanged — including
  its four reporting doors and the fifth path (`dataclasses.replace()`) documented there.

- Everything else in this release is maintainer tooling and test-suite hygiene, which reach no
  wheel holder: a release-script refusal that fired silently in its normal case, and two guards
  whose populations could narrow without failing. They are named in `CHANGELOG.md` and excluded
  here deliberately, per this file's own criteria, rather than omitted by oversight.

### Known limitations

None.

## [1.49.0] — 2026-09-08

### New capabilities

None. This release removes one.

### Behavior changes you can observe

- **A download with no `--route` no longer relocates your output.** Until now, a document whose
  converted body carried a particular set of three key/value table rows was written into a
  subdirectory derived from their values beneath `-o`, on by default. That derivation is
  gone. **The same document now lands flat in `-o`.** Deciding where a document belongs is
  yours; if you want a derived subpath, derive it and pass it as `--route`.

  **There is no code path that can warn you about this — it happens at exit 0.** If you keyed
  anything on the derived location — a ledger, a re-ingestion glob, an idempotency check, or
  simply two documents that used to separate into two subdirectories and now share one — read
  `result.output_dir` (or `result["output_dir"]`) rather than globbing the tree.
- **`result["route"]["reason"]` can no longer be either of the two values that reported the derivation.**
  The surviving vocabulary is exactly `explicit_route` and `routing_disabled`, both spelled
  as they always were — a strict **subset** of the old four, so validating an answer against
  the set you already know never meets an unknown string. Drop any branch on the two removed
  literals.
- **Two public constants are REMOVED, not renamed: `ROUTE_DERIVED` and `ROUTE_NOT_DERIVED`.**
  `from larkdocio.read.download import ROUTE_DERIVED` now raises `ImportError`. They named the
  two reason values above, so they leave with them. `ROUTE_EXPLICIT` and `ROUTE_DISABLED` are
  unchanged and still importable from the same place — if you imported **those two** rather
  than hardcoding their strings, nothing changes for you.
- **`routing_disabled` survived as a spelling but now means MORE than it did.** It used to
  mean *"the operator switched the derivation off"* and, with the derivation on by default, a
  default-configured download never produced it. It now means *"no `--route` was supplied, and
  the library derives none"* — which is **every download you do not route**, including the ones
  that used to report an incomplete derivation. If you branch on it as evidence that someone
  turned a feature off, that branch now fires on ordinary traffic.
- **The record's other three keys are unchanged and still always present**, and are now
  permanently `derivation_ran: false`, `labels_found: []`, `labels_missing: []` — nothing is
  looked for, so nothing is found and nothing is missing.
- **The `WARNING` line that announced a detected document format and its derived path is gone**, along with
  the `INFO` miss report that named which of the three rows a document carried. A download that
  relocates nothing now says nothing about relocation.
- **One runtime refusal message changed its example text.** The refusal for spans on a table
  block still refuses for the same reason and still says "a table's content lives in rows";
  the example after it names a generic table. Refusal text is not
  part of the preserved surface — if you match on it, match on the reason, not the example.

### Upgrade & compatibility

- **A GUIDE SECTION ADDRESS MOVED with its retitle, and the break is disclosed rather than
  silent.** The chapter documenting where a download lands was retitled, so its slug changed:
  the old address, which named the derivation, becomes
  `where-the-file-lands--o-and---route-when-you-name-the-subpath`. The old address now raises
  `ValueError` from `guide(section=…)` and exits 1 from `larkdocio guide --section …`; the slug
  also rides in `capabilities(full=True)` and in `guide_sections()`. If you deep-link or script
  against that section — and it is the very chapter a reader upgrading through this release
  goes to — re-point it. `guide_sections()` lists every current heading with its slug.
- **UNCHANGED, stated explicitly because silence reads as risk:** the `route=` parameter of
  `handle_download_command` and **all eleven parameter names in their current positions**; the
  `RoutedPath` class; the `route` key on the download's result with **all five** of its record
  keys; the `INFO` line prefixed `Downloaded markdown file to `; the `WARNING` shaped
  `Unknown block type <N> (block_id=`; and the `WARNING`
  `Routing to the caller-supplied --route path: `. `--route`'s own sanitization and its four
  refusal messages are byte-identical.
- **The config key that switched the derivation off is accepted and ignored in this release,
  and removed in the next one. Four ways of setting it exist and none of them breaks:** a `config.json` still
  carrying it loads and ignores it; the in-process form this guide used to teach — passing
  that key `=False` into an `OutputConfig(...)` constructor — still constructs rather than
  raising `TypeError`; **a POSITIONAL argument still lands where you meant it**, because the
  field stays declared in its old position for this release; and assigning the attribute on a
  loaded config is accepted and ignored too. **Every one of the four reports a warning** —
  including a positional call of five arguments whose fifth happens to be the field's own
  default, which is detected from the call's own argument count rather than from the value it
  carried. Each warning names what the key did
  and what to do instead. **A fifth path also emits it, harmlessly:**
  `dataclasses.replace()` on an `OutputConfig` re-passes every declared field as a keyword,
  read off the instance it was handed, so it trips the same notice for a key you never
  touched — the object it returns is correct and unaffected, and the notice goes with the
  field when the field goes.
- **Positional calls to `OutputConfig` change meaning when the field is removed next release.
  Move them to keywords now.** Measured against a successor with the field dropped and the
  order otherwise unchanged: **five** positional arguments — the fifth silently rebinds from
  the retired key onto `download_attachments`, switching **network fetching of attachment
  binaries ON**; **six** — same rebinding, and the sixth moves onto `resolve_mentions`;
  **seven** — raises `TypeError`, which is loud, immediate, and therefore the *safe* case, not
  a meaning change. Five and six are the dangerous ones precisely because they keep working.
  Keyword calls are unaffected at every count.
- **No dependency moved.**

### Known limitations

- **larkdocio derives no destination, at all.** There is no replacement, no opt-in and no
  caller-supplied label list: `--route` (or `route=`) is the only thing that ever places output
  anywhere but `-o`. That is the point of the change, not a gap in it.

## [1.48.0] — 2026-09-07

### New capabilities

None. The Base column-type migration already worked and is unchanged; what changed is the
permission requirement the library publishes for it.

### Behavior changes you can observe

- **The Base column-type migration (`base-schema-write`.`migrate_field_type`) told you it needed
  no permission at all. It now names the four bitable routes it reaches and the scope they
  require.** Its published permission block read `api_using: false`, `scopes: []`,
  `endpoints: []` — the shape that means *this call makes no Lark request* — for an operation that
  authors a column, copies every value in it, verifies the copy by reading, and deletes the
  original. The maintainer's permission matrix (`PERMISSIONS.md`, in the dev repo), which is a
  byte-identical projection of that same derivation, therefore carried no row for it. If you provision your Lark app from the
  published requirement — which is exactly what it is for — this operation contributed nothing to
  your grant list, and the denial you would have met was one the library implied could not happen.

  The block now reports `api_using: true`, `endpoints` listing
  `/open-apis/bitable/v1/apps/:app_token`, `/open-apis/bitable/v1/apps/:app_token/tables`,
  `/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields` and
  `/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search`, and
  `scopes: ['bitable:app']`. The maintainer matrix carries the matching row.

  **You almost certainly need to grant nothing new.** `bitable:app` was already required by the
  other operations of the Base schema-write surface, so the *surface's* scope list has not moved
  and a caller who could already create or delete a column could already run the migration. What
  moved is that the operation now states its requirement instead of publishing an empty one.

- **`preflight.requirements_for_operations("base-schema-write.migrate_field_type")` answers
  `state="known"` instead of `state="undetermined"`, and `check_permissions` returns real
  verdicts for it.** If you branch on that state, this is the field that changed. It still appears
  in `blind_spots`, and its `unresolved_call_sites` is still non-empty — see Known limitations.

- **A docx `apply()` that hits a Lark error mid-batch now hands you the apply-log instead of
  losing it — and the exception it raises changes class.** Before: a create, patch or delete
  that Lark refused part-way through a batch raised `LarkAPIError` straight out of `apply()`,
  so you got no `ApplyLog` at all — not for the entries that had *already written*, and not
  for the ones that never ran. Recovering from a half-applied batch meant re-reading the
  document and guessing. Now every plan entry ends in exactly one log entry,
  `len(log.entries) == len(plan.entries)` in plan order on every run, and the failure comes
  back as `LarkApplyRefusedError` carrying that complete log on `.log` (or as the return value
  if you pass `allow_partial=True`).

  **What you may need to change.** If you catch `LarkAPIError` around a docx `apply()` in
  order to notice a mid-batch failure, that `except` no longer fires — catch
  `LarkApplyRefusedError` (or `LarkDocIOError`, which is a base of both) and read `err.log`.
  If you already catch `LarkApplyRefusedError`, you need to change nothing: this failure now
  arrives in the arm you already have, with more in it.

  **And read this one even if you catch nothing: there is a case that now raises NOTHING AT
  ALL, where it used to raise.** `apply()` raises only when the finished log holds an entry
  that did **not** land. An `applied-unverified` entry *did* land, so it is not one of those —
  and if it is the **last** entry of the plan (a one-entry batch is the common case) there is
  nothing after it to log as not-attempted, so the log holds no non-landing entry and `apply()`
  **returns normally**. The concrete shape: you insert a table, the create call succeeds,
  filling its cells then fails — you get a return value, exit status 0, and a table in your
  document with some cells empty. Nothing about that is new behaviour in the document; what is
  new is that this used to reach you as an exception and now reaches you as a log entry.
  **Do not treat "`apply()` returned" as "the batch is clean."** Check the log — the one-line
  form is `assert not log.refusals and not [e for e in log if e.outcome ==
  "applied-unverified"]`, or read `log.halt`, which is `None` exactly when the batch ran to the
  end. Each `applied-unverified` entry names in its `detail` which write returned and what
  failed afterwards.

  **Which entries apply and which do not is unchanged, and no call is issued that was not
  issued before.** The batch still stops at the first failure, exactly as it did when the
  exception escaped; the entries after it are now *logged* as `not-attempted` rather than
  simply missing.

- **The docx apply-log has three new outcomes, eight new refusal codes and a new `halt`
  field.** `entry.outcome` can now be `applied-unverified` (a write **returned** and a step
  after it failed — the change **is** in your document and only its verification record is
  incomplete), `failed` (whether it landed is **indeterminate**; deliberately not called a
  refusal, because "nothing landed" would be a guess) and `not-attempted` (the batch halted
  earlier). The refusal codes are `api-error`, `permission-denied`, `rate-limited`,
  `transport-failure`, `pagination-unterminated`, `unexpected-error`, `unverified-write` and
  `not-attempted` — seven of them deliberately spelled exactly as the Sheets and Base engines
  already spell them, so one condition does not have two names across two engines.
  `log.halt` is `None` on a batch that ran to the end, and otherwise says which entry stopped
  it and why. Two new read-only properties come with them: `log.not_attempted` and
  `log.indeterminate`.

  **If you branch on `log.applied` or `log.refusals`, read this.** `applied` now means *the
  change landed* (which includes `applied-unverified`) and `refusals` means *it did not*
  (which now includes `failed` and `not-attempted`). For every outcome that existed before
  this release both properties give the identical answer they always gave; what changed is
  that the new outcomes are sorted deliberately rather than by whether the word was
  `"refused"`. Serialized logs written by earlier releases round-trip byte-identically —
  `halt` is omitted when unset.

- **A rate limit that survives the write transport's backoff is now reported rather than
  raised, on three docx paths.** The rule behind those paths is unchanged and still holds:
  throttling is never reported as staleness and never as an ownership denial. What changed is
  that it comes back typed `rate-limited` in the log, with the batch halted, instead of
  travelling out of `apply()` and taking the log with it. The **one** rate limit that still
  raises is the whole-document compare-and-swap's, which happens before the batch and before
  any write.

- **A new exception type, `larkdocio.errors.LarkPaginationError`**, raised when a paged walk
  cannot be run to exhaustion. It cannot fire against a well-behaved server: it needs a
  response that reports "there is more" while handing back a cursor already used, no cursor at
  all, or a chain of 200 fresh ones. The docx write client's document-block listing used to
  loop forever on the first of those — it now stops and says so, because that listing is how a
  created table's cell fill learns which blocks to write to, and a short list would aim those
  writes at a subset of your table without telling you. It is a `LarkDocIOError`, not a
  `LarkAPIError`: every page answered successfully, so there is no Lark code to carry.

- **A scope denial on an attachment upload, a Drive file upload/download/delete, or a chunked
  upload used to reach you as an ordinary API error. It now carries the same denial record
  every other surface's denials carry — and `err.denial is not None` is the check that means
  the same thing everywhere.** Those legs raise a typed error of their own —
  `MediaUploadError`, `MediaDownloadError`, `MediaPermalinkError`, `DriveFileUploadError`,
  `DriveFileChunkedUploadError`, `DriveFileDownloadError`, `DriveFileMetaError`,
  `DriveFileDeleteError` — and until now those errors carried only Lark's `code` and `msg`.
  A refusal for a **missing scope** was therefore indistinguishable from any other failure on
  exactly the legs where a missing grant is the likeliest cause, and the fix a caller needed
  (grant a scope in the Lark console, on *this* app) was the one fact the error did not carry.

  **What arrives now.** The same errors, of the same classes, with `err.denial` populated when
  Lark's answer was a scope denial: the exact missing scope(s), Lark's verbatim `code`/`msg`,
  the console deep link when Lark supplies one (never invented — an absent link is stated as
  absent), **which credential pair** made the call, and the fallback that still works where
  there is one. `err.denial.detail()` is one paragraph you can relay as-is. On these SDK legs
  the console link is new: it lives only in the response body, and the body was not being read.

  **What you may need to change — and it is probably nothing.** The classes did not move: an
  `except MediaUploadError` or `except LarkAPIError` fires exactly as before. If you branch on
  `isinstance(err, LarkPermissionError)` to tell *"I could not"* from *"it is not there"*,
  that check still answers correctly for every surface it already answered for, and it still
  answers **False** on these typed legs — they keep their own class deliberately, because
  `MediaUploadError` is what tells you *the attachment leg failed and the record was never
  judged*, and `DriveFileChunkedUploadError` carries the `upload_id` of a transaction no
  listing shows and no delete removes. Losing that to gain a classification would have been a
  poor trade. **Use `err.denial is not None`** and you get the right answer on every surface,
  including these.

  **Nothing else about these errors moved.** For a non-denial code the class, the `code`, the
  `msg` and the message text are byte-for-byte what they were, and `err.denial` is `None`; a
  rate-limit code on one of these legs still comes back as that leg's own class, as before.
  `err.denial` now exists (as `None`) on **every** `larkdocio` API error, so reading it never
  raises `AttributeError`.

  **One related fix rides with it.** The Sheets workbook walk, which loudly skips a tab Lark
  refuses and keeps reading the rest, refuses to skip a tab on **any** answer carrying a scope
  denial rather than only one of a particular class. A missing grant is a fact about the call,
  not about the tab, and laundering it into "this tab is unreadable" would turn it into a
  permanently short document.

  **One more place this reaches, and it is the one where you already have something to clean
  up: `create_table(..., default_view_name=…)`.** That call creates the table and then renames
  its default view. If the rename is refused, you get `TableCreatedViewNotNamed` — the table
  **exists**, the name did not land, nothing was rolled back and nothing was retried. Until now
  that error carried Lark's `code` and `msg` but no denial record, so a rename refused because
  your app lacks `bitable:app` was indistinguishable from any other rename failure, on the one
  path where you are already holding a half-finished object. It now carries `err.denial` with
  the missing scope, the console link and the credential pair, forwarded from the underlying
  refusal rather than rebuilt — so the link survives. Everything else about that error is
  unchanged: same class, same `code`/`msg`, same message text, same `to_dict()`, still chained
  to the original.

- **Two Drive write legs now DECLARE what they verify, and `help(larkdocio.drive)` stops
  promising a read-back for all four.** No behaviour moved: nothing gained a read-back, nothing
  lost one, and no plan gate was added. What moved is what the library says.
  `capabilities(full=True)['surfaces']['drive-files-write']['safety_contracts']` gains
  **`bytes-verified-round-trip`** — the leg with the strongest verification in the package
  (`put_file_in_folder` re-downloads the object and compares it to what went up by `sha256`
  **and** length, and publishes the verdict as `LinkedFile.bytes_verified`; `verify_bytes=False`
  turns it off, and `bytes_verified` then reports `False`, which is the absence of a verdict
  rather than a negative one) — and `drive-versions-write`, which declared nothing at all, gains
  **`version-pairing-is-not-a-verdict`**: its head-revision read happens *before* the create,
  which pairs `(name, token, revision)` rather than confirming the write, and the new version is
  never listed back. `drive-folders-write` still declares no verification because `create_folder`
  performs none, and `drive-access-write`'s `read-back-is-the-verdict` is untouched. **If you
  pin the anchor or diff the census, this is a payload change**; if you branch on
  `safety_contracts`, two lists grew. The package docstring now states the split per leg, and
  its `drive-access-write` line no longer says *docx* where the leg takes `docx` / `sheet` /
  `bitable`.
  **This SUPERSEDES the count in the `[1.41.0]` note below** — *"Only one does"* — and only the
  count: that note was true the day it was written, when the access leg was the one leg
  declaring a verification contract, and its reasoning (read the posture off the leg, never off
  a blanket sentence) is unchanged and is exactly what this release acts on. **Two legs verify
  in-library now.** The note stays as written because it is a dated record of what 1.41.0
  shipped; the live answer is each leg's own `safety_contracts`, which is where both notes send
  you.

- **The registry told you every packaged consumer document's `###` headings were individually
  retrievable. For two of the five documents that was false, and following it raised
  `ValueError`.** `capabilities(full=True)['docs'][<accessor>]['section_addressing']` carried one
  sentence written for all five packaged documents — *"Each `###` (and `##`) heading is
  individually retrievable"* — but the release notes and the changelog are indexed at `##` only,
  so `release_notes(section=…)` raised for the heading `New capabilities`, and
  `changelog(section=…)` for `Fixed` — exactly the headings the registry named. This is the artifact you are told to trust over prose,
  and it was wrong about its own accessors.

  **The sentence is now derived from each document's own index** and states that document's real
  levels: `##` and `###` for the guide, the writer brief and the Lark-application walkthrough;
  `##` only for the release notes and the changelog, where it now also says in so many words that
  a heading at any other level is not a section and `section=` raises for it. **No call behaves
  differently** — the levels themselves did not move, only the description of them — so if you
  drove section access from the index (`<accessor>_sections()`, or the `sections` rows in the same
  registry row) rather than from that sentence, you were never affected. If you have a snapshot
  over the `capabilities()` payload, five strings in it changed.

- **The typed error taxonomy moved into the shared read/write core, so a traceback now prints
  `larkdocio.common.errors.LarkConfigError` where it printed `larkdocio.errors.LarkConfigError`.**
  A class reports where it is defined, and the definitions moved one tier down — beside the
  transport and the credential resolution that raise them — so `repr()` of any of these classes
  carries the same new prefix. **Nothing a program *does* with them changes.** They are the same
  class objects: same names, same bases in the same order, same constructors, same message text.
  `except LarkAPIError`, `isinstance`, and an identity check all answer exactly as they did
  before, on either import path, because the two paths bind the *same objects* rather than
  copies. **`from larkdocio.errors import ...` is unchanged and is not deprecated** — it is
  still the import every recipe in the packaged guide uses, and it is staying. Two smaller
  visible things come with it: `larkdocio.common.errors` is importable as well, and
  `help(larkdocio.errors)` now opens by explaining the re-export — the taxonomy's own overview
  is `help(larkdocio.common.errors)` — while listing one member that page had been omitting,
  `note_for`. **No action is required unless you scrape or assert on the text.** A log line
  matched against the old module prefix, or a snapshot over a traceback or a `repr()`, is the
  one thing to re-baseline; nothing you call, catch or read back behaves differently.

### Upgrade & compatibility

**No dependency was added, dropped or re-pinned.** No CLI flag changed.

Two things in this release do move under you and both are described above: the exception class a
docx `apply()` raises on a mid-batch Lark error, and the docx apply-log's outcome and refusal
vocabulary. **The permission half of this release moves nothing you call** — it changes what the
library *says* about a permission, not what it *does*: two fields on one operation's published
permission block change value (`api_using`, `endpoints`/`scopes`) and one `preflight` state
changes.

One public symbol is added — `larkdocio.errors.LarkPaginationError` — and nothing is renamed or
removed. If you have snapshot tests over the published permissions payload, over the
`capabilities()` payload, or over a serialized docx apply-log's shape, re-baseline them; a log
serialized by an earlier release still reads back identically.

### Known limitations

- **Two of the Base schema surface's five deletes are outside the consent fence, deliberately —
  and the text you read from `help(larkdocio.base)` used to say otherwise.** It claimed *every*
  delete on `base-schema-write` sat behind a Base-wide loss preview and a consent token minted
  from its own plan. Three deletes do: deleting a column, deleting a table, and the batch table
  delete each require a read seam, produce an enumerated loss preview, and refuse without
  `consent_to_destroy(plan)`. **Two do not, and if you assumed the fence would stop you, read
  this:** deleting a **view** is a plan-gated, read-back-verified call that asks for no consent,
  because a view is a saved presentation — a filter, a hierarchy pointer, a hidden-field set — so
  its delete destroys configuration and not one record; and deleting the **Base itself** is a
  whole-object trash on the same gate as deleting a document or a spreadsheet, with no plan, no
  preview and no token, because a whole Base's loss is every table, column, record and view it
  holds and nothing can enumerate that before the call. **Nothing about how any of these behaves
  has changed in this release** — the set the library reports as destructive is the same three
  names it has always been, and no call you already make behaves differently. What changed is
  that the shipped text now says which two are outside the fence and why, so the assumption is no
  longer available to make.
- **The two Base write engines are reached by importing the module that owns them, not off
  `larkdocio.base`** — and the same shipped text used to claim the opposite. `larkdocio.base`
  exports the read surface and the pure offline helpers; it exports **no** write entry point, on
  purpose, the same way the top-level package re-exports neither write half. Import them
  directly: `from larkdocio.base.apply import dry_run, apply` for records,
  `from larkdocio.base.schema_apply import schema_dry_run, schema_apply, consent_to_destroy` for
  schema, and `BaseWriteClient` / `BaseSchemaClient` from `write_client` / `schema_client`. **One
  trap in particular:** `larkdocio.base.apply` is the *module*, never the `apply` function inside
  it, so `from larkdocio.base import apply` hands you something you cannot call — and attribute
  access off `larkdocio.base` for a submodule is **not a contract** at all: it works only for
  whatever the package happens to import, which is why `larkdocio.base.view_plan` does not resolve
  until you import it by name. Nothing was removed and nothing was renamed; the documented route
  is now the one that actually works.
- **The migration's *endpoint* list may still be short by up to two routes, and it says so.** Two
  seams inside its reach load a module by name at call time, which the static derivation cannot
  follow, so `unresolved_call_sites` still names them (two entries, down from fourteen) and the
  operation is still reported as an incomplete derivation by the maintainer-side coverage audit.
  This was measured rather than left open: everything behind the first seam is a fixed advice
  string that reaches no endpoint, and everything behind the second reaches only routes requiring
  `bitable:app` — the scope you are already told to grant. So the **scope** answer is complete;
  the endpoint list may omit the two Base *view* routes. The disclosure is deliberately kept
  rather than suppressed, because an unverifiable-looking empty is the failure this release fixes.
- **The docx apply-log invariant is still not *declared* for `docx-write`, and the published
  reason for that has changed.** Every entry of an accepted batch now ends in a typed, logged
  outcome. What keeps the surface from declaring the invariant outright is one deliberate
  escape *before* the batch: the whole-document compare-and-swap re-raises a rate-limit error
  rather than treating throttling as document drift, so that single failure still leaves
  `apply()` with no log. The published position text says exactly this; the previous wording,
  that the surface ran no per-entry boundary at all, is no longer true and has been replaced.
- **The release notes and the changelog remain addressable one whole release at a time, by
  design.** Both documents repeat the same `###` subsection headings under every release, so an
  index at that level would find one name dozens of times and could only answer it ambiguously;
  the index refuses to be built rather than serve you an arbitrary match, which would make *every*
  `section=` call raise. Ask for a release — `release_notes(section='1-48-0-2026-09-07')`, the slug the index gives you — and you get its
  subsections with it, under the rule that a section runs to the next heading of the same or
  higher level.
- Nothing else changed here. The library still never widens, requests or escalates a scope — it
  describes requirements and surfaces Lark's own denial body; a grant stays a Lark console action.

