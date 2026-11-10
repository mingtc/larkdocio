"""The SHAREABILITY disclosure — a docx-bound media token is not an independently
shareable object, and the reading that explains it ships labelled as an INFERENCE.

Three things are guarded here, because a disclosure that is only half-said is the shape a
consumer plans around and then discovers at the worst moment:

1. **the measured half** — both halves of the sharing recipe that works on a *file* object are
   refused on a **docx-bound media token**, while the same two calls on a drive-uploaded file
   token succeed;
2. **the labelled half** — the *"its access rides its parent document"* reading is an
   **inference from two refusals, not a measurement of the rule**, and says so in the text a
   consumer reads rather than in a commit message;
3. **the steer** — a caller who needs an **independently shareable** file wants the folder
   route, not the attachment card.

The claim is **authored once** (``larkdocio.base.media``) and quoted everywhere else, the same
discipline the residue and empty-upload disclosures already live under; this module fails if a
second authoring appears, if a home drops it, or if the inference label is quietly upgraded
into a measurement.

Conformance-tier: this pins **measured external truth and a product contract**
(``process/doctrine/conformance-tier.md`` § A.4).
"""
import pathlib
import re

import pytest

from larkdocio import capabilities
from larkdocio.base.media import MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE as CLAIM
from larkdocio.drive import files_write as drive_files_write
from larkdocio.write import media as write_media
import private_tree  # noqa: E402  (LD-685)

pytestmark = pytest.mark.conformance

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "larkdocio"

#: The three clauses, as phrases a reader can grep for. Each one is a *separate* failure so a
#: partial implementation cannot pass with the loudest third of the disclosure.
MEASURED_HALF = "CANNOT BE PERMISSION-GRANTED"
INFERENCE_LABEL = "inference from two refusals, not a measurement"
ROUTE_STEER = "put_file_in_folder"


# --------------------------------------------------------------------------- #
# The claim itself — all three clauses, in one authoring.                      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("clause", [MEASURED_HALF, INFERENCE_LABEL, ROUTE_STEER])
def test_the_claim_carries_all_three_clauses(clause):
    assert clause in CLAIM


def test_the_contrast_is_stated_rather_than_only_the_refusal():
    """Half the evidence is that the SAME TWO CALLS succeed on a drive-uploaded file token.

    Without the successful half, the refusals read as *"sharing does not work here"* — which
    is the wrong lesson and the one that would send a caller down the attachment route.
    """
    assert "DRIVE-UPLOADED FILE token succeed" in CLAIM


def test_the_inference_is_NOT_dressed_as_a_measurement():
    """The reading may be offered; it may not be stated as the rule."""
    assert "LABELLED AS AN INFERENCE" in CLAIM
    assert "appears to" in CLAIM
    # …and the reason the two refusals do not prove a policy is said, not implied.
    assert "rather than a scope denial" in CLAIM


def test_the_untried_forms_are_named_unmeasured_rather_than_refuted():
    assert "UNMEASURED, NOT REFUTED" in CLAIM
    for form in ("user_access_token", "other tenants"):
        assert form in CLAIM


def test_the_claim_is_authored_EXACTLY_ONCE_in_the_shipped_tree():
    """One authoring, quoted — never a second copy that can drift into disagreeing."""
    authorings = [
        path.relative_to(REPO).as_posix()
        for path in SRC.rglob("*.py")
        if MEASURED_HALF in path.read_text("utf-8")
    ]
    assert authorings == ["src/larkdocio/base/media.py"], authorings


# --------------------------------------------------------------------------- #
# Every home a caller actually looks in.                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("module", [write_media, drive_files_write], ids=lambda m: m.__name__)
def test_both_media_routes_QUOTE_the_disclosure_in_their_own_docstring(module):
    """The attachment leg mints the token; the folder leg is the answer to it.

    A caller reads whichever module they are already using, so both carry it — and both carry
    the *same* sentence rather than two paraphrases.
    """
    doc = module.__doc__ or ""
    assert CLAIM in doc
    assert "<<" not in doc, "an unreplaced quotation marker shipped"


def _unwrapped(path: pathlib.Path) -> str:
    """Prose wrapped at 95 columns is still one sentence — read it as one."""
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


