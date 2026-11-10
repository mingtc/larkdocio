"""CAPTURED comment payloads — cut verbatim from the committed probe captures.

Every dict here is a **real Lark response body**, copied byte-for-byte out of
``tests/captures/comments-probe-captures/``. Nothing is hand-invented: the probe ran against
self-provisioned disposables, every payload below is one of its recorded ``response``
objects, and the provenance comment above each names the capture file and the label of
the call inside it. So a fixture drift is an API drift, not an author's guess (PROJECT.md
§ Quality bar: fixtures are deserialized from actual API JSON).

Why a module rather than ``tests/fixtures/``: that directory is the reader's
input/expected GOLDEN corpus, walked pairwise by ``tests/test_golden.py``. These are
transport payloads for a different surface, so they live beside ``write_harness.py`` as
readable per-test DATA (the ``write_harness`` doctrine).

**Where a payload is NOT a verbatim capture, it says so at its own definition.** Two classes
of exception exist here and both are labelled: a handful of reply/thread *arrangements* the
probe's create route could not produce (composed on captured envelopes — see § 2b), and the
``1069304`` error body, which had no committed capture and has since been observed directly
against a deleted disposable (its note records what the guess got wrong). Everything else is
copied out of a capture file unchanged.
"""

# --------------------------------------------------------------------------- #
# 1. The whole-document comment, in ALL FOUR endpoint shapes.                   #
#                                                                              #
#    The asymmetry this surface has to survive is visible by eye below:         #
#    ``is_whole`` is ABSENT from CREATE and GET-one and PRESENT on LIST and     #
#    BATCH_QUERY, for the very same comment.                                    #
# --------------------------------------------------------------------------- #

#: ``01-hazard-drill.json`` → label ``v1-create-whole-doc``
#: (``POST /open-apis/drive/v1/files/{doc}/comments?file_type=docx``, HTTP 200, code 0).
#: NOTE the absent ``is_whole`` — this comment IS whole-document (LIST says so below),
#: and the create response does not say so at all.
CREATE_WHOLE_DOC = {
    "code": 0,
    "data": {
        "comment_id": "7667710952829095653",
        "create_time": 1785278076,
        "is_solved": False,
        "reply_list": {
            "replies": [
                {
                    "content": {
                        "elements": [
                            {
                                "docs_link": None,
                                "person": None,
                                "text_run": {
                                    "text": "LD-156 hazard-drill comment ALPHA-9f15285c — disposable only."
                                },
                                "type": "text_run",
                            }
                        ]
                    },
                    "create_time": 1785278076,
                    "extra": None,
                    "reply_id": "7667710952845889243",
                    "update_time": 1785278076,
                    "user_id": "ou_examplebot0000000000000000000001",
                }
            ]
        },
        "solver_user_id": None,
        "update_time": 1785278076,
        "user_id": "ou_examplebot0000000000000000000001",
    },
    "msg": "Success",
}

#: ``01-hazard-drill.json`` → label ``get-comment``
#: (``GET …/comments/{cid}``, HTTP 200, code 0). ``is_whole`` ABSENT here too — so the
#: absence is a property of the ENDPOINT, not of the create call.
GET_ONE_WHOLE_DOC = {
    "code": 0,
    "data": {
        "comment_id": "7667710952829095653",
        "create_time": 1785278076,
        "is_solved": False,
        "reply_list": {
            "replies": [
                {
                    "content": {
                        "elements": [
                            {
                                "docs_link": None,
                                "person": None,
                                "text_run": {
                                    "text": "LD-156 hazard-drill comment ALPHA-9f15285c — disposable only."
                                },
                                "type": "text_run",
                            }
                        ]
                    },
                    "create_time": 1785278076,
                    "extra": {"image_list": None},
                    "reply_id": "7667710952845889243",
                    "update_time": 1785278076,
                    "user_id": "ou_examplebot0000000000000000000001",
                }
            ]
        },
        "solver_user_id": None,
        "update_time": 1785278076,
        "user_id": "ou_examplebot0000000000000000000001",
    },
    "msg": "Success",
}

