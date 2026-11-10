"""Diagram add-on (Type 40) hardening tests.

The mermaid handler parses ``add_ons.record`` as JSON. If the JSON decodes to a
non-dict (a list or a bare string), the old code called ``.get('data', '')`` on
it and raised AttributeError, aborting the whole document render. The unsupported
add-on branch also interpolated a possibly-``None`` component id, printing the
literal string 'None'.
"""
from harness import render

MERMAID_ID = "blk_640017963d808005a21a6445"


def _block(record, component_type_id=MERMAID_ID):
    return [{
        "block_id": "b40",
        "block_type": 40,
        "add_ons": {
            "component_id": "c1",
            "component_type_id": component_type_id,
            "record": record,
        },
    }]


def test_mermaid_record_json_list_does_not_crash():
    # record JSON decodes to a list -> must not raise, graceful output.
    out = render(_block('[1, 2, 3]'))
    assert out is not None


def test_mermaid_record_json_string_does_not_crash():
    # record JSON decodes to a bare string -> must not raise.
    out = render(_block('"just a string"'))
    assert out is not None


def test_mermaid_record_valid_dict_renders_source():
    out = render(_block('{"data": "graph TD; A-->B"}'))
    assert "graph TD; A-->B" in out
    assert "```mermaid" in out


def test_unsupported_add_on_never_prints_none():
    # component_type_id missing -> placeholder must not contain the literal 'None'.
    out = render(_block("{}", component_type_id=None))
    assert "None" not in out
