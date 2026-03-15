"""Tests for cluster path derivation functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from multiagent.config.settings import (
    Settings,
    agents_config_path,
    cluster_dir,
    mcp_secrets_path,
    prompts_dir,
)
from multiagent.exceptions import InvalidConfigurationError


def _make_settings(tmp_path: Path, cluster: str = "") -> Settings:
    """Create a Settings instance with clusters_dir under tmp_path."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        greeting_secret="secret",  # type: ignore[call-arg]
        openrouter_api_key="test-key",  # type: ignore[call-arg]
        clusters_dir=tmp_path / "clusters",  # type: ignore[call-arg]
        cluster=cluster,  # type: ignore[call-arg]
    )


class TestClusterPathDerivation:
    def test_default_cluster_loads_from_clusters_default(
        self, tmp_path: Path
    ) -> None:
        """Empty cluster → clusters/default/agents.toml."""
        clusters = tmp_path / "clusters" / "default"
        clusters.mkdir(parents=True)
        (clusters / "agents.toml").write_text(
            "[agents.alfa]\n", encoding="utf-8"
        )
        settings = _make_settings(tmp_path, cluster="")
        path = agents_config_path(settings)
        assert path == clusters / "agents.toml"

    def test_named_cluster_loads_from_clusters_subdir(
        self, tmp_path: Path
    ) -> None:
        """Named cluster → clusters/{name}/agents.toml."""
        clusters = tmp_path / "clusters" / "research-desk"
        clusters.mkdir(parents=True)
        (clusters / "agents.toml").write_text(
            "[agents.supervisor]\n", encoding="utf-8"
        )
        settings = _make_settings(tmp_path, cluster="research-desk")
        path = agents_config_path(settings)
        assert path == clusters / "agents.toml"

    def test_raises_when_cluster_dir_missing(
        self, tmp_path: Path
    ) -> None:
        """Missing cluster directory raises ConfigurationError."""
        settings = _make_settings(tmp_path, cluster="nonexistent")
        with pytest.raises(
            InvalidConfigurationError, match="Cluster config not found"
        ):
            agents_config_path(settings)

    def test_secrets_falls_back_to_default_cluster(
        self, tmp_path: Path
    ) -> None:
        """Named cluster without secrets falls back to default secrets."""
        default_dir = tmp_path / "clusters" / "default"
        default_dir.mkdir(parents=True)
        (default_dir / "agents.mcp.secrets.json").write_text(
            '{"mcpServers": {}}', encoding="utf-8"
        )

        named_dir = tmp_path / "clusters" / "research-desk"
        named_dir.mkdir(parents=True)
        # No secrets file in named cluster

        settings = _make_settings(tmp_path, cluster="research-desk")
        result = mcp_secrets_path(settings)
        assert result == default_dir / "agents.mcp.secrets.json"

    def test_cluster_dir_returns_correct_path(
        self, tmp_path: Path
    ) -> None:
        settings = _make_settings(tmp_path, cluster="research-desk")
        assert cluster_dir(settings) == tmp_path / "clusters" / "research-desk"

    def test_prompts_dir_returns_cluster_prompts(
        self, tmp_path: Path
    ) -> None:
        settings = _make_settings(tmp_path, cluster="research-desk")
        assert prompts_dir(settings) == tmp_path / "clusters" / "research-desk" / "prompts"

    def test_secrets_returns_none_when_no_secrets_anywhere(
        self, tmp_path: Path
    ) -> None:
        """No secrets files at all returns None."""
        settings = _make_settings(tmp_path, cluster="research-desk")
        result = mcp_secrets_path(settings)
        assert result is None
