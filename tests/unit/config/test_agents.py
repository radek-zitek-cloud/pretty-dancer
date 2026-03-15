from pathlib import Path

import pytest

from multiagent.config.agents import AgentsConfig, load_agents_config, resolve_experiment_path
from multiagent.exceptions import InvalidConfigurationError

FIXTURE_PATH = Path("tests/fixtures/agents.toml")


class TestLoadAgentsConfig:
    def test_loads_researcher_and_critic(self) -> None:
        result = load_agents_config(FIXTURE_PATH)
        assert "researcher" in result.agents
        assert "critic" in result.agents
        assert len(result.agents) == 2

    def test_returns_agents_config(self) -> None:
        result = load_agents_config(FIXTURE_PATH)
        assert isinstance(result, AgentsConfig)

    def test_researcher_next_agent_is_critic(self) -> None:
        result = load_agents_config(FIXTURE_PATH)
        assert result.agents["researcher"].next_agent == "critic"

    def test_critic_next_agent_is_none(self) -> None:
        result = load_agents_config(FIXTURE_PATH)
        assert result.agents["critic"].next_agent is None

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
        result = load_agents_config(FIXTURE_PATH)
        with pytest.raises(AttributeError):
            result.agents["researcher"].name = "changed"  # type: ignore[misc]

    def test_agent_names_match_section_keys(self) -> None:
        result = load_agents_config(FIXTURE_PATH)
        for name, config in result.agents.items():
            assert config.name == name


class TestRouterConfig:
    def test_loads_router_sections_from_toml(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "agents.toml"
        toml_file.write_text(
            '[agents.editor]\nrouter = "test_gate"\n\n'
            '[routers.test_gate]\n'
            'type = "keyword"\n'
            'routes.writer = ["BRIEF"]\n'
            'default = "human"\n',
            encoding="utf-8",
        )
        result = load_agents_config(toml_file)
        assert "test_gate" in result.routers
        router = result.routers["test_gate"]
        assert router.type == "keyword"
        assert router.routes == {"writer": ["BRIEF"]}
        assert router.default == "human"
        assert router.name == "test_gate"

    def test_raises_when_agent_has_both_next_agent_and_router(
        self, tmp_path: Path
    ) -> None:
        toml_file = tmp_path / "agents.toml"
        toml_file.write_text(
            '[agents.editor]\nnext_agent = "writer"\nrouter = "gate"\n',
            encoding="utf-8",
        )
        with pytest.raises(
            InvalidConfigurationError, match="mutually exclusive"
        ):
            load_agents_config(toml_file)

    def test_backward_compatible_next_agent_still_works(self) -> None:
        result = load_agents_config(FIXTURE_PATH)
        assert result.agents["researcher"].next_agent == "critic"
        assert result.agents["researcher"].router is None
        assert len(result.routers) == 0

    def test_router_without_type_raises(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "agents.toml"
        toml_file.write_text(
            '[agents.editor]\nrouter = "gate"\n\n'
            '[routers.gate]\n'
            'default = "human"\n',
            encoding="utf-8",
        )
        with pytest.raises(
            InvalidConfigurationError, match="must have a 'type' field"
        ):
            load_agents_config(toml_file)

    def test_loads_llm_router_with_prompt_and_model(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "agents.toml"
        toml_file.write_text(
            '[agents.editor]\nrouter = "gate"\n\n'
            '[routers.gate]\n'
            'type = "llm"\n'
            'prompt = "prompts/routers/gate.md"\n'
            'model = "anthropic/claude-haiku-4-5"\n'
            'routes.writer = "writer"\n'
            'routes.human = "human"\n'
            'default = "human"\n',
            encoding="utf-8",
        )
        result = load_agents_config(toml_file)
        router = result.routers["gate"]
        assert router.type == "llm"
        assert router.prompt_path == Path("prompts/routers/gate.md")
        assert router.model == "anthropic/claude-haiku-4-5"
        assert router.routes == {"writer": ["writer"], "human": ["human"]}


class TestAgentTools:
    def test_loads_tools_field_from_toml(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "agents.toml"
        toml_file.write_text(
            '[agents.researcher]\n'
            'next_agent = "critic"\n'
            'tools = ["exa", "filesystem"]\n',
            encoding="utf-8",
        )
        result = load_agents_config(toml_file)
        assert result.agents["researcher"].tools == ["exa", "filesystem"]

    def test_tools_defaults_to_empty_list_when_absent(self) -> None:
        result = load_agents_config(FIXTURE_PATH)
        assert result.agents["researcher"].tools == []
        assert result.agents["critic"].tools == []


class TestExperimentConfigResolution:
    def test_resolves_experiment_config_path_correctly(
        self, tmp_path: Path
    ) -> None:
        exp_file = tmp_path / "agents.research-desk.toml"
        exp_file.write_text(
            '[agents.supervisor]\nrouter = "gate"\n',
            encoding="utf-8",
        )
        result = resolve_experiment_path(
            tmp_path / "agents.toml", "research-desk", "config"
        )
        assert result == exp_file

    def test_raises_when_experiment_config_missing(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(
            InvalidConfigurationError, match="Experiment config not found"
        ):
            resolve_experiment_path(
                tmp_path / "agents.toml", "nonexistent", "config"
            )

    def test_returns_default_path_when_no_experiment(
        self, tmp_path: Path
    ) -> None:
        base = tmp_path / "agents.toml"
        result = resolve_experiment_path(base, "", "config")
        assert result == base

    def test_loads_experiment_agents_config(self, tmp_path: Path) -> None:
        exp_file = tmp_path / "agents.research-desk.toml"
        exp_file.write_text(
            '[agents.supervisor]\n',
            encoding="utf-8",
        )
        result = load_agents_config(
            tmp_path / "agents.toml", experiment="research-desk"
        )
        assert "supervisor" in result.agents
