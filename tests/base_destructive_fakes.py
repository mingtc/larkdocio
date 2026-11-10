"""Offline stand-ins for the DESTRUCTIVE schema rung (LD-265) — one place, three consumers.

The loss-preview tests, the engine tests and the offline companion all need the same thing: a
**whole-app** read seam whose state the test owns, and which answers the *paging proof* question
the cross-table scan is required to ask. A second definition of either would be two opinions
about what a Base looks like from the outside.

The world here is deliberately richer than :mod:`base_schema_fakes`' — that one models apps and
tables, and this rung's whole subject is what lives *inside* the tables and *between* them: the
fields, their link properties, and the records whose cells a delete destroys.
"""
from lark_oapi.api.bitable.v1 import AppTableFieldProperty

from larkdocio.base.model import ReadProof
from larkdocio.errors import LarkAPIError


class Page:
    """One page body, in the shape :meth:`larkdocio.base.model.ReadProof.from_pages` reads."""

    def __init__(self, items, has_more=False, page_token=None):
        self.items = list(items)
        self.has_more = has_more
        self.page_token = page_token


class FakeProperty:
    """A field ``property``, attribute-shaped like the pinned SDK's own model."""

    def __init__(self, **keys):
        for name, value in keys.items():
            setattr(self, name, value)

    def __getattr__(self, name):       # every unset property key reads as None, as the SDK's
        return None


class FakeField:
    def __init__(self, field_id, field_name, type=1, ui_type="Text", property=None):
        self.field_id = field_id
        self.field_name = field_name
        self.type = type
        self.ui_type = ui_type
        self.property = property


class FakeRecord:
    def __init__(self, record_id, fields):
        self.record_id = record_id
        self.fields = dict(fields)


class FakeTable:
    def __init__(self, table_id, name, revision=1):
        self.table_id = table_id
        self.name = name
        self.revision = revision


def link_field(field_id, field_name, *, target_table_id, target_table_name=None,
               duplex=False, back_field_name=None, back_field_id=None, multiple=True):
    """A ``SingleLink`` (18) or ``DuplexLink`` (21) column, in the captured property shape.

    ``target_table_name=None`` is the **dangling** shape — the detector ``p0-5-02`` found by
    accident: deleting the target table leaves ``table_id`` in place and drops ``table_name``.
    """
    keys = {"table_id": target_table_id, "table_name": target_table_name,
            "multiple": multiple}
    if duplex:
        keys.update({"back_field_name": back_field_name, "back_field_id": back_field_id})
    return FakeField(field_id, field_name, type=21 if duplex else 18,
                     ui_type="DuplexLink" if duplex else "SingleLink",
                     property=FakeProperty(**keys))


def lookup_field(field_id, field_name, *, target_table_id, as_dict=False):
    """A ``Lookup`` (19) column, in the shape the provenance surface really reads.

    The table a Lookup rolls up from lives **nested** under ``filter_info.target_table`` — the
    one of the four provenance keys that survives this library's transport
    (:data:`larkdocio.base.computed.TARGET_TABLE_PATH`) — so a fake that put it at the top of
    the property would be testing a shape no read produces.

    ``as_dict`` picks the door the field came through: a plain dict (a raw capture) or **the
    pinned SDK's own property model** (the read path). The typed door is the PINNED SDK CLASS
    and not an attribute-shaped stand-in, because the shape that matters is one no stand-in
    reproduces: ``AppTableFieldProperty.filter_info`` is an ``AppTableFieldPropertyLookupFilter``
    **object**, not a dict, so a reader that walked the property as a mapping saw the key and
    could not read through it. A fake carrying a plain dict there passed while the live read
    refused (LD-281, QA round 1) — the blindness was in the fake, so the fake is what changed.

    ``target_table_id=None`` is the shape whose provenance did NOT arrive — a Lookup nothing
    can place — and it is built through the same typed door, where it reads as a filter object
    whose ``target_table`` is ``None``.
    """
    filter_info = {} if target_table_id is None else {"target_table": target_table_id}
    prop = ({"filter_info": dict(filter_info)} if as_dict
            else AppTableFieldProperty({"filter_info": dict(filter_info)}))
    return FakeField(field_id, field_name, type=19, ui_type="Lookup", property=prop)


def select_field(field_id, field_name, *, options, multi=False, as_dict=False):
    """A ``SingleSelect`` (3) / ``MultiSelect`` (4) column carrying its option set.

    ``as_dict`` picks the door the field came through, for the same reason
    :func:`lookup_field` does: on the **typed** door the pinned SDK turns each option into an
    ``AppTableFieldPropertyOption`` **object**, so a reader that required a mapping at the
    option level would see the array and be blind to every ``id`` in it — the LD-281 shape, one
    level deeper. ``options=None`` is the column whose option set did not arrive at all, which
    an option-shrink preview must refuse over rather than read as *no options*.
    """
    body = {} if options is None else {"options": [dict(option) for option in options]}
    prop = dict(body) if as_dict else AppTableFieldProperty(body)
    return FakeField(field_id, field_name, type=4 if multi else 3,
                     ui_type="MultiSelect" if multi else "SingleSelect", property=prop)


