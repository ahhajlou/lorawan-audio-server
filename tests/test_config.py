import pytest

from config import load_env_variables


class TestConfig:
    def test_valid_log_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        settings = load_env_variables()
        assert settings.log_level == "DEBUG"

    def test_invalid_log_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "fdf")
        with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
            load_env_variables()

    def test_default_log_level(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.setattr("config.load_dotenv", lambda **kwargs: None)
        settings = load_env_variables()
        assert settings.log_level == "INFO"

    def test_all_valid_log_levels(self, monkeypatch):
        levels = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}

        for level in levels:
            monkeypatch.setenv("LOG_LEVEL", level)
            settings = load_env_variables()
            assert settings.log_level == level
