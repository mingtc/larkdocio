"""larkdocio.common.auth — shared credential resolution + ``.env`` handling + IPv4 pin.

Relocated from ``larkdocio.auth`` into the shared read/write core (LD-061).
Token/auth management and the IPv4 pin are genuinely shared
between the reader and the forthcoming writer, so per the maintainer directive they live
in the core; ``larkdocio.auth`` remains as a transparent back-compat shim that
re-exports the *same* objects (never a fork).

Behavior is **byte-identical** to the pre-extraction module — this is a move, not
a rewrite. The module-level IPv4-pin guard (``_ipv4_pin_applied``) now lives here,
its single canonical home.

Credential scheme (read/write separation)
------------------------------------------
The toolkit uses a two-app, least-privilege setup (see ``write/README.md``): a
read-only app for reading documents and a separate, narrowly-scoped app for writeback.

- **Read path** (``get_read_credentials``) resolves, in order:
    1. ``LARK_READ_APP_ID`` + ``LARK_READ_APP_SECRET`` when *both* are set, else
    2. the legacy ``LARK_APP_ID`` + ``LARK_APP_SECRET`` (compat with every
       existing ``.env``), else
    3. **a loud, typed refusal** — ``LarkConfigError``, from the single
       :data:`READ_CREDENTIALS_REFUSAL` constant.
- **Write path** (``get_write_credentials``) uses ``LARK_WRITE_APP_ID`` /
  ``LARK_WRITE_APP_SECRET``. The read path **must never** pick these up — a
  read-only download must not silently run under write-scoped credentials.

Resolution is *pair-wise* on purpose: a lone ``LARK_READ_APP_ID`` with no
matching secret falls back to the legacy pair rather than mixing a read id with
a legacy secret.

**Both halves of the fence refuse the same way (LD-580).** The read getter used
to end in ``return "", ""`` — with nothing configured a caller got ``('','')``
and no signal at all, and the empty pair travelled into a client constructor to
surface as whatever Lark says about a blank app id, one layer away from the thing
that was actually wrong. It now raises, in the same shape the write half already
used, for the same reason pair-wise resolution exists: **no complete pair is a
configuration error, not an answer**. What did *not* change is the resolution
order — the legacy pair is still a first-class fallback, and every existing
``.env`` keeps working exactly as before.

The ``.env`` bootstrap writes the pair the read path *prefers*
------------------------------------------------------------
Both bootstrap doors — the stub :func:`init_env` writes for a missing file, and
:func:`set_env_credentials`, which is what ``larkdocio config`` calls — write
``LARK_READ_APP_ID`` / ``LARK_READ_APP_SECRET``. The bootstrap used to write the
*legacy* names, so the documented onboarding path handed every new consumer the
compat scheme and the least-privilege read/write separation was unreachable from
it. The legacy pair is still resolved, unchanged: every existing ``.env`` keeps
working, and an existing file is never re-keyed behind its owner's back — a file
that already assigns the legacy names is updated **in place** on those names,
with a notice naming both schemes so migrating stays the owner's choice.

Write credentials are deliberately outside the bootstrap: the writer uses a
separate, narrowly-scoped app, and a read bootstrap that also seeded write keys
would blur the separation it exists to keep.
"""
import os
import socket
import logging
from pathlib import Path

from dotenv import dotenv_values, load_dotenv, set_key

from larkdocio.common.errors import LarkConfigError

logger = logging.getLogger("larkdocio")

# Environment variable names, grouped by path. The read path resolves the
# read pair first, then the legacy pair. Write names are declared here (shared
# core) so the read path can be proven never to consult them, and so S4's
# write-credential getter has a single canonical home for the pair.
READ_ENV = ("LARK_READ_APP_ID", "LARK_READ_APP_SECRET")
LEGACY_ENV = ("LARK_APP_ID", "LARK_APP_SECRET")
WRITE_ENV = ("LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET")

