import os
import re
import json
import logging
from datetime import datetime, timezone

import click

from .config import get_default_config_path, read_config_from_file
from .client import Client
from .mentions import resolve_mentions
from .parser import Parser
from .references import sidecar_payload, summary_lines
from lark_oapi.core.exception import ObtainAccessTokenException

from larkdocio.common import get_read_credentials, init_env, validate_download_url
from larkdocio.common.auth import (
    resolved_read_env,
    token_mint_refusal,
    token_mint_refusal_lines,
)
from larkdocio.errors import LarkConfigError, LarkPermissionError
from larkdocio.sheets import SheetsReadClient
from larkdocio.sheets.export_reader import SheetsExportReader
from larkdocio.base.client import BaseReadClient
from larkdocio.common.sanitize import sanitize_path_string, sanitizes_to_nothing
from larkdocio.common.filename import compose_name
from larkdocio.common.reporting import check_err

logger = logging.getLogger("larkdocio")


class LarkObjectEncoder(json.JSONEncoder):
    """Custom encoder to handle nested Lark SDK objects."""
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)


# --------------------------------------------------------------------------- #
# WHY THE OUTPUT DIRECTORY IS WHAT IT IS — the two reasons, and nothing else.  #
# --------------------------------------------------------------------------- #
#
# A closed vocabulary, because these strings are read by a machine: they land in the returned
# value AND in the ``--dump`` sidecar, and a reason invented at a call site would be a value a
# consumer cannot switch on. They are lower-case, separator-free identifiers rather than
# sentences — the sentence is the log line's job, and a log sentence copied into a machine-read
# file is a string somebody will end up parsing.
#
# LD-650: the vocabulary SHRANK from four to two, and deliberately shrank rather than
# re-spelled. The library used to read the converted body for a document-type-specific
# metadata table and route the output off it, which is the downstream consumer's job and not
# a library's; both of the values that reported that derivation left with it, and the release
# note for 1.49.0 names them verbatim so a consumer can find the branch it must drop rather
# than diffing two vocabularies. The survivors keep their EXACT old spellings, so
# the post-change vocabulary is a strict SUBSET of the old one: a consumer validating an
# answer against the set it already knows never meets a string it has not seen, and only a
# consumer branching on one of the two removed literals has a branch to drop.

#: The caller named the subpath outright. The library derived nothing and read the document not
#: at all — the only way an output root is ever rewritten.
ROUTE_EXPLICIT = "explicit_route"
#: No subpath was supplied, so the output root is used exactly as given. **The library derives
#: none** — it does not read the document to decide where the document goes. The value keeps
#: its old spelling because the old meaning ("nothing was detected, and that is a different
#: fact from 'detected nothing'") is the meaning that survived: nothing is detected here
#: either, and now nothing ever will be.
ROUTE_DISABLED = "routing_disabled"


class RoutedPath(str):
    """An output directory that also carries **why it is that directory** — a ``str``.

    It is a ``str`` subclass, so it concatenates, compares, formats, hashes, keys a dict,
    ``os.path.join``s and JSON-serialises exactly as a plain path does, including
    ``== "/out/a/b/c"``. The one thing that differs is ``type(path) is str``. The precedent is
    :class:`larkdocio.common.destination.ApplicationRootToken`, the same trick for the same
    reason: a value that has to keep answering as its trunk type while carrying one more fact.

    **Why the decision rides the path instead of being re-derived.** The routing rule has one
    definition — the caller's ``--route``, applied by :func:`_apply_explicit_route` — and asking
    a second function *"would this path have been rewritten, and why?"* would be a second
    definition of it, free to disagree with the first. So the branch that decides also reports,
    and the report travels on its own answer.

    **Both label lists are still here, and are still answered unconditionally** (LD-650). They
    read as vestigial now that the library looks for nothing — but the record's five keys are a
    shape a consumer reads, and a key that appears only sometimes is worse than a key that is
    honestly empty: nothing was looked for, so nothing was found and nothing is missing.

    **The same limit the root-token type carries:** every string derived from this one —
    joined, sliced, or passed back through ``str`` — is a plain ``str`` again. So read the
    decision off the value the router handed you, not off something built from it.
    """

    def __new__(cls, path, *, routed, reason, derivation_ran,
                labels_found=(), labels_missing=()):
        self = super().__new__(cls, path)
        self.routed = bool(routed)
        self.reason = reason
        self.derivation_ran = bool(derivation_ran)
        self.labels_found = list(labels_found)
        self.labels_missing = list(labels_missing)
        return self

    @property
    def record(self):
        """The decision as plain JSON-native data — **the one shape**, built once here.

        Both readers take it from this property: the value the download verb returns, and the
        ``--dump`` sidecar's ``route`` key. Two projections of one decision cannot disagree.

        **It carries no path, by construction.** Not the output root, not the derived subpath,
        not the caller's ``--route`` string — because the sidecar's byte-identical determinism
        is a stated property of that file and a path is machine- and invocation-specific.
        Everything here is a function of the document and the switches alone, which is what
        makes two dumps of one document from two different output roots match byte for byte.
        """
        return {
            "routed": self.routed,
            "reason": self.reason,
            "derivation_ran": self.derivation_ran,
            "labels_found": list(self.labels_found),
            "labels_missing": list(self.labels_missing),
        }


