"""The ``.env`` bootstrap writes the PREFERRED read pair — and never re-keys a file.

The bug this file fences (LD-182): ``larkdocio config`` bootstrapped a ``.env`` onto the
**legacy** ``LARK_APP_ID`` / ``LARK_APP_SECRET`` names while the read path *prefers*
``LARK_READ_APP_ID`` / ``LARK_READ_APP_SECRET`` and only falls back to the legacy pair. The
CLI's own onboarding therefore taught every new consumer the deprecated scheme, and the
least-privilege read/write separation was unreachable from the documented path. Nothing broke
(the fallback caught it) — which is exactly why it survived.

Three contracts are pinned here, and the second is a regression fence, not a feature:

1. **A fresh file gets the preferred pair.** Both bootstrap doors — ``init_env``'s stub for a
   missing file and ``set_env_credentials``'s persistence — write ``LARK_READ_APP_*``.
2. **Every legacy file keeps resolving, unchanged.** The pair-wise resolution order in
   ``larkdocio.common.auth`` is untouched: modern pair when *both* are set, else the legacy
   pair. Proved from real files on disk (four shapes), not only from a patched environment.
3. **An existing credential file is never silently re-keyed.** A ``.env`` that already carries
   the legacy names is updated *in place* on those names and told so in the command's output.
   Rewriting someone's credential file to a different key scheme is a surprising side effect,
   and a half-migrated file (modern pair shadowing a legacy pair the owner still hand-edits)
   is worse than a legacy one.

Every test writes to a ``tmp_path`` only — the repository's own ``.env`` is never touched, and
no ``.env`` is ever created outside a temporary directory.
"""
import inspect
import logging
import os
import pathlib
import re
import stat

import pytest
from dotenv import dotenv_values

import larkdocio.common.auth as auth
from larkdocio.common import LEGACY_ENV, READ_ENV, WRITE_ENV
from larkdocio.errors import LarkConfigError

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: A value that must never reach a log record, a stdout echo, or an error message.
SENTINEL_SECRET = "SENTINEL_SECRET_VALUE_NEVER_ECHOED"


@pytest.fixture(autouse=True)
def isolate_credential_env(monkeypatch):
    """Neutralize the six credential names for the whole module.

    ``init_env`` calls ``load_dotenv(override=True)`` and ``set_env_credentials`` assigns
    ``os.environ`` directly, so the names must be *touched through monkeypatch* for teardown to
    restore the pre-test process state.
    """
    for name in (*READ_ENV, *LEGACY_ENV, *WRITE_ENV):
        monkeypatch.delenv(name, raising=False)


def _assigned_keys(path):
    """The env keys the file at *path* actually assigns (``#`` comments ignored)."""
    return set(dotenv_values(path))


def _credential_keys(path):
    """Only the read/legacy/write credential names among a file's assignments."""
    return _assigned_keys(path) & {*READ_ENV, *LEGACY_ENV, *WRITE_ENV}


# --------------------------------------------------------------------------- #
# 1. A fresh file is bootstrapped onto the PREFERRED read pair                 #
# --------------------------------------------------------------------------- #

def test_init_env_stub_assigns_the_preferred_read_pair(tmp_path):
    """The stub written for a missing ``.env`` carries the preferred names as the primary
    keys — the pair the read path actually prefers, not the compat fallback."""
    env_path = tmp_path / ".env"

    auth.init_env(str(env_path))

    assert _credential_keys(env_path) == set(READ_ENV), env_path.read_text(encoding="utf-8")


def test_set_env_credentials_persists_under_the_preferred_names(tmp_path):
    """``larkdocio config --appId … --appSecret …`` on a fresh file lands the values under
    ``LARK_READ_APP_*`` — in the file *and* in the live process env for the current run."""
    env_path = tmp_path / ".env"

    auth.set_env_credentials("fresh_id", "fresh_secret", str(env_path))

    values = dotenv_values(env_path)
    assert values[READ_ENV[0]] == "fresh_id"
    assert values[READ_ENV[1]] == "fresh_secret"
    assert _credential_keys(env_path) == set(READ_ENV)
    assert os.environ[READ_ENV[0]] == "fresh_id"
    assert os.environ[READ_ENV[1]] == "fresh_secret"


def test_a_freshly_bootstrapped_file_resolves_through_the_preferred_pair(tmp_path):
    """End to end: bootstrap, then resolve. The credentials a fresh onboarding writes are the
    ones the reader picks up — through the preferred branch, with no fallback involved."""
    env_path = tmp_path / ".env"

    auth.set_env_credentials("boot_id", "boot_secret", str(env_path))

    assert auth.get_read_credentials() == ("boot_id", "boot_secret")
    assert os.environ.get(LEGACY_ENV[0], "") == ""


def test_neither_bootstrap_door_assigns_the_write_pair(tmp_path):
    """The write credentials are deliberately out of this bootstrap: the writer uses a
    separate, narrowly-scoped app, and the read/write separation is the point."""
    stub_only = tmp_path / "stub.env"
    auth.init_env(str(stub_only))

    with_values = tmp_path / "values.env"
    auth.set_env_credentials("id", "sec", str(with_values))

    for path in (stub_only, with_values):
        assert not _assigned_keys(path) & set(WRITE_ENV), path.read_text(encoding="utf-8")
        assert os.environ.get(WRITE_ENV[0], "") == ""
        assert os.environ.get(WRITE_ENV[1], "") == ""


