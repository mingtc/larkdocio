"""LD-133 — the shipped discovery layer must tell the TRUTH about writes.

Dogfood session #1's verdict was "for reads — yes, completely; for writes — no", and all
three stoppers were in the shipped discovery layer (``larkdocio.guide()`` +
``larkdocio.capabilities()``), not in the engines:

* **F13** — the docx-write recipe was **not runnable**: it passed a ``root`` that was an
  undefined free variable, and the call that produces one (``Parser.parse_docx_tree``) was
  named in **neither** discovery surface. A ``compile()``-only recipe gate is blind to
  this, so the suite stayed green while the shipped recipe ``NameError``ed.
* **F14 + F9** — the single most consequential constraint in the library (**only unstyled
  paragraph text is creatable** — no headings, lists, tables) appeared in neither surface,
  and ``WRITE_HOSTILE_NODE_TYPES`` excluding ``TableNode`` reads as "tables are writable"
  when only a table's *cells* are **editable** (editable ≠ creatable).
* **F4 + F8** — the sheets-write recipe was actively wrong: ``"Sheet1!A1:A1"`` is a tab
  *title*, ranges take the ``sheet_id``, so the recipe **refused** as pasted; and its
  ``client`` was the read recipe's variable name with no type anywhere.
* **F10/F11/F12/F15** — no ``.env`` story on the Python path, ``domain=`` undocumented as
  the **API** domain (not the tenant host), ``capabilities()`` printing as a ~4KB wall, and
  nothing on writing into an **empty** document.

The AC sections below are the contract. The load-bearing upgrade is **§AC7**: every recipe
is extracted from the shipped guide and **EXECUTED** offline (``tests/guide_recipes.py``),
so a future guide edit that breaks a recipe reddens the suite instead of shipping.
"""
import inspect
import json
import re
import sys

import pytest

import guide_recipes as gr
from log_reading_apply import reading_the_log
import capability_rows as rows
from larkdocio import capabilities, guide

# --------------------------------------------------------------------------- #
# Shared readers over the shipped guide text.                                   #
# --------------------------------------------------------------------------- #

_TEXT = None


def _guide_text() -> str:
    global _TEXT
    if _TEXT is None:
        _TEXT = guide(full=True)
    return _TEXT


def _section(heading: str) -> str:
    """The guide text from ``heading`` up to the next same-level heading."""
    text = _guide_text()
    level = len(heading) - len(heading.lstrip("#"))
    start = text.find(heading)
    assert start != -1, f"the guide has no {heading!r} section"
    rest = text[start + len(heading):]
    nxt = re.search(rf"^#{{1,{level}}} ", rest, flags=re.MULTILINE)
    return heading + (rest[: nxt.start()] if nxt else rest)


def _docx_write_surface() -> dict:
    return capabilities(full=True)["surfaces"]["docx-write"]


# --------------------------------------------------------------------------- #
# AC1 — the docx-write recipe is RUNNABLE starting from a URL (F13).             #
# --------------------------------------------------------------------------- #

def test_ac1_docx_write_recipe_names_parse_docx_tree_and_the_full_chain():
    """AC1: the docx-write recipe composes read → ``parse_docx_tree`` → ``dry_run`` →
    ``apply`` — every step named in the recipe text itself."""
    src = gr.recipe_source("the-docx-write-handshake")
    for needle in ("init_env", "validate_download_url", "get_docx_content",
                   "parse_docx_tree", "dry_run(", "apply("):
        assert needle in src, f"the docx-write recipe never names {needle!r}:\n{src}"


def test_ac1_parse_docx_tree_is_named_in_the_guide_prose_too():
    """AC1: ``parse_docx_tree`` is discoverable in the guide's prose, with the
    ``parse_docx_content`` (Markdown) vs ``parse_docx_tree`` (node tree) distinction
    spelled out — the exact fork the dogfood consumer had to find via ``dir(Parser)``."""
    section = _section("### Recipe: the docx write handshake")
    assert "parse_docx_tree" in section
    assert "parse_docx_content" in section, (
        "the recipe must contrast parse_docx_tree with parse_docx_content — reaching for "
        "the Markdown one is the mistake the guide has to prevent"
    )


@pytest.mark.parametrize("block", gr.python_blocks(), ids=lambda b: (b.slug or "non-recipe"))
def test_ac1_no_python_block_has_an_undefined_free_variable(block):
    """AC1 (the F13 root cause): NO python block in the guide loads a name it never binds.

    This is the check a ``compile()``-only gate cannot make — it is what let
    ``dry_run(requests, root)`` ship with ``root`` undefined."""
    undefined = gr.undefined_free_names(block.source)
    assert not undefined, (
        f"guide block has undefined free variable(s) {undefined} — it cannot run as "
        f"pasted:\n{block.source}"
    )


def test_ac1_the_free_variable_check_bites_on_the_shipped_bug():
    """AC1 (red-then-green on the checker itself): the VERBATIM pre-fix recipe line is
    caught, and the shipped recipe is clean — so the check that guards is the check that
    bites."""
    prefix = (
        "from larkdocio.write import Anchor, EditRequest, dry_run, apply, WriteClient\n"
        "requests = [EditRequest(anchor=Anchor(quote='q', breadcrumb=()), replacement='r')]\n"
        "plan = dry_run(requests, root)\n"
    )
    assert gr.undefined_free_names(prefix) == ["root"]
    assert gr.undefined_free_names(gr.recipe_source("the-docx-write-handshake")) == []


