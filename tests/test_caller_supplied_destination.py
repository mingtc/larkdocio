"""THE CALLER-SUPPLIED-DESTINATION RULE — every top-level create names its place (LD-493).

**The rule.** If the caller does not supply a destination — a folder they own, created, or were
given — nothing is created. The library picks no default place and creates no folder to put
things in.

**Why it is a rule and not a taste, measured:** an object created with no destination lands in
the *application identity's own space*, and that space has **no human interface at all** — not
even for a full tenant administrator. It cannot be browsed; its trash cannot be listed; and
``delete`` there is a **trash, not a purge** (the object's metadata still resolves afterwards).
So a stray created that way is effectively permanent. The evidence is in the dev repo
(``dev/ld476-media-purge-probe/findings.md``): the application root listed 17 then 16 children,
every one of them a stray from a destination-less create, alongside 1,602+ trashed Bases.

**The shape is not new — it is generalised from two surfaces that already shipped it:**
``create_folder`` (its ``parent_token`` is required and refused locally, precisely because Lark
*accepts* ``folder_token: ""`` and files the folder in the calling app's own root) and the
upload family (``folder_token`` a required keyword, refused by ``_refuse_unaddressed``). This
module holds the offline half of extending that fence to every remaining create-class verb that
makes a **new top-level object**.

The in-parent creates — a block inside a document, a table/field/record/view inside a Base, a
float image inside a workbook, a version of a file, a comment on a file — are **out of scope**
with a reason: their parent *is* the destination and the caller already named it, so there is no
default to refuse. That classification is asserted here too (``test_out_of_scope_*``), because a
create verb that is neither fenced nor explicitly reasoned about is a hole in the rule.
"""
import pytest

import canary_support
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.schema_plan import copy_base, create_base
from larkdocio.common.destination import (
    DESTINATION_RULE,
    HOW_TO_GET_A_DESTINATION,
    ROOT_IS_NOT_A_DESTINATION,
    WHAT_A_FOLDER_COSTS,
    WHAT_TO_SUPPLY,
    ApplicationRootToken,
    require_destination,
)
from larkdocio.common.transport import WriteTransport
from larkdocio.errors import LarkConfigError, MissingDestinationError
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.write.client import WriteClient

from base_schema_fakes import copy_app_echo, create_app_echo, schema_client
from write_harness import FakeClock

#: A destination that is *shaped* like a real folder token. Nothing here reaches the network:
#: every assertion below is about a refusal that happens **before** any call.
FOLDER = "fldrCALLERSUPPLIED01"

#: Every spelling of "no destination" one call site could arrive with. The **empty string** is
#: the load-bearing one: Lark itself accepts it and files the object in the application's own
#: root, which is exactly the outcome this rule exists to prevent.
NO_DESTINATION = [None, "", "   ", "\t\n"]

#: The token the application's own root accessor answers, in the shape the captures show.
ROOT = "nodlROOTTOKEN"

#: THE LIMIT, in one phrase. The type-based refusal covers the value the accessor itself
#: handed out and nothing else; a raw root token a caller copied in from somewhere is an
#: ordinary string and this library cannot tell. That is a narrower guarantee than a
#: resolve-and-compare predicate would give, and it is stated rather than implied — held in
#: four places at once (the constant, the fence's docstring, the module paragraph, the shipped
#: guide) by ``test_the_LIMIT_is_stated_in_the_constant_the_docstrings_and_the_guide``.
LIMIT_PHRASE = "copied in from elsewhere"


# --------------------------------------------------------------------------- #
# The fence itself                                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("spelling", NO_DESTINATION)
def test_the_fence_refuses_every_spelling_of_no_destination(spelling):
    with pytest.raises(MissingDestinationError):
        require_destination(spelling, what="a document")


def test_the_fence_returns_the_token_when_one_is_supplied():
    assert require_destination(FOLDER, what="a document") == FOLDER


def test_the_refusal_names_the_rule_what_to_supply_and_how_to_get_one():
    """AC2's three obligations, in one message: the rule, the argument, the route to one."""
    with pytest.raises(MissingDestinationError) as caught:
        require_destination("", what="a document")
    message = str(caught.value)
    assert DESTINATION_RULE in message
    assert WHAT_TO_SUPPLY in message
    assert HOW_TO_GET_A_DESTINATION in message
    assert WHAT_A_FOLDER_COSTS in message
    assert "create_folder" in message, "the route to a token must be nameable, not implied"


# --------------------------------------------------------------------------- #
# LD-565 — the remedy order, what the remedy costs, and the non-destination     #
# --------------------------------------------------------------------------- #

def test_the_remedy_with_no_permanent_consequence_comes_FIRST():
    """AC1. Remedy #1 used to be ``create_folder`` — a folder this library cannot delete.

    The folder a caller can already open costs nothing and is undoable; it leads.
    """
    opening = HOW_TO_GET_A_DESTINATION.index("open a folder in your own Drive")
    making = HOW_TO_GET_A_DESTINATION.index("create_folder(")
    assert opening < making, (
        "the refusal's first remedy must be the one with no permanent consequence "
        f"— got: {HOW_TO_GET_A_DESTINATION!r}")


def test_the_refusal_states_the_PERMANENCE_and_the_NON_IDEMPOTENCE():
    """AC2. Both facts land in the refusal itself, sourced from folders_write's own rows."""
    from larkdocio.drive.folders_write import DUPLICATE_NAME_BEHAVIOUR, R3_NOT_SHIPPED

    delete_row = next(why for what, why in R3_NOT_SHIPPED if what == "delete a folder")
    assert "MEASURED route left unshipped" in delete_row
    assert "permanent as far as this library is concerned" in delete_row
    assert "A SECOND FOLDER" in DUPLICATE_NAME_BEHAVIOUR

    # The refusal repeats the two facts in the caller's voice, with the SAME label the
    # measurement carries — a measured route left unshipped …
    assert "measured" in WHAT_A_FOLDER_COSTS.lower()
    assert "permanent as far as this library is concerned" in WHAT_A_FOLDER_COSTS
    # … and the same disclosure create_folder already makes about a repeated name.
    assert "a second folder" in WHAT_A_FOLDER_COSTS.lower()