# The stub a missing ``.env`` is bootstrapped with. It ASSIGNS the preferred read
# pair and only *mentions* the legacy one: an assignment would put a brand-new
# file on the compat scheme, while the mention is what tells a reader their
# existing legacy file still works. Built from the tuples above so a rename of a
# name cannot leave the stub behind.
BOOTSTRAP_ENV_TEMPLATE = (
    "# Lark read credentials. The config command writes these two names.\n"
    f"# {READ_ENV[0]} / {READ_ENV[1]} are the preferred pair.\n"
    f"# The legacy {LEGACY_ENV[0]} / {LEGACY_ENV[1]} names are still accepted as a\n"
    f"# fallback whenever the pair below is not fully set, so an existing file that\n"
    f"# uses them keeps working and is never rewritten onto the preferred names.\n"
    f"# Write credentials ({WRITE_ENV[0]} / {WRITE_ENV[1]}) are deliberately not\n"
    f"# bootstrapped here: writing uses a separate, narrowly-scoped app, and the read\n"
    f"# path never consults them.\n"
    f"{READ_ENV[0]}=\n{READ_ENV[1]}=\n"
)

#: **The read-credential refusal — ONE constant, one authoring** (LD-580). Every raise and every
#: documented spelling of this text is a projection of it, held bidirectionally by the suite's
#: ``test_read_credential_fence.py`` (in the source repository); a string typed twice is two things to
#: keep true (the ``STALE_SHEET`` precedent). Rendered through :func:`read_credentials_refusal`,
#: which supplies
#: the pair :func:`resolved_read_env` says is **in force** — naming the preferred pair while the
#: legacy one is in force would send a reader to edit a variable nothing is reading.
#:
#: It is the **F8** shape, not F1: the difference is not severity, it is whether the message tells
#: the caller what to DO. So it names the variables, the ``larkdocio config`` bootstrap that writes
#: them (:func:`set_env_credentials`, and :func:`init_env`'s own ``.env`` stub), and the ``.env``
#: doctrine — and it names them only: **no credential value is ever echoed.**
READ_CREDENTIALS_REFUSAL = (
    "Read credentials not configured: set {name_id} and {name_secret} — the pair the read path "
    "is resolving right now. The quickest route is `larkdocio config --appId <id> --appSecret "
    "<secret>`, which writes a read pair into the .env the reader loads; .env is gitignored, so "
    "credentials live only there and never in the repository. The read and write pairs are "
    "resolved independently and neither falls back to the other, so a write-scoped app is never "
    "borrowed to satisfy a read."
)

#: **The create-opt-out refusal — one constant, one authoring**, the same shape as
#: :data:`READ_CREDENTIALS_REFUSAL` above and rendered through
#: :func:`env_file_missing_refusal`. It is the **F8** shape: it tells the caller what to DO,
#: because ``create=False`` is a deliberate choice and the caller who made it needs the path
#: that was looked for, the pair that is in force, and the two ways to get a file there. It
#: names variables and a path only — **no credential value is ever echoed.**
ENV_FILE_MISSING_REFUSAL = (
    "Environment file not found: {path}. init_env was called with create=False, so nothing "
    "was written and no directory was created. Either create that file yourself carrying "
    "{name_id} and {name_secret} — the pair the read path is resolving right now — or run "
    "`larkdocio config --appId <id> --appSecret <secret>` to have it written for you, or call "
    "init_env without create=False and a commented template is bootstrapped there. .env is "
    "gitignored, so credentials live only there and never in the repository."
)

# ── IPv4 pin (LD-017 / B3) ──────────────────────────────────────────────────
# Lark's IP allowlist is IPv4-only: when the API host resolves to an IPv6
# address, requests leave from an IPv6 source that is not on the allowlist and
# Lark rejects them. Pinning ``getaddrinfo`` to ``AF_INET`` sidesteps that.
#
# The pin is applied by ``init_env`` **after** ``.env`` is loaded (not at import
# time), so ``LARK_DISABLE_IPV4_PIN`` set in a ``.env`` is honored. ``init_env``
# is the single ``.env``-loaded chokepoint shared by the CLI command handlers and
# the package-API / live-canary path, so the knob works everywhere the reader
# loads its env. Merely importing the package does not mutate process-wide DNS.
DISABLE_IPV4_PIN_ENV = "LARK_DISABLE_IPV4_PIN"