class DownloadResult(dict):
    """One whole download's answer: **where the file landed, and how the destination was
    decided** — in the dict-compatible shape the write side's typed create returns already use.

    The verb used to return ``None``, so a programmatic caller could learn neither of those
    things except by parsing log lines — while the ``--dump`` sidecar, which answers the one
    question of this shape already, is written *into* the routed directory the caller could not
    learn. ``None`` → an object breaks no caller: nobody can be relying on a value that was
    never produced.

    **It IS its body** — a ``dict`` subclass, so subscripting, ``.get``, ``in``, iteration,
    ``len``, ``.keys()/.values()/.items()``, ``json.dumps``, ``dict(result)``, ``{**result}``
    and ``==`` against the plain dict all work, and every value is JSON-native so a ledger can
    write it straight out. The grammar is deliberately the one
    :class:`larkdocio.write.client.CreatedDocument` established for a create: the read side and
    the write side answer the same way, and the attributes below are **views onto that same
    body**, never a second copy, so an attribute cannot drift from its key.

    Keys: ``output_path`` (the Markdown file), ``output_dir`` (the directory it landed in, which
    is **not** always the ``-o`` you passed), ``doc_token``, ``title``, ``dump_path`` (the
    ``--dump`` sidecar, or ``None`` when the flag was not given — stated rather than absent, so
    a machine can tell "no sidecar" from "key missing"), ``route`` (the routing decision:
    ``routed``, ``reason``, ``derivation_ran``, ``labels_found``, ``labels_missing``),
    ``disambiguated`` and ``replaced_existing`` (LD-665 — the two facts about the **name** that
    were previously knowable only by parsing log text or by noticing a file had vanished), and —
    as of LD-657 — ``unknown_block_types``, the block types this document used that the library
    does not model, **stated on every successful download** and empty when nothing was lost (the
    discipline ``dump_path`` follows, for the same reason: a machine must be able to tell
    "nothing unmodelled" from "key missing").

    **This is not a new capability** — no operation, endpoint or scope moved, nothing new is
    read, and the Markdown written is byte-identical to what it always was. A richer return
    type is a report on work already done.
    """

    __slots__ = ()

    @property
    def output_path(self):
        """The Markdown file this run wrote."""
        return self.get("output_path")

    @property
    def output_dir(self):
        """The directory the output landed in — the ``-o`` root, or the routed subpath."""
        return self.get("output_dir")

    @property
    def dump_path(self):
        """The ``--dump`` sidecar's path, or ``None`` when no sidecar was written."""
        return self.get("dump_path")

    @property
    def doc_token(self):
        """The docx token the run resolved and read — a wiki URL's wrapper is resolved away."""
        return self.get("doc_token")

    @property
    def title(self):
        """The document's title, as Lark answered it."""
        return self.get("title")

    @property
    def route(self):
        """The routing decision, as data — the same record the ``--dump`` sidecar carries."""
        return self.get("route") or {}

    @property
    def disambiguated(self):
        """Was the title CUT, so that this document's own token went into the filename?

        ``False`` on every name that fits — which is every ASCII title under the character
        ceiling, i.e. almost all of them. ``True`` is the signal that the filename is no longer
        a function of the title alone, and it is the one a consumer keying on the old
        ``[stamp]_<title>.md`` shape needs (LD-665 AC3).
        """
        return bool(self.get("disambiguated"))

    @property
    def replaced_existing(self):
        """Did a file already exist at ``output_path``, and was it overwritten?

        **This is a disclosure, not a fault.** Re-downloading the same document into the same
        directory within the same clock minute lands on the same name by design, and that is
        ``True`` here as well — a filename cannot answer *"is this the same document?"*, so
        this key cannot either, and claiming otherwise would be the guess this library refuses
        to make. What it does answer is the question a pipeline previously had no way to ask:
        *did this download replace bytes?* (LD-665 AC4.)
        """
        return bool(self.get("replaced_existing"))

    @property
    def unknown_block_types(self):
        """What this document used that this library does not model — as DATA (LD-657).

        A list, one entry per **distinct** unmodelled block type in first-seen order, each
        answering ``block_type``, ``count``, ``containers`` and ``children`` — all ints, no
        block ids (see :attr:`larkdocio.read.parser.Parser.unknown_block_types`, which builds
        it, for why the ids deliberately stay behind). **Empty on a document that used none**,
        and present either way: an absent key and a clean document are indistinguishable to a
        machine, which is the whole reason the sibling ``dump_path`` is stated too.

        It is the same decision the ``Unknown block type N …`` warning reports — one recorder
        emits both — so this cannot disagree with the log line a consumer parses today. That
        parse is what this key exists to retire; the warning's text stays frozen until it has.
        """
        return self.get("unknown_block_types") or []

    @property
    def routed(self):
        """Whether the ``-o`` root was rewritten."""
        return bool(self.route.get("routed"))

    @property
    def route_reason(self):
        """Why — one of the two ``ROUTE_*`` values in this module (LD-650 retired the other
        two with the body-sniffing derivation they reported on; the survivors kept their
        spellings, so this is a strict subset of the vocabulary that shipped before)."""
        return self.route.get("reason")


def _validate_and_init(env_file):
    """Load env and verify credentials.

    Returns (app_id, app_secret) on success, or None if credentials are
    missing (after logging the configuration-error guidance).
    """
    init_env(env_file)  # load .env explicitly or via fallback
    refusal = None
    try:
        app_id, app_secret = get_read_credentials()
    except LarkConfigError as exc:
        # LD-580: the getter refuses a pair that does not resolve. The CLI keeps its own
        # operator guidance and its exit-code contract (log, then return ``None``), so the typed
        # refusal is carried INTO the branch below rather than escaping the command — and it,
        # not a second hand-typed copy, is what names the variables that are in force.
        app_id, app_secret, refusal = "", "", str(exc)
    if not app_id or not app_secret:
        logger.error("CONFIGURATION ERROR: Missing Lark App Credentials")
        logger.error(refusal or "Set LARK_READ_APP_ID/LARK_READ_APP_SECRET (preferred) or the legacy LARK_APP_ID/LARK_APP_SECRET.")
        logger.error("Action Required: Obtain these credentials from your Lark App Administrator.")
        logger.error("You can set them by running: larkdocio config --appId YOUR_APP_ID --appSecret YOUR_APP_SECRET")
        logger.error("Or edit the .env file directly.")
        return None
    return app_id, app_secret


#: What a URL this download path cannot resolve is told, per recognised type. The validator
#: **recognises** a spreadsheet and a Base URL — that is what lets a caller route on the type
#: it returns — so the guard that keeps a document download from being handed one lives here,
#: beside the legacy-Docs guard it is the sibling of. Each message names the surface that
#: really reads that type, which the old bare validation error could not.
_NON_DOCUMENT_URL_MESSAGES = {
    "sheets": (
        "that is a SPREADSHEET url, not a document url. A spreadsheet is read through the "
        "Sheets surface, not this download, and it is ONE call: "
        "larkdocio.sheets.read_spreadsheet_markdown(url) takes the url you just typed and "
        "returns the whole workbook as Markdown — every tab walked, and a tab Lark refuses "
        "SKIPPED and disclosed rather than ending the read. (read_spreadsheet(url) is the "
        "same walk without the render.) This message used to send you to "
        "SheetsReadClient.from_read_credentials(domain=…) then query_sheets / "
        "read_used_range / render_spreadsheet: that is the per-tab CONTROL path, it does not "
        "skip a refused tab, and it is the long way round for 'read this spreadsheet'. The "
        "url validator recognised it and handed back its type and token — either is accepted."
    ),
    "base": (
        "that is a BASE url, not a document url. A Base is read through the Base surface, "
        "not this download: larkdocio.base.read_base_markdown(url) renders its tables as "
        "titled Markdown (larkdocio.base also carries the plan-gated record- and "
        "schema-write engines). The url validator recognised it and handed back its type "
        "and token — hand the url to the Base reader. A Base is not a spreadsheet; its "
        "records live in a separate Base document."
    ),
    # The row that ROUTES rather than merely refuses: a folder read now ships, so this names
    # the verb that handles a folder url instead of turning the caller away. The § D2 stance,
    # one layer down from common/url.py's own routing refusals.
    "drive": (
        "that is a DRIVE FOLDER url, not a document url. A folder is a container of many "
        "documents, and this download writes ONE document plus its images — so a folder is "
        "read by its own verb: `larkdocio folder \"<url>\" -o ./out/` enumerates the tree and "
        "writes every document inside as one Markdown file (or call larkdocio.drive.read_folder "
        "from Python). To read a single document with THIS command, pass that document's own url."
    ),
}

