# Changelog

All notable changes to `larkdocio` are recorded here, one section per release, newest first.
Version numbers **increase monotonically** and carry no major/minor semantics: read a
release's section, not its number, to learn what changed.

**Where this log starts.** Versions up to and including 1.52.0 were developed privately, and
1.53.0 is the first public release. This log has an entry for 1.52.0 only so that every version
the package can report has one; the user-facing changes of 1.52.0 and of the earlier versions,
from 1.14.0 on, are recorded per version in [`RELEASE_NOTES.md`](RELEASE_NOTES.md). The copy
of those notes inside the wheel carries the newest eight releases only; the repository's root
copy, and the one the `dist` branch carries, hold every section from 1.14.0.

**Two documents, two readers.** This file says what changed in each release. `RELEASE_NOTES.md`
is filtered to what a caller can observe, install, or be broken by, and reaches further back.

**Whose the date is.** A section's date belongs to the cutter: it is the day the release was
cut. The topmost section may be **un-cut**: changes land in it before the release is tagged, and
until then its date is a placeholder. The release tooling refuses to tag a section whose header date
is earlier than the newest date written inside that same section.

> **This copy carries every release this document records — 4 releases, 1.52.0 up to 1.53.2 —
> verbatim.** The same entries are at `vendor/larkdocio-CHANGELOG.md`, which the consumer
> refresh script drops beside the vendored wheel on every refresh, and the publishing
> repository's own complete copy of this document at its root.
>
> Releases older than this changelog's first entry are recorded per version in the release
> notes: the `vendor/larkdocio-RELEASE_NOTES.md` drop beside the wheel, or the publishing
> repository's root copy. The wheel's own `larkdocio.release_notes()` carries only a window of
> the newest releases.
>
> `larkdocio.changelog(section=...)` refuses a release this copy does not carry by name and
> says where to read it; `larkdocio.changelog_sections()` lists the 4 releases this copy
> carries.

## [1.53.2] — 2026-11-14

### Fixed

- **Shipped text no longer cites the maintainers' private records.** Docstrings, comments,
  packaged documents and `evidence` strings pointed at files in the maintainers' private working
  repository, which neither the wheel nor this repository carries. Each pointer was dropped where
  the sentence stood on its own; otherwise the fact is stated, a published recording is cited
  instead (under `tests/captures/` in the source repository), or the text says the recording is
  unpublished. No fact and
  no behaviour changed. If you match an `evidence` string by exact text, re-check it.
- **A correction to the 1.53.1 entry.** It says no product behaviour changed, which holds, but
  the 1.53.1 release notes also said no code that ships in the wheel changed. One message string
  in `guide.py` (shown by `changelog()`), one sentence of the shipped guide and one comment did
  change.
- **Release dates.** A section's date is the day the release was cut, and the public tag can
  follow it: v1.53.0 and v1.53.1 were tagged here three days after their cut dates. From 1.53.2 on,
  the public release commit and its tag carry the cut's time, in UTC (`+0000`).
- No dependency moved.

## [1.53.1] — 2026-11-10

### Fixed

- **The test suite passes at this version.** At 1.53.0 one test failed in a source checkout: it
  pinned the README example `scripts/update_larkdocio.sh` with the release's own version, which
  the suite's version-freeze check refuses once that version is the installed one. The example
  and the README now use the placeholder `vX.Y.Z`, and the freeze check also refuses a literal
  of the next version, so the same mistake fails before a release rather than after it.
- **A correction to the 1.53.0 entry.** It says the test suite runs green on Python 3.11
  through 3.14. At the 1.53.0 tag it did not, on any of them: the one failure above was red on
  every interpreter. It is fixed in 1.53.1.
- No product behaviour changed and no dependency moved.

## [1.53.0] — 2026-11-08

### Changed

- **The supported Python floor is now 3.11** (`Requires-Python: >=3.11`; it was `>=3.10`). The
  test suite already needed 3.11, so 3.10 was never tested. On Python 3.10, pip no longer
  installs this release.
- The documentation describes the shipped changelog as the project's changelog, consistently.

- **Licensed under the Apache License 2.0.** The wheel and sdist carry the `LICENSE` file, and
  the package metadata reads `License-Expression: Apache-2.0` (it read `Proprietary`). Building
  from source needs `setuptools` 77 or newer; pip fetches it in an isolated build.
- **The package's `Author` metadata is `mingtc`.** It carried a placeholder.
- **Examples and recorded test data use placeholder values**, in the guide, docstrings, some
  messages and `capabilities()` texts, and a few sentences in earlier release-notes sections.
  Nothing a call does changed; if you match a message by exact text, re-check it.
- **Some earlier release-notes entries were reworded for clarity**, to describe each fix by what
  changed. Nothing a call does changed.
- **The `html` refusal's recovery text has a new example**, `Lorem <ipsum dolor>`. The construct,
  the reason code and the repair are unchanged; if you match that message by exact text, re-check it.
