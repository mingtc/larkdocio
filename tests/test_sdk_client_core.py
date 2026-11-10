"""The SDK-client constructor family's characterization net (LD-534).

Written **before** the LD-534 moves (``safety-net-check``, the refactor charter's doctrine)
and green on the refactor's baseline commit, so every assertion here pins what the eight
hand-built ``lark.Client.builder()`` constructors **already did** — not what a shared core
ought to do. That ordering is the whole point: the file is the net the extraction falls into,
so it has to be able to catch the extraction going wrong.

**The gaps it was written to close**, each measured absent at the baseline rather than assumed:

* **The five-call builder chain itself was unobserved offline.** Every client that takes an
  injected ``sdk_client`` never reaches the chain, and no test constructed one without a stub,
  so dropping ``.log_level(...)``, or the ``https://open.`` prefix, or the timeout, would have
  been invisible until a live run. ``test_the_builder_chain_config_is_identical_on_all_eight``
  reads the built client's own ``Config`` and pins all five values.
* **Not one of the seven credential-absent constructor refusals was asserted anywhere** —
  ``grep -rn "no credentials were resolved" tests/`` returned nothing at the baseline. Those
  seven strings are exactly the text the move relocates.
* **Only two of the seven default limiters were pinned** (comments and contacts). The other
  five — both Base write limiters, the schema limiter, the two media limiters — were free to
  move silently.
* **The constructor signatures were load-bearing but unstated.** 27 test files pass
  ``sdk_client=`` and 35 pass ``rate_limiter=``; each of them proves its *own* call works, and
  none of them says what the signature *is*. ``test_every_constructor_signature_is_unchanged``
  says it, verbatim, so a reordered or renamed parameter reddens with the text of the change.
* **The read/write credential separation had no structural guard.** ``tests/test_auth.py``
  proves the two *getters* do not fall back across each other — it would stay green if
  ``BaseReadClient.from_read_credentials`` started calling ``get_write_credentials``. The
  three arms under "AC2" close that, and they are deliberately **structural** (which getter
  is called, and from where): on this tenant the READ and WRITE pairs alias one app with
  byte-identical secrets, so a live scope probe here would prove nothing.

Nothing in this file is a live test: no network, no credentials, no SDK call. The clients are
constructed with literal strings and either a stub or nothing.
"""
import ast
import importlib
import inspect
import pkgutil
import types
import typing

import pytest

import lark_oapi as lark
import larkdocio
from larkdocio.common.transport import RateLimiter
from larkdocio.errors import LarkConfigError


class _Rendered:
    """An annotation stand-in whose ``repr`` is already the text ``inspect`` should print."""

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return self.text


def _canonical_annotation(annotation):
    """Spell a union as ``A | B`` on every interpreter (LD-687).

    ``Optional[X]`` and ``X | None`` are the same object to the type system, but ``inspect``
    renders it ``Optional[X]`` before 3.14 and ``X | None`` from 3.14 on (where
    ``typing.Union`` became ``types.UnionType``). Only that spelling is normalised; each member
    is still rendered by ``inspect.formatannotation``, so a changed member type still reddens.
    """
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        return _Rendered(
            " | ".join(
                "None" if arg is type(None) else inspect.formatannotation(arg)
                for arg in typing.get_args(annotation)
            )
        )
    return annotation


def _signature_text(func):
    """``str(inspect.signature(func))`` with every union spelled the 3.14 way — the verbatim
    pin below, made interpreter-independent without loosening any other character of it."""
    sig = inspect.signature(func)
    return str(
        sig.replace(
            parameters=[
                p.replace(annotation=_canonical_annotation(p.annotation))
                for p in sig.parameters.values()
            ]
        )
    )


class _Stub:
    """Stands in for an SDK client. Never called — construction is the whole subject."""


# --------------------------------------------------------------------------- #
# The seven families that share the injection seam, and the eighth that does not
# --------------------------------------------------------------------------- #

