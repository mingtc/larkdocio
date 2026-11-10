"""THE FOLDER-GRANT REFUTATION, ON THE ACCESS SURFACE (LD-500).

``OBJECT_TYPE_UNSUPPORTED`` used to tell every caller that *"permissions on a container are not
measured here at all, so nothing about them is claimed"*. On **2026-08-17** the container
question was asked, carefully, and the answer came back the other way: a grant addressed to
``drive/v1/permissions/<token>/members?type=folder`` answered **HTTP 403 · `1063002`** on
**three enumerated write spellings**.

This module holds the supersession (``process/doctrine/supersession.md`` § A.1) in place:

* the **reason** survives untouched and still governs ``file``, ``wiki`` and every other value —
  an unmeasured type is refused locally rather than guessed onto the wire;
* only the **conclusion about ``folder``** moved, and it moved to a claim bounded by its
  evidence's scope (``process/doctrine/negative-claims.md`` § A.1);
* the claim is **exactly "Lark refused the write"** and never *"the grant did not store"* —
  because this tenant has **no folder member-read oracle at all**, so the read that would tell
  those two readings apart never existed;
* **nothing was widened**: ``folder`` is still refused locally, before any call is spent.
"""
import ast
import importlib
import json
import pathlib
import pkgutil
import re

import pytest

import larkdocio
from larkdocio.drive import access
from larkdocio.drive.access import (
    ABSENCES,
    OBJECT_TYPES_MEASURED,
    OBJECT_TYPE_UNSUPPORTED,
    AccessRefusedError,
)

import access_fixtures as afx
from larkdocio.drive.access_write import DriveAccessWriteClient


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

DOC = afx.DOC
GRANTEE = afx.GRANTEE_OPEN_ID


def client(route, **kwargs):
    transport = afx.RecordingTransport(route)
    kwargs.setdefault("token_fetcher", afx.token_fetcher)
    kwargs.setdefault("rate_limiter", afx.fast_limiter())
    return DriveAccessWriteClient("app-id", "app-secret", urlopen=transport, **kwargs), transport


# --------------------------------------------------------------------------- #
# AC1 — the shipped container sentence states the measurement, scoped.          #
# --------------------------------------------------------------------------- #

#: The clause that is superseded. Its ABSENCE is half the criterion; the other half is that
#: what replaced it carries the measurement's own scope on its face.
SUPERSEDED_CLAUSE = "permissions on a container are not measured here at all"


@pytest.mark.conformance
def test_ac1_the_SUPERSEDED_CLAUSE_no_longer_ships():
    assert SUPERSEDED_CLAUSE not in OBJECT_TYPE_UNSUPPORTED
    assert "nothing about them is claimed" not in OBJECT_TYPE_UNSUPPORTED


@pytest.mark.conformance
def test_ac1_the_refusal_states_the_MEASURED_REFUSAL_for_folder():
    text = OBJECT_TYPE_UNSUPPORTED
    lowered = text.lower()
    assert "403" in text, "the status Lark answered with"
    assert "1063002" in text, "Lark's own code, relayed rather than paraphrased"
    assert "permission denied" in lowered, "Lark's own message"
    assert "three enumerated write spellings" in lowered
    for spelling in ("full_access", "need_notification", "view"):
        assert spelling in lowered, f"the {spelling} spelling is not enumerated"


@pytest.mark.conformance
@pytest.mark.parametrize("element, needle", [
    ("the date", "2026-08-17"),
    ("one tenant", "one tenant"),
    ("one application identity", "one application identity"),
    ("the token kind (the WRITE pair)", "tenant_access_token"),
    ("the write pair", "write pair"),
    ("the route", "permissions/<token>/members?type=folder"),
])
def test_ac1_the_claim_carries_ITS_OWN_SCOPE_on_its_face(element, needle):
    """A negative claim's scope may not exceed its evidence's scope, and the only way a reader
    can check that is if the claim says which axes it was measured on."""
    assert needle.lower() in OBJECT_TYPE_UNSUPPORTED.lower(), element


