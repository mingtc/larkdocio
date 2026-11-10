#!/usr/bin/env bash
# KIT-CLASS: MIXED — kit pattern (one gate runner, uniform invocation), PROJECT gates (pytest, python -m build). See process/EXTRACTION.md.
# (Names below that the public repository lacks — PROJECT.md, CLAUDE.md, process/, requirements/,
# scripts/release.sh, scripts/finish-pr.sh — are the maintainers' process kit, kept in their
# private working repository. The script itself needs none of them.)
# scripts/verify.sh — the one-shot quality-gate runner (PROJECT.md § Quality gates & how to verify).
#
# larkdocio is a Python CLI/library, so the binding static + unit stack is deliberately small and
# tooling-agnostic: pytest is the floor, and `python -m build` proves the package still assembles.
# Every role/agent runs the SAME commands in the SAME order instead of re-deriving them from docs.
#
#   ./scripts/verify.sh             # pytest  →  python -m build (sdist+wheel)
#   ./scripts/verify.sh --quick     # pytest only (fast sanity gate; used by finish-pr.sh post-merge)
#   ./scripts/verify.sh --scope tests/test_foo.py 'tests/test_bar.py::test_baz'
#                                   # the named tests PLUS the always-on drift-guard set
#
#     --scope is for the TDD INNER LOOP ONLY. The FULL suite remains mandatory at the
#     dev_complete handoff, at QA, and at release — coverage is never cut and the drift guards
#     are never skipped (LD-354). There is NO flag, env var or argument combination that runs a
#     scoped selection without the guard set: a scoped run that could skip the cross-cutting
#     guards would let a change sail past the very tests designed to catch it from a distance.
#     --scope never runs the build gate, so --quick alongside it is accepted and redundant.
#     The guard set's full membership is the GUARD_SET array below, readable without running
#     anything; parallelism (-n auto, LD-353) is inherited from pyproject addopts.
#
# NOT covered here (by design — no web/Node tooling in this project): the LIVE round-trip check
# against the sacrificial scratch doc. That is a MANUAL QA gate for any PR touching API-facing code
# (PROJECT.md § "The binding QA gate") — it needs real Lark write credentials and a disposable doc,
# so it is never wired into an unattended runner. pytest green is the floor; the live check is the
# ceiling QA owns by hand.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ─────────────────────────────────────────────────────────────────────────────────────────────
# THE GUARD SET — the always-on floor of a --scope run (LD-354).
#
# WHAT BELONGS IN IT (the inclusion rule, one sentence): a test module whose subject is a
# CROSS-CUTTING DRIFT GUARD — it holds a hand-maintained or generated artifact (a capability
# matrix, the permissions projection, the front door, a shipped/packaged doc, a registry's
# completeness) against real code ELSEWHERE in the tree, so it reddens for a change made
# somewhere else. That is exactly the class of failure a scoped run would otherwise miss,
# which is why membership here is not optional and no flag disables it.
#
# WHAT DOES NOT: a test of one surface's own behavior, however important (e.g. the STALE_*
# CAS guards, the live-gate ring) — those redden for a change made in the file under test, so
# the Dev's own --scope selection already covers them.
#
# WHO UPDATES IT: the Dev who adds or renames a cross-cutting guard, IN THE SAME CHANGE — the
# same rule PROJECT.md § "Living capability matrices" applies to the matrices themselves.
#
# HOW THAT IS HELD, in both directions (LD-649 — before it, neither half was true of the
# canonical gate and the second half did not exist at all):
#   * LIST → TREE. **Every invocation of this runner** — bare, --quick and --scope alike —
#     refuses to start if a listed path has vanished (the existence check below, which is
#     UNCONDITIONAL; it used to be reachable only on the --scope path, so the mandatory gate
#     never ran it). A rename that forgets this list fails loudly instead of quietly shrinking
#     the floor. `tests/test_verify_gate_reporting.py` holds the check outside the branch.
#   * TREE → LIST. Every member carries a `GUARD-SET MEMBER` marker line, and
#     `tests/test_verify_gate_reporting.py` holds the marked set and this array EQUAL both ways
#     over a non-empty population. So a member that is renamed, moved or un-marked reddens, and
#     a newly written guard that declares itself a member but never reaches this array reddens
#     too. What neither direction can catch is a guard that declares nothing AND is never
#     listed — membership is a judgment about what a test's subject IS (the inclusion rule
#     above), and no static property of a test module distinguishes it: about a third of the test modules
#     walk the tree (199 of 600, counted on or before 2026-09-18 — the oldest commit that
#     records the figure; not re-derived since), so a code-derived population would be a long
#     exclusion list (165 rows at that count). The marker
#     makes the judgment explicit and mechanically held; it does not make it automatic.
#
# The membership is READABLE HERE, without running anything — that is the point of a list
# rather than only a marker scattered across the modules, or a glob over names containing
# "guard".
GUARD_SET=(
  # The capability matrices (PROJECT.md § "Living capability matrices").
  tests/test_blocks_md_matrix.py
  tests/test_sheets_md_matrix.py
  tests/test_base_md_matrix.py
  tests/test_base_schema_matrix.py
  tests/test_drive_md_matrix.py
  tests/test_mermaid_rules_matrix.py
  # The permissions pair (PROJECT.md § "Permissions are the THIRD living matrix").
  tests/test_permissions_registry.py
  tests/test_permissions_docs.py
  # The FOURTH direction (LD-442, D-78) — a public call site the declaration never named. It is
  # seeded from the CODE, so it reddens for a client method added anywhere in the tree.
  tests/test_permissions_call_site_completeness.py
  # The refusal-shape guard (LD-644). Owed here NOW rather than before, because before it
  # could not bite: its detector matched one literal class name, answered `[]` over 29
  # denial-owning modules, and would have added nothing to a scoped floor. It now walks the
  # class graph and reddens for a code-carrying raise added ANYWHERE in the tree.
  tests/test_permission_refusals.py
  # The front door (PROJECT.md § "The front door is guarded the same way").
  tests/test_front_door_doctrine.py
  tests/test_consumer_dialect_guard.py
  tests/test_front_door_truth.py
  tests/test_cli_front_door_truth.py
  # The doc-drift family, incl. the prose/wording guards.
  tests/test_doc_drift_guards.py
  tests/test_doctrine_and_recipes.py
  tests/test_prose_signature_guard.py
  tests/test_fidelity_scope_wording_guard.py
  # Shipped/packaged-doc content guards — a claim in the wheel's own docs vs the code.
  tests/test_base_shape_docs.py
  tests/test_guide_flag_docs.py
  tests/test_download_output_docs.py
  # LD-650 — the download verb's consumer contract, pinned by execution (signature shape and
  # the six positional bindings, the routing record's five unconditional keys, the three
  # parsed log shapes counted off log-call ARGUMENTS across the whole package). Cross-cutting
  # by construction: the log-emitter arms walk every module under src/larkdocio, so a second
  # emitter of a consumer-parsed line added ANYWHERE reddens here.
  tests/test_download_route_contract_pins.py
  tests/test_comment_anchor_claim_guard.py
  tests/test_absence_claims_guard.py
  tests/test_cleanup_deps_docs.py
  tests/test_docs_cleanup_lows.py
  tests/test_dev_repo_citations.py
  # LD-659 — the MIRROR of the line above: a label that calls a file the wheel DOES carry
  # unshipped. Cross-cutting by construction: its corpus is derived from packaging (every
  # packaged module and document), and its answer is derived from the wheel's own manifest, so
  # a document that starts or stops shipping reddens here rather than in the file that moved.
  tests/test_citation_label_truth.py
  tests/test_changelog_register_citations.py
  # LD-472 — the sheets doc-truth guards. Cross-cutting by construction: they hold shipped
  # prose against code elsewhere (SheetTab's fields, the rich-cell constructors' __doc__, the
  # CLI's sheets refusal), so a read-route change that makes the hidden-tab paragraph false
  # reddens here rather than in the file that changed.
  tests/test_sheets_doc_truth_ld472.py
  # LD-530 — the capabilities() anchor: the ONE whole-payload tripwire, the per-address
  # localized pins and the bidirectional completeness arm. Cross-cutting by construction: it
  # holds the generated pin table (tests/capabilities_anchor.py) against the live payload, so a
  # leaf moved ANYWHERE under src/larkdocio — a surface's prose, a guide heading, a shared
  # permission-evidence string bleeding across two surfaces — reddens here rather than in the
  # file that changed. That is exactly the class a --scope run would otherwise sail past.
  tests/test_capabilities_package_split.py
  # Registry completeness — a new handler/op/live-gate with no registration reddens here.
  tests/test_registry.py
  tests/test_gate_registry.py
  tests/test_sheets_registration_seam.py
  # LD-637 — the schema-op family walk. Cross-cutting by construction: it reads the PACKAGE on
  # disk (ast, no import) and reddens for a family module added ANYWHERE under src/larkdocio
  # that never got its line in base/schema_ops.py's hand-written FAMILY_MODULES — the ablation
  # the whole suite sailed past on 2026-09-03 (19,693 passed, rc=0), because such a module is
  # invisible to destructive_ops() and so to the consent fence.
  tests/test_base_schema_family_registration.py
  # LD-647 — the Base destructive-verb CENSUS and the fence/front-door claims that describe it.
  # Cross-cutting by construction: the census is derived from all THREE Base op registries, so an
  # op with a destructive verb added to ANY of them — or a fenced op dropped out of
  # destructive_ops() — reddens here rather than in the file that changed, and the shipped
  # help(larkdocio.base) text is held against __all__ and the live attribute namespace.
  tests/test_base_destructive_claim_truth.py
  # LD-660 — the HOST assumptions, and the encoding census that is their population. Cross-
  # cutting by construction: the census is an AST walk over src/, tests/ and scripts/, so a
  # bare read_text()/write_text()/open() added ANYWHERE in the repo reddens here rather than in
  # the file that added it — the whole point of landing the census as a guard instead of a
  # one-off sweep. The same module also pins the shipped read seam's codec, the permissions
  # corpus's totality, and the xdist/tomllib/fcntl host claims.
  tests/test_host_assumptions.py
  # The runner's own contract, and the parallel-suite wiring it depends on (LD-353).
  tests/test_verify_gate_reporting.py
  tests/test_parallel_offline_suite.py
)
# ─────────────────────────────────────────────────────────────────────────────────────────────

