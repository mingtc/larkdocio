"""The leak-proof disposable-Base provisioner (LD-255 born MINIMAL here, LD-258 hardened it
in place — same path, same public names).

**Why this file exists now rather than later.** Three stories stand on this seam and they run
in different waves. The encoder story imports this helper without editing it; the hardening
story hardens it **in place** — same path, same public names — and the compiler story rides
whatever it has become. Born anywhere else, it would have to move, and a move is exactly the
kind of change that makes two parallel stories collide. So it is born **here**, deliberately
small, and every later change is an edit to this file rather than a relocation of it.

**What "minimal" means, precisely.** Create a Base, hand it to the caller, delete it in a
``finally``, and keep a persisted ledger so a delete that could not land is a **recorded
token** rather than a lost one. No populate / mutate / verify legs, no fixture library — those
are the hardening story's, and writing them here would be writing that story badly and early.
What is NOT deferred is the invariant they exist to protect:

* **Disposables only.** A token can enter this harness in exactly one way — through its own
  create. There is no code path that reads a configured document, sheet or Base token as a
  write destination, and no environment variable naming one is read anywhere in this file.
  The read fixtures are read fixtures; one of them holds hand-authored specimens the API
  cannot recreate, so writing it would destroy evidence rather than merely be impolite.
* **Delete in a ``finally``.** A crashed run still tries to clean up.
* **A greppable name.** Every Base is titled ``larkdocio-DISPOSABLE-<nonce>``, so a survivor is
  findable by name alone.
* **A survivor is never silent.** See below — this is the part measurement forced.

**THE MEASURED TEARDOWN LAG, and why a ledger is not optional here.** Deleting a Base is a
**drive-file** operation, and on this tenant a freshly created Base is **not reliably
addressable as a drive file for many minutes**. Measured while this harness was written: the
identical delete, against a Base the bitable API resolves happily, answered a rotating set of
three not-found-shaped codes for **over twenty minutes** — ``1061003`` *not found*, ``1065200``
*source node not found* and ``1061001`` *unknown error*, interleaved, with no monotonic
progression — and then succeeded on a first attempt later. Two sibling Bases behaved the same
way and were deleted cleanly once enough time had passed.

So a synchronous ``finally``-delete **cannot** be the whole contract on this tenant: the run
that must clean up is the run least able to. The contract this harness offers instead is
*"deleted, or **recorded** and sweepable"* — the ``finally`` attempts the delete on a short
budget, the ledger keeps every token it could not land with its last code, and
:func:`close_out` re-attempts each survivor and returns the ones that still resolve. Nothing is
forgiven and nothing is dropped: an unswept token is a name a human can act on, and
:func:`survivors` is the authoritative list. **Sweep a session's leftovers with**
``python -c "import sys; sys.path.insert(0,'tests'); import base_write_harness as h;
print(h.close_out())"``.

**THE LEDGER IS CROSS-SESSION, AND IT LIVES IN THE MAIN CHECKOUT (LD-275).** The lag above is
only half the danger; the other half is *where the record of it is kept*. On 2026-08-04 six
disposables outlived their runs while every session reported ``orphans = 0`` — and not one of
them appears in the surviving ledger. The mechanism was arithmetic, not API: the ledger path was
derived from *this file's* parent, so a leg running in a linked **git worktree** wrote its record
into the worktree, and ``git worktree remove`` deleted the only evidence that a token existed.
A per-run ``tmp_path`` ledger loses it the same way when pytest sweeps its temp dirs. So
:func:`durable_ledger_path` follows a linked worktree home to the **main checkout's** root (its
``.git`` is a file naming ``…/.git/worktrees/<name>``), and a caller that keeps its own per-run
ledger gets a **mirror**: every real token is recorded in the durable ledger *as well*, so the
next session inherits it. The mirror engages only for a provisioner whose SDK client is real
(:attr:`_Provisioner.mints_real_objects`) — an offline double must never write a live sweep
instruction. Because every arm's teardown calls ``close_out()`` with no arguments, that one call
now sweeps **prior sessions'** survivors too; :func:`sweep_stale` is the same sweep restricted to
entries older than the lag, for a session that wants to open by clearing the field.

**ONE SHARED FILE IS WRITTEN CONCURRENTLY, SO A FLUSH MERGES (LD-297).** Making the ledger
shared is what makes a lost update reachable: read-all-at-``__init__`` / write-all-at-flush means
the leg that flushes **last** writes back a list captured before the other leg's entries existed,
erasing them. So :class:`Ledger` never writes its snapshot — every mutation re-reads the file,
**upserts** its own entries onto it (keyed on ``kind`` + token), applies the mutation to the
merged list and replaces the file atomically, all inside an **exclusive OS-level lock** on a
sidecar ``<ledger>.lock``. The merge is not a plain union: ``deleted`` is **monotonic**, so a
stale snapshot's ``deleted: false`` can never retract a delete another leg watched land — the
sweep list shrinks by evidence only.

**ADOPTION IS OF THE *STALE* — a parallel leg's Base is not yours to delete (LD-275).** One
shared ledger is one shared sweep list, and two wave-runner legs run at once. So every create is
stamped with :data:`SESSION_ID`, and :func:`_adoptable` lets a sweep delete only what **this**
session minted or what has outlived :data:`LAG_HORIZON_SECONDS` — past which no run is plausibly
still writing to it. An inherited young entry is neither deleted nor judged: it is reported
``pending`` and left on the list for the session that owns it, or for the one after the horizon.

**A NOT-FOUND ANSWER IS NOT PROOF ON ITS OWN (LD-275).** The oracle below asks the bitable API
whether an object is gone — but asked *inside* the addressability window about a token whose
delete never landed, a single ``1002`` / ``91402`` is exactly what a **live** Base can answer,
and scoring it ``gone`` retires the token from every future sweep. So a disappearance must be
**corroborated**: either the delete itself landed (``code:0`` or *already deleted* —
:data:`DELETE_LANDED_CODES`), or the entry has outlived :data:`LAG_HORIZON_SECONDS`. Otherwise
the verdict is :data:`VERDICT_PENDING` — *not yet observed gone* — and :func:`orphans` reports it
rather than swallowing it. ``orphans() == []`` therefore now means "every token verified gone",
which is the claim the gates were always taken to be making.

**THE ORPHAN ORACLE IS THE BITABLE API — never Drive metadata** (the Base read spec **D3**, made
executable here). An object this harness created is cleaned up when ``GET /bitable/v1/apps/{a}``
answers **1002** or **91402** (an app), or a table path — ``GET
/bitable/v1/apps/{a}/tables/{t}/fields`` — answers **1254041** (a table; the code is a real
capture, ``tests/captures/base-study/captures/02-bitable18-fields.json``). It is emphatically **not**
Drive: ``POST /drive/v1/metas/batch_query`` still returns a deleted Base's title and timestamps
for ever (``tests/captures/base-study/captures/07-orphan-sweep.json``), so an oracle built on Drive
metadata would report a **false orphan in perpetuity**. That residue is **inert**, not a leak.
:func:`orphans` is the executable form: every ledger token the bitable API still resolves.

**WHAT ACCRETES AND CANNOT BE PURGED — read this before adding a leg.** Three facts, none of
them fixable by being tidier. The first two are authored in ``BASE.md``'s limitation register,
**row 9** and **row 10**; they are *cited* here, not re-stated as truth, because a guarded fact
with two homes drifts from itself.

1. **``DELETE`` is TRASH, not purge (register row 9).** ``DELETE
   /drive/v1/files/{a}?type=bitable`` returns ``code:0`` and the bitable API then reports
   ``1002`` — but no open-API verb *purges* an app, and a deleted **table** sits in its Base's
   trash the same way (``dev/base-study/p0-addendum-2026-08-03.md`` § 6). A swept run leaves
   trash behind by design; that is the tenant's state, not a harness defect.
2. **Uploaded media accretes with NO purge verb at all (register row 10).** A
   ``bitable_file`` / ``bitable_image`` ``file_token`` survives its table's deletion and there
   is **no purge verb** for it anywhere in the open API — the P0 pack left four such tokens
   orphaned under a table that no longer exists. This harness **did** refuse to upload media
   for exactly that reason (the Base write spec § O3′) until the attachment leg was scoped; the maintainer then
   **bought that residue knowingly** to buy a hash-verified round trip, so :func:`attach_media`
   now exists and **mints something nothing can reclaim, on purpose**. The answer is
   disclosure, not a simulated purge: every token is written to the ledger with its
   ``parent_type`` and its disposable's app_token (:meth:`Ledger.record_media`), there is **no
   media delete leg here and there cannot be one**, and the ``orphans() == []`` claim below is
   made against the **bitable** liveness definition with **media residue explicitly outside
   it**. :func:`media_residue` is the standing list.
3. **``app.revision`` moves on every structural op and cannot be restored.** The P0 probe pack
   moved the Scratch Base ``0 → 14`` and P1 moved another ``0 → 5``; no verb winds it back.
   This is the deepest reason the gate provisions its own Base instead of writing a read
   fixture: a revision counter is a one-way door.

**THE SCRATCH BASE IS A READ FIXTURE, AND IT IS UNTOUCHABLE (O2′).** It holds the maintainer's six
records and the only hand-authored **Lookup**, **Email** and **Stage** fields in existence —
un-authorable types the API *cannot* recreate — and L1's registry fixtures and cross-time live
canary depend on them. The enforcement here is an **allow-list, not a deny-list**: a token
enters this harness in exactly one way, through its own create (or through a ledger entry that
one wrote), and :class:`NonDisposableTargetError` refuses everything else. So the Scratch Base
is refused **without this file naming it** — which is both stronger than a deny-list (every
pre-existing Base is refused, not just the one we remembered) and what keeps the landed
"names no configured target at all" guard true. The maintainer's free-fire grant is not a licence for
this gate to write it. *(If a live arm ever needs an un-authorable column, the sanctioned route
is ``POST …/apps/{a}/copy`` — the only API route that produces one — inside this harness,
deleted after; copy is **async** (``1254036``), so poll rather than assume the token is usable.)*

**THE PREFIX IS ENFORCED, NOT CONVENTIONAL.** :meth:`_Provisioner.create` refuses a title that
does not start with ``larkdocio-DISPOSABLE-`` **before** it touches the SDK, so an object this
harness made can always be found by a human trash sweep with one grep.

**Gentle.** Create and delete both pass a limiter at the spacing the probe packs sustained, and
nothing here retries on a rate limit.

**Skips loudly.** :func:`missing_reason` returns a sentence naming exactly what is absent, so a
credential-less run says so instead of passing silently.
"""
import json
import os
import time
import uuid