@pytest.mark.conformance
def test_ac1_the_UNMEASURED_AXES_are_named_rather_than_left_implied():
    lowered = OBJECT_TYPE_UNSUPPORTED.lower()
    assert "nothing is refuted" in lowered
    for axis in ("date", "tenant", "application identity", "token kind", "route", "spelling"):
        assert axis in lowered, axis


# --------------------------------------------------------------------------- #
# AC2 — the claim is EXACTLY "Lark refused the write", and the oracle is gone.  #
# --------------------------------------------------------------------------- #

#: Every phrasing that would presuppose a read that never happened. The difference between
#: *refused* and *stored but invisible* is exactly what this tenant cannot answer.
FORBIDDEN_PHRASINGS = (
    "did not store", "was not stored", "was not saved", "did not save",
    "failed to save", "not persisted", "did not persist", "was not persisted",
    "stored=false", "nothing was stored",
)


@pytest.mark.conformance
@pytest.mark.parametrize("forbidden", FORBIDDEN_PHRASINGS)
def test_ac2_the_claim_NEVER_presupposes_the_read_that_never_happened(forbidden):
    assert forbidden not in OBJECT_TYPE_UNSUPPORTED.lower(), (
        f"{forbidden!r} claims a read this tenant has no route for")


@pytest.mark.conformance
def test_ac2_the_claim_IS_that_LARK_REFUSED_THE_WRITE():
    lowered = OBJECT_TYPE_UNSUPPORTED.lower()
    assert "lark refused the write" in lowered
    assert "failed to store" in lowered, (
        "the sentence must say what it is NOT claiming, not merely omit it")


@pytest.mark.conformance
def test_ac2_the_MISSING_ORACLE_is_stated_with_the_routes_own_enum():
    lowered = OBJECT_TYPE_UNSUPPORTED.lower()
    assert "does not exist on that tenant" in lowered, "the oracle's absence is the whole reason"
    assert "99992402" in lowered
    assert "field_violations" in lowered
    for member in ("doc", "sheet", "file", "wiki", "bitable", "docx",
                   "mindnote", "minutes", "slides"):
        assert member in lowered, f"the route's own type enum omits {member}"
    assert "does not contain folder" in lowered


@pytest.mark.conformance
def test_ac2_BOTH_contradictory_bodies_ship_and_NEITHER_is_reconciled_away():
    lowered = OBJECT_TYPE_UNSUPPORTED.lower()
    assert "type is required" in lowered, "the second, contradicting body"
    assert "contradict each other" in lowered
    assert "neither was reconciled away" in lowered


# --------------------------------------------------------------------------- #
# AC3 — the REASON survives, and still governs every other type.                #
# --------------------------------------------------------------------------- #

#: The rule sentence that is NOT superseded. It is quoted here verbatim: this is the executable
#: memory of why the surface refuses an unmeasured value at all.
THE_RULE_THAT_SURVIVES = (
    "Unmeasured is not impossible — extending the surface to one of them needs its own "
    "measurements, and the refusal says so."
)


@pytest.mark.conformance
def test_ac3_the_rule_that_grounds_every_local_refusal_STILL_SHIPS():
    assert THE_RULE_THAT_SURVIVES in OBJECT_TYPES_MEASURED
    assert OBJECT_TYPES_MEASURED in ABSENCES, "still carried as data, not scattered prose"


@pytest.mark.conformance
def test_ac3_file_and_wiki_are_STILL_UNMEASURED_not_impossible():
    assert "STILL UNMEASURED, and therefore refused locally by name rather than sent: file, " \
        "wiki and every other type= value" in OBJECT_TYPES_MEASURED
    lowered = OBJECT_TYPE_UNSUPPORTED.lower()
    assert "unmeasured on this family, not proven impossible" in lowered


@pytest.mark.conformance
def test_ac3_ONLY_folder_moved_out_of_the_unmeasured_list():
    """The list that names what is still refused for want of a measurement no longer names
    ``folder`` — and the sentence that says where ``folder`` went is in the same paragraph, so
    a reader cannot read the removal as a silent strike."""
    still_unmeasured = OBJECT_TYPES_MEASURED.split("STILL UNMEASURED", 1)[1]
    listed = still_unmeasured.split("Unmeasured is not impossible", 1)[0]
    assert "file" in listed and "wiki" in listed
    assert "folder" not in listed
    assert "FOLDER IS THE ONE THAT IS NO LONGER UNMEASURED" in OBJECT_TYPES_MEASURED
    assert "1063002" in OBJECT_TYPES_MEASURED