class ScanWorld:
    """A read seam over a whole Base whose state the test owns, **with a paging proof**.

    ``tables`` is ``{table_id: {"name":…, "revision":…, "fields":[…], "records":[…]}}``.

    ``truncate`` names the walks whose proof must read *not exhausted* — ``"tables"``,
    ``"fields:<table_id>"`` or ``"records:<table_id>"`` — which is how AC3's truncated table
    list is simulated without a network. ``raises`` maps the same keys to an exception.
    """

    def __init__(self, tables=None, *, truncate=(), raises=None, no_proof=False):
        self.tables = {table_id: dict(body) for table_id, body in (tables or {}).items()}
        self.truncate = set(truncate)
        self.raises = dict(raises or {})
        self.no_proof = no_proof
        self.calls = []
        self._pages = ()

    # -- the paging proof the destructive scan is required to ask for --------- #

    @property
    def last_walk_pages(self):
        if self.no_proof:
            raise AttributeError("this read client publishes no paging proof")
        return self._pages

    def _walk(self, key, items):
        self.calls.append(key)
        if key in self.raises:
            raise self.raises[key]
        if key in self.truncate:
            # "There is more" with no cursor to ask for it — one of the three shapes the
            # shipped walk stops under, and the one that reads most like a complete answer.
            self._pages = (Page(items, has_more=True, page_token=None),)
        else:
            self._pages = (Page(items, has_more=False),)
        return list(items)

    # -- the read seam ------------------------------------------------------- #

    def list_tables(self, app_token):
        return self._walk("tables", [FakeTable(table_id, body.get("name", table_id),
                                               body.get("revision", 1))
                                     for table_id, body in self.tables.items()])

    def list_fields(self, app_token, table_id):
        if table_id not in self.tables and f"fields:{table_id}" not in self.raises:
            # What the API really answers for a table that is not there — and therefore what
            # the object-gone oracle reads. `1254041` is a captured code, not a guess
            # (`tests/captures/base-study/captures/02-bitable18-fields.json`).
            self.calls.append(f"fields:{table_id}")
            raise LarkAPIError("no such table", code=1254041, msg="TableIdNotFound")
        return self._walk(f"fields:{table_id}",
                          list(self.tables.get(table_id, {}).get("fields", ())))

    def search_records(self, app_token, table_id):
        return self._walk(f"records:{table_id}",
                          list(self.tables.get(table_id, {}).get("records", ())))


EXHAUSTED = ReadProof(pages=1, records=0, exhausted=True, stopped_because="test fixture")


class ScriptedDestructiveClient:
    """A schema client whose three destructive methods really mutate a :class:`ScanWorld`.

    The honest offline stand-in for "the delete landed": the world really changes — the mirror
    column really disappears from the other table, the inbound links really lose their
    ``table_name`` — so a read-back that confirms is confirming something.

    ``deaf`` names ops that answer ``code:0`` and change **nothing**: the write-effect oracle's
    own defect, reproduced. ``frozen_revision`` answers ``code:0`` and removes the column while
    leaving ``table.revision`` where it was — the sharper defect, and the one AC9 names.
    """

    def __init__(self, world, deaf=(), raises=None, frozen_revision=False):
        self.world = world
        self.deaf = set(deaf)
        self.raises = dict(raises or {})
        self.frozen_revision = frozen_revision
        self.calls = []

    def _record(self, name, *args):
        self.calls.append((name,) + args)
        if name in self.raises:
            raise self.raises[name]

    def _bump(self, table_id):
        if self.frozen_revision:
            return
        body = self.world.tables.get(table_id)
        if body is not None:
            body["revision"] = (body.get("revision") or 0) + 1

    def _drop_field(self, table_id, field_id):
        body = self.world.tables.get(table_id)
        if body is None:
            return None
        for spec in list(body.get("fields", ())):
            if spec.field_id == field_id:
                body["fields"] = [f for f in body["fields"] if f.field_id != field_id]
                self._bump(table_id)
                return spec
        return None

    def delete_field(self, app_token, table_id, field_id):
        self._record("delete_field", app_token, table_id, field_id)
        if "delete_field" in self.deaf:
            return field_id
        spec = self._drop_field(table_id, field_id)
        if spec is not None and getattr(spec, "type", None) == 21:
            prop = spec.property
            # The measured two-table effect: the mirror goes with it, in the OTHER table.
            target, back = getattr(prop, "table_id", None), getattr(prop, "back_field_id", None)
            if target and back:
                self._drop_field(target, back)
        return field_id

    def _dangle_inbound(self, table_id):
        for body in self.world.tables.values():
            for spec in body.get("fields", ()):
                prop = getattr(spec, "property", None)
                if prop is not None and getattr(prop, "table_id", None) == table_id:
                    prop.table_name = None      # the detector, reproduced

    def delete_table(self, app_token, table_id):
        self._record("delete_table", app_token, table_id)
        if "delete_table" in self.deaf:
            return None
        self.world.tables.pop(table_id, None)
        self._dangle_inbound(table_id)
        return None

    def batch_delete_tables(self, app_token, table_ids):
        self._record("batch_delete_tables", app_token, tuple(table_ids))
        if "batch_delete_tables" in self.deaf:
            return list(table_ids)
        for table_id in table_ids:
            self.world.tables.pop(table_id, None)
            self._dangle_inbound(table_id)
        return list(table_ids)