def test_the_stub_still_names_the_legacy_pair_as_an_accepted_fallback(tmp_path):
    """A consumer reading the bootstrapped file must be able to see that an existing legacy
    file keeps working — the fallback is a shipped contract, not a secret."""
    env_path = tmp_path / ".env"
    auth.init_env(str(env_path))

    text = env_path.read_text(encoding="utf-8")
    assert LEGACY_ENV[0] in text and LEGACY_ENV[1] in text
    # …mentioned, but never *assigned*: a commented name is documentation, an assignment
    # would put the file back on the deprecated scheme.
    assert not _assigned_keys(env_path) & set(LEGACY_ENV)


# --------------------------------------------------------------------------- #
# 2. REGRESSION FENCE — every legacy file keeps resolving, from disk           #
# --------------------------------------------------------------------------- #

#: ``(label, file body, expected (id, secret))`` — the four shapes a real ``.env`` takes.
#: The last one is the pair-wise rule that a lone modern id must NOT shadow a working legacy
#: pair (mixing a modern id with a legacy secret would be the actual data-corruption bug).
_RESOLUTION_SHAPES = (
    (
        "modern-only",
        f"{READ_ENV[0]}=m_id\n{READ_ENV[1]}=m_sec\n",
        ("m_id", "m_sec"),
    ),
    (
        "legacy-only (the file the old bootstrap wrote)",
        f"{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n",
        ("l_id", "l_sec"),
    ),
    (
        "both — the preferred pair wins",
        f"{READ_ENV[0]}=m_id\n{READ_ENV[1]}=m_sec\n{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n",
        ("m_id", "m_sec"),
    ),
    (
        "half-populated modern pair + complete legacy pair",
        f"{READ_ENV[0]}=m_id_only\n{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n",
        ("l_id", "l_sec"),
    ),
)


@pytest.mark.parametrize(
    "body,expected", [(body, expected) for _label, body, expected in _RESOLUTION_SHAPES],
    ids=[label for label, _body, _expected in _RESOLUTION_SHAPES],
)
def test_resolution_from_a_real_file_is_unchanged(tmp_path, body, expected):
    """Loaded from a file on disk, not a hand-patched environment — the shape a consumer
    actually has. The resolution order is a shipped contract and this fixes it in place."""
    env_path = tmp_path / ".env"
    env_path.write_text(body, encoding="utf-8")

    auth.init_env(str(env_path))

    assert auth.get_read_credentials() == expected


def test_a_legacy_only_file_is_loaded_not_rewritten(tmp_path):
    """The compat path is read-only: loading a legacy file must not add, remove or reorder a
    single byte of it."""
    env_path = tmp_path / ".env"
    body = f"{LEGACY_ENV[0]}=already\n{LEGACY_ENV[1]}=here\n"
    env_path.write_text(body, encoding="utf-8")

    auth.init_env(str(env_path))

    assert env_path.read_text(encoding="utf-8") == body


# --------------------------------------------------------------------------- #
# 3. An existing file is never silently re-keyed                              #
# --------------------------------------------------------------------------- #

