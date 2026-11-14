"""larkdocio.base.schema_ops_app_table — the **app & table** schema-op family.

One family module, registered into :data:`larkdocio.base.schema_ops.FAMILY_MODULES`. It knows
nothing about the other families and they know nothing about it — which is the point: the
field family and the view family are each one new file and one new line, not an edit to a
tuple three stories share.

**Six non-destructive structural ops.** Create a Base, rename it, copy it, create a table, batch
create tables, rename a table. Every destructive verb — table delete, table ``batch_delete``,
field delete and the drive-file delete that removes a Base — is **deliberately absent**: a later
rung owns all four behind the cross-table loss preview and the explicit-consent fence, and a
descriptor here would be this registry claiming a capability the package does not ship.

**Copy is the one asynchronous op in the entire Base surface.** ``POST …/apps/{a}/copy``
returns a new ``app_token`` and an **empty** ``default_table_id``, and an immediate
``GET /apps/{new}`` answers ``1254036 "Bitable is copying, please try again later."`` — then
reads cleanly ~1.2 s later. ``settles: True`` is how that fact reaches the engine, which spends
a **bounded, response-driven** settle rather than a sleep.

**Nothing here is verified by ``code:0``.** R12: the Base API silently ignores what it does not
recognise, so an accepted call is not an applied one. Each descriptor states its own read-back,
and the engine performs it.

**A TABLE CREATE MAY CARRY ITS WHOLE COLUMN KIT, AND THE KIT GOES *THROUGH* THE FIELD GATE
RATHER THAN AROUND IT.** ``POST …/tables`` takes an inline ``fields`` array, so a table and its
columns land in **one** call, on a route that never touches the ``/fields`` write family.
**``batch_create`` does NOT** — its ``tables`` are the same ``ReqTable`` model, so a kit is
*transportable* there, and the server **accepts it at ``code:0`` and creates every table without
it** (measured on the shipped path and again on a hand-written raw body: probe ``ld336-02``). So
the batch verb **refuses** a kit rather than shipping a silent no-op
(:data:`BATCH_CREATE_IGNORES_A_COLUMN_KIT`) — the converse of R12's rule that a parameter this
library sends is one a test proved changed something. The standing ruling here used to be *"not sent:
reaching field authoring through a table create would be a side door around the allow-list."*
That **reason is preserved** and only its **conclusion** is superseded: :func:`check_column_kit`
runs :func:`~larkdocio.base.field_vocabulary.check_authorable` and
:func:`~larkdocio.base.field_authoring.build_property` — **the same two seams ``create_field``
calls, never a second parallel copy of either** — over **every** entry, so a definition
``create_field`` would refuse is refused here too, **locally, at plan time, with zero calls**,
and an unauthorable entry **anywhere** in the array refuses the **whole** op rather than
creating a table with one column silently missing. ``default_view_name`` is the other real key
that route takes and is **still not sent** — the reason is the measured one: Lark's
``create_table`` **rejects** a body carrying it (``1254001 WrongRequestBody``, no table created —
measured twice, raw core + pinned SDK, probe ``ld344-01``). The view name *is* readable
(``list_views``), so it was never *unprovable*; it is simply refused at create time.

**WHAT CHANGED IS ONLY THE CONCLUSION'S TAIL: the goal is now DELIVERED, by a COMPOSITE.** The key stays off the body; a ``create_table`` entry carrying a
``default_view_name`` makes the create and then **renames the single view the table is born
with**, addressed by the ``default_view_id`` the create's own reply carries — measured equal to
that view's id, on exactly the kitted shape this family sends (probe ``ld356-01``, which also
measured ``total: 1`` on both the plain and the kitted create). No locale-dependent name is ever
compared. **The composite is NOT ATOMIC** and this family says so rather than implying otherwise:
a rename that fails after the create landed surfaces
:class:`~larkdocio.base.errors.TableCreatedViewNotNamed` — the ids plus Lark's unedited denial —
and **nothing is rolled back and nothing is retried**. The
read-back is this family's own, as ever: the view name is confirmed from the table's **view
list**, never from ``code:0``.

**TWO THINGS ABOUT THAT ROUTE ARE MEASURED FACTS NOBODY COULD HAVE READ OFF THE SDK MODEL**, and
both are authored here as data (probe ``ld336-02``). **(1) The kit's FIRST entry BECOMES the
PRIMARY column** — a kitted create does not get Lark's locale-named default *plus* the kit, it
gets the kit, entry 0 first and primary (:data:`KIT_FIRST_ENTRY_IS_THE_PRIMARY`). **(2) This
route's kind vocabulary is NARROWER than ``POST …/fields``'s** — ``Rating`` and ``Checkbox``
answer ``1254012 "Unsupported field type."`` and create **nothing at all**, so they are refused
locally with the route that does author them named in the refusal
(:data:`NOT_AUTHORABLE_AT_CREATION`). Both statements say what was **measured** rather than what
the enum implies, which is the standing bar on this surface.
"""
from typing import Any, Dict, Mapping, Sequence, Tuple

