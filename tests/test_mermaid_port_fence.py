"""The mermaid package's standing boundary conditions: determinism, packaging, offline, text.

Four properties that are about the package **as it sits in the tree** rather than about
either compiler — each one has the same answer on every branch, on every day:

* **Determinism.** The same spec compiles to the same bytes — across calls, across key
  insertion orders, and across processes with different hash seeds.
* **Packaging.** The shipped rule document travels inside the wheel *by construction*, and
  the defect of shipping a document nobody can open cannot be re-created here.
* **Offline.** Nothing in the package can reach a network or a document: the import surface
  is checked, not promised.
* **The shipped text.** Every string this package carries is free of the internal dialect,
  and it says what an offline test cannot settle.

**Why the change fence this file used to open with is gone, and must not be reinvented.**
The retired first property was a *fence*: "this change adds ``src/larkdocio/mermaid/`` and
its tests and touches nothing else", asserted against a live ``git diff <trunk>...HEAD``
plus ``git status --porcelain``. That is a claim about **one branch's diff and one
reviewer's working state**, not about the repository, and it was true exactly once — on the
port's own branch. Once the port merged, the only tree that could still satisfy it was a
pristine trunk checkout, so it reddened on **every** later branch (and on any dirty file),
naming that branch's own innocent paths as fence violations: the whole tranche after the
port handed off carrying one failing test that belonged to a change which had already
landed. A guard that cries wolf is how guards get weakened until they guard nothing. The
fence did its job at review time, and the evidence it produced lives where review-time
evidence belongs — in the port issue's QA record — so it was **removed** rather than
narrowed into a form that could never fire again. The standing rule it leaves behind: **a
guard that asserts the shape of a diff — or any other git or working-tree state — must not
land on the trunk**; assert the content of the tree instead, as every test below does. The
same defect was caught and rescoped once before, in
``tests/test_shipped_notes.py::test_ac8_the_shipped_notes_are_documents_not_code``.

**Where the guard that used to sit here went.** This module carried its own scan,
``test_no_test_here_asks_git_what_changed``, whose only job was to keep *this file* from a
third round. It is now **subsumed** by the suite-wide guard in
``tests/test_no_test_reads_live_git.py``, which asserts the same property over the whole test
tree — this module included, by construction — with a widened envelope (a tuple argv, a
``shell=True`` string, an absolute path, name indirection) and a two-entry exemption register
for the only sites legitimately allowed to drive git, both hermetic sandboxes. It was
subsumed rather than kept alongside because two guards asserting one property invite one of
them to be weakened while the other silently covers for it. Read the rule there; the story
stays here, where the defect happened.
"""
import ast
import pathlib
import subprocess
import sys
import textwrap

import consumer_text

import larkdocio.mermaid as mermaid
from larkdocio.mermaid import flowchart, rules, sequence

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO / "src" / "larkdocio" / "mermaid"


# --------------------------------------------------------------------------- #
# DETERMINISM                                                                  #
# --------------------------------------------------------------------------- #

def test_key_insertion_order_does_not_change_the_output():
    """The output is a function of the spec's meaning, not of its dict layout."""
    one = {
        "title": "Order",
        "theme": "neutral",
        "direction": "TD",
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "label": "next"}],
    }
    two = {}
    two["edges"] = [{"label": "next", "to": "B", "from": "A"}]
    two["nodes"] = [{"label": "A", "id": "A"}, {"label": "B", "id": "B"}]
    two["direction"] = "TD"
    two["theme"] = "neutral"
    two["title"] = "Order"
    assert flowchart(one) == flowchart(two)


