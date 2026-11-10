"""Typed exception taxonomy — LD-060 (W0-S1).

Pins the taxonomy contract (AC1) and the read-path wiring (AC2):

* AC1 — a ``LarkDocIOError`` base with a configuration/credential family, an
  API-error family carrying Lark's ``code`` + ``msg``, and a rate-limit error
  that is ``99991400``-aware (its own type, an API-error subclass).
* AC2 — no ``raise Exception(`` remains anywhere under ``src/larkdocio/read/``,
  and the API-failure sites raise the API family carrying the response
  ``code``/``msg``.

AC3 (CLI-observable text unchanged) is guarded by ``test_client.py`` (the exact
``str()`` message strings the reader's operator guidance is built from) staying green
without re-wording; those assertions now flow through the typed exceptions.
LD-531 completed that direction of travel: ``download._report_error`` reads the typed
``code`` and class instead of re-parsing the message, so the message is text for a human
again rather than an interface.
"""

import io
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import larkdocio.errors as errors
from larkdocio.errors import (
    LarkDocIOError,
    LarkConfigError,
    LarkAPIError,
    LarkRateLimitError,
    RATE_LIMIT_CODE,
    api_error,
)
from larkdocio.read.client import Client


# --------------------------------------------------------------------------- #
# AC1 — the taxonomy exists                                                   #
# --------------------------------------------------------------------------- #

def test_base_is_an_exception():
    assert issubclass(LarkDocIOError, Exception)


def test_config_family_under_base():
    err = LarkConfigError("missing credentials")
    assert isinstance(err, LarkDocIOError)
    assert issubclass(LarkConfigError, LarkDocIOError)
    assert str(err) == "missing credentials"


def test_api_family_carries_code_and_msg():
    err = LarkAPIError("boom", code="1061004", msg="not found")
    assert isinstance(err, LarkDocIOError)
    assert issubclass(LarkAPIError, LarkDocIOError)
    # The carried Lark error body is accessible as attributes …
    assert err.code == "1061004"
    assert err.msg == "not found"
    # … while str() is the caller-supplied message verbatim (AC3 preservation).
    assert str(err) == "boom"


def test_api_error_defaults_code_msg_to_none():
    err = LarkAPIError("no body here")
    assert err.code is None
    assert err.msg is None


def test_rate_limit_is_api_subclass_and_carries_code():
    err = LarkRateLimitError("rate limited", code=RATE_LIMIT_CODE, msg="too many")
    assert isinstance(err, LarkAPIError)
    assert isinstance(err, LarkDocIOError)
    assert issubclass(LarkRateLimitError, LarkAPIError)
    assert err.code == RATE_LIMIT_CODE
    assert err.msg == "too many"


def test_rate_limit_code_is_99991400():
    assert str(RATE_LIMIT_CODE) == "99991400"


def test_api_factory_routes_rate_limit_code_to_rate_limit_type():
    # 99991400-aware: the factory yields the rate-limit type for that code …
    err = api_error("throttled", code="99991400", msg="rate")
    assert isinstance(err, LarkRateLimitError)
    assert err.code == "99991400"
    # … also tolerant of an int-typed code from the SDK.
    assert isinstance(api_error("x", code=99991400), LarkRateLimitError)


def test_api_factory_routes_other_codes_to_plain_api_error():
    err = api_error("plain", code="1061004", msg="not found")
    assert isinstance(err, LarkAPIError)
    assert not isinstance(err, LarkRateLimitError)


def test_api_error_is_rate_limit_flag():
    assert api_error("x", code="99991400").is_rate_limit is True
    assert api_error("x", code="1061004").is_rate_limit is False
    assert LarkAPIError("x").is_rate_limit is False


# --------------------------------------------------------------------------- #
# AC2 — read path raises typed, no bare Exception left                        #
# --------------------------------------------------------------------------- #

_READ_DIR = Path(errors.__file__).resolve().parent / "read"