#: The legacy-Docs refusal, one literal shared by the two places that raise it (LD-397) — the
#: early local check below and the post-wiki-resolution check in :func:`_resolve_doc`, which is
#: the only one a `wiki` url resolving to `docs` can reach.
#: LD-658 AC2: it used to refer the reader to a Readme/Release section for a `v1_support` label
#: that appears in ZERO shipped documents, so the pointer had no destination. Replaced by what
#: the refusal can state for itself; nothing is added about Lark's own migration, which is
#: unmeasured here. (The old pointer SHAPE is deliberately not reproduced in this comment —
#: a guard in the source repository (`tests/test_drive_folder_cli.py`) derives the population by
#: walking this source.)
_LEGACY_DOCS_MESSAGE = (
    "lark Docs is no longer supported. This reader reads the `docx` type; if the file also has "
    "a `/docx/` url, pass that one instead.")


def refuse_unreadable_url(url, allow_host=""):
    """Refuse — from the URL STRING ALONE — a url this download cannot read.

    **The free half of :func:`_resolve_doc`, split out so it can run first** (LD-397, spike gap
    G15). Parsing the url, routing on its type, and refusing by naming the surface that does read
    it cost nothing: no ``.env``, no credential resolution, no token mint, no packet. They
    therefore run BEFORE the credential step, so a mistyped verb never produces an auth error for
    a command that was never going to run. Returns the validated ``(domain, type, token)``;
    ``_resolve_doc`` calls it too, so there is exactly one copy of the guard.
    """
    domain, doc_type, doc_token = validate_download_url(url, allow_host)

    # A recognised non-document type is refused HERE rather than at validation, so the
    # validator can name what a url is for every caller while this path still only accepts
    # what it can actually read.
    if doc_type in _NON_DOCUMENT_URL_MESSAGES:
        raise LarkConfigError(_NON_DOCUMENT_URL_MESSAGES[doc_type])

    # A `docs` URL is unreadable from its shape alone; a `wiki` url that RESOLVES to `docs` is
    # not, and stays behind the resolve in `_resolve_doc`.
    if doc_type == "docs":
        raise LarkConfigError(_LEGACY_DOCS_MESSAGE)

    return domain, doc_type, doc_token


def _resolve_doc(url, allow_host, config_file, app_id, app_secret):
    """Validate the URL, build the client, resolve wiki nodes, and guard
    against the URL types this download cannot resolve — the unsupported legacy Docs type,
    and the spreadsheet / Base types the validator now recognises.

    Returns (client, config, doc_type, doc_token).
    """
    domain, doc_type, doc_token = refuse_unreadable_url(url, allow_host)

    logger.info(f"Captured document token: {doc_token}")

    config_path = config_file or get_default_config_path()
    config = read_config_from_file(config_path)

    client = Client(app_id, app_secret, domain)

    if doc_type == "wiki":
        node = client.get_wiki_node_info(doc_token)
        doc_type = node.obj_type
        doc_token = node.obj_token

    if doc_type == "docs":
        raise LarkConfigError(_LEGACY_DOCS_MESSAGE)

    return client, config, doc_type, doc_token


def _parse(client, config, doc_token, *, sheets_client=None, sheets_export_reader=None, base_client=None):
    """Fetch docx content and parse it to markdown.

    Returns (docx, blocks, parser, title, markdown).

    ``sheets_client`` is the opt-in embedded-sheet deep-read hook (LD-105): when
    supplied, the Parser deep-reads type-30 embedded sheets (only
    the referenced tab, D3) in place of the placeholder; ``None`` (the default)
    keeps the byte-identical placeholder path with **zero** Sheets API calls (D2).

    ``sheets_export_reader`` is the opt-in **whole-cell (format-level)** style FIDELITY
    hook, consulted only inside a deep-read: when supplied (alongside a
    ``sheets_client``), a deep-read reads the emphasis set on each CELL from the READ-creds
    xlsx export and renders it as MD emphasis; ``None`` → the values-only deep read.
    Run-level emphasis (a styled run inside a cell) comes through the values API either
    way, so a sheet styled that way reads identically with or without this hook.
    """
    docx, blocks = client.get_docx_content(doc_token)
    # Default path keeps the exact ``Parser(config)`` construction (byte-identical,
    # zero Sheets/Base surface); only an opted-in deep-read attaches its client. The
    # ``base_client`` seam (LD-340) mirrors the sheets one exactly: handed a client, the
    # Parser deep-reads embedded Bases; ``None`` keeps the placeholder path with zero Base
    # API calls. Both seams compose — a download may opt into sheets, Bases, or both.
    parser_kwargs = {}
    if sheets_client is not None:
        parser_kwargs.update(
            deep_read_sheets=True,
            sheets_client=sheets_client,
            fidelity_read_sheets=sheets_export_reader is not None,
            sheets_export_reader=sheets_export_reader,
        )
    if base_client is not None:
        parser_kwargs.update(deep_read_bases=True, base_client=base_client)
    parser = Parser(config, **parser_kwargs) if parser_kwargs else Parser(config)

    title = docx.title if hasattr(docx, "title") else doc_token
    markdown = parser.parse_docx_content(docx.document_id, blocks)

    return docx, blocks, parser, title, markdown


def build_deep_read_clients(url, allow_host, app_id, app_secret, *,
                            deep_read_sheets=False, fidelity_read_sheets=False,
                            deep_read_bases=False):
    """Build exactly the opt-in deep-read clients the flags ask for — and nothing else.

    Returns ``(sheets_client, sheets_export_reader, base_client)``, each ``None`` unless its own
    flag is on. **Every default is OFF, and OFF means no object is constructed**: no
    ``SheetsReadClient``, no export reader, no ``BaseReadClient``, and therefore not one Sheets
    or Base API call (D2/D8, LD-340).

    Extracted from :func:`handle_download_command` for LD-384, where the ``folder`` walk needed
    the same three opt-ins for the documents it reads. It is ONE construction shared by both
    verbs on purpose: a second copy is how ``--deep-read-sheets`` on one command would come to
    mean something slightly different from ``--deep-read-sheets`` on the other.
    """
    sheets_client = None
    sheets_export_reader = None
    base_client = None
    if deep_read_sheets or deep_read_bases:
        domain = validate_download_url(url, allow_host)[0]
        if deep_read_sheets:
            sheets_client = SheetsReadClient(app_id, app_secret, domain)
            # Opt-in WHOLE-CELL (format-level) style FIDELITY read (LD-117 D5a) — only meaningful
            # WITH a deep-read. Off by default: NO xlsx export is issued, the deep read stays
            # values-only. When opted in, a READ-creds export reader (D1, least-privilege —
            # scope PROVEN); a deep-read then renders whole-cell bold/italic as MD emphasis,
            # degrading to values-only on any export error.
            if fidelity_read_sheets:
                sheets_export_reader = SheetsExportReader.from_read_credentials(domain)
        # Opt-in embedded-BASE deep read (LD-340): a READ-creds Base client on the same domain
        # the doc resolve used. Every failure inside the bridge degrades to the placeholder — a
        # read never fails because a Base could not be read.
        if deep_read_bases:
            base_client = BaseReadClient(app_id, app_secret, domain)
    return sheets_client, sheets_export_reader, base_client


