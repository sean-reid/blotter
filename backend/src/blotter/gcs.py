import shutil
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
        log.info("uploaded to storage", path=gcs_path, size_mb=round(local_path.stat().st_size / 1e6, 1))
        return str(dest)

    def download(self, gcs_path: str, local_path: Path) -> Path:
        src = self._base / gcs_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != local_path.resolve():
            shutil.copy2(src, local_path)
        return local_path

    def signed_url(self, gcs_path: str, expiration_hours: int = 24) -> str:
        return f"/api/audio/{gcs_path}"

    def delete(self, gcs_path: str) -> None:
        path = self._base / gcs_path
        path.unlink(missing_ok=True)
        log.info("deleted from storage", path=gcs_path)

    def exists(self, gcs_path: str) -> bool:
        return (self._base / gcs_path).exists()


def get_storage(config: GCSConfig) -> LocalStorageClient:
    log.info("using local storage", base_dir=config.local_dir)
    return LocalStorageClient(config.local_dir)