def test_ac1_capabilities_docx_read_gains_the_parser_ops():
    """AC1: the producing call is discoverable in the PROJECTION, not only the guide —
    ``capabilities()['surfaces']['docx-read']`` carries the parser ops, projected from
    the ``Parser`` class (never hand-listed)."""
    ops = rows.by_name(capabilities(full=True)["surfaces"]["docx-read"], rows.OPERATION)
    assert "parse_docx_tree" in ops, (
        "capabilities() docx-read must name the call that produces the writer's `root`")
    assert "parse_docx_content" in ops
    assert ops["parse_docx_tree"]["projected_from"] == "larkdocio.read.parser.Parser"


# --------------------------------------------------------------------------- #
# AC2 — the creatable-content floor, in BOTH discovery surfaces (F14 + F9).      #
# --------------------------------------------------------------------------- #

def test_ac2_capabilities_docx_write_carries_a_content_constraints_floor():
    """AC2: the docx-write row carries an explicit floor field naming the creatable
    content types.

    LD-134 lifted the floor off ``NewParagraph``-only (dogfood F2): the creatable set is
    now ``NewBlock`` (heading / paragraph / bullet / ordered / todo / code / quote) **plus**
    the still-valid legacy ``NewParagraph``, and the projected field list is their union.
    """
    cc = _docx_write_surface().get("content_constraints")
    assert cc, "capabilities() docx-write must carry a content_constraints/floor field"
    assert cc["creatable"] == ["NewBlock", "NewParagraph"], cc
    assert "text" in cc["creatable_content_fields"], cc
    assert "kind" in cc["creatable_content_fields"], cc
    assert cc["floor"] and isinstance(cc["floor"], str)


def test_ac2_the_floor_field_is_consistent_with_the_write_model_code_truth():
    """AC2 (the amplifier): the floor is a PROJECTION over ``write/`` code truth, not a
    hand-list — it equals the content types of ``InsertRequest.content`` (a ``Union`` is
    flattened, LD-134) and the union of their dataclass fields."""
    import dataclasses
    import typing

    from larkdocio.capabilities import _flatten_content_types
    from larkdocio.write.model import InsertRequest

    types = _flatten_content_types(typing.get_type_hints(InsertRequest)["content"])
    assert types, "the content annotation must project at least one creatable type"
    truth_types = sorted(t.__name__ for t in types)
    truth_fields = []
    for cls in sorted(types, key=lambda c: c.__name__):
        for f in dataclasses.fields(cls):
            if f.name not in truth_fields:
                truth_fields.append(f.name)

    cc = _docx_write_surface()["content_constraints"]
    assert cc["creatable"] == truth_types
    assert cc["creatable_content_fields"] == truth_fields
    assert cc["projected_from"] == "larkdocio.write.model.InsertRequest.content"


def test_ac2_the_floor_names_the_shapes_that_are_still_not_creatable():
    """AC2 (F14): the floor spells out the shapes a consumer WILL plan an architecture
    around and cannot create. Headings and list items came OFF this list in LD-134 and a
    plain **table** came off it in LD-135 (they are creatable now — claiming otherwise
    would be the same F14 lie in reverse); what remains for tables is the **merged cell**,
    which Markdown cannot express at all."""
    cc = _docx_write_surface()["content_constraints"]
    joined = " ".join(cc["not_creatable"]).lower()
    for shape in ("merged", "table", "image", "board", "embed", "styled runs"):
        assert shape in joined, f"not_creatable must name {shape!r}: {cc['not_creatable']}"
    for creatable_now in ("heading (any level)", "list item (bullet"):
        assert creatable_now not in joined, (
            f"{creatable_now!r} is creatable since LD-134: {cc['not_creatable']}")
    for entry in cc["not_creatable"]:
        assert not entry.lower().startswith("table"), (
            f"a plain table is creatable since LD-135; only a MERGE is not: {entry!r}")
    assert not set(cc["not_creatable"]) & set(cc["creatable"])


def test_ac2_the_floor_states_the_editable_not_creatable_nuance():
    """AC2 (F9): the floor distinguishes **editable** from **creatable**. Since LD-135 the
    nuance lives in the **merge** case — a merged table reads and its unmerged cells edit,
    but no merge can be authored (and created text is unstyled while an existing block's
    styles survive a sub-span edit)."""
    cc = _docx_write_surface()["content_constraints"]
    joined = " ".join(cc["editable_not_creatable"]).lower()
    assert "table" in joined, cc["editable_not_creatable"]
    assert "merge" in joined, cc["editable_not_creatable"]
    assert not set(cc["editable_not_creatable"]) & set(cc["creatable"])
    assert "editable" in cc["floor"].lower() and "creatable" in cc["floor"].lower()