@pytest.mark.conformance
def test_ac3_the_module_records_the_SUPERSESSION_and_its_doctrine_in_the_SOURCE():
    """The issue id lives in the module's own comment, never in the shipped sentence — a
    consumer holds only the wheel, where an issue id resolves to nothing."""
    source = pathlib.Path(access.__file__).read_text(encoding="utf-8")
    assert "LD-500" in source and "supersession" in source
    assert "negative-claims" in source
    assert "LD-500" not in OBJECT_TYPE_UNSUPPORTED
    assert "LD-494" not in OBJECT_TYPE_UNSUPPORTED


# --------------------------------------------------------------------------- #
# AC4 — NOTHING IS WIDENED. The refusal is better-evidenced, not weaker.        #
# --------------------------------------------------------------------------- #

def test_ac4_a_folder_grant_is_STILL_refused_LOCALLY_and_spends_NO_call():
    route = afx.access_router()          # every branch of this router asserts if reached
    access_client, transport = client(route)
    with pytest.raises(AccessRefusedError) as excinfo:
        access_client.grant_access(DOC, open_id=GRANTEE, obj_type="folder")
    message = str(excinfo.value)
    assert "folder" in message
    assert "LARK REFUSED THE WRITE" in message, "the refusal now carries its evidence"
    assert transport.calls == [], "a refused type spends no call"
    assert access_client.api_calls == 0


@pytest.mark.parametrize("verb", ["grant_access", "update_access", "revoke_access",
                                  "list_members"])
def test_ac4_the_WHOLE_write_family_still_refuses_folder_before_any_call(verb):
    access_client, transport = client(afx.access_router())
    kwargs = {"obj_type": "folder"}
    if verb != "list_members":
        kwargs["open_id"] = GRANTEE
    with pytest.raises(AccessRefusedError):
        getattr(access_client, verb)(DOC, **kwargs)
    assert transport.calls == []


def test_ac4_no_folder_value_can_reach_the_wire_from_the_TYPE_MAP():
    """The widening this measurement refutes would show up here first: a ``folder`` entry in
    the type vocabulary the surface is willing to send."""
    from larkdocio.drive.access import WIRE_OBJECT_TYPES

    assert "folder" not in WIRE_OBJECT_TYPES
    assert "file" not in WIRE_OBJECT_TYPES and "wiki" not in WIRE_OBJECT_TYPES


# --------------------------------------------------------------------------- #
# AC6 — THE CENSUS, taken BOTH WAYS (the LD-480 lesson).                        #
#                                                                              #
# Source text catches what only exists as text (a comment, a document); values  #
# catch what only exists once assembled (an implicit concatenation, an          #
# import-time composition). Neither reading is a superset of the other.         #
# --------------------------------------------------------------------------- #

#: A surviving assertion that container permissions are UNMEASURED. Each pattern is the
#: superseded conclusion in a shape it could plausibly be re-written in.
CONTAINER_UNMEASURED_CLAIM = (
    re.compile(r"permissions?\s+on\s+a\s+container", re.I),
    re.compile(r"container[^.]{0,40}\b(?:are|is)\s+not\s+measured", re.I),
    re.compile(r"container\s+permissions[^.]{0,60}unmeasured", re.I),
    # The folder half, kept PERMISSION-SPECIFIC on purpose: a folder is also an upload
    # destination and a name-length subject, and an unmeasured claim about either of those is
    # not this supersession's business (a census that reddens on them teaches people to widen
    # the exclusions instead of fixing the claim).
    re.compile(r"\bfolder\b[^.]{0,40}(?:stay|stays|remain|remains|is|are)\s+(?:still\s+)?"
               r"unmeasured\s+rather\s+than\s+impossible", re.I),
    re.compile(r"\bfolder\b[^.]{0,80}(?:grant|permission|member)[^.]{0,60}"
               r"(?:unmeasured|not\s+measured|never\s+(?:exercised|measured|tried))", re.I),
    re.compile(r"(?:grant|permission|member)[^.]{0,80}\bfolder\b[^.]{0,60}"
               r"(?:unmeasured|not\s+measured|never\s+(?:exercised|measured|tried))", re.I),
)