@pytest.mark.parametrize("over_claim", ["Lark cannot", "Lark does not", "impossible"])
def test_the_cost_sentence_never_over_claims_about_LARK(over_claim):
    """AC2/AC7. The route works; this library does not ship it. Those are different claims."""
    assert over_claim.lower() not in WHAT_A_FOLDER_COSTS.lower()


def test_the_module_docstring_names_root_folder_token_as_a_NON_DESTINATION():
    """AC3. The one public accessor that hands out a fatal destination is named where the
    rule lives — not only in a capability row on the other side of the guide.

    TRANSFORMED, not replaced (LD-581): the paragraph this guard holds used to be the ONLY
    thing standing between a caller and that value — prose the guard could not enforce. It is
    now backed by a type check, so the same paragraph must additionally say *by type* and must
    state the resulting limit. The original assertions stay exactly as they were: the
    conclusion is widened, the reason preserved.
    """
    import larkdocio.common.destination as destination

    doc = destination.__doc__
    assert "root_folder_token" in doc
    assert "not" in doc.lower()
    # The transform: prose alone is no longer the whole fence, and the paragraph says so.
    assert "by type" in doc
    assert LIMIT_PHRASE in doc, (
        "the paragraph must state the guarantee's LIMIT where it states the guarantee")


def test_the_refusal_names_WHAT_was_being_created():
    with pytest.raises(MissingDestinationError) as caught:
        require_destination(None, what="a spreadsheet")
    assert "a spreadsheet" in str(caught.value)


def test_the_refusal_is_a_config_error_and_a_value_error():
    """Local, pre-API, and a bad argument — so both established ``except`` shapes catch it."""
    assert issubclass(MissingDestinationError, LarkConfigError)
    assert issubclass(MissingDestinationError, ValueError)


# --------------------------------------------------------------------------- #
# In scope 1/3 — docx: WriteClient.create_document                             #
# --------------------------------------------------------------------------- #

class _RecordingOpener:
    """An opener that records and would answer — it must never be reached."""

    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout=None):  # pragma: no cover - never reached
        self.requests.append(request)
        raise AssertionError("a create with no destination reached the network")


def _write_client(opener):
    clock = FakeClock()
    return WriteClient(
        "app", "secret", "larksuite.com",
        transport=WriteTransport(max_writes_per_sec=3, time_fn=clock.time,
                                 sleep_fn=clock.sleep),
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )


@pytest.mark.parametrize("spelling", NO_DESTINATION)
def test_create_document_refuses_locally_with_zero_calls(spelling):
    opener = _RecordingOpener()
    client = _write_client(opener)

    with pytest.raises(MissingDestinationError):
        client.create_document(title="x", folder_token=spelling)
    assert opener.requests == []


def test_create_document_defaults_the_destination_to_None_so_OMISSION_IS_REFUSED_TOO():
    """LD-582 keeps LD-493's reason and supersedes only its conclusion for this one method.

    **The reason, unchanged:** the pre-LD-493 signature defaulted to ``folder_token=""``, and
    an *empty-string* default is what made the application's own space reachable by accident —
    that spelling is still refused, by ``test_create_document_refuses_locally_with_zero_calls``
    above. **The conclusion that changed:** "therefore no default at all" also handed omission
    to Python, so a caller who named no destination met a bare ``TypeError`` and none of the
    teaching text. ``None`` is not a destination and cannot become one, so defaulting to it
    costs nothing and is what lets *this library* own the omission —
    :meth:`larkdocio.base.schema_client.BaseSchemaClient.create_app` has shipped exactly this
    shape all along. Required and defaulted are not in tension.
    """
    opener = _RecordingOpener()
    with pytest.raises(MissingDestinationError):
        _write_client(opener).create_document(title="x")
    assert opener.requests == []