def test_ac2_the_guide_write_recipe_states_the_floor_inline():
    """AC2: the guide's docx-write section states the floor where a consumer pastes the
    recipe — naming ``NewParagraph``, the creatable kinds (headings / lists / tables), and
    what is still NOT creatable (since LD-135, a table's **merged** cells)."""
    section = _section("### Recipe: the docx write handshake")
    assert "NewParagraph" in section
    low = section.lower()
    assert "not creatable" in low or "cannot be created" in low, section
    for shape in ("heading", "list", "table", "merged"):
        assert shape in low, f"the write recipe must name {shape!r} in the floor"


def test_ac2_the_guide_spells_out_editable_not_creatable_where_write_hostile_lives():
    """AC2 (F9): **every** Markdown block that mentions the write-hostile refusal also
    carries the editable ≠ creatable nuance.

    Block-level granularity is the point (the LD-132 anti-rot rule replayed): a nuance
    present *somewhere else* in the guide does not stop the paragraph a consumer is
    actually reading from implying that the hostile list is a creatable list. That is F9
    verbatim — ``WRITE_HOSTILE_NODE_TYPES`` excludes ``TableNode``, so a consumer reading
    only the refusal paragraph concludes tables are writable."""
    blocks = [
        b for b in re.split(r"\n\n+", _guide_text())
        if "write-hostile" in b.lower() or "WRITE_HOSTILE" in b
    ]
    assert blocks, "the guide must document the write-hostile refusal"
    for block in blocks:
        low = block.lower()
        assert "editable" in low and "creatable" in low, (
            "a block mentioning the write-hostile refusal omits the editable ≠ creatable "
            "nuance (F9) — read alone it implies the hostile list is a creatable list:\n"
            + block
        )


# --------------------------------------------------------------------------- #
# AC3 — the sheets-write recipe uses a real sheet_id obtained in-recipe (F4+F8). #
# --------------------------------------------------------------------------- #

def test_ac3_sheets_write_recipe_obtains_the_sheet_id_via_query_tabs():
    """AC3 (F4): the recipe calls ``query_tabs`` ITSELF and uses the returned
    ``sheet_id`` in the A1 range — no title-shaped literal."""
    src = gr.recipe_source("the-sheets-write-handshake")
    assert "query_tabs" in src, src
    assert "sheet_id" in src, src
    assert re.search(r"for_a1\(\s*f?[\"'][^\"']*\{?sheet_id", src), (
        "the A1 range must be built from the sheet_id the recipe just obtained:\n" + src)


