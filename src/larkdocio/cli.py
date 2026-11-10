import json
import os
import pathlib
import sys
import logging
import click

from larkdocio import __version__ as VERSION

# B3 (LD-017): the IPv4 pin lives in the shared core (``larkdocio.common``, moved
# there from ``larkdocio.auth`` by LD-061) and is applied by ``init_env`` *after*
# the ``.env`` is loaded — so ``LARK_DISABLE_IPV4_PIN`` set in a ``.env`` is
# honored — instead of at import time here. Merely importing this module no longer
# mutates process-wide DNS. Re-exported for backward compatibility with any caller
# that imported it from ``larkdocio.cli``.
from larkdocio.common import init_env, pin_socket_to_ipv4  # noqa: F401

from lark_oapi.core.exception import ObtainAccessTokenException

from larkdocio.common.auth import (
    WRITE_ENV,
    resolved_read_env,
    token_mint_refusal,
    token_mint_refusal_lines,
)
from larkdocio.common.reporting import ISSUES_URL
from larkdocio.common.transport import (
    is_credential_rejection,
    token_mint_credential_env,
)
from larkdocio.errors import LarkAPIError, LarkConfigError
from larkdocio.guide import guide as packaged_guide
from larkdocio.mermaid import flowchart as compile_flowchart
from larkdocio.mermaid import sequence as compile_sequence
from larkdocio.drive.folder_cmd import handle_folder_command
from larkdocio.read.config_cmd import handle_config_command
from larkdocio.read.download import handle_download_command
from larkdocio import roundtrip as roundtrip_flow
from larkdocio.roundtrip import COMMAND_NAME as ROUNDTRIP_COMMAND
from larkdocio.roundtrip import PHASES as ROUNDTRIP_PHASES
from larkdocio.roundtrip import PHASE_PULL, PHASE_PUSH
# PRIVATE and projected on purpose (LD-561): the push line states the guard's availability in
# the roundtrip surface's own words, authored once there rather than retyped here.
from larkdocio.roundtrip import _CONCURRENCY_GUARD_LABEL

#: The two diagram kinds this command line compiles, each mapped to its compiler. The keys are
#: the vocabulary a spec's ``"kind"`` may spell and the flags ``--flowchart`` / ``--sequence``
#: state; nothing outside this map is compiled, and nothing in it is ever *inferred*.
MERMAID_COMPILERS = {"flowchart": compile_flowchart, "sequence": compile_sequence}


def deep_read_options(command):
    """Attach the three opt-in deep-read flags to a read command — **one grammar, one text**.

    ``download`` carried these three and ``folder`` carried none, so a folder walk returned
    every embedded sheet and Base as a placeholder with no way to say yes (LD-384). They are
    applied here as one shared decorator rather than copied onto the second verb, because two
    hand-kept copies is exactly how ``--deep-read-sheets`` on one command comes to mean
    something slightly different from ``--deep-read-sheets`` on the other: same spelling, same
    semantics, same default (OFF), same sentence explaining it, on every command that reads a
    document. The wording says *read* rather than *download* for the same reason — one
    explanation that is true on both verbs, not a second one authored per command.

    ``--fidelity-read-sheets`` rides along deliberately (LD-384 AC6): it is the third sibling of
    the same family, off by default, and leaving it behind would recreate on ``folder``
    precisely the gap this change closes on it. It governs **two** legs whose prerequisites
    differ (LD-385): the docx **embedded**-sheet leg, which needs ``--deep-read-sheets`` because
    without it there is no deep read to add fidelity to, and a folder's **standalone
    spreadsheet** child, which is read through the Sheets surface either way and so needs
    nothing but this flag. Until LD-385 that second leg was values-only with **no** flag that
    could change it, which made a workbook whose meaning is its cell colours — the cells
    themselves blank — read as an empty table with nothing said.
    """
    for option in reversed((
        click.option(
            "--deep-read-sheets",
            "deep_read_sheets",
            is_flag=True,
            default=False,
            help=(
                "Opt in to deep-reading embedded sheets (block type 30) into inline "
                "Markdown tables. Off by default: embedded sheets stay a traceable "
                "placeholder and NO Sheets API calls are made. Enabling adds live Sheets "
                "reads (the referenced tab only); a read that fails degrades to the "
                "placeholder and never fails the read."
            ),
        ),
        click.option(
            "--fidelity-read-sheets",
            "fidelity_read_sheets",
            is_flag=True,
            default=False,
            help=(
                "Opt in to reading a sheet's whole-cell (format-level) bold/italic "
                "AND its per-cell BACKGROUND FILLS — the style set on the CELL, which the "
                "values API does not carry. Bold/italic render as Markdown emphasis; a fill "
                "has no Markdown equivalent, so each tab's fills are disclosed in a note "
                "above its table, as the ARGB the export carries against the cells carrying "
                "it — which is what makes a colour-encoded sheet (a schedule drawn in cell "
                "colours) readable instead of silently empty. Run-level emphasis (bold/italic on a text "
                "run inside a cell) comes through the values API and is ALREADY rendered "
                "without this flag, so on a sheet whose emphasis is run-level this flag "
                "correctly changes nothing: expected, not broken. It governs TWO legs: a "
                "docx EMBEDDED sheet, which also needs --deep-read-sheets, and a folder's "
                "STANDALONE SPREADSHEET child, which needs only this flag. "
                "Off by default: NO xlsx export is issued and cells render values-only. "
                "Enabling adds a READ-creds xlsx export of the spreadsheet (a few extra "
                "seconds); an export that fails degrades to the values-only table, says per "
                "tab that its fills could not be read, and never fails the read."
            ),
        ),
        click.option(
            "--deep-read-bases",
            "deep_read_bases",
            is_flag=True,
            default=False,
            help=(
                "Opt in to deep-reading a Base embedded in the document (both embed block "
                "types) into inline Markdown tables — the command-line route the Base twin of "
                "--deep-read-sheets previously lacked. Off by default: NO Base API calls are "
                "made and the reader emits exactly the placeholder it always has. Enabling adds "
                "live Base reads (the referenced table only) on the READ credentials; every "
                "failure — a stale token, a missing scope, an API error — degrades to that same "
                "placeholder, so a read never fails because a Base could not be read."
            ),
        ),
    )):
        command = option(command)
    return command

