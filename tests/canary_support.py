"""Importable helpers for the live read-canary (LD-003).

Kept out of the test bodies so the scratch-doc URL plumbing and the
creds/URL availability check are (a) covered by offline unit tests
(``tests/test_canary_offline.py``, no network) and (b) reused by the live
canary suite (``tests/test_live_canary.py``, marked ``@pytest.mark.live``).

Design:
* The scratch-doc URL is **never hard-coded** in a test — it comes from the
  ``LARKDOCIO_CANARY_DOC`` env var (documented in ``.env.example``).
* ``load_env()`` loads the repo-root ``.env`` **only if it exists**, so local
  ``pytest -m live`` runs pick up creds + the canary URL from ``.env`` while a
  CI run (creds + URL injected as CI variables) is untouched and no stray
  ``.env`` file is created.
* When the URL or the read creds are missing the live test should
  ``pytest.skip(missing_reason())`` — never silently pass.
"""
import os
from pathlib import Path
from urllib.parse import urlsplit

# Env var carrying the disposable scratch-doc URL (never hard-coded in a test).
CANARY_DOC_ENV = "LARKDOCIO_CANARY_DOC"

# Env var carrying the disposable standalone scratch-SHEET URL — the L1 live
# sheets canary (LD-106). The sheets analogue of CANARY_DOC_ENV:
# the canary reads it read-only and skips loudly when unset (never a silent pass).
SCRATCH_SHEET_ENV = "LARKDOCIO_SCRATCH_SHEET"

# Env var carrying the maintainer-granted free-fire Scratch BASE (2026-08-03) — the Base
# analogue of the two above, read the same skip-loudly way. LD-247 uses it for a
# single READ-ONLY arm; the full determinism canary is LD-252.
SCRATCH_BASE_ENV = "LARKDOCIO_SCRATCH_BASE"

# OPTIONAL env var carrying a maintainer-designated Drive folder for the live Drive canary
# (LD-328). UNSET is the norm: the canary then reads the bot's OWN
# root folder, discovered live (the Drive spec § D7) — no grant, no write, no resource.
# When set it OVERRIDES the subject; a set-but-unreachable value makes the canary
# SKIP LOUDLY (never fail, never a silent pass). It is a folder token (or a Drive
# folder URL — the canary reads only the trailing token). READ-ONLY like every
# other env below.
CANARY_FOLDER_ENV = "LARKDOCIO_CANARY_FOLDER"

# Env vars carrying the disposable block-zoo doc URL(s) — the advisory zoo ring
# (LD-044). The zoo ring mirrors the canary's skip-loudly-never-
# block machinery exactly; these vars are the zoo analogue of CANARY_DOC_ENV.
# The wiki companion is OPTIONAL (only for the wiki-only types 42/51 if the maintainer
# adds the wiki page).
BLOCKZOO_DOC_ENV = "LARKDOCIO_BLOCKZOO_DOC"
BLOCKZOO_WIKI_ENV = "LARKDOCIO_BLOCKZOO_WIKI"

# THE HOUSE HALF OF THE CALLER-SUPPLIED-DESTINATION RULE (LD-493).
#
# The destination every live harness creates its disposables in: a folder in a HUMAN's own
# Drive, which the application has been granted access to in the Lark console (a grant is a
# console action — the library never widens its own access). Documented in ``.env.example``.
#
# UNSET ⇒ every harness that creates something SKIPS LOUDLY naming this variable. It never
# falls back to the application's own space, because that space has no human interface: what
# is created there cannot be browsed, its trash cannot be listed, and a delete there is a
# trash rather than a purge. A rule the library states and its own harnesses break is not a
# rule.
#
# Accepts a folder token or a pasted Drive folder link (the trailing token is read), exactly
# as ``LARKDOCIO_CANARY_FOLDER`` does.
DISPOSABLES_FOLDER_ENV = "LARKDOCIO_DISPOSABLES_FOLDER"

# Repo root is one level up from this tests/ directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


