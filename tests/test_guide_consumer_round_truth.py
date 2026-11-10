"""LD-319 — the five guide-truth corrections the first 1.27.0 Base consumer's round earned.

The consumer read the shipped guide as their **entire** contract (they never needed the external
API docs) and hit five places where the document was true in principle and unusable in
practice. This project holds a shipped document to the same bar as code, so each correction gets
a guard rather than a promise. One test class per group, in the issue's AC order:

* **AC1** — the structural-handshake recipe's DELETE portion: the ``read_client=`` keyword a
  destructive ``schema_dry_run`` requires, the two import lines nobody can guess
  (``consent_to_destroy`` is in ``schema_apply``; the delete verbs are in
  ``schema_ops_destructive``), and the recipe's own internal contradiction resolved.
* **AC2** — the *"where refusals happen, and when"* taxonomy: three channels, one table,
  deliberately **not** unified.
* **AC3** — the locale-named default primary column, stated as a route and **not** as an
  argument this library accepts.
* **AC4** — section addressability said at the ENTRY of the journey, not 5,000 lines down.
* **AC5** — the READ/WRITE pairs may alias one app, said in both setup surfaces, with the
  doctrine intact.

Every assertion here reads the SHIPPED text (``larkdocio.guide()``), never a source file, so a
guard cannot pass against a document the wheel does not carry.
"""
import importlib
import pathlib
import re
import sys

import pytest

import larkdocio
from larkdocio import guide, guide_sections

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import guide_recipes as gr  # noqa: E402  — tests/ is on sys.path (conftest)
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

_HANDSHAKE = "recipe-create-rename-and-copy-a-base-the-structural-handshake"
#: the same recipe as ``guide_recipes`` slugs it — that helper drops the ``Recipe: `` prefix.
_HANDSHAKE_RECIPE = "create-rename-and-copy-a-base-the-structural-handshake"
_TAXONOMY = "where-refusals-happen-and-when-the-three-channels"


def _prose(text: str) -> str:
    """Collapse wrapping and emphasis so a line break can never decide a test."""
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", ""))


def _comment_prose(text: str) -> str:
    """:func:`_prose` for a shell-comment surface (``.env.example``): the ``#`` that opens each
    wrapped line is punctuation of the file format, not of the sentence, so it comes off before
    the collapse — otherwise a wrapped sentence could never be asserted at all."""
    return _prose("\n".join(re.sub(r"^\s*#\s?", "", line) for line in text.splitlines()))


# --------------------------------------------------------------------------- #
# AC1 — the destructive portion RUNS, and the delete tension is decided.        #
# --------------------------------------------------------------------------- #

