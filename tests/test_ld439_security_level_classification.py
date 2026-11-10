"""LD-439 — the docx SECURITY LEVEL classification: readable, not settable, docs only.

**What this file guards.** LD-439 ships no library behaviour change — the AC is that a
classification (already measured in ``dev/permissions-spike/findings.md`` § *Security-level
glance*) lands in the right places, authored once, scoped to its evidence. This suite pins:

* AC1/AC2 — the ONE authored passage in the shipped guide states all four parts (exists,
  gates editing, is READABLE, is NOT SETTABLE) and the two pre-existing bare mentions of
  ``sec_label_name`` elsewhere in the guide point at it rather than re-authoring it.
* AC4 — the "not tried, and therefore not refuted" enumeration ships with the claim.
* AC5 — the copy/paste confound names its third variable.
* AC6 — the never-escalate restatement (D-15's shape).
* AC3 — DRIVE.md's two ``metas/batch_query`` rows and register row 15 carry the same facts.
* AC8 — ``requirements/DECISIONS.md`` D-76 exists and is cited from the guide/DRIVE.md side.
* AC10 — no code under ``src/larkdocio`` gained a READ of ``sec_label_name`` (a docstring
  *mention* of the key is unaffected; an attribute access or dict subscript is what this
  guards against).

One test is CONFORMANCE-tier (process/doctrine/conformance-tier.md § A.4): it pins that the
vendored Lark SDK still exposes ``sec_label*`` only on response ``Meta`` models and on no
request body anywhere in the package — the measured EXTERNAL truth the "not settable" claim
rests on. No Lark numeric HTTP code is pinned into any offline assertion (the LD-417 AC10
precedent): the 404s live in prose and in the spike's own captures, never here.
"""
import pathlib
import re

import pytest

import larkdocio
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DRIVE_MD = REPO_ROOT / "DRIVE.md"
DECISIONS_MD = REPO_ROOT / "requirements" / "DECISIONS.md"
SRC = REPO_ROOT / "src" / "larkdocio"

_SECTION_HEADING = (
    "The document's SECURITY LEVEL — readable, not settable, and it can gate an edit before "
    "you get here"
)


@pytest.fixture(scope="module")
def guide_text():
    return larkdocio.guide(full=True)


@pytest.fixture(scope="module")
def section_text():
    return larkdocio.guide(section=_SECTION_HEADING)


# --------------------------------------------------------------------------- #
# AC1 / AC2 — one authored passage, all four parts, and it is where a caller  #
# working out "why can't this person edit?" would meet it.                    #
# --------------------------------------------------------------------------- #

def test_the_classification_has_its_own_guide_heading(guide_text):
    assert f"### {_SECTION_HEADING}" in guide_text


def test_the_section_sits_beside_the_access_grant_recipe(guide_text):
    """AC2 — chosen so a reader working out an editing failure meets it: it must be the
    heading immediately after LD-432's grant-access recipe."""
    grant_heading = "### Recipe: grant a HUMAN access"
    idx = guide_text.index(grant_heading)
    next_heading = guide_text.index(f"### {_SECTION_HEADING}")
    between = guide_text[idx:next_heading]
    assert between.count("\n### ") == 0, "another heading sits between the two — not adjacent"


@pytest.mark.parametrize("needle", [
    "security level",             # (i) it exists
    "before editing is allowed",  # (ii) a tenant policy can gate an edit on a human choosing one
    "sec_label_name",             # (iii) how it is READ
    "metas/batch_query",          # (iii) the exact call
    "no request body",           # (iv) not settable — no write route
])
def test_section_states_all_four_classification_parts(section_text, needle):
    assert needle.lower() in section_text.lower(), needle


def test_section_proves_EMPTY_STRING_means_no_level_not_absence(section_text):
    """AC1(iii) — this must be a measured claim (before/after + negative control), never
    an assumption."""
    lowered = section_text.lower()
    assert "before control" in lowered
    assert "negative control" in lowered
    assert '""' in section_text or "empty" in lowered


# --------------------------------------------------------------------------- #
# AC4 — the not-tried enumeration ships with the claim.                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("needle", [
    "user_access_token",
    "admin",
    "console",
    "localised display string",
    "gates the open api",
])
def test_section_carries_the_NOT_TRIED_enumeration(section_text, needle):
    assert needle.lower() in section_text.lower(), needle