def test_create_document_keeps_folder_token_KEYWORD_ONLY_so_no_call_site_moves():
    """Only the default is added (LD-582 AC1): the parameter stays keyword-only, in place."""
    import inspect

    param = inspect.signature(WriteClient.create_document).parameters["folder_token"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is None


def test_OMISSION_and_an_explicit_None_produce_BYTE_IDENTICAL_refusals():
    """LD-582 AC2 — the refusal is the one that already existed; there is no second authoring.

    Omitting the keyword and passing ``folder_token=None`` must arrive at the *same*
    ``require_destination(…, what="a document")`` call and therefore carry the same four
    composed constants, byte for byte. A drift here would mean a second refusal was authored.
    """
    opener = _RecordingOpener()
    client = _write_client(opener)

    with pytest.raises(MissingDestinationError) as omitted:
        client.create_document(title="x")
    with pytest.raises(MissingDestinationError) as explicit_none:
        client.create_document(title="x", folder_token=None)

    assert str(omitted.value) == str(explicit_none.value)
    for fragment in (DESTINATION_RULE, WHAT_TO_SUPPLY, HOW_TO_GET_A_DESTINATION,
                     WHAT_A_FOLDER_COSTS):
        assert fragment in str(omitted.value)
    assert "a document" in str(omitted.value)
    assert opener.requests == []


# --------------------------------------------------------------------------- #
# In scope 2/3 — sheets: SheetsWriteClient.create_spreadsheet                   #
# --------------------------------------------------------------------------- #

def _sheets_client(opener):
    clock = FakeClock()
    return SheetsWriteClient(
        "app", "secret", "larksuite.com",
        transport=WriteTransport(max_writes_per_sec=3, time_fn=clock.time,
                                 sleep_fn=clock.sleep),
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )


@pytest.mark.parametrize("spelling", NO_DESTINATION)
def test_create_spreadsheet_refuses_locally_with_zero_calls(spelling):
    opener = _RecordingOpener()
    client = _sheets_client(opener)

    with pytest.raises(MissingDestinationError):
        client.create_spreadsheet("x", folder_token=spelling)
    assert opener.requests == []


def test_create_spreadsheet_has_no_destination_default_at_all():
    opener = _RecordingOpener()
    with pytest.raises(TypeError):
        _sheets_client(opener).create_spreadsheet("x")
    assert opener.requests == []


# --------------------------------------------------------------------------- #
# In scope 3/3 — Base: create_app / copy_app, and their plan-level twins        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("spelling", NO_DESTINATION)
def test_create_app_refuses_locally_with_zero_calls(spelling):
    client = schema_client(create=[create_app_echo()])
    with pytest.raises(MissingDestinationError):
        client.create_app("n", spelling)
    assert client.api_calls == 0


@pytest.mark.parametrize("spelling", NO_DESTINATION)
def test_copy_app_refuses_locally_with_zero_calls(spelling):
    """A copy makes a **new top-level Base**, and a keyless copy is measured to land in the
    application's own root — so the rule reaches the copy exactly as it reaches the create."""
    client = schema_client(copy=[copy_app_echo()])
    with pytest.raises(MissingDestinationError):
        client.copy_app("appTOKEN", "n", folder_token=spelling)
    assert client.api_calls == 0


@pytest.mark.parametrize("spelling", NO_DESTINATION)
def test_create_base_refuses_at_the_PLAN_seam(spelling):
    """The plan seam refuses too, so a refused request costs zero calls **and** never enters a
    plan — the same public-seam doctrine ``create_table`` states for its primary column."""
    with pytest.raises(MissingDestinationError):
        create_base("n", spelling)


@pytest.mark.parametrize("spelling", NO_DESTINATION)
def test_copy_base_refuses_at_the_PLAN_seam(spelling):
    with pytest.raises(MissingDestinationError):
        copy_base("appTOKEN", "n", folder_token=spelling)


def test_the_plan_seam_accepts_a_supplied_destination():
    request = create_base("n", FOLDER)
    assert request.arguments["folder_token"] == FOLDER
    assert copy_base("appTOKEN", "n", folder_token=FOLDER).arguments["folder_token"] == FOLDER


def test_a_supplied_destination_still_travels_on_the_wire():
    """The fence adds a refusal; it changes nothing about the addressed call."""
    client = schema_client(create=[create_app_echo()])
    client.create_app("n", FOLDER)
    request = client._sdk.bitable.v1.app.create.requests[0]
    assert getattr(request.request_body, "folder_token", None) == FOLDER


# --------------------------------------------------------------------------- #
# AC1 — the classification is asserted, not merely written down                 #
# --------------------------------------------------------------------------- #

#: Every create-class verb the package ships, with the side of the rule it falls on. Read off
#: the code (``grep -rn "def create" src/larkdocio``) rather than off any prior list, and kept
#: here so a newly added create verb has to be classified rather than quietly defaulting.
IN_SCOPE = (
    "larkdocio.write.client.WriteClient.create_document",
    "larkdocio.sheets.write_client.SheetsWriteClient.create_spreadsheet",
    "larkdocio.base.schema_client.BaseSchemaClient.create_app",
    "larkdocio.base.schema_client.BaseSchemaClient.copy_app",
    "larkdocio.base.schema_plan.create_base",
    "larkdocio.base.schema_plan.copy_base",
    "larkdocio.drive.folders_write.DriveFoldersWriteClient.create_folder",
    "larkdocio.drive.files_write.DriveFilesWriteClient.upload",
    "larkdocio.drive.files_write.DriveFilesWriteClient.upload_prepare",
    "larkdocio.drive.files_write.DriveFilesWriteClient.upload_chunked",
)

#: Out of scope, each with the reason the rule does not reach it. Every one of these creates
#: **inside an object the caller already named**, so the caller has already said where.
OUT_OF_SCOPE = {
    "larkdocio.write.client.WriteClient.create_children":
        "blocks inside a document the caller named",
    "larkdocio.write.client.WriteClient.create_descendant":
        "a block subtree inside a document the caller named",
    "larkdocio.write.client.WriteClient.create_whole_document_comment":
        "a comment on a file the caller named",
    "larkdocio.base.schema_client.BaseSchemaClient.create_table":
        "a table inside a Base the caller named",
    "larkdocio.base.schema_client.BaseSchemaClient.create_field":
        "a column inside a table the caller named",
    "larkdocio.base.schema_plan.create_table":
        "a table inside a Base the caller named",
    "larkdocio.base.schema_ops_fields.create_field":
        "a column inside a table the caller named",
    "larkdocio.base.view_client.BaseViewOps.create_view":
        "a view inside a table the caller named",
    "larkdocio.base.view_plan.create_view":
        "a view inside a table the caller named",
    "larkdocio.base.write_client.BaseWriteClient.create_record":
        "a row inside a table the caller named",
    "larkdocio.sheets.write_client.SheetsWriteClient.create_float_image":
        "an image anchored in a workbook the caller named",
    "larkdocio.drive.versions_write.DriveVersionsWriteClient.create_version":
        "a version of a file the caller named",
    "larkdocio.sheets.export_reader.SheetsExportReader.create_export_task":
        "an export job, not a placed object: the endpoint takes no destination",
}


def _resolve(dotted):
    import importlib
    parts = dotted.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        obj = module
        for attr in parts[cut:]:
            obj = getattr(obj, attr)
        return obj
    raise AssertionError(f"could not resolve {dotted}")


@pytest.mark.parametrize("dotted", IN_SCOPE + tuple(OUT_OF_SCOPE))
def test_every_classified_verb_still_exists(dotted):
    """The classification is worthless if it names a symbol that has moved or gone."""
    assert callable(_resolve(dotted))


def test_the_enumeration_covers_every_create_verb_the_package_defines():
    """Bidirectional: a create verb added without a classification reddens here."""
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio"
    classified = {dotted.rsplit(".", 1)[-1] for dotted in IN_SCOPE} | {
        dotted.rsplit(".", 1)[-1] for dotted in OUT_OF_SCOPE}
    found = set()
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("create_") or node.name.startswith("copy_"):
                    found.add(node.name)
    # Verb-shaped helpers that create nothing addressable: they build request payloads,
    # batches or local objects. Named, so the exemption is a decision rather than a gap.
    not_creates = {"create_batches", "created_count"}
    unclassified = found - classified - not_creates
    assert unclassified == set(), (
        f"these create-class verbs are neither in-scope nor out-of-scope-with-a-reason: "
        f"{sorted(unclassified)} — classify each one (LD-493 AC1)")


@pytest.mark.parametrize("dotted,reason", sorted(OUT_OF_SCOPE.items()))
def test_out_of_scope_verbs_carry_a_reason(dotted, reason):
    assert reason.strip(), f"{dotted} is exempted with no reason"


# --------------------------------------------------------------------------- #
# The HOUSE half — our own harnesses obey the rule, and say so when they cannot #
# --------------------------------------------------------------------------- #
#
# Offline by construction: the skip path is the half a credential-less environment can
# actually exercise, and it is the half that must never degrade into a silent pass.

def test_the_disposables_folder_is_read_from_the_named_variable(monkeypatch):
    monkeypatch.setenv(canary_support.DISPOSABLES_FOLDER_ENV, FOLDER)
    assert canary_support.disposables_folder() == FOLDER
    assert canary_support.disposables_folder_missing_reason() is None


def test_a_pasted_folder_LINK_degrades_to_its_token(monkeypatch):
    """A human fills ``.env`` in by copying a link out of their Drive."""
    monkeypatch.setenv(
        canary_support.DISPOSABLES_FOLDER_ENV,
        f"https://example.larksuite.com/drive/folder/{FOLDER}")
    assert canary_support.disposables_folder() == FOLDER


@pytest.mark.parametrize("spelling", ["", "   "])
def test_unset_or_blank_is_no_folder_at_all(monkeypatch, spelling):
    monkeypatch.setenv(canary_support.DISPOSABLES_FOLDER_ENV, spelling)
    assert canary_support.disposables_folder() is None


def test_unset_SKIPS_LOUDLY_naming_the_variable(monkeypatch):
    """Never a silent pass, and never a fall-back to the application's own space."""
    monkeypatch.delenv(canary_support.DISPOSABLES_FOLDER_ENV, raising=False)
    reason = canary_support.disposables_folder_missing_reason()
    assert reason and canary_support.DISPOSABLES_FOLDER_ENV in reason
    # ``Skipped`` is a BaseException, so ``pytest.raises(Exception)`` would NOT catch it and
    # this test would itself skip — silently asserting nothing, which is the exact failure
    # mode the rule is about. The skip type is caught by name.
    with pytest.raises(pytest.skip.Exception) as caught:
        canary_support.require_disposables_folder()
    assert canary_support.DISPOSABLES_FOLDER_ENV in str(caught.value)
    assert "application's own space" in str(caught.value), (
        "the skip must say WHY it will not fall back, not merely that it skipped")


def test_require_returns_the_token_when_it_is_set(monkeypatch):
    monkeypatch.setenv(canary_support.DISPOSABLES_FOLDER_ENV, FOLDER)
    assert canary_support.require_disposables_folder() == FOLDER


def test_no_harness_creates_a_disposable_without_asking_for_the_folder():
    """Every live module that calls an in-scope create verb must first ask for the folder.

    The bidirectional half of AC7: a new live gate that creates something and forgets the
    destination reddens here rather than quietly filing an object where nobody can see it.
    """
    import pathlib
    import re

    tests_dir = pathlib.Path(__file__).resolve().parent
    creators = re.compile(r"\.create_document\(|\.create_spreadsheet\(|\.create_app\(|"
                          r"\.copy_app\(|[^.\w]create_base\(|[^.\w]copy_base\(")
    offenders = []
    for path in sorted(tests_dir.rglob("test_live_*.py")):  # LD-654: recursive population
        body = path.read_text(encoding="utf-8")
        if path.name.endswith("_offline.py"):
            continue
        if creators.search(body) and "disposables_folder" not in body:
            offenders.append(path.name)
    assert offenders == [], (
        f"these live gates create a top-level object without asking for "
        f"{canary_support.DISPOSABLES_FOLDER_ENV}: {offenders}")


# --------------------------------------------------------------------------- #
# LD-565 AC4 — the guide carries the constants VERBATIM inside a fenced region   #
# --------------------------------------------------------------------------- #
#
# Not a projection and not a paraphrase: the shipped guide holds the SAME BYTES the refusal
# holds, between two markers, on the fence pattern ``BEGIN/END CAPABILITY-MATRIX`` already
# uses. The comparison is literal on both arms — no normalising, no fuzzy match, no
# keyword-presence — because a second, test-side transform is how a documented promise ends
# up wider than the guard that holds it.

FENCE_BEGIN = (
    "<!-- BEGIN DESTINATION-REFUSAL (verbatim from larkdocio.common.destination; "
    "byte-equality guarded by tests/test_caller_supplied_destination.py, in the source "
    "repository) -->")
FENCE_END = "<!-- END DESTINATION-REFUSAL -->"


def _guide_text():
    import pathlib
    guide = pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio" / "GUIDE.md"
    return guide.read_text(encoding="utf-8")


def _expected_fenced_region():
    """The region's bytes, built from the constants themselves — the only authoring site."""
    return "\n".join((
        "",
        "> **The rule.** " + DESTINATION_RULE + ".",
        ">",
        # LD-581. Second, exactly where the refusal message puts it — the fence exists so the
        # traceback and the guide cannot drift, and that includes their ORDER.
        "> **Not a destination.** " + ROOT_IS_NOT_A_DESTINATION + ".",
        ">",
        "> **What to supply.** " + WHAT_TO_SUPPLY + ".",
        ">",
        "> **How to get one.** " + HOW_TO_GET_A_DESTINATION + ".",
        ">",
        "> **What a folder costs.** " + WHAT_A_FOLDER_COSTS + ".",
        "",
    ))


def test_the_guide_carries_the_refusal_constants_BYTE_FOR_BYTE():
    """AC4. Change the constant → red. Change the guide's fenced bytes → red."""
    text = _guide_text()
    assert text.count(FENCE_BEGIN) == 1, "exactly one DESTINATION-REFUSAL region"
    assert text.count(FENCE_END) == 1
    region = text.split(FENCE_BEGIN, 1)[1].split(FENCE_END, 1)[0]
    assert region == _expected_fenced_region(), (
        "the guide's fenced destination-refusal region has drifted from "
        "larkdocio.common.destination — re-copy the constants verbatim; never reword them")


def test_the_fenced_region_lives_INSIDE_the_destination_section():
    """The bytes are worthless in the wrong place: they must sit under the rule's own
    heading — whose slug the shipped skills pack routes to and which must not be renamed."""
    heading = ("### Where a new object goes — you name the destination, or nothing is "
               "created")
    text = _guide_text()
    assert heading in text
    after_heading = text.split(heading, 1)[1]
    next_heading = after_heading.split("\n### ", 1)[0]
    assert FENCE_BEGIN in next_heading and FENCE_END in next_heading


def test_the_guide_names_root_folder_token_as_a_NON_DESTINATION_where_the_rule_lives():
    """AC3, the guide half. Before LD-565 the accessor appeared exactly once in the whole
    guide — a capability-table row — and never where a caller meets the rule."""
    heading = ("### Where a new object goes — you name the destination, or nothing is "
               "created")
    section = _guide_text().split(heading, 1)[1].split("\n### ", 1)[0]
    assert "root_folder_token" in section


# --------------------------------------------------------------------------- #
# LD-581 — the typed root token, refused LOCALLY by type                        #
# --------------------------------------------------------------------------- #
#
# The measured harm (dev/dogfood5/DIGEST.md § 7 P6): a consumer called the public accessor and
# passed the value straight on. The guard was armed on every spelling of "nothing" and
# structurally blind on the one real token that reproduces the harm.
#
# The remedy had to stay LOCAL. Making the fence resolve the root and compare would have pulled
# a drive-read endpoint into every write path — a wider scope requirement on a create — which is
# why that variant was priced and NOT ruled. A `str` subclass makes an `isinstance` check
# sufficient: zero calls, zero credentials, zero scope. The tests below hold both halves — the
# refusal, and the locality that is the whole reason it is shaped this way.

#: The section heading the destination rule lives under in the shipped guide. Its slug is
#: routed to by the skills pack, so it must not be renamed.
DESTINATION_HEADING = ("### Where a new object goes — you name the destination, or nothing is "
                       "created")

#: The six verbs that take a destination, named so the fence's reach is *counted* rather than
#: quoted. Re-derived on the branch with
#: ``grep -rn "require_destination" --include="*.py" src/larkdocio/`` — never from the issue
#: file and never from CHANGELOG.md's historical "all six".
DESTINATION_TAKING_VERBS = (
    "create_document",     # write/client.py
    "create_spreadsheet",  # sheets/write_client.py
    "create_app",          # base/schema_client.py
    "copy_app",            # base/schema_client.py
    "create_base",         # base/schema_plan.py — the plan seam
    "copy_base",           # base/schema_plan.py — the plan seam
)


def _guide_destination_section():
    return _guide_text().split(DESTINATION_HEADING, 1)[1].split("\n### ", 1)[0]


def _probe(verb):
    """``(invoke, observed_calls)`` for one of the six, driven through its own public seam.

    The two plan-seam entries answer a structural zero: ``create_base`` / ``copy_base`` build a
    request object and own no transport at all, so there is nothing they could have sent.
    """
    if verb == "create_document":
        opener = _RecordingOpener()
        client = _write_client(opener)
        return (lambda token: client.create_document(title="x", folder_token=token),
                lambda: len(opener.requests))
    if verb == "create_spreadsheet":
        opener = _RecordingOpener()
        client = _sheets_client(opener)
        return (lambda token: client.create_spreadsheet("x", folder_token=token),
                lambda: len(opener.requests))
    if verb == "create_app":
        client = schema_client(create=[create_app_echo()])
        return (lambda token: client.create_app("n", token), lambda: client.api_calls)
    if verb == "copy_app":
        client = schema_client(copy=[copy_app_echo()])
        return (lambda token: client.copy_app("appTOKEN", "n", folder_token=token),
                lambda: client.api_calls)
    if verb == "create_base":
        return (lambda token: create_base("n", token), lambda: 0)
    if verb == "copy_base":
        return (lambda token: copy_base("appTOKEN", "n", folder_token=token), lambda: 0)
    raise AssertionError(f"unknown verb {verb!r}")


# -- AC1: the typed token is a string everywhere a string is used ------------- #

def test_the_typed_root_token_is_a_STRING_everywhere_a_string_is_used():
    """Nothing existing breaks: it concatenates, compares, formats, hashes, keys a dict,
    JSON-serialises and sorts exactly as the plain token did."""
    import json

    token = ApplicationRootToken(ROOT)
    assert isinstance(token, str)
    assert token == ROOT and ROOT == token and not token != ROOT
    assert token + "/child" == ROOT + "/child"
    assert "parent/" + token == "parent/" + ROOT
    assert f"{token}!" == ROOT + "!"
    assert "%s" % token == ROOT
    assert "{}".format(token) == ROOT
    assert hash(token) == hash(ROOT)
    assert {token: 1}[ROOT] == 1 and {ROOT: 1}[token] == 1
    assert token in {ROOT}
    assert json.dumps({"folder_token": token}) == '{"folder_token": "%s"}' % ROOT
    assert token.startswith("nodl") and token.upper() == ROOT.upper()
    assert token.strip() == ROOT and len(token) == len(ROOT) and str(token) == ROOT
    assert sorted([token, "aaa"]) == ["aaa", ROOT]
    assert bool(token) is True


def test_only_the_ACCESSORS_OWN_VALUE_carries_the_type_and_that_IS_the_limit():
    """Every derived string is a plain ``str`` again, so the guarantee is exactly as wide as
    the value the accessor handed out — which is what makes the stated limit true rather than
    modest."""
    token = ApplicationRootToken(ROOT)
    assert type(str(token)) is str
    assert type(token.strip()) is str
    assert type(token[:]) is str
    assert type(token + "") is str


def test_an_EMPTY_answer_is_still_typed_and_still_means_NO_ANSWER():
    """The accessor's ``or ""`` path keeps its meaning. The type marks *provenance* — this came
    out of the accessor — not non-emptiness, so an empty answer stays falsy and equal to ``""``.
    """
    empty = ApplicationRootToken("")
    assert empty == "" and not empty and len(empty) == 0


# -- AC2: the local refusal, from one constant, with F8 remedies -------------- #

def test_the_typed_root_token_is_REFUSED_and_the_message_teaches():
    with pytest.raises(MissingDestinationError) as caught:
        require_destination(ApplicationRootToken(ROOT), what="a document")
    message = str(caught.value)
    assert "a document" in message
    assert ROOT_IS_NOT_A_DESTINATION in message
    assert DESTINATION_RULE in message
    assert WHAT_TO_SUPPLY in message
    assert HOW_TO_GET_A_DESTINATION in message
    assert WHAT_A_FOLDER_COSTS in message
    # LD-565's remedy order is INHERITED, not re-derived: the message reuses the one constant,
    # so the route with no permanent consequence still leads.
    assert message.index("open a folder in your own Drive") < message.index("create_folder(")


def test_the_root_refusal_POINTS_AT_the_why_instead_of_paraphrasing_it():
    """The no-human-interface measurement keeps exactly one statement of itself: the new
    constant leans on the rule rather than becoming a second thing to keep true."""
    assert "no human interface can browse" in DESTINATION_RULE
    assert "no human interface" not in ROOT_IS_NOT_A_DESTINATION
    assert "root_folder_token" in ROOT_IS_NOT_A_DESTINATION


def test_the_root_refusal_is_ONE_CONSTANT_beside_the_others():
    """Same authoring site, same projection mechanism as the four that shipped before it."""
    import larkdocio.common.destination as destination

    for name in ("DESTINATION_RULE", "WHAT_TO_SUPPLY", "HOW_TO_GET_A_DESTINATION",
                 "WHAT_A_FOLDER_COSTS", "ROOT_IS_NOT_A_DESTINATION"):
        assert isinstance(getattr(destination, name), str)


def test_the_SAME_BYTES_as_a_PLAIN_string_are_still_ACCEPTED():
    """The limit, executable. A raw root token copied in from elsewhere is an ordinary string
    here — accepted, and disclosed as accepted, rather than silently missing."""
    assert require_destination(ROOT, what="a document") == ROOT


def test_an_EMPTY_typed_answer_refuses_through_the_PRE_EXISTING_blank_branch():
    """Blankness is tested FIRST, so an empty answer gets the message it already got. A
    root-specific message there would claim the caller passed the root when they passed
    nothing."""
    with pytest.raises(MissingDestinationError) as caught:
        require_destination(ApplicationRootToken(""), what="a document")
    message = str(caught.value)
    assert ROOT_IS_NOT_A_DESTINATION not in message
    assert DESTINATION_RULE in message


# -- AC3: zero calls, no client, no credentials, no scope --------------------- #

@pytest.mark.parametrize("verb", DESTINATION_TAKING_VERBS)
def test_every_destination_taking_verb_refuses_the_typed_root_with_ZERO_CALLS(verb):
    """One seam, every call site for free — and a recording transport proves nothing was
    sent. No call site was edited to add the check."""
    invoke, observed_calls = _probe(verb)
    with pytest.raises(MissingDestinationError) as caught:
        invoke(ApplicationRootToken(ROOT))
    assert ROOT_IS_NOT_A_DESTINATION in str(caught.value)
    assert observed_calls() == 0


def test_the_number_of_call_sites_is_RE_DERIVED_from_the_source():
    """Never quoted. A seventh destination-taking verb added without a probe reddens here."""
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio"
    sites = []
    for path in sorted(src.rglob("*.py")):
        if path.name == "destination.py":  # the definition, not a call site
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<![\w.])require_destination\(", line):
                sites.append(f"{path.relative_to(src)}:{number}")
    assert len(sites) == len(DESTINATION_TAKING_VERBS), (
        f"the fence's reach changed — probe every call site: {sites}")


def test_the_fence_MODULE_imports_nothing_that_could_reach_the_network():
    """AC3's teeth, and the reason the root-resolving variant stayed unruled: this module may
    not learn about a client, a credential or an endpoint."""
    import ast
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio"
              / "common" / "destination.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = ("larkdocio.drive", "larkdocio.read", "larkdocio.write", "larkdocio.sheets",
                 "larkdocio.base", "larkdocio.common.transport", "larkdocio.common.auth",
                 "larkdocio.permissions", "urllib", "http", "socket", "ssl", "lark_oapi",
                 "requests")
    offenders = sorted(name for name in imported
                       if any(name == bad or name.startswith(bad + ".") for bad in forbidden))
    assert offenders == [], (
        f"the destination fence must stay client-free and network-free — got {offenders}")
    assert imported == {"larkdocio.common.errors"}, (
        f"one import, the error type, and nothing else — got {sorted(imported)}")