# Module-level guard so repeated ``init_env`` calls in one process patch
# ``getaddrinfo`` at most once (no wrapper stacking).
_ipv4_pin_applied = False


def pin_socket_to_ipv4():
    """Force Python's socket resolver to return IPv4 addresses only.

    Idempotent: patches ``socket.getaddrinfo`` at most once per process. Opt out
    by setting ``LARK_DISABLE_IPV4_PIN=1`` (see ``apply_ipv4_pin``).
    """
    global _ipv4_pin_applied
    if _ipv4_pin_applied:
        return

    orig_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = patched_getaddrinfo
    _ipv4_pin_applied = True


def _ipv4_pin_disabled() -> bool:
    """True when ``LARK_DISABLE_IPV4_PIN`` is set to ``1``/``true``/``yes``.

    Read from ``os.environ`` — callers apply the pin *after* loading ``.env`` so
    a value set there is already present in the process env.
    """
    return os.environ.get(DISABLE_IPV4_PIN_ENV, "").strip().lower() in ("1", "true", "yes")


def apply_ipv4_pin():
    """Apply the IPv4 pin unless disabled via ``LARK_DISABLE_IPV4_PIN``.

    Call *after* ``.env`` is loaded so the knob is honored from ``.env``.
    Idempotent and a no-op when disabled.
    """
    if not _ipv4_pin_disabled():
        pin_socket_to_ipv4()


def env_file_missing_refusal(path) -> str:
    """:data:`ENV_FILE_MISSING_REFUSAL` rendered for *path*, on the pair **in force**.

    The same discipline as :func:`read_credentials_refusal`: the pair comes from
    :func:`resolved_read_env` rather than being assumed, because pointing a reader at a
    variable nothing is consulting is the defect that function exists to prevent. No
    credential value is ever echoed — only names and the path that was looked for.
    """
    name_id, name_secret = resolved_read_env()
    return ENV_FILE_MISSING_REFUSAL.format(
        path=path, name_id=name_id, name_secret=name_secret)


def init_env(env_path: str = None, *, create: bool = True) -> str:
    """Ensure a ``.env`` exists and load its variables. Returns the path used.

    With no explicit path, uses ``<cwd>/.env`` (matching how the CLI is run from
    a consumer repo root). An existing file is loaded untouched, whichever of the
    two accepted schemes it uses.

    **What a missing file gets, by default.** Any missing parent directories are
    created, and the new file is a **commented template** — not an empty file —
    that assigns the **preferred** read credential names (the pair
    :func:`get_read_credentials` resolves first) with blank values, so the
    ``config`` command / hand-editing has somewhere to write.

    **Pass ``create=False`` to load only.** Nothing is then written and no
    directory is created; a missing file raises
    :class:`~larkdocio.errors.LarkConfigError` naming the path it looked for.
    ``create`` is keyword-only and defaults to ``True``, so every existing call
    behaves exactly as it did before it existed.

    **Loading overrides the process environment.** Variables in the file win over
    variables of the same name already exported in the process — a blank value in
    the file included. So if credentials are set in the environment on purpose (a
    CI job, a test harness), point ``env_path`` at a file that agrees with them
    rather than expecting the environment to survive this call.

    :raises LarkConfigError: when ``create=False`` and the file does not exist —
        naming the path and the credential pair in force, echoing no value.
    """
    if env_path:
        path_obj = Path(env_path).resolve()
    else:
        path_obj = Path.cwd() / ".env"

    if not path_obj.exists():
        if not create:
            raise LarkConfigError(env_file_missing_refusal(path_obj))
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        # LD-660: encoding pinned as HARDENING, not a fix — BOOTSTRAP_ENV_TEMPLATE is pure
        # ASCII today, so the locale default could not have mangled it. The keyword removes the
        # trap for the next edit of that template, since this codebase uses non-ASCII
        # punctuation nearly everywhere.
        path_obj.write_text(BOOTSTRAP_ENV_TEMPLATE, encoding="utf-8")
        logger.info(
            f"Notice: Created {path_obj} — a commented template with blank "
            f"credential values, and any missing parent directories along with it. "
            f"Please run the config command to configure {READ_ENV[0]} and "
            f"{READ_ENV[1]} natively, or edit it directly."
        )

    load_dotenv(dotenv_path=path_obj, override=True)

    # B3: apply the IPv4 pin *after* the .env is loaded, so LARK_DISABLE_IPV4_PIN
    # set in the .env is honored (idempotent; no-op when disabled).
    apply_ipv4_pin()

    return str(path_obj)


