"""LD-659 AC4, TRANSFORMED by LD-704 — a reconstruction of an ``OutputConfig`` is silent and faithful.

`dataclasses.replace()` (and 3.13+'s `copy.replace()`) re-invokes `__init__` with the **full**
field set, read off the instance it was handed. While a retired key was tolerated as a declared
placeholder field, that meant every `replace()` re-passed the retired key for the caller, and
LD-659 fixed two defects on that path: the notice accused the caller of naming a key they never
wrote, and the reconstruction reset the placeholder to its declared default instead of copying
it.

LD-704 (absorbing LD-674) discharged the tolerance: the placeholder field and the notice are
gone, so a reconstruction passes only live fields. **The subject that survives is the one a
caller depends on** — a copy is a copy, and an ordinary copy says nothing — and it is held here
on every field, on both `replace` routes. (The retired key's own census, at every door, is in
``tests/test_config.py``.)
"""
import copy
import dataclasses
import logging

import pytest

from larkdocio.read.config import Config, OutputConfig


def larkdocio_messages(caplog, call):
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        result = call()
    return result, [r.message for r in caplog.records if r.name == "larkdocio"]


def test_replace_says_nothing(caplog):
    """The LD-659 defect was a notice naming a key the caller never wrote; the discharge's
    end state is the strongest form of the fix — no notice at all."""
    _, messages = larkdocio_messages(
        caplog, lambda: dataclasses.replace(OutputConfig(), image_dir="x"))
    assert messages == [], messages


def test_copy_replace_says_nothing_either(caplog):
    """3.13+'s `copy.replace()` reaches the dataclass by a different route with the same call
    shape."""
    if not hasattr(copy, "replace"):
        pytest.skip("copy.replace() is 3.13+; the dataclasses.replace() leg covers the shape")
    rebuilt, messages = larkdocio_messages(
        caplog, lambda: copy.replace(OutputConfig(), image_dir="x"))
    assert messages == [], messages
    assert rebuilt.image_dir == "x"


def test_a_replace_PRESERVES_every_field_it_was_not_asked_to_change(caplog):
    """LD-659's second defect, generalised: a reconstruction once reset a field to its declared
    default. Every field is now checked, with every one set OFF its default first."""
    flipped = {}
    for field in dataclasses.fields(OutputConfig):
        default = field.default
        flipped[field.name] = (not default) if isinstance(default, bool) else f"{default}-x"
    base = OutputConfig(**flipped)
    for field in dataclasses.fields(OutputConfig):
        changes = {field.name: getattr(OutputConfig(), field.name)}
        rebuilt, _ = larkdocio_messages(caplog, lambda: dataclasses.replace(base, **changes))
        expected = dict(flipped, **changes)
        assert {f.name: getattr(rebuilt, f.name) for f in dataclasses.fields(OutputConfig)} == (
            expected), field.name


def test_a_replace_still_returns_a_correct_object_on_every_OTHER_field(caplog):
    base = OutputConfig(image_dir="pool", resolve_mentions=False)
    rebuilt, _ = larkdocio_messages(caplog, lambda: dataclasses.replace(base, use_html_tags=True))
    assert (rebuilt.image_dir, rebuilt.resolve_mentions, rebuilt.use_html_tags) == (
        "pool", False, True)
    assert rebuilt.to_dict() == dict(base.to_dict(), use_html_tags=True)


def test_a_full_keyword_call_is_an_ordinary_call(caplog):
    """The shape LD-659 detected as a reconstruction (every declared field as a keyword) is now
    simply a complete call — accepted, silent, and equal to the object it was read off."""
    every = {field.name: getattr(OutputConfig(), field.name)
             for field in dataclasses.fields(OutputConfig)}
    rebuilt, messages = larkdocio_messages(caplog, lambda: OutputConfig(**every))
    assert messages == [] and rebuilt == OutputConfig()


def test_no_notice_at_all_for_the_ordinary_constructions(caplog):
    for call in (OutputConfig,
                 lambda: OutputConfig(image_dir="x"),
                 lambda: OutputConfig.from_dict({"image_dir": "x"}),
                 Config):
        _, messages = larkdocio_messages(caplog, call)
        assert messages == [], messages
