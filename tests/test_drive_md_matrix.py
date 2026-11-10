# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""``/DRIVE.md`` — the FIFTH living matrix's drift guard (LD-323).

Same shape as ``test_blocks_md_matrix.py`` / ``test_sheets_md_matrix.py`` /
``test_base_md_matrix.py``, and enrolled the way ``guard_kit`` says the next matrix guard should
be — **by import, not by copy**.

**Why it exists before the code it guards.** `DRIVE.md` is born inside the tranche that builds
the surface, so the matrix cannot be a retrospective. That makes one region special: the
child-``type`` → reader **dispatch** table has no dispatcher to compare against yet, so the guard
holds it to being an honest set of placeholders **now**, and switches to the bidirectional
comparison the moment a dispatcher exists (`LD-325`). The comparison is written and tested today
against a synthetic dispatcher, so it cannot arrive dead.

The three regions, and what is checked over each:

* **Operations** — every status is a recognised slug the vocabulary table itself defines; every
  row carries a non-empty evidence pointer; every capture pointer resolves inside
  ``tests/captures/drive-spike/captures/``.
* **The dispatch table** — exactly Lark's six child types, no more and no fewer; the vocabulary
  seam is recorded; bidirectional against a dispatcher as soon as one exists.
* **§ Limitations & revisit-triggers** — the six founding rows, all cells non-empty, every
  revisit trigger naming an **observable** change, the `USER`-token row worded as an auth-model
  wall rather than a scope denial, and no scope string authored here at all.