def test_require_destination_takes_no_client_and_no_credentials():
    import inspect

    assert list(inspect.signature(require_destination).parameters) == ["folder_token", "what"]


def test_the_LOCALITY_promise_is_RESTATED_and_names_what_preserves_it():
    doc = require_destination.__doc__
    assert "locally, before any call" in doc
    assert "type check" in doc, (
        "the docstring must say that the TYPE CHECK is what keeps the promise local")


# -- AC4: the limit stated where a caller meets it --------------------------- #

def test_the_LIMIT_is_stated_in_the_constant_the_docstrings_and_the_guide():
    """A bare "the library refuses the app's own root" would be a universal the code does not
    deliver. The narrower truth is shipped in all four places a caller reads."""
    import larkdocio.common.destination as destination

    assert LIMIT_PHRASE in ROOT_IS_NOT_A_DESTINATION
    assert LIMIT_PHRASE in require_destination.__doc__
    assert LIMIT_PHRASE in destination.__doc__
    assert LIMIT_PHRASE in _guide_destination_section()


# -- AC5: ruling 4 recorded, and nothing about scope moved ------------------- #

def test_the_accessor_docstring_records_PUBLIC_ON_PURPOSE_and_REFUSED_BY_TYPE():
    from larkdocio.drive.client import DriveClient

    doc = DriveClient.root_folder_token.__doc__
    assert "public" in doc
    assert "by type" in doc
    assert "drive-read" in doc, "it stays in the read matrix — reading the root is legitimate"