from lark_oapi.api.bitable.v1 import (
    AppTableCreateHeader,
    BatchCreateAppTableRequest,
    CopyAppRequest,
    CreateAppRequest,
    CreateAppTableRequest,
    PatchAppTableRequest,
    ReqTable,
    UpdateAppRequest,
)

from larkdocio.base.field_authoring import (
    FieldAuthoringRefusal,
    PLAIN_TEXT_FIELD,
    build_property,
)
from larkdocio.base.field_vocabulary import UnauthorableFieldError, check_authorable
from larkdocio.base.schema_ops import BaseSchemaOpDescriptor, SchemaOpFamily
from larkdocio.common.citations import dev_repo

_CAPTURES = "tests/captures/base-study/captures"

#: The family's name, used by the aggregator and quoted in the source repository's ``BASE.md``
#: schema-ops table.
FAMILY_NAME = "app-and-table"


SCHEMA_OP_FAMILY = SchemaOpFamily(
    name=FAMILY_NAME,
    module=__name__,
    ops=(
        BaseSchemaOpDescriptor(
            name="create_app",
            endpoint="/open-apis/bitable/v1/apps",
            http_method="POST",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back="GET …/apps/{new} answers code:0 and echoes the name that was asked for",
            request_cls=CreateAppRequest,
            evidence=dev_repo(f"{_CAPTURES}/05-01-create-app.json"),
        ),
        BaseSchemaOpDescriptor(
            name="rename_app",
            endpoint="/open-apis/bitable/v1/apps/:app_token",
            http_method="PUT",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back="GET …/apps/{a} re-reads with the new name",
            request_cls=UpdateAppRequest,
            evidence=dev_repo(f"{_CAPTURES}/p1-q4-03-parity-sweep.json"),
        ),
        BaseSchemaOpDescriptor(
            name="copy_app",
            endpoint="/open-apis/bitable/v1/apps/:app_token/copy",
            http_method="POST",
            mutates=True,
            family=FAMILY_NAME,
            # THE ONE ASYNCHRONOUS OP. Everything else on this surface answers about a state
            # that already exists by the time it answers.
            settles=True,
            read_back=("GET …/apps/{new}/tables lists the copied tables — reachable only "
                       "AFTER the copy settles, never from the copy's own echo"),
            request_cls=CopyAppRequest,
            evidence=dev_repo(f"{_CAPTURES}/p1-q4-02-copy.json"),
        ),
        BaseSchemaOpDescriptor(
            name="create_table",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables",
            http_method="POST",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back="GET …/apps/{a}/tables lists the returned table_id",
            request_cls=CreateAppTableRequest,
            evidence=dev_repo(f"{_CAPTURES}/05-03-create-table.json"),
        ),
        BaseSchemaOpDescriptor(
            name="batch_create_tables",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/batch_create",
            http_method="POST",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=("GET …/apps/{a}/tables lists EVERY returned table_id in a SINGLE "
                       "read-back — one call, one verification"),
            request_cls=BatchCreateAppTableRequest,
            evidence=dev_repo(f"{_CAPTURES}/p1-q4-03-parity-sweep.json"),
        ),
        BaseSchemaOpDescriptor(
            name="rename_table",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id",
            http_method="PATCH",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back="GET …/apps/{a}/tables shows the table under its new name",
            request_cls=PatchAppTableRequest,
            evidence=dev_repo(f"{_CAPTURES}/p1-q4-03-parity-sweep.json"),
        ),
    ),
)


# --------------------------------------------------------------------------- #
# THE COLUMN KIT — a table create's inline `fields`, through the FIELD gate     #
# --------------------------------------------------------------------------- #

#: The keys **one** column definition in a table create's ``fields`` array may carry: exactly
#: the four :func:`larkdocio.base.schema_ops_fields.create_field` takes, spelled the same way,
#: so a caller who can author a column one way can author it the other without a second
#: vocabulary to learn. Anything else is **refused rather than forwarded**: this API silently
#: ignores body keys it does not recognise, so a key travelling on unread would come back
#: ``code:0`` having authored a column without it.
COLUMN_KIT_KEYS: Tuple[str, ...] = ("field_name", "field_type", "ui_type", "properties")

