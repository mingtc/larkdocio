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
the day the release was actually tagged. Until then the topmost section is **un-cut**: its
date is a **placeholder with no authority**, it may be days or weeks older than the newest
work described beneath it, and **nothing landing into an un-cut section edits that date**.
This is enforced rather than promised — the release tooling refuses to tag a section whose
header date is **earlier** than the newest date written inside that same section, naming both
dates, because a release dated before the changes it contains is a date nobody can use. So:
read the topmost section for **what** changed; read a **cut** section's date for **when**.

**Where the history starts.** These notes begin at **1.14.0**, the span across which a
consumer had to reconstruct dependency and behavior changes out of the internal log. Changes
before 1.14.0 are recorded only in the maintainers' engineering log, which is not published.

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

## [1.47.0] — 2026-09-03

### New capabilities

None. Addressing a column of a header-less table by a verbatim quote of its row-0 text already
worked and is unchanged; what changed is the sentence you are given when it misses.

### Behavior changes you can observe

- **A `column-not-found` refusal no longer claims that a table's first row holds headers when
  the table says it does not — and it now tells you which of the two kinds of table it was
  looking at.** `TableLocator`'s `column_header` means *the text in row 0*, and it never required
  the table to have a header row; the refusal, however, presented row 0 as *"its headers"* for
  every table. On a table whose own `header_row` is false, that named **data** cells as headers,
  inside the very did-you-mean list that exists so you would not have to re-read the document.
  The refusal detail is reworded, and the list of row-0 strings survives intact:

  ```
  before: no column header in table t9 contains 'Units'; its headers are ['Widgets', '1200']
  after:  no cell in row 0 of table t9 contains 'Units' (column_header always matches row 0,
          and this table declares header_row=False - so row 0 holds DATA, not headers; address
          a column positionally with column_index); row 0 reads ['Widgets', '1200']
  ```

  Where row 0 really is the header row you are told so — *"column_header matches row 0, this
  table's header row"* — because that is the fact that helps there. **What did not move:** the
  refusal code is still `column-not-found`, resolution is still unique-or-refuse, and which cell
  a locator resolves to is unchanged. Only the `detail` string differs. **If you match on that
  string, re-read it** — `detail` is prose for a human and has never been a stable parsing
  surface; the code is the field to branch on.
- **A reconciliation that refuses because a marker was deleted now says so even when the
  document also contains an escape it cannot decode.** When you delete a block's `<!-- lark:block:… -->`
  marker but leave the block's text in place, the refusal is the narrow, actionable one:
  `marker-dropped`, *"the block's own text came back with it"* — put the marker line back above
  that text. That reading was being lost: **one** line elsewhere in the same stretch of Markdown
  carrying a backslash escape the round trip cannot decode caused the whole stretch to be dropped
  from the text the check compares against, and the identical edit was refused `marker-absent`
  instead — *"the block and its content are both gone"*, which was false, and it pointed you at
  content sitting in front of you. The undecodable text itself was never mentioned by any
  refusal, so the thing actually blocking you was invisible. **Nothing was ever written on either
  path** — both readings refuse and no request is compiled; what you lost was the reason you
  could act on. Now each unit is decoded on its own: a unit that cannot be decoded no longer
  removes its neighbours from the comparison, and it still matches nothing, so text that came
  back **split** by something unreadable is not reported as having come back whole (that case
  refuses `marker-absent`). **What did not move:** the stages still run in the same order, and
  no refusal code, no field and no return shape changed. **What CAN move, and it is the same
  correction seen from the other side:** if the deleted marker's text came back **split apart
  by a whole stretch you cannot decode**, that stretch used to vanish from the comparison, the
  two halves read as adjacent, and you were told `marker-dropped` — *"the block's own text came
  back with it"* — on the strength of Markdown nothing could read. Today that document is
  refused `marker-absent`, because text nobody can decode is not evidence your block's text
  came back whole. Both of those refuse and **nothing is written on either**; what differs is
  the reason you are handed. Those two document shapes are the ones we measured moving, side by
  side against 1.46.0, and each is pinned by a regression test in the source tree; we did not
  enumerate every possible document, which is one more reason to branch on the refusal **code**
  and read `detail` as prose. Fix the marker, re-run, and an undecodable escape is then
  reported on its own as `undecodable-text`.
- **A refused plan preview over a long quote now returns in a tenth of a second instead of
  seconds.** When a quote differs from the document only in whitespace, the refusal computes the
  longest run of your quote's words that *is* verbatim in the document, so it can tell you where
  the difference starts. That search was superlinear and it runs once per plan entry. Measured
  end-to-end through `dry_run` with one space turned into a newline: **3.271 s → 0.105 s** for a
  1200-word quote, **0.984 s → 0.043 s** at 800 words, and **2.513 s → 0.123 s** for one preview
  of ten 500-word near-miss edits. **The fragment you are told is byte-for-byte the same string**
  — this is a cheaper search for the same answer, never a cap or a truncation, which would have
  changed what you are told. Nothing was written before or after; the whole cost was the
  explanation, and a preview that feels hung is one you kill, losing the very detail it was
  computing.

### Upgrade & compatibility

- **No dependency moved and no pin moved** — nothing this release depends on changed, and the
  wheel's requirements are byte-identical to 1.46.0's.
- **Drop-in, with one caveat worth reading.** Every public symbol, CLI flag, refusal code and
  return shape is unchanged, so re-vendoring needs no call-site edit. The caveat: the `detail`
  text of one refusal changed (above), so a test or a log matcher pinned to that wording needs
  re-reading. Refusal codes are the stable contract; `detail` is not.

### Known limitations

- **`column_header` is deliberately *not* gated on a table's `header_row` flag.** It matches row
  0 either way. That is a capability — it is how you address a column of a header-less table by
  name — and gating it was considered and declined, because it would have removed a working way
  to repair a sentence. The consequence to know: on a header-less table, `column_header` matches
  a **data** cell, and if row 0's text is not unique across columns the locator refuses as
  ambiguous rather than guessing. `column_index` is the positional address for that job, and the
  refusal now names it.
- **A row addressed by a row-0 cell describes itself.** If a `row_key` quote matches a cell in
  row 0, the locator resolves row 0 — and the `column_label` the resolved cell reports is read
  from that same row, so the preview's description of the cell is worded in terms of the cell
  itself. It resolves to the cell you designated and it is unique-or-refuse; only the disclosure
  is circular. Known, and left alone in this release.

## [1.46.0] — 2026-09-03

### New capabilities

None.

### Behavior changes you can observe

- **The shipped setup walkthrough (`larkdocio.lark_setup()`) now tells you that an app's reach
  is WIDER than the list of things you shared with it.** An app also inherits whatever is
  visible to the whole tenant, and that cuts two ways, so the walkthrough states both.
  The convenient way: before concluding you need per-person identity to reach something, check
  whether the app can already read it. The way that matters more: *"what can this app read?"* is
  not answerable from your share list — the honest answer is your shares plus anything visible
  to the whole tenant — so an exposure audit taken from the share list alone under-counts
  what the app can see. This is Lark's own permission model rather than a library feature or a
  guarantee to build on; it is written scoped to one tenant, one app and one folder, observed
  on one day, and a tenant that shares nothing that widely would see none of it. It is a
  statement about **access**, not about scopes: no grant in the console decides which objects a
  call may touch.
- **And the walkthrough no longer contradicts itself further down.** The bullet about an app's
  *availability* list said an app the whole tenant can see still reads nothing that has not
  been shared onto it; it now reads *"…shared onto it (including tenant-wide
  visibility)"*, so the section you meet later cannot hand you back the assumption the section
  above just corrected.
- **Nothing else a caller can observe moved** — no public symbol, CLI flag, refusal code or
  return shape. The remainder of this release is the publishing repository's own cut tooling,
  which now reads the remote back and reports what it measured rather than trusting the exit
  code of a push.

### Upgrade & compatibility

- **No dependency moved and no pin moved** — nothing this release depends on changed, and the
  wheel's requirements are byte-identical to 1.45.0's.
- **Drop-in.** No call site needs an edit and nothing a consumer parses changed shape; the only
  shipped text that moved is the setup walkthrough described above.

### Known limitations

- **The distribution branch is published as a single force-pushed commit, and the host has been
  observed reverting a ref it accepted.** If a fresh
  `git clone --branch dist --depth 1` hands you a wheel older than the tag you expected, that is
  the shape to suspect: the tag is authoritative, and your refresh script's build-from-tag
  path reproduces the same wheel from it.

## [1.45.0] — 2026-09-03

### New capabilities

None.

### Behavior changes you can observe

- **The shipped guide's clear-cells recipe stated the wrong number of sheets-write
  operations, and now states the derived one.** `larkdocio guide` (and the packaged
  `GUIDE.md` the wheel carries) said *"`capabilities()` lists six sheets-write operations
  and none of them clears anything"*. The recipe's own point was and remains correct — a
  value write of `[[None]]` is how you clear a range — but the count had been false for
  three releases: `capabilities()` reports **nine** operations
  for `sheets-write`, which is what the sentence now says, matching the reconciliation
  (*"Ten families, nine operations"*) that the same section of the guide already carried.
  Nothing about the surface itself moved: no operation was added, renamed or removed, and
  no code path changed. If you counted operations out of that sentence rather than out of
  `capabilities()`, re-read it.

### Upgrade & compatibility

- **No dependency moved and no pin moved** — nothing this release depends on changed, and
  the wheel's requirements are byte-identical to 1.44.0's.
- **Drop-in.** Only shipped prose changed; every public symbol, CLI flag, refusal code and
  return shape is unchanged, so re-vendoring needs no call-site edit.

### Known limitations

- **Clearing a range on the Sheets write surface is a value write of `[[None]]`, not an
  operation of its own.** It goes through the same `dry_run` → plan → `apply` gate as any
  other value write, and the previewer attaches an `overwrites-live-formula` note naming
  every formula such a write would destroy. The packaged guide's *"Recipe: clear cells"*
  is the reference, and it now states the operation count the projection derives.

## [1.44.0] — 2026-09-02

### New capabilities

- **You do not have to hand-roll the client, the wiki lookup and the parser to get one
  document's Markdown — there is a one-call door, and the guide now names it.**
  `larkdocio.drive.read_child_markdown("docx", url=…, token=…)` returns that document as one
  Markdown string. It shipped some time ago and nothing you read pointed at it, which is the
  actual fix here: no function changed. **Import it from `larkdocio.drive`** — it is exported
  there and **not** from the top-level `larkdocio` namespace, which is why it was easy to miss.
  **Four things it does NOT do, and this is the half worth reading before you switch to it:**
  no image fetch (image and whiteboard tokens stay tokens; nothing is downloaded), no file write
  (nothing lands on disk — the returned string is the whole result), no metadata-table routing (the
  three-row derivation is the CLI's), and **no `@mention`
  resolution** — it parses without a read client, so mentions come back as raw `@ou_…` ids where
  the `download` command substitutes display names. Need any of the four and you want `download`.
  The docx-read recipe carries the call and the exclusions together; the block is executed by the
  test suite, so it is the working call rather than a snippet.

- **A release is now addressable by its bare version.** `larkdocio.release_notes(section="1.43.0")`
  returns that release's section — the spelling you already hold in your pin — alongside the two
  spellings that always worked: the full `## [X.Y.Z] — date` heading and the slug derived from
  it. `larkdocio.changelog(section=...)` takes the same spellings for a release the changelog
  records. The bare version is matched only
  after both exact spellings miss, so nothing that resolved before resolves differently now.
  Matching stays case-insensitive and tolerant of surrounding whitespace.

- **The guide now tells you what a plan entry's `before` and `after` actually hold — one row
  per shape, and there are six.** `before` never meant one thing, and three of its meanings
  had no sentence you could read: it is a paragraph's whole text on a whole-block edit, the
  **cell's** descendant text on a table-cell patch, the **span only** on a sub-span edit, a
  **grid phrase and not text at all** on an appended table row (`"3 rows × 2 columns"`), the
  text that would be removed on a delete — where there is **no `after` key at all** — and, on a
  checkbox flip, the *same string* `after` holds, with the real change carried by the separate
  `todo_done` field. That last one is the trap worth knowing: an entry whose `before` and
  `after` match is not necessarily a no-op. Read the new table with
  `guide(section="what-a-plan-entry-s-before-and-after-hold-one-row-per-shape")`, or find it in
  the write handshake recipe. It is **generated from the write layer's own serializers**
  rather than typed, so it cannot fall behind the code, and it names the ops that carry neither
  field (`insert`, `comment-create`, `comment-remove`) alongside what each of those previews
  instead. Nothing about the fields themselves changed — only what is written down about them.

- **The guide now says WHICH text it means — the library reduces a block to text five different
  ways, and it used to describe two.** Four things you could not previously read anywhere.
  (1) **The ladder.** § "The tree's own types" now carries a five-row table, each rung named by
  *the question it answers*: a block's own words with `@mentions` included (`plain_text`); what
  someone could literally quote back, mentions omitted on purpose (`block_plain_text`); a table
  cell's own descendant text; the **sub-span splitting basis — the `content` text runs only**;
  and what the apply engine reads back live as its staleness precondition. The last three are
  internal, so they are described and deliberately **not named** — you meet each one as a
  `before` value or as a refusal, which is what the rows tell you.
  (2) **The node-class index does not predict a sub-span refusal.** That generated table answers
  `plain_text`'s question, and `plain_text` reads a block's own text wherever it lives —
  `content` first, then a `title`, `caption`, `url` or `markup` field. A sub-span edit reaches
  only the `content` runs, so a block whose text lives on one of those other fields reads
  **yes** in the index and yields the **empty string** on the sub-span basis, and a sub-span
  edit against it refuses. Read that column as *"can I read this block's text"*, never as
  *"can I edit part of it"*.
  (3) **A sub-span edit segments the block permanently.** The run split is what preserves the
  surrounding styles, and nothing re-merges it: this library carries no coalescing step. A
  `snapshot()` digest is a sha256 over the raw block payloads, so once a block is segmented its
  digest **never returns to its pre-edit value** — not even after the words are edited back to
  what they said before. Two precisions worth holding: only a **proper** substring segments the
  block (a span equal to its whole text leaves one run), and a **whole-block** edit is the one
  path that re-merges — at the price of the styling flattening it always cost. Whether Lark's
  own server merges adjacent identically-styled runs on its side is *unmeasured, not refuted*.
  (4) **The id a whole-cell patch actually writes now has a name in the guide.**
  `entry.cell.target_text_block_id` is the inner text block the patch rewrites;
  `entry.block_id` is the container it was addressed through. Both are on the resolved entry,
  so you can read the id before approving, and it is the id to anchor a follow-up sub-span edit
  by. Nothing about the behaviour changed — only what is written down about it.

- **A labelled link now works inside a docx table cell.** Write
  `| EX-01 | Example Item | [Example Item - Details](https://example.com/items/example-item) |` and
  the cell comes back as that same Markdown — a label a reader can scan instead of a
  60-character URL. Two routes to it: hand the table to `compose()` as Markdown (a
  `[label](url)` inside a pipe-table cell is the one inline construct the dialect accepts), or
  author the cell as a sequence of `TextSpan` instead of a string:

  ```python
  NewBlock.table([
      ["Code", "Name", "Link"],
      ["EX-01", "Example Item",
       (TextSpan("Example Item - Details", link_url="https://example.com/items/example-item"),)],
  ])
  ```

  It works whichever way this library creates the table — the one-call table create and the
  create-then-fill route both carry it — and a cell with no link is written exactly as it was
  before.

- **What that supersedes, said plainly, because the previous release shipped the opposite.**
  Earlier notes and the shipped guide said an anchored link inside a table cell was
  unreachable, and added that *whether Lark's own API can style a docx cell at create time had
  never been probed*. It has now been probed, against a throwaway document this library created
  and deleted: Lark **accepts and stores** the link-carrying run inside a cell, on both of the
  routes above, confirmed by reading the document back fresh rather than by trusting the
  create's success code, and stored in the same shape as the same run in an ordinary paragraph.
  So the gap was ours and it is closed. The old sentence's *reason* still stands and is still in
  the guide — this library genuinely offered no route, and the bare URL genuinely was the route
  that worked — only its conclusion has moved.

- **THE HONEST SCOPE OF THAT MEASUREMENT, so nothing is read into it.** What was measured is a
  **link**, on **one** tenant, on **both** write routes, on a docx table cell that is neither
  merged nor nested. **Bold, italic, strikethrough, inline code, underline and colour inside a
  cell are not offered**, and nothing here says Lark refuses them — nobody has asked it. They
  are also not requestable: those are not fields on a `TextSpan`, so there is nothing to pass.
  Two more boundaries worth knowing: the anchor is authored when the cell is **created**, and a
  later whole-cell edit takes a plain string and replaces the cell with plain text; and merged
  cells (`rowspan` / `colspan`) are a different, unrelated thing and are still not authorable.
  Outside a table cell, `compose()` still refuses `[label](url)` and the typed
  `NewBlock.rich_paragraph` remains the route — that has not changed.

- **You no longer have to discover one refusal per attempt: `compose_check(markdown)` reports
  every construct a fragment cannot express, all at once, with line numbers.** Someone
  migrating ~27,000 words of existing prose needed **eight** separate attempts, because
  `compose()` refuses on the **first** inexpressible construct and says nothing about the rest.
  Six came from the source content — bold, italic, strikethrough, inline code, images, links
  (including a nested `[[label]](url)`) — and **two more came from what their own sanitiser had
  produced**: a list item whose text opens with `#` (which starts a new block and leaves the
  marker empty) and angle-bracket text (a well-formed open tag, so it reads as raw
  HTML). Each refusal was clear and named its fix. The cost was entirely in finding them one at
  a time, and that is what this removes.

  ```python
  from larkdocio import compose_check

  report = compose_check(fragment)
  report.ok                       # False if anything in the fragment is inexpressible
  for row in report.refusals:     # one row per OCCURRENCE, in document order
      print(row.line, row.construct, row.detail)
  report.constructs               # the de-duplicated construct names
  report.to_dict()                # JSON-native, if you report the list rather than read it
  ```

  **Nothing about what is refused has changed, and that is deliberate.** `compose()` behaves
  exactly as it did: same refusals, same messages, same codes, and it still refuses the whole
  batch on the first construct — **nothing became writable that was not writable before**, and
  the dialect is not one construct wider. Each row's `refusal` is the *same* typed refusal
  object `compose()` raises, so the recovery text you read here is the recovery text you would
  have met serially, word for word. The checker is **read-only and offline**: it compiles
  nothing, writes nothing, holds no client and no credentials, and makes no network call — so
  there is no plan, no gate and no cost to running it before every batch.

  Two behaviours to expect before you loop over the result. Rows are **per occurrence**, not per
  construct, because two bold spans on two lines are two edits (`constructs` is the collapsed
  view). And a construct **inside a fenced code block is not reported** — a fence's body is
  content, not structure, which is the distinction a search for `**` in your own text cannot
  make. There is a worked recipe in the shipped guide, § "Recipe: find every construct that will
  refuse"; the long-form treatment is in the writer brief, § "Finding every refusal in one
  pass".

  **What is NOT here.** There is **no command-line half** — no `roundtrip push --check`, no
  `--dry-dialect` flag — and none is promised: this is a library call. And there is no
  permissive mode: nothing here compiles a fragment partially, rewrites your prose, or turns a
  refusal into a warning.

### Behavior changes you can observe

- **A version-only request for a release the wheel carries used to fail.** Because a release
  heading carries its date, its slug does too (`1-43-0-2026-08-31`), and a bare `1.43.0` matched
  nothing — so the release you most likely ask about, the one you are re-pinning to, raised
  `ValueError: unknown section '1.43.0'`. Same input, different outcome: it now returns the
  section. If you worked around this by reading `release_notes_sections()` and passing a slug,
  that keeps working unchanged.
- **The refusal for a release older than the packaged window no longer claims the version you
  named is real.** It used to open *"`<version>` is a real release"* — an existence claim this
  copy cannot check, because it carries a window of the newest releases rather than the whole
  history. A version-shaped string that was never released got the same vouching answer as one
  that was, and you had no way to tell them apart. The refusal now leads with what this copy
  carries, states that the name you gave sorts below that window, and says plainly that it
  cannot settle whether such a release was ever cut. Everything it could substantiate is
  unchanged and still there: the same `out-of-window section` opening (it is never laundered
  into `unknown section`), the window's count and span, the two openable addresses the full
  history sits at, and the pointers at `<accessor>_sections()` and
  `capabilities(full=True)["docs"][...]["sections"]`.
- **Four Drive disclosures now quote Lark's OWN reason, so their text is different bytes.** A
  `code: 0` from `POST /open-apis/drive/v1/metas/batch_query` with an **empty `metas` array** is
  not an answer: it is a refusal whose reason sits in a sibling key, `failed_list`. Four legs in
  this library disclosed the **missing field** and never read that key, so a refused token
  produced *"Lark returned no title for &lt;token&gt;"* — which reads as *the folder has no
  title* rather than *Lark would not resolve this token*. On a degrade path the message **is** the
  product, so this is a fix, not a cosmetic change. The affected text: `folder_name`'s *"Lark
  returned no title"* disclosure, `document_security_level`'s *"carried no security-level key at
  all"* disclosure, the member listing's *"the metadata answered with no owner_id"* owner note,
  and the file `permalink` refusal's *"answered success but reported no URL"*. Each now **appends**
  a sentence naming Lark's own `failed_list` code for the token you sent (or says plainly that the
  answer named no reason at all). **Nothing was removed or reworded** — if you match on those
  phrases you still match; if you match on the whole string, it grew.
- **Behaviour, types and dispositions are unchanged.** Every one of those four legs answers the
  way it always did: `folder_name` and `document_security_level` still degrade to their typed
  value with a disclosure, the owner read still degrades to `None` with a note, and the file
  `permalink` still **raises**. No return type, field, optionality or exception class moved, and
  no leg gained or lost an API call.

- **What a delete leaves resolvable is now a number instead of a hint — and it is our own
  number.** The guide used to say only that a removed object's *"metadata still resolves"*, naming
  one route. Measured here on 2026-08-31, against a document this project created and then
  removed: of **five** routes probed, **one still answered** — the Drive metadata query
  (`metas/batch_query` with `doc_type: "docx"`) came back with the removed document's title,
  owner, timestamps and url and an empty `failed_list`, while the document meta and the document
  body route both answered `1770003 resource deleted`, the named-versions route answered
  `1068404`, and the parent folder stopped listing the token as a child. **Plan for the trap:** if
  your ledger asks only the metadata route, a document you deleted still looks present.
  **And plan for the limit, which matters more than the number:** none of the five separates
  **trashed** from **purged** — `1770003` says *deleted*, not *unrecoverable* — so **"removed" is
  the strongest true statement** any of them supports, and a claim that a document is gone for
  good needs something other than these reads. The measurement is one tenant, one document, one
  run; other tenants, regions and object types are unmeasured rather than refuted.

- **`capabilities()` now tells you which endpoints' scope requirement is UNKNOWN, instead of
  leaving you to read an empty list as "needs nothing".** Each surface in the no-argument summary
  can now carry an `unknown_requirements` key beside its `scopes` / `optional_scopes`. Its values
  are **endpoint names** — nothing else, no sentences — and each one is a key of the
  `unknown_requirements` catalog in `capabilities(full=True)`, where the reason it is unknown is
  spelled out. The key appears only on a surface that has at least one such endpoint; on the fix
  tree that is 13 of the 17 surfaces, and it is derived from the registry on every call, so the set
  moves by itself.
  **Read the two keys together from now on.** A short or empty `scopes` list does not mean a
  surface needs no Lark permission — it can also mean no scope was ever observed demanded for some
  of the endpoints it calls, which this library records as unrecorded rather than guessing at. Six
  surfaces printed an empty list and read as *needs nothing*; seven more printed a list that looked
  complete and was not. The `reading.this_is` sentence at the top of the summary says this now, and
  points at the key.
  **Nothing about the library's behaviour or its permission requirements changed — only what it
  discloses.** No scope was added, widened, filled in or requested; the permission registry, the
  shipped guide, `preflight` and `capabilities(full=True)` are unchanged (the full payload is
  byte-identical), and every one of them already carried this fact. The summary was the one door
  that dropped it. If you parse the summary, the change is additive: a new optional key on a
  surface row, and a longer `reading.this_is` string. The summary grew from 13,045 to 15,268 bytes
  and stays more than 20× smaller than the registry it indexes.

- **Two refusals that were true about the mechanism and false-sounding about your document now
  name the block class and where its text actually lives.** Both are text-only changes — the same
  requests still refuse, with the same typed reason. **(1) A sub-span edit anchored at a document
  page whose title contains your span** used to answer *"the span … does not occur in the text runs
  of block …"*, which reads as *those words are not in this document* while the title plainly says
  them. It now says the span **is** text of that block but not sub-span-editable text, because a
  page keeps its own words on its `title` and a sub-span edit reaches only the `content` text runs
  — so no span will match on that block, and lengthening or re-quoting it cannot help. **(2) A
  block this library could not render** keeps its source verbatim in a `markup` field, and used to
  be described as a *container* whose *"text lives in its child blocks"*, with the advice to
  *"target the text-bearing child block's id instead"* — a block that has no children at all, so
  that advice could never succeed. It now says plainly that the block is not a container, that its
  own text is the raw markup it carries, and that reading it works (`plain_text(node)` returns it)
  while no text-replacing write can patch it, whole-block or sub-span. Both messages point at the
  guide section that carries the rule and the node-class index, so there is one place to read it.
  **What did NOT change:** which blocks are editable, which are refused, and the refusal reason
  codes; the message for a real container (a table, a cell, a grid, a callout, a quote container),
  the message for an image or an embed, the diagram message, and the ordinary *span not in this
  block* message are byte-for-byte what they were. If you match on refusal `detail` text, the two
  cases above are the only strings that moved.

- **The docx download now hands you a value: where the file landed, and how that was decided.**
  `handle_download_command` — the function behind `larkdocio download` — used to return
  **nothing**, so if you called it from a program there were only two ways to learn where your
  Markdown had gone: pre-compute the routed path yourself (and be wrong the moment a document
  routed differently), or scrape the messages the run prints. And the `--dump` sidecar, which
  answers the machine-readable half of the same question, is written **into the routed directory
  you could not learn** — the answer sat behind the question. It now returns a `DownloadResult`:

  | Read | What it holds |
  |---|---|
  | `result.output_path` | the Markdown file that was written |
  | `result.output_dir` | the directory it landed in — **not always the `-o` you passed** |
  | `result.dump_path` | the `--dump` sidecar, or `None` when the flag was not given |
  | `result.doc_token` / `result.title` | the docx token that was read, and Lark's own title |
  | `result.routed` / `result.route_reason` | whether the root was rewritten, and why |
  | `result.route` | the whole decision as data — the same record the sidecar carries |

  **Nothing you already wrote breaks, and the reason is exact: nobody can be relying on a value
  that was never produced.** `None` → an object is invisible to every caller that was not asking.
  It is a `dict` subclass, so `result["output_dir"]`, `.get`, `in`, `{**result}`, `json.dumps` and
  `==` against a plain dict all answer — the same grammar the create verbs adopted in 1.41.0, so
  the read side and the write side now answer alike, and the attributes are **views** onto the
  body rather than a second copy of it.

  **`route_reason` is one of four values, and the fourth is why a boolean was not enough**:
  `explicit_route` (you named the subpath), a derived-route value (all three metadata rows found),
  an incomplete-derivation value (the derivation ran and did not find all three — `result.route` lists
  which rows were found and which were missing, so a two-of-three near miss reads differently from
  a document carrying none of them) and `routing_disabled` (the derivation never ran, which is a
  different fact from "ran and found nothing").

  **With `--dump`, the same record is in the sidecar under `route` — and there is no path in it.**
  Not the output root, not the derived subpath, not a `--route` you supplied. That is deliberate
  and it is the fence the whole design turns on: the sidecar is **byte-identical between two runs
  over an unchanged document**, which is a property you can key a ledger on, and a path is
  specific to the machine and the invocation. So two dumps of one document from two different
  `-o` roots still match byte for byte. **The sidecar also does not move** — it stays beside the
  Markdown in the directory the output landed in, named from the token, exactly as before; being
  unable to find it is fixed by the returned value naming it, not by relocating the file.

  **What did NOT change:** the Markdown written for a given document is byte-identical, which
  documents route where and how they always did, both routing log messages are word-for-word what
  they were, no CLI flag was added, and **no new permission, endpoint, scope or operation** — a
  richer return type is a report on work already done. If you want a Markdown string with no files
  written and no images fetched, that door is still `larkdocio.drive.read_child_markdown`.

- **`init_env(".env")` OVERRIDES credentials already set in your environment — and the guide never
  said so.** This is the half of this fix you can be bitten by, so it leads. `init_env` loads your
  `.env` with override semantics: if `LARK_READ_APP_ID` (or any other name in the file) is already
  exported — by your shell, by CI, by a test harness — the file's value **replaces** it, and a
  blank value in the file replaces it with nothing. Nothing about that changed in this release; what
  changed is that it is now written down, in the guide and in `init_env`'s own docstring. If you set
  credentials in the environment on purpose, point `env_path` at a file that agrees with them rather
  than expecting the environment to win.

  **Two more things that sentence understated.** The guide said `init_env()` *"creates an empty
  one"* if the `.env` is missing. It creates a **commented template** carrying the read-credential
  names with blank values — useful, but not empty — and it **creates missing parent directories**
  on the way there, so `init_env("config/local/.env")` makes `config/local/`.

  **And there is now an opt-out: `init_env(path, create=False)`.** Nothing is written, no directory
  is made, and a missing file raises `LarkConfigError` naming the path it looked for and the
  credential pair being resolved — so you find out, instead of receiving a file you did not ask for.
  `create` is **keyword-only and defaults to `True`**: every call you already have behaves exactly
  as it did. With the file present, `create` makes no difference whatsoever, override included.

- **A permission row that says an operation needs nothing now means it — and where the registry
  cannot tell, it says so in the row.** The endpoint derivation reads each call site's own code.
  It could not see a call site that imports the API **inside** the function body, so such an
  operation reported `api_using: false`, no endpoints and no scopes — indistinguishable from an
  operation that genuinely makes no call. It follows those imports now, and, more importantly, it
  **discloses what it still cannot resolve**: a `permissions` block in
  `capabilities(full=True)` can carry a new `unresolved_call_sites` list naming each seam and the
  function it is in, emitted only when there is one. **Read an empty scope list together with it**,
  exactly as you already read one together with `unknown_requirements` — empty plus nothing
  unresolved is a measurement; empty plus a seam is a recorded unknown.
  `check_permissions(...)` follows the same rule: `requirements_for_operations` has a fifth state,
  **`undetermined`**, for an operation whose derivation could not be completed, it is reported in
  `blind_spots`, and an operation whose scopes ARE known but which carries a seam is named there
  too. One shipped operation is in that state today — the Base column-type migration
  (`base-schema-write`.`migrate_field_type`), a composed leg whose three clients are handed in — and
  its scopes are covered by the surface's other operations, which is why nothing you hold changes.
  **Two Base read operations gained an endpoint** they always reached: `read_base` and
  `read_base_markdown` now list the records `batch_get` route, whose scope the Base read surface
  already required, so no surface's scope list moved and no new grant is needed. Nothing here
  widens, requests or escalates a scope — the library describes requirements; a grant stays a Lark
  console action.

### Upgrade & compatibility

- **No public symbol, command, flag, refusal prefix, credential or scope requirement moved.**
  Both refusals keep their opening words (`unknown section` / `out-of-window section`), so a
  caller keying on the prefix is unaffected. **If you match on the refusal TEXT**, note that the
  phrase `is a real release` no longer appears anywhere in it — that is the sentence this
  release removes, and it is the only removal.
- **Rendered Markdown is untouched.** Nothing in the read or write path changed; the same
  document converts to the same bytes.
- No dependency was added, dropped, or moved.
- **The one import-time `DeprecationWarning` you see is not ours, and no pin moved to chase
  it.** `import larkdocio` emits exactly one `DeprecationWarning` on Python 3.12 and newer, out
  of `lark_oapi/ws/pb/google/protobuf/internal/well_known_types.py` — a protobuf **vendored
  inside `lark-oapi`**, calling `datetime.utcfromtimestamp()` at module scope. The `protobuf`
  distribution is not installed at all, and larkdocio's own code touches no protobuf. **A pin
  move would not clear it, and that was measured rather than assumed:** the newest published
  `lark-oapi` (1.7.3, against the pinned 1.5.3) still carries the identical line at the identical
  path. The limit of that evidence, plainly — the published wheel was downloaded and **inspected
  without installing it**, so what is established is the presence of the source line and not an
  executed import of that version, and the versions between the two were not checked. **Nothing
  here suppresses the warning**, deliberately: a library that edits its consumer's warning
  filters silences a diagnostic the consumer never asked to have silenced, in a process the
  consumer owns. Filter it in your own test configuration if it is noise to you — the README's
  dependency section now carries the whole record.
- **If you wired the advisory update nag, CHECK WHERE YOUR HOOK ACTUALLY LANDED — it may never
  have run.** The recipe we shipped told you to copy the template to `.git/hooks/post-merge`.
  That is only correct when `core.hooksPath` is unset; when it is set, git reads hooks from that
  directory and **only** that one, so the hook you installed was never called — no warning, no
  error, and a `git pull` that should have nagged you said nothing. Because the nag is quiet
  when you are up to date, there was nothing to notice. To check and repair, from your repo
  root:

  ```bash
  HOOKS="$(git rev-parse --git-path hooks)"   # where git really reads hooks
  mkdir -p "$HOOKS"
  cp scripts/larkdocio-post-merge.hook "$HOOKS/post-merge"
  chmod +x "$HOOKS/post-merge"
  git hook run post-merge                    # proves it: prints the nag's own line
  ```

  If `$HOOKS` comes back as something other than `.git/hooks`, your old copy was dead and you
  have not been told about any release since you installed it — worth a
  `scripts/update_larkdocio.sh --check` now. The stale copy in `.git/hooks` is harmless; delete
  it if you like. `git hook run` needs git 2.36 or newer; on older git, merge something and
  watch for the `[larkdocio]` line.

### Known limitations

- **This copy still cannot tell you whether a version outside its window exists.** It carries a
  window of the newest releases, not the whole history, and that is deliberate: making the wheel
  able to verify any version would mean shipping every release ever cut, or a manifest of them.
  So for an out-of-window name the honest answer is the one it now gives — *this copy cannot
  say* — and the two addresses it names are where that question is settled.
- **Grammar at a one-section document.** The section-count messages agree with their count now
  ("1 section", not "1 sections"). At the counts this wheel actually ships, the emitted text is
  byte-for-byte what it was, so nothing you match on moves.
- **TRASHED and PURGED are not separable for a folder, by either route that can see one.** Two
  routes discriminate a folder's existence — the folder listing, and `metas/batch_query` with
  `doc_type` spelled `"folder"` (the one most callers miss). Both answer the same way for a folder
  sitting in the trash and for one that is gone for good, so **"removed" is the strongest true
  statement** you can make from either — *"trashed"* is not measurable from these reads, and
  neither is *"restorable"*. If your ledger needs that distinction it has to come from somewhere
  else. Related, and worth knowing before you reach for the endpoint yourself: the **`doc_type`
  spelling is load-bearing**. Send the wrong one at a folder token — `"docx"` is the common slip —
  and you get `code: 0` with an empty `metas`: the shape of an answer with no answer in it. The
  shipped guide's folder-read recipe now teaches both routes, the spelling, and both measured
  controls with their dates.
- **A truncated folder listing is still not evidence of absence.** `complete: False` means the
  walk stopped, not that a child is gone. Unchanged; restated here because the existence-oracle
  guidance above is the place people will look for it.
- **The two round-trip working-directory filenames are DERIVED, and the spellings are not
  promised.** `roundtrip pull` writes `document.snapshot` and `document.md`, and the documents
  only ever showed you those literals — the derived surface appeared nowhere. They are the values
  of `roundtrip.SNAPSHOT_FILENAME` and `roundtrip.MARKDOWN_FILENAME`;
  `roundtrip.snapshot_path()` / `roundtrip.markdown_path()` join either onto a working directory;
  and `pull()` already hands both back joined, as `PullResult.snapshot_path` and
  `PullResult.markdown_path` — **that pair is the one to hold.** What is promised is the pair of
  paths on the result, **not** the two spellings: a hard-coded `"document.md"` is a copy of a
  value rather than a read of it, and it is the copy that goes stale. Neither name has moved
  since the verb shipped, which is a fact about what happened and not a commitment. A shell
  caller cannot import a constant, so print the current values instead:
  `python -c "from larkdocio import roundtrip; print(roundtrip.SNAPSHOT_FILENAME, roundtrip.MARKDOWN_FILENAME)"`.
  **No code changed** — what changed is that the packaged guide's round-trip recipe now says all
  of this beside its "Two files, two owners." bullet.
- **Metadata-table auto-routing trusts the value cell, so an untouched template routes into a
  tree named after its own labels.** The derivation asks only whether the three metadata rows
  are **present**; nothing checks that a value cell holds a real value. A
  template still carrying its placeholders therefore routes — at **exit 0**, under the **same**
  warning-level notice a correct route emits, and with `routed` true and `reason` set to
  the derived-route value on the returned `RoutedPath`. The record you were given so you could stop
  reading log text reports, on this input, exactly what it reports for a correct route. `TBD`
  lands under `tbd/tbd/tbd`, `N/A` under `na/na/na`, `???` under `untitled/untitled/untitled`,
  and — the sharp one — angle-bracketed placeholder labels route under the **labels' own
  names**, because angle brackets are stripped like any other OS-reserved character. That last path looks entirely plausible on disk. **Routing behaviour is
  unchanged in this release**; what is new is that the packaged guide says so, with the derived
  paths shown. If it matters to your pipeline: switch the derivation off with its config key and
  name the destination with `--route`, or read the returned record and check the segments
  against your own list of placeholder spellings before you trust the path.

## [1.43.0] — 2026-08-31

### New capabilities

None.

### Behavior changes you can observe

None. No public symbol, CLI command, flag, refusal code or rendered Markdown moved; the same
input produces the same bytes it did before this release. What changed is the **consumer
update script template**, which is not part of the wheel — see below.

### Upgrade & compatibility

- **Re-copy the update-script template into your repo — your copy silently vendors the WRONG
  WHEEL under some conditions, and tells you it succeeded.** (Your `scripts/update_larkdocio.sh`,
  whose own header names the development-repository template it was copied from.) The defect fires
  exactly when the `dist` fast path bails out and the build-from-tag path runs — which is the case
  the build path exists to cover, and the case you are in whenever `dist` lags the tag you asked
  for. The fast path's shallow clone and the build's output landed in the **same** scratch
  directory, and the script then picked between the two wheels by **sort order**: it built the
  version you asked for, vendored the older one, printed the old filename beside the new tag on a
  single success line, and exited **0**. The pin it printed pointed at the stale wheel, and
  `./vendor/` was left internally inconsistent — an older wheel sitting beside the newer release's
  changelog and release notes. **You cannot discover this from your own repo**, which is why it is
  here rather than only in the development log. **Three fixes, and all three are in the template you
  are re-copying:** the two scratch directories are now separate constants that no branch-name
  setting can collide; selection **refuses** rather than guesses when it finds more than one
  candidate wheel, listing what it found and saying nothing was vendored (the same posture the
  script already took for a `vendor/` holding two wheels); and the success line's own claim — that
  the file it vendored is the version of the tag you asked for — is now **checked before it is
  printed and before `./vendor/` is touched**, so a mismatch stops the run naming both versions
  instead of clearing your existing pin. **After re-copying, re-run the refresh and check the
  wheel's version against the tag you asked for** — if you refreshed while `dist` lagged, what you
  have vendored may be older than you believe. No wheel API, command, credential or scope
  requirement moved: this is the copied consumer script only, and a re-copy is a harmless no-op if
  your repo already carries these fixes.
- No dependency was added, dropped, or moved.

### Known limitations

- **The repair is scoped to the BUILD path, and the fast path's own selection is unchanged.** When
  the `dist` fast path serves you, the script still picks the wheel out of its shallow clone by
  **sort order** — the same mechanism that failed above. It is safe *because that branch carries
  exactly one wheel by construction*: it is republished as a single commit that replaces the
  previous one. That is now written down rather than assumed, which is the point — the defect above
  existed because a comment asserted a directory could not hold two artifacts and stopped being
  true when something else began writing there. If the distribution branch ever carries two wheels,
  the same class of fault returns on that path, and it would again be quiet. Deliberately left
  alone here: making it refuse would change *when* the script falls back to building, which is a
  behaviour change this fix did not want to smuggle in.

## [1.42.0] — 2026-08-31

### New capabilities

None.

### Behavior changes you can observe

- **A document whose metadata table has EMPHASIZED key cells now routes, where it used to land
  flat.** `-o` is the root such a document is routed under: carry the three metadata table rows
  and the file lands in the subpath derived from their values. Until now those label cells had to be the **bare** label, so
  a template that bolds its metadata keys — `| **Label** | Value |`, a very common shape —
  matched nothing and the document was written flat into the `-o` root you passed. Nothing
  failed while it happened: the download succeeded, the exit code was 0, the file was written,
  and the not-routed notice was at info level only.
  **What is tolerated now.** Every emphasis this converter can put on a label — bold, italic,
  strikethrough, underline, an inline-code span, and any nesting of them, in both the Markdown
  and the HTML-tag rendering mode. That set is what the converter itself emits, which is why it
  is the boundary: for italic it writes `_label_`, never `*label*`. The single-asterisk spelling
  is tolerated as well, for a label this converter did not write. An emphasized label routes to
  the byte-identical path the plain label routes to.
  **What did NOT change.** The **value** cell is read exactly as before, through the same
  normalization and nothing else — this fix does not touch it. The three labels, their
  case-insensitivity, their order in the derived path and the filename stamp are unchanged.
  A document with only two of the three rows still routes nowhere, emphasized or not, and still
  says so at info level. The off-switch config key still switches the whole thing off before any
  detection, silently.
  **THE ONE THING TO CHECK BEFORE RE-VENDORING.** This is strictly widening — a document that
  routed before routes to exactly the same place — but a document that did **not** route before
  because its keys were bolded will now be written to a **different directory** than it was on
  the previous wheel. If you have tooling that expects those documents flat in the `-o` root,
  that is the one behavior to look at. The only off switch is that config key, and it is
  all-or-nothing — it stops routing for **every** document, not only the ones this release newly
  routes — so reach for it only if you want the whole corpus flat. To place a single document by
  hand instead, `--route A/B/C` overrides routing for that one invocation.

### Upgrade & compatibility

- **No dependency moved** — nothing added, nothing dropped, no pin changed.
- No public symbol, CLI command or flag was added, renamed or removed. Only where a
  bolded-key metadata document lands has changed, as described above.

### Known limitations

- A metadata table containing **merged cells** renders as an HTML table with no pipe rows at
  all, and has never routed in any version — emphasis tolerance does not change that.
- On the **value** side, a value wrapped in backticks keeps its backticks through
  normalization (`` `ExampleValue` `` becomes `` `examplevalue` `` in the path). That is unchanged
  here and deliberately left alone.

## [1.41.0] — 2026-08-26

### New capabilities

- **You can now tick and untick a checkbox on a document you already have, through the same
  gated route you use for everything else.** Flip `- [ ]` to `- [x]` on that item's line in an
  edited block-identity projection, reconcile, preview, apply — the bit moves, the item keeps
  its block id, and the item's own text is **not** rewritten, so styling inside it survives. It
  works in both directions, needs no new permission, and rides the plan gate, the whole-document
  revision guard and the refusal set exactly as a text edit does. The plan entry and the
  apply-log entry both carry `todo_done`, which is how you tell a flip apart from a text edit
  that happens to leave the text alone. If you had reached for the raw block route to do this,
  you no longer need to.

**READ THIS IF YOU EVER FLIPPED A CHECKBOX AND GOT A GREEN RUN.** Before this release that
call **succeeded and did nothing**: the plan was `ok`, the apply log said `applied`, and the
checkbox on the document did not move. That is fixed, and the fix has two visible outcomes
depending on what your edit actually changed. **The discriminator is simple: what is different
between the projection you were given and the Markdown you handed back.**

1. **Only a checkbox differs** (or a checkbox plus text) → **the bit now actually moves.**
   Nothing to change on your side. A run that previously reported success and left the document
   alone now reports success and changes it. If you built a workaround — a second pass, a
   delete-and-recreate, a raw call — it is now redundant, and a delete-and-recreate will still
   cost you the block id it always did.
2. **The difference is a property this route cannot write** → **the call now REFUSES, typed,**
   with `change-not-expressible`, naming the property and telling you to delete the block and
   insert its replacement. Nothing is written and nothing is compiled. Which properties: a code
   block's fence language, a diagram's theme, a list item's nesting — and, the case most likely
   to surprise you, **a different Markdown spelling of the same block** (`- item` for `* item`,
   or an editor that reformatted a line without changing what it says). Those all previously
   returned a green apply log and changed nothing at all, so this is the same non-event you
   already had, now stated out loud instead of hidden. A document you did **not** change is
   still not a change and is still not refused: an unedited projection reconciles to zero
   changes exactly as before.

The machine-readable form of the boundary is the docx-write surface's `absences` register,
under `no-block-property-edit-beyond-text` — it replaces `todo-done-bit-is-not-editable`, whose
statement (the bit cannot be changed; an edit that tries reports success) is now false. If you
read that register by **index** rather than by `id`, note that the replacement took the same
slot on purpose: no other row moved.

- **A successful insert's apply-log entry now tells you what it cost, and whether it was
  atomic.** Every `inserted` entry **the engine performs** carries two new keys: `mutating_write_calls`,
  the number of mutating write calls the engine actually issued for that entry, and `atomic`,
  which is `true`
  when that count is one and `false` otherwise. An `atomic: false` insert means a failure
  partway through could have left part of that content in the document — a table built across
  several calls is the case that motivated this — where `atomic: true` means it landed whole or
  not at all. Read them off the entry (`entry.mutating_write_calls` / `entry.atomic`) or off
  its JSON. **The number is a measurement, not a prediction**: rely on the keys being there and
  on the unit (mutating write calls — a paginated read is not one, and one batched call
  carrying many updates is exactly one), but do not rely on the number for any given content
  and do not compose to a boundary you infer from it. How the engine gets content into a
  document is internal and changes without notice. The contract is stated in full in
  `larkdocio guide` (§ "What authoring a table costs, and where the 500-cell cap comes from")
  and on `ApplyLogEntry` itself.
- **`WriteClient.patch_block` now states its cost at both doors you can reach it through** —
  its own docstring and the guide's write-recipe router. *(Scoped in time by the `patch_block`
  fence later in this same release, and not rewritten: there were two such doors when this
  entry landed. The public `WriteClient.patch_block` now RAISES `FencedPrimitiveError` and
  sends nothing; `PATCH_BLOCK_COST` was re-projected onto the internal `_patch_block`'s
  docstring. Everything this bullet says about the cost is still true **of that internal
  method**; what is no longer true is that you can reach it through a public door.)* It is outside the plan gate, outside
  the `STALE_DOCUMENT` whole-document compare-and-swap and outside the refusal set, so nothing
  previews it, no drift is detected for you, no typed refusal is raised on your behalf, no
  apply-log entry is written — and **the caller owns the read-back**. What it does that the
  gated route cannot is in-place, identity-preserving mutation: the block keeps its id. It is
  **not** the only route to any shape; delete-and-recreate reaches the same content through the
  gate, at the price of new block ids.
- **Those two disclosures — the insert apply-log's cost keys and `patch_block`'s stated cost —
  changed no behaviour.** No route changed — the same content still takes the same path, at the
  same cost, in the same order. Nothing was fenced, deprecated or renamed **by them**, and
  `patch_block` was still exactly as callable as it was **at the point those two disclosures
  landed**. (The capability below it **is** new; this sentence covers the two disclosures it
  names and nothing else. **And its last clause has since been overtaken inside this same
  release** — see *"`WriteClient.patch_block` is gone from the public surface"* under **Behavior
  changes you can observe**. The reason these disclosures were written — that door could be
  reached without a warning — is exactly the reason the door is now shut; only the conclusion
  moved.)
- **You can now add a row to a table that already exists, through the gated route — and the
  table keeps its block ids.** `GrowTableRequest(anchor=AnchorById(block_id=table_id))` appends
  one row at the end, inside the same `dry_run` → `apply` gate, the same whole-document revision
  guard and the same refusal set as every other change. The table's own `block_id` and every
  pre-existing cell's come through unchanged, in the order they were in — **so the
  identity-preserving route is now the supported one.** If you were reaching for the raw block
  route to add a row, this is the route that replaces it. Anchor it by the table's id, or by a
  `TableLocator` whose row-key names one of its rows. It needs **no new permission**: it rides
  the block `PATCH` your other write calls already use. The apply-log entry names the cells that
  came into existence, in row-major order, which is what you fill next — one cell edit each.
  Recipe: § "Recipe: add a row to a table that already exists" in `larkdocio guide`.
- **It is APPEND-ONLY, and here is exactly where the edge is.** One row per request, at the
  **end**. Two rows are two requests — deliberately, because that keeps every entry to exactly
  one write call, so `atomic` on the log is true and can never claim a partial landing it did
  not have. What it will **not** do: remove a row or a column, add a **column**, or insert a row
  in the **middle**. A `row_index` other than `-1` is **refused, typed
  `table-grow-unsupported`**, naming `-1` as the remedy — and the refusal says plainly that any
  other index is **unmeasured** by this library rather than something Lark was seen to turn
  down. **Rows past 200 are unmeasured too, and are attempted rather than refused:** the row
  axis has been taken to 200 with no refusal at any row, the authoring cap is 500 cells, and no
  platform row cap has ever been observed here — so this release does not invent one. A grow
  that would take the grid past the 500-cell cap refuses under the same reason, with a second
  table as the remedy; that cap is this library's own, and it is the one that already refuses an
  authored grid of that size. For anything on that list, the route is what it was: author the
  table again at the shape you want and delete the old one, which costs the block ids of the
  table and of every cell in it.
- **A conserved block can now tell you whether its body came back changed — and it is a
  disclosure, not a verdict.** A conserved-opaque plan entry carries `body_differs`.
  body_differs discloses that the block's body read back differently from the Markdown the
  projection emitted for it. That is one fact and it settles nothing: EITHER the consumer
  edited that body, OR the projection reshaped it and the editor normalised the reshaping. The
  plan asserts neither reading and compiles nothing either way — the block is conserved, left
  exactly alone. None means no opinion, which is not the same as False: a conserved block whose
  marker never came back has no read-back to compare. **Nothing refuses on it** and no new
  refusal reason exists: refusing on a fact that ambiguous would turn away pushes against
  documents nobody edited, wherever a conserved block's Markdown is not round-trip stable.
  `plan.conserved_block_ids_that_read_back_differently` is the subset it names — use it for
  *which conserved block do I look at first?*, never as evidence that an edit happened.

### Behavior changes you can observe

- **TWO THINGS THIS DOCUMENTATION TOLD YOU WERE WRONG, AND ARE NOW STATED CORRECTLY.** No
  behaviour moved for either; what moved is what the library says about itself, and both were
  wrong in a direction you could have planned around.
  **(i) Not every Drive write reports an independent read-back.** The wheel's `METADATA` body,
  the CLI `--help` and several places besides said each of the four Drive write legs verified
  itself that way. Only **one** does: `drive-access-write` declares `read-back-is-the-verdict`
  and follows each grant / update / revoke with an independent member read. The **versions**
  leg reads the head revision *before* its write, not after. **`create_folder` is exactly one
  call and reads nothing back** — you get Lark's own answer. Each leg's own
  `safety_contracts` in `capabilities(full=True)` is now the statement, and the prose is scoped
  to it. If you relied on the blanket promise, add your own read-back on the two legs that do
  not make it.
  **(ii) The docx write surface has FIVE body-writing request families, not four — and the
  count is now genuinely derived.** The guide said `EditRequest`, `InsertRequest`,
  `DeleteRequest`, `SubSpanEditRequest` *"and no more"*, stamped **derived from the shipped
  surface**, while the derivation behind it was a hand-typed tuple; `GrowTableRequest` shipped
  earlier in this same release and never joined it. The enumeration is now read off the op
  registry — each registered op declares whether it writes the document body or the review
  conversation — so a future family joins the answer by existing. **The conclusion that
  enumeration serves is unchanged**: none of the five relocates a block, there is still no move
  or reorder operation, and a whole-document reorganisation is still delete-and-recreate.

- **`WriteClient.patch_block` is gone from the public surface. READ THIS IF YOU HAVE EVER
  CALLED IT.** It was the raw single-block PATCH, and it took your oneof body **around**
  everything this library sells: outside the plan gate (nothing previewed it, no `Plan` recorded
  it), outside the `STALE_DOCUMENT` whole-document compare-and-swap (a document edited under you
  was not detected) and outside the refusal set (no typed refusal on your behalf, no apply-log
  entry). A green call proved nothing and the read-back was yours. **Nothing stopped a caller
  firing an unproven field mask at a document a refusal had just reported as under concurrent
  edit.** So the door is shut.
  - **What you will observe.** **Import and attribute lookup are unaffected** — `from
    larkdocio.write import WriteClient` still works, `WriteClient` still constructs, every other
    method is untouched, and `hasattr(client, "patch_block")` is still `True`, so a defensive
    capability probe does not change its answer. **The break is at CALL time and it is typed.**
    `client.patch_block(...)` raises `larkdocio.errors.FencedPrimitiveError`, which is both a
    `LarkDocIOError` (so `except LarkDocIOError` / `except LarkConfigError` already catches it)
    **and** an `AttributeError` (so an `except AttributeError` you wrote around a name you were
    unsure of also catches it). **Nothing is sent to Lark** — the refusal is local, before the
    wire. The message names the route to use instead; it does not say only "deprecated".
  - **The exact migration action — and both of the edits this method was used for now have
    a gated route, which is why this door could finally close.** *Ticking or unticking a
    checkbox:* flip `- [ ]` to `- [x]` on that item's line in an edited block-identity
    projection and reconcile — the item keeps its block id, its text is not rewritten, and the
    plan and apply-log entries carry `todo_done` (see the first entry under **New capabilities**
    above). *Adding a row to a table that already exists:* a `GrowTableRequest` through `dry_run`
    and `apply` appends one row at the end and keeps every pre-existing block id, in order (also
    above). *Anything else:* author the replacement and delete the old block through the same
    plan gate — that reaches the same content, at the price of new block ids. Every one of those
    is written out end to end in `larkdocio guide` (the write-recipe router).
  - **If you are on an older wheel, nothing happens to you.** The wheel you vendored is
    unchanged and still carries a callable `patch_block`; this only reaches you when *you* choose
    to bump. There is no window, no deprecation period and no clock: the name is fenced from
    this release onward, permanently, and it keeps answering forever so that a call always gets
    told what to do rather than an `AttributeError` with no advice.
  - **This supersedes something said earlier in this same release.** Under **New capabilities**
    above, the disclosure entry says `patch_block` "was still exactly as callable as it was" —
    true when it was written, and no longer true now. The *reason* that disclosure existed is
    preserved unchanged and is precisely why the fence exists; only the conclusion moved, from
    *disclose the public door* to *there is no public door*. The primitive itself was **not
    deleted** — it is internal now, and every one of this library's own gated writes still runs
    through it, which is why none of them changed behaviour (see **Upgrade & compatibility**).
- **The `stale-document` refusal now tells you what the guard watches, and what re-planning
  costs whoever edited beside you.** **The guard's behaviour is unchanged** — the same drift
  refuses the same whole batch with the same zero writes. What changed is a **disclosure of an
  existing limit**: a caller relying on the whole-document compare-and-swap to protect a
  co-editor's earlier text was already unprotected, and the library now says so. Every
  `stale-document` detail (both the drift refusal and the conservative could-not-confirm one)
  now carries two more statements. First, the **window**: the guard compares the revision the
  plan was built on against the revision read immediately before the batch, so it sees an edit
  that lands inside that window and nothing else — text that arrived **before** the plan is
  already part of the tree the plan was computed from, the two revisions compared are the same
  one, and no refusal is raised for it. Second, **what the recovery costs**: re-download,
  rebuild, re-plan is still the recovery, but the re-downloaded tree already contains the other
  editor's words, and a whole-block edit re-planned against it replaces the block entire and
  carries those words away with no further refusal. The remedy names the sub-span edit as the
  route that preserves them **and states its limits** — narrative blocks only, a span inside a
  table cell is out of scope, the span must occur exactly once, and a span crossing runs of
  differing style or overlapping a non-text inline refuses `span_not_splittable` — and says what
  to do where that route does not apply: build the whole-block replacement out of the block you
  just re-read. The same two statements are in `larkdocio guide` § "Do not edit the document
  while an authoring session runs", carried there byte-for-byte from the library's own constants.
  **Nothing was added to a success path**: neither statement appears in `plan.revision_guard_detail`
  or in `roundtrip push` output, and no new refusal reason, field or default was introduced.

- **The "you did not say where this goes" refusal now leads with the remedy that costs you
  nothing, and tells you what the other one costs.** When a create is refused for having no
  destination, the message used to offer `create_folder(name, parent_token)` **first**. That is
  the remedy with a permanent consequence: **larkdocio ships no verb that deletes a folder** —
  the Drive delete route was measured to work and was deliberately left unshipped, so a folder
  you create through this library is permanent as far as this library is concerned, and
  **creating the same name twice under the same parent makes a second folder** rather than
  reusing the first, so a retry is not idempotent. The refusal now leads with **a folder you can
  already open** (take the token from its link) and states both of those costs before you reach
  for the other route. The same words are in `larkdocio guide` § "Where a new object goes",
  carried there byte-for-byte from the library's own constants.
  **`DriveClient.root_folder_token()` is named there as a NON-destination**: it answers the
  token of the application's own root — the unbrowsable space the whole rule exists to keep
  things out of — so it must never be passed as a `folder_token`. It stays public and stays in
  the drive-read matrix; reading that space is a legitimate thing to do, filing new objects into
  it is not. **The guard's behaviour did not change**: the same inputs are refused and the same
  accepted, still locally and before any call is spent. *(Scoped in time by the typed-root
  refusal later in this same release, and not rewritten: that was true of the guard when this
  entry landed. One input class has since moved — the value `root_folder_token()` answers is
  now refused by TYPE, where a plain folder-shaped string is still accepted.)* **If you assert on the refusal string,
  it changed** — assert on `MissingDestinationError` instead.
- **The guide no longer describes an unaddressed document create as something you can choose.**
  Two passages used to walk through what happens when `folder_token` is left out, worded as if
  that were a live option — it never was: the destination is required, and the closest a caller
  can get to omitting it is either the library's own local refusal (pass `folder_token=None` or
  another refused spelling) or Python's own `TypeError` if the keyword is left out of the call
  entirely. **Nothing about the signature changed** — `create_document` and
  `create_spreadsheet` have been keyword-only with no default for a while — only the disclosure
  is new, and it now appears in both docstrings and the guide's create recipes. *(Scoped in
  time by the `create_document` destination change later in this same release, and not
  rewritten: the signature really had not moved when this entry landed. It moved afterwards —
  `create_document(self, title='', *, folder_token=None)` — so on `create_document` an omitted
  keyword now reaches `MissingDestinationError`, never `TypeError`, and the guide's twin
  sentences were transformed in that same change. This clause stays true, unchanged, of
  `create_spreadsheet`. See the Upgrade & compatibility section.)* If you had
  planned a call around the removed no-`folder_token` option, it never actually worked; pass a
  real folder token instead.
- **A newly created Base's default table is now disclosed where you create one, not only in the
  guide's Base recipe.** `create_app`'s own docstring now says a fresh Base arrives with one
  table it made — not one you asked for — and points at the guide's existing explanation rather
  than repeating it. The table itself is not new: it already shipped, and the guide already
  documented it.
- **A document you just created now has a documented way to find its own URL** — scoped to
  docx, where the create's own reply has never carried one. List the folder you created it in
  and read the listing's own `url` field back; it is `Optional`, because Lark does not always
  send one. `create_spreadsheet` and `create_app` already hand back a `url` directly, so this
  gap was docx-specific.
- **The docx write handshake now warns that `create_document(title=…)` already renders an H1.**
  A following `heading(1, …)` makes a **second** H1, not the section's only one; give the first
  heading a level of 2 or lower, or let the title stand alone.
- **A successful `roundtrip push` no longer describes its concurrency guard in the words of a
  refusal — the text on the first line moved.** Every push, preview and `--apply` alike, used to
  open with `plan for <token>: N change(s), STALE_DOCUMENT guard active`. That sentence was
  accurate — it reported that the whole-document compare-and-swap was armed — but it spent the
  refusal's own name on a run that had refused nothing, and there was no word anywhere in a
  success message meaning *"this did not refuse"*. It now reads
  `plan for <token>: N change(s), concurrency guard active` (or `… concurrency guard
  unavailable`). The same wording is used by the warning printed when a snapshot carries no
  document revision and the guard cannot be armed. **If you parse push output, this line moved**:
  match on `concurrency guard <state>`, and note that `STALE_DOCUMENT` now appears in push output
  only where it always belonged — in an actual refusal.
- **The `revision_guard_detail` field says the same thing the same way.** The armed disclosure a
  caller reads from `Plan.to_dict()["revision_guard_detail"]` (and from a `PushResult`) used to
  open *"the whole-document compare-and-swap (STALE_DOCUMENT) is ACTIVE … refuses the ENTIRE
  batch with ZERO writes issued"* — a state and a consequence in the same breath, the second half
  readable as a report of what just happened. It now says the guard is **ARMED**, states plainly
  that nothing has been refused, and puts the consequence in the conditional (*"IF IT EVER
  FIRES…"*). Every clause of substance is still there. **The guard's behaviour did not change** —
  what it refuses, when it refuses, and with what refusal are all exactly as before, so there is
  no behaviour fix here to go looking for.
- **The round-trip push refusal for "this reconciles to no change" now tells you both things
  it could mean, and names the blocks involved.** Pushing an edited Markdown file that
  reconciles to nothing has always refused rather than reporting a successful no-op. The text
  it refused with named a single cause — *edit that file, keep the markers where they are* —
  which is true only when the file genuinely did not change. It is not true for the other
  consumer who reaches the same branch: one whose real change landed inside a block the
  authoring dialect cannot re-express, which the engine conserves untouched by construction,
  so the change reconciles to nothing and is not written.
  The refusal now says both, names the conserved block ids, and gives each possibility its own
  remedy. It **does not claim to know which of the two happened** — it cannot: a plan for an
  edited document and a plan for an untouched one are identical here, so an accusation either
  way would be a guess dressed as a diagnosis. When a document has nothing conserved, the
  previous wording is unchanged. This message reaches you as the raised error's text, whether
  you read it as CLI output or catch the exception.

- **The packaged guide's first reading recipe corrected a wrong example.** The guide's
  earliest walkthrough of the two tree-reading functions demonstrated calling `plain_text` on
  a table cell and printing the — always empty — result as if it were the cell's content: the
  exact pattern that silently returns nothing for every table, grid, or callout, which is
  usually where a document keeps its numbers. The recipe's stand-in tree now includes a table,
  so the example runs the branch it shows; the rule for what `plain_text` returns is now
  quoted directly from the function's own documentation, placed beside the code it explains
  instead of stated separately several lines above it; and a generated reference table lists
  every node class the library ships, answering two questions per class — does it carry its
  own text, and does reading descend into it — so a class answering no to both reads as such
  rather than being mislabelled a container. **No API changed**: `plain_text` and `walk`
  behave exactly as they always did; only the guide's own words were wrong.

- **The write-recipe router — the table you read before choosing how to write — gained two
  rows for edits it had no row for, and lost a claim that was not true.** Nothing about writing
  changed; this is the router finally saying what the engine already did. There is now a
  **"change a checkbox"** row and an **"add or remove a table row"** row, and both exist to tell
  you the gated route does not serve them: flipping an existing checkbox is planned, reported
  `applied`, and does not move the bit (an open defect, named as one), and no plan-gated
  operation changes an existing table's grid — so each row names what does work today and what
  it costs, including the escape hatch's price (outside the plan gate, outside the
  whole-document compare-and-swap, outside the refusal set, read-back yours). **Both of those
  verdicts were overtaken later in this same release and this entry describes only what the
  router said when it was written:** the gated route now serves both — a checkbox flip and a
  one-row table grow are plan-gated operations (**New capabilities**, above) — and the escape
  hatch whose price this row disclosed is now fenced out of the public surface entirely
  (**Behavior changes you can observe**). What the two rows say today is what those entries say. The sub-span row
  now warns about more than styling: a whole-block change rewrites the block's text **as a
  whole**, from the copy you read, so text another writer added to that block after your read is
  replaced along with your edit — and the apply log calls that entry `applied`, because it was.
  Which posture to take on a shared document is yours; the guide states the mechanism and stops
  there. The whole-document row now says what happens to **tables** (they are conserved whole —
  a row you add or a cell you retype in the edited Markdown compiles to no request at all, and
  the run is green) and points forward to the conservation contract. And the row that claimed
  bold, italics **or a link** inside an edited block refuses the batch is corrected: a
  **labelled** link refuses, but a link whose label is its own url composes as plain unstyled
  text, which is the shape you write without noticing.
- **The authoring-dialect and lossiness tables — the two you read before composing anything —
  now say the three things they were silent about.** Documentation correction, **no behaviour
  change**, plus one additive line in `capabilities()` (below). (1) The `todo` row is no longer
  a plain creatable kind: the checkbox **state** is write-once, and an edit to it is reported
  *applied* while the bit does not move — **an open defect, not a designed limit**, and the row
  says so as loudly as the `mermaid` row beside it says it is create-only. (2) The whole
  register of what the docx write surface cannot do is now printed **in the guide itself**,
  right under the lossiness table, generated from the same data `capabilities()` returns, so
  the answer to *"can this library do X"* is in the document you were already reading. New
  accessor if you want the block yourself: `larkdocio.write.absences.docx_write_absences_markdown()`.
  (3) **A table cell cannot carry a link anchor** — the one styling a created run can carry
  stops at the cell boundary — and that fact now sits in the capability matrix and the dialect
  section, not only inside the file-link recipe. The block-support matrix agrees with the guide
  about the checkbox in its own notes.
- **Colour, and what a read does to emphasis, are now stated where you compose.** Nothing
  changed in either behaviour; the guide simply says it. The reader **does** emit character
  styling — a bold run comes back as `**x**`, italic `_x_`, strikethrough `~~x~~`, inline code
  in backticks, an underline as `<u>x</u>` — and `compose()` refuses every one of those markers,
  so the reader's own output of a styled run does not re-compose. **Colour is different: it is
  captured and never emitted**, so a coloured run reads back as plain text; there is no marker
  to refuse, which is why colour is an absence rather than a refusal row, and it is not
  authorable either. Existing styling you did not write is still safe — a whole-block edit keeps
  the styling around your change and a sub-span edit that would have to split a styled run
  refuses instead of flattening it.
- **The Base read recipe said "This surface is read-only, end to end" without naming its
  subject — and at least one reader took it to mean Bases are read-only and wrote that into a
  design document.** Documentation correction, **no behaviour change**: nothing about the Base
  read or write surfaces moved. The sentence now says which surface it is about, and points
  straight at the two Base **write** surfaces beside it — `base-write` (records) and
  `base-schema-write` (Bases, tables, fields and views), both on by default, both enumerated in
  the capability matrix and driven in the two write-handshake recipes. **If you planned around
  the old sentence, re-check that plan**: writing a Base was always possible.
- **The read path now names `retain_raw`, and says what the Markdown cannot tell apart.** Three
  different cells — a `Url` cell, a text cell whose bare URL was autolinked, and a mention chip
  — all render as `[text](url)`, so neither the cell's type nor the segment's kind survives the
  projection; an *unlabelled* `Url` cell is byte-identical to the autolinked text cell, and a
  *labelled* one is byte-identical to a chip. `read_base(url, retain_raw=True)` is the view that
  keeps them apart: it hands back the API's own `fields` body per record, kind on `type`, label
  on `text`, href on `link`, and it costs no extra API call, only memory. Take those from
  `raw_fields`, never from a pattern over the rendered Markdown — a `[label](url)` parse is
  wrong for every link whose author typed a label.
- **The per-field-type cell-shapes table gained a legend.** Its `Field type` column packs three
  different names into one cell (`1 / Text` · Text) — the integer storage type, the API's
  `ui_type` string, and the label Lark's own field picker shows — and the prose above the table
  now says which is which, so you can match on the pair and still find the row from the UI.
- **THE PERMISSIONS TABLE IS CORRECTED, AND NO SCOPE REQUIREMENT CHANGED — only what the library
  reported about one.** Read this if you have ever asked an administrator for a scope on the
  strength of that table. Two corrections, both to what is *printed*: (1) a surface that
  requires **no** scope now says so even when it has *optional* ones — `sheets-read` and
  `sheets-write` were the two, and they printed only their optional rows, so the table never
  stated what they must hold while `drive-read` did; and (2) each table now says **which question
  it answers**, and neither predicts what a missing scope costs. The surface table answers *what
  does this surface stop doing without the scope*; the per-call table (and
  `larkdocio.preflight.requirements_for_operations([...])`) answers *what must a grant include for
  that call to do its whole job*. **They are different questions, so the same scope can be
  `optional` in the first and still listed in the second** — the two `contact:*` scopes on
  `sheets-write` are exactly that case: a sheet write still works without them, while the call
  that resolves a name cannot do its whole job without them. **What absence costs is per scope,
  not uniform**, and it is written once per scope in that same section: without
  `contact:contact.base:readonly` the directory call is denied and no display name resolves at
  all, while without `contact:user.base:readonly` — a FIELD-level grant — that call **succeeds**
  and every name field comes back empty, which reads exactly like *"there is no such user"*.
  Nothing about the requirement moved: those scopes were required
  for that call before this release and are required after it, the per-call table said so
  already, and **no scope was added, widened or escalated** — the library still never requests a
  scope, and a grant is a Lark console action.
- **`larkdocio.capabilities()` no longer denies a call it lists, and now tells you how big the
  next call is.** The `drive-files-write` credentials note claimed there was *no folder-creating
  call anywhere in this library* while `drive-folders-write.create_folder` sat in the same
  payload — a claim that was true of that upload module and false of the library after folder
  creation shipped. It now says what it means (that module creates no folder; the destination is
  always yours), and the sentence is projected from that module rather than restated, so the two
  cannot drift again. Beside it, the summary's `reading` block gained
  `everything_is_this_big` — the size in bytes of what `capabilities(full=True)` returns, plus
  what one surface costs — because there was no way to know before making the call.
- **The capability matrix now tells you when you are asking the wrong index.** Ask it *"can it
  hide a tab?"* and it never answered: the matrix is indexed by operation NAME, and that
  capability is spelled `set-tab-visibility` / `SetTabVisibility` on `sheets-write`. The section
  now says so up front and routes a task-shaped question to `larkdocio.guide()`, whose sections
  are named after the failure each cures. Rule of thumb: the matrix when you know the verb, the
  guide's index when you know only the job.
- **The library now refuses the app's own root as a destination — and tells you exactly how far
  that reaches.** Every create already refused `None`, `""` and whitespace, but a *real* token was
  accepted, and `DriveClient.root_folder_token()` hands you the token of the application's own
  space: no human interface, trash that cannot be listed, `delete` that trashes rather than
  purges. So the rule refused the caller who said nothing and accepted the caller who named the
  one place nobody can browse to. **What changed:** that accessor's return type. It now answers an
  `ApplicationRootToken` (`larkdocio.common.destination.ApplicationRootToken`, also
  `larkdocio.drive.ApplicationRootToken`) and every create refuses that type outright — locally,
  before anything is sent. **Nothing else about it changed:** the type is a `str` subclass, so
  every existing string use — concatenation, comparison, f-strings, `json.dumps`, dict keys,
  sorting — behaves exactly as before, and an empty answer is still falsy and still `== ""`. **The
  limit, said with the guarantee rather than after it:** what is refused is the value this
  library's own accessor handed you. A raw root token *copied in from elsewhere* — pasted from a
  log, read out of your own config, rebuilt from a string — arrives as an ordinary string and
  cannot be told apart from a folder you own. Closing that gap would mean resolving the root
  inside the check, adding a network call and a wider permission requirement to every create; the
  check stays local instead, so **no scope, no endpoint and no call count changed**. And the
  accessor **stays public**, still in the `drive-read` matrix: reading that space is how you
  inspect it.

- **A create now hands you a value that names what it made — and can tell you what the reply
  did not answer.** Four calls changed what they return, and **nothing you already wrote
  breaks**:

  | Call | Now returns | New reads on it |
  |---|---|---|
  | `WriteClient.create_document` | `CreatedDocument` — a `dict` subclass | `.document_id` `.title` `.revision_id` `.folder_token` |
  | `SheetsWriteClient.create_spreadsheet` | `CreatedSpreadsheet` — a `dict` subclass | `.spreadsheet_token` `.title` `.url` `.folder_token` `.capture_the_token` |
  | `BaseSchemaClient.create_app` | `CreatedBase` — a subclass of the SDK's `App` | `.default_table_disclosure`, plus every `App` attribute as before |
  | `BaseSchemaClient.copy_app` | `CopiedBase` — a subclass of the SDK's `App` | `.echo_is_not_state`, plus every `App` attribute as before |

  **WHY, and it is not tidiness — this cost real objects.** While using this library against a
  live workspace, three separate failures came out of the same gap: **a spreadsheet was created and its
  token dropped**, leaving a live workbook in a space that cannot be browsed and that nothing can
  now name; **a run crashed with an `InvalidURL` *after* the object already existed**, because a
  link was constructed out of a host and a token rather than read off a reply; and **a run
  reported what it had created and was wrong**. All three are one defect: nothing about the value
  a create handed back said what you now held, or what the reply had not answered. This library
  already did it right one module over — `create_folder` has always returned a `CreatedFolder` —
  so the fix is **consistency, not invention**.

  **`create_document` still has no url, and now it says so out loud.** The docx create reply
  carries `document_id`, `revision_id` and `title` and nothing that names a web address, and this
  library will never assemble one from a host and a token — a constructed link is a guess wearing
  the shape of an answer, which is precisely the `InvalidURL` crash above. So `CreatedDocument`
  has **no `url` attribute at all**: `hasattr(created, "url")` is `False`, asking for it raises an
  `AttributeError` that tells you why and points you at the paved road (list the parent folder and
  read the new document back off it — the listing's per-child `url` is Lark's own), and the same
  sentence is readable without an exception as `created.no_url_reason`. **It is absent rather than
  `None` on purpose:** `None` is already what `CreatedFolder.url` means when Lark *carried* the key
  and left it empty, and if the two looked alike you could not tell *"Lark did not answer"* from
  *"we did not ask"*. `create_spreadsheet`'s reply **does** carry a url, and `CreatedSpreadsheet.url`
  is that value exactly as it arrived.

  **Disclosures you used to have to find in the docs now ride the value you are holding**:
  `created.capture_the_token` on a new spreadsheet (a create whose token is dropped is an orphan by
  construction), `created.default_table_disclosure` on a new Base (it is not empty — Lark seeds a
  table you did not ask for), and `copied.echo_is_not_state` on a Base copy (the copy is
  asynchronous, so `default_table_id` comes back empty and an immediate read of the new token
  fails). **No new permission, no new endpoint, no new scope, and no new operation** — a richer
  return type is not a new capability.

- **Two contracts you read to decide what to rely on now say what they always meant.** Prose only:
  **no behaviour changed, no key, no endpoint, no scope, and no capability was added or removed.**
  What moved is bytes in `capabilities(full=True)`'s `safety_contracts` and one row of the guide
  that ships inside the wheel.

  **The destination contract now tells you about the second refusal, and about its limit, in the
  same breath.** Alongside the rule you already knew — every verb that creates a **new top-level
  object** needs a destination you supply, and every spelling of *none* is refused locally,
  including the empty string Lark itself accepts — the summary now also states that
  `require_destination` refuses **the application's own root by type**: the value
  `DriveClient.root_folder_token()` answers. **And the limit ships with it, not later**: what can
  be refused is *the value the accessor itself handed you*; a raw root token copied in from
  somewhere else arrives as an ordinary string and is accepted. That gap is disclosed, not closed,
  because closing it would turn a local check into a networked one on every create. The summary
  also carries the remedy in the order the refusal itself states it — **open a folder you already
  own and use the token from its link** first, `create_folder` second, with what a folder costs
  said **before** you make one. Finally, the old *"creates no folder"* clause is re-cut: it was a
  statement about the fence, and it is now readable as one, because `create_folder` **does** ship
  and the refusal offers it to you as the second route.

- **If you read the docx apply-log guarantee as "docx never leaves partial content", read this
  one.** Both of the following were already true, and nothing on the page said they were about
  different things:

  - a batch the **whole-document compare-and-swap REFUSES** issues **zero writes** and never
    partially applies — there is nothing to enumerate, and that is unchanged;
  - inside a batch that was **ACCEPTED**, each inserted apply-log entry carries
    `mutating_write_calls` and the `atomic` derived from it, and **`atomic: false` means a failure
    partway through that entry can leave part of its content in the document**.

  The contract now carries one sentence of scope saying so. **What to do about it:** for the
  refused case, nothing changes. For the accepted case, key your CI on the **entry's own keys** —
  read `atomic` and `mutating_write_calls` per entry, exactly as the stability contract on those
  two keys already told you — rather than on the whole-batch sentence, which was never about that.

### Upgrade & compatibility

- **A BREAK, small and only in the exception type: if you catch `TypeError` around
  `create_document` to detect a missing destination, catch `MissingDestinationError` instead.**
  `WriteClient.create_document`'s `folder_token` now defaults to `None`, so calling it with no
  destination at all reaches *this library's* refusal — the one that tells you the rule, what to
  pass, how to get a folder token and what making a folder costs — rather than Python's bare
  "missing 1 required keyword-only argument". **Nothing else changes.** The argument is still
  keyword-only, still in the same position, and still required in effect: nothing is created and
  nothing is sent, exactly as before. No call site moves, and every call that already passes a
  real folder token behaves identically. The only code that notices is code whose `except` names
  `TypeError` — and if you were following the previous release's advice to *pass
  `folder_token=None` on purpose to reach the teaching refusal*, that advice still works and is
  now simply unnecessary for this method.
  **A note so you do not infer a symmetry that does not exist yet:** `create_spreadsheet` was
  **not** changed. Omitting its `folder_token` still raises `TypeError`, one step before the
  library runs, and the guidance to pass `None` deliberately still applies there. Making the two
  behave alike is a decision that has not been taken.
- **If you pass `DriveClient.root_folder_token()` anywhere as a `folder_token`, that call now
  raises `MissingDestinationError` instead of creating something.** Nothing is sent, so there is
  nothing to clean up — but the create you expected will not have happened. Replace it with a
  folder a person can open: take the token from a Drive folder's own link, or make one with
  `create_folder(name, parent_token)` (that folder is permanent as far as this library is
  concerned — read the cost before you take that route). Everything else about the accessor's
  return value is unchanged, so no other use of it needs touching.
- **The one thing to grep your own code for before re-vendoring: `.patch_block(`.** If it
  appears anywhere, that call now refuses (typed, locally, nothing sent) and you swap it for the
  gated route named in **Behavior changes you can observe**. If it appears nowhere, this release
  changes nothing for you: **every other public symbol, return shape, refusal class and refusal
  code is untouched**, and the library's own writes — paragraph edits, table-cell patches,
  sub-span edits, the checkbox flip, the table grow, and the image and file binds — put the
  **identical** body on the wire in the identical order, because they all still run through the
  same primitive under its internal name.
- **The armed-guard wording change is text-only, and it is the one thing to check before
  re-vendoring.** No public symbol, return shape, refusal class, refusal code or plan field
  changed with it: `revision_guard` still reads `active` / `unavailable`, `STALE_DOCUMENT` is
  still the refusal you catch when the document drifts under a plan, and no new token was added
  for you to key on — the refusal vocabulary was removed from the success path rather than
  answered with a success token. **If you match on push output or on `revision_guard_detail`
  text**, update those matches; if you match on the fields, nothing moved.
- **The two new apply-log keys are additive and appear only where they are measured.** They
  are written on `inserted` entries only, and only when a measurement was taken, so an entry
  built any other way — a hand-built one, a replayed one, one from an older release — keeps
  its exact previous JSON. `from_dict` reads the count back; `atomic` is re-derived from it
  rather than trusted off the wire, so a hand-edited log cannot carry a flag its own number
  contradicts. **If you compare apply-log JSON against a stored fixture**, a successful insert
  now carries two more keys.
- No dependency moved — **that half is release-wide**. The rest of this bullet is scoped to
  **this entry's own change** and is not a release-wide claim: within it, no public symbol,
  return shape, refusal class or plan field changed, and the ids in the new message come from
  `ReconciliationPlan.conserved_block_ids`, which was already public. Release-wide, several did
  move, each stated in its own entry — the new `body_differs` plan key in the bullet immediately
  below, the `patch_block` fence and `FencedPrimitiveError`, four changed create return shapes,
  and the added `mutating_write_calls` / `atomic` / `todo_done` keys. **If you match on this refusal's text**, note that the wording after the
  first sentence now differs for a document containing conserved blocks; the opening (`…
  reconciles to no change at all, so there is nothing to apply.`) is unchanged, and the error
  class is unchanged.
- **One plan key is new, it is additive, and it appears only where there is something to
  disclose.** `body_differs` is written on conserved-opaque entries only, and only when the
  reconciler actually compared a read-back, so an entry built any other way — a hand-built one,
  one rebuilt from a plan you stored, one from an older release — keeps its **exact previous
  JSON**. `from_dict` reads the key back and accepts a plan written without it, and a plan
  written before this release round-trips through `from_dict` → `to_dict` byte-for-byte. **If you
  compare plan JSON against a stored fixture**, a conserved-opaque entry now carries one more
  key. Nothing else moved: no scope, no refusal class, no refusal code, no new refusal reason,
  and `conserved_block_ids` is unchanged.
- **The push refusal for a no-change document names more than it did — and still asserts
  nothing.** When at least one conserved block read back differently, the conserved arm now says
  which ones, as a second disjunction (*either an edit landed there, or the projection reshaped
  that body*). When nothing read back differently the wording is **exactly** what it was. **If
  you match on this refusal's text**, that added sentence is the only difference, and the opening
  sentence and the error class are unchanged.
- **The permissions and capabilities corrections move generated TEXT, and one summary key is
  new.** No scope, no requirement, no state token and no public symbol changed. What moved: the
  permissions table in `larkdocio guide` gains one row per surface that requires nothing but
  offers something optional, plus a which-question label above each table; `capabilities()`'s
  `drive-files-write` credentials note is rewritten to the module scope it always meant; and
  `capabilities()['reading']` carries a new `everything_is_this_big` key beside the ones already
  there. **If you match on the text of that note, or compare the summary dict against a stored
  fixture**, those two are the places to re-check — `reading['everything']` is unchanged, and
  every other key kept its spelling.
- **A BREAK, stated plainly: `get_read_credentials()` now raises `LarkConfigError` where it
  returned the empty pair `('', '')`.** The exception a caller catches is
  `larkdocio.errors.LarkConfigError` — the same class `get_write_credentials()` has always raised
  for a missing write pair. It raises when **no complete pair resolves**: neither
  `LARK_READ_APP_ID` + `LARK_READ_APP_SECRET` nor the legacy `LARK_APP_ID` + `LARK_APP_SECRET`,
  and a pair with one half missing counts as not resolving. The resolution **order** is
  unchanged, the legacy fallback is unchanged, and a `.env` that worked before works now.

  **The break's whole extent is one anti-pattern: code that relied on the empty-tuple
  sentinel** — reading `('', '')` back as a boolean instead of being told what was wrong. That is
  precisely the shape this fence exists to stop, because the blank then travelled into a client
  constructor and came back out as whatever Lark says about a blank app id, one layer away from
  the thing that was actually wrong. If you have such a caller, the migration is one line:

  ```python
  # before — the sentinel as a boolean
  app_id, app_secret = get_read_credentials()
  configured = bool(app_id and app_secret)

  # after — the refusal as a boolean
  try:
      app_id, app_secret = get_read_credentials()
      configured = bool(app_id and app_secret)
  except LarkConfigError:
      configured = False
  ```

  Anything that used the pair as a **pair** — handing it to a client, to `Client(*...)`, to a
  `from_read_credentials()` — needs no change at all: it now gets a message that names the two
  variables that are actually in force, the `larkdocio config` command that writes them, and the
  fact that `.env` is the only place credentials live. **What it buys:** both halves of the
  credential fence refuse the same way, and neither borrows the other's pair — a read-only app is
  never promoted into a write, and a write app is never assumed able to read.

- **The four typed create returns above: what is promised, exactly, and for how long. THE OLD
  ACCESS STILL WORKS — that is the point of the shape.** `create_document` and
  `create_spreadsheet` used to return a plain `dict`; the value you get now **is** that same dict
  (the reply's own payload, key for key) with attributes added on top, so all of this keeps its
  old answer: subscript `created["document_id"]`; `.get(key)` and `.get(key, default)`;
  `key in created`; iteration; `len()`; `.keys()` / `.values()` / `.items()`; `==` against the
  plain dict you compared to before; `json.dumps(created)`; `dict(created)`; `{**created}`;
  splatting it into a call as `**created`; `isinstance(created, dict)`; and mutating it, because
  it is a real dict.
  `create_app` and `copy_app` used to return the SDK's `App` object — **not** a dict — so for
  those two the promise is about attributes: `app_token`, `name`, `revision`, `folder_token`,
  `url`, `default_table_id` and `time_zone` all answer what they answered, and
  `isinstance(app, App)` is still `True`.

  **The one thing that is no longer true, said plainly rather than left for you to find:**
  `type(x) is dict` and `type(x) is App` now answer `False`. Use `isinstance`, which answers
  `True`. That is the whole break, and there is no shape that adds attributes to a value while
  keeping `type(x) is dict` true.

  **How long is the old access promised for? PERMANENTLY. There is no deprecation window and no
  sunset date, and the reason is that a window nobody can measure the end of is a permanent
  surface with extra words.** This library does not track who consumes it — there is no telemetry
  and no registry — so the last caller subscripting a create's answer can never be observed to
  leave, which means any date printed here would be a promise nobody could enforce. There is also
  nothing to gain by taking it away: the dict body is not a compatibility shim sitting beside the
  real value, it **is** the reply, and the attributes are views onto it that cannot drift from it.
  Retiring the dict access would mean deleting the reply's own content from what you are handed.
  **So: build on either style, indefinitely.** And if you pin a vendored wheel, note that none of
  this reaches you until you choose to bump — an older wheel's bytes are unchanged.

### Known limitations

- **The silent no-op itself is NOT fixed by this release — only what you are told about it.**
  An edit made inside a conserved block is still not written, and no release note here changes
  that: the engine conserves such a block whether or not you edited it. What you can now be told
  is **narrower than an answer**: `body_differs` says whether that block's body read back
  differently, and that fact has two readings it cannot choose between (your edit, or the
  projection's own reshaping). So there is still **no** way to be told which block absorbed an
  edit — only which ones are worth looking at first. Do not go looking for a fix that is not
  there.
- **Calling the reconciler directly gets the disclosure, not the message.** The refusal text
  belongs to the file-first round trip. A caller reconciling in-process still sees a zero-change
  plan and must read the plan itself — `conserved_block_ids` for what was left alone, and
  `conserved_block_ids_that_read_back_differently` (or each entry's `body_differs`) for the
  disclosure the refusal text would have quoted.
- **The docx write surface now states five more things it cannot do — and NO capability was
  added or removed to go with them.** Nothing was implemented, no route moved, and one
  docstring stopped promising something it never delivered. The surface's machine-readable
  absence list — `capabilities(full=True)["surfaces"]["docx-write"]["absences"]`, which
  already carried the no-move row — gains five rows, each with its statement, how firmly it
  was established, the evidence, and what to do **instead**: no way to author an **@mention**;
  no operation that applies **character styling** (bold, italic, colour) to text, created or
  existing — though styling and mentions already in a block are preserved by an edit; no
  operation that **grows a table that already exists** (its cells are editable, its grid is
  not); no way to change an existing **todo's checkbox**; and no way to **retitle** a document.
  Two of those rows carry facts you should read before planning around them. The
  table-grow row records a route that **was measured** and is deliberately not shipped —
  appending a row at the end preserves every existing cell id, measured to 200 rows — with
  rows beyond that, and insertion anywhere but the end, marked **unmeasured, not refuted**.
  *(Two of the five rows are scoped in time by later entries in this same release, and this
  bullet is not rewritten: both were accurate descriptions of the register when it landed.
  **The table-grow row was narrowed** — appending a row at the end IS a shipped operation now
  (`GrowTableRequest`), and the row reads `no-table-grid-change-beyond-appending-a-row`.
  **The checkbox row was replaced outright** by `no-block-property-edit-beyond-text`; there is
  no register row saying the checkbox cannot be changed. The arithmetic — five rows added —
  still holds; what has moved is what two of them say.)*
  The retitle row says the same about its route: this library publishes the fact that a
  document's root page block is addressable by the document's own id, and that is an
  addressing fact, **not** a way to rename anything — nobody here has ever called it.
- **The checkbox row is a DEFECT, not a boundary, and it is the one to read.** ***FIXED LATER
  IN THIS SAME RELEASE — read the New capabilities bullet on the `done` bit first. The
  paragraph below is kept as written, scoped in time and not rewritten: it was true at the
  point it landed, and it is the record of the defect the fix closed. The three workarounds it
  names are no longer needed; a flipped checkbox now moves the bit through the plan-gated
  route.*** Editing a
  todo's `done` bit through the round trip **reported success and changed nothing**: a flipped
  checkbox reconciles to a text-only edit whose replacement is the text already there, so the
  plan is fine, the apply log says `applied`, and the box does not move. The library now says
  so where you ask what it cannot do. Until it is fixed, create the item in the state you want
  (`NewBlock.todo(text, done=True)` writes the bit at creation), flip it in the Lark editor, or
  delete and re-insert the item — which gives it a new block id.
- **And the dialect table said the same, so a green apply on a checkbox was not evidence the
  checkbox moved.** ***SUPERSEDED LATER IN THIS SAME RELEASE, kept as written and not
  rewritten.*** Two things have since changed under it. **It IS fixed by this release** — the
  bit moves — and **the dialect table no longer says this**: the guide's `todo` row now reads
  that the checkbox state is editable in place, and the docx block matrix's write-side row (`BLOCKS.md` **in the dev repo** — the wheel ships
  no matrix) was corrected in step, superseding the prior clause that the `done` bit was not
  editable. What
  the paragraph recorded, at the point it landed, was real: the plan was fine, the entry read
  `applied`, and the box was exactly where it had been.
- **A link anchor cannot be put inside a table cell, by any route.** A cell's text is editable,
  but only as text: the whole-cell edit carries a plain string and no spans, the span-level edit
  is narrative-anchored and a sub-span inside a cell is out of scope, and creating the table
  takes plain-text cells. Put the anchored sentence in a paragraph beside the table, or write
  the bare url as the cell's text and let the reader's own autolink shape carry it.
- **Table cells are plain text after creation, not only at creation.** `NewBlock.table`'s
  docstring used to say rich cell content (styled runs, a nested list) could be authored after
  creation through the cell-edit path. It cannot, and the shipped types are why: the cell edit
  takes a `str` replacement for one whole cell, and the only family that edits *within* a block
  takes narrative anchors, never a cell. Author every cell's text at creation, patch a whole
  cell later, and put rich content in a block beside the table.
- **The six block kinds that accept `spans=` are now written down** — in the packaged writer
  brief (`larkdocio.writer_brief()`), as a table held to the engine's own list in both
  directions, together with the reasons `code`, `mermaid` and `table` cannot take one. The link
  anchor was previously discoverable only by reading the source.
- **`compose()` still accepts a fragment of any size — the 50-block-per-call limit is now
  stated where you would build the request, not only where it fires.** Composing more than
  `MAX_CHILDREN_PER_CALL` (50) top-level blocks has never raised inside `compose()` itself,
  and still does not: the limit is enforced one step later, when you wrap the result in an
  `InsertRequest`, which raises a plain `ValueError` naming the count and the limit. Nothing
  about that behavior changed. What is new is disclosure: `compose()`'s own docstring and the
  writer brief now state the limit, show `len(compose(markdown))` as the check to run first,
  and say plainly that this particular limit raises a `ValueError`, not the typed refusal
  every other documented limit on this surface raises. If your fragment can exceed 50
  top-level blocks, check the count before building the request and split it across more than
  one insert.

## [1.40.0] — 2026-08-22

### New capabilities

- **The setup walkthrough now covers the walls, not just the happy path — read it before your
  next app: `larkdocio.lark_setup()`.** It used to describe the sequence that works (create the
  app, grant, share the documents, prove one read) and none of the places a real setup gets
  stuck. It now carries five, each written at the step where it bites and each labelled
  **operator-observed console guidance** — console-side observations from real onboarding
  attempts, **not** measurements of the API:
  - **A fresh app is not a bot yet.** Creating the app is one form; the bot capability, the app's
    profile and its permissions are three separate pages, and none of them takes effect on save.
  - **Tenant or user.** The console offers most permissions twice — once for the *application*,
    once for a *signed-in person*. Grant the application side: this library authenticates as the
    application on every call, with a tenant access token.
  - **The grant list keeps growing, one refusal at a time.** That loop is the normal experience;
    reading the generated per-operation table once for everything you plan to run, and granting
    it in a single pass, turns several release cycles into one.
  - **The release flow gates membership and availability too**, not just permissions. Adding
    collaborators, a department or the whole tenant to an app is a version change, and the list
    you edited is not the list in force until that version is released.
  - **The IP allowlist.** An app can be configured to accept calls only from listed addresses,
    and until the address your calls leave from is on that list, correct credentials and correct
    permissions get you nowhere. The section names the symptom (every call fails identically,
    whichever document you point at), the fix path (add the **public** address, then release),
    and why it recurs (a laptop's public address moves with the network).
- **An own-app framing at the top of the walkthrough.** Create your own app rather than asking
  to be added to somebody else's: an app's permissions are capabilities of the app, not of a
  folder, so one that starts as *"my own documents"* becomes read and write reach across
  everyone's shared folders the moment it is handed around — and cannot be narrowed again once people
  depend on it. One app per person or per team is the shape the walkthrough now assumes.

### Behavior changes you can observe

- **`larkdocio.lark_setup_sections()` returns 12 rows where it returned 6**, and the new rows
  are **level 3** — the five walls plus the own-app framing. If you index or filter that list,
  note that it is no longer level-2-only. `larkdocio.lark_setup(section=…)` takes each new
  heading or its slug like any other section, so a wall can be printed on its own.
- **`larkdocio.lark_setup()` returns roughly two and a half times as much text.** Same call,
  same contract, more document.

### Upgrade & compatibility

- **No dependency moved** — nothing added, nothing dropped, no pin changed.
- **No public symbol, signature or CLI flag changed.** The only observable difference is the
  content of the shipped walkthrough and the length of its section index.
- The walkthrough still **quotes no permission scope string**. Both walls that discuss
  permissions point at the generated per-operation table and at
  `larkdocio.guide(section="permissions-what-to-ask-for")`, which stay the single place a scope
  string is written down.

### Known limitations

- **The five walls are console-side observations, not API measurements, and they are not
  exhaustive.** Lark's console governs its own layout and behavior and may change either; page
  names and nesting already differ by region. Each wall says what to look for, never where to
  click, and Lark's own documentation remains the authority.
- **Per-person (user) tokens remain out of scope, and that is an unmeasured position rather than
  a refuted one.** No path in this library obtains, stores or sends one, so how such a grant
  behaves has not been observed here. A design that needs per-person identity is not one this
  walkthrough reaches.

## [1.39.0] — 2026-08-22

### New capabilities

- **The Lark-application walkthrough now ships inside the wheel, and you can open it:
  `larkdocio.lark_setup()`.** It is the ten minutes before a first call — create the app, note
  its App ID and App Secret, grant the starter scope, **release the app version** (a grant that
  has not been released is the first thing to check when a call is still refused), share the
  documents onto the app, then prove one real read. Nothing in this library works until an app
  exists, holds the scopes and can reach the documents, and none of those three is something
  code can do for you. `larkdocio.lark_setup(section=...)` returns one step and
  `larkdocio.lark_setup_sections()` is its index — the same `section=` seam the guide, the writer
  brief, the release notes and the changelog already take. Until now that document existed only in the publishing repository, so
  the only reader who could open it was the one who needed it least.
- **The vendor refresh drops it beside the wheel too**, as `vendor/larkdocio-LARK_SETUP.md`,
  alongside the guide, the changelog and the release notes — readable before anything is
  installed at all, which is the one case the in-wheel copy cannot serve. A tag that predates
  the document skips that drop with its own logged note and the run still succeeds, exactly as
  the other drops do. Both the `dist` fast path and the build-from-tag path carry it, so
  `./vendor/` is still identical whichever one ran.

### Behavior changes you can observe

- **`capabilities(full=True)["docs"]` now has five rows, not four** — `lark_setup()` joins
  `guide()`, `writer_brief()`, `release_notes()` and `changelog()`, each with its resource, its
  summary and its section index. Read the registry rather than a count: if you asserted the
  length of that mapping, this release moves it. `capabilities(full=True)["entry_points"]` gains
  `lark_setup` and `lark_setup_sections` on the same footing.
- **The wheel's top-level packaged Markdown set gains `LARK_SETUP.md`.** Nothing was removed and
  no existing document's PROSE was rewritten (the guide's own discovery counts and both notes windows moved with the new document, as they must).

### Upgrade & compatibility

- **No dependency moved** — nothing added, nothing dropped, no pin changed. This release adds a
  document, two accessors and a vendor drop.
- **Purely additive to the public surface.** Every existing accessor returns the same bytes;
  `larkdocio.__all__` grows by the two new names and loses nothing.

### Known limitations

- **The walkthrough names files that the wheel does not carry, and says so.** The generated
  permissions matrix and the per-surface support matrices live in the publishing repository, so
  the document names them as paths **in the dev repo** and gives the in-wheel address beside
  each — `larkdocio.guide(section=...)` for the scope rows, `larkdocio.capabilities()` for the
  surfaces. It deliberately quotes **no scope string at all**: a scope copied into prose is
  where drift starts, so it points at the generated table instead.
- **It cannot tell you whether your app is configured.** Everything it describes happens in the
  Lark console and in Lark's sharing UI. The library never widens, requests or escalates a
  scope; it describes what an operation needs and surfaces Lark's own denial body when something
  is missing.

## [1.38.0] — 2026-08-22

### New capabilities

- **You can ask what a Lark error code MEANS.** `larkdocio.errors.note_for(code)` returns a row
  for every code this library has recorded — 39 of them as this release was written, and
  `len(larkdocio.errors.ERROR_CODES)` is the count, so ask it rather than trust this
  sentence — Lark's own message where it was recorded, one
  actionable sentence about what to do, where the reading was established, and how firmly
  (`denial-verified`, `wire-observed` or `documented-unverified`). `larkdocio.errors.ERROR_CODES`
  is the whole table. It takes an `int` or a `str`, and returns `None` for a code nobody here
  has explained rather than inventing one.

  ```python
  from larkdocio.errors import note_for
  note = note_for(err.code)            # err.code is on every LarkAPIError
  if note:
      print(note.meaning, "—", note.verification)
  ```

  It is a **lookup and nothing more**: no new command, no new flag, and it put nothing of its
  own into `capabilities()` — no key, no operation row, no scope. (`capabilities()` itself did
  reshape in this release, for an unrelated reason, and that break has its own entries below.)
  Codes carrying an empty message are codes whose text nobody wrote down, said so on purpose
  rather than reconstructed.
- **A permission refusal and a *"you are not on this object's list"* refusal are now told
  apart.** Rows carry `denial_class`: `"scope"` means the **application** lacks a permission and
  a workspace administrator grants it in the Lark console; `"object-acl"` means the application
  has the permission and is simply not shared on that particular folder or document, so the fix
  is to **share it**. Two different fixes that used to look like one number. `1770040
  "no folder permission"` and `1254701 DriveNodePermNotAllow` are the two object-ACL codes
  recorded so far, and `larkdocio.permissions.denial_from` still returns `None` for them —
  correctly, because no scope is missing.

- **`capabilities()` now answers with a SUMMARY, and the whole registry moved behind
  `capabilities(full=True)`.** The no-argument call returns every surface, every operation
  **name** with its kind, and the scopes each surface needs — names only, never prose — plus a
  `reading` block that spells the calls that get you more. The whole registry is **23.8×** its
  size — 12,772 bytes against 304,343, both `json.dumps(…, default=str, sort_keys=True)` on the
  release tree, 2026-08-20 — and the size guard that ships with it binds the ratio at **more than
  20×** on every run, so this stays a thing you can read in one go, by eye or by agent.
- **`capabilities(surface="<id>")` returns ONE surface's full row** — the middle rung, for when
  you want a surface's detail without holding the whole registry. An unknown id raises
  `ValueError` naming every surface there is; asking for `surface=` and `full=True` together
  raises too, because that is two requests in one call.
### Behavior changes you can observe

- **A FAILED DOWNLOAD'S OPERATOR GUIDANCE IS NOW CHOSEN BY WHAT THE ERROR *IS*, NOT BY WORDS IN
  ITS MESSAGE.** The wording of every banner and every failure message is **unchanged, byte for
  byte**, and a failed download still exits non-zero exactly as before. What changed is which
  banner you get in two cases:
  - **Narrower.** An error whose message merely contains the words *"not found"* — and which
    carries no Lark document-access code — no longer prints the *"Missing Document
    Permissions"* advice. Previously any failure containing those two words did, including ones
    that had nothing to do with document access, which sent you to share a Lark document over,
    say, a missing local file. Such an error now prints its own message and Lark's own code.
    **The real case is unaffected:** *"not found"* is Lark's message for the docx read's own
    access code, and that code still routes to the permissions banner.
  - **Wider.** A refusal in which **Lark named the missing permission** now prints the
    *"Missing Document Permissions"* advice whatever code it carried. Previously only two
    specific code numbers did, so a genuine permission refusal under a third code fell through
    to the generic bug-report banner.
- **A MERGED TABLE NO LONGER LOSES WHAT SITS AT A MERGE-COVERED CELL.** When a document has a
  table with merged cells, the reader emits an HTML `<table>` with real `rowspan` / `colspan`,
  and a grid position *covered* by another cell's span emits no cell of its own. Until this
  release, emitting no cell also **threw away everything that position held** — the text, and
  equally an image. That was silent: no marker, no note, no warning. **It now renders.**
- **Where it renders.** A covered position's content is **absorbed into the cell of the anchor
  whose span covers it**, appended **after** that anchor's own content, in **row-major order**
  of the positions the anchor covers, with **nothing wrapped around it** to mark it as
  absorbed. Two shapes, so you can recognize both in your output:

  ```html
  <!-- both cells hold plain text: joined with <br/> inside the one cell -->
  <td rowspan="2">Tall<br/>covered-by-Tall</td>

  <!-- one side needs block markup: the pieces are separate blocks in the one cell -->
  <td colspan="2"><p>Images</p><img src="…"/></td>
  ```

  A covered cell that is **empty** contributes nothing at all, not even whitespace, so a table
  whose covered positions are all empty renders exactly as it did before. **How often real
  documents look like that is unmeasured** — one document's output was checked and did not
  move, which is one document's worth of evidence and no more.
- **An image at a covered position was downloaded and then linked nowhere. That is fixed.** The
  image's token was queued for download before the table was rendered, so the bytes landed in
  your `static/` directory while no line of the Markdown referenced them. Now the reference
  exists. If you have been reconciling downloaded files against links, that mismatch was real
  and it is gone.
- **RE-CONVERTED OUTPUT WILL DIFFER** wherever a Lark document holds a merged table with
  content at a covered position — that is the point of the fix, and it is a rendered-Markdown
  change like any other. If you keep converted Markdown under version control, re-convert the
  whole document as its own commit before diffing content, exactly as the guide's
  refresh-a-snapshot advice says.
- **What did NOT change: the layout.** No cell is emitted at a covered position, and every
  rendered row still occupies exactly as many grid columns as the table declares — so a table
  that lined up correctly still lines up correctly. Nothing about the **write** side moved
  either: a merged or covered cell still refuses as a write target, and merged cells still
  cannot be authored. Content becoming visible does not make it writable.

- **BREAKING — `capabilities()` returns a different shape. Code that parsed its output needs
  one edit.** The whole registry is now behind an explicit argument: wherever you called
  `capabilities()` and read `["surfaces"]`, `["docs"]`, `["flags"]` or an operation's
  `["permissions"]`, call **`capabilities(full=True)`** instead. Nothing was removed from that
  payload — the same facts are all in it — so the migration is that one keyword, everywhere.
- **BREAKING — a surface's call sites are under ONE key.** `operations`, `legs` and `lifecycle`
  are now a single `operations` list per surface, and every row carries a **`kind`**:
  `operation` (a kind the surface's engine dispatches), `leg` (an API-using call that is not one
  of those), or `lifecycle` (a call that creates or destroys the file itself). The
  `operation_index` pointer list is gone with them, because with one key there is nowhere for a
  pointer to point. **If you read `operations` alone, you now see everything the surface can
  do** — including the file-lifecycle calls and the API-using legs, which used to sit under keys
  a reader had to know existed. If you specifically want the plan-gated write ops, filter
  `row["kind"] == "operation"`; the summary carries the same names and kinds.
- **BREAKING — the evidence behind a scope requirement is carried once, at the top level.** An
  operation's `permissions["scopes"]` and `permissions["optional_scopes"]` are now lists of
  **scope strings**, and `permissions["unknown_requirements"]` a list of **endpoints**; the row
  each one names — how firmly it is verified, the evidence that established it, what its absence
  looks like, whether it degrades or is field-level — lives once under the new top-level
  `scope_evidence` and `unknown_requirements`. So `[s["scope"] for s in block["scopes"]]` becomes
  `block["scopes"]`, and reading the detail is one lookup: `payload["scope_evidence"][key]`.
  **Nothing was summarised away or shortened** — the same paragraphs are all still there, once
  each instead of up to twenty-one times, which is most of why the registry is now about a
  quarter smaller.
- **What did NOT change — BY THE RESHAPE.** Every fact the registry carried, and the operations,
  credentials, flags, safety contracts, gate coverage, level models, block-read support and
  packaged-document rows themselves. (Scoped rather than struck: the reshape moved no fact, and
  that is still exactly true. **One** gate-coverage value did change later in this same release —
  each write surface's live-gate `command` gained the consent variable, its own entry below — so
  the sentence stands for the reshape and not for the release.) No Lark API call, no CLI command, no CLI flag and no refusal code moved, and
  the `--help` text and the permissions matrix — this guide's own generated permissions section
  — regenerate **byte-identical**, because they derive from the permission registry's typed rows
  and not from this serialization. **The shipped guide's text did move**,
  though its facts did not: every `capabilities()` example in it now names the door that returns
  what the surrounding paragraph describes. The registry is still built by projection off the
  library's own registries, and still round-trips through `json.dumps` / `loads`.
- **The command `capabilities()` reports for a write surface's live gate now carries the consent
  variable that gate requires.** Each write surface's `gate_coverage.command` reads
  `LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write` — `LD-NNN` being a
  placeholder for the identifier that authorized the run — rather than
  the bare `pytest -m live_write`, which on its own selects the ring and is then refused; the
  value is an identifier, never `1` or `true`. Only that one string moved — the marker, the
  credential list, the ring members and the target policy are unchanged, and no runtime behaviour
  of the library depends on it.
- **THE WHEEL'S OWN COPIES OF `CHANGELOG.md` AND `RELEASE_NOTES.md` — two of the documents it
  carries for a consumer — NOW CARRY A WINDOW OF THE NEWEST 8 RELEASES, NOT THE WHOLE
  HISTORY.** `larkdocio.changelog()` and
  `larkdocio.release_notes()` return that window: each document's preamble verbatim, a banner
  saying what the window is and where the rest lives, then the newest 8 `## [X.Y.Z]` sections
  verbatim. Nothing inside a section was edited or reflowed — a section the window carries is
  byte-for-byte the section the publishing repository holds. **This is a decision, not a
  regression**, ruled on 2026-08-18 (§ 5.2 of this project's refactor reconciliation): these
  documents are read by whoever is deciding whether to re-pin, and a full history made an agent
  pay for seventeen to thirty-one releases it can no longer act on before reaching the one it
  can. Measured on 2026-08-21, at the moment the window was cut and before this entry was
  written — a byte count written into the file it counts moves itself — the two packaged
  documents together fell from **997,519 bytes to 549,304**, and their release-section counts
  from **39 and 25 to 8 each**. The section counts are exact as shipped; they do not move with
  prose.
- **ASKING FOR A RELEASE OLDER THAN THE WINDOW NOW REFUSES WITH ITS OWN MESSAGE, WHICH NAMES
  WHERE THAT RELEASE LIVES.** `larkdocio.changelog(section=...)` and
  `larkdocio.release_notes(section=...)` still take one release at a time. A name that resolves
  to a release **inside** the window behaves exactly as before. A name that parses as a release
  **older** than the window raises `ValueError` saying *out-of-window* rather than *unknown* —
  it states that the release is real, what the window is, and the two addresses the full history
  sits at. A name that was never a release at all keeps the **unchanged** *unknown section*
  message listing every section this copy has. The two cases are deliberately distinct: being
  told a release you are holding "does not exist" would be false, and would not tell you where
  to look.
- **HOW 8 WAS CHOSEN, so you can judge whether it covers you — and the rule you can apply to
  yourself in one line: if you are more than SEVEN releases behind the wheel you are reading,
  this copy does not name the release you are on.** Eight sections cover you and the seven
  releases before you. That is **one section more than the largest update gap this project can
  evidence**, a jump of six releases made without these notes to hand — the reason these documents are packaged in the wheel at
  all — **seven sections** counting the release they were on. So the margin over the worst case
  on record is **×1.14, not a comfortable multiple**, and it is stated that way rather than
  rounded up: the number is also about thirteen days at the measured release cadence of 12
  releases in the 19 days to 2026-08-20, and every section added here is a section of shrink
  given back. **If you are outside it, nothing is lost and nothing is hidden**: the complete
  history is beside your vendored wheel at `vendor/larkdocio-<DOC>.md` — the refresh script
  drops it complete on every refresh, unaffected by this change — and in the publishing
  repository at its root, and asking for an older release by name tells you exactly that
  instead of claiming it does not exist. The same number is used for both documents because each
  carries one contiguous section per release (measured 2026-08-21: 39 and 25 sections, zero gaps
  in either), so the newest 8 of each are the **same 8 releases** and a reader who opens both
  gets a matched pair.

- **THE GUIDE IS REORGANISED BY TASK — AND EVERY SECTION ADDRESS YOU ALREADY CITE STILL
  RESOLVES.** This is a decision, not drift: the 2026-08 refactor charter names *"the guide
  restructure"* as a **ruled** exception to behavior preservation, and guide length as the first
  thing to shrink.
  - **What changed.** One flat `## Recipes` heading used to hold **60** recipes in the order they
    shipped — **83.0%** of the whole guide, measured 2026-08-21 by line count between `##`
    boundaries. So asking for that one section handed you three quarters of the document. There
    are now **six task sections**, each answering one thing you might be doing:
    `task-read-something-out-of-lark-into-markdown`,
    `task-who-can-open-it-where-it-lives-and-which-edition-you-mean`,
    `task-change-what-a-document-says`,
    `task-put-a-picture-a-file-or-a-link-into-a-document`,
    `task-rows-columns-and-tables-in-a-base`,
    `task-cells-tabs-and-formatting-in-a-spreadsheet`. The largest one is **22.5%** of the guide,
    same method, same day.
  - **NOTHING YOU CITE BREAKS. Zero section names were retired.** If you have a `--section` slug
    hard-coded, or a `larkdocio.guide(section="…")` call in a script, or a routing table full of
    them: they all still resolve. The reorganisation moved whole sections and added headings above
    them; a section's name comes from its own heading, and no heading was renamed. **103 → 110
    sections** (**14 → 21** top-level, **89** recipe/reference sections unchanged), so what you
    get is **seven new addresses** and nothing taken away.
  - **ONE ADDRESS ANSWERS DIFFERENTLY, and it is the only one: `recipes`.**
    `larkdocio guide --section recipes` used to print the entire recipe chapter — **9,045 lines**.
    It now prints the chapter's promise and the **index** of the six task addresses — **26
    lines**. If you were using it to get every recipe at once, the whole document is one explicit
    argument away (`larkdocio.guide(full=True)`, or `larkdocio guide --full`); if you wanted a
    particular family of recipes, ask for its task address instead.
  - **How to find any address, without reading this entry twice.** `larkdocio.guide_sections()`
    returns every heading with its slug and its level, derived from the shipped document at call
    time — so it is the index, not a copy of one, and it cannot be behind the guide. On the
    command line, `larkdocio guide` with no arguments prints the same index, and
    `larkdocio guide --section <slug>` reads one part. A name the guide has no heading for raises
    `ValueError` listing every name it does have, so a wrong guess costs no second call.
  - **Reference material is out of the recipe list.** The read-back law and the three Base
    wire-shape references now live in `reference-the-shapes-and-the-law-a-recipe-assumes` instead
    of sitting between unrelated recipes. Their own addresses did not change.
  - **The routing pack that ships beside the wheel needed no update, and that is the proof
    nothing moved.** All **54** guide addresses its six routers cite were re-resolved through
    `larkdocio.guide` on 2026-08-21: every one answers. The pack's own installer copies the same bytes it
    did before — **13,147**, unchanged.
    Two routing clauses were added to the pack **later in this same release**, for the round
    trip's cost rather than for this reorganisation, taking the copied bytes to **13,774**; the
    reorganisation described here still moved nothing, and that clause is left exactly as it was
    measured.
  - **One sentence is shorter in 40 recipes.** Each write recipe still closes by pointing at
    *§ "The read-back law — a green apply is not a receipt"* — the pointer is unchanged and the
    section it names is unchanged. What each of them stopped repeating is the one-sentence
    paraphrase of that section, which the section itself says in full. Nothing became
    unlearnable: the address is right there, and it resolves.

- **THE FILE-FIRST ROUND TRIP NOW SAYS WHAT IT COSTS AT THE DOOR WHERE YOU CHOOSE IT — AND
  NOTHING ABOUT IT BEHAVES DIFFERENTLY.** No engine, plan, refusal, flag default, verb name,
  printed line or rendered Markdown moved: the same input produces the same plan, the same
  refusals and the same bytes it did before this release. What moved is **text you read** — the
  `roundtrip` entry in the description the wheel carries, the `larkdocio roundtrip --help` page,
  the packaged guide's write-recipe routing table, and the guide's own file-first recipe. Each of
  those four now tells you, at the point where you are picking a path rather than three sections
  later, that a block the round trip edits is **re-written from your Markdown**, and each names
  the sub-span edit as the way to change a few words inside a block and keep the rest of it
  exactly as it stands. The round trip is unchanged, still fully supported, and still the right
  tool for changing a lot of a document at once; it is now described with its cost attached.
  `larkdocio guide` has the recipe for either path.

### Upgrade & compatibility

- **Re-copy the update-script template into your repo** (your `scripts/update_larkdocio.sh`,
  whose own header names the development-repository template it is copied from). Two defects
  are fixed in the template this release. **First**, with more than one vendored wheel in `vendor/` the script
  used to compare against whichever sorted first — a stale old wheel beside your current one
  could make `--check` report an update whose "remedy" was a downgrade. It now refuses to
  guess, lists every wheel it found, and asks you to remove the stale ones; with a single
  wheel nothing changes, and the one-line verdict contract (`UP TO DATE` /
  `UPDATE AVAILABLE` / `AHEAD`) is unchanged. **Second**, a build that produced no wheel used
  to die with a bare unexplained exit; it now tells you plainly that the build produced no
  wheel. No wheel API, command, or credential requirement moved — this is the copied consumer
  script only, and if your repo already ported these fixes locally the re-copy is a harmless
  no-op.

- **Migrating a reader of `capabilities()` — the whole list.** (1) add `full=True` where you
  read the payload's own keys; (2) read a surface's `operations` and filter on `kind` if you
  wanted only the dispatched ops; (3) drop `operation_index` — `operations` is complete;
  (4) treat `permissions["scopes"]` as scope strings and look the detail up in `scope_evidence`.
  There is no compatibility shim and no deprecation window: the old shape is gone in this
  release.
- **What the middle rung returns, and which call resolves a key.**
  `capabilities(surface="<id>")` returns that surface's row **and nothing else** — so the scope
  strings in its `permissions` blocks are **keys into catalogs the returned dict does not
  carry**. The catalogs are top-level, so resolving one is a `full=True` call:
  `capabilities(full=True)["scope_evidence"][scope]` for a scope's evidence and
  `["unknown_requirements"][endpoint]` for an endpoint's honest unknown. If you want the
  evidence with the row, ask for `full=True` once and read both out of the same payload.
- **No dependency was added, dropped, or moved** — no pin changed, runtime or otherwise.
- **No CLI command, flag or refusal code changed in this release at all.** On the **error-code
  lookup** specifically there is nothing to migrate either: two **added** public symbols, both
  purely additive and both described under *New capabilities* —
  `larkdocio.errors.note_for` and `larkdocio.errors.ERROR_CODES` — with nothing renamed and
  nothing removed, so code that used them before compiles and behaves as it did. **The one thing
  in this release that does need migrating is `capabilities()`**, and its four-step edit is the
  first bullet in this section.
- **Scoped, because three separate CONSUMER-OBSERVABLE changes ship in this release.**
  (Scoped, not re-counted: the number was and stays a count of the changes that need
  migrating. Internal reorganizations land in the same release without joining this list —
  a module split whose observable surface did not move is not news to you, and the
  engineering log carries it instead.) *For the merged-table fix*,
  the only thing that moves is the Markdown a merged table renders to — no public symbol, no
  command, no flag, no refusal code. *For the typed error routing*, no output changes and no
  symbol is removed; what moves is which operator guidance a failed **download** prints in the
  two cases named above. *For the `capabilities()` reshape*, a public signature and a return
  shape moved and there is no shim — that is the one break in this release, and the bullets above
  are its whole migration.
- **If you pin golden output** of documents with merged tables, expect those goldens to move
  once, at this upgrade, and only for tables whose covered positions actually hold something.
- **YOUR OWN COPY BESIDE THE WHEEL IS UNAFFECTED, AND IT IS STILL THE COMPLETE HISTORY.** The
  refresh script reads the **repository's** `CHANGELOG.md` and `RELEASE_NOTES.md` out of the
  cloned tag tree — never the wheel's packaged copies — so `vendor/larkdocio-CHANGELOG.md` and
  `vendor/larkdocio-RELEASE_NOTES.md` still land complete on every refresh, and the
  what-changed report the script prints at `--check` still spans every intervening release with
  no front edge to fall off. The distribution branch publishes the same complete files. **The
  only thing that narrowed is what is inside the wheel.**
- **WHERE TO READ AN OLDER RELEASE — two addresses, both openable.** `vendor/larkdocio-<DOC>.md`
  beside your vendored wheel, refreshed whenever you update; or the publishing repository's own
  complete copy of that document at its root. The out-of-window refusal repeats both, so a
  caller who guesses wrong is told where to go rather than told nothing exists.
- **NOTHING ELSE ABOUT THESE ACCESSORS CHANGED.** `changelog()` / `release_notes()` with no
  argument still return the document as text; `changelog_sections()` /
  `release_notes_sections()` still return the index of what is addressable, now 8 rows each and
  still derived from the shipped bytes at call time; `capabilities(full=True)["docs"]` still
  carries the same index, which is smaller by the sections that left. No dependency was added,
  dropped or moved. No command, flag or refusal **code** changed.

- **Migrating a hard-coded guide `--section` slug — there is nothing to migrate, and here is how
  to check.** No section name was retired in this release, so every address you hold resolves.
  To prove it against the wheel you actually have rather than against this sentence:
  `python -c "import larkdocio; print([r['slug'] for r in larkdocio.guide_sections()])"`, or read
  the index with `larkdocio guide`. The single exception is `recipes`, which now answers with the
  recipe **index** rather than the whole recipe chapter — its own entry above says what to call
  instead. There is no shim, because nothing was removed.

### Known limitations

- **How Lark's own interface or export treats content at a covered position is unmeasured.**
  There is no evidence either way here, so the absorption above is **larkdocio's stated
  rendering rule**, not a claim to reproduce a rendering that was never measured. It is written
  down so you meet the rule rather than discover it.
- **One position-based drop remains, deliberately.** A cell that declares a span of **zero** at
  a position no other cell's span covers still emits nothing and its content is still dropped.
  That skip is an old safety net against a synthetic payload marking a covered cell `0`; it has
  never been seen in a real document, and it is left exactly as it was rather than changed
  blind. If you have a document where it fires, that is worth reporting.
- **The error-code lookup knows what has been recorded here, and nothing more.** It answers for
  the codes recorded here and no others; every other code returns `None`, and the library keeps
  relaying Lark's own `code` and `msg` unedited either way. Some rows carry **no message text**
  because nobody wrote down what Lark said, and some are labelled `documented-unverified` —
  named in this project's own notes, never seen on the wire here. Both sets are readable off
  the table itself (`[c for c, n in ERROR_CODES.items() if not n.label]`, and
  `n.verification`), which is the only count that cannot go stale. Read those as honest unknowns, not as facts. Nothing
  in the library **branches** on the lookup: it explains, it does not decide, so a missing row
  can never change what a call does.
- **Spreadsheets are deliberately different and are unchanged.** A merged range in a sheet still
  renders the anchor's value and a **blank** for every covered cell, and a stray value at a
  covered cell is still blanked. A pipe table has to emit a cell at every column, so there is
  nowhere to put covered content; a document table emits HTML with real spans, so an anchor cell
  exists that can carry it. The geometry still lives only in each tab's own `merges` array.
- **A FACT ANNOUNCED IN A RELEASE OLDER THAN THE WINDOW IS NO LONGER READABLE THROUGH THESE TWO
  ACCESSORS — read it beside the wheel, or in the guide.** That is the narrowing working as
  intended: these documents are the re-pinning companion and are explicitly not a substitute for
  `guide()`, `writer_brief()` or `capabilities()`, which are where a **standing** behaviour is
  written down and where they stay current. It was checked rather than assumed for this release:
  the upgrade-critical facts that predate the window were measured still present in the shipped
  guide, the shipped writer brief and the refusal texts themselves, so no behaviour a caller
  needs left the wheel — only the release-note announcement of it.
- **THE WINDOW MOVES ON EVERY RELEASE, so the oldest release the wheel carries is a moving
  target.** It is always the newest 8, so a wheel you have held for more than about thirteen days
  of this project's recent cadence may not name the release you are on. If it does not, the
  refusal tells you so explicitly and names both addresses; it does not fail silently and it
  does not pretend the release never happened.

- **A BLOCK THE ROUND TRIP EDITS COMES BACK AS ONE RUN CARRYING THE STYLING THAT BLOCK STARTS
  WITH, SO A COLOUR THAT DIFFERED ELSEWHERE IN THE SAME PARAGRAPH IS FLATTENED ONTO IT
  SILENTLY.** Markdown has no form for a run's colour, so nothing in your edited file can put a
  mid-paragraph colour back: a paragraph that had two colours comes back with one. The colour
  the block *opens* with is carried across the whole replacement, so a paragraph that was one
  colour throughout keeps it. Nothing refuses, nothing warns, and the apply log calls the entry
  `applied`, because it *was* applied. This is not new behaviour and it is not a regression — it
  is the projection's documented residue, stated from this release at the place you choose the
  path instead of only in the reference. Read it with all three of its bounds, because each one
  narrows it:
  - **Styling the authoring dialect cannot create is not flattened — it REFUSES.** Inline bold,
    italics, strikethrough, inline code or an anchored link inside a block you edited refuses the
    whole push (`not-in-dialect`) with zero writes, and a word-level comment anchor on such a
    block refuses at plan time (`comment-anchors-present`), naming the sub-span edit as the
    recovery. Those are loud outcomes, not silent ones.
  - **Blocks you did not edit keep their ids AND their formatting**, and a block the Markdown
    cannot express at all — an image, a board, an embed — is conserved untouched: never edited,
    never deleted, never re-created.
  - **Most block types cannot be reached by this path in the first place.** Of the document block
    types this library knows, the editable set is what the round trip can re-write and everything
    else is conserved — ask `larkdocio.model.conservation.editable_block_types()` and
    `.opaque_block_types()` rather than trust a count in this sentence (12 and 42 as this release
    was written).
  To change a few words inside a block and leave the rest of it exactly as it stands, use a
  sub-span edit instead; `larkdocio guide` has the recipe. Which of the two is better for a given
  edit depends on the block: for a plain-text paragraph the round trip loses nothing at all.

## [1.37.0] — 2026-08-20

### New capabilities

- **The file-first round trip is now ONE COMMAND — `larkdocio roundtrip` — and it is the FIRST
  and ONLY console command that writes to Lark.** The flow the packaged guide teaches as ~80
  lines of Python is a verb you call:

  ```bash
  larkdocio roundtrip pull "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./edit/
  # ...you (or your agent) edit ./edit/document.md — keep every marker where it is...
  larkdocio roundtrip push -o ./edit/            # ALWAYS previews. Writes NOTHING.
  larkdocio roundtrip push -o ./edit/ --apply    # applies THAT plan, then verifies by re-reading
  ```

  Two invocations, because your edit happens **between** them — in another process, or
  tomorrow. `pull` writes two files: `document.snapshot`, which is ours and immutable, and
  `document.md`, which is yours and is the one you edit. In Python it is
  `larkdocio.roundtrip.pull()` / `.push()`, with the same gates in the same order. The runnable
  script it was promoted from **stays in the guide** — you still need it to change the middle.
- **It is PLAN-GATED, and no flag removes the gate.** `push` always builds and prints the plan;
  `--apply` means *apply the plan you just previewed*. The plan carries the revision the
  snapshot recorded, so if the document changed while your edit sat on disk the batch is
  **refused whole, with zero writes** — pull again and re-apply your edit. A snapshot taken with
  no revision cannot arm that guard, and the command **says so loudly** instead of writing as
  though it had.
- **It verifies its own work by re-reading, using compose-equivalence rather than string
  equality** — so a list you authored tight and the reader emits loose is **not** reported as a
  change, which is the trap every hand-written self-check falls into. A block whose content is
  outside the authoring dialect is reported *unverifiable by name*, never quietly counted clean.
- **`push` is the first and only place the command line consults your WRITE credentials**
  (`LARK_WRITE_APP_ID` / `LARK_WRITE_APP_SECRET`); it also needs the READ pair for the
  read-back. The two are separate apps, resolved separately, and neither is ever borrowed for
  the other — a `push` with no WRITE pair refuses **before making any call**, naming both.
- **THE SHIPPED TEXT THAT SAID THE COMMAND LINE NEVER WRITES IS NOW CORRECTED.** `larkdocio
  --help`, and the README in two places, said the command line is read-only. That was true for
  every release before this one and is false now, so it has been replaced by what is true:
  which commands read, which one writes, and that the writing one is plan-gated and refuses
  rather than guesses. **The reason behind the old sentence is unchanged and still enforced** —
  a download must never be able to mutate the document it is reading — so `download`, `folder`,
  `guide`, `config` and `mermaid` still carry no write flag, and a guard now proves the write
  engine is reachable from the command line **only** through the round-trip verb.
- **Nothing else moved.** No new endpoint, no new API scope, no new permission row, no
  dependency, and no change to `reconcile`, `dry_run` or `apply` — the verb is a caller of them.
- **One public constant now carries the media-cleanup evidence, so you can read it from Python
  instead of taking it on trust: `larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`.** It sits
  beside `MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE` and holds the whole disclosure in one place —
  the list of what was attempted, the three results that carry the weight, and the boundary of
  what was measured. Every module that states the fact quotes or cites this constant, so there
  is one sentence to read and no second paraphrase to drift from it. The long form is written
  out in the shipped guide's `§ "The disposables doctrine"`.
- **Two new Base links you can hand a human, and they cost you nothing:
  `larkdocio.base.table_url(base_url, table_id)` and
  `larkdocio.base.view_url(base_url, table_id, view_id, record=None)`.** They build
  `…/base/<app_token>?table=<table_id>&view=<view_id>` — and, with `record=`, the record's
  card — out of ids a Base read already handed you. **They make zero API calls**, so they need
  no scope and spend no quota.

  ```python
  from larkdocio.base import table_url, view_url

  link = view_url("https://your-tenant.larksuite.com/base/AbCdEfG", "tbl…", "vew…")
  ```

  **What they need from you is the Base's own URL**, because the tenant host is an *input*: it
  is read off that URL and never derived from the API domain (`feishu.cn` / `larksuite.com`),
  which is not the host a working link lives on. A hostless URL, a non-`https` URL, a URL that
  is not a `/base/<token>` link, a bare `app_token`, or an empty id is a refusal — never a
  quietly defaulted host. Nothing is resolved or validated: an id that does not exist gives you
  a link that does not open.

  **How far the evidence goes, so you can size the promise.** The grammar was clicked by hand on
  2026-08-17 in the Lark web client, on one tenant, on one Base; the navigating click was made
  against a **non-first** table, because on a first table whose target view is its only view a
  correct navigation and a default landing look identical. The ids were checked byte-identical
  ten days later. The mobile client, the desktop app client, any other tenant and any longer
  span are **unmeasured, not refuted** — the whole disclosure is readable from Python as
  `larkdocio.common.url.BASE_DEEP_LINK_CLICK_MEASUREMENT` and is quoted in the guide's Base
  chapter.

  **For a record, prefer `record_permalink`.** The `record=` parameter works, but
  `record_permalink` returns an address **Lark itself minted**, measured byte-identical across a
  week. The constructed link is the answer when the ids are what you have and a call is what you
  do not want to spend.
- **`parse_deep_link` still answers `NotADeepLink` for a Base `?table=&view=` URL — for a
  better-stated reason.** It used to say the grammar was *unverified*; it has now been clicked,
  so that reason is kept only as dated history. The behaviour is deliberately unchanged, and
  pinned by a test: teaching the parse a new grammar would move a typed return value you may
  already depend on, which is its own change.
- **There is now a small pack of ROUTER SKILLS you can copy into your own repository — and it
  is copied, not installed with the wheel.** The pack lives in the dev repo — the larkdocio
  checkout somebody handed you a path to — at `consumers/skills/`, never inside the installed
  package. Six files, one per task
  shape: read something out of Lark into Markdown, edit a document as a file, author content
  that is not there yet, write rows and cells, work out why a call was refused, and a
  start-here router that dispatches to the other five. Get them with:

  ```bash
  /path/to/larkdocio/consumers/install-skills.sh     # into ./.claude/skills/
  ```

  `setup-consumer.sh` now runs that for you during onboarding. They are **copied on purpose**:
  an agent harness discovers skills as files in your working repository, so a copy inside the
  installed package would sit there doing nothing until something wrote it out.
- **They point at the guide; they do not duplicate it.** Each router answers a task shape with
  an address — the name of a `larkdocio.guide()` section, or the command to run — and stops
  there. That is why they are short, and it is deliberate: a skill file that re-explains what
  the guide explains is a second copy, and the second copy is the one that goes stale when you
  refresh the wheel. Checks in the larkdocio repository hold the shipped copies to it — every
  section name a router cites is resolved by calling `guide()` itself, every console verb is
  checked against the commands the package really registers, and a router repeating a dozen
  consecutive words of the guide's **prose** — anywhere in the document — fails the build, with a
  prose-word ceiling behind it that bounds how long any one router may grow, so a router that
  answers with an essay instead of an address fails too. A quoted code block does not count
  against a router: quoting a command is the behaviour these files are for.
- **The cost of copying is version skew, and it is disclosed rather than hidden.** Your pack
  points at the wheel it was copied from; if your vendored wheel is older, a pointer can miss.
  Every file names the version it came from and tells you to run `scripts/update_larkdocio.sh`.
  After any refresh, re-run `install-skills.sh` so the two move together.
- **A TABLE CELL is a legal `parent_block_id` — you can put an image INSIDE a cell, and the
  guide now shows the whole route.** Pass a cell's block id to `put_image_in_document` and the
  picture is created in that cell; the bytes verify and the block reads back with the cell as
  its `parent_id`. Observed on a disposable document. A table with one picture per row — a
  `Variant | Image` table, say — keeps each picture beside its label, and the recipe now
  carries a runnable script for it.
- **The route to the cell id is the part that was missing, and it is one step longer than it
  looks.** `apply()` hands back exactly **one** created id for a table insert — the **table's**,
  never the cells'. The cells are that block's own `children`, **row-major**, so one `get_block`
  on the id you were handed gives you `children[row * columns + column]`. The recipe now warns,
  in the strongest terms it has, against the obvious alternative: **never find your table by
  re-reading the document and taking the last one.** A document carrying ten or eleven
  tables can end on any of the others; done that way on a document with many tables, four images
  landed in the wrong table and a person had to remove them by hand. And the cost is asymmetric for an image —
  whatever you do to the block, the **upload behind it is permanent**.
- **A new recipe for the state a rate limit leaves behind: an interrupted rewrite whose re-push
  refuses `stale-anchor`.** If a run stops part-way and you push the same batch again, the
  deletes whose blocks the interrupted run already removed are refused one by one — correctly:
  the engine re-reads every anchored block immediately before writing to it, and a block it
  cannot re-read is not the block you previewed. **Nothing about that is being relaxed.** What
  the guide now shows is where the fix belongs: in **your plan construction**. Express the repair
  as *"the document must no longer contain these things"*, re-derive it against a **fresh** read
  every time, and the deletes for blocks that are already gone are never built — so the second
  run of the repair sends nothing at all. The recipe is runnable and its convergence is checked,
  not asserted.

### Behavior changes you can observe

- **BREAKING — if you create a document, a spreadsheet or a Base and do not say WHERE, the call
  now refuses instead of creating it.** `create_document`, `create_spreadsheet`, `create_app`,
  `copy_app` and their plan-level twins `create_base` / `copy_base` all require a
  `folder_token`, and a call that omits it is refused **locally, before anything is sent** —
  nothing is created, nothing is half-created, and no API call is spent. `create_folder` and the
  upload family already worked this way and are unchanged.
- **What to pass instead: the token of a folder you own, created, or were given access to.**
  Open the folder in your own Drive and take the last path segment of its link, or make one with
  `create_folder(name, parent_token)`. The refusal itself names the rule, the argument and both
  routes to a token, so a caller who hits it is told what to do rather than merely stopped. The
  fix on your side is **one argument**.
- **Every spelling of "no destination" is refused alike — including the empty string.** Passing
  `folder_token=""` used to be accepted and filed the new object in the application's own space;
  it is now refused for exactly that reason.
- **Why: the application's own space is not somewhere a person can look.** With no destination
  the platform files the object in the storage belonging to the application identity your
  credentials name. **No human interface lists that space** — not even for an account with full
  administrative rights — its trash cannot be listed or emptied, and **a delete there is a trash,
  not a purge**: the object still resolves afterwards. Anything that lands there is reachable
  only through a token somebody kept, and unreachable forever once that token is lost. On the
  measuring tenant that default had accumulated a root full of strays and more than 1,600 trashed
  Bases. (Objects there may also surface in search — **not measured by this project**.)
- **There is no compatibility shim and no opt-out.** No flag, no configuration key and no
  keyword restores the old default, and none is coming: the old default is the behaviour this
  change exists to remove. If you were relying on it, pass a folder you can see.
- **A new error type, and it is a `ValueError` too.** The refusal is
  `larkdocio.errors.MissingDestinationError`, a subclass of both `LarkConfigError` and
  `ValueError`, so an existing `except LarkConfigError` — or an `except ValueError` around
  argument handling — still catches it.
- **What is NOT affected: creating something inside an object you already named.** Blocks in a
  document, a table, column, row or view in a Base, an image anchored in a workbook, a version of
  a file, a comment on a file — all unchanged. There the parent is the destination and you
  supplied it already.
- **`capabilities()` says it too**, as the safety contract `caller-supplied-destination` on the
  document, spreadsheet, Base-schema, folder and file-upload surfaces — so the rule is readable
  from code as well as from the guide, whose § "Where a new object goes — you name the
  destination, or nothing is created" states it once and in full.

- **A disclosure you were already relying on got stronger, and nothing you call behaves
  differently.** The library used to tell you that an uploaded Drive media token is permanent by
  saying *no verb purges drive media* — a sentence about **larkdocio's own surface**, said in
  **the platform's voice**, with no list of what had actually been tried behind it. It now says
  the falsifiable thing instead: **no ROUTE in Lark's open API purged a Drive media token**,
  with the attempts enumerated so you can see where the evidence stops. If you match on these
  strings, they have changed; if you read them, they now tell you more.
- **The enumeration, in one breath.** **Nine** distinct destructive request spellings, across
  **fourteen** sends, against **four** media tokens minted on **both** of this library's media
  paths (two on the sheets float-image path, two on the docx image path): **not one removed a
  media token**, and a liveness check answered *still resolves* after every send. Three results
  carry the weight and are not averaged in with the rest. The one **documented** delete route,
  `DELETE drive/v1/files/:token?type=file`, refuses a media token with **HTTP 404** and code
  `1061003` identically on both paths, while a **positive control** in the same run under the
  same credential deletes a real Drive file (`code: 0`, and an independent re-query answers *is
  deleted*) — so the refusal belongs to the token, not to the credential. That route's own error
  body prints a **closed** `type` enum — `file, docx, bitable, folder, doc, sheet, mindnote,
  shortcut, slides` — containing neither `media`, nor `sheet_image`, nor `docx_image`, all three
  of which were sent and all three refused with the server echoing back the value it received.
  And **unbinding is not a purge**: deleting the only block that referenced a bound token
  answered `code: 0`, the parent's children read back empty, and the token still resolved.
- **"There is no move" is no longer a statement about this library — it is a measurement about
  Lark, and the shipped text says so.** The guide, and the machine-readable
  `capabilities()["surfaces"]["docx-write"]["absences"]` row, used to tell you that larkdocio
  ships no move request family and that *whether Lark's own API exposes a move route anywhere
  is unmeasured, not refuted — nothing here was probed for one*. That sentence is **superseded
  by measurement** and is gone from the shipped guide: **Lark's docx `v1` API exposes no route
  that moves or reorders an existing block**, probed on 2026-08-16 over **eleven enumerated
  candidate spellings**. Two move operation keys on the documented block `PATCH` route and its
  `batch_update` twin answered `1770001 "invalid param"` — and a control showed that is the
  code an operation key the route has never heard of answers, not a complaint about the body.
  Adopting an existing block id as a child was refused `99992402` with `children[*].block_type
  is required`. Five invented `…/move` spellings answered the gateway's own non-JSON HTTP 404.
  So **delete-and-recreate is the shape the surface offers**, not a gap this library has yet to
  close, and the restructure recipe now rests on that rather than on our own absence. If you
  were waiting for a move operation before reorganising a document, stop waiting.
- **The trap that makes it dangerous rather than merely inconvenient: a `code 0` that means
  *duplicated*.** `POST /open-apis/docx/v1/documents/{doc}/blocks/{parent}/descendant`, given a
  well-formed body that names an **existing** block id, answers HTTP 200 `code 0 "success"` and
  **creates a NEW block** — it reads the live id as a *client-side temporary* id and hands it
  back as `temporary_block_id` beside the new block's real id in `data.block_id_relations`.
  Read back, the original was still in its original place and the child order was **unchanged**.
  **If you call that route yourself and read `code 0` as "moved", you have shipped a
  duplicate.** The warning now sits in the guide beside the routing decision it changes, and
  it is the sharpest reason the read-back law is not optional on a reorganisation.
- **The two facts carry different verification labels, on purpose.** *larkdocio ships no move
  request family* is **derived from the shipped surface** — a closed set in this library's own
  code, checkable without a call. *Lark's docx `v1` exposes no move route* is **measured**. The
  `absences` row keeps the weaker label on itself, because its statement is about this library;
  the measured half carries its own label and its own scope inside the row's `evidence`. If you
  read that row programmatically, read both.
- **READING A BASE TO MARKDOWN NOW KEEPS THE URL ON A DOC-MENTION CHIP — so some cells that
  used to render as bare text will render as `[title](url)`.** A Base text cell reads back as a
  segment array, and a segment can be a plain run of text, a link, or a **chip**: the thing Lark
  mints when a human touches a cell holding a pasted document url, replacing the url on screen
  with the document's title. The chip carries **both** halves, and `read_base_markdown` used to
  keep only the title. It now renders the chip through the very same serializer an ordinary
  link goes through, so the two are byte-identical.
- **This is a link becoming visible, not text changing meaning.** The words already in the cell
  are still there and still say the same thing; what is added is the url that was already in the
  payload and was being discarded on the way out. If you freeze `.md` snapshots of a Base, expect
  a **one-time diff** on exactly the cells someone has chipped — those snapshots were quietly
  under-recording their anchors, and merely chipping a cell used to show up in a diff as though
  the content had been edited. Nothing else about the projection moved.
- **The plain projection is deliberately unchanged.** `cell_text` and `plain_value` still hand
  back the visible text with the url dropped — that is what "unescaped, undecorated" means, and
  it is the right string to key a dict on. If you want the url, take the Markdown projection or
  read the segments yourself. The guide's Base-to-Markdown recipe now states all of this in one
  paragraph, including where the evidence stops.

- **A FOLDER GRANT IS NOW KNOWN TO BE REFUSED — on the tenant it was measured on — and the
  library says so where you meet it.** Asking this surface to grant on a `folder` has always been
  refused **locally, before any call**, and that has not changed. What has changed is why: the
  message used to say the container question was simply unmeasured. On **2026-08-17** it was
  measured. A grant sent to `POST /open-apis/drive/v1/permissions/<token>/members?type=folder`
  answered **HTTP 403 · `{"code":1063002,"msg":"Permission denied"}`** on **three enumerated
  write spellings**: `full_access` with `need_notification=false`; the `view` level; and the same
  body with `need_notification` omitted entirely.
- **The claim is exactly "Lark refused the write" — never "the grant did not store".** Those are
  different claims and only one of them is measured. The read that would tell them apart does not
  exist on that tenant: the member listing answers `99992402` for `?type=folder`, and its own
  `field_violations` print the route's own `type` enum —
  `[doc, sheet, file, wiki, bitable, docx, mindnote, minutes, slides]` — which **does not contain
  `folder`**; sending no `type` answers `99992402 "type is required"`. **The two bodies
  contradict each other. Both were captured and neither was reconciled away**, because tidying
  one of them out of the record would be inventing an answer nobody has.
- **The scope ships with the claim, and everything outside it is still unmeasured, not refuted.**
  One day, one tenant, one application identity, a `tenant_access_token` (the write credentials),
  and exactly that route and that spelling set. **`file`, `wiki` and every other object type stay
  UNMEASURED rather than impossible** — nobody has asked, so nothing is claimed — and no grant was
  ever attempted on a raw uploaded file or a wiki node. **The refusal you already get is
  unchanged**, and so is everything the surface does grant on: `docx`, `sheet` and `bitable` are
  untouched. Nothing was widened by any of this — no new object type can reach the wire, and this
  library never requests, widens or escalates a scope; a grant is a console action.
- **THE SAME CORRECTION REACHES EVERY PLACE YOU READ IT.** Three shipped sentences still told you
  a `folder` grant was unmeasured — the packaged guide's *"WHICH OBJECT TYPES"* paragraph (the one
  `larkdocio.guide()` hands you), the front-door README the wheel carries as its own `METADATA`
  body, and the Drive capability matrix **in the dev repo**. All three now say what was measured,
  scoped, and all three still
  say `file` and `wiki` are **unmeasured rather than impossible**. If you read only one of them,
  you now get the same answer as if you read all three.

- **"IS THIS FOLDER UNREACHABLE, OR DOES IT NOT EXIST?" — THE ANSWER DEPENDS ON THE ROUTE, AND THE
  DOCS NOW SAY WHICH.** Until now the Base copy surface told you flatly that the two cases are
  indistinguishable because *Lark* answers `1254702` to both. That is what the **Base copy** route
  answered when it was measured — and it is **not** what every route answers, so the sentence is
  now **scoped to that route** rather than stated about Lark. The measurement itself is unchanged
  and still ships; only its reach was too wide.
- **The other half, measured 2026-08-17:** `create_document`, handed a real folder the account
  holder owns and your application was **not** granted, answers **`403 · 1770040 "no folder
  permission"`** with Lark's own help text — an **actionable denial**: ask for access to that
  folder. A folder that genuinely does not exist answers `1254702 DriveNodeNotExist`. So on that
  route the two cases *are* distinguishable, and if you were told otherwise you may have stopped
  looking for a denial you could have acted on. Scope, stated because it bounds the claim: one
  tenant, one application identity, `tenant_access_token`, that one route, **one honest send**.
- **What this changes for you: words, not behaviour.** No refusal, error type, request or code
  path moved — the library still relays Lark's own code and message unedited and asks for no
  further permission. The Base copy route's own unreachable-folder case has **not** been
  re-measured, and the docs say so instead of implying it was: read the code you actually got
  rather than the one another route taught you.
- **Passing `width` or `height` to `put_image_in_document` now LOGS A WARNING** on the
  `larkdocio` logger, naming what happens to them, both measurements behind that, and the one
  lever that works. It is a disclosure, not a refusal: the call does exactly what it did
  before, the parameters are unchanged, and omitting both is silent. If your logging is
  configured at `WARNING`, expect one new line per image you size at create time — and the
  fix for the line is the fix for the picture: size the bytes instead. The shipped guide's
  image recipe no longer passes them.

- **An authored IMAGE BLOCK can now be deleted, and the refusal that used to stop you has
  narrowed.** A `DeleteRequest` targeting `AnchorById(block_id=<the id
  `put_image_in_document` returned>)` used to refuse `write-hostile-target`; it now resolves
  and applies. This was **measured, once, 2026-08-19**, and the verdict was taken from a
  **read-back and not from the delete's own success code**: after the call the parent no longer
  listed the block and a direct read of the id answered *not found*, with a **control** — the
  same call, the same parent, the same run, against a text block — answering identically, so the
  result belongs to the block type rather than to the harness.
- **What this fixes for you.** Delete-and-recreate is the only way to restructure a document
  (there is no move operation), and it used to stop converging the moment a document contained
  a picture: the inserts landed, the image deletes refused, and every pass left another stranded
  copy. That pattern now completes.
- **Two things to know before you rely on it.** **(1) Use the id, not a quote** — an image
  carries no quotable text of its own, so a quote-anchored delete still refuses, with the id
  route named in the refusal. **(2) Deleting the block reclaims nothing** — the upload is still
  permanent tenant residue, so putting the picture back somewhere else is a **new** upload and a
  **second** permanent media token. Blocks move for free; bytes accumulate.
- **What did NOT change.** An image still refuses as an **edit** target, a **sub-span** target
  and an **insertion reference** — it carries no text to patch and nothing to anchor to — and
  every other write-hostile kind (board, iframe, Base embed, Sheet embed, Base named-view, both
  synced kinds) still refuses **every** operation including delete. The plan gate and the
  exactly-one-or-refuse contract are untouched; the destructive-safe removed-block capture is
  unchanged for every other block type and now records the picture too — see the next entry.

- **A deleted image's apply-log entry now records the picture it removed.** `removed_payload`
  is the destructive-safe record captured from the live block immediately before a delete, and
  for an image block it used to read `{'block_id': …, 'block_type': 27, 'elements': [],
  'style': None}` — the file token, the width, the height, the alignment and the scale all
  dropped, because the capture looks for a text container and an image has none. It now carries
  the block's `image` object **verbatim**, so the record names what was destroyed instead of
  only which id is gone. **If you log the apply log as your undo trail, a delete entry for an
  image gains one key.** Every other block type's record is **byte-identical** to before: the
  `image` key is absent, not empty, for anything that is not an image — the same rule the
  diagram's `add_ons` key has always followed. Nineteen block shapes were diffed before and
  after to confirm it.
- **What that record is: a reference, not a restore.** The captured token still names bytes
  that exist — deleting the block purges no media, and no route in Lark's open API does — so
  you can say exactly what was removed and fetch it back with `DocxMediaClient.download`.
  **Nothing in this library re-binds a captured token to a new block**: `put_image_in_document`
  takes no pre-made token, so putting the picture back is a fresh upload and therefore a new
  permanent media token beside the old one. Whether the platform itself would accept a re-bind
  is **unmeasured**, and this release does not measure it.
- **The Base copy route DOES tell an unreachable folder apart from one that does not exist, and
  the two answers call for two different actions.** Handed a **real folder this application has
  no permission on**, a Base copy answers `1254701 DriveNodePermNotAllow` and copies nothing.
  Handed a folder-shaped token naming nothing — or a real Drive object that is not a folder — it
  answers `1254702 DriveNodeNotExist` and copies nothing. Handed a real folder it can reach, it
  takes the copy and the copy reads back inside that folder's own listing. **So check the code
  you actually got:** `1254701` from this route means the folder is real and your application is
  not allowed into it, so ask a workspace administrator to grant access to that folder — a grant
  is a Lark console action, and the library never widens, requests or escalates a scope;
  `1254702` from this route means the token is wrong.
- **Words, not behaviour.** No refusal, error type, request body or code path moved, no scope
  moved, and the library still relays Lark's own code and message unedited and asks for no
  further permission. What changed is that the docstring, the packaged guide (prose and the copy
  recipe's comment) and the Base capability matrix used to say the two cases could not be told
  apart on this route — an inference, not a measurement. It has now been measured, and they can.

### Upgrade & compatibility

- **One dependency moved, and it is opt-in tooling: `mutmut` has left the `dev` extra for a new
  `mutation` extra.** The wheel's metadata gains `Provides-Extra: mutation`, and
  `pip install "larkdocio[dev]"` no longer installs `mutmut` or the dependencies it brings with
  it — one of which, `setproctitle`, makes a parallel test run freeze the whole desktop on
  macOS. **What to do:** nothing, unless you were relying on the `dev` extra to bring the
  mutation-testing tool, in which case ask for the `mutation` extra instead. **No runtime
  dependency was added or dropped and no pin moved**, so the library you import is unaffected.
- **The Base Markdown change above moves rendered bytes for one specific kind of cell** — a text
  cell holding a document chip — and for nothing else. If you diff Base snapshots, take the
  one-time diff deliberately rather than treating it as drift; if you compare on *plain* text,
  nothing you see moves at all.
- **THIS RELEASE BREAKS ONE THING ON PURPOSE, and it is the destination rule above.** A
  create-class call that named no `folder_token` used to succeed and now refuses. Nothing else
  was removed or renamed: no symbol, CLI flag, refusal code or return shape changed, and one
  public constant plus one new error type are added. **What to do:** pass a folder you can see
  to `create_document`, `create_spreadsheet`, `create_app`, `copy_app`, `create_base` and
  `copy_base` — that is the whole migration, one argument per call site. **There is no
  compatibility shim and no opt-out**, by design.
- Beyond that, an upgrade is text-only unless you assert on the exact wording of the
  media-cleanup disclosure, in which case update the expected string.

### Known limitations

- **A docx TABLE CELL CANNOT CARRY A LINK ANCHOR — and this is now said next to the recipe that
  makes you expect one.** `NewBlock.table(rows=…)` takes a plain string per cell: there is
  nowhere on a cell to hang a `TextSpan`, so the `rich_paragraph` link anchor has no table-cell
  equivalent, and a Markdown table whose cell carries `[Example Item](https://…)` is refused like
  any other inline link, naming its line. **The route that does work is the bare URL**: put the
  URL in the cell as plain text and it reads back as a live link, because the reader auto-links
  a bare http / https URL everywhere it renders literal text. What you lose is the **label**.
- **The limit of that claim ships with it.** What is measured is **this library's own surface**:
  larkdocio offers no route to a styled or link-carrying docx table cell at create time. Whether
  **Lark's** own API can style a docx cell at create time has never been probed, so nothing says
  the platform cannot do it — that half is **unmeasured, not refuted**.
- **Two Markdown-authoring traps that a text sanitiser can produce for you, now documented with
  the repair.** (1) A list item whose text begins with `#` or `>` — `- # Heading` — parses as a
  heading (or a quote) *nested inside* the item and leaves the item itself empty, so the whole
  fragment is refused `empty-list-item` naming a bullet you were sure had text on it. Escape the
  marker (`- \# Heading`) and it composes as literal text. (2) Ordinary prose in **angle
  brackets** is HTML to a Markdown parser: `Lorem <ipsum dolor> sit amet` is a well-formed open tag,
  so one bracketed word refuses the batch. Measured: `<ipsum>` and `<ipsum dolor>` refuse,
  `<ipsum_dolor>` and `A <= 3` do not. Escape the bracket, or write `&lt;`; **backticks do not help** — that is
  an `inline-code` refusal instead. Both refusal messages now carry the repair as well.
- **There is still no `allow_missing` on `DeleteRequest`, and none is promised.** A delete whose
  target has already gone is refused, by design; the repair recipe above is the supported answer.
- **The `1254701` observation is ONE SEND, and it is not a general mapping.** One tenant, one
  application identity, `tenant_access_token`, the Base copy route, 2026-08-18, one send with no
  retries. It establishes that the two codes come apart **on that route**; it says nothing about
  another route, another tenant, another region or a `user_access_token`, and those stay
  **unmeasured, not refuted**. Placement of a copy into a folder that is not the default
  destination also remains **unmeasured, not refuted** — on the measuring tenant the only
  addressable folder was the application's own root.
- **A Base Markdown read is still NOT promised to be link-lossless for every cell a human has
  touched.** The chips actually observed in a Base cell are **document** mentions, on one
  tenant, on one day. The chips a person (**@user**) or a group chat (**@chat**)
  produces are **unmeasured** — nobody has captured one, so nothing is claimed about what they
  carry. What can be said is that the rule keys on a segment *having* a url rather than on what
  kind of chip carries it, so a kind nobody has seen is written down by the same rule the day
  one arrives.
- **Writing a chip into a Base text cell is still refused by the platform, and the enumeration
  grew by one route.** Fourteen segment spellings were already refused `1254060
  TextFieldConvFail` on both single-record write routes; the batch create route has now been
  asked once, with a real chip, on a throwaway Base — and it answered the same way. The batch
  *update* route and cell values seeded at table-creation time were not asked and stay
  **unmeasured, not refuted**. A Base text cell still takes a plain string on write.
- **The claim does not exceed its scope, and the scope ships with it.** One tenant, on one day,
  on `larksuite.com`, with a `tenant_access_token`. A **`user_access_token` is unmeasured** — and
  a human trash UI does exist for a user identity, so a user-scoped route is the most plausible
  unprobed thing. Every spelling outside the nine is **unmeasured, not refuted**, and an API
  gains endpoints.
- **A Base-parented media token borrows nobody's evidence.** The four probed tokens were
  sheets- and docx-parented, so wherever the library talks about `bitable_file` /
  `bitable_image` attachments it now says plainly that those spellings are **unmeasured, not
  refuted** for a Base-parented token, instead of inheriting the other paths' result.
- **What this means for you is unchanged, and now provable: an upload is permanent before you
  send it.** No purge verb was added, and there is none to invent — the measurement is that the
  route does not exist. The only lever that reduces the leak is validating the bind target
  **before** the upload. Record the tokens you mint; recording them is the only thing anyone can
  do with them.
- **The no-move measurement does not exceed its scope, and the scope ships with it.** One
  tenant, one day (2026-08-16), a `tenant_access_token` on the write credential pair, the
  `larksuite.com` OpenAPI domain, docx **`v1`**, on three plain `docx` documents the probe
  created and destroyed. **Explicitly unmeasured — neither refuted nor supported:** a
  `user_access_token`; any other tenant; **wiki-wrapped** documents; any docx API version other
  than `v1`; the Lark web client's internal reorder API; any move spelling outside the eleven;
  and whether the descendant route deep-copies a whole **subtree** — the block it copied was a
  leaf. The pinned SDK agrees from the offline side (its block-update request declares sixteen
  operation fields and none moves or re-parents a block), but that is evidence about a
  published spec at one pinned version, not about the live gateway, and the claim does not rest
  on it.
- **No move verb was added, and there is none to invent.** A larkdocio `move_block` could only
  be delete-and-recreate underneath, which mints a new block id, breaks every anchor and deep
  link you hold to the old one, and orphans anything anchored to it — a verb whose name would
  promise what the API cannot honour.
- **This applies to the docx `v1` block surface only.** The separately measured column-order
  absence on the sheets and Base surfaces is a different measurement about different routes;
  neither result carries the other, and the guide states each on its own evidence.

- **A table you author on its own now goes into the document in ONE call — and either it all
  lands or none of it does.** Up to **499 cells**, `larkdocio` sends the whole table — the grid,
  every cell, every cell's text — as a single request. A 6-column × 36-row table was measured at
  **one call, 0.82 s**; the same table cost 37 calls and 12.4 seconds in the
  last release, and 463 calls and over two and a half minutes before that.
- **The failure mode this removes is the one that left a wrong table in your document.** The
  older construction creates the grid, then grows it a line per call, then fills the cells — so
  a failure partway through leaves a real, half-built table behind. The one-call route has no
  such middle: Lark takes the subtree whole or takes none of it, and a refusal leaves the
  document exactly as it was. If a table matters to you that way, keep it as its own insert and
  inside 499 cells — that is precisely the condition that puts it on this route.
- **Which route your table takes is decided from your content, and the other one has not gone
  away.** A table that shares an insert with other blocks, or one over 499 cells (up to the
  500-cell authoring cap), still takes the create-grow-fill route exactly as before. **Nothing
  is refused for being on either side of that line**, and the table you get is the same either
  way: the same content authored both ways reads back **identical** through this library's own
  reader. The guide's § "What authoring a table costs, and where the 500-cell cap comes from"
  now describes both routes and what each costs.
- **Nothing you hold changes.** The insert lands at the same position it always did — beside
  your own reference block, in a batch with other edits as much as alone — and `apply()` still
  reports exactly one created block id for a table insert, the table's, usable as an
  `AnchorById` for your next edit. No new API scope, no new permission, no new dependency, no
  change to `compose`, `dry_run` or `apply` as you call them.
- **Where the 499 comes from, and how far it is known to hold.** Lark's own ceiling is **1000
  blocks per subtree request**, and a table subtree is `2 × cells + 1` of them — measured by
  bisection: 499 cells (999 blocks) is accepted and read back, 500 cells (1001 blocks) is
  refused with nothing created. Measured on one tenant, with a tenant access token, on docx v1
  documents the probe created and that are **not** wiki-wrapped. Other tenants, user access
  tokens and wiki-wrapped documents are **unmeasured, not refuted**.
- **An image's display size is chosen ONCE, by the bytes you upload — `width`/`height` do not
  survive the bind.** `put_image_in_document` accepts them, the binding `replace_image` PATCH
  replaces the whole image property, and the block reads back at the uploaded file's own pixel
  size: authored `560x560` → read back `2560x2560, scale: 1` (consumer-observed on one day,
  four images); authored `120x60` → read back `1x1, scale: 1, align: 2` on a **1x1** PNG
  (captured, 2026-08-19, one image). The numbers differ because the files differ; both are
  consistent with the bind writing the file's own pixel dimensions, and neither sample isolates
  that mechanism, so that is not claimed as proven — what is claimed is that **the values you
  pass are not the values that come back**. **Nothing resizes it afterwards** on any measured
  route: `replace_image` with size answers `99992402`, `update_image` and a bare `image`
  property answer `1770001`, and `update_image_scale` / `update_block_property` were refused
  too — other spellings are **unmeasured, not refuted**, and no resize op ships.
  **So: DOWNSCALE THE IMAGE BYTES BEFORE YOU UPLOAD.** That is the only lever. And watch the
  filename while you do it — Lark exports a whiteboard as **JPEG bytes named `.png`**
  (consumer-observed on one day, five exports), so a check that trusts the extension returns
  nothing on exactly the images most likely to be oversized; dispatch on the bytes' header.
  larkdocio itself never inspects, decodes or re-encodes image bytes, so it is unaffected.
  If you get it wrong, the **block** can be deleted and re-authored by its id — but the upload
  is permanent and the re-upload mints a **second** token, so the bytes accumulate either way.

- **Images inside table cells: what your Markdown carries, and the one position it does not.**
  An image in a table cell does reach your Markdown — on its own in a cell, beside text, two in
  one cell, in a nested table, under a list item, inside a callout, and in a merged table's
  anchor cell. Two things are worth knowing before you audit a document by counting its
  projection. **First, a merged table's cells are rendered as HTML**, so an image there arrives
  as `<img src="…">` rather than `![](…)`; a count that greps only `![` will under-report a
  heavily merged document, and that is a counting artefact rather than lost content. **Second,
  an image sitting at a grid position covered by a neighbouring cell's row- or column-span is
  dropped** — the covered position emits no cell at all and its content goes with it, and the
  image file is still downloaded even though nothing links it. That limit is now written down in
  the block-support matrix instead of being left to be discovered. **If you have ever taken a
  media count from a projection, re-take it counting both spellings.** Nothing about the
  rendered output changed in this release; what changed is that the limit is now stated.
- **The image-delete result covers image blocks and nothing else, and the scope ships with it.**
  One tenant, one application identity, a `tenant_access_token`, `larksuite.com`, a plain docx,
  one route (`…/blocks/{parent}/children/batch_delete`), one block type (image, 27), one parent
  kind (a table cell), one date, **one send**. Whether the same route removes a **board**, an
  **iframe / Base / Sheet embed**, a **Base named-view** or either **synced** block is
  **unmeasured, not refuted** — those still refuse, and the refusal says exactly that rather
  than claiming their delete fails. Whether any *other* route can is unmeasured too.
- **A quote anchor still cannot delete a picture.** This is a property of the block, not a gap
  in the engine: an image's only quotable text is its caption, which does not appear in the live
  block's text runs, so the delete path's pre-write precondition (*the quote must still be a
  substring of the live text*) can never hold for one. Hold the `block_id`
  `put_image_in_document` returns and target it with `AnchorById`.
- **There is still no way to un-upload.** Deleting an image block does not purge its bytes, and
  no route in Lark's open API does — so an image-heavy reorganisation costs one new permanent
  media token per picture that actually moves. Plan for that before the run, not after it.
- **A complete undo record is not an undo.** A delete's `removed_payload` now carries an
  image's token and geometry, which is enough to *name* what was destroyed and to download the
  bytes again — and that is all it is promised to be. There is **no restore operation**, and this
  library will not re-attach a captured token to a new block, so recovering a deleted picture
  means uploading it again and accepting a second permanent token. Treat the record as
  evidence, not as a rollback.

## [1.36.0] — 2026-08-16

### New capabilities

- **Read a document's tenant SECURITY LEVEL — one call, READ credentials, nothing to hand-roll.**
  `DriveClient.document_security_level(document_token)` returns the `sec_label_name` a tenant's
  tenant security-level policy puts on a docx — the field that can require a **human** to
  choose a level in the Lark client before editing is allowed at all. It rides the same
  documented `POST /open-apis/drive/v1/metas/batch_query` the folder-title leg already uses, so
  it needs no new scope, no write credentials and no new dependency; **one token per call** (the
  batched form is not shipped), `doc_type` defaulting to `docx` and passed through for any other
  value so Lark answers for it. **The answer has THREE cases, not two**, distinguished in the
  returned type rather than in a comment: `level` is what Lark reported, carried verbatim and
  never normalised, mapped or ranked; `level == ""` **means no level is set** — a value, not an
  absence, and `no_level_set` reads it without anyone comparing to `""` at a call site; and
  `level is None` with a `disclosure` means the key was absent or the call could not answer,
  which is never quietly turned into an empty string. `outcome` names all three. **The level is
  not settable through this library or through any route found** — choosing one is a human's
  action in the Lark client, or an administrator's in the console — and what stays *unmeasured
  rather than refuted* (a `user_access_token`, admin/console routes, whether `"Label A"` is a stable
  id or a localised display string, object types beyond docx) is carried on the result itself.
  If you had concluded that fetching this for a document needed a private API, that was measured
  false: the route is documented and this library was already calling it.
- **A READ CAN NOW TELL YOU A TAB IS HIDDEN — `SheetTab.hidden`, no write credentials, no extra
  call.** The last release told you the opposite, and it was true then: the tab objects a read
  handed back had no visibility field, so a hidden scratch tab landed in a status report looking
  exactly like a live one, and asking meant building a write client with credentials a reporting
  job has no business holding. The field was on the response the whole time and this library was
  discarding it. Every tab `query_sheets` returns now carries `hidden`: `True` hidden from
  someone opening the spreadsheet, `False` visible, `None` the payload did not say. **`None` is
  not `False`** — an unanswered visibility is never reported as *visible*, the same rule the
  frozen-panes read follows, so a report that treats `None` as visible is making a claim this
  library did not. **It costs nothing**: the same one request, the same endpoint, read
  credentials. **What is measured and what is not**: the field was read back on
  `GET /open-apis/sheets/v3/spreadsheets/{token}/sheets/query` with a tenant token on
  2026-08-16, one hidden tab and one visible tab, the hidden state confirmed independently
  through the workbook's xlsx export. Whether the older metadata routes report visibility is
  unmeasured, and nothing here tells you what scopes your app needs.

### Behavior changes you can observe

- **A record permalink is now described as MEASURED durable across a week — and still not as
  permanent.** `record_permalink` used to tell you its address was byte-identical across
  sessions on the same day and that anything longer *had not been measured*, so it claimed no
  permanence. It has since been measured: the same links were re-read a week later — on
  2026-08-15, seven and eight days after the first read, through this same call — and came back
  **byte-identical**, five links out of five, with no re-mint, no rotation and no expiry
  parameter. The `resolved` state's note and the guide's *Stability* bullet now say that, and
  they keep both dates so you can see what was known when. **What this does NOT say**, on
  purpose: durable is not permanent — the evidence is **one week, one tenant, that read route,
  with the records intact**, and nothing is claimed beyond it (a longer span, another tenant, or
  a record somebody deletes is still unmeasured). And a durable address is **no promise the
  content behind it is fetchable**: attachment permalinks came back byte-identical while
  downloading their bytes answered `HTTP 404` with an empty body — the link can outlive what it
  points at. **What you can now plan on:** re-verifying a batch of links collapses to *"does
  this record still exist"*, which is one batched read for many ids and is exactly what
  `record_permalink` already returns, typed — `resolved` / `unminted` / `absent` / `forbidden`.
  No signature, state, request or return shape changed; only the words did.
- **Deleting a Base table does NOT leave every inbound link dangling — the two link kinds are
  destroyed differently, and the guide, the register and the previews now say so.** Eleven
  shipped sentences read *"a table delete leaves every inbound `SingleLink`/`DuplexLink` in
  every other table dangling"*. Measured per kind on the table-delete route, twice, that is
  over-broad: an inbound **one-way** (`SingleLink`) column **survives and dangles** — it keeps
  the dead table's `table_id`, its `table_name` drops out, its cells keep the deleted records'
  ids, and a record search on the surviving table still answers success — while an inbound
  **two-way** (`DuplexLink`) column **does not survive at all**: its twin lives inside the table
  you deleted and the source column goes with it, column and contents. **Both losses are
  silent**, and neither is recoverable through the API. Nothing about how a delete behaves
  changed and no preview enumerates a different set of columns; what changed is that the
  sentence an inbound two-way column carries now states the measured outcome instead of hedging
  between two, and each corrected sentence names the **route** its reading was taken on —
  deleting a link **column** is a different call from deleting a **table**, and neither one's
  evidence is borrowed for the other. **What this means for you:** if you planned around an
  inbound two-way link surviving a table delete so you could detect it afterwards, it will not
  be there; `dangling_link_columns` reports the one-way survivors, and the loss preview names
  both kinds **before** the delete, which is the only place either loss is visible.
- **The delete-table preview's own headline no longer contradicts the rows beneath it.** The
  `what` sentence `table_delete_loss()` returns said every inbound link *survives with the dead
  table's id*, while the `inbound_links[].effect` in the **same returned dict** correctly told a
  two-way column it *does not survive at all*. A caller reading top-down met the wrong one
  first. The headline now states both outcomes and defers to the per-column entries beside it.
  **Where else the corrected sentence reaches you** — each of these carried the over-broad
  wording and now states the outcome per kind: the invariant quoted by **every** destructive
  refusal on this surface (the paragraph a refused delete ends with), the
  `cross-table-loss-preview` entry of `capabilities()["safety_contracts"]`, the row for that
  same contract in this guide, `delete_table`'s own docstring, and the documented meaning of a
  plan entry's `loss_preview` field.

### Upgrade & compatibility

- **No dependency moved** — nothing added, nothing dropped, no pin changed.
- **One field was ADDED to a public read type and nothing was renamed or removed.** `SheetTab`
  gained `hidden`, appended **last** in its field order, so a tab you construct positionally
  keeps working unchanged and one you never inspect behaves as before. **The Markdown a
  spreadsheet renders to is byte-identical** — a hidden tab still renders under its own heading,
  with no marker — so goldens you compare against do not move. If you serialize a `SheetTab`
  generically (`dataclasses.asdict`, a schema check, a snapshot test), that output now has one
  more key.
- **The corrections below are wording inside strings you may already be displaying**: if you
  assert on the exact text of a loss preview, a refusal, a safety-contract summary or a
  docstring, those assertions will need re-reading. The registry's canonical output is **163
  bytes** larger for the one corrected contract summary and nothing else — no operation,
  endpoint, scope, flag or contract id moved.

### Known limitations

- **Whether Lark's table-delete cascade is deterministic under load is still unknown.** One
  reading of a surviving two-way column exists against seven readings of it not surviving. The
  refutation of the timing explanation was taken on a **quiet** tenant across a 40-second
  window; a busy tenant was not measured, and nothing here claims more than that. If you see an
  inbound two-way column outlive its target table's deletion, that is a real observation, not a
  bug in the reading above — the loss preview names both kinds before the delete either way.
- **Live verification of this correction cost seven permanent media uploads.** Each run of the
  relational gate mints one media `file_token` that no open-API verb can purge; seven were spent
  across this work, knowingly, and no cleanup leg exists because there is nothing to call. This
  affects the development tenant only — it changes nothing for a consumer of the wheel.

## [1.35.0] — 2026-08-15

### New capabilities

- **A recipe for the two rich-cell writes that shipped invisible** —
  *Recipe: write a hyperlink and a styled run into a cell*, reachable by name from
  `guide_sections()`. `RichCellWriteRequest.hyperlink()` and `.styled_runs()` have shipped and
  worked since the sheets rich-cell write landed and had **zero** mentions anywhere in the guide plus `__doc__ is None` on
  both constructors, while their siblings `mention()` and `multi_select()` each had a recipe.
  **Nothing about either capability changed** — they are simply findable now, with a runnable
  example the suite executes and a real docstring on each of the four rich constructors.

- **`capabilities()["surfaces"]["docx-write"]["absences"]` — a new key**, carrying the docx
  surface's contract-level absences with a verification label and what to do instead. Its
  first row is the one a reorganisation runs into: **there is no move or reorder operation**,
  so every whole-document reorganisation is delete-and-recreate. Every other surface's
  serialization is unchanged; the key is emitted only where there is a row.
- **The shipped guide gains two sections**, both reachable by name from `guide_sections()`:
  *The read-back law — a green apply is not a receipt*, and *Recipe: reorganise a document —
  there is no move, so a reorder is delete-and-recreate* — check the comments first, insert
  before delete, batch under the cap, re-create only the genuinely-moved blocks (longest
  common subsequence), and read the final order back.
- **A recipe for a fragment bigger than one call**: *Recipe: author more than one call's worth
  of blocks — the 50-per-call cap, batched in order*. One `InsertRequest` carries at most
  `MAX_CHILDREN_PER_CALL` (**50**) blocks — docx v1's own `create_children` window — and a
  wider one is refused **at construction, as a `ValueError`, before `dry_run`**. The recipe
  splits the fragment, anchors each batch to the last **top-level** block the previous one
  created (`created_block_ids` comes back in pre-order, so the last id can be a grandchild),
  and proves the final order by reading the document back.

- **The shipped guide gains another section** — *Recipe: attach a file to a document (the 📎
  attachment card)*, also reachable by name from `guide_sections()`. `put_file_in_document` had
  been **named** by the image recipe for two releases while only an image sample shipped; it now
  has its own worked, runnable example that attaches a file and reads back both what bound and
  where it landed, and it cross-links the recipe for the other product — a link inside a
  sentence — so the two are not confused.

- **The shipped guide gains another section** — *Recipe: you re-ingested a document that never
  changed — the revision_id change detector*, reachable by name from `guide_sections()`. The
  library has surfaced a document's `revision_id` since the writer's staleness guard shipped and
  it is the only true change detector here, but there was no worked loop for using it as one:
  the ledger branch, what it costs (one metadata call via `read_document_revision`, versus
  downloading the document to find out), that polling it is **inert**, and the four things it
  does **not** tell you — it is not a content digest, it is comparable only to itself, it says
  nothing about Drive raw files, and it is not a lock. Measured on a disposable: `1` before,
  `2` after one block insert, `2` again on the next read.

- **`walk_folder`, `folder_manifest` and `folder --dump` are in the guide for the first time.**
  All three shipped and worked; none of them was mentioned in the guide, so the manifest that
  already ships was easy to rebuild by hand without knowing it existed. The folder recipe now
  shows the enumeration alone, the `client=` construction idiom, the result shapes
  (`.walk.children` / `.outcomes`) and the JSON-ready manifest, in one runnable block the suite
  executes. **Nothing about any of the three changed.**

### Behavior changes you can observe

- **IF YOU CONCLUDED FROM 1.33.0's FOLDER-READ SKIP REASON THAT DRIVE FILE BYTES WERE
  UNREACHABLE, RE-READ IT — THAT SENTENCE WAS WRONG.**
  Reading a folder skips every raw uploaded `file` child, and the reason it gave was that the
  bytes leg *"(GET /drive/v1/files/:file_token/download) is not shipped"*. **It ships.**
  `DriveFilesWriteClient.download(file_token)` (`larkdocio.drive.files_write`) returns those
  bytes and has since the upload round trip landed, so the old sentence wrongly suggested there
  was no route from a Drive file token to its bytes. **No behaviour changed and no new capability shipped**: the walk still reads
  documents and still fetches no bytes for a `file` child. What changed is that the reason now
  **names the verb**, at the point of the skip, where you read it — verified before the sentence
  was rewritten by a live gate that skips a file through the folder read and then downloads that
  very token, hash-matching it against the upload. If you built a folder ledger around the old
  sentence, the content digest you were told was impossible is one call per file away.

- **What a folder ledger can and cannot key on is now stated, and it is not what the absence of
  a statement implied.** `FolderChild` and `folder --dump` carry, **on every child and free**:
  token, title, type, url, `parent_token`, `owner_id`, `created_time` and `modified_time` — the
  timestamps as **unix epoch SECONDS strings** — plus a `revision` on every child the run
  actually read. They carry **no size, digest, etag, checksum or content hash of any kind**, so
  *"download only what changed"* is buildable on `modified_time` and on `revision`, and content
  identity is not buildable from a manifest at all. Both halves are held by a live gate that
  asserts the **absences** as well as the presences, so this list cannot rot quietly.

- **`larkdocio.__doc__` — the first paragraph a new reader meets — said two things that were
  false.** It described the Base surface as writing rows only, denying that it creates, renames,
  converts or deletes a field, a table or a view, while `capabilities()` reported a
  **fifteen-operation** `base-schema-write` surface doing exactly those verbs; and it called
  `drive/` **Read-only** across four shipped Drive write surfaces. Both are corrected, and the
  front-door guard suite now holds that paragraph against the surfaces `capabilities()` reports
  — derived, so a new write surface widens the check with nobody editing a list. **No behaviour
  changed**; the registry was right and the paragraph was stale.

- **`sec_label_name` — a document's tenant security level — is fetchable, and the guide now says
  how.** The classification section explained the field at length without a single route to read
  one for a **document**, which sent at least one reader looking for a private API. There is no
  private API involved: the field rides `POST /open-apis/drive/v1/metas/batch_query`, a
  documented open-API route **this library already calls** for other purposes. **No shipped
  larkdocio operation returns it** — that is unchanged and is now stated plainly, with the exact
  request body to make yourself, and with the measurement (the key came back present, value
  `""`, on a disposable docx on 2026-08-15).

- **The permanent-media-residue caveat now sits with the cleanup it constrains.** *"Uploaded
  media inside a disposable is permanent residue"* lived in `capabilities()`'s
  `content_constraints` prose, nowhere near where anyone plans a teardown. It is now stated once
  in the disposables doctrine — a destroy is not a clean slate, a media token survives the
  deletion of the thing it was uploaded into, and a file uploaded into a **folder** is the one
  case that can be deleted — and `capabilities()` cites that statement instead of carrying a
  second, divergent copy of it. The `docx-write` `creatable_out_of_band` text moved accordingly;
  **`capabilities()`'s shape is unchanged** and no key was added or removed.

- **THE BASE SURFACE MAP ROUTED YOU TO TWO ATTRIBUTES THAT DO NOT EXIST — IF YOU COPIED
  `.records` OR `.raw()` OUT OF THE GUIDE, YOUR CODE IS BROKEN TODAY AND THIS IS THE
  CORRECTION.** The map's *"what did the wire actually say for this cell?"* row said
  `read_base(url, retain_raw=True)`, then `record.raw(name)`. Both spellings belong to a
  **different object** than the one that read hands you, so the line raises `AttributeError`.
  **Nothing in the library changed** — the names were always these:
  - the **read model**: `read_base(url, retain_raw=True).tables[i]` has **`.rows`** (not
    `.records`), and one row's wire body is the **attribute `.raw_fields`** (there is no
    `.raw()` method on it);
  - the **write engine's snapshot**: `snapshot_table(...)` has **`.records`**, and a
    `SnapshotRecord` has `.raw_fields` **and** the loud accessors `.raw(field_name)` /
    `.raw_as_dict()` that refuse with `RawNotRetained` when the read did not retain raw.

  The fix for copied code is mechanical: on a `read_base` result, `.records` → `.rows` and
  `record.raw(name)` → `row.raw_fields[name]` (an **absent key** is an empty cell, so use
  `.get(name)` if you were relying on the accessor's `default`). And `RawNotRetained` is
  imported from `larkdocio.base.model`, not from `larkdocio.base`, which does not re-export it.
  The page now carries one row per object and a guard resolves every name it prints against the
  real class, in both directions, so this cannot silently re-break.

- **A NEWLY CREATED BASE IS NOT EMPTY, AND `list_tables(app_token)[0]` IS LARK'S TABLE.**
  Measured, not assumed: a `create_base(...)` answers a Base already holding one table named
  `Table` with four columns you did not ask for — `Text`, `Single option`, `Date` and
  **`Attachment`** — and **ten blank rows**. The create's own reply names it
  (`default_table_id`). Nothing about this is new behaviour; it was simply never written down,
  while two recipes taught `list_tables(app_token)[0]` as *"the table I just made"*. **If you
  provision Bases and index `[0]`, you have been addressing Lark's seeded table.** Take a table
  **by name**, or keep the `table_id` your own `create_table` handed back — the tables you
  create are appended after the seeded one.

- **`create_table(fields=[…])` IS THE ONLY ROUTE THAT SETS COLUMN ORDER *AND* THE ONLY ROUTE
  THAT WILL NOT AUTHOR A `Checkbox` OR A `Rating` — AND ADDING ONE LATER FORFEITS ITS
  POSITION.** Both facts shipped, in two sections that never mentioned each other, and the
  consequence was left to be discovered: `create_field` **appends**, and no create-time
  parameter, update-time parameter or move route places or moves a column afterward. The two
  sections now cite each other and both state the forfeit, and the local refusal you meet when
  you try carries it too. **The taught route, measured:** author the orderable prefix with
  `fields=`, then `create_field` the refused kinds **in display order** — append order is
  display order, so they land in the order you call them, after every column the kit carried.

- **Creating a Base record is `draft.add(cells)`. There is no `draft.create`.** The write
  handshake previously showed only how to edit an existing row, and the guess this library's own
  vocabulary invites (`draft.create`) is an `AttributeError` rather than a typed refusal. The
  recipe now creates a row end to end, and the guide corrects the guess where it is made.

- **`AddTab` WITH NO `index` PLACES THE NEW TAB FIRST. THIS IS A DOCUMENTATION CORRECTION, NOT
  A BEHAVIOUR CHANGE — do not go looking for a fix that is not there.** The guide claimed
  through 1.34 that leaving `index` out would append; it never did. The placement is unchanged
  and is not changing, so any code you have written against it keeps working exactly as before.
  Re-measured on a disposable before the sentence was rewritten: a workbook reading
  `[(0,'Sheet1'), (1,'Rollout')]` came back `[(0,'zz-no-index'), (1,'Sheet1'), (2,'Rollout')]`.
  **To append, name the position:** `AddTab(title=…, index=len(write_client.query_tabs(token)))`,
  measured landing last in the same run. If you wrote code that omitted `index` expecting an
  append, your tabs have been going to the front — check the workbooks, not the library.
- **A FLOAT IMAGE DOES NOT WORK OVER A RANGE, and the recipe that said it did is retitled.**
  `put_float_image_in_sheet(a1_range=…)` refuses every multi-cell range — an ordinary 4x10
  `A1:D10` answers `1310202 Wrong Range` — and only a **single-cell anchor** binds. This was
  documented as untried-and-therefore-open; it is now **refuted**, measured twice
  independently. Nothing about the op changed. And the part that costs you something: **the
  upload happens before the bind is validated**, so every refused bind — including this one —
  leaves a **permanent, unpurgeable** Drive media token behind (`exc.orphan_file_token`). If
  you have been retrying a multi-cell bind, every attempt minted bytes nobody can delete.
- **A READ CANNOT TELL YOU A TAB IS HIDDEN.** `SheetTab` carries no `hidden` field, so a hidden
  scratch tab renders into a status report identically to a live one and nothing in the output
  says so. The only way to ask today is `SheetsWriteClient.query_tabs`, which needs **WRITE**
  credentials — so a read-only reporting job cannot answer the question with the credentials it
  has. Nothing changed here either; the gap is now stated on the read route instead of being
  discovered. Making it answerable on the read route is parked.
- **INSERTING A COLUMN MOVES A DROPDOWN RULE, AND NO PLAN DIAGNOSTIC WARNS YOU.** larkdocio can
  write a list rule and can neither read one back nor delete one, so a rule relocated by
  `InsertColsAt` is invisible to it. Keep your own record of which ranges you ruled and
  re-issue after a structural write. Disclosed, not fixed — the missing `preview_note` is
  engine work and was deliberately not minted.
- **`read_spreadsheet_markdown(url)` is the one call that reads a whole workbook**, and it is
  now named where you would look for it: the guide's *read a sheet to Markdown* recipe and the
  CLI's own refusal for `larkdocio download <sheets url>`. It was reachable only from the
  ghost-tabs recipe, so both of those doors used to hand you a four-step loop **with no skip
  handling** — which loses the rest of a workbook to one refused tab.

- **WHERE a picture or a file lands is now documented, and the arguments are not new — only
  their documentation is.** `put_image_in_document` and `put_file_in_document` have always
  taken `parent_block_id` and `index`; neither appeared in any shipped text, so the only way to
  find them was `inspect.signature` and the only way to learn what they do was to write to a
  live document. Nothing about either op changed in this release. What they do, **measured on a
  disposable rather than inferred**: `parent_block_id` names the block the new block becomes a
  child of and defaults to the document root (a docx root block id **is** the document id);
  `index` is a **zero-based position in that parent's ordered `children`, inserting BEFORE the
  child at that position**, and the default `-1` appends — which is why an unplaced picture
  always turned up at the bottom. An `index` past the end, and parents other than the root and
  a list item, are **unmeasured, not refuted**.
- **These two ops are the only docx writes that position with a bare integer, and that is now
  said out loud.** Every other write says *where* with `Anchor` / `AnchorById` through the plan
  gate; these two are out of band and accept neither, so passing an anchor is a `TypeError`
  rather than a refusal. The asymmetry is disclosed, not changed. The `block_id` you get back
  is what `AnchorById` wants for whatever you write next.
- **KNOW WHICH OF THE TWO BLOCKS YOU WERE HANDED WHEN YOU ATTACH A FILE.** A file create brings
  **two** blocks into existence: a type-33 view wrapper and, inside it, the real type-23 file
  block. That fact previously lived only in the installed source. It has consequences you act
  on: the id `put_file_in_document` returns is the **file block** (the id a patch, delete or
  `AnchorById` must address — the wrapper refuses a patch), while the block that occupies the
  position you asked for is the **wrapper**, one level above it. Both are reported
  (`block_id` and `wrapper_block_id`); neither is silently preferred.

- **THE READ-BACK LAW, and it changes what your code should do: after an apply, re-read the
  document and assert what landed — a green apply is not a receipt.** The log says what was
  *accepted*; only a re-read says what the document *contains*. It is a documented rule, not a
  step the library takes for you: larkdocio does not silently re-download after a write. Every
  write recipe in the guide now either performs the read-back or points at the law, and every
  one of them models reading the apply log on **both** sides — what landed and what was refused,
  with the refusal's reason and detail per entry.
- **The `revision=0` disclosure was wrong by omission and is now measured on both parameters
  that carry the name.** On the historical READ (`get_docx_content(document_revision_id=0)`) a
  bad pin is refused locally, before a call is spent, in Lark's own words. On the write plan
  (`dry_run(..., document_revision_id=0)`) it is **not** refused: the plan comes back with
  `revision_guard == "unavailable"` and the whole-document guard is off. Read
  `plan.revision_guard` after every `dry_run`; `"active"` is the only value that means armed.
- **RE-CHECK THE MEMBER LIST OF ANY DOCUMENT YOU CREATED INTO A FOLDER.** Previous releases
  stated without condition that a document this library creates is *"a document only the app
  can use"* whose member read answers `items: []`. That is true **only** of a document created
  with **no** `folder_token`. A document created **into a folder inherits that folder's
  access** — measured 2026-08-15 on disposables created and deleted in the same run — and the
  inherited rows come back marked **`perm_type='container'`**. If you relied on the old
  sentence, list the members of the documents you filed into folders and see who is on them;
  nothing about your documents changed in this release, but what the guide told you about them
  was wrong. (You cannot ask the folder instead: the members route refuses `type=folder`,
  measured.) `create_document(title=…, folder_token=…)` — the argument that decides which case
  you are in — is now documented in the guide's write handshake and in `writer_brief()`.
- **The 50-blocks-per-call cap is now on the page** rather than only in the exception. Nothing
  about the cap changed; what changed is that the number, its origin, the constant's name and
  its unusual failure shape (a `ValueError` at construction, before `dry_run`) are stated where
  you author, with a batching recipe beside them.
- **Every `guide(section=…)` address that appears in shipped text is now checked to resolve.**
  Three of them did not, including the first runnable line of the wheel's own front page, so a
  copy-paste answered with `ValueError` naming a section the guide does not have. The addresses
  are corrected, and a new guard resolves **every** citation in the shipped corpus — the front
  page, the guide, the writer brief, both release documents, the rendered `--help` pages and the
  shipped docstrings, in all three spellings (`guide("…")`, `guide(section="…")` and
  `larkdocio guide --section …`) — through `guide()` itself, so a wrong address cannot ship
  again. Placeholders such as `guide("<slug>")` and the deliberate demonstrations of a refusal
  are excluded by name, each with its reason recorded beside it.
- **No shipped code path changed behaviour in this release.** The recipes moved, the
  disclosures moved, the engines did not. **One public NAME moved with the disclosures:** the
  module-level constant `larkdocio.drive.access.EMPTY_MEMBER_LIST` is now
  `MEMBER_LIST_AT_BIRTH` (renamed with its reason preserved when the birth-ACL truth it
  described gained its folder-inheritance half). An import of the old name raises
  `ImportError` — update the import; the value's meaning and every behaviour behind it are
  unchanged.

### Upgrade & compatibility

- **No dependency moved** — nothing added, nothing dropped, no pin changed. The new diff recipe
  uses `difflib` from the standard library.
- **One name moved, nothing else renamed or removed.** The module-level constant
  `larkdocio.drive.access.EMPTY_MEMBER_LIST` is now `MEMBER_LIST_AT_BIRTH` (see "Behavior
  changes" above) — an import of the old name raises `ImportError`; update the import, nothing
  behavioral moved with it. Every other consumer upgrades without touching a call. If you
  consume `capabilities()` by exact serialization, note the one new `absences` key on
  `docx-write`.
- **Two guide-section ADDRESSES moved with their retitles** (no stability guarantee is
  published for slugs, but the breaks are disclosed rather than silent): the grant-access
  recipe (its heading asserted a claim this release corrects) and the float-image recipe (its
  heading asserted the refuted over-a-range claim). A stored old slug now refuses with the
  full section list; re-ask `guide()` — the no-argument index — or `guide_sections()` for the
  current names.

### Known limitations

- **A reorganisation still costs block ids.** There is no move operation, so a moved block is
  re-created and its old id — with any deep link and any comment anchored to it — is gone. The
  recipe minimises the loss (only genuinely-moved blocks are re-created) but cannot remove it.
- **Whether Lark's API exposes a move route anywhere is unmeasured, not refuted.** Nothing was
  probed for one; the absence recorded is about what larkdocio ships.
- **A created version cannot be deleted through this library.** The diff recipe now says so
  **above** its example rather than below it, because `create_version` leaves permanent residue
  on whatever document you point it at.

## [1.34.0] — 2026-08-15

### New capabilities

- **Grant a human access to a spreadsheet or a Base — not just a docx.** Every access verb
  (`grant_access`, `update_access`, `revoke_access`, `list_members`, `set_copy_permissions`)
  now takes `obj_type=`: say `"sheet"`/`"sheets"` or `"bitable"`/`"base"` (both vocabularies
  work), or hand the verb the object's **URL** and the type and token resolve in one parse. A
  bare token still means `docx` — a **declared** default, not a guess — so every existing call
  is untouched. What used to happen on a Base was a bare `Code: 1063001, Msg: Invalid
  parameter` at every permission level (the 1.33.0 field exercise, scenario B3, both tiers, graded
  Blocker); a folder, file or wiki token now refuses **typed, before any call is spent**, and
  a display name instead of an email or id gets a refusal that names
  `contacts.resolve_user(name=…)`. The old docx-only scope was a recorded decision; it is
  superseded with its reason preserved (`OBJECT_TYPES_MEASURED`), and the shipped claims reach
  exactly as far as what was measured live: the member family, proven per-type on a disposable
  spreadsheet and a disposable Base.

- **Edit an id-anchored projection BY BLOCK — `block_markdown()` and
  `replace_block_markdown()`.** `larkdocio.model.projection` now hands you the two calls that
  make an edited projection safe to splice: `block_markdown(projection, block_id)` returns the
  whole Markdown a block occupies, and `replace_block_markdown(projection, block_id, markdown)`
  returns the whole document with that block's Markdown replaced. Both take identity from the
  identifiers the projection emitted — an id it did not emit raises rather than matching
  something that looks close — and both leave the marker line, the block's indentation and the
  blank line to the next block exactly as they were. **Why you want them:** a marker introduces
  a block, it does not promise the block is one line, so "find the line that starts with X and
  replace that line" can rewrite half a block (see the next section). These replace that idiom,
  and the shipped update recipes now use them.

- **A snapshot now carries the API domain, so the file-first recipe really does resume from
  the two files alone.** `snapshot(blocks, document_token=..., document_revision_id=...,
  api_domain=domain)` writes the domain the read was taken against **inside** the checksummed
  payload, and `load()` hands it back as `Snapshot.api_domain` — so a later process (or
  another machine, or another person) builds its `Client` / `WriteClient` from the artefact
  instead of needing the original URL back. It is a routing fact, **not a credential**: no app
  id, secret or access token is ever written into a snapshot. **Old artefacts still load.**
  The artefact format version did not change, so a snapshot written by 1.33.0 or earlier loads
  unchanged and reports `api_domain` as `None` — absence stays absence, never a default,
  because `larksuite.com` and `feishu.cn` are two different tenants; take a fresh snapshot if
  you want the domain in the file. A 1.33.0 reader also still loads a snapshot this release
  writes. The shipped file-first recipe was corrected in the same release: its resumable half
  takes the domain off the snapshot, and its block search no longer raises `StopIteration`
  when you paste it against a document that does not contain the sample's sentence.

- **Declare a Base's time zone when you create it — `create_base(name, time_zone="Asia/Tokyo")`.**
  A Lark Base date is stored as an **instant** (milliseconds since the epoch), not a calendar
  date, so which calendar day it is depends entirely on a time zone. Lark accepts the zone in
  exactly one place, the Base's create, and reports it on every later read; a Base created
  without it reports **no zone at all**, and then any reader — this library included — has to
  assume one. The parameter is on `create_base(...)` and on
  `BaseSchemaClient.create_app(...)`, is sent only when you pass it, and appears in the plan's
  own description so you can see the declaration before anything is sent. **Pass it.** It is the
  difference between a date that round-trips and a date somebody has to reason about.

- **A Base read now tells you which zone its dates were rendered in, and whether that zone was
  assumed.** `read_base(...)` returns three new fields on the result: `date_zone` (the zone the
  dates above were rendered in), `date_zone_assumed` (`True` when the Base declared none and the
  library had to choose) and `date_zone_disclosure` (a plain-language sentence to show a person,
  or `None` when nothing was assumed). They are derived from the Base's own `time_zone`, so they
  cannot disagree with it, and **nothing changed in the rendered Markdown** — the disclosure is
  provenance on the result, not a marker in the output.

- **A Base you create, you can now delete — `BaseSchemaClient.delete_base(app_token)`.** Until
  this release a Base was the one object this library could bring into existence and could never
  remove, which made the `try`/`finally` disposables recipe it teaches **unfollowable** on that
  surface: every Base you made for a test or a demo stayed in your tenant for good. All three
  write surfaces now carry the same create/destroy pair, and the runnable Base version — create →
  use → `finally`-delete → confirm gone — is at the end of the guide's Base structural-handshake
  recipe. **It removes the whole Base**, not a table in it: removing one table is still
  `delete_table` through the plan gate, which enumerates the loss across the whole Base and needs
  consent minted from that plan. `delete_base` takes **no consent token** and that is deliberate,
  not a gap — a whole Base's loss is every table, column, record and view it holds, and nothing
  reads that at plan time, so it rides the same whole-object gate `delete_document` and
  `delete_spreadsheet` ride.
  **Read three things before you call it.** (1) **It is a trash, not an erasure.** A human can
  restore the Base from Lark's own trash; no open-API verb purges anything here, and attachment or
  image tokens you uploaded into the Base survive it with no purge verb at all. (2) **The delete's
  own `code: 0` means *accepted*, and the proof has to come from the bitable side** — after a
  landed delete the Drive metadata route *still resolves* the token with its title and timestamps,
  so it cannot tell you the Base is gone. Ask for the Base again and the error you get back is the
  confirmation; `base_is_gone(exc)` is the one predicate to use, because the delete of an
  already-trashed Base and a read of a trashed `app_token` report the same fact with two different
  codes and it spans both. A code-less error is `False` — that is a failure below Lark, where
  whether the Base is gone is unknown. (3) **A brand-new Base is not always addressable as a Drive
  file yet**: not-found-shaped codes have been observed for over twenty minutes before the
  identical delete landed. Nothing is retried inside the call, so if you provision Bases in a
  loop, keep every token and re-attempt the ones that did not land.
  **One refusal now points somewhere real, too.** `delete_table` on a Base's **last** table still
  answers `1254034` — Lark keeps every Base on a floor of one table — but its advice used to name
  deleting the Base and then say this library did not offer it. It now names `delete_base`, says
  what that costs, and says it trashes rather than erases.

- **Create a folder — `create_folder(name, parent_token)`.** You could read a folder tree and
  upload a file into a folder; you could not make a folder, so "publish these and organise them
  into subfolders" was impossible rather than merely undocumented. `DriveFoldersWriteClient`
  (WRITE pair) now creates one folder under a parent you name and hands back the new folder's
  token and Lark's own url for it — pass that token straight to `put_file_in_folder` as the
  parent. **The one thing to plan around: creating the same name twice makes a SECOND folder.**
  Measured, not guessed — the second create answers success with a distinct token and the parent
  then lists two folders whose names are identical, with no de-duplication and no warning. The
  library does not pre-check, because a look-then-create is a race it cannot win: if you need one
  folder per name, list the parent yourself. The parent is always yours to name (omitting it is
  refused by Lark; an empty string would land the folder in the app's own root, so the library
  refuses that itself), an empty name is refused for the same reason Lark's acceptance of one is
  the problem, and a parent that is a file rather than a folder comes back as a typed refusal
  naming what to check. **Everything else about organising a Drive is still not shipped** — no
  move, rename, copy, shortcut, bulk "organise by type" or folder delete — and the guide's new
  recipe says so where you meet the verb.

- **Check whether a name is already in a folder before you upload — `find_children_by_name`.**
  `larkdocio.drive.client.DriveClient.find_children_by_name(folder_token, name)` lists the folder
  and hands back every child already carrying that **byte-identical** name, each with its token,
  so you can decide skip-or-replace before writing. It exists because of the sentence below, and
  it takes no action of its own: nothing uploads, deletes, renames or de-duplicates on your
  behalf. Two fences ride on the answer and both are measured. It is a **check, not a lock** —
  another writer can add the same name between your look and your upload, and nothing refuses
  them. And it compares **names only**: neither the folder listing nor the metadata query reports
  a size or a digest, so identical-name never means identical bytes — download the token and hash
  it if that is the question. A listing that hits the page budget comes back with
  `complete = False`, which means *unknown*, never *not there*.

- **A table of up to 500 cells now authors, and it costs tens of calls instead of hundreds.**
  Authoring a table used to write **two throttled calls per non-empty cell** — a read to find
  the cell's inner text block, then a patch on it — which is why a 6×36 grid's 216 cells took
  **463 write API calls and 158 seconds**. Both halves are now batched: the inner block ids
  come from one paginated document block list, and the texts go out through
  `PATCH …/blocks/batch_update` in runs of 48. An authored table costs
  `1 create + (R−9)+(C−9) grow + one block-list read per 500 blocks + ⌈cells/48⌉ batch` —
  the same 6×36 grid measured **37 calls in 12.4 seconds**. Nothing about what lands in a
  cell changed — same body, same row-major order, an empty cell still costs no write. Two new
  client routes ride the endpoint family the write surface already uses
  (`WriteClient.batch_update_blocks`, `WriteClient.list_document_blocks`): **no new scope is
  requested, widened or escalated**. What a table costs is now written down, in the guide's
  § "What authoring a table costs, and where the 500-cell cap comes from".

### Behavior changes you can observe

- **BREAKING — `larkdocio.guide()` with no argument now returns the guide's SECTION INDEX, not
  the whole document. Pass `full=True` for the document.** The guide is over half a megabyte as
  one string, and that had a two-sided cost: the default answer was too large to read,
  while the quickest way to the section you need — the index of ~95 headings, each named after
  the FAILURE its section cures — was easy to miss. The two have swapped roles.
  **What you now get with no argument:** a ~14 KB text index — every heading, indented by level
  so a `##` name visibly contains the `###` names under it, each row spelled as the call that
  fetches it — with a header that names your next call, the whole-document call, and both
  command-line spellings. **The document is unchanged**: `guide(full=True)` returns the same
  bytes the wheel carries, byte for byte, exactly as `guide()` did through 1.33.0.
  **Migration, one line:** replace `guide()` with `guide(full=True)` anywhere you parsed or
  searched the whole document — or, better, replace it with `guide(section=...)` for the one
  section you were searching for, which is what the index is for. `guide(section=...)` itself is
  **unchanged** (same slug and heading matching, same case-insensitivity, same nesting rule, same
  `ValueError` naming every section there is), and `guide_sections()` still returns the same rows
  as data. Asking for a section and `full=True` in one call is two mutually exclusive requests
  and raises `ValueError`.
  **On the command line the same swap:** `larkdocio guide` prints the index, `larkdocio guide
  --section <name>` prints one section (unchanged), and the new `larkdocio guide --full` prints
  the whole document — so a script doing `larkdocio guide > guide.md` becomes `larkdocio guide
  --full > guide.md`. `--full` and `--section` cannot be combined.


- **UPLOADING THE SAME NAME TWICE HAS ALWAYS MADE A SECOND FILE, AND NOW THE LIBRARY SAYS SO —
  if any automation of yours has re-run an upload, it has been duplicating files in Drive.**
  Nothing about the upload changed in this release; what changed is that the behaviour is now
  disclosed where you meet it. Sending the same name and the same bytes into the same folder
  answers `code:0` with a **distinct file token**, and the folder then lists two children whose
  names are byte-identical — no collision report, no de-duplication, no warning. There is **no
  overwrite**, and that was measured rather than assumed: five spellings of an extra `upload_all`
  form field (`overwrite`, `duplicate_handling`, `conflict_strategy`, `mode`, `upsert`), an
  `?overwrite=true` query string and an `overwrite` key on `upload_prepare` were **all accepted
  and all ignored**, each minting another new token. **How to audit what you already have:** run
  `find_children_by_name` (above) over the folders your automation writes into — more than one
  token for a name is one object per run. This library will **not** overwrite for you: a
  delete-then-upload done on your behalf would destroy a file as a convenience, so if you want
  replace, take the tokens and call `DriveFilesWriteClient.delete` yourself.

- **`delete` no longer appends "The file is still there" — if you match on that string, this
  breaks you.** Deleting a token that was already deleted is refused by Lark with *"file has been
  delete."*, and the library used to answer that with the opposite claim. Now: a refusal carrying
  that code reports the file as **already deleted**, and `larkdocio.drive.files_write.
  file_is_gone(exc)` is the predicate to test it with — the Drive mirror of the sheets surface's
  `spreadsheet_is_gone`, so a `finally` can forgive exactly that outcome. Every other refusal says
  **nothing was reported as removed** and makes no claim about the object either way. Read the
  code, not the sentence: the message text is disclosure, `file_is_gone` is the contract. One
  honest edge comes with it, because half of it would be a new wrong sentence: *already deleted*
  means the object **left its folder listing**, and the metadata route was measured **still
  resolving** a trashed file token. It is trash, not purge.

- **THIS RELEASE REFUSES A SELECT-COLUMN WRITE THAT USED TO SUCCEED — and it does so because that
  write was destroying your cells in silence.** If you edit a `SingleSelect` / `MultiSelect`
  column's `options` through `update_field`, two things change for you: the dry run now needs
  **`read_client=`**, and a body that **drops** an option some record still holds now needs
  **`consent=consent_to_destroy(plan)`**. Without either, the entry refuses and **nothing is
  sent**.
  **Why, plainly.** `PUT …/fields/{f}` *replaces* the whole option set and matches on each
  option's `id`, so omitting an option deletes it — and **every cell that held it is emptied**.
  Measured on a throwaway Base: a `SingleSelect` shrink emptied the **2 of 3** records holding
  the dropped option; on a `MultiSelect` the dropped value was stripped from each cell it was in
  (`[B, C]` → `[B]`) and the cell that held it alone was **emptied**. Until now that write
  reported `loss_preview: None`, asked for no consent, and returned outcome `'applied'` — while
  the very same library refuses to delete a *column* (the same blast radius: a column of values)
  without a read client, an enumerated preview and a consent token. One of those two doctrines
  was wrong, and it was not the strict one.
  **What you get instead of the silence.** The plan entry's `loss_preview` names **every record**
  that will lose a value, what its cell keeps, and whether the cell empties — before anything is
  sent — and the refusal names the safe ordering: **remap the records off the option first, then
  shrink**, at which point nothing is destroyed at all.
  **What did NOT get more expensive.** A shrink that destroys nothing — dropping an option no
  record holds — still applies with **no consent token**; its preview comes back explicitly
  **empty and measured** (`destroys: false`), never `None`, so you can tell "measured harmless"
  from "not checked". A **rename** of an option (every `id` kept) destroys nothing and is measured
  as such. And a non-select `update_field` — a column rename, a currency format, a date format —
  is completely untouched: zero extra reads, no preview, no token.
  **What to change in your code.** Pass `read_client=` to `schema_dry_run` when the body carries
  a select `options` array (you are almost certainly holding that client already — the apply
  requires one). If you meant to drop a populated option, read the preview and pass the consent
  token, exactly as you already do for a column delete. One route is deliberately *not* fenced:
  `BaseSchemaClient.update_field` called directly, outside a plan, is a plain single API call —
  like `delete_field` beside it — so plan your option edits.
  **If you shrank a select column with an earlier release, cells were lost.** There is no API
  undo, and this is not a delete-to-trash: the value simply reads empty. Whether the Base's own
  record history retains it was not measured, so it is neither promised nor refuted here — check
  the columns you edited.

- **Date-only values in a Base can be one calendar day off — and this release is where that
  stops being silent. Check existing data.** A Base date is stored as an instant, and the
  library used to turn that instant into a calendar date by quietly assuming **UTC** whenever
  the Base reported no zone of its own — which was **every** Base this library created, because
  its create never declared one. Measured against a real tenant, that assumption was simply
  wrong: the server's own day for such a Base rolled over at **16:00 UTC** (i.e. UTC+8), so a
  value written as local midnight read back **one calendar day early**, every time, with nothing
  said. **If you wrote or read date-only values before this release, they may be off by one day
  — check any Base date you rely on.** How to check: read the Base and compare a few dates you
  know; if `date_zone_assumed` is `True` on the result, the dates you are looking at were
  rendered in an assumed zone and a value authored as midnight in a zone ahead of UTC will show
  the previous day. How to fix it going forward: create Bases with `time_zone=` (above), and for
  an existing zone-less Base read the values raw (the stored millisecond integers are exact and
  were never corrupted) and interpret them in the zone you meant. Nothing about the **write**
  path changed: a date cell still takes a millisecond integer and still refuses a date object,
  because converting one needs a zone the encoder cannot know — and the integer you sent is the
  integer Lark stored, verbatim, which is why the data is recoverable at all.

- **An edited projection no longer writes stray backslashes into code lines you did not
  touch.** The id-anchored projection you edit renders with literal text **escaped** (`--`
  reads as `\-\-`), and everything written back is decoded again — except, until now, inside a
  **fenced code block**, where a backslash is a backslash to Markdown itself. So editing one
  line of a multi-line code block wrote **every other line back escaped**: a runbook nobody
  edited ended up carrying `deploy rollback \-\-service $SERVICE`. Nothing announced it — the
  plan preview showed the block's current text against the escaped replacement, which reads
  like a diff you asked for. Code blocks now round-trip byte-identically like every other
  block kind. **If you wrote through `reconcile()` before this release, documents may carry
  stray backslashes in untouched lines of multi-line code blocks.** To find them: re-read the
  document and print `repr()` of a code block's text, or diff a fresh read against a copy from
  before the edit — a `\` in front of punctuation (`\-`, `\.`, `\*`) that you never typed is
  the fingerprint. To fix one: edit that block's line in a fresh projection and apply as
  usual.
- **A body that cannot be decoded refuses instead of being written.** If a code block's text
  in the edited Markdown carries a backslash the projection's escaping could never have
  produced, the batch refuses `undecodable-text` naming the position — nothing is guessed and
  nothing is written. In practice you reach this only by hand-building the Markdown rather
  than editing the projection you were handed.
- **Several inserts into the same parent, in one document batch, now land where you asked.**
  If a batch contained two or more `InsertRequest`s that resolved to the **same parent block**,
  every insert after the first landed **one position early per earlier insert above it** — and
  nothing told you: the plan carried no refusals, `apply()` reported `inserted` for every entry
  with real `created_block_ids`, and only re-downloading the document showed it. In the measured
  three-insert case the second marker landed *before* its own anchor and the third landed two
  positions early, in the wrong section. Two related shapes went with it: two `APPEND_INTO`
  inserts into one parent came out in **reverse** authored order, and a delete earlier in the
  same batch pushed a later same-parent insert one position **late**. All four now land beside
  their own reference, in the order you authored them, whatever order the requests were
  submitted in. **This is a change only for a caller who was depending on the misplacement.**
  Applying one insert per batch was always correct and is **unchanged**, position for position.
- **You can drop the workarounds.** One insert per batch with a fresh read between, and
  submitting same-parent inserts in **descending** index order, were the two shapes that
  happened to work. Neither is needed any more, and neither was ever documented — the guide now
  says both what is safe and what used to be needed.
- **A resolved insert's `insertion_point.index` is documented as ADVISORY.** It tells you the
  ordinal the reference occupied **when you planned**; the plan's commitment is the *position
  beside that reference*, which is what `apply()` guarantees. In a batch with several inserts
  into one parent the first landing write moves every later ordinal, so that integer cannot also
  predict the final slot — it is disclosed rather than left to be discovered. No field was
  added, removed or renamed, and `position` / `parent_block_id` are unchanged.
- **The limitation this is NOT.** *One tree, one batch* still holds exactly as before: every
  request in a batch is resolved against a single consistent snapshot, so a batch still cannot
  anchor on content its own earlier entry creates. That contract is about **which** block an
  anchor means; this fix is about **where beside it** the new block goes.
- **A `not-found` anchor quote may now say "differs only in whitespace" instead.** An anchor
  quote is matched **byte-verbatim against the block's raw stored text**, and stored text can
  carry a *soft return* — a literal newline inside one paragraph — which rendered Markdown shows
  as an ordinary line wrap. So a whole sentence copied off a wrapped paragraph differed from
  what was stored by one invisible character, and all the refusal said was `not-found`, with the
  remedy *"re-read the document and copy the quote verbatim"* — the exact action you had just
  taken. Nothing about matching has changed: it is still verbatim, still exactly-one-or-refuse,
  and whitespace is **never** normalized to force a match. What changed is the refusal's
  `detail`. When a whitespace-normalized comparison would have matched exactly one block it now
  reads `block '<id>' differs only in whitespace`, quotes the block's actual stored spelling
  (so the invisible newline is visible) and offers a fragment of your own quote that does match;
  when it would have matched several it says *ambiguous after whitespace normalization* and
  names every candidate id; when it matches none the old diagnosis stands with a remedy that is
  a different action. The same clause is appended to a sub-span edit's `span`-absent refusal.
  **If you match on `detail` text, a refusal you used to recognize may now carry more of it** —
  the reason code is unchanged (`not-found`), and the diagnosis is still the detail's prefix.
- **The copy-this update recipe no longer garbles a sentence with a clean plan.** The recipe
  spliced the projection **by line**: find the line starting with your text, replace that line.
  A paragraph carrying a soft return occupies two projected lines with a marker only above the
  first, so that idiom rewrote *part* of a block and left the rest — and `reconcile()` cannot
  see it, because by contract whatever you hand back is authored intent. The measured outcome
  was `plan.ok: True` over a sentence whose ending had been written twice. The recipes now
  splice with `replace_block_markdown()`, which replaces the block's whole segment however many
  lines it spans. **If you wrote your own line-based splice over a projection, it carries this
  bug**: switch it to `replace_block_markdown()`, and check any paragraph you edited whose text
  contains a newline (`repr()` the block's text) for a duplicated fragment.
- **Every anchor-quote example is now a short fragment.** The guide, the writer brief, the
  `Anchor` docstring and the README taught `quote="Revenue grew 12.4% in Q3."` — a whole
  sentence, which is exactly the shape a soft return breaks. They now teach
  `quote="Revenue grew 12.4%"`, and state in one sentence that the match is against raw stored
  text which may carry wraps the Markdown does not show.
- **`capabilities()` now lists every operation a surface has — not just its dispatched ones.**
  Each surface gained `operation_index`: one row per call site (`name`, `kind`, and the `key`
  its full row is under), so `capabilities()["surfaces"][<id>]["operation_index"]` is the
  complete answer to "what can this surface do". It matters because `operations` was only a
  subset — 20 API-using operations were reachable only under `legs` or `lifecycle`, and a
  caller reading the documented key concluded the library could not do things it does.
  **The 20 now discoverable** (worth re-reading if you concluded any of them was missing):
  `base-write` `download_attachment_media`, `permalink_attachment_media`,
  `upload_attachment_media`; `docx-write` `create_document`, `delete_document`,
  `put_file_in_document`, `put_image_in_document`; `drive-access-write`
  `resolve_grantee_email`; `drive-files-write` `delete`; `sheets-read` `create_export_task`,
  `download_export`, `export_xlsx`, `poll_export_task`, `read_workbook`; `sheets-write`
  `create_spreadsheet`, `delete_spreadsheet`, `dry_run`, `put_float_image_in_sheet`,
  `put_image_in_sheet`, `remove_float_image_from_sheet`. Nothing was added to the library —
  these are calls it already shipped; only their discoverability changed. The index is derived
  from the same fields the permission registry is built from, so a future operation joins both
  at once.

- **The refusal-reason vocabulary is now EXPORTED — and if you copied the retry guard out of
  the guide before this release, IT NEVER FIRED.** `entry.refusal.reason` on the sheets and
  Base engines is a plain string carrying the **wire value** (`stale-sheet`, `stale-base`,
  `precondition-mismatch`, …), but the shipped guide wrote the SCREAMING_SNAKE spelling
  fourteen times and the wire spelling zero times. So **a retry guard written against
  `== "STALE_SHEET"` never fired**: the compare-and-swap refused correctly, the guard skipped
  it, and the write was dropped in silence on the one path where silence hurts most. **Go grep
  your own code for that comparison now.** The mechanism was always right and is unchanged; no
  wire value moved. What is new is that the vocabulary is importable —
  `from larkdocio.sheets import RefusalReason, REFUSAL_REASONS` and the same pair from
  `larkdocio.base` — so a guard reads `entry.refusal.reason == RefusalReason.STALE_SHEET` and
  nobody has to type either spelling. The guide now teaches exactly that, and every mention of
  a reason in the shipped text is the wire value. The docx engine is unaffected: its
  `RefusalReason` is an **enum** that was already exported, and its member name is what you
  compare against there.
- **A preflight result that came back empty before this release meant "unmeasured", not
  "fine". If you gate a deploy on `check_permissions()`, re-read your check.** For an
  operation whose requirement nobody has ever observed — `put_file_in_folder` and
  `grant_access` among them — the advisory check returned `verdicts=() blind_spots=()
  unknown_operations=() ok=True`: an answer shaped exactly like *you hold everything these
  need*, for the operations it knew the least about. **50 of the 108 operations that called
  Lark at that measurement answered that way** (the inventory stands at 111 as of this
  release). Nothing distinguished *needs nothing* from *nobody has ever measured
  what this needs*. Now every operation you ask about comes back in one of four states, carried
  on `result.requirements`: `known`, `unmeasured` (it calls Lark and no scope string has ever
  been seen demanded — reported as a blind spot naming the operation, with the recorded reasons
  attached), `no-api-call` (it reaches Lark not at all, so it truly needs nothing — an
  emptiness that was measured), and `unrecognised` (a name this library does not have,
  unchanged). **Read `result.ok` together with `result.blind_spots`** — that pairing is now
  said on the class, in the guide's recipe, and in `ok`'s own documentation. Nothing was probed
  that was not probed before: this makes the **absence** honest, it does not close it.

- **Behavior change: passing a SURFACE id to `check_permissions()` now raises.**
  `check_permissions(['docx-read'])` — `'docx-read'`, `'sheets-write'` and the rest of the
  vocabulary `capabilities()` and the guide hand you — used to check nothing and return an
  empty, clean-looking result. It now raises `LarkConfigError` naming that surface's
  operations and the two spellings that work (the bare operation name, or
  `surface.operation`). If you pass a surface id today you get an exception where you used to
  get a misleading `ok=True`; pass the operations instead. An unknown *string* is unchanged —
  still reported in `unknown_operations`, never raised.

- **The preflight answer is JSON, provably.** `PermissionCheck`, `ScopeVerdict` and the new
  `OperationRequirement` each document `to_dict()` on the class, so
  `json.dumps(result.to_dict())` round-trips the whole answer including `blind_spots` and
  `requirements`. The library's *JSON-serializable* claim is now true of both of its
  self-description surfaces, not one.
- **BREAKING — `apply()` now RAISES when any entry refuses, unless you opt into partial
  application.** Every plan-gated apply this library ships — the document engine
  (`larkdocio.write.apply`), the spreadsheet engine (`larkdocio.sheets`), the Base record
  engine (`larkdocio.base.apply`) and the Base schema engine
  (`larkdocio.base.schema_apply.schema_apply`) — raises the new
  `larkdocio.errors.LarkApplyRefusedError` when the finished apply-log holds one or more
  entries that did **not** land. Code that called `apply()` and ignored the log now raises
  where it used to return. **Nothing about the writes changed**: the same entries apply and the
  same entries refuse, in the same order, issuing the same calls; only return-vs-raise moved,
  and nothing is rolled back — whatever applied is still applied.
  **The one-line migration: pass `allow_partial=True`** — the same spelling on all four
  surfaces — and `apply()` returns exactly what it returned before, refusals and all. Or catch
  the error: it carries `err.log` (the whole apply-log), `err.applied` (the entries that
  landed), `err.refused` (the entries that did not) and `err.refusals` (one
  `{"reason", "detail"}` per refused entry, in log order), and its message names the counts
  both ways — *"3 of 5 entries applied; 2 refused"* — plus how to opt in. It subclasses
  `LarkDocIOError`, so an existing `except LarkDocIOError` already catches it.
  **Why:** a caller who did not read the log got silent partial application — some entries
  landed, some did not, and the process exited 0 — so a run could look complete while the log
  held typed refusals naming every candidate.
- **Every `ApplyLog` is now iterable and answers `len()`.** `for entry in log:` and `len(log)`
  work on all three apply-log classes (document, spreadsheet, Base); the document log also
  gained the `applied` / `refusals` accessors its siblings already had. `for entry in log:`
  used to raise `TypeError` on the document log, after a live write had already landed.

- **A structural insert now tells you which index convention its own parameter uses — the
  printed convention was wrong, the behavior was not.** `InsertColsAt(before_col=N)` and
  `InsertRowsAt(before_row=N)` have always been **1-based against displayed position**
  (`before_col=3` inserts to the left of the column you see as `C`), and that has not changed:
  the request, the wire payload and the parameter's meaning are byte-identical to 1.33.0. What
  was wrong was the plan's own text. Beside `semantic: 'insert 1 column(s) before column 3'`
  sat `convention: '0-index-half-open'` — which describes the span larkdocio put **on the
  wire**, not your parameter — and that was the only basis the printed diagnostics offered for
  the number. Read that way, the insert lands **one column early**, with `code: 0` and no
  warning. The plan now names both bases: the entry carries `position` and
  `position_convention: '1-index-displayed'`, and the `semantic` line reads `insert 1 column(s)
  before column 3 (before_col is 1-based against displayed column position; wire span [2, 3) is
  0-index-half-open)`. **If you followed the printed convention before this release, a write may
  have landed one row or column early — check any structural insert you made.** A delete is
  unaffected: `first` / `last` are 1-indexed inclusive and go on the wire unchanged, so its two
  numbers were always the same number.

### Upgrade & compatibility

**No dependency moved** — nothing was added, removed or re-pinned. But this is **not a drop-in
release**: it carries **three breaking changes** and one return-type exception, each with a
one-line migration, enumerated in full right here. Everything else keeps its name, signature
and return type. An insert now costs **one extra read** per entry (the live parent lookup that
decides the index); it calls no new endpoint and needs **no new permission scope**. If a
reference block cannot be read, or has stopped being a child of the parent it was planned
against, that entry refuses `stale-anchor` with **no write issued** — the same typed staleness
path the rest of the write engine already uses — rather than writing at a guessed position.

**Break 1 — `apply()` raises on a refused entry.** See the bullet under "Behavior changes you
can observe". If your code reads the apply-log already, pass `allow_partial=True` to keep the
old return; if it does not, the raise is the point — read `err.log` and act on `err.refusals`.
There is no flag file, no environment variable and no deprecation window: the argument is the
whole migration, and it is spelled identically on the document, spreadsheet, Base record and
Base schema engines.

**Break 2 — `guide()` with no argument now returns the section INDEX, not the whole document.**
The full ~600 KB document moved behind `guide(full=True)` (CLI: `larkdocio guide --full`),
byte-identical to the old default. If you parsed the no-argument answer, add `full=True` and
you are done; every section fetch (`guide("<slug>")`, `guide_sections()`) is unchanged. See
"Changed" for why the index won the door.

**Break 3 — a select-column write that used to succeed now refuses, because it was destroying
cells in silence.** Editing a `SingleSelect`/`MultiSelect` column's `options` through
`update_field` now needs `read_client=` at dry-run, and a body that drops an option some record
still holds now needs `consent=consent_to_destroy(plan)`. Without either, the entry refuses
and nothing is sent. An option edit that only adds or renames needs nothing new. The full
story is under "Behavior changes you can observe".

**The return-type exception:** `larkdocio.permissions.coverage_gaps()` — the permission-drift
audit — **changed its return type**. It was a 2-tuple `(uncovered, orphans)`; it is now a
4-field `CoverageGaps` NamedTuple adding `unprojected` and `phantom`, the
projection-vs-registry direction that could not see the gap fixed in this release. If you
unpack it as a pair, read the fields by name instead (`gaps.uncovered`). This is a dev-time
audit helper — no operation, endpoint or scope moved with it, and nothing on the read or write
paths calls it.

### Known limitations

- The plan's `insertion_point.index` remains a **plan-time** ordinal (see above). Read the
  *position + reference* pair as the promise.
- Resolution is still snapshot-frozen per batch: commit the insert, then anchor follow-ups by
  the ids `apply()` handed back.
- **A soft return is still shown as an ordinary line wrap.** The projection's bytes did not
  change: a paragraph carrying a newline still renders as two Markdown lines under one marker.
  Use `block_markdown()` to see how many lines a block really occupies, and
  `replace_block_markdown()` to edit it.
- **The whitespace near-miss is a diagnostic, not a matcher.** It is reported only when a
  normalized comparison actually matches, and only for a quote of two or more words — a lone
  token normalizes to something a long document contains by accident, so claiming a near-miss
  for it would be true and useless. Nothing is ever resolved off the normalized comparison.

- **`larkdocio.write.MAX_TABLE_CELLS` moved 200 → 500: a table between 201 and 500 cells that
  was refused before will now be authored.** Know this before you hit it — it is a real
  behaviour change, in the permissive direction. The old 200 was **larkdocio's own** number, a
  cost budget for the per-cell fill described above, and that fill no longer exists; the new
  500 is anchored on a **measured** platform envelope (Lark accepts a table subtree of 499
  cells / 1000 descendants in one call and refuses the next), so it keeps an authored grid
  inside one platform-sized unit of work. If your code relied on a >200-cell table being
  refused, it will now be written. **The refusal for a bigger table tells the truth now:** both
  routes — the `ValueError` from `NewBlock.table(...)` and `compose()`'s `table-cap` refusal —
  name the 500-cell cap **and that it is larkdocio's, not Lark's**, the measured envelope
  behind it, **Lark's own ceilings that are not this one** (100 columns, `1770010 "too many
  table column"`; no row cap has ever been observed), and a size to split into instead of a
  bare "split into batches". It still fires **at construction, before `dry_run`, with zero API
  calls** — nothing is half-written. Measured on one tenant with `tenant_access_token`, docx
  v1, block type 31, on documents the probes created; `user_access_token`, other tenants and
  wiki-wrapped documents are **unmeasured, not refuted**.

## [1.33.0] — 2026-08-13

### New capabilities

- **Send another user a link to a file in a Base — `media.permalink(file_token)`.** An
  Attachment cell hands you a `file_token` and two API routes; what you usually want is the
  address a *person* can open. `larkdocio.base.media.BaseMediaClient.permalink` asks Lark for
  it and returns `MediaPermalink(file_token, url, title)` — the file's own
  `https://<host>/file/<token>` address and its title — for an attachment uploaded as either a
  file or an image. It is a read: it uploads nothing and leaves no residue. **A `code:0` from
  that query is not a permalink** — Lark answers *success with an empty answer* for a token it
  cannot resolve, putting the reason in `failed_list`, and this op refuses with
  `MediaPermalinkNotResolvedError` naming your token and Lark's own reason rather than
  reporting a success it did not get. It never builds a URL out of a host and a token: if the
  answer carries no `url`, you get a refusal, not a guess.

- **A LARGE file goes into a folder now, and the same call does it.** `put_file_in_folder`
  still takes bytes, a name and **your** folder token and still hands back the file paired with
  the permalink it read back — but above `larkdocio.drive.files_write.SINGLE_SHOT_MAX_BYTES` it
  sends the bytes in **blocks** (`upload_prepare` → `upload_part` per block → `upload_finish`)
  instead of in one shot. There is **no second upload verb to choose between**, and the only
  new thing on the answer is `linked.parts`: how many blocks the bytes actually went in, `1`
  for a single shot. **The block size is LARK's and is asked for on every upload** — the
  library partitions by the `block_size` / `block_num` `upload_prepare` declares and compiles
  no size constant of its own, because a partition constant is right on one tenant on one day
  and a silent bug afterwards. `SINGLE_SHOT_MAX_BYTES` is a **library policy** that decides
  only *whether* to chunk; it is **not** a limit anyone observed Lark enforcing, and you can
  move it per call with a `chunk_above_bytes` argument. The verdict is unchanged: the file is
  downloaded again and compared by sha256 and length through the same shipped check —
  `upload_finish` answering success is an acceptance, not a file.

- **Float a picture OVER a range — the other way a picture reaches a spreadsheet.**
  `larkdocio.sheets.media.put_float_image_in_sheet(client=…, media=…, spreadsheet_token=…,
  sheet_id=…, a1_range=…, data=…, name=…, width=…, height=…)` anchors a picture **over** a
  range, leaving the cells underneath untouched — a **different product** from putting a
  picture *in* a cell, which **is** the cell's value. It is three calls in a fixed order and
  one op does all three, so the order cannot be got wrong: upload → bind → **ask the tab what
  it now has**. `remove_float_image_from_sheet(client=…, spreadsheet_token=…, sheet_id=…,
  float_image_id=…)` takes it away and is verdicted the same way. Four things it makes hard to get wrong, all measured: **`parent_node` is the WORKBOOK**
  (not a cell, not a `sheet_id` — the one place a document-image habit misleads, since there
  the upload binds to the block); **an upload answering success has bound nothing**, so the
  verdict is a fresh `float_images/query` and never a call's own answer; **an error on this
  route is a refusal even when it says "retry later"**, so nothing retries it; and the bind
  **does not police image-vs-file tokens**, which you cannot hit through the op because it
  mints the token it binds. Byte proof is **on by default** here — the picture is downloaded
  again and compared by sha256 and length (`verify_bytes=False` opts out, and then
  `bytes_verified` says `False` rather than claiming something nobody checked). **Not
  plan-gated**: no `dry_run`, `Plan`, `apply` or `stale-sheet`, and `capabilities()` reports
  both ops as **legs**. The recipe is *"Recipe: float a picture OVER a range (the float-image
  write)"*.

- **Put a picture IN a spreadsheet cell — one call, and a verdict you can trust.**
  `larkdocio.sheets.media.put_image_in_sheet(client=…, spreadsheet_token=…, a1_range=…,
  data=…, name=…)` writes bytes as the **value of one cell**, then answers with what the cell
  **now holds**, because it re-reads it: an accepted call is not a stored one, and a cell that
  reads back with no picture raises instead of reporting a success nobody observed. Byte proof
  is **opt-in, and opt-in by construction** — pass a `SheetsMediaClient` and the picture is
  downloaded again and compared by sha256 and length (the same check the document-image and
  Base-attachment legs use); pass none and `bytes_verified` is `False`, which is the honest
  answer rather than a claim. **It is NOT plan-gated**: it needs bytes, which the plan
  compiler cannot carry, so it is a **leg** beside the sheets write engine — no `dry_run`, no
  `Plan`, no `apply`, no `stale-sheet` — and `capabilities()` reports it that way instead of
  letting you assume it inherited them. A **multi-cell or merged-cell target is refused before
  any call**, because only a single cell was ever measured. The recipe is *"Recipe: put a
  picture IN a cell (the in-cell image write)"*.

- **Keep a read, and come back to it tomorrow.** `snapshot(blocks, document_token=…,
  document_revision_id=…, path="doc.larkdocio.json")` writes the read you just paid for — the
  blocks exactly as they arrived, the revision, and the token — into one file, and
  `load("doc.larkdocio.json")` gives it back in another process, another day, with no network.
  The promise that makes it useful: **projecting a loaded snapshot produces the same bytes as
  projecting the original read**, so an agent's edits still line up against a projection taken
  later. If the file has been damaged — a half-written copy, a half-synced cloud folder, a
  hand-edit — you get a typed refusal that tells you what failed and tells you to
  **re-download**; you never get half a document back. The checksum is there for **accidental
  corruption and nothing else**: nothing here is encrypted, and it says nothing about who wrote
  the file. **The snapshot is not editable and there is still no way to hand a changed
  document tree back** — the editable artefact is the **Markdown**, and the route to a write is
  the one you already have: project → edit the Markdown → `reconcile()` → `dry_run()` →
  `apply()`. The revision travels with the file because it is what arms
  `dry_run(..., document_revision_id=…)`: if somebody edits the document while your snapshot is
  on disk, that guard refuses the batch, which is what you want. **A snapshot is not a lock —
  it reserves nothing and blocks nobody.** Documents only; spreadsheets, Bases and folder reads
  are not covered. Import it from `larkdocio.snapshot`; it needs no credentials and makes no
  call.

- **Show a view four of its twelve columns.** `set_view_hidden_fields(app_token, table_id,
  view_id, ["fldA", "fldB"])` hides columns in a view, and `clear_view_hidden_fields(...)` shows
  them all again — both through the ordinary plan gate, both **proved by re-reading the view**
  rather than by a success code. **An empty list is the CLEAR, and it is not the same as leaving
  the argument out**: leave it out and nothing about the hidden set changes; pass `[]` and every
  column comes back. Hiding a column changes what a **person** sees when they open the view, and
  it marks the column on a per-view field read; it does **not** narrow anything you read — every
  value is still there, and this is not a way to withhold data. Grouping and a saved sort are
  still not settable through the API, and still say so. **The one column you cannot hide is the
  table's primary field** — Lark refuses that and says why, and larkdocio hands you its answer.
  Measured on a grid view, on one tenant, with one look at the web client.
- **Point a sentence at a file.** *"For the full details, **open the attached file**"* — where
  *open the attached file* is a link, and the file behind it is one Lark will not draw inside the document
  at all (an `.html`, say). That needed two things this toolkit did not have, and both are here
  now. `put_file_in_folder(files=…, data=…, name=…, folder_token=…)` puts the file in a folder
  **you name** and hands back its own web address; `NewBlock.rich_paragraph` builds the sentence
  out of `TextSpan` pieces, and the piece carrying `link_url` becomes the anchor — text that is
  not the URL. **Three things to know.** The **folder is yours to choose**: it is a required
  argument, nothing here creates a folder, and there is no default destination, because a
  permanent file dropped somewhere you did not pick is a surprise. The address you get back is a
  **permalink** — the file's own, asked for rather than assembled — and it **lets nobody in**:
  whoever clicks it still needs access to the file, which you arrange. And the URL is sent
  **exactly as you give it**; a percent-encoded one is refused, because reading the document
  back would decode it and the round trip would not close.
- **A 📎 attachment in the body — a different thing, said plainly.** `put_file_in_document`
  attaches a file as an attachment block. It is **not** a link inside a sentence, and it is
  worth its own operation for a reason you would otherwise discover the hard way: creating one
  makes **two** blocks and hands you the wrapper, whose child is the real one — patch the
  wrapper and Lark refuses with a message you cannot decode. This does the resolution for you
  and gives you the id that actually works. One caveat, the same as for pictures: those bytes
  are **permanent**. A file you put in a **folder** can be deleted; bytes put **inside a
  document** cannot be, by anything. And Markdown still cannot write a `[text](url)` link — on
  purpose rather than unfinished: the compiler creates unstyled text, and the guarantee that
  what you compose reads back as what you wrote is what that refusal protects. Author the anchor
  as the typed shape above; the refusal now says so instead of leaving you stuck.
- **Which of the two you want may come down to sharing — so here is what was measured.** The
  bytes behind a 📎 card **cannot be shared on their own**: both halves of the sharing recipe
  are refused on a document-bound media token, while **the same two calls on a file you
  uploaded into a folder succeed**. The likely explanation is that the attached bytes ride the
  document's own access — but that is an **inference from two refusals, not something any
  endpoint states**, and it ships labelled that way rather than dressed up as a rule. **If the
  file has to be shareable in its own right, put it in a folder and link to it.** Either way
  larkdocio grants nobody access to a file: that is yours to arrange.

- **Put a picture in a document.** Not a link to one — the image itself, in the body.
  `put_image_in_document(client=…, media=…, document_id=…, data=png_bytes, name="diagram.png")`
  does it in one call and hands back **both** the block id and the file token. Under it are
  three calls that have to happen in one exact order, and the two ways that order bites are why
  this is one operation instead of three: **the block has to exist before the bytes go up** (an
  upload aimed at the document succeeds, hands you a token, and then no block will ever accept
  it — and that token cannot be undone), and **an upload answering "success" has bound
  nothing** (the block's image is still empty until the third call). So the answer this returns
  is a **re-read of the block**, not a status code, and the bytes are then downloaded again and
  checked by digest — if the picture is not really there, you get an error, not a `True`.
  Markdown still cannot express it: a `![](…)` has no bytes attached, so `compose()` refuses it
  and points here instead. **Two things to know before you use it.** An upload leaves
  **permanent** residue — nothing in Lark's API deletes uploaded media, and deleting the
  document does not either, so upload the smallest file that proves your point. And **whether
  the picture actually draws on screen is not something any API call can tell you**: what is
  proven is that the block holds the bytes and hands them back unchanged, and this library will
  not claim more than it measured. Only PNGs have been tried; `width`/`height` are the only
  sizing fields offered. The shipped guide carries a runnable recipe.
- **Give a person access to a document your app created — grant, raise, lower, revoke.** A
  document the app makes starts with **nobody on it**: its member list is empty and the app owns
  it without appearing on that list, so the humans who need it have to be put there. 
  `DriveAccessWriteClient.grant_access(doc_token, email="someone@example.com", perm="full_access")`
  does that, `update_access` moves the level in either direction, `revoke_access` takes it back,
  and `list_members` shows who is on it **plus the owner**, because the owner is not one of the
  rows. `set_copy_permissions` moves the two document settings whose names govern copying, one
  key per call. **Every one of them tells you what it FOUND, not what the call returned** — this
  endpoint family was observed accepting a write and not storing it, so each op re-reads and
  reports `stored=False` when the two disagree. The grantee is an **email or an `open_id`**; a
  bare name is refused before anything is sent, with a message that asks for an email — and an
  address that does not resolve means *this lookup did not resolve it*, never *there is no such
  person*. **docx only.** There is no ownership transfer (measured: it is one-way, and the app
  loses its ability to delete the document afterwards), no group or department grantee
  (unmeasured — one call, with a made-up id), and **nothing here claims your copy/paste will
  work**: no Lark endpoint reports what a clipboard does, so this reports what was stored and
  says the rest is a hypothesis. The shipped guide carries a runnable recipe.
- **Named versions on a Drive file — list them, and create one that records what it named.**
  `list_versions(file_token, obj_type="docx")` returns every named version of a document or
  spreadsheet, **paged to exhaustion for you** and sorted **newest first** by this library (the
  server's own order was observed descending on a single listing, which is enough to use and
  not enough to rely on). A file that has never been versioned answers an **empty list**, never
  a denial in disguise. `create_version(file_token, name)` adds one and — the reason it exists —
  returns the new version token **paired with the document's head revision, read immediately
  before the create**. Creating a version is measured **revision-inert**, so that
  `(name, token, revision)` triple is exact unless someone edited the document concurrently.
  Where the revision cannot be read (the read failed, or the file is not a docx) the field is
  **absent with its reason**, never zero and never invented. Reach them as
  `larkdocio.drive.DriveClient.list_versions` and
  `larkdocio.drive.DriveVersionsWriteClient.create_version`; the shipped guide carries a runnable
  recipe.

- **Read a document AT A PAST REVISION.** `get_docx_content(token, document_revision_id=<n>)`
  returns the document as it was at revision `n`, so change detection stops being
  "re-download head and diff against the copy on disk" and becomes **diff the revision you
  ingested against head**. Paired with the version-create above, an ingestion ledger can pin a
  **semantic** version (`V1.3`) and still resolve it to bytes later, because the revision was
  recorded at the moment the version was named. **Omitting the parameter changes nothing**: the
  same two calls, the same bytes, byte-identical output for every existing caller. A pinned read
  returns a small `HistoricalDocumentMeta` in place of the usual document metadata — it carries
  `document_id` and the `document_revision_id` you asked for, and **deliberately no
  `revision_id` and no `title`** (see the limitations below for why). The shipped guide carries
  a runnable recipe under *"diff a named edition against head"*.

- **A link to a named edition — minted offline, and shipped CLICK-VERIFIED (web client, one
  tenant).**
  `docx_edition_url(doc_url, version_token)` — importable from `larkdocio.common`, beside
  `docx_block_url` — builds `https://<tenant-host>/docx/<doc_token>?edition_id=<version_token>`
  from the document's own URL and a version token, with **zero API calls** and no credential.
  The tenant host is an input, never invented; a hostless, non-`https`, non-`/docx/` or
  wiki-wrapped URL is refused rather than defaulted, and a query or fragment already on the URL
  you pass is **dropped** (this helper adds a query of its own). **Read the disclosure before
  you put one of these in a ledger — it is the reason the helper is safe to ship:**

  > A docx named-edition link (`…/docx/<doc>?edition_id=<version token>`) is mintable offline — `docx_edition_url(doc_url, version_token)` builds one from the document's own URL and a version token, and makes zero API calls — and it ships click-verified — the `?edition_id=` grammar was clicked on 2026-08-11 in the Lark WEB client, on one tenant, and it opened the named version. Here is the edge of the evidence, so the claim is never read wider than what was measured. The click was made against a harness-created two-paragraph document whose two states were proven to differ AT THE API LEVEL first — a read pinned at the version's recorded revision returned the first paragraph only, while a head read taken in the same sitting returned both — so a browser showing one state could not be an accident of the fixture. What was seen: through the edition URL the document showed STATE ONE only, and Lark's own UI labelled that view an older version; through the control URL (the plain document URL, unmodified) it showed both paragraphs, head. MEASURED: the QUERY half, by that click; and the PATH half, `https://<tenant host>/docx/<doc token>`, which is the document's URL as Lark itself reports it (the drive metas/batch_query verb asked `with_url: true`, 2026-08-11), and it is character-for-character the grammar `docx_block_url` already mints; the version token is Lark's own, returned by the versions family. UNMEASURED, and therefore neither refuted nor supported: the mobile client, the desktop app client, wiki-wrapped documents (`…/wiki/<node>`, which this function refuses rather than guess at), any other tenant, and any non-web client. Whether such a link opens the named version is a rendering behavior of the Lark client, so no API call can widen this measurement — only another click can. Separately, and unchanged by the click: no API route resolves an edition token to CONTENT — the versions family answers no url of any kind, and an edition token resolves to nothing — so keep recording the (name, token, revision) triple at creation time, because that pairing is what a pinned historical read actually runs on.

  The disclosure above is the **click-verified** one: the link was clicked on 2026-08-11, after
  which the constant that authors it was renamed
  `larkdocio.common.DOCX_EDITION_LINK_CLICK_UNVERIFIED` →
  **`DOCX_EDITION_LINK_CLICK_MEASUREMENT`**, so the symbol's name no longer states a verdict its
  body contradicts. **No released version ever exported the old name** — both it and the rename
  land inside this same, un-cut section — so there is nothing to migrate.

- **`writer_brief()`, `release_notes()` and `changelog()` gain `section=...`, the same seam
  `guide(section=...)` already had.** Each has its own `<accessor>_sections()` index
  (`writer_brief_sections()`, `release_notes_sections()`, `changelog_sections()`), and
  `capabilities()["docs"][...]["sections"]` now carries every one of them, not only the
  guide's. The writer brief is indexed at the same `##`/`###` levels as the guide; the release
  notes and the changelog are indexed at `##` (one release) only, because both repeat the same
  `###` subsection titles under every release and indexing those too would collide on every
  call. **Omitting `section` changes nothing**: all four accessors still return the whole
  document, byte for byte, exactly as before.

- **A Base VIEW can now filter a Checkbox column — and the shape is captured, not reported.**
  The one value form Lark accepts on the view route is a JSON string carrying a list of
  booleans — `"[true]"` / `"[false]"` — named by Lark's own refusal body and proven end to end
  through the shipped path. A Python `bool` in a view-route condition now reaches the wire as
  that JSON boolean; previously the serializer quoted every value, producing `'["True"]'` —
  one of the spellings Lark refuses — so this filter worked nowhere before and works now. The
  search route is untouched: its own measured shape was always the boolean. The guide's
  filter-shape table now carries **route-scoped evidence**: each row says separately what its
  search half and its view half were observed on, and an unprobed half reads `unmeasured`
  instead of borrowing the other half's label.

- **One call reads a whole spreadsheet from its URL.**
  `larkdocio.sheets.read_spreadsheet(url)` — the sheets twin of `read_base`, with
  `read_spreadsheet_markdown(url)` beside it — accepts the URL (or a bare token, by the same
  rule `read_base` follows), builds the read client from your environment, walks every tab
  with the skip-loudly posture, and returns the structured read or the rendered Markdown. The
  hand-built `SheetsReadClient` + token form remains, one level down, unchanged.

- **`TabOutcome.reason`** — the skip reason without the reach-through: `reason` is the skip's
  reason when the tab was skipped and `None` when it read. `outcome.skip.reason` still works.

- **`capabilities()` now indexes COMPOUND WORKFLOWS — the task you arrived with, not just the
  wire operations.** A new top-level `workflows` section answers *how do I update a document
  that already has content*, which `operations` could never answer: reconciliation compiles
  down to edit / insert / delete and mints no request family of its own, so it was correctly
  absent from that list and correspondingly hard to find. The row names the module
  (`larkdocio.write.reconcile`), the request families it compiles to, the plan gate they all
  still pass through, and the guide sections that teach it — plus a `detail` path to the full
  reconciliation record, which it points at rather than restating. The `docx-write` surface
  carries a stub under its own `workflows` key, so printing the surface finds it too. **The
  row states its own evidence class in the payload**: descriptive and guide-pointer-shaped,
  **not** endpoint-derived — and it states, in the same breath, that the operations lists keep
  their projection guarantee undiminished. Nothing was added to any operations list.

### Behavior changes you can observe

- **The scope list now names an endpoint it had been leaving out.** The permissions matrix —
  `larkdocio.guide()`'s permissions section, and its maintainer-side projection in the dev
  repo — gained a row for the Drive **file delete** — `DELETE
  /open-apis/drive/v1/files/:file_token`, the call `larkdocio.drive.files_write`'s `delete`
  makes. The verb itself is not new; it has shipped and been exercised since the folder-upload
  slice landed. What was missing was its **declaration**, and therefore its row: a call site the
  capability registry never named was invisible to the completeness check, because both
  directions of that check started from the same declaration. A fourth check now reads the code
  itself and reports any endpoint a public callable can reach that no row carries, so *"is there
  a call this library makes that nobody wrote down?"* is answered by the code rather than by a
  list. **No scope string was invented** — the requirement for this endpoint family was already
  recorded, and recorded as *unknown*, which it remains. **Nothing this library does changed**:
  no new call, no widened permission, no new verb.

- **The *"a media token cannot be shared on its own"* disclosure now covers Base, not just
  documents.** If you upload a file into a Base attachment cell, the token you get back cannot be
  permission-granted to another user or link-shared on its own — the same two refusals already
  documented for a document-bound token were measured on a Base-bound one too, and the text said
  only *docx*. Three things were measured alongside it, and they are worth planning around:
  the permission family **reads** such a token quite happily and refuses only to **change** its
  sharing, so a successful read tells you nothing about whether a grant will work; **deleting
  the parent Base makes the bytes unfetchable while the token, its metadata and its permalink
  keep resolving**, so a link you handed somebody can survive the file it points at (whether a
  restore brings the bytes back is **unmeasured**); and the obvious work-around — take the
  shareable drive-uploaded file token and put *that* in the attachment cell — is **refused by
  name**. So the route steer is now stated with both halves: a folder upload is how you get a
  file you can share, and it is **not** a way to fill an attachment column.
- **A picture in a spreadsheet cell stops rendering as an empty cell.** Read a sheet whose cell
  holds a picture and you used to get a **blank cell** — no marker, no note, nothing to tell you
  content had been dropped. That cell now renders as `![](<fileToken>)`, the **same** Markdown
  form a document image reads as, so whatever already handles document images handles these
  unchanged; a caption becomes the alt text, and a value that somehow carries no token gets the
  same visible `[Image: missing token]` marker a document image would. **This changes the bytes
  a read returns** for any workbook containing an in-cell picture, which is why it is here: if
  you diff today's output against output you stored earlier, a cell that was blank may now carry
  an image reference. The **bytes are not downloaded** by the read — you get the token and fetch
  them yourself from the drive media download route, which returns them byte-identical — and the
  read reaches **no new endpoint and needs no new scope**. The picture's pixel width and height
  are not carried into Markdown, which has no portable way to say them. A read of a workbook
  with no in-cell picture is **byte-identical** to before.
- **And a second kind of picture is now stated to be invisible, rather than left implied.** A
  picture **anchored over a range** — floating, rather than living in a cell — is not a cell
  value at all, so a values read cannot see it **in any form, under any option**, and this
  library ships no call that asks for one. No output changed for this; what changed is that the
  shipped guide and the sheets capability matrix now say it out loud, so *"the sheet reads
  clean"* stops being mistakable for *"the sheet has no pictures"*. Measured on one tenant, one
  day, with one small PNG, in one workbook; other media kinds, merged and multi-cell ranges, a
  user token, and whether either picture survives the export-fidelity read are **unmeasured, not
  refuted**.

- **The shipped documentation stops telling you a capability does not exist when it does.**
  `larkdocio.writer_brief()` listed image creation under **Non-goals** as *"structurally
  inexpressible"*, and `larkdocio.guide()`'s capability matrix agreed — five releases after
  `larkdocio.write.media.put_image_in_document` shipped. Both are corrected, and the correction
  is **narrowed, not reversed**: creating an image or a file attachment is out of the
  **plan-gated Markdown path** — the reason is unchanged, the compiler holds no bytes and makes
  no network call — and is available **out of band** via `put_image_in_document` (docx block
  type 27) and `put_file_in_document` (type 23). **Boards and embeds really are structurally
  inexpressible** and still say so. The guide's creatable-content floor now shows four states
  rather than two (through-the-path / out-of-band / editable-not-creatable / not at all),
  `mermaid` appears among the creatable kinds with its create-only caveat, and the styled-runs
  row carries the one exception — a link is a *destination* rather than a decoration: a created
  run **may** carry a LINK anchor (`TextSpan(link_url=…)` inside `NewBlock.rich_paragraph`), and
  nothing else.
- **If you round-trip a link this library MINTED back through `parse_deep_link`, the refusal is
  by design and the guide now says so.** `docx_block_url` mints `…#<block_id>` and
  `docx_edition_url` mints `…?edition_id=…`; neither is one of the four **UI-observed** grammars
  the parser recognises, so both answer `NotADeepLink` — measured — and the chapter's *"no
  fragment or query"* exclusion never covered them.
- **Reach another user by EMAIL, not by name.** The guide's front-of-book routing row sent
  *"@mention Ada"* to `resolve_user(name=…)`, whose directory search was measured — **on one
  tenant, on one day** — to return at most the account owner. The row and the recipe now lead
  with `resolve_colleague(email=…)`. Another tenant's contacts data range may reach further;
  that is unmeasured, not refuted. **No code changed** — only what the documentation tells you
  to reach for first.
- **The Base cell-shape table's Phone and Barcode rows showed another type's value.** Several
  field types share one encoder, and the generated table gave each pair the encoder's single
  example — so the Phone row read *write* `"row"` → *read back* `"+12025550100"`, which is a
  round trip of nothing. Each pair now carries its own example, so the two columns describe the
  same value. **No encoder, no accepted input and no refusal changed.**
- **Smaller corrections in the same sweep:** the guide's opening definition now names every
  surface family the library ships (it named three of sixteen); the *"exactly four call sites"*
  Markdown enumeration is five and includes `render_folder`; the write-recipe chooser routes
  *"put a picture or a file in the body"* and *"link to something from inside a sentence"*; the
  mintable-deep-links heading counts all three helpers its body documents; four `§ "…"`
  citations that pointed at bold prose rather than headings — and so could not be fetched with
  `guide(section=…)` — now name their containing heading; and the install chapter says the
  vendor drop is three files while the **wheel carries four** (the fourth is
  `larkdocio.writer_brief()`).

- **The front door now says what the library does — including the parts that are not
  plan-gated.** The README, the `larkdocio --help` group text, the CLI schema document and
  `help(larkdocio.drive)` described drive as read-only, the WRITE credentials as belonging to
  the writer and Sheets alone, writing as always plan-gated, and the Base as reachable by no
  flag. All four were stale rather than wrong-at-the-time, and all four are corrected against
  `larkdocio.capabilities()`. **What this changes for you is what you can trust:** ask
  `capabilities()` which surfaces need `LARK_WRITE_APP_*` rather than reading a sentence, and
  read each surface's own `safety_contracts` before assuming a dry run exists — the Drive
  named-version, access and file-upload legs have none, and prove themselves by an independent
  read-back instead. `download --deep-read-bases` and `folder --deep-read-bases` are real and
  documented as such. No behavior, symbol, flag or scope changed; only the description did.

- **A Markdown table taller than nine rows now authors, instead of failing at the API.**
  `compose()` accepted it, `dry_run()` planned it, and Lark then refused it with
  `1770001 invalid param` — after earlier batches had already been written, which left a
  half-written document. The cause was never the height of the table: the create call's
  auto-provisioned grid form validates **nine per axis**, so the engine now creates the grid at
  nine and appends the remaining rows and columns before filling the cells. Nothing about how
  you author changes; a table within nine by nine sends exactly the bytes it always did. There
  is **no row cap** — a 200-row table was written and read back.

- **A table wider than 100 columns is now refused before anything is sent.** That number is
  Lark's, not ours (it answers `1770010 "too many table column"` at the 101st column), and the
  refusal names the cap, the table and the fix — split it into two narrower tables. It is
  exported as `larkdocio.write.MAX_TABLE_COLUMNS` beside `MAX_TABLE_CELLS`, and it has **no row
  equivalent**, because the row axis is not limited this way.

- **When Lark refuses a write mid-batch, the error now says which block was being written.**
  You get `[while writing block index 7 (kind: table) of 203 in the composed content]` appended
  to Lark's own message — a range and a kind tally when the failing call carried a whole batch,
  because the API refuses a batch rather than a block and this library will not guess which
  member it objected to. Lark's code and text come through unedited, and **your content never
  appears in the error** (index and kind only — an error string ends up in logs).

- **`capabilities()` reports THREE new surfaces, all on the Drive family, all write mode and
  all on the WRITE credential pair** — enumerate them from the registry rather than from this
  paragraph, which is how this list was built:
  - **`drive-files-write`** (one operation, `put_file_in_folder`) — a file object into a
    folder you name, single-shot or chunked, verdicted by the hash-verified read-back.
  - **`drive-access-write`** (five operations: `grant_access`, `update_access`,
    `revoke_access`, `list_members`, `set_copy_permissions`) — who can open a document the app
    created, and the two copy-related document settings.
  - **`drive-versions-write`** (one operation, `create_version`) — one named version on a
    Drive file, returned paired with the head revision read immediately before it.

  `drive-read` gains `list_versions` and remains read-only end
  to end — every one of its operations still declares `mutates=False` and it still makes no call
  on the write pair. The wheel `Summary`, the keywords and the CLI group help name **all three**
  new surfaces; **no CLI flag or subcommand changed**, and the command line is still read-only.
  Sixteen surfaces are reported in total, where the previous release reported thirteen.

- **THREE new safety contracts are declared, and two of them are the first of their kind.**
  `capabilities()["safety_contracts"]` now carries nineteen entries where the previous release
  carried sixteen. The new ones, each declared by the surfaces that actually honour it:
  - **`read-back-is-the-verdict`** — declared by `drive-access-write`. It says out loud what
    every un-plan-gated write leg here does instead of a dry run: a `code 0` is an
    **acceptance**, so the operation re-reads its own work and reports what it **found**,
    including reporting `stored=False` when the two disagree. This family produced a measured
    swallow — a write accepted with a complete echo and absent from the independent read —
    which is why the contract exists rather than being assumed.
  - **`snapshot-integrity-refusal`** — declared by `docx-read`. A damaged snapshot file is a
    typed refusal naming what failed and telling you to re-download; you never get half a
    document back. It is an **accidental-corruption** check and says nothing about who wrote
    the file.
  - **`historical-read-rides-the-measured-route`** — declared by `docx-read`, and described
    above: which route a pinned historical read is allowed to trust, and the two that accept
    the pin and discard it.

  **Read a surface's own `safety_contracts` before assuming a dry run exists**: the three new
  Drive write surfaces carry no plan gate, and `drive-files-write` and `drive-versions-write`
  declare no contract at all — they prove themselves by an independent read-back, which is
  documented in each surface's own note rather than promised by a shared word.

- **A revision pin Lark itself refuses is now refused locally, before a call is spent**:
  `document_revision_id=0` (Lark answers `1770001 invalid param`), any negative number and
  anything that is not an `int` (`99992402 field validation failed`). `-1` is Lark's own head
  sentinel on the wire and is **not** accepted as a second spelling of head — pass `None`, or
  omit the parameter. The refusal is the toolkit's own typed error and names the spelling that
  works.
- **The machine-readable registry gains its first READ-side safety contract** —
  `capabilities()["safety_contracts"]["historical-read-rides-the-measured-route"]`, declared by
  the `docx-read` surface. It states which route a
  historical read is allowed to trust and names the two routes that accept the pin and discard
  it, so all three traps below are met in one place rather than discovered one at a time.

- **The sheets walk result types refuse wrong construction AT construction.**
  `SpreadsheetRead`, `TabOutcome` and `TabSkip` are keyword-only and validate their fields, so
  building one by hand from the wrong arguments fails at the call site instead of three calls
  later as an `AttributeError`. Only construction that was already wrong behaves differently;
  every object the library itself returns is unchanged.

- **The whole-workbook walk recipe is now findable by what burned you.** It has its own guide
  heading naming the failure it cures — *"Recipe: ghost tabs — read a whole workbook, skipping
  tabs Lark refuses"* — so a `guide_sections()` search for "ghost" or "workbook" hits. It
  previously lived unnamed inside the sheet-to-Markdown recipe, which remains.

- **The view recipe's heading now names the failure it cures too.** *"Recipe: create,
  configure and delete a view"* is now *"Recipe: create, configure and delete a view — and
  why grouping, saved sort and hidden fields are NOT among them"*, so a `guide_sections()`
  search for "group", "sort" or "hidden" hits the classification that was already there — a
  view's grouping is accepted and not stored, hidden fields are contradicted by their own
  probes, and a saved sort has no established route. Nothing about that classification
  changed, only its name; a caller pinning the old heading text breaks and should re-pin the
  new one (the slug moved the same way).

- **The refusal you get for a segment array in a Text cell now says the server refuses it too.**
  The message still opens with the words it always did — a segment array is the read shape, pass
  the string itself — and now carries the measurement behind it (what was sent, what came back,
  and which routes were never asked). Nothing else about the refusal moved: the same input is
  refused at the same moment, before any call is spent, with the same exception type. Phone and
  Barcode cells share that encoder and their message is **unchanged**, because nobody measured
  them.

- **A view-route Checkbox filter that Lark refuses is now refused LOCALLY, before the call is
  spent.** Resolving a view filter whose Checkbox condition uses `isNot`, `contains`, `isEmpty`
  or `isNotEmpty` now raises the library's own filter refusal instead of costing an API call
  that comes back `1254001` — those four were measured refused on a Checkbox while a Text
  control on the same view took them, and the message quotes the code and says which operator
  *was* seen working (`is`). **This is a new refusal on a path that previously reached the
  API**: if you were relying on the round trip to tell you, you now get the answer without it,
  with the same exception type the other filter refusals use. `doesNotContain` was never sent
  to a Checkbox, so it is **unmeasured, not refused**, and still goes to Lark. The refusal is
  on the resolver, so a filter you serialize without resolving is unaffected — and the search
  route says nothing about this and is untouched.

  **The exported disclosure beside it was rewritten to stop contradicting that refusal.**
  `VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS` — a public, `__all__`-exported constant you can
  quote and diff — still said the `isNot` limit was *not* worked around locally, which stopped
  being true the moment the local refusal above shipped. Its text now points at
  `VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE` for that operator, while the **other** limit it
  describes — a two-element boolean array accepted and stored as its first element alone —
  keeps its original wording **and its original reason**, because that one really is answered
  by `echoes()` rather than worked around. **If you diff this string across versions it has
  moved**; no operator set, serializer, refusal or call moved with it.
  The shipped filter-shape table's preamble is
  corrected in the same change: the six operators are shared **between the two routes** (proved
  on a Text field), and which operators a given field *type* accepts is claimed only where a row
  says so — it previously read "not type-restricted", which its own Checkbox row contradicted.

- **The guide's write chapter is renamed and re-routed so an update can be FOUND. One section
  name changed, one is gone, two are new — a caller pinning a section name is affected.**
  Following the documented discovery order led to a destructive clear-and-rewrite of a
  document (every block deleted and re-inserted, **no block ids kept**) instead of the one-edit
  reconciliation path this wheel already exports; every fact was in the guide, but none of it
  was reachable by the words a reader searching for an update would use.
  What moved, exactly:
  - **RENAMED** — `### Recipe: round-trip an edit through the block-identity projection`
    is now **`### Recipe: update an existing document — change or edit many blocks at once,
    without re-authoring it`**. Its slug changes with it; `guide_sections()` reports the new
    name, and `guide(section=...)` on the OLD name now raises with the full index, as it does
    for any unknown name. The body — the mechanism, the whole-document-only limitation, the
    refusal vocabulary — is unchanged.
  - **DELETED** — `### A future release may add an editable Markdown projection`. It said a
    capability had not shipped that has shipped since (`project_block_ids()` / `reconcile()`).
    The claim it carried that is still true — *the tree stays the source of truth, and the
    projection is one more optional front-end onto it* — is now stated in the recipe itself,
    where the person who needs it is reading.
  - **NEW** — `### Which write recipe do you need? — add, change, update or delete content in
    a document`, a task-to-recipe decision table at the head of the write chapter; and
    `### Recipe: copy this — the end-to-end update script, from url to applied edit`, the
    preamble every write integration was re-implementing (url → token → wiki hop → read →
    parse → project → edit → reconcile → **dry_run** → apply) shipped once, whole, with the
    plan gate intact.
  - The two entry recipes (empty document, Markdown fragment) and the object-level
    "change a document" recipe now cross-link to the reconciliation recipe. The object-level
    recipe's own comparison is accurate and is unchanged.
  - **Newly stated, because the library ships the join that proves it:** block ids are what
    comments anchor to, so re-creating a block orphans the review conversation left on it —
    `review.for_node(block)` is how you see what is at stake before you decide.
  Across this whole release the guide grew: `guide_sections()` returns **93** rows (93 unique
  slugs) where 1.32.0 returned **81**. Both numbers are measured from the wheel, not counted by
  hand — `len(larkdocio.guide_sections())` answers it on any version you have installed, and a
  caller pinning a section name should re-check it against that index rather than against this
  sentence.

### Upgrade & compatibility

- **No dependency moved** — no add, no drop, no pin change, runtime or dev.
- **This release reaches TEN endpoints it had never called, and every one of them is listed
  here.** All ten were derived by comparing the endpoints the shipped code can reach against
  the same derivation on the previous release — not from anybody's memory of what was
  built. **Their scope requirement is recorded UNKNOWN rather than guessed**, in the one place
  scope requirements are authored, each carrying its reason: every route answered successfully
  on the credential pair named below, and no denial has ever named a scope on any of them, so
  their rows are **empty and say why**. **If your app is denied, read Lark's own denial body —
  it names what Lark actually wants**, and this library never widens, requests or escalates a
  scope. The families, with the credential pair each is called with:
  - **Putting a file in a folder** — `POST /open-apis/drive/v1/files/upload_all`
    (**WRITE**), and, for a file large enough to be chunked, `POST
    /open-apis/drive/v1/files/upload_prepare`, `.../upload_part` and `.../upload_finish`
    (**WRITE**).
  - **Reading an uploaded file's bytes back** — `GET
    /open-apis/drive/v1/files/:file_token/download` (**WRITE**). This is the hash-verified
    read-back that decides whether an upload actually stored the file; it is not an
    independent download surface, and no command exposes it.
  - **Named versions on a Drive file** — `/open-apis/drive/v1/files/:file_token/versions`,
    **GET on the READ pair** (listing) and **POST on the WRITE pair** (creating). This is the
    one family here whose create carries a **known** scope requirement rather than an unknown
    one; the listing half's row is empty with its reason. Neither half falls back to the other
    pair.
  - **Giving a person access to a document** — `/open-apis/drive/v1/permissions/:file_token/members`
    (**WRITE**) for the member list, and `/open-apis/drive/v2/permissions/:file_token/public`
    (**WRITE**) for the two copy-related document settings.
  - **Deleting a file you uploaded** — `DELETE /open-apis/drive/v1/files/:file_token`
    (**WRITE**). It arrived with the folder upload, and it is the reason a file object is the
    one permanent thing here you can take back (trash, not purge, and no undo was measured).
  - **Floating a picture over a spreadsheet range** —
    `/open-apis/sheets/v3/spreadsheets/{token}/sheets/{sheet_id}/float_images` (**WRITE**),
    reached by the float-image write and its removal.
- **One endpoint is now called on a SECOND credential pair.** The metadata query
  `POST /open-apis/drive/v1/metas/batch_query` has always been called on the **READ** pair;
  the folder-upload, access and Base-attachment legs call it on the **WRITE** pair, so it now
  has a row for each. Same endpoint, same answer shape — what is new is which app asks.
- **One long-standing call is newly DECLARED rather than newly made, and the difference
  matters.** `/open-apis/docx/v1/documents/:document_id/blocks` is the route the reader has
  opened since the first release; it appears in the scope matrix now only because the pinned
  historical read made it a call site of its own. It carries the reader's existing scope, and
  **nothing you must grant changed** — what changed is that you can see it written down.
- **The historical read and the in-cell picture read need NO new scope.** The pinned-revision
  read rides the docx documents/blocks family the reader already opens, on the **READ** pair
  and its existing scope; the in-cell picture read reaches no new endpoint at all. Nothing
  moved in what you must grant for either.
- **One deliberate tightening, in the fail-safe direction.** Hand-constructing the sheets walk
  result types positionally (or with wrong-typed fields) now refuses at construction; it
  previously constructed silently and failed later. Objects returned by the library are
  unaffected. And a Python `bool` in a view-route Base filter condition now serializes to the
  accepted JSON-boolean form — a call Lark refused before is a call that works now, never the
  reverse. Everything else: nothing existing moved, and the reader's Markdown is
  byte-identical.

### Known limitations

- **A permalink OUTLIVES the bytes it points at, and nothing in the link says so.** Measured:
  after the parent Base was deleted, the metadata query still returned the permalinks —
  immediately, and again seven minutes later — while the bytes answered **HTTP 404**. So a link
  you hand out today can keep resolving for content that is gone, and this library cannot tell
  from a permalink whether the bytes are still there. **A permalink that resolves is not
  evidence the bytes are there**; only fetching them and comparing digests is, and that answer
  is true only for the moment you took it. Whether **restoring** a trashed parent brings the
  bytes back is **unmeasured, not refuted**.
- **A permalink grants nobody access.** It is the object's own address, not a credential: no
  signature, no expiry, no query parameters, and handing it to somebody who could not already
  open the file gives them nothing. An unauthenticated GET answers **302 to a login page** —
  the route is live and login-gated, which is **not** a proof that a human can open it; what a
  person clicking the link actually sees is **unmeasured**. And the two calls that *would* grant
  somebody something are still **refused** on a Base-bound media token, exactly as on a
  docx-bound one, so a file that must be independently shareable belongs in a folder
  (`put_file_in_folder`), not in an Attachment cell. This library never widens, requests or
  escalates a scope — a grant is a Lark console action.
- **What was measured about the permalink is narrow**: one tenant, one day, a tenant token, one
  disposable Base, two small files, and only the `doc_type: file` spelling (the `bitable` and
  `docx` spellings were tried on the same token and both came back empty). A user token, other
  tenants, regions and domains, and whether a **sheet**-bound media token has a permalink at all
  are **unmeasured, not refuted**.

- **A chunked upload that dies part-way leaves a leftover you cannot see or clean up.** The
  blocks that got through belong to a **pending upload transaction with no Drive object** —
  nothing lists it, nothing deletes it, and **no cancel verb was found in the SDK's drive v1
  surface and none was called: that is unmeasured, not "cannot"**. Its expiry is unmeasured
  too. The raised `DriveFileChunkedUploadError` names the `upload_id`, how many blocks went and
  how many were declared, so the leftover is at least recorded; retrying starts a new upload.
- **Multi-block behaviour is thinner evidence than the single-block path.** A **two-block**
  upload is measured end to end and hash-verified; **a gap in `seq`, a resumed upload, and any
  ordering beyond two in-order blocks are unmeasured, not refuted**. The optional Adler-32
  `checksum` is **not sent** — it was omitted against Lark on three blocks across two uploads
  and all were accepted, so sending it would buy no guarantee this library can point to, and
  the sha256 read-back stays the only definition of a round trip.
- **Converting an uploaded file into a native Lark document is still not shipped**, and neither
  is any folder-organising verb (move, copy, shortcut) or folder creation. The chunked upload
  opens the size ceiling on the one thing this surface already did and nothing else.

- **Floating a picture over a range leaves PERMANENT residue, and removing the picture does not
  take it away.** The upload mints a drive media token, **no open-API verb purges drive
  media**, and neither `remove_float_image_from_sheet` nor trashing the whole workbook removes
  the bytes — the removal takes away the anchor, not the file. If a run uploads and then fails
  to bind, you are told exactly that: a permanent token exists and a picture does not
  (`orphan_file_token` on the raised error). Treat an upload as permanent before you send it.
- **On the float-image route an HTTP 500 saying "Server Error, Retry Later" is a REFUSAL.**
  Binding a token that was never minted answers `1315203` with that message and creates
  nothing — measured, with the re-query that proves no phantom appeared. **Do not retry it**
  and do not classify it as transient: nothing in this library retries it, and a client that
  believes the message will loop against a call that can never succeed. Read the read-back, not
  the message. (The number is Lark's and may be renumbered; nothing here asserts it.)
- **There is no move or resize for a float image.** `float_images` PATCH and the GET-one were
  **never tried** — `unmeasured`, not refuted — so this library ships neither; remove and
  re-create instead.
- **What was measured about the float image is narrow**: one tenant, one day, a tenant token,
  one 88-byte PNG, one workbook, one single-cell anchor. A user token, media kinds other than
  PNG, the chunked-upload family, larger files, multi-cell and merged anchors, concurrent
  writers and the `stale-sheet` interaction, whether the picture survives an xlsx export, and
  whether a sheet-bound media token has a permalink are all **unmeasured, not refuted**.
  Whether a person looking at the spreadsheet *sees* a picture is not something any API call
  can observe.
- **A picture written into a cell costs 3–4× its own size on the wire, and that is a real
  ceiling.** The bytes go up as a JSON array of integers, so one byte becomes up to four
  characters in the request body: budget from the inflated size, not the file's. **The exact
  limit is unmeasured** — an 88-byte PNG is all that was ever sent through it. If the file is
  large, the multipart routes do not pay this: uploading into a folder and linking to it, or
  the float-image route that anchors a picture *over* a range (a different product, and not an
  operation this library ships).
- **Writing a picture into a cell leaves PERMANENT residue you cannot remove.** The call mints
  its **own** media token — you did not upload it and you do not choose it — and **no open-API
  verb purges drive media**: clearing the cell removes the picture from the sheet, and trashing
  the whole workbook does not remove the bytes. Treat a write here as permanent before you send
  it. **The clear itself is an ordinary `""` value write**, not a delete verb; `None` over an
  image was never measured.
- **What was measured about the in-cell image is narrow**: one tenant, one day, a tenant token,
  one 88-byte PNG, one workbook. A user token, media kinds other than PNG, larger files, a
  write into a cell that **already holds a value**, multi-cell and merged-cell ranges, the
  interaction with a concurrent writer, and whether the picture survives an xlsx export are all
  **unmeasured, not refuted**. Whether a person looking at the sheet *sees* a picture is not
  something any API call can observe.
- **There is no delete-version call, deliberately.** The route works — it was measured — and it
  is unshipped because deleting a named version is a destruction with **no restore verb anywhere
  in the family**, and a version's whole value is that a person chose the label.
- **A version token resolves to nothing.** The version object carries no revision id, no url, no
  size, no description and no creator display name, and the token could not be resolved back to
  a revision or to content by any route tried. A name records a moment it cannot reproduce —
  which is why `create_version` hands you the revision at creation time.
- **No quota is disclosed, which is not the same as there being none** (seven versions on one
  document, four back-to-back, no warning and no refusal). **No name-length ceiling is claimed**
  either — 300 characters were accepted whole. The `status` field is `0` on every version ever
  observed and its vocabulary is **unmeasured**.
- **`obj_type` accepts `docx` and `sheet` (measured).** `bitable` and `sheets` are refused
  locally, in Lark's own words, before a call is spent. Any other value is **passed through** for
  Lark to answer: it was never tried, and unmeasured is not the same as refused.

- **An out-of-range revision SILENTLY returns HEAD, and the operation cannot detect it.**
  Measured: a revision 50 past head answered `code 0` with head's body, no error and no marker.
  So a caller who pins a bad number is **silently reading head**. If that matters, bound the
  number yourself — read the head revision first and refuse a pin above it.
- **Two neighbouring routes accept a revision pin and ignore it.** `raw_content` answers head,
  byte-identical to the plain call (this library exposes no raw-content read at all, so the pin
  cannot reach one here); and the document **metadata** route answers head's `revision_id`. That
  second one is why a pinned read hands back no `revision_id`: head's number wearing the pinned
  revision's name would quietly arm a compare-and-swap write against the wrong state. The title
  as of the pinned revision is in the blocks you were returned — it is the page block's text.
- **The edition LINK is click-verified on ONE client and ONE tenant — and nowhere else.**
  `docx_edition_url`'s `?edition_id=` grammar was clicked on 2026-08-11 in the Lark **web**
  client and opened the named version (the control URL showed head; Lark's UI labelled the
  edition view an older version). The **mobile** client, the **desktop app**, wiki-wrapped
  documents and **any other tenant** are **unmeasured** — neither refuted nor supported —
  because this is a rendering behavior of the Lark client that no API call can widen. And
  opening a link is not resolving a token: no API route maps an edition to content, so the
  `(name, token, revision)` triple recorded at creation time is still what a pinned read
  runs on.
- **Reading at a NAMED EDITION is not served, and the search is written out rather than left for
  you to repeat.** No route maps an edition token to content, and none maps an edition to a
  revision: the version object carries no pointer of any kind; four `edition`-shaped query
  spellings on the blocks route answered `code 0` with **head**; the token is not a file token
  to the metadata batch route and not a valid export token; two speculative export fields were
  accepted and ignored; and five speculative history sub-routes answered 404. **Not tried** — a
  user-token session (everything measured was a tenant token, and the web client is a user
  session), non-GET spellings of the unknown paths, the wiki and legacy document families,
  hashing the export artefacts, and retention (how far back the revision pin reaches on an old
  document). So an edition **a person created in the web UI stays unresolvable**; editions your
  own ledger created are resolvable, because you were able to record the revision.
- **A Base record's edit history is not served by the API, measured rather than assumed.** Six
  `bitable`-family route spellings answer the gateway's own non-JSON `404`, the drive versions
  family refuses `obj_type=bitable`, and the drive statistics family answers `code 0` with view
  counters and nothing about history. **Not tried** — a `user_access_token` session, and any
  undocumented product-internal endpoint the web UI itself calls. The nearest thing the API DOES
  serve is `automatic_fields=true`'s `created_by` / `last_modified_by` — who last touched the
  row, not what changed — in epoch **milliseconds**, a different unit from the drive versions
  family's epoch-**second** strings above; and this library does **not** expose it: it pins
  `automatic_fields` **false** by its own PII policy. See `larkdocio.base.history` and the
  shipped guide's "Record edit history" section.
- **On a Checkbox VIEW condition, only `is` was seen working.** `isNot` answers Lark's
  `1254001` even carrying the accepted value form, and a **two-element** boolean array is
  accepted with `code 0` and stored as its **first element alone** — the write-verification
  (`echoes`) correctly reports that as not persisted. Both measured through the shipped path.
- **A Base Text cell cannot be written as a segment array — that is Lark's answer, not this
  library's policy.** The label-that-is-the-link column (visible words clickable, no URL on
  screen) is the shape a Text cell **reads back** as, and Lark's own auto-linkifier puts one
  there — so it was reasonable to think the write was being withheld. It was measured instead:
  **14** segment spellings — one url segment alone, text/url/text, the read-back's own key
  order, url-first, text-only, an empty array and five malformed variants — each answered
  `1254060 TextFieldConvFail` on **both** record-write routes (create one record, update one
  record), in a run whose plain-string control answered `code 0` on both and read back as a
  segment array. So: write the string. **Not tried, and therefore open rather than closed** —
  the batch record routes, cell values seeded at table-creation time, segment arrays longer than
  three members, a url segment carrying extra unrecognized keys, and every field type other than
  Text (Phone and Barcode share the write rule and were deliberately left out of the question).
  The shipped guide's per-type cell-shape section now lists every shape that was sent and every
  one that was not.
- **Grouping COLUMNS in a Base table has no API route — measured, not assumed.** This is
  grouping columns in the table UI, the thing worked around with column-name prefixes; it is
  **not** the row-grouping feature with a similar name, which is classified separately. Every
  shape that could plausibly carry a column group was tried: the table-level write route
  refuses all 7 group-shaped keys tried with "the request body cannot be empty", identical to
  a made-up key; the field-level write route accepts all 8 group-shaped keys tried and stores
  nothing, provably (each attempt also carried a real rename that landed); 5 dedicated
  endpoints all answer "not found"; and a column's own read model carries no group concept at
  all. **Not tried** — a user-scoped credential, any undocumented internal endpoint, the
  dashboard/automation/form families, copying from a template that already has groups, and a
  non-grid view's own vocabulary. This describes one tenant with a tenant-scoped credential —
  not a claim that Lark's product cannot group columns, which its own UI plainly can.
- **Column order is settable once, at table creation — and nowhere else, measured.**
  `create_table`'s own `fields=[…]` array decides the column order (proved with a reversed
  control: two tables, same three names, opposite array order, each read back in that order).
  After creation, no route places or moves a column: 12 create-time and 5 update-time
  position-shaped parameters are all accepted and silently ignored, and 6 dedicated
  move/reorder routes all answer "not found". So: choose the order when you create the table,
  because there is no second chance. **Not tried** — a user-scoped credential, a non-grid
  view's own property vocabulary (plausible territory for a field-order setting), and
  deleting and re-creating columns to force an order (a data-destroying rebuild, deliberately
  not attempted).
- **A view's saved sort and its hidden-fields knob, reclassified against real measurements.**
  The guide previously said a saved sort had "no route was ever established" (nobody had
  looked) and that hidden fields' evidence "contradict[ed] each other" (an unresolved unknown).
  Both are now measured: a saved, view-level sort is **accepted and not stored** — eight
  `property` spellings, every one `code 0` and indistinguishable from an invented key, in the
  same call where a filter really did store; `property.hidden_fields` **is** stored (a second
  write moves it, `[]` clears it, a nonexistent field id is refused) but changes **no read this
  library makes**, so it still ships no parameter. Neither the API nor this library's surface
  changed — only what the guide claims about them, and how confidently.
- **A ghost tab's own listing payload is now measured, and it refutes the one field a caller
  might have guessed at.** The ghost-tabs recipe previously said the payload "could not be
  manufactured on a disposable" and called `resource_type` "a candidate discriminator, untried
  rather than refuted". Both are now false: the payload is captured, from a real workbook, and
  it is **indistinguishable** from a readable tab's — the same six keys, `resource_type:
  "sheet"` on **both**, `hidden: false` on both, and the tab's own single-tab metadata read
  serves the ghost at `code:0`. **Nothing in the metadata discriminates a ghost from a readable
  tab; only a values read does**, which is why this library still skips on the refusal rather
  than on a guess — the shipped behavior was already correct, and this measurement is why, not
  a gap it had to close. One separator was observed (`title == sheet_id`, 21 of 21 ghosts, 0 of
  2 readable tabs) and it **ships as a documented hazard, not a filter**: it is a naming
  accident, not a typed field, and using it would drop a real tab a person titled with its own
  id. Why a ghost tab exists at all is unchanged and still unmeasured. Neither the API nor this
  library's surface changed — only what the guide claims about the payload, and how confidently.

- **A docx can carry a tenant SECURITY LEVEL, and your tenant's policy may stop a human from
  editing until one is set — the API cannot see or move it either way.** `sec_label_name` on the
  metadata read reports the level (empty means none); no route anywhere in the vendored SDK sets
  one, and this library adds none. If another user reports being unable to edit a document your
  app created, this — not a scope grant — is the first thing to ask about.

## [1.32.0] — 2026-08-10

### Disclosures

- **New: `docx_block_url(doc_url, block_id)` — a mintable deep link to a specific block inside a
  docx document.** Pure and offline: it reaches no endpoint; the URL is built from the document's
  own link and a block id every tree read already carries. The anchor grammar is the bare
  `#<block_id>` fragment, **click-verified on the web client for all six common block kinds**
  (headings, paragraph and bullet blocks scroll to the target; table and code blocks move and
  momentarily highlight). What it does NOT claim, stated plainly: mobile and desktop-app clients
  and wiki-wrapped documents are **unmeasured**; the anchor is a web-client behavior, not an API
  contract, and the docstring says so. The product's own "copy link" `#share-<token>` grammar
  remains genuinely unmintable — that half of the older guidance was always right and its
  reasoning is preserved. One trap documented loudly: a **fabricated** `#share-<block_id>` link
  fails with a FALSE "the selected content has been deleted" toast; do not build that form, and do
  not trust that toast as evidence.
- **Mangled deep links now refuse instead of half-parsing.** Previously a URL whose token region
  contained an invalid character could silently truncate at that character and parse as a
  *different, plausible-looking* token. Now the whole token parses or the URL is `NotADeepLink`,
  loudly — across every link grammar (doc, sheet, base, record, folder). Valid links are
  byte-for-byte unaffected; only malformed input behaves differently, and it now fails safe.
- **The CLI refuses locally before spending your credentials.** A URL of the wrong type (for
  example a document URL handed to `folder`) is refused by shape BEFORE any credential resolution
  or network call — previously one token request could fire first. Valid invocations
  authenticate exactly once, as before.
- **DRIVE.md's revision-probe claims updated to shipped truth** (the cheap single-document
  revision route shipped in 1.31; the bulk form remains a measured refusal with its probes
  enumerated).

### Upgrade & compatibility

- **No dependency moved** — no add, no drop, no pin change, runtime or dev. Install requirements
  are byte-for-byte unchanged.
- **No new endpoint and no new scope** — `docx_block_url` performs no API call at all; the other
  fixes reorder or tighten existing local behavior. Nothing to grant.
- **No breaking change for valid inputs.** The one behavioral tightening affects only malformed
  deep links (silent mis-parse → loud refusal), which is the failure-safe direction.

## [1.31.0] — 2026-08-10

### Disclosures

- **Folder reads grew their ledger half.** `folder --dump` now writes a machine-readable child
  manifest beside the Markdown — one flat row per walked child (title, token, type, surface,
  outcome, path, depth, url, parent token, created/modified time, owner, revision where the child's
  surface exposes one, and the skip record where it doesn't or the child refused). Together with
  the new cheap revision probe (below) this closes the traverse → probe → download-only-what-moved
  loop.
- **A document's revision is now readable without reading the document.** The document-meta route
  returns `revision_id` beside the title with **no blocks fetched** — one call, no content
  transfer. The **bulk** variant was probed and is a **measured refusal**: no batch route answered
  on this tenant, and the notes enumerate what was tried rather than claiming impossibility.
- **Ghost tabs no longer poison a workbook read.** A new whole-spreadsheet walk reads every tab
  and **skips a refused tab loudly** — Lark's verbatim error code and message per tab ride the
  returned object and the rendered Markdown — so a workbook where 20 of 22 tabs are
  server-enumerated ghosts returns the two real tabs plus twenty named skips, instead of one
  exception and nothing. An all-skipped result is distinguishable from success. Existing
  single-tab reads are unchanged.
- **The deep-read flags reach `folder`.** `--deep-read-sheets`, `--fidelity-read-sheets` and
  `--deep-read-bases` are accepted by `folder` with byte-identical spelling, defaults and help
  text as on `download` (one shared definition — the texts cannot drift apart). Per-child
  deep-read failures inherit the skip-loudly posture.
- **`folder --assets` (opt-in, off by default)** fetches image assets folder-wide into one shared,
  flat, token-named pool under the output's existing asset directory — an image-only document
  comes back as a local PNG instead of a bare token. Filename collisions cannot occur by
  construction (asset tokens are the filenames).
- **Cell fills were already carried by the export-fidelity leg — now they are joined and
  disclosed.** No second route was built (the probe confirmed the existing leg exposes per-cell
  ARGB fills from one whole-workbook export); the fidelity read and the folder deep-read now
  surface them, and the docs say exactly where fills come from and what they cost.
- **`copy_base` accepts `folder_token`.** Probed three ways before shipping: the parameter is
  genuinely **honoured** — the copy reads back inside the requested folder from the folder's own
  listing, not merely echoed — so copies land where humans can find them.
- **Deep-link truth tightened in the guide:** deep links parse only on Lark-family hosts over
  `https`; anything else is `NotADeepLink`, loudly. (This was always the shipped behavior; it is
  now stated and conformance-pinned.)
- **Consumer install hints corrected** where they actually needed it: upgrade-path reinstall hints
  now carry `--no-deps`; first-install hints were verified correct as written and left alone; a
  stale version literal in hint text was neutralized.
- **New: you can mint a link to a specific block in a document.**
  `docx_block_url(doc_url, block_id)` — importable from `larkdocio.common` — builds
  `<tenant-host>/docx/<doc_token>#<block_id>` from the document's own URL and a block id the
  reader already emits. Pure and offline: **zero API calls, no credential, no scope**, the docx
  twin of `sheets.tab_url`. It ships with the edge of its evidence rather than a bare claim: the
  bare fragment was clicked in the Lark **web** client, on one tenant, on 2026-08-10, against all
  six block kinds tried — heading1, heading2, paragraph, table, bullet, code — and anchors on
  every one (a heading, paragraph or bullet is jumped to; a table or code block is moved to with a
  momentary highlight). **Unmeasured, and therefore neither refuted nor supported:** the mobile
  client, the desktop app, wiki-wrapped documents and any other tenant. A wiki-wrapped URL is
  refused rather than guessed at.
- **The 1.29 "docx anchors are UI-only" claim is narrowed, not withdrawn — and its hazard is now
  documented.** The reasoning about `…/docx/<doc>#share-<token>` is unchanged and still true: that
  fragment is an opaque share token the web client mints, no endpoint resolves it, and this
  library cannot mint one. What was too wide was applying that verdict to docx anchors **as a
  class** — the bare-fragment grammar above had never been tried. The two grammars are now stated
  separately everywhere the claim appears. **Do not bridge them:** `…/docx/<doc>#share-<block_id>`
  navigates nowhere and shows a toast reading "The selection content has been deleted" about
  content that is perfectly intact — the same lie-class as the sheets cell-link toast, and a
  reader who sees it will file a data-loss bug against an undamaged document. Passing a `share-`
  prefixed id to `docx_block_url` is refused with that reason.

### Upgrade & compatibility

- **No dependency moved** — no add, no drop, no pin change, runtime or dev. The wheel's install
  requirements are byte-for-byte unchanged. (The only packaging-file change registers an internal
  test marker; it alters nothing a consumer installs or runs.)
- **No new scope.** Two new endpoint rows entered the permissions matrix (the document-meta read;
  the Base copy's folder parameter) — both under scopes this library already documented. Nothing
  to grant.
- **No breaking change.** Every new capability is opt-in (new flags, a new optional parameter, a
  new walk entry point); existing call sites and existing single-tab/single-document reads behave
  exactly as before.

## [1.30.0] — 2026-08-09

### Disclosures

- **New: `create_table` can now name the new table's default view — via a composite it discloses
  honestly.** Lark's create endpoint rejects a `default_view_name` key on the request body
  (`1254001`, measured) — that has not changed, and the key is still never sent. What is new: pass
  `default_view_name` on a table-create entry and the library creates the table, then renames the
  single view the table is born with, addressed by the id the create's own reply carries — never by
  comparing a locale-dependent view name. **The composite is not atomic**, and the library says so
  rather than pretending otherwise: if the rename fails after the create landed, you get the typed
  `TableCreatedViewNotNamed` error carrying the created `table_id`, the default `view_id` (or an
  explicit statement that it was not learned), the name you asked for, and Lark's unedited denial
  body. The table is **not** deleted and the call is **not** retried — one `update_view` call from
  you, with the ids the error hands you, completes the rename. An entry without the key behaves
  exactly as before: no existing call site gains a second write. The result is confirmed by reading
  the table's view list back, never by the write's `code:0`.
- Everything else in this release is internal — test-suite speed and reliability work,
  development-documentation hygiene, and a behavior-preserving decomposition of the writer's
  reconciliation internals whose refusal messages are byte-frozen by characterization tests.
  Nothing else observable at the API or CLI surface changed.

### Upgrade & compatibility

- **No dependency moved** — no add, no drop, no pin change. The wheel's install requirements are
  byte-for-byte unchanged. (One test-only extra, `pytest-xdist`, was added to the development
  repository's dev extras; a consumer installing the wheel inherits nothing from it.)
- **No new endpoint and no new scope** — the create-then-rename composite reaches only endpoints
  this library already calls (`create_table`, `list_views`, `update_view`), under the scopes it
  already documents. Nothing to grant.
- **No breaking change.** Existing `create_table` call sites without `default_view_name` behave
  exactly as before — no second write is added to them.

## [1.29.0] — 2026-08-09

### Disclosures

- **BREAKING, AND IT IS A DATA-LOSS FIX: editing a `SingleSelect` / `MultiSelect` column now
  requires you to hand back its option `id`s, and two shapes that v1.28.0 accepted are refused.**
  A select cell stores the option's **`id`**, not its name, and `PUT .../fields/{f}` **replaces**
  the whole option set, matching on that id. Up to 1.28.0 this library **could not send an option
  id at all** — it read `name` and `color` off each option you passed and silently dropped the
  `id` — so *every* options-carrying `update_field` handed the server a fresh option list. The
  server minted new ids for it and every cell pointing at an old id was orphaned. Measured on a
  throwaway Base with six populated cells per column: ids on the wire kept **6 of 6** cells; ids
  missing left **0 of 6**, even when the names and colours were byte-identical; and a **bare
  rename** — an update sending no options at all — emptied the option set outright and also left
  **0 of 6**. A single colour change could empty every cell of the column.
  **What is now fixed:** an option `id` you supply **goes on the wire**, so recolouring or
  renaming options on a live column works — pass the options you read back from `list_fields`
  through unchanged, each with its `id`, alongside whatever you are changing. An option with no
  `id` *beside* id-carrying ones is treated as an **addition** and is allowed. An unrecognised
  per-option key is now refused **by name** instead of dropped.
  **What can break you:** two shapes are refused locally, before anything is sent — (1) an update
  of a select column that carries **no option set**, which includes a bare rename of one, and
  (2) an update whose options carry **no `id` on any of them**. If you were doing either, you were
  losing cells; the refusal names the fix. The check is on the request's **shape**, not on whether
  the column holds data — populated-ness cannot be known without reading the whole table, and an
  unknown blast radius is not a safe one — so an **empty** select column is refused identically,
  and the refusal says so out loud. Non-select columns are untouched: a name-only rename of a text
  column, and a `Currency` / `DateTime` / `Rating` property edit, behave exactly as before.
  **And there is no safe API route to discard an option set on a live column** — that is a
  deletion, not an edit, and this library does not ship it; do it in the product.
  **Set colours at CREATE time.** `option.color` is an int the server stores verbatim — 21 ints
  spread across `0`–`53` (`0, 1, 2, 3, 4, 5, 8, 11, 14, 17, 20, 22, 24, 28, 33, 36, 40, 43, 46, 49, 53`)
  were each sent and read back unchanged, a separate probe accepted `54` and stored it, and
  `-1`, `99` and `1000` were each refused `99992402 field validation failed`. The ints between
  the ones listed were **not probed** — that is a measured spread, not a whole-range promise. Set them in `create_field` or in a `create_table` fields
  kit, where there are no cells to orphan yet. **What shade an int paints is not something this
  library reads**, so it does not name one for you: set them once, look, and write down what you
  see.
- **New: `contacts.resolve_colleague(email=…)` — an EMAIL becomes exactly one `open_id`, or a
  refusal that tells you what it did and did not establish.** The library could already turn a
  display *name* into an id (`resolve_user`, the directory search); it now has a second forward
  verb over a different endpoint family (`contact/v3/users/batch_get_id`), and on this tenant
  that family resolved another user the directory search reaches by no query at all. It returns
  the **same** `NameLookup` — one `UserRef` or one typed `Refusal`, never both, always with the
  partiality disclosure — so nothing about how you branch on an answer changes. It is a **point
  query**: one identifier in, one id out, no roster, no cache, no best-effort matcher. Read it
  with three limits it states in its own voice, in the refusal and in the guide: **(1)** an
  unresolved identifier is **undifferentiated** — an address that exists nowhere and a real
  person this app cannot see produce the *identical* body, so the refusal reports that the
  lookup did not resolve it and picks **neither** reading; **(2)** the **reach is measured at
  two identifiers**, both on one small tenant, and whether it answers for an arbitrary member is
  **unmeasured**; **(3)** the **`mobile=` leg is accepted but has never been observed resolving
  anybody** — it is callable and refuses cleanly, and nothing here promises more. Another user's
  **name** is still not resolvable; an address route is not a name route. The endpoint's scope
  requirement is recorded **unknown** rather than guessed: nine calls across two credential
  pairs all answered `code: 0` and no scope was ever observed demanded, and no string for it
  could be sourced. The permissions section of `larkdocio.guide()` carries the same
  generated table (`PERMISSIONS.md`, in the dev repo, is its twin).

- **New surface — read an entire Drive folder as one Markdown document: `larkdocio folder <url>`.**
  Hand it a Drive folder link and it walks the tree, reading every document inside (docx, Sheets,
  Base) through the existing readers into one Markdown document with a tree index. A child it cannot
  read is **skipped loudly** — named with Lark's own reason — so the walk **never fails on one bad
  child**; a `file` child (a binary upload) is disclosed, not downloaded, and a shortcut is followed
  to its target. `larkdocio download` now refuses a folder URL by pointing you at `folder`. It is
  **read-only**: creating, moving or deleting folders is not offered — that is a one-way permanent
  write, deliberately out of this first round. This is the sixth surface and the 13th
  `capabilities()` entry (`drive-read`).
- **New: `base.record_permalink(app_token, table_id, record_ids)` — the stable link to a Base
  record.** Returns Lark's own server-minted `record_url` for the records you name: **cross-session
  stable** (a re-fetch a session later returns the identical string), **per selection** (you pass
  record ids — it never dumps a whole table), one typed result per record (resolved / unminted /
  absent / forbidden). The other, credential-class URL Lark can also mint for a record is
  **deliberately never rendered** by this library. One batched read per `BATCH_GET_MAX_IDS` records;
  support was confirmed by the URL field actually appearing, not by a bare success code.
- **Smaller additions.** Per-family counts on the apply log (`ApplyLog.families`, an additive
  `{operation: count}` accessor over what was applied); and a generated **per-type filter-condition
  shape reference** in the guide — which condition shapes are measured versus not-yet-established, so
  a `search_records` filter body is never a guess.

- **The `[YYYY-MM-DD_HHMM]` stamp in a downloaded file's name is UTC — and now it says so.**
  Nothing about the name changed: same shape, no offset, no `Z`, and `title_as_filename: false`
  still gives a stamp-free `<document token>.md`. What changed is that the fact is now written
  down where you meet it. `larkdocio download --help` states the timezone **and the reason** —
  one document downloaded at one moment lands under the same name on every machine, which is
  what makes the name comparable across machines. And `--dump` now writes an additive
  `filename_timestamp` object (`timezone`: `"UTC"` by default, `format`: `"[%Y-%m-%d_%H%M]"`)
  alongside the existing `document` and `blocks` keys, so an ingestion ledger can read the basis
  instead of assuming it — the failure this answers was a ledger that timestamped its own rows
  off the filename and was silently off by the machine's offset. The sidecar is still a function
  of the payload (and the chosen basis) alone. **If you have been treating that stamp as local
  time, your recorded times are off by your offset** — that is the one thing to check.
  A local-time naming option was considered and declined **here** on determinism grounds — but
  that decision has since been **reversed**, and it ships in this same release as the opt-in
  `--local-time` flag (below): the default basis does not move, and a caller who wants local
  naming trades the cross-machine comparison knowingly.

- **Three new `download` flags, all opt-in, all leaving their defaults exactly where they were.**
  **`--deep-read-bases`** — the embedded-Base deep read finally has a command-line route, the
  twin of `--deep-read-sheets`. Off (the default) is byte-identical and makes zero Base API
  calls; on, it inlines a Base embedded in the document as Markdown tables, degrading to the
  usual placeholder on any failure, so a download never fails because a Base could not be read.
  (This reverses an earlier documented "no CLI flag for it" — the reason had gone circular, since
  `--deep-read-sheets` is itself a read switch that builds a client.)
  **`--local-time`** — stamp the output filename in the machine's local clock instead of the
  default UTC. The shape is unchanged; only the digits move. **The trade-off is printed in the
  flag's own `--help`:** the same document downloaded at the same instant on two machines in
  different zones then lands under different names, so a filename-keyed ledger becomes
  machine-dependent. UTC stays the default and keeps that name identical everywhere; `--dump`
  records which basis a run used.
  **`--route area/section/topic`** — place the output under a subpath you supply, instead of
  letting a document carrying a metadata table self-route. **You supply the path; larkdocio infers nothing** —
  there is deliberately no title-convention or filename heuristic (a request to learn a
  document-title grammar was declined: a library that learns one caller's naming scheme
  has stopped being general). It overrides a document's own routing and works whether or not
  the routing off-switch is set. An absolute path, a `..` segment or an empty segment is refused with the
  reason named — it cannot escape `-o`.

- **A statement in the shipped guide was WRONG, and if you planned around it, re-read it.** The
  guide's person-cell recipe (and the matching `capabilities()` note) said the documented
  email-or-mobile → `open_id` route, `contact/v3/users/batch_get_id`, had **never been called**
  from here, so its reach was unknown. That was false: the route **has** been called, and it
  **resolved another user's `open_id` from that second user's email address** — it reaches past the
  directory search rather than being refused by anything. Two things stay true and are now said
  plainly: that reach is **measured at two identifiers on one tenant**, not established for an
  arbitrary member; and **larkdocio still ships no verb for it**, so an email is not yet an
  address you can hand this library. Nothing you call behaves differently — this is a correction
  to what you were told, which is exactly the kind of thing you would otherwise plan around.
- **Deep links: you can now PARSE the four Lark URL grammars losslessly, MINT the one that is
  mintable, and you are told plainly about the two that are neither.** `parse_deep_link(url)`
  (in `larkdocio.common.url`, beside the unchanged `validate_download_url`) recognises a docx
  section anchor, a spreadsheet tab, a spreadsheet cell/range, and a Base record link, returning
  a typed address that carries every opaque part — the `share_token`, the `rangeId`/`rangeVer`,
  the record token — **exactly as it arrived**; anything else is a typed *not-a-deep-link*
  answer, never a guess. A docx `#share-<token>` is **never** reported as a `block_id`.
  `larkdocio.sheets.tab_url(sheet_url, sheet_id)` mints the one click-proven spreadsheet deep
  link; it is pure and offline, and the tenant host is read off the sheet's own URL, never the
  API domain. Two links you **cannot** build and should not fake: a docx section anchor (use
  `emit_block_ids` in band instead) and a sheets **cell** link — a guessed `range=<A1>` URL
  half-works and shows a **"The cell was deleted"** toast about cells that are perfectly intact,
  so do not build one. Neither is a permissions problem — the data is not in the API at all.
  **No new endpoint, no new scope; nothing here calls Lark.**

### Behavior changes you can observe

- **A Base table is no longer created with a primary column Lark named — `create_table` now
  REQUIRES you to name it, and refuses if you do not.** In 1.28.0,
  `create_table(app_token, "Items")` was legal and landed a table whose primary column Lark
  named in **your tenant's** locale (`多行文本` on the reporting tenant), so the column your rows
  are keyed by carried a name you did not choose. That call now **raises before anything is
  sent** — no API call, no table — with a refusal that names the locale default it prevented and
  both ways forward. **The one-line fix:**
  `create_table(app_token, "Items", primary_field_name="Title")` — one `Text` primary column
  under your name, on exactly the same single call. For more columns at birth, the existing
  `fields=[…]` kit is unchanged and its **first** entry is the primary one. Passing **both** is
  refused too (the kit's entry 0 already names that column), even when the two names agree.
  larkdocio does **not** invent a name for you: a library-chosen `"Title"` would still be a name
  you did not pick.
- **`batch_create_tables` cannot name a primary column, so it now requires you to acknowledge
  that.** Lark ignores a per-table column kit on the batch route (measured), so there is nothing
  larkdocio could send to name those columns — every table it creates *will* arrive with the
  locale-named default. The call therefore refuses unless you say so:
  `batch_create_tables(app_token, names, accept_locale_default_primary=True)`. The request it
  then sends is byte-identical to 1.28.0's. To name those columns instead, use one
  `create_table(app_token, name, primary_field_name=…)` per table — still one call each.
- **You cannot name a new table's default VIEW at create time — Lark refuses it, so larkdocio
  does not offer it.** The naming discipline above is about the primary *column*; a table's
  default *view* is a separate name Lark also picks. We measured whether `create_table` could set
  it: sending a default-view name makes Lark reject the whole request (`1254001 WrongRequestBody`)
  and **no table is created**. So there is no create-time knob to offer, and the view keeps the
  name Lark's default gives it (a locale default — `表格视图 1` on the tenant measured). The view
  name itself *is* readable back, and renaming an existing view is already supported; naming the
  default view **as part of a create** is a candidate for a future release, not something 1.29.0
  ships.

### Upgrade & compatibility

- **No dependency moved** — no add, no drop, no pin change.
- **No new endpoint and no new scope** — this release calls nothing new. Nothing to grant.
- **One breaking change, and it is the Base table create.** If you call `create_table` or
  `batch_create_tables`, read the two bullets above: a two-argument `create_table` and a
  name-only `batch_create_tables` both now raise (`FieldAuthoringRefusal`, the family your
  `except` clauses already catch) with the one-line fix in the message. Nothing else moved.
- **Drop-in otherwise, with one thing to read.** Filenames, Markdown, routed paths and exit codes are
  byte-for-byte what 1.28.0 produced. The `--dump` sidecar gained one key and renamed none, so a
  reader that indexes `document` / `blocks` by name is unaffected; a reader that asserts the
  sidecar has *exactly* two top-level keys will see the third. The one thing worth reading is the
  UTC note above, because it may mean your existing recorded times need correcting.

## [1.28.0] — 2026-08-07

### New capabilities

- **A Base read can now be FILTERED, VIEW-SCOPED and SORTED — and the result is proven, not
  assumed.** `search_records` accepts three new keyword-only arguments: `filter=` (the
  `SearchFilter` that `search_filter()` builds — previously a body with nowhere to go),
  `view_id=` (read back exactly what a saved view shows — including checking your own view
  write), and `sort=` (a new `SortKey`, by field name). All three default to absent, so an
  unfiltered read sends exactly the bytes it always sent. Because this endpoint silently
  ignores body keys it does not recognise, the capability was proven **differentially** against
  a live Base: a filtered read returns a strict subset the predicate holds over, a
  match-nothing filter returns nothing rather than everything, `desc` is exactly `asc`
  reversed, and a filtered walk re-sends the filter on **every page**. Two honest edges are
  refused rather than guessed: `view_id` does not combine with `filter`/`sort` (the composition
  has never been observed, and a wrong guess would be undetectable), and an unknown sort field
  is Lark's own refusal, surfaced verbatim.

- **A table can be created WITH its columns — one call, one plan entry.** `create_table` now
  accepts a field kit: every column definition rides the same create call, held to the same
  vocabulary and property enforcement as a standalone column create (an unauthorable kind or a
  missing required property refuses the whole op at plan time, before anything is sent, naming
  the offending column). The created table's **first kit column becomes the primary field** —
  so the locale-named default primary (多行文本 on a Chinese-locale tenant) never appears.
  Priced as what it is: one call. The **batch** verb deliberately refuses a field kit: Lark
  accepts the same array there with a success code and silently creates every table without
  it, so forwarding it would report success for nothing — the refusal says so, and a live
  check will redden the day Lark starts honouring it.

- **The guide now answers "what does a Base cell TAKE, and what does it HAND BACK?" for every
  type, in one generated table** — write shape beside read-back shape beside the difference,
  all 27 types, with the five sharpest asymmetries (email, text, link, location, person)
  called out quoting the refusals the library already speaks. Generated from the same
  registries the encoders run on, so it cannot drift from the code.

- **`cell_text()` and `plain_value()`** — the five-line flattener every consumer was writing
  is now shipped: plain projections from a raw Base cell to a string / a plain value,
  tolerant of both the typed and dict shapes, never mutating, with per-type behavior stated
  in the docstring rather than guessed.

- **Reads now carry the revision anchor a change-detection ledger needs.** Sheets: the tab
  objects expose the same per-spreadsheet `revision` the used-range read already carried
  (plus `read_revision` / `read_tabs_revision` to get it without reading values); absent is
  `None`, never `0`. Base: the read result exposes each table's `revision` — the data was
  already fetched and is no longer dropped. Zero new endpoints, zero new scopes.

- **A Drive folder URL is now recognised** — parsed to its token and, for now, refused with a
  teaching message that names what the command line can read instead. The folder *reader* is
  the next release's headline; this release stops the URL from being mistaken for a document.

- **When the download's metadata-table routing does not route, it now says why** — the detection
  outcome and the missing piece are reported, so an unrouted document is a diagnosis instead
  of a mystery. The detection rules themselves are unchanged (and deliberately generic).

- **Every operation row in `capabilities()` now resolves to real code** — the `projected_from`
  on all 88 rows is machine-verified against the package, and `capabilities()["docs"]` states
  that every guide heading is addressable via `guide(section=…)`.

- **A Base apply-log now says what `46 applied` is made of.** `ApplyLog.families` is a computed
  `{op: count}` breakdown of what **landed**, so a schema run reads as `45 create_field + 1
  delete_field` (and a record run as its creates/updates/deletes) instead of one alarming
  number. The keys are the ops the entries already carry — the library invents no op vocabulary
  — it counts over `applied` only, and its counts add up to exactly `len(log.applied)`. Purely
  additive: no existing accessor changed and the serialized `to_dict()` shape is untouched.

### Behavior changes you can observe

- **A select-field view filter written with option NAMES now works instead of failing at
  apply.** Previously a name-valued condition sailed through the dry run and died at apply
  with Lark's "option id … not found". The registry now retains each select field's options
  and **translates a known name to its option id** on the view route; an id you already hold
  passes through; an unknown value refuses locally, naming the options that exist. The
  **search** route is the measured mirror image — it takes option *names* — and both rules are
  stated once in the library and quoted by every refusal that enforces them.

- **When the platform itself breaks, the log now says so — and stops.** If every attempted
  entry of a schema plan fails with the *same* error code the taxonomy does not know, on ids
  the read client vouched for in that same plan, the apply log discloses **"a platform
  anomaly, not your plan"** — and after two such identical failures the engine **halts the
  remaining entries** instead of spending one throttled call per entry to collect the same
  alien error N times. Halted entries are enumerated in the log as not-attempted, each saying
  why and that nothing was sent for it; Lark's own code and message are preserved verbatim.
  The halt also requires that nothing in the plan has applied and that entries remain to
  skip — a plan whose failures only complete on its last entry still reports it continued.
  Genuine per-entry refusals, mixed failures, and single-entry plans behave exactly as
  before. There is deliberately **no retry**: the observed failure mode does not clear
  between attempts, and a backoff would only turn a legible failure into a hang.

- **Five column kinds now refuse a property-less create BEFORE the call.** `Currency`,
  `DuplexLink`, `Progress`, `Rating` and `SingleLink` are refused by the server when created
  without a `property`; the library previously let that round-trip fail. Each now refuses at
  plan time, at zero cost, naming the captured working shape. All 24 creatable kinds'
  property requirements are now individually capture-proven.

- **The guide got a truth pass.** The structural-handshake recipe's delete portion now shows
  the `read_client=` a destructive dry run requires and both import lines (they live in two
  different modules); a contradiction about whether deletes are "on this path" is resolved
  (a Base delete is on no path; table and field deletes are on this one, behind consent); a
  new section names the three places a refusal can arrive (build-time, plan-time,
  apply-time) and why they stay distinct; the credential setup now says the READ/WRITE pairs
  may point at one app — the split is about routes, not necessarily two registrations.

### Upgrade & compatibility

- **No dependency moved** — no add, no drop, no pin change.
- **No new endpoint and no new scope** — every capability above rides endpoint families and
  scopes the library already used. Nothing to grant.
- **No exception class moved** — the 1.27.0 hierarchy stands; `except` clauses need nothing.
- **A programmatically created Base lands in no folder.** `create_app` files the new Base in
  the app's own space; moving or trashing it is a human action in the Lark UI — the library
  ships no Base delete and no Base move, because the API has none.

### Known limitations

- **A one-day Lark platform regression broke all field authoring on 2026-08-07 — it healed
  before this release was cut, and the hardening it prompted ships anyway.** For most of that
  day, Lark's `create_field` / `update_field` / `convert_field` endpoints rejected valid table
  ids server-side (code 9499) while every other route worked; the failure was reproduced
  independently of this library and reported to Lark with their own trace id. This release's
  final live ring verified full recovery. What remains, permanently: the platform-anomaly
  disclosure and halt (above), and fields-at-creation as the one-call path that never depends
  on those endpoints.
- **A field kit on the BATCH table-create is refused locally** — Lark currently accepts and
  silently ignores it (see New capabilities). Create tables one at a time when they need
  columns at birth.
- **`view_id` does not combine with `filter`/`sort` on a read** — the composition is
  unobserved, and on an endpoint that ignores unknown keys, a wrong guess would read as
  success. Refused with the reason; strictly widenable later.

## [1.27.0] — 2026-08-07

### New capabilities

- **Read — and build — a Base row tree (sub-items).** A Lark row tree is not a record concept:
  there is no parent field on a record, and six plausible ones were each proven to behave exactly
  like a made-up key. It is a **link column pointed at its own table**, named by **one view
  property**. So: `hierarchy_config` is now a view parameter (a wrong target is refused *locally*,
  in the server's own words, rather than after a round trip), the parent edge is an ordinary cell
  write through the path that already shipped, and `read_hierarchy` turns the column into a tree
  in depth-first order — reconstructed here from the pointers, for **no extra API call**. It never
  guesses which column is the hierarchy: name it, or hand over a view, and the answer says which.

  **Lark accepts two shapes no tree can contain — a row with two parents, and a row that is its
  own parent — and larkdocio discloses both rather than refusing either.** Before a parent write
  you get a warning built from the graph you already hold, and if you passed no graph it tells you
  **it did not check** rather than letting silence read as safety. On the way back nothing lies and
  nothing hangs: cycles are marked and the walk terminates, both parents survive, a parent you did
  not read is *detached* rather than promoted to a root, and a table with no hierarchy comes back
  *not configured* rather than as an empty tree.

  And the part that needs none of the above: **`resolve_links=True` already renders a parent-name
  column today** — `ROOT-1 / CHILD-1 / LEAF-1` instead of `recvrvyxLVX9TP`.

  ```python
  from larkdocio.base import hierarchy

  tree = hierarchy.read_hierarchy(fields, records, view=view)   # or field_name="Parent"
  print(hierarchy.render_hierarchy(tree))
  print(hierarchy.parent_write_disclosure(
      child_id=root, parent_ids=[leaf], hierarchy=tree)["cycle"])
  ```

- **Change a Base column's type — safely, as one operation.** larkdocio still refuses to
  *convert* a column whose conversion nobody has watched Lark perform (`Text → Number` and every
  other uncaptured pair), because that rewrites every value server-side and cannot be undone.
  What it no longer does is leave you to rebuild the column by hand. `plan_field_migration` /
  `apply_field_migration` run the whole five-step sequence — create a staging column, copy the
  re-encoded values, **read the copy back and compare it**, delete the old column, rename the new
  one — as one plan and one consent. The preview costs zero writes and carries the same loss
  preview a delete does; the delete is **unreachable until the copy has been verified**, so *the
  copy did not round-trip* means nothing is destroyed; and a value the new column cannot hold
  refuses the whole migration before anything is sent, naming the records. It is not a conversion
  and it is not atomic — both said plainly, with a halted run's log naming where you are and what
  a recovery would do.

  ```python
  from larkdocio.base.field_migration import apply_field_migration, plan_field_migration
  from larkdocio.base.schema_apply import consent_to_destroy

  plan = plan_field_migration(read, app_token, table_id,
                              field_name="Estimate", to_field_type=2, to_ui_type="Number")
  log = apply_field_migration(plan, schema_client=schema, client=write, read_client=read,
                              consent=consent_to_destroy(plan))
  ```

- **Read a Lark Base (bitable) as Markdown.** The library could read documents and
  spreadsheets; a Base was recognised as a kind of URL and nothing more. It can now be read:
  one `##` heading and one GFM table per Base table, in the order the API lists them.

  ```python
  from larkdocio.base import read_base, read_base_markdown

  markdown = read_base_markdown("https://your-host.larksuite.com/base/YOURAPPTOKEN")

  # or keep the data instead of the string — no second network read to get the Markdown later
  document = read_base(document_url_or_app_token)
  for table in document.tables:
      print(table.name, [f.field_name for f in table.fields], len(table.rows))
  ```

  **Two entry points, because a string is not always what you wanted.**
  `read_base_markdown` returns the reading form; `read_base` returns the structured
  document — the field list, the record ids, and each row's rendered cells — and
  `render_base(document)` turns that into the same Markdown without calling the API again.
  Both accept **either a Base URL or a bare `app_token`**. A spreadsheet or document URL is
  refused by name rather than read as a token.

  **Import it from `larkdocio.base`.** It is deliberately not re-exported from `larkdocio`
  itself yet, does not appear in `capabilities()`, and has no CLI flag.

- **Every cell type the field picker offers renders**, driven by the field's own
  configuration rather than guessed from the value: number / currency / progress / rating
  formats, select option names, dates in the Base's own time zone, links, attachments by
  name, and person-bearing fields **by name only**. No email address, avatar URL or person id
  from a person object reaches the Markdown.

- **A Base embedded inside a document can now be read inline — if you ask.** A document that
  embeds a Base has always shown a placeholder where it sits. Turn the deep read on and the
  referenced table is rendered in place of it instead:

  ```python
  from larkdocio.base.client import BaseReadClient
  from larkdocio.read.parser import Parser
  from larkdocio.read.config import Config

  parser = Parser(Config(), deep_read_bases=True,
                  base_client=BaseReadClient.from_read_credentials())
  ```

  **Off by default, and off means off**: with the flag unset the reader makes **zero** Base API
  calls and your Markdown is byte-for-byte what it was before. Both kinds of embed are covered
  — a plain embedded Base and one switched to a named view — and only the **referenced table**
  is read, never its siblings. **Any failure degrades back to the placeholder**: a stale token,
  a table that no longer exists, a missing scope or a network error will not fail your
  download. It works exactly like the embedded-*spreadsheet* deep read (`deep_read_sheets`),
  on purpose.

- **A Base that a document created for itself is a different animal — and the guide now says
  so.** When Lark auto-provisions a Base for an embed block, it is **owned by that document**:
  it has **no time zone** (dates render in UTC), a **blank** title, and it **cannot be deleted
  on its own** — deleting the document is what removes it. Nor can such an embed be pointed at
  a Base you already have. If you have tried to manage one as a normal Base and been confused,
  that is why.

- **Read a Base's comments — and see which ROW each one is about.** The comments surface
  already read documents and spreadsheets; it now takes a Base too, through the same call:

  ```python
  from larkdocio.comments import comments

  review = comments(app_token, file_type="bitable")
  for thread in review.comments:
      print(thread.attribution_state, thread.attribution, thread.rendered_thread)
  ```

  A comment written against a row reports **the record, table and view** it was written
  against, as structured data rather than as a string to parse. A comment that names no row
  is reported as `file-level`: the surface reports what the payload says and infers no row
  from silence. A Base with no comments gets the same ordinary "the read succeeded and found none"
  result a document does, not an error.

  **A comment thread never renders a person.** `rendered_thread` labels an author, and any
  @mention inside the text, with a redacted marker: the payload carries no name at all, only
  an opaque id, and an id is not something to print. The id is still on the projection for a
  caller that can resolve it.

- **The Base read is checked against a real Base, not only against recorded payloads.** The
  read now has its own live check, alongside the ones the document and spreadsheet readers
  already had: it reads a Base twice in one run and requires the two results to be
  **byte-for-byte identical**, that every column type it meets is one the library knows, and
  that nothing person-sourced — no email address, no avatar URL, no person id — reaches the
  Markdown. It is **read-only** and changes nothing about the Base it reads. So if Lark changes
  a payload shape under you, that shows up as a failing check rather than as quietly wrong
  Markdown.

- **The install now describes the Base surface, so you do not have to read source to find
  it.** `capabilities()` reports **three** read surfaces — `base-read`, `base-comments-read`
  and `base-embedded-deep-read` — each with the exact scope it needs, the entry point that
  returns objects, the one that returns Markdown, and the limits worth planning around; the
  deep read has a `deep_read_bases` row among the flags. `guide()` gains a **Base recipe that
  runs as pasted**, its permissions table carries the Base rows (generated from the same
  registry, so it cannot fall behind), and `larkdocio --help` names the three surfaces in its
  roll. Two wordings in there are
  deliberate rather than incidental: **larkdocio does not control a Base's shareability** (it
  exposes no operation that would), and a Base's *roles* refusal is a **product feature gate**
  — advanced permissions are switched on by the **Base's owner**, in the product, so no scope
  granted in your console will change it.

  ```python
  import larkdocio

  caps = larkdocio.capabilities()
  print(caps["surfaces"]["base-read"]["credentials"]["scopes"])   # what to grant
  print(caps["surfaces"]["base-read"]["levels"]["summary"])       # objects vs Markdown, + limits
  print(larkdocio.guide(section="Recipe: read a Base to Markdown"))  # the recipe, on its own
  ```

- **Write a Lark Base's RECORDS — plan-gated.** The Base was readable; its rows can now be
  changed. Read a table into a snapshot, edit the snapshot in memory, preview the change as a
  `Plan` (zero API calls), then apply that plan — the same handshake the document and
  spreadsheet engines use. **This engine writes the rows and changes no shape**: nothing on this
  path creates, renames, converts or deletes a column, a table or a view, so plan around the
  schema it read. Changing a Base's shape is a separate engine with its own gate, described
  below.

  ```python
  from larkdocio.base.apply import apply, dry_run

  plan = dry_run(snapshot.edit().set(record_id, "Text", "written by larkdocio"))
  log = apply(plan, client=write_client, read_client=read_client)
  print([entry.outcome for entry in log.entries])       # 1:1 with the plan, in plan order
  print(larkdocio.guide(section="Recipe: the Base write handshake"))
  ```

- **Two things about Base writes that are unusual, and are stated rather than hidden.**
  First, **there is no `If-Match` on this API**: a write carrying a revision in its body is
  accepted and the write lands, so larkdocio sends no such key and guards **client-side**
  instead — it re-reads the table's revision, compares it to the one your plan was built on,
  and only then writes. That closes the window between your plan and your write, and not the
  last microsecond after it; a table that moved refuses `stale-base` with **zero writes for
  that table**, and the cure is re-read, re-plan, re-apply. Other tables in the same plan are
  judged against their own anchors. Second, **success is not evidence that a write happened**:
  some cells accept a write, answer success and store nothing, so every call is followed by a
  second revision read and a call that did not move it is reported `dropped`, never `applied`.
  Read `entry.outcome`; do not assume.

- **Computed cells and wrong-shaped values are refused before any call is made.** A formula, a
  lookup, a stage, an auto-number and the four created/modified time and user fields are owned
  by the server; a value that is not its field's write shape is a different object from what a
  read hands back. Both are refused at plan time, so they cost nothing and the plan shows them.
  A **person or group** cell is written by **id** (`open_id`), never by name — the guide's Base
  write recipe names the two honest sources of an id, and larkdocio invents no third.

- **`capabilities()` now reports a fourth Base surface, `base-write`** — the first that is not
  read-only — with its scopes, its safety contracts and where they are proved live. The two
  Base **read** surfaces' live arms are declared in the same place.

- **You are told which columns Lark will create, and told it before you ask.** Lark's fields
  API declares its own vocabulary in the body of every refusal it sends, and larkdocio now
  ships that vocabulary verbatim — **20 storage types and 24 column kinds** — at
  `capabilities()["surfaces"]["base-schema-write"]["field_authoring"]`. Four kinds are outside it:
  `Lookup`, `Stage` (the product calls it Flow), `Email`, and anything Button-shaped. Naming
  one is refused **locally, with no API call at all**, in a message that repeats the value you
  wrote, says that the **server** declares the accepted set rather than larkdocio, lists it,
  and tells you what *is* possible instead — a `Lookup` or a `Stage` column arrives only by
  copying a Base that already has one; an `Email` column cannot be created, and that is the
  only thing you cannot do with one, because its cells read and write fine; a Button column
  larkdocio will not support in any case, which is a decision on this library's side and not a
  limit on Lark's. **Note what this list is not.** It answers *can I create this column?*,
  which is a different question from *can I write this cell?*: a formula, an auto-number and
  the four created/modified time and user columns can all be **created** while their cells
  never accept a value, and an `Email` column is the exact reverse. This is the vocabulary the
  column-authoring operations below are **held to**, and it is published on the same surface
  that enforces it.
- **A Base's SHAPE can now be changed — create, rename and copy a Base, create and rename
  tables.** All behind the same preview-then-apply gate the other engines use: build the ops,
  `schema_dry_run` them into a plan (zero API calls), then `schema_apply` that plan. Deleting a
  table or a column ships too, behind a further fence described below. **A Base itself has no
  delete verb at all** — Lark's own route trashes rather than purges, so nothing here offers
  one.

  ```python
  from larkdocio.base.schema_apply import schema_apply, schema_dry_run
  from larkdocio.base.schema_client import BaseSchemaClient
  from larkdocio.base.schema_plan import copy_base, create_table, rename_base

  plan = schema_dry_run([rename_base(app_token, "Inventory"),
                         create_table(app_token, "Items")])
  log = schema_apply(plan, client=schema_client, read_client=read_client)
  ```

- **Copying a Base is the only way to get a `Lookup`, `Stage` or `Email` column.** Lark's
  field-creation endpoint does not accept those types, so no API call can author one — but a
  copy is a server-side clone, and it brings them across fully configured. Build one in the
  product once, then copy that Base; `without_content=True` clones the columns without the rows.

- **A copy is ASYNCHRONOUS, and the library settles it for you.** The copy answers with a new
  token before the Base exists — reading it immediately answers *"Bitable is copying, please try
  again later"*. That is neither an error nor something to retry by hand: larkdocio polls, stops
  the moment the read answers, and records how it settled. If its bounded budget runs out you
  get `applied-unverified` — **the copy is on your tenant**, it is simply not readable yet.

- **There is NO staleness guard on a structural change, and every plan entry says so.** Record
  writes are protected by the table's revision; a structural op has no usable anchor, so instead
  **every one is verified by a read-back**. Read `entry.outcome`: `applied` means the server's
  own state showed the change; `dropped` means the call was accepted and the read-back did not
  show it. Each entry carries a `revision_guard_disclosure` stating the limit in plain words —
  nothing will notice if something else reshapes the Base between your plan and your apply.

- **`is_advanced` is refused before anything is sent.** Turning on advanced permissions is a
  Base-owner action in the product; the API refuses it outright, so asking for another scope
  will not help and the rename will not silently accept the argument.

- **You can author a Base's COLUMNS, behind the same plan gate.** Create a column, edit its name
  or its property, and — for one pair — convert its kind. Every column kind Lark declines to
  create is refused locally, before the call, in a message that says what *is* possible instead.

- **A column's `property` is built from shapes that were captured, not guessed.** The awkward
  ones are handled for you: a location's input type nests where Lark expects it, a currency
  takes a currency code, a rating takes its symbol and cannot be created without one, and a
  phone column's kind is `Phone` — asking for `PhoneNumber` is refused. **A property key no
  captured shape carries is refused rather than sent**, because this API silently ignores keys
  it does not recognise: an invented key would come back successful having done nothing.

- **Creating a two-way link column creates a column IN ANOTHER TABLE — and the dry run tells you
  first.** One call, two columns: the mirror lands in the table you are linking to, named after
  the source table and the source column. The plan entry names that table and predicts the
  mirror's name **before** anything is sent, so a cross-table change is never a surprise.

- **Converting a column's kind works for one pair, and refuses every other pair locally.**
  Changing a kind rewrites every value in the column, on the server, permanently. `Text` →
  `Barcode` has been observed end to end with the values intact, so that one converts. Anything
  else — including changing the storage type underneath a column — is refused **before any call
  is made**, naming the pair and saying why: nobody has observed whether Lark coerces the
  existing values, blanks them, or refuses, and this library will not guess on your behalf.

- **A column change IS guarded by the table's revision.** Unlike an app-scoped structural change,
  a field operation has a usable anchor: the library re-reads it immediately before the write and
  refuses, with **zero writes**, if the table moved since your plan. Afterwards it checks the
  anchor moved — a call that was accepted but changed nothing is reported as `dropped`, never
  `applied`.

- **Creating a column is not the same as being able to write its cells.** A formula, an
  auto-number and the four created/modified time and user columns can all be created while their
  values stay the server's own; an email column is the reverse — its cells read and write fine
  and the column itself cannot be created. Two questions, two answers.

- **A VIEW'S FILTER CAN NOW BE SET, AND IT STICKS.** Create a view, save a filter onto it,
  change that filter, delete the view — all behind the same preview-then-apply gate. The filter
  you set is the filter a person sees when they open that view.

  ```python
  from larkdocio.base.view_filters import Condition, FieldName, FieldRegistry, FilterSpec, view_filter
  from larkdocio.base.view_plan import set_view_filter

  fields = FieldRegistry.from_read_client(read_client, app_token, table_id)
  wanted = FilterSpec(conditions=(Condition(FieldName("Status"), "isNot", ("Done",)),))
  plan = schema_dry_run([set_view_filter(app_token, table_id, view_id,
                                         view_filter(fields.resolve(wanted)))])
  ```

- **There are TWO filters in a Base and larkdocio will not let you cross them.** One filters the
  rows a *read* returns and is keyed by the field's **name**; the other is the view's saved
  filter above and is keyed by the field's **id**. They also disagree on smaller things — one
  wants a value as a list, the other as a quoted string — which you do not have to know. You describe what you want once, then say
  which you meant — and the wrong one is refused before anything is sent, because the two are
  different types rather than two conventions. A field name is resolved to its id from a field
  list read to exhaustion; an unknown name is a refusal naming the columns the table has, and a
  field list that was truncated refuses to resolve at all rather than answering sometimes.

- **A view write is proved by re-reading the view, not by a success code.** This endpoint accepts
  some things and then ignores them: setting a view's *grouping* answers success and stores
  nothing. So after every view write larkdocio re-reads the view and compares what the server
  stored against what you asked for. `applied` means it is really there; `dropped` means the call
  was accepted and the change is not — you are told rather than left believing it worked. Note
  the flip side: **there is no staleness guard on a view write at all**, so nothing will notice
  if somebody else edits the same view between your plan and your apply.

- **Grouping, hidden columns, a saved sort and form views are deliberately not offered.** Setting
  a grouping is accepted and does nothing; hiding columns behaved two different ways on two
  different occasions with no way to tell which is current; a saved view sort has never been
  observed at all. A knob whose effect cannot be checked is worse than no knob. **Form views** are
  a separate matter: creating one *works*, and one further call would publish a public submission
  link — larkdocio does not control a Base's shareability, so it stays out of it entirely. Build
  a form in the product if you need one. Deleting a view is the mildest destructive Base
  operation that ships — a view holds no data of its own; a table's **last** view cannot be
  deleted, and you are told to create one first.

- **A COLUMN OR A TABLE CAN NOW BE DELETED — AND YOU ARE SHOWN WHAT THAT COSTS, ACROSS THE WHOLE
  BASE, BEFORE ANYTHING HAPPENS.** Deleting a column, a table, or several tables at once are the
  only operations here that destroy data, and none of them is reachable from an ordinary call.
  The dry run produces a **loss preview** and the apply refuses without your explicit consent to
  **that** preview:

  ```python
  from larkdocio.base.schema_apply import consent_to_destroy, schema_apply, schema_dry_run
  from larkdocio.base.schema_ops_destructive import delete_table

  plan = schema_dry_run([delete_table(app_token, table_id)], read_client=read_client)
  print(plan.entries[0].loss_preview)      # every column and table this reaches
  log = schema_apply(plan, client=schema_client, read_client=read_client,
                     consent=consent_to_destroy(plan))
  ```

- **The preview covers the WHOLE BASE, because the damage does.** Two things are true of a Base
  that are not obvious: deleting a **two-way link column deletes its twin in the other table** —
  one call, two columns, in two tables — and deleting a **table** leaves every link pointing at
  it, in every other table, **dangling silently**: those columns survive holding the ids of rows
  that no longer exist, and nothing errors afterwards. So the preview reads every table's columns
  first and names both columns, both tables and how many cells each currently holds, and lists
  every link elsewhere in the Base that a table delete would strand.

- **If the preview cannot be completed, nothing is deleted.** A table list that cannot be shown
  to have been read to the end, a column read that fails, a table this credential cannot see —
  any of them and the delete refuses, with **zero writes**, saying which read fell short. A
  partial answer here would be worse than none, because it would read as reassurance.

- **Deleted is not erased.** Lark's delete puts the object in the Base's trash, where a person can
  restore it from the product. There is no API verb that purges anything, and there is **no API
  undo**: this library reports what happened and never re-sends a destructive call. A Base's
  **last** table cannot be deleted either — you are told what to do instead, and the rest of your
  batch still runs, because that answer is about that table and nothing else.

- **A delete is proved, not assumed.** A column delete is confirmed by the column being gone
  **and** the table's revision having moved — a call that was accepted and moved nothing is never
  reported as applied — and for a two-way link the twin's disappearance is checked in the *other*
  table. A table delete is confirmed by asking the table's own address and getting Lark's own
  "no such table" back.

- **`capabilities()` now reports a FIFTH Base surface, `base-schema-write`** — the second that
  is not read-only, and the one that changes a Base's shape. It carries its own operations
  (every registered schema op, projected from the table that enforces them), its scopes
  (unchanged: the same single Base scope a record write already needed — nothing here widens a
  grant), the column allow-list it holds authoring to, its limitations in plain words, and the
  live ring where each of its promises is proved against the real API. Its safety contracts are
  the plan gate, the mandatory dry run, **a consent token minted from the plan itself for
  anything destructive**, **an app-scoped loss preview**, **a revision guard that covers column
  ops and openly does not cover the rest**, and the house rule that an apply log accounts for
  every entry.

  ```python
  import larkdocio

  schema = larkdocio.capabilities()["surfaces"]["base-schema-write"]
  print(schema["credentials"]["scopes"])          # what to grant — the same one, still
  print(sorted(schema["safety_contracts"]))       # what protects you, by name
  print(schema["credentials"]["note"])            # and what it will not do
  ```

- **The line the front door used to draw is retracted.** Until this release every consumer-facing
  document said larkdocio writes a Base's records and does **not** write its schema. That is no
  longer true and the sentence is gone from all of them — the README, the wheel summary, the
  packaged guide, the command-line help and the capability registry. What replaces it is bounded
  to what actually ships: **records and schema are both writable**, columns across a published
  allow-list, tables, and views carrying a persistent **filter** — while grouping, hidden
  columns and a view-level sort remain unoffered, and a form view remains out by this library's
  own policy.

- **You can attach a FILE to a Base now — and verify the bytes, not the status code.**
  `larkdocio.base.media.BaseMediaClient` uploads a file (as a file column's attachment or an
  image column's), hands back the file token an attachment cell is written from, and downloads
  that token again so `verify_round_trip(...)` can compare `sha256` digests. Three things to
  know before you call it. **It reaches the drive endpoint family, not the Base one** — being
  granted the Base permissions says nothing about whether it is permitted, and the
  per-operation rows in the packaged guide say so separately. **An upload is permanent**: the
  file token survives the deletion of the table it was attached to and of the Base itself, and
  no interface in Lark's open API purges uploaded media at all — larkdocio ships no purge verb
  and no "clean up my uploads" helper, because neither could work. And the two short-lived
  **signed** links an attachment cell reads back (`url`, `tmp_url`) are treated as
  credentials — never logged, never stored, never rendered;
  `scrub_attachment_cell(cell)` is the projection to use before one reaches a log of your own.

- **Person and chat cells: what you can address, said plainly — starting with the good news.**
  A person cell is written by **id**, and an id-written cell renders the person's **full name
  chip** in the Lark UI, exactly like one someone picked by hand. The display is unaffected;
  only the *addressing* is limited, and the packaged guide, the capability registry and the
  Base capability matrix now all say so in that order. Three honest sources of an id are
  named — harvest one from a read, supply one you already hold, or resolve the **account
  owner's own** through `larkdocio.contacts.resolve_user`. What larkdocio cannot do is turn another
  **user's** name into an id: the directory search behind that lookup returns only the
  account owner on the tenant it was measured against, and the documented email-or-mobile
  route has never been called from here at all, so its reach is recorded as unknown rather
  than as a refusal. No roster, no directory dump and no closest match ships in their place.
  One consequence is worth knowing before you write code against it: a person cell
  **round-trips through the model and not through the Markdown** — the structured read keeps
  the raw id, the Markdown projection emits the display name only, so a cell rendered and
  parsed back is a name, and a name is not an id. Chat ids are the easier twin (a group-chat
  cell takes the same shape and the chat list is obtainable in band), but no chat lister ships
  here either — that is a different endpoint family with its own grant. **No new call, no new
  scope, and no behavior change**: this release states what was already true.

- **What a broken Base link does is no longer a claim — it was watched.** Four things about
  linked records used to be written down and asserted; a live round trip against a Base built
  and thrown away for the purpose now shows each of them happening:

  - **A one-way link keeps pointing at a record you deleted.** Lark does not clean it up, and
    nothing reports an error. The cell still holds the dead id, and a resolved read renders a
    typed *dangling* marker rather than an id that looks like data.
  - **A two-way link heals itself.** The same delete quietly removes the id from the symmetric
    column without anyone writing to it — so the two kinds of link really do behave differently,
    and it matters which one you chose.
  - **Deleting a whole target table is silent.** The source column survives pointing at a table
    that no longer exists, a record search still answers success, and the only free evidence is
    the target's *name* dropping out of the column's own configuration. Reading that costs **no
    extra call** — it comes off the schema the read already fetched.
  - **A missing linked record is a normal outcome, not an error.** The read completes; the
    surviving links resolve; nothing raises.

- **The Base surface moves attachment files, and the front door now says so.** Earlier notes
  described a Base surface that did not fetch or push media. That stopped being true when the
  attachment leg shipped, and this release **retracts** the old sentence everywhere it was
  written — the README, the package summary and keywords, the command-line help, the capability
  matrix and the packaged guide. What is true: an upload hands back the file token an attachment
  cell is written from, and the same token downloads back, so you can verify the round trip by
  comparing **`sha256`** digests instead of trusting a success code. It is a leg **beside** the
  read and the write rather than part of either — a read still renders file **names** only, the
  short-lived signed links a cell reads back are treated as credentials and never render, and no
  media byte is ever inspected. **An upload cannot be undone:** the file token survives the
  deletion of the table and of the Base, and nothing in Lark's open API purges uploaded media, so
  the library says so instead of offering a cleanup that would not work.

- **You can now read a Base's RAW values — what the server actually sent — beside the rendered
  ones.** Everything a Base read gives you is *display-shaped*: a Date arrives as an epoch and
  leaves as `2025/07/01`, an Email leaves as `[billing@example.com](mailto:billing@example.com)`, a Person leaves
  as a comma-joined name. That is right for reading and wrong for computing — dedupe, diff,
  compare and chart all had to parse the Markdown back apart, and the most common way that goes
  wrong is comparing one address written as a link against the same address written plain and
  concluding they are two different vendors.

  ```python
  from larkdocio.base import read_base

  document = read_base(base_url, retain_raw=True)
  row = document.tables[0].rows[0]
  row.cells          # the rendered cells, exactly as before
  row.raw_fields     # {'Email': [{'link': 'mailto:billing@example.com', 'text': 'billing@example.com', …}], …}
  ```

  **Raw is the wire shape, byte for byte** — no key renamed, no absence coerced, no epoch turned
  into a string, no list flattened or sorted, no type changed — and it is deliberately **not** a
  typed middle form: no `datetime`, no `Decimal`, no person class, no conversion of any kind. If you want
  a `datetime`, build it from the epoch with your own timezone opinion. The per-type shapes are
  documented in the packaged guide, with a worked dedupe recipe.

  **Off by default, and off is byte-identical** — the rendered output does not move and nothing
  is retained. **It costs no extra API call** (the payload was already received; the flag only
  decides whether it is kept) **but it does cost memory: ≈7× the rendered cells**, ≈260 KB
  against ≈38 KB on a 64-row read of a real four-column table. It also reaches the snapshot the
  write engine takes: `SnapshotRecord.raw(field_name)` / `.raw_as_dict()` stand beside
  `value()` / `as_dict()`, and with retention off they **refuse** (`RawNotRetained`) rather than
  hand back an empty dict that would read as "the cells were empty". A retained read holds
  everything the API sent, including the person ids, addresses and signed attachment links the
  Markdown projection deliberately drops.

### Behavior changes you can observe

- **`except LarkDocIOError` now catches SIX MORE FAMILIES OF REFUSAL than it did. If you rely
  on one of them falling *through* a broad handler, change that handler deliberately.**
  `LarkDocIOError` has always been documented as the one base every larkdocio failure
  subclasses — *"`except LarkDocIOError` catches the whole toolkit's typed failures"* — and for
  these six it was simply not true. Each was raised as a plain `ValueError` (or, for
  `LossNotEnumerable`, a plain `Exception`) and went **straight past** `except LarkDocIOError`.
  They are inside the taxonomy now:

  | Refusal | Raised when |
  |---|---|
  | `BaseSchemaRefusal` | a Base schema request is refused locally, before any call |
  | `BaseFilterRefusal` | a Base view filter is refused locally, before any call |
  | `FieldAuthoringRefusal` — and its `UncapturedFieldPropertyError`, `UncapturedConversionError`, `RefutedFieldAuthoringError` | a field-authoring shape has no captured evidence behind it |
  | `DestructiveConsentRequired` | a plan that can lose data is applied without consent for **that** plan |
  | `LossNotEnumerable` | the cross-table loss scan could not be completed, so nothing may be deleted |
  | `RefusedError` | authored content is inexpressible, refused where it is built |

  **What this means for your code.** A broad `except LarkDocIOError` — around a whole apply, in
  a retry wrapper, in a CLI top-level handler — now **swallows these six** where before they
  propagated past it to your caller. The one to check first is `DestructiveConsentRequired`: it
  is the fence that stops a data-losing plan from being applied unread, and it is probably the
  refusal you most want to reach an operator rather than a generic "the operation failed" log.
  Either catch the specific class **before** the base clause, or re-raise it out of the broad
  one. Nothing tells you at runtime that a handler widened — this note is the notice.

  **The `ValueError` half is preserved.** Every one of these that was a `ValueError` still
  is one — `BaseSchemaRefusal`, `BaseFilterRefusal`, `FieldAuthoringRefusal` (with all three
  subclasses above), `DestructiveConsentRequired` and `RefusedError` — so an existing
  `except ValueError` loses nothing and needs no change. `LossNotEnumerable` was never a
  `ValueError` and has not been made one. **No class was renamed, no message text changed, and
  no refusal fires at a different moment**; only what these classes inherit is different.

- **No Markdown renders differently.** Most of this release is new surface, and the one
  addition to an existing read surface — the embedded-Base deep read on the document reader —
  is **opt-in and off**. The document and spreadsheet readers are untouched, their goldens are
  byte-identical, and a document's or spreadsheet's comments read exactly as before. The
  observable changes in this release are on the **failure paths and generated documents**: the
  exception hierarchy above, and the entries below.
- **A wrong-kind-of-URL refusal from `larkdocio download` prints one `Error:` line now, not a
  traceback.** Handing `download` a spreadsheet or Base URL has always been refused with a
  well-worded message — but the message arrived wrapped in a raw Python traceback under a
  *"Report the following if it is a bug"* banner. The same refusal now prints as a single
  `Error: <the same message>` line and still exits nonzero, matching every other refusal the
  command line prints; the refusal text itself is unchanged, so anything matching on the
  message keeps matching. **A genuinely unexpected crash still prints its full traceback** —
  that path survives for the class it was written for; only deliberate refusals stopped
  wearing it.
- **`DestructiveConsentRequired` now leads with the fix instead of the doctrine.** When a
  destructive Base plan is refused because its entries carry refusals, the exception message
  now begins with each offending entry's own refusal detail — the exact call to make — and the
  standing warning about cross-table blast radius rides after it, once, at the tail.
  Previously the message listed op names, told you to read the per-entry refusals yourself,
  and led with the doctrine. Every raise still says **nothing was planned and nothing was
  sent**, the doctrine text is intact, and nothing about *when* the fence fires changed — only
  the message's content and order. If you match on that message (matching on the class is
  sturdier), re-check your match.
- **The generated consumer permissions table is one row per scope now.**
  `larkdocio.permissions.consumer_permissions_markdown()` used to join several scopes' loss
  notes into one semicolon-joined cell and repeat the same ninety-word text verbatim across
  rows — accurate and unreadable, so people rewrote it by hand for their IT requests, which is
  the failure a generated table exists to prevent. It now emits **one row per (surface,
  scope)** with no repeated blobs. Nothing was dropped in the compaction: every scope's loss
  text, its verification label (including *documented-unverified*), the credential pair it
  belongs to, and the field-level-grant warning on the person-name scope are all still in the
  rendered output. The packaged guide's permissions section — and the permissions matrix in
  the dev repo (`PERMISSIONS.md`) — moved with it, byte-identical to the projection as always.
- **`download --help` now states what `-o` is.** The `-o/--output` help opens with the
  contract that was previously only implied: it is **always a directory, never a filename** —
  the generated file inside it is named from the document title, and the help now points at
  the `title_as_filename` switch (documented in `larkdocio guide`) for controlling that
  filename. Help text only; no option changed behavior.
- **Shipped docstrings stopped pointing at files the wheel does not carry.** Docstrings across
  the package cite the development repository's capability matrices heavily — the Base
  register and the document, spreadsheet and permissions matrices — and a wheel-only reader
  could not follow those pointers; one was a live relative link into nowhere. Every such
  pointer now wears the same *"in the dev repo"* label the rest of the package already uses,
  or points instead at `capabilities()` / `guide()`, which a wheel-only reader has. The broken
  link is gone, and the one module header that overstated a copied Base's computed columns
  (claiming a copied Lookup reads back populated moments after the copy) now states the
  measured truth: **settled means readable, not materialised** — a caller who needs a mirrored
  column's values must re-read. The prose you read through `help()` on some modules changed
  accordingly. A standing guard now holds every shipped docstring to this rule, so the rot
  cannot re-accumulate.
- **The Base read surface gained one operation, `get_view`.** It reads a single view *with its
  saved filter* — which the view listing does not return at all — and exists so a view write can
  be checked. It reads; it changes nothing, and it needs no scope you did not already need to
  read a Base.
- **`capabilities()` returns more than it did**, because it now reports the Base surfaces and
  the Base deep-read flag. If you assert on its exact contents (a snapshot test, a surface
  count), that assertion moves; every key that was there before is unchanged.
- **The `larkdocio --help` text and the wheel `Summary` mention Base.** No option, subcommand
  or behavior of the command line changed — it still never writes.
- **One question, one vocabulary: "can I recover from a half-applied batch?"** The apply-log
  completeness contract (`apply-log-complete`) is now stated as a house invariant — *the
  apply-log is 1:1 with the plan and every entry ends in a typed disposition, whatever
  happened* — and it is declared only where it is enforced, which today is the spreadsheet
  write engine. **The document-write position is now stated rather than left to be inferred:**
  it does not declare the invariant, because a document batch refused by the whole-document
  compare-and-swap issues **zero writes** and never partially applies, so there is nothing to
  enumerate — and no per-entry account of a half-applied batch is promised there. **Nothing
  behaves differently:** no apply path, disposition or plan structure changed, and the
  spreadsheet engine promises exactly what it promised before, word for word. Only the text of
  that one contract in `capabilities()` and the guide moved, so a snapshot assertion on its
  `summary` will need re-taking.

### Upgrade & compatibility

- **No dependency moved** — no add, no drop, no pin change. The Base surface is built on the
  already-pinned Lark SDK.
- **Reading a Base needs the `bitable:app:readonly` scope** on the app whose credentials you
  read with. Without it, the read refuses with a message naming the scope; granting it is an
  action in your Lark console, and the library never requests or widens a scope itself.
- **Nothing is renamed or removed.** Every existing symbol, flag and output is unchanged.
- **One thing to review before you upgrade: your `except` clauses.** Six refusal families that
  used to escape `except LarkDocIOError` are now caught by it — see **Behavior changes you can
  observe** above for the list and what to do about it. Their `ValueError` half is preserved, so
  `except ValueError` handlers need nothing.
- **`.env.example` now names every scope the permission registry knows** — nine, each under the
  credential pair it belongs to, where the file previously named four. If you provisioned a
  Lark app from that file alone, it under-asked: a fresh consumer following it would have
  failed every Base call (`bitable:app:readonly` to read, `bitable:app` to write), the contacts
  lookup (`directory:employee:search`), and the spreadsheet export-fidelity read
  (`drive:export`). Each scope now carries one sentence saying what it buys and what is lost
  without it. The whiteboard-export scope is listed as **a candidate, not a confirmed
  requirement** — it has never been observed to be demanded, and the file says so rather than
  telling you to grant it. **No requirement changed**; the setup file caught up with the
  registry, and a guard now holds the two together.

### Known limitations

- **A "Flow" (stage) column cannot be read.** Its schema is visible but Lark returns **no
  value for it on any read route**, so every cell in such a column renders a visible
  "unreadable" marker rather than a blank — a blank would claim the cell is empty when it may
  not be.
- **A view does not narrow the read.** Scoping by view, or hiding fields in one, changes
  nothing about what comes back, so the read renders the **table's** columns and takes no
  view argument.
- **A Base read cannot be filtered server-side yet — and the guide now says so instead of
  implying otherwise.** `search_filter()` builds a correct `records/search` request body, but
  no shipped read method accepts it — nor a `view_id`, nor a sort — so the packaged guide's
  filter recipe used to read as a working round trip. It now states the truth plainly:
  larkdocio builds this body, and **the shipped read client does not send it yet** — read the
  table and filter in Python, or send the body with your own SDK call. The saved **view**
  filter (the other filter dialect) is unaffected: setting one works and is verified by
  read-back, as above. The capability registry never advertised a read filter, and that
  silence is now guarded so a claim cannot arrive without the capability.
- **A Base's comments can be read, not written.** Writing a Base comment is refused by Lark's
  own API at every granularity, so no path to it is offered. And a Base's **sharing** stays
  out of reach on purpose: this library does not control shareability and exposes no operation
  that would.
- **A "Button" column reads as blank.** Lark does return such a column in a Base's schema, but
  it carries no value on any read route, and a button is an action rather than data — so the
  column appears with empty cells. This is a deliberate decision, not a gap waiting on the
  API.
- **Some families are reachable and deliberately unread**, each recorded with what would
  reopen it: dashboards and automations (nothing to read on any Base we could reach), the
  advanced-permission roles family (the feature gate above), and the Share dialog and
  collaborator list, which are readable and out of scope for a content read.
- **A Base embedded inside a document renders as a placeholder unless you opt in** (see the
  deep read above), and even then only the one referenced table is read — not the rest of that
  Base. There is **no CLI flag** for it: it is set on the parser in Python, and the flag row in
  `capabilities()` says so rather than naming a switch that does not exist.
- **Eight Base field types can never be given a value, whoever is asking.** Formula, Lookup,
  Flow (stage), Numbering, and the four record-metadata types (created / last-modified time and
  user) are computed or opaque — the server owns the value. The sharpest of them is Flow:
  writing to it answers *success* and changes nothing at all, with the table's revision provably
  unmoved, so anything that forwarded such a write would be reporting success for data loss.
- **A Base cell is not written in the shape it is read in, for several types.** An email address
  is written as a plain string and read back as a link with a `mailto:` prefix the server added;
  feeding that read-back shape in again is refused. A link cell is written as a bare list of
  record ids and read back as an object. A text cell is written as a string and read back as an
  array. **You cannot round-trip a Base cell by feeding a read straight back into a write**, and
  where the shapes differ the refusal happens locally rather than as a surprise from the server.
- **A location cell accepts exactly one literal: `"<longitude>,<latitude>"`.** An address string,
  or the object a read returns, is refused. Reversed coordinates are refused by Lark with an
  *internal-error* code, which is easy to misread as an outage; where the reversal is detectable
  it is refused locally instead, and where it is not — both numbers in range — it is sent as
  given.
- **A person cell takes ids, never names.** Lark itself refuses a name-shaped value, so writing a
  person means supplying an `open_id`: harvest one from a read that already names the person, or
  supply one you hold. A name can be resolved to an id **for the account owner** through the
  existing directory lookup; resolving an arbitrary other user's name is deliberately **not**
  offered — a partial or best-guess answer to "which user did you mean?" is the wrong shape
  for a write, and no lookup table stands in for one here.
- **A "single" link field does not enforce single-valuedness.** A one-way link configured as
  single-valued accepts and stores two record ids, so nothing in this library enforces a
  cardinality the server does not. If you need one value, enforce it on your side.
- **A link column can point at a table that no longer exists — and the read now says so, for
  free.** Lark keeps one of its two link kinds referentially intact and not the other. Delete a
  linked *record* and a two-way link self-heals while a one-way link keeps holding the id of a
  record that is gone. Delete the whole link-*target table* and the source column survives
  pointing at a table that no longer exists: it still carries the target's table id, its cells
  still carry record ids, a record search on that table still answers success, and **nothing
  anywhere reports an error**. Every link column a read returns therefore carries what its own
  configuration says about the table it points at — named and live, an id whose table name has
  dropped out (which is what a deleted target table reads like), or **`cannot-determine`**
  wherever the shape answers neither way. It costs **no extra call** and is not behind a flag,
  because it is read from schema the reader already fetched:

  ```python
  document = read_base(base_url_or_app_token)
  for table in document.tables:
      for column in table.dangling_link_columns:
          print(table.name, column.field_name, column.note)
  ```

  Read it for what it is: a reading of an **observed** shape, not a guarantee the API
  documents. Where the reading is ambiguous it says so rather than claiming the target is
  alive. And it is never a repair — no dangling id is deleted and no cell is rewritten to
  imitate the link kind that self-heals; rendering a broken reference honestly is the point.
- **A link cell can now be FOLLOWED to its target — opt in, and it is off by default.** A Base
  link cell has always rendered the linked records' **ids**. Ask for resolution and each linked
  record renders as its target table's **primary field** instead — the field that table's own
  schema designates, never "the first column":

  ```python
  document = read_base(base_url_or_app_token, resolve_links=True)
  print(document.link_resolution.disclosure)   # what the extra reads cost, and where
  ```

  **Off is byte-identical.** Leave it off — the default — and nothing changes: no extra API
  call is made and every link cell renders exactly the ids it always did. A new capability
  never changes an existing consumer's bytes.

  **On, it costs reads, and it tells you.** The result carries how many extra calls were made
  and which target tables were touched, because latency, a throttle budget and failure
  granularity are yours to reason about. The count follows the number of **target tables**, not
  the number of link cells: every id wanted from one table is fetched in a single batched read,
  deduplicated across cells and rows.

  **A link whose target record was deleted is normal, not an error.** Lark keeps one of its two
  link kinds referentially intact and not the other, so this happens as a matter of course and
  it never fails a read. Each id comes back typed — resolved, **dangling**, or
  **unresolvable** — and a dangling id renders a visible marker carrying the id, so a broken
  reference stays traceable instead of being silently rendered as a live one. *Unresolvable*
  means exactly that: no claim is made in either direction. Nothing is repaired — no dangling
  id is deleted and no cell is rewritten.

  **One caveat worth stating plainly:** resolution reads a **second table**, so two reads of an
  unchanged Base are byte-identical **within a run**, but a linked record renamed between runs
  legitimately changes your output — the same scoping live @mention resolution has always had.
- **Two things a two-way link does in ANOTHER table, disclosed rather than discovered.**
  Creating a two-way link column also creates its **mirror column in the target table**, named
  after the source table and the source column. Writing a two-way link cell **populates the
  reverse link over there**, done by the server, with no write to that table at all — so this
  library never performs that second write, and a plan that touches one table can still change
  what another one shows.
- **A computed column now tells you where its numbers came from.** A Lookup column is a
  **mirror of another table**, not something anyone typed, and a Markdown table that does not
  say so can be read as though it were. Every Lookup, Formula, Stage and auto column in a table
  you read now carries a reading beside the rows: what kind it is, **the type of value it
  computes**, a Formula's expression exactly as stored, and — for a Lookup — **the table it
  rolls up from**. It is derived from what the read already fetched, so it costs **no extra
  calls** and needs no extra permission.

  ```python
  for table in document.tables:
      for column in table.computed_columns:
          print(column.field_name, column.ui_type, column.rolls_up_from_table)
  ```

  **Three things it will not tell you, and the reason is this library rather than Lark.** Which
  *field* a Lookup rolls up, how it aggregates them, and the formula string stored on a Lookup
  are all returned by Lark and are **not carried through by the Lark client this library pins**
  — so they are reported as unavailable rather than quietly omitted, and each column lists them.
  **Nothing is ever computed here and no formula is ever parsed**: a computed cell shows what
  the server already computed, and a formula string is carried untouched. One consequence worth
  planning around: an aggregated Lookup arrives with **the server's own separators inside the
  cell**, so the text joins them exactly as sent — and afterwards, a comma that came from the
  aggregation cannot be told apart from a comma inside a value. That is how Lark aggregates;
  the library discloses it rather than inventing an escape Lark never used.

## [1.26.0] — 2026-08-03

### New capabilities

- **A new surface: turn a display name into an `open_id`.** The library could already turn an
  `open_id` into a name; it could not go the other way, so *"@mention Example User in that cell"*
  had no honest path to a mention, which is an **id** in the payload and never a name in a
  string.

  ```python
  from larkdocio.contacts import resolve_user

  lookup = resolve_user(name="Example User")
  if lookup.resolved:
      open_id = lookup.user.open_id
  ```

  **Exactly one, or a refusal — never a best guess.** Matching is case-insensitive and
  whitespace-normalized but otherwise **exact**, applied on your side over what the directory
  returns. There is no fuzzy distance, no phonetic matching, no ranking and no "take the top
  hit". More than one exact match refuses as ambiguous and carries the candidate
  **`open_id`s** — not their names, because a refusal that listed names would be a way to read
  the directory one query at a time.

  **"I could not look" is not "there is no such person".** Without the directory-search
  permission the call raises `LarkPermissionError`, carrying Lark's own code, message and
  console link. It is never reported as an absence, and nothing falls back to walking the
  directory.

  **Every answer says what it did not cover.** A lookup always carries a `partiality`
  disclosure. Lark can answer *success* while quietly failing on some rows, and when it does,
  those rows are never reported as resolved — you get the error codes it gave, verbatim.

  **What the endpoint actually does, measured rather than assumed.** Its own match rule is
  token-prefix and case-insensitive, and — importantly — **its reachable set can be much
  smaller than your directory**. On the tenant this was verified against it returned only the
  account owner, while name-from-id resolution worked for everyone. So read a not-found as
  *"the search did not return them"*, not as *"this person does not exist"*. Meeting rooms are
  not in the employee directory at all. Resigned employees are excluded.

  **It does not replace the plan-time mention check.** `dry_run` still proves a mention id
  exists; *"this name means this id"* and *"this id still exists"* are different facts. See
  the new guide recipe *"author a sheet cell that @mentions a teammate"*.

- **`larkdocio guide --section <name>` prints one part of the guide instead of all of it.**
  The library call `larkdocio.guide(section=…)` could already do this; the command line could
  not, so a shell user had to take the whole ~200 KB document or nothing. Now:

  ```bash
  larkdocio guide --section recipes
  larkdocio guide --section "Capability matrix" > matrix.md
  ```

  **Naming a section.** Either the heading exactly as it appears in the guide, or the slug
  derived from it — both matched case-insensitively, with surrounding whitespace ignored.

  **What comes back.** That section's own bytes, heading line included, up to the next heading
  at the same or a higher level: name a top-level section and its subsections come with it;
  name a subsection and it stops at the next one. Nothing is stripped, reflowed or paged, and
  no trailing newline is added — the same byte-fidelity contract the whole-guide output has.

  **A name that matches nothing refuses.** The message names every section there is, so a
  wrong guess is recoverable in one step. It goes to **stderr** with a non-zero exit status
  and **stdout stays empty** — `larkdocio guide --section typo > out.md` leaves `out.md`
  empty rather than half-written.

  **Omitting the option changes nothing.** `larkdocio guide` prints exactly what it printed
  before, byte for byte.

- **An opt-in projection that says which block each piece of the Markdown came from.**
  Markdown from a read tells you everything about a document except *which block said it*,
  which is fine to read and useless to edit — an agent wanting to change one paragraph had to
  reconstruct an anchor out of a verbatim quote and hope the quote was unique.
  `project_block_ids(root)` renders the same tree with one single-line
  `<!-- lark:block:<id> -->` marker before each block, and hands back the identifiers it
  emitted **with** the text:

  ```python
  from larkdocio.model import project_block_ids, strip_block_id_markers, unescape_literals

  projection = project_block_ids(tree)     # the tree parse_docx_tree returned
  projection.markdown                      # the Markdown, with markers
  projection.block_ids                     # what it emitted, in document order
  projection.to_dict()                     # JSON-serializable, both together
  ```

  **Nothing changes unless you ask.** It is off by default and there is no CLI flag; a read
  that does not call it produces byte-identical output to before.

  **It is additive, and provably so.** `strip_block_id_markers(text, ids)` returns the
  renderer's own Markdown, byte for byte. A marker line is inserted, nothing is modified —
  including inside nested lists, quotes and callouts, where the marker takes the indentation
  of the block it introduces so the surrounding structure still parses as itself.

  **It renders with literal text escaped, on purpose.** That is what stops a document whose
  own prose is `<!-- lark:block:X -->` from emitting something indistinguishable from a real
  marker. The price is that the block text you get back is *escaped*, so compare it through
  `unescape_literals` — the exact inverse, which **refuses with a detail rather than guess**
  on a sequence the escaper could not have produced. Comparing against the raw projected line
  instead makes an editor who merely normalized `99\.9` back to `99.9` look like they rewrote
  a paragraph nobody touched.

  **The identifier list is authoritative, and the strip needs it.** `strip_block_id_markers`
  removes the markers that were emitted, not every line that looks like one — stripping
  anything marker-shaped deletes a consumer's own writing about markers, which is a real
  document rather than a hypothetical one.

  **What carries no marker.** An **editable** block that renders no content (there would be
  nothing to point at), and any block inside a table cell, where a pipe-table row is a single
  line and a merged cell is raw HTML — a marker there would tear the table apart. A table is
  marked at the table block itself.

- **Opaque markers, and the conservation contract: the projection now says which blocks you
  may edit and which it only conserves.** A marker alone says *what* a piece of Markdown came
  from; it does not say whether changing that piece can mean anything. A block whose Markdown
  the authoring dialect cannot compile back — an image, a synced block, an embed, a
  whiteboard, a type this release has never heard of — and a block the reader renders in a
  *different shape* than its own — a table (a pipe grid, or HTML when merged), a mermaid
  add-on (a fenced source listing) — now carries the opaque form instead:

  ```
  <!-- lark:block:doxcnAbC123 opaque=image -->
  ![](boxedHoM834)
  ```

  and comes back in `.opaque_block_ids` alongside `.block_ids`. The content still shows, so
  the projection stays readable — opaque means "do not reconcile me", not "hide me" — and the
  distinction is a named attribute plus a list on the result, never something to infer.

  **The contract.** An opaque-marked block is **left exactly alone** by any reconciliation: it
  is **not edited**, **not deleted**, and **not re-created** — even if the edited projection
  **omits it entirely**. Conservation is the default posture and destruction is never
  inferred: the absence of a block from edited Markdown is evidence about the Markdown, not an
  instruction about the document. Without this, the first prose edit an agent makes could
  silently delete a diagram.

  **A table is opaque as a whole**, and its cells carry no markers of their own, so an edited
  cell has no anchor. The supported route for changing one is unchanged: the **cell-patch**
  path in `larkdocio.write`, which addresses a cell directly by table anchor, row key and
  column.

  **Which types are on which side is derived, not listed.** The answer is a live join of the
  reader's handler registry, the writer's creatable set and the per-type read-lossiness the
  wheel already ships, so the editable and opaque sets are complementary and exhaustive and a
  newly supported block type cannot fall into an unspecified middle. A type with no handler is
  conserved under the reader's own unknown-block identity, `unknown-block-type-N`. Ask
  `capabilities()["surfaces"]["docx-read"]["block_projection_support"]` for the per-type answer
  and the contract in full; `/BLOCKS.md` carries the same column for maintainers.

- **Hand an edited projection back and get a typed plan of what changed —
  `larkdocio.write.reconcile`.** The projection told you which block each piece of Markdown
  came from. This is the other half: edit that Markdown however you like, hand the whole
  thing back, and get a frozen, JSON-serializable `ReconciliationPlan` saying per block
  whether it is **unchanged**, **edited**, **inserted**, **deleted** or **conserved-opaque** —
  with the pre-image and post-image for every edit. It is **offline**: no network call, no
  request, nothing applied. Read it first.

  ```python
  from larkdocio.model import project_block_ids
  from larkdocio.write import reconcile, AbsentBlockDisposition

  projection = project_block_ids(tree)      # the tree parse_docx_tree returned
  plan = reconcile(projection, edited_markdown)
  plan.ok, plan.change_count, plan.touched_block_ids
  for entry in plan.changes:
      entry.state, entry.block_id, entry.before, entry.after
  ```

  **What it will not do, and why.** A marker resolves only against the identifiers the
  projection itself emitted — exactly one, or the whole reconciliation refuses. There is no
  content-based fallback, so an identifier that was never emitted refuses as
  `marker-invented` whether an editor invented it or your own prose happens to be
  marker-shaped, and an identifier that appears twice refuses rather than picking one. A
  block whose marker did **not** come back is **not** deleted: absence refuses by default,
  naming the block and quoting the text it still has, and deletes only when you pass
  `absent=AbsentBlockDisposition.DELETE`. Moving a block refuses (a move is not expressible,
  and faking it as delete+insert would destroy the block's identifier and everything anchored
  to it), and so does editing a block into a different type — the refusal names the working
  route, delete + insert as two commits.

  **Conservation is enforced, not just promised.** An opaque block — an image, a table, an
  embed, a type this release has never heard of — is `conserved-opaque` under **either**
  disposition, even if your edited Markdown dropped it entirely or changed its visible text.
  Nothing the plan would compile names it, and `plan.touched_block_ids` is how you check
  without taking anyone's word for it.

  **Added content is an insert, anchored to the block above it.** Content you write inside a
  marker's segment is planned as an insert anchored to that surviving marker — on the side
  you actually wrote it — or to the document root when it arrives ahead of the first marker.
  An insert is never anchored to another insert, so the batch never depends on its own
  writes.

  **Comparison happens after decoding.** The projection escapes literal text, so an editor
  that only normalized `99\.9` back to `99.9` changed nothing, and the plan says so: zero
  changes. `capabilities()["surfaces"]["docx-write"]["reconciliation"]` carries the plan's
  whole vocabulary — every state, both dispositions, every refusal reason, and the contract
  in full.

- **Turn that plan into requests the engine already applies —
  `larkdocio.write.compile_reconciliation`.** The plan says what changed; this compiles it
  into the write engine's **own** `EditRequest` / `InsertRequest` / `DeleteRequest`, each
  anchored by block id, and hands them to the **same** dry-run gate every other write goes
  through. There is no new request type, no new apply path and no second gate to learn.

  ```python
  from larkdocio.model import project_block_ids
  from larkdocio.write import compile_reconciliation, reconcile, dry_run, apply

  projection = project_block_ids(tree)
  plan = reconcile(projection, edited_markdown)
  requests = compile_reconciliation(plan, projection)
  preview = dry_run(requests, tree, document_revision_id=document.revision_id)
  log = apply(preview, client, document_id)      # an ordinary apply-log
  ```

  **Pass the revision and drift refuses everything.** `document_revision_id` is the shipped
  whole-document compare-and-swap: if the document moved between your plan and your apply, the
  **entire** batch refuses with **zero** writes and you re-download and re-plan. Nothing is
  half-applied, and there is no second staleness setting on the compiler to get out of step
  with it.

  **Nothing in a batch depends on the batch.** Every anchor names a block the projection
  itself emitted, so no request can point at content the same batch creates — the rule the
  engine has always had, honored here by construction rather than by hoping. Content you added
  in one place becomes **one** insert carrying several blocks, which is also what lets the
  engine's own batching split it exactly as it splits any other authored content.

  **Markers never reach your document, and the edit path is the one that needed the work.**
  An insert body cannot carry a marker — the authoring compiler refuses marker-bearing
  Markdown outright. An **edit** replacement is a plain string nobody parses, and Lark stores
  marker-shaped text **verbatim**, so text that would put an identity marker for one of *your
  document's own blocks* into the document is **refused** — never written, and never silently
  stripped either. That holds **anywhere in the text**: on a line of its own, or in the middle
  of a sentence, in what you wrote or in its escaped form. Prose that merely *looks* like a
  marker but names no block in this document is your content and is carried through untouched,
  wherever it sits.

  **Nothing else is written.** An unchanged block and a conserved-opaque block compile to
  nothing at all — not to a rewrite with the same value — so a reconciliation that changes one
  paragraph of a hundred issues exactly one request, and a reconciliation that changes nothing
  makes **zero** API calls. An edit that is really a structural change (turning a paragraph
  into a list) refuses and names the two-commit route instead of approximating it.

  **Proven against real documents, not only fixtures.** The four load-bearing guarantees are
  re-proved end to end against real Lark documents, each provisioned and destroyed for the
  purpose: the surgical single-patch edit (everything else byte-identical, then restored to a
  byte-identical baseline), conservation under omission — both shapes, including the
  zero-write `conserved-block-re-created` refusal — the zero-write `STALE_DOCUMENT` refusal
  with its re-download-and-re-plan recovery, and the no-marker-reaches-your-document scan of
  the re-read document in **both** representations. The guide ships the whole chain as
  **§ "Recipe: round-trip an edit through the block-identity projection"**, copy-pasteable and
  verified by compose-equivalence rather than string equality.

- **When a reconciliation refuses, it now tells you exactly which way it went wrong — and
  what to do about it.** Every way an identity marker can be lost on the round trip has its
  own named reason instead of one catch-all, and every refusal names the block it is about
  and a next step that actually succeeds:

  | What happened | What you get back |
  | --- | --- |
  | The marker is gone but the block's text plainly came back | `marker-dropped` — put the marker line back above that text |
  | The marker **and** the text are both gone | `marker-absent` — restore both, or re-run with the deletion disposition to mean it |
  | A marker came back sitting on **another** block's text | `marker-relocated` — both blocks named |
  | A marker-**shaped** line that is not the exact form | `marker-mangled` — the bytes and the canonical form quoted |
  | A marker came back with nothing under it | `marker-orphaned` — an emptied block is a deletion said ambiguously |
  | The same marker appears twice | `marker-duplicated` — both places named |
  | A marker naming no block of this document | `marker-invented` |

  **Nothing is repaired by guessing.** A marker-shaped line that is not byte-exact is never
  normalized into the marker it resembles — it may be your own content that merely looks like
  one. A dropped marker is never re-attached to text by resemblance, because an identifier
  cannot be recovered from what a block happens to say and a wrong re-attachment rewrites the
  wrong block. Two copies of one marker are never resolved by choosing an occurrence.

  **And a refusal set that refuses too much would be the worse bug**, so the opposite case is
  pinned just as hard: a clean edit of one paragraph plans exactly that one edit and refuses
  nothing, and an untouched projection plans nothing at all.

- **Fixed (could corrupt a document): a conserved block could be planned twice.** A table,
  diagram, image or other block the reconciler **conserves** is never edited, deleted or
  re-created. But if your editor dropped that block's identity marker while keeping the block
  itself, the plan reported it conserved **and** planned its content as a brand-new
  insert — so applying it left the document holding the block **twice** while telling you it
  had been conserved. That plan now **refuses**, naming the block, and the recovery is to put
  the block's own marker line back above its content. The added content is **not** discarded
  to make the problem go away: text sitting beside a conserved block may be a real addition of
  yours. If the block's marker is where it belongs, a second copy of its content beside it is
  still an ordinary insert — the refusal fires only for the ambiguous case it exists for.

### Behavior changes you can observe

- **The metadata-table routing notice is now logged at `WARNING` instead of `INFO`.** When a
  downloaded document carries all three metadata table rows, the reader writes the file into a
  subpath of `<your -o>` derived from their values rather than into `-o` itself, and says so
  with one log record naming the derived path. That
  record used to be emitted at `INFO`, which the command line prints but an in-process caller
  who has attached no handler never sees — Python's fallback handler only emits `WARNING` and
  above. So the one thing the library does that changes **where your file lands** was silent
  for library callers, who would write to `./out/` and find nothing there. The record is now
  emitted at `WARNING`.

  **What to change.** If you configured nothing, you now see one line per routed document
  where before there was none; that line is the notice, it tells you the real output
  directory, and — like every larkdocio log line — it goes to **stderr**, never to stdout, so
  it cannot contaminate output you are piping. If you filter, route or assert on the `larkdocio` logger, move this record
  from your `INFO` handling to your `WARNING` handling — and if you would rather not see it,
  either raise your handler's level or turn routing off with its output-config key, which is
  unchanged.

  **Nothing else about routing moved.** The message text is byte-identical, and the detection
  rows, the derived subpath, the lower-cased path normalization, the three-row requirement,
  the output filename and the emitted Markdown are all exactly as before. A document that is
  **not** routed still logs nothing at all, at any level.

- **The timestamp in the output filename is now UTC, not your machine's local clock.** With
  `title_as_filename` at its default the file is named `[YYYY-MM-DD_HHMM]_<title>.md`, and
  that stamp used to be read off the local clock — so the same document, downloaded at the
  same moment on two machines in different time zones, landed under two different names. It
  is now taken in UTC, which makes the name a function of the instant alone.

  **The rendered shape is unchanged.** The format is still `[YYYY-MM-DD_HHMM]_` — no `Z`, no
  offset, no seconds appended — so any glob or pattern you match filenames with keeps working
  exactly as it did.

  **What to expect.** A filename produced after upgrading can differ from one produced before
  by your machine's UTC offset; if you key a cache, a test fixture or a check on an exact
  filename produced earlier, expect that one-time shift. Nothing about the file's **content**
  moved — the stamp never appears inside the Markdown — and `title_as_filename: false`
  remains the way to get `<document token>.md` with no stamp at all.

### Upgrade & compatibility

- Drop-in. No return shape or file content changes, the one new CLI option is opt-in, and the
  new public symbols are additions — omit them and every command behaves exactly as before.
  What can be observed: the level of one log record, and the UTC basis of the output
  filename's timestamp.
- **No dependency was added, dropped, or re-pinned.**

### Known limitations

- **The round trip's supported shape is a WHOLE DOCUMENT, in and out — this will shape your
  integration.** You hand the editor the whole projection and take the whole edited document
  back. **A patch, a unified diff, or an edited fragment is not supported and is not
  tested** — nothing accepts one, and a fragment describes a document that lost every block
  the fragment left out. If your editor emits a patch, apply it to the projection yourself
  and pass the complete result. The same sentence is in
  `capabilities()["surfaces"]["docx-write"]["reconciliation"]["contract"]`, so a machine can
  read it too.
- **Name-to-id lookup reaches what the directory search returns, which can be much smaller
  than your directory.** On the tenant this release was verified against, the search returned
  only the account owner while id-to-name resolution worked for everyone — so treat a
  not-found as "the search did not return them", never "this person does not exist". The
  lookup's own disclosure says the same thing programmatically.

## [1.25.0] — 2026-08-01

### New capabilities

None.

### Behavior changes you can observe

- **A spreadsheet style plan's two disclosure notes renamed their `leg` field to
  `verified_by`.** Plan a cell-style or border write and the entry carries up to two
  disclosures: `style-verification-cost` (proving this style landed rides the workbook-export
  leg, and here is what that costs) and `style-border-not-verifiable` (that leg carries no
  border information, so the border in this write is not checked). Both named the verifying
  leg under the key `leg` — while every spreadsheet **apply-log** entry has always named the
  same thing under `verified_by`. One fact under two spellings on one surface is a trap for
  anyone reading the disclosures programmatically, and the plan-side and log-side halves of a
  single write disagreeing on the key is the worst version of it. The notes now use
  `verified_by`, so the two halves match.

  **What to change: read `note["verified_by"]` where you read `note["leg"]`.** Everything else
  about those notes is byte-identical — the value is still `"xlsx-export-style-leg"`, the
  prose is unchanged, and the field sits in the same position with the same neighbours
  (`kind`, `scope`, `ranges`, `sheet_id`, `border_ranges`, `note`). Nothing else in a plan or
  an apply log moved.

  **There is deliberately no compatibility shim and no dual key.** The old spelling shipped in
  1.24.0, cut the same day the style write itself first landed, so the window in which anyone
  could have adopted it is one release wide; carrying both keys forward would preserve exactly
  the two-spellings problem the rename removes.

### Upgrade & compatibility

- **No dependency was added, dropped, or moved** — the runtime dependency set is byte-identical
  to the previous release.
- **One field rename to check for, in one place:** an entry of
  `plan.entries[i].preview_notes` whose `kind` is `style-verification-cost` or
  `style-border-not-verifiable`. If you never read that field, nothing in this release affects
  you. No public symbol was added, renamed or removed; no apply-log field moved; no refusal
  reason or `outcome` value changed; and the number and order of API calls every spreadsheet
  write makes is unchanged.

### Known limitations

- **Borders still write but cannot be read back** — which is why the second of the two renamed
  notes exists at all. The workbook-export leg that verifies fills, fonts and number formats
  carries no border information, so a border write is confirmed but not verified. The note
  states that gap in the same breath as it names the leg, now under the new key.

## [1.24.0] — 2026-08-01

### New capabilities

- **A new sheets apply-log refusal reason, `permission-denied`.** It is the disposition a
  spreadsheet-write entry gets when Lark refuses the call because your app lacks a required
  **scope**, and it is `systemic`: outcome `refused`, nothing landed, and the batch **halts**.
  Its `detail` relays Lark's own answer rather than a paraphrase — the exact missing scope(s),
  the verbatim `code`/`msg`, the console link when Lark supplies one, and **which credential
  pair** made the call — plus the repair, which is a grant in the Lark console followed by a
  re-`dry_run` and an apply of the remainder. No scope string is ever invented: a refusal that
  arrives without a structured denial record says so instead of filling the gap. Read it the way
  you read every other reason, from `ApplyLog`; the disposition table in the packaged guide has
  its row.
- **Spreadsheet tabs can now be reordered, retitled, and hidden or shown.** Three new
  plan-gated requests — `ReorderTab`, `RetitleTab` and `SetTabVisibility` — go through the
  same gated engine as every other spreadsheet write (`dry_run` → `apply`, staleness-guarded),
  and the apply step verifies the result through the same tab query that already proves adds,
  copies and deletes. Two facts a caller should know are stated by the plan itself rather than
  left to be discovered: **hiding a tab hides it only in the UI** — the data stays fully
  readable through this library and the API, so hiding is presentation, not protection — and
  **retitling a tab breaks any cached title→sheet-id mapping you keep** (the sheet id itself
  never changes; a join keyed on the title goes stale the moment the title moves). The
  packaged guide has the recipe.
- **Cell styling is now a first-class write.** A `StyleWriteRequest` carries a typed
  `CellStyle` — fill (background color), bold / italic / font size, number format, and cell
  borders (`border_type` / `border_color`) — through the same plan-gated engine, over one
  range or many ranges in a **single** API call. Refusals are typed and cost zero API calls:
  a font size outside Lark's accepted 9–36 band is refused at construction quoting Lark's own
  rule, a border color with no border type is refused, and an unknown border type names the
  accepted set. A style write also discloses its verification cost up front: proving a style
  landed rides the workbook-export leg, which is slower than a value read, and the plan says
  so before you commit.
- **A typed answer to "did my number land?".** Lark normalizes whole-valued floats on
  read-back — write `18.0` and the sheet hands back `18` — so a naive written-equals-read
  comparison reports a phantom diff. The new `larkdocio.sheets.verify` module ships
  `values_equivalent`, `value_differences` and `cells_equivalent`: typed numeric equivalence
  (an int and a float that are the same number match; `22.5` must still be `22.5`; the *text*
  `"18.0"` is not the number 18), with `value_differences` naming each mismatching cell. This
  is equivalence under a documented normalization, deliberately **not** a tolerance — nothing
  is "close enough".

### Behavior changes you can observe

- **A spreadsheet-write batch now STOPS on a scope denial instead of trying every remaining
  entry.** Before this release a denial was classified `entry-scoped` and reported as
  `api-error`, so a 20-entry plan issued **20** throttled write calls against a permission that
  cannot appear between one entry and the next, and the log read as twenty unrelated failures.
  A missing grant would refuse every remaining entry identically, so it is now treated as what
  it is: one condition, stated once. **What you observe changes in four ways** — (1) the failing
  entry's reason is `permission-denied`, not `api-error`; (2) the entries after it are
  `not-attempted`, each naming the halt position **and** `permission-denied`, so nothing is
  silently dropped; (3) `ApplyLog.halt` / `.halted` are set, with `landed: "no"`; and (4) the
  batch spends **one** write call rather than one per entry. The apply-log is still exactly
  1:1 with the plan, in plan order, and **no exception escapes `apply()`** — the halt is a
  logged disposition, never a raise. **If you were counting on the old shape**, the recovery is
  the same work in a different order: grant the scope, then `dry_run` + `apply` the remainder.
  There is deliberately **no option to restore the old behavior** — a second batch doctrine to
  reason about is worse than the calls it would save.
- **Nothing else about the disposition table moved.** An ordinary rejection Lark answers about
  one entry (the `id not found` class) is still `api-error`, still entry-scoped, and its batch
  still continues; a rate limit is still `rate-limited`; a failure below Lark is still
  `transport-failure`; a locally invalid request is still `invalid-request`. And a denial raised
  by a step that runs **after** the write already returned is still `unverified-write` /
  `applied-unverified` with `landed: "yes"` — the change is on the spreadsheet, and that fact
  outranks why the following call failed. The `outcome` vocabulary is unchanged at six values;
  the new reason reuses `refused`.
- **The two undocumented merge variants are now refused before any call is made.** The merge
  request's type field was a free string, so `MERGE_ROWS` and `MERGE_COLUMNS` could reach a
  **destructive** operation whose loss preview was written for `MERGE_ALL` — and probing the
  live behavior proved the preview **mis-discloses** on the variants: they can land several
  merge regions at once, and a cell the preview named as lost can survive. Until each
  variant's loss model is characterized and previewed truthfully, constructing a merge with
  any type other than `MERGE_ALL` raises a typed refusal naming the accepted set — catchable
  both as this library's configuration error and as a plain `ValueError` — and costs zero API
  calls. `MERGE_ALL` merges are unchanged.

### Upgrade & compatibility

- **No dependency was added, dropped, or moved** — the runtime dependency set is byte-identical
  to the previous release.
- **One behavioral break to check for, and it is narrow:** code that branches on the string
  `"api-error"` to detect a scope denial, or that assumes a spreadsheet batch always attempts
  every entry, will need the `permission-denied` reason and the `halt` / `not-attempted` shape
  instead. Both were already part of the apply-log contract; only which failures reach them
  changed. No public symbol was renamed or removed, no existing reason string changed, and
  document (non-spreadsheet) writes are untouched — they already refused a whole batch with
  zero writes.
- **A second narrow break, in the same spirit:** a merge constructed with
  `merge_type="MERGE_ROWS"` or `"MERGE_COLUMNS"` now refuses at construction instead of
  landing a merge whose loss preview could not be trusted. Re-express the intent as
  `MERGE_ALL` merges over the exact ranges you mean. Code that only ever used `MERGE_ALL` —
  the only documented value — is unaffected.

### Known limitations

- **The denial is discovered at apply time, not at plan time.** `dry_run` does not pre-check
  spreadsheet write scopes, and the advisory permission pre-check cannot supply them: a write
  scope cannot be proved by any read, and the scope requirements for spreadsheet endpoints are
  not established, so a pre-check verdict for them would be `unknown` rather than a clean bill
  of health. Inventing a scope name to fill that gap is worse than the gap. So the first entry
  of a batch is what discovers a missing grant — it now costs one call to discover instead of
  one per entry.
- **A denial that arrives without a structured record names no scope.** Lark's answer carries
  the scope in the great majority of cases; where it does not, the `detail` says so and relays
  the code and message, which are the whole of what Lark said.
- **Word-wrap cannot be written, and that is Lark's behavior, not a missing knob.** Every
  plausible wrap field was probed live: the endpoint answers success and stores nothing —
  indistinguishable from a no-op — and no error body exists to relay. `CellStyle` therefore
  has no wrap field, and `capabilities()` lists word-wrap under `style_fields_not_writable`,
  so the absence is machine-readable rather than a surprise.
- **Borders write, but cannot be read back.** The workbook-export leg that verifies fills,
  fonts and number formats carries no border information, so a border write is verified as
  accepted rather than round-tripped, and the plan carries a note saying exactly that for the
  bordered ranges.
- **Dropdown option colors write but do not read back.** Colors are written positionally with
  the rule; what the API returns on a read uses a different shape this library does not yet
  decode, so a written color cannot currently be confirmed by reading the rule back.

## [1.23.0] — 2026-07-31

### New capabilities

- **`larkdocio guide` — the packaged consumer guide from a shell, with no Python.** It writes
  exactly what `larkdocio.guide()` returns to stdout: the same bytes, read out of the installed
  package, so it needs no network, no credentials and no source tree. It takes no options, and
  the output is the document's own bytes — no pager, no colorization, no reflow and no added
  trailing newline — so `larkdocio guide > guide.md` and piping it into another program are both
  exactly what it is for.
- **`larkdocio.guide(section=...)` — one section of the packaged guide instead of the whole
  document — and `larkdocio.guide_sections()`, the index of what you can ask for.** The guide is
  over 200 KB as one string, so a caller that wants a single recipe no longer has to hold all of
  it. Sections are the document's **own headings** (`##` and `###`), read out of the packaged
  file on every call, so there is no separate list of section names that could fall behind it.
  Name one either by its heading exactly as it appears or by the slug derived from it (backticks
  dropped, lower-cased, every run of other characters collapsed to `-`), and both are matched
  **case-insensitively** with surrounding spaces ignored — so a heading that is later only
  re-cased or re-punctuated keeps answering to the name you already wrote down. What comes back
  is the heading line plus that section's text through the character before the next heading of
  the same or higher level, verbatim: a `##` name therefore includes its `###` children, and a
  `###` name stops at the next `###` or the next `##`. **A name the document has no heading for
  raises `ValueError` whose message names every section it does have**, so recovering from a
  wrong guess costs no second call. `guide_sections()` returns one row per heading — `heading`,
  `slug`, `level`, names only and never section text — and the same rows now appear on
  `capabilities()["docs"]["guide()"]["sections"]`, a new **optional** field on that one row which
  leaves every other row's shape exactly as it was. `guide()` with no argument is
  **byte-identical** to before, and the guide documents the feature itself under *Reading the
  shipped documents programmatically*.
- **`larkdocio.preflight` and `larkdocio.check_permissions` are now exported from the top
  level.** The advisory permission pre-check already existed and was already described, but it
  was absent from `larkdocio.__all__`, so `dir(larkdocio)`, `help(larkdocio)` and
  `from larkdocio import *` all failed to mention it and finding it took a full-text search of
  the guide. Both names now appear there, and the guide's credentials section says where to look.
  Nothing about the check changed: it is still optional and advisory, it never mutates, and no
  operation requires it.
- **`larkdocio.capabilities()` gained a top-level `entry_points` key** — one row per symbol
  `larkdocio.__all__` exports, each with a one-line summary and **what calling it costs in API
  calls** (every entry point but the pre-check costs none). It is the callable-side companion to
  the existing `docs` index, which continues to list packaged **documents** only. Existing keys
  are unchanged.
- **The whole `--config` schema is now readable from an installed wheel.** The packaged guide
  carries an *Output configuration* section listing all seven `output` keys — `image_dir`,
  `title_as_filename`, `use_html_tags`, `skip_img_download`, the routing off-switch,
  `download_attachments`, `resolve_mentions` — with each key's default, what it does, and the
  whole file at its defaults (which is exactly what the package ships, so omitting `--config`
  and passing that file are the same run). The table is **generated from the settings object
  itself**, so a default printed there is the default the code holds; the same generated text is
  the repository's CLI-contract copy, so the two cannot disagree. Previously the schema existed
  only in a repository file a vendored wheel does not carry, and the front door linked to it
  twice — including from the `--config` option itself. Those pointers now name the packaged
  guide. **No key, default or behavior changed.**
- **`larkdocio.capabilities` gained two module-level helpers for that schema** —
  `config_schema()` (one row per `output` key: its name, its real default, what it does) and
  `config_schema_markdown()` (the generated Markdown region the documents carry). They read the
  reader's own settings object, so a key added later cannot be described two different ways.
- **`larkdocio mermaid` — compile a diagram spec to Mermaid source from a shell, with no
  Python.** A spec (JSON) from a file or `-` for stdin goes in; Lark-safe Mermaid source comes
  out on stdout, or into a file with `-o`/`--output`. It is **pure** — no credentials, no
  network, no document is touched, nothing leaves the machine — so a shell-driven or
  agent-driven caller reaches it with nothing configured, and `cat spec.json | larkdocio
  mermaid --flowchart - > diagram.mmd` is the whole workflow. Two things it deliberately does:
  the **diagram kind is stated, never guessed** (`--flowchart`, `--sequence`, or a `"kind"` key
  in the spec — stating neither refuses, and a flag contradicting the key refuses rather than
  picking a winner; which keys a spec happens to carry is never consulted), and a spec the
  renderer could not draw **refuses** with the construct and its value named on stderr, a
  non-zero exit status, an empty stdout, and **no output file** — so a refusal cannot leave a
  half-finished `.mmd` behind. It compiles only: it never writes a diagram into a Lark
  document, which remains the plan-gated library call in the packaged guide's mermaid recipe.

### Behavior changes you can observe

- **Everything the command line logs now goes to stderr instead of stdout.** This is a
  separate, observable change from the new subcommand above, and it affects **`larkdocio
  download`**: its progress lines (the ones naming the document, the image count and where the
  file landed) used to arrive on **stdout** and now arrive on **stderr**. If you were reading
  them off stdout, add `2>&1` to get the old single-stream view; if you were capturing stdout
  expecting only those lines, you now get nothing there. **Nothing else about `download`
  changed** — the same lines, in the same order, with the same text, and the files it writes to
  disk are untouched. The reason is the rule the new `mermaid` subcommand needs and the whole
  command line now follows: **stdout carries a command's output, stderr carries everything said
  about the run.** Without it, a diagram large enough to earn an advisory warning would have
  emitted that warning *into* the compiled source on stdout, so `> diagram.mmd` would have
  produced a file that is not valid Mermaid.

- **`-o`'s help text now tells you what `-o` actually does — the behavior it describes is
  unchanged and has been there for releases.** `-o` is the **root** the output is written
  under, not always the output directory itself: when a downloaded document's converted body
  carries the three metadata table rows, the file is written into a subpath derived from their
  values beneath `-o`, and the filename is the document title with a
  local-time `[YYYY-MM-DD_HHMM]_` stamp welded on. The option's help had said only *"Specify the
  output directory for the markdown files"*, which is why this read as a surprise. **Nothing
  about the routing, the normalization or the filenames changed in this release** — only what
  the help string and the documents say about them. The full rule is now in the packaged guide
  under its *Where the file lands* chapter, including the parts that cost real
  time: **all three** rows are required (a document matching two of the three is not routed at
  all, and the notice that would have told you is logged at a level an in-process caller does
  not see), each value is normalized and then **lower-cased** so the **document's own spelling
  wins** (a document saying `Example Value` routes into `example_value` and will not meet a tree
  spelling it `sample_value`), values are truncated at 100 characters, an empty one becomes
  `untitled`, the stamp exists only while `title_as_filename` is true — set it `false` and the
  filename is `<document token>.md` with no stamp at all — and routing is turned off with a
  config key, for which there is deliberately **no command-line flag**. And: do
  **not** pre-build the derived path yourself; pass the root, or the derived
  path nests twice.

- **`larkdocio --help` describes the library the library actually is.** The first screen said
  *"Download lark document to markdown file"* — accurate for the first release and wrong for
  twenty-two of them. It now names the surfaces this install reports (the ids
  `larkdocio.capabilities()` reports, listed on the page), points at `larkdocio guide` and
  `larkdocio.capabilities()`, and **states plainly that the command line is read-only**: it
  downloads and converts, it never writes to a Lark document or spreadsheet, and writing stays a
  library call whose plan you approve. **No existing command, argument, flag or default changed**
  — `download` and `config` behave exactly as before.

- **`larkdocio.mermaid` now REFUSES every off-dialect spec instead of quietly compiling a
  different diagram. This is the one change in this release that can break a working call.**
  Until now the compilers dropped and substituted content and returned a clean string: an edge
  or message naming an identifier nothing declared was **omitted** (behind a log line a library
  caller has no handler for), and an unknown `shape`, an unknown `direction`, a `label` on an
  `invisible` edge, an unusable node, participant or subgraph identifier, a subgraph member
  nothing defined, a `length` outside the sanctioned range or not a whole number, an unknown
  edge `style`, an unknown message `style`, and an arrow outside the accepted literals were all
  **silently replaced or discarded with no signal at all**. Each of those now raises
  `LarkConfigError` — the same type an unknown `theme` has always raised — with a detail that
  names the offending construct **and its value**, and enumerates the valid set wherever the set
  is closed. **Nothing is produced when a spec is refused**, so a wrong-but-plausible diagram
  can no longer reach a document unnoticed.
  - **What this means for you:** a spec that relied on a silent fallback **now raises where it
    used to return source**. The migration is to fix the spec — the refusal message says what to
    fix and what the accepted values are. **There is no flag and no lenient mode**, deliberately:
    a leniency switch would keep the wrong behavior reachable, and every caller who passed it
    would re-create exactly this problem.
  - **What did NOT change:** a **valid** spec compiles to **byte-identical** source — the whole
    historical spec vocabulary (shapes and their aliases, subgraphs, every edge style, the
    `length` and `invisible` layout levers, bare-string participants, the older `type` /
    `message` keys) is pinned byte for byte against the output of the previous release. Keys you
    leave out are not off-dialect: a node with no `shape`, an edge or message with no `style`,
    and an edge with no `length` still get their documented defaults. And the **two advisory
    rules still only warn and then compile** — diagram size past the complexity ceiling, and a
    wide horizontal layout — because those are judgments about a valid diagram, not dialect
    errors. `rules()` marks every rule enforced or advisory, and the packaged guide's diagram
    recipe now states which classes refuse.
- **The @mention resolver's one diagnostic line now fires in cases that used to be silent.** When
  a mention lookup succeeds but still leaves mentions unresolved, the reader logs one `info` line
  saying which way it fell short. That line's condition used to be a comparison of three counts —
  how many ids were asked about, how many users came back, how many carried a readable name — and
  three counts cannot express *which* ids are missing. So an answer that returned an id nobody
  asked about balanced the books for an id it omitted, and the run went silent on exactly the
  case the line exists to report. The condition is now the set difference between the ids asked
  about and the ids resolved, which also stops a repeated input id being counted as a missing one
  and stops a record that arrives with no user id being blamed on your contacts data range — it
  gets its own clause instead, because the directory did answer. **What did NOT change:** the
  names that resolve, the `{id: name}` result, the raw `@open_id` fallback for anything
  unresolved, and therefore the rendered Markdown — a document converts to the same bytes. The
  line is still `info`, still fires **at most once per run** however many mentions a document
  carries, and still names the missing field-scope **class** rather than a scope string. This is
  a widening of what gets disclosed, not a fix to what gets read.
- **The Sheets capability matrix no longer says comment creation is unavailable everywhere.** The
  shipped matrix's comments row ended with a claim that comment creation was not a capability of
  this library at any granularity. That stopped being true when whole-document comment creation
  shipped for **docx**. Corrected to the boundary that actually holds: creation is **not**
  available **on a spreadsheet** at any granularity — the server itself refuses it, naming its own
  `[doc,docx]` enum — while whole-document creation on a docx is supported, and **anchored**
  creation exists on no surface. No behavior moved; a documented capability claim did.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned.**
- **No new scope is required** — the mermaid compilers are pure and reach no API at all.
- The refusals are compile-time and client-free, so they are reachable in a unit test with no
  credentials: the cheapest way to check your own specs against this release is to compile them
  offline before you upgrade the write path.

### Known limitations

- The compilers still cannot tell you how a diagram **draws** once it reaches a document — that
  needs a real render. They enforce the dialect, not legibility.
- `escape_label` still **rewrites** rather than refuses for label text: markup is stripped and a
  double quote is downgraded to a single one. That is deliberate and documented — it applies to
  human-readable text, keeps the meaning, and cannot produce a structurally wrong diagram.

## [1.22.0] — 2026-07-30

### New capabilities

- **Mermaid diagrams, authorable.** `NewBlock.mermaid(source, theme=None)` composes a
  mermaid diagram into a docx document through the standard write handshake, emitting the
  same record shape a hand-inserted diagram carries. The source is your compiled mermaid
  text; a bundled compiler ships alongside (no new dependency). An empty source is refused
  (Lark stores it as an invisible block) and a theme outside the known whitelist is refused
  (the server validates nothing inside the record, so the client-side check is the only
  guard there is). Changing a diagram is delete + re-create — the documented path, with the
  removal snapshot carrying the full diagram so the step is reversible; the block id changes
  and the plan says so.
- **Whole-document comments: create and remove.** `larkdocio.write` gains two plan-gated
  ops: leave a whole-document comment on a docx document, and remove a comment thread the
  app itself authored. Anchored (passage-level) creation is refused honestly — Lark's create
  route silently drops anchor fields, so instead of a comment that lands somewhere you did
  not ask for, you get a typed plan-time refusal. Removal is ownership-scoped: a thread with
  any human author is refused with Lark's own denial body, and the ownership check runs
  before the first delete, so a thread is never half-removed by design. The created comment
  is authored by your app's bot identity; the plan discloses this before you apply.
- **Sheets: freeze panes.** Freeze or unfreeze rows and columns, with the write's semantics
  pinned to live-probed behavior: the update is a patch, so freezing rows can never silently
  unfreeze a frozen column; `unfreeze()` names both axes deliberately. Out-of-range counts
  are refused at plan time — before any API call — and the boundary follows the server's
  actual behavior, not its error message (which misstates its own limit). The frozen state
  is now also readable, and the apply log records the observed counts after every freeze.
- **Sheets: row and column dimension properties.** Set row heights and column widths, hide
  and show rows and columns. Ranges use the spreadsheet's own numbering (first row is 1,
  bounds inclusive) — characterized from live probes, stated in every docstring. Hiding is
  disclosed in the plan as a visibility event, and the result is verified through the
  export-based read leg because the metainfo endpoints do not carry dimension state.
- **Permissions are now a first-class, queryable dimension.** `larkdocio.permissions`
  describes, per operation, exactly which Lark scopes each call needs — every claim carrying
  its evidence, and where no requirement has ever been observed the entry says so instead of
  guessing. A permission denial now raises `LarkPermissionError` (a subclass of the existing
  `LarkAPIError`; existing `except` clauses and messages are unchanged) whose detail carries
  five things: the missing scope, Lark's verbatim code and message, Lark's own console link,
  which credential pair the call used, and what to do next. An optional `check_permissions()`
  preflight reports which scopes are held before you spend a write — advisory by design (it
  names its own blind spots: a read cannot prove a write scope, and field-level grants are
  invisible), it discloses its cost before spending it, and no code path ever requires it.
  The library still never requests or widens a scope — granting stays a console action.
- **"Will my blocks survive?" is answerable from the wheel.** `capabilities()` now carries a
  per-block-type read projection: 54 rows, each stating whether the type is handled, what it
  renders as, and its lossiness class. The handled column is computed live from the actual
  handler registry at call time, so it cannot go stale.
- **Sheet and Base URLs accepted everywhere.** The URL validator now accepts `/sheets/` and
  `/base/` URLs and returns their type, so the paste-a-URL flow works symmetrically across
  document kinds; the guide's sheet recipes drop their hand-rolled URL parsing.
- **A lighter way to vendor.** Every release now publishes a `dist` branch holding just the
  built wheel (single commit, replaced each release). The consumer updater prefers it and
  falls back to building from the tag; `--check` tells you which path an update would take,
  still writing nothing. The README now opens with a pick-your-path router — consumer,
  vendor, or developer — so each audience gets only its own entry points.
- **Mention resolution failures are diagnosable.** When display names cannot be resolved,
  the log line now names the actual cause class — ids absent from the app's contacts range
  vs. names withheld by a missing field-level grant — and a partial result is reported as
  partial. One line per run; the successful path stays silent.

### Behavior changes you can observe

- `capabilities()` now reports the sheets write path's optional contacts scopes (used by the
  plan-time mention check, which runs on the write credential pair) instead of an empty
  list; scope lists across all surfaces are now derived from the per-operation registry, so
  every scope string has exactly one source of truth.
- API denials across every surface gain the structured five-element detail described above.
  The exception type refines to `LarkPermissionError`; `str(err)` is byte-identical to
  before, so log-matching and existing handlers are unaffected.
- Prose in the packaged documents that claimed "every packaged document" now says "every
  packaged **consumer** document" — the wheel also carries one contributor-facing reference
  that has no accessor, and the claim now matches reality.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned.** The mermaid compiler is a pure-Python
  port inside the wheel.
- **No new scope is required** by any capability in this release. The permissions surface
  now documents which scopes each existing operation needs; one scope name that circulates
  in Lark's own docs for whiteboard export is marked documented-but-unverified rather than
  asserted.
- Vendoring via the new `dist` branch is optional; the build-from-tag path is unchanged.

### Known limitations

- **Parked for the next release** (a fast-follow is planned): sheets tab reorder/hide/
  retitle, cell style and fill writes, borders and word-wrap. The capability matrices state
  their current status truthfully.
- **A missing-scope denial mid-batch does not halt the batch.** During a multi-entry sheets
  apply, a scope denial is recorded per entry and the run continues, although the denial
  cannot clear mid-run. This is long-standing behavior, now easier to see thanks to the
  typed denial; a halting classification is under consideration.
- **Comment removal edge:** interrupting a multi-reply removal (e.g. a rate limit between
  deletes) can leave a thread partially removed without a dedicated partial record. Only
  reachable with app-authored multi-reply threads, which this library's own ops cannot
  create.
- **Mermaid diagrams cannot be updated in place** — Lark's update route does not accept
  diagram payloads. Delete + re-create is the documented path; the block id changes.
- **Anchored comment creation does not exist** on either surface (see above) — this is a
  server behavior, disclosed as a refusal rather than worked around.

## [1.21.0] — 2026-07-29

### New capabilities

- **Comments, read end-to-end.** `larkdocio.comments` ships a typed read:
  `comments(document)` returns every comment thread — text, replies, author id,
  resolved state, the quoted passage — joined to its exact anchor: which block,
  and on docx documents which word-range. The document tree now carries comment
  anchors at both granularities, so "what did reviewers object to, and about
  which passage" is answerable programmatically. Works on spreadsheets too,
  with one disclosed difference: a sheet comment has no structured cell anchor —
  the quoted text is its only locator, and the surface says so rather than
  fabricating one. No new scopes; runs on existing credentials. Comment authors
  are raw ids (`ou_…`) by design — the API offers no display name for them.
- **"Choose your level" guidance for agents.** The packaged guide now opens the
  writer-and-reader mental model to everyone: a decision table mapping common
  user requests to the right entry point (the full-fidelity tree and values
  objects vs. the Markdown projection), worked object-level recipes proven to
  make **zero** Markdown calls, and a self-diagnosis list of symptoms that mean
  you picked the wrong level.
- **Release notes travel with the wheel.** This file and the engineering
  changelog are now packaged inside the wheel, and the consumer updater's
  `--check` prints the release-notes sections for the exact versions you would
  jump — no more blind multi-version upgrades.

### Behavior changes you can observe

- **Package metadata tells the truth.** `pip show larkdocio` previously said
  "writeback reserved" — false since the writer shipped — and the README pointed
  at a support matrix that did not exist in the wheel. Summary, keywords, the
  README's opening, its layout and CLI-options tables are all corrected and now
  guarded against rot.
- **A false documentation claim is corrected**: the write client's docs
  overstated what an edit keeps. They now state, per path, what each edit path
  does with a reviewer's inline comment anchors (below).
- **Editing no longer silently strips a reviewer's inline comment anchors, and
  the two edit paths now differ — deliberately.** A **sub-span** edit re-emits
  each rebuilt run's anchors, so the run that replaces your span carries the
  anchors of the text it replaced and an untouched run is sent back unchanged;
  where the span crosses runs whose anchors differ it refuses
  (`span-not-splittable`) instead of guessing which passage a reviewer meant. A
  **whole-block** edit collapses the block to a single run, so per-passage
  anchors have nowhere to attach: such an edit is now **refused at plan time**
  with the new `comment-anchors-present` code, whose `detail` names the sub-span
  edit as the way through. Nothing is written for a refused entry, and the
  entries around it still apply. **If you edit whole blocks, expect a new
  refusal** on blocks your reviewers have commented inside — where the previous
  release applied the edit and dropped their anchors with no signal at all.
  There is deliberately no flag to override it.
- **A new refusal code:** `comment-anchors-present` joins the docx
  `RefusalReason` family. Code that switches exhaustively on refusal reasons
  should add a branch for it.
- **Rendered Markdown is byte-identical to 1.20.0** for identical inputs —
  every capability above is additive; the projection did not move.

### Upgrade & compatibility

- **No dependency adds, drops, or pin moves.** The pin policy itself is now
  declared in the README: dependencies are pinned exactly, deliberately, for the
  vendored-wheel model — and every future pin move will be announced here.
- **Optional console setting for mention names:** resolving @mention display
  names requires the app's *contacts data range* (a Lark admin/developer console
  setting, not an API scope) to cover the mentioned users. Out of range, mentions
  keep rendering as raw tokens — graceful, unchanged.
- The wheel now contains `larkdocio/CHANGELOG.md` and
  `larkdocio/RELEASE_NOTES.md`, held byte-identical to the repository copies.

### Known limitations

- **A whole-block edit cannot be made to work on a block with inline comment
  anchors** — it rebuilds the block as one run, and there is no honest place to
  put a per-passage anchor on one run, so it refuses rather than move a
  reviewer's comment onto text they never commented on. Use a sub-span edit for
  the words you actually mean to change, or resolve the comments first.
- **What the server then does with the anchors is Lark's behaviour, not ours.**
  We can only send them: a patch that omits the anchors leaves the comment
  orphaned, and no later call can re-attach it (Lark validates the anchors a
  patch sends against the ones the block currently has). That is precisely why
  the sub-span path sends them and the whole-block path refuses.
- **Anchored comment creation does not exist in Lark's API** (verified
  exhaustively against live endpoints): the library reads anchored comments —
  humans create them in the UI — but no API call can create one, on documents or
  sheets. The one creation that works is an unanchored whole-document note, and
  it is deliberately not exposed as a public operation.
- **Sheet comments have no structured cell anchor even on read**; the quoted
  text is a weak locator and is surfaced as exactly that.

## [1.20.0] — 2026-07-29

### New capabilities

- **Sheets filter state is readable.** A tab now reports whether rows are hidden by a filter
  (four states: not read / none / active / unavailable), exposes `filtered_out_rows` on the
  tab model (sheet-absolute, 1-indexed), and the rendered output carries a note naming the
  hidden rows. Which rows render is unchanged — a tab read the traditional way is
  byte-identical to before.
- **Five more executable recipes in the shipped guide** — structural row and column edits,
  merge and unmerge, dropdown rules, tab management, and the export-fidelity read (including
  the explicit tab-title-to-`sheet_id` join, `[[None]]` as the cell-clearing idiom, and
  spreadsheet-URL-to-token extraction). Every recipe in the guide is executed by the test
  suite, so an unrunnable recipe cannot ship.

### Behavior changes you can observe

- A values matrix whose shape does not match its target range now **refuses before any
  network call** (`shape-mismatch`), naming both shapes and both ways to repair it.
- A write or clear over a **live formula** carries an `overwrites-live-formula` preview note
  listing the affected cells.
- `preview_note` now survives onto **applied** log entries, and the apply log gained
  `inert_formula_strings`.
- A reversed or otherwise invalid range refuses as **`malformed-range`** instead of the
  misleading `tab-vanished`. Malformed A1 references and reversed spans now raise typed,
  exampled errors — `A1RangeError` and `DimensionSpanError`; existing `except` clauses keep
  working because both remain in the previous position of the error hierarchy.
- Id-anchored sub-span plans now expose `precondition_text`, so all four request families
  disclose the same thing.
- Unmerging where nothing is merged, and an out-of-bounds dimension delete, now carry
  `no-merge-at-range` and `out-of-bounds-dimension` notes. Destructive previews trim
  `removed.values` to the used width and disclose the trim.
- The advice on a refused same-batch anchor was **wrong and is corrected**: a batch cannot
  depend on its own writes, so re-reading and copying the quote can never succeed. Commit the
  insert, then anchor follow-ups by `created_block_ids`. The engine is unchanged; the
  one-tree-one-batch model is deliberate and now documented as such.
- **Consumer-facing text was rewritten in plain language** — refusal details, preview notes,
  plan and log string values, the shipped guide, `capabilities()` text, and public
  docstrings. Machine-readable codes and field names did not change, but if you match on
  human-readable message text, that text moved.
- The claim that cell emphasis is "invisible to the values API" is gone: the export-fidelity
  read reports **whole-cell, format-level** styling, while run-level emphasis already arrives
  through the ordinary values read. The flag adding nothing at run level is expected.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned in this release.**
- Reader output is unchanged: existing conversions are byte-identical. The new filter
  disclosure renders only when you use the new explicit read path.

### Known limitations

- The export-fidelity read costs an asynchronous whole-workbook export (about 1.2 seconds
  measured, up to roughly 30 seconds in the worst case) and needs the `drive:export` scope
  on the reading application. With the flag off there are no export calls at all.
- Verifying authored content against what reads back is a **compose-equivalence** comparison,
  not string equality — comparing strings will report false differences.
- A merged sheets cell renders as blank, unlike a merged document table cell which carries
  `rowspan`/`colspan`. The asymmetry is intentional and now documented.

## [1.19.0] — 2026-07-28

### New capabilities

- **Formula writes** — a formula request goes through the same plan-and-apply gate. The
  precondition compares the *expression* you intended, not the value it computed, and the
  apply log records that the formula `evaluated`.
- **A worked multi-turn agent recipe** — serialize requests across turns and plan fresh at
  commit time — plus the document and spreadsheet batch contracts documented side by side.

### Behavior changes you can observe

- **No exception can escape `apply()` any more.** Every entry now ends in a typed, logged
  disposition: an entry-scoped failure refuses that entry and the batch continues, while a
  systemic failure (rate limit, transport) halts the batch with every remaining entry logged
  `not-attempted`. Previously a raw API error mid-batch could leave a spreadsheet partially
  written with no record of it.
- **Mentions are validated at plan time.** An unresolvable user id now refuses at dry-run,
  naming the id; if validation itself is unavailable, that is disclosed rather than silent.
- A plain `"=…"` **string** never evaluates on this API. It now earns a loud dry-run note
  instead of landing as silently inert text. Use the formula request form to evaluate.
- **Rendered Markdown changed in two consented ways.** Rich content inside merged table
  cells (bold, lists, dividers, links, nested tables) previously collapsed into garbled inert
  text and now carries real `<strong>`, `<ul>`, `<li>`, `<hr/>` and `<p>` markup with HTML
  entity escaping. Headings deeper than level 6 previously emitted invalid runs of seven or
  more `#` and are now capped at `######`.
- Code blocks keep the leading whitespace of their first line on read; it was previously
  stripped.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned in this release.**
- If you cached Markdown produced by an earlier version, tables with merged cells and
  documents with very deep headings will differ. Re-convert rather than diffing against the
  old output.
- The note claiming writes "run only against scratch documents" was wrong and is corrected:
  it described the test suite's own policy, never a restriction in the engine.

### Known limitations

- Colors inside merged table cells are captured but not rendered.
- A capped deep heading reads back as a level-6 heading, although the parsed tree keeps the
  true level — a documented asymmetry between reading and re-composing.

## [1.18.0] — 2026-07-28

### New capabilities

- **The write engine now authors documents.** Typed new-block kinds — headings 1 to 6,
  bullet, ordered and todo lists with nesting, code blocks with a language, quotes — plus
  **table creation** (rows × columns with an optional header row). Everything goes through
  the existing plan, dry-run and apply gate, and a plain new paragraph stays byte-compatible
  with the previous release.
- **`compose(markdown)`** — compiles a Markdown fragment into gated insert requests. The
  accepted dialect is exactly the reader's own output, and the compiler is bound by a
  round-trip property: what it composes reads back as the same Markdown.
- **Anchoring by block id** — insert, edit, delete and sub-span edits can target a
  `block_id` directly, which closes the loop with the ids an apply returns. Exactly-one or
  refuse; a vanished id refuses with the id named.
- **Strict concurrency for document writes (`STALE_DOCUMENT`)** — a whole-document
  compare-and-swap. Any drift in the document between planning and applying refuses the
  entire batch with zero writes issued: no partial application and no silent re-mapping. It
  is never off, and recovery is refuse, re-plan, proceed.
- Discovery surfaces were updated to match: `capabilities()` and `guide()` state what can now
  be created, the guide gained executable authoring recipes, and per-block write support is
  notated in the block matrix.

### Behavior changes you can observe

- Creating a table with merged cells **refuses** — Markdown cannot express a merge, so the
  engine will not guess one.
- A Markdown construct the dialect does not support **refuses with the construct named**,
  rather than being silently flattened.
- Anchoring by id at the document root previously refused `STALE_ANCHOR` every time; those
  inserts now apply, while genuine drift still refuses.

### Upgrade & compatibility

- **New runtime dependency: `markdown-it-py`, pinned `==4.2.0`.** It was previously a
  test-only extra and is now required at runtime, so installing this wheel pulls it in along
  with its single transitive dependency, `mdurl`. It is pure Python. The reason it is a
  runtime dependency rather than a hand-rolled parser: the authoring dialect *is* CommonMark
  plus GFM tables and strikethrough — the reader's own output — and a second hand-rolled
  definition of that dialect would make the round-trip property prove only that two
  hand-rolled halves agree with each other. **If you vendor the wheel into an environment
  that installs from a private index or an offline mirror, make `markdown-it-py` and `mdurl`
  available there before upgrading.**
- No other dependency was added, dropped, or re-pinned.
- Reader output is byte-identical to the previous release.

### Known limitations

- Do not edit a document concurrently with an authoring session: the engine refuses the batch
  rather than guessing how to re-anchor.

## [1.17.0] — 2026-07-27

### New capabilities

- **The discovery layer tells the truth about writes.** The document-write recipe is runnable
  starting from a URL (the tree-parsing entry point it needed is now linked from both
  `guide()` and `capabilities()`), the creatable-content floor is stated on both surfaces, the
  spreadsheet recipe obtains a real `sheet_id` in-recipe rather than assuming a tab title
  works, and every recipe opens with the credential-loading line. Every guide recipe now
  executes in the test suite.

### Behavior changes you can observe

- **The reader escapes Markdown metacharacters in plain text.** A paragraph whose literal
  text is `# Fake H1`, `- item`, `| a | b |` or `**bold**` previously emitted as *real*
  Markdown structure, indistinguishable from a genuine heading, list or table. Plain text now
  escapes (`\#`, `\-`, `\*\*`), which renders as the literal characters in any Markdown
  viewer. Real structure, real styled runs, linkified URLs, and code content are unchanged.
  This was latent since the first release and silently promoted plain text to structure on
  every conversion.
- **Refusals tell the truth.** An insert target that exists but cannot hold siblings now
  refuses `CANNOT_HOLD_SIBLINGS` instead of a bare `not-found` with an empty detail; every
  document refusal now structurally requires an actionable detail; and a spreadsheet tab id
  that never existed refuses `unknown-tab` with a did-you-mean list of real id and title
  pairs, instead of the staleness misdirection `tab-vanished`.
- **The spreadsheet staleness guard is never silently off.** Some spreadsheets genuinely
  report revision `0`, where the compare-and-swap would have compared 0 against 0 forever.
  Every plan now carries an explicit `revision_guard` marker (`active` or `unavailable`, with
  the reason) plus per-entry value-precondition disclosure, and the guard self-heals the
  moment the revision anchor goes nonzero.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned in this release.**
- The escaping fix **changes converted output** wherever a document contained plain text that
  looked like Markdown structure. Re-convert; do not diff new output against output cached
  from an earlier version. Anchor resolution that keys on rendered text gets more reliable,
  not less, but the keys themselves change.
- If you branched on `tab-vanished` or on an empty refusal detail, update those branches to
  the codes above.

### Known limitations

- None recorded for this release.

## [1.16.0] — 2026-07-27

### New capabilities

- **`larkdocio.capabilities()`** — a typed, JSON-serializable registry of what this version
  can do: surfaces, operations, opt-in flags, the credential and scope requirements per
  surface, and the safety contracts (the staleness compare-and-swaps, plan-gated writes,
  mandatory dry-run). Operations are projected off the real internal registries rather than
  hand-listed, so the registry cannot claim a capability that does not exist or hide one that
  does.
- **`larkdocio.guide()` and an in-wheel consumer guide** — `GUIDE.md` now ships inside the
  wheel with the distilled capability matrix and verified copy-paste recipes for the document
  read and write handshakes, the spreadsheet read and write handshakes, and credential setup.
  The consumer update script drops that guide beside the vendored wheel.

### Behavior changes you can observe

- None. Reading and writing behave identically to the previous release.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned in this release.**
- The spreadsheet write module was reorganized behind a facade and the public surface is
  byte-identical, pinned by an explicit export list. An import that reached past the public
  surface into module internals may need updating; a supported import does not.

### Known limitations

- None recorded for this release.

## [1.15.0] — 2026-07-27

### New capabilities

- **Rich-cell writes** — hyperlink, styled runs, @mention, and multi-select cells can all be
  written back, matching the shapes the reader understands.
- **Dropdown-rule writes** — single and multi list rules can be set, read back, and
  overwritten.
- **Structural row and column writes** — insert and delete rows or columns, plus appending
  rows. The index-convention asymmetry between insert and delete is made inexpressible: you
  describe the edit semantically and never pass a raw index through.
- **Merge, unmerge, and tab writes** — merge and unmerge ranges; add, copy, and delete tabs
  (a copy duplicates merges).
- **Destructive-safe apply** — every operation class runs behind the spreadsheet
  compare-and-swap, and every destructive apply-log entry carries the **full removed
  payload**, so what was destroyed can be reconstructed from the log alone.

### Behavior changes you can observe

- A write targeting a cell covered by a merge **refuses** (`merged-cell-target`).
- A comma inside a multi-select option label **refuses** with a typed error: the wire format
  is comma-delimited, so the label would be ambiguous.
- Setting dropdown highlight colors **refuses before the write**, because the API rejects it.
- Merging **previews the covered values it is about to destroy** before you apply.
- Multi-select values normalize to the same ordered label set on both the read and the write
  side, so a round-trip comparison no longer reports a false difference.
- An apply that was never previewed is not expressible: a plan cannot be forged and there is
  no bypass.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned in this release.**
- **Mention writes default to not notifying and not granting read permission.** Opt in
  explicitly if you want either.
- **Dropdown rules replace, they do not accumulate.** Writing a rule over an existing one
  discards the old option list.
- Reader output is unchanged.

### Known limitations

- A dropdown rule is guidance, not enforcement: values outside the option list are accepted
  by the API. This was confirmed against the live service, not assumed.

## [1.14.0] — 2026-07-27

### New capabilities

- **Opt-in export-fidelity read for spreadsheets (`--fidelity-read-sheets`).** Renders
  cell-level bold and italic as Markdown emphasis. With the flag off — the default — there
  are zero export calls and the output is byte-identical to a values-only read.
- **A typed spreadsheet cell model** (purely additive): raw and display value side by side,
  segment runs, the number-format pattern, hyperlink, mention and multi-select structure, and
  merge membership. A values-only read degrades gracefully when no export is available.
- **Style and number-format verification on writes (`--verify-style`)** — automatically on
  for style, format, merge, and structural writes, so a style write cannot skip its own
  verification. A failure names the offending cell and attribute.

### Behavior changes you can observe

- **Multi-select cells render as an ordered, `", "`-joined set**: `Red,Green` now renders as
  `Red, Green`. Both the comma-string read form and the write wire form normalize
  identically, and a digit-flank guard keeps currency strings such as `$1,234.56` untouched.
  This is the one default-output change in this release.
- Document conversion output is byte-identical to the previous release.

### Upgrade & compatibility

- **No dependency was added, dropped, or re-pinned in this release** — and specifically, the
  export reader that powers the fidelity read is **stdlib-only** (`zipfile` and
  `xml.etree`), deliberately adding no new dependency.
- The export-fidelity read needs the **`drive:export`** scope on the reading application. If
  that scope is not granted, leave the flag off; the default path never calls export.
- If you compare rendered spreadsheet Markdown against output cached from an earlier version,
  multi-select cells will differ by the space after each comma.

### Known limitations

- A values-only read cannot report cell-level styling; that is what the opt-in fidelity read
  is for.