def read_credentials_refusal() -> str:
    """:data:`READ_CREDENTIALS_REFUSAL` rendered on the pair that is **in force** right now.

    The one seam between the constant and every raise of it. It reads the pair from
    :func:`resolved_read_env` rather than assuming the preferred one, because the read path
    accepts a legacy pair and pointing a reader at a variable nothing is consulting is the
    exact defect that function exists to prevent.
    """
    name_id, name_secret = resolved_read_env()
    return READ_CREDENTIALS_REFUSAL.format(name_id=name_id, name_secret=name_secret)


def token_mint_refusal(subject: str) -> str:
    """The one-line refusal a rejected credential pair exits on, for ``subject``'s verb.

    Short by design — the actionable detail is in the lines
    :func:`token_mint_refusal_lines` logs above it, the same shape the reader's other operator
    banners use.

    **``subject`` is a parameter and not a constant, because the arm is shared (LD-658 fix
    round).** It was the literal ``"Download failed: …"``, written when only ``download`` had
    this arm; once the CLI seam carried it for every verb, ``roundtrip pull`` printed
    ``Error: Download failed: …`` — a refusal that misnames the command the user typed. New
    advice that cannot be followed is the exact defect class this issue exists to remove, so it
    would have been one here.

    ``download`` passes ``"Download"`` and its bytes are unchanged — that spelling is the
    convention every other refusal on that path already uses. The seam passes the verb click
    itself parsed, so a future subcommand is named correctly without being listed anywhere.
    """
    return f"{subject} failed: the app credentials were rejected — see the guidance above."


def token_mint_refusal_lines(pairs, env_file: str = None) -> list:
    """The operator-facing guidance for **Lark rejecting the app itself** — authored once here.

    A wrong App ID or App Secret fails the SDK's tenant-access-token handshake, so **no token is
    issued and no document is ever asked for**. It arrives as ``lark_oapi``'s own
    ``ObtainAccessTokenException``, which is neither this library's ``LarkAPIError`` nor a
    ``ValueError`` nor an ``OSError`` — so nothing on the widened CLI refusal seam catches it by
    class, and before LD-658 it reached the bug-report banner and a traceback. The user was
    accused of finding a bug in this library when what they had was a typo in ``.env``, and was
    told neither which variables to fix nor which ``.env`` had been read. It is the second most
    likely first-run mistake, after a mistyped url.

    **``pairs`` is a tuple of env-var pairs, and the CALLER supplies it, because how precisely
    the culprit can be named differs by caller and neither answer may be guessed.**

    * The **reader** knows exactly one pair can be at fault — the read path resolves a preferred
      pair with a legacy fallback and nothing else — so it passes ``(resolved_read_env(),)`` and
      the guidance names one pair. Asking for the pair *in force* rather than hard-coding the
      preferred one is the point: pointing a reader at a variable nothing is consulting is the
      defect :func:`resolved_read_env` exists to prevent.
    * The **CLI seam** is reached by any verb whose failure carries the SDK's exception class,
      which may be one that writes, and it cannot know which credential pair the failing call
      was minting (the exception carries no app id, and mapping subcommand → pair would be a
      second, wrong copy of the credential doctrine — ``roundtrip`` alone reads on ``pull`` and
      writes on ``push``). It passes both, and the text below says plainly that it is one of them
      rather than claiming to know.

    **What that seam does NOT reach** is stated where the seam is
    (:class:`larkdocio.cli._RefusalUniformCommand`) and not restated here: this library mints a
    tenant token two ways, and the raw-HTTP one raises a different class. This function is only
    the words; which failures arrive at it is the callers' question.

    Returning **lines rather than logging** keeps this function free of a logger and a stream, so
    the two callers emit identical bytes through their own already-configured one.
    """
    named = " / ".join(name for pair in pairs for name in pair)
    which = (f"Check {named} against the app's own credentials in the Lark console."
             if len(pairs) == 1 else
             f"Lark does not say WHICH app it rejected, and this command can use more than one "
             f"pair, so check the one this invocation uses: {named}. Each pair belongs to its "
             f"own Lark app — the read app and the write app are never interchangeable.")
    return [
        "LARK API ERROR: The App ID / App Secret were rejected (no token was issued)",
        "This is a CREDENTIAL problem, not a document problem — Lark refused the app itself, so no document was ever asked for.",
        f"Action Required: {which} Run `larkdocio config --appId … --appSecret …` to write the "
        f"read pair, or edit the `.env` this run read: "
        f"{os.path.abspath(env_file) if env_file else os.path.abspath('.env')}"
        f"{'' if env_file else ' (or the file you passed to --env-file)'}.",
    ]


