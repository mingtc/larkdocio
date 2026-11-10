"""LD-256 — the Base WRITE-shape encoder registry and its LOCAL refusal set.

L1's registry answers *"what did Lark send me?"*. This one answers *"what must I send
Lark?"* — and for several types **the two are different objects**. Every expectation in this
file is read out of a **committed capture**, by filename, because the failure mode this story
exists to prevent is a plausible shape that answers ``code:0`` and stores nothing (the
``extra.notify_extra`` lesson, on the write side where it is silent).

Offline and credential-free: the one live capture this story owed — the Person (11 / User)
write shape, the one writable type no earlier pack ever wrote — was taken against a
**self-provisioned disposable** and committed as
``tests/captures/base-study/captures/ld256-01-person-write-shapes.json``. The tests read that file, not
the network.
"""
import inspect
import socket

import pytest
from base_captures import CAPTURES, capture

from larkdocio.base import cells, write_cells
from larkdocio.base.cells import FieldSpec
from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def field(type_, ui_type, name="F", property_=None):
    return FieldSpec(field_name=name, type=type_, ui_type=ui_type, property=property_)


def encode(value, type_, ui_type, property_=None):
    return write_cells.encode_cell(value, field(type_, ui_type, property_=property_))


@pytest.fixture
def no_transport(monkeypatch):
    """A call-count spy with teeth: any socket a refusal opened would EXPLODE.

    AC4 / AC7 ask for "the refusal fires without any transport call being made". A counting
    spy on a client object would prove nothing — the encoder takes no client — so the spy is
    installed one layer down, on the socket itself.
    """
    calls = []

    def forbidden(*args, **kwargs):  # pragma: no cover - reaching it IS the failure
        calls.append(args)
        raise AssertionError("a LOCAL refusal opened a socket")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return calls


#: **AC1's contract, as data: every writable pair names the capture its shape came from.**
#: Not "derived from the packs" — a filename, which the first test resolves on disk.
CAPTURE_ANCHORS = {
    (1, "Text"): "p1-q6-01-value-writes.json",
    (1, "Barcode"): "p0-5-01-scalar-read-encodings.json",
    (1, "Email"): "p1-q6-01-value-writes.json",
    (13, "Phone"): "06-02-record-create-echo.json",
    (3, "SingleSelect"): "05-06-records-batch-create.json",
    (4, "MultiSelect"): "05-06-records-batch-create.json",
    (5, "DateTime"): "05-06-records-batch-create.json",
    (7, "Checkbox"): "06-02-record-create-echo.json",
    (2, "Number"): "05-06-records-batch-create.json",
    (2, "Progress"): "05-06-records-batch-create.json",
    (2, "Currency"): "p0-5-01-scalar-read-encodings.json",
    (2, "Rating"): "p0-5-01-scalar-read-encodings.json",
    (15, "Url"): "05-06-records-batch-create.json",
    (17, "Attachment"): "p0-4-01-attachment-population.json",
    (18, "SingleLink"): "p0-2-04-link-write-echo.json",
    (21, "DuplexLink"): "p0-2-04-link-write-echo.json",
    (22, "Location"): "p0-4-02-location-population.json",
    (23, "GroupChat"): "p0-4-03-groupchat-population.json",
    (11, "User"): "ld256-01-person-write-shapes.json",
}

PERSON_CAPTURE = "ld256-01-person-write-shapes.json"


def person_shape(name):
    for entry in capture(PERSON_CAPTURE)["response"]["data"]["write_shapes"]:
        if entry["shape"] == name:
            return entry
    raise AssertionError(f"{PERSON_CAPTURE} has no shape {name!r}")


# --------------------------------------------------------------------------- #
# AC1 — every writable type has a CAPTURED encoder                             #
# --------------------------------------------------------------------------- #

def test_ac1_the_writable_set_is_EXACTLY_the_read_registry_minus_the_non_writable_pairs():
    assert set(write_cells.WRITABLE_PAIRS) == set(cells.PAIRS) - set(NON_WRITABLE_PAIRS)
    assert len(write_cells.WRITABLE_PAIRS) == 19
    assert set(write_cells.WRITABLE_PAIRS) == set(CAPTURE_ANCHORS)


