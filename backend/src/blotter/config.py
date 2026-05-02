from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClickHouseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")

    host: str = "localhost"
    port: int = 8123
    database: str = "blotter"
    username: str = "default"
    password: str = ""


class RegionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REGION_", env_file=".env", extra="ignore")

    name: str = "Los Angeles"
    state: str = "CA"
    bbox_south: float = 33.7
    bbox_west: float = -118.95
    bbox_north: float = 34.35
    bbox_east: float = -117.65

    @property
    def location_suffix(self) -> str:
        return f"{self.name}, {self.state}" if self.state else self.name

    @property
    def places_bias(self) -> str:
        return f"rectangle:{self.bbox_south},{self.bbox_west}|{self.bbox_north},{self.bbox_east}"


class GoogleGeocodingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOOGLE_GEOCODING_", env_file=".env", extra="ignore")

    api_key: str = ""


class GoogleNLPConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOOGLE_NLP_", env_file=".env", extra="ignore")

    api_key: str = ""


class TranscriptionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRANSCRIPTION_", env_file=".env", extra="ignore")

    model_size: str = "large-v3-turbo"
    device: str = "cuda"
    compute_type: str = "float16"
    beam_size: int = 10
    language: str = "en"
    vad_filter: bool = True
    vad_min_silence_ms: int = 500
    vad_speech_pad_ms: int = 200
    no_speech_threshold: float = 0.75
    condition_on_previous_text: bool = False
    prompt_file: str = ""


class GCSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GCS_", env_file=".env", extra="ignore")

    bucket: str = "blotter-audio"
    project: str = ""
    local_dir: str = "data/stream"


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=".env", extra="ignore")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""


class OpenMhzConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENMHZ_", env_file=".env", extra="ignore")

    api_url: str = "https://api.openmhz.com"
    systems: str = "lapdvalley,lapdwest"
    poll_interval: int = 10


class StreamConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STREAM_", env_file=".env", extra="ignore")

    segment_time: int = 300
    overlap_seconds: int = 5
    ad_skip_seconds: int = 35
    reconnect_delay: int = 5
    reconnect_max_delay: int = 300
    reconnect_max_failures: int = 10
    chunk_dir: str = "/tmp/blotter"

    feeds: str = "20296:LAPD South Bureau,33623:LAPD West Bureau,26569:LAPD Valley Bureau,40488:LAPD Hotshot,25187:LASD Multi-Dispatch,24051:Long Beach PD"

    def get_feeds(self) -> dict[str, str]:
        result = {}
        for entry in self.feeds.split(","):
            entry = entry.strip()
            if ":" in entry:
                fid, name = entry.split(":", 1)
                result[fid.strip()] = name.strip()
        return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: str = "data"

    region: RegionConfig = Field(default_factory=RegionConfig)
    clickhouse: ClickHouseConfig = Field(default_factory=ClickHouseConfig)
    google_geocoding: GoogleGeocodingConfig = Field(default_factory=GoogleGeocodingConfig)
    google_nlp: GoogleNLPConfig = Field(default_factory=GoogleNLPConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    gcs: GCSConfig = Field(default_factory=GCSConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    stream: StreamConfig = Field(default_factory=StreamConfig)
    openmhz: OpenMhzConfig = Field(default_factory=OpenMhzConfig)


def get_settings() -> Settings:
    return Settings()
