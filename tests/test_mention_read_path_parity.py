"""LD-173 (dogfood F3 + F4) — @mention resolution on the DOCUMENTED Python read path.

The finding this module makes testable: the guide's own download recipe and the guide's own
download CLI, on the SAME document with the SAME credentials, produced **different Markdown**
— ``@ou_exampleowner…`` from Python, ``@Example User`` from the CLI. The reason was structural: the
resolver lives on ``read.client.Client`` while the recipe built a bare ``Parser``, which had
no seam to reach a client through, so it was not "undocumented", it was *unreachable*.

What is pinned here, and why each pin exists:

* **AC2 — PARITY, ASSERTED.** ``test_the_documented_python_recipe_and_the_cli_produce_the_same_markdown``
  runs the guide's recipe **verbatim** (extracted from the shipped text) over a
  mention-bearing document and runs ``handle_download_command`` over the *same* payload and
  the *same* directory, then compares byte-for-byte. Its absence IS the whole finding.
* **The parity pin BITES.** The mutation probe strips ``read_client=client`` back out of the
  recipe and asserts the pre-fix defect returns — otherwise the parity test is decoration.
* **AC1 / AC6 — the four mention shapes**: one that resolves, one the directory does not
  cover, one whose name fields are all null (the shape the field-scope diagnosis turned on),
  and all three in ONE block (the mixed case). Every unresolved shape keeps its raw
  ``@ou_…``, and a resolver that raises never fails the read.
* **The flag stays honest in both positions** — ``resolve_mentions=False`` keeps ids raw and
  makes **no** contacts call, on the Parser seam and on the download path alike.
* **ZERO-DRIFT** — a ``Parser`` with no ``read_client`` renders exactly what it rendered
  before the seam existed and touches no contacts surface.
* **AC3/AC4/AC5 — the discovery and doc claims**: the flag is in ``capabilities()["flags"]``
  with its default and its precondition; the false authorship claim is gone, replaced by the
  working call under the **changed-precondition** framing; and the precondition's **two**
  halves (the contacts data range AND the field-level scope) are stated where the call is.
"""
import re
from types import SimpleNamespace

import pytest

import guide_recipes as gr
import larkdocio
from doc_prose import missing_phrases, prose
from harness import build_blocks
from larkdocio.capabilities import capabilities
from larkdocio.read import download
from larkdocio.read.config import Config, OutputConfig
from larkdocio.read.parser import Parser

_RECIPE = "download-a-docx-to-markdown"
_COMMENTS_RECIPE = "read-the-comments-on-a-document"
_DOC_TOKEN = "YOURDOCTOKENHERE"

_RESOLVED = gr._FIXTURE_MENTION_RESOLVED
_UNKNOWN = gr._FIXTURE_MENTION_UNKNOWN
_NULL_NAMED = gr._FIXTURE_MENTION_NULL_NAMED
_NAME = gr._FIXTURE_MENTION_NAME


# --------------------------------------------------------------------------- #
# Scaffolding — the CLI leg, the recipe leg, and the guide-slicing helper.       #
# --------------------------------------------------------------------------- #

class _CliReadClient:
    """The read client the **CLI** path gets: the same mention-bearing payload and the same
    contacts directory the offline stage serves the recipe.

    Only the network boundary is replaced — the shipped ``Parser``, the shipped substitution
    and the shipped ``handle_download_command`` all run for real, which is what makes the
    parity comparison a comparison of the two *pipelines* rather than of two doubles.
    """

    def __init__(self, names=None):
        self._names = dict(gr._FIXTURE_MENTION_NAMES if names is None else names)
        self.contact_calls = []

    def get_docx_content(self, doc_token):
        blocks = gr.fixture_block_dicts(doc_token, mentions=True)
        docx = SimpleNamespace(
            title=gr._FIXTURE_TITLE, document_id=doc_token, revision_id=1)
        return docx, build_blocks(blocks)

    def batch_get_user_names(self, ids):
        self.contact_calls.append(list(ids))
        return {uid: self._names[uid] for uid in ids if uid in self._names}