def test_ac3_the_old_title_shaped_example_is_gone():
    """AC3 (the negative test the amplifier asks for): the trap form the dogfood consumer
    pasted — a tab TITLE where an id belongs — is no longer *executable* anywhere in the
    guide. Naming it in prose/comments as the trap is the fix, so the check targets code:
    no runnable line may build a range from a title."""
    text = _guide_text()
    assert not re.search(r"for_a1\(\s*f?[\"']Sheet1!", text), (
        "the guide still ships the title-shaped A1 range that refuses as pasted (F4)")
    for block in gr.python_blocks():
        runnable = [ln for ln in block.source.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")]
        offenders = [ln for ln in runnable if "Sheet1!" in ln]
        assert not offenders, f"a runnable line still uses a tab TITLE as a range: {offenders}"
    # and the trap is still explained where the consumer reads it.
    assert "Sheet1!A1:A1" in text, (
        "the guide must still NAME the trap form so a consumer recognizes it (F4)")


def test_ac3_the_recipe_comments_the_title_vs_id_trap():
    """AC3: the recipe carries a comment naming the trap — ``Sheet1`` is a *title*, not an
    id, and it is the default title Lark gives every new tab."""
    src = gr.recipe_source("the-sheets-write-handshake")
    comments = "\n".join(ln for ln in src.splitlines() if ln.strip().startswith("#")).lower()
    assert "title" in comments and "sheet_id" in comments, comments
    assert "sheet1" in comments, (
        "the comment must name `Sheet1` — the actual default title Lark gives every tab, "
        "which is what makes the old example a trap")


def test_ac3_the_recipe_names_its_client_variable_after_the_write_class():
    """AC3 (F8): the recipe's client variable is NOT the read recipe's ``client`` — it is
    named for the write class it holds, so the two recipes cannot be confused."""
    src = gr.recipe_source("the-sheets-write-handshake")
    assert "SheetsWriteClient" in src
    assert re.search(r"^\s*write_client\s*=\s*SheetsWriteClient", src, flags=re.MULTILINE), src
    assert not re.search(r"^\s*client\s*=", src, flags=re.MULTILINE), (
        "the sheets WRITE recipe must not reuse the read recipe's bare `client` name:\n"
        + src)
    assert "dry_run(requests, write_client" in src, src


def test_ac3_sheets_dry_run_types_its_client_parameter():
    """AC3 (F8): the shipped ``dry_run`` / ``apply`` ANNOTATE their client parameter with
    the class a consumer must pass — ``inspect.signature`` now answers F8's question."""
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    for fn in (dry_run, apply):
        ann = inspect.signature(fn).parameters["client"].annotation
        assert ann is not inspect.Parameter.empty, f"{fn.__name__}'s client is untyped"
        assert "SheetsWriteClient" in str(ann), f"{fn.__name__}: {ann!r}"


def test_ac3_the_docx_and_sheets_write_clients_are_named_in_the_guide():
    """AC3/F8: both write-client classes are named in the guide, so neither recipe leaves
    the consumer guessing which class a ``client`` parameter wants."""
    text = _guide_text()
    assert "SheetsWriteClient" in text and "WriteClient" in text


# --------------------------------------------------------------------------- #
# AC4 — the .env story + domain= (F10 + F11).                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("spec", gr.RECIPE_SPECS, ids=lambda s: s.slug)
def test_ac4_every_recipe_opens_with_the_env_init_line(spec):
    """AC4 (F10): every Python recipe's FIRST statement after its imports is the
    ``init_env`` call — without it nothing reads credentials from the environment.

    **TRANSFORMED, not weakened, by LD-518** — the reason above is the original and is
    unchanged, and it is a claim about a recipe that *reads credentials*. The narrow class
    it does not cover is a recipe that reaches nothing: ``compose_check`` compiles a string
    offline, so opening its recipe with ``init_env(...)`` would teach a credential step that
    is not needed, on a page whose whole promise is that a recipe runs as pasted. Such a
    recipe declares ``needs_no_credentials=True`` on its spec, and the guard then bites the
    OTHER way — it must not carry the line at all — so the exemption cannot be used to
    smuggle the omission into a recipe that really does read the environment. That the
    declaration is TRUE is proved elsewhere by execution, not by this assertion:
    ``test_ac7_recipe_executes_from_a_cwd_with_no_env_file`` runs every recipe with no
    ``.env`` in reach.
    """
    if spec.needs_no_credentials:
        for src in gr.recipe_sources(spec.slug):
            assert "init_env(" not in src, (
                f"recipe {spec.slug!r} declares needs_no_credentials but calls init_env(...) "
                f"— drop the declaration or drop the call")
        return
    for src in gr.recipe_sources(spec.slug):     # LD-445: every block, not just the first
        code = [ln for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        non_import = [ln for ln in code
                      if not ln.startswith(("from ", "import ", " ", ")", "\t"))]
        assert non_import, src
        assert non_import[0].startswith("init_env("), (
            f"recipe {spec.slug!r} must open with init_env(...); first statement was "
            f"{non_import[0]!r}")
        assert "init_env" in src.split("init_env(")[0] or "import" in src, src


#: The shapes that put bytes on disk, WIDENED by LD-512 from ``.write_text(`` + an inline
#: ``open(..., "w"/"a")`` — two spellings behind a docstring claiming the whole class ("Every
#: recipe is checked, not just the ones known to write today"). No shipped recipe uses any of
#: the added shapes today, so this is guard REACH, not a live defect; the point is that the
#: next recipe to reach for one is caught rather than trusted.
#:
#: **What it now sees:** ``.write_text(`` · ``.write_bytes(`` · ``open(..., "w"/"a"/"wb"/…)``
#: written inline · ``json.dump(obj, fh)`` and ``<mod>.dump(obj, fh)`` onto a handle opened
#: anywhere · ``shutil.copy``/``copy2``/``copyfile``/``copytree``/``move`` ·
#: ``os.rename``/``os.replace``/``os.link``/``os.symlink`` · ``pathlib``-free
#: ``urlretrieve(`` · a bare ``os.makedirs(``/``.mkdir(``, which is a directory rather than a
#: file but is the tell that a write is about to follow (and the LD-485 defect — littering the
#: repository's own cwd — is a directory defect as much as a file one).
#:
#: **What it still CANNOT see, stated so the docstring's class-wide claim is honest.** It is a
#: source-text grep, so it is blind to: a write reached through an alias or an attribute it
#: cannot spell (``writer = fh.write`` then ``writer(...)``, ``getattr(fh, "write")``); a write
#: inside a library the recipe calls (``df.to_csv(path)``, ``fig.savefig(path)``, any
#: third-party helper); a handle whose ``open`` mode is a variable rather than a literal
#: (``open(path, mode)``); ``os.open``/``os.write`` at the file-descriptor level;
#: ``subprocess``/``os.system`` shelling out to a redirect; and anything built by string
#: concatenation or ``exec``. A recipe that persists through one of those still has to declare
#: ``persists_to_disk`` by its author's own honesty — the guard bounds the common case, it does
#: not prove the negative.
_PERSISTS_TO_DISK_PATTERN = re.compile(
    r"""\.write_text\(                          # pathlib text write
      | \.write_bytes\(                         # pathlib binary write (LD-512)
      | \bopen\([^)]*["']a?[wx]b?\+?["']        # builtin open in a writing mode, inline
      | \b\w*\.?dump\(\s*[^)]*,\s*\w        # json/pickle/yaml .dump(obj, handle) (LD-512)
      | \bshutil\.(copy2?|copyfile|copytree|move)\(   # (LD-512)
      | \bos\.(rename|replace|link|symlink)\(   # (LD-512)
      | \burlretrieve\(                         # (LD-512)
      | \bos\.makedirs\( | \.mkdir\(           # the tell that a write follows (LD-512)
    """,
    re.VERBOSE,
)


@pytest.mark.parametrize("spec", gr.RECIPE_SPECS, ids=lambda s: s.slug)
def test_ac_ld485_a_recipe_that_writes_a_file_declares_persists_to_disk(spec):
    """LD-485: closes the CLASS, not the instance. ``persists_to_disk`` (LD-445) had been
    asserted for exactly one recipe by name (``test_file_first_routing.py``), so the next
    recipe whose shipped block writes a file (``.write_text(`` / ``open(..., "w"/"a")``) was
    free to repeat the bug the flag exists to prevent — a file written into the repository's
    own cwd on every suite run instead of into a scratch directory. Every recipe is checked,
    not just the ones known to write today.

    **Scope of "checked" (LD-512).** Every recipe, yes — but by a source-text grep, so what is
    checked is the WRITING SHAPES :data:`_PERSISTS_TO_DISK_PATTERN` can spell. That was two
    spellings when this docstring was written and is nine now; the shapes it still cannot see
    are enumerated at the constant, because a class-wide claim standing on an unstated
    exclusion list is the defect this file exists to catch, one level up."""
    writes = any(_PERSISTS_TO_DISK_PATTERN.search(src) for src in gr.recipe_sources(spec.slug))
    if writes:
        assert spec.persists_to_disk, (
            f"recipe {spec.slug!r} writes a file but does not declare "
            "persists_to_disk=True — it will litter the repository root on every run")


def test_ac4_non_recipe_blocks_are_exempt_only_because_they_need_no_credentials():
    """AC4 (the exemption cannot be abused): a python block OUTSIDE the Recipes section
    skips the ``init_env`` line only if it constructs no client and resolves no
    credentials. The moment one does, it must become a recipe."""
    offenders = []
    for block in gr.python_blocks():
        if block.slug is not None:
            continue
        if any(n in block.source for n in (
                "Client(", "from_read_credentials", "from_write_credentials",
                "get_read_credentials", "get_write_credentials")):
            offenders.append(block.source)
    assert not offenders, (
        "a non-recipe guide block touches credentials but has no init_env line: "
        f"{offenders}")


def test_ac4_the_guide_documents_what_domain_means():
    """AC4 (F11): ``domain=`` is documented as the **API** domain, not the tenant host —
    the dogfood target was ``your-domain.larksuite.com`` while ``domain='larksuite.com'``."""
    text = _guide_text()
    assert "`domain=`" in text or "domain=" in text
    low = text.lower()
    assert "api domain" in low, "the guide must call domain= the API domain"
    assert "tenant" in low, "the guide must contrast it with the tenant host"
    # the contrast must be concrete: a subdomained tenant host mapped to the API domain.
    assert re.search(r"[a-z0-9-]+\.(sg\.)?larksuite\.com", low), (
        "the domain= note must show a real subdomained tenant host next to the API domain")


def test_ac4_init_env_is_load_bearing_in_the_write_recipe(monkeypatch, tmp_path):
    """AC4 (red-then-green — the line is not decoration): running the docx-write recipe
    with its ``init_env`` line DELETED fails to resolve credentials, and the shipped
    recipe succeeds. This is F10 reproduced and then closed."""
    from larkdocio.errors import LarkConfigError

    src = gr.recipe_source("the-docx-write-handshake")
    without = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("init_env("))
    assert without != src, "the recipe has no init_env line to delete"

    st = gr.stage(monkeypatch, tmp_path)
    with pytest.raises((LarkConfigError, AssertionError, ValueError)):
        st.run("the-docx-write-handshake", source=without)

    ns = st.run("the-docx-write-handshake")
    assert st.init_env_calls, "the shipped recipe never called init_env"
    gr._check_docx_write(ns)


# --------------------------------------------------------------------------- #
# AC5 — the empty-document recipe (F15).                                        #
# --------------------------------------------------------------------------- #

def test_ac5_an_empty_document_recipe_ships():
    """AC5 (F15): the guide documents writing into a document with NO body blocks, and
    names ``APPEND_INTO`` the page node as the way in."""
    assert "### Recipe: write into an empty document" in _guide_text()
    section = _section("### Recipe: write into an empty document")
    assert "APPEND_INTO" in section
    low = section.lower()
    assert "page" in low, section
    assert "no body blocks" in low or "no quote" in low, section


def test_ac5_the_empty_doc_recipe_anchors_on_the_page_node():
    """AC5: the recipe anchors on the PAGE node (the document title) rather than on a body
    quote there is none of."""
    src = gr.recipe_source("write-into-an-empty-document")
    assert "APPEND_INTO" in src and "block_plain_text" in src, src
    assert "NewParagraph" in src, src


# --------------------------------------------------------------------------- #
# AC6 — the compact human rendering of capabilities() (F12).                     #
# --------------------------------------------------------------------------- #

def test_ac6_the_guide_shows_the_json_dumps_rendering_hint():
    """AC6 (F12): the guide shows ``json.dumps(capabilities(), indent=2)`` as the readable
    form — the smallest honest fix (no ``__str__`` change)."""
    text = _guide_text()
    assert re.search(r"json\.dumps\(\s*(larkdocio\.)?capabilities\(\)\s*,\s*indent=2\s*\)", text), (
        "the guide must show json.dumps(capabilities(), indent=2)")
    assert "import json" in text


def test_ac6_capabilities_has_no_str_override():
    """AC6: explicitly NOT changed — ``capabilities()`` still returns a plain ``dict``
    (a ``__str__`` subclass would be the bigger, riskier fix the AC rules out)."""
    caps = capabilities(full=True)
    assert type(caps) is dict


def test_ac6_the_shown_rendering_actually_works():
    """AC6: the hint is executable and readable — the rendered form is multi-line, unlike
    the ~4KB single-line wall F12 reported."""
    rendered = json.dumps(capabilities(full=True), indent=2)
    assert rendered.count("\n") > 100
    assert json.loads(rendered) == capabilities(full=True)


# --------------------------------------------------------------------------- #
# AC7 — EVERY recipe EXECUTES offline (the extract-and-run harness).             #
# --------------------------------------------------------------------------- #

def test_ac7_every_guide_recipe_has_an_execution_spec_and_vice_versa():
    """AC7 (anti-rot): the recipe headings in the guide and the execution specs in the
    harness are 1:1 — a new recipe with no spec, or a spec whose recipe was renamed away,
    reddens here."""
    in_guide = sorted(gr.recipe_blocks())
    specced = sorted(gr.SPEC_BY_SLUG)
    assert in_guide == specced, (
        f"guide recipes {in_guide} != execution specs {specced}")


def test_ac7_every_recipe_block_is_declared_and_executed():
    """AC7: every runnable python block of every recipe is executed and checked (the bash CLI
    blocks are separate).

    **Was "one recipe, one python block" until LD-445**; the *reason* — no block may sit in
    the guide unrun, and ``recipe_source`` must be unambiguous — is unchanged and now bites
    per block: a recipe may carry extra blocks only by declaring one post-condition per extra
    block in ``RECIPE_SPECS``, so an undeclared second fence still fails here. The one recipe
    that does declare extras is the copy-this script's **file-first variant**, which is a
    second block precisely so the harness can run it in a namespace of its own."""
    for slug, blocks in gr.recipe_blocks().items():
        declared = 1 + len(gr.SPEC_BY_SLUG[slug].extra_checks)
        assert len(blocks) == declared, (
            f"recipe {slug!r} has {len(blocks)} python blocks but declares {declared}")


@pytest.mark.parametrize("spec", gr.RECIPE_SPECS, ids=lambda s: s.slug)
def test_ac7_recipe_executes_offline(spec, monkeypatch, tmp_path):
    """AC7 — **the load-bearing test**: the recipe is extracted from the shipped guide
    VERBATIM and executed in a builtins-only namespace against fixtures + injected
    transports, then checked for what it claims to produce.

    A guide edit that breaks a recipe (an undefined variable, a renamed symbol, a wrong
    example, a dropped step) fails here — which is exactly what LD-128's ``compile()``
    gate could not do."""
    # LD-445: every block, each against a fresh stage and in a namespace of its own.
    gr.run_and_check(spec, monkeypatch, tmp_path)


@pytest.mark.parametrize("spec", gr.RECIPE_SPECS, ids=lambda s: s.slug)
def test_ac7_recipe_executes_from_a_cwd_with_no_env_file(spec, monkeypatch, tmp_path):
    """LD-430 — the stage insulates every recipe from the AMBIENT ``<cwd>/.env``.

    The bug: ``drive.read._read_docx_markdown`` calls ``init_env`` through **its own**
    module binding (``read.download.init_env``, bound by ``from larkdocio.common import
    init_env``), which the stage's ``common.init_env`` patch never reached. The real
    ``init_env`` then **bootstrapped an empty ``.env`` into the cwd** and loaded it with
    ``override=True``, clobbering the stage's offline credentials to ``""`` — so the folder
    recipe's docx child was skipped ("constructed with empty credentials") and
    ``_check_read_folder`` saw zero reads. It looked order-dependent because on a machine
    whose cwd *did* carry a populated ``.env`` the clobber restored working credentials.

    So: run every recipe from a cwd with **no** ``.env``, and assert the run neither fails
    nor writes one. A harness that reads or creates a file in the cwd is not offline.
    """
    cwd = tmp_path / "empty-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    gr.run_and_check(spec, monkeypatch, tmp_path)

    assert not (cwd / ".env").exists(), (
        "a recipe run bootstrapped a .env into the cwd — the shipped init_env ran "
        "unpatched somewhere in the chain")


def test_ac7_the_stage_leaves_no_unpatched_init_env_binding(monkeypatch, tmp_path):
    """LD-430 (anti-rot): with a stage installed, **no** imported ``larkdocio`` module still
    binds the real ``init_env``.

    ``from larkdocio.common import init_env`` makes a per-module copy, so patching one
    module's attribute is never enough. This guard fails the moment a new module takes such
    a binding without the stage learning about it — the drift that produced LD-430.
    """
    gr.stage(monkeypatch, tmp_path)

    unpatched = sorted(
        name for name, module in list(sys.modules.items())
        if name.split(".")[0] == "larkdocio"
        and getattr(module, "init_env", None) is gr.REAL_INIT_ENV
    )
    assert unpatched == [], (
        f"these modules still call the real init_env under a stage: {unpatched}")


def test_ac7_the_execution_harness_bites_when_a_recipe_breaks(monkeypatch, tmp_path):
    """AC7 (red-then-green on the harness): the SAME runner that greens the shipped recipe
    fails on a mutated one — so the guard is not vacuous."""
    src = gr.recipe_source("the-docx-write-handshake")

    # (a) the F13 mutation: drop the parse step that produces `root`.
    broken = "\n".join(
        ln for ln in src.splitlines() if "parse_docx_tree" not in ln)
    st = gr.stage(monkeypatch, tmp_path)
    with pytest.raises(NameError):
        st.run("the-docx-write-handshake", source=broken)

    # (b) a renamed public symbol in an import line.
    renamed = src.replace("parse_docx_tree", "parse_docx_treee")
    with pytest.raises(AttributeError):
        st.run("the-docx-write-handshake", source=renamed)

    # (c) the shipped text greens the very same runner.
    gr._check_docx_write(st.run("the-docx-write-handshake"))


def test_ac7_the_sheets_recipe_would_have_failed_with_the_old_title_range(
        monkeypatch, tmp_path):
    """AC7 (F4 reproduced): the pre-fix A1 range (a tab TITLE) refuses through the very
    same offline engine the fixed recipe applies through — the trap is real, and the fix
    is what removes it."""
    src = gr.recipe_source("the-sheets-write-handshake")
    st = gr.stage(monkeypatch, tmp_path)

    trapped = re.sub(r"f\"\{sheet_id\}!", 'f"Sheet1!', src)
    assert trapped != src, "could not build the title-shaped mutation"
    ns = st.run("the-sheets-write-handshake", source=trapped)
    outcomes = [e.to_dict()["outcome"] for e in ns["log"].entries]
    assert outcomes == ["refused"], (
        f"a title-shaped range must refuse, not write: {[e.to_dict() for e in ns['log'].entries]}")

    ns_ok = st.run("the-sheets-write-handshake")
    gr._check_sheets_write(ns_ok)


@pytest.mark.parametrize("slug", ["download-a-docx-to-markdown", "the-docx-write-handshake"])
def test_ac7_the_url_bearing_recipes_run_from_a_wiki_url_too(slug, monkeypatch, tmp_path):
    """AC7 (**URL-bearing steps parameterized**): the recipes claim to start "from a URL",
    so the URL is swapped for a **wiki** one and the recipe re-run.

    This exercises the ``doc_type == "wiki"`` branch — a wiki URL carries a *node* token
    that must be resolved to the real docx token before any block read. Without the branch
    a wiki URL silently yields an empty document and every anchor refuses ``not-found``,
    which is the same class of bug F13 was."""
    src = gr.recipe_source(slug)
    wiki = src.replace("/docx/YOURDOCTOKENHERE", "/wiki/YOURWIKINODETOKEN")
    assert wiki != src, "the recipe does not start from a substitutable docx URL"

    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run(slug, source=wiki)
    assert ns["doc_type"] == "docx", (
        "the recipe left doc_type as 'wiki' — the wiki node was never resolved")
    assert ns["doc_token"] == "YOURWIKINODETOKEN"
    gr.SPEC_BY_SLUG[slug].check(ns)


def test_ac7_the_offline_doubles_have_not_drifted_from_the_shipped_clients():
    """AC7 (harness integrity): each offline double's public methods still match the
    shipped client class it stands in for — so a recipe cannot pass here against an API
    that no longer exists."""
    problems = gr.double_signature_mismatches()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("spec", gr.RECIPE_SPECS, ids=lambda s: s.slug)
def test_ac7_recipes_execute_against_no_network(spec, monkeypatch, tmp_path):
    """AC7: a recipe run opens **no socket** — proven by making socket creation raise for
    the duration of the run, not by inspecting the source.

    The offline doubles must cover the *whole* HTTP boundary; if one ever stopped covering
    it, the recipe would reach for the network and this reddens instead of the suite
    silently starting to need credentials (PROJECT.md § the offline floor)."""
    import socket

    def _no_sockets(*a, **k):
        raise AssertionError(
            f"recipe {spec.slug!r} tried to open a socket — the offline doubles no longer "
            "cover the whole HTTP boundary")

    monkeypatch.setattr(socket, "socket", _no_sockets)
    monkeypatch.setattr(socket, "create_connection", _no_sockets)
    gr.run_and_check(spec, monkeypatch, tmp_path)


# --------------------------------------------------------------------------- #
# AC8 — the guide↔capabilities() drift guard covers the new couplings.           #
# --------------------------------------------------------------------------- #

def test_ac8_the_guide_matrix_documents_the_floor_field():
    """AC8: the guide's capability matrix carries the docx-write floor, so the new
    ``content_constraints`` field cannot exist in ``capabilities()`` and be invisible in
    the guide (the F14 failure mode, one level up)."""
    from test_guide import _matrix_region

    region = _matrix_region()
    assert "NewParagraph" in region, (
        "the capability matrix must state the docx-write creatable-content floor")


def test_ac8_the_floor_guard_bites_red_then_green():
    """AC8 (red-then-green): the guide↔capabilities floor coupling is checked by a real
    comparison that fails on a divergence and greens on truth."""
    from test_guide import _guide_content_constraints, _phantom_and_missing

    truth = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]["creatable"]
    documented = _guide_content_constraints()

    phantom, missing = _phantom_and_missing(documented, truth)
    assert not phantom and not missing, (documented, truth)

    # drift in either direction is caught by the SAME check.
    p1, m1 = _phantom_and_missing(documented + ["NewTable"], truth)
    assert p1 == ["NewTable"] and not m1
    p2, m2 = _phantom_and_missing([], truth)
    assert not p2 and m2 == sorted(truth)