# --------------------------------------------------------------------------- #
# AC5 — the copy/paste confound names its THIRD variable, without re-litigating #
# DRIVE.md register row 14 (Out of Scope).                                     #
# --------------------------------------------------------------------------- #

def test_section_states_the_copy_paste_confound_with_its_third_variable(section_text):
    lowered = section_text.lower()
    assert "same sitting" in lowered
    assert "three" in lowered
    assert "copy_entity" in section_text or "copy entity" in lowered
    assert "may present the library's two levers as the cause" in lowered \
        or "not an attribution" in lowered


# --------------------------------------------------------------------------- #
# AC6 — the never-escalate rule restated in the same breath (D-15's shape).     #
# --------------------------------------------------------------------------- #

def test_section_restates_the_never_escalate_rule(section_text):
    lowered = section_text.lower()
    assert "never" in lowered and ("escalate" in lowered or "widen" in lowered)
    assert "console" in lowered


def test_section_never_claims_the_library_CAN_set_a_level(section_text):
    """QA's own check, restated as a guard: no sentence may say the library sets, or can
    set, a security level."""
    forbidden = re.compile(
        r"larkdocio (?:can |now )?sets? (?:a |the )?(?:security )?level"
        r"|this library sets? (?:a |the )?(?:security )?level",
        re.IGNORECASE,
    )
    assert not forbidden.search(section_text)


# --------------------------------------------------------------------------- #
# AC2 — the two pre-existing bare mentions now POINT AT the section rather    #
# than re-authoring it.                                                       #
# --------------------------------------------------------------------------- #

def test_the_bulk_form_key_list_points_at_the_new_section(guide_text):
    region_start = guide_text.index("sec_label_name`, `title` and `url`")
    region = guide_text[region_start:region_start + 800]
    assert "security level" in region.lower()
    assert "The document's SECURITY LEVEL" in region


def test_the_embedded_base_mention_points_at_the_new_section(guide_text):
    region_start = guide_text.index("**doc-owned**, and it is a distinct object class")
    region = guide_text[region_start:region_start + 400]
    assert "security level" in region.lower()
    assert "The document's SECURITY LEVEL" in region


def test_only_ONE_place_authors_the_classification(guide_text):
    """AC1's one-authoring rule — a second independently worded copy is a drift source and
    a FAIL. Cheap proxy: part iv's distinctive phrase appears exactly once in the whole guide.

    **LD-568 re-cut the proxy, and only the proxy.** The rule is unchanged and so is its
    reason: a second independently worded copy of the classification's not-settable finding is
    a drift source. What changed is that the old proxy — the bare ``no request body`` — stopped
    being distinctive: the docx-write absence register is now projected into this guide, and its
    checkbox row says ``no request body carries a done field``, a different claim about a
    different surface that happens to share four words. A proxy that fires on a true, unrelated
    sentence measures nothing, so it is narrowed to the phrase that is actually part iv's — the
    ``no request body, no PATCH`` enumeration — rather than deleted.
    """
    assert guide_text.count("no request body, no") == 1


# --------------------------------------------------------------------------- #
# AC3 — DRIVE.md: the metas rows and the new register row.                    #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def drive_md_text():
    return DRIVE_MD.read_text(encoding="utf-8")


def test_drive_md_metas_rows_mention_the_classification(drive_md_text):
    idx = drive_md_text.index("Resolve a folder's OWN title")
    row = drive_md_text[idx:drive_md_text.index("|\n", idx)]
    assert "sec_label_name" in row
    assert "SECURITY LEVEL" in row


def test_drive_md_batch_metadata_row_mentions_the_classification(drive_md_text):
    idx = drive_md_text.index("Batch metadata for many tokens")
    row = drive_md_text[idx:drive_md_text.index("|\n", idx)]
    assert "sec_label_name" in row


def test_drive_md_register_row_15_exists_with_reopen_condition(drive_md_text):
    from guard_kit import section
    region = section(drive_md_text, "## Limitations & revisit-triggers")
    assert "| 15 |" in region
    row_start = region.index("| 15 |")
    row = region[row_start:region.index("\n", row_start)]
    assert "SECURITY LEVEL" in row
    assert "NO WRITE ROUTE" in row
    # the reopen condition names something OBSERVABLE, per the file's own discipline
    assert any(word in row for word in ("found", "denied", "gains"))


