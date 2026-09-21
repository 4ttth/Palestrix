"""Object storage wiring.

One interface, two backends:
- LocalStorage: filesystem under PALESTRIX_STORAGE_LOCAL_ROOT (development).
- MinioStorage: MinIO or any S3-compatible endpoint (production; see
  docs/usecase-a-baremetal.md and usecase-b-cloud-aws.md).

Buckets are fixed: isos, lab-archives, writeups, sandbox-samples,
sandbox-reports, backups. The sandbox module is scoped to its own two
buckets only (docs/sandbox-security.md §What the sandbox module never gets).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

from .config import get_settings

BUCKETS = (
    "isos",
    "lab-archives",
    "writeups",
    "sandbox-samples",
    "sandbox-reports",
    "backups",
)

# Object-key alphabet. Keys are built from client-supplied filenames in
# several places (assignment attachments, lab archives, ISOs), so the
# sanitizer lives here, next to the backend that would otherwise follow a
# "../" out of its bucket.
_SAFE_KEY_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"


class StorageKeyError(ValueError):
    """A key that would escape its bucket, or a filename that cannot be
    reduced to one. Callers answer 4xx; this is client input, not a bug."""


def safe_filename(filename: str | None, *, fallback: str = "upload.bin") -> str:
    """One path segment from a client-supplied filename.

    Directory parts are dropped and everything outside the alphabet above
    becomes an underscore, so the result can never contain a separator or a
    "..". Used wherever an upload's own name becomes part of an object key.
    """
    base = PurePosixPath((filename or "").replace("\\", "/")).name
    cleaned = "".join(c if c in _SAFE_KEY_CHARS else "_" for c in base).lstrip(".")
    return cleaned[:128] or fallback


@dataclass
class StoredObject:
    key: str
    size: int
    last_modified: datetime | None = None


class Storage(Protocol):
    def put(self, bucket: str, key: str, data: BinaryIO, size: int) -> str: ...
    def get(self, bucket: str, key: str) -> bytes: ...
    def exists(self, bucket: str, key: str) -> bool: ...
    def list(self, bucket: str) -> list[StoredObject]: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        for bucket in BUCKETS:
            (self.root / bucket).mkdir(parents=True, exist_ok=True)

    def _path(self, bucket: str, key: str) -> Path:
        # Raised, not asserted: `python -O` strips assert statements, and an
        # escape check that vanishes under an optimization flag is not a
        # check. Both conditions are reachable from client input.
        if bucket not in BUCKETS:
            raise StorageKeyError(f"unknown bucket {bucket}")
        root = self.root.resolve()
        path = (root / bucket / key).resolve()
        if path != root / bucket and not path.is_relative_to(root / bucket):
            raise StorageKeyError(f"key escapes bucket {bucket}: {key!r}")
        return path

    def put(self, bucket: str, key: str, data: BinaryIO, size: int) -> str:
        import shutil

        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Chunked copy: uploads (multi-GB ISOs especially) must never be
        # buffered whole in memory.
        with open(path, "wb") as fh:
            shutil.copyfileobj(data, fh, length=4 * 1024 * 1024)
        return f"{bucket}/{key}"

    def get(self, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()

    def exists(self, bucket: str, key: str) -> bool:
        return self._path(bucket, key).exists()

    def list(self, bucket: str) -> list[StoredObject]:
        root = self._path(bucket, "")
        out = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            stat = path.stat()
            out.append(
                StoredObject(
                    key=path.relative_to(root).as_posix(),
                    size=stat.st_size,
                    last_modified=datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ),
                )
            )
        return out


class MinioStorage:
    def __init__(self) -> None:
        from minio import Minio  # imported lazily: dev installs may omit it

        settings = get_settings()
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        for bucket in BUCKETS:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)

    def put(self, bucket: str, key: str, data: BinaryIO, size: int) -> str:
        self.client.put_object(bucket, key, data, size)
        return f"{bucket}/{key}"

    def get(self, bucket: str, key: str) -> bytes:
        resp = self.client.get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def exists(self, bucket: str, key: str) -> bool:
        from minio.error import S3Error

        try:
            self.client.stat_object(bucket, key)
            return True
        except S3Error:
            return False

    def list(self, bucket: str) -> list[StoredObject]:
        return [
            StoredObject(
                key=obj.object_name,
                size=obj.size or 0,
                last_modified=obj.last_modified,
            )
            for obj in self.client.list_objects(bucket, recursive=True)
        ]


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "minio":
        return MinioStorage()
    return LocalStorage(settings.storage_local_root)
