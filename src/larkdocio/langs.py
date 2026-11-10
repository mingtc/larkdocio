"""larkdocio.langs — the ONE docx code-block language table, both directions.

A Lark docx **code** block (type 14) carries its language as an integer enum in
``code.style.language``. Two surfaces need that mapping and they must never disagree:

* the **reader** turns the enum into the Markdown fence's language token
  (``blocks/text.py`` → ``CodeNode.lang``), and
* the **writer** turns a consumer's Markdown token back into the enum when it *creates* a
  code block (``write/model/requests.py`` validates the token,
  ``write/encode.py`` emits the enum).

Before LD-134 only the read direction existed, inside ``blocks/text.py``. Duplicating the
~65 rows on the write side would have been a drift bomb (a language added to one map and
not the other silently mis-encodes), and having the pure-data write model import the
**block registry** to reach the table would have inverted the layering the model is
deliberately dumb to protect. So the table lives here — a leaf module with **no larkdocio
imports at all** — and both directions are derived from the one literal:
:data:`DOCX_CODE_LANG_TO_MD` (read) and :data:`MD_LANG_TO_DOCX_CODE` (write).
``blocks.text`` re-exports the read direction, so its former import path still works.

Enum ``1`` is Lark's *PlainText* and maps to the **empty** MD token (a fence with no
language). It is therefore excluded from the reverse map and represented instead by
:data:`PLAIN_TEXT_LANGUAGE` — "no language" is a value, not a name.
"""

#: Lark's *PlainText* language enum — a fence with no language token.
PLAIN_TEXT_LANGUAGE = 1

#: docx ``code.style.language`` enum → the Markdown fence's language token. The reader's
#: map since the first release; ``1`` (PlainText) and any unmapped enum emit a bare fence.
DOCX_CODE_LANG_TO_MD = {
    1: "",            # PlainText
    2: "abap",
    3: "ada",
    4: "apache",
    5: "apex",
    6: "assembly",
    7: "bash",
    8: "csharp",
    9: "cpp",
    10: "c",
    11: "cobol",
    12: "css",
    13: "coffeescript",
    14: "d",
    15: "dart",
    16: "delphi",
    17: "django",
    18: "dockerfile",
    19: "erlang",
    20: "fortran",
    21: "foxpro",
    22: "go",
    23: "groovy",
    24: "html",
    25: "htmlbars",
    26: "http",
    27: "haskell",
    28: "json",
    29: "java",
    30: "javascript",
    31: "julia",
    32: "kotlin",
    33: "latex",
    34: "lisp",
    35: "logo",
    36: "lua",
    37: "matlab",
    38: "makefile",
    39: "markdown",
    40: "nginx",
    41: "objectivec",
    42: "openedge-abl",
    43: "php",
    44: "perl",
    45: "postscript",
    46: "powershell",
    47: "prolog",
    48: "protobuf",
    49: "python",
    50: "r",
    51: "rpg",
    52: "ruby",
    53: "rust",
    54: "sas",
    55: "scss",
    56: "sql",
    57: "scala",
    58: "scheme",
    59: "scratch",
    60: "shell",
    61: "swift",
    62: "thrift",
    63: "typescript",
    64: "vbscript",
    65: "vbnet",
    67: "yaml",
}

#: The write direction — a Markdown fence token → the docx enum. **Derived** from the read
#: map (never hand-maintained), so a language can only ever be added in one place. The
#: empty PlainText token is excluded: "no language" is expressed as ``None`` on the request
#: and encoded as :data:`PLAIN_TEXT_LANGUAGE`.
MD_LANG_TO_DOCX_CODE = {md: docx for docx, md in DOCX_CODE_LANG_TO_MD.items() if md}


def supported_code_languages():
    """The Markdown language tokens a created code block may carry, sorted.

    The set a consumer can check *before* building a request — the token is validated at
    construction (an unknown one is refused, never silently downgraded to plain text).
    """
    return sorted(MD_LANG_TO_DOCX_CODE)