Deliberate-defect tests prove each of the three biting halves reddens rather than merely running.
"""
import importlib
import pkgutil
import re

import pytest

from guard_kit import REPO_ROOT, md_table_rows, section
import private_tree  # noqa: E402  (LD-685)

# LD-370 — CONFORMANCE-tier: DRIVE.md is a corpus member; the folder-read contract it states is consumer-facing.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

DRIVE_MD = REPO_ROOT / "DRIVE.md"


@pytest.fixture(scope="module")
def drive_md():
    return DRIVE_MD.read_text(encoding="utf-8")


#: The slug set, authored here and cross-checked against the document's own vocabulary table so
#: neither side can drift alone.
_STATUSES = {
    "shipped",
    "not-yet-R1", "not-yet-R2", "not-yet-R3", "not-yet-R4",
    "refused-by-server", "refused-by-policy",
    "structurally-unreachable",
    "uncaptured",
}

#: Statuses whose row must name resolving code — the status-honesty rule. A `shipped` row that
#: cannot point at code is the exact defect a matrix born early is prone to.
_CODE_BEARING = {"shipped"}

#: A dotted code anchor inside backticks: ``larkdocio.base.media``.
_ANCHOR = re.compile(r"`(larkdocio(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")

#: A repository path cited in a cell, optionally with a ``§``/``::`` suffix after it.
_REPO_PATH = re.compile(r"`?((?:dev|src|tests|requirements)/[\w./\-]+)")

#: A Lark scope string — ``docx:document``, ``drive:export``. Any of these in this file must be a
#: quotation of the registry, never an authoring.
_SCOPE = re.compile(r"`([a-z_]+:[a-z_]+(?::[a-z_]+)?)`")

#: Lark's own child-``type`` vocabulary, from the listing response and the SDK's ``File`` model.
_CHILD_TYPES = ("docx", "sheet", "bitable", "folder", "shortcut", "file")


def _rows(text, section_heading, *required_headers):
    """The rows of the one table in ``section_heading`` that carries ``required_headers``."""
    region = section(text, section_heading)
    rows = md_table_rows(region)
    assert rows, f"{section_heading} carries no table"
    headers = rows[0]
    for required in required_headers:
        assert any(required.lower() in header.lower() for header in headers), (
            f"{section_heading}'s table has no {required!r} column — headers are {headers}")
    return [dict(zip(headers, cells)) for cells in rows[1:] if len(cells) == len(headers)]


def operation_rows(text):
    return _rows(text, "## Operations", "Operation", "Status", "Evidence")


def dispatch_rows(text):
    return _rows(text, "## The child-`type` → reader dispatch table",
                 "Child `type`", "Status", "Fills it")


def register_rows(text):
    return _rows(text, "## Limitations & revisit-triggers",
                 "Limitation", "Status", "Evidence", "Revisit trigger")


def _status_of(row):
    for key, value in row.items():
        if "status" in key.lower():
            return value.strip().strip("*`")
    raise AssertionError(f"row has no status column: {row}")


def _resolves(anchor):
    module, _, attr = anchor.rpartition(".")
    for candidate, name in ((anchor, None), (module, attr)):
        try:
            mod = importlib.import_module(candidate)
        except ImportError:
            continue
        return name is None or hasattr(mod, name)
    return False


# --------------------------------------------------------------------------- #
# The document parses, and it really has the three regions the Drive spec § D1 ruled. #
# --------------------------------------------------------------------------- #

def test_the_matrix_exists_and_has_the_THREE_REGIONS(drive_md):
    assert "# DRIVE.md" in drive_md
    assert len(operation_rows(drive_md)) >= 20, "the operations region is the surface's whole map"
    assert len(dispatch_rows(drive_md)) == len(_CHILD_TYPES)
    assert len(register_rows(drive_md)) == _REGISTER_ROWS


def test_it_declares_itself_the_FIFTH_matrix_and_names_the_other_four(drive_md):
    """The matrices are a set, and a new member that does not say so reads as a stray doc."""
    assert "fifth" in drive_md.lower()
    for sibling in ("BLOCKS.md", "SHEETS.md", "BASE.md", "PERMISSIONS.md"):
        assert sibling in drive_md, sibling


# --------------------------------------------------------------------------- #
# The revision-anchor prose stays honest once the cheap probe SHIPS (LD-392). #
# The "until it lands" clause was a negative claim LD-382 refuted; a stale     #
# forward reference is exactly the class LD-380's doctrine says nobody         #
# re-tests on its own — so it gets a guard.                                    #
# --------------------------------------------------------------------------- #

def _revision_section(text):
    return section(text, "## The manifest's `revision` field")


def test_the_revision_section_NAMES_the_SHIPPED_cheap_probe(drive_md):
    region = _revision_section(drive_md)
    assert "read_document_revision" in region, (
        "the shipped cheap route (LD-382) is not named in the revision-anchor prose")
    assert "LD-382" in region


def test_the_revision_section_no_longer_FORWARD_REFERENCES_unlanded_work(drive_md):
    """The exact stale phrasing this bug was filed over — a negative claim LD-382 refuted."""
    region = _revision_section(drive_md).lower()
    assert "until it lands" not in region
    assert "is a separate piece of work" not in region


def test_the_revision_section_still_states_the_UNMEASURED_bulk_form(drive_md):
    """LD-380's doctrine: correcting a refuted negative claim must not silently drop the
    part that is still true — there really is no bulk revision route (DECISIONS.md D-50)."""
    region = _revision_section(drive_md).lower()
    assert "batch_query" in region or "bulk" in region


def test_the_revision_section_POINTS_AT_its_own_provenance(drive_md):
    """The full semantics and the measured-unmeasured line live in GUIDE.md / DECISIONS.md;
    this matrix cross-references rather than re-authoring them (drift-prone otherwise)."""
    region = _revision_section(drive_md)
    assert "GUIDE.md" in region
    assert "D-50" in region


# --------------------------------------------------------------------------- #
# Status honesty — the slug set, and the code a status claims.                  #
# --------------------------------------------------------------------------- #

def _all_rows(text):
    return operation_rows(text) + dispatch_rows(text) + register_rows(text)


def test_every_status_slug_is_recognised(drive_md):
    unknown = sorted({_status_of(row) for row in _all_rows(drive_md)} - _STATUSES)
    assert not unknown, f"/DRIVE.md uses status slugs no vocabulary defines: {unknown}"


def test_the_status_vocabulary_table_DEFINES_every_slug_the_matrix_uses(drive_md):
    """The document's own vocabulary table is the reader's dictionary — a slug used but never
    defined is how an honest-status discipline turns into decoration."""
    defined = set()
    for row in md_table_rows(section(drive_md, "## Status vocabulary"))[1:]:
        defined.add(row[0].strip().strip("*`"))
    used = {_status_of(row) for row in _all_rows(drive_md)}
    assert used <= defined, f"used but undefined: {sorted(used - defined)}"
    assert defined <= _STATUSES, f"defined but not a house slug: {sorted(defined - _STATUSES)}"


def test_every_code_bearing_row_names_RESOLVING_code(drive_md):
    for row in operation_rows(drive_md):
        if _status_of(row) not in _CODE_BEARING:
            continue
        anchors = _ANCHOR.findall(" ".join(row.values()))
        assert anchors, f"a shipped row names no code: {row}"
        for anchor in anchors:
            assert _resolves(anchor), f"{anchor} does not resolve — a shipped row must"


def test_every_code_anchor_ANYWHERE_in_the_matrix_resolves(drive_md):
    dead = [a for a in _ANCHOR.findall(drive_md) if not _resolves(a)]
    assert not dead, f"/DRIVE.md names code that cannot be imported: {sorted(set(dead))}"


def _cited_path_exists(path):
    """A path exists, or — LD-700 (T13), where a token fragment in a file name was written
    ``<token>`` and the match stops there — it is a prefix of a file in its directory."""
    target = REPO_ROOT / path.rstrip(".,;)")
    if target.exists():
        return True
    if path.endswith("-") and target.parent.is_dir():
        return any(child.name.startswith(target.name) for child in target.parent.iterdir())
    return False


@private_tree.citations
def test_every_repo_path_cited_ANYWHERE_exists(drive_md):
    missing = sorted({
        path for path in _REPO_PATH.findall(drive_md)
        if not _cited_path_exists(path)
    })
    assert not missing, f"/DRIVE.md cites paths this repo does not carry: {missing}"


def test_SCOPES_ARE_NOT_AUTHORED_HERE_and_the_single_source_is_NAMED(drive_md):
    """The Drive spec § D1: where a row names a scope it quotes ``larkdocio.permissions``. The safest
    form of that rule is the one this file obeys — no scope literal at all."""
    assert "larkdocio.permissions" in drive_md
    literals = sorted(set(_SCOPE.findall(drive_md)))
    assert not literals, (
        f"/DRIVE.md authors the scope literals {literals}; this file quotes the registry by "
        "NAME and carries no scope string of its own — which is also what keeps it out of the "
        "duplication ratchet tests/test_permissions_docs.py holds")
    from larkdocio import permissions

    known = {
        scope.scope
        for _endpoint, _mode, scopes, _optional in permissions.ENDPOINT_SCOPES
        for scope in scopes
    }
    for literal in literals:
        assert literal in known, (
            f"/DRIVE.md authors the scope {literal!r}, which the registry does not carry — a "
            "scope requirement is authored in larkdocio.permissions and quoted here")


# --------------------------------------------------------------------------- #
# Operations — every row is answerable, and every capture pointer is real.      #
# --------------------------------------------------------------------------- #

def test_every_operations_row_carries_an_EVIDENCE_pointer(drive_md):
    for row in operation_rows(drive_md):
        evidence = next(v for k, v in row.items() if "evidence" in k.lower())
        assert evidence.strip() not in ("", "—", "-", "TBD"), row


def test_no_operations_row_cites_a_CAPTURE_THAT_DOES_NOT_EXIST(drive_md):
    """The evidence base is a capture directory; a pointer into it that resolves to nothing is
    the failure mode a matrix written from a spike is most exposed to."""
    captures = REPO_ROOT / "tests" / "captures" / "drive-spike" / "captures"
    assert captures.is_dir()
    carried = {path.name for path in captures.iterdir()}
    cited = set()
    for row in operation_rows(drive_md):
        for path in _REPO_PATH.findall(" ".join(row.values())):
            if "drive-spike/captures/" in path:
                cited.add(path.rsplit("/", 1)[1])
    assert cited, "no operations row cites the spike's captures at all"
    assert cited <= carried, f"cited captures that do not exist: {sorted(cited - carried)}"


def test_the_ALREADY_SHIPPED_drive_reach_is_listed_and_NOT_counted_as_new(drive_md):
    """Export, media and comments are Drive-family calls this project has been making for
    releases. A matrix that omitted them would read as if Drive were untouched — and one that
    listed them as new reach would double-count the effort."""
    rows = {row["Operation"]: row for row in operation_rows(drive_md)}
    shipped = [name for name, row in rows.items() if _status_of(row) == "shipped"]
    assert len(shipped) >= 4, shipped
    text = " ".join(" ".join(rows[name].values()) for name in shipped)
    assert "export_tasks" in text and "medias/upload_all" in text and "comments" in text
    assert "not new" in text.lower() or "not to be counted twice" in text.lower()


def test_the_OUT_classes_are_each_REPRESENTED_because_they_are_why_this_file_exists(drive_md):
    """The Drive spec's § D1 whole argument: ``capabilities()`` has no row shape for can-but-won't, for
    structurally unreachable, or for the API-has-no-such-verb. If those classes were absent here
    the file would not be earning its keep."""
    statuses = {_status_of(row) for row in operation_rows(drive_md)}
    for required in ("refused-by-policy", "structurally-unreachable", "uncaptured", "shipped"):
        assert required in statuses, required
    rows = operation_rows(drive_md)
    policy = " ".join(" ".join(r.values()) for r in rows
                      if _status_of(r) == "refused-by-policy")
    assert "capability token" in policy, (
        "the share-password row is the sharpest member of the refused family and the reason the "
        "class is written down rather than left implicit")


# --------------------------------------------------------------------------- #
# The dispatch table — placeholders now, BIDIRECTIONAL the moment a dispatcher  #
# exists. The comparison is written and tested today so it cannot arrive dead.  #
# --------------------------------------------------------------------------- #

#: The attribute names a dispatcher's ``type`` → reader mapping may carry. The guard looks for
#: one of these anywhere in ``larkdocio.drive``; a dispatcher that names its mapping something
#: else must add the name here, which is a one-line, deliberate act.
_DISPATCH_ATTRS = ("CHILD_TYPE_READERS", "TYPE_READERS", "DISPATCH", "DISPATCH_TABLE")


def shipped_dispatch_map():
    """The shipped ``child type`` → reader mapping, or ``None`` while no dispatcher exists."""
    try:
        package = importlib.import_module("larkdocio.drive")
    except ImportError:
        return None
    modules = [package]
    for info in pkgutil.iter_modules(package.__path__):
        try:
            modules.append(importlib.import_module(f"larkdocio.drive.{info.name}"))
        except ImportError:
            continue
    for module in modules:
        for attr in _DISPATCH_ATTRS:
            candidate = getattr(module, attr, None)
            if isinstance(candidate, dict) and candidate:
                return candidate
    return None


def bidirectional_failures(documented, mapping):
    """Both directions, as a list of human-readable failures. Empty means agreement."""
    failures = []
    for child_type in sorted(set(mapping) - set(documented)):
        failures.append(
            f"the dispatcher branches on {child_type!r} and no /DRIVE.md row documents it — "
            "touch the surface, update the matrix")
    for child_type in sorted(set(documented) - set(mapping)):
        failures.append(
            f"/DRIVE.md documents {child_type!r} but no dispatcher branch handles it")
    return failures


def _documented_types(text):
    key = "Child `type` (Lark's word)"
    return [row[key].strip().strip("`") for row in dispatch_rows(text)]


def test_the_dispatch_table_documents_EXACTLY_larks_six_child_types(drive_md):
    assert _documented_types(drive_md) == list(_CHILD_TYPES)


def test_the_VOCABULARY_SEAM_is_RECORDED_and_labelled_ASSERTED_NOT_DEMONSTRATED(drive_md):
    """The seam — Drive says ``sheet``/``bitable``, larkdocio says ``sheets``/``base`` — is
    LD-325's to solve and this file's to record. It must also carry its own honesty label: the
    Maintainer's real tree contained neither a spreadsheet nor a Base, so the mapping rests on the SDK's
    model rather than on a live dispatch."""
    region = section(drive_md, "## The child-`type` → reader dispatch table")
    assert "seam" in region.lower()
    for word in ("`sheet`", "`bitable`", "`sheets`", "`base`"):
        assert word in region, word
    assert "asserted-not-demonstrated" in region.lower().replace("**", "")
    rows = {row["Child `type` (Lark's word)"].strip("` "): row for row in dispatch_rows(drive_md)}
    for lark_word, our_word in (("sheet", "sheets"), ("bitable", "base")):
        cell = rows[lark_word]["larkdocio's word"]
        assert our_word in cell and "seam" in cell.lower(), (lark_word, cell)


def test_while_NO_DISPATCHER_EXISTS_every_row_is_an_HONEST_PLACEHOLDER(drive_md):
    """AC5: the rows may be placeholders in this issue — but a placeholder must name the story
    that fills it, or "not yet" is a shrug. The moment a dispatcher exists this arm stops
    applying and the bidirectional one takes over."""
    mapping = shipped_dispatch_map()
    if mapping is not None:
        pytest.skip("a dispatcher exists — the bidirectional guard is the binding one now")
    for row in dispatch_rows(drive_md):
        assert _status_of(row) == "not-yet-R1", row
        assert "LD-325" in row["Fills it"], row


def test_the_dispatch_region_is_BIDIRECTIONAL_the_moment_a_dispatcher_exists(drive_md):
    mapping = shipped_dispatch_map()
    if mapping is None:
        pytest.skip("no dispatcher yet (LD-325) — the placeholder guard is the binding one")
    failures = bidirectional_failures(_documented_types(drive_md), mapping)
    assert not failures, "\n".join(failures)


# --------------------------------------------------------------------------- #
# § Limitations & revisit-triggers — the founding six.                          #
# --------------------------------------------------------------------------- #

_REGISTER_ROWS = 15

#: ``row number -> (a needle its limitation must carry, a needle its trigger must carry)`` — each
#: row pinned by what makes it that row rather than by position. Rows 1-6 are the founding six
#: (LD-323 AC5); rows 7-11 are the boundaries the named-version family shipped with (LD-409
#: AC11), added here in the same change that added them to the document.
_FOUNDING = {
    "1": ("1061002", "1061003"),
    "2": ("option", "documents the accepted values"),
    "3": ("trash", "purge"),
    "4": ("UN-PURGEABLE", "media delete/purge verb"),
    "5": ("USER", "token_types"),
    "6": ("documented-unverified", "denied"),
    "7": ("delete_version", "restore/undelete route"),
    "8": ("`status` vocabulary is UNMEASURED", "other than `0`"),
    "9": ("UNMEASURED, NOT REFUTED", "untried `obj_type`"),
    "10": ("NO QUOTA IS DISCLOSED", "quota or rate refusal"),
    "11": ("NO `revision_id`", "gains** a `revision_id`"),
    # LD-432 AC8 — the three boundaries the docx ACCESS surface shipped with, added here in
    # the same change that added them to the document (the LD-409 precedent, exactly).
    "12": ("ONE-WAY", "delete right"),
    "13": ("UNMEASURED, NOT REFUSED", "real** department id"),
    "14": ("UNOBSERVABLE", "copy/paste attempt"),
    # LD-439 AC3 — the security-level classification's own register row, added here in the
    # same change that added it to the document (the LD-409/LD-432 precedent, exactly).
    "15": ("NO WRITE ROUTE", "denied"),
}


def _register_by_number(text):
    return {row["#"].strip(): row for row in register_rows(text)}


def test_the_register_has_EXACTLY_the_FOUNDING_rows(drive_md):
    rows = _register_by_number(drive_md)
    assert sorted(rows) == sorted(_FOUNDING), sorted(rows)
    assert len(rows) == _REGISTER_ROWS


@pytest.mark.parametrize("number,needles", sorted(_FOUNDING.items()))
def test_each_founding_row_SAYS_ITS_OWN_FACT(drive_md, number, needles):
    row = _register_by_number(drive_md)[number]
    limitation, trigger = needles
    assert limitation in row["Limitation"], (number, row["Limitation"])
    assert trigger in row["Revisit trigger — the observable API change"], (number, row)


def test_every_register_cell_is_NON_EMPTY(drive_md):
    for row in register_rows(drive_md):
        for key, value in row.items():
            assert value.strip() not in ("", "—", "-", "TBD"), (key, row)


def test_every_revisit_trigger_names_an_OBSERVABLE_change(drive_md):
    """A trigger that says "revisit later" is not a trigger. Each must name something a
    maintainer could *see* — a code, a route, a field, a body, a model."""
    observable = ("answers", "appears", "returns", "lists", "documents", "denied",
                  "accepts", "instead of", "gains", "stops")
    for row in register_rows(drive_md):
        trigger = row["Revisit trigger — the observable API change"].lower()
        assert any(word in trigger for word in observable), row


def test_row_5_is_worded_as_an_AUTH_MODEL_WALL_and_NOT_as_a_scope_denial(drive_md):
    """AC5 is explicit about this row's wording, and the reason is that the two are fixed by
    completely different things: a scope denial is a console grant away, and this is not."""
    row = _register_by_number(drive_md)["5"]
    text = " ".join(row.values())
    assert "auth-model wall" in text.lower()
    assert "not a scope denial" in text.lower().replace("**", "")
    assert "no grant in any lark console opens this" in text.lower().replace("**", "")


def test_row_4_CROSS_REFERENCES_the_base_matrix_instead_of_RESTATING_it(drive_md):
    """The unpurgeable-media finding is ``BASE.md`` row 10 seen from the Drive side. Two
    independent authorings of one fact is how they drift apart."""
    row = _register_by_number(drive_md)["4"]
    text = " ".join(row.values())
    assert "BASE.md" in text and "row 10" in text
    assert "not a second finding" in text.lower()


def test_row_6_records_a_NON_OBSERVATION_and_GUESSES_NOTHING(drive_md):
    """The scope rows are the ones a future maintainer is most tempted to fill in from the
    documentation. The register's job is to make the non-observation legible."""
    row = _register_by_number(drive_md)["6"]
    text = " ".join(row.values())
    assert _status_of(row) == "uncaptured"
    assert "not guessed" in text.lower()
    assert "credential aliasing" in text.lower(), (
        "the aliasing fact is why a same-tenant success cannot attribute a scope at all")


