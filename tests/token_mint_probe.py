"""THE TOKEN-MINT COVERAGE PROBE — which surfaces answer a rejected app pair, MEASURED.

Not a list. This module **executes** every surface's real client against **both** token-mint
paths broken at their own seams, hands whatever escapes to the **real CLI seam**, and reports
whether a consumer would have been told this is a credential problem.

**Why this exists.** One sentence in ``RELEASE_NOTES.md`` claiming which surfaces are covered
was hand-typed three times and wrong three times: too wide (all three verbs), then too narrow
(excluding Base), each falsified by execution and none caught by review. A hand-typed coverage
claim in this repo has a 0-for-3 record, so the claim is derived from here instead.

**What changed at LD-672, and it is the point.** This probe used to measure the **exception
class** — ``ObtainAccessTokenException`` meant covered, anything else meant not. That was a
proxy, and a proxy for the wrong thing: the class is a fact about *which mint ran*, while the
claim it fed is about *what the consumer is told*. Once the CLI seam grew an arm for the
raw-HTTP mint's own ``LarkAPIError``, the class-based measurement would have gone on reporting
four families as uncovered while they answered perfectly. So the question asked here is now the
consumer's question, put to the shipped seam: **does the guidance reach the terminal?**

**Neither seam is a mock of the thing under test.** The mint is broken one layer BELOW the
client — ``lark_oapi``'s own ``TokenManager`` for the SDK path, ``urlopen`` for the raw-HTTP
path — so each surface's client, its request construction and its error handling all run for
real, and so does ``cli._RefusalUniformCommand``. That is the difference between this and the
injected-callback test that let the false claim through.

**Nothing here may reach the network, and that is ASSERTED, not assumed.** See
:func:`inject_rejecting_urlopen` for the trap that has now cost three real auth calls.
"""
import json
import logging
import urllib.request

#: One real entry point per client family. The label is the word the shipped claim uses.
#: **Every family that mints a token is here**; the population guard in
#: ``tests/test_cli_refusal_uniformity.py`` holds that against the tree, so a new client family
#: cannot quietly go unmeasured.
PROBE_SUBJECTS = {
    "read": lambda: _read(),
    "drive": lambda: _drive(),
    "write": lambda: _write(),
    "base": lambda: _base(),
    "sheets": lambda: _sheets(),
    "comments": lambda: _comments(),
    "contacts": lambda: _contacts(),
}

#: Which CLI verbs (and phases) ride each family — the vocabulary a consumer reads.
#: Derived nowhere: it is the routing this repo documents, and it is checked against the real
#: click group by ``test_the_verb_mapping_names_only_REAL_click_verbs``.
VERBS_BY_FAMILY = {
    "read": ("download", "roundtrip pull"),
    "drive": ("folder",),
    "write": ("roundtrip push",),
    "base": (),
    "sheets": (),
    "comments": (),
    "contacts": (),
}

_GARBAGE = ("cli_garbage", "garbage")

#: **What Lark answers a rejected app pair with, on the raw-HTTP token endpoint.**
#:
#: The ``code`` VALUE is deliberately not load-bearing: the discriminator
#: (:func:`larkdocio.common.transport.is_credential_rejection`) asks whether Lark answered with
#: a non-zero, non-throttle code at all, precisely so that no hand-typed list of rejection
#: numbers has to be maintained — that is the instrument this issue exists to stop trusting.
#: Two message shapes are both on record for this endpoint: ``lark_oapi``'s own
#: ``"app not exist or app secret error"`` (the pair LD-658's SDK arm was written against) and
#: the ``"invalid param"`` LD-672's executed ``larkdocio folder`` run surfaced. The probe drives
#: the first; ``test_BOTH_observed_rejection_shapes_are_credential_rejections`` pins the second.
REJECTION_BODY = {"code": 10003, "msg": "app not exist or app secret error"}
OBSERVED_REJECTION_MESSAGES = ("app not exist or app secret error", "invalid param")


def _read():
    from larkdocio.read.client import Client

    return Client(*_GARBAGE, "larksuite.com").get_docx_content("docxGARBAGE")


def _drive():
    from larkdocio.drive.client import DriveClient

    return DriveClient(*_GARBAGE).list_folder_children("fldrGARBAGE")


def _write():
    from larkdocio.write.client import WriteClient

    return WriteClient(*_GARBAGE).get_document("docxGARBAGE")


def _base():
    from larkdocio.base.client import BaseReadClient

    return BaseReadClient(*_GARBAGE).get_app("bascnGARBAGE")


def _sheets():
    from larkdocio.sheets.client import SheetsReadClient

    return SheetsReadClient(*_GARBAGE).get_spreadsheet_meta("shtFREKWNI")


def _contacts():
    from larkdocio.contacts import ContactsSearchClient

    return ContactsSearchClient(*_GARBAGE).search_employees("someone")


def _comments():
    from larkdocio.comments.client import CommentsReadClient

    return CommentsReadClient(*_GARBAGE).list_comments("docxGARBAGE", file_type="docx")


