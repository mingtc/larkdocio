# Consuming larkdocio — zero-knowledge onboarding

You want to use `larkdocio` from **your** project. **What ships is enumerated by
`larkdocio.capabilities()`, not counted here** — read it for the census; this
paragraph names the families. The **reader** (a Lark/Feishu `docx`/`wiki` document
→ clean Markdown), the **writer** (a plan-gated writeback apply-engine plus
Markdown authoring), **sheets** (values → Markdown plus a plan-gated write
engine), **base** (a Base → titled Markdown tables, plus plan-gated record and
schema writes), **drive** (a folder read, plus direct-call writes beside it —
versions, access, files, folders), **contacts** (a name, an email or a mobile → exactly
one `open_id`, or a typed refusal) and **comments**. **Comments:** read on a docx, a
spreadsheet and a Base; create and remove an unanchored (whole-document) comment on a docx. An
anchored comment, and a comment write on a Sheet or a Base, is refused.
This walkthrough takes you from nothing to a working, pinned, self-updating-aware
setup **without reading a single line of the larkdocio source**. Everything below
is a command you run in **your** repo.

> **The one rule to remember:** larkdocio is **never auto-updated**. Refreshing
> the vendored wheel is always a deliberate command you run. The optional nag
> (the git hook) only *tells you* an update exists — it never applies one.

---

## How larkdocio ships (the 20-second version)

larkdocio does **not** get installed from PyPI or pip-from-git. Instead you
**vendor a built wheel** into your repo (`./vendor/larkdocio-<ver>-py3-none-any.whl`)
and **pin a local-file requirement** to it. A fresh clone of *your* repo then
rebuilds its environment from that local wheel — **no larkdocio git host needed**
(PyPI is only used for ordinary transitive dependencies).

**Where the wheel comes from.** larkdocio's public repository,
`https://github.com/mingtc/larkdocio`, is its release home: every release from
1.53.0 (the first public one) on is a `vX.Y.Z` tag there, and its `dist` branch carries the current release's wheel,
consumer documents and a short README, and nothing else (it is replaced on each release). The refresh
script takes the wheel from `dist` when it is the version you asked for, and
otherwise builds it from the tag. Both are anonymous HTTPS reads.

The **only** step that ever contacts the larkdocio git host is building/refreshing
the wheel (`update_larkdocio.sh`). Normal `git pull` in your repo touches no
larkdocio network at all.

---

## Prerequisites

- `git` and `python3` (Python 3.11 or newer) on your machine.
- A Python virtual environment for your project (this guide assumes `.venv/`).
- **One-time** network access to `github.com` (only to fetch or build the wheel),
  and to PyPI when the wheel is built from a tag.
  The default URL is the public repository over HTTPS, so no git credential is
  needed. To install from a mirror or a fork instead, set `LARKDOCIO_REPO_URL` (the
  one place the refresh script keeps the location).
- Lark **read** credentials (a Lark app with `docx:document:readonly`). The full,
  authoritative per-operation scope list is generated from the library's own permission
  registry — `larkdocio.permissions` — and printed in the permissions section of
  `larkdocio.guide()`; this line names only the one scope a plain download needs.

You do **not** need: to read or build the larkdocio source, submodules, or any
Node/web tooling. (Step 1 takes the onboarding scripts from a shallow clone you can
delete as soon as it finishes.)

---

## Step 1 — Onboard (build + vendor the wheel)

From **your** repo root, fetch the onboarding kit with a shallow clone of the
public repository and run its script (you never open its files, and you can delete
the clone afterwards — everything it installs is copied into your repo):

```bash
git clone --depth 1 https://github.com/mingtc/larkdocio.git /tmp/larkdocio
/tmp/larkdocio/consumers/setup-consumer.sh
```

This does four things for you and then **prints exactly what remains**:

1. copies `update_larkdocio.sh` into your `scripts/`,
2. copies the advisory git-hook template into your `scripts/`
   (`scripts/larkdocio-post-merge.hook`),
3. copies the **router skill pack** into your `.claude/skills/` (see Step 5),
4. vendors the latest release's wheel into `./vendor/` (from `dist`, or built from
   the tag when `dist` is not that version).

The tail of its output is your to-do list (the pin line, the `.env` names, and
the nag-wiring one-liner). Follow it — the rest of this page is the same list
with more explanation.

## Step 2 — Pin the requirement and install

The script prints a line like:

```
larkdocio @ file:./vendor/larkdocio-<ver>-py3-none-any.whl
```

Add **that exact line** to your requirements file (e.g. `requirements.txt`), then
install it into your venv (substituting the actual version the script printed
for `<ver>`):

```bash
.venv/bin/pip install --force-reinstall './vendor/larkdocio-<ver>-py3-none-any.whl'
```

This first install resolves larkdocio's runtime dependencies, so it deliberately does
**not** pass `--no-deps`. On a **later refresh** — the venv already has those
dependencies and only the wheel moved — use the command `update_larkdocio.sh` prints
when it finishes, which adds `--no-deps` so pip touches the local wheel and nothing else.