# --------------------------------------------------------------------------- #
# The LD-132 fix-round nit routed here: the "six families" paragraph named five. #
# LD-149 added the SEVENTH family (formula), so the count is now DERIVED from    #
# the registry — a hard-coded digit is exactly what let the nit survive once.    #
# --------------------------------------------------------------------------- #

#: The count word is captured too, so the prose's stated number is checked against the
#: registry rather than trusted (the count-is-derived discipline, cf. LD-140).
_FAMILIES_RE = re.compile(r"([A-Za-z]+) request families[^(]*\(([^)]*)\)")

#: The ONE word→number table in the suite (LD-213 AC6). It was two hand-kept copies with
#: DIFFERENT ceilings — this one stopped at ``"ten"`` and ``test_guide_sheets_completion``'s
#: stopped at ``"eight"``, one landing away from raising ``KeyError: 'nine'`` instead of failing
#: with its own message the moment a ninth **op** shipped. Built by enumeration so it has no
#: hand-kept ceiling at all, and read through :func:`count_word` so an unknown word fails with a
#: sentence rather than a traceback.
_COUNT_WORDS = {
    word: number for number, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())
}


def count_word(word: str) -> int:
    """``"nine"`` → ``9``. The shared reader for every doc guard that checks a stated count.

    Raises an ``AssertionError`` naming the word — never a ``KeyError`` — because a guard whose
    own lookup explodes tells the next Dev nothing about which document is wrong."""
    number = _COUNT_WORDS.get(word.strip().strip("*").lower())
    assert number is not None, (
        f"{word!r} is not a count word this suite knows — extend _COUNT_WORDS in "
        f"tests/test_discovery_truth.py (the ONE table; do not start a second one)")
    return number