#: **The kit's FIRST entry BECOMES the table's PRIMARY column — measured, not assumed.**
#: A ``create_table`` with no kit arrives with a primary column Lark names itself, in the
#: tenant's locale (``多行文本`` on a Chinese-locale tenant). A create carrying a kit does **not**
#: get that column plus the kit: probe ``ld336-02`` sent seven single-entry kits and every one
#: read back as ``is_primary: true`` with **no** locale-named column anywhere in the listing, and
#: a two-entry kit made the first entry primary and the second an ordinary column. So the first
#: entry of a kit is the one thing a caller cannot append to later, and this is the sentence the
#: consumer guide states rather than the older guess that a kit adds columns *beside* the
#: locale-named default.
KIT_FIRST_ENTRY_IS_THE_PRIMARY = (
    "The FIRST entry of a table create's `fields` array becomes that table's PRIMARY column. "
    "A create with no `fields` gets a primary column Lark names itself in the tenant's locale; "
    "a create WITH `fields` does not get that column at all — the kit's first entry is it, "
    "under the name you gave. Measured across seven single-entry kits and one two-entry kit "
    "(every first entry read back `is_primary: true`, with no locale-named column present), so "
    "order the array deliberately: entry 0 is the column your rows are keyed by."
)

#: **Column kinds the INLINE array will not author, though ``create_field`` will — MEASURED.**
#: This route's vocabulary is **narrower** than ``POST …/fields``'s, which is a fact no amount of
#: reading the SDK model could have produced: ``Rating`` and ``Checkbox`` each answer
#: ``1254012 "Unsupported field type."`` and **nothing lands** — not the column, not the table —
#: while ``Text``, ``Number``, ``DateTime``, ``SingleSelect``, ``Barcode``, ``Currency`` and
#: ``Progress`` all land with their ``property`` intact (probe ``ld336-02``).
#:
#: **This list is what was MEASURED, not a claim about the whole enum.** Eight kinds were probed;
#: a kind not named here is *not* thereby promised — it is simply unmeasured, and Lark's own
#: ``1254012`` is what a caller meets, typed and loud, with nothing partially created. The two
#: members are refused **locally** because an opaque ``1254012`` on a whole-table create is a
#: worse answer than a sentence naming the column and the route that does author it.
NOT_AUTHORABLE_AT_CREATION: Tuple[str, ...] = ("Checkbox", "Rating")

#: What to do instead, per refused kind. Both are ordinary columns on the **field-authoring**
#: route: create the table first, then add them with ``create_field``.
#:
#: **The way forward carries its own COST, and the cost is stated in the same breath (LD-473).**
#: Telling a caller to use ``create_field`` without saying that it *appends* sends them to a
#: workaround whose price they discover only by reading the column order back: this array is the
#: **only** route that sets column order, so a kind it refuses can never sit anywhere but after
#: every kind it accepts. Measured with an anti-alphabetical control (probe ``ld473-01``): three
#: columns appended one call each read back at the END, in **call** order — so append order is
#: display order, which is what makes the workaround usable at all.
NOT_AUTHORABLE_AT_CREATION_GUIDANCE = (
    "This column kind is authorable — just not AT CREATION. Lark's table-create route answers "
    "`1254012 Unsupported field type.` for it and creates NOTHING (no table, no columns), which "
    "is why it is refused here instead: create the table with the kinds this route takes, then "
    "add this column with `create_field`, which does author it. Measured in probe `ld336-02`. "
    "AND THE COST, because this array is the ONLY route that sets column order: `create_field` "
    "APPENDS, so the position you asked for here is FORFEITED PERMANENTLY — no create-time or "
    "update-time position parameter and no move/reorder route was found to place or move a "
    "column afterward. What you keep is that APPEND ORDER IS DISPLAY ORDER (measured, probe "
    "`ld473-01`), so author the orderable prefix here and add the refused kinds in the display "
    "order you want them in; they will sit after every column this route accepted."
)


def _where(index: int, field_name) -> str:
    """Which entry of the array a refusal is about — index **and** name.

    Both, because a kit is assembled in a loop: an index with no name is unreadable in a log,
    and a name with no index cannot be found in an array that repeats one.
    """
    return f"the column kit's entry at index {index} ({field_name!r})"