def test_ac1_every_encoder_NAMES_THE_CAPTURE_FILE_it_is_anchored_to():
    """The AC's own words: *not "derived from the packs", a filename*.

    Both halves are checked — the anchor exists on disk, and the shipped registry publishes
    the same mapping this test asserts against, so an encoder added without an anchor reddens
    here rather than shipping on a plausible-looking guess.
    """
    assert write_cells.CAPTURE_ANCHORS == CAPTURE_ANCHORS
    missing = [name for name in set(CAPTURE_ANCHORS.values())
               if not (CAPTURES / name).exists()]
    assert not missing, f"anchored to captures that do not exist: {missing}"


def test_ac1_text_barcode_phone_and_email_are_written_as_a_PLAIN_STRING():
    """`p1-q6-01-value-writes.json` carries the request body verbatim in its own note; the
    scalar echoes in `06-02` / `p0-5-01` say the same from the other side."""
    body = capture("p1-q6-01-value-writes.json")["steps"][0]["_note"]
    assert '"Text": "p1w-email"' in body and '"Email": "probe.value@example.invalid"' in body
    assert capture("06-02-record-create-echo.json")[
        "response"]["data"]["record"]["fields"]["Phone"] == "+12025550100"
    assert capture("p0-5-01-scalar-read-encodings.json")[
        "response"]["data"]["create_echo"]["fields"]["Barcode"] == "BC-9"

    assert encode("hello", 1, "Text") == "hello"
    assert encode("BC-9", 1, "Barcode") == "BC-9"
    assert encode("+12025550100", 13, "Phone") == "+12025550100"
    assert encode("probe.value@example.invalid", 1, "Email") == "probe.value@example.invalid"


def test_ac1_single_select_writes_the_OPTION_NAME_as_a_bare_string():
    assert capture("05-06-records-batch-create.json")[
        "response"]["data"]["records"][0]["fields"]["Z-SingleSelect"] == "Alpha"
    assert encode("Alpha", 3, "SingleSelect") == "Alpha"


def test_ac1_multi_select_writes_a_LIST_of_option_names():
    assert capture("05-06-records-batch-create.json")[
        "response"]["data"]["records"][0]["fields"]["Z-MultiSelect"] == ["Red", "Green"]
    assert encode(["Red", "Green"], 4, "MultiSelect") == ["Red", "Green"]


def test_ac1_datetime_writes_a_MS_EPOCH_INT():
    stored = capture("05-06-records-batch-create.json")[
        "response"]["data"]["records"][0]["fields"]["Z-DateTime"]
    assert stored == 1785061011000 and isinstance(stored, int)
    assert encode(1785061011000, 5, "DateTime") == 1785061011000


def test_ac1_checkbox_writes_a_BOOL():
    assert capture("06-02-record-create-echo.json")[
        "response"]["data"]["record"]["fields"]["Checkbox"] is True
    assert encode(True, 7, "Checkbox") is True
    assert encode(False, 7, "Checkbox") is False


def test_ac1_the_four_type_2_pairs_all_write_a_JSON_NUMBER():
    zoo = capture("05-06-records-batch-create.json")[
        "response"]["data"]["records"][0]["fields"]
    echo = capture("p0-5-01-scalar-read-encodings.json")[
        "response"]["data"]["create_echo"]["fields"]
    assert (zoo["Z-Number"], zoo["Z-Progress"], echo["Currency"], echo["Rating"]) == (
        42.5, 0.75, 12.5, 4)
    assert encode(42.5, 2, "Number") == 42.5
    assert encode(0.75, 2, "Progress") == 0.75
    assert encode(12.5, 2, "Currency") == 12.5
    assert encode(4, 2, "Rating") == 4