#: The host every URL in ``.env.example`` is written on (LD-694 F13). ``setup.sh`` copies that
#: file to ``.env`` on a fresh clone, so a value on this host is the committed PLACEHOLDER — never
#: a target — and reads as unset: the arm skips naming its variable instead of running against it.
PLACEHOLDER_HOST_LABEL = "your-domain"


def is_placeholder(value):
    """Whether ``value`` is a ``.env.example`` placeholder rather than something a person set.

    The test is the placeholder HOST (``https://your-domain.larksuite.com/…``), which no tenant
    has. The ``Example`` in a placeholder's token is not used: it is a property of the fixtures,
    and a real token is free to contain those seven letters.
    """
    host = urlsplit(value.strip()).hostname or ""
    return host.split(".", 1)[0] == PLACEHOLDER_HOST_LABEL


def _env_url(var):
    """Return ``os.environ[var]`` stripped, or ``None`` when unset, blank or a placeholder.

    The one strip-or-None reader behind every scratch-doc URL getter below —
    they differ only in *which* env var they read (LD-088 dedup). A ``.env.example``
    placeholder counts as unset (:func:`is_placeholder`, LD-694).
    """
    url = os.environ.get(var, "").strip()
    if not url or is_placeholder(url):
        return None
    return url


def canary_doc_url():
    """Return the scratch-doc URL from ``LARKDOCIO_CANARY_DOC``.

    Returns ``None`` when the var is unset or blank (so the live canary skips
    rather than running against a garbage URL).
    """
    return _env_url(CANARY_DOC_ENV)


def canary_folder_override():
    """The OPTIONAL maintainer-designated Drive folder token from ``LARKDOCIO_CANARY_FOLDER``.

    Returns ``None`` when unset or blank (⇒ the Drive canary falls back to the bot's own
    root folder, discovered live — the Drive spec § D7). When set to a Drive folder URL the trailing
    path token is taken, so a committed URL and a bare token both resolve to the token the
    listing endpoint wants; the canary never writes it and never reaches a real tree as a hard
    dependency (LD-328 AC2).
    """
    raw = _env_url(CANARY_FOLDER_ENV)
    if raw is None:
        return None
    # A Drive folder URL degrades to its trailing token; a bare token passes through unchanged.
    return raw.rstrip("/").split("/")[-1].split("?")[0] or None


def disposables_folder():
    """The folder every live harness creates its disposables in, or ``None`` when unset.

    Read from :data:`DISPOSABLES_FOLDER_ENV`. A pasted Drive folder link degrades to its
    trailing token; a bare token passes through unchanged — the same tolerance
    :func:`canary_folder_override` has, because the human who fills ``.env`` in copies a link.

    ``None`` is not a fallback: it is the signal to **skip loudly**
    (:func:`disposables_folder_missing_reason`). Nothing here invents a destination, and
    nothing here creates a folder — that would be the same guess one level up.
    """
    raw = _env_url(DISPOSABLES_FOLDER_ENV)
    if raw is None:
        return None
    return raw.rstrip("/").split("/")[-1].split("?")[0] or None


def disposables_folder_missing_reason():
    """Why a disposable-creating harness cannot run, or ``None`` when it can.

    The message **names the variable**, so a skipped run says what to set rather than looking
    like a pass.
    """
    if disposables_folder() is None:
        return (
            f"{DISPOSABLES_FOLDER_ENV} is unset — skipping: this harness CREATES objects, and "
            f"the caller-supplied-destination rule means it will not create them in the "
            f"application's own space (no human interface can see that space; a delete there "
            f"is a trash, not a purge). Create a folder in your own Drive, grant the "
            f"application access to it in the Lark console, and set "
            f"{DISPOSABLES_FOLDER_ENV} to its link or token."
        )
    return None


def require_disposables_folder():
    """The disposables folder token, or ``pytest.skip`` naming the variable.

    The one call every disposable-creating live harness makes before it creates anything.
    """
    import pytest

    reason = disposables_folder_missing_reason()
    if reason:
        pytest.skip(reason)
    return disposables_folder()


