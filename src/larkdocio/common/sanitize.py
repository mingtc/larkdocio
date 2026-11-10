import logging
import re

logger = logging.getLogger("larkdocio")

#: The name a string with nothing usable in it becomes. One constant, because two call sites
#: reason about it: :func:`larkdocio.read.download._write_markdown` prefers the document token
#: over it, and the ``--route`` guard refuses rather than materialise a directory nobody named.
UNTITLED = "untitled"

#: The **character** ceiling, kept exactly as it was. It is not the limit that exists on any
#: filesystem — the limit is in bytes, below — and it is kept anyway so that every name this
#: function has ever produced from ASCII input still comes out byte-identical. Removing it
#: would silently lengthen filenames for every existing consumer, which is a change nobody
#: asked for in a fix for a crash.
MAX_NAME_CHARS = 100

#: ``NAME_MAX`` on Linux/ext4 and the practical per-component ceiling elsewhere: **255 bytes,
#: not 255 characters.** This is the limit the character ceiling above cannot see.
NAME_MAX_BYTES = 255

#: What the callers of this function add to the name it returns, reserved out of
#: :data:`NAME_MAX_BYTES`. The longest decoration in this library is the download's timestamp
#: prefix plus the extension — ``[2026-09-08_1930]_`` + ``.md``, 21 bytes — and this is that
#: measurement rounded up, so a change to the stamp's shape does not silently re-open the
#: crash. It is **held to the real call sites by a guard** rather than trusted — that guard is
#: in the source repository, not in the wheel: ``tests/test_sanitize_byte_budget.py`` composes each
#: site's real filename and fails if any of them decorates a name by more than this, or
#: exceeds :data:`NAME_MAX_BYTES`.
DECORATION_RESERVE_BYTES = 32

#: The **byte** ceiling this function truncates to. Derived, never typed: it is what is left of
#: a filesystem component after the reserve above.
MAX_NAME_BYTES = NAME_MAX_BYTES - DECORATION_RESERVE_BYTES


def _reduce(name: str) -> str:
    """The character-level half of the rule — spaces closed up, OS-reserved characters
    removed, leading/trailing ``-``/``_`` stripped — and **the only statement of it**.

    Extracted so the two ceilings below read as the one thing they are: the reduction, then
    the truncation.
    """
    return re.sub(r'[\\/:*?"<>|]', "", name.replace(" ", "_")).strip("-_")


def truncate_to_bytes(name: str, limit: int) -> str:
    """``name`` cut to at most ``limit`` UTF-8 bytes, always on a codepoint boundary.

    The cut walks **back** over UTF-8 continuation bytes (``0b10xxxxxx``) rather than decoding
    with ``errors="ignore"``, so the discarded fragment is exactly one partial sequence and
    nothing else can be silently dropped.

    **Public as of LD-665**, and the rename is the whole change to it: the composition seam
    (:mod:`larkdocio.common.filename`) has to cut a stem to a budget only IT can compute — the
    room left after the caller's own fixed parts — so this rule cannot stay private to the one
    module that happened to need it first. Two statements of a UTF-8-safe cut is exactly the
    duplication that produces a partial sequence in one of them.
    """
    encoded = name.encode("utf-8")
    if len(encoded) <= limit:
        return name
    cut = limit
    while cut > 0 and (encoded[cut] & 0xC0) == 0x80:
        cut -= 1
    return encoded[:cut].decode("utf-8")