def test_ac1_url_writes_the_LINK_TEXT_OBJECT_and_NOT_the_reads_type_key():
    written = capture("05-06-records-batch-create.json")[
        "response"]["data"]["records"][0]["fields"]["Z-Url"]
    read = capture("06-03-value-read-option-matrix.json")[
        "response"]["data"]["modes"]["plain"]["populated_record"]["fields"]["Url"]
    assert written == {"link": "https://example.invalid/x", "text": "Example"}
    assert read["type"] == "url" and "type" not in written

    assert encode({"link": "https://example.invalid/x", "text": "Example"}, 15, "Url") == written
    # The read-back shape normalizes DELIBERATELY: the `type` key is the read's, not the write's.
    assert encode(read, 15, "Url") == written


def test_ac1_attachment_writes_FILE_TOKEN_OBJECTS_and_a_bare_token_list_is_1254069():
    data = capture("p0-4-01-attachment-population.json")["response"]["data"]
    accepted = data["write::list_of_file_token_objects"]
    refused = data["write::bare_list_of_tokens"]
    assert accepted["request_value"] == [{"file_token": "Example92f5849e435cbbc81d5d"}]
    assert accepted["code"] == 0
    assert (refused["code"], refused["msg"]) == (1254069, "AttachFieldConvFail")

    assert encode(["Example92f5849e435cbbc81d5d"], 17, "Attachment") == accepted["request_value"]
    assert encode(accepted["request_value"], 17, "Attachment") == accepted["request_value"]


def test_ac1_both_link_types_write_a_BARE_LIST_of_record_ids():
    """`p0-2-04`'s own note: *a bare list of record_ids is sent; this is what the API echoes*."""
    payload = capture("p0-2-04-link-write-echo.json")
    assert "bare list of record_ids is sent" in payload["_note"]
    echoed = payload["response"]["data"]["records"][1]["fields"]["SingleLinkOne"]
    assert echoed == ["recvrftvdQu0a2"]
    assert encode(["recvrftvdQu0a2"], 18, "SingleLink") == ["recvrftvdQu0a2"]
    assert encode(["recvrftvdQu0a2"], 21, "DuplexLink") == ["recvrftvdQu0a2"]


def test_ac1_location_writes_the_LNG_LAT_LITERAL_only():
    data = capture("p0-4-02-location-population.json")["response"]["data"]
    assert data["lng_lat_string"]["request_value"] == "103.8198,1.3521"
    assert data["lng_lat_string"]["code"] == 0
    assert encode("103.8198,1.3521", 22, "Location") == "103.8198,1.3521"


def test_ac1_groupchat_writes_a_LIST_OF_ID_OBJECTS_and_a_bare_string_list_is_1254001():
    data = capture("p0-4-03-groupchat-population.json")["response"]["data"]
    assert data["write::object_shape"]["code"] == 0
    assert data["write::real_chat_id"]["code"] == 1254001
    assert "must be a list of object" in data["write::real_chat_id"]["error"]["message"]
    assert encode(["oc_abc"], 23, "GroupChat") == [{"id": "oc_abc"}]
    assert encode([{"id": "oc_abc"}], 23, "GroupChat") == [{"id": "oc_abc"}]


# --------------------------------------------------------------------------- #
# AC2 — write shape ≠ create echo ≠ `records/search` read shape                 #
# --------------------------------------------------------------------------- #

def test_ac2_the_three_way_asymmetry_is_pinned_for_a_LINK_cell():
    """**A fixture pinned to the create ECHO is a bug** — and that is how the mistake gets
    made, because for a link cell the echo happens to equal the write shape while the read
    does not. Write ``["rec…"]``; the echo returns ``["rec…"]``; ``records/search`` returns
    ``{"link_record_ids": ["rec…"]}``. Three objects, two of which look identical."""
    echo = capture("p0-2-04-link-write-echo.json")[
        "response"]["data"]["records"][1]["fields"]["SingleLinkOne"]
    read = capture("p0-2-05-link-lookup-read-encodings.json")[
        "response"]["data"]["main_rows"][0]["fields"]["SingleLinkOne"]
    written = encode(["recvrftvdQu0a2"], 18, "SingleLink")

    assert written == echo == ["recvrftvdQu0a2"]
    assert isinstance(read, dict) and "link_record_ids" in read
    assert written != read
    # And the read shape is refused rather than silently unwrapped: the encoder never treats a
    # read object as a write value.
    with pytest.raises(write_cells.WriteShapeError):
        encode({"link_record_ids": ["recvrftvdQu0a2"]}, 18, "SingleLink")


