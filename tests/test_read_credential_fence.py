"""LD-580 — the read half of the credential fence refuses typed, like the write half.

**The bug this file fences.** ``get_write_credentials()`` raises ``LarkConfigError`` naming both
env vars on a missing or half-configured pair; ``get_read_credentials()`` used to return
``('','')`` and no signal at all, so an empty pair travelled into a client constructor and
surfaced as whatever Lark says about a blank app id — one layer away from the thing that was
actually wrong. The fence was armed in one direction only (dogfood round 5, DIGEST § 3 ranked
major **#12** — two independent opus legs on two tracks, reproduced by two observers).

**The three properties, and which one this change fails on if it fails at all.**

1. The getter refuses, in the F8 teaching shape, from **one constant** — naming the pair
   :func:`resolved_read_env` says is *in force* (never the other one, which would send a reader
   to edit a variable nothing is reading), the ``larkdocio config`` bootstrap, and the ``.env``
   doctrine — and never echoing a credential value.
2. The refusal is authored **once**: ``roundtrip``'s ``_read_credentials_or_refuse`` existed only
   because the getter did not raise, so it delegates now.
3. **The make-or-break** — a clone with no ``.env`` still gets a green offline suite and *loud
   skips* on the live rings. The skip predicate ``canary_support.read_creds_available`` used to
   rely on the sentinel; it now wraps the raising getter exactly as its own sibling
   ``write_creds_available`` already did, "so the live-write ring can *skip loudly* rather than
   error". This file proves that at unit level; the binding proof is a run in a shell with the
   variables genuinely unset (AC7 — an instrument beats a self-report).
"""
import inspect
import pathlib

import pytest

import canary_support
import larkdocio.common.auth as auth
from larkdocio.common.auth import (
    LEGACY_ENV,
    READ_CREDENTIALS_REFUSAL,
    READ_ENV,
    WRITE_ENV,
    get_read_credentials,
    read_credentials_refusal,
    resolved_read_env,
)
from larkdocio.errors import LarkConfigError


def _clear(monkeypatch):
    for name in (*READ_ENV, *LEGACY_ENV, *WRITE_ENV):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- #
# AC3 — the refusal, in the F8 teaching shape, from ONE constant               #
# --------------------------------------------------------------------------- #

def test_a_missing_pair_is_a_loud_typed_refusal_not_a_blank_tuple(monkeypatch):
    """The retired sentinel. Nothing configured used to yield ``('','')``."""
    _clear(monkeypatch)
    with pytest.raises(LarkConfigError):
        get_read_credentials()


def test_a_half_set_preferred_pair_still_falls_back_then_refuses(monkeypatch):
    """The fallback is NOT weakened (Dev note 3): a lone preferred id still falls through to the
    legacy pair — what retires is the blank *return* at the end of that fall, not the fall."""
    _clear(monkeypatch)
    monkeypatch.setenv(READ_ENV[0], "read_id_only")
    with pytest.raises(LarkConfigError):
        get_read_credentials()

    monkeypatch.setenv(LEGACY_ENV[0], "legacy_id")
    monkeypatch.setenv(LEGACY_ENV[1], "legacy_sec")
    assert get_read_credentials() == ("legacy_id", "legacy_sec")


def test_a_half_set_legacy_pair_refuses_instead_of_handing_over_a_blank_secret(monkeypatch):
    """Resolution is pair-wise on purpose (``auth.py`` module docstring), so a legacy pair with
    one half missing is a no-pair outcome too — and returning ``("l_id", "")`` from it is the
    same sentinel defect as ``('','')``, one blank further along."""
    _clear(monkeypatch)
    monkeypatch.setenv(LEGACY_ENV[0], "legacy_id")
    with pytest.raises(LarkConfigError):
        get_read_credentials()


