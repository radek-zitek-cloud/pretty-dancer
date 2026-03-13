from pathlib import Path

import pytest

from multiagent.config.agents import load_agents_config
from multiagent.exceptions import InvalidConfigurationError

FIXTURE_PATH = Path("tests/fixtures/agents.toml")


class TestLoadAgentsConfig:
    def test_loads_researcher_and_critic(self) -> None:
        configs = load_agents_config(FIXTURE_PATH)
        assert "researcher" in configs
        assert "critic" in configs
        assert len(configs) == 2

    def test_researcher_next_agent_is_critic(self) -> None:
        configs = load_agents_config(FIXTURE_PATH)
        assert configs["researcher"].next_agent == "critic"

    def test_critic_next_agent_is_none(self) -> None:
        configs = load_agents_config(FIXTURE_PATH)
        assert configs["critic"].next_agent is None

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(InvalidConfigurationError, match="not found"):
            load_agents_config(Path("nonexistent/agents.toml"))

    def test_raises_on_invalid_toml(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("this is [not valid", encoding="utf-8")
        with pytest.raises(InvalidConfigurationError, match="not valid TOML"):
            load_agents_config(bad_file)

    def test_raises_when_agents_table_absent(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.toml"
        empty_file.write_text('[other]\nkey = "value"\n', encoding="utf-8")
        with pytest.raises(InvalidConfigurationError, match="\\[agents\\] table"):
            load_agents_config(empty_file)

    def test_returns_frozen_dataclasses(self) -> None:
        configs = load_agents_config(FIXTURE_PATH)
        with pytest.raises(AttributeError):
            configs["researcher"].name = "changed"  # type: ignore[misc]

    def test_agent_names_match_section_keys(self) -> None:
        configs = load_agents_config(FIXTURE_PATH)
        for name, config in configs.items():
            assert config.name == name