# --------------------------------------------------------------------------- #
# THE WIDENING (LD-500 fix round).                                             #
#                                                                              #
# The two folder patterns above are permission-token-*adjacent*: the token has #
# to sit within ~80 characters of ``folder`` AND inside the same sentence AND  #
# on one particular side. THREE SHIPPED SITES asserted folder-is-unmeasured    #
# without that adjacency — GUIDE.md's "WHICH OBJECT TYPES" paragraph,          #
# README.md's ``drive/`` layout row and DRIVE.md's shipped-grant row — and the #
# census read all three as clean and reported "zero survivors". A census that  #
# cannot reach a phrasing is decoration.                                       #
#                                                                              #
# The widening keeps the domain check (a folder is ALSO an upload destination, #
# a create target and a quota subject, and an unmeasured claim about any of    #
# those is not this supersession's business) but stops requiring adjacency:    #
#   * the CLAIM shape is now ``folder`` as the subject of an is-unmeasured     #
#     predicate, or ``folder`` enumerated "as unmeasured" — no token at all    #
#     inside the pattern;                                                      #
#   * the DOMAIN is a window of +/- 150 characters, either side, across        #
#     sentence and line boundaries, which is roughly a paragraph either way.   #
#                                                                              #
# Two disqualifiers are built into the shape rather than bolted on as an       #
# allow-list of files, because an allow-list is where this kind of claim goes  #
# to hide (LD-483): ``no longer`` and ``supersede`` anywhere in the gap kill   #
# the match, since "is NO LONGER unmeasured" and "supersedes the *unmeasured*  #
# conclusion" are the supersession speaking, not a survivor of it. And         #
# ``folder`` must precede the predicate, so a sentence that marks              #
# ``file``/``wiki`` unmeasured and then treats ``folder`` separately — exactly #
# what all three corrected sites now do — is not a hit.                        #
# --------------------------------------------------------------------------- #

_NOT_A_SURVIVOR = r"(?:(?!no longer|supersede)[^.]){0,60}"

FOLDER_UNMEASURED_CLAIM = (
    re.compile(r"\bfolder\b" + _NOT_A_SURVIVOR +
               r"\b(?:is|are|was|were|stay|stays|remain|remains|still)\b" + _NOT_A_SURVIVOR +
               r"\b(?:unmeasured|not\s+measured|never\s+(?:exercised|measured|tried|attempted))\b",
               re.I),
    re.compile(r"\bfolder\b" + _NOT_A_SURVIVOR +
               r"\bas\s+(?:still\s+)?(?:unmeasured|not\s+measured)\b", re.I),
)

#: The access family, by its own words. Deliberately NOT ``access`` on its own — that string is
#: inside ``tenant_access_token`` and ``full_access`` and would make the domain check vacuous.
ACCESS_FAMILY_IN_REGION = re.compile(
    r"\b(?:grant|grants|granted|granting|permission|permissions|member|members)\b", re.I)


def _region(text, index):
    """The blank-line-delimited paragraph ``index`` falls in — a Markdown table ROW, a prose
    paragraph, one stanza of a docstring. This is the domain unit: the shipped patterns asked
    for a permission word within ~80 characters on one side of ``folder``, which none of the
    three survivors had; a paragraph is where a document actually keeps its subject."""
    start = text.rfind("\n\n", 0, index)
    start = 0 if start < 0 else start + 2
    end = text.find("\n\n", index)
    return text[start:len(text) if end < 0 else end]