def test_the_refusal_names_the_pair_actually_in_force_never_the_other_one(monkeypatch):
    """The defect :func:`resolved_read_env` exists to prevent. With no preferred pair set the
    LEGACY pair is what the read path is reading, so that is the pair the message names — naming
    the preferred one here would send a reader to edit a variable nothing is consulting."""
    _clear(monkeypatch)
    assert resolved_read_env() == LEGACY_ENV

    with pytest.raises(LarkConfigError) as refusal:
        get_read_credentials()
    message = str(refusal.value)

    assert LEGACY_ENV[0] in message and LEGACY_ENV[1] in message
    assert READ_ENV[0] not in message and READ_ENV[1] not in message


def test_the_refusal_teaches_the_bootstrap_and_the_env_doctrine():
    """F8, not F1: *"the difference is not severity; it is whether the message tells the caller
    what to DO"*. So the text names the CLI route that writes the pair, says credentials live
    only in a gitignored ``.env``, and says the two pairs never borrow from each other."""
    message = READ_CREDENTIALS_REFUSAL
    assert "larkdocio config" in message
    assert ".env" in message and "gitignore" in message.lower()
    assert "independently" in message and "never" in message


def test_the_refusal_never_echoes_a_credential_value(monkeypatch):
    """The write half's docstring promise (``auth.py`` — "names the env vars only; it never
    echoes a credential value"), now owed by the read half too."""
    _clear(monkeypatch)
    monkeypatch.setenv(READ_ENV[0], "an-id-that-must-not-be-quoted")
    monkeypatch.setenv(LEGACY_ENV[1], "a-secret-that-must-not-be-quoted")

    with pytest.raises(LarkConfigError) as refusal:
        get_read_credentials()

    message = str(refusal.value)
    assert "must-not-be-quoted" not in message, message


def test_the_write_pair_is_never_borrowed_to_satisfy_a_read(monkeypatch):
    """PROJECT.md § Credential aliasing consequence 2, restated at the refusal: with ONLY the
    write pair set the read path refuses, and the refusal does not so much as name a write
    variable — let alone return its value."""
    _clear(monkeypatch)
    monkeypatch.setenv(WRITE_ENV[0], "w_id")
    monkeypatch.setenv(WRITE_ENV[1], "w_sec")

    with pytest.raises(LarkConfigError) as refusal:
        get_read_credentials()

    message = str(refusal.value)
    assert "w_id" not in message and "w_sec" not in message
    assert WRITE_ENV[0] not in message and WRITE_ENV[1] not in message


# --------------------------------------------------------------------------- #
# AC3 — ONE CONSTANT, held bidirectionally against every documented spelling   #
# --------------------------------------------------------------------------- #

#: The shipped surfaces that spell the refusal out for a consumer. Each carries the text
#: **rendered from the constant**, byte-identical — never a second hand-typed copy (the
#: ``STALE_SHEET`` precedent: a string typed twice is two things to keep true).
_PROJECTIONS = ("GUIDE.md", "write/README.md")

#: The distinctive opening of the message. The reverse arm greps for it, so a second authoring
#: anywhere under ``src/`` is caught by its own first five words.
_LEAD = READ_CREDENTIALS_REFUSAL.split(":", 1)[0]


def _rendered_for_docs():
    """The constant rendered on the PREFERRED pair — the pair a documented example is about."""
    return READ_CREDENTIALS_REFUSAL.format(name_id=READ_ENV[0], name_secret=READ_ENV[1])


def _rendered_reachable():
    """The constant rendered on the LEGACY pair — the ONLY rendering the raise can produce.

    ``read_credentials_refusal()`` renders on ``resolved_read_env()``, which answers the
    preferred pair only when BOTH READ vars are set and non-blank — precisely the case in which
    ``get_read_credentials()`` returns instead of raising. So a doc quoting the preferred-pair
    rendering is illustrating a message no consumer can receive.
    """
    return READ_CREDENTIALS_REFUSAL.format(name_id=LEGACY_ENV[0], name_secret=LEGACY_ENV[1])


def _package_dir():
    """``src/larkdocio`` — the wheel's own tree, which is what ships."""
    return pathlib.Path(auth.__file__).resolve().parent.parent


