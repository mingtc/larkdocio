# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""The shipped guide's hand-prose documents the two download flags LD-340 added —
``--local-time`` and ``--route SUBPATH`` — in the section ``download --help`` / ``-o``
point a reader to, WITHOUT touching the generated CONFIG-SCHEMA projection.

Why this guard exists: the CLI help for the filename stamp and for ``-o`` both end with
"Read it in `larkdocio guide`", so the guide prose those pointers land on must actually
describe the flags. Before this change it said the stamp is UTC-only (omitting
``--local-time``) and that routing has "no command-line flag for it" full stop (omitting
the ``--route`` destination override), so the pointers landed on contradicted prose.

The flags are CLI-only, so this is a HAND-PROSE contract, not a schema one: ``local_time``
must NOT appear inside the generated ``CONFIG-SCHEMA`` block (it is not an ``OutputConfig``
key), and the block stays a byte projection of ``capabilities.config_schema_markdown``.
"""
from larkdocio import guide

#: LD-650 retitled this chapter (the old heading named a document format the library
#: no longer knows about). The slug is stated once, here, and both arms below read it.
_ROUTING_SLUG = "where-the-file-lands-o-and-route-when-you-name-the-subpath"


def _config_schema_block(text: str) -> str:
    b = text.index("<!-- BEGIN CONFIG-SCHEMA")
    e = text.index("<!-- END CONFIG-SCHEMA")
    return text[b:e]


# --------------------------------------------------------------------------- #
# AC1 (S3) — the filename sub-rule documents --local-time.                      #
# --------------------------------------------------------------------------- #

def test_filename_rule_documents_local_time_flag_and_its_tradeoff():
    section = guide(section=_ROUTING_SLUG)
    assert "--local-time" in section, (
        "the filename sub-rule does not mention --local-time — the CLI help points here"
    )
    lowered = section.lower()
    # default is UTC, the flag opts into the machine-local clock
    assert "utc" in lowered and "local" in lowered
    # the disclosed trade-off: the filename ledger becomes machine-dependent
    assert "machine-dependent" in lowered or "machine dependent" in lowered


# --------------------------------------------------------------------------- #
# AC2 (S4) — the placement recipe documents --route as THE way output moves.    #
#            (LD-650: it used to be documented as distinct from an on/off toggle #
#            for a body-sniffing derivation; both are gone, so what the recipe   #
#            must now say is that --route is the caller's and the only one.)     #
# --------------------------------------------------------------------------- #

def test_routing_recipe_documents_route_as_the_one_caller_supplied_destination():
    section = guide(section=_ROUTING_SLUG)
    assert "--route" in section, "the placement recipe does not mention --route"
    lowered = section.lower()
    assert "the one way" in lowered or "only way" in lowered, (
        "--route is not framed as THE way output is placed under a subpath"
    )
    # And the negative half, which is the actual product of LD-650: the library infers no
    # destination from the document. A recipe that only said "pass --route" would leave a
    # reader upgrading from an earlier release wondering what happened to their subpaths.
    assert "infers nothing" in lowered, (
        "the recipe must state that the library derives no destination from the document"
    )


# --------------------------------------------------------------------------- #
# AC3 — the generated projection is untouched: local_time is CLI-only, never an  #
#       OutputConfig schema key, and stays outside the CONFIG-SCHEMA fences.     #
# --------------------------------------------------------------------------- #

def test_local_time_is_not_added_to_the_generated_config_schema_block():
    block = _config_schema_block(guide(full=True))
    assert "local_time" not in block and "--local-time" not in block, (
        "--local-time is a CLI-only flag; it must not enter the OutputConfig schema table"
    )
    # (The block's byte-projection-of-capabilities() invariant is guarded authoritatively by
    # tests/test_download_output_docs.py::test_ac5_the_GUIDE_carries_the_generated_region_byte_identically.)