def test_the_shipped_guide_carries_the_disclosure_and_the_route_steer():
    guide = _unwrapped(SRC / "GUIDE.md")
    assert "cannot be permission-granted" in guide.lower()
    assert "inference from two refusals, not a measurement" in guide
    assert "put_file_in_folder" in guide


def test_capabilities_reports_it_on_the_surface_that_mints_the_token():
    """The machine-readable answer moves with the prose, or a consumer querying the library
    gets a different story from the one the guide tells."""
    note = capabilities(full=True)["surfaces"]["docx-write"]["credentials"]["note"]
    assert "PERMISSION-GRANTED" in note.upper()
    assert "inference" in note.lower()
    assert "put_file_in_folder" in note


@private_tree.register
@pytest.mark.parametrize("doc", ["BLOCKS.md", "DRIVE.md", "requirements/DECISIONS.md"])
def test_the_matrices_and_the_register_carry_the_disclosure_with_its_evidence(doc):
    """Where a maintainer looks it up — and with the capture pointers, both halves.

    The evidence is a *pair*: the two refusals AND the two successes. A row citing only the
    refusals would leave the contrast — the part that makes it a route choice — unsupported.
    """
    text = _unwrapped(REPO / doc)
    assert "cannot be permission-granted" in text.lower()
    assert "inference from two refusals" in text.lower()
    refusals = re.search(r"51[89]-", text)
    successes = re.search(r"51[67]-", text)
    assert refusals and successes, f"{doc} cites {refusals=} {successes=}"


# --------------------------------------------------------------------------- #
# The WIDENING (LD-442) — the same refusal was measured on a BASE-bound token,  #
# and three corroborations came with it. Measured external truth, so this whole #
# module's `conformance` mark is the right one for these too.                   #
# --------------------------------------------------------------------------- #

def test_the_claim_covers_the_BASE_bound_token_and_not_only_the_docx_one():
    """The under-statement this widening fixes: the same two refusals were measured on a
    Base-bound token, in both spellings, and a text that said only *docx* told a Base caller
    nothing while describing their case exactly."""
    assert "PARENT-BOUND MEDIA TOKEN CANNOT BE PERMISSION-GRANTED" in CLAIM
    assert "DOCX-BOUND AND THE BASE-BOUND" in CLAIM
    assert "bound to a Base" in CLAIM


def test_the_permission_family_READS_the_token_and_refuses_only_to_MUTATE_it():
    """The corroboration that rules out *'the family does not know this token'* — and the
    control that makes the read a real resolution rather than an echo."""
    assert "READS such a token happily" in CLAIM
    assert "1063001" in CLAIM


def test_the_bytes_stop_being_fetchable_when_the_PARENT_dies_and_the_permalink_does_not():
    """Reachability and existence are different axes, and the row a reader looks this up in
    (`BASE.md` row 10) says so because the claim would otherwise be over-read either way."""
    assert "trashing the parent" in CLAIM
    assert "UNFETCHABLE" in CLAIM
    assert "KEEP RESOLVING" in CLAIM
    assert "RESTORE of the parent is UNMEASURED" in CLAIM


def test_the_corroborations_do_NOT_promote_the_inference_to_a_measurement():
    """Three positive-side observations arrived; the label did not move. That is the whole
    discipline — corroborated is not measured."""
    assert "Corroborated is not promoted" in CLAIM
    assert "inference from two refusals, not a measurement" in CLAIM


def test_the_CROSS_FAMILY_refusal_is_disclosed_where_the_steer_is_MADE():
    """M4: *'put it in a folder instead'* reads as advice to someone whose column needs an
    attachment — unless the other half is said in the same breath."""
    assert "does not belong to this bitable" in CLAIM
    assert "1254303" in CLAIM
    steer = CLAIM.index(ROUTE_STEER)
    assert CLAIM.index("does not belong to this bitable") > steer, (
        "the refusal must follow the steer it qualifies, in the same disclosure")


@pytest.mark.parametrize("doc", ["BASE.md", "DRIVE.md"])
def test_the_matrices_carry_the_parent_death_nuance_with_its_reason_PRESERVED(doc):
    """Supersession, both halves: the nuance is added and row 10's original reason — residue
    accretes, no open-API purge verb exists — is still there to be read."""
    text = _unwrapped(REPO / doc)
    assert "keep resolving" in text.lower()
    assert "restore" in text.lower() and "unmeasured" in text.lower()
    assert "no open-api purge verb" in text.lower() or "nothing purges" in text.lower()