def _cli_markdown(monkeypatch, tmp_path, *, config=None, names=None):
    """Run the CLI whole-pipeline entry point and return ``(written markdown, client)``."""
    client = _CliReadClient(names=names)
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(
        download, "get_read_credentials", lambda: ("cli_read_offline", "read-secret"))
    monkeypatch.setattr(download, "Client", lambda *a, **k: client)
    if config is not None:
        monkeypatch.setattr(download, "read_config_from_file", lambda path: config)

    out_dir = tmp_path / "cli-out"
    download.handle_download_command(
        f"https://example.larksuite.com/docx/{_DOC_TOKEN}", str(out_dir), "", False, "")

    written = list(out_dir.glob("*.md"))
    assert len(written) == 1, f"the CLI wrote {written}"
    return written[0].read_text(encoding="utf-8"), client


def _recipe_markdown(monkeypatch, tmp_path, *, source=None):
    """Run the guide's download recipe on the MENTION-BEARING stage; return its markdown."""
    stage = gr.stage(monkeypatch, tmp_path, mentions=True)
    ns = stage.run(_RECIPE, source=source)
    return ns["markdown"], stage


def _guide_section(heading):
    """The guide's text from ``heading`` up to the next ``### `` heading."""
    guide = larkdocio.guide(full=True)
    assert heading in guide, f"the guide has no section {heading!r}"
    start = guide.index(heading)
    rest = guide[start + len(heading):]
    nxt = re.search(r"^### ", rest, flags=re.MULTILINE)
    return heading + (rest[: nxt.start()] if nxt else rest)


def _blocks():
    return build_blocks(gr.fixture_block_dicts(_DOC_TOKEN, mentions=True))


class _Resolver:
    """A read client exposing ONLY the contacts leg — the seam's whole contract."""

    def __init__(self, names=None, raises=None):
        self._names = dict(gr._FIXTURE_MENTION_NAMES if names is None else names)
        self._raises = raises
        self.calls = []

    def batch_get_user_names(self, ids):
        self.calls.append(list(ids))
        if self._raises is not None:
            raise self._raises
        return {uid: self._names[uid] for uid in ids if uid in self._names}


def _parser_markdown(read_client=None, config=None):
    parser = Parser(config or Config(), read_client=read_client)
    return parser.parse_docx_content(_DOC_TOKEN, _blocks())


# --------------------------------------------------------------------------- #
# AC2 — THE PARITY ASSERTION (and the probe that proves it bites).              #
# --------------------------------------------------------------------------- #

def test_the_documented_python_recipe_and_the_cli_produce_the_same_markdown(
        monkeypatch, tmp_path):
    """AC2: the guide's Python read recipe and the ``download`` command produce the SAME
    Markdown for the same mention-bearing document — the assertion whose absence let the
    two paths drift apart, made mechanical."""
    recipe_md, _ = _recipe_markdown(monkeypatch, tmp_path)
    cli_md, cli_client = _cli_markdown(monkeypatch, tmp_path)

    assert recipe_md == cli_md, (
        "the documented Python path and the CLI disagree:\n"
        f"--- python ---\n{recipe_md}\n--- cli ---\n{cli_md}"
    )
    # ...and they agree on the RESOLVED form, not on the raw one (a pair that both emitted
    # raw ids would be "parity" while reproducing the defect).
    assert f"@{_NAME}" in recipe_md, recipe_md
    assert _RESOLVED not in recipe_md, recipe_md

    # One contacts call per document on each path (the ids are deduped by the parser).
    assert gr.OfflineDocxReadClient.contact_calls == [[_RESOLVED, _UNKNOWN, _NULL_NAMED]]
    assert cli_client.contact_calls == [[_RESOLVED, _UNKNOWN, _NULL_NAMED]]


