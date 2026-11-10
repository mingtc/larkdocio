"""A rejected App ID/Secret is a CREDENTIAL problem on **both** of this library's token paths.

**LD-672.** The reader minted through ``lark_oapi`` and got the SDK's own
``ObtainAccessTokenException``, which LD-658's arm answers; every raw-HTTP surface — Drive, the
write engine, Sheets, preflight — minted through
:func:`larkdocio.common.transport.fetch_tenant_access_token` and got this library's own
``LarkAPIError``, which nothing caught. Executed: ``larkdocio folder <url>`` on a rejected pair
printed **zero bytes** and escaped an uncaught exception with no guidance at all.

This module owns the **transport-level** contract; the CLI-visible outcome (and the coverage
claim that is held set-equal to the probe) lives in ``tests/test_cli_refusal_uniformity.py``.

**Every arm here drives the REAL mint.** Nothing constructs a ``LarkAPIError`` by hand and
calls that a measurement: the errors under test come out of ``fetch_tenant_access_token``
itself, reached through a real client, with the ``urlopen`` door shut at every one of its nine
import-time-bound defaults **and** at the socket layer — and every arm asserts that no call
left the process (``token_mint_probe.assert_nothing_dialled_out``). That assertion is not
decoration: three separate agents assumed a module-attribute patch reached the mint, and each
made a real call to Lark's ``tenant_access_token`` endpoint. The third was a **shipped test
row** which had been dialling out on every suite run since it landed.
"""
import ast
import importlib
import inspect
import pkgutil
import urllib.error
import urllib.request

import pytest

import token_mint_probe as probe
from larkdocio.common import transport
from larkdocio.common.auth import LEGACY_ENV, READ_ENV, WRITE_ENV, resolved_read_env
from larkdocio.common.transport import (
    RawHttpClient,
    fetch_tenant_access_token,
    is_credential_rejection,
    token_mint_credential_env,
)
from larkdocio.errors import LarkAPIError, api_error

RATE_LIMIT_BODY = {"code": 99991400, "msg": "too many requests"}


def _mint(monkeypatch, urlopen):
    """Run the REAL mint with ``urlopen`` as its transport, and hand back what escaped."""
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(LarkAPIError) as caught:
        fetch_tenant_access_token("cli_garbage", "garbage", urlopen=urlopen)
    return caught.value


_answering = probe.answering


def _dead_network(*_args, **_kwargs):
    raise urllib.error.URLError("connection refused")


# --------------------------------------------------------------------------- #
# AC1 — the mint stamps its own failures, and the CODE decides which are       #
#       credential rejections.                                                 #
# --------------------------------------------------------------------------- #

def test_EVERY_raise_in_the_token_mint_IS_STAMPED_walked_not_named():
    """The stamp is what tells a mint failure from every other ``LarkAPIError``, so a branch
    added later must not be able to slip out unstamped. Walked over the function's own AST
    rather than counted: the ``LarkConfigError`` raise is exempt **by name and with a reason**
    — it is already a refusal class this command line converts, and it fires before any
    request is built.
    """
    tree = ast.parse(inspect.getsource(fetch_tenant_access_token))
    raises = [node for node in ast.walk(tree) if isinstance(node, ast.Raise)]
    assert len(raises) >= 4, (
        f"only {len(raises)} raise(s) found in the mint — this walk would be near-vacuous")

    unstamped = []
    for node in raises:
        raised = node.exc
        name = getattr(raised.func, "id", getattr(raised.func, "attr", None)) \
            if isinstance(raised, ast.Call) else None
        if name == "LarkConfigError":
            continue
        if name != "from_the_token_mint":
            unstamped.append(ast.unparse(raised)[:60])
    assert not unstamped, (
        f"these raises in the token mint are not stamped as coming from it: {unstamped}. "
        f"An unstamped one is invisible to is_credential_rejection, so the CLI seam answers it "
        f"with a traceback again.")


@pytest.mark.parametrize("message", probe.OBSERVED_REJECTION_MESSAGES)
def test_BOTH_observed_rejection_shapes_are_credential_rejections(monkeypatch, message):
    """Lark's answer to a rejected pair is on record with two different ``msg`` texts —
    ``lark_oapi``'s own and the ``invalid param`` the executed ``larkdocio folder`` run
    surfaced. Neither the text nor the code VALUE may be load-bearing; only the presence of a
    non-zero, non-throttle code is.
    """
    escaped = _mint(monkeypatch, _answering({"code": 10003, "msg": message}))
    assert is_credential_rejection(escaped), f"{message!r} was not read as a rejected credential"
    assert message in str(escaped), "Lark's own words did not survive"
    probe.assert_nothing_dialled_out()