def test_ac2_the_three_way_asymmetry_is_pinned_for_a_TEXT_cell():
    echo = capture("06-02-record-create-echo.json")[
        "response"]["data"]["record"]["fields"]["Text"]
    read = capture("06-03-value-read-option-matrix.json")[
        "response"]["data"]["modes"]["plain"]["populated_record"]["fields"]["Text"]
    assert echo == "THE ROW"
    assert read == [{"text": "THE ROW", "type": "text"}]
    assert encode("THE ROW", 1, "Text") == "THE ROW" == echo
    with pytest.raises(write_cells.WriteShapeError):
        encode(read, 1, "Text")


# --------------------------------------------------------------------------- #
# AC3 — Email: the sharpest asymmetry, non-round-trippable, and NO validation   #
# --------------------------------------------------------------------------- #

def test_ac3_the_email_READ_BACK_shape_is_refused_because_lark_refuses_it_1254060():
    step = capture("p1-q6-01-value-writes.json")["steps"][1]
    assert (step["_lark_code"], step["_lark_msg"]) == (1254060, "TextFieldConvFail")
    assert '"link": "mailto:' in step["_note"]

    with pytest.raises(write_cells.WriteShapeError) as caught:
        encode({"link": "mailto:probe@example.invalid", "text": "probe@example.invalid"},
               1, "Email")
    assert "1254060" in str(caught.value)
    with pytest.raises(write_cells.WriteShapeError):
        encode([{"link": "mailto:probe@example.invalid", "text": "probe@example.invalid",
                 "type": "url"}], 1, "Email")


def test_ac3_the_caller_passes_the_ADDRESS_and_lark_synthesizes_the_mailto_prefix():
    accepted = capture("p1-q6-01-value-writes.json")["steps"][0]
    assert accepted["_lark_code"] == 0
    assert encode("probe.value@example.invalid", 1, "Email") == "probe.value@example.invalid"
    assert "mailto:" in write_cells.EMAIL_IS_NOT_ROUND_TRIPPABLE
    assert "mailto:" not in encode("probe.value@example.invalid", 1, "Email")


def test_ac3_the_library_invents_NO_address_validation_lark_does_not_do():
    """Seat addendum correction #3: ``not-an-email`` writes ``code:0`` and lands, so
    ``1254060`` was about the mailto-*segment shape*, never the address format. A library that
    added a format check here would refuse writes Lark accepts."""
    assert encode("not-an-email", 1, "Email") == "not-an-email"
    assert encode("", 1, "Email") == ""
    assert "no address validation" in write_cells.EMAIL_IS_NOT_ROUND_TRIPPABLE.lower()


# --------------------------------------------------------------------------- #
# AC4 — the computed / opaque set refuses LOCALLY, before the call              #
# --------------------------------------------------------------------------- #

def test_ac4_all_eight_computed_or_opaque_pairs_refuse_with_ZERO_TRANSPORT_CALLS(no_transport):
    assert len(NON_WRITABLE_PAIRS) == 8
    for type_, ui_type in NON_WRITABLE_PAIRS:
        with pytest.raises(write_cells.NonWritableFieldError) as caught:
            encode("anything", type_, ui_type)
        message = str(caught.value)
        assert ui_type in message, message
        assert str(type_) in message, message
    assert no_transport == []