def test_the_output_is_identical_across_processes_with_DIFFERENT_HASH_SEEDS():
    """Set and dict ordering can vary between processes; the output may not.

    Three subprocesses, three hash seeds, both compilers, compared byte for byte.
    """
    program = textwrap.dedent(
        """
        from larkdocio.mermaid import flowchart, sequence

        drawing = {
            "title": "Seeded",
            "theme": "dark",
            "subgraphs": [{"id": "g1", "label": "Phase 1", "nodes": ["A", "B"]}],
            "nodes": [
                {"id": "A", "label": "A"},
                {"id": "B", "label": "B"},
                {"id": "C", "label": "C"},
            ],
            "edges": [
                {"from": "A", "to": "B"},
                {"from": "B", "to": "C", "label": "then", "style": "dotted"},
            ],
        }
        talk = {
            "theme": "forest",
            "participants": [{"id": "One", "label": "Client"}, "Two", {"id": "Three"}],
            "messages": [
                {"from": "One", "to": "Two", "label": "a"},
                {"from": "Two", "to": "Three", "label": "b", "style": "dotted"},
            ],
        }
        print(flowchart(drawing))
        print(sequence(talk))
        """
    )
    # LD-355: the three probes are INDEPENDENT — different seeds, no shared state, and the
    # assertion is over the collected outputs — so they are launched together instead of
    # one-after-another. Same three seeds, same program, same env, same byte-for-byte
    # comparison in the same order; only the waiting is shared. This was the suite's single
    # longest test (13.2 s), and ~4.4 s of that is one cold `import larkdocio` paid 3x.
    running = [
        (seed, subprocess.Popen(
            [sys.executable, "-c", program],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={"PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO / "src")},
        ))
        for seed in ("0", "1", "12345")
    ]
    outputs = []
    for seed, proc in running:
        stdout, stderr = proc.communicate()
        # `check=True`'s job, kept: a probe that died must fail the test loudly rather than
        # contribute an empty string that happens to equal another empty string.
        assert proc.returncode == 0, f"PYTHONHASHSEED={seed} probe failed:\n{stderr[-2000:]}"
        outputs.append(stdout)
    assert outputs[0] == outputs[1] == outputs[2]
    assert "flowchart TD" in outputs[0] and "sequenceDiagram" in outputs[0]


def test_the_rule_document_is_the_same_text_every_time():
    assert rules() == rules()
    assert rules() == mermaid.MERMAID_RULES


# --------------------------------------------------------------------------- #
# PACKAGING — the document travels with the code                                #
# --------------------------------------------------------------------------- #

def test_the_rule_document_is_carried_by_a_module_INSIDE_the_package():
    """Why this is the packaging property that matters: a module inside a discovered package
    is shipped by the build with no packaging list to keep in step, so the document cannot be
    left behind by an omission the way a data file can."""
    from larkdocio.mermaid import rules_doc

    assert pathlib.Path(rules_doc.__file__).parent == PACKAGE
    assert rules_doc.MERMAID_RULES.strip()


def test_no_unpackaged_document_sits_beside_the_code():
    """The defect this forecloses: a document in the source tree that the wheel does not
    carry is a citation a caller cannot follow. Every file here is a module, so every file
    here ships."""
    strays = sorted(
        path.name for path in PACKAGE.iterdir()
        if path.is_file() and path.suffix != ".py"
    )
    assert not strays, (
        f"these files sit inside the package but are not modules, so a build does not carry "
        f"them unless they are also declared as package data: {strays}"
    )


def test_the_accessor_is_public_and_every_exported_name_resolves():
    assert "rules" in mermaid.__all__
    missing = [name for name in mermaid.__all__ if not hasattr(mermaid, name)]
    assert not missing


def test_the_public_surface_is_the_declared_one():
    """No accidental exports: the names a caller reaches are the ones the module declares."""
    public = {name for name in dir(mermaid) if not name.startswith("_")}
    undeclared = public - set(mermaid.__all__) - {
        "escape",
        "rules_doc",
        "ruleset",
    }
    assert not undeclared, undeclared


# --------------------------------------------------------------------------- #
# OFFLINE — the package cannot reach Lark or a network                          #
# --------------------------------------------------------------------------- #

#: Everything the package is allowed to import. No client, no transport, no SDK, no socket.
ALLOWED_IMPORTS = {
    "re",
    "logging",
    "collections",
    ".escape",
    ".ruleset",
    ".rules_doc",
    ".flowchart",
    ".sequence",
    "..errors",
}


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * (node.level or 0) + (node.module or ""))
    return names


def test_the_package_imports_nothing_that_could_reach_a_network_or_a_document():
    used = set()
    for path in sorted(PACKAGE.rglob("*.py")):  # LD-654: recursive population
        used |= _imports(path)
    assert used <= ALLOWED_IMPORTS, used - ALLOWED_IMPORTS


def test_no_module_here_names_the_client_or_the_sdk():
    """Stated separately because it is the claim a reader cares about."""
    joined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PACKAGE.rglob("*.py"))  # LD-654: recursive
    )
    for forbidden in ("lark_oapi", "urllib", "socket", "http.client", "Client("):
        assert forbidden not in joined, forbidden


def test_compiling_needs_no_credentials_and_no_environment(monkeypatch):
    """Every credential name the toolkit knows is cleared, and compiling still works."""
    for name in (
        "LARK_APP_ID",
        "LARK_APP_SECRET",
        "LARK_READ_APP_ID",
        "LARK_READ_APP_SECRET",
        "LARK_WRITE_APP_ID",
        "LARK_WRITE_APP_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    assert "flowchart TD" in flowchart({"nodes": [{"id": "A", "label": "A"}]})
    assert "sequenceDiagram" in sequence({"participants": ["A"], "messages": []})


# --------------------------------------------------------------------------- #
# THE SHIPPED TEXT — dialect-free, provenance stated in the code                #
# --------------------------------------------------------------------------- #

def _package_texts():
    """``{label: text}`` for every docstring and string literal in the new package."""
    texts = {}
    for path in sorted(PACKAGE.rglob("*.py")):  # LD-654: recursive population
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                texts[f"{path.name}:{node.lineno}"] = node.value
    return texts


def test_no_internal_dialect_in_any_shipped_string_of_the_new_package():
    """The prose, the docstrings and every emitted message, held to the shipped-text rule:
    an issue number, a criterion label or an internal role name means nothing to a reader who
    has only the wheel."""
    offenders = {
        label: consumer_text.dialect_hits(text)
        for label, text in _package_texts().items()
        if consumer_text.dialect_hits(text)
    }
    assert not offenders, offenders


def test_the_dialect_check_here_is_the_shipped_one_and_it_bites():
    """Otherwise the sweep above could be running an empty pattern set."""
    assert consumer_text.dialect_hits("ported in " + "LD-" + "191 per " + "AC4")


def test_the_module_docstring_states_the_provenance_and_its_limit():
    doc = mermaid.__doc__
    lowered = doc.lower()
    assert "stale" in lowered, doc
    assert "re-validate" in lowered, doc
    # And it says what an offline test cannot settle.
    assert "outside this module" in lowered, doc


def test_every_docstring_in_the_package_is_free_of_the_dialect():
    for path in sorted(PACKAGE.rglob("*.py")):  # LD-654: recursive population
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                doc = ast.get_docstring(node)
                if doc:
                    assert not consumer_text.dialect_hits(doc), (path.name, doc[:120])