def sanitize_path_string(name: str) -> str:
    """
    Sanitize a string to be used as a valid file or directory name across platforms.
    - Allows international UTF-8 characters
    - Strips OS-reserved characters
    - Mandatory conversion of spaces to underscores
    - Truncates to :data:`MAX_NAME_CHARS` characters **and** to :data:`MAX_NAME_BYTES` bytes,
      whichever bites first, always on a codepoint boundary
    - **Discloses** the :data:`UNTITLED` substitution when stripping leaves nothing

    Both ceilings are real and neither is redundant. The character one is the older of the two
    and is kept so an ASCII name is byte-identical to what this function always returned; the
    byte one is the limit the operating system actually enforces, and it is the one this
    function was missing. A CJK codepoint is 3 bytes in UTF-8, so 100 characters was up to 300
    bytes against a 255-byte ``NAME_MAX``: measured on this tree, a title of 78 hanzi wrote and
    79 raised ``OSError: [Errno 36] File name too long`` — **after** the network fetch had
    already succeeded, so the caller paid for a download they never received.

    """
    if not name:
        return UNTITLED

    # Spaces to underscores, the OS-reserved characters removed, leading/trailing - and _
    # stripped. One statement of that, in `_reduce`.
    safe_name = _reduce(name)

    # Truncate to BOTH ceilings. The character slice runs first and is unchanged; the byte
    # truncation is what LD-659 added.
    #
    # The comment that used to stand here read: "Slicing a python string handles multi-byte
    # utf-8 gracefully." That is TRUE and it is the half that caused the defect — slicing does
    # avoid splitting a codepoint, which is presumably what was checked, and it says nothing
    # whatever about the byte budget, which is the limit the filesystem enforces. A comment
    # that records the reassuring half of a check and not the load-bearing half is how this
    # survived to a crash on a real Chinese document title, so it is replaced rather than
    # extended.
    safe_name = safe_name[:MAX_NAME_CHARS]
    safe_name = truncate_to_bytes(safe_name, MAX_NAME_BYTES)

    # Fallback if stripping made it empty — and it SAYS SO. Silence here is how `--route '***'`
    # became `<out>/untitled/`: a directory the caller never named, created without a word. The
    # substitution itself is defensible (something has to be written); doing it silently is not.
    if not safe_name:
        logger.warning(
            "%r has no characters usable in a filename — the OS-reserved characters "
            "\\ / : * ? \" < > | are removed and leading/trailing - and _ are stripped, which "
            "leaves nothing — so %r is being used instead.",
            name, UNTITLED,
        )
        return UNTITLED

    return safe_name


def sanitizes_to_nothing(name: str) -> bool:
    """Would :func:`sanitize_path_string` have to SUBSTITUTE :data:`UNTITLED` for ``name``?

    Answered by construction rather than by comparing the sanitized result against
    :data:`UNTITLED` — which would be wrong for the caller who literally asked for ``untitled``
    and is entitled to get it.

    Exists so a caller can **refuse** where disclosing is not enough, and the split is
    deliberate: a name this library DERIVED (a document title) is substituted and disclosed,
    because something has to be written and the caller has nothing to correct; a name the CALLER
    supplied (a ``--route`` segment) is refused, because they can fix their input and this
    library's habit is to refuse rather than guess.
    """
    return not name or not _reduce(name)


def truncates(name: str) -> bool:
    """Did :func:`sanitize_path_string` have to CUT ``name``, as opposed to merely reducing it?

    The distinction is the whole of LD-665. A reduction (spaces closed up, reserved characters
    removed) is **information-preserving in the sense that matters**: two different titles stay
    two different names. A truncation is not — it maps every title sharing a prefix onto one
    name, which is how two documents came to share one file. So the composition seam asks this
    question, and only when the answer is ``True`` does it earn the right to put something of
    its own into the caller's name.

    Answered by comparing against the **reduction** rather than against the input, for the same
    reason :func:`sanitizes_to_nothing` is answered by construction: a title full of spaces is
    changed by the sanitizer without being cut, and treating that as a truncation would rename
    files nobody's collision could ever have touched. The ``UNTITLED`` substitution is
    likewise **not** a truncation — it is the other function's question, and a call site that
    substitutes has already left this one's path.
    """
    reduced = _reduce(name) if name else ""
    if not reduced:
        return False
    return sanitize_path_string(name) != reduced