#: THE ONLY EXEMPTION, and it carries its reason and is pinned to the shipped text
#: (:func:`test_ac6_every_census_EXEMPTION_is_REASONED_and_still_MATCHES_ITS_SHIPPED_TEXT`), so
#: it cannot become a hiding place: an entry that no longer quotes what ships reddens, and an
#: entry the patterns would not have caught anyway reddens too.
CENSUS_ALLOWED = (
    (
        "BASE.md",
        "placement into a folder that is not the default* is **unmeasured, not refuted**",
        "A DIFFERENT CLAIM ABOUT A DIFFERENT VERB. This is `copy_app`'s folder_token — where a "
        "COPIED BASE LANDS — measured only against the app's own root because a second folder "
        "could not be provisioned. It is unmeasured PLACEMENT, not an unmeasured permission, "
        "and the folder-grant refutation says nothing about it. Its paragraph mentions "
        "permissions only in passing, which is exactly why the domain check alone cannot tell "
        "the two apart.",
    ),
)


def _claim_matches(text):
    """Every hit in ``text``: the unconditional container patterns, plus the widened folder
    patterns gated on an access-family word being present in the same paragraph, minus the
    reasoned exemptions."""
    found = []
    for pattern in CONTAINER_UNMEASURED_CLAIM:
        found += [(pattern, match) for match in pattern.finditer(text)]
    for pattern in FOLDER_UNMEASURED_CLAIM:
        for match in pattern.finditer(text):
            if not ACCESS_FAMILY_IN_REGION.search(_region(text, match.start())):
                continue
            if any(match.group(0) in snippet for _, snippet, _ in CENSUS_ALLOWED):
                continue
            found.append((pattern, match))
    return found

#: The two documents the census does NOT read, and the reason is not convenience: a release
#: record is **dated history**. An entry published under a version already shipped says what was
#: claimed then; rewriting it would destroy the record instead of superseding it. Both copies —
#: the root file and the packaged one — are excluded, and the exclusion is answered by
#: :func:`test_ac6_the_DATED_RELEASE_RECORD_exclusion_is_ANSWERED_by_the_OPEN_SECTION`, so it
#: cannot become a hiding place.
DATED_RELEASE_RECORDS = ("CHANGELOG.md", "RELEASE_NOTES.md")

#: The root matrices — the maintainer registers a claim about a surface is also authored in.
ROOT_MATRICES = ("BLOCKS.md", "SHEETS.md", "BASE.md", "DRIVE.md", "PERMISSIONS.md", "README.md")


def _census_files():
    shipped = sorted((REPO_ROOT / "src/larkdocio").rglob("*.py"))
    shipped += sorted((REPO_ROOT / "src/larkdocio").rglob("*.md"))
    shipped += [REPO_ROOT / name for name in ROOT_MATRICES]
    return [p for p in shipped if p.name not in DATED_RELEASE_RECORDS]


def _folded_string_values(path):
    """Every string literal **as the interpreter sees it** — implicit concatenations folded."""
    values = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            values.append("".join(
                part.value if isinstance(part, ast.Constant) and isinstance(part.value, str)
                else " " for part in node.values))
    return values


def _runtime_string_values():
    """The values the **imported** package actually holds, plus its two published projections."""
    values = [larkdocio.guide(full=True),
              json.dumps(larkdocio.capabilities(full=True), ensure_ascii=False)]
    package = importlib.import_module("larkdocio")
    for info in pkgutil.walk_packages(package.__path__, prefix="larkdocio."):
        module = importlib.import_module(info.name)
        values.append(module.__doc__ or "")
        for name in dir(module):
            attribute = getattr(module, name, None)
            if isinstance(attribute, str):
                values.append(attribute)
            elif callable(attribute) and getattr(attribute, "__doc__", None):
                values.append(attribute.__doc__)
    return values


def test_ac6_NO_SHIPPED_TEXT_still_asserts_that_CONTAINER_PERMISSIONS_ARE_UNMEASURED():
    hits = []
    for path in _census_files():
        text = path.read_text(encoding="utf-8")
        for _, match in _claim_matches(text):
            hits.append(("source", str(path.relative_to(REPO_ROOT)),
                         text[:match.start()].count("\n") + 1, match.group(0)))
        if path.suffix == ".py":
            for value in _folded_string_values(path):
                for _, match in _claim_matches(value):
                    hits.append(("value", str(path.relative_to(REPO_ROOT)), None,
                                 match.group(0)))
    for value in _runtime_string_values():
        for _, match in _claim_matches(value):
            hits.append(("runtime", None, None, match.group(0)))
    # One sentence can be reached twice by the same reading; a survivor is a place, not a count.
    assert list(dict.fromkeys(hits)) == [], list(dict.fromkeys(hits))