Now `import larkdocio` (and the `larkdocio` CLI) work in your project.

## Step 3 — Provide Lark credentials

larkdocio reads credentials from your project's `.env` (never committed). The
**read** path uses:

```dotenv
LARK_READ_APP_ID=...        # preferred
LARK_READ_APP_SECRET=...
# — or the legacy names, still accepted —
LARK_APP_ID=...
LARK_APP_SECRET=...
```

(`LARK_WRITE_APP_ID` / `LARK_WRITE_APP_SECRET` are **separate, write-scoped**
credentials (one app or two; two recommended) and are never consulted by the read path. Leave them unset unless you use
a write surface — the document writer, a Sheets, Base or Drive write, or
`larkdocio roundtrip push` — which the shipped guide `larkdocio.guide()` walks you
through.)

## Step 4 — Wire the advisory update nag (recommended, optional)

So you find out when a newer larkdocio is released **without** having to remember
to check. This is a **nag only** — it never updates anything.

**Git hook (fires after `git pull` / `git merge`).** From your repo root — and
let git name the destination rather than typing it:

```bash
HOOKS="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOKS"
cp scripts/larkdocio-post-merge.hook "$HOOKS/post-merge"
chmod +x "$HOOKS/post-merge"
git hook run post-merge
```

**Why not just copy into `.git/hooks`?** Because that is only right when
`core.hooksPath` is unset. When it is set — and plenty of repos set it, including
any repo that adopted a shared hook directory — git reads hooks from *that*
directory and only that one, so a hook copied into `.git/hooks` is **never run**:
no warning, no error, exit 0, and a `git pull` that should have nagged you says
nothing at all. `git rev-parse --git-path hooks` answers correctly in every
case: `.git/hooks` when the setting is unset, the configured directory
(relative or absolute) when it is set. (`git config --get core.hooksPath` looks
like the primitive to use and is not — it prints nothing and exits 1 when the
setting is absent.)

**Run that last line.** `git hook run post-merge` resolves the hook through
git's own lookup, so it prints the nag's own line when the wiring is right (or
nothing at all if the check cannot reach the host or no tag exists yet) and
fails loudly (`cannot find a hook named post-merge`) when the file sits
somewhere git does not read. It needs git 2.36 or newer; on older git, merge
something and watch for the `[larkdocio]` line. Check it once, because this nag
is **quiet when you are up to date** — one short line — so its silence is not by
itself evidence that it is working.

After that, on your next `git pull`, if a newer larkdocio tag exists you'll see a
`[larkdocio] UPDATE AVAILABLE …` line. It never fails your pull, never writes to
`./vendor/`, and never updates. (The same file works as `"$HOOKS/post-checkout"`
if you also want a nag on branch switches.)

## Step 5 — The router skill pack (installed for you; re-copy after every refresh)

`setup-consumer.sh` copies a handful of small **router** skills into your
`.claude/skills/`. You can also install or refresh them on their own, without
re-vendoring the wheel:

```bash
/path/to/larkdocio/consumers/install-skills.sh
```

Each file fires on a **task shape** — *edit a document as a file*, *write rows
into a Base*, *why was I refused?* — and answers with an **address**: the name of
a section in `larkdocio.guide()`, or the console command to run. That is all they
do.

**They are deliberately thin, and that is not an oversight to fix.** A skill file
that *explains* a thing the guide already explains becomes a second copy of it,
and the copy is the one that goes stale: the wheel moves, the copy does not, and
nothing tells you. So the routers point and stop. If you improve one, keep it
pointing — and if the section you want does not exist, that is worth reporting
rather than writing the missing prose into a skill file.

Two guards in the larkdocio repository hold that line for the copies shipped
here: every section name a router cites is resolved by calling `guide()` itself,
and every console verb is checked against the command tree the wheel actually
registers, so a router naming something that does not exist fails the build
rather than your agent.

**Version skew is the known cost of copying, and it cuts both ways.** The pack
is stamped with the version of the checkout it was copied from, and your wheel may be **older** than that
— a pointer the pack names will not resolve, so refresh the wheel — or **newer**
than it, in which case the pack may be missing something added since, so re-copy
the pack. Each file says which version and date it came from — `install-skills.sh`
writes that stamp at copy time, from the version of the larkdocio checkout it copies
from, so a re-copy is always stamped with what it really is — and tells you to
run `scripts/update_larkdocio.sh`. After any refresh, re-copy the pack so the
pointers and the wheel move together. `install-skills.sh` is not copied into your
repo, so take it from a fresh clone: the same shallow clone as Step 1, then
`/tmp/larkdocio/consumers/install-skills.sh`, then delete the clone again.