class _NetworkBlocked(OSError):
    """Raised by the blocked socket connect — no probe may reach the network."""


class _RejectingResponse:
    """What ``urlopen`` hands back: Lark's own rejection body, verbatim bytes."""

    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def answering(payload):
    """A ``urlopen`` stand-in that hands back *payload* as Lark's response body."""
    response = _RejectingResponse(payload)

    def _urlopen(*_args, **_kwargs):
        return response
    return _urlopen


def urlopen_default_sites():
    """Every **import-time-bound** ``urlopen=`` default in the shipped package, by a walk.

    ``(qualified name, function, parameter kind)`` per site, derived from the package's own
    signatures. Nothing is named here, which is the whole point: the trap below is not one
    function's, it is an idiom this package uses in nine places.
    """
    import importlib
    import inspect
    import pkgutil

    import larkdocio

    sites = []
    seen = set()
    modules = [larkdocio]
    for info in pkgutil.walk_packages(larkdocio.__path__, larkdocio.__name__ + "."):
        try:
            modules.append(importlib.import_module(info.name))
        except Exception:                                        # noqa: BLE001
            continue
    for module in modules:
        for _name, member in vars(module).items():
            candidates = [member]
            if inspect.isclass(member):
                candidates = [value for value in vars(member).values()
                              if inspect.isfunction(value)]
            for func in candidates:
                if not inspect.isfunction(func):
                    continue
                key = (func.__module__, func.__qualname__)
                if key in seen:
                    continue
                try:
                    parameter = inspect.signature(func).parameters.get("urlopen")
                except (ValueError, TypeError):                  # pragma: no cover - builtins
                    continue
                if parameter is None or parameter.default is inspect.Parameter.empty:
                    continue
                if not callable(parameter.default):
                    continue
                seen.add(key)
                sites.append((f"{func.__module__}.{func.__qualname__}", func, parameter.kind))
    return sorted(sites)


def inject_rejecting_urlopen(monkeypatch, payload=None):
    """Make **every** door to ``urlopen`` in this package answer with Lark's rejection body.

    Returns the list of sites patched, so a caller can state the derived figure rather than a
    remembered one.

    **THE TRAP, in one sentence: a stub above a name-bound import is not a stub.**
    ``fetch_tenant_access_token`` takes ``urlopen=urllib.request.urlopen`` as a **default
    argument**, and so do the nine raw-HTTP clients' constructors — evaluated when the function
    is *defined*, so patching ``urllib.request.urlopen`` afterwards does not reach them. Three
    separate agents believed otherwise and each made a real (rejected, read-only, no-document)
    call to Lark's ``tenant_access_token`` endpoint; the third was the shipped test row this
    probe replaces, which had been dialling out on every suite run since it landed.

    So all three doors are shut: the module attribute (for anything that resolves it late), each
    bound default found by :func:`urlopen_default_sites`, and the socket layer, which sits below
    every binding and is the belt to the other two braces. The socket block **records** attempts
    rather than merely refusing them, because *"no call left"* is a measurement and not an
    inference — :func:`assert_nothing_dialled_out` is what turns it into one.
    """
    import inspect
    import socket

    response = _RejectingResponse(payload if payload is not None else REJECTION_BODY)

    def _rejecting_urlopen(*_args, **_kwargs):
        return response

    def _no_network(*args, **_kwargs):
        _DIALLED_OUT.append(args[1:] if len(args) > 1 else args)
        raise _NetworkBlocked("the token-mint probe may not reach the network")

    _DIALLED_OUT.clear()
    monkeypatch.setattr(urllib.request, "urlopen", _rejecting_urlopen, raising=True)
    monkeypatch.setattr(socket.socket, "connect", _no_network, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _no_network, raising=True)

    sites = urlopen_default_sites()
    assert sites, ("no import-time-bound `urlopen=` default was found — this injection would "
                   "then be relying on the module attribute alone, which is exactly the "
                   "assumption that leaked three real auth calls")
    for name, func, kind in sites:
        if kind is inspect.Parameter.KEYWORD_ONLY:
            monkeypatch.setitem(func.__kwdefaults__, "urlopen", _rejecting_urlopen)
        else:
            # ``__defaults__`` covers the POSITIONAL parameters only, so the index is taken
            # against those — counting keyword-only ones too would land on the wrong slot.
            positional = [name for name, parameter in
                          inspect.signature(func).parameters.items()
                          if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                                inspect.Parameter.POSITIONAL_OR_KEYWORD)]
            offset = len(positional) - len(func.__defaults__ or ())
            index = positional.index("urlopen") - offset
            defaults = list(func.__defaults__)
            defaults[index] = _rejecting_urlopen
            monkeypatch.setattr(func, "__defaults__", tuple(defaults))
    return sites


#: Every socket connect attempted since the last injection — see
#: :func:`assert_nothing_dialled_out`.
_DIALLED_OUT = []