def test_a_DEAD_NETWORK_is_a_token_mint_failure_and_NOT_a_credential_rejection(monkeypatch):
    """**The over-catch arm, and the reason the stamp alone is not the verdict.** The mint also
    raises when the call never arrives — ``URLError``, no code at all. Telling an operator with
    no network that their App Secret is wrong is the same defect class this issue fixes, in a
    new costume.
    """
    escaped = _mint(monkeypatch, _dead_network)
    assert escaped.code is None
    assert hasattr(escaped, transport.TOKEN_MINT_ATTRIBUTION), (
        "even a transport failure is stamped — the stamp says WHERE it came from, not what it "
        "means")
    assert not is_credential_rejection(escaped)


def test_a_THROTTLE_at_the_mint_is_not_a_credential_rejection(monkeypatch):
    """Lark's rate-limit code arrives from the same handshake and means the opposite thing:
    the pair is fine, the caller is early."""
    escaped = _mint(monkeypatch, _answering(RATE_LIMIT_BODY))
    assert escaped.is_rate_limit
    assert not is_credential_rejection(escaped)


def test_an_ORDINARY_Lark_failure_is_not_a_credential_rejection():
    """The class is not the discriminator: a coded ``LarkAPIError`` that did not come from the
    handshake — a missing document, a rejected parameter — keeps exactly the behaviour it has
    today, which is what keeps this fix a fix rather than a widening."""
    assert not is_credential_rejection(
        api_error("get_document failed: Code: 1770001, Msg: params error",
                  code=1770001, msg="params error"))
    assert not is_credential_rejection(ValueError("not an API error at all"))


# --------------------------------------------------------------------------- #
# AC4 — the guidance names the pair the FAILING CALL used.                      #
# --------------------------------------------------------------------------- #

