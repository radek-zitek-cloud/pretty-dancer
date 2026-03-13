import pytest
from pydantic import ValidationError

from multiagent.config.settings import Settings


class TestSettingsDefaults:
    def test_default_log_level_is_info(self, test_settings: Settings) -> None:
        assert test_settings.log_level == "INFO"

    def test_default_log_format_is_console(self, test_settings: Settings) -> None:
        assert test_settings.log_format == "console"

    def test_default_greeting_message_is_set(self, test_settings: Settings) -> None:
        assert test_settings.greeting_message == "Hello from test config"


class TestSettingsValidation:
    def test_invalid_log_level_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                greeting_secret="secret",  # type: ignore[call-arg]
                log_level="INVALID",  # type: ignore[call-arg]
            )

    def test_invalid_log_format_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                greeting_secret="secret",  # type: ignore[call-arg]
                log_format="yaml",  # type: ignore[call-arg]
            )

    def test_invalid_app_env_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                greeting_secret="secret",  # type: ignore[call-arg]
                app_env="staging",  # type: ignore[call-arg]
            )

    def test_extra_field_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                greeting_secret="secret",  # type: ignore[call-arg]
                unknown_extra_field="value",  # type: ignore[call-arg]
            )


class TestSettingsRequired:
    def test_missing_greeting_secret_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,  # type: ignore[call-arg]
            )
