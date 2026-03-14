"""Implementation of the ``multiagent version`` command."""

from __future__ import annotations

import typer

from multiagent import __version__


def version_command() -> None:
    """Show the current package version."""
    typer.echo(__version__)