QUICK=0
SCOPE=()
SCOPED=0
in_scope=0
for arg in "$@"; do
  case "$arg" in
    --scope) SCOPED=1; in_scope=1 ;;
    --quick) QUICK=1; in_scope=0 ;;
    -h|--help) sed -n '3,26p' "${BASH_SOURCE[0]}" | sed 's|^# \{0,1\}||'; exit 0 ;;
    -*) echo "verify.sh: unknown arg '$arg' (known: --quick, --scope <paths…>, --help)" >&2; exit 2 ;;
    *)
      # A bare word is a scope path only after --scope; anything else is still the old loud
      # failure. Note a flag-looking arg AFTER --scope is caught by the -* branch above, so a
      # typo'd flag can never be swallowed as a test path.
      if [ "$in_scope" -eq 1 ]; then
        SCOPE+=("$arg")
      else
        echo "verify.sh: unknown arg '$arg' (known: --quick, --scope <paths…>, --help)" >&2; exit 2
      fi
      ;;
  esac
done

if [ "$SCOPED" -eq 1 ] && [ "${#SCOPE[@]}" -eq 0 ]; then
  echo "verify.sh: --scope needs at least one test path or node-id" >&2; exit 2
fi

# A vanished guard is a hard stop, never a silent shrink of the floor.
#
# UNCONDITIONAL (LD-649). This check used to sit inside `if [ "$SCOPED" -eq 1 ]`, so the
# canonical gate — bare `./scripts/verify.sh`, the one that is mandatory at the dev_complete
# handoff, at QA and at release — never ran it, and the comment above claiming "the runner
# refuses to start if a listed path has vanished" was true only of the TDD inner loop. A check
# the canonical run skips is a check that has stopped checking: the rename it exists to catch
# would have reached QA green. It now runs on every invocation, before any gate, so the refusal
# is the same on the bare runner, on --quick and on --scope.
missing=()
for g in "${GUARD_SET[@]}"; do [ -e "$g" ] || missing+=("$g"); done
if [ "${#missing[@]}" -ne 0 ]; then
  echo "verify.sh: GUARD_SET names ${#missing[@]} path(s) that no longer exist: ${missing[*]}" >&2
  echo "verify.sh: fix the list in this script (LD-354) — the guard floor must stay complete." >&2
  exit 2