def read_creds_available():
    """True when read credentials resolve to a non-empty ``(app_id, app_secret)``.

    Delegates to the package's own resolver so this tracks the real read-path
    precedence (``LARK_READ_APP_*`` preferred, legacy ``LARK_APP_*`` fallback).
    That resolver **raises** ``LarkConfigError`` when no pair resolves (LD-580 —
    it used to hand back a blank pair); we translate that into ``False`` so the
    live read rings can *skip loudly* rather than error. Same shape and same
    reason as :func:`write_creds_available`, which has done this since W0: this
    function is a **predicate**, and a predicate that raises turns every
    ``skipif`` that reads it into a collection error on a clone with no ``.env``.
    """
    from larkdocio.auth import get_read_credentials
    from larkdocio.errors import LarkConfigError

    try:
        app_id, app_secret = get_read_credentials()
    except LarkConfigError:
        return False
    return bool(app_id and app_secret)


def live_available():
    """True when both the canary URL and read creds are present (live can run)."""
    return canary_doc_url() is not None and read_creds_available()


def missing_reason():
    """Human-readable reason the live canary cannot run, or ``None`` if it can.

    Used as the ``pytest.skip`` message so a creds/URL-less environment (CI
    without secrets, a fresh clone) skips loudly instead of passing silently.
    """
    if canary_doc_url() is None:
        return (
            f"{CANARY_DOC_ENV} is unset — set it to the disposable scratch-doc "
            "URL (see .env.example) to run the live read-canary."
        )
    if not read_creds_available():
        return (
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET "
            "(or the legacy LARK_APP_ID/LARK_APP_SECRET) to run the live "
            "read-canary."
        )
    return None


# ---------------------------------------------------------------------------
# Live SHEETS canary (LD-106) — THE L1 gate. The sheets analogue
# of the docx canary helpers above, keyed on SCRATCH_SHEET_ENV. Read creds are
# shared (the canary is READ-ONLY, like the docx canary). The sheets URL parse is
# validate_download_url's (LD-183 taught it /sheets/ and made it return the type),
# so :func:`parse_sheet_url` is a THIN ADAPTER onto that call and not a parser.
#
# It used to be a parser: a third hand-rolled copy of the same regex, whose comments
# still claimed the validator handled docx/wiki only. LD-183 collapsed the two copies
# in the shipped guide; LD-210 AC5 collapses this one, and drops the /sheet/ SINGULAR
# form it uniquely accepted — unevidenced (LD-183's accepted-shape table is built from
# real URLs and is plural-only), and the sole reason a third parser was still needed.
# ---------------------------------------------------------------------------


def scratch_sheet_url():
    """Return the standalone scratch-SHEET URL from ``LARKDOCIO_SCRATCH_SHEET``.

    Returns ``None`` when the var is unset or blank (so the live sheets canary
    skips rather than running against a garbage URL).
    """
    return _env_url(SCRATCH_SHEET_ENV)


def parse_sheet_url(raw_url):
    """A Lark sheets URL → ``(base_host, spreadsheet_token)``; ``ValueError`` if
    malformed or not a spreadsheet.

    ``https://your-domain.larksuite.com/sheets/SheetS…`` →
    ``("larksuite.com", "SheetS…")``. This is :func:`larkdocio.common.validate_download_url`
    — which recognises ``/sheets/`` and names the type since LD-183 — narrowed to the
    spreadsheet type and to the two values the sheets canary needs. Not a parse: the
    host allowlist, the optional subdomains, the query string and the trailing slash
    are all the shipped validator's, so the canary cannot drift from what the library
    accepts (LD-210 AC5).

    A document URL is refused here even though the validator accepts it: recognising a
    URL is not the same as it naming a spreadsheet, and handing a docx token to the
    sheets client would fail later and vaguer.
    """
    from larkdocio.common import validate_download_url

    domain, url_type, token = validate_download_url(raw_url or "")
    if url_type != "sheets":
        raise ValueError(
            f"Not a Lark sheets URL (recognised as {url_type!r}): {raw_url!r}"
        )
    return domain, token