def _one_column(index: int, entry) -> Dict[str, Any]:
    """One kit entry, gate-checked and normalised — or a refusal naming *which* entry.

    The gate is :func:`~larkdocio.base.field_vocabulary.check_authorable` for the
    ``(field_type, ui_type)`` identity and :func:`~larkdocio.base.field_authoring.build_property`
    for the ``property``, which are the **same two calls** ``create_field`` makes at
    :mod:`larkdocio.base.schema_ops_fields`. A vocabulary refusal is re-raised **as its own
    type** with the entry it came from prefixed, so ``except UnauthorableFieldError`` /
    ``except UncapturedFieldPairError`` / ``except UncapturedFieldPropertyError`` keep catching
    exactly what they caught before and **no new exception type is minted**.
    """
    if not isinstance(entry, Mapping):
        raise FieldAuthoringRefusal(
            f"the column kit's entry at index {index} is a {type(entry).__name__}, not a "
            f"mapping of {', '.join(COLUMN_KIT_KEYS)}. Nothing was sent.")
    unknown = [key for key in entry if key not in COLUMN_KIT_KEYS]
    if unknown:
        raise FieldAuthoringRefusal(
            f"{_where(index, entry.get('field_name'))} carries {unknown!r}, which this library "
            f"does not send on a table create. The keys one column definition may carry are: "
            f"{', '.join(COLUMN_KIT_KEYS)}. This API silently IGNORES body keys it does not "
            f"recognise, so an unread key would come back code:0 having authored a column "
            f"without it. Nothing was sent.")
    field_name = entry.get("field_name")
    if not isinstance(field_name, str) or not field_name:
        raise FieldAuthoringRefusal(
            f"the column kit's entry at index {index} has no usable 'field_name' "
            f"({field_name!r}): a column with no name is not a column. Nothing was sent.")
    if "field_type" not in entry:
        raise FieldAuthoringRefusal(
            f"{_where(index, field_name)} names no 'field_type'. A column's identity is the "
            f"PAIR of its storage type and its kind, and this library does not guess either "
            f"half. Nothing was sent.")
    field_type = entry.get("field_type")
    ui_type = entry.get("ui_type")
    properties = dict(entry.get("properties") or {})
    if ui_type in NOT_AUTHORABLE_AT_CREATION:
        raise FieldAuthoringRefusal(
            f"{_where(index, field_name)} asks for a {ui_type!r} column, which this route does "
            f"not author. {NOT_AUTHORABLE_AT_CREATION_GUIDANCE} The kinds measured landing here "
            f"are Text, Number, DateTime, SingleSelect, Barcode, Currency and Progress; the "
            f"ones measured refusing are: {', '.join(NOT_AUTHORABLE_AT_CREATION)}. Nothing was "
            f"sent.")
    try:
        check_authorable(field_type, ui_type)
        if ui_type is not None:
            build_property(ui_type, **properties)
    except (UnauthorableFieldError, FieldAuthoringRefusal) as exc:
        # Re-raised as its OWN type, only prefixed with which entry it came from: the two
        # refusal families and their subclasses are what a caller already catches, and a
        # wrapper type would break every `except` written against `create_field`.
        raise type(exc)(f"{_where(index, field_name)} was refused: {exc}") from exc
    # Exactly :data:`COLUMN_KIT_KEYS` and nothing else, so the normalised form is **valid input
    # to this function again** — which is what lets the plan carry it as a JSON-serialisable
    # argument and the client seam re-check it without a second, laxer shape to maintain. The
    # typed ``property`` is deliberately NOT stashed here; :func:`_column_header` builds it from
    # the same one builder at the moment the request is assembled.
    return {"field_name": field_name, "field_type": field_type, "ui_type": ui_type,
            "properties": properties}


#: **The locale-named default is what a nameless create BUYS — refused rather than sold.**
#: A ``create_table`` carrying neither ``primary_field_name=`` nor ``fields=[…]`` lands a primary
#: column **Lark** names, in the **tenant's** locale (``多行文本`` on the reporting tenant —
#: measured on a real field listing, not hypothesised). Every downstream keying decision then
#: runs through a name the caller never chose and cannot predict.
#: So the call is refused, locally, before a client exists. **The library does not invent a
#: default either** — inventing ``"Title"`` is the same class of decision the locale default is
#: (a name the caller did not pick), only in a language they happen to read.
NAMELESS_PRIMARY_IS_REFUSED = (
    "`create_table` will not create a table whose PRIMARY column this library did not name. "
    "Passed neither `primary_field_name=` nor `fields=[...]`, Lark names that column itself, in "
    "the TENANT'S locale — a Chinese-locale tenant gets `多行文本` — so the column your rows are "
    "keyed by would arrive under a name you did not choose and cannot predict. "
    "The one-line fix: `create_table(app_token, name, primary_field_name='Title')`, which gives "
    "you a Text primary column under the name you gave. "
    "The kit alternative, for a table that should be born with more than one column: "
    "`create_table(app_token, name, fields=[...])`, whose FIRST entry becomes the primary "
    "column. Nothing was sent."
)