def test_an_existing_legacy_file_is_updated_in_place_never_re_keyed(tmp_path, caplog):
    """The documented call: a file already on the legacy names stays on them. The new values
    land on the keys that are there, no modern key is appended, and the file is *not* migrated
    behind the owner's back."""
    env_path = tmp_path / ".env"
    env_path.write_text(f"{LEGACY_ENV[0]}=old_id\n{LEGACY_ENV[1]}=old_sec\n", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        auth.set_env_credentials("new_id", "new_sec", str(env_path))

    values = dotenv_values(env_path)
    assert values[LEGACY_ENV[0]] == "new_id"
    assert values[LEGACY_ENV[1]] == "new_sec"
    assert _credential_keys(env_path) == set(LEGACY_ENV)
    # …and the reader still finds them, through the fallback branch.
    assert auth.get_read_credentials() == ("new_id", "new_sec")
    # The behavior is stated in the command's output, naming both schemes so the choice is
    # legible and the migration is the owner's to make.
    output = caplog.text
    assert LEGACY_ENV[0] in output and READ_ENV[0] in output


def test_an_existing_legacy_file_keeps_its_scheme_even_when_the_keys_are_blank(tmp_path):
    """The file the *old* bootstrap left behind: legacy keys present but empty. Key presence,
    not key value, is what says "this file is on that scheme"."""
    env_path = tmp_path / ".env"
    env_path.write_text(f"# bootstrapped earlier\n{LEGACY_ENV[0]}=\n{LEGACY_ENV[1]}=\n", encoding="utf-8")

    auth.set_env_credentials("filled_id", "filled_sec", str(env_path))

    assert _credential_keys(env_path) == set(LEGACY_ENV)
    assert dotenv_values(env_path)[LEGACY_ENV[0]] == "filled_id"


def test_a_commented_legacy_pair_does_not_count_as_the_file_s_scheme(tmp_path):
    """``.env.example``'s legacy block is commented out. A comment is documentation, so a file
    copied from it is a *fresh* file and gets the preferred pair."""
    env_path = tmp_path / ".env"
    env_path.write_text(f"# {LEGACY_ENV[0]}=\n# {LEGACY_ENV[1]}=\n", encoding="utf-8")

    auth.set_env_credentials("copy_id", "copy_sec", str(env_path))

    assert _credential_keys(env_path) == set(READ_ENV)


def test_a_modern_file_is_updated_in_place_with_no_legacy_key_added(tmp_path):
    """The already-correct file: same in-place rule, no duplicate scheme."""
    env_path = tmp_path / ".env"
    env_path.write_text(f"{READ_ENV[0]}=old_id\n{READ_ENV[1]}=old_sec\n", encoding="utf-8")

    auth.set_env_credentials("new_id", "new_sec", str(env_path))

    assert _credential_keys(env_path) == set(READ_ENV)
    assert dotenv_values(env_path)[READ_ENV[0]] == "new_id"


def test_a_mixed_file_is_written_on_the_pair_that_actually_resolves(tmp_path):
    """A file carrying both pairs: the modern pair is what the reader uses, so that is where
    a new value has to land. Writing the legacy half would silently have no effect."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"{READ_ENV[0]}=\n{READ_ENV[1]}=\n{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n"
    , encoding="utf-8")

    auth.set_env_credentials("new_id", "new_sec", str(env_path))

    values = dotenv_values(env_path)
    assert values[READ_ENV[0]] == "new_id"
    assert values[READ_ENV[1]] == "new_sec"
    # the legacy half is left exactly as the owner had it
    assert values[LEGACY_ENV[0]] == "l_id"
    assert values[LEGACY_ENV[1]] == "l_sec"
    assert auth.get_read_credentials() == ("new_id", "new_sec")


def test_only_the_provided_field_is_persisted(tmp_path):
    """A blank field is not written — the historical guard, now on the preferred names."""
    env_path = tmp_path / ".env"

    auth.set_env_credentials("only_id", "", str(env_path))

    assert dotenv_values(env_path)[READ_ENV[0]] == "only_id"
    assert os.environ.get(READ_ENV[1], "") == ""


# --------------------------------------------------------------------------- #
# 3b. A ONE-SIDED update: the key the value lands on, AND whether it takes     #
#     effect.                                                                  #
#                                                                              #
#     The edge these pin: the write target is chosen by which credential keys a #
#     file ASSIGNS, and a blank assignment counts. So a file carrying a blank    #
#     preferred key beside a complete legacy pair is written on the preferred    #
#     pair — and because resolution is pair-wise, that half-set preferred pair   #
#     loses to the complete legacy one. The value the owner just set is IGNORED. #
#                                                                              #
#     The write target is deliberately UNCHANGED (an existing file is never      #
#     re-keyed, and that rule is worth more than absorbing a half-finished       #
#     update). What the command now does is SAY SO, naming the key still         #
#     missing. Every shape below therefore asserts BOTH halves — the key the      #
#     value landed on, and what a later resolution returns. Asserting only the    #
#     first is how this edge survived a review.                                  #
# --------------------------------------------------------------------------- #

#: The id a one-sided update supplies. Distinctive so a resolution result cannot match it by
#: accident.
ONE_SIDED_ID = "one_sided_new_id"

#: What a shape whose one-sided update leaves NOTHING resolvable expects from
#: ``get_read_credentials()``. It used to be the ``("", "")`` sentinel; LD-580 retired that
#: return in favour of the typed refusal the write half already raised, so the table's
#: "what resolution returns afterwards" column carries this marker instead. The row's real
#: claim — *the value that was just written does not take effect* — is unchanged.
_REFUSES = "LarkConfigError"

#: The six shapes a ``.env`` can present to a one-sided ``--appId`` update:
#: ``(label, file body — ``None`` for a file that does not exist yet, the pair the value must
#: land on, what ``get_read_credentials()`` returns afterwards (or :data:`_REFUSES`), the key
#: the notice must name — ``None`` when the value does take effect and there is nothing to
#: report)``.
_ONE_SIDED_SHAPES = (
    (
        "fresh file (nothing on disk yet — the documented onboarding path)",
        None,
        READ_ENV,
        _REFUSES,
        READ_ENV[1],
    ),
    (
        "preferred-only, valued",
        f"{READ_ENV[0]}=m_id\n{READ_ENV[1]}=m_sec\n",
        READ_ENV,
        (ONE_SIDED_ID, "m_sec"),
        None,
    ),
    (
        "legacy-only, valued",
        f"{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n",
        LEGACY_ENV,
        (ONE_SIDED_ID, "l_sec"),
        None,
    ),
    (
        "blank-preferred + valued-legacy (the edge)",
        f"{READ_ENV[0]}=\n{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n",
        READ_ENV,
        ("l_id", "l_sec"),
        READ_ENV[1],
    ),
    (
        "blank-legacy + valued-preferred (the mirror)",
        f"{LEGACY_ENV[0]}=\n{READ_ENV[0]}=m_id\n{READ_ENV[1]}=m_sec\n",
        READ_ENV,
        (ONE_SIDED_ID, "m_sec"),
        None,
    ),
    (
        "both pairs valued",
        f"{READ_ENV[0]}=m_id\n{READ_ENV[1]}=m_sec\n"
        f"{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n",
        READ_ENV,
        (ONE_SIDED_ID, "m_sec"),
        None,
    ),
)

_ONE_SIDED_IDS = [label for label, *_rest in _ONE_SIDED_SHAPES]


@pytest.mark.parametrize(
    "body,target,resolved,missing",
    [(body, target, resolved, missing) for _l, body, target, resolved, missing in _ONE_SIDED_SHAPES],
    ids=_ONE_SIDED_IDS,
)
def test_a_one_sided_update_lands_on_the_file_s_own_pair_and_says_if_it_is_inert(
    tmp_path, caplog, body, target, resolved, missing
):
    """The six-shape table. Half one is the key written; half two is whether a subsequent
    resolution returns the new value; half three is that the command states the difference
    instead of leaving a value quietly inert."""
    env_path = tmp_path / ".env"
    if body is not None:
        env_path.write_text(body, encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        auth.set_env_credentials(ONE_SIDED_ID, "", str(env_path))

    # half one — which key the value landed on
    assert dotenv_values(env_path)[target[0]] == ONE_SIDED_ID, env_path.read_text(encoding="utf-8")
    # half two — and whether resolution actually returns it (or refuses, LD-580)
    if resolved is _REFUSES:
        with pytest.raises(LarkConfigError):
            auth.get_read_credentials()
    else:
        assert auth.get_read_credentials() == resolved
    # half three — stated either way, never silently
    output = caplog.text
    if missing is None:
        assert "will not take effect" not in output, output
    else:
        assert missing in output, output
        assert "will not take effect" in output, output
        assert resolved is _REFUSES or resolved[0] != ONE_SIDED_ID, (
            "a reported shape must really be inert")


@pytest.mark.parametrize(
    "body,target",
    [(body, target) for _l, body, target, _r, _m in _ONE_SIDED_SHAPES],
    ids=_ONE_SIDED_IDS,
)
def test_a_one_sided_update_never_re_keys_and_never_migrates(tmp_path, body, target):
    """The no-re-key rule holds in the one-sided shape too: the set of credential keys a file
    assigns is exactly what it was, so nothing is migrated, added or dropped — the update only
    fills a key that is already there (a fresh file gets the preferred pair from the stub)."""
    env_path = tmp_path / ".env"
    if body is not None:
        env_path.write_text(body, encoding="utf-8")
    before = _credential_keys(env_path) if body is not None else set(READ_ENV)

    auth.set_env_credentials(ONE_SIDED_ID, "", str(env_path))

    assert _credential_keys(env_path) == before, env_path.read_text(encoding="utf-8")
    assert target[0] in before


def test_the_blank_preferred_edge_names_the_missing_key_and_echoes_no_value(tmp_path, caplog):
    """The sharpest shape, spelled out: a blank preferred id beside a complete legacy pair.
    The write stays on the preferred pair — that is the scheme the file presents, and it is
    never re-keyed — the legacy half is left byte-for-byte alone, resolution still returns the
    legacy values, and the command says the new value will not take effect until the named
    partner key is set. Names only: no credential value is echoed."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"{READ_ENV[0]}=\n{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n"
    , encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        auth.set_env_credentials(ONE_SIDED_ID, "", str(env_path))

    values = dotenv_values(env_path)
    assert values[READ_ENV[0]] == ONE_SIDED_ID
    assert READ_ENV[1] not in values, "the missing partner key is not invented for the owner"
    assert values[LEGACY_ENV[0]] == "l_id" and values[LEGACY_ENV[1]] == "l_sec"
    assert auth.get_read_credentials() == ("l_id", "l_sec")

    output = caplog.text
    assert READ_ENV[1] in output and "will not take effect" in output, output
    assert ONE_SIDED_ID not in output, "the notice states key names, never a value"


def test_the_mirror_shape_takes_effect_so_nothing_alarming_is_reported(tmp_path, caplog):
    """The mirror: a blank legacy id beside a complete preferred pair. Same write target, but
    the preferred pair stays complete, so the value DOES take effect — and a command that
    warned here would be crying wolf on a correct update."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"{LEGACY_ENV[0]}=\n{READ_ENV[0]}=m_id\n{READ_ENV[1]}=m_sec\n"
    , encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        auth.set_env_credentials(ONE_SIDED_ID, "", str(env_path))

    assert dotenv_values(env_path)[READ_ENV[0]] == ONE_SIDED_ID
    assert dotenv_values(env_path)[LEGACY_ENV[0]] == ""
    assert auth.get_read_credentials() == (ONE_SIDED_ID, "m_sec")
    assert "will not take effect" not in caplog.text, caplog.text


def test_a_completed_pair_stops_reporting_the_gap(tmp_path, caplog):
    """The notice is a state, not a scold: supply the missing half and the second run is
    silent about it — so the message tells the owner what to do and then stops."""
    env_path = tmp_path / ".env"
    env_path.write_text(f"{READ_ENV[0]}=\n{LEGACY_ENV[0]}=l_id\n{LEGACY_ENV[1]}=l_sec\n", encoding="utf-8")

    auth.set_env_credentials(ONE_SIDED_ID, "", str(env_path))
    # Only the SECOND run is under test. ``caplog`` captures for the whole test item, not just
    # the ``with`` block, so the first run's (correct) notice has to be dropped or this reads
    # as a false failure whenever an earlier test left the shared logger at INFO.
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        auth.set_env_credentials("", "the_partner_secret", str(env_path))

    assert "will not take effect" not in caplog.text, caplog.text
    assert auth.get_read_credentials() == (ONE_SIDED_ID, "the_partner_secret")


#: ``(label, file body, the pair being written, the key the gap check must report)`` — the
#: seam under the notice, exercised directly.
#:
#: **The legacy leg used to be an asymmetry, and the reason it was one is preserved here:** the
#: legacy pair is the LAST resort, so a half-set legacy pair was still exactly what resolution
#: returned, and claiming the value would be ignored there would have been a new falsehood.
#: LD-580 made ``get_read_credentials`` refuse rather than hand back a half pair, so the reason
#: stands and only its conclusion is superseded — the value now really is inert, and the honest
#: answer is to report it. The asymmetry that remains is the one below it: a pair with **neither**
#: half set is hiding nothing.
_GAP_CASES = (
    ("preferred pair, partner missing", f"{READ_ENV[0]}=id\n", READ_ENV, READ_ENV[1]),
    ("preferred pair, partner blank", f"{READ_ENV[0]}=id\n{READ_ENV[1]}=\n", READ_ENV, READ_ENV[1]),
    (
        "preferred pair, complete",
        f"{READ_ENV[0]}=id\n{READ_ENV[1]}=sec\n",
        READ_ENV,
        None,
    ),
    (
        "legacy pair, partner blank — resolution refuses now, so the value really is inert",
        f"{LEGACY_ENV[0]}=id\n{LEGACY_ENV[1]}=\n",
        LEGACY_ENV,
        LEGACY_ENV[1],
    ),
    (
        "preferred pair, neither half set — nothing is hidden yet",
        f"{READ_ENV[0]}=\n{READ_ENV[1]}=\n",
        READ_ENV,
        None,
    ),
)


@pytest.mark.parametrize(
    "body,names,expected",
    [(body, names, expected) for _l, body, names, expected in _GAP_CASES],
    ids=[label for label, *_rest in _GAP_CASES],
)
def test_the_gap_check_reports_only_a_pair_resolution_would_skip(tmp_path, body, names, expected):
    env_path = tmp_path / ".env"
    env_path.write_text(body, encoding="utf-8")

    assert auth.unresolved_pair_gap(str(env_path), names) == expected


def test_the_gap_check_is_silent_on_a_file_that_is_not_there(tmp_path):
    """Nothing is set, so nothing is being hidden — a path with no file is not a place to start
    guessing (and the persistence path never reaches it: the stub is written first)."""
    assert auth.unresolved_pair_gap(str(tmp_path / "nope" / ".env"), READ_ENV) is None


#: The claim that was false. ``env_credential_pair`` promised that "a value never lands on a
#: key the resolution order would ignore" — and in the blank-preferred shape above it does
#: exactly that. A ratchet against the sentence returning: it reads as correct to anyone
#: editing nearby, which is why it was written in the first place.
_RETIRED_OVERCLAIM = "a value never lands on a key the resolution order would ignore"


def test_the_write_target_no_longer_claims_a_value_is_always_resolved():
    """The honesty requirement: either the claim becomes true or the claim goes. The write
    target is unchanged — so the claim goes, and what remains describes the guarantee the
    function really makes plus where the exception is reported."""
    source = pathlib.Path(auth.__file__).read_text(encoding="utf-8")
    assert _RETIRED_OVERCLAIM not in source, "the retired overclaim is back in the module"

    doc = inspect.getdoc(auth.env_credential_pair) or ""
    assert "never re-keyed" in doc, "the surviving guarantee has to be stated"
    assert "unresolved_pair_gap" in doc, (
        "the docstring must point at where the incomplete-pair case is reported, or the "
        "exception is undocumented again"
    )


def test_the_persistence_docstring_documents_the_incomplete_pair_notice():
    """``set_env_credentials`` is public API, so what it prints in the awkward case belongs in
    its own docstring — not only in the code that prints it."""
    doc = inspect.getdoc(auth.set_env_credentials) or ""
    assert "will not take effect" in doc or "does not take effect" in doc, doc
    assert "incomplete" in doc.lower(), doc


# --------------------------------------------------------------------------- #
# 4. File hygiene — idempotence, newlines, permissions, and no echoed secret   #
# --------------------------------------------------------------------------- #

def test_the_bootstrap_is_idempotent(tmp_path):
    """Running the command twice must not duplicate a key or corrupt the file: the second run
    is byte-identical to the first, and each key appears exactly once."""
    env_path = tmp_path / ".env"

    auth.set_env_credentials("id_1", "sec_1", str(env_path))
    once = env_path.read_text(encoding="utf-8")
    auth.set_env_credentials("id_1", "sec_1", str(env_path))
    twice = env_path.read_text(encoding="utf-8")

    assert twice == once
    for name in READ_ENV:
        assert twice.count(f"{name}=") == 1, twice
    assert dotenv_values(env_path)[READ_ENV[0]] == "id_1"


def test_a_rewrite_emits_no_carriage_returns(tmp_path):
    """A credential file is not the place to start emitting CRLF."""
    env_path = tmp_path / ".env"

    auth.set_env_credentials("id", "sec", str(env_path))

    # The raw bytes, so no newline translation can hide a CR (LD-687: ``read_text(newline=)``
    # is 3.13+; bytes are the stricter check on every interpreter).
    assert b"\r" not in env_path.read_bytes()


def test_a_private_credential_file_stays_private(tmp_path):
    """An owner who chmod'ed their ``.env`` to 0600 must not have it widened by a rewrite."""
    env_path = tmp_path / ".env"
    env_path.write_text(f"{READ_ENV[0]}=old\n{READ_ENV[1]}=old\n", encoding="utf-8")
    env_path.chmod(0o600)

    auth.set_env_credentials("id", "sec", str(env_path))

    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_no_secret_value_is_logged_by_the_persistence_path(tmp_path, caplog):
    """This is the one code path that handles a secret. Names may be logged; values may not."""
    env_path = tmp_path / ".env"

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        auth.set_env_credentials("some_app_id", SENTINEL_SECRET, str(env_path))

    assert SENTINEL_SECRET not in caplog.text


def test_the_config_command_echoes_no_secret_value(tmp_path, caplog):
    """Through the real click ring: the command reports the resolved credentials, and the
    secret is masked. The ``.env`` it writes is a temporary one — the repository's own is
    never touched by the suite."""
    from click.testing import CliRunner

    from larkdocio.cli import cli

    env_path = tmp_path / ".env"
    config_path = tmp_path / "config.json"

    with caplog.at_level(logging.INFO, logger="larkdocio"):
        result = CliRunner().invoke(cli, [
            "--config", str(config_path), "--env-file", str(env_path),
            "config", "--appId", "some_app_id", "--appSecret", SENTINEL_SECRET,
        ])

    assert result.exit_code == 0, result.output
    assert SENTINEL_SECRET not in result.output
    assert SENTINEL_SECRET not in caplog.text
    assert "***" in caplog.text
    # …and the file the documented onboarding path produced is on the preferred scheme.
    assert _credential_keys(env_path) == set(READ_ENV)


# --------------------------------------------------------------------------- #
# 5. The consumer-facing text agrees with what the code now does               #
# --------------------------------------------------------------------------- #

def test_the_example_env_and_the_bootstrap_agree_on_the_active_read_pair():
    """Derived, not hand-listed: whichever read pair ``.env.example`` presents as *active*
    (uncommented) is the pair the bootstrap writes. The example file is the copy-paste
    starting point, so a drift between the two is the same defect in a second place."""
    example = REPO_ROOT / ".env.example"
    active = _assigned_keys(example) & {*READ_ENV, *LEGACY_ENV}

    assert active == set(READ_ENV), (
        f"{example.name} presents {sorted(active)} as the active read pair; the bootstrap "
        f"writes {sorted(READ_ENV)}"
    )


#: The four consumer-facing documents that told a reader the command writes the legacy names,
#: with the exact claim each one made. A ratchet against the sentence coming back: the claim
#: was true of the old behavior, so it reads as correct to anyone editing nearby.
_CORRECTED_CLAIMS = (
    (".env.example", "writes\n# these two names"),
    ("README.md", "writes the legacy names"),
    ("TOOLS.md", "writes\nthe legacy credential names"),
    ("src/larkdocio/GUIDE.md", "(`larkdocio config` writes these)"),
)


@pytest.mark.parametrize("rel,claim", _CORRECTED_CLAIMS, ids=[c[0] for c in _CORRECTED_CLAIMS])
def test_no_document_says_the_command_writes_the_legacy_names(rel, claim):
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert claim not in text, f"{rel} still claims the bootstrap writes the legacy pair"


@pytest.mark.parametrize("rel", [rel for rel, _claim in _CORRECTED_CLAIMS])
def test_every_document_that_mentions_the_command_names_the_preferred_pair(rel):
    """Whoever reads about the bootstrap has to be able to see which names it produces."""
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    if "larkdocio config" not in text:
        pytest.skip(f"{rel} does not mention the command")
    assert READ_ENV[0] in text, f"{rel} describes the bootstrap without naming {READ_ENV[0]}"


def _config_help_page(columns="100"):
    """The rendered ``larkdocio config --help``, as a user sees it.

    Rendered through click's own runner rather than read off the source string: click wraps the
    command description to the terminal width, so the page a reader gets is assembled text, not
    the literal. Whitespace is flattened so a fact that happens to straddle a wrap is still one
    phrase to look for.
    """
    from click.testing import CliRunner

    from larkdocio.cli import cli

    result = CliRunner(env={"COLUMNS": columns}).invoke(
        cli, ["config", "--help"], prog_name="larkdocio"
    )
    assert result.exit_code == 0, result.output
    return result.output


#: The three facts a reader needs before running the command, each as ``(what it is, the phrase
#: the page must carry)``. Built from the name tuples so a rename cannot leave the page behind.
_HELP_FACTS = (
    ("the key the id is written to", READ_ENV[0]),
    ("the key the secret is written to", READ_ENV[1]),
    ("the legacy id it updates in place instead", LEGACY_ENV[0]),
    ("the legacy secret it updates in place instead", LEGACY_ENV[1]),
    ("that an existing file is not migrated", "never re-keyed"),
    ("that write credentials are a separate pair", "separate pair"),
)


@pytest.mark.parametrize("fact,phrase", _HELP_FACTS, ids=[f for f, _p in _HELP_FACTS])
def test_the_config_help_page_states_what_the_command_writes(fact, phrase):
    """The rendered ``--help`` is the whole manual for anyone who installed the console
    command, and it used to be silent about which keys the command touches. It now names all
    three facts: the pair the credentials are written to, that a file already on the legacy
    names is updated in place rather than re-keyed, and that write credentials are a
    separate pair (one app or two) and are never written here."""
    page = " ".join(_config_help_page().split())

    assert phrase in page, f"the config --help page does not state {fact}: {page}"


def test_the_config_help_page_carries_no_internal_dialect():
    """It is a shipped surface — the corpus the dialect guard greps includes every rendered
    ``--help`` page — so the new sentences have to read for someone holding only the wheel."""
    from consumer_text import dialect_hits

    assert dialect_hits(_config_help_page()) == []


def test_the_config_help_page_and_the_code_name_the_same_pair():
    """Derived, not duplicated: whichever pair the persistence path writes to a fresh file is
    the pair the help page advertises. A future rename that missed one of the two would leave
    the page lying, and this is what says so."""
    page = " ".join(_config_help_page().split())

    for name in READ_ENV:
        assert name in page
    # …and the pair really is what a fresh bootstrap produces (the constants alone could both
    # be wrong; this is the behavioral half).
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        env_path = pathlib.Path(tmp) / ".env"
        auth.set_env_credentials("id", "sec", str(env_path))
        assert _credential_keys(env_path) == set(READ_ENV)


# --------------------------------------------------------------------------- #
# 6. The bootstrap is OPT-OUTABLE, and the guide states what it really does    #
# --------------------------------------------------------------------------- #
# The creation half was always documented — but as "creates an empty one", which understated
# it in the caller's favour: the file is a commented template, the parent directories are made
# on the way, and the load that follows is ``override=True``, so it replaces credentials
# already present in the process environment. That last one is the sharp end and had no
# spelling in any shipped document. ``create=False`` is the additive opt-out for a caller who
# wants the load without the write; the guide correction stands on its own regardless.

def _guide_text():
    return (REPO_ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")


def _guide_init_env_paragraph():
    """The guide's own paragraph about what ``init_env`` does to a missing file.

    Located by the sentence that opens it rather than by line number, so an edit above it
    cannot silently move the target of these assertions.
    """
    text = _guide_text()
    anchor = "Three things `init_env` does"
    assert anchor in text, "the guide no longer walks what init_env does to a missing file"
    start = text.index(anchor)
    return text[start:text.index("\n### ", start)]


def test_create_is_keyword_only_and_defaults_to_true():
    """AC1. A positional third argument is a compatibility surface nobody asked for."""
    param = inspect.signature(auth.init_env).parameters["create"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is True


def test_create_cannot_be_passed_positionally(tmp_path):
    """AC1, from the caller's side: the keyword-only star is enforced, not just annotated."""
    with pytest.raises(TypeError):
        auth.init_env(str(tmp_path / ".env"), False)


def test_create_false_on_a_missing_file_makes_no_directory_and_writes_nothing(tmp_path):
    """AC3. The whole point of the opt-out: nothing on disk changes."""
    target = tmp_path / "nested" / "deeper" / ".env"

    with pytest.raises(LarkConfigError):
        auth.init_env(str(target), create=False)

    assert not target.exists()
    assert not target.parent.exists(), "create=False still ran the mkdir -p"
    assert list(tmp_path.iterdir()) == [], f"create=False wrote {list(tmp_path.iterdir())}"


def test_the_missing_file_refusal_names_the_path_and_the_pair_in_force(tmp_path):
    """AC3. A silent return, or a path that does not exist, teaches the caller nothing —
    so the refusal is the project's own ``LarkConfigError`` and it says where it looked and
    which credential pair is being resolved right now (the ``resolved_read_env`` discipline)."""
    target = tmp_path / ".env"

    with pytest.raises(LarkConfigError) as excinfo:
        auth.init_env(str(target), create=False)

    message = str(excinfo.value)
    assert str(target.resolve()) in message
    name_id, name_secret = auth.resolved_read_env()
    assert name_id in message and name_secret in message


def test_the_missing_file_refusal_echoes_no_credential_value(monkeypatch, tmp_path):
    """AC3. Same absolute as every other refusal in this module: names, never values."""
    monkeypatch.setenv(READ_ENV[0], "an-app-id")
    monkeypatch.setenv(READ_ENV[1], SENTINEL_SECRET)

    with pytest.raises(LarkConfigError) as excinfo:
        auth.init_env(str(tmp_path / ".env"), create=False)

    assert SENTINEL_SECRET not in str(excinfo.value)
    assert "an-app-id" not in str(excinfo.value)


def test_create_false_on_an_existing_file_behaves_exactly_as_create_true(monkeypatch, tmp_path):
    """AC4. With the file there, ``create`` changes nothing at all — including the
    ``override=True`` load, which is characterised here, not altered."""
    body = f"{READ_ENV[0]}=from-the-file\n{READ_ENV[1]}=also-from-the-file\n"
    outcomes = []
    for name in ("with-create", "without-create"):
        env_path = tmp_path / name / ".env"
        env_path.parent.mkdir()
        env_path.write_text(body, encoding="utf-8")
        monkeypatch.setenv(READ_ENV[0], "already-in-the-process-env")

        kwargs = {} if name == "with-create" else {"create": False}
        returned = auth.init_env(str(env_path), **kwargs)

        outcomes.append((
            pathlib.Path(returned) == env_path.resolve(),
            env_path.read_text(encoding="utf-8"),
            os.environ[READ_ENV[0]],
        ))

    assert outcomes[0] == outcomes[1]
    # …and the outcome both share is the documented one: the file won.
    assert outcomes[0][2] == "from-the-file"


def test_the_offline_stand_in_carries_the_same_signature_as_the_shipped_function(
        monkeypatch, tmp_path):
    """AC5. The stand-in is patched onto every module that binds ``init_env`` (LD-430), so a
    signature drift surfaces as an unrelated failure far from the change that caused it."""
    import guide_recipes as gr
    import larkdocio.common as common

    gr.stage(monkeypatch, tmp_path)

    assert common.init_env is not gr.REAL_INIT_ENV, "the stage did not install the stand-in"

    def shape(fn):
        """Name, kind and default per parameter — what decides whether a CALL is compatible.
        Annotations are deliberately out: the stand-in carries none, and one appearing or
        disappearing on the shipped function changes no caller."""
        return [(p.name, p.kind, p.default)
                for p in inspect.signature(fn).parameters.values()]

    assert shape(common.init_env) == shape(gr.REAL_INIT_ENV)


def test_the_guide_no_longer_calls_the_bootstrapped_file_empty():
    """AC6. Every statement moves in the same change — including the emitted log notice, which
    said the same understated thing from the other side of the wheel."""
    package = REPO_ROOT / "src" / "larkdocio"
    strays = sorted(
        str(path.relative_to(package))
        for path in package.rglob("*")
        if path.is_file() and path.suffix in (".py", ".md")
        and path.name != "CHANGELOG.md"
        and any(claim in path.read_text(encoding="utf-8", errors="ignore")
                for claim in ("creates an empty one", "Created empty"))
    )
    assert not strays, f"these shipped files still call the bootstrapped file empty: {strays}"


_GUIDE_MUST_SAY = (
    ("a commented template rather than an empty file", ("commented template",)),
    ("that missing parent directories are created too", ("parent director",)),
    ("that loading overrides the process environment", ("override", "process environment")),
    ("how to turn the creation off", ("create=False",)),
)


@pytest.mark.parametrize("what,needles", _GUIDE_MUST_SAY, ids=[c[0] for c in _GUIDE_MUST_SAY])
def test_the_guide_states_what_init_env_actually_does(what, needles):
    """AC6. The three understated facts plus the opt-out, in the paragraph a consumer reads."""
    paragraph = _guide_init_env_paragraph()
    for needle in needles:
        assert needle in paragraph, f"the guide does not say {what}: {needle!r} missing"


def test_the_guide_states_no_bare_size_for_the_bootstrap_template():
    """AC7. A count in shipped prose is derived, dated, or not stated; this one is not stated,
    and the words that replace it are held true of the code by the test below."""
    paragraph = _guide_init_env_paragraph()
    bare = re.findall(r"\d+[\s-]*(?:line|byte)s?", paragraph)
    assert bare == [], f"the guide states an unguarded template size: {bare}"


def test_the_template_really_is_a_commented_multi_line_stub():
    """AC7's other half — the derivation. "commented template, not an empty file" is a claim
    about ``BOOTSTRAP_ENV_TEMPLATE``, so it is checked against the constant instead of being
    asserted in prose: comment lines present, assignments present, more than one line."""
    lines = auth.BOOTSTRAP_ENV_TEMPLATE.splitlines()
    assert len(lines) > 1
    assert [ln for ln in lines if ln.startswith("#")], "no comment lines to call 'commented'"
    assert [ln for ln in lines if "=" in ln and not ln.startswith("#")], "no assignments"


def test_the_public_docstring_says_the_same_three_things_as_the_guide():
    """AC8. ``init_env`` is public and its docstring is in the guarded consumer corpus, so the
    correction lands in both places or in neither."""
    doc = inspect.getdoc(auth.init_env)
    for needle in ("commented template", "parent director", "create=False"):
        assert needle in doc, f"init_env's docstring does not say {needle!r}"
    assert "override" in doc.lower()