def lookup_rollup_world(*, as_dict=False, target="tblSrc"):
    """The LD-281 shape: ``Rollup`` mirrors ``Source`` through a Lookup, and a third table
    mirrors ``Rollup``.

    Deleting ``Source`` destroys nothing in ``Rollup`` and yet **blanks a whole column of it**,
    which is the loss the link-only scan could not see. ``target=None`` makes the Lookup's
    provenance absent, the case the preview must refuse on rather than pass over.
    """
    return ScanWorld({
        "tblSrc": {
            "name": "Source", "revision": 3,
            "fields": [FakeField("fldSrcName", "Name")],
            "records": [FakeRecord("s1", {"Name": "one"}), FakeRecord("s2", {"Name": "two"})],
        },
        "tblRoll": {
            "name": "Rollup", "revision": 5,
            "fields": [
                FakeField("fldOwn", "Own"),
                link_field("fldSrcLink", "Source link", target_table_id="tblSrc",
                           target_table_name="Source"),
                lookup_field("fldLook", "Source rollup", target_table_id=target,
                             as_dict=as_dict),
            ],
            "records": [
                FakeRecord("r1", {"Own": "a", "Source rollup": {"type": 1, "value": ["x"]}}),
                FakeRecord("r2", {"Source rollup": {"type": 1, "value": ["y"]}}),
                FakeRecord("r3", {"Own": "c"}),
            ],
        },
        "tblOther": {
            "name": "Other", "revision": 1,
            "fields": [FakeField("fldOtherOwn", "Own"),
                       lookup_field("fldOtherLook", "Rollup rollup",
                                    target_table_id="tblRoll", as_dict=as_dict)],
            "records": [FakeRecord("o1", {"Rollup rollup": {"type": 1, "value": ["z"]}})],
        },
    })


def two_table_link_world(*, dangling=False, mirror=True):
    """The P0 shape: ``Main`` with a ``SingleLink`` and a ``DuplexLink`` into ``Ref``.

    ``mirror=False`` drops the mirror column from ``Ref`` (a shape the API does not produce —
    used only to prove the preview notices).
    """
    ref_fields = [FakeField("fldRefKey", "Name")]
    if mirror:
        ref_fields.append(link_field(
            "fldMirror", "Main-DLink", target_table_id="tblMain",
            target_table_name=None if dangling else "Main", duplex=True,
            back_field_name="DLink", back_field_id="fldDuplex"))
    return ScanWorld({
        "tblMain": {
            "name": "Main",
            "revision": 12,
            "fields": [
                FakeField("fldText", "Notes"),
                link_field("fldSingle", "SLink", target_table_id="tblRef",
                           target_table_name=None if dangling else "Ref"),
                link_field("fldDuplex", "DLink", target_table_id="tblRef",
                           target_table_name=None if dangling else "Ref", duplex=True,
                           back_field_name="Main-DLink", back_field_id="fldMirror"),
            ],
            "records": [
                FakeRecord("rec1", {"Notes": "a", "SLink": {"link_record_ids": ["r1"]},
                                    "DLink": {"link_record_ids": ["r1"]}}),
                FakeRecord("rec2", {"Notes": "b"}),
                FakeRecord("rec3", {"DLink": {"link_record_ids": ["r2"]}}),
            ],
        },
        "tblRef": {
            "name": "Ref",
            "revision": 4,
            "fields": ref_fields,
            "records": [FakeRecord("r1", {"Name": "one", "Main-DLink":
                                          {"link_record_ids": ["rec1"]}}),
                        FakeRecord("r2", {"Name": "two"})],
        },
        "tblThird": {
            "name": "Third",
            "revision": 1,
            "fields": [FakeField("fldT", "T"),
                       link_field("fldThirdLink", "RefLink", target_table_id="tblRef",
                                  target_table_name=None if dangling else "Ref")],
            "records": [FakeRecord("t1", {"RefLink": {"link_record_ids": ["r1"]}})],
        },
    })