def assert_nothing_dialled_out():
    """Fail unless the run made **no** outbound connection attempt at all."""
    assert not _DIALLED_OUT, (
        f"this run attempted {len(_DIALLED_OUT)} outbound connection(s) — {_DIALLED_OUT[:3]}. "
        f"A probe of a rejected credential must never reach Lark; find the `urlopen` door that "
        f"was left open (see inject_rejecting_urlopen).")


def break_the_sdk_mint(monkeypatch):
    """Make ``lark_oapi``'s own ``TokenManager`` refuse the way a wrong App Secret does.

    The tenant-token getters are **derived from the class**, not named: the attribute set has
    changed across ``lark-oapi`` versions, and an earlier draft hard-coded a name that does not
    exist — so it silently stopped breaking the SDK mint and cheerfully reported *every* surface
    as raw-HTTP, which is the exact wrong answer, produced while passing.
    """
    from lark_oapi.core.exception import ObtainAccessTokenException
    from lark_oapi.core.token.manager import TokenManager

    def _sdk_rejects(*_args, **_kwargs):
        raise ObtainAccessTokenException(
            "obtain tenant access token failed", 10003, "app not exist or app secret error")

    getters = [name for name in dir(TokenManager)
               if name.startswith("get_") and "tenant" in name]
    assert getters, ("lark_oapi's TokenManager exposes no tenant-token getter; the SDK half of "
                     "this probe would measure nothing")
    for name in getters:
        monkeypatch.setattr(TokenManager, name, staticmethod(_sdk_rejects), raising=True)
    return getters


def seam_answers(error, verb="folder"):
    """Put *error* through the REAL CLI seam; ``True`` when the credential guidance is emitted.

    This is the coverage question as a consumer would ask it, and it is asked of
    ``cli._RefusalUniformCommand`` itself rather than of a copy of its rules. ``verb`` only
    decides which command class instance is used; every subcommand is minted from the same
    class, which is the property that makes one enough.
    """
    import click

    from larkdocio.cli import cli

    command = cli.commands[verb]

    def _raise(*_args, **_kwargs):
        raise error

    records = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    log = logging.getLogger("larkdocio")
    handler = _Collect()
    log.addHandler(handler)
    original = command.callback
    command.callback = _raise
    context = click.Context(command, info_name=verb, parent=click.Context(cli))
    context.obj = {}
    try:
        command.invoke(context)
    except click.ClickException:
        pass
    except BaseException:                                        # noqa: BLE001
        # The seam let it through unconverted — the definition of not covered.
        return False
    finally:
        command.callback = original
        log.removeHandler(handler)
    return any("CREDENTIAL problem" in message for message in records)


def measure(monkeypatch):
    """``{family: True if COVERED else False}`` — by execution, for every subject.

    **How each path is broken, and why at these seams.**

    * **SDK path** — every tenant-token getter on ``lark_oapi``'s own ``TokenManager`` raises
      ``ObtainAccessTokenException`` (:func:`break_the_sdk_mint`).
    * **Raw-HTTP path** — every door to ``urlopen`` answers with Lark's own rejection body
      (:func:`inject_rejecting_urlopen`), so ``common/transport``'s real non-zero-code branch
      runs and raises the ``LarkAPIError`` it really raises, carrying the real code.

    Neither seam is a mock of the thing under test: each surface's client, its request
    construction, its error handling and the CLI seam all run for real. Nothing reaches the
    network, and :func:`assert_nothing_dialled_out` proves it rather than promising it.
    """
    break_the_sdk_mint(monkeypatch)
    inject_rejecting_urlopen(monkeypatch)

    measured = {}
    for family, call in sorted(PROBE_SUBJECTS.items()):
        try:
            call()
        except BaseException as escaped:                         # noqa: BLE001
            if isinstance(escaped, _NetworkBlocked):
                raise AssertionError(
                    f"the {family!r} probe dialled out — an `urlopen` door was left open, "
                    f"which is how three real auth calls happened. Fix the injection, never "
                    f"the assertion.") from None
            measured[family] = seam_answers(escaped)
        else:
            raise AssertionError(
                f"the {family!r} probe returned without minting a token, so it measures "
                f"nothing. Pick an entry point that reaches the API.")
    assert_nothing_dialled_out()
    return measured


def documented_labels(text, lead_in):
    """The backticked labels in the ONE sentence of ``text`` introduced by ``lead_in``.

    The claim's format is part of its contract: every label is backticked, so extraction needs
    no vocabulary list and cannot silently miss a plain-word surface — which is exactly how
    ``Base`` came to be named in a list nothing checked.
    """
    import re

    flat = " ".join(text.split())
    assert flat.count(lead_in) == 1, (
        f"expected exactly one {lead_in!r} sentence; found {flat.count(lead_in)}")
    sentence = flat.split(lead_in, 1)[1].split(".")[0]
    return {m.group(1) for m in re.finditer(r"`([a-z][a-z ]*)`", sentence)}