def sheets_live_available():
    """True when both the scratch-sheet URL and read creds are present."""
    return scratch_sheet_url() is not None and read_creds_available()


def sheets_missing_reason():
    """Human-readable reason the live sheets canary cannot run, or ``None``.

    Used as the ``pytest.skip`` message so a creds/URL-less environment (CI
    without secrets, a fresh clone) skips **loudly** instead of passing silently.
    """
    if scratch_sheet_url() is None:
        return (
            f"{SCRATCH_SHEET_ENV} is unset — set it to the disposable standalone "
            "scratch-sheet URL (see .env.example) to run the live sheets canary "
            "(THE L1 gate)."
        )
    if not read_creds_available():
        return (
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET "
            "(or the legacy LARK_APP_ID/LARK_APP_SECRET) to run the live sheets "
            "canary."
        )
    return None


# ---------------------------------------------------------------------------
# Live BASE read arm (LD-247). The Base analogue of the sheets
# helpers above, keyed on SCRATCH_BASE_ENV and sharing the READ credentials —
# the arm is READ-ONLY and never writes. Same thin-adapter posture: the URL parse
# is validate_download_url's (it has recognised /base/ since LD-183), narrowed to
# the base type, so the arm cannot drift from what the library accepts.
# ---------------------------------------------------------------------------


def scratch_base_url():
    """Return the free-fire Scratch Base URL from ``LARKDOCIO_SCRATCH_BASE``.

    ``None`` when unset or blank, so the live arm skips rather than running against
    a garbage URL.
    """
    return _env_url(SCRATCH_BASE_ENV)


def parse_base_url(raw_url):
    """A Lark Base URL → ``(base_host, app_token)``; ``ValueError`` if it is not one.

    ``https://your-domain.larksuite.com/base/BaseScratchExample…`` → ``("larksuite.com", "BaseScratchExample…")``.
    A spreadsheet or document URL is refused even though the validator accepts it:
    recognising a URL is not the same as it naming a Base, and handing a docx token to
    the Base client would fail later and vaguer.
    """
    from larkdocio.common import validate_download_url

    domain, url_type, token = validate_download_url(raw_url or "")
    if url_type != "base":
        raise ValueError(
            f"Not a Lark Base URL (recognised as {url_type!r}): {raw_url!r}"
        )
    return domain, token


def base_live_available():
    """True when both the Scratch Base URL and read creds are present."""
    return scratch_base_url() is not None and read_creds_available()


def base_missing_reason():
    """Human-readable reason the live Base read arm cannot run, or ``None``.

    Used as the ``pytest.skip`` message so a creds/URL-less environment skips
    **loudly** instead of passing silently.
    """
    if scratch_base_url() is None:
        return (
            f"{SCRATCH_BASE_ENV} is unset — set it to the free-fire Scratch Base URL "
            "(see .env.example) to run the live Base read arm."
        )
    if not read_creds_available():
        return (
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET "
            "(or the legacy LARK_APP_ID/LARK_APP_SECRET) to run the live Base read arm."
        )
    return None


# ---------------------------------------------------------------------------
# Block-zoo live ring (LD-044) — the advisory sibling of the canary above.
# These mirror the canary helpers exactly, keyed on BLOCKZOO_DOC_ENV instead of
# CANARY_DOC_ENV, so the zoo ring inherits the same skip-loudly-never-block
# discipline. Read creds are shared (the ring is READ-ONLY, like the canary).
# ---------------------------------------------------------------------------


def blockzoo_doc_url():
    """Return the zoo-doc URL from ``LARKDOCIO_BLOCKZOO_DOC``.

    Returns ``None`` when the var is unset or blank (so the advisory zoo ring
    skips rather than running against a garbage URL).
    """
    return _env_url(BLOCKZOO_DOC_ENV)