@pytest.mark.parametrize("relative", _PROJECTIONS)
def test_every_documented_spelling_is_the_constant_rendered(relative):
    """Direction one: constant → docs. Change the wording in ``auth.py`` and every shipped
    spelling of it reddens until it is regenerated from the constant.

    **LD-586 transformed this arm; its reason is unchanged.** The reason was, and is, that a
    shipped spelling must be the CONSTANT RENDERED and never a second hand-typed copy — the
    ``STALE_SHEET`` precedent. What changed is which rendering satisfies it: pinning every
    projection to the PREFERRED-pair rendering made the shipped guide illustrate a message the
    raise cannot produce (``resolved_read_env()`` answers the preferred pair only when both READ
    vars are set, which is exactly when the getter returns instead of raising), and it sent a
    reader with an empty ``.env`` to edit a variable nothing was reading. So either rendering
    projects — **and a doc that quotes the preferred-pair one must SAY which pair it rendered
    for**, which is the clause the guide's copy had dropped.
    """
    text = (_package_dir() / relative).read_text(encoding="utf-8")
    preferred, reachable = _rendered_for_docs() in text, _rendered_reachable() in text
    assert preferred or reachable, (
        f"{relative} does not carry the refusal as rendered from "
        "auth.READ_CREDENTIALS_REFUSAL — the doc is a projection, not a retyping"
    )
    if preferred and not reachable:
        assert "in force" in text or "preferred pair" in text, (
            f"{relative} quotes the PREFERRED-pair rendering, which the raise never produces, "
            "without saying which pair it was rendered for — name the pair in force"
        )


def test_no_second_authoring_of_the_refusal_exists_under_src():
    """Direction two: every documented spelling → the constant. Any file under ``src/`` whose
    text opens the refusal is either the module that DEFINES it or a registered projection."""
    allowed = {pathlib.Path(auth.__file__).resolve()} | {
        (_package_dir() / relative).resolve() for relative in _PROJECTIONS
    }
    strays = sorted(
        str(path.relative_to(_package_dir()))
        for path in _package_dir().rglob("*")
        if path.is_file()
        and path.suffix in (".py", ".md")
        and path.resolve() not in allowed
        and _LEAD in path.read_text(encoding="utf-8", errors="ignore")
    )
    assert not strays, (
        f"a second authoring of the read-credential refusal: {strays}. It is ONE constant in "
        "common/auth.py that every spelling projects from."
    )


def test_the_rendered_refusal_carries_the_pair_it_was_rendered_for(monkeypatch):
    """The seam between the constant and the raise: :func:`read_credentials_refusal` is what
    binds the template to ``resolved_read_env()``, and the getter raises exactly its text."""
    _clear(monkeypatch)
    with pytest.raises(LarkConfigError) as refusal:
        get_read_credentials()
    assert str(refusal.value) == read_credentials_refusal()
    assert read_credentials_refusal() == READ_CREDENTIALS_REFUSAL.format(
        name_id=LEGACY_ENV[0], name_secret=LEGACY_ENV[1])


# --------------------------------------------------------------------------- #
# AC4 — the second authoring retires, its reason preserved                     #
# --------------------------------------------------------------------------- #

def test_roundtrip_no_longer_re_authors_the_read_refusal():
    """``_read_credentials_or_refuse`` existed *only because the getter did not raise*; with the
    getter raising it becomes the exact thing its own sibling forbids — "a second authoring of
    that refusal here would be a second thing to keep true". So it delegates."""
    source = inspect.getsource(
        __import__("larkdocio.roundtrip", fromlist=["x"])._read_credentials_or_refuse)
    body = source.split('"""')[-1]
    assert "if not (app_id and app_secret)" not in body, (
        "roundtrip still re-implements the blank check the getter now owns")
    assert "resolved_read_env" not in body, (
        "roundtrip still names the in-force pair itself instead of delegating")
    assert "get_read_credentials()" in body


def test_the_retired_reason_is_preserved_not_struck():
    """Supersession § A.1: the **reason** stays, only the **conclusion** is superseded. A
    rationale-free strike is what gets a settled argument re-litigated."""
    doc = inspect.getdoc(
        __import__("larkdocio.roundtrip", fromlist=["x"])._read_credentials_or_refuse) or ""
    assert "blanks" in doc, "the original reason (it returned blanks) has to survive"
    assert "LD-580" in doc, "the superseding conclusion has to be attributed"
    assert "second thing to keep true" in doc or "second authoring" in doc