#: **Both naming routes at once is refused — not reconciled, not last-one-wins.** The kit's
#: first entry **is** the primary column, so a ``primary_field_name`` beside a ``fields`` array
#: names the same column twice. Allowing it when the two strings happen to agree would be a rule
#: whose behaviour depends on string equality — a rule nobody can remember.
PRIMARY_FIELD_NAME_AND_KIT = (
    "`create_table` takes `primary_field_name=` OR `fields=[...]`, never both: the kit's FIRST "
    "entry IS the primary column, so a `primary_field_name` beside it names that one column "
    "twice and this library will not choose which of the two you meant. Drop one — keep "
    "`fields=` and name entry 0 the way the primary column should read, or keep "
    "`primary_field_name=` if one Text column is all the table should be born with. This is "
    "refused even when the two names AGREE: a rule whose behaviour depends on string equality "
    "is a rule nobody can remember. Nothing was sent."
)

#: **The batch verb cannot honour a name, so it asks for an ACKNOWLEDGEMENT instead.** Lark
#: ignores a per-table ``fields`` array on that route at ``code:0``
#: (:data:`BATCH_CREATE_IGNORES_A_COLUMN_KIT`, measured twice), so forwarding a
#: ``primary_field_name`` there would be shipping a no-op — exactly what R12 forbids. A hard
#: refusal with no opt-out was **rejected** too: it would delete a shipped capability with no
#: same-price substitute. So the silence is made **explicit** — the caller says out loud that
#: they accept Lark's locale-named default, or they use the verb that does honour a name.
BATCH_CREATE_LOCALE_DEFAULT_PRIMARY = (
    "`batch_create_tables` cannot name a primary column, so it will not create tables that "
    "silently take one. Every table it creates arrives with the primary column LARK names, in "
    "the tenant's locale — a Chinese-locale tenant gets `多行文本`. That is the server's "
    "behaviour and not something this library can send its way around: the batch route ACCEPTS "
    "a per-table `fields` array, answers code:0, and creates every table without it (measured "
    "twice), so a forwarded name would be a silent no-op. "
    "To take that deal, say so: "
    "`batch_create_tables(app_token, names, accept_locale_default_primary=True)`. "
    "To name the columns instead, use one "
    "`create_table(app_token, name, primary_field_name=...)` per table — that route DOES honour "
    "the name, and each is still one call. Nothing was sent."
)

#: What a ``primary_field_name=`` **is**: one plain-text column, its ``(field_type, ui_type)``
#: identity taken from the field family's one shape table rather than restated here. A primary
#: column of any other kind is ``fields=[…]``'s job, and changing one afterwards is
#: ``convert_field``'s.
PRIMARY_FIELD_TYPE, PRIMARY_FIELD_UI_TYPE = PLAIN_TEXT_FIELD


def check_primary_naming(fields, primary_field_name) -> Tuple[Dict[str, Any], ...]:
    """The two naming routes, resolved to **one** gated kit — or refused, before any call.

    ``primary_field_name=`` is **sugar over LD-336's fields-at-creation transport**: it is
    normalised into a one-entry ``Text`` kit and then handed to :func:`check_column_kit`, so it
    passes the **same** :func:`~larkdocio.base.field_vocabulary.check_authorable` /
    :func:`~larkdocio.base.field_authoring.build_property` seams every other column passes.
    There is no second path, no second shape table, and **no new endpoint reach** — in
    particular, rename-after-create (``update_field``) is emphatically **not** the mechanism:
    it needs a ``field_id`` that does not exist until the create is applied.

    Three refusals, all local, all with zero calls **structurally**:
    both routes at once (:data:`PRIMARY_FIELD_NAME_AND_KIT`), neither route
    (:data:`NAMELESS_PRIMARY_IS_REFUSED`), and whatever the shared gate itself refuses.
    """
    if primary_field_name is not None and fields:
        raise FieldAuthoringRefusal(PRIMARY_FIELD_NAME_AND_KIT)
    if primary_field_name is not None:
        fields = [{"field_name": primary_field_name,
                   "field_type": PRIMARY_FIELD_TYPE,
                   "ui_type": PRIMARY_FIELD_UI_TYPE}]
    kit = check_column_kit(fields)
    if not kit:
        raise FieldAuthoringRefusal(NAMELESS_PRIMARY_IS_REFUSED)
    return kit