def test_drive_md_register_row_14_keeps_its_ruling_and_names_the_third_variable(drive_md_text):
    from guard_kit import section
    region = section(drive_md_text, "## Limitations & revisit-triggers")
    row_start = region.index("| 14 |")
    row = region[row_start:region.index("\n", row_start)]
    assert "UNOBSERVABLE" in row, "row 14's original ruling must stand, unedited"
    assert "THIRD variable" in row or "third variable" in row.lower()
    assert "not reopened" in row.lower() or "unchanged" in row.lower()


# --------------------------------------------------------------------------- #
# AC8 — the standing ruling in DECISIONS.md.                                  #
# --------------------------------------------------------------------------- #

@private_tree.register
def test_decisions_md_has_the_D76_ruling():
    text = DECISIONS_MD.read_text(encoding="utf-8")
    assert re.search(r"^### D-76 — .+$", text, re.MULTILINE), "D-76 heading not found"


@private_tree.register
def test_decisions_md_D76_cites_LD_439():
    text = DECISIONS_MD.read_text(encoding="utf-8")
    start = text.index("### D-76")
    end = text.find("### D-", start + 1)
    section_text = text[start:end if end != -1 else start + 2000]
    assert "LD-439" in section_text
    assert "sec_label_name" in section_text


# --------------------------------------------------------------------------- #
# AC10 — no library behaviour change: no READ of sec_label_name landed.       #
# --------------------------------------------------------------------------- #

#: an attribute access (``.sec_label_name``) or a dict/subscript read
#: (``["sec_label_name"]`` / ``['sec_label_name']``) is what "the library reads the field"
#: would look like in code; a bare mention of the string inside a docstring/comment is not.
_ATTR_READ = re.compile(r"\.sec_label_name\b")
_SUBSCRIPT_READ = re.compile(r"""\[\s*['"]sec_label_name['"]\s*\]""")

#: The two known DOCSTRING mentions today (LD-439's own evidence, cited in the issue) — this
#: guard's job is catching a NEW read, not the prose that already exists.
_KNOWN_PROSE_FILES = frozenset({
    SRC / "read" / "client.py",
    SRC / "base" / "embed.py",
})

#: **THE ALLOW-LIST — one entry, and each entry names its file and its reason.**
#: A read of ``sec_label_name`` anywhere under ``src/larkdocio`` that is not in this mapping
#: reddens :func:`test_no_new_READ_of_sec_label_name_anywhere_under_src`. Adding an entry is
#: therefore a deliberate act with a written reason, which is exactly what the guard is for.
_ALLOWED_READ_SITES = {
    SRC / "drive" / "client.py": (
        "DriveClient.document_security_level — THE shipped read-side surfacing of a document's "
        "tenant security level (LD-487). One literal subscript, on the reply of the documented "
        "metas/batch_query route this library already calls through its own shipped endpoint "
        "constant; it returns the value verbatim, types '' as NO LEVEL SET and an absent key as "
        "a disclosure, and writes nothing."
    ),
}


def test_no_new_READ_of_sec_label_name_anywhere_under_src():
    """**TRANSFORMED, never deleted or widened (D-24, 2026-08-16).**

    *The reason, PRESERVED and dated.* LD-439 (2026-08-12) was a **documentation** issue, and a
    documentation issue does not grow a capability: surfacing ``sec_label_name`` in library
    outputs was out of scope for it, so this guard was shipped to hold that line. That reason
    was correct then and is not struck — it is still why an **unannounced** reader of this field
    is a defect.

    *The conclusion, SUPERSEDED.* Round 4 recorded the gap as *needing a private API* — "no
    public call to fetch it for a document, only for a folder". LD-474 **measured that false**:
    reached through the shipped ``METAS_BATCH_QUERY_ENDPOINT`` constant on a **DOCUMENT** token
    of a harness-created disposable, the reply carried
    ``sec_label_name_key_present: True | sec_label_name_value: ''`` with ``residue: []``. The
    route is documented, already called by this library, and already reached through the shipped
    constant — so LD-487 ships the read, and this guard becomes an **allow-list** rather than a
    prohibition.

    What it enforces now: **exactly the sites in** :data:`_ALLOWED_READ_SITES` may read the
    field; **any other** ``.sec_label_name`` / ``["sec_label_name"]`` under ``src/larkdocio``
    still reddens the suite. A stale allow-list entry reddens too, so the list cannot outlive
    the call site it exists for.
    """
    hits = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if _ATTR_READ.search(text) or _SUBSCRIPT_READ.search(text):
            hits.append(path)
    unexpected = sorted(str(path) for path in hits if path not in _ALLOWED_READ_SITES)
    assert not unexpected, (
        "a code path now READS sec_label_name and is not on the allow-list — surfacing this "
        "field is a library behaviour change and needs its own ruling, its own typing (an empty "
        f"string MEANS 'no level set') and its own permission row: {unexpected}"
    )
    stale = sorted(str(path) for path in _ALLOWED_READ_SITES if path not in hits)
    assert not stale, (
        f"the allow-list names a file that no longer reads sec_label_name: {stale} — remove the "
        "entry rather than leaving a licence nobody uses"
    )