def test_the_guide_sentence_says_BY_TYPE_not_only_BY_RULE():
    section = _guide_destination_section()
    assert "root_folder_token" in section
    assert "by type" in section


#: The generated permissions row for the accessor, quoted whole. This issue changes no scope,
#: no endpoint and no call count, so the row must come out byte-identical.
ROOT_FOLDER_TOKEN_PERMISSION_ROW = (
    "| `drive-read` | `root_folder_token` | operation | `LARK_READ_APP_ID` · "
    "`LARK_READ_APP_SECRET` | `/open-apis/drive/explorer/v2/root_folder/meta` | — | — "
    "| derived |")


def test_NO_scope_NO_endpoint_and_NO_capability_row_changed():
    import pathlib

    from larkdocio import capabilities
    from larkdocio.drive import ops

    matrix = (pathlib.Path(__file__).resolve().parent.parent / "PERMISSIONS.md").read_text(
        encoding="utf-8")
    assert ROOT_FOLDER_TOKEN_PERMISSION_ROW in matrix

    surface = capabilities(surface="drive-read")
    row = next(op for op in surface["operations"] if op["name"] == "root_folder_token")
    assert row["kind"] == "operation"
    assert row["projected_from"] == "larkdocio.drive.client.DriveClient"
    assert surface["mode"] == "read"
    assert surface["credentials"]["scopes"] == []

    descriptor = next(d for d in ops.OPS if d.name == "root_folder_token")
    assert descriptor.mutates is False
    assert descriptor.endpoint == ops.ROOT_FOLDER_META_ENDPOINT
    assert descriptor in ops.ENUMERATION_OPS


