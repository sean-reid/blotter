import shutil
from datetime import timedelta
from pathlib import Path

import httpx

from blotter.config import GCSConfig
from blotter.log import get_logger

log = get_logger(__name__)

_GCS_UPLOAD_URL = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
_GCS_OBJECT_URL = "https://storage.googleapis.com/storage/v1/b/{bucket}/o/{object}?alt=media"


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

        self._config = config
        self._bucket_name = config.bucket

        self._storage_client = storage.Client(project=config.project or None)
        self._signing_bucket = self._storage_client.bucket(config.bucket)
        self._credentials = self._storage_client._credentials

        self._http = httpx.Client(timeout=30)

        from google.auth.transport.requests import Request
        self._auth_request = Request()

    def _auth_headers(self) -> dict[str, str]:
        if not self._credentials.valid:
            self._credentials.refresh(self._auth_request)
        return {"Authorization": f"Bearer {self._credentials.token}"}

    def upload(self, local_path: Path, gcs_path: str) -> str:
        data = local_path.read_bytes()
        resp = self._http.post(
            _GCS_UPLOAD_URL.format(bucket=self._bucket_name),
            params={"uploadType": "media", "name": gcs_path},
            headers={**self._auth_headers(), "Content-Type": "audio/wav"},
            content=data,
        )
        resp.raise_for_status()
        log.info("uploaded to gcs", path=gcs_path, size_mb=round(len(data) / 1e6, 1))
        return f"gs://{self._bucket_name}/{gcs_path}"

    def download(self, gcs_path: str, local_path: Path) -> Path:
        from urllib.parse import quote
        local_path.parent.mkdir(parents=True, exist_ok=True)
        resp = self._http.get(
            _GCS_OBJECT_URL.format(bucket=self._bucket_name, object=quote(gcs_path, safe="")),
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        local_path.write_bytes(resp.content)
        return local_path

    def public_url(self, gcs_path: str) -> str:
        return f"https://storage.googleapis.com/{self._bucket_name}/{gcs_path}"

    def signed_url(self, gcs_path: str, expiration_hours: int = 24) -> str:
        blob = self._signing_bucket.blob(gcs_path)
        return blob.generate_signed_url(
            expiration=timedelta(hours=expiration_hours),
            response_type="audio/wav",
        )

    def delete(self, gcs_path: str) -> None:
        from urllib.parse import quote
        resp = self._http.delete(
            f"https://storage.googleapis.com/storage/v1/b/{self._bucket_name}/o/{quote(gcs_path, safe='')}",
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        log.info("deleted from gcs", path=gcs_path)

    def exists(self, gcs_path: str) -> bool:
        from urllib.parse import quote
        resp = self._http.get(
            f"https://storage.googleapis.com/storage/v1/b/{self._bucket_name}/o/{quote(gcs_path, safe='')}",
            headers=self._auth_headers(),
        )
        return resp.status_code == 200


def get_storage(config: GCSConfig) -> LocalStorageClient | GCSClient:
    if not config.project:
        log.info("using local storage", base_dir=config.local_dir)
        return LocalStorageClient(config.local_dir)
    return GCSClient(config)