# --------------------------------------------------------------------------- #
# DELIBERATE DEFECTS — the guard bites, on each of its three binding halves.    #
# --------------------------------------------------------------------------- #

def test_DEFECT_removing_a_register_row_reddens_the_count(drive_md):
    mutated = "\n".join(
        line for line in drive_md.splitlines() if not line.startswith("| 3 |"))
    assert len(register_rows(mutated)) == _REGISTER_ROWS - 1
    with pytest.raises(AssertionError):
        rows = _register_by_number(mutated)
        assert sorted(rows) == sorted(_FOUNDING)


def test_DEFECT_emptying_a_revisit_trigger_reddens_the_completeness_guard(drive_md):
    row = _register_by_number(drive_md)["2"]
    trigger = row["Revisit trigger — the observable API change"]
    mutated = drive_md.replace(f"| {trigger} |", "|  |")
    assert mutated != drive_md
    with pytest.raises(AssertionError):
        for mutated_row in register_rows(mutated):
            for value in mutated_row.values():
                assert value.strip() not in ("", "—", "-", "TBD")


def test_DEFECT_a_dispatch_row_removed_reddens_the_BIDIRECTIONAL_comparison():
    """The comparison cannot be exercised against the real dispatcher yet, so it is exercised
    against a synthetic one — which is what stops it arriving dead. Both directions bite."""
    documented = list(_CHILD_TYPES)
    mapping = {child_type: object() for child_type in _CHILD_TYPES}

    assert bidirectional_failures(documented, mapping) == []

    dropped = bidirectional_failures([t for t in documented if t != "shortcut"], mapping)
    assert len(dropped) == 1 and "no /DRIVE.md row documents it" in dropped[0]

    phantom = bidirectional_failures(documented + ["mindnote"], mapping)
    assert len(phantom) == 1 and "no dispatcher branch handles it" in phantom[0]