# --------------------------------------------------------------------------- #
# LD-585 (b) — THE CONTRACT SUMMARY IS A PROJECTION, NOT A FOURTH PARAPHRASE.   #
# --------------------------------------------------------------------------- #
#
# ``capabilities(full=True)["safety_contracts"]["caller-supplied-destination"]["summary"]`` used
# to be a hand-written restatement of this module's rule, free to drift from it — and it drifted
# TWICE: past LD-565's remedy ORDER (the route with no permanent consequence leads, and the cost
# of the other one is stated before it is taken) and past LD-581's typed-root refusal AND the
# limit that ships with it. Its "CREATES NO FOLDER" clause had also become readable as a denial
# that ``create_folder`` ships, which it does.
#
# The remedy is the mechanism ``capabilities/_assembly.py`` already uses for the sibling
# destination sentence: import the module, concatenate the constants, keep the reason in a
# comment. The test below is deliberately a WHOLE-CONSTRUCTION EQUALITY rather than a
# presence check — it names every hand-written fragment in order, so a new free-floating
# sentence cannot be slipped between two projected ones. That is what "the hand-written
# remainder is the only non-projected text" means as an assertion.

#: The connective scaffold, in order. Interleaved with :data:`_PROJECTED` below, these two
#: tuples ARE the summary — there is no third thing.
_SCAFFOLD = (
    "Every verb that creates a NEW TOP-LEVEL OBJECT — a document, a spreadsheet, a Base, a "
    "copy of a Base, a folder, an uploaded file — requires a destination the caller supplies, "
    "and refuses LOCALLY, before any call, when none is given. THE RULE, IN THE WORDS THE "
    "REFUSAL ITSELF CARRIES: ",

    ". Every spelling of none is refused alike, including the EMPTY STRING, which Lark itself "
    "accepts and files in the calling application's own root. ONE REAL TOKEN IS REFUSED TOO, "
    "AND BY TYPE RATHER THAN BY PROSE — with the guarantee's own limit in the same breath: ",

    ". WHAT THIS FENCE IS: a refusal, not a folder factory. It picks no default place for you "
    "and makes no folder of its own to put things in — which is a statement about the fence, "
    "NOT a claim that no folder-creating verb ships, because one does and the remedy below "
    "names it. There is no opt-out and no flag restoring the old default. THE REMEDY, IN THE "
    "ORDER THE REFUSAL STATES IT: ",

    "; ",

    "; ",

    ". A create INSIDE an object the caller already named — a block, a table, a column, a row, "
    "a view, an anchored image, a version, a comment — is not in scope: the parent is the "
    "destination and it was already supplied.",
)