def test_the_parity_assertion_bites_when_the_recipe_loses_its_read_client(
        monkeypatch, tmp_path):
    """The mutation probe: strip ``read_client=client`` back out of the recipe and the
    pre-fix defect returns — raw ids from Python, resolved names from the CLI, and the
    parity assertion above fails. Without this the parity test would be decoration."""
    source = gr.recipe_source(_RECIPE)
    stripped = source.replace(", read_client=client", "")
    assert stripped != source, (
        "the download recipe no longer injects a read client — the parity fix regressed")

    recipe_md, _ = _recipe_markdown(monkeypatch, tmp_path, source=stripped)
    cli_md, _ = _cli_markdown(monkeypatch, tmp_path)

    assert _RESOLVED in recipe_md, "the probe did not reproduce the raw-id defect"
    assert recipe_md != cli_md, "the parity assertion does not bite"
    assert gr.OfflineDocxReadClient.contact_calls == [], (
        "a Parser with no read client must never touch the contacts surface")


def test_the_shipped_recipe_text_itself_injects_the_read_client():
    """The recipe a consumer PASTES carries the seam — pinned on the shipped text, so the
    guide cannot regress to the bare ``Parser(Config())`` while the seam still exists."""
    source = gr.recipe_source(_RECIPE)
    assert "read_client=client" in source, source


# --------------------------------------------------------------------------- #
# AC1 / AC6 — the four mention shapes through the Parser seam.                   #
# --------------------------------------------------------------------------- #

def test_the_read_client_seam_resolves_what_it_can_and_leaves_the_rest_raw():
    """AC1 + AC6, all four shapes in one document: the covered id becomes a name, the id
    the directory does not cover and the null-named id stay raw ``@ou_…``, and the three
    live in ONE block (the mixed case)."""
    resolver = _Resolver()
    markdown = _parser_markdown(read_client=resolver)

    assert f"@{_NAME}" in markdown, markdown
    assert _RESOLVED not in markdown, markdown
    assert f"@{_UNKNOWN}" in markdown, markdown
    assert f"@{_NULL_NAMED}" in markdown, markdown

    # The mixed block: one line carries the resolved name AND both raw ids.
    mixed = [line for line in markdown.splitlines() if f"@{_NAME}" in line]
    assert len(mixed) == 1, markdown
    assert f"@{_UNKNOWN}" in mixed[0] and f"@{_NULL_NAMED}" in mixed[0], mixed[0]

    assert resolver.calls == [[_RESOLVED, _UNKNOWN, _NULL_NAMED]]


def test_a_parser_with_no_read_client_is_byte_identical_and_touches_no_contacts():
    """ZERO-DRIFT: the default construction renders exactly what it rendered before the
    seam existed — every mention raw — and no contacts surface is reachable from it."""
    raw = _parser_markdown()

    assert f"@{_RESOLVED}" in raw and f"@{_UNKNOWN}" in raw and f"@{_NULL_NAMED}" in raw
    assert _NAME not in raw, raw
    # Byte-identical to the same parse with the flag explicitly off — the two "no
    # resolution" routes cannot diverge.
    assert raw == _parser_markdown(config=Config(OutputConfig(resolve_mentions=False)))


def test_the_flag_is_honest_in_both_positions_on_the_seam():
    """``resolve_mentions=False`` with a read client injected: ids stay raw and the contacts
    API is never called (the flag must mean what it says in BOTH positions)."""
    resolver = _Resolver()
    markdown = _parser_markdown(
        read_client=resolver, config=Config(OutputConfig(resolve_mentions=False)))

    assert f"@{_RESOLVED}" in markdown and _NAME not in markdown
    assert resolver.calls == [], "the disabled flag must never touch the contacts API"


def test_the_flag_is_honest_in_both_positions_on_the_cli_path(monkeypatch, tmp_path):
    """The same knob, on the CLI pipeline: raw ids, zero contacts calls."""
    markdown, client = _cli_markdown(
        monkeypatch, tmp_path, config=Config(OutputConfig(resolve_mentions=False)))

    assert f"@{_RESOLVED}" in markdown and _NAME not in markdown
    assert client.contact_calls == []