def test_ac4_the_STAGE_evidence_is_why_this_is_not_defensive_over_engineering():
    """Five Stage value shapes, five ``code:0``, and ``table.revision`` unmoved on every one.
    A library that forwarded that write would report success for data loss."""
    steps = capture("p1-q1-03-stage-writes.json")["steps"]
    dropped = [s for s in steps if s["_note"].startswith("stage write")]
    assert len(dropped) == 5
    for step in dropped:
        assert step["_lark_code"] == 0
        assert "bumped=False" in step["_note"] and "stage_in_echo=False" in step["_note"]

    created = capture("p1-q6-01-value-writes.json")["steps"][2]
    assert created["_lark_code"] == 0 and "echo_keys=['Text']" in created["_note"]

    with pytest.raises(write_cells.NonWritableFieldError):
        encode("Stage A", 24, "Stage")


def test_ac4_the_eight_pairs_are_IMPORTED_from_the_shared_vocabulary_never_re_listed():
    source = inspect.getsource(write_cells)
    assert "from larkdocio.base.write_vocabulary import" in source
    for _type, ui_type in NON_WRITABLE_PAIRS:
        assert f'"{ui_type}"' not in source.split('"""', 2)[-1], (
            f"{ui_type} is re-listed in write_cells; the set is authored ONCE in "
            "write_vocabulary (LD-255 AC2c) and imported here")


def test_ac4_the_module_can_make_NO_call_AT_ALL_by_construction():
    source = inspect.getsource(write_cells)
    for banned in ("lark_oapi", "write_client", "transport", "requests", "urllib", "socket"):
        assert banned not in source, f"the encoder module reaches for {banned}"


# --------------------------------------------------------------------------- #
# AC5 — the Location trap                                                      #
# --------------------------------------------------------------------------- #

def test_ac5_LOCATION_reversed_to_lat_lng_returns_1255002_an_INTERNAL_error_code():
    """The named regression test, carrying the story: ``"<lng>,<lat>"`` is geocoded
    server-side and ``"<lat>,<lng>"`` answers **1255002** — an *internal-error* code, not a
    validation error, and therefore the one a caller will misread as "Lark is broken". An
    address string or a ``{full_address, location}`` object answers ``1254001`` instead.

    What the encoder can and cannot catch is stated rather than implied: a pair whose values
    are BOTH inside their ranges is indistinguishable from its own reversal, so the local
    check catches only the out-of-range half — which is exactly the half the capture caught.
    """
    data = capture("p0-4-02-location-population.json")["response"]["data"]
    assert data["lat_lng_string"]["request_value"] == "1.3521,103.8198"
    assert data["lat_lng_string"]["code"] == 1255002
    assert data["address_string"]["code"] == 1254001
    assert data["object_full_address"]["code"] == 1254001

    with pytest.raises(write_cells.WriteShapeError) as reversed_:
        encode("1.3521,103.8198", 22, "Location")
    assert "1255002" in str(reversed_.value)

    with pytest.raises(write_cells.WriteShapeError) as address:
        encode("Marina Bay Sands, Singapore", 22, "Location")
    assert "1254001" in str(address.value)

    with pytest.raises(write_cells.WriteShapeError):
        encode({"full_address": "Marina Bay Sands, Singapore", "location": "103.8198,1.3521"},
               22, "Location")

    # An in-range pair is accepted whichever way round it is: the encoder does not pretend to
    # know which of two plausible coordinates the caller meant.
    assert encode("1.3521,3.8198", 22, "Location") == "1.3521,3.8198"


# --------------------------------------------------------------------------- #
# AC6 — `multiple: false` is not a cardinality guarantee                        #
# --------------------------------------------------------------------------- #

def test_ac6_multiple_false_is_NOT_enforced_by_the_server_so_the_encoder_does_not_enforce_it():
    """The Base read spec § F1-S1 AC8, re-pinned on the WRITE side: a ``SingleLink`` created with
    ``property.multiple: false`` **accepted two record ids and echoed both**, ``code:0``."""
    probe = capture("p0-4-06-field-authoring-boundary.json")[
        "response"]["data"]["multiple_false_fed_two_ids"]
    assert probe["code"] == 0
    assert probe["request"] == probe["echo"] == ["recvrdC1LZZeuo", "recvrkV1rRVeKa"]

    single = field(18, "SingleLink", property_={"multiple": False})
    assert write_cells.encode_cell(probe["request"], single) == probe["request"]
    assert "multiple" not in inspect.getsource(write_cells._e_link_ids)