class TestAC1DestructiveRecipePortion:

    def test_the_destructive_dry_run_passes_read_client(self):
        """Friction 3, the whole of it: ``schema_dry_run`` refuses a destructive request
        without ``read_client=``, and not one call in the guide passed it."""
        source = gr.recipe_source(_HANDSHAKE_RECIPE)
        destructive = [line for line in source.splitlines() if "delete_field(" in line]
        assert destructive, "the recipe carries no delete at all"
        assert re.search(r"schema_dry_run\(\[delete_field\([^\n]*\n?[^\n]*read_client=read",
                         source), source
        # ...and nothing in the whole guide builds a destructive plan without one.
        for block in gr.python_blocks():
            for call in re.finditer(r"schema_dry_run\((.{0,400}?)\)\s*\n", block.source,
                                    re.DOTALL):
                body = call.group(1)
                if "delete_field(" in body or "delete_table(" in body:
                    assert "read_client=" in body, body

    def test_the_two_import_lines_nobody_can_guess_are_both_present_and_both_resolve(self):
        """The consumer guessed ``schema_ops_destructive`` for ``consent_to_destroy``. Both
        halves are now written down — and imported here, so a module rename cannot leave the
        guide teaching a path that no longer exists."""
        source = gr.recipe_source(_HANDSHAKE_RECIPE)
        assert ("from larkdocio.base.schema_apply import consent_to_destroy, schema_apply, "
                "schema_dry_run") in source
        assert "from larkdocio.base.schema_ops_destructive import delete_field" in source
        assert hasattr(importlib.import_module("larkdocio.base.schema_apply"),
                       "consent_to_destroy")
        assert hasattr(importlib.import_module("larkdocio.base.schema_ops_destructive"),
                       "delete_field")
        # The one thing the guide must NOT do is repeat the consumer's wrong guess.
        assert not hasattr(importlib.import_module("larkdocio.base.schema_ops_destructive"),
                          "consent_to_destroy"), (
            "if consent_to_destroy ever moves here, the recipe's prose about the split is "
            "stale and must be rewritten with it")

    def test_the_consent_is_minted_from_the_destructive_plan_itself(self):
        source = gr.recipe_source(_HANDSHAKE_RECIPE)
        assert "consent=consent_to_destroy(loss_plan)" in source, source

    def test_the_recipe_no_longer_contradicts_itself_about_deletes(self):
        """The tension LD-319 AC1 required a DECISION on: the recipe said *"Deleting IS
        available"* near the top and *"Deleting a Base, a table or a field is not on this
        path"* at the bottom. Only one of those can be true. The ruling: deletes of a **table**
        and a **field** ARE on this path (step 5 runs one); only a **Base** delete is nowhere,
        because Lark's route trashes rather than purges.

        **TRANSFORMED, not struck (LD-466), and the reason is kept.** The tension this guard was
        written for is unchanged and is still asserted: the recipe may not promise a delete in one
        paragraph and deny it in another. What changed is which sentence is the true one. Lark's
        route still trashes rather than purges — re-measured, and the trash is now *disclosed* by
        the verb instead of used as a reason to withhold it — so a **Base** delete is no longer
        nowhere: it is `delete_base`, off the plan-gated path (no plan, no consent token) and
        taught in this same section. So the guard now pins the third statement too, which is the
        one that would go stale if the verb were ever removed without the prose following it.
        """
        section = _prose(guide(section=_HANDSHAKE))
        assert "Deleting IS available, it is taught HERE" in section
        assert "Deleting a BASE is not on the PLAN-GATED path" in section
        assert "Deleting a Base, a table or a field is not on this path" not in section, (
            "the retired sentence is back, and it contradicts step 5")
        assert "Deleting a BASE is not on this path — and it is not on any path" not in section, (
            "the superseded sentence is back, and it contradicts the delete_base block below it")
        assert "Deleting a table or a field IS on this path" in section
        assert "delete_base(app_token)" in section, (
            "the section teaches the whole-object delete; if the verb goes, this prose must too")
        assert "trash" in section.lower(), (
            "the ORIGINAL reason survives as a disclosure — a delete taught without its trash "
            "semantics would be the worse half of the old contradiction")

    def test_the_three_delete_rows_point_at_the_recipe_that_actually_teaches_them(self):
        """A map is a pointer, and these three pointed at a recipe whose code never calls
        them."""
        matrix = guide(section="every-operation-and-where-it-is-taught")
        for op in ("delete_table", "batch_delete_tables", "delete_field"):
            row = [line for line in matrix.splitlines() if line.startswith(f"| `{op}` ")]
            assert len(row) == 1, op
            assert "structural handshake" in row[0], row[0]


# --------------------------------------------------------------------------- #
# AC2 — the refusal taxonomy: named ONCE, three channels, NOT unified.          #
# --------------------------------------------------------------------------- #

