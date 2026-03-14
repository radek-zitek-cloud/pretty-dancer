from __future__ import annotations

from pathlib import Path

import pytest

from multiagent.version import (
    BumpPart,
    SemVer,
    bump_in_pyproject,
    parse_version,
    read_pyproject_version,
    write_pyproject_version,
)

SAMPLE_PYPROJECT = """\
[project]
name = "example"
version = "1.2.3"
description = "A test project"
"""


class TestParseVersion:
    def test_simple(self):
        v = parse_version("1.2.3")
        assert v == SemVer(1, 2, 3)

    def test_zero_version(self):
        v = parse_version("0.1.0")
        assert v == SemVer(0, 1, 0)

    def test_with_prerelease(self):
        v = parse_version("0.2.0-alpha.1")
        assert v == SemVer(0, 2, 0, prerelease="alpha.1")

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid SemVer"):
            parse_version("not-a-version")

    def test_incomplete_raises(self):
        with pytest.raises(ValueError, match="Invalid SemVer"):
            parse_version("1.2")

    def test_leading_zeros_major_raises(self):
        with pytest.raises(ValueError, match="Invalid SemVer"):
            parse_version("01.2.3")


class TestSemVerStr:
    def test_without_prerelease(self):
        assert str(SemVer(1, 2, 3)) == "1.2.3"

    def test_with_prerelease(self):
        assert str(SemVer(1, 0, 0, prerelease="rc.1")) == "1.0.0-rc.1"


class TestSemVerBump:
    def test_bump_patch(self):
        assert SemVer(1, 2, 3).bump(BumpPart.PATCH) == SemVer(1, 2, 4)

    def test_bump_minor_resets_patch(self):
        assert SemVer(1, 2, 3).bump(BumpPart.MINOR) == SemVer(1, 3, 0)

    def test_bump_major_resets_minor_and_patch(self):
        assert SemVer(1, 2, 3).bump(BumpPart.MAJOR) == SemVer(2, 0, 0)

    def test_bump_clears_prerelease(self):
        v = SemVer(1, 0, 0, prerelease="alpha.1")
        assert v.bump(BumpPart.PATCH) == SemVer(1, 0, 1)
        assert v.bump(BumpPart.PATCH).prerelease is None


class TestReadWritePyprojectVersion:
    def test_read_version(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text(SAMPLE_PYPROJECT, encoding="utf-8")
        assert read_pyproject_version(f) == "1.2.3"

    def test_write_version(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text(SAMPLE_PYPROJECT, encoding="utf-8")
        write_pyproject_version(f, "2.0.0")
        assert read_pyproject_version(f) == "2.0.0"

    def test_write_preserves_other_content(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text(SAMPLE_PYPROJECT, encoding="utf-8")
        write_pyproject_version(f, "9.9.9")
        content = f.read_text(encoding="utf-8")
        assert 'name = "example"' in content
        assert 'description = "A test project"' in content

    def test_read_missing_version_raises(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text("[project]\nname = 'x'\n", encoding="utf-8")
        with pytest.raises(ValueError, match="No version field"):
            read_pyproject_version(f)

    def test_write_missing_version_raises(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text("[project]\nname = 'x'\n", encoding="utf-8")
        with pytest.raises(ValueError, match="No version field"):
            write_pyproject_version(f, "1.0.0")


class TestBumpInPyproject:
    def test_bump_patch(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text(SAMPLE_PYPROJECT, encoding="utf-8")
        result = bump_in_pyproject("patch", f)
        assert result == "1.2.4"
        assert read_pyproject_version(f) == "1.2.4"

    def test_bump_minor(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text(SAMPLE_PYPROJECT, encoding="utf-8")
        result = bump_in_pyproject("minor", f)
        assert result == "1.3.0"

    def test_bump_major(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text(SAMPLE_PYPROJECT, encoding="utf-8")
        result = bump_in_pyproject("major", f)
        assert result == "2.0.0"

    def test_invalid_part_raises(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text(SAMPLE_PYPROJECT, encoding="utf-8")
        with pytest.raises(ValueError):
            bump_in_pyproject("invalid", f)
