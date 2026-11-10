"""The MISSING DIRECTION: registry -> ``.env.example`` (LD-302).

``tests/test_permissions_docs.py`` runs the membership half — every scope literal anywhere in
the repository must be one ``larkdocio.permissions`` knows. That direction cannot notice a
scope the registry knows and the **setup document never mentions**, and that is exactly what
had happened: ``.env.example`` — the file a consumer copies to ``.env`` and provisions their
Lark app from — named **4 of the registry's 9** required scopes. A consumer provisioning fresh
from it would fail every Base call.

This module is the other direction, so the two together close the loop:

* every scope a shipped operation REQUIRES is named in ``.env.example``, or is named here in an
  exclusion list that carries its reason (the same standard the registry holds itself to for an
  empty requirement);
* each one sits under the credential pair the registry assigns it to, not in a flat list;
* the one ``documented-unverified`` candidate keeps its candidate framing — the library never
  widens, requests or escalates a scope, and telling a consumer to grant a scope Lark has never
  been observed to demand is that failure in prose form.

The single source is unchanged: a requirement is authored only in ``larkdocio.permissions``;
``.env.example``'s scope names are references, and the membership guard proves each is a scope
the registry knows.
"""

import pathlib
import re

from larkdocio import permissions as perm

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

#: The scope literal pattern, re-used from the sibling guard so the two read the same strings.
from test_permissions_docs import SCOPE_LITERAL  # noqa: E402  (after REPO_ROOT for clarity)

#: Scopes the registry KNOWS that ``.env.example`` deliberately does not ask a consumer to
#: grant — each with the reason, because an exclusion without a stated reason is
#: indistinguishable from an oversight.
EXCLUDED_FROM_ENV_EXAMPLE = {
    "directory:employee:list": (
        "a captured DENIAL string, not a requirement: no shipped operation calls the endpoint "
        "that demanded it. The registry keeps the denial as evidence; a setup document that "
        "listed it would be asking for a grant nothing needs."
    ),
    "directory:employee:read": (
        "a captured DENIAL string only, as above — kept as evidence of what Lark asked for on "
        "a route this library does not use."
    ),
    "contact:group:readonly": (
        "a captured DENIAL string only, as above — no shipped operation reads contact groups."
    ),
    "admin:app.info:readonly": (
        "a captured DENIAL string only, from an admin route probed during the credential "
        "spike; nothing shipped calls it."
    ),
    "application:application:self_manage": (
        "a captured DENIAL string only, from the self-inspection route probed during the "
        "credential spike; nothing shipped calls it, and self-management is not a thing this "
        "library does."
    ),
}


def _required_scopes():
    """``{scope string: {credential modes}}`` — every scope a shipped operation REQUIRES.

    Derived from the registry's one hand-listed table, so a scope added there tomorrow is
    demanded of the setup document with no second list to update.
    """
    required = {}
    for _prefix, mode, scopes, _reason in perm.ENDPOINT_SCOPES:
        for scope in scopes:
            required.setdefault(scope.scope, set()).add(mode)
    return required


def _env_text():
    return ENV_EXAMPLE.read_text(encoding="utf-8")


def _section(header, text):
    """The body of one ``── <header> …`` block: from its heading to the next heading."""
    start = text.index(header)
    rest = text[start + len(header):]
    match = re.search(r"^# ──", rest, re.MULTILINE)
    return rest[: match.start()] if match else rest


READ_HEADER = "# ── Read credentials"
WRITE_HEADER = "# ── Write credentials"


def test_every_scope_the_registry_REQUIRES_is_named_in_env_example():
    """The direction ``test_permissions_docs`` cannot run.

    A convenience copy missing five of nine is not a copy — and nothing was red.
    """
    text = _env_text()
    missing = [scope for scope in sorted(_required_scopes())
               if scope not in text and scope not in EXCLUDED_FROM_ENV_EXAMPLE]
    assert not missing, (
        "the registry requires these scopes but the file a consumer provisions from never "
        f"names them: {missing}")