def test_the_allow_list_names_ONE_site_and_carries_ITS_REASON():
    """A licence with no reason is a licence nobody can review."""
    assert len(_ALLOWED_READ_SITES) == 1
    (path, reason), = _ALLOWED_READ_SITES.items()
    assert path == SRC / "drive" / "client.py"
    assert "document_security_level" in reason
    assert "metas/batch_query" in reason
    assert len(reason) > 200, "the reason is the point; one clause is not a reason"


def test_the_transformed_guard_STILL_BITES_on_a_second_unrelated_read(tmp_path):
    """The deliberate-defect proof, run rather than described: a second reader anywhere under
    ``src`` that is not allow-listed must be caught. Exercised against the guard's own predicate
    so nothing is written into the real tree."""
    intruder = tmp_path / "somewhere_else.py"
    intruder.write_text('level = meta["sec_label_name"]\n', encoding="utf-8")
    assert _SUBSCRIPT_READ.search(intruder.read_text(encoding="utf-8"))
    assert intruder not in _ALLOWED_READ_SITES

    attribute_form = tmp_path / "attribute_form.py"
    attribute_form.write_text("level = meta.sec_label_name\n", encoding="utf-8")
    assert _ATTR_READ.search(attribute_form.read_text(encoding="utf-8"))
    assert attribute_form not in _ALLOWED_READ_SITES


def test_the_two_known_mentions_are_PROSE_ONLY_not_a_read(guide_text):
    """Belt-and-braces: confirm the two files the issue itself names still carry the key
    only as text, not as an attribute/subscript access — the deliberate-defect half of the
    guard above."""
    for path in _KNOWN_PROSE_FILES:
        text = path.read_text(encoding="utf-8")
        assert "sec_label_name" in text, f"{path} no longer mentions it — is the citation stale?"
        assert not _ATTR_READ.search(text)
        assert not _SUBSCRIPT_READ.search(text)


# --------------------------------------------------------------------------- #
# CONFORMANCE — the measured EXTERNAL truth the "not settable" claim rests on. #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_vendored_sdk_ships_sec_label_ONLY_on_response_META_models():
    """Pins the PRODUCT-level fact (process/doctrine/conformance-tier.md § A.4): a rewrite
    from the corpus must still find no settable security-level route, because the evidence
    behind that claim is this SDK shape, not this implementation. No Lark numeric HTTP code
    is pinned (LD-417 AC10 precedent) — this checks import-time SDK shape only."""
    import lark_oapi

    root = pathlib.Path(lark_oapi.__file__).resolve().parent
    hits = sorted(
        p for p in root.rglob("*.py")
        if re.search(r"sec_label", p.read_text(encoding="utf-8", errors="ignore"), re.IGNORECASE)
    )
    assert hits, (
        "the vendored SDK dropped sec_label* entirely — the READ-side evidence behind "
        "GUIDE.md's classification is now stale and needs re-measuring"
    )
    known_response_models = {
        root / "api" / "drive" / "v1" / "model" / "meta.py",
        root / "api" / "docs" / "v1" / "model" / "meta.py",
        root / "api" / "base" / "v2" / "model" / "meta.py",
    }
    unexpected = [p for p in hits if p not in known_response_models]
    assert not unexpected, (
        f"sec_label now appears outside the three known RESPONSE Meta models: {unexpected} "
        "— a write-shaped route may have appeared; re-check DRIVE.md register row 15"
    )