def test_a_resolver_that_raises_never_fails_the_read():
    """AC6: the read must never fail because of mention resolution — a resolver that blows
    up degrades to the raw ids (the warn-and-continue precedent)."""
    resolver = _Resolver(raises=RuntimeError("contacts down"))
    markdown = _parser_markdown(read_client=resolver)

    assert f"@{_RESOLVED}" in markdown and _NAME not in markdown


def test_the_seam_and_the_download_post_pass_are_the_SAME_substitution():
    """One implementation, two call sites: resolving through the Parser seam and resolving
    through the download pipeline's post-pass produce byte-identical Markdown. This is what
    makes parity structural rather than coincidental."""
    parser = Parser(Config())
    raw = parser.parse_docx_content(_DOC_TOKEN, _blocks())
    post_pass = download._resolve_mentions(_Resolver(), Config(), parser, raw)

    assert post_pass == _parser_markdown(read_client=_Resolver())


# --------------------------------------------------------------------------- #
# AC3 — the flag is discoverable without inspect().                             #
# --------------------------------------------------------------------------- #

def test_capabilities_flags_carry_resolve_mentions_with_its_default_and_precondition():
    """AC3: ``resolve_mentions`` is in ``capabilities()["flags"]`` with its default AND its
    precondition — the two facts whose absence made the trap invisible (the default is True,
    so anyone who found the knob by other means concluded it was already working)."""
    flag = capabilities(full=True)["flags"]["resolve_mentions"]

    assert flag["default"] is True
    assert flag["mode"] == "config"
    summary = flag["summary"]
    for phrase in ("contact:user.base:readonly", "contacts data range",
                   "batch_get_user_names", "read_client"):
        assert phrase in summary, f"the flag summary does not state {phrase!r}: {summary}"


def test_the_docx_read_surface_names_the_field_level_scope_it_needs():
    """The optional-scope list is where a consumer looks for "what do I have to grant" —
    it must name the FIELD-level scope, not only the directory-access one."""
    credentials = capabilities(full=True)["surfaces"]["docx-read"]["credentials"]
    assert "contact:user.base:readonly" in credentials["optional_scopes"]
    assert "contacts data range" in credentials["note"]


# --------------------------------------------------------------------------- #
# AC4 / AC5 — the doc claims: the false bullet, its framing, the precondition.    #
# --------------------------------------------------------------------------- #

#: The claim as it shipped — TRUE when written, made false by the scope change. Kept
#: verbatim (hard wrap included) so the guard below is provably the guard that would have
#: caught it, and so the wrap cannot be what makes a substring check pass.
_PRE_FIX_BULLET = (
    "- **Authors are raw ids, not names.** A comment carries an opaque `ou_…` id and no\n"
    "  human-readable name; the directory lookup that would resolve one is not available on "
    "the\n  reader's scope, so nothing here guesses."
)

#: The precondition's two halves. The five-day misdiagnosis happened because only ONE of
#: them was ever suspected, so a text that names one and not the other is a repeat of it.
_PRECONDITION_HALVES = ("contacts data range", "contact:user.base:readonly")

#: The dead claim, and the three things that must be there instead. Checked on
#: ``prose``-normalized text so a reflow or an added emphasis marker cannot defeat either
#: direction — the shipped bullet really is wrapped mid-phrase.
_DEAD_CLAIM = "not available on the reader's scope"
_REQUIRED_CLAIMS = (
    "batch_get_user_names",                 # the call that does it
    "precondition, not a permanent limit",  # the framing that stops a "restore"
)


def _authorship_claim_problems(text):
    """Every way ``text`` still fails the authorship claim (AC4) — reused by the live guard
    AND by the bite test, so the check that guards is provably the check that bites."""
    problems = []
    if prose(_DEAD_CLAIM) in prose(text):
        problems.append("the text still says the directory lookup is unavailable")
    for phrase in missing_phrases(text, _REQUIRED_CLAIMS):
        problems.append(f"the text does not state: {phrase!r}")
    missing = missing_phrases(text, _PRECONDITION_HALVES)
    if missing:
        problems.append(f"the text does not state the precondition halves: {missing}")
    return problems