def test_no_bare_raise_exception_under_read():
    offenders = []
    for py in _READ_DIR.rglob("*.py"):
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\braise\s+Exception\s*\(", line):
                offenders.append(f"{py.name}:{lineno}: {line.strip()}")
    assert offenders == [], "bare `raise Exception(` still present:\n" + "\n".join(offenders)


def _resp(success=True, code=0, msg="ok", **data):
    return SimpleNamespace(
        success=lambda: success, code=code, msg=msg, data=SimpleNamespace(**data)
    )


def _media_resp(success=True, code=0, msg="ok", file_name=None, file=None):
    return SimpleNamespace(
        success=lambda: success, code=code, msg=msg, file_name=file_name, file=file
    )


def _client_with(**shims):
    client = Client.__new__(Client)
    client.lark_client = SimpleNamespace(
        docx=SimpleNamespace(v1=SimpleNamespace(
            document=SimpleNamespace(
                get=shims.get("docx_doc_get")
                or (lambda req: _resp(document=SimpleNamespace(title="t")))),
            document_block_children=SimpleNamespace(
                get=shims.get("children_get")
                or (lambda req: _resp(items=[], page_token="", has_more=False))),
        )),
        drive=SimpleNamespace(v1=SimpleNamespace(media=SimpleNamespace(
            download=shims.get("media_download")
            or (lambda req: _media_resp(file=io.BytesIO(b"")))))),
        board=SimpleNamespace(v1=SimpleNamespace(whiteboard=SimpleNamespace(
            download_as_image=shims.get("board_download")
            or (lambda req: SimpleNamespace(
                success=lambda: True, code=0, msg="ok", file=io.BytesIO(b"")))))),
        wiki=SimpleNamespace(v2=SimpleNamespace(space=SimpleNamespace(
            get_node=shims.get("wiki_get_node")
            or (lambda req: _resp(node=SimpleNamespace(obj_token="x")))))),
    )
    return client


def test_docx_document_failure_raises_api_family_with_code_msg():
    resp = _resp(success=False, code="1061004", msg="not found")
    client = _client_with(docx_doc_get=lambda req: resp)
    with pytest.raises(LarkAPIError) as ei:
        client.get_docx_content("doc9")
    assert ei.value.code == "1061004"
    assert ei.value.msg == "not found"


def test_docx_blocks_failure_raises_api_family_with_code_msg():
    resp = _resp(success=False, code="99991672", msg="not read permission")
    client = _client_with(children_get=lambda req: resp)
    with pytest.raises(LarkAPIError) as ei:
        client.get_docx_content("docB")
    assert ei.value.code == "99991672"
    assert ei.value.msg == "not read permission"


def test_download_image_failure_raises_api_family_with_code_msg(tmp_path):
    resp = _media_resp(success=False, code="1061004", msg="not read permission")
    client = _client_with(media_download=lambda req: resp)
    with pytest.raises(LarkAPIError) as ei:
        client.download_image("imgX", str(tmp_path))
    assert ei.value.code == "1061004"
    assert ei.value.msg == "not read permission"


def test_board_image_failure_raises_api_family_with_code_msg(tmp_path):
    resp = SimpleNamespace(
        success=lambda: False, code="1061004", msg="board denied",
        get_log_id=lambda: "LOG-1", raw=SimpleNamespace(status_code=403))
    client = _client_with(board_download=lambda req: resp)
    with pytest.raises(LarkAPIError) as ei:
        client.download_board_image("wb3", str(tmp_path))
    assert ei.value.code == "1061004"
    assert ei.value.msg == "board denied"


def test_wiki_node_failure_raises_api_family_with_code_msg():
    resp = _resp(success=False, code="1061004", msg="not found")
    client = _client_with(wiki_get_node=lambda req: resp)
    with pytest.raises(LarkAPIError) as ei:
        client.get_wiki_node_info("wikitok")
    assert ei.value.code == "1061004"
    assert ei.value.msg == "not found"


def test_rate_limit_code_from_api_surfaces_rate_limit_type():
    """A docx call that fails with 99991400 raises the rate-limit subclass."""
    resp = _resp(success=False, code="99991400", msg="too many requests")
    client = _client_with(docx_doc_get=lambda req: resp)
    with pytest.raises(LarkRateLimitError) as ei:
        client.get_docx_content("docRL")
    assert ei.value.code == "99991400"


def test_all_read_typed_errors_are_larkdocio_errors():
    """Every typed error the read path raises is catchable as the one base."""
    resp = _resp(success=False, code="1061004", msg="not found")
    client = _client_with(docx_doc_get=lambda req: resp)
    with pytest.raises(LarkDocIOError):
        client.get_docx_content("doc9")


# --------------------------------------------------------------------------- #
# LD-299 — the base class's promise, held by MEASUREMENT not by re-reading     #
# --------------------------------------------------------------------------- #
#
# ``LarkDocIOError``'s own docstring and the shipped README both promise that
# ``except LarkDocIOError`` is a complete net. Six shipped refusal roots escaped it (four
# more transitively), so the promise was false for a consumer who learned it from the
# wheel's METADATA. The fix re-parents the roots; the guard below is what keeps the promise
# true as new families are minted — an escaping exception reddens it, and so does an
# allow-list entry that has stopped being needed.

#: Exception classes defined under ``src/larkdocio/`` that are deliberately NOT
#: ``LarkDocIOError`` subclasses, **each with its written reason**. A bare set would rot into
#: a rubber stamp on its second use; a reason is what makes the next entry argue for itself.
ESCAPE_ALLOW_LIST = {
    "larkdocio.sheets.ops._structural._RemovedSnapshotFailed": (
        "Private internal carrier, absent from ``__all__`` and name-mangled by convention. "
        "Its own docstring states: \"Never escapes this module — :func:`_preview_structural` "
        "converts it to a typed refusal\". No consumer can catch what never crosses the "
        "module boundary, so the base class's promise does not reach it."
    ),
}

#: The six roots LD-299 re-parents, mapped to the base each one shipped with — the base a
#: consumer's existing ``except`` clause may already be relying on, which the re-parenting
#: must therefore RETAIN. ``LossNotEnumerable`` shipped on plain ``Exception``, so it gains
#: the taxonomy without being forced into ``ValueError`` it never claimed.
_REPARENTED_ROOTS_PRESERVED_BASE = {
    ("larkdocio.base.schema_client", "BaseSchemaRefusal"): ValueError,
    ("larkdocio.base.view_filters", "BaseFilterRefusal"): ValueError,
    ("larkdocio.base.field_authoring", "FieldAuthoringRefusal"): ValueError,
    ("larkdocio.base.schema_apply", "DestructiveConsentRequired"): ValueError,
    ("larkdocio.base.loss_preview", "LossNotEnumerable"): Exception,
    ("larkdocio.write.model.refusal", "RefusedError"): ValueError,
}

#: The transitive descendants — public in their module's ``__all__`` — fixed by re-parenting
#: ``FieldAuthoringRefusal``. Pinned by name so a future split of the family cannot silently
#: drop one back out of the taxonomy.
_TRANSITIVE_FIELD_AUTHORING = (
    "UncapturedFieldPropertyError",
    "UncapturedConversionError",
    "RefutedFieldAuthoringError",
)


def _walk_larkdocio_exception_classes():
    """Every exception class **defined** under ``larkdocio``, keyed ``module.QualName``.

    The same ``pkgutil.walk_packages`` enumeration LD-299's reproduction used. Keyed on the
    class's own ``__module__`` so a re-export cannot report a class twice or attribute it to
    the wrong file. ``import_errors`` is returned rather than swallowed: a module the walk
    could not import is a hole in the guard, not a pass.
    """
    import importlib
    import inspect
    import pkgutil

    import larkdocio

    found, import_errors = {}, []
    for mod_info in pkgutil.walk_packages(larkdocio.__path__, "larkdocio."):
        try:
            module = importlib.import_module(mod_info.name)
        except Exception as exc:  # pragma: no cover - a red guard, not a skip
            import_errors.append(f"{mod_info.name}: {exc!r}")
            continue
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseException)
                and obj.__module__.startswith("larkdocio")
            ):
                found[f"{obj.__module__}.{obj.__qualname__}"] = obj
    return found, import_errors