def test_ac6_the_census_READS_BOTH_the_source_text_AND_the_runtime_values():
    """The guard is only worth its runtime if both readings really run — a census that
    silently degraded to one of them would go green on exactly the survivor it was built for."""
    paths = {p.name for p in _census_files()}
    assert "access.py" in paths and "GUIDE.md" in paths and "DRIVE.md" in paths
    values = _runtime_string_values()
    assert OBJECT_TYPE_UNSUPPORTED in values, "the runtime reading really holds the constant"
    folded = _folded_string_values(REPO_ROOT / "src/larkdocio/drive/access.py")
    assert OBJECT_TYPE_UNSUPPORTED in folded, "the folded reading really holds it too"


def test_ac6_the_census_BITES_on_a_reintroduced_survivor():
    """A census that cannot redden is decoration. The superseded clause, in each reading."""
    survivor = "permissions on a container are not measured here at all"
    assert any(p.search(survivor) for p in CONTAINER_UNMEASURED_CLAIM)
    assert any(p.search("`folder` and `wiki` stay unmeasured rather than impossible")
               for p in CONTAINER_UNMEASURED_CLAIM)


#: The three phrasings the shipped census could not reach, verbatim as they shipped before the
#: LD-500 fix round. Each is a place, and each is quoted here exactly once — this is the
#: executable memory of *why* the pattern set is shaped the way it is.
THE_THREE_SURVIVORS = {
    "src/larkdocio/GUIDE.md": (
        "(`folder`, `file`, `wiki`, …) is **refused locally by name** as unmeasured — not "
        "proven\nimpossible."
    ),
    "README.md": (
        "refuses locally every object type it has not measured — `folder`, `file`, `wiki` — as "
        "unmeasured rather than impossible,"
    ),
    "DRIVE.md": (
        "`folder`, `file` and `wiki` are refused **locally** as unmeasured,"
    ),
}

#: What each site says NOW — the WHOLE replacement, so restoring the survivor over it is
#: lossless in both directions. The census must be silent on all three, or the fix would be
#: unshippable and the pressure would be to widen an exclusion instead.
THE_THREE_CORRECTIONS = {
    "src/larkdocio/GUIDE.md": (
        "is **refused locally by name**: `file`, `wiki` and every other `type=` value as "
        "unmeasured —\nnot proven impossible — and `folder` on evidence rather than on silence, "
        "because on 2026-08-17\n(one tenant, one application identity, `tenant_access_token`) a "
        "grant addressed to\n`drive/v1/permissions/<token>/members?type=folder` answered **HTTP "
        "403 · `1063002` \"Permission\ndenied\"** on three enumerated write spellings. That claim "
        "is exactly *Lark refused the write*\nand nothing wider — never *the grant did not "
        "store*, because this tenant has no folder\nmember-read to tell those two apart; the "
        "refusal you get back carries the whole measurement and\nthe scope it was made in."
    ),
    "README.md": (
        "refuses locally every object type it has not measured — `file` and `wiki` as unmeasured "
        "rather than impossible, and `folder` on evidence rather than on silence: a grant sent as "
        "`type=folder` was **refused by Lark** (`403 · 1063002`, three enumerated write "
        "spellings, 2026-08-17, one tenant, one application identity, `tenant_access_token`), a "
        "claim bounded to *Lark refused the write* because that tenant has no folder member-read "
        "to say more (the shipped refusal message carries the measurement; "
        "[`DRIVE.md`](DRIVE.md) carries the row),"
    ),
    "DRIVE.md": (
        "`file` and `wiki` are refused **locally** as unmeasured; `folder` is refused **locally "
        "too, but on evidence** — it was exercised on 2026-08-17 and Lark refused the write "
        "(`403 · 1063002`, three enumerated write spellings; its own `refused-by-server` row is "
        "below),"
    ),
}