def test_the_false_authorship_claim_is_replaced_by_the_working_call():
    """AC4: the comments recipe's authorship bullet no longer says the lookup is
    unavailable; it carries the working call, framed as a **changed precondition** (which is
    what stops a future reader "restoring" the old sentence), and it keeps the true half of
    the original claim — the projection really does report raw ids."""
    preamble = gr.recipe_preamble(_COMMENTS_RECIPE)

    assert not _authorship_claim_problems(preamble), _authorship_claim_problems(preamble)
    assert "raw ids, not names" in preamble, "the true half of the claim was dropped"
    # Cross-referenced to the recipe that does it end to end, per the fix direction.
    assert "recipe: download a docx to markdown" in prose(preamble), preamble


def test_the_claim_guard_would_have_caught_the_shipped_sentence():
    """The bite test: the same helper flags the pre-fix bullet — RED on the old text, green
    on the new one."""
    problems = _authorship_claim_problems(_PRE_FIX_BULLET)
    assert problems, "the guard does not flag the very sentence it exists to catch"
    assert any("unavailable" in p for p in problems), problems


def test_the_old_claim_is_absent_from_the_whole_shipped_guide():
    """AC4, content-guarded in the strong direction: the sentence is gone from the WHOLE
    guide, not merely from the bullet that carried it."""
    assert prose(_DEAD_CLAIM) not in prose(larkdocio.guide(full=True))


@pytest.mark.parametrize("section_heading", [
    "### Recipe: download a docx to Markdown",
    "### Recipe: read the comments on a document",
])
def test_the_precondition_is_stated_where_the_call_is(section_heading):
    """AC5: **both** halves of the precondition — the contacts data range AND the
    field-level scope — are stated beside the call, in every place the call appears, so the
    claim carries its own falsifier instead of sending a reader back to the release notes."""
    section = _guide_section(section_heading)
    missing = missing_phrases(section, _PRECONDITION_HALVES)
    assert not missing, f"{section_heading} does not state: {missing}"
    # Both halves are console settings on the consumer's own app — the fact that makes the
    # precondition actionable rather than mysterious.
    assert "console" in prose(section), section_heading


def test_the_download_recipe_teaches_the_seam_the_flag_and_the_degrade():
    """AC1 + AC6, on the text: the recipe explains what ``read_client=`` does, names the
    switch a consumer can turn off, and states the degrade — so the resolved output is not a
    surprise and the raw output is not a mystery."""
    section = _guide_section("### Recipe: download a docx to Markdown")

    missing = missing_phrases(section, (
        "read_client=", "resolve_mentions", "batch_get_user_names",
        "the same Markdown", "falls back to the raw",
    ))
    assert not missing, f"the download recipe does not state: {missing}"


def test_the_flags_table_carries_the_one_flag_that_is_on_by_default():
    """The guide's flags table lists ``resolve_mentions`` (the bidirectional guard in
    ``tests/test_guide.py`` enforces the set; this pins the row's DEFAULT, which is the
    fact that makes it different from the other three).

    **Scoped to the capability-matrix region**, which is the table this test is about. It used
    to scan the whole document for a row starting ``| `resolve_mentions```, which was the same
    thing only while the guide named the key in exactly one table. It now also appears as a row
    of the generated ``config.json`` schema — a second, legitimate table — and a whole-document
    count read that as the flags row having been duplicated. The check itself is unchanged
    (exactly one such row, and it says the flag is on); only the region it reads is stated,
    using the same fences ``tests/test_guide.py`` parses the matrix with.
    """
    text = larkdocio.guide(full=True)
    begin, end = text.find("<!-- BEGIN CAPABILITY-MATRIX"), text.find("<!-- END CAPABILITY-MATRIX")
    assert begin != -1 and end > begin, "the guide's capability-matrix fences are gone"
    rows = [line for line in text[begin:end].splitlines()
            if line.startswith("| `resolve_mentions`")]
    assert len(rows) == 1, rows
    assert "on" in rows[0], rows[0]
