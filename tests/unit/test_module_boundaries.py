"""Programmatic enforcement of module dependency boundaries.

These tests verify that the absolute import rules documented in the
implementation guide are not violated. They use subprocess grep to
scan the source tree — no runtime import introspection.
"""

from __future__ import annotations

import subprocess


class TestModuleBoundaries:
    def test_core_does_not_import_transport(self) -> None:
        """core/ must never have runtime imports from transport/."""
        result = subprocess.run(
            [
                "grep", "-rn",
                "--include=*.py",
                "from multiagent.transport",
                "src/multiagent/core/",
            ],
            capture_output=True,
            text=True,
        )
        # Filter out TYPE_CHECKING-guarded imports (indented lines)
        violations = [
            line for line in result.stdout.strip().splitlines()
            if line and not line.split(":", 2)[-1].startswith("    ")
        ]
        assert violations == [], (
            "core/ has runtime imports from transport/:\n"
            + "\n".join(violations)
        )

    def test_transport_does_not_import_core(self) -> None:
        """transport/ must never import from core/."""
        result = subprocess.run(
            [
                "grep", "-rn",
                "--include=*.py",
                "from multiagent.core",
                "src/multiagent/transport/",
            ],
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "", (
            f"transport/ imports from core/:\n{result.stdout}"
        )