def _families_match():
    section = _section("### Recipe: the sheets write handshake")
    m = _FAMILIES_RE.search(section)
    assert m, "the guide must name the sheets request families inline, with a count word"
    return m


def _named_families() -> list:
    # families are separated by "/"; a "·" joins the variants WITHIN one family
    # (merge·unmerge is one family, not two).
    return [p.strip().strip("`") for p in _families_match().group(2).split("/") if p.strip()]


def _expected_family_count() -> int:
    """Every projected sheets-write op kind is a family, **plus** the rich-cell request
    family — which is a request *type* of the ``value`` op rather than an op kind of its own
    (the next test pins exactly that, and it is how rich-cell went missing from a list keyed
    on op kinds)."""
    return len(rows.names(capabilities(full=True)["surfaces"]["sheets-write"], rows.OPERATION)) + 1


def test_the_sheets_request_families_paragraph_names_them_all():
    """LD-132's routed nit: the guide's sheets-write intro said "Six request families" and
    then listed **five** — rich-cell was missing. The stated count must match the list AND
    the registry, so LD-149's seventh family could not be added without saying so."""
    named = _named_families()
    expected = _expected_family_count()
    stated = count_word(_families_match().group(1))

    assert stated == expected, (
        f"the guide says {_families_match().group(1)!r} request families; the registry has "
        f"{expected} (every projected op kind + the rich-cell request family)")
    assert len(named) == expected, f"the count says {expected} but the list has {len(named)}: {named}"
    joined = " ".join(named).lower()
    for family in ("value", "formula", "rich", "dropdown", "structural", "merge", "tab"):
        assert family in joined, f"the families list must name {family!r}: {named}"


def test_the_named_families_cover_every_projected_sheets_write_op():
    """The families the guide names in prose cover every op ``capabilities()`` projects off
    ``sheets/ops/``, so the list cannot silently drift from the registry."""
    truth = set(rows.names(capabilities(full=True)["surfaces"]["sheets-write"], rows.OPERATION))
    joined = " ".join(_named_families()).lower()
    for op in sorted(truth):
        assert op[:4] in joined, (
            f"projected sheets-write op {op!r} is not in the guide's family list")


def test_the_sixth_family_exists_in_code_which_is_why_it_must_be_named():
    """The nit's code anchor: ``RichCellWriteRequest`` is a **projected request type** of
    the ``value`` op — a distinct request family whose name is not any op *kind*, which is
    exactly how it went missing from a list keyed on op kinds. It exists in the projection,
    so the guide must name it."""
    ops = rows.by_name(capabilities(full=True)["surfaces"]["sheets-write"], rows.OPERATION)
    assert "RichCellWriteRequest" in ops["value"]["request_types"], ops["value"]
    assert "ValueWriteRequest" in ops["value"]["request_types"], ops["value"]
    joined = " ".join(_named_families()).lower()
    assert "rich" in joined, "the rich-cell family is in the projection but not the guide"
