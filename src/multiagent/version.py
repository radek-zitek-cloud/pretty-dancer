"""Semantic version parsing, bumping, and pyproject.toml management."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z\-.]+))?$"
)

_PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*")[^"]+(")', re.MULTILINE)


class BumpPart(Enum):
    """Which part of a SemVer string to increment."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


@dataclass(frozen=True)
class SemVer:
    """An immutable Semantic Version value.

    Attributes:
        major: Major version number.
        minor: Minor version number.
        patch: Patch version number.
        prerelease: Optional prerelease label (e.g. ``"alpha.1"``).
    """

    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    def __str__(self) -> str:
        """Return the canonical SemVer string."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            return f"{base}-{self.prerelease}"
        return base

    def bump(self, part: BumpPart) -> SemVer:
        """Return a new ``SemVer`` with *part* incremented.

        Bumping major resets minor and patch to 0.
        Bumping minor resets patch to 0.
        All bumps clear the prerelease label.

        Args:
            part: Which component to increment.
        """
        if part is BumpPart.MAJOR:
            return SemVer(self.major + 1, 0, 0)
        if part is BumpPart.MINOR:
            return SemVer(self.major, self.minor + 1, 0)
        return SemVer(self.major, self.minor, self.patch + 1)


def parse_version(version_str: str) -> SemVer:
    """Parse a SemVer string into a ``SemVer`` instance.

    Args:
        version_str: A string like ``"1.2.3"`` or ``"0.2.0-alpha.1"``.

    Raises:
        ValueError: If *version_str* does not match SemVer 2.0.0.
    """
    m = _VERSION_RE.match(version_str)
    if not m:
        msg = f"Invalid SemVer string: {version_str!r}"
        raise ValueError(msg)
    return SemVer(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        prerelease=m.group("prerelease"),
    )


def _default_pyproject_path() -> Path:
    """Return the pyproject.toml path at the project root."""
    return Path(__file__).resolve().parents[2] / "pyproject.toml"


def read_pyproject_version(pyproject_path: Path | None = None) -> str:
    """Read the ``version`` field from a pyproject.toml file.

    Args:
        pyproject_path: Path to pyproject.toml. Defaults to the project root.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If no ``version = "..."`` line is found.
    """
    path = pyproject_path or _default_pyproject_path()
    content = path.read_text(encoding="utf-8")
    m = _PYPROJECT_VERSION_RE.search(content)
    if not m:
        msg = f"No version field found in {path}"
        raise ValueError(msg)
    # Extract the version string between the quotes
    full_match = m.group(0)
    return full_match.split('"')[1]


def write_pyproject_version(pyproject_path: Path, new_version: str) -> None:
    """Replace the ``version`` field in a pyproject.toml file.

    Args:
        pyproject_path: Path to pyproject.toml.
        new_version: The new version string to write.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If no ``version = "..."`` line is found.
    """
    content = pyproject_path.read_text(encoding="utf-8")
    new_content, count = _PYPROJECT_VERSION_RE.subn(rf'\g<1>{new_version}\2', content)
    if count == 0:
        msg = f"No version field found in {pyproject_path}"
        raise ValueError(msg)
    pyproject_path.write_text(new_content, encoding="utf-8")


def bump_in_pyproject(part_name: str, pyproject_path: Path | None = None) -> str:
    """Bump the version in pyproject.toml and return the new version string.

    Args:
        part_name: One of ``"major"``, ``"minor"``, or ``"patch"``.
        pyproject_path: Path to pyproject.toml. Defaults to the project root.

    Returns:
        The new version string after bumping.

    Raises:
        ValueError: If *part_name* is not a valid bump part.
    """
    path = pyproject_path or _default_pyproject_path()
    current = read_pyproject_version(path)
    sem = parse_version(current)
    part = BumpPart(part_name)
    new_sem = sem.bump(part)
    new_version = str(new_sem)
    write_pyproject_version(path, new_version)
    return new_version