def _configure_logging():
    """Configure the shared ``larkdocio`` logger for a CLI run.

    Runs at CLI **invocation** (the ``cli()`` group callback), not at import —
    so merely importing ``larkdocio.cli`` attaches no handler to the ``larkdocio``
    logger that every library module logs through. Reads ``LOG_LEVEL`` at call
    time (INFO shows plain messages; DEBUG adds a ``[larkdocio]`` prefix).

    Idempotent: if a ``StreamHandler`` is already attached (repeated invocation
    in one process), it does nothing — matching the historical once-per-process
    guarantee that import-time configuration provided.

    **The handler writes to STDERR, and that is load-bearing.** It wrote to ``sys.stdout``
    until the ``mermaid`` subcommand arrived, and ``mermaid``'s stdout **is** its product:
    the compiled diagram source, meant to be redirected straight into a ``.mmd`` file. The
    two advisory dialect rules warn and compile anyway (diagram size, a wide horizontal
    layout), so a warning on stdout would land *inside* the emitted source and produce a file
    that is not valid Mermaid — a corrupt artifact rather than an error, which is the failure
    shape that is hardest to notice. The rule this settles for the whole command line:
    **stdout carries a command's OUTPUT, stderr carries everything said ABOUT the run.** The
    observable consequence is that ``download``'s progress lines now arrive on stderr; a
    caller who was reading them off stdout reads them off stderr instead (``2>&1`` restores
    the old single-stream view), and nothing about what ``download`` writes to disk changed.
    """
    logger = logging.getLogger("larkdocio")
    if any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        return
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    if log_level == "DEBUG":
        handler.setFormatter(logging.Formatter("[larkdocio] %(levelname)s: %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, log_level, logging.INFO))

#: The tail an ``OSError`` refusal carries (LD-658 AC4). An OSError reaching the command line is
#: ambiguous by nature — the caller's path, their filesystem, or a defect here — and this seam
#: cannot tell which. So it says so, rather than picking one and sounding certain, and it names
#: the one thing that recovers the diagnosis it just suppressed.
OSERROR_MAY_BE_OURS = (
    "That is an operating-system error: it may be about the path or the filesystem you gave, "
    "or it may be a fault in larkdocio. Re-run with LOG_LEVEL=DEBUG for the full traceback, "
    f"and report it at {ISSUES_URL} if it looks like ours."
)


class _RefusalUniformCommand(click.Command):
    """A subcommand whose deliberate refusals reach the terminal as one ``Error:`` line.

    ``LarkConfigError`` is this toolkit's **user-input / configuration** refusal, and its
    message is already written for the person reading it (*"that is a SPREADSHEET url, not a
    document url…"*). What a shell caller wants from one is a message and an exit status — not
    this library's call stack, and above all not the ``"Report the following if it is a bug"``
    banner the unknown-error path prints, which invites a bug report for a refusal that is
    working exactly as designed.

    **Why the conversion lives on the command class rather than inside each command.** It used
    to be a ``try/except`` written next to whichever command remembered it, so ``mermaid``
    printed a clean line for the class while ``download`` let the same class fall through to a
    traceback. A subcommand cannot forget a rule it does not implement: the group mints every
    command through this class, so a future ``@cli.command`` inherits the contract without
    writing anything and there is exactly one place the shape is decided.

    ``from None`` is load-bearing — it is what keeps the original traceback out of the
    terminal. Nothing else is caught here: an unexpected exception keeps its traceback and its
    bug-report banner, because that path exists for the class it was written for.

    **Widened at LD-658 AC4 to the two BUILTIN classes this library also refuses through, and
    the two are NOT treated alike.**

    * ``ValueError`` is a refusal class here **by stated contract** — :mod:`larkdocio.common.url`
      documents every unparseable url as *"a ``ValueError`` refusal, never a default"*, and its
      messages are written for the person reading them. It converts exactly like
      ``LarkConfigError``: verbatim, no tail. Before this, a mistyped download url printed the
      refusal and then ``====================``, the bug-report banner, and a ~45-line
      traceback — for a typo the caller made — while ``larkdocio folder <bad url>`` printed a
      bare traceback with **no refusal line at all**, because it had no handler of its own. That
      second case is the argument for the seam living on the command class: a verb cannot forget
      a rule it does not implement.
    * ``OSError`` is **not** a refusal contract anywhere in this library. It is a fact about the
      machine, about the path the caller gave — *or a fault of ours*, which is exactly what
      LD-659's filename-length overflow is. Converting it silently would bury an internal I/O
      bug in a bland one-liner, so this arm **discloses the ambiguity** and names the route back
      to the traceback (:data:`OSERROR_MAY_BE_OURS`). The alternative — leaving ``OSError``
      uncaught — was rejected because the case it hits most often is a real user with a long
      CJK document title, who is owed a sentence rather than a stack.

    **A token-mint failure is handled here too, and now on BOTH of this library's two
    token-mint paths (LD-672).** The claim here has been wrong in both directions: *"on EVERY
    verb"* (LD-658 round 2) was measured false, and the narrowing that replaced it became
    understated the moment the second path was covered. It is no longer maintained by hand —
    see the two lists below.

    **The two paths, and why one arm could never cover both.** ``lark_oapi``'s ``TokenManager``
    raises the SDK's own ``ObtainAccessTokenException``; this library's
    :func:`larkdocio.common.transport.fetch_tenant_access_token` raises its own
    ``LarkAPIError``. They share this seam and not an exception class, so there are two arms
    below, and the second one cannot key on the class alone — ``LarkAPIError`` is also a missing
    document and a rejected parameter. It asks
    :func:`larkdocio.common.transport.is_credential_rejection`, which is true only for an error
    the **mint itself** raised **carrying a Lark code** — the whole reasoning, including why a
    hand-listed set of rejection codes was rejected, is written at that function.

    **THE CLAIM BELOW IS THE ONE PLACE ANY SURFACE IS NAMED, AND A TEST MEASURES IT.** The two
    lists are held set-equal to an execution probe that runs every surface's real client against
    both mint paths broken at their own seams and asks **this seam** whether the escaping error
    is answered with credential guidance (a guard in the source repository, ``tests/token_mint_probe.py``
    + ``tests/test_cli_refusal_uniformity.py``). Note what the probe measures **now**: the
    OUTCOME, not the exception class — measuring the class is what let the narrowed claim read
    as a verdict on a surface when it was a fact about a mint. They are written in a fixed shape
    — every label backticked, one sentence each — because that shape is what the guard parses.
    **Do not hand-edit them to match a belief; run the probe.** The consumer-facing sentence in
    ``RELEASE_NOTES.md`` deliberately names **no** surface at all and states the rule instead,
    because a dated release section becomes immutable at the cut and cannot be corrected when
    this set changes.

    Covered: `read`, `drive`, `write`, `base`, `sheets`, `comments`, `contacts` — every family
    that mints a tenant token, on either path. Reached as every verb this command line has (the
    reader, the folder walk, and ``roundtrip``'s **pull** *and* **push** phases) plus the
    library-only surfaces. Which helper builds a family's client is **not** what decides this
    any more, and naming one here is what made the previous claim's *reason* wrong for the
    reader — it builds through :func:`larkdocio.common.sdk_client.build_sdk_client`, not
    ``resolve_sdk_client`` — while its answer happened to be right.

    Not covered: none — both mint paths answer. **The behaviour this closed was pre-existing,
    not a regression:** ``larkdocio folder`` on a rejected pair printed **zero bytes** and
    escaped ``LarkAPIError('tenant_access_token error: …')`` on every release up to this one.

    The **guidance** is not written here: it is authored once in
    :func:`larkdocio.common.auth.token_mint_refusal_lines`, and the two arms differ from the
    reader's own arm in exactly one respect — **which credential pair they can name.**

    * The **SDK arm** passes **both** pairs and the text says it is one of them: the SDK's
      exception carries no app id, this seam is reached by verbs that write as well as read, and
      a subcommand → pair map would be a second, wrong copy of the credential doctrine.
    * The **raw-HTTP arm** usually knows, and says the ONE pair: every raw-HTTP client declares
      the pair it mints on (:meth:`larkdocio.common.transport.RawHttpClient._credential_pair`) and
      the failure carries it, so a rejected credential on ``roundtrip``'s **push** phase names
      ``LARK_WRITE_APP_*`` rather than the pair its **pull** phase used. Where the pair is
      genuinely unknown — a bare :func:`fetch_tenant_access_token` call outside a client — it
      falls back to the both-pairs wording rather than guessing.

    ``download`` never reaches either arm — its own arm converts first, and keeps the narrower
    answer.
    """

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except LarkConfigError as refusal:
            raise click.ClickException(str(refusal)) from None
        except ValueError as refusal:
            raise click.ClickException(str(refusal)) from None
        except OSError as failure:
            raise click.ClickException(f"{failure}. {OSERROR_MAY_BE_OURS}") from None
        except ObtainAccessTokenException as rejected:
            # Path A — the SDK minted. Its exception carries no app id, so both pairs.
            raise self._credential_refusal(
                ctx, rejected, (resolved_read_env(), WRITE_ENV)) from None
        except LarkAPIError as failed:
            # Path B — this library's own raw-HTTP mint (LD-672). NOT every LarkAPIError: a
            # missing document and a rejected parameter arrive as this class too and keep the
            # behaviour they have always had, traceback and all.
            if not is_credential_rejection(failed):
                raise
            pair = token_mint_credential_env(failed)
            raise self._credential_refusal(
                ctx, failed, (pair,) if pair else (resolved_read_env(), WRITE_ENV)) from None

    def _credential_refusal(self, ctx, rejected, pairs):
        """Lark's own words, then the authored guidance, then the one-line refusal to exit on.

        Shared by both arms so the two mint paths cannot drift into two answers — which is the
        defect one level up from the one LD-672 fixed, and the reason the guidance itself lives
        in :func:`larkdocio.common.auth.token_mint_refusal_lines` rather than here.
        """
        log = logging.getLogger("larkdocio")
        log.error(str(rejected))
        for line in token_mint_refusal_lines(
                pairs, ctx.obj.get("ENV_FILE") if ctx.obj else None):
            log.error(line)
        # The verb click itself parsed, so every subcommand names itself correctly and a
        # future one needs no entry anywhere (LD-658 fix round: this was the literal
        # "Download failed: …", so `roundtrip pull` misnamed itself).
        return click.ClickException(
            token_mint_refusal(f"`larkdocio {ctx.info_name or self.name}`"))


def _reconfigure_output_encoding():
    """Make this process's stdout/stderr able to carry the text this CLI prints (LD-658 AC5).

    **The defect, measured.** Nothing in the package set an output encoding, so Python used the
    locale's. On Windows a **redirected** stdout gets the active code page, and the packaged
    guide, the capability tables and the refusal texts all carry characters no legacy code page
    can encode (em dashes, arrows, ``§``, the 📎 marker). Executed across four code pages:
    ``larkdocio guide`` exited **1** having written **0 bytes** with a ``UnicodeEncodeError`` on
    cp1252, cp936, cp932 *and* cp437, and the root ``--help`` failed on cp932 and cp437. The
    ``guide`` command's own shipped help advertises the recipe that fails — *"piping it to a file
    or into another program is exactly what it is for."*

    A Windows console is fine (it writes UTF-16); this is the redirect, which is the case a
    consumer automates. Nothing changes on a UTF-8 host: the encoding is already what this sets.

    **Why ``errors="backslashreplace"`` and not ``strict``.** The point of the fix is that the
    documentary commands cannot fail on their own output. If some future stream still cannot
    carry a character, a visible escape in the middle of a guide is recoverable; **zero bytes and
    exit 1 is not**. And not ``replace``: ``\\u2014`` says which character was lost, ``?`` does not.

    **Why it runs in ``main()`` rather than the group callback.** ``--help`` is answered by click
    during parsing, before any callback runs — and the root ``--help`` is one of the two surfaces
    measured broken. A stream that cannot be reconfigured (a ``StringIO``, an already-detached
    stream) is left exactly as it was: this is a best-effort widening, never a reason for the
    command line to fail before it starts.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            # Not a reconfigurable text stream. Leave it alone — see the docstring.
            pass


class _RefusalUniformGroup(click.Group):
    """The command line's group — every subcommand it mints is a :class:`_RefusalUniformCommand`."""

    command_class = _RefusalUniformCommand

    def main(self, *args, **kwargs):
        # Before click parses anything, so `--help` is covered too (LD-658 AC5).
        _reconfigure_output_encoding()
        return super().main(*args, **kwargs)


@click.group(invoke_without_command=True, cls=_RefusalUniformGroup)
@click.version_option(version=VERSION, prog_name="larkdocio")
@click.option("--config", "config_file", default="", help="Path to config file", type=click.Path(exists=False))
@click.option("--env-file", "env_file", default="", help="Path to .env file", type=click.Path(exists=False))
@click.pass_context
def cli(ctx, config_file, env_file):
    """Lark (Feishu) documents, spreadsheets and bases — download, convert, inspect.

    The LIBRARY reads and writes: a docx download-to-Markdown, a comments read (comment create
    and remove ride the docx writeback plan), a Sheets read, a Base (bitable) read, a Drive folder read, a name- or email-to-open_id lookup, Markdown
    authoring, and plan-gated docx / Sheets / Base writeback. Drive writes too, and they are
    the ones that are NOT plan-gated: a document's named versions, who has access to it,
    one file uploaded into a folder, and one folder created under a parent (the whole organize
    rung on offer — no move, rename, copy or folder delete, and the same name twice makes a
    second folder). They are direct calls rather than a plan you approve first, AND WHAT
    VERIFIES ONE DIFFERS PER LEG — read it off the leg, not off this sentence. Only the ACCESS
    leg declares `read-back-is-the-verdict`: each grant / update / revoke is followed by an
    independent member read, and a call that was accepted and did not store reports
    `stored=False`. The VERSIONS leg reads the head revision BEFORE its write, not after. The
    FOLDER-create leg is exactly one call and reads nothing back — you get Lark's own answer.
    The FILES leg verifies by a byte round trip: the upload is downloaded again and compared.
    The census that settles it is
    `capabilities(full=True)["surfaces"][<surface>]["safety_contracts"]`. On a Base that writeback now covers the SCHEMA as well as
    the records: fields across a published allow-list, tables, and views carrying a persistent
    filter. Every delete is shown first as a loss preview spanning the whole Base, and applies
    only against a consent token minted from that preview's own plan. Hidden columns are
    settable; view grouping and a view-level sort are not offered, and a form view is refused
    by policy. A Base
    attachment also has a file leg: the library uploads bytes, hands back the token the cell is
    written from, and downloads the same token so the round trip can be checked by comparing
    digests. It is out of band — a read still renders file names only, the signed links a cell
    reads back never render, and an upload cannot be undone.

    EXACTLY ONE COMMAND HERE WRITES TO LARK, and it is `roundtrip push --apply`. Everything
    else on this command line reads: `download`, `folder`, `guide`, `config` and `mermaid`
    change nothing in Lark, and that is deliberate rather than incidental — a download must
    never be able to mutate the document it is reading, which is why the reading verbs carry
    no write flag and never will. The one writing verb is PLAN-GATED and separate: it pulls a
    document to a Markdown file, you edit that file, and it pushes the edit back only through
    a plan it built and printed first, refusing rather than guessing when the document moved
    underneath it. It is also the only place this command line consults the WRITE credential
    pair. Everything ELSE a consumer can write — Sheets, Base, the Drive legs — is a library
    call and has no flag here: for the docx, Sheets and Base content and schema writes a plan
    you approve first; a direct call, with no plan, for their media legs (put_image_in_document
    and put_file_in_document; put_image_in_sheet, put_float_image_in_sheet and
    remove_float_image_from_sheet; the Base attachment upload, BaseMediaClient.upload) and for
    their whole-object lifecycle calls (create_document and delete_document,
    create_spreadsheet and delete_spreadsheet, and for a Base delete_base only, since a Base is
    created through the plan-gated schema writes) and the documented direct cell write,
    put_values on SheetsWriteClient (its other public value writes, append_values,
    prepend_values and batch_update_values, are direct calls with no plan as well when
    you call them yourself); and for the Drive write legs a direct call
    — with the
    verification stated PER LEG (an independent
    read-back on the access leg; a pre-write revision read on the versions leg; a byte round
    trip on the files leg; one call and no read-back on folder create), never as one blanket
    promise over all four.
    The STANDALONE Base surface is a
    LIBRARY call too, read and write both: neither has a subcommand of its own and neither has
    a flag, so reach the read with `larkdocio.base.read_base_markdown(url)`. A Base EMBEDDED in
    a document is a different thing and IS reachable here, as a read: `download
    --deep-read-bases` and `folder --deep-read-bases` inline it as Markdown tables.

    \b
    Surfaces in this install:
      docx-read, docx-comments-read, contacts-read, drive-read,
      sheets-read, sheets-embedded-deep-read,
      base-read, base-comments-read, base-embedded-deep-read,
      docx-write, sheets-write, base-write, base-schema-write,
      drive-versions-write, drive-access-write, drive-files-write,
      drive-folders-write

    Those are the ids `larkdocio.capabilities()` reports, each carrying its operations,
    credentials, scopes, opt-in flags and safety contracts. `larkdocio guide` prints the
    packaged consumer guide — recipes, the capability matrix, the credential split and the
    permissions table — straight from the install, with no network and no source tree.
    """
    _configure_logging()
    ctx.ensure_object(dict)
    ctx.obj['CONFIG_FILE'] = config_file
    ctx.obj['ENV_FILE'] = env_file
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@cli.command(name="config", help=(
    "Read config file or set field(s) if provided. Credentials are written to the .env as "
    "LARK_READ_APP_ID / LARK_READ_APP_SECRET (a .env already using the legacy LARK_APP_ID / "
    "LARK_APP_SECRET is updated in place, never re-keyed). Write credentials are a separate "
    "pair (one app or two; two recommended) and are never written here."))
@click.option("--appId", "app_id", default="", help="Set app id for the OPEN API")
@click.option("--appSecret", "app_secret", default="", help="Set app secret for the OPEN API")
@click.pass_context
def config(ctx, app_id: str, app_secret: str):
    handle_config_command(app_id, app_secret, ctx.obj.get('CONFIG_FILE'), ctx.obj.get('ENV_FILE'))

@cli.command(name="guide", help=(
    "Print the packaged consumer guide's SECTION INDEX to stdout — the same text "
    "larkdocio.guide() returns. Every section of the guide is named after the failure it "
    "cures, so the index is what you read first: it names each section, its slug, and the "
    "call that fetches it. It is read out of the installed package, so it needs no network, "
    "no credentials and no source tree. Pass --section to print one part of the guide "
    "(recipes that run as pasted, the capability matrix, the READ / WRITE credential split, "
    "the generated permissions table), or --full to print the whole document, which runs to "
    "hundreds of KB as one string. Whatever is printed, the bytes are the document's own — no "
    "pager, no colorization, no reflow and no added trailing newline — so piping it to a file "
    "or into another program is exactly what it is for."))
@click.option("--section", default=None, help=(
    "Print one section instead of the index. Name it either by the heading exactly as it "
    "appears or by the slug derived from it (both case-insensitive); what comes back is that "
    "section's own bytes, and a top-level name includes the subsections nested under it. Omit "
    "this option and --full to print the index of what can be named. An unrecognised name "
    "prints nothing and refuses with a message listing every section there is."))
@click.option("--full", is_flag=True, default=False, help=(
    "Print the whole guide instead of the index — every section, byte for byte as the wheel "
    "carries it, hundreds of KB as one string. This is what this command printed before the "
    "index became the default. Cannot be combined with --section."))
def guide_command(section, full):
    """Write the packaged guide's index — or one section, or all of it — to stdout, unmodified.

    ``nl=False`` is load-bearing: the guide's own bytes are the contract (a consumer diffing
    ``larkdocio guide`` against ``larkdocio.guide()`` must see nothing), so this must not add
    the newline ``click.echo`` appends by default.

    Both flags are **pass-throughs**. ``guide()`` already owns the naming rule, the boundary
    rule, what the default answer is and every refusal, and a second definition of any of them
    here would rot against the first — so this function contributes no logic at all, not even
    the ``--section``/``--full`` exclusion, which is the API's own ``ValueError``. What it does
    contribute is the surfacing: a refusal is raised as a ``ClickException`` so it reaches
    stderr with a non-zero status and **stdout stays empty**, which is what keeps
    ``larkdocio guide --section typo > out.md`` from leaving a half-written file.
    """
    try:
        text = packaged_guide(section=section, full=full)
    except ValueError as refusal:
        raise click.ClickException(str(refusal)) from None
    click.echo(text, nl=False)

def _read_mermaid_spec(spec_path: str) -> dict:
    """Return the diagram spec ``spec_path`` names, or refuse with a message a shell can use.

    ``-`` reads stdin, which is the pipeline form. Three refusal classes live here and none of
    them may reach the terminal as a traceback: a spec that cannot be read, one that is not
    JSON (named **with its parse position**, because "invalid JSON" tells the author nothing
    about where to look), and one that is valid JSON but not an object — a list of nodes is a
    plausible mistake, and compiling it would raise from inside the compiler about a key that
    was never the problem.
    """
    if spec_path == "-":
        raw, origin = sys.stdin.read(), "the spec on stdin"
    else:
        origin = f"the spec file {spec_path!r}"
        try:
            raw = pathlib.Path(spec_path).read_text(encoding="utf-8")
        except OSError as unreadable:
            raise click.ClickException(
                f"{origin} could not be read: {unreadable.strerror or unreadable}"
            ) from None
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as malformed:
        raise click.ClickException(
            f"{origin} is not valid JSON: {malformed.msg} at line {malformed.lineno} "
            f"column {malformed.colno} (char {malformed.pos})"
        ) from None
    if not isinstance(spec, dict):
        raise click.ClickException(
            f"{origin} is a JSON {type(spec).__name__}, and a diagram spec must be a JSON "
            f"object — the keys the two compilers read are documented in `larkdocio guide`"
        )
    return spec


def _resolve_mermaid_kind(spec: dict, as_flowchart: bool, as_sequence: bool) -> str:
    """Return the diagram kind, refusing anything short of one unambiguous statement of it.

    **The kind is stated, never guessed.** A spec carrying ``nodes``/``edges`` *looks* like a
    flowchart and one carrying ``participants``/``messages`` *looks* like a sequence diagram,
    and reading the answer off that resemblance is guessing: a spec that carries both, or
    neither, has no right answer, and a spec whose author meant the other one gets a diagram
    that says something else with nothing to inspect. So the kind comes from a **declaration**
    — the ``--flowchart`` / ``--sequence`` flag, or the spec's own ``"kind"`` key — and which
    keys the spec happens to contain is never consulted. Two declarations that disagree refuse
    rather than resolve, because picking a winner is the same guess wearing a tie.

    Both sources exist on purpose: a shell-driven caller wants the flag (it is what the
    pipeline reads), and a spec file that travels between tools should be able to carry its own
    kind so a pipeline cannot mis-route it. Requiring them to agree is what keeps the second
    from silently overriding the first.

    The ``"kind"`` key is consumed **here** and is not a dialect widening: the compilers never
    see it as a spec key, and both already ignore keys they do not read.
    """
    kinds = ", ".join(MERMAID_COMPILERS)
    if as_flowchart and as_sequence:
        raise click.ClickException(
            "--flowchart and --sequence disagree about the diagram kind, and exactly one kind "
            "can be compiled — pass one of them, not both"
        )
    stated = "flowchart" if as_flowchart else "sequence" if as_sequence else ""

    if "kind" in spec:
        declared = str(spec.get("kind") or "").strip().lower()
        if declared not in MERMAID_COMPILERS:
            raise click.ClickException(
                f"the spec declares the diagram kind {spec.get('kind')!r}, which this command "
                f"does not compile — it compiles exactly {len(MERMAID_COMPILERS)}: {kinds}"
            )
        if stated and stated != declared:
            raise click.ClickException(
                f"the spec declares the diagram kind {declared!r} and the invocation says "
                f"--{stated}: they disagree, and choosing one of them would compile a diagram "
                f"nobody asked for — make them agree, or drop one"
            )
        return declared

    if stated:
        return stated
    raise click.ClickException(
        f"the diagram kind is not stated, and it is never guessed — pass --flowchart or "
        f"--sequence, or give the spec a \"kind\" key spelling one of: {kinds}"
    )


@cli.command(
    name="mermaid",
    short_help="Compile a diagram spec (JSON) to Mermaid source.",
    help=(
        "Compile a structured diagram spec to Mermaid source: a spec in, Lark-safe Mermaid "
        "source out.\n"
        "\n"
        "SPEC is the path to a JSON file, or `-` (the default) to read the spec from stdin. "
        "The compiled source goes to stdout, or into a file of your choosing with -o.\n"
        "\n"
        "This is PURE: no credentials, no network, no document is touched, and nothing leaves "
        "the machine. It compiles text and stops — it never writes a diagram into a Lark "
        "document. Putting a compiled diagram into a document is a library call whose plan you "
        "approve first; `larkdocio guide` has that recipe.\n"
        "\n"
        "The diagram kind is stated, never guessed: pass --flowchart or --sequence, or give "
        "the spec a \"kind\" key spelling one of them. Stating neither refuses, and a flag that "
        "contradicts the key refuses instead of picking a winner. Which keys a spec happens to "
        "carry is never consulted.\n"
        "\n"
        "A spec the renderer could not draw REFUSES rather than being silently corrected: the "
        "message names the construct and its value, goes to stderr, exits non-zero, and leaves "
        "stdout empty with no output written. Advisory warnings about a valid diagram (its "
        "size, a wide horizontal layout) go to stderr too, so stdout carries only diagram "
        "source and redirecting it is safe."
    ),
    epilog=(
        "Examples:\n"
        "\n"
        "\b\n"
        "larkdocio mermaid --flowchart spec.json > diagram.mmd\n"
        "cat spec.json | larkdocio mermaid --sequence -"
    ),
)
@click.argument("spec_path", required=False, default="-", metavar="[SPEC]",
                type=click.Path(exists=False))
@click.option("--flowchart", "as_flowchart", is_flag=True, default=False, help=(
    "State that the spec is a flowchart. Exactly one kind must be stated — with this flag, "
    "with --sequence, or by the spec's own \"kind\" key."))
@click.option("--sequence", "as_sequence", is_flag=True, default=False, help=(
    "State that the spec is a sequence diagram. Exactly one kind must be stated — with this "
    "flag, with --flowchart, or by the spec's own \"kind\" key."))
@click.option("-o", "--output", "output_file", default="", type=click.Path(exists=False), help=(
    "Write the Mermaid source into this FILE instead of stdout (a file, unlike the -o of "
    "`larkdocio download`, which is a root that output is written under). Nothing is written "
    "when the spec is refused, so a refusal never leaves a half-finished diagram behind."))
def mermaid_command(spec_path: str, as_flowchart: bool, as_sequence: bool, output_file: str):
    """Compile a spec and emit the source — the whole command, in the order that matters.

    Read, then resolve the kind, then compile, and only **then** write anything anywhere. The
    ordering is the no-partial-output guarantee: every refusal class raises before a single
    byte reaches stdout or the output file, so a shell redirect cannot be left holding a
    truncated ``.mmd`` and an existing file is untouched.
    """
    spec = _read_mermaid_spec(spec_path)
    kind = _resolve_mermaid_kind(spec, as_flowchart, as_sequence)
    # A compiler refusal is a `LarkConfigError` and reaches the terminal as one `Error:` line
    # carrying its own detail verbatim — see `_RefusalUniformCommand`, which does that for
    # EVERY subcommand. This command used to convert the class itself; the local `try/except`
    # is gone because a rule each command re-implements is a rule the next one ships without.
    source = MERMAID_COMPILERS[kind](spec)
    if not output_file:
        click.echo(source, nl=False)
        return
    try:
        pathlib.Path(output_file).write_text(source, encoding="utf-8")
    except OSError as unwritable:
        raise click.ClickException(
            f"the source compiled, but the output file {output_file!r} could not be written: "
            f"{unwritable.strerror or unwritable}"
        ) from None


@cli.command(
    name="download",
    help="Download lark document to markdown file",
    epilog=(
        "Examples:\n"
        "\n"
        "\b\n"
        'larkdocio download "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./out/\n'
        "\n"
        # A no-rewrap block (\b): the generated filename SHAPE must reach the reader
        # unbroken, and click's epilog wraps at eighty columns regardless of terminal
        # width — which splits `[YYYY-MM-DD_HHMM]_<title>.md` on a hyphen.
        "\b\n"
        "-o is that directory. The file in it is named [YYYY-MM-DD_HHMM]_<title>.md;\n"
        "that stamp is UTC by default, never the local clock, so one document downloaded\n"
        "at one moment lands under the same name on every machine. Pass --local-time to\n"
        "stamp in the machine's own zone instead (see its help for the trade-off). The\n"
        "switch governing the name is title_as_filename — set it false for a stable\n"
        "<document token>.md with no stamp. A title too long for the filesystem is cut,\n"
        "and a cut title is a prefix other documents share, so the document's own token\n"
        "joins the name then — [stamp]_<cut title>_<token>.md — which is what stops two\n"
        "documents overwriting one file. Short titles are untouched. Read it in\n"
        "`larkdocio guide`."
    ),
)
@click.argument("url", required=True)
@click.option("-o", "--output", "output_dir", default="./", help=(
    "A DIRECTORY, always — never a filename: the root the output is written UNDER (default "
    "./), not the file to write. The file lands here exactly, flat: nothing in the document "
    "moves it. Pass --route to place it under a subpath you name. Full rule: "
    "`larkdocio guide`."))
@click.option("--allowHost", "allow_host", default="", help="Additional allow host for the OPEN API")
@click.option("--dump", is_flag=True, default=False, help="Dump json response of the OPEN API")
@deep_read_options
@click.option(
    "--local-time",
    "local_time",
    is_flag=True,
    default=False,
    help=(
        "Stamp the output filename in the machine's LOCAL clock instead of the default "
        "UTC. The shape [YYYY-MM-DD_HHMM]_<title>.md is unchanged — only the digits "
        "move; no zone suffix is added. THE TRADE-OFF, opt in knowing it: the same "
        "document downloaded at the same instant on two machines in different zones "
        "then lands under DIFFERENT names, so a ledger keyed on the filename becomes "
        "machine-dependent. UTC (the default) keeps that name identical on every "
        "machine. Governs the stamp only; --dump records which basis a run used."
    ),
)
@click.option(
    "--route",
    "route",
    default=None,
    metavar="SUBPATH",
    help=(
        "Place the output under this caller-supplied SUBPATH beneath -o (e.g. "
        "area/section/topic). THE ONLY thing that ever moves output off -o: you supply "
        "the path and larkdocio infers nothing from the document — no body scan, no title "
        "or filename convention is read. Each segment is sanitised (spaces to underscores, "
        "OS-reserved characters stripped) but NOT lower-cased; an absolute path, a '..' "
        "segment, an empty segment, and a segment that stripping leaves nothing of (e.g. "
        "'***') are each refused, never normalised — it cannot escape -o, and no directory "
        "name is invented for you."
    ),
)
@click.pass_context
def download(ctx, url: str, output_dir: str, allow_host: str, dump: bool, deep_read_sheets: bool, fidelity_read_sheets: bool, deep_read_bases: bool, local_time: bool, route: str):
    handle_download_command(url, output_dir, allow_host, dump, ctx.obj.get('CONFIG_FILE'), ctx.obj.get('ENV_FILE'), deep_read_sheets=deep_read_sheets, fidelity_read_sheets=fidelity_read_sheets, deep_read_bases=deep_read_bases, local_time=local_time, route=route)

@cli.command(
    name="folder",
    short_help="Read a whole Drive folder to Markdown.",
    help=(
        "Read a whole Lark Drive FOLDER: hand it one folder URL and it enumerates the tree, "
        "reads every document inside — at any depth — and writes ONE Markdown document (a tree "
        "index, then each document under its own heading, then a list of what could not be "
        "read) into -o.\n"
        "\n"
        "This is the folder counterpart of `download`, and the two do not overlap: `download` "
        "takes ONE document URL and writes that one document plus its images, while `folder` "
        "takes a FOLDER URL and writes the whole tree as a single file. Hand a folder URL to "
        "`download` and it refuses and points you here; hand a document URL to `folder` and the "
        "URL validator refuses it as not a folder.\n"
        "\n"
        "It is READ-ONLY. It reads on the READ credentials, never writes to Lark, and never "
        "moves, uploads or deletes anything. A child it cannot read — a raw uploaded file, an "
        "unreadable document — is DISCLOSED by name in the output, never silently dropped, and "
        "never fails the rest of the walk. Reading the documents inside uses the same docx / "
        "Sheets / Base read surfaces the library already ships, each on its own scope."
    ),
    epilog=(
        "Examples:\n"
        "\n"
        "\b\n"
        'larkdocio --env-file .env folder "https://your-domain.larksuite.com/drive/folder/AbCdEfG" -o ./out/'
    ),
)
@click.argument("url", required=True)
@click.option("-o", "--output", "output_dir", default="./", help=(
    "A DIRECTORY, always — the root the one Markdown document is written UNDER (default ./), "
    "not the file to write. The file is named for the folder. The library itself writes no "
    "files for a folder read; this on-disk shape is the CLI's."))
@click.option(
    "--dump",
    "dump",
    is_flag=True,
    default=False,
    help=(
        "ALSO write a machine-readable child manifest — <folder token>.json, beside the "
        "Markdown in -o, the same naming and placement `download --dump` uses. One row per "
        "child carrying its TITLE, TOKEN, TYPE and REVISION, plus the listing's own "
        "created_time / modified_time / owner_id / url, the read-or-disclosed outcome, and the "
        "walk's truncations, cycles and refusals so a truncated walk cannot read as a complete "
        "folder. This is the input a change-detection ledger wants, and the flag is purely "
        "ADDITIVE: the Markdown is byte-identical with or without it. A revision is reported "
        "where the read already carried one (a document's revision_id, a spreadsheet's "
        "revision) and is marked UNAVAILABLE WITH THE REASON everywhere else — never "
        "fabricated, never inferred, never silently omitted; no extra API call is made to "
        "obtain one. Every row carries modified_time regardless, which is the free change "
        "anchor the listing itself supplies."
    ),
)
@click.option(
    "--assets",
    "assets",
    is_flag=True,
    default=False,
    help=(
        "ALSO fetch every document's IMAGES and its flowchart / mindmap (whiteboard) PNGs, "
        "into ONE SHARED POOL beside the Markdown: <-o>/static/<asset token>.<ext> — the same "
        "directory name and the same token-derived filenames `download` writes for a single "
        "document, and each reference in the Markdown is rewritten to that local relative "
        "link. COLLISIONS ARE IMPOSSIBLE BY CONSTRUCTION because the filename IS the Lark "
        "asset token, which is globally unique; the same token in two documents is the SAME "
        "asset, so it is fetched ONCE and every reference relinked. This is the flag a "
        "MINDMAP-ONLY document needs: without it such a document comes back as a bare token "
        "and nothing else. OFF BY DEFAULT — `download` fetches a single document's assets "
        "unconditionally (its only switches are config, not flags), but a whole folder's "
        "binaries are a different cost class and nobody should pay it by surprise; off, NO "
        "asset call is made, no pool directory is created, and the Markdown is byte-identical "
        "to a walk without it. An asset that fails is DISCLOSED — Lark's own code and msg, "
        "naming the document and the asset, in the log and in an `## Assets not fetched` "
        "section — and never fails the walk. Attachments (uploaded file blocks) are NOT "
        "included: they are `download`'s own separate config opt-in."
    ),
)
@deep_read_options
@click.pass_context
def folder(ctx, url: str, output_dir: str, dump: bool, assets: bool,
           deep_read_sheets: bool, fidelity_read_sheets: bool, deep_read_bases: bool):
    handle_folder_command(url, output_dir, ctx.obj.get('ENV_FILE'), dump=dump,
                          deep_read_sheets=deep_read_sheets,
                          fidelity_read_sheets=fidelity_read_sheets,
                          deep_read_bases=deep_read_bases,
                          assets=assets)

@cli.command(
    name=ROUNDTRIP_COMMAND,
    short_help="Edit a document as a Markdown FILE: pull it, edit it, push it back.",
    help=(
        "Edit a Lark document as a Markdown FILE on your disk. THIS IS THE ONE SUBCOMMAND "
        "THAT WRITES TO LARK, and it writes only under `push --apply`.\n"
        "\n"
        "PHASE is `pull` or `push`, and they are two invocations of this one verb because "
        "your edit happens BETWEEN them — in another process, or tomorrow:\n"
        "\n"
        "\b\n"
        "  1. larkdocio roundtrip pull \"<url>\" -o ./edit/\n"
        "     ...you (or your agent) edit ./edit/document.md...\n"
        "  2. larkdocio roundtrip push -o ./edit/            # preview only, writes NOTHING\n"
        "  3. larkdocio roundtrip push -o ./edit/ --apply    # applies that plan, then verifies\n"
        "\n"
        "`pull` reads the document on the READ credentials and writes TWO files into -o. "
        "document.snapshot is OURS and immutable — the read, checksummed, carrying the "
        "revision and the tenant domain. document.md is YOURS and editable, and it is the "
        "file to edit: every block carries an identity marker comment, and keeping each "
        "marker where it is is what makes this an update instead of a re-authoring. Change "
        "the text under a marker; never move a marker onto another block's text. A block you "
        "edit is re-written from your Markdown as one run carrying the styling the block "
        "starts with, so a colour that differed elsewhere in the paragraph is flattened onto "
        "that, and bold, italics or a link inside it refuse the push rather than being "
        "flattened — to change a few words inside a block and keep the rest of it, use a "
        "sub-span edit from the library instead; `larkdocio guide` has that recipe.\n"
        "\n"
        "TEXT IS NOT THE ONLY THING AN EDIT CARRIES: flipping `- [ ]` to `- [x]` under a "
        "marker really moves the checkbox, through the same plan-gated route. Those two — "
        "the text and a todo's done bit — are what a roundtrip edit can move; anything else "
        "you change about a block is not expressible as a write. And an edit that compiles "
        "to a byte-identical write is REFUSED typed (`change-not-expressible`) rather than "
        "reported applied, so a green apply is never a receipt for nothing.\n"
        "\n"
        "`push` loads the snapshot, reconciles your edited document.md against it, and ALWAYS "
        "builds and prints the plan first. THERE IS NO FLAG THAT SKIPS THE PREVIEW: --apply "
        "means apply the plan you just previewed, and the write goes only through that plan. "
        "The plan carries the revision the snapshot recorded, which arms the whole-document "
        "compare-and-swap: if the document changed while your edit sat on disk the batch is "
        "REFUSED whole, with zero writes, and the fix is to pull again and re-apply your "
        "edit. A snapshot that carried no revision cannot arm it, and this says so loudly "
        "instead of writing as if it had.\n"
        "\n"
        "After a successful apply it RE-READS the document and verifies it by "
        "compose-equivalence — what the document now means, compared with what you authored "
        "— rather than by comparing two Markdown strings, which reports a false difference "
        "on every list. A block whose content is outside the authoring dialect is reported "
        "unverifiable BY NAME, never quietly counted as clean.\n"
        "\n"
        "CREDENTIALS: `pull` uses the READ pair (LARK_READ_APP_ID / LARK_READ_APP_SECRET). "
        "`push` is the FIRST AND ONLY place this command line consults the WRITE pair "
        "(LARK_WRITE_APP_ID / LARK_WRITE_APP_SECRET), and it also needs the READ pair for "
        "the read-back. The two pairs are separate credentials, resolved separately (they may name one app or two): neither "
        "is ever borrowed for the other, and a `push` with no WRITE pair refuses before it "
        "makes any call, naming both variables.\n"
        "\n"
        "Every refusal is typed, says what to do next, and names the guide section that "
        "covers the recovery — a stale or corrupted snapshot, a wiki url whose node does not "
        "resolve, an edited file that reconciles to nothing, a plan the engine refuses. "
        "Nothing is half-written: a refused push writes nothing at all."
    ),
    epilog=(
        "Examples:\n"
        "\n"
        "\b\n"
        'larkdocio --env-file .env roundtrip pull "https://your-domain.larksuite.com/docx/AbCdEfG" -o ./edit/\n'
        "larkdocio --env-file .env roundtrip push -o ./edit/\n"
        "larkdocio --env-file .env roundtrip push -o ./edit/ --apply"
    ),
)
@click.argument("phase", required=True, type=click.Choice(ROUNDTRIP_PHASES))
@click.argument("url", required=False, default="")
@click.option("-o", "--workdir", "workdir", default="./", help=(
    "A DIRECTORY, always — the one that holds the two files this verb passes between its "
    "phases (default ./): document.snapshot, which is ours and immutable, and document.md, "
    "which is yours and is the file you edit. `pull` writes both into it; `push` reads both "
    "out of it, so both phases must be given the SAME directory."))
@click.option("--apply", "apply_changes", is_flag=True, default=False, help=(
    "On `push` only: apply the plan that was just previewed. THIS DOES NOT SKIP THE PREVIEW "
    "— the plan is built, armed with the snapshot's revision and printed either way, and the "
    "write goes only through that plan; there is no flag anywhere on this command that "
    "reaches a write without one. Without it `push` is a rehearsal that writes NOTHING, which "
    "is what to run first. With it, the apply is followed by a re-read and a "
    "compose-equivalence verification of every edited block."))
@click.pass_context
def roundtrip(ctx, phase: str, url: str, workdir: str, apply_changes: bool):
    """Run one phase of the file-first round trip and report it — the ONE writing verb.

    The command layer contributes no flow of its own: :mod:`larkdocio.roundtrip` owns the
    order the steps happen in and every refusal, so a consumer calling the library and a
    consumer running this command get the same gates in the same order. What this adds is the
    surfacing — the product on stdout, everything said *about* the run through the logger, on
    stderr.
    """
    init_env(ctx.obj.get('ENV_FILE'))
    if phase == PHASE_PULL:
        if not url:
            raise click.ClickException(
                f"`{ROUNDTRIP_COMMAND} {PHASE_PULL}` needs the document URL to read — "
                f"`larkdocio {ROUNDTRIP_COMMAND} {PHASE_PULL} \"<url>\" -o {workdir}`"
            )
        result = roundtrip_flow.pull(url, workdir)
        click.echo(
            f"pulled {result.document_token} ({result.block_count} addressable blocks)\n"
            f"  snapshot (ours, immutable): {result.snapshot_path}\n"
            f"  markdown (yours, EDIT THIS): {result.markdown_path}\n"
            f"Then: larkdocio {ROUNDTRIP_COMMAND} {PHASE_PUSH} -o {workdir}"
        )
        return

    if url:
        raise click.ClickException(
            f"`{ROUNDTRIP_COMMAND} {PHASE_PUSH}` takes no URL — the document it pushes to is "
            f"the one recorded in the snapshot `{PHASE_PULL}` wrote, which is what keeps the "
            f"two phases addressing the same document. Got {url!r}."
        )
    result = roundtrip_flow.push(workdir, apply_changes=apply_changes)
    lines = [
        f"plan for {result.document_token}: {result.plan.change_count} change(s), "
        f"{_CONCURRENCY_GUARD_LABEL} {result.revision_guard}",
    ]
    for entry in result.plan.changes:
        lines.append(f"  {entry.state.value}: {entry.block_id or '(new block)'}")
    if not result.applied:
        lines.append(
            f"NOTHING WAS WRITTEN — this was the preview. Re-run with --apply to apply this "
            f"plan: larkdocio {ROUNDTRIP_COMMAND} {PHASE_PUSH} -o {workdir} --apply"
        )
    else:
        verification = result.verification
        lines.append(
            f"applied {len(result.log.applied)} entr(y/ies); read-back verification: "
            f"{'CLEAN' if verification.ok else 'MISMATCHED'} "
            f"({len(verification.verified)} verified by compose-equivalence)"
        )
        for block_id, why in verification.mismatched:
            lines.append(f"  MISMATCH {block_id}: {why}")
        for block_id, why in verification.unverifiable:
            lines.append(f"  UNVERIFIABLE {block_id}: {why}")
    click.echo("\n".join(lines))


if __name__ == "__main__":
    cli()