class TestAC2RefusalTaxonomy:

    def test_the_section_ships_with_a_derived_slug(self):
        index = {row["slug"]: row for row in guide_sections()}
        assert _TAXONOMY in index, sorted(index)
        assert index[_TAXONOMY]["level"] == 2
        assert index[_TAXONOMY]["heading"] == (
            "Where refusals happen, and when — the three channels")

    def test_all_three_channels_are_in_ONE_table_each_with_the_four_facts(self):
        section = guide(section=_TAXONOMY)
        rows = [line for line in section.splitlines()
                if line.startswith("| **") and line.count("|") == 6]
        assert len(rows) == 3, rows
        for wanted in ("Op-build exception", "Plan-entry refusal",
                       "Apply-time refusal, surfaced by read-back"):
            assert any(wanted in row for row in rows), (wanted, rows)
        header = [line for line in section.splitlines() if line.startswith("| Channel")]
        assert len(header) == 1, header
        for column in ("What it looks like in your code", "When it fires", "What it costs",
                       "How you detect it"):
            assert column in header[0], column

    def test_each_channel_names_a_real_refusal_class_or_field_of_the_shipped_engine(self):
        """A taxonomy that named channels the code does not have would be worse than none."""
        section = guide(section=_TAXONOMY)
        authoring = importlib.import_module("larkdocio.base.field_authoring")
        vocabulary = importlib.import_module("larkdocio.base.field_vocabulary")
        for name, module in (("UnauthorableFieldError", vocabulary),
                             ("UncapturedFieldPairError", vocabulary),
                             ("UncapturedFieldPropertyError", authoring),
                             ("RefutedFieldAuthoringError", authoring),
                             ("UncapturedConversionError", authoring),
                             ("SelectOptionIdRequiredError", authoring)):
            assert name in section, name
            assert hasattr(module, name), name
        assert "entry.refusal is not None" in section        # channel 2's detector
        assert "entry.refusal.detail" in section             # channel 3's reason

    def test_the_section_says_the_three_are_NOT_unified_and_states_the_ask(self):
        """The ask is stated, not quoted: LD-703 (round 5, V3) paraphrased the consumer's own
        words, which this assertion used to pin verbatim."""
        section = _prose(guide(section=_TAXONOMY))
        assert "The three are deliberately NOT unified" in section
        # LD-715 (owner ruling 2026-11-07): the decision is stated on its own terms, not as
        # what was asked for; the substance pinned here — not unified, the timing differences
        # justified, the taxonomy named once — is unchanged.
        assert "the timing differences are justified" in section
        assert "only the taxonomy is named once" in section
        assert "Not asking to unify them" not in section

    def test_the_section_is_not_a_recipe_and_therefore_takes_no_execution_spec(self):
        """AC6: no ``python`` fence ⇒ not a recipe ⇒ no ``RECIPE_SPECS`` entry, and the
        recipe↔spec 1:1 pairing is untouched by this section's arrival."""
        assert "```python" not in guide(section=_TAXONOMY)
        assert _TAXONOMY not in gr.SPEC_BY_SLUG
        assert sorted(gr.SPEC_BY_SLUG) == sorted(
            gr._slug(heading) for heading in gr.recipe_headings())


# --------------------------------------------------------------------------- #
# AC3 — the locale-named primary column: a ROUTE, and no phantom argument.      #
# --------------------------------------------------------------------------- #

class TestAC3LocaleNamedPrimaryField:

    def test_the_recipe_REFUSES_a_nameless_create_and_says_what_that_PREVENTS(self):
        """**LD-322 amended this section to the landed truth.** LD-319 shipped the warning that
        the primary column arrives locale-named; LD-322 stopped it arriving at all. The locale
        default is now what the refusal *prevents*, and the concrete reported name stays — it is
        what makes the warning checkable rather than abstract."""
        section = _prose(guide(section=_HANDSHAKE))
        assert "WILL NOT CREATE A TABLE WHOSE PRIMARY COLUMN YOU DID NOT NAME" in section
        assert "refuses before any call is made" in section
        assert "多行文本" in section, "the reported name is the concrete part of the warning"
        assert 'create_table(app_token, "Items", primary_field_name="Title")' in section
        assert "its first entry is the primary one" in section

    def test_the_recipe_says_the_BATCH_verb_asks_for_an_ACKNOWLEDGEMENT_instead(self):
        """The asymmetry is the measurement: Lark ignores a kit on the batch route, so a name
        cannot be honoured there and the silence is made explicit instead."""
        section = _prose(guide(section=_HANDSHAKE))
        assert "CANNOT NAME A PRIMARY COLUMN, SO IT ASKS YOU TO SAY SO OUT LOUD" in section
        assert "accept_locale_default_primary=True" in section

    def test_the_RENAME_sentence_still_claims_a_ROUTE_and_not_a_MEASUREMENT(self):
        """Renaming an EXISTING table's primary column is untouched by LD-322, and the sentence
        that says so must still not read as a live-verified flow — it says which call renames
        the column, not that anyone watched it do so on your tenant."""
        section = _prose(guide(section=_HANDSHAKE))
        assert "That rename sentence is a route, not a measurement" in section
        assert "read it rather than assume it" in section

    @private_tree.dev_record
    def test_primary_field_name_LANDED_and_the_downtime_row_is_STRUCK(self):
        """The inverse of what this test used to pin, and deliberately so: LD-319 registered the
        argument as an unanswered question about the endpoint, LD-336 answered it live, and
        LD-322 shipped it. So it MUST now appear in the shipped surface, and the queue row that
        asked for the probe MUST be gone — the file's own removal discipline."""
        carriers = [path.name for path in (REPO_ROOT / "src").rglob("*")
                    if path.is_file() and path.suffix in {".py", ".md"}
                    and "primary_field_name=" in path.read_text(encoding="utf-8")]
        assert "schema_plan.py" in carriers and "GUIDE.md" in carriers, carriers
        register = (REPO_ROOT / "dev" / "downtime-queue.md").read_text(encoding="utf-8")
        assert not [line for line in register.splitlines()
                    if "primary_field_name" in line and line.startswith("|")], (
            "the queue row LD-319 AC3 registered is struck: the item landed in LD-322")