fi

# Resolve the interpreter: prefer the project venv, then python3, then python.
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

RESULTS=()
FAILED=0
run_gate() {
  local name="$1"; shift
  echo
  echo "── GATE: $name"
  if "$@"; then
    RESULTS+=("PASS  $name")
  else
    RESULTS+=("FAIL  $name")
    FAILED=1
  fi
}

# Verbosity is deliberately NOT repeated here. `pyproject.toml`'s `addopts` already supplies
# `-q`, and a second `-q` on this command line stacked into `-qq` — which suppresses pytest's
# summary count line, so the canonical gate reported the suite it had just run without ever
# printing a number, and every count quoted in a review had to come from a separate invocation.
# One definition of the default verbosity, owned by `addopts`, is what keeps the count visible.
#
# The DEFAULT path below is untouched by --scope: bare `verify.sh` and `--quick` still run the
# canonical gate line verbatim, which `tests/test_verify_gate_reporting.py` and
# `tests/test_parallel_offline_suite.py` both pin literally. The scoped run is a SEPARATE,
# differently-named gate rather than extra arguments spliced into that line, so the canonical
# invocation stays one exact string that a guard can hold. Parallelism is NOT re-specified in
# either: `-n auto` lives in pyproject's addopts (LD-353), so a scoped run inherits it for free.
if [ "$SCOPED" -eq 1 ]; then
  # The Dev's paths PLUS the whole GUARD_SET, deduplicated so naming a guard in the scope does
  # not collect it twice.
  PYTEST_ARGS=()
  for a in "${SCOPE[@]}" "${GUARD_SET[@]}"; do
    seen=0
    for b in "${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}"; do [ "$b" = "$a" ] && seen=1 && break; done
    [ "$seen" -eq 0 ] && PYTEST_ARGS+=("$a")
  done
  echo
  echo "── SCOPED RUN (TDD inner loop only): ${#SCOPE[@]} requested path(s) + ${#GUARD_SET[@]} always-on drift guards."
  echo "   The FULL suite remains mandatory at the dev_complete handoff, at QA and at release."
  # `--dist loadfile` (xdist's per-file distribution) is the ONE refinement a scoped run adds on
  # top of the inherited `-n auto`. Reason, measured under LD-354: a handful of guard modules
  # mutate a REAL repo file and restore it (e.g. the permissions-docs pointer guard's own
  # bite-red test), and at full-suite size those tests are diluted across the whole collection,
  # while a scoped selection two orders of magnitude smaller lands their siblings on OTHER
  # workers at the same instant — so an unmodified
  # `--scope` run reddened 3 times in 3 on a test that is green serially and green as a single
  # node-id. Pinning a file's tests to one worker removes the intra-file window without giving
  # up parallelism (3/3 green, 23.8-31.2s vs 87.2s serial). The underlying test-side race is
  # filed separately; this line is the inner loop refusing to teach a Dev to ignore red.
  run_gate "pytest (scoped + guards)" "$PY" -m pytest --dist loadfile "${PYTEST_ARGS[@]}"
else
  run_gate "pytest"        "$PY" -m pytest
fi

if [ "$QUICK" -eq 0 ] && [ "$SCOPED" -eq 0 ]; then
  # Packaging sanity — the wheel + sdist still build. Output to dist/ (gitignored).
  # Skipped by --quick (finish-pr.sh's post-merge check wants a fast pytest-only gate).
  run_gate "python -m build" "$PY" -m build --outdir "$REPO_ROOT/dist"
fi

echo
echo "═══ verify.sh summary ═══"
printf '%s\n' "${RESULTS[@]}"
exit "$FAILED"
