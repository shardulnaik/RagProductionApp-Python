import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3


def _storage_backend() -> str:
    configured_backend = os.getenv("STORAGE_BACKEND")
    if configured_backend is None:
        configured_backend = "s3" if os.getenv("STORAGE_BUCKET_URL") else "local"

    backend = configured_backend.strip().lower()
    if backend not in {"local", "s3"}:
        raise ValueError("STORAGE_BACKEND must be 'local' or 's3'")
    return backend


def _local_storage_root() -> Path:
    configured_path = os.getenv("STORAGE_LOCAL_DIR", "data/uploads")
    return Path(configured_path).expanduser().resolve()


def _storage_location() -> tuple[Any, str, str]:
    bucket_url = os.environ["STORAGE_BUCKET_URL"].rstrip("/")
    parsed = urlparse(bucket_url)

    if parsed.scheme == "s3":
        if not parsed.netloc:
            raise ValueError("STORAGE_BUCKET_URL must include an S3 bucket name")
        endpoint_url = ""
        bucket = parsed.netloc
        prefix = parsed.path.strip("/")
    elif parsed.scheme in {"http", "https"} and parsed.netloc:
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts:
            raise ValueError(
                "STORAGE_BUCKET_URL must include the bucket in its URL path"
            )
        endpoint_url = f"{parsed.scheme}://{parsed.netloc}"
        bucket = path_parts[0]
        prefix = "/".join(path_parts[1:])
    else:
        raise ValueError(
            "STORAGE_BUCKET_URL must be an s3:// URL or an HTTPS bucket URL"
        )

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        aws_access_key_id=os.environ["STORAGE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["STORAGE_SECRET_KEY"],
    )
    return client, bucket, prefix


def upload_pdf(file_name: str, file_bytes: bytes) -> str:
    object_name = Path(file_name).name
    object_key = f"{uuid.uuid4()}/{object_name}"

    if _storage_backend() == "local":
        root = _local_storage_root()
        destination = (root / object_key).resolve()
        if root not in destination.parents:
            raise ValueError("PDF path must stay inside the local storage directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(file_bytes)
        return object_key

    client, bucket, prefix = _storage_location()
    if prefix:
        object_key = f"{prefix}/{object_key}"

    client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=file_bytes,
        ContentType="application/pdf",
    )
    return object_key


def download_pdf(object_key: str) -> str:
    if _storage_backend() == "local":
        root = _local_storage_root()
        source = (root / object_key).resolve()
        if root not in source.parents:
            raise ValueError("PDF path must stay inside the local storage directory")
        if not source.is_file():
            raise FileNotFoundError(f"PDF not found in local storage: {object_key}")

        temporary_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temporary_file.close()
        try:
            shutil.copyfile(source, temporary_file.name)
        except Exception:
            Path(temporary_file.name).unlink(missing_ok=True)
            raise
        return temporary_file.name

    client, bucket, _ = _storage_location()
    temporary_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temporary_file.close()
    try:
        client.download_file(bucket, object_key, temporary_file.name)
    except Exception:
        Path(temporary_file.name).unlink(missing_ok=True)
        raise
    return temporary_file.name