def test_DEFECT_an_unrecognised_status_slug_reddens(drive_md):
    # LD-325 filled the dispatch rows, so the placeholder ``not-yet-R1`` status is gone; the
    # shortcut row's ``uncaptured`` is the live half's honest status and the mutation target now.
    mutated = drive_md.replace("| `uncaptured` | `LD-325` |", "| `soon` | `LD-325` |", 1)
    assert mutated != drive_md
    with pytest.raises(AssertionError):
        unknown = sorted({_status_of(row) for row in dispatch_rows(mutated)} - _STATUSES)
        assert not unknown


def test_DEFECT_a_dead_code_anchor_reddens_the_status_honesty_guard():
    assert _resolves("larkdocio.common.url.URL_PATH_SHAPES")
    # LD-326 shipped ``read_folder`` (it now resolves), so the dead-anchor example moves on to
    # the next still-unbuilt rung — LD-327's Drive CLI verb, which does not exist yet.
    assert _resolves("larkdocio.drive.read_folder")
    assert not _resolves("larkdocio.drive.download_folder")


# --------------------------------------------------------------------------- #
# LD-442 — the rows a shipped verb had been filed under as unbuilt, and the    #
# chunked row's measured-rather-than-untried sentence. Measured external truth  #
# about Lark (this module is conformance-marked at the top).                    #
# --------------------------------------------------------------------------- #