def _apply_explicit_route(output_dir, route):
    """Place the output under a CALLER-SUPPLIED subpath (LD-340 group c, AC5).

    The consumer supplies the path; **the library infers nothing** — no title parsing, no
    title grammar, no filename heuristic, no defaulting from document content.
    This function reads the document not at all — and since LD-650 **nothing else in the
    library does either**: the three-table-row derivation this sentence used to carve itself
    out from is gone, so the guarantee is no longer "the one derivation stays over there" but
    "there is no derivation at all". A caller-supplied ``--route`` is the ONLY thing that ever
    rewrites the ``-o`` root. The negation above is kept verbatim on purpose: it is a contract
    **by negation**, and the grammar it names is the example that makes the promise concrete,
    not vocabulary to be swept.

    The supplied path goes through ``sanitize_path_string`` (spaces → underscores, the
    OS-reserved characters stripped) — but it is **not**
    lower-cased, because the caller's spelling is theirs, not a value inferred from a document.
    It **cannot escape the output root**: an absolute path, a ``.`` / ``..`` navigation segment,
    or an empty interior segment is **refused with the reason named**, never silently
    normalised. A leading/trailing separator is a harmless convenience and is tolerated.

    **A segment the sanitizer would empty is refused too** (LD-659): ``--route '***'`` used to
    write to ``<out>/untitled/`` — a directory the caller never named — because the sanitizer
    substitutes ``untitled`` for a name that strips to nothing. A caller-supplied segment is the
    caller's to fix, so this one refuses rather than substituting; a document *title* that
    strips to nothing still gets the substitution, disclosed
    (:func:`larkdocio.common.sanitize.sanitizes_to_nothing` records why the two differ).
    """
    if os.path.isabs(route) or route.startswith(("/", "\\")):
        raise click.ClickException(
            f"--route must be a relative subpath under -o, but {route!r} is an absolute path. "
            "Give it as area/section/topic, not a rooted path."
        )
    if not route.strip():
        raise click.ClickException(
            "--route was empty — give it as area/section/topic."
        )
    segments = []
    for seg in re.split(r"[/\\]", route.strip().strip("/\\")):
        if seg == "":
            raise click.ClickException(
                f"--route {route!r} has an empty path segment — give it as "
                "area/section/topic with no doubled separators."
            )
        # LD-658 AC6: the check runs on the SANITIZED segment, because sanitizing is what
        # MANUFACTURES the navigation segment. `sanitize_path_string` strips `\ / : * ? " < > |`,
        # so `.?.` becomes `..` after this line and the literal test above it never saw one.
        # Executed at LD-658: `..`, `.` and `a/../b` were correctly refused while `.?.`, `.:.`
        # and `..*` all returned `<out>/..`, and `.?./.?./escaped` returned
        # `<out>/../../escaped` — materialized. The order is the whole fix: sanitize, THEN
        # judge. The negation this function's docstring and the rendered `--help` both state as
        # an absolute ("it cannot escape the output root … never silently normalised") was
        # false in shipped bytes until this moved.
        # LD-659 AC1b: a segment the sanitizer would EMPTY is refused, not substituted. This
        # is asked BEFORE sanitizing, because the sanitizer's answer for such a segment is the
        # literal directory name `untitled` — indistinguishable from a caller who typed
        # `--route untitled` and is entitled to get it. Refusing here rather than disclosing is
        # the caller-supplied half of the split recorded on `sanitizes_to_nothing`: a document
        # TITLE that sanitizes away has to become something, but a `--route` segment is the
        # caller's own input and they can correct it. Until this, `--route '***'` wrote to
        # `<out>/untitled/` — a path nobody named, created in silence, past the LD-658 traversal
        # guard that was working exactly as designed.
        if sanitizes_to_nothing(seg):
            raise click.ClickException(
                f"--route {route!r} has a segment with nothing usable in it: stripping the "
                f"OS-reserved characters from {seg!r} leaves nothing to name a directory with. "
                "Give a subpath whose every segment survives that stripping — larkdocio will "
                "not invent a directory name for you."
            )
        safe = sanitize_path_string(seg)
        if safe in (".", ".."):
            if safe == seg:
                raise click.ClickException(
                    f"--route {route!r} may not contain a {seg!r} segment — it would navigate "
                    "outside the output root. Give a subpath that stays under -o."
                )
            # The caller did not type `..`; sanitizing produced it. Say both, or they go looking
            # for a segment that is not in their command line.
            raise click.ClickException(
                f"--route {route!r} may not contain the segment {seg!r} — stripping the "
                f"OS-reserved characters from it leaves {safe!r}, which would navigate outside "
                "the output root. Give a subpath that stays under -o."
            )
        segments.append(safe)
    return os.path.join(output_dir, *segments)


def _fetch_and_relink(tokens, fetch_fn, output_dir, img_dir, markdown, noun):
    """Download each asset token and rewrite its first markdown occurrence to a
    local relative link. The shared body of the twin image/board loops.

    ``fetch_fn(token, img_dir)`` is the client download method (``download_image``
    or ``download_board_image``); ``noun`` is the warn-message noun (``image`` /
    ``board image``). ``markdown`` is threaded in and out (``str`` is immutable).
    Per-asset failures warn-and-continue with the byte-identical
    ``Could not download {noun} {token}: {e}`` string and leave the markdown
    unchanged. Returns the (possibly updated) markdown.
    """
    for token in tokens:
        try:
            local_link = fetch_fn(token, img_dir)
            rel_link = os.path.relpath(local_link, output_dir)
            rel_link = rel_link.replace(os.sep, '/')
            markdown = markdown.replace(token, rel_link, 1)
        except Exception as e:
            logger.warning(f"Could not download {noun} {token}: {e}")
    return markdown


def _download_images_and_boards(client, config, parser, output_dir, markdown):
    """Download image and board assets (unless disabled), rewriting their
    tokens in the markdown to local relative links. Returns the updated markdown.
    """
    if not config.output.skip_img_download:
        img_dir = os.path.join(output_dir, config.output.image_dir)
        # The fetch method is resolved lazily (per-token, inside the loop's try) —
        # matching the original inline loops, which never touched the attribute
        # when the token list was empty.
        markdown = _fetch_and_relink(
            parser.img_tokens,
            lambda token, d: client.download_image(token, d),
            output_dir, img_dir, markdown, "image",
        )
        markdown = _fetch_and_relink(
            parser.board_tokens,
            lambda token, d: client.download_board_image(token, d),
            output_dir, img_dir, markdown, "board image",
        )

    # Attachment binaries (LD-040) are fetched ONLY when explicitly opted in
    # (download_attachments, default False → zero attachment network — maintainer
    # directive: never fetched by default). Best-effort, warn-and-continue on
    # failure, reusing the drive media download; the file marker keeps its
    # name+token (no token→link substitution — the binary lands in the assets dir
    # alongside images). Independent of skip_img_download (a separate knob).
    if config.output.download_attachments:
        for file_token in parser.file_tokens:
            assets_dir = os.path.join(output_dir, config.output.image_dir)
            try:
                client.download_image(file_token, assets_dir)
            except Exception as e:
                logger.warning(f"Could not download attachment {file_token}: {e}")

    return markdown


