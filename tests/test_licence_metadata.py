"""LD-683 — the package is Apache-2.0, declared as an SPDX expression with its licence file (D-120).

The build is the one ``front_door.packaging_artifacts()`` already pays for; nothing here shells
out to ``python -m build`` again (LD-221's one-build-site rule).
"""
import hashlib
import tarfile
import zipfile

import front_door

#: sha256 of https://www.apache.org/licenses/LICENSE-2.0.txt as fetched 2026-10-31. A hash, not a
#: copy: the root ``LICENSE`` must be the licence text unmodified, and a hash says so without a
#: second copy of 11 KB to keep in step.
APACHE_2_0_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_the_root_licence_file_is_the_apache_2_0_text_unmodified():
    data = (front_door.REPO_ROOT / "LICENSE").read_bytes()
    assert hashlib.sha256(data).hexdigest() == APACHE_2_0_SHA256


def test_pyproject_declares_an_spdx_expression_and_the_file():
    project = front_door.pyproject()["project"]
    assert project["license"] == "Apache-2.0", "a plain SPDX string, not the deprecated table form"
    assert project["license-files"] == ["LICENSE"]


def test_the_build_backend_floor_supports_spdx_license_expressions():
    requires = front_door.pyproject()["build-system"]["requires"]
    setuptools = [r for r in requires if r.replace(" ", "").startswith("setuptools")]
    assert setuptools == ["setuptools>=77.0"], (
        "PEP 639 license expressions need setuptools 77; an older floor builds with a "
        f"deprecation warning or not at all: {requires}")


def test_the_wheel_metadata_carries_the_expression_and_the_file():
    _, wheel = front_door.packaging_artifacts()
    headers = front_door.metadata_headers(front_door.wheel_metadata(wheel))
    assert headers.get("License-Expression") == ["Apache-2.0"]
    assert headers.get("License-File") == ["LICENSE"]
    assert "License" not in headers, "the legacy free-text License header must be gone"
    with zipfile.ZipFile(wheel) as archive:
        licences = [n for n in archive.namelist() if n.endswith(".dist-info/licenses/LICENSE")]
        assert len(licences) == 1
        assert hashlib.sha256(archive.read(licences[0])).hexdigest() == APACHE_2_0_SHA256


def test_the_sdist_carries_the_licence_file():
    sdist, _ = front_door.packaging_artifacts()
    with tarfile.open(sdist) as archive:
        names = [m for m in archive.getmembers() if m.name.count("/") == 1 and m.name.endswith("/LICENSE")]
        assert len(names) == 1
        data = archive.extractfile(names[0]).read()
    assert hashlib.sha256(data).hexdigest() == APACHE_2_0_SHA256