def get_read_credentials() -> tuple[str, str]:
    """Resolve the read-path (app_id, app_secret), or refuse loudly.

    Prefers the ``LARK_READ_APP_*`` pair when *both* are set; otherwise falls
    back to the legacy ``LARK_APP_*`` pair. Never consults ``LARK_WRITE_APP_*``.

    Resolution is **pair-wise**, so "no pair resolved" is a configuration error and not an
    answer: this used to end in a ``('','')`` return, which handed the caller an empty pair and
    no signal, and the blank then surfaced from inside a client constructor as whatever Lark
    says about a blank app id. Both halves of the credential fence now refuse the same way —
    the write half's reasoning, applied to the read half.

    :raises LarkConfigError: when neither pair resolves completely, with
        :func:`read_credentials_refusal`'s text — which names the env vars **in force**, the
        ``larkdocio config`` bootstrap and the ``.env`` doctrine, and never a credential value.
    """
    read_id = os.environ.get(READ_ENV[0], "").strip()
    read_secret = os.environ.get(READ_ENV[1], "").strip()
    if read_id and read_secret:
        return read_id, read_secret
    # The legacy values are returned UNSTRIPPED — that is the shipped compat behaviour and this
    # change does not touch it. Only the emptiness test decides between answering and refusing.
    legacy_id = os.environ.get(LEGACY_ENV[0], "")
    legacy_secret = os.environ.get(LEGACY_ENV[1], "")
    if legacy_id.strip() and legacy_secret.strip():
        return legacy_id, legacy_secret
    raise LarkConfigError(read_credentials_refusal())


def resolved_read_env() -> tuple[str, str]:
    """The env-var NAMES the read path would actually use right now.

    The read path accepts a legacy pair as a fallback, so "which credentials made this call"
    has two possible answers and only one of them is true at a time. A permission denial names
    this pair — and so does :func:`read_credentials_refusal`, the no-pair case — and naming the
    preferred one while the legacy one is in force would send a reader to edit a variable
    nothing is reading. Mirrors :func:`get_read_credentials`' resolution exactly, so the two
    cannot disagree. With **nothing** configured the answer is the legacy pair: that is the
    read path's last resort, so it is what the read path is reading, and the refusal names the
    ``larkdocio config`` route beside it for anyone who would rather be on the preferred pair.
    """
    read_id = os.environ.get(READ_ENV[0], "").strip()
    read_secret = os.environ.get(READ_ENV[1], "").strip()
    return READ_ENV if (read_id and read_secret) else LEGACY_ENV