> **Why the pack exists in this shape** (larkdocio maintainers). It is built to be
> **A/B measured**: the same consumer scenarios run with and without it, per the
> design in **LD-479** — `dev/dogfood5/DESIGN.md`, the design's own permanent home, in the dev
> repo, among the maintainers' private records (the public repository does not carry it). (Cited by issue id and stable path, never by a board column:
> a column citation rots the next time the issue moves, which is what happened to the one this
> line used to carry. LD-546 § A item 8.) Thinness is the thing being measured. Growing a router
> into a restatement before that run would quietly change what is being compared.

---

## Refreshing later (always deliberate)

When the nag tells you an update exists — or any time you choose — run your own
copy of the refresh script from your repo root:

```bash
scripts/update_larkdocio.sh            # build + vendor the LATEST tag
scripts/update_larkdocio.sh v1.53.0    # build + vendor a specific tag
scripts/update_larkdocio.sh --check    # report-only: is a newer tag available?
```

After a real (non-`--check`) run, re-pin the new requirement line it prints and
re-install it into your venv (same as Step 2). That is the *entire* update loop —
nothing about it is automatic.

**A refresh either gives you the wheel you asked for or refuses out loud.** It never
vendors a different version under a success line. Before it copies anything into
`./vendor/`, it checks that the wheel it built carries the version of the tag the run
asked for, and it refuses to choose between two candidate wheels by sort order — the
same posture it already takes when `./vendor/` itself holds more than one. Every one of
those refusals is a nonzero exit that names what it found and leaves `./vendor/`
untouched, so a failed refresh cannot leave you pinned to something you did not ask for.
If you are carrying an older copy of this template, re-copy it: the older copy could
vendor a stale wheel and report success when the fast-path branch lagged the tag.

**What a refresh leaves in `./vendor/`.** Five files, all refreshed on every run and
all taken from the tag you vendored, so they always describe the wheel sitting next
to them:

| In `./vendor/` | What it is |
|----------------|------------|
| `larkdocio-<ver>-py3-none-any.whl` | The wheel you pin. |
| `larkdocio-GUIDE.md` | Usage recipes + the capability matrix. |
| `larkdocio-CHANGELOG.md` | The project's changelog. |
| `larkdocio-RELEASE_NOTES.md` | **What changed that affects you**, release by release — public symbols and flags, observable behavior changes, new refusals, credential and scope requirements, every dependency add and pin move, and known limitations. Read this one before you re-pin. |
| `larkdocio-LARK_SETUP.md` | The **Lark-application walkthrough**: create the app, grant the starter scope, share the documents onto it, prove one real read. Read this one FIRST if nothing works yet — nothing in the library runs until a Lark app exists, holds the scopes and can reach your documents, and none of those three is a code change. |

A tag that lacks one of those documents skips that drop with a logged note; the
refresh still succeeds. Each of those documents also ships *inside* the wheel —
as `larkdocio.guide()`, `larkdocio.changelog()`, `larkdocio.release_notes()` and
`larkdocio.lark_setup()` — so they are readable from an installed package too.
**The release notes are not the same document in the wheel as in the drop, and the
difference matters when you go looking for an old release:** the drop copies the
publishing repository's root `RELEASE_NOTES.md` (every release from 1.14.0 on), while
the packaged `larkdocio.release_notes()` carries a **window of the newest releases
only** — it says so in its own first lines, and names where the older history lives.
So look an old release up in the file this drop just handed you, not in the
installed package. The changelog has the same entries in both: it records 1.52.0
onwards, whole, and sends you to the release notes for anything earlier; the packaged
copy adds a short banner at the top saying so.

**`--check` also tells you what you would be getting.** When a newer tag exists it
prints the release notes' section headers for the versions in between, plus the
subsection titles that have something to say — so "should I update?" is answered
with the reason, not just a version number. It stays report-only: it never writes to
`./vendor/`, never updates, and its one-line verdict on stdout is unchanged (the
detail is printed alongside it, on stderr). It reads those headers from the latest
tag, which costs a small throwaway clone; set `LARKDOCIO_CHECK_NOTES=0` to skip that
and keep the check to lightweight remote queries (one, plus one for the `dist` branch
when an update is available). The advisory git hook
already does exactly that, so your `git pull` stays fast.

---

## What each file in `consumers/` is for

| File | Purpose |
|------|---------|
| `setup-consumer.sh` | One-time onboarding: copies the scripts, vendors the wheel, prints your to-do list. |
| `update_larkdocio.sh` | The refresh script (copied into your `scripts/`). Builds/vendors a wheel; `--check` reports only. |
| `hooks/post-merge` | Advisory git-hook template (nag only). `setup-consumer.sh` copies it to your `scripts/larkdocio-post-merge.hook`. |
| `skills/` | The router skill pack — one directory per skill, each holding a `SKILL.md`. Copied, never installed with the wheel. |
| `install-skills.sh` | Copies `skills/` into your `.claude/skills/`. Enumerates the pack directory, so it needs no editing when a router is added. Run it again after every wheel refresh. |

You never need to read any larkdocio **source** to consume it — these consumer
files are the whole contract.