def check_batch_primary_naming(accept_locale_default_primary, primary_field_name=None) -> None:
    """The batch verb's half of the naming doctrine: an **acknowledgement**, not a name.

    ``primary_field_name=`` is accepted as a keyword purely so a caller who reaches for it meets
    :data:`BATCH_CREATE_LOCALE_DEFAULT_PRIMARY` rather than a bare ``TypeError`` — the same
    reason the ``fields`` parameter is kept rather than removed.
    """
    if primary_field_name is not None or not accept_locale_default_primary:
        raise FieldAuthoringRefusal(BATCH_CREATE_LOCALE_DEFAULT_PRIMARY)


def check_column_kit(fields) -> Tuple[Dict[str, Any], ...]:
    """A table create's ``fields`` array, gate-checked **entry by entry**, before any call.

    Returns the normalised kit — empty for ``None`` / ``()`` / ``[]``, which all mean *"this
    create asks for no columns"* and reach the wire as **no ``fields`` key at all** rather than
    as ``null`` or ``[]``. Raises on the **first** offending entry, which refuses the **whole**
    op: a table created with one of its columns silently dropped is worse than a refusal,
    because the caller's next write is against a schema they think they authored.

    Every refusal here is **local** — no client is constructed and no request is built — so an
    unauthorable kit costs zero API calls **structurally**, not by being counted afterwards.
    """
    if not fields:
        return ()
    if isinstance(fields, Mapping) or isinstance(fields, str):
        raise FieldAuthoringRefusal(
            f"a column kit is a SEQUENCE of column definitions, in the order the columns "
            f"should be created; got {type(fields).__name__}. Nothing was sent.")
    return tuple(_one_column(index, entry) for index, entry in enumerate(fields))


#: **``batch_create`` ACCEPTS a per-table ``fields`` array AND SILENTLY IGNORES IT — MEASURED.**
#: The single create honours the array; the batch answers ``code:0``, returns its ``table_ids``,
#: and every table arrives with Lark's locale-named default primary and **none** of the kit. The
#: swallow was proved to be the SERVER's and not this library's: the identical body, hand-written
#: and sent through the raw HTTP core, behaves the same way (probe ``ld336-02``). So the kit is
#: **refused** on this verb rather than sent — R12's own rule, that a parameter this client sends
#: is a parameter a test proved changed something, and its converse.
BATCH_CREATE_IGNORES_A_COLUMN_KIT = (
    "`batch_create_tables` does not author columns. Lark's batch route ACCEPTS a per-table "
    "`fields` array, answers code:0, and creates every table WITHOUT it — each one arrives with "
    "the locale-named default primary column and none of the kit. That was measured on the "
    "shipped path and again on a hand-written body through the raw HTTP core, so it is the "
    "server's behaviour and not something this library can send its way around; forwarding the "
    "array anyway would be shipping a silent no-op, which is exactly what R12 forbids. Use one "
    "`create_table(app_token, name, fields=[...])` per table — that route DOES author the kit, "
    "and each is still a single call. Nothing was sent."
)


def check_batch_column_kits(names: Sequence[str], fields) -> Tuple[Tuple, ...]:
    """Refuse a column kit on the batch verb, locally, with the measurement that earned it.

    The batch's ``ReqTable`` is the **same model** the single create uses, so a kit is
    *transportable* here — and transportable is not processed. It is ignored at ``code:0``
    (:data:`BATCH_CREATE_IGNORES_A_COLUMN_KIT`), and the read-back would report every such
    create ``dropped``, which is a correct answer to a call that should never have been made.

    The parameter is **kept rather than removed** so that a caller who reaches for it meets this
    sentence instead of a ``TypeError`` that explains nothing.
    """
    names = list(names)
    if not fields:
        return tuple(() for _ in names)
    if any(kit for kit in fields):
        raise FieldAuthoringRefusal(BATCH_CREATE_IGNORES_A_COLUMN_KIT)
    return tuple(() for _ in names)


def column_kit_disclosure(kit: Sequence[Mapping]) -> str:
    """``with 3 columns: 'Title' (Text), …`` — what the dry run shows before the call.

    The plan entry already carries the kit as data; this is the one-line form a human approving
    a plan reads, so the columns a create will author are visible **before** it is made rather
    than discoverable afterwards from a field listing.
    """
    if not kit:
        return ""
    listed = ", ".join(
        f"{column['field_name']!r} ({column.get('ui_type') or column.get('field_type')})"
        for column in kit)
    noun = "column" if len(kit) == 1 else "columns"
    return f" with {len(kit)} {noun}: {listed}"