#: The projected halves, in the order the refusal itself states them (LD-565's order, inherited
#: rather than re-derived). ``ROOT_IS_NOT_A_DESTINATION`` is what makes the root refusal ship
#: WITH ITS LIMIT: the limit is that constant's own last clause, so a bare "it refuses the root"
#: is unreachable from here.
_PROJECTED = (
    DESTINATION_RULE,
    ROOT_IS_NOT_A_DESTINATION,
    WHAT_TO_SUPPLY,
    HOW_TO_GET_A_DESTINATION,
    WHAT_A_FOLDER_COSTS,
)


def _destination_contract():
    from larkdocio import capabilities

    return capabilities(full=True)["safety_contracts"]["caller-supplied-destination"]


def _woven(scaffold=_SCAFFOLD, projected=_PROJECTED):
    out = []
    for index, piece in enumerate(scaffold):
        out.append(piece)
        if index < len(projected):
            out.append(projected[index])
    return "".join(out)


def test_ac3_the_summary_IS_the_constants_woven_into_a_named_scaffold():
    """Whole-construction equality: every byte of the summary is either one of this module's
    five constants or one of the six connective fragments named above. A fourth free-floating
    restatement of the rule has nowhere to live."""
    assert _destination_contract()["summary"] == _woven()


def test_ac3_every_destination_constant_appears_VERBATIM_in_the_summary():
    """The readable half of the equality above — and the one that names which constant is
    missing when the equality fails."""
    summary = _destination_contract()["summary"]
    for constant in _PROJECTED:
        assert constant in summary, constant[:60]