def _escapees(found, allow_list):
    """Classes that escape the base and are not allow-listed — direction (a) of the guard."""
    return sorted(
        name for name, cls in found.items()
        if not issubclass(cls, LarkDocIOError) and name not in allow_list
    )


def _stale_allow_list_entries(found, allow_list):
    """Allow-list entries that no longer earn their place — direction (b) of the guard.

    Two ways an entry rots, and both must redden: the class is **gone**, or the class no longer
    escapes (someone re-parented it and left the exemption behind).
    """
    stale = []
    for name in sorted(allow_list):
        if name not in found:
            stale.append(f"{name}: no longer defined under larkdocio — delete the entry")
        elif issubclass(found[name], LarkDocIOError):
            stale.append(f"{name}: is now a LarkDocIOError — delete the entry, it is covered")
    return stale


def test_the_completeness_walk_can_import_every_larkdocio_module():
    """The guard's own integrity: an unimportable module would hide an escapee."""
    _found, import_errors = _walk_larkdocio_exception_classes()
    assert import_errors == [], "modules the completeness walk could not import"


def test_every_exception_under_the_package_is_a_larkdocio_error():
    """AC3(a) — the base class's promise, measured over the whole package."""
    found, _errs = _walk_larkdocio_exception_classes()
    assert found, "the walk found no exception classes at all — enumeration is broken"
    assert _escapees(found, ESCAPE_ALLOW_LIST) == [], (
        "exception class(es) escape `LarkDocIOError`, so `except LarkDocIOError` is not the "
        "complete net common/errors.py and README.md promise. Re-parent onto the taxonomy, or "
        "add "
        "an ESCAPE_ALLOW_LIST entry WITH a written reason:\n  "
        + "\n  ".join(_escapees(found, ESCAPE_ALLOW_LIST))
    )