try:                                  # POSIX only; the ledger lock degrades to a no-op without it
    import fcntl
except ImportError:                   # pragma: no cover - not reachable on this project's platforms
    fcntl = None
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableField,
    AppTableFieldProperty,
    CreateAppRequest,
    CreateAppTableFieldRequest,
    GetAppRequest,
    ListAppTableFieldRequest,
    ReqApp,
)
from lark_oapi.api.drive.v1 import DeleteFileRequest

from larkdocio.base.errors import raise_for_base_code
from larkdocio.base.media import BaseMediaClient
from larkdocio.common.auth import WRITE_ENV, get_write_credentials
from larkdocio.common.transport import RateLimiter

#: The greppable disposable-title prefix. Every Base this harness creates carries it.
DISPOSABLE_TITLE_PREFIX = "larkdocio-DISPOSABLE-"

#: A Base is a drive file of this type, which is what the delete leg addresses it as.
DRIVE_FILE_TYPE = "bitable"

#: Same pace as the shipped clients: 50 calls a minute is a 1.2 s spacing.
HARNESS_MAX_CALLS_PER_WINDOW = 50
HARNESS_RATE_WINDOW_SECONDS = 60.0

#: **The create/delete consistency lag, measured on this tenant.** A Base created minutes
#: earlier is not yet addressable as a drive file: the delete answers one of these three
#: not-found-shaped codes — interleaved, with no monotonic progression — while the bitable API
#: resolves the very same token happily. `1061001` reads as *unknown error* but was observed
#: rotating with the other two against the same token in the same minute, which is what puts it
#: here rather than in the genuine-failure branch. These three are reported to the ledger; every
#: other non-zero code is raised typed, because a refusal about the caller is not a lag.
NOT_YET_ADDRESSABLE_CODES = (1061003, 1065200, 1061001)

#: **Already gone — a SUCCESS-shaped answer, not a lag and not a failure.** ``1061007``
#: (*"file has been delete"*) is what the drive delete answers for a token that is already in
#: the trash: the outcome the caller asked for has happened. Reported ``deleted`` rather than
#: raised, because a ``finally`` that raises on *"it is already gone"* turns a clean teardown
#: into a red test — and rather than filed as a lag, because a lag is retried and this has
#: nothing left to retry. Found by LD-270's arm on its second run over a ledger whose entry the
#: first run had left behind and the tenant had since released.
ALREADY_DELETED_CODES = (1061007,)

#: Codes that mean the Base really is gone — the positive proof a delete landed. The APP half
#: of the orphan oracle (D3): asked of the **bitable** API, never of Drive metadata.
DELETED_CODES = (1002, 91402)

#: The TABLE half of the same oracle. A table path — the field list — answers `1254041
#: TableIdNotFound` once the table is gone; the code is a real capture
#: (`tests/captures/base-study/captures/02-bitable18-fields.json`), not a guess.
TABLE_DELETED_CODES = (1254041,)

#: How many attempts the ``finally`` spends, and how long between them. Deliberately SHORT:
#: the measured lag runs to tens of minutes, so a budget large enough to beat it would turn
#: every live run into a stall. The budget catches the fast case; the ledger catches the rest.
DELETE_ATTEMPTS = 3
DELETE_RETRY_SECONDS = 2.0

#: Codes that mean the delete ITSELF landed — the corroboration that turns a later not-found
#: answer into proof. ``None`` is here because a transport that returned no code at all has
#: already been treated as success by :meth:`_Provisioner.delete` since LD-258.
DELETE_LANDED_CODES = (0, None) + ALREADY_DELETED_CODES

