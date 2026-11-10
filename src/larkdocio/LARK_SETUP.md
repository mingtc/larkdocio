# Setting up your Lark application — the ten minutes before your first download

larkdocio talks to Lark (Feishu) **as an application, not as you**. Nothing in this library
works until a Lark app exists, holds the right scopes, and can reach the documents you point
it at. This file is the shortest honest path through those three facts. It deliberately does
**not** enumerate permissions — that table is **generated from the code** and lives in
`PERMISSIONS.md` **in the source repository** (every call site, every endpoint, every scope, with the
evidence for each row); from an installed wheel the same rows come back from
`larkdocio.guide(section="permissions-what-to-ask-for")`, which is the same projection of the
same registry. This file just gets you to your first successful call — and it records the five
places real setups get stuck, each marked as the console-side observation it is.

**This document ships inside the wheel.** `larkdocio.lark_setup()` returns it and
`larkdocio.lark_setup_sections()` indexes it, so the walkthrough is readable from an install
with no clone, no network and no source-reading — the same text either way.

## Running your own app (do this — don't borrow someone else's)

**Create your own app; do not ask to be added to somebody else's.** A Lark app's grants are
capabilities of the app, not of a folder: everything shared onto that app is readable by
everyone holding its credentials, and the grant list is one list for all of them. So an app
that starts life as *"my own documents"* turns into an app with read and write reach across
everyone's shared folders the moment it is handed around — over-scoped for almost everyone carrying
it, and hard to narrow again once people depend on it.

The shape that stays honest is **one app per person, or per team**: each holding only the
grants its own work needs, each with only its own documents shared onto it. It costs the ten
minutes below, once, and it is what the rest of this walkthrough assumes — your app, your
grants, your documents.

**Five subsections below are marked *operator-observed console guidance*.** Each is a place
real onboarding attempts got stuck, recorded from the console side. They are **not**
measurements of the API, and Lark's console governs its own behavior and may change it: read
each as *"look here first"*, with Lark's own documentation as the authority on what any
setting is called and where it lives.

## 1. Create the app