# --------------------------------------------------------------------------- #
# AC7 — Person (11 / User): captured in THIS story, and IDS ONLY (D3′(c))       #
# --------------------------------------------------------------------------- #

def test_ac7_the_person_write_shape_is_a_LIST_OF_ID_OBJECTS_captured_live_here():
    accepted = person_shape("list_of_id_objects")
    assert accepted["code"] == 0
    assert accepted["request_value"] == [{"id": "<redacted:person-id>"}]
    assert encode([{"id": "ou_x"}], 11, "User") == [{"id": "ou_x"}]
    assert encode(["ou_x"], 11, "User") == [{"id": "ou_x"}]


def test_ac7_the_three_OTHER_person_shapes_are_all_1254066_UserFieldConvFail():
    """Including the name-shaped one — **the server itself refuses a name**, which is what
    makes the id-only ruling a description of the API rather than a library preference."""
    for shape in ("bare_list_of_ids", "bare_string_id", "list_of_name_objects"):
        entry = person_shape(shape)
        assert (entry["code"], entry["msg"]) == (1254066, "UserFieldConvFail"), shape


def test_ac7_a_NAME_SHAPED_argument_earns_a_TYPED_refusal_with_zero_transport_calls(
        no_transport):
    for value in ("Ada Lovelace", ["Ada Lovelace"], [{"name": "Ada Lovelace"}],
                  [{"en_name": "Ada Lovelace"}]):
        with pytest.raises(write_cells.PersonNameNotResolvableError):
            encode(value, 11, "User")
    assert no_transport == []


def test_ac7_the_refusal_names_the_TWO_HONEST_ID_SOURCES_and_STATES_the_deferred_mandate():
    """The mandate is stated as a FACT, not as a citation.

    The sentence used to end *"see dev/downtime-queue.md"* — a file that ships in no
    artifact — so the answer a blocked caller is most likely to act on sent them to a
    document they do not hold. The deferral is the point and it survives; the dangling
    pointer does not.
    """
    with pytest.raises(write_cells.PersonNameNotResolvableError) as caught:
        encode([{"name": "Ada Lovelace"}], 11, "User")
    message = str(caught.value)
    assert "larkdocio.contacts.resolve_user" in message
    assert "deferred work with its own mandate" in message
    assert "dev/" not in message
    assert "harvest" in message.lower() and "caller" in message.lower()


def test_ac7_the_refusal_INVENTS_NO_RESOLUTION_PATH_because_D1_triple_prime_deferred_it():
    """D1‴ = (b): the other-user name→id gap is deferred for a **comprehensive-solution
    investigation** — *"no roster-table hack, no abandonment"*. A lookup table, a scraped
    directory or a "best effort" match shipped here would contradict a live ruling, so the
    refusal is checked for the vocabulary such a shortcut would arrive in."""
    with pytest.raises(write_cells.PersonNameNotResolvableError) as caught:
        encode([{"name": "Ada Lovelace"}], 11, "User")
    message = str(caught.value).lower()
    for invented in ("roster", "best effort", "best-effort", "fuzzy", "closest match",
                     "approximate", "guess"):
        assert invented not in message, f"the refusal offers an invented path: {invented}"


def test_ac7_the_person_encoder_DROPS_every_pii_key_the_read_shape_carries():
    read_back = person_shape("read_back_shape")["request_value"]
    assert set(read_back[0]) == {"id", "name", "en_name"}
    assert encode(read_back, 11, "User") == [{"id": "<redacted:person-id>"}]


# --------------------------------------------------------------------------- #
# AC7b — no Button encoder, no Button row, no bespoke refusal                   #
# --------------------------------------------------------------------------- #