#: How long a not-found answer stays UNTRUSTWORTHY for a token whose delete never landed. The
#: measured addressability lag ran to "over twenty minutes" (module docstring); thirty is that
#: measurement with a margin. Past it, a bitable API that will not serve the app is proof — a
#: shorter horizon re-opens LD-275's hole, a longer one only delays a sweep.
LAG_HORIZON_SECONDS = 30 * 60

#: The three verdicts :func:`liveness_verdict` can reach. ``PENDING`` is the one LD-275 added:
#: *not yet observed gone*, which is neither a clean sweep nor a proven leak.
VERDICT_ALIVE = "alive"
VERDICT_GONE = "gone"
VERDICT_PENDING = "pending"

#: **The one field that may take a row out of the orphan oracle's probe set (LD-535).** An ISO
#: stamp written by — and ONLY by — a code path that has just watched :func:`liveness_verdict`
#: reach :data:`VERDICT_GONE` on a *fresh bitable probe answer* for that token. So it is not a
#: new judgement: it is the judgement the oracle already made and then threw away, written down.
#: What it deliberately is NOT is ``deleted: true``. A delete's own answer is a claim about a
#: *drive file* (LD-275: six Bases leaked past a green gate on exactly that claim; **D-55** — a
#: read-back, never a ``code: 0``), so a ``deleted: true`` row carrying no stamp keeps being
#: asked, for ever, which is the pre-LD-535 behaviour unchanged. Absent-means-probe-it is the
#: fail-safe default, and it is also why this needs no migration: an unstamped legacy file is
#: exactly a file whose every row is still in the probe set.
PROBE_GONE_FIELD = "probe_gone_at"

#: Who minted a token, stamped on every ``record_create``. One shared ledger means one shared
#: sweep list, so the sweep needs to tell *its own* survivors from a **parallel leg's Base that
#: is still being written to** — see :func:`_adoptable`.
SESSION_ID = uuid.uuid4().hex

#: The ledger's filename. It sits at the **main checkout's** root and is gitignored: a record of
#: live state, not source.
LEDGER_FILENAME = ".base-disposables.json"

#: The sidecar the read-modify-write window locks (LD-297). A sidecar rather than the ledger
#: itself because the ledger is replaced atomically (``os.replace``), and a lock held on a file
#: that is about to become a different inode guards nothing.
LEDGER_LOCK_SUFFIX = ".lock"