# --------------------------------------------------------------------------- #
# AC4 — the entry pointer is at the ENTRY.                                     #
# --------------------------------------------------------------------------- #

class TestAC4SectionAddressabilityAtTheEntry:

    def test_the_preamble_itself_says_every_heading_is_addressable(self):
        """Friction 8: the accessor existed and was found ~5,400 lines late. The preamble is
        everything above the first ``##`` heading — where a reader actually starts."""
        preamble = guide(full=True).split("\n## ", 1)[0]
        flat = _prose(preamble)
        assert "individually addressable" in flat
        assert "guide_sections()" in flat
        assert "Reading ONE section of this guide" in flat

    def test_the_preamble_example_is_a_slug_that_really_resolves(self):
        preamble = guide(full=True).split("\n## ", 1)[0]
        examples = re.findall(r'guide\(section="([^"]+)"\)', preamble)
        assert examples, preamble
        for slug in examples:
            assert guide(section=slug).startswith("### "), slug

    def test_the_capabilities_half_and_the_preamble_half_agree(self):
        """LD-320 landed the ``capabilities()['docs']`` half; the two must not drift."""
        rows = larkdocio.capabilities(full=True)["docs"]["guide()"]["sections"]
        assert rows == list(guide_sections())

    def test_byte_identical_reassembly_still_holds_over_the_new_preamble(self):
        """The invariant the preamble edit could break: preamble + every ``##`` section,
        concatenated, IS ``guide()``."""
        text = guide(full=True)
        parts = [text[:text.index("\n## ") + 1]]
        parts += [guide(section=row["slug"]) for row in guide_sections() if row["level"] == 2]
        assert "".join(parts) == text


# --------------------------------------------------------------------------- #
# AC5 — the pairs may alias one app, in BOTH setup surfaces.                    #
# --------------------------------------------------------------------------- #

class TestAC5CredentialPairsMayAlias:

    def test_the_shipped_setup_section_says_it(self):
        section = _prose(guide(section="credentials-env-setup-the-read-write-app-split"))
        assert "The two pairs MAY point at the same app" in section
        assert "the split is about ROUTES, not necessarily two registrations" in section

    def test_the_shipped_section_does_NOT_read_as_you_only_need_one_app(self):
        """The one FAIL condition AC5 names. Both consequences PROJECT.md records must survive:
        two apps stays the target, and neither pair may be left unset."""
        section = _prose(guide(section="credentials-env-setup-the-read-write-app-split"))
        assert "Two apps remains the shape to aim for" in section
        assert "no fallback either way" in section
        assert "neither pair may ever be left unset" in section

    @private_tree.process
    def test_the_dev_repo_surface_says_it_AND_cites_the_authority(self):
        env = _comment_prose((REPO_ROOT / ".env.example").read_text(encoding="utf-8"))
        assert "THE PAIRS MAY POINT AT THE SAME APP" in env
        assert "The split is about ROUTES, not necessarily two registrations" in env
        assert 'PROJECT.md § "Credential aliasing (accepted — noted 2026-07-31)"' in env
        # ...and the two binding consequences are restated, not weakened.
        assert "remains the TARGET" in env
        assert "no code may collapse them, infer one from the other, or fall back" in env
        assert (REPO_ROOT / "PROJECT.md").read_text(encoding="utf-8").count(
            "### Credential aliasing (accepted — noted 2026-07-31)") == 1, (
            "the cited section was renamed; the .env.example citation is now a dead pointer")

    @pytest.mark.parametrize("pair", ["READ", "WRITE"])
    def test_no_code_change_came_with_it(self, pair):
        """AC5 is prose only: the resolver still reads the two pairs independently."""
        auth = importlib.import_module("larkdocio.common.auth")
        source = pathlib.Path(auth.__file__).read_text(encoding="utf-8")
        assert f"LARK_{pair}_APP_ID" in source and f"LARK_{pair}_APP_SECRET" in source
        assert "LARK_WRITE_APP_ID" not in source.split("def get_read_credentials", 1)[-1] \
            .split("def ", 2)[0], "the read path must not reach for a WRITE name"