def test_ac7b_the_write_registry_has_NO_BUTTON_ENTRY_AND_NO_BESPOKE_REFUSAL():
    """The write-side twin of ``test_ac1_button_has_no_pair_and_no_renderer``. The generic
    unregistered-pair refusal covers it; a bespoke branch would be the library re-opening a maintainer
    ruling that an API fact explicitly does not reopen."""
    assert not [pair for pair in write_cells.WRITABLE_PAIRS if pair[1] == "Button"]
    assert write_cells.encoder_for(3001, "Button") is None
    body = inspect.getsource(write_cells).split('"""', 2)[-1]
    assert "3001" not in body and "Button" not in body, (
        "Button is discussed in the module docstring and nowhere in its code — a bespoke "
        "branch keyed on its identity is exactly what AC7b forbids")

    with pytest.raises(write_cells.UnsupportedFieldTypeError):
        encode("anything", 3001, "Button")


def test_ac7b_the_same_generic_refusal_covers_a_field_type_nobody_has_seen(no_transport):
    with pytest.raises(write_cells.UnsupportedFieldTypeError):
        encode("anything", 4242, "SomethingNew")
    assert no_transport == []


# --------------------------------------------------------------------------- #
# AC8 — PII discipline on the write side                                       #
# --------------------------------------------------------------------------- #

def test_ac8_no_refusal_message_ECHOES_the_person_or_chat_VALUE_it_refused():
    secrets = {
        "ou_SECRET_PERSON_ID": lambda v: encode({"id": v}, 11, "User"),
        "Ada SECRETNAME Lovelace": lambda v: encode([{"name": v}], 11, "User"),
        "oc_SECRET_CHAT_ID": lambda v: encode([{"nope": v}], 23, "GroupChat"),
        "secret.person@example.invalid": lambda v: encode({"link": f"mailto:{v}"}, 1, "Email"),
    }
    for secret, call in secrets.items():
        try:
            call(secret)
        except write_cells.BaseWriteRefusal as refusal:
            assert secret not in str(refusal), f"a refusal echoed {secret!r}"
        # A shape that is ACCEPTED is not this test's subject — only the refusals are.


def test_ac8_the_committed_person_capture_leaks_NOTHING():
    """The bar is the P0/P1 sweep result, applied to the one capture this story added: 0
    emails, 0 person ids, 0 chat ids, 0 avatar/CDN URLs, 0 unredacted names."""
    text = (CAPTURES / PERSON_CAPTURE).read_text(encoding="utf-8")
    for leak in ("@", "ou_", "on_", "oc_", "feishucdn", "larksuite.com", "avatar_url\": \"h"):
        assert leak not in text, f"the committed capture carries {leak!r}"
    assert "<redacted:person-id>" in text and "<redacted:person-name>" in text


def test_ac8_a_probe_authored_address_uses_the_RFC_2606_RESERVED_domain():
    body = capture("p1-q6-01-value-writes.json")["steps"][0]["_note"]
    assert "example.invalid" in body


# --------------------------------------------------------------------------- #
# The test-rigor amplifier (from the spec)                                      #
# --------------------------------------------------------------------------- #

