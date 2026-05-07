import os

from blotter.config import PostgresConfig, Settings


class TestPostgresConfig:
    def test_defaults(self):
        config = PostgresConfig()
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "blotter"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_HOST", "db.example.com")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        config = PostgresConfig()
        assert config.host == "db.example.com"
        assert config.port == 5433

    def test_conninfo(self):
        config = PostgresConfig(host="myhost", port=5433, database="mydb", user="myuser", password="mypass")
        assert "host=myhost" in config.conninfo
        assert "port=5433" in config.conninfo
        assert "dbname=mydb" in config.conninfo
