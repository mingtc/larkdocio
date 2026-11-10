"""The shipped rule document, carried as packaged text.

It lives here — inside the package, as a module constant — so that it reaches an installed
wheel with the code it describes and cannot be separated from it: no packaging list to keep
in step, nothing to forget to copy, and the same bytes from a source tree and from a
vendored wheel. :func:`larkdocio.mermaid.rules` is the accessor a caller reads it through.

The drift guard parses this text and holds it equal, in both directions, to the constants in
:mod:`larkdocio.mermaid.ruleset` and to what the compilers really emit.
"""

MERMAID_RULES = """# Lark-safe Mermaid — the dialect this library compiles to

Lark's document renderer draws Mermaid diagrams through an add-on block, and it accepts a
narrower dialect than Mermaid itself does. Worse, it validates nothing on the way in: a
diagram whose source it cannot draw is stored exactly as sent and then simply fails to
appear. Nothing downstream will tell you. So the constraints below are not style advice —
they are the difference between a diagram and a blank space in a document.

The two compilers in this package (`flowchart` and `sequence`) already obey every rule here.
Read this document when you are writing Mermaid source **by hand**, or to understand why a
compiled diagram looks the way it does.

**About the provenance of these rules, because it bounds what they claim.** They were ported
from an older standalone generator whose own documentation had gone stale — it stated
constraints nothing in it checked, and one that its own compiler broke. That documentation
was therefore treated as a set of claims to check rather than as evidence: every rule below
is now either enforced by the compilers and re-validated by a test that shows them obeying
it, or explicitly marked advisory. Where the older document and the older behavior
disagreed, the disagreement was resolved deliberately and the result is what is written
here.

## The rules

Each rule is **enforced** — the compilers refuse the input or rewrite it, so breaking the
rule is not expressible in their output — or **advisory** — they warn and then honor your
choice, because the rule is a layout judgment rather than a correctness one. The third
column names the constants that carry the rule in code, so a rule cannot drift from the
behavior that implements it.

**Where an enforced rule refuses and where it rewrites.** Anything **structural** — a
direction, a shape, an edge style or length, a message arrow, an identifier, a reference to a
node or participant nothing declares — is **refused**: it raises, naming the construct and its
value, and no source is produced. Substituting a default for it would answer your spec with a
diagram that says something else, and nothing downstream would tell you. The rewrites are
confined to **label text**, where the meaning survives the change: markup is stripped, and a
label carrying syntax is quoted. A key you leave out is not off-dialect — the documented
default applies to an **absent** key, never to a wrong value.

**One class of label text is refused rather than rewritten**, and it is refused for the same
reason the structural rules are: a control character — a line break above all — is not a
character the renderer draws badly, it is a character that **ends the statement your label sits
in**, so the text after it is read as diagram syntax. That is a structural change wearing label
clothing, and there is no rewrite that preserves the meaning (see *No control characters in
label text*).

| Rule | Posture | Constants |
|------|---------|-----------|
| Supported diagram declarations | enforced | `SUPPORTED_DIAGRAM_TYPES`, `SANCTIONED_DECLARATIONS`, `UNSTABLE_DIAGRAM_TYPES`, `DIRECTIONS`, `DIRECTION_SYNONYMS`, `DEFAULT_DIRECTION` |
| No HTML in labels | enforced | `HTML_TAG_RE` |
| No control characters in label text | enforced | `LABEL_CONTROL_CHARS`, `LABEL_LINE_BREAKS` |
| Sanctioned node shapes | enforced | `SHAPE_ALIASES`, `SHAPE_TEMPLATES`, `DEFAULT_SHAPE` |
| Quoting labels that carry syntax | enforced | `LABEL_BAD_CHARS` |
| Edge styles and lengths | enforced | `EDGE_STYLES`, `DEFAULT_EDGE_STYLE`, `EDGE_LENGTH_RANGE` |
| Explicit participants | enforced | `EXPLICIT_PARTICIPANTS_REQUIRED` |
| Sanctioned message arrows | enforced | `MESSAGE_ARROWS`, `DEFAULT_MESSAGE_STYLE`, `LEGACY_ARROWS` |
| The theme whitelist | enforced | `THEMES`, `DEFAULT_THEME` |
| Comments | enforced | `COMMENT_PREFIX` |
| No blank line inside the block | enforced | `BLANK_LINE_ALLOWED` |
| One init-line dialect | enforced | `INIT_QUOTE` |
| Prefer the vertical direction | advisory | `VERTICAL_PREFERRED_ABOVE` |
| The complexity ceiling | advisory | `COMPLEXITY_LIMIT` |

### Supported diagram declarations

A diagram must open with one of the declarations below, spelled exactly — the keyword is
case-sensitive. Two of them have compilers here; the rest are listed because hand-written
source may use them and the renderer will draw them.

- Declarations: `graph TD`, `graph LR`, `flowchart TD`, `flowchart LR`, `sequenceDiagram`, `classDiagram`, `stateDiagram`, `mindmap`, `gantt`
- Diagram kinds: `graph`, `flowchart`, `sequenceDiagram`, `classDiagram`, `stateDiagram`, `mindmap`, `gantt`
- Avoid: `pie`, `gitGraph`, `journey`, `quadrantChart`
- Directions: `TD`, `LR`
- Synonyms: `TB` → `TD`
- Fallback direction: `TD`

The four kinds under *Avoid* are treated as experimental and draw unreliably; convert one to
a flowchart instead. A direction that is neither sanctioned nor a listed synonym is **refused**,
because a declaration the renderer does not recognize draws nothing at all — and drawing the
diagram along the other axis instead would answer a typo with a different diagram. The fallback
direction is what a spec naming **no** direction gets.

### No HTML in labels

Raw markup inside a label stops the diagram drawing. Tags are removed from every label
before anything else happens to it — what is left of the text is kept, including the
whitespace the tag was standing next to.

- Example: `<b>Start</b> here` → `"Start here"`

Line breaks are the common reason to reach for markup. There is no safe substitute in this
dialect: shorten the label, or split the node in two. A label that carries the line break
itself, rather than markup for one, is **refused** — the next section is that rule.

### No control characters in label text

A line break inside a label does not draw a two-line label: the source these compilers write
is **line-oriented** — one node, one edge, one message, one comment per line — so the break
ends that statement and everything after it is parsed as diagram syntax. A node labelled
`Start` + a newline + `flowchart LR` used to emit a valid diagram with a **second declaration
in it** and no warning anywhere. So every string that reaches the source — node, subgraph,
edge and participant labels, message text, and the diagram `title` that becomes a `%%` comment
— is **refused** when it carries a control character, naming the codepoint and the construct.

- Refused: the C0 controls (`U+0000`–`U+001F`, which includes tab, newline and carriage
  return), `DEL` (`U+007F`), `NEL` (`U+0085`), and the Unicode line and paragraph separators
  (`U+2028`, `U+2029`)

Nothing is substituted. `<br/>` is not the escape hatch it looks like: this dialect has no safe
line-break substitute (the section above), and a `<br/>` you write yourself is removed by the
no-HTML rule — so inserting one for you would mean the same request, spelled two ways, came
out two different ways. Shorten the text, or split the construct in two.

### Sanctioned node shapes

Four shapes, each with one spelling. A `shape` outside the list below is **refused** rather
than drawn as something else — a decision drawn as a rectangle no longer reads as a decision.
In the examples below, `A` stands for the node's identifier and `<label>` for its text.

- Shapes: `rect` → `A[<label>]`, `round` → `A((<label>))`, `diamond` → `A{<label>}`, `cylinder` → `A[(<label>)]`
- Aliases: `rounded`, `decision`, `condition`, `database`
- Default shape: `rect`

A node that names no shape at all gets the default. A node whose identifier is missing, or is
nothing but whitespace, is refused: the identifier is what every edge and every group naming
that node is written with, so there is nothing for them to refer to.

`round` is Mermaid's circle form. The name is the one this dialect has always used and it is
kept so existing input keeps working; if you want a rounded rectangle, know that this is not
it. Use `diamond` for a decision, and `cylinder` where a step is a datastore.

### Quoting labels that carry syntax

A label containing any of the characters below — or a space — is wrapped in double quotes,
because unwrapped punctuation is read as diagram syntax and the parse fails. A double quote
inside a label is downgraded to a single quote first, so the wrapping cannot be terminated
early by the label's own text.

- Bad characters: `(`, `)`, `[`, `]`, `{`, `}`, `,`, `"`, `'`

A label with none of them is emitted bare, which keeps simple diagrams readable as source.
Note that the vertical bar is deliberately not in the set: it is the delimiter an edge label
sits inside, and it is not a hazard within the label text itself.

### Edge styles and lengths

- Styles: `solid`, `dotted`, `thick`, `invisible`
- Default style: `solid`
- Length: `1` to `5`

`dotted` reads well for an error or an alternative path, `thick` for the path you want the
reader's eye to follow first. `invisible` draws nothing and can carry no label — it exists only
to make the layout engine place two nodes in sequence — so a label on an invisible edge is
**refused**: the text would simply never appear.

A length above one stretches the arrow, pushing its target further down the layout. Both
levers are for a diagram that is already drawn and still crossing itself; grouping related
nodes together is the first thing to try, not the last. A style outside the list, and a length
outside the range or that is not a whole number, are **refused** rather than substituted:
clamping a length silently chooses a layout you did not ask for, and drawing an unknown style
solid loses the distinction you were drawing. An edge naming a node the spec does not define is
refused too — the renderer draws nothing at all for such a diagram.

### Explicit participants

Every participant in a sequence diagram must be declared before any message names it.

- Participants: `required`

A message naming an undeclared participant is **refused** rather than emitted, because the
renderer would otherwise invent a silent extra column for it and the diagram would no longer
say what you meant — and dropping the message instead would remove the exchange you were
recording. A participant with no usable identifier is refused for the same reason a node is.
Declaring participants in the order you want them to appear is also the only control you have
over their left-to-right placement.

### Sanctioned message arrows

- Arrows: `dotted` → `-->>`, `solid` → `->>`
- Also accepted: `->>`, `-->>`, `->`, `-->`
- Default style: `solid`

Two arrows draw reliably: the solid one for a request, the dotted one for a response. The
second list is the set of literal arrows accepted from callers who name the arrow directly
instead of naming the style; anything outside it — or a `style` outside the two above — is
**refused**, because drawing it solid would turn a response into a request. A message that
names neither gets the default style.

### The theme whitelist

The renderer draws exactly 5 themes. A theme outside the list is refused rather than passed
through — an unknown theme is stored verbatim, ignored at draw time, and produces a diagram
in the wrong colors with no error anywhere.

- Themes: `default`, `dark`, `neutral`, `forest`, `base`
- Default: `default`

The default theme is never written into the configuration line; leaving it out is what
selects it.

### Comments

- Prefix: `%%`

That is the only comment marker the renderer understands. A number sign or a double slash is
read as diagram content and breaks the parse. A title, in particular, is emitted as a
comment: the renderer draws no title, so the text is there for whoever reads the source.

### No blank line inside the block

- Blank lines: `none`

A stray empty line inside a diagram block can end the parse early, so the compilers emit
none anywhere — not after the declaration, not around a group, not before the connections.
This is the one rule where the older generator broke its own document: it emitted spacers at
several positions. The rule was kept and the behavior corrected, because a diagram with no
blank lines draws under either reading of the renderer's tolerance, while one with them draws
only under the more generous reading.

### One init-line dialect

A leading configuration line sets the theme and the edge curve. There is one spelling of it,
written with single quotes.

- Quote: `'`
- Example: `%%{init: {'theme': 'dark'}}%%`

The older generator had two spellings — one compiler wrote double quotes and a stray space,
the other single quotes — so half its output was in a form its own document never showed.
Both compilers here render the line through the same emitter, which is what makes a second
dialect impossible rather than merely discouraged.

### Prefer the vertical direction

- Preferred above: `5`

The diagram view scales to fit the page width, and a horizontal diagram with many nodes is
scaled down until its text is unreadable. Past this many nodes the vertical direction is
what you want. This rule is advisory: the compilers warn and then draw the diagram the way
you asked for it, because a wide diagram of six short labels can be perfectly legible and
only you can see it.

### The complexity ceiling

- Ceiling: `30`

Nodes plus connections. Past that number a diagram is usually better as two diagrams — the
renderer will draw it, but a reader has to work to follow it. This rule is advisory: the
compilers warn and compile anyway, since where to cut a diagram is a judgment about meaning,
not about syntax.
"""
