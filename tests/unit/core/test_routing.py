from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from multiagent.config.agents import RouterConfig
from multiagent.core.routing import KeywordRouter, LLMRouter, build_router
from multiagent.exceptions import ConfigurationError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from multiagent.config.settings import Settings


def _keyword_config(
    routes: dict[str, list[str]] | None = None,
    default: str = "human",
) -> RouterConfig:
    """Helper to build a keyword RouterConfig."""
    return RouterConfig(
        name="test_router",
        type="keyword",
        routes=routes or {"writer": ["WRITER BRIEF", "END BRIEF"]},
        default=default,
    )


class TestKeywordRouter:
    def test_routes_to_first_matching_destination(self) -> None:
        router = KeywordRouter(_keyword_config())
        assert router.route("Here is the WRITER BRIEF for you") == "writer"

    def test_routes_to_default_when_no_match(self) -> None:
        router = KeywordRouter(_keyword_config())
        assert router.route("Just a normal conversation") == "human"

    def test_first_match_wins_when_multiple_triggers_present(self) -> None:
        config = _keyword_config(
            routes={
                "writer": ["BRIEF"],
                "editor": ["REVIEW"],
            }
        )
        router = KeywordRouter(config)
        # Both present — first defined destination wins
        assert router.route("BRIEF and REVIEW both here") == "writer"

    def test_empty_trigger_list_never_matches(self) -> None:
        config = _keyword_config(
            routes={
                "writer": ["BRIEF"],
                "editor": [],
            },
            default="human",
        )
        router = KeywordRouter(config)
        # "editor" has empty triggers — should never match, fall to default
        assert router.route("No triggers here") == "human"


class TestLLMRouter:
    @pytest.fixture
    def llm_config(self) -> RouterConfig:
        return RouterConfig(
            name="test_llm_router",
            type="llm",
            routes={"writer": ["writer"], "human": ["human"]},
            default="human",
            prompt_path=Path("nonexistent.md"),
            model="",
        )

    @pytest.mark.asyncio
    async def test_routes_to_recognised_key(
        self,
        llm_config: RouterConfig,
        test_settings: Settings,
        mocker: MockerFixture,
    ) -> None:
        from langchain_core.messages import AIMessage

        mock = AsyncMock(return_value=AIMessage(content="writer"))
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock)

        router = LLMRouter(llm_config, test_settings)
        result = await router.route("Some agent output")
        assert result == "writer"

    @pytest.mark.asyncio
    async def test_falls_back_to_default_on_unrecognised_key(
        self,
        llm_config: RouterConfig,
        test_settings: Settings,
        mocker: MockerFixture,
    ) -> None:
        from langchain_core.messages import AIMessage

        mock = AsyncMock(return_value=AIMessage(content="nonsense"))
        mocker.patch("langchain_openai.ChatOpenAI.ainvoke", side_effect=mock)

        router = LLMRouter(llm_config, test_settings)
        result = await router.route("Some agent output")
        assert result == "human"

    @pytest.mark.asyncio
    async def test_uses_override_model_when_specified(
        self,
        test_settings: Settings,
        mocker: MockerFixture,
    ) -> None:
        config = RouterConfig(
            name="model_test",
            type="llm",
            routes={"writer": ["writer"]},
            default="human",
            prompt_path=Path("nonexistent.md"),
            model="anthropic/claude-haiku-4-5",
        )

        mock_init = mocker.patch(
            "multiagent.core.routing.ChatOpenAI",
            return_value=AsyncMock(),
        )

        LLMRouter(config, test_settings)

        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-haiku-4-5"


class TestBuildRouter:
    def test_builds_keyword_router_for_keyword_type(
        self, test_settings: Settings
    ) -> None:
        config = _keyword_config()
        router = build_router(config, test_settings)
        assert isinstance(router, KeywordRouter)

    def test_builds_llm_router_for_llm_type(
        self, test_settings: Settings
    ) -> None:
        config = RouterConfig(
            name="llm_test",
            type="llm",
            routes={"writer": ["writer"]},
            default="human",
        )
        router = build_router(config, test_settings)
        assert isinstance(router, LLMRouter)

    def test_raises_configuration_error_for_unknown_type(
        self, test_settings: Settings
    ) -> None:
        config = RouterConfig(
            name="bad_router",
            type="magic",
            routes={},
            default="human",
        )
        with pytest.raises(ConfigurationError, match="Unknown router type"):
            build_router(config, test_settings)
