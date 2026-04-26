import os

from blotter.config import BroadcastifyConfig, ClickHouseConfig, Settings


class TestClickHouseConfig:
    def test_defaults(self):
        config = ClickHouseConfig()
        assert config.host == "localhost"
        assert config.port == 8123
        assert config.database == "blotter"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CLICKHOUSE_HOST", "db.example.com")
        monkeypatch.setenv("CLICKHOUSE_PORT", "9000")
        config = ClickHouseConfig()
        assert config.host == "db.example.com"
        assert config.port == 9000


class TestBroadcastifyConfig:
    def test_requires_credentials(self, monkeypatch):
        monkeypatch.setenv("BROADCASTIFY_API_KEY", "test_key")
        monkeypatch.setenv("BROADCASTIFY_USERNAME", "test_user")
        config = BroadcastifyConfig()
        assert config.api_key == "test_key"
        assert config.rate_limit_rps == 1.0
