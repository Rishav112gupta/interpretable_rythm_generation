"""Media storage abstraction.

Instagram's API does not accept uploaded bytes for images: it downloads the
image from a *public URL* that we give it. So wherever images are stored, the
URL returned by `save()` must be reachable from the internet in production.

* LocalStorage - files on disk, served by the backend at /media/... (good for
  development; for production the backend must be publicly reachable over https).
* S3Storage    - any S3-compatible bucket (AWS S3, Cloudflare R2, DigitalOcean
  Spaces, MinIO) with a public-read base URL / CDN.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class Storage(ABC):
    @abstractmethod
    def save(self, data: bytes, *, folder: str, extension: str, content_type: str) -> str:
        """Store bytes and return the absolute public URL."""

    @abstractmethod
    def read(self, url: str) -> bytes:
        """Read back bytes previously stored (used when re-composing templates)."""

    @staticmethod
    def new_key(folder: str, extension: str) -> str:
        # Unguessable names: media URLs are public (Instagram must fetch them).
        return f"{folder.strip('/')}/{uuid.uuid4().hex}.{extension.lstrip('.')}"


class LocalStorage(Storage):
    def __init__(self, root: str, public_base_url: str) -> None:
        self.root = Path(root).resolve()
        self.base = public_base_url.rstrip("/") + "/media"

    def save(self, data: bytes, *, folder: str, extension: str, content_type: str) -> str:
        key = self.new_key(folder, extension)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"{self.base}/{key}"

    def read(self, url: str) -> bytes:
        prefix = self.base + "/"
        if not url.startswith(prefix):
            raise FileNotFoundError(url)
        path = (self.root / url[len(prefix) :]).resolve()
        if self.root not in path.parents:  # path traversal guard
            raise FileNotFoundError(url)
        return path.read_bytes()


class S3Storage(Storage):
    def __init__(self) -> None:
        import boto3

        self.bucket = settings.s3_bucket
        self.public_base = settings.s3_public_base_url.rstrip("/")
        self.client = boto3.client(
            "s3",
            region_name=settings.s3_region or None,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
        )

    def save(self, data: bytes, *, folder: str, extension: str, content_type: str) -> str:
        key = self.new_key(folder, extension)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return f"{self.public_base}/{key}"

    def read(self, url: str) -> bytes:
        prefix = self.public_base + "/"
        if not url.startswith(prefix):
            raise FileNotFoundError(url)
        obj = self.client.get_object(Bucket=self.bucket, Key=url[len(prefix) :])
        return obj["Body"].read()


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_backend == "s3":
            _storage = S3Storage()
        else:
            _storage = LocalStorage(settings.media_root, settings.public_base_url)
    return _storage


def set_storage(storage: Storage | None) -> None:
    global _storage
    _storage = storage
