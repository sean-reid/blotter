from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BroadcastifyConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BROADCASTIFY_")

    api_key: str
    username: str
    base_url: str = "https://api.broadcastify.com/calls"
    rate_limit_rps: float = 1.0


class ClickHouseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")

    host: str = "localhost"
    port: int = 8123
    database: str = "blotter"
    username: str = "default"
    password: str = ""


class NominatimConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOMINATIM_")

    url: str = "http://localhost:8080"
    viewbox: str = "-122.2,37.5,-121.2,36.9"
    bounded: bool = True
    country_codes: str = "us"


class TranscriptionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRANSCRIPTION_")

    model_size: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    beam_size: int = 10
    language: str = "en"
    vad_filter: bool = True
    vad_min_silence_ms: int = 500
    vad_speech_pad_ms: int = 200


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    feed_ids: list[str] = Field(default_factory=list)
    data_dir: str = "data"

    broadcastify: BroadcastifyConfig = Field(default_factory=BroadcastifyConfig)
    clickhouse: ClickHouseConfig = Field(default_factory=ClickHouseConfig)
    nominatim: NominatimConfig = Field(default_factory=NominatimConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)


def get_settings() -> Settings:
    return Settings()