#: One row per client family that declares the shared constructor shape, carrying every value
#: the LD-534 move could disturb: the module, the class, the exact ``__init__`` signature, the
#: default limiter as ``(max_per_sec, window)``, the credential-absent constructor refusal, and
#: the credential classmethod with the getter it is allowed to call and the text it refuses
#: with. Enumerated on purpose — a characterization table's job is to *state* the current
#: values — with :func:`test_the_seven_families_are_every_class_carrying_the_injection_seam`
#: derived from the code so an eighth family cannot join without a row.
FAMILIES = (
    dict(
        module="larkdocio.base.client",
        cls="BaseReadClient",
        signature=(
            "(self, app_id: str, app_secret: str, domain: str = 'larksuite.com', *, "
            "sdk_client=None, rate_limiter=None, page_size: int = 100, timeout: int = 30)"
        ),
        limiter=(50, 60.0),
        ctor_refusal="Cannot read a Base: no credentials were resolved",
        classmethod_name="from_read_credentials",
        getter="get_read_credentials",
        classmethod_refusal="Cannot read a Base: no read credentials in the environment",
    ),
    dict(
        module="larkdocio.base.write_client",
        cls="BaseWriteClient",
        signature=(
            "(self, app_id: str, app_secret: str, domain: str = 'larksuite.com', *, "
            "sdk_client=None, rate_limiter=None, timeout: int = 30)"
        ),
        limiter=(50, 60.0),
        ctor_refusal="Cannot write a Base: no credentials were resolved",
        classmethod_name="from_write_credentials",
        getter="get_write_credentials",
        classmethod_refusal="Cannot write a Base: no write credentials in the environment",
    ),
    dict(
        module="larkdocio.base.schema_client",
        cls="BaseSchemaClient",
        signature=(
            "(self, app_id: str, app_secret: str, domain: str = 'larksuite.com', *, "
            "sdk_client=None, rate_limiter=None, timeout: int = 30)"
        ),
        limiter=(50, 60.0),
        ctor_refusal="Cannot change a Base's schema: no credentials were resolved",
        classmethod_name="from_write_credentials",
        getter="get_write_credentials",
        classmethod_refusal=(
            "Cannot change a Base's schema: no write credentials in the environment"
        ),
    ),
    dict(
        module="larkdocio.base.media",
        cls="BaseMediaClient",
        signature=(
            "(self, app_id: str, app_secret: str, domain: str = 'larksuite.com', *, "
            "sdk_client=None, rate_limiter=None, timeout: int = 30)"
        ),
        limiter=(50, 60.0),
        ctor_refusal="Cannot upload or download media: no credentials were resolved",
        classmethod_name="from_write_credentials",
        getter="get_write_credentials",
        classmethod_refusal="Cannot upload media: no write credentials in the environment",
    ),
    dict(
        module="larkdocio.comments.client",
        cls="CommentsReadClient",
        signature=(
            "(self, app_id: str, app_secret: str, domain: str = 'larksuite.com', *, "
            "sdk_client=None, "
            "rate_limiter: larkdocio.common.transport.RateLimiter | None = None, "
            "user_id_type: str = 'open_id', page_size: int = 100, timeout: int = 30)"
        ),
        limiter=(60, 60.0),
        ctor_refusal="Cannot read comments: no credentials were resolved",
        classmethod_name="from_read_credentials",
        getter="get_read_credentials",
        classmethod_refusal="Cannot read comments: no read credentials in the environment",
    ),
    dict(
        module="larkdocio.contacts.client",
        cls="ContactsSearchClient",
        signature=(
            "(self, app_id: str, app_secret: str, domain: str = 'larksuite.com', *, "
            "sdk_client=None, "
            "rate_limiter: larkdocio.common.transport.RateLimiter | None = None, "
            "employee_id_type: str = 'open_id', page_size: int = 20, timeout: int = 30)"
        ),
        limiter=(1, 1.2),
        ctor_refusal="Cannot search the directory: no credentials were resolved",
        classmethod_name="from_read_credentials",
        getter="get_read_credentials",
        classmethod_refusal=(
            "Cannot search the directory: no read credentials in the environment"
        ),
    ),
    dict(
        module="larkdocio.drive.files_write",
        cls="DriveFilesWriteClient",
        signature=(
            "(self, app_id: str, app_secret: str, domain: str = 'larksuite.com', *, "
            "sdk_client=None, rate_limiter=None, timeout: int = 30)"
        ),
        limiter=(50, 60.0),
        ctor_refusal="Cannot upload a file: no credentials were resolved",
        classmethod_name="from_write_credentials",
        getter="get_write_credentials",
        classmethod_refusal="Cannot upload a file: no write credentials in the environment",
    ),
)