def _resolve_mentions(client, config, parser, markdown):
    """Resolve @mention open_ids to display names and substitute in the markdown
    (LD-053), mirroring the image token→local-link substitution.

    The parser collects the distinct open_ids offline; here (download time) we do the
    network: resolve them via the contacts batch API (best-effort,
    ``client.batch_get_user_names`` handles the graceful degrade — one info log + fall
    back to raw ``@ou_id`` on a missing-scope error) and rewrite ``@ou_id`` →
    ``@Display Name``.

    Gated by ``config.output.resolve_mentions`` (default True). With the knob off,
    or with no mentions, or when nothing resolved (scope absent), the markdown is
    returned **byte-identical** to today's raw ``@ou_id`` passthrough. A partial
    result rewrites only the resolved ids.

    **The substitution itself lives in ``read.mentions`` (LD-173), not here**, because the
    documented in-process read path resolves through the ``Parser(read_client=…)`` seam and
    the two paths must not be able to disagree: one implementation, two call sites. This
    function stays the pipeline's step (and its stable name), delegating the work.
    """
    return resolve_mentions(
        markdown,
        getattr(parser, "mention_user_ids", None),
        client,
        enabled=config.output.resolve_mentions,
    )


def _report_unfetched_references(parser):
    """Log what this document REFERENCED and the run did not fetch (LD-334).

    The reader's per-block markers answer *"what is in this paragraph?"*; after a
    sixteen-document run the question is *"what did this run not get?"*, and answering it
    meant grepping every output file for four marker strings. This is the same disclosure
    lifted from per-block to per-run — a **projection of the parsed tree** (the queue the
    handlers filled from their own nodes), never a second reading of the Markdown, so the
    summary and a marker cannot disagree.

    ``logger.info``, not ``print``/``click.echo``: this module is imported by in-process
    callers as well as the CLI. INFO, not WARNING — an unfetched reference is the *designed*
    behaviour of an opt-in deep read, so it is a disclosure and not a fault; one warning per
    document at volume only teaches the operator to ignore warnings. A document with nothing
    unfetched logs **nothing at all**: this is a disclosure, not a per-run banner.
    """
    for line in summary_lines(getattr(parser, "reference_notes", []) or []):
        logger.info(line)


def _dump_json(docx, blocks, output_dir, doc_token, parser=None, local_time=False,
               route=None):
    """Dump the raw document/blocks payload as JSON. Returns the sidecar's path, or ``None``
    when the write failed.

    The sidecar is a ledger's input (it carries the document's own ``revision_id`` and
    title), which is why it also DECLARES the timezone of the Markdown filename's stamp
    (LD-335): a ledger that timestamps its ingestion off the filename reads JSON, not
    ``--help``, and read as local time the stamp is simply wrong by the machine's offset.
    The declaration is two keys — the basis and the format. The **format** is a constant; the
    **basis** reports the run's ACTUAL choice (LD-340): ``"UTC"`` on the default path, or
    ``"local"`` when ``--local-time`` was passed. A sidecar that said ``UTC`` while the filename
    was the local clock would be worse than no sidecar — a ledger keying its ingestion off the
    filename would be wrong by the machine's offset. The clock reading itself still belongs to
    the filename (``_write_markdown``) and is deliberately not repeated here, so the sidecar
    stays a function of the payload (and the mode) alone — two dumps in one run are byte-identical.

    For the same ledger reason it carries ``unfetched_references`` when a ``parser`` is
    handed in (LD-334): a bulk-ingestion pipeline asking *"what did this run not get"*
    reads JSON, not a log line, and leaving the count log-only would guarantee it is
    re-derived by parsing log text. Counts, kinds, reasons and the identifying token — a
    function of the parse alone, so the sidecar stays deterministic — and, unlike the log,
    an explicit **zero**, because an absent key and a clean run are indistinguishable to a
    machine. With no ``parser`` (a caller with no parse in hand) the payload is exactly what
    it always was.

    And for the third time the same reason (LD-598), it carries the ``route`` decision when one
    is handed in: *"did the router rewrite my -o root, and why"* is a question a pipeline was
    otherwise answering by parsing log text. **What it must never carry is a path** — not the
    output root, not the derived subpath, not the caller's supplied one: this file's
    byte-identical determinism is a stated property, and a path is machine- and
    invocation-specific, so writing one in would break the property the file is built on. The
    record :attr:`RoutedPath.record` builds is a function of the document and the switches
    alone, which is exactly why it can be in here at all. The place a caller learns the path is
    the value the download verb returns (:class:`DownloadResult`) — and that value also names
    this sidecar, so the answer is no longer behind the question. With no ``route`` (a helper
    called directly, with no routing decision in hand) the payload is exactly what it was.
    """
    json_name = f"{doc_token}.json"
    output_path = os.path.join(output_dir, json_name)

    dump_data = {
        "document": getattr(docx, "__dict__", str(docx)),
        "blocks": [],
        "filename_timestamp": {
            "timezone": "local" if local_time else "UTC",
            "format": "[%Y-%m-%d_%H%M]",
        },
    }

    if route is not None:
        dump_data["route"] = route

    if parser is not None:
        dump_data["unfetched_references"] = sidecar_payload(
            getattr(parser, "reference_notes", []) or []
        )

    for b in blocks:
        block_dict = getattr(b, "__dict__", str(b))
        dump_data["blocks"].append(block_dict)

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, indent=4, ensure_ascii=False, cls=LarkObjectEncoder)
        logger.info(f"Dumped JSON document data to {output_path}")
        return output_path
    except Exception as e:
        logger.warning(f"Failed to dump pure JSON due to serialization issues: {e}")
        # No path is reported for a dump that did not complete: a caller handed a path to a
        # file whose contents are truncated is worse off than one told there is no sidecar.
        return None


class _WrittenMarkdown(str):
    """The path ``_write_markdown`` wrote, carrying **how the name was decided**.

    A ``str`` subclass, and that is the point: the value **is** the path, so every existing
    caller — ``open``, ``pathlib.Path``, ``os.path.basename``, the equality assertions in ten
    tests — behaves byte-identically to the plain string it replaced. What is added is two
    facts the writing function is the only place that knows, and which LD-665 needs carried out
    to :class:`DownloadResult` rather than logged: whether the name was disambiguated, and
    whether a file was replaced.

    Private and internal on purpose. The public answer is the two keys on ``DownloadResult``;
    ``handle_download_command`` reads these attributes and puts plain ``bool`` s in the body, so
    nothing of this type reaches a caller and the result stays JSON-native.
    """

    __slots__ = ("disambiguated", "replaced_existing")

    def __new__(cls, path, *, disambiguated, replaced_existing):
        written = super().__new__(cls, path)
        written.disambiguated = disambiguated
        written.replaced_existing = replaced_existing
        return written