def _text_with_the_survivor_restored(site):
    """The real shipped file, with the corrected clause swapped back for the phrasing that
    survived the first census. Restoring it IN SITU is the point: the widened patterns are
    domain-gated on their surroundings, so a bare snippet would prove nothing about the file."""
    text = (REPO_ROOT / site).read_text(encoding="utf-8")
    assert THE_THREE_CORRECTIONS[site] in text, site
    return text.replace(THE_THREE_CORRECTIONS[site], THE_THREE_SURVIVORS[site], 1)


@pytest.mark.parametrize("site", sorted(THE_THREE_SURVIVORS))
def test_ac6_the_WIDENED_census_BITES_on_each_of_the_THREE_MISSED_SURVIVORS(site):
    """The shipped census reported "zero survivors" while all three of these were live. A
    pattern set that has not been watched redden on them is not evidence."""
    restored = _text_with_the_survivor_restored(site)
    hits = [m.group(0) for _, m in _claim_matches(restored)]
    assert hits, f"the census still cannot reach the survivor in {site}"
    assert any("folder" in hit.lower() for hit in hits), (site, hits)


@pytest.mark.parametrize("site", sorted(THE_THREE_SURVIVORS))
def test_ac6_ONLY_the_survivor_reddens__the_rest_of_the_file_stays_clean(site):
    """The bite above is only meaningful if the same file is silent once the correction is back
    — otherwise the census would be reddening on something else entirely."""
    clean = (REPO_ROOT / site).read_text(encoding="utf-8")
    assert [m.group(0) for _, m in _claim_matches(clean)] == [], site


@pytest.mark.parametrize("site", sorted(THE_THREE_CORRECTIONS))
def test_ac6_the_corrected_text_IS_WHAT_ACTUALLY_SHIPS(site):
    """The two dictionaries above are only worth their runtime if the second one is the real
    shipped text — otherwise this file would be testing its own fixtures."""
    text = (REPO_ROOT / site).read_text(encoding="utf-8")
    assert THE_THREE_CORRECTIONS[site] in text, site
    assert THE_THREE_SURVIVORS[site] not in text, f"{site} still ships the superseded phrasing"


@pytest.mark.parametrize("site", sorted(THE_THREE_CORRECTIONS))
def test_ac6_each_corrected_site_states_the_MEASURED_REFUSAL_rather_than_merely_dropping_folder(site):
    """Striking ``folder`` from an unmeasured list would also silence the census. The point is
    the opposite one: each site now carries the measurement, scoped — and none of them claims
    more than Lark's refusal of the write."""
    correction = THE_THREE_CORRECTIONS[site]
    assert "1063002" in correction, site
    assert "403" in correction, site
    assert "2026-08-17" in correction, site
    assert "refused the write" in correction.lower() or "refused by lark" in correction.lower()
    # A NEGATED mention is the opposite of the offence: saying *"never that the grant did not
    # store"* is the boundary being drawn, so the negation is removed before the scan and the
    # scan then insists nothing is left.
    lowered = re.sub(r"never \*[^*]*\*", "", correction.lower())
    for forbidden in FORBIDDEN_PHRASINGS:
        assert forbidden not in lowered, (site, forbidden)
    assert "wiki" in correction and "unmeasured" in correction, (
        "file/wiki stay unmeasured-not-impossible at every site")