#: The eighth builder site, kept out of :data:`FAMILIES` because it shares almost nothing with
#: them: a **positional** constructor with no default for ``domain``, no injection seam, no
#: limiter at all, and the SDK client on the **public** ``lark_client`` attribute. It is the
#: determinism-guaranteed docx reader, so its shape is pinned separately and exactly.
READER = dict(
    module="larkdocio.read.client",
    cls="Client",
    signature="(self, app_id: str, app_secret: str, domain: str)",
    attribute="lark_client",
    classmethod_name="from_read_credentials",
    getter="get_read_credentials",
    classmethod_refusal="Cannot read: no read credentials in the environment",
)

IDS = [row["cls"] for row in FAMILIES]


def _klass(row):
    return getattr(importlib.import_module(row["module"]), row["cls"])


# --------------------------------------------------------------------------- #
# Completeness — the table cannot silently miss a family                       #
# --------------------------------------------------------------------------- #

def _classes_declaring_the_injection_seam():
    """Every class in the package that declares its **own** ``__init__`` taking both
    ``sdk_client`` and ``rate_limiter``.

    Derived, so an eighth SDK client added tomorrow lands here with nobody editing a list.
    "Its own" matters: three media clients (``sheets.media``'s two and ``write.media``'s one)
    inherit :class:`~larkdocio.base.media.BaseMediaClient`'s constructor rather than declaring
    one, so they ride whatever this table pins for their base and are not separate rows.
    """
    found = set()
    for found_module in pkgutil.walk_packages(larkdocio.__path__, "larkdocio."):
        try:
            module = importlib.import_module(found_module.name)
        except Exception:  # pragma: no cover - an unimportable module is another test's job
            continue
        for name, obj in vars(module).items():
            if not inspect.isclass(obj) or obj.__module__ != found_module.name:
                continue
            if "__init__" not in obj.__dict__:
                continue
            try:
                params = inspect.signature(obj.__init__).parameters
            except (ValueError, TypeError):  # pragma: no cover - C-level signature
                continue
            if "sdk_client" in params and "rate_limiter" in params:
                found.add((found_module.name, name))
    return found


def test_the_seven_families_are_every_class_carrying_the_injection_seam():
    """The table's completeness arm. A ninth SDK client with the shared seam and no row here
    reddens, which is what keeps this file a net rather than a snapshot of seven names."""
    assert _classes_declaring_the_injection_seam() == {
        (row["module"], row["cls"]) for row in FAMILIES
    }


def test_the_reader_is_deliberately_outside_that_set():
    """The eighth site's shape, stated as the reason it is a separate row: the docx reader
    carries **neither** injection keyword, so it cannot appear in the derived set above."""
    params = inspect.signature(_klass(READER).__init__).parameters
    assert "sdk_client" not in params and "rate_limiter" not in params


# --------------------------------------------------------------------------- #
# AC1 — the signatures, verbatim                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_every_constructor_signature_is_unchanged(row):
    """The injection seam's contract, spelled out. 27 + 35 test files pass these keywords;
    this is the one place that says what the parameters are, in what order, with what
    defaults — so a "harmless" reorder reddens here with the diff in the message."""
    assert _signature_text(_klass(row).__init__) == row["signature"]