def _write_markdown(config, output_dir, doc_token, title, markdown, local_time=False):
    """Compute the output filename (timestamped title when configured) and
    write the markdown file. Returns the path written, as a :class:`_WrittenMarkdown`.

    LD-598: the path was computed here and reported only into the log, so the one function that
    knows the answer to *"where did my file land"* was the one place it could not be read from.
    It is returned — the caller (``handle_download_command``) carries it into its own answer.

    LD-665: the filename is composed by :func:`larkdocio.common.filename.compose_name` rather
    than by an f-string here, so that the budget and the collision are decided where the WHOLE
    name is visible. **The name a caller gets back is unchanged unless the title was cut** —
    and when it was cut it now carries the document's own token, because a truncated title is
    not a name, it is a prefix that every document sharing it would answer to.
    """
    # UTC basis (LD-227) is the DEFAULT and does not move: the stamp is a function of the
    # instant alone, so the same document downloaded at the same moment on two machines in
    # different zones lands under the same name (cross-machine byte-identity). LD-340 adds an
    # OPT-IN local-clock basis (``--local-time``): the caller trades that byte-identity for a
    # name that reads in their own zone. The rendered SHAPE is unchanged either way — only the
    # digits move; no offset, no ``Z`` and no zone suffix is appended (see the flag's help).
    if local_time:
        now_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    else:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")

    md_name = f"{doc_token}.md"
    composed = None
    if config.output.title_as_filename:
        safe_title = sanitize_path_string(title)
        if safe_title and safe_title != "untitled":
            # The whole name is composed in ONE place (LD-665) — see
            # `larkdocio.common.filename`. What moved here is not the byte budget (that is
            # LD-659's, in the sanitizer, and is untouched) but the two facts only this seam
            # knows: what is wrapped around the title, and whether the title was CUT. A cut
            # title is no longer this document's name — it is a prefix every document sharing
            # it would answer to — so the document's own token joins it, paid for out of the
            # title's bytes and never out of the extension.
            composed = compose_name(title, prefix=f"[{now_str}]_", suffix=".md",
                                    token=doc_token)
            md_name = composed.name
        else:
            md_name = f"[{now_str}]_{doc_token}.md"

    output_path = os.path.join(output_dir, md_name)
    # Asked BEFORE the truncating `open`, because afterwards the answer is always yes and the
    # bytes that would have answered it are gone. This is a DISCLOSURE, not a guard: it does
    # not refuse, and the window between the check and the write is not defended — a filename
    # cannot answer *"is this the same document?"*, so refusing would break the legitimate
    # re-download that this branch deliberately keeps working (LD-665 AC4).
    replaced = os.path.exists(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info(f"Downloaded markdown file to {output_path}")
    if replaced:
        # INFO, not WARNING, and the reason is `_report_unfetched_references`'s: re-downloading
        # a document into the same directory in the same minute is the DESIGNED behaviour and
        # is common, so a warning here would fire mostly on correct runs and teach the operator
        # to ignore warnings. The load-bearing half of this disclosure is the structured field
        # on `DownloadResult`, which a pipeline can read without parsing this line.
        logger.info(
            "A file already existed at %s and was replaced. If that was not this same document "
            "being downloaded again, two documents have converged on one name — "
            "`replaced_existing` on the download's result reports it as data.",
            output_path)
    return _WrittenMarkdown(
        output_path,
        disambiguated=bool(composed and composed.disambiguated),
        replaced_existing=replaced,
    )


#: Lark's own codes for *"this application cannot read this document, or there is nothing at
#: that token"* — **the reader's own classification**, and the reader's alone. Lark does not
#: separate the two outcomes on this route, which is why the guidance below names both in one
#: sentence instead of picking one. Each code's meaning and standing are authored once, for the
#: whole library, in :mod:`larkdocio.common.error_codes`; what is authored here is which of
#: them THIS surface routes to THIS banner.
#:
#: Compared as strings so the check is representation-agnostic — the SDK hands back an ``int``
#: on some routes and a ``str`` on others — the same discipline as
#: :data:`larkdocio.errors.RATE_LIMIT_CODE`.
DOCUMENT_ACCESS_CODES = ("99991672", "1061004")

#: The one substring this branch still greps, and why it MUST stay: it is Lark's own ``msg`` on
#: this family, and a code-less error can carry it. Not every raise on the read path has a Lark
#: ``code`` to offer — ``read.client._write_binary``'s *"response contained no file content"*
#: has none at all, and the board-download raise is documented to answer ``code``/``msg``
#: ``None`` for exactly the permission failures this banner is for. On a path with no code
#: there is nothing to type, so a substring is not a shortcut, it is the only evidence there is.
_NO_READ_PERMISSION_MARKER = "not read permission"


def _document_access_refusal(e) -> bool:
    """Whether ``e`` is *"I could not read that document"* — TYPED, not grepped (LD-531).

    Three arms, in the order of how much they know:

    1. :class:`~larkdocio.errors.LarkPermissionError` — the library already decided this was a
       **scope denial**, through :func:`larkdocio.errors.api_error`, which is the door every
       READ surface refuses through. (It is not the only door in the library: a leg with an
       error family of its own classifies through :func:`larkdocio.errors.api_error_as` and
       carries the record on ``err.denial`` while keeping its own class. None of those legs is
       reachable from this walk, so this arm stays a class check.) Catching the class rather
       than re-deriving it from message text is the point of the class existing.
    2. Lark's own :data:`DOCUMENT_ACCESS_CODES`, off ``e.code``.
    3. :data:`_NO_READ_PERMISSION_MARKER`, kept for the code-less paths named above.

    **What this no longer does, on purpose: route on the bare words "not found".** See
    :func:`_report_error`.
    """
    if isinstance(e, LarkPermissionError):
        return True
    code = getattr(e, "code", None)
    if code is not None and str(code) in DOCUMENT_ACCESS_CODES:
        return True
    return _NO_READ_PERMISSION_MARKER in str(e).lower()


def _report_error(e, env_file: str = None):
    """Map an exception to the appropriate operator-facing error guidance.

    **The routing is typed; the operator-facing text is byte-identical (LD-531).** Every line
    logged below and both ``ClickException`` messages are exactly the bytes they were before —
    they are consumer-reaching text — and what changed is how an exception reaches them.

    **Two reach changes, both deliberate, both pinned by tests.**

    *Narrowed.* The bare words **"not found"**, anywhere in any message, used to route here.
    That swallowed failures that were nothing to do with document access — anything whose text
    happened to contain the phrase — and told the operator to go and share a Lark document
    about it. It is Lark's ``msg`` for ``1061004``, so the coded arm above still catches the
    real case; what it no longer catches is an unrelated error wearing the same two words. Such
    an error now takes the default arm: it still exits non-zero, and it now shows its own
    message and Lark's own code instead of advice that cannot help.

    *Widened.* A :class:`~larkdocio.errors.LarkPermissionError` now routes here whatever its
    code — including the denial codes this library has never captured, which
    :func:`larkdocio.permissions.looks_like_scope_denial` recognises by message shape. Before,
    only two code numbers appearing as text in the message did. A scope denial is precisely
    what this banner is for, so the widening is the banner reaching the cases it was written
    for.

    The IP-block branch below stays substring-only, and must: no measurement here has ever
    recorded a Lark code for an IP-allowlist refusal, so there is no code to route on.

    **Which is exactly why it runs LAST, not first (LD-658 AC1).** It used to run first, and a
    bare ``"ip" and "denied"`` substring test cannot tell an IP refusal from a document-access
    refusal whose *token* happens to contain the letters ``ip``: a Lark document token is 22-24
    base62 characters, so ~**2.15%** of them do (measured over 200,000 synthetic tokens at
    LD-658, ~doubled for a wiki url whose refusal text carries two tokens), and Lark's denial
    ``msg`` supplies the ``denied``. The library classified those correctly and then printed the
    wrong remedy — go and edit an IP allowlist, when the fix is Share -> Add Application. The
    ordering below is the whole fix, and it generalises: **a typed classification is asked
    first, and the substring heuristic gets only what the typed arm did not claim.** No text
    and no classifier changed; a genuine IP refusal carries no document-access code and no
    ``not read permission``, so it still reaches its own banner.
    """
    error_msg = str(e)

    # 0. The two BUILTIN classes the CLI's refusal seam now converts (LD-658 AC4) pass straight
    #    through, un-bannered. `check_err` below prints "Report the following if it is a bug",
    #    and it would print it BEFORE the seam ever saw the exception — which is exactly the
    #    measured defect: a mistyped url printed its refusal, then the bug banner, and only
    #    then reached a handler. Re-raised rather than converted here, so the seam stays the one
    #    place the conversion is decided (`cli._RefusalUniformCommand`, which explains why the
    #    two classes are treated differently once they arrive).
    if isinstance(e, (ValueError, OSError)):
        # `raise e`, not a bare `raise`: a bare one needs an ACTIVE exception, so calling this
        # function outside an `except` block would replace the caller's error with
        # `RuntimeError: No active exception to reraise` and lose the original. The one
        # production call site is inside an `except`, so that was latent — and naming `e`
        # removes the trap for free (LD-658 fix round).
        raise e

    # 1. Document Permission Error — typed, see the docstring. TWO arms, and which one fires is
    #    decided by whether Lark named a SCOPE (LD-658 AC1b).
    if _document_access_refusal(e):
        # Lark's own answer, FIRST, in both arms. This arm used to log advice and nothing else,
        # so the body Lark actually sent was dropped on the floor — and on the scope-denial arm
        # that body is the only place the missing permission is spelled. The default arm has
        # always echoed it first (`common/reporting.check_err`); these arms now match it.
        logger.error(error_msg)

        denial = getattr(e, "denial", None)
        if denial is not None:
            # A SCOPE denial. The library is holding a `PermissionDenial` that already names the
            # exact missing scope, the credential pair the call was made on, and Lark's own
            # console deep link (the reader passes both `body=` and `credential_env=` —
            # `read/client.py::_ensure_success`). This used to print the Share dialog instead:
            # the right wall, the wrong console. `detail()` is the same string every other
            # surface relays, so this is a PRINT, not a second derivation of the remedy.
            logger.error("LARK API ERROR: Missing App Permission (a Lark SCOPE, not a share)")
            logger.error(denial.detail())
            # The step the loop dies on. An operator who granted the scope and never released a
            # new app version sees this identical failure and concludes the grant was wrong, so
            # they go round the SHARE wall instead — two wrong walls, neither of them the one
            # they are standing at. `LARK_SETUP.md` already states the release step for the
            # grant loop; the refusal now states it at the moment it is needed.
            # The operator-facing lines here are ONE source literal each, deliberately long, the
            # same shape as the two banners below: a guard in the source repository
            # (`tests/test_error_code_registry.py`) § F1
            # holds every shipped line byte-identical by folding this file's own text, and a
            # wrapped literal folds with its quote characters in the middle.
            logger.error("Action Required: grant the permission(s) above on the app in the Lark console — and then RELEASE a new version of the app. A grant takes effect on RELEASE, not on save: an unreleased grant leaves this call failing exactly as it does now.")
            raise click.ClickException("Download failed: missing app permission — see the guidance above.")

        # No scope was named — the denial-less `1061004` / `not read permission` case, which
        # really IS a sharing problem. Byte-identical to what it has always said.
        logger.error("LARK API ERROR: Missing Document Permissions")
        logger.error("The Lark App does not have permission to read this document, or it does not exist.")
        logger.error("Action Required: Open the Lark Document in your browser, click 'Share' -> 'Add Application' (or 'App Application' / 'Add Integration'), and search for your Lark App to give it read access.")
        # B1: exit nonzero on a permission failure (was previously a silent exit 0).
        raise click.ClickException("Download failed: missing document permissions — see the guidance above.")

    # 2. IP Block Error — the substring fallback, and it goes SECOND on purpose (see docstring).
    if "ip" in error_msg.lower() and "denied" in error_msg.lower():
        # Lark's own answer, first, here too — and the reason is STRONGER on this arm than on
        # the typed one above (LD-658 ruling, after AC1). Since the reorder this arm fires only
        # on what the typed classification DECLINED, which makes it, by construction, the arm
        # where our own confidence is lowest: a pure heuristic over somebody else's message
        # text. Lark's body is worth most exactly where our classification is worth least. Added
        # ABOVE the banner, so every pinned consumer line below keeps its bytes and its order.
        logger.error(error_msg)
        logger.error("LARK API ERROR: IP Address Blocked")
        logger.error("Your current IP address is not authorized to use this Lark Application.")
        logger.error("Action Required: Please check with your Lark App Administrator to add your current IP address to the App's IP Allowlist in the Lark Developer Console.")
        # B1: a failed download must exit nonzero so consumer automation can tell
        # success from failure. click.ClickException prints its message and exits 1
        # without a traceback (the operator guidance above is what matters here).
        raise click.ClickException("Download failed: IP address blocked — see the guidance above.")

    # 3. Token-mint failure — a wrong App ID / App Secret (LD-658 AC4).
    #
    #    The GUIDANCE is authored once, in `common/auth.token_mint_refusal_lines`, because the
    #    CLI's refusal seam needs the same words for `folder` and `roundtrip` — neither of which
    #    reaches this function at all. What this call site contributes is the one thing it knows
    #    better than the seam: WHICH credential pair can be at fault. The read path resolves a
    #    preferred pair with a legacy fallback and nothing else, so exactly one pair is in force
    #    and `resolved_read_env()` names it — asked rather than hard-coded, because pointing a
    #    legacy-configured caller at variables they do not have is the defect that function
    #    exists to prevent. The seam, which cannot know, says so instead of guessing.
    if isinstance(e, ObtainAccessTokenException):
        logger.error(error_msg)
        # `env_file` is threaded from the caller (LD-658 fix round). Without it this named
        # `./.env` unconditionally, so a run invoked with `--env-file /somewhere/else.env` told
        # the user to edit a file that was NOT the one read — advice that cannot be followed,
        # which is the defect class this issue exists to remove. With nothing passed the
        # fallback is still right: `init_env`'s own no-argument resolution IS `<cwd>/.env`.
        for line in token_mint_refusal_lines((resolved_read_env(),), env_file):
            logger.error(line)
        raise click.ClickException(token_mint_refusal("Download"))

    # Default error handler — re-raises the original exception (nonzero exit),
    # keeping unknown-error propagation consistent with the known-error paths above.
    check_err(e)


def handle_download_command(url: str, output_dir: str, allow_host: str, dump: bool, config_file: str, env_file: str = None, deep_read_sheets: bool = False, fidelity_read_sheets: bool = False, deep_read_bases: bool = False, local_time: bool = False, route: str = None) -> DownloadResult:
    """Run one whole download: URL in, Markdown (plus its images) written under ``output_dir``.

    The command behind ``larkdocio download`` and the only place the read pipeline is wired
    end to end — credentials, URL/host validation, wiki-to-docx resolution, block read,
    parse, image and board-image fetch, and the file write. On failure it raises
    ``click.ClickException`` (so the CLI exits nonzero) or the typed refusal class, unchanged.

    **On success it answers with a :class:`DownloadResult`** — where the file landed,
    the directory it landed in (which is not always the ``-o`` you passed), the ``--dump``
    sidecar's path if one was written, and the routing decision. It used to return ``None``,
    which left a programmatic caller unable to learn either of the first two except by parsing
    the log lines this function emits. The change is additive by construction: nobody can be
    relying on a value that was never produced.
    """
    try:
        # LD-397: the checks that cost nothing run FIRST. A url this download cannot read is
        # refused from its shape alone, so a wrong-verb or wrong-surface invocation never
        # resolves a credential and never reaches the network — and, when the credentials are
        # ALSO wrong, the user is told about the url they typed rather than sent to debug an
        # auth error for a command that was never going to run.
        refuse_unreadable_url(url, allow_host)

        credentials = _validate_and_init(env_file)
        if credentials is None:
            # B1: missing credentials is a failed download → exit nonzero
            # (the operator guidance was already logged by _validate_and_init).
            raise click.ClickException("Download failed: missing Lark App credentials — see the guidance above.")
        app_id, app_secret = credentials

        client, config, doc_type, doc_token = _resolve_doc(url, allow_host, config_file, app_id, app_secret)

        # Opt-in embedded-sheet deep-read (LD-105). OFF by default:
        # NO SheetsReadClient is built and NO Sheets API is touched, so the docx
        # download is byte-identical to today (D2/D8). When opted in, build a
        # read-creds sheets client (same domain as the docx read) for the type-30
        # bridge; the domain comes from the same URL validator the doc resolve used.
        sheets_client, sheets_export_reader, base_client = build_deep_read_clients(
            url, allow_host, app_id, app_secret,
            deep_read_sheets=deep_read_sheets,
            fidelity_read_sheets=fidelity_read_sheets,
            deep_read_bases=deep_read_bases,
        )

        docx, blocks, parser, title, markdown = _parse(
            client, config, doc_token,
            sheets_client=sheets_client, sheets_export_reader=sheets_export_reader,
            base_client=base_client,
        )

        # Routing: an explicit --route (LD-340 group c) is a CALLER INSTRUCTION, and since
        # LD-650 it is the ONLY instruction there is — the library no longer reads the
        # converted body to decide where the converted body goes. `is not None`, deliberately,
        # NOT truthiness: `--route ''` is a caller who supplied a route and got it wrong, and
        # it must reach the refusal below rather than silently becoming a no-op.
        if route is not None:
            # A RoutedPath in the explicit branch too, so ONE type carries the decision
            # whichever way it was made — and `derivation_ran=False` says what it has always
            # said: the library read the document not at all. No label list, because none was
            # consulted, and the supplied subpath itself is deliberately NOT echoed into the
            # record (see `RoutedPath.record`: no path, ever, so the sidecar stays
            # byte-deterministic).
            output_dir = RoutedPath(
                _apply_explicit_route(output_dir, route),
                routed=True, reason=ROUTE_EXPLICIT, derivation_ran=False)
            # WARNING because it rewrites the caller's -o root, and a library caller with no
            # handler still needs to know where the file went (logging.lastResort emits
            # WARNING and above). This line is parsed downstream: it does not move.
            logger.warning(f"Routing to the caller-supplied --route path: {output_dir}")
        else:
            # REWRITTEN, not deleted (LD-650). The next statement reads `.record` off this
            # value for BOTH branches, so a bare `output_dir` here — the shape this branch
            # collapses to if the derivation is simply cut away — is an AttributeError on
            # every ordinary download, invisible to a smoke import. The root is used exactly
            # as the caller gave it, and the RoutedPath says so.
            output_dir = RoutedPath(
                output_dir, routed=False, reason=ROUTE_DISABLED, derivation_ran=False)
        route_record = output_dir.record

        markdown = _download_images_and_boards(client, config, parser, output_dir, markdown)

        # Resolve @mention open_ids → display names (LD-053, download-time like
        # image substitution; gated by resolve_mentions, default on, graceful
        # degrade to raw @ou_id when the contacts scope is absent).
        markdown = _resolve_mentions(client, config, parser, markdown)

        # Ensure output dir exists
        os.makedirs(output_dir, exist_ok=True)

        dump_path = None
        if dump:
            dump_path = _dump_json(docx, blocks, output_dir, doc_token, parser=parser,
                                   local_time=local_time, route=route_record)

        output_path = _write_markdown(
            config, output_dir, doc_token, title, markdown, local_time=local_time)

        # Last, after the file is written, so the operator reads "here is your file" and
        # then "here is what it references and this run did not get" in that order.
        _report_unfetched_references(parser)

        # `str(output_dir)` rather than the RoutedPath: the decision is already carried, whole,
        # under `route`, and a body key whose value is a str SUBCLASS would make the result
        # unequal to the plain dict it is supposed to compare equal to under `json.loads`.
        # `str(output_path)` for the same reason `output_dir` is stringified above: the value
        # `_write_markdown` returns is a str SUBCLASS carrying the two facts below, and the
        # body is contractually JSON-native plain values. The subclass is the transport from
        # the one function that knows, not part of the answer.
        return DownloadResult({
            "output_path": str(output_path),
            "output_dir": str(output_dir),
            "doc_token": doc_token,
            "title": title,
            "dump_path": dump_path,
            "route": route_record,
            "disambiguated": bool(getattr(output_path, "disambiguated", False)),
            "replaced_existing": bool(getattr(output_path, "replaced_existing", False)),
            # LD-657. A PROJECTION of the parse that already happened — the parser's own
            # recorder wrote it in the same call that emitted each `Unknown block type N …`
            # warning, so this key and that log line cannot disagree. `getattr` with a default
            # for the same reason `reference_notes` is read that way: the Parser is a seam, and
            # a stand-in handed in at it must not be able to make a stated key disappear.
            # Stated on EVERY successful download: `[]` is the answer for a document that used
            # nothing unmodelled, and a missing key is not an answer at all.
            "unknown_block_types": list(getattr(parser, "unknown_block_types", None) or []),
        })

    except click.ClickException:
        # Already an operator-facing failure carrying a nonzero exit; let it
        # propagate to click unchanged rather than re-wrapping via _report_error.
        raise
    except LarkConfigError:
        # A DELIBERATE refusal — a url this download cannot read, an unsupported document
        # type — whose message is already written for the person reading it. It must NOT reach
        # `_report_error`: that function's default branch hands the exception to `check_err`,
        # which logs "Report the following if it is a bug" and re-raises, so a well-worded
        # refusal arrived as a traceback labelled a possible bug. Re-raised untouched, which
        # serves both callers: the CLI boundary (`cli._RefusalUniformCommand`) prints it as one
        # `Error: …` line, and a LIBRARY caller still catches the typed class it expects rather
        # than a click exception.
        raise
    except Exception as e:
        _report_error(e, env_file=env_file)