@pytest.mark.parametrize("path, snippet, reason", CENSUS_ALLOWED)
def test_ac6_every_census_EXEMPTION_is_REASONED_and_still_MATCHES_ITS_SHIPPED_TEXT(
        path, snippet, reason):
    """The LD-483 honest-allow-list rule: an exemption carries its reason and is checked against
    the shipped text, so it cannot become a hiding place. Three things must hold — the text is
    really there, the reason is really written, and the entry is really load-bearing (a pattern
    would have caught it), because a dead entry is a place a future survivor could be filed."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    assert snippet in text, f"{path} no longer contains the exempted text — retire the entry"
    assert len(reason) > 120, "an exemption's reason is the whole price of having one"
    assert any(p.search(snippet) for p in FOLDER_UNMEASURED_CLAIM), (
        "this entry exempts nothing the census would have caught")


def test_ac6_the_exemption_list_is_the_ONLY_way_text_is_skipped():
    """Beyond the dated release records and the reasoned entries above, the census has no
    per-file skip: every shipped ``.py``/``.md`` under the package and every root matrix is read.
    """
    read = {p.resolve() for p in _census_files()}
    for path in sorted((REPO_ROOT / "src/larkdocio").rglob("*.py")) + \
            sorted((REPO_ROOT / "src/larkdocio").rglob("*.md")):
        assert path.resolve() in read or path.name in DATED_RELEASE_RECORDS, path
    assert len(CENSUS_ALLOWED) == 1, (
        "the exemption list grew — each new entry needs its own reason and its own argument")


def test_ac6_the_DATED_RELEASE_RECORD_exclusion_is_STATED_and_covers_BOTH_copies():
    excluded = [p for name in DATED_RELEASE_RECORDS
                for p in (REPO_ROOT / name, REPO_ROOT / "src/larkdocio" / name)]
    for path in excluded:
        assert path.exists(), path
        assert path not in _census_files(), (
            f"{path} is a dated release record and is excluded from the census by name")


def test_ac6_the_DATED_RELEASE_RECORD_exclusion_is_ANSWERED_by_the_OPEN_SECTION():
    """History is only honest if the correction is *published*. The exclusion is paid for by an
    entry in the notes a consumer reads — in the section this change joined, never by editing a
    cut, dated one.

    **TRANSFORMED (LD-621, ruled by D-111), and only the LOCATOR moved.** The reason above is
    untouched and every assertion below is still made: the refutation is published, in exactly
    ONE dated release section, with its code, its route and its remaining unmeasured case in the
    same entry. What expired is one premise this guard silently rested on — that the PACKAGED
    copy carries the publishing section forever. It does not, and that is DESIGNED: the packaged
    copy is a window of the newest releases (``RELEASE_NOTES_WINDOW_SECTIONS``), the window rolls
    at every cut, and this entry was written into ``[1.37.0]`` — the oldest section still inside
    it, so the next section opened evicts it with nothing edited and nothing wrong. So the
    invariant now reads the CANONICAL ROOT document, which is complete and stays complete, and
    keeps ``== 1`` there **permanently**; the wheel-facing arm is *kept for as long as it can be
    true*, exactly as
    ``test_base_table_delete_link_semantics.py``'s
    ``test_the_DATED_RELEASE_RECORD_exclusion_is_ANSWERED_by_the_PUBLISHING_SECTION`` already
    does. Deleting the refutation, scattering its parts across sections, demoting it out
    of a release section, or editing the section the packaged copy still carries all still
    redden — in both copies.
    """
    def _sections(text):
        return re.split(r"^(?=## \[\d+\.\d+\.\d+\])", text, flags=re.MULTILINE)[1:]

    notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    publishing = [s for s in _sections(notes) if "Lark refused the write" in s]
    assert len(publishing) == 1, (
        "the folder-grant refutation must be published in exactly one release section of "
        f"RELEASE_NOTES.md — found {len(publishing)}")
    section = publishing[0]
    header = section.splitlines()[0]
    assert re.match(r"^## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}$", header), header
    assert "1063002" in section
    assert "folder" in section.lower()
    assert "unmeasured" in section.lower(), "what is still unmeasured is said in the same entry"

    # The wheel-facing arm, while the window still reaches it: no separate expectation is
    # written down — the packaged copy either carries that section or the window has moved
    # past it, and only the first case is asserted.
    packaged = (REPO_ROOT / "src/larkdocio/RELEASE_NOTES.md").read_text(encoding="utf-8")
    if header in packaged:
        in_wheel = [s for s in _sections(packaged) if s.splitlines()[0] == header]
        assert len(in_wheel) == 1 and in_wheel[0] == section, (
            "the packaged copy still carries the publishing section but not verbatim — the "
            "projection must never reflow or edit a byte")