def _row_named(text, name):
    for row in operation_rows(text):
        if name in row["Operation"]:
            return row
    raise AssertionError(f"no operations row named {name!r}")


def test_no_row_files_a_SHIPPED_verb_under_an_unapproved_rung(drive_md):
    """The defect this guard exists for: `delete` and the file-bytes download both ship, and
    both were filed as deferred-and-unapproved — a matrix saying a shipped verb is unbuilt is
    worse than one that omits it, because a reader plans around it."""
    for name in ("Delete a file this library uploaded",
                 "Download a file object's bytes",
                 'Download a `type:"file"` child\'s bytes'):
        assert _status_of(_row_named(drive_md, name)) == "shipped", name
    organize = _row_named(drive_md, "Move / copy")
    assert "delete" not in organize["Endpoint"].lower(), (
        "the organize row must no longer claim the DELETE endpoint it does not fence")
    assert _status_of(organize) == "not-yet-R3"


def test_the_walk_half_of_the_re_scoped_download_row_SURVIVES(drive_md):
    """Re-scoped, not deleted: the endpoint ships AND the R1 folder walk still fetches no
    bytes. Dropping the second half would trade one false sentence for another."""
    row = _row_named(drive_md, 'Download a `type:"file"` child\'s bytes')
    said = row["What the project says"].lower()
    assert "lists and discloses" in said and "fetches no bytes" in said