def get_write_credentials() -> tuple[str, str]:
    """Resolve the write-path (app_id, app_secret) from ``LARK_WRITE_APP_*``.

    Write-only, **no fallback**: unlike :func:`get_read_credentials` (which falls
    back to the legacy pair before refusing), the write getter resolves *only* the
    ``LARK_WRITE_APP_*`` pair and **never** borrows the read or legacy
    credentials. A read-only app must not be silently promoted to run a
    write-scoped operation, so a missing or half-configured write pair is a loud,
    typed configuration error rather than a silent fallback (credential doctrine;
    ``write/README.md`` § "Credential doctrine"). This half was for a while the
    fence's only armed direction; the read half refuses the same way now, so the
    two differ only in the *fallback*, never in the *outcome* of not resolving.

    Resolution is pair-wise: both names must be present (non-blank after
    stripping). A lone id or a lone secret is an error — never mixed with any
    other pair.

    :raises LarkConfigError: when the ``LARK_WRITE_APP_*`` pair is missing or
        incomplete. The message names the env vars only; it never echoes a
        credential value.
    """
    write_id = os.environ.get(WRITE_ENV[0], "").strip()
    write_secret = os.environ.get(WRITE_ENV[1], "").strip()
    if write_id and write_secret:
        return write_id, write_secret
    raise LarkConfigError(
        f"Write credentials not configured: set {WRITE_ENV[0]} and {WRITE_ENV[1]} "
        f"(the write path never falls back to read/legacy credentials)."
    )


def env_credential_pair(env_path: str) -> tuple[str, str]:
    """Which read pair the ``.env`` at *env_path* should be written to.

    The **preferred** ``LARK_READ_APP_*`` pair for a fresh file or one that
    already assigns it; the legacy ``LARK_APP_*`` pair only when the file assigns
    *that* and no preferred key. The guarantee is that an existing credential
    file is **never re-keyed**: a value lands on the scheme the file already
    presents, and no key of the other scheme is added behind its owner's back.

    Detection is by **assigned key, not by value** — a blank assignment still
    says "this file is on that scheme". One consequence is worth stating plainly,
    because it is the one place the write and the *resolution* can disagree: on a
    file that assigns a blank preferred key beside a complete legacy pair, a
    one-sided update lands on the preferred pair, and a half-set preferred pair
    loses to the complete legacy one — so the new value is not what resolution
    returns until its partner key is set too. That case is **reported**, never
    silent: see :func:`unresolved_pair_gap`, which :func:`set_env_credentials`
    consults to name the missing key in its output.

    Only real assignments count: a commented-out name (as ``.env.example`` ships
    the legacy pair) is documentation, so a file copied from it is fresh.
    """
    try:
        assigned = set(dotenv_values(env_path))
    except OSError:
        assigned = set()

    if assigned & set(READ_ENV):
        return READ_ENV
    if assigned & set(LEGACY_ENV):
        return LEGACY_ENV
    return READ_ENV


def unresolved_pair_gap(env_path: str, names: tuple[str, str]) -> str | None:
    """The key of *names* whose absence keeps a just-written value from resolving.

    Returns the missing (absent or blank) key name when a value written to the
    other half of *names* is **not** what :func:`get_read_credentials` will
    return, and ``None`` when there is nothing to report.

    Reported only for a pair that is **partially** set — one half carries a value
    and the other does not, which is exactly when a value sits in the file that
    resolution will skip. A pair with neither half set hides nothing (there is
    nothing there to be ignored, and the refusal names the pair anyway), and a
    complete pair resolves.

    **Both pairs can be in that position** — the preferred pair because resolution
    is pair-wise and a lone preferred key falls through to the legacy pair, and
    the legacy pair because a half-set last resort no longer resolves either. That
    second half used to answer ``None``, on the reason that *"a half-set legacy
    pair is still exactly what resolution returns, so claiming its value would be
    ignored would be a new falsehood"* — a correct reason for the behaviour of the
    time. LD-580 made :func:`get_read_credentials` refuse instead of handing back a
    blank half, so the reason survives and only its conclusion is superseded: the
    value now really is inert, and saying so is the honest answer rather than the
    new falsehood.

    Read from the file rather than the process environment: the file is what the
    owner just edited and what the next run will load.
    """
    if tuple(names) not in (READ_ENV, LEGACY_ENV):
        return None
    try:
        values = dotenv_values(env_path)
    except OSError:
        return None
    unset = [name for name in names if not (values.get(name) or "").strip()]
    if len(unset) != 1:
        return None
    return unset[0]


