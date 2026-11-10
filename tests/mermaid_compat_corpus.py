"""THE COMPAT CORPUS — every historical spec shape, and the bytes it has always compiled to.

The module absorbed from the older standalone generator brought a compatibility promise with
it: the exact spec shapes its callers had been writing for months — shapes and aliases,
subgraphs, every edge style, the ``length`` and ``invisible`` layout levers, the older bare-
string participant and the older literal-arrow key — keep compiling **verbatim**. This module
holds those specs as data so that promise is one list rather than an assumption spread over
two test files, and ``tests/fixtures/mermaid_compat_bytes.json`` holds the bytes each of them
compiled to **before** the strict-dialect change (captured by running these same specs against
the previous trunk), so the promise is checked byte for byte rather than by re-reading the
assertions.

Every spec here is **inside the dialect**: nothing in this corpus relies on a silent fallback,
a clamp, or a dropped construct. That is what makes it the right thing to hold fixed while the
off-dialect constructs turn into refusals — a spec that only compiled because something was
guessed for it was never compatible, it was just quiet.
"""

CORPUS = {
    # ------------------------------------------------------------------ flowchart
    "header-and-direction-LR": ("flowchart", {
        "direction": "LR", "nodes": [{"id": "A", "label": "Start"}],
    }),
    "direction-TD": ("flowchart", {
        "direction": "TD", "nodes": [{"id": "A", "label": "A"}],
    }),
    "direction-lowercase-td": ("flowchart", {
        "direction": "td", "nodes": [{"id": "A", "label": "A"}],
    }),
    "direction-synonym-TB": ("flowchart", {
        "direction": "TB", "nodes": [{"id": "A", "label": "A"}],
    }),
    "direction-absent": ("flowchart", {"nodes": [{"id": "A", "label": "A"}]}),
    "direction-empty-string": ("flowchart", {
        "direction": "", "nodes": [{"id": "A", "label": "A"}],
    }),
    "title-comment": ("flowchart", {
        "title": "My Flow", "nodes": [{"id": "A", "label": "A"}],
    }),
    "every-shape": ("flowchart", {"nodes": [
        {"id": "R", "label": "Rect", "shape": "rect"},
        {"id": "O", "label": "Round", "shape": "round"},
        {"id": "C", "label": "Cyl", "shape": "cylinder"},
        {"id": "Dm", "label": "Dia", "shape": "diamond"},
    ]}),
    "every-shape-alias": ("flowchart", {"nodes": [
        {"id": "O", "label": "Round", "shape": "rounded"},
        {"id": "Dc", "label": "Dec", "shape": "decision"},
        {"id": "B", "label": "DB", "shape": "database"},
        {"id": "Cn", "label": "Cond", "shape": "condition"},
    ]}),
    "shape-absent": ("flowchart", {"nodes": [{"id": "A", "label": "A"}]}),
    "label-escaping": ("flowchart", {"nodes": [{"id": "A", "label": "Process (New)"}]}),
    "label-html-stripped": ("flowchart", {
        "nodes": [{"id": "A", "label": "Dashboard <script>"}],
    }),
    "solid-arrow-default": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "label": ""}],
    }),
    "solid-length-1": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "solid", "length": 1}],
    }),
    "solid-length-2": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "solid", "length": 2}],
    }),
    "solid-length-3": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "solid", "length": 3}],
    }),
    "solid-length-5-the-ceiling": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "solid", "length": 5}],
    }),
    "dotted-length-1": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "dotted", "length": 1}],
    }),
    "dotted-length-2": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "dotted", "length": 2}],
    }),
    "thick-length-1": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "thick", "length": 1}],
    }),
    "thick-length-2": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "thick", "length": 2}],
    }),
    "invisible-length-1-no-label": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "invisible", "length": 1}],
    }),
    "invisible-length-2": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "invisible", "length": 2}],
    }),
    "invisible-with-an-empty-label": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "invisible", "label": ""}],
    }),
    "edge-label-piped": ("flowchart", {
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "label": "Yes (Logged In)"}],
    }),
    "subgraphs": ("flowchart", {
        "subgraphs": [{"id": "g1", "label": "Phase 1", "nodes": ["A"]}],
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
    }),
    "subgraph-label-absent": ("flowchart", {
        "subgraphs": [{"id": "g1", "nodes": ["A"]}],
        "nodes": [{"id": "A", "label": "A"}],
    }),
    "two-subgraphs": ("flowchart", {
        "subgraphs": [
            {"id": "one", "label": "One", "nodes": ["A"]},
            {"id": "two", "label": "Two", "nodes": ["B"]},
        ],
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
    }),
    "id-with-a-space-sanitized": ("flowchart", {
        "nodes": [{"id": "Mobile App", "label": "Mobile App"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "Mobile App", "to": "B"}],
    }),
    "theme-dark": ("flowchart", {"theme": "dark", "nodes": [{"id": "A", "label": "A"}]}),
    "theme-default": ("flowchart", {
        "theme": "default", "nodes": [{"id": "A", "label": "A"}],
    }),
    "theme-none": ("flowchart", {"theme": None, "nodes": [{"id": "A", "label": "A"}]}),
    "theme-empty": ("flowchart", {"theme": "", "nodes": [{"id": "A", "label": "A"}]}),
    "empty-spec": ("flowchart", {}),
    "no-nodes-at-all": ("flowchart", {"nodes": []}),
    "everything-at-once": ("flowchart", {
        "title": "Everything",
        "theme": "dark",
        "direction": "LR",
        "subgraphs": [{"id": "g1", "label": "Phase 1", "nodes": ["A", "B"]}],
        "nodes": [
            {"id": "A", "label": "Start (now)", "shape": "round"},
            {"id": "B", "label": "Check", "shape": "diamond"},
            {"id": "C", "label": "Store", "shape": "cylinder"},
            {"id": "Dd", "label": "Done", "shape": "rect"},
        ],
        "edges": [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "C", "label": "yes", "style": "thick"},
            {"from": "B", "to": "Dd", "label": "no", "style": "dotted", "length": 2},
            {"from": "C", "to": "Dd", "style": "invisible"},
        ],
    }),
    "the-guide-recipe-diagram": ("flowchart", {
        "direction": "TD",
        "title": "Approval flow",
        "nodes": [
            {"id": "A", "label": "Draft"},
            {"id": "B", "label": "In review"},
            {"id": "C", "label": "Shipped"},
        ],
        "edges": [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "C", "label": "approved"},
        ],
    }),
    # ------------------------------------------------------------------- sequence
    "sequence-header": ("sequence", {"participants": [{"id": "A"}], "messages": []}),
    "sequence-title": ("sequence", {
        "title": "Auth Flow", "participants": [{"id": "A"}], "messages": [],
    }),
    "sequence-theme-dark": ("sequence", {
        "theme": "dark", "participants": [{"id": "A"}], "messages": [],
    }),
    "sequence-theme-default": ("sequence", {
        "theme": "default", "participants": [{"id": "A"}], "messages": [],
    }),
    "sequence-participant-alias": ("sequence", {
        "participants": [{"id": "Client", "label": "Mobile App"}], "messages": [],
    }),
    "sequence-participant-no-label": ("sequence", {
        "participants": [{"id": "Client"}], "messages": [],
    }),
    "sequence-participant-label-equals-id": ("sequence", {
        "participants": [{"id": "Client", "label": "Client"}], "messages": [],
    }),
    "sequence-participant-null-label": ("sequence", {
        "participants": [{"id": "Client", "label": None}], "messages": [],
    }),
    "sequence-older-bare-strings": ("sequence", {
        "participants": ["User", "API"], "messages": [],
    }),
    "sequence-bare-string-with-a-space": ("sequence", {
        "participants": ["Mobile App"], "messages": [],
    }),
    "sequence-style-solid": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "req", "style": "solid"}],
    }),
    "sequence-style-dotted": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "resp", "style": "dotted"}],
    }),
    "sequence-style-absent": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "plain"}],
    }),
    "sequence-legacy-literal-arrow": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "req", "type": "->"}],
    }),
    "sequence-legacy-arrow-double": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "req", "type": "-->"}],
    }),
    "sequence-legacy-arrow-solid": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "req", "type": "->>"}],
    }),
    "sequence-legacy-arrow-dotted": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "req", "type": "-->>"}],
    }),
    "sequence-older-text-key": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "older text"}],
    }),
    "sequence-style-wins-over-type": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [
            {"from": "A", "to": "B", "label": "x", "style": "dotted", "type": "->"}
        ],
    }),
    "sequence-text-escaped": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "POST (login)", "style": "solid"}],
    }),
    "sequence-html-stripped": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "hi<script>", "style": "solid"}],
    }),
    "sequence-space-ids-declared-and-referenced": ("sequence", {
        "participants": ["Mobile App", "Auth Service"],
        "messages": [{"from": "Mobile App", "to": "Auth Service", "label": "check"}],
    }),
    "sequence-empty-spec": ("sequence", {}),
    "sequence-everything-at-once": ("sequence", {
        "title": "Authentication",
        "theme": "forest",
        "participants": [
            {"id": "Client", "label": "Mobile App"},
            {"id": "Gateway"},
            "Auth",
        ],
        "messages": [
            {"from": "Client", "to": "Gateway", "label": "1. POST /login"},
            {"from": "Gateway", "to": "Auth", "label": "2. validate", "style": "solid"},
            {"from": "Auth", "to": "Client", "label": "3. token", "style": "dotted"},
        ],
    }),
}