def _column_header(column: Mapping) -> AppTableCreateHeader:
    """One ``AppTableCreateHeader``, from the pinned SDK's builder and nothing else."""
    builder = AppTableCreateHeader.builder() \
        .field_name(column["field_name"]) \
        .type(column["field_type"])
    ui_type = column.get("ui_type")
    if ui_type is not None:
        builder = builder.ui_type(ui_type)
        # THE ONE property builder — `create_field`'s own. A second shape table here is exactly
        # the drift this reuse exists to make impossible (the `Rating` trap: `symbol` is taken
        # flat and nested under `rating` by that function alone).
        prop = build_property(ui_type, **dict(column.get("properties") or {}))
        if prop is not None:
            builder = builder.property(prop)
    return builder.build()


def req_table(name: str, fields=None) -> ReqTable:
    """The ``ReqTable`` one table create sends — name only, or name **plus a gated kit**.

    The single create and each element of ``batch_create``'s ``tables`` are the **same** model,
    so this one function builds both and there is no second place a kit could reach the wire
    ungated. ``fields`` is re-checked here even when the plan already checked it: this is a
    **public seam**, and a refusal a caller can read beats a round trip to an opaque code
    whichever door they came in through — the reason ``create_field`` already gives.
    """
    builder = ReqTable.builder().name(name)
    kit = check_column_kit(fields)
    if kit:
        builder = builder.fields([_column_header(column) for column in kit])
    return builder.build()


# --------------------------------------------------------------------------- #
# The engine seams — published for the two verbs whose call gained an argument  #
# --------------------------------------------------------------------------- #

def _kit_of(arguments: Mapping) -> Tuple:
    return tuple(arguments.get("fields") or ())


def _issue(watch, entry):
    """Make ONE table-create call. Registered in :data:`ISSUE_HANDLERS` for the two verbs that
    can carry a column kit, so the kit reaches the client **in its own family's file**.

    The keyword is passed **only when a kit was asked for**, which keeps a kit-less create
    byte-identical to the call this family has always made — including for any caller holding a
    client of their own shape.
    """
    arguments = dict(entry.fields or {})
    kit = _kit_of(arguments)
    if entry.op == "create_table":
        # The view name is passed ONLY when the plan carries one, for the same reason the kit is:
        # a create that did not ask for it stays byte-identical to the call this family has
        # always made — including for a caller holding a client of their own shape.
        extra = {}
        if arguments.get("default_view_name") is not None:
            extra["default_view_name"] = arguments["default_view_name"]
        if kit:
            return watch.create_table(arguments["app_token"], arguments["name"], fields=kit,
                                      **extra)
        return watch.create_table(arguments["app_token"], arguments["name"], **extra)
    # No kit branch for the batch: a kit never reaches a plan entry for this verb, because the
    # constructor refuses it (BATCH_CREATE_IGNORES_A_COLUMN_KIT). The acknowledgement is passed
    # because a plan entry for this verb can only EXIST if the caller already gave it at plan
    # time (check_batch_primary_naming) — the client seam asks the caller, not the engine.
    return watch.batch_create_tables(arguments["app_token"], arguments["names"],
                                     accept_locale_default_primary=True)


def _columns_landed(read_client, app_token, table_id, kit) -> dict:
    """What the created table's **own field list** says about the kit — never ``code:0``.

    R12 in its sharpest form on this rung: a create carrying ``fields`` answers ``code:0``
    whether or not the array was processed, so the only evidence a column landed is the
    column. Compared on **name, type, ui_type and property**, and only on the coordinates the
    caller actually named — the server fills in a ``ui_type`` of its own for a create that
    omitted one, and holding it against a claim nobody made would be a false negative.
    """
    seen = {getattr(field, "field_name", None): field
            for field in (read_client.list_fields(app_token, table_id) or ())}
    missing, mismatched = [], []
    for column in kit:
        field = seen.get(column["field_name"])
        if field is None:
            missing.append(column["field_name"])
            continue
        for asked, attribute in (("field_type", "type"), ("ui_type", "ui_type")):
            want = column.get(asked)
            if want is not None and getattr(field, attribute, None) != want:
                mismatched.append({"field_name": column["field_name"], "key": attribute,
                                   "expected": want, "seen": getattr(field, attribute, None)})
    return {
        "table_id": table_id,
        "asked": [column["field_name"] for column in kit],
        "seen": sorted(name for name in seen if name),
        "missing": missing,
        "mismatched": mismatched,
        "primary": [getattr(field, "field_name", None) for field in seen.values()
                    if getattr(field, "is_primary", False)],
    }