def test_amplifier_EVERY_encoder_is_fed_its_own_READ_BACK_shape():
    """Refuse, or normalize **deliberately** — never guess. Every writable pair is fed the
    shape ``records/search`` returns for it, and the outcome is asserted per pair, so a new
    encoder cannot skip the question."""
    read_back = {
        (1, "Text"): ([{"text": "x", "type": "text"}], "refuse"),
        (1, "Barcode"): ([{"text": "BC-9", "type": "text"}], "refuse"),
        (1, "Email"): ([{"link": "mailto:a@example.invalid", "text": "a@example.invalid",
                         "type": "url"}], "refuse"),
        (13, "Phone"): ("+12025550100", "+12025550100"),
        (3, "SingleSelect"): ("Alpha", "Alpha"),
        (4, "MultiSelect"): (["Red", "Green"], ["Red", "Green"]),
        (5, "DateTime"): (1785061011000, 1785061011000),
        (7, "Checkbox"): (True, True),
        (2, "Number"): (42.5, 42.5),
        (2, "Progress"): (0.35, 0.35),
        (2, "Currency"): (12.5, 12.5),
        (2, "Rating"): (4, 4),
        (15, "Url"): ({"link": "https://e.invalid/x", "text": "E", "type": "url"},
                      {"link": "https://e.invalid/x", "text": "E"}),
        (17, "Attachment"): ([{"file_token": "tok", "name": "f.txt", "size": 1,
                               "url": "https://cdn.invalid/f"}], [{"file_token": "tok"}]),
        (18, "SingleLink"): ({"link_record_ids": ["rec1"]}, "refuse"),
        (21, "DuplexLink"): ({"link_record_ids": ["rec1"]}, "refuse"),
        (22, "Location"): ({"full_address": "somewhere", "location": "103.8,1.35"}, "refuse"),
        (23, "GroupChat"): ([{"id": "oc_x", "name": "Team", "avatar_url": "https://c.invalid"}],
                            [{"id": "oc_x"}]),
        (11, "User"): ([{"id": "ou_x", "name": "N", "en_name": "N",
                         "email": "n@example.invalid", "avatar_url": "https://c.invalid"}],
                       [{"id": "ou_x"}]),
    }
    assert set(read_back) == set(write_cells.WRITABLE_PAIRS)
    for pair, (value, expected) in read_back.items():
        if expected == "refuse":
            with pytest.raises(write_cells.WriteShapeError):
                encode(value, *pair)
        else:
            assert encode(value, *pair) == expected, pair


def test_amplifier_NONE_and_EMPTY_STRING_and_ABSENT_are_three_distinct_things():
    text = field(1, "Text", name="Text")
    number = field(2, "Number", name="Number")

    # `None` — an explicit clear the caller asked for. Distinct from a missing key.
    assert write_cells.encode_fields({"Text": None}, [text, number]) == {"Text": None}
    # `""` — a real empty string, which for a text field is a value.
    assert write_cells.encode_fields({"Text": ""}, [text, number]) == {"Text": ""}
    # ABSENT — the key never appears, which is the shape an empty cell READS BACK as.
    assert write_cells.encode_fields({}, [text, number]) == {}
    assert write_cells.encode_fields({"Text": write_cells.OMIT}, [text, number]) == {}
    # `None` on a numeric field is a clear too, never a coerced zero.
    assert write_cells.encode_fields({"Number": None}, [text, number]) == {"Number": None}


def test_amplifier_a_CHECKBOX_written_FALSE_reads_back_as_an_ABSENT_KEY_not_false():
    checkbox = field(7, "Checkbox", name="Checkbox")
    assert write_cells.encode_fields({"Checkbox": False}, [checkbox]) == {"Checkbox": False}
    # …and the read side's own answer for that same cell is the ABSENT form, not `false`.
    assert cells.render_absent(checkbox) == "[ ]"
    assert cells.render_row({}, [checkbox]) == ["[ ]"]


def test_encode_fields_refuses_a_FIELD_NAME_THE_SCHEMA_DOES_NOT_KNOW(no_transport):
    with pytest.raises(write_cells.UnsupportedFieldTypeError):
        write_cells.encode_fields({"Nope": "x"}, [field(1, "Text", name="Text")])
    assert no_transport == []


def test_encode_fields_refuses_a_NON_WRITABLE_FIELD_before_building_anything(no_transport):
    schema = [field(1, "Text", name="Text"), field(20, "Formula", name="Calc")]
    with pytest.raises(write_cells.NonWritableFieldError):
        write_cells.encode_fields({"Text": "ok", "Calc": 1}, schema)
    assert no_transport == []


def test_every_refusal_is_a_LarkConfigError_so_existing_handlers_catch_it():
    from larkdocio.errors import LarkConfigError, LarkDocIOError

    for cls in (write_cells.BaseWriteRefusal, write_cells.NonWritableFieldError,
                write_cells.UnsupportedFieldTypeError, write_cells.WriteShapeError,
                write_cells.PersonNameNotResolvableError):
        assert issubclass(cls, LarkConfigError) and issubclass(cls, LarkDocIOError)