#: ``01-hazard-drill.json`` → label ``list-after-create``
#: (``GET …/comments``, HTTP 200, code 0). ``is_whole: true`` PRESENT.
LIST_ONE_PAGE = {
    "code": 0,
    "data": {
        "has_more": False,
        "items": [
            {
                "comment_id": "7667710952829095653",
                "create_time": 1785278076,
                "is_solved": False,
                "is_whole": True,
                "reply_list": {
                    "replies": [
                        {
                            "content": {
                                "elements": [
                                    {
                                        "docs_link": None,
                                        "person": None,
                                        "text_run": {
                                            "text": "LD-156 hazard-drill comment ALPHA-9f15285c — disposable only."
                                        },
                                        "type": "text_run",
                                    }
                                ]
                            },
                            "create_time": 1785278076,
                            "extra": {"image_list": None},
                            "reply_id": "7667710952845889243",
                            "update_time": 1785278076,
                            "user_id": "ou_examplebot0000000000000000000001",
                        }
                    ]
                },
                "solver_user_id": None,
                "update_time": 1785278076,
                "user_id": "ou_examplebot0000000000000000000001",
            }
        ],
        "page_token": "7667710952829095653",
    },
    "msg": "Success",
}

#: ``01-hazard-drill.json`` → label ``batch-query-need-relation``
#: (``POST …/comments/batch_query?need_relation=true``, HTTP 200, code 0).
#: TWO facts to read off this one: ``is_whole: true`` is PRESENT, and there is NO
#: ``relation`` key AT ALL even though the request asked for it — which is why this
#: surface ships no reverse join.
BATCH_QUERY_ONE = {
    "code": 0,
    "data": {
        "items": [
            {
                "comment_id": "7667710952829095653",
                "create_time": 1785278076,
                "has_more": False,
                "is_solved": False,
                "is_whole": True,
                "page_token": "",
                "reply_list": {
                    "replies": [
                        {
                            "content": {
                                "elements": [
                                    {
                                        "docs_link": None,
                                        "person": None,
                                        "text_run": {
                                            "text": "LD-156 hazard-drill comment ALPHA-9f15285c — disposable only."
                                        },
                                        "type": "text_run",
                                    }
                                ]
                            },
                            "create_time": 1785278076,
                            "extra": {"image_list": None},
                            "reply_id": "7667710952845889243",
                            "update_time": 1785278076,
                            "user_id": "ou_examplebot0000000000000000000001",
                        }
                    ]
                },
                "solver_user_id": None,
                "update_time": 1785278076,
                "user_id": "ou_examplebot0000000000000000000001",
            }
        ]
    },
    "msg": "Success",
}

#: ``01-hazard-drill.json`` → label ``removal-b-replies-list``
#: (``GET …/comments/{cid}/replies``, HTTP 200, code 0). The reply-list endpoint's own
#: page shape — ``items`` are bare replies, with ``has_more`` / ``page_token`` beside them.
REPLY_LIST_ONE_PAGE = {
    "code": 0,
    "data": {
        "has_more": False,
        "items": [
            {
                "content": {
                    "elements": [
                        {
                            "docs_link": None,
                            "person": None,
                            "text_run": {
                                "text": "LD-156 hazard-drill comment ALPHA-9f15285c — disposable only."
                            },
                            "type": "text_run",
                        }
                    ]
                },
                "create_time": 1785278076,
                "extra": {"image_list": None},
                "reply_id": "7667710952845889243",
                "update_time": 1785278076,
                "user_id": "ou_examplebot0000000000000000000001",
            }
        ],
        "page_token": "0",
    },
    "msg": "Success",
}

# --------------------------------------------------------------------------- #
# 2. The PERSON mention — the only captured multi-element reply.                #
# --------------------------------------------------------------------------- #

#: ``04-authorship.json`` → ``content_person_mention.response`` (create, HTTP 200, code 0).
#: A two-element reply: a ``text_run`` then a ``person`` carrying a RAW ``user_id`` and
#: nothing else — no display name, no ``user_type``. The captured proof that the author of
#: a mention is an opaque id as far as this surface is concerned.
CREATE_WITH_PERSON_MENTION = {
    "code": 0,
    "data": {
        "comment_id": "7667711237102243557",
        "create_time": 1785278142,
        "is_solved": False,
        "reply_list": {
            "replies": [
                {
                    "content": {
                        "elements": [
                            {
                                "docs_link": None,
                                "person": None,
                                "text_run": {"text": "mention arm: "},
                                "type": "text_run",
                            },
                            {
                                "docs_link": None,
                                "person": {
                                    "user_id": "ou_examplebot0000000000000000000001"
                                },
                                "text_run": None,
                                "type": "person",
                            },
                        ]
                    },
                    "create_time": 1785278142,
                    "extra": None,
                    "reply_id": "7667711237119020767",
                    "update_time": 1785278142,
                    "user_id": "ou_examplebot0000000000000000000001",
                }
            ]
        },
        "solver_user_id": None,
        "update_time": 1785278142,
        "user_id": "ou_examplebot0000000000000000000001",
    },
    "msg": "Success",
}