def test_every_scope_the_registry_KNOWS_is_either_named_or_EXCLUDED_WITH_A_REASON():
    """The whole known set, so a denial-only string cannot quietly become an unexplained gap."""
    text = _env_text()
    known = {scope.scope
             for _prefix, _mode, scopes, _reason in perm.ENDPOINT_SCOPES
             for scope in scopes}
    known |= {denial.scope for denial in perm.OBSERVED_DENIALS}
    unaccounted = [scope for scope in sorted(known)
                   if scope not in text and scope not in EXCLUDED_FROM_ENV_EXAMPLE]
    assert not unaccounted, (
        "these scopes are known to the registry but are neither named in .env.example nor "
        f"excluded with a reason here: {unaccounted}")


def test_each_exclusion_carries_a_REAL_reason_and_is_required_by_NOTHING():
    required = _required_scopes()
    for scope, reason in EXCLUDED_FROM_ENV_EXAMPLE.items():
        assert reason and len(reason) > 40, f"{scope} is excluded without a real reason"
        assert scope not in required, (
            f"{scope} is excluded from the setup document but a shipped operation REQUIRES it "
            "— a consumer provisioning from the file would fail that call")


def test_each_named_scope_sits_under_the_credential_pair_the_registry_ASSIGNS_it():
    """Not a flat list at the bottom: the READ app's scopes under the READ pair, the WRITE
    app's under the WRITE pair. A consumer provisions two apps, and a scope in the wrong block
    is a scope granted to the wrong one."""
    text = _env_text()
    # Matched as whole literals, not substrings: ``bitable:app`` occurs inside
    # ``bitable:app:readonly`` and ``docx:document`` inside ``docx:document:readonly``, so a
    # naive ``in`` reports every write scope as also present under the READ pair.
    read_body = set(SCOPE_LITERAL.findall(_section(READ_HEADER, text)))
    write_body = set(SCOPE_LITERAL.findall(_section(WRITE_HEADER, text)))
    offenders = []
    for scope, modes in sorted(_required_scopes().items()):
        in_read, in_write = scope in read_body, scope in write_body
        if modes == {"read"} and not (in_read and not in_write):
            offenders.append(f"{scope}: read-only scope, read={in_read} write={in_write}")
        elif modes == {"write"} and not (in_write and not in_read):
            offenders.append(f"{scope}: write scope, read={in_read} write={in_write}")
        elif modes == {"*"} and not (in_read or in_write):
            offenders.append(f"{scope}: either-pair scope, named under neither")
    assert not offenders, f"scopes named under the wrong credential pair: {offenders}"


def test_no_scope_is_named_OUTSIDE_the_two_credential_blocks():
    """The flat-list-at-the-bottom failure, stated as a rule rather than trusted."""
    text = _env_text()
    inside = _section(READ_HEADER, text) + _section(WRITE_HEADER, text)
    outside = [hit for hit in SCOPE_LITERAL.findall(text)
               if SCOPE_LITERAL.findall(inside).count(hit) < SCOPE_LITERAL.findall(text).count(hit)]
    assert not outside, (
        f"these scope names appear outside the READ/WRITE credential blocks: {sorted(set(outside))}")