@contextmanager
def ledger_lock(path):
    """Hold an exclusive OS-level lock over one ledger's read-modify-write window (LD-297).

    ``fcntl.flock`` on ``<path>.lock``, which is the same primitive ``.kanban-wt`` serializes its
    board ops with. Where ``fcntl`` does not exist the lock degrades to a no-op: the merge below
    is still correct for the sequential case, and this harness's live legs are POSIX-only.
    """
    if fcntl is None:
        yield
        return
    lock_path = Path(str(path) + LEDGER_LOCK_SUFFIX)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _worktree_home(git_file, fallback):
    """The main checkout's root behind a linked worktree's ``.git`` FILE, or ``fallback``.

    A linked worktree's ``.git`` holds ``gitdir: <main>/.git/worktrees/<name>``, which is the
    one durable pointer from a directory that is about to be deleted back to the one that is
    not. Parsed rather than shelled out to, so this stays a pure-file question with no git
    dependency and an offline test.
    """
    text = git_file.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir:"):
        return fallback
    gitdir = Path(text.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = git_file.parent / gitdir
    parts = gitdir.parts
    if "worktrees" in parts:
        common = Path(*parts[:parts.index("worktrees")])
        if common.name == ".git":
            return common.parent
    return fallback


def durable_ledger_path(start=None):
    """Where the cross-session ledger lives — the **main checkout's** root (LD-275).

    The ledger must outlive the process that wrote it *and* the directory that ran it: the six
    Bases that leaked on 2026-08-04 were recorded into ``/tmp/wt-*`` worktrees that a runner
    deleted minutes later, which is why every session could truthfully report ``orphans = 0``.
    So a linked worktree resolves to the checkout it was made from, and a plain checkout to its
    own root.
    """
    here = Path(start).resolve() if start is not None else Path(__file__).resolve()
    for candidate in here.parents:
        git = candidate / ".git"
        if git.is_dir():
            return candidate / LEDGER_FILENAME
        if git.is_file():
            return _worktree_home(git, candidate) / LEDGER_FILENAME
    return here.parent.parent / LEDGER_FILENAME


#: The persisted ledger — the authoritative sweep list, resolved to the main checkout so a
#: worktree-run leg cannot take its only record of a live Base to the grave with it.
LEDGER_PATH = durable_ledger_path()

DOMAIN_DEFAULT = "larksuite.com"


class Ledger:
    """Every disposable this harness created, on disk, with whether it was deleted.

    One entry per create — ``{kind: "base", app_token, title, created_at, deleted, last_code}``
    — appended on create and updated on a successful delete. A delete that could not land
    leaves ``deleted: false`` with its last code: the token is **flagged, never dropped**,
    which is what makes an unswept Base a name somebody can act on instead of a silence.

    **The MEDIA half (LD-268), an extension of this ledger rather than a second one.** An
    uploaded ``file_token`` is recorded as ``{kind: "media", file_token, parent_type,
    app_token, created_at}`` and is **never marked deleted, because it never can be** — no
    open-API verb purges drive media (register row 10). Two kinds in one file, because the
    sweep question a human asks is *"what did this repository's live runs leave behind?"* and
    two files would let one of the answers rot. Everything that sweeps — :meth:`survivors`,
    :func:`close_out`, :func:`orphans` — reads only the **base** entries, so a media token can
    never be mistaken for something a delete could reach; a legacy entry with no ``kind`` is a
    base entry, which is what it was.

    **EVERY MUTATION IS A LOCKED MERGE, NEVER A WRITE-BACK (LD-297).** One shared file plus two
    parallel legs is a lost update: the second flusher's snapshot predates the first's entries and
    would erase them, which is LD-275's unnameable leaked Base re-cut at a different angle. So a
    mutation takes an exclusive lock (:func:`ledger_lock`), re-reads the file, **upserts** this
    instance's entries onto it keyed on ``kind`` + token, applies the mutation to the *merged*
    list, and replaces the file atomically. The union is deliberately asymmetric: ``deleted`` is
    **monotonic**, so a stale ``deleted: false`` never resurrects a verified-deleted entry as
    pending, and the merged entry keeps the ``last_code`` of whichever half saw it go.

    **ARCHIVAL, IN PLACE (LD-535).** The file is append-only by construction and
    :func:`orphans` used to re-ask the bitable API about every base row it had ever held, so the
    cost of the safety machinery grew with the whole history of disposables rather than with what
    is outstanding. A row now leaves the *probe set* — and nothing else — when a probe has
    corroborated its disappearance, recorded as :data:`PROBE_GONE_FIELD` by
    :meth:`record_probe_gone`. Three things that policy deliberately does **not** do. It does not
    delete or relocate anything: the row stays in this file, in place, greppable
    (:meth:`archived`), because *"an archived entry must stay a recorded datum, never a forgotten
    one"*. It does not touch the **media** half — a media row is never stamped, so
    :meth:`media` counts exactly what it counted before; the residue stays *countable rather than
    merely acknowledged*. And it does not trust ``deleted: true``: only a probe's own answer buys
    the exit, which is LD-275's lesson kept whole. ``deleted`` and the stamp are both monotonic,
    and the stamp is applied through the same locked merge as every other mutation, so an
    archival cannot amputate a parallel leg's list either.
    """

    #: The two ledger entry kinds. ``media`` entries are records of permanent residue.
    BASE_KIND = "base"
    MEDIA_KIND = "media"

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else LEDGER_PATH
        self._entries = self._read()

    def _read(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return []

    @staticmethod
    def _key(entry):
        """What makes two rows the same record — the identity a merge upserts on."""
        kind = entry.get("kind", Ledger.BASE_KIND)
        if kind == Ledger.MEDIA_KIND:
            return (kind, entry.get("file_token"))
        return (kind, entry.get("app_token"))

    @staticmethod
    def _reconcile(mine, theirs):
        """One record as both halves see it. Mine wins on ordinary fields — a caller that just
        edited its copy meant it — but ``deleted`` is **monotonic**: a Base does not come back,
        so a ``true`` from either half stands, carrying that half's ``last_code`` with it."""
        merged = dict(mine)
        for field, value in theirs.items():
            if merged.get(field) is None:
                merged[field] = value
        mine_gone, theirs_gone = bool(mine.get("deleted")), bool(theirs.get("deleted"))
        if theirs_gone and not mine_gone:
            merged["deleted"] = True
            merged["last_code"] = theirs.get("last_code")
        else:
            merged["deleted"] = mine_gone or theirs_gone
        return merged

    def _merged_with_disk(self):
        """This instance's entries upserted onto whatever is on disk **now**. Call under the
        lock: it is the read half of the read-modify-write window."""
        merged = [dict(entry) for entry in self._entries]
        seen = {}
        for position, entry in enumerate(merged):
            seen.setdefault(self._key(entry), position)
        for entry in self._read():
            key = self._key(entry)
            if key in seen:
                merged[seen[key]] = self._reconcile(merged[seen[key]], entry)
            else:
                seen[key] = len(merged)
                merged.append(entry)
        return merged

    def _write(self, entries):
        """Replace the file atomically, so a concurrent reader sees one whole list or the
        other — never the torn middle of a rewrite."""
        payload = json.dumps(entries, ensure_ascii=False, indent=2)
        tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)

    def _mutate(self, apply_to=None):
        """The one write path: lock → re-read → merge → mutate → replace → adopt the merge."""
        with ledger_lock(self.path):
            merged = self._merged_with_disk()
            if apply_to is not None:
                apply_to(merged)
            self._write(merged)
            self._entries = merged

    def _flush(self):
        """Persist this instance's view **without losing anybody else's** (LD-297)."""
        self._mutate()

    @property
    def entries(self):
        """The **base** entries — every disposable Base this harness created.

        Deliberately still the base half only: every caller of this property is a sweep, and a
        sweep over a media token would be a delete attempt on something no verb deletes. The
        media half has its own accessor, :meth:`media`.
        """
        return [e for e in self._entries
                if e.get("kind", self.BASE_KIND) == self.BASE_KIND]

    @property
    def all_entries(self):
        """Every entry of every kind, in write order — the raw file."""
        return list(self._entries)

    def media(self):
        """Every media ``file_token`` this repository's live runs have minted.

        **There is no sweep for this list.** It is a disclosure: each entry names the token,
        which ``parent_type`` minted it and which disposable it was attached to, so the residue
        this project has created is countable rather than merely acknowledged.
        """
        return [e for e in self._entries if e.get("kind") == self.MEDIA_KIND]

    def record_create(self, app_token, title):
        row = {
            "kind": self.BASE_KIND,
            "app_token": app_token,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session": SESSION_ID,
            "deleted": False,
            "last_code": None,
        }
        self._mutate(lambda entries: entries.append(row))

    def record_media(self, file_token, parent_type, app_token):
        """Record one minted media token. **Permanent by construction** — there is no
        ``record_media_delete``, because there is no verb it could report.

        **And no archival either (LD-535).** A media row is never stamped
        :data:`PROBE_GONE_FIELD` — :meth:`record_probe_gone` refuses it by ``kind`` — so
        :meth:`media` and :func:`media_residue` count exactly what they counted before the
        probe set was ever narrowed. There is nothing to corroborate: the oracle that could
        stamp a row is a *bitable* question, and this is not a bitable object."""
        row = {
            "kind": self.MEDIA_KIND,
            "file_token": file_token,
            "parent_type": parent_type,
            "app_token": app_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._mutate(lambda entries: entries.append(row))

    def record_delete(self, app_token, code, deleted):
        """Write one delete's outcome down. Applied to the **merged** list, so a sweep's verdict
        lands on an adopted entry this instance never held in memory — and never downgrades an
        entry already recorded gone, because a Base does not come back (LD-297)."""
        def mark(entries):
            for entry in entries:
                if entry.get("kind", self.BASE_KIND) != self.BASE_KIND:
                    continue
                if entry["app_token"] != app_token:
                    continue
                if entry.get("deleted") and not deleted:
                    continue
                entry["deleted"] = bool(deleted)
                entry["last_code"] = code

        self._mutate(mark)

    def record_probe_gone(self, app_tokens):
        """Stamp the rows a **probe** has just corroborated gone (LD-535) — the only exit from
        the probe set, and the only writer of :data:`PROBE_GONE_FIELD`.

        Callers hand over tokens they watched :func:`liveness_verdict` score
        :data:`VERDICT_GONE` *against a fresh bitable answer*. The three refusals below are the
        fence, and they live here rather than in the callers so that no future call site can
        route around them:

        * **a media row is never stamped** — it is not in the probe set, it is a disclosure, and
          there is no verb that could make it gone (:meth:`record_media`);
        * **a survivor is never archived** — a row still reading ``deleted: false`` stays on the
          sweep list and in the probe set whatever a probe said, because :func:`close_out` and
          :meth:`survivors` are the authorities on that half and a row hidden from the oracle
          while still listed as a survivor would be two answers to one question;
        * **the stamp is monotonic** — the first corroboration stands, so a re-probe cannot
          re-date it. No new merge rule was needed for that: :meth:`_reconcile` already carries
          a field the other half is missing, so a stale instance's write-back cannot drop it.

        Applied through :meth:`_mutate`, i.e. the same lock → re-read → merge → replace window
        as every other mutation (LD-297); an empty token list writes nothing at all, so an
        oracle run that corroborates nothing new leaves the file untouched.
        """
        wanted = {token for token in app_tokens}
        if not wanted:
            return
        stamp = datetime.now(timezone.utc).isoformat()

        def mark(entries):
            for entry in entries:
                if entry.get("kind", self.BASE_KIND) != self.BASE_KIND:
                    continue
                if entry.get("app_token") not in wanted:
                    continue
                if not entry.get("deleted"):
                    continue
                if entry.get(PROBE_GONE_FIELD):
                    continue
                entry[PROBE_GONE_FIELD] = stamp

        self._mutate(mark)

    def probe_set(self):
        """The base rows the orphan oracle still has to ASK the bitable API about (LD-535).

        Every base entry **except** the ones a probe corroborated gone. The default is to ask:
        a row with no :data:`PROBE_GONE_FIELD` is in this list, which is what makes a legacy
        file — and a hand-edited one — safe with no migration.
        """
        return [e for e in self.entries if not e.get(PROBE_GONE_FIELD)]

    def archived(self):
        """The base rows a probe corroborated gone — **recorded, not forgotten** (LD-535).

        They are still in this file, still carrying their token, title, session and
        ``last_code``; ``grep probe_gone_at`` is the whole retrieval story. The complement of
        :meth:`probe_set` over :attr:`entries`, so the two partition the base half exactly.
        """
        return [e for e in self.entries if e.get(PROBE_GONE_FIELD)]

    def survivors(self):
        """Every **Base** token the ledger still believes exists.

        Deliberately over :attr:`entries` — the WHOLE base half, archived rows included — so
        the sweep list is what it always was. Archival narrows the oracle's probe set and
        nothing else (LD-535).
        """
        return [e for e in self.entries if not e.get("deleted")]


def _entry_age_seconds(entry, now):
    """How long ago this entry's create was recorded. An entry with no readable stamp counts as
    settled — it predates the field, so it cannot be a token from the current lag window."""
    stamp = entry.get("created_at")
    if not stamp:
        return float("inf")
    try:
        created = datetime.fromisoformat(stamp)
    except ValueError:
        return float("inf")
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created).total_seconds()


def _delete_landed(entry):
    """True when the delete's own answer said the file went away."""
    return bool(entry.get("deleted")) and entry.get("last_code") in DELETE_LANDED_CODES


def _adoptable(entry, now):
    """True when this sweep may issue a DELETE for ``entry`` (LD-275).

    The cross-session ledger cuts both ways: it is what stops a token dying with the worktree
    that minted it, and it is also what puts a **parallel leg's in-flight disposable** on this
    session's sweep list. So adoption is of the *stale* — the issue's own wording. An entry this
    session minted is always ours to finish; an inherited one is somebody else's until it has
    outlived :data:`LAG_HORIZON_SECONDS`, past which no run is plausibly still using it. An
    entry with no ``session`` stamp predates the field and is therefore inherited too.
    """
    if entry.get("session") == SESSION_ID:
        return True
    return _entry_age_seconds(entry, now) >= LAG_HORIZON_SECONDS


def liveness_verdict(entry, still_resolves, now=None):
    """One of :data:`VERDICT_ALIVE` / :data:`VERDICT_GONE` / :data:`VERDICT_PENDING` (LD-275).

    ``still_resolves`` is the bitable API's raw answer for this entry's token. The judgement it
    is folded into is the LD-275 fix: a not-found answer is proof only when the delete itself
    landed, or when the entry has outlived :data:`LAG_HORIZON_SECONDS` — because inside that
    window a **live** Base can answer ``1002`` / ``91402`` too, and a token retired on that
    evidence is a leak nothing will ever find again.
    """
    if still_resolves:
        return VERDICT_ALIVE
    if _delete_landed(entry):
        return VERDICT_GONE
    now = now if now is not None else datetime.now(timezone.utc)
    if _entry_age_seconds(entry, now) >= LAG_HORIZON_SECONDS:
        return VERDICT_GONE
    return VERDICT_PENDING


class HarnessError(Exception):
    """A provisioning failure — a create that returned no token, or a delete that failed.

    Loud by design: a harness that silently yielded a bogus token, or silently leaked a real
    Base, would be worse than no harness at all.
    """


class NonDisposableTitleError(HarnessError):
    """A create whose title does not carry :data:`DISPOSABLE_TITLE_PREFIX`.

    Raised **before** the SDK is touched. A Base created under any other name is one a human
    trash sweep cannot find, which is the whole reason the prefix is enforced rather than
    merely conventional.
    """


class NonDisposableTargetError(HarnessError):
    """An attempt to address a token this harness did not create.

    The allow-list refusal that makes the Scratch Base — and every other pre-existing Base —
    untouchable **without naming any of them**. A token becomes addressable in exactly one way:
    :meth:`_Provisioner.create` minted it, or the ledger recorded that create and
    :meth:`_Provisioner.adopt_from_ledger` re-admitted it for the sweep.
    """


def disposable_title(nonce=None):
    """A greppable disposable title: ``larkdocio-DISPOSABLE-<nonce>``."""
    if nonce is None:
        nonce = f"{int(time.time())}-{os.getpid()}"
    return f"{DISPOSABLE_TITLE_PREFIX}{nonce}"


def is_disposable_title(title):
    """True iff ``title`` was minted by :func:`disposable_title`."""
    return isinstance(title, str) and title.startswith(DISPOSABLE_TITLE_PREFIX)


def missing_reason():
    """A sentence naming what is missing, or ``None`` when the harness can run."""
    app_id, app_secret = get_write_credentials()
    if not (app_id and app_secret):
        return (f"no write credentials: set {WRITE_ENV[0]} and {WRITE_ENV[1]} to run the "
                f"live Base write arm")
    return None


def _sdk_client(domain=DOMAIN_DEFAULT, timeout=30):
    app_id, app_secret = get_write_credentials()
    return lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .domain(f"https://open.{domain}") \
        .log_level(lark.LogLevel.ERROR) \
        .timeout(timeout) \
        .build()


#: The destination a provisioner over a FAKE SDK sends. It names nothing on any tenant: an
#: offline double creates nothing, so the disposables folder is neither needed nor consulted,
#: and a skip there would be noise rather than protection.
OFFLINE_DESTINATION = "fldrOFFLINEDOUBLEDESTINATION"


class _Provisioner:
    """Create and delete, both paced through one limiter."""

    def __init__(self, sdk=None, rate_limiter=None, domain=DOMAIN_DEFAULT):
        self._sdk = sdk if sdk is not None else _sdk_client(domain)
        self._limiter = rate_limiter if rate_limiter is not None else RateLimiter(
            HARNESS_MAX_CALLS_PER_WINDOW, window=HARNESS_RATE_WINDOW_SECONDS)
        #: THE ALLOW-LIST. Every token this provisioner may address; the only writers are
        #: `create` and `adopt_from_ledger`, and the ledger is only ever appended by a create.
        self._own = set()
        #: The media client, built lazily over the same SDK client and the same limiter.
        self._media = None

    @property
    def mints_real_objects(self):
        """True when this provisioner's SDK client is the real one — i.e. when the tokens it
        hands out name objects on a live tenant.

        The mirror in :func:`disposable_base` keys off this and nothing else. A fake SDK's token
        written into the durable ledger would be a **live sweep instruction** for something that
        never existed, so the discriminator is the client itself rather than an argument a
        caller could get wrong.
        """
        return isinstance(self._sdk, lark.Client)

    def _paced(self, call, request):
        self._limiter.acquire()
        return call(request)

    def _require_own(self, app_token):
        """Refuse a token this harness did not create. The Scratch Base is refused here, along
        with every other pre-existing Base — by allow-list, so nothing has to be named."""
        if app_token not in self._own:
            raise NonDisposableTargetError(
                f"{app_token!r} was not created by this harness, so it is not a disposable and "
                f"will not be addressed. A token enters only through create(); read fixtures — "
                f"including the Base holding the hand-authored specimens — are never a write "
                f"target")

    def adopt_from_ledger(self, ledger):
        """Re-admit the tokens a *previous* run's create recorded, so a sweep can address them.

        The only route into the allow-list that is not a create in this process — and it is
        still a create, one whose record survived the process. The title is re-checked, so a
        hand-edited ledger cannot smuggle a non-disposable in.
        """
        for entry in ledger.entries:
            title = entry.get("title")
            if not is_disposable_title(title):
                raise NonDisposableTargetError(
                    f"ledger entry {entry.get('app_token')!r} is titled {title!r}, which is not "
                    f"a {DISPOSABLE_TITLE_PREFIX} disposable — refusing to sweep it")
            self._own.add(entry["app_token"])
        return self

    def create(self, title, time_zone=None, *, folder_token=None):
        """Create the disposable. ``time_zone`` declares the Base's own zone and is sent **only
        when supplied**, so the zone-free create's body is otherwise byte-identical to what it
        has always been — which is what makes it usable as the reverted-fix control for the date
        round-trip (a Base with no declared zone is exactly what this library used to mint).

        ``folder_token`` is **where** the disposable goes; omitted, it is read from
        ``LARKDOCIO_DISPOSABLES_FOLDER`` and the caller **SKIPS LOUDLY** when that is unset.
        The harness no longer lets a Base land in the application's own space: that space has no
        human interface, so a Base created there could not be seen — nor its trash listed — by
        the account holder. This is the house half of the caller-supplied-destination rule.
        """
        if folder_token is None:
            import canary_support

            # The environment is consulted ONLY when this provisioner mints real objects.
            # A fake SDK creates nothing anywhere, so there is nothing to protect and the
            # offline suite must not skip — but the key still travels, so the body an
            # offline test inspects is the body a live run sends.
            folder_token = (canary_support.require_disposables_folder()
                            if self.mints_real_objects else OFFLINE_DESTINATION)
        if not is_disposable_title(title):
            raise NonDisposableTitleError(
                f"{title!r} does not start with {DISPOSABLE_TITLE_PREFIX!r}; every object this "
                f"harness creates must be greppable in a human trash sweep")
        body = ReqApp.builder().name(title).folder_token(folder_token)
        if time_zone:
            body = body.time_zone(time_zone)
        request = CreateAppRequest.builder() \
            .request_body(body.build()) \
            .build()
        response = raise_for_base_code(
            self._paced(self._sdk.bitable.v1.app.create, request),
            context=f"create the disposable Base {title}", credential_env=WRITE_ENV)
        app = getattr(response.data, "app", None)
        token = getattr(app, "app_token", None)
        if not token:
            raise HarnessError(f"the create of {title} returned no app_token")
        self._own.add(token)
        return token, getattr(app, "default_table_id", None)

    def delete(self, app_token, attempts=DELETE_ATTEMPTS):
        """Try to delete the Base. Returns ``(deleted, last_code)`` — it does not raise.

        A ``finally`` must **record** an outcome, never raise on the way out of a failing
        test, and on this tenant the outcome genuinely can be *"not yet"*: the delete is a
        drive-file operation and a freshly created Base is not reliably addressable as one for
        many minutes (module docstring, with the measurement). The not-found-shaped codes are
        therefore reported rather than thrown, and the ledger keeps the token.

        Any OTHER non-zero code is a real failure and is raised typed — a refusal about who the
        caller is, or about the request, is not a consistency lag and must not be filed as one.
        Nothing is retried on a rate limit, which would be a probe by another name.
        """
        self._require_own(app_token)
        request = DeleteFileRequest.builder() \
            .file_token(app_token) \
            .type(DRIVE_FILE_TYPE) \
            .build()
        last = None
        for attempt in range(max(1, attempts)):
            response = self._paced(self._sdk.drive.v1.file.delete, request)
            last = getattr(response, "code", None)
            if last in (0, None) or last in ALREADY_DELETED_CODES:
                return True, last
            if last not in NOT_YET_ADDRESSABLE_CODES:
                raise_for_base_code(
                    response, context=f"delete the disposable Base {app_token}",
                    credential_env=WRITE_ENV)
            if attempt + 1 < attempts:
                time.sleep(DELETE_RETRY_SECONDS)
        return False, last

    def raw_create_field(self, app_token, table_id, *, field_name, field_type, ui_type,
                         formula_expression=None, property_body=None):
        """``POST …/fields`` with the body assembled **here** — the probe seam.

        The shipped library refuses some bodies locally, on committed evidence: a ``Formula``
        whose expression references another column authors a column that never computes, and
        that refusal is enforced in the request builder every seam goes through. A probe that
        measures **the server** has to be able to send exactly the refused body, or the
        refusal outlives its evidence with nothing left able to re-test it. So the bypass
        lives HERE, in the harness, where every target is allow-listed and disposable — and
        never on the shipped client, where it would be the footgun itself.

        ``property_body`` is the same bypass one level up (LD-317): the minimal-form sweep has
        to send a ``property`` the shipped builder would refuse — including the **absence** of
        one for a kind the registry marks required — so the dict is passed through verbatim
        rather than routed through ``build_property``.
        """
        self._require_own(app_token)
        builder = AppTableField.builder().field_name(field_name).type(field_type)
        if ui_type is not None:
            builder = builder.ui_type(ui_type)
        if formula_expression is not None:
            builder = builder.property(
                AppTableFieldProperty.builder().formula_expression(formula_expression).build())
        elif property_body is not None:
            if isinstance(property_body, dict):
                prop = AppTableFieldProperty.builder().build()
                for key, value in property_body.items():
                    setattr(prop, key, value)
            else:  # an already-built property — e.g. one the shipped build_property made
                prop = property_body
            builder = builder.property(prop)
        request = CreateAppTableFieldRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(builder.build()) \
            .build()
        response = raise_for_base_code(
            self._paced(self._sdk.bitable.v1.app_table_field.create, request),
            context=f"create the probe column {field_name!r} in {table_id}",
            credential_env=WRITE_ENV)
        return response.data.field

    def upload_media(self, app_token, *, data, name, parent_type):
        """Upload ``data`` as attachment media **onto a disposable this harness created**.

        **The allow-list guards ``parent_node``, and that is the whole point of putting this
        leg here.** ``parent_node`` is not a write target — no record is written and no table
        is touched — so a check that only guarded write targets would miss it entirely, and an
        upload's residue **cannot be undone even by deleting the Base**. :meth:`_require_own`
        therefore runs first, refusing the configured Scratch Base along with every other
        pre-existing Base, by allow-list, without naming any of them.

        The shipped client does the call: this harness owns *which Base may be a parent_node*,
        not *how an upload is made*.
        """
        self._require_own(app_token)
        return self._media_client().upload(
            data=data, name=name, parent_type=parent_type, parent_node=app_token)

    def download_media(self, file_token):
        """Download a media token's bytes for **hashing**. Mints no residue: the token already
        exists, and a download creates nothing."""
        return self._media_client().download(file_token)

    def _media_client(self):
        """The shipped media client over this provisioner's own paced SDK client, so an upload
        is spaced exactly like every other call this harness makes."""
        if self._media is None:
            self._media = BaseMediaClient("", "", sdk_client=self._sdk,
                                          rate_limiter=self._limiter)
        return self._media

    def is_gone(self, app_token):
        """``True`` when the **bitable API** no longer resolves the app — the orphan oracle.

        Drive is not asked, and must never be: ``metas/batch_query`` answers for a deleted Base
        for ever (module docstring), so a Drive-based oracle reports a false orphan in
        perpetuity. This is the app half of D3; :meth:`table_is_gone` is the table half.
        """
        self._require_own(app_token)
        response = self._paced(self._sdk.bitable.v1.app.get,
                               GetAppRequest.builder().app_token(app_token).build())
        return getattr(response, "code", None) in DELETED_CODES

    def table_is_gone(self, app_token, table_id):
        """``True`` when a **table path** no longer resolves — ``1254041``, the table half.

        The harness creates no standalone table today (a fresh Base arrives with its default
        one), so nothing in this file calls it on the happy path; it exists because the oracle
        is defined over objects, not over apps, and a leg that deletes a table inside its own
        disposable needs the same answer from the same authority.
        """
        self._require_own(app_token)
        response = self._paced(
            self._sdk.bitable.v1.app_table_field.list,
            ListAppTableFieldRequest.builder().app_token(app_token).table_id(table_id).build())
        return getattr(response, "code", None) in TABLE_DELETED_CODES


def _ledgers(provisioner, ledger):
    """``ledger``, plus the durable one when this is a per-run ledger holding REAL tokens.

    The LD-275 mirror. A per-run ledger is right for a cycle that wants to assert about its own
    disposables — but it is the wrong and only home for a token a failed delete kept, because
    the temp dir (or the whole worktree) outlives it by minutes. So the record is written to
    both, and the durable half is what the next session sweeps. An offline double mirrors
    nothing: see :attr:`_Provisioner.mints_real_objects`.
    """
    if not getattr(provisioner, "mints_real_objects", False):
        return [ledger]
    if Path(ledger.path) == Path(LEDGER_PATH):
        return [ledger]
    return [ledger, Ledger()]


@contextmanager
def disposable_base(provisioner=None, nonce=None, ledger=None, time_zone=None,
                    folder_token=None):
    """Yield ``(app_token, default_table_id, title)`` for a fresh disposable Base.

    ``time_zone`` is forwarded to :meth:`_Provisioner.create` and declares the new Base's own
    zone; omitted, the Base declares none — the two halves the date round-trip gate needs.

    The delete sits in a ``finally``, so a failing run still tries to clean up, and its outcome
    is written to the ledger either way — so a Base the API would not let go of yet is a
    recorded token rather than a lost one. :func:`close_out` is what finishes the job.

    **Every real token is also recorded in the durable ledger** (:func:`_ledgers`), so a caller
    keeping a per-run ledger cannot accidentally make itself the only witness to a leak.
    """
    if provisioner is None:
        provisioner = _Provisioner()
    if ledger is None:
        ledger = Ledger()
    ledgers = _ledgers(provisioner, ledger)
    title = disposable_title(nonce)
    app_token, default_table_id = provisioner.create(title, time_zone=time_zone,
                                                     folder_token=folder_token)
    for led in ledgers:
        led.record_create(app_token, title)
    try:
        yield app_token, default_table_id, title
    finally:
        deleted, code = provisioner.delete(app_token)
        for led in ledgers:
            led.record_delete(app_token, code, deleted)


def _sweep(entries, provisioner, ledger, attempts, now=None):
    """Re-attempt the delete on each entry and report what is not verified gone.

    The LD-275 shape: a delete that lands is the end of it; a delete that does not gets one
    bitable question, and that answer is **judged** (:func:`liveness_verdict`) rather than
    believed. A ``pending`` token keeps its ``deleted: false`` and stays on the sweep list, so
    the session after the lag is the one that finishes the job.

    An entry this session may not yet adopt (:func:`_adoptable` — a **parallel leg's** young
    disposable) is not deleted and not judged; it is reported ``pending`` and left on the list
    untouched. Reported rather than skipped silently, because ``{survivors} == {left}`` is the
    invariant every shipped Base arm asserts about this function.

    **The one branch that also archives (LD-535).** Where this function reaches ``gone`` by
    *asking* (``provisioner.is_gone`` in the ``else`` below), the disappearance is
    probe-corroborated and the token is stamped, so the oracle need not ask again. Where it
    reaches ``gone`` because the **delete itself** answered success, nothing is stamped: that is
    a claim about a drive file, and it is the exact claim six leaked Bases once rode past a
    green gate on (LD-275, **D-55**). Those tokens stay in the probe set until a probe of their
    own clears them — which is the pre-LD-535 behaviour, unchanged, for the common case.
    """
    provisioner.adopt_from_ledger(ledger)
    when = now if now is not None else datetime.now(timezone.utc)
    still_there = []
    probe_corroborated = []
    for entry in entries:
        token = entry["app_token"]
        if not _adoptable(entry, when):
            still_there.append({"app_token": token, "title": entry.get("title"),
                                "last_code": entry.get("last_code"), "state": VERDICT_PENDING})
            continue
        deleted, code = provisioner.delete(token, attempts=attempts)
        if deleted:
            verdict = VERDICT_GONE
        else:
            verdict = liveness_verdict(dict(entry, deleted=False, last_code=code),
                                       not provisioner.is_gone(token), now=now)
            deleted = verdict == VERDICT_GONE
            if deleted:
                probe_corroborated.append(token)
        ledger.record_delete(token, code, deleted)
        if not deleted:
            still_there.append({"app_token": token, "title": entry.get("title"),
                                "last_code": code, "state": verdict})
    ledger.record_probe_gone(probe_corroborated)
    return still_there


def close_out(provisioner=None, ledger=None, attempts=DELETE_ATTEMPTS):
    """Re-attempt every ledger survivor and return the ones that are NOT verified gone.

    The other half of the contract the measured teardown lag forces: the ``finally`` gets one
    short budget, and this gets the rest. Returns a list of ``{app_token, title, last_code,
    state}`` for every Base still unaccounted for — empty is clean. Nothing is forgiven here
    either: a token leaves the ledger only when its disappearance is **corroborated** (LD-275),
    never on one not-found answer inside the addressability window.

    Called with no arguments — as every live arm's teardown calls it — the ledger is the durable
    one, so this sweeps **previous sessions'** survivors as well as this run's.
    """
    if ledger is None:
        ledger = Ledger()
    survivors = ledger.survivors()
    if not survivors:
        return []
    if provisioner is None:
        provisioner = _Provisioner()
    return _sweep(survivors, provisioner, ledger, attempts)


def sweep_stale(provisioner=None, ledger=None, attempts=DELETE_ATTEMPTS,
                older_than=LAG_HORIZON_SECONDS):
    """:func:`close_out` restricted to survivors older than ``older_than`` — the adopt-stale
    sweep a session can open with (LD-275).

    Age is the whole point: past the lag horizon a survivor is somebody's leftover and the
    delete that failed then will land now, while a young one may still be in use by a run in
    flight. Adoption is safe because the titles are prefix-enforced and re-checked
    (:meth:`_Provisioner.adopt_from_ledger`), so nothing but a disposable can be swept.
    """
    if ledger is None:
        ledger = Ledger()
    now = datetime.now(timezone.utc)
    stale = [e for e in ledger.survivors() if _entry_age_seconds(e, now) >= older_than]
    if not stale:
        return []
    if provisioner is None:
        provisioner = _Provisioner()
    return _sweep(stale, provisioner, ledger, attempts, now=now)


def survivors(ledger=None):
    """Every disposable the ledger still believes exists — the authoritative sweep list."""
    return (ledger if ledger is not None else Ledger()).survivors()


def attach_media(app_token, *, data, name, parent_type, provisioner=None, ledger=None):
    """Upload attachment media onto a disposable and **ledger the token**.

    The one route by which this repository mints media residue, so it is also the one place
    the disclosure can be enforced: the ledger write happens here, beside the call, and there
    is deliberately **no ``finally``-delete beside it** — nothing to call. A caller that wants
    the residue counted afterwards reads :func:`media_residue`.

    ``app_token`` is the ``parent_node``, and it is checked against the harness's allow-list
    before the call: the configured Scratch Base — like every other Base this harness did not
    create — is refused, and an upload it would have taken is one no deletion could undo.
    """
    if provisioner is None:
        provisioner = _Provisioner()
    if ledger is None:
        ledger = Ledger()
    uploaded = provisioner.upload_media(app_token, data=data, name=name,
                                        parent_type=parent_type)
    ledger.record_media(uploaded.file_token, parent_type, app_token)
    for mirror in _ledgers(provisioner, ledger):
        if mirror is not ledger:
            # LD-275: an un-purgeable token recorded ONLY in a per-run ledger is residue
            # nothing can even name afterwards. The durable ledger gets a copy.
            mirror.record_media(uploaded.file_token, parent_type, app_token)
    return uploaded


def media_residue(ledger=None):
    """Every media token this repository's live runs have minted — the permanent list.

    **Not a sweep list**: there is no verb that would empty it. It is the honest counterpart of
    :func:`orphans`, whose ``[]`` is a claim about *bitable* objects and says nothing about
    media.
    """
    return (ledger if ledger is not None else Ledger()).media()


def orphans(provisioner=None, ledger=None, include_archived=False):
    """**The orphan oracle, executable.** Every ledger token the BITABLE API still resolves.

    ``orphans(...) == []`` is what "zero orphans" means here, and it is deliberately stricter
    than "every delete answered ``code:0``": a delete's own answer is a claim about a *drive
    file*, and the object we care about is the *Base*. So every entry in the ledger's **probe
    set** — deleted-by-us or not — is re-asked of ``GET /bitable/v1/apps/{a}``, and only
    ``1002`` / ``91402`` counts as gone (:data:`DELETED_CODES`).

    **THE PROBE SET, AND WHAT IT USED TO BE (LD-535).** Before LD-535 this asked about *every*
    base row the file had ever held, and then discarded the verdict — so a token already proved
    gone was re-proved gone once per oracle call, for ever, and this repository's Base ring calls
    the oracle **seven** times. The set is now :meth:`Ledger.probe_set` — every base row
    **except** the ones whose ``gone`` verdict was reached here, on a probe answer, and written
    down (:data:`PROBE_GONE_FIELD`). Nothing else changed: the criterion for leaving is the
    verdict this function already computed, so ``deleted: true`` on its own still buys nothing
    (LD-275), a survivor is never archived, and an unstamped legacy file is asked about in full.
    A stamped row is still *in* the ledger — :meth:`Ledger.archived` and one ``grep
    probe_gone_at`` find it — and ``include_archived=True`` re-asks about the whole base half,
    restoring the pre-LD-535 sweep exactly.

    **The one class this is narrower on, named rather than absorbed:** a Base that was
    probe-corroborated gone and then **came back**. It has **two causes, and they are one
    shape** (LD-539 widens the wording; the conclusion below is unchanged): a human restoring
    it from the tenant's recycle bin, **or** a ``gone`` verdict that was never true — a wrong
    **past-horizon** ``1002``, where :func:`liveness_verdict` retired the token on age alone
    (``_entry_age_seconds >= LAG_HORIZON_SECONDS``) and the live Base that answered ``1002``
    inside its own lag window was still there. The second cause is not a resurrection at all,
    which is precisely why it presents as one: on the next probe the token resolves again.
    The ledger's merge law already assumes that cannot happen (:meth:`_reconcile`
    makes ``deleted`` monotonic *because* "a Base does not come back", LD-297), so nothing else
    in this harness would represent such a resurrection either; but the old sweep would have
    caught it and this one will not until someone passes ``include_archived=True``. LD-535's
    Handoff put that to the maintainer rather than deciding it here. **The ruling asked for is still
    the same one, for both causes** (LD-539): bound 1 above already *defines* a corroborated
    past-horizon not-found as proof, and ``include_archived=True`` re-asks about the whole base
    half — so it covers the second cause exactly as it covers the first, and LD-535's
    recommendation, *accept as scoped, no ``D-`` ruling needed*, stands.

    **Drive metadata is never consulted.** It keeps answering for a deleted Base for ever
    (module docstring, with the capture), so it would report a false orphan in perpetuity. That
    residue is inert; an orphan is a Base the bitable API will still serve.

    **A not-found answer is not proof on its own (LD-275).** Each raw answer is judged by
    :func:`liveness_verdict`, so an entry is reported when it is ``alive`` *or* ``pending`` — the
    latter being a token whose delete never landed answering not-found from inside the
    addressability window, which is exactly what a live Base did on 2026-08-04 while six of them
    leaked past a green gate. Only a **corroborated** disappearance clears.

    Returns ``{app_token, title, last_code, state}`` per orphan — named, so a sweep is a grep
    away, and stated, so ``pending`` is distinguishable from a Base that is provably still there.
    """
    if ledger is None:
        ledger = Ledger()
    entries = ledger.entries if include_archived else ledger.probe_set()
    if not entries:
        return []
    if provisioner is None:
        provisioner = _Provisioner()
    # Over the WHOLE base half, not the probe set: the allow-list's title re-check is what stops
    # a hand-edited ledger smuggling a non-disposable in, and an archived row is still a row a
    # human (or ``include_archived=True``) can put back in front of a delete.
    provisioner.adopt_from_ledger(ledger)
    reported = []
    probe_corroborated = []
    for e in entries:
        verdict = liveness_verdict(e, not provisioner.is_gone(e["app_token"]))
        if verdict != VERDICT_GONE:
            reported.append({"app_token": e["app_token"], "title": e.get("title"),
                             "last_code": e.get("last_code"), "state": verdict})
        elif e.get("deleted"):
            # The second half of the fence, in front of the ledger's own: a ``gone`` verdict on
            # a row still reading ``deleted: false`` is NOT an archival ticket — that row belongs
            # to :func:`close_out`'s sweep list until a delete marks it.
            probe_corroborated.append(e["app_token"])
    ledger.record_probe_gone(probe_corroborated)
    return reported
