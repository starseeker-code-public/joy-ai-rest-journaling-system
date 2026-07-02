"""S3-compatible object storage (MinIO) for journal attachments.

Clients never stream bytes through the API: uploads and downloads use
short-TTL presigned URLs. Object keys are namespaced per user:
    {user_id}/{uuid}/{sanitized_filename}

Presigned URLs must be usable from outside the compose network, so they are
signed against STORAGE_PUBLIC_ENDPOINT (e.g. localhost:9000) while bucket
administration uses the in-network endpoint.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

BUCKET = os.getenv('STORAGE_BUCKET', 'joy-attachments')
UPLOAD_TTL = timedelta(minutes=10)
DOWNLOAD_TTL = timedelta(minutes=10)
MAX_ATTACHMENT_BYTES = int(os.getenv('STORAGE_MAX_ATTACHMENT_BYTES', str(10 * 1024 * 1024)))
# Objects younger than this are never swept: an upload may still be in flight
ORPHAN_MIN_AGE = timedelta(hours=1)


class ObjectMissing(Exception):
    """The attachment metadata exists but the object was never uploaded."""


class ObjectTooLarge(Exception):
    """The uploaded object exceeds MAX_ATTACHMENT_BYTES."""

_FILENAME_SAFE = re.compile(r'[^A-Za-z0-9._-]+')


def _sanitize_filename(filename: str) -> str:
    cleaned = _FILENAME_SAFE.sub('_', filename.strip().replace('/', '_'))
    cleaned = cleaned[-128:]
    # '.'/'..' are rejected by S3 object-name validation; treat them as empty
    if cleaned in ('', '.', '..'):
        return 'file'
    return cleaned


def _make_client(endpoint: str):
    from minio import Minio
    return Minio(
        endpoint,
        access_key=os.getenv('STORAGE_ACCESS_KEY', 'joy'),
        secret_key=os.getenv('STORAGE_SECRET_KEY', 'joysecret'),
        secure=os.getenv('STORAGE_SECURE', 'false').lower() == 'true',
        # Pinning the region keeps presigning offline: without it minio-py
        # queries the bucket location first, which the public-endpoint
        # client cannot reach from inside the compose network.
        region=os.getenv('STORAGE_REGION', 'us-east-1'),
    )


def default_clients():
    internal = os.getenv('STORAGE_ENDPOINT', 'localhost:9000')
    public = os.getenv('STORAGE_PUBLIC_ENDPOINT', internal)
    internal_client = _make_client(internal)
    return internal_client, _make_client(public) if public != internal else internal_client


class StorageService:
    def __init__(self, client=None, presign_client=None, bucket: str = BUCKET):
        if client is None:
            client, default_presign = default_clients()
            presign_client = presign_client or default_presign
        self.client = client
        self.presign_client = presign_client or client
        self.bucket = bucket

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def presign_upload(self, user_id: str, filename: str) -> dict:
        object_key = f'{user_id}/{uuid4()}/{_sanitize_filename(filename)}'
        url = self.presign_client.presigned_put_object(self.bucket, object_key, expires=UPLOAD_TTL)
        return {
            'object_key': object_key,
            'upload_url': url,
            'expires_in': int(UPLOAD_TTL.total_seconds()),
        }

    def object_size(self, object_key: str) -> int | None:
        """Size in bytes, or None when the object doesn't exist."""
        from minio.error import S3Error
        try:
            return self.client.stat_object(self.bucket, object_key).size
        except S3Error as e:
            if e.code in ('NoSuchKey', 'NoSuchObject'):
                return None
            raise

    def presign_download(self, object_key: str) -> dict:
        """Raises ObjectMissing / ObjectTooLarge before handing out a URL.

        The size cap is enforced at read time because plain presigned PUTs
        cannot carry a content-length-range condition; an oversized upload
        is deleted on first access.
        """
        size = self.object_size(object_key)
        if size is None:
            raise ObjectMissing(object_key)
        if size > MAX_ATTACHMENT_BYTES:
            self.delete_object(object_key)
            raise ObjectTooLarge(object_key)
        url = self.presign_client.presigned_get_object(self.bucket, object_key, expires=DOWNLOAD_TTL)
        return {'download_url': url, 'expires_in': int(DOWNLOAD_TTL.total_seconds())}

    def download_to(self, object_key: str, path: str) -> None:
        self.client.fget_object(self.bucket, object_key, path)

    def delete_object(self, object_key: str) -> None:
        self.client.remove_object(self.bucket, object_key)

    def cleanup_orphans(self, referenced_keys: set[str], min_age: timedelta = ORPHAN_MIN_AGE) -> list[str]:
        """Delete unreferenced objects older than min_age. Returns deleted keys.

        The age guard prevents sweeping an object whose metadata was written
        after the referenced-keys snapshot (upload still in flight).
        """
        cutoff = datetime.now(timezone.utc) - min_age
        deleted = []
        for obj in self.client.list_objects(self.bucket, recursive=True):
            modified = obj.last_modified
            if modified is not None and modified > cutoff:
                continue
            if obj.object_name not in referenced_keys:
                self.delete_object(obj.object_name)
                deleted.append(obj.object_name)
        return deleted