def test_ac3_the_projection_HAS_TEETH_move_a_constant_byte_and_the_summary_moves():
    """The ruling's load-bearing clause is *"projected … so it cannot drift a third time"*. A
    projection that is really a copy would pass every presence check above and still drift, so
    this test moves a byte in the authoring site and demands the payload move with it."""
    from larkdocio.capabilities import _contracts
    from larkdocio.common import destination as destination_module

    moved = DESTINATION_RULE + " (a byte moved in the authoring site)"
    original = destination_module.DESTINATION_RULE
    try:
        destination_module.DESTINATION_RULE = moved
        summary = _contracts._safety_contracts()["caller-supplied-destination"].summary
        assert moved in summary, "the summary did not follow the constant — it is a copy"
        assert summary == _woven(projected=(moved,) + _PROJECTED[1:])
    finally:
        destination_module.DESTINATION_RULE = original
    assert DESTINATION_RULE in _destination_contract()["summary"]


def test_ac3_the_applies_to_list_is_ELEMENT_FOR_ELEMENT_UNCHANGED():
    """This change moves prose and nothing else: the five surfaces the fence reaches are the
    five it reached before, in the same order."""
    assert _destination_contract()["applies_to"] == [
        "docx-write", "sheets-write", "base-schema-write",
        "drive-folders-write", "drive-files-write",
    ]


def test_ac4_the_root_refusal_CANNOT_SHIP_WITHOUT_ITS_LIMIT():
    """A bare *"the library refuses the application's own root"* is the defect. Because the
    disclosure is projected from the constant that carries the limit in its own last clause,
    the two arrive together or not at all — asserted on the shipped payload, both halves."""
    summary = _destination_contract()["summary"]
    assert "refused by type" in summary
    assert "its own accessor handed you" in summary
    assert "copied in from elsewhere" in summary


def test_ac4_the_CREATES_NO_FOLDER_clause_no_longer_reads_as_a_DENIAL():
    """The same defect (a) fixes in DRIVE.md, wearing a different costume: a fence that says it
    creates no folder, beside a shipped create_folder the fence's own remedy offers. The clause
    now says what it is a statement ABOUT."""
    summary = _destination_contract()["summary"]
    assert "CREATES NO FOLDER" not in summary
    assert "a refusal, not a folder factory" in summary
    assert "NOT a claim that no folder-creating verb ships" in summary
    # LD-565's remedy order is inherited whole, so create_folder is named as remedy TWO.
    assert summary.index("open a folder in your own Drive") < summary.index("create_folder(")


def test_ac3_the_projection_INTRODUCES_NO_IMPORT_CYCLE():
    """Stated as a checked fact, not an assurance: the authoring module imports the error type
    and nothing else, so the new edge from the capabilities package cannot close a loop."""
    import ast
    import pathlib

    source = pathlib.Path(
        larkdocio_destination_source := __import__(
            "larkdocio.common.destination", fromlist=["destination"]).__file__)
    assert source.exists(), larkdocio_destination_source
    imported = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert {name for name in imported if name.startswith("larkdocio")} == {
        "larkdocio.common.errors"}
