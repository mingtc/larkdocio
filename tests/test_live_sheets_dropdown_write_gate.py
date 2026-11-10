"""LD-120 live gate — the Sheets DROPDOWN-RULE write round-trip (the Sheets rich/structural-write spec § F1-S2, D6).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that the LD-120 dropdown-rule write round-trips **through the gated apply
engine** on a self-provisioned disposable: a :class:`~larkdocio.sheets.write_apply.DropdownRuleWriteRequest`
→ ``dry_run`` Plan → ``apply`` writes a ``dataValidation`` list rule (``POST …/dataValidation``),
which is then read back via the **``dataValidation`` GET** (rule) and the **values API**
(the selected value), covering the story's characterization matrix:

* a **multi-select rule on a RANGE** (``A1:A3``) + a **single-select rule on a single cell**
  (``B1``) — rule-on-a-range vs single-cell;
* **values set THROUGH a written rule** — a 2-selection ``multipleValue`` on ``A1`` (read
  back as the comma-joined string, normalized to the same ordered label set, D7) and a
  single-select value on ``B1``;
* **rule-overwrite semantics** — a second rule written over the same range, the rule re-read
  to record replace-vs-accumulate (characterization, recorded not asserted);
* **a value NOT in the option list** — written and read back to record whether Lark refuses
  or accepts it (characterization, recorded not asserted).

The **``90204`` colors caveat** is proven **offline** (the encoder refuses a highlight/colors
mismatch *before* any write — ``tests/test_sheets_rich_encode.py``), so this gate never fires
a deliberate ``90204`` against the live API. Per-rule DELETE-by-id is **uncaptured** (the
LD-107 spike's ``dataValidation`` GET exposes no rule id — ``captures/03b-dropdown.json``); a
best-effort probe records what the live GET exposes, and rule cleanup rides the leak-proof
disposable teardown (the whole sheet is deleted in ``finally``). Writes use the WRITE app only
(``LARK_WRITE_APP_*``); every target is a self-provisioned disposable — never the scratch
sheet, never the zoo, never a real document (D7).
"""
import json
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.rich_encode import normalize_multi_select
from larkdocio.sheets.write_apply import (
    DropdownRuleWriteRequest,
    RichCellWriteRequest,
    apply,
    dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient, normalize_write_range

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

MULTI_CONDS = ["Red", "Green", "Blue"]
SINGLE_CONDS = ["Alpha", "Bravo", "Charlie"]


def _get_rules(request, token, a1_range):
    """The ``dataValidations`` list on ``a1_range`` via ``GET …/dataValidation``.

    The range is forced to ``Start:End`` (a bare single cell like ``B1`` returns no
    rules — the same ``90202`` posture the write endpoints have)."""
    _status, resp = request(
        "GET",
        f"/open-apis/sheets/v2/spreadsheets/{token}/dataValidation",
        None,
        {"range": normalize_write_range(a1_range)},
    )
    return (((resp or {}).get("data") or {}).get("dataValidations")) or []


def _first_rule(rules):
    return rules[0] if rules else {}


def test_sheets_dropdown_rule_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    request = H.build_throttled_write_request(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld120-sheets-dropdown-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        evidence["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"

        sid = d.first_sheet_id
        multi_range = f"{sid}!A1:A3"     # rule on a RANGE
        a1, a2 = f"{sid}!A1", f"{sid}!A2"
        single_cell = f"{sid}!B1"        # rule on a SINGLE cell

        # 1) MULTI-select rule on a RANGE, through the gated engine.
        multi_plan = dry_run(
            [DropdownRuleWriteRequest.list_rule(multi_range, MULTI_CONDS, multiple_values=True)],
            writer, d.token,
        )
        assert len(multi_plan.resolved) == 1, f"multi rule refused at dry-run: {multi_plan.refusals!r}"
        multi_log = apply(multi_plan, writer)
        assert multi_log.entries[0].is_applied, f"multi rule did not apply: {multi_log.entries[0].to_dict()!r}"
        assert multi_log.entries[0].write_kind == "data-validation"
        evidence["multi_rule_revision"] = multi_log.entries[0].revision

        # 2) READ THE RULE BACK (dataValidation GET) — conditionValues + multipleValues.
        multi_rule = _first_rule(_get_rules(request, d.token, multi_range))
        assert multi_rule.get("conditionValues") == MULTI_CONDS, f"rule readback drifted: {multi_rule!r}"
        assert (multi_rule.get("options") or {}).get("multipleValues") is True
        evidence["multi_rule_readback"] = multi_rule.get("conditionValues")

        # 3) A 2-SELECTION multipleValue THROUGH the written rule (LD-119 cell it pairs with).
        multi_val_log = apply(
            dry_run([RichCellWriteRequest.multi_select(a1, ["Red", "Green"])], writer, d.token),
            writer,
        )
        assert multi_val_log.entries[0].is_applied
        read_multi = d.read_values(f"{sid}!A1:A1")[0][0]
        assert normalize_multi_select(read_multi) == normalize_multi_select(
            {"type": "multipleValue", "values": ["Red", "Green"]}
        ) == ("Red", "Green"), f"multi-select did not round-trip: {read_multi!r}"
        evidence["multi_value_readback"] = read_multi

        # 4) SINGLE-select rule on a SINGLE cell + a value through it.
        single_log = apply(
            dry_run([DropdownRuleWriteRequest.list_rule(single_cell, SINGLE_CONDS)], writer, d.token),
            writer,
        )
        assert single_log.entries[0].is_applied
        single_rule = _first_rule(_get_rules(request, d.token, single_cell))
        assert single_rule.get("conditionValues") == SINGLE_CONDS, f"single rule drifted: {single_rule!r}"
        assert (single_rule.get("options") or {}).get("multipleValues") is False
        d.put_values(f"{sid}!B1:B1", [["Bravo"]])
        assert d.read_values(f"{sid}!B1:B1") == [["Bravo"]], "single-select value did not round-trip"
        evidence["single_rule_readback"] = single_rule.get("conditionValues")

        # 5) CHARACTERIZE — a value NOT in the option list (refuse or accept?).
        try:
            d.put_values(f"{sid}!A2:A2", [["Purple"]])  # Purple is not in MULTI_CONDS
            evidence["out_of_list"] = {"accepted": True, "readback": d.read_values(f"{sid}!A2:A2")}
        except LarkAPIError as e:
            evidence["out_of_list"] = {"accepted": False, "code": e.code, "msg": e.msg}

        # 6) CHARACTERIZE — rule-overwrite semantics (a second rule over the same range).
        overwrite_conds = ["One", "Two"]
        apply(
            dry_run([DropdownRuleWriteRequest.list_rule(multi_range, overwrite_conds)], writer, d.token),
            writer,
        )
        after_overwrite = _get_rules(request, d.token, multi_range)
        evidence["overwrite"] = {
            "rule_count_on_range": len(after_overwrite),
            "condition_values": _first_rule(after_overwrite).get("conditionValues"),
            "replaced": _first_rule(after_overwrite).get("conditionValues") == overwrite_conds,
        }

        # 7) BEST-EFFORT delete probe — the GET exposes no rule id in the LD-107 spike, so
        #    record what the live GET actually carries (cleanup rides the teardown regardless).
        evidence["rule_keys_exposed"] = sorted(_first_rule(after_overwrite).keys())
    # 8) delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    evidence["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(
            "\n[live_write:sheets-dropdown-gate] "
            f"token={evidence.get('token')} "
            f"sheet_id={evidence.get('sheet_id')} "
            f"multi_rule={evidence.get('multi_rule_readback')} "
            f"multi_value={evidence.get('multi_value_readback')!r} "
            f"single_rule={evidence.get('single_rule_readback')} "
            f"out_of_list={json.dumps(evidence.get('out_of_list'))} "
            f"overwrite={json.dumps(evidence.get('overwrite'))} "
            f"rule_keys_exposed={evidence.get('rule_keys_exposed')} "
            f"orphans={evidence.get('orphans')}"
        )