def test_roundtrip_pull_refuses_with_the_getter_text_plus_its_recovery_pointer(monkeypatch):
    """Delegation is not a downgrade: the caller still gets the shipped recovery pointer
    ``_TEACHES_THE_CREDENTIAL_SPLIT`` on top of the getter's own teaching text."""
    from larkdocio import roundtrip

    _clear(monkeypatch)
    with pytest.raises(LarkConfigError) as refusal:
        roundtrip._read_credentials_or_refuse("`roundtrip pull`")

    message = str(refusal.value)
    assert read_credentials_refusal() in message
    assert LEGACY_ENV[0] in message


# --------------------------------------------------------------------------- #
# AC2 — THE MAKE-OR-BREAK: the skip predicate answers False, it does not raise #
# --------------------------------------------------------------------------- #

def test_the_live_skip_predicate_answers_false_instead_of_raising(monkeypatch):
    """The single most likely way this change lands broken. ``read_creds_available`` is a
    ``skipif`` predicate: if it raises, every live ring **errors** instead of skipping loudly."""
    _clear(monkeypatch)
    assert canary_support.read_creds_available() is False


def test_the_read_predicate_uses_the_shape_its_own_sibling_already_used():
    """``write_creds_available`` was the in-tree answer key — the same problem, already solved
    once in this repo, with its reason written down. The read half copies the shape *and* the
    reason, so the next reader does not have to re-derive why the ``except`` is there."""
    doc = inspect.getdoc(canary_support.read_creds_available) or ""
    source = inspect.getsource(canary_support.read_creds_available)
    assert "except LarkConfigError" in source
    assert "skip loudly" in doc, (
        "the reason write_creds_available records — so the ring can skip loudly rather than "
        "error — has to travel with the shape")


def test_live_availability_and_the_skip_reason_still_answer_with_no_creds(monkeypatch):
    """The two functions the rings actually call: neither may raise, and the creds-absent
    message still names the env vars it named before."""
    _clear(monkeypatch)
    monkeypatch.setenv(canary_support.CANARY_DOC_ENV, "https://example.larksuite.com/docx/TOKEN")

    assert canary_support.live_available() is False
    reason = canary_support.missing_reason()
    assert reason is not None
    assert READ_ENV[0] in reason and LEGACY_ENV[0] in reason


def test_neither_consent_fence_became_credential_driven():
    """A consent fence keyed on a credential would be a different fence (AC2). The LD-505 media
    guardrail and the LD-537 live-write fence answer *was this authorized*, never *is this
    configured* — and this change must not have blurred the two."""
    for module in ("media_guardrail", "live_write_fence"):
        source = pathlib.Path(
            __import__(module).__file__).read_text(encoding="utf-8")
        assert "get_read_credentials" not in source
        assert "creds_available" not in source


# --------------------------------------------------------------------------- #
# AC5 — the bootstrap route the refusal points at must keep working            #
# --------------------------------------------------------------------------- #

def test_larkdocio_config_still_reports_on_a_clone_with_nothing_configured(monkeypatch, tmp_path):
    """``larkdocio config`` **is** the remedy the refusal names, so it is the one read-path
    caller that must survive the raise: it displays the (empty) current values instead of
    refusing to run. A remedy that cannot run on the machine that needs it is not a remedy."""
    from click.testing import CliRunner

    from larkdocio.cli import cli

    _clear(monkeypatch)
    result = CliRunner().invoke(
        cli, ["--env-file", str(tmp_path / ".env"), "config"])

    assert result.exit_code == 0, result.output


def test_preflights_pragma_claim_is_now_true(monkeypatch):
    """``preflight.py``'s ``# pragma: no cover - get_read_credentials raises first`` asserted a
    raise that did not happen. It does now — the comment describes the code again."""
    from larkdocio import preflight

    _clear(monkeypatch)
    with pytest.raises(LarkConfigError):
        preflight.check_permissions(("get_docx_content",))
