import shutil
from datetime import timedelta
from pathlib import Path

from blotter.config import GCSConfig
from blotter.log import get_logger

log = get_logger(__name__)


class LocalStorageClient:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: Path, gcs_path: str) -> str:
        dest = self._base / gcs_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if local_path.resolve() != dest.resolve():
            shutil.copy2(local_path, dest)
        log.info("stored locally", path=str(dest), size_mb=round(local_path.stat().st_size / 1e6, 1))
        return str(dest)

    def download(self, gcs_path: str, local_path: Path) -> Path:
        src = self._base / gcs_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != local_path.resolve():
            shutil.copy2(src, local_path)
        return local_path

    def public_url(self, gcs_path: str) -> str:
        return f"/audio-data/stream/{gcs_path}"

    def signed_url(self, gcs_path: str, expiration_hours: int = 24) -> str:
        return self.public_url(gcs_path)

    def delete(self, gcs_path: str) -> None:
        path = self._base / gcs_path
        path.unlink(missing_ok=True)

    def exists(self, gcs_path: str) -> bool:
        return (self._base / gcs_path).exists()


class GCSClient:
    def __init__(self, config: GCSConfig) -> None:
        from google.cloud import storage
        self._client = storage.Client(project=config.project or None)
        self._bucket = self._client.bucket(config.bucket)

    def upload(self, local_path: Path, gcs_path: str) -> str:
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_filename(str(local_path))
        log.info("uploaded to gcs", path=gcs_path, size_mb=round(local_path.stat().st_size / 1e6, 1))
        return f"gs://{self._bucket.name}/{gcs_path}"

    def download(self, gcs_path: str, local_path: Path) -> Path:
        blob = self._bucket.blob(gcs_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))
        return local_path

    def public_url(self, gcs_path: str) -> str:
        return f"https://storage.googleapis.com/{self._bucket.name}/{gcs_path}"

    def signed_url(self, gcs_path: str, expiration_hours: int = 24) -> str:
        blob = self._bucket.blob(gcs_path)
        return blob.generate_signed_url(expiration=timedelta(hours=expiration_hours))

    def delete(self, gcs_path: str) -> None:
        blob = self._bucket.blob(gcs_path)
        blob.delete()
        log.info("deleted from gcs", path=gcs_path)

    def exists(self, gcs_path: str) -> bool:
        return self._bucket.blob(gcs_path).exists()


def get_storage(config: GCSConfig) -> LocalStorageClient | GCSClient:
    if not config.project:
        log.info("using local storage", base_dir=config.local_dir)
        return LocalStorageClient(config.local_dir)
    return GCSClient(config)