1. Open your tenant's developer console — `open.larksuite.com` (international) or
   `open.feishu.cn` (China; the console flow is the same, Lark's own docs govern the details).
2. **Create a custom app.** Note its **App ID** (`cli_…`) and **App Secret** — these are the
   credentials larkdocio uses.
3. Grant it scopes (next section), then **publish/release the app version** — in Lark,
   scope grants generally take effect through the app's release flow, not the moment you
   click them. If a call is refused after granting, an unreleased version is the first thing
   to check — and the release flow gates more than grants, which is *The release wall* under
   step 3.

### Wall — a fresh app is not a bot yet (operator-observed console guidance)

Creating the app is one form. Making it into something your tenant can actually see and use is
several pages of settings that live apart from each other, and that separation is where the
first attempt usually stalls:

- **The bot capability is added, not implied.** A newly created custom app has no capabilities
  enabled. The bot is one you add to it explicitly, on its own page; the app's name, icon and
  description are a different page again; the grants are a third. Whether any particular
  document call needs the bot half is **unmeasured here rather than refuted** — what was
  observed is narrower and still useful: the tenant-facing half of an app (finding it in a
  chat, offering it in a share dialog, listing it for an administrator) is the bot, and a fresh
  app has none until you add one.
- **Nothing on these pages takes effect on save.** Capability and profile changes go live
  through the same release flow as grants, which is why a setting that reads correctly in the
  console can still be absent from the app your credentials are talking to.
- **The console is the authority on its own layout.** Page names, and which page nests under
  which, differ by region and change over time. The list above says *what to look for*, never
  where to click.

## 2. Grant scopes — start small, ask the library for the rest

For your **first read** — a document into Markdown — grant the one readonly scope the core
document read carries: it is the `docx-read` rows of the permissions matrix, which is
`PERMISSIONS.md` **in the source repository** and
`larkdocio.guide(section="permissions-what-to-ask-for")` from an installed wheel. Both are
**generated from the code and canonical** — the scope string is deliberately not copied here,
because a copy is where drift starts; open the table, take the row.

Then stop hand-collecting and **ask the library**, which knows its own requirements
per operation:

```python
import larkdocio
print(larkdocio.guide(section="permissions-what-to-ask-for"))   # per-operation scope rows
```

Specific surfaces add their own rows as you reach them — Base reads, sheets, whiteboard
images, name resolution — and each refusal you meet is **typed and names what was missing**:
the library surfaces Lark's own denial body rather than guessing.

**Two different things can be missing, and the refusal says which.** A missing **scope** names
the scope, from Lark's own denial body. A rejected **App ID / App Secret** — the one that fails
before any document is asked for, because no token is issued at all — says it is a credential
problem, names the credential variables to fix and the `.env` that was read, and where the
failing call used one specific pair it names that pair rather than offering you both. That
second answer arrives on **every** command from **1.52.0** on. In 1.51.0 it arrived on the
reader (`download`, `roundtrip pull`) only, and in every release before that on none of them:
`folder`, `roundtrip`'s `push` phase, the spreadsheet clients and `preflight` surfaced a
rejected pair as an untyped error instead. So on any wheel older than 1.52.0, a command that
dies with a bare `tenant_access_token` traceback is this — check the pair, not the document.

One rule to know up front:
**larkdocio never widens, requests or escalates a scope** — it describes requirements; the
grant itself is always your action in the Lark console.

### Wall — tenant or user: this is a tenant-identity library (operator-observed console guidance)

The console offers most permissions **twice** — once as something the *application* may do, and
once as something a *signed-in person* may do through the app. Those are two different
identities with two different consent flows, and granting the wrong one produces a grant that
never takes effect for this library.

**larkdocio authenticates as the application on every call, with a tenant access token.** It
holds no user session, runs no sign-in redirect, and stores nothing per person: the app is the
caller, and what it can reach is what has been shared onto the app (step 3). So grant the
**application** side of every permission you need, and read the generated table the same way —
its rows are the app's requirements.

Per-person tokens are **out of scope** here, and out of scope means exactly that: no path in
this library obtains, stores or sends one, so how such a grant behaves has been
**unmeasured, not refuted**. If your situation genuinely needs per-person identity, that is a
different design and not one this walkthrough reaches.

**Before concluding you need per-person identity, check whether the app can already read what
you are after.** The sentence above — *what it can reach is what has been shared onto the app* —
is the floor rather than the whole story: an app also inherits whatever is **visible to the
whole tenant**, because a document shared with everyone in the tenant is shared with
the app too. Observed on **one tenant, one app, one folder**: on a folder visible to the whole
tenant but never shared to the app, the tenant token listed the folder's children, walked
into its subfolder and read the documents in it — while being refused on that same folder's
permission configuration. That is Lark's own permission
model, not anything larkdocio does, and it is **not** the claim that an app can read whatever it
likes: a tenant that shares nothing tenant-wide would see none of it.

**The other half is the uncomfortable one, and it is the half an operator most needs: an app's
reach is WIDER than the list of things you shared with it.** So *"what can this app read?"* is
**not answerable from your share list** — the honest answer is *your shares, plus anything
visible to the whole tenant* — and an exposure audit that reads the share list alone
**under-counts** what the app can see. Two riders. This is **access**, not scope: a scope
decides which *kinds* of call the app may make, sharing and tenant-wide visibility decide
which *objects* it may make them on, and no grant in the console moves the second (step 3). And
it is a fact to know rather than a design to rely on — a share can be narrowed at any time by
somebody who is not you.

### Wall — the grant list keeps growing, one refusal at a time (operator-observed console guidance)

Nobody gets the list right up front, and this library is built on that assumption: every
refusal it surfaces is typed and carries Lark's own denial body, which names what was missing.
The loop is *call → read the refusal → grant → release → call again*, and going round it
several times as you reach new surfaces is the normal experience, not a sign of a mistake.

Two things make the loop cheaper:

- **Read the generated table once for the operations you actually plan to run**, and grant that
  whole set in a single pass. Because it is derived from the code, it is the shortest honest
  list that exists — and each release costs a review cycle, so batching turns five cycles into
  one.
- **Expect the list to keep growing anyway.** A surface you reach later — Base reads, sheets,
  whiteboard images, name resolution — is one or more new rows, and re-reading the table beats
  guessing at the string. Nothing in the library adds a grant for you: every addition is your
  console action, and the library's only job is to tell you, in the refusal, which one is
  missing.

## 3. Let the app REACH your documents

Scopes are not access. A Lark app sees only what has been **shared with it** (or what its
availability settings expose). If a call answers with a permission denial on a document you
own, share the document — or its parent folder — with the app, the same way you would share
with a person. Folder-level shares cover the tree under them.

### Wall — the release flow gates members and availability, not just grants (operator-observed console guidance)

The release step in step 1 reads like a grants-only formality. It is not: the same flow also
gates **who the app is available to**.

- **Adding people to the app requires a release.** Putting collaborators, a department, or the
  whole tenant on an app's availability list is a version change like any other — the list you
  edited is not the list in force until the version carrying it has been released, and where
  your tenant requires it, approved by an administrator.
- **Narrowing it is the same flow**, which matters if you widened an app in a hurry and want it
  back.
- **Two lists, both real, neither a substitute for the other.** *Availability* is who may use
  the app; *sharing* is which documents the app can see. An app the whole tenant can see still
  reads nothing that has not been shared onto it **(including tenant-wide visibility)**,
  and an app with every document shared onto it is still unusable by another user who is not on
  its availability list.
- **The symptom to recognise.** Another user who cannot see an app you just added them to, or a
  grant behaving as though it were never made, is far more often an unreleased version than a
  wrong setting.

## 4. Credentials into larkdocio

```bash
larkdocio config --appId cli_a123... --appSecret abc...   # writes LARK_READ_APP_ID / _SECRET into .env
```

…or write the `.env` yourself (never commit it). **Read and write are separate credential
pairs** here: the `LARK_WRITE_APP_*` pair names the app holding write scopes — a second app is
recommended, not required (both pairs may name one app) — and the read path never consults it,
enforced by the credential resolution order documented under *Credentials & `.env`* in **this project's README** — which you do not
need a clone to read: it **is** this wheel's own description page, so the installed package's
metadata carries the same text (`importlib.metadata.metadata("larkdocio").get_payload()`) — and in
`larkdocio.guide(section="credentials-env-setup-the-read-write-app-split")`.

## 5. Prove it works

```bash
larkdocio download "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./out/
```

A clean run drops Markdown (plus any images) into `./out/`. A refusal tells you which of the
three facts above is missing — wrong credentials, a missing scope (the body names it), or a
document the app cannot reach. If it fails in a way that does not mention any of the three, read
the next subsection before anything else.

### Wall — the IP allowlist, the one nothing warns you about (operator-observed console guidance)

An app can be configured to accept calls only from **listed IP addresses**. Until the address
your calls actually leave from is on that list, correct credentials and correct grants get you
nowhere — and this is the wall that is hardest to guess from the error, which is why it is
written down here at all.

- **What it looks like.** Every call fails the same way whichever document you point at —
  including, in the attempts behind this note, the credential exchange itself, before any
  document is involved. A refusal that does not change when you change the document is a strong
  hint that the wall sits below the document layer.
- **The fix path.** In the app's security or network settings, add the **public** address the
  calls leave from — not your machine's local address — and then release the version, like any
  other change. Re-run the command above.
- **What trips people repeatedly.** A laptop's public address moves. A different office, a home
  connection, a phone hotspot, or a company network that egresses through several addresses all
  produce a list that was correct yesterday, so a setup that worked and then stopped after you
  moved is this wall before it is anything else.
- **Where the truth is.** Whether the allowlist is enabled at all, what your console calls it,
  and which addresses count are console-side and tenant-side questions. Lark's console governs,
  and it is the authority over every sentence here.

## Where the full truth lives

Every file named in this table lives **in the source repository** — the clone that publishes this
wheel. Each row's second address is the one that answers from an installed wheel with nothing
else to hand, which is why both are given.

| Question | The answer's home |
|---|---|
| Every call site, endpoint, and scope, with evidence | `PERMISSIONS.md` — generated, never hand-kept — or `larkdocio.guide(section="permissions-what-to-ask-for")` |
| What the installed wheel can do at all | `larkdocio.capabilities()` — every surface self-describes; `larkdocio.capabilities(full=True)` adds which credential pair each one uses |
| Per-surface support matrices | `BLOCKS.md` · `SHEETS.md` · `BASE.md` — or `larkdocio.capabilities(full=True)`, whose per-surface rows carry the same support facts |
| This walkthrough, from an install | `larkdocio.lark_setup()` (and `larkdocio.lark_setup_sections()` for its index) |