def set_env_credentials(app_id: str, app_secret: str, env_path: str = None):
    """Persist the read credentials into the ``.env`` file.

    Writes the **preferred** ``LARK_READ_APP_*`` names — the pair
    :func:`get_read_credentials` resolves first — so the credentials a bootstrap
    produces are the ones the least-privilege read/write separation is built on.

    A ``.env`` that already assigns the legacy ``LARK_APP_*`` names is updated
    **in place** on those names and says so: silently re-keying somebody's
    credential file is a surprising side effect, and the legacy pair keeps
    resolving anyway. Only the value(s) actually supplied are written.

    When only one half of a pair is supplied and the pair is left **incomplete**,
    the output says the value **will not take effect** until the named partner key
    is set — because resolution is pair-wise, a half-set preferred pair falls back
    to the legacy pair and the new value is quietly ignored otherwise. The write
    target is unchanged either way (a file is never re-keyed); what changes is
    that the awkward case is stated rather than left silent.

    Write credentials are never touched here — those belong to a separate,
    narrowly-scoped app (see :func:`get_write_credentials`).
    """
    path = init_env(env_path)
    names = env_credential_pair(path)

    if app_id:
        set_key(path, names[0], app_id)
        os.environ[names[0]] = app_id
    if app_secret:
        set_key(path, names[1], app_secret)
        os.environ[names[1]] = app_secret

    if not (app_id or app_secret):
        return

    # Which names a credential landed on is the one thing a caller cannot see from
    # the outside, so the command says it — names only, never a value.
    logger.info(
        f"Read credentials written to {path} as {names[0]} / {names[1]}. Write "
        f"credentials ({WRITE_ENV[0]} / {WRITE_ENV[1]}) are not set by this command: "
        f"writing uses a separate, narrowly-scoped app."
    )
    if names == LEGACY_ENV:
        logger.info(
            f"Notice: that file already used the legacy {LEGACY_ENV[0]} / {LEGACY_ENV[1]} "
            f"names, so it was left on that scheme — an existing credential file is never "
            f"re-keyed for you, and the legacy pair keeps resolving. The preferred names "
            f"are {READ_ENV[0]} / {READ_ENV[1]}; to move over, rename the two keys."
        )

    # A one-sided update can leave the pair half-set, and read credentials resolve pair-wise —
    # so the value would sit in the file doing nothing. Say it, and name the key that is
    # missing; a stated no-op costs a sentence, a silent one costs an afternoon.
    gap = unresolved_pair_gap(path, names)
    if gap:
        # Where an incomplete pair leaves the read path depends on WHICH pair it is: the
        # preferred pair falls through to the legacy one, the legacy pair is the last resort
        # and there is nothing below it, so it refuses. Saying "falls back to the legacy pair"
        # about the legacy pair would tell the owner it falls back to itself.
        consequence = (
            f"falls back to {LEGACY_ENV[0]} / {LEGACY_ENV[1]}"
            if tuple(names) == READ_ENV
            else "is refused, because the legacy pair is the last resort and nothing follows it"
        )
        logger.info(
            f"Notice: {gap} is still not set, so the {names[0]} / {names[1]} pair is "
            f"incomplete. Read credentials resolve as a pair, so an incomplete pair "
            f"{consequence}, and what was just written will not take effect until {gap} is "
            f"set too — re-run the command supplying both values."
        )