# --------------------------------------------------------------------------- #
# 2b. COMPOSED reply shapes — real element shapes, arrangements the probe could   #
#     not produce.                                                              #
#                                                                              #
#     Honesty note. The probe created every comment it read, and the create API  #
#     it had accepts a single reply of text and mentions. So three arrangements  #
#     have no capture: a ``docs_link`` element, a multi-reply thread, and a      #
#     thread the server reports as TRUNCATED. Each is composed below out of      #
#     shapes that ARE captured (or, for ``docs_link``, out of the pinned SDK's   #
#     own field contract), and each says so at its definition. The alternative   #
#     was leaving three element/thread arms untested, which is worse.            #
# --------------------------------------------------------------------------- #

#: **COMPOSED.** No probe reply contained a ``docs_link``: the create route it used takes
#: text and mentions, so one was never produced to read back. The element's shape is pinned
#: by the SDK's own ``DocsLink`` model (one field, ``url``) and by the sibling keys every
#: captured element carries (all three sub-objects present, the irrelevant ones ``null``,
#: plus a ``type`` label). Composed onto the captured reply envelope verbatim.
REPLY_WITH_ALL_THREE_ELEMENT_KINDS = {
    "content": {
        "elements": [
            {
                "docs_link": None,
                "person": None,
                "text_run": {"text": "see "},
                "type": "text_run",
            },
            {
                "docs_link": {"url": "https://example.larksuite.com/docx/AbCdEf123456"},
                "person": None,
                "text_run": None,
                "type": "docs_link",
            },
            {
                "docs_link": None,
                "person": None,
                "text_run": {"text": " and "},
                "type": "text_run",
            },
            {
                "docs_link": None,
                "person": {"user_id": "ou_examplebot0000000000000000000001"},
                "text_run": None,
                "type": "person",
            },
        ]
    },
    "create_time": 1785278076,
    "extra": {"image_list": None},
    "reply_id": "7667710952845889243",
    "update_time": 1785278076,
    "user_id": "ou_examplebot0000000000000000000001",
}

#: **COMPOSED.** A three-reply thread — the captured reply envelope repeated with distinct
#: ids and texts. The probe only ever created single-reply threads (one create, one reply),
#: so a real multi-reply capture does not exist; the envelope is unchanged from the capture.
MULTI_REPLY_THREAD = {
    "comment_id": "7667710952829095653",
    "create_time": 1785278076,
    "is_solved": False,
    "is_whole": False,
    "quote": "Revenue grew 12.4% in Q3.",
    "reply_list": {
        "replies": [
            {
                "content": {"elements": [{
                    "docs_link": None, "person": None,
                    "text_run": {"text": "Is this figure final?"}, "type": "text_run"}]},
                "create_time": 1785278076,
                "extra": {"image_list": None},
                "reply_id": "reply-1",
                "update_time": 1785278076,
                "user_id": "ou_examplebot0000000000000000000001",
            },
            {
                "content": {"elements": [{
                    "docs_link": None, "person": None,
                    "text_run": {"text": "Not yet — audit pending."}, "type": "text_run"}]},
                "create_time": 1785278077,
                "extra": {"image_list": None},
                "reply_id": "reply-2",
                "update_time": 1785278077,
                "user_id": "ou_second_reviewer_0000000000000000",
            },
            {
                "content": {"elements": [
                    {"docs_link": None, "person": None,
                     "text_run": {"text": "thanks "}, "type": "text_run"},
                    {"docs_link": None,
                     "person": {"user_id": "ou_examplebot0000000000000000000001"},
                     "text_run": None, "type": "person"},
                ]},
                "create_time": 1785278078,
                "extra": {"image_list": None},
                "reply_id": "reply-3",
                "update_time": 1785278078,
                "user_id": "ou_second_reviewer_0000000000000000",
            },
        ]
    },
    "solver_user_id": None,
    "update_time": 1785278078,
    "user_id": "ou_examplebot0000000000000000000001",
}