def test_EVERY_raw_HTTP_client_DECLARES_the_pair_it_mints_on():
    """Walked over the class graph, not a list: the base answer ``()`` is the one that loses the
    attribution, so a new rider that forgets to override would silently fall back to *"one of
    these two pairs"* — the hedge, reintroduced for a call that knows the answer.
    """
    import larkdocio

    for info in pkgutil.walk_packages(larkdocio.__path__, larkdocio.__name__ + "."):
        try:
            importlib.import_module(info.name)
        except Exception:                                        # noqa: BLE001
            continue

    def _descendants(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from _descendants(sub)

    # The skeleton's own intermediate layers live in ``common.transport`` and declare no pair
    # on purpose — they are the shape, not a surface, and a pair is a fact about a surface.
    riders = [cls for cls in _descendants(RawHttpClient)
              if cls.__module__.startswith("larkdocio.")
              and cls.__module__ != RawHttpClient.__module__]
    assert len(riders) >= 8, f"only {len(riders)} riders found — the walk is not seeing the tree"

    silent = sorted(f"{cls.__module__}.{cls.__qualname__}" for cls in riders
                    if cls._credential_pair is RawHttpClient._credential_pair)
    assert not silent, (
        f"these raw-HTTP clients do not declare the credential pair they mint on: {silent}. "
        f"Add a _credential_pair() override — a rejected credential on that surface would "
        f"otherwise name both pairs and hedge, on a call that knows which one it used.")


def test_a_READ_client_names_the_READ_pair_and_a_WRITE_client_the_WRITE_pair(monkeypatch):
    """**The crux of AC4.** The write path resolves a *different* pair from the read path, so a
    message naming the read pair on a push failure is the *"names the wrong file"* defect
    wearing new clothes. Driven through both real clients' real mints.
    """
    from larkdocio.drive.client import DriveClient
    from larkdocio.write.client import WriteClient

    probe.inject_rejecting_urlopen(monkeypatch)

    with pytest.raises(LarkAPIError) as read_leg:
        DriveClient("cli_garbage", "garbage").list_folder_children("fldrGARBAGE")
    with pytest.raises(LarkAPIError) as write_leg:
        WriteClient("cli_garbage", "garbage").get_document("docxGARBAGE")

    assert is_credential_rejection(read_leg.value)
    assert is_credential_rejection(write_leg.value)
    assert token_mint_credential_env(read_leg.value) == resolved_read_env()
    assert token_mint_credential_env(read_leg.value) in (READ_ENV, LEGACY_ENV)
    assert token_mint_credential_env(write_leg.value) == WRITE_ENV
    assert token_mint_credential_env(write_leg.value) != token_mint_credential_env(
        read_leg.value), "the two paths' attribution collapsed onto one pair"
    probe.assert_nothing_dialled_out()


def test_an_UNATTRIBUTED_mint_failure_says_BOTH_pairs_rather_than_guessing(monkeypatch):
    """:func:`fetch_tenant_access_token` is importable, so a caller can mint outside a client
    and no pair can be attributed. ``()`` is the honest answer, and its consumer says *both,
    and Lark does not report which* — LD-658's own pattern, not a new invention."""
    escaped = _mint(monkeypatch, _answering(probe.REJECTION_BODY))
    assert token_mint_credential_env(escaped) == ()

    from larkdocio.common.auth import token_mint_refusal_lines

    hedged = token_mint_refusal_lines((resolved_read_env(), WRITE_ENV))
    assert "does not say WHICH app" in hedged[2]
    named = token_mint_refusal_lines((WRITE_ENV,))
    assert "does not say WHICH app" not in named[2] and WRITE_ENV[0] in named[2]


def test_the_INNERMOST_knower_wins_and_attribution_is_never_overwritten():
    """A client stamps only a pair the mint left empty. If the mint ever learns the pair
    itself, the client must not overwrite it with its own guess."""
    error = transport.from_the_token_mint(
        LarkAPIError("tenant_access_token error: x", code=10003), READ_ENV)
    transport.attribute_token_mint_failure(error, WRITE_ENV)
    assert token_mint_credential_env(error) == READ_ENV
    # ...and an error that never came from the mint is left completely alone.
    ordinary = api_error("get_document failed", code=1770001)
    transport.attribute_token_mint_failure(ordinary, WRITE_ENV)
    assert not hasattr(ordinary, transport.TOKEN_MINT_ATTRIBUTION)


# --------------------------------------------------------------------------- #
# The instrument's own honesty.                                                #
# --------------------------------------------------------------------------- #

def test_the_urlopen_INJECTION_covers_every_import_time_bound_default():
    """The trap this issue is most likely to be re-broken by: a stub above a name-bound import
    is not a stub. The sites are DERIVED from the package's signatures, so a tenth one added
    tomorrow is shut without this test being edited — and the figure is read off the walk
    rather than typed here.
    """
    sites = probe.urlopen_default_sites()
    names = [name for name, _func, _kind in sites]
    assert "larkdocio.common.transport.fetch_tenant_access_token" in names, (
        "the mint's own bound default is not in the injection's population — that is the exact "
        "door two agents left open")
    assert len(names) == len(set(names))
    # Every rider that mints over raw HTTP binds one; the walk finds them all, and the count is
    # asserted as a FLOOR so adding a client does not redden this for the wrong reason.
    assert len(sites) >= 9, f"only {len(sites)} bound urlopen defaults found: {names}"


def test_the_probe_ASSERTS_that_nothing_dialled_out_rather_than_inferring_it(monkeypatch):
    """The assertion has to be able to fail, or it is decoration. Driven by opening one door:
    a client handed the REAL urlopen reaches the blocked socket, which records the attempt.
    """
    probe.inject_rejecting_urlopen(monkeypatch)
    probe.assert_nothing_dialled_out()

    from larkdocio.drive.client import DriveClient

    # The one door the injection cannot shut — a caller passing urlopen explicitly.
    with pytest.raises(probe._NetworkBlocked):
        DriveClient("cli_garbage", "garbage",
                    urlopen=_really_dial).list_folder_children("fldrGARBAGE")
    with pytest.raises(AssertionError, match="outbound connection"):
        probe.assert_nothing_dialled_out()
    probe._DIALLED_OUT.clear()


def _really_dial(request, timeout=None):
    """Reach the socket layer for real — where the probe's block records the attempt."""
    import socket

    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("101.100.179.146", 443))
    raise AssertionError("unreachable: the probe's socket block must fire")     # pragma: no cover