def _default_view_named(read_client, app_token, table_id, asked) -> dict:
    """Did the created table's default view really end up carrying the name asked for?

    R12 on the composite's second leg. The rename answers ``code:0`` whether or not it took —
    the sibling key ``property.group_info`` on that very route answers ``code:0`` and persists
    ``property: null`` — so the only evidence is the table's **own view list**. The comparison is
    against the **caller's** name and never against a locale default: what the tenant calls a
    fresh view is not a constant this library may know.
    """
    seen = [getattr(view, "view_name", None)
            for view in (read_client.list_views(app_token, table_id) or ())]
    return {"asked": asked, "seen": seen, "views": len(seen), "named": asked in seen}


def _table_index(read_client, app_token) -> dict:
    return {getattr(table, "table_id", None): getattr(table, "name", None)
            for table in (read_client.list_tables(app_token) or ())}


def _read_back(read_client, entry, reply, created_app_token):
    """``(confirmed, disclosure)`` for a table create — the listing, **plus the columns**.

    A kit-less create is verified exactly as it always was: one table listing, and the
    disclosure this family's descriptor describes. A **kitted** create answers a second
    question the listing cannot — did the columns land — so it costs one more read, which the
    plan already priced (``read_cost``) before anything was sent.
    """
    arguments = dict(entry.fields or {})
    app_token = arguments["app_token"]
    tables = _table_index(read_client, app_token)

    if entry.op == "create_table":
        listed = reply in tables
        disclosure = {"how": entry.read_back, "table_ids": [reply], "listed": listed}
        confirmed = listed
        kit = _kit_of(arguments)
        if kit:
            columns = _columns_landed(read_client, app_token, reply, kit)
            disclosure["columns"] = [columns]
            confirmed = confirmed and not columns["missing"] and not columns["mismatched"]
        asked_view_name = arguments.get("default_view_name")
        if asked_view_name is not None:
            named = _default_view_named(read_client, app_token, reply, asked_view_name)
            disclosure["default_view"] = named
            confirmed = confirmed and named["named"]
        return confirmed, disclosure

    created = list(reply or ())
    missing = [table_id for table_id in created if table_id not in tables]
    disclosure = {"how": entry.read_back, "table_ids": created, "missing": missing,
                  "read_backs": 1}
    kits = list(arguments.get("fields") or ())
    if not kits:
        return bool(created) and not missing, disclosure
    columns = [_columns_landed(read_client, app_token, table_id, tuple(kit))
               for table_id, kit in zip(created, kits) if kit]
    disclosure["columns"] = columns
    disclosure["read_backs"] = 1 + len(columns)
    return (bool(created) and not missing
            and not any(seen["missing"] or seen["mismatched"] for seen in columns)), disclosure


#: ``op name → the one call it makes``, for the two verbs a column kit rides. Published here
#: rather than branched on inside the engine, which is the seam that lets this family ship an
#: argument **in its own file** (:func:`larkdocio.base.schema_apply._family_handlers`).
ISSUE_HANDLERS = {"create_table": _issue, "batch_create_tables": _issue}

#: The same two verbs' read-backs, for the same reason: the column verification is this
#: family's own claim and belongs beside its descriptors.
READ_BACK_HANDLERS = {"create_table": _read_back, "batch_create_tables": _read_back}


__all__ = [
    "COLUMN_KIT_KEYS",
    "KIT_FIRST_ENTRY_IS_THE_PRIMARY",
    "NAMELESS_PRIMARY_IS_REFUSED",
    "PRIMARY_FIELD_NAME_AND_KIT",
    "PRIMARY_FIELD_TYPE",
    "PRIMARY_FIELD_UI_TYPE",
    "BATCH_CREATE_LOCALE_DEFAULT_PRIMARY",
    "NOT_AUTHORABLE_AT_CREATION",
    "BATCH_CREATE_IGNORES_A_COLUMN_KIT",
    "NOT_AUTHORABLE_AT_CREATION_GUIDANCE",
    "FAMILY_NAME",
    "ISSUE_HANDLERS",
    "READ_BACK_HANDLERS",
    "SCHEMA_OP_FAMILY",
    "check_batch_column_kits",
    "check_batch_primary_naming",
    "check_column_kit",
    "check_primary_naming",
    "column_kit_disclosure",
    "req_table",
]