#: **COMPOSED.** A comment whose embedded thread the server reports as PARTIAL. The keys are
#: the ones the captured batch-fetch item really carries (``has_more`` / ``page_token`` sit on
#: the item itself — see :data:`BATCH_QUERY_ONE`, where they are ``false`` / ``""``); here
#: they are flipped to the truthy case the probe's single-reply threads never reached.
COMMENT_WITH_TRUNCATED_THREAD = {
    "comment_id": "7667710952829095653",
    "create_time": 1785278076,
    "has_more": True,
    "is_solved": False,
    "is_whole": True,
    "page_token": "reply-page-2",
    "reply_list": {
        "replies": [
            {
                "content": {"elements": [{
                    "docs_link": None, "person": None,
                    "text_run": {"text": "first page reply"}, "type": "text_run"}]},
                "create_time": 1785278076,
                "extra": {"image_list": None},
                "reply_id": "reply-1",
                "update_time": 1785278076,
                "user_id": "ou_examplebot0000000000000000000001",
            }
        ]
    },
    "solver_user_id": None,
    "update_time": 1785278076,
    "user_id": "ou_examplebot0000000000000000000001",
}

#: **COMPOSED.** The remaining replies the reply-list endpoint serves for the comment above,
#: in that endpoint's own captured page shape (:data:`REPLY_LIST_ONE_PAGE`).
REPLY_LIST_PAGE_TWO = {
    "code": 0,
    "data": {
        "has_more": False,
        "items": [
            {
                "content": {"elements": [{
                    "docs_link": None, "person": None,
                    "text_run": {"text": "second page reply"}, "type": "text_run"}]},
                "create_time": 1785278079,
                "extra": {"image_list": None},
                "reply_id": "reply-2",
                "update_time": 1785278079,
                "user_id": "ou_examplebot0000000000000000000001",
            }
        ],
        "page_token": "0",
    },
    "msg": "Success",
}

#: **COMPOSED.** A reply whose content is absent entirely — the shape a thread takes when the
#: server sends no ``content`` at all. Derived by deletion from the captured envelope.
REPLY_WITHOUT_CONTENT = {
    "create_time": 1785278076,
    "extra": None,
    "reply_id": "reply-empty",
    "update_time": 1785278076,
    "user_id": "ou_examplebot0000000000000000000001",
}

#: **COMPOSED.** A comment with no thread at all (``reply_list`` absent), resolved. Derived
#: from :data:`LIST_ONE_PAGE`'s item by deleting ``reply_list`` and flipping ``is_solved`` with
#: a ``solver_user_id`` beside it — the resolved shape the round-2 harvest captured for real
#: (``examples.Resolved`` in ``tests/captures/comments-probe-round2-captures/10-harvest-docx.json``).
#: **CORRECTED:** this fixture used to carry ``"solved_time": 1785278090``, which was neither
#: captured nor derivable by deletion — no comment endpoint has **ever** sent ``solved_time``,
#: on either surface, so a fixture carrying one proved the opposite of the API's behaviour.
COMMENT_WITHOUT_REPLY_LIST = {
    "comment_id": "comment-no-replies",
    "create_time": 1785278076,
    "is_solved": True,
    "is_whole": True,
    "solver_user_id": "ou_examplebot0000000000000000000001",
    "update_time": 1785278076,
    "user_id": "ou_examplebot0000000000000000000001",
}

#: **COMPOSED.** An element of a kind this projection does not model — the forward-compatible
#: case. Shaped like every captured element (all modelled sub-objects ``null``, a ``type``
#: label the API alone knows).
REPLY_WITH_UNMODELLED_ELEMENT = {
    "content": {
        "elements": [
            {"docs_link": None, "person": None, "text_run": None, "type": "sticker"},
            {"docs_link": None, "person": None,
             "text_run": {"text": "tail"}, "type": "text_run"},
        ]
    },
    "create_time": 1785278076,
    "extra": None,
    "reply_id": "reply-unmodelled",
    "update_time": 1785278076,
    "user_id": "ou_examplebot0000000000000000000001",
}


# --------------------------------------------------------------------------- #
# 3. The SHEETS leg — read ACCEPTED where create is enum-REJECTED.               #
# --------------------------------------------------------------------------- #

#: ``03-create-v2-sheets.json`` → label ``s3-list-file_type-sheet``
#: (``GET …/comments?file_type=sheet`` on a spreadsheet token, HTTP 200, **code 0**).
#: The list is empty because the probe could never CREATE a sheets comment to list — see
#: :data:`SHEETS_CREATE_ENUM_REJECTED`. The value of this capture is the ``code 0``: the
#: read is accepted on the same token whose create is refused.
SHEETS_LIST_ACCEPTED = {
    "code": 0,
    "data": {"has_more": False, "items": [], "page_token": "0"},
    "msg": "Success",
}