def test_the_documented_unverified_candidate_keeps_its_CANDIDATE_framing():
    """``board:whiteboard:node:read`` is ``documented-unverified``: the registry's own words are
    *"a CANDIDATE, not a confirmed requirement — try it if the image download is denied, and
    read the denial body"*. The library never widens, requests or escalates a scope, so the
    setup document must not launder the candidate into a requirement."""
    candidates = [scope.scope
                  for _prefix, _mode, scopes, _reason in perm.ENDPOINT_SCOPES
                  for scope in scopes
                  if not scope.established]
    assert candidates, "the registry carries no candidate scope — this guard's premise moved"
    text = _env_text()
    for scope in candidates:
        assert scope in text, f"{scope} is not named in the setup document at all"
        bullet = _bullet_containing(text, scope)
        assert "CANDIDATE" in bullet, (
            f"{scope} is named without its candidate framing; the bullet reads: {bullet!r}")
        assert "not a confirmed requirement" in bullet, (
            f"{scope}'s bullet must carry the registry's own qualifier: {bullet!r}")
        assert "documented-unverified" in bullet, (
            f"{scope}'s bullet must name its verification label: {bullet!r}")
        assert "denial body" in bullet, (
            f"{scope}'s bullet must tell the consumer to read Lark's own denial body, which is "
            f"what names a real requirement: {bullet!r}")


def _bullet_containing(text, needle):
    """The ``*``-bullet (with its continuation lines) that names ``needle``."""
    lines = text.splitlines()
    index = next(n for n, line in enumerate(lines) if needle in line)
    start = index
    while start > 0 and not lines[start].lstrip("# ").startswith("* "):
        start -= 1
    end = index + 1
    while end < len(lines):
        stripped = lines[end].lstrip("# ")
        if stripped.startswith("* ") or not lines[end].startswith("#"):
            break
        end += 1
    return "\n".join(lines[start:end])


#: The vocabulary the file itself uses to state a consequence. Deliberately broader than one
#: phrasing: the contacts bullet says the run "GRACEFULLY DEGRADES … to the raw ``@ou_id``",
#: which states the loss as plainly as "without it" does.
LOSS_WORDS = ("without", "unset", "degrade", "missing scope", "fails", "cannot")


def test_each_added_scope_says_what_it_BUYS_and_what_is_LOST_without_it():
    """The registry states a consequence per scope (``note``); the setup document is only useful
    if it carries one too — a bare scope name tells a consumer nothing about the cost of
    skipping it.

    Candidate (non-``established``) scopes are exempt: there is no established loss to state,
    and their framing is governed by the candidate guard above instead.
    """
    text = _env_text()
    candidates = {scope.scope
                  for _prefix, _mode, scopes, _reason in perm.ENDPOINT_SCOPES
                  for scope in scopes if not scope.established}
    thin = []
    for scope in sorted(_required_scopes()):
        if scope not in text or scope in candidates:
            continue
        bullet = _bullet_containing(text, scope).lower()
        if not any(word in bullet for word in LOSS_WORDS):
            thin.append(scope)
    assert not thin, (
        "these scopes are named with no statement of what is lost without them: "
        f"{thin}")


def test_the_setup_document_still_points_at_the_SINGLE_SOURCE():
    """The additions are references. The file must keep sending a reader to the one place a
    requirement is authored — otherwise nine names read as authoritative instead of four."""
    text = _env_text()
    assert "larkdocio.permissions" in text
    assert "permission registry" in text


def test_the_mention_ceiling_RAISE_is_STATED_rather_than_absorbed():
    """LD-302 AC4. The sibling guard's ratchet has no slack, so five new references move it —
    and the file's own ceremony is that a raise is written down with its delta, its file and
    why each new mention is a reference rather than an authored requirement (the ``+6
    preflight`` and ``+3 LD-188`` comments are the precedents). An absorbed bump is the failure
    this asserts against."""
    source = (REPO_ROOT / "tests" / "test_permissions_docs.py").read_text(encoding="utf-8")
    head, _, _tail = source.partition("MAX_MENTIONS_OUTSIDE_THE_SINGLE_SOURCE =")
    comment = head[head.rindex("#: The count that measures"):]
    assert "38 -> 43" in comment, (
        "the ceiling raise must name its exact delta, as the +6 and +3 raises before it did")
    assert ".env.example" in comment, "the raise must name which file grew"
    assert "LD-302" in comment, "the raise must name the change that made it"