def blockzoo_wiki_url():
    """Return the OPTIONAL zoo-wiki URL from ``LARKDOCIO_BLOCKZOO_WIKI``.

    Returns ``None`` when unset or blank. Only relevant to the wiki-only block
    types (42/51) if the maintainer adds the companion wiki page; the core zoo ring does
    not require it.
    """
    return _env_url(BLOCKZOO_WIKI_ENV)


def blockzoo_available():
    """True when both the zoo URL and read creds are present (the ring can run)."""
    return blockzoo_doc_url() is not None and read_creds_available()


def blockzoo_missing_reason():
    """Human-readable reason the zoo ring cannot run, or ``None`` if it can.

    Used as the ``pytest.skip`` message so a creds/URL-less environment (CI
    without secrets, a fresh clone) skips loudly instead of passing silently.
    The ring is advisory — a missing zoo doc/creds is NEVER a failure.
    """
    if blockzoo_doc_url() is None:
        return (
            f"{BLOCKZOO_DOC_ENV} is unset — set it to the disposable block-zoo "
            "doc URL (see .env.example) to run the advisory zoo ring."
        )
    if not read_creds_available():
        return (
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET "
            "(or the legacy LARK_APP_ID/LARK_APP_SECRET) to run the advisory "
            "zoo ring."
        )
    return None


# ---------------------------------------------------------------------------
# Live-WRITE harness (LD-064, W0-S5) — the credential-gated write ring.
# The write harness self-provisions its OWN disposable doc via the API, so unlike
# the read canary / zoo ring it needs **no scratch-doc URL** — only the
# LARK_WRITE_APP_* pair (+ network). These mirror the read helpers' skip-loudly-
# never-block discipline, keyed on the WRITE credentials.
# ---------------------------------------------------------------------------


def write_creds_available():
    """True when the ``LARK_WRITE_APP_*`` pair resolves to a non-empty pair.

    Delegates to the package's own write-credential resolver (write-only, no
    fallback to read/legacy). That resolver **raises** ``LarkConfigError`` when the
    pair is missing or half-configured; we translate that into ``False`` so the
    live-write ring can *skip loudly* rather than error.
    """
    from larkdocio.common import get_write_credentials
    from larkdocio.errors import LarkConfigError

    try:
        app_id, app_secret = get_write_credentials()
    except LarkConfigError:
        return False
    return bool(app_id and app_secret)


def live_write_missing_reason():
    """Human-readable reason the live-write harness cannot run, or ``None``.

    Used as the ``pytest.skip`` message so a creds-less environment (CI without
    write secrets, a fresh clone) skips **loudly** instead of passing silently.
    """
    if not write_creds_available():
        return (
            "Write creds / LARK_WRITE_APP_* unset — skipping live-write harness "
            "(the W0 gate). It self-provisions its own disposable doc via the API, "
            "so no scratch-doc URL is needed — set LARK_WRITE_APP_ID / "
            "LARK_WRITE_APP_SECRET to run it."
        )
    return None


def load_env():
    """Load the repo-root ``.env`` into ``os.environ`` IF it exists.

    Local runs get creds + ``LARKDOCIO_CANARY_DOC`` from ``.env``; a CI run
    (variables already in the environment) is left untouched, and no ``.env``
    file is ever created as a side effect.
    """
    if DEFAULT_ENV_FILE.exists():
        from larkdocio.auth import init_env

        init_env(str(DEFAULT_ENV_FILE))


def live_identity(env_name, why):
    """A REAL tenant identity for a live arm, read from the environment (``.env``) — LD-684.

    The committed tree carries only obvious fakes for people and apps (an ``open_id`` such as
    ``ou_exampleowner…``), so a live arm that must address a real person reads that person's
    value from ``env_name`` instead, and SKIPS LOUDLY when it is unset rather than running
    against a fake and failing for a reason that is not the product's. ``why`` names the arm.
    """
    import pytest

    load_env()
    value = (os.environ.get(env_name) or "").strip()
    if not value or is_placeholder(value):
        pytest.skip(f"{env_name} is unset, so {why} cannot run. Set it in your .env to the real "
                    "value on your tenant; the repository deliberately carries only a fake.")
    return value