#: ``03-create-v2-sheets.json`` → label ``s3-list-file_type-docx``
#: (the same spreadsheet token read with ``file_type=docx``, HTTP 404, code 1069307).
#: The control that makes the row above mean something: the token is real, and it is the
#: WRONG ``file_type`` that fails — so ``file_type`` is load-bearing, not decorative.
SHEETS_LIST_WRONG_FILE_TYPE = {
    "code": 1069307,
    "msg": "not exist",
    "error": {"log_id": "202607290635333C60DFEDA5CBCCB8B09F"},
}

#: ``03-create-v2-sheets.json`` → label ``s2-D-whole-file-on-sheets``
#: (``POST …/comments?file_type=sheet``, HTTP 400, code 99992402). The create side of the
#: asymmetry, with the enum printed by the server itself. Captured for the disclosure, NOT
#: because this surface ever creates anything.
SHEETS_CREATE_ENUM_REJECTED = {
    "code": 99992402,
    "msg": "field validation failed",
    "error": {
        "log_id": "202607290635305477620229AA27BBCC6B",
        "field_violations": [
            {
                "field": "file_type",
                "value": "sheet",
                "description": "file_type is optional, options: [doc,docx]",
            }
        ],
    },
}

# --------------------------------------------------------------------------- #
# 4. The ERROR envelopes the graceful-degrade path maps.                        #
# --------------------------------------------------------------------------- #

#: ``00-smoke.json`` → label ``docx-batch-query-bogus-id``
#: (``POST …/comments/batch_query`` with ``{"comment_ids":["nonexistent-comment-id"]}``,
#: HTTP 400, code 9499). A MALFORMED id is rejected for the whole batch — which is why a
#: caller cannot use a 9499 to learn which single id was bad.
BATCH_QUERY_MALFORMED_ID = {
    "code": 9499,
    "msg": (
        'Invalid parameter type in json: CommentIDs. Invalid parameter value: '
        '"nonexistent-comment-id". Please check and modify accordingly.'
    ),
    "error": {"log_id": "2026072906342892B1FAE6EFF60CE8458A"},
}

#: ``01-hazard-drill.json`` → label ``removal-e-get-after-reply-delete``
#: (``GET …/comments/{cid}`` after the last reply was deleted, HTTP 404, code 1069307).
GET_ONE_GONE = {
    "code": 1069307,
    "msg": "not exist",
    "error": {"log_id": "20260729063452EE96CFE0AB4A8FD91BC9"},
}

#: ``01-hazard-drill.json`` → label ``removal-f-patch-solved``
#: (``PATCH …/comments/{cid}`` ``{"is_solved": true}`` on a vanished comment, HTTP 400,
#: code 1069301). This surface never patches; the code is in the table because a consumer
#: reading comments will meet it the moment it tries to resolve one.
PATCH_SOLVED_VANISHED = {
    "code": 1069301,
    "msg": "fail",
    "error": {"log_id": "202607290634539A4C1EA0DFDB6ECF9AF5"},
}

#: ``04-authorship.json`` → ``content_empty.response`` (HTTP 400, code 1069302).
EMPTY_REPLY_CONTENT = {
    "code": 1069302,
    "msg": "param error",
    "error": {"log_id": "20260729063543D8FB0A917C28342284D8"},
}

#: ``04-authorship.json`` → ``contact_resolve`` (``GET /open-apis/contact/v3/users/{ou_…}``,
#: HTTP 400, code 41050). The scope gap that stays a gap: this surface never makes this
#: call, and no scope is requested to make it succeed.
CONTACT_RESOLVE_DENIED = {
    "code": 41050,
    "msg": "no user authority error",
}

#: ``1069304`` — a comments list issued against a file that has been trashed.
#:
#: **Provenance, corrected after the fact.** This started out as the one assembled payload in
#: this module: the code had been *seen* while re-verifying the probe's close-out, but no
#: capture file recorded it, so its message was a guess. It is now **observed directly**. The
#: live comments gate deletes the two disposables it creates, and re-querying both of them
#: afterwards — read-only, through this very surface — answered ``1069304`` with the message
#: below, verbatim, on both. The guess had been ``"not exist"`` (borrowed from ``1069307``);
#: the server actually says ``"docs had been deleted"``, which is a different and more precise
#: statement, and the reason the fixture is now real rather than plausible. The ``log_id`` is
#: still not reproduced: it is per-request by nature and carries no behaviour.
LIST_ON_DELETED_FILE = {
    "code": 1069304,
    "msg": "docs had been deleted",
    "error": {"log_id": "observed-live-log-id-not-reproduced"},
}
