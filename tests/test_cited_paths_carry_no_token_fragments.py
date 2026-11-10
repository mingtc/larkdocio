"""LD-700 (round 3 of the public-export review, T13) — a cited maintainers' file name carries no
fragment of a real token.

Probe recordings are often named after what they touched, and two cited file names in
``DRIVE.md`` carried the first eight characters of a real Drive file token. The substitution
rules replace prefixes of tokens the private record holds, but these tokens appear nowhere else,
so nothing related the fragment to a known value. This sweep needs no known value: in every
``dev/…`` path the shipped corpus cites, a hyphen- or underscore-delimited segment of 7 to 12
lowercase letters and digits that contains a digit must be a named stem (``dogfood5``,
``bitable18``) — anything else reads as a token fragment and is written ``<token>`` instead.
"""
import re

from test_citation_label_reservation import corpus

_DEV_PATH = re.compile(r"dev/[A-Za-z0-9_./<>-]+")
_SEGMENT = re.compile(r"(?<![a-z0-9])[a-z0-9]{7,12}(?![a-z0-9])")
#: Word stems a probe names its own objects with; a segment is a stem plus a number.
_NAMED_STEMS = ("dogfood", "bitable", "refbase", "scratch", "fixture", "summary")


def _fragment(segment):
    if not re.search(r"\d", segment) or len(re.findall(r"[a-z]", segment)) < 3:
        return False
    stem = re.match(r"[a-z]+", segment)
    return not (stem and stem.group(0) in _NAMED_STEMS and re.fullmatch(r"[a-z]+\d+", segment))


def fragments(runs_by_source):
    found = []
    for source, runs in runs_by_source.items():
        for run in runs:
            for path in _DEV_PATH.findall(run):
                for segment in _SEGMENT.findall(path.lower()):
                    if _fragment(segment):
                        found.append(f"{source}: {path}")
    return sorted(set(found))


def test_the_sweep_flags_a_token_fragment_and_passes_a_named_stem():
    runs = {"x": ["dev/media-spike/captures/518-fixture-share-file-ab3cd9ef-link.json"],
            "y": ["dev/ld514-dogfood4-folder-cleanup/captures/x.json"]}
    assert fragments(runs) == ["x: dev/media-spike/captures/518-fixture-share-file-ab3cd9ef-link.json"]


def test_no_cited_maintainers_path_carries_a_token_fragment():
    assert fragments(corpus()) == []