def test_every_allow_list_entry_still_exists_and_still_escapes():
    """AC3(b) — the list cannot rot: a stale entry reddens as loudly as a new escapee."""
    found, _errs = _walk_larkdocio_exception_classes()
    assert _stale_allow_list_entries(found, ESCAPE_ALLOW_LIST) == []


def test_the_guard_BITES_on_a_newly_minted_escaping_exception():
    """AC3(a) proven to bite — the next family minted against ``ValueError`` is caught."""
    class _NextRungRefusal(ValueError):
        pass

    _NextRungRefusal.__module__ = "larkdocio.base.some_new_rung"
    found, _errs = _walk_larkdocio_exception_classes()
    found["larkdocio.base.some_new_rung._NextRungRefusal"] = _NextRungRefusal
    assert _escapees(found, ESCAPE_ALLOW_LIST) == [
        "larkdocio.base.some_new_rung._NextRungRefusal"
    ]


def test_the_guard_BITES_on_an_allow_list_entry_that_stopped_escaping():
    """AC3(b) proven to bite — an exemption whose class was re-parented reddens."""
    class _NowInTheTaxonomy(LarkDocIOError):
        pass

    found = {"larkdocio.somewhere._Carrier": _NowInTheTaxonomy}
    stale = _stale_allow_list_entries(found, {"larkdocio.somewhere._Carrier": "a reason"})
    assert len(stale) == 1 and "is now a LarkDocIOError" in stale[0]


def test_the_guard_BITES_on_an_allow_list_entry_whose_class_vanished():
    """AC3(b) proven to bite — an exemption for a class nobody defines any more reddens."""
    stale = _stale_allow_list_entries({}, {"larkdocio.gone._Deleted": "a reason"})
    assert len(stale) == 1 and "no longer defined" in stale[0]


def test_every_allow_list_entry_carries_a_written_reason():
    """AC4 — a reason per entry, or the guard is a rubber stamp on its second use."""
    for name, reason in ESCAPE_ALLOW_LIST.items():
        assert isinstance(reason, str) and reason.strip(), f"{name} has no written reason"
        assert len(reason.split()) >= 8, f"{name}'s reason is too thin to argue anything"


def test_private_sheets_carrier_reason_cites_its_own_docstring():
    """AC4 — the one entry's reason quotes the class's own confinement claim."""
    from larkdocio.sheets.ops import _RemovedSnapshotFailed

    reason = ESCAPE_ALLOW_LIST["larkdocio.sheets.ops._structural._RemovedSnapshotFailed"]
    assert "Never escapes this module" in reason
    # The docstring is wrapped, so the citation is checked against its collapsed whitespace.
    assert "Never escapes this module" in " ".join(_RemovedSnapshotFailed.__doc__.split())
    from larkdocio.sheets import ops

    assert "_RemovedSnapshotFailed" not in getattr(ops, "__all__", ())


@pytest.mark.parametrize("module_name,cls_name", sorted(_REPARENTED_ROOTS_PRESERVED_BASE))
def test_each_reparented_root_is_a_larkdocio_error(module_name, cls_name):
    """AC1 — each of the six roots, asserted by name."""
    import importlib

    cls = getattr(importlib.import_module(module_name), cls_name)
    assert issubclass(cls, LarkDocIOError)


@pytest.mark.parametrize("module_name,cls_name", sorted(_REPARENTED_ROOTS_PRESERVED_BASE))
def test_each_reparented_root_keeps_the_base_it_shipped_with(module_name, cls_name):
    """AC2 — no existing ``except`` clause loses a refusal to the re-parenting."""
    import importlib

    cls = getattr(importlib.import_module(module_name), cls_name)
    preserved = _REPARENTED_ROOTS_PRESERVED_BASE[(module_name, cls_name)]
    assert issubclass(cls, preserved), (
        f"{cls_name} no longer subclasses {preserved.__name__} — a consumer's existing "
        f"`except {preserved.__name__}` would stop catching this refusal"
    )


@pytest.mark.parametrize("cls_name", _TRANSITIVE_FIELD_AUTHORING)
def test_field_authoring_descendants_inherit_the_fix(cls_name):
    """AC1/AC2 — the three public descendants are fixed transitively, ValueError intact."""
    from larkdocio.base import field_authoring

    cls = getattr(field_authoring, cls_name)
    assert issubclass(cls, field_authoring.FieldAuthoringRefusal)
    assert issubclass(cls, LarkDocIOError)
    assert issubclass(cls, ValueError)
    assert cls_name in field_authoring.__all__