@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_both_injection_keywords_are_keyword_only_and_default_to_none(row):
    """``sdk_client`` and ``rate_limiter`` are keyword-only with a ``None`` default on every
    family — the property the 62 call sites rely on, asserted as a property rather than read
    out of the signature string above."""
    params = inspect.signature(_klass(row).__init__).parameters
    for name in ("sdk_client", "rate_limiter"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[name].default is None


def test_the_reader_constructor_signature_is_unchanged():
    """Positional, with no default for ``domain`` — pinned because AC4 brought this file's
    builder chain in scope while leaving its constructor shape deliberately alone."""
    assert _signature_text(_klass(READER).__init__) == READER["signature"]


@pytest.mark.parametrize("row", FAMILIES + (READER,), ids=IDS + [READER["cls"]])
def test_the_credential_classmethod_keeps_its_name(row):
    """Named per class, never resolved through a shared entry point (see the AC2 arms)."""
    assert row["classmethod_name"] in _klass(row).__dict__


# --------------------------------------------------------------------------- #
# AC1 — the builder chain, read off the client it builds                       #
# --------------------------------------------------------------------------- #

def _built_config(client_obj, attribute):
    return getattr(client_obj, attribute)._config


@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_the_builder_chain_config_is_identical_on_all_seven(row):
    """The five chained calls, observed where they land: the SDK's own ``Config``. This is the
    assertion that would have caught a dropped ``log_level`` or a lost ``https://open.``
    prefix offline, which nothing did at the baseline."""
    built = _klass(row)("an-id", "a-secret", "feishu.cn")
    config = _built_config(built, "_sdk")
    assert (config.app_id, config.app_secret) == ("an-id", "a-secret")
    assert config.domain == "https://open.feishu.cn"
    assert config.log_level is lark.LogLevel.ERROR
    assert config.timeout == 30


@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_the_timeout_parameter_reaches_the_builder(row):
    """``timeout`` is a per-family constructor knob, not a constant inside the chain."""
    built = _klass(row)("an-id", "a-secret", timeout=7)
    assert _built_config(built, "_sdk").timeout == 7


def test_the_reader_builder_chain_config_is_the_same_five_values():
    """The eighth site, same five values — and on the **public** ``lark_client`` attribute,
    which stubs and tests assign to by name."""
    built = _klass(READER)("an-id", "a-secret", "feishu.cn")
    config = _built_config(built, READER["attribute"])
    assert (config.app_id, config.app_secret) == ("an-id", "a-secret")
    assert config.domain == "https://open.feishu.cn"
    assert config.log_level is lark.LogLevel.ERROR
    assert config.timeout == 30


def test_the_reader_has_no_rate_limiter_and_no_private_sdk_attribute():
    """AC4's "no limiter is introduced where there was none". The reader paces nothing, and
    its client is not reachable under the seven families' private name either — so a sweep
    that quietly gave it the shared shape reddens here."""
    built = _klass(READER)("an-id", "a-secret", "larksuite.com")
    assert hasattr(built, "lark_client")
    for absent in ("_sdk", "_limiter", "limiter"):
        assert not hasattr(built, absent), absent


# --------------------------------------------------------------------------- #
# AC1 — the injection seam's semantics                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_an_injected_sdk_client_bypasses_credential_resolution_entirely(row):
    """The reference behaviour: with a client supplied, blank credentials are **not** an
    error, because no credential is needed. Every offline test of these surfaces depends on
    exactly this, which is why it is stated once here instead of inferred 27 times."""
    stub = _Stub()
    built = _klass(row)("", "", sdk_client=stub)
    assert built._sdk is stub


@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_missing_credentials_with_no_injected_client_raise_the_familys_own_text(row):
    """Seven refusal strings, none of which was asserted anywhere at the baseline."""
    with pytest.raises(LarkConfigError) as excinfo:
        _klass(row)("", "")
    assert str(excinfo.value) == row["ctor_refusal"]


@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_a_half_credential_pair_is_refused_the_same_way(row):
    """``if not (app_id and app_secret)`` — an id with no secret is as absent as neither."""
    with pytest.raises(LarkConfigError) as excinfo:
        _klass(row)("an-id", "")
    assert str(excinfo.value) == row["ctor_refusal"]


# --------------------------------------------------------------------------- #
# AC5 — the limiters, per family                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_each_family_keeps_its_own_default_limiter(row):
    """``(max_per_sec, window)`` per family. Five of these seven were unpinned at the
    baseline, so the pacing policy could have been unified by accident."""
    built = _klass(row)("", "", sdk_client=_Stub())
    assert (built.limiter.max_per_sec, built.limiter.window) == row["limiter"]


@pytest.mark.parametrize("row", FAMILIES, ids=IDS)
def test_an_injected_limiter_is_used_as_is(row):
    """The other half of the seam: a supplied limiter is the limiter, not a template."""
    injected = RateLimiter(3, window=9.0)
    built = _klass(row)("", "", sdk_client=_Stub(), rate_limiter=injected)
    assert built.limiter is injected


# --------------------------------------------------------------------------- #
# AC2 — the read/write credential separation, structurally                     #
# --------------------------------------------------------------------------- #

READ_GETTER = "get_read_credentials"
WRITE_GETTER = "get_write_credentials"

#: The two modules that are *allowed* to name both getters: the one that defines them and the
#: package facade that re-exports them. Everything else in ``larkdocio.common`` naming either
#: one would mean a shared core had learned to resolve a credential pair — the precise
#: regression PROJECT.md § Credential aliasing consequence 2 forbids.
COMMON_MODULES_ALLOWED_TO_NAME_A_GETTER = frozenset(
    {"larkdocio.common.auth", "larkdocio.common"}
)

#: The two classmethod names the idiom uses, and the getter each one is the only caller of.
CREDENTIAL_CLASSMETHODS = {
    "from_read_credentials": READ_GETTER,
    "from_write_credentials": WRITE_GETTER,
}


def _called_names(node):
    return {
        child.func.attr if isinstance(child.func, ast.Attribute) else
        child.func.id if isinstance(child.func, ast.Name) else ""
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
    }


def _package_sources():
    sources = {}
    for found_module in pkgutil.walk_packages(larkdocio.__path__, "larkdocio."):
        try:
            module = importlib.import_module(found_module.name)
        except Exception:  # pragma: no cover
            continue
        path = getattr(module, "__file__", None)
        if not path or not path.endswith(".py"):  # pragma: no cover
            continue
        with open(path, encoding="utf-8") as handle:
            sources[found_module.name] = handle.read()
    return sources


def _credential_classmethods():
    """``(module, class, function_name, ast.FunctionDef)`` for every ``from_*_credentials``
    in the package — derived, so the arms below cover the whole idiom (16 sites at the LD-534
    baseline, across both the SDK and the raw-HTTP families) rather than this issue's eight."""
    out = []
    for name, source in _package_sources().items():
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                        member.name in CREDENTIAL_CLASSMETHODS:
                    out.append((name, node.name, member.name, member))
    return out


def test_the_credential_classmethod_census_is_not_empty():
    """A derivation that silently found nothing would make the two arms below vacuous."""
    found = _credential_classmethods()
    assert len(found) >= 16, [(m, c, f) for m, c, f, _ in found]


def test_no_credential_classmethod_can_reach_the_other_pairs_getter():
    """AC2, arm 1 — **which getter is called, read off the call site's own body.**
    ``from_read_credentials`` calls the read getter and never the write one; the write
    classmethod is the mirror. ``tests/test_auth.py`` proves the *getters* do not fall back
    across each other and would stay green if a client called the wrong one; this is the arm
    that would not.

    Structural on purpose. On this tenant the READ and WRITE pairs alias a single app with
    byte-identical secrets, so a runtime or scope-based check here could not tell the two
    apart — *"a least-privilege claim proven only on this tenant proves little."*
    """
    offenders = {}
    for module, cls, func_name, node in _credential_classmethods():
        called = _called_names(node)
        wanted = CREDENTIAL_CLASSMETHODS[func_name]
        forbidden = WRITE_GETTER if wanted == READ_GETTER else READ_GETTER
        if wanted not in called or forbidden in called:
            offenders[f"{module}.{cls}.{func_name}"] = sorted(called & {READ_GETTER,
                                                                       WRITE_GETTER})
    assert not offenders, (
        f"a credential classmethod resolves the wrong pair, or resolves none in its own "
        f"body: {offenders}"
    )


def test_no_function_anywhere_resolves_both_credential_pairs():
    """AC2, arm 2 — no fallback *across* the pairs. A single function body naming both getters
    is the shape a "try read, else write" fallback would take, and there is none: the two
    modules that hold both classmethods (``sheets/export_reader.py`` and the ``roundtrip``
    helpers) keep them in separate functions."""
    offenders = []
    for module, source in _package_sources().items():
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            called = _called_names(node)
            if READ_GETTER in called and WRITE_GETTER in called:
                offenders.append(f"{module}.{node.name}")
    assert not offenders, f"these bodies resolve both credential pairs: {offenders}"


def test_no_shared_core_under_common_resolves_a_credential_pair():
    """AC2, arm 3 — **the fence on the extraction itself.** The shared constructor core LD-534
    adds lives under ``larkdocio.common``; if it ever names a credential getter, then a
    ``credentials=``-shaped parameter could carry either pair through one call, which is the
    named regression. Only ``common.auth`` (which defines the getters) and the ``common``
    facade (which re-exports them) may name one.

    Green at the LD-534 baseline, before the core existed — so it is a ratchet the extraction
    has to keep satisfying, not a description written around the result.
    """
    offenders = {}
    for module, source in _package_sources().items():
        if not module.startswith("larkdocio.common"):
            continue
        if module in COMMON_MODULES_ALLOWED_TO_NAME_A_GETTER:
            continue
        named = sorted(g for g in (READ_GETTER, WRITE_GETTER) if g in source)
        if named:
            offenders[module] = named
    assert not offenders, (
        f"a module under larkdocio.common names a credential getter: {offenders} — a shared "
        f"core that can resolve either pair is what PROJECT.md forbids"
    )
