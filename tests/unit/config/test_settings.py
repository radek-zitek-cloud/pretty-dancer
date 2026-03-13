import pytest
from pydantic import ValidationError

from multiagent.config.settings import Settings


class TestSettingsDefaults:
    def test_default_greeting_message_is_set(self, test_settings: Settings) -> None:
        assert test_settings.greeting_message == "Hello from test config"


class TestSettingsValidation:
    def test_invalid_app_env_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                greeting_secret="secret",  # type: ignore[call-arg]
                openrouter_api_key="test-key",  # type: ignore[call-arg]
                app_env="staging",  # type: ignore[call-arg]
            )

    def test_extra_field_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                greeting_secret="secret",  # type: ignore[call-arg]
                openrouter_api_key="test-key",  # type: ignore[call-arg]
                unknown_extra_field="value",  # type: ignore[call-arg]
            )


class TestSettingsRequired:
    def test_missing_greeting_secret_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,  # type: ignore[call-arg]
            )


class TestObservabilitySettings:
    def test_log_console_enabled_defaults_to_true(self, test_settings: Settings) -> None:
        assert test_settings.log_console_enabled is True

    def test_log_console_level_defaults_to_info(self) -> None:
        s = Settings(
            greeting_secret="secret",  # type: ignore[call-arg]
            openrouter_api_key="test-key",  # type: ignore[call-arg]
        )
        assert s.log_console_level == "INFO"

    def test_log_human_file_enabled_defaults_to_false(self, test_settings: Settings) -> None:
        assert test_settings.log_human_file_enabled is False

    def test_log_human_file_level_defaults_to_info(self) -> None:
        s = Settings(
            greeting_secret="secret",  # type: ignore[call-arg]
            openrouter_api_key="test-key",  # type: ignore[call-arg]
        )
        assert s.log_human_file_level == "INFO"

    def test_log_json_file_enabled_defaults_to_false(self, test_settings: Settings) -> None:
        assert test_settings.log_json_file_enabled is False

    def test_log_json_file_level_defaults_to_debug(self) -> None:
        s = Settings(
            greeting_secret="secret",  # type: ignore[call-arg]
            openrouter_api_key="test-key",  # type: ignore[call-arg]
        )
        assert s.log_json_file_level == "DEBUG"

    def test_log_trace_llm_defaults_to_false(self, test_settings: Settings) -> None:
        assert test_settings.log_trace_llm is False

    def test_experiment_defaults_to_empty_string(self) -> None:
        s = Settings(
            greeting_secret="secret",  # type: ignore[call-arg]
            openrouter_api_key="test-key",  # type: ignore[call-arg]
        )
        assert s.experiment == ""