def test_the_chunked_row_is_SHIPPED_and_still_states_what_was_MEASURED(drive_md):
    """**Transformed, not deleted (LD-449 supersedes LD-442's conclusion, keeping its
    reason).** LD-442 pinned this row at ``not-yet-R2`` to hold one thing true: *correcting a
    false sentence inside a row is not an approval, and a rung opens only when a ruling opens
    it*. That reason stands and is why this assertion still exists. What changed is the fact it
    asserts: a maintainer ruling opened the chunked half, so the row is ``shipped`` — and the same
    guard now holds the other half of the bargain, that a `shipped` row keeps the measurement
    which forbids a hard-coded cut-over instead of shrinking to a boast."""
    row = _row_named(drive_md, "Upload a file in CHUNKS")
    assert _status_of(row) == "shipped", (
        "the rung was opened by an explicit ruling; a status only ever moves that way")
    said = row["What the project says"]
    assert "4194304" in said and "1 → 16" in said, (
        "the server-declared block size and count ARE the measurement — an implementation may "
        "never hard-code a cut-over, and the numbers are why")
    assert "hash-verified" in said.lower()
    assert "server-declared" in said.lower() and "library policy" in said.lower(), (
        "the row must say which number is the SERVER's and which is this library's policy")
    assert "no cancel verb" in said.lower() and "unmeasured" in said.lower(), (
        "the abandoned-upload_id residue is disclosed as unmeasured, never as 'cannot'")
    assert "never sent" in said.lower(), (
        "block_num > 1 was asked about and never sent AT SPIKE TIME — the row keeps that "
        "history beside the live gate that settled it")


def test_the_cross_pointers_cite_rows_by_NAME_not_by_direction(drive_md):
    """A row inserted between two rows that point at each other by *above* / *below* breaks
    both silently. Naming the row cannot rot that way."""
    body = " ".join(" ".join(row.values()) for row in operation_rows(drive_md))
    for phrase in ("the row above", "the row below"):
        assert phrase not in body, (
            f"an operations row still cites a neighbour as {phrase!r} — cite it by its "
            "Operation name so a row insertion cannot re-break the pointer")