- **The consumer kit no longer carries a CI include.** It depended on one hosting service's CI; a copy you
  already made keeps working, and the walkthrough's `post-merge` hook is the update reminder.
- **`larkdocio.changelog()` returns this changelog.** For releases before 1.52.0 it refuses and
  points at the release notes; read `release_notes(section=...)` for those the wheel's copy
  carries (the newest eight releases), and the repository's `RELEASE_NOTES.md` for the rest.
- **Install and refresh from the public repository, over HTTPS, with no credential.** Every
  release from 1.53.0 on is a `vX.Y.Z` tag there, and its `dist` branch carries the current
  wheel. The consumer
  refresh script's default URL is `https://github.com/mingtc/larkdocio.git`; re-copy
  `update_larkdocio.sh` from the consumer kit over your `scripts/update_larkdocio.sh` to pick
  it up.
- **The skill pack is stamped at copy time.** `install-skills.sh` writes into each copied router
  the larkdocio version it was copied from and the date of the copy.
- **Evidence paths for recorded API responses name a copy you can open.** The path is now the
  copy the repository carries under `tests/captures/`, labelled "in the source repository"; the
  wheel does not include it.

### Fixed

- **The import-time warning record is corrected for Python 3.11 to 3.13.** The README said
  `import larkdocio` emits exactly one `DeprecationWarning` on Python 3.12 and newer; that holds
  on 3.14 only. Older interpreters also show deprecations from `lark-oapi`'s websocket client
  and the `websockets` library it imports. None is larkdocio's, and none is suppressed. The test
  suite now runs green on Python 3.11 through 3.14.
- **Provenance notes no longer cite files that do not exist.** Refusal messages, preview notes,
  the `capabilities()` absence register, the guide's permissions tables and docstrings cite the
  project's recorded measurements. Where a recording is no longer
  published, the text now says so and states the measured fact itself. The facts did not change.
  Two messages changed wording: the note on a border-style write plan no longer names a probe
  script, and the refusal for an empty Drive folder name cites the one recording that survives.
  If you match either message by exact text, re-check it.
- **A path labelled "(in the dev repo)" that points into the maintainers' records is a note, not
  a file you can open.** The library's own description of that label now says so; the sentence
  carrying such a path states the fact itself.
- **A citation of a file any clone carries says "(in the source repository)".** Recorded API
  responses under `tests/captures/`, the root matrices and the tests are in any clone of this
  repository; "(in the dev repo)" is kept for the maintainers' private records. This holds across
  the library's text, `capabilities()` and the root matrices; earlier release-notes sections keep
  their released wording. `evidence` strings in refusals and loss previews change with it.
- **The guide's first routing table no longer calls a Base or a Drive folder read-only.**
- **`update_larkdocio.sh`'s note for a tag lacking a vendored document is shorter.**
- **The console link in `larkdocio.permissions.OBSERVED_DENIALS` no longer names a specific Lark
  app.** The `directory:employee:search` denial's `help_url` carries `<your-app-id>` in place of
  an application id that was not yours. Scope, query string and host are unchanged.
- **A retired output key from earlier versions is no longer accepted.** As an `OutputConfig(...)`
  keyword or a fifth positional argument it raises `TypeError` (the fields after
  `skip_img_download` are keyword-only); in `config.json` it is ignored like any unknown key. In
  1.52.0 its warning named 1.51.0, so it read as though the key had already been removed; it was
  accepted and ignored throughout 1.52.0.
- **Examples generalised**: the documentation states its examples in general terms. The `--route` help and refusal messages give
  `area/section/topic` as the example subpath.

- **A refused refresh leaves `./vendor/` exactly as it was.** The refresh script copied the new
  tag's documents into `./vendor/` before building, so a failed build or a version refusal left
  your old wheel beside the new documents. The wheel and the documents are now vendored together,
  after every check passes; a `dist` branch carrying more than one wheel is refused rather than
  chosen from by sort order, and the script builds from the tag instead.

- **Four claims are corrected.** `larkdocio --help` and the README say hidden view columns are
  settable; the consumer README says comments can be created and removed on a docx; the help
  names the Drive files leg's byte round trip; and the refresh script, hook and consumer README say
  `--check` can make a second remote query. If you match any of these by exact text, re-check it.
- **Every recording cited "in the source repository" exists in it.** Where a recording is not
  published, the text says so and states the fact.
- **`capabilities(full=True)` no longer says Drive sharing is refused.** The `drive-read`
  surface's note said the Drive family had one write surface and offered no sharing call; it now
  names the four Drive write surfaces, `drive-access-write` among them. If you match that note by
  exact text, re-check it.
- **No example names a tag older than v1.53.0**, the first public release.
- **The recorded responses' numeric ids fit int64**, so a typed parser reads the fixtures.

### Dependencies

- No runtime dependency was added, dropped or re-pinned. Building from source needs
  `setuptools` 77 or newer.

## [1.52.0] — 2026-09-09

The last release developed privately. Its changes are recorded in `RELEASE_NOTES.md` § 1.52.0.
